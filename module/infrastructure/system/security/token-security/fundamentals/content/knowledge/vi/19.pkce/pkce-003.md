# Code challenge methods

Trong OAuth 2.0 Authorization Code flow, một ứng dụng gửi `response_type=code` và chờ authorization server (AS) chuyển trình duyệt về callback với **authorization code**. Nếu kẻ tấn công chặn được code trước khi ứng dụng đổi nó, liệu họ có thể tự gọi token endpoint để lấy access token? **PKCE (Proof Key for Code Exchange)** làm giảm nguy cơ đó bằng cách ràng buộc authorization code với một bí mật ngẫu nhiên tạm thời của **chính authorization transaction**.

Tham số **`code_challenge_method`** xác định cách client tạo **`code_challenge`** từ **`code_verifier`**. Hai method được định nghĩa trong RFC 7636 là **`S256`** và **`plain`**. Chúng không có mức bảo vệ tương đương: **`S256` là lựa chọn cần ưu tiên và nên được bắt buộc trong hệ thống hiện đại**; `plain` bộc lộ verifier qua authorization request, làm giảm khả năng chống lại một số mô hình chặn request.

Bài thuộc chương **PKCE** của module `SECURITY_TOKEN_SECURITY_FUNDAMENTALS`. Nội dung tập trung vào code challenge methods, quy tắc chuỗi và entropy, công thức S256, toàn bộ authorization/token exchange, kiểm tra phía AS, bảo vệ chống downgrade/code interception, Java và JavaScript, Spring Security, cùng quan hệ giữa PKCE và JWT, opaque token, access/refresh token trong OAuth 2.0/OIDC.

## 1. Ba giá trị phải phân biệt: verifier, challenge và method

| Giá trị | Ai tạo? | Được dùng tại đâu? | Có phải bí mật? |
|---|---|---|---|
| **`code_verifier`** | OAuth client, mới cho mỗi authorization transaction. | Gửi tới **token endpoint** khi đổi authorization code. | **Có**: cần bảo vệ khỏi bên không được phép đổi code. |
| **`code_challenge`** | Client dẫn xuất từ verifier. | Gửi tới **authorization endpoint**, được AS liên kết với code. | Không phải secret độc lập khi dùng `S256`; vẫn phải bảo vệ tính toàn vẹn của transaction. |
| **`code_challenge_method`** | Client chọn từ method AS hỗ trợ. | Gửi cùng challenge tại **authorization endpoint**. | Không phải secret; quyết định cách AS kiểm tra verifier. |

Ví dụ có PKCE:

```text
Authorization request:
  response_type=code
  client_id=orders-web
  code_challenge=E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM
  code_challenge_method=S256

Token request:
  grant_type=authorization_code
  code=AUTHORIZATION_CODE_PLACEHOLDER
  code_verifier=dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk
```

Hai chuỗi verifier/challenge ở đây là **test vector công khai từ RFC 7636**, dùng để kiểm tra thuật toán — **không được tái sử dụng làm bí mật trong hệ thống thật**. Authorization code trong ví dụ chỉ là placeholder.

**Quy tắc bắt buộc:** verifier không đi trong authorization URL như một tham số PKCE. AS chỉ biết challenge từ request ban đầu; khi đổi code, AS nhận verifier và kiểm tra rằng nó sinh ra challenge đã lưu.

## 2. Tại sao cần PKCE trong Authorization Code flow?

Authorization Code flow tách hai kênh:

1. **Front channel:** trình duyệt/external user-agent đi tới authorization endpoint và nhận redirect mang authorization code.
2. **Token exchange:** client gọi token endpoint với code cùng các ràng buộc cần thiết để lấy access token.

Authorization code có thể lộ qua deep-link hijacking, log URL callback, browser extension, ứng dụng khác đăng ký cùng private-use URI scheme, open redirect hoặc client environment bị chiếm quyền. Code bản thân phải ngắn hạn, dùng một lần và bị ràng buộc với client/redirect, nhưng **public client không thể bảo vệ client secret cố định**.

```mermaid
flowchart TD
    C[Client sinh verifier ngẫu nhiên] --> H[Tạo S256 challenge]
    H --> A[Authorization request: challenge + method]
    A --> AS[Authorization Server xác thực / cấp code]
    AS --> R[Redirect callback có code]
    R --> T[Client gửi code + verifier tới token endpoint]
    T --> V{AS tính lại challenge và so với bản đã lưu?}
    V -- Sai --> D[invalid_grant / từ chối]
    V -- Đúng --> B{Code còn hạn, chưa dùng, đúng client/redirect?}
    B -- Sai --> D
    B -- Đúng --> I[Đổi code một lần; phát token đúng grant]
```

Kẻ tấn công lấy được **code nhưng không có verifier** sẽ không thể vượt phép kiểm PKCE nếu AS thực hiện đúng và method không bị downgrade. PKCE không chứng minh người trình **access token** sau đó là người dùng hợp pháp: bearer access token bị đánh cắp vẫn có thể bị phát lại khi còn hợp lệ.

## 3. Hai code challenge methods trong RFC 7636

| Đặc tính | `S256` | `plain` |
|---|---|---|
| Cách tạo challenge | `BASE64URL(SHA256(ASCII(code_verifier)))` | `code_challenge = code_verifier` |
| Verifier có lộ trực tiếp trong authorization request? | **Không**; chỉ có digest được mã hóa Base64URL. | **Có**, vì challenge chính là verifier. |
| Bảo vệ khi attacker thấy authorization request/challenge nhưng không thấy verifier | Có, dựa trên verifier entropy cao và tính chất tiền ảnh của SHA-256. | Không; attacker học được verifier từ challenge. |
| Hỗ trợ trong RFC 7636 | Method chuẩn, AS triển khai PKCE phải hỗ trợ. | Method có trong chuẩn để tương thích trường hợp hạn chế. |
| Khuyến nghị triển khai mới | **Dùng và enforce** nếu hệ thống hỗ trợ. | Tránh; chỉ xem xét ngoại lệ tương thích có đánh giá rủi ro. |
| Giá trị gửi trong token request | Verifier **gốc**, không phải challenge. | Verifier gốc (trùng challenge). |

### Phương thức `S256`

Định nghĩa:

```text
code_challenge = BASE64URL-ENCODE(
    SHA256(ASCII(code_verifier))
)
```

- `ASCII(code_verifier)`: chuyển chuỗi verifier sang bytes ASCII theo charset hợp lệ.
- `SHA256(...)`: hàm băm SHA-256 trả về **32 bytes**.
- `BASE64URL-ENCODE(...)`: mã hóa theo alphabet URL-safe, **bỏ ký tự padding `=`**.
- Kết quả S256 chuẩn cho 32 bytes SHA-256 thường dài **43 ký tự**.

**SHA-256 không phải mã hóa có khóa**, không phải chữ ký số và không có thao tác “giải mã” challenge về verifier. Tính bảo mật chống đoán dựa trên **verifier đủ entropy** và cấu trúc một chiều của hàm băm.

