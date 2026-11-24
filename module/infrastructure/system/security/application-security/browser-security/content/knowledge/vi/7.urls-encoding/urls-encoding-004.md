# Unicode hostname — tên miền quốc tế hóa và ranh giới bảo mật

> **Chương:** URL và encoding  
> **Mục tiêu:** Hiểu hostname Unicode (IDN), phân biệt U-label và A-label, vai trò của IDNA và Punycode, cách trình duyệt chuẩn hóa hostname khi phân tích URL, và các rủi ro giả mạo tên miền bằng ký tự nhìn giống nhau. Áp dụng nguyên tắc này khi so sánh origin, xử lý redirect, cookie, TLS và danh sách hostname được phép.

## 1. Vì sao hostname có thể chứa Unicode?

Tên miền truyền thống thường được viết bằng chữ Latin không dấu, chữ số và dấu gạch nối ASCII, ví dụ `shop.example.com`. Nhưng Internet phục vụ người dùng nhiều ngôn ngữ, nên người dùng có nhu cầu nhập và nhìn thấy tên miền bằng ký tự bản địa:

- `https://bücher.example` — có chữ `ü`.
- `https://例え.example` — có ký tự tiếng Nhật.
- `https://пример.example` — có ký tự Cyrillic.

Những tên miền quốc tế hóa này được gọi là **Internationalized Domain Names (IDN)**. Trình duyệt phải chuyển đổi và kiểm tra hostname để có thể dùng với hệ thống DNS vốn vận chuyển tên miền theo dạng ASCII.

Việc hỗ trợ Unicode giúp người dùng dễ nhớ và truy cập tên miền bằng ngôn ngữ của họ. Tuy nhiên, nhiều ký tự từ các hệ chữ khác nhau trông gần như giống hệt nhau. Kẻ tấn công có thể lợi dụng điểm đó để tạo website giả mạo thương hiệu, đánh lừa người dùng nhập mật khẩu hoặc thanh toán.

Do vậy, Unicode hostname vừa là vấn đề **encoding và chuẩn hóa URL**, vừa là vấn đề **nhận diện danh tính và chống giả mạo**.

## 2. IDN, U-label và A-label

Một hostname IDN có thể được biểu diễn theo hai dạng:

- **U-label:** dạng Unicode mà người dùng có thể đọc, ví dụ `bücher`.
- **A-label:** dạng ASCII-Compatible Encoding (ACE) tương ứng, ví dụ `xn--bcher-kva`.

Với tên miền ví dụ:

| Dạng | Hostname |
| --- | --- |
| Unicode / U-label | `bücher.example` |
| ASCII / A-label | `xn--bcher-kva.example` |

Phần `xn--` là tiền tố nhận diện A-label theo IDNA. Phần còn lại là kết quả mã hóa nhãn Unicode bằng Punycode theo quy tắc IDNA.

**DNS không cần truyền nhãn Unicode thô.** Khi xử lý một IDN hợp lệ, ứng dụng chuyển từng nhãn Unicode sang A-label ASCII để sử dụng trong những giao thức và thao tác tên miền tương ứng. Người dùng có thể nhập U-label; trình duyệt có thể hiển thị Unicode hoặc dạng punycode tùy chính sách an toàn của nó.

U-label và A-label là hai cách biểu diễn của cùng một nhãn tên miền hợp lệ. Chúng không phải hai website riêng biệt chỉ vì chuỗi ký tự khác nhau.

## 3. Punycode là gì — và không phải là gì?

**Punycode** là một thuật toán mã hóa dùng để biểu diễn chuỗi Unicode thành chuỗi ASCII. IDNA sử dụng Punycode để tạo A-label cho các nhãn tên miền quốc tế hóa.

Ví dụ:

```text
U-label: bücher
A-label: xn--bcher-kva
```

Punycode giúp nhãn IDN đi qua hạ tầng chỉ hỗ trợ ASCII. Nó **không phải mã hóa bí mật**, không có khóa và không che giấu nội dung. Bất kỳ ai cũng có thể giải mã A-label thành dạng Unicode tương ứng bằng thư viện thích hợp.

