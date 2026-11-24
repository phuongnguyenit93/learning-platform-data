# Origin serialization: biểu diễn origin trong trình duyệt và HTTP

## 1. Origin serialization là gì?

Trong mô hình bảo mật web, **origin** là danh tính dùng để quyết định các tài liệu và script có được truy cập lẫn nhau hay không. Khi trình duyệt cần hiển thị origin ở một thuộc tính JavaScript, truyền origin trong HTTP header hoặc giao tiếp giữa các cửa sổ, nó phải chuyển giá trị origin nội bộ thành một chuỗi. Quá trình này gọi là **origin serialization** (tuần tự hóa origin).

Với origin thông thường từ HTTP(S), chuỗi đó có dạng:

```text
<scheme>://<host>[:<non-default-port>]

https://app.example.com
https://app.example.com:8443
http://localhost:3000
```

Với **opaque origin** (origin không thể biểu diễn bằng bộ scheme/host/port thông thường), kết quả serialization là chuỗi ký tự **`"null"`**.

> **Điểm mấu chốt:** Serialization là cách biểu diễn origin để trao đổi hoặc quan sát. Chuỗi biểu diễn không phải toàn bộ trạng thái bảo mật của một tài liệu. Đặc biệt, `"null"` không nhận diện duy nhất một opaque origin và không có nghĩa là JavaScript `null`.

Bài này thuộc chương **Origin** của module **SECURITY_APPLICATION_SECURITY_BROWSER_SECURITY**. Kiến thức serialization giúp phân tích chính xác ranh giới trình duyệt–origin–cookie–ứng dụng web, từ đó thiết kế CORS, bảo vệ SOP, kiểm tra thông điệp `postMessage` và đánh giá rủi ro CSRF, XSS, clickjacking cùng những cơ chế như CSP, Trusted Types, security headers.

Sau bài học, bạn có thể:

- Giải thích sự khác nhau giữa **tuple origin**, **opaque origin** và chuỗi serialized origin.
- Tự xác định kết quả serialization từ các URL HTTP(S), port mặc định, URL `blob:`, `data:` và một số ngữ cảnh đặc biệt.
- Phân biệt `URL.origin`, origin thực tế của một `Document`, HTTP `Origin` header và `MessageEvent.origin`.
- Viết allowlist origin an toàn cho CORS/`postMessage`, hiểu lý do không nên cấp quyền cho `Origin: null`.
- Thực hành kiểm chứng các trường hợp bằng DevTools và một server cục bộ.

## 2. Origin nội bộ không nhất thiết là một chuỗi

Theo HTML Standard, origin có hai dạng chính:

| Dạng origin | Bản chất | Khi serialize |
|---|---|---|
| **Tuple origin** | Bộ gồm scheme, host, port và một thành phần domain liên quan cơ chế `document.domain` cũ | `scheme://host` và `:port` nếu port không phải `null` trong tuple |
| **Opaque origin** | Danh tính nội bộ đặc biệt, không thể tạo lại bằng cách phân tích một chuỗi URL | Chính xác chuỗi `"null"` |

### 2.1. Tuple origin: scheme + host + port

Đối với URL HTTP(S) thông thường, ba thành phần nhận diện origin là:

- **Scheme:** `http` và `https` là hai giá trị khác nhau.
- **Host:** tên miền hoặc địa chỉ IP đã được URL parser chuẩn hóa; subdomain khác nhau thường có origin khác nhau.
- **Port:** cổng kết nối; khi port đúng giá trị mặc định của scheme, URL parser thường biểu diễn nó là `null` ở trạng thái URL chuẩn hóa.

Ví dụ:

```text
URL:       https://user:pass@SHOP.example.com:443/orders?id=5#top
Origin:    https://shop.example.com

Không bao gồm:
- username/password
- path: /orders
- query: ?id=5
- fragment: #top
- dấu / kết thúc sau hostname
```

Các thành phần bị bỏ qua trong serialized origin không góp phần tạo nên sự khác biệt về origin. Tuy vậy, chúng vẫn có vai trò riêng trong routing, logging, truy cập tài nguyên và bảo mật ứng dụng.

### 2.2. Opaque origin: một danh tính không tái tạo từ chuỗi

Một số tài liệu có **opaque origin**, thường gặp với tài liệu `data:` hoặc iframe được sandbox mà không có `allow-same-origin`. Trình duyệt quản lý danh tính opaque origin ở bên trong. Khi serialize:

```text
Opaque origin A ──serialize──> "null"
Opaque origin B ──serialize──> "null"
```

A và B có thể là **hai opaque origin hoàn toàn khác nhau**, dù chuỗi nhận được đều là `"null"`. So sánh serialized string vì vậy không đủ để kết luận chúng cùng origin. Một opaque origin cũng không tự nhiên "cùng origin" với tuple origin nào.

