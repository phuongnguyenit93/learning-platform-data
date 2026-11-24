# Yếu tố vị trí trong xác thực

> **Chương:** Authentication factor  
> **Phạm vi:** Trong module **SECURITY_AUTHENTICATION_FUNDAMENTALS**, người học tìm hiểu credential, mật khẩu, MFA, passkey, chứng chỉ, token, phiên, liên kết danh tính và khôi phục tài khoản. Bài này tập trung vào **vị trí** như một nguồn thông tin giúp đánh giá bối cảnh, rủi ro và điều kiện truy cập trong luồng xác thực an toàn.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

1. Giải thích cách vị trí được dùng trong bảo mật đăng nhập và lý do **vị trí địa lý tự nó không phải một yếu tố MFA độc lập** theo cách phân loại phổ biến.
2. Phân biệt dữ liệu vị trí suy ra từ IP với vị trí do thiết bị báo cáo, tín hiệu mạng cục bộ và bằng chứng hiện diện gần một thiết bị.
3. Mô tả các ranh giới tin cậy khi thu thập IP, GPS, Wi-Fi, Bluetooth hoặc dữ liệu từ một proxy/gateway.
4. Thiết kế đánh giá rủi ro theo ngữ cảnh, chẳng hạn phát hiện đăng nhập ở nơi bất thường, *impossible travel* và yêu cầu xác thực tăng cường (*step-up authentication*).
5. Nhận diện các cách làm giả vị trí, dùng VPN/proxy, chuyển tiếp tín hiệu, lạm dụng phiên và các nguyên nhân gây cảnh báo sai.
6. Đề xuất chiến lược kiểm thử, giảm thiểu rò rỉ thông tin vị trí và hỗ trợ người dùng di chuyển hợp pháp.

## 2. Vị trí là “yếu tố” gì?

Trong cách giới thiệu bảo mật, đôi khi ta bắt gặp câu “**somewhere you are**” — *bạn đang ở đâu*. Ví dụ, doanh nghiệp chỉ cho phép thực hiện một thao tác nhạy cảm khi nhân viên đang ở văn phòng, hoặc yêu cầu xác minh bổ sung nếu tài khoản bất ngờ đăng nhập từ khu vực chưa từng xuất hiện.

Tuy nhiên, cần phân biệt **cách gọi thường gặp** với **phân loại yếu tố xác thực**:

| Nhóm | Câu hỏi | Ví dụ |
|---|---|---|
| **Something you know — điều bạn biết** | Người dùng biết bí mật nào? | Mật khẩu, PIN dùng để mở khóa một authenticator |
| **Something you have — vật bạn sở hữu/kiểm soát** | Người dùng kiểm soát vật/thiết bị/khóa nào? | Khóa bảo mật, authenticator phần cứng, thiết bị chứa khóa passkey |
| **Something you are — đặc điểm sinh trắc** | Đặc điểm sinh trắc nào được kiểm tra? | Vân tay hoặc khuôn mặt, thường dùng cùng authenticator |
| **Location — bạn đang ở đâu** | Yêu cầu có vẻ đến từ vị trí nào? | IP suy đoán quốc gia; tọa độ GPS; hiện diện ở một mạng/địa điểm |

Trong mô hình MFA của các chuẩn như NIST SP 800-63, yếu tố được phân loại chủ yếu thành **knowledge, possession, inherence**. **Vị trí địa lý thông thường là tín hiệu ngữ cảnh hoặc tín hiệu rủi ro, không tự động là một yếu tố xác thực độc lập**. Việc kết hợp mật khẩu với IP thuộc văn phòng không nên được quảng bá là “MFA hai yếu tố”, vì IP hoặc vị trí có thể bị chia sẻ, thay đổi hay giả mạo.

Một hệ thống có thể sử dụng bằng chứng **hiện diện tại nơi được kiểm soát** để áp dụng chính sách truy cập; ví dụ thiết bị kết nối mạng nội bộ với xác thực thiết bị mạnh. Khi đó, bảo đảm đáng tin chủ yếu có thể đến từ **chứng chỉ/khóa mật mã và kiểm soát mạng**, không chỉ từ việc suy đoán tọa độ.

### Ví dụ đầu tiên

An đăng nhập từ Hà Nội bằng mật khẩu chính xác. Tài khoản của An thường đăng nhập tại TP. Hồ Chí Minh. Hệ thống nên hiểu:

- **Mật khẩu đúng:** một kiểm tra của bước xác thực đạt yêu cầu theo cơ chế đã thiết kế.
- **Vị trí bất thường:** một tín hiệu có thể làm tăng rủi ro; **chưa chứng minh** đây là kẻ tấn công.
- **Biện pháp phù hợp:** tùy bối cảnh, yêu cầu passkey/MFA, hạn chế thao tác nhạy cảm, thông báo đăng nhập hoặc kiểm tra thêm thiết bị.

Kết luận sai là “An ở thành phố lạ nên An chắc chắn giả mạo”; kết luận sai khác là “IP ở văn phòng nên chắc chắn đây là An”.

