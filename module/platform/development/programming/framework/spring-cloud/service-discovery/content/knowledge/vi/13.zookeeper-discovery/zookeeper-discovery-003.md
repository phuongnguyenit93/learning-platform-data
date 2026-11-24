# Phiên kết nối, thời hạn phiên và vòng đời nút tạm thời

Trong ZooKeeper, một client không chỉ mở TCP connection rồi gửi lệnh độc lập. Client tạo một **session** với cụm ZooKeeper và duy trì session đó qua các kết nối mạng. Session là đơn vị mà server dùng để theo dõi client, quyền sở hữu các ephemeral znode và thời điểm client được xem là đã mất.

Điều này rất quan trọng với service discovery. Khi một service instance đăng ký bằng ephemeral znode, nút đó tồn tại gắn với session đã tạo ra nó. Nếu kết nối mạng chập chờn nhưng session vẫn còn hiệu lực, znode có thể tiếp tục tồn tại. Nếu session hết hạn, ZooKeeper tự động xóa các ephemeral znode thuộc session đó. Instance muốn xuất hiện lại trong registry phải tạo session mới và đăng ký lại.

Trong Spring Cloud Zookeeper Discovery, thư viện Curator quản lý kết nối và vòng đời session ở phía client. Hiểu rõ trạng thái kết nối, session timeout và ephemeral node giúp xử lý đúng các tình huống mất mạng, khởi động lại, tạm dừng JVM và đăng ký lại service.

## 1. Session trong ZooKeeper là gì?

Session là một phiên làm việc logic giữa ZooKeeper client và cụm ZooKeeper. Khi client kết nối lần đầu, server tạo session và cấp một session ID cùng thông tin xác thực phiên. Client sử dụng session này trong các lần kết nối tiếp theo.

Một session có các đặc điểm:

- Có định danh riêng là session ID.
- Được duy trì bằng các gói tin heartbeat và hoạt động client-server.
- Có thời hạn do client yêu cầu và server thương lượng.
- Có thể tiếp tục qua một lần đứt kết nối nếu client kết nối lại trước khi session hết hạn.
- Khi hết hạn, server xóa các ephemeral znode thuộc session.

Session không đồng nghĩa với một TCP connection. TCP connection có thể bị ngắt rồi được thiết lập lại trong khi session vẫn còn hiệu lực. Đây là điểm mấu chốt để phân biệt mất kết nối tạm thời với việc client thực sự mất quyền sở hữu các ephemeral node.

~~~mermaid
flowchart TD
    C["ZooKeeper client"] -->|"Tạo session"| S[("ZooKeeper ensemble")]
    S -->|"Session ID và timeout đã thương lượng"| C
    C <-->|"Heartbeat / request / response"| S
    C -->|"Tạo ephemeral znode"| E["Ephemeral znode"]
    E -->|"Gắn với session owner"| S
~~~

Trong service discovery, mỗi instance có thể tạo một znode đại diện cho chính nó. Session là cơ sở để ZooKeeper biết instance nào đang sở hữu znode đó.

## 2. Session timeout và connection timeout

Hai loại timeout thường bị nhầm lẫn:

| Timeout | Ý nghĩa | Hệ quả khi hết hạn |
|---|---|---|
| Connection timeout | Thời gian chờ thiết lập kết nối tới một server hoặc endpoint | Lần kết nối hiện tại thất bại; client có thể thử server khác |
| Session timeout | Thời gian tối đa server chờ hoạt động hợp lệ từ client trước khi xem session đã hết hạn | Session bị xóa và các ephemeral znode thuộc session bị xóa |

Connection timeout thường ngắn hơn và áp dụng cho một lần kết nối. Session timeout quyết định vòng đời logic của session. Một lần connection timeout không tự động có nghĩa session đã hết hạn.

### Client yêu cầu, server thương lượng

Client yêu cầu một session timeout khi tạo session. ZooKeeper server sẽ thương lượng giá trị hiệu lực trong giới hạn mà server cho phép. Trong cấu hình ZooKeeper, giới hạn thường được điều khiển bởi minSessionTimeout và maxSessionTimeout; nếu không cấu hình riêng, các giá trị mặc định được tính theo tickTime của server.

Vì vậy, giá trị client yêu cầu không nhất thiết là giá trị cuối cùng. Cần xem log hoặc thông tin session của client và cấu hình cụm khi cần xác định timeout thực tế.

