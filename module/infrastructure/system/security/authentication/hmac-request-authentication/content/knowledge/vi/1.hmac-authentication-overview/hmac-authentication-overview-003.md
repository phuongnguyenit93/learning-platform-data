# Client ký HTTP request bằng HMAC

Trong cơ chế **HMAC request authentication**, client và server cùng nắm giữ một **shared secret**. Client dùng secret để tạo mã xác thực cho một biểu diễn xác định của HTTP request (canonical request). Server tự tính lại mã đó và đối chiếu, qua đó xác thực rằng request đến từ bên có khả năng sử dụng secret và những thành phần được ký không bị sửa đổi sau khi ký.

Bài này thuộc phần **Tổng quan HMAC request auth**, tập trung vào việc **client ký request**: chuẩn bị dữ liệu, tạo canonical request, tính HMAC, gắn chữ ký vào header và gửi đúng các byte đã ký. Quy trình còn đặt nền tảng để server xác minh chữ ký, chống replay bằng timestamp/nonce, thay khóa và kiểm thử khi đi qua proxy hoặc gateway.

Sau bài học, người học có thể:

- Phân biệt body hash, canonical request và HMAC signature; biết thành phần nào phải được hai bên thống nhất.
- Viết client Java ký một HTTP request bằng HMAC-SHA256 với secret được cấu hình bên ngoài mã nguồn.
- Xử lý timestamp, nonce, key ID và request retry theo các yêu cầu chống replay.
- Phát hiện lỗi thường gặp khi URI, header hoặc body thay đổi giữa thời điểm ký và thời điểm truyền.
- Phân biệt xác thực request với kiểm tra quyền thực hiện thao tác.

## 1. Client thực sự ký những gì?

Một HTTP request có nhiều thành phần: method, URI, header và body. HMAC không tự biết phần nào trong số đó phải được bảo vệ. **Client và server phải thống nhất một hợp đồng ký (signing contract)**: trường nào được ký, cách chuyển chúng thành byte, thuật toán và cách truyền chữ ký.

Ví dụ, client muốn gửi:

~~~http
POST /v1/payments?currency=VND&dryRun=true HTTP/1.1
Host: api.example.test
Content-Type: application/json

{"orderId":"ord-123","amount":50000}
~~~

Ta sẽ dùng hợp đồng ký **minh họa**, không coi đây là định dạng chuẩn chung của mọi hệ thống HMAC. Trong một API thực, phải triển khai đúng hợp đồng mà bên cung cấp công bố; đổi thứ tự trường hoặc cách chuẩn hóa dù chỉ một byte cũng có thể khiến chữ ký không khớp.

| Thành phần | Giá trị trong ví dụ | Quy tắc ký |
| --- | --- | --- |
| HTTP method | POST | Chữ hoa ASCII. |
| Request target | /v1/payments?currency=VND&dryRun=true | Ghép raw path và raw query đúng như request được gửi, không gồm scheme, host hay fragment. |
| X-Client-Id | partner-42 | Định danh client; không phải secret. |
| X-Key-Id | k-2026-11 | Phiên bản secret server cần dùng để xác minh. |
| X-Timestamp | Unix time tính bằng giây | Chuỗi số thập phân; đồng hồ client phải đủ chính xác. |
| X-Nonce | 16 byte ngẫu nhiên mã hóa hex | Giá trị mới cho từng lần gửi đã ký, giúp phát hiện request phát lại. |
| Content-Type | application/json | Trong ví dụ này phải có đúng giá trị đó, không tự thêm charset. |
| X-Content-SHA256 | SHA-256 của body bytes, mã hóa hex chữ thường | Ràng buộc toàn bộ body vào chữ ký. |
| X-Signature | Base64 của HMAC-SHA256 | Gửi kèm request, **không** tự đưa trường chữ ký vào dữ liệu được ký. |

Hợp đồng còn phải quy định **đúng thứ tự** các dòng canonical, ký tự phân tách và cách mã hóa. Ở đây:

~~~text
POST
/v1/payments?currency=VND&dryRun=true
x-client-id:partner-42
x-key-id:k-2026-11
x-timestamp:<unix-seconds>
x-nonce:<32-hex-characters>
content-type:application/json
x-content-sha256:<64-hex-characters>
~~~

Quy tắc biểu diễn chính xác:

1. Mỗi dòng theo đúng thứ tự trên, nối bằng ký tự LF (byte 0A), **không có LF ở cuối**.
2. Tên header trong canonical dùng chữ thường như mẫu. Giá trị header dùng đúng giá trị client gửi; ví dụ giới hạn giá trị không có khoảng trắng thừa, CR hay LF. Không được tự thêm dấu cách sau dấu hai chấm.
3. Tất cả dữ liệu canonical được mã hóa UTF-8 trước khi tính HMAC.
4. Raw path bắt đầu bằng dấu gạch chéo; nếu URI không có path thì dùng dấu gạch chéo đơn. Raw query được giữ nguyên thứ tự, dấu phân tách, percent-encoding và cả các tham số trùng tên; query rỗng nhưng có dấu hỏi vẫn giữ dấu hỏi. Không tự sắp xếp tham số hay giải mã rồi mã hóa lại.
5. Body hash là hex chữ thường của SHA-256 tính trên **byte thực gửi qua HTTP**. Với body rỗng vẫn tính SHA-256 của mảng byte rỗng, không dùng chuỗi rỗng thay cho giá trị hash.
6. Chữ ký được mã hóa Base64 chuẩn (có padding theo quy tắc Base64), không phải Base64URL; secret được đọc dưới dạng byte từ cấu hình Base64, không dùng trực tiếp các ký tự Base64 làm key.

Nếu hệ thống yêu cầu ký hostname, audience, tenant, idempotency key hoặc các header khác thì **phải thêm chúng vào hợp đồng ở cả client lẫn server**. Trong mẫu này, server phải ràng buộc mỗi client/key với dịch vụ và phạm vi endpoint được phép sử dụng; không được tùy tiện dùng chung secret cho nhiều dịch vụ với quyền khác nhau.

## 2. Trình tự client tạo chữ ký

~~~mermaid
flowchart TD
    A["Tạo method, URI và body bytes"] --> B["Đọc client ID, key ID, shared secret"]
    B --> C["Lấy timestamp và tạo nonce ngẫu nhiên"]
    C --> D["Tính SHA-256(body bytes)"]
    D --> E["Dựng canonical request đúng hợp đồng"]
    E --> F["Tính HMAC-SHA256(secret, UTF-8 canonical)"]
    F --> G["Mã hóa chữ ký Base64"]
    G --> H["Gắn header và gửi cùng body bytes đã ký"]
~~~

Về mặt toán học:

~~~text
bodyHash  = lowerHex(SHA256(bodyBytes))
canonical = method + "\n" + requestTarget + "\n" + ... + "x-content-sha256:" + bodyHash
signature = Base64(HMAC_SHA256(secretBytes, UTF8(canonical)))
~~~

**SHA-256(body)** chỉ là một giá trị kiểm tra nội dung công khai; bất kỳ ai cũng tính được nó. Yếu tố chứng minh quyền sở hữu secret là **HMAC trên toàn bộ canonical request**, trong đó có body hash. Nếu chỉ gửi body hash mà không đưa nó vào dữ liệu được HMAC bảo vệ thì kẻ tấn công có thể sửa cả body lẫn hash.

Nên tạo hoặc serialize body **một lần** thành byte array, sau đó dùng cùng byte array cho bước hash và bước gửi. Nếu ký JSON compact nhưng HTTP client gửi JSON được format lại, hoặc một interceptor nén/thay đổi body sau khi ký, chữ ký có thể sai.

## 3. Ví dụ client hoàn chỉnh với Java 17+

