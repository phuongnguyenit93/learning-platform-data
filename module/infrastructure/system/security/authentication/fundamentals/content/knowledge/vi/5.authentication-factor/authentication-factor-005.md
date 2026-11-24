# Yếu tố hành vi

## 1. Yếu tố hành vi là gì?

Trong bảo mật danh tính, **yếu tố hành vi** (*behavioral factor*) là những đặc điểm có thể quan sát được từ cách một chủ thể tương tác với hệ thống: nhịp gõ phím, cách di chuyển chuột, thao tác chạm, nhịp đi, giọng nói trong một số ứng dụng hoặc thói quen thực hiện giao dịch. Hệ thống có thể phân tích những dấu hiệu đó để ước lượng liệu người đang tương tác có phù hợp với người dùng đã biết, hoặc hành động hiện tại có bất thường hay không.

Ví dụ, một ứng dụng có thể nhận thấy tài khoản thường gõ từng phím với khoảng thời gian tương đối ổn định, nhưng phiên hiện tại tạo ra chuỗi thao tác có nhịp và tốc độ khác biệt lớn. Đây là **tín hiệu rủi ro** để xem xét, chưa phải kết luận rằng người dùng đã bị mạo danh.

Trong module **SECURITY_AUTHENTICATION_FUNDAMENTALS**, yếu tố hành vi giúp kết nối các chủ đề credential, mật khẩu, MFA, passkey, chứng chỉ, token, phiên và khôi phục tài khoản với việc **đánh giá liên tục ranh giới tin cậy**. Nó đặc biệt hữu ích để phát hiện tự động hóa đăng nhập, hành vi khác thường trong phiên hoặc thao tác nhạy cảm. Tuy nhiên, việc thu thập hành vi phải có giới hạn rõ ràng vì tín hiệu có sai số, dễ thay đổi theo bối cảnh và có thể ảnh hưởng quyền riêng tư.

**Mục tiêu học tập:** Sau bài này, người học có thể nhận diện loại tín hiệu hành vi, phân biệt nó với yếu tố xác thực độc lập, thiết kế vòng đời thu thập và đánh giá rủi ro, và chọn phản ứng an toàn trước phishing, replay, chiếm phiên và lạm dụng đăng nhập.

## 2. Phân loại đúng: hành vi có phải một yếu tố MFA độc lập?

Ba nhóm yếu tố xác thực thường gặp là:

| Nhóm | Bản chất | Ví dụ | Rủi ro đặc trưng |
| --- | --- | --- | --- |
| **Something you know** — điều biết | Bí mật do người dùng biết | Mật khẩu, PIN | Phishing, đoán mật khẩu, lộ từ hệ thống khác |
| **Something you have** — điều sở hữu/kiểm soát | Thiết bị hoặc khóa xác thực | Khóa bảo mật FIDO2, authenticator, smart card | Mất thiết bị, chiếm quyền hoặc đánh cắp khóa |
| **Something you are** — đặc điểm sinh trắc | Đặc điểm sinh học/hành vi được dùng để nhận dạng | Dấu vân tay, khuôn mặt; có thể có nhịp gõ phím | Sai số, giả mạo, khó thay thế mẫu đã lộ |

Cụm từ **“something you do”** đôi khi được dùng để mô tả hành vi. Đây là cách nói dễ nhớ trong một số tài liệu, **không phải bằng chứng rằng hành vi luôn tạo thành nhóm yếu tố thứ tư độc lập**. Khi đặc điểm hành vi được dùng để phân biệt con người, nó thường được xem là một dạng **sinh trắc hành vi** (*behavioral biometrics*) hoặc một tín hiệu đánh giá rủi ro. Các khung bảo đảm xác thực có thể có yêu cầu riêng về cách sử dụng sinh trắc.

Điều kiện cốt lõi của **MFA (multi-factor authentication)** là kết hợp các yếu tố thuộc những nhóm phù hợp và độc lập theo yêu cầu chính sách. Hai đặc điểm như **nhịp gõ phím + cách di chuột** có thể cùng chịu ảnh hưởng từ một thiết bị, một người điều khiển hoặc một phần mềm giả lập. Chúng **không tự động tương đương hai yếu tố MFA**. Một mô hình học máy cho điểm “trùng người dùng” cao cũng **không tự chứng minh quyền sở hữu passkey, mật khẩu hay khóa riêng**.

> Quy tắc thực hành: sử dụng tín hiệu hành vi để **bổ sung quyết định rủi ro** hoặc yêu cầu bước xác thực mạnh hơn. Không tùy tiện dùng điểm hành vi để bỏ qua credential, MFA hoặc yêu cầu xác thực có ràng buộc origin.

Ví dụ, mật khẩu + nhịp gõ phím không mặc nhiên đáp ứng cùng chính sách với mật khẩu + khóa bảo mật. Passkey dùng WebAuthn/FIDO2 có cơ chế khóa mật mã và kiểm tra origin/challenge; nhịp gõ phím không cung cấp những bảo đảm mật mã tương tự.

## 3. Những loại tín hiệu hành vi

Tín hiệu có thể được thu thập **chủ động** trong một thử thách cụ thể hoặc **thụ động** trong quá trình sử dụng thông thường. Các nhóm thường gặp:

| Tín hiệu | Dữ liệu đặc trưng có thể trích xuất | Ứng dụng điển hình | Hạn chế cần nhớ |
| --- | --- | --- | --- |
| **Keystroke dynamics** — nhịp gõ | Thời gian giữ phím (*dwell time*), khoảng cách giữa lần nhấn (*flight time*), độ biến thiên nhịp | Đánh giá rủi ro khi đăng nhập hoặc điền biểu mẫu | Bị ảnh hưởng bởi bàn phím, ngôn ngữ, thiết bị hỗ trợ, mỏi tay; tránh lưu nội dung người dùng gõ |
| **Mouse dynamics** — thao tác chuột | Vận tốc, gia tốc, độ cong đường di chuyển, khoảng nghỉ và kiểu nhấp | Phân biệt hành vi tự động hóa và tương tác quen thuộc | Phụ thuộc độ phân giải, chuột, touchpad, hệ điều hành; có thể bị mô phỏng |
| **Touch/gesture dynamics** — thao tác chạm | Thời gian chạm, hướng vuốt, tốc độ, áp lực nếu thiết bị hỗ trợ | Đánh giá phiên trên thiết bị di động | Khác biệt lớn giữa thiết bị; người dùng thay cách cầm, bị thương hoặc dùng công cụ hỗ trợ |
| **Gait/motion** — dáng đi, chuyển động | Nhịp bước, gia tốc, con quay hồi chuyển | Một số ngữ cảnh thiết bị đeo hoặc thiết bị cá nhân | Nhiễu môi trường, thay đổi thể trạng; yêu cầu quyền truy cập cảm biến |
| **Voice behavior** — đặc trưng giọng | Nhịp, cao độ, ngữ điệu hoặc embedding giọng trong hệ được thiết kế riêng | Một số kênh thoại | Giả giọng, phát lại, deepfake, âm thanh nhiễu; phải xử lý như dữ liệu sinh trắc nhạy cảm |
| **Interaction pattern** — mẫu thao tác | Trình tự trang, tốc độ hoàn tất biểu mẫu, chuỗi thao tác khác thường | Phát hiện bot, credential stuffing, gian lận giao dịch | Có thể phản ánh loại nhiệm vụ chứ không phản ánh danh tính |
| **Transaction behavior** — mẫu giao dịch | Tần suất, thời điểm, số tiền tương đối, nhóm thao tác | Risk-based authentication trước giao dịch nhạy cảm | Hành vi hợp lệ có thể thay đổi đột ngột; cần kiểm tra nguy cơ và quyền riêng tư |

**Không phải mọi tín hiệu trong bảng đều là sinh trắc.** Ví dụ, lịch sử giao dịch hoặc luồng điều hướng có thể phục vụ chấm điểm gian lận, nhưng tự nó không nhất thiết được thiết kế để nhận dạng một người. Cần nêu rõ mục đích sử dụng để tránh nhầm **fraud detection**, **behavioral biometrics** và **authentication**.

### 3.1. Đặc điểm động và ngữ cảnh

Sự khác biệt về nhịp gõ có thể đến từ chính người dùng trong một ngày mệt mỏi, hoặc do chuyển từ laptop sang điện thoại. Tín hiệu hành vi vì vậy thường có các thuộc tính:

- **Không hoàn toàn ổn định:** thay đổi theo thời gian và tình trạng người dùng.
- **Phụ thuộc môi trường:** trình duyệt, độ trễ, thiết bị ngoại vi và điều kiện mạng ảnh hưởng phép đo.
- **Có tính xác suất:** khớp mẫu chỉ mang lại mức độ phù hợp, không phải chứng cứ tuyệt đối.
- **Có thể bị giả lập:** bot, công cụ tự động hoặc người điều khiển từ xa có thể mô phỏng một số hành vi.
- **Có thể nhạy cảm:** mẫu hành vi đôi khi cho phép suy ra sức khỏe, khuyết tật hoặc thói quen cá nhân ngoài mục đích xác thực.

Vì vậy, chất lượng dữ liệu, việc xin phép và giới hạn sử dụng phải được xác định trước khi xây dựng mô hình.

## 4. Yếu tố hành vi đi vào luồng xác thực thế nào?

Một mô hình ứng dụng điển hình là **risk-based authentication**: mật khẩu/passkey/MFA tiếp tục là cơ sở xác thực; tín hiệu hành vi hỗ trợ quyết định có cần kiểm tra bổ sung hay không.

~~~mermaid
flowchart TD
    A[Người dùng bắt đầu đăng nhập hoặc thao tác nhạy cảm] --> B[Kiểm tra credential và ngữ cảnh phiên]
    B --> C{Đủ yêu cầu xác thực cơ bản?}
    C -- Không --> R[Từ chối hoặc yêu cầu phương thức hợp lệ]
    C -- Có --> D[Thu thập tín hiệu hành vi được phép]
    D --> E[Kiểm tra chất lượng và tính mới của tín hiệu]
    E --> F[Đánh giá lệch mẫu và ngữ cảnh rủi ro]
    F --> G{Quyết định theo chính sách}
    G -- Rủi ro thấp --> H[Tiếp tục theo quyền hiện có]
    G -- Rủi ro cao hoặc thiếu tin cậy --> I[Step-up bằng passkey/MFA hoặc xử lý an toàn]
    I --> J{Thử thách hợp lệ?}
    J -- Có --> H
    J -- Không --> R
    H --> K[Đánh giá lại khi phiên tiếp tục]
