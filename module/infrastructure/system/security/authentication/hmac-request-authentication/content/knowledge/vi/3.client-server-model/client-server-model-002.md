# Server identity trong mô hình client–server dùng HMAC request authentication

## 1. Server identity là gì và vì sao cần xác minh?

Trong mô hình client–server, **server identity (danh tính máy chủ)** trả lời câu hỏi: **“Client đang giao tiếp với đúng dịch vụ/điểm cuối mà mình định tin cậy hay không?”** Với một API thanh toán, client cần biết kết nối thực sự đến dịch vụ `https://api.payments.example.test` do bên cung cấp vận hành, thay vì một endpoint do kẻ tấn công dựng lên.

Đây là chủ đề của chương **Mô hình client server** trong module `SECURITY_AUTHENTICATION_HMAC_REQUEST_AUTHENTICATION`. Module hướng dẫn ký HTTP request bằng **HMAC với shared secret** trên một **canonical request** (method, URI, header, body theo hợp đồng), kiểm tra chữ ký, chống replay bằng timestamp/nonce, key rotation và kiểm thử proxy/gateway. Trong toàn bộ quy trình đó, phải phân biệt rõ **client được xác thực trước server** và **server được xác thực trước client**.

Giả sử client có key ID `merchant-42` và shared secret `K`. Client ký dữ liệu:

```text
canonicalRequest = canonicalize(method, URI, headers, SHA-256(body))
signature        = HMAC-SHA256(K, UTF-8(canonicalRequest))
```

Server có khóa `K` sẽ tính lại HMAC và so sánh. **Chữ ký này chủ yếu cho phép server xác minh request đến từ bên nắm giữ secret** và phát hiện thay đổi ở những phần đã ký. Nhưng **chỉ nhìn vào chữ ký trên request, client chưa nhận được bằng chứng nào rằng đầu bên kia chính là server dự định**. Kẻ tấn công có thể đặt một máy chủ giả để nhận request đã ký hoặc chuyển tiếp request đó; họ không cần biết `K` để nhận dữ liệu mà client tự gửi.

Vì vậy cần ít nhất hai lớp kiểm soát có mục đích khác nhau:

| Câu hỏi | Lớp xử lý chính | Kết quả mong muốn |
| --- | --- | --- |
| “Có phải server `api.payments.example.test` mà client định gọi?” | **TLS server authentication**: kiểm tra certificate chain và tên miền của chứng chỉ khi kết nối HTTPS. | Client chỉ gửi request sau khi xác minh endpoint đích. |
| “Bên gửi request có biết shared secret phù hợp với key ID?” | **HMAC request verification** tại server. | Server nhận diện credential của caller và phát hiện sửa dữ liệu được ký. |
| “Chữ ký có được dùng cho đúng API/authority không?” | **Audience/authority binding** trong hợp đồng ký và chính sách route. | Tránh dùng lại chữ ký hợp lệ ở server/tenant/route ngoài phạm vi dự định. |
| “Caller được phép thao tác tài nguyên này không?” | **Authorization** sau xác thực. | Thực thi đúng quyền theo tài nguyên và nghiệp vụ. |
| “Có thể gửi lại request cũ không?” | **Timestamp + nonce + lưu nonce nguyên tử** hoặc cơ chế chống replay tương đương. | Hạn chế replay trong khoảng thời gian chữ ký còn hợp lệ. |

**Nhớ:** HMAC không thay cho việc xác minh server qua TLS; HTTPS cũng không tự thay thế yêu cầu xác thực API bằng HMAC nếu API đó cần nhận diện client theo shared secret.

## 2. TLS giúp client nhận biết server ra sao?

Khi client kết nối `https://api.payments.example.test` bằng HTTPS với cấu hình TLS an toàn, các bước có ý nghĩa bảo mật là:

