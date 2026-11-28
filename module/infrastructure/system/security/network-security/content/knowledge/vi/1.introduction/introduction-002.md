# Mối liên hệ giữa mạng, ứng dụng, danh tính và dữ liệu

> **Chương:** Nhập môn  
> **Học phần:** SECURITY_NETWORK_SECURITY — An ninh mạng  
> **Trọng tâm:** Hiểu cách các biện pháp bảo vệ mạng, ứng dụng, danh tính và dữ liệu phối hợp để kiểm soát truy cập, giới hạn thiệt hại và phát hiện xâm nhập.

Một hệ thống chỉ thực sự an toàn khi **đúng chủ thể** được thực hiện **đúng hành động**, trên **đúng tài nguyên**, thông qua **đường kết nối được kiểm soát**, và dữ liệu được bảo vệ trong suốt vòng đời. Một tường lửa có thể ngăn kết nối trái phép nhưng không biết liệu người dùng đã đăng nhập có quyền xem đơn hàng của người khác hay không. Ngược lại, ứng dụng có kiểm tra quyền tốt vẫn có thể bị ảnh hưởng nếu cơ sở dữ liệu được mở trực tiếp ra Internet, tài khoản dịch vụ bị lộ hoặc bản sao lưu không được bảo vệ.

Bài học này đặt nền tảng cho học phần **SECURITY_NETWORK_SECURITY**: từ phân đoạn mạng, firewall, VPN, IDS/IPS và xác thực kết nối đến DNS, mạng không dây, môi trường đám mây, phân tích lưu lượng, mô hình hóa mối đe dọa và kiến trúc mạng an toàn. Trọng tâm là **mối quan hệ giữa các lớp bảo vệ**, không phải xem từng công nghệ như một giải pháp độc lập.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích vai trò riêng của mạng, ứng dụng, danh tính và dữ liệu, cũng như giới hạn của từng lớp.
2. Theo dõi một yêu cầu từ thiết bị người dùng đến cơ sở dữ liệu và xác định nơi cần xác thực, phân quyền, mã hóa, ghi log và giám sát.
3. Nhận diện **ranh giới tin cậy** (trust boundary), **đường đi của dữ liệu** (data flow) và các tình huống một lớp bảo vệ bị vượt qua nhưng lớp khác vẫn phải hoạt động.
4. Phân biệt xác thực kết nối, xác thực danh tính, phân quyền và quyền sở hữu dữ liệu.
5. Phác thảo một kiến trúc phòng vệ nhiều lớp cho ứng dụng web/API và xác định tín hiệu cần theo dõi.

## 2. Bốn góc nhìn về một hệ thống

Hãy xét một ứng dụng quản lý đơn hàng: khách hàng sử dụng trình duyệt, nhân viên hỗ trợ sử dụng trang quản trị, dịch vụ ứng dụng truy vấn cơ sở dữ liệu và hệ thống gửi thông báo qua một dịch vụ bên ngoài.

| Góc nhìn | Câu hỏi cần trả lời | Tài sản và điểm kiểm soát điển hình | Điều lớp này không tự đảm bảo |
|---|---|---|---|
| **Mạng (Network)** | Kết nối từ đâu đến đâu, qua giao thức và cổng nào? | DNS, tuyến mạng, firewall, phân đoạn mạng, VPN, security group, gateway, IDS/IPS | Người gọi có quyền xem từng bản ghi cụ thể hay không |
| **Ứng dụng (Application)** | Yêu cầu muốn thực hiện nghiệp vụ gì và có hợp lệ không? | Web/API, xác thực phiên, kiểm tra đầu vào, phân quyền tại đối tượng, rate limit, WAF | Đường mạng và hạ tầng lưu trữ đã được cô lập đầy đủ hay chưa |
| **Danh tính (Identity)** | Ai hoặc dịch vụ nào đang gọi, chứng cứ xác thực và quyền hạn là gì? | IdP, MFA, OAuth 2.0/OIDC, tài khoản dịch vụ, chứng chỉ, role, policy | Một yêu cầu được phép truy cập mọi dữ liệu chỉ vì chủ thể đã đăng nhập |
| **Dữ liệu (Data)** | Thông tin nào cần bảo vệ, nằm ở đâu và ai được sử dụng? | CSDL, object storage, khóa mã hóa, phân loại dữ liệu, backup, audit, chính sách lưu giữ | Các cổng kết nối bên ngoài có được kiểm soát hay không |

Một cách ghi nhớ:

- **Mạng** kiểm soát *đường đi và phạm vi kết nối*.
- **Danh tính** xác minh *chủ thể truy cập* và cung cấp thông tin về quyền hạn.
- **Ứng dụng** quyết định *hành động nghiệp vụ nào được phép* trong ngữ cảnh cụ thể.
- **Dữ liệu** là *tài sản cần được bảo vệ*, đồng thời là nơi các quyền truy cập cuối cùng phát huy tác dụng.

Bốn góc nhìn này liên kết với nhau. Chẳng hạn, cùng một API đọc đơn hàng có thể được gọi qua mạng hợp lệ, bằng access token hợp lệ, nhưng vẫn phải bị từ chối nếu đơn hàng thuộc khách hàng khác. Kiểm tra **quyền trên từng đối tượng** là mắt xích quyết định ở bước cuối.

### 2.1. Ba khái niệm thường bị nhầm lẫn

**Xác thực kết nối** trả lời: *Hai đầu kết nối có đang giao tiếp với đúng đối tác kỹ thuật không?* TLS giúp mã hóa và bảo vệ tính toàn vẹn dữ liệu trên đường truyền; kiểm tra chứng chỉ máy chủ giúp máy khách xác thực điểm cuối. Với mTLS, hai bên cùng trình chứng chỉ để xác thực lẫn nhau.

