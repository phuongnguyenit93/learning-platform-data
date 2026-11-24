# Nguyên lý Trusted Types: tạo ranh giới an toàn cho DOM injection sinks

## 1. Trusted Types giải quyết vấn đề gì?

**Trusted Types** là một Web API giúp ứng dụng kiểm soát cách dữ liệu chuỗi đi vào một số DOM API có thể diễn giải dữ liệu thành HTML, JavaScript hoặc URL tải script. Mục tiêu chính là giảm DOM-based XSS do dữ liệu không tin cậy đi tới một **injection sink** như innerHTML mà không qua bước kiểm tra phù hợp.

Một ứng dụng có thể lấy nội dung từ query string rồi đưa vào DOM:

~~~js
const message = new URLSearchParams(location.search).get("message") ?? "";
document.querySelector("#preview").innerHTML = message;
~~~

innerHTML yêu cầu browser parse chuỗi thành HTML. Nếu dữ liệu có thể do người dùng kiểm soát, ứng dụng đã đưa dữ liệu không tin cậy vào một sink có khả năng tạo markup. Thay bằng textContent nếu chỉ cần hiển thị chữ:

~~~js
const message = new URLSearchParams(location.search).get("message") ?? "";
document.querySelector("#preview").textContent = message;
~~~

Trong ứng dụng lớn, việc tìm và sửa mọi sink có thể khó. Trusted Types bổ sung một ranh giới ở runtime: khi CSP enforcement được bật, một số sink yêu cầu giá trị có kiểu Trusted Type phù hợp thay vì chấp nhận chuỗi tùy ý. Ứng dụng phải tạo giá trị đó qua một **policy** được định nghĩa rõ.

Trusted Types không tự sanitize chuỗi và không tự xác định dữ liệu nào đáng tin. Policy của ứng dụng mới quyết định cách kiểm tra, lọc hoặc tạo giá trị được chấp nhận.

Bài học thuộc chương **Trusted Types** của module **SECURITY_APPLICATION_SECURITY_BROWSER_SECURITY**. Module nghiên cứu ranh giới giữa browser, origin, cookie và ứng dụng web, bao gồm phòng vệ XSS/CSRF/clickjacking bằng CSP, Trusted Types, security headers và kiểm chứng hành vi thực tế. Bài này xây dựng nền tảng để hiểu type, policy, enforcement và giới hạn của Trusted Types trong chiến lược chống DOM XSS.

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích injection sink và lý do chuỗi không tin cậy tại sink có thể gây DOM XSS.
2. Phân biệt TrustedHTML, TrustedScript và TrustedScriptURL.
3. Giải thích vai trò của trustedTypes.createPolicy và các hàm tạo giá trị tin cậy.
4. Đọc hai CSP directive trusted-types và require-trusted-types-for.
5. Xây policy HTML có sanitizer phù hợp và tránh policy trả nguyên input.
6. Hiểu default policy, rủi ro của policy quá rộng và cách dùng trong giai đoạn chuyển đổi.
7. Lập kế hoạch tìm sink, sửa luồng dữ liệu và bật enforcement dần.
8. Nêu giới hạn của Trusted Types trước XSS, browser không hỗ trợ và các context ngoài phạm vi.

## 2. Từ chuỗi đến injection sink

Trong JavaScript, phần lớn dữ liệu đến từ API, URL, storage, DOM hoặc người dùng đều được biểu diễn bằng primitive string. Chuỗi tự nó không nói lên dữ liệu an toàn hay nguy hiểm. Điều quan trọng là API nhận chuỗi đó diễn giải nó như thế nào.

Ví dụ:

~~~js
const input = getUserProvidedText();

title.textContent = input;       // Tạo text node.
container.innerHTML = input;     // Parse thành HTML.
script.src = input;              // Có thể chọn nguồn script.
~~~

Cùng một biến input, nhưng ba sink có semantics khác nhau:

- textContent coi giá trị là văn bản.
- innerHTML coi giá trị là markup.
- script.src dùng giá trị làm URL của script.

Một số sink nhạy cảm được browser xác định trong mô hình Trusted Types. Khi enforcement được bật, các sink được hỗ trợ có thể từ chối chuỗi thông thường và yêu cầu loại Trusted Type tương ứng.

### 2.1. Source, transformation và sink

Phân tích DOM XSS thường bắt đầu bằng ba phần:

| Thành phần | Câu hỏi cần trả lời | Ví dụ |
| --- | --- | --- |
| Source | Dữ liệu có thể bị ai kiểm soát? | location.search, postMessage, API, storage. |
| Transformation | Ứng dụng xử lý dữ liệu ra sao? | Decode, nối chuỗi, parse JSON, sanitize. |
| Sink | Browser diễn giải dữ liệu thành gì? | HTML fragment, script, script URL. |

Trusted Types chủ yếu giúp kiểm soát ranh giới **transformation → sink**. Nó không tự phát hiện mọi source nguy hiểm và không chứng minh rằng dữ liệu được tạo từ source tin cậy.

### 2.2. Sơ đồ hoạt động

