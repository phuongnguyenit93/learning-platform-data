# Strict-dynamic

**strict-dynamic** là một source expression của Content Security Policy (CSP) Level 3 dành cho **script-src**. Khi chính sách có nonce hoặc hash source hợp lệ cùng với strict-dynamic, browser có thể mở rộng niềm tin từ script gốc đã được cho phép sang các script mà script đáng tin cậy đó chủ động tạo và nạp động. Nhờ vậy ứng dụng có thể dùng một số script gốc được kiểm soát làm điểm khởi đầu, thay vì phải duy trì một danh sách host dài cho mọi script được tải tiếp theo.

Đây là cơ chế **truyền niềm tin**, không phải bộ lọc URL và cũng không tự động làm mọi script trên trang đáng tin cậy. Nếu script gốc có lỗ hổng hoặc tải URL do attacker kiểm soát, strict-dynamic có thể khiến script độc hại được nạp như một hậu duệ được tin cậy. Vì vậy, cần bảo vệ script gốc, kiểm soát chặt script loader, sinh nonce đúng vòng đời và kiểm thử CSP trên browser thực tế.

Bài học thuộc chương **CSP nâng cao** trong module **Browser Security** (SECURITY_APPLICATION_SECURITY_BROWSER_SECURITY). Nội dung phân tích ranh giới giữa browser, origin, cookie và ứng dụng web; tập trung vào CSP, XSS, script loading, Trusted Types và kiểm chứng hành vi thực tế.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích strict-dynamic và điều kiện để browser áp dụng cơ chế truyền niềm tin.
2. Phân biệt script gốc được tin cậy với script được tải động và script được parser chèn vào tài liệu.
3. Hiểu vai trò của nonce source, hash source và fallback cho browser cũ.
4. Nhận diện rủi ro khi script loader nhận URL hoặc tên script từ dữ liệu không tin cậy.
5. Thiết kế script loader dựa trên registry/allowlist do ứng dụng kiểm soát.
6. Quản lý nonce theo từng response, cache, template và log.
7. Kết hợp strict-dynamic với CSP directives khác, Subresource Integrity và Trusted Types.
8. Dùng Node.js và DevTools để kiểm tra script nào được thực thi hoặc bị browser chặn.

## 2. Vấn đề của allowlist host truyền thống

Một chính sách CSP truyền thống thường liệt kê các nguồn script:

~~~http
Content-Security-Policy: script-src 'self' https://cdn.example.com https://widgets.example.net
~~~

Browser cho phép tải script từ các nguồn được liệt kê. Cách này có thể hoạt động, nhưng danh sách host không luôn thể hiện được script nào thực sự đáng tin cậy:

- Một host CDN có thể phục vụ nhiều ứng dụng hoặc nhiều tenant.
- Một host được cho phép có thể có endpoint JSONP, upload hoặc nội dung do người dùng kiểm soát.
- Script của ứng dụng có thể tải tiếp script từ nguồn khác mà CSP không mô tả rõ chuỗi tin cậy.
- Danh sách nguồn dễ phình to theo plugin, analytics, tag manager và widget.
- Một host hợp lệ không bảo đảm mọi đường dẫn trên host đó đều an toàn.

Allowlist host chỉ mô tả nơi browser được phép tải script. Nó không chứng minh từng script được tải là mã mà ứng dụng chủ đích tin cậy.

### 2.1. Mô hình tin cậy với strict-dynamic

Strict-dynamic chuyển trọng tâm sang **script gốc được xác thực bằng nonce/hash**. Script gốc có thể tải thêm script một cách có chủ đích; browser hỗ trợ CSP3 truyền niềm tin tới những script được chèn động bởi script đáng tin cậy.

~~~mermaid
flowchart TD
    A["HTTP response có CSP"] --> B["script-src chứa nonce/hash<br/>và strict-dynamic"]
    B --> C["Script gốc có nonce/hash hợp lệ"]
    C --> D["Browser đánh dấu script gốc đáng tin cậy"]
    D --> E["Script gốc tạo script element<br/>và chèn vào DOM"]
    E --> F["Browser truyền niềm tin<br/>tới script được nạp động"]
    F --> G["Script con được thực thi"]
    H["Script parser-inserted<br/>không có nonce/hash"] --> I["Bị chặn trong CSP3"]
~~~

Đây là cơ chế của browser, không phải logic JavaScript tự đánh dấu script con. Ứng dụng vẫn chịu trách nhiệm bảo đảm script gốc chỉ tải những mã mà nó được phép tin cậy.

## 3. Cú pháp strict-dynamic

Một chính sách cơ bản:

~~~http
Content-Security-Policy: script-src 'nonce-RANDOM_PER_RESPONSE' 'strict-dynamic'; object-src 'none'; base-uri 'none'
~~~

