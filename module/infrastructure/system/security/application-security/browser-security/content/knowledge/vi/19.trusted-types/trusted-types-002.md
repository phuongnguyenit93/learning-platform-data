# TrustedHTML: kiểm soát dữ liệu được đưa vào HTML injection sinks

## 1. TrustedHTML giải quyết vấn đề gì?

Ứng dụng web thường cần hiển thị nội dung do người dùng tạo, chẳng hạn bình luận, mô tả sản phẩm hoặc bài viết có định dạng. Một số giao diện đưa nội dung này vào DOM bằng các API nhận chuỗi HTML như `innerHTML`. Nếu chuỗi không được xử lý đúng, trình duyệt có thể parse markup ngoài dự kiến và tạo lỗ hổng DOM-based XSS.

Ví dụ:

```javascript
const comment = getCommentFromApi();
document.querySelector("#comments").innerHTML = comment;
```

Ở đây, `innerHTML` coi `comment` là HTML. Nếu nội dung có element, attribute hoặc URL nguy hiểm, ứng dụng có thể tạo DOM không an toàn.

**TrustedHTML** là một kiểu dữ liệu của Trusted Types API, dùng để biểu thị chuỗi HTML đã đi qua một policy được ứng dụng tin cậy. Khi browser bật cơ chế thực thi Trusted Types, các HTML injection sinks có thể từ chối chuỗi thông thường và chỉ nhận `TrustedHTML`.

TrustedHTML không tự làm sạch HTML. Policy tạo ra giá trị này phải thực hiện sanitization bằng thư viện phù hợp và cấu hình allowlist rõ ràng. Nếu policy trả nguyên input, ứng dụng vẫn có XSS; chỉ là chuỗi nguy hiểm đã được gắn nhãn tin cậy.

Trong module bảo mật trình duyệt, TrustedHTML là lớp kiểm soát DOM sink, bổ sung cho contextual output encoding, HTML sanitization, CSP, Trusted Types và các security headers. Nó giúp tập trung những điểm được phép biến chuỗi thành HTML để dễ kiểm tra và duy trì.

Sau bài học, bạn có thể:

- Giải thích `TrustedHTML`, `TrustedTypePolicy` và `createHTML()`.
- Bật enforcement bằng CSP.
- Tạo policy sử dụng sanitizer được duy trì.
- Nhận diện các HTML injection sinks cần kiểm soát.
- Dùng default policy có chủ đích trong giai đoạn migration.
- Kiểm thử hành vi browser và xử lý môi trường chưa hỗ trợ Trusted Types.

## 2. TrustedHTML là một kiểu, không phải một sanitizer

Trusted Types API cung cấp các kiểu dữ liệu mang nhãn tin cậy:

| Kiểu | Mục đích |
| --- | --- |
| `TrustedHTML` | Nội dung được phép đưa vào HTML injection sinks. |
| `TrustedScript` | Script đã được policy cho phép tại các sink nhận script. |
| `TrustedScriptURL` | URL script đã được policy cho phép tại các sink tải script. |

Bài này tập trung vào `TrustedHTML`. Các kiểu còn lại có policy method và sink riêng; không dùng `TrustedHTML` để đại diện cho JavaScript hoặc URL script.

Một giá trị chuỗi bình thường:

```javascript
const html = "<p>Xin chào</p>";
```

không tự trở thành `TrustedHTML` chỉ vì nó chứa markup hợp lệ. Ứng dụng phải gọi policy:

```javascript
const trustedHtml = htmlPolicy.createHTML(html);
container.innerHTML = trustedHtml;
```

`createHTML()` gọi hàm `createHTML` mà ứng dụng đăng ký trong policy rồi trả về đối tượng `TrustedHTML`. Browser có thể kiểm tra kiểu này tại sink khi CSP enforcement được bật.

**Tên kiểu không phải bằng chứng nội dung an toàn tuyệt đối.** Mức an toàn phụ thuộc vào policy, sanitizer, allowlist và cách ứng dụng quản lý policy.

## 3. HTML injection sinks là gì?

