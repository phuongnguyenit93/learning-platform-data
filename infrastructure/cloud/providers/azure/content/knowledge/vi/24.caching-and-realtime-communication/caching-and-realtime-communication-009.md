# Tích hợp backend Java với dịch vụ thời gian thực

Một ứng dụng quản lý đơn hàng dùng **Java Spring Boot** có API tạo đơn, duyệt thanh toán và theo dõi trạng thái giao hàng. Khi trạng thái thay đổi, khách hàng mong muốn trang web cập nhật ngay, không phải tải lại trang hoặc gọi REST API mỗi giây. Tương tự, dashboard vận hành cần hiển thị cảnh báo theo thời gian thực, hệ thống hỗ trợ khách hàng cần chat hai chiều và một ứng dụng cộng tác cần phát sự kiện tới nhiều trình duyệt đang mở.

**Azure Web PubSub** cho phép backend phát thông điệp đến các client duy trì kết nối WebSocket mà không phải tự triển khai hàng nghìn WebSocket servers và cơ chế fan-out. Với **Azure SignalR Service**, mô hình tích hợp thường xoay quanh SignalR hubs và hệ sinh thái ASP.NET Core. Backend Java cũng có thể tham gia vào kiến trúc realtime, nhưng cần chọn giao thức/dịch vụ phù hợp thay vì mặc định thư viện Java SignalR client tương đương một SignalR hub server.

Bài học thuộc chương **Cache và giao tiếp thời gian thực** của module **CLOUD_PROVIDERS_AZURE**. Module khám phá hệ sinh thái Microsoft Azure từ subscription, resource group, Microsoft Entra ID đến mạng ảo, compute, lưu trữ và dữ liệu; đồng thời thực hành triển khai, giám sát, bảo vệ và kiểm soát chi phí kiến trúc ứng dụng. Ở đây, trọng tâm là **tích hợp backend Java với dịch vụ thời gian thực trên Azure**, thiết kế luồng sự kiện từ nghiệp vụ đến kết nối WebSocket, bảo vệ subscription/connection credentials, xử lý mất kết nối và vận hành ở quy mô thực tế.

Các ví dụ tập trung vào **Azure Web PubSub Service và Java/Spring Boot**. Những API của Azure SDK có thể thay đổi theo phiên bản; hãy đối chiếu tài liệu SDK và pin dependency trước khi build production. Ví dụ sử dụng tài nguyên, user và tenant giả, không yêu cầu tạo hoặc thay đổi Azure production.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt **request-response HTTP**, **WebSocket**, **Server-Sent Events**, **polling** và **message brokers**.
- Chọn đúng công cụ giữa **Azure Web PubSub**, **Azure SignalR Service**, **Azure Service Bus/Event Hubs** và cache pub/sub.
- Hiểu **hub, client connection, connectionId, userId, group, service endpoint, negotiation endpoint và event handler**.
- Thiết kế Spring Boot backend nhận identity đã xác thực, phát **client access token/URL ngắn hạn** và gửi thông báo tới đúng user/group.
- Phân biệt **server-to-client messaging** với **client-to-server messaging** và khi nào cần một upstream event handler.
- Dùng Azure SDK Java quản lý kết nối dịch vụ, phát message và quan sát phản hồi/errors.
- Kiểm soát quyền **join/send group** theo tenant, không để client tự chọn userId/role tùy ý.
- Hiểu giới hạn của realtime delivery: disconnect, retries, duplicate events, ordering và cách đồng bộ lại dữ liệu.
- Dùng **transactional outbox + Service Bus/worker** khi thay đổi database và phát thông báo cần độ tin cậy cao.
- Thiết kế deployment, secrets/managed identity, Private Link/network, logs, metrics, load test và dự toán chi phí.
- Chẩn đoán lỗi 401/403, WebSocket handshake, lost messages, hot groups, throttling và kết nối rớt.

## 2. Thời gian thực nghĩa là gì?

Trong một ứng dụng web truyền thống:

~~~text
Browser -- HTTP GET /orders/123 --> Java REST API
Browser <-- JSON order status --- Java REST API

Sau 5 giây:
Browser -- HTTP GET /orders/123 --> Java REST API
~~~

**Polling** là việc client hỏi lại sau mỗi khoảng thời gian. Nó đơn giản, tương thích hầu hết hạ tầng, nhưng có thể tạo nhiều request không có dữ liệu mới và tăng độ trễ cập nhật tối đa theo chu kỳ polling.

Với giao tiếp realtime:

~~~text
Browser -- HTTPS negotiate --> Java REST API
Browser <-- connection URL/token -- Java REST API

Browser ====== WebSocket =====> Azure Web PubSub
                                  ^
                                  | Send notification
                           Java backend / worker
                                  ^
                                  |
                           Business state change
~~~

Browser giữ một kết nối WebSocket lâu dài; khi có sự kiện, backend chủ động phát thông báo qua dịch vụ Web PubSub. Đây là mô hình **server push**, giúp giảm độ trễ cảm nhận nhưng **không đảm bảo mọi thông điệp luôn tới client** khi client offline hoặc mạng bị đứt.

### Những chữ "realtime" dễ gây nhầm

| Khái niệm | Ý nghĩa |
|---|---|
| **Low latency delivery** | Giảm thời gian từ lúc event phát sinh đến lúc client nhận |
| **Live connection** | Client và dịch vụ duy trì WebSocket session |
| **Reliable event processing** | Có retry, durability, DLQ và khả năng xử lý lại; không tự có chỉ nhờ WebSocket |
| **Exactly-once business effect** | Không xử lý tác động nghiệp vụ trùng; cần idempotency/transaction design |
| **Strong consistency** | Đọc dữ liệu mới nhất theo mô hình consistency của nguồn; không tự được đảm bảo bởi push |

Mục tiêu thực tế thường là **cập nhật UI nhanh**, có khả năng **kết nối lại và đồng bộ trạng thái**; không nên hứa độ trễ cố định vài mili-giây trong mọi mạng và mọi điều kiện tải.

## 3. Chọn giao thức: WebSocket, SSE, long polling

| Giao thức | Luồng dữ liệu | Ưu điểm | Giới hạn điển hình |
|---|---|---|---|
| **HTTP polling** | Client hỏi theo chu kỳ | Đơn giản, dễ cache/debug | Requests dư thừa, độ trễ theo chu kỳ |
| **Long polling** | Server giữ HTTP request đến khi có dữ liệu/timeout | Dễ tích hợp với HTTP | Quản lý nhiều requests/timeout và reconnect |
| **SSE (Server-Sent Events)** | Server → client, luồng HTTP | Phù hợp thông báo một chiều, trình duyệt có EventSource | Không có kênh gửi binary/two-way như WebSocket |
| **WebSocket** | Hai chiều trên kết nối dài | Chat, notifications, presence, collaborative UIs | Proxy/firewall, lifecycle, auth/reconnect, scaling |
| **Broker/event stream** | Producer → broker → consumers | Durability, retry, decoupling theo service | Không tự thay WebSocket delivery tới browser |

Nếu ứng dụng chỉ hiển thị tình trạng xử lý batch mỗi 30 giây, polling/SSE có thể đủ. Nếu cần fan-out tới nhiều users, group chat hoặc signaling hai chiều, WebSocket với một dịch vụ managed thường phù hợp hơn.

**WebSocket không phải cơ sở dữ liệu hay hàng đợi bền vững**. Một thông điệp đã được service nhận không đồng nghĩa client chắc chắn đã hiển thị và lưu trạng thái đó.

## 4. Phân biệt các dịch vụ Azure liên quan

| Dịch vụ | Vai trò điển hình | Backend Java nên dùng khi |
|---|---|---|
| **Azure Web PubSub** | Managed WebSocket hub, fan-out tới user/group/connections; có server SDK và event handlers | Java/Spring Boot cần phát live updates tới browser/mobile hoặc nhận WebSocket events |
| **Azure SignalR Service** | Scale-out SignalR hub connections; gắn chặt với giao thức và server model SignalR | Ứng dụng có ASP.NET Core SignalR hubs hoặc Java đóng vai trò client theo mô hình phù hợp |
| **Azure Service Bus** | Durable enterprise messaging, queues/topics, dead-letter/retry | Cần xử lý sự kiện backend đáng tin trước khi phát notification |
| **Azure Event Hubs** | Ingest/stream lượng lớn telemetry/events | Cần tiêu thụ event stream, không trực tiếp kết nối browser chat |
| **Azure Cache for Redis / Redis pub/sub** | Cache và pub/sub tốc độ cao, phụ thuộc sản phẩm/tier | Cần cache/presence state hoặc truyền tín hiệu nội bộ; không coi pub/sub là durable delivery |
| **Azure Functions** | Xử lý sự kiện serverless | Worker/event handler chuyển thông báo qua Web PubSub |
| **Azure API Management** | API authentication, gateway và policies | Bảo vệ REST negotiation/backend APIs; không tự thay managed WebSocket hub |

**Java SignalR client** có thể kết nối tới SignalR hub được host bởi server phù hợp, nhưng không biến Spring Boot thành ASP.NET Core SignalR hub server chỉ bằng cách thêm client dependency. Với hệ thống **backend Java là nơi phát và nhận events**, **Azure Web PubSub** thường là lựa chọn trực tiếp hơn cho raw WebSocket/managed PubSub.

Trong một kiến trúc đầy đủ, các dịch vụ bổ trợ:

~~~text
Orders REST API (Java)
       |
       | Database transaction
       v
Azure SQL / Cosmos DB
       |
       | Outbox / domain event
       v
Service Bus / background worker
       |
       | Publish to connected clients
       v
Azure Web PubSub ----> Browsers / mobile clients
~~~

Service Bus ở đây giúp xử lý event bền vững **trước** WebSocket delivery. Client offline cần cơ chế fetch/resync; Service Bus không tự giữ notification cho mọi browser đã ngắt kết nối.

## 5. Azure Web PubSub: thành phần chính

Một tài nguyên Azure Web PubSub có service endpoint, **hubs**, client connections và các API server-side cho việc gửi thông điệp.

| Thành phần | Mô tả | Ví dụ |
|---|---|---|
| **Service instance** | Tài nguyên Azure được cấp SKU/region/network/keys/identity | webpubsub-commerce-dev |
| **Hub** | Không gian logic của ứng dụng, phân tách kết nối và messages | orders |
| **Connection** | Một WebSocket session, có connectionId | Browser tab A |
| **User ID** | Danh tính do trusted server gán khi cấp client token | user-278 |
| **Group** | Tập kết nối để fan-out | tenant-a-orders |
| **Client access token** | Credential tạm thời để kết nối tới hub | Token được negotiate từ backend |
| **Service client** | SDK/REST identity phía server để gửi/quản lý messages | Java WebPubSubServiceClient |
| **Event handler** | Endpoint backend xử lý các sự kiện upstream được cấu hình | /webpubsub/events |
| **Role/permission** | Quyền client join/leave hoặc gửi tới group theo model | webpubsub.joinLeaveGroup.group-name |

### Hub không phải database/schema

Một hub như **orders** là không gian realtime logic. Dữ liệu order thật vẫn nằm trong Azure SQL/Cosmos DB. Không được dùng việc một client đang ở hub để suy luận client sở hữu mọi tài nguyên nghiệp vụ trong backend.

### User và connection không tương đương

Một user có thể mở ba tabs hoặc đăng nhập từ điện thoại và desktop:

~~~text
userId = user-278
   |
   +-- connectionId c-101  (browser tab 1)
   +-- connectionId c-102  (browser tab 2)
   +-- connectionId c-103  (mobile)
~~~

