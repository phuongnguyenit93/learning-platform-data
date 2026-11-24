# Hash source

> **Chương:** CSP nâng cao  
> **Học phần:** Application Security — Browser Security (`SECURITY_APPLICATION_SECURITY_BROWSER_SECURITY`)

Trong Content Security Policy (CSP), **hash source** cho phép browser thực thi một đoạn script hoặc áp dụng một đoạn style inline khi nội dung của nó khớp với giá trị hash được khai báo trong policy. Thay vì cho phép mọi inline code hoặc phải tạo nonce riêng cho từng response, ứng dụng có thể cho phép chính xác những block tĩnh đã được kiểm tra và đưa vào build.

Hash source hữu ích khi nội dung inline ổn định, được kiểm soát trong source code và cần hoạt động với CSP chặt. Nhưng hash không phải bí mật, không tự xác thực người dùng và không thay thế output encoding, kiểm soát DOM sink hay review code. Nếu kẻ tấn công có thể chèn lại đúng đoạn code đã được allowlist, browser vẫn có thể chấp nhận đoạn đó. Cần hiểu rõ hash bảo vệ điều gì, cách tính đúng byte nội dung và các trường hợp cần `'unsafe-hashes'`.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích hash source trong CSP và các thuật toán hash được hỗ trợ.
2. Tính hash cho inline `<script>` và `<style>` block từ nội dung chính xác.
3. Phân biệt hash source với nonce source và Subresource Integrity (SRI).
4. Hiểu vì sao whitespace, xuống dòng hoặc bước build có thể làm hash không khớp.
5. Nhận diện trường hợp cần `'unsafe-hashes'` cho event handler và style attribute.
6. Tạo policy hash theo nguyên tắc least privilege.
7. Tích hợp sinh hash vào build/release pipeline và kiểm thử regression.
8. Chẩn đoán CSP violation khi hash không khớp hoặc policy bị ghi đè.

## 2. Hash source là gì?

Hash source là một source expression trong CSP có dạng:

```text
'sha256-BASE64_DIGEST'
'sha384-BASE64_DIGEST'
'sha512-BASE64_DIGEST'
```

Browser tính digest của nội dung inline tương ứng rồi so sánh với hash trong policy. Nếu thuật toán và digest khớp, block đó có thể được cho phép theo directive áp dụng.

Ví dụ policy:

```http
Content-Security-Policy: default-src 'self'; script-src 'self' 'sha256-HASH_CUA_SCRIPT'; style-src 'self' 'sha256-HASH_CUA_STYLE'; object-src 'none'; base-uri 'none'
```

Trong ví dụ:

- `script-src` chứa hash cho inline script block.
- `style-src` chứa hash cho inline style block.
- `'self'` cho phép tài nguyên script/style cùng origin theo directive tương ứng.
- `object-src 'none'` và `base-uri 'none'` là các lớp CSP khác, không phải một phần của thuật toán hash.

`HASH_CUA_SCRIPT` và `HASH_CUA_STYLE` chỉ là placeholder, không phải digest hợp lệ. Khi triển khai, phải thay bằng Base64 digest được tính từ nội dung thực tế.

Các thuật toán CSP hash source tiêu chuẩn gồm SHA-256, SHA-384 và SHA-512. Không dùng SHA-1. Phần digest dùng **Base64 chuẩn**, không phải hexadecimal và không phải Base64URL.

## 3. Hash cho inline `<script>` block

Giả sử trang có script inline tĩnh:

```html
<script>
  console.log("Ứng dụng đã khởi tạo");
</script>
```

Hash được tính trên **nội dung script bên trong element**, không bao gồm thẻ mở `<script>` và thẻ đóng `</script>`. Nội dung cần được lấy từ HTML cuối cùng mà server gửi tới browser, sau khi template, minifier hoặc build tool đã xử lý.

Policy sẽ chứa source expression dạng:

```http
Content-Security-Policy: script-src 'self' 'sha256-BASE64_DIGEST'
```

