# Giới hạn RelayState và ngăn chuyển hướng tới địa chỉ không tin cậy

Trong **SAML 2.0 Web Browser SSO**, Service Provider (SP) gửi `AuthnRequest` tới Identity Provider (IdP), trình duyệt đi qua trang đăng nhập IdP rồi quay lại Assertion Consumer Service (ACS) của SP với `SAMLResponse`. SP thường muốn biết người dùng đang định mở tài nguyên nào trước khi đăng nhập để đưa họ quay về đúng trang. SAML hỗ trợ truyền một giá trị **`RelayState`** đi kèm thông điệp nhằm bảo toàn trạng thái này.

Vấn đề: trình duyệt có thể gửi, sửa hoặc phát lại `RelayState`. Nếu SP diễn giải nó thành URL rồi redirect không kiểm soát, một đường dẫn đăng nhập đáng tin có thể trở thành **open redirect** dẫn tới trang giả mạo. Nếu SP chỉ dựa vào RelayState để quyết định giao dịch thuộc trình duyệt nào, kẻ tấn công còn có thể gây **login CSRF/session swapping**. Vì vậy bài này giải thích đồng thời **giới hạn kích thước**, **bảo vệ tính toàn vẹn và tương quan giao dịch**, và **quy tắc quyết định đích chuyển hướng an toàn** khi tùy chỉnh AuthnRequest trong Spring Security.

## 1. RelayState thực chất là gì?

`RelayState` là **tham số của SAML binding** (ví dụ HTTP-Redirect hoặc HTTP-POST), **không phải** một attribute bên trong `AuthnRequest` hay `Assertion`, **không phải** chữ ký, access token hay chứng cứ xác thực. Nó là dữ liệu do bên khởi tạo giao dịch muốn mang theo qua bước trung gian, thường dùng cho:

- Nhận diện một **pending authentication transaction** đã lưu tại SP.
- Khôi phục ngữ cảnh điều hướng, như trang báo cáo mà người dùng định xem.
- Duy trì một khóa liên hệ ngắn cho các trạng thái ứng dụng đã được lưu an toàn phía server.

Nếu một request có `RelayState` được gửi theo binding hỗ trợ cơ chế này, SAML responder cần dùng binding hỗ trợ RelayState cho phản hồi và **trả lại đúng giá trị đã nhận, không sửa đổi**. Trách nhiệm **diễn giải** giá trị đó và quyết định redirect thuộc về bên nhận theo chính sách của mình.

~~~text
Trình duyệt                SP                       IdP
    |                       |                         |
    | GET /reports          |                         |
    |---------------------->|                         |
    |                       | lưu trạng thái:          |
    |                       |  handle -> /reports     |
    |                       |  session, requestId, TTL |
    |                       |                         |
    |<-- Redirect đến IdP --|                         |
    |    SAMLRequest=...    |                         |
    |    RelayState=H...    |                         |
    |-----------------------------------------------> |
    |                       |                    xác thực
    |<----------------------------------------------- |
    | form POST SAMLResponse=..., RelayState=H...     |
    |                       |                         |
    | POST đến ACS          |                         |
    |---------------------->|                         |
    |                       | xác minh SAMLResponse,  |
    |                       | InResponseTo, phiên,    |
    |                       | rồi tiêu thụ handle     |
    |<--- 302 /reports -----|                         |
~~~

Trong mô hình này, **`H...` chỉ là mã tham chiếu ngẫu nhiên**; URL `/reports` nằm trong trạng thái đã được kiểm tra ở phía SP. Không có URL tùy ý nằm trong RelayState để bên thứ ba thay thế.

### 1.1. RelayState khác InResponseTo và session như thế nào?

| Thành phần | Dùng làm gì? | Không tự bảo đảm điều gì? |
| --- | --- | --- |
| `RelayState` | Mang một giá trị trạng thái/khóa tham chiếu qua IdP rồi về SP. | Không tự xác minh danh tính, không tự chứng minh trình duyệt đã khởi tạo login. |
| `AuthnRequest@ID` | Định danh yêu cầu SP đã tạo. | Không tự cho phép redirect tới một URL. |
| `Response@InResponseTo`, bearer `SubjectConfirmationData@InResponseTo` | Liên hệ response/assertion với AuthnRequest đã phát. | Không thay thế việc gắn pending request với phiên trình duyệt. |
| Session cookie `HttpOnly`/`Secure` của SP | Cho SP biết phiên trình duyệt đang thực hiện callback. | Không thay cho xác minh chữ ký/audience/issuer của SAMLResponse. |
| `SAMLResponse` đã được xác minh | Cho phép SP tin kết quả xác thực và thiết lập principal. | Không cho phép tin mọi đích redirect lấy từ URL/form. |

**Bất biến:** SP chỉ khôi phục đích điều hướng nếu đã **xác minh phản hồi SAML**, **liên kết nó với giao dịch thuộc phiên này**, và **kiểm tra đích đó theo chính sách**. Không dùng `RelayState` thay cho bất kỳ bước nào.

## 2. Giới hạn 80 byte của RelayState

Đặc tả **OASIS SAML 2.0 Bindings**, mục về `RelayState` của **HTTP-Redirect (3.4.3)** và **HTTP-POST (3.5.3)**, đặt giới hạn **MUST NOT exceed 80 bytes**. Đây là **80 byte**, không phải 80 ký tự Unicode, không phải 80 ký tự Java `String.length()`, và không phải giới hạn 80 byte cho toàn bộ SAMLRequest/SAMLResponse.