HTML injection sink là API hoặc thuộc tính mà browser có thể dùng để parse chuỗi thành HTML. Một số sink thường gặp:

| Sink | Cách sử dụng | Lưu ý |
| --- | --- | --- |
| `Element.innerHTML` | Gán hoặc đọc markup bên trong element. | Sink phổ biến cần kiểm soát. |
| `Element.outerHTML` | Thay thế element bằng markup. | Có thể tạo cấu trúc DOM mới. |
| `Element.insertAdjacentHTML()` | Chèn markup tại vị trí chỉ định. | Cần giá trị HTML tin cậy. |
| `Document.write()` / `writeln()` | Ghi chuỗi vào luồng parser của document. | API cũ, nên loại bỏ khi có thể. |
| `Range.createContextualFragment()` | Parse chuỗi thành DocumentFragment. | Có thể nhận HTML từ dữ liệu không tin cậy. |
| `HTMLIFrameElement.srcdoc` | Đặt nội dung tài liệu HTML cho iframe. | Cần kiểm soát nội dung và sandbox riêng. |
| `DOMParser.parseFromString(..., "text/html")` | Parse chuỗi thành một document HTML. | Cần kiểm tra cách ứng dụng sử dụng document sau khi parse. |

Danh sách sink được browser kiểm soát và mức hỗ trợ Trusted Types có thể thay đổi theo API và trình duyệt. Khi audit, hãy kiểm tra tài liệu của browser mục tiêu và tìm các đường dữ liệu đi vào DOM parser.

### 3.1 Ví dụ sink nhận chuỗi

```javascript
const input = getUntrustedMarkup();
const container = document.querySelector("#preview");

// HTML parser được gọi tại sink này.
container.innerHTML = input;
```

Với enforcement Trusted Types, gán chuỗi trực tiếp có thể phát sinh `TypeError`:

```javascript
// Khi require-trusted-types-for 'script' đang được thực thi,
// chuỗi thông thường bị từ chối ở HTML injection sink.
container.innerHTML = input;
```

Ứng dụng cần chuyển chuỗi qua policy được kiểm soát trước khi gọi sink.

### 3.2 Không phải mọi sink đều nhận TrustedHTML

`href`, `src` và các vị trí URL cần validation theo scheme/host; event handler cần loại bỏ cách tạo code từ chuỗi; sink thực thi script có thể yêu cầu `TrustedScript` hoặc `TrustedScriptURL`. Đừng dùng một policy HTML để cấp quyền cho mọi loại sink.

## 4. Tạo policy và TrustedHTML

Policy được tạo qua `trustedTypes.createPolicy()`. Policy khai báo các hàm chuyển đổi dữ liệu đầu vào thành kiểu Trusted Types tương ứng.

Ví dụ tối giản về cấu trúc:

```javascript
const htmlPolicy = trustedTypes.createPolicy("app-html", {
  createHTML(input) {
    return sanitizeRichText(input);
  }
});

const trustedHtml = htmlPolicy.createHTML(untrustedHtml);
container.innerHTML = trustedHtml;
```

Trong ví dụ này:

1. `createPolicy("app-html", ...)` đăng ký policy tên `app-html`.
2. Ứng dụng gọi `htmlPolicy.createHTML()` với chuỗi chưa tin cậy.
3. Callback `createHTML()` chạy sanitizer.
4. API trả về đối tượng `TrustedHTML`.
5. Sink nhận giá trị TrustedHTML thay vì chuỗi tùy ý.

`sanitizeRichText()` là hàm minh họa, không có sẵn trong browser. Trong ứng dụng thật, hàm này phải gọi thư viện sanitizer được duy trì và có cấu hình rõ ràng.

### 4.1 Policy là ranh giới tin cậy

Mọi code có quyền sử dụng policy có thể yêu cầu policy tạo `TrustedHTML`. Do đó:

- Tạo policy tại một module trung tâm, không tạo tùy tiện ở mọi component.
- Chỉ cấp quyền gọi policy cho phần code thật sự cần render rich text.
- Không expose hàm `createHTML()` tổng quát cho dữ liệu không kiểm soát.
- Review sanitizer và cấu hình allowlist như một phần của security boundary.
- Tránh tạo nhiều policy có tên khác nhau nhưng cùng trả nguyên input.