### Phương thức `plain`

Định nghĩa:

```text
code_challenge = code_verifier
```

AS xác nhận verifier tại token endpoint **bằng đúng** challenge đã lưu. Nếu attacker có thể đọc authorization request, họ có thể biết verifier ngay cả khi chưa đọc token request.

RFC 7636 có `plain` để tương thích một số client bị hạn chế khả năng băm. Tuy nhiên, ứng dụng hiện đại (Java backend, browser Web Crypto, mobile OS APIs) thường hỗ trợ SHA-256; **không nên chọn `plain` vì dễ code hơn**.

## 4. Giá trị mặc định khi thiếu `code_challenge_method`

Theo RFC 7636, nếu client **đã gửi `code_challenge` nhưng không gửi `code_challenge_method`**, AS xử lý như **`plain`** theo quy tắc mặc định của đặc tả.

Ví dụ:

```text
code_challenge=abc...
# Không có code_challenge_method
=> RFC 7636 diễn giải method là "plain", không phải "S256".
```

Hệ quả:

- Không được cho rằng mọi request có `code_challenge` đều đang dùng S256.
- Một policy **chỉ cho phép S256** phải từ chối request thiếu method dù RFC định nghĩa default là plain.
- Một request không có **cả challenge và method** không tự trở thành PKCE flow; nếu client/profile bắt buộc PKCE thì AS phải từ chối, không cấp code thiếu ràng buộc.
- Một client gửi `code_challenge_method=S256` nhưng không có challenge là request lỗi, không được âm thầm bỏ PKCE.
- Method không được nhận diện (ví dụ `S512` không có đăng ký/hỗ trợ) phải bị từ chối; không tự fallback.

**Không thực hiện downgrade “thử S256, nếu lỗi thì thử plain”**: client và server cần thỏa thuận method hợp lệ từ đầu và lưu method đó gắn với authorization code.

## 5. Syntax và entropy của `code_verifier`

RFC 7636 quy định:

```text
code-verifier = 43*128unreserved

unreserved = ALPHA / DIGIT / "-" / "." / "_" / "~"
```

Nghĩa là verifier phải có độ dài **từ 43 đến 128 ký tự ASCII**, và mỗi ký tự phải thuộc một trong các nhóm:

- Chữ cái `A–Z`, `a–z`.
- Chữ số `0–9`.
- Các ký tự `- . _ ~`.

Không có khoảng trắng, dấu `+`, `/`, `=`, xuống dòng hoặc Unicode tùy ý.

**Độ dài không đồng nghĩa entropy**. Một chuỗi 128 chữ `A` vẫn rất dễ đoán. Verifier phải được sinh bằng **CSPRNG** (cryptographically secure pseudorandom number generator), mới cho mỗi authorization transaction, không dùng timestamp, user ID, số tăng dần hay hàm ngẫu nhiên không phù hợp bảo mật.

### Cách sinh verifier thông dụng

Sinh **32 bytes ngẫu nhiên** rồi mã hóa Base64URL **không padding**:

```text
randomBytes = CSPRNG(32 bytes)
code_verifier = BASE64URL(randomBytes)
=> 43 ký tự, tương ứng khoảng 256 bit entropy
```

Đây là cách RFC 7636 khuyến nghị để thu được verifier có entropy đủ cao. Không cần sinh một verifier dài 128 ký tự nếu 32 bytes ngẫu nhiên đã đáp ứng mức bảo mật; dài hơn không bù được lỗi để lộ verifier.

**Vòng đời:** mỗi lần mở authorization transaction cần verifier mới, ràng buộc với transaction và xóa sau khi code exchange kết thúc hoặc thất bại. Không ghi vào log, analytics, crash report, callback query hoặc browser URL.

## 6. Test vector S256 chuẩn để tự kiểm chứng

RFC 7636 đưa ra verifier:

```text
dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk
```

Challenge S256 tương ứng:

```text
E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM
```

Một triển khai đúng phải tạo ra kết quả **chính xác** trên từ verifier đã nêu.

| Bước | Dữ liệu/biến đổi | Điều cần nhớ |
|---|---|---|
| 1 | Verifier ASCII bytes | Không chuẩn hóa Unicode hay thêm xuống dòng. |
| 2 | SHA-256 trên verifier bytes | Dùng hash SHA-256 thật, không tự tạo hàm băm. |
| 3 | Base64URL trên 32-byte digest | Sử dụng `-` và `_` thay `+` và `/`; bỏ padding. |
| 4 | So khớp challenge | So sánh chính xác chuỗi/bytes; không ignore case. |

**Không Base64URL verifier rồi lại hash chuỗi Base64URL đó** nếu verifier đã là chuỗi cuối cùng. Công thức S256 hash trực tiếp **ASCII bytes của chuỗi verifier được gửi tới token endpoint**.

### Lỗi thường gặp ở test vector

- Gọi `SHA256(UTF-16 bytes)` thay vì bytes ASCII.
- Dùng Base64 thông thường có `+`, `/` hoặc thêm `=`.
- Băm dữ liệu hex string của verifier thay vì verifier nguyên gốc.
- Có newline `\n` trong chuỗi từ terminal.
- Trả challenge là hexadecimal SHA-256 digest (64 ký tự hex) thay vì Base64URL.
- Dùng Base64URL của verifier làm S256 challenge mà không băm.

Những lỗi này thường khiến code exchange trả `invalid_grant` dù authorization redirect ban đầu vẫn thành công.

## 7. Authorization request gửi challenge và method

Client tạo verifier/challenge, lưu verifier an toàn trong một transaction và bắt đầu luồng đăng nhập.

Ví dụ authorization request (trình bày nhiều dòng để đọc; khi truyền thực phải URL-encode chuẩn và nằm trên request target hợp lệ):

```http
GET /oauth2/authorize?
  response_type=code&
  client_id=orders-web&
  redirect_uri=https%3A%2F%2Fapp.example.test%2Flogin%2Fcallback&
  scope=openid%20orders.read&
  state=RANDOM_TRANSACTION_STATE&
  code_challenge=E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM&
  code_challenge_method=S256
HTTP/1.1
Host: id.example.test
```

Ở đây `state` phải được tạo ngẫu nhiên cho transaction, còn challenge dùng test vector **chỉ phục vụ minh họa**.

**Trường `code_verifier` không xuất hiện trong authorization request**. Nếu nó xuất hiện, attacker có thể lấy trực tiếp verifier khi URL hoặc logs bị lộ và PKCE mất tác dụng bảo vệ theo thiết kế.

### `response_type` và `code_challenge_method` khác nhau

| Tham số | Bên nhận | Ý nghĩa |
|---|---|---|
| `response_type=code` | Authorization endpoint | AS trả authorization **code** qua redirect. |
| `code_challenge_method=S256` | Authorization endpoint | AS dùng S256 để kiểm chứng verifier trong bước đổi code. |
| `grant_type=authorization_code` | Token endpoint | Client đang đổi authorization code lấy tokens. |

