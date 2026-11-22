# Canonicalization trước khi kiểm tra policy

## 1. Vì sao phải canonicalize trước khi kiểm tra policy?

Một giá trị đầu vào có thể có nhiều cách biểu diễn nhưng cùng được hệ thống hiểu là một tài nguyên hoặc một danh tính. Ví dụ, một URL có thể chứa percent-encoding; một đường dẫn có thể có dấu chấm . và ..; một tên miền có thể dùng Unicode hoặc Punycode; một chuỗi Unicode có thể được biểu diễn bằng các tổ hợp code point khác nhau; một request có thể chứa tham số trùng lặp hoặc header được viết theo nhiều cách.

Nếu API kiểm tra quyền trên một dạng biểu diễn nhưng router, proxy, cache, filesystem hoặc dependency sử dụng một dạng khác, kẻ tấn công có thể tạo ra **parser differential**: mỗi thành phần hiểu request theo một cách. Khi đó, policy có thể cho phép một giá trị trong khi thành phần thực thi lại truy cập tài nguyên khác.

Canonicalization là quá trình chuyển dữ liệu sang một biểu diễn chuẩn, nhất quán theo ngữ nghĩa của giao thức hoặc nghiệp vụ. Trong bảo mật API, mục tiêu là bảo đảm mọi bước sau đó cùng nhìn thấy một giá trị đã được phân tích và chuẩn hóa theo cùng quy tắc.

Ví dụ:

- Policy kiểm tra đường dẫn /public/../admin trước khi chuẩn hóa và cho rằng nó nằm dưới /public; router chuẩn hóa thành /admin.
- Gateway kiểm tra host đã chuyển chữ thường, nhưng backend dùng Host khác hoặc X-Forwarded-Host chưa được xác minh để tạo URL.
- Cache dùng query parameter đầu tiên, còn application dùng giá trị cuối cùng khi có tham số trùng; cache và authorization không còn đồng thuận về tài nguyên.
- Một lớp giải mã %252e%252e một lần, lớp khác giải mã thêm lần nữa và nhận .., làm thay đổi ranh giới path.
- Policy so sánh tên người dùng ở dạng Unicode NFC, còn database hoặc service khác so sánh chuỗi chưa chuẩn hóa, dẫn tới hai danh tính bị coi là một ở một nơi nhưng khác ở nơi khác.

Quy tắc cốt lõi: **parse nghiêm ngặt, canonicalize một lần theo đúng ngữ nghĩa, validate trên giá trị đã chuẩn hóa, rồi dùng chính giá trị đó cho authorization, routing và thao tác dữ liệu.**

## 2. Phân biệt parsing, canonicalization, validation và authorization

Các bước này liên quan nhưng giải quyết các câu hỏi khác nhau:

| Bước | Câu hỏi | Ví dụ |
|---|---|---|
| Parsing | Byte đầu vào có cấu trúc giao thức hợp lệ không? | Phân tích request target, JSON, header và encoding |
| Canonicalization | Có nhiều cách biểu diễn tương đương cần quy về một dạng không? | Chuẩn hóa path, Unicode hoặc hostname theo quy tắc đã chọn |
| Validation | Giá trị sau parsing/canonicalization có đúng schema và ràng buộc không? | UUID đúng định dạng, page size trong giới hạn |
| Authorization / policy | Principal có được phép thực hiện hành động trên tài nguyên/giá trị này không? | User có quyền đọc object và field tương ứng |
| Business rule | Thao tác có hợp lệ trong trạng thái nghiệp vụ hiện tại không? | Đơn hàng đã giao không thể đổi địa chỉ |

Canonicalization không thay thế validation. Một URL được chuẩn hóa vẫn có thể trỏ tới host không được phép. Một đường dẫn hợp lệ vẫn có thể thuộc tenant khác. Một chuỗi Unicode chuẩn hóa vẫn có thể chứa ký tự không được nghiệp vụ chấp nhận.

Authorization cũng không thể chỉ kiểm tra chuỗi thô. Policy cần nhận cùng biểu diễn tài nguyên mà tầng thực thi sẽ sử dụng. Nếu router, cache hoặc repository diễn giải khác nhau, kiểm tra quyền có thể vô nghĩa.

## 3. Pipeline xử lý an toàn

Một pipeline tổng quát cho request API:

~~~text
Raw HTTP bytes
     |
     v
Giới hạn kích thước / framing / encoding
     |
     v
Strict parsing theo đúng protocol
     |
     v
Canonicalization theo từng loại dữ liệu
     |
     v
Schema + syntax + semantic validation
     |
     v
Authentication / principal context
     |
     v
Authorization trên canonical resource và action
     |
     v
Business invariant + transaction
     |
     v
Thực thi bằng chính giá trị đã kiểm tra
~~~

Trong thực tế, authentication có thể diễn ra trước hoặc song song với parsing một số thành phần, nhưng không được dùng input chưa xác minh làm danh tính. Giới hạn body/header phải được áp dụng trước khi parser cấp phát tài nguyên lớn. Điểm quan trọng là policy không được kiểm tra một representation rồi tầng thực thi tự parse hoặc normalize lại theo cách khác.