Policy là nơi cần review kỹ nhất. Trusted Types enforcement chỉ đảm bảo sink nhận một giá trị đã đi qua policy; nó không chứng minh callback policy đã làm đúng.

## 5. Dùng sanitizer trong createHTML()

Với nội dung rich text, nên dùng thư viện HTML sanitizer trưởng thành, được cập nhật và cấu hình theo allowlist. Ví dụ với DOMPurify:

```javascript
const htmlPolicy = trustedTypes.createPolicy("app-html", {
  createHTML(input) {
    return DOMPurify.sanitize(input, {
      ALLOWED_TAGS: [
        "p", "br", "strong", "em", "ul", "ol", "li", "a"
      ],
      ALLOWED_ATTR: ["href", "title"],
      ALLOW_DATA_ATTR: false,
      RETURN_TRUSTED_TYPE: false
    });
  }
});

function renderRichText(target, untrustedHtml) {
  target.innerHTML = htmlPolicy.createHTML(untrustedHtml);
}
```

Ở trong callback của policy, `RETURN_TRUSTED_TYPE: false` yêu cầu DOMPurify trả về chuỗi đã sanitize. Sau đó Trusted Types API bọc kết quả từ callback thành `TrustedHTML`. Cấu hình tag/attribute ở trên chỉ là ví dụ; sản phẩm cần xác định đúng tập markup cần hỗ trợ.

DOMPurify có quy tắc xử lý URL nguy hiểm mặc định, nhưng vẫn phải review cấu hình khi thay đổi allowlist, đặc biệt với `href`, SVG, MathML, style hoặc các tính năng mở rộng. Không tự bật thêm tag/attribute chỉ để nội dung hiển thị giống hệt đầu vào.

### 5.1 Vì sao không trả nguyên input?

Policy sau đây là sai:

```javascript
const unsafePolicy = trustedTypes.createPolicy("unsafe-html", {
  createHTML(input) {
    return input;
  }
});

container.innerHTML = unsafePolicy.createHTML(untrustedHtml);
```

Policy không hề kiểm tra hay làm sạch nội dung. Nếu CSP cho phép policy này, mọi chuỗi có thể trở thành TrustedHTML và đi vào sink. Enforcement khi đó mất ý nghĩa bảo vệ.

### 5.2 Encoding và sanitization có vai trò khác nhau

Nếu chỉ hiển thị văn bản, dùng `textContent`; không cần tạo TrustedHTML. Nếu cần giữ rich text, sanitizer tạo ra markup được phép. TrustedHTML giúp kiểm soát đường đưa kết quả đã sanitize vào sink.

Không dùng TrustedHTML như cách lưu trữ dữ liệu lâu dài hoặc thay thế output encoding trong HTML server-side. Đây là kiểu runtime dành cho các sink được browser hỗ trợ.

## 6. Bật enforcement bằng Content Security Policy

Trusted Types được điều khiển qua hai CSP directives thường dùng:

```http
Content-Security-Policy: require-trusted-types-for 'script'; trusted-types app-html
```

Hai directive có nhiệm vụ khác nhau:

| Directive | Vai trò |
| --- | --- |
| `require-trusted-types-for 'script'` | Yêu cầu các sink được hỗ trợ dùng Trusted Types thay vì nhận chuỗi thông thường. |
| `trusted-types app-html` | Chỉ cho phép tạo policy có tên `app-html`. |

Nếu chỉ có `trusted-types app-html` mà không có `require-trusted-types-for 'script'`, ứng dụng có thể tạo policy được phép nhưng browser chưa bắt buộc các sink dùng Trusted Types.

Nếu chỉ có `require-trusted-types-for 'script'` mà không cho phép policy cần thiết, code gọi `trustedTypes.createPolicy("app-html", ...)` có thể bị từ chối bởi CSP. Vì vậy, cần cấu hình cả enforcement lẫn tên policy.

### 6.1 Cho phép nhiều policy có kiểm soát