Ví dụ dưới đây dùng Java HttpClient và các API sẵn có trong JDK. Đây là ví dụ client-to-server: server và client đã thống nhất hợp đồng ở mục 1. Biến môi trường **HMAC_SHARED_SECRET_B64** chứa Base64 của secret ngẫu nhiên có ít nhất 32 byte; **HMAC_KEY_ID** chứa key ID mà server đã cấp. Không đặt secret thật trong source code, commit, log hay request header.

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.time.Instant;
import java.util.Base64;
import java.util.HexFormat;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class HmacRequestClient {
    private static final String CONTENT_TYPE = "application/json";
    private static final SecureRandom RANDOM = new SecureRandom();

    public static void main(String[] args) throws Exception {
        URI uri = URI.create(
            "https://api.example.test/v1/payments?currency=VND&dryRun=true"
        );
        byte[] body = "{\"orderId\":\"ord-123\",\"amount\":50000}"
            .getBytes(StandardCharsets.UTF_8);

        String clientId = "partner-42";
        String keyId = requiredEnv("HMAC_KEY_ID");
        byte[] secret = Base64.getDecoder().decode(
            requiredEnv("HMAC_SHARED_SECRET_B64")
        );
        if (secret.length < 32) {
            throw new IllegalArgumentException("Secret phải có ít nhất 32 byte");
        }

        String timestamp = Long.toString(Instant.now().getEpochSecond());
        String nonce = newNonce();
        String bodyHash = sha256Hex(body);

        String canonical = String.join("\n",
            "POST",
            rawTarget(uri),
            "x-client-id:" + clientId,
            "x-key-id:" + keyId,
            "x-timestamp:" + timestamp,
            "x-nonce:" + nonce,
            "content-type:" + CONTENT_TYPE,
            "x-content-sha256:" + bodyHash
        );
        String signature = hmacBase64(secret, canonical);

        HttpRequest request = HttpRequest.newBuilder(uri)
            .header("Content-Type", CONTENT_TYPE)
            .header("X-Client-Id", clientId)
            .header("X-Key-Id", keyId)
            .header("X-Timestamp", timestamp)
            .header("X-Nonce", nonce)
            .header("X-Content-SHA256", bodyHash)
            .header("X-Signature", signature)
            .POST(HttpRequest.BodyPublishers.ofByteArray(body))
            .build();

        HttpClient httpClient = HttpClient.newHttpClient();
        HttpResponse<String> response = httpClient.send(
            request,
            HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8)
        );
        System.out.println("HTTP status: " + response.statusCode());
    }

    // Raw path và raw query phải khớp request target mà server nhận.
    private static String rawTarget(URI uri) {
        if (uri.getRawFragment() != null) {
            throw new IllegalArgumentException("URI không được có fragment");
        }
        String path = uri.getRawPath();
        if (path == null || path.isEmpty()) {
            path = "/";
        }
        String query = uri.getRawQuery();
        return path + (query == null ? "" : "?" + query);
    }

    private static String sha256Hex(byte[] bytes)
            throws GeneralSecurityException {
        byte[] digest = MessageDigest.getInstance("SHA-256").digest(bytes);
        return HexFormat.of().formatHex(digest);
    }

    private static String hmacBase64(byte[] secret, String canonical)
            throws GeneralSecurityException {
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(secret, "HmacSHA256"));
        byte[] signature = mac.doFinal(
            canonical.getBytes(StandardCharsets.UTF_8)
        );
        return Base64.getEncoder().encodeToString(signature);
    }

    // 128 bit ngẫu nhiên; mã hóa thành 32 ký tự hex chữ thường.
    private static String newNonce() {
        byte[] nonce = new byte[16];
        RANDOM.nextBytes(nonce);
        return HexFormat.of().formatHex(nonce);
    }

    private static String requiredEnv(String name) {
        String value = System.getenv(name);
        if (value == null || value.isBlank()) {
            throw new IllegalStateException("Thiếu biến môi trường: " + name);
        }
        return value;
    }
}
~~~

**Điểm cần kiểm tra khi tích hợp:** Java URI cho phép lấy raw path và raw query, nhưng nhiều HTTP stack, thư viện ký, proxy hoặc gateway có thể chuẩn hóa URL ở bước khác. Phải kiểm thử rằng request target dùng để ký thực sự trùng với request target mà server dựng lại khi xác minh. Java HttpClient có thể sử dụng HTTP/2; ở HTTP/2, gateway nhận method và path qua pseudo-header thay vì dòng request HTTP/1.1, nhưng ý nghĩa canonical vẫn phải nhất quán.

Để đổi sang GET hoặc PUT, không chỉ thay method ở HttpRequest: phải đổi method trong canonical và dùng đúng body bytes tương ứng. Với GET không có body, hash được tính từ byte array rỗng. Nếu có middleware tự gắn hoặc sửa một header **đã nằm trong danh sách được ký**, cần chạy bước ký sau khi header đó có giá trị cuối cùng hoặc ngăn middleware sửa nó.

### Ví dụ request sau khi ký