1. Client chọn **origin** đích từ cấu hình tin cậy: scheme `https`, host `api.payments.example.test`, port (ngầm định 443). Tên này là **danh tính mong đợi**, không đơn thuần là địa chỉ IP lấy từ DNS.
2. Trong TLS handshake, phía server xuất trình chứng chỉ; client xác minh certificate chain tới một trust anchor được tin cậy, thời hạn/chính sách chứng chỉ phù hợp và **tên host kết nối khớp danh tính trong SAN của chứng chỉ**.
3. Nếu xác minh thất bại, client **dừng kết nối, không gửi secret, HMAC request hoặc payload nhạy cảm**. Không sửa lỗi bằng cách bỏ kiểm tra hostname hoặc chấp nhận mọi certificate.
4. Khi bắt tay TLS thành công, client có kênh liên lạc được bảo vệ về tính toàn vẹn, bảo mật và tính xác thực của endpoint đã kiểm tra; lúc đó mới gửi HTTP request chứa chữ ký HMAC.
5. Server/gateway nhận request và xác minh HMAC trên canonical request theo hợp đồng, sau đó thực thi authorization.

```mermaid
sequenceDiagram
    participant C as Client
    participant G as HTTPS API Gateway
    participant S as Service / HMAC verifier

    C->>G: TLS handshake cho api.payments.example.test
    G-->>C: Certificate + TLS handshake
    Note over C: Kiểm tra CA chain và SAN/hostname
    alt TLS certificate/hostname không hợp lệ
        C-xG: Dừng kết nối, không gửi request
    else TLS hợp lệ
        C->>G: HTTPS request với X-Key-Id, timestamp, nonce, HMAC
        G->>S: Forward qua kênh upstream tin cậy
        Note over G,S: Giữ nguyên hoặc chuẩn hóa theo hợp đồng ký
        S->>S: Chọn secret; xác minh canonical + HMAC
        S->>S: Kiểm tra replay và authorization
        S-->>G: Kết quả xử lý
        G-->>C: HTTPS response
    end
```

**DNS không tự chứng minh danh tính server.** DNS có thể trả về IP sai do cấu hình hoặc tấn công; TLS hostname verification giúp phát hiện trường hợp bên ở IP đó không có chứng chỉ hợp lệ cho host mà client mong đợi. Trong khi đó, một chứng chỉ hợp lệ cho `attacker.example.test` **không thể** được dùng để chứng minh danh tính của `api.payments.example.test`.

### Server identity xác minh ở mức nào?

- **Tên dịch vụ/origin:** HTTPS thông thường xác minh chủ thể đang phục vụ hostname cụ thể theo hệ thống chứng chỉ tin cậy. Nó không chứng minh danh tính một process hoặc một pod backend cụ thể.
- **Backend nằm sau gateway:** nếu TLS từ client kết thúc tại gateway, client xác minh **điểm kết thúc TLS công khai** đại diện dịch vụ. Backend cần một quan hệ tin cậy khác với gateway, ví dụ mTLS ở đường upstream, chính sách mạng và cơ chế chuyển giao caller identity.
- **Danh tính theo ứng dụng/nghiệp vụ:** chứng chỉ TLS hợp lệ cho hostname chưa trả lời API đó thuộc merchant/tenant nào hoặc người gọi được quyền làm gì. Những quan hệ này cần cấu hình tin cậy và authorization riêng.

Certificate pinning có thể hữu ích ở một số môi trường có yêu cầu đặc biệt, nhưng dễ làm gián đoạn dịch vụ khi thay chứng chỉ/CA; đây không phải điều kiện mặc định để dùng HTTPS an toàn. Trong đa số client, xác minh PKI + hostname đúng và chính sách cập nhật trust store đáng tin cậy là nền tảng.

## 3. Tại sao HMAC request chưa chứng minh server identity?

Xét luồng có client `C`, server hợp lệ `S` và server giả `M`:

1. `C` sở hữu shared secret `K` dùng với `S`; `C` tạo HMAC cho `POST /v1/payments`.
2. Vì cấu hình endpoint bị sửa hoặc client bỏ kiểm tra TLS, request được gửi đến `M`.
3. `M` có thể **nhận và lưu body cùng chữ ký**. HMAC không mã hóa payload và cũng không buộc kẻ nhận phải chứng minh mình biết secret.
4. `M` có thể thử **chuyển tiếp nguyên request đã ký** đến `S`. Nếu hợp đồng ký không gắn với authority/đích và request vẫn nằm trong cửa sổ chống replay, `S` có thể chấp nhận nó.
5. `M` không thể sửa nội dung đã ký để tạo HMAC hợp lệ mà không có `K`; tuy nhiên điều đó **không** loại bỏ khả năng relay nguyên request hoặc đánh lừa client gửi nội dung đến nhầm server.