Trong đó:

- **nonce source** cho phép script element có thuộc tính nonce trùng với nonce trong response header.
- **strict-dynamic** cho browser CSP3 truyền niềm tin từ script gốc được cho phép sang script được chèn động bởi script đó.
- **object-src 'none'** chặn plugin/object cũ.
- **base-uri 'none'** ngăn tài liệu bị thay đổi URL base thông qua thẻ base.

Trong triển khai có hỗ trợ browser cũ, chính sách có thể thêm nguồn fallback như 'self' hoặc host cần thiết:

~~~http
Content-Security-Policy: script-src 'nonce-RANDOM_PER_RESPONSE' 'strict-dynamic' 'self'; object-src 'none'; base-uri 'none'
~~~

Ở browser CSP3 hỗ trợ strict-dynamic, khi nonce/hash source và strict-dynamic cùng có mặt, các host-source và scheme-source trong cùng directive như 'self' hoặc https: bị bỏ qua đối với quyết định script theo cơ chế strict-dynamic. Ở browser cũ không hiểu strict-dynamic, nguồn fallback có thể được dùng theo phiên bản CSP mà browser hỗ trợ.

**Fallback làm giảm mức chặt trên browser cũ.** Ví dụ 'self' cho phép script cùng origin trong browser không hỗ trợ strict-dynamic. Nếu cần hỗ trợ browser cũ, hãy xác định rõ mức bảo vệ chấp nhận được và chỉ thêm host cần thiết; đừng thêm https: hoặc wildcard chỉ để làm hết lỗi Console.

## 4. Nonce source và hash source

Strict-dynamic cần một hoặc nhiều script gốc được xác thực. Hai cách thường dùng là nonce và hash.

### 4.1. Nonce source

Nonce là giá trị ngẫu nhiên do server sinh cho response. Header và script element phải dùng cùng giá trị:

~~~http
Content-Security-Policy: script-src 'nonce-abc123BASE64' 'strict-dynamic'
~~~

~~~html
<script nonce="abc123BASE64" src="/assets/bootstrap.js"></script>
~~~

Giá trị ví dụ chỉ minh họa cú pháp. Production cần:

- Sinh nonce bằng CSPRNG, ví dụ 16 byte ngẫu nhiên trở lên.
- Sinh nonce mới cho mỗi response HTML.
- Gắn đúng cùng nonce vào CSP header và những script gốc được phép.
- Không cho dữ liệu người dùng tự chọn hoặc ghi đè nonce.
- Không log nonce cùng toàn bộ HTML/session data.

Ví dụ Node.js:

~~~js
import { randomBytes } from 'node:crypto';

const nonce = randomBytes(16).toString('base64');
~~~

Nonce không phải password dài hạn. Nó tồn tại trong một response và được hiển thị trong HTML để browser đối chiếu. Yêu cầu quan trọng là attacker không thể dự đoán nonce trước khi response được tạo và ứng dụng không vô tình phát nonce cho markup không tin cậy.

### 4.2. Hash source

Thay vì nonce, CSP có thể cho phép script inline cụ thể bằng hash của nội dung script:

~~~http
Content-Security-Policy: script-src 'sha256-BASE64_HASH_OF_SCRIPT' 'strict-dynamic'
~~~

Hash source phải khớp chính xác bytes nội dung script theo quy tắc CSP. Chỉ thay một ký tự, khoảng trắng hoặc newline cũng có thể làm hash không còn khớp. Hash phù hợp với script inline tĩnh, ít thay đổi và được kiểm soát trong build.

Với external script, CSP hash source cần được phối hợp với thuộc tính integrity theo yêu cầu của CSP; đừng giả định chỉ khai báo hash trong header là mọi external script có nội dung tương ứng sẽ tự động được chấp nhận.

### 4.3. Chọn nonce hay hash?

| Tiêu chí | Nonce | Hash |
| --- | --- | --- |
| Phù hợp | HTML được render động theo response | Script inline tĩnh, ổn định |
| Tạo giá trị | CSPRNG cho mỗi response | Tính từ nội dung script |
| Cache | Phải đồng bộ header và HTML có nonce | Hash ổn định nếu nội dung không đổi |
| Thay đổi script | Không cần cập nhật hash khi nội dung đổi, nếu nonce vẫn đúng | Nội dung đổi thì phải cập nhật hash |
| Tích hợp | Cần template/server gắn nonce | Cần build pipeline quản lý hash |

Có thể dùng cả nonce và hash cho các nhóm script khác nhau. Điều quan trọng là danh sách script gốc phải nhỏ, rõ ràng và được review.

## 5. Parser-inserted và dynamically inserted scripts

Để hiểu strict-dynamic, cần phân biệt cách script element được đưa vào tài liệu.

