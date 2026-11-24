# Credentialless iframe

**Credentialless iframe** là cơ chế cho phép tải tài liệu trong một iframe bằng một **ngữ cảnh tạm thời (ephemeral context)**, tách khỏi cookie, network state và storage thông thường của origin được nhúng. Iframe không dùng lại trạng thái đăng nhập hoặc dữ liệu lưu trữ đã có của origin đó. Ngữ cảnh tạm thời tồn tại trong vòng đời của tài liệu top-level đang nhúng nó; khi người dùng rời trang hoặc tải lại trang top-level, ngữ cảnh cũ không còn được dùng.

Cơ chế này đặc biệt hữu ích khi một trang đã bật **Cross-Origin Embedder Policy (COEP)** cần nhúng nội dung cross-origin từ bên thứ ba chưa tự triển khai COEP. Khi đặt thuộc tính **credentialless** trên iframe, browser có thể nới quy tắc COEP cho chính iframe đó và tải tài liệu trong ngữ cảnh không dùng credential/storage thông thường. Đổi lại, iframe thường chỉ hiển thị phiên bản công khai hoặc mặc định của nội dung.

Credentialless iframe không biến tài liệu thành cùng-origin với trang cha, không cho phép đọc DOM cross-origin và không phải cơ chế sandbox tổng quát. Nó cũng không phù hợp với nội dung cần đăng nhập, dữ liệu cá nhân, OAuth popup hoặc trạng thái phải tồn tại qua lần tải trang.

Bài học thuộc chương **Iframe** trong module **Browser Security** (SECURITY_APPLICATION_SECURITY_BROWSER_SECURITY). Nội dung phân tích ranh giới browser, origin, cookie và ứng dụng web; tập trung vào credentialless iframe, COOP/COEP, storage isolation, SOP và cách kiểm chứng hành vi thực tế.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích credentialless iframe và lý do cơ chế này tạo một ephemeral context.
2. Phân biệt cookie/storage thông thường của origin với trạng thái tạm thời trong credentialless context.
3. Mô tả cách credentialless iframe hỗ trợ trang đã bật COEP nhúng tài liệu cross-origin chưa opt-in COEP.
4. Phân biệt thuộc tính iframe credentialless với response header Cross-Origin-Embedder-Policy: credentialless.
5. Giải thích những gì credentialless iframe không thay đổi: origin, SOP, quyền đọc DOM, CSP, sandbox và authorization.
6. Nhận diện các giới hạn như popup, OAuth, autofill, password manager và dữ liệu lưu trữ mất sau khi rời trang.
7. Dùng feature detection và kiểm tra window.credentialless để xác định hành vi browser.
8. Thực hành so sánh iframe thông thường với credentialless iframe bằng Node.js và DevTools.

## 2. Vì sao cần credentialless iframe?

Một số Web API có quyền năng cao hơn, ví dụ SharedArrayBuffer và các phép đo thời gian có độ phân giải cao. Các API này có thể làm tăng rủi ro side-channel như Spectre, vì vậy browser yêu cầu trang chủ động bật **cross-origin isolation** trước khi sử dụng trong nhiều tình huống.

Một cấu hình phổ biến để trang top-level đạt cross-origin isolation là:

~~~http
Cross-Origin-Opener-Policy: same-origin
Cross-Origin-Embedder-Policy: require-corp
~~~

COOP: same-origin tách browsing context của trang khỏi các cửa sổ cross-origin không cùng chính sách. COEP: require-corp yêu cầu tài nguyên cross-origin được nhúng phải cho phép việc sử dụng qua CORS hoặc Cross-Origin-Resource-Policy (CORP), tùy loại request và tài nguyên.

Điều này có thể gây khó khăn khi trang cần nhúng một widget hoặc tài liệu bên thứ ba không gửi COEP/CORP phù hợp. Ví dụ:

- Một trang hướng dẫn công khai từ nhà cung cấp khác.
- Widget bản đồ hoặc biểu đồ chỉ hiển thị dữ liệu công khai.
- Một tài liệu demo không cần biết người dùng đang đăng nhập ở website của nhà cung cấp.

Nếu nội dung đó không cần cookie, tài khoản hoặc storage đã có của origin bên thứ ba, có thể tải nó trong credentialless iframe. Browser tạo ngữ cảnh tạm thời và nới điều kiện COEP cho iframe đó.

### 2.1. Luồng hoạt động

~~~mermaid
flowchart TD
    A["Trang top-level"] --> B["COOP: same-origin"]
    B --> C["COEP: require-corp"]
    C --> D{"Nhúng tài liệu cross-origin"}
    D -->|Tài liệu có COEP/CORP/CORS phù hợp| E["Nhúng theo quy tắc COEP thông thường"]
    D -->|Tài liệu bên thứ ba chưa opt-in COEP| F{"Nội dung có cần credential/storage thật?"}
    F -->|Có| G["Thiết kế tích hợp khác<br/>hoặc yêu cầu bên thứ ba opt-in"]
    F -->|Không| H["Đặt credentialless trên iframe"]
    H --> I["Tạo ephemeral context"]
    I --> J["Không dùng lại cookie/network state<br/>và storage thông thường của origin"]
    J --> K["Tài liệu được nhúng trong COEP page"]
~~~

Credentialless là một lựa chọn có chủ đích cho nội dung không cần trạng thái cá nhân. Không nên bật nó cho mọi iframe chỉ để làm biến mất lỗi COEP.

