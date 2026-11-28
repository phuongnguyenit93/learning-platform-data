# Hostname verification

Hostname verification là bước kiểm tra tên máy chủ mà ứng dụng muốn kết nối có khớp với danh tính được chứng thực trong chứng thư TLS mà máy chủ gửi hay không. Bước này giúp client phát hiện trường hợp kết nối tới một máy chủ đang trình bày chứng thư hợp lệ về mặt chữ ký CA nhưng chứng thư đó được cấp cho một tên miền khác.

Ví dụ, ứng dụng gọi **https://api.example.com** nhưng một thiết bị trung gian trả về chứng thư chỉ hợp lệ cho **login.example.net**. Chứng thư có thể vẫn được ký bởi một CA nằm trong trust store của client. Nếu client chỉ kiểm tra chuỗi chứng thư mà bỏ qua hostname verification, nó có thể chấp nhận nhầm máy chủ trung gian và gửi token, cookie hoặc dữ liệu nhạy cảm cho bên đó.

Trong TLS, chứng thư số gắn public key với danh tính máy chủ. CA xác nhận chứng thư theo chính sách phát hành của mình; TLS chứng minh phía máy chủ đang nắm private key tương ứng; hostname verification xác nhận danh tính trong chứng thư đúng với đích mà client định truy cập. Ba phần này bổ sung cho nhau.

## 1. Mục tiêu và phạm vi

Sau bài học, người đọc cần có khả năng:

- Giải thích vì sao chứng thư có chuỗi tin cậy hợp lệ vẫn có thể không phù hợp với máy chủ đang truy cập.
- Xác định đúng tên tham chiếu mà client phải kiểm tra từ URL hoặc cấu hình dịch vụ.
- Phân biệt DNS name, IP address, Subject Alternative Name (SAN), Common Name (CN) và Server Name Indication (SNI).
- Áp dụng quy tắc khớp tên chính xác, wildcard và IP address.
- Nhận biết tác động của DNS alias, reverse proxy, CDN, TLS termination và mutual TLS.
- Cấu hình thư viện TLS theo hướng xác minh danh tính mặc định và xử lý lỗi an toàn.
- Thiết kế kiểm thử để phát hiện cấu hình bỏ qua hostname verification.

Bài tập trung vào xác minh danh tính máy chủ trong TLS, đặc biệt là HTTPS. Nó không thay thế việc xác minh chuỗi chứng thư, kiểm tra thời hạn, kiểm soát quyền sử dụng khóa, thu hồi chứng thư hay xác thực người dùng ở tầng ứng dụng.

## 2. Hai tên cần được so khớp

Hostname verification luôn so sánh hai phía:

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| Reference identifier | Danh tính mà client mong đợi ở đầu bên kia của kết nối | **api.example.com** lấy từ URL |
| Presented identifier | Danh tính máy chủ công bố trong chứng thư | **DNS:api.example.com** trong SAN |
| DNS-ID | Tên DNS được biểu diễn trong SAN dưới dạng dNSName | **DNS:api.example.com** |
| IP-ID | Địa chỉ IP được biểu diễn trong SAN dưới dạng iPAddress | **IP Address:192.0.2.10** |
| Subject CN | Trường Common Name trong Subject của chứng thư | **CN=api.example.com** |
| SNI | Tên client gửi trong ClientHello để máy chủ chọn cấu hình/chứng thư phù hợp | **api.example.com** |

Reference identifier phải xuất phát từ đích mà ứng dụng thực sự yêu cầu. Với một URL HTTPS, thông thường đó là hostname trong authority của URL. Presented identifier đến từ SAN của chứng thư máy chủ.

Ví dụ:

- Client yêu cầu **https://api.example.com/v1/orders**.
- Reference identifier là **api.example.com**.
- Máy chủ gửi chứng thư có SAN **DNS:api.example.com**.
- Hai tên khớp theo quy tắc DNS-ID, vì vậy phần kiểm tra tên có thể thành công.

Nếu chứng thư chỉ có **DNS:admin.example.com**, hostname verification phải thất bại, kể cả khi chứng thư được CA tin cậy ký và còn hạn.

## 3. Hostname verification khác xác minh chuỗi chứng thư

Xác minh chứng thư TLS là một tập hợp các kiểm tra độc lập. Một luồng xác minh thông thường bao gồm:

1. Xây dựng đường dẫn chứng thư từ chứng thư máy chủ tới một trust anchor mà client tin cậy.
2. Kiểm tra chữ ký của các chứng thư trong đường dẫn và các ràng buộc CA liên quan.
3. Kiểm tra thời gian hiệu lực, thuật toán, key usage và extended key usage phù hợp với mục đích xác thực máy chủ.
4. Kiểm tra chính sách thu hồi nếu ứng dụng và môi trường triển khai yêu cầu.
5. So khớp reference identifier với danh tính được trình bày trong SAN.
6. Hoàn tất xác thực TLS và chỉ sau đó mới cho phép ứng dụng sử dụng kết nối.

Một chứng thư có thể vượt qua bước 1–4 nhưng thất bại ở bước 5. Đây là lỗi hostname mismatch. Ngược lại, một chứng thư có SAN đúng hostname vẫn phải bị từ chối nếu chuỗi chứng thư không được tin cậy, đã hết hạn hoặc không hợp lệ cho mục đích server authentication.

Không nên xem việc cài CA vào trust store là đủ để xác thực máy chủ. Trust store trả lời câu hỏi “tôi tin CA nào có thể phát hành chứng thư”; hostname verification trả lời câu hỏi “chứng thư này có đại diện đúng máy chủ tôi định gọi hay không”.

### Ví dụ về hai lỗi khác nhau

| Tình huống | Chuỗi chứng thư | Hostname | Kết quả |
|---|---|---|---|
| CA tin cậy, SAN đúng tên, chứng thư còn hạn | Hợp lệ | Khớp | Có thể chấp nhận nếu các kiểm tra khác cũng đạt |
| CA tin cậy, SAN là tên miền khác | Hợp lệ | Không khớp | Từ chối |
| SAN đúng tên nhưng CA không được tin cậy | Không hợp lệ | Khớp | Từ chối |
| SAN đúng tên nhưng chứng thư hết hạn | Không hợp lệ | Khớp | Từ chối |
| Chứng thư chỉ có CN, không có SAN phù hợp | Không đủ danh tính theo mô hình hiện đại | Không xác minh được đúng cách | Từ chối |