~~~mermaid
flowchart TD
    A["Nguồn dữ liệu"] --> B["Chuỗi không tin cậy"]
    B --> C["Xử lý trong ứng dụng"]
    C --> D{"Giá trị đã qua policy phù hợp?"}
    D -->| "Chưa" | E["Chuỗi thường"]
    D -->| "Rồi" | F["TrustedHTML / TrustedScript / TrustedScriptURL"]
    E --> G["Sink được bảo vệ bởi enforcement"]
    F --> H["Sink kiểm tra kiểu và chấp nhận"]
    G --> I["TypeError / CSP violation"]
    H --> J["Browser tiếp tục xử lý theo semantics của sink"]
~~~

Khi enforcement có hiệu lực, chuỗi thường không được tự động coi là trusted. Sink yêu cầu kiểu phù hợp; policy là nơi ứng dụng chủ động tạo kiểu đó.

## 3. Ba loại Trusted Types chính

Trusted Types định nghĩa ba loại giá trị cốt lõi:

| Kiểu | Mục đích | Ví dụ ngữ cảnh |
| --- | --- | --- |
| TrustedHTML | Giá trị được phép đi vào một số HTML injection sinks | innerHTML, outerHTML, insertAdjacentHTML. |
| TrustedScript | Giá trị được phép đi vào một số JavaScript execution sinks | Một số API đánh giá chuỗi thành script. |
| TrustedScriptURL | URL được phép dùng tại một số script URL sinks | HTMLScriptElement.src. |

Tên Trusted không có nghĩa browser đã tự xác minh nội dung. Nó chỉ biểu thị giá trị được tạo qua policy mà ứng dụng cho phép. Nếu policy chấp nhận mọi chuỗi, kiểu trusted không làm dữ liệu trở nên an toàn.

### 3.1. TrustedHTML

TrustedHTML đại diện cho nội dung HTML mà policy đã kiểm tra theo quy tắc ứng dụng. Một số sink parse HTML có thể yêu cầu TrustedHTML khi enforcement được bật.

Ví dụ sink:

~~~js
target.innerHTML = trustedHtml;
target.outerHTML = trustedHtml;
target.insertAdjacentHTML("beforeend", trustedHtml);
~~~

Danh sách sink cụ thể phụ thuộc browser và API được hỗ trợ. Không suy luận rằng mọi API nhận HTML đều đã được Trusted Types bảo vệ; kiểm tra tài liệu và browser mục tiêu.

Nếu nội dung chỉ là văn bản, dùng textContent để tránh cần TrustedHTML. Chỉ tạo TrustedHTML khi sản phẩm thực sự cần render một tập markup được cho phép.

### 3.2. TrustedScript

TrustedScript đại diện cho script source đã được policy chấp thuận cho một số sink thực thi chuỗi. Các API sinh hoặc đánh giá JavaScript từ chuỗi làm tăng rủi ro vì dữ liệu có thể trở thành mã.

Hướng thiết kế ưu tiên là loại bỏ việc sinh script động:

~~~js
// Tránh biến dữ liệu thành source code.
setTimeout("refreshDashboard()", 1000);

// Dùng callback đã được định nghĩa trong code.
setTimeout(() => refreshDashboard(), 1000);
~~~

TrustedScript không phải lý do để tiếp tục dùng eval hoặc Function với dữ liệu. Nếu một hệ thống legacy thực sự cần script source động, phải xác định chính xác sink, nguồn code, allowlist và policy review; không tạo policy trả lại input nguyên trạng.

### 3.3. TrustedScriptURL

TrustedScriptURL đại diện cho URL được policy chấp thuận tại một số sink dùng để tải script. Đây là loại riêng vì URL script có thể quyết định mã nào được browser tải và thực thi.

Ví dụ:

~~~js
script.src = trustedScriptUrl;
~~~

Một policy URL cần kiểm tra URL đã parse, origin và path theo allowlist. Chỉ kiểm tra chuỗi bắt đầu bằng một prefix dễ bị lách; nên dùng URL parser và so sánh các thành phần có cấu trúc.

~~~js
const scriptUrlPolicy = trustedTypes.createPolicy("app-script-url", {
  createScriptURL(input) {
    const url = new URL(input, location.origin);

    if (
      url.origin !== location.origin ||
      !url.pathname.startsWith("/assets/")
    ) {
      throw new TypeError("Script URL không được phép");
    }

    return url.href;
  }
});

const script = document.createElement("script");
script.src = scriptUrlPolicy.createScriptURL("/assets/charts.js");
document.head.append(script);
~~~

Ví dụ này chỉ cho phép script cùng origin dưới path /assets/. Trong production, server cần tránh open redirect từ path được allowlist và CSP script-src vẫn phải giới hạn nguồn script. TrustedScriptURL không thay thế kiểm tra integrity, quản lý dependency hoặc kiểm soát quyền thực thi.

## 4. Policy là gì?

**Policy** là đối tượng do ứng dụng tạo thông qua trustedTypes.createPolicy(name, rules). Policy cung cấp các hàm như createHTML, createScript và createScriptURL. Mỗi hàm nhận dữ liệu đầu vào, thực hiện kiểm tra/biến đổi và trả về giá trị để Trusted Types đóng dấu theo kiểu tương ứng.