Các nguyên tắc triển khai:

1. Giới hạn byte và cấu trúc request ngay tại edge và application.
2. Dùng parser chuẩn, strict và nhất quán; từ chối encoding hoặc framing mơ hồ.
3. Chuyển input thành kiểu dữ liệu có cấu trúc thay vì truyền chuỗi thô qua nhiều lớp.
4. Canonicalize theo loại dữ liệu, không dùng một hàm normalize chung cho mọi trường.
5. Validate trên giá trị canonical và áp dụng giới hạn độ dài/kích thước sau chuẩn hóa.
6. Kiểm tra quyền trên đúng object, tenant, property và action sẽ được sử dụng.
7. Truyền canonical value hoặc typed object xuống router/service/repository; không giải mã lần nữa.
8. Log representation an toàn hoặc fingerprint, không log secret hay raw payload nhạy cảm.

## 4. Quy tắc canonicalization phải theo ngữ nghĩa

Không có một phép chuẩn hóa phù hợp cho mọi chuỗi. Quy tắc phụ thuộc vào dữ liệu là path, hostname, username, email, số tiền, token, query parameter hay nội dung tự do.

| Loại dữ liệu | Chuẩn hóa có thể cần | Điều cần tránh |
|---|---|---|
| URI/path | Percent-decoding theo quy tắc, dot-segment handling, path policy | Decode lặp, thay đổi ranh giới segment không nhất quán |
| Hostname | Lowercase DNS name, IDNA/Punycode theo policy | Tin Host header tùy ý hoặc so sánh Unicode không nhất quán |
| Unicode identifier | NFC hoặc quy tắc Unicode được công bố | Áp dụng NFKC tùy tiện lên nội dung tự do hoặc bí mật |
| Query parameter | Quy tắc duplicate, thứ tự, encoding và kiểu dữ liệu | Để proxy và application chọn giá trị khác nhau |
| JSON | Parser strict, duplicate-key policy, kiểu số rõ ràng | Parser đầu tiên/ cuối cùng khác nhau giữa các thư viện |
| HTTP header | Parser theo HTTP, xử lý OWS và header lặp đúng chuẩn | Tự split hoặc nối header theo quy tắc riêng |
| IP address | Parse thành kiểu địa chỉ nhị phân, xử lý IPv4-mapped IPv6 | So sánh chuỗi textual hoặc chấp nhận dạng số mơ hồ |
| File path | Resolve trong root cho phép và kiểm tra symlink | Chỉ lọc chuỗi ../ |
| Token/secret | Giữ nguyên byte/chuỗi theo định dạng giao thức | Lowercase, Unicode normalize hoặc trim tùy tiện |

Không làm sạch mọi input bằng cách xóa ký tự lạ. Cách đó có thể biến hai giá trị khác nhau thành một giá trị hợp lệ ngoài ý muốn, làm sai chữ ký, danh tính hoặc policy. Với biểu diễn mơ hồ, từ chối thường an toàn hơn đoán cách hiểu.

## 5. URI và path: percent-encoding, dot segment và double decoding

### 5.1 Percent-encoding

URI có thể biểu diễn một byte bằng %HH. Ví dụ %2F là byte slash /, %2E là dấu chấm . Thành phần xử lý request có thể giải mã ở các thời điểm khác nhau. Nếu gateway, router và application không thống nhất, một chuỗi có thể thay đổi cấu trúc sau khi policy đã chạy.

Ví dụ:

~~~text
/files/public/report.pdf
/files/public%2Freport.pdf
/files/public/%2e%2e/private/secret.txt
/files/%252e%252e/private/secret.txt
~~~

%252e sau một lần decode thành %2e; nếu thành phần phía sau decode lần nữa, nó thành dấu chấm. Đây là một dạng double decoding. Không thực hiện giải mã đệ quy cho đến khi chuỗi trông có vẻ bình thường.

Quy tắc an toàn:

- Dùng một URI parser được duy trì, tuân thủ giao thức.
- Xác định rõ thành phần nào decode path và decode bao nhiêu lần.
- Từ chối percent-encoding sai định dạng, byte không hợp lệ hoặc cách biểu diễn không được endpoint hỗ trợ.
- Không decode dấu phân cách segment nếu router phía sau có thể diễn giải khác; cân nhắc từ chối encoded slash/backslash.
- Không ghép chuỗi raw path với filesystem path hoặc route rồi mới kiểm tra.
- Đưa path đã parse/canonicalize vào authorization và routing.

### 5.2 Dot-segment và path traversal

Đường dẫn có . và .. có thể thay đổi vị trí sau khi chuẩn hóa. Ví dụ:

~~~text
/api/public/../admin/users
~~~

Nếu policy chỉ kiểm tra prefix /api/public trên chuỗi thô, nhưng router loại bỏ public/.., request có thể đi tới /api/admin/users.

Không chỉ kiểm tra startsWith("/public"). Hãy parse path thành segment, áp dụng một quy tắc dot-segment thống nhất và kiểm tra boundary theo segment. /publicity không phải con của /public; so sánh chuỗi prefix đơn giản dễ sai.