**Send to user** có thể chuyển tới các connections tương ứng với user theo hành vi dịch vụ. **Send to connection** nhắm một session cụ thể. **Send to group** nhắm các connections thuộc group; group membership có thể thay đổi theo kết nối.

## 6. Thiết kế thông báo đơn hàng với backend Java

Ví dụ có ba vai trò:

- **Customer:** xem đơn hàng của mình.
- **Merchant:** xem các đơn thuộc cửa hàng/tenant được phép.
- **Operator:** quan sát dashboard được phân quyền.

Một kiến trúc hợp lý:

~~~mermaid
flowchart LR
    B[Browser / Mobile] -->|HTTPS login + negotiate| A[Spring Boot API]
    A -->|Authn + tenant authz| DB[(Azure SQL / Cosmos DB)]
    A -->|Outbox event| Q[Service Bus]
    Q --> W[Java notification worker]
    W -->|Service SDK: sendToGroup / sendToUser| P[Azure Web PubSub]
    B <-->|WebSocket| P
    B -->|REST resync after reconnect| A
~~~

Các bước:

1. Client đăng nhập bằng phương thức ứng dụng hỗ trợ (ví dụ OIDC/Entra).
2. Client gọi **POST /api/realtime/negotiate** với session/JWT đã được backend xác minh.
3. Backend lấy **userId** và **tenantId** từ principal đáng tin, tạo quyền kết nối giới hạn.
4. Backend trả WebSocket URL/access token ngắn hạn.
5. Client kết nối trực tiếp tới Azure Web PubSub.
6. Khi order được cập nhật và transaction commit, hệ thống phát domain event.
7. Worker dùng Web PubSub server SDK gửi notification tới user/group được phép.
8. Client cập nhật UI hoặc gọi REST API để lấy trạng thái xác thực mới nhất.

**Không phát orderCreated/paid trước khi database commit thành công** nếu UI sẽ hiển thị trạng thái chưa tồn tại. Với yêu cầu tin cậy cao, dùng outbox để tránh lỗi commit thành công nhưng publish thất bại.

## 7. Thiết kế message contract trước khi viết WebSocket code

Không nên gửi trực tiếp toàn bộ database entity. Hãy thiết kế một event payload **nhỏ, ổn định và không nhạy cảm**:

~~~json
{
  "schemaVersion": 1,
  "eventId": "evt-6b9a",
  "type": "ORDER_STATUS_CHANGED",
  "tenantId": "tenant-a",
  "orderId": "order-102",
  "status": "SHIPPED",
  "occurredAt": "2026-11-20T10:20:00Z",
  "resourceVersion": 37
}
~~~

| Trường | Mục đích |
|---|---|
| **schemaVersion** | Khả năng tương thích producer/consumer |
| **eventId** | Dùng để phát hiện duplicate nếu cần |
| **type** | Phân loại event |
| **tenantId/orderId** | Xác định resource, cần ràng buộc quyền |
| **status** | Chỉ chứa dữ liệu có thể hiển thị an toàn |
| **occurredAt** | Thời điểm sự kiện theo UTC |
| **resourceVersion** | Giúp client nhận biết phiên bản/có cần refetch |

### Notification và nguồn dữ liệu chuẩn

Event WebSocket thường chỉ là **tín hiệu thay đổi**, còn API/backend database là **source of truth**. Khi client thấy ORDER_STATUS_CHANGED, có thể fetch **GET /orders/{id}** với authorization để lấy dữ liệu mới nhất.

Lợi ích:

- Không phát PII/secret ra những group quá rộng.
- Client có thể tự phục hồi sau reconnect.
- Cho phép message schema ngắn và có version.
- Hạn chế phụ thuộc UI vào mọi thay đổi database.

Một eventId **không tự chống trùng**: client/server phải lưu hoặc kiểm tra eventId/resourceVersion theo chiến lược idempotency.

## 8. Phân biệt hub, user và group theo tenant

Với SaaS đa tenant, không nên tạo một hub cho **mỗi đơn hàng** mà chưa đánh giá vận hành. Một mô hình đơn giản:

~~~text
Hub: orders
   |
   +-- Group: tenant-a-orders
   |      +-- merchant A browser
   |      +-- merchant A dashboard
   |
   +-- Group: tenant-b-orders
          +-- merchant B browser
          +-- merchant B mobile

Send to user: user-278
  --> tất cả các connections của user đó theo định danh service
~~~

### Quy tắc phân quyền

1. User **không được tự chọn tenantId tùy ý** khi yêu cầu join group.
2. Backend phải kiểm tra user có quyền vào group nào trước khi cấp role hoặc thêm connection.
3. Nếu user mất quyền, phải xem lại **các connections đang hoạt động**, token còn hạn và group memberships.
4. Không cấp quyền **sendToGroup** cho browser chỉ để browser "thử chat" khi use case chỉ cần nhận notifications.
5. Không dùng một group tên **all-users** cho dữ liệu riêng tenant/customer.

**Tên group chỉ là một nhãn định tuyến**, không phải authorization boundary tự có. Với thiết kế an toàn, backend phải kiểm tra quyền và kiểm soát việc cấp group/role theo identity đáng tin.

### Join group khi nào?

Có hai hướng:

- **Server-managed group membership:** backend dùng server SDK/API thêm user/connection vào nhóm khi đã kiểm tra quyền.
- **Client-managed với limited role:** backend cấp role cụ thể cho những group được phép, browser mới được gửi message join/leave tương ứng.

Nếu chỉ cần **server → client**, server-managed membership hoặc user targeting có thể giúp thu hẹp quyền client. Nếu client cần tự join/leave, cấp role giới hạn tên nhóm, TTL và kiểm tra tenant kỹ.

## 9. Negotiation endpoint: cầu nối identity tới Web PubSub

Browser thường **không** tự biết service key; nó gọi backend để lấy URL và token tạm thời.

~~~text
Browser (authenticated)
   |
   | POST /api/realtime/negotiate
   | Authorization: Bearer <APP_ACCESS_TOKEN>
   v
Java backend
   | Validate user identity + tenant membership
   | Select hub / roles / userId
   | Mint short-lived client access token
   v
{ "url": "wss://.../client/hubs/orders?...token..." }
   |
   v
Browser establishes WebSocket to Azure Web PubSub
~~~

### Phân biệt hai credentials

| Credential | Đối tượng giữ | Quyền |
|---|---|---|
| **Service credential/managed identity** | Java backend hoặc worker đáng tin | Server-side send/management/token operations |
| **Client access token** | Browser/mobile client sau khi được xác thực | Kết nối hub và các roles cụ thể được cấp |

**Không bao giờ trả service connection string/account key từ negotiation endpoint.** Client chỉ nhận token ngắn hạn cần thiết cho một kết nối/hub và không được tự gán userId/role.

### Rủi ro khi token nằm trong WebSocket URL

Client access URL có thể chứa token ở query string theo giao thức Web PubSub. Không sao chép URL đầy đủ vào log, analytics, screenshots, support tickets hoặc referrer. Dùng HTTPS cho negotiation, WSS cho kết nối, hạn token ngắn và chính sách không cache.

**Token hết hạn thường kiểm soát việc thiết lập kết nối mới; không mặc nhiên đóng mọi kết nối đã được xác thực từ trước ngay khi hết hạn.** Với revocation thực sự, cần thực hiện disconnect/role removal theo khả năng Web PubSub và thiết kế ứng dụng.

## 10. Quy tắc tạo token an toàn

Backend khi nhận yêu cầu negotiation nên:

1. Bắt buộc người dùng đăng nhập, xác minh chữ ký, issuer, audience, expiry và các claims cần thiết.
2. Xác định **userId** từ identity server-side; không tin client gửi userId khác.
3. Đọc tenant/resource membership từ nguồn đáng tin.
4. Chọn hub phù hợp do server cấu hình.
5. Cấp token với **TTL ngắn** và chỉ các roles/groups cần thiết.
6. Không cấp quyền gửi group khi chỉ cần nhận event.
7. Cấu hình **Cache-Control: no-store** cho response.
8. Giới hạn tốc độ negotiation theo user/IP theo tính năng API gateway.
9. Log user ID dạng an toàn, request correlation và kết quả mà không log token.
10. Kiểm thử token của user A không thể join group tenant B.

### Tại sao không tạo token ở frontend?

Muốn frontend ký client token trực tiếp, bạn phải đưa credential/service secret hoặc quyền ký token vào môi trường public, khiến mọi người dùng có thể tự cấp quyền. **Token chỉ được mint bởi trusted backend** hoặc cơ chế identity/authorization được dịch vụ hỗ trợ và được tổ chức cấu hình.

### Token với nhiều tabs

Một người có thể nhận nhiều client tokens cho nhiều connections. Hãy giới hạn per-user connections nếu nghiệp vụ cần, nhưng tránh giả định mỗi user chỉ có đúng một WebSocket session.

## 11. Chuẩn bị Spring Boot và Azure SDK Java

Mô hình bài thực hành:

~~~text
Java 17 hoặc phiên bản JDK được dự án và SDK hỗ trợ
Spring Boot Web / Spring Security
Azure Web PubSub server SDK (Java)
Azure identity SDK nếu dùng managed identity
REST API orders + notification service
Browser WebSocket client / JavaScript
~~~

Với Maven, cần các dependency theo **các phiên bản tương thích đã được kiểm tra**, chẳng hạn:

~~~xml
<dependencies>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
  </dependency>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-security</artifactId>
  </dependency>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
  </dependency>
  <dependency>
    <groupId>com.azure</groupId>
    <artifactId>azure-messaging-webpubsub</artifactId>
    <version>AZURE_WEBPUBSUB_SDK_VERSION</version>
  </dependency>
</dependencies>
~~~

Đây là **trích đoạn pom.xml**, chưa phải dự án Maven hoàn chỉnh: cần Spring Boot BOM/parent hoặc dependency management, compiler settings và các thư viện production khác. Thay placeholder **AZURE_WEBPUBSUB_SDK_VERSION** bằng bản còn được hỗ trợ/đã kiểm thử; không copy nguyên rồi kỳ vọng Maven build. SDK models và method signatures phải được so với version đã pin.

Nếu chọn managed identity qua credential/token API của SDK, bổ sung **azure-identity** phù hợp:

~~~xml
<dependency>
  <groupId>com.azure</groupId>
  <artifactId>azure-identity</artifactId>
  <version>AZURE_IDENTITY_VERSION</version>
</dependency>
~~~

**Không nhầm Java server SDK để gửi messages với JavaScript/browser client SDK để thiết lập WebSocket.** Hai phía có credentials và vai trò hoàn toàn khác nhau.

## 12. Cấu hình Web PubSub service client trong Java

Trong môi trường **lab** có connection string từ secret store, backend có thể tạo server SDK client một lần và tái sử dụng.

~~~java
package com.example.realtime;

import com.azure.messaging.webpubsub.WebPubSubServiceClient;
import com.azure.messaging.webpubsub.WebPubSubServiceClientBuilder;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class WebPubSubConfiguration {

    @Bean
    WebPubSubServiceClient webPubSubServiceClient(
            @Value("#{environment.getRequiredProperty('webpubsub.connection-string')}")
                String connectionString,
            @Value("#{environment.getProperty('webpubsub.hub', 'orders')}")
                String hubName) {
        return new WebPubSubServiceClientBuilder()
            .connectionString(connectionString)
            .hub(hubName)
            .buildClient();
    }
}
~~~

Các API **WebPubSubServiceClientBuilder, connectionString, hub, buildClient** là pattern của Azure Web PubSub Java server SDK; kiểm tra signatures và transitive dependencies theo SDK version được chọn. Không tạo service client mới cho từng HTTP request. Với ứng dụng chạy nhiều pods/instances, mỗi backend instance có thể có service client riêng hướng tới cùng Azure Web PubSub resource/hub.

