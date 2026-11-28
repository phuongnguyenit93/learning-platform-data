# Session resumption và ticket trong TLS: hiệu năng, tính an toàn và vận hành

**Session resumption (nối lại phiên TLS)** cho phép client và server tận dụng **trạng thái mật mã được thiết lập từ một lần kết nối TLS trước** để xây dựng một kết nối TLS mới hiệu quả hơn, thay vì luôn bắt đầu toàn bộ quy trình bắt tay như một khách hàng hoàn toàn mới. **Session ticket** là cơ chế phổ biến để server cấp cho client thông tin có thể được trình lại khi nối phiên. Trong **TLS 1.3**, ticket thường gắn với một **resumption pre-shared key (PSK)**; trong TLS 1.2, có cơ chế session ID dựa trên cache phía server và cơ chế session ticket theo thiết kế khác.

Resumption giúp giảm chi phí CPU và thời gian bắt tay, đặc biệt với kết nối có độ trễ mạng lớn, lưu lượng truy cập lặp lại, edge/CDN và dịch vụ nhận nhiều kết nối ngắn. Nhưng việc tái sử dụng trạng thái cũng tạo yêu cầu bảo mật mới: **quản lý vòng đời khóa/ticket, chống replay với 0-RTT, giới hạn phạm vi danh tính và chính sách, bảo vệ quyền riêng tư, xử lý rotation và lỗi đồng bộ giữa các node**.

Bài thuộc chương **TLS và bảo mật kênh truyền** của module **SECURITY_NETWORK_SECURITY**. Trong kiến trúc phòng vệ nhiều lớp gồm firewall, VPN, IDS/IPS, NAC, DNS, Wi-Fi và cloud, TLS bảo vệ dữ liệu **trên từng kết nối được cấu hình**; nối phiên TLS **không** thay việc định tuyến đúng, lọc mạng, xác thực người dùng hoặc kiểm tra quyền ứng dụng.

> **Phạm vi:** bài tập chỉ dùng localhost, dữ liệu mô phỏng và dịch vụ thử nghiệm do người học sở hữu. Không thu thập session tickets của người khác, không thử replay yêu cầu trên dịch vụ không được phép, không tắt certificate validation để chứng minh một lần nối phiên “thành công”. Các đoạn cấu hình mang tên pseudo là mô hình ý định, **không phải** cú pháp triển khai chung cho mọi load balancer, reverse proxy hay thư viện TLS.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **TLS connection**, **TLS session**, **HTTP keep-alive**, **HTTP/2 multiplexing**, **application session cookie** và **TLS session resumption**.
2. Mô tả **session ID/session cache và session ticket trong TLS 1.2**; mô tả **NewSessionTicket và resumption PSK trong TLS 1.3**.
3. Hiểu vai trò của **PSK binder, nonce, ticket identity, ticket lifetime, ticket_age_add và psk_key_exchange_modes** ở mức thiết kế.
4. Phân biệt **1-RTT resumed handshake** với **0-RTT early data**; giải thích tác động của replay, forward secrecy và giới hạn thao tác ứng dụng.
5. Thiết kế **ticket key rotation, phạm vi chia sẻ khóa giữa các node, bảo mật key material, điều kiện hết hạn và fallback full handshake**.
6. Đánh giá rủi ro resumption trong **mTLS, chuyển đổi certificate, SNI/ALPN, reverse proxy, CDN, multi-tenant và dịch vụ cloud**.
7. Xây dựng telemetry, alert, kiểm thử hiệu năng/an toàn và playbook khắc phục các lỗi session cache/ticket.
8. Phân tích kết quả quan sát với OpenSSL/Java ở **môi trường lab được phép**, không nhầm reuse TCP hoặc HTTP session với resumption TLS thật.

## 2. TLS bảo vệ gì và vì sao cần nối phiên?

### 2.1. Một kết nối TLS mới cần những việc gì?

TLS là giao thức bảo vệ **tính bí mật và toàn vẹn** của các bản tin ứng dụng trên một kết nối, đồng thời giúp client **xác thực server** khi certificate/hostname validation được cấu hình đúng. **mTLS** bổ sung xác thực client bằng chứng chỉ hoặc cơ chế thích hợp trong phạm vi handshake. TLS không tự xác thực user của một phiên đăng nhập web và không giải quyết authorization của API.

Với **TLS 1.3 full handshake** thông thường:

1. Client gửi **ClientHello**, đề xuất phiên bản, thuật toán và vật liệu key share.
2. Server trả **ServerHello** và các thông tin tiếp theo theo luồng TLS 1.3, bao gồm xác thực certificate nếu dùng certificate-based authentication.
3. Hai bên dẫn xuất traffic keys, xác minh thông điệp Finished và chuyển sang trao đổi dữ liệu ứng dụng được bảo vệ.

Trong điều kiện không có trường hợp đặc biệt như **HelloRetryRequest**, handshake TLS 1.3 đầy đủ thường cần khoảng **một RTT trước khi client gửi application data bình thường**. Có thể phát triển kết nối TCP hoặc QUIC trước đó tùy vận chuyển, nhưng **không nên đồng nhất RTT của handshake TLS với tổng thời gian tạo kết nối ứng dụng**, vì DNS, TCP, congestion, proxy và xác thực ứng dụng còn chiếm thời gian.

Với TLS 1.2, một full handshake truyền thống có thể cần nhiều vòng đi-về hơn TLS 1.3. Cơ chế nối phiên đã tồn tại trước TLS 1.3 để giảm phần công việc lặp lại này.

### 2.2. Đừng nhầm các khái niệm "phiên"

| Khái niệm | Tầng | Thực tế tái sử dụng | Không đồng nghĩa |
| --- | --- | --- | --- |
| **TCP keep-alive / kết nối TCP tái dùng** | Vận chuyển và ứng dụng | Duy trì một socket/kết nối đang mở | Tạo kết nối TLS mới hoặc nối phiên TLS |
| **HTTP keep-alive, HTTP/2 multiplexing** | HTTP | Nhiều request cùng một kết nối được giữ lại | Phải thực hiện resumption cho mỗi HTTP request |
| **HTTP/3 connection qua QUIC** | QUIC + HTTP/3 | Nhiều stream trong kết nối; hỗ trợ một số cơ chế migration | TLS resumption là một kết nối mới |
| **Full TLS handshake** | TLS | Thiết lập ngữ cảnh mật mã mới mà không dùng trạng thái resumption đã cấp | Giữ kết nối trước đó đang mở |
| **TLS session resumption** | TLS | Dùng trạng thái/PSK từ phiên TLS trước khi tạo kết nối mới | Đăng nhập người dùng ứng dụng |
| **HTTP session cookie** | HTTP/ứng dụng | Duy trì định danh phiên đăng nhập hoặc ngữ cảnh ứng dụng | Session ticket trong TLS |
| **OAuth access/refresh token** | Xác thực/ủy quyền ứng dụng | Truy cập API theo scope, expiry và policy | Quyền tái sử dụng traffic keys TLS |
| **Load-balancer affinity cookie** | Hạ tầng ứng dụng | Gợi ý định tuyến các request tới backend | Bản thân nó là chứng cứ resumption TLS |

Một trình duyệt có thể gửi **100 request HTTP/2 trên cùng kết nối TLS** mà không có lần resumption mới nào. Ngược lại, khi tạo một kết nối TLS mới tới cùng server, client có thể thử trình lại ticket **dù chưa có cookie đăng nhập**.

### 2.3. Resumption giúp giảm gì?

Lợi ích điển hình:

- **Latency:** giảm khối lượng và số round trips của handshake so với đường đầy đủ, tùy phiên bản TLS và cấu hình.
- **CPU:** giảm hoặc tránh một số phép tính/xử lý certificate trong handshake mới.
- **Băng thông:** giảm trao đổi các thông điệp, đặc biệt nếu full certificate chain khá lớn.
- **Khả năng mở rộng:** có thể giảm tải cho edge xử lý nhiều kết nối.
- **Trải nghiệm:** có lợi khi client phải kết nối lại sau thay mạng, timeout hoặc load balancer chuyển hướng.

Nhưng **không phải lúc nào resumption cũng cải thiện đáng kể**: nếu HTTP/2 đã tái dùng kết nối lâu dài, ứng dụng chủ yếu tốn thời gian database, hoặc có DNS/network RTT lớn hơn phần bắt tay TLS, lợi ích tổng thể có thể thấp. Việc tối ưu cần đo **full vs resumed handshake** trên workload thực, không chỉ bật tùy chọn trên server.

## 3. Toàn cảnh TLS 1.2 và TLS 1.3

| Khía cạnh | TLS 1.2 | TLS 1.3 |
| --- | --- | --- |
| Cơ chế nối phiên | Session ID/cache hoặc session ticket (thường gắn RFC 5077) | **PSK resumption** từ NewSessionTicket; session ID legacy không phải cơ chế tái dùng khóa tương đương TLS 1.2 |
| Dữ liệu phía client | Session ID hoặc ticket chứa trạng thái được bảo vệ | PSK identity/ticket và bí mật resumption tương ứng, metadata |
| Trạng thái phía server | Cache theo session ID hoặc khả năng giải mã ticket | Khả năng kiểm tra/giải mã ticket hoặc tìm PSK theo cách triển khai |
| Bắt tay nối phiên | Abbreviated handshake theo TLS 1.2 | Resumed handshake dựa trên PSK, có hoặc không DHE theo mode |
| 0-RTT early data | Không có cơ chế 0-RTT TLS 1.3 tương ứng | Có thể được hỗ trợ nhưng tùy server/client/policy và **có replay risk** |
| Certificate gửi lại trong resumption | Thường không cần full certificate exchange ở abbreviated handshake | Thường không gửi lại certificate theo đường resumption PSK |
| Freshness của secret | Phụ thuộc cơ chế phiên và khóa gốc; cần hiểu giới hạn PFS trong TLS 1.2 | **PSK + (EC)DHE** cung cấp fresh key agreement cho 1-RTT resumed traffic khi dùng mode này |
| Ticket-key management | Bảo vệ khóa mã hóa/xác thực ticket hoặc cache | Bảo vệ khóa ticket/PSK state, rotation và giới hạn reuse |
| Tính tương thích | Có thể bị hạn chế ở hệ cũ/chính sách tắt TLS 1.2 | Phụ thuộc phiên bản OpenSSL/JSSE/proxy và policy TLS 1.3 |

**Không thể suy từ việc thấy một NewSessionTicket rằng phiên TLS tiếp theo chắc chắn sẽ resume**. Client có thể không lưu ticket, server có thể không chấp nhận, scope hoặc policy thay đổi, ticket hết hạn, node khác không giải mã được hoặc client không đề nghị PSK.

## 4. Nối phiên TLS 1.2 bằng session ID và server cache

### 4.1. Mô hình session ID (stateful)

Một server TLS 1.2 có thể lưu **session state** trong cache và cấp **session ID** cho client. Lần kết nối tiếp theo, client gửi session ID cũ trong ClientHello. Nếu server tìm thấy phiên, trạng thái còn hợp lệ và chính sách cho phép, hai bên có thể thực hiện abbreviated handshake.

~~~mermaid
sequenceDiagram
    participant C as TLS 1.2 client
    participant S as TLS 1.2 server
    participant K as Server session cache
    C->>S: Full ClientHello
    S->>K: Lưu session state
    S-->>C: Full handshake + session ID
    Note over C,S: Phiên đầu thiết lập thành công
    C->>S: ClientHello + session ID đã lưu
    S->>K: Tra cứu session ID và policy
    alt Cache hit và phiên hợp lệ
        S-->>C: Abbreviated handshake
        Note over C,S: Kết nối mới dùng trạng thái nối phiên
    else Cache miss / hết hạn / policy không cho
        S-->>C: Full handshake mới
    end
~~~

**Đặc điểm vận hành:**

- Server phải lưu và quản lý **session cache** theo dung lượng, thời gian và phạm vi node.
- Cache miss có thể xảy ra khi server restart, cache eviction hoặc client được load balancer chuyển sang node khác.
- Với cluster, chia sẻ session state có thể tăng hit rate nhưng mở rộng **phạm vi quyền truy cập dữ liệu bí mật và tác động khi cache bị lộ**.
- Một session ID không phải token ứng dụng để cấp quyền API. Server vẫn kiểm tra chứng chỉ, hostname, mTLS/identity, policy được áp dụng và quyền nghiệp vụ theo từng ngữ cảnh.

### 4.2. Cache hit và failover

Giả sử node A có session cache, còn node B không có:

~~~text
Connection 1: client -> Load balancer -> TLS node A
              Full TLS 1.2 handshake; A lưu session X.

Connection 2: client -> Load balancer -> TLS node B
              Client trình session ID X.
              B không biết X -> full handshake nếu cấu hình cho phép.
~~~

**Cache miss không phải mặc định là lỗi bảo mật hoặc outage.** Một triển khai đúng phải có đường **fallback full handshake** khi cache không có entry, thay vì chấp nhận session state sai hoặc tắt xác thực certificate.

### 4.3. Giới hạn bảo mật của phiên cũ

TLS 1.2 session resumption dùng trạng thái bí mật liên quan phiên ban đầu. Không nên tuyên bố rằng **mỗi lần abbreviated handshake đều tạo fresh (EC)DHE độc lập**. Mức forward secrecy và hậu quả lộ trạng thái phụ thuộc full handshake ban đầu, thuật toán, cách lưu master secret/cache/ticket và thời gian bí mật còn được sử dụng. Đó là một lý do cần giới hạn lifetime và tắt các giao thức/cipher lỗi thời khi chuẩn hóa TLS.

## 5. Session ticket trong TLS 1.2

### 5.1. Từ cache tập trung sang ticket do client giữ

Trong mô hình **TLS 1.2 session ticket**, server tạo một **opaque ticket** cho client; ticket thường chứa session state đã được server **mã hóa và bảo vệ tính toàn vẹn** bằng khóa quản lý phía server. Client giữ ticket và trình lại khi tạo kết nối khác. Server nhận ticket, kiểm tra/giải mã bằng khóa thích hợp, rồi quyết định có nối phiên hay không.

~~~mermaid
sequenceDiagram
    participant C as TLS 1.2 client
    participant A as TLS server A
    participant B as TLS server B
    participant K as Ticket protection keys
    C->>A: Full ClientHello
    A->>K: Dùng khóa bảo vệ ticket
    A-->>C: Full handshake + NewSessionTicket
    Note over C,A: Client lưu opaque ticket và session state phù hợp
    C->>B: New ClientHello + ticket đã nhận
    B->>K: Tra/giải mã ticket bằng khóa được cấp cho B
    alt Ticket hợp lệ và policy cho phép
        B-->>C: Abbreviated handshake
    else Không giải được / hết hạn / thay policy
        B-->>C: Full handshake bình thường
    end
~~~