**Xác thực danh tính (authentication)** trả lời: *Chủ thể nào đang yêu cầu?* Ví dụ, người dùng đăng nhập qua nhà cung cấp danh tính (Identity Provider, IdP) bằng mật khẩu và MFA; hoặc một workload chứng minh danh tính bằng chứng chỉ/credential riêng.

**Phân quyền (authorization)** trả lời: *Chủ thể này được làm gì với tài nguyên này, ngay lúc này?* Quyết định có thể phụ thuộc vai trò, quyền, người sở hữu bản ghi, trạng thái giao dịch, thiết bị, mức nhạy cảm và các điều kiện bổ sung.

Một kết nối TLS thành công **không** có nghĩa người gọi đã đăng nhập; một lần đăng nhập thành công **không** đồng nghĩa với quyền truy cập mọi chức năng; một role hợp lệ **không** thay thế được kiểm tra chủ sở hữu bản ghi.

## 3. Theo dấu một yêu cầu từ người dùng đến dữ liệu

Sơ đồ sau minh họa ứng dụng web/API triển khai theo nhiều vùng. Các đường nét đứt thể hiện chức năng hỗ trợ có thể diễn ra ngoài luồng dữ liệu chính.

~~~mermaid
flowchart LR
    U["Người dùng<br/>Trình duyệt / thiết bị"] --> DNS["Phân giải DNS"]
    DNS --> EDGE["Biên mạng<br/>CDN / WAF / Gateway"]
    EDGE --> API["Ứng dụng / API"]
    API --> DB[("Cơ sở dữ liệu")]
    U -. "Đăng nhập" .-> IDP["Identity Provider<br/>MFA / OIDC"]
    API -. "Xác minh token / chính sách" .-> IDP
    API -. "Log / cảnh báo" .-> OBS["Giám sát / SIEM"]
    EDGE -. "Log / cảnh báo" .-> OBS
    DB -. "Audit" .-> OBS
    KMS["Quản lý khóa / bí mật"] -. "Cấp và quản lý khóa" .-> DB
~~~

Sơ đồ đơn giản hóa vị trí triển khai: DNS giải tên miền thành địa chỉ để máy khách xác định đích; kết nối thực tế được thiết lập tới hệ thống biên. Một CDN, WAF, load balancer hoặc API gateway có thể là các thành phần riêng biệt.

### Bước 1 — Tìm đúng điểm đến và thiết lập kênh truyền

Người dùng mở trang HTTPS. Thiết bị thường tra cứu DNS trước khi tạo kết nối tới máy chủ hoặc dịch vụ biên. TLS bảo vệ tính bí mật và toàn vẹn nội dung trong phiên truyền, đồng thời xác minh máy chủ thông qua chứng chỉ được kiểm tra hợp lệ.

Các điểm cần lưu ý:

- **DNS** có thể bị thao túng để hướng người dùng sang đích khác; kiểm tra chứng chỉ TLS vẫn rất quan trọng. **DNSSEC** hỗ trợ xác minh tính toàn vẹn/xuất xứ dữ liệu DNS khi được cấu hình và kiểm chứng đúng, nhưng **không mã hóa** truy vấn DNS. **DoH/DoT** mã hóa kênh truy vấn DNS nhưng không tự thay thế DNSSEC hoặc xác thực ứng dụng.
- **Wi-Fi công cộng** và mạng trung gian có thể quan sát metadata kết nối; HTTPS vẫn cần được sử dụng. Không được xem việc kết nối vào Wi-Fi nội bộ là bằng chứng người dùng đáng tin cậy.
- **VPN** tạo đường truy cập được bảo vệ tới một phạm vi mạng, nhưng một kết nối VPN thành công không trao quyền sử dụng mọi API hoặc dữ liệu trong phạm vi đó.

### Bước 2 — Kiểm soát đường vào mạng và vùng ứng dụng

Gateway và firewall chỉ cho phép các luồng cần thiết đi qua. Ví dụ, Internet có thể truy cập HTTPS của gateway; gateway được phép gọi dịch vụ ứng dụng; chỉ dịch vụ ứng dụng được phép kết nối cổng cơ sở dữ liệu. IDS có thể phát hiện và cảnh báo lưu lượng nghi vấn; IPS có thể áp dụng chính sách chặn tương ứng.

Chính sách mạng giảm **bề mặt tấn công** (attack surface) và **bán kính ảnh hưởng** (blast radius). Tuy nhiên, đối với nhiều hệ thống, mọi người dùng cuối đều đi vào cùng cổng HTTPS. Để phân biệt khách hàng A và B, lớp mạng cần dựa vào ứng dụng/danh tính hoặc các điểm thực thi chính sách có hiểu ngữ cảnh cao hơn.

### Bước 3 — Xác định danh tính người dùng hoặc dịch vụ

Ứng dụng chuyển người dùng tới IdP để đăng nhập theo luồng thích hợp. Với OIDC, **ID token** mô tả sự kiện xác thực và danh tính cho phía ứng dụng cần thông tin đó; với OAuth 2.0, **access token** được thiết kế để client gọi tài nguyên/API theo phạm vi đã cấp. API phải sử dụng loại token thích hợp, kiểm tra chữ ký hoặc xác thực token theo cơ chế đã định, cùng các thuộc tính như **issuer, audience, thời hạn hiệu lực** và quyền/scope cần thiết.

Đối với lời gọi giữa các dịch vụ, hệ thống cần danh tính workload riêng: tài khoản dịch vụ, credential ngắn hạn, certificate/mTLS hoặc cơ chế do nền tảng quản lý. **Không dùng chung tài khoản đặc quyền** cho mọi dịch vụ chỉ vì chúng nằm trong cùng mạng.

### Bước 4 — Ứng dụng áp dụng quy tắc nghiệp vụ

API xác định thao tác và đối tượng được yêu cầu. Với **GET /api/orders/8471**, câu hỏi không dừng ở “token có quyền orders:read không?” mà còn bao gồm “đơn hàng 8471 có thuộc người gọi không, hoặc người gọi có một quyền hỗ trợ đặc biệt được giới hạn phù hợp không?”.