Nếu `M` **không biết** secret, việc gửi một response bất kỳ `200 OK` cũng không phải bằng chứng sở hữu `K`. Nếu nhiều server cùng được cấp một shared secret, một thông điệp HMAC do server tạo (khi có thiết kế xác thực response) chỉ chứng minh **một bên trong nhóm biết khóa**, chứ chưa chỉ ra node nào.

**Không gửi shared secret trong HTTP header hoặc body.** Client chỉ dùng secret tại chỗ để tính MAC; server tải secret từ kho tin cậy qua key ID. Nhưng ngay cả khi secret không đi trên mạng, request/response nghiệp vụ vẫn cần TLS để chống nghe lén và chỉnh sửa trên đường truyền.

## 4. Gắn chữ ký với đúng service: authority và audience

Khi cùng một tổ chức vận hành nhiều API, môi trường hoặc tenant, chỉ ký `method + path + body` có thể chưa đủ. Chẳng hạn, cả hai dịch vụ sau đều có `POST /v1/orders`:

```text
https://orders.prod.example.test/v1/orders
https://orders.staging.example.test/v1/orders
```

Nếu cùng một secret bị tái sử dụng và chữ ký không chứa dấu hiệu chỉ định đích, một chữ ký hợp lệ ở môi trường này có thể bị chấp nhận ở môi trường kia nếu các điều kiện khác cho phép. **Nên ưu tiên tách khóa theo môi trường, dịch vụ, tenant và mục đích**, đồng thời ràng buộc canonical request với authority/audience mà backend dự định phục vụ.

Ví dụ về **hợp đồng ký minh họa** (không phải chuẩn mặc định của mọi hệ thống):

```http
POST /v1/payments?currency=VND HTTP/1.1
Host: api.payments.example.test
Content-Type: application/json
X-Key-Id: merchant-42-2026-11
X-Timestamp: 2026-11-28T02:05:00Z
X-Nonce: kNu0xA7qIuD3M6RlcG9fQWNd
X-Signature: <hex của HMAC-SHA256>

{"account":"A123","amount":100000}
```

**Canonical request v1**:

```text
HMAC-REQUEST-V1
POST
https://api.payments.example.test
/v1/payments?currency=VND
content-type:application/json
x-key-id:merchant-42-2026-11
x-timestamp:2026-11-28T02:05:00Z
x-nonce:kNu0xA7qIuD3M6RlcG9fQWNd
<lowercase-hex(SHA-256(bodyBytes))>
```

Hợp đồng minh họa quy định các dòng mã hóa UTF-8, nối bằng `LF` và **không có newline ở cuối**. Dòng cuối là giá trị digest hex thật, không phải chuỗi `<...>`; `bodyBytes` là **byte body mà ứng dụng thực sự sử dụng**, không phải JSON đã parse rồi serialize lại.

Các quy tắc cần ghi rõ và thực thi ở cả client lẫn server:

| Trường | Quy tắc |
| --- | --- |
| `scheme + authority` | Canonical chứa `https://api.payments.example.test` theo cấu hình endpoint đích được chấp nhận; nếu có cổng khác mặc định, phải thống nhất cách ghi cổng. |
| `method` | Giá trị như `POST`, viết hoa, chính xác method server xử lý. |
| `rawTarget` | Raw path + raw query (nếu có); phải cố định quy tắc percent-encoding, query order và dấu `?`. Không chứa fragment. |
| `content-type` | Ví dụ chỉ chấp nhận `application/json`; từ chối header trùng hoặc biến thể không được hợp đồng hỗ trợ. |
| `x-key-id` | Định danh secret đang hiệu lực; ký để chống sửa ID mà không được phát hiện. |
| `x-timestamp`, `x-nonce` | Ký cả hai, đồng thời kiểm tra freshness và nonce uniqueness ở server. |
| Body hash | Server tự tính SHA-256 từ **body bytes nhận được** và dùng digest trong canonical; không tin hash do client khai báo. |

Để tránh việc dùng chữ ký ở sai service, server **phải đối chiếu audience/authority đã ký với route đích tin cậy**. Đừng chỉ nhận giá trị `Host`, `Forwarded` hoặc `X-Forwarded-Host` từ request mà không kiểm soát đường đi của header; các giá trị do caller tự đặt có thể bị giả. Ở gateway, nên có mapping đã cấu hình giữa host được phép và backend, đồng thời loại bỏ header forwarding do client tự gửi trước khi gắn metadata đáng tin cậy.

