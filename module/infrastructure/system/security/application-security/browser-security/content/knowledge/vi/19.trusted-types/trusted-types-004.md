# TrustedScriptURL: kiểm soát URL dùng để tải mã JavaScript

Trusted Types cung cấp các kiểu dữ liệu đặc biệt để ứng dụng kiểm soát những API của trình duyệt có thể đưa dữ liệu vào DOM hoặc tải mã. Trong nhóm này, `TrustedScriptURL` đại diện cho một URL đã được policy của ứng dụng chấp thuận để dùng tại một script URL sink.

Điểm quan trọng là một URL script không chỉ là một địa chỉ tài nguyên. Khi trình duyệt tải JavaScript từ URL đó, mã nhận được có thể chạy với quyền của trang. Nếu URL được ghép từ tham số do người dùng kiểm soát, ứng dụng có thể vô tình tải mã từ một vị trí ngoài dự kiến. `TrustedScriptURL` giúp đặt một ranh giới rõ ràng: chỉ policy có kiểm tra mới được tạo giá trị mà sink được bảo vệ chấp nhận.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích `TrustedScriptURL` là gì và vì sao nó khác một chuỗi URL thông thường.
- Nhận diện những luồng dữ liệu có thể dẫn đến việc tải script ngoài ý muốn.
- Phân biệt `TrustedScriptURL` với `TrustedScript` và `TrustedHTML`.
- Tạo policy có allowlist URL cụ thể và dùng policy tại script URL sink.
- Kết hợp Trusted Types với CSP `trusted-types`, `require-trusted-types-for` và `script-src`.
- Hiểu giới hạn của Trusted Types, CSP và Subresource Integrity (SRI).
- Kiểm thử và rà soát các bộ nạp script động trong ứng dụng.

## 1. TrustedScriptURL là gì?

`TrustedScriptURL` là một kiểu đối tượng của Trusted Types. Nó biểu diễn URL được tạo thông qua phương thức `createScriptURL` của một Trusted Types policy. Ứng dụng có thể đưa giá trị này vào các sink được trình duyệt định nghĩa là nơi nhận URL script.

Ví dụ phổ biến là thuộc tính `src` của phần tử `HTMLScriptElement`:

~~~js
const script = document.createElement("script");
script.src = trustedScriptURL;
document.head.append(script);
~~~

Khi trình duyệt thực thi Trusted Types enforcement, sink được bảo vệ sẽ yêu cầu kiểu phù hợp thay vì chấp nhận một chuỗi thông thường. Một chuỗi có nội dung giống hệt URL vẫn là chuỗi thường; nó không tự trở thành `TrustedScriptURL`.

Kiểu này giúp ứng dụng tách hai việc:

1. Chọn URL nào được phép dùng để tải script.
2. Đưa URL đã được policy kiểm tra vào sink có khả năng tải mã.

`TrustedScriptURL` không tự xác minh máy chủ có an toàn, nội dung script có đáng tin hay mã có đúng phiên bản hay không. Những quyết định đó cần allowlist, CSP, kiểm soát triển khai và các biện pháp như SRI khi phù hợp.

## 2. Vì sao URL tải script là ranh giới bảo mật?

Một trang web có thể tải script tĩnh từ HTML hoặc tạo script động bằng JavaScript. Cách thứ hai thường xuất hiện trong:

- Bộ nạp module hoặc tính năng chỉ tải khi người dùng mở một màn hình.
- Hệ thống plugin, tiện ích mở rộng nội bộ hoặc widget.
- Ứng dụng tải biểu đồ, trình soạn thảo, trình xem tài liệu theo nhu cầu.
- Mã tích hợp SDK của bên thứ ba.
- Bộ nạp script dựa trên cấu hình máy chủ hoặc phản hồi API.

Một luồng nguy hiểm có thể trông như sau:

~~~text
Tham số URL / dữ liệu API / cấu hình không tin cậy
                      |
                      v
              JavaScript đọc dữ liệu
                      |
                      v
             Ghép hoặc chọn URL script
                      |
                      v
          Gán vào HTMLScriptElement.src
                      |
                      v
             Trình duyệt tải JavaScript
                      |
                      v
          Mã được tải có thể chạy trong trang
~~~

Ví dụ lỗi:

~~~js
const params = new URLSearchParams(location.search);
const scriptUrl = params.get("module");

const script = document.createElement("script");
script.src = scriptUrl;
document.head.append(script);
~~~

Nếu người dùng có thể điều khiển `module`, họ có thể làm ứng dụng tải một URL ngoài dự kiến. Tùy chính sách CSP và các kiểm soát khác, điều này có thể dẫn đến việc thực thi mã không mong muốn trong trang.

Lỗi tương tự có thể xuất hiện khi URL được lấy từ:

- Query string, fragment hoặc dữ liệu `postMessage`.
- API trả về tên file hoặc đường dẫn do người dùng tạo.
- `localStorage`, `sessionStorage` hoặc IndexedDB.
- Cấu hình plugin được lưu từ một nguồn không đáng tin.
- Dữ liệu được ghép từ nhiều thành phần, trong đó một phần do người dùng kiểm soát.

Dữ liệu đã được lưu vào cơ sở dữ liệu hoặc trả về từ máy chủ vẫn cần được đánh giá theo nguồn gốc và quyền kiểm soát. Việc chuyển qua một tầng lưu trữ không biến URL thành đáng tin.

## 3. Phân biệt ba kiểu Trusted Types

Trusted Types có ba kiểu chính thường gặp khi bảo vệ các sink phía trình duyệt.

| Kiểu | Đại diện cho | Ví dụ mục đích |
|---|---|---|
| `TrustedHTML` | HTML đã được policy xử lý | Chèn nội dung rich text vào HTML sink |
| `TrustedScript` | Nội dung mã script đã được policy chấp thuận | Một số sink nhận mã script dạng chuỗi |
| `TrustedScriptURL` | URL được dùng để tải script | Gán URL vào script URL sink |

Không dùng nhầm các kiểu này cho nhau. Một HTML fragment đã được làm sạch không phải URL script. Một URL script được allowlist không phải nội dung mã JavaScript. Mỗi kiểu bảo vệ một nhóm sink và một mục đích khác nhau.

Ví dụ:

~~~js
// HTML fragment: policy cần làm sạch cấu trúc HTML.
const safeMarkup = htmlPolicy.createHTML(untrustedMarkup);

// Mã script: policy cần kiểm soát nội dung mã.
const trustedCode = scriptPolicy.createScript(untrustedCode);

// URL tải script: policy cần xác minh đích đến được phép.
const trustedUrl = scriptUrlPolicy.createScriptURL(scriptPath);
~~~

Đối với bài học này, trọng tâm là URL được dùng để tải mã. Không dùng `createScriptURL` để làm sạch HTML hoặc xác thực nội dung JavaScript.

## 4. Policy tạo TrustedScriptURL hoạt động thế nào?

Ứng dụng tạo policy bằng `trustedTypes.createPolicy`. Policy cung cấp callback `createScriptURL`. Callback nhận chuỗi đầu vào, kiểm tra theo quy tắc của ứng dụng và trả về chuỗi URL được chấp thuận. Trình duyệt bọc kết quả thành đối tượng `TrustedScriptURL`.

Ví dụ cấu trúc tối giản:

~~~js
const scriptUrlPolicy = trustedTypes.createPolicy("app-script-url", {
  createScriptURL(input) {
    // Kiểm tra URL tại đây.
    return input;
  }
});
~~~

Đoạn tối giản trên chỉ mô tả hình dạng API. Callback trả nguyên đầu vào mà không kiểm tra là policy pass-through và không cung cấp hàng rào bảo mật có ý nghĩa. Không dùng nó trong ứng dụng thật.

Một policy có trách nhiệm cần:

- Chỉ nhận các URL hoặc đường dẫn đã được ứng dụng dự kiến.
- Phân tích URL bằng API chuẩn như `URL`, không tự kiểm tra bằng regex đơn giản.
- Kiểm tra origin, path và các thành phần khác theo chính sách.
- Từ chối URL sai định dạng hoặc ngoài allowlist.
- Không cho dữ liệu người dùng tùy ý quyết định host hay đường dẫn script.
- Được tạo ở một module có kiểm soát và không bị chia sẻ như một hàm tin cậy tùy tiện.

## 5. Dùng allowlist cố định cho script động

