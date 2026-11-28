# Changed header test: kiểm thử thay đổi header trong xác thực HMAC

## 1. Bài toán và mục tiêu

Trong mô hình **HMAC request authentication**, client và server chia sẻ một secret. Client tạo chữ ký HMAC từ biểu diễn chuẩn hóa (*canonical request*) của HTTP request; server dựng lại cùng biểu diễn, tự tính HMAC và so sánh chữ ký. Hệ thống có thể ràng buộc phương thức, URI, một tập header và nội dung body vào chữ ký tùy theo hợp đồng ký.

**Changed header test** kiểm tra một tính chất quan trọng: **nếu một header đã được đưa vào canonical request bị thay đổi sau khi client ký, chữ ký cũ phải không còn hợp lệ**. Ngược lại, việc thay đổi header không nằm trong hợp đồng ký không tự động làm HMAC thất bại. Bài kiểm thử cũng cần phân biệt thay đổi giá trị thực sự với các biến đổi cú pháp được hợp đồng chuẩn hóa cho phép.

Sau bài này, người học có thể:

1. Nhận diện header nào bắt buộc được ký, header nào chỉ phục vụ truyền tải hoặc quan sát.
2. Tạo request có chữ ký hợp lệ, giữ nguyên chữ ký rồi chỉ thay đổi **một** header để kiểm tra tính toàn vẹn.
3. Kiểm thử các tình huống header bị thiếu, trùng, đổi tên chữ hoa/thường, thay khoảng trắng, hoặc bị gateway/proxy viết lại.
4. Xác định nguyên nhân thất bại là **signature mismatch** thay vì timestamp hết hạn, nonce đã dùng, thiếu credential hay thiếu quyền truy cập.
5. Viết bài kiểm thử tích hợp cho luồng xác thực HMAC trong ứng dụng Java/Spring Security.

Phạm vi là tính toàn vẹn và **xác thực HTTP request**; HMAC xác nhận request được tạo bởi bên có secret và phần dữ liệu được ký chưa bị thay đổi, nhưng **không tự quyết định client có quyền thực hiện thao tác hay không**.

## 2. Chốt hợp đồng canonical request trước khi viết test

Không có một cách canonical hóa header dùng chung cho mọi hệ thống HMAC. Client và server phải dùng **cùng một phiên bản hợp đồng**. Ví dụ dưới đây sử dụng một hợp đồng minh họa `v1`; khi triển khai thực tế, cần thay bằng hợp đồng của API đang kiểm thử.

| Thành phần | Quy tắc của hợp đồng `v1` minh họa |
|---|---|
| HTTP method | Viết hoa, ví dụ `POST`. |
| Request target | Dùng path và raw query theo thứ tự đã thỏa thuận, ví dụ `/v1/payments?currency=VND&orderId=42`. Không tự giải mã/mã hóa lại URI hoặc sắp xếp query nếu hợp đồng không quy định. |
| Header được ký | `Content-Type`, `X-Client-Id`, `X-Nonce`, `X-Timestamp`; tất cả bắt buộc có mặt đúng một lần. |
| Tên header | Đưa về chữ thường và sắp xếp theo tên: `content-type`, `x-client-id`, `x-nonce`, `x-timestamp`. HTTP header name vốn không phân biệt hoa/thường. |
| Giá trị header | Bỏ khoảng trắng/tabs ở **đầu và cuối** (OWS); giữ nguyên ký tự và khoảng trắng **bên trong**. Không tự đổi chữ hoa/thường của giá trị. Từ chối CR/LF trong giá trị. |
| Header trùng | Từ chối nếu header bắt buộc được ký xuất hiện nhiều lần, trừ khi hợp đồng định nghĩa rõ cách gộp. Không mặc nhiên lấy giá trị đầu hoặc cuối. |
| Body | SHA-256 trên **byte body thực sự truyền đi**, xuất dưới dạng hex chữ thường. Body rỗng vẫn có giá trị SHA-256 xác định. |
| Mã hóa canonical | UTF-8, các dòng ngăn bằng `\n` (LF), không thêm dòng trống cuối. |
| HMAC | `HMAC-SHA256(secret, UTF8(canonicalRequest))`, chữ ký xuất hex chữ thường. |
| Header chữ ký | `X-Signature: v1=<hex>`; bản thân `X-Signature` không nằm trong canonical request. Phiên bản `v1` được ràng buộc bởi dòng đầu của canonical request. |