Ví dụ:

| Giá trị | Độ dài cần quan tâm | Nhận xét |
| --- | --- | --- |
| 24 byte ngẫu nhiên mã hóa **Base64URL không padding** | **32 ký tự ASCII = 32 byte UTF-8**. | Ngắn, khó đoán; phù hợp làm handle. |
| 32 byte ngẫu nhiên mã hóa Base64URL không padding | **43 ký tự ASCII = 43 byte**. | Vẫn nhỏ hơn 80 byte. |
| URL đầy đủ `https://sp.example.org/reports?... ` | Phụ thuộc số byte của cả chuỗi. | Dễ vượt 80 byte, còn có nguy cơ open redirect và rò dữ liệu. |
| Chuỗi chứa dấu tiếng Việt, emoji | Có ký tự nhiều byte trong UTF-8. | `String.length()` không đủ để xác định số byte truyền. |

Trong Java, khi tính độ dài dữ liệu dạng UTF-8, dùng:

~~~java
int bytes = relayState.getBytes(
        java.nio.charset.StandardCharsets.UTF_8).length;
if (bytes > 80) {
    throw new IllegalArgumentException("RelayState vượt 80 byte");
}
~~~

Ví dụ trên chỉ minh họa phép tính độ dài, là **đoạn code bên trong một method**. Khi thực thi một binding cụ thể, còn cần hiểu quy tắc encode/decode trên wire; giới hạn cần được kiểm tra nhất quán trên **giá trị RelayState đã chọn**, không nhầm với độ dài của chuỗi URL-encoded trong cả HTTP query.

**Không dựa vào việc một IdP hiện tại vẫn chấp nhận giá trị dài hơn 80 byte** để coi điều đó là hành vi tương thích chuẩn. Một số sản phẩm có ngoại lệ liên thông, nhưng bên khác có thể cảnh báo, cắt ngắn hoặc từ chối. Để xây dựng SP portable và dễ kiểm thử, hãy giữ RelayState **ngắn hơn giới hạn nhiều**, ví dụ handle Base64URL 32 hoặc 43 byte.

### 2.1. Không đặt cả URL và dữ liệu phiên trong RelayState

Tránh nhét vào RelayState những dữ liệu như:

- Địa chỉ tuyệt đối tới trang người dùng sẽ đến, đặc biệt URL tới host bên thứ ba.
- JSON chứa user ID, tenant, group, quyền, profile, cookie, token, mật khẩu, email hoặc thông tin nhạy cảm.
- Dữ liệu định tuyến rất dài, nhiều query parameters, JWT tự phát dài hoặc toàn bộ saved request.
- Giá trị có thể tiết lộ qua history trình duyệt, log proxy, Referer, bản ghi IdP hoặc hệ thống giám sát.

RelayState đi qua trình duyệt và đối tác, nên **không xem nó là bí mật**. Nếu cần lưu nhiều trường ngữ cảnh, hãy lưu trong server-side session/cache với TTL và chỉ đưa **opaque handle ngẫu nhiên** vào RelayState.

## 3. Bảo vệ tính toàn vẹn: echo chính xác chưa đủ

Theo OASIS Bindings, RelayState **nên được bảo vệ tính toàn vẹn**. Errata làm rõ rằng với **HTTP-Redirect**, khi có chữ ký query-string theo binding, chữ ký có thể bao phủ đúng chuỗi `SAMLRequest` hoặc `SAMLResponse`, `RelayState` và `SigAlg` theo thứ tự quy định. Với **HTTP-POST**, chữ ký XML của SAMLResponse **không mặc nhiên** ký tham số form `RelayState` nằm ngoài XML; cần bảo vệ độc lập phù hợp nếu sử dụng giá trị đó.

Các lựa chọn an toàn phổ biến:

1. **Opaque random handle + trạng thái lưu phía server**: handle đủ ngẫu nhiên, duy nhất theo giao dịch, TTL ngắn, chỉ được sử dụng một lần. Đây là lựa chọn đơn giản và thường dễ kiểm soát nhất.
2. **MAC/chữ ký cho giá trị tự chứa**: nếu buộc truyền dữ liệu trạng thái phía client, dùng MAC/chữ ký từ khóa do SP quản lý, kèm thời hạn, audience/tenant, transaction/session binding và phiên bản format. Sau Base64URL còn phải bảo đảm tổng số byte không vượt giới hạn; dữ liệu nhạy cảm có thể cần mã hóa, nên giải pháp này phức tạp hơn.
3. **Bảo vệ ở lớp binding**: khi dùng HTTP-Redirect ký, xác minh đúng chữ ký query bao gồm RelayState như đặc tả; vẫn phải kiểm tra **đích redirect** và **phiên trình duyệt** riêng.

**Hash đơn thuần không có khóa** không chứng minh nguồn gốc; người tấn công có thể tự tạo hash cho giá trị mới. **HTTPS** bảo vệ đường truyền giữa các chặng nhưng không biến đầu vào do trình duyệt/đối tác gửi thành giá trị đáng tin tuyệt đối. Cũng không nên mặc định rằng một chữ ký SAMLResponse hợp lệ đã bảo vệ giá trị RelayState.

### 3.1. Giới hạn replay

Cùng một handle không được mang lại quyền chuyển hướng hoặc đăng nhập mới vô hạn lần. Trạng thái cần có:

- **Thời điểm tạo và thời hạn**, ví dụ TTL vài phút phù hợp timeout SSO.
- **Session binding**: handle phải thuộc phiên trình duyệt đã khởi tạo AuthnRequest.
- **Request binding**: gắn với ID AuthnRequest, IdP/registration và các giá trị correlation được xác minh trong SAMLResponse.
- **Single use**: tiêu thụ một lần theo thao tác nguyên tử; các callback song song không được cùng thành công.
- **Cleanup**: xóa pending transaction hết hạn để tránh phình cache và rò trạng thái.

Nên sử dụng `Saml2AuthenticationRequestRepository` của Spring Security để bảo toàn liên kết AuthnRequest. **Đừng triển khai cơ chế phân quyền hay xác thực riêng chỉ từ handle**: handle chỉ hỗ trợ quản lý giao dịch và điều hướng.

## 4. Open redirect: vì sao giá trị RelayState nguy hiểm khi biến thành URL?

**Open redirect** xảy ra khi ứng dụng hợp lệ chuyển trình duyệt tới đích do bên ngoài điều khiển mà không có chính sách cho phép. Ví dụ thiết kế sai:

~~~text
GET /saml2/authenticate/corporate?returnUrl=https://attacker.example/phishing

SP đưa returnUrl vào RelayState.
IdP đăng nhập người dùng rồi echo RelayState.
SP sau callback thực hiện:
  sendRedirect(request.getParameter("RelayState"));
~~~

Kẻ tấn công có thể dẫn nạn nhân tới một URL thuộc domain thật của SP để bắt đầu đăng nhập, rồi được chuyển tới trang giả mạo sau khi đăng nhập. Tác hại gồm **phishing**, giảm hiệu quả kiểm tra domain, lạm dụng luồng login, chuyển hướng token/code khi tích hợp sai và làm khó bảo vệ phiên.

**Không dùng `RelayState` trực tiếp làm tham số của `sendRedirect`, `RedirectStrategy.sendRedirect`, `Location` header hay `redirect:` của Spring MVC** khi chưa qua chính sách và xác minh trạng thái.

### 4.1. Những chuỗi cần từ chối khi chỉ cho redirect nội bộ

| Đầu vào chưa tin cậy | Rủi ro |
| --- | --- |
| `https://attacker.example/login` | URL tuyệt đối tới domain khác. |
| `http://attacker.example/` | Đưa người dùng sang site không đáng tin và có thể hạ cấp HTTPS. |
| `//attacker.example/login` | URL *protocol-relative*; trình duyệt dùng scheme hiện tại với host bên ngoài. |
| `javascript:alert(1)` | Scheme có thể dẫn tới thực thi mã trong các bối cảnh xử lý không an toàn. |
| `data:text/html,...` | Scheme dẫn tới tài liệu do kẻ tấn công kiểm soát. |
| `https://trusted.example.attacker.example/` | Kiểm tra host bằng `startsWith("https://trusted.example")` bị qua mặt. |
| `https://trusted.example@attacker.example/` | Dùng `userinfo@` để khiến URL trông giống host tin cậy. |
| `/\\attacker.example/` hoặc `\\attacker.example` | Dấu backslash có thể được browser/proxy diễn giải không nhất quán. |
| `%2f%2fattacker.example` hoặc chuỗi double-encode | Dấu slash được giải mã một hoặc nhiều lần làm thay đổi cách hiểu URL. |
| `/app/../admin` | Chuẩn hóa đường dẫn có thể vượt khỏi phạm vi route cho phép. |
| CR/LF, tab, ký tự điều khiển, `%0d%0a` | Nguy cơ header injection, parser khác nhau hoặc bypass validator. |

Đây là **các họ đầu vào cần chống**, không phải lời khẳng định mọi Java servlet sẽ xử lý chúng giống nhau. Parser của Java, reverse proxy và trình duyệt có thể chuẩn hóa khác nhau, nên **kiểm thử tại điểm redirect thực tế**, sau đúng thứ tự giải mã và chuẩn hóa của hệ thống.

### 4.2. Mô hình cho phép tốt nhất: route ID → đường dẫn nội bộ cố định

Thay vì dùng một URL tùy ý, lưu **route ID** tại server:

| Route ID được chấp nhận | Đường dẫn server tự chọn |
| --- | --- |
| `dashboard` | `/dashboard` |
| `reports` | `/reports` |
| `profile` | `/profile` |
| Bất kỳ giá trị khác | `/dashboard` (fallback an toàn) |

Ưu điểm: **không cần diễn giải URL do người dùng đưa vào**, đồng thời tránh cả việc phân tích hostname và nhập nhằng URL encoding. Khi cần phân trang sâu, lưu **ID tài nguyên đã validate** và tự sinh đường dẫn từ route template an toàn. Ví dụ route `report` và ID số hợp lệ dẫn tới `/reports/42` sau khi kiểm tra authorization của người dùng.

Nếu sản phẩm thật sự phải redirect đến **domain đối tác**, hãy có allowlist **scheme HTTPS, hostname chuẩn hóa, port và đường dẫn đúng mục đích**; so bằng parser URI/URL đáng tin cậy trên thành phần hostname, không bằng `startsWith`, `contains` hoặc suffix đơn giản. Xử lý IDN/punycode, mixed case, dot cuối, credential `@`, backslash và nhiều lần decode theo quy tắc thống nhất. Quyền chuyển sang domain ngoài phải là lựa chọn được quản trị riêng, có thể hiển thị xác nhận; không tự xem mọi URL được đưa vào RelayState là hợp lệ.