## 4. Vì sao bỏ qua hostname verification tạo ra lỗ hổng

Giả sử ứng dụng gửi yêu cầu tới **api.bank.example**. Kẻ tấn công có thể kiểm soát mạng Wi-Fi, DNS tại một mạng bị xâm nhập, proxy độc hại hoặc một điểm trung gian trên đường truyền. Kẻ tấn công đưa ra một chứng thư cho **attacker.example**, nhưng chứng thư đó được ký bởi một CA mà thiết bị nạn nhân tin cậy.

Nếu client chỉ kiểm tra chữ ký CA và thời hạn, nó có thể chấp nhận chứng thư. Khi hostname verification được thực hiện đúng, client so sánh **api.bank.example** với SAN **DNS:attacker.example**, thấy không khớp và dừng handshake.

Các tình huống có thể dẫn đến lỗ hổng gồm:

- Tắt kiểm tra tên để “sửa nhanh” lỗi chứng thư trong môi trường staging hoặc production.
- Dùng trust manager chỉ kiểm tra CA nhưng không kiểm tra danh tính endpoint.
- Viết custom hostname verifier luôn trả về **true**.
- Cho phép mọi chứng thư tự ký mà không ràng buộc hostname và trust anchor.
- Dùng địa chỉ IP hoặc hostname nội bộ khác với tên mà chứng thư đại diện.
- Tái sử dụng một kết nối TLS cho nhiều đích mà không duy trì đúng danh tính endpoint.

Hậu quả không chỉ là đọc được nội dung. Khi client chấp nhận nhầm máy chủ, kẻ tấn công có thể thu thập thông tin xác thực, thay đổi phản hồi, phát lại hoặc chuyển tiếp giao dịch, giả mạo metadata, đánh cắp bearer token và gây sai lệch dữ liệu.

## 5. Lấy reference identifier từ đích kết nối

Client phải xác định tên cần xác minh trước khi bắt đầu TLS. Với HTTPS, nguồn thông thường là hostname trong URL được ứng dụng yêu cầu.

Ví dụ:

| URL | Reference identifier | Thành phần không tham gia so khớp hostname |
|---|---|---|
| **https://api.example.com:8443/v1** | **api.example.com** | Scheme, port 8443, path /v1 |
| **https://www.example.com/** | **www.example.com** | Path / |
| **https://192.0.2.10/status** | IP **192.0.2.10** | Path /status |
| **https://[2001:db8::10]:9443/health** | IP **2001:db8::10** | Dấu ngoặc vuông, port và path |

Không tự suy ra reference identifier từ địa chỉ IP mà DNS phân giải ra. Nếu ứng dụng gọi **api.example.com** và DNS trả về **192.0.2.10**, danh tính cần kiểm tra vẫn là **api.example.com**. Địa chỉ IP chỉ là thông tin định tuyến tới máy chủ.

Tương tự, nếu **api.example.com** là CNAME trỏ tới **edge-17.provider.net**, client vẫn xác minh tên **api.example.com** theo yêu cầu ban đầu. Chứng thư của dịch vụ đích phải có SAN bao phủ tên alias mà người dùng truy cập, hoặc lớp proxy/CDN phải trình bày chứng thư phù hợp.

### Redirect

Khi HTTP redirect đưa client từ **https://a.example** sang **https://b.example**, mỗi kết nối TLS phải xác minh hostname theo URL đích tương ứng. Thành công khi xác minh **a.example** không cấp quyền tin cậy cho **b.example**.

Ứng dụng cũng cần áp dụng chính sách redirect phù hợp với thông tin xác thực. Không tự động chuyển token hoặc header nhạy cảm sang một origin khác chỉ vì kết nối TLS của origin mới hợp lệ.

### Proxy

Với HTTP CONNECT proxy, client tạo tunnel tới proxy rồi thực hiện TLS với máy chủ đích bên trong tunnel. Chứng thư được kiểm tra vẫn phải đại diện cho hostname đích trong URL. Chứng thư của proxy chỉ được dùng trong một mô hình TLS interception được quản trị và tin cậy rõ ràng; nó không tự động thay thế danh tính máy chủ đích.

## 6. SAN là nguồn danh tính máy chủ

Subject Alternative Name (SAN) là extension của X.509 dùng để đưa các danh tính thay thế vào chứng thư. Với HTTPS và tên DNS, client kiểm tra một SAN kiểu **dNSName**. Khi URL dùng địa chỉ IP literal, client cần một SAN kiểu **iPAddress**.

Ví dụ minh họa phần SAN:

~~~~text
X509v3 Subject Alternative Name:
    DNS:api.example.com
    DNS:admin.example.com
    DNS:*.svc.example.com
    IP Address:192.0.2.10
~~~~

Chứng thư trên có thể đại diện cho hai DNS name cụ thể, một phạm vi wildcard và một địa chỉ IP. Mỗi reference identifier được so khớp với loại SAN tương ứng.

Theo mô hình hiện đại được mô tả trong RFC 9525, client sử dụng danh tính trong SAN. Không nên phát hành chứng thư máy chủ chỉ có CN rồi trông đợi client dùng CN làm phương án thay thế. Các thư viện cũ có thể còn hành vi tương thích khác nhau; hệ thống mới nên phát hành SAN đầy đủ và kiểm tra bằng client hiện đại.

### DNS name và IP address không thay thế cho nhau

Giả sử SAN có:

~~~~text
DNS:192.0.2.10
~~~~

Đây là một chuỗi DNS-ID, không phải IP-ID. Nó không đáp ứng yêu cầu truy cập URL bằng IP **192.0.2.10**.

Để chứng thư đại diện cho IP đó, SAN phải chứa kiểu IP Address với giá trị địa chỉ nhị phân tương ứng. Ngược lại, nếu client truy cập bằng hostname **api.example.com**, SAN IP không tự động thay thế DNS SAN.