Đối với route API, tốt nhất là từ chối path chứa dot segment nếu ứng dụng không có nhu cầu hợp lệ. Nếu phải hỗ trợ, chuẩn hóa trước khi route và đảm bảo proxy/backend dùng cùng kết quả.

### 5.3 Backslash và dấu phân cách khác

Một số runtime hoặc filesystem xem backslash là dấu phân cách path; một số URI parser chỉ xem slash là dấu phân cách. Windows path có thể có drive letter, UNC path hoặc device namespace. Không giả định slash và backslash có cùng ngữ nghĩa ở mọi lớp.

Nếu endpoint nhận tên file hoặc path:

- Ưu tiên nhận một file ID do server tạo thay vì path tùy ý.
- Nếu cần path, parse theo filesystem đích và từ chối drive/UNC/device path không được phép.
- Resolve path dưới một root cố định, kiểm tra kết quả vẫn nằm trong root.
- Xử lý symlink và race condition; kiểm tra chuỗi trước khi mở file là chưa đủ.
- Mở file qua API an toàn theo handle nếu nền tảng hỗ trợ, tránh TOCTOU giữa kiểm tra và sử dụng.

### 5.4 Không chuẩn hóa hai lần

Một lỗi phổ biến là gateway decode path để kiểm tra policy, rồi framework decode lại khi route. Hãy chọn một lớp làm canonical parser hoặc đảm bảo các lớp có cấu hình và test tương thích. Nếu application chỉ nhận được raw URI, không giả định proxy đã chuẩn hóa trừ khi hợp đồng giữa các hop được xác định và kiểm chứng.

## 6. Unicode và định danh

Unicode cho phép cùng một ký tự hiển thị được biểu diễn bằng một code point dựng sẵn hoặc một chuỗi base character cộng combining mark. Ví dụ chữ có dấu có thể có dạng composed hoặc decomposed. Hai chuỗi nhìn giống nhau có thể khác byte và khác kết quả so sánh.

### 6.1 NFC và NFKC

- **NFC** chuẩn hóa các chuỗi tương đương canonical composition về một dạng chuẩn.
- **NFKC** còn áp dụng compatibility mapping, có thể gộp các ký tự tương thích như một số dạng full-width hoặc ký tự trình bày.

Với identifier như username hoặc tenant slug, tổ chức có thể chọn NFC hoặc một profile Unicode/precis phù hợp và áp dụng nhất quán khi đăng ký, đăng nhập, tìm kiếm và so sánh. NFKC có thể hữu ích trong một số chính sách identifier nhưng cũng có thể làm thay đổi ý nghĩa của dữ liệu; không áp dụng tùy tiện.

Với nội dung tự do như tên hiển thị, ghi chú hoặc văn bản người dùng, thường nên bảo toàn nội dung gốc để hiển thị và chỉ tạo representation phục vụ tìm kiếm/so sánh theo chính sách riêng.

### 6.2 Case folding và locale

Không dùng toLowerCase() phụ thuộc locale mặc định để chuẩn hóa identifier. Một số ngôn ngữ có quy tắc chữ hoa/thường khác nhau. Dùng quy tắc case folding không phụ thuộc locale hoặc profile đã chọn cho loại identifier.

Không lowercase mọi chuỗi. Password, API token, chữ ký, mã phân biệt hoa/thường và dữ liệu nhị phân phải được giữ nguyên theo định dạng. Email cũng có phần local-part có quy tắc riêng; nếu sản phẩm muốn so sánh không phân biệt hoa/thường, phải định nghĩa chính sách nghiệp vụ và áp dụng nhất quán thay vì tùy tiện lowercase toàn bộ địa chỉ.

### 6.3 Confusable và mixed-script

Một số ký tự thuộc các script khác nhau nhìn gần giống nhau, ví dụ chữ Latin và Cyrillic. Canonicalization không thể giải quyết hoàn toàn vấn đề homograph. Với domain, username, tenant slug hoặc định danh có tác động bảo mật:

- Giới hạn script được phép nếu nghiệp vụ cho phép.
- Phát hiện mixed-script hoặc ký tự confusable theo Unicode security guidance.
- Hiển thị dạng punycode hoặc cảnh báo khi cần đối với hostname quốc tế hóa.
- Không dùng hình thức hiển thị làm khóa authorization; dùng canonical identifier đã xác minh.
- Cân nhắc quy trình duyệt/claim tên tenant và tên miền.

## 7. Hostname, IDNA và Host header

Hostname có thể được biểu diễn bằng chữ thường/hoa, dấu chấm cuối, Unicode hoặc Punycode. DNS name không phân biệt hoa/thường, nhưng chuỗi URL và cấu hình ứng dụng có thể có quy tắc khác.

Với hostname dùng trong allowlist hoặc routing:

1. Parse URL bằng URI parser; không tự tách host bằng split(":") vì IPv6 và userinfo làm cú pháp phức tạp.
2. Tách hostname từ cấu trúc URL đã parse.
3. Chuyển domain quốc tế hóa qua profile IDNA được chọn để có dạng ASCII/Punycode thống nhất.
4. Chuẩn hóa chữ hoa/thường theo DNS semantics và xử lý trailing dot theo policy.
5. So sánh domain theo label boundary; example.com.attacker.test không thuộc example.com.
6. Kiểm tra port, scheme, userinfo và hostname đúng allowlist.
7. Dùng canonical hostname đã xác minh cho policy và kết nối.

Không dùng phép kiểm tra host.endsWith("example.com") đơn giản. Nó có thể chấp nhận notexample.com. Nếu cho phép subdomain, so sánh chính xác host == example.com hoặc hậu tố có dấu chấm trước tên miền, theo policy.

Host header ảnh hưởng virtual hosting, redirect, absolute URL và cache. Chỉ chấp nhận host công khai đã cấu hình. Reverse proxy biên phải loại bỏ hoặc ghi đè forwarding header do client gửi; backend chỉ tin Forwarded/X-Forwarded-Host từ proxy được xác thực. Không xây dựng password-reset link, callback URL hoặc origin policy từ Host tùy ý.

## 8. Query parameter và tham số trùng lặp

Một URL có thể chứa tham số lặp:

~~~text
/api/users?role=user&role=admin
~~~

Các framework có thể:

- Lấy giá trị đầu tiên.
- Lấy giá trị cuối cùng.
- Trả danh sách nhiều giá trị.
- Từ chối request có duplicate.

Nếu gateway kiểm tra giá trị đầu tiên là user, nhưng application dùng giá trị cuối cùng là admin, policy có thể bị bypass.

Đối với từng endpoint, định nghĩa rõ:

- Tham số nào được phép xuất hiện nhiều lần, ví dụ filter hoặc list ID.
- Tham số scalar nào phải xuất hiện đúng một lần.
- Thứ tự tham số có ý nghĩa hay không.
- Cách xử lý empty value, missing value và encoded separator.
- Có chấp nhận cả tên parameter ở dạng encoded và unencoded hay không.

Với tham số scalar nhạy cảm như tenant, role, redirect_uri, sort, pageSize hoặc signature, nên từ chối duplicate thay vì chọn một giá trị. Parse thành map/list có cấu trúc rồi validate; không tự parse query string lần nữa ở service.

Không coi dấu + luôn tương đương dấu cách. Quy tắc đó thuộc form URL encoding (application/x-www-form-urlencoded); URI query nói chung có thể mang dấu cộng literal. Hãy dùng parser phù hợp với Content-Type/ngữ cảnh và test cùng parser của framework.

## 9. JSON, duplicate key và kiểu dữ liệu

JSON object về mặt thực tế có thể gặp duplicate member name:

~~~json
{
  "role": "user",
  "role": "admin"
}
~~~

Các parser khác nhau có thể giữ giá trị đầu, giá trị cuối hoặc từ chối. Nếu WAF và application khác hành vi, attacker có thể khai thác parser differential. Với request nhạy cảm, dùng parser strict từ chối duplicate key.

Các điểm cần xác định:

- Giới hạn body size, nesting depth, string length, số property và số phần tử array.
- Từ chối encoding không hợp lệ và Content-Type không được hỗ trợ.
- Không tự ép kiểu mơ hồ, ví dụ chuỗi true thành boolean hoặc 001 thành số nếu contract không cho phép.
- Quy định rõ kiểu số, độ chính xác và giới hạn; tránh dùng floating point cho tiền.
- Xử lý null, field thiếu và field có giá trị mặc định khác nhau.
- Từ chối unknown field đối với request nhạy cảm hoặc dùng schema allowlist.
- Không cho phép property trùng sau khi áp dụng alias hoặc naming strategy.

Với số tiền, quota, ID hoặc giá trị có độ chính xác cao, dùng kiểu decimal/integer có giới hạn rõ ràng. Không để 1, 1.0, 1e0, -0 hoặc số vượt range bị diễn giải khác nhau giữa validator, application và database.

Nếu API ký JSON payload, phải dùng đúng thuật toán canonicalization đã quy định trong giao thức ký. Không tự serialize lại JSON theo thứ tự field hoặc cách biểu diễn số tùy ý rồi kỳ vọng chữ ký vẫn có cùng ngữ nghĩa.

## 10. HTTP header và request framing

Header có quy tắc riêng về tên, whitespace, giá trị lặp và header hop-by-hop. Tên header không phân biệt hoa/thường theo HTTP, nhưng giá trị của nhiều header có ngữ nghĩa riêng và không thể lowercase tùy tiện.

Các rủi ro:

- Content-Length lặp hoặc mâu thuẫn với Transfer-Encoding.
- Header forwarding do client gửi bị proxy nối thêm thay vì xóa.
- Host và :authority khác nhau giữa HTTP/1.1 và HTTP/2.
- Proxy và backend gộp header lặp theo cách khác nhau.
- Whitespace hoặc ký tự control được parser xử lý không nhất quán.