**Ưu điểm:** node xử lý kết nối có thể khôi phục session state mà không phải luôn tra cache tập trung, nếu nó có khóa/điều kiện phù hợp. **Đánh đổi:** bảo vệ và vòng đời **ticket encryption/protection keys** trở thành yêu cầu an ninh cốt lõi; để tiện tải, chia sẻ cùng khóa ticket cho quá nhiều dịch vụ có thể làm tăng phạm vi rủi ro.

### 5.2. Ticket chứa gì?

Ticket là **opaque blob đối với client**. Không nên giả định nó là JSON/JWT, và ứng dụng **không cần đọc hoặc giải mã ticket** để tiếp tục sử dụng TLS. Tùy thư viện hoặc sản phẩm, phần server có thể bảo vệ session parameters, secret và metadata cần thiết cho nối phiên; cấu trúc cụ thể không thống nhất giữa mọi hệ thống.

Ba loại thông tin cần phân biệt:

| Thông tin | Vai trò | Ai được quyền xử lý? |
| --- | --- | --- |
| **Session ID** | Khóa tra trạng thái session cache trong TLS 1.2 stateful mode | Client giữ ID, server kiểm soát entry |
| **Opaque TLS ticket** | Đại diện trạng thái nối phiên được server bảo vệ | Client lưu/trình lại; TLS stack server kiểm tra/giải mã |
| **Ticket protection key** | Khóa mã hóa/xác thực ticket hoặc các state cần bảo vệ | **Chỉ hệ thống TLS termination được cấp quyền**; không đưa cho client hay vào log |

Một session ticket **không phải cookie đăng nhập**, không phải access token gửi qua HTTP và không nên được lưu nguyên văn trong SIEM/ticket vận hành. Client và server vẫn có thể có cookie ứng dụng riêng ở **bên trong traffic TLS được mã hóa**.

### 5.3. Hạn sử dụng và thay đổi khóa

Ticket có thể có **lifetime hint** hoặc hạn mức do server/client policy quyết định. Hint **không phải cam kết** server sẽ chấp nhận ticket tới tận ngày đó. Khi server xoay khóa, thay policy, vô hiệu trạng thái, nâng phiên bản TLS hoặc chuyển tới node không có khóa phù hợp, nó có thể từ chối ticket và thực hiện full handshake.

**Một lần full handshake sau rotation thường là hành vi chấp nhận được**, không phải lý do kéo dài tuổi khóa ticket vô hạn. Cần tránh cách xử lý nguy hiểm như: **không giải được ticket → chấp nhận mà không xác minh hoặc bỏ qua certificate checks**.

### 5.4. Ảnh hưởng khi lộ khóa ticket TLS 1.2

Tùy cách triển khai và trạng thái được mã hóa, **lộ ticket protection key** cùng các ticket đã thu thập có thể khiến dữ liệu session secret bị khôi phục, tạo rủi ro cho traffic sử dụng trạng thái đó. Vì vậy, TLS 1.2 session ticket có **hệ quả forward-secrecy cần được phân tích riêng**, kể cả khi full handshake ban đầu dùng (EC)DHE. Không coi việc có ECDHE trong full handshake là đủ để bỏ qua quản lý khóa ticket dài hạn.

Phòng vệ gồm hạn chế quyền vào key material, rotate định kỳ, quản lý ticket lifetime, theo dõi xuất/đọc khóa và xem xét tắt ticket nếu nền tảng không thể bảo vệ hoặc kiểm soát rotation phù hợp. Cách vô hiệu hóa, chia sẻ và rotation tùy thư viện/edge provider.

## 6. TLS 1.3: NewSessionTicket và resumption PSK

### 6.1. Điểm khác biệt nền tảng

Trong **TLS 1.3**, nối phiên dựa trên **PSK (pre-shared key)** chứ không dựa vào TLS 1.2 master-secret/session-ID semantics. Sau handshake ban đầu, server có thể gửi **một hoặc nhiều NewSessionTicket messages** được bảo vệ bên trong kênh TLS đã thiết lập. Client nhận ticket, lưu trạng thái phù hợp và dùng một **ticket identity cùng PSK liên quan** ở kết nối sau.

**PSK không phải khóa bị truyền nguyên dạng qua mạng.** Trong thiết kế resumption TLS 1.3, các bên dẫn xuất PSK theo cơ chế trong giao thức dựa trên resumption state, ví dụ resumption master secret và nonce duy nhất theo ticket. Client giữ phần trạng thái bí mật cần thiết; server phải có khả năng phục hồi hoặc tra cứu PSK theo ticket identity.

### 6.2. Chuỗi full handshake rồi resumed handshake

~~~mermaid
sequenceDiagram
    participant C as TLS 1.3 client
    participant S as TLS 1.3 edge server
    participant K as Ticket / PSK state
    Note over C,S: Kết nối đầu tiên
    C->>S: ClientHello + key_share
    S-->>C: ServerHello + key_share
    S-->>C: EncryptedExtensions, Certificate, Verify, Finished
    C->>S: Finished
    Note over C,S: Application traffic bảo vệ bằng TLS
    S->>K: Tạo thông tin cho resumption
    S-->>C: Encrypted NewSessionTicket
    Note over C,S: Client lưu ticket identity và PSK state
    Note over C,S: Kết nối mới, có thể tới node khác
    C->>S: ClientHello + pre_shared_key + binder + key_share
    S->>K: Kiểm tra ticket, PSK, tuổi và policy
    alt PSK hợp lệ và chọn psk_dhe_ke
        S-->>C: ServerHello + key_share + PSK selected
        S-->>C: EncryptedExtensions + Finished
        C->>S: Finished
        Note over C,S: Resumed 1-RTT traffic với fresh DHE
    else Không chấp nhận resumption
        S-->>C: Full TLS handshake khi điều kiện cho phép
    end
~~~

Sơ đồ là **dòng khái niệm**, không hiển thị mọi extension, key schedule và các trường hợp như HelloRetryRequest, certificate request hay nhiều ticket. Thông điệp NewSessionTicket **đến sau** khi kết nối đầu đã được thiết lập và được bảo vệ; không nên trông chờ nhìn thấy plaintext ticket trong packet capture TLS 1.3 khi không có quyền giải mã.

### 6.3. Những trường TLS 1.3 liên quan

| Thành phần | Ý nghĩa | Lưu ý khi thiết kế |
| --- | --- | --- |
| **NewSessionTicket.ticket** | Opaque identity client có thể trình lại | Không gửi ticket vào URL, cookie, log hoặc header ứng dụng |
| **ticket_lifetime** | Tuổi tối đa được server công bố để client biết lúc nào nên thử resumption | TLS 1.3 quy định giá trị trong khoảng hợp lệ và không lớn hơn **7 ngày**; triển khai có thể chọn thấp hơn rất nhiều |
| **ticket_age_add** | Giá trị dùng để che tuổi ticket trong thông tin ClientHello | Không phải biện pháp chống replay hoàn chỉnh |
| **ticket_nonce** | Phần tử nonce để dẫn xuất PSK riêng cho từng ticket theo key schedule | Không tự tương đương anti-replay database |
| **ticket identity / obfuscated age** | Được client trình cùng proposed PSK ở lần sau | Không được coi là chứng cứ danh tính người dùng |
| **pre_shared_key extension** | Mang các identity đề xuất và binder tương ứng trong ClientHello | TLS stack xác minh binder khi chọn PSK |
| **psk_key_exchange_modes** | Cho biết client hỗ trợ mode PSK nào | Nên hiểu khác biệt **psk_dhe_ke** với **psk_ke** |
| **early_data extension** | Thể hiện khả năng hoặc thử dùng 0-RTT trong phạm vi được hỗ trợ | Chỉ bật với application policy chống replay đã được đánh giá |
| **NewSessionTicket extensions** | Có thể quảng bá **early_data max_early_data_size** khi server cho phép | Ticket tồn tại không có nghĩa server chấp nhận 0-RTT |

**Không giả định TTL của session ticket bằng thời hạn certificate, cookie, JWT hoặc phiên đăng nhập.** Chúng có lifecycle khác nhau và cần policy riêng.

### 6.4. PSK binder xác nhận điều gì?

Khi client đề xuất resumption PSK, **PSK binder** được tính từ vật liệu bí mật liên quan PSK và nội dung ClientHello theo cách giao thức định nghĩa. Nó giúp server phát hiện một client **không sở hữu đúng PSK** hoặc ClientHello bị thay đổi không hợp lệ trong phạm vi được binder bảo vệ.

Nhưng binder **không biến một ticket thành giấy phép truy cập tài nguyên**. Nó không thay:

- Kiểm tra điều kiện ticket còn hiệu lực và thuộc context mong đợi.
- Xác minh hostname/peer/certificate theo mô hình client đã được dùng và cache hợp lệ.
- Kiểm soát TLS version, cipher/hash, SNI/ALPN, network policy và trạng thái mTLS khi cần.
- Đăng nhập/authorization của người dùng ở tầng HTTP/API.

**Ticket bị lộ như chuỗi bytes** không nhất thiết đủ để tự nối phiên TLS 1.3 nếu bên thứ ba không có PSK tương ứng, nhưng **lộ cả PSK hoặc state bí mật** là vấn đề nghiêm trọng. Vì vậy cần bảo vệ cả ticket identity và session secret trong TLS client cache/server keys.

### 6.5. Một server có thể cấp nhiều ticket

TLS 1.3 có thể phát **nhiều NewSessionTicket** sau một handshake. Điều này giúp client có nhiều lựa chọn cho các kết nối tiếp theo hoặc chính sách single-use/short-lived tickets khi được hỗ trợ. Không mặc định:

- Một ticket chỉ được dùng được đúng một lần trên mọi sản phẩm.
- Một client chỉ lưu đúng một ticket cho một hostname.
- Có nhiều ticket đồng nghĩa mọi ticket có thể được sử dụng để gửi 0-RTT.
- Client bắt buộc phải thử resumption ở mọi kết nối.

Khả năng tái sử dụng, loại bỏ ticket, giám sát replay và giới hạn parallel connections là **quyết định của TLS stack và triển khai** cần kiểm chứng bằng test.

## 7. PSK-only so với PSK + (EC)DHE: Forward secrecy

### 7.1. Hai mode quan trọng

**TLS 1.3** hỗ trợ các mode trao đổi khóa cho PSK:

- **psk_ke:** dùng PSK mà không thực hiện trao đổi (EC)DHE mới trong handshake nối phiên. Bí mật bảo vệ phiên mới phụ thuộc PSK và key schedule, **không có fresh DHE forward secrecy** cho resumed 1-RTT data.
- **psk_dhe_ke:** dùng PSK **kết hợp với (EC)DHE mới**, nhờ đó 1-RTT traffic của kết nối nối phiên có **forward secrecy từ phần DHE mới** khi triển khai đúng.

| Đặc điểm | PSK-only (psk_ke) | PSK + DHE (psk_dhe_ke) |
| --- | --- | --- |
| Cần key share mới cho resumed handshake | Không | Có |
| Bổ sung tính bí mật về sau từ fresh ephemeral DHE | Không | Có đối với 1-RTT resumed traffic theo mô hình TLS 1.3 |
| Khả năng chống tác động của việc lộ PSK **sau này** đối với 1-RTT data đã ghi | Yếu hơn | Tốt hơn nhờ DHE nếu ephemeral secrets được xử lý đúng |
| Chi phí tính toán | Có thể thấp hơn | Có thêm chi phí DHE |
| Đề xuất chung | Chỉ dùng khi có lý do rõ và risk review | **Ưu tiên nếu hỗ trợ** cho kết nối nối phiên có yêu cầu bảo mật |

Không nhầm forward secrecy của **resumed 1-RTT traffic** với dữ liệu **0-RTT early data**. Dữ liệu 0-RTT được dẫn xuất từ PSK trước khi có kết quả fresh DHE của handshake mới và **không có forward secrecy từ DHE mới**.

### 7.2. Khi nào resumption không được chấp nhận?

Ngay cả khi client có ticket và server hỗ trợ mode PSK tương ứng, server vẫn có thể từ chối nối phiên vì:

1. Ticket quá hạn, bị hủy hoặc server không giải mã/tra được.
2. Node mới không có khóa ticket hoặc cache state liên quan.
3. TLS version, hash/cipher constraints, PSK mode hoặc chính sách handshake không tương thích.
4. Thay SNI, application protocol qua ALPN, tenant hoặc mục đích sử dụng không cho phép reuse.
5. Thay chính sách xác thực, trạng thái client certificate hoặc quyền truy cập cần bắt buộc fresh authentication.
6. Ticket/PSK bị đánh dấu không dùng được, không đáp ứng anti-replay policy hoặc bị từ chối theo server configuration.
7. Client không gửi PSK identity, không lưu ticket hoặc tự bỏ ticket vì privacy/session handling.

**Fallback về full handshake là hành vi bình thường** khi đáp ứng các điều kiện tương thích. Không hạ TLS version, bỏ xác thực certificate hoặc mở rộng resumption scope chỉ để nâng "hit rate".

## 8. 0-RTT early data: nhanh hơn nhưng phải tính đến replay

### 8.1. 1-RTT và 0-RTT không phải hai tên gọi của resumption giống nhau

TLS 1.3 cho phép nối phiên với handshake **1-RTT**; server/client vẫn hoàn tất xác nhận các thông điệp handshake mới trước khi xử lý application data theo luồng thông thường. **TLS 1.3 full handshake và resumed 1-RTT handshake đều thường cần khoảng một RTT**, vì vậy lợi ích rõ ràng của nối phiên 1-RTT là **giảm xử lý và dữ liệu handshake**, không phải luôn giảm một RTT so với TLS 1.3 full handshake.

**0-RTT (early data)** là khả năng **client gửi một số application data ngay trong lần gửi đầu tiên** của kết nối nối phiên, dựa trên PSK đã có. Client không phải đợi nhận ServerHello trước khi gửi early data, nhưng **server có quyền chấp nhận hoặc từ chối** dữ liệu này. Một số handshake có thể resume nhưng **không dùng 0-RTT**.

~~~mermaid
sequenceDiagram
    participant C as Client đã giữ TLS 1.3 PSK
    participant S as Server / TLS terminator
    C->>S: ClientHello + PSK identity + binder + early_data
    C->>S: Encrypted early application data (0-RTT)
    Note over C,S: Early data đã đến trước xác nhận handshake mới
    alt Server cho phép và chính sách anti-replay đạt
        S-->>C: ServerHello + PSK selection, handshake data
        S-->>C: Xác nhận early_data accepted theo giao thức
        C->>S: Hoàn tất handshake (khi thích hợp)
        Note over C,S: Phần application data tiếp theo dùng 1-RTT keys
    else Server không chấp nhận early data
        S-->>C: Handshake tiếp tục, early_data rejected
        Note over C,S: Client cần gửi lại nếu phù hợp, sau handshake
    end
~~~

Sơ đồ lược bỏ các thông điệp chi tiết và xử lý EndOfEarlyData/Finished. **Không được tự động phát lại một thao tác có tác dụng phụ nếu early data bị từ chối**; logic retry phải biết loại request, tình trạng phía server và yêu cầu idempotency của ứng dụng.

