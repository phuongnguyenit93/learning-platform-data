# HMAC tại service khi request đi qua gateway và proxy

## 1. Vì sao đặt bước xác minh HMAC ở service?

Trong module **SECURITY_AUTHENTICATION_HMAC_REQUEST_AUTHENTICATION**, client ký HTTP request bằng **HMAC với shared secret** và một **canonical request** đã được thỏa thuận. Thông điệp được ký có thể bao gồm phương thức HTTP, URI, một tập header và/hoặc digest của body. Server phải xác minh chữ ký, kiểm tra timestamp/nonce để chống replay, xử lý key rotation và quyết định phân quyền **sau khi** xác thực danh tính.

Chương **Gateway và proxy** xem xét một vấn đề rất thực tế: request đi qua một hoặc nhiều lớp trung gian trước khi đến ứng dụng Java. Bài **HMAC tại service** giải thích cách service tự kiểm tra chữ ký HMAC ở điểm cuối của đường truyền HTTP, trong khi gateway vẫn làm những việc như định tuyến, TLS termination, rate limiting, quan sát lưu lượng và cân bằng tải.

Ví dụ một đối tác gọi:

~~~http
POST /public/v1/payments?source=partner HTTP/1.1
Host: api.example.test
Content-Type: application/json
X-Key-Id: merchant-a-key-7
X-Timestamp: 2026-11-28T03:20:00Z
X-Nonce: 377eb9ab-a711-4ec2-b4a4-19b9dfd2f6a1
X-Signature: <base64-hmac-sha256>

{"amount":125000,"currency":"VND"}
~~~

Gateway chuyển request vào service, có thể với URI nội bộ là `/payments`. Nếu service dùng URI nội bộ để tạo canonical request trong khi client đã ký `/public/v1/payments`, việc kiểm tra chữ ký sẽ thất bại dù client có secret đúng. Nguy hiểm hơn, nếu service tin bừa một header như `X-Original-URI` do người gọi tự gửi, kẻ tấn công có thể làm lệch dữ liệu được xác minh với tài nguyên thực tế bị gọi.

**Mục tiêu học tập** là thiết kế hợp đồng ký và ranh giới tin cậy để service kiểm tra chính xác **request mà client đã ký**, ràng buộc nó với hành động thực tế mà service sẽ thực hiện, không tin dữ liệu từ proxy thiếu xác thực và không cho request không hợp lệ chạy nghiệp vụ.

## 2. Vị trí xác minh trong kiến trúc

~~~mermaid
flowchart LR
    C[Client / đối tác] -->|HTTPS + HMAC| G[Gateway]
    G -->|Kênh nội bộ bảo vệ| P[Reverse proxy / service mesh]
    P -->|Request đã định tuyến| S[Payment service]
    S --> V{HMAC + timestamp + nonce}
    V -- Không hợp lệ --> X[401 / 503; dừng xử lý]
    V -- Hợp lệ --> A{Có quyền?}
    A -- Không --> F[403]
    A -- Có --> B[Controller + nghiệp vụ]
~~~

**Xác minh HMAC tại service** nghĩa là chính service quyết định request có chứng thực hợp lệ hay không. Gateway có thể chặn kết nối nguy hiểm hoặc giới hạn request, nhưng service phải có đầy đủ dữ liệu đáng tin cậy để xác minh phần được ký. Cần phân biệt ba hướng thiết kế:

| Hướng | Nơi xác minh chữ ký | Đặc điểm |
|---|---|---|
| HMAC tại service | Service đích | Secret và quyết định xác thực ở service; gateway phải giữ hoặc chuyển giao an toàn dữ liệu được ký |
| HMAC tại gateway | Gateway | Gateway xác thực một lần, sau đó chuyển **assertion danh tính được bảo vệ** tới service; service phải tin cậy được assertion và vẫn kiểm tra phân quyền |
| Xác minh ở cả hai tầng | Gateway và service | Có thể tăng kiểm soát ở nhiều biên, nhưng phải thống nhất canonical contract và quản lý secret/trust; thêm độ trễ và độ phức tạp |

Không có lựa chọn phù hợp cho mọi hệ thống. Bài này chỉ đi sâu vào **hướng thứ nhất**. Đặt HMAC tại service thường hữu ích khi service quản lý riêng khóa của đối tác, cần chính nó kiểm tra chữ ký trước khi thực hiện nghiệp vụ hoặc gateway chỉ chịu trách nhiệm định tuyến mà không được phép truy cập secret.

Tuy nhiên, vị trí xác minh là một **quyết định kiến trúc**, không tự tạo bảo đảm end-to-end. Nếu gateway sửa byte body trước khi giao cho service, service có thể thiếu thông tin để kiểm tra chữ ký gốc. Nếu proxy gửi metadata không được xác thực, service có thể bị đánh lừa về URI client đã gọi.

## 3. Phân chia trách nhiệm giữa gateway và service