Method PKCE không quyết định AS cấp **JWT hay opaque access token**, có cấp **refresh token** hay không, hoặc access token có những scope nào. Đó là các quyết định khác của AS và token profile.

## 8. Toàn bộ luồng S256: from challenge to token

```mermaid
sequenceDiagram
    autonumber
    actor U as Resource Owner
    participant C as OAuth/OIDC Client
    participant B as Browser / External User-Agent
    participant AS as Authorization Server
    participant RS as Orders Resource Server
    C->>C: CSPRNG tạo verifier + challenge S256 + state
    C->>B: Redirect authorization request
    B->>AS: response_type=code, challenge, method=S256, state
    AS->>AS: Kiểm tra client, redirect, scope; lưu challenge/method
    AS->>U: Authentication / consent nếu cần
    AS-->>B: Redirect callback với code + state (+ iss nếu áp dụng)
    B->>C: Gửi code tới callback
    C->>C: Kiểm tra state, issuer và transaction
    C->>AS: POST token: code, verifier, grant_type=authorization_code
    AS->>AS: Tính BASE64URL(SHA256(ASCII(verifier)))
    AS->>AS: So khớp challenge đã lưu và kiểm tra code binding
    AS-->>C: Access token; ID/refresh token nếu được cấp
    C->>RS: Authorization: Bearer access token
    RS->>RS: JWT/opaque validation, aud, scope, quyền resource
    RS-->>C: Kết quả API
```

Hai thời điểm không được nhầm:

- **Khi cấp authorization code:** AS lưu method và challenge gắn với code/authorization transaction.
- **Khi đổi code:** AS nhận verifier rồi dùng **method đã lưu** để tính challenge và so sánh.

Client không được thay method từ S256 sang plain ở token endpoint. Token endpoint không nhận `code_challenge_method` như một đề nghị chọn thuật toán mới; nó phải dùng **method gắn với code do AS lưu**.

## 9. Token exchange và quy tắc kiểm tra phía AS

Client gửi HTTP POST tới **token endpoint của issuer đã chọn**:

```http
POST /oauth2/token HTTP/1.1
Host: id.example.test
Content-Type: application/x-www-form-urlencoded
Authorization: Basic CLIENT_AUTH_PLACEHOLDER

grant_type=authorization_code&
code=AUTHORIZATION_CODE_PLACEHOLDER&
redirect_uri=https%3A%2F%2Fapp.example.test%2Flogin%2Fcallback&
code_verifier=dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk
```

Payload được xuống dòng cho dễ đọc; request thực tế cần form-url-encode đúng. Header Basic ở đây minh họa **confidential client**; public SPA/mobile không được nhúng client secret cố định rồi gọi đó là confidential client. AS có thể yêu cầu `client_id` cho public client theo hợp đồng.

### Checklist của authorization server

1. Xác minh **issuer/token endpoint**, client ID và client authentication theo đăng ký.
2. Tìm authorization code và đảm bảo code được phát cho **đúng client**.
3. Xác nhận code **chưa dùng**, **chưa hết hạn**, đúng redirect URI/transaction.
4. Lấy **`code_challenge` và `code_challenge_method` đã lưu khi phát code**.
5. Xác minh syntax, độ dài verifier; từ chối nếu thiếu verifier khi PKCE bắt buộc.
6. Nếu method `S256`: tính lại S256 từ verifier; nếu `plain` được chính sách cho phép: so sánh verifier với challenge.
7. So sánh kết quả chính xác và theo phương thức so sánh tránh rò rỉ thời gian khi phù hợp.
8. **Consume code một lần theo cơ chế nguyên tử**, không để hai node cùng cấp token từ một code.
9. Phát access token theo **scope/resource/grant đã cấp**, không tự nâng quyền dựa vào token request.
10. Ghi audit bằng transaction reference, mã lỗi; **không ghi raw code, verifier hoặc tokens**.

### Pseudocode AS đúng định hướng

```text
exchangeAuthorizationCode(code, verifier, client, redirectUri):
    transaction = findCodeTransaction(code)
    if transaction missing/expired/used:
        reject invalid_grant

    check client binding, redirect URI, issuer and grant status

    if transaction.PKCE_required:
        require verifier matches PKCE syntax
        if transaction.method == "S256":
            expected = BASE64URL(SHA256(ASCII(verifier)))
        else if transaction.method == "plain" AND policy explicitly allows:
            expected = verifier
        else:
            reject invalid_grant

        require constant-time comparison(expected, transaction.challenge)
    else:
        follow explicit non-PKCE compatibility policy, never downgrade silently

    atomically consume the code, then issue permitted tokens
```

Đây là thuật toán khái niệm, không phải một đoạn code AS production đầy đủ. Triển khai phải giải quyết transaction, concurrency, timeouts, crash giữa consume và phát token, replay detection, logging và chính sách tương thích legacy.

## 10. Mẫu Java tạo `code_verifier` và `S256` challenge

Java hỗ trợ `SecureRandom`, `MessageDigest` và Base64URL encoder. Ví dụ có thể biên dịch ở Java hiện đại:

```java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.SecureRandom;
import java.util.Base64;

public final class PkceSupport {

    private static final SecureRandom RANDOM = new SecureRandom();
    private static final Base64.Encoder BASE64_URL =
            Base64.getUrlEncoder().withoutPadding();

    private PkceSupport() { }

    public static String generateVerifier() {
        byte[] random = new byte[32];  // 256 bit
        RANDOM.nextBytes(random);
        return BASE64_URL.encodeToString(random); // 43 ký tự
    }

    public static String s256Challenge(String verifier) {
        try {
            byte[] bytes = verifier.getBytes(StandardCharsets.US_ASCII);
            byte[] digest = MessageDigest.getInstance("SHA-256")
                    .digest(bytes);
            return BASE64_URL.encodeToString(digest);
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException("SHA-256 unavailable", e);
        }
    }

    public static void main(String[] args) {
        String knownVerifier =
                "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk";
        String expected =
                "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM";

        if (!expected.equals(s256Challenge(knownVerifier))) {
            throw new IllegalStateException("PKCE vector mismatch");
        }

        String freshVerifier = generateVerifier();
        String freshChallenge = s256Challenge(freshVerifier);

        // Trong sản phẩm, lưu verifier trong authorization transaction.
        // Chỉ đưa freshChallenge vào URL của authorization endpoint.
        System.out.println("S256 challenge length=" + freshChallenge.length());
    }
}
```

Mẫu này không cố gắng kiểm tra cú pháp verifier bên ngoài; nếu method nhận verifier không đáng tin, cần validate theo RFC trước khi băm. `US_ASCII` chỉ an toàn khi đầu vào thuộc tập ký tự RFC 7636; không dùng mã hóa thay thế âm thầm với Unicode ngoài tập này. Đừng xuất `freshVerifier` ra logs hoặc gửi nó cho resource server.