Browser chỉ cho phép inline script block có nội dung khớp digest. Nếu script thay đổi, hash cũ không còn khớp và browser chặn block đó.

### 3.1 Hash không phải hash của cả file HTML

Không tính hash trên toàn bộ HTML document hoặc cả hai thẻ `<script>`. Cần lấy đúng phần nội dung script block. Nếu một trang có ba inline script block khác nhau, mỗi block cần hash tương ứng, trừ khi nội dung của chúng giống hệt nhau và cùng digest.

Không nhầm hash source với hash của URL hoặc tên file JavaScript. Với script ngoài, có một quy tắc riêng liên quan tới `integrity` và SRI ở mục 9.

## 4. Tính hash chính xác

Hash là phép tính trên byte. Chỉ cần thay đổi một byte trong nội dung đầu vào, digest sẽ thay đổi đáng kể. Các khác biệt dễ bị bỏ qua gồm:

- Khoảng trắng đầu/cuối.
- Dấu xuống dòng LF (`\n`) và CRLF (`\r\n`).
- Tab và số lượng dấu cách.
- Chữ hoa/chữ thường.
- Dấu nháy đơn/kép và dấu backslash.
- Ký tự Unicode và cách mã hóa byte.
- Nội dung sau khi template render, minify hoặc transform.

Hãy tính hash từ **nội dung cuối cùng được phát hành**, không phải từ đoạn code trong editor trước các bước build.

### 4.1 Tính bằng Node.js

Tạo file `inline-script.js` chỉ chứa chính xác phần nội dung nằm giữa thẻ `<script>` trong HTML cuối cùng, không bao gồm hai thẻ HTML:

```js
const { createHash } = require("node:crypto");
const { readFileSync } = require("node:fs");

const exactContent = readFileSync("inline-script.js");
const digest = createHash("sha256").update(exactContent).digest("base64");

console.log(`'sha256-${digest}'`);
```

Đọc file dưới dạng Buffer giúp giữ nguyên byte, bao gồm newline và encoding. Không đọc thành string rồi tự động chuẩn hóa line ending trước khi hash nếu mục tiêu là khớp HTML response.

### 4.2 Tính bằng OpenSSL

Với file chứa đúng nội dung block:

```bash
openssl dgst -sha256 -binary inline-script.js | openssl base64 -A
```

Kết quả Base64 được ghép vào source expression:

```text
'sha256-KET_QUA_BASE64'
```

Có thể dùng `-sha384` hoặc `-sha512` nếu policy và quy trình build chọn thuật toán tương ứng. Dùng cùng một thuật toán khi tính digest và khai báo prefix.

### 4.3 Kiểm tra byte trước khi phát hành

Nếu hash không khớp, hãy lưu HTML response thực tế từ Network và trích nội dung block từ response đó. So sánh byte với file được dùng để tạo hash. Đừng chỉ nhìn hai đoạn code trong editor vì template engine, CDN, minifier hoặc middleware có thể thay đổi output.

## 5. Whitespace và bước build có thể làm hash thay đổi

Ví dụ hai block sau nhìn gần giống nhau nhưng nội dung khác:

```html
<script>initializeApp();</script>
```

```html
<script>
  initializeApp();
</script>
```

Phần nội dung giữa hai thẻ khác nhau về newline và khoảng trắng, do đó hash có thể khác. Minifier có thể loại bỏ whitespace; formatter có thể thêm newline; template engine có thể chèn indentation. Hash phải khớp nội dung sau các biến đổi đó.

Quy trình nên là:

1. Render hoặc build HTML theo đúng cấu hình production.
2. Trích các inline block cuối cùng.
3. Tính hash trên nội dung đã phát hành.
4. Sinh CSP header cùng artifact HTML.
5. Kiểm thử response sau proxy/CDN để xác nhận nội dung không bị biến đổi tiếp.