Punycode cũng **không phải bộ lọc chống phishing**. Nó chỉ chuyển biểu diễn; một hostname có ký tự đánh lừa thị giác vẫn có thể được mã hóa thành A-label hợp lệ. Việc nhãn có hợp lệ theo IDNA và việc website có đáng tin hay không là hai câu hỏi hoàn toàn khác nhau.

Ví dụ JavaScript với thư viện chuẩn:

```js
const input = "bücher";
const encoded = new URL("https://" + input + ".example").hostname;

console.log(encoded); // xn--bcher-kva.example
```

Ở ví dụ này, `URL` API thực hiện phân tích hostname và chuyển đổi theo thuật toán URL của nền tảng. Không nên tự tách chuỗi rồi gọi một hàm Punycode thô để thay thế toàn bộ quy tắc kiểm tra IDNA.

## 4. IDNA, IDNA2008 và UTS #46

**IDNA (Internationalized Domain Names in Applications)** định nghĩa cách ứng dụng xử lý nhãn tên miền Unicode để sử dụng trong hệ thống DNS và các giao thức Internet.

Hai tên gọi cần phân biệt:

| Chuẩn / tài liệu | Vai trò |
| --- | --- |
| **IDNA2008** | Định nghĩa tập quy tắc về ký tự hợp lệ, xử lý ngữ cảnh và quy tắc bidi cho tên miền quốc tế hóa |
| **Unicode UTS #46** | Đưa ra cơ chế xử lý tương thích Unicode để các ứng dụng có thể chuẩn hóa/map đầu vào người dùng trước khi áp dụng quy tắc IDNA |
| **WHATWG URL Standard** | Định nghĩa cách trình duyệt phân tích URL và chuyển hostname sang ASCII, dựa trên quy trình domain-to-ASCII và xử lý IDNA tương ứng |

IDNA2008 không đơn giản biến mọi ký tự Unicode thành chữ Latin. Nó có các điều kiện về code point hợp lệ, quy tắc ngữ cảnh (*ContextJ/ContextO*) và quy tắc chữ viết hai chiều (*bidirectional rules*). Một nhãn Unicode bất kỳ không đương nhiên trở thành hostname hợp lệ.

UTS #46 cung cấp các bước mapping để hỗ trợ đầu vào người dùng và tương thích với những cách viết Unicode khác nhau. Ví dụ, một số ký tự hoa/thường, ký tự tương đương hoặc dấu chấm Unicode có thể được chuẩn hóa theo quy tắc. Chế độ transitional và nontransitional có thể cho kết quả khác nhau đối với một số ký tự đặc biệt.

Trình duyệt hiện đại thường tuân theo thuật toán phân tích URL của nền tảng web, trong đó có bước chuyển hostname sang ASCII theo quy trình tương thích IDNA. Thư viện server, runtime và công cụ DNS có thể dùng phiên bản hoặc chế độ khác nhau.

**Nguyên tắc triển khai:** đừng tự viết bộ IDNA bằng regex, lower-case hoặc Punycode đơn lẻ. Dùng parser URL và thư viện IDNA/PSL được duy trì, thống nhất chính sách giữa frontend, backend, reverse proxy và hệ thống kiểm soát quyền.

## 5. Chuẩn hóa Unicode và dấu phân cách hostname

Unicode cho phép một số ký tự có thể được biểu diễn theo nhiều chuỗi code point. Ví dụ chữ có dấu đôi khi được biểu diễn bằng:

- Một code point đã kết hợp sẵn (*precomposed*).
- Chữ cái cơ sở cộng với dấu kết hợp (*combining mark*).

Vì vậy, xử lý hostname cần có bước chuẩn hóa Unicode theo quy tắc IDNA, thường liên quan đến **Normalization Form C (NFC)**. Không nên tự đoán rằng hai chuỗi nhìn giống nhau sẽ luôn được chấp nhận hoặc luôn chuyển thành cùng A-label.

Một số dấu chấm Unicode cũng có thể được xử lý như dấu phân cách nhãn trong quy trình mapping, chẳng hạn:

| Ký tự | Code point | Vai trò thường gặp trong mapping |
| --- | --- | --- |
| `.` | U+002E | Dấu chấm ASCII |
| `。` | U+3002 | Ideographic full stop |
| `．` | U+FF0E | Fullwidth full stop |
| `｡` | U+FF61 | Halfwidth ideographic full stop |

Khi được xử lý theo quy tắc tương thích tương ứng, các dấu phân cách này có thể được quy về dấu chấm ASCII. Đây là một trong những lý do không nên so sánh hostname bằng chuỗi Unicode người dùng nhập.

Ngoài ra, IDNA có các quy tắc hạn chế ký tự điều khiển, ký tự không hợp lệ, ký tự kết hợp ở vị trí không phù hợp và những trường hợp chữ viết hai chiều. **Chuẩn hóa không có nghĩa là xóa mọi khác biệt Unicode**, cũng không loại bỏ các ký tự giống nhau về hình thức.

## 6. Trình duyệt chuẩn hóa hostname khi phân tích URL

Khi trình duyệt xử lý một URL, nó không chỉ lấy phần text sau `https://`. Nó phân tích cú pháp URL, xác định scheme, authority, hostname, port, path và những thành phần khác.

Ví dụ:

```js
const url = new URL("https://bücher.example/account");

console.log(url.hostname);
// "xn--bcher-kva.example"

console.log(url.origin);
// "https://xn--bcher-kva.example"
```

Với cùng hostname được viết dưới dạng A-label:

```js
const unicodeURL = new URL("https://bücher.example/profile");
const asciiURL = new URL("https://xn--bcher-kva.example/settings");

console.log(unicodeURL.hostname === asciiURL.hostname); // true
console.log(unicodeURL.origin === asciiURL.origin);     // true
```

Đường dẫn khác nhau không làm thay đổi origin. Origin thông thường vẫn gồm **scheme + hostname đã chuẩn hóa + port**. Port mặc định được chuẩn hóa theo scheme; hostname không phân biệt chữ hoa/thường và IDN được đưa về biểu diễn ASCII tương ứng.

Điều này quan trọng khi:

- So sánh origin trong allowlist.
- Kiểm tra đích redirect.
- Kiểm tra nguồn gửi thông điệp qua `postMessage`.
- Thiết lập cookie và xác định host nhận cookie.
- Đối chiếu hostname trong TLS và HTTP.

**Lưu ý:** `new URL()` kiểm tra cú pháp và chuẩn hóa URL; nó không xác định hostname có phải thương hiệu thật hay có ý định lừa đảo. Một URL IDN hợp lệ về mặt cú pháp vẫn có thể là phishing.

## 7. Homograph attack: tên miền nhìn giống nhưng khác ký tự

**Homograph attack** là cách giả mạo dựa trên những ký tự có hình dáng giống hoặc gần giống nhau. Ví dụ, chữ Latin `a` và chữ Cyrillic `а` là hai code point khác nhau dù có thể trông gần như giống hệt trong một font.

Một hostname giả mạo có thể thay một hoặc nhiều ký tự trong tên thương hiệu bằng ký tự của hệ chữ khác. Người dùng nhìn thanh địa chỉ và tưởng rằng họ đang truy cập website quen thuộc.

Các dạng rủi ro phổ biến:

1. **Mixed-script:** trộn ký tự từ nhiều hệ chữ trong cùng nhãn, chẳng hạn Latin và Cyrillic.
2. **Whole-script confusable:** dùng gần như toàn bộ một hệ chữ khác nhưng tạo hình thức tương tự tên miền thật.
3. **Combining mark abuse:** dùng dấu kết hợp hoặc dấu phụ để làm thay đổi hình thức hiển thị.
4. **Punctuation confusion:** tận dụng dấu chấm hoặc ký tự phân cách nhìn tương tự trong một số ngữ cảnh.
5. **Bidi confusion:** lợi dụng cách hiển thị chữ từ phải sang trái để làm người dùng hiểu nhầm thứ tự ký tự hoặc phần mở rộng.