### Kiểm tra cú pháp verifier bằng Java

```java
private static final java.util.regex.Pattern VERIFIER =
    java.util.regex.Pattern.compile("^[A-Za-z0-9._~-]{43,128}$");

public static boolean isValidVerifier(String value) {
    return value != null && VERIFIER.matcher(value).matches();
}
```

Regex chỉ xác nhận **độ dài và charset**, không chứng minh chuỗi có entropy tốt. Một chuỗi lặp 43 chữ `A` vẫn qua regex nhưng **không nên được client tạo ra**.

## 11. JavaScript/browser: dùng Web Crypto, không dùng `Math.random()`

Browser có thể tạo verifier và tính S256 challenge bằng Web Crypto API trong secure context.

```javascript
const base64Url = (bytes) => {
  let binary = "";
  for (const value of bytes) {
    binary += String.fromCharCode(value);
  }
  return btoa(binary)
    .replaceAll("+", "-")
    .replaceAll("/", "_")
    .replace(/=+$/, "");
};

function createVerifier() {
  const random = new Uint8Array(32);
  crypto.getRandomValues(random);
  return base64Url(random);
}

async function createS256Challenge(verifier) {
  const bytes = new TextEncoder().encode(verifier);
  const hash = await crypto.subtle.digest("SHA-256", bytes);
  return base64Url(new Uint8Array(hash));
}

async function beginAuthorization() {
  const verifier = createVerifier();
  const challenge = await createS256Challenge(verifier);
  // Lưu verifier trong state của transaction theo mô hình app.
  // Chỉ đưa challenge + method=S256 tới authorization endpoint.
  return { verifier, challenge, challengeMethod: "S256" };
}
```

`TextEncoder` cho UTF-8 bytes, nhưng với **verifier RFC 7636 chỉ gồm ASCII** thì UTF-8 và ASCII cho cùng dãy bytes; không áp dụng hàm cho chuỗi Unicode không hợp lệ. Đây là ví dụ minh họa; trong ứng dụng thật còn cần **`state`, storage theo transaction, issuer binding, redirect URI, code exchange và cleanup**.

Một SPA không thể biến client secret thành bí mật bằng cách nhúng vào JavaScript. **PKCE không làm browser thành confidential client**. Nếu có điều kiện, cân nhắc mô hình BFF để giữ token phía server.

## 12. Phía AS kiểm chứng S256 an toàn trong Java

Một mẫu verifier độc lập (thành phần kiểm tra PKCE) có thể viết như sau:

```java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.Base64;
import java.util.regex.Pattern;

public final class PkceVerifier {

    private static final Pattern SYNTAX =
            Pattern.compile("^[A-Za-z0-9._~-]{43,128}$");

    public static boolean matches(
            String verifier,
            String storedChallenge,
            String storedMethod) {

        if (verifier == null || !SYNTAX.matcher(verifier).matches()) {
            return false;
        }
        if (storedChallenge == null) {
            return false;
        }

        String computed;
        if ("S256".equals(storedMethod)) {
            try {
                byte[] digest = MessageDigest.getInstance("SHA-256")
                        .digest(verifier.getBytes(StandardCharsets.US_ASCII));
                computed = Base64.getUrlEncoder()
                        .withoutPadding()
                        .encodeToString(digest);
            } catch (NoSuchAlgorithmException ex) {
                throw new IllegalStateException(ex);
            }
        } else {
            // S256-only policy: từ chối plain, null, method chưa biết.
            return false;
        }

        byte[] actual = computed.getBytes(StandardCharsets.US_ASCII);
        byte[] expected =
                storedChallenge.getBytes(StandardCharsets.US_ASCII);
        return MessageDigest.isEqual(actual, expected);
    }
}
```

**Đây chỉ là hàm so sánh challenge** trong một hệ thống **chỉ chấp nhận S256**. Authorization server thật còn phải tự lưu challenge/method gắn với code, kiểm tra client, redirect URI, grant, thời hạn, trạng thái một lần và xử lý race/transaction. Không để client gửi `storedMethod` hoặc `storedChallenge` tùy ý ở bước token exchange.

Một lỗi nguy hiểm là **không tìm thấy challenge trong code record rồi trả true** để “tương thích client cũ”. Nếu hệ thống yêu cầu PKCE, thiếu challenge phải khiến token exchange thất bại. Không được chấp nhận challenge do client cung cấp **sau khi** code đã phát hành.

## 13. Chống downgrade từ S256 xuống plain hoặc không có PKCE

*Downgrade* là làm yếu cơ chế PKCE trong khi các bên tưởng rằng vẫn đang dùng S256.

### Các trường hợp điển hình

| Tình huống | Vì sao nguy hiểm? | Phản ứng đúng khi policy S256-only |
|---|---|---|
| Client quên `code_challenge_method` nhưng có challenge. | Theo RFC, method mặc định thành `plain`. | Từ chối authorization request. |
| Client gửi `code_challenge_method=plain`. | Challenge chính là verifier, dễ lộ qua authorization URL. | Từ chối. |
| Client gửi `S256` nhưng challenge bị proxy/thư viện xóa. | Code có thể bị phát không ràng buộc. | Từ chối, không bỏ PKCE. |
| AS “fallback” sang so sánh plain sau khi S256 mismatch. | Attacker có thể chọn cách yếu hơn. | Từ chối `invalid_grant`. |
| Token request tự gửi method=plain nhằm ghi đè record đã lưu S256. | Client chi phối thuật toán sau khi code phát hành. | Bỏ qua/từ chối tham số không hợp đồng; dùng method đã lưu. |
| Có verifier sai nhưng AS vẫn phát token vì client đã xác thực bằng secret. | PKCE bị vô hiệu dù đã cam kết trên authorization code. | Từ chối; xác thực client không thay PKCE. |
| AS nhận method viết `s256`, `S-256`, `S512` tùy ý. | Nhầm thuật toán/behavior không được đăng ký. | Chỉ nhận tên method được hỗ trợ chính xác. |
| Client dùng verifier tĩnh mỗi lần đăng nhập. | Attacker học một verifier có thể khai thác các transaction khác. | Sinh verifier mới bằng CSPRNG cho mỗi transaction. |

Trong môi trường legacy còn yêu cầu `plain`, hãy tách **chính sách cho đúng client/profile**, thời gian loại bỏ và giám sát; không âm thầm downgrade toàn bộ hệ thống. Dù cho phép plain về cú pháp, AS vẫn phải kiểm chứng verifier và bind code đúng client/redirect.

**Lưu ý tinh tế:** Tham số `code_challenge_method` là do client gửi, không cần bí mật, nhưng **AS phải cố định method đã chọn vào authorization transaction**. Nếu method có thể bị thay lúc đổi code, mô hình bảo vệ mất nghĩa.

## 14. Vai trò của PKCE với `state`, `nonce` và issuer

PKCE giải quyết một phần quan trọng của code interception, nhưng không thay những bảo vệ khác.

