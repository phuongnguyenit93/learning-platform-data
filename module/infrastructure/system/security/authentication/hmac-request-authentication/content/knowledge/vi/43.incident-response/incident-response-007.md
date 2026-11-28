# Chặn client trong ứng phó sự cố HMAC Request Authentication

## 1. Mục tiêu và bối cảnh

Trong hệ thống xác thực HTTP request bằng **HMAC (Hash-based Message Authentication Code)**, mỗi client sử dụng một shared secret để ký canonical request theo hợp đồng đã thống nhất. Canonical request có thể bao gồm HTTP method, URI, những header được chọn, timestamp, nonce và digest của body. Server kiểm tra chữ ký để xác định request có được ký bằng secret tương ứng và các thành phần đã ký có bị sửa đổi hay không. Timestamp và nonce giúp giới hạn replay; cơ chế phân quyền vẫn phải được thực hiện riêng sau bước xác thực.

Khi một secret bị lộ hoặc một client có hành vi nguy hiểm, đội vận hành cần khả năng **chặn client** để ngăn request mới gây tác động đến hệ thống. Đây là thao tác ứng phó sự cố có phạm vi, thời hạn và cơ chế khôi phục rõ ràng, không đơn thuần là thêm địa chỉ IP vào danh sách cấm.

Sau bài học, người học có thể:

- Phân biệt chặn client, thu hồi khóa HMAC, giới hạn tốc độ và từ chối một thao tác nghiệp vụ.
- Nhận diện tín hiệu đủ tin cậy để chặn, đồng thời tránh chặn nhầm do giả mạo client ID hoặc lỗi canonicalization.
- Thiết kế điểm thực thi chính sách chặn trên gateway, Spring Security và dịch vụ xác thực.
- Thực hiện quy trình phát hiện, cô lập, kiểm tra hiệu lực, cấp lại credential và mở chặn.
- Kiểm thử hành vi trên nhiều instance, proxy/gateway và trong giai đoạn key rotation.

**Tình huống xuyên suốt:** Client tích hợp tên giả định **partner-demo** ký các request bằng HMAC-SHA256. Hệ thống phát hiện nhiều request đã ký hợp lệ đang gọi một API nhạy cảm ngoài mức sử dụng thông thường. Đội ứng phó phải xác minh nguồn tín hiệu, hạn chế tác động, điều tra khả năng lộ secret, rồi quyết định chặn theo client, theo key hoặc theo endpoint.

## 2. "Chặn client" có thể có nhiều nghĩa

Một client có thể sở hữu nhiều khóa đang hoạt động để phục vụ key rotation; nhiều client có thể đi ra cùng một NAT/proxy; một client có thể được phép gọi nhiều API khác nhau. Vì vậy **đối tượng chặn** phải được biểu diễn rõ ràng.

| Biện pháp | Đối tượng bị ảnh hưởng | Trường hợp phù hợp | Giới hạn cần nhớ |
| --- | --- | --- | --- |
| **Thu hồi key HMAC** | Một `keyId` hoặc phiên bản secret | Key đã lộ hoặc cần ngừng sử dụng khẩn cấp | Nếu client có key khác còn hợp lệ, client có thể vẫn gửi request |
| **Chặn client ID** | Toàn bộ credential thuộc một danh tính client đã xác thực | Client bị chiếm quyền, mất khả năng kiểm soát hoặc phải tạm đình chỉ | Ảnh hưởng toàn bộ luồng tích hợp của client đó |
| **Chặn route/quyền** | Một nhóm API hoặc hành động nhất định | Chỉ một chức năng bị lạm dụng, cần giảm phạm vi ảnh hưởng | Không thay thế việc thu hồi key bị lộ |
| **Rate limit / quota** | Client đã xác thực, IP, mạng hoặc route | Tăng tải bất thường, nghi ngờ bot hoặc DoS | Chỉ làm chậm, không chắc chắn ngăn được request có hại |
| **WAF/network block** | IP/CIDR/ASN hoặc dấu hiệu lớp mạng | Flood từ nguồn mạng đã được xác minh | IP có thể dùng chung, thay đổi hoặc bị giả mạo trong header |

