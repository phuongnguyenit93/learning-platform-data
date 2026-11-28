# Trust boundary và data flow trong threat modeling mạng

Một sơ đồ mạng có thể cho thấy firewall, VPN, subnet và các máy chủ nhưng vẫn bỏ sót câu hỏi quan trọng: **dữ liệu đi từ đâu đến đâu, ai được quyền gửi, ai có thể sửa, và giả định tin cậy thay đổi tại bước nào?** Hai khái niệm **data flow** (luồng dữ liệu) và **trust boundary** (ranh giới tin cậy) giúp trả lời câu hỏi đó trước khi chọn biện pháp phòng vệ.

Bài học thuộc chương **Threat modeling mạng**, trong phạm vi **SECURITY_NETWORK_SECURITY**. Mục tiêu là dùng mô hình luồng dữ liệu và ranh giới tin cậy để phân tích bề mặt tấn công, nhận diện nguy cơ khi lưu lượng đi qua nhiều vùng, rồi lựa chọn phân đoạn, firewall, VPN/ZTNA, xác thực kết nối, bảo vệ DNS, IDS/IPS và kiểm soát hạ tầng đám mây một cách có căn cứ.

## 1. Hai khái niệm cốt lõi

### 1.1. Data flow là gì?

**Data flow** là đường trao đổi thông tin giữa hai thực thể trong phạm vi hệ thống đang phân tích. Một luồng có thể chứa dữ liệu nghiệp vụ, thông tin xác thực, lệnh điều khiển, sự kiện giám sát hoặc bản sao lưu.

Ví dụ:

- Trình duyệt gửi yêu cầu HTTPS tới cổng API.
- API truy vấn cơ sở dữ liệu qua kết nối TLS.
- Dịch vụ lấy khóa xác minh token từ nhà cung cấp danh tính.
- Ứng dụng gửi log tới hệ thống quan sát tập trung.
- Máy chủ cập nhật địa chỉ dịch vụ qua DNS; nhân viên quản trị truy cập qua kênh quản lý riêng.

Trong **Data Flow Diagram (DFD)**, luồng thường được vẽ bằng mũi tên có hướng và tên dữ liệu. DFD mô tả **quan hệ xử lý và truyền dữ liệu ở mức logic**; nó không nhất thiết mô tả toàn bộ gói tin, đường đi vật lý, mọi hop định tuyến hoặc chi tiết TCP.

Một yêu cầu và phản hồi có thể được vẽ thành hai mũi tên nếu sự khác biệt quan trọng cho phân tích đe dọa. Tương tự, luồng đọc dữ liệu và luồng ghi dữ liệu thường cần tách riêng vì quyền và tác động an ninh khác nhau.

### 1.2. Trust boundary là gì?

**Trust boundary** là ranh giới mà tại đó **mức độ tin cậy, quyền kiểm soát, danh tính, đặc quyền hoặc giả định bảo vệ dữ liệu thay đổi**. Bất kỳ dữ liệu hay hành động nào vượt qua ranh giới đó đều cần được đánh giá theo chính sách của bên nhận.

Các ví dụ phổ biến:

| Ranh giới | Sự thay đổi cần chú ý | Câu hỏi bảo mật |
|---|---|---|
| Internet → reverse proxy/gateway | Nguồn bên ngoài vào điểm tiếp nhận công khai | Ai là nguồn gửi? Có TLS, giới hạn tốc độ, kiểm tra đầu vào và giám sát không? |
| Gateway → API nội bộ | TLS có thể kết thúc; yêu cầu đi vào vùng xử lý khác | Gateway đã xác thực backend chưa? API có tự kiểm tra quyền không? |
| API → cơ sở dữ liệu | Thành phần xử lý được phép đọc/ghi dữ liệu nhạy cảm | Tài khoản dịch vụ có quyền tối thiểu không? Có tách dữ liệu giữa người dùng/tenant không? |
| Workload → dịch vụ SaaS/IdP | Chuyển sang đơn vị và cơ chế quản trị khác | Danh tính đầu nhận, dữ liệu gửi đi và sự phụ thuộc bên thứ ba được kiểm soát thế nào? |
| Nhân viên → giao diện quản trị | Quyền hạn tăng, có thể đổi cấu hình hệ thống | Có MFA, xác thực thiết bị, kiểm soát đặc quyền và nhật ký thao tác không? |
| Pod/dịch vụ A → Pod/dịch vụ B cùng cluster | Khác tiến trình, danh tính và quyền nghiệp vụ dù cùng mạng | Có xác thực từng dịch vụ và kiểm tra quyền cho từng lời gọi không? |