| Cơ chế | Bảo vệ mục tiêu gì? | Có thay PKCE không? |
|---|---|---|
| **`state`** | Ràng buộc authorization response với transaction/client session; chống CSRF/response injection. | Không. |
| **`nonce` trong OIDC** | Ràng buộc ID token với yêu cầu đăng nhập, khi được sử dụng theo profile. | Không. |
| **PKCE S256** | Ràng buộc authorization code với bên giữ verifier. | Là cơ chế riêng cho code exchange. |
| **Issuer binding/RFC 9207** | Chống nhầm authorization server, nhất là multi-AS. | Không. |
| **Exact redirect URI** | Tránh code được gửi tới callback không đăng ký hoặc bị chuyển sai. | Không. |
| **Client authentication** | Chứng minh confidential client tại token endpoint. | Bổ sung, không thay PKCE. |
| **Audience/scope của access token** | Giới hạn resource server và hành động token được cấp. | Không. |
| **DPoP hoặc mTLS** | Ràng buộc token với bên giữ khóa phù hợp nhằm giảm replay. | Không; áp dụng ở lớp token khác. |

Ví dụ client nhận callback với `state` sai nhưng code vẫn khớp verifier. **Không được tiếp tục token exchange** vì transaction/phiên có thể bị nhầm hoặc bị attacker cài response. Ngược lại, `state` đúng nhưng verifier sai cũng phải thất bại ở token endpoint.

### PKCE có chống login CSRF hoàn toàn không?

Không nên tuyên bố vậy. PKCE có thể hỗ trợ ràng buộc transaction, nhưng client vẫn phải thực thi **CSRF/transaction binding** phù hợp và issuer validation. Browser có thể có nhiều tab, nhiều authorization transactions; cần lưu verifier theo **transaction identity**, không dùng một global verifier bị ghi đè khi tab khác bắt đầu login.

## 15. PKCE trong BFF, SPA và mobile

| Môi trường | Nơi sinh/lưu verifier | Cách đổi code | Điểm cần bảo vệ |
|---|---|---|---|
| **Web backend/BFF** | Backend sinh và lưu tạm trong authorization request repository/server session. | Backend gọi AS token endpoint. | Session/CSRF, secure cookie, multi-tab isolation, code binding, client authentication. |
| **SPA public client** | Browser runtime và transaction storage theo kiến trúc. | Browser gọi token endpoint khi AS cho phép. | XSS, state/issuer binding, PKCE S256, token storage, CORS. |
| **Mobile native public client** | App tạo verifier bằng OS CSPRNG, lưu trong transaction. | App gọi token endpoint qua TLS. | External user-agent, app link/redirect, lifecycle và Keychain/Keystore cho refresh token. |
| **Desktop native** | App tạo verifier và lưu theo flow. | Native token request. | System browser, loopback/private-use URI theo RFC 8252, PKCE. |

### BFF

Với BFF, browser thường **không cần thấy verifier hoặc OAuth tokens**; backend giữ các bí mật của authorization transaction và đổi code phía server. Sau login, browser giữ session cookie được bảo vệ thay vì refresh token OAuth trong JavaScript.

**Không coi cookie `HttpOnly` là thay thế CSRF defense.** BFF vẫn cần session validation, cookie `Secure`/`SameSite` thích hợp, chống session fixation và authorization trên API.

### SPA

SPA không giữ được static client secret như confidential backend. JavaScript có thể dùng Web Crypto để triển khai S256; không có lý do phổ biến để downgrade `plain`. Khi nhận refresh token, cần cơ chế rotation hoặc sender constraint cho public client theo chính sách và RFC 9700; cân nhắc BFF cho dữ liệu nhạy cảm.

### Mobile

Theo RFC 8252, native apps nên sử dụng **external user-agent** (system browser/secure tabs), không dùng embedded webview kiểm soát màn hình đăng nhập. App phải chống code interception qua redirect/deep link bằng PKCE và policy redirect hợp lệ. **PKCE không ngăn một runtime đã bị chiếm quyền đọc verifier**, nên vẫn cần bảo vệ thiết bị, app links, lưu trữ và phiên.

## 16. Spring Security OAuth2 Client: cấu hình PKCE S256

Spring Security có hỗ trợ PKCE trong các luồng OAuth2 Client. Ví dụ đăng ký một **confidential web client** với issuer tin cậy:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          orders-login:
            provider: orders-idp
            client-id: "ORDERS_CLIENT_ID_PLACEHOLDER"
            client-secret: "ORDERS_CLIENT_SECRET_FROM_SECRET_MANAGER"
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: openid,profile,orders.read
        provider:
          orders-idp:
            issuer-uri: "https://id.example.test"
```

**Các chuỗi `PLACEHOLDER` và `FROM_SECRET_MANAGER` không phải secrets thật.** Confidential client phải đọc secret từ cơ chế quản lý cấu hình an toàn. Public SPA/mobile không được nhúng cùng client secret vào bundle/app package.

Trong Spring Security 6.x, có thể tùy biến authorization request resolver để thêm PKCE:

```java
@Configuration
public class OAuthLoginSecurityConfig {

    @Bean
    SecurityFilterChain webSecurity(
            HttpSecurity http,
            ClientRegistrationRepository registrations) throws Exception {

        DefaultOAuth2AuthorizationRequestResolver resolver =
                new DefaultOAuth2AuthorizationRequestResolver(
                    registrations, "/oauth2/authorization");

        resolver.setAuthorizationRequestCustomizer(
                OAuth2AuthorizationRequestCustomizers.withPkce());

        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/health").permitAll()
                .anyRequest().authenticated());

        http.oauth2Login(login -> login.authorizationEndpoint(
                endpoint -> endpoint.authorizationRequestResolver(resolver)));

