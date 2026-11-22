# Phân quyền client và quản lý group kết nối

Một ứng dụng hỗ trợ khách hàng cần cập nhật trạng thái đơn hàng theo thời gian thực. Người mua chỉ được xem thông báo của **đơn hàng thuộc tài khoản mình**; nhân viên hỗ trợ có thể tham gia một số phòng trao đổi theo phân công; quản trị viên được phép phát thông báo cho một nhóm người dùng. Nếu lập trình viên chỉ kiểm tra tên group ở phía trình duyệt, một người dùng có thể sửa JavaScript để tham gia group khác và đọc dữ liệu không được phép.

Với **Azure Web PubSub**, cách thiết kế đúng là tách ba quyết định:

1. **Client là ai?** Backend xác thực người dùng và thiết bị/phiên kết nối.
2. **Client được làm gì?** Backend cấp quyền phù hợp khi cấp client access URL/token hoặc qua API quản trị của dịch vụ.
3. **Client thuộc group nào, trong bao lâu?** Backend xét quyền theo nghiệp vụ, điều phối việc tham gia/rời group và xử lý thay đổi trong suốt vòng đời kết nối.

Ví dụ:

```text
Browser (user: buyer-1042)
        |
        | 1. HTTPS /realtime/negotiate + application login token
        v
Application Backend
  - xác thực người dùng
  - tra membership / chính sách tenant
  - chỉ cấp quyền tối thiểu
        |
        | 2. Client access URL có chữ ký, hạn sử dụng ngắn
        v
Azure Web PubSub Service
        |
        | 3. WebSocket kết nối vào hub "orders"
        |
        +--> Group "tenant-a.order-1042" (được backend cho phép)
        |
        +--X Group "tenant-b.order-9001" (không được phép)
        |
        v
Nhận thông báo của đơn 1042, không nhận dữ liệu tenant B
```

Bài học thuộc chương **Cache và giao tiếp thời gian thực**, trong module `CLOUD_PROVIDERS_AZURE`. Module giới thiệu toàn bộ hệ sinh thái Azure từ subscription, resource group và Microsoft Entra ID tới VNet, dịch vụ tính toán, lưu trữ và dữ liệu, đồng thời hướng dẫn triển khai, giám sát, bảo mật và kiểm soát chi phí kiến trúc ứng dụng. Bài này tập trung vào **Azure Web PubSub** — nơi các khái niệm **client roles, group permissions và connection management** được biểu diễn trực tiếp — đồng thời đối chiếu **Azure SignalR Service** để tránh nhầm hai mô hình. Cache như Azure Managed Redis/Redis có thể hỗ trợ lưu metadata/presence ngắn hạn nhưng **không được coi là nguồn quyết định phân quyền duy nhất**.

> Phạm vi chính: Azure Web PubSub và giao thức WebSocket client. Các API, tên thao tác, hình thức authentication, quota và tính năng như Private Endpoint phụ thuộc SDK, tier, region và phiên bản dịch vụ. Ví dụ được ghi rõ là mã có thể chạy hoặc pseudocode. Không đưa access token, connection string, key hoặc thông tin khách hàng thật vào mã học tập/logs.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **Azure Web PubSub resource**, **hub**, **connection**, **user**, **group** và **role**.
2. Mô tả quá trình xác thực ứng dụng → backend cấp client access URL/token → client mở WebSocket.
3. Giải thích hai nhóm quyền **join/leave group** và **send to group** của Azure Web PubSub client protocol.
4. Phân biệt **quyền client** với **quyền quản trị server/data plane**.
5. Thiết kế phân quyền cho multi-tenant room theo nguyên tắc **least privilege** và kiểm tra phía server.
6. Cho client tham gia/rời group qua backend hoặc giao thức client khi được cấp role.
7. Xử lý nhiều tabs/devices của cùng user, reconnect, token expiry và sự kiện disconnect.
8. Phát thông điệp tới group mà không vô tình broadcast toàn bộ hub.
9. Quản lý thay đổi quyền và thu hồi quyền khi một user bị xóa khỏi room hoặc tenant.
10. Xử lý **presence, group membership và message delivery** theo ngữ nghĩa thời gian thực, không giả định bền vững như queue.
11. So sánh Azure Web PubSub với **Azure SignalR Service**, đặc biệt quyền group và lifecycle.
12. Thiết lập HTTPS/TLS, Microsoft Entra/managed identity cho backend, metrics và runbook bảo mật.
13. Hoàn thành bài thực hành và kiểm thử cả trường hợp được phép lẫn bị từ chối.

## 2. Phạm vi dịch vụ: Web PubSub, SignalR và cache

Ba công nghệ có thể xuất hiện cạnh nhau trong một ứng dụng thời gian thực nhưng đảm nhận vai trò khác nhau:

| Công nghệ | Mục tiêu chủ yếu | Khái niệm liên quan |
|---|---|---|
| **Azure Web PubSub** | Dịch vụ managed WebSocket/PubSub cho ứng dụng real-time; có client protocol và group routing. | Hub, user ID, connection ID, group, client roles, server-side API. |
| **Azure SignalR Service** | Scale-out real-time communication cho ứng dụng dùng ASP.NET Core SignalR và mô hình SignalR tương ứng. | SignalR Hub, Hub methods, Context.User, Groups, connection lifecycle. |
| **Azure Managed Redis/Redis cache** | Lưu truy cập nhanh cho dữ liệu/cache; có thể giúp lưu một số trạng thái ngắn hạn. | Cache key, TTL, invalidation; không thay thế authorization backend. |

**Web PubSub group** không phải **SignalR group** dù cùng từ “group”. Client-side roles dạng `webpubsub.joinLeaveGroup...` là cơ chế của **Azure Web PubSub client protocol**, không tự áp dụng cho ASP.NET Core SignalR.

Redis Pub/Sub hoặc Redis cache cũng không đồng nghĩa nhóm WebSocket của Web PubSub. Dữ liệu cache có thể hỗ trợ kiểm tra nhanh nhưng quyết định user được vào phòng vẫn phải dựa trên danh tính và nguồn phân quyền đáng tin cậy.

## 3. Những khái niệm của Azure Web PubSub

| Khái niệm | Giải thích | Ví dụ |
|---|---|---|
| **Resource/service** | Tài nguyên Azure quản lý WebSocket connections, endpoint, hubs và capacity. | `wps-customer-prod` |
| **Hub** | Không gian logic tổ chức connections, groups và event handlers. | `orders` |
| **Connection ID** | Định danh một WebSocket connection cụ thể do dịch vụ quản lý. | `conn-8f2...` |
| **User ID** | Định danh logic của người dùng gắn với connection theo authentication/negotiate. | `buyer-1042` |
| **Group** | Tập connections trong một hub nhận được broadcast định tuyến theo group. | `tenant-a.order-1042` |
| **Client role/permission** | Quyền cho phép client thực hiện thao tác group theo giao thức Web PubSub. | `webpubsub.joinLeaveGroup.tenant-a.order-1042` |
| **Client access token/URL** | Thông tin cấp ngắn hạn để một client kết nối đến Web PubSub. | Signed `wss://...` URL |
| **Server SDK/REST API** | Kênh có thẩm quyền để backend quản lý connections/groups và gửi message. | Add connection to group, send to group |
| **Event handler** | Callback/upstream xử lý connect/user events theo cấu hình. | Kiểm tra user khi connect hoặc nhận client event |

**Group là đơn vị định tuyến kết nối**, không phải một bảng phân quyền do Web PubSub tự dựng từ dữ liệu khách hàng. Chính ứng dụng phải xác định group membership nào hợp lệ.

## 4. Hub, user, connection và group khác nhau thế nào?

Một người dùng có thể mở nhiều tab, điện thoại và laptop:

```text
Web PubSub resource: wps-customer-prod
└── Hub: orders
    ├── User: buyer-1042
    │   ├── Connection C1 (tab Chrome)
    │   ├── Connection C2 (điện thoại)
    │   └── Connection C3 (tab khác)
    │
    ├── Group tenant-a.order-1042
    │   ├── Connection C1
    │   └── Connection C2
    │
    └── Group tenant-a.support-team
        └── Connection S1 (nhân viên hỗ trợ)
```

Phân biệt:

- **User ID** có thể gắn với **nhiều connection IDs**.
- **Connection ID** chỉ tồn tại cho một kết nối cụ thể; không dùng làm identity bền vững.
- **Group membership** liên quan đến các connections, không mặc định đồng nghĩa “tất cả thiết bị user luôn thuộc cùng group”.
- Một connection có thể tham gia **nhiều groups** khi được cho phép và còn trong giới hạn dịch vụ.
- Cùng group name ở **hai hubs khác nhau** không phải cùng kênh phát thông báo.
- Khi connection đứt và tạo lại, ID thay đổi; ứng dụng phải có quy trình **khôi phục membership hợp lệ**.

Để gửi thông báo “chỉ cho buyer-1042”, hãy chọn user-targeting hoặc group-targeting theo đặc tính nghiệp vụ; không tự suy rằng một group dựa trên user ID sẽ tự bao gồm mọi connection hiện tại và tương lai.

## 5. Kịch bản multi-tenant: ai được vào room nào?

Giả sử hệ thống có hai tenants:

```text
Tenant A
  ├── Buyer Alice: xem order-1042
  ├── Buyer Bob: xem order-1043
  └── Support A: xem các order đang được phân công

Tenant B
  └── Buyer Carol: xem order-9001
```

Chính sách mong muốn:

| Chủ thể | Được nhận ở group | Không được nhận ở group |
|---|---|---|
| Alice (tenant A, order 1042) | `tenant-a.order-1042` | `tenant-a.order-1043` nếu không có quyền; mọi group tenant B. |
| Bob (tenant A, order 1043) | `tenant-a.order-1043` | Group của Alice nếu không được chia sẻ. |
| Support A | Các room đã được phân công và còn hiệu lực. | Room tenant B nếu không được ủy quyền liên tenant. |
| Carol (tenant B) | `tenant-b.order-9001` | Toàn bộ room tenant A. |
| Backend notification publisher | Gửi theo room có chủ đích. | Không broadcast cả hub nếu nội dung chỉ dành cho một room. |

