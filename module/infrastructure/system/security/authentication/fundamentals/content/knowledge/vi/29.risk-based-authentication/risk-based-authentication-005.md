# Impossible travel — Phát hiện đăng nhập từ các vị trí khó có thể di chuyển kịp

> **Chương:** Risk-based authentication  
> **Chủ đề:** Impossible travel

**Impossible travel** là một tín hiệu phát hiện rủi ro trong xác thực dựa trên ngữ cảnh. Hệ thống so sánh các sự kiện đăng nhập hoặc xác thực của cùng một danh tính tại những thời điểm khác nhau. Nếu hai vị trí suy ra từ địa chỉ IP cách nhau quá xa so với khoảng thời gian giữa các sự kiện, hệ thống đánh dấu khả năng credential hoặc session đang được sử dụng bởi nhiều người, bị đánh cắp, hoặc đi qua hạ tầng mạng trung gian bất thường.

Ví dụ, một tài khoản vừa đăng nhập thành công từ Hà Nội rồi chỉ vài phút sau lại có một lần đăng nhập thành công được định vị ở một quốc gia cách hàng nghìn kilomet. Đây là dấu hiệu đáng điều tra. Tuy nhiên, vị trí từ IP thường chỉ là ước lượng: VPN, proxy, mạng di động, gateway doanh nghiệp và cơ sở dữ liệu định vị có thể làm vị trí hiển thị khác xa nơi người dùng thực sự ở. Vì vậy, **impossible travel là một risk signal, không phải bằng chứng chắc chắn rằng tài khoản đã bị chiếm**.

Bài học thuộc module **SECURITY_AUTHENTICATION_FUNDAMENTALS**, tập trung vào cách phát hiện, đánh giá và xử lý tín hiệu impossible travel trong risk-based authentication. Người học cần hiểu nguồn dữ liệu vị trí, cách so sánh thời gian và khoảng cách, giới hạn của IP geolocation, cách kết hợp nhiều tín hiệu và cách chọn hành động tương xứng mà không gây khóa nhầm tài khoản hợp lệ.

## 1. Kết quả học tập

Sau bài học, người học có thể:

1. Giải thích impossible travel và phân biệt nó với concurrent session, token replay và đăng nhập từ thiết bị mới.
2. Mô tả cách hệ thống suy ra vị trí gần đúng từ IP và các nguồn sai lệch thường gặp.
3. Chuẩn hóa sự kiện xác thực, thời gian, địa chỉ IP và ngữ cảnh thiết bị trước khi so sánh.
4. Ước lượng khoảng cách, thời gian di chuyển và mức độ bất thường mà không coi kết quả địa lý là tuyệt đối.
5. Thiết kế confidence, risk score và chính sách xử lý false positive.
6. Kết hợp impossible travel với MFA result, device posture, session history và tín hiệu compromise khác.
7. Chọn giữa allow, monitor, step-up, deny hoặc revoke dựa trên rủi ro và mức độ tin cậy của dữ liệu.
8. Bảo vệ quyền riêng tư, chống lạm dụng risk engine và xây dựng audit/test plan.

## 2. Impossible travel là gì?

Hệ thống quan sát các sự kiện liên quan tới một principal, ví dụ hai lần đăng nhập thành công:

- Sự kiện A: lúc 08:00 UTC, IP được định vị gần Thành phố Hồ Chí Minh;
- Sự kiện B: lúc 08:20 UTC, IP được định vị gần một thành phố cách đó hàng nghìn kilomet.

Nếu hai sự kiện thực sự đại diện cho cùng một người đang trực tiếp sử dụng hai thiết bị, khoảng cách và thời gian có thể không hợp lý. Hệ thống có thể gắn cờ sự kiện B để yêu cầu xác minh bổ sung.

### 2.1. Ý nghĩa của tín hiệu

Impossible travel có thể chỉ ra:

- Password bị lộ và được sử dụng từ một nơi khác;
- Session cookie hoặc refresh token bị đánh cắp;
- Attacker dùng proxy/VPN để che vị trí;
- Một tài khoản được chia sẻ cho nhiều người;
- Bot hoặc công cụ tự động sử dụng credential;
- Một lần đăng nhập hợp lệ đi qua egress network ở vị trí khác với người dùng.

Tín hiệu này giúp phát hiện bất thường trong chuỗi hoạt động. Nó không tự xác định ai là attacker, credential nào bị lộ hay người dùng có thực sự di chuyển hay không.

### 2.2. Vì sao gọi là “impossible”?

Tên gọi mô tả một phép so sánh đơn giản: khoảng cách suy ra giữa hai sự kiện lớn hơn quãng đường một người có thể di chuyển trong thời gian quan sát. Trong triển khai thực tế, hệ thống chỉ có **vị trí ước lượng và timestamp có sai số**. Do đó, kết quả nên được hiểu là “di chuyển có vẻ không hợp lý theo dữ liệu hiện có”, thay vì khẳng định một hành trình vật lý là bất khả thi.

## 3. Impossible travel khác những tín hiệu nào?

| Tín hiệu | Điều được quan sát | Khác biệt chính |
| --- | --- | --- |
| **Impossible travel** | Hai sự kiện cùng danh tính ở các vị trí IP khác xa trong thời gian ngắn | Ước lượng tính hợp lý của khoảng cách/thời gian |
| **Concurrent session** | Nhiều session cùng hoạt động | Không nhất thiết có vị trí bất thường |
| **New device** | Thiết bị hoặc browser context chưa thấy trước đó | Thiết bị mới có thể ở cùng vị trí |
| **Token replay** | Token/nonce/credential được dùng lại trái quy tắc | Có thể xảy ra từ cùng một IP |
| **Credential stuffing** | Nhiều lần thử credential trên nhiều account | Có thể không có lần đăng nhập thành công |
| **Unfamiliar network** | IP/ASN/network chưa từng thấy hoặc có rủi ro | Không cần hai vị trí để so sánh |
| **Impossible session overlap** | Hai hoạt động cùng session/token xảy ra đồng thời ở ngữ cảnh khác nhau | Có thể là dấu hiệu sao chép session |