        return http.build();
    }
}
```

Đây là ví dụ cấu hình cho **Spring Security servlet OAuth2 Login**, bỏ `import` và cấu hình session/CSRF/authorized-client persistence. Framework có thể tự thêm PKCE trong một số trường hợp và phiên bản; cấu hình rõ ràng cần được **kiểm chứng bằng integration test** rằng authorization request thực tế có `code_challenge_method=S256`, token request có verifier và AS kiểm tra đúng. Không tự suy rằng khai báo resolver hoặc chỉ dùng `issuer-uri` đã bảo đảm toàn bộ security policy.

Nếu AS hoặc thư viện hỗ trợ `code_challenge_methods_supported` trong metadata (RFC 8414), giá trị `S256` thường được công bố. **Discovery là khả năng**, không phải bảo đảm một client đã gửi PKCE hay AS đã enforce PKCE cho request cụ thể. Cần kiểm thử luồng thật.

## 17. Code challenge methods và AS metadata

OAuth 2.0 Authorization Server Metadata (RFC 8414) định nghĩa trường **`code_challenge_methods_supported`**, ví dụ:

```json
{
  "issuer": "https://id.example.test",
  "authorization_endpoint": "https://id.example.test/oauth2/authorize",
  "token_endpoint": "https://id.example.test/oauth2/token",
  "code_challenge_methods_supported": ["S256"]
}
```

Một số AS có thể hỗ trợ thêm `plain` vì tương thích:

```json
{
  "code_challenge_methods_supported": ["S256", "plain"]
}
```

**Không nhầm khả năng AS với lựa chọn của client:**

- AS hỗ trợ S256 ⇒ client **nên chọn S256** và gửi tham số method rõ ràng.
- AS hỗ trợ plain ⇒ không có nghĩa client buộc phải sử dụng plain.
- Metadata không có trường PKCE ⇒ cần xem hồ sơ/triển khai AS, không tự giả định “AS không hỗ trợ, hãy bỏ PKCE”.
- Metadata do một issuer khác cung cấp ⇒ không được tin, dù danh sách method phù hợp.
- Tên method phải so khớp theo registry/hợp đồng; **không tự dùng một method “tự nghĩ ra”** rồi bắt AS tính tương tự.

**Metadata không phải nơi lưu verifier/challenge của một transaction.** Những giá trị tạm thời đó nằm trong authorization request/code record của chính AS và client.

## 18. Khi PKCE thành công: token vẫn cần validation và authorization

Sau token exchange thành công, AS có thể trả:

```json
{
  "access_token": "ACCESS_TOKEN_PLACEHOLDER",
  "token_type": "Bearer",
  "expires_in": 600,
  "scope": "orders.read"
}
```

Với OIDC, token response có thể kèm **ID token**, và nếu chính sách cho phép có thể kèm **refresh token**. PKCE **không quy định định dạng token**: access token có thể là JWT hoặc opaque.

| Credential | Mục đích | Liên hệ với PKCE |
|---|---|---|
| **Authorization code** | Được đổi một lần tại token endpoint. | PKCE trực tiếp bảo vệ việc đổi code. |
| **JWT access token** | Credential cho resource server, có claims và chữ ký theo profile. | RS vẫn kiểm chữ ký, `iss`, `aud`, `exp`, scope, loại token. |
| **Opaque access token** | Credential cần RS kiểm tra trạng thái/metadata tin cậy. | Introspection/tra cứu vẫn cần `active`, audience, scope và policy. |
| **ID token (OIDC)** | RP xác minh authentication và danh tính user. | Không thay access token; client kiểm `aud`, issuer, signature, `nonce` khi áp dụng. |
| **Refresh token** | Xin access token mới ở AS. | Không được bảo vệ chỉ nhờ PKCE ban đầu; cần rotation/sender constraint, TTL/revocation. |

### Audience và scope giảm tác động khi token lộ

Ví dụ token được cấp cho `aud=orders-api`, `scope=orders.read`. Payments API phải từ chối vì **audience sai**; Orders API phải từ chối hành động `orders.approve` vì **scope thiếu**. Tuy nhiên, nếu kẻ tấn công lấy được Bearer access token còn hạn, họ **vẫn có thể dùng token để đọc tài nguyên nằm trong quyền được cấp**.

PKCE **không chống replay Bearer token sau khi phát hành**. Sender-constrained access token như DPoP (RFC 9449) hoặc mTLS (RFC 8705), bảo vệ storage, lifetime ngắn, revocation và object-level authorization là các lớp tiếp theo.

## 19. Mã lỗi và xử lý sự cố PKCE

| Bước | Lỗi | Cách xử lý |
|---|---|---|
| Authorization request | `code_challenge` thiếu trong luồng bắt buộc. | AS từ chối request, không phát code thiếu PKCE. |
| Authorization request | Method `plain` nhưng policy S256-only. | AS từ chối, không fallback. |
| Authorization request | Method không được hỗ trợ. | AS trả authorization error phù hợp, ví dụ `invalid_request` theo ngữ cảnh. |
| Authorization request | Challenge sai syntax/độ dài. | AS từ chối sớm. |
| Token request | Thiếu verifier hoặc verifier không hợp lệ. | AS từ chối, thường `invalid_grant` trong flow đổi code. |
| Token request | S256(verifier) khác challenge đã lưu. | `invalid_grant`, không cấp token. |
| Token request | Code đã hết hạn/đã được dùng. | `invalid_grant`, chống replay. |
| Token request | Client/redirect URI không khớp. | Từ chối exchange theo OAuth token endpoint error. |
| Token request | AS/token endpoint bị chọn nhầm. | Không gửi code/verifier tới AS khác; xử lý issuer binding. |
| API resource server | Access token sai chữ ký/issuer/audience/hết hạn. | Thường `401 invalid_token`. |
| API resource server | Token hợp lệ nhưng thiếu scope. | Thường `403 insufficient_scope`. |

Nếu AS nhận token request có verifier không khớp, việc **retry cùng code với verifier khác** không phải hướng xử lý bình thường. Hãy kiểm tra client có đang **lấy nhầm verifier của tab/session khác**, encode sai Base64URL, chuyển đổi chuỗi sai hoặc bị downgrade. Khi code đã tiêu thụ/hết hạn, client phải bắt đầu authorization transaction mới.

Không ghi code hoặc verifier vào log để debug. Có thể ghi transaction ID, method đã đàm phán, mã `PKCE_VERIFIER_MISMATCH`, `MISSING_CHALLENGE` hoặc `UNSUPPORTED_METHOD` và thời điểm.

## 20. Các lỗi triển khai gây nguy hiểm hoặc khó phát hiện

| Sai lầm | Hậu quả | Phòng tránh |
|---|---|---|
| Sinh verifier bằng `Math.random()` hoặc timestamp. | Verifier có thể đoán được. | CSPRNG 32 bytes, Base64URL no padding. |
| Dùng verifier chung cho mọi lần login. | Một lần lộ có thể ảnh hưởng nhiều code transactions. | Verifier mới cho mỗi giao dịch. |
| Dùng `plain` vì không biết tính SHA-256. | Authorization request lộ verifier trực tiếp. | Dùng S256 qua thư viện mật mã chuẩn. |
| Bỏ `code_challenge_method`, tưởng server mặc định S256. | RFC mặc định plain nếu có challenge. | Gửi method=S256 rõ ràng; policy AS enforce. |
| S256 mismatch thì tự thử plain. | Downgrade và có thể mở đường đổi code trái phép. | Từ chối, không fallback. |
| Lưu challenge nhưng không lưu method gắn với code. | Server có thể chọn sai logic kiểm tra. | Lưu challenge + method cùng code/client/redirect. |
| Để token request ghi đè challenge ban đầu. | Attacker điều khiển kiểm tra PKCE sau khi nhận code. | Chỉ dùng thông tin đã cố định ở AS. |
| Dùng Base64 thường hoặc thêm padding. | Mismatch hoặc lỗi syntax theo profile. | Base64URL không `=`. |
| Dùng UTF-16 bytes khi hash. | S256 sai so với RFC. | ASCII bytes của verifier hợp lệ. |
| Khai báo `response_type=code` nhưng token request thiếu verifier. | Code không được bảo vệ nếu AS vẫn cho qua. | AS reject khi PKCE required. |
| Lưu một verifier global giữa các tab. | Tab B ghi đè transaction của tab A. | Ánh xạ verifier theo transaction/state. |
| Chỉ kiểm PKCE, bỏ `state`/issuer validation. | Login injection hoặc AS mix-up vẫn có thể xảy ra. | Các lớp kiểm tra bổ sung độc lập. |
| Ghi raw code, verifier hoặc Authorization header vào logs. | Bên đọc log có thể đánh cắp credential. | Redaction, least-privilege log access. |
| Coi PKCE là sender constraint của access token. | Bearer token bị lộ vẫn bị phát lại. | DPoP/mTLS và token security phù hợp. |
| Tự chấp nhận mọi JWT sau code flow nếu chữ ký đúng. | Token sai audience/type/expiry hoặc vượt quyền. | RS validation và authorization đầy đủ. |

## 21. Ma trận kiểm thử code challenge methods

Giả sử AS hỗ trợ **S256-only** cho client `orders-web`; client dùng issuer `https://id.example.test`, redirect URI đã đăng ký và access token cho `orders-api`.

