# Cross-browser test

Kiểm thử đa trình duyệt (cross-browser test) xác nhận rằng một ứng dụng web giữ nguyên các yêu cầu bảo mật trên những trình duyệt, engine, phiên bản và nền tảng mà sản phẩm hỗ trợ. Cùng một chuẩn web có thể được triển khai với khác biệt về thời điểm cập nhật, chính sách quyền riêng tư, lưu trữ bên thứ ba, quyền thiết bị và vòng đời API. Một ca chạy tốt trên Chrome chưa đủ để kết luận ứng dụng an toàn trên Firefox hoặc Safari.

Bài học thuộc module <code>SECURITY_APPLICATION_SECURITY_BROWSER_SECURITY</code>, tập trung vào ranh giới bảo mật giữa trình duyệt, origin, cookie và ứng dụng web. Các ca kiểm thử liên hệ trực tiếp với Same-Origin Policy (SOP), CORS và cơ chế cách ly; đồng thời xác minh cách CSP, Trusted Types và security headers hỗ trợ phòng vệ XSS, CSRF, clickjacking trong các môi trường trình duyệt khác nhau.

## Mục tiêu

Sau bài học, bạn có thể:

- Lập ma trận kiểm thử theo browser engine, trình duyệt, phiên bản, hệ điều hành và cấu hình quyền riêng tư.
- Phân biệt khác biệt triển khai của trình duyệt với lỗi bảo mật trong ứng dụng.
- Kiểm tra các bất biến bảo mật của SOP, CORS, cookie, CSP, iframe sandbox, postMessage, storage và service worker.
- Tự động hóa cùng một bộ kiểm thử trên Chromium, Firefox và WebKit bằng Playwright.
- Bổ sung kiểm thử trên trình duyệt và thiết bị thực khi môi trường giả lập chưa phản ánh đầy đủ hành vi production.
- Ghi nhận kết quả có thể tái hiện, kèm bằng chứng đủ để xác định nguyên nhân.

## 1. Cross-browser test kiểm tra điều gì?

Mỗi trình duyệt có nhiều lớp cần phân biệt:

- **Trình duyệt:** sản phẩm người dùng cài đặt, ví dụ Chrome, Edge, Firefox hoặc Safari.
- **Browser engine:** thành phần xử lý HTML, CSS, JavaScript và nhiều chính sách nền tảng. Các engine phổ biến gồm Chromium/Blink, Firefox/Gecko và WebKit.
- **Phiên bản:** phiên bản trình duyệt và engine tại thời điểm kiểm thử.
- **Nền tảng:** Windows, macOS, Linux, Android hoặc iOS.
- **Cấu hình:** chế độ riêng tư, chặn cookie bên thứ ba, chính sách theo dõi, quyền đã cấp, extension và chính sách doanh nghiệp.
- **Ngữ cảnh chạy:** tab thông thường, iframe, popup, webview hoặc trình duyệt nhúng trong ứng dụng.

Nhiều trình duyệt có thể dùng chung một engine nhưng vẫn khác nhau về giao diện quyền, cấu hình mặc định, cơ chế cập nhật, tích hợp hệ điều hành và chính sách quyền riêng tư. Vì vậy, kiểm thử theo tên thương hiệu là chưa đủ; cần ghi nhận engine và cấu hình thực tế.

Cross-browser test bảo mật tập trung vào **kết quả bảo mật quan sát được**. Ví dụ, trang khác origin phải không đọc được DOM riêng tư; response CORS chỉ được expose cho origin hợp lệ; cookie chỉ được gửi trong ngữ cảnh đáp ứng chính sách; iframe bị giới hạn đúng theo sandbox; script bị CSP chặn phải không thực thi. Thông báo Console, câu chữ exception, cách hiển thị hộp thoại hoặc thời gian hoàn thành có thể khác nhau giữa các trình duyệt.

Không yêu cầu mọi trình duyệt có cùng thông báo lỗi hoặc giao diện. Hãy xác định hành vi bảo mật mà ứng dụng cần giữ, sau đó kiểm tra từng engine bằng assertion phù hợp.

## 2. Xây dựng ma trận trình duyệt

### Chọn phạm vi theo rủi ro

Bắt đầu từ danh sách trình duyệt và phiên bản sản phẩm thực sự hỗ trợ. Một ma trận cơ sở thường bao gồm:

| Nhóm | Môi trường đại diện | Mục đích |
|---|---|---|
| Chromium desktop | Chrome hoặc Edge phiên bản ổn định hiện hành | Kiểm tra luồng chính trên engine Chromium |
| Firefox desktop | Firefox phiên bản ổn định hiện hành | Kiểm tra engine Gecko và chính sách riêng |
| Safari desktop | Safari trên macOS thực tế | Kiểm tra WebKit trong sản phẩm Safari |
| Chromium mobile | Chrome trên Android hoặc thiết bị Android hỗ trợ | Kiểm tra viewport, quyền và chính sách mobile |
| Safari mobile | Safari trên iOS/iPadOS được hỗ trợ | Kiểm tra WebKit trên thiết bị Apple |
| WebView | Android WebView hoặc WKWebView nếu ứng dụng nhúng sử dụng | Kiểm tra container và chính sách của ứng dụng chủ |

Playwright có thể chạy các project Chromium, Firefox và WebKit. WebKit do Playwright cung cấp rất hữu ích để phát hiện nhiều khác biệt của engine, nhưng không nên xem đó là phép thay thế hoàn toàn cho Safari phát hành trên macOS hoặc iOS. Với sản phẩm hỗ trợ Safari, hãy có ít nhất một vòng xác minh trên Safari thực tế. Nếu ứng dụng chạy trong WebView, kiểm tra chính WebView và phiên bản hệ điều hành được hỗ trợ.

Đối với mỗi engine, nên kiểm tra phiên bản ổn định mới nhất và phiên bản tối thiểu mà sản phẩm cam kết hỗ trợ. Có thể thêm bản beta hoặc bản preview cho luồng bảo mật quan trọng để phát hiện thay đổi sớm. Không cần chạy mọi tổ hợp phiên bản, thiết bị và cấu hình ở mọi lần build; hãy chọn tổ hợp dựa trên mức độ rủi ro và mức độ phổ biến của người dùng.

### Các chiều cấu hình cần ghi nhận

| Chiều | Ví dụ giá trị | Vì sao cần ghi nhận |
|---|---|---|
| Browser và engine | Chrome/Chromium, Firefox/Gecko, Safari/WebKit | Xác định phạm vi triển khai |
| Phiên bản | Phiên bản hiện tại, phiên bản tối thiểu | Phát hiện thay đổi hoặc thiếu API |
| Hệ điều hành | Windows, macOS, Android, iOS | Quyền hệ thống và tích hợp nền tảng có thể khác |
| Cookie bên thứ ba | Cho phép, chặn mặc định, ngoại lệ | Ảnh hưởng luồng đăng nhập nhúng và tracking |
| Chế độ riêng tư | Profile thông thường, private/incognito | Có thể thay đổi lưu trữ và thời hạn dữ liệu |
| Quyền thiết bị | Granted, denied, prompt, policy-blocked | Ảnh hưởng camera, microphone, clipboard, geolocation |
| Extension/chính sách | Profile sạch, profile doanh nghiệp | Có thể can thiệp request hoặc quyền |

Hãy giữ một profile sạch làm mốc. Khi điều tra lỗi, tạo thêm profile với đúng chính sách quyền riêng tư hoặc extension cần tái hiện. Không trộn kết quả của profile có extension với kết quả của profile sạch.

### Giảm số tổ hợp mà vẫn giữ độ bao phủ

Không nên nhân tất cả chiều cấu hình với nhau thành một ma trận khổng lồ. Dùng cách tiếp cận theo rủi ro:

1. Chạy bộ smoke test bảo mật trên cả ba engine chính sau mỗi thay đổi lớn.
2. Chạy các ca liên quan tới nền tảng trên hệ điều hành và thiết bị thực mà sản phẩm hỗ trợ.
3. Ưu tiên tổ hợp có thay đổi về cookie bên thứ ba, quyền, storage partitioning hoặc service worker.
4. Dùng kiểm thử pairwise cho các chiều cấu hình ít rủi ro hơn.
5. Chạy lại toàn bộ ca liên quan khi thay đổi CSP, CORS, cookie, xác thực, iframe hoặc luồng đăng nhập.

Ghi rõ tổ hợp nào đã được kiểm tra và tổ hợp nào chưa được kiểm tra. Không suy rộng kết quả của Chrome desktop thành kết quả cho toàn bộ trình duyệt mobile.

## 3. Chuẩn bị môi trường kiểm thử an toàn

### Tạo các origin do nhóm kiểm soát

Dùng host thử nghiệm riêng, chẳng hạn:

| Vai trò | Origin ví dụ | Dữ liệu hoặc hành vi |
|---|---|---|
| Ứng dụng chính | <code>https://app.example.test</code> | Trang tài khoản và marker riêng tư giả lập |
| API | <code>https://api.example.test</code> | Endpoint có CORS allowlist |
| Portal được tin cậy | <code>https://portal.example.test</code> | Client được phép đọc API |
| Trang không tin cậy | <code>https://attacker.test</code> | Thử truy cập cross-origin |
| Nội dung nhúng | <code>https://preview.example.test</code> | Iframe sandbox và preview |
| Host HTTP thử nghiệm | <code>http://legacy.example.test</code> | Ca mixed content hoặc chuyển hướng HTTPS |