### 5.1. Parser-inserted script

Đây là script element được HTML parser tạo ra khi phân tích markup:

~~~html
<script src="/assets/app.js"></script>
~~~

Trong chính sách strict-dynamic có nonce/hash source, script parser-inserted cần có nonce/hash hợp lệ để trở thành script gốc được tin cậy. Chỉ vì URL cùng origin hoặc host nằm trong allowlist không đủ để được tin cậy theo cơ chế CSP3 strict-dynamic.

Ví dụ:

~~~html
<!-- Không có nonce/hash: bị CSP3 strict-dynamic chặn -->
<script src="/assets/legacy.js"></script>

<!-- Có nonce hợp lệ: được phép làm script gốc -->
<script nonce="NONCE_FROM_RESPONSE" src="/assets/bootstrap.js"></script>
~~~

### 5.2. Script được chèn động bởi script đáng tin cậy

Một script gốc đã được xác thực có thể tạo element script rồi thêm vào DOM:

~~~js
const child = document.createElement('script');
child.src = '/assets/feature.js';
document.head.append(child);
~~~

Với browser hỗ trợ CSP3 strict-dynamic, script được chèn động theo cách này có thể kế thừa niềm tin từ script gốc đã được nonce/hash cho phép. Đây là lý do strict-dynamic hữu ích với ứng dụng dùng loader để tải module hoặc tính năng theo nhu cầu.

### 5.3. document.write không phải dynamic insertion tương đương

Không nên giả định mọi script được tạo sau khi trang tải đều kế thừa niềm tin. Script được đưa vào bằng document.write vẫn được HTML parser xử lý như parser-inserted trong các tình huống liên quan; nó không tương đương với việc script đáng tin cậy gọi createElement rồi append.

Hãy thiết kế loader bằng DOM API rõ ràng và kiểm thử hành vi trên browser mục tiêu. Tránh dùng document.write để tải script.

### 5.4. Bảng hành vi khái quát

| Trường hợp | CSP3 strict-dynamic với nonce/hash root | Ghi chú |
| --- | --- | --- |
| Script tĩnh có nonce hợp lệ | Cho phép | Là một trusted root |
| Script tĩnh có hash hợp lệ | Cho phép | Nội dung phải khớp hash |
| Script parser-inserted không nonce/hash | Chặn | Host 'self' không mở lại quyền trong chế độ strict-dynamic |
| Script được trusted root tạo bằng createElement và append | Có thể được cho phép | Niềm tin được truyền từ root |
| Script được chèn bằng document.write | Không được coi như descendant dynamic insertion | Xử lý theo parser-inserted rules |
| Inline event handler như onclick | Không được cho phép chỉ nhờ strict-dynamic | Cần bỏ inline handler; không bật unsafe-inline |
| eval hoặc new Function | Không được cho phép chỉ nhờ strict-dynamic | unsafe-eval là quyền riêng, nên tránh |

## 6. Script loader là ranh giới tin cậy quan trọng nhất

Khi bật strict-dynamic, script loader trở thành một phần của ranh giới bảo mật. Nếu loader nhận một URL tùy ý từ query string, API response, DOM attribute hoặc postMessage rồi tạo script element, browser có thể tin script đó vì loader gốc đã được nonce/hash xác thực.

### 6.1. Loader nguy hiểm

~~~js
// Không an toàn: dữ liệu URL do người dùng kiểm soát.
const requested = new URLSearchParams(location.search).get('script');
const script = document.createElement('script');
script.src = requested;
document.head.append(script);
~~~

Trong CSP strict-dynamic, không nên trông đợi host allowlist trong script-src sẽ chặn script con được trusted root tải động. Nếu attacker kiểm soát được requested, họ có thể khiến loader tải mã từ nguồn không mong muốn.

### 6.2. Loader dựa trên registry cố định

Tạo registry do ứng dụng kiểm soát:

~~~js
const featureScripts = Object.freeze({
  charts: '/assets/charts.8f31a2.js',
  reports: '/assets/reports.4b7c10.js',
  editor: '/assets/editor.2d9e61.js',
});

function loadFeature(name) {
  const src = featureScripts[name];
  if (!src) {
    throw new Error('Unknown feature');
  }

  const script = document.createElement('script');
  script.src = src;
  script.async = true;
  document.head.append(script);
}
~~~

Registry chỉ ánh xạ tên tính năng đã biết tới đường dẫn script được build và review. Không dùng URL thô từ user, query, dataset, API response hoặc postMessage làm script source.

### 6.3. Nếu phải tải script từ CDN

Hãy:

- Quản lý host và đường dẫn CDN trong cấu hình build/deploy tin cậy.
- Dùng SRI với integrity hash khi nội dung script có thể cố định.
- Thiết lập crossorigin phù hợp khi cần SRI cho tài nguyên cross-origin.
- Kiểm soát phiên bản, quyền publish và quy trình thay đổi package.
- Tránh CDN path có nội dung do người dùng hoặc tenant tùy ý ghi.
- Đánh giá rủi ro supply chain và quyền thực thi của script bên thứ ba.

Một host CDN được CSP cho phép không tự chứng minh package hoặc file trên host đó an toàn.

## 7. Script gadget và rủi ro khi tin script gốc quá rộng

**Script gadget** là đoạn code hợp lệ nhưng có thể bị lợi dụng để biến dữ liệu attacker kiểm soát thành hành vi nguy hiểm. Strict-dynamic không loại bỏ script gadget; nó có thể làm tác động của gadget lớn hơn nếu gadget nằm trong trusted root.

Ví dụ một loader hợp lệ nhận cấu hình:

~~~js
function loadWidget(config) {
  const script = document.createElement('script');
  script.src = config.widgetUrl;
  document.head.append(script);
}
~~~

Nếu attacker điều khiển config.widgetUrl, loader có thể tải script độc hại. Việc loader có nonce hợp lệ không làm URL đó trở nên đáng tin.

Các nguồn dữ liệu cần kiểm tra kỹ:

- Query string, fragment và path.
- Thuộc tính data-* hoặc DOM element có thể bị DOM clobbering.
- JSON từ API hoặc cấu hình tenant.
- postMessage từ iframe/window khác.
- Tên plugin hoặc module do user cung cấp.
- Nội dung từ tag manager, CMS hoặc database có quyền chỉnh sửa rộng.

Phòng vệ:

1. Script root phải nhỏ và dễ review.
2. Loader chỉ nhận identifier từ enum/registry do ứng dụng định nghĩa.
3. Không cho cấu hình người dùng cung cấp URL script tùy ý.
4. Kiểm tra URL và origin ở loader như lớp bổ sung, nhưng ưu tiên registry đường dẫn cố định.
5. Dùng Trusted Types cho sink hỗ trợ nếu ứng dụng có thể triển khai policy chặt.
6. Theo dõi thay đổi script root và dependency như thay đổi mã thực thi có đặc quyền.

## 8. Nonce lifecycle, cache và template

Nonce chỉ có giá trị khi server quản lý đúng vòng đời.

### 8.1. Sinh nonce mới theo response

Ví dụ Node.js tạo nonce:

~~~js
import { randomBytes } from 'node:crypto';

function createNonce() {
  return randomBytes(16).toString('base64');
}
~~~

Server cần dùng cùng nonce trong header và markup của đúng response:

~~~js
const nonce = createNonce();
const csp = "script-src 'nonce-" + nonce + "' 'strict-dynamic' 'self'; object-src 'none'; base-uri 'none'";

res.setHeader('Content-Security-Policy', csp);
res.setHeader('Cache-Control', 'no-store');
~~~

Trong template:

~~~html
<script nonce="NONCE_GENERATED_FOR_THIS_RESPONSE" src="/assets/bootstrap.js"></script>
~~~

Không hardcode nonce trong source code, không dùng một nonce cố định cho mọi request và không cho người dùng điều khiển template nonce.

### 8.2. HTML cache và CDN

Nếu CDN cache HTML nhưng CSP header được tạo lại với nonce khác, header và markup không khớp; browser sẽ chặn script. Nếu CDN cache cả header và HTML với cùng nonce trong thời gian dài, nonce có thể bị tái sử dụng giữa nhiều người dùng/request, làm giảm mục tiêu chống đoán trước.

Các lựa chọn:

- Không cache response HTML có nonce ở shared cache; dùng Cache-Control phù hợp như private/no-store tùy yêu cầu.
- Nếu cần cache, thiết kế edge/server để tạo nonce và thay thế header + markup nhất quán cho từng response; phải kiểm thử tính nguyên tử và tránh cache leak.
- Với script inline tĩnh, cân nhắc hash source để không phụ thuộc nonce động.

Không cấu hình CDN chỉ sửa header hoặc chỉ thay nonce trong HTML. Hai phần phải luôn khớp chính xác.

### 8.3. Không phát nonce cho nội dung do người dùng kiểm soát

Không gắn nonce lên mọi script element theo một bước xử lý tổng quát sau render. Nếu HTML do người dùng cung cấp được chèn vào tài liệu rồi nhận nonce, attacker có thể có script được cho phép. Template chỉ nên gắn nonce cho các script gốc đã được review và xác định.

Nonce cũng không phải bí mật có thể giấu khỏi JavaScript đang chạy cùng trang. Nếu attacker đã có XSS thực thi trong origin, họ thường có thể đọc DOM và tìm cách dùng quyền của trang; CSP nonce không phải biện pháp chữa XSS đã thành công.