## 3. Những nguồn dữ liệu được gọi là “vị trí”

Từ “vị trí” có thể chỉ các bằng chứng khác nhau, có độ chính xác và độ tin cậy rất khác nhau.

| Nguồn | Hệ thống biết gì? | Điểm mạnh | Hạn chế, rủi ro |
|---|---|---|---|
| **Địa chỉ IP công khai** | Ước lượng quốc gia, vùng, thành phố hoặc nhà mạng/ASN của điểm ra Internet | Thường có sẵn ở máy chủ, ít cần quyền thiết bị | Không chứng minh vị trí con người; VPN, proxy, NAT, mạng di động và cơ sở dữ liệu định vị IP có thể gây sai lệch |
| **GPS/GNSS** | Thiết bị báo tọa độ và độ chính xác ước lượng | Có thể chi tiết trong điều kiện tốt | Cần quyền truy cập; có thể bị giả lập/spoof ở máy khách; tín hiệu yếu trong nhà; tọa độ được gửi lên cần được coi là đầu vào chưa tin cậy |
| **Wi-Fi** | Mạng đang kết nối hoặc mạng lân cận, đôi khi kèm cơ sở dữ liệu điểm phát | Hữu ích trong tòa nhà/khu vực nhỏ | SSID/BSSID có thể bị bắt chước; cơ sở dữ liệu cũ; kết nối vào Wi-Fi không đủ để nhận dạng người dùng |
| **Mạng di động** | Trạm phát sóng/vùng phủ hoặc vị trí do nền tảng mạng ước lượng | Phủ sóng rộng, hỗ trợ ước lượng thô | Độ chính xác thay đổi; IP thoát mạng có thể ở thành phố khác; nguồn dữ liệu nhạy cảm |
| **Bluetooth/BLE, NFC, UWB** | Thiết bị có thể đang ở gần beacon/đầu đọc hoặc đáp ứng giao thức lân cận | Có thể phục vụ yêu cầu hiện diện vật lý | Tín hiệu đơn giản có thể bị phát lại/relay; chống relay cần giao thức và thiết bị phù hợp, không chỉ đo RSSI |
| **Mạng doanh nghiệp / cổng ra VPN** | Yêu cầu đi qua đường mạng được kiểm soát ở mức nào đó | Phù hợp chính sách truy cập mạng nếu cấu hình đúng | IP VPN của nhân viên ở xa vẫn có thể giống văn phòng; mạng dùng chung không tự định danh người |
| **Lịch sử đăng nhập** | Mẫu quốc gia, thiết bị, thời điểm và tuyến mạng thường gặp | Dùng phát hiện bất thường | Dữ liệu cũ, thiên lệch; người dùng đi công tác, chuyển nhà, đổi nhà mạng |

**Độ chính xác không đồng nghĩa độ tin cậy.** Tọa độ GPS có thể rất chi tiết nhưng được client tự gửi nên dễ thao túng hơn một tín hiệu mạng do ingress đáng tin ghi nhận. Ngược lại, địa chỉ IP do ingress ghi nhận tương đối đáng tin về **điểm kết nối mà ingress thấy**, nhưng vẫn không cho biết vị trí thực của con người ở phía sau VPN.

Nếu kết hợp nguồn, cần lưu thêm **thời điểm thu thập, sai số ước lượng, nguồn và mức tin cậy**, thay vì chỉ có một cặp `latitude, longitude` rồi mặc định đó là sự thật.

## 4. Ranh giới tin cậy: từ nguồn tín hiệu đến quyết định bảo mật

Giả sử một API nhận các giá trị sau:

~~~http
POST /login
X-Forwarded-For: 203.0.113.12
Content-Type: application/json

{
  "username": "an",
  "password": "<bi-mat>",
  "latitude": 10.7769,
  "longitude": 106.7009,
  "country": "VN"
}
~~~

**Không được** tin rằng vị trí của An là TP. Hồ Chí Minh chỉ vì client đưa ra tọa độ hoặc gửi `country = "VN"`. Kẻ tấn công có thể thay toàn bộ JSON. Header `X-Forwarded-For` cũng có thể do client tự đặt nếu hệ thống không có cơ chế ingress đáng tin để quản lý header này.

Luồng an toàn cần xác định rõ:

1. **Biên nhận request:** reverse proxy/load balancer đáng tin nhìn thấy IP của phía kết nối với nó. Nếu có chuỗi proxy, ứng dụng chỉ diễn giải các forwarding header theo cấu hình **trusted proxies**; ingress phải loại bỏ hoặc chuẩn hóa header do client không đáng tin gửi.
2. **Phân tích IP:** dịch vụ địa lý hóa IP trả về ước lượng, nhà mạng, ASN hoặc loại mạng. Đây vẫn là **suy đoán**, không phải bằng chứng về người dùng.
3. **Thông tin thiết bị:** dữ liệu GPS, Wi-Fi, cảm biến hoặc vị trí do ứng dụng gửi là dữ liệu cần đánh giá nguồn và tính toàn vẹn. Attestation của thiết bị có thể tăng độ tin cậy đối với một số thuộc tính, nhưng không tự động chứng minh tọa độ là tuyệt đối đúng hoặc không bị relay.
4. **Danh tính đăng nhập:** các cơ chế xác thực (mật khẩu, passkey, chứng chỉ, MFA) được xác minh độc lập. Dữ liệu vị trí không được thay thế kết quả kiểm tra credential.
5. **Quyết định chính sách:** kết hợp principal đã xác thực, hành động, tài nguyên, mức rủi ro và điều kiện hiện hành để quyết định tiếp tục, yêu cầu step-up hoặc từ chối.