Một mẫu an toàn hơn là dùng một registry ánh xạ tên tính năng sang đường dẫn script do ứng dụng kiểm soát. Người dùng chỉ chọn tên tính năng; họ không cung cấp URL.

~~~js
const SCRIPT_PATHS = Object.freeze({
  charts: "/assets/charts.8f2a.js",
  reports: "/assets/reports.1b7c.js"
});

const allowedPaths = new Set(Object.values(SCRIPT_PATHS));

const scriptUrlPolicy = trustedTypes.createPolicy("app-script-url", {
  createScriptURL(input) {
    const url = new URL(input, window.location.origin);

    const isAllowed =
      url.origin === window.location.origin &&
      url.username === "" &&
      url.password === "" &&
      url.search === "" &&
      url.hash === "" &&
      allowedPaths.has(url.pathname);

    if (!isAllowed) {
      throw new TypeError("Script URL is not allowed");
    }

    return url.href;
  }
});

function loadFeature(name) {
  const path = SCRIPT_PATHS[name];

  if (!path) {
    throw new TypeError("Unknown feature");
  }

  const script = document.createElement("script");
  script.src = scriptUrlPolicy.createScriptURL(path);
  script.async = true;
  document.head.append(script);
}
~~~

Trong ví dụ này:

- `SCRIPT_PATHS` là danh sách đường dẫn cố định trong mã ứng dụng.
- `allowedPaths` chứa các đường dẫn đã được phê duyệt.
- `new URL` phân tích và chuẩn hóa URL trước khi kiểm tra.
- Policy chỉ chấp nhận URL cùng origin, không có userinfo, query hoặc fragment, và có pathname nằm trong allowlist.
- Hàm `loadFeature` nhận một khóa tính năng, không nhận URL tùy ý từ người dùng.

Trong sản phẩm thật, đường dẫn có thể chứa phiên bản build hoặc hash nội dung. Hãy cập nhật registry cùng quy trình phát hành để URL được phép luôn khớp với tài nguyên đã triển khai.

Nếu ứng dụng cần tải script từ CDN, allowlist phải chỉ rõ origin và đường dẫn cần thiết. Không thay kiểm tra origin chính xác bằng điều kiện chứa chuỗi như `url.href.includes("cdn.example")`; điều kiện kiểu đó dễ chấp nhận hostname giả hoặc URL có userinfo gây nhầm lẫn.

## 6. Kiểm tra URL đúng cách

Một URL có thể có nhiều thành phần cần xem xét:

~~~text
https://cdn.example.test:443/assets/app.js?mode=prod#entry
|       |                 |             |          |
scheme  host              path          query      fragment
        + port
~~~

Tùy kiến trúc, policy có thể cần kiểm tra:

- Scheme: chỉ chấp nhận giao thức mà ứng dụng cho phép, thường là HTTPS trong môi trường triển khai.
- Origin: so sánh `url.origin` với origin ứng dụng hoặc origin CDN được phê duyệt.
- Hostname: không dùng so khớp chuỗi con.
- Port: chỉ cho phép port cần thiết.
- Pathname: dùng danh sách đường dẫn hoặc quy tắc prefix có ranh giới rõ ràng.
- Username/password: từ chối userinfo nếu ứng dụng không có nhu cầu rõ ràng.
- Query và fragment: chỉ cho phép khi tính năng có yêu cầu và giá trị được kiểm soát.

### 6.1 So sánh origin thay vì chuỗi URL

Không dùng:

~~~js
if (input.includes("trusted.example.test")) {
  return input;
}
~~~

Một URL có thể chứa chuỗi đó trong phần query, path hoặc username mà host thật lại khác. Dùng parser URL và so sánh thuộc tính đã phân tích:

~~~js
const url = new URL(input, window.location.origin);

if (url.origin !== "https://trusted.example.test") {
  throw new TypeError("Unexpected script origin");
}
~~~

So sánh origin bao gồm scheme, hostname và port. Nếu chính sách cho phép nhiều host, dùng một tập origin chính xác.

### 6.2 Kiểm tra path với ranh giới rõ ràng

Nếu ứng dụng dùng prefix, tránh kiểm tra kiểu:

~~~js
url.pathname.startsWith("/assets")
~~~