Cần phân biệt ba giá trị sau:

```js
const serialized = new URL("data:text/plain,hello").origin;

console.log(serialized);            // "null"
console.log(typeof serialized);     // "string"
console.log(serialized === "null"); // true
console.log(serialized === null);   // false
```

`"null"` là **một chuỗi gồm bốn ký tự**, khác hoàn toàn với `null` (giá trị thiếu/vắng mặt trong JavaScript).

## 3. Thuật toán serialization theo HTML Standard

Có thể mô tả thuật toán ở mức khái niệm như sau:

1. Nếu đầu vào là opaque origin, trả về **`"null"`**.
2. Nếu đầu vào là tuple origin, bắt đầu với **scheme**.
3. Nối chuỗi **`"://"`**.
4. Nối **host đã serialize**.
5. Nếu **port không phải `null`** trong tuple, nối dấu **`":"`** và số port.
6. Trả về kết quả.

```mermaid
flowchart TD
    A["Origin nội bộ"] --> B{"Opaque origin?"}
    B -- Có --> N["Chuỗi 'null'"]
    B -- Không --> T["Tuple origin"]
    T --> H["scheme + '://' + serialized host"]
    H --> P{"port khác null?"}
    P -- Có --> C["Thêm ':' + port"]
    P -- Không --> R["Trả về chuỗi"]
    C --> R
```

**Điểm tinh tế:** Quy tắc *bỏ port mặc định* chủ yếu xuất phát từ bước **phân tích/chuẩn hóa URL** trước khi hình thành origin. Bản thân bước serialization ở trên chỉ cần kiểm tra port trong tuple có phải `null` hay không. Thành phần `domain` của tuple origin (liên quan API `document.domain` đã lỗi thời) **không được chèn vào chuỗi serialization**.

### 3.1. Những thành phần thường được chuẩn hóa

Khi dùng `new URL(...)`, nền tảng web phân tích và chuẩn hóa URL trước khi bạn đọc `.origin`:

- Scheme và tên host DNS thường được chuyển thành chữ thường.
- Cổng mặc định được loại khỏi dạng URL chuẩn hóa: `http:80` và `https:443`.
- Tên miền quốc tế có thể được biểu diễn bằng ASCII/Punycode.
- Địa chỉ IPv6 được giữ trong ngoặc vuông khi xuất hiện trong host.
- Path, query, fragment và userinfo không xuất hiện trong serialized origin.

Không nên tự xây chuỗi origin bằng cách ghép `protocol + "//" + hostname` một cách tùy ý, vì dễ bỏ sót port, cách chuẩn hóa host và các scheme đặc biệt.

## 4. Bảng ví dụ: URL và serialized origin

Bảng dưới đây minh họa giá trị của `new URL(input).origin` trong trình duyệt hiện đại đối với các trường hợp thông thường.

| URL đầu vào | `URL.origin` | Giải thích |
|---|---|---|
| `https://shop.example.com/orders?id=1#top` | `https://shop.example.com` | Bỏ path, query, fragment |
| `https://SHOP.example.com:443/a` | `https://shop.example.com` | Chuẩn hóa host; HTTPS dùng port mặc định |
| `http://shop.example.com:80/a` | `http://shop.example.com` | HTTP dùng port mặc định 80 |
| `https://shop.example.com:8443/a` | `https://shop.example.com:8443` | Giữ port không mặc định |
| `http://shop.example.com/a` | `http://shop.example.com` | Scheme khác HTTPS nên khác origin |
| `https://user:pass@shop.example.com/private` | `https://shop.example.com` | Không đưa userinfo vào origin |
| `https://api.example.com` | `https://api.example.com` | Subdomain khác tạo host khác |
| `https://[2001:db8::1]:8443/a` | `https://[2001:db8::1]:8443` | IPv6 giữ ngoặc vuông |
| `data:text/html,Hello` | `null` | Opaque origin, kết quả **string** `"null"` |
| `blob:https://shop.example.com/1234` | `https://shop.example.com` | `blob:` có thể lấy origin từ phần URL bên trong |

**Ngoại lệ cần ghi nhớ:**

- `file:` có quy tắc origin phụ thuộc trình duyệt/triển khai; nhiều trình duyệt dùng opaque origin. Không lấy giá trị quan sát được trên một máy làm đảm bảo chung cho mọi trình duyệt.
- `blob:` không mặc định là opaque: một blob URL được tạo từ tài liệu HTTP(S) thường gắn với origin của môi trường tạo nó. Blob URL từ ngữ cảnh opaque có thể serialize thành `"null"`.
- `about:blank` hoặc `about:srcdoc` đòi hỏi phân biệt **origin của một URL độc lập** với **origin thực sự của tài liệu** được tạo trong ngữ cảnh có parent/creator.

