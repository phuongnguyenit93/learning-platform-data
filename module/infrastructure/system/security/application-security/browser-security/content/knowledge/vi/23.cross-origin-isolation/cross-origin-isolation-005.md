# SharedArrayBuffer: chia sẻ bộ nhớ giữa các JavaScript contexts

## 1. SharedArrayBuffer dùng để làm gì?

Thông thường, khi một trang gửi dữ liệu cho Web Worker bằng `postMessage()`, browser sao chép dữ liệu theo structured clone algorithm hoặc chuyển quyền sở hữu một số transferable objects. Cách này phù hợp với nhiều ứng dụng, nhưng khi phải trao đổi khối dữ liệu lớn hoặc đồng bộ trạng thái liên tục, chi phí sao chép và độ trễ có thể đáng kể.

**SharedArrayBuffer (SAB)** cho phép nhiều JavaScript execution contexts cùng truy cập một vùng bộ nhớ. Ví dụ, trang chính và một Web Worker có thể cùng tạo các typed arrays trên một buffer và đọc/ghi vào cùng các byte. Không cần gửi một bản sao mới của toàn bộ dữ liệu mỗi lần trạng thái thay đổi.

Chia sẻ bộ nhớ cũng tạo ra rủi ro: hai context có thể đọc và ghi cùng lúc, dẫn đến race condition nếu không đồng bộ đúng cách. JavaScript cung cấp `Atomics` để thực hiện các thao tác nguyên tử và đồng bộ trên shared memory.

Vì shared memory có thể hỗ trợ các kỹ thuật timing tinh vi, browser hiện đại chỉ cho phép các ứng dụng đáp ứng điều kiện **cross-origin isolation** sử dụng SharedArrayBuffer trong những ngữ cảnh web thông thường. Điều này gắn SAB với các cơ chế COOP, COEP, CORP, CORS và ranh giới giữa các origin.

Sau bài học, bạn có thể:

- Giải thích SharedArrayBuffer khác ArrayBuffer và transferable objects như thế nào.
- Kiểm tra điều kiện `crossOriginIsolated` trước khi dùng SAB.
- Cấu hình COOP và COEP để bật cross-origin isolation.
- Hiểu vai trò của CORP và CORS khi tải tài nguyên cross-origin.
- Chia sẻ SAB giữa trang và worker, đồng bộ bằng Atomics.
- Chẩn đoán lỗi khi một tài nguyên bên thứ ba làm hỏng COEP.
- Đánh giá tác động của cross-origin isolation tới popup, OAuth và tích hợp bên ngoài.

## 2. ArrayBuffer và SharedArrayBuffer khác nhau

`ArrayBuffer` là vùng nhớ có kích thước cố định chứa dữ liệu nhị phân. Một typed array như `Uint8Array`, `Int32Array` hoặc `Float64Array` tạo view để đọc/ghi các phần tử trong vùng nhớ đó.

Ví dụ:

```javascript
const buffer = new ArrayBuffer(16);
const bytes = new Uint8Array(buffer);
bytes[0] = 42;

console.log(bytes[0]); // 42
```

Nếu gửi một `ArrayBuffer` bình thường bằng `postMessage()` mà không chuyển quyền sở hữu, browser structured-clone dữ liệu và worker nhận bản sao. Nếu đưa buffer vào transfer list, ownership được chuyển sang context nhận; phía gửi không thể tiếp tục sử dụng buffer đã detach.

Với `SharedArrayBuffer`, các context nhận cùng truy cập một vùng nhớ:

```javascript
const shared = new SharedArrayBuffer(16);
const bytes = new Uint8Array(shared);
bytes[0] = 42;

// Một context khác có view trên cùng shared buffer
// sẽ đọc được giá trị 42.
```

| Đặc điểm | ArrayBuffer | SharedArrayBuffer |
| --- | --- | --- |
| Vùng nhớ | Một buffer thông thường. | Vùng nhớ có thể được chia sẻ giữa contexts. |
| Gửi bằng postMessage | Clone hoặc transfer. | Structured clone tạo tham chiếu chia sẻ tới cùng vùng nhớ. |
| Transfer list | Có thể transfer ownership. | Không transfer SAB như ArrayBuffer; SAB được chia sẻ. |
| Đồng bộ truy cập | Không cần phối hợp nếu mỗi context có bản sao riêng. | Cần thiết kế đồng bộ khi nhiều context đọc/ghi. |
| Điều kiện browser | Được hỗ trợ trong secure context tùy API. | Trong web thông thường cần cross-origin isolation. |

### 2.1 Typed arrays chỉ là view