### 8.2. Nguy cơ replay

Một đối tượng có khả năng ghi và gửi lại một bản early-data hợp lệ trong một số điều kiện có thể khiến hệ thống **xử lý lại cùng dữ liệu**. Mức bảo vệ, cửa sổ replay và việc phối hợp giữa các node tùy triển khai. TLS 1.3 **không cam kết 0-RTT có tính chống replay như application data sau handshake**.

Ví dụ sai:

~~~text
POST /v1/payments/transfer
Body: {"amount":100,"to":"recipient-xyz"}

Nếu hệ thống xử lý request này trong 0-RTT và không kiểm soát
idempotency/replay, bản request được phát lại có nguy cơ gây
thêm một lần chuyển tiền hoặc tạo hành vi trùng.
~~~

Ngay cả các method HTTP thường được coi là "safe", như GET, **cũng có thể có tác dụng phụ trong một ứng dụng viết sai** (ghi audit counter, tạo resource, kích hoạt email, thay trạng thái gián tiếp). Vì vậy, điều kiện cho 0-RTT phải dựa trên **ngữ nghĩa nghiệp vụ đã đánh giá và kiểm thử**, không dựa một cách máy móc vào tên HTTP method.

### 8.3. Các thao tác nên mặc định không xử lý bằng 0-RTT

| Nhóm nghiệp vụ | Ví dụ | Rủi ro khi replay |
| --- | --- | --- |
| Thanh toán, chuyển tiền | Tạo đơn thanh toán, chuyển tiền, hoàn tiền | Giao dịch trùng hoặc thay đổi trạng thái sai |
| Danh tính và quyền | Đăng nhập, logout, cấp token, đổi mật khẩu, cập nhật MFA | Thao tác trái ngữ cảnh, ghi đè/đảo trạng thái |
| Thay đổi dữ liệu | Ghi đơn hàng, cập nhật hồ sơ, xóa tài nguyên | Tạo hoặc thay đổi nhiều lần |
| Điều khiển hệ thống | Deploy, restart, scale, xóa cache, mở quyền | Có thể tác động availability hoặc bảo mật |
| Webhook và xử lý sự kiện | Xử lý event từ đối tác, gửi email, mở ticket | Event bị xử lý trùng, gây race condition |
| Truy vấn nhạy cảm | Truy vấn thông tin cá nhân hoặc dữ liệu trả phí | Rủi ro về authorization/session state và ngữ nghĩa xử lý |
| API dùng nonce/time-sensitive | Kích hoạt thao tác theo thời gian, OTP hoặc replay window | Logic xác thực dễ bị diễn giải sai khi resumption/retry |

**Khuyến nghị mặc định:** để 0-RTT **tắt** cho ứng dụng có trạng thái hoặc dữ liệu nhạy cảm trừ khi có thiết kế application-layer anti-replay rõ ràng. Nối phiên TLS 1.3 **không cần bật 0-RTT** mới hoạt động.

### 8.4. Các lớp giảm replay nếu thật sự cần 0-RTT

Khi một endpoint được phép xử lý early data, cân nhắc:

1. **Chỉ chấp nhận tác vụ read-only thực sự** theo định nghĩa nghiệp vụ, kiểm tra cả side effects gián tiếp.
2. **Giới hạn 0-RTT theo route, method, identity và trạng thái xác thực**, thay vì bật tất cả API ở edge.
3. **Replay cache / anti-replay state** với key, TTL và phạm vi phù hợp; ở cluster đa vùng phải hiểu giới hạn đồng bộ và race conditions.
4. **Idempotency key** ở tầng ứng dụng cho thao tác có khả năng lặp khi thiết kế cho phép, lưu kết quả trước khi cho xử lý lần nữa. Đây là bổ trợ, **không làm 0-RTT tuyệt đối chống replay**.
5. **Đánh dấu request là early data** ở thành phần đáng tin, bảo đảm reverse proxy/backend từ chối hoặc xử lý riêng theo policy (ví dụ 425 Too Early trong HTTP nếu phù hợp).
6. **Đánh giá TLS terminator và backend**: nếu proxy chấp nhận early data rồi chuyển tới backend unaware, backend có thể xử lý hành động có tác dụng phụ.
7. **Giám sát** early_data accepted/rejected, replay suspicion, idempotency conflicts, duplicate transaction và ticket key rotation.

**425 Too Early** có thể được server dùng để biểu thị không sẵn sàng xử lý request trong early data. Nhưng một client/proxy không nhất thiết tự retry chính xác; hệ thống phải được kiểm tra để tránh **double execution** khi retry có xảy ra.

### 8.5. Anti-replay ở nhiều edge nodes khó hơn trên một server

Giả sử cùng ticket được trình ở hai edge nodes gần như đồng thời:

~~~text
Client / duplicated early request
        |                          |
        v                          v
Edge A (region A)            Edge B (region B)
        |                          |
Anti-replay state A          Anti-replay state B
        |                          |
Backend payment/order service (shared)
~~~

Nếu A và B có trạng thái anti-replay **không đồng bộ**, mỗi bên có thể coi bản request là lần đầu. Nếu cần chống replay theo phân vùng toàn hệ thống, phải xem **tính nhất quán, chi phí đồng bộ và lỗi mạng**; không thể chỉ cài timeout cache cục bộ rồi tuyên bố "0-RTT đã chống replay hoàn toàn".

### 8.6. Tính riêng tư, forward secrecy và dữ liệu đầu phiên

Early data TLS 1.3 **được mã hóa**, nhưng key schedule dựa trên **PSK từ phiên trước** và **không có forward secrecy mới từ (EC)DHE của kết nối đang bắt đầu**. Nếu trạng thái PSK bị lộ trong các điều kiện phù hợp, rủi ro đối với early data đã ghi phải được xem xét. Ngay cả khi resumed 1-RTT về sau dùng psk_dhe_ke, **điều đó không hồi tố bảo vệ forward secrecy cho 0-RTT đã gửi**.

Resumption identifiers có thể liên kết nhiều kết nối nếu được tái sử dụng/quan sát. Ticket rotation, session scope và hành vi client có tác động tới quyền riêng tư, bên cạnh mục tiêu giảm latency.

## 9. Ticket-key management và vòng đời PSK

### 9.1. Hai loại bí mật khác nhau

Trong triển khai thực, cần phân biệt:

1. **Ticket protection key / server-side resumption secrets:** khóa dùng để bảo vệ ticket hoặc khôi phục/tra PSK; do TLS termination infrastructure quản lý.
2. **Resumption PSK/session state của client:** bí mật được TLS client stack lưu cho cơ chế nối phiên, không được đưa vào log/HTTP.
3. **Ephemeral (EC)DHE secret:** chỉ dùng ở handshake phù hợp, cần được hủy đúng lúc để đạt tính chất forward secrecy.
4. **Application access token/cookie:** quyền ứng dụng ở tầng HTTP, có vòng đời và policy riêng, không chia sẻ với secret TLS.

**Rotation ticket key** không đồng nghĩa tự động thay certificate private key hoặc xóa user sessions. Cần có kế hoạch riêng cho từng khóa và loại bí mật, đồng thời xem sự phụ thuộc giữa chúng khi sự cố xảy ra.

### 9.2. Chu kỳ rotation có cửa sổ tương thích

Mô hình gợi ý:

~~~text
Giai đoạn A:
  Key K1 = current, dùng để tạo ticket và kiểm tra ticket cũ.

Giai đoạn B:
  Key K2 = current, tạo ticket mới.
  Key K1 = previous, chỉ kiểm tra ticket đang còn hạn.

Giai đoạn C:
  Key K2 = current, tiếp tục phục vụ.
  K1 hết hạn/được hủy theo policy.

Khi không thể dùng K1/K2 để resume:
  Server từ chối ticket và dùng full handshake an toàn.
~~~

Lịch rotation **không có một con số áp dụng cho mọi tổ chức**. Phải dựa vào ticket lifetime, mức nhạy cảm dịch vụ, khả năng vận hành, phạm vi key sharing, chiến lược cluster và chính sách ứng cứu. Ticket được quảng bá có lifetime dài không bắt buộc server phải giữ khóa cũ dài bằng giá trị đó nếu chủ đích cho phép cache miss.

### 9.3. Phân phối khóa giữa nhiều node

| Thiết kế | Lợi ích | Rủi ro / đánh đổi |
| --- | --- | --- |
| Mỗi TLS node có key riêng | Giới hạn phạm vi compromise giữa node | Resumption giảm khi load balancer chuyển node; rotation dễ tạo miss |
| Cùng key giữa các node của một service | Resumption thuận tiện khi chuyển node | Lộ key một node có thể ảnh hưởng mọi node chia sẻ; cần phân quyền và rotation đồng bộ |
| Key riêng theo tenant/hostname | Giảm nguy cơ dùng nhầm ticket qua context | Quản trị phức tạp; cần đảm bảo không lẫn routing/config |
| Cluster có key distributor bảo vệ | Quản lý version và rollout tập trung | Hệ phân phối khóa trở thành tài sản nhạy cảm và điểm phụ thuộc |
| Server-side state / cache khi hỗ trợ | Kiểm soát invalidation theo state | Cache cần HA, giới hạn bộ nhớ, quyền truy cập và data lifecycle |

**Load balancing không nhất thiết phải sticky sessions để TLS resumption hoạt động**, nếu ticket có thể được xử lý trên các node phù hợp. Ngược lại, sticky sessions không bảo đảm 100% resumption vì ticket có thể hết hạn hoặc bị từ chối theo policy.

### 9.4. Bảo vệ key material

- Lưu/đọc khóa qua **secret management/KMS/HSM** hoặc cơ chế phù hợp của nền tảng khi công nghệ hỗ trợ, với quyền tối thiểu và audit.
- Không commit ticket keys, PSK, TLS key logs, session cache dumps hoặc file session thật vào source repository.
- Không ghi **raw ticket, binder secret, session PSK** vào SIEM, request logs hoặc issue tracker.
- Khi phân phối khóa, dùng kênh được xác thực/mã hóa và giới hạn node/tenant được phép.
- Có cơ chế xác định **key version, activated/retired time, affected service nodes** mà không lộ bytes khóa.
- Khi nghi lộ khóa, đánh giá các ticket đã cấp, PSK/client state, tác động tới full/resumed connections và yêu cầu rotation/fallback.
- Xóa khóa cũ theo policy; không giữ mọi key đời trước vô thời hạn chỉ để tối đa hit rate.

**Tách ưu tiên an toàn và hiệu năng:** nếu không thể bảo vệ khóa ticket trong một nhóm node, giảm resumption hit rate hoặc tắt ticket có thể chấp nhận hơn chia sẻ khóa với toàn bộ workload không được tin cậy.

### 9.5. Ticket lifetime và phạm vi resumption

Ticket nên được ràng buộc hoặc kiểm tra phù hợp với:

- TLS phiên bản và các thuật toán được chấp thuận.
- Hostname/SNI và **đúng dịch vụ hoặc security context**.
- ALPN hoặc application protocol được phép.
- Tenant, environment (dev/staging/prod) và ranh giới quản lý.
- Chính sách client authentication/mTLS/credential state nếu dùng.
- Ticket issue time, effective expiration, key version và mục đích dùng 0-RTT hay 1-RTT.

**Không mặc định mọi trường trên nằm trong một chuẩn ticket chung**: một số là metadata/điều kiện do TLS stack hoặc ứng dụng kiểm tra; hiệu lực của chúng cần xác nhận theo triển khai. Tránh mở khả năng resume từ **staging sang production** hoặc từ một tenant sang tenant khác chỉ vì chia sẻ khóa và endpoint có cùng reverse proxy.

### 9.6. Khả năng thu hồi khẩn cấp

Một sự cố bảo mật có thể yêu cầu:

1. Chặn issuance ticket mới hoặc thay key version theo khả năng hệ thống.
2. Không chấp nhận những ticket/PSK liên quan phạm vi bị ảnh hưởng.
3. Yêu cầu full handshake với certificate/mTLS policy đang có.
4. Thu hồi/rotate credential ứng dụng **riêng**, nếu có dấu hiệu liên quan identity/access token.
5. Xác minh mọi node/region đã nhận cấu hình và không phục vụ key cũ ngoài policy.
6. Đo tăng CPU, latency, handshake failures trong giai đoạn chuyển sang full handshake.

Một số ticket **stateless** không thể bị vô hiệu từng cái nếu không có denylist/state bổ trợ; rotation key có thể vô hiệu **một nhóm ticket**, gây cache miss hàng loạt. Đây là một trade-off an toàn cần được tính khi thiết kế hệ thống lớn.

## 10. mTLS, certificate changes và ngữ cảnh authorization

### 10.1. Xác thực server khi nối phiên

Trong full TLS handshake dựa trên certificate, client phải kiểm tra **chuỗi tin cậy, thời hạn, hostname (SAN), mục đích chứng chỉ và các chính sách xác thực có hiệu lực** theo thư viện/nền tảng. Với TLS 1.3 resumption PSK, lần nối phiên thường **không gửi lại toàn bộ server certificate**, vì nó dựa trên ngữ cảnh đã được thiết lập trước đó.

Điều này có hai hệ quả:

1. **Không được cấp resumption state từ kết nối không được xác thực đúng.** Nếu client trước đó đã tắt kiểm tra certificate/hostname, reuse PSK không sửa được lỗ hổng xác thực gốc.
2. **Không được coi thành công resumption là đã đánh giá lại certificate hiện tại của server.** Khi server certificate, hostname, trust anchor, tenant hoặc chính sách thay đổi, TLS stack/ứng dụng cần có cơ chế buộc full handshake hoặc từ chối ticket khi bối cảnh cũ không còn phù hợp.

Một server certificate thay đổi **không mặc định làm mọi ticket ngay lập tức vô hiệu trong mọi sản phẩm**; hành vi phụ thuộc policy và TLS implementation. Cần kiểm thử đúng khi rotation certificate, đổi CA, ngừng hỗ trợ ciphers/protocols hoặc chuyển dịch vụ.

### 10.2. mTLS và nối phiên của client đã xác thực

**Mutual TLS** dùng certificate của cả server và client theo chính sách hệ thống. Khi resumption được chấp nhận, một số triển khai có thể **tái sử dụng ngữ cảnh xác thực client từ phiên trước** mà không yêu cầu client trình chứng chỉ mới trong resumed handshake.

Điều cần đánh giá:

| Sự kiện thay đổi | Nguy cơ nếu dựa hoàn toàn vào resumption cũ | Kiểm soát |
| --- | --- | --- |
| Client certificate bị thu hồi | Một ticket đã cấp có thể tiếp tục được chấp nhận theo policy cũ | Giới hạn resumption lifetime, ràng buộc authentication context, cơ chế invalidation |
| Client mất quyền vào dịch vụ | TLS kết nối được nhưng user/service account không còn được phép | Re-evaluate authorization tại ứng dụng, API gateway hoặc policy engine |
| Server đổi trusted client CA | Session cũ có thể không được đánh giá theo trust set mới | Buộc full handshake hoặc version chính sách trong resumption context |
| Workload chuyển tenant/namespace | Resumption nhầm sang context khác nếu khóa chia sẻ quá rộng | Tách key scope, kiểm tra tenant/SNI/identity |
| Certificate hết hạn giữa hai lần kết nối | Resumed handshake không nhất thiết gửi lại certificate | Xác định giới hạn phiên và kiểm tra trạng thái theo policy |
| Xác thực client được nâng mức yêu cầu | Ticket cũ từ phiên không đủ xác thực có thể không phù hợp | Không chấp nhận session cũ cho endpoint cần re-authentication |

**Không dùng kết luận "mTLS lần trước đã OK" để bỏ kiểm tra authorization mỗi request**. Resumption bảo vệ hiệu quả của handshake; IAM/role/revocation và quyền nghiệp vụ cần được kiểm soát độc lập.

### 10.3. Step-up authentication và hành vi bắt buộc fresh handshake

Một số tác vụ như truy cập secrets, điều khiển hạ tầng, thay đổi chính sách firewall hoặc quyền sản xuất cần **fresh authentication** hoặc xác thực nhiều yếu tố ở tầng ứng dụng. Nếu chính sách quy định certificate/client attestation phải được kiểm tra lại, kiến trúc cần **giới hạn resumption/loại bỏ ticket liên quan** hoặc yêu cầu cơ chế xác thực mới thực sự có khả năng kiểm chứng.

**TLS 1.3 post-handshake authentication** tồn tại trong đặc tả với những điều kiện hỗ trợ nhất định, nhưng **không phải sản phẩm/ngôn ngữ nào cũng triển khai hoặc hỗ trợ giống nhau**. Không dựa vào nó như một biện pháp mặc định khi chưa xác minh nền tảng.

### 10.4. Resumption, hostname và HTTP origin

Một TLS kết nối có thể phục vụ HTTP requests với các authority/origin khác nhau theo những quy tắc riêng của HTTP, certificate, kết nối được tái sử dụng và client/proxy. Điều đó **không cho phép một TLS ticket từ hostname/tenant A trở thành chứng cứ đăng nhập của hostname/tenant B**.

Khi dùng SNI-based virtual hosts:

- Kiểm tra ticket được chấp nhận trong **đúng resumption scope** mà dịch vụ chủ ý cho phép.
- Không giả định SNI trong ClientHello là danh tính người dùng đáng tin.
- Không cho một ticket của **dịch vụ staging** được chấp nhận ở production chỉ vì host cùng cấp dưới một load balancer.
- Xem **ALPN, TLS cipher/hash và application protocol** khi xét resumption và đặc biệt 0-RTT.
- Duy trì kiểm tra HTTP Host/authority và authorization tại application gateway; TLS và HTTP có các lớp danh tính khác nhau.

## 11. Kiến trúc nhiều điểm kết thúc TLS: proxy, CDN, service mesh và QUIC

### 11.1. Một request có thể đi qua nhiều kết nối TLS độc lập

~~~mermaid
flowchart LR
    U["Browser / mobile client"] -->|"TLS A\nTicket/PSK set A"| E["CDN / WAF / edge"]
    E -->|"TLS B\nResumption state B"| P["Reverse proxy / gateway"]
    P -->|"TLS C hoặc mTLS\nResumption state C"| S["App service"]
    S -->|"TLS D nếu thiết kế"| DB[("Database")]
    E -. "Edge event" .-> SIEM[("SIEM")]
    P -. "Proxy event" .-> SIEM
    S -. "App / auth event" .-> SIEM
~~~

Trong sơ đồ, **TLS A, B, C, D là các kết nối riêng** với peer, khóa, certificate, policy và ticket context riêng. Ticket TLS A do edge cấp **không tự nối phiên TLS B** giữa edge và reverse proxy. Việc bật resumption tại edge không chứng minh origin traffic được mã hóa, hoặc backend đã xác thực peer đúng.

Nếu một tổ chức dùng TLS termination tại CDN/WAF, cần giám sát độc lập:

- TLS client → CDN/WAF: certificate public, resumption hit rate và policy 0-RTT.
- TLS CDN/WAF → origin: certificate/SNI verification, mTLS/origin access restrictions, resumption nếu có.
- TLS internal proxy → backend: service identity, TLS policy và east–west network segmentation.

**Origin bypass** vẫn là một vấn đề riêng: nếu origin public IP có thể truy cập trực tiếp, khách có thể không đi qua CDN/WAF ngay cả khi tuyến chính bật session tickets. Firewall/ACL, identity và trust headers phải được cấu hình theo ranh giới tin cậy.

### 11.2. Session resumption ở edge và multi-region

Các edge thường nhận nhiều kết nối ngắn từ mobile/browsers, nhưng resumption state không nhất thiết được chia sẻ xuyên tất cả khu vực:

| Tình huống | Hiện tượng | Hướng thiết kế |
| --- | --- | --- |
| Client trở lại cùng edge node | Ticket được chấp nhận nếu còn hạn/policy | Đo hit rate và security controls |
| Client sang edge node khác cùng cụm | Full handshake nếu không có key/cached PSK phù hợp | Chọn scope chia sẻ key theo risk review |
| Client sang vùng địa lý khác | Resumption hit rate có thể giảm | Không chia sẻ ticket keys toàn cầu chỉ vì tối ưu hit rate |
| Triển khai TLS server version mới | Một số ticket cũ có thể bị từ chối | Có fallback full handshake và theo dõi errors |
| Rotation key không đồng bộ | Một số node resume, số khác full handshake | Theo dõi key version, rollout order, cache misses |
| Failover origin | TLS B/C có thể tạo kết nối mới | Kiểm tra origin certificate, mTLS và ticket state riêng |

Nếu các vùng chia sẻ ticket keys, phạm vi compromise của key cũng mở rộng. Nếu không chia sẻ, hiệu năng handshake có thể tăng tải sau failover. **Quyết định đúng** phụ thuộc mức rủi ro, SLO, khả năng scale và mô hình quản trị bí mật của hệ thống.

### 11.3. HTTP/2, connection pooling và resumption

HTTP/2 multiplexing cho phép nhiều stream cùng dùng một kết nối TLS. Một connection pool ở backend có thể giữ nhiều kết nối và tái dùng chúng lâu dài. Do đó:

**Ít handshake hơn không nhất thiết do resumption tốt hơn.** Có thể chỉ vì hệ thống tái sử dụng một kết nối TCP/TLS đã tồn tại. Khi đánh giá, phân biệt:

- Số **new TCP/QUIC connections**.
- Số **full TLS handshakes**.
- Số **resumed TLS handshakes**.
- Số **early-data attempts/accepts/rejections**.
- Số **HTTP requests hoặc streams**.
- Độ trễ tạo kết nối và request latency, cùng chi phí CPU/memory.

Trên HTTP/1.1, nhiều request tuần tự có thể dùng một persistent connection. Trên HTTP/2, nhiều request đồng thời có thể dùng một TLS connection. Vì vậy không thể suy từ tỷ lệ request/s cao rằng server phải cấp lại session ticket liên tục.

### 11.4. HTTP/3 và QUIC

**HTTP/3** sử dụng **QUIC**, giao thức vận chuyển tích hợp **TLS 1.3 handshake** để tạo khóa bảo mật. TLS handshake messages được QUIC vận chuyển trong **CRYPTO frames**, chứ không phải TLS record layer chạy trên TCP như HTTPS qua HTTP/1.1 hoặc HTTP/2.

QUIC cũng hỗ trợ **session resumption và 0-RTT** theo các quy tắc thích hợp, nhưng cần phân biệt:

- **QUIC connection migration:** một kết nối đã thiết lập có thể chuyển đường mạng trong một số điều kiện mà **không phải là TLS resumption**.
- **0-RTT QUIC:** dùng resumption state và bị ràng buộc bởi những thông số QUIC, ứng dụng và replay risk; không mặc định mọi transport parameter từ phiên cũ vẫn phù hợp.
- **UDP/443:** firewall/IDS/IPS/sensor cần quan sát đúng traffic UDP nếu tổ chức bật HTTP/3.
- **TLS logs:** không tìm TLS record-layer messages trên QUIC packet capture theo cách giống TLS over TCP.
- **Load balancer/edge:** ticket-key sharing và policy 0-RTT phải được thiết kế riêng cho QUIC endpoint, không tự suy từ trạng thái của TCP/443.

**TLS resumption không tạo khả năng bảo vệ DNS, route hoặc client identity tự động.** Với QUIC lẫn TCP, ứng dụng vẫn cần hostname validation, quyền truy cập và phòng vệ trước tình huống đường đi mạng thay đổi.

### 11.5. Service mesh và TLS nội bộ

Trong service mesh hoặc hạ tầng sidecar/mTLS:

- **Sidecar hoặc mesh gateway** có thể là điểm TLS termination; ứng dụng không phải lúc nào trực tiếp cầm certificate.
- TLS resumption giữa hai proxy/sidecars phụ thuộc **TLS library, mesh policy, workload identity và lifecycle của certificate**.
- Pod đổi IP, sidecar restart hoặc rotation workload certificate có thể làm ticket/cache miss; không phải tất cả cache miss là sự cố.
- Việc tái dùng session **không cho phép workload vượt quyền chính sách mTLS hoặc authorization theo service identity**.
- Mạng Kubernetes vẫn cần NetworkPolicy/CNI/segmentation để giới hạn đường east–west, không thay bằng một ticket đã từng được cấp.

### 11.6. Dịch vụ cloud và serverless

Với managed load balancer, API gateway, CDN, serverless front door hoặc WAF-as-a-service, nhiều thông số như ticket-key rotation và resumption scope **do nhà cung cấp quản lý**. Người vận hành phải biết:

1. Có thể bật/tắt TLS 1.2 tickets, TLS 1.3 PSK và 0-RTT không?
2. Có hỗ trợ **0-RTT per route/hostname** hay chỉ toàn endpoint?
3. Các nodes/regions/tenants có chia sẻ ticket-key scope như thế nào?
4. Log có phân biệt full/resumed/early-data mà không lộ secret không?
5. Khi thay certificate, TLS policy, cấu hình domain hoặc mTLS, tickets cũ được xử lý ra sao?
6. Khả năng rollback và phối hợp với provider khi phát hiện ticket-key exposure là gì?

Không giả định mọi nhà cung cấp có cùng tên tuỳ chọn hay cùng security defaults. Nếu một nền tảng không công bố đủ chi tiết, ghi rõ **giới hạn khả năng kiểm chứng**, dùng observable metrics và quy trình hỗ trợ nhà cung cấp.

## 12. Quan sát và đo lường resumption

### 12.1. Metric theo từng điểm TLS termination

| Chỉ số | Mục tiêu | Điều không nên diễn giải sai |
| --- | --- | --- |
| **Full handshakes / second** | Đo tải handshake xác thực đầy đủ | Cao không mặc nhiên do tấn công; có thể là release, client mới hoặc key rotation |
| **Resumed handshakes / second** | Đo mức sử dụng resumption | Nhiều resumption không thay quyền ứng dụng |
| **Resumption hit rate** | Quan sát tỷ lệ resumed trên các lần có thể thử | Định nghĩa denominator phải nhất quán; không tính mọi HTTP request |
| **Ticket issued / accepted / rejected** | Phát hiện hành vi key scope, lifecycle | Issued không đảm bảo accepted ở kết nối tiếp theo |
| **Rejected ticket reason** khi có | Expired, unknown key, scope mismatch, policy | Vendor có thể không log chi tiết; không invent nguyên nhân |
| **TLS full/resumed handshake latency p50/p95/p99** | Đo giảm chi phí bắt tay | Không đồng nghĩa end-to-end request latency |
| **TLS termination CPU/memory** | Phát hiện hiệu năng và cache pressure | CPU có thể do WAF parsing, encryption traffic hoặc backend |
| **0-RTT attempt/accepted/rejected** | Theo dõi mức sử dụng early data | Accepted không chứng minh replay prevention |
| **Possible replay / duplicate request** | Giám sát nguy cơ nghiệp vụ | Nhiều request tương tự không mặc nhiên là tấn công |
| **Ticket key version / rollout lag** | Xác minh rotation trên mọi node | Chỉ lưu key metadata, không lưu key bytes |
| **TLS version, ALPN, SNI scope** | Kiểm soát chính sách và compatibility | Không dùng SNI làm danh tính người dùng |
| **Certificate/mTLS auth state** | Hiểu xác thực ban đầu và resumed context | Resumption không nhất thiết gửi lại chứng chỉ |
| **Fallback/full handshake success** | Đảm bảo hoạt động khi ticket miss | Không cố sửa bằng cách bỏ certificate validation |

### 12.2. Tính hit rate cho đúng

Một công thức vận hành thường gặp:

~~~text
Resumption hit rate =
    successful_resumed_handshakes
    / (successful_resumed_handshakes + successful_full_handshakes)
~~~

Tuy nhiên, tỷ lệ này là **tỷ lệ handshakes hoàn thành đã quan sát**, không hẳn là **tỷ lệ chấp nhận trên tất cả resumption attempts**. Nếu TLS stack log được số **PSK attempted**, có thể tính thêm:

~~~text
Ticket acceptance rate =
    resumption_attempts_accepted
    / resumption_attempts_observed
~~~

Đo riêng TLS 1.2/TLS 1.3, edge/origin, TCP/QUIC, hostname, vùng và phiên bản triển khai. Tránh lấy một tỷ lệ lớn rồi suy toàn hệ thống an toàn hơn. Một server không có resumption vì phần lớn client là khách mới vẫn có thể đúng chính sách.

### 12.3. Sample alert

| Alert | Tín hiệu | Các khả năng cần loại trừ |
| --- | --- | --- |
| Resumption hit rate giảm sau deployment | Accepted giảm, full tăng, key version thay | Rotation đúng kế hoạch, load balancer chuyển node, ticket không tương thích |
| Full handshake CPU tăng đột biến | CPU + new connections tăng | Traffic đột biến hợp lệ, DDoS, LB health check, client bug, key rotation |
| 0-RTT bị từ chối tăng | early_data rejected và 425 tăng | Policy đã siết, anti-replay state không đồng bộ, ALPN/tenant mismatch |
| Multi-region khác biệt lớn | Region A accepted cao, B thấp | Key distribution, certificate/policy version, routing |
| mTLS resumption tiếp tục khi quyền bị thu hồi | Ticket accepted với auth context cũ | Revocation/invalidation policy chưa đúng |
| Handshake failure sau thay certificate | TLS errors + fallback failures | Trust chain, SNI, hostname, client pinning, không chỉ ticket |
| Ticket được dùng qua scope không mong đợi | Ticket identity reuse across endpoints | Cross-tenant key sharing, policy sai, cần kiểm tra provenance |
| Session telemetry mất đột ngột | Edge exporter/collector không heartbeat | **Mất dữ liệu**, không kết luận tỷ lệ lỗi giảm |