Session timeout quá ngắn có thể khiến một lần pause JVM, GC dài hoặc sự cố mạng ngắn làm session hết hạn. Timeout quá dài khiến registry giữ ephemeral node lâu hơn sau khi instance đã chết, làm chậm quá trình phát hiện instance không còn hoạt động.

### Chọn session timeout

Khi chọn timeout, cân nhắc:

- Thời gian pause JVM hoặc container có thể gặp trong điều kiện tải cao.
- Độ trễ mạng giữa ứng dụng và ZooKeeper ensemble.
- Thời gian phục hồi khi một node ZooKeeper bị lỗi hoặc client chuyển sang server khác.
- Mức độ chấp nhận instance cũ còn xuất hiện trong discovery.
- Tải heartbeat và số lượng session trên cụm.

Không nên đặt timeout cực ngắn chỉ để phát hiện lỗi nhanh. Cơ chế phát hiện quá nhạy có thể tạo ra hiện tượng instance liên tục mất session rồi đăng ký lại khi hệ thống chỉ bị chậm tạm thời.

## 3. Heartbeat duy trì session

ZooKeeper client duy trì session bằng cách gửi heartbeat và các request đến server. Server cập nhật thời điểm hoạt động gần nhất của session. Nếu không nhận được hoạt động trong khoảng timeout đã thương lượng, server có thể xem session đã hết hạn.

Heartbeat thường được thư viện client quản lý tự động. Ứng dụng Spring Boot không cần tự viết lịch gửi ping để duy trì session khi sử dụng Spring Cloud Zookeeper và Curator đúng cách.

~~~mermaid
sequenceDiagram
    participant A as Application / Curator
    participant Z as ZooKeeper server
    participant N as Ephemeral znode
    A->>Z: Mở session
    Z-->>A: Session ID và timeout
    A->>N: Tạo ephemeral znode
    loop Session còn hiệu lực
        A->>Z: Heartbeat hoặc request
        Z-->>A: Phản hồi
    end
~~~

Heartbeat không phải health check nghiệp vụ. Nó chứng minh client vẫn có thể duy trì giao tiếp với ZooKeeper. Nó không chứng minh API của service đang xử lý đúng, database còn hoạt động hoặc instance sẵn sàng phục vụ mọi request.

Do đó, cần phân biệt:

- **Session liveness:** client còn duy trì được session với ZooKeeper hay không.
- **Process liveness:** tiến trình ứng dụng còn chạy hay không.
- **Service health/readiness:** instance có đủ điều kiện nhận request nghiệp vụ hay không.

Một ứng dụng có thể giữ session khỏe mạnh nhưng endpoint nghiệp vụ bị lỗi. Ngược lại, ứng dụng vẫn chạy và phục vụ request trong khi mất kết nối tạm thời tới ZooKeeper.

## 4. Ephemeral znode là gì?

Znode là đơn vị dữ liệu trong cây phân cấp của ZooKeeper. Có hai loại thường gặp:

- **Persistent znode:** tồn tại cho đến khi client hoặc quản trị viên xóa nó.
- **Ephemeral znode:** được tạo gắn với một session và tự động bị xóa khi session đó hết hạn.

Trong service discovery, ephemeral znode phù hợp để đại diện cho một instance đang đăng ký. Khi instance mất session, registry tự loại bỏ bản ghi tương ứng mà không cần tiến trình đã chết phải chạy mã cleanup.

Ví dụ cấu trúc minh họa:

~~~text
/services                         (persistent)
  /inventory-service              (persistent)
    /instance-01                  (ephemeral)
    /instance-02                  (ephemeral)
  /payment-service                (persistent)
    /instance-01                  (ephemeral)
~~~

Các znode cha thường là persistent để giữ cấu trúc cây. Znode instance là ephemeral, chứa dữ liệu như host, port, metadata hoặc thông tin định tuyến. Cấu trúc chính xác do thư viện discovery và phiên bản triển khai quyết định; cây trên nhằm minh họa mối quan hệ giữa service và instance.

### Đặc điểm của ephemeral znode

- Gắn với session đã tạo ra node.
- Tự bị xóa khi session owner hết hạn.
- Không thể có child znode bên dưới một ephemeral znode.
- Có thể dùng ephemeral sequential node nếu cần tên được ZooKeeper cấp thêm hậu tố tuần tự.
- Không tự hết hạn chỉ vì một TCP connection bị đóng; việc xóa gắn với session expiration.