SAB không trực tiếp cung cấp API đọc/ghi số nguyên hoặc số thực. Ứng dụng tạo view phù hợp:

```javascript
const shared = new SharedArrayBuffer(4 * Int32Array.BYTES_PER_ELEMENT);
const values = new Int32Array(shared);

values[0] = 10;
values[1] = 20;
```

Nhiều view có thể trỏ vào cùng buffer. Nếu một worker cập nhật `values[0]`, context khác có thể quan sát thay đổi đó. Cách quan sát và thứ tự các thao tác cần được thiết kế đúng, đặc biệt khi có nhiều thao tác đồng thời.

## 3. Điều kiện cross-origin isolation

SharedArrayBuffer trong browser web thông thường yêu cầu document nằm trong môi trường **cross-origin isolated**. Cách kiểm tra trực tiếp:

```javascript
if (window.crossOriginIsolated) {
  // Có thể khởi tạo SharedArrayBuffer nếu browser hỗ trợ API.
} else {
  // Dùng ArrayBuffer/transfer hoặc phương án không shared memory.
}
```

`crossOriginIsolated` là thuộc tính boolean do browser cung cấp. Nó cho biết document đang ở trong môi trường đáp ứng các yêu cầu isolation của nền tảng. Không tự suy luận giá trị này chỉ từ việc trang chạy HTTPS hoặc có một header CSP.

Đối với các ứng dụng thông thường, điều kiện triển khai chính gồm:

- Trang được phục vụ trong secure context, thường là HTTPS (localhost có thể được xem là trustworthy trong môi trường phát triển).
- COOP thiết lập browsing context group isolation phù hợp.
- COEP yêu cầu tài nguyên nhúng tuân thủ chính sách cross-origin.
- Các tài nguyên cross-origin cần có CORS hoặc CORP phù hợp với chế độ tải.

Ví dụ hai response headers thường dùng:

```http
Cross-Origin-Opener-Policy: same-origin
Cross-Origin-Embedder-Policy: require-corp
```

Một số triển khai có thể dùng `COEP: credentialless` thay cho `require-corp`, với ngữ nghĩa và giới hạn khác nhau được trình bày ở phần sau.

### 3.1 HTTPS là điều kiện quan trọng nhưng chưa đủ

Secure context giúp browser bảo đảm một số khả năng mạnh chỉ chạy trong môi trường an toàn. Tuy nhiên, chỉ bật HTTPS không làm `window.crossOriginIsolated` tự động thành `true`.

Tương tự, chỉ phát COOP hoặc chỉ phát COEP cũng không đủ. Hãy kiểm tra cả hai response headers trên document chính và xác nhận bằng `window.crossOriginIsolated`.

### 3.2 Secure context và môi trường local

Trong phát triển, `http://localhost` thường được browser xem là potentially trustworthy và có thể dùng để kiểm tra các API secure-context. Tuy nhiên, host local tùy biến hoặc IP trong môi trường mạng có thể không được xử lý giống localhost. Khi triển khai staging/production, dùng HTTPS và kiểm tra header trên response thực tế.

## 4. COOP: tách browsing context group

**Cross-Origin-Opener-Policy (COOP)** kiểm soát mối quan hệ giữa document hiện tại với các browsing context khác, đặc biệt là cửa sổ được mở bằng `window.open()` và quan hệ opener.

Giá trị phổ biến để bật cross-origin isolation:

```http
Cross-Origin-Opener-Policy: same-origin
```

Với `same-origin`, document chỉ giữ quan hệ opener trong phạm vi phù hợp cùng origin. Khi điều hướng hoặc mở trang khác origin, browser có thể đặt document vào browsing context group khác và cắt quan hệ tham chiếu opener giữa các nhóm.

Điều này làm giảm khả năng một trang cross-origin tương tác với cửa sổ đang mở nó và giúp cô lập các browsing contexts. Đây là một phần quan trọng để browser có thể cung cấp shared memory an toàn hơn.

### 4.1 Tác động tới window.opener và popup

Một số luồng đăng nhập, OAuth, thanh toán hoặc tích hợp đối tác dựa vào:

- Trang chính mở popup bằng `window.open()`.
- Popup hoàn thành công việc rồi gọi `window.opener.postMessage(...)`.
- Trang chính nhận message và đóng popup.

Khi áp dụng COOP `same-origin`, quan hệ opener với popup cross-origin có thể bị cắt. Code dựa vào `window.opener` có thể thấy `null` hoặc không còn dùng được như trước. Do đó, cần thử các luồng popup trước khi bật isolation ở production.

Các hướng xử lý gồm:

- Dùng redirect-based flow nếu nhà cung cấp hỗ trợ.
- Thiết kế callback cùng origin hoặc endpoint trung gian có xác minh state/nonce.
- Dùng cơ chế giao tiếp được nhà cung cấp hỗ trợ và không phụ thuộc opener cross-origin.
- Đánh giá COOP policy khác khi phù hợp, nhưng không giả định chúng vẫn bật cross-origin isolation.

`same-origin-allow-popups` có thể giữ một số quan hệ popup trong những trường hợp cụ thể, nhưng không tương đương `same-origin` cho mục tiêu cross-origin isolation. Nếu đổi COOP để giữ popup, phải kiểm tra lại `crossOriginIsolated`.

### 4.2 COOP không phải CORS

COOP kiểm soát quan hệ giữa browsing contexts và opener. CORS kiểm soát việc JavaScript đọc response cross-origin. Một header không thay thế header kia.

## 5. COEP: yêu cầu tài nguyên được nhúng tuân thủ chính sách

**Cross-Origin-Embedder-Policy (COEP)** quy định cách document xử lý tài nguyên cross-origin được nhúng hoặc tải vào context của nó. Khi bật COEP, trang phải đảm bảo các tài nguyên cross-origin được chia sẻ có chủ đích thông qua CORS hoặc CORP, tùy chế độ request.

Hai giá trị quan trọng:

```http
Cross-Origin-Embedder-Policy: require-corp
```

và:

```http
Cross-Origin-Embedder-Policy: credentialless
```

### 5.1 require-corp

Với `require-corp`, các request cross-origin ở chế độ `no-cors` cần response cho phép nhúng bằng Cross-Origin-Resource-Policy (CORP). Nếu tài nguyên không cấp quyền phù hợp, browser chặn việc sử dụng tài nguyên đó trong document có COEP.

Ví dụ một ảnh public từ CDN có thể trả:

```http
Cross-Origin-Resource-Policy: cross-origin
```

Hoặc tài nguyên chỉ cho phép cùng site:

```http
Cross-Origin-Resource-Policy: same-site
```

Với request ở chế độ CORS, server cần trả CORS headers phù hợp, chẳng hạn `Access-Control-Allow-Origin` cho origin ứng dụng.

### 5.2 credentialless

`credentialless` cho phép một số cross-origin `no-cors` requests được tải mà không gửi credentials, và không yêu cầu response phải cấp CORP như `require-corp` trong trường hợp đó. Browser xử lý request ở chế độ không credentials; cookie và HTTP authentication không được gửi theo cách thông thường cho request đó.

Điều này có thể giúp giảm công việc cấu hình CORP cho tài nguyên public của bên thứ ba, nhưng tài nguyên không được dựa vào cookie đăng nhập để trả nội dung. Các request CORS vẫn cần đáp ứng CORS; `credentialless` không bỏ qua CORS cho fetch/XHR cần đọc response.

Không chọn `credentialless` chỉ để làm mất lỗi tải tài nguyên. Hãy kiểm tra tài nguyên có cần credentials không, và đánh giá hành vi trên browser mục tiêu.

### 5.3 COEP ảnh hưởng nhiều loại tài nguyên

Các tích hợp có thể bị ảnh hưởng gồm:

- Ảnh, font, stylesheet và script từ CDN bên ngoài.
- iframe và nội dung nhúng.
- Worker scripts và tài nguyên mà worker tiếp tục tải.
- SDK analytics, quảng cáo, video hoặc widget của bên thứ ba.
- Tài nguyên tải ở chế độ `no-cors` nhưng không có CORP.

Không phải mọi request cross-origin đều bị xử lý giống nhau. Cần xác định request mode (`cors`, `no-cors`, `same-origin`), credentials mode và response headers của từng tài nguyên.

## 6. CORP và CORS hỗ trợ COEP như thế nào?

Hai cơ chế này thường được nhắc cùng COEP nhưng giải quyết các tình huống khác nhau.

| Cơ chế | Được cấu hình ở đâu? | Vai trò |
| --- | --- | --- |
| COEP | Response của document/worker | Yêu cầu tài nguyên được nhúng tuân thủ chính sách cross-origin. |
| CORP | Response của tài nguyên | Cho phép hoặc giới hạn việc tài nguyên được nhúng bởi context khác origin/site trong request `no-cors`. |
| CORS | Response của tài nguyên và request mode của caller | Cho phép JavaScript đọc response cross-origin theo allowlist. |

CORP có các giá trị thường gặp:

| Header | Ý nghĩa |
| --- | --- |
| `Cross-Origin-Resource-Policy: same-origin` | Chỉ cho phép tài nguyên được sử dụng theo chính sách same-origin. |
| `Cross-Origin-Resource-Policy: same-site` | Cho phép cùng site theo định nghĩa schemeful site. |
| `Cross-Origin-Resource-Policy: cross-origin` | Cho phép tài nguyên được nhúng cross-origin trong các ngữ cảnh CORP kiểm soát. |

Ví dụ API trả JSON để frontend đọc:

```http
Access-Control-Allow-Origin: https://app.example.com
Vary: Origin
Content-Type: application/json
```

Ví dụ tài nguyên public chỉ được nhúng cross-origin ở chế độ no-cors:

```http
Cross-Origin-Resource-Policy: cross-origin
Content-Type: image/png
```

Không thêm `Access-Control-Allow-Origin: *` hoặc `Cross-Origin-Resource-Policy: cross-origin` một cách đại trà cho mọi response. Chỉ mở quyền chia sẻ ở tài nguyên thực sự cần và cân nhắc dữ liệu/credentials được phục vụ.

## 7. Cấu hình tối thiểu để bật SharedArrayBuffer

Một response document ví dụ:

```http
HTTP/1.1 200 OK
Content-Type: text/html; charset=utf-8
Cross-Origin-Opener-Policy: same-origin
Cross-Origin-Embedder-Policy: require-corp
```

Sau khi tải trang:

```javascript
console.log(window.isSecureContext);
console.log(window.crossOriginIsolated);
console.log(typeof SharedArrayBuffer);
```

Kết quả mong đợi trong browser hỗ trợ và cấu hình đúng:

- `window.isSecureContext` là `true`.
- `window.crossOriginIsolated` là `true`.
- `SharedArrayBuffer` khả dụng.

Nếu `crossOriginIsolated` là `false`, kiểm tra COOP, COEP, secure context và tài nguyên bị chặn. Đừng chỉ kiểm tra `typeof SharedArrayBuffer`, vì hành vi khả dụng có thể thay đổi theo browser và context.

### 7.1 Worker cũng cần cấu hình phù hợp

Nếu ứng dụng tạo Dedicated Worker để thao tác shared memory, worker cần được tải từ môi trường phù hợp và chịu các chính sách embedder liên quan. Worker script cùng origin thường đơn giản hơn; nếu script worker hoặc `importScripts` lấy từ origin khác, cần kiểm tra CORS/CORP và chính sách COEP trên chuỗi tài nguyên.

Ví dụ:

```javascript
const worker = new Worker("/workers/compute.js");
```

Worker có thể kiểm tra:

```javascript
self.postMessage({
  secureContext: self.isSecureContext,
  crossOriginIsolated: self.crossOriginIsolated,
  sharedArrayBufferAvailable: typeof SharedArrayBuffer !== "undefined"
});
```

## 8. Chia sẻ SharedArrayBuffer với Web Worker

Ví dụ tối giản: trang tạo shared buffer rồi gửi cho worker:

```javascript
if (!crossOriginIsolated || typeof SharedArrayBuffer === "undefined") {
  throw new Error("SharedArrayBuffer requires cross-origin isolation");
}

const shared = new SharedArrayBuffer(Int32Array.BYTES_PER_ELEMENT);
const view = new Int32Array(shared);

const worker = new Worker("/worker.js");
worker.postMessage({ shared });

console.log("Initial value:", Atomics.load(view, 0));
```

Worker:

```javascript
self.addEventListener("message", event => {
  const { shared } = event.data;
  const view = new Int32Array(shared);

  Atomics.store(view, 0, 123);
  self.postMessage({ type: "UPDATED" });
});
```

Trang chính:

```javascript
worker.addEventListener("message", event => {
  if (event.data?.type === "UPDATED") {
    console.log("Shared value:", Atomics.load(view, 0));
  }
});
```

Worker và trang chính đang dùng cùng một vùng nhớ. Message `UPDATED` chỉ báo hiệu worker đã thực hiện thao tác; dữ liệu thực tế nằm trong shared buffer.

Lưu ý: `SharedArrayBuffer` được structured clone khi gửi bằng `postMessage()`, nhưng vùng nhớ underlying được chia sẻ. Không đặt SAB vào transfer list như ArrayBuffer.

## 9. Đồng bộ shared memory bằng Atomics

Khi nhiều contexts truy cập cùng vùng nhớ, cần tránh race condition. `Atomics` cung cấp các phép đọc/ghi nguyên tử trên integer typed arrays được hỗ trợ, cùng các thao tác chờ và đánh thức.

### 9.1 Load và store