| Trách nhiệm | Gateway / proxy | Service |
|---|---|---|
| TLS ngoài Internet, giới hạn kết nối, chống lưu lượng bất thường | Thường xử lý tại biên | Chỉ nhận traffic từ đường đi được bảo vệ |
| Route public sang route nội bộ | Thực hiện và ghi nhận mapping | Biết route nội bộ nào ứng với tài nguyên client được phép ký |
| Chuyển tiếp method, path/query, headers, body | Không làm sai hợp đồng ký; bảo vệ metadata chuyển tiếp | Đọc đúng representation đã được ký |
| Shared secret / key rotation | Không cần giữ secret trong mô hình service verify | Lookup key theo key ID, hiệu lực, phạm vi client/tenant |
| HMAC signature | Có thể precheck hình thức; không có quyền tự chứng thực nếu không được giao | Tính HMAC kỳ vọng và so sánh |
| Timestamp, nonce và replay | Có thể hỗ trợ rate limit | Xác minh thời gian, claim nonce nguyên tử trước nghiệp vụ |
| Authentication | Không được tự gán client ID dựa trên header do khách gửi | Tạo principal từ key đã xác thực |
| Authorization | Chặn thô theo policy ở biên nếu cần | Kiểm tra authority, tenant và quyền với resource |
| Audit và response | Gắn request ID tin cậy, quan sát lỗi ở biên | Ghi nhận kết quả xác thực/phân quyền và gửi status phù hợp |

Một client gửi `X-Key-Id: merchant-a-key-7` mới chỉ **khai báo key muốn dùng**. Chỉ sau khi service kiểm tra HMAC bằng key tương ứng, identity mới có giá trị chứng thực. `X-Forwarded-For`, IP ở gateway hay header `X-Client-Id` không thể thay thế bước này.

## 4. Ký “request bên ngoài” hay “request bên trong”?

Đây là quyết định quan trọng nhất khi HMAC nằm ở service đích.

### 4.1. Hai URI có thể khác nhau

Ví dụ:

~~~text
Client thấy:  POST https://api.example.test/public/v1/payments?source=partner
Gateway:     rewrite /public/v1/payments  ->  /payments
Service thấy: POST http://payment-service:8080/payments?source=partner
~~~

Nếu hợp đồng ký bao gồm public raw path `/public/v1/payments` thì service không được tự thay bằng `/payments` rồi tính HMAC; hai bên sẽ dùng canonical string khác nhau.

Có ba mô hình khả thi:

1. **Giữ nguyên representation được ký.** Gateway chuyển path/query và body dưới dạng mà service có thể quan sát tương đương với client; service canonicalize trên chính representation đó.
2. **Chuyển metadata gốc có xác thực.** Gateway rewrite để route nhưng truyền public target trong metadata nội bộ được bảo vệ. Service chỉ sử dụng metadata sau khi nhận diện gateway đáng tin cậy và đối chiếu public target với route nội bộ đã cho phép.
3. **Ký logical resource độc lập với route vật lý.** Hợp đồng ký một định danh logic ổn định, chẳng hạn resource ID hay canonical endpoint ID; service và gateway đều phải ánh xạ định danh này tới duy nhất một thao tác. Không cho client tự chọn một logical route rồi tác động lên endpoint khác.

**Không tự lấy `X-Original-URI` hoặc `X-Forwarded-Prefix` làm sự thật.** Các header này có thể do client Internet gửi hoặc do nhiều hop nối/chồng giá trị. Nếu cần chuyển public target, phải làm rõ ai được quyền phát hành metadata, ai được quyền thay đổi nó và service xác minh metadata thế nào.

### 4.2. Mẫu chuyển giao metadata đáng tin cậy

Ví dụ môi trường cho phép gateway đưa tới service các header nội bộ:

~~~text
X-Internal-Original-Method: POST
X-Internal-Original-Target: /public/v1/payments?source=partner
X-Internal-Route-Id: payments.create.v1
~~~

**Các header trên là quy ước minh họa của một hệ thống**, không phải chuẩn chung. Chỉ được tin khi thỏa **đồng thời** các điều kiện:

- Ingress **xóa hoặc ghi đè** mọi header cùng tên đến từ client không tin cậy; không giữ giá trị cũ hoặc nối nhiều bản.
- Service chỉ cho phép kết nối từ gateway/proxy đã xác thực, ví dụ mTLS với workload identity và network policy; không có đường gọi trực tiếp từ Internet hoặc từ workload không được ủy quyền.
- Từng hop trung gian được tin cậy hoặc metadata được bảo vệ bằng cơ chế xác minh tính toàn vẹn/nguồn phát riêng. Một hop không đáng tin cậy có thể sửa header sau ingress.
- Service kiểm tra **mapping hợp lệ** từ public method/target/route ID sang endpoint nội bộ đang xử lý. Metadata nói `payments.create.v1` không được phép thực thi `payments.refund.v1`.
- Service vẫn kiểm tra **chữ ký HMAC gốc từ client** trên đúng canonical request được thỏa thuận. Việc gateway gửi metadata không làm nó trở thành bằng chứng danh tính của đối tác.