Ứng dụng đồng thời kiểm tra cấu trúc yêu cầu, tham số, giới hạn kích thước, trạng thái nghiệp vụ và quyền trên đối tượng. WAF có thể giảm một số lưu lượng khai thác phổ biến, nhưng không thể hiểu hết quy tắc chủ sở hữu hay trạng thái nghiệp vụ riêng của hệ thống.

### Bước 5 — Truy cập và bảo vệ dữ liệu

Dịch vụ ứng dụng sử dụng danh tính riêng, chỉ có quyền CSDL hoặc bucket tối thiểu cần cho chức năng của nó. Dữ liệu nhạy cảm được mã hóa khi lưu trữ khi phù hợp; khóa mã hóa được quản lý tách biệt và cấp quyền sử dụng chặt chẽ. Bản sao lưu, môi trường thử nghiệm, dữ liệu xuất báo cáo và log cũng phải được bảo vệ.

**Mã hóa khi lưu trữ (encryption at rest) không tự chặn được truy vấn hợp lệ do một dịch vụ bị chiếm quyền thực hiện.** Vì vậy phải kết hợp phân quyền dữ liệu, giới hạn dịch vụ có thể truy cập, phát hiện hành vi bất thường và kiểm soát dữ liệu rời khỏi hệ thống.

### Bước 6 — Ghi nhận bằng chứng để phát hiện và điều tra

Gateway có thể ghi nguồn yêu cầu và trạng thái kết nối; ứng dụng ghi chủ thể, hành động, đối tượng, quyết định phân quyền và mã lỗi; CSDL ghi truy cập/quản trị quan trọng. Các hệ thống giám sát ghép sự kiện theo **request ID/correlation ID**, mốc thời gian và danh tính liên quan.

Log không nên chứa mật khẩu, access token, khóa bí mật hoặc nguyên văn dữ liệu nhạy cảm. Chỉ ghi trường đủ để phân tích sự cố và áp dụng chính sách giữ/xóa log phù hợp.

## 4. Ranh giới tin cậy: nơi bắt buộc kiểm tra lại

**Ranh giới tin cậy** xuất hiện khi thông tin hoặc yêu cầu đi từ miền có chính sách, chủ thể vận hành hay mức đảm bảo khác sang miền kế tiếp. Mỗi lần vượt ranh giới đều có giả định cần kiểm chứng.

| Ranh giới | Rủi ro nếu tin tưởng ngầm | Kiểm tra cần có |
|---|---|---|
| Thiết bị người dùng → Internet/gateway | Thiết bị hoặc mạng nguồn có thể không an toàn | TLS, kiểm tra request, rate limit, bảo vệ DDoS phù hợp |
| Gateway → ứng dụng | Yêu cầu đến từ gateway chưa chắc hợp lệ về nghiệp vụ; header nguồn có thể bị giả mạo nếu không kiểm soát | Chỉ tin header do proxy tin cậy thiết lập, xác thực token/phiên, validation |
| Người dùng → API | Người dùng đăng nhập có thể yêu cầu tài nguyên ngoài phạm vi | Kiểm tra role/scope **và** quyền trên từng đối tượng |
| Dịch vụ A → dịch vụ B | Dịch vụ nội bộ có thể bị xâm nhập hoặc vượt quyền | Danh tính workload, mTLS khi phù hợp, authorization, giới hạn đường mạng |
| API → CSDL/kho đối tượng | Credential dịch vụ bị lộ hoặc quyền lưu trữ quá rộng | Tài khoản riêng, least privilege, phân đoạn, mã hóa, audit |
| Hệ thống → đối tác/Internet | Rò rỉ dữ liệu do gửi đến đích bất ngờ hoặc tích hợp bị xâm nhập | Egress policy, kiểm tra đích, giới hạn dữ liệu chia sẻ và xác thực đối tác |
| Production → backup/dev/analytics | Bản sao dữ liệu có thể yếu bảo mật hơn bản gốc | Phân loại, ẩn danh/giảm dữ liệu, tách quyền, mã hóa, kiểm soát lưu giữ |

Chẳng hạn, một dịch vụ backend nằm trong mạng riêng vẫn cần xác thực danh tính khi gọi dịch vụ thanh toán. Địa chỉ IP nội bộ có thể thay đổi trong Kubernetes hoặc cloud, và một workload bên trong mạng có thể bị chiếm quyền. **“Nằm bên trong” là thuộc tính vị trí, không phải bằng chứng được phép truy cập.**

### Defense in depth và Zero Trust bổ sung nhau như thế nào?

**Phòng vệ nhiều lớp (defense in depth)** kết hợp nhiều biện pháp độc lập tương đối để một lỗi đơn lẻ khó dẫn đến thất bại toàn bộ: firewall giới hạn đường mạng, danh tính xác thực chủ thể, ứng dụng kiểm tra nghiệp vụ, dữ liệu giới hạn quyền đọc/ghi, hệ thống giám sát phát hiện sai lệch.

**Zero Trust** là cách thiết kế không trao tin cậy mặc định chỉ vì một yêu cầu xuất phát từ mạng nội bộ. Mỗi truy cập cần được đánh giá theo danh tính, thiết bị, tài nguyên, ngữ cảnh và chính sách; quyền nên ở mức tối thiểu, thời gian hiệu lực được giới hạn và có giám sát liên tục. Zero Trust **không đồng nghĩa** bỏ firewall, VPN hoặc phân đoạn mạng; các cơ chế đó vẫn có ích khi được phối hợp với kiểm tra danh tính và phân quyền.

## 5. Mối quan hệ giữa các công nghệ bảo mật mạng và bốn lớp