Điều kiện đó cũng có thể khớp một đường dẫn như `/assets-evil/loader.js`. Nếu cần prefix, hãy kiểm tra `url.pathname === "/assets" || url.pathname.startsWith("/assets/")`, đồng thời cân nhắc chỉ cho phép tên file cụ thể.

Allowlist chính xác các URL script thường dễ review hơn. Nếu dùng prefix, hãy có kiểm thử cho path gần giống, ký tự mã hóa, dấu chấm đường dẫn và dấu gạch chéo lặp.

### 6.3 Không dựa vào đuôi file

Đường dẫn kết thúc bằng `.js` không chứng minh tài nguyên là script đáng tin. Máy chủ có thể trả nội dung khác, redirect sang địa chỉ khác hoặc bị cấu hình sai. Policy URL kiểm soát địa chỉ ban đầu; CSP và kiểm soát phía máy chủ vẫn cần thiết.

## 7. Kết hợp với CSP

Trusted Types được bật bằng CSP. Hai directive quan trọng là:

- `require-trusted-types-for 'script'`: yêu cầu các sink được bảo vệ nhận giá trị Trusted Types phù hợp thay vì chuỗi thông thường.
- `trusted-types app-script-url`: giới hạn tên policy được phép tạo.

Ví dụ header:

~~~http
Content-Security-Policy: default-src 'self'; script-src 'self'; require-trusted-types-for 'script'; trusted-types app-script-url
~~~

Trong ví dụ này:

- `script-src 'self'` kiểm soát nguồn script mà trình duyệt được phép tải hoặc thực thi theo CSP.
- `require-trusted-types-for 'script'` bật enforcement cho nhóm sink script được hỗ trợ.
- `trusted-types app-script-url` chỉ cho phép tạo policy có tên `app-script-url`.

Tên policy trong mã phải khớp với tên được cho phép trong CSP:

~~~js
trustedTypes.createPolicy("app-script-url", {
  createScriptURL(input) {
    // Kiểm tra allowlist trước khi trả URL.
    return validateScriptURL(input);
  }
});
~~~

Nếu tên policy không được CSP cho phép, trình duyệt có thể từ chối tạo policy. Nếu ứng dụng tạo policy nhưng không bật enforcement, các sink có thể vẫn chấp nhận chuỗi thường. Vì vậy, cần kiểm tra cả header thực tế lẫn hành vi runtime.

`script-src` và Trusted Types giải quyết hai lớp khác nhau. Một URL có thể được policy Trusted Types chấp nhận nhưng vẫn bị `script-src` chặn. Ngược lại, `script-src 'self'` cho phép nguồn cùng origin nhưng không tự xác minh rằng một chuỗi cụ thể được đưa vào sink là đường dẫn script mà ứng dụng dự định.

## 8. TrustedScriptURL không thay thế CSP hoặc SRI

Các cơ chế dưới đây bổ sung cho nhau:

| Cơ chế | Câu hỏi nó giải quyết |
|---|---|
| TrustedScriptURL | Giá trị nào được phép đi vào script URL sink được bảo vệ? |
| CSP `script-src` | Trình duyệt được phép tải hoặc thực thi script từ nguồn nào? |
| SRI (`integrity`) | Byte của tài nguyên tải về có khớp hash mong đợi không? |
| HTTPS và kiểm soát máy chủ | Tài nguyên được truyền và phục vụ qua hạ tầng nào? |

Ví dụ SRI cho script tĩnh:

~~~html
<script
  src="https://cdn.example.test/library-4.2.0.min.js"
  integrity="sha384-BASE64_HASH_DO_BUILD_TAO"
  crossorigin="anonymous"></script>
~~~

SRI phù hợp khi ứng dụng biết trước nội dung mong đợi của tài nguyên. Với script động có nhiều phiên bản hoặc nội dung thay đổi, cần thiết kế quy trình phát hành và hash tương ứng.

`TrustedScriptURL` không tính hash và không kiểm tra nội dung tải về. SRI không quyết định URL nào được phép đi vào mọi sink. CSP cũng không thay thế allowlist URL ở cấp ứng dụng.

## 9. Redirect và rủi ro từ URL được cho phép

Một URL nằm trong allowlist vẫn có thể chuyển hướng. Ví dụ, `https://app.example.test/load-script?id=42` có thể trả về redirect đến một host khác. Kiểm tra URL đầu vào không đảm bảo URL cuối cùng hoặc nội dung cuối cùng sẽ an toàn.