Một hệ thống tốt có thể kết hợp các tín hiệu này, nhưng không nên đếm cùng một nguyên nhân nhiều lần như các bằng chứng độc lập. Ví dụ, “IP mới”, “quốc gia mới” và “impossible travel” có thể cùng bắt nguồn từ một VPN egress.

## 4. Nguồn vị trí và giới hạn của IP geolocation

Hầu hết hệ thống impossible travel dùng IP geolocation để suy ra vị trí gần đúng của địa chỉ IP quan sát được. Cơ sở dữ liệu có thể cung cấp quốc gia, vùng, thành phố, tọa độ ước lượng, ASN hoặc loại mạng.

### 4.1. IP không phải GPS

Địa chỉ IP thường xác định điểm ra mạng hoặc vùng đăng ký của nhà cung cấp, không xác định chính xác thiết bị hoặc con người. Tọa độ ở mức thành phố có thể lệch đáng kể; một số IP chỉ có thông tin quốc gia hoặc khu vực.

Không nên:

- Hiển thị tọa độ IP như vị trí GPS chính xác;
- Kết luận người dùng đang ở một địa chỉ cụ thể;
- Dùng IP geolocation làm bằng chứng duy nhất để khóa account;
- Thu thập vị trí GPS của thiết bị nếu mục đích chỉ cần đánh giá bất thường đăng nhập.

### 4.2. VPN, proxy và Tor

VPN/proxy có thể làm địa chỉ IP hiển thị thuộc quốc gia khác với nơi người dùng đang ở. Một người làm việc từ Việt Nam có thể dùng VPN công ty với egress tại Singapore hoặc Hoa Kỳ. Tor exit node có thể ở nơi hoàn toàn khác.

Phát hiện VPN/proxy có thể là một tín hiệu bổ sung, nhưng không chứng minh hành vi độc hại. Nhiều tổ chức bắt buộc VPN để truy cập nội bộ; policy cần nhận diện network egress đã được tổ chức phê duyệt.

### 4.3. Mạng di động và CGNAT

Nhà mạng di động có thể thay IP khi thiết bị đổi cell, chuyển Wi-Fi/mobile hoặc roaming. Carrier-grade NAT (CGNAT) khiến nhiều thuê bao cùng chia sẻ địa chỉ IP public. Geolocation của IP nhà mạng có thể trỏ tới trung tâm mạng ở thành phố khác.

Vì vậy, một IP mới không nhất thiết là một thiết bị mới, và một vị trí mới không nhất thiết là người dùng đã di chuyển.

### 4.4. Địa chỉ IP doanh nghiệp và cloud

Gateway tập trung, secure web gateway, cloud egress và remote desktop có thể khiến nhiều nhân viên xuất hiện từ cùng một IP hoặc vùng địa lý. Một IP cloud/datacenter mới cũng có thể là dấu hiệu tự động hóa, nhưng cần xét loại workload và kiến trúc tổ chức.

### 4.5. Chất lượng dữ liệu địa lý

Mỗi kết quả geolocation nên có nguồn, phiên bản dữ liệu, độ chính xác hoặc confidence nếu provider cung cấp. Dữ liệu có thể cũ, thiếu hoặc không đồng nhất giữa các nhà cung cấp. Nếu chỉ có country-level location, không nên tính tốc độ di chuyển bằng tọa độ thành phố giả định.

## 5. Chọn đúng sự kiện để so sánh

Impossible travel cần các sự kiện có ý nghĩa và thời gian đáng tin. Không phải mọi request HTTP đều đại diện cho người dùng đang ở vị trí đó.

### 5.1. Sự kiện phù hợp

Có thể sử dụng:

- Đăng nhập tương tác thành công;
- Hoàn tất MFA hoặc reauthentication;
- Tạo session mới;
- Đăng nhập qua IdP/SSO thành công;
- Một sự kiện xác thực mạnh có liên kết rõ với principal.

### 5.2. Sự kiện cần thận trọng

- Refresh access token tự động;
- Background sync;
- API request từ backend hoặc mobile push service;
- WebSocket reconnect;
- Request đi qua proxy hoặc service mesh;
- Event được ingest trễ hoặc replay từ hàng đợi.

Refresh token có thể được sử dụng từ một backend hoặc egress khác mà không có người dùng di chuyển. Không coi mỗi lần refresh token là một lần đăng nhập mới.

### 5.3. Ưu tiên event time

Mỗi event nên có:

- **event_time:** thời điểm hoạt động xác thực thực sự xảy ra;
- **ingested_at:** thời điểm hệ thống nhận event;
- **source_time_quality:** độ tin cậy của đồng hồ nguồn;
- **correlation_id:** định danh giao dịch;
- **principal_id:** subject đã được xác minh;
- **session_id/reference:** session liên quan nếu có.

So sánh theo event_time đã chuẩn hóa UTC, không dùng thời điểm event tới hàng đợi nếu có thể bị trễ. Nếu timestamp sai, ở tương lai hoặc lệch quá nhiều, hạ confidence hoặc bỏ qua phép tính.

## 6. Chuẩn hóa IP và trust boundary

Trước khi định vị IP, phải xác định địa chỉ nào thực sự đại diện cho client.

### 6.1. Reverse proxy và forwarded headers

Ứng dụng phía sau load balancer có thể nhận:

- Địa chỉ socket của proxy;
- Forwarded header do proxy thêm;
- Header do client bên ngoài tự gửi.

Chỉ tin forwarded header từ proxy/load balancer nằm trong trust configuration. Proxy tin cậy phải loại bỏ hoặc ghi đè header do client tự cung cấp trước khi thêm giá trị của nó. Không lấy phần tử đầu tiên của X-Forwarded-For một cách mù quáng.

### 6.2. Chuẩn hóa địa chỉ

- Parse IPv4/IPv6 bằng thư viện chuẩn;
- Chuẩn hóa IPv4-mapped IPv6 nếu hệ thống quy định;
- Loại bỏ giá trị malformed;
- Nhận diện private, loopback, link-local và reserved address;
- Không định vị private IP như một địa chỉ Internet công khai;
- Ghi lại nguồn IP và proxy chain theo chính sách bảo vệ dữ liệu.

### 6.3. Không nhầm IP với danh tính thiết bị

IP là thuộc tính mạng có thể chia sẻ hoặc thay đổi. Không dùng IP làm khóa duy nhất của thiết bị hoặc principal. Hãy kết hợp session, credential, device registration và các tín hiệu khác có nguồn đáng tin.

## 7. Tính khoảng cách và thời gian

Một phép tính cơ bản so sánh khoảng cách địa lý giữa hai tọa độ ước lượng với thời gian giữa hai sự kiện.

### 7.1. Khoảng cách đường chim bay

Có thể dùng công thức Haversine để ước lượng khoảng cách trên bề mặt Trái Đất giữa hai điểm latitude/longitude:

~~~text
function haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    phi1 = radians(lat1)
    phi2 = radians(lat2)
    d_phi = radians(lat2 - lat1)
    d_lambda = radians(lon2 - lon1)

    a = sin(d_phi / 2)^2
      + cos(phi1) * cos(phi2) * sin(d_lambda / 2)^2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    return R * c
~~~

Đây là khoảng cách đường chim bay, không phải tuyến đường thực tế hoặc thời gian di chuyển. Nếu hai vị trí chỉ được biết ở mức quốc gia, không nên giả định tọa độ thành phố để tạo kết quả có vẻ chính xác.

### 7.2. Khoảng thời gian

Đặt:

- \(t_1\): event time của lần xác thực trước;
- \(t_2\): event time của lần xác thực sau;
- \(\Delta t = t_2 - t_1\): thời gian tính bằng giờ;
- \(d\): khoảng cách ước lượng tính bằng kilomet.

Tốc độ trung bình tối thiểu theo đường chim bay là:

\[
v = \frac{d}{\Delta t}
\]

Nếu \(\Delta t\) không dương hoặc timestamp không đáng tin, không tính tốc độ. Hai event xảy ra gần như đồng thời có thể là concurrent session hoặc token reuse; cần đánh giá theo một detector khác.

### 7.3. Tính đến độ bất định vị trí

Nếu provider đưa ra bán kính sai số \(r_1\) và \(r_2\), có thể ước lượng khoảng cách thấp nhất:

\[
d_{\min} = \max(0,\ d-r_1-r_2)
\]

Sau đó tính tốc độ tối thiểu \(v_{\min}=d_{\min}/\Delta t\). Cách này thận trọng hơn việc dùng tọa độ như chính xác tuyệt đối. Nếu không có độ chính xác đáng tin, hãy hạ confidence thay vì tự gán một bán kính tùy ý.

### 7.4. Không có một ngưỡng tốc độ phổ quát

Không có một con số duy nhất phù hợp mọi loại tài khoản, mạng và vùng địa lý. Người dùng có thể đi máy bay, nhưng IP có thể phản ánh VPN chứ không phải điểm đến; khoảng cách giữa hai thành phố cũng không cho biết người dùng đi bằng phương tiện nào.

Ngưỡng nên được hiệu chỉnh dựa trên:

- Độ chính xác geolocation;
- Thời gian event và sai số đồng hồ;
- Loại network/ASN và VPN đã biết;
- Loại principal (con người, service account, workload);
- Lịch sử hành vi hợp lệ;
- Mức nhạy cảm của hành động tiếp theo.

## 8. Mô hình phát hiện cơ bản

Một detector đơn giản có thể so sánh event xác thực mới với một hoặc nhiều event gần nhất của cùng principal.

~~~mermaid
flowchart TD
    A["Nhận authentication event"] --> B["Xác minh principal và event type"]
    B --> C["Lấy client IP từ trust boundary"]
    C --> D["Chuẩn hóa IP và tra geolocation"]
    D --> E["Kiểm tra chất lượng timestamp/location"]
    E --> F["Lấy các event trước của principal"]
    F --> G["So sánh thời gian, khoảng cách và context"]
    G --> H{"Có bất thường đáng tin?"}
    H -->|"Không"| I["Cập nhật baseline / allow"]
    H -->|"Có"| J["Tạo impossible-travel signal"]
    J --> K["Kết hợp các risk signal khác"]
    K --> L["Policy: allow / monitor / step-up / deny"]
    L --> M["Audit, notify hoặc incident workflow"]
~~~

### 8.1. Cặp event nào nên so sánh?

Chỉ so sánh event thuộc cùng principal đã được xác minh và có loại sự kiện tương thích. Có thể ưu tiên:

- Hai login thành công;
- Login mới với event xác thực gần nhất;
- Hai session mới có cùng subject;
- Một login mới với một sự kiện reauthentication mạnh.

Không so sánh event của hai account chỉ vì cùng email hiển thị. Với account federation, subject phải được xác định theo issuer + subject hoặc identity mapping đã xác minh.

### 8.2. Cửa sổ quan sát