Không dùng reverse DNS hoặc PTR record để biến một IP thành hostname rồi tự coi tên PTR là danh tính được yêu cầu. Reference identifier phải được xác định theo đích kết nối và chính sách ứng dụng.

## 7. Quy tắc so khớp DNS name

Với DNS-ID, client so sánh tên tham chiếu với một hoặc nhiều giá trị **dNSName** trong SAN theo quy tắc hostname matching của TLS.

Các nguyên tắc quan trọng:

- DNS name không phân biệt chữ hoa và chữ thường.
- So khớp tên đầy đủ theo các label DNS, không phải so khớp chuỗi con tùy ý.
- Không coi **api.example.com.attacker.net** là khớp với **api.example.com**.
- Không tự bỏ hoặc thêm label để cố làm cho tên khớp.
- Dùng một chính sách chuẩn hóa hostname nhất quán trong toàn bộ client.
- Không thay hostname được yêu cầu bằng kết quả CNAME hoặc địa chỉ IP sau phân giải DNS.

Ví dụ:

| Reference identifier | SAN | Kết quả |
|---|---|---|
| **api.example.com** | **DNS:api.example.com** | Khớp chính xác |
| **API.EXAMPLE.COM** | **DNS:api.example.com** | Khớp theo quy tắc DNS không phân biệt hoa/thường |
| **api.example.com** | **DNS:admin.example.com** | Không khớp |
| **api.example.com.attacker.net** | **DNS:api.example.com** | Không khớp |
| **api.example.com** | **DNS:example.com** | Không khớp |

Không tự viết hàm so sánh bằng **endsWith**, **contains** hoặc regex đơn giản. Các cách này dễ chấp nhận nhầm tên miền có hậu tố giống nhau, dấu chấm, label rỗng hoặc wildcard không hợp lệ. Hãy dùng hostname verifier của thư viện TLS đáng tin cậy.

## 8. Wildcard certificate

Wildcard certificate cho phép một SAN đại diện cho một nhóm hostname trong phạm vi nhất định. Ví dụ, **DNS:*.example.com** thường được dùng cho các host cấp một như **api.example.com** hoặc **shop.example.com**.

Wildcard cần được xử lý chặt chẽ:

- Dấu **\*** chỉ được dùng như toàn bộ label ngoài cùng bên trái theo quy tắc wildcard matching.
- Wildcard chỉ khớp một label.
- **\*.example.com** có thể khớp **api.example.com**.
- **\*.example.com** không khớp **example.com**.
- **\*.example.com** không khớp **v2.api.example.com**.
- Không dùng wildcard một phần như **api*.example.com** hoặc **\*api.example.com**.

Bảng ví dụ:

| Reference identifier | SAN wildcard | Kết quả |
|---|---|---|
| **api.example.com** | **\*.example.com** | Khớp |
| **shop.example.com** | **\*.example.com** | Khớp |
| **example.com** | **\*.example.com** | Không khớp |
| **a.b.example.com** | **\*.example.com** | Không khớp |
| **api.example.net** | **\*.example.com** | Không khớp |
| **api-v2.example.com** | **api\*.example.com** | Không được coi là wildcard hợp lệ |

Wildcard làm giảm số chứng thư cần quản lý nhưng mở rộng phạm vi ảnh hưởng khi private key bị lộ. Nếu một wildcard key được dùng cho nhiều tenant hoặc nhiều dịch vụ, sự cố ở một nơi có thể ảnh hưởng tới toàn bộ tên miền nằm trong phạm vi đó.

Nên giới hạn wildcard theo zone và môi trường, tách private key giữa production và non-production, quản lý quyền truy cập theo nguyên tắc tối thiểu, theo dõi việc phát hành và thay thế chứng thư, đồng thời tránh dùng wildcard rộng cho các ranh giới tin cậy khác nhau.

## 9. Internationalized Domain Name (IDN)

Tên miền có ký tự Unicode có thể được biểu diễn bằng dạng U-label cho người đọc và dạng A-label dùng cơ chế punycode cho DNS. Ví dụ minh họa:

~~~~text
U-label: bücher.example
A-label: xn--bcher-kva.example
~~~~

Client và hệ thống phát hành chứng thư cần áp dụng cùng chính sách IDNA để tránh hai cách diễn giải khác nhau của một tên. Trong quá trình so khớp, thư viện TLS nên xử lý chuyển đổi và so sánh theo tiêu chuẩn, thường sử dụng dạng ASCII A-label khi biểu diễn DNS name trên đường truyền.

Không tự viết thuật toán chuyển Unicode sang punycode hoặc tự loại bỏ ký tự nhìn giống nhau. Các ký tự Unicode có thể có hình dạng tương tự nhưng mã điểm khác nhau; quy trình IDNA và chính sách hiển thị an toàn giúp giảm nhầm lẫn và nguy cơ giả mạo tên miền.

Khi vận hành, cần kiểm tra tên miền đã được chuẩn hóa ở bước đăng ký, phát hành chứng thư, cấu hình service discovery và phía client. Không để mỗi thành phần tự chuẩn hóa theo một quy tắc riêng.

## 10. SNI hỗ trợ chọn chứng thư, nhưng không thay thế hostname verification

Server Name Indication (SNI) là extension TLS cho phép client gửi tên máy chủ dự định truy cập trong ClientHello. Một địa chỉ IP có thể phục vụ nhiều website hoặc dịch vụ TLS; máy chủ dùng SNI để chọn virtual host, policy và chứng thư phù hợp.

Ví dụ, một load balancer có thể phục vụ:

- **api.example.com**
- **admin.example.com**
- **static.example.com**

Client gửi SNI **api.example.com**, máy chủ chọn chứng thư tương ứng và gửi về. Sau khi nhận chứng thư, client vẫn phải kiểm tra SAN có đại diện cho **api.example.com** hay không.

SNI và hostname verification có vai trò khác nhau:

| Thành phần | Câu hỏi được giải quyết |
|---|---|
| SNI | Máy chủ nên chọn virtual host/chứng thư nào cho kết nối này? |
| Hostname verification | Chứng thư được gửi có đại diện cho hostname mà client yêu cầu không? |
| Certificate path validation | Chứng thư có nối tới trust anchor và thỏa các chính sách tin cậy không? |
| TLS proof of possession | Phía máy chủ có chứng minh được quyền kiểm soát private key tương ứng không? |

Một client có thể gửi SNI đúng nhưng vẫn nhận chứng thư sai do cấu hình load balancer. Ngược lại, một client gửi SNI không đúng có thể khiến máy chủ trả về chứng thư mặc định; hostname verification sẽ phát hiện nếu chứng thư mặc định không chứa tên tham chiếu.

SNI không phải chữ ký xác nhận danh tính và không làm cho chứng thư tự động đáng tin cậy. Với URL dùng IP literal, client thường không gửi DNS SNI; nếu kết nối bằng IP thì kiểm tra IP-ID theo SAN IP.

## 11. Luồng kiểm tra trong một kết nối TLS

Sơ đồ sau mô tả quan hệ giữa reference identifier, SNI, chứng thư và quyết định chấp nhận kết nối:

~~~~mermaid
sequenceDiagram
    participant A as Ứng dụng client
    participant T as TLS client
    participant S as TLS server
    A->>T: Yêu cầu https://api.example.com
    T->>T: Lấy reference identifier api.example.com
    T->>S: ClientHello + SNI api.example.com
    S->>T: Certificate chain + SAN
    T->>T: Xác minh chain, thời hạn và mục đích
    T->>T: So khớp api.example.com với DNS-ID trong SAN
    alt Tất cả kiểm tra thành công
        T->>S: Hoàn tất handshake
        T->>A: Cung cấp kết nối TLS
    else Có kiểm tra thất bại
        T-->>A: Báo lỗi TLS và đóng kết nối
    end
~~~~

Trình tự cụ thể của các thông điệp có thể thay đổi theo phiên bản TLS, cơ chế xác thực và thư viện. Điều quan trọng về mặt bảo mật là client chỉ cung cấp một kết nối đã được xác thực cho ứng dụng khi tất cả điều kiện bắt buộc đều đạt.

Không nên cho ứng dụng tiếp tục gửi dữ liệu rồi mới kiểm tra hostname. Việc kiểm tra phải nằm trong handshake hoặc lớp TLS client được tin cậy, trước khi ứng dụng sử dụng kết nối.

## 12. Hostname verification trong kiến trúc nhiều lớp

Trong hệ thống có CDN, API gateway, ingress hoặc reverse proxy, cần xác định rõ mỗi kết nối TLS xác thực danh tính nào.

~~~~mermaid
flowchart LR
    C[Client] -->|TLS 1: api.example.com| E[CDN / Edge]
    E -->|TLS 2: origin.internal.example| O[Origin service]
    O -->|TLS 3: inventory.internal.example| I[Inventory service]
~~~~

Ở ví dụ này:

- Client xác minh chứng thư edge theo **api.example.com**.
- Edge xác minh chứng thư origin theo **origin.internal.example**.
- Origin xác minh chứng thư inventory theo **inventory.internal.example**.

Mỗi TLS hop có reference identifier riêng. Không lấy hostname bên ngoài rồi dùng cho tất cả kết nối nội bộ nếu các dịch vụ có danh tính khác nhau.

Một cấu hình sai thường gặp là edge kết nối tới origin bằng địa chỉ IP nhưng tắt xác minh hostname vì chứng thư origin được cấp cho DNS name. Cách đúng là giữ reference identifier của origin, cấu hình SNI phù hợp và xác minh SAN của chứng thư origin theo tên đó, kể cả khi socket được định tuyến qua IP.

Với service mesh hoặc workload identity, hệ thống có thể xác minh URI SAN theo một định dạng danh tính như SPIFFE. Đây là chính sách xác minh danh tính ở tầng workload. Nó cần được cấu hình rõ ràng và không được nhầm lẫn với DNS hostname verification của HTTPS thông thường.

## 13. Phân biệt server authentication và mutual TLS

Trong TLS một chiều thông thường, client xác minh chứng thư máy chủ. Máy chủ không cần chứng minh danh tính client bằng chứng thư trong handshake.

Trong mutual TLS (mTLS), hai phía cùng xác thực chứng thư:

- Client xác minh chứng thư máy chủ và hostname của máy chủ.
- Server xác minh chứng thư client theo trust policy, danh tính workload hoặc danh tính client được phép.

Hostname verification phía client không thay thế việc server kiểm tra client certificate. Tương tự, việc server chấp nhận client certificate không có nghĩa client đã xác minh đúng hostname máy chủ.

Một hệ thống mTLS nên định nghĩa rõ:

- Trust anchor nào được dùng cho server certificate và client certificate.
- Danh tính nào được lấy từ SAN.
- DNS-ID, IP-ID hay URI-ID được phép cho từng loại kết nối.
- Dịch vụ nào được phép gọi dịch vụ nào.
- Quy trình cấp mới, xoay vòng, thu hồi và kiểm toán chứng thư.

## 14. Cấu hình client an toàn

Ưu tiên thư viện TLS có hành vi xác minh hostname mặc định. Khi cần dùng CA nội bộ, hãy thêm đúng CA hoặc trust anchor vào trust store và giữ nguyên kiểm tra tên máy chủ.

### Python

Với Python, **ssl.create_default_context()** tạo context dùng kiểm tra chứng thư theo cấu hình mặc định an toàn. Khi gọi **wrap_socket**, truyền hostname dự định truy cập vào **server_hostname**; giá trị này vừa hỗ trợ SNI cho DNS hostname vừa cho phép thư viện thực hiện kiểm tra tên.

~~~~python
import socket
import ssl

hostname = "api.example.com"
port = 443

context = ssl.create_default_context()

with socket.create_connection((hostname, port), timeout=5) as raw_socket:
    with context.wrap_socket(
        raw_socket,
        server_hostname=hostname,
    ) as tls_socket:
        print("TLS version:", tls_socket.version())
        print("Peer:", tls_socket.getpeercert())
~~~~

Nếu dùng CA riêng:

~~~~python
context = ssl.create_default_context(
    cafile="/etc/my-service/trust/internal-root-ca.pem"
)
~~~~

Không dùng **ssl._create_unverified_context()** hoặc tắt **check_hostname** để vượt qua lỗi chứng thư. Nếu kết nối bằng IP literal, truyền IP literal làm reference identity và yêu cầu chứng thư có SAN IP tương ứng.

### Java 17

Với Java HTTP Client, giữ cấu hình xác minh mặc định và chỉ thay trust material khi có yêu cầu rõ ràng. Ví dụ sau sử dụng hệ thống trust store mặc định:

~~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

public class HttpsRequest {
    public static void main(String[] args) throws Exception {
        URI uri = URI.create("https://api.example.com/v1/health");

        HttpClient client = HttpClient.newBuilder()
                .build();

        HttpRequest request = HttpRequest.newBuilder(uri)
                .GET()
                .build();

        HttpResponse<String> response = client.send(
                request,
                HttpResponse.BodyHandlers.ofString()
        );

        System.out.println("HTTP status: " + response.statusCode());
    }
}
~~~~

Nếu ứng dụng dùng **SSLContext** tùy chỉnh để tin cậy CA nội bộ, vẫn phải giữ endpoint identification của HTTPS. Với **SSLSocket** tự quản lý, có thể đặt endpoint identification algorithm trước khi handshake:

~~~~java
import javax.net.ssl.SSLParameters;
import javax.net.ssl.SSLSocket;
import javax.net.ssl.SSLSocketFactory;

public class VerifiedTlsSocket {
    public static void main(String[] args) throws Exception {
        String hostname = "api.example.com";
        int port = 443;

        SSLSocketFactory factory =
                (SSLSocketFactory) SSLSocketFactory.getDefault();

        try (SSLSocket socket = (SSLSocket) factory.createSocket(
                hostname,
                port
        )) {
            SSLParameters parameters = socket.getSSLParameters();
            parameters.setEndpointIdentificationAlgorithm("HTTPS");
            socket.setSSLParameters(parameters);

            socket.startHandshake();

            System.out.println("TLS protocol: "
                    + socket.getSession().getProtocol());
            System.out.println("Peer principal: "
                    + socket.getSession().getPeerPrincipal());
        }
    }
}
~~~~

Khi dùng API mức thấp, lập trình viên chịu trách nhiệm cấu hình đầy đủ các tham số TLS, trust manager, timeout, SNI và endpoint identification. Không thêm một **HostnameVerifier** tùy chỉnh luôn trả về **true** hoặc bỏ qua lỗi do endpoint identification phát hiện.

### Go

Go xác minh chứng thư và hostname khi **InsecureSkipVerify** không được bật. Có thể chỉ rõ **ServerName** để cấu hình tên mong đợi và SNI:

~~~~go
package main

import (
    "crypto/tls"
    "fmt"
    "log"
)

func main() {
    config := &tls.Config{
        ServerName: "api.example.com",
    }

    conn, err := tls.Dial("tcp", "api.example.com:443", config)
    if err != nil {
        log.Fatal(err)
    }
    defer conn.Close()

    state := conn.ConnectionState()
    fmt.Println("TLS version:", state.Version)
    fmt.Println("Peer certificates:", len(state.PeerCertificates))
}
~~~~

Không bật **InsecureSkipVerify: true** trong production để “chỉ dùng mã hóa”. Nếu có yêu cầu xác minh bổ sung, hãy dùng **VerifyConnection** hoặc cơ chế xác minh phù hợp nhưng vẫn giữ xác minh mặc định, và cần kiểm thử cả đường đi thành công lẫn thất bại.

### curl

curl xác minh CA chain và hostname theo mặc định:

~~~~bash
curl --fail --show-error https://api.example.com/health
~~~~

Nếu máy chủ dùng CA nội bộ, chỉ định CA cần tin cậy:

~~~~bash
curl --fail --show-error \
  --cacert ./internal-root-ca.pem \
  https://api.internal.example/health
~~~~

Không dùng **-k** hoặc **--insecure** làm cách sửa lỗi lâu dài. Tùy chọn đó bỏ qua xác minh chứng thư và có thể cho phép kết nối tới máy chủ giả mạo.

### OpenSSL để chẩn đoán

Có thể dùng **s_client** để xem chứng thư và kiểm tra hostname:

~~~~bash
openssl s_client \
  -connect api.example.com:443 \
  -servername api.example.com \
  -verify_hostname api.example.com \
  -verify_return_error \
  -CAfile ./roots.pem
~~~~

Khi kiểm tra URL dùng IP literal, dùng **-verify_ip** với IP tương ứng. SNI là thông tin chọn virtual host; **-verify_hostname** hoặc **-verify_ip** mới là phần yêu cầu xác minh danh tính tương ứng. Phiên bản OpenSSL và bộ CA được dùng phải phù hợp với môi trường đang chẩn đoán.

Lệnh chẩn đoán không thay thế kiểm tra trong ứng dụng thực tế. Cần xác nhận thư viện và cấu hình runtime của ứng dụng cũng thực hiện hostname verification.

## 15. Các cách cấu hình nguy hiểm cần loại bỏ

| Môi trường | Cách bỏ qua thường gặp | Rủi ro |
|---|---|---|
| curl | **-k**, **--insecure** | Bỏ qua xác minh chứng thư |
| Python requests | **verify=False** | Không xác minh CA và danh tính máy chủ |
| Python ssl | Tắt **check_hostname** hoặc dùng unverified context | Có thể chấp nhận máy chủ sai danh tính |
| Go | **InsecureSkipVerify: true** | Tắt xác minh mặc định; custom verify sai có thể để lọt MITM |
| Node.js | **rejectUnauthorized: false** | Chấp nhận chứng thư không hợp lệ |
| Java | Trust manager tin mọi chứng thư | Bỏ qua xác minh trust chain |
| Java | HostnameVerifier luôn trả về **true** | Bỏ qua xác minh tên máy chủ |