Nếu ứng dụng có các module riêng biệt, có thể cho phép một tập tên:

```http
Content-Security-Policy: require-trusted-types-for 'script'; trusted-types app-html editor-html
```

Mỗi policy phải có trách nhiệm rõ ràng và được review riêng. Không dùng tên wildcard hoặc mở rộng danh sách policy chỉ để khắc phục lỗi runtime mà chưa xác định module nào cần quyền tạo TrustedHTML.

### 6.2 Chặn tất cả policy

Chính sách:

```http
Content-Security-Policy: trusted-types 'none'
```

không cho phép code tạo policy Trusted Types mới theo directive đó. Nếu đồng thời bật `require-trusted-types-for 'script'`, các sink cần Trusted Types sẽ không có policy tùy chỉnh để chuyển chuỗi; ứng dụng nên dùng safe APIs như `textContent` hoặc thiết kế lại các luồng HTML.

## 7. Default policy và migration ứng dụng cũ

Ứng dụng lớn có thể có hàng trăm chỗ gán chuỗi vào `innerHTML`. Việc sửa đồng loạt có thể cần thời gian. Trusted Types hỗ trợ policy đặc biệt tên `default`.

Khi enforcement đang bật và sink nhận chuỗi thông thường, browser có thể gọi callback của default policy để chuyển chuỗi sang kiểu phù hợp. Ví dụ:

```javascript
const defaultPolicy = trustedTypes.createPolicy("default", {
  createHTML(input) {
    console.warn("Legacy HTML sink needs review");
    return DOMPurify.sanitize(input, {
      RETURN_TRUSTED_TYPE: false
    });
  }
});
```

Policy mặc định có thể giúp ứng dụng cũ tiếp tục hoạt động trong lúc chuyển từng sink sang policy chuyên biệt. Tuy nhiên, nó cũng có thể che khuất các chỗ code chưa được sửa vì mọi chuỗi đi vào sink đều được chuyển tự động.

### 7.1 Dùng default policy như bước chuyển tiếp

Một kế hoạch migration hợp lý:

1. Bật CSP Report-Only để thu thập các sink đang truyền chuỗi.
2. Phân loại sink: hiển thị text, rich text, template nội bộ hay dữ liệu không rõ nguồn.
3. Thay sink hiển thị text bằng `textContent`/DOM API an toàn.
4. Tạo policy chuyên biệt cho rich text và dùng sanitizer.
5. Nếu cần, dùng default policy tạm thời để giảm lỗi khi chuyển đổi.
6. Ghi log nơi default policy được gọi và sửa từng call site.
7. Xóa default policy khi các luồng cần thiết đã chuyển sang policy tường minh hoặc safe sink.
8. Bật enforcement và theo dõi lỗi còn lại.

Không tạo default policy trả nguyên input. Nếu chưa có sanitizer an toàn, không dùng default policy để tự động tin mọi chuỗi.

### 7.2 Policy default không phải ngoại lệ khỏi CSP

Tên `default` vẫn phải được CSP cho phép trong directive `trusted-types`. Nếu policy name bị CSP cấm, việc tạo policy sẽ thất bại. Kiểm tra response header thực tế và lỗi trong Console khi khởi tạo.

## 8. TrustedHTML không bảo vệ các context khác

TrustedHTML chỉ dành cho các HTML injection sinks được Trusted Types kiểm soát. Nó không xác thực mọi dữ liệu mà ứng dụng nhận.

| Vị trí | Cơ chế phù hợp |
| --- | --- |
| Văn bản trong element | `textContent` hoặc output encoding HTML text. |
| Rich HTML | Sanitizer allowlist rồi tạo `TrustedHTML`. |
| `href`/`src` | Parse URL, allowlist scheme/host và gán property phù hợp. |
| Event handler | Không tạo code từ chuỗi; dùng `addEventListener`. |
| JavaScript source | Tránh nội suy; dùng dữ liệu JSON/DOM an toàn hoặc cơ chế riêng cho script. |
| Script URL | Kiểm tra URL và dùng `TrustedScriptURL` khi sink/enforcement yêu cầu. |
| CSS value | Dùng CSSOM và allowlist theo thuộc tính. |