```javascript
const shared = new SharedArrayBuffer(Int32Array.BYTES_PER_ELEMENT);
const state = new Int32Array(shared);

Atomics.store(state, 0, 7);
const current = Atomics.load(state, 0);

console.log(current); // 7
```

`Atomics.load()` và `Atomics.store()` thực hiện truy cập nguyên tử đối với vị trí phần tử. Điều này giúp các thao tác quan sát/ghi giá trị nhất quán theo mô hình bộ nhớ JavaScript.

### 9.2 Compare-and-exchange

`Atomics.compareExchange()` cập nhật phần tử chỉ khi giá trị hiện tại khớp giá trị kỳ vọng:

```javascript
const state = new Int32Array(
  new SharedArrayBuffer(Int32Array.BYTES_PER_ELEMENT)
);

Atomics.store(state, 0, 0);
const previous = Atomics.compareExchange(state, 0, 0, 1);

console.log(previous); // 0
console.log(Atomics.load(state, 0)); // 1
```

Đây là nền tảng để tạo lock hoặc trạng thái chuyển đổi mà không cần thao tác đọc/ghi rời rạc có race.

### 9.3 Wait và notify

Worker có thể chờ một giá trị thay đổi:

```javascript
// Worker
const state = new Int32Array(shared);

const result = Atomics.wait(state, 0, 0);
// Worker tiếp tục khi được notify hoặc khi wait kết thúc.
```

Context khác đánh thức:

```javascript
Atomics.store(state, 0, 1);
Atomics.notify(state, 0, 1);
```

`Atomics.wait()` không được phép gọi trên main thread của browser vì có thể block giao diện; nó thường dùng trong worker. Main thread có thể dùng `Atomics.waitAsync()` ở môi trường hỗ trợ hoặc thiết kế message/event để tránh block UI. Cần kiểm tra hỗ trợ API trên browser mục tiêu.

## 10. Rủi ro race condition và thiết kế giao thức

Chia sẻ buffer không tự làm dữ liệu an toàn. Ví dụ hai worker cùng tăng một counter:

```javascript
// Không an toàn nếu nhiều context cùng thực hiện:
view[0] = view[0] + 1;
```

Đây là chuỗi đọc, cộng và ghi riêng biệt. Hai worker có thể cùng đọc giá trị 10, cùng tính 11 rồi cùng ghi 11; một lần tăng bị mất.

Dùng thao tác nguyên tử:

```javascript
Atomics.add(view, 0, 1);
```

### 10.1 Chọn cấu trúc dữ liệu có quyền sở hữu rõ ràng

Với shared memory phức tạp, xác định:

- Context nào được ghi vào từng vùng.
- Field nào chỉ đọc sau khi publish.
- Cách biểu diễn trạng thái: empty, writing, ready, consumed.
- Cách đồng bộ producer/consumer.
- Cách xử lý worker crash hoặc timeout.
- Giới hạn kích thước buffer và dữ liệu đầu vào.

Nếu có thể, chia buffer thành các vùng do từng worker sở hữu để giảm tranh chấp. Dùng Atomics cho các cờ đồng bộ và counter; không giả định một thao tác đọc/ghi thông thường sẽ tự tạo thứ tự đồng bộ mong muốn.

### 10.2 Không dùng shared memory làm kênh tin cậy giữa các bên không tin

Một context có tham chiếu tới SAB có thể sửa dữ liệu trong vùng nhớ chung. Chỉ chia sẻ buffer với worker/context thuộc ứng dụng và được kiểm soát. Kiểm tra schema, range và trạng thái trước khi sử dụng dữ liệu, đặc biệt khi dữ liệu có thể đến từ message hoặc nội dung bên ngoài.

## 11. Tài nguyên bên thứ ba có thể làm COEP thất bại

Một trong các phần khó nhất khi bật cross-origin isolation là kiểm kê tất cả tài nguyên cross-origin. Ví dụ, ứng dụng có thể tải:

- Font từ CDN không trả CORP hoặc CORS.
- Ảnh public từ một host không cấp CORP.
- SDK analytics dùng script hoặc request từ nhiều domain.
- Video, iframe hoặc widget của đối tác.
- Worker script hoặc module import từ host khác.

Với COEP `require-corp`, browser có thể chặn tài nguyên cross-origin `no-cors` không có CORP phù hợp. Nếu tài nguyên được tải theo CORS mode, server phải trả CORS headers thích hợp.

### 11.1 Cách xử lý