Tuyệt đối **không** cấp quyền tham gia room dựa trên điều kiện:

```text
Client gửi roomId = "tenant-b.order-9001"
→ Backend tin luôn roomId
→ Client được vào group
```

Đúng là:

```text
Client yêu cầu roomId
→ Backend xác thực user
→ Query quyền trên dữ liệu tenant/order
→ Nếu hợp lệ, backend quyết định group name chuẩn
→ Cấp quyền/join group với phạm vi được duyệt
→ Nếu không, trả 403, không cấp quyền
```

## 6. Authentication khác authorization khác membership

Ba bước thường bị trộn lẫn:

**Authentication — bạn là ai?**

- Backend xác minh bearer token/session/cookie theo Microsoft Entra ID hoặc hệ thống identity của ứng dụng.
- Tạo một **user ID đã xác minh** dùng cho Web PubSub connection.
- Không lấy user ID từ một field do client tùy ý cung cấp rồi tin ngay.

**Authorization — bạn được làm gì?**

- Backend kiểm tra user thuộc đúng tenant, có thể xem room/order và được thực hiện hành động gửi hay chỉ nhận.
- Cấp role Web PubSub hoặc điều phối membership theo server SDK.
- Cập nhật khi phân công, role hay trạng thái đơn hàng đổi.

**Membership — bạn đang ở room nào?**

- Backend/client thực hiện join theo cơ chế được phép.
- Service định tuyến group messages tới những connections đang là thành viên.
- Membership có vòng đời gắn với trạng thái connection và điều khiển server.

**Đã đăng nhập** không có nghĩa **được tham gia mọi group**. **Đã ở group** không có nghĩa **được phép gửi lên group**. **Được cấp quyền gửi** không có nghĩa người dùng có quyền đổi dữ liệu nghiệp vụ trong SQL/Cosmos DB.

## 7. Control plane, server data plane và client protocol

Cần chia quyền theo nơi thực thi.

```text
Azure Administrator (control plane)
  - tạo Web PubSub resource
  - cấu hình network, hub/event handlers, roles
                |
                v
Application Backend (server data plane)
  - cấp client access URL
  - add/remove connection/user vào group
  - gửi message tới group/user/connection
  - close/revoke khi tính năng hỗ trợ
                |
                v
Browser/Mobile (client protocol)
  - kết nối WebSocket bằng URL được cấp
  - nhận messages
  - join/leave và sendToGroup khi có client role phù hợp
```

| Quyền | Ai cần | Không nên cấp cho |
|---|---|---|
| Azure Resource Manager quản trị resource | Đội hạ tầng/automation theo RBAC. | Trình duyệt và mobile client. |
| Web PubSub server-side data-plane access | Backend có managed identity/service identity được phê duyệt. | Client không tin cậy. |
| Client access URL/role có phạm vi | Người dùng đã được backend xác thực. | Người dùng chưa xác thực hoặc user của tenant khác. |
| Business authorization | Backend/API và nơi dữ liệu nguồn. | Không giao duy nhất cho mã JavaScript client. |

**Không đưa Web PubSub connection string hoặc service access key vào web/mobile app.** Service key cho phép thao tác vượt xa quyền cần thiết của một client cuối.

## 8. Luồng negotiate cấp URL kết nối

Ứng dụng thường dùng endpoint **negotiate** trong backend:

```text
1. Browser -- HTTPS GET /api/realtime/negotiate
   Authorization: Bearer <application access token>
                 |
                 v
2. Backend xác thực token, tenant và role
                 |
                 v
3. Backend tạo client access URI:
   - hub được chọn
   - userId đáng tin cậy
   - roles tối thiểu
   - expiry ngắn
                 |
                 v
4. Backend trả URL có chữ ký bằng HTTPS, no-store
                 |
                 v
5. Browser mở WebSocket (wss://)
                 |
                 v
6. Web PubSub xác thực token và tạo connection
```

Điều kiện bảo mật:

1. API negotiate phải **yêu cầu authentication**; không chỉ nhận `?userId=...` rồi cấp URL.
2. Không để client chọn tùy ý roles hoặc scopes.
3. Chỉ cấp role cần cho room đã được **backend kiểm tra**.
4. URL phải sống ngắn và được coi là **secret**.
5. Response chứa URL phải có chính sách không cache qua intermediary khi phù hợp.
6. Không ghi toàn URL vào access logs, frontend analytics hoặc exception traces.
7. Kết nối sử dụng **WSS/TLS**, không phải WS không mã hóa.
8. Server có thể buộc client re-negotiate khi reconnect để kiểm tra lại quyền.

## 9. Client access URL/token không phải tài khoản quản trị

Client access URL thường chứa token có chữ ký, gắn hub/user/roles và hạn dùng theo cách dịch vụ cung cấp. Nó cho phép **thiết lập WebSocket** và những thao tác client được ủy quyền.

Các lỗi thiết kế:

- Copy token của người dùng A để kiểm thử user B.
- Cấp URL hợp lệ một ngày dù user có thể bị xóa khỏi room trong vài phút.
- Đặt user ID bằng giá trị client tự khai báo.
- Dùng một token chung cho toàn bộ khách của một tenant.
- Trả về service connection string thay vì client URL.
- Lưu token trong localStorage lâu dài để “đỡ negotiate”.
- In đầy đủ token vào logs để debug.

Token bị lộ có thể bị người khác sử dụng tới khi hết hạn hoặc bị vô hiệu bằng cơ chế được hỗ trợ. Do vậy **expiry ngắn, TLS, client authentication và cơ chế thu hồi khi quyền thay đổi** đều quan trọng.

### Hết hạn token có ngắt WebSocket đang hoạt động ngay?

Không nên coi access token expiry đồng nghĩa mọi connection hiện tại sẽ tự bị đóng đúng giây đó. Expiry chủ yếu ràng buộc việc sử dụng token theo semantics dịch vụ, đặc biệt khi tạo/reconnect connection. **Muốn cắt quyền một user đang online**, phải có quy trình server-side revoke/remove group/close connection phù hợp và kiểm chứng.

## 10. Quyền client trong Web PubSub: hai nhóm cơ bản

Với **Azure Web PubSub client protocol**, các roles thường gặp:

| Role pattern | Khả năng | Phạm vi |
|---|---|---|
| `webpubsub.joinLeaveGroup` | Cho phép client tham gia/rời các groups theo phạm vi rộng. | Rộng trên các groups trong hub. |
| `webpubsub.joinLeaveGroup.<group>` | Cho phép client join/leave group cụ thể. | Một group xác định. |
| `webpubsub.sendToGroup` | Cho phép client gửi message tới groups theo phạm vi rộng. | Rộng trên các groups trong hub. |
| `webpubsub.sendToGroup.<group>` | Cho phép client gửi tới group cụ thể. | Một group xác định. |

Thay `<group>` bằng **tên group thật** do backend kiểm tra, không phải biểu thức wildcard tùy ý do client truyền.

**Ví dụ vai trò:**

```text
Viewer của order-1042:
  webpubsub.joinLeaveGroup.tenant-a.order-1042
  (không có sendToGroup)

Agent được chat ở order-1042:
  webpubsub.joinLeaveGroup.tenant-a.order-1042
  webpubsub.sendToGroup.tenant-a.order-1042

Server publisher:
  dùng server SDK/data-plane permission,
  KHÔNG cần cấp vai trò client toàn quyền
```

### Role không thay thế business authorization

Ngay cả khi client có `sendToGroup`, điều đó không chứng minh nội dung message không độc hại hay user được phép **thay đổi trạng thái đơn hàng**. Nếu message mang lệnh nghiệp vụ, backend cần xác thực và kiểm tra lại tại handler/API trước khi thực thi.

## 11. Quyền join/leave khác quyền send

Một room thông báo trạng thái đơn hàng thường chỉ cần cho người mua **nhận thông báo**.

- Khi backend **thêm connection vào group**, client có thể nhận group messages nhờ membership hiện hành, không nhất thiết cần tự có quyền join.
- Nếu client được phép tự gửi yêu cầu `joinGroup` bằng client protocol, cần role **joinLeaveGroup** phù hợp.
- Nếu client được phép tự gửi `sendToGroup`, cần role **sendToGroup** phù hợp.
- Nếu client chỉ nên nhận status updates từ backend, **không cấp sendToGroup**.

Những nhầm lẫn thường gặp:

| Nhận định | Đúng hay sai? | Giải thích |
|---|---|---|
| “Ở trong group thì có quyền gửi group message.” | Sai. | Membership và send permission là hai việc khác. |
| “Có sendToGroup thì tự động tham gia group.” | Sai. | Send authorization không mặc nhiên thêm membership. |
| “Client cần sendToGroup để nhận server broadcast.” | Sai. | Nhận group messages dựa trên membership/routing. |
| “Client biết tên group thì join được.” | Sai. | Cần role hoặc server operation được ủy quyền. |
| “Server dùng SDK quản trị phải xin role client.” | Sai. | Server operation và client role là hai kênh quyền khác. |

## 12. Thiết kế mặc định an toàn: server-controlled membership

Đối với dữ liệu multi-tenant nhạy cảm, cách dễ kiểm soát là **không cấp quyền tự join bất kỳ group nào**. Client xác thực với backend, backend quyết định join sau khi kiểm tra.

```text
Client kết nối WebSocket, có user ID đáng tin cậy
           |
           v
Client → HTTPS POST /api/rooms/1042/join
           |
           v
Backend kiểm tra:
  - user login hợp lệ?
  - thuộc tenant A?
  - có quyền xem Order 1042?
  - connectionId thuộc user đang gọi?
           |
           +-- Không → 403, không add
           |
           +-- Có
                 |
                 v
      Server SDK AddConnectionToGroup
                 |
                 v
      Client nhận event ở group được cấp
```