Một policy `createHTML()` không biến URL `javascript:` thành URL hợp lệ. Nếu sanitizer cho phép liên kết, sanitizer phải có quy tắc URL an toàn riêng. Khi đặt URL vào `href`, vẫn cần validation theo chính sách ứng dụng.

## 9. Xử lý trình duyệt chưa hỗ trợ Trusted Types

Hỗ trợ Trusted Types khác nhau giữa các browser và phiên bản. Ứng dụng cần kiểm tra browser mục tiêu, nhưng không được bỏ sanitization chỉ vì API không có.

Có thể feature-detect:

```javascript
if (window.trustedTypes) {
  // Tạo policy và dùng TrustedHTML.
} else {
  // Vẫn sanitize bằng cùng thư viện trước khi dùng HTML sink,
  // hoặc ưu tiên safe DOM APIs để không cần HTML sink.
}
```

Fallback phải giữ nguyên kiểm soát bảo mật. Ví dụ, nếu browser không hỗ trợ Trusted Types, ứng dụng vẫn gọi sanitizer trước khi gán vào `innerHTML`. Nếu chỉ cần hiển thị text, `textContent` hoạt động mà không cần Trusted Types.

Không làm kiểu:

```javascript
// Không an toàn: browser không hỗ trợ thì dùng input thô.
const html = window.trustedTypes
  ? policy.createHTML(input)
  : input;
```

Đoạn code này bỏ qua sanitization trong browser không hỗ trợ. Thay vào đó, sanitizer phải là bước độc lập; Trusted Types chỉ bổ sung enforcement ở browser hỗ trợ.

## 10. Ví dụ tích hợp có fallback an toàn

Ví dụ sau giả định DOMPurify đã được nạp từ nguồn tin cậy và có phiên bản được cập nhật:

```javascript
const sanitize = input => DOMPurify.sanitize(input, {
  ALLOWED_TAGS: ["p", "br", "strong", "em", "ul", "ol", "li", "a"],
  ALLOWED_ATTR: ["href", "title"],
  ALLOW_DATA_ATTR: false,
  RETURN_TRUSTED_TYPE: false
});

const htmlPolicy = window.trustedTypes
  ? window.trustedTypes.createPolicy("app-html", {
      createHTML(input) {
        return sanitize(input);
      }
    })
  : null;

function renderComment(target, untrustedComment) {
  if (htmlPolicy) {
    target.innerHTML = htmlPolicy.createHTML(untrustedComment);
  } else {
    // Browser không có Trusted Types vẫn nhận nội dung đã sanitize.
    target.innerHTML = sanitize(untrustedComment);
  }
}
```

Chọn một thiết kế thống nhất trong ứng dụng để không sanitize hai lần không cần thiết. Policy và fallback phải dùng cùng cấu hình allowlist.

## 11. Kiểm thử TrustedHTML trong browser

Thực hiện trong môi trường phát triển do bạn kiểm soát, với dữ liệu giả.

### 11.1 Kiểm tra API có sẵn

Mở DevTools Console:

```javascript
console.log("Trusted Types supported:", Boolean(window.trustedTypes));
```

Nếu API không có, vẫn kiểm thử sanitizer và safe DOM APIs. Không dùng kết quả feature detection làm lý do bỏ qua xử lý HTML.

### 11.2 Kiểm tra enforcement

Phát response với CSP:

```http
Content-Security-Policy: require-trusted-types-for 'script'; trusted-types app-html
```

Sau đó thử:

```javascript
const target = document.querySelector("#preview");
target.innerHTML = "<p>plain string</p>";
```

Trong browser hỗ trợ enforcement, phép gán chuỗi thông thường vào sink được bảo vệ phải bị từ chối, thường bằng `TypeError`, nếu không có default policy xử lý.

### 11.3 Kiểm tra policy

```javascript
const policy = trustedTypes.createPolicy("app-html", {
  createHTML(input) {
    return DOMPurify.sanitize(input, {
      RETURN_TRUSTED_TYPE: false
    });
  }
});

const safe = policy.createHTML("<p>Đoạn văn</p>");
document.querySelector("#preview").innerHTML = safe;
```