| Công nghệ/biện pháp | Vai trò chính | Lớp phải phối hợp |
|---|---|---|
| **Segmentation, VLAN, security group, network policy** | Phân vùng và giới hạn luồng đông–tây giữa các hệ thống | Danh tính workload và quyền truy cập dịch vụ/dữ liệu |
| **Firewall L3/L4** | Lọc theo IP, giao thức, cổng, trạng thái kết nối | API authorization vì nhiều người dùng cùng truy cập cổng HTTPS |
| **WAF/API gateway** | Kiểm soát request HTTP, giới hạn tốc độ, áp dụng một số chính sách tập trung | Ứng dụng vẫn phải kiểm tra nghiệp vụ và quyền đối tượng |
| **VPN/ZTNA** | Kiểm soát đường kết nối hoặc truy cập từ xa theo chính sách | Đăng nhập/MFA, trạng thái thiết bị, phân quyền tài nguyên |
| **TLS/mTLS/PKI** | Bảo vệ kênh truyền, xác thực endpoint và có thể xác thực hai chiều | Quản lý vòng đời certificate, user identity, authorization |
| **IDS/IPS, NDR** | Nhận diện mẫu lưu lượng hoặc hành vi mạng đáng ngờ; IPS có thể chặn | Log ứng dụng, IdP, CSDL để hiểu ý nghĩa của cảnh báo |
| **DNS filtering, DNSSEC, DoH/DoT** | Kiểm soát/phát hiện tên miền nguy hiểm, xác minh DNS, bảo vệ kênh phân giải | TLS, an toàn endpoint và kiểm soát request ứng dụng |
| **Wi-Fi enterprise, 802.1X/NAC** | Kiểm soát thiết bị/người dùng tham gia mạng không dây hoặc mạng nội bộ | Chính sách danh tính thiết bị, phân vùng mạng, TLS cho ứng dụng |
| **Cloud IAM, private networking, KMS** | Quản lý quyền tài nguyên cloud, giới hạn đường mạng và sử dụng khóa | Quyền nghiệp vụ tại API và kiểm soát dữ liệu ở cấp ứng dụng |

**Không có một công nghệ nào thay thế trọn vẹn các lớp còn lại.** Ví dụ, mTLS có thể chứng minh “dịch vụ orders-api đang gọi database-proxy” nhưng không chứng minh “khách hàng Nguyễn A có quyền xem đơn hàng của khách hàng B”. Cần đưa ngữ cảnh danh tính người dùng và chính sách dữ liệu vào quyết định tại ứng dụng.

## 6. Ví dụ xuyên suốt: API xem đơn hàng

### 6.1. Tình huống và tài sản

Giả sử hệ thống có ba loại chủ thể:

- **Khách hàng:** xem đơn hàng do mình sở hữu.
- **Nhân viên hỗ trợ:** chỉ xem một đơn hàng khi có yêu cầu hỗ trợ hợp lệ và đúng phạm vi công việc.
- **Dịch vụ gửi thông báo:** chỉ nhận dữ liệu tối thiểu để gửi thông báo, không được đọc toàn bộ hồ sơ khách hàng.

Đơn hàng chứa mã đơn, danh sách mặt hàng, số tiền, địa chỉ giao hàng và thông tin liên hệ. Thông tin liên hệ, địa chỉ, lịch sử mua sắm là dữ liệu cần bảo vệ theo chính sách và yêu cầu pháp lý áp dụng.

Người dùng gọi:

~~~http
GET /api/orders/8471 HTTP/1.1
Host: shop.example
Authorization: Bearer <access-token-da-che>
X-Request-ID: req-demo-001
~~~

Đây là ví dụ minh họa; chuỗi trong dấu ngoặc nhọn là chỗ giữ chỗ, không phải token thật. Client có thể cung cấp mã truy vết, nhưng hệ thống cần kiểm soát hoặc sinh lại các trường định danh truy vết nếu dùng chúng cho quyết định tin cậy.

### 6.2. Tập điều kiện để cho phép

API cần kết hợp các kiểm tra thay vì kết luận từ một thuộc tính đơn lẻ:

~~~text
function mayReadOrder(request, order):
    token = authenticateAccessToken(request)
    if token is invalid:
        return DENY

    if token.audience != "orders-api":
        return DENY
    if "orders:read" not in token.scopes:
        return DENY

    if order.customerId == token.subjectId:
        return ALLOW

    if token.role == "support"
       and request.supportCase.isActive
       and request.supportCase.orderId == order.id
       and request.supportCase.assigneeId == token.subjectId:
        return ALLOW_WITH_AUDIT

    return DENY
~~~

Đây là **mã giả diễn giải chính sách**, không phải đoạn mã có thể triển khai trực tiếp. Trong hệ thống thực, hồ sơ hỗ trợ phải được tải/kiểm tra từ nguồn tin cậy phía máy chủ, không dựa vào một mã hoặc cờ do client tự khai báo. Token hợp lệ còn cần kiểm tra issuer, thời hạn, chữ ký hoặc introspection, cách quản lý khóa và các ràng buộc phù hợp với thiết kế hệ thống.

Điểm cốt lõi:

1. **Firewall** cho phép kết nối cần thiết đến API, nhưng không ra quyết định về quyền đọc đơn 8471.
2. **IdP** xác thực danh tính, còn **API** kiểm tra scope và quyền với đơn hàng.
3. **CSDL** chỉ chấp nhận kết nối từ workload được phép và cấp cho workload đúng quyền cần dùng.
4. **Audit log** ghi ai đã đọc đơn nào, lúc nào, kết quả cho phép/từ chối và lý do ở mức phù hợp.
5. **Dữ liệu phản hồi** chỉ chứa những trường cần thiết cho màn hình hoặc nghiệp vụ đang thực hiện.

### 6.3. Điều gì xảy ra nếu thiếu một kiểm tra?