Nếu hệ thống chỉ có một endpoint duy nhất được cấu hình cố định và secret chỉ có hiệu lực cho endpoint đó, audience có thể được ràng buộc bằng chính sách kiểm tra route/key scope thay vì một dòng canonical riêng. **Điều quan trọng là chứng minh được khóa/chữ ký không được tái dùng trên đích ngoài phạm vi.**

## 5. Ví dụ Java 17+: client xác minh HTTPS rồi gửi request HMAC

Ví dụ dưới đây dùng `java.net.http.HttpClient` với cơ chế xác minh TLS mặc định của JDK. Client giữ một endpoint đã cấu hình, bắt buộc HTTPS, không tự theo redirect, ký method/authority/raw target/header/body, rồi gửi request. `api.payments.example.test` là hostname minh họa: khi triển khai cần thay bằng DNS thực với chứng chỉ TLS hợp lệ.

```java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.time.Duration;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.Base64;
import java.util.HexFormat;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class SignedApiClient {
    private static final String ALLOWED_HOST = "api.payments.example.test";
    private static final String KEY_ID = "merchant-42-2026-11";
    private static final URI ENDPOINT = URI.create(
            "https://api.payments.example.test/v1/payments?currency=VND");

    public static HttpResponse<byte[]> sendPayment(byte[] sharedSecret)
            throws Exception {
        // Cố định origin mà client kỳ vọng, trước cả khi ký và kết nối.
        if (!"https".equalsIgnoreCase(ENDPOINT.getScheme())
                || !ALLOWED_HOST.equalsIgnoreCase(ENDPOINT.getHost())
                || (ENDPOINT.getPort() != -1 && ENDPOINT.getPort() != 443)
                || ENDPOINT.getUserInfo() != null
                || ENDPOINT.getFragment() != null) {
            throw new IllegalArgumentException("Untrusted API origin");
        }
        if (sharedSecret == null || sharedSecret.length < 32) {
            throw new IllegalArgumentException("Invalid HMAC secret");
        }

        byte[] body = "{\"account\":\"A123\",\"amount\":100000}"
                .getBytes(StandardCharsets.UTF_8);
        String timestamp = Instant.now().truncatedTo(ChronoUnit.SECONDS).toString();
        byte[] nonceBytes = new byte[24];
        new SecureRandom().nextBytes(nonceBytes);
        String nonce = Base64.getUrlEncoder().withoutPadding()
                .encodeToString(nonceBytes);
        String rawTarget = ENDPOINT.getRawPath()
                + (ENDPOINT.getRawQuery() == null
                    ? "" : "?" + ENDPOINT.getRawQuery());
        String bodyHash = HexFormat.of().formatHex(
                MessageDigest.getInstance("SHA-256").digest(body));

        // Phải khớp 100% hợp đồng canonical phía server.
        String canonical = String.join("\n",
                "HMAC-REQUEST-V1",
                "POST",
                "https://" + ALLOWED_HOST,
                rawTarget,
                "content-type:application/json",
                "x-key-id:" + KEY_ID,
                "x-timestamp:" + timestamp,
                "x-nonce:" + nonce,
                bodyHash);
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(sharedSecret, "HmacSHA256"));
        String signature = HexFormat.of().formatHex(
                mac.doFinal(canonical.getBytes(StandardCharsets.UTF_8)));

        HttpClient http = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(5))
                .followRedirects(HttpClient.Redirect.NEVER)
                .build(); // Trust store + hostname verification mặc định
        HttpRequest request = HttpRequest.newBuilder(ENDPOINT)
                .timeout(Duration.ofSeconds(15))
                .header("Content-Type", "application/json")
                .header("X-Key-Id", KEY_ID)
                .header("X-Timestamp", timestamp)
                .header("X-Nonce", nonce)
                .header("X-Signature", signature)
                .POST(HttpRequest.BodyPublishers.ofByteArray(body))
                .build();

        // TLS handshake + kiểm tra certificate/hostname diễn ra khi kết nối.
        // Nếu thất bại, send() ném lỗi thay vì trả response HTTP.
        return http.send(request, HttpResponse.BodyHandlers.ofByteArray());
    }
}
```