Các biện pháp cần cân nhắc:

- Tránh endpoint redirect tổng quát làm nguồn script.
- Dùng đường dẫn tài nguyên tĩnh hoặc manifest do build tạo.
- Kiểm soát redirect tại máy chủ và giới hạn đích chuyển hướng.
- Dùng CSP để giới hạn nguồn script được phép.
- Dùng SRI khi có thể cố định nội dung tài nguyên.
- Kiểm tra Network để quan sát chuỗi redirect và response cuối cùng.

Nếu policy cho phép một CDN, hãy hiểu CDN đó phục vụ những path nào, ai có quyền publish, cách xác thực tài khoản và quy trình cập nhật package. Tin cậy một hostname cũng có nghĩa là tin cậy quy trình triển khai nội dung ở hostname đó.

## 10. Không để policy trở thành API cấp quyền tùy tiện

Policy có quyền tạo `TrustedScriptURL`. Nếu mã không tin cậy có thể gọi policy với bất kỳ chuỗi nào, ranh giới bảo vệ sẽ mất ý nghĩa.

Tránh thiết kế API công khai như:

~~~js
window.makeTrustedScriptURL = value =>
  scriptUrlPolicy.createScriptURL(value);
~~~

Mã bất kỳ trong trang có thể gọi hàm này với URL do nó chọn. Thay vào đó, giữ policy trong module nội bộ và chỉ cung cấp hàm cấp cao nhận khóa tính năng đã định nghĩa:

~~~js
function loadApprovedFeature(featureName) {
  const path = SCRIPT_PATHS[featureName];

  if (!path) {
    throw new TypeError("Feature is not approved");
  }

  return loadFeature(featureName);
}
~~~

Các nguyên tắc bổ sung:

- Không đưa đối tượng policy lên `window` hoặc chia sẻ cho plugin không tin cậy.
- Không để dữ liệu API tự quyết định tên policy.
- Không tạo policy mới tại từng component chỉ để né lỗi enforcement.
- Không dùng policy mặc định kiểu pass-through.
- Không bắt lỗi policy rồi fallback sang gán chuỗi thông thường.
- Ghi nhận và xử lý lỗi khi URL không nằm trong allowlist.

Một policy là một quyền bảo mật. Chỉ những module có trách nhiệm mới nên nắm quyền đó.

## 11. Default policy và giai đoạn chuyển đổi

Trusted Types có thể dùng một policy tên `default` để xử lý một số trường hợp mã cũ đưa chuỗi vào sink được bảo vệ. Đây là cơ chế tương thích, không phải cách tự động làm cho mọi chuỗi an toàn.

Với script URL, default policy nếu có phải thực hiện cùng mức kiểm tra như policy chuyên biệt. Nếu nó chấp nhận mọi đầu vào, mã cũ vẫn có thể tải script từ URL tùy ý và lợi ích của enforcement bị suy giảm.

Trong giai đoạn chuyển đổi:

1. Bật báo cáo để tìm sink đang nhận chuỗi.
2. Phân loại từng sink theo mục đích: HTML, script code hay script URL.
3. Tạo policy chuyên biệt với kiểm tra phù hợp.
4. Chuyển caller sang API cấp cao đã được review.
5. Loại bỏ default policy khi các luồng cũ đã được xử lý nếu ứng dụng không còn cần nó.

Không tạo một default policy chỉ trả lại đầu vào để làm biến mất lỗi console.

## 12. Nhiều policy và quyền tạo policy

Directive CSP `trusted-types` giới hạn tên policy có thể được tạo trong tài liệu. Ví dụ:

~~~http
Content-Security-Policy: trusted-types app-script-url app-html; require-trusted-types-for 'script'
~~~

Chính sách này cho phép hai tên policy đã liệt kê. Mỗi policy nên có mục đích riêng và callback phù hợp với loại dữ liệu mà nó tạo.

Không đặt một tên policy dùng chung cho mọi tác vụ chỉ vì thuận tiện. Một policy HTML và một policy URL script có yêu cầu kiểm tra khác nhau. Tách tên giúp review quyền rõ ràng và giảm nguy cơ một thay đổi ở policy này ảnh hưởng đến sink khác.