Các giá trị có dấu ngoặc nhọn bên dưới chỉ là ký hiệu minh họa, không phải chữ ký tính sẵn:

~~~http
POST /v1/payments?currency=VND&dryRun=true HTTP/1.1
Host: api.example.test
Content-Type: application/json
X-Client-Id: partner-42
X-Key-Id: k-2026-11
X-Timestamp: {epoch-seconds}
X-Nonce: {32-lowercase-hex-chars}
X-Content-SHA256: {64-lowercase-hex-chars}
X-Signature: {base64-hmac-signature}

{"orderId":"ord-123","amount":50000}
~~~

**Client không gửi shared secret.** X-Key-Id giúp server chọn secret, X-Timestamp và X-Nonce tham gia chính sách chống replay, còn X-Signature mang kết quả MAC. Việc gửi chữ ký qua header chỉ có ý nghĩa khi server cũng xác minh từng trường theo cùng hợp đồng.

## 4. Timestamp, nonce và xử lý retry

Chữ ký HMAC hợp lệ có thể bị chụp lại và gửi nhiều lần nếu server không có cơ chế chống replay. HMAC tự nó không chứng minh request là mới.

- **Timestamp:** Client ghi thời điểm ký dưới dạng epoch seconds. Ví dụ server chỉ chấp nhận request có sai lệch trong khoảng ±300 giây so với thời gian server; con số này là chính sách của ứng dụng, không phải quy định của HMAC. Client cần đồng bộ đồng hồ qua nguồn thời gian tin cậy và tạo timestamp sát thời điểm gửi.
- **Nonce:** Client tạo ít nhất 128 bit ngẫu nhiên bằng SecureRandom cho **mỗi request mới được ký**; không dùng số đếm dễ đoán, timestamp đơn lẻ hay hàm random không dành cho bảo mật. Server lưu dấu nonce đã chấp nhận trong phạm vi client/key, với thời gian lưu ít nhất đủ bao phủ cửa sổ timestamp và độ lệch đồng hồ cho phép.
- **Kiểm tra ở server:** Chỉ sau khi xác minh HMAC hợp lệ, server mới ghi nhận nonce bằng thao tác nguyên tử kiểu insert-if-absent trước khi thực hiện nghiệp vụ. Hai request đồng thời dùng cùng nonce chỉ được một request vượt qua bước chống replay. Kiểm tra nonce trên từng instance bằng một map cục bộ là không đủ nếu hệ thống chạy nhiều replica.
- **Retry:** Với một lần gọi lại, client nên lấy timestamp/nonce mới và ký lại. Nếu request đầu đã được xử lý nhưng response bị mất, request ký lại vẫn có thể tạo tác dụng phụ nghiệp vụ; cần cơ chế **idempotency key** được server thực thi. Với API có idempotency key, hợp đồng nên đưa key đó vào phần được ký để tránh bị thay đổi trên đường truyền.

Hệ thống có thể có chính sách retry khác, nhưng phải thiết kế đồng bộ với nonce store và idempotency ở server. Đừng giả định tự động retry của HTTP client luôn an toàn cho thao tác tạo giao dịch.

## 5. Server xác minh chữ ký theo cùng hợp đồng

Hiểu luồng server giúp client chẩn đoán lỗi chính xác. Một trình tự xác minh tham khảo:

1. Áp dụng giới hạn kích thước request, kiểm tra cấu trúc và sự hiện diện của các header bắt buộc; bác bỏ header trùng hoặc mơ hồ theo chính sách hợp đồng.
2. Từ client ID và key ID, lấy **đúng secret** đang có hiệu lực và ràng buộc với dịch vụ/đối tượng gọi; không dùng key ID do client khai báo để truy cập file hoặc cấu hình tùy ý.
3. Kiểm tra định dạng timestamp, nonce, body hash và chữ ký; bảo đảm timestamp nằm trong cửa sổ hợp lệ.
4. Tính SHA-256 từ đúng body bytes được server xác minh; so sánh với X-Content-SHA256 và dựng lại canonical request từ method, request target, các header đã nhận và body hash.
5. Tính HMAC-SHA256 bằng secret vừa chọn, giải mã X-Signature từ Base64, rồi so sánh **byte chữ ký** bằng phép so sánh thời gian hằng tương đối, ví dụ MessageDigest.isEqual trong Java. Không dùng so sánh chuỗi thông thường để kiểm tra MAC.
6. Sau khi chữ ký hợp lệ, kiểm tra/lưu nonce bằng thao tác nguyên tử và từ chối nonce đã dùng; tiếp tục áp dụng kiểm tra **phân quyền** cho endpoint, tài nguyên và hành động.