### application.yml minh họa

~~~yaml
webpubsub:
  hub: orders
  connection-string: ${WEBPUBSUB_CONNECTION_STRING}

spring:
  application:
    name: orders-backend
~~~

Giá trị **WEBPUBSUB_CONNECTION_STRING** phải lấy từ secure app settings hoặc secret reference, không nằm trực tiếp trong Git. Trong production, ưu tiên **Microsoft Entra ID/managed identity** và role data-plane phù hợp khi Web PubSub SDK/tính năng hỗ trợ. Khi dùng identity, cấu hình bằng endpoint/TokenCredential theo API của version đã pin; không trộn service key với managed identity trong cùng một credential path tùy tiện.

### Service connection string là credential rất nhạy cảm

Nếu leak service key, bên có key có thể có quyền rộng đối với service, tùy mô hình. Khi bị lộ:

1. Đánh giá phạm vi service/keys đang dùng.
2. Thu hồi/rotate key theo kế hoạch, không làm đứt tất cả backend đang chạy.
3. Di chuyển credential qua Key Vault/managed identity.
4. Rà soát logs và access events.
5. Không chỉ xóa key khỏi Git: cần coi key đã leak và rotate.

## 13. Java Spring Boot: negotiation controller

Một endpoint negotiation tốt phải **được bảo vệ bằng Spring Security** và chỉ dựa trên principal đã xác thực.

~~~java
package com.example.realtime;

import com.azure.messaging.webpubsub.WebPubSubServiceClient;
import com.azure.messaging.webpubsub.models.GetClientAccessTokenOptions;
import com.azure.messaging.webpubsub.models.WebPubSubClientAccessToken;
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/realtime")
public class NegotiationController {
    private final WebPubSubServiceClient serviceClient;

    public NegotiationController(WebPubSubServiceClient serviceClient) {
        this.serviceClient = serviceClient;
    }

    public record NegotiationResponse(String url) {}

    @PostMapping("/negotiate")
    public ResponseEntity<NegotiationResponse> negotiate(
            Authentication authentication) {
        if (authentication == null
                || !authentication.isAuthenticated()
                || authentication instanceof AnonymousAuthenticationToken) {
            return ResponseEntity.status(401).build();
        }

        // Ví dụ tối thiểu: principal đã được Spring Security xác thực.
        // Production phải ràng buộc tenant và quyền theo resource riêng.
        String trustedUserId = authentication.getName();

        GetClientAccessTokenOptions options =
            new GetClientAccessTokenOptions()
                .setUserId(trustedUserId);

        WebPubSubClientAccessToken token =
            serviceClient.getClientAccessToken(options);

        return ResponseEntity.ok()
            .cacheControl(CacheControl.noStore())
            .body(new NegotiationResponse(token.getUrl()));
    }
}
~~~

**Lưu ý về tính thực thi:** Đoạn code minh họa Spring Boot 3/Java 17+ và các models trong Azure SDK Web PubSub; cần pin đúng phiên bản và đối chiếu package/signature của **WebPubSubClientAccessToken** với SDK đang dùng. Chưa có toàn bộ SecurityFilterChain, issuer/audience validation và tenant authorization nên **không coi đây là endpoint production hoàn chỉnh**.

### Những phần production cần bổ sung

- Chặn tất cả requests chưa có authentication trong SecurityFilterChain.
- Với Bearer JWT, xác minh **issuer, audience, signature, expiry** và permissions; không chỉ decode JWT mà bỏ kiểm tra chữ ký.
- Tạo userId có namespace ổn định theo hệ thống/tenant; nếu principal name là email, cân nhắc internal opaque ID.
- Kiểm tra user còn thuộc tenant/team hoặc có quyền xem orders.
- Giới hạn TTL token theo khả năng SDK; không dùng token dài ngày cho browser.
- Giới hạn login/negotiate rate và kiểm tra origin/CSRF khi dùng cookie auth.
- Cấu hình service role assignment và logging không chứa URL/token.
- Không cấp quyền gửi group cho user nếu chỉ cần nhận thông báo.

### Client có thể gửi tenantId làm gì?

Nếu API nhận:

~~~json
{"tenantId": "tenant-b", "group": "tenant-b-orders"}
~~~

thì đây chỉ là **dữ liệu đầu vào chưa tin cậy**. Backend phải kiểm tra principal có quyền tenant-b trước khi tạo token, gán group hoặc đăng ký membership. Không dùng nội dung request làm userId/role trực tiếp.

## 14. Java backend gửi sự kiện tới client

Đối với một thông báo chung không nhạy cảm, server SDK có thể gửi tới **mọi connections trong hub**:

~~~java
package com.example.realtime;

import com.azure.messaging.webpubsub.WebPubSubServiceClient;
import com.azure.messaging.webpubsub.models.WebPubSubContentType;
import org.springframework.stereotype.Service;

@Service
public class LiveAnnouncementService {
    private final WebPubSubServiceClient client;

    public LiveAnnouncementService(WebPubSubServiceClient client) {
        this.client = client;
    }

    public void announceMaintenance() {
        client.sendToAll(
            "Scheduled maintenance starts in 15 minutes.",
            WebPubSubContentType.TEXT_PLAIN
        );
    }
}
~~~

Đây là ví dụ minh họa **sendToAll**. Không đưa số dư tài khoản, địa chỉ khách hàng, order details hoặc tenant-specific notifications vào **sendToAll**, vì nó nhắm toàn hub.

### Gửi theo user hoặc group

Trong production, backend cần **targeted delivery**:

~~~text
OrderStatusChanged(tenant-a, order-102)
    |
    +-- Notify user: tenant-a:user-278
    |
    +-- Notify group: tenant-a-orders
~~~

Azure Web PubSub server SDK hỗ trợ các thao tác quản lý/gửi theo **user, group và connection** theo phiên bản được dùng. Trước khi dùng, hãy kiểm tra method signatures **sendToUser**, **sendToGroup**, **addUserToGroup**, **removeUserFromGroup** hoặc API tương ứng trong tài liệu SDK. Đừng tự suy rằng group method tham số có cùng thứ tự trên mọi ngôn ngữ SDK.

**Quy trình nghiệp vụ trước khi gửi**:

1. Xác minh event đến từ nguồn server đáng tin.
2. Đọc tenantId, orderId, resourceVersion và eventId.
3. Kiểm tra recipient/group được phép nhận thông báo.
4. Serialize payload JSON theo schema version.
5. Gửi bằng server SDK và ghi metrics không có PII/secret.
6. Nếu publish thất bại, để worker/outbox retry theo chính sách, không trả trạng thái database về trước khi commit.

**Lỗi publish sau DB commit** không được giải bằng việc tự chạy lại toàn bộ giao dịch tạo đơn nếu điều đó có thể tạo order/charge trùng.

## 15. Browser tạo WebSocket session

Sau khi đăng nhập, browser gọi negotiation endpoint được bảo vệ và dùng WebSocket URL được trả về:

~~~javascript
async function connectNotifications() {
  const res = await fetch("/api/realtime/negotiate", {
    method: "POST",
    credentials: "include",
    headers: {
      "Accept": "application/json"
    }
  });

  if (!res.ok) {
    throw new Error("Negotiation failed with HTTP " + res.status);
  }

  const payload = await res.json();
  const socket = new WebSocket(
    payload.url,
    "json.webpubsub.azure.v1"
  );

  socket.addEventListener("open", () => {
    console.info("Realtime connection established");
  });

  socket.addEventListener("message", (event) => {
    // Có thể nhận cả system/ack messages và application events.
    let frame;
    try {
      frame = JSON.parse(event.data);
    } catch {
      console.warn("Unknown message format");
      return;
    }
    handleRealtimeFrame(frame);
  });

  socket.addEventListener("close", () => {
    console.warn("Realtime disconnected; schedule reconnect");
  });

  socket.addEventListener("error", () => {
    console.warn("WebSocket error");
  });

  return socket;
}

function handleRealtimeFrame(frame) {
  if (frame.type !== "message") return;

  // Kiểm tra payload/schema để tránh render dữ liệu không tin cậy.
  const data = frame.data;
  if (data?.type === "ORDER_STATUS_CHANGED") {
    // Thường nên gọi REST API để lấy trạng thái có authorization.
    console.info("Order changed; refresh affected resource.");
  }
}
~~~

Đây là ví dụ browser dựa trên **Web PubSub JSON subprotocol**. Payload/frame shape cần được xác nhận với subprotocol, dataType và client SDK đang chọn. Nếu chỉ dùng raw WebSocket không chọn subprotocol này, cách đóng gói messages có thể khác. Với giao thức webpubsub JSON, frame **type = message** chỉ là một loại; các frame **system/ack** cần xử lý tùy thiết kế.

### Đừng quên auth của negotiation

Ví dụ dùng **credentials: include** phù hợp khi ứng dụng dùng same-origin cookie sessions và có CSRF protection. Nếu dùng Bearer access token, gửi token ứng dụng tới **backend negotiation** qua header Authorization theo cấu hình bảo mật; **không sao chép service key** sang browser.

### Kết nối mất trong thực tế

Mobile apps chuyển mạng, browser tabs bị suspend, proxies ngắt idle sessions và phiên người dùng hết hạn. App cần:

- Reconnect với **exponential backoff + jitter** và trần giới hạn.
- Gọi negotiation lại khi cần token URL mới.
- Không vòng lặp reconnect liên tục khi backend trả 401/403.
- Khi reconnect thành công, **GET /orders?updatedSince=...** hoặc lấy snapshot mới nhất để lấp khoảng trống.
- Giữ UI hiển thị trạng thái "đang kết nối lại" và degrade gracefully sang polling khi hợp lý.

**Một WebSocket mở thành công không phải bằng chứng user sẽ không bỏ lỡ sự kiện trong các lần reconnect.**

## 16. Reconnect, backoff và đồng bộ trạng thái

Một sơ đồ trạng thái client:

~~~mermaid
stateDiagram-v2
    [*] --> Disconnected
    Disconnected --> Negotiating: authenticated request
    Negotiating --> Connected: WebSocket opens
    Negotiating --> RetryWait: transient error
    Connected --> RetryWait: close/error
    RetryWait --> Negotiating: backoff expired
    Connected --> Resyncing: after successful reconnect
    Resyncing --> Connected: REST snapshot caught up
    Negotiating --> SignedOut: 401/403 or logout
    SignedOut --> [*]
~~~

Ví dụ pseudocode, **không phải JavaScript sản phẩm hoàn chỉnh**:

~~~text
attempt = 0
when websocket closes unexpectedly:
    while signedIn and not connected:
        delay = min(MAX_DELAY, BASE_DELAY * 2^attempt)
        sleep(delay + random jitter)
        request fresh negotiated URL
        try connect
        if connected:
            GET authorized REST snapshot since last resourceVersion
            attempt = 0
            break
        if auth failed permanently:
            stop and ask for sign-in
        attempt++
~~~

### Trạng thái UI không nên phụ thuộc vào một event duy nhất

Giả sử client đã nhận resourceVersion **37**, sau mất kết nối backend phát versions 38 và 39. Khi trở lại, client có thể không nhận lại 38/39 qua Web PubSub. Client nên:

1. Kiểm tra REST snapshot/order version hiện hành.
2. Cập nhật cache/UI theo authoritative state.
3. Nếu server hỗ trợ durable event history, dùng cursor để replay trong phạm vi quyền.
4. Không tin rằng sequence of WebSocket messages tự tạo một event log bền vững.