Nếu có nhiều CSP enforcement policy trên cùng tài liệu, tất cả các chính sách có hiệu lực cùng lúc. Một header khác không thể mở rộng quyền mà header hiện tại đã giới hạn.

## 13. Khả năng tương thích trình duyệt

Trusted Types enforcement phụ thuộc khả năng hỗ trợ của trình duyệt. Không nên giả định mọi trình duyệt hoặc mọi phiên bản đều thực thi giống nhau.

Khi triển khai:

- Kiểm tra ma trận trình duyệt mà sản phẩm hỗ trợ.
- Xác nhận `window.trustedTypes` có tồn tại trước khi dùng API.
- Kiểm tra CSP response header và console trên từng trình duyệt.
- Không xem polyfill là ranh giới bảo mật tương đương enforcement gốc của trình duyệt.
- Giữ các biện pháp nền như CSP `script-src`, HTTPS, kiểm soát URL ở ứng dụng và quy trình phát hành an toàn.

Nếu trình duyệt không hỗ trợ Trusted Types, allowlist trong mã vẫn hữu ích, nhưng sink không được trình duyệt ép kiểu theo cơ chế Trusted Types. Hãy coi đây là khác biệt về mức bảo vệ và đưa vào kiểm thử tương thích.

## 14. Kiểm thử bằng DevTools

### 14.1 Xác nhận enforcement

Trên một trang lab, thiết lập header:

~~~http
Content-Security-Policy: default-src 'self'; script-src 'self'; require-trusted-types-for 'script'; trusted-types app-script-url
~~~

Thử gán một chuỗi thông thường vào script URL sink:

~~~js
const script = document.createElement("script");
script.src = "/assets/charts.js";
document.head.append(script);
~~~

Trong trình duyệt có hỗ trợ enforcement, thao tác này cần bị từ chối vì giá trị đưa vào sink là chuỗi thường.

### 14.2 Xác nhận policy hợp lệ

Tạo policy có allowlist và gán giá trị được tạo ra:

~~~js
const policy = trustedTypes.createPolicy("app-script-url", {
  createScriptURL(input) {
    const url = new URL(input, location.origin);

    if (
      url.origin !== location.origin ||
      url.pathname !== "/assets/charts.js" ||
      url.search ||
      url.hash
    ) {
      throw new TypeError("URL is not approved");
    }

    return url.href;
  }
});

const script = document.createElement("script");
script.src = policy.createScriptURL("/assets/charts.js");
document.head.append(script);
~~~

Xác nhận URL được allowlist được chấp nhận và tài nguyên vẫn phải thỏa mãn `script-src`.

### 14.3 Xác nhận URL ngoài allowlist bị từ chối

Thử lần lượt:

~~~js
policy.createScriptURL("https://attacker.example.test/payload.js");
policy.createScriptURL("/uploads/user-provided.js");
policy.createScriptURL("/assets/charts.js?next=https://attacker.example.test");
~~~

Các đầu vào này phải bị policy từ chối theo quy tắc của ví dụ. Không dùng mã thử nghiệm có thể tải script thật từ bên ngoài; có thể chỉ gọi policy và quan sát lỗi.

### 14.4 Quan sát Network và Console

Kiểm tra:

- Request script có được gửi không.
- URL cuối cùng sau redirect.
- Response status, Content-Type và nguồn tải.
- Lỗi Trusted Types khi sink nhận chuỗi thường.
- Vi phạm CSP nếu URL không khớp `script-src`.
- Header CSP có đúng policy name và enforcement directive không.

Lưu ý: policy từ chối URL trước khi gán sẽ không tạo request. CSP chặn nguồn thường được thể hiện bằng một vi phạm khác. Phân biệt hai loại lỗi giúp xác định lớp kiểm soát đang hoạt động.

## 15. Rà soát mã nguồn

Tìm các vị trí có thể tải script động hoặc nhận URL script:

~~~js
document.createElement("script");
script.src = value;
script.setAttribute("src", value);
import(value);
new Worker(value);
navigator.serviceWorker.register(value);
~~~

Danh sách trên là các điểm cần điều tra, không có nghĩa mọi API trong đó đều dùng cùng một Trusted Types sink hoặc được thực thi giống nhau trên mọi trình duyệt. Hãy đối chiếu loại sink và hỗ trợ của nền tảng mà ứng dụng triển khai.