Một số đội phát triển tạo cờ **skipTlsVerify** để hỗ trợ môi trường local. Cờ này dễ bị bật nhầm trong production, bị kế thừa qua cấu hình hoặc được bật trong một nhánh code không được kiểm thử. Nếu cần CA local, hãy tạo CA phát triển riêng và cài vào trust store của môi trường phát triển. Nếu cần mock server, dùng chứng thư test có SAN phù hợp với hostname test.

Không biến lỗi hostname mismatch thành cảnh báo có thể bỏ qua. Nếu hệ thống phải hỗ trợ một endpoint legacy, hãy xác định danh tính đúng, phát hành chứng thư phù hợp hoặc có một policy ngoại lệ hẹp, được phê duyệt, có thời hạn và có kiểm toán. Ngoại lệ không được làm suy yếu các kết nối khác.

## 16. Các lỗi phổ biến và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| **hostname mismatch** | SAN không chứa tên client đang gọi | Kiểm tra URL, SAN và chứng thư thực tế được endpoint gửi |
| Chỉ lỗi trên một domain alias | Chứng thư có tên canonical nhưng thiếu alias | Bổ sung alias vào SAN hoặc cấu hình client dùng đúng public hostname |
| Chỉ lỗi khi truy cập bằng IP | Chứng thư có DNS SAN nhưng thiếu IP SAN | Dùng DNS name phù hợp hoặc phát hành chứng thư có IP SAN |
| Lỗi trên một node trong cluster | Node đó đang phục vụ chứng thư cũ hoặc chứng thư mặc định | Kiểm tra SNI routing và trạng thái rollout từng node |
| Lỗi sau khi thêm CDN | Edge trả về chứng thư của virtual host khác | Kiểm tra SNI, mapping hostname và cấu hình certificate tại CDN |
| Lỗi sau khi đổi DNS | Client truy cập alias mới chưa có trong SAN | Giữ reference hostname và bổ sung SAN trước khi chuyển traffic |
| OpenSSL thành công nhưng ứng dụng thất bại | Trust store, proxy, SNI hoặc runtime khác nhau | Chạy kiểm tra từ đúng host/container và dùng đúng CA/runtime |
| Trình duyệt thành công nhưng service thất bại | Trust store hoặc hostname policy giữa các client khác nhau | Kiểm tra CA bundle, proxy và thư viện của service |
| Chỉ lỗi trong môi trường nội bộ | Internal CA chưa được cài hoặc internal hostname thiếu SAN | Cập nhật trust store và chứng thư theo inventory nội bộ |
| Chứng thư có CN đúng nhưng vẫn lỗi | SAN thiếu tên hoặc client không dùng CN fallback | Phát hành lại chứng thư với SAN chính xác |

### Quy trình chẩn đoán có thứ tự

1. Ghi lại URL chính xác mà ứng dụng gọi, gồm scheme, hostname và port.
2. Xác định hostname mà TLS client thực sự dùng làm reference identifier.
3. Kiểm tra DNS resolution và đường đi mạng để biết request tới node hoặc proxy nào.
4. Kiểm tra SNI được gửi và chứng thư thực tế được endpoint trả về.
5. Đọc SAN của chứng thư, xác nhận đúng loại DNS-ID hoặc IP-ID.
6. Kiểm tra thời hạn, chain, EKU, trust store và chính sách thu hồi.
7. Lặp lại kiểm tra từ đúng container, máy chủ, runtime và proxy của ứng dụng.
8. Kiểm tra redirect, connection pool và cấu hình upstream nếu lỗi chỉ xuất hiện ở một đường đi.
9. Sửa SAN, SNI, trust store hoặc routing; triển khai theo từng node và theo dõi handshake.
10. Thêm regression test để lỗi không quay lại.

Không chỉ kiểm tra chứng thư ở một địa chỉ IP rồi kết luận toàn bộ dịch vụ đúng. Load balancer, CDN và DNS round-robin có thể đưa các kết nối khác nhau tới các node có chứng thư khác nhau.

## 17. Vòng đời chứng thư và quản lý khóa

Hostname verification phụ thuộc vào chất lượng dữ liệu danh tính được đưa vào chứng thư. Vì vậy quy trình quản lý certificate và private key cần giữ nhất quán từ lúc phát hành đến khi thu hồi.

Một quy trình điển hình:

1. Chủ dịch vụ khai báo các DNS name hoặc IP address cần đại diện.
2. Hệ thống kiểm tra quyền kiểm soát domain hoặc quyền sở hữu địa chỉ theo chính sách CA.
3. Tạo key pair trong vị trí lưu trữ phù hợp; với hệ thống nhạy cảm, private key có thể được tạo và giữ trong HSM hoặc dịch vụ quản lý khóa.
4. Tạo CSR với SAN đúng; không chỉ đặt hostname trong CN.
5. CA phát hành chứng thư theo policy.
6. Triển khai certificate chain và private key tới đúng TLS terminator.
7. Kiểm thử hostname từ các client và network path thực tế.
8. Theo dõi ngày hết hạn, lỗi handshake, thay đổi SAN và việc sử dụng private key.
9. Khi xoay vòng, phát hành chứng thư mới với tập danh tính được phê duyệt, triển khai trước khi chứng thư cũ hết hạn.
10. Khi thu hồi hoặc thay thế do compromise, cập nhật trạng thái tin cậy và thay private key theo incident plan.

Hostname verification chỉ xác nhận tên trong chứng thư khớp với tên client yêu cầu. Nó không chứng minh rằng quy trình cấp chứng thư đã đúng, rằng private key không bị lộ, hoặc rằng người dùng được phép gọi API. Các kiểm soát phát hành, bảo vệ private key, phân quyền và audit vẫn cần thiết.

### SAN thay đổi phải được quản trị như thay đổi danh tính

Thêm một DNS name vào SAN làm chứng thư đại diện cho một tên mới. Điều này có thể mở rộng phạm vi truy cập mà private key đó có thể xác thực. Vì vậy việc thêm SAN phải có chủ sở hữu dịch vụ, bằng chứng quyền kiểm soát tên, phê duyệt phù hợp và audit trail.