~~~

Điểm quan trọng là bước **kiểm tra credential và chính sách xác thực cơ bản** không bị loại bỏ chỉ vì điểm hành vi trông bình thường. Chỉ những ràng buộc do hệ thống có thẩm quyền đã xác minh mới được phép tạo hoặc nâng mức tin cậy của phiên.

### 4.1. Ba thời điểm ứng dụng

1. **Lúc đăng nhập:** phát hiện biểu hiện giống bot, sai khác lớn so với mẫu đã có, hoặc thiết bị/ngữ cảnh không quen thuộc; có thể kích hoạt xác thực bổ sung, chống lạm dụng hoặc review.
2. **Trong phiên (*continuous/risk-adaptive authentication*):** kiểm tra tín hiệu bất thường sau khi phiên đã được cấp, hỗ trợ phát hiện chiếm phiên hoặc tương tác không phù hợp. Điều này **không đồng nghĩa hệ thống liên tục chứng minh danh tính chắc chắn**.
3. **Trước thao tác nhạy cảm:** dùng ngữ cảnh và hành vi để quyết định yêu cầu xác thực lại (*reauthentication/step-up*), ví dụ trước khi thay phương thức khôi phục hoặc chuyển tài sản.

Nếu người dùng **chưa có dữ liệu hành vi** (đăng nhập lần đầu, đổi thiết bị, không cung cấp quyền thu thập), hệ thống cần đường thay thế an toàn dựa trên credential phù hợp. Thiếu dữ liệu không thể được xem là “chắc chắn gian lận”, và cũng không nên mặc nhiên cho phép bỏ qua yêu cầu xác thực.

## 5. Vòng đời mẫu hành vi: đăng ký, đối chiếu và cập nhật

Để một hệ thống có thể đánh giá nhịp gõ hoặc thao tác chuột, nó cần một **mẫu tham chiếu** (*behavioral profile/template*) được xây dựng từ dữ liệu đủ tin cậy.

### 5.1. Giai đoạn thiết lập mẫu

Mẫu nên được thiết lập **sau khi** hệ thống đã xác thực tài khoản bằng phương thức phù hợp. Một cách làm khái niệm:

1. Xác định mục đích, loại dữ liệu thu thập, cơ sở xử lý, thời hạn giữ và chính sách cho phép.
2. Thu thập nhiều lần tương tác có chất lượng ở ngữ cảnh tương đối ổn định, gắn với principal đã được xác thực.
3. Trích xuất các đặc trưng được phép, ví dụ thống kê thời gian giữ và chuyển phím, thay vì lưu nội dung mật khẩu hoặc văn bản đã nhập.
4. Kiểm tra chất lượng mẫu: số lượng sự kiện, phân bố thời gian, độ tin cậy thiết bị, tính nhất quán.
5. Tạo mẫu tham chiếu, lưu phiên bản mô hình và ngày cập nhật, bảo vệ truy cập như dữ liệu có tính nhạy cảm.

Cần tránh để kẻ tấn công đang kiểm soát phiên **đầu độc mẫu** bằng việc đưa hành vi của họ vào dữ liệu “bình thường”. Việc cập nhật profile phải có tiêu chí tin cậy và có thể tạm dừng trong giai đoạn nghi ngờ chiếm tài khoản.

### 5.2. Giai đoạn xác minh một lần tương tác

Tại mỗi lần đối chiếu, hệ thống trích xuất cùng loại đặc trưng, so với mẫu tham chiếu và tính **độ phù hợp** hoặc **điểm bất thường**. Ví dụ:

- Hồ sơ đã biết: thời gian giữ phím tương đối đều khi dùng bàn phím vật lý.
- Lần hiện tại: nhiều sự kiện có thời gian gần như đồng nhất, không giống tương tác người dùng đã ghi nhận.
- Nhận xét: có thể là tự động hóa, phần mềm hỗ trợ, thay thiết bị hoặc đo sai. Cần xét **chất lượng mẫu và ngữ cảnh**, không kết luận ngay “đã bị hack”.

Kết quả đo nên bao gồm **độ tin cậy của phép đo**. Không đủ sự kiện hoặc độ trễ không ổn định có thể khiến hệ thống từ chối đưa ra kết luận, thay vì coi dữ liệu không đạt là bằng chứng người dùng bất thường.

### 5.3. Giai đoạn cập nhật và hết hạn mẫu

Hành vi người dùng thay đổi theo thời gian (*concept drift*). Một hệ thống thực tế nên:

- Tái hiệu chỉnh mẫu theo những phiên **đã xác thực đáng tin** và không có dấu hiệu gian lận.
- Hạn chế cập nhật tự động nếu đang phát hiện rủi ro cao hoặc nghi ngờ account takeover.
- Quản lý phiên bản, quan sát phân bố điểm và kiểm thử trước khi đổi mô hình.
- Có đường cấp lại mẫu, xóa mẫu và chuyển sang hình thức xác thực khác khi thiết bị hoặc khả năng vận động của người dùng thay đổi.

Một profile được đo đúng tại thời điểm trước đây không trở thành “chữ ký vĩnh viễn” của người dùng.

## 6. Mô hình kết quả: điểm số không phải bằng chứng tuyệt đối