Với mỗi vị trí, trả lời:

1. URL được tạo ở đâu?
2. Dữ liệu nào có thể ảnh hưởng đến URL?
3. Policy nào tạo `TrustedScriptURL`?
4. Policy có allowlist origin và path rõ ràng không?
5. Có endpoint redirect hoặc CDN nào trong chuỗi tải không?
6. CSP `script-src` có giới hạn nguồn độc lập không?
7. Có thể dùng SRI để xác minh nội dung không?
8. Policy có bị expose cho mã không tin cậy không?
9. Hành vi khi URL bị từ chối có an toàn và dễ chẩn đoán không?
10. Có kiểm thử trên trình duyệt hỗ trợ và không hỗ trợ Trusted Types không?

Không kết luận lỗ hổng chỉ từ việc thấy `createElement("script")`. Cần lần theo nguồn URL, policy, CSP, redirect và quyền publish tài nguyên.

## 16. Các lỗi triển khai thường gặp

### 16.1 Policy pass-through

Callback trả nguyên chuỗi đầu vào không kiểm tra gì. Bất kỳ URL nào cũng có thể được đóng gói thành giá trị tin cậy.

### 16.2 Allowlist bằng chuỗi con

Kiểm tra `includes("trusted.example")` có thể chấp nhận URL mà hostname thực tế không phải host dự kiến. Hãy parse URL và so sánh origin hoặc hostname chính xác.

### 16.3 Cho phép cả một scheme

Cho phép `https:` có thể mở rộng đến nhiều host. HTTPS bảo vệ kênh truyền, nhưng không chứng minh mọi máy chủ HTTPS đều được phép cung cấp mã cho ứng dụng.

### 16.4 Tin vào đuôi .js

Đuôi file không xác nhận nội dung response. Kiểm soát nguồn, quyền publish và nội dung tài nguyên vẫn cần thiết.

### 16.5 Bỏ qua redirect

Policy kiểm tra URL ban đầu nhưng máy chủ có thể chuyển hướng sang nơi khác. Tránh endpoint redirect tổng quát và kiểm tra URL cuối cùng trong Network.

### 16.6 Chỉ bật Trusted Types mà quên script-src

Trusted Types không quyết định nguồn nào được tải. Nếu CSP `script-src` quá rộng, policy URL cũng có thể cho phép nguồn rộng ngoài ý muốn.

### 16.7 Tắt enforcement để sửa lỗi

Bỏ `require-trusted-types-for 'script'` làm các sink có thể trở lại nhận chuỗi thường. Hãy sửa caller và policy thay vì loại bỏ hàng rào.

### 16.8 Dùng policy cho mọi plugin

Một policy rộng được chia sẻ cho nhiều module làm khó xác định ai có quyền tải script nào. Dùng registry và API cấp cao theo chức năng.

## 17. Bài thực hành

Thực hiện trên trang lab cục bộ. Dùng script mẫu do bạn kiểm soát và không đưa mã bên ngoài vào ứng dụng thật.

### Bài 1: Quan sát script URL sink

Tạo một phần tử script bằng `document.createElement`. Gán URL bằng chuỗi thường trong môi trường đã bật Trusted Types enforcement. Quan sát lỗi và giải thích vì sao chuỗi URL hợp lệ về cú pháp vẫn chưa phải `TrustedScriptURL`.

### Bài 2: Tạo policy allowlist

Tạo policy chỉ cho phép hai đường dẫn script trong cùng origin. Gọi policy với đường dẫn được phép, đường dẫn khác, URL ngoài origin và URL có query string. Ghi lại đầu vào được chấp nhận và bị từ chối.

### Bài 3: Tạo loader theo tên tính năng

Tạo một object registry ánh xạ tên tính năng sang URL tĩnh. Viết hàm `loadFeature(name)` chỉ nhận khóa trong registry. Kiểm thử tên không tồn tại và bảo đảm hàm không nhận URL tùy ý.

### Bài 4: So sánh Trusted Types với CSP

Giữ policy allowlist nhưng thay đổi `script-src` để chặn origin của script. Quan sát rằng policy có thể tạo TrustedScriptURL nhưng trình duyệt vẫn chặn tải theo CSP. Sau đó khôi phục nguồn được phép và kiểm tra lại.