Các host cần trỏ tới môi trường local/QA do nhóm kiểm soát. Dùng HTTPS với chứng chỉ được trình duyệt tin cậy khi kiểm tra cookie Secure, service worker, Permissions API hoặc hành vi secure context. Chỉ tạo endpoint HTTP khi cần kiểm tra một tình huống cụ thể như mixed content hoặc chuyển hướng sang HTTPS.

Dữ liệu trong lab phải là dữ liệu tổng hợp. Tạo marker như <code>APP-PRIVATE-MARKER-001</code>, cookie giả lập và tài khoản kiểm thử riêng. Không đưa token production, cookie phiên thật hoặc dữ liệu cá nhân vào test fixture.

### Làm cho fixture ổn định

Mỗi fixture nên có hành vi xác định và dễ quan sát:

- Endpoint CORS trả cùng một payload giả lập; allowlist chỉ thay đổi theo ca kiểm thử.
- Endpoint preflight hỗ trợ đúng method và header được yêu cầu.
- Trang CSP có một script inline cần bị chặn và một script ngoài được phép để quan sát kết quả.
- Iframe sandbox có marker riêng, route và tập token sandbox được cố định.
- Endpoint cookie ghi nhận request có nhận cookie hay không mà không ghi giá trị cookie ra log.
- Service worker có phiên bản cache rõ ràng và route kiểm tra trạng thái điều khiển.
- Mỗi test có thể tạo và xóa dữ liệu của chính nó.

Không phụ thuộc vào một website bên ngoài để làm fixture. Chính sách của website bên ngoài có thể thay đổi và khiến kết quả không thể tái hiện.

### Cố định điều kiện chạy

Trước khi so sánh kết quả, xác nhận:

- Tất cả browser truy cập cùng một bản build và cùng dữ liệu fixture.
- Đồng hồ, timezone và trạng thái đăng nhập không làm thay đổi kết quả.
- Cache, service worker và storage được tạo mới hoặc dọn theo quy trình của test.
- Chứng chỉ HTTPS hợp lệ; không bật tùy chọn bỏ qua lỗi chứng chỉ để che lỗi cấu hình.
- Các request và response có thể được quan sát trong Network hoặc log server.
- Mỗi lần chạy ghi lại browser, engine, phiên bản, hệ điều hành và cấu hình quyền riêng tư.

Dùng browser context riêng cho từng test hoặc từng nhóm test. Điều này giúp tránh cookie, localStorage, IndexedDB và service worker của ca trước làm thay đổi ca sau.

## 4. Kiểm thử các bất biến bảo mật trên nhiều trình duyệt

### Origin và Same-Origin Policy

Tạo một trang ở <code>attacker.test</code> nhúng trang <code>app.example.test</code>. Thử đọc marker trong DOM và vùng lưu trữ của ứng dụng. Kết quả mong đợi là script ở origin khác không đọc được dữ liệu đó. Lặp lại với trang cùng origin để xác nhận fixture hoạt động.

Kiểm tra ít nhất các trường hợp:

- Cùng scheme, host và port nhưng khác path: cùng origin.
- Khác scheme, host hoặc port: khác origin.
- Subdomain khác nhau: khác origin, kể cả khi cùng site.
- Iframe sandbox không có <code>allow-same-origin</code>: tài liệu có opaque origin.
- Popup hoặc cửa sổ được mở từ origin khác: chỉ truy cập được những thuộc tính mà SOP cho phép.

Không so sánh nguyên văn exception giữa các browser. Có thể kiểm tra thao tác đọc bị từ chối và ghi nhận tên exception nếu có, nhưng assertion chính phải mô tả quyền truy cập dữ liệu.

### CORS và preflight

CORS cần được kiểm tra ở cả đường được phép và đường bị từ chối:

| Ca kiểm thử | Kết quả mong đợi |
|---|---|
| Origin được allowlist, response hợp lệ | JavaScript đọc được response theo cấu hình |
| Origin không nằm trong allowlist | JavaScript không đọc được response |
| Preflight yêu cầu method/header không được cho phép | Browser không thực hiện request chính sau preflight thất bại |
| Request đơn giản không cần preflight nhưng response không được expose | Server có thể nhận request, JavaScript vẫn không đọc được response |
| Credentials đi kèm wildcard origin | Browser từ chối expose response theo quy tắc CORS |
| Server phản chiếu Origin tùy ý | Test phát hiện cấu hình allowlist không an toàn |
| Response thay đổi theo Origin | Cache xử lý đúng <code>Vary: Origin</code> khi cần |