### 12.4. Bảo vệ log và dữ liệu định danh

Các trường nên ghi ở dạng tổng hợp/metadata: **thời điểm, edge ID, TLS version, cipher suite, ALPN, trạng thái full/resumed, 0-RTT accepted/rejected, ticket key version (không phải key), lỗi TLS, duration và correlation ID**.

Không ghi:

- **PSK bytes, ticket protection key, key log file hoặc SSL_SESSION chứa bí mật** vào hệ thống log chung.
- Raw ClientHello/session tickets nếu không có nhu cầu forensic được cấp quyền và biện pháp bảo vệ thích hợp.
- Access token, Authorization header, session cookie, password hoặc nội dung early-data request body vào log WAF/SIEM không cần thiết.
- Dữ liệu client có thể nhận diện cá nhân vượt mục đích an ninh/retention chính sách.

**Ticket identity có thể là một định danh theo dõi kết nối** trong một số cấu hình. Ngay cả khi nó không giải mã được thành session secret, raw ticket vẫn cần xử lý như dữ liệu nhạy cảm để giảm khả năng liên kết người dùng/thiết bị qua phiên.

### 12.5. Tương quan tới SLO ứng dụng

Theo dõi cùng lúc:

1. TLS handshake latency và error rate.
2. First-byte/request latency, 4xx/5xx và tỷ lệ thành công nghiệp vụ.
3. CPU/connection concurrency/handshake queue của TLS terminator.
4. Ticket acceptance, full fallback, key rollout.
5. Tình trạng identity/mTLS và rule của WAF/reverse proxy.
6. 0-RTT duplicate/replay suspicion nếu bật.

Một thay đổi làm resumption hit rate tăng nhưng **API transaction success giảm** không thể coi là tối ưu thành công. Bảo mật, độ sẵn sàng và trải nghiệm phải được đánh giá cùng nhau.

## 13. Bài thực hành TLS resumption trong lab được cấp quyền

**Mục tiêu:** tạo một TLS server ở **localhost**, thực hiện full handshake, nhận session ticket, dùng lại session trên **kết nối TLS mới**, quan sát resumed/full fallback và rút ra bài học về lifetime/rotation. Không phát replay request tới bất kỳ hệ thống production nào.

### 13.1. Điều kiện trước khi chạy

- Máy lab có OpenSSL hỗ trợ TLS 1.3 (ví dụ bản OpenSSL 1.1.1 trở lên, tùy build/policy) và quyền chạy server localhost.
- Sử dụng shell Bash trên Unix/Linux hoặc môi trường tương đương; Windows PowerShell có cú pháp khác và cần điều chỉnh đường dẫn.
- Chỉ binding server vào localhost khi có thể; nếu công cụ không hỗ trợ giới hạn địa chỉ theo cú pháp tương ứng, dùng firewall của môi trường lab để **không công bố cổng thử nghiệm ra Internet**.
- Đảm bảo cổng 8443 không dùng cho dịch vụ khác; dùng chứng chỉ self-signed **chỉ trong lab**, có SAN localhost.
- Không sử dụng khóa/phiên thật, cookie thực hoặc thông tin cá nhân. Không commit các file **server.key, session.pem** hoặc TLS key logs vào repository.

**Lưu ý:** cú pháp/tùy chọn và cách OpenSSL lưu TLS 1.3 ticket có khác biệt giữa phiên bản. Tài liệu dưới đây là một quy trình thử nghiệm mẫu; nếu build OpenSSL không hỗ trợ option, kiểm tra trợ giúp của chính bản đó thay vì tắt xác minh chứng chỉ.

### 13.2. Tạo môi trường lab cục bộ

Trong một shell test riêng:

~~~bash
# Dùng thư mục do người học sở hữu; tuyệt đối không dùng key production.
umask 077
mkdir -p "$HOME/tls-resume-lab"
cd "$HOME/tls-resume-lab"
chmod 700 .

# Chứng chỉ tự ký cho đúng hostname localhost (lab only).
openssl req -x509 -newkey rsa:2048 -nodes \
  -keyout server.key -out server.crt -days 1 \
  -subj "/CN=localhost" \
  -addext "subjectAltName=DNS:localhost"
~~~

Đối với lab này, **server.crt** đóng vai trò chứng chỉ được client tin cậy thông qua tham số **-CAfile**, không có nghĩa mọi server certificate tự ký đều được tin cậy trong môi trường sản xuất. Trong production, client phải kiểm tra chuỗi chứng thực và hostname theo PKI được phê duyệt.

### 13.3. Chạy server TLS 1.3

Terminal A:

~~~bash
cd "$HOME/tls-resume-lab"

# Chỉ lắng nghe loopback khi cú pháp network endpoint được hỗ trợ.
openssl s_server -accept 127.0.0.1:8443 \
  -cert server.crt -key server.key -tls1_3 -www
~~~

Nếu phiên bản OpenSSL của bạn không chấp nhận dạng **127.0.0.1:8443** cho -accept, hãy xem cú pháp s_server của phiên bản đó và đảm bảo cổng chỉ có thể được truy cập từ lab. **Không mở listener trên tất cả interface rồi để Internet kết nối vào thử nghiệm**.

### 13.4. Full handshake và lưu ticket

Terminal B:

~~~bash
cd "$HOME/tls-resume-lab"

openssl s_client \
  -connect 127.0.0.1:8443 \
  -servername localhost \
  -verify_hostname localhost \
  -verify_return_error \
  -CAfile server.crt \
  -tls1_3 \
  -sess_out session.pem \
  -ign_eof
~~~

Khi kết nối được thiết lập, có thể nhập request HTTP thử sau để server trả thông tin lab:

~~~text
GET / HTTP/1.1
Host: localhost
Connection: close

~~~

Quan sát đầu ra handshake và **NewSessionTicket** sau khi server phát ticket. Với TLS 1.3, ticket thường được gửi **sau khi handshake đã hoàn tất**, nên nếu client đóng socket quá nhanh, file session có thể chưa chứa ticket phù hợp. Đợi công cụ nhận ticket trước khi đóng client; kiểm tra file session đã được lưu. Không copy nội dung file này lên chat, SIEM hoặc issue tracker vì nó chứa thông tin phiên nhạy cảm.

### 13.5. Nối phiên trên kết nối TLS 1.3 mới

Sau khi đảm bảo **session.pem** được tạo từ kết nối trước (và **server vẫn đang chạy**), tại Terminal B:

~~~bash
cd "$HOME/tls-resume-lab"
chmod 600 session.pem

openssl s_client \
  -connect 127.0.0.1:8443 \
  -servername localhost \
  -verify_hostname localhost \
  -verify_return_error \
  -CAfile server.crt \
  -tls1_3 \
  -sess_in session.pem
~~~

Một số bản OpenSSL hiển thị **Reused, TLSv1.3** khi nối phiên được chấp nhận hoặc **New, TLSv1.3** khi thực hiện full handshake. Dòng output chỉ là **bằng chứng quan sát trên phiên bản công cụ đang dùng**, không là một chuẩn log thống nhất. Nếu server không chấp nhận ticket, client có thể fallback full handshake; đó có thể là kết quả bình thường do ticket chưa lưu, quá hạn hoặc server không hỗ trợ như kỳ vọng.

**Kiểm thử fallback:** dừng server lab, khởi động lại với cấu hình/key ticket mới nếu công cụ hỗ trợ theo cách đã được cấp quyền, rồi dùng session.pem cũ. Bạn có thể thấy full handshake thay vì resumption. Không yêu cầu cố ép server nhận session đã hết hiệu lực.

### 13.6. Thử TLS 1.2 với session ID/ticket

Để so sánh, có thể khởi động **một** server lab riêng trên port khác khi cần:

~~~bash
# Terminal A - trên môi trường lab đã tạo cert/key.
openssl s_server -accept 127.0.0.1:8444 \
  -cert server.crt -key server.key -tls1_2 -www
~~~

~~~bash
# Terminal B - tạo session TLS 1.2 cho cùng server.
openssl s_client -connect 127.0.0.1:8444 \
  -servername localhost -verify_hostname localhost \
  -verify_return_error -CAfile server.crt \
  -tls1_2 -sess_out session12.pem

# Kết nối TLS 1.2 mới, thử session state đã lưu.
openssl s_client -connect 127.0.0.1:8444 \
  -servername localhost -verify_hostname localhost \
  -verify_return_error -CAfile server.crt \
  -tls1_2 -sess_in session12.pem
~~~

Không dùng cùng session file của TLS 1.2 để thử TLS 1.3 hoặc ngược lại. Nếu thư viện hiển thị **TLS session ticket** trong thông tin TLS 1.2, điều đó chỉ cho biết cơ chế có thể được thương lượng; muốn chắc chắn reused, phải kiểm tra handshake thực tế và trạng thái xử lý ở server.

### 13.7. Java JSSE: quản lý session cache

Trong Java, **JSSE** cung cấp quản lý TLS qua SSLContext, SSLSocket/SSLEngine, và SSLSessionContext. Thư viện HTTP client có thể giữ connection pool và các session được quản lý nội bộ. Một ví dụ đọc thông tin cấu hình session context:

~~~java
import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLSessionContext;

public class TlsSessionCacheInfo {
    public static void main(String[] args) throws Exception {
        SSLContext context = SSLContext.getDefault();
        SSLSessionContext clientSessions = context.getClientSessionContext();

        System.out.println("Cache size setting: "
                + clientSessions.getSessionCacheSize());
        System.out.println("Session timeout (seconds): "
                + clientSessions.getSessionTimeout());
    }
}
~~~

**Lưu ý:**

- Giá trị trả về là **cấu hình session cache context**, **không chứng minh** một HTTP request cụ thể đã dùng TLS resumption.
- Cách quản lý TLS 1.3 tickets/cache và session reuse phụ thuộc **JDK version, TLS provider, HTTP client implementation và connection pooling**.
- Có thể sử dụng **javax.net.debug=ssl,handshake,session** trong một lab được cấp quyền để điều tra handshake, nhưng **không bật log debug TLS chi tiết lâu dài trong production** và tránh chia sẻ log thô vì có thể lộ metadata bí mật.
- Không tạo TrustManager chấp nhận mọi certificate để “giúp resumption dễ hơn”. Phải dùng hostname verification và CA/trust anchors hợp lệ.
- Nếu ứng dụng giữ một socket TLS đang mở hoặc một HTTP/2 connection, bạn có thể **không tạo handshake mới**, nên không thấy resumption dù kết nối hoạt động tốt.

Ví dụ tham số debug khi chạy class trong lab:

~~~bash
java -Djavax.net.debug=ssl,handshake,session TlsSessionCacheInfo
~~~

Lệnh trên chỉ đọc thông tin cache và có thể **không tạo TLS handshake**, vì chương trình mẫu không mở kết nối HTTPS. Khi cần quan sát resumption bằng JSSE, phải có **một ứng dụng lab thật sự tạo hai kết nối TLS mới tới cùng endpoint** và phân tích log theo JDK đang dùng. Không diễn giải một dòng "session" trong debug là bằng chứng chắc chắn handshake resumed.

### 13.8. Quan sát bằng packet capture đúng cách

Trong lab được phép, công cụ phân tích gói như Wireshark có thể thấy:

- TCP connection hoặc UDP/QUIC connection mới.
- **ClientHello/ServerHello** và các extension không được mã hóa trong ngữ cảnh phù hợp.
- **pre_shared_key extension** trong TLS 1.3 ClientHello trên TLS over TCP theo cách phân tích thích hợp.
- Sự khác biệt về số lượng/kích thước handshake messages giữa full và resumed handshakes.

Nhưng **NewSessionTicket TLS 1.3 được bảo vệ bằng TLS encryption sau handshake**, nên packet capture thụ động **không giải mã được chỉ bằng việc nhìn gói**. Một số client còn dùng ECH cho ClientHello ở bối cảnh hỗ trợ, làm thay đổi metadata quan sát được. Khi cần phân tích gói đã giải mã, chỉ sử dụng session secrets của **client lab do bạn kiểm soát** và bảo vệ file key log như một bí mật có thể giải mã traffic; không thu thập session secrets của khách hàng.

**Không gửi PCAP có payload nhạy cảm** vào kho log hoặc bug tracker công khai chỉ để đo resumption. Với production, ưu tiên metrics từ TLS termination software, tổng hợp event và traces đã redaction.

### 13.9. Ma trận kiểm chứng lab

| ID | Thử nghiệm | Kết quả mong đợi | Bằng chứng |
| --- | --- | --- | --- |
| T01 | Kết nối TLS 1.3 lần đầu, cert hợp lệ | Full handshake thành công | Phiên bản, certificate verification, handshake summary |
| T02 | Client nhận và lưu NewSessionTicket | Session state khả dụng nếu stack hỗ trợ | Log công cụ và file session được bảo vệ |
| T03 | Tạo kết nối TLS mới, trình session ticket phù hợp | Resumed nếu được hỗ trợ, nếu không full handshake an toàn | New/Reused, server counters |
| T04 | Client không có ticket | Full handshake | Log full, certificate validation |
| T05 | Ticket quá hạn hoặc server không nhận key cũ | Full fallback, không bỏ xác thực | Server rejection reason nếu có |
| T06 | Thay server certificate sang cert không đáng tin trong lab | Client không được chấp nhận full handshake sai trust; resumption cần xử lý đúng context policy | TLS errors/policy evidence |
| T07 | Thay SNI/ALPN hoặc tenant trong lab | Không dùng ticket ngoài scope cho phép | TLS logs + host/tenant policy |
| T08 | Chuyển tới node không chia sẻ ticket key | Full fallback nếu không có state tương thích | Per-node log/counter |
| T09 | Thử resumed PSK+DHE nếu stack hỗ trợ | Có PSK selection và fresh key share | Handshake telemetry, negotiated mode |
| T10 | 0-RTT disabled | Không xử lý early-data request | Server policy, early_data counters |
| T11 | 0-RTT request bị từ chối ở route nhạy cảm | Không có tác dụng phụ trước handshake; retry có kiểm soát | 425/log/backend transaction IDs nếu có |
| T12 | Client dùng HTTP/2 connection pooling | Request mới có thể không sinh handshake | Connection ID, TLS handshake count |
| T13 | TLS 1.2 new/resumed | So full và abbreviated khi hỗ trợ | TLS 1.2 session state, mode/counter |
| T14 | TLS termination trên hai hop | Mỗi hop có certificate và resumption state riêng | Edge/origin logs, session scope |

**Không thử replay 0-RTT trên dịch vụ có dữ liệu thật.** T14 có thể được kiểm tra bằng proxy lab, không yêu cầu gọi cloud production hoặc mở mạng nội bộ không thuộc quyền.

## 14. Threat modeling cho session resumption và ticket