Kết quả mong đợi là markup được allowlist giữ lại và sink chấp nhận `TrustedHTML`. Thử thêm nội dung chứa event handler hoặc URL scheme không được phép; sanitizer phải loại bỏ phần nguy hiểm theo cấu hình.

### 11.4 Kiểm tra CSP policy name

Nếu Console báo không thể tạo policy, kiểm tra:

- Header `Content-Security-Policy` có directive `trusted-types` không?
- Tên `app-html` có nằm trong danh sách được phép không?
- Có policy trùng tên hoặc code khởi tạo policy nhiều lần không?
- Response có nhiều CSP headers cùng áp dụng không?
- CSP do reverse proxy hoặc CDN có ghi đè/ghép thêm policy không?

### 11.5 Kiểm tra default policy

Trong giai đoạn migration, ghi nhận mỗi lần default policy được gọi và truy ra call site. Mục tiêu là giảm dần số lần gọi, không biến log thành một allowlist tự động. Khi đã sửa call site, xóa default policy và xác nhận các sink còn lại đều dùng policy chuyên biệt hoặc safe API.

## 12. Các lỗi thường gặp

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| Nghĩ TrustedHTML tự sanitize | Chuỗi nguy hiểm vẫn có thể được policy chấp nhận. | Gọi sanitizer trưởng thành bên trong `createHTML()`. |
| Policy trả nguyên input | Mọi chuỗi có thể được cấp nhãn tin cậy. | Không tạo policy passthrough cho dữ liệu không tin cậy. |
| Cho phép quá nhiều policy name | Nhiều module có thể tạo đường cấp TrustedHTML khó kiểm soát. | Allowlist tên policy tối thiểu bằng CSP. |
| Chỉ khai báo `trusted-types` | Policy name bị giới hạn nhưng sink chưa chắc bị enforcement. | Thêm `require-trusted-types-for 'script'` khi sẵn sàng. |
| Bật enforcement nhưng không cho phép policy cần dùng | `createPolicy()` thất bại và chức năng render bị lỗi. | Đồng bộ CSP policy name với code. |
| Default policy tồn tại mãi | Che khuất các sink chưa được refactor. | Dùng tạm, log call site và loại bỏ sau migration. |
| Browser không hỗ trợ thì dùng chuỗi thô | Mất lớp sanitization ở browser đó. | Sanitizer phải chạy độc lập với Trusted Types. |
| Dùng TrustedHTML cho URL hoặc script | Sai loại dữ liệu và sai security boundary. | Dùng validation/TrustedScript/TrustedScriptURL phù hợp. |
| Tin mọi HTML từ database | Nội dung có thể đã bị attacker lưu vào trước đó. | Sanitize tại ranh giới đưa vào HTML sink. |
| Tạo policy ở nhiều component | Khó audit, dễ trùng tên hoặc lệch cấu hình. | Tập trung policy tại module bảo mật dùng chung. |

## 13. Quy trình triển khai trong ứng dụng hiện hữu

1. **Kiểm kê sink:** tìm `innerHTML`, `outerHTML`, `insertAdjacentHTML`, `document.write`, `srcdoc` và các API parse HTML.
2. **Truy vết nguồn:** xác định dữ liệu đến từ form, API, URL, storage, postMessage hay database.
3. **Phân loại nhu cầu:** text thuần chuyển sang `textContent`; rich text cần sanitizer; nội dung không cần HTML thì loại bỏ sink.
4. **Tập trung policy:** tạo policy `app-html` ở module dùng chung và cấu hình sanitizer allowlist.
5. **Chạy Report-Only:** quan sát các vi phạm Trusted Types trong browser hỗ trợ trước khi enforcement.
6. **Sửa call site:** thay chuỗi trực tiếp bằng safe API hoặc `policy.createHTML()`.
7. **Bật enforcement:** phát `require-trusted-types-for 'script'` và chỉ cho phép policy name cần thiết.
8. **Theo dõi và duy trì:** kiểm tra report, cập nhật sanitizer và rà soát khi thêm HTML rendering feature.