Không nên tự động thêm mọi hostname được tìm thấy trong DNS vào SAN. DNS record có thể tồn tại vì mục đích routing hoặc kiểm thử, không đồng nghĩa dịch vụ có quyền đại diện cho tên đó.

## 18. Kiểm thử hostname verification

Một bộ kiểm thử tốt phải chứng minh cả trường hợp hợp lệ và trường hợp bắt buộc bị từ chối.

| Ca kiểm thử | Chứng thư hoặc reference | Kết quả mong đợi |
|---|---|---|
| DNS exact match | Reference **api.example.com**, SAN **DNS:api.example.com** | Thành công |
| DNS khác tên | Reference **api.example.com**, SAN **DNS:admin.example.com** | Thất bại |
| Tên có hậu tố gây nhầm | Reference **api.example.com.attacker.net**, SAN **DNS:api.example.com** | Thất bại |
| Wildcard một label | Reference **api.example.com**, SAN **DNS:*.example.com** | Thành công nếu client policy hỗ trợ wildcard |
| Wildcard nhiều label | Reference **v2.api.example.com**, SAN **DNS:*.example.com** | Thất bại |
| Wildcard không nằm ở label trái nhất | SAN **DNS:api.*.example.com** | Chứng thư/tên không được chấp nhận theo quy tắc wildcard |
| Apex domain | Reference **example.com**, SAN **DNS:*.example.com** | Thất bại |
| IP exact match | Reference **192.0.2.10**, SAN **IP:192.0.2.10** | Thành công |
| IP chỉ có DNS SAN | Reference **192.0.2.10**, SAN **DNS:192.0.2.10** | Thất bại |
| CN-only | CN đúng nhưng không có SAN phù hợp | Thất bại theo chính sách hiện đại |
| CNAME alias | Reference là alias, SAN chỉ có canonical target | Thất bại |
| Redirect sang host khác | Host mới không nằm trong SAN chứng thư mới | Thất bại ở kết nối mới |
| Chứng thư hết hạn | SAN đúng nhưng chứng thư hết hạn | Thất bại |
| CA không tin cậy | SAN đúng nhưng chain không tin cậy | Thất bại |
| SNI sai | Máy chủ trả default certificate không khớp reference | Thất bại |
| Proxy TLS interception | Proxy trình bày chứng thư không được policy tin cậy hoặc sai hostname | Thất bại |

### Kiểm thử ở nhiều lớp

- Unit test cho logic chọn reference identifier từ URL, bao gồm DNS name, IPv4, IPv6 và redirect.
- Integration test dùng TLS test server có các certificate fixture khác nhau.
- Negative test xác nhận client đóng kết nối khi SAN không khớp.
- Test trên đúng runtime và trust store sẽ dùng ở production.
- Test qua CDN, load balancer, service mesh hoặc outbound proxy nếu chúng nằm trên đường đi thực tế.
- Regression test xác nhận cấu hình không vô tình bật **InsecureSkipVerify**, **verify=False** hoặc **rejectUnauthorized=false**.

Không chỉ kiểm tra mã trả về của HTTP. Nếu hostname verification thất bại, ứng dụng không được gửi request body hoặc thông tin xác thực qua kết nối đó.

## 19. Tình huống thực tế

### Tình huống A: CNAME trỏ sang nhà cung cấp CDN

Một doanh nghiệp cấu hình **shop.example.com** là CNAME trỏ tới **tenant-42.cdn-provider.net**. Client truy cập **https://shop.example.com**.

CDN cần phục vụ chứng thư có SAN bao phủ **shop.example.com**. Chứng thư chỉ có **tenant-42.cdn-provider.net** không đáp ứng reference identifier của client, dù DNS resolution hoàn toàn chính xác.

Khi chẩn đoán, cần kiểm tra chứng thư mà edge trả về khi nhận SNI **shop.example.com**, không chỉ kiểm tra chứng thư tại hostname nội bộ của nhà cung cấp.

### Tình huống B: Gọi service nội bộ qua IP

Một service gọi **https://10.20.4.12:9443** trong khi certificate của backend chỉ chứa **DNS:orders.internal.example**.

Nếu client dùng IP literal làm reference identifier, hostname verification phải tìm IP SAN tương ứng và sẽ thất bại. Có hai hướng thiết kế:

- Gọi bằng **orders.internal.example**, để DNS hoặc service discovery phân giải tên sang IP; chứng thư có DNS SAN đúng tên.
- Nếu bắt buộc dùng IP literal làm danh tính endpoint, phát hành chứng thư có IP SAN đúng địa chỉ.

Không sửa lỗi bằng cách tắt hostname verification hoặc viết verifier luôn trả về thành công.

### Tình huống C: Reverse proxy xác minh upstream

API gateway nhận request từ client ở **api.example.com**, sau đó gọi backend **orders.service.local**.

Client xác minh chứng thư edge theo **api.example.com**. Gateway phải xác minh chứng thư backend theo **orders.service.local**, cấu hình SNI tương ứng và tin cậy CA nội bộ theo policy. Nếu gateway chỉ bật TLS encryption mà bỏ qua hostname verification upstream, kẻ tấn công trong mạng nội bộ có thể giả mạo backend.

### Tình huống D: Xoay vòng certificate

Chứng thư cũ của **payments.example.com** sắp hết hạn. Đội vận hành phát hành chứng thư mới nhưng CSR chỉ có **CN=payments.example.com**, thiếu SAN.

Một số client legacy có thể vẫn kết nối; client hiện đại từ chối. Sự khác biệt giữa môi trường tạo ra lỗi khó dự đoán. Quy trình phát hành cần kiểm tra SAN trong CSR và certificate đã ký trước khi rollout. Chỉ đánh dấu rollout thành công sau khi kiểm thử từ client thực tế.

## 20. Checklist triển khai

### Thiết kế và phát hành

- [ ] Mỗi endpoint có danh sách reference hostname hoặc IP rõ ràng.
- [ ] Certificate có SAN bao phủ đúng các DNS name/IP cần phục vụ.
- [ ] Không phụ thuộc vào CN-only certificate.
- [ ] Wildcard được giới hạn trong phạm vi cần thiết và có owner.
- [ ] Tên IDN được chuẩn hóa theo một chính sách IDNA thống nhất.
- [ ] Mọi SAN bổ sung có phê duyệt và audit trail.
- [ ] Private key được lưu trữ, phân quyền và xoay vòng theo policy.