Ví dụ cấu trúc:

~~~js
const policy = trustedTypes.createPolicy("app-html", {
  createHTML(input) {
    // Kiểm tra và sanitize nội dung HTML tại đây.
    return sanitizeAllowedMarkup(input);
  }
});
~~~

Sau đó:

~~~js
const safeMarkup = policy.createHTML(untrustedMarkup);
target.innerHTML = safeMarkup;
~~~

Tên policy cần phản ánh mục đích cụ thể. Một ứng dụng có thể có policy cho HTML của rich text editor và một policy khác cho script URL. Không nên tạo một policy duy nhất nhận mọi loại dữ liệu và được dùng khắp ứng dụng mà không có ranh giới review.

### 4.1. Policy không tự động an toàn

Ví dụ nguy hiểm:

~~~js
const unsafePolicy = trustedTypes.createPolicy("unsafe", {
  createHTML(input) {
    return input;
  }
});
~~~

Policy này chỉ chuyển chuỗi thường thành TrustedHTML mà không kiểm tra gì. Nếu input chứa markup nguy hiểm, sink vẫn nhận nội dung đó. Enforcement bị vô hiệu hóa về mặt thực chất vì ứng dụng đã cấp quyền trusted cho mọi input.

Policy phải thực hiện đúng mục tiêu: sanitize, validate, allowlist hoặc chỉ nhận dữ liệu cố định do ứng dụng kiểm soát.

### 4.2. Giữ policy tập trung và nhỏ

Một thiết kế dễ review thường có:

- Policy được tạo ở một module bảo mật trung tâm.
- Tên policy rõ ràng và giới hạn theo CSP.
- Số lượng policy nhỏ, có owner và mục đích cụ thể.
- Không expose API tạo TrustedHTML tùy ý cho mọi module.
- Unit/integration tests cho nội dung được cho phép và bị loại bỏ.
- Ghi nhận nơi gọi policy và sink nhận kết quả.

Không để mỗi component tự tạo policy riêng mà không có tiêu chuẩn chung; điều đó làm mất khả năng kiểm soát tập trung.

## 5. Tạo TrustedHTML bằng sanitizer

Nếu ứng dụng cần hiển thị rich text do người dùng tạo, có thể cần cho phép một tập HTML giới hạn. Khi đó, sanitizer được bảo trì như DOMPurify có thể làm sạch markup trước khi policy trả kết quả.

Ví dụ:

~~~js
const htmlPolicy = trustedTypes.createPolicy("app-html", {
  createHTML(input) {
    return DOMPurify.sanitize(input, {
      RETURN_TRUSTED_TYPE: false
    });
  }
});

const userMarkup = getRichTextFromServer();
target.innerHTML = htmlPolicy.createHTML(userMarkup);
~~~

Ở đây:

- DOMPurify lọc markup theo cấu hình của ứng dụng.
- RETURN_TRUSTED_TYPE: false yêu cầu sanitizer trả chuỗi trong callback policy; chính Trusted Types policy tạo TrustedHTML.
- Sink nhận TrustedHTML thay vì chuỗi tùy ý.

Cấu hình sanitizer cần phù hợp với sản phẩm. Ví dụ, cho phép thẻ định dạng cơ bản khác với cho phép iframe, SVG, form, style hoặc thuộc tính URL. Cần cập nhật sanitizer, kiểm thử mutation XSS và tránh tự xây sanitizer bằng regex.

### 5.1. Không sanitize rồi lại làm hỏng kết quả

Sau khi sanitize, không nối thêm chuỗi chưa kiểm tra vào TrustedHTML hoặc serialize lại theo cách làm thay đổi markup. Nếu nội dung đi qua nhiều transformation, xác định bước cuối cùng trước sink và bảo đảm output cuối cùng vẫn thuộc tập markup được phép.

### 5.2. Sanitizer không thay authorization

Sanitizer quyết định markup nào được phép hiển thị. Nó không xác nhận user có quyền xem dữ liệu, không kiểm tra quyền sửa bài viết và không bảo vệ API. Backend vẫn phải xác minh authentication, authorization và ownership.

## 6. Bật enforcement bằng CSP

Trusted Types được tích hợp với CSP qua hai directive chính.

### 6.1. require-trusted-types-for

Directive:

~~~http
Content-Security-Policy: require-trusted-types-for 'script'
~~~

yêu cầu một số injection sinks được browser hỗ trợ nhận Trusted Types thay cho chuỗi thường. Từ script trong directive là token cú pháp CSP; không nên diễn giải nó thành “mọi đoạn JavaScript đều được tự động kiểm tra”.

Khi enforcement áp dụng, thao tác đưa chuỗi thường vào sink được bảo vệ có thể ném TypeError và tạo CSP violation. Hành vi cụ thể tùy sink và browser hỗ trợ.

### 6.2. trusted-types

Directive:

~~~http
Content-Security-Policy: trusted-types app-html app-script-url
~~~