Không chỉnh tay hash trong header sau mỗi lần thay code. Hãy để build pipeline sinh và cập nhật policy từ cùng một nguồn nội dung.

## 6. Hash cho inline `<style>` block

Hash source cũng áp dụng cho inline style element:

```html
<style>
  .notice {
    color: #2457a7;
    font-weight: 600;
  }
</style>
```

Policy có thể chứa:

```http
Content-Security-Policy: style-src 'self' 'sha256-BASE64_DIGEST'
```

Hash được tính trên nội dung của style block, không gồm thẻ `<style>`. Nếu CSS được format lại hoặc nội dung động thay đổi, hash phải được tạo lại. Với một số block inline tĩnh, hash có thể dễ quản lý hơn nonce vì không cần tạo nonce mới cho từng response.

Nếu ứng dụng dùng `style-src-elem`, hash cho style element cần nằm trong directive được áp dụng cho style element. Nếu directive chi tiết không có, browser fallback về `style-src` rồi `default-src` theo quy tắc CSP.

## 7. Hash source không tự cho phép style attribute hoặc event handler

Một nhầm lẫn thường gặp là cho rằng thêm hash vào `script-src` sẽ cho phép mọi inline JavaScript, hoặc thêm hash vào `style-src` sẽ cho phép mọi `style="..."`. Điều này không đúng.

Ví dụ:

```html
<button onclick="saveDraft()">Lưu</button>
<div style="color: #2457a7">Thông báo</div>
```

Các trường hợp này là **inline attribute**, không phải script/style element. Để cho phép một số attribute cụ thể bằng hash, CSP cần keyword `'unsafe-hashes'` cùng hash phù hợp trong directive tương ứng.

## 8. `'unsafe-hashes'` cho event handler và style attribute

`'unsafe-hashes'` cho phép browser áp dụng hash source tới một số inline event handler hoặc style attribute. Đây là ngoại lệ cần cân nhắc vì nó mở rộng phạm vi hash ngoài `<script>`/`<style>` element.

### 8.1 Event handler attribute

Ví dụ HTML cũ:

```html
<button onclick="saveDraft()">Lưu</button>
```

Với CSP Level 3, có thể cho phép handler cụ thể bằng policy dạng:

```http
Content-Security-Policy: script-src 'self'; script-src-attr 'unsafe-hashes' 'sha256-HASH_CUA_HANDLER'
```

Hash được tính trên nội dung handler theo cách browser diễn giải attribute, ví dụ phần `saveDraft()`; không hash toàn bộ chuỗi HTML của button hoặc tên attribute. Nếu không khai báo `script-src-attr`, `script-src` là fallback cho inline handler.

### 8.2 Style attribute

Ví dụ:

```html
<div style="color: #2457a7">Thông báo</div>
```

Policy có thể dùng:

```http
Content-Security-Policy: style-src 'self'; style-src-attr 'unsafe-hashes' 'sha256-HASH_CUA_STYLE_ATTRIBUTE'
```

Hash được tính trên giá trị style attribute, không gồm tên `style` và dấu nháy HTML. Nếu không có `style-src-attr`, browser fallback về `style-src`.

### 8.3 Vì sao `'unsafe-hashes'` làm tăng rủi ro?

Hash là giá trị công khai trong CSP header. Nếu một handler được allowlist bằng hash, kẻ tấn công có thể cố chèn cùng nội dung handler vào một attribute khác do họ kiểm soát. Browser không biết block/attribute nào là “bản gốc” mà chỉ so nội dung với hash được phép.

Vì vậy:

- Chỉ dùng `'unsafe-hashes'` cho một số trường hợp legacy thực sự cần.
- Giữ handler được allowlist ngắn, không có quyền nhạy cảm ngoài ý muốn.
- Không dùng hash để cho phép các handler tổng quát hoặc nhận dữ liệu không tin cậy.
- Ưu tiên chuyển inline event handler sang `addEventListener`.
- Ưu tiên chuyển style attribute sang class và stylesheet.