Ví dụ, nếu secret của **partner-demo** bị rò rỉ, việc chặn IP máy chủ tích hợp cũ chưa đủ: kẻ tấn công có thể ký request từ IP khác. Cần **thu hồi key bị lộ**; tùy mức độ chắc chắn và ảnh hưởng, chặn luôn client cho đến khi xác minh được chủ sở hữu và cấp lại credential. Ngược lại, nếu chỉ có một endpoint bị gọi quá nhanh nhưng chữ ký vẫn hợp lệ, rate limit hoặc giới hạn quyền tại endpoint có thể là biện pháp tạm thời phù hợp hơn.

Nên định nghĩa các trạng thái độc lập:

- **Credential**: active, rotating, revoked. Một key đã revoked không được chấp nhận lại chỉ vì client được mở chặn.
- **Client**: active, temporarily blocked, suspended. Chính sách client có thể phủ lên mọi key của client đó.
- **Access policy**: quyền đối với route, method hoặc hành động. Đây là **phân quyền**, không phải kết quả xác minh HMAC.

## 3. Khi nào cần chặn và bằng chứng nào đủ mạnh?

Một tỷ lệ lỗi chữ ký cao tự nó chưa chứng minh secret của client bị lộ. Lỗi có thể phát sinh do đồng hồ lệch, thay đổi URL ở reverse proxy, chuẩn hóa query không nhất quán, xử lý body khác nhau hoặc key rotation chưa đồng bộ.

| Tín hiệu | Cách kiểm tra | Hành động ban đầu có thể áp dụng |
| --- | --- | --- |
| Có bằng chứng secret/key đã lộ, hoặc request độc hại với **HMAC hợp lệ** | Đối chiếu key ID đã xác thực, trace, hoạt động nghiệp vụ và thông tin từ chủ sở hữu | Thu hồi key khẩn cấp; chặn client nếu chưa khống chế được toàn bộ credential |
| Nhiều request dùng lại cùng cặp timestamp/nonce và signature | Kiểm tra nonce store, retry từ gateway và khả năng lặp do gửi lại hợp lệ | Từ chối replay, giới hạn nguồn tấn công, điều tra; leo thang nếu xuất hiện tín hiệu chiếm quyền |
| Nhiều HMAC sai nhưng header tự khai một client ID | Xác định key ID/client ID **chưa được xác thực**, kiểm tra địa chỉ nguồn tin cậy và lỗi canonical | Rate limit lớp mạng; **không tự động khóa chủ sở hữu client ID bị khai báo** |
| Request hợp lệ nhưng gọi API ngoài quyền được cấp | Kiểm tra quyền gắn với principal, thay đổi cấu hình và nhật ký `403` | Từ chối theo authorization; đánh giá có cần tạm đình chỉ client hay không |
| Chữ ký sai hàng loạt sau thay đổi gateway | So canonical input ở hai đầu, host/path/query, encoding, body digest, clock skew | Khôi phục hoặc sửa cấu hình proxy; tránh quy kết nhầm là sự cố client |

**Nguyên tắc chống chặn oan:** `clientId`, `keyId`, `X-Forwarded-For` hoặc bất kỳ header nào do request mang đến ban đầu đều có thể bị giả mạo. Một kẻ tấn công có thể gửi hàng nghìn chữ ký sai với `clientId` của đối thủ để cố tình khiến đối thủ bị khóa. Quyết định tự động chặn một danh tính cần dựa trên bằng chứng đã xác thực hoặc quy trình điều tra có kiểm soát.

Ngay cả khi HMAC hợp lệ, điều đó chỉ chứng minh bên gửi **có khả năng sử dụng secret**. Nó không chứng minh request được chủ sở hữu hợp pháp chủ ý gửi; secret có thể đã bị đánh cắp. Do đó phải kết hợp dữ liệu nghiệp vụ, hành vi, lịch sử cấp quyền và phản hồi từ chủ sở hữu khi cần.

## 4. Luồng thực thi chính sách chặn

Hệ thống nên phân tách lớp chặn lưu lượng độc hại, lớp xác thực HMAC, lớp chính sách client và lớp phân quyền. Một luồng tham khảo:

~~~mermaid
flowchart TD
    A[HTTP request đến gateway] --> B{Flood hoặc vi phạm<br/>rate limit lớp mạng?}
    B -- Có --> C[429 hoặc drop tại gateway]
    B -- Không --> D[Đọc keyId và metadata chưa tin cậy]
    D --> E{Key đã bị thu hồi?}
    E -- Có --> F[401 với thông báo chung]
    E -- Không --> G[Xác thực canonical request,<br/>HMAC, timestamp và nonce]
    G -- Thất bại --> H[401; ghi nhận lý do nội bộ]
    G -- Thành công --> I{Chính sách đang chặn<br/>client hoặc key?}
    I -- Có --> J[403; ghi audit sự cố]
    I -- Không --> K[Phân quyền theo route và hành động]
    K --> L{Có quyền?}
    L -- Không --> M[403 theo authorization]
    L -- Có --> N[Xử lý nghiệp vụ]