Giải thích một số quyết định quan trọng:

- **Không cấu hình trust-all certificate hay tắt hostname verification.** Khối lệnh mặc định giả định trust store của JDK/môi trường vận hành được quản lý đúng; nếu cần private CA, phải cài trust anchor tin cậy theo chính sách cụ thể.
- **Giữ endpoint đúng mục tiêu.** Cấu hình host và hạn chế redirect giúp tránh gửi request đã ký đến một host ngoài ý muốn; nếu có redirect hợp lệ, cần một quy trình mới để kiểm tra đích và ký lại request, không tự tái sử dụng chữ ký.
- **Không đưa secret vào HTTP.** Chỉ có chữ ký `X-Signature` được gửi; trong ứng dụng thật, secret cần lấy từ kho bí mật phù hợp thay vì ghi cứng vào source code hoặc log.
- **Giữ body nhất quán.** Byte body đã hash cũng chính là byte gửi bằng `BodyPublishers.ofByteArray`. Việc ký `rawTarget` yêu cầu client/proxy/server thống nhất cách biểu diễn URI.
- **Ví dụ không triển khai server verifier.** Server phải dựng lại chính canonical string này từ request đã nhận, chọn secret tin cậy theo key ID, so sánh MAC bằng cơ chế hạn chế timing leak, kiểm tra timestamp/nonce, đối chiếu audience rồi authorization.

Java API chỉ là một ví dụ minh họa; ngôn ngữ/framework khác cũng phải tuân thủ hai nguyên tắc: **đích TLS được xác minh** và **canonical HMAC khớp byte với dữ liệu backend sử dụng**.

## 6. Server identity khi có reverse proxy và API gateway

Hệ thống thực tế thường có đường đi:

```text
Client
  ── HTTPS / TLS(public) ──> Edge proxy / API Gateway
                                  │
                                  └── TLS/mTLS(private) ──> Backend HMAC verifier
                                                              │
                                                              └── Authorization + business logic
```

Trong mô hình này, **certificate client nhìn thấy là của gateway** cho hostname public. Client không trực tiếp xác minh chứng chỉ của backend nếu TLS kết thúc ở gateway. Vì vậy:

1. **Client → gateway:** kiểm tra hostname và certificate chain, bắt buộc HTTPS, áp dụng giới hạn redirect.
2. **Gateway → backend:** dùng TLS/mTLS hoặc cơ chế tin cậy tương đương theo hạ tầng để chống giả mạo endpoint upstream và chỉnh sửa request. Nếu chỉ dùng mạng nội bộ không mã hóa, cần đánh giá riêng rủi ro mạng và vận hành.
3. **Chuyển tiếp request:** phải biết gateway có rewrite path, query, authority, header hoặc body không. Cần xác minh trên một dạng canonical **khớp request nghiệp vụ sẽ xử lý**. Nếu gateway xác minh HMAC thay backend, nó phải chuyển kết quả xác thực qua kênh được bảo vệ và backend phải tin cậy **chính gateway**.
4. **Forwarded identity:** gateway xóa các header caller có thể giả như `X-Authenticated-Client` trước khi gắn caller identity từ kết quả đã xác minh; backend chỉ tin header này khi request đến từ gateway được xác thực.
5. **Chặn bypass:** backend không nên cho caller truy cập trực tiếp một đường khác để vượt qua gateway và giả header nội bộ; kiểm soát routing, network policy và authentication upstream.

Hai lỗi đặc biệt dễ nhầm:

| Tình huống | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Client ký `/v1/files/a%2Fb`, gateway giải mã thành `/v1/files/a/b`. | HMAC không khớp hoặc router xử lý **khác tài nguyên đã được ký**. | Cố định raw target dùng cho verify và routing; kiểm thử percent-encoding qua proxy. |
| Backend lấy `X-Forwarded-Host` do client tự đặt làm authority đã ký. | Caller có thể điều khiển thông tin đích; kiểm tra audience trở nên không đáng tin. | Gateway xóa header đầu vào, tạo metadata từ route đã xác thực; backend kiểm tra audience theo cấu hình. |