## 9. Hash source và Subresource Integrity (SRI)

CSP hash source và **Subresource Integrity (SRI)** đều dùng digest, nhưng chúng có mục đích và vị trí khác nhau.

| Cơ chế | Nơi khai báo | Mục đích |
| --- | --- | --- |
| CSP hash source cho inline block | CSP header, ví dụ `script-src 'sha384-...'` | Cho phép một nội dung inline cụ thể theo hash |
| SRI | Attribute `integrity` trên `<script>` hoặc `<link>` | Browser xác minh nội dung tài nguyên được tải có khớp digest mong đợi |
| CSP hash source cho external script | CSP header kết hợp với `integrity` phù hợp trên element theo CSP Level 3 | Cho phép external script dựa trên hash metadata của tài nguyên |

Ví dụ external script có SRI:

```html
<script
  src="https://cdn.example.com/library.min.js"
  integrity="sha384-BASE64_DIGEST"
  crossorigin="anonymous"></script>
```

SRI kiểm tra byte của file JavaScript được tải. Để CSP cho phép external script bằng hash source, CSP Level 3 có thể đối chiếu hash trong `integrity` với hash được liệt kê trong `script-src`. Nếu tài nguyên cross-origin, SRI còn cần response đáp ứng CORS phù hợp; `crossorigin="anonymous"` cùng `Access-Control-Allow-Origin` phù hợp thường được dùng.

SRI không thay CSP: SRI xác minh tính toàn vẹn của tài nguyên cụ thể, còn CSP giới hạn những nguồn/hành vi browser được phép. CSP hash cho inline block cũng không tự cung cấp cơ chế xác minh file ngoài nếu thiếu quy tắc integrity tương ứng.

## 10. Hash source khác nonce source như thế nào?

| Tiêu chí | Hash source | Nonce source |
| --- | --- | --- |
| Dựa trên | Nội dung chính xác của block | Giá trị nonce khớp giữa header và element |
| Phù hợp với | Inline code tĩnh, ổn định | Inline code cần thay đổi hoặc render động theo response |
| Giá trị | Có thể tính ở build time | Phải sinh ngẫu nhiên cho mỗi response |
| Cache HTML | Dễ cache hơn nếu nội dung và policy ổn định | Cần bảo đảm nonce header/HTML luôn cùng response và không tái sử dụng sai |
| Khi nội dung thay đổi | Phải tính lại hash | Không cần đổi nonce chỉ vì code thay đổi, nhưng vẫn phải giữ nonce ngẫu nhiên theo response |
| Tính bí mật | Hash không bí mật | Nonce cần khó đoán và không bị lộ trước khi response được gửi |

Chọn hash khi inline block tĩnh và build pipeline có thể duy trì digest chính xác. Chọn nonce khi nội dung inline được tạo động hoặc có nhiều block thay đổi theo response. Có thể kết hợp hai cách trong cùng policy nếu có lý do rõ ràng.

Không dùng nonce cố định như một hash giả. Nonce phải được tạo mới bằng CSPRNG cho từng response HTML. Hash thì không cần bí mật; an toàn đến từ việc chỉ allowlist nội dung đã kiểm tra và giữ cho những block khác không thể thực thi.

## 11. Hash không phải chữ ký bí mật và không ngăn mọi HTML injection

Hash source không phải token bí mật. Bất kỳ người nào nhận response đều có thể đọc CSP header và biết digest được cho phép. Hash chỉ chứng minh nội dung candidate khớp digest đã khai báo; nó không chứng minh vị trí DOM hoặc ý định của người tạo markup.

Nếu một attacker có thể chèn markup và sao chép chính xác nội dung của một inline script đã được allowlist, browser có thể chấp nhận block có hash khớp. Do đó:

- Không allowlist một script tổng quát có thể thao tác nguy hiểm dựa trên dữ liệu DOM không tin cậy.
- Giữ inline block nhỏ, tĩnh và ít quyền.
- Không dùng hash source thay output encoding hoặc sanitizer.
- Sửa DOM XSS tại source/sink; cân nhắc Trusted Types để kiểm soát injection sink.
- CSP vẫn cần `object-src`, `base-uri`, `frame-ancestors`, `connect-src` và các directive khác theo mô hình đe dọa.

Hash source cũng không cho phép `eval()` hoặc `Function()` tự động. Quyền thực thi chuỗi được điều khiển bởi các quy tắc riêng, ví dụ `'unsafe-eval'`; không thêm chúng chỉ để xử lý lỗi CSP.

## 12. Fallback và directive áp dụng

Hash phải được đặt trong directive phù hợp với loại nội dung:

| Nội dung | Directive ưu tiên | Fallback khi thiếu |
| --- | --- | --- |
| Inline `<script>` block | `script-src-elem` nếu được khai báo; nếu không `script-src` | `default-src` |
| Inline event handler | `script-src-attr` nếu được khai báo; nếu không `script-src` | `default-src` |
| Inline `<style>` block | `style-src-elem` nếu được khai báo; nếu không `style-src` | `default-src` |
| `style` attribute | `style-src-attr` nếu được khai báo; nếu không `style-src` | `default-src` |

Ví dụ policy tách riêng:

```http
Content-Security-Policy: default-src 'self'; script-src 'self'; script-src-elem 'self' 'sha256-HASH_SCRIPT'; script-src-attr 'none'; style-src 'self'; style-src-elem 'self' 'sha256-HASH_STYLE'; style-src-attr 'none'
```

Policy trên cho phép các block cụ thể theo hash trong element, đồng thời chặn inline event handler và style attribute. Các directive chi tiết hơn có thể làm thay đổi cách `script-src`/`style-src` được áp dụng; hãy kiểm tra policy hoàn chỉnh và hỗ trợ browser mục tiêu.

## 13. Tạo hash trong build pipeline

Hash source dễ duy trì nhất khi được sinh tự động từ cùng artifact mà hệ thống phát hành. Một pipeline cơ bản:

1. Build và render HTML theo cấu hình production.
2. Xác định các inline script/style block được phê duyệt.
3. Trích nội dung chính xác sau mọi bước transform/minify.
4. Tính SHA-256/384/512 và encode Base64 chuẩn.
5. Tạo CSP header từ danh sách hash được sinh.
6. Kiểm thử HTML response và header trên môi trường gần production.
7. Phát hành HTML và CSP cùng một phiên bản.
8. Khi nội dung inline thay đổi, build tự tính lại hash và cập nhật policy.

Không duy trì danh sách hash thủ công ở nhiều nơi. Tránh trường hợp template cập nhật nhưng CSP header ở gateway vẫn dùng hash cũ. Nên lưu artifact/build manifest để biết hash nào tương ứng với block và phiên bản nào.

### 13.1 Cache và CDN

Với hash source, policy thường ổn định nếu nội dung inline ổn định. Tuy nhiên, CDN hoặc reverse proxy có thể minify HTML, chèn script/style hoặc biến đổi whitespace sau khi hash được tạo. Khi đó browser thấy nội dung khác digest và chặn block.

Nếu hạ tầng có HTML rewriting, cần:

- Tính hash sau bước rewrite cuối cùng; hoặc tắt rewrite đối với HTML có hash policy.
- Bảo đảm HTML và CSP header được cache/invalidated cùng nhau.
- Không để một phiên bản HTML đi cùng CSP của phiên bản khác.
- Kiểm tra response cuối qua CDN, không chỉ response từ origin server.

## 14. Ví dụ policy thực tế

### 14.1 Chỉ cho phép một inline script tĩnh

```http
Content-Security-Policy: default-src 'self'; script-src 'self' 'sha256-HASH_INLINE_SCRIPT'; object-src 'none'; base-uri 'none'
```

Phù hợp khi ứng dụng có một script bootstrap tĩnh cần inline. Các inline script khác không có hash khớp sẽ bị chặn.