Trường ephemeralOwner trong stat của znode cho biết session ID đang sở hữu ephemeral node. Với persistent znode, ephemeralOwner bằng 0.

## 5. Vòng đời ephemeral node khi service đăng ký

Giả sử inventory-service chạy hai instance. Mỗi instance tạo một session riêng và đăng ký ephemeral znode của nó:

~~~mermaid
sequenceDiagram
    participant I1 as Inventory instance 01
    participant I2 as Inventory instance 02
    participant Z as ZooKeeper
    participant C as Discovery consumer
    I1->>Z: Mở session S1
    I2->>Z: Mở session S2
    I1->>Z: Create ephemeral /services/inventory/01
    I2->>Z: Create ephemeral /services/inventory/02
    Z-->>C: Watch /services/inventory
    C->>Z: Đọc danh sách instance
    Z-->>C: Instance 01, Instance 02
    Note over I2,Z: Session S2 hết hạn
    Z->>Z: Xóa ephemeral node của S2
    Z-->>C: Watch event: instance 02 bị xóa
    C->>Z: Đọc lại danh sách instance
    Z-->>C: Chỉ còn instance 01
~~~

Luồng điển hình:

1. Instance khởi động và tạo session với ZooKeeper.
2. Discovery client tạo ephemeral znode chứa thông tin instance.
3. Consumer đọc danh sách instance và có thể đăng ký watch để nhận tín hiệu khi cây thay đổi.
4. Khi instance dừng có kiểm soát, client có thể chủ động xóa node và đóng session.
5. Nếu tiến trình chết hoặc mất mạng kéo dài, server phát hiện session hết hạn và tự xóa node.
6. Consumer nhận tín hiệu thay đổi, đọc lại dữ liệu và cập nhật danh sách instance.

Đăng ký và hủy đăng ký qua vòng đời ứng dụng giúp trạng thái registry sạch hơn. Tuy nhiên, khả năng tự xóa ephemeral node khi session hết hạn vẫn rất quan trọng vì shutdown hook không thể chạy trong mọi sự cố.

## 6. Mất kết nối tạm thời không đồng nghĩa session đã hết hạn

Đây là tình huống quan trọng nhất khi vận hành ZooKeeper.

Giả sử ứng dụng bị mất kết nối tới ZooKeeper trong vài giây do network interruption. Trong thời gian này, client không gửi được heartbeat. Nếu session timeout chưa hết, server vẫn giữ session và ephemeral znode. Khi client kết nối lại và tiếp tục dùng được session cũ, znode vẫn còn.

~~~mermaid
flowchart TD
    A["Client đang CONNECTED"] --> B["Mất kết nối mạng"]
    B --> C["Session còn trong thời hạn"]
    C --> D{"Kết nối lại kịp?"}
    D -->|"Có"| E["RECONNECTED với session cũ"]
    E --> F["Ephemeral node vẫn tồn tại"]
    D -->|"Không"| G["Server hết hạn session"]
    G --> H["Ephemeral node bị xóa"]
    H --> I["Client tạo session mới"]
    I --> J["Đăng ký lại ephemeral node"]
~~~

Vì vậy:

- Không nên xóa và tạo lại toàn bộ registration chỉ vì một socket tạm thời bị ngắt nếu session vẫn có thể phục hồi.
- Không nên khẳng định instance đã chết ngay khi nhận tín hiệu mất kết nối.
- Cần phân biệt trạng thái kết nối tạm thời với sự kiện session expired.
- Nếu session đã hết hạn, node cũ không thể được giữ lại bằng cách kết nối lại với session đó.

Trong khoảng mất kết nối, consumer có thể vẫn nhìn thấy ephemeral node trong registry. Điều này không đảm bảo instance còn nhận request. Chính sách timeout và xử lý lỗi ở consumer vẫn cần thiết.

## 7. Session hết hạn và đăng ký lại

Session hết hạn là sự kiện khác hẳn reconnect thành công. Khi server đã đánh dấu session expired:

1. Session cũ không còn hợp lệ.
2. ZooKeeper xóa mọi ephemeral znode được session đó sở hữu.
3. Client không thể tiếp tục dùng session ID cũ.
4. Client cần tạo session mới.
5. Discovery integration phải đăng ký lại các ephemeral node đại diện cho instance.