Ranh giới tin cậy **không đồng nghĩa** với ranh giới subnet, VLAN, VPC, firewall hoặc địa chỉ IP. Một subnet có thể chứa các workload ở mức tin cậy khác nhau; hai hệ thống ở hai subnet cũng có thể cùng thuộc một miền quản trị. Phân đoạn mạng là **một cơ chế thực thi**, không tự tạo ra bằng chứng rằng nội dung hoặc danh tính đã đáng tin.

Đặt tên rõ cho từng ranh giới, ví dụ **TB1: nguồn không tin cậy → edge**, **TB2: edge → ứng dụng**, **TB3: ứng dụng → dữ liệu**. Mỗi lần vượt TB cần xác định điều kiện được chấp nhận và cách kiểm chứng.

### 1.3. Đặt phạm vi để tránh khái niệm “tin cậy tuyệt đối”

Không có một vùng mạng nào mặc nhiên an toàn trong mọi ngữ cảnh. “Trusted” trong một sơ đồ chỉ có nghĩa là **có một tập giả định cụ thể**: ai sở hữu hệ thống, loại danh tính nào có mặt, được phép thực hiện thao tác nào và đã triển khai kiểm soát gì.

Chẳng hạn, API có thể tin cậy gateway để chặn lưu lượng bất thường, nhưng vẫn phải **tự phân quyền theo đối tượng dữ liệu**. Database có thể chấp nhận kết nối từ API mà không vì vậy cho phép API dùng tài khoản quản trị cơ sở dữ liệu.

## 2. Thành phần của DFD phục vụ threat modeling

Một DFD hiệu quả tối thiểu mô tả bốn loại đối tượng và ranh giới tin cậy:

| Thành phần | Ký hiệu gợi ý | Cách nhận diện | Ví dụ |
|---|---|---|---|
| **External entity** (thực thể bên ngoài) | Hình chữ nhật | Bên tương tác với hệ thống nhưng nằm ngoài phạm vi kiểm soát được chọn | Người dùng, nhà cung cấp IdP, đối tác API |
| **Process** (tiến trình xử lý) | Ô tiến trình | Nhận và biến đổi dữ liệu, ra quyết định hoặc điều phối | API, gateway, job xử lý nền |
| **Data store** (kho dữ liệu) | Hình trụ / ký hiệu lưu trữ | Nơi trạng thái được lưu và truy xuất | Database, object storage, kho session |
| **Data flow** (luồng dữ liệu) | Mũi tên có hướng | Loại thông tin di chuyển từ nguồn đến đích | Yêu cầu HTTP, truy vấn SQL, log, token |
| **Trust boundary** (ranh giới tin cậy) | Khung/đường bao quanh nhóm đối tượng | Điểm đổi giả định tin cậy và trách nhiệm bảo vệ | Internet, edge, private workload, data zone |

**Asset** (tài sản cần bảo vệ) không nhất thiết là một ô riêng: một bản ghi khách hàng là tài sản nằm trong data store và cũng có thể xuất hiện trong phản hồi API. Tương tự, thông tin xác thực có thể nằm trên một luồng hoặc trong kho bí mật.

Khi chú thích một data flow, nên bổ sung:

1. **Nguồn, đích và hướng:** ai thực sự chủ động thiết lập kết nối; ai nhận dữ liệu?
2. **Loại dữ liệu và độ nhạy cảm:** dữ liệu công khai, cá nhân, bí mật kinh doanh, token, khóa, metadata quản trị.
3. **Kênh truyền:** giao thức, cổng thông dụng, có mã hóa hay không; TLS kết thúc ở đâu?
4. **Danh tính và quyền:** danh tính người dùng/dịch vụ, cơ chế xác thực, đối tượng được phép truy cập.
5. **Ranh giới đi qua:** đường đi đổi miền quản trị hoặc giả định tin cậy ở điểm nào?
6. **Cơ chế thực thi và quan sát:** firewall, network policy, mTLS, kiểm tra quyền API, log, cảnh báo, giới hạn tốc độ.

Thông tin về **luồng điều khiển** cũng quan trọng: bản cập nhật chính sách, thao tác cấp quyền và quản lý secret có thể tạo tác động lớn hơn cả một truy vấn dữ liệu thông thường.

## 3. Ví dụ xuyên suốt: hệ thống quản lý hồ sơ qua web

Giả định một dịch vụ cho phép người dùng xem hồ sơ của họ. Hệ thống có trình duyệt ngoài Internet, reverse proxy/WAF công khai, API trong vùng ứng dụng riêng, cơ sở dữ liệu, kho log và dịch vụ danh tính (IdP) bên thứ ba. Đây là **kiến trúc minh họa**, không phải sơ đồ một hệ thống đang vận hành.

### 3.1. Sơ đồ DFD mức 1