### 14.2 Cho phép một style block tĩnh và chặn style attribute

```http
Content-Security-Policy: default-src 'self'; style-src 'self' 'sha256-HASH_STYLE_BLOCK'; style-src-attr 'none'
```

Style block được cho phép bằng hash; style attribute bị chặn. Có thể cần `style-src-elem` riêng nếu policy sử dụng directive Level 3.

### 14.3 Policy cho inline block và external script có SRI

```http
Content-Security-Policy: default-src 'self'; script-src 'self' 'sha384-HASH_EXTERNAL_SCRIPT' 'sha256-HASH_INLINE_BOOTSTRAP'; object-src 'none'; base-uri 'none'
```

External script cần `integrity` khớp hash được CSP cho phép theo quy tắc hỗ trợ của browser; inline bootstrap cần nội dung khớp hash tương ứng. Nếu dùng CDN cross-origin, kiểm tra SRI/CORS và response thực tế.

Các giá trị `HASH_*` là placeholder. Không sao chép nguyên policy này vào production trước khi sinh digest, xác minh nguồn tài nguyên và kiểm thử đầy đủ.

## 15. Debug khi hash không khớp

Khi browser báo CSP violation, kiểm tra theo trình tự:

1. Xác định directive vi phạm: `script-src`, `script-src-elem`, `script-src-attr`, `style-src`, `style-src-elem` hay `style-src-attr`.
2. Xác định loại nội dung: inline element, event handler, style attribute hay external resource.
3. Kiểm tra CSP header thực tế trong Network; có thể có nhiều policy cùng được thực thi.
4. Trích nội dung chính xác từ HTML response, không lấy từ source template trước khi render.
5. Kiểm tra whitespace, line ending, encoding và transform/minify.
6. Tính lại digest với đúng thuật toán và Base64 chuẩn.
7. Nếu là attribute, xác nhận policy có `'unsafe-hashes'` và hash nằm trong directive đúng.
8. Nếu là external script, kiểm tra `integrity`, CSP hash source và CORS/SRI nếu cross-origin.
9. Kiểm tra proxy/CDN có thêm CSP header hoặc thay đổi HTML không.
10. Thêm regression test để build phát hiện lệch hash trước release.

Một trang có thể nhận nhiều CSP header. Browser thực thi đồng thời các policy, nên một header cho phép hash không thể nới lỏng policy khác đang chặn inline code. Kiểm tra tất cả header, kể cả header được thêm tại gateway/CDN.

## 16. Report-Only và rollout an toàn

Trước khi enforce policy hash, có thể dùng `Content-Security-Policy-Report-Only` để quan sát các inline block hiện có và xác định block nào thật sự cần được giữ lại.

Ví dụ:

```http
Content-Security-Policy-Report-Only: default-src 'self'; script-src 'self' 'sha256-HASH_INLINE_SCRIPT'; style-src 'self' 'sha256-HASH_STYLE'; report-to csp-endpoint
```

Report-Only không chặn nội dung; nó báo cáo vi phạm theo cấu hình reporting. Nếu response đồng thời có một CSP enforcement header khác, policy enforce đó vẫn chặn như bình thường.

Quy trình rollout:

1. Thu thập inline script/style đang chạy trên các luồng quan trọng.
2. Phân loại block tĩnh, block động, event handler và style attribute.
3. Chuyển inline handler sang `addEventListener`, style attribute sang class nếu có thể.
4. Sinh hash cho các block tĩnh thực sự cần giữ.
5. Kiểm tra report trong staging và một nhóm production phù hợp.
6. Xử lý violation hợp lệ; không thêm hash cho mọi block một cách tự động mà thiếu review.
7. Chuyển policy sang enforcement và theo dõi lỗi giao diện/chức năng.

Không đưa report endpoint vào policy mà chưa bảo vệ khỏi spam và dữ liệu không tin cậy. CSP report có thể chứa URL và thông tin về tài nguyên bị chặn; giới hạn lưu trữ và quyền truy cập theo chính sách dữ liệu.