Ví dụ request gốc:

```http
POST /v1/payments?currency=VND&orderId=42 HTTP/1.1
Host: api.example.test
Content-Type: application/json
X-Client-Id: client-a
X-Nonce: 6af3d8f5-32af-4fd4-87eb-723e8597a649
X-Timestamp: 1795800000
X-Request-Id: req-1001
X-Signature: v1=<chu-ky-hex-do-client-tinh>

{"orderId":42,"amount":100000}
```

Canonical request tương ứng là **chuỗi dưới đây, không có dòng trống cuối**:

```text
v1
POST
/v1/payments?currency=VND&orderId=42
content-type:application/json
x-client-id:client-a
x-nonce:6af3d8f5-32af-4fd4-87eb-723e8597a649
x-timestamp:1795800000
body-sha256:<sha256-hex-cua-byte-body>
```

Ở đây `<sha256-hex-cua-byte-body>` và `<chu-ky-hex-do-client-tinh>` là chỗ giữ chỗ để giải thích; triển khai thật phải thay bằng các giá trị hex được tính, không đưa dấu `<...>` vào dữ liệu ký. `Host` và `X-Request-Id` không được ký trong **hợp đồng minh họa** này. Nếu ứng dụng dùng host, tenant, quyền truy cập, key id hoặc một header điều hướng nghiệp vụ để đưa ra quyết định bảo mật, phải cân nhắc đưa trường đó vào hợp đồng ký và kiểm thử nó tương ứng.

Với secret `K` và canonical request `C`, chữ ký là:

\[
S = \operatorname{HMAC}_{\mathrm{SHA256}}(K,\operatorname{UTF8}(C))
\]

Nếu kẻ trung gian thay `X-Timestamp: 1795800000` thành `X-Timestamp: 1795800001` nhưng giữ nguyên `S`, server tạo canonical request khác và tính ra HMAC khác. Giá trị timestamp mới vẫn có thể nằm trong cửa sổ thời gian hợp lệ; request **vẫn phải bị từ chối vì chữ ký không khớp**. Tương tự, đổi `Content-Type` từ `application/json` thành `application/json; charset=UTF-8` sẽ làm thay đổi canonical request theo quy tắc `v1` trên, dù hai giá trị có thể được ứng dụng xử lý tương đương về mặt media type.

## 3. Thiết kế changed header test có giá trị

### 3.1. Chuẩn bị fixture hợp lệ

Một changed header test đáng tin cậy bắt đầu từ một request có chữ ký hợp lệ và **được endpoint chấp nhận** trong môi trường kiểm thử:

1. Dùng client test và secret dành riêng cho môi trường kiểm thử, đã đăng ký ở server.
2. Chọn method, URI, body và tất cả header bắt buộc; tạo `X-Timestamp` gần thời điểm server kiểm tra, `X-Nonce` mới cho từng request.
3. Tính SHA-256 của body byte, dựng canonical request độc lập theo hợp đồng, tính HMAC-SHA256 rồi gửi request gốc.
4. Xác minh request gốc đi qua xác thực HMAC thành công. Endpoint hoặc test identity phải có quyền phù hợp để kết quả không bị lẫn với `403 Forbidden`.
5. Tạo một request thử nghiệm từ cùng bộ dữ liệu ký; **chỉ sửa header đang được khảo sát, không ký lại** và không thay đổi signature.

Điểm mấu chốt là **chữ ký phản ánh dữ liệu *trước* khi thay đổi**, còn request trên đường truyền chứa dữ liệu *sau* khi thay đổi. Nếu code test ký lại request sau khi sửa header, đó là phép thử một request hợp lệ khác, không phải changed header test.

Không nên gửi request gốc rồi tái sử dụng chính `X-Nonce` trong request biến đổi: cơ chế chống replay có thể từ chối request thứ hai trước khi phép kiểm tra chữ ký được quan sát. Hãy dùng một fixture độc lập với nonce mới cho mỗi ca kiểm thử; xây chữ ký từ giá trị gốc rồi biến đổi giá trị header **trước lần gửi duy nhất** của ca đó.

### 3.2. Ma trận test

Trong bảng này, giả định server trả `401 Unauthorized` cho HMAC không hợp lệ và `400 Bad Request` cho định dạng header sai. Đó là quy ước kiểm thử ví dụ; nếu API công bố mã lỗi khác, phải theo đúng hợp đồng của API nhưng vẫn giữ nguyên nguyên tắc **từ chối truy cập trước khi xử lý nghiệp vụ**.