### 4.1. Chạy trực tiếp trong DevTools

Mở trang bất kỳ qua HTTP(S), chọn DevTools → **Console** và chạy:

```js
const cases = [
  "https://SHOP.example.com:443/orders?id=1#top",
  "https://shop.example.com:8443/orders",
  "http://shop.example.com:80/a",
  "https://user:pass@shop.example.com/private",
  "https://api.example.com/a",
  "https://[2001:db8::1]:8443/a",
  "data:text/html,Hello",
  "blob:https://shop.example.com/1234",
  "about:blank",
];

console.table(cases.map((input) => ({
  input,
  serializedOrigin: new URL(input).origin,
})));
```

Quan sát `about:blank` trong bảng: khi bạn tạo riêng đối tượng `URL` từ chuỗi đó, `.origin` thường là `"null"`. Tuy nhiên, một **tài liệu iframe about:blank** được tạo bởi trang cha thông thường có thể **thừa hưởng origin của parent**. Vì vậy, đọc origin của một `URL` chưa đủ để suy ra chính xác origin bảo mật của mọi `Document`.

## 5. Phân biệt bốn nơi thường thấy serialized origin

Một giá trị trông như `https://app.example.com` có thể xuất hiện ở nhiều ngữ cảnh, nhưng ý nghĩa và bên chịu trách nhiệm kiểm tra khác nhau.

| Nơi quan sát | Giá trị biểu diễn cái gì? | Đặc điểm |
|---|---|---|
| `new URL(text).origin` | Origin được tính từ **URL đã parse** | Không nhất thiết phản ánh origin thực tế của một Document được tạo đặc biệt |
| `location.origin` | Giá trị origin được giao diện `Location` biểu diễn trong ngữ cảnh đang xét | Khi xét tài liệu đặc biệt, cần hiểu origin kế thừa và sandbox, không chỉ nhìn địa chỉ |
| HTTP request `Origin` header | Origin/ngữ cảnh khởi phát request theo quy tắc Fetch và bảo vệ riêng tư | Có thể thiếu hoặc là `null`; không phải header gửi trên mọi request |
| `MessageEvent.origin` | Origin đã serialize của bên gửi `postMessage` tại thời điểm gửi | Có thể là `"null"`; cần kiểm tra thêm `source` và nội dung thông điệp |

### 5.1. URL origin khác document origin trong các ngữ cảnh kế thừa

Ví dụ một trang `https://app.example.com` tạo iframe chưa có URL điều hướng riêng:

```html
<iframe id="child"></iframe>
<script>
  const child = document.getElementById("child");

  // Tài liệu about:blank ban đầu thường kế thừa origin của cha.
  child.contentWindow.document.body.textContent =
    "Trang cha có thể sửa DOM của iframe này";

  // Đây chỉ là origin được tính từ chuỗi URL about:blank.
  console.log(new URL("about:blank").origin); // "null"
</script>
```

Thao tác đọc/ghi DOM thành công ở ví dụ là do **ngữ cảnh kế thừa origin**, không phải vì hai chuỗi URL có cùng host. Nếu iframe được áp sandbox không cho phép same-origin, kết quả sẽ khác.

Không nên suy luận "tài liệu about:blank luôn có origin null" hoặc "URL có host A thì document chắc chắn có origin A". Khi cần kiểm soát quyền truy cập, phải tính cả quy tắc tạo tài liệu, sandbox, redirect và ngữ cảnh hiện hành.

### 5.2. HTTP `Origin` header

Một request từ trang `https://shop.example.com/cart` đến API có thể mang header:

```http
GET /account HTTP/1.1
Host: api.example.com
Origin: https://shop.example.com
```

`Origin` không chứa `/cart`, query hay fragment, vì nó cho biết **origin của môi trường gửi**, không phải đường dẫn trang đang đứng. Trình duyệt đặt header này theo quy tắc Fetch; script frontend không được tự do đặt `Origin` bằng `fetch`.

Một số trường hợp có thể khiến giá trị header là:

```http
Origin: null
```

Điều này có thể do nguồn khởi phát opaque (ví dụ tài liệu `data:` hoặc sandbox) hoặc quy tắc bảo vệ riêng tư/ngữ cảnh request. **Không suy ra rằng tất cả các request có `Origin: null` đều đến từ cùng một nơi hoặc cùng một quyền hạn.**

`Origin` không nhất thiết xuất hiện với mọi request: phương thức, mode (`cors`/`no-cors`), chính sách và một số trường hợp đặc biệt ảnh hưởng việc gửi header. Việc không có header phải được xử lý như một trạng thái riêng; nó khác với chuỗi `"null"`.

### 5.3. `MessageEvent.origin` khi nhận `postMessage`