**ResourceVersion** giúp phát hiện stale/duplicate hoặc cần refetch, nhưng chỉ có ý nghĩa nếu backend gán version nhất quán trong transaction.

## 17. Phân biệt broadcast, user và group messaging

| Kiểu gửi | Đối tượng nhận | Dùng khi | Rủi ro |
|---|---|---|---|
| **sendToAll** | Toàn bộ connections trong hub | Thông báo bảo trì chung | Rò dữ liệu riêng nếu dùng sai |
| **sendToUser** | Connections thuộc user identity | Thông báo cá nhân | UserId mapping sai, nhiều tabs |
| **sendToGroup** | Các connections trong group | Dashboard merchant, room chat | Group membership/tenant isolation sai |
| **sendToConnection** | Một connection cụ thể | Ack hoặc diagnostic giới hạn | Connection có thể đã rớt, ID thay đổi |

### Ví dụ chọn nhóm

Merchant A thuộc tenant-a:

~~~text
userId = tenant-a:user-278
group  = tenant-a:merchant:orders
~~~

Merchant B thuộc tenant-b:

~~~text
userId = tenant-b:user-512
group  = tenant-b:merchant:orders
~~~

Nếu một service event chỉ liên quan order của tenant-a, gửi vào nhóm tenant-b là **lỗi authorization nghiêm trọng**, kể cả message chỉ chứa orderId.

### Không giả định group membership được lưu mãi mãi

WebSocket connection và membership có vòng đời. Khi client disconnect/reconnect, cần xác định lại user/nhóm theo cơ chế dịch vụ và quyền hiện hành. Đừng dùng group membership như database duy nhất lưu danh sách thành viên tổ chức.

## 18. Client-to-server events và upstream event handlers

Không phải ứng dụng nào cũng chỉ cần server push. Chat và collaborative editing có thể cần browser gửi message tới backend.

Azure Web PubSub có thể cấu hình **event handler endpoints** để dịch vụ chuyển một số **system/user events** tới backend theo giao thức/tính năng được hỗ trợ.

~~~text
Browser
   |
   | WebSocket message / client event
   v
Azure Web PubSub
   |
   | Upstream webhook / CloudEvents-style request
   v
Java event handler endpoint
   |
   +-- Validate event origin / signature or configured auth
   +-- Validate user permission and payload
   +-- Execute domain command / persist / publish
   |
   v
Azure Web PubSub service API -> client groups/users
~~~

### Những sự kiện cần hiểu

- **Connect events:** có thể tham gia quy trình chấp thuận kết nối, identity/metadata tùy event handler setup.
- **Connected/disconnected events:** phục vụ presence/diagnostics; delivery/lifecycle cần kiểm tra.
- **User events:** message do client gửi qua upstream route.
- **Service-side messages:** Java worker gửi qua server SDK, không bắt buộc đi qua user event handler.

**Không coi JSON nhận từ event handler là trusted business command** chỉ vì endpoint được gọi từ Web PubSub. Cần xác minh nguồn, quyền user, schema, resource ID và giới hạn payload.

### Event handler là optional

Nếu use case chỉ gửi trạng thái order từ backend tới browser, **không nhất thiết cần tự triển khai upstream event handler**. Có thể dùng negotiation + server SDK send API. Chỉ thêm endpoint khi client-to-server flows, connect lifecycle hoặc business orchestration thật sự cần.

## 19. Xác minh Web PubSub event handler

Một endpoint sự kiện public có thể bị bên ngoài cố gửi HTTP requests giả. Khi cấu hình upstream webhook, dịch vụ có thể sử dụng CloudEvents metadata và cơ chế **origin validation/abuse protection handshake**.

Mô hình kiểm tra:

1. Xác định endpoint path chỉ dành cho Web PubSub events.
2. Áp dụng cơ chế **validation được Azure Web PubSub hỗ trợ** trong Java SDK hoặc library tương ứng; không tự so sánh một header không bảo đảm.
3. Kiểm tra event type, hub, userId/connectionId và nội dung request theo schema.
4. Chặn payload vượt giới hạn, invalid JSON, unexpected operations.
5. Chỉ xử lý command sau khi principal/connection được map tới identity và tenant hợp lệ.
6. Đặt timeouts, retries và idempotency vì upstream có thể gọi lại.
7. Ghi log eventId/correlation; không log access token hoặc raw personal content.

### Abuse protection handshake

Với Web PubSub event handlers, khi thêm URL upstream, Azure có thể gửi một **validation request** với header như **WebHook-Request-Origin**; endpoint đáp ứng theo giao thức **WebHook-Allowed-Origin** ở kịch bản validation được hỗ trợ. Đây là **bước xác nhận URL owner**, không thay thế kiểm tra chữ ký/origin/authorization cho mọi business event về sau.

**Không viết một Spring Controller trả 200 cho mọi POST dưới /events** rồi coi là đã xác minh Web PubSub. Hãy dùng hướng dẫn Web PubSub event handlers và SDK/version đã chọn để xử lý đúng CloudEvents và security; cấu hình network/private access cho upstream endpoint nếu có tính năng hỗ trợ.

## 20. Java event handler: kiến trúc tầng ứng dụng

Một event handler đáng tin nên tách HTTP adapter khỏi business services:

~~~text
WebPubSub upstream callback
        |
        v
HTTP adapter / protocol validator
        |
        v
Identity + tenant authorization
        |
        v
Command validation
        |
        v
Application service (Java)
        |
        +--> Azure SQL/Cosmos DB transaction
        +--> Outbox event
        |
        v
Response / acknowledgement per Web PubSub event contract
~~~

Ví dụ pseudocode Java:

~~~java
public void onClientCommand(VerifiedWebPubSubEvent event) {
    // VerifiedWebPubSubEvent là DTO nội bộ sau khi đã xác thực
    // protocol/origin, KHÔNG phải Azure SDK class.
    String userId = event.trustedUserId();
    String tenantId = event.trustedTenantId();

    if (!permissions.canUpdateOrder(userId, tenantId,
                                     event.orderId())) {
        throw new AccessDeniedException("Not authorized");
    }

    commands.updateOrder(event.orderId(), event.requestedStatus());
    // Domain event được ghi qua outbox, worker publish sau commit.
}
~~~

Đoạn code là **pseudocode mô tả lớp application**, cần triển khai các DTO/services/exception imports, transaction boundaries, validation và response format thực. **Không nhập class VerifiedWebPubSubEvent từ SDK**: đó là tên tự định nghĩa để nhấn mạnh chỉ business layer được nhận event đã xác minh.

### Tại sao không để browser gửi thay đổi trạng thái trực tiếp qua group?

Vì việc client có thể gửi một WebSocket message vào group **không xác nhận** nó có quyền đổi order status ở database. Các thao tác nghiệp vụ nên đi qua API/command handler có authorization, concurrency control, transaction và audit riêng.

## 21. Transactional outbox: tránh mất thông báo sau DB commit

Một anti-pattern rất thường gặp:

~~~text
HTTP POST /orders/123/confirm
   |
   +-- UPDATE orders SET status='CONFIRMED'
   +-- COMMIT thành công
   +-- Send Web PubSub notification  <-- Network timeout!
   |
   v
API đã đổi trạng thái nhưng browser không được báo
~~~

Nếu gửi notification **trước commit**, có thể phát sự kiện rồi transaction rollback, khiến browser thấy trạng thái không tồn tại. Nếu gửi **sau commit** mà không có cơ chế bền vững, publish lỗi có thể khiến notification bị bỏ qua.

### Pattern transactional outbox

~~~text
Java Orders API
    |
    | Database transaction
    +---- UPDATE Orders
    +---- INSERT OutboxEvents
    | COMMIT cả hai
    v
Database
    |
    | Poller / CDC / event bridge
    v
Service Bus (durable message)
    |
    v
Java notification worker
    |
    | Web PubSub SDK send
    v
Connected browsers
~~~

**Đặt bản ghi outbox và thay đổi order trong cùng transaction database** bảo vệ khoảng trống giữa ghi nghiệp vụ và ghi event intent. Tuy nhiên cần thiết kế worker có retries, ordering, idempotency và kiểm soát publish duplicates; outbox **không** tạo exactly-once client delivery.

### Java service transaction minh họa

~~~java
@Service
public class OrderApplicationService {
    private final OrderRepository orders;
    private final OutboxRepository outbox;

    public OrderApplicationService(
            OrderRepository orders, OutboxRepository outbox) {
        this.orders = orders;
        this.outbox = outbox;
    }

    @Transactional
    public void confirmOrder(
            String trustedTenantId, String orderId) {
        Order order = orders.findAuthorizedOrder(
            trustedTenantId, orderId
        );

        order.confirm();
        orders.save(order);

        outbox.save(OutboxEvent.orderStatusChanged(
            trustedTenantId, orderId,
            order.getVersion(), "CONFIRMED"
        ));
    }
}
~~~

**Đây là skeleton kiến trúc**, không phải code build được độc lập; cần imports, repository implementations, transaction manager, entity/schema và exception handling. Với Cosmos DB, transaction boundaries và batch operation phải tuân theo **logical partition** và khả năng transactional batch được API hỗ trợ; không giả định @Transactional của JPA tự quản Cosmos DB partition transactions.

### Worker nên làm gì?

1. Nhận/poll event từ outbox hoặc Service Bus.
2. Xác thực schema, tenant, eventId/resourceVersion.
3. Chọn recipient/group dựa trên dữ liệu đáng tin.
4. Gửi Web PubSub message.
5. Chỉ đánh dấu event hoàn thành sau kết quả gửi theo mức bảo đảm của service API.
6. Khi lỗi transient, retry với backoff; khi lỗi cấu hình/quyền nghiêm trọng, cảnh báo hoặc dead-letter.
7. Dùng idempotency để giảm side effects nếu một event được xử lý lại.

Không xóa outbox event vừa ghi chỉ vì HTTP response tới browser thất bại; lưu/cập nhật trạng thái xử lý độc lập theo runbook.

## 22. Delivery semantics: đã gửi không có nghĩa đã nhận

Một hệ thống WebSocket managed có thể xác nhận **server API request** đã được xử lý nhưng:

- Người dùng đã ngắt kết nối trước khi packet tới browser.
- Browser nhận thông báo rồi crash trước khi render/lưu.
- Một user có nhiều connections, mỗi tab xử lý khác nhau.
- Worker retry cùng event và phát thông báo trùng.
- Message bị mất ở khoảng reconnect.

### Ba mức acknowledgment khác nhau

| Mức | Ai xác nhận? | Chứng minh điều gì? |
|---|---|---|
| **Backend event recorded** | Database/outbox | Intent phát thông báo đã được lưu bền |
| **Web PubSub service accepted send** | Service API/SDK | Dịch vụ đã nhận lệnh gửi theo hợp đồng API |
| **Application client processed event** | Browser/mobile app | UI/code đã xử lý event nếu có explicit acknowledgment |

**Client acknowledgment** nếu cần phải tự thiết kế: client gửi ack gồm eventId, backend xác minh và lưu trạng thái. Ngay cả khi có ack, disconnect và retries vẫn có thể làm message lặp; business effects cần idempotency.

### Event ordering

Nếu order chuyển:

~~~text
PENDING -> CONFIRMED -> SHIPPED -> DELIVERED
~~~

thì hai worker/connections/regions có thể làm client thấy events lệch thứ tự trong điều kiện cụ thể. Đừng giả định Web PubSub bảo đảm global ordering cho mọi user/group/event source.

Một giải pháp:

- Lưu **resourceVersion** tăng đơn điệu theo order.
- Client bỏ qua event version thấp hơn trạng thái đang hiển thị.
- Nếu có bước nhảy version, fetch REST snapshot.
- Không cho event stale làm state backward.