Ưu điểm:

- Backend giữ quyền kiểm soát **join, leave, audit**.
- Client không tự chọn room ngoài tập được kiểm tra.
- Có thể không cấp role `joinLeaveGroup` cho viewer.
- Quyết định join gắn với tình trạng room/tenant hiện thời.
- Dễ tích hợp rate limiting và business logging.

Đánh đổi:

- Một API call/server operation mỗi lần join hoặc leave, tùy thiết kế.
- Phải bảo vệ connectionId không bị giả mạo.
- Cần xử lý race giữa join và disconnect.
- Mỗi reconnect là connection mới, phải xác minh lại membership.

Không xem connectionId do client cung cấp là bằng chứng sở hữu. Backend nên ánh xạ connection tới authenticated user bằng thông tin có thể xác minh từ dịch vụ/event callback, hoặc dùng user-level API với semantics được kiểm tra.

## 13. Thiết kế client-controlled: scoped roles và ràng buộc nghiệp vụ

Có những ứng dụng chat tương tác cao muốn client tự join/leave room sau khi được backend cho phép. Khi đó backend cấp **role theo group cụ thể**, thay vì cấp toàn quyền trên hub.

```text
Negotiate:
  user = agent-71
  allowed room = tenant-a.order-1042

Issued role:
  webpubsub.joinLeaveGroup.tenant-a.order-1042

Client:
  joinGroup("tenant-a.order-1042") → được phép
  joinGroup("tenant-b.order-9001") → bị từ chối
```

**Lưu ý chính tả:** đây là minh họa một quyết định negotiate; tên endpoint do ứng dụng tự đặt. Role phải do backend đưa vào token/authorization theo API thực tế.

Hạn chế cần xử lý:

- Sau khi quyền nghiệp vụ bị thu hồi, token có thể còn hiệu lực; server cần **remove membership/revoke/close** khi cần.
- Group name được client nhìn thấy không phải secret; đừng dựa vào sự “khó đoán” để bảo vệ.
- Nếu chat message thực hiện thay đổi dữ liệu, server handler vẫn kiểm tra business authorization.
- Token cấp roles cho nhiều rooms sẽ phình scope và phức tạp khi quyền thay đổi.
- Khi có thay đổi membership liên tục, server-controlled join thường dễ bảo đảm chính sách hơn.

### Viewer có cần quyền join không?

Không bắt buộc. Viewer chỉ nhận thông báo có thể do backend add connection trực tiếp. Chọn cách nào phụ thuộc trải nghiệm, tốc độ thay đổi quyền và rủi ro an toàn dữ liệu.

## 14. Bảng phân quyền theo vai trò nghiệp vụ

Ví dụ hệ thống order support:

| Vai trò nghiệp vụ | Tham gia group | Gửi group message | Thay đổi Order |
|---|---|---|---|
| Buyer | Chỉ room của Order mình sở hữu. | Mặc định không; nếu chat, giới hạn room và lọc message. | Thông qua API nghiệp vụ được xác thực. |
| Support agent | Room được phân công, trong thời hạn phân công. | Chỉ room được phép chat. | Chỉ qua API và authorization nghiệp vụ. |
| Supervisor | Room theo khu vực/nhóm được quản lý. | Gửi thông báo theo chính sách. | Theo quyền backend độc lập. |
| Operator/monitor | Group observability riêng hoặc server-targeted feed. | Không cần quyền client gửi. | Không. |
| Backend publisher | Dùng service SDK để gửi đến group được chọn. | Có qua server data plane. | Theo service identity và business policy. |
| Unknown/unauthed user | Không group nhạy cảm. | Không. | Không. |

Không gộp **application RBAC** với **Azure RBAC**:

- Azure RBAC điều khiển ai tạo/cấu hình Web PubSub resource và backend server data-plane operations.
- Application RBAC/ABAC kiểm tra người dùng được vào room nào.
- Client roles Web PubSub giới hạn thao tác WebSocket cụ thể đã được cấp cho connection.

Cả ba cần tương thích, nhưng không thay thế nhau.

## 15. Backend cấp client access URI: ví dụ .NET

Ví dụ khái niệm bằng **Azure.Messaging.WebPubSub** và **Azure.Identity**. Backend xác thực caller qua middleware và **tự xác định** user ID/group hợp lệ; không lấy danh sách roles không kiểm soát từ request.

```csharp
using Azure.Identity;
using Azure.Messaging.WebPubSub;

// Mã backend minh họa: endpoint, hub và principal đã được kiểm tra.
var endpoint = new Uri("https://wps-customer-lab.webpubsub.azure.com");
string hubName = "orders";
string userId = "buyer-1042";
string groupName = "tenant-a.order-1042";

// Backend/service identity cần được cấp quyền data-plane phù hợp.
var client = new WebPubSubServiceClient(
    endpoint,
    hubName,
    new DefaultAzureCredential());

// Chỉ cho client tự join/leave room đã được phép.
// Không cấp sendToGroup nếu đây là viewer chỉ đọc.
Uri accessUri = client.GetClientAccessUri(
    userId: userId,
    roles: new[] { "webpubsub.joinLeaveGroup." + groupName },
    expiresAfter: TimeSpan.FromMinutes(5));

// Trả accessUri.AbsoluteUri cho caller đã xác thực bằng HTTPS.
// Không ghi URL/token vào logs, không lưu vào source code.
```

**Điều kiện chạy thực tế:**

1. Project backend có SDK/version hỗ trợ constructor và `GetClientAccessUri` tương ứng.
2. Endpoint/hub tồn tại trong resource lab.
3. Principal của backend được cấp quyền quản lý/generate access URI phù hợp với cách authentication của SDK.
4. Backend đã kiểm tra **buyer-1042 thật sự được xem order-1042**.
5. HTTPS negotiate response được bảo vệ, không cache/public log.
6. Client dùng URL có chữ ký để tạo WebSocket **trước khi hết thời hạn**.

Nếu SDK/version khác thay đổi overload, dùng API tương đương được công bố, **không chuyển sang hard-code service key vào trình duyệt**. Đoạn mã chỉ biểu diễn luồng cấp quyền, không phải một API endpoint hoàn chỉnh có middleware authentication.

## 16. Pseudocode endpoint negotiate an toàn

Bước kiểm tra quyền thường quan trọng hơn lời gọi SDK.

```text
GET /api/realtime/negotiate?orderId=ORD-1042

principal = VerifyApplicationAccessToken(request)
if principal is missing:
    return 401

tenantId = principal.tenantId
userId = principal.stableUserId
orderId = NormalizeAndValidate(request.orderId)

order = OrdersRepository.GetByTenantAndId(tenantId, orderId)
if order does not exist:
    return 404 or permitted non-disclosing response

if not Authorization.CanViewOrder(principal, order):
    return 403 or permitted non-disclosing response

group = CanonicalGroupName(tenantId, orderId)
roles = ["webpubsub.joinLeaveGroup." + group]  # nếu cho tự join
signedUrl = WebPubSubService.GenerateClientAccessUrl(
    hub="orders",
    userId=userId,
    roles=roles,
    expiresIn=5minutes
)

return HTTPS 200 with:
    url = signedUrl
    group = group
    expiresInSeconds = 300
Cache-Control: no-store
```

**Pseudocode, không phải chương trình deploy trực tiếp.** Bổ sung rate limiting, audit, validate request, error handling và cơ chế CSRF nếu ứng dụng dùng cookie authentication. Không tin `tenantId`, `userId` hoặc `roles` từ body/query string client.

### Tránh lộ sự tồn tại của room

Ở hệ thống nhạy cảm, response 403 vs 404 có thể tiết lộ order ID có tồn tại. Hãy chọn chiến lược lỗi nhất quán, không trả chi tiết quyền nội bộ cho caller không có quyền.

## 17. WebSocket client: kết nối và nhận group messages

Ví dụ trình duyệt sử dụng **Web PubSub JSON subprotocol**. Token URL được backend cấp sau khi xác thực.

```javascript
// Giả định endpoint /api/realtime/negotiate đã được bảo vệ.
// Không in token URL vào console/log.
const response = await fetch("/api/realtime/negotiate?orderId=ORD-1042", {
  credentials: "include",
  cache: "no-store"
});

if (!response.ok) {
  throw new Error("Không được phép thiết lập kết nối realtime");
}

const { url, group } = await response.json();

// Azure Web PubSub client protocol với JSON messages.
const socket = new WebSocket(url, "json.webpubsub.azure.v1");
let nextAckId = 1;

socket.addEventListener("open", () => {
  socket.send(JSON.stringify({
    type: "joinGroup",
    group: group,
    ackId: nextAckId++
  }));
});

socket.addEventListener("message", (event) => {
  const frame = JSON.parse(event.data);

  if (frame.type === "message") {
    // Đây chỉ là payload nhận được.
    // Render an toàn: tránh chèn HTML không tin cậy.
    renderNotificationAsText(frame.data);
  } else if (frame.type === "ack") {
    handleAcknowledgement(frame);
  }
});

socket.addEventListener("close", () => {
  // Dừng gửi, bật cơ chế reconnect có backoff và re-negotiate.
  scheduleAuthenticatedReconnect();
});
```

**Các hàm** `renderNotificationAsText`, `handleAcknowledgement` và `scheduleAuthenticatedReconnect` là tên minh họa, phải được hiện thực bởi ứng dụng. Đoạn mã cho thấy cấu trúc kết nối, **không hoàn chỉnh để copy chạy** nếu chưa khai báo các hàm đó.

### Không dùng JavaScript client làm điểm kiểm tra quyền cuối

Mã JavaScript có thể bị người dùng sửa trong DevTools. Vì thế server phải quyết định role và group nào được phép; việc ẩn nút “Join tenant B” không tạo bảo mật.

## 18. Client protocol: joinGroup, leaveGroup, sendToGroup