`postMessage` truyền dữ liệu giữa window/frame theo cơ chế cho phép của web platform. Bên nhận thấy:

```js
window.addEventListener("message", (event) => {
  console.log("Serialized sender origin:", event.origin);
  console.log("Sender window:", event.source);
  console.log("Payload:", event.data);
});
```

Nếu bên gửi là tuple origin thông thường, `event.origin` có thể là `"https://pay.example.com"`. Nếu bên gửi có opaque origin, `event.origin` có thể là `"null"`.

**Đừng dùng mỗi `event.origin === "null"` để cấp quyền cho iframe.** Nhiều nguồn không tin cậy có thể tạo tài liệu opaque và xuất hiện cùng chuỗi đó. Ngay cả khi `event.origin` là chuỗi cụ thể được cho phép, vẫn cần đối chiếu `event.source`, cấu trúc `event.data` và quyền nghiệp vụ.

## 6. Vì sao serialized `"null"` có ý nghĩa bảo mật đặc biệt?

### 6.1. Nhiều nguồn khác nhau dùng chung biểu diễn `"null"`

Ví dụ:

```text
data:text/html,...                ─┐
iframe sandbox="allow-scripts"  ──┼──serialize──> "null"
một số ngữ cảnh file:           ─┘
```

Cách biểu diễn trùng nhau **không phải bằng chứng cùng origin**.

Một iframe sandbox có `allow-scripts` nhưng **không có `allow-same-origin`** có thể thực thi script trong origin opaque. Script đó vẫn có thể phát `postMessage` hoặc thử yêu cầu mạng theo các giới hạn áp dụng. Nếu một API cho phép tất cả `Origin: null`, một trang độc hại có thể thử lợi dụng đặc điểm này.

### 6.2. Cấu hình CORS nguy hiểm với `Access-Control-Allow-Origin: null`

Ví dụ response:

```http
Access-Control-Allow-Origin: null
Access-Control-Allow-Credentials: true
```

Cấu hình này có thể cho phép JavaScript từ các ngữ cảnh có serialized origin `"null"` đọc response nếu các điều kiện CORS/credential liên quan được đáp ứng. Đối với dữ liệu nhạy cảm, đây là **rủi ro lớn**: nguồn tấn công có thể cố tạo một tài liệu opaque.

**Không đưa chuỗi `"null"` vào allowlist CORS cho dữ liệu riêng tư.** Nếu hệ thống phải hỗ trợ các ứng dụng chạy từ `file:` hay sandbox, nên thiết kế luồng xác thực và phân phối riêng, thường ưu tiên phục vụ ứng dụng qua origin HTTPS cụ thể thay vì nới quyền CORS đến mọi opaque origin.

### 6.3. `"null"` không phải wildcard và cũng không phải một domain

Ba response sau có nghĩa khác nhau:

| Header | Ý nghĩa |
|---|---|
| `Access-Control-Allow-Origin: https://app.example.com` | Cho phép JavaScript từ serialized origin cụ thể đọc response theo quy tắc CORS |
| `Access-Control-Allow-Origin: *` | Cho phép các origin nói chung đọc response trong trường hợp **không dùng credential** theo CORS |
| `Access-Control-Allow-Origin: null` | Cho phép nguồn có serialized origin `"null"`; **không nên dùng cho dữ liệu nhạy cảm** |

Đừng đặt thêm dấu ngoặc kép vào giá trị HTTP header, ví dụ `Access-Control-Allow-Origin: "null"` hoặc `Access-Control-Allow-Origin: "https://app.example.com"`; cú pháp CORS sử dụng giá trị token/origin, không phải chuỗi JSON có dấu ngoặc.

## 7. CORS: so khớp serialized origin đúng cách

CORS là chính sách cho phép script từ origin khác đọc HTTP response khi server chủ động cấp quyền. Khi dùng allowlist, server có thể so sánh **giá trị `Origin` mà trình duyệt đã serialize** với một tập origin hợp lệ.

### 7.1. Ví dụ allowlist phía server

Đoạn sau dùng Node.js HTTP module, không phụ thuộc framework:

```js
import http from "node:http";

const allowedOrigins = new Set([
  "https://app.example.com",
  "https://admin.example.com:8443",
]);

http.createServer((req, res) => {
  const requestOrigin = req.headers.origin;

  // Response CORS thay đổi theo Origin => cần chỉ dẫn cache phù hợp.
  res.setHeader("Vary", "Origin");

  if (
    typeof requestOrigin === "string" &&
    allowedOrigins.has(requestOrigin)
  ) {
    res.setHeader("Access-Control-Allow-Origin", requestOrigin);
    // Chỉ bật dòng dưới nếu API thực sự cần request có credential:
    // res.setHeader("Access-Control-Allow-Credentials", "true");
  }

  res.setHeader("Content-Type", "application/json; charset=utf-8");
  res.end(JSON.stringify({ message: "Ví dụ CORS" }));
}).listen(8001, "127.0.0.1");
```