Một ứng dụng có thể vẫn còn process và thậm chí API vẫn đang chạy khi session hết hạn. Ví dụ, JVM bị pause lâu hơn timeout hoặc node bị cô lập mạng trong một khoảng thời gian dài. Sau khi hoạt động trở lại, ứng dụng phải nhận biết session đã mất và hoàn thành đăng ký lại trước khi xem mình là một instance đã được discovery công bố.

### Không tái sử dụng registration cũ một cách mù quáng

Khi session mới được tạo, ephemeral node cũ đã bị xóa. Việc client giữ trong bộ nhớ một đường dẫn znode hoặc một bản sao dữ liệu cũ không có nghĩa node đó vẫn tồn tại trên server.

Quy trình phục hồi cần:

- Tạo session mới và xác nhận kết nối ổn định.
- Tạo lại znode đăng ký với instance ID phù hợp.
- Xử lý trường hợp node đã tồn tại do một lần đăng ký khác hoặc do luồng phục hồi chạy lặp.
- Cập nhật watch và cache ở consumer.
- Chỉ báo instance đã đăng ký sau khi thao tác tạo node thành công.

Nếu có nhiều luồng phục hồi đồng thời, cần đồng bộ để tránh hai lần tạo cùng đường dẫn. Có thể dùng thao tác idempotent, kiểm tra quyền sở hữu node và xử lý NodeExistsException theo đúng instance identity.

## 8. Trạng thái kết nối trong Curator

Spring Cloud Zookeeper thường sử dụng Apache Curator để quản lý ZooKeeper client. Curator cung cấp các trạng thái kết nối giúp ứng dụng phân biệt mất kết nối tạm thời và mất session.

Các trạng thái thường gặp:

| Trạng thái Curator | Ý nghĩa | Cách hiểu trong service discovery |
|---|---|---|
| CONNECTED | Kết nối và session đã sẵn sàng | Có thể thực hiện thao tác discovery |
| SUSPENDED | Kết nối bị gián đoạn hoặc tạm thời không chắc chắn | Không kết luận session đã hết hạn; tạm dừng các quyết định phụ thuộc registry nếu cần |
| RECONNECTED | Client đã kết nối lại | Có thể tiếp tục session cũ nếu session chưa hết hạn |
| LOST | Session đã hết hạn hoặc mất hiệu lực | Ephemeral node đã bị xóa; phải tạo session và đăng ký lại |

Tên trạng thái và chi tiết callback phụ thuộc phiên bản Curator, nhưng nguyên tắc phân biệt SUSPENDED, RECONNECTED và LOST vẫn rất quan trọng.

Một cách xử lý khái niệm:

~~~text
CONNECTED:
  Cho phép discovery hoạt động bình thường.

SUSPENDED:
  Đánh dấu trạng thái registry chưa chắc chắn.
  Hạn chế thao tác cần bảo đảm quyền sở hữu session.
  Chờ kết quả reconnect hoặc session loss.

RECONNECTED:
  Nếu session cũ còn hiệu lực, tiếp tục theo dõi và xác minh registration.
  Làm mới snapshot discovery nếu cần.

LOST:
  Không sử dụng registration gắn với session cũ.
  Tạo session mới và đăng ký lại ephemeral node.
  Công bố instance sau khi đăng ký thành công.
~~~

Không nên xử lý SUSPENDED giống LOST. Nếu xóa node hoặc tạo registration mới ngay khi kết nối tạm thời bị ngắt, ứng dụng có thể tạo churn không cần thiết. Ngược lại, bỏ qua LOST có thể khiến instance chạy nhưng biến mất khỏi registry.

## 9. Cấu hình session trong Spring Cloud Zookeeper

Ứng dụng dùng Spring Cloud Zookeeper Discovery cần khai báo endpoint ZooKeeper ensemble và có thể điều chỉnh connection timeout, session timeout theo yêu cầu triển khai.

Ví dụ cấu hình minh họa:

~~~yaml
spring:
  application:
    name: inventory-service
  cloud:
    zookeeper:
      connect-string: zk-1.internal:2181,zk-2.internal:2181,zk-3.internal:2181
      session-timeout: 10000
      connection-timeout: 15000
      discovery:
        enabled: true
        register: true
        root: /services
        instance-id: inventory-service-node-01
~~~

Trong ví dụ, timeout được biểu diễn bằng mili giây theo cách cấu hình thường gặp của Spring Cloud Zookeeper. Hãy xác nhận kiểu dữ liệu và tên property trong phiên bản Spring Cloud đang sử dụng. Giá trị client yêu cầu vẫn chịu giới hạn min/max session timeout do ZooKeeper server thương lượng.