| Ca kiểm thử | Phép biến đổi sau khi đã ký | Kết quả mong đợi |
|---|---|---|
| Control | Không sửa header, signature hợp lệ, nonce chưa dùng | Qua bước xác thực HMAC; endpoint có thể trả `2xx` khi fixture có đủ quyền. |
| Changed `Content-Type` | `application/json` → `application/json; charset=UTF-8` | Từ chối vì signature mismatch theo hợp đồng `v1`. |
| Changed `X-Client-Id` | `client-a` → `client-b` | Từ chối; không được xác thực nhầm sang danh tính/key khác. |
| Changed `X-Timestamp` | Tăng một giây, vẫn trong cửa sổ cho phép | Từ chối do signature mismatch, không quy lỗi thành timestamp quá hạn. |
| Changed `X-Nonce` | Thay bằng nonce mới, đúng định dạng | Từ chối vì signature mismatch, không quy lỗi thành nonce trùng. |
| Missing signed header | Bỏ `X-Nonce` hoặc `Content-Type` | Từ chối vì thiếu trường ký bắt buộc; không thế giá trị rỗng rồi chấp nhận. |
| Duplicate signed header | Gửi hai `X-Client-Id` khác nhau | Từ chối định dạng mơ hồ; tránh khác biệt cách đọc giữa gateway và ứng dụng. |
| Changed unsigned header | Chỉ sửa `X-Request-Id`, giữ signature cũ | HMAC vẫn hợp lệ theo `v1` nếu header này không ảnh hưởng quyết định bảo mật. |
| Changed header-name case | `X-Nonce` → `x-nonce`, giữ nguyên giá trị | HMAC vẫn hợp lệ vì tên header được chuẩn hóa về lowercase. |
| Changed outer OWS | Thêm dấu cách đầu/cuối giá trị đã ký | HMAC vẫn hợp lệ **nếu** stack HTTP giữ được dữ liệu và hai phía cùng trim OWS theo hợp đồng. |
| Changed inner whitespace | Đổi khoảng trắng bên trong giá trị header có khoảng trắng | Từ chối nếu canonical value thực sự thay đổi theo `v1`. |
| Changed body | Sửa một byte JSON sau khi ký, không đổi signature | Từ chối vì body hash trong canonical request thay đổi. |
| Changed method/URI | Đổi path, raw query hoặc method sau khi ký | Từ chối nếu biểu diễn canonical khác. |
| Changed signature | Sửa một ký tự của chữ ký hex hoặc phiên bản không hỗ trợ | Từ chối; định dạng sai có thể nhận mã lỗi riêng. |

Các ca **positive** (control, header không ký, đổi hoa/thường tên header, trim OWS) quan trọng ngang các ca **negative**: chúng bắt được lỗi canonical hóa quá chặt hoặc xử lý sai hợp đồng. Ngược lại, header không ký mà điều khiển tenant, scope, nội dung định tuyến hoặc lựa chọn secret là một điểm cần đánh giá lại thiết kế; không thể chỉ dựa vào việc test HMAC vẫn thành công để kết luận an toàn.

## 4. Ví dụ kiểm thử tích hợp bằng Java, JUnit 5 và Spring MockMvc

Đoạn mã dưới đây minh họa cách **ký dữ liệu gốc rồi gửi một header đã bị sửa với chữ ký cũ**. Giả định ứng dụng Spring Boot đã cấu hình bộ lọc xác thực HMAC cho `POST /v1/payments`, dùng đúng hợp đồng `v1` ở phần 2, client `client-a` có key test và đủ quyền gọi endpoint. Cần thay URI, fixture key, body và kỳ vọng HTTP theo ứng dụng cụ thể. Bộ ký trong test độc lập với bộ canonical hóa trong production để tránh hai phía cùng mắc một lỗi mà test vẫn xanh.