**Nguyên tắc:** mọi giá trị nằm ở thiết bị do người dùng hoặc kẻ tấn công kiểm soát đều là đầu vào chưa tin cậy cho tới khi có quy trình xác minh phù hợp; ngay cả nguồn “đáng tin hơn” vẫn cần được hiểu đúng phạm vi bảo đảm.

## 5. Location-based authentication và risk-based authentication

Hai cách dùng vị trí phổ biến:

### 5.1. Điều kiện vị trí tĩnh: geofencing

**Geofence** là ranh giới khu vực do tổ chức định nghĩa. Ví dụ: chỉ được đăng nhập vào hệ thống quản lý phòng thí nghiệm khi yêu cầu xuất phát từ một mạng được quản lý, hoặc chỉ cho phép phê duyệt lệnh xuất kho khi có bằng chứng hiện diện tại cơ sở.

Tuy nhiên, quyết định “nằm trong geofence” chỉ có ý nghĩa khi:

- Nguồn vị trí có độ tin cậy phù hợp với **mức rủi ro của thao tác**.
- Có chính sách xử lý khi dữ liệu bị thiếu, sai số lớn hoặc bị nghi giả mạo.
- Có kiểm tra AuthN và AuthZ độc lập, cộng với giới hạn tenant, chức năng, đối tượng và vai trò.
- Cơ chế vị trí không tạo đường vòng chỉ vì client biết IP/SSID “đúng”.

**IP allowlist** có thể giảm bề mặt truy cập, nhưng cần coi đây là một lớp hạn chế mạng. Một IP công khai có thể được nhiều người chia sẻ; việc nằm trong danh sách IP không tự động xác thực người đang cầm thiết bị.

### 5.2. Tín hiệu rủi ro động: adaptive / risk-based authentication

Hệ thống đánh giá vị trí kết hợp với ngữ cảnh:

- Tài khoản đã xuất hiện ở quốc gia này trước đây chưa?
- Vị trí ước lượng có **khác đáng kể** so với lần đăng nhập gần nhất không?
- Thiết bị hiện tại có quen thuộc không? Mức độ xác thực có đủ cho thao tác không?
- Địa chỉ mạng có thuộc hosting provider, proxy/VPN hoặc tuyến mạng lạ theo nguồn đánh giá đáng tin không?
- Có nhiều lần đăng nhập thất bại, credential stuffing hoặc dấu hiệu chiếm phiên đồng thời không?

Đầu ra không nên là “địa điểm lạ → tài khoản giả”. Đó có thể là một **điểm rủi ro hoặc cờ bất thường**, dẫn tới step-up, đánh giá thêm, thông báo hoặc tạm giới hạn những thao tác đặc biệt nhạy cảm.

| Tín hiệu quan sát | Diễn giải có thể đúng | Hành động tham khảo |
|---|---|---|
| Vị trí quen thuộc, thiết bị quen, passkey thành công | Rủi ro tương đối thấp | Tiếp tục theo chính sách, vẫn kiểm tra quyền cho từng tài nguyên |
| Quốc gia mới nhưng thiết bị quen, đã xác thực mạnh | Có thể đang đi công tác | Có thể yêu cầu xác minh bổ sung cho thao tác nhạy cảm; tránh khóa cứng vô cớ |
| Quốc gia mới và thiết bị lạ, nhiều lần nhập sai trước đó | Rủi ro chiếm tài khoản cao hơn | Step-up chống phishing, giới hạn tốc độ và thông báo bảo mật |
| IP thuộc mạng VPN doanh nghiệp | Có thể là nhân viên ở xa | Không suy ra người dùng đang ở trong tòa nhà công ty |
| Tọa độ GPS do client tự gửi nằm đúng geofence | Dữ liệu chưa được xác minh | Không dùng làm điều kiện đủ để cấp đặc quyền |
| Phiên hợp lệ đột ngột đổi điểm ra mạng | Có thể đổi Wi-Fi/di động hoặc phiên bị đánh cắp | Đánh giá thiết bị, token/phiên, thao tác hiện tại và rủi ro; cân nhắc step-up |

## 6. “Impossible travel” là tín hiệu cảnh báo, không phải kết luận

**Impossible travel** thường chỉ tình huống hai sự kiện xác thực liên tiếp có khoảng cách và khoảng thời gian khiến việc một người tự di chuyển bình thường giữa hai vị trí trở nên không hợp lý.

Ví dụ, theo cơ sở dữ liệu định vị IP:

- 09:00, tài khoản An đăng nhập từ mạng được định vị ở TP. Hồ Chí Minh.
- 09:15, tài khoản này có đăng nhập mới từ mạng được định vị ở Hà Nội.
- Giả sử hai điểm cách nhau xấp xỉ 1.100 km, tốc độ suy ra là:

~~~text
15 phút = 0,25 giờ
1.100 km / 0,25 giờ = 4.400 km/giờ
~~~

Đây là tốc độ bất thường nếu thực sự là **cùng một người di chuyển vật lý**. Tuy nhiên, dữ liệu chỉ phản ánh **ước lượng vị trí mạng**, nên chưa thể kết luận tài khoản bị chiếm. Những giải thích hợp lệ có thể gồm:

- Một phiên dùng VPN/proxy và một phiên dùng mạng di động.
- Hạ tầng CDN, NAT, điểm thoát Internet hoặc cơ sở dữ liệu định vị IP đặt sai vị trí.
- Ứng dụng nền gửi request từ nơi khác, hoặc hai sự kiện không thực sự là hai lần người dùng mới đăng nhập.
- Nhân viên dùng thiết bị/remote desktop ở một vị trí, trong khi người đó ở vị trí khác.
- Dấu thời gian, múi giờ hoặc cách ghi nhận sự kiện không nhất quán.

Để kiểm tra tốt hơn, hãy dùng **thời gian do server tin cậy ghi nhận**, phân biệt đăng nhập tương tác với yêu cầu nền, xem độ chính xác vị trí, nhận diện cùng thiết bị/phiên, kiểm tra VPN/ASN và ghép với tín hiệu bất thường khác.

**Đừng sử dụng duy nhất một ngưỡng “tốc độ lớn hơn X thì khóa tài khoản”**. Những giá trị X khác nhau theo bài toán, chất lượng dữ liệu và nhóm người dùng; hệ thống cần đánh giá cảnh báo sai và có đường phục hồi an toàn.

## 7. Mẫu kiến trúc: location signal nằm ở đâu trong luồng đăng nhập?

~~~mermaid
sequenceDiagram
    autonumber
    actor User as Người dùng
    participant Client as Trình duyệt/ứng dụng
    participant Edge as Ingress đáng tin
    participant Auth as Hệ thống xác thực
    participant Risk as Bộ đánh giá rủi ro
    participant Policy as Chính sách truy cập

    User->>Client: Đăng nhập bằng credential/passkey
    Client->>Edge: Gửi request qua TLS
    Edge->>Edge: Quan sát IP kết nối, chuẩn hóa proxy headers
    Edge->>Auth: Request + network context từ ingress
    Auth->>Auth: Xác minh credential, anti-replay, MFA theo yêu cầu
    alt Credential không hợp lệ
        Auth-->>Client: Từ chối, chống dò đoán và lạm dụng
    else Xác thực cơ bản hợp lệ
        Auth->>Risk: Principal + mạng + thiết bị + lịch sử có kiểm soát
        Risk->>Risk: Ước lượng vị trí và mức bất thường
        Risk-->>Auth: Risk signals, confidence, lý do
        alt Cần xác thực tăng cường
            Auth->>Client: Yêu cầu bước xác thực bổ sung
            Client-->>Auth: Bằng chứng step-up
            Auth->>Auth: Xác minh step-up
        end
        Auth->>Policy: Principal + assurance + action + resource
        Policy-->>Auth: Permit hoặc Deny
        Auth-->>Client: Phiên/giới hạn hoặc từ chối theo chính sách
    end
~~~

Sơ đồ diễn tả thứ tự khái niệm, không bắt buộc mọi hệ thống phải có từng dịch vụ riêng. Trong triển khai thực tế, chặn lạm dụng mạng hoặc rate limit có thể diễn ra **trước** kiểm tra credential; bước xác minh thêm có thể thực hiện **trước khi cấp phiên đầy đủ** hoặc khi thao tác nhạy cảm được yêu cầu. Chỉ cấp mức quyền phù hợp sau khi các kiểm tra bắt buộc hoàn tất.

### Những ranh giới không được bỏ qua

1. **Client → ingress:** địa chỉ client mà ứng dụng sử dụng phải được thiết lập từ chuỗi proxy đáng tin; không tin tùy tiện `X-Forwarded-For`, `X-Real-IP` hay một header tự chế.
2. **Client → tín hiệu cảm biến:** vị trí trình duyệt/thiết bị cung cấp có thể cần quyền truy cập và có thể bị giả lập. Không coi một tọa độ đơn lẻ là bằng chứng mật mã.
3. **Tín hiệu rủi ro → principal:** một địa điểm quen thuộc không biến request vô danh thành request đã xác thực.
4. **Principal → authorization:** xác thực thành công, kể cả từ một địa điểm tin cậy, không có nghĩa người gọi được phép xem mọi tài nguyên.
5. **Giữa các service:** bảo vệ kết nối và danh tính giữa ingress, bộ đánh giá rủi ro và hệ thống xác thực; không cho phép caller tùy ý chèn một nhãn `trusted_location=true`.

## 8. Mã Java minh họa: vị trí chỉ là một tín hiệu đầu vào