Các thuộc tính có vai trò khác nhau:

- **connect-string:** danh sách host và client port của ZooKeeper ensemble.
- **session-timeout:** thời gian session client yêu cầu; ảnh hưởng thời điểm server xem session là hết hạn.
- **connection-timeout:** giới hạn chờ khi thiết lập kết nối.
- **discovery.root:** nút gốc dùng để tổ chức registration của dịch vụ.
- **discovery.instance-id:** định danh instance được đăng ký; cần duy nhất trong phạm vi service.
- **discovery.register:** bật hoặc tắt đăng ký instance.

Không nhầm client port 2181 với các cổng quorum, election hoặc giao tiếp nội bộ giữa các ZooKeeper server. Ứng dụng kết nối tới client port của ensemble; server quản lý các cổng nội bộ.

## 10. Quan sát ephemeral node bằng ZooKeeper CLI

Có thể dùng ZooKeeper CLI để xem node và trạng thái owner. Ví dụ trong môi trường kiểm thử, sau khi kết nối tới server:

~~~text
create /services ""
create /services/inventory-service ""
create -e /services/inventory-service/instance-01 "{\"host\":\"10.0.1.11\",\"port\":8081}"
ls /services/inventory-service
stat /services/inventory-service/instance-01
get -s /services/inventory-service/instance-01
~~~

Hai node cha được tạo persistent; node instance được tạo với tùy chọn ephemeral. Kết quả stat có thể cho biết ephemeralOwner của node. Giá trị khác 0 cho biết node gắn với một session.

Khi CLI client thoát hoặc session bị mất, server không nhất thiết xóa node ngay tại thời điểm socket đóng. Node sẽ được xóa khi session owner hết hạn. Có thể quan sát bằng cách đợi quá session timeout rồi đọc lại cây:

~~~text
ls /services/inventory-service
~~~

Lệnh trên chỉ minh họa cách quan sát. Trong môi trường thật, không tự tạo node giả trùng với đường dẫn mà Spring Cloud Zookeeper đang quản lý. ACL của node cũng cần được cấu hình phù hợp; không dùng ACL mở cho mọi người ghi trong production.

## 11. Watcher và thay đổi registry

Consumer thường cần biết khi ephemeral node được tạo hoặc xóa. ZooKeeper hỗ trợ watch để client nhận thông báo khi znode hoặc child list thay đổi.

Ví dụ, consumer theo dõi children của:

~~~text
/services/inventory-service
~~~

Khi instance mới đăng ký, child node xuất hiện. Khi session owner hết hạn, ephemeral node bị xóa và consumer nhận tín hiệu thay đổi.

Watch của ZooKeeper có tính chất một lần: sau khi sự kiện được gửi, client thường cần đăng ký watch mới để tiếp tục theo dõi. Các abstraction như Curator Cache hoặc service discovery integration có thể tự quản lý việc đăng ký lại watch và cập nhật dữ liệu.

Không nên coi watch event là một bản sao đầy đủ của trạng thái registry. Event báo rằng có thay đổi; consumer nên đọc lại danh sách hiện tại để lấy snapshot mới. Nếu kết nối mất trong lúc watch không hoạt động, client cần phục hồi watch và đối soát trạng thái.

## 12. Tác động đến service discovery và request đang chạy

Khi ephemeral node bị xóa, consumer sẽ dần loại instance đó khỏi danh sách discovery sau khi nhận và xử lý thay đổi. Tuy nhiên, request đã được gửi tới instance trước thời điểm cập nhật có thể vẫn đang chạy hoặc thất bại vì tiến trình đã dừng.

Vì thế, cơ chế session không thay thế các chính sách resilience:

- Đặt timeout kết nối và timeout xử lý request phù hợp.
- Retry có giới hạn và chỉ retry thao tác an toàn/idempotent.
- Dùng circuit breaker khi cần ngăn request liên tục tới endpoint lỗi.
- Cập nhật cache discovery sau watch event hoặc sau reconnect.
- Không xem một instance là sẵn sàng chỉ vì ephemeral node còn tồn tại.
- Khi session LOST, tránh tiếp tục tự nhận mình là instance đã đăng ký trước khi tạo lại node.