## 3. Credentialless iframe là gì?

Một iframe thông thường tải tài liệu trong browsing context của nó và có thể sử dụng credential/storage phù hợp với origin, cookie policy và các cơ chế phân vùng của browser. Khi iframe có thuộc tính credentialless, browser tải tài liệu trong một context mới, tạm thời và không truy cập trạng thái thông thường của origin đó.

Ví dụ:

~~~html
<iframe
  src="https://widget.example.com/public/embed"
  credentialless
  title="Widget công khai"
  width="640"
  height="360"></iframe>
~~~

Trong browser hỗ trợ, tài liệu bên trong iframe:

- Không dùng cookie thông thường đã lưu cho origin của tài liệu.
- Không truy cập localStorage, IndexedDB và storage thông thường của origin đó.
- Sử dụng storage/network context tạm thời riêng, gắn với vòng đời tài liệu top-level đang nhúng.
- Có thể tạo trạng thái tạm thời trong context này; trạng thái đó có thể được chia sẻ với credentialless iframe cùng origin nằm dưới cùng top-level document theo quy tắc của cơ chế.
- Mất context khi top-level document bị tải lại hoặc người dùng rời khỏi trang.

Điều này khác với việc xóa cookie hoặc mở cửa sổ ẩn danh. Browser tạo một context phục vụ riêng cho iframe trong trang hiện tại; không thay đổi dữ liệu profile thông thường của người dùng.

### 3.1. Credentialless không có nghĩa là không có trạng thái nào

Từ credentialless dễ khiến người học nghĩ iframe hoàn toàn không có cookie hay storage. Cách hiểu chính xác hơn là iframe không dùng lại **trạng thái thông thường gắn với origin**. Ngữ cảnh tạm thời vẫn có thể có storage riêng trong thời gian sống của top-level document.

Ví dụ, một credentialless iframe có thể ghi một giá trị vào localStorage tạm thời. Nếu một credentialless iframe cùng origin khác nằm trong cùng cây top-level document, nó có thể dùng chung context tạm thời đó. Khi tải lại trang top-level, context mới được tạo và giá trị cũ không còn.

Nếu một tài liệu credentialless tạo iframe con, chế độ credentialless được kế thừa trong cây iframe con đó, kể cả khi iframe lồng bên trong không tự khai báo thuộc tính. Vì vậy, khi tích hợp widget nhiều lớp, cần đánh giá cả các iframe lồng nhau thay vì chỉ kiểm tra element đầu tiên.

### 3.2. Trạng thái được chia sẻ trong phạm vi nào?

| Tình huống | Trạng thái thông thường của origin | Ephemeral context |
| --- | --- | --- |
| Mở trang origin đó trực tiếp | Có thể truy cập theo cookie/storage policy | Không phải credentialless context |
| Iframe thường của origin đó | Có thể dùng credential/storage nếu browser policy cho phép | Không |
| Credentialless iframe | Không dùng lại trạng thái thông thường | Có context tạm thời |
| Credentialless iframe cùng origin, cùng top-level document | Không truy cập storage thông thường | Có thể chia sẻ ephemeral context |
| Credentialless iframe sau khi top-level reload | Trạng thái thông thường vẫn theo policy | Context mới; dữ liệu tạm cũ không còn |
| Credentialless iframe sau khi rời trang | Trạng thái thông thường vẫn theo policy | Context cũ kết thúc theo vòng đời của top-level document |

Không dùng ephemeral storage làm nơi lưu dữ liệu cần tồn tại lâu dài, đồng bộ giữa thiết bị hoặc khôi phục sau reload.

## 4. Tác động tới cookie, network và storage

### 4.1. Cookie

Iframe credentialless không gửi cookie thông thường của origin được nhúng như một iframe có trạng thái đăng nhập. Vì vậy tài liệu bên thứ ba không tự nhận được phiên đăng nhập sẵn có của người dùng ở website đó.

Hệ quả:

- Widget có thể hiển thị phiên bản công khai thay vì dashboard cá nhân.
- Trang yêu cầu đăng nhập có thể chuyển sang trang login hoặc trả nội dung chưa xác thực.
- Cookie được tạo trong ephemeral context không trở thành cookie thông thường của profile.
- Không thể dùng credentialless iframe như cách đăng nhập ẩn danh vào một tài khoản đã có.

Cookie do tài liệu tạo trong ephemeral context chỉ thuộc context tạm thời theo cơ chế của browser. Nó không làm thay đổi cookie jar thông thường của origin.

### 4.2. Network request

Các request từ credentialless context không dùng lại credential/network state thông thường của origin. Server bên thứ ba có thể nhận request không có cookie phiên vốn có, nên phản hồi thường là nội dung công khai.

Credentialless không làm request biến mất khỏi mạng. Server vẫn có thể nhận:

- URL và path được yêu cầu.
- Địa chỉ IP và metadata kết nối mà browser/network cung cấp.
- User-Agent hoặc Client Hints theo chính sách browser.
- Referer nếu Referrer-Policy cho phép gửi.
- Dữ liệu được truyền tường minh trong URL, form, message hoặc request body.

Do đó, credentialless iframe **không phải công cụ ẩn danh** và không tự loại bỏ việc theo dõi dựa trên IP, URL hoặc fingerprinting.

### 4.3. Web Storage và IndexedDB

Iframe credentialless không truy cập storage thông thường của origin:

- localStorage
- sessionStorage
- IndexedDB
- Các storage API khác theo context và browser implementation

Browser tạo trạng thái tạm thời riêng cho context. Không nên dựa vào việc ephemeral storage tồn tại qua lần tải lại top-level hoặc qua lần điều hướng sang trang khác.

### 4.4. Cache và dữ liệu lưu khác

Credentialless tập trung vào credential/network state và storage của browsing context. Không nên suy ra rằng mọi dấu vết mạng hoặc cache ở mọi tầng đều bị xóa ngay lập tức. Cache HTTP, cache của service worker, DNS cache và cache ở proxy/CDN có quy tắc riêng. Khi đánh giá riêng tư hoặc dữ liệu nhạy cảm, cần xem xét các lớp cache và chính sách cache response độc lập.

## 5. Quan hệ với COOP, COEP và cross-origin isolation

Credentialless iframe được thiết kế để giải quyết một tình huống triển khai COEP: trang chủ đã opt-in vào cross-origin isolation nhưng muốn nhúng tài liệu cross-origin chưa tự gửi COEP.

### 5.1. COOP

Cross-Origin-Opener-Policy kiểm soát việc tài liệu chia sẻ browsing context group và mối quan hệ opener với cửa sổ cross-origin. Một giá trị thường dùng để đạt cross-origin isolation là:

~~~http
Cross-Origin-Opener-Policy: same-origin
~~~

COOP không tạo ephemeral storage cho iframe. Nó xử lý ranh giới giữa các browsing context/window.

### 5.2. COEP

Cross-Origin-Embedder-Policy quy định điều kiện để tài liệu tải và nhúng tài nguyên cross-origin. Hai giá trị thường gặp:

| Giá trị | Ý nghĩa khái quát |
| --- | --- |
| require-corp | Tài nguyên cross-origin cần được cho phép qua CORS hoặc CORP theo loại request |
| credentialless | Với một số request cross-origin ở chế độ no-CORS, browser bỏ credential và không yêu cầu CORP theo cùng cách; request có credential vẫn cần quyền rõ ràng phù hợp |

COEP có thể được dùng cùng COOP để đạt cross-origin isolation. Tùy ứng dụng, các tài nguyên cross-origin khác vẫn cần được kiểm tra và cấu hình đúng.

### 5.3. Credentialless iframe giải quyết phần nào?

Khi trang top-level có COEP, thuộc tính credentialless trên iframe cho phép browser tải tài liệu cross-origin trong ephemeral context và nới điều kiện COEP cho chính iframe đó. Tài liệu con không cần triển khai COEP chỉ để được nhúng theo luồng này.

Điều đó **không** có nghĩa:

- Toàn bộ trang top-level được bỏ qua COEP.
- Các script, image, worker hoặc fetch cross-origin khác tự động được cho phép.
- Tài liệu con được quyền đọc DOM của trang cha.
- Mọi iframe bên ngoài đều tự động an toàn.

### 5.4. crossOriginIsolated

Trang top-level có thể kiểm tra:

~~~js
console.log(window.crossOriginIsolated);
~~~

Giá trị true cho biết document đang chạy trong môi trường cross-origin isolated theo các điều kiện browser hỗ trợ. Việc đặt thuộc tính credentialless trên một iframe **không tự làm** trang top-level trở thành cross-origin isolated. Trang vẫn cần cấu hình COOP/COEP và đáp ứng các điều kiện liên quan.

## 6. Phân biệt thuộc tính iframe và response header COEP: credentialless

Hai tên gọi giống nhau nhưng tác động ở hai cấp độ khác nhau:

| Tiêu chí | iframe credentialless | Cross-Origin-Embedder-Policy: credentialless |
| --- | --- | --- |
| Vị trí | Thuộc tính boolean trên element iframe | HTTP response header của document |
| Phạm vi | Context của iframe và cây tài liệu con liên quan | Quy tắc embedder policy của document |
| Mục tiêu | Nhúng tài liệu cross-origin trong ephemeral context | Cho phép một số cross-origin no-CORS request không cần CORP bằng cách bỏ credential |
| Storage | Không dùng lại storage thông thường của origin trong iframe context | Không tự tạo ephemeral iframe context chỉ vì header có giá trị này |
| Cookie/credential | Iframe không dùng lại credential thông thường của origin | Với request no-CORS cross-origin thuộc phạm vi COEP credentialless, browser bỏ credential; request có credential cần quyền riêng |
| Trường hợp dùng | Nhúng iframe bên thứ ba chưa opt-in COEP | Cấu hình COEP ở cấp document cho tài nguyên cross-origin phù hợp |

Không thay thế lẫn nhau. Nếu mục tiêu là nhúng một tài liệu bên thứ ba chưa gửi COEP vào trang COEP, cần xem xét thuộc tính credentialless trên iframe. Nếu mục tiêu là chính sách request của document, hãy đọc kỹ COEP header và loại request đang được thực hiện.

## 7. Credentialless không thay thế SOP, CSP hoặc sandbox

### 7.1. Same-Origin Policy vẫn áp dụng

Credentialless iframe không biến origin của tài liệu con thành origin của trang cha. Nếu trang cha là https://app.example.com và iframe tải https://widget.example.net, hai tài liệu vẫn khác origin.

SOP vẫn hạn chế trang cha đọc DOM hoặc truy cập dữ liệu nội bộ của iframe cross-origin. Credentialless thay đổi context credential/storage và một số điều kiện embed, không cấp thêm quyền đọc dữ liệu cross-origin.