1. Kiểm tra Console để tìm thông báo COEP/CORP/CORS.
2. Mở Network và xác định tài nguyên bị chặn, request mode và response headers.
3. Nếu kiểm soát server tài nguyên, cấu hình CORP hoặc CORS theo nhu cầu thật.
4. Nếu là CDN/đối tác, kiểm tra khả năng hỗ trợ CORS/CORP và điều khoản tích hợp.
5. Nếu không thể thay đổi server, cân nhắc proxy tài nguyên qua backend của mình khi hợp pháp và phù hợp, hoặc loại bỏ tích hợp khỏi trang cần isolation.
6. Chỉ cân nhắc `credentialless` nếu tài nguyên cross-origin `no-cors` không cần credentials và browser mục tiêu hỗ trợ.

Không dùng wildcard allowlist cho toàn bộ tài nguyên chỉ để bật SAB nhanh chóng.

## 12. Ảnh hưởng tới ứng dụng và kiến trúc

Cross-origin isolation là một thay đổi kiến trúc, không chỉ là bật hai HTTP headers. Cần đánh giá:

| Thành phần | Ảnh hưởng có thể gặp |
| --- | --- |
| OAuth/popup | COOP có thể cắt quan hệ opener với popup cross-origin. |
| Payment widget | Iframe hoặc popup của đối tác có thể không hoạt động như trước. |
| Analytics/ads | Tài nguyên hoặc SDK cross-origin có thể bị COEP chặn. |
| CDN ảnh/font | Cần CORP/CORS phù hợp. |
| Worker | Script và import của worker cần tương thích với isolation. |
| Micro-frontend | Các iframe cross-origin và luồng giao tiếp cần kiểm tra lại. |
| Browser cũ | Có thể không hỗ trợ đầy đủ SAB, Atomics hoặc các policy mới. |

Nếu chỉ một chức năng cần SAB, cân nhắc đặt chức năng đó trong một ứng dụng/subdomain riêng có cross-origin isolation thay vì áp dụng cho toàn bộ hệ thống. Tuy nhiên, việc tách origin phải đi kèm thiết kế authentication, cookie, API và giao tiếp giữa các ứng dụng.

## 13. Chẩn đoán crossOriginIsolated và SharedArrayBuffer

### 13.1 Kiểm tra trong Console

Chạy:

```javascript
({
  secureContext: window.isSecureContext,
  crossOriginIsolated: window.crossOriginIsolated,
  sharedArrayBuffer: typeof SharedArrayBuffer
});
```

Nếu `crossOriginIsolated` là `false`, kiểm tra:

- Response document có `Cross-Origin-Opener-Policy: same-origin` không?
- Response document có `Cross-Origin-Embedder-Policy: require-corp` hoặc `credentialless` không?
- Trang có secure context không?
- Có tài nguyên cross-origin bị COEP chặn không?
- Worker có tải đúng và được hưởng chính sách phù hợp không?
- Có nhiều redirect hoặc response khác nhau làm header bị mất không?

### 13.2 Kiểm tra response headers

Trong DevTools → Network:

1. Chọn document request chính.
2. Xem Response Headers của document cuối cùng sau redirect.
3. Xác nhận COOP và COEP xuất hiện trên response thực tế.
4. Lọc request bị blocked và kiểm tra CORP/CORS headers của tài nguyên.
5. Kiểm tra popup/iframe/worker nếu luồng ứng dụng có dùng chúng.

Header đặt ở HTML meta element không thay thế COOP/COEP response headers.

### 13.3 curl chỉ kiểm tra header, không mô phỏng browser isolation

Có thể xem header:

```bash
curl -I https://app.example.com/
```

Nhưng curl không thực thi browsing context group, COEP enforcement hoặc `window.crossOriginIsolated`. Cần mở trang bằng browser thật để xác nhận trạng thái isolation và hành vi worker.

## 14. Ví dụ cấu hình server

### 14.1 Nginx

Ví dụ cho ứng dụng cần cross-origin isolation:

```nginx
add_header Cross-Origin-Opener-Policy "same-origin" always;
add_header Cross-Origin-Embedder-Policy "require-corp" always;
```

Nếu dùng `credentialless`, chỉ thay COEP sau khi xác nhận yêu cầu credentials của các tài nguyên:

```nginx
add_header Cross-Origin-Opener-Policy "same-origin" always;
add_header Cross-Origin-Embedder-Policy "credentialless" always;
```

Kiểm tra scope `http`, `server`, `location` và quy tắc kế thừa `add_header`. Nếu location riêng có `add_header` khác, có thể làm header ở cấp trên không còn được áp dụng như mong đợi.

### 14.2 Apache

Ví dụ:

```apache
Header always set Cross-Origin-Opener-Policy "same-origin"
Header always set Cross-Origin-Embedder-Policy "require-corp"
```