Nếu API chỉ kiểm tra token có scope **orders:read** rồi trả về mọi đơn theo tham số URL, khách hàng A có thể nhận dữ liệu đơn của B dù cả hai đều đi qua HTTPS và token của A là hợp lệ. Đây là dạng lỗi **Broken Object Level Authorization (BOLA)**, đôi khi được nhắc tới trong bối cảnh truy cập trực tiếp đến đối tượng không an toàn (IDOR).

Ngược lại, nếu ứng dụng phân quyền tốt nhưng CSDL được mở trên Internet cùng credential mặc định, kẻ xâm nhập có thể đi vòng qua toàn bộ API. **Kiểm soát quyền ở ứng dụng và cô lập mạng bảo vệ những đường tấn công khác nhau.**

### 6.4. Khi dịch vụ nội bộ bị chiếm quyền

Giả sử một dịch vụ chỉ có nhiệm vụ gửi thông báo bị xâm nhập. Mức thiệt hại phụ thuộc vào nhiều điều kiện:

| Kiểm soát có sẵn | Giới hạn thiệt hại dự kiến |
|---|---|
| Phân đoạn mạng: notification-service không được kết nối trực tiếp database | Giảm khả năng truy cập trái phép CSDL qua mạng |
| Danh tính dịch vụ riêng và credential ngắn hạn | Giảm nguy cơ một credential dùng được cho nhiều dịch vụ |
| API nội bộ phân quyền theo scope và nghiệp vụ | Ngăn yêu cầu lấy danh sách khách hàng ngoài quyền chức năng |
| Chỉ gửi dữ liệu tối thiểu cho dịch vụ thông báo | Giảm lượng thông tin có sẵn ngay cả khi dịch vụ bị xâm nhập |
| Egress control, audit và cảnh báo lưu lượng bất thường | Hạn chế một số đường truyền dữ liệu ra ngoài và hỗ trợ phát hiện |

Một kiểm soát có thể giảm rủi ro mà không loại bỏ hoàn toàn. Chẳng hạn, egress policy theo tên miền/IP không tự ngăn dữ liệu bị gửi tới một đích được phép nhưng sử dụng sai mục đích; cần cả giới hạn dữ liệu và hành vi tại ứng dụng.

## 7. Mô hình hóa mối đe dọa theo luồng dữ liệu

Mô hình hóa mối đe dọa (threat modeling) nên bắt đầu từ **tài sản cần bảo vệ**, **chủ thể**, **luồng dữ liệu**, **ranh giới tin cậy** và **khả năng của kẻ tấn công**. Có thể sử dụng khung STRIDE để gợi mở nhóm rủi ro; không cần áp dụng máy móc mỗi nhóm cho mọi thành phần.

| Nhóm STRIDE | Ví dụ trong hệ thống đơn hàng | Lớp phòng vệ liên quan |
|---|---|---|
| **Spoofing — giả mạo danh tính** | Credential khách hàng hoặc dịch vụ bị đánh cắp | MFA chống lừa đảo khi phù hợp, quản lý phiên, danh tính workload, hạn chế credential |
| **Tampering — sửa đổi trái phép** | Request, giá tiền hoặc trạng thái đơn bị sửa trên đường đi hay trong ứng dụng | TLS, xác thực request, validation, kiểm tra nghiệp vụ, kiểm soát ghi dữ liệu |
| **Repudiation — chối bỏ hành động** | Không xác định được ai đã truy cập/sửa đơn hàng | Audit có bảo vệ, thời gian đồng bộ, request ID, lưu giữ log phù hợp |
| **Information disclosure — lộ thông tin** | Khách hàng xem đơn của người khác; backup bị tải xuống | Quyền đối tượng, least privilege, mã hóa, chính sách backup, DLP phù hợp |
| **Denial of service — từ chối dịch vụ** | Lượng truy cập lớn làm gateway/API/DB quá tải | Rate limit, DDoS protection, quota, autoscaling, giới hạn tài nguyên |
| **Elevation of privilege — leo thang đặc quyền** | Tài khoản dịch vụ thường được cấp quyền quản trị | Phân quyền tối thiểu, tách vai trò, policy review, giám sát thay đổi quyền |

Khi phân tích, cần hỏi lần lượt:

1. **Cần bảo vệ điều gì?** Ví dụ: địa chỉ giao hàng, token truy cập, khóa mã hóa, tính sẵn sàng của API.
2. **Ai có thể tiếp cận?** Người dùng, nhân viên, thiết bị, ứng dụng đối tác, workload và quản trị viên.
3. **Hệ thống tin điều gì?** Ví dụ: “request đến từ gateway thì đáng tin” hoặc “dịch vụ nội bộ không bị xâm nhập”.
4. **Giả định nào có thể sai?** Token bị lộ, cấu hình security group bị mở rộng, quyền CSDL bị cấp dư.
5. **Lớp nào ngăn chặn/phát hiện/giảm hậu quả?** Gắn biện pháp cụ thể với từng điểm trên luồng.
6. **Kiểm chứng như thế nào?** Dùng kiểm tra quyền truy cập, rà soát cấu hình, đánh giá log và diễn tập sự cố trong phạm vi được phép.

### Đường tấn công và bán kính ảnh hưởng

Không nên đánh giá rủi ro chỉ bằng việc “kẻ tấn công đã vào được mạng hay chưa”. Một đường tấn công có thể gồm nhiều bước: lấy được một danh tính → gọi một API → tận dụng quyền quá rộng → truy cập dữ liệu nhạy cảm → chuyển dữ liệu ra ngoài. Mỗi mũi tên là một nơi có thể triển khai kiểm soát.

**Bán kính ảnh hưởng** là phạm vi tài nguyên/dữ liệu có thể chịu tác động khi một thành phần hoặc danh tính bị xâm nhập. Phân đoạn mạng, tài khoản riêng, quyền tối thiểu, cô lập môi trường, giới hạn truy vấn và phân loại dữ liệu là những cách giảm bán kính đó.