### 7.2. CSP vẫn cần thiết

CSP của trang cha vẫn có thể giới hạn iframe được tải bằng frame-src. CSP frame-ancestors trên tài liệu con vẫn kiểm soát ai được phép nhúng tài liệu đó. Credentialless không bỏ qua mọi CSP directive.

Ví dụ:

~~~http
Content-Security-Policy: default-src 'self'; frame-src https://widget.example.net; object-src 'none'; base-uri 'self'
~~~

frame-src quyết định trang cha có được tải iframe từ nguồn đó không. Thuộc tính credentialless điều khiển context của iframe; hai cơ chế có vai trò khác nhau.

### 7.3. iframe sandbox vẫn là cơ chế riêng

sandbox giới hạn khả năng của nội dung trong iframe, ví dụ script, form, popup hoặc top-level navigation tùy token được cấp. credentialless tập trung vào credential/storage context và COEP embedding.

Có thể kết hợp cả hai khi phù hợp:

~~~html
<iframe
  src="https://widget.example.net/embed"
  credentialless
  sandbox="allow-scripts"
  title="Widget công khai"></iframe>
~~~

Nhưng phải kiểm tra widget có hoạt động khi bị sandbox hạn chế hay không. Không thêm allow-same-origin, allow-popups hoặc token khác nếu không có nhu cầu đã được đánh giá. Credentialless không tự giới hạn script hoặc navigation như sandbox.

## 8. Giới hạn sản phẩm và trải nghiệm người dùng

Vì iframe không dùng lại credential/storage thông thường, một số luồng sản phẩm sẽ không hoạt động như iframe có trạng thái:

| Tính năng | Tác động thường gặp |
| --- | --- |
| Nội dung công khai | Phù hợp; iframe có thể hiển thị bản mặc định |
| Dashboard cá nhân | Không dùng được session cookie thông thường để tùy biến theo tài khoản |
| Login dựa trên cookie | Có thể yêu cầu đăng nhập nhưng phiên thông thường không được dùng lại |
| OAuth popup | Không phù hợp; popup mở từ credentialless iframe được xử lý như có noopener và không chia sẻ opener với iframe |
| Browser autofill | Không khả dụng theo hành vi được mô tả cho credentialless iframe |
| Password manager | Có thể không hoạt động trong credentialless iframe |
| Giỏ hàng hoặc trạng thái lưu lâu dài | Dữ liệu tạm không nên được kỳ vọng tồn tại qua reload/rời trang |
| Widget public/stateless | Thường phù hợp nếu không cần trạng thái cá nhân |

Popup được mở từ credentialless iframe được xử lý như có noopener: popup không giữ quan hệ opener thông thường với iframe. Điều này ngăn một số luồng popup/OAuth vốn cần trao đổi trạng thái qua window.opener. Hãy thiết kế một luồng tích hợp khác nếu cần xác thực.

Browser autofill và password manager cũng không khả dụng trong credentialless iframe theo hành vi được mô tả của tính năng. Hãy tránh nhúng form đăng nhập hoặc biểu mẫu cần tự điền trong context này.

## 9. Khi nào nên và không nên dùng?

### Nên cân nhắc

- Nhúng tài liệu hoặc widget công khai từ bên thứ ba chưa hỗ trợ COEP.
- Trang top-level cần cross-origin isolation để dùng API như SharedArrayBuffer.
- Nội dung bên thứ ba không cần tài khoản, cookie, lịch sử hoặc storage đã có của người dùng.
- Có thể chấp nhận việc trạng thái iframe chỉ tồn tại trong vòng đời trang top-level.
- Đã kiểm thử browser support và hành vi fallback.

### Không nên dùng

- Trang tài khoản, thanh toán, ngân hàng hoặc dashboard cần session người dùng.
- Widget cần cookie đăng nhập hoặc localStorage thông thường của nhà cung cấp.
- Luồng OAuth popup hoặc đăng nhập qua cửa sổ mới.
- Form cần browser autofill/password manager.
- Nội dung phải lưu trạng thái qua reload hoặc chia sẻ với lần truy cập độc lập.
- Tài liệu bên thứ ba có thể nhận dữ liệu nhạy cảm qua URL hoặc postMessage mà chưa có thiết kế bảo vệ.

Credentialless không biến một bên thứ ba không đáng tin thành bên đáng tin. Chỉ nhúng nội dung có nguồn gốc và chức năng đã được đánh giá; giới hạn dữ liệu truyền sang iframe.

## 10. Cách khai báo và kiểm tra hỗ trợ

### 10.1. Khai báo trực tiếp trong HTML

~~~html
<iframe
  src="https://public-widget.example/embed"
  credentialless
  title="Widget công khai"
  loading="lazy"
  referrerpolicy="strict-origin"
  width="800"
  height="450"></iframe>
~~~

credentialless là boolean attribute: có mặt nghĩa là bật. loading và referrerpolicy là các thuộc tính riêng, không phải một phần của credentialless.

### 10.2. Tạo iframe bằng JavaScript

Đặt property trước khi gán src để context được áp dụng ngay từ lần navigation đầu:

~~~js
function createCredentiallessFrame(container, url) {
  if (!('credentialless' in HTMLIFrameElement.prototype)) {
    throw new Error('Browser does not support credentialless iframe');
  }

  const frame = document.createElement('iframe');
  frame.credentialless = true;
  frame.title = 'Public embedded content';
  frame.loading = 'lazy';
  frame.referrerPolicy = 'strict-origin';
  frame.src = url;

  container.append(frame);
  return frame;
}
~~~