Ví dụ dưới đây minh họa **quyết định sau khi đã xác thực danh tính cơ bản**. Các giá trị trong `LocationSignals` phải được thành phần đánh giá rủi ro xây dựng bằng nguồn và chính sách có kiểm soát, không ánh xạ trực tiếp từ JSON do client gửi.

~~~java
import java.util.UUID;

record AuthenticatedPrincipal(UUID accountId) {}

record LocationSignals(
    boolean geographicallyUnusual,
    boolean newDevice,
    boolean suspectedAutomatedAbuse,
    boolean insufficientLocationConfidence
) {}

enum NextAction {
    CONTINUE_WITH_NORMAL_POLICY,
    REQUIRE_STRONG_STEP_UP,
    TEMPORARILY_HOLD_AND_REVIEW
}

final class LoginRiskPolicy {
    NextAction decide(
        AuthenticatedPrincipal principal,
        LocationSignals signals
    ) {
        // Principal phải đến từ một luồng AuthN đã kiểm chứng.
        // Đây là chính sách ví dụ, không phải ngưỡng rủi ro chuẩn.
        if (signals.suspectedAutomatedAbuse()) {
            return NextAction.TEMPORARILY_HOLD_AND_REVIEW;
        }
        if (signals.geographicallyUnusual() && signals.newDevice()) {
            return NextAction.REQUIRE_STRONG_STEP_UP;
        }
        // Không phạt người dùng chỉ vì vị trí không xác định.
        // Kiểm tra quyền, mức bảo đảm và các quy tắc khác vẫn tiếp tục.
        return NextAction.CONTINUE_WITH_NORMAL_POLICY;
    }
}
~~~

Trong thiết kế thực, cần xử lý thêm trường hợp **không có dữ liệu vị trí**, signal chất lượng kém, người dùng di chuyển hợp pháp, thao tác nhạy cảm và trạng thái phiên. Bước `REQUIRE_STRONG_STEP_UP` phải thật sự dẫn tới việc xác minh một authenticator thích hợp — ví dụ passkey/WebAuthn hỗ trợ chống phishing — trước khi trao quyền phù hợp; không thể chỉ đặt một cờ “đã step-up”.

Một phần trích xuất context có thể được hình dung như sau:

~~~java
// Pseudocode: interface do ứng dụng định nghĩa.
// TrustedIngressResolver xác minh chuỗi proxy đáng tin.
NetworkContext network = trustedIngressResolver.from(request);

// Thành phần này chỉ đưa ra ước lượng, không chứng minh danh tính.
GeoEstimate estimate = ipGeoService.estimate(network.clientIp());

// Risk engine có thể dùng estimate + lịch sử + trạng thái thiết bị.
LocationSignals signals =
    riskSignals.forAccount(authenticatedPrincipal.accountId(),
                           estimate, network, deviceContext);
~~~

Nếu hệ thống có yêu cầu pháp lý hoặc nghiệp vụ buộc xác định hiện diện vật lý, chính sách cần bổ sung **nguồn bằng chứng hiện diện mạnh hơn và cơ chế xử lý khi không thể chứng minh**, thay vì dựa vào `geographicallyUnusual == false`.

## 9. Vì sao vị trí dễ bị giả mạo hoặc hiểu sai?

### 9.1. VPN, proxy, Tor và NAT

IP công khai thường cho biết **điểm mạng ra Internet**, không phải vị trí của người dùng. Một người đang ở nước A có thể dùng VPN với exit node tại nước B. Ngược lại, một người tại nước B có thể thoát ra Internet qua gateway doanh nghiệp ở nước A.

Điều này có hai hệ quả:

- **False positive:** người dùng hợp lệ bị đánh dấu bất thường khi đổi VPN, nhà mạng, đi công tác hoặc sử dụng mạng di động.
- **False negative:** kẻ tấn công có thể chọn exit IP gần khu vực quen thuộc của nạn nhân, khiến kiểm tra địa lý đơn giản không phát hiện được.

Danh sách IP “đáng ngờ” hoặc công cụ phát hiện proxy giúp bổ sung tín hiệu, nhưng bản thân nhãn IP không đủ để xác định ý định của người dùng.

### 9.2. GPS spoofing và chỉnh sửa dữ liệu ứng dụng

Nếu một API nhận `latitude` và `longitude` do client gửi, kẻ tấn công có thể tự chọn tọa độ. Trên một số thiết bị/môi trường, vị trí từ hệ điều hành hoặc ứng dụng cũng có thể bị giả lập. Việc chống sửa đổi ứng dụng và attestation có thể tăng độ khó tấn công nhưng không bảo đảm mọi thông tin vị trí đúng trong mọi tình huống.

Ngay cả khi tọa độ hợp lệ, **mang thiết bị đến một nơi** không chứng minh người được xác thực đang có mặt ở đó. Ai đó có thể mượn, đánh cắp hoặc điều khiển thiết bị từ xa.

### 9.3. Tín hiệu gần và tấn công relay