~~~mermaid
flowchart LR
    subgraph Z0["Ngoài hệ thống: thiết bị người dùng"]
        U["E1: Trình duyệt"]
    end
    subgraph Z1["Vùng edge / ingress (sau TB1)"]
        G["P1: Reverse proxy / WAF"]
    end
    subgraph Z2["Vùng ứng dụng riêng (sau TB2)"]
        A["P2: API hồ sơ"]
    end
    subgraph Z3["Vùng dữ liệu (sau TB3)"]
        D[("D1: Cơ sở dữ liệu hồ sơ")]
    end
    subgraph Z4["Vùng telemetry (sau TB4)"]
        L[("D2: Kho log tập trung")]
    end
    subgraph Z5["Đơn vị danh tính ngoài tổ chức (TB5)"]
        I["E2: Identity Provider"]
    end

    U -->|"F1: HTTPS / yêu cầu API"| G
    G -->|"F2: HTTPS hoặc mTLS / yêu cầu được chuyển tiếp"| A
    A -->|"F3: TLS / đọc ghi hồ sơ"| D
    A -->|"F4: TLS / sự kiện đã lọc"| L
    U -->|"F5: HTTPS / luồng đăng nhập"| I
    A -->|"F6: HTTPS / metadata và khóa công khai"| I
~~~

Các khung mô tả **miền tin cậy được lựa chọn để phân tích**; mã TB xác định ranh giới tại nơi luồng vượt sang miền đó. Mũi tên đi qua đường bao khung là ứng viên cho việc rà soát ranh giới; gateway, API và database vẫn cần kiểm tra bảo mật ngay cả khi cùng một tổ chức sở hữu.

Sơ đồ trên lược bớt phản hồi, DNS, hệ thống quản trị, backup và các luồng nội bộ không có ý nghĩa trực tiếp trong ví dụ ban đầu. Khi threat modeling thực tế, các luồng bị lược bớt **phải được xem xét rồi bổ sung nếu có ảnh hưởng đến tài sản và ranh giới tin cậy**.

### 3.2. Bảng kiểm kê data flow

| Luồng | Nguồn → đích | Nội dung | Kênh minh họa | Kiểm soát cần xác nhận |
|---|---|---|---|---|
| **F1** | Trình duyệt → gateway | Yêu cầu đăng nhập, cookie/token, yêu cầu xem hồ sơ | HTTPS, thường 443 | TLS hợp lệ, rate limiting, kiểm tra header/đầu vào, log an toàn |
| **F2** | Gateway → API | Yêu cầu đã được proxy, ngữ cảnh xác thực | HTTPS hoặc mTLS nội bộ | Xác minh danh tính upstream, hạn chế nguồn, chống giả mạo header, phân quyền tại API |
| **F3** | API → database | Truy vấn và bản ghi hồ sơ | Giao thức DB qua TLS, cổng theo DB | Xác thực máy chủ DB, tài khoản DB quyền tối thiểu, tách dữ liệu, audit |
| **F4** | API → kho log | Thời gian, request ID, mã trạng thái, sự kiện an ninh | TLS tới collector | Không ghi secret/PII không cần thiết, phân quyền đọc log, bảo đảm khả dụng |
| **F5** | Trình duyệt ↔ IdP | Yêu cầu đăng nhập, chuyển hướng và kết quả xác thực | HTTPS | Chống giả mạo callback, kiểm tra `state`/`nonce` theo luồng OIDC, bảo vệ phiên |
| **F6** | API → IdP | Lấy metadata/khóa công khai cho việc kiểm tra token | HTTPS | Tin cậy đúng issuer, kiểm tra TLS, giới hạn đích egress, quản lý vòng đời khóa |

Tùy mô hình đăng nhập, ứng dụng còn có thể trao đổi authorization code/token trực tiếp với IdP. **Đừng mặc định** rằng API sẽ gọi IdP cho *mỗi* yêu cầu: nhiều hệ thống xác minh chữ ký token cục bộ bằng bộ khóa công khai đã tải và lưu đệm.

Để tránh thiếu sót, nhóm vận hành cần bổ sung các luồng “ít nhìn thấy”: phân giải DNS, đồng bộ thời gian, cập nhật phần mềm, phân phối secret, health check, xuất bản log/metrics, truy cập quản trị, sao lưu và khôi phục, đồng bộ dữ liệu sang đối tác, lưu lượng khi scale/failover.

### 3.3. Trust boundary gắn với việc gì?

- **TB1 — ingress:** thiết bị và trình duyệt do người dùng điều khiển gửi dữ liệu tới gateway; không tin dữ liệu đầu vào, tên tệp, header tự khai báo hoặc lưu lượng chỉ vì đã qua HTTPS.
- **TB2 — gateway/API:** nếu gateway kết thúc TLS, chặng gateway–API phải có bảo vệ riêng phù hợp mô hình đe dọa. Chỉ chấp nhận header nhận dạng từ proxy được tin cậy và cấu hình đúng; API vẫn tự kiểm tra quyền truy cập.
- **TB3 — ứng dụng/dữ liệu:** API có thể bị lỗi hoặc bị chiếm; kết nối DB cần quyền giới hạn, kiểm soát truy vấn và bảo vệ dữ liệu theo người dùng/tenant.
- **TB4 — ứng dụng/telemetry:** nội dung log có thể chứa thông tin nhạy cảm; tuyến ghi và quyền đọc log là một bề mặt tấn công độc lập.
- **TB5 — tổ chức/bên thứ ba:** xác minh đúng miền, issuer, audience, chứng chỉ và chuỗi tin cậy khi nhận dữ liệu danh tính; phụ thuộc IdP cũng cần phương án xử lý lỗi.