## 17. Thực hành kiểm chứng trong môi trường lab

Thực hiện trên trang local hoặc ứng dụng lab do bạn quản lý. Dùng script/style vô hại và dữ liệu giả; không thử trên website bên ngoài.

### Bài thử A — Hash cho inline script

Tạo một trang có một inline script tĩnh ghi thông báo ra Console. Trích chính xác nội dung script block, tính SHA-256 bằng Node.js hoặc OpenSSL, rồi thêm digest vào `script-src`.

**Kỳ vọng:** Block có nội dung khớp hash được thực thi; nếu thay đổi một ký tự hoặc whitespace rồi giữ hash cũ, browser tạo violation và chặn block.

### Bài thử B — Hash cho inline style

Tạo một `<style>` block tĩnh, tính hash nội dung block và thêm vào `style-src` hoặc `style-src-elem` theo policy.

**Kỳ vọng:** Style block khớp hash được áp dụng. Khi format CSS hoặc thêm một dòng mới, digest cũ không còn khớp.

### Bài thử C — Event handler và `'unsafe-hashes'`

Trong lab, tạo một nút có handler vô hại. So sánh policy chỉ có hash với policy có `'unsafe-hashes'` và hash trong `script-src-attr`.

**Kỳ vọng:** Hash đơn thuần không tự cho phép inline event handler; policy có `'unsafe-hashes'` cùng digest phù hợp có thể cho phép handler cụ thể trên browser hỗ trợ. Sau đó chuyển handler sang `addEventListener` và loại bỏ ngoại lệ.

### Bài thử D — So sánh CSP hash với SRI

Tạo file JavaScript tĩnh và gắn `integrity` vào thẻ script. Thử thay đổi byte file sau khi tính digest; quan sát SRI. Sau đó thử policy CSP hash cho external script với integrity tương ứng.

**Kỳ vọng:** SRI kiểm tra nội dung tài nguyên được tải; CSP quyết định script có được phép theo policy hay không. Với CDN cross-origin, cần cấu hình CORS phù hợp cho SRI.

### Bài thử E — Build output và cache

Cho build tool format/minify HTML sau khi hash được tính. So sánh digest trước/sau và kiểm tra browser. Sau đó điều chỉnh pipeline để hash được sinh từ artifact cuối cùng.

**Kỳ vọng:** Hash từ source chưa qua transform có thể không khớp HTML được phát hành. Sinh hash sau bước cuối cùng và cache HTML/header cùng phiên bản sẽ loại bỏ sai lệch.

## 18. Các lỗi thường gặp

| Lỗi | Vì sao sai | Cách xử lý |
| --- | --- | --- |
| Hash cả file HTML hoặc gồm thẻ `<script>` | CSP đối chiếu nội dung block, không phải toàn document | Hash đúng phần nội dung nằm trong element |
| Tính hash từ source trước minify | HTML cuối cùng có byte khác | Tính từ artifact sau build/transform |
| Dùng hex thay Base64 | CSP source expression yêu cầu Base64 digest | Dùng Base64 chuẩn |
| Dùng Base64URL | Alphabet/format khác digest Base64 thông thường | Dùng Base64 chuẩn |
| Cho rằng hash không quan tâm whitespace | Thay đổi nội dung làm digest thay đổi | Giữ output ổn định và sinh hash tự động |
| Thêm hash vào `script-src` để cho phép `onclick` | Event handler cần quy tắc `'unsafe-hashes'` | Refactor handler hoặc dùng ngoại lệ có giới hạn |
| Thêm hash vào `style-src` để cho phép mọi style attribute | Style attribute có directive/điều kiện riêng | Dùng `style-src-attr` và `'unsafe-hashes'` nếu thật sự cần |
| Nhầm CSP hash với SRI | Một cái là policy cho phép, một cái xác minh tài nguyên | Dùng đúng cơ chế và phối hợp khi cần |
| Coi hash là bí mật | CSP header công khai | Không dựa vào tính bí mật của digest |
| Allowlist script block quá tổng quát | Attacker có thể cố chèn lại đúng block được phép | Giữ block nhỏ, tĩnh, ít quyền và sửa HTML injection |
| Hash header và HTML khác phiên bản | Browser chặn block do mismatch | Phát hành và cache đồng bộ cùng artifact |
| Thêm nhiều CSP header mà không kiểm tra | Các policy được áp dụng đồng thời | Kiểm tra header từ app, proxy và CDN |