## 9. Fallback cho browser không hỗ trợ strict-dynamic

Strict-dynamic thuộc CSP Level 3. Browser cũ có thể hiểu nonce nhưng bỏ qua strict-dynamic; browser rất cũ có thể không hiểu nonce. Vì vậy cần biết chính sách fallback thực sự cho phép điều gì.

Ví dụ:

~~~http
Content-Security-Policy: script-src 'nonce-RANDOM_PER_RESPONSE' 'strict-dynamic' 'self'; object-src 'none'; base-uri 'none'
~~~

| Khả năng browser | Cách hiểu chính sách |
| --- | --- |
| CSP3 có strict-dynamic | Dùng nonce root và truyền trust; 'self' bị bỏ qua trong quyết định script theo strict-dynamic |
| CSP2 có nonce nhưng không có strict-dynamic | Nonce vẫn có tác dụng; 'self' là nguồn fallback và có thể cho phép script cùng origin |
| CSP1 không hỗ trợ nonce/strict-dynamic | Có thể chỉ hiểu nguồn 'self'; mức bảo vệ thấp hơn |

Nếu ứng dụng cần tương thích rộng hơn, hãy lựa chọn fallback dựa trên browser thực tế của người dùng. Có thể dùng host allowlist hẹp thay cho 'self' nếu script được phục vụ từ CDN cụ thể. Tránh thêm wildcard hoặc https: mà không đánh giá phạm vi tin cậy.

Không cần đưa 'unsafe-inline' vào một chính sách strict-dynamic hiện đại. Nếu dùng nó như fallback cho CSP1, cần hiểu rằng browser cũ có thể cho phép inline script và event handler; đây là mức bảo vệ thấp hơn rõ rệt. Ưu tiên nâng browser support baseline nếu sản phẩm cho phép.

## 10. strict-dynamic không thay thế các directive khác

Strict-dynamic chỉ liên quan đến quyết định script trong script-src (và các directive script tương ứng theo CSP). Nó không thay toàn bộ CSP.

| Directive | Vai trò | Vì sao vẫn cần |
| --- | --- | --- |
| script-src | Chính sách nguồn script và strict-dynamic | Xác định trusted root và quy tắc script |
| object-src | Kiểm soát object/embed | Chặn plugin cũ, giảm bề mặt tấn công |
| base-uri | Giới hạn URL base | Tránh thẻ base làm đổi cách resolve URL tương đối |
| style-src | Nguồn CSS | Script trust không kiểm soát CSS |
| img-src | Nguồn ảnh | Giới hạn tracking/tải tài nguyên ngoài |
| connect-src | fetch/XHR/WebSocket/EventSource | Giới hạn endpoint kết nối |
| frame-src | Nguồn iframe | Kiểm soát tài liệu được nhúng |
| frame-ancestors | Ai được nhúng trang hiện tại | Phòng clickjacking |
| form-action | Đích gửi form | Giảm việc form bị chuyển hướng dữ liệu |
| require-trusted-types-for | Enforcement Trusted Types | Bổ sung kiểm soát DOM XSS sink được hỗ trợ |

Một chính sách có thể bắt đầu như sau rồi điều chỉnh theo ứng dụng:

~~~http
Content-Security-Policy: default-src 'self'; script-src 'nonce-RANDOM_PER_RESPONSE' 'strict-dynamic' 'self'; object-src 'none'; base-uri 'none'; style-src 'self'; img-src 'self' https://images.example.com; connect-src 'self' https://api.example.com; frame-src 'self'; frame-ancestors 'none'; form-action 'self'
~~~

Nonce phải được thay theo từng response. Danh sách host trong img-src/connect-src/frame-src/style-src là chính sách riêng cho các loại tài nguyên; strict-dynamic không mở rộng chúng.

## 11. Kết hợp Subresource Integrity và Trusted Types

### 11.1. Subresource Integrity (SRI)

SRI cho phép browser kiểm tra nội dung của một số script/style bên ngoài có khớp hash đã khai báo không:

~~~html
<script
  src="https://cdn.example.com/library-4.2.1.min.js"
  integrity="sha384-BASE64_HASH"
  crossorigin="anonymous"></script>
~~~

SRI hữu ích khi nội dung file có phiên bản cố định. Nếu file thay đổi mà hash không cập nhật, browser từ chối tài nguyên. SRI và CSP giải quyết hai lớp khác nhau:

- CSP quyết định nguồn/script nào được phép nạp.
- SRI kiểm tra bytes của tài nguyên có khớp hash đã mong đợi không.

Strict-dynamic không tự xác minh nội dung script con. Nếu loader nạp script động từ một URL, hãy dùng integrity hash được quản lý nếu có thể và không lấy hash từ nguồn attacker kiểm soát.