giới hạn tên policy mà trang được phép tạo. Trong ví dụ, chỉ các policy app-html và app-script-url được cho phép theo directive.

Hai directive giải quyết hai việc:

| Directive | Vai trò |
| --- | --- |
| require-trusted-types-for 'script' | Bật kiểm tra kiểu tại các sink được hỗ trợ. |
| trusted-types app-html app-script-url | Giới hạn tên policy được phép tạo. |

Có thể kết hợp:

~~~http
Content-Security-Policy: default-src 'self'; script-src 'self'; object-src 'none'; base-uri 'none'; require-trusted-types-for 'script'; trusted-types app-html app-script-url
~~~

Policy name phải khớp với tên được ứng dụng tạo. Nếu CSP cho phép tên khác hoặc policy code tạo tên không được phép, browser có thể từ chối việc tạo policy.

### 6.3. Không nhầm trusted-types với script-src

trusted-types không phải danh sách host tải script. script-src kiểm soát nguồn và một số cách thực thi script; trusted-types kiểm soát tên policy; require-trusted-types-for áp dụng type enforcement cho các sink được hỗ trợ.

Cần cả CSP script-src phù hợp và Trusted Types policy có review. Một directive không thay thế directive còn lại.

## 7. Default policy và rủi ro tương thích

Trusted Types hỗ trợ một policy đặc biệt tên là **default**. Khi policy này tồn tại và browser gặp chuỗi thường tại một sink đang được enforce, browser có thể gọi default policy để chuyển đổi chuỗi thành Trusted Type phù hợp trước khi tiếp tục.

Điều này hữu ích khi chuyển đổi ứng dụng legacy có nhiều sink, nhưng cũng có rủi ro: default policy có thể âm thầm chấp nhận mọi chuỗi nếu được viết quá rộng.

### 7.1. Default policy không nên là sanitizer “cho qua”

Không viết policy mặc định trả nguyên input cho createHTML, createScript hoặc createScriptURL. Cách đó biến enforcement thành một bước chuyển kiểu hình thức và giữ nguyên đường XSS.

Nếu cần default policy trong giai đoạn migration:

- Dùng để phát hiện và ghi nhận các sink cũ.
- Áp dụng kiểm tra nghiêm ngặt theo từng loại sink.
- Trả kết quả bị từ chối khi không thể xác minh.
- Không log nội dung bí mật hoặc token trong input.
- Đặt thời hạn loại bỏ default policy sau khi sửa các call site.

Một default policy cho phép toàn bộ chuỗi có thể khiến đội phát triển tưởng rằng enforcement đã bật an toàn trong khi mọi input vẫn được chấp nhận.

### 7.2. Giới hạn tên policy bằng CSP

Nếu dùng policy tên default, CSP trusted-types cần cho phép tên default cùng các policy cụ thể khác. Chỉ thêm tên này khi ứng dụng thực sự cần và đã review logic; không bật policy mặc định như giải pháp chung cho lỗi TypeError.

## 8. Trusted Types và DOMPurify

DOMPurify là sanitizer HTML; Trusted Types là cơ chế kiểm soát kiểu tại sink. Hai công cụ có thể bổ trợ:

- DOMPurify quyết định markup nào được giữ lại.
- Trusted Types yêu cầu sink nhận kết quả từ policy đã định nghĩa.
- CSP giới hạn policy name và bật enforcement.

Một ứng dụng có thể dùng policy createHTML bọc DOMPurify như ví dụ ở phần trước. Cần đọc tài liệu của phiên bản DOMPurify đang dùng để chọn đúng tùy chọn Trusted Types; đặc biệt tránh yêu cầu sanitizer trả TrustedHTML bên trong callback vốn cần trả chuỗi cho policy.

Không cho phép HTML rộng chỉ vì đã dùng sanitizer. Cấu hình allowlist nên theo nhu cầu UI: thường loại script, event-handler attributes, URL scheme thực thi và markup không cần thiết.

## 9. Các sink và phạm vi bảo vệ

Trusted Types không bao phủ mọi API của browser. Nó bảo vệ một tập injection sinks được định nghĩa trong nền tảng và được triển khai theo browser.

Một số nhóm sink cần kiểm tra:

| Nhóm | Ví dụ đại diện | Trusted Type liên quan |
| --- | --- | --- |
| HTML parsing | innerHTML, outerHTML, insertAdjacentHTML | TrustedHTML |
| Script execution | Một số API nhận source code dạng chuỗi | TrustedScript |
| Script URL | script.src và các sink script URL được hỗ trợ | TrustedScriptURL |

Danh sách chính xác thay đổi theo API/spec và browser. Khi review, tra bảng injection sinks trong tài liệu Trusted Types hiện hành của browser mục tiêu thay vì suy rộng từ một ví dụ.

### 9.1. Không phải mọi URL đều cần TrustedScriptURL

Một liên kết điều hướng như anchor.href không tự động trở thành TrustedScriptURL chỉ vì nó là URL. TrustedScriptURL dành cho những sink dùng URL để tải script được định nghĩa trong mô hình Trusted Types.