Cần phân biệt **request đã gửi** với **response được JavaScript đọc**. CORS chủ yếu kiểm soát việc browser expose response cho script. Một request đơn giản vẫn có thể tới server dù script không đọc được response. Vì vậy, với endpoint có tác dụng phụ, kiểm tra cả log server và trạng thái dữ liệu; không kết luận request không xảy ra chỉ vì <code>fetch()</code> bị reject.

Thông báo lỗi CORS trong Console có thể khác giữa Chromium, Firefox và WebKit. Hãy xác nhận status của preflight, request chính, response header và khả năng đọc body thay vì so khớp một chuỗi lỗi.

### Cookie và chính sách quyền riêng tư

Kiểm tra cookie trong các ngữ cảnh:

- Cookie host-only và cookie có thuộc tính Domain.
- <code>Secure</code>, <code>HttpOnly</code>, <code>Path</code> và thời hạn.
- <code>SameSite=Strict</code>, <code>Lax</code> và <code>None; Secure</code>.
- Điều hướng top-level, request fetch và iframe cross-site.
- Profile thông thường, chế độ riêng tư và cấu hình chặn cookie bên thứ ba.
- Cookie partitioned nếu sản phẩm có sử dụng và browser mục tiêu hỗ trợ.

Các trình duyệt có thể áp dụng biện pháp hạn chế cookie bên thứ ba ở mức mặc định hoặc theo cơ chế theo dõi riêng. Do đó, xác định rõ sản phẩm cần hỗ trợ luồng nào: đăng nhập top-level, đăng nhập trong iframe, SSO, thanh toán chuyển hướng hay nhúng nội dung. Viết kỳ vọng theo chính sách sản phẩm và browser được hỗ trợ; không mặc định rằng mọi trình duyệt đều gửi cookie trong iframe cross-site.

Dùng endpoint thử nghiệm ghi nhận cookie có xuất hiện trong request hay không. Không ghi giá trị cookie ra log hoặc báo cáo. Với cookie HttpOnly, xác nhận JavaScript không đọc được cookie qua <code>document.cookie</code> nhưng browser vẫn gửi cookie trong request phù hợp.

Nếu luồng cần cookie bên thứ ba nhưng browser chặn theo mặc định, kiểm tra phương án đăng nhập top-level hoặc cơ chế thay thế đã được sản phẩm thiết kế. Không tắt cơ chế bảo vệ của trình duyệt để biến test thành pass.

### CSP, Trusted Types và security headers

Với mỗi browser, kiểm tra header được trả về và hành vi thực thi:

- <code>Content-Security-Policy</code> có chặn script inline, nguồn script ngoài và frame theo chính sách dự kiến không.
- <code>Content-Security-Policy-Report-Only</code> có ghi nhận vi phạm mà chưa chặn nội dung không.
- <code>frame-ancestors</code> có ngăn trang bị nhúng từ origin không được phép không.
- <code>X-Frame-Options</code> có được cấu hình phù hợp cho các browser hoặc hệ thống cũ cần hỗ trợ không.
- <code>X-Content-Type-Options: nosniff</code> có được gửi cho response cần bảo vệ không.
- <code>Referrer-Policy</code> có giới hạn dữ liệu referrer theo yêu cầu không.
- Trusted Types có được thực thi trên các browser mục tiêu có hỗ trợ không.

Không chỉ kiểm tra header xuất hiện trong Network. Cần xác nhận hành vi: script không được phép không chạy, frame không được phép không hiển thị nội dung ứng dụng và vi phạm được ghi nhận theo cơ chế đã cấu hình.

Trusted Types có mức hỗ trợ khác nhau giữa các browser. Nếu ứng dụng yêu cầu tính năng này, hãy đưa điều kiện hỗ trợ vào ma trận và xác định hành vi an toàn khi API không tồn tại. Feature detection có thể cho biết API hiện diện; nó không thay thế yêu cầu kiểm thử rằng sink nguy hiểm đã được bảo vệ. Không dựa riêng vào Trusted Types để phòng vệ XSS trên mọi trình duyệt.

Thông điệp CSP trong Console không phải giao diện ổn định để assertion. Dùng marker, request, trạng thái DOM và báo cáo CSP làm bằng chứng.

### Iframe sandbox và postMessage

Với iframe, kiểm tra cùng một bộ URL và token sandbox trên mọi engine:

- Script trong iframe không có quyền vượt quá tập token được cấp.
- Tài liệu sandbox opaque origin không được truy cập DOM trực tiếp từ trang cha.
- Form, popup, download và navigation chỉ hoạt động khi token tương ứng cho phép.
- Thay đổi <code>allow-same-origin</code> tạo ra khác biệt origin đúng như dự kiến.
- Trang cha chỉ nhận message từ đúng origin và đúng cửa sổ được kỳ vọng.