Nếu trạng thái có logic phức tạp, hậu kiểm ở backend vẫn là nguồn sự thật.

## 23. Presence: online/offline là tín hiệu xấp xỉ

Ứng dụng chat muốn hiển thị ai đang trực tuyến. Có thể quan sát kết nối/nhóm và các event connection lifecycle theo Web PubSub capabilities.

### Cẩn trọng với những suy luận

- Một user có **nhiều tabs/devices**.
- Disconnect callback có thể trễ hoặc không đến theo kỳ vọng trong mọi failure mode.
- Một browser tab còn WebSocket không bảo đảm người dùng đang nhìn màn hình.
- Một người dùng offline không đồng nghĩa backend nên xóa toàn bộ subscription của họ.
- Presence có thể phải tổng hợp theo userId, không theo connectionId.

Mô hình:

~~~text
userId = user-278
  c-1 connected, c-2 connected -> online
  c-1 closed, c-2 connected    -> vẫn online
  c-2 closed                   -> offline sau grace period
~~~

Nếu presence là tính năng quan trọng, sử dụng state store có TTL (có thể là cache theo kiến trúc), heartbeat/lifecycle events và reconcile. **Redis/cache presence không thay thế Web PubSub group membership** và ngược lại.

### Thiết kế riêng tư

Trạng thái online có thể là thông tin nhạy cảm. Chỉ hiển thị cho những người được quyền nhìn thấy và tôn trọng "invisible" hoặc trạng thái riêng tư nếu sản phẩm yêu cầu.

## 24. CORS, Origin, WSS và mạng

Một sơ đồ triển khai điển hình:

~~~text
Browser/Client
   |
   | HTTPS negotiate
   v
App Service / AKS Spring Boot API
   |
   | Service SDK HTTPS, RBAC/secret
   v
Azure Web PubSub service
   ^
   | WSS over client WebSocket
Browser
~~~

Hai đường mạng khác nhau:

1. **Browser → Java API:** HTTPS, CORS và authentication cho REST negotiation.
2. **Browser → Web PubSub:** WSS, client token, service endpoint, origin/network settings.
3. **Java API/worker → Web PubSub:** HTTPS SDK requests qua network/identity dành cho server.
4. **Web PubSub → Java event handler:** HTTPS upstream callback chỉ khi cấu hình event handler.

### CORS không phải WebSocket authorization

CORS áp dụng chủ yếu cho browser HTTP fetch/XHR. WebSocket handshake và **Origin** có cơ chế riêng, nên cần kiểm tra **Web PubSub allowed origins**/cấu hình tương đương và token. Một non-browser client có thể tự gửi Origin tùy ý; **chỉ kiểm tra Origin không bảo vệ đủ dữ liệu**.

Nếu SPA chạy từ domain khác Spring Boot API:

- Chỉ cho origin được phép, không wildcard cùng credential cookies một cách nguy hiểm.
- Bảo vệ CSRF khi dùng cookie-based session.
- Dùng HTTPS/WSS, không gọi endpoint HTTP trần.
- Kiểm tra redirect, SameSite cookie và token acquisition.

### Private Endpoint và đường đi client

Khi service/region/SKU hỗ trợ **Private Endpoint** hoặc giới hạn public network:

- Xác định browser ở Internet hay trong VNet/VPN.
- Private Endpoint cho backend nội bộ không tự cho browser Internet kết nối tới endpoint private.
- Kiểm tra Private DNS zone, network routes, firewall/proxy và certificate hostname.
- Nếu browser public cần WebSocket, phải có đường mạng hợp lệ cho browser theo thiết kế.

**Không tắt public network access trên service đang phục vụ browser công khai trước khi xác nhận kiến trúc kết nối thực tế.** Một thay đổi firewall có thể cắt hàng nghìn WebSocket sessions.

## 25. Managed identity, Azure RBAC và Key Vault

Có hai đường cấp credential phổ biến cho Java backend:

| Lựa chọn | Ưu điểm | Hạn chế |
|---|---|---|
| **Connection string/service key** | Cấu hình dễ ở lab, hỗ trợ nhiều SDK scenarios | Secret dài hạn phải bảo vệ và rotate |
| **Microsoft Entra ID/managed identity** | Giảm static secrets, audit theo principal, least privilege | Cần SKU/API/SDK support, data-plane roles, network và dependency |

### Khuyến nghị cho production

1. Bật managed identity cho App Service/AKS workload theo phương thức phù hợp.
2. Cấp **Web PubSub data-plane role** nhỏ nhất cho việc gửi tin/tạo token theo chính sách dịch vụ.
3. Cấu hình SDK bằng endpoint và TokenCredential nếu Java SDK/version hỗ trợ.
4. Với keys còn phải dùng, lưu Key Vault và đưa qua secret reference.
5. Tách identity của **REST API**, **notification worker** và **administrative provisioning** khi cần.
6. Kiểm thử vai trò bằng chính identity thật, không dùng Owner account để debug rồi quên thu quyền.

**Azure Contributor trên resource group không tự đồng nghĩa application identity được phép gửi/nhận messages qua Web PubSub data plane**. Phân biệt management plane với data-plane authorization.

### Chú ý AKS Workload Identity

Nếu Java worker chạy trên AKS, dùng cơ chế **Microsoft Entra Workload ID** với Kubernetes service account/federation khi đã cấu hình; không đặt một service principal client secret chung vào mọi pod. Phải kiểm tra SDK/azure-identity support, token audience và role assignment.

### Key rotation

Khi đổi service key:

- Kiểm kê backend instances/slots dùng key cũ.
- Đổi secret trong Key Vault và restart/refresh theo cơ chế app.
- Test SDK send/negotiation.
- Thu hồi key cũ khi đã xác nhận mọi instances chuyển.
- Quan sát 401/403/retries và cảnh báo.

Client access tokens hiện hữu có vòng đời riêng. **Key rotation và client disconnection** có thể tương tác theo cơ chế token signing; phải thử trên lab và có runbook trước thay đổi production.

## 26. Triển khai backend Java: App Service, AKS hoặc Functions

Azure Web PubSub không thay Java backend. Backend Java có thể chạy trên nhiều nền tảng:

| Nền tảng | Lợi thế | Cần chú ý |
|---|---|---|
| **Azure App Service** | Deploy Spring Boot JAR/container, managed identity, monitoring | VNet Integration, app settings, scale-out, health checks |
| **AKS** | Microservices, workload identity, autoscaling | Pod lifecycle, retries, max concurrent requests, network policy |
| **Azure Container Apps** | Container deployment/serverless scale theo tính năng | Identity, ingress/network, cold start và event consumers |
| **Azure Functions Java** | Xử lý event/worker ngắn từ Service Bus/Event Grid | Hosting constraints, startup, retries, SDK reuse |
| **Azure VM** | Tùy biến toàn phần | Patch/HA/scale vận hành nhiều hơn |

### Bất biến cấu hình theo môi trường

~~~text
DEV:
  WEBPUBSUB_HUB=orders-dev
  Web PubSub instance=dev
  Backend DB/Service Bus=dev
  Identity/RBAC=dev

STAGING:
  WEBPUBSUB_HUB=orders-staging
  Web PubSub instance=staging (hoặc cách ly theo policy)
  Backend DB/Service Bus=staging
  Identity/RBAC=staging

PRODUCTION:
  WEBPUBSUB_HUB=orders
  Web PubSub instance=production
  Backend DB/Service Bus=production
  Identity/RBAC=production
~~~

**Chỉ thay HUB name không phải isolation hoàn chỉnh** nếu một client token/service key vẫn có quyền thao tác nhiều hubs, hoặc backend staging vẫn đọc database/queue production.

### App Service deployment workflow

1. Build Spring Boot JAR/container một lần; lưu Git SHA và artifact digest.
2. Provision Web PubSub instance và networking bằng IaC.
3. Cấp managed identity/data role hoặc Key Vault secret.
4. Deploy code tới staging; cấu hình hub/endpoint/roles đúng môi trường.
5. Smoke test negotiation, WSS handshake, targeted send và reconnect.
6. Kiểm tra multi-instance behavior và metric cost.
7. Promote cùng artifact lên production sau approval.
8. Theo dõi connection count, send failures và app error rate sau rollout.

Nếu dùng App Service deployment slots, **Web PubSub endpoint/connection secret và backend tenant data settings** cần được kiểm tra theo slot stickiness; swap không tự an toàn nếu staging bắt đầu gửi thông báo production.

## 27. Provision Web PubSub trên Portal và Azure CLI

Trong Azure Portal:

1. Chọn **Azure Web PubSub** và đúng subscription/resource group.
2. Tạo service trong region gần workload/client và tuân thủ data residency.
3. Chọn SKU/tier/capacity theo tài liệu và dự toán.
4. Cấu hình network access, allowed origins, identity/keys theo yêu cầu.
5. Cấu hình hub/event handlers nếu ứng dụng cần upstream events.
6. Gán data-plane roles cho backend managed identity.
7. Ghi endpoint hostname và resource ID không nhạy cảm; không dán service key vào tài liệu.

### Đọc metadata bằng CLI

~~~bash
az login
az account set --subscription "<LAB_SUBSCRIPTION_ID>"

RG="<LAB_RESOURCE_GROUP>"
SERVICE="<WEBPUBSUB_RESOURCE_NAME>"

az webpubsub show \
  --resource-group "$RG" \
  --name "$SERVICE" \
  --query "{name:name,location:location,sku:sku.name,hostName:hostName}" \
  --output json
~~~

Đây là lệnh đọc metadata nếu **az webpubsub** command/extension đã được cài đúng. Không dùng **az webpubsub key list** trong logs công khai vì có thể hiển thị service keys. Nếu tài khoản chỉ có Reader, vẫn có thể làm phần thiết kế lab, không cần tạo tài nguyên.

### Tạo service lab có chi phí

Ví dụ **lệnh mẫu** khi tổ chức đã phê duyệt chi phí, region và SKU:

~~~bash
az webpubsub create \
  --resource-group "<LAB_RESOURCE_GROUP>" \
  --name "<UNIQUE_LAB_WEBPUBSUB_NAME>" \
  --location "<AZURE_REGION>" \
  --sku "Standard_S1"
~~~

**Không chạy nếu chưa kiểm tra SKU/region hiện khả dụng, quota, giá và thời hạn lab**. CLI version có thể đòi các tham số hoặc extension khác; xem **az webpubsub create --help** trước. Một tài nguyên realtime chạy nhàn rỗi vẫn có thể tính phí theo tier/capacity.

## 28. Scale, connection capacity và backpressure

Realtime workloads có đặc tính khác HTTP:

- **Số kết nối đồng thời:** mỗi tab/browser/device có thể là một kết nối dài.
- **Thông điệp/giây:** một event có thể fan-out tới nhiều connections.
- **Payload size:** thông điệp lớn tăng network và chi phí/băng thông.
- **Hot groups:** một nhóm quá đông nhận messages liên tục.
- **Peak reconnection:** sau outage, hàng nghìn clients đồng thời negotiate.
- **Region latency:** user xa service region có round-trip lớn hơn.

### Tính tải sơ bộ

Giả định:

~~~text
5.000 users online
Mỗi user trung bình 1,5 WebSocket connections
=> 7.500 concurrent connections

100 notifications/giây
Mỗi notification fan-out trung bình 80 connections
=> 8.000 deliveries/giây theo mô hình ước lượng
~~~

Số liệu chỉ là **giả định tính capacity**, không phản ánh giới hạn hay billing unit thật của Web PubSub. Dịch vụ có thể đo messages/connections theo định nghĩa riêng; phải tra SKU/metrics/pricing hiện hành và benchmark.