Không đặt src trước rồi mới bật credentialless, vì navigation đầu có thể đã bắt đầu trong context không mong muốn. Nếu cần thay đổi thuộc tính sau khi frame đã tải, hãy tạo/navigation lại theo cách được browser hỗ trợ và kiểm thử kết quả.

### 10.3. Feature detection

Ở trang cha:

~~~js
const supported = 'credentialless' in HTMLIFrameElement.prototype;

if (!supported) {
  console.warn('Credentialless iframe is unavailable in this browser.');
}
~~~

Trong tài liệu con:

~~~js
if (window.credentialless === true) {
  console.log('Document is running in a credentialless iframe context.');
} else {
  console.log('Document is not in a credentialless iframe context.');
}
~~~

window.credentialless có thể là undefined ở browser chưa triển khai API. Không xem giá trị undefined như bằng chứng rằng browser đã áp dụng chế độ credentialless.

### 10.4. Fallback phải theo yêu cầu sản phẩm

Tài liệu MDN hiện đánh dấu credentialless iframe là tính năng experimental và limited availability, chưa phải Baseline trên toàn bộ browser phổ biến. Hãy kiểm tra bảng tương thích của browser/version mà sản phẩm hỗ trợ; đừng suy ra hỗ trợ chỉ từ việc iframe thông thường hoạt động.

Nếu browser không hỗ trợ, không âm thầm bỏ thuộc tính rồi tải iframe như bình thường trong trang COEP. Tùy sản phẩm:

- Không nhúng nội dung và hiển thị thông báo tương thích.
- Dùng một trang trung gian do ứng dụng kiểm soát.
- Yêu cầu nhà cung cấp hỗ trợ COEP/CORP/CORS phù hợp.
- Dùng một phương án tích hợp khác đã được đánh giá về bảo mật.

Nếu nội dung chỉ an toàn khi không có credential, việc fallback sang iframe thường có thể làm thay đổi threat model. Cần fail closed hoặc yêu cầu lựa chọn rõ ràng.

## 11. Thực hành: so sánh iframe thường và credentialless iframe

Bài thực hành dùng **Node.js 18 trở lên**, không cần package ngoài. Lab chạy hai server trên cùng hostname localhost nhưng khác port:

- http://localhost:3000: trang cha.
- http://localhost:3001: tài liệu được nhúng.

Hai URL khác port nên khác origin, nhưng vẫn cùng site theo khái niệm schemeful site. Cookie không được phân vùng theo port, vì vậy lab có thể quan sát sự khác nhau giữa iframe thường và credentialless iframe mà không phải dựa vào cookie cross-site.

Lab đặt cookie demo và một giá trị localStorage khi mở trang con trực tiếp. Sau đó so sánh:

- Iframe thường có thể dùng lại cookie/storage của origin con theo chính sách browser.
- Credentialless iframe không dùng lại trạng thái thông thường đó và chạy trong ephemeral context.
- Trang cha có COOP/COEP để minh họa việc nhúng tài liệu con không tự triển khai COEP.

Cookie trong lab chỉ là dữ liệu giả, không chứa thông tin đăng nhập thật.

### 11.1. Tạo file credentialless-lab.mjs

~~~js
import { createServer } from 'node:http';

const seedPage =
  '<!doctype html><html lang="vi"><meta charset="utf-8">' +
  '<title>Seed regular child context</title>' +
  '<h1>Child origin seed</h1>' +
  '<p id="status">Đang khởi tạo dữ liệu demo...</p>' +
  '<script>' +
  "localStorage.setItem('regular-context-value', 'stored-in-normal-origin');" +
  "document.querySelector('#status').textContent =" +
  "'Đã tạo localStorage thông thường. Cookie demo được server đặt trong response.';" +
  '</script></html>';

function childPage(requestHadCookie) {
  const cookieText = requestHadCookie ? 'Có' : 'Không';
  return '<!doctype html><html lang="vi"><head><meta charset="utf-8">' +
    '<title>Child context probe</title>' +
    '<style>body{font:14px sans-serif;padding:12px;overflow-wrap:anywhere}' +
    'dt{font-weight:bold;margin-top:8px}dd{margin-left:0}</style></head><body>' +
    '<h2>Child origin probe</h2><dl>' +
    '<dt>window.credentialless</dt><dd id="credentialless"></dd>' +
    '<dt>Cookie demo có trong request tới server?</dt><dd>' + cookieText + '</dd>' +
    '<dt>document.cookie (cookie demo là HttpOnly)</dt><dd id="cookie"></dd>' +
    '<dt>localStorage thông thường đã seed?</dt><dd id="regular-storage"></dd>' +
    '<dt>Ephemeral visit counter</dt><dd id="counter"></dd></dl>' +
    '<script>' +
    "const isCredentialless = window.credentialless;" +
    "const previous = Number(localStorage.getItem('ephemeral-visit-counter') || '0');" +
    'const next = previous + 1;' +
    "localStorage.setItem('ephemeral-visit-counter', String(next));" +
    "document.querySelector('#credentialless').textContent = String(isCredentialless);" +
    "document.querySelector('#cookie').textContent = document.cookie || '(không có cookie đọc được)';" +
    "document.querySelector('#regular-storage').textContent =" +
    "localStorage.getItem('regular-context-value') || '(không tìm thấy)';" +
    "document.querySelector('#counter').textContent = String(next);" +
    '</script></body></html>';
}