| ID | Tình huống | Kỳ vọng |
|---|---|---|
| P01 | Verifier vector RFC 7636 được tính S256. | Challenge đúng `E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM`. |
| P02 | Sinh verifier từ 32 bytes CSPRNG. | Verifier 43 ký tự, thuộc charset RFC. |
| P03 | Verifier 42 ký tự. | Từ chối, quá ngắn. |
| P04 | Verifier 129 ký tự. | Từ chối, quá dài. |
| P05 | Verifier có dấu `=`, `+`, `/`, whitespace hoặc Unicode. | Từ chối syntax sai. |
| P06 | Verifier toàn một ký tự lặp dù đủ dài. | Client generation test/entropy review phát hiện mẫu sai; regex alone không đủ. |
| P07 | Authorization request có challenge và `method=S256`. | AS lưu challenge/method gắn với transaction. |
| P08 | Có challenge nhưng thiếu method trong S256-only policy. | Từ chối; không mặc định chấp nhận plain. |
| P09 | `method=plain` trong S256-only policy. | Từ chối trước khi cấp code. |
| P10 | `method=s256` hoặc method lạ. | Từ chối do tên method không khớp. |
| P11 | Có method nhưng không có challenge. | Từ chối request lỗi. |
| P12 | Authorization Code flow cần PKCE nhưng không có challenge. | Từ chối, không cấp code unbound. |
| P13 | Token request có verifier đúng. | PKCE pass nếu code/client/redirect còn hợp lệ. |
| P14 | Verifier sai một ký tự. | `invalid_grant`, không phát token. |
| P15 | Verifier đúng nhưng code của client khác. | Từ chối do client binding. |
| P16 | Verifier đúng nhưng redirect URI không khớp transaction. | Từ chối exchange. |
| P17 | Code đã dùng được gửi lại với verifier cũ. | Từ chối replay, không phát token mới. |
| P18 | Hai request đồng thời cùng đổi code. | Chỉ một code consume thành công. |
| P19 | Code hết hạn dù verifier đúng. | Từ chối. |
| P20 | Token request cố chỉ định `method=plain` để bỏ qua stored S256. | Không downgrade, từ chối hoặc bỏ tham số sai hợp đồng. |
| P21 | S256 mismatch và client/server tự thử plain. | Security test thất bại; phải từ chối. |
| P22 | Client dùng verifier của một tab cho code tab khác. | Từ chối, chứng minh transaction isolation. |
| P23 | Callback có `state` không khớp nhưng verifier hợp lệ. | Client từ chối trước token exchange. |
| P24 | Callback issuer khác AS ban đầu. | Từ chối mix-up. |
| P25 | OIDC ID token có nonce khác request. | OIDC client từ chối. |
| P26 | AS metadata chỉ hỗ trợ `S256`. | Client chọn S256, không downgrade. |
| P27 | AS metadata công bố cả S256/plain nhưng client policy S256-only. | Client vẫn dùng S256. |
| P28 | JWT access token đúng code flow nhưng `aud=payments-api` tại Orders API. | Resource server từ chối. |
| P29 | JWT signature sai, dù code challenge đã đúng. | RS từ chối; PKCE không thay signature check. |
| P30 | Opaque access token introspection `active=false`. | RS từ chối. |
| P31 | Access token hợp lệ nhưng thiếu `orders.approve`. | API approve từ chối `403`. |
| P32 | Token đúng audience/scope nhưng order thuộc tenant khác. | RS từ chối theo object-level policy. |
| P33 | Access Bearer token bị đánh cắp sau PKCE. | Có thể bị replay nếu còn hợp lệ; test lớp bảo vệ thêm. |
| P34 | Refresh token bị reuse sau rotation. | AS phát hiện/từ chối theo chính sách family. |
| P35 | Callback/token request bị ghi raw code hoặc verifier vào logs. | Redaction/security tests phát hiện lỗi. |
| P36 | Web backend/Spring không thực sự gửi PKCE dù được kỳ vọng. | Integration test fail, phải cấu hình resolver/enforcement. |

### Phân biệt những tầng kiểm thử

- **Unit tests:** test vector RFC, syntax, encoding ASCII/Base64URL, tạo verifier CSPRNG, challenge function.
- **Authorization-server integration tests:** gửi requests thật, bảo đảm lưu method với code, verifier comparison, code one-time/client/redirect binding, chống downgrade.
- **Browser/mobile end-to-end tests:** multi-tab verifier isolation, state/callback/issuer, external user-agent và xử lý thất bại.
- **Resource-server tests:** access JWT signature/issuer/audience/scope/expiry, opaque introspection, tenant/object authorization và revocation.
- **Logging/security tests:** không chứa raw code/verifier/token trong URL logs, traces, analytics hoặc error reports.

Mock principal hoặc Spring Security Test `jwt()` không chứng minh authorization server thực thi PKCE đúng. Muốn kiểm thử end-to-end, cần AS/JWKS môi trường test, verifier/challenge mới và code exchange thật theo protocol.

## 22. Tình huống học tập

### Tình huống A — thiếu method, client tưởng S256

Client tạo S256 challenge rồi gửi `code_challenge` nhưng không gửi `code_challenge_method`. AS triển khai mặc định RFC 7636 là `plain`.

**Câu hỏi:** Khi client gửi verifier gốc ở token endpoint, vì sao exchange thất bại?

> Vì AS kiểm tra theo `plain`: so sánh verifier trực tiếp với challenge. Nhưng challenge client gửi là SHA-256 digest mã hóa Base64URL, nên hai chuỗi không khớp. Sửa bằng cách gửi **`code_challenge_method=S256`**, không bằng cách tắt PKCE.

### Tình huống B — code lộ nhưng verifier không lộ