Các thông điệp JSON minh họa theo kiểu client protocol:

**Join group** — cần `joinLeaveGroup` permission khi client tự gọi:

```json
{
  "type": "joinGroup",
  "group": "tenant-a.order-1042",
  "ackId": 1
}
```

**Leave group**:

```json
{
  "type": "leaveGroup",
  "group": "tenant-a.order-1042",
  "ackId": 2
}
```

**Gửi group message** — chỉ cho client được cấp quyền `sendToGroup` tương ứng:

```json
{
  "type": "sendToGroup",
  "group": "tenant-a.order-1042",
  "dataType": "json",
  "data": {
    "kind": "ChatMessage",
    "text": "Tôi cần hỗ trợ đơn hàng này"
  },
  "ackId": 3
}
```

### Vai trò của ackId

`ackId` cho phép client ghép **acknowledgement từ dịch vụ** với thao tác gửi/join/leave. Nhưng một ACK thành công của service **không** có nghĩa:

- Mọi client trong group đều online.
- Mọi thiết bị đã nhận và hiển thị nội dung.
- Tin nhắn đã được lưu bền vững trong database.
- Nhân viên hỗ trợ đã đọc hoặc xử lý yêu cầu.
- Lệnh nghiệp vụ trong payload đã được phép và đã commit.

Muốn xác nhận “đã đọc” hoặc “đã xử lý”, xây cơ chế **application-level acknowledgements/read receipts** và lưu trữ trạng thái riêng.

## 19. Xử lý ACK và từ chối quyền trên client

Client nên quản lý pending commands bằng ackId:

```text
Pending:
  ackId=10 → join tenant-a.order-1042
  ackId=11 → send message to room
  ackId=12 → leave room

Khi nhận ACK:
  - ghép ackId
  - kiểm tra success/error fields theo protocol version
  - cập nhật trạng thái UI
  - nếu permission denied: không retry mù
  - nếu reconnect: xin URL mới và đồng bộ membership
```

Những lỗi cần phân biệt:

- **Permission denied:** user chưa được cấp role hoặc quyền đã bị thu hồi.
- **Invalid group name/protocol:** payload/cú pháp không hợp lệ.
- **Connection closed:** token, mạng, server operation hoặc lifecycle.
- **Transient network error:** có thể cần reconnect/backoff.
- **Join acknowledged nhưng chưa thấy message:** chưa có publisher, group chưa có dữ liệu, backend gửi nhầm hub/group hoặc thời điểm join sau khi message được phát.

Không dùng retry liên tục với cùng group trái phép để “đợi đến khi được cấp quyền”. Mỗi lần thay đổi quyền phải thông qua backend và quy trình nghiệp vụ.

## 20. Server-managed groups qua SDK/REST

Backend được cấp quyền data plane có thể quản lý membership mà không cho client tự join:

```text
Authorized API request
   |
   v
Validate user + tenant + room + connection ownership
   |
   +-- AddConnectionToGroup(group, connectionId)
   |
   +-- RemoveConnectionFromGroup(group, connectionId)
   |
   +-- SendToGroup(group, payload)
   |
   +-- CloseConnection(connectionId) khi cần
```

Đây là **tên thao tác khái niệm**, không phải chữ ký phương thức cố định trên mọi phiên bản SDK. Một số SDK cũng cung cấp thao tác **theo user** chứ không chỉ connection; cần xác minh semantics khi user có nhiều thiết bị/connection.

### Mã C# dạng pseudocode có chủ đích

```csharp
// PSEUDOCODE: tên hàm và đối số phải đối chiếu SDK version.
async Task ApproveAndJoinAsync(
    Principal actor, string connectionId, string roomId)
{
    var room = await rooms.LoadAsync(actor.TenantId, roomId);

    if (!policy.CanRead(actor, room))
        throw new ForbiddenException();

    if (!await connections.BelongsToUserAsync(connectionId, actor.UserId))
        throw new ForbiddenException();

    string group = CanonicalGroup(actor.TenantId, room.Id);

    await webPubSubAdmin.AddConnectionToGroupAsync(
        group, connectionId);
}
```

Hàm `connections.BelongsToUserAsync` rất quan trọng. Nếu client có thể truyền một connectionId của người khác, backend có thể vô tình thêm **connection của nạn nhân** vào group sai.

## 21. Tại sao group name phải chuẩn hóa và có tenant scope?

Những tên như `room-1042` thường **không đủ an toàn** trong multi-tenant app vì tenant A và tenant B có thể cùng có một order ID.

Ví dụ canonical naming:

```text
tenant-a.order-1042
tenant-a.order-1043
tenant-b.order-1042
```

Nhưng tên canonical **không tự cấp quyền**. Backend phải xác thực và kiểm tra:

1. Tenant ID lấy từ danh tính đã xác minh, không từ chuỗi user tự nhập.
2. Order/room thuộc tenant đó.
3. User được quyền xem/gửi tại thời điểm thao tác.
4. Group name được xây từ các thành phần chuẩn, được encode/validate theo giới hạn dịch vụ.
5. Không cho các chuỗi đặc biệt, tên rỗng, delimiter hoặc Unicode normalization làm hai room trùng tên ngoài ý muốn.
6. Có version/prefix khi schema group naming thay đổi.
7. Backend và producer dùng cùng naming function, không copy logic khác nhau ở nhiều dịch vụ.

### Khi group name chứa dữ liệu nhạy cảm

Group name có thể xuất hiện trong diagnostics/URLs/logs. Tránh đưa email, số điện thoại, access token hoặc nội dung chăm sóc khách hàng vào group name. Có thể dùng ID giả danh (opaque ID) kết hợp bảng ánh xạ được bảo vệ.

## 22. User-level vs connection-level group operations

Hai kiểu thao tác có mục đích khác nhau:

**Connection-level:** nhắm tới một WebSocket connection cụ thể.

- Phù hợp khi một tab chỉ xem Order A nhưng tab khác của cùng user đang xem Order B.
- Dễ kiểm soát UI/session-level membership.
- Sau reconnect, connection ID cũ không còn dùng được.
- Phải kiểm tra quyền sở hữu connection ID.

**User-level:** nhắm tới user ID logic, có thể ảnh hưởng nhiều connections theo semantics API.

- Phù hợp với broadcast thông báo cho mọi thiết bị của user.
- Cần hiểu liệu SDK/API thao tác lên những connections hiện tại hay có behavior bổ sung đối với connections mới, theo tính năng thực.
- Khi một user đăng nhập trên hai tenants/contexts, không nên nhầm user ID toàn cục với tenant-scoped policy.
- Cần xác định logout/ban/role change áp dụng **mọi thiết bị** hay một session.

**Quy tắc:** tài liệu runbook phải ghi rõ “remove connection C1 from group” hay “remove user U across active connections” và hậu quả đối với các tabs; không chỉ ghi “remove khỏi room”.

## 23. Một user có nhiều tab và nhiều thiết bị

Giả sử buyer-1042 có ba kết nối:

```text
C1 — Chrome, xem order-1042
C2 — Safari, xem order-1042
C3 — Mobile, xem dashboard tổng
```

Các lựa chọn:

- **Theo connection:** thêm C1 và C2 vào group đơn hàng, C3 không cần.
- **Theo user:** server gửi một thông báo tổng quát đến tất cả connections của buyer-1042, nếu API/phương án đáp ứng.
- **Theo app session:** lưu session ID/connection mapping đáng tin cậy để thu hồi một thiết bị cụ thể.

### Race condition thực tế

1. Browser C1 gửi yêu cầu join.
2. C1 mất mạng, Web PubSub đóng connection.
3. Backend kiểm tra quyền xong và cố add C1 vào group.
4. Operation có thể báo connection không còn tồn tại hoặc thay đổi vì lifecycle.

Hướng xử lý: coi disconnect/not-found là tình huống bình thường, log ở mức phù hợp, không tự lấy connection khác của user để join mà chưa xác minh nhu cầu. Client reconnect → negotiate lại → join theo connection mới.

## 24. Reconnect: connection mới không giữ mọi trạng thái cũ

WebSocket không phải kênh luôn sống. Thiết bị có thể chuyển từ Wi-Fi sang 4G, trình duyệt ngủ, service scale hoặc server chủ động close connection.

```text
Connected C1, thuộc group G
        |
        v
Network disconnected
        |
        v
C1 closed / membership tied to C1 kết thúc
        |
        v
Client re-negotiate
        |
        v
Connected C2 (ID mới)
        |
        v
Backend kiểm tra quyền mới
        |
        v
Join group G (nếu vẫn được phép)
```

Cần:

1. **Exponential backoff/jitter** cho reconnect.
2. Lấy **client URL mới** nếu URL cũ hết hạn.
3. Xác thực và kiểm tra authorization **một lần nữa**.
4. Tái thiết lập các memberships cần thiết; không giả định session trước vẫn nguyên vẹn.
5. Chỉ báo “đã tham gia room” khi có xác nhận phù hợp.
6. Có một API lấy state hiện tại sau reconnect, vì các realtime messages trong thời gian offline có thể mất.
7. Dừng/thu hồi listeners cũ, tránh nhiều WebSockets trùng cho một UI.

Một số client SDK/protocol cung cấp tính năng khôi phục/reliable delivery giới hạn; không mặc định nó tạo message history bền vững hoặc miễn nhu cầu đồng bộ state sau offline.

## 25. Thu hồi quyền khi user rời room hoặc bị khóa

**Tình huống:** Support agent bị rút khỏi đơn hàng lúc 10:00 nhưng WebSocket đang kết nối.

Chỉ cập nhật database từ `assigned=true` sang `false` **không đủ** nếu connection vẫn thuộc group và tiếp tục nhận messages. Hệ thống cần một **authorization revocation workflow**.

```text
Supervisor removes agent from order
          |
          v
DB transaction: revoke assignment
          |
          v
Authorization/revocation event
          |
          +-- invalidate cached permissions
          +-- revoke ability to join/send when API supports
          +-- remove active connection/user from group
          +-- optionally close affected connections
          |
          v
Verify no further sensitive group delivery
```