Chỉ so sánh event trong cửa sổ phù hợp để tránh liên kết những lần đăng nhập cách nhau quá xa. Cửa sổ cần đủ để phát hiện bất thường nhưng không giữ lịch sử vị trí lâu hơn cần thiết. Có thể ưu tiên vài event gần nhất thay vì lưu toàn bộ lịch sử.

### 8.3. Nhiều event và baseline

Một event đơn lẻ có thể là outlier. Nhiều event liên tiếp từ cùng một VPN egress có thể cho thấy một network pattern hợp lệ. Detector có thể duy trì baseline quốc gia/ASN/thiết bị ở mức tổng quát, nhưng không nên để baseline tự học một chuỗi hoạt động độc hại rồi coi nó là bình thường.

Baseline cần:

- Thời gian tồn tại và cơ chế hết hạn;
- Nguồn dữ liệu có chất lượng;
- Không tự học từ event đang bị đánh dấu rủi ro cao;
- Có thể reset sau compromise/recovery;
- Không biến vị trí thành thuộc tính danh tính cố định.

## 9. Confidence và chất lượng bằng chứng

Không phải kết quả impossible travel nào cũng có cùng độ tin cậy. Risk engine nên tách **mức bất thường** khỏi **độ tin cậy của dữ liệu**.

### 9.1. Các yếu tố làm tăng confidence

- Cả hai event đều là login tương tác thành công;
- Timestamp từ nguồn đáng tin và đồng hồ đồng bộ;
- IP public được quan sát trực tiếp tại edge đáng tin cậy;
- Geolocation có độ chính xác tốt và nguồn dữ liệu mới;
- Khoảng cách thấp nhất vẫn rất lớn so với thời gian;
- Hai session có dấu hiệu hoạt động chồng lấn;
- Device context khác biệt đáng kể;
- Có thêm tín hiệu credential compromise hoặc MFA bất thường.

### 9.2. Các yếu tố làm giảm confidence

- Một event chỉ là token refresh hoặc background job;
- IP thuộc VPN/proxy/corporate egress đã biết;
- IP thuộc mạng di động hoặc CGNAT;
- Chỉ có country-level geolocation;
- Timestamp đến trễ hoặc không đáng tin;
- Hai event dùng cùng thiết bị/session nhưng egress thay đổi;
- Provider geolocation có độ chính xác thấp;
- Hệ thống vừa thay đổi proxy/network architecture.

### 9.3. Tách anomaly score và confidence

Một thiết kế có thể lưu:

- **anomaly_score:** mức độ bất thường của cặp event;
- **evidence_confidence:** độ tin cậy của vị trí và thời gian;
- **corroborating_signals:** các tín hiệu độc lập hỗ trợ;
- **decision:** kết quả policy.

Không nên cộng nhiều signal tương quan như “quốc gia mới”, “ASN mới” và “IP mới” thành ba bằng chứng độc lập nếu tất cả xuất phát từ một lần chuyển VPN.

## 10. False positive và các tình huống hợp lệ

False positive là phần không thể loại bỏ hoàn toàn vì vị trí IP có sai số. Cần nhận diện các trường hợp phổ biến:

| Tình huống | Vì sao tạo tín hiệu | Cách xử lý |
| --- | --- | --- |
| VPN cá nhân | IP egress ở quốc gia khác | Kết hợp VPN signal, session/device và lịch sử |
| VPN doanh nghiệp | Egress tập trung ở một vùng | Duy trì danh sách network tổ chức đã xác minh |
| Mobile roaming | IP thay đổi khi chuyển mạng/quốc gia | Hạ confidence nếu event/context phù hợp |
| Carrier NAT | Nhiều người dùng chung IP | Không suy ra danh tính từ IP |
| Cloud browser/VDI | Client egress nằm ở data center | Dùng device/workspace context đã đăng ký |
| Secure web gateway | Nhiều địa điểm đi ra từ một gateway | Nhận diện gateway theo tenant/network policy |
| Geolocation database sai | Tọa độ hoặc thành phố bị gán nhầm | So sánh provider/accuracy, không hard-block |
| Event ingestion trễ | Thời điểm nhận khác thời điểm xảy ra | Dùng event_time và kiểm tra timestamp quality |
| Đồng hồ thiết bị sai | Event time không chính xác | Dùng server-side timestamp phù hợp |
| User chủ động di chuyển | Người dùng đi máy bay hoặc qua biên giới | Xét thời gian, context và xác thực bổ sung |

### 10.1. Allowlist network có kiểm soát

Tổ chức có thể đăng ký VPN egress hoặc secure gateway đã xác minh. Allowlist cần owner, tenant scope, ngày hết hạn và audit. Không allowlist toàn bộ ASN hoặc quốc gia chỉ vì một số người dùng hợp lệ sử dụng mạng đó.

### 10.2. Người dùng đang đi du lịch

Nếu người dùng báo trước chuyến đi, hệ thống có thể ghi nhận travel context trong thời hạn nhất định sau khi xác minh account. Không nên cho người dùng tự tắt toàn bộ risk detection vô thời hạn. Travel context chỉ làm thay đổi cách diễn giải signal; nó không miễn trừ MFA, session checks hoặc authorization.

## 11. Kết hợp với các tín hiệu rủi ro khác

Impossible travel mạnh hơn khi được củng cố bởi các tín hiệu độc lập.

Ví dụ:

- Device chưa từng thấy và chưa được quản lý;
- MFA bị từ chối nhiều lần hoặc có push fatigue;
- Password vừa được reset từ nguồn bất thường;
- Refresh token reuse hoặc session cookie được dùng song song;
- ASN/datacenter/proxy có rủi ro cao;
- Nhiều account đăng nhập từ cùng một IP theo pattern bot;
- Thao tác sau login có hành vi bất thường;
- Account vừa thay đổi recovery channel hoặc thêm authenticator.