Một dịch vụ phân tích hành vi có thể cung cấp **đánh giá rủi ro** cho máy chủ xác thực hoặc công cụ chính sách. Ví dụ TypeScript sau là **hợp đồng minh họa**, không phải chuẩn giao thức:

~~~ts
type BehavioralAssessment = {
  principalRef: string;
  sessionRef: string;
  assessedAt: string;
  scope: "login" | "active_session" | "sensitive_action";
  modelVersion: string;
  sampleQuality: "sufficient" | "low" | "unavailable";
  anomalyScore: number; // Ví dụ 0..1: càng cao càng bất thường
  signals: Array<"keystroke_timing" | "pointer_motion" | "touch_pattern">;
  reasonCodes: string[]; // Mã nội bộ, tránh tiết lộ chi tiết chống gian lận
};

type AuthPolicyDecision =
  | { kind: "continue"; assuranceUnchanged: true }
  | { kind: "step_up"; requiredAuthenticator: "passkey" | "approved_mfa" }
  | { kind: "restrict"; action: "hold" | "deny" | "manual_review" };
~~~

**Không nên** dùng một con số trần như “score = 0,97” để quyết định đã xác thực đúng người. Cần biết ý nghĩa thang điểm, phiên bản mô hình, chất lượng và độ mới của mẫu, tỷ lệ sai trên dữ liệu thực tế, cùng ngưỡng riêng cho hành động có rủi ro khác nhau.

Ví dụ chính sách nội bộ dưới đây mô tả ý tưởng **không cho điểm hành vi bỏ qua yêu cầu xác thực**:

~~~text
function decide(authState, behavior, action):
    if not authState.valid:
        return REQUIRE_STANDARD_AUTHENTICATION

    if action.requiresRecentStrongAuthentication
       and not authState.meetsRequiredAssurance:
        return REQUIRE_APPROVED_STEP_UP

    if behavior.sampleQuality == "unavailable":
        return CONTINUE_WITH_BASELINE_AUTH_POLICY

    if behavior.indicatesHighRisk:
        return REQUIRE_APPROVED_STEP_UP_OR_RESTRICT

    return CONTINUE_UNDER_EXISTING_AUTHORIZATION
~~~

Trong hệ thống sản xuất, việc phân quyền tài nguyên (*authorization*) và quyết định chặn giao dịch vẫn phải được thực hiện tại server. Client không được tự gửi cờ “behaviorVerified = true” rồi được tin ngay.

## 7. Ví dụ thực tế: đăng nhập bằng mật khẩu và hành vi

Giả sử ứng dụng có phiên đăng nhập thông thường bằng mật khẩu + MFA, đồng thời muốn phát hiện đăng nhập tự động.

| Diễn biến | Điều hệ thống biết | Phản ứng phù hợp |
| --- | --- | --- |
| Người dùng nhập mật khẩu đúng, chưa qua MFA | Kiểm chứng được một yếu tố, chưa đủ chính sách | Yêu cầu MFA; hành vi “giống người quen” không thay thế MFA |
| Mật khẩu đúng, đã qua MFA; nhịp gõ khác thường | Phiên có thể được xác thực, nhưng có thêm tín hiệu bất thường | Xét thiết bị, ngữ cảnh, chất lượng mẫu; tăng giám sát hoặc step-up ở tác vụ nhạy cảm |
| Mật khẩu sai hàng loạt, thao tác chuột được lập trình | Dấu hiệu credential stuffing hoặc bot | Rate limit, kiểm soát abuse, cảnh báo nội bộ; không trả chi tiết mô hình cho đối thủ |
| Người dùng hợp lệ mới đổi sang bàn phím khác | Mẫu có thể sai do thiết bị | Cho dùng phương thức xác thực thay thế, tránh khóa tài khoản chỉ vì hành vi thay đổi |
| Phiên đang dùng bỗng xuất hiện thao tác giao dịch bất thường | Nguy cơ session hijacking hoặc giao dịch gian lận | Thử thách lại qua kênh/phương thức phù hợp, giới hạn thao tác cho tới khi thỏa chính sách |

Với một yêu cầu có rủi ro cao như thay email khôi phục, quyết định an toàn thường là **yêu cầu lại bằng chứng kiểm soát authenticator đã đăng ký** nếu phiên chưa thỏa tính mới và mức bảo đảm. Điểm hành vi thấp không thể làm mất đi yêu cầu đó; điểm bất thường cao có thể là căn cứ tăng cường bảo vệ.

## 8. Chống phishing, replay, giả mạo và chiếm phiên

Yếu tố hành vi không thay thế các kiểm soát mật mã và quản lý phiên. Các mối đe dọa chính:

| Mối đe dọa | Cách khai thác | Kiểm soát nên kết hợp |
| --- | --- | --- |
| **Phishing** | Đánh cắp mật khẩu/OTP rồi đăng nhập từ môi trường khác | Ưu tiên WebAuthn/passkey ràng buộc origin, MFA phù hợp, phát hiện đăng nhập bất thường; không xem hành vi là bảo vệ chống phishing độc lập |
| **Replay** | Gửi lại event hoặc mẫu thao tác cũ | Ràng buộc mẫu với session, thời điểm, challenge và kiểm tra phía server; phát hiện sự kiện trùng lặp/không hợp lý |
| **Tự động hóa/bot** | Phát sinh chuỗi sự kiện giả để giống người thật | Rate limiting, phân tích hành vi, xác minh ngữ cảnh, chính sách chống abuse đa lớp |
| **Giả lập hành vi** | Mô hình hoặc người khác bắt chước nhịp gõ, mouse path | Không dựa duy nhất vào điểm hành vi; dùng cryptographic authenticator và step-up |
| **Chiếm phiên** | Đánh cắp cookie/token rồi thao tác như người dùng | Cookie Secure/HttpOnly/SameSite khi phù hợp, kiểm soát CSRF, TTL, rotation, thu hồi và xác thực lại |
| **Điều khiển máy từ xa** | Đối thủ dùng chính thiết bị và phiên hợp lệ | Phân tích giao dịch, cảnh báo ngữ cảnh, xác nhận thao tác quan trọng bằng cơ chế độc lập |
| **Đầu độc profile** | Kẻ xấu sau khi chiếm phiên huấn luyện mẫu hành vi của mình | Chỉ học từ phiên tin cậy, chặn cập nhật khi rủi ro cao, quản lý phiên bản và rollback |
| **Đánh cắp mẫu** | Lộ dữ liệu động tác hoặc embedding hành vi | Tối thiểu hóa, phân quyền, mã hóa, chống truy xuất hàng loạt, chính sách xóa |
| **Giả mạo hoặc bóp méo telemetry** | Script trên client gửi timing và sự kiện giả | Kiểm tra server, tính hợp lý của thời gian/chuỗi sự kiện; không tin event client như bằng chứng mật mã |

**Ranh giới tin cậy cần nhớ:** JavaScript trong trình duyệt hoặc SDK trên thiết bị có thể đo tương tác, nhưng dữ liệu được gửi từ client **có thể bị kiểm soát bởi client hoặc phần mềm độc hại**. HTTPS bảo vệ truyền tải qua mạng; nó không tự chứng minh event đã xuất phát từ thao tác thật của một người. Thiết kế có thể tăng độ tin cậy bằng kiểm tra tính nhất quán, sự kiện phía server và xác thực thiết bị phù hợp, nhưng không được mô tả các biện pháp này như bảo đảm tuyệt đối.

### 8.1. Tại sao replay vẫn nguy hiểm khi “mẫu hành vi rất riêng”?

Một vector timing thu thập từ người dùng có thể trở thành dữ liệu tấn công nếu hệ thống chấp nhận nó nhiều lần. Mẫu cần được đánh giá trong **ngữ cảnh giao dịch hiện tại**, có dữ liệu đủ mới, và nếu dùng thử thách chủ động thì cần challenge duy nhất, thời hạn, quy tắc tiêu thụ và ràng buộc phiên. Tuy nhiên, việc gắn nonce vào telemetry **không làm cho telemetry trở thành chữ ký mật mã**; kẻ tấn công kiểm soát client có thể tạo dữ liệu mới cho nonce mới.

### 8.2. Tại sao yếu tố hành vi không tự bảo vệ khỏi phishing?

Trang phishing có thể lừa người dùng nhập bí mật và đồng thời quan sát cách họ gõ. Kẻ tấn công còn có thể chuyển tiếp tương tác tới hệ thống thật. Vì vậy, phương pháp chống phishing cần cơ chế xác thực **gắn với bên nhận hợp lệ**, như WebAuthn kiểm tra origin và RP ID. Hành vi đóng vai trò phụ trợ, chẳng hạn phát hiện sự khác biệt khi credential bị dùng trên thiết bị khác.

## 9. Sai số và các đại lượng đánh giá

Khi đánh giá mô hình sinh trắc hành vi, cần xem cả tấn công lọt qua lẫn người dùng hợp lệ bị làm khó.

| Đại lượng | Ý nghĩa | Rủi ro khi chỉ tối ưu một phía |
| --- | --- | --- |
| **FAR** (*False Acceptance Rate*) | Tỷ lệ lần thử của kẻ không phù hợp nhưng bị chấp nhận là khớp mẫu | FAR cao khiến đối thủ dễ vượt qua |
| **FRR** (*False Rejection Rate*) | Tỷ lệ lần thử hợp lệ nhưng bị từ chối là không khớp | FRR cao tạo khóa nhầm, tăng hỗ trợ và giảm khả năng tiếp cận |
| **TPR / Recall** khi phát hiện bất thường | Tỷ lệ trường hợp rủi ro thật được phát hiện | Tăng TPR quá mức có thể kéo theo nhiều cảnh báo nhầm |
| **FPR** khi phát hiện bất thường | Tỷ lệ trường hợp bình thường bị báo rủi ro | FPR cao tạo step-up không cần thiết |
| **EER** (*Equal Error Rate*) | Điểm hoạt động mà FAR gần bằng FRR trong một phép thử | Không phải ngưỡng sử dụng tối ưu cho mọi hệ thống thực tế |
| **Coverage/quality** | Bao nhiêu phiên có đủ mẫu đáng tin để đưa ra kết luận? | Bỏ qua nhóm thiếu dữ liệu có thể làm kết quả thử nghiệm quá lạc quan |

Cần phân biệt **FAR/FRR của đối chiếu danh tính** với **precision/recall/FPR của bộ phát hiện gian lận**; định nghĩa nhãn và phép thử khác nhau thì các con số không so sánh trực tiếp.