### 11.2. Trusted Types

Trusted Types có thể hạn chế một số DOM sink nguy hiểm nhận chuỗi tùy ý. Ví dụ enforcement:

~~~http
Content-Security-Policy: require-trusted-types-for 'script'; trusted-types app-html
~~~

Trusted Types hỗ trợ bảo vệ các sink như innerHTML và một số sink script được triển khai trong browser. Nó không thay allowlist URL cho mọi anchor/navigation và không tự làm loader an toàn. Một policy tạo TrustedScriptURL từ chuỗi tùy ý vẫn có thể mở đường cho script injection.

### 11.3. CSP nonce không phải CSRF token

Nonce CSP gắn với script trong response và dùng để browser xác định script được phép chạy. CSRF token xác minh request thay đổi trạng thái gắn với session. Hai loại token có mục tiêu và vòng đời khác nhau; không dùng thay thế nhau.

## 12. Báo cáo và kiểm thử CSP

Trước khi bật enforcement trên toàn bộ traffic:

1. Kiểm kê script root, loader, tag manager, analytics và widget.
2. Triển khai CSP ở chế độ Report-Only trên môi trường thử nghiệm hoặc nhóm traffic phù hợp.
3. Thu thập vi phạm, xác định script hợp lệ bị chặn và nguồn không mong muốn.
4. Sửa loader hoặc cấu hình theo registry thay vì thêm nguồn rộng để bỏ cảnh báo.
5. Kiểm thử các luồng lazy-load, route khác nhau, đăng nhập, thanh toán và trang nhúng.
6. Bật enforcement rồi tiếp tục giám sát vi phạm.

Header báo cáo có thể dùng endpoint được hỗ trợ bởi browser:

~~~http
Content-Security-Policy-Report-Only: script-src 'nonce-RANDOM_PER_RESPONSE' 'strict-dynamic' 'self'; object-src 'none'; base-uri 'none'; report-to csp-endpoint
Reporting-Endpoints: csp-endpoint="https://reports.example.com/csp"
~~~

Hỗ trợ reporting và định dạng report khác nhau theo browser/phiên bản. Không giả định mọi browser đều gửi report giống nhau. Report có thể chứa URL, line number và dữ liệu trang; cần xử lý như telemetry có thể chứa thông tin nhạy cảm, giới hạn quyền truy cập và retention.

## 13. Thực hành: kiểm chứng strict-dynamic với Node.js

Bài thực hành dùng **Node.js 18 trở lên**, không cần package ngoài. Server tạo nonce cho mỗi response, gửi một script gốc có nonce, một script parser-inserted không có nonce và để script gốc tải script con bằng createElement.

### 13.1. Tạo file strict-dynamic-lab.mjs

~~~js
import { createServer } from 'node:http';
import { randomBytes } from 'node:crypto';

const html = (nonce) => (
  '<!doctype html>' +
  '<html lang="vi"><head><meta charset="utf-8">' +
  '<title>strict-dynamic lab</title></head><body>' +
  '<h1>strict-dynamic</h1>' +
  '<p id="parser-status">Parser script chưa chạy.</p>' +
  '<p id="root-status">Root script chưa chạy.</p>' +
  '<p id="child-status">Child script chưa chạy.</p>' +
  '<script src="/parser-without-nonce.js"></script>' +
  '<script nonce="' + nonce + '" src="/root.js"></script>' +
  '</body></html>'
);

createServer((req, res) => {
  const path = new URL(req.url, 'http://localhost').pathname;

  if (path === '/') {
    const nonce = randomBytes(16).toString('base64');
    const policy =
      "default-src 'none'; " +
      "script-src 'nonce-" + nonce + "' 'strict-dynamic' 'self'; " +
      "base-uri 'none'; object-src 'none'; frame-ancestors 'none'; " +
      "script-src-attr 'none'";

    res.writeHead(200, {
      'Content-Type': 'text/html; charset=utf-8',
      'Content-Security-Policy': policy,
      'Cache-Control': 'no-store',
    });
    res.end(html(nonce));
    return;
  }

  if (path === '/parser-without-nonce.js') {
    res.writeHead(200, {
      'Content-Type': 'text/javascript; charset=utf-8',
      'Cache-Control': 'no-store',
    });
    res.end(
      "window.parserScriptRan = true;" +
      "document.querySelector('#parser-status').textContent =" +
      "'Parser-inserted script đã chạy';"
    );
    return;
  }

  if (path === '/root.js') {
    res.writeHead(200, {
      'Content-Type': 'text/javascript; charset=utf-8',
      'Cache-Control': 'no-store',
    });
    res.end(
      "window.rootScriptRan = true;" +
      "document.querySelector('#root-status').textContent =" +
      "'Root script có nonce đã chạy';" +
      "var child = document.createElement('script');" +
      "child.src = '/child.js';" +
      "document.head.append(child);"
    );
    return;
  }

  if (path === '/child.js') {
    res.writeHead(200, {
      'Content-Type': 'text/javascript; charset=utf-8',
      'Cache-Control': 'no-store',
    });
    res.end(
      "window.childScriptRan = true;" +
      "document.querySelector('#child-status').textContent =" +
      "'Child script được root tải động đã chạy';"
    );
    return;
  }

  res.writeHead(404, { 'Content-Type': 'text/plain; charset=utf-8' });
  res.end('Not found');
}).listen(3000, () => {
  console.log('Open http://localhost:3000');
});
~~~