Nếu không thể bảo đảm chuỗi điều kiện trên, ưu tiên thiết kế không cần tin forwarded header, hoặc dùng một assertion được gateway ký riêng để service xác minh. **Chữ ký của gateway và HMAC của client là hai lớp với hai danh tính/trust khác nhau.**

### 4.3. Mapping phải ràng buộc với thao tác nghiệp vụ

Giả sử client ký public route `POST /public/v1/payments`. Gateway vô tình map sang `POST /internal/refunds`. Nếu service chỉ kiểm tra chữ ký public route mà không đối chiếu route mapping, một chữ ký hợp lệ có thể bị áp vào thao tác khác.

Service nên kiểm tra một invariant:

~~~text
signedMethod + signedPublicTarget
        phải ánh xạ tới
actualInternalMethod + actualRouteId
        theo cấu hình server đã kiểm soát.
~~~

Ví dụ một route ID cố định được gắn khi routing, sau đó service so sánh với endpoint handler và hợp đồng URI đã được khai báo. Không dựng identity/resource từ header không đáng tin rồi mặc nhiên coi là quyền của client.

## 5. Hợp đồng canonical request ổn định xuyên proxy

Để minh họa, giả sử HMAC-V1 ký các thành phần sau:

~~~text
HMAC-V1
<UPPERCASE_HTTP_METHOD>
<PUBLIC_RAW_PATH>
<PUBLIC_RAW_QUERY_OR_EMPTY>
<KEY_ID>
<UTC_TIMESTAMP>
<NONCE>
<LOWERCASE_HEX_SHA256_OF_RAW_BODY_BYTES>
~~~

Với request đầu bài, canonical string ví dụ:

~~~text
HMAC-V1
POST
/public/v1/payments
source=partner
merchant-a-key-7
2026-11-28T03:20:00Z
377eb9ab-a711-4ec2-b4a4-19b9dfd2f6a1
<sha256-hex-64-ky-tu-cua-byte-body>
~~~

Sau đó tính:

~~~text
expected = HMAC-SHA256(secret(keyId), UTF8(canonical))
received = strictBase64Decode(X-Signature)
valid = constantTimeCompare(expected, received)
~~~

Đây chỉ là **hợp đồng minh họa**. Hợp đồng thực tế phải chỉ rõ thuật toán, encoding, version, cách chuẩn hóa từng trường, bytes nào được ký và thứ tự dòng. Để chống nhập nhằng do xuống dòng hoặc ký tự điều khiển, cần giới hạn hợp lệ của header/URI và độ dài từng trường, hoặc dùng định dạng canonical có length-prefix rõ ràng.

### 5.1. Path, query và host

Đối với request qua proxy, các trường này dễ thay đổi:

| Thành phần | Rủi ro | Quy tắc nên thống nhất |
|---|---|---|
| Method | `X-HTTP-Method-Override` hoặc routing thay method | Method được ký phải ràng buộc với method nghiệp vụ thực sự |
| Path | Rewrite prefix, decode `%2F`, dot-segment, slash kép, trailing slash | Ký một biểu diễn URI xác định; route mapping phải nhất quán |
| Query | Thứ tự key, key lặp, `+` so với `%20`, percent-encoding | Chọn raw query hoặc canonical query có định nghĩa đầy đủ |
| Host/scheme | TLS termination đổi `https` thành `http`; internal host khác public host | Nếu ký host/scheme, dùng public authority đã bảo vệ hoặc định danh endpoint logic |
| Header | Case tên header, OWS, giá trị trùng/được gộp, header do proxy thêm | Chỉ ký tập header xác định, có quy tắc canonicalization và xử lý duplicate |
| HTTP version | HTTP/2 pseudo-headers khác HTTP/1.1 | Ký semantics đã thỏa thuận, không phụ thuộc cú pháp wire của từng phiên bản |

Một thay đổi **không làm khác nghĩa nghiệp vụ** vẫn có thể làm HMAC sai nếu byte canonical không giống nhau. Ví dụ `a=1&b=2` khác `b=2&a=1` khi hợp đồng ký nguyên raw query; vì thế cần test vector giữa client, gateway và service.

Nếu chọn canonical query có sort, phải quy định xử lý tham số trùng như `role=user&role=admin`; nếu không, service có thể kiểm tra một giá trị nhưng handler dùng giá trị khác, tạo tình huống **HTTP parameter pollution**.

### 5.2. Header và dữ liệu không nên dùng để chứng minh danh tính

Không đưa tất cả header HTTP vào chuỗi ký một cách mù quáng: `Connection`, `Transfer-Encoding` và các hop-by-hop headers có thể bị proxy bỏ; `Via`, `X-Request-Id` hoặc `X-Forwarded-*` có thể được thêm ở các hop. Chọn tập header có ý nghĩa nghiệp vụ và ổn định theo hợp đồng, ví dụ `Content-Type` nếu nó quyết định cách giải thích payload.

Nếu header có nhiều giá trị, hợp đồng phải quy định có cho phép không, cách nối và cách xử lý khoảng trắng. Với các header nhạy cảm cho xác thực như `X-Signature`, `X-Key-Id`, `X-Timestamp` và `X-Nonce`, nên **từ chối bản trùng/không đúng cú pháp**, thay vì để gateway lấy giá trị đầu và service lấy giá trị cuối.