Một ranh giới có thể có **nhiều luồng** đi qua và một luồng có thể đi qua **nhiều ranh giới**. Khi dùng proxy hoặc service mesh, nên mô tả cả điểm kết thúc TLS, điểm xác thực danh tính và điểm thực thi quyết định cho phép/từ chối.

## 4. Tìm trust boundary trong một kiến trúc thực tế

Hãy rà soát theo các dấu hiệu sau thay vì chỉ dựa vào địa chỉ IP:

### 4.1. Thay đổi miền danh tính và đặc quyền

Ví dụ: trình duyệt chưa đăng nhập → API đã xác thực; workload A → workload B dùng tài khoản dịch vụ khác; nhân viên thường → giao diện quản trị. Mỗi bước phải xác định **ai cấp danh tính, chứng thực thế nào, quyền được kiểm tra ở đâu, và thời hạn có hiệu lực bao lâu**.

Không gộp xác thực và phân quyền: một service account hợp lệ vẫn có thể không được truy cập kho dữ liệu khác.

### 4.2. Thay đổi miền mạng và điểm chặn

Ví dụ: Wi-Fi khách → mạng nhân viên; Internet → DMZ; DMZ → private subnet; VPC A → VPC B; namespace Kubernetes A → B. Tại mỗi điểm cần hỏi có chính sách **default deny**, danh sách luồng cho phép, chống giả mạo nguồn, định tuyến bất thường, giới hạn outbound hay không.

VPN mã hóa đường kết nối tới hệ thống VPN; **đi qua VPN không tự có mọi quyền nội bộ**. Tương tự, NAT và private IP không tự cung cấp xác thực ứng dụng, phân quyền dữ liệu hoặc mã hóa.

### 4.3. Thay đổi quyền quản trị và trách nhiệm

Ví dụ: hệ thống nội bộ → SaaS, hạ tầng công ty → tài khoản cloud đối tác, workload → API quản trị cloud, máy quản trị → firewall/controller. Chú ý **control plane** (nơi cấu hình quyền, mạng, khóa và tài nguyên) khác với **data plane** (nơi dữ liệu nghiệp vụ đi qua). Quyền kiểm soát control plane có thể ảnh hưởng nhiều data flow cùng lúc.

### 4.4. Thay đổi trạng thái bảo vệ dữ liệu

Ví dụ: TLS kết thúc tại load balancer, dữ liệu được giải mã để xử lý, log được xuất qua mạng khác, file được lưu vào object storage hoặc sao lưu ra tài khoản cloud thứ hai. Tại đây cần kiểm tra tính bảo mật, toàn vẹn, yêu cầu lưu trữ và người đọc được dữ liệu.

**Cách kiểm tra:** với từng mũi tên, giả sử nguồn bị xâm nhập, hoặc dữ liệu bị thay đổi trên đường đi. Thành phần nhận có còn tự bảo vệ được tài sản của mình không? Nếu không, đó là giả định tin cậy cần được ghi thành rủi ro.

## 5. Quy trình xây dựng DFD và phân tích đe dọa

### Bước 1 — Chốt phạm vi và tài sản

Viết rõ hệ thống nào đang xét, điều gì nằm ngoài phạm vi, môi trường triển khai (on-premise, cloud, Kubernetes, hybrid), các tác nhân có quyền hợp pháp và mức độ nhạy cảm của dữ liệu.

Ví dụ tài sản: thông tin hồ sơ, khóa ký token, dữ liệu xác thực, tính sẵn sàng của API, cấu hình firewall, quyền quản trị tài khoản cloud. Ghi giả định và điều chưa kiểm chứng; tránh suy ra “private subnet = hoàn toàn tin cậy”.

### Bước 2 — Vẽ DFD mức ngữ cảnh

Ở **DFD mức ngữ cảnh (level 0)**, có thể coi toàn bộ hệ thống là một tiến trình duy nhất và nối nó với người dùng, đối tác/IdP và các hệ thống bên ngoài. Mục tiêu là nhận diện **mọi đầu vào/đầu ra**; các kho dữ liệu nội bộ thường được thể hiện khi phân rã sơ đồ, không sa vào cấu hình từng subnet.