### Backpressure ở worker

Nếu mỗi DB event tạo 1000 Web PubSub sends, worker có thể tự quá tải. Hãy:

- Batch/coalesce các thông báo trạng thái nếu nghiệp vụ cho phép.
- Giới hạn concurrency bằng worker pool, queue prefetch và rate control.
- Dùng retry có backoff/jitter cho lỗi transient.
- Không retry vô hạn lỗi 401/403/invalid group.
- Giảm payload; gửi eventId/resourceVersion thay vì toàn bộ aggregate lớn.
- Thiết lập dead-letter/reconciliation cho các messages backend chưa xử lý.

Đừng tăng số AKS pods vô hạn nếu **Web PubSub resource/SDK/network hoặc backend database** đang là bottleneck.

## 29. Metrics, logging và alerting

Một dashboard vận hành cần nhìn cả **Web PubSub service** lẫn **Java/backend**.

| Nhóm | Tín hiệu cần theo dõi | Ý nghĩa |
|---|---|---|
| WebSocket sessions | Connected/disconnected connections, peak count | Capacity, churn, reconnect storms |
| Client traffic | Server-to-client messages, message size, errors | Fan-out, limits, throughput |
| Service APIs | Send requests, failures, rate limits/throttling | SDK/service issues |
| Negotiation API | Requests, 401/403, latency, 5xx | Auth/token mint problems |
| Upstream callbacks | Event success/failure/latency, retries | Client commands/callback health |
| Message backlog | Service Bus queue depth/oldest message, DLQ | Outbox worker có theo kịp nghiệp vụ? |
| Client UI | Reconnect count, time to first update, resync errors | Trải nghiệm end user |
| Java worker | CPU, thread pool, HTTP client requests, exceptions | Bottleneck ứng dụng |
| Security | Unusual token minting, group join denials | Credential misuse/authorization gaps |
| Cost | Concurrent connections, messages, egress, logs | Ngân sách và sizing |

Azure Monitor/metrics và diagnostics có thể khác nhau theo SKU/region/service version. **Không mặc định tất cả các metric tên như bảng đều tồn tại trong Azure Monitor**: đây là các tín hiệu cần thu thập, có thể kết hợp service metrics, Application Insights và application telemetry.

### Correlation ID

Một nghiệp vụ order có thể có:

~~~text
REST requestId
   |
   +-- DB transaction / outbox eventId
   |
   +-- Service Bus messageId
   |
   +-- Java worker attempt
   |
   +-- Web PubSub send result
   |
   +-- Client eventId/resourceVersion
~~~

Cho phép trả lời: "Đơn hàng đã commit lúc nào, event đã đến worker chưa, worker có gọi service thành công không, UI có reconnect không?".

**Không gắn raw service token/WebSocket URL hoặc PII vào correlation field.** Log **eventId** và opaque user reference khi cần.

## 30. Threat model cho kết nối thời gian thực

| Mối đe dọa | Cách tấn công/lỗi | Biện pháp |
|---|---|---|
| Token bị lộ | Client access URL trong log/screenshot | Token ngắn hạn, redaction, HTTPS/WSS |
| Service key bị lộ | Connection string commit vào repo | Managed identity, Key Vault, rotation |
| Cross-tenant subscribe | Client gửi tenantId/group khác | Server-side tenant authz, group role giới hạn |
| Client giả message nghiệp vụ | Browser tự gửi ORDER_PAID | Backend command authorization + DB transaction |
| Replay/duplicate event | Worker retry hoặc reconnect | eventId/resourceVersion, idempotency |
| Flood/reconnect storm | Nhiều tabs/tokens/requests | Rate limiting, quotas, backoff, capacity |
| Backend bypass | Public internal API hoặc webhook không xác thực | Private networking/identity, event validation |
| XSS | Script lấy negotiation token từ SPA | CSP, output encoding, browser security |
| Stale membership | User đã bị thu quyền nhưng socket còn sống | Disconnect/revalidate membership, TTL |
| Sensitive data broadcast | sendToAll order/customer data | User/group targeting, minimal payload |

### Security tests trước release

1. Anonymous negotiation → 401.
2. JWT sai issuer/audience hoặc expired → 401.
3. User tenant A xin group tenant B → 403.
4. Client read-only cố gửi vào group → bị từ chối theo role.
5. User bị revoke quyền nhưng vẫn kết nối → xét disconnect/revalidation.
6. Service key không có trong source, logs, container image, network traces được chia sẻ.
7. Event handler nhận POST giả → bị chặn trước business logic.
8. Reconnect không tự cấp rộng role hơn trước.
9. API GET /orders/{id} vẫn kiểm tra tenant/resource authorization.
10. Client từ network/origin trái chính sách không được vào theo thiết kế.

## 31. Ví dụ Java: gửi JSON tới nhóm đơn hàng

Khác ví dụ **sendToAll** ở mục 14, ứng dụng đa tenant nên gửi notification chỉ tới nhóm đã được backend cấp quyền.

~~~java
package com.example.realtime;

import com.azure.messaging.webpubsub.WebPubSubServiceClient;
import com.azure.messaging.webpubsub.models.WebPubSubContentType;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.stereotype.Service;

@Service
public class OrderNotificationPublisher {
    private final WebPubSubServiceClient client;
    private final ObjectMapper json;

    public OrderNotificationPublisher(
            WebPubSubServiceClient client,
            ObjectMapper json) {
        this.client = client;
        this.json = json;
    }

    record OrderNotice(
        int schemaVersion,
        String eventId,
        String type,
        String orderId,
        String status,
        long resourceVersion
    ) {}

    public void publishToTenant(
            String trustedTenantId,
            String eventId,
            String orderId,
            String status,
            long resourceVersion) throws JsonProcessingException {
        // Tên group được server tính từ tenantId đã xác minh.
        String groupName = trustedTenantId + "-orders";
        OrderNotice notice = new OrderNotice(
            1, eventId, "ORDER_STATUS_CHANGED",
            orderId, status, resourceVersion
        );

        String payload = json.writeValueAsString(notice);
        client.sendToGroup(
            groupName,
            payload,
            WebPubSubContentType.APPLICATION_JSON
        );
    }
}
~~~

Ví dụ cho thấy một **điểm phát thông báo đã tách khỏi REST Controller**. Cần kiểm tra overload **sendToGroup** và enum **WebPubSubContentType** theo version của **azure-messaging-webpubsub** đã pin; code mẫu không có phần worker Service Bus, retries, group setup hoặc SecurityFilterChain. **Không gọi trực tiếp từ transaction trước commit** nếu notification thể hiện sự kiện đã hoàn tất; dùng worker/outbox như mục 21.

### Group membership phải được thiết lập trước

Để client nhận message của **tenant-a-orders**, backend/service phải thêm connection/user vào group theo cơ chế Web PubSub được chọn, hoặc cấp quyền client join đúng group rồi thực hiện join. **Gửi tới tên group không tự đăng ký user vào group.**

Khi dùng client-managed join, cần cấp role **webpubsub.joinLeaveGroup.<group>** đúng tên nhóm theo format được dịch vụ hỗ trợ và không cấp wildcard rộng ngoài ý định. Với mô hình server-managed group membership, phía backend giữ kiểm tra quyền và thực hiện add/remove khi connect/reconnect/revocation.

### Contract JSON phải tương thích client

Browser ở mục 15 kiểm tra **frame.data.type**. Với sendToGroup có **APPLICATION_JSON**, khung sự kiện được xử lý qua JSON subprotocol theo schema service/client. Cần kiểm tra frame fields với SDK/protocol thực tế và không coi string/plain text cùng JSON message là một dạng.

## 32. Bảng xử lý sự cố thường gặp

| Hiện tượng | Nguyên nhân khả dĩ | Kiểm tra |
|---|---|---|
| Negotiate trả 401 | Không đăng nhập, session expired, JWT sai | Spring Security filter, issuer/audience, auth logs |
| Negotiate trả 403 | Thiếu quyền tenant/role | Principal, tenant membership, policy |
| WebSocket handshake 401/403 | Client token sai/hết hạn, hub/role sai | Token TTL, trusted userId, service settings |
| WebSocket 404 hoặc host không hợp lệ | URL/hub/service endpoint sai | URL từ negotiation, service region/hostname |
| Browser báo CORS nhưng REST hoạt động | Origin của negotiation khác, preflight bị từ chối | Browser network tab, API CORS/SameSite |
| REST negotiate OK, WebSocket không mở | WSS bị proxy/firewall chặn, origin, TLS, network | DevTools WS, DNS, service public/private settings |
| Client connect nhưng không nhận group message | Chưa join group, tên group/role sai | Membership, send target, user/connection IDs |
| User A nhận event tenant B | Group mapping hoặc authorization sai | Dừng phát, audit identity/group, negative tests |
| Send API 401/403 | Service key sai hoặc identity không đủ data-plane role | Credential, RBAC, SDK scope |
| Send API 429/throttled | Service/plan capacity, burst/retry storm | Service metrics, messages/connection, backpressure |
| UI bỏ lỡ trạng thái sau reconnect | WebSocket không durable | REST resync, event version |
| UI nhận duplicate events | Worker retry, multiple sessions | eventId/resourceVersion, idempotency |
| UI hiện trạng thái cũ | Event out of order hoặc stale cache | Resource version, authoritative GET |
| Event handler bị retry liên tục | HTTP validation/timeout, lỗi event response | Handler logs, auth, event contract |
| App Service staging gửi prod | Connection/hub/backend config sai | Sticky settings, environment isolation |
| Sau rotate key, mọi clients rớt | Service auth/key strategy chưa chuẩn | Key rotation runbook, token lifecycle |

**Điều tra từng lớp theo thứ tự:** browser/network → negotiation/auth → Web PubSub connection → group membership → backend publish → outbox/broker → source-of-truth DB. Một WebSocket error không mặc nhiên là lỗi Java code.

## 33. Tình huống A: negotiation thành công nhưng WebSocket 403

**Bối cảnh:** Java API trả 200 và một WebSocket URL. Browser dùng URL đó nhưng handshake thất bại với 403.

### Những nguyên nhân nên kiểm tra

1. URL/token có bị cắt bớt hoặc bị encode hai lần khi truyền cho client không?
2. Token có bị hết hạn do browser cache, thời gian giữa negotiation và connect quá lâu không?
3. Hub trong URL có khớp hub của Web PubSub service không?
4. Allowed origins/service network policy có chặn browser không?
5. Token có được ký bằng đúng service credential/identity config không?
6. Service data-plane roles có đủ cho token minting không?
7. Endpoint có phải private-only trong khi browser ở public Internet không?

### Runbook

- Dùng request/correlation ID không nhạy cảm để đối chiếu negotiation logs và service metrics.
- Kiểm tra một client test trong lab, dùng token vừa negotiate.
- Đối chiếu service hostname/hub và config production.
- Nếu auth sai, sửa server-side token/role configuration; không đưa service key cho browser để "thử".
- Nếu network bị chặn, xác định topology trước khi thay firewall.
- Thử lại và xác nhận group targeted message đến đúng user.

**Không log URL đầy đủ có token** vào Browser Console hoặc server diagnostics khi điều tra.

## 34. Tình huống B: một merchant nhận được thông báo của tenant khác

**Bối cảnh:** merchant thuộc tenant-b nhận notification **ORDER_STATUS_CHANGED** cho order tenant-a. Backend dùng groupName do browser gửi khi negotiate.

### Nguyên nhân gốc

Ứng dụng đã **tin đầu vào group/tenantId từ client** thay vì ràng buộc theo principal đã xác thực và quyền trong database. Dù không chứa PII, event lộ orderId/status giữa tenants có thể là sự cố bảo mật.