Không đưa `X-Forwarded-For` vào identity của đối tác: IP có thể dùng làm tín hiệu hạn chế/rate limit sau khi đã xác định proxy tin cậy, nhưng bằng chứng sở hữu shared secret chỉ đến từ chữ ký HMAC được xác minh.

### 5.3. Body bytes, compression và buffering

Nếu hợp đồng ký SHA-256 của **raw body bytes**, cần bảo toàn chính các byte ấy từ điểm ký đến điểm xác minh:

- Gateway/WAF không tự parse JSON rồi serialize lại, đổi thứ tự field, khoảng trắng, newline hoặc charset trước khi service xác minh.
- Nếu có gzip, phải quy định chữ ký áp dụng lên **compressed bytes** hay **decompressed bytes**; không tự chọn theo trạng thái của service.
- HTTP chunked framing và các header truyền tải có thể thay đổi qua hop; cần ký **entity body bytes đã định nghĩa trong hợp đồng**, không ký framing thô phụ thuộc phiên bản kết nối.
- Service phải đọc payload với giới hạn dung lượng, bảo đảm handler còn đọc được body sau khi verify (Servlet wrapper replay body, WebFlux `DataBuffer`/request decorator phù hợp).
- Đối với upload lớn hoặc streaming, cần giao thức ký dạng streaming hoặc phương án digest có bảo đảm toàn vẹn được thiết kế riêng, thay vì buffer vô hạn hay bỏ kiểm tra chữ ký.

Ví dụ hai chuỗi JSON sau có thể tạo cùng đối tượng dữ liệu nhưng **có byte khác nhau**:

~~~json
{"amount":125000,"currency":"VND"}
~~~

~~~json
{ "currency": "VND", "amount": 125000 }
~~~

Nếu chữ ký bảo vệ raw body, hai payload có SHA-256 khác nhau. Parser/serializer ở proxy không được thay dữ liệu một cách âm thầm.

## 6. Luồng xác minh HMAC tại service

### 6.1. Từ nhận request đến cấp authentication

~~~mermaid
flowchart TD
    A[Nhận request từ gateway] --> B{Nguồn proxy và metadata có đáng tin?}
    B -- Không --> X[Chặn tại biên nội bộ]
    B -- Có --> C[Giới hạn kích thước + đọc input]
    C --> D{Tái dựng public target được ký và mapping hợp lệ?}
    D -- Không --> R[Từ chối]
    D -- Có --> E[Parse keyId timestamp nonce signature]
    E --> F[Tra key active theo client/tenant]
    F --> G{Timestamp trong cửa sổ?}
    G -- Không --> U[401]
    G -- Có --> H[HMAC canonical + so sánh constant-time]
    H -- Sai --> U
    H -- Đúng --> I{Claim nonce nguyên tử thành công?}
    I -- Đã có --> U
    I -- Kho nonce lỗi --> S[503 fail closed]
    I -- Mới --> J[Authenticated principal]
    J --> K{Đủ authority và resource ownership?}
    K -- Không --> L[403]
    K -- Có --> M[Controller và side effect]
~~~

Một quy trình hợp lý theo thứ tự:

1. Service nhận request qua đường mạng được bảo vệ; nếu có metadata external target, kiểm tra nguồn gateway, việc sanitize và route mapping đã cấu hình.
2. Kiểm tra method, header bắt buộc, encoding, version, giới hạn body và cú pháp URI. Không tin giá trị được gửi chỉ vì nó nằm trong header.
3. Lấy key ID và tra secret/phạm vi hiệu lực từ kho khóa phía server. Key ID chỉ là **lookup hint**, không phải authentication.
4. Parse timestamp và kiểm tra độ lệch thời gian theo UTC clock của server. Ví dụ sử dụng cửa sổ ±5 phút nếu hợp đồng cho phép; không mặc định thời lượng này là chuẩn HMAC.
5. Canonicalize theo version, dùng byte body đã thỏa thuận, tính HMAC kỳ vọng. Decode chữ ký nghiêm ngặt và so sánh byte bằng phép so sánh có thời gian xử lý ít phụ thuộc dữ liệu, chẳng hạn `MessageDigest.isEqual`.
6. Chỉ sau khi chữ ký đúng, **claim nonce nguyên tử** theo phạm vi client/key và TTL. Nonce trùng là replay; Redis/DB không khả dụng thì không cho request đi qua.
7. Tạo `Authentication` với principal, tenant và authority lấy từ dữ liệu có thể tin cậy bên server. Không lấy roles tự khai báo trong request để tự cấp quyền.
8. Authorization kiểm tra quyền endpoint, tenant và resource trước khi thực hiện nghiệp vụ. Service được phép phân biệt **401 chưa xác thực** và **403 xác thực rồi nhưng thiếu quyền**.

Nếu ký timestamp/nonce nhưng **không kiểm tra** chúng, chữ ký có thể được phát lại trong thời gian dài. Nếu kiểm tra rồi mới ghi nonce bằng hai thao tác tách rời, hai request đồng thời có thể đều vượt qua.