Đảm bảo module headers được bật và cấu hình nằm đúng virtual host/directory. Kiểm tra response sau proxy/CDN vì tầng phía trước có thể loại bỏ hoặc ghi đè header.

### 14.3 Node/Express

Ví dụ middleware:

```javascript
app.use((req, res, next) => {
  res.setHeader("Cross-Origin-Opener-Policy", "same-origin");
  res.setHeader("Cross-Origin-Embedder-Policy", "require-corp");
  next();
});
```

Chỉ áp dụng middleware cho các route/ứng dụng đã được đánh giá tương thích. Nếu cùng server phục vụ cả trang cần popup cross-origin và trang cần SAB, cân nhắc tách policy theo route hoặc subdomain.
## 15. Fallback khi không có cross-origin isolation

Không phải ứng dụng nào cũng cần shared memory. Nếu browser không hỗ trợ SAB hoặc document chưa được cross-origin isolated, hãy chọn phương án giao tiếp phù hợp:

| Nhu cầu | Phương án |
| --- | --- |
| Gửi dữ liệu một lần tới worker | postMessage() với structured clone. |
| Chuyển một buffer lớn và không cần dùng lại ở sender | Transfer ArrayBuffer trong transfer list. |
| Gửi cập nhật nhỏ, thường xuyên | Message protocol có batching hoặc coalescing. |
| Tính toán nền | Web Worker với dữ liệu đầu vào/đầu ra theo batch. |
| Chia sẻ trạng thái đồng thời thật sự | SharedArrayBuffer khi cross-origin isolation và browser hỗ trợ. |

Ví dụ chuyển quyền sở hữu ArrayBuffer:

```javascript
const buffer = new ArrayBuffer(1024 * 1024);
const worker = new Worker("/worker.js");

worker.postMessage({ buffer }, [buffer]);

// Sau transfer, buffer phía sender đã detached.
console.log(buffer.byteLength); // 0
```

Worker nhận buffer và có thể xử lý mà không cần tạo thêm bản sao ban đầu. Nếu sender cần dữ liệu sau đó, phải thiết kế vòng đời ownership hoặc tạo buffer mới.

### 15.1 Fallback không được thay bằng kiểm tra bảo mật yếu hơn

Không hạ COOP/COEP trên toàn bộ ứng dụng chỉ để một browser cũ dùng được SAB. Hãy dùng capability detection và fallback theo chức năng. Các endpoint và dữ liệu vẫn phải được bảo vệ bằng authentication, authorization, CORS/CORP và các chính sách phù hợp.

## 16. Lỗi triển khai thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| crossOriginIsolated là false dù trang dùng HTTPS | Thiếu COOP hoặc COEP, hoặc response cuối không có header. | Kiểm tra response document sau redirect. |
| SAB không khả dụng | Browser/context không hỗ trợ hoặc chưa isolated. | Kiểm tra secure context, crossOriginIsolated và feature support. |
| Ảnh/font CDN bị chặn | COEP require-corp nhưng tài nguyên no-cors thiếu CORP phù hợp. | Cấu hình CORP ở server tài nguyên hoặc dùng CORS mode phù hợp. |
| Fetch API cross-origin lỗi CORS | API không cấp CORS cho origin frontend. | Cấu hình CORS đúng origin và credentials policy. |
| Widget hoặc quảng cáo không tải | Iframe/SDK không tương thích COEP hoặc không cung cấp headers cần thiết. | Kiểm tra vendor, thay tích hợp hoặc cô lập chức năng. |
| OAuth popup không gọi được opener | COOP đã tách browsing context group. | Chuyển sang redirect/callback flow hoặc thiết kế tích hợp khác. |
| SAB hoạt động nhưng counter sai | Race condition do thao tác đọc/cộng/ghi không nguyên tử. | Dùng Atomics.add() hoặc giao thức đồng bộ phù hợp. |
| Giao diện bị treo | Main thread gọi thao tác chờ đồng bộ. | Không gọi Atomics.wait() trên main thread. |
| Header có trong cấu hình nhưng thiếu ở browser | Proxy/CDN/location làm mất hoặc ghi đè header. | Kiểm tra response cuối và quy tắc kế thừa header. |
| credentialless làm nội dung bên thứ ba thay đổi | Request không gửi cookie/HTTP credentials. | Chỉ dùng với tài nguyên không cần credentials hoặc chuyển sang CORS/CORP phù hợp. |

## 17. Quy trình rollout cross-origin isolation