const childServer = createServer((req, res) => {
  const path = new URL(req.url, 'http://localhost:3001').pathname;

  if (path === '/seed') {
    res.writeHead(200, {
      'Content-Type': 'text/html; charset=utf-8',
      'Set-Cookie': 'demo_regular=present; Path=/; HttpOnly; SameSite=Lax',
      'Cache-Control': 'no-store',
    });
    res.end(seedPage);
    return;
  }

  if (path === '/probe') {
    const cookieHeader = req.headers.cookie || '';
    const requestHadCookie =
      /(?:^|;\s*)demo_regular=present(?:;|$)/.test(cookieHeader);
    console.log('[child /probe] demo cookie sent:', requestHadCookie);

    res.writeHead(200, {
      'Content-Type': 'text/html; charset=utf-8',
      'Cache-Control': 'no-store',
    });
    res.end(childPage(requestHadCookie));
    return;
  }

  res.writeHead(404);
  res.end('Not found');
});

function parentPage(credentialless) {
  const heading = credentialless ? 'Credentialless iframe' : 'Iframe thông thường';
  const isolatedFrame = credentialless
    ? 'true'
    : 'false';
  const source = credentialless
    ? 'http://localhost:3001/probe'
    : 'http://localhost:3001/probe';

  return '<!doctype html><html lang="vi"><head><meta charset="utf-8">' +
    '<title>' + heading + '</title>' +
    '<style>body{font:16px sans-serif;margin:24px}' +
    'iframe{width:100%;height:340px;border:2px solid #777}</style></head><body>' +
    '<h1>' + heading + '</h1>' +
    '<p>Parent crossOriginIsolated: <strong id="isolated"></strong></p>' +
    '<p id="support"></p><div id="frame-container"></div>' +
    '<p><a href="http://localhost:3000/normal">Iframe thường</a> | ' +
    '<a href="http://localhost:3000/isolated">Credentialless iframe</a> | ' +
    '<a href="http://localhost:3001/seed">Seed lại dữ liệu origin con</a></p>' +
    '<script>' +
    "document.querySelector('#isolated').textContent = String(window.crossOriginIsolated);" +
    "const container = document.querySelector('#frame-container');" +
    "const support = document.querySelector('#support');" +
    'if (' + isolatedFrame + ') {' +
    "  if (!('credentialless' in HTMLIFrameElement.prototype)) {" +
    "    support.textContent = 'Browser không hỗ trợ credentialless iframe; lab không tải iframe theo chế độ thường.';" +
    '  } else {' +
    "    support.textContent = 'Browser hỗ trợ credentialless. Child được tải trong ephemeral context.';" +
    "    const frame = document.createElement('iframe');" +
    '    frame.credentialless = true;' +
    "    frame.title = 'Credentialless child probe';" +
    '    frame.src = ' + JSON.stringify(source) + ';' +
    '    container.append(frame);' +
    '  }' +
    '} else {' +
    "  support.textContent = 'Iframe thường dùng context thông thường của origin con theo browser policy.';" +
    "  const frame = document.createElement('iframe');" +
    "  frame.title = 'Normal child probe';" +
    '  frame.src = ' + JSON.stringify(source) + ';' +
    '  container.append(frame);' +
    '}' +
    '</script></body></html>';
}

createServer((req, res) => {
  const path = new URL(req.url, 'http://localhost:3000').pathname;

  if (path === '/normal') {
    res.writeHead(200, {
      'Content-Type': 'text/html; charset=utf-8',
      'Cache-Control': 'no-store',
    });
    res.end(parentPage(false));
    return;
  }

  if (path === '/isolated') {
    res.writeHead(200, {
      'Content-Type': 'text/html; charset=utf-8',
      'Cache-Control': 'no-store',
      'Cross-Origin-Opener-Policy': 'same-origin',
      'Cross-Origin-Embedder-Policy': 'require-corp',
    });
    res.end(parentPage(true));
    return;
  }

  res.writeHead(200, {
    'Content-Type': 'text/html; charset=utf-8',
    'Cache-Control': 'no-store',
  });
  res.end(
    '<!doctype html><html lang="vi"><meta charset="utf-8">' +
    '<h1>Credentialless iframe lab</h1><ol>' +
    '<li>Mở <a href="http://localhost:3001/seed">child /seed</a> trước.</li>' +
    '<li>Sau đó mở <a href="/normal">iframe thường</a>.</li>' +
    '<li>Cuối cùng mở <a href="/isolated">credentialless iframe</a>.</li>' +
    '</ol></html>'
  );
}).listen(3000, () => {
  console.log('Parent origin: http://localhost:3000');
});

childServer.listen(3001, () => {
  console.log('Child origin: http://localhost:3001');
});
~~~

### 11.2. Chạy và seed trạng thái origin con

Chạy:

~~~bash
node credentialless-lab.mjs
~~~

Mở http://localhost:3001/seed trực tiếp trong tab. Trang này:

1. Đặt cookie demo demo_regular=present với HttpOnly và SameSite=Lax.
2. Ghi regular-context-value vào localStorage của origin http://localhost:3001.

Cookie chỉ phục vụ quan sát request; không dùng mật khẩu, session ID hoặc dữ liệu cá nhân. Cookie không được đặt Secure vì lab chạy HTTP localhost; production phải dùng HTTPS và Secure.