### 6.2. Kiểm tra atomic nonce trong môi trường nhiều replica

Tại service có nhiều instance phía sau load balancer:

~~~text
Gateway  -->  payment-service-1  --\
                                  +--> Shared atomic nonce store
Gateway  -->  payment-service-2  --/
~~~

**Không dùng một `HashSet`/cache chỉ trong RAM của từng instance** để chống replay giữa các replica. Một nonce đi qua instance A sau đó được gửi lại đến B vẫn có thể vượt qua.

Ví dụ Redis thực hiện:

~~~text
SET hmac:nonce:<client-id>:<key-id>:<hash(nonce)> 1 NX PX <ttl-ms>
~~~

Ý nghĩa: chỉ lưu key nếu chưa tồn tại, kèm thời hạn sống **trong một thao tác atomic**. Nếu kết quả cho biết key đã có, trả lỗi authentication. Key nonce nên được tạo từ scope server đã xác thực và một bản băm nonce đã kiểm soát định dạng/độ dài, không ghép trực tiếp dữ liệu tùy ý.

TTL phải bao phủ toàn bộ **cửa sổ chấp nhận replay còn lại**, tính từ thời điểm claim. Ví dụ chấp nhận timestamp trong khoảng `now ± W`: một request có timestamp lệch tới tương lai `W` vẫn có thể hợp lệ tới `now + 2W`. Nếu dùng TTL cứng `W` tính từ lúc claim, có trường hợp key nonce hết hạn trước khi timestamp hết hiệu lực. Có thể đặt expiry tới `signedTimestamp + W + safetyMargin` (nếu được đánh giá đúng theo hợp đồng), hoặc dùng TTL đủ lớn cho mọi request chấp nhận.

Redis không sẵn sàng là lỗi **không thể bảo đảm chống replay**, thường trả 503. Đừng tự động cho qua để “giữ uptime”. Đối với request ghi như tạo thanh toán, **nonce HMAC khác idempotency key**: nonce ngăn tái dùng thông điệp đã ký; idempotency key bảo vệ ngữ nghĩa retry và tránh tạo giao dịch trùng lặp.

### 6.3. Key rotation trong backend

Key ID cần liên kết với client/tenant, secret, thuật toán, trạng thái, thời gian hiệu lực và quyền được gán. Để rotate an toàn:

- Client chuyển sang key ID mới; service tiếp tục nhận key cũ **chỉ trong thời gian overlap đã phê duyệt**.
- Từng instance và cache key phải cập nhật chính sách hiệu lực/revoke nhất quán; tránh instance chấp nhận key đã bị thu hồi vì cache quá cũ.
- Không thử tất cả secret rồi chọn key nào khớp; điều đó làm yếu tính minh bạch và phạm vi key, đồng thời tăng chi phí xác minh.
- Không để gateway tự quyết định tenant/authority dựa vào key ID trước khi service kiểm tra chữ ký; service phải đối chiếu với kho khóa đáng tin cậy.
- Khi nghi ngờ key bị lộ, revoke và dừng nhận ngay theo chính sách; xoay key không loại bỏ replay nếu nonce/timestamp không được kiểm tra.

## 7. Ví dụ Java: tính và kiểm tra chữ ký theo public request

Ví dụ Java 17+ sau tập trung vào **hàm tạo chữ ký kỳ vọng** và so sánh trên các giá trị đã được trích xuất, xác minh nguồn và chuẩn hóa bởi adapter HTTP. Đây là một thành phần dùng trong service; nó **không** tự giải quyết xác thực gateway, lấy raw body, authorization, lưu nonce hay quản lý secret.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.util.Base64;
import java.util.HexFormat;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class HmacV1 {
    private HmacV1() {}

    public static String canonical(
            String method,
            String signedPublicRawPath,
            String signedPublicRawQuery,
            String keyId,
            String timestamp,
            String nonce,
            byte[] bodyBytes) {

        // Gọi sau khi adapter đã xác thực nguồn public target và
        // từ chối ký tự điều khiển/giá trị header lặp/giá trị sai định dạng.
        // signedPublicRawQuery = "" nếu không có query.
        String bodyDigest = sha256Hex(bodyBytes);
        return String.join("\n",
                "HMAC-V1",
                method,
                signedPublicRawPath,
                signedPublicRawQuery,
                keyId,
                timestamp,
                nonce,
                bodyDigest);
    }

    public static boolean validSignature(
            byte[] secret, String canonical, String signatureBase64) {
        try {
            // Base64.getDecoder() từ chối những ký tự không hợp lệ.
            // Adapter cần giới hạn độ dài header trước khi decode.
            byte[] provided = Base64.getDecoder().decode(signatureBase64);
            if (provided.length != 32) {
                return false; // HMAC-SHA256 luôn cho 32 byte.
            }

            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(secret, "HmacSHA256"));
            byte[] expected = mac.doFinal(
                    canonical.getBytes(StandardCharsets.UTF_8));
            return MessageDigest.isEqual(expected, provided);
        } catch (IllegalArgumentException badBase64) {
            return false;
        } catch (GeneralSecurityException cryptoFailure) {
            // Lỗi thuật toán/crypto provider cần xử lý như lỗi hệ thống.
            throw new IllegalStateException("Cannot evaluate HMAC", cryptoFailure);
        }
    }

    private static String sha256Hex(byte[] bytes) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            return HexFormat.of().formatHex(digest.digest(bytes));
        } catch (GeneralSecurityException cryptoFailure) {
            throw new IllegalStateException("Cannot compute SHA-256", cryptoFailure);
        }
    }
}
~~~