Với thao tác cần độc quyền như leader election hoặc khóa phân tán, session expiration còn có thể tạo tình huống tiến trình cũ tiếp tục chạy sau khi mất quyền sở hữu. Cần cơ chế fencing token hoặc epoch để ngăn tiến trình cũ ghi dữ liệu sau khi một owner mới đã được bầu. Việc chỉ dựa vào ephemeral node để khóa mà không fencing có thể gây lỗi khi mạng phân vùng hoặc JVM pause dài.

## 13. Bảo mật và quyền sở hữu znode

Ephemeral node gắn với session nhưng quyền tạo, đọc, sửa và xóa vẫn được kiểm soát bằng ACL của ZooKeeper. Session không tự động cấp quyền truy cập cho mọi client khác.

Các điểm cần chú ý:

- Dùng authentication scheme và ACL phù hợp với ứng dụng.
- Hạn chế quyền tạo hoặc xóa node trong nhánh registry của service.
- Không sử dụng ACL mở như world:anyone với quyền ghi trong production.
- Bảo vệ thông tin session password và credential trong log, dump hoặc secret store.
- Phân tách namespace hoặc root path khi nhiều ứng dụng/nhóm triển khai dùng chung ensemble.
- Theo dõi số lượng session, số ephemeral node và sự kiện session expiration.

Nếu client bị mất credential hoặc authentication thất bại, việc reconnect có thể không khôi phục session như mong muốn. Cần phân biệt lỗi xác thực với lỗi mạng và session expiration khi chẩn đoán.

## 14. Tình huống lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Instance vẫn còn trong registry một lúc sau khi process chết | Server đang chờ session timeout | Kiểm tra session timeout và thời điểm node bị xóa |
| Instance biến mất khi JVM pause dài | Session hết hạn trong lúc client không gửi heartbeat | Điều chỉnh timeout và kiểm tra GC pause |
| Socket reconnect thành công nhưng node không còn | Session cũ đã expired; client đã tạo session mới hoặc chưa đăng ký lại | Xử lý LOST và tạo lại ephemeral node |
| Instance bị xóa khi chỉ mất mạng ngắn | Timeout quá ngắn hoặc gián đoạn kéo dài hơn giới hạn thương lượng | Kiểm tra timeout thực tế, network latency và pause |
| Hai registration cùng service instance | Instance ID hoặc đường dẫn không duy nhất, retry không idempotent | Chuẩn hóa instance ID và xử lý NodeExists |
| Consumer không cập nhật sau khi node bị xóa | Watch không được đăng ký lại hoặc cache chưa refresh | Đọc lại snapshot và khôi phục watch |
| Instance chạy nhưng không xuất hiện trong discovery | Session mới chưa tạo registration hoặc ACL từ chối | Kiểm tra log Curator, trạng thái session và ACL |
| Service được phát hiện nhưng không gọi được | Ephemeral node còn trong khoảng chờ timeout dù tiến trình đã mất | Dùng timeout request và resilience ở consumer |

## 15. Nguyên tắc vận hành

- Phân biệt TCP connection với ZooKeeper session.
- Hiểu connection timeout và session timeout là hai cơ chế khác nhau.
- Chọn session timeout theo độ trễ mạng, thời gian pause JVM và thời gian chấp nhận stale registration.
- Để Curator quản lý heartbeat; không tự viết heartbeat song song khi không cần thiết.
- Dùng ephemeral znode cho registration gắn với vòng đời instance.
- Khi mất kết nối tạm thời, chờ kết quả reconnect thay vì kết luận session đã mất ngay.
- Khi nhận trạng thái LOST hoặc session expired, tạo session mới và đăng ký lại ephemeral node.
- Dùng watch để nhận tín hiệu thay đổi nhưng đọc lại snapshot để xác nhận trạng thái hiện tại.
- Theo dõi session expiration, reconnect, ephemeral owner và số lượng registration.
- Kết hợp discovery với timeout, retry, circuit breaker và fencing khi nghiệp vụ cần bảo đảm quyền sở hữu.

Session xác định khoảng thời gian ZooKeeper tin rằng client còn hiện diện. Ephemeral znode dùng session đó để biểu diễn sự tồn tại của service instance trong registry. Mất kết nối tạm thời có thể không ảnh hưởng node nếu session còn hiệu lực; session hết hạn sẽ xóa node và buộc client đăng ký lại bằng session mới. Nắm chắc ranh giới này giúp Spring Cloud Zookeeper Discovery phản ánh vòng đời instance chính xác hơn và phục hồi an toàn sau sự cố mạng.