## 19. Checklist review hash source

- [ ] Hash chỉ được dùng cho inline block tĩnh, đã được review và thực sự cần thiết.
- [ ] Digest dùng SHA-256, SHA-384 hoặc SHA-512 và Base64 chuẩn.
- [ ] Hash được tính trên nội dung thực tế của block, không gồm thẻ bao ngoài.
- [ ] Whitespace, newline, encoding và bước minify/build được tính đến.
- [ ] Hash được sinh tự động từ artifact cuối cùng.
- [ ] Hash cho `<script>` nằm trong directive script phù hợp.
- [ ] Hash cho `<style>` nằm trong directive style phù hợp.
- [ ] Event handler/style attribute chỉ được cho phép khi hiểu rõ `'unsafe-hashes'` và phạm vi của nó.
- [ ] Ưu tiên loại bỏ inline event handler và style attribute bằng refactor.
- [ ] External script dùng SRI `integrity` khi cần xác minh byte; CSP policy cũng được kiểm tra riêng.
- [ ] Không coi hash là bí mật hoặc bằng chứng xác thực.
- [ ] Inline block được allowlist nhỏ, tĩnh và không có hành vi nguy hiểm theo dữ liệu không tin cậy.
- [ ] HTML và CSP header được phát hành/cache đồng bộ.
- [ ] Đã kiểm tra nhiều CSP header, Report-Only và enforcement trên browser mục tiêu.
- [ ] Có regression test phát hiện hash mismatch trước release.

## 20. Câu hỏi tự kiểm tra

1. Hash source trong CSP có dạng nào và những thuật toán nào được hỗ trợ?
2. Khi hash inline `<script>`, phần nào của HTML được đưa vào digest?
3. Vì sao newline hoặc bước minify có thể làm hash không khớp?
4. Hash cho `<style>` block khác hash cho `style` attribute ra sao?
5. `'unsafe-hashes'` cần thiết trong tình huống nào và vì sao nó làm tăng phạm vi cho phép?
6. CSP hash source khác SRI ở mục tiêu và vị trí khai báo nào?
7. Vì sao hash không phải bí mật và không tự ngăn attacker chèn lại block đã allowlist?
8. Khi nào hash source phù hợp hơn nonce, và ngược lại?
9. Nếu policy cho phép hash nhưng browser vẫn chặn, cần kiểm tra những yếu tố nào?
10. Làm thế nào để build pipeline bảo đảm HTML và CSP header luôn cùng hash?

## 21. Ghi nhớ

Hash source cho phép một inline script hoặc style cụ thể khi digest của nội dung khớp hash trong CSP. Hash phải được tính trên nội dung chính xác mà browser nhận, dùng SHA-256/384/512 và Base64 chuẩn. Whitespace, line ending, Unicode và các bước build/minify đều có thể làm thay đổi digest.

Hash cho `<script>`/`<style>` element khác với hash cho event handler hoặc style attribute; các attribute cần `'unsafe-hashes'` và nên được refactor khi có thể. CSP hash cũng khác SRI: CSP quyết định quyền thực thi theo policy, SRI xác minh nội dung tài nguyên được tải. **Hãy sinh hash từ artifact cuối cùng, allowlist block nhỏ đã review, đồng bộ HTML với CSP header và tiếp tục phòng vệ XSS ở source/sink.**