### 14.1. Những tài sản cần bảo vệ

- **Certificate/private key** và hệ thống tin cậy để xác minh TLS peers.
- **Ticket protection keys và resumption PSKs**, bao gồm vùng lưu, key distributor và các node có quyền giải mã.
- **Ticket issuance/acceptance policy**: lifetime, SNI/ALPN, TLS mode, early data và tenant.
- **mTLS identity và authorization context** gắn với kết nối trước.
- **Dữ liệu early-data request**, đặc biệt thao tác có tác dụng phụ và dữ liệu nhạy cảm.
- **TLS termination availability**, CPU, cache và khả năng fallback full handshake.
- **Observability** của full/resumed/0-RTT và audit các thay đổi chính sách.

### 14.2. Bảng đe dọa và kiểm soát

| ID | Mối đe dọa / lỗi | Điều kiện xảy ra | Hậu quả | Biện pháp |
| --- | --- | --- | --- | --- |
| TLS-R01 | Ticket protection key bị lộ | Node, secret store hoặc distribution bị truy cập trái phép | Rủi ro khôi phục state/session secrets, phạm vi tùy TLS version và cách triển khai | Quyền tối thiểu, key rotation, short lifetime, audit, giới hạn key scope |
| TLS-R02 | PSK/client session state bị lộ | Client cache/file/log thiếu bảo vệ | Có thể sử dụng hoặc phân tích trạng thái nối phiên trái phép | Bảo vệ session storage, không xuất secret/log thô, endpoint protection |
| TLS-R03 | 0-RTT bị replay | Server nhận early data có side effects, anti-replay không đầy đủ | Xử lý trùng giao dịch hoặc thay trạng thái | Disable theo mặc định, route policy, application idempotency, replay controls |
| TLS-R04 | Anti-replay state không đồng bộ giữa edge | Multi-node/region cùng xử lý một ticket | Cùng early data có thể được xử lý nhiều nơi | Coordination theo khả năng, không xử lý stateful operation bằng 0-RTT |
| TLS-R05 | Ticket được chấp nhận xuyên tenant | Chia sẻ key/scope không phù hợp | Resumption trong bối cảnh bảo mật sai | Tenant/SNI/ALPN policy binding, key isolation, negative tests |
| TLS-R06 | Revoked mTLS identity vẫn được resume | Resumption dùng auth context cũ quá lâu | Tiếp tục có kênh được xác thực theo trạng thái cũ | Context expiry/invalidation, fresh authentication, app authorization |
| TLS-R07 | Rotation làm cache miss hàng loạt | Key rollout sai thứ tự hoặc mất compatibility | CPU/latency tăng, handshake failures khi server quá tải | Graceful rotation, capacity planning, fallback, staged deployment |
| TLS-R08 | Ticket lifetime quá dài | Vòng đời key/session không được giới hạn | Tăng thời gian sử dụng state cũ và tác động khi compromise | Lifetime theo risk, key retirement, review traffic |
| TLS-R09 | Session cache tràn hoặc thất bại | Tải lớn, thiếu memory/cache HA | Hiệu năng giảm, lỗi nếu fallback không vững | Cache limits, metrics, scale, full handshake path |
| TLS-R10 | 0-RTT bật trên API admin/payment | Edge chấp nhận request sớm, backend unaware | Side effects, race condition, duplicate transaction | Route allowlist hẹp hoặc tắt, application policy tại backend |
| TLS-R11 | Certificate validation bị bỏ qua vì muốn resumption | Client/SDK có cấu hình insecure | Kết nối có thể chấp nhận peer không đúng | Enforce PKI/SAN validation, test full/fallback |
| TLS-R12 | Nhầm session ticket với HTTP session | Ứng dụng cấp quyền từ TLS resume flag | Authorization bypass hoặc sai identity | Tách rõ TLS layer và app authn/authz |
| TLS-R13 | Quan sát bị mất tại edge khác | SIEM chỉ nhận một region/node | Không phát hiện 0-RTT hoặc key drift toàn cụm | Per-node telemetry, heartbeat, rollout audit |
| TLS-R14 | Raw ticket/PSK vào log | Debug TLS kéo dài hoặc export PCAP/keylog | Bí mật phiên và privacy metadata bị phơi bày | Redaction, RBAC, retention, incident handling |
| TLS-R15 | Origin TLS thiếu xác minh sau proxy | Chỉ client–edge TLS được kiểm tra | Traffic nội bộ có thể gặp peer sai, dù edge resumption đúng | Origin TLS validation, mTLS, firewall và origin restriction |
| TLS-R16 | Traffic resumption dùng thuật toán không còn phù hợp | Cấu hình cũ được reuse không xét policy mới | Vi phạm chuẩn bảo mật nội bộ | Policy versioning, reject/fallback, kiểm tra cipher/protocol |

### 14.3. STRIDE ở lớp TLS resumption

- **Spoofing:** chủ thể có trạng thái/PSK hoặc credential không được phép cố nối phiên; cần xác minh PSK binder và authentication context.
- **Tampering:** sửa ticket/ClientHello hoặc policy/key distribution; TLS bảo vệ integrity cho transcript/ticket theo cơ chế đúng, nhưng vẫn cần kiểm soát người quản trị.
- **Repudiation:** thiếu audit khi bật 0-RTT, đổi lifetime hoặc chấp nhận ticket ngoài scope; cần thay đổi có người duyệt và trace ID.
- **Information disclosure:** lộ PSK/ticket protection key, TLS key logs hoặc liên kết người dùng qua ticket identity.
- **Denial of Service:** rotation, cache failure hoặc flood full handshakes làm CPU TLS terminator quá tải.
- **Elevation of privilege:** resumed authentication context cũ vẫn được dùng sau khi quyền ứng dụng hoặc mTLS client identity đã bị thu hồi.

Không gộp mọi trường hợp vào "ticket bị đánh cắp thì tự đăng nhập được". Việc có **opaque ticket bytes** khác với có **PSK bí mật**, và việc có kết nối TLS khác với quyền ứng dụng. Đánh giá khả năng tấn công phải dựa trên phiên bản TLS, key exposure, binder, identity policy và hành vi ứng dụng.

### 14.4. Attack tree mức phòng vệ

~~~mermaid
flowchart TD
    G["Mục tiêu rủi ro: lợi dụng resumption"] --> A{"Bề mặt"}
    A --> K["Khóa/ticket state"]
    A --> E["0-RTT early data"]
    A --> I["Identity và session scope"]
    A --> P["Availability và policy"]
    K --> K1["Secret manager, rotation,\nkey isolation, audit"]
    E --> E1["Disable/route policy,\nanti-replay, idempotency"]
    I --> I1["mTLS revocation, tenant/SNI/ALPN,\napplication authorization"]
    P --> P1["Fallback full handshake,\ncapacity, staged rollout"]
    K1 --> R["SOC/NOC review và kiểm thử"]
    E1 --> R
    I1 --> R
    P1 --> R
~~~

Sơ đồ chỉ mô tả **phạm vi phòng vệ**; không phải chuỗi bước khai thác. Những khả năng của người có quyền truy cập secret khác người chỉ quan sát gói hoặc chỉ sở hữu ticket identity.

## 15. Khắc phục sự cố session resumption

### 15.1. Bắt đầu bằng phân loại triệu chứng

| Triệu chứng | Những nguyên nhân có thể | Kiểm tra đúng |
| --- | --- | --- |
| Không thấy "Reused" ở lần nối TLS mới | Client không giữ ticket, server không phát ticket, key scope sai, timeout | Kiểm tra ticket issuance, ClientHello PSK proposal, server acceptance và TLS version |
| Session ticket được cấp nhưng hit rate thấp | Client mới nhiều, load balancer đổi node, key rotation thường xuyên | Breakdown theo client/edge/region; hit rate có denominator rõ |
| TLS 1.3 resumption không giảm RTT đáng kể | Cả full/resumed 1-RTT thường cần một RTT | Đo CPU, handshake bytes, TLS latency; không so với kỳ vọng giảm RTT sai |
| Full handshake tăng sau restart | Cache mất, ticket protection keys thay | Fallback, CPU, rollout order và secret lifecycle |
| Một vùng resumption hoạt động, vùng khác không | Region keys/policy/ALPN khác hoặc ticket state không chia sẻ | Per-region key ID, config version, TLS logs |
| 0-RTT requests bị 425 | Server/gateway không muốn xử lý early data | Route policy, backend support, client retry |
| 0-RTT tạo giao dịch trùng | Replay hoặc logic retry/idempotency sai | Request IDs, idempotency store, edge logs, backend side effects |
| mTLS identity đã bị thu hồi nhưng kết nối vẫn đi | Ticket còn dùng auth context cũ, role cache chưa invalidated | Revocation policy, session lifetime, request authorization |
| Client báo certificate error sau rotation | CA/SAN/hostname/trust mismatch | Full handshake cert chain, SNI, client trust store; không tắt xác minh |
| SSL session file không có ticket TLS 1.3 | Client đóng sớm trước NewSessionTicket | Đợi post-handshake ticket và kiểm tra công cụ |
| QUIC 0-RTT hoạt động khác TCP/TLS | Transport params, UDP path và QUIC policy khác | QUIC-specific logs, handshake/early-data counters |
| Session cache hit nhưng app vẫn 401/403 | TLS thành công nhưng identity/authorization ứng dụng từ chối | App auth logs, token expiry, session cookies |
| Resumption hit nhưng origin 502/504 | Lỗi chặng TLS/proxy/backend khác | Phân tích từng hop, health check, origin certificate |
| TLS CPU tăng khi bật chặn ticket cũ | Số full handshakes tăng | Auto scaling/capacity, kiểm tra failover an toàn |
| Không có session events tại một node | Telemetry exporter/collector lỗi | Heartbeat, event lag và log nguồn |

### 15.2. Sơ đồ chẩn đoán

~~~mermaid
flowchart TD
    A["Resumption không đúng kỳ vọng"] --> B{"Có kết nối TLS mới thực sự?"}
    B -- "Không" --> B1["Kết nối cũ được reuse\n(HTTP pooling / multiplexing)"]
    B -- "Có" --> C{"Client có trạng thái ticket/PSK?"}
    C -- "Không" --> C1["Kiểm tra NewSessionTicket,\nclient cache, thời điểm đóng"]
    C -- "Có" --> D{"Client gửi PSK proposal hợp lệ?"}
    D -- "Không" --> D1["Kiểm tra TLS version,\nSNI/ALPN, session expiry"]
    D -- "Có" --> E{"Server chấp nhận PSK?"}
    E -- "Không" --> E1["Kiểm tra ticket keys, node,\npolicy, auth context, fallback"]
    E -- "Có" --> F{"Ứng dụng có sự cố?"}
    F -- "Có" --> F1["Phân biệt 0-RTT, HTTP auth,\norigin routing, backend"]
    F -- "Không" --> G["Đo hiệu năng, privacy\nvà giới hạn replay"]
~~~

**Dòng đầu tiên là quan trọng:** nếu client đang dùng một TLS connection đã có, việc không thấy resumption mới là bình thường. Tránh bật các tính năng có rủi ro chỉ để buộc dashboard hiển thị nhiều ticket hơn.

### 15.3. Khi kết quả TLS 1.2 và 1.3 khác nhau

Nếu test cho thấy TLS 1.2 "Reused" nhưng TLS 1.3 luôn "New", hãy kiểm tra:

1. Server thực sự hỗ trợ/phát **TLS 1.3 NewSessionTicket** không?
2. Client có đợi nhận ticket **post-handshake** rồi lưu session state không?
3. OpenSSL/JDK/provider có hỗ trợ resumption TLS 1.3 và cách xuất/nhập state đang dùng không?
4. Chính sách TLS 1.3, psk_key_exchange_modes, ALPN/SNI có thay đổi không?
5. Các kết nối thử có đi đúng **cùng endpoint/context** hay đã qua load balancer đổi node?

Không cần hạ TLS xuống 1.2 để "khôi phục resumption". Tối ưu ưu tiên **TLS 1.3 có xác thực và policy mạnh**; nếu resumption 1.3 không được hỗ trợ do một thư viện cũ, nâng cấp/thay công nghệ theo kế hoạch thay vì cố làm yếu security settings.

### 15.4. Khác biệt giữa ticket rotation và revocation

**Rotation** là chủ động thay key mới và chuyển ticket mới sang key đó. **Revocation** là từ chối trạng thái/identity không còn đáng tin, có thể đòi vô hiệu ticket và session cache đang hoạt động theo cơ chế nền tảng.

Nếu một mTLS client credential bị thu hồi:

- Không chỉ rotate server certificate.
- Không chỉ đợi cookie ứng dụng hết hạn.
- Xem liệu resumption ticket đã cấp **còn được chấp nhận hay không** và các phiên TLS đang mở xử lý ra sao.
- Xác minh API authorization/revocation độc lập với TLS.
- Khi cần, dùng policy yêu cầu fresh handshake hoặc vô hiệu tickets theo phạm vi thích hợp.

### 15.5. Đo trước khi sửa cấu hình

Một bài kiểm tra có thể quan sát **tăng 8% CPU** sau khi giảm ticket lifetime, nhưng chưa chắc sự cố do bản thân TLS: có thể vừa thay số kết nối mới, tăng request hoặc bật tính năng WAF khác. Khi điều tra, so **cùng khối lượng traffic, TLS version, ALPN, edge group, session attempts và time window**, rồi kiểm tra mối tương quan với key rollout.

Không dựa vào một mẫu đo duy nhất ở laptop localhost để suy CPU hoặc RTT trong production. Lab chứng minh **cơ chế**; benchmark thực tế cần mô hình tải phù hợp, theo chính sách hiệu năng và an ninh.

## 16. Kế hoạch triển khai bảo mật resumption trong thực tế

### 16.1. Bước 1 — Bản đồ TLS termination và phạm vi tin cậy

Ghi:

- Hostname/SNI, ALPN, TLS versions và các certificate/CA được dùng.
- Điểm kết thúc TLS: CDN/WAF, load balancer, reverse proxy, service mesh sidecar và backend.
- Phạm vi ticket-key hoặc PSK state của từng nhóm TLS termination, tenant và region.
- Client populations: browser, mobile, machine-to-machine, thiết bị IoT, client mTLS.
- 0-RTT có hỗ trợ không, bật ở đâu, backend có nhận early-data marker hay không.
- Đường fallback full handshake khi node restart/rotation/validator unavailable.
- Các điểm firewall/IDS/IPS, VPN và network segmentation của từng hop.

Kết quả cần là **sơ đồ kết nối và ownership**: đội nào có quyền sửa TLS policy/ticket keys và ai kiểm tra authorization của ứng dụng.

### 16.2. Bước 2 — Baseline bảo mật

Trước khi tối ưu:

1. Ưu tiên **TLS 1.3** với cấu hình cipher/group/certificate được phê duyệt; vô hiệu các protocol/cipher không còn an toàn theo chính sách tổ chức.
2. Không bỏ qua **certificate chain/hostname verification** trên mọi hop.
3. Giới hạn ticket lifetime, quản lý key scope và bảo vệ resumption state.
4. **0-RTT tắt theo mặc định** nếu không có use case và anti-replay policy đủ rõ.
5. Quy định cách xử lý **mTLS revocation, role changes và step-up authorization** khi session được nối lại.
6. Đảm bảo full handshake fallback hoạt động với đúng authentication/policy.

### 16.3. Bước 3 — Baseline telemetry và hiệu năng

Thu số liệu trước thay đổi: **full/resumed handshakes, ticket acceptance, 0-RTT state, latency p50/p95/p99, CPU, memory, session cache, TLS errors, HTTP success/latency và failover results**.

Các số liệu phải được phân tách theo **TLS termination hop, region/node, version, ALPN, application group**. Nếu SIEM chỉ có event từ một edge region, ghi nhận là **giới hạn quan sát**, không báo toàn bộ hệ thống khỏe.

### 16.4. Bước 4 — Triển khai có kiểm soát

Một lộ trình:

1. Bật TLS 1.3 resumption theo mặc định/năng lực sản phẩm trong lab, **chưa bật 0-RTT**.
2. Kiểm tra full/resumed handshake và fallback sau ticket expiration.
3. Thiết kế key rotation có thời kỳ tương thích hợp lý, version và secret distribution được bảo vệ.
4. Thử chuyển kết nối qua các node/regions; xác minh khi không chia sẻ key thì full handshake vẫn an toàn.
5. Thử thay certificate, mTLS policy, SNI/ALPN và tenant để phát hiện cross-scope reuse không được phép.
6. Chạy canary/rollout theo vùng/hostname khi công nghệ hỗ trợ; theo dõi CPU, lỗi handshake và ứng dụng.
7. Chỉ xem xét 0-RTT cho use case rất hẹp nếu có thiết kế chống replay, application policy và capacity phù hợp.
8. Lưu version policy, owner, phê duyệt và cách hoàn tác.

### 16.5. Bước 5 — Kiểm thử phương án rollback

Một phương án rollback đúng có thể:

- Khôi phục key distribution/policy trước đó trong giới hạn đã duyệt.
- Tạm **không nhận các ticket đang gây lỗi**, nhưng vẫn thực hiện **full TLS handshake hợp lệ**.
- Tắt 0-RTT độc lập mà không tắt TLS 1.3.
- Tăng năng lực TLS terminator dự phòng để chịu thêm full handshake khi cần.
- Xác minh client mTLS và application authorization không bị nới lỏng.
- Kiểm tra API, DNS/TCP/QUIC, origin TLS, firewall routes và trạng thái thực tế từng edge.

**Không dùng giải pháp rollback là tắt xác minh certificate, mở origin trực tiếp ra Internet hoặc chấp nhận early-data writes không kiểm soát.** Tính sẵn sàng phải được phục hồi mà không bỏ ranh giới tin cậy cần thiết.

### 16.6. Bước 6 — Vận hành theo vòng đời

Khi xảy ra thay đổi **TLS software, JDK/OpenSSL version, HSM/secret provider, load balancer topology, CDN, hostname/ALPN, certificate, mTLS CA hoặc policy authorization**, đội vận hành nên chạy lại các test resumption, key rotation, failure/fallback và 0-RTT.

Thực hiện review định kỳ cho:

- Ticket lifetime/rotation không vượt mục tiêu rủi ro.
- Không có tenant/region ngoài phạm vi nhận khóa ticket.
- Không có API nhạy cảm vô tình xử lý early data.
- mTLS revocation và authorization tiếp tục được thực thi.
- Log không chứa secrets.
- SOC/NOC nhận cảnh báo khi key rollout/telemetry gặp lỗi.

## 17. Tình huống thực tế và quyết định thiết kế

### 17.1. Case A — Tỷ lệ resumption giảm khi cân bằng tải sang region khác

Một API ở edge region A có hit rate 70% trong nhóm handshakes đo được. Sau khi chuyển 30% traffic sang region B, hit rate toàn hệ thống giảm đáng kể, trong khi TLS vẫn thành công và HTTP transaction success không đổi.

**Nhận định:** region B có thể không chia sẻ ticket-key state với region A, client mới không có ticket phù hợp hoặc region B dùng TLS policy khác. Đây **không tự động là sự cố bảo mật**, và không nhất thiết là lý do phải dùng cùng khóa toàn cầu.

**Cách xử lý:**

1. Xem per-region TLS version, full/resumed counters và key version.
2. Kiểm tra issuance/acceptance và load balancer routing trước/sau chuyển vùng.
3. Đánh giá CPU/TLS latency và SLO ứng dụng; chỉ tối ưu nếu có tác động đáng kể.
4. Nếu cân nhắc chia sẻ key, đánh giá **blast radius**, phân quyền và rotation đồng bộ.
5. Giữ fallback full handshake và kiểm tra không có lỗi certificate/authentication.

**Kết luận mẫu:** hit rate thấp hơn có thể được chấp nhận để giữ **key isolation theo region**, nhất là khi full handshake còn đáp ứng SLA.

### 17.2. Case B — Tạo giao dịch trùng sau khi bật 0-RTT

Một nhóm bật 0-RTT trên toàn bộ host API để giảm độ trễ mobile. Sau đó một số request tạo đơn hàng xuất hiện hai lần. Hệ thống có retry tự động tại client, load balancer đa vùng và backend chưa có idempotency key.

**Giả thuyết:** duplicate có thể do **early-data replay**, do client retry khi 0-RTT bị từ chối, do queue/job retry, hoặc do application bug. Chỉ quan sát hai order IDs gần nhau **không đủ quy kết TLS**.

**Các bước xác minh:**

| Dữ liệu | Cần kiểm tra |
| --- | --- |
| Edge TLS logs | Kết nối nào dùng early data, accepted/rejected, ticket identity hoặc correlation an toàn |
| HTTP gateway logs | Request ID, Early-Data marker tin cậy nếu có, route, method, status, retry |
| Backend logs | Transaction IDs, idempotency keys, side effects, storage commit time |
| Multi-region gateway | Anti-replay store, đồng bộ state và thời gian nhận request |
| Client telemetry | Retry behavior, lỗi 425/timeout và giao dịch người dùng |

**Ứng phó an toàn:** tắt early-data processing cho **các route ghi trạng thái** trong khi vẫn giữ TLS 1.3 và resumption 1-RTT; sửa idempotency và retry semantics ở tầng ứng dụng. Không xóa lịch sử giao dịch hoặc hủy cả TLS security chỉ để dashboard hết duplicate.

### 17.3. Case C — Certificate khách hàng bị thu hồi nhưng API vẫn chấp nhận kết nối

Một service dùng mTLS. Certificate của workload X bị thu hồi lúc 11:00, nhưng một kết nối mới từ client vẫn được ghi là **resumed** lúc 11:02, và backend trả HTTP 200 cho một API được bảo vệ.

Đây là sự kiện **cần điều tra nghiêm trọng**, vì có thể resumption tiếp tục dựa vào authentication context cũ hoặc application authorization chưa kiểm tra revocation. Tuy nhiên, phải xác minh client thật sự dùng credential đã bị thu hồi, trạng thái TLS terminator, session cache và chính sách revocation trước khi kết luận là bypass thành công.

**Quy trình:**

1. Xác nhận effective revocation time, certificate identity, trust/CRL/OCSP hoặc policy tương ứng.
2. Kiểm tra full/resumed handshake evidence và ticket acceptance.
3. Xác định mTLS peer identity được gán cho request, lifetime/context của resumption state.
4. Kiểm tra backend có được phép **tái đánh giá quyền** và gắn identity đúng không.
5. Yêu cầu fresh authentication hoặc vô hiệu tickets liên quan theo khả năng TLS stack.
6. Áp chính sách authorization với workload X không còn quyền; kiểm tra các đường TLS termination khác.
7. Giám sát sau thay đổi và lưu case evidence, không log raw PSK/ticket.

**Điểm học:** resumption TLS và thu hồi credential/role **không nhất thiết có cùng vòng đời**.

### 17.4. Case D — Origin vẫn dùng TLS 1.2 ticket keys cũ

CDN/WAF hỗ trợ TLS 1.3 phía client và rotate ticket keys đúng chính sách. Nhưng reverse proxy phía origin dùng TLS 1.2, key quản lý ticket đã lâu không thay đổi và các node share key qua một vùng secret có quyền quá rộng.

**Vấn đề:** hệ thống có ít nhất **hai security contexts**. Dù TLS A phía client được bảo vệ tốt, key lifetime và access control của TLS B vẫn tạo rủi ro riêng.

**Cần làm:**

- Kiểm kê phiên bản/cipher TLS ở cả client–edge và edge–origin.
- Kiểm tra origin certificate validation, mTLS, danh sách peer được phép truy cập.
- Rà TLS 1.2 session ticket key lifecycle hoặc thay bằng mô hình TLS 1.3 được hỗ trợ.
- Thu hẹp quyền secret distribution, lập quy trình rotation và full fallback.
- Không dựa vào việc "client thấy TLS 1.3" để kết luận toàn bộ đường đi đã dùng TLS 1.3.

### 17.5. Case E — Resumption bị mất sau khi chuyển SNI và ALPN

Một đội chuyển API từ **api-a.example.test** sang **api-b.example.test**, đồng thời từ HTTP/1.1 sang HTTP/2. Client đôi khi thực hiện full handshake dù đã lưu ticket trước đó.

**Diễn giải phù hợp:** ticket có thể bị ràng buộc vào hostname/protocol context cũ, TLS library có thể tách cache theo endpoint, server đổi chính sách hoặc node khác không có key tương ứng. **Không cố gắng chia sẻ resumption state giữa hai host để xóa full handshake** nếu chưa có thiết kế scope được duyệt.

**Kết quả mong đợi:** full handshake có certificate/hostname validation đúng cho host mới; resumption về sau có thể được thiết lập **trong context mới**.

### 17.6. Case F — Tăng CPU sau khi vô hiệu ticket khẩn cấp

SOC nghi lộ ticket protection key và yêu cầu hủy khóa cũ. Sau rotation khẩn cấp, nhiều client thực hiện full handshake khiến CPU TLS terminator tăng và p95 handshake latency xấu đi.

**Đánh giá:** đây là **đánh đổi availability có thể dự đoán** khi vô hiệu một nhóm tickets. Phản ứng phù hợp không phải bật lại key có nguy cơ lộ; cần:

1. Điều tra phạm vi key bị lộ, nhóm nodes/tenants được cấp quyền.
2. Giữ yêu cầu full authentication và certificate validation.
3. Tăng capacity, rate limit kết nối không hợp lệ hoặc điều tiết rollout theo quy trình.
4. Quan sát p95 handshake, TLS errors và transaction SLO.
5. Phân phối key mới có kiểm soát, xác minh mọi node đã nghỉ key cũ.
6. Rà quyền secret store, audit export và thời hạn keys về sau.

### 17.7. Case G — Java HTTP client không hiển thị lần resume nào

Một nhóm Java dùng HTTP client với connection pooling, gửi 1.000 API calls và chờ thấy 1.000 session resumptions. Log chỉ cho biết một full TLS handshake.

**Phân tích:** có thể tất cả request dùng lại **một hoặc vài kết nối HTTPS đang mở**, nhất là HTTP/2. Không có 1.000 handshake mới để resume. Hãy đo **connection count** và tạo **hai TLS connections độc lập** trong lab nếu muốn kiểm tra riêng cơ chế resumption; không tắt pooling trong production chỉ để tạo số liệu đẹp.

### 17.8. Case H — Wi-Fi chuyển mạng, mobile app tạo kết nối mới

Thiết bị chuyển từ WLAN doanh nghiệp sang cellular và tạo QUIC connection mới. Session resumption có thể được thử từ ticket cũ, hoặc QUIC connection migration có thể giữ kết nối cũ nếu điều kiện hỗ trợ. Hai hành vi này **khác nhau**; mobile app có thể phải xác thực API lại nếu token hết hạn dù TLS resume thành công.

**Kiểm chứng:** phân biệt **new QUIC handshake/resumption** với **migration của connection ID đang tồn tại**, sau đó kiểm tra DNS, network policy, token/authorization và thời gian phản hồi từ client.

## 18. Checklist kiểm tra sản xuất

### 18.1. Giao thức và client

- [ ] Có danh sách TLS termination points, hostname/SNI, ALPN, phiên bản TLS, cipher policy và owner.
- [ ] Client/server ưu tiên TLS 1.3 theo mức hỗ trợ đã duyệt; không giữ phiên bản/cipher lỗi thời chỉ vì resumption.
- [ ] Certificate chain, SAN/hostname và trust roots được xác minh đúng ở mỗi hop.
- [ ] Resumption state được bảo vệ; không gửi ticket/PSK vào HTTP layer hoặc application cookie.
- [ ] Biết lúc nào HTTP/2 pooling hoặc QUIC migration làm **không có handshake mới**.
- [ ] Có test khi client/new connection không sở hữu ticket hoặc ticket hết hạn.

### 18.2. Ticket keys, policy và identity

- [ ] Key/lifetime/rotation được review theo nhu cầu và phân loại rủi ro.
- [ ] Key distribution có quyền tối thiểu, audit và giới hạn region/tenant/service.
- [ ] Có khả năng versioning, graceful rotation và chấp nhận full handshake khi không còn key cũ.
- [ ] Không cho ticket từ context này vô điều kiện resume ở tenant/environment khác.
- [ ] Có test certificate rotation, SNI/ALPN change, key loss và multi-node failover.
- [ ] TLS 1.3 dùng PSK+DHE khi cần forward secrecy và nền tảng hỗ trợ.
- [ ] mTLS client identity/role revocation được xử lý cả khi đang có ticket hợp lệ.
- [ ] Application authorization vẫn chạy độc lập trên mọi request.

### 18.3. 0-RTT early data

- [ ] 0-RTT **tắt** nếu chưa có use case rõ, risk review và application policy.
- [ ] Không xử lý payment/admin/data-changing routes bằng 0-RTT ngoài thiết kế đã kiểm chứng rất chặt.
- [ ] Không coi GET là an toàn chỉ vì tên method.
- [ ] Anti-replay policy được thiết kế cho nhiều nodes/regions nếu 0-RTT bật.
- [ ] Backend nhận biết/được bảo vệ khỏi early-data request cần từ chối.
- [ ] Retry semantics, idempotency và 425 Too Early được test bằng synthetic data.
- [ ] Giám sát early_data accepted/rejected, duplicate effects và privacy concerns.
- [ ] Khi gặp sự cố, có thể tắt riêng early data mà không tắt TLS 1.3.

### 18.4. Quan sát, ứng phó và bảo mật dữ liệu