~~~

Lưu ý khi triển khai:

1. **Tra cứu key bị thu hồi** có thể diễn ra sớm theo `keyId` nhằm loại bỏ request và tiết kiệm tài nguyên. Tuy nhiên `keyId` trước xác thực chỉ là một chỉ dấu tra cứu; kết quả phải trả thông báo lỗi chung, không dùng nó làm bằng chứng quy trách nhiệm cho client.
2. **HMAC verification** phải dùng đúng hợp đồng canonicalization, so sánh MAC theo thời gian không phụ thuộc vào vị trí byte sai, kiểm tra timestamp có giới hạn và dùng thao tác ghi nonce nguyên tử để chống replay. Nonce được ràng buộc với định danh key/client và giữ ít nhất đủ cho cửa sổ chấp nhận timestamp cùng sai lệch đồng hồ đã cho phép.
3. **Client block** nên được kiểm tra dựa trên principal đã xác thực, hoặc dựa trên credential mapping nội bộ có độ tin cậy tương đương. Thực thi trước khi xử lý nghiệp vụ và trước khi phát sinh side effect.
4. **Authorization** tiếp tục chạy với request không bị chặn. HMAC hợp lệ và không thuộc blocklist không đồng nghĩa có quyền thực hiện hành động.
5. **HTTP status** tham khảo: `401 Unauthorized` cho chữ ký/credential không hợp lệ hoặc key bị thu hồi; `403 Forbidden` cho client đã xác thực nhưng đang bị chặn hoặc không đủ quyền; `429 Too Many Requests` cho rate limit. Một số WAF có thể drop request mà không trả HTTP response.

Nếu client đã bị thu hồi key, request có thể bị từ chối `401` trước khi tới bước client block. Vì vậy kiểm thử không nên mặc định mọi request của một client bị đình chỉ đều phải trả cùng một mã. Phản hồi cho phía ngoài cần ít chi tiết, trong khi log nội bộ phải phân biệt được `INVALID_SIGNATURE`, `REPLAY`, `KEY_REVOKED`, `CLIENT_BLOCKED` và `AUTHORIZATION_DENIED`.

### Điểm chặn khi có gateway và nhiều service

Với kiến trúc gateway xác thực tập trung, gateway có thể kiểm tra block policy và chuyển danh tính client đã xác minh cho downstream. Backend chỉ được tin metadata này nếu kênh gateway → backend được bảo vệ (ví dụ mTLS hoặc cơ chế chứng thực nội bộ), và gateway **xóa các header định danh do client bên ngoài tự gửi** trước khi tạo metadata mới. Nếu từng service tự xác thực HMAC thì mọi service phải nhận được chính sách block nhất quán.

Không lấy `X-Forwarded-For` từ request công khai làm danh tính đáng tin; chỉ sử dụng dữ liệu proxy forwarding từ proxy được cấu hình là trusted. Đặc biệt kiểm thử các biến đổi path, percent-encoding, query và body trên đường truyền, vì chúng ảnh hưởng đến canonical request nhưng không được làm vô hiệu hóa cơ chế chặn.

## 5. Runbook: từ phát hiện đến cô lập

### Bước 1 — Ghi nhận sự cố và mức độ ảnh hưởng

Tạo mã incident, xác định thời điểm bắt đầu, client/key/route liên quan, nhóm người trực xử lý và nguồn cảnh báo. Lưu các bằng chứng tối thiểu: request ID, timestamp, key ID, client ID **nếu đã xác thực**, route, kết quả xác thực, trạng thái nonce, mã HTTP, nguồn mạng đã được gateway xác nhận, số request và hậu quả nghiệp vụ.

Không đưa shared secret, Authorization header chứa bí mật, bản sao private credential hoặc toàn bộ body nhạy cảm vào ticket/log. Signature có thể là thông tin nhạy cảm khi kết hợp với request đã ký và timestamp, nên chỉ lưu khi thật sự cần điều tra, được phân quyền truy cập và có chính sách lưu giữ phù hợp.