Với <code>postMessage</code>, listener cần kiểm tra <code>event.origin</code>, <code>event.source</code> và cấu trúc <code>event.data</code>. Test message từ origin lạ, cửa sổ khác cùng origin, payload sai kiểu và payload có trường ngoài schema.

Opaque origin có thể được tuần tự hóa thành chuỗi <code>null</code>. Không dùng riêng chuỗi này làm allowlist vì nhiều tài liệu opaque origin khác nhau có thể cùng hiển thị như vậy. Ghi nhận hành vi trên từng browser và thiết kế kênh trao đổi phù hợp với sandbox.

### Storage và service worker

Kiểm tra cách ly và vòng đời của:

- <code>localStorage</code> và <code>sessionStorage</code> theo origin và browsing context.
- IndexedDB và Cache API.
- Service worker registration, activation, controller và update.
- Storage trong iframe bên thứ ba và chế độ riêng tư.
- Dữ liệu còn tồn tại sau reload, đóng tab hoặc mở context mới.

Một số chính sách quyền riêng tư có thể partition storage theo top-level site hoặc hạn chế lưu trữ trong ngữ cảnh bên thứ ba. Kiểm tra đúng ngữ cảnh mà sản phẩm sử dụng. Không giả định rằng dữ liệu trong iframe luôn dùng chung với dữ liệu của tab top-level.

Service worker yêu cầu secure context trong các môi trường web thông thường. Khi tự động hóa, chờ sự kiện hoặc trạng thái thực tế như <code>navigator.serviceWorker.ready</code> và <code>navigator.serviceWorker.controller</code>; tránh dùng một khoảng sleep cố định vì thời gian cài đặt và kích hoạt khác nhau giữa máy chạy.

### Permissions API và secure context

Các quyền camera, microphone, geolocation, notification và clipboard phụ thuộc browser, hệ điều hành, user gesture, nguồn HTTPS và chính sách quản trị thiết bị.

Kiểm tra các trạng thái được sản phẩm xử lý: granted, denied, prompt và API không được hỗ trợ. Không so sánh pixel hoặc câu chữ của hộp thoại quyền giữa các trình duyệt; đây là giao diện do browser hoặc hệ điều hành quản lý. Xác nhận ứng dụng xử lý đúng kết quả API và không tiếp tục thao tác nhạy cảm khi quyền bị từ chối.

Một số quyền chỉ hoạt động trong secure context hoặc cần thao tác trực tiếp của người dùng. Ghi nhận điều kiện đó trong fixture. Nếu automation cấp quyền bằng API riêng của công cụ, đánh dấu đây là ca kiểm thử quyền đã cấp; vẫn cần một vòng kiểm tra thủ công cho luồng prompt và từ chối trên thiết bị thực.

### Mixed content và điều hướng

Dùng fixture HTTPS tham chiếu tới tài nguyên HTTP để kiểm tra mixed content. Xác nhận tài nguyên bị chặn hoặc được nâng cấp theo chính sách browser và cấu hình sản phẩm. Kiểm tra chuyển hướng HTTP sang HTTPS, URL đích cuối cùng và các header bảo mật sau redirect.

Với các ca này, ghi lại toàn bộ chuỗi request trong Network. Không kết luận chỉ dựa trên việc trang cuối cùng hiển thị được; một tài nguyên phụ, script hoặc request API có thể đã bị chặn.

## 5. Tự động hóa với Playwright

Playwright cung cấp project cho Chromium, Firefox và WebKit. Một cấu hình cơ bản có thể chạy cùng bộ test trên ba engine:

~~~ts
import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/security",
  timeout: 30_000,
  expect: {
    timeout: 5_000
  },
  use: {
    baseURL: "https://attacker.test",
    ignoreHTTPSErrors: false,
    trace: "retain-on-failure",
    screenshot: "only-on-failure"
  },
  projects: [
    {
      name: "chromium",
      use: { browserName: "chromium" }
    },
    {
      name: "firefox",
      use: { browserName: "firefox" }
    },
    {
      name: "webkit",
      use: { browserName: "webkit" }
    }
  ]
});
~~~

Các host trong ví dụ phải được cấu hình trong môi trường kiểm thử để phân giải đúng tới fixture. Không bật <code>ignoreHTTPSErrors</code> trong test bảo mật thông thường; nếu chứng chỉ không hợp lệ, hãy sửa môi trường hoặc tạo một ca riêng để kiểm tra lỗi chứng chỉ.

### Ví dụ kiểm tra SOP

Trang hiện tại chạy ở <code>attacker.test</code>, còn iframe tải tài liệu từ <code>app.example.test</code>:

~~~ts
import { test, expect } from "@playwright/test";

test("cross-origin page cannot read the private marker", async ({ page }) => {
  await page.goto("/fixtures/iframe-check");

  const result = await page.evaluate(async () => {
    const frame = document.createElement("iframe");
    frame.src = "https://app.example.test/fixtures/private-marker";
    document.body.append(frame);

    await new Promise<void>((resolve, reject) => {
      const timeout = window.setTimeout(() => {
        reject(new Error("iframe load timeout"));
      }, 5_000);

      frame.addEventListener("load", () => {
        window.clearTimeout(timeout);
        resolve();
      }, { once: true });
    });

    try {
      return frame.contentWindow?.document
        .querySelector("#private-marker")
        ?.textContent ?? "missing";
    } catch (error) {
      return error instanceof DOMException ? error.name : "unexpected-error";
    }
  });

  expect(result).toBe("SecurityError");
});
~~~

Ca này xác nhận trang khác origin không đọc được marker. Hãy bổ sung một ca dương tính cùng origin để chắc chắn marker tồn tại và selector đúng. Trong suite thực tế, thêm timeout và log URL để tránh nhầm lỗi fixture hoặc lỗi mạng với hành vi SOP.

### Ví dụ kiểm tra response CORS không được expose

Trang chạy ở origin không nằm trong allowlist gọi API bằng credentials:

~~~ts
test("untrusted origin cannot read the API response", async ({ page }) => {
  await page.goto("/fixtures/cors-check");

  const result = await page.evaluate(async () => {
    try {
      const response = await fetch("https://api.example.test/private", {
        credentials: "include"
      });

      return {
        readable: true,
        status: response.status
      };
    } catch {
      return {
        readable: false
      };
    }
  });

  expect(result.readable).toBe(false);
});
~~~

Test này chỉ khẳng định JavaScript không đọc được response. Nó không chứng minh server chưa nhận request. Với endpoint có tác dụng phụ, dùng log hoặc trạng thái server để xác định request có tới server hay không. Tạo thêm ca positive từ <code>portal.example.test</code> để xác nhận origin được allowlist đọc được đúng response.

### Kiểm tra CSP bằng marker

Tạo một fixture trả header <code>Content-Security-Policy: default-src 'self'; script-src 'self'</code>. Trong HTML, đặt một script inline thay đổi biến marker và một script ngoài cùng origin đọc marker rồi ghi kết quả ra phần tử hiển thị. Kết quả mong đợi: script inline bị chặn, script ngoài được phép chạy và xác nhận marker chưa bị thay đổi.

Cách này kiểm tra hành vi thực tế thay vì phụ thuộc vào chuỗi thông báo trong Console. Có thể bổ sung listener cho console và page error để hỗ trợ điều tra, nhưng không nên dùng chúng làm assertion duy nhất.

### Tổ chức test và cô lập trạng thái

- Dùng browser context mới cho mỗi test cần trạng thái cookie hoặc storage sạch.
- Tạo dữ liệu giả lập theo test và xóa dữ liệu sau khi hoàn tất.
- Dùng route hoặc endpoint riêng cho từng chính sách CORS/CSP để kết quả dễ đọc.
- Chờ sự kiện thực tế như load, response, controllerchange hoặc trạng thái DOM thay vì sleep tùy ý.
- Lưu trace, screenshot và request/response metadata khi test thất bại.
- Gắn nhãn test theo nhóm bảo mật để có thể chạy nhanh nhóm bị ảnh hưởng.

Không dùng một test pass trên Chromium làm điều kiện bỏ qua Firefox và WebKit. Mục tiêu của project là chạy cùng bộ assertion trên từng engine.

## 6. Xác minh bằng trình duyệt và thiết bị thực

Automation rút ngắn vòng lặp nhưng không mô phỏng đầy đủ mọi chính sách của trình duyệt phát hành. Cần xác minh thủ công hoặc trên thiết bị thực khi ca kiểm thử liên quan tới:

- Safari trên macOS/iOS và chính sách WebKit phát hành.
- Cookie bên thứ ba, tracking prevention và storage partitioning.
- Hộp thoại quyền do browser hoặc hệ điều hành quản lý.
- Camera, microphone, geolocation, clipboard và user gesture.
- WebView hoặc browser nhúng trong ứng dụng.
- Download, popup, navigation và tích hợp hệ điều hành.
- Chính sách doanh nghiệp hoặc extension có ảnh hưởng đến request.

Khi kiểm tra Safari, ghi lại phiên bản Safari và phiên bản hệ điều hành. Khi kiểm tra WebView, ghi lại phiên bản WebView hoặc ứng dụng chủ. Khi kiểm tra mobile, xác nhận test thực sự chạy trên thiết bị hoặc môi trường cloud device tương ứng; viewport giả lập trên desktop không đại diện cho mọi chính sách mobile.