Một thiết bị nhìn thấy beacon Bluetooth hoặc phản hồi một tín hiệu gần không nhất thiết đang ở đúng vị trí mà hệ thống suy luận. Kẻ tấn công có thể chuyển tiếp thông điệp qua mạng (*relay attack*). Một số giao thức đo khoảng cách an toàn (*secure ranging / distance bounding*) giúp chống những kiểu relay cụ thể, nhưng cần hỗ trợ từ phần cứng, giao thức và cấu hình phù hợp.

Không nên tự thiết kế “chứng minh gần” chỉ bằng RSSI, tên Bluetooth, SSID hoặc timestamp do client gửi.

### 9.4. Tấn công phishing, replay và đánh cắp phiên vẫn tồn tại

Geofencing không làm mật khẩu chống phishing; kiểm tra vùng địa lý cũng không ngăn người dùng tiết lộ OTP cho trang giả. Nếu session cookie hoặc bearer token bị đánh cắp, request có thể mang danh tính hợp lệ từ một tuyến mạng khác. Cần bảo vệ vòng đời phiên/token, chống replay theo giao thức, phát hiện lạm dụng và ưu tiên authenticator chống phishing khi phù hợp.

**Vị trí là một lớp bối cảnh bổ sung**, không thể thay thế các kiểm tra mật mã và vòng đời danh tính.

## 10. Thiết kế chính sách phù hợp từng mức rủi ro

Một chính sách tốt cần cân bằng rủi ro bảo mật với khả năng người dùng làm việc hợp lệ:

| Hoạt động | Dữ liệu vị trí nên đóng vai trò gì? | Biện pháp mạnh hơn khi cần |
|---|---|---|
| Xem thông tin công khai | Thường không cần thu thập vị trí chính xác | Giới hạn lạm dụng ở tầng dịch vụ nếu có |
| Đăng nhập tài khoản thông thường | Tín hiệu đánh giá rủi ro, thường ở mức thô | MFA/passkey và giới hạn thử đăng nhập |
| Thay mật khẩu, thêm authenticator, khôi phục tài khoản | Có thể gợi ý bất thường; không chứng minh quyền sở hữu tài khoản | Xác thực lại, cơ chế recovery chặt chẽ, thông báo thay đổi |
| Chuyển tiền, xuất dữ liệu nhạy cảm | Có thể tăng mức rủi ro nếu vị trí/thiết bị không quen | Xác thực tăng cường, kiểm tra authorization và phê duyệt nghiệp vụ |
| Chỉ làm việc tại cơ sở được cấp phép | Một trong các điều kiện vật lý/nghiệp vụ | Xác thực thiết bị/người dùng mạnh, kiểm soát mạng/ra vào, bằng chứng hiện diện phù hợp |
| Truy cập từ xa qua VPN công ty | Tín hiệu tuyến mạng, không khẳng định ở trụ sở | Xác thực người dùng, mTLS hoặc chứng chỉ thiết bị và chính sách truy cập |

Khi áp dụng **step-up**, nên xét cả **mức bảo đảm hiện tại** và **độ mới của xác thực**. Nếu người dùng đã vừa hoàn thành bước xác thực chống phishing trên thiết bị quen thuộc, hệ thống có thể chọn xử lý khác với một phiên lâu ngày chỉ dựa vào mật khẩu, tùy chính sách và tín hiệu khác.

Nên phân biệt rõ các kết quả:

- **ALLOW / continue:** chưa có lý do để yêu cầu bước thêm từ tín hiệu vị trí; các bước kiểm tra khác vẫn bắt buộc.
- **CHALLENGE / step-up:** cần bổ sung bằng chứng danh tính hoặc mức bảo đảm cao hơn.
- **RESTRICT:** có thể cho xem thông tin ít nhạy cảm nhưng tạm giữ thao tác rủi ro cao theo chính sách.
- **DENY / hold:** chỉ khi chính sách và tổng hợp chứng cứ cho thấy cần từ chối hoặc tạm ngưng; cần cơ chế kháng nghị/phục hồi phù hợp.

## 11. Quyền riêng tư và trải nghiệm người dùng

Vị trí, đặc biệt là lịch sử tọa độ chi tiết, có thể tiết lộ nơi cư trú, nơi làm việc, lịch sinh hoạt và hành trình. Thu thập quá mức còn làm tăng thiệt hại nếu log hoặc dữ liệu phân tích bị lộ.

Thiết kế nên:

1. **Giải thích mục đích thu thập:** vì sao cần vị trí, mức độ chi tiết và hoạt động nào dùng tín hiệu này.
2. **Thu thập tối thiểu:** nếu chỉ cần đánh giá quốc gia hoặc trạng thái “khác thường”, không mặc định yêu cầu GPS chính xác cho mọi lần đăng nhập.
3. **Quản lý quyền:** tôn trọng quyết định cấp quyền vị trí của người dùng và quy định áp dụng; tránh biến tín hiệu vị trí không cần thiết thành điều kiện bắt buộc ngầm.
4. **Giới hạn lưu giữ:** lưu bằng chứng và kết quả rủi ro đủ phục vụ bảo mật, có thời hạn rõ ràng; tránh giữ hành trình chính xác vô thời hạn.
5. **Bảo vệ dữ liệu:** mã hóa khi truyền/lưu theo mức độ nhạy cảm, phân quyền truy cập log và báo cáo, không ghi credential hoặc token cùng dữ liệu định vị.
6. **Có phương án thay thế:** người dùng đi công tác, dùng mạng hỗ trợ riêng tư, có thiết bị không cấp GPS hoặc ở vùng sóng kém vẫn cần con đường xác thực an toàn và hỗ trợ phù hợp.
7. **Theo dõi sai lệch:** kiểm tra tỷ lệ cảnh báo sai đối với người di chuyển, làm việc từ xa, dùng IPv6, CGNAT hoặc nhà mạng có IP geolocation kém.

Ví dụ, log có thể cần giữ `country=VN`, `geo_anomaly=true`, `confidence=low` và thời điểm sự kiện, thay vì lưu tọa độ GPS chính xác của từng lần truy cập. Mức chi tiết tối thiểu phải do nhu cầu thực tế và quy định áp dụng quyết định.

## 12. Tình huống thực tế

### Tình huống A: nhân viên kết nối VPN

Mai đang làm việc từ nhà tại Đà Nẵng, kết nối VPN doanh nghiệp có cổng ra tại Hà Nội. API thấy IP của gateway tại Hà Nội.

**Nhận định đúng:** API thấy đường mạng đi qua gateway; chưa chứng minh Mai đang ở Hà Nội hay ở trụ sở. Để xác thực, hệ thống vẫn cần kiểm tra principal, session/token, authenticator và quyền theo chức năng.

**Thiết kế phù hợp:** nếu chính sách là “thiết bị được quản lý và xác thực qua VPN công ty”, hãy kiểm tra kết quả xác thực VPN, trạng thái thiết bị và danh tính ứng dụng. Đừng diễn giải thành “người dùng có mặt tại Hà Nội”.

### Tình huống B: đăng nhập bất thường sau khi lộ mật khẩu

Tài khoản thường truy cập từ Việt Nam, đột nhiên có đăng nhập bằng mật khẩu từ một mạng hosting ở quốc gia khác. Thiết bị mới và trước đó xuất hiện nhiều lần đăng nhập thất bại.

**Nhận định đúng:** nhiều tín hiệu rủi ro cùng xuất hiện; hệ thống nên buộc xác thực tăng cường chống phishing hoặc tạm ngăn phiên nhạy cảm theo chính sách, thông báo bảo mật và điều tra dấu hiệu credential stuffing.

**Không kết luận:** “IP nước ngoài là kẻ tấn công” hoặc “có mật khẩu đúng là an toàn”. Cần đánh giá bằng chứng xác thực và dấu hiệu lạm dụng đồng thời.

### Tình huống C: bảo vệ phê duyệt tại kho

Doanh nghiệp muốn chỉ cho phép phê duyệt xuất hàng khi có người có quyền đang có mặt tại kho. Một ứng dụng di động gửi GPS nằm trong geofence.

**Nhận định đúng:** GPS tự khai chỉ là bằng chứng vị trí độ tin cậy hạn chế. Đối với nghiệp vụ rủi ro cao, phải xác thực nhân viên, kiểm tra quyền phê duyệt và dùng cơ chế hiện diện được thiết kế, kiểm thử chống giả mạo/relay theo yêu cầu. Có thể cần thêm kiểm soát vật lý hoặc phê duyệt nhiều người.

### Tình huống D: phiên bị chiếm nhưng IP vẫn “quen”

Kẻ tấn công có cookie phiên của An và sử dụng proxy có điểm ra cùng thành phố với An.

**Nhận định đúng:** geolocation có thể không báo bất thường; điều này không chứng minh phiên an toàn. Các kiểm soát vòng đời session, chống đánh cắp phiên, re-authentication cho hành động nhạy cảm, đánh giá thiết bị và authorization vẫn cần thiết.

## 13. Ma trận kiểm thử đề xuất

Hãy kiểm thử cả **độ tin cậy của dữ liệu vị trí**, **quyết định bảo mật** và **khả năng dùng hợp pháp**.