### Bước 2 — Xác minh chủ thể và phân loại sự cố

Đối chiếu key ID với kho credential, kết quả HMAC verifier, phiên bản key đang được phép sử dụng, cảnh báo từ owner và thay đổi mới ở gateway/SDK. Tách các tình huống:

- **Confirmed compromise**: có bằng chứng key lộ hoặc request hợp lệ mang hành vi chiếm quyền.
- **Suspected abuse**: có hành vi bất thường nhưng chưa xác minh được nguồn.
- **Integration failure**: lỗi ký, canonicalization, clock skew hoặc cấu hình giao tiếp.

Mức độ xác thực của bằng chứng quyết định phạm vi hành động. Một key bị lộ rõ ràng cần thu hồi ngay; số lượng lớn chữ ký sai có thể chỉ cần giới hạn lưu lượng trong thời gian điều tra.

### Bước 3 — Chọn phạm vi và thời gian chặn

Đối với key bị lộ, đặt trạng thái **revoked** ngay trong kho xác thực, vô hiệu mọi bản sao key tương ứng, sau đó quyết định có đình chỉ cả client để ngăn các key khác tiếp tục bị sử dụng hay không. Đối với lạm dụng một chức năng, cân nhắc chặn route hoặc giới hạn quyền với mức tác động nhỏ nhất có thể.

Mỗi block policy nên có tối thiểu: loại đối tượng và định danh, lý do nội bộ, mã incident, người/tác vụ ra quyết định, thời điểm bắt đầu, thời điểm hết hạn hoặc lịch rà soát, phiên bản chính sách và trạng thái hiện hành. Không dùng bản ghi cấm vĩnh viễn không có chủ sở hữu hay cơ chế rà soát.

Ví dụ **dữ liệu minh họa** cho một quyết định chặn tạm thời:

~~~yaml
incidentId: INC-EXAMPLE-001
scope: CLIENT
subjectId: partner-demo
reasonCode: SUSPECTED_CREDENTIAL_ABUSE
state: ACTIVE
createdAt: "2026-11-28T04:00:00Z"
expiresAt: "2026-11-28T05:00:00Z"
decidedBy: security-oncall
policyVersion: 107
~~~

Đây là mô hình của hệ thống quản lý block policy, **không phải metadata YAML của bài học**. Nếu có khóa bị lộ, việc lưu policy `CLIENT` không tự động thay thế thao tác `KEY_REVOKED` trong credential store.

### Bước 4 — Phát lệnh chặn và xác nhận lan truyền

Phát lệnh qua kênh quản trị được xác thực và phân quyền, ghi audit bất biến hoặc chống sửa đổi; tránh thao tác trực tiếp trên từng node mà không có nguồn sự thật chung. Đối với nhiều instance/region:

- Ghi policy vào nguồn dữ liệu tập trung có version hoặc revision.
- Phát sự kiện invalidate cache/đồng bộ trạng thái, hoặc dùng polling với TTL hữu hạn và mục tiêu thời gian cập nhật được định nghĩa.
- Kiểm tra dữ liệu tại gateway và **mọi** verifier/service có thể chấp nhận key hoặc client đó.
- Xem xét kết nối đang mở, request đã vào hàng đợi và job bất đồng bộ; chặn HTTP request mới không tự hủy các tác vụ đã được chấp nhận trước đó.
- Nếu chặn khẩn cấp, cân nhắc tạm dừng luồng ghi hoặc hành động nghiệp vụ rủi ro cao trong thời gian đồng bộ.

Cần phân biệt **thời điểm policy được lưu** với **thời điểm nó thực sự có hiệu lực ở mọi đường xử lý**. Một node còn cache chính sách cũ có thể tiếp nhận request dù bảng điều khiển đã hiển thị client bị chặn. Thiết kế phải xác định rõ giới hạn độ trễ đồng bộ và cách xử lý khi kho policy không sẵn sàng. Với nghiệp vụ rủi ro cao, trạng thái không thể xác minh nên dẫn tới từ chối hoặc giảm quyền theo chính sách đã định; tránh biến một sự cố cache thành sự cố từ chối dịch vụ toàn hệ thống một cách vô ý.

### Bước 5 — Kiểm tra biện pháp chặn và tiếp tục điều tra