### 11.3. Quan sát iframe thông thường

Mở http://localhost:3000/normal.

Trong browser không chặn trạng thái same-site của lab:

- Child có thể hiển thị window.credentialless là false hoặc giá trị false tương đương.
- Server child có thể ghi log cookie demo đã được gửi.
- Child có thể đọc regular-context-value trong localStorage.

Hai trang khác origin vì port khác nhau, nên parent không thể đọc DOM của iframe theo SOP. Tuy nhiên, iframe vẫn chạy trong context thông thường của origin con.

### 11.4. Quan sát credentialless iframe

Mở http://localhost:3000/isolated.

Trang cha trả:

~~~http
Cross-Origin-Opener-Policy: same-origin
Cross-Origin-Embedder-Policy: require-corp
~~~

Nếu browser hỗ trợ credentialless iframe:

- window.crossOriginIsolated ở parent thường là true nếu các điều kiện cross-origin isolation khác đều thỏa.
- Child hiển thị window.credentialless là true.
- Server child ghi log request không có cookie demo thông thường.
- Child không tìm thấy regular-context-value đã seed trong storage thông thường.
- Child tạo ephemeral-visit-counter trong context tạm thời.

Tải lại trang /isolated. Counter tạm thời trở về giá trị ban đầu vì top-level document mới tạo context mới. Trạng thái cookie/localStorage thông thường ở origin con vẫn tồn tại.

### 11.5. Quan sát bằng DevTools

- Mở Network và chọn request /probe để kiểm tra request headers.
- Xem log server child để biết cookie demo có được gửi hay không.
- Chọn iframe trong DevTools → Elements để quan sát thuộc tính và URL.
- Trong Console của parent, kiểm tra crossOriginIsolated.
- Trong Console của child frame, kiểm tra window.credentialless và localStorage.

Parent không thể đọc contentDocument của child cross-origin chỉ vì iframe là credentialless. Hãy chọn execution context của frame trong DevTools để quan sát trực tiếp.

### 11.6. Giới hạn và cách diễn giải kết quả

- Browser privacy setting, cookie policy và storage partitioning có thể ảnh hưởng kết quả của iframe thường. Nếu cookie/localStorage thông thường không được chia sẻ trong baseline, kiểm tra log và cấu hình browser trước khi kết luận.
- Cookie không được phân vùng theo port; hai origin localhost khác port vẫn dùng cùng host cookie. Điều này được tận dụng có chủ đích trong lab.
- Browser không hỗ trợ thuộc tính có thể bỏ qua credentialless; lab feature-detect và không tự tải iframe thường ở route isolated.
- Lab dùng HTTP localhost và cookie demo không có Secure; production cần HTTPS và cấu hình cookie phù hợp.
- Lab không triển khai xác thực hoặc dữ liệu nhạy cảm; không dùng cho hệ thống thật.

## 12. Các lỗi triển khai thường gặp

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Dùng credentialless cho dashboard cần đăng nhập | Iframe không nhận session cookie thông thường | Dùng tích hợp có xác thực phù hợp hoặc yêu cầu bên thứ ba hỗ trợ COEP |
| Nghĩ credentialless đồng nghĩa opaque origin | Thiết kế sai quyền đọc DOM và postMessage | SOP/origin vẫn phải được phân tích riêng |
| Đặt src trước khi bật credentialless | Navigation đầu có thể chạy trong context khác dự kiến | Đặt thuộc tính trước khi gán src |
| Không feature-detect | Browser không hỗ trợ có thể tải theo hành vi thường hoặc bị COEP chặn | Kiểm tra property và chọn fallback rõ ràng |
| Dùng URL chứa token hoặc PII | Dữ liệu vẫn được gửi tới server dù iframe credentialless | Không nhúng bí mật vào URL; giới hạn Referrer-Policy và payload |
| Mong cookie/storage tồn tại sau reload | Trạng thái tạm thời biến mất | Không lưu trạng thái lâu dài trong ephemeral context |
| Cho rằng mọi iframe con đều độc lập | Iframe con trong credentialless subtree kế thừa credentialless | Đánh giá cả cây iframe lồng nhau |
| Dùng popup OAuth | Popup không giữ quan hệ opener thông thường | Thiết kế luồng xác thực khác |
| Nhầm COEP header với iframe attribute | Áp dụng chính sách sai cấp độ | Phân biệt request policy của document và context của iframe |
| Bật credentialless để sửa mọi lỗi COEP | Tài nguyên khác vẫn có thể bị chặn hoặc tích hợp sai | Phân loại từng request/resource và sửa đúng policy |

## 13. Checklist đánh giá trước khi triển khai