### 13.1 CSP Report-Only

Có thể thử chính sách trước:

```http
Content-Security-Policy-Report-Only: require-trusted-types-for 'script'; trusted-types app-html; report-uri /csp-report
```

Report-Only giúp phát hiện những nơi đang truyền chuỗi vào sink mà không lập tức chặn chức năng. Hãy kiểm tra browser mục tiêu và endpoint nhận report; dữ liệu report cần được giới hạn và xử lý như input không tin cậy.

Khi đã xử lý các vi phạm cần thiết, chuyển sang enforcement:

```http
Content-Security-Policy: require-trusted-types-for 'script'; trusted-types app-html
```

Không chuyển sang enforcement chỉ vì số report thấp trong một lần tải trang. Cần thử các luồng sản phẩm, trang ít truy cập và chức năng editor có rich text.

## 14. Checklist bảo mật

- [ ] Đã kiểm kê HTML injection sinks và source dữ liệu.
- [ ] Nội dung text thuần dùng `textContent` hoặc safe DOM APIs.
- [ ] Chỉ rich text thực sự cần markup mới đi qua sanitizer.
- [ ] Policy `createHTML()` gọi sanitizer được duy trì với allowlist.
- [ ] Không có policy trả nguyên input.
- [ ] CSP `trusted-types` chỉ cho phép policy names cần thiết.
- [ ] CSP `require-trusted-types-for 'script'` được bật sau giai đoạn kiểm thử.
- [ ] Default policy (nếu có) chỉ là giải pháp migration và có kế hoạch loại bỏ.
- [ ] Fallback browser không hỗ trợ vẫn chạy sanitizer.
- [ ] URL, JavaScript và CSS được xử lý theo context riêng.
- [ ] Policy được tạo tập trung và review như security boundary.
- [ ] Đã kiểm thử enforcement, policy name, sink và rich-text sanitizer.
- [ ] CSP reports không lưu dữ liệu nhạy cảm quá mức.

## 15. Câu hỏi tự kiểm tra

1. `TrustedHTML` khác chuỗi HTML thông thường ở điểm nào?
2. Vì sao TrustedHTML không tự chứng minh nội dung đã được sanitize?
3. `trustedTypes.createPolicy()` và `policy.createHTML()` có vai trò gì?
4. `require-trusted-types-for 'script'` khác directive `trusted-types` như thế nào?
5. Vì sao policy trả nguyên input làm mất ý nghĩa của enforcement?
6. Khi nào nên dùng `textContent` thay cho TrustedHTML?
7. Default policy giúp migration ra sao và vì sao không nên giữ nó lâu dài?
8. Nếu browser không hỗ trợ Trusted Types, ứng dụng cần giữ lớp bảo vệ nào?
9. Vì sao TrustedHTML không thay thế URL validation hoặc TrustedScriptURL?
10. Cần kiểm tra những gì khi `createPolicy()` bị CSP từ chối?

## 16. Tổng kết

`TrustedHTML` là kiểu dữ liệu do Trusted Types API tạo ra để đánh dấu HTML đã đi qua policy được ứng dụng cho phép. Khi CSP bật `require-trusted-types-for 'script'`, các HTML injection sinks được hỗ trợ có thể từ chối chuỗi thông thường và yêu cầu TrustedHTML. Directive `trusted-types` giới hạn tên policy được phép tạo.

Giá trị bảo vệ nằm ở policy: `createHTML()` phải gọi sanitizer được duy trì với allowlist phù hợp, không trả nguyên input. Dùng `textContent` cho văn bản, TrustedHTML cho rich text đã sanitize và cơ chế riêng cho URL/script/CSS. Default policy có thể hỗ trợ migration nhưng cần log, thu hẹp và loại bỏ. Với browser chưa hỗ trợ Trusted Types, vẫn phải chạy sanitizer hoặc dùng safe DOM APIs. Hãy kiểm kê source-to-sink, thử Report-Only, bật enforcement sau khi sửa call site và kiểm tra hành vi thực tế trong browser.