```java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Instant;
import java.util.HexFormat;
import java.util.UUID;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.ResultActions;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ChangedHeaderHmacIT {
    private static final String CLIENT_ID = "client-a";
    // Chỉ dùng secret fixture, trùng với cấu hình test ở server.
    private static final byte[] TEST_KEY =
            "integration-test-secret-only".getBytes(StandardCharsets.UTF_8);
    private static final String TARGET =
            "/v1/payments?currency=VND&orderId=42";
    private static final byte[] BODY =
            "{\"orderId\":42,\"amount\":100000}"
                    .getBytes(StandardCharsets.UTF_8);

    @Autowired MockMvc mockMvc;

    // Bộ ký ở phía test cố ý không dùng lại implementation canonical của server.
    private static String sign(String contentType, String timestamp, String nonce)
            throws Exception {
        byte[] digest = MessageDigest.getInstance("SHA-256").digest(BODY);
        String bodyHash = HexFormat.of().formatHex(digest);

        String canonical = String.join("\n",
                "v1",
                "POST",
                TARGET,
                "content-type:" + contentType.trim(),
                "x-client-id:" + CLIENT_ID,
                "x-nonce:" + nonce,
                "x-timestamp:" + timestamp,
                "body-sha256:" + bodyHash);

        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(TEST_KEY, "HmacSHA256"));
        return HexFormat.of().formatHex(
                mac.doFinal(canonical.getBytes(StandardCharsets.UTF_8)));
    }

    private ResultActions send(String contentType, String timestamp,
                               String nonce, String signature, String requestId)
            throws Exception {
        return mockMvc.perform(post("/v1/payments")
                .queryParam("currency", "VND")
                .queryParam("orderId", "42")
                .contentType(contentType)
                .header("X-Client-Id", CLIENT_ID)
                .header("X-Timestamp", timestamp)
                .header("X-Nonce", nonce)
                .header("X-Signature", "v1=" + signature)
                .header("X-Request-Id", requestId)
                .content(BODY));
    }

    @Test
    void unchangedSignedHeadersAreAccepted() throws Exception {
        String timestamp = Long.toString(Instant.now().getEpochSecond());
        String nonce = UUID.randomUUID().toString();
        String signature = sign("application/json", timestamp, nonce);

        send("application/json", timestamp, nonce, signature, "req-control")
                .andExpect(status().is2xxSuccessful());
    }

    @Test
    void changingSignedContentTypeWithoutResigningIsRejected() throws Exception {
        String timestamp = Long.toString(Instant.now().getEpochSecond());
        String nonce = UUID.randomUUID().toString();
        String signature = sign("application/json", timestamp, nonce);

        // Chỉ thay Content-Type trên đường truyền; chữ ký vẫn ký giá trị cũ.
        send("application/json; charset=UTF-8", timestamp, nonce,
                signature, "req-mutated-content-type")
                .andExpect(status().isUnauthorized());
    }

    @Test
    void changingUnsignedRequestIdDoesNotInvalidateHmac() throws Exception {
        String timestamp = Long.toString(Instant.now().getEpochSecond());
        String nonce = UUID.randomUUID().toString();
        String signature = sign("application/json", timestamp, nonce);

        // X-Request-Id không nằm trong hợp đồng ký v1.
        send("application/json", timestamp, nonce, signature, "req-modified")
                .andExpect(status().is2xxSuccessful());
    }

    @Test
    void changingSignedTimestampWithinAllowedWindowIsRejected() throws Exception {
        long now = Instant.now().getEpochSecond();
        String originalTimestamp = Long.toString(now);
        String changedTimestamp = Long.toString(now + 1);
        String nonce = UUID.randomUUID().toString();
        String signature = sign("application/json", originalTimestamp, nonce);

        send("application/json", changedTimestamp, nonce,
                signature, "req-mutated-timestamp")
                .andExpect(status().isUnauthorized());
    }
}
```

**Cách đọc kết quả:** test `changingSignedContentTypeWithoutResigningIsRejected` chỉ đáng tin nếu bộ lọc HMAC thực sự xử lý request trước controller và báo **signature mismatch**. Nếu ứng dụng trả `401` do không tìm thấy client, trả `415` vì media type, hoặc trả `403` vì thiếu quyền, cần sửa fixture hoặc điểm quan sát trước khi kết luận. Nên kiểm tra thêm mã lỗi nội bộ đã được lược bỏ thông tin nhạy cảm, metric hoặc test spy của verifier để biết chính xác nhánh từ chối. Với endpoint yêu cầu quyền riêng, fixture `client-a` phải được cấp quyền tương ứng.

Trong ứng dụng dùng **Spring WebFlux**, nguyên tắc giống hệt nhưng dùng `WebTestClient` và `WebFilter` thay cho `MockMvc` và servlet filter. Điều cần quan sát vẫn là dữ liệu header mà bộ xác minh nhận được và canonical request mà server thực sự sử dụng.