Từ môi trường kiểm thử có kiểm soát, gửi request mới được ký hợp lệ bằng key/client đã bị chặn, quan sát từ chối trước khi thực thi nghiệp vụ và xác nhận có audit event. Kiểm tra client khác vẫn hoạt động, route không liên quan vẫn tuân theo policy, và mọi vùng triển khai đã cập nhật.

Tiếp tục điều tra nguồn lộ secret, phạm vi truy cập dữ liệu, hành động đã được thực hiện và khả năng cần rollback hoặc khắc phục dữ liệu. Chặn thành công chỉ cô lập đường truy cập mới; nó không tự đảo ngược giao dịch đã thực hiện.

### Bước 6 — Cấp lại credential và mở chặn có điều kiện

Xác minh chủ sở hữu client qua kênh độc lập. Tạo secret mới bằng bộ sinh ngẫu nhiên mật mã, phân phối qua kênh bí mật được phê duyệt và cập nhật `keyId`. Không tái sử dụng secret đã xác định bị lộ, kể cả sau khi mở chặn. Nếu xoay khóa có giai đoạn chấp nhận song song, **key đã compromised phải bị loại khỏi tập được chấp nhận ngay**, không giữ grace period thông thường cho key đó.

Chỉ mở chặn sau khi nguồn rủi ro đã được xử lý, key mới đã kiểm tra, owner xác nhận khả năng vận hành và có quyết định được ghi nhận. Khôi phục theo từng bước: cho phép một luồng kiểm thử giới hạn, giám sát phản hồi/hoạt động nghiệp vụ, rồi mới phục hồi toàn bộ phạm vi. Block đã hết hạn theo TTL cũng cần tạo sự kiện audit; không mặc nhiên suy ra credential cũ có thể được dùng lại.

## 6. Ví dụ triển khai trong Java và Spring Security

Đoạn dưới đây minh họa một **filter kiểm tra client block sau khi HMAC đã xác thực thành công**, trước bước authorization và controller. Giả định ứng dụng đã có `HmacPrincipal` chứa `clientId()`, `keyId()` từ verifier, cùng `ClientBlockRegistry` truy vấn policy hiện hành. Đây là các kiểu giao diện của ví dụ, cần ánh xạ sang mô hình ứng dụng thật.

~~~java
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;
import java.time.Clock;

public final class HmacClientBlockFilter extends OncePerRequestFilter {
    private final ClientBlockRegistry registry;
    private final Clock clock;