Trong Java, `Mac` là đối tượng mutable; ví dụ tạo instance riêng mỗi lần tính, không chia sẻ một `Mac` giữa nhiều request/thread. `MessageDigest.isEqual` hỗ trợ so sánh hai mảng byte an toàn hơn so với `String.equals` trên chữ ký do client gửi. Chỉ decode/đánh giá signature **sau khi giới hạn header**, tránh lãng phí CPU/bộ nhớ trước kiểm tra đầu vào.

### 7.1. Adapter ở service: lấy đúng dữ liệu và dừng đúng chỗ

Pseudocode phía dưới mô tả phần điều phối trong một Servlet filter hoặc reactive security filter. Các thao tác I/O phải theo mô hình tương ứng của framework; đặc biệt **không dùng `block()` trên event-loop WebFlux**.

~~~text
authenticate(exchange):
    assertRequestArrivedThroughTrustedGatewayChannel()
    route = resolveActualInternalRoute(exchange)
    external = resolveAuthenticatedPublicTarget(exchange)
    assertAllowedMapping(external.method, external.target, route)

    headers = parseSingleRequiredHmacHeaders(exchange)
    assertAllowedAlgorithmAndVersion(headers)
    bodyBytes = readBodyWithLimitAndReplayForDownstream(exchange)

    key = keyStore.findActiveById(headers.keyId)
    if key missing/revoked: throw InvalidCredentials
    if timestamp outside allowed UTC window: throw InvalidCredentials

    canonical = HmacV1.canonical(
        external.method, external.rawPath, external.rawQuery,
        headers.keyId, headers.timestamp, headers.nonce, bodyBytes)

    if !HmacV1.validSignature(key.secret, canonical, headers.signature):
        throw InvalidCredentials

    if !nonceStore.atomicClaim(
        key.clientId, key.keyId, headers.nonce, calculatedExpiry):
        throw InvalidCredentials

    principal = authenticatedPrincipal(
        key.clientId, key.tenant, key.serverGrantedAuthorities)
    continueSecurityChainWith(principal)
    // Authorization quyết định được gọi handler hay không.
~~~

**Không đặt `nonceStore.atomicClaim` trước kiểm tra chữ ký.** Kẻ tấn công có thể dùng request giả để chiếm nonce của request hợp lệ hoặc làm đầy kho nonce. Exception do kho key/nonce lỗi cần được phân loại riêng thành lỗi hạ tầng và xử lý fail closed.

Với Servlet, nếu filter đã tiêu thụ `ServletInputStream` để hash, phải có request wrapper hỗ trợ phát lại body cho controller; `ContentCachingRequestWrapper` chỉ cache byte đã đọc và **không tự bảo đảm** một controller đọc lại stream vừa bị filter tiêu thụ. Với WebFlux, thao tác với `Flux<DataBuffer>` phải giới hạn kích thước, release buffer theo hợp đồng và dùng `ServerHttpRequestDecorator` phù hợp nếu đã thu body.

### 7.2. Hợp đồng gateway ↔ service là một cấu hình riêng

Ví dụ tài liệu hợp đồng triển khai (pseudoconfiguration, **không phải file cấu hình Nginx/Envoy chạy trực tiếp**):

~~~yaml
externalRoute: "POST /public/v1/payments"
internalRouteId: "payments.create.v1"
internalMethod: "POST"
internalPath: "/payments"
clientSigns:
  scheme: "HMAC-V1"
  uri: "public-raw-path-and-query"
  body: "SHA-256-of-original-body-bytes"
gatewayRules:
  rejectOrStripClientHeaders:
    - "X-Internal-Original-Method"
    - "X-Internal-Original-Target"
    - "X-Internal-Route-Id"
  forwardTrustedMetadataOnlyOver: "authenticated-internal-channel"
serviceRules:
  validateGatewayIdentity: true
  validatePublicToInternalRouteMapping: true
  verifyClientSignature: true
  requireAtomicNonceClaim: true
~~~

Mẫu này làm rõ bên nào tạo/có quyền tin metadata; không thay thế một cấu hình cụ thể của proxy hoặc chính sách triển khai mạng.

## 8. Phản hồi lỗi và phân quyền