### Cấu hình client

- [ ] Hostname verification được bật mặc định.
- [ ] SNI được cấu hình đúng cho virtual hosting.
- [ ] Trust store chứa đúng CA cần tin cậy.
- [ ] Custom trust manager không bỏ qua endpoint identity.
- [ ] Redirect xác minh hostname mới ở từng kết nối.
- [ ] DNS CNAME không làm thay đổi reference identifier.
- [ ] IP literal được kiểm tra bằng IP SAN.
- [ ] Không bật tùy chọn insecure trong production.

### Vận hành và kiểm thử

- [ ] Kiểm thử từ đúng container, runtime, proxy và trust store.
- [ ] Có negative test cho SAN sai, thiếu SAN, wildcard sai và IP mismatch.
- [ ] Theo dõi handshake failure theo hostname và node.
- [ ] Kiểm tra chứng thư tại tất cả edge/load balancer/replica.
- [ ] Có quy trình xử lý hostname mismatch và rollout certificate.
- [ ] Có regression test ngăn việc vô tình tắt xác minh TLS.

## 21. Câu hỏi tự kiểm tra

**1. Chứng thư được CA tin cậy ký nhưng SAN không chứa hostname đang truy cập có được chấp nhận không?**

Không. Trust chain hợp lệ không thay thế hostname verification. Client phải từ chối vì chứng thư không đại diện cho reference identifier.

**2. URL https://api.example.com:8443/orders dùng hostname nào để kiểm tra?**

**api.example.com**. Port và path không tham gia so khớp hostname.

**3. DNS của api.example.com trả về IP 192.0.2.10. Client có thể kiểm tra chứng thư theo IP đó thay cho hostname không?**

Không theo mặc định. Reference identifier vẫn là **api.example.com**; DNS chỉ cung cấp địa chỉ định tuyến.

**4. SAN có DNS:192.0.2.10 có đủ cho URL dùng IP literal không?**

Không. Địa chỉ IP cần SAN kiểu **iPAddress**, không phải chuỗi DNS-ID.

**5. *.example.com có khớp v2.api.example.com không?**

Không. Wildcard chỉ khớp một label ở vị trí được phép.

**6. Wildcard *.example.com có khớp example.com không?**

Không. Apex domain không có label con để wildcard đại diện.

**7. SNI có thay thế hostname verification không?**

Không. SNI giúp máy chủ chọn virtual host/chứng thư; client vẫn phải xác minh SAN của chứng thư được gửi.

**8. CNAME trỏ từ shop.example.com tới tenant.cdn.net. Client xác minh tên nào?**

Client xác minh **shop.example.com**, vì đó là reference identifier trong yêu cầu ban đầu.

**9. Chứng thư chỉ có CN đúng hostname nhưng thiếu SAN có nên được dùng cho hệ thống mới không?**

Không. Hệ thống mới nên phát hành SAN đầy đủ và dùng mô hình xác minh hiện đại.

**10. Nếu dùng mTLS, hostname verification có biến mất không?**

Không. Client vẫn xác minh server certificate và hostname. Server xác minh client certificate theo policy riêng.

**11. Có thể thêm CA nội bộ vào trust store rồi tắt hostname verification không?**

Không. Thêm CA chỉ giải quyết trust anchor. Client vẫn phải xác minh chứng thư đại diện đúng endpoint.

**12. Khi HTTP redirect sang hostname khác, kết quả xác minh hostname ban đầu có được tái sử dụng không?**

Không. Kết nối mới phải xác minh chứng thư theo hostname mới.

**13. Vì sao custom verifier luôn trả về true nguy hiểm?**

Nó loại bỏ kiểm tra danh tính endpoint và cho phép chứng thư của máy chủ khác được chấp nhận, mở đường cho MITM.

**14. Nếu OpenSSL kiểm tra thành công nhưng ứng dụng thất bại, nên kiểm tra điều gì?**

So sánh runtime, CA bundle, proxy, SNI, hostname thực tế, chứng thư được trả về và cấu hình TLS của ứng dụng.

**15. Hostname verification có chứng minh người dùng được phép gọi API không?**

Không. Nó xác thực danh tính máy chủ ở tầng TLS. Authorization và authentication người dùng/workload vẫn phải được thực hiện riêng.

## 22. Kết luận

Hostname verification ràng buộc kết nối TLS với đúng danh tính mà ứng dụng định truy cập. Client lấy reference identifier từ đích yêu cầu, đọc DNS-ID hoặc IP-ID trong SAN của chứng thư, rồi áp dụng quy tắc so khớp tiêu chuẩn. SNI hỗ trợ máy chủ chọn chứng thư nhưng không thay thế phép kiểm tra này.

Một triển khai an toàn cần giữ xác minh mặc định của thư viện TLS, phát hành SAN đúng, quản trị wildcard và alias có kiểm soát, xác minh riêng từng TLS hop và kiểm thử các trường hợp phải bị từ chối. Khi hostname mismatch xảy ra, cần sửa danh tính, chứng thư hoặc routing theo đúng nguyên nhân; bỏ qua lỗi sẽ làm mất một lớp bảo vệ quan trọng của TLS.

## 23. Tài liệu tham khảo

- RFC 9525 — Service Identity in TLS: quy tắc reference identifier, presented identifier và xác minh danh tính dịch vụ trong TLS.
- RFC 5280 — Internet X.509 Public Key Infrastructure Certificate and CRL Profile: cấu trúc chứng thư X.509, SAN, certificate path validation và CRL.
- RFC 8446 — The Transport Layer Security (TLS) Protocol Version 1.3: handshake TLS 1.3 và cơ chế xác thực phía máy chủ.
- RFC 6066 — Transport Layer Security (TLS) Extensions: Server Name Indication (SNI).
- Tài liệu chính thức của thư viện TLS/runtime đang dùng: Python ssl, Java JSSE/HttpClient, Go crypto/tls, OpenSSL và curl.