Tuy nhiên, URL người dùng vẫn cần validation theo context. Một href có thể dùng scheme không mong muốn hoặc tạo open redirect; đó là vấn đề URL validation riêng.

### 9.2. Không phải mọi chuỗi đưa vào DOM đều bị chặn

textContent, thuộc tính title và nhiều API dữ liệu không parse markup không cần TrustedHTML. Việc chúng không bị enforcement chặn không có nghĩa dữ liệu luôn an toàn cho mọi mục đích. Nếu cùng giá trị sau đó được chuyển tới innerHTML hoặc script sink, phải đánh giá lại.

## 10. Trusted Types không phải sanitizer và không phải sandbox

Ba điều cần phân biệt:

1. **Trusted Types:** kiểm soát kiểu dữ liệu đi vào một số sink.
2. **Sanitizer:** kiểm tra và lọc nội dung theo một chính sách cho phép.
3. **Sandbox/isolation:** giới hạn quyền thực thi hoặc phạm vi ảnh hưởng của code.

Trusted Types không tự biến input thành HTML an toàn. Policy có thể tạo TrustedHTML từ dữ liệu nguy hiểm nếu code policy cho phép. Nó cũng không cô lập script đã chạy trong origin và không ngăn script độc truy cập API mà trang được quyền sử dụng.

Nếu XSS đã thực thi trong origin ứng dụng, mã độc có thể đọc DOM, gọi API, thao tác session hoặc sử dụng các policy mà ứng dụng expose. Cần phòng XSS từ source tới sink và dùng CSP, sandbox iframe, phân quyền backend theo threat model.

## 11. Quan hệ với CSP, output encoding và safe DOM APIs

Trusted Types là một lớp bổ sung trong chiến lược chống XSS:

| Biện pháp | Vai trò | Giới hạn |
| --- | --- | --- |
| Output encoding theo context | Giữ dữ liệu là dữ liệu trong HTML/attribute/JS context | Cần đúng context và đúng serializer. |
| textContent / createElement | Tránh parse dữ liệu như HTML khi chỉ cần text/DOM node | Không giải quyết URL hoặc mọi thuộc tính nhạy cảm. |
| HTML sanitizer | Cho phép một tập markup đã lọc | Cấu hình và cập nhật sanitizer là trách nhiệm ứng dụng. |
| Trusted Types | Chặn chuỗi thường tại các sink được hỗ trợ | Policy có thể viết sai; không phải sanitizer. |
| CSP script-src | Giới hạn nguồn script và cách thực thi | Không thay output handling và authorization. |
| Backend authorization | Kiểm soát user có quyền làm gì | Không ngăn browser parse markup nguy hiểm. |

Ưu tiên sửa code để không cần HTML sink. Khi cần rich text, sanitize; sau đó dùng Trusted Types để buộc call site đi qua policy đã review.

## 12. Browser support và feature detection

Trusted Types là Web Platform API, nhưng mức hỗ trợ và enforcement không đồng nhất giữa mọi browser/version. Một ứng dụng cần xác định browser mục tiêu, kiểm tra hỗ trợ và thử nghiệm policy trước khi bật enforcement rộng.

Feature detection cơ bản:

~~~js
if (window.trustedTypes) {
  // Browser có cung cấp Trusted Types API.
  const policy = trustedTypes.createPolicy("app-html", {
    createHTML(input) {
      return DOMPurify.sanitize(input, {
        RETURN_TRUSTED_TYPE: false
      });
    }
  });
} else {
  // Fallback vẫn phải dùng sanitizer và safe DOM APIs.
}
~~~

Feature detection chỉ cho biết API hiện diện. Nó không chứng minh CSP enforcement đang bật, mọi sink đều được bảo vệ hoặc policy được cấu hình đúng.

Với browser không hỗ trợ Trusted Types, ứng dụng vẫn phải dùng safe DOM APIs, output encoding, sanitizer và CSP phù hợp. Không được dựa vào việc browser cũ bỏ qua enforcement như một lý do để chấp nhận input không an toàn.

## 13. Lộ trình đưa Trusted Types vào ứng dụng đang chạy

Bật enforcement ngay trên một ứng dụng legacy có nhiều innerHTML call site có thể làm hỏng giao diện. Nên chuyển đổi có kiểm soát.

### Bước 1 — Kiểm kê sinks

Tìm các API và luồng có thể đưa dữ liệu vào HTML/script sinks:

- innerHTML, outerHTML, insertAdjacentHTML.
- document.write và các parser API.
- eval, Function và timer nhận string.
- script.src và loader tải script động.
- Wrapper/helper nội bộ gọi các API trên.

Không chỉ tìm bằng tên API; một abstraction có thể che giấu sink phía dưới.

### Bước 2 — Theo dõi source-to-sink

Với mỗi sink, xác định dữ liệu đến từ URL, API, storage, postMessage, nội dung người dùng hay code cố định. Đánh giá transformation hiện có và xem liệu sink có thực sự cần parse HTML/script không.

### Bước 3 — Thay sink khi có thể