Dùng HTTP parser/proxy được duy trì; từ chối request framing mơ hồ; không tự nối header nhạy cảm. Đặc biệt, không để WAF kiểm tra một ranh giới body còn backend sử dụng ranh giới khác. Kiểm thử đường đi HTTP/1.1, HTTP/2, HTTP/3 và downgrade giữa các phiên bản nếu kiến trúc có hỗ trợ.

Đối với bearer token trong Authorization, giữ đúng token value theo cú pháp giao thức. Không lowercase, Unicode normalize hoặc đưa token vào URL. Không dùng header tùy chỉnh do client gửi để ghi đè principal hoặc tenant context đã xác minh.

## 11. Canonicalization của IP address và SSRF

IP address có nhiều dạng textual. IPv6 có thể viết hoa/thường, rút gọn zero hoặc dùng IPv4-mapped IPv6. Một số parser cũ còn chấp nhận dạng IPv4 số nguyên, octal hoặc hexadecimal. Nếu allowlist so sánh chuỗi, các biểu diễn khác nhau có thể vượt kiểm tra.

### 11.1 Parse IP thành kiểu địa chỉ

Khi kiểm tra IP:

- Dùng parser IP chuẩn và chuyển thành biểu diễn nhị phân/kiểu địa chỉ.
- Chỉ chấp nhận cú pháp IPv4/IPv6 được hệ thống hỗ trợ; từ chối dạng legacy mơ hồ.
- Chuẩn hóa IPv4-mapped IPv6 theo policy để không bỏ sót địa chỉ IPv4 private.
- So sánh subnet bằng phép toán CIDR trên địa chỉ đã parse, không dùng string prefix.
- Phân loại loopback, private, link-local, multicast, unspecified, reserved và địa chỉ metadata theo môi trường.

### 11.2 URL fetch và SSRF

Với endpoint tải ảnh, webhook test, import từ URL hoặc preview link, canonicalization là một phần của chống SSRF:

1. Parse URL đầy đủ; chỉ cho phép scheme cần thiết, thường là HTTPS.
2. Từ chối userinfo, fragment hoặc port ngoài policy nếu không cần.
3. Canonicalize hostname qua IDNA và kiểm tra allowlist/domain boundary.
4. Resolve tất cả bản ghi A/AAAA và kiểm tra từng địa chỉ; từ chối đích private, loopback, link-local, metadata hoặc vùng mạng nội bộ không được phép.
5. Kết nối tới đúng địa chỉ đã kiểm tra hoặc áp dụng egress policy tương đương; tránh DNS rebinding giữa lúc kiểm tra và kết nối.
6. Tắt redirect hoặc kiểm tra lại từng redirect từ đầu, gồm scheme, hostname, DNS và IP đích.
7. Giới hạn connect/read timeout, số redirect, response size và thời gian tải.
8. Không chuyển tiếp Authorization/cookie của người dùng sang host đích.

Chỉ kiểm tra URL ban đầu là chưa đủ. DNS có thể trả địa chỉ khác ở lần phân giải tiếp theo; redirect có thể chuyển từ host công khai sang địa chỉ nội bộ. Network egress policy là lớp bảo vệ bổ sung quan trọng.

Không dùng startsWith hoặc regex đơn giản để kiểm tra host. Không resolve rồi kiểm tra IP nhưng sau đó để HTTP client tự resolve lại tên miền mà không ràng buộc tới địa chỉ đã xác minh.

## 12. Canonicalization của file path

Nếu API nhận tên file hoặc path, không ghép trực tiếp input vào thư mục lưu trữ:

~~~java
Path target = baseDirectory.resolve(userInput);
~~~

Đoạn code trên chỉ an toàn khi có thêm parse, normalize và kiểm tra containment phù hợp. Một mẫu khái niệm:

~~~java
Path root = baseDirectory.toRealPath();
Path candidate = root.resolve(validatedRelativePath).normalize();

if (!candidate.startsWith(root)) {
    throw new AccessDeniedException("Invalid path");
}
~~~

startsWith trên Path có semantics theo component của filesystem, khác với String.startsWith, nhưng ví dụ này vẫn chưa giải quyết mọi symlink/TOCTOU. Nếu attacker có thể tạo hoặc thay symlink giữa kiểm tra và mở file, đường dẫn có thể thoát root sau khi kiểm tra. Dùng API mở file an toàn theo handle/SecureDirectoryStream khi nền tảng hỗ trợ, kiểm soát quyền ghi thư mục và tránh thư mục có thể bị sửa bởi principal không tin cậy.

Tốt hơn nữa, API nhận file ID do server cấp và ánh xạ ID sang object storage key nội bộ sau khi authorization, thay vì nhận đường dẫn filesystem.

## 13. Canonicalization và authorization phải dùng cùng một resource

Đây là điểm quan trọng nhất khi thiết kế policy. Mọi thành phần phải đồng thuận về tài nguyên đang được kiểm tra:

| Thành phần | Điều phải thống nhất |
|---|---|
| CDN/reverse proxy | Host, path, query và request framing được parse thế nào |
| WAF/API gateway | Route và tham số nào được kiểm tra |
| Router/framework | Canonical path và parameter nào thực sự được dispatch |
| Authentication layer | Token/credential được parse theo đúng giao thức |
| Authorization service | Object/tenant/property được đánh giá theo canonical identifier |
| Cache | Key đại diện đúng resource và đúng policy scope |
| Repository/database | Query dùng đúng object ID, tenant và filter đã được kiểm tra |
| Filesystem/HTTP client | Đích thực tế trùng với đích đã được validate và authorize |

Không kiểm tra quyền trên /documents/a%2Fb rồi để repository hoặc file service tự decode thành a/b. Không authorize URL theo host A rồi để redirect/HTTP client kết nối host B. Không dùng cache key từ raw query nếu application diễn giải query theo quy tắc khác.

Tạo typed value object như CanonicalPath, ValidatedHost, TenantId, NormalizedUsername hoặc ResolvedDestination giúp phân biệt dữ liệu đã parse/kiểm tra với chuỗi raw. Constructor nên giới hạn quyền tạo object để code không thể tự đánh dấu input chưa kiểm tra thành canonical.

## 14. Chữ ký request và canonicalization

Một số API ký request hoặc webhook bằng HMAC/chữ ký số. Chữ ký chỉ xác thực được dữ liệu nếu client và server tạo cùng canonical representation.

Các thành phần thường được ký:

- HTTP method.
- Canonical path và query.
- Một số header được chọn.
- Hash của request body.
- Timestamp, nonce hoặc request ID.

Ví dụ khái niệm:

~~~text
canonicalRequest =
    METHOD + "\n" +
    CANONICAL_PATH + "\n" +
    CANONICAL_QUERY + "\n" +
    CANONICAL_HEADERS + "\n" +
    BODY_HASH
~~~

Không tự sáng tạo quy tắc canonicalization nếu đã có protocol/SDK chính thức. Phải tuân thủ chính xác thứ tự header, cách trim whitespace, percent-encoding, query sorting, cách biểu diễn body và thuật toán hash theo đặc tả. Nếu client ký raw bytes nhưng server ký lại JSON đã parse, hai bên có thể tính chữ ký khác nhau hoặc tạo lỗ hổng kiểm tra.

Quy trình:

1. Giới hạn request và parse theo đúng protocol.
2. Tạo canonical representation đúng đặc tả chữ ký.
3. Xác minh signature constant-time khi so sánh MAC.
4. Kiểm tra timestamp, nonce và replay window.
5. Chỉ sau khi xác minh mới tin các claim về nguồn gửi.
6. Tiếp tục validation nghiệp vụ và authorization; chữ ký hợp lệ không có nghĩa sender được phép truy cập mọi resource.

Canonicalization cho chữ ký và canonicalization cho routing có thể có mục tiêu khác nhau. Phải xác định rõ từng loại và không dùng kết quả của loại này thay cho loại kia nếu đặc tả không cho phép.

## 15. Canonicalization, cache key và idempotency

Nếu cache, rate limiter hoặc idempotency store dùng representation khác với application, cùng một request nghiệp vụ có thể tạo nhiều key hoặc nhiều request khác nhau bị gộp sai.

Ví dụ:

~~~text
/api/orders?status=OPEN&page=1
/api/orders?page=1&status=OPEN
~~~

Nếu thứ tự query không ảnh hưởng ngữ nghĩa, hai request có thể dùng cùng canonical query key. Nhưng nếu duplicate parameter được phép hoặc thứ tự có ý nghĩa, không được sort/xóa duplicate một cách tùy tiện.

Với idempotency:

- Xác định request fingerprint từ principal/tenant, operation, canonical parameters và body hash theo contract.
- Không đưa token thô vào idempotency key.
- Phân vùng key theo tenant hoặc principal phù hợp để tránh va chạm giữa khách hàng.
- Từ chối reuse cùng key với payload khác nếu contract yêu cầu.
- Giữ cùng canonicalization version trong suốt thời gian key còn hiệu lực.

Với cache:

- Canonicalize trước khi tạo key.
- Key phải phản ánh tenant, principal/policy scope và các biến thể response thực sự ảnh hưởng nội dung.
- Không cache response nhạy cảm trong shared cache chỉ vì URL giống nhau.
- Không dùng cache hit để bỏ qua authorization nếu dữ liệu phụ thuộc quyền hiện tại.

## 16. Ví dụ pipeline trong Java/Spring

Ví dụ dưới đây mô tả cấu trúc, không phải thư viện canonicalization dùng chung cho mọi endpoint:

~~~java
public record CanonicalDocumentPath(String value) {
    public static CanonicalDocumentPath parse(String raw) {
        ParsedPath parsed = strictPathParser.parse(raw);

        if (parsed.hasMalformedEncoding()
                || parsed.hasUnsupportedSeparator()
                || parsed.hasAmbiguousDotSegment()) {
            throw new BadRequestException("Invalid document path");
        }

        String canonical = parsed.canonicalValue();
        if (!canonical.startsWith("/documents/")) {
            throw new BadRequestException("Invalid document path");
        }

        return new CanonicalDocumentPath(canonical);
    }
}
~~~

Controller/service dùng canonical value:

~~~java
public DocumentResponse getDocument(
    Principal principal,
    String rawPath
) {
    CanonicalDocumentPath path =
        CanonicalDocumentPath.parse(rawPath);

    Document document = repository
        .findByTenantAndCanonicalPath(principal.tenantId(), path)
        .orElseThrow(NotFoundException::new);

    policy.requireCanRead(principal, document);
    return responseMapper.toAllowedView(principal, document);
}
~~~

Các điểm cần lưu ý:

- strictPathParser là parser được lựa chọn và cấu hình cụ thể; không tự viết parser bằng chuỗi replace.
- Tenant lấy từ principal/context đã xác minh, không từ raw path hoặc body.
- Repository nhận typed canonical path và tenant scope.
- Authorization kiểm tra object đã tải trong đúng tenant.
- Response mapper chỉ trả property được phép.
- Không truyền rawPath xuống một service khác để service đó decode lại.

Nếu route framework đã giải mã path trước khi controller chạy, cần hiểu rõ framework cung cấp raw URI hay decoded path. Đặt canonicalization tại một boundary có đủ thông tin và kiểm thử qua đúng proxy/router đang chạy.

## 17. Kiểm thử canonicalization và parser differential

Kiểm thử cần bao phủ cả giá trị hợp lệ, biểu diễn tương đương và đầu vào mơ hồ:

| Nhóm | Ví dụ đầu vào | Điều cần xác minh |
|---|---|---|
| Percent encoding | %2F, %2e, %252e | Không decode khác số lần giữa các lớp |
| Dot segment | a/../admin, ./file | Policy và router dùng cùng path |
| Backslash | ..\secret, %5c | Không vượt root hoặc đổi route |
| Unicode | NFC/NFD, full-width, mixed-script | Identifier so sánh nhất quán; nội dung tự do được bảo toàn |
| Hostname | Chữ hoa, trailing dot, IDN/Punycode | Allowlist so sánh đúng domain boundary |
| Query duplicate | role=user&role=admin | Duplicate scalar bị từ chối hoặc xử lý đúng contract |
| Query encoding | %26, %3D, dấu + | Parser không tách tham số khác nhau giữa gateway và app |
| JSON duplicate | Hai key role | Parser strict từ chối |
| JSON number | 1, 1.0, 1e0, -0 | Schema và business logic dùng cùng kiểu/precision |
| Header | Header lặp, whitespace, framing mâu thuẫn | Proxy và backend từ chối/diễn giải nhất quán |
| IP | IPv4-mapped IPv6, private IPv6, dạng legacy | Allowlist dựa trên địa chỉ đã parse |
| URL fetch | Redirect, DNS thay đổi, IP private | Không kết nối đích ngoài policy |
| File path | Symlink, UNC, drive path, traversal | File mở thực tế vẫn trong root cho phép |
| Signature | Header/query/body encoding thay đổi | Client/server canonicalize đúng đặc tả |

### 17.1 Kiểm thử end-to-end qua toàn bộ hop

Gọi qua CDN, WAF, gateway, reverse proxy và application như production. Ghi nhận canonical route hoặc request ID ở từng hop để xác minh cùng một request được hiểu thống nhất. Không chỉ gọi trực tiếp controller hoặc mock parser.

Kiểm thử hai hướng: request bị từ chối phải không tạo side effect; request hợp lệ phải thao tác đúng object đã được authorize. Kiểm tra cả cache, audit, file storage và outbound connection khi endpoint có các dependency này.

### 17.2 Property-based và fuzz testing

Có thể sinh các biến thể percent-encoding, Unicode normalization, duplicate query, header order, path separator và JSON member để tìm parser differential. Với mỗi canonical input, kiểm tra các biểu diễn tương đương được xử lý theo một quy tắc; biểu diễn mơ hồ hoặc không hợp lệ phải bị từ chối nhất quán.

Không dùng fuzzing trong production theo cách tạo tải hoặc truy cập tài nguyên thật. Chạy trong môi trường kiểm thử với dữ liệu giả và giới hạn tài nguyên.

## 18. Logging và quan sát

Để điều tra parser differential, cần quan sát được request đã được phân tích ra sao mà không lưu bí mật:

- Request ID/correlation ID xuyên qua các hop.
- Route/template sau canonicalization, không nhất thiết lưu raw path đầy đủ.
- Loại parser/canonicalization version hoặc policy version.
- Kết quả validation: malformed encoding, duplicate parameter, invalid host hoặc path ambiguity.
- Host/scheme đã xác minh và peer proxy đáng tin.
- Cache status, route thực tế và upstream được chọn.
- Policy decision: principal, tenant, action, resource ID ở dạng được kiểm soát và kết quả allow/deny.

Không log Authorization, cookie, signed URL đầy đủ, query token hoặc body nhạy cảm. Nếu cần đối chiếu raw/canonical representation, dùng fingerprint có khóa hoặc dữ liệu đã redact; giới hạn quyền và thời gian lưu log.

Theo dõi các dấu hiệu:

- Một request bị edge cho qua nhưng backend từ chối vì path/host khác.
- Tỷ lệ malformed encoding hoặc duplicate parameter tăng.
- Cache key và route canonical không khớp.
- Host không thuộc allowlist hoặc nhiều redirect tới mạng nội bộ.
- Một principal liên tục thử các biến thể encoding quanh resource ID.
- Chữ ký request thất bại sau thay đổi proxy/parser.

## 19. Các lỗi thiết kế thường gặp

1. **Authorize trước canonicalization:** policy kiểm tra chuỗi khác với tài nguyên thực tế.
2. **Decode nhiều lần:** %252e có thể trở thành dấu chấm sau nhiều lớp.
3. **Dùng regex thay URI parser:** bỏ sót IPv6, userinfo, encoding hoặc ranh giới segment.
4. **Chỉ kiểm tra string prefix:** /publicity có thể bị nhầm là con của /public.
5. **Không xử lý duplicate parameter/key:** gateway và backend chọn giá trị khác nhau.
6. **Normalize mọi chuỗi giống nhau:** làm thay đổi password, token, chữ ký hoặc nội dung tự do.
7. **Dựa vào Host header chưa xác minh:** tạo redirect hoặc URL tới domain của attacker.
8. **Kiểm tra DNS rồi để client resolve lại:** mở cửa DNS rebinding/SSRF.
9. **Lọc IP bằng string prefix:** bỏ sót IPv6 hoặc dạng địa chỉ tương đương.
10. **Chỉ normalize path nhưng không xử lý symlink:** file thực tế vẫn có thể thoát root.
11. **WAF và backend khác parser:** tạo request smuggling hoặc route bypass.
12. **Canonicalize lại ở tầng sau:** giá trị được kiểm tra và giá trị được sử dụng không còn giống nhau.
13. **Chỉ test unit parser:** bỏ qua proxy, cache, router và dependency thực tế.

## 20. Quy trình rà soát canonicalization cho endpoint

Với mỗi endpoint:

1. Liệt kê các input ảnh hưởng tới định danh tài nguyên, routing, cache, filesystem, outbound network và policy.
2. Xác định parser và canonicalization rule cho từng loại dữ liệu; ghi rõ thành phần chịu trách nhiệm.
3. Giới hạn raw bytes, header, body, nesting và số phần tử trước khi parse.
4. Từ chối encoding sai, duplicate scalar hoặc biểu diễn mơ hồ không được contract hỗ trợ.
5. Tạo typed canonical value; không chuyển raw string qua nhiều lớp để tự diễn giải lại.
6. Validate schema, syntax, semantic constraints và business limits trên giá trị canonical.
7. Xác minh principal/tenant rồi authorize đúng resource, property và action.
8. Dùng cùng canonical value cho routing, repository, cache key, signature và thao tác thực tế theo đúng semantics từng protocol.
9. Kiểm tra downstream không decode, normalize hoặc resolve lại theo cách khác.
10. Viết test qua toàn bộ proxy/router/service/dependency; bổ sung fuzz/property-based test.
11. Log policy/parser outcome an toàn và theo dõi parser differential.
12. Khi đổi framework, proxy hoặc thư viện parser, chạy lại bộ test tương thích trước khi rollout.

## 21. Checklist rà soát

- [ ] Đã phân biệt parsing, canonicalization, validation, authorization và business rule.
- [ ] Có giới hạn raw request trước khi parser cấp phát tài nguyên lớn.
- [ ] Mỗi loại input có quy tắc canonicalization riêng và được tài liệu hóa.
- [ ] URI/path chỉ được parse và decode theo một quy tắc thống nhất; không double decode.
- [ ] Dot segment, encoded separator, backslash và path traversal được xử lý nhất quán.
- [ ] Unicode identifier có normalization/case policy rõ; password/token/nội dung tự do không bị normalize tùy tiện.
- [ ] Hostname được xử lý IDNA và so sánh allowlist theo label boundary.
- [ ] Query parameter scalar và JSON duplicate key có chính sách rõ, ưu tiên từ chối mơ hồ.
- [ ] Header/framing được proxy và backend parse nhất quán.
- [ ] IP được parse thành kiểu địa chỉ trước khi áp dụng CIDR/SSRF policy.
- [ ] URL fetch kiểm tra scheme, host, DNS/IP, redirect và egress.
- [ ] File path được resolve dưới root, xét symlink và TOCTOU.
- [ ] Authorization, cache, routing và thao tác dữ liệu dùng cùng canonical resource.
- [ ] Chữ ký request tuân thủ đúng canonicalization của protocol.
- [ ] Có test end-to-end, negative test và fuzz/property-based test.
- [ ] Log không chứa token, cookie, signed URL hoặc payload nhạy cảm.

Canonicalization trước khi kiểm tra policy giúp mọi lớp của API thống nhất về tài nguyên và giá trị đang được xử lý. Khi parser strict, quy tắc chuẩn hóa theo đúng ngữ nghĩa, validation và authorization cùng sử dụng một canonical representation, các khác biệt giữa proxy, gateway, framework, cache và dependency khó bị khai thác thành đường vòng bảo mật.