Ví dụ minh họa: hệ thống thử 1.000 lần tương tác hợp lệ; có 40 lần bị đánh dấu nhầm là bất thường. Khi đó tỷ lệ từ chối nhầm trên tập thử đó là 40 / 1.000 = **4%** nếu quy tắc thực sự từ chối toàn bộ 40 lần. Nếu chỉ tạo cảnh báo rồi yêu cầu step-up, phải báo cáo đúng là **tỷ lệ cảnh báo nhầm**, không gán nhầm thành FRR của toàn bộ luồng đăng nhập. Cần đánh giá đồng thời thời gian xử lý, tỷ lệ step-up thành công và ảnh hưởng tới người dùng.

Để chọn ngưỡng, nhóm kỹ thuật nên:

1. Dùng tập dữ liệu tách riêng để huấn luyện, hiệu chỉnh và đánh giá; tránh mẫu cùng phiên hoặc cùng người rò sang tập kiểm tra khi không phù hợp mục tiêu.
2. Thử theo thiết bị, môi trường, ngôn ngữ bàn phím, người dùng mới và trường hợp dùng công cụ trợ năng.
3. Thử các kiểu gian lận có chủ đích, không chỉ dữ liệu người dùng bình thường.
4. Đo độ trễ, chất lượng telemetry, drift, false positive, false negative và tác động của quyết định tới sản phẩm.
5. Hiệu chỉnh theo rủi ro giao dịch; có giám sát vận hành, rollback và quy trình đánh giá sau sự cố.

Không nên tuyên bố “99% chính xác” nếu không nêu rõ mẫu thử, chỉ số, ngưỡng và bối cảnh. Một mô hình chính xác trên laptop của một nhóm nhỏ có thể hoạt động kém trên điện thoại hoặc với người dùng có nhu cầu hỗ trợ vận động.

## 10. Thiết kế phản ứng khi tín hiệu bất thường

Hành vi bất thường nên dẫn tới **quyết định có mức độ**, không nhất thiết khóa vĩnh viễn.

| Kết quả đánh giá | Phản ứng có thể chọn | Điều kiện cần lưu ý |
| --- | --- | --- |
| Tín hiệu bình thường, credential và phiên hợp lệ | Tiếp tục trong phạm vi quyền hiện có | Vẫn kiểm tra authorization cho mỗi thao tác |
| Tín hiệu thiếu hoặc chất lượng thấp | Áp dụng chính sách xác thực cơ bản; có thể yêu cầu bước phụ cho giao dịch nhạy cảm | Không kết luận người dùng là kẻ gian |
| Bất thường vừa phải | Thêm giám sát, giới hạn tốc độ hoặc yêu cầu xác minh bổ sung | Tránh gây phiền quá mức; xét bối cảnh và lịch sử |
| Bất thường cao, tác vụ nhạy cảm | Step-up bằng phương thức đã phê duyệt; tạm giữ giao dịch nếu cần | Không cho hành vi tốt ở lần kế tiếp tự xóa yêu cầu MFA |
| Có dấu hiệu rõ ràng về chiếm tài khoản | Chặn thao tác nguy hiểm, thu hồi/luân chuyển session theo chính sách, xử lý sự cố | Hỗ trợ khôi phục an toàn và tránh tạo đường vòng chiếm tài khoản |

**Step-up** nên là phép kiểm tra độc lập và phù hợp, ví dụ passkey trên origin hợp lệ hoặc authenticator đã đăng ký theo chính sách. Nếu người dùng không có khả năng thực hiện phương thức đó, cần quy trình hỗ trợ/khôi phục có mức bảo vệ tương ứng, không hạ xuống đường tắt dễ bị lợi dụng.

Hệ thống nên ghi nhận **mã lý do nội bộ** phục vụ vận hành, ví dụ chất lượng mẫu thấp hoặc rủi ro tương tác cao. Thông báo cho client cần vừa đủ để người dùng xử lý; không công bố vector đặc trưng, ngưỡng chi tiết hoặc chiến lược chống gian lận nhạy cảm giúp đối thủ tối ưu hành vi giả.

## 11. Ví dụ triển khai: phiên có đánh giá rủi ro

Giả sử một ứng dụng quản trị hỗ trợ passkey và session cookie. Khi người dùng đã đăng nhập, dịch vụ phân tích nhận các khoảng thời gian thao tác được phép và trả về đánh giá rủi ro. Backend **không** tin một câu trả lời “đã xác thực bằng hành vi” do trình duyệt tự khai.

~~~text
Browser:
    tương tác -> thu thập đặc trưng tối thiểu được cho phép
    -> gửi dữ liệu qua HTTPS với session hiện có

Backend:
    validateSessionAndCSRFProtection()
    verifyTelemetrySchemaAndFreshness()
    rateLimitTelemetryEvents()
    behavioralRisk = evaluateBehavioralSignals()
    risk = combineWithServerObservedContext(behavioralRisk)

    if requestedAction.isSensitive:
        if not session.hasRecentRequiredAuthentication:
            return STEP_UP_REQUIRED

        if risk.isHigh:
            return HOLD_OR_STEP_UP

    return authorizePrincipalForRequestedAction()
~~~