## 8. Thiết kế kiến trúc mẫu cho ứng dụng nhiều tầng

Một kiến trúc tham chiếu có thể gồm các vùng sau:

~~~mermaid
flowchart TB
    CLIENT["Internet / thiết bị người dùng"]
    EDGE["Vùng biên: CDN, WAF, API gateway"]
    APP["Vùng ứng dụng: orders-api, auth middleware"]
    DATA["Vùng dữ liệu: database, object storage, backup"]
    EXT["Dịch vụ bên ngoài được cấp phép"]
    ID["IdP / IAM / danh tính workload"]
    MON["Log, IDS/IPS, giám sát và phản ứng"]
    CLIENT -->|"HTTPS 443"| EDGE
    EDGE -->|"Chỉ cổng dịch vụ cần thiết"| APP
    APP -->|"Chỉ kết nối DB được phép"| DATA
    APP -->|"Egress hạn chế"| EXT
    CLIENT -. "Đăng nhập / MFA" .-> ID
    APP -. "Xác thực / phân quyền" .-> ID
    EDGE -. "Telemetry" .-> MON
    APP -. "Telemetry" .-> MON
    DATA -. "Audit" .-> MON
~~~

Khi thiết kế thật, có thể chọn private subnet/VPC, network policy của Kubernetes, security group cloud, service mesh hoặc giải pháp tương đương tùy môi trường. Tên công nghệ có thể khác, nhưng các yêu cầu chức năng vẫn tương tự:

- **Đường vào:** chỉ công bố thành phần cần phục vụ bên ngoài; kiểm soát HTTPS, chính sách gateway và bảo vệ lưu lượng lớn.
- **Đường nội bộ:** dịch vụ chỉ được gọi những đích phục vụ chức năng; các giao tiếp nhạy cảm cần xác thực endpoint/workload và mã hóa phù hợp.
- **Đường ra:** hạn chế kết nối tới dịch vụ bên ngoài, quản lý chứng chỉ và bí mật, quan sát hành vi truyền dữ liệu.
- **Danh tính:** dùng danh tính riêng cho người, máy và workload; quyền được cấp theo chức năng, có quy trình thu hồi, cập nhật và kiểm tra định kỳ.
- **Dữ liệu:** giảm thu thập không cần thiết, phân tách quyền đọc/ghi, mã hóa, quản lý khóa, backup/khôi phục và vòng đời dữ liệu.
- **Giám sát:** liên kết sự kiện giữa mạng, ứng dụng, IdP và dữ liệu để nhận diện chuỗi hoạt động thay vì chỉ cảnh báo riêng lẻ.

### 8.1. Vai trò của điểm thực thi chính sách

Trong hệ thống phức tạp, có thể tách **Policy Decision Point (PDP)**, nơi quyết định cho phép hay từ chối, khỏi **Policy Enforcement Point (PEP)**, nơi thực thi quyết định. PEP có thể ở gateway, proxy, middleware hoặc chính dịch vụ ứng dụng. Phân quyền liên quan đến **chủ sở hữu bản ghi, trạng thái đơn hàng hoặc điều kiện nghiệp vụ** thường cần dữ liệu đáng tin cậy từ ứng dụng; không nên giao toàn bộ cho firewall hoặc gateway chỉ nhìn thấy IP và đường dẫn.

Với workload cloud, quyền IAM bảo vệ tài nguyên hạ tầng (ví dụ quyền gọi object storage hoặc lấy secret), trong khi phân quyền trong ứng dụng bảo vệ tài nguyên nghiệp vụ (ví dụ chỉ chủ đơn hàng mới đọc được đơn). Hai chính sách bổ sung nhau và nên có chủ sở hữu rõ ràng.

### 8.2. Khi kết nối chạy qua Wi-Fi, VPN và cloud

Điểm đáng quan tâm không chỉ là topology cố định:

- Thiết bị trên Wi-Fi doanh nghiệp có thể dùng **802.1X/NAC** để kiểm soát tham gia mạng, nhưng từng ứng dụng vẫn yêu cầu danh tính và chính sách truy cập.
- Người làm việc từ xa có thể dùng **VPN hoặc truy cập theo ứng dụng** để bảo vệ kết nối; quyền truy cập phải thu hẹp theo nhu cầu công việc.
- Trong cloud, **VPC/subnet/security group** bảo vệ đường mạng; **IAM/workload identity** quyết định thao tác với tài nguyên; **KMS** quản lý quyền sử dụng khóa; API vẫn kiểm tra quyền nghiệp vụ.
- Trong mô hình lai (hybrid), những đường nối on-premises ↔ cloud là **ranh giới tin cậy** cần mã hóa, định tuyến, phân đoạn và giám sát phù hợp.

## 9. Quan sát và phản ứng: ghép tín hiệu từ nhiều lớp

Một sự kiện đáng nghi có thể vô hình nếu chỉ nhìn vào một nguồn log. Ví dụ: người dùng đăng nhập thành công từ một thiết bị mới, sau đó gửi nhiều yêu cầu đọc các mã đơn liên tiếp; phần lớn bị từ chối, nhưng một số được trả về do cấu hình quyền sai. Firewall có thể chỉ thấy lưu lượng HTTPS bình thường. Kết hợp sự kiện từ IdP, API và CSDL mới cho thấy bức tranh đầy đủ.