## 5. Các trường hợp dễ làm test sai

### 5.1. Thay đổi header rồi ký lại

```text
SAI MỤC TIÊU: sign(headers_moi) -> send(headers_moi, signature_moi)
ĐÚNG MỤC TIÊU: sign(headers_goc) -> send(headers_da_sua, signature_goc)
```

Trường hợp đầu kiểm tra khả năng tạo chữ ký cho một request mới. Trường hợp sau mới chứng minh HMAC phát hiện header đã bị can thiệp sau khi ký. Dữ liệu khác trong canonical request cần giữ nguyên, ngoại trừ phép biến đổi được chủ đích kiểm tra.

### 5.2. Không nhất quán quy tắc canonical hóa

- **Hoa/thường tên header:** `X-Client-Id` và `x-client-id` phải được nhìn như cùng một tên. Nếu client đưa tên về lowercase còn server giữ nguyên chữ hoa, request hợp lệ có thể bị từ chối.
- **Hoa/thường giá trị:** `client-a` và `CLIENT-A` là hai giá trị khác nhau theo hợp đồng `v1`; không được lowercase giá trị khi hợp đồng không yêu cầu.
- **Khoảng trắng:** trim OWS đầu/cuối khác với gộp khoảng trắng giữa chuỗi. Hai bên phải áp dụng đúng cùng một quy tắc.
- **Header lặp:** một số HTTP stack kết hợp các giá trị bằng dấu phẩy, số khác lấy phần tử đầu hoặc cuối. Phải có quy tắc xử lý trùng rõ ràng, ưu tiên từ chối trường hợp mơ hồ trước khi xác minh.
- **Header bắt buộc nhưng thiếu:** không coi header vắng mặt và header có giá trị rỗng là tương đương nếu hợp đồng không nêu; fail closed.
- **Byte body và URI:** không parse JSON rồi serialize lại để băm, và không đổi thứ tự query khi hợp đồng ký raw request target. Hai bên có thể nhận cùng dữ liệu nghiệp vụ nhưng tạo ra chuỗi ký khác nhau.

Nếu hợp đồng hỗ trợ `X-Signed-Headers` hoặc chọn subset header động, phải kiểm tra danh sách đó được ràng buộc vào chữ ký hoặc bị giới hạn bởi chính sách server. Client không được tùy ý bỏ một header bảo mật khỏi tập được ký để né phát hiện thay đổi.

### 5.3. Proxy/gateway thay đổi header

Khi có reverse proxy, API gateway, ingress hay service mesh, luồng xử lý có thể là:

```text
Client --(ký request)--> Gateway --(thêm/sửa header)--> HMAC verifier --> Controller
```

Gateway có thể thêm `X-Forwarded-*`, chuẩn hóa `Host`, sửa `Content-Type`, gộp header lặp hoặc thay request target. Nếu một trường đã được ký bị thay đổi trước verifier, signature mismatch là kết quả **đúng theo hợp đồng**. Cần quyết định ranh giới ký/xác minh: bảo toàn các byte và header được ký qua gateway, hoặc chuẩn hóa ở điểm được các bên tin cậy và công bố chính xác trong hợp đồng; không nới lỏng verifier để chấp nhận thay đổi tùy ý.

Một bài test tích hợp nên gửi cùng fixture qua **đường đi production-like**, đồng thời thu thập (trong môi trường an toàn) tên header được ký, phiên bản canonical và mã nguyên nhân lỗi ở phía verifier. Nếu ký `Host` hoặc `X-Forwarded-*`, phải xác định rõ giá trị nào được tin cậy và gateway nào được phép cung cấp; không lấy giá trị forwarded do client tự khai làm nguồn sự thật.

### 5.4. Trộn lẫn HMAC, replay protection và authorization

Trong một hệ thống đầy đủ, verifier thường kiểm tra timestamp có nằm trong giới hạn sai lệch đồng hồ, nonce có bị tái sử dụng, signature có hợp lệ và client có bị khóa hay không. Chỉ sau khi danh tính được xác thực mới kiểm tra quyền truy cập tài nguyên. Test phải xác định đúng lớp thất bại:

| Kiểm tra | Ví dụ | Ý nghĩa |
|---|---|---|
| HMAC integrity | Header được ký thay đổi nhưng chữ ký giữ nguyên | Chữ ký không khớp; từ chối xác thực. |
| Freshness | `X-Timestamp` đã quá hạn, dù được ký hợp lệ | Từ chối request cũ theo chính sách thời gian. |
| Replay | Cùng nonce đã được chấp nhận trước đó, chữ ký vẫn hợp lệ | Từ chối request lặp; nonce cần được ghi nhận nguyên tử và có TTL phù hợp. |
| Key lifecycle | Client dùng key bị thu hồi hoặc key version hết hiệu lực | Từ chối theo trạng thái credential/rotation. |
| Authorization | HMAC hợp lệ nhưng client thiếu quyền tạo payment | Trả `403` (hoặc mã tương đương theo API); không kết luận HMAC sai. |

Không dùng cùng nonce để chạy lần lượt nhiều positive test. Với request HMAC sai, chính sách ghi nhận nonce cũng phải có quy tắc rõ ràng, tránh cho phép request giả mạo chiếm nonce hợp lệ; kiểm tra việc ghi nhận và chống race trong một nhóm test riêng. Nếu có key rotation, cần đảm bảo key id/client id được ràng buộc và lookup secret theo chính sách server, đồng thời thử changed header với key hiện hành và key còn trong thời gian chuyển tiếp.

## 6. Tiêu chí chấp nhận và chẩn đoán lỗi

Một changed header test đạt yêu cầu khi có đủ bằng chứng sau:

1. **Baseline pass:** một request với canonical request và chữ ký hợp lệ được verifier chấp nhận; fixture có quyền gọi endpoint.
2. **Signed header fails:** thay một header được ký, giữ nguyên chữ ký gốc và các dữ liệu còn lại; verifier từ chối rõ ràng vì HMAC mismatch.
3. **Unsigned header behaves as specified:** thay header không ký vẫn hợp lệ về mặt HMAC, nhưng header có ảnh hưởng bảo mật phải được kiểm tra hoặc bổ sung vào hợp đồng ký.
4. **Normalization pass:** các biến đổi chỉ thuộc phần chuẩn hóa đã công bố (như casing tên header) không phá chữ ký.
5. **Ambiguity fails closed:** header ký bị thiếu, bị lặp hoặc chứa định dạng nguy hiểm bị từ chối nhất quán giữa HTTP stack, gateway và verifier.
6. **Side effects absent:** request HMAC sai không đi vào xử lý nghiệp vụ và không tạo payment, ghi giao dịch hoặc thực hiện thay đổi trạng thái.
7. **Observability safe:** log/metric có loại lỗi và correlation id đủ để phân tích, nhưng không ghi shared secret, khóa, canonical chứa dữ liệu nhạy cảm, toàn bộ chữ ký hay dữ liệu cá nhân của body.

Khi test thất bại ngoài dự kiến, kiểm tra theo thứ tự: header thật sự đến verifier là gì; có duplicate/gộp header hay không; canonical request có cùng version, thứ tự, LF, encoding và body hash không; timestamp và nonce có hợp lệ không; request có đi qua đúng security filter chain không; cuối cùng mới kiểm tra ánh xạ HTTP status. Đặc biệt, **không dùng duy nhất HTTP 401 làm bằng chứng signature mismatch** nếu hệ thống có nhiều nguyên nhân trả cùng mã.

## 7. Bài tập thực hành

Giữ nguyên hợp đồng `v1` và xây bảng kiểm thử tự động có tối thiểu sáu tình huống: request hợp lệ, đổi `Content-Type` sau khi ký, đổi `X-Timestamp` trong cửa sổ hợp lệ, đổi `X-Nonce` sang giá trị chưa dùng, đổi `X-Request-Id` không ký, và đổi casing tên `X-Client-Id`. Với mỗi tình huống, ghi rõ **giá trị đã ký**, **giá trị thực gửi**, **signature có được giữ nguyên không**, **lý do verifier chấp nhận/từ chối** và **có phát sinh tác dụng nghiệp vụ không**.

Sau đó bổ sung một ca gateway thay `Content-Type` trước verifier và một ca gửi hai `X-Client-Id`. Giải thích vì sao việc bỏ qua header thay đổi hoặc tự động dùng một trong hai giá trị có thể làm mất ràng buộc danh tính. Kết quả mong đợi của bài tập là bộ test có thể phân biệt được lỗi canonicalization, lỗi toàn vẹn chữ ký, lỗi chống replay và lỗi phân quyền.