Đây là **pseudocode về thứ tự kiểm soát**, không phải mã production. Nơi nhận telemetry cần áp dụng chính sách thu thập và ngăn spam; không nên lưu nguyên sự kiện quá lâu chỉ vì cần gỡ lỗi. Nếu mô hình rủi ro tạm ngừng hoạt động, sản phẩm cần **fallback an toàn được xác định từ trước**, đặc biệt với thao tác nhạy cảm; không nên mặc nhiên bỏ qua bước bảo vệ bắt buộc.

### 11.1. Những dữ liệu không nên xuất hiện trong telemetry

- Nội dung mật khẩu, mã OTP, recovery code hoặc ký tự người dùng gõ.
- Private key, session token thô, access token, ID token và cookie.
- Toàn bộ nội dung biểu mẫu, trường thông tin nhạy cảm, dữ liệu ghi âm hoặc vị trí liên tục nếu không thật sự cần.
- Dữ liệu hành vi được giữ vô thời hạn và tái sử dụng cho mục đích khác khi chưa có cơ sở phù hợp.

Đặc trưng timing đã xử lý vẫn có thể liên quan đến một cá nhân và có thể nhạy cảm; tránh giả định rằng “không chứa chữ gõ” thì dữ liệu đã hoàn toàn ẩn danh.

## 12. Quyền riêng tư, khả năng tiếp cận và công bằng

Yếu tố hành vi tạo ra một điểm cân bằng khó: đo đủ để tăng bảo mật nhưng không xâm phạm quyền riêng tư hay làm khó người dùng hợp lệ.

**Nguyên tắc thiết kế:**

- **Mục đích rõ ràng:** giải thích cho người dùng khi nào và vì sao hệ thống thu thập mẫu hành vi; xác định cơ sở pháp lý và yêu cầu đồng ý khi áp dụng. Quy định về dữ liệu sinh trắc và quyền riêng tư khác nhau theo khu vực.
- **Tối thiểu dữ liệu:** chỉ trích xuất đặc trưng cần thiết cho mục tiêu; tránh thu nội dung phím, bản ghi màn hình hoặc mẫu giọng nguyên gốc nếu không bắt buộc.
- **Giới hạn lưu trữ:** đặt TTL, quy tắc xóa, phân quyền, mã hóa và khả năng truy xuất/audit; hạn chế chia sẻ với nhà cung cấp hoặc dùng lại ngoài mục đích.
- **Khả năng tiếp cận:** chấn thương, khuyết tật vận động, công cụ hỗ trợ, thay đổi thiết bị hoặc thao tác gián tiếp có thể làm hành vi khác biệt. Cần phương thức xác thực thay thế có mức bảo vệ phù hợp.
- **Công bằng và kiểm soát lỗi:** đánh giá sai số theo các nhóm sử dụng và bối cảnh phù hợp mà không thu thập dữ liệu nhạy cảm ngoài mục đích; thiết lập quy trình khiếu nại, kiểm tra thủ công và sửa sai.
- **Không định danh ngoài phạm vi:** hạn chế dùng mẫu hành vi để theo dõi người dùng xuyên ứng dụng hoặc suy đoán thông tin sức khỏe/tính cách ngoài yêu cầu bảo mật.
- **Giám sát nhà cung cấp:** nếu dùng SDK chống gian lận, cần hiểu dữ liệu họ thu, nơi xử lý, chính sách lưu giữ và khả năng kiểm soát của tổ chức.

Ví dụ, một người đang hồi phục sau chấn thương có thể gõ rất khác trước. Nếu mô hình tự động từ chối mọi lần đăng nhập, người đó bị khóa tài khoản dù credential hợp lệ. Cách xử lý tốt hơn là yêu cầu phương thức xác thực thay thế có thể tiếp cận, sau đó cập nhật profile trên cơ sở dữ liệu đáng tin và có thể kiểm soát.

## 13. Liên hệ với định danh, phiên, token và khôi phục

Các thành phần trong hệ thống xác thực liên kết với nhau nhưng giữ vai trò riêng:

| Thành phần | Vai trò | Yếu tố hành vi có thể đóng góp gì? |
| --- | --- | --- |
| **Identity proofing** | Kiểm chứng claim về chủ thể/thuộc tính | Có thể hỗ trợ phát hiện rủi ro, nhưng không tự chứng minh họ tên hay tư cách pháp lý |
| **Credential enrollment** | Gắn authenticator với principal đã xác định | Hành vi có thể cảnh báo bất thường trước đăng ký mới, không thay quy trình xác minh |
| **Login/MFA** | Xác nhận quyền kiểm soát credential và các yếu tố được yêu cầu | Tăng đánh giá rủi ro hoặc kích hoạt step-up; không tự tạo yếu tố độc lập |
| **Session** | Duy trì trạng thái sau xác thực | Giám sát bất thường trong phiên và yêu cầu tái xác thực khi phù hợp |
| **Token** | Chuyển thông tin xác thực/ủy quyền đến đúng bên nhận | Không biến risk score thành quyền hay bằng chứng ký số; API vẫn xác minh issuer, audience, thời hạn và chính sách |
| **Account linking** | Liên kết định danh nội bộ với IdP bên ngoài | Không gộp tài khoản chỉ vì hành vi giống nhau; phải xác minh identity assertions và sở hữu account |
| **Recovery** | Khôi phục khả năng truy cập khi mất credential | Có thể hỗ trợ chống gian lận, nhưng không hạ yêu cầu bảo vệ của flow phục hồi |