Profile dùng để kiểm tra phải có cấu hình được ghi nhận. Nếu cần thử chế độ chặn cookie bên thứ ba, chạy cả profile mặc định và profile có cấu hình đó, sau đó ghi rõ sự khác biệt.

## 7. Phân tích sai khác giữa các browser

Khi một ca chỉ thất bại trên một browser, hãy điều tra theo thứ tự:

1. **Xác minh môi trường:** browser, phiên bản, engine, hệ điều hành, URL, chứng chỉ và fixture có giống dự kiến không?
2. **Xác minh trạng thái:** cookie, storage, service worker, quyền và cache có được tạo mới đúng cách không?
3. **Quan sát request:** request có được gửi không, có preflight không, redirect tới đâu và response header là gì?
4. **Quan sát hành vi:** DOM có đọc được không, script có chạy không, cookie có được gửi không, message có được xử lý không?
5. **Phân loại nguyên nhân:** lỗi fixture, khác biệt cấu hình, API chưa hỗ trợ, thay đổi chính sách browser hay lỗi ứng dụng?
6. **Tái hiện:** chạy lại trên profile sạch và phiên bản khác trong cùng engine để xác định phạm vi.

Không dùng User-Agent sniffing làm cách sửa mặc định. Nếu tính năng cần kiểm tra, dùng feature detection và xác định fallback an toàn. Khi browser không hỗ trợ một API, ứng dụng phải xử lý trạng thái đó theo yêu cầu sản phẩm; không được vô tình bỏ qua kiểm soát bảo mật.

Không hạ mức bảo vệ để làm cho các browser cho kết quả giống nhau. Nếu một browser áp dụng chính sách chặt hơn và làm hỏng luồng ứng dụng, điều chỉnh thiết kế hoặc luồng tương tác theo hướng vẫn giữ nguyên bất biến bảo mật.

### Những kết luận dễ sai

| Quan sát | Kết luận không nên đưa ra | Cách xác minh đúng |
|---|---|---|
| Console hiển thị lỗi CORS | Request chắc chắn không tới server | Kiểm tra Network và log server |
| Cookie không xuất hiện trong request iframe | CORS đã chặn cookie | Kiểm tra SameSite, third-party cookie và request context |
| Playwright WebKit pass | Safari thực tế chắc chắn pass | Chạy thêm trên Safari phát hành |
| Hộp thoại quyền khác giao diện | API quyền hoạt động sai | Kiểm tra trạng thái API và hành vi ứng dụng |
| Một browser không có Trusted Types | Có thể bỏ qua mọi kiểm soát XSS | Kiểm tra fallback và output handling |
| Test pass trong profile thường | Test cũng pass trong private mode | Chạy riêng profile và cấu hình quyền riêng tư |

## 8. Ma trận Cross-browser test mẫu

Bảng sau là bộ khung có thể điều chỉnh theo tính năng và browser được sản phẩm hỗ trợ:

| ID | Nhóm | Tình huống | Kết quả mong đợi |
|---|---|---|---|
| CB-01 | SOP | Trang khác origin đọc DOM của ứng dụng | Bị chặn |
| CB-02 | SOP | Trang cùng origin đọc marker kiểm thử | Được phép |
| CB-03 | CORS | Origin được allowlist đọc API | Được phép theo cấu hình |
| CB-04 | CORS | Origin không được allowlist đọc API | Response không được expose |
| CB-05 | CORS | Preflight yêu cầu header không được cho phép | Request chính không được thực hiện |
| CB-06 | Cookie | Cookie HttpOnly | JavaScript không đọc được; request phù hợp vẫn gửi cookie |
| CB-07 | Cookie | Iframe cross-site với third-party cookie bị chặn | Ứng dụng xử lý trạng thái thiếu cookie an toàn |
| CB-08 | CSP | Inline script không có quyền thực thi | Script không chạy |
| CB-09 | CSP | Origin không được phép nhúng trang | Frame bị chặn theo chính sách |
| CB-10 | Trusted Types | Browser hỗ trợ và policy bật | Sink được bảo vệ theo policy |
| CB-11 | Sandbox | Iframe thiếu allow-same-origin | Tài liệu có opaque origin |
| CB-12 | postMessage | Message từ origin hoặc source không tin cậy | Listener từ chối |
| CB-13 | Storage | Storage ở origin khác hoặc top-level site khác | Không lộ dữ liệu ngoài phạm vi |
| CB-14 | Service worker | Trang secure context đăng ký worker | Worker hoạt động theo vòng đời dự kiến |
| CB-15 | Permissions | Người dùng từ chối quyền thiết bị | Ứng dụng dừng thao tác cần quyền và thông báo phù hợp |
| CB-16 | Mixed content | HTTPS page tải tài nguyên HTTP bị cấm | Tài nguyên không được sử dụng trái chính sách |