1. **Xác định mục đích iframe:** nội dung công khai hay nội dung cá nhân hóa theo user?
2. **Xác định credential cần thiết:** widget có cần cookie, login, localStorage hoặc IndexedDB thông thường không?
3. **Kiểm tra COEP của parent:** trang có thực sự cần cross-origin isolation và header COOP/COEP đã đúng chưa?
4. **Chọn đúng cơ chế:** iframe attribute credentialless hay COEP response header credentialless?
5. **Feature detection:** browser mục tiêu có hỗ trợ HTMLIFrameElement.credentialless không?
6. **Đặt trước navigation:** bật thuộc tính trước khi gán src.
7. **Kiểm soát dữ liệu truyền:** không đưa token, session ID, PII hoặc dữ liệu nhạy cảm vào URL/query/postMessage không cần thiết.
8. **Kiểm tra nested iframe:** các iframe con có kế thừa credentialless và hoạt động đúng không?
9. **Kiểm tra popup:** luồng OAuth, login popup hoặc giao tiếp opener có bị ảnh hưởng không?
10. **Kiểm tra storage lifecycle:** dữ liệu tạm mất khi reload/rời trang có chấp nhận được không?
11. **Giữ SOP/CSP/sandbox:** kiểm tra quyền đọc DOM, frame-src, frame-ancestors và sandbox riêng.
12. **Thiết kế fallback:** browser không hỗ trợ thì dừng nhúng hoặc dùng giải pháp đã được đánh giá; không tự chuyển sang iframe có credential.
13. **Kiểm thử thực tế:** cookie request, localStorage, window.credentialless, crossOriginIsolated, Network và Console trên từng browser hỗ trợ.

## 14. Những nhầm lẫn cần tránh

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| “Credentialless iframe không có bất kỳ storage nào.” | Nó có ephemeral context riêng; dữ liệu tạm có thể dùng trong vòng đời top-level document. |
| “Credentialless iframe xóa cookie thật của người dùng.” | Cookie thông thường vẫn còn; iframe chỉ không dùng lại chúng trong context credentialless. |
| “Credentialless làm iframe cùng-origin với parent.” | Origin và SOP vẫn giữ nguyên; cross-origin DOM access vẫn bị giới hạn. |
| “Credentialless là iframe sandbox.” | Nó không tự giới hạn script, form, popup hoặc navigation như sandbox. |
| “Credentialless iframe làm request ẩn danh.” | Server vẫn có thể thấy IP, URL và metadata; dữ liệu truyền tường minh vẫn có thể bị lộ. |
| “Bật credentialless là parent đã cross-origin isolated.” | Parent vẫn cần COOP/COEP và đáp ứng các điều kiện cross-origin isolation khác. |
| “COEP: credentialless và iframe credentialless giống nhau.” | Một cái là response policy của document; một cái là thuộc tính tạo ephemeral context cho iframe. |
| “Credentialless iframe dùng được cho OAuth popup.” | Popup mở từ credentialless iframe được xử lý như có noopener, nên luồng phụ thuộc opener có thể không hoạt động. |
| “Browser không hỗ trợ thì bỏ thuộc tính cũng được.” | Bỏ thuộc tính có thể làm iframe tải với credential thông thường; fallback phải theo threat model. |
| “Mọi lỗi COEP đều sửa bằng credentialless.” | Cơ chế chỉ áp dụng cho iframe được đánh dấu; các resource/request khác vẫn theo COEP rules. |

## 15. Câu hỏi tự đánh giá

**Câu 1.** Credentialless iframe tạo ra thay đổi chính nào so với iframe thông thường?

**Gợi ý trả lời:** Nó tải tài liệu trong ephemeral context, không dùng lại cookie, network state và storage thông thường của origin được nhúng.

**Câu 2.** Vì sao credentialless iframe hữu ích với trang có COEP require-corp?

**Gợi ý trả lời:** Nó cho phép trang COEP nhúng một số tài liệu cross-origin chưa tự opt-in COEP bằng cách tải chúng trong context credentialless.

**Câu 3.** Dữ liệu trong ephemeral storage có tồn tại sau khi reload trang top-level không?

**Gợi ý trả lời:** Không nên kỳ vọng điều đó. Reload top-level tạo context mới; trạng thái tạm trước đó không còn được truy cập.

**Câu 4.** Credentialless iframe có làm SOP ngừng áp dụng không?

**Gợi ý trả lời:** Không. Origin vẫn khác nhau và parent không tự nhiên có quyền đọc DOM cross-origin.

**Câu 5.** window.credentialless dùng để làm gì?

**Gợi ý trả lời:** Tài liệu con có thể dùng thuộc tính này để biết nó đang chạy trong credentialless iframe context; browser chưa hỗ trợ có thể trả undefined.

**Câu 6.** Vì sao không nên dùng credentialless iframe cho OAuth popup?

**Gợi ý trả lời:** Popup mở từ credentialless iframe được xử lý như có noopener, nên không có quan hệ opener thông thường để trao đổi trạng thái OAuth.

**Câu 7.** Khác biệt giữa iframe attribute credentialless và COEP header credentialless là gì?

**Gợi ý trả lời:** Attribute tạo ephemeral context cho iframe; COEP header đặt chính sách embedder ở cấp document và ảnh hưởng cách xử lý một số cross-origin no-CORS request.

## Tài liệu tham khảo

- MDN — [IFrame credentialless](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/IFrame_credentialless).
- MDN — [HTMLIFrameElement.credentialless](https://developer.mozilla.org/en-US/docs/Web/API/HTMLIFrameElement/credentialless), [Window.credentialless](https://developer.mozilla.org/en-US/docs/Web/API/Window/credentialless).
- Chrome for Developers — [Iframe credentialless: Easily embed iframes in COEP environments](https://developer.chrome.com/blog/iframe-credentialless).
- MDN — [Cross-Origin-Embedder-Policy (COEP)](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Cross-Origin-Embedder-Policy), [Cross-Origin-Opener-Policy (COOP)](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Cross-Origin-Opener-Policy).
- WHATWG — [HTML Standard: embedder policy](https://html.spec.whatwg.org/multipage/browsers.html#embedder-policy).