| Kiểm thử | Điều cần xác minh |
|---|---|
| Client tự đặt `X-Forwarded-For` là IP trong allowlist | Ingress không tin giá trị tùy ý; client không thể tự nhận là đến từ mạng tin cậy |
| Client gửi GPS nằm trong geofence nhưng IP/môi trường khác thường | GPS chưa xác minh không tự cấp phiên hoặc quyền đặc biệt |
| VPN đặt exit IP ở quốc gia khác | Hệ thống hiểu đây là tín hiệu mạng, có xử lý phù hợp cho người dùng hợp lệ |
| Đăng nhập từ vị trí chưa từng thấy, thiết bị đã biết | Đánh giá theo nhiều tín hiệu, không khóa cứng chỉ vì vị trí |
| Vị trí mới, thiết bị mới, nhiều lần thử sai | Kích hoạt biện pháp kiểm soát rủi ro và step-up theo chính sách |
| Thời gian giữa hai địa điểm quá ngắn | Đánh dấu “impossible travel” có tính đến sai số dữ liệu, VPN và loại sự kiện |
| Thiết bị tắt quyền GPS hoặc không thể xác định IP | Không mặc định coi thiếu dữ liệu là chứng cứ gian lận; có đường xử lý an toàn |
| Tọa độ giả lập, SSID giả hoặc tín hiệu BLE bị relay | Không có đường cấp đặc quyền chỉ dựa vào tín hiệu chưa kiểm chứng |
| Phiên/token bị đánh cắp và dùng từ IP quen thuộc | Kiểm thử cơ chế bảo vệ phiên và step-up; geolocation không được là phòng tuyến duy nhất |
| Người dùng thuộc tenant T1 truy cập tài nguyên tenant T2 từ vị trí “đúng” | Authorization vẫn từ chối truy cập trái quyền |
| Quyền người dùng bị thu hồi trong khi session còn hiệu lực | Điều kiện địa lý không vượt qua được trạng thái tài khoản/phân quyền mới |
| Chính sách vị trí gây cảnh báo sai với mạng di động | Có giám sát false positive, khả năng hỗ trợ và phương án xác thực thay thế |

Trong kiểm thử tự động, nên tách mô-đun ước lượng địa lý khỏi bộ chính sách để có thể cấp các tình huống IP/độ tin cậy giả lập mà **không cần** dùng VPN hay đi đến các địa điểm thực. Không dùng dữ liệu vị trí cá nhân thật nếu không cần thiết.

## 14. Câu hỏi tự kiểm tra

**Câu 1.** Một API chấp nhận mật khẩu đúng và thấy IP nằm trong danh sách văn phòng. Có thể gọi đây là MFA hai yếu tố không?

*Trả lời:* Không. Mật khẩu là một yếu tố knowledge; IP cho biết điểm mạng quan sát được và không tự là possession/inherence độc lập. IP allowlist là kiểm soát ngữ cảnh/mạng, không tự chứng minh danh tính người dùng.

**Câu 2.** Người dùng xuất hiện ở hai quốc gia trong mười phút. Có thể kết luận bị chiếm tài khoản ngay không?

*Trả lời:* Chưa. Có thể là VPN, proxy, NAT, dữ liệu vị trí sai hoặc sự kiện nền. Cần đối chiếu thiết bị, phiên, thời gian do server ghi, chất lượng nguồn vị trí và các dấu hiệu lạm dụng khác; có thể yêu cầu step-up khi rủi ro đủ lớn.

**Câu 3.** Một ứng dụng gửi tọa độ GPS khớp geofence. Điều gì còn thiếu trước khi phê duyệt thao tác nhạy cảm?

*Trả lời:* Cần xác thực principal và kiểm tra quyền; cần hiểu độ tin cậy của GPS/thiết bị cùng khả năng giả mạo/relay. Nếu chính sách yêu cầu hiện diện thật, phải dùng bằng chứng phù hợp thay vì chỉ tin tọa độ client cung cấp.

**Câu 4.** Nếu passkey đã xác thực thành công, có còn cần kiểm tra quyền và rủi ro vị trí không?

*Trả lời:* Có. Passkey giúp chứng minh quyền kiểm soát authenticator và có thể chống phishing theo cấu hình đúng; nó không tự cấp mọi quyền. Vị trí có thể là tín hiệu phụ trợ khi đánh giá thao tác rủi ro cao, còn AuthZ vẫn kiểm tra hành động và tài nguyên.

## 15. Ghi nhớ trọng tâm

- **Vị trí thường là tín hiệu ngữ cảnh, không phải một yếu tố MFA độc lập.** Đừng dùng khái niệm “somewhere you are” để khẳng định mật khẩu + vị trí là xác thực hai yếu tố đạt chuẩn.
- **IP, GPS, Wi-Fi, mạng di động và tín hiệu gần mang mức tin cậy khác nhau.** Thông tin càng chính xác không tự động càng đáng tin; phải xét nguồn, sai số và ranh giới kiểm chứng.
- **Impossible travel và geofencing là công cụ đánh giá rủi ro hoặc áp chính sách.** VPN, NAT, proxy và di chuyển hợp pháp có thể làm kết quả khác thực tế.
- **Xác thực vẫn phải dựa vào credential/authenticator phù hợp**, kết hợp chống phishing, replay và lạm dụng đăng nhập. Vị trí không thể sửa lỗi phiên bị đánh cắp hoặc phân quyền sai.
- **Dùng vị trí theo mức độ cần thiết, có quyền riêng tư và phương án dự phòng.** Thu thập tối thiểu, đo tỷ lệ cảnh báo sai và bảo đảm người dùng hợp lệ có thể chứng minh danh tính qua phương thức an toàn khác.

Khi coi vị trí là bằng chứng **có giới hạn và cần diễn giải**, hệ thống có thể phát hiện đăng nhập bất thường tốt hơn mà không đánh đồng “truy cập từ một nơi quen thuộc” với “đúng con người, đúng quyền và an toàn”.