| Điều kiện | Cách xử lý tại service | Status thường gặp |
|---|---|---|
| Thiếu HMAC trên route bắt buộc | Dừng trước nghiệp vụ | **401 Unauthorized** |
| Key ID không tồn tại, signature sai, timestamp hết hạn, nonce trùng | Dừng, không lộ nguyên nhân chi tiết cho client | **401 Unauthorized** |
| HMAC hợp lệ nhưng client/tenant không có quyền resource hoặc action | Authorization từ chối | **403 Forbidden** |
| Không thể lấy key/claim nonce vì hạ tầng lỗi | Fail closed, đánh dấu lỗi hệ thống | **503 Service Unavailable** (ví dụ) |
| Body vượt hạn mức | Từ chối trước khi buffer toàn bộ | **413 Content Too Large** |
| Header malformed theo hợp đồng | 400 hoặc 401 tùy policy được tài liệu hóa | **400 Bad Request** hoặc **401** |
| Rate limit tại gateway | Gateway quyết định | **429 Too Many Requests** |
| Gọi service trực tiếp, giả metadata gateway | Chặn ở network/proxy trust boundary; nếu đã tới service thì không xác thực | Tùy cấu hình biên, không cho tới nghiệp vụ |

Theo HTTP, phản hồi **401** cần có `WWW-Authenticate` với challenge phù hợp. Nếu hệ thống tự định nghĩa scheme HMAC, có thể thỏa thuận `WWW-Authenticate: HMAC realm="signed-api"`; đây là **convention riêng**, không có nghĩa mọi thư viện HTTP hỗ trợ một giao thức HMAC tiêu chuẩn giống nhau.

Body lỗi nên nhất quán, ví dụ:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: HMAC realm="signed-api"
Content-Type: application/problem+json
Cache-Control: no-store

{"type":"about:blank","title":"Unauthorized","status":401}
~~~

Không trả shared secret, canonical string nội bộ, chữ ký kỳ vọng, key ID có tồn tại hay không hoặc nonce đã được dùng lúc nào. Hệ thống vẫn có thể ghi mã nguyên nhân an toàn vào log nội bộ để vận hành phân biệt lỗi tích hợp, replay và lỗi gateway.

## 9. Kiểm thử xuyên gateway: đừng chỉ test service trực tiếp

Một test unit chạy thẳng vào service có thể cho kết quả xanh nhưng request production vẫn sai chữ ký khi gateway rewrite. Cần kiểm thử **cùng một vector HMAC** qua các tuyến thực tế:

| Ca kiểm thử | Kỳ vọng |
|---|---|
| Client ký public URI, gateway rewrite đúng mapping | Service dùng public target đã xác thực; chữ ký hợp lệ |
| Gateway đổi prefix/path không được quy định | Service từ chối hoặc không xác minh được; không tự fallback bỏ ký |
| Client tự gửi `X-Internal-Original-Target` giả | Ingress xóa/ghi đè; service không tin giá trị giả |
| Gọi trực tiếp internal service và tự khai trusted metadata | Bị network/mTLS policy chặn; không tới handler |
| Raw query đảo thứ tự, key trùng hoặc encoding thay đổi | Kết quả theo đúng canonical contract; không parse tùy hứng |
| Proxy chuyển HTTP/2 ↔ HTTP/1.1, thay Host nội bộ | Vẫn đúng nếu contract ký public semantics được bảo toàn |
| Một proxy thay đổi body JSON nhưng không đổi signature | Chữ ký sai; không thực hiện nghiệp vụ |
| Proxy decompress gzip trước service | Đúng theo hợp đồng nếu được thiết kế; nếu byte không khớp thì từ chối |
| Signature có Base64 sai hoặc trùng header ký | Bị từ chối, không dò nhiều giá trị để tìm cái hợp lệ |
| Thiếu header HMAC trên signed route | 401, service không chạy nghiệp vụ |
| Replay cùng nonce tới **hai replica đồng thời** | Tối đa một request claim nonce thành công |
| Timestamp nằm ở biên ±W, đồng hồ gateway/service lệch | Kết quả theo chính sách skew thống nhất, có test clock cố định |
| Key cũ còn trong overlap, key bị revoke | Chỉ key được cho phép mới xác thực được |
| Nonce store không hoạt động | 503, request không được bỏ qua replay check |
| Chữ ký đúng nhưng thiếu quyền/khác tenant | 403, không có side effect |
| Client retry POST vì kết nối bị ngắt | Chữ ký mới/nonce mới và idempotency key xử lý ngữ nghĩa retry |
| Request body quá lớn | 413 trước khi chiếm quá nhiều memory |

Ví dụ test cấu trúc bằng lời:

1. Dùng cùng secret thử nghiệm tạo HMAC cho `POST /public/v1/payments?source=partner`, hash trên các byte JSON đã định.
2. Gửi **qua gateway thật hoặc test proxy tương đương**, không gọi trực tiếp `/payments`.
3. Xác minh service nhận đúng public target qua kênh tin cậy, ánh xạ sang route `payments.create.v1` và xác thực thành công.
4. Đổi một byte body, method hoặc query mà giữ nguyên signature; phải bị từ chối và mock payment handler không được gọi.
5. Gửi đồng thời cùng một signed request đến hai replica; hệ thống nonce store phải chỉ cho tối đa một lần đi qua lớp authentication.