Kẻ tấn công lấy code từ URL redirect. Authorization transaction sử dụng `S256`, client giữ verifier đúng cách.

**Câu hỏi:** Attacker có đổi code thành access token được không?

> Không, nếu AS thực thi PKCE đúng, code còn ràng buộc với client/redirect và attacker không có verifier. Vẫn cần xử lý URL logs, TTL và code one-time; nếu attacker chiếm client runtime thì có thể có đường lộ verifier khác.

### Tình huống C — plain khi authorization URL bị ghi log

Một ứng dụng dùng `code_challenge_method=plain`. Proxy ghi authorization request đầy đủ, kẻ tấn công có quyền đọc logs.

**Câu hỏi:** PKCE còn bảo vệ nếu code cũng bị chặn không?

> Rất yếu trong mô hình này: challenge chính là verifier, nên kẻ đọc URL có thể biết verifier. Dùng S256, redaction và các kiểm tra client/redirect; không chỉ dựa vào một lớp bảo vệ.

### Tình huống D — BFF có client secret thì không cần PKCE?

Một web backend dùng confidential client authentication bằng private-key JWT hoặc client secret. Nhóm phát triển muốn bỏ PKCE vì đã có client authentication.

**Câu hỏi:** Có phù hợp thực hành hiện đại không?

> Không nên bỏ PKCE chỉ vì có client authentication. Chúng bảo vệ những thuộc tính khác nhau; PKCE ràng buộc code với transaction và bổ sung bảo vệ interception/injection. Nên thực thi S256 theo chính sách của AS/client.

### Tình huống E — một verifier cho nhiều tab

Tab 1 bắt đầu login, sinh verifier V1; tab 2 bắt đầu login, ghi đè biến global bằng V2. Callback tab 1 tới trước và dùng V2 để đổi code.

**Câu hỏi:** Kết quả và cách sửa?

> AS phải từ chối vì S256(V2) không khớp challenge của code tab 1. Client cần lưu verifier **theo từng transaction**, ràng buộc với `state`/session; không dùng một biến toàn cục cho nhiều luồng đồng thời.

### Tình huống F — PKCE pass nhưng API sai audience

Authorization code được đổi thành access token qua PKCE thành công. Token có `aud=payments-api` nhưng được gửi đến `orders-api`.

**Câu hỏi:** Orders API có cho phép vì PKCE đã pass?

> Không. PKCE chứng minh code exchange đúng transaction, không cấp quyền cho resource server khác. Orders API phải từ chối audience sai và tiếp tục kiểm tra scope/tenant khi token đúng.

### Câu hỏi tự đánh giá

1. `code_verifier`, `code_challenge` và `code_challenge_method` được tạo, lưu và gửi vào những bước nào?
2. Công thức chính xác của S256 là gì? Vì sao không được thêm Base64 padding?
3. `plain` khác S256 ở điều kiện bảo mật nào quan trọng nhất?
4. Khi thiếu `code_challenge_method` nhưng có challenge, RFC 7636 mặc định method gì?
5. Vì sao AS S256-only phải từ chối `plain` và không fallback khi S256 mismatch?
6. Verifier hợp lệ có độ dài, tập ký tự và yêu cầu entropy như thế nào?
7. Vì sao không được sinh verifier bằng timestamp hoặc dùng cùng verifier giữa nhiều tab?
8. Vì sao server phải lưu challenge **và method** gắn với authorization code?
9. PKCE có thay `state`, `nonce`, issuer validation hoặc redirect URI binding không?
10. PKCE có tự chống việc refresh token hoặc Bearer access token bị đánh cắp không?
11. Một JWT access token sau PKCE còn phải được resource server kiểm tra những gì?
12. Tại sao `code_challenge_methods_supported` trong metadata không chứng minh client thực sự dùng S256?

## 23. Ghi nhớ

- **Code challenge methods trong RFC 7636 gồm `S256` và `plain`**. **S256 là lựa chọn an toàn mặc định** cho triển khai hiện đại.
- **S256 = BASE64URL(SHA256(ASCII(code_verifier)))**; chuỗi Base64URL không có padding. `plain` chỉ sao chép verifier thành challenge và có thể làm lộ verifier trên front channel.
- **Verifier cần 43–128 ký tự unreserved và được sinh bằng CSPRNG**, điển hình 32 random bytes → Base64URL 43 ký tự. Tạo mới cho từng authorization transaction.
- **Authorization endpoint nhận challenge + method**, còn **token endpoint nhận verifier**. AS dùng method/challenge **đã lưu với code**, không cho client chọn lại sau khi code phát hành.
- **Không fallback/downgrade**: thiếu method được RFC 7636 hiểu là plain, nhưng AS theo policy S256-only phải từ chối; verifier sai/code đã dùng phải bị từ chối.
- **PKCE không thay state, nonce, issuer, redirect và client authentication**. Code phải hết hạn nhanh, ràng buộc đúng client/grant và chỉ dùng một lần.
- **BFF, SPA và mobile** đều có thể sử dụng S256 theo cách lưu transaction phù hợp; public client không giữ được client secret cố định như backend.
- **PKCE chỉ bảo vệ code exchange**, không quyết định JWT/opaque, scope, audience hoặc thu hồi token. Access/refresh/ID tokens vẫn phải được bảo vệ và xác minh theo đúng mục đích.
- **Kiểm thử bằng RFC test vector, AS integration tests và API authorization tests**, không chỉ dựa vào giao diện login có thành công.

### Tài liệu chuẩn tham khảo

- [RFC 7636 — Proof Key for Code Exchange (PKCE)](https://www.rfc-editor.org/rfc/rfc7636): syntax của verifier, S256/plain, test vector, authorization/token requests và validation.
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): Authorization Code grant và yêu cầu một lần sử dụng code.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): PKCE, chống interception/injection, issuer mix-up và bảo vệ tokens.
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414): `code_challenge_methods_supported` và issuer discovery.
- [RFC 9207 — Authorization Server Issuer Identification](https://www.rfc-editor.org/rfc/rfc9207): issuer binding để chống mix-up.
- [RFC 8252 — OAuth 2.0 for Native Apps](https://www.rfc-editor.org/rfc/rfc8252): PKCE, external user-agent và redirect security trên mobile.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750) và [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): access token validation, audience và scope.
- [RFC 7662 — Token Introspection](https://www.rfc-editor.org/rfc/rfc7662) và [RFC 7009 — Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): xác minh trạng thái và thu hồi token.
- [RFC 9449 — OAuth 2.0 DPoP](https://www.rfc-editor.org/rfc/rfc9449) và [RFC 8705 — OAuth 2.0 mTLS](https://www.rfc-editor.org/rfc/rfc8705): sender-constrained tokens, khác PKCE.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): OIDC code flow, ID token, `nonce` và token validation.
- [Spring Security — OAuth 2.0 Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html) và [OAuth 2.0 Client Core](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/core.html): Spring Security OAuth2 Client và PKCE integration.