Sau đó phân rã thành **DFD mức 1**: gateway, API, background job, database, log collector, secret manager và các hệ thống cần thiết. Chỉ tách thêm nếu việc chia nhỏ giúp nhận diện luồng hoặc ranh giới chưa được kiểm soát.

### Bước 3 — Kiểm kê luồng hai chiều và trạng thái dữ liệu

Mỗi luồng có mã duy nhất, mục đích, nguồn/đích, giao thức, cổng, mức nhạy cảm, xác thực, mã hóa, ranh giới vượt qua và chủ sở hữu. Ghi riêng các luồng **quản trị, backup, telemetry, DNS, đồng bộ, callback và egress**.

Chú ý dữ liệu nhận từ đối tác có thể được **lưu lâu dài**, rồi trở thành đầu vào không tin cậy trong một job khác. Threat modeling không chỉ dừng ở lần truyền đầu tiên.

### Bước 4 — Đánh dấu trust boundary và giả định

Khoanh theo miền kiểm soát, danh tính, quyền, phân loại dữ liệu và điểm thay đổi trạng thái mã hóa. Gắn mã TB1, TB2... rồi chú thích **chính sách phải được thực thi** khi đi qua.

Một câu mô tả tốt: “Chỉ gateway sở hữu danh tính dịch vụ X được gọi API qua mTLS; API xác thực ngữ cảnh người dùng và phân quyền từng hồ sơ.” Câu “hai bên đều ở mạng nội bộ” chưa đủ làm giả định an toàn.

### Bước 5 — Tạo tình huống đe dọa bằng STRIDE

STRIDE là một khung hỏi hệ thống:

| Nhóm | Câu hỏi với luồng/ranh giới | Ví dụ gần kiến trúc minh họa |
|---|---|---|
| **S — Spoofing** (giả mạo) | Kẻ tấn công có thể mạo danh nguồn, máy chủ hay tài khoản dịch vụ không? | API tin header `X-User-Id` gửi trực tiếp từ Internet |
| **T — Tampering** (sửa đổi) | Dữ liệu/định tuyến/cấu hình có thể bị thay trái phép không? | Chặng gateway–API truyền dữ liệu không được bảo vệ trong mạng có nguy cơ bị nghe lén, sửa đổi |
| **R — Repudiation** (chối bỏ) | Có đủ bằng chứng gắn hành động với chủ thể để điều tra không? | Thao tác xóa hồ sơ không có log danh tính và request ID |
| **I — Information disclosure** (lộ thông tin) | Ai có thể đọc dữ liệu nhạy cảm trên đường truyền, trong lưu trữ hoặc log? | Session token bị ghi vào hệ thống log mà nhiều người được xem |
| **D — Denial of service** (từ chối dịch vụ) | Thành phần/đường truyền/phụ thuộc nào bị làm cạn tài nguyên? | Lưu lượng tăng đột biến làm cạn kết nối database hoặc quota IdP |
| **E — Elevation of privilege** (leo thang đặc quyền) | Một danh tính hạn chế có thể đạt quyền lớn hơn nhờ sai kiểm tra hay cấu hình không? | API dùng tài khoản DB có quyền quản trị cho tác vụ đọc hồ sơ |

STRIDE là công cụ gợi ý **các kịch bản có nguyên nhân và hậu quả cụ thể**, không phải bảng kiểm mà chỉ cần đánh dấu đủ sáu ô. Có thể kết hợp phân tích quyền riêng tư, gian lận, phụ thuộc chuỗi cung ứng và tính sẵn sàng tùy loại hệ thống.

### Bước 6 — Chấm mức ưu tiên và chọn kiểm soát

Với mỗi kịch bản, ghi **điều kiện khai thác, tài sản bị ảnh hưởng, hậu quả, khả năng xảy ra, biện pháp đang có và phần rủi ro còn lại**. Có thể dùng thang Độ ảnh hưởng × Khả năng (Cao/Trung bình/Thấp) để ưu tiên, nhưng cần ghi lý do, không xem điểm là sự thật khách quan.

Ưu tiên xử lý vấn đề có thể làm lộ dữ liệu hàng loạt, mất quyền quản trị hoặc gián đoạn diện rộng. Gắn mỗi biện pháp với **chủ sở hữu, bằng chứng cấu hình/kiểm thử và điều kiện hoàn thành**.

### Bước 7 — Kiểm chứng và cập nhật mô hình

Đối chiếu DFD với cấu hình thực: ingress, egress, firewall, security group, network policy, DNS, chứng chỉ, IAM, endpoint và log. Dùng review kiến trúc, kiểm thử phân quyền, kiểm tra cấu hình và diễn tập sự cố theo phạm vi được cấp phép.

Cập nhật DFD khi thêm API, bên thứ ba, vùng cloud, luồng backup, cơ chế xác thực, thay đổi TLS termination hoặc phân quyền. Một mô hình sai vì không còn phản ánh triển khai thực tế có thể gây đánh giá thiếu rủi ro.