### Bài 5: Kiểm tra redirect và SRI

Dùng một endpoint lab có redirect đến một đường dẫn khác. Quan sát URL ban đầu và URL cuối cùng. Nếu script là tài nguyên cố định, thử thêm SRI với hash được tạo từ đúng file. Giải thích vai trò riêng của allowlist URL, CSP và SRI.

## 18. Checklist review TrustedScriptURL

- [ ] Đã xác định chính xác script URL sink đang sử dụng.
- [ ] Không đưa URL tùy ý từ query string, API hoặc storage trực tiếp vào sink.
- [ ] Policy `createScriptURL` kiểm tra URL bằng parser chuẩn.
- [ ] Allowlist giới hạn origin và path theo nhu cầu tối thiểu.
- [ ] Không dùng kiểm tra chuỗi con, wildcard hoặc scheme quá rộng.
- [ ] Đã cân nhắc query, fragment, userinfo, port và redirect.
- [ ] Policy không phải pass-through và không bị expose cho mã không tin cậy.
- [ ] CSP `trusted-types` chỉ cho phép tên policy cần thiết.
- [ ] CSP `require-trusted-types-for 'script'` được thực thi trên trình duyệt hỗ trợ.
- [ ] CSP `script-src` vẫn giới hạn nguồn script độc lập.
- [ ] SRI được dùng khi có thể cố định nội dung script.
- [ ] Đã kiểm thử trình duyệt có và không có Trusted Types enforcement.
- [ ] Có log và xử lý lỗi khi policy từ chối URL.
- [ ] Không có fallback sang chuỗi thường khi policy thất bại.

## 19. Câu hỏi tự kiểm tra

**1. TrustedScriptURL đại diện cho điều gì?**

Nó đại diện cho URL dùng để tải script, được tạo bởi callback `createScriptURL` của Trusted Types policy.

**2. Vì sao chuỗi URL hợp lệ vẫn chưa phải TrustedScriptURL?**

Vì tính hợp lệ về cú pháp không chứng minh URL được ứng dụng cho phép. TrustedScriptURL chỉ được tạo qua policy và policy cần kiểm tra đích đến.

**3. TrustedScriptURL khác TrustedScript như thế nào?**

TrustedScriptURL là địa chỉ tải mã; TrustedScript đại diện cho nội dung mã trong những sink nhận script code. Chúng không thay thế nhau.

**4. Policy createScriptURL có nên trả nguyên đầu vào không?**

Không. Policy pass-through không kiểm tra URL và có thể biến mọi đầu vào thành giá trị được tin cậy.

**5. Vì sao nên dùng URL parser thay cho includes?**

Parser cho phép kiểm tra origin, hostname, port, path và các thành phần riêng. Kiểm tra chuỗi con có thể chấp nhận URL giả có chứa tên host đáng tin trong một thành phần khác.

**6. TrustedScriptURL có bỏ qua script-src không?**

Không. CSP `script-src` vẫn kiểm soát nguồn script được phép tải hoặc thực thi.

**7. SRI và TrustedScriptURL khác nhau thế nào?**

TrustedScriptURL kiểm soát giá trị URL đi vào sink. SRI kiểm tra byte tài nguyên tải về có khớp hash mong đợi hay không.

**8. Nếu trình duyệt không hỗ trợ Trusted Types thì sao?**

Enforcement gốc có thể không hoạt động. Ứng dụng vẫn cần allowlist ở mã, CSP script-src, HTTPS và các kiểm soát phát hành; cần ghi nhận khác biệt trong ma trận trình duyệt.

**9. Vì sao không nên expose policy lên window?**

Vì mã khác trong trang có thể gọi policy với URL do nó chọn, làm mất kiểm soát tập trung đối với quyền tạo TrustedScriptURL.

## Ghi nhớ

`TrustedScriptURL` đặt một ranh giới kiểu dữ liệu tại những sink tải script được bảo vệ. Policy phải xác minh URL theo allowlist cụ thể và chỉ cấp giá trị tin cậy cho các tài nguyên mà ứng dụng đã phê duyệt. CSP `script-src` tiếp tục giới hạn nguồn tải, còn SRI có thể xác minh nội dung tài nguyên cố định. Ba cơ chế này giải quyết các câu hỏi khác nhau và cần được kiểm thử cùng nhau.