**Lưu ý:** Nếu request HMAC được xác minh sau gateway, ký những header hay thay đổi qua từng HTTP hop (`Connection`, `Transfer-Encoding`, nhiều dạng `Content-Length`) thường gây sai lệch; chỉ đưa field vào hợp đồng ký khi có quy tắc biểu diễn đầu cuối rõ ràng.

## 7. Nếu cần xác thực cả response của server?

TLS đã cung cấp **server authentication, confidentiality và integrity của dữ liệu trong kết nối** khi kiểm tra chứng chỉ thành công. Phần lớn API trực tuyến vì vậy không cần HMAC riêng trên response chỉ để chứng minh server identity trong kênh HTTPS.

Trong trường hợp dữ liệu response sẽ được **lưu, chuyển tiếp hoặc xác minh bên ngoài phiên TLS**, có thể cần cơ chế xác thực response ở tầng ứng dụng. Tuy nhiên phải thiết kế một **hợp đồng response riêng**:

```text
RESPONSE-HMAC-V1
<request-id đã được ràng buộc>
<status-code>
<selected-response-headers>
<SHA-256(response-body-bytes)>
<response-timestamp-or-nonce>
```

Sau đó tạo MAC bằng **khóa được phân tách theo mục đích** (ví dụ khóa response dẫn xuất độc lập bằng một KDF phù hợp), không dùng tùy tiện cùng message format và cùng key cho cả request và response. Client phải so sánh response với request đang chờ, key scope/audience và thông tin chống phát lại, tránh dùng nhầm response cũ hoặc phản hồi của API khác.

**Giới hạn căn bản:** vì HMAC là mật mã **đối xứng**, mọi bên biết khóa response đều có thể tạo MAC; điều đó chỉ chứng minh sở hữu khóa, không tạo bằng chứng độc lập về danh tính một server duy nhất. Nếu cần bên thứ ba kiểm chứng nguồn gốc lâu dài, nên cân nhắc chữ ký số bất đối xứng với quản lý khóa và chuỗi tin cậy phù hợp. Đừng biến chữ ký HMAC response thành phương án thay TLS.

## 8. Key rotation, multi-tenant và server identity

Trong một hệ thống nhiều server hoặc nhiều tenant, quản lý key ảnh hưởng trực tiếp đến phạm vi một chữ ký được tin cậy:

- **Key ID và key scope:** ánh xạ key ID tới credential, client identity, môi trường và service/audience được phép. Không để client tự quyết định scope chỉ bằng field không được đối chiếu.
- **Tách key:** tránh dùng một shared secret cho nhiều môi trường, service hoặc tenant; nếu phải chia sẻ trong một cụm, thừa nhận HMAC chứng minh thành viên của **nhóm biết khóa**, không phải một backend đơn lẻ.
- **Rotation:** phát hành key mới với key ID mới, cho phép giai đoạn chuyển tiếp hữu hạn, sau đó thu hồi key cũ. Key đã revoke không được dùng xác minh nữa.
- **Certificate rotation:** thay chứng chỉ TLS độc lập với rotation HMAC; nếu trust store và DNS đúng, certificate mới hợp lệ cho đúng hostname vẫn được client chấp nhận. Kiểm tra cả quy trình triển khai chứng chỉ và key API.
- **Audit:** ghi dấu key ID, audience, kết quả TLS/HMAC/replay và route ở mức an toàn; không log secret, chữ ký đầy đủ khi không cần, hay dữ liệu nhạy cảm.

Giả sử `merchant-42` chỉ được ký cho `payments.prod`, nhưng vẫn sở hữu credential hợp lệ. Một request sang `refunds.prod` phải bị **từ chối bởi audience/key scope hoặc authorization**, kể cả khi MAC có thể được tính đúng. Nhận diện caller không tự đồng nghĩa caller được phép sử dụng mọi API.

## 9. Các tình huống cần kiểm thử

Các phép thử dưới đây nên chạy trong môi trường có HTTPS thật hoặc CA thử nghiệm được client tin cậy đúng cách, đồng thời kiểm tra qua cả gateway và backend.

