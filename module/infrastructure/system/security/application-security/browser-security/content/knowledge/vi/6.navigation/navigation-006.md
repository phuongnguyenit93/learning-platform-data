# URL fragment trong navigation: cơ chế hoạt động, giới hạn và bảo mật

## 1. URL fragment là gì, và vì sao liên quan đến bảo mật trình duyệt?

Trong URL `https://shop.example.test/products/42#reviews`, phần `#reviews` được gọi là **URL fragment** (fragment identifier). Nó xuất hiện sau dấu `#` đầu tiên được dùng làm ký tự phân cách fragment và thường chỉ **một vị trí, một phần tài liệu hoặc một trạng thái được diễn giải ở phía client**.

Đây là thành phần quen thuộc của hành vi **navigation**: nhấp vào mục lục để cuộn tới một tiêu đề, mở tab bằng đường dẫn có `#tab=details`, hoặc dùng `#/orders` trong ứng dụng một trang (single-page application, SPA). Điểm bảo mật quan trọng là **fragment không thuộc định danh origin và không được gửi trong HTTP request-target thông thường**. Tuy nhiên, fragment vẫn hiện diện ở phía trình duyệt, có thể được JavaScript đọc, thay đổi và đôi khi chuyển thành request mới.

Bài học nằm trong chương **Navigation** của module `SECURITY_APPLICATION_SECURITY_BROWSER_SECURITY`, tập trung vào **URL fragment** ở ranh giới giữa URL, trình duyệt, DOM, lịch sử điều hướng và ứng dụng web. Hiểu đúng ranh giới này hỗ trợ phân tích Same-Origin Policy (SOP), CORS, cookie; đồng thời tránh lỗi DOM XSS, luồng chuyển hướng không an toàn, rò rỉ token, sai sót xác thực và giao diện dễ bị lợi dụng.

### Mục tiêu

Hoàn thành bài này, người học có thể:

1. Nhận diện fragment trong URL và phân biệt nó với path, query, origin.
2. Giải thích tại sao fragment không được gửi trong HTTP request-target, nhưng vẫn có thể xuất hiện ở JavaScript và các hệ thống nhận dữ liệu do client chuyển tiếp.
3. So sánh điều hướng tới `#id`, hash routing và History API.
4. Dùng `location.hash`, `URL.hash`, `hashchange`, `history.pushState` và `history.replaceState` đúng mục đích.
5. Xác định fragment là **dữ liệu không tin cậy**, có thể trở thành nguồn DOM XSS hoặc open redirect nếu xử lý sai.
6. Thiết kế cách sử dụng fragment tránh chứa bí mật và không coi fragment là cơ chế phân quyền.
7. Kiểm chứng hành vi bằng DevTools trong môi trường do mình kiểm soát.

## 2. Fragment nằm ở đâu trong URL?

Ví dụ:

~~~text
https://shop.example.test:8443/docs/guide?lang=vi#installation
└─────┬────┘ └───────┬────────┘└┬┘└────┬─────┘└──┬──┘└───┬──────┘
    scheme           host       port   path       query    fragment
~~~

Về mặt cú pháp, fragment bắt đầu sau dấu `#` phân cách. Bản thân dấu `#` là **delimiter**, không thuộc nội dung fragment.

| Thành phần | Giá trị trong ví dụ | Có thuộc origin? | Vai trò |
| --- | --- | --- | --- |
| Scheme | `https` | **Có** | Giao thức URL. |
| Host | `shop.example.test` | **Có** | Host được URL tham chiếu. |
| Port | `8443` | **Có** | Cổng khác mặc định. |
| Path | `/docs/guide` | Không | Đường dẫn tài nguyên trên origin. |
| Query | `lang=vi` | Không | Thông số của tài nguyên/ứng dụng. |
| Fragment | `installation` | **Không** | Phần hoặc trạng thái được xử lý phía client. |

Với HTTP(S), **origin = (scheme, host, port)**. Vì vậy hai URL sau **cùng origin**, dù fragment khác nhau:

~~~text
https://shop.example.test/account#profile
https://shop.example.test/account#security
~~~

Và hai URL sau **khác origin**, dù fragment giống nhau:

~~~text
https://shop.example.test/account#profile
https://admin.example.test/account#profile
~~~

### 2.1. Dấu `#` và chuỗi `%23` không giống nhau

Dấu `#` phân cách fragment **chỉ khi nó là ký tự phân cách chưa được mã hóa** trong cú pháp URL. Chuỗi `%23` là cách percent-encode dấu `#`, có thể nằm trong path, query hoặc fragment mà không tự tạo ra delimiter mới.

So sánh:

~~~text
https://example.test/search?q=a%23b
https://example.test/search?q=a#b
~~~

- URL thứ nhất có query `q=a%23b`, **không có fragment**.
- URL thứ hai có query `q=a` và fragment `b`.

Nếu ứng dụng ghép chuỗi URL thủ công, nhầm lẫn này có thể khiến tham số bị cắt hoặc nội dung do người dùng kiểm soát vô tình trở thành fragment. Sử dụng `URL` và `URLSearchParams` để tạo/đọc URL sẽ giảm sai sót.

### 2.2. Không coi fragment là một đoạn đường dẫn của máy chủ

~~~text
https://example.test/#/products/42
~~~

Phần `/products/42` ở ví dụ này **nằm trong fragment**. Nó không phải path `/products/42` của HTTP request đến server. Máy chủ nhận URL cơ sở `/`, trừ khi JavaScript ứng dụng gửi thêm request từ nội dung hash.

Đây là điểm thường gây lỗi khi cấu hình backend, analytics, cache hoặc phân quyền cho SPA dùng hash router.

## 3. Fragment được xử lý ở phía client khi tải trang

Hình dung người dùng mở:

~~~text
https://docs.example.test/guide#installation
~~~