### 11.1. Ví dụ kết hợp

Một login từ vị trí xa có confidence thấp vì IP thuộc VPN công ty. Nếu device đã đăng ký, passkey xác minh thành công và network nằm trong allowlist, hệ thống có thể cho phép nhưng ghi nhận context.

Ngược lại, nếu vị trí xa có confidence cao, device mới, password-only login và sau đó là yêu cầu xuất dữ liệu lớn, policy có thể yêu cầu phishing-resistant step-up hoặc chặn giao dịch.

### 11.2. Không đếm trùng bằng chứng

Risk engine nên nhóm signal theo nguyên nhân:

- Network/location;
- Credential/authentication;
- Device/session;
- Behavior/resource;
- Account lifecycle.

Điều này giảm việc một thay đổi VPN làm score tăng quá mức vì nhiều field liên quan cùng thay đổi.

## 12. Chọn hành động theo mức rủi ro

Impossible travel không nên luôn dẫn tới khóa account. Hành động phụ thuộc confidence, anomaly severity, mức nhạy cảm của request và khả năng xác minh bổ sung.

| Mức đánh giá | Ví dụ | Hành động có thể áp dụng |
| --- | --- | --- |
| **Thông tin yếu** | IP mới, geolocation không chính xác | Ghi nhận, không làm gián đoạn |
| **Bất thường vừa** | Hai vị trí khác xa, nhưng có VPN/network giải thích được | Monitor, tăng logging hoặc step-up khi action nhạy cảm |
| **Rủi ro cao** | Login xa với confidence cao, device mới, credential yếu | Yêu cầu MFA/passkey phù hợp, hạn chế action nhạy cảm |
| **Rủi ro rất cao** | Impossible travel cộng refresh-token reuse hoặc dấu hiệu session hijack | Từ chối request, revoke session/token liên quan và yêu cầu recovery nếu cần |

### 12.1. Allow

Cho phép request khi signal yếu hoặc có giải thích đáng tin, nhưng vẫn ghi nhận theo retention policy. Allow không có nghĩa xóa lịch sử hoặc vô hiệu hóa detector.

### 12.2. Monitor

Ghi event, tăng quan sát hoặc gửi cảnh báo nội bộ mà chưa yêu cầu người dùng thao tác. Phù hợp khi confidence thấp hoặc action có rủi ro thấp.

### 12.3. Step-up

Yêu cầu phương thức phù hợp với mức rủi ro: passkey/WebAuthn với user verification, security key hoặc MFA đã được policy chấp nhận. Không mặc định SMS OTP là đủ cho mọi tình huống. Kết quả step-up cần gắn với đúng session và action.

### 12.4. Deny hoặc revoke

Nếu có nhiều bằng chứng độc lập về compromise, từ chối hành động và thu hồi session/token liên quan. Không nhất thiết khóa vĩnh viễn toàn bộ account; có thể yêu cầu recovery hoặc support verification. Cần tránh tạo điều kiện cho attacker cố ý kích hoạt detector để khóa tài khoản nạn nhân.

## 13. Quy trình xử lý khi phát hiện impossible travel

Một flow xử lý có thể:

1. Nhận event xác thực mới và xác minh principal.
2. Chuẩn hóa IP từ trust boundary.
3. Tra vị trí và chất lượng geolocation.
4. So sánh với event trước phù hợp.
5. Tính anomaly score và confidence.
6. Kết hợp device, network, MFA, session và behavior signals.
7. Đánh giá policy theo action hiện tại.
8. Allow, monitor, step-up hoặc deny.
9. Ghi audit event đã giảm thiểu dữ liệu.
10. Thông báo người dùng khi cần và cung cấp đường xử lý nếu họ không nhận ra hoạt động.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant A as Authentication service
    participant R as Risk engine
    participant G as GeoIP provider
    participant P as Policy engine
    participant U as User
    C->>A: Login thành công
    A->>R: Gửi event xác thực và context
    R->>G: Tra IP geolocation
    G-->>R: Vị trí ước lượng + confidence
    R->>R: So với event trước của principal
    R->>P: Impossible-travel signal + các signal khác
    P-->>A: ALLOW / MONITOR / STEP_UP / DENY
    alt Step-up
        A->>U: Yêu cầu phương thức xác thực phù hợp
        U->>A: Bằng chứng xác thực
        A->>P: Kết quả step-up và action context
    else Deny
        A->>U: Từ chối và hướng dẫn bảo vệ account
    end
~~~

## 14. Bảo vệ người dùng và tránh tạo cơ hội DoS

Nếu bất kỳ ai có thể gửi request từ IP khác để kích hoạt impossible travel, chính sách khóa account tự động có thể bị lạm dụng nhằm gây từ chối dịch vụ.

### 14.1. Không khóa account chỉ từ một cặp IP

Một signal đơn lẻ thường nên dẫn tới monitor hoặc step-up, trừ khi có policy đặc biệt và bằng chứng mạnh. Account lock cần dựa trên nhiều tín hiệu, giới hạn thử và cơ chế mở khóa an toàn.

### 14.2. Thông báo an toàn

Thông báo cho người dùng nên nêu:

- Có hoạt động đăng nhập bất thường được phát hiện;
- Thời điểm gần đúng và thiết bị/network ở mức thông tin phù hợp;
- Hành động nào đã được thực hiện (ví dụ yêu cầu xác thực lại);
- Cách báo cáo nếu họ không nhận ra hoạt động;
- Cách đổi credential/thu hồi session qua kênh chính thức.