    public HmacClientBlockFilter(ClientBlockRegistry registry, Clock clock) {
        this.registry = registry;
        this.clock = clock;
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {

        Authentication authentication =
                SecurityContextHolder.getContext().getAuthentication();

        // HmacPrincipal phải do HMAC verifier đáng tin cậy tạo ra.
        if (authentication == null
                || !authentication.isAuthenticated()
                || !(authentication.getPrincipal() instanceof HmacPrincipal)) {
            chain.doFilter(request, response);
            return;
        }

        HmacPrincipal principal = (HmacPrincipal) authentication.getPrincipal();
        if (registry.isBlocked(
                principal.clientId(),
                principal.keyId(),
                clock.instant())) {
            // Ghi audit nội bộ: incidentId, traceId, policyVersion, subjectId.
            response.setStatus(HttpServletResponse.SC_FORBIDDEN);
            response.setHeader("Cache-Control", "no-store");
            response.setContentType("application/problem+json;charset=UTF-8");
            response.getWriter().write(
                    "{\"title\":\"Access denied\",\"status\":403}");
            return;
        }

        chain.doFilter(request, response);
    }
}
~~~

Trong cấu hình Spring Security, phải bảo đảm thứ tự: **HMAC authentication → client block filter → authorization**. Một filter chạy trước khi có principal đã xác thực sẽ không thể kiểm tra client ID một cách đáng tin cậy. Ứng dụng dùng Spring WebFlux cần cách triển khai tương đương qua `WebFilter` và reactive context, không áp dụng trực tiếp `OncePerRequestFilter` của Servlet.

Các phần cần hiện thực bên ngoài ví dụ:

- Registry kiểm tra được cả phạm vi `CLIENT` và `KEY`, trạng thái `ACTIVE`, expiry và phiên bản policy; có quy tắc rõ ràng khi datastore/cache lỗi.
- HMAC verifier từ chối `KEY_REVOKED` trước khi tạo authenticated principal; khống chế replay bằng nonce store nguyên tử và ký đúng canonical contract.
- Audit được phát ra ở nhánh block nhưng không lưu secret, body nhạy cảm hoặc signature thô.
- Endpoint quản trị policy có authentication, authorization, audit và kiểm soát cạnh tranh khi đồng thời có lệnh block/unblock.

Ví dụ không triển khai toàn bộ verifier vì thuật toán canonicalization phải được ràng buộc bởi hợp đồng ký cụ thể của module. Kiểm tra MAC thành công không thay thế logic kiểm soát quyền của Spring Security.

## 7. Tính nhất quán, key rotation và chống bypass

**Key rotation:** Một client có thể có key cũ và key mới cùng hoạt động trong giai đoạn chuyển đổi bình thường. Block theo `KEY` chỉ cấm một key cụ thể; block theo `CLIENT` phải áp dụng cho cả hai key. Nếu key cũ đã lộ, cần thu hồi key đó ngay, bất kể cửa sổ overlap còn thời gian. Tránh dùng `keyId` trùng hoặc tái sử dụng để ngăn chính sách cũ bị hiểu nhầm sau rotation.

**Chính sách theo thời gian:** So sánh thời điểm hiệu lực và hết hạn bằng clock được chuẩn hóa (UTC), kiểm thử lệch đồng hồ và đổi phiên bản policy theo thứ tự nhất quán. Nếu cache miss rồi truy vấn nguồn trung tâm, phải có timeout và cách xử lý lỗi. Những node đã nhận revision mới không được ghi đè bằng sự kiện cũ đến muộn.

**Cạnh tranh block/unblock:** Một lệnh unblock dựa trên incident đã cũ không được vô hiệu hóa block mới hơn cho cùng client. Có thể sử dụng version check hoặc compare-and-set, đồng thời ghi người phê duyệt, lý do và sự kiện chuyển trạng thái. Nếu có nhiều incident độc lập, một client chỉ trở lại hoạt động khi **mọi chính sách block còn hiệu lực** cho client đó đã được gỡ/hết hạn.

**Bypass qua kiến trúc:** Đối chiếu tất cả đường vào như API gateway công khai, internal ingress, endpoint cũ và consumer xử lý tác vụ bất đồng bộ. Một đường bypass không xác thực lại principal hoặc không nhận policy sẽ làm biện pháp chặn mất hiệu lực. Nếu downstream chỉ tin header do gateway tạo, bảo vệ chặt kết nối nội bộ và không chấp nhận header giả từ Internet.

**Khả năng quan sát:** Nên theo dõi số request bị từ chối theo nhóm lý do, số block policy active, độ trễ lan truyền, tỷ lệ lỗi xác thực, số replay và số request vẫn được tiếp nhận sau mốc policy có hiệu lực. Với metrics, tránh đưa client ID/key ID vào label có cardinality cao; lưu định danh đã kiểm soát trong audit/log truy cập hạn chế và tương quan bằng trace ID. Alert khi có request **đã xác thực và được xử lý nghiệp vụ** sau khi block đáng lẽ có hiệu lực.

## 8. Bảng kiểm thử các trường hợp bắt buộc

| Ca kiểm thử | Đầu vào | Kết quả mong đợi |
| --- | --- | --- |
| Client bình thường | HMAC hợp lệ, timestamp/nonce mới, client active, có quyền | Request qua authentication, block check và authorization |
| Client bị block | HMAC hợp lệ, nonce mới, policy `CLIENT` active | `403`, không chạy logic nghiệp vụ, có audit |
| Một key bị revoked | Request ký bằng key đã thu hồi | `401`, kể cả khi client có key mới vẫn active |
| Nhiều key của client | Client có key A và B; block theo client | Cả A và B đều bị từ chối |
| Chặn riêng key A | Key A revoked, key B active, client không bị block | A bị từ chối; B có thể tiếp tục sau các kiểm tra còn lại |
| Replay | Gửi lại timestamp/nonce/signature đã được sử dụng | Verifier từ chối theo chính sách replay; không thực hiện side effect lần hai |
| Giả mạo client ID | Hàng loạt request ký sai, tự khai client ID của client tốt | Không tự động đình chỉ client tốt chỉ dựa vào header khai báo |
| Gateway biến đổi URI/body | Cấu hình proxy tạo canonical input khác đầu gửi | Báo lỗi xác thực và xác định nguyên nhân; không kết luận tự động credential bị lộ |
| Policy lan truyền đa vùng | Chặn ở nguồn policy, gửi request đến từng instance/region | Tất cả instance từ chối trong giới hạn thời gian đã cam kết |
| Hết hạn/gỡ block | Policy không còn active nhưng key vẫn revoked | Client hết block; key revoked vẫn không được dùng lại |
| Race block/unblock | Sự kiện version thấp đến sau version cao | Trạng thái mới không bị ghi đè; còn block độc lập thì vẫn từ chối |
| Phân quyền | HMAC hợp lệ, client không block, thiếu quyền route | `403` theo authorization; reason nội bộ phân biệt với block |
| Rate limit | Vượt quota của client/nguồn theo cấu hình | `429` hoặc kết quả của WAF tương ứng, không tự ý revoke credential |

Khi thực hiện kiểm thử end-to-end, kiểm tra cả **không có side effect**: không phát sinh giao dịch, không ghi dữ liệu, không enqueue job sau khi request đáng lẽ đã bị chặn. Ngoài mã HTTP, xác nhận audit có đúng incident/policy version và không rò thông tin nhạy cảm trong response.

## 9. Sai lầm thường gặp và cách tránh

1. **Khóa client dựa trên header chưa xác thực.** Kẻ tấn công giả mạo định danh khiến đối thủ bị khóa. Chỉ quy trách nhiệm cho principal đã xác thực hoặc bằng chứng độc lập.
2. **Chỉ chặn IP khi secret bị lộ.** Secret vẫn ký được từ mạng khác. Thu hồi key tại nguồn xác thực và xác nhận mọi verifier không còn chấp nhận.
3. **Chặn ở API gateway nhưng bỏ quên đường nội bộ.** Endpoint trực tiếp hoặc consumer có thể tiếp tục xử lý. Kiểm kê toàn bộ ingress và nơi thực thi nghiệp vụ.
4. **Xem kết quả HMAC là quyền truy cập.** Request đã ký hợp lệ vẫn có thể vượt quyền hoặc gây tác hại. Chạy authorization sau authentication và block check.
5. **Cache blocklist quá lâu hoặc fail-open không kiểm soát.** Node nhận policy chậm tạo cửa sổ bypass. Đặt mục tiêu propagation, version, invalidation và chiến lược xử lý datastore lỗi theo mức rủi ro.
6. **Mở chặn đồng thời kích hoạt key cũ.** Mở client policy không được tự động phục hồi key đã thu hồi. Credential mới phải được cấp riêng sau xác minh.
7. **Coi mọi request replay là tấn công có chủ ý.** Retry do lỗi mạng hoặc proxy có thể tái gửi request. Vẫn từ chối replay theo hợp đồng, nhưng điều tra tín hiệu trước khi khóa cả client.

## 10. Checklist cho ca trực incident response

- [ ] Incident có chủ sở hữu, mức độ ưu tiên, phạm vi dữ liệu và bằng chứng tối thiểu.
- [ ] Đã tách client/key ID được xác thực với các giá trị do request tự khai báo.
- [ ] Đã chọn phạm vi chặn theo `KEY`, `CLIENT`, `ROUTE` hoặc nguồn mạng và nêu rõ lý do.
- [ ] Nếu nghi lộ secret, đã thu hồi key có nguy cơ, không giữ grace period cho key compromised.
- [ ] Policy có thời điểm hiệu lực, hạn kết thúc/rà soát, version, actor và audit.
- [ ] Đã xác nhận policy tại gateway, verifier, service và các region; đánh giá request/job đang chạy.
- [ ] Đã kiểm thử request hợp lệ bị chặn, request bình thường không bị ảnh hưởng và không phát sinh side effect.
- [ ] Đã kiểm tra khả năng chặn nhầm do canonical request, timestamp, nonce và proxy.
- [ ] Khi khôi phục, đã xác minh owner, cấp key an toàn, thực hiện unblock có kiểm soát và giám sát tái phát.

Chặn client hiệu quả đòi hỏi **đúng danh tính, đúng phạm vi và đúng thời điểm có hiệu lực**. Trong kiến trúc HMAC, biện pháp này phải đi cùng thu hồi shared secret, bảo vệ khỏi replay, quản trị key rotation, quan sát được trạng thái đa vùng và phân quyền tách biệt; khi đó đội vận hành mới có thể cô lập sự cố mà vẫn duy trì khả năng khôi phục an toàn cho client hợp pháp.