Chạy:

~~~bash
node strict-dynamic-lab.mjs
~~~

Mở http://localhost:3000 trong browser hỗ trợ CSP3 strict-dynamic. Mở DevTools → Console và Network, bật Preserve log nếu cần.

### 13.2. Kết quả mong đợi trên browser hỗ trợ strict-dynamic

| Thành phần | Cách đưa vào trang | Kết quả |
| --- | --- | --- |
| parser-without-nonce.js | Script trong HTML parser, không nonce/hash | Bị CSP chặn |
| root.js | Script parser-inserted có nonce đúng | Được chạy |
| child.js | Root script tạo element rồi append | Được chạy nhờ trust propagation |

Trong Console, browser có thể ghi CSP violation cho parser script thiếu nonce/hash. Trong Network, request script có thể xuất hiện khác nhau tùy thời điểm và browser; việc request tải được không tự chứng minh script được phép thực thi. Hãy quan sát cả trạng thái DOM và Console.

### 13.3. Thử thay đổi loader

Trong root.js, thử thay đường dẫn cố định:

~~~js
child.src = '/child.js';
~~~

bằng URL lấy từ query:

~~~js
const requested = new URLSearchParams(location.search).get('script');
child.src = requested;
~~~

Đây là biến thể **không an toàn** để phân tích trong lab cô lập. Vì child được tạo bởi trusted root, strict-dynamic có thể cho phép nó tải script ngoài host allowlist. Không triển khai kiểu loader này trong ứng dụng thật. Hãy thay bằng registry tên module → đường dẫn tĩnh đã review.

### 13.4. So sánh browser cũ

Browser không hỗ trợ strict-dynamic sẽ bỏ qua source expression này. Với fallback 'self' trong ví dụ, browser CSP2 có thể cho phép parser-inserted script cùng origin dù script đó không có nonce. Đây là khác biệt có chủ đích của fallback; không đánh giá kết quả chỉ dựa trên một browser.

### 13.5. Giới hạn lab

- Lab dùng HTTP localhost để dễ chạy; production phải dùng HTTPS.
- Nonce được sinh mới mỗi lần tải trang và response không cache.
- Script root và child chỉ thay đổi text trên trang, không thực hiện hành động nhạy cảm.
- Lab không thay thế kiểm thử trên toàn bộ browser/version mà sản phẩm hỗ trợ.
- Không thử tải script từ website không tin cậy hoặc đưa dữ liệu tài khoản thật vào trang thử nghiệm.

## 14. Checklist triển khai strict-dynamic

1. **Chọn trusted root:** chỉ nonce/hash những script gốc được review và thực sự cần thiết.
2. **Sinh nonce an toàn:** CSPRNG, giá trị mới theo response, header và HTML phải khớp.
3. **Kiểm soát cache:** không để CDN tách header khỏi HTML hoặc tái sử dụng nonce ngoài thiết kế.
4. **Kiểm tra loader:** không nhận script URL tùy ý từ query, API, postMessage, DOM hoặc cấu hình tenant.
5. **Dùng registry:** ánh xạ module name đã định nghĩa tới script path/version cố định.
6. **Phân biệt parser và dynamic insertion:** script tĩnh cần nonce/hash; script con chỉ được tin cậy qua luồng do root kiểm soát.
7. **Không dùng document.write:** thay bằng createElement/append với URL đã kiểm tra.
8. **Giữ fallback hẹp:** chỉ thêm 'self' hoặc host cần thiết cho browser cũ; hiểu rõ browser cũ có thể cho phép rộng hơn.
9. **Giữ directive khác:** object-src, base-uri, form-action, frame-ancestors, connect-src và các policy cần thiết.
10. **Cân nhắc SRI:** xác minh nội dung external script cố định; strict-dynamic không thay integrity check.
11. **Bảo vệ DOM:** Trusted Types, sanitizer và Safe DOM API giảm script gadget/XSS trong trusted root.
12. **Report rồi enforce:** kiểm tra violation, lazy-load, tag manager, route và luồng đăng nhập trước khi bật chặn.
13. **Không log nonce/token:** CSP report và log cần lọc dữ liệu nhạy cảm.
14. **Theo dõi dependency:** thay đổi script root, loader hoặc package là thay đổi ranh giới tin cậy cần review.