Luồng xử lý cơ bản:

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant B as Trình duyệt
    participant S as Máy chủ
    participant D as DOM / JavaScript
    U->>B: Mở /guide#installation
    B->>S: GET /guide (không có #installation)
    S-->>B: HTML của /guide
    B->>D: Tạo tài liệu và xử lý fragment
    D-->>B: Tìm đích điều hướng hoặc xử lý hash route
    B-->>U: Hiển thị và cuộn / cập nhật giao diện
~~~

Request HTTP thông thường không chứa fragment:

~~~http
GET /guide HTTP/1.1
Host: docs.example.test
~~~

Điều này có những hệ quả thực tế:

- Máy chủ HTTP thường **không nhận fragment trong request-target**, nên không thể dùng riêng nó để phân biệt resource `/guide#intro` và `/guide#advanced`.
- Hai URL chỉ khác fragment có thể dùng **cùng phản hồi HTML** và cùng cache entry của tài nguyên HTTP cơ sở; hành vi hiển thị có thể khác do trình duyệt hoặc script.
- Máy chủ có thể nhận biết fragment **gián tiếp** nếu JavaScript cố ý gửi nó trong body/query/header của một request khác.
- Việc fragment không gửi trong HTTP request-target **không biến nó thành bí mật**: mã chạy trên trang vẫn có thể đọc nó.
- Trong HTTP `Referer` thông thường, fragment được loại bỏ trước khi đưa vào header. Điều này không ngăn JavaScript, analytics, nội dung được chia sẻ hoặc trình duyệt mở rộng thu thập fragment bằng con đường khác.

### 3.1. Tải trang mới khác với đổi fragment trên cùng trang

Nếu người dùng điều hướng từ `https://docs.example.test/home` sang `https://docs.example.test/guide#installation`, trình duyệt có thể tải tài liệu `/guide` từ mạng hoặc cache như một navigation mới, rồi xử lý fragment.

Nếu đã ở `https://docs.example.test/guide#intro` và chỉ đổi thành `https://docs.example.test/guide#installation`, đây thường là **same-document navigation**. Trình duyệt có thể thêm mục vào lịch sử, cập nhật điểm cuộn hoặc thông báo sự kiện liên quan mà không tải lại HTML `/guide`.

Tuy vậy, **ứng dụng JavaScript có thể tự tạo request mạng** khi hash thay đổi. Do đó quan sát thêm request trong Network không chứng minh fragment đã được trình duyệt gửi trực tiếp trong request-target.

## 4. Những cách sử dụng fragment thường gặp

| Dạng URL | Người xử lý chính | Ý nghĩa |
| --- | --- | --- |
| `/docs#install` | Trình duyệt | Đi tới phần tử có `id="install"` hoặc một đích điều hướng tương ứng. |
| `/docs#chapter-3` | Trình duyệt | Điều hướng trong tài liệu dài. |
| `/#/products/42` | JavaScript hash router | Tuyến phía client, không phải path của request ban đầu. |
| `/#tab=reviews` | JavaScript ứng dụng | Chọn tab hoặc trạng thái hiển thị. |
| `/#section?filter=active` | JavaScript ứng dụng | Quy ước riêng của ứng dụng; browser không mặc định phân tích thành query của server. |
| `/article#:~:text=browser%20security` | Trình duyệt hỗ trợ text fragments | Chỉ định đoạn văn bản để điều hướng/đánh dấu theo cơ chế riêng của trình duyệt. |

Các ứng dụng có thể tự định nghĩa cấu trúc fragment. Trình duyệt **không** mặc định hiểu `#/orders` là đường dẫn API, `#token=...` là dữ liệu xác thực, hoặc `#tab=...` là trạng thái an toàn.

### 4.1. Anchor navigation truyền thống

HTML:

~~~html
<nav aria-label="Mục lục">
  <a href="#overview">Tổng quan</a>
  <a href="#examples">Ví dụ</a>
</nav>

<section id="overview">
  <h2>Tổng quan</h2>
  <p>Đây là phần giới thiệu.</p>
</section>

<section id="examples">
  <h2>Ví dụ</h2>
  <p>Đây là phần minh họa.</p>
</section>
~~~

Khi nhấp `href="#examples"`, browser thường điều hướng tới phần tử đích. Một selector CSS có thể áp dụng cho phần tử được đánh dấu làm target:

~~~css
:target {
  outline: 2px solid currentColor;
  scroll-margin-top: 4rem;
}
~~~

`:target` là một cơ chế tạo trạng thái giao diện dựa trên fragment. Nó hữu ích cho mục lục, nhưng không phải chính sách phân quyền và không được dùng làm căn cứ duy nhất cho thao tác nhạy cảm.

### 4.2. Hash routing trong SPA

Một SPA có thể dùng:

~~~text
https://app.example.test/#/dashboard
https://app.example.test/#/settings
~~~

Browser vẫn yêu cầu tài liệu `/` từ server khi mở trang. JavaScript đọc fragment rồi quyết định hiển thị màn hình nào.

Ưu điểm của hash routing: ứng dụng có thể chọn màn hình phía client mà không yêu cầu backend trả trang HTML ở từng path khi tải trực tiếp.

Giới hạn: **route ẩn trong fragment không phải bảo vệ máy chủ**. Một ứng dụng hiển thị `#/admin` phải kiểm tra quyền quản trị ở backend đối với mọi dữ liệu/hành động, ngay cả nếu giao diện cố gắng ẩn route khỏi người dùng không có quyền.

## 5. Đọc và thay đổi fragment bằng JavaScript

Web API cung cấp nhiều cách đọc URL. Ví dụ:

~~~js
const current = new URL(
  "https://shop.example.test/catalog?q=tablet#reviews"
);

console.log(current.origin);   // "https://shop.example.test"
console.log(current.pathname); // "/catalog"
console.log(current.search);   // "?q=tablet"
console.log(current.hash);     // "#reviews"

current.hash = "details";
console.log(current.href);
// "https://shop.example.test/catalog?q=tablet#details"
~~~

Trên tài liệu hiện tại:

~~~js
console.log(window.location.hash); // Ví dụ "#reviews"
console.log(window.location.href); // Toàn bộ URL (với fragment thông thường)
~~~

Điểm dễ nhầm:

- `URL.hash` và `location.hash` thường bắt đầu bằng `#` nếu có fragment không rỗng.
- Ký tự percent-encoded có thể được giữ dưới dạng mã hóa khi đọc `hash`; **đừng giả định** đây là chuỗi đã được decode cho mọi ký tự.
- Giá trị `hash === ""` không đủ để phân biệt chắc chắn URL **không có dấu #** với URL có fragment rỗng `#`; nếu việc này thực sự cần cho thiết kế, phải kiểm tra bằng API/quy tắc phù hợp.
- `location.hash` là **dữ liệu do URL cung cấp**, có thể do người khác đặt trong liên kết gửi cho người dùng.

### 5.1. Decode phải có giới hạn và xử lý lỗi

Một ứng dụng có thể muốn chuyển fragment encoded thành văn bản:

~~~js
function readFragment(maxLength = 200) {
  const raw = window.location.hash.slice(1);

  if (raw.length > maxLength) {
    return { ok: false, reason: "Fragment quá dài" };
  }

  try {
    return { ok: true, value: decodeURIComponent(raw) };
  } catch {
    return { ok: false, reason: "Percent encoding không hợp lệ" };
  }
}
~~~

Đây chỉ là bước đọc dữ liệu an toàn hơn trước khi xử lý. **Decode không phải sanitize và không bảo đảm dữ liệu an toàn để chèn vào HTML**. Với cú pháp route phức tạp, cần parser/validator theo định dạng ứng dụng đã định nghĩa.

### 5.2. `location.hash` có thể tạo điều hướng

~~~js
location.hash = "examples";
~~~

Thao tác thường tạo cùng-document navigation tới `#examples`, có thể ảnh hưởng điểm cuộn, URL hiển thị và lịch sử trang. Nó không có nghĩa máy chủ nhận `GET /page#examples`.

Nếu muốn thay đổi fragment mà **thay thế** mục lịch sử hiện tại thay vì thêm mục mới, có thể dùng History API:

~~~js
const next = new URL(location.href);
next.hash = "examples";
history.replaceState(history.state, "", next);
~~~

History API có ràng buộc **same-origin** đối với URL mới; thay fragment qua `replaceState` không tự kích hoạt `hashchange`. Cần đồng bộ giao diện ứng dụng chủ động nếu dùng kỹ thuật này.

## 6. `hashchange` và lịch sử điều hướng

Sự kiện `hashchange` giúp ứng dụng phản ứng với thay đổi fragment trong các điều hướng phù hợp, ví dụ người dùng nhấp anchor hoặc script gán `location.hash`:

~~~js
function showFragment() {
  const raw = location.hash.slice(1);
  document.querySelector("#current-fragment").textContent = raw;
}

window.addEventListener("hashchange", (event) => {
  console.log("Từ:", event.oldURL);
  console.log("Đến:", event.newURL);
  showFragment();
});

showFragment();
~~~

`event.oldURL` và `event.newURL` là địa chỉ URL liên quan đến việc thay đổi, có thể chứa fragment. Không ghi nguyên những URL này vào log/analytics nếu ứng dụng có khả năng chứa dữ liệu riêng tư trong URL.

### 6.1. Những điều `hashchange` không làm

| Thao tác | Có làm thay đổi URL không? | Có tự phát `hashchange` không? | Ghi chú |
| --- | --- | --- | --- |
| Nhấp `<a href="#section">` tới fragment mới | Có | Thường **có** | Có thể cuộn tới phần tử đích. |
| Gán `location.hash = "section"` | Có | Thường **có** nếu fragment thực sự đổi | Có thể tạo mục lịch sử mới. |
| `history.pushState(state, "", "#section")` | Có | **Không** | Ứng dụng phải tự cập nhật giao diện. |
| `history.replaceState(state, "", "#section")` | Có | **Không** | Thay mục lịch sử hiện tại. |
| Browser Back/Forward | Có thể | Phụ thuộc bước lịch sử được duyệt | Có thể phát các sự kiện lịch sử phù hợp, gồm `popstate` và/hoặc `hashchange` theo trường hợp. |

History API có các sự kiện/nguyên tắc khác với điều hướng hash truyền thống. Nếu thiết kế SPA kết hợp `hashchange` và `popstate`, phải có **một nguồn trạng thái rõ ràng** để tránh render hai lần hoặc bỏ sót cập nhật.

### 6.2. Điều hướng fragment ảnh hưởng trải nghiệm người dùng

Browser có thể cuộn, cập nhật phần tử target, lưu các mục history và phục hồi vị trí cuộn khi người dùng đi Back/Forward. Những hành vi này còn phụ thuộc trình duyệt, nội dung được tải trễ, CSS và code ứng dụng.

Một liên kết sâu (deep link) nên đưa người dùng tới vị trí đúng, ngay cả khi JavaScript không chạy, nếu tính năng có thể thực hiện bằng anchor HTML. Nếu cần state phức tạp, cân nhắc cách đồng bộ URL và UI sao cho Back/Forward hoạt động dự đoán được.

## 7. Fragment có thuộc SOP, CORS hay phạm vi cookie không?

**Không**: fragment không tham gia xác định origin hoặc site. Hai URL cùng scheme/host/port nhưng khác fragment vẫn **same-origin**, dù có thể hiển thị hai trạng thái UI khác nhau.

| Cơ chế | Fragment ảnh hưởng thế nào? |
| --- | --- |
| SOP | Không tạo origin mới; giới hạn DOM và các quyền cross-origin vẫn theo origin, tài liệu và chính sách khác. |
| CORS | Server kiểm tra origin gửi request; fragment của URL request không phải thành phần trong `Origin` header. |
| Cookie | Không có thuộc tính phạm vi cookie theo fragment; cookie xét host/domain, path, `SameSite`, `Secure` và các quy tắc khác. |
| `localStorage`/IndexedDB | Fragment không làm đổi origin lưu trữ; các chính sách partitioning khác có thể áp dụng. |
| CSP | Các chính sách như `script-src`, `connect-src`, `frame-ancestors` áp dụng theo vai trò riêng; fragment không thay thế chúng. |
| Authentication/authorization | Fragment không chứng minh danh tính hoặc quyền của người dùng; server phải kiểm tra request thật. |

Ví dụ hai URL:

~~~text
https://app.example.test/#/user
https://app.example.test/#/admin
~~~

Có **cùng origin**. Nếu frontend tự coi người có `#/admin` là admin thì đó là lỗi logic. Người dùng hoàn toàn có thể sửa fragment trong address bar mà không cần xâm phạm SOP.

### 7.1. Fragment không bảo vệ request đổi trạng thái

Fragment bản thân nó không được gửi trong HTTP request-target, nhưng ứng dụng có thể đọc fragment để chọn hành động rồi gửi API request:

~~~js
// Minh họa logic cần được bảo vệ đầy đủ ở server:
const route = location.hash.slice(1);

if (route === "/delete-account") {
  // Tuyệt đối không tự động gọi API nguy hiểm chỉ vì URL chứa hash.
}
~~~

Một liên kết do bên ngoài gửi có thể khiến người dùng mở đúng hash route này. Với API nhạy cảm, cần yêu cầu tương tác/chủ đích phù hợp, xác thực, phân quyền và chống CSRF theo phương thức xác thực. **Không được dùng fragment để miễn trừ kiểm tra CSRF.**

## 8. Ranh giới dữ liệu không tin cậy: DOM XSS từ `location.hash`

Một trong những lỗi bảo mật quan trọng nhất là **DOM-based XSS**: dữ liệu từ URL được JavaScript chuyển vào API có khả năng phân tích HTML hoặc thực thi mã.

Ví dụ **không an toàn**:

~~~html
<div id="output"></div>
<script>
  const fragment = decodeURIComponent(location.hash.slice(1));
  document.querySelector("#output").innerHTML =
    "Bạn đang xem: " + fragment;
</script>
~~~

Nguồn dữ liệu là `location.hash` do người dùng/đường dẫn bên ngoài kiểm soát. Sink nguy hiểm là `innerHTML`, nơi giá trị chuỗi có thể biến thành markup với các hành vi không mong muốn. Do fragment không đi qua request HTTP ban đầu, bộ lọc hoặc log ở máy chủ có thể không nhìn thấy đầu vào gây lỗi.

Một cách xử lý phù hợp khi chỉ hiển thị chữ:

~~~html
<div id="output"></div>
<script>
  const fragment = location.hash.slice(1);

  document.querySelector("#output").textContent =
    "Bạn đang xem: " + fragment;
</script>
~~~

`textContent` xử lý nội dung như văn bản, tránh việc trình phân tích HTML biến chuỗi đầu vào thành nút DOM/script. Nếu cần decode/validate để hiển thị chuẩn hơn, làm trước và **vẫn kết thúc ở text sink an toàn**.

### 8.1. Phân biệt source, transformation và sink

~~~mermaid
flowchart LR
    A["Link của người ngoài<br/>#%3C...%3E"] --> B["location.hash<br/>SOURCE"]
    B --> C["slice / decode<br/>TRANSFORMATION"]
    C --> D{"SINK nào?"}
    D -->| "innerHTML" | E["HTML parsing<br/>có nguy cơ DOM XSS"]
    D -->| "textContent" | F["Hiển thị văn bản<br/>an toàn hơn"]
~~~

Đừng mặc định `decodeURIComponent`, `encodeURIComponent`, escape theo ngữ cảnh sai hoặc lọc vài ký tự là đủ phòng chống XSS. An toàn phụ thuộc **ngữ cảnh đầu ra**: HTML text, HTML attribute, URL, JavaScript, CSS và DOM API có đặc tính khác nhau.

Khi ứng dụng thực sự cần hiển thị HTML do người dùng cung cấp, dùng thư viện sanitize có bảo trì và chính sách cho phép cụ thể; tránh tự viết bộ lọc với regex.

### 8.2. CSP và Trusted Types hỗ trợ thế nào?

**Content Security Policy (CSP)** có thể giới hạn nguồn script và những kiểu thực thi script không mong muốn:

~~~http
Content-Security-Policy: default-src 'self'; script-src 'self' 'nonce-{NONCE_MOI_RESPONSE}'; object-src 'none'; base-uri 'none'
~~~

Nonce phải được sinh an toàn cho từng HTML response và đặt trên script hợp lệ. Chính sách thực tế cần phù hợp resource ứng dụng. CSP hỗ trợ giảm rủi ro XSS nhưng không thay thế sửa sink DOM không an toàn.

**Trusted Types** giúp hạn chế truyền string tùy ý vào một số DOM injection sink trên những trình duyệt hỗ trợ:

~~~http
Content-Security-Policy: require-trusted-types-for 'script'; trusted-types appSanitizer
~~~

Ứng dụng phải định nghĩa policy đúng và **thực hiện sanitize thật** đối với HTML nếu cần. Không tạo policy chỉ để gắn nhãn “trusted” cho mọi dữ liệu từ hash. Trusted Types không được hỗ trợ giống nhau ở mọi trình duyệt; dùng `textContent`, validation và sanitize vẫn là nền tảng.

### 8.3. Fragment không tự là script

Việc mở `https://app.example.test/#...` không tự thực thi đoạn văn bản sau `#`. Rủi ro xuất hiện khi **mã của ứng dụng** diễn giải fragment theo cách không an toàn: đưa vào `innerHTML`, tạo JavaScript động, dùng làm URL điều hướng không kiểm tra hoặc xây request có tác dụng mạnh. Phân tích đúng điểm chuyển **dữ liệu → lệnh** giúp tránh kết luận sai về trình duyệt.

## 9. Hash router an toàn: parse, giới hạn và phân quyền

Một hash router đơn giản có thể định nghĩa duy nhất các route được phép:

~~~html
<nav>
  <a href="#/">Trang chủ</a>
  <a href="#/products">Sản phẩm</a>
  <a href="#/orders">Đơn hàng</a>
</nav>
<h1 id="page-title"></h1>

<script>
  const pages = new Map([
    ["/", "Trang chủ"],
    ["/products", "Sản phẩm"],
    ["/orders", "Đơn hàng"]
  ]);

  function renderFromHash() {
    const route = location.hash.slice(1) || "/";
    const title = pages.get(route) ?? "Không tìm thấy trang";

    document.querySelector("#page-title").textContent = title;
  }

  window.addEventListener("hashchange", renderFromHash);
  renderFromHash();
</script>
~~~

Mẫu này có một số đặc tính tốt:

- Chỉ chấp nhận route **nằm trong allowlist**.
- Hiển thị dữ liệu bằng `textContent`, không ép chuỗi hash thành HTML.
- Không xem `#/orders` là chứng chỉ người dùng được xem đơn hàng.
- Nếu cần tải danh sách đơn hàng, backend kiểm tra **đúng người sở hữu**, kể cả khi người dùng thay fragment bằng tay.

Ứng dụng thực tế cần chuẩn hóa route, giới hạn độ dài, xử lý query nội bộ fragment một cách có cấu trúc, quản lý trạng thái Back/Forward và xử lý trạng thái tải/lỗi. Với các route nhạy cảm, cần xác thực và phân quyền **trên API**, không ở parser fragment.

### 9.1. Nếu hash chứa tham số

Một số router dùng:

~~~text
#/products?sort=price&category=book
~~~

Đây là **chuỗi thuộc fragment**, không phải `location.search`. Nếu muốn đọc tham số, ứng dụng phải parse theo quy ước:

~~~js
const raw = location.hash.slice(1);
const index = raw.indexOf("?");

const route = index >= 0 ? raw.slice(0, index) : raw;
const search = index >= 0 ? raw.slice(index + 1) : "";

const params = new URLSearchParams(search);
const sort = params.get("sort");

console.log({ route, sort });
~~~

`URLSearchParams` giúp parse tham số, nhưng **không tự xác nhận giá trị hợp lệ**. Ví dụ `sort` chỉ nên nhận một danh sách đã xác định như `price`, `newest`. Mọi dữ liệu được đưa vào request phải được backend kiểm tra độc lập.

### 9.2. Không dùng fragment làm cơ chế khóa chức năng

Mã kiểu sau là thiết kế sai:

~~~js
if (location.hash === "#/admin") {
  showAdminControls();
  allowDeleteUsers = true;
}
~~~

Fragment có thể bị người dùng sửa tự do. Nếu việc “cho phép xóa người dùng” chỉ xuất phát từ biến frontend, không có bảo vệ backend thì đây là **broken access control**, không phải lỗi SOP.

## 10. Open redirect và điều hướng dựa trên fragment

Một ứng dụng có thể dùng fragment để chọn đích đến:

~~~text
https://app.example.test/redirect#https://other.test/
~~~

**Anti-pattern:** lấy trực tiếp nội dung hash làm URL điều hướng:

~~~js
// Không an toàn nếu cho phép fragment điều khiển đích ngoài ý muốn:
const destination = decodeURIComponent(location.hash.slice(1));
location.assign(destination);
~~~

Trong các luồng đăng nhập, thanh toán hoặc xác nhận, cách xử lý này có thể tạo **open redirect**, phishing và làm người dùng hiểu nhầm mình vẫn đi theo ứng dụng tin cậy. Ngoài URL ngoài, còn phải thận trọng với những scheme không phù hợp như `javascript:` hoặc `data:`.

Thiết kế tốt hơn: dùng **mã định danh nội bộ** và bảng route có sẵn:

~~~js
const destinations = new Map([
  ["home", "/"],
  ["help", "/help"],
  ["account", "/account"]
]);

const key = location.hash.slice(1);
const destination = destinations.get(key);

if (destination) {
  location.assign(destination);
}
~~~

Nếu nghiệp vụ thực sự cần điều hướng theo URL động, dùng `new URL(value, location.origin)`, kiểm tra scheme và **origin đích chính xác**, allowlist điểm đến được tin cậy, giới hạn đường dẫn và chỉ xử lý sau xác nhận người dùng khi phù hợp. Không kiểm tra bằng `includes("example.test")` hoặc `endsWith("example.test")` trên chuỗi tùy ý.

### 10.1. Điều hướng có thể ảnh hưởng ngữ cảnh bảo mật khác

- Điều hướng đến một URL khác có thể đổi origin tài liệu, làm thay đổi quyền đọc DOM và storage.
- Khi mở tab/window mới tới bên không tin cậy, cân nhắc `rel="noopener"` cho liên kết `target="_blank"` để hạn chế quan hệ `window.opener` và nguy cơ tabnabbing.
- Có thể dùng CSP `navigate-to` nơi trình duyệt hỗ trợ, nhưng không nên xem là biện pháp duy nhất hoặc được hỗ trợ đồng đều. Logic kiểm tra đích đến vẫn phải đúng ở ứng dụng.
- Header `frame-ancestors` chống trang ngoài nhúng trang được bảo vệ; nó không giải quyết trực tiếp open redirect do fragment.

## 11. Bảo mật dữ liệu: fragment không phải nơi cất bí mật

Vì fragment không nằm trong HTTP request-target và thường bị loại khỏi `Referer`, đôi khi người ta lầm tưởng `#token=...` là nơi lưu token an toàn.

Sự thật cần xét toàn bộ vòng đời dữ liệu:

| Nơi dữ liệu có thể xuất hiện | Fragment có thể bị lộ? | Ghi chú |
| --- | --- | --- |
| HTTP request-target đến origin đích | **Không**, theo hành vi HTTP thông thường | Nhưng JavaScript có thể gửi nội dung fragment trong một request khác. |
| `Referer` header thông thường | Fragment bị loại | Không được suy ra bảo mật tuyệt đối. |
| Thanh địa chỉ, URL được copy/chia sẻ | **Có** | Người nhận liên kết thấy fragment. |
| JavaScript cùng môi trường trang | **Có** đối với fragment thông thường | Script bên thứ ba dạng `<script src>` có thể chạy trong origin của trang và đọc hash. |
| Browser history và trạng thái khôi phục | Có thể | Hành vi lưu trữ/đồng bộ phụ thuộc trình duyệt, thiết bị, cài đặt. |
| Analytics/error logging phía client | **Có nếu code thu thập** | `location.href` có thể bao gồm fragment; cần cấu hình loại bỏ dữ liệu nhạy cảm. |
| Extension hoặc môi trường browser bị xâm phạm | Có thể | SOP không thay thế bảo vệ môi trường endpoint. |

### 11.1. Bài học từ OAuth implicit flow

Trong một số luồng OAuth cũ, access token được trả về tại fragment trên redirect URI, ví dụ minh họa:

~~~text
https://app.example.test/callback#access_token=...&token_type=Bearer
~~~

Browser không tự gửi fragment ấy tới server nhận redirect, nhưng **JavaScript trong trang callback có thể đọc nó**. Điều này mở ra các rủi ro liên quan đến mã script trong trang, lịch sử URL, log phía client và sự phức tạp của luồng token.

Với ứng dụng hiện đại, thường ưu tiên **Authorization Code Flow với PKCE** theo kiến trúc OAuth phù hợp thay cho implicit flow. Các thông tin xác thực phải được xử lý theo mô hình bảo mật đã thiết kế, giới hạn thời gian sống/phạm vi và tránh hiện diện lâu trong URL hiển thị.

Nếu đã có một luồng hợp lệ nhận thông tin nhạy cảm trong fragment, ứng dụng cần xử lý một cách có kiểm soát và **xóa fragment khỏi URL hiển thị sớm** khi phù hợp:

~~~js
const clean = new URL(location.href);
clean.hash = "";
history.replaceState(history.state, "", clean);
~~~

Đây chỉ là thao tác giảm việc lưu/hiển thị fragment **sau thời điểm xử lý**; nó không đảo ngược rủi ro nếu một script đã đọc nội dung trước đó. Không dùng đoạn mã này như một giải pháp thay thế thiết kế xác thực an toàn.

### 11.2. Không dùng fragment làm chứng thực backend

Backend không nhận fragment trong request-target của navigation thông thường. Vì vậy server **không** thể dựa vào việc trang đang ở `#admin` hoặc `#verified` để quyết định quyền. Nếu ứng dụng chủ động gửi nội dung fragment trong API request, server vẫn phải coi đó là **input không tin cậy**, không phải bằng chứng danh tính.

## 12. Fragment, referrer, lịch sử và telemetry

Có ba lớp thường bị trộn lẫn:

1. **HTTP URL mà server thấy:** thông thường không có fragment.
2. **URL hiển thị trong trình duyệt và JS:** có thể bao gồm fragment.
3. **Dữ liệu được JavaScript xuất sang hệ thống khác:** phụ thuộc code ứng dụng, có thể tự truyền fragment qua query, JSON body, analytics hoặc lỗi.

Ví dụ không nên dùng nguyên trạng trong ứng dụng có token/PII trên URL:

~~~js
// Không nên thu thập URL đầy đủ mà không xem xét dữ liệu riêng tư:
const report = {
  url: location.href
};
// Gửi report cho analytics có thể vô tình gửi cả fragment.
~~~

Thay vào đó, chỉ ghi những trường phục vụ đo lường và đã được thiết kế an toàn:

~~~js
const report = {
  pathname: location.pathname,
  action: "page-view"
  // Không tự động thêm location.hash hoặc location.href.
};
~~~

Ứng dụng có thể cần biết hash route phục vụ analytics, nhưng nên map thành **tên route có kiểm soát** như `"orders"` thay vì gửi toàn bộ fragment chứa dữ liệu do người dùng kiểm soát.

### 12.1. Redirect và fragment cần được kiểm tra trên browser thật

Một số quy tắc redirect HTTP có thể **kế thừa fragment từ URL trước** khi `Location` không chỉ định fragment mới. Do đó một luồng chuyển hướng có thể khiến fragment của URL ban đầu xuất hiện ở URL đích trên thanh địa chỉ dù request HTTP không trực tiếp gửi fragment. Hành vi cụ thể phải kiểm chứng theo URL/redirect chain thực tế.

Khi xây luồng login/logout hoặc chuyển trang, cần thiết kế rõ fragment được giữ, thay thế hay loại bỏ, và tránh chuyển tiếp bí mật sang trang ngoài ý muốn. Không giả định một phản hồi `302` đơn thuần sẽ xóa fragment cũ.

## 13. Fragment và các biện pháp bảo vệ bổ sung

| Rủi ro hoặc yêu cầu | SOP giúp gì? | Lớp bảo vệ phù hợp |
| --- | --- | --- |
| Link bên ngoài đặt fragment chứa markup | SOP không xác định dữ liệu này là tin cậy | API DOM an toàn, validation, sanitize đúng ngữ cảnh, CSP, Trusted Types. |
| Hash route bật giao diện quản trị | Cùng origin dù hash đổi | Authentication và authorization ở backend, kiểm tra ownership từng API. |
| Dùng hash làm đích redirect | Không kiểm soát URL do ứng dụng chọn | Allowlist đích, kiểm tra scheme/origin, confirmation khi cần. |
| Fragment chứa token hoặc mã cá nhân | Fragment không gửi trong request-target | Thiết kế auth an toàn, tránh token trong URL, không log, giảm thời gian tồn tại. |
| Trang bị nhúng và người dùng bị lừa click | SOP chặn nhiều kiểu đọc cross-origin nhưng không cấm nhúng tuyệt đối | CSP `frame-ancestors`, `X-Frame-Options` khi phù hợp, kiểm tra hành động nhạy cảm. |
| Hash route gọi API cross-origin | SOP/CORS chi phối quyền đọc response trong browser | CORS cấu hình đúng, CSRF khi cần, authentication/authorization ở backend. |
| Tích hợp iframe gửi thông điệp | SOP chặn đọc DOM trực tiếp | `postMessage` với `targetOrigin` cụ thể, kiểm tra `event.origin`, `event.source` và schema. |
| Script CDN đọc fragment | Script thường chạy trong origin trang nhúng | Kiểm soát dependency, CSP, SRI và cách ly widget ít tin cậy. |

### 13.1. Hash khác với `postMessage`

Từng có những kỹ thuật truyền trạng thái giữa các tài liệu bằng cách thay fragment URL của iframe. Với ứng dụng hiện đại, cần phân biệt:

- **Fragment:** một phần của URL; thường phục vụ navigation, anchor hoặc route nội bộ.
- **`postMessage`:** API trao đổi thông điệp giữa các window/context, cho phép kiểm tra origin bên gửi và chọn origin đích.

Nếu hai tài liệu cross-origin cần giao tiếp, nên thiết kế giao thức `postMessage` nhỏ gọn, xác minh `event.origin`, `event.source` và schema, không dựa vào hash để truyền bí mật hoặc “vượt SOP”.

## 14. Thực hành A — Quan sát fragment trong DevTools

Thực hiện trên một trang local hoặc staging do bạn kiểm soát. Một file HTML được phục vụ qua `http://localhost:3000` sẽ giúp dễ xem các sự kiện và Network; tránh dựa vào chính sách đặc biệt của `file:`.

Tạo nội dung thử nghiệm:

~~~html
<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <title>Thử nghiệm URL fragment</title>
  <style>
    section { min-height: 50vh; padding: 1rem; }
    :target { outline: 2px solid; }
  </style>
</head>
<body>
  <nav>
    <a href="#alpha">Mục Alpha</a>
    <a href="#beta">Mục Beta</a>
  </nav>

  <p>Fragment hiện tại: <output id="hash"></output></p>
  <section id="alpha"><h2>Alpha</h2></section>
  <section id="beta"><h2>Beta</h2></section>

  <script>
    function showHash() {
      document.querySelector("#hash").textContent = location.hash;
    }

    addEventListener("hashchange", (event) => {
      console.log("hashchange", event.oldURL, event.newURL);
      showHash();
    });

    showHash();
  </script>
</body>
</html>
~~~

### Quan sát từng bước

1. Mở trang ở `http://localhost:3000/fragment-lab.html`.
2. Bật **DevTools → Network**, chọn mục **Doc** nếu có và giữ log để quan sát.
3. Nhấp **Mục Beta**; ghi nhận thanh địa chỉ có `#beta`, vị trí cuộn, sự kiện `hashchange`.
4. Trong Network, kiểm tra không có request `GET /fragment-lab.html#beta`. Nếu có request tài liệu khác, kiểm tra script và điều hướng đã diễn ra.
5. Tại Console, chạy `location.hash = "alpha"`, sau đó nhấn **Back** và **Forward** để quan sát history.
6. So sánh `location.origin` và `location.href` trước/sau thay fragment.

**Kết luận mong đợi:** Fragment có thể thay đổi điều hướng, URL và lịch sử phía client mà không làm thay đổi origin hoặc trở thành một phần HTTP request-target.

## 15. Thực hành B — Đối chiếu `hashchange` với History API

Dùng cùng trang thử ở mục 14. Trong Console:

~~~js
window.addEventListener("hashchange", () => {
  console.log("Đã nhận hashchange");
});

location.hash = "alpha";
~~~

Để quan sát chắc chắn, hãy bắt đầu từ một fragment **khác** `#alpha`; nếu gán cùng fragment hiện tại, hành vi có thể không tạo thay đổi đáng quan sát.

Tiếp theo:

~~~js
const updated = new URL(location.href);
updated.hash = "beta";

history.pushState({ demo: true }, "", updated);
console.log(location.hash); // "#beta"
~~~

Mặc dù URL đổi thành `#beta`, thao tác `pushState` **không tự phát `hashchange`**. Ứng dụng cần chủ động cập nhật UI dựa trên router state nếu muốn render tức thì.

Thử tiếp:

~~~js
const current = new URL(location.href);
current.hash = "alpha";

history.replaceState(history.state, "", current);
console.log(location.hash); // "#alpha"
~~~

`replaceState` thay thế mục lịch sử hiện tại, không phải thêm một mục mới. Khi dùng Back/Forward sau các thao tác, quan sát sự kiện history có thể khác so với chỉ thay `location.hash`.

**Câu hỏi tự đánh giá:** Nếu router của bạn chỉ lắng nghe `hashchange` nhưng lại sử dụng `history.pushState` để đổi URL, có thể xuất hiện lỗi gì? — Giao diện có thể không đồng bộ ngay với URL mới.

## 16. Thực hành C — Chứng minh fragment không gửi trong HTTP request

Chuẩn bị một HTTP server thử nghiệm ở `http://localhost:4000` trả phản hồi cho `GET /demo` và ghi lại request-target.

Mở trực tiếp trên thanh địa chỉ:

~~~text
http://localhost:4000/demo#private-note
~~~

Kiểm tra request ở **Network** và log server:

~~~http
GET /demo HTTP/1.1
Host: localhost:4000
~~~

Server không nhận `#private-note` qua request-target. Trong Console của trang `/demo`, có thể đọc:

~~~js
console.log(location.pathname); // "/demo"
console.log(location.hash);     // "#private-note"
~~~

Tiếp theo, chỉ để minh họa việc **JavaScript có thể tự gửi fragment**, từ cùng trang thử gọi:

~~~js
const fragment = location.hash.slice(1);

await fetch("/debug-fragment", {
  method: "POST",
  headers: { "Content-Type": "text/plain" },
  body: fragment
});
~~~

Nếu endpoint `/debug-fragment` được máy chủ thử nghiệm triển khai, nó sẽ nhận chuỗi `private-note` do **code phía client chủ động gửi**, chứ không phải do trình duyệt tự đưa fragment vào request-target.

**Kết luận mong đợi:** Không có mâu thuẫn giữa hai quan sát “fragment không gửi trong navigation HTTP” và “máy chủ có thể nhận fragment do JavaScript gửi lại”. Đây là hai luồng dữ liệu khác nhau.

## 17. Thực hành D — Phát hiện DOM XSS source/sink mà không cần chạy mã nguy hiểm

Trên trang thử của bạn, tạo:

~~~html
<div id="unsafe-demo"></div>
<div id="safe-demo"></div>
~~~

Sau đó dùng một fragment **chỉ chứa markup vô hại**:

~~~text
#%3Cb%3Ehello%3C%2Fb%3E
~~~

Trong Console:

~~~js
const value = decodeURIComponent(location.hash.slice(1));

document.querySelector("#unsafe-demo").innerHTML = value;
document.querySelector("#safe-demo").textContent = value;
~~~

Quan sát:

- `innerHTML` tạo phần tử `<b>` và trình duyệt hiển thị chữ đậm, chứng tỏ dữ liệu đã được **diễn giải là HTML**.
- `textContent` hiển thị chuỗi ký tự `<b>hello</b>`, không sinh phần tử HTML từ dữ liệu.

Đây là bằng chứng về **đường đi source → sink**, chưa cần chạy script tấn công. Trong ứng dụng thật, dữ liệu không tin cậy được đưa vào `innerHTML` có thể dẫn tới DOM XSS và cần sửa tại sink. Hãy ghi lại kết quả bằng ảnh DevTools Elements và không triển khai đoạn demo `innerHTML` lên production.

## 18. Bài tập tình huống tổng hợp

Một ứng dụng bán hàng có các URL:

~~~text
https://shop.example.test/#/products/42
https://shop.example.test/#/account
https://shop.example.test/#/admin
~~~

Ứng dụng đọc `location.hash` để quyết định hiển thị màn hình, tải nội dung từ `https://api.example.test` và có thêm widget bên thứ ba.

Giả sử đội phát triển tạo ba quyết định:

1. “Chỉ người có URL `#/admin` mới thấy nút quản trị; vậy ta có thể cho API tin rằng họ là admin.”
2. “SOP sẽ ngăn mọi nguồn bên ngoài thay đổi fragment vì fragment nằm cùng origin.”
3. “Token từ `#token=...` không xuất hiện ở server log; vậy nó an toàn với mọi script.”

**Phân tích:**

- **Quyết định 1 sai:** fragment do người dùng tự sửa được, không phải quyền. Backend phải xác thực và phân quyền từng request quản trị, đồng thời kiểm tra CSRF và nghiệp vụ khi cần.
- **Quyết định 2 sai:** người ngoài có thể gửi liên kết tới trang chính với fragment do họ chọn; SOP không xác thực nội dung hash. Nếu code frontend render hash bằng `innerHTML` còn có nguy cơ DOM XSS.
- **Quyết định 3 sai:** script chạy trong trang có thể đọc fragment; rủi ro tồn tại qua script bên thứ ba, analytics, URL được chia sẻ hoặc lịch sử. Mô hình xác thực nên tránh để token tồn tại trong fragment khi không cần thiết và chọn luồng an toàn hơn.

**Thiết kế đề xuất:** Hash router có route allowlist; render bằng API DOM an toàn; backend kiểm tra quyền; CORS cho đúng origin frontend; cookie cấu hình hợp lý, có chống CSRF khi dùng cookie phiên; CSP/Trusted Types/SRI cho rủi ro script; phân tách widget ít tin cậy bằng iframe nếu cần; và telemetry loại bỏ dữ liệu URL nhạy cảm.

## 19. Checklist review URL fragment trong ứng dụng

- [ ] Xác định chính xác đâu là path/query/fragment; không phân tích URL bằng cắt chuỗi tùy tiện.
- [ ] Xác nhận backend **không dựa vào fragment** để định danh tài nguyên hoặc kiểm tra quyền.
- [ ] Phân biệt `location.hash` do bên ngoài kiểm soát với dữ liệu tin cậy; giới hạn độ dài và parse theo schema.
- [ ] Đối với text, dùng `textContent`; đối với HTML bắt buộc, dùng sanitize đúng ngữ cảnh.
- [ ] Kiểm tra CSP, Trusted Types và nguồn script bên thứ ba có quyền đọc fragment.
- [ ] Không để fragment điều khiển redirect tùy ý, nhất là đến scheme hoặc origin ngoài allowlist.
- [ ] Tránh chứa token, mật khẩu, mã riêng tư trong fragment; rà soát browser history và telemetry.
- [ ] Đảm bảo API vẫn kiểm tra authentication, authorization, CSRF và không tin vào hash route.
- [ ] Nếu dùng hash router, kiểm tra sâu liên kết, tải lại trang, Back/Forward, `hashchange` và History API.
- [ ] Đo hành vi bằng Network và Console: request-target không có hash; nếu server nhận hash, truy nguồn JavaScript đã chuyển tiếp nó.
- [ ] Khi có iframe hoặc trang đối tác, kiểm tra `frame-ancestors`, `sandbox`, `postMessage` và chính sách nguồn script đúng chức năng.
- [ ] Kiểm thử phân biệt `#`, `%23`, fragment mã hóa và giá trị không hợp lệ.

### Những nhầm lẫn phổ biến

| Nhận định | Đánh giá | Giải thích |
| --- | --- | --- |
| “`#section` làm đổi origin.” | **Sai** | Origin chỉ dựa vào scheme, host, port đối với HTTP(S). |
| “Browser gửi `#section` trong HTTP request line.” | **Sai** | Fragment bị loại khỏi request-target thông thường. |
| “Server hoàn toàn không thể thấy fragment.” | **Sai** | Script hoặc luồng khác có thể chủ động gửi lại fragment. |
| “Fragment an toàn vì không nằm trong `Referer`.” | **Sai** | JavaScript, URL chia sẻ, history và telemetry vẫn có thể thấy. |
| “Đổi `location.hash` luôn tải lại cả trang.” | **Sai** | Thường là same-document navigation. |
| “`history.pushState` đổi hash thì `hashchange` tự chạy.” | **Sai** | API này không tự phát `hashchange`. |
| “`#/admin` là vùng bảo mật riêng.” | **Sai** | Cùng origin và có thể sửa hash bằng tay. |
| “`location.hash` không thể gây DOM XSS.” | **Sai** | Dữ liệu hash có thể đi vào sink HTML nguy hiểm. |
| “`encodeURIComponent` tự đảm bảo không có XSS.” | **Sai** | An toàn phụ thuộc ngữ cảnh sử dụng và sink. |
| “SOP không cho người khác gửi link với hash bất kỳ.” | **Sai** | Link ngoài có thể chọn fragment trong URL đích. |
| “Iframe và trang chính cùng URL path nhưng khác hash nên bị SOP cách ly.” | **Sai** | Hash không định danh origin; việc cách ly cần cơ chế khác. |

## 20. Tổng kết kiến thức

Có ba nguyên tắc cần giữ khi phân tích URL fragment:

1. **Fragment là thông tin điều hướng phía client:** nó có thể thay đổi điểm cuộn, trạng thái UI, hash route và lịch sử trình duyệt, nhưng không tham gia bộ ba origin và không xuất hiện trong HTTP request-target thông thường.
2. **Fragment là input không tin cậy:** người dùng hoặc một liên kết bên ngoài có thể chọn giá trị hash. Chỉ cần một `innerHTML`, redirect không kiểm soát hoặc lời gọi API tự động thiếu kiểm tra là có thể chuyển input này thành lỗi bảo mật.
3. **Không nhầm phạm vi trách nhiệm:** SOP/CORS quản lý những quyền đọc/trao đổi cross-origin trong trình duyệt; CSP và Trusted Types hỗ trợ giảm rủi ro thực thi code từ dữ liệu; cookie/CSRF và backend authentication/authorization bảo vệ phiên và quyền nghiệp vụ; security headers cho iframe/nhúng giải quyết ranh giới giao diện.

Khi phân tích bất kỳ ứng dụng nào có `#` trong URL, hãy hỏi: **ai có thể đặt fragment này, script nào đọc nó, nó được đưa vào sink hoặc request nào, và bước xác minh cuối cùng nằm ở đâu?** Trả lời được bốn câu hỏi đó giúp điều hướng hoạt động đúng mà vẫn giữ ranh giới bảo mật rõ ràng.