Unicode có dữ liệu về ký tự dễ nhầm lẫn (*confusables*) và hướng dẫn bảo mật như **Unicode Technical Standard #39 (UTS #39)**. Tuy nhiên, việc phát hiện confusable không thể chỉ dựa vào so sánh hai chuỗi code point: font, ngôn ngữ, locale và ngữ cảnh người dùng đều có ảnh hưởng.

Một số trình duyệt chọn hiển thị A-label/punycode thay vì Unicode khi phát hiện hostname có dấu hiệu đáng ngờ. Quy tắc hiển thị khác nhau theo browser, phiên bản và ngữ cảnh. **Không giả định rằng mọi trình duyệt đều hiển thị Unicode hoặc đều cảnh báo mọi homograph.**

## 8. Punycode không thay thế kiểm tra danh tính

Hãy phân biệt bốn câu hỏi:

| Câu hỏi | Cơ chế trả lời |
| --- | --- |
| Hostname Unicode có thể chuyển sang dạng ASCII tương ứng không? | IDNA / Punycode |
| URL có hợp lệ và origin được chuẩn hóa là gì? | URL parser theo chuẩn nền tảng |
| Kết nối có được mã hóa và chứng chỉ khớp hostname không? | TLS và xác minh chứng chỉ |
| Website có thực sự thuộc thương hiệu mà người dùng mong đợi không? | Danh tính tổ chức, kênh phân phối đáng tin, kiểm tra phishing và ngữ cảnh nghiệp vụ |

TLS xác minh chứng chỉ phù hợp với hostname được truy cập theo chuỗi tin cậy của trình duyệt. Điều đó bảo vệ kết nối tới **hostname đó**, nhưng không chứng minh hostname là website chính thức của thương hiệu. Kẻ tấn công có thể đăng ký một tên miền gần giống và có chứng chỉ TLS hợp lệ cho chính tên miền giả mạo.

Vì vậy, biểu tượng HTTPS/ổ khóa không đủ để kết luận website an toàn. Người dùng và ứng dụng cần kiểm tra hostname chính xác, nguồn liên kết, danh tính nhà cung cấp và các tín hiệu chống phishing khác.

## 9. URL parser và so sánh origin an toàn

Không kiểm tra hostname bằng cách tìm một chuỗi con trong URL:

```js
// Không an toàn: có thể chấp nhận host giả mạo hoặc URL chứa chuỗi đó ở path.
if (input.includes("example.com")) {
  allowNavigation(input);
}
```

Một URL có thể chứa username/password, hostname khác, port khác hoặc path chứa chữ `example.com`. Hãy phân tích URL trước, sau đó so sánh **origin chính xác**:

```js
const allowedOrigins = new Set([
  "https://app.example.com",
  "https://xn--bcher-kva.example",
]);

function validateDestination(input) {
  const url = new URL(input);

  if (url.protocol !== "https:") {
    throw new Error("Chỉ cho phép HTTPS");
  }

  if (url.username || url.password) {
    throw new Error("Không cho phép userinfo trong URL");
  }

  if (!allowedOrigins.has(url.origin)) {
    throw new Error("Origin không nằm trong allowlist");
  }

  return url;
}
```

Ví dụ này minh họa allowlist cố định. Trong hệ thống thực, cần xác định URL tương đối được phép hay không, kiểm tra port, xử lý redirect sau khi theo dõi đích cuối cùng, và áp dụng cùng chính sách ở server. Không tự động cho phép mọi subdomain chỉ vì chúng có cùng registrable domain.

Nếu nghiệp vụ cho phép một tập hợp subdomain, hãy phân tích hostname đã chuẩn hóa và kiểm tra ranh giới nhãn chính xác. Tuy nhiên, **allowlist origin cụ thể** thường dễ kiểm toán hơn. Một subdomain có thể được cấp cho tenant khác, trỏ tới hạ tầng bị chiếm hoặc phục vụ nội dung do người dùng kiểm soát.

## 10. IDN và các lớp bảo mật của ứng dụng web

Unicode hostname ảnh hưởng đến nhiều cơ chế khác nhau:

| Thành phần | Ảnh hưởng của IDN | Hướng xử lý |
| --- | --- | --- |
| **Origin / SOP** | U-label được chuẩn hóa thành hostname ASCII khi phân tích URL; hai cách viết tương đương có thể cùng origin | Dùng URL parser và so sánh origin chuẩn hóa |
| **CORS** | Header `Origin` mang origin đã được trình duyệt tuần tự hóa; server phải đối chiếu chính xác | Chuẩn hóa allowlist bằng thư viện phù hợp, không phản chiếu tùy tiện |
| **Cookie** | Host/domain cookie có thể chứa IDN và được xử lý theo quy tắc domain matching | Dùng cookie host-only khi phù hợp; tránh Domain quá rộng; tôn trọng public suffix |
| **TLS** | Hostname IDN cần được biểu diễn phù hợp khi tra cứu và xác minh chứng chỉ | Dùng TLS stack chuẩn, không tự giải mã/so chuỗi tên hiển thị |
| **Redirect** | URL Unicode có thể chuẩn hóa thành host ASCII khác với cách người dùng tưởng tượng | Parse URL, kiểm tra scheme và origin đích, xem cả redirect chain |
| **CSP / frame policy** | Nguồn host trong policy phải khớp hostname theo cú pháp URL/CSP | Dùng nguồn cụ thể, kiểm tra response header thực tế |
| **Phishing** | Ký tự đồng dạng có thể giả mạo thương hiệu trong link và giao diện | Hiển thị/đối chiếu hostname rõ ràng, kiểm tra ngữ cảnh và cảnh báo |

### Header Origin và Host

Khi một trình duyệt gửi request, header `Origin` (trong những request có áp dụng) biểu diễn origin của bên khởi tạo theo dạng chuẩn hóa. HTTP/1.1 sử dụng `Host` để chỉ authority đích; HTTP/2 và HTTP/3 dùng `:authority` trong pseudo-header.

Reverse proxy và ứng dụng backend phải thống nhất cách parse, chuẩn hóa và kiểm tra hostname. Tránh tình huống một tầng kiểm tra U-label trong khi tầng khác kiểm tra A-label hoặc xử lý Unicode khác nhau, dẫn đến hai tầng hiểu request là hai host khác nhau.

Không tin header `Host` hoặc `X-Forwarded-Host` chỉ vì request có vẻ đến từ browser. Proxy chỉ nên chấp nhận forwarded header từ proxy tin cậy và server phải kiểm tra hostname đích trong danh sách được phép.

## 11. Xử lý Unicode hostname trong hệ thống backend

Một ứng dụng nhận URL từ người dùng, cấu hình tenant hoặc callback OAuth cần có chính sách nhất quán:

1. **Parse URL bằng thư viện chuẩn.** Không dùng regex tự tách scheme/host/port và không tự percent-decode hostname.
2. **Chuẩn hóa IDN theo một chế độ đã chọn.** Dùng thư viện IDNA/UTS #46 được duy trì, biết rõ cách xử lý transitional/nontransitional và lỗi đầu vào.
3. **So sánh hostname canonical.** Khi quyết định quyền, so sánh origin đã chuẩn hóa với allowlist; không so sánh chuỗi Unicode hiển thị.
4. **Từ chối đầu vào mơ hồ hoặc không hợp lệ.** Không âm thầm sửa một hostname lỗi rồi dùng nó làm danh tính bảo mật nếu chính sách nghiệp vụ chưa quy định.
5. **Đồng bộ các tầng.** Frontend, backend, proxy, cache, hệ thống log và bộ lọc SSRF cần hiểu hostname nhất quán.
6. **Giữ nguyên bằng chứng phục vụ điều tra.** Có thể lưu URL đầu vào theo cách an toàn để kiểm toán, đồng thời ghi host canonical đã parse; tránh log dữ liệu nhạy cảm trong query hoặc userinfo.

### Kiểm tra redirect và SSRF

Unicode hostname còn xuất hiện trong URL redirect hoặc URL do người dùng cung cấp cho server tải tài nguyên. Nếu backend chỉ kiểm tra chuỗi ban đầu, một biến thể IDN hoặc redirect tiếp theo có thể đưa request đến host ngoài dự kiến.

Với chức năng fetch URL phía server, ngoài IDNA cần kiểm tra:

- Scheme được phép, thường chỉ HTTPS nếu phù hợp nghiệp vụ.
- Origin/hostname đích sau canonicalization và **sau mỗi redirect**.
- Kết quả DNS và địa chỉ IP thực tế, bao gồm loopback, private, link-local và các dải nhạy cảm.
- Thay đổi DNS/rebinding giữa lúc kiểm tra và lúc kết nối.
- Cổng, proxy, credential trong URL và chính sách egress.

IDNA giải quyết cách biểu diễn hostname; nó không phải cơ chế chống SSRF và không xác minh IP đích an toàn.

## 12. Thực hành: quan sát Unicode và A-label trong DevTools

Thí nghiệm dùng tên miền dành cho tài liệu `.example`. Parser URL có thể phân tích hostname dù tên miền không được đăng ký hay không phân giải DNS; vì vậy có thể kiểm tra chuẩn hóa mà không cần truy cập một website bên ngoài.

### Bước 1 — Mở Console

Chạy:

```js
const samples = [
  "https://bücher.example/path",
  "https://xn--bcher-kva.example/another-path",
];

const parsed = samples.map((value) => {
  const url = new URL(value);
  return {
    input: value,
    hostname: url.hostname,
    origin: url.origin,
    pathname: url.pathname,
  };
});

console.table(parsed);
```

**Kỳ vọng:** hai URL có hostname canonical và origin giống nhau, dù path và cách biểu diễn đầu vào khác nhau.

### Bước 2 — So sánh origin

```js
const [unicode, ascii] = [
  new URL("https://bücher.example/one"),
  new URL("https://xn--bcher-kva.example/two"),
];

console.log(unicode.hostname === ascii.hostname);
console.log(unicode.origin === ascii.origin);
```

Cả hai phép so sánh dự kiến trả về `true`. Thử thay scheme thành `http` hoặc port thành `8443` để thấy origin thay đổi. Thay path không làm thay đổi origin.

### Bước 3 — Quan sát đầu vào không hợp lệ và ký tự phân cách

```js
const inputs = [
  "https://example.com/",
  "https://example。com/",
  "https://example．com/",
];

for (const input of inputs) {
  try {
    const url = new URL(input);
    console.log(input, "=>", url.hostname);
  } catch (error) {
    console.log(input, "=> rejected:", error.name);
  }
}
```

Những dấu phân cách Unicode có thể được mapping thành dấu chấm ASCII theo quy tắc URL/IDNA của trình duyệt. Đối chiếu kết quả trên các browser mục tiêu, vì phiên bản parser và chính sách hiển thị có thể khác nhau.

### Bước 4 — Kiểm tra hiển thị homograph

Không cần mở một tên miền lạ để thử. Có thể dùng dữ liệu Unicode và A-label đã biết trong môi trường offline để xem:

- Parser tạo hostname ASCII nào.
- Công cụ hiển thị Unicode có nhận ra nhãn mixed-script hay không.
- Browser nào hiển thị A-label và browser nào hiển thị Unicode.
- Cảnh báo có khác nhau theo locale hoặc phiên bản không.

Không dùng kết quả hiển thị của một trình duyệt làm tiêu chuẩn bảo mật duy nhất. Server vẫn phải canonicalize và xác thực hostname theo chính sách của ứng dụng.

## 13. Tình huống thiết kế: đăng nhập và callback của đối tác

Một ứng dụng cho phép người quản trị cấu hình callback URL để nhận kết quả thanh toán. Hệ thống có frontend tại `https://admin.example.com` và API tại `https://api.example.com`.

Nếu người dùng nhập một URL Unicode trông giống tên miền đối tác, ứng dụng không nên chỉ hiển thị chuỗi Unicode rồi lưu làm đích callback. Quy trình an toàn hơn:

1. Parse URL bằng parser chuẩn, từ chối URL không hợp lệ và scheme không được phép.
2. Lấy `url.origin` đã canonicalize và so sánh với danh sách origin đối tác đã xác minh.
3. Nếu cho phép nhiều hostname IDN, lưu cả origin canonical A-label và nhãn hiển thị đã được kiểm duyệt; không dùng nhãn hiển thị để quyết định quyền.
4. Khi gửi request callback, xác minh lại hostname, DNS/IP và redirect theo yêu cầu nghiệp vụ; áp dụng TLS chuẩn.
5. Hiển thị rõ hostname canonical hoặc một dạng trình bày đã được kiểm tra để người quản trị nhận diện đúng đích.
6. Ghi log origin canonical và kết quả kiểm tra, không ghi token hay bí mật trong URL.

**Không cấp quyền chỉ dựa trên vẻ ngoài của tên miền.** Chứng chỉ TLS hợp lệ cho một IDN chỉ chứng minh kết nối đến hostname đó được xác thực theo PKI; nó không chứng minh đó là đối tác mà doanh nghiệp muốn tích hợp.

## 14. Những nhầm lẫn thường gặp

| Ngộ nhận | Cách hiểu đúng |
| --- | --- |
| “Punycode là mã hóa để che giấu hostname.” | Punycode là encoding công khai, có thể chuyển đổi ngược. |
| “A-label bắt đầu bằng `xn--` nên chắc chắn an toàn.” | Tiền tố chỉ cho biết dạng ACE; IDN vẫn có thể dùng ký tự đánh lừa. |
| “Mọi Unicode hostname đều hợp lệ.” | IDNA áp dụng quy tắc ký tự, ngữ cảnh và bidi; parser có thể từ chối đầu vào. |
| “Chuỗi Unicode nhìn giống nhau thì là cùng hostname.” | Code point khác nhau có thể tạo hostname khác nhau dù glyph gần giống. |
| “Chuẩn hóa Unicode loại bỏ homograph.” | Chuẩn hóa giải quyết biểu diễn tương đương, không giải quyết mọi confusable. |
| “HTTPS/ổ khóa chứng minh website thuộc thương hiệu thật.” | TLS xác minh hostname và kết nối, không chứng thực ý định/thương hiệu mà người dùng mong đợi. |
| “So sánh URL bằng includes() là đủ.” | Cần parse URL và so sánh origin/hostname canonical theo allowlist. |
| “Frontend và backend có thể tự chọn IDNA khác nhau.” | Khác biệt canonicalization có thể tạo lỗi kiểm tra quyền; cần thống nhất và kiểm thử. |
| “Punycode xử lý luôn SSRF.” | SSRF còn cần kiểm tra DNS, IP, redirect, cổng và egress. |

## 15. Câu hỏi tự kiểm tra

1. U-label và A-label khác nhau thế nào? Vì sao `xn--` xuất hiện trong A-label?
2. Punycode giải quyết vấn đề biểu diễn nào và không giải quyết vấn đề bảo mật nào?
3. Vì sao IDNA2008 và UTS #46 không nên được xem là cùng một bước mapping?
4. Vì sao browser URL parser có thể biến `https://bücher.example` thành hostname `xn--bcher-kva.example`?
5. Nếu hai URL Unicode và punycode có cùng origin canonical, path khác nhau có làm origin khác nhau không?
6. Homograph attack khai thác khác biệt nào giữa code point và hình dáng glyph?
7. Chứng chỉ TLS hợp lệ cho IDN có chứng minh website thuộc thương hiệu chính thức không?
8. Vì sao allowlist cần so sánh origin đã parse thay vì tìm chuỗi con trong URL?
9. Backend tải URL do người dùng cung cấp cần thêm những kiểm tra nào ngoài IDNA để chống SSRF?

**Ghi nhớ:** Unicode hostname giúp Internet hỗ trợ tên miền đa ngôn ngữ, nhưng cần một quy trình thống nhất từ **IDNA và Punycode**, qua **URL parsing và canonicalization**, đến **so sánh origin, xác minh TLS và chống giả mạo**. A-label là biểu diễn ASCII của một nhãn IDN hợp lệ; nó không phải dấu hiệu đáng tin. Hãy dùng parser và thư viện chuẩn, so sánh origin canonical, kiểm soát redirect và hiển thị hostname cẩn thận — đồng thời nhớ rằng tính hợp lệ của hostname và danh tính của website là hai việc khác nhau.