1. **Xác định lý do cần SAB:** đo chi phí copy, latency và lợi ích của shared memory. Nếu message/transfer đủ đáp ứng, tránh thêm độ phức tạp isolation.
2. **Lập bản đồ tài nguyên:** liệt kê ảnh, font, script, iframe, worker, analytics, video, API và popup cross-origin.
3. **Phân loại request:** xác định request mode, credentials mode, response headers và chủ sở hữu từng host.
4. **Kiểm tra tích hợp:** thử OAuth, payment, popup, widget, micro-frontend và các route ít được sử dụng.
5. **Chọn COEP:** dùng require-corp khi có thể cấu hình CORP/CORS đầy đủ; cân nhắc credentialless khi các request no-cors không cần credentials.
6. **Triển khai trên staging:** phát COOP/COEP ở document và worker cần thiết; kiểm tra crossOriginIsolated.
7. **Xử lý vi phạm:** dùng DevTools Network/Console để sửa từng tài nguyên bị chặn, không mở wildcard toàn cục.
8. **Kiểm thử shared memory:** chạy worker, Atomics, timeout, worker restart và fallback.
9. **Rollout có giám sát:** theo dõi lỗi popup, tài nguyên, worker và browser compatibility sau triển khai.
10. **Duy trì:** cập nhật allowlist và đánh giá lại khi thêm SDK, CDN hoặc đối tác mới.

## 18. Checklist triển khai SharedArrayBuffer

- [ ] Trang chạy trong secure context.
- [ ] window.crossOriginIsolated trả về true trên browser mục tiêu.
- [ ] COOP được cấu hình theo nhu cầu, thường là same-origin.
- [ ] COEP được chọn rõ ràng: require-corp hoặc credentialless.
- [ ] Tài nguyên cross-origin đã được kiểm kê theo request mode.
- [ ] CORS/CORP được cấu hình tối thiểu ở các server tài nguyên cần thiết.
- [ ] Popup, OAuth, payment, iframe và analytics đã được kiểm thử.
- [ ] Worker script và các import tương thích với isolation.
- [ ] SharedArrayBuffer chỉ chia sẻ với contexts được kiểm soát.
- [ ] Atomics được dùng cho trạng thái đồng bộ có tranh chấp.
- [ ] Không block main thread bằng Atomics.wait().
- [ ] Có fallback dùng ArrayBuffer/transfer hoặc message khi không có SAB.
- [ ] Có giới hạn buffer, timeout và xử lý worker lỗi.
- [ ] Đã kiểm tra response headers sau reverse proxy/CDN.

## 19. Câu hỏi tự kiểm tra

1. SharedArrayBuffer khác ArrayBuffer ở cách chia sẻ vùng nhớ như thế nào?
2. Vì sao SAB trong web thông thường yêu cầu cross-origin isolation?
3. window.crossOriginIsolated cho biết điều gì?
4. COOP same-origin ảnh hưởng quan hệ opener với popup ra sao?
5. COEP require-corp yêu cầu gì đối với tài nguyên cross-origin no-cors?
6. credentialless khác require-corp ở cách gửi credentials như thế nào?
7. CORP và CORS khác nhau ra sao?
8. Vì sao thêm Access-Control-Allow-Origin không luôn giải quyết được lỗi COEP?
9. Vì sao view[0] = view[0] + 1 có thể mất cập nhật khi nhiều worker cùng chạy?
10. Atomics.add() và Atomics.wait()/notify() hỗ trợ đồng bộ như thế nào?
11. Vì sao Atomics.wait() không nên chạy trên main thread?
12. Cần kiểm thử những luồng sản phẩm nào trước khi bật COOP/COEP?

## 20. Tổng kết

SharedArrayBuffer cho phép nhiều JavaScript contexts truy cập cùng một vùng nhớ, hữu ích cho xử lý dữ liệu lớn và giao tiếp worker có độ trễ thấp. Đổi lại, ứng dụng phải quản lý race condition và đồng bộ bằng các thao tác Atomics phù hợp. Trong web thông thường, SAB cần môi trường cross-origin isolated; kiểm tra trạng thái bằng window.crossOriginIsolated.

Để bật isolation, thường cấu hình COOP same-origin và COEP require-corp hoặc credentialless trên response document, đồng thời bảo đảm tài nguyên cross-origin tuân thủ CORS/CORP theo request mode. COOP có thể ảnh hưởng popup và OAuth; COEP có thể chặn CDN, font, iframe hoặc SDK bên thứ ba. Hãy kiểm kê tích hợp, thử nghiệm trên browser mục tiêu và chuẩn bị fallback bằng ArrayBuffer/transfer trước khi triển khai rộng. Shared memory chỉ nên được chia sẻ với contexts được kiểm soát và mọi thao tác nhạy cảm vẫn cần kiểm tra ở ứng dụng/backend.