### Thứ tự hành động quan trọng

- Nếu client còn role `joinLeaveGroup.G`, chỉ remove membership có thể không đủ: client có thể tự join lại. Cần **thu hồi quyền hoặc đóng connection**, tùy service API và mức độ rủi ro.
- Access URL đã cấp có thể còn hạn; dùng expiry ngắn và phản ứng chủ động cho thay đổi quyền.
- Cache permissions phải được invalidated hoặc có TTL/quy trình cập nhật.
- Một message đã ở trên đường truyền ngay trước thu hồi vẫn có thể tới client; **không thể thu hồi thông tin đã nhận**. Đây là giới hạn cần đưa vào threat model.
- Xác minh trạng thái trên **mọi connections cần bị ảnh hưởng**, không chỉ tab hiện tại.

### Cách đo thành công

Không chỉ kiểm tra backend trả HTTP 200. Dùng một client test: sau revocation, thử join/send lại và phát thông điệp thử không nhạy cảm vào group; client bị thu hồi không được nhận khi policy đã có hiệu lực.

## 26. Event handlers: connect, connected, disconnected và user events

Azure Web PubSub cho phép cấu hình **event handlers/upstream** cho những sự kiện liên quan tới kết nối và thông điệp theo hỗ trợ.

Các nhóm sự kiện thường gặp:

- **Connect:** thời điểm thiết lập kết nối, có thể tham gia quyết định cho phép kết nối và ngữ cảnh user/roles/groups theo mô hình handler được hỗ trợ.
- **Connected:** thông báo kết nối đã được thiết lập.
- **Disconnected:** thông báo connection kết thúc.
- **User events:** những events mà client gửi tới backend qua service theo cấu hình protocol/event handler.

### Tại sao handler cần security?

- Webhook/upstream nhận request từ dịch vụ, phải xác minh nguồn và phương thức authentication được cung cấp/hỗ trợ.
- Event handler URL không được mở như một API ẩn danh tin bất kỳ payload tùy ý.
- Nếu connect handler trả roles/groups, phải lấy quyết định từ **policy đáng tin cậy**, không từ chuỗi client kiểm soát.
- Handler phải chịu được retry/duplicate/out-of-order event notifications theo semantics dịch vụ.
- Tránh thực hiện giao dịch database lâu trong synchronous connect decision.
- Disconnected event có thể tới muộn hoặc không phải thời điểm authoritative duy nhất cho presence; có cơ chế cleanup/TTL/reconciliation.

Không đồng nhất **“đã connect thành công”** với **“đã vào một group”**. Membership phải được cấp/chấp nhận theo luồng cụ thể.

## 27. Backend gửi message đến group

Ví dụ hệ thống nhận sự kiện trạng thái từ Order worker:

```json
{
  "eventType": "OrderStatusChanged",
  "orderId": "ORD-1042",
  "status": "Shipped",
  "eventId": "evt-1042-shipped-1",
  "occurredAtUtc": "2026-11-20T09:00:00Z"
}
```

Backend:

1. Xác minh event từ nguồn được ủy quyền.
2. Xác định tenant/order từ record đáng tin cậy, **không tin group name trong event body**.
3. Xây group `tenant-a.order-1042`.
4. Gọi Web PubSub **server SDK send-to-group** với payload đã làm sạch.
5. Quan sát kết quả API/latency và ghi correlation/event ID.
6. Nếu cần lưu message history, ghi vào database hoặc event store **trước hoặc theo workflow outbox**.
7. Nếu user offline, khi reconnect frontend gọi API lấy trạng thái hiện tại.

### Pseudocode

```text
onOrderStatusChanged(event):
    order = trustedRepository.get(event.orderId, event.tenantId)
    if order is null:
        raise or quarantine

    group = canonicalGroup(order.tenantId, order.id)
    payload = {
        eventType: "OrderStatusChanged",
        orderId: order.id,
        status: order.currentStatus,
        eventId: event.eventId
    }

    webPubSubServer.sendToGroup(hub="orders", group, payload)
    metrics.increment("realtime_publish_attempt")
```

**Send-to-group succeeded** không có nghĩa mọi client đã nhận hoặc người dùng đọc thông báo. Nếu nghiệp vụ cần bằng chứng, phải có application-level ack, persistent message store hoặc trạng thái đọc riêng.

## 28. Không broadcast rộng hơn cần thiết

Phân biệt các phạm vi định tuyến:

| Mục tiêu | Thao tác phù hợp | Rủi ro nếu chọn sai |
|---|---|---|
| Một connection cụ thể | Send to connection. | Nhầm connection của user khác. |
| Mọi connections của một user | Send to user, khi phù hợp. | Gửi sang thiết bị không nên xem thông tin theo session. |
| Những connections đã join một room | Send to group. | Sai group name → lộ dữ liệu liên tenant. |
| Tất cả connections trong hub | Broadcast to hub/all. | **Rất nguy hiểm** với thông tin đơn hàng riêng tư. |

Nếu payload chứa PII hoặc chi tiết đơn hàng, **không sử dụng toàn hub broadcast làm fallback** khi group lookup thất bại. Khi không xác định được group chính xác, nên dừng gửi, cảnh báo và đối soát.

### Tách event notification khỏi dữ liệu nhạy cảm

Một thiết kế có thể gửi thông báo nhỏ như:

```json
{
  "kind": "OrderChanged",
  "orderId": "ORD-1042",
  "version": 12
}
```

Frontend sau đó gọi API HTTPS có authorization để lấy dữ liệu chi tiết. Cách này giảm dữ liệu nhạy cảm đi qua realtime channel, nhưng phải cân nhắc tần suất API calls, caching và consistency.

## 29. Validation nội dung client gửi: chống XSS và command injection

Nếu có chat hoặc client-to-group send:

- Kiểm tra **kích thước, kiểu dữ liệu, content type, schema và encoding**.
- Giới hạn text length và attachments metadata.
- Không render text bằng `innerHTML` mà không sanitize.
- Không cho message client tự gắn nhãn “system”, “admin” hay “paid” rồi backend tin.
- Không chứa SQL query, command hay service credentials trong client messages.
- Áp dụng rate limit/anti-spam theo user/IP/tenant.
- Gắn `senderUserId` từ **identity đã xác minh**, không từ payload.
- Nếu event cần moderation/audit, cân nhắc **client gửi vào backend event handler** để validate trước khi server phát lại thay vì mở direct send rộng.
- Thiết kế chống CSRF/CORS ở negotiate/backend API theo phương thức authentication thực tế.

**Quyền sendToGroup chỉ kiểm tra phạm vi gửi**, không tự kiểm tra nội dung chat hợp lệ hoặc an toàn cho mọi recipient.

## 30. Group message có bảo đảm lưu lại khi user offline không?

**Không coi Azure Web PubSub group như message queue bền vững.**

```text
10:00  Server send "Order shipped" to group G
10:00  Browser A online, thuộc G → có thể nhận
10:00  Browser B offline         → không mặc định có message để replay
10:03  Browser B reconnect       → cần gọi API lấy trạng thái hiện tại
```

Nếu business yêu cầu **không bỏ lỡ thông báo**, dùng kiến trúc kết hợp:

```text
Order event
   |
   +-- Lưu trạng thái/notification record bền vững
   |       |
   |       +-- API GET /notifications?since=cursor
   |
   +-- Publish realtime hint qua Web PubSub
           |
           v
       Client update UI
           |
           +-- Sau reconnect lấy lại missed state/events
```

Cần message IDs, cursor/sequence, idempotency và retention phía ứng dụng. WebSocket là kênh **delivery gần thời gian thực**, không phải bằng chứng lưu trữ cuối cùng.

## 31. Ordering, duplicate và acknowledgement

Ứng dụng có thể gặp:

- Message đến trễ do network.
- Client reconnect và đồng thời gọi API refresh state.
- Worker gửi lại notification với cùng event ID.
- Hai publishers cập nhật trạng thái gần đồng thời.
- Message real-time tới UI trước khi API đọc thấy dữ liệu mới, tùy consistency/replication.
- ACK ở mức Web PubSub protocol có được, nhưng UI chưa render hoặc người dùng chưa đọc.

### Thiết kế chống lỗi

1. Mỗi event có `eventId` duy nhất theo nguồn nghiệp vụ.
2. Record/entity có **version** tăng dần hoặc commit marker phù hợp.
3. Client bỏ qua event cũ hơn version đã áp dụng.
4. Khi phát hiện lỗ hổng version, gọi API lấy authoritative state.
5. Dedupe theo eventId trong khoảng cần thiết.
6. Không dùng thời gian nhận WebSocket làm chứng cứ thứ tự nghiệp vụ tuyệt đối.
7. Không coi một group trên nhiều connections như một total-order transaction log.

**Ví dụ:** client đã render Order version 12; nhận version 11 muộn thì không được đưa trạng thái trở lại version 11.

## 32. Presence và group membership: trạng thái không tuyệt đối

Ứng dụng muốn hiển thị “3 người đang online trong phòng”. Nhưng số kết nối không bằng số người:

```text
Buyer A:
  2 tabs WebSocket → 2 connections, 1 user

Agent B:
  1 desktop app → 1 connection, 1 user
```

Một group có 3 connections nhưng chỉ 2 users. Thêm nữa, mạng mất có thể tạo độ trễ giữa disconnect thực tế và event cleanup.

### Các mô hình presence

| Mô hình | Có thể đo | Cần thận trọng |
|---|---|---|
| Service-level connection status | Một connection/user có online theo API có hỗ trợ. | Độ trễ cập nhật và timeout. |
| Application in-memory/cache map | Danh sách connection IDs/user/group tạm thời. | Crash, multi-instance, TTL và rò trạng thái. |
| Redis cache có TTL | Fast lookup cho presence gần thực. | Cache không authoritative, cần expiry/refresh/reconciliation. |
| Database membership | User **được phép** thuộc room. | Không đồng nghĩa user đang online. |
| Audit events | Ai join/leave khi nào. | Event có thể trễ/lặp, cần timestamps/IDs. |