| Nguồn tín hiệu | Ví dụ trường có ích | Phát hiện hỗ trợ |
|---|---|---|
| **DNS / gateway / firewall** | Thời gian, nguồn/đích, tên miền, phương thức, đường dẫn đã giảm nhạy cảm, trạng thái, byte truyền | Kết nối bất thường, quét bề mặt, tăng đột biến lưu lượng, đích egress lạ |
| **IdP / IAM** | Subject ID, ứng dụng/client, kết quả đăng nhập, MFA, cấp/thu hồi quyền, thiết bị | Đăng nhập bất thường, thay đổi quyền, đăng nhập thất bại lặp lại |
| **API / ứng dụng** | Request ID, subject, action, resource type/ID đã xử lý phù hợp, quyết định allow/deny, mã lỗi | Truy cập sai đối tượng, tăng 403/404, lạm dụng thao tác |
| **CSDL / kho dữ liệu** | Danh tính dịch vụ, hoạt động quản trị, lượng dữ liệu đọc/ghi, truy vấn nhạy cảm theo chính sách | Truy vấn hàng loạt, thao tác bất thường, tải/export dữ liệu |
| **Hệ thống quản lý khóa** | Dịch vụ gọi khóa, thao tác sử dụng/đổi khóa, kết quả | Sử dụng khóa ngoài thời gian/phạm vi kỳ vọng |

Cần đồng bộ thời gian, bảo vệ tính toàn vẹn của log, áp dụng quyền đọc log tối thiểu, quản lý thời hạn lưu giữ và giảm/ẩn dữ liệu nhạy cảm. Một cảnh báo có chất lượng thường là **một quan hệ bất thường giữa các nguồn**, không đơn thuần là một địa chỉ IP lạ.

### Một số chỉ số theo dõi có ý nghĩa

- Tỷ lệ truy cập bị từ chối theo API, loại tài nguyên và nhóm chủ thể; chú ý đột biến sau khi thay đổi chính sách.
- Số tài khoản dịch vụ có quyền quản trị hoặc dùng chung credential; số quyền dư đã loại bỏ.
- Số luồng mạng giữa các vùng không có nhu cầu nghiệp vụ hoặc kết nối trực tiếp tới kho dữ liệu.
- Tỷ lệ tài sản/dữ liệu quan trọng được gắn phân loại, có người chịu trách nhiệm và có nhật ký truy cập.
- Thời gian từ phát hiện đến xử lý một hành vi truy cập bất thường, cùng khả năng truy vết từ gateway tới dữ liệu.

Chỉ số cần được đọc theo bối cảnh. Ví dụ, tỷ lệ từ chối tăng có thể do một biện pháp ngăn chặn đang hoạt động đúng, nhưng cũng có thể do cấu hình quyền làm hỏng luồng nghiệp vụ.

## 10. Quy trình xây dựng phòng vệ nhiều lớp

Với một tính năng hoặc ứng dụng mới, có thể thực hiện theo trình tự sau:

**Bước 1: Lập danh mục tài sản và phân loại dữ liệu.** Xác định hệ thống xử lý những loại dữ liệu nào, mức nhạy cảm, nơi lưu trữ, bản sao, thời hạn lưu giữ và người chịu trách nhiệm. Ví dụ, thông tin thanh toán có thể có yêu cầu riêng cao hơn dữ liệu danh mục công khai.

**Bước 2: Vẽ đường đi của yêu cầu và dữ liệu.** Liệt kê tác nhân, endpoint, dịch vụ, CSDL, mạng trung gian, tích hợp bên ngoài. Đánh dấu mọi đường vào, đường ra và ranh giới tin cậy; không bỏ quên job chạy nền, backup, bảng điều khiển quản trị và quy trình xuất báo cáo.

**Bước 3: Xây dựng ma trận quyền.** Ghi rõ mỗi chủ thể được thao tác gì với loại tài nguyên nào và trong điều kiện nào. Ma trận nên bao gồm quyền ở tầng ứng dụng, IAM cloud và quyền của tài khoản dịch vụ đối với dữ liệu.

**Bước 4: Giới hạn đường kết nối.** Dùng phân đoạn, firewall/security group, quy tắc ingress/egress, xác thực kết nối và nguyên tắc chỉ mở luồng thực sự cần.

**Bước 5: Đặt kiểm tra tại đúng điểm.** Gateway áp dụng các chính sách chung; API kiểm tra danh tính, scope, đối tượng và trạng thái nghiệp vụ; tầng dữ liệu sử dụng credential tối thiểu và kiểm soát truy cập thích hợp.

**Bước 6: Bảo vệ dữ liệu trong suốt vòng đời.** Áp dụng TLS, mã hóa lưu trữ khi cần, quản lý secret/khóa, sao lưu và khôi phục, xóa dữ liệu theo chính sách, kiểm soát việc xuất dữ liệu và sử dụng dữ liệu trong môi trường phát triển.

**Bước 7: Đo lường và diễn tập.** Kiểm tra truy cập hợp lệ và không hợp lệ, rà soát thay đổi cấu hình mạng/IAM, xác minh luồng log, thử phương án thu hồi credential và phản ứng sự cố trên môi trường được phép.

Quá trình này nên lặp lại mỗi khi thêm dịch vụ, API, loại dữ liệu, đối tác hoặc thay đổi cách triển khai. Một thay đổi mạng tưởng nhỏ có thể tạo đường đi mới tới dữ liệu; một endpoint mới có thể mở ra quyền mà ma trận truy cập cũ chưa bao phủ.

## 11. Những ngộ nhận thường gặp