Server có thể ẩn chi tiết lý do từ chối khỏi response ngoài hệ thống để hạn chế lộ thông tin về khóa hay chính sách; nhật ký nội bộ vẫn nên có mã lỗi được phân loại. Không log shared secret, canonical chứa dữ liệu nhạy cảm, body đầy đủ hoặc chữ ký nếu không thực sự cần.

**Xác thực khác phân quyền:** HMAC có thể chứng minh request được tạo bởi bên giữ secret hợp lệ; nó không tự cho phép client đọc mọi đơn hàng hoặc tạo mọi khoản thanh toán. Quyền phải dựa trên identity đã xác thực, scope, role và kiểm tra tài nguyên cụ thể. HTTPS vẫn bắt buộc để bảo vệ tính bí mật của dữ liệu trong quá trình truyền và hạn chế các kiểu tấn công ở lớp kết nối.

## 6. Key rotation: client chọn secret thế nào?

Shared secret cần vòng đời rõ ràng. Key ID là tên của một phiên bản key, **không phải secret** và không thay thế HMAC.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant S as Server
    Note over C,S: Giai đoạn chuyển đổi: key cũ và mới cùng được phép xác minh
    S-->>C: Cấp key ID mới và secret mới qua kênh an toàn
    C->>S: Request ký bằng key ID mới
    S->>S: Chọn secret đúng key ID và xác minh
    S-->>C: Kết quả xác minh
    Note over C,S: Khi toàn bộ client chuyển đổi và hết thời gian ân hạn
    S->>S: Thu hồi key ID cũ
~~~

Client lưu cặp **key ID → secret** an toàn trong secret manager hoặc cấu hình có kiểm soát truy cập, đọc key ID đang active và ký bằng đúng secret tương ứng. Server có thể chấp nhận đồng thời key cũ và mới trong thời gian chuyển đổi đã định; không được thử vô hạn mọi secret để tìm một chữ ký khớp. Việc thu hồi key cũ nên tính đến request đang bay, giới hạn timestamp và thời gian chuyển đổi, nhưng nếu key bị lộ thì phải ưu tiên thu hồi và xử lý sự cố.

Khi cần rotate, thay cả key ID và secret theo phiên bản cấp phát. Chỉ đổi X-Key-Id nhưng tiếp tục dùng secret cũ sẽ tạo chữ ký không hợp lệ. Không nhúng shared secret vào frontend JavaScript công khai hay ứng dụng mà người dùng cuối có thể trích xuất dễ dàng; mẫu HMAC shared secret phù hợp hơn với máy chủ, tác vụ backend và client được quản lý tin cậy.

## 7. Các lỗi canonical hóa và gateway thường gặp

| Hiện tượng | Nguyên nhân có thể xảy ra | Cách xử lý |
| --- | --- | --- |
| Signature mismatch dù hai bên cùng secret | Client ký JSON đã serialize một lần, rồi gửi JSON khác byte; hoặc encoding UTF-8 khác | Hash trên chính mảng byte đưa vào HTTP body publisher; kiểm thử digest client/server. |
| Cùng dữ liệu nhưng đổi thứ tự query bị từ chối | Hợp đồng dùng raw query nguyên dạng | Giữ nguyên request target hoặc cùng thống nhất quy tắc sort/encode giữa hai phía trước khi ký. |
| Chỉ hỏng khi qua gateway | Gateway sửa prefix path, chuyển %2F thành /, đổi query hoặc rewrite header | Quan sát request target tại điểm server xác minh; quyết định canonical hóa tại cùng một trust boundary. |
| Header đúng tên nhưng ký sai | Khác chữ hoa tên header, whitespace, giá trị Content-Type hoặc nhiều header trùng | Chuẩn hóa đúng theo hợp đồng và từ chối input không duy nhất/mơ hồ. |
| Request lúc được lúc không | Đồng hồ lệch hoặc nonce bị tái sử dụng | Đồng bộ thời gian, sinh nonce mới, kiểm tra TTL và tính nguyên tử của nonce store. |
| Sai chữ ký khi đổi key | X-Key-Id không khớp secret hoặc server đã thu hồi key | Cập nhật đồng bộ cặp key ID/secret; chỉ chọn key đang được cho phép. |
| Chỉ sai khi qua proxy nén body | Thành phần trung gian làm thay đổi byte body mà server đưa vào SHA-256 | Thống nhất ký body ở dạng nào và điểm áp dụng content encoding; tránh biến đổi sau ký. |