Đừng biến một heartbeat/presence cache thành chứng cứ phân quyền; khi phát lệnh nhạy cảm phải kiểm tra business policy đáng tin cậy.

## 33. Cache quyền: tăng tốc nhưng phải có invalidation

Nếu mỗi WebSocket join cần đọc database, backend có thể cache kết quả `CanViewRoom(userId, roomId)` theo TTL. Nhưng cache permission nguy hiểm nếu không xử lý thu hồi.

Ví dụ:

```text
10:00  Agent có quyền xem room R → cache ALLOW 15 phút
10:01  Supervisor thu hồi quyền trong DB
10:02  Agent join lại room R → cache cũ vẫn ALLOW
```

Cách giảm rủi ro:

1. TTL permission ngắn phù hợp mức độ nhạy cảm.
2. Invalidate cache khi thay đổi phân công/role.
3. Với thao tác quyền cao, đọc **nguồn authoritative** hoặc kiểm tra version của policy.
4. Bind cache key với **tenantId + userId + roomId + role/policy version**.
5. Không cache kết quả từ request chưa xác thực.
6. Khi Redis/cache không khả dụng, có chiến lược **fail closed** cho việc cấp quyền nhạy cảm.
7. Không dùng khóa cache dựa riêng trên roomId trong multi-tenant.
8. Giám sát số lần từ chối, độ trễ invalidate và sự cố stale authorization.

Cache giúp hiệu năng; không được trở thành nguyên nhân client bị thu hồi quyền vẫn đọc dữ liệu riêng tư quá lâu.

## 34. Azure SignalR Service: group có semantics khác

Nếu ứng dụng sử dụng **ASP.NET Core SignalR**, nhóm kết nối thường được quản lý bằng **Hub methods** và `IGroupManager` hoặc SignalR Service management APIs tương ứng.

Ví dụ Hub trong ASP.NET Core:

```csharp
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.SignalR;

[Authorize]
public sealed class OrderHub : Hub
{
    private readonly IOrderAccessPolicy _policy;

    public OrderHub(IOrderAccessPolicy policy)
    {
        _policy = policy;
    }

    public async Task JoinOrder(string orderId)
    {
        string? userId = Context.UserIdentifier;
        if (userId is null ||
            !await _policy.CanViewOrderAsync(userId, orderId))
        {
            throw new HubException("Not authorized for this order");
        }

        string group = _policy.CanonicalGroupFor(userId, orderId);
        await Groups.AddToGroupAsync(Context.ConnectionId, group);
    }

    public Task LeaveOrder(string groupName)
    {
        // Bản production phải derive/check groupName phía server.
        return Groups.RemoveFromGroupAsync(
            Context.ConnectionId, groupName);
    }
}

// IOrderAccessPolicy là interface của ứng dụng, không phải
// interface có sẵn trong SignalR.
```

**Đây là mã minh họa một phần**, cần implementation `IOrderAccessPolicy`, DI registration và cấu hình authentication thực tế. Với `LeaveOrder`, không nên tin groupName client truyền trực tiếp trong Production; hãy derive room từ ID/ngữ cảnh rồi kiểm tra.

### Điểm khác Web PubSub

| Web PubSub | SignalR |
|---|---|
| Có JSON client protocol với roles `webpubsub.joinLeaveGroup...` và `sendToGroup...`. | App định nghĩa Hub methods và authorization trong ASP.NET Core; không tự dùng những roles Web PubSub đó. |
| Client có thể tự join khi được cấp Web PubSub role, hoặc server quản lý membership. | Client thường gọi Hub method, server kiểm tra rồi dùng `Groups.AddToGroupAsync`. |
| Service server SDK có thao tác groups/users/connections. | SignalR Hub context/management SDK có thao tác tương đương theo mô hình khác. |
| Access URI/token và hub là khái niệm của Web PubSub service. | SignalR negotiate/access token và Hub endpoint có semantics riêng. |

**Chọn dịch vụ trước, rồi chọn đúng mô hình SDK/permissions.** Không copy protocol JSON của Web PubSub vào SignalR client và mong nó hoạt động.

## 35. Microsoft Entra ID, managed identity và Azure RBAC

Đối với backend quản lý Azure Web PubSub:

- Ưu tiên **managed identity** khi dịch vụ/SDK hỗ trợ.
- Cấp Azure RBAC **data-plane role** phù hợp trên resource/scope cho backend.
- Chỉ đội hạ tầng được cấp quyền quản trị resource/network/keys theo control plane.
- Tránh dùng service access key/connection string trong application settings plaintext nếu có giải pháp identity.
- Nếu phải dùng key, lưu trong Azure Key Vault/secret manager và rotate theo quy trình.
- Không gán quyền data-plane của resource cho end user browser chỉ để họ vào group.
- Trình duyệt dùng **client access URL được cấp có kiểm soát**; authentication application được thực hiện trước đó.
- API authorize room còn dựa trên database/policy riêng.

**Azure Contributor ở resource group** không tự đồng nghĩa “tất cả client đều được xem mọi group”. **Managed identity enabled** cũng không đồng nghĩa identity đã có quyền gửi message; cần kiểm tra role, scope và data-plane operation thực tế.

### Client app dùng Microsoft Entra login

Có thể triển khai:

```text
Browser → Entra authentication → application bearer token
    → Backend API negotiate validates user and tenant
    → Backend issues Web PubSub client access URL
    → Browser connects WebSocket
```

Một Entra token cho application API và Web PubSub client access token **không nhất thiết hoán đổi cho nhau**. Cần tôn trọng audience, issuer, scope, thời hạn và giao thức xác thực tương ứng.

## 36. TLS, networking và Private Endpoint

Các lớp cần kiểm tra:

1. **HTTPS** cho application negotiate/API.
2. **WSS** cho browser→Web PubSub.
3. Endpoint và DNS của resource/hub chính xác.
4. Network restrictions/public vs private access theo SKU/tier.
5. Backend dùng Private Endpoint/VNet nếu tổ chức yêu cầu và tính năng hỗ trợ.
6. NSG, Azure Firewall, UDR, NAT và outbound egress phù hợp.
7. Browser clients ở Internet có thể truy cập endpoint đúng không khi resource bị khóa public access?
8. Token và client roles có scope hợp lệ?
9. Event handler/upstream endpoint được service gọi và xác thực đúng?
10. Certificate/hostname validation không bị tắt để “sửa lỗi nhanh”.

**Private Endpoint không tự cung cấp authorization**. Nó chỉ thay đổi đường mạng. Nếu Web PubSub resource chỉ có private access trong VNet, **browser bên ngoài VNet có thể không kết nối được**; cần xác định topology client public/private trước khi bật.

Không mặc định mọi tier/region hỗ trợ mọi network feature. Kiểm tra feature matrix thực tế rồi thiết kế.

## 37. Giới hạn dịch vụ, hiệu năng và quota

Khả năng chịu tải phụ thuộc:

- Số **concurrent connections**.
- Số lượng incoming/outgoing messages và kích thước payload.
- Tần suất join/leave/reconnect.
- Số groups, số connections trong group, giới hạn theo hub/tier.
- Bandwidth/network egress, service unit/capacity.
- Authentication/negotiate workload của backend.
- Tốc độ xử lý event handlers/upstream.
- Fan-out rộng, đặc biệt một group có hàng chục nghìn connections.
- Retry storms sau khi mạng/service phục hồi.

### Fan-out làm tăng outgoing traffic

Ví dụ minh họa:

```text
Backend gửi 1 message tới group 10.000 connections
→ Có thể tạo tới 10.000 outbound deliveries ở lớp realtime
  (phụ thuộc connections hiện hành và hành vi dịch vụ).
```

**Một send request không đồng nghĩa một message egress.** Khi lập capacity/cost model, cân nhắc số recipients và kích thước dữ liệu.

### Reconnect storm

Khi 20.000 clients đồng thời rớt kết nối rồi reconnect:

- Backend negotiate có thể quá tải.
- Mỗi client lấy token mới và join group lại.
- Group membership/control operations tăng đột biến.
- Redis/DB authorization checks tăng vọt.
- Outgoing messages/CPU/latency bị ảnh hưởng.

Cần jitter, token short TTL nhưng không quá ngắn gây negotiate dồn dập, auth caching an toàn, capacity planning và load testing theo giới hạn tier.

## 38. Giám sát kết nối, nhóm và quyền

Một hệ thống production nên quan sát đồng thời **service metrics** và **business authorization decisions**.

| Tín hiệu | Câu hỏi vận hành | Nguồn |
|---|---|---|
| Connected clients/current connections | Số WebSocket đang hoạt động? | Azure Monitor metrics theo Web PubSub resource. |
| Connection opens/closes/failures | Có tăng disconnect/reconnect? | Resource metrics/diagnostics + client telemetry. |
| Incoming/outgoing messages | Có spike hoặc drop traffic? | Service metrics. |
| Server/API send failures | Publisher có gửi thành công? | Backend logs + service diagnostics. |
| Join/leave success/failure | Client bị từ chối quyền hay lỗi protocol? | Client ACK/error + server audit. |
| Unauthorized join/send attempts | Có user cố vào group khác? | Backend authorization logs, protocol errors, security alerts. |
| Active group memberships | Những connections nào cần ở room? | Application mapping/event lifecycle; API khi hỗ trợ. |
| Token issuance/expiration | API negotiate có đang cấp quá rộng? | Backend audit, không lưu token. |
| Revocation delay | Sau thu hồi bao lâu thì không còn nhận? | Security tests + audit metrics. |
| Send-to-group latency/p95 | Real-time experience ra sao? | Backend timing + client E2E metrics. |
| Missed state after reconnect | UI có bị sai khi offline? | App reconnect/sync metrics. |