Giải thích:

- Tập allowlist chứa các **origin đầy đủ** (scheme/host/port), không phải URL có path.
- So sánh chính xác sẽ không nhận nhầm `https://app.example.com.attacker.test`.
- `"null"` không được cấp quyền; request thiếu header `Origin` cũng không được cấp CORS.
- `Vary: Origin` giúp các cache hiểu response phụ thuộc request origin.
- `Access-Control-Allow-Credentials: true` chỉ cần nếu hỗ trợ đọc response kèm credential; khi bật phải dùng origin cụ thể được phép, không dùng `*`. Cách cookie được gửi còn phụ thuộc `SameSite`, `Secure`, cấu hình request và chính sách trình duyệt.

Đây là ví dụ tối giản cho **đọc response GET đơn giản**. API thực tế có thể cần xử lý `OPTIONS` preflight, `Access-Control-Allow-Methods`, `Access-Control-Allow-Headers`, cache, lỗi, xác thực và phân quyền. CORS **không phải cơ chế xác thực**; client ngoài trình duyệt có thể tự tạo HTTP header, nên server vẫn phải kiểm tra quyền riêng.

### 7.2. Những phép kiểm tra không an toàn

```js
// SAI: chấp nhận attacker.example.com hoặc host nối thêm tiền tố.
origin.endsWith("example.com");

// SAI: "https://app.example.com.attacker.test" có cùng tiền tố.
origin.startsWith("https://app.example.com");

// SAI: origin opaque không nhận diện nguồn tin cậy.
origin === "null";

// SAI: phản chiếu bất kỳ Origin nào cùng với credentials.
response.setHeader("Access-Control-Allow-Origin", origin);
response.setHeader("Access-Control-Allow-Credentials", "true");
```

Nếu thật sự cần cho phép nhiều subdomain, phải có chính sách đăng ký/kiểm soát subdomain riêng, phân tích URL cẩn thận, đánh giá khả năng takeover và cấp quyền chỉ cho các subdomain cần thiết. Cách dễ kiểm tra nhất với tập nhỏ là **allowlist origin chính xác**.

### 7.3. Vì sao không thể thay CSRF token bằng CORS?

Giả sử trình duyệt đang đăng nhập `https://bank.example.com` và một trang độc khiến nó gửi request chuyển tiền. CORS có thể ngăn script của trang độc **đọc response**, nhưng một số request cross-origin vẫn có thể **được gửi**. Vì vậy:

- Đối với thao tác thay đổi trạng thái: dùng **CSRF token được kiểm tra phía server**, kiểm tra `Origin`/`Referer` theo chính sách, và cookie `SameSite` phù hợp.
- Không xem `Origin` là một cơ chế xác thực người dùng: header có thể vắng mặt ở một số request và có thể bị giả mạo bởi client không phải trình duyệt.
- Không cấp quyền chỉ vì `Origin: null`; đây không phải một danh tính đáng tin cậy.
- Có thể bổ sung kiểm tra Fetch Metadata như `Sec-Fetch-Site` để tăng phòng vệ.

## 8. postMessage: dùng origin serialization để kiểm tra nguồn gửi

Xét trang `https://shop.example.com` nhúng iframe thanh toán từ `https://pay.example.net`.

**Bên iframe** gửi thông điệp đến origin cụ thể của trang cha:

```js
window.parent.postMessage(
  { type: "PAYMENT_READY", version: 1 },
  "https://shop.example.com"
);
```

**Bên trang cha** xác minh trước khi xử lý:

```js
const paymentFrame = document.getElementById("payment-frame");

window.addEventListener("message", (event) => {
  if (event.origin !== "https://pay.example.net") return;
  if (event.source !== paymentFrame.contentWindow) return;

  const message = event.data;
  if (
    !message ||
    message.type !== "PAYMENT_READY" ||
    message.version !== 1
  ) {
    return;
  }

  console.log("Khung thanh toán đã sẵn sàng");
});
```

**Quy tắc:** phía gửi dùng `targetOrigin` cụ thể; phía nhận kiểm tra `event.origin` và `event.source`, xác thực cấu trúc dữ liệu và thực thi kiểm soát nghiệp vụ. Không dùng `*` cho thông điệp bí mật khi đã biết chính xác origin đích.

Nếu frame có opaque origin, không thể nhận diện nguồn duy nhất bằng serialized `"null"`. Với những trường hợp buộc phải giao tiếp, cần kiểm tra đối tượng cửa sổ, giao thức trao đổi được thiết kế trước, nonce/capability và giới hạn dữ liệu chia sẻ; tránh truyền bí mật qua wildcard `targetOrigin`.