Không gửi raw IP, tọa độ chính xác hoặc dữ liệu định vị vượt quá nhu cầu. Không đưa link đăng nhập có thể bị giả mạo; hướng người dùng tự mở ứng dụng hoặc domain chính thức.

### 14.3. Helpdesk và recovery

Nhân viên hỗ trợ không nên bỏ qua risk flag chỉ vì người gọi biết tên, email hoặc một vài thông tin công khai. Recovery cần kiểm tra độc lập, audit và thu hồi session/credential nếu có dấu hiệu compromise.

## 15. Quyền riêng tư và quản trị dữ liệu vị trí

Dữ liệu IP và vị trí có thể tiết lộ nơi làm việc, thói quen và hành trình của người dùng. Risk engine cần thu thập ít nhất đủ để phát hiện rủi ro.

### 15.1. Data minimization

- Chỉ dùng IP và geolocation cho mục đích bảo mật đã công bố;
- Ưu tiên lưu country/region hoặc vùng ước lượng thay vì tọa độ chi tiết nếu đủ;
- Tách dữ liệu điều tra chi tiết khỏi log ứng dụng thông thường;
- Không lưu lịch sử vị trí vô thời hạn;
- Giới hạn quyền truy cập risk event và audit;
- Có retention, deletion và access review rõ ràng.

### 15.2. Pseudonymization

Dùng subject reference nội bộ hoặc mã giả thay cho email/tên trong pipeline risk. Chỉ dịch vụ cần thiết mới được ánh xạ về danh tính thật. Không đưa IP và subject trực tiếp vào dashboard rộng nếu không cần.

### 15.3. Giải thích và kiểm soát

Tổ chức cần giải thích mục đích dùng network/location signal, thời gian lưu và cách xử lý false positive. Người dùng cần kênh báo cáo sự kiện không nhận ra và yêu cầu hỗ trợ mà không phải cung cấp thêm dữ liệu quá mức.

## 16. Thiết kế dữ liệu và audit event

Một event có thể chứa các trường sau, tùy nhu cầu và chính sách:

~~~json
{
  "event_id": "evt_01JQ8M7K",
  "principal_ref": "usr_ref_417",
  "event_type": "interactive_login_success",
  "event_time": "2026-11-22T08:00:00Z",
  "ingested_at": "2026-11-22T08:00:02Z",
  "session_ref": "sess_ref_82a",
  "client_ip_ref": "ip_ref_91d",
  "network": {
    "asn": 64520,
    "network_type": "corporate_egress"
  },
  "geo": {
    "country_code": "VN",
    "region": "HCMC",
    "latitude_approx": 10.8,
    "longitude_approx": 106.7,
    "accuracy_km": 80,
    "provider": "example_geo_db"
  },
  "device_ref": "device_ref_22",
  "auth_method": "passkey",
  "outcome": "success"
}
~~~

Đây là cấu trúc minh họa; không phải schema bắt buộc. Không cần lưu tọa độ nếu policy chỉ cần country/region. IP thật nên được bảo vệ hoặc thay bằng reference/pseudonym khi có thể.

### 16.1. Event phát hiện

Risk event có thể lưu:

- Event IDs được so sánh;
- Khoảng thời gian và khoảng cách ước lượng;
- Confidence và anomaly score;
- Geolocation provider/version;
- Network/VPN context;
- Các signal corroborating;
- Policy version và quyết định;
- Actor/service đã xử lý và thời điểm.

Không cần sao chép toàn bộ raw login payload vào risk event. Dùng reference tới nguồn audit có quyền truy cập giới hạn.

## 17. Pseudocode detector tham khảo

~~~text
evaluate_impossible_travel(current_event):
    require current_event.principal_is_verified
    require current_event.type in INTERACTIVE_AUTH_EVENTS
    require current_event.outcome == SUCCESS
    require current_event.event_time_is_trustworthy

    client_ip = resolve_client_ip_from_trusted_proxy_chain(current_event)
    if client_ip is missing or client_ip is private_or_invalid:
        return INSUFFICIENT_LOCATION_EVIDENCE

    current_geo = lookup_geo_with_quality(client_ip)
    if current_geo is missing:
        return INSUFFICIENT_LOCATION_EVIDENCE

    previous = load_recent_compatible_auth_event(
        principal = current_event.principal,
        before = current_event.event_time,
        within = configured_observation_window
    )
    if previous is missing:
        store_event(current_event)
        return NO_COMPARABLE_EVENT

    if not previous.event_time_is_trustworthy:
        return LOW_CONFIDENCE

    delta_hours = hours_between(
        previous.event_time,
        current_event.event_time
    )
    if delta_hours <= configured_minimum_delta:
        return EVALUATE_CONCURRENT_SESSION_SEPARATELY

    previous_geo = lookup_geo_with_quality(previous.client_ip)
    if previous_geo is missing:
        return INSUFFICIENT_LOCATION_EVIDENCE

    distance = haversine(previous_geo.point, current_geo.point)
    min_distance = adjust_for_accuracy_if_available(
        distance,
        previous_geo.accuracy,
        current_geo.accuracy
    )

    anomaly = compare_minimum_travel_speed_and_context(
        min_distance,
        delta_hours,
        network_context,
        principal_type
    )
    confidence = assess_event_time_and_geo_quality(
        previous,
        current_event,
        previous_geo,
        current_geo
    )

    signals = collect_independent_risk_signals(current_event)
    decision = policy_engine.evaluate(
        anomaly,
        confidence,
        signals,
        requested_action
    )

    store_minimized_risk_event(decision)
    return decision
~~~

Pseudocode mô tả logic, không phải implementation dùng trực tiếp. Cần xử lý event đến sai thứ tự, deduplication, clock skew, nhiều session, geolocation cache, network allowlist có thời hạn, data retention và các loại principal khác nhau.