**Không mặc định Azure Monitor có sẵn một metric “user membership count của từng group”**. Nếu cần, ứng dụng phải tự thiết kế counters có reconciliation hoặc dùng service management API theo khả năng hỗ trợ.

### Correlation IDs

Tạo một chuỗi:

```text
Order eventId=evt-1042-shipped-1
  → backend publish operation ID
  → Web PubSub target hub/group
  → client received eventId
  → client state refresh requestId
```

Không dùng access token hay raw client URL như correlation ID. Có thể log **hash/opaque IDs** theo chính sách để giảm nguy cơ lộ dữ liệu.

## 39. Chi phí và khả năng mở rộng group

Chi phí có thể đến từ:

- Web PubSub tier/capacity, concurrent connections và message traffic theo pricing meter thực.
- Outbound fan-out tới nhiều connections.
- Backend App Service/Functions/AKS/Container Apps dùng cho negotiate và event handlers.
- Database/Redis dùng lưu room authorization, membership, state.
- Private Endpoint, network egress, firewall/NAT và DNS.
- Azure Monitor logs, Application Insights, retention.
- Persistent notification store/Service Bus nếu cần delivery sau offline.
- Load tests và thời gian vận hành.

| Thiết kế | Tác động |
|---|---|
| Một group cho mỗi order | Cách ly dữ liệu tốt; tăng số group names và quản lý lifecycle. |
| Một group chung cho cả tenant | Ít groups hơn nhưng dễ gửi dư dữ liệu nếu mỗi buyer không được xem mọi order. |
| Broadcast toàn hub | Dễ triển khai nhưng có nguy cơ rò riêng tư và fan-out lớn. |
| Payload rất lớn mỗi lần cập nhật | Tăng bandwidth/cost và latency; cân nhắc gửi hint + API fetch. |
| Reconnect liên tục | Tăng token issuance, connection churn và membership operations. |
| Caching quyền có TTL dài | Giảm DB reads nhưng tăng nguy cơ stale authorization. |

Không tối ưu số groups bằng cách hy sinh **tenant isolation**. Dùng Azure Pricing Calculator và service metrics thực tế; tránh đoán giá từ một số lượng connections đơn lẻ.

## 40. Runbook: client A có thể vào group tenant B

**Mức độ:** nguy cơ rò rỉ dữ liệu liên tenant, cần ưu tiên cao.

### Điều tra

1. Ghi incident ID, thời gian UTC, user ID/tenant đã được làm sạch.
2. Không phát payload nhạy cảm để tái hiện trên Production.
3. Kiểm tra negotiate endpoint có xác thực principal và tenant không.
4. Kiểm tra code xây group name; có dùng `roomId` client truyền trực tiếp không?
5. Xem token roles; có cấp `webpubsub.joinLeaveGroup` quá rộng không?
6. Kiểm tra API server-side AddConnectionToGroup có validate connection ownership không.
7. Xem permissions cache có stale hoặc thiếu tenant trong cache key không.
8. Xem group subscription/membership hoạt động có vượt phạm vi không.
9. Kiểm tra audit, xác định payload nào có thể đã được gửi.
10. Escalate theo incident response/privacy policy.

### Khắc phục

- Thu hồi quyền/join và remove/close affected connections theo khả năng dịch vụ.
- Tắt hoặc giới hạn flow negotiate lỗi khi chưa sửa xong.
- Cấp lại tokens với scoped roles ngắn hạn.
- Bổ sung tenant-aware authorization và canonical group names.
- Invalidate caches và deploy fix có phê duyệt.
- Test deny cross-tenant và kiểm tra hệ thống theo dõi.
- Không cố “xóa mọi group” để che sự cố; điều tra audit và ảnh hưởng thực.

### Bài học

**Tên group không phải password.** Quyền phải được gắn với user/tenant/resource thật và được thực thi ở backend/service.

## 41. Runbook: permission revoked nhưng client vẫn nhận message

**Hiện tượng:** agent bị xóa khỏi room nhưng tab cũ vẫn nhận thông báo.

### Các nguyên nhân có thể

- Backend chỉ đổi database, chưa remove active group membership.
- Access token/role vẫn còn hiệu lực.
- Agent có thể tự join lại vì role `joinLeaveGroup.G` chưa thu hồi.
- Có nhiều active connections của cùng user; chỉ xử lý một connection.
- Permission cache chưa invalidated.
- Event revoke bị trễ/lỗi trong worker.
- Message đã được gửi trước thời điểm revoke và tới sau.

### Các bước

1. Xác minh thời điểm đổi policy và timestamps của messages.
2. Xác định tất cả connections đang liên quan.
3. Revoke scoped permission/close connection nếu API/tình huống hỗ trợ.
4. Remove group memberships cần thiết.
5. Invalidate authorization cache.
6. Buộc negotiate lại hoặc re-authenticate.
7. Thử join và send trở lại: phải bị từ chối.
8. Phát một event lab không nhạy cảm; client bị thu hồi không nhận.
9. Ghi thời gian hoàn tất revocation và điều tra race window.
10. Bổ sung alert cho revocation workflow thất bại.

**Giới hạn:** không thể xóa một nội dung đã được người dùng nhận trước khi thu hồi. Thiết kế giảm payload nhạy cảm và giới hạn thời gian cấp quyền ngay từ đầu.

## 42. Runbook: reconnect thành công nhưng không nhận group messages

**Hiện tượng:** màn hình hiển thị “Connected” nhưng không cập nhật đơn hàng sau khi điện thoại chuyển mạng.

### Điều tra

1. Connection mới có ID khác connection cũ không?
2. Client có lấy access URL mới nếu URL cũ hết hạn?
3. Client dùng đúng hub và protocol/subprotocol?
4. Backend có cấp roles đúng với policy mới?
5. Có gửi `joinGroup` hoặc server re-add connection mới?
6. ACK join có success hay permission denied?
7. Backend publisher có gửi đúng group name và hub?
8. Client có đang filter/parse sai payload?
9. Có network/Private Endpoint/DNS restrictions?
10. Có message nào được gửi trong lúc client offline? Nếu có cần API catch-up.

### Khắc phục

- Re-negotiate và re-authorize room.
- Join connection hiện tại; đợi ACK hoặc server membership confirmation.
- Đồng bộ state từ API bền vững.
- Gắn eventId/version để xử lý trùng/sai thứ tự.
- Dùng reconnect backoff, không loop vô hạn.
- Theo dõi số failures sau đổi mạng và reconnect latency.

**Bài học:** WebSocket online không đồng nghĩa connection mới đã join group cũ. Reconnect cần **state rehydration**.

## 43. Bài thực hành: hệ thống thông báo đơn hàng theo tenant

**Bối cảnh:** tạo Azure Web PubSub resource lab với hub `orders`. Có ba người dùng giả lập:

- Alice thuộc tenant A, xem Order 1042.
- Bob thuộc tenant A, xem Order 1043.
- Carol thuộc tenant B, xem Order 9001.

Yêu cầu phân quyền:

| User | Được join/receive | Send từ client |
|---|---|---|
| Alice | `tenant-a.order-1042` | Không. |
| Bob | `tenant-a.order-1043` | Không. |
| Carol | `tenant-b.order-9001` | Không. |
| Server publisher | Được gửi theo group được backend quyết định. | Server-side operation. |

### Nhiệm vụ

1. Vẽ kiến trúc browser → negotiate API → Web PubSub → groups → backend publisher.
2. Tạo resource/hub lab theo quyền và budget được phê duyệt; xác minh tier và endpoint.
3. Cấu hình backend identity/server-side permissions tối thiểu.
4. Tạo dữ liệu phân quyền test cho Alice, Bob và Carol.
5. Viết endpoint negotiate lấy user/tenant từ principal đã xác thực.
6. Cấp token **chỉ có role joinLeaveGroup của group hợp lệ** hoặc dùng server-controlled membership.
7. Không cấp `webpubsub.sendToGroup` cho ba viewers.
8. Kết nối Alice vào Web PubSub bằng JSON client protocol.
9. Join group `tenant-a.order-1042`; kiểm tra ACK success.
10. Thử join `tenant-b.order-9001` bằng connection của Alice; phải bị từ chối.
11. Thử client sendToGroup vào room Alice; nếu không cấp send, phải bị từ chối.
12. Cho Bob và Carol join groups đúng theo quyền.
13. Backend gửi một event `OrderStatusChanged` chỉ tới group Alice.
14. Xác minh Alice nhận, Bob/Carol không nhận event đó.
15. Mở tab thứ hai của Alice, phân biệt connection-level và user-level membership.
16. Ngắt mạng tab đầu rồi reconnect; kiểm tra connection ID/membership được cấp lại.
17. Thu hồi quyền Alice, xóa membership/đóng connections phù hợp và kiểm tra không thể join lại.
18. Bật diagnostics/metrics và logs đã làm sạch.
19. Thử đổi group name trong frontend; xác nhận service/backend không tự cấp quyền.
20. Mô phỏng event được phát khi Alice offline; sau reconnect gọi API lấy state.
21. Đo số send operations và recipients để ước lượng fan-out/cost.
22. Kiểm tra token URLs không xuất hiện trong logs, Git hoặc browser analytics.
23. Ghi runbook xử lý sự cố cross-tenant join.
24. Dọn resource lab theo quy trình; không xóa resource dùng chung.

### Các dữ liệu thử

**Thông điệp gửi cho Alice:**

```json
{
  "eventId": "evt-lab-order-1042-shipped",
  "eventType": "OrderStatusChanged",
  "orderId": "ORD-1042",
  "version": 7,
  "status": "Shipped"
}
```

**Kỳ vọng nhận:**

```text
Alice connection C1 in tenant-a.order-1042 → receives
Alice C2 if not joined                     → not assumed to receive
Bob tenant-a.order-1043                   → must not receive
Carol tenant-b.order-9001                 → must not receive
```