| Kiểm thử | Kết quả kỳ vọng |
| --- | --- |
| Server trả chứng chỉ hợp lệ cho đúng hostname; HMAC đúng; nonce mới. | TLS thành công; server tiếp tục kiểm tra HMAC, replay và quyền. |
| Certificate hết hạn, không tin CA, hoặc SAN không khớp hostname. | **Client từ chối kết nối**, chưa gửi request. |
| DNS trỏ đến IP máy chủ giả với cert chỉ hợp lệ cho domain của kẻ tấn công. | **Client từ chối** khi hostname không khớp. |
| Client bị cấu hình trỏ tới host ngoài danh sách đích tin cậy. | **Từ chối trước khi gửi**; không ký request cho đích lạ. |
| Server trả redirect sang hostname khác. | Không tự động gửi lại request đã ký; kiểm tra đích trước bất kỳ lần ký/gửi mới nào. |
| HMAC hợp lệ nhưng audience trong canonical không khớp route đã cấu hình. | **Server từ chối**; không xử lý nghiệp vụ. |
| HMAC hợp lệ cho client, nhưng client không có quyền trên tài nguyên. | **Authorization từ chối**, dù xác thực đúng. |
| Attacker chuyển tiếp nguyên request HMAC chưa hết hạn đến server thật. | TLS không tự loại bỏ relay; cơ chế **nonce/replay** phải ngăn request bị thực thi lại khi nonce đã được dùng. |
| Header `X-Forwarded-Host` được caller tự đưa vào hoặc route backend bị bypass. | Gateway/backend không tin metadata chưa xác thực; request bị từ chối theo chính sách route. |
| Gateway viết lại percent-encoding, `Host`, header hoặc body. | Kiểm thử phát hiện sai lệch giữa canonical ký, canonical xác minh và dữ liệu xử lý; không bỏ qua lỗi HMAC. |
| HMAC key bị revoke hoặc key ID thuộc môi trường khác. | **Từ chối**, ngay cả khi chữ ký được tạo đúng với khóa cũ. |
| Rotate TLS certificate và HMAC key độc lập. | Chỉ endpoint có certificate phù hợp và request ký bởi key đang có hiệu lực mới được nhận. |

**Trường hợp replay cần hiểu đúng:** Nếu request bị đánh cắp rồi chuyển tiếp **trước request gốc**, hệ thống có thể coi bản đến đầu tiên là hợp lệ khi timestamp và nonce chưa xuất hiện. Nonce store thường chặn **bản lặp thứ hai**, chứ không có khả năng luôn phân biệt đâu là người gửi gốc. TLS endpoint verification và bảo vệ kênh từ client mới là lớp quan trọng để giảm khả năng chiếm và relay request.

## 10. Checklist thiết kế

- [ ] Cấu hình một **origin HTTPS tin cậy** cho mỗi API và xác minh hostname/SAN + certificate chain; không tắt TLS verification để xử lý lỗi.
- [ ] Quy định rõ gateway hay backend là endpoint TLS công khai và bên nào chịu trách nhiệm HMAC verification.
- [ ] Ký method, URI, header và body theo hợp đồng canonical; ràng buộc audience/authority với service và key scope được phép.
- [ ] Bảo đảm gateway xử lý `Host`/`Forwarded`, raw path, query và body nhất quán; không tin header caller tự giả làm identity nội bộ.
- [ ] Dùng TLS/mTLS hoặc kênh upstream tin cậy giữa gateway và backend; chặn đường bypass.
- [ ] Bảo vệ shared secret, phân tách key theo dịch vụ/môi trường/mục đích, kiểm soát rotation và revocation.
- [ ] Ký và kiểm tra timestamp/nonce; dùng nonce store nguyên tử trên các instance; xây dựng idempotency riêng cho tác vụ quan trọng.
- [ ] Thực thi authorization sau HMAC; nếu cần xác thực response độc lập TLS, thiết kế message format và key scope riêng.
- [ ] Kiểm thử cả tình huống kết nối nhầm server, TLS sai chứng chỉ, signature đúng nhưng sai audience, proxy rewrite, key rotation và relay.

**Kết luận:** Trong HMAC request authentication, *server identity* chủ yếu được client xác minh qua **TLS và hostname đã tin cậy**. HMAC xác minh **request được ký bằng shared secret**, còn authority binding đảm bảo chữ ký áp dụng đúng API đích. Kết hợp ba yếu tố này với chống replay, bảo vệ đường truyền qua gateway, quản lý key và authorization mới tạo nên một mô hình client–server có ranh giới tin cậy rõ ràng.