### Runbook

1. Ngừng hoặc giới hạn quyền join/send group bị ảnh hưởng.
2. Kiểm tra token roles đã phát, membership hiện hành và danh sách các user có thể nhận dữ liệu sai.
3. Thu hồi/disconnect sessions và tạo lại credentials khi cần.
4. Sửa negotiation logic để server tự tính group theo tenant membership.
5. Áp kiểm tra resource ownership cho mọi business command.
6. Thiết kế negative tests: tenant-a không thể join tenant-b, kể cả khi sửa request và replay token.
7. Đánh giá phạm vi lộ dữ liệu, audit và quy trình incident response.

**Không chỉ đổi tên group cho khó đoán**: tên group không phải secret hoặc cơ chế authorization.

## 35. Tình huống C: đã cập nhật order nhưng UI không nhận thông báo

**Bối cảnh:** REST endpoint trả 200 và database có trạng thái SHIPPED, nhưng dashboard vẫn hiển thị CONFIRMED.

### Truy vết theo correlation

~~~text
Order DB row status SHIPPED?
        |
        v
Outbox record tồn tại và committed?
        |
        v
Worker nhận event / Service Bus message?
        |
        v
Worker Web PubSub send thành công?
        |
        v
Client có đang connected + đúng group?
        |
        v
Client xử lý event đúng schema/version?
        |
        v
REST resync/update UI thành công?
~~~

### Các khả năng

- Code publish trực tiếp sau commit nhưng gặp timeout và **không có outbox**.
- Worker nhận event nhưng lỗi serialization/auth, message vào DLQ.
- Browser mất kết nối ở thời điểm message gửi.
- Merchant chưa join group do reconnect không setup membership.
- Client nhận sự kiện version 38 nhưng cache xử lý nhầm version 37.

### Cách xử lý

- Nếu có outbox, replay chưa xử lý với eventId duy nhất, tránh tạo order trùng.
- Cải thiện retries/backoff/DLQ cho worker.
- Bổ sung REST resync để UI không phụ thuộc duy nhất notification.
- Thêm thông số **time from DB commit to client display** và cảnh báo theo SLO.
- Không rollback database chỉ để ép websocket notification được gửi lại.

## 36. Tình huống D: hàng nghìn clients reconnect cùng lúc

**Bối cảnh:** Web PubSub region/network có sự cố ngắn. Sau khi phục hồi, hàng chục nghìn tabs cùng gọi negotiation trong một giây, Java backend bắt đầu 429/5xx.

### Vấn đề

- REST negotiation bị spike, tạo áp lực lên authentication/identity provider.
- Backend/Key Vault/DB kiểm tra tenant membership cùng lúc.
- Nhiều kết nối WebSocket được mở đồng thời.
- Retried event deliveries khiến worker queue backlog tăng.

### Giải pháp

1. Dùng exponential backoff **có jitter** ở client.
2. Rate limit negotiation endpoint với thông báo retry rõ.
3. Đặt cap reconnect attempts và yêu cầu đăng nhập lại khi 401.
4. Cache membership an toàn với TTL ngắn nếu đủ điều kiện.
5. Sizing Web PubSub connections/throughput theo **peak**, không chỉ average.
6. Giảm payload/giới hạn tần suất notifications khi service quá tải.
7. Đảm bảo browser **resync** qua REST sau khi kết nối lại.

**Không để 10.000 clients cố mở kết nối mỗi 100 ms vô hạn**: retry storm có thể gây sự cố thứ cấp ngay khi dịch vụ bắt đầu hồi phục.

## 37. Bài lab: Spring Boot Orders realtime

Bài thực hành có hai mức:

- **Thiết kế và thử local:** không phải tạo tài nguyên Azure nếu chưa có subscription/quyền.
- **Sandbox Azure:** dùng Web PubSub resource, identity và backend lab đã được phê duyệt về ngân sách.

### Yêu cầu nghiệp vụ

Bạn xây ứng dụng **Orders Live** gồm:

- Spring Boot REST API trả order status và có **/api/realtime/negotiate**.
- Web PubSub hub tên **orders**.
- Browser của merchant A xem thông báo trong group **tenant-a-orders**.
- Browser của merchant B xem group **tenant-b-orders**.
- Khi order trạng thái đổi, server phát **ORDER_STATUS_CHANGED** theo tenant.
- Browser mất mạng phải reconnect và resync trạng thái qua REST.
- Không đưa credential thật vào source hoặc log.

### Phần A: lập ma trận luồng

| Luồng | Caller | Receiver | Authn/authz |
|---|---|---|---|
| HTTP login | Browser | Identity provider/backend | OIDC/JWT/cookie theo thiết kế |
| HTTP negotiate | Browser | Spring Boot | Principal hợp lệ, tenant membership |
| WSS connect | Browser | Azure Web PubSub | Client access token đúng hub/role |
| Group membership | Browser/backend | Azure Web PubSub | Server kiểm tra group được phép |
| DB status change | Trusted API | Azure SQL/Cosmos DB | Nghiệp vụ + transaction |
| Outbox/worker | Database/Service Bus | Java notification worker | Managed identity/queue permissions |
| Server send | Worker | Web PubSub service | Server identity/service credential |
| Browser fetch latest | Browser | Spring Boot | Resource-level authorization |

**Câu hỏi kiểm tra:** luồng nào được phép chạm dữ liệu production? Câu trả lời là **không luồng nào của lab**; mọi endpoint/tenant/resources phải thuộc sandbox.

### Phần B: tạo project Java local

1. Tạo một ứng dụng Spring Boot với Java 17+ theo phiên bản Spring/SDK được hỗ trợ.
2. Thêm Spring Web, Security/OAuth Resource Server và Azure Web PubSub SDK.
3. Thêm **WebPubSubConfiguration** ở mục 12.
4. Thêm **NegotiationController** ở mục 13.
5. Thêm **OrderNotificationPublisher** ở mục 31.
6. Tạo REST endpoint GET /orders/{id} có kiểm tra principal và tenant.
7. Tạo fake in-memory orders cho lab thay vì dùng dữ liệu thật.
8. Nếu chưa có Azure resource, mock SDK service layer và unit test negotiation/auth/targeting logic.

### Phần C: cấu hình môi trường

Với lab Azure có Key Vault hoặc secure app settings:

~~~text
SERVICE_ENV=lab
WEBPUBSUB_HUB=orders
WEBPUBSUB_CONNECTION_STRING=<FROM_SECRET_STORE_ONLY>
ORDER_BACKEND_DATA_SOURCE=mock-or-lab-database
APP_VERSION=lab-1.0.0
~~~

**Đây là mô hình biến môi trường**, không phải một file chứa secret thật. Ánh xạ tên biến với Spring Boot property binding/Spring configuration đã chọn, vì **WEBPUBSUB_HUB** và **webpubsub.hub** có thể cần mapping/relaxed binding được xác minh. Không giả định mọi host tự hiểu mọi tên key.

### Phần D: dùng browser test client

1. Đăng nhập user thuộc tenant-a.
2. Gọi negotiation endpoint, kiểm tra 200 và **Cache-Control: no-store**.
3. Kết nối WebSocket với URL được trả về.
4. Nếu dùng client-managed join, chỉ join group tenant-a-orders với role tương ứng; nếu server-managed, backend thực hiện membership.
5. Cho backend/worker phát sự kiện thử cho tenant-a.
6. Kiểm tra browser A nhận **ORDER_STATUS_CHANGED** theo đúng frame/protocol.
7. Kiểm tra browser B không nhận event tenant-a.
8. Ngắt mạng browser A, cập nhật trạng thái giả, reconnect và REST resync.

### Phần E: kiểm thử negative cases

| Case | Thao tác | Kỳ vọng |
|---|---|---|
| 1 | Anonymous gọi negotiate | 401 |
| 2 | User A xin token cho user B | Server bỏ qua hoặc từ chối input giả |
| 3 | Tenant A xin group tenant B | 403 hoặc không được cấp role |
| 4 | Dùng token đã hết hạn cho kết nối mới | Handshake bị từ chối theo service |
| 5 | Read-only browser cố send group message | Bị từ chối bởi role/policy |
| 6 | WebSocket mất kết nối giữa hai events | Client fetch REST snapshot và cập nhật |
| 7 | Worker gửi trùng một eventId | UI không đảo trạng thái hoặc tạo side effect trùng |
| 8 | Service send tạm lỗi | Worker retry/alert, không mất bản ghi outbox |
| 9 | Quên group membership sau reconnect | Test phát hiện và sửa membership |
| 10 | Backend permission bị thu hồi | Không thể tiếp tục query order khác tenant |

Không dùng hai tenants/khách hàng thật để chứng minh quyền bằng cách cố truy cập dữ liệu ngoài thẩm quyền; dùng accounts/test data tạo riêng trong lab.

### Phần F: bảng bằng chứng thực hành

| Bằng chứng | Điều cần ghi |
|---|---|
| Module/platform | Spring Boot/Java/SDK versions, Web PubSub tier và region |
| Identity | Cách authentication, principal/tenant mapping, quyền dịch vụ |
| Negotiation | HTTP status, token TTL config, no-store và redaction |
| Connection | WebSocket open/close, subprotocol, group join |
| Delivery | eventId, correct tenant, latency quan sát được |
| Reconnect | Backoff và REST resync đúng trạng thái |
| Negative test | Cross-tenant/anonymous/expired token bị chặn |
| Durability | Outbox/Service Bus design hoặc giới hạn khi không có |
| Monitoring | Connections, service sends, errors, 429, backlog |
| Cost | Giả định concurrent connections, messages và cleanup |

### Dọn môi trường lab

- Chỉ xóa Web PubSub resource, Key Vault secrets và test services **do chính lab tạo và sở hữu**.
- Không xóa resource group dùng chung hoặc xoay key production.
- Ngắt kết nối test clients và xóa dữ liệu thử theo retention.
- Xóa credentials cục bộ khỏi shell history/artifacts nếu đã vô tình lưu.
- Xác minh subscription chi phí, tags và resources đã được dọn an toàn.

## 38. Tích hợp CI/CD và kiểm thử tự động

Không nên chỉ click thử WebSocket bằng tay. CI/CD có thể kiểm tra nhiều lớp:

~~~mermaid
flowchart TD
    A[Commit Java + IaC + message schema] --> B[Build + unit tests]
    B --> C[Security and dependency scanning]
    C --> D[Deploy dev/sandbox]
    D --> E[Test negotiation and identity]
    E --> F[Test WS connect + tenant groups]
    F --> G[Test send, reconnect and resync]
    G --> H[Test worker retries and idempotency]
    H --> I{Staging approval?}
    I -- No --> J[Stop and investigate]
    I -- Yes --> K[Promote same artifact]
    K --> L[Monitor production SLO + cost]
~~~

### Unit tests

- Backend không cho anonymous user negotiate.
- Từ principal tenant-a tạo group target tenant-a, không dùng group do client tự gửi.
- Domain event có schemaVersion/eventId/resourceVersion.
- Worker retry đúng lỗi transient; không retry invalid authorization vô hạn.
- Notification sender không dùng sendToAll cho các event riêng tư.
- Order mutation và outbox record được ghi trong cùng transaction theo database được chọn.

### Integration tests

- Token được Web PubSub chấp nhận trên đúng hub.
- Group assignment chính xác với nhiều connections của cùng user.
- Service SDK targeted send nhận được ở client được phép.
- Kết nối ngắt trong lúc send không khiến UI mất state vĩnh viễn sau resync.
- Event handler từ nguồn giả không được thực thi business command.
- Key/managed identity thiếu data-plane role gây lỗi và có alert.
- Staging không kết nối Web PubSub/backend production.