- Thay innerHTML dùng để hiển thị chữ bằng textContent.
- Dùng createElement, setAttribute cho thuộc tính không thực thi và addEventListener cho hành vi.
- Thay timer string bằng callback.
- Loại bỏ eval/Function nếu có thể.
- Dùng URL allowlist cho script loader.

### Bước 4 — Tạo policy nhỏ, có review

Chỉ tạo policy cho nhu cầu thực tế. Policy HTML cần sanitizer; policy script URL cần allowlist chặt; tránh policy generic nhận mọi string.

### Bước 5 — Quan sát ở Report-Only

Triển khai CSP Report-Only có các directive Trusted Types phù hợp trong môi trường thử nghiệm/browser hỗ trợ. Thu thập vi phạm và sửa các call site hợp lệ. Report-Only giúp quan sát; nó chưa enforce việc từ chối sink theo policy đó.

### Bước 6 — Enforce ở staging

Bật Content-Security-Policy với require-trusted-types-for 'script' và trusted-types policy name được phép. Chạy các luồng quan trọng: login, form, rich text, upload preview, editor, dashboard và trang có script loader.

### Bước 7 — Triển khai và giám sát

Rollout theo nhóm người dùng hoặc ứng dụng nếu hạ tầng hỗ trợ. Theo dõi TypeError, CSP violation, lỗi UI và báo cáo browser. Có kế hoạch rollback policy nhưng giữ safe DOM handling trong code.

## 14. Ví dụ hoàn chỉnh: rich text an toàn với Trusted Types

Giả sử sản phẩm có trường mô tả cho phép định dạng cơ bản như đoạn văn, danh sách, chữ đậm và liên kết. Server nhận rich text và lưu nội dung; browser cần hiển thị.

CSP ví dụ:

~~~http
Content-Security-Policy: default-src 'self'; script-src 'self'; object-src 'none'; base-uri 'none'; require-trusted-types-for 'script'; trusted-types app-html
~~~

JavaScript:

~~~js
const htmlPolicy = trustedTypes.createPolicy("app-html", {
  createHTML(input) {
    return DOMPurify.sanitize(input, {
      ALLOWED_TAGS: [
        "p", "br", "strong", "em", "ul", "ol", "li", "a"
      ],
      ALLOWED_ATTR: ["href", "title"],
      RETURN_TRUSTED_TYPE: false
    });
  }
});

function renderDescription(container, untrustedDescription) {
  const trustedMarkup = htmlPolicy.createHTML(untrustedDescription);
  container.innerHTML = trustedMarkup;
}
~~~

Cần kiểm tra URL của liên kết theo policy sanitizer, không cho phép scheme thực thi. Nếu ứng dụng không cần markup, giải pháp đơn giản hơn là textContent và không tạo TrustedHTML.

### 14.1. Vì sao cần cả policy lẫn enforcement?

- Policy định nghĩa cách tạo TrustedHTML.
- CSP giới hạn policy name được tạo.
- require-trusted-types-for bật type check ở sink hỗ trợ.
- innerHTML nhận giá trị do policy tạo.

Nếu bỏ enforcement, code khác vẫn có thể đưa chuỗi thường vào sink. Nếu policy trả nguyên input, policy không tạo ra nội dung an toàn. Nếu CSP không giới hạn tên policy, module khác có thể tạo thêm policy ngoài dự kiến. Cần phối hợp cả ba.

## 15. Kiểm thử policy và sanitizer

Policy cần test như một thành phần bảo mật, không chỉ test rằng hàm createHTML trả về một object.

Những trường hợp nên kiểm tra:

- Markup hợp lệ được cho phép theo yêu cầu UI.
- Thẻ và thuộc tính không được phép bị loại bỏ.
- URL trong href chỉ dùng scheme được cho phép.
- Event handler attributes bị loại bỏ.
- Nội dung SVG/MathML hoặc namespace đặc biệt được xử lý theo policy.
- Input malformed và Unicode không làm sanitizer lỗi hoặc thay đổi semantics ngoài ý muốn.
- Nội dung có chuỗi giống thẻ đóng script không phá HTML template.
- Sink được enforce từ chối string thường.
- Policy name không được CSP cho phép bị từ chối.
- Browser không hỗ trợ vẫn dùng fallback an toàn.

Không tự viết payload tấn công thực thi để test production. Dùng test fixture trong môi trường kiểm soát và xác minh DOM kết quả.

## 16. Những lỗi thiết kế thường gặp