## 6. Risk register mẫu cho các ranh giới

Một **risk register** liên kết đe dọa với chính xác luồng và quyết định cần kiểm tra:

| ID | Điểm bị đe dọa | Kịch bản và tác động | Kiểm soát đề xuất | Cách xác minh |
|---|---|---|---|---|
| **R01** | F1 / TB1 | Kẻ tấn công gửi lượng lớn yêu cầu khiến gateway hoặc API quá tải (D) | Rate limit theo ngữ cảnh, quota, bảo vệ DDoS, giám sát độ trễ/lỗi | Thử tải có giới hạn và xem cảnh báo, tỷ lệ chặn |
| **R02** | F2 / TB2 | Kẻ ngoài giả mạo header danh tính hoặc gọi thẳng API bỏ qua gateway (S/E) | Chỉ cho gateway gọi API; xác thực dịch vụ; xóa/ghi đè header không tin cậy; phân quyền tại API | Kiểm tra đường gọi trực tiếp bị chặn, quyền đối tượng được áp dụng |
| **R03** | F2 / TB2 | Gateway kết thúc TLS, chặng nội bộ bị nghe lén/chỉnh sửa (I/T) | TLS/mTLS upstream khi mô hình đe dọa yêu cầu, xác minh chứng chỉ, network policy | Kiểm tra cấu hình TLS và danh tính peer, thử kết nối sai chứng chỉ |
| **R04** | F3 / TB3 | Workload bị chiếm dùng tài khoản DB quyền quá rộng để đọc nhiều hồ sơ (I/E) | Least privilege ở DB, tách tenant, kiểm tra quyền nghiệp vụ, kiểm soát outbound | Audit role DB, kiểm thử truy cập chéo tài khoản/tenant |
| **R05** | F4 / TB4 | Token/PII xuất hiện trong log, người ngoài nhóm có thể đọc (I) | Lọc/redact trường nhạy cảm, hạn chế quyền đọc, retention phù hợp | Rà soát mẫu log và quyền truy cập kho log |
| **R06** | F5–F6 / TB5 | Nhầm issuer/audience hoặc callback khiến danh tính bị chấp nhận sai (S/E) | Xác minh issuer, audience, chữ ký token, callback/state/nonce theo giao thức | Kiểm thử token sai issuer/audience, callback không hợp lệ |
| **R07** | Luồng egress chưa vẽ | SSRF hoặc cấu hình sai khiến workload truy cập endpoint nội bộ/metadata cloud (I/E) | Egress policy, kiểm tra URL/đích ở ứng dụng, bảo vệ metadata service, IAM tối thiểu | Rà soát đường egress, quyền của workload và cấu hình metadata |
| **R08** | Kênh quản trị chưa vẽ | Một tài khoản vận hành bị chiếm có thể sửa firewall/IAM trên nhiều vùng (E/T) | MFA chống phishing khi phù hợp, quyền đặc quyền tối thiểu, tách quản trị, audit | Kiểm tra đường truy cập quản trị và nhật ký thay đổi |

Các ID và mức kiểm soát trên là **ví dụ phân tích**, chưa phải kết quả đánh giá mức độ rủi ro thực tế. Nên bổ sung cột **owner, mức ưu tiên, trạng thái xử lý, ngày kiểm chứng và rủi ro còn lại** trong hệ thống quản lý công việc của đội.

### Viết một threat scenario đủ cụ thể

Thay vì ghi “nguy cơ bị hack API”, hãy mô tả:

> Khi API cho phép kết nối trực tiếp từ mọi workload trong VPC và chấp nhận `X-User-Id` mà không xác thực nguồn, một workload nội bộ bị chiếm có thể tự đặt danh tính người khác và đọc hồ sơ trái phép.

Từ mô tả này xác định được:

- **Điểm bắt đầu:** một workload có khả năng truy cập API nội bộ.
- **Điểm vượt ranh giới:** từ miền của workload nguồn sang miền ra quyết định của API (TB2).
- **Tài sản:** hồ sơ người dùng.
- **Lỗi tin cậy:** API coi header do nguồn cung cấp là thông tin đã xác minh.
- **Kiểm soát:** xác thực service-to-service, chỉ chấp nhận ngữ cảnh danh tính qua kênh được thiết kế, kiểm tra quyền đối tượng tại API và giới hạn luồng nội bộ.
- **Bằng chứng:** yêu cầu không có định danh được xác minh hoặc yêu cầu với ID người khác bị từ chối; nhật ký đủ cho việc điều tra.

## 7. Biến mô hình thành kiến trúc phòng vệ mạng

### 7.1. Phân đoạn và lọc luồng

Với mỗi trust boundary, bắt đầu từ **nhu cầu giao tiếp hợp lệ**, sau đó áp chính sách ở nơi có thể thực thi:

| Lớp | Kiểm soát thường dùng | Lưu ý |
|---|---|---|
| Mạng doanh nghiệp | VLAN/subnet, firewall, ACL, VPN/ZTNA, NAC khi phù hợp | Xác định rõ đường truy cập giữa người dùng, khách, hệ thống vận hành và sản xuất |
| Hạ tầng cloud | VPC/VNet, subnet, security group, network ACL, route table, private endpoint | Cấu hình theo luồng được phép; khác biệt stateful/stateless tùy loại kiểm soát và nền tảng |
| Container/Kubernetes | NetworkPolicy/CNI phù hợp, ingress/egress rules, identity/service mesh nếu sử dụng | NetworkPolicy chỉ có tác dụng trong phạm vi plugin mạng hỗ trợ; không thay kiểm tra quyền API |
| Tầng ứng dụng | Authentication, authorization, input validation, quota | Bảo vệ dữ liệu ngay cả khi một workload nội bộ bị chiếm |
| Kênh truyền | TLS/mTLS, xác minh chứng chỉ, quản lý khóa/chứng chỉ | Kiểm tra cả điểm kết thúc TLS, rotate chứng chỉ và ranh giới tin cậy sau giải mã |

Ví dụ, với F3 chỉ cho danh tính/workload API kết nối tới cổng DB đã định; cấm truy cập DB trực tiếp từ Internet và từ các workload không liên quan. Tuy nhiên, **network allowlist không thay thế vai trò và quyền truy vấn của tài khoản DB**.

### 7.2. Phòng vệ lưu lượng vào, ra và nội bộ

- **North–south traffic:** lưu lượng từ ngoài vào hoặc từ hệ thống ra ngoài; tập trung ở DNS, ingress, egress, WAF, gateway, proxy và kiểm soát outbound.
- **East–west traffic:** trao đổi giữa các workload nội bộ; cần nhận diện lời gọi service-to-service, quyền cụ thể và lưu lượng bất thường do xâm nhập lan truyền.
- **Management/control-plane traffic:** thao tác cấu hình cloud, firewall, cluster, IAM, secret; cần đường quản trị có danh tính mạnh, kiểm soát đặc quyền và audit độc lập.

Một WAF hoặc IDS/IPS có thể phát hiện/chặn một số kiểu lưu lượng đáng ngờ; **không bảo đảm** ngăn được yêu cầu hợp lệ về cú pháp nhưng trái quyền nghiệp vụ. Hệ thống phát hiện xâm nhập cũng phụ thuộc vị trí quan sát, khả năng giải mã/phân tích và chất lượng cảnh báo.

### 7.3. DNS và kết nối ra ngoài là data flow

DNS thường xuất hiện trước khi truy cập HTTP/API và có thể là nguồn sai lệch định tuyến hoặc rò rỉ tên miền được truy vấn. Khi mô hình hóa cần ghi **ai dùng resolver nào, có chặn DNS tùy ý, có giám sát thay đổi bản ghi và cách kiểm tra chứng chỉ đích**. DNSSEC có thể bảo vệ tính xác thực của dữ liệu DNS khi được triển khai đúng; nó **không thay thế HTTPS/TLS** hoặc bảo đảm dịch vụ đích không bị xâm nhập.

Với luồng egress của workload, ghi rõ đích được gọi (IdP, kho cập nhật, API đối tác), loại dữ liệu gửi đi và danh tính bên đích. Kiểm soát egress có thể giảm phạm vi liên lạc tới endpoint nhạy cảm hoặc dịch vụ không được phê duyệt, nhưng phải kết hợp kiểm tra URL/redirect và quyền của workload.

### 7.4. Cloud và mạng không dây

Trong cloud, một workload thường có cả **quyền mạng** (gọi tới endpoint nào) và **quyền IAM** (được gọi API hạ tầng hoặc đọc tài nguyên nào). Hai quyền này cần được đánh giá đồng thời. Một workload ở subnet riêng nhưng gắn role quá rộng vẫn có thể gây hậu quả lớn.

Với mạng Wi-Fi, ranh giới giữa thiết bị khách, thiết bị nhân viên và hệ thống nội bộ quan trọng hơn tên SSID. Kiểm tra tách mạng, xác thực thiết bị/người dùng, giới hạn truy cập nội bộ và kênh quản trị access point. **Có mật khẩu Wi-Fi không đồng nghĩa mọi thiết bị trong mạng đều đáng tin.**

## 8. Tài liệu hóa data flow dưới dạng có thể kiểm tra

Ngoài sơ đồ, có thể lưu một bản ghi luồng minh họa như sau:

~~~yaml
flowId: F2
source: EDGE_GATEWAY
destination: PROFILE_API
purpose: Chuyển tiếp yêu cầu xem hồ sơ
protocol: HTTPS
destinationPort: 8443
dataClasses:
  - request_metadata
  - user_context