| Nhận định dễ nhầm | Cách hiểu đúng |
|---|---|
| “Đã dùng HTTPS thì dữ liệu đã an toàn.” | HTTPS bảo vệ **đường truyền** khi dùng đúng; dữ liệu vẫn cần phân quyền, bảo vệ lưu trữ và vận hành an toàn. |
| “Ứng dụng ở subnet riêng nên người dùng nội bộ đáng tin.” | Subnet giảm khả năng kết nối; mọi người dùng và workload vẫn cần danh tính và quyền phù hợp. |
| “Có VPN nghĩa là đã có Zero Trust.” | VPN chủ yếu tạo đường truy cập mạng; Zero Trust đòi hỏi đánh giá truy cập theo danh tính, ngữ cảnh và tài nguyên. |
| “Token hợp lệ thì mọi URL trong API đều hợp lệ.” | Access token hợp lệ chỉ là một điều kiện; API còn phải xác minh audience, scope và quyền trên đối tượng. |
| “Dùng mTLS thì không cần phân quyền ứng dụng.” | mTLS chủ yếu xác thực endpoint/workload và bảo vệ kênh; không thay thế quy tắc nghiệp vụ theo người dùng. |
| “Mã hóa CSDL đủ để chống rò rỉ.” | Một tài khoản có quyền đọc dữ liệu giải mã vẫn có thể làm lộ dữ liệu; cần least privilege, kiểm soát truy vấn và phát hiện. |
| “WAF/IDS/IPS sẽ chặn mọi tấn công.” | Công cụ có giới hạn quan sát và khả năng phát hiện; lỗi phân quyền nghiệp vụ, cấu hình quyền hoặc lạm dụng tài khoản hợp lệ vẫn cần biện pháp riêng. |
| “Dùng cloud thì nhà cung cấp chịu trách nhiệm toàn bộ.” | Trách nhiệm được chia theo dịch vụ và mô hình triển khai; người vận hành vẫn phải cấu hình danh tính, quyền, dữ liệu, đường mạng và giám sát phần mình kiểm soát. |

## 12. Bài thực hành thiết kế trên giấy

Không cần hệ thống thật. Hãy tự vẽ một dịch vụ **xem hóa đơn** với bốn thành phần: trình duyệt, API, cơ sở dữ liệu và IdP. Giả sử khách hàng chỉ được xem hóa đơn của mình, kế toán được xem hóa đơn thuộc đơn vị quản lý, còn công cụ phân tích chỉ được đọc dữ liệu tổng hợp đã giảm nhạy cảm.

Hãy tạo ba hiện vật:

1. **Sơ đồ luồng:** đánh dấu nơi tra cứu DNS, thiết lập TLS, kiểm soát mạng, xác thực, phân quyền và truy vấn CSDL. Tách đường gọi của người dùng khỏi đường gọi giữa dịch vụ.
2. **Ma trận quyền:** với mỗi chủ thể, chỉ rõ thao tác, tài nguyên, điều kiện cho phép và nguồn dữ liệu cần dùng để kiểm tra điều kiện.
3. **Bảng phát hiện:** chọn ít nhất một kịch bản lỗi cho mỗi lớp (ví dụ cho phép kết nối CSDL quá rộng, API bỏ qua kiểm tra chủ sở hữu, credential dịch vụ bị dùng sai mục đích, dữ liệu nhạy cảm xuất vào log) và ghi nguồn telemetry phù hợp.

Một bản thiết kế được coi là nhất quán khi: không có đường truy cập nhạy cảm nào chỉ dựa vào “nằm trong mạng nội bộ”; quyền xem hóa đơn được xét theo **người dùng, hóa đơn và ngữ cảnh**; tài khoản API không có quyền quản trị CSDL; và log có thể truy vết một yêu cầu bị từ chối mà không tiết lộ thông tin bí mật.

## 13. Thuật ngữ cần nhớ

| Thuật ngữ | Ý nghĩa trong bài |
|---|---|
| **Trust boundary** | Điểm giao giữa hai miền cần kiểm chứng lại giả định tin cậy |
| **Least privilege** | Chỉ cấp quyền tối thiểu đủ để hoàn thành nhiệm vụ |
| **Defense in depth** | Nhiều lớp kiểm soát kết hợp để giảm nguy cơ thất bại từ một lỗi |
| **Zero Trust** | Không tin cậy mặc định theo vị trí mạng; đánh giá truy cập theo chủ thể, tài nguyên và ngữ cảnh |
| **IAM / IdP** | Quản lý danh tính, xác thực, cấp quyền và vòng đời tài khoản |
| **Authentication / Authorization** | Xác thực *ai đang gọi* / quyết định *được làm gì* |
| **OIDC / OAuth 2.0** | Giao thức lớp danh tính trên OAuth 2.0 / khung ủy quyền truy cập tài nguyên |
| **mTLS** | TLS xác thực hai chiều bằng chứng chỉ của cả hai phía |
| **BOLA / IDOR** | Lỗi kiểm soát quyền ở cấp đối tượng cho phép truy cập tài nguyên không thuộc quyền |
| **Ingress / Egress** | Lưu lượng vào / ra khỏi một mạng, workload hoặc vùng bảo vệ |
| **Blast radius** | Phạm vi tác động khi một thành phần hoặc danh tính bị xâm nhập |
| **Telemetry / Audit** | Dữ liệu quan sát hoạt động hệ thống / dấu vết phục vụ giải trình và điều tra |

## 14. Kết luận

Mạng, ứng dụng, danh tính và dữ liệu không phải bốn “hộp bảo mật” tách rời: chúng cùng tham gia vào **một quyết định truy cập xuyên suốt**. Mạng quyết định đường nào được kết nối; danh tính chứng minh ai hoặc workload nào đang gọi; ứng dụng kiểm tra thao tác và quyền nghiệp vụ; lớp dữ liệu bảo vệ tài sản ngay cả khi một thành phần khác gặp sự cố. DNS, TLS, firewall, VPN, IDS/IPS, phân đoạn mạng, IAM, chính sách API, mã hóa và giám sát chỉ phát huy đầy đủ hiệu quả khi đặt đúng vị trí trên đường đi của yêu cầu và liên kết bằng chính sách nhất quán.

Khi đánh giá một kiến trúc mạng an toàn, hãy luôn tự hỏi: **Dữ liệu nào đang được bảo vệ, ai có thể đi đến nó, danh tính và quyền được kiểm tra ở đâu, điều gì xảy ra nếu một lớp thất bại, và ta sẽ nhận biết sự cố bằng bằng chứng nào?** Những câu hỏi này là nền tảng để học sâu hơn về phân đoạn, firewall, VPN, IDS/IPS, bảo vệ DNS và bảo mật hạ tầng đám mây.