Kiểm thử cần xem **cả status lẫn side effect** (bản ghi thanh toán, lệnh phát event hoặc lời gọi service phụ thuộc). Chỉ kiểm tra 401 mà không kiểm tra nghiệp vụ có chạy hay không có thể bỏ sót lỗi filter vẫn tiếp tục chain sau khi ghi lỗi.

## 10. Vận hành, hiệu năng và lỗi thiết kế thường gặp

**Đặt giới hạn trước khi hash:** gateway có thể giới hạn request size và rate, nhưng service vẫn phải có hạn mức riêng, vì lớp biên có thể bị cấu hình sai hoặc traffic nội bộ đi đường khác. Với body ký toàn phần, chi phí CPU/memory tăng theo kích thước payload.

**Không đưa secret tới nơi không cần:** nếu HMAC xác minh tại service, kho secret có thể chỉ được service truy cập. Gateway không cần secret để route hay xác minh mTLS kết nối nội bộ. Phân quyền secret theo service/tenant, có audit, rotation và revoke.

**Quan sát nhưng tránh lộ credential:** log request/correlation ID, route ID, key ID đã làm mờ, nhóm lỗi xác thực, thời gian xử lý và trạng thái hạ tầng nonce. Không log raw shared secret, signature đầy đủ, canonical string có dữ liệu nhạy cảm hoặc body thanh toán.

**Giữ đồng hồ đồng bộ:** timestamp và replay window phụ thuộc vào clock của service; đồng bộ NTP/clock health, theo dõi lệch thời gian và chủ động cảnh báo. Không lấy thời gian từ header của gateway do bên ngoài giả mạo để thay clock xác minh.

**Không lẫn 401 với 403:** HMAC sai là chưa xác thực; quyền `payments:write` thiếu là đã xác thực nhưng không được phép. Phải cấu hình Spring Security filter chain để hai trường hợp không bị nuốt chung thành lỗi 500 hoặc cùng một response không rõ ngữ nghĩa.

**Không cho service trust mọi gateway-looking header:** private IP một mình không đủ xác định danh tính máy gửi. Ưu tiên workload identity/mTLS và network policy; sanitizer phải bao phủ cả request có header trùng/case khác, và mọi hop được quyền ghi metadata.

**Không bỏ qua kiểm tra khi gateway lỗi:** nếu original signed target không thể xác định an toàn, dừng xác thực hoặc trả lỗi hạ tầng phù hợp. Đừng fallback sang internal URI chỉ để request có cơ hội chạy.

**Không coi HMAC là phân quyền hay idempotency:** signature chứng minh người gọi có secret tương ứng với key đã chấp nhận, nhưng service vẫn phải kiểm tra quyền trên resource và điều kiện trạng thái nghiệp vụ. Nonce ngăn replay trong cửa sổ xác thực; idempotency kiểm soát hiệu ứng khi client retry một thao tác ghi.

## 11. Checklist áp dụng

- [ ] Chọn rõ nơi xác minh: chính service đích kiểm tra HMAC bằng key lấy từ server.
- [ ] Canonical contract ghi rõ method, public path/query hoặc logical route, tập signed headers, body bytes, version, encoding và thuật toán.
- [ ] Gateway rewrite không làm mất dữ liệu được ký; mọi forwarded metadata được sanitize, bảo vệ qua các hop và kiểm tra nguồn.
- [ ] Service ràng buộc public target đã ký với internal route/handler thực sự, không cho chữ ký của thao tác này được dùng cho thao tác khác.
- [ ] Body được giữ đúng byte theo hợp đồng; có giới hạn kích thước và cơ chế cho controller đọc lại.
- [ ] Header HMAC được kiểm tra cú pháp, uniqueness và độ dài; key ID chỉ làm lookup hint.
- [ ] Timestamp dùng clock đáng tin cậy và giới hạn skew; chữ ký so sánh theo byte bằng hàm phù hợp.
- [ ] Nonce dùng shared atomic store giữa các replica; TTL bao phủ trọn replay window; store lỗi thì fail closed.
- [ ] Key ID/rotation/revoke và tenant/authority được quản lý phía server.
- [ ] Mọi nhánh từ chối dừng nghiệp vụ; 401, 403, 413, 503 được sử dụng đúng ngữ nghĩa.
- [ ] Test cùng một signed request xuyên proxy/gateway, bao gồm rewrite, body transform, query edge cases, concurrent replay và route mapping.
- [ ] Có audit/metric và cảnh báo cho lỗi chữ ký, replay, clock skew, kho key/nonce; không ghi credential nhạy cảm vào log.

**Điểm cốt lõi:** đặt xác minh HMAC ở service chỉ an toàn khi service nhìn thấy **đúng nội dung có thể xác minh mà client đã ký** và biết chắc nội dung đó tương ứng với hành động mà handler sẽ thực thi. Gateway được phép định tuyến và bảo vệ mạng, nhưng mọi phép chuyển đổi path/header/body phải nằm trong hợp đồng canonical và ranh giới tin cậy. Sau khi chữ ký, timestamp và nonce được chấp nhận, service vẫn phải kiểm tra phân quyền trước bất kỳ side effect nào.