- [ ] Có counters full/resumed handshakes, ticket issuance/acceptance, fallback reason khi có.
- [ ] Có độ trễ p50/p95/p99 handshake, CPU và application availability theo từng TLS hop.
- [ ] Có health checks cho edge exporter, key distribution và session cache.
- [ ] Không lưu raw ticket, PSK, session key log hoặc Authorization token vào SIEM chung.
- [ ] Có RBAC và retention phù hợp cho TLS debug traces, key audit và forensic artifacts.
- [ ] Có canary/rollback, capacity để chịu full handshakes sau key rotation.
- [ ] Có đầu mối SOC/NOC, change ticket, phiên bản policy và quy trình xử lý nghi lộ khóa.
- [ ] Có kiểm thử chéo TCP/HTTP2, UDP/HTTP3 nếu hệ thống hỗ trợ và từng region/tenant quan trọng.

### 18.5. Mẫu tiêu chí nghiệm thu

| Điều kiện | Pass khi | Fail/đòi điều tra khi |
| --- | --- | --- |
| Full handshake | Có certificate validation đúng và application connection hợp lệ | Chấp nhận chứng chỉ sai hoặc cố fallback insecure |
| Resumption | Chấp nhận ticket đúng context, có full fallback khi miss | Chấp nhận ticket hết hạn/sai tenant/policy |
| PSK+DHE | Negotiated mode được xác minh khi yêu cầu | Server rơi xuống psk_ke ngoài policy |
| mTLS authorization | Identity/role đang có hiệu lực, đã thu hồi bị từ chối theo policy | Ticket cũ bypass revocation/authorization |
| Ticket rotation | Node nhận key mới, key cũ nghỉ theo kế hoạch, SLO chấp nhận | Key distribution lộ, handshake errors hàng loạt |
| 0-RTT disabled | Không có early-data writes, policy log đúng | Edge xử lý state-changing request trước handshake |
| 0-RTT enabled có điều kiện | Route được duyệt; duplicate/replay controls có bằng chứng | Duplicate side effects hoặc retry không kiểm soát |
| Multi-tenant/region | Không nhận ticket ngoài authorized scope | Cross-scope acceptance không có thiết kế |
| Telemetry | Full/resumed/early data và health metric đầy đủ | Logs thiếu hoặc chứa PSK/key material |
| Origin security | Mỗi chặng TLS xác minh peer và network policy hợp lệ | Client-edge TLS tốt nhưng origin TLS bị bỏ kiểm tra |

## 19. Bài tập thiết kế và câu hỏi ôn tập

### 19.1. Bài tập thiết kế hệ thống

Một công ty triển khai:

~~~text
Client web/mobile
      |
      | TLS 1.3 / HTTP/2 hoặc HTTP/3
      v
CDN + WAF + Load balancer (multi-region)
      |
      | TLS tới origin
      v
Reverse proxy / API gateway
      |
      | mTLS trong service mesh
      v
Orders API / Payment API / Identity API
      |
      v
Database / event bus
~~~

Hệ thống nhận nhiều kết nối ngắn, cần giảm CPU TLS termination. Hai region có thể chuyển traffic qua nhau khi sự cố. Website có API chỉ đọc, thanh toán, tài khoản và webhook đối tác. Một số service yêu cầu mTLS client certificate.

**Yêu cầu nộp**:

1. **Sơ đồ từng điểm TLS termination**, ghi rõ peer/certificate, owner và sự khác nhau của TLS A/B/C.
2. **Quyết định resumption** tại từng hop: TLS version, session cache/tickets, PSK+DHE, ticket lifetime/key scope và fallback.
3. **Phân tách các route** có thể cân nhắc 0-RTT và route bắt buộc từ chối early data. Giải thích bằng **ngữ nghĩa side effects**, không chỉ HTTP method.
4. **Lộ trình rotate ticket keys** giữa hai region, bao gồm current/previous key, không gian tenant và những sự kiện có thể làm hit rate giảm.
5. **Xử lý revoked mTLS client**: thay certificate, thu hồi identity và kiểm tra authorization khi ticket vẫn còn.
6. **12 phép thử**: full handshake, resumed, expired ticket, wrong SNI/ALPN, certificate error, cross-tenant, region change, key rotation, 0-RTT deny, backend retry, origin TLS và fallback capacity.
7. **Metric và alerts** cho mỗi hop: full/resumed, accepted/rejected early data, p95 latency, CPU, key rollout, SIEM telemetry gap.
8. **Phương án ứng phó** khi nghi lộ ticket key không làm mất certificate validation hay mở origin bypass.

**Tiêu chí đạt:** thiết kế giữ TLS 1.3/peer verification đúng; không đồng nhất TLS session với đăng nhập ứng dụng; không xử lý side-effecting 0-RTT; ticket key không chia sẻ ngoài scope; có khả năng full fallback mà không giảm bảo mật.

### 19.2. Câu hỏi tự kiểm tra

**Câu 1.** Session resumption khác việc tái dùng một kết nối TCP/TLS đang mở thế nào?

*Gợi ý:* Resumption thiết lập **một kết nối TLS mới** dùng state/PSK từ phiên trước; connection reuse chỉ gửi thêm dữ liệu trên kết nối đã tồn tại, không cần handshake mới.

**Câu 2.** TLS 1.2 session ID khác TLS 1.2 session ticket thế nào?

*Gợi ý:* Session ID thường tra state trong cache server; ticket thường để client giữ blob được server bảo vệ, giúp server khôi phục state mà không nhất thiết tra cache tập trung.

**Câu 3.** Trong TLS 1.3, server có thể phát NewSessionTicket lúc nào?

*Gợi ý:* Thường sau handshake ban đầu, trong kênh TLS đã được bảo vệ. Client có thể không nhận/lưu nếu đóng kết nối quá sớm.

**Câu 4.** Có ticket nghĩa là lần kết nối mới chắc chắn được resume không?

*Gợi ý:* Không. Ticket có thể hết hạn, không được server/node biết, sai SNI/ALPN/context hoặc bị policy từ chối.

**Câu 5.** PSK binder dùng để làm gì và không làm gì?

*Gợi ý:* Giúp kiểm chứng client biết đúng PSK trong quá trình đề xuất resumption; không cấp quyền nghiệp vụ hoặc thay mTLS/application authorization.

**Câu 6.** So với TLS 1.3 full handshake, TLS 1.3 resumed 1-RTT có luôn bớt một RTT không?

*Gợi ý:* Không. Cả hai thường khoảng một RTT; lợi ích rõ rệt của resumption 1-RTT là giảm xử lý/bytes handshake. **0-RTT** mới cho phép gửi một số application data trước khi nhận phản hồi handshake.

**Câu 7.** Vì sao nên ưu tiên psk_dhe_ke hơn psk_ke trong nhiều hệ thống?

*Gợi ý:* PSK+DHE bổ sung fresh (EC)DHE và forward secrecy cho resumed 1-RTT traffic; PSK-only không có trao đổi ephemeral mới.

**Câu 8.** Nếu resumed handshake dùng PSK+DHE, early data 0-RTT có forward secrecy tương tự không?

*Gợi ý:* Không. Early data được tạo trước khi phần DHE mới đóng góp vào traffic secrets, nên không có fresh-DHE forward secrecy.

**Câu 9.** Ticket lifetime có đồng nhất với hạn JWT/cookie đăng nhập không?

*Gợi ý:* Không. TLS session state và authentication/authorization ứng dụng có vòng đời độc lập.

**Câu 10.** Vì sao session ticket TLS 1.2 chứa rủi ro đáng chú ý nếu key mã hóa ticket bị lộ?

*Gợi ý:* Có thể khôi phục session secrets tùy triển khai, ảnh hưởng phiên được resumption; full handshake dùng ECDHE không cho phép bỏ qua yêu cầu bảo vệ ticket key dài hạn.

**Câu 11.** Nguyên nhân nào khiến một ticket TLS 1.3 không hoạt động giữa hai edge nodes?

*Gợi ý:* Khác key scope, key version, cache state, policy hoặc tenant/SNI/ALPN. Full fallback đúng vẫn là kết quả an toàn.

**Câu 12.** Vì sao không nên bật 0-RTT cho API thanh toán?

*Gợi ý:* Replay/retry có thể tạo side effects trùng; 0-RTT không có bảo đảm chống replay như phần traffic sau handshake. Cần tắt hoặc thiết kế kiểm soát rất chặt.

**Câu 13.** Một HTTP GET có luôn an toàn khi dùng 0-RTT không?

*Gợi ý:* Không. Ứng dụng có thể làm thay đổi trạng thái gián tiếp hoặc có yêu cầu riêng về identity, dữ liệu nhạy cảm và replay.

**Câu 14.** Anti-replay cache cục bộ của từng region có đủ khi hai region có thể nhận cùng early data không?

*Gợi ý:* Không chắc. Cần đánh giá đồng bộ/cạnh tranh giữa nodes và bảo vệ ở tầng ứng dụng; lý tưởng là không xử lý side-effecting requests bằng 0-RTT.

**Câu 15.** Một user đăng xuất nhưng TLS resumption vẫn hoạt động: có nhất thiết là lỗi không?

*Gợi ý:* Không nhất thiết. TLS session và user login khác nhau; ứng dụng phải từ chối các request cần user auth nếu token/session đã vô hiệu. Lỗi xảy ra nếu resumption được dùng làm cơ chế cấp quyền thay ứng dụng.

**Câu 16.** Một mTLS certificate bị thu hồi nhưng resumed connection được chấp nhận. Cần kiểm tra gì?

*Gợi ý:* Ticket auth context, revocation/invalidation policy, full-handshake requirement, thời gian cấp ticket và authorization backend.

**Câu 17.** Tại sao bật TLS 1.3 tickets ở CDN chưa chứng minh origin được mã hóa?

*Gợi ý:* Client–CDN và CDN–origin là những TLS connections độc lập; cần cấu hình/xác minh TLS origin và network policy riêng.

**Câu 18.** Khi thay certificate server, có thể dựa vào một resumed handshake thành công để xác nhận certificate mới không?

*Gợi ý:* Không đủ. Resumed handshake thường không gửi lại full certificate; phải kiểm tra fresh full handshake với đúng hostname/SNI và trust store.

**Câu 19.** Tại sao khi hệ thống chỉ ghi một full handshake cho hàng trăm request HTTP/2 không nên coi là lỗi?

*Gợi ý:* HTTP/2 multiplexing có thể phục vụ nhiều request trên một kết nối TLS đã mở, không phát sinh handshake mới cho từng request.

**Câu 20.** Nếu SIEM thấy full handshake CPU tăng sau rotate key, nên bật lại khóa cũ bị nghi lộ không?

*Gợi ý:* Không. Đánh giá impact, bổ sung capacity và full fallback; xử lý secret compromise và rotation theo quy trình an toàn.

### 19.3. Bài tập đánh giá một bản log mô phỏng

Giả sử hệ thống báo:

~~~text
Time: 09:00Z
Edge A, TLS 1.3: full=700, resumed=300, 0rtt_accepted=0
Edge B, TLS 1.3: full=800, resumed=200, 0rtt_accepted=0

Time: 09:15Z (sau key rotation)
Edge A, TLS 1.3: full=950, resumed=50, 0rtt_accepted=0
Edge B, TLS 1.3: full=990, resumed=10, 0rtt_accepted=0

Other signals:
  TLS handshake errors: không tăng đáng kể
  API transaction success: ổn định
  CPU edge: tăng 12%
  TLS p95 latency: tăng nhẹ
  Key distribution logs: Edge B nhận key mới chậm hơn A
~~~

**Câu hỏi:**

1. Tính resumption hit rate theo công thức của mục 12.2 cho A/B ở hai mốc.
2. Có đủ căn cứ khẳng định user sessions bị lỗi không? Vì sao?
3. Nguyên nhân nào có thể giải thích Edge B thấp hơn A?
4. Cần điều tra những log nào để xác minh ticket key rollout thay vì chỉ thay load balancer?
5. Hướng khắc phục an toàn nếu vẫn phải retire key cũ là gì?

**Đáp án tham khảo:**

| Điểm đo | Trước rotation | Sau rotation |
| --- | --- | --- |
| Edge A | 300 / (700+300) = **30%** | 50 / (950+50) = **5%** |
| Edge B | 200 / (800+200) = **20%** | 10 / (990+10) = **1%** |

Đây là tỷ lệ **trên các handshakes thành công đã thống kê**, không phải tỷ lệ trên toàn bộ HTTP requests. Cần kiểm tra node key versions, secret distribution và ticket rejection reasons nếu có; không suy rằng user logout hoặc dữ liệu bị lộ. Giữ full fallback, cân nhắc capacity và rollout đồng bộ theo chính sách mà **không phục hồi key nghi lộ**.

## 20. Tổng kết

- **Session resumption** là cách xây dựng **kết nối TLS mới** bằng trạng thái từ phiên trước, không phải giữ TCP socket cũ, không phải HTTP cookie và không cấp quyền API.
- **TLS 1.2** có session ID/cache và session ticket; **TLS 1.3** sử dụng resumption PSK qua **NewSessionTicket**, PSK identity và binder.
- **Full TLS 1.3 và resumed 1-RTT** thường đều cần một RTT; resumption 1-RTT có thể giảm chi phí handshake. **0-RTT** cho phép gửi early data sớm nhưng có **replay risk** và không nên bật mặc định cho ứng dụng nhạy cảm.
- **PSK + (EC)DHE** bổ sung forward secrecy cho resumed 1-RTT traffic; **PSK-only** không có fresh DHE, còn **0-RTT early data** không nhận forward secrecy từ DHE mới.
- **Ticket protection keys và resumption PSKs là bí mật** cần bảo vệ, rotation, lifetime, scope và audit. Không lưu raw ticket/PSK trong log hoặc source code.
- **Không có ticket nào bảo đảm sẽ resume**: hết hạn, node đổi, key rotation, TLS policy, SNI/ALPN hoặc mTLS context thay đổi có thể dẫn đến **full handshake fallback** an toàn.
- **Certificate, mTLS identity và application authorization** có vòng đời riêng. Resumption không thay việc xác minh certificate ở kết nối đầu và không cho phép dùng quyền đã bị thu hồi ở API.
- Trong **CDN/WAF, reverse proxy, service mesh và cloud**, mỗi hop TLS có ticket/certificate/policy riêng; resumption ở edge không chứng minh origin được bảo vệ.
- **HTTP/2 pooling, HTTP/3/QUIC và QUIC migration** phải được phân biệt với TLS resumption; mọi quyết định cần dựa trên handshake thật và telemetry theo đúng điểm termination.
- Vận hành tốt cần **full/resumed/0-RTT metrics, key rollout health, CPU/latency/SLO, test fallback, canary/rollback và ứng phó khi nghi lộ khóa**.
- Hiệu quả của session resumption không được đánh đổi lấy **certificate verification, tính riêng tư, quyền ứng dụng hoặc an toàn nghiệp vụ**. Mục tiêu là giảm chi phí kết nối **trong khi giữ nguyên các ranh giới tin cậy**.