Đặc biệt với reverse proxy và API gateway, phải quyết định **thành phần nào là nguồn sự thật** cho method, path, query và body. Nếu gateway xác minh chữ ký trước khi rewrite route, cần dùng dạng request tại gateway. Nếu ứng dụng xác minh sau rewrite, phải có thiết kế bảo toàn hoặc truyền tin cậy giá trị gốc; không lấy một header do client tự điền như X-Original-URI làm nguồn sự thật nếu gateway không kiểm soát và xác thực header đó. Kiểm thử cả HTTP/1.1 và HTTP/2 khi hệ thống triển khai cả hai.

## 8. Bài thực hành và bảng kiểm

**Bài thực hành:** Xây dựng một client ký POST /v1/payments theo hợp đồng minh họa; tạo endpoint kiểm chứng có secret test riêng, log an toàn các bước băm/ký dưới dạng mã trạng thái (không log secret). Tách hàm tạo canonical, SHA-256, HMAC và sinh nonce để kiểm thử độc lập. Cho server nhận request và mô phỏng nonce store có thao tác insert-if-absent.

| Ca kiểm thử | Kết quả mong đợi |
| --- | --- |
| Request nguyên vẹn, key hợp lệ, timestamp mới, nonce chưa dùng | Chữ ký hợp lệ và qua bước chống replay. |
| Đổi amount trong body nhưng giữ chữ ký cũ | Từ chối do digest/HMAC không khớp. |
| Đổi method, path, một ký tự trong query, client ID hoặc Content-Type đã ký | Từ chối vì canonical thay đổi. |
| Gửi lại đúng request đã chấp nhận, cùng nonce | Từ chối replay kể cả chữ ký còn hợp lệ. |
| Timestamp vượt ngoài cửa sổ cho phép | Từ chối request hết hạn hoặc sai thời gian. |
| Hai request đồng thời có nonce giống nhau trên hai replica | Nhiều nhất một request vượt bước chống replay. |
| Key ID không tồn tại hoặc bị thu hồi | Từ chối, không thử secret không được phép. |
| Key mới trong giai đoạn rotation | Xác minh đúng key theo key ID và chính sách hiệu lực. |
| Query trùng tên, ký tự %2F, thứ tự query khác nhau, đường dẫn qua proxy | Kết quả thống nhất với quy tắc raw request target đã cam kết. |
| Body rỗng, Unicode, thay đổi whitespace JSON, thay đổi content encoding | Băm đúng byte gửi và giải thích được khi nào chữ ký thay đổi. |
| Client hợp lệ gọi tài nguyên không có quyền | Chữ ký có thể hợp lệ nhưng request bị từ chối ở bước phân quyền. |

**Tự kiểm tra kiến thức:**

1. Vì sao SHA-256(body) không đủ để xác thực request nếu không nằm trong dữ liệu được HMAC ký?
2. Nếu client ký đường dẫn gốc nhưng gateway chuyển đường dẫn trước khi server xác minh, hai bên phải sửa hợp đồng hoặc điểm xác minh như thế nào?
3. Tại sao timestamp hợp lệ vẫn không ngăn được replay nếu server không theo dõi nonce?
4. Vì sao retry một thao tác thanh toán cần idempotency ngay cả khi mỗi lần retry đều có nonce mới và chữ ký hợp lệ?
5. Server đã xác thực client qua HMAC thì có thể bỏ bước kiểm tra quyền truy cập tài nguyên hay không?

**Ghi nhớ:** Client ký được một request đáng tin cậy khi **cùng byte body, cùng canonical contract, đúng secret theo key ID và cùng request target** được dùng xuyên suốt quá trình tạo/chấp nhận request. Timestamp và nonce cần server thực thi để chống replay; quyền truy cập vẫn phải kiểm tra riêng.