trustBoundary: TB2
sourceIdentity: gateway_service
requiredControls:
  - Xác minh chứng chỉ và danh tính upstream
  - Chỉ chấp nhận nguồn được cho phép
  - Không tin header danh tính do client tự gửi
  - API kiểm tra quyền truy cập từng hồ sơ
monitoring:
  - TLS handshake failures
  - unauthorized access attempts
  - request ID và kết quả truy cập
owner: application_and_platform_team
~~~

Đây chỉ là **mẫu trao đổi trong tài liệu kiến trúc**; tên field và cổng là giá trị minh họa, không đại diện cho một cấu hình có thật. DFD được duy trì tốt khi mã luồng trong sơ đồ khớp với cấu hình firewall, các quy tắc IAM/NetworkPolicy, thông số giám sát và danh mục rủi ro.

## 9. Bài tập thực hành phân tích ranh giới

**Tình huống:** Một hệ thống bán hàng có API trong private subnet, database riêng và bộ xử lý ảnh chạy trong cluster. Người dùng tải ảnh lên qua gateway; bộ xử lý ảnh tải một URL do người dùng cung cấp để lấy ảnh bổ sung. Cả API và bộ xử lý đều dùng chung một role cloud có quyền đọc object storage chứa hóa đơn.

Hãy tự trả lời:

1. Những thành phần/luồng nào cần bổ sung vào DFD mức 1?
2. URL do người dùng cung cấp vượt qua những ranh giới tin cậy nào?
3. Vì sao đặt bộ xử lý trong private subnet chưa đủ để bảo vệ object storage?
4. Cần ưu tiên những kiểm soát mạng, danh tính và ứng dụng nào?
5. Có thể dựa vào tín hiệu giám sát nào để phát hiện hoạt động bất thường?

**Gợi ý đối chiếu:**

- Vẽ thêm luồng **browser → gateway → API → object storage/queue → image worker**, luồng **image worker → URL bên ngoài**, **worker → object storage hóa đơn** (nếu role cho phép), log và metadata cloud; chú thích dữ liệu tin cậy/không tin cậy.
- URL của người dùng là đầu vào không tin cậy; khi worker gọi đích, hành động vượt từ **nội dung do bên ngoài kiểm soát** sang **quyền mạng và danh tính của workload**. Đây là điểm cần xét **SSRF**, điều hướng lại, phân giải DNS và kết nối tới địa chỉ nội bộ/metadata.
- Tách role cloud giữa API, worker và dữ liệu hóa đơn; chặn quyền đọc kho hóa đơn từ worker, áp egress policy, kiểm tra và giới hạn đích URL theo nhu cầu, kiểm soát kích thước/loại nội dung và giới hạn tài nguyên xử lý.
- Theo dõi yêu cầu đi tới đích bất thường, quyền truy cập object storage bị từ chối, thay đổi role/policy, DNS bất thường, tốc độ tải và mức tài nguyên worker. Giới hạn quyền và kiểm thử các đường bị từ chối theo môi trường được phép.

## 10. Checklist khi review kiến trúc

- [ ] Phạm vi, tài sản, tác nhân và hệ thống ngoài được ghi rõ.
- [ ] DFD mô tả ingress, egress, east–west, quản trị, DNS, log và backup khi có liên quan.
- [ ] Mỗi data flow có hướng, nguồn/đích, loại dữ liệu, giao thức, danh tính, quyền và chủ sở hữu.
- [ ] Mọi điểm đổi miền tin cậy, quyền quản trị hoặc trạng thái TLS được đánh dấu bằng trust boundary.
- [ ] Không dùng subnet/private IP/VPN/WAF làm lý do duy nhất để tin một request.
- [ ] Có biện pháp xác thực và phân quyền ở đúng thành phần tiếp nhận, đặc biệt với API và kho dữ liệu.
- [ ] Firewall, security group, network policy, IAM và egress policy được kiểm tra theo luồng cho phép.
- [ ] Luồng chứa token, secret, dữ liệu cá nhân và log được giới hạn truy cập phù hợp.
- [ ] Mỗi kịch bản đe dọa quan trọng có tác động, biện pháp xử lý, người chịu trách nhiệm và cách kiểm chứng.
- [ ] Mô hình được cập nhật khi kiến trúc, quyền hoặc đường đi dữ liệu thay đổi.

**Ghi nhớ:** **data flow** chỉ ra dữ liệu và quyền đang di chuyển ở đâu; **trust boundary** chỉ ra nơi phải thay đổi giả định và thực thi kiểm soát. Threat modeling mạng có giá trị khi hai thành phần này gắn với tài sản cụ thể, kịch bản tấn công có thể kiểm tra và bằng chứng từ cấu hình thực tế.