## 18. Những tình huống cần xử lý riêng

### 18.1. Hai login gần như đồng thời

Nếu hai event có timestamp gần bằng nhau nhưng ở hai vị trí xa, không nên tính tốc độ bằng cách chia cho một khoảng thời gian gần 0. Đây có thể là concurrent session, session sharing hoặc token hijack. Chuyển sang phân tích overlap, session ID, device context và credential result.

### 18.2. Một event cũ đến muộn

Event có thể tới risk engine sau event mới hơn do queue hoặc retry. Sắp xếp theo event_time và xử lý late arrival; không coi thứ tự ingest là thứ tự di chuyển. Có thể đánh giá lại cặp event nhưng phải tránh phát nhiều alert trùng.

### 18.3. Một tài khoản dùng chung

Tài khoản tổ chức có thể được nhiều người dùng từ nhiều địa điểm. Impossible travel có thể phát hiện việc chia sẻ, nhưng giải pháp thường là cấp danh tính riêng, service identity hoặc delegated access; không nên chỉ nới ngưỡng để che giấu mô hình account sharing.

### 18.4. Service account và workload

Workload có thể chạy ở nhiều region hoặc thay đổi egress theo autoscaling. Không áp dụng ngưỡng di chuyển của con người cho workload. Dùng workload identity, expected region/network, deployment metadata và service-specific policy.

### 18.5. Người dùng sau recovery

Sau khi account được khôi phục, baseline cũ có thể không còn đáng tin hoặc có thể bị attacker làm nhiễm. Tăng giám sát trong khoảng thời gian hợp lý, xác minh credential/session, và chỉ học baseline mới từ event đạt confidence.

## 19. Kiểm thử impossible travel

Test trong môi trường được phép với IP giả lập, dữ liệu geolocation mẫu và event synthetic. Không dùng dữ liệu vị trí cá nhân thật nếu không cần thiết.

| Nhóm | Tình huống | Kết quả mong đợi |
| --- | --- | --- |
| Baseline | Hai login hợp lệ ở cùng vùng, cách nhau hợp lý | Không tạo high-risk signal |
| Large distance | Hai login ở hai vùng rất xa trong thời gian ngắn, dữ liệu tốt | Tạo anomaly signal với confidence phù hợp |
| VPN | Một event đi qua VPN egress đã biết | Hạ confidence hoặc áp dụng network policy |
| Corporate gateway | Nhiều user cùng xuất hiện từ một egress | Không coi họ là cùng thiết bị/danh tính |
| Mobile network | IP đổi khi chuyển Wi-Fi/mobile | Không tự động khóa account |
| Low accuracy | Geolocation chỉ có country-level hoặc sai số lớn | Không tính tốc độ chính xác giả |
| Private IP | Event chỉ có private/loopback IP | Không định vị Internet; đánh dấu thiếu bằng chứng |
| Forwarded header spoof | Client tự gửi X-Forwarded-For giả | Proxy trust boundary loại bỏ giá trị không tin cậy |
| Clock skew | Event timestamp lệch hoặc ở tương lai | Hạ confidence hoặc bỏ phép so sánh |
| Late arrival | Event cũ được ingest sau event mới | Sắp xếp theo event_time, deduplicate |
| Token refresh | Refresh token qua egress khác | Không mặc định coi là người dùng di chuyển |
| Concurrent events | Hai login gần như đồng thời ở hai vùng | Chuyển sang detector concurrent/session overlap |
| Same session | Cùng session xuất hiện ở hai IP | Kiểm tra session hijack/replay và device context |
| New device | Vị trí xa và thiết bị mới | Kết hợp signal, trigger theo policy |
| MFA success | Passkey UV thành công tại event mới | Giảm một số rủi ro nhưng không xóa mọi signal |
| MFA fatigue | Nhiều push bị từ chối rồi một lần được chấp thuận | Tăng risk; kiểm tra number matching và user report |
| Service account | Workload chạy đa region | Áp dụng policy workload riêng |
| Account sharing | Nhiều thiết bị/địa điểm hợp lệ theo mô hình tổ chức | Dùng identity riêng/delegation thay vì nới vô hạn |
| DoS attempt | Attacker cố tạo signal để khóa nạn nhân | Không hard-lock chỉ từ một signal IP |
| Recovery | Account vừa khôi phục và đăng nhập từ vị trí mới | Áp dụng recovery policy và giám sát tăng cường |
| Privacy | Dashboard/log hiển thị risk event | Chỉ lộ dữ liệu vị trí tối thiểu cho người có quyền |

### 19.1. Kiểm tra bất biến

- Không dùng IP geolocation như GPS chính xác;
- Không kết luận compromise chỉ từ một cặp IP;
- Không dùng token refresh/background request làm login event nếu không có lý do;
- Không tin forwarded header từ client không được xác thực;
- Timestamp và vị trí thiếu chất lượng không tạo high-confidence alert;
- Không hard-lock account chỉ vì một risk signal có thể bị attacker kích hoạt;
- Step-up và authorization được thực thi server-side;
- Raw IP và vị trí chỉ được lưu/truy cập theo retention và privacy policy.