Điều đặc biệt cần tránh là coi mẫu hành vi “quen thuộc” như quyền sở hữu danh tính. Kẻ tấn công có thể kiểm soát thiết bị, chiếm phiên hoặc lấy được dữ liệu mẫu. Việc liên kết danh tính phải dựa vào chứng cứ và quy trình xác minh danh tính phù hợp; quyền truy cập phải dựa vào chính sách authorization.

## 14. Checklist thiết kế và kiểm thử

Dùng các câu hỏi sau khi review một hệ thống dùng behavioral factor:

| Câu hỏi | Tiêu chí đạt |
| --- | --- |
| Tín hiệu đang phục vụ mục tiêu gì? | Phân biệt rõ sinh trắc hành vi, chống bot, phát hiện gian lận và authentication |
| Có coi điểm hành vi là yếu tố MFA độc lập không? | Không tự suy diễn; đánh giá theo chính sách và yêu cầu mức bảo đảm |
| Có bảo vệ luồng đăng nhập nền tảng? | Mật khẩu/passkey/MFA vẫn được xác minh độc lập |
| Đã kiểm tra trust boundary của telemetry chưa? | Dữ liệu client có thể bị giả; có kiểm soát schema, thời gian, phiên, chống abuse |
| Có chống replay và spoofing? | Challenge/session binding khi áp dụng, kiểm soát mẫu trùng và đánh giá đa lớp |
| Dữ liệu dùng xây profile có đáng tin? | Chỉ học từ phiên hợp lệ, có ngăn poisoning, quản lý phiên bản và drift |
| Khi không đủ dữ liệu thì sao? | Có fallback an toàn và khả năng tiếp cận |
| Đã đo các lỗi vận hành? | Theo dõi FAR, FRR, FPR, coverage, tỷ lệ step-up và tỉ lệ hoàn tất |
| Người dùng đổi thiết bị hoặc cách tương tác? | Có phương thức xác thực thay thế, cập nhật mẫu có kiểm soát |
| Tín hiệu hành vi được lưu bao lâu? | Có mục đích, tối thiểu hóa, phân quyền, cơ chế xóa và kiểm toán |
| Có nguy cơ rò rỉ bí mật? | Không ghi nội dung gõ, OTP, token, khóa hoặc dữ liệu thô không cần thiết |
| Phản ứng khi rủi ro cao có nhất quán? | Có step-up, hạn chế hành động/thu hồi phiên theo chính sách và đường hỗ trợ |
| Tín hiệu có bị lạm dụng để định danh chéo không? | Phạm vi xử lý và bên nhận được giới hạn rõ ràng |

### Tình huống tự kiểm tra

**Tình huống 1:** Người dùng nhập đúng mật khẩu, nhịp gõ khớp 99% nhưng hệ thống yêu cầu MFA. Có nên bỏ qua MFA? **Không.** Điểm khớp là đánh giá xác suất; chính sách xác thực vẫn phải được đáp ứng.

**Tình huống 2:** Người dùng dùng bàn phím hỗ trợ mới. Mô hình báo rủi ro cao, trong khi passkey được xác minh hợp lệ. Có nên khóa vĩnh viễn? **Không nên chỉ dựa vào điểm hành vi.** Cần xem chất lượng tín hiệu, bối cảnh, áp dụng step-up phù hợp nếu cần và hỗ trợ cập nhật mẫu tin cậy.

**Tình huống 3:** Kẻ tấn công lấy cookie phiên và mô phỏng mouse path. Hệ thống có được tin rằng phiên an toàn do hành vi khớp? **Không.** Cần phòng chống chiếm phiên, giới hạn quyền và thời hạn, đánh giá giao dịch, yêu cầu xác thực lại ở thao tác nhạy cảm.

**Tình huống 4:** Một nhà cung cấp chống bot muốn ghi lại toàn bộ phím bấm để huấn luyện. Có nên chấp nhận? **Không mặc nhiên.** Cần xem mục đích, tính cần thiết, rủi ro lộ bí mật và quyền riêng tư; thường có thể thiết kế dữ liệu đặc trưng thay cho văn bản người dùng gõ.

## 15. Ghi nhớ

**Yếu tố hành vi** cho biết một tương tác có **phù hợp** với mẫu đã biết hoặc có dấu hiệu rủi ro hay không. Tín hiệu này có ích cho phát hiện bot, đăng nhập bất thường, chiếm phiên và quyết định step-up, nhưng chịu ảnh hưởng bởi thiết bị, môi trường, khả năng vận động và khả năng giả mạo. Nó thường được dùng như **sinh trắc hành vi hoặc tín hiệu đánh giá rủi ro**, không phải một yếu tố MFA thứ tư độc lập mặc định.

Thiết kế vững chắc cần kết hợp credential/passkey/MFA hợp lệ, bảo vệ session/token, kiểm tra quyền tại server, đánh giá mẫu có chất lượng, xử lý replay và giả mạo telemetry, đồng thời bảo vệ dữ liệu cá nhân. Câu hỏi đúng không phải “hành vi có giống 100% không?” mà là: **“Tín hiệu này hỗ trợ kết luận nào, sai số bao nhiêu, thu được qua ranh giới tin cậy nào, và hệ thống sẽ phản ứng an toàn ra sao khi nó bất thường hoặc không có dữ liệu?”**