Với mỗi ca, lưu browser/engine/version, hệ điều hành, cấu hình profile, URL nguồn và đích, trạng thái đăng nhập giả lập, request/response liên quan, kết quả kỳ vọng, kết quả thực tế và bằng chứng. Đánh dấu rõ ca nào chưa chạy trên thiết bị thực.

## 9. Báo cáo lỗi cross-browser

Một báo cáo tốt cần đủ thông tin để người khác tái hiện trên đúng môi trường:

| Trường | Nội dung cần ghi |
|---|---|
| Mã lỗi | ID duy nhất và liên kết test case |
| Browser | Tên, phiên bản và engine |
| Nền tảng | Hệ điều hành, phiên bản và thiết bị nếu có |
| Cấu hình | Profile, quyền, cookie bên thứ ba, extension hoặc policy |
| Fixture | Bản build, URL và dữ liệu giả lập |
| Bước tái hiện | Các thao tác cụ thể, có thể chạy lại |
| Kỳ vọng | Bất biến bảo mật cần giữ |
| Thực tế | Hành vi quan sát được |
| Bằng chứng | Trace, Network, header, log server, screenshot đã che dữ liệu |
| Phạm vi | Chỉ một browser, một engine hay nhiều môi trường |
| Tác động | Dữ liệu bị lộ, thao tác trái phép hoặc luồng hợp lệ bị gián đoạn |

Khi đính kèm trace hoặc screenshot, che cookie, token, thông tin cá nhân và dữ liệu tài khoản. Không ghi bí mật vào test output. Nếu khác biệt không tái hiện được, ghi rõ điều kiện đã thử và trạng thái chưa xác định thay vì kết luận lỗi đã được sửa.

## 10. Thực hành

Xây dựng một lab gồm ba origin:

- <code>https://app.example.test</code> chứa marker riêng tư và trang tài khoản giả lập.
- <code>https://api.example.test</code> cung cấp endpoint có CORS allowlist.
- <code>https://attacker.test</code> chứa trang kiểm thử cross-origin.

Chạy bộ test trên Chromium, Firefox và WebKit bằng Playwright. Sau đó chọn một phiên bản Safari thực tế nếu sản phẩm hỗ trợ Safari.

Thực hiện các yêu cầu:

1. Kiểm tra trang ở <code>attacker.test</code> không đọc được marker trong DOM của <code>app.example.test</code>.
2. Kiểm tra origin không được allowlist không đọc được response API; dùng log server để xác định request có tới server hay không.
3. Kiểm tra origin được allowlist đọc được response đúng theo cấu hình CORS.
4. Kiểm tra cookie HttpOnly và SameSite trong top-level navigation và iframe cross-site.
5. Kiểm tra CSP chặn script inline và ngăn origin không được phép nhúng trang.
6. Kiểm tra iframe sandbox và listener postMessage từ chối nguồn không tin cậy.
7. Ghi lại khác biệt về storage, service worker hoặc permission nếu sản phẩm sử dụng các tính năng đó.

Hoàn thiện bảng kết quả với các cột: browser/engine/version, nền tảng, cấu hình, test ID, kỳ vọng, thực tế, bằng chứng và trạng thái. Chạy lại các ca thất bại trên profile sạch để phân biệt lỗi ứng dụng với trạng thái còn sót từ lần chạy trước. Cuối cùng, xóa marker, cookie và dữ liệu giả lập khỏi browser context.

## Ghi nhớ

- Cross-browser test phải kiểm tra các bất biến bảo mật trên những browser và nền tảng sản phẩm hỗ trợ.
- Ghi nhận engine, phiên bản, hệ điều hành và cấu hình quyền riêng tư; tên trình duyệt một mình chưa đủ để mô tả môi trường.
- Chromium, Firefox và WebKit là bộ engine phù hợp cho automation, nhưng Playwright WebKit không thay thế hoàn toàn Safari phát hành hoặc WebView thực tế.
- Kiểm tra cả đường được phép và đường bị chặn của SOP, CORS, cookie, CSP, sandbox, storage và quyền.
- CORS không đảm bảo request không tới server; cookie và CORS là hai cơ chế khác nhau.
- Khác biệt thông báo Console hoặc giao diện quyền không tự động là lỗi bảo mật.
- Dùng fixture do nhóm kiểm soát, dữ liệu giả lập, profile cô lập và bằng chứng có thể tái hiện.
- Khi browser không hỗ trợ một API, ứng dụng cần fallback an toàn theo yêu cầu sản phẩm.