## 5. Mô hình thiết kế an toàn cho SP-initiated login

### 5.1. Trước khi chuyển đến IdP

1. Người dùng định vào `/reports`; SP xác định đây là tài nguyên nội bộ hợp lệ và ghi route trong trạng thái phiên **chưa xác thực**.
2. SP tạo `AuthnRequest` với ID duy nhất và chọn một `RelyingPartyRegistration` tin cậy.
3. SP tạo **RelayState ngẫu nhiên** (ví dụ 24 byte ngẫu nhiên → Base64URL 32 ký tự).
4. Lưu bản ghi server-side gồm `handle`, `AuthnRequest ID`, `registrationId`, session browser, route nội bộ, thời điểm hết hạn và cờ đã dùng.
5. SP gửi `AuthnRequest` và RelayState sang IdP bằng binding đã cấu hình. Không đưa URL đích ngoài vào SAMLRequest hoặc RelayState với mục đích tự động redirect.

### 5.2. Khi SAMLResponse trở về ACS

1. Đọc form `SAMLResponse` và RelayState qua bộ xử lý SAML đã cấu hình. **Không cấp phiên chỉ vì có form POST**.
2. Xác minh chữ ký, issuer, `Destination`/ACS, `AudienceRestriction`, Conditions, `SubjectConfirmation`, trạng thái response và chống replay.
3. Với SP-initiated, đối chiếu `InResponseTo` với **AuthnRequest đang chờ của đúng browser session**. Đảm bảo IdP/registration đúng giao dịch.
4. Kiểm tra RelayState theo định dạng, độ dài byte, sự tồn tại của handle, TTL, liên hệ phiên/yêu cầu; **tiêu thụ một lần nguyên tử**.
5. Khi authentication thành công và tài khoản ứng dụng được phép hoạt động, chọn đích từ **route đã lưu, đã được kiểm tra ở phía SP**, không từ tham số callback.
6. Nếu route không hợp lệ, hết hạn hoặc bị thu hồi quyền, redirect tới **đường dẫn fallback cố định cùng origin**, ví dụ `/dashboard`, hoặc trả lỗi/cần đăng nhập lại theo loại lỗi.
7. Áp dụng authorization ở trang đích: `/reports` vẫn cần kiểm tra tenant, role và quyền trên dữ liệu. Một redirect thành công **không chứng minh** quyền xem tài nguyên.

**Thứ tự xác thực quan trọng:** nếu SAMLResponse bị giả mạo hoặc không hợp lệ, **không được sử dụng** RelayState để tạo login thành công hay mở tài nguyên nhạy cảm. Có thể trả về trang lỗi an toàn cố định; không đưa người dùng ra ngoài chỉ vì RelayState chứa URL đẹp.

## 6. Java 17: ví dụ handle ngắn, bind phiên, TTL và redirect allowlist

Ví dụ tự chạy dưới đây mô phỏng **phần quản lý RelayState và return route của SP**, không phải trình xử lý SAML. Nó **không xác minh chữ ký, issuer, audience, `InResponseTo` hoặc tạo Spring Authentication**. Trong ứng dụng thật, chỉ gọi bước khôi phục đích sau khi thư viện SAML xác thực Response, và lấy session ID từ cookie/HttpSession đáng tin cậy chứ **không lấy từ tham số do người dùng gửi**.

Tệp `RelayStateDemo.java`:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.time.Instant;
import java.util.Base64;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

public final class RelayStateDemo {
    private static final SecureRandom RANDOM = new SecureRandom();
    private static final String FALLBACK = "/dashboard";
    private static final ConcurrentMap<String, Pending> STORE =
            new ConcurrentHashMap<>();

    private record Pending(String browserSession, String returnPath,
                           Instant expiresAt) {}

    private static String allowedRoute(String route) {
        if (route == null) {
            return FALLBACK;
        }
        return switch (route) {
            case "reports" -> "/reports";
            case "profile" -> "/profile";
            default -> FALLBACK;
        };
    }

    static String begin(String browserSession, String route, Instant now) {
        byte[] randomBytes = new byte[24];
        RANDOM.nextBytes(randomBytes);
        String handle = Base64.getUrlEncoder()
                .withoutPadding().encodeToString(randomBytes);
        STORE.put(handle, new Pending(
                browserSession, allowedRoute(route), now.plusSeconds(180)));
        return handle;
    }

    static String finish(String browserSession, String relayState,
                         Instant now) {
        if (relayState == null ||
                relayState.getBytes(StandardCharsets.UTF_8).length > 80) {
            return FALLBACK;
        }

        Pending pending = STORE.get(relayState);
        if (pending == null ||
                !pending.browserSession().equals(browserSession) ||
                !now.isBefore(pending.expiresAt())) {
            return FALLBACK;
        }

        // remove(key, value) giúp callback song song chỉ dùng một lần.
        return STORE.remove(relayState, pending)
                ? pending.returnPath()
                : FALLBACK;
    }