1. **Policy trả nguyên input:** tạo TrustedHTML nhưng không sanitize.
2. **Một policy dùng cho mọi thứ:** trộn HTML, script và script URL với quy tắc quá rộng.
3. **Tên policy không bị giới hạn:** thiếu CSP trusted-types khiến policy mới có thể được tạo ngoài dự kiến.
4. **Chỉ bật require-trusted-types-for:** enforcement có thể làm vỡ code cũ nếu chưa migration; cần xử lý sink và policy.
5. **Tạo default policy quá rộng:** tự động chấp nhận mọi chuỗi và che giấu sink chưa được sửa.
6. **Dùng TrustedScript để hợp thức hóa eval:** tiếp tục sinh code động từ input.
7. **Dùng TrustedScriptURL chỉ kiểm tra prefix:** URL parser, origin, path và redirect không được kiểm soát đầy đủ.
8. **Cho phép policy sanitizer quá rộng:** HTML có thể chứa thẻ, thuộc tính hoặc URL không cần thiết.
9. **Tưởng mọi sink đều được bảo vệ:** Trusted Types chỉ áp dụng cho tập sink được định nghĩa và hỗ trợ.
10. **Bỏ qua browser cũ:** fallback không dùng Trusted Types vẫn phải an toàn.
11. **Nhầm Trusted Types với CSP script-src:** hai cơ chế giải quyết vấn đề khác nhau.
12. **Cho rằng XSS đã bị loại bỏ hoàn toàn:** script độc chạy cùng origin vẫn có thể dùng DOM/API và policy được expose.

## 17. Thực hành A — Quan sát sink bị chặn khi enforcement bật

Trên trang local/staging do bạn kiểm soát, tạo một trang đơn giản:

~~~html
<div id="output"></div>
<script src="/assets/tt-demo.js" defer></script>
~~~

JavaScript demo:

~~~js
const value = "<strong>Trusted Types demo</strong>";
document.querySelector("#output").innerHTML = value;
~~~

Bật CSP trên response:

~~~http
Content-Security-Policy: require-trusted-types-for 'script'; trusted-types app-html
~~~

Trên browser hỗ trợ enforcement, quan sát Console và DOM. Sink được bảo vệ có thể từ chối chuỗi thường và phát sinh TypeError/CSP violation.

**Mục tiêu:** xác nhận enforcement kiểm soát việc truyền string vào sink. Không dùng dữ liệu thật hoặc triển khai thử trên production.

## 18. Thực hành B — Tạo policy HTML có sanitizer

Thêm DOMPurify đã được cài đặt và phục vụ từ nguồn tin cậy. Tạo policy:

~~~js
const htmlPolicy = trustedTypes.createPolicy("app-html", {
  createHTML(input) {
    return DOMPurify.sanitize(input, {
      ALLOWED_TAGS: ["p", "strong", "em", "ul", "li"],
      ALLOWED_ATTR: [],
      RETURN_TRUSTED_TYPE: false
    });
  }
});
~~~

Sau đó:

~~~js
const userContent = getTestContent();
document.querySelector("#output").innerHTML =
  htmlPolicy.createHTML(userContent);
~~~

Quan sát tab Elements để xác minh chỉ markup trong allowlist còn lại. Thử chuỗi text bình thường, thẻ định dạng được cho phép và thẻ/attribute không được phép trong fixture test.

**Mục tiêu:** policy chỉ cấp TrustedHTML sau khi sanitizer thực hiện công việc.

## 19. Thực hành C — Giới hạn policy name bằng CSP

Dùng header:

~~~http
Content-Security-Policy: require-trusted-types-for 'script'; trusted-types app-html
~~~

Trong Console, thử tạo policy với tên được phép và một tên không nằm trong allowlist:

~~~js
trustedTypes.createPolicy("app-html", {
  createHTML(input) {
    return input;
  }
});
~~~

~~~js
trustedTypes.createPolicy("unapproved-policy", {
  createHTML(input) {
    return input;
  }
});
~~~

Lưu ý: ví dụ policy đầu tiên chỉ để quan sát việc kiểm soát tên trong môi trường test; callback trả nguyên input không phải policy an toàn để dùng cho nội dung thực. Quan sát policy không được phép bị CSP từ chối trên browser hỗ trợ.

**Mục tiêu:** phân biệt việc cho phép tên policy với việc policy có logic an toàn.

## 20. Thực hành D — Migration từ sink cũ sang API an toàn

Tạo một danh sách call site giả lập trong ứng dụng demo:

~~~js
function renderTitle(value) {
  document.querySelector("#title").innerHTML = value;
}

function renderPlainMessage(value) {
  document.querySelector("#message").textContent = value;
}

function scheduleRefresh() {
  setTimeout("refreshDashboard()", 1000);
}
~~~

Refactor:

~~~js
function renderTitle(value) {
  document.querySelector("#title").textContent = value;
}

function renderPlainMessage(value) {
  document.querySelector("#message").textContent = value;
}

function scheduleRefresh() {
  setTimeout(() => refreshDashboard(), 1000);
}
~~~

Nếu renderTitle thực sự cần rich HTML, thay bằng policy sanitizer có test thay vì dùng textContent. Bật enforcement trong staging và kiểm tra các luồng giao diện còn lại.

**Mục tiêu:** loại bỏ sink không cần thiết trước khi tạo policy mới.

## 21. Checklist review Trusted Types