### Load tests

Kiểm tra:

1. Concurrent connections tăng dần theo mức đã phê duyệt.
2. Tốc độ negotiate trong reconnect storm.
3. Fan-out cùng group và nhiều small groups.
4. Worker send p95 latency, 429, queue backlog.
5. Browser time-to-update và UI memory khi nhiều messages.
6. Scale-out backend Java/AKS không làm tăng duplicate business effects.

Không tạo lượng kết nối vượt quota/tier hoặc gây DoS trên môi trường dùng chung; load test có kế hoạch capacity và ngân sách rõ.

## 39. Chi phí và dự toán kiến trúc realtime

Một hệ thống managed realtime có thể phát sinh chi phí ở nhiều lớp:

| Hạng mục | Yếu tố ảnh hưởng |
|---|---|
| **Azure Web PubSub service** | SKU/tier, units/capacity, connections, messages theo pricing model |
| **Java backend** | App Service plan, AKS nodes, Container Apps/Functions usage |
| **Azure Service Bus** | Queues/topics, messages, broker tier/operations |
| **Database** | SQL/Cosmos DB writes, outbox storage, reads phục vụ resync |
| **Network** | Egress, Private Link/Private Endpoint, DNS, NAT theo topology |
| **Observability** | Application Insights/Log Analytics ingestion, retention, alerts |
| **Security** | Key Vault operations, identity/admin infrastructure |
| **CI/CD** | Build runners, image registry/artifact storage, integration/load tests |

### Không nhầm số connections và số users

Một user có thể mở nhiều tabs và devices. **5.000 active users không chắc chỉ có 5.000 concurrent connections**. Tổng messages tính theo cơ chế tính phí của dịch vụ cũng không nhất thiết bằng số lần backend gọi send API: một broadcast có thể tạo nhiều client deliveries; phải kiểm tra pricing definitions của tier hiện hành.

### Mẫu bảng sizing

| Đại lượng | Giá trị giả định | Nguồn cần đo |
|---|---:|---|
| Daily active users | 20.000 | Product analytics |
| Peak concurrent users | 5.000 | Usage/traffic models |
| Avg connections/user | 1,5 | Client telemetry |
| Peak connections | 7.500 | Multiplication + headroom |
| Backend events/s | 100 | Service Bus/outbox metrics |
| Avg recipients/event | 80 | Group membership distribution |
| Estimated fan-out/s | 8.000 | Events × recipients |
| Avg payload bytes | 500 | Serialized event samples |
| Reconnect peak | Cần load test | WebSocket churn/history |

**Số liệu hoàn toàn giả định**, không phải bảng giá/giới hạn chính thức. Chỉ sau khi đo thật mới nên chọn tier và số units, regions, autoscaling strategy/DR.

### Tối ưu chi phí

- Giảm phát lặp các trạng thái không đổi.
- Coalesce progress events (ví dụ 1%, 2%, 3% → cập nhật mỗi 5% khi hợp lý).
- Không gửi toàn bộ JSON entity lớn qua WebSocket.
- Chỉ phát cho user/group cần thiết.
- Không giữ unused connections hoặc reconnect liên tục.
- Dùng REST snapshot và client cache thay vì push mọi field change.
- Tối ưu Service Bus/outbox retries và hạn chế DLQ growth.
- Đặt tags, budgets, alerting; dọn tài nguyên lab sau test.

**Budget alerts không tự ngừng mọi khoản tính phí.** Một Web PubSub instance ít traffic vẫn có thể phát sinh chi phí capacity theo tier được cấp.

## 40. Checklist production-ready

- [ ] Đã xác định realtime use case cần WebSocket, không chỉ polling/SSE.
- [ ] Đã so sánh Web PubSub, SignalR, Service Bus và Redis pub/sub theo yêu cầu Java.
- [ ] Đã chọn region, SKU/tier và capacity từ concurrent connections/fan-out peak.
- [ ] Java SDK/dependencies/JDK đã pin version tương thích.
- [ ] Service client được tái sử dụng, không tạo mới mỗi request.
- [ ] Negotiation endpoint dùng HTTPS và principal được xác thực đầy đủ.
- [ ] UserId/tenantId/roles lấy từ nguồn server-side tin cậy, không tin client input.
- [ ] Client access tokens có TTL ngắn/no-store, không xuất hiện trong logs.
- [ ] Managed identity hoặc Key Vault được dùng cho server credential.
- [ ] Đã kiểm tra data-plane RBAC riêng management RBAC.
- [ ] Group membership được giới hạn theo tenant và tái cấp khi reconnect.
- [ ] Không broadcast PII/tenant-specific messages vào toàn hub.
- [ ] Event handler có protocol/origin validation, authorization và idempotency.
- [ ] Message schema có version/eventId/resourceVersion; không gửi secrets.
- [ ] Domain commit và notification được phối hợp bằng outbox/worker khi cần tin cậy.
- [ ] UI có reconnect backoff + REST resync sau disconnect.
- [ ] Business APIs vẫn kiểm tra resource/tenant authorization.
- [ ] Có tests cho anonymous/wrong-tenant/expired-token/revoked-role cases.
- [ ] Có observability từ DB commit → Service Bus → Web PubSub → client.
- [ ] Có alerts cho send errors, 429, connection churn, negotiation failures và backlog.
- [ ] Network/public-private topology đã được kiểm thử từ browser và backend.
- [ ] Dev/staging/prod tách identity, hub/instance, event source và secrets.
- [ ] CI/CD sử dụng artifact đã kiểm thử, approvals, canary/rollback và data compatibility.
- [ ] Có runbook key rotation, service failover/reconnect storm và incident response.
- [ ] Đã benchmark peak connections/message size/fan-out và dự toán chi phí.

## 41. Câu hỏi tự kiểm tra

1. Polling, SSE và WebSocket khác nhau về luồng thông tin và quản lý kết nối như thế nào?
2. Khi nào backend Java nên chọn Azure Web PubSub thay vì Azure SignalR Service?
3. Azure Service Bus có thể thay Web PubSub để push trực tiếp tới browser không?
4. Hub, group, userId và connectionId khác nhau ra sao?
5. Một user có ba tabs thì có bao nhiêu WebSocket connections theo mô hình thông thường?
6. Negotiation endpoint phải xác thực gì trước khi trả token?
7. Vì sao browser không được nhận service connection string?
8. Client access token hết hạn có bắt buộc đóng mọi connection hiện hữu không?
9. Vì sao không thể tin một groupName do browser tự gửi?
10. Server-managed membership và client-managed join có điểm gì khác?
11. Khi nào cần quyền sendToGroup cho browser và khi nào không?
12. Dùng sendToAll cho thông báo hóa đơn riêng là lỗi gì?
13. JSON subprotocol khác raw WebSocket message framing như thế nào?
14. Khi browser nhận một ORDER_STATUS_CHANGED, vì sao nên fetch REST snapshot?
15. Có thể bỏ lỡ WebSocket message nào trong lúc mất kết nối?
16. ResourceVersion/eventId giúp xử lý stale/duplicate events như thế nào?
17. Outbox bảo vệ khoảng trống giữa database commit và publish ra sao?
18. Outbox có bảo đảm browser nhận exactly-once không?
19. Vì sao Service Bus worker cần retry, DLQ và idempotency?
20. Presence online/offline có bằng chứng người dùng đang xem màn hình không?
21. CORS và WebSocket Origin có thay thế token authentication không?
22. Private Endpoint backend có giúp browser Internet tự kết nối vào service private-only không?
23. Azure RBAC Contributor có tự cấp quyền gửi message qua Web PubSub data plane không?
24. Managed identity và Service Bus/Key Vault phối hợp với Java worker thế nào?
25. Vì sao staging slot có thể phát nhầm message production?
26. Một reconnect storm có thể làm API negotiation quá tải bằng cách nào?
27. Trước khi scale AKS pods, cần đo giới hạn nào ở Web PubSub và database?
28. Số gửi từ backend có luôn bằng số message tới client không?
29. Kiểm tra gì khi negotiate 200 nhưng WebSocket handshake trả 403?
30. Cần thông số gì để xác nhận thời gian từ DB commit đến UI update?
31. Rollback Java app có tự thu hồi token đã cấp và undo event đã gửi không?
32. Vì sao cần giữ message payload nhỏ và schema versioned?
33. Ứng dụng chat client-to-server cần bổ sung backend event handler ở đâu?
34. Khi nào một ứng dụng đơn giản không cần upstream event handler?

## 42. Tài liệu tham khảo

- [Azure Web PubSub overview](https://learn.microsoft.com/azure/azure-web-pubsub/overview) — managed WebSocket và use cases.
- [What is Azure Web PubSub?](https://learn.microsoft.com/azure/azure-web-pubsub/overview#what-is-azure-web-pubsub-service) — thành phần kiến trúc và giao thức.
- [Azure Web PubSub Java quickstart](https://learn.microsoft.com/azure/azure-web-pubsub/quickstart-pubsub-java) — Java service SDK và publish messages.
- [Azure Web PubSub client protocol](https://learn.microsoft.com/azure/azure-web-pubsub/concept-client-protocols) — raw WebSocket/JSON subprotocol và client events.
- [Azure Web PubSub client access tokens](https://learn.microsoft.com/azure/azure-web-pubsub/concept-client-access-token) — kết nối client, role và scope.
- [Azure Web PubSub event handlers](https://learn.microsoft.com/azure/azure-web-pubsub/concept-service-internals#event-handler) — upstream connect/user events và bảo vệ callback.
- [Azure Web PubSub security best practices](https://learn.microsoft.com/azure/azure-web-pubsub/concept-security) — authorization và secure connections.
- [Azure Web PubSub Java SDK](https://learn.microsoft.com/java/api/overview/azure/messaging-webpubsub-readme) — Java server SDK và model types.
- [Azure Web PubSub monitoring](https://learn.microsoft.com/azure/azure-web-pubsub/howto-monitor-azure-web-pubsub) — connections, diagnostics và Azure Monitor.
- [Azure SignalR Service overview](https://learn.microsoft.com/azure/azure-signalr/signalr-overview) — SignalR hubs và service models.
- [Azure Service Bus documentation](https://learn.microsoft.com/azure/service-bus-messaging/service-bus-messaging-overview) — durable messaging/queues/topics.
- [Microsoft Entra workload identity for AKS](https://learn.microsoft.com/azure/aks/workload-identity-overview) — Java pod identity.
- [Spring Security OAuth2 Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/index.html) — bearer token validation.
- [Azure CLI az webpubsub](https://learn.microsoft.com/cli/azure/webpubsub) — quản lý service metadata và provisioning.
- [Azure Pricing Calculator](https://azure.microsoft.com/pricing/calculator/) — dự toán chi phí backend/managed realtime.

**Kết luận:** Tích hợp backend Java với dịch vụ thời gian thực trên Azure không chỉ là mở một WebSocket và gọi sendToAll. Một hệ thống vững chắc cần **negotiation có xác thực, client token ngắn hạn, group/user targeting đúng quyền tenant, Java SDK được quản lý credential, luồng dữ liệu sau database commit, client reconnect/resync và observability đến mức eventId**. Azure Web PubSub giúp giảm gánh nặng duy trì và fan-out WebSocket connections, nhưng không thay thế **database, Service Bus/outbox, authorization nghiệp vụ hoặc chính sách phục hồi**. Khi thiết kế đúng từ đầu và kiểm chứng bằng tests/metrics, ứng dụng realtime mới có thể mở rộng, giữ an toàn dữ liệu và kiểm soát chi phí.