**Lưu ý về điều hướng:** `event.origin` phản ánh origin của bên gửi tại thời điểm gửi. Một window có thể điều hướng sau đó, nên không dùng kết quả kiểm tra một thông điệp để mặc nhiên tin tưởng tất cả thông điệp hoặc trạng thái tương lai.

## 9. Origin serialization khác cookie scope và same-site

Hai URL sau **khác origin** vì port:

```text
http://app.example.com:3000
http://app.example.com:4000
```

Nhưng cookie không dùng port làm ranh giới scope giống SOP: các cookie thích hợp cho cùng hostname/path/scheme có thể được gửi ở cả hai port, tùy thuộc thuộc tính cookie và chính sách trình duyệt. Vì vậy **khác serialized origin không đồng nghĩa cookie được cách ly theo port**.

Tương tự:

```text
https://shop.example.com
https://api.example.com
```

Hai URL **khác origin**, nhưng có thể **cùng schemeful site** vì đều dùng HTTPS và có registrable domain `example.com`. Một cookie có `Domain=example.com` (nếu hợp lệ) có thể áp dụng cho nhiều subdomain; cookie host-only chỉ gắn với host đã đặt. Quy tắc cookie, `SameSite`, `Secure`, `HttpOnly`, `Path`, Partitioned cookies và hạn chế theo browser đều cần đánh giá riêng.

| Câu hỏi | Khái niệm/cơ chế cần dùng |
|---|---|
| Script có thể đọc DOM hoặc response của tài liệu khác không? | Origin, SOP, CORS |
| Hai URL được xem là cùng site trong chính sách cookie không? | Schemeful site và eTLD+1 |
| Cookie có được gửi trong request không? | Domain/host-only, Path, Secure, SameSite, partitioning, chính sách browser |
| Một iframe có được nhúng trang nhạy cảm không? | CSP `frame-ancestors` và/hoặc `X-Frame-Options` |
| Dữ liệu không tin cậy có thể gây XSS không? | Output encoding, sanitization, CSP, Trusted Types |
| Hai tài liệu có cùng renderer process không? | Chính sách phân bổ tiến trình và Site Isolation của trình duyệt |

Origin serialization thường xuất hiện trong kiểm tra các chính sách này, nhưng **không thay thế** các quy tắc xác thực, cookie, sandbox, phân quyền và kiểm soát dữ liệu riêng.

## 10. Thực hành kiểm chứng trong trình duyệt

### Bài A — Quan sát chuẩn hóa và serialized `"null"`

Trong DevTools → Console chạy đoạn mã ở mục 4.1. Trả lời:

1. Vì sao URL có `:443` và không có `:443` cùng cho chuỗi origin HTTPS?
2. Vì sao `https://shop.example.com` khác `http://shop.example.com`?
3. `new URL("data:text/html,Hello").origin` trả về kiểu `string` hay giá trị JavaScript `null`?
4. `blob:https://shop.example.com/1234` có bắt buộc trả về `"null"` không?

**Kết quả mong đợi:** Hai URL HTTPS tương đương sau chuẩn hóa port mặc định; HTTP/HTTPS khác scheme; opaque origin được serialize thành string `"null"`; blob URL gắn với tuple origin HTTP(S) có thể serialize thành tuple origin tương ứng.

### Bài B — Opaque origin trong sandbox iframe

Tạo `sandbox-origin.html` với nội dung:

```html
<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <title>Quan sát opaque origin</title>
</head>
<body>
  <h1>Parent document</h1>
  <iframe id="demo" sandbox="allow-scripts"></iframe>

  <script>
    const frame = document.getElementById("demo");

    window.addEventListener("message", (event) => {
      if (event.source !== frame.contentWindow) return;
      if (event.data?.type !== "OPAQUE_ORIGIN_PROBE") return;

      console.log("event.origin:", event.origin); // "null"
      console.log("typeof:", typeof event.origin); // "string"
    });

    frame.srcdoc =
      "<script>parent.postMessage({type:'OPAQUE_ORIGIN_PROBE'}, '*')<\/script>";
  </script>
</body>
</html>
```

Chạy HTTP server trong thư mục chứa file:

```bash
python -m http.server 8000 --bind 127.0.0.1
```

Mở `http://127.0.0.1:8000/sandbox-origin.html` và DevTools → Console. Thông điệp từ iframe dự kiến có `event.origin === "null"` dù URL của trang cha là HTTP.