- [ ] Xác định browser mục tiêu và khả năng hỗ trợ Trusted Types enforcement.
- [ ] Kiểm kê HTML, script và script URL injection sinks.
- [ ] Lần theo source và transformation tới từng sink.
- [ ] Thay sink bằng textContent/createElement/callback khi không cần parse HTML hoặc script.
- [ ] Chỉ tạo TrustedHTML khi thật sự cần render markup.
- [ ] Dùng sanitizer được bảo trì và cấu hình allowlist nhỏ nhất cần thiết.
- [ ] Dùng RETURN_TRUSTED_TYPE phù hợp khi bọc DOMPurify trong createHTML policy.
- [ ] Không tạo policy trả nguyên input.
- [ ] Tách policy theo mục đích: HTML, script hoặc script URL.
- [ ] Giới hạn tên policy bằng CSP trusted-types.
- [ ] Bật require-trusted-types-for 'script' sau khi đã migration và kiểm thử.
- [ ] Tránh default policy rộng; nếu cần migration, ghi nhận và có kế hoạch loại bỏ.
- [ ] Với TrustedScriptURL, parse URL và allowlist origin/path; kiểm soát redirect.
- [ ] Giữ CSP script-src, output encoding và URL validation.
- [ ] Không xem Trusted Types là sanitizer, sandbox hoặc authorization.
- [ ] Xử lý browser không hỗ trợ bằng fallback vẫn an toàn.
- [ ] Test cả nội dung được phép, nội dung bị loại và sink bị từ chối.
- [ ] Theo dõi CSP reports, TypeError và lỗi giao diện khi rollout.
- [ ] Không log dữ liệu nhạy cảm khi ghi nhận vi phạm.
- [ ] Review policy code như một thành phần bảo mật quan trọng.

## 22. Những ngộ nhận thường gặp

| Nhận định | Đánh giá | Giải thích |
| --- | --- | --- |
| “Trusted Types tự sanitize mọi chuỗi.” | **Sai** | Policy của ứng dụng phải kiểm tra hoặc sanitize. |
| “TrustedHTML có nghĩa nội dung luôn an toàn.” | **Sai** | Policy có thể cấp TrustedHTML cho input nguy hiểm. |
| “Chỉ cần tạo policy là enforcement đã bật.” | **Sai** | Cần CSP require-trusted-types-for 'script' để enforce tại sink được hỗ trợ. |
| “trusted-types và require-trusted-types-for giống nhau.” | **Sai** | Một directive giới hạn policy name, directive kia bật type enforcement. |
| “TrustedScript là cách an toàn để dùng eval với input.” | **Sai** | Tránh sinh JavaScript source từ dữ liệu. |
| “TrustedScriptURL chỉ cần kiểm tra chuỗi bắt đầu bằng /assets/.” | **Sai** | Cần parse URL, kiểm tra origin/path và kiểm soát redirect. |
| “Mọi URL đều cần TrustedScriptURL.” | **Sai** | Kiểu này dành cho các script URL sinks được hỗ trợ. |
| “Default policy là lựa chọn tốt nhất cho mọi ứng dụng.” | **Sai** | Policy quá rộng có thể âm thầm chấp nhận chuỗi không an toàn. |
| “Trusted Types chặn XSS đã chạy trong origin.” | **Sai** | Script độc vẫn có thể thao tác DOM/API và gọi policy được expose. |
| “CSP script-src thay thế Trusted Types.” | **Sai** | Chúng kiểm soát các lớp khác nhau và có thể bổ trợ. |
| “Browser không hỗ trợ Trusted Types thì không cần quan tâm sink.” | **Sai** | Safe DOM APIs, sanitizer và output encoding vẫn bắt buộc. |
| “Nếu TypeError biến mất thì ứng dụng đã an toàn.” | **Sai** | Policy có thể đang chấp nhận mọi input; cần review logic và kết quả DOM. |

## 23. Tổng kết

Trusted Types tạo một ranh giới kiểu dữ liệu tại một số DOM injection sinks. Khi CSP enforcement được bật, sink được hỗ trợ có thể từ chối chuỗi thường và yêu cầu giá trị tương ứng như TrustedHTML, TrustedScript hoặc TrustedScriptURL. Ứng dụng tạo các giá trị đó qua policy có tên và logic cụ thể.

Ba nguyên tắc cần nhớ:

1. **Policy chịu trách nhiệm về nội dung:** Trusted Types không tự sanitize. Policy HTML cần sanitizer phù hợp; policy script URL cần parse và allowlist chặt; tránh tạo script từ input.
2. **CSP bật và giới hạn enforcement:** require-trusted-types-for 'script' kiểm soát sink được hỗ trợ; trusted-types giới hạn policy name. Kết hợp với script-src và CSP tổng thể.
3. **Sửa source-to-sink trước, dùng policy cho phần thật sự cần:** ưu tiên textContent, createElement và callback; chỉ dùng TrustedHTML khi phải render markup. Giữ fallback an toàn cho browser không hỗ trợ và nhớ Trusted Types không ngăn mã độc đã chạy trong origin.

Khi review một sink, hãy hỏi: **dữ liệu đến từ đâu, sink diễn giải nó thành gì, có thể tránh sink không, policy nào tạo Trusted Type, policy kiểm tra điều gì, CSP có giới hạn policy đó không, và browser mục tiêu có enforce không?** Trả lời rõ các câu hỏi này giúp Trusted Types trở thành ranh giới kiểm soát có ý nghĩa trong phòng vệ DOM XSS.