    public static void main(String[] args) {
        Instant t0 = Instant.parse("2026-11-07T03:00:00Z");
        String handle = begin("session-A", "reports", t0);

        System.out.println(
                handle.getBytes(StandardCharsets.UTF_8).length);
        System.out.println(finish(
                "session-B", handle, t0.plusSeconds(1)));
        System.out.println(finish(
                "session-A", handle, t0.plusSeconds(2)));
        System.out.println(finish(
                "session-A", handle, t0.plusSeconds(3)));

        String malicious = begin(
                "session-A", "https://attacker.example/", t0);
        System.out.println(finish(
                "session-A", malicious, t0.plusSeconds(4)));

        String expired = begin("session-A", "profile", t0);
        System.out.println(finish(
                "session-A", expired, t0.plusSeconds(181)));
    }
}
~~~

Biên dịch/chạy bằng Java 17 trở lên:

~~~bash
javac RelayStateDemo.java
java RelayStateDemo
~~~

Kết quả **xác định**, không phụ thuộc giá trị ngẫu nhiên cụ thể:

~~~text
32
/dashboard
/reports
/dashboard
/dashboard
/dashboard
~~~

Giải thích từng dòng:

1. 24 byte ngẫu nhiên khi mã hóa Base64URL không padding tạo **32 byte ASCII**, dưới giới hạn SAML 80 byte.
2. Một handle của **session-A** không cho phiên **session-B** lấy route.
3. Lần đầu trong session-A, trước TTL, được lấy `/reports`.
4. Lần dùng lại handle đã bị tiêu thụ trả về fallback.
5. Route không nằm trong allowlist (`https://attacker.example/`) được chuyển thành fallback từ **lúc tạo trạng thái**, không tạo open redirect.
6. Handle hết hạn sau 180 giây không được chấp nhận.

**Giới hạn của demo:** `ConcurrentHashMap` chỉ dùng trong một process và không tự dọn bản ghi hết hạn; production cần cache có TTL/eviction, giới hạn dung lượng, hỗ trợ nhiều node và thao tác tiêu thụ nguyên tử. Demo gắn handle với chuỗi session mô phỏng, nhưng production phải gắn thêm `AuthnRequest ID`, IdP registration, đối chiếu `InResponseTo` và các điều kiện SAML của thư viện. Đồng thời, tránh dùng cùng một ID session duy nhất làm khóa nếu ứng dụng cần hỗ trợ nhiều tab SSO đồng thời; mỗi transaction phải có một handle riêng.

## 7. Cấu hình với Spring Security SAML 2.0

Spring Security Servlet đã có các thành phần để giảm nhu cầu tự quản lý giao dịch:

- **`Saml2WebSsoAuthenticationRequestFilter`**: tạo/gửi AuthnRequest tới IdP.
- **`Saml2AuthenticationRequestResolver`**: xác định cấu hình và dữ liệu AuthnRequest, bao gồm RelayState qua cơ chế resolver tương ứng phiên bản.
- **`Saml2AuthenticationRequestRepository`**: lưu yêu cầu đang chờ. Mặc định thường là **`HttpSessionSaml2AuthenticationRequestRepository`**, cho lợi ích ràng buộc request với trình duyệt.
- **`Saml2WebSsoAuthenticationFilter`** và converter: nhận SAMLResponse và lấy thông tin request/registration để cung cấp cho provider xác thực.
- **OpenSAML authentication provider**: xác minh Response/assertion trước khi cấp `Saml2Authentication`.
- **Authentication success handler**: quyết định người dùng đi đến đâu sau khi xác thực thành công.

### 7.1. Chọn phương án dễ an toàn nhất: giữ mặc định và đích cố định

Nếu nghiệp vụ chỉ cần người dùng quay về dashboard, không có yêu cầu giữ deep link, hãy dùng **success handler với đường dẫn cố định cùng ứng dụng**. Ví dụ cấu hình trong dự án Spring Boot có `spring-security-saml2-service-provider` và IdP registration hợp lệ:

~~~java
package example.federation;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SafeSamlLoginConfig {

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/**", "/error").permitAll()
                .anyRequest().authenticated())
            .saml2Login(saml -> saml.successHandler(
                (request, response, authentication) ->
                    response.sendRedirect(
                        request.getContextPath() + "/dashboard")));
        return http.build();
    }
}
~~~

Đây là **mã cấu hình Spring Boot, không thể `javac` độc lập** nếu thiếu dependencies và registration thực. Cấu hình này chuyển người dùng đã đăng nhập tới `/dashboard` của chính ứng dụng; không lấy `returnUrl`, `RelayState` hoặc `Referer` từ callback để quyết định đích. `/dashboard` vẫn phải có endpoint và kiểm tra authorization phù hợp.

Nếu muốn đưa người dùng về **saved request** ban đầu, có thể giữ cơ chế `SavedRequestAwareAuthenticationSuccessHandler` mặc định khi phù hợp; saved request phải thuộc session đáng tin và cấu hình HTTP host/forwarded headers của proxy phải đúng. Không bật tùy chọn `targetUrlParameter` hoặc `useReferer` bừa bãi: chúng có thể lấy đích từ tham số/header chưa đáng tin.

### 7.2. Tùy chỉnh RelayState tại AuthnRequest resolver

**Ví dụ dành riêng cho Spring Security 6.x với OpenSAML 4** (đối chiếu phiên bản thực tế trước khi dùng). `OpenSaml4AuthenticationRequestResolver` có method **`setRelayStateResolver`** để tự sinh RelayState; ví dụ này chỉ điều chỉnh **cách tạo handle**, không đưa một URL trực tiếp vào tham số.

Tệp `src/main/java/example/federation/SamlRelayStateResolverConfig.java`:

~~~java
package example.federation;

import java.security.SecureRandom;
import java.util.Base64;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.web.DefaultRelyingPartyRegistrationResolver;
import org.springframework.security.saml2.provider.service.web.RelyingPartyRegistrationResolver;
import org.springframework.security.saml2.provider.service.web.authentication.OpenSaml4AuthenticationRequestResolver;
import org.springframework.security.saml2.provider.service.web.authentication.Saml2AuthenticationRequestResolver;

@Configuration
public class SamlRelayStateResolverConfig {

    private static final SecureRandom RANDOM = new SecureRandom();

    @Bean
    Saml2AuthenticationRequestResolver authenticationRequestResolver(
            RelyingPartyRegistrationRepository registrations) {
        RelyingPartyRegistrationResolver relyingParties =
                new DefaultRelyingPartyRegistrationResolver(registrations);
        OpenSaml4AuthenticationRequestResolver resolver =
                new OpenSaml4AuthenticationRequestResolver(relyingParties);

        resolver.setRelayStateResolver(request -> {
            byte[] randomBytes = new byte[24];
            RANDOM.nextBytes(randomBytes);
            return Base64.getUrlEncoder().withoutPadding()
                    .encodeToString(randomBytes);
        });
        return resolver;
    }
}
~~~

`24` byte ngẫu nhiên tương đương 192 bit entropy; giá trị Base64URL không padding có **32 byte ASCII**, phù hợp giới hạn RelayState. Spring Security vẫn cần lưu `AbstractSaml2AuthenticationRequest` bằng repository và xác minh callback tương ứng; **không được suy ra** rằng thay resolver như trên tự triển khai return-path mapping, session binding bổ sung, TTL hay logic redirect tùy biến.

Nếu lưu trạng thái dựa vào handle trong cache riêng, cần nối nó với AuthnRequest trong repository và session/trust model một cách nhất quán. Một **`CacheSaml2AuthenticationRequestRepository` tìm theo RelayState** có thể giúp đa node nhưng làm mất lợi ích ràng buộc với session nếu chỉ lấy lại giao dịch theo handle công khai: Spring Security tài liệu chính thức cảnh báo rủi ro login fixation khi tin vào RelayState/`InResponseTo` mà không biết browser nào yêu cầu login. Phải bổ sung session binding hoặc thiết kế tương đương, không dùng cache tra theo handle làm bằng chứng duy nhất.

**Version note:** ở Spring Security 7.x, tên class/constructor hoặc cách cấu hình OpenSAML có thể khác (ví dụ dùng `OpenSaml5AuthenticationRequestResolver`). Không copy code OpenSAML 4 vào bản mới rồi tự giả định compile được; dùng API chính thức khớp dependency đang triển khai.

### 7.3. Nếu cần redirect trở lại deep link

Một phương án an toàn hơn raw `RelayState` là:

1. Khi bắt đầu SSO, nhận yêu cầu `/reports/42`, kiểm tra rằng đây là **route nội bộ có thể lưu lại**; nếu chứa ID thì validate/encode ID theo kiểu riêng.
2. Lưu route đó trong session hoặc kho pending login thuộc session, kèm `AuthnRequest ID`, registration, TTL và handle.
3. Giữ nguyên `Saml2AuthenticationRequestRepository`/correlation và validator của Spring Security.
4. Sau khi `Saml2Authentication` đã được tạo thành công, success handler chỉ lấy route từ **trạng thái server-side vừa tiêu thụ hợp lệ**.
5. Nếu không có trạng thái hợp lệ hoặc route không còn được cho phép, dùng fallback nội bộ hoặc trả lỗi có chủ đích.
6. Khi người dùng tới trang báo cáo, kiểm tra **authorization** trên report 42 và tenant trước khi hiển thị.

Dù có handle ngẫu nhiên và session hợp lệ, **không chấp nhận return path chưa kiểm tra chỉ vì nó đã được lưu trong session**. Nếu SP trước đó lưu `returnUrl` do attacker gửi vào mà không validate, quá trình “lưu ở server” chỉ trì hoãn open redirect.

## 8. Các bối cảnh đặc biệt

### 8.1. IdP-initiated / unsolicited SSO

Khi IdP chủ động phát SAMLResponse mà SP không tạo AuthnRequest trước, có thể **không có** RelayState do SP khởi tạo hoặc `InResponseTo` để đối chiếu. Nếu sản phẩm hỗ trợ IdP-initiated SSO, phải có chính sách riêng: xác minh đầy đủ chữ ký/issuer/audience/recipient/thời hạn, quyết định có chấp nhận unsolicited login không và chỉ redirect tới **đích cố định/allowlist do SP quản lý**. Không dùng một RelayState chứa URL do IdP/browser cung cấp để cấp quyền điều hướng tùy ý.

Nếu SP-initiated bị lỗi correlation, **không tự động hạ cấp** sang IdP-initiated chỉ để cho login thành công.

### 8.2. Nhiều IdP hoặc nhiều tenant

Mỗi pending login phải biết `registrationId`, entityID IdP, SP entityID, ACS và context tenant đã xác minh. Một handle của IdP A không được dùng để hoàn tất phiên của IdP B hoặc tenant khác. Đừng chọn trust anchor/chứng thư của IdP chỉ vì một chuỗi issuer/tenant trong RelayState chưa xác minh. Khi đổi IdP giữa login, cần một giao dịch SSO mới đúng registration.

### 8.3. Reverse proxy, cookie SameSite và nhiều instance

Khi IdP POST cross-site về ACS, cookie của SP có thể bị chặn theo chính sách `SameSite`. Vấn đề này gây mất pending request trong `HttpSession`. Cần thiết kế cookie/session phù hợp với HTTPS, `Secure`, `HttpOnly`, chính sách `SameSite` và cấu hình reverse proxy đáng tin cậy.

Nếu cache phân tán được dùng, phải giữ **ràng buộc phiên trình duyệt + giao dịch + TTL + single-use** bằng cơ chế đáng tin. Không bỏ xác minh `InResponseTo`/session chỉ vì một callback chạy trên node khác. Khi thành công, tránh redirect tới URL chứa hostname nội bộ hoặc host lấy từ `Host`/forwarded headers không được kiểm soát.

### 8.4. Logging và bảo mật dữ liệu

Chỉ log mã correlation nội bộ (có thể hash/hide bớt), loại lỗi, thời gian, registration đã cấu hình. Không log nguyên `SAMLResponse`, assertion, cookie, secret, route chứa dữ liệu nhạy cảm hoặc toàn bộ RelayState có nhúng thông tin cá nhân. Để điều tra lỗi 80 byte, log **số byte**, loại binding và endpoint đang dùng thay vì in cả chuỗi RelayState.

## 9. Thử nghiệm bảo mật bắt buộc cho RelayState

| Tình huống | Kết quả mong đợi |
| --- | --- |
| Handle 32 byte ASCII, yêu cầu SAML hợp lệ, session và AuthnRequest khớp. | Chấp nhận login và redirect tới route nội bộ đã lưu. |
| RelayState chứa hơn 80 byte. | Từ chối/không sinh giá trị đó trong hệ thống theo chuẩn; thông báo lỗi rõ ràng, không cắt chuỗi tùy tiện. |
| RelayState chứa Unicode, độ dài Java String dưới 80 ký tự nhưng UTF-8 vượt 80 byte. | Kiểm tra theo **byte**, từ chối nếu vượt giới hạn binding. |
| Callback từ session khác với cùng handle. | Không được dùng handle để chuyển hướng/tạo login của phiên khác. |
| Replay lại cùng handle sau khi đã tiêu thụ. | Từ chối và không tái tạo trạng thái. |
| RelayState bị thay 1 ký tự dù SAMLResponse có chữ ký hợp lệ. | Không tìm được trạng thái đáng tin hoặc toàn vẹn thất bại; không dùng như URL. |
| `RelayState=https://attacker.example/`. | Không redirect ra ngoài; fallback hoặc lỗi. |
| `RelayState=//attacker.example/` hoặc `javascript:...`. | Không chấp nhận làm đích redirect. |
| `https://trusted.example.attacker.example/` / URL userinfo `@`. | Không qua được allowlist hostname chính xác. |
| Payload percent-encoded/double-encoded và backslash. | Không bypass validation sau khi browser/proxy chuẩn hóa. |
| RelayState/return URL thiếu hoặc đã hết TTL. | Dùng route fallback an toàn; nếu transaction SAML bị mất thì thất bại xác thực. |
| `InResponseTo` không khớp AuthnRequest trong cùng phiên. | Từ chối login dù RelayState tồn tại. |
| Route `/reports/42` hợp lệ nhưng user không có quyền xem report 42. | Đích có thể được điều hướng tới, nhưng **authorization từ chối xem dữ liệu**. |
| IdP-initiated SSO không có pending request. | Áp dụng chính sách unsolicited riêng; không tin URL ngoài qua RelayState. |

Tách rõ **kiểm thử xác thực** (chữ ký, IdP, audience, InResponseTo, replay), **kiểm thử trạng thái** (byte length, TTL, session, single-use) và **kiểm thử đích redirect** (internal route/allowlist, parser/canonicalization). Passing một nhóm không chứng minh hai nhóm còn lại an toàn.

## 10. Các lỗi thường gặp và cách sửa

| Cách làm sai | Vì sao nguy hiểm | Cách làm đúng |
| --- | --- | --- |
| Gán RelayState bằng URL tuyệt đối do `returnUrl` cung cấp. | Dễ vượt 80 byte và bị open redirect. | Opaque handle; lưu route nội bộ đã cho phép phía server. |
| Dùng `relayState.length() <= 80`. | Số code unit Java không tương đương byte UTF-8. | Đếm byte theo encoding của binding, giữ handle ASCII ngắn. |
| `sendRedirect(request.getParameter("RelayState"))`. | Người dùng có thể tự đổi đích redirect. | Chỉ redirect theo route ID/đích được sinh từ state đáng tin. |
| Dùng `url.startsWith("https://trusted.example")`. | Host giả `trusted.example.attacker.example` có thể vượt qua. | Phân tích và so khớp scheme/host/port chuẩn hóa, hoặc dùng allowlist route nội bộ. |
| Tưởng chữ ký XML bảo vệ cả RelayState. | RelayState nằm ngoài XML; mức bảo vệ phụ thuộc binding/thiết kế. | Bảo vệ toàn vẹn độc lập hoặc opaque handle; xác minh binding signature nếu có. |
| Chỉ tra cache theo RelayState rồi coi browser callback là hợp lệ. | Không biết browser đó có khởi tạo AuthnRequest hay không. | Gắn giao dịch vào session browser, kiểm tra InResponseTo và tiêu thụ một lần. |
| Bỏ xác minh `InResponseTo` vì cookie SameSite bị mất. | Mở đường login CSRF/session swapping. | Sửa session/cookie và correlation store theo yêu cầu SSO. |
| Tin mọi URL `targetUrlParameter`/Referer sau login. | Có thể open redirect hoặc chuyển đến trang không phù hợp. | Success handler cố định, saved request đáng tin hoặc allowlist đã kiểm tra. |
| Cho phép mọi RelayState từ IdP-initiated đăng nhập. | Thiếu giao dịch gốc và dễ bị chuyển hướng ngoài. | Chính sách riêng, redirect cố định/allowlist, giới hạn unsolicited SSO. |
| Lưu token/PII trong RelayState. | RelayState qua trình duyệt, IdP, proxy và log. | Chỉ chuyển handle ngắn; bảo vệ state ở server. |

## 11. Checklist khi tích hợp thực tế

1. **Phạm vi:** xác định RelayState của hệ thống dùng cho correlation, route hay cả hai; không để nó là URL redirect tự do.
2. **Dung lượng:** giữ tối đa 80 byte theo SAML HTTP bindings; ưu tiên handle Base64URL ASCII 32 hoặc 43 byte.
3. **Tính toàn vẹn:** dùng handle ngẫu nhiên gắn server-side state hoặc MAC/chữ ký phù hợp; kiểm tra cơ chế bảo vệ theo Redirect/POST binding.
4. **Phiên:** chứng minh request và response thuộc cùng browser session, registration và `AuthnRequest`; không chỉ tra bằng RelayState.
5. **Vòng đời:** TTL ngắn, tiêu thụ nguyên tử một lần, cleanup, xử lý nhiều tab/nhiều node có kiểm soát.
6. **SAML:** xác minh signature, issuer, status, destination, audience, conditions, subject confirmation, `InResponseTo` và replay.
7. **Redirect:** cho phép route nội bộ cố định hoặc allowlist origin/URI rất hẹp; từ chối URL protocol-relative, scheme lạ, host giả, double-encoding và control chars.
8. **Spring Security:** giữ `Saml2AuthenticationRequestRepository` và OpenSAML validators; chỉ tùy chỉnh resolver/success handler ở điểm mở rộng được hỗ trợ đúng phiên bản.
9. **Authorization:** kiểm tra quyền nghiệp vụ khi truy cập đích, không coi đăng nhập SAML đồng nghĩa quyền với mọi tài nguyên.
10. **Giám sát:** log lý do lỗi và số byte RelayState an toàn, không ghi token/PII; kiểm thử browser thật, cookie SameSite, proxy và IdP khác nhau.

## 12. Tự kiểm tra kiến thức

1. **Giới hạn RelayState là 80 ký tự hay 80 byte?** — **80 byte** theo quy tắc HTTP-Redirect và HTTP-POST của SAML Bindings.
2. **IdP echo RelayState chính xác thì có thể đưa nó thẳng vào HTTP Location không?** — **Không**; echo không xác minh đích redirect hay nguồn gốc phiên.
3. **Base64URL 24 byte ngẫu nhiên tạo giá trị dài bao nhiêu?** — **32 ký tự ASCII/32 byte** khi không padding.
4. **RelayState là một phần của XML Signature trên SAMLResponse không?** — **Không mặc nhiên**; nó là tham số của binding, bảo vệ riêng theo binding/thiết kế.
5. **Chỉ dùng `InResponseTo` hoặc RelayState tra cache có chứng minh callback do cùng browser khởi tạo?** — **Không**; cần session binding hoặc cơ chế chứng minh tương đương.
6. **Đường dẫn `//attacker.example` có phải local path vô hại không?** — **Không**; nó có thể là protocol-relative URL tới host ngoài.
7. **Tại sao nên lưu `reports` thay vì URL tùy ý trong state?** — Vì server có thể ánh xạ route ID sang đường dẫn cố định được phép và tránh open redirect.
8. **SAML login hợp lệ có cho phép xem mọi báo cáo không?** — **Không**; quyền tài nguyên/tenant phải được kiểm tra độc lập.

## Tài liệu tham khảo

- [OASIS — SAML 2.0 Bindings, RelayState (HTTP-Redirect §3.4.3, HTTP-POST §3.5.3)](https://docs.oasis-open.org/security/saml/v2.0/saml-bindings-2.0-os.pdf)
- [OASIS — SAML 2.0 Errata 05, bảo vệ RelayState và cảnh báo URL/CSRF/XSS](https://docs.oasis-open.org/security/saml/v2.0/errata05/os/saml-v2.0-errata05-os.html)
- [OASIS — SAML 2.0 Web Browser SSO Profile](https://docs.oasis-open.org/security/saml/v2.0/saml-profiles-2.0-os.pdf)
- [Spring Security — Producing AuthnRequests, RelayState và AuthenticationRequestRepository](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication-requests.html)
- [Spring Security — Authenticating SAML Responses](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html)
- [Spring Security API 6.3.5 — OpenSaml4AuthenticationRequestResolver.setRelayStateResolver](https://docs.spring.io/spring-security/site/docs/6.3.5/api/org/springframework/security/saml2/provider/service/web/authentication/OpenSaml4AuthenticationRequestResolver.html)
- [Spring Security API — AbstractAuthenticationTargetUrlRequestHandler, kiểm soát redirect target](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/authentication/AbstractAuthenticationTargetUrlRequestHandler.html)