**Giải thích:** Iframe có `sandbox="allow-scripts"` nên script được phép thực thi; vì không có `allow-same-origin`, tài liệu trong iframe bị đặt vào opaque origin. Nếu thêm `allow-same-origin` vào sandbox thì hành vi thay đổi; tránh kết hợp `allow-scripts` và `allow-same-origin` một cách tùy tiện với nội dung nhúng cùng origin, vì có thể làm giảm hiệu quả sandbox.

Quan sát này chỉ kiểm chứng **serialization của opaque origin**. Nó không chứng minh iframe là cùng hoặc khác OS process so với trang cha.

### Bài C — CORS allowlist với hai port

Tạo `cors-server.mjs`:

```js
import http from "node:http";

const allowedOrigins = new Set(["http://127.0.0.1:8000"]);

http.createServer((req, res) => {
  const origin = req.headers.origin;

  res.setHeader("Content-Type", "application/json; charset=utf-8");
  res.setHeader("Vary", "Origin");

  if (typeof origin === "string" && allowedOrigins.has(origin)) {
    res.setHeader("Access-Control-Allow-Origin", origin);
  }

  res.end(JSON.stringify({
    receivedOrigin: origin ?? null,
    message: "API from port 8001",
  }));
}).listen(8001, "127.0.0.1", () => {
  console.log("API: http://127.0.0.1:8001");
});
```

Trong terminal thứ hai, chạy:

```bash
node cors-server.mjs
```

Trong Console của trang `http://127.0.0.1:8000/sandbox-origin.html` (chọn **ngữ cảnh trang cha**, không phải iframe), chạy:

```js
fetch("http://127.0.0.1:8001/api")
  .then((response) => response.json())
  .then(console.log)
  .catch(console.error);
```

Kết quả mong đợi:

- Request có `Origin: http://127.0.0.1:8000` (trang cha); server nhận đúng chuỗi này.
- Server trả `Access-Control-Allow-Origin: http://127.0.0.1:8000` nên script có thể đọc response.
- Đổi `allowedOrigins` thành tập rỗng và khởi động lại server, rồi chạy `fetch` một lần nữa: request mạng có thể hoàn tất nhưng **JavaScript bị chặn đọc response** bởi CORS.
- Nếu thử request từ **ngữ cảnh iframe opaque**, `Origin` có thể là `null`. Server không cấp CORS cho `null`. Lưu ý công cụ Console có thể cho chọn frame hiện hành; hãy xác định đúng context đang chạy script.

Dừng hai server khi hoàn tất. Ví dụ minh họa kiểm tra origin khi đọc response; nếu mở rộng sang request có credential hoặc request không đơn giản, cần thêm xử lý tương ứng.

## 11. Các lỗi phổ biến cần tránh

| Hiểu sai / cấu hình sai | Cách hiểu và cách sửa |
|---|---|
| "Origin chính là URL đầy đủ." | Origin thường chỉ là scheme + host + port; path/query/fragment không được serialize. |
| "`https://example.com/` là giá trị allowlist giống `https://example.com`." | Serialized origin không có dấu slash cuối; cấu hình đúng dạng origin. |
| "Port không quan trọng vì hostname đã giống nhau." | SOP tính port; chỉ port **mặc định** được chuẩn hóa thành không hiển thị. |
| "`null` nghĩa là không có origin nên đáng tin." | `"null"` là chuỗi biểu diễn opaque origin hoặc một số trường hợp riêng tư; không dùng để cấp quyền. |
| "Hai serialized origin cùng bằng `null` thì cùng origin." | Các opaque origin khác nhau có thể serialize trùng nhau nhưng không cùng danh tính. |
| "Có thể lấy `new URL("about:blank").origin` để biết chắc origin của mọi iframe about:blank." | Origin document có thể kế thừa từ creator/parent; còn chịu ảnh hưởng sandbox. |
| "`Origin` luôn có trên mọi HTTP request." | Header chỉ xuất hiện theo quy tắc request và chính sách cụ thể; thiếu header và `Origin: null` khác nhau. |
| "CORS chặn mọi CSRF." | CORS chủ yếu quản lý quyền đọc response; CSRF cần bảo vệ phía server. |
| "Có thể tin `event.origin === "null"`." | Phải xác minh nguồn cửa sổ, giao thức và payload; không cấp quyền vì chuỗi này. |
| "Cookie, SOP và Site Isolation dùng cùng một ranh giới origin." | Cookie có scope riêng; SOP dùng origin; Site Isolation dùng chính sách triển khai trình duyệt. |

## 12. Checklist bảo mật khi sử dụng serialized origin