**Test quyền âm:** Alice thử join `tenant-b.order-9001`, gửi tới group không được cấp quyền, hoặc truyền userId của Carol vào request negotiate. Backend/service phải từ chối, không cấp URL/role thay người dùng.

### Tiêu chí nghiệm thu

- Authenticated user ID và tenant lấy từ backend identity, không trust client.
- Mỗi client nhận đúng group messages đã được phép.
- Không cấp role `sendToGroup` cho viewer chỉ đọc.
- Client không thể mở rộng roles bằng sửa request/JavaScript.
- Reconnect tạo kết nối mới và có quy trình khôi phục membership.
- Revocation xử lý được cả active connections và khả năng rejoin.
- Không broadcast payload riêng tư toàn hub.
- Có state store/API để bù những cập nhật bị lỡ khi offline.
- Logs và chi phí được giám sát, không lộ token.
- Test report nêu cả trường hợp thành công lẫn bị từ chối.

## 44. Checklist production trước khi bật real-time groups

**Identity và phân quyền**

- [ ] Backend authenticate user và xác minh tenant.
- [ ] Không nhận userId/role/groupName chưa kiểm tra từ client.
- [ ] Group names được chuẩn hóa, tenant-scoped và không chứa dữ liệu bí mật.
- [ ] Client roles chỉ scoped tới groups cần thiết; không cấp wildcard rộng nếu không cần.
- [ ] Viewer không có direct send permission nếu chỉ cần nhận.
- [ ] Server data-plane credential không xuất hiện ở frontend.
- [ ] Token URL ngắn hạn, được truyền HTTPS và không bị log.
- [ ] Có revocation, close/leave và cache invalidation.

**Kết nối và tính đúng đắn**

- [ ] Reconnect có backoff và re-negotiate.
- [ ] Connection ID mới không được coi như session bền vững.
- [ ] Mọi active devices được xử lý theo policy revocation.
- [ ] Dữ liệu quan trọng có API/history bền vững để bù sự kiện offline.
- [ ] Event IDs/versions giúp tránh duplicate hoặc stale UI.
- [ ] Không coi protocol ACK là user read receipt.
- [ ] Khi group không xác định, không fallback broadcast toàn hub.
- [ ] Backend/API vẫn kiểm tra authorization cho thao tác nghiệp vụ.

**Vận hành và an toàn**

- [ ] Azure RBAC/managed identity đúng phạm vi.
- [ ] TLS/DNS/private networking được kiểm tra từ runtime thật.
- [ ] Event handlers/upstream có authentication.
- [ ] Metrics/logs/alerts cho connect, auth errors, join/leave, send failures.
- [ ] Có synthetic deny cross-tenant và revocation test.
- [ ] Đã test reconnect storm và fan-out load.
- [ ] Cost model bao gồm kết nối, outgoing messages, backend và monitoring.
- [ ] Có incident runbook và owner vận hành rõ ràng.

## 45. Câu hỏi tự kiểm tra

**Câu 1.** Trong Azure Web PubSub, hub và group khác nhau thế nào?

**Đáp án:** Hub là không gian logic tổ chức connections/groups/event handlers; group là tập connections trong một hub nhận broadcast theo group name.

**Câu 2.** User ID và connection ID có giống nhau không?

**Đáp án:** Không. Một user có thể có nhiều connections; connection ID gắn với một WebSocket cụ thể và thay đổi sau reconnect.

**Câu 3.** Đã authenticated thì user có được join mọi group không?

**Đáp án:** Không. Backend phải kiểm tra quyền theo tenant/room rồi cấp role hoặc server-controlled membership.

**Câu 4.** Role `webpubsub.joinLeaveGroup.<group>` cho phép làm gì?

**Đáp án:** Cho phép client join/leave group cụ thể theo Web PubSub client protocol khi được cấp hợp lệ.

**Câu 5.** Role `webpubsub.sendToGroup.<group>` có tự cho phép receive mọi message ở group không?

**Đáp án:** Không. Send permission và group membership là hai khái niệm khác.

**Câu 6.** Viewer chỉ nhận thông báo có cần `sendToGroup` không?

**Đáp án:** Không. Server có thể gửi cho group; viewer chỉ cần thuộc group hợp lệ.

**Câu 7.** Trình duyệt có thể tự gửi connection string của Web PubSub service không?

**Đáp án:** Không nên. Service keys/connection strings phải ở backend hoặc secret manager; frontend dùng scoped client access URL.

**Câu 8.** Vì sao không cho client chọn userId trong API negotiate?

**Đáp án:** Người dùng có thể giả danh người khác để xin token/role; userId phải xuất phát từ principal đã xác thực.

**Câu 9.** Tên group khó đoán có đủ bảo mật không?

**Đáp án:** Không. Group name không phải secret; phải enforce roles và authorization phía server.

**Câu 10.** Alice có role join group A, cô ấy sửa JavaScript để join group B. Điều gì nên xảy ra?

**Đáp án:** Service/backend từ chối vì không có quyền scoped cho B.

**Câu 11.** Agent bị remove group nhưng còn role join. Rủi ro nào?

**Đáp án:** Có thể tự join lại; phải revoke permission hoặc close affected connections theo thiết kế.

**Câu 12.** Token hết hạn có bảo đảm mọi WebSocket hiện tại lập tức bị đóng không?

**Đáp án:** Không được giả định như vậy. Cần cơ chế chủ động thu hồi/đóng kết nối khi quyền thay đổi.

**Câu 13.** Vì sao sau reconnect cần join lại?

**Đáp án:** Connection cũ đã kết thúc, connection mới có ID và trạng thái membership mới.

**Câu 14.** User có hai tabs nhưng chỉ tab một ở group; send-to-group có chắc tới tab hai không?

**Đáp án:** Không. Membership là theo connection/topology, cần kiểm tra semantics khi dùng user-level operations.

**Câu 15.** Backend trả send-to-group success có nghĩa người dùng đã đọc không?

**Đáp án:** Không. Cần application-level read receipt hoặc API/status store.

**Câu 16.** Khi user offline, Web PubSub có tự lưu mọi group messages để đọc lại như queue không?

**Đáp án:** Không nên coi là hàng đợi bền vững. Cần persistent notification store và cơ chế catch-up.

**Câu 17.** Redis cache có thể là nguồn duy nhất quyết định quyền room không?

**Đáp án:** Không. Permission cache có TTL/invalidation, không thay thế authoritative policy.

**Câu 18.** Vì sao cache key phải có tenant ID?

**Đáp án:** Tránh nhầm quyền giữa những người dùng/room cùng ID ở các tenants khác nhau.

**Câu 19.** Khi WebSocket ACK join thành công nhưng không nhận message, nên kiểm tra gì?

**Đáp án:** Hub/group name, thời điểm publish, membership hiện tại, publisher scope và client parsing/connection health.

**Câu 20.** Có nên broadcast toàn hub khi group lookup lỗi không?

**Đáp án:** Không. Dễ làm lộ dữ liệu riêng tư tới người không có quyền.

**Câu 21.** Web PubSub group permission có áp dụng tự động cho SignalR Hub methods không?

**Đáp án:** Không. SignalR có Hub/Groups và authorization theo framework/runtime riêng.

**Câu 22.** Azure RBAC Contributor có tự xác định buyer được xem order nào không?

**Đáp án:** Không. Azure RBAC bảo vệ resource/data plane; application authorization cần xác minh business data.

**Câu 23.** Private Endpoint có làm client hợp lệ dù thiếu group role không?

**Đáp án:** Không. Network reachability và authorization là hai lớp khác nhau.

**Câu 24.** Một group 10.000 connections có thể làm chi phí outgoing tăng thế nào?

**Đáp án:** Một send có thể fan-out thành nhiều deliveries; cần ước lượng recipients, payload size, tier và pricing meter thật.

**Câu 25.** Nếu cùng Order version 11 tới sau version 12, frontend nên làm gì?

**Đáp án:** Không ghi đè trạng thái mới bằng cũ; dùng version/event ID và refresh authoritative state khi cần.

**Câu 26.** Vì sao không coi disconnect event là dấu mốc presence tuyệt đối?

**Đáp án:** Network và event processing có độ trễ, events có thể đến muộn/lặp; cần TTL/heartbeat và reconciliation.

**Câu 27.** Nếu client có `sendToGroup`, backend có thể bỏ kiểm tra business commands không?

**Đáp án:** Không. Web PubSub role chỉ giới hạn thao tác gửi qua protocol; nghiệp vụ vẫn phải validate/authenticate/authorize.

**Câu 28.** Tại sao một user có nhiều thiết bị làm revocation phức tạp?

**Đáp án:** Cần xử lý nhiều active connections hoặc user-level operation phù hợp, không chỉ một tab/connection ID.

**Câu 29.** Dấu hiệu nào gợi ý reconnect storm?

**Đáp án:** Tăng đột biến kết nối mới, negotiate requests, join operations, backend CPU/latency và authorization lookups.

**Câu 30.** Điều kiện tối thiểu để nghiệm thu multi-tenant group permissions là gì?

**Đáp án:** User được cấp đúng room nhận thông báo; user trái tenant bị từ chối; viewer không thể gửi nếu không có role; reconnect/revocation có kiểm thử; không lộ access URL hoặc dữ liệu riêng tư.

**Tóm lại:** **Phân quyền client và quản lý group kết nối** trong Azure Web PubSub yêu cầu kết hợp **authentication của ứng dụng, scoped client roles, server-authorized membership và quản lý vòng đời WebSocket**. Group không phải cơ chế phân quyền tự thân, connection không phải user, ACK không phải xác nhận đọc và real-time delivery không phải message persistence. Một hệ thống an toàn phải **chặn cross-tenant join/send, thu hồi quyền đang có hiệu lực, tái xác thực sau reconnect, chỉ broadcast đúng đối tượng và theo dõi lỗi/quota/chi phí**. Các nguyên tắc tương tự về server-side authorization vẫn quan trọng trong **Azure SignalR Service**, nhưng API và mô hình quyền khác với Web PubSub.