## 15. Những nhầm lẫn cần tránh

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| “strict-dynamic cho phép mọi script trên trang.” | Nó truyền niềm tin từ trusted root tới script được root chèn động; parser script không nonce/hash vẫn bị chặn trong CSP3. |
| “Có 'self' thì script cùng origin luôn được phép.” | Khi strict-dynamic hoạt động cùng nonce/hash, host-source như 'self' bị bỏ qua cho quyết định script theo cơ chế này. |
| “Script con được tải động chắc chắn an toàn.” | Nó được tin do nguồn tạo ra; nếu loader nhận URL attacker kiểm soát, script độc hại có thể được tải. |
| “Nonce có thể hardcode.” | Nonce cần khó đoán và mới theo response; hardcode làm mất mục tiêu bảo vệ. |
| “Nonce phải được giấu khỏi mọi JavaScript.” | Nonce xuất hiện trong response/DOM; nó không bảo vệ khi attacker đã thực thi XSS cùng origin. |
| “document.write giống createElement + append.” | document.write đi qua HTML parser và không có cùng quy tắc truyền trust của dynamic insertion. |
| “strict-dynamic thay toàn bộ CSP.” | Nó chỉ ảnh hưởng chính sách script; các directive cho frame, image, connect, form và object vẫn cần. |
| “strict-dynamic tự chặn eval.” | eval/new Function có chính sách riêng; strict-dynamic không cấp quyền unsafe-eval. |
| “CSP nonce là CSRF token.” | Nonce xác thực script được browser phép chạy; CSRF token xác minh request gắn với session. |
| “CSP cho phép script thì nội dung script đã được kiểm tra integrity.” | CSP quyết định quyền thực thi; SRI mới kiểm tra bytes khớp hash mong đợi. |

## 16. Câu hỏi tự đánh giá

**Câu 1.** strict-dynamic cần kết hợp với điều kiện nào để xác định trusted root?

**Gợi ý trả lời:** Chính sách script-src cần có nonce source hoặc hash source hợp lệ cùng strict-dynamic. Script gốc phải có nonce/hash tương ứng.

**Câu 2.** Vì sao script parser-inserted không nonce bị chặn trong CSP3 strict-dynamic dù host là self?

**Gợi ý trả lời:** Khi strict-dynamic hoạt động với nonce/hash source, host-source và scheme-source trong directive không còn là căn cứ cho phép script; script parser-inserted cần nonce/hash.

**Câu 3.** Script gốc có nonce tạo script element và append vào DOM. Browser hỗ trợ CSP3 xử lý thế nào?

**Gợi ý trả lời:** Browser có thể truyền niềm tin từ trusted root sang script được chèn động đó.

**Câu 4.** Vì sao loader không được lấy URL script từ query string?

**Gợi ý trả lời:** Script con được trusted root tải có thể kế thừa trust; attacker điều khiển URL có thể khiến ứng dụng tải mã độc.

**Câu 5.** Nonce cần được quản lý thế nào khi dùng CDN cache HTML?

**Gợi ý trả lời:** Header và HTML phải dùng cùng nonce cho đúng response. Không cache riêng một phần hoặc tái sử dụng nonce ngoài thiết kế; thường cần no-store/private hoặc edge thay thế nguyên tử.

**Câu 6.** strict-dynamic có cho phép inline onclick hoặc eval không?

**Gợi ý trả lời:** Không. Inline event handler và eval có quy tắc riêng; nên bỏ inline handler và tránh unsafe-eval.

**Câu 7.** SRI bổ sung gì cho strict-dynamic?

**Gợi ý trả lời:** strict-dynamic quyết định script có được tin cậy để nạp hay không; SRI kiểm tra nội dung tài nguyên có khớp hash đã mong đợi không.

## Tài liệu tham khảo

- W3C — [Content Security Policy Level 3: strict-dynamic](https://www.w3.org/TR/CSP3/#strict-dynamic-usage).
- MDN — [Content-Security-Policy: script-src](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Security-Policy/script-src), [CSP guide](https://developer.mozilla.org/en-US/docs/Web/HTTP/CSP).
- Google Web Fundamentals — [Mitigate cross-site scripting with a strict Content Security Policy](https://web.dev/articles/strict-csp).
- OWASP — [Content Security Policy Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Content_Security_Policy_Cheat_Sheet.html), [Cross Site Scripting Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet.html).
- MDN — [Subresource Integrity](https://developer.mozilla.org/en-US/docs/Web/Security/Subresource_Integrity), [Trusted Types API](https://developer.mozilla.org/en-US/docs/Web/API/Trusted_Types_API).