1. **Xác định đúng đầu vào:** Bạn đang so sánh origin nội bộ, `URL.origin`, HTTP `Origin`, hay `event.origin`? Mỗi ngữ cảnh có quy tắc riêng.
2. **Dùng origin chính xác:** Allowlist gồm scheme + host + port khi cần; không thêm path, wildcard host thiếu kiểm soát, dấu slash cuối hoặc tiền tố không đáng tin.
3. **Xử lý `"null"` thận trọng:** Không xem như danh tính duy nhất; tránh cho phép `Access-Control-Allow-Origin: null` với dữ liệu nhạy cảm.
4. **Phân biệt thiếu header:** Không đánh đồng `Origin` bị thiếu với chuỗi `"null"`, và không dùng duy nhất Origin làm xác thực.
5. **Áp CORS đúng:** So khớp allowlist, đặt `Vary: Origin` khi phản hồi thay đổi theo origin; xử lý credential và preflight riêng nếu cần.
6. **Bảo vệ message:** Chỉ định `targetOrigin` cụ thể khi có thể; kiểm tra `event.origin`, `event.source`, schema và quyền nghiệp vụ.
7. **Không bỏ sót phòng vệ khác:** CSRF token và SameSite cookie cho CSRF, kiểm soát DOM injection/CSP/Trusted Types cho XSS, `frame-ancestors` cho clickjacking.
8. **Kiểm chứng thực tế:** Xem Network → Request Headers/Response Headers, Console và môi trường frame đang chọn; thử URL port mặc định, port tùy biến, sandbox, `data:` và iframe.

## 13. Câu hỏi ôn tập

1. Origin serialization nhằm giải quyết vấn đề gì? Vì sao không thể dùng chuỗi đó để tái dựng một opaque origin?
2. `new URL("https://APP.example.com:443/cart?q=1").origin` trả về gì? Tại sao?
3. So sánh `https://app.example.com` và `https://app.example.com:8443`: chúng có cùng origin không?
4. Hai iframe sandbox khác nhau đều phát `event.origin === "null"`; điều này có chứng minh chúng cùng origin không?
5. Khác biệt giữa `new URL("about:blank").origin` và origin thực tế của một iframe about:blank được tạo từ trang cha là gì?
6. Vì sao `Access-Control-Allow-Origin: null` có thể nguy hiểm với API chứa dữ liệu cá nhân?
7. Vì sao một `Origin` hợp lệ không thể thay thế xác thực, phân quyền và CSRF token?
8. Cookie cho cùng hostname nhưng khác port có nhất thiết được cô lập như SOP không?

**Đáp án định hướng:** (1) Chuyển origin nội bộ thành chuỗi; opaque origin không thể tái tạo từ `"null"`. (2) `https://app.example.com` do chuẩn hóa chữ thường, port mặc định và bỏ path/query. (3) Không, port khác. (4) Không. (5) Origin của document có thể được kế thừa; URL text độc lập không chứa thông tin đó. (6) Kẻ tấn công có thể tạo ngữ cảnh có opaque origin và thử đọc response được CORS cấp cho `null`. (7) Header là tín hiệu ngữ cảnh browser, không phải chứng thực danh tính của client hoặc quyền người dùng. (8) Không; cookie matching không dùng port giống SOP.

## 14. Tài liệu tham khảo

- [WHATWG HTML Standard — Origins](https://html.spec.whatwg.org/multipage/browsers.html#origin): Định nghĩa tuple/opaque origin, phép so sánh origin và thuật toán serialization.
- [MDN — URL: origin property](https://developer.mozilla.org/en-US/docs/Web/API/URL/origin): Ví dụ chuẩn hóa URL, blob URL và trường hợp `file:`.
- [MDN — Origin HTTP header](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Origin): Cú pháp `Origin` và những trường hợp giá trị `null` hoặc header bị thiếu.
- [MDN — Access-Control-Allow-Origin](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Access-Control-Allow-Origin): Cách allowlist origin, cảnh báo với `null` và `Vary: Origin`.
- [MDN — Same-origin policy](https://developer.mozilla.org/en-US/docs/Web/Security/Same-origin_policy): SOP, origin kế thừa và tương tác giữa các tài liệu.
- [MDN — Window.postMessage](https://developer.mozilla.org/en-US/docs/Web/API/Window/postMessage): Kiểm tra `targetOrigin`, `event.origin` và nguồn thông điệp.
- [OWASP — Cross Site Scripting Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet.html) và [CSRF Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html): Phòng vệ phía ứng dụng song song với chính sách trình duyệt.

**Kết luận:** Origin serialization tạo ra biểu diễn chuẩn cho danh tính origin trong JavaScript, HTTP và giao tiếp frame. Với tuple origin, biểu diễn dùng scheme/host/port đã chuẩn hóa; với opaque origin, kết quả `"null"` không chứa danh tính đủ để xác thực nguồn. Áp dụng đúng nguyên tắc này là điều kiện cần để cấu hình CORS an toàn, kiểm tra `postMessage` và tránh nhầm lẫn giữa các ranh giới origin, site, cookie và tiến trình trình duyệt.