## 20. Những lỗi triển khai thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Coi IP location là vị trí chính xác | Báo sai người dùng đang ở đâu | Lưu accuracy/confidence, dùng mô tả gần đúng |
| Dùng ingest time thay event time | Tạo hành trình giả do queue delay | Chuẩn hóa event timestamp UTC |
| So sánh mọi HTTP request | Background traffic tạo false positive | Chọn event xác thực phù hợp |
| Tin X-Forwarded-For tùy ý | Attacker giả IP và kích hoạt/bypass detector | Trust proxy chain |
| Dùng một ngưỡng tốc độ cho mọi người | Sai lệch theo network, loại account và vùng | Hiệu chỉnh theo dữ liệu và risk policy |
| Tự động khóa account từ một signal | DoS và false positive | Step-up/monitor, cần corroboration cho revoke |
| Bỏ qua VPN/corporate egress | Người dùng hợp lệ bị chặn | Network context có owner và expiry |
| Coi refresh token là login mới | Backend egress bị hiểu là vị trí user | Phân biệt event type |
| Dùng email làm principal key | Gộp nhầm identity | Dùng subject nội bộ đã xác minh |
| Không xử lý late event | Alert trùng hoặc sai thứ tự | Event-time ordering và deduplication |
| Lưu lịch sử vị trí vô thời hạn | Rủi ro quyền riêng tư | Data minimization và retention |
| Dùng chung policy cho workload và người | Alert liên tục ở cloud service | Principal-type-specific policy |
| Cho risk score ghi đè action policy | Hành động nhạy cảm được phép quá dễ | Assurance bắt buộc theo action |

## 21. Checklist production

1. **Event semantics:** Chỉ so sánh event xác thực có ý nghĩa; phân biệt login, reauth, refresh và background activity?
2. **Principal binding:** Event được gắn với subject đã xác minh, không chỉ email?
3. **IP trust:** Client IP lấy từ socket/proxy chain đáng tin; forwarded header giả bị loại?
4. **Geo quality:** Có provider, version, accuracy/confidence và loại network?
5. **Time quality:** Event time UTC, clock skew, late arrival và deduplication được xử lý?
6. **Distance model:** Dùng khoảng cách ước lượng, tính đến uncertainty và không giả vờ chính xác?
7. **Thresholds:** Ngưỡng được hiệu chỉnh theo loại principal, network và risk; có owner?
8. **Confidence:** Tách anomaly severity khỏi độ tin cậy bằng chứng?
9. **Corroboration:** Kết hợp device, MFA, session, token reuse và behavior mà không đếm trùng?
10. **Actions:** Allow/monitor/step-up/deny/revoke có tiêu chí và escalation rõ?
11. **DoS resistance:** Một signal không dễ khóa account nạn nhân?
12. **Session controls:** Có thể revoke session/token liên quan và kiểm tra authorization hiện tại?
13. **User communication:** Thông báo an toàn, không lộ tọa độ/IP quá mức và có kênh báo cáo?
14. **Privacy:** Data minimization, pseudonymization, access control và retention được xác định?
15. **Operations:** Có metric false positive, alert volume, geolocation drift và provider outage?
16. **Testing:** Có test VPN, mobile, proxy spoof, clock skew, late event, concurrent session và workload?

## 22. Bài tập tình huống

Một nền tảng học tập phát hiện tài khoản giảng viên đăng nhập lúc 08:00 từ Thành phố Hồ Chí Minh và lúc 08:15 từ một IP được định vị ở châu Âu. Hệ thống lập tức khóa account trong 24 giờ. Sau điều tra, người dùng cho biết họ đang ở Việt Nam và laptop được cấu hình VPN doanh nghiệp với egress ở châu Âu. Cùng thời điểm đó, mobile app tự refresh token qua mạng di động.

**Yêu cầu:**

1. Xác định ít nhất **tám nguyên nhân** có thể làm tín hiệu impossible travel sai hoặc thiếu confidence.
2. Phân biệt event login tương tác, refresh token và network egress.
3. Thiết kế lại pipeline IP trust, geolocation, event-time và distance calculation.
4. Đề xuất cách đưa VPN doanh nghiệp vào network context có kiểm soát.
5. Xây dựng policy chọn monitor, step-up hoặc deny thay vì khóa cứng từ một signal.
6. Xác định các tín hiệu bổ sung cần kiểm tra trước khi revoke session.
7. Viết test cho VPN egress, mobile IP change, spoofed forwarded header và event đến trễ.

**Gợi ý đối chiếu:** IP không phải GPS; VPN egress khác vị trí người dùng; refresh token không phải login mới; dùng event_time và trusted proxy chain; tách confidence/anomaly; kết hợp device/MFA/session signals; không hard-lock account chỉ từ một cặp IP.

## 23. Ghi nhớ

- **Impossible travel** là tín hiệu bất thường khi hai sự kiện xác thực của cùng principal có vị trí IP ước lượng cách xa nhau trong khoảng thời gian ngắn.
- IP geolocation chỉ gần đúng; VPN, proxy, mobile network, CGNAT và corporate egress tạo false positive.
- Chọn đúng authentication event, dùng event_time UTC và lấy client IP từ proxy chain được tin cậy.
- Khoảng cách/tốc độ chỉ là ước lượng; cần tính đến accuracy, clock skew và loại principal. Không có một ngưỡng phổ quát.
- Tách anomaly score khỏi confidence; kết hợp device, MFA, session, token reuse và behavior signals độc lập.
- Chọn allow, monitor, step-up, deny hoặc revoke theo risk policy. Một signal đơn lẻ không nên tự động khóa account.
- Bảo vệ quyền riêng tư bằng data minimization, pseudonymization, access control và retention có giới hạn.

Impossible travel hữu ích khi được dùng như **một tín hiệu trong quyết định xác thực dựa trên rủi ro**. Hệ thống cần biết dữ liệu vị trí đáng tin đến đâu, điều gì có thể giải thích sự khác biệt và hành động nào tương xứng; mục tiêu là phát hiện truy cập đáng ngờ mà vẫn cho phép người dùng hợp lệ làm việc qua mạng di động, VPN và hạ tầng doanh nghiệp.
