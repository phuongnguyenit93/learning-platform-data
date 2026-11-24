# Camera

> **Chương:** Permissions  
> **Chủ đề:** Camera  
> **Module:** SECURITY_APPLICATION_SECURITY_BROWSER_SECURITY — phân tích ranh giới bảo mật giữa trình duyệt, origin, cookie và ứng dụng web để hiểu Same-Origin Policy, CORS và các cơ chế cách ly. Thực hành phòng vệ XSS, CSRF, clickjacking bằng CSP, Trusted Types, security headers và kiểm chứng hành vi thực tế.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích điều kiện để một trang web yêu cầu quyền truy cập camera.
2. Dùng navigator.mediaDevices.getUserMedia() để xin quyền và nhận video stream.
3. Phân biệt yêu cầu quyền truy cập với truy vấn trạng thái permission qua Permissions API.
4. Giới hạn quyền camera bằng Permissions Policy và hiểu cách cấp quyền cho iframe.
5. Chọn camera và cấu hình video constraints phù hợp.
6. Giải phóng camera đúng vòng đời bằng cách dừng các MediaStreamTrack.
7. Chẩn đoán lỗi từ quyền người dùng, browser, hệ điều hành, thiết bị và cấu hình nhúng.
8. Thiết kế trải nghiệm camera tôn trọng quyền riêng tư và kiểm thử trong môi trường local.

## 1. Quyền camera trong trình duyệt là gì?

Web API cho phép trang web yêu cầu browser truy cập thiết bị ghi hình, thường là camera trước hoặc camera sau của điện thoại và webcam của máy tính. API chính là navigator.mediaDevices.getUserMedia().

Ví dụ một trang gọi camera:

```js
const stream = await navigator.mediaDevices.getUserMedia({
  audio: false,
  video: true,
});

document.querySelector('video').srcObject = stream;
```

Browser áp dụng các điều kiện bảo mật và quyền riêng tư trước khi cung cấp stream. Tùy browser và trạng thái permission, người dùng có thể thấy hộp thoại hỏi quyền, hoặc request có thể bị từ chối ngay vì chính sách, cài đặt site hay môi trường không đáp ứng điều kiện.

Camera là thiết bị nhạy cảm: hình ảnh có thể tiết lộ khuôn mặt, không gian sống, tài liệu, màn hình hoặc người khác xuất hiện trong khung hình. Vì vậy, ứng dụng cần giải thích lý do sử dụng camera, chỉ xin quyền khi người dùng chủ động bắt đầu chức năng và dừng stream khi không còn cần.

### 1.1. Permission và stream là hai khái niệm khác nhau

- **Permission** là quyết định của browser/người dùng về việc origin có được phép yêu cầu sử dụng thiết bị hay không.
- **MediaStream** là luồng media được cấp sau khi request thành công.
- **MediaStreamTrack** đại diện cho track video hoặc audio trong stream. Track có trạng thái, settings và vòng đời riêng.

Có permission granted không bảo đảm camera đang tồn tại hoặc có thể mở được. Thiết bị có thể bị rút, đang được ứng dụng khác sử dụng hoặc bị hệ điều hành chặn. Ngược lại, trạng thái prompt không có nghĩa request chắc chắn sẽ hiển thị hộp thoại; browser có thể áp dụng thêm chính sách khác.

## 2. Điều kiện để yêu cầu camera

### 2.1. Secure context

getUserMedia() chỉ khả dụng trong **secure context**. Thông thường, trang phải được tải qua HTTPS với certificate hợp lệ. Các địa chỉ loopback như http://localhost được browser xem là nguồn đáng tin cậy trong quá trình phát triển ở các browser hiện đại.

| URL | Khả năng sử dụng camera |
|---|---|
| https://app.example.test | Có, nếu certificate hợp lệ và các điều kiện khác được đáp ứng |
| http://localhost:3000 | Thường được xem là secure context cho phát triển local |
| http://192.168.1.20 | Thông thường không phải secure context |
| http://app.example.test | Không đáp ứng yêu cầu secure context |

Nếu navigator.mediaDevices hoặc getUserMedia không tồn tại, kiểm tra URL, secure context và browser support trước khi điều tra phần cứng.

### 2.2. Document và quyền nhúng

Trang top-level thường có thể yêu cầu camera sau khi người dùng cho phép. Với nội dung chạy trong iframe, browser còn kiểm tra **Permissions Policy** của document cha và thuộc tính allow của iframe.

Một iframe cross-origin có thể bị từ chối quyền camera ngay cả khi người dùng từng cấp quyền cho origin của iframe, nếu parent không cho phép tính năng đó. Ngược lại, việc parent cho phép camera qua Permissions Policy cũng không tự động cấp permission cho người dùng; browser vẫn áp dụng cơ chế xin quyền của origin cần truy cập.

### 2.3. Người dùng có quyền quyết định

Không có cách hợp lệ để JavaScript âm thầm vượt qua lựa chọn của người dùng. Browser có thể ghi nhớ quyết định cho origin, nhưng người dùng vẫn có thể thu hồi trong Site Settings hoặc cài đặt quyền riêng tư của hệ điều hành.

Ứng dụng nên gọi getUserMedia() sau hành động rõ ràng như nhấn nút “Bật camera”. Không tự động bật camera ngay khi trang vừa mở hoặc khi người dùng chỉ xem nội dung không liên quan tới camera.

## 3. Gọi getUserMedia và hiển thị video

getUserMedia() nhận một đối tượng constraints. Mỗi loại media có thể được bật hoặc tắt bằng boolean hoặc cấu hình chi tiết.

Ví dụ chỉ xin video:

```js
const stream = await navigator.mediaDevices.getUserMedia({
  audio: false,
  video: true,
});
```

Gắn stream vào phần tử video:

```html
<video id="preview" autoplay playsinline muted controls></video>
```

```js
const video = document.querySelector('#preview');
video.srcObject = stream;
await video.play();
```

- autoplay yêu cầu phần tử bắt đầu phát khi có thể.
- playsinline giúp video tiếp tục hiển thị trong layout trên các thiết bị di động hỗ trợ thuộc tính này.
- muted phù hợp với preview cục bộ để tránh phản hồi âm thanh ngoài ý muốn; lab chỉ xin video, không xin microphone.
- srcObject nhận trực tiếp MediaStream.

Một số browser áp dụng autoplay policy; gọi play() có thể bị từ chối. Hãy bắt lỗi Promise của play() và cung cấp thao tác phát lại khi cần.

### 3.1. Xin quyền sau một thao tác có chủ đích

Ví dụ:

```html
<button id="start-camera" type="button">Bật camera</button>
<button id="stop-camera" type="button">Tắt camera</button>
<video id="preview" autoplay playsinline muted></video>
<p id="status" role="status"></p>
```

```js
const startButton = document.querySelector('#start-camera');
const stopButton = document.querySelector('#stop-camera');
const preview = document.querySelector('#preview');
const status = document.querySelector('#status');
let activeStream = null;

startButton.addEventListener('click', async () => {
  status.textContent = 'Đang yêu cầu quyền camera...';

  try {
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: false,
      video: true,
    });

    activeStream = stream;
    preview.srcObject = stream;
    try {
      await preview.play();
    } catch (playError) {
      status.textContent =
        'Camera đã mở; hãy nhấn phát video nếu browser chặn autoplay.';
      return;
    }
    status.textContent = 'Camera đang hoạt động.';
  } catch (error) {
    status.textContent = 'Không thể mở camera: ' + error.name;
  }
});

stopButton.addEventListener('click', () => {
  if (activeStream) {
    activeStream.getTracks().forEach((track) => track.stop());
    activeStream = null;
  }
  preview.pause();
  preview.srcObject = null;
  status.textContent = 'Đã tắt camera.';
});
```

Ví dụ này minh họa luồng cơ bản. Ứng dụng production cần xử lý thêm việc nhấn Bật nhiều lần, request đang chờ, component bị tháo khỏi DOM và stream được thay thế bởi request mới.

### 3.2. Xử lý request đang chờ

Người dùng có thể chưa chọn Allow hoặc Block trong hộp thoại permission. Promise từ getUserMedia() có thể tiếp tục ở trạng thái pending vô thời hạn nếu người dùng bỏ qua prompt.

Ứng dụng không nên giả định request sẽ kết thúc trong vài giây. Có thể hiển thị trạng thái “Đang chờ bạn chọn quyền”, cho phép người dùng hủy luồng giao diện và bỏ qua kết quả đến muộn. Nếu request trả về stream sau khi giao diện đã đóng, phải dừng ngay các track đó.

Một cách quản lý request generation:

```js
let requestGeneration = 0;
let activeStream = null;

async function startCamera() {
  const generation = ++requestGeneration;
  const stream = await navigator.mediaDevices.getUserMedia({
    audio: false,
    video: true,
  });

  if (generation !== requestGeneration) {
    stream.getTracks().forEach((track) => track.stop());
    return;
  }

  activeStream?.getTracks().forEach((track) => track.stop());
  activeStream = stream;
  preview.srcObject = stream;
}

function cancelCameraRequest() {
  requestGeneration++;
}
```

cancelCameraRequest() không hủy hộp thoại permission hoặc Promise của browser; nó chỉ đánh dấu kết quả đang chờ là cũ để ứng dụng không sử dụng stream trả về sau đó.

## 4. Đọc trạng thái permission bằng Permissions API

Permissions API cho phép truy vấn trạng thái permission mà browser công bố:

```js
async function readCameraPermission() {
  if (!navigator.permissions?.query) {
    return 'unknown';
  }

  try {
    const result = await navigator.permissions.query({
      name: 'camera',
    });
    return result.state;
  } catch {
    return 'unknown';
  }
}
```

Các trạng thái thường gặp:

| State | Ý nghĩa |
|---|---|
| granted | Browser báo permission đã được cấp |
| denied | Permission bị từ chối hoặc bị policy/cấu hình chặn |
| prompt | Browser có thể cần hỏi người dùng khi ứng dụng yêu cầu |

Permissions API có khác biệt về hỗ trợ giữa browser và phiên bản. Descriptor camera có thể không được triển khai; query() có thể reject dù getUserMedia() vẫn dùng được. Vì vậy, hãy bắt lỗi và coi trạng thái không đọc được là unknown, không suy luận rằng người dùng đã từ chối.

Truy vấn trạng thái không hiển thị prompt và không chứng minh thiết bị có thể mở được. Chỉ getUserMedia() mới thực hiện yêu cầu truy cập thực tế.

Có thể theo dõi thay đổi trạng thái:

```js
const permission = await navigator.permissions.query({
  name: 'camera',
});

permission.addEventListener('change', () => {
  console.log('Camera permission:', permission.state);
});
```

Sự kiện change chỉ phản ánh thay đổi mà browser công bố qua Permissions API. Không phải browser nào cũng hỗ trợ descriptor camera hoặc phát hiện mọi thay đổi ở hệ điều hành ngay lập tức.

## 5. Permissions Policy giới hạn quyền camera

Permissions Policy cho phép chủ sở hữu document giới hạn những tính năng browser mà trang và các frame con có thể sử dụng. Directive dành cho camera là camera.

Ví dụ chỉ cho phép document cùng origin:

```http
Permissions-Policy: camera=(self), microphone=()
```

- camera=(self) cho phép camera trong document cùng origin theo policy.
- microphone=() không cho phép microphone trong document và các frame con theo policy đó.

Nếu ứng dụng không cần camera, có thể cấm rõ ràng:

```http
Permissions-Policy: camera=()
```

Header này giới hạn khả năng gọi API. Nó không cấp quyền cho người dùng và không thay hộp thoại permission.

### 5.1. Cấp camera cho iframe cross-origin

Giả sử parent ở https://app.example.test nhúng ứng dụng họp ở https://meet.example.test. Parent cần cho phép origin child qua response header:

```http
Permissions-Policy: camera=(self "https://meet.example.test")
```

Iframe cũng cần khai báo quyền được delegate:

```html
<iframe
  src="https://meet.example.test/room"
  title="Phòng họp"
  allow="camera">
</iframe>
```

Hai điều kiện này phối hợp với nhau:

1. Policy của parent phải cho phép origin child.
2. Container policy của iframe phải delegate tính năng camera.
3. Document child phải ở secure context và người dùng phải cấp permission cho origin cần truy cập.
4. Policy do document child hoặc ancestor khác đặt không được chặn tính năng đó.

Thuộc tính allow không thể vượt qua policy của parent. Nếu parent gửi camera=(), iframe không thể tự mở quyền bằng cách thêm allow="camera".

### 5.2. Permissions Policy và sandbox

Iframe có sandbox có thể bị hạn chế thêm. Khi kết hợp sandbox với camera, cần kiểm tra origin và token sandbox thực tế; document có opaque origin hoặc bị giới hạn script có thể không hoạt động như iframe thông thường.

Không thêm allow-same-origin hoặc các sandbox token khác chỉ để làm camera chạy. Hãy xác định quyền tối thiểu cần thiết, tách nội dung không tin cậy sang origin riêng và kiểm tra Console để biết tính năng bị chặn ở lớp nào.

## 6. Chọn camera và cấu hình video constraints

Constraints mô tả loại media và chất lượng mong muốn. Browser cố gắng chọn thiết bị phù hợp, nhưng không phải mọi thiết bị đều hỗ trợ mọi constraint.

Ví dụ ưu tiên camera trước và độ phân giải HD:

```js
const stream = await navigator.mediaDevices.getUserMedia({
  audio: false,
  video: {
    facingMode: { ideal: 'user' },
    width: { ideal: 1280 },
    height: { ideal: 720 },
  },
});
```

Các constraint thường dùng:

| Constraint | Ví dụ | Ý nghĩa |
|---|---|---|
| facingMode | { ideal: 'environment' } | Ưu tiên camera sau trên thiết bị có nhiều camera |
| width | { ideal: 1280 } | Ưu tiên chiều rộng video |
| height | { ideal: 720 } | Ưu tiên chiều cao video |
| frameRate | { ideal: 30, max: 30 } | Ưu tiên tốc độ khung hình |
| deviceId | { exact: selectedId } | Yêu cầu đúng thiết bị đã chọn |

ideal là giá trị mong muốn; browser có thể chọn cấu hình gần nhất. exact, min hoặc max đặt ràng buộc chặt hơn và có thể làm request thất bại nếu thiết bị không đáp ứng.

### 6.1. Liệt kê thiết bị

enumerateDevices() cho phép liệt kê thiết bị media:

```js
const devices = await navigator.mediaDevices.enumerateDevices();
const cameras = devices.filter((device) => device.kind === 'videoinput');

for (const camera of cameras) {
  console.log(camera.label, camera.deviceId);
}
```

Trước khi người dùng cấp quyền, browser có thể ẩn label hoặc hạn chế thông tin thiết bị để giảm khả năng fingerprinting. Sau khi có quyền, thông tin thiết bị có thể đầy đủ hơn. Không coi danh sách rỗng hoặc label trống là bằng chứng chắc chắn máy không có camera.

### 6.2. Chuyển camera

Để chuyển sang camera khác, ứng dụng có thể chọn deviceId từ danh sách đã được browser cho phép hiển thị, rồi gọi getUserMedia() với constraint tương ứng. Sau khi stream mới hoạt động, dừng stream cũ để không giữ hai camera mở đồng thời.

Không lưu deviceId như một định danh thiết bị bền vững hoặc gửi nó lên server nếu không có nhu cầu rõ ràng. ID có thể thay đổi theo browser, origin, quyền riêng tư và thiết bị.

## 7. Vòng đời MediaStream và giải phóng camera

Sau khi không còn cần camera, dừng mọi track:

```js
function stopStream(stream) {
  if (!stream) return;
  stream.getTracks().forEach((track) => track.stop());
}
```

video.pause() hoặc xóa video.srcObject không thay thế việc dừng track. Track vẫn có thể giữ camera hoạt động nếu ứng dụng không gọi stop().

Một quy trình cleanup:

```js
function stopCamera() {
  if (activeStream) {
    activeStream.getTracks().forEach((track) => track.stop());
    activeStream = null;
  }

  preview.pause();
  preview.srcObject = null;
}

window.addEventListener('pagehide', stopCamera);
```

Trong ứng dụng SPA, gọi cleanup khi component unmount hoặc khi người dùng rời khỏi tính năng camera. Không chỉ dựa vào page unload vì route có thể thay đổi mà document vẫn tồn tại.

### 7.1. Track state và sự kiện ended

Track có readyState như live hoặc ended. Sự kiện ended có thể xảy ra khi thiết bị bị rút, quyền bị thu hồi hoặc nguồn media kết thúc:

```js
const [videoTrack] = activeStream.getVideoTracks();

videoTrack.addEventListener('ended', () => {
  status.textContent = 'Camera đã dừng hoặc không còn khả dụng.';
});
```

Gọi track.stop() chủ động sẽ chuyển track sang trạng thái ended nhưng không nhất thiết phát sự kiện ended cho chính track đó. Vì vậy, code cleanup chủ động cần tự cập nhật giao diện thay vì chờ sự kiện.

### 7.2. Tắt camera không đồng nghĩa thu hồi permission

track.stop() giải phóng việc sử dụng stream hiện tại. Nó không xóa quyết định permission mà người dùng đã cấp cho origin. Nếu muốn thu hồi quyền, người dùng thực hiện qua giao diện quyền riêng tư của browser hoặc hệ điều hành.

Không thể dùng JavaScript để âm thầm xóa permission đã cấp hoặc buộc browser hiển thị lại prompt.

## 8. Các lỗi thường gặp khi mở camera

| Lỗi | Nguyên nhân thường gặp | Hướng kiểm tra |
|---|---|---|
| NotAllowedError | Người dùng từ chối, site setting chặn, Permissions Policy chặn, hệ điều hành không cấp quyền hoặc môi trường không đáp ứng điều kiện | Kiểm tra prompt, Site Settings, OS privacy settings, secure context và header policy |
| NotFoundError | Không có thiết bị phù hợp với constraints | Kiểm tra camera có được hệ điều hành nhận diện và thử video: true |
| NotReadableError | Thiết bị không mở được, đang bị ứng dụng khác giữ hoặc driver gặp lỗi | Đóng ứng dụng khác đang dùng camera, kiểm tra OS/driver và thử lại |
| OverconstrainedError | Constraint bắt buộc không thể đáp ứng | Đọc thuộc tính constraint, nới exact, min hoặc max |
| AbortError | Browser hoặc hệ thống không thể hoàn tất việc mở thiết bị | Kiểm tra log browser, driver và thử lại sau khi thiết bị ổn định |
| TypeError | Constraints không hợp lệ/rỗng hoặc API không khả dụng trong môi trường hiện tại | Kiểm tra cấu trúc constraints và navigator.mediaDevices |
| SecurityError | Quyền media bị vô hiệu hóa trong document/browser theo cấu hình | Kiểm tra cài đặt browser và chính sách triển khai |
| play() bị reject | Autoplay policy hoặc trạng thái phần tử video không cho phát | Gọi play() sau thao tác người dùng và hiển thị nút phát lại |

Không nên hiển thị nguyên stack trace hoặc thông tin thiết bị cho người dùng cuối. Giao diện có thể đưa ra thông báo thân thiện, còn log kỹ thuật chỉ ghi tên lỗi, constraint liên quan và route; tránh thu thập dữ liệu hình ảnh.

### 8.1. Phân biệt các lớp từ chối

Khi camera không mở được, điều tra theo thứ tự:

1. **API:** navigator.mediaDevices?.getUserMedia có tồn tại không?
2. **Secure context:** window.isSecureContext có phải true không?
3. **Embedding policy:** Console có báo camera bị Permissions Policy chặn không?
4. **Browser permission:** Site Settings đang Allow, Ask hay Block?
5. **OS permission:** Hệ điều hành có cho browser sử dụng camera không?
6. **Hardware:** Thiết bị có xuất hiện trong hệ điều hành và không bị ứng dụng khác chiếm dụng không?
7. **Constraints:** Thử cấu hình tối thiểu video: true để loại trừ constraint quá chặt.

NotAllowedError có thể đến từ nhiều lớp. Không nên kết luận người dùng đã nhấn Block chỉ dựa vào tên lỗi.

## 9. Quyền riêng tư và thiết kế giao diện

Camera có thể ghi lại dữ liệu cá nhân và môi trường xung quanh. Ứng dụng cần giảm dữ liệu thu thập và làm rõ trạng thái camera.

Các nguyên tắc thiết kế:

- Giải thích camera được dùng để làm gì trước khi gọi API.
- Chỉ xin quyền sau thao tác rõ ràng của người dùng.
- Chỉ yêu cầu video: true nếu không cần microphone; không xin cả audio và video theo thói quen.
- Hiển thị preview và trạng thái camera đang bật.
- Có nút tắt camera dễ tìm, hoạt động ngay cả khi request khác đang chờ.
- Dừng track khi kết thúc cuộc gọi, quét mã, chụp ảnh hoặc rời tính năng.
- Không upload frame hoặc stream lên server nếu chức năng không cần.
- Nếu cần upload, giải thích mục đích, thời hạn lưu và ai có thể truy cập.
- Không lưu ảnh/frame vào local storage hoặc analytics ngoài mục đích đã thông báo.
- Kiểm tra chính sách quyền riêng tư của browser và hệ điều hành; không tìm cách che giấu indicator camera.

Không thể dựa vào việc đèn camera có sáng hay không để xác định stream đang được sử dụng trên mọi thiết bị. Hãy quản lý MediaStreamTrack trong ứng dụng và cung cấp trạng thái rõ ràng.

## 10. Thực hành: lab camera permission với Node.js

Lab chạy một trang local trên http://localhost:3000. Browser hiện đại xem localhost là secure context để phát triển, vì vậy có thể thử getUserMedia() mà không cần dựng TLS cho lab. Nếu browser hoặc môi trường quản trị không chấp nhận localhost, chạy lab qua HTTPS với certificate được tin cậy.

Lab có các chức năng:

- Kiểm tra isSecureContext và khả năng tồn tại của API.
- Truy vấn permission state nếu browser hỗ trợ descriptor camera.
- Xin quyền camera sau khi người dùng nhấn nút.
- Hiển thị video preview và thông tin track.
- Dừng toàn bộ track và xóa preview.
- Hiển thị lỗi theo tên DOMException.

### Bước 1 — Tạo file camera-permission-lab.cjs

```js
const http = require('node:http');

const html = [
  '<!doctype html>',
  '<html lang="vi"><head><meta charset="utf-8">',
  '<meta name="viewport" content="width=device-width, initial-scale=1">',
  '<title>Camera permission lab</title></head><body>',
  '<h1>Camera permission lab</h1>',
  '<p id="environment"></p>',
  '<p id="permission">Permission: chưa kiểm tra</p>',
  '<button id="check" type="button">Kiểm tra permission</button>',
  '<button id="start" type="button">Bật camera</button>',
  '<button id="stop" type="button">Tắt camera</button>',
  '<video id="preview" autoplay playsinline muted controls></video>',
  '<p id="status" role="status">Camera chưa được yêu cầu.</p>',
  '<pre id="details"></pre>',
  '<script>',
  "const environment = document.querySelector('#environment');",
  "const permissionText = document.querySelector('#permission');",
  "const status = document.querySelector('#status');",
  "const details = document.querySelector('#details');",
  "const preview = document.querySelector('#preview');",
  'let activeStream = null;',
  'let requestGeneration = 0;',
  'let permissionStatus = null;',
  "environment.textContent = 'Secure context: ' + window.isSecureContext +",
  "  ' | getUserMedia: ' + Boolean(navigator.mediaDevices?.getUserMedia);",
  'async function checkPermission() {',
  '  if (permissionStatus) {',
  "    permissionText.textContent = 'Permission state: ' + permissionStatus.state;",
  '    return;',
  '  }',
  '  if (!navigator.permissions?.query) {',
  "    permissionText.textContent = 'Permission API không được hỗ trợ.';",
  '    return;',
  '  }',
  '  try {',
  "    permissionStatus = await navigator.permissions.query({ name: 'camera' });",
  "    permissionText.textContent = 'Permission state: ' + permissionStatus.state;",
  "    permissionStatus.addEventListener('change', () => {",
  "      permissionText.textContent = 'Permission state: ' + permissionStatus.state;",
  '    });',
  '  } catch (error) {',
  "    permissionText.textContent = 'Không truy vấn được descriptor camera: ' + error.name;",
  '  }',
  '}',
  'async function startCamera() {',
  '  if (!navigator.mediaDevices?.getUserMedia) {',
  "    status.textContent = 'getUserMedia không khả dụng. Kiểm tra secure context và browser.';",
  '    return;',
  '  }',
  '  const generation = ++requestGeneration;',
  "  status.textContent = 'Đang chờ browser và người dùng quyết định quyền camera...';",
  '  details.textContent = "";',
  '  try {',
  '    const stream = await navigator.mediaDevices.getUserMedia({',
  '      audio: false,',
  '      video: {',
  "        facingMode: { ideal: 'user' },",
  '        width: { ideal: 1280 },',
  '        height: { ideal: 720 }',
  '      }',
  '    });',
  '    if (generation !== requestGeneration) {',
  '      stream.getTracks().forEach((track) => track.stop());',
  '      return;',
  '    }',
  '    activeStream?.getTracks().forEach((track) => track.stop());',
  '    activeStream = stream;',
  '    preview.srcObject = stream;',
  '    try {',
  '      await preview.play();',
  '    } catch (playError) {',
  "      status.textContent = 'Camera đã mở; nhấn phát video nếu browser chặn autoplay.';",
  '    }',
  '    const track = stream.getVideoTracks()[0];',
  '    details.textContent = JSON.stringify({',
  '      label: track?.label,',
  '      readyState: track?.readyState,',
  '      settings: track?.getSettings()',
  '    }, null, 2);',
  '    if (track) {',
  "      track.addEventListener('ended', () => {",
  "        status.textContent = 'Camera track đã kết thúc.';",
  '      }, { once: true });',
  '    }',
  "    if (status.textContent.startsWith('Đang chờ')) {",
  "      status.textContent = 'Camera đang hoạt động.';",
  '    }',
  '  } catch (error) {',
  "    status.textContent = 'Không thể mở camera: ' + error.name;",
  '    details.textContent = error.message || "";',
  '  }',
  '}',
  'function stopCamera() {',
  '  requestGeneration++;',
  '  if (activeStream) {',
  '    activeStream.getTracks().forEach((track) => track.stop());',
  '    activeStream = null;',
  '  }',
  '  preview.pause();',
  '  preview.srcObject = null;',
  "  status.textContent = 'Đã dừng camera và giải phóng stream.';",
  '  details.textContent = "";',
  '}',
  "document.querySelector('#check').addEventListener('click', checkPermission);",
  "document.querySelector('#start').addEventListener('click', startCamera);",
  "document.querySelector('#stop').addEventListener('click', stopCamera);",
  "window.addEventListener('pagehide', stopCamera);",
  'checkPermission();',
  '</script>',
  '</body></html>',
].join('\n');

const server = http.createServer((req, res) => {
  const url = new URL(req.url, 'http://localhost:3000');
  if (req.method !== 'GET' || url.pathname !== '/') {
    res.writeHead(404, { 'Content-Type': 'text/plain; charset=utf-8' });
    return res.end('Not found');
  }
  res.writeHead(200, {
    'Content-Type': 'text/html; charset=utf-8',
    'Cache-Control': 'no-store',
    'X-Content-Type-Options': 'nosniff',
    'Permissions-Policy': 'camera=(self), microphone=()'
  });
  res.end(html);
});

server.listen(3000, 'localhost', () => {
  console.log('Open http://localhost:3000');
});
```

### Bước 2 — Chạy lab

```sh
node camera-permission-lab.cjs
```

Mở http://localhost:3000 trong browser. Nếu cổng 3000 đang được sử dụng, đổi cổng trong dòng server.listen() và URL hiển thị tương ứng.

### Bước 3 — Kiểm tra permission state

Nhấn **Kiểm tra permission**:

- Nếu browser hỗ trợ descriptor camera, trang hiển thị granted, denied hoặc prompt.
- Nếu browser không hỗ trợ, trang hiển thị thông báo API/descriptor không khả dụng.
- Truy vấn này không tự bật hộp thoại và không mở camera.

### Bước 4 — Xin quyền và xem preview

Nhấn **Bật camera**:

1. Browser có thể hỏi quyền nếu trạng thái hiện tại cần prompt.
2. Chọn Allow để mở camera.
3. Video preview xuất hiện và phần details hiển thị label/settings nếu browser cho phép.
4. Chọn Block để kiểm tra nhánh lỗi; trang hiển thị tên lỗi thay vì giả định camera không tồn tại.

Nếu browser đã ghi nhớ quyết định, prompt có thể không xuất hiện. Có thể thay đổi quyền trong Site Settings để thử lại.

### Bước 5 — Dừng camera và kiểm tra vòng đời

Nhấn **Tắt camera**:

- Preview bị xóa.
- Các track trong stream được dừng.
- Trạng thái hiển thị xác nhận stream đã được giải phóng.
- Permission của origin có thể vẫn là granted; điều này bình thường vì dừng stream không thu hồi quyền.

Mở lại camera rồi đóng tab để kiểm tra cleanup khi pagehide.

### Bước 6 — Thử Permissions Policy

Trong code server, thay header:

```http
Permissions-Policy: camera=(self), microphone=()
```

bằng:

```http
Permissions-Policy: camera=(), microphone=()
```

Khởi động lại server và tải lại trang. Khi nhấn Bật camera, browser phải chặn tính năng camera theo policy. Kết quả cụ thể có thể biểu hiện qua NotAllowedError và thông báo trong Console.

Khôi phục camera=(self) sau khi thử xong.

## 11. Kiểm thử camera trong ứng dụng thật

Khi review một tính năng camera, kiểm tra theo các lớp:

1. **Secure context:** URL và certificate có đáp ứng yêu cầu không?
2. **User intent:** request chỉ bắt đầu sau thao tác người dùng có hiểu biết không?
3. **Permission:** ứng dụng xử lý cả granted, denied, prompt và trạng thái không truy vấn được chưa?
4. **Policy:** response header, iframe allow và ancestor policy có cho phép camera không?
5. **Constraints:** có yêu cầu quá chặt hoặc cố định device ID không?
6. **Lifecycle:** mọi track có được dừng khi kết thúc, unmount, thay stream hoặc đóng tính năng không?
7. **Error UX:** lỗi có thông báo bước khắc phục phù hợp mà không đổ lỗi sai cho người dùng không?
8. **Privacy:** có xin microphone hoặc upload stream ngoài nhu cầu không?
9. **Embedding:** iframe cross-origin có được delegate quyền rõ ràng không?
10. **Compatibility:** đã thử trên browser, OS, mobile và thiết bị camera mục tiêu chưa?

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Không có navigator.mediaDevices | Trang không ở secure context hoặc browser không hỗ trợ | Kiểm tra isSecureContext, HTTPS/localhost và browser |
| Không thấy prompt | Permission đã lưu, API bị policy chặn hoặc browser không thể yêu cầu | Kiểm tra Site Settings, Console và Permissions Policy |
| Permission là granted nhưng camera lỗi | Thiết bị bận, bị rút hoặc OS chặn | Kiểm tra NotReadableError, OS privacy và ứng dụng khác |
| Camera sau không được chọn | facingMode chỉ là ideal hoặc thiết bị không có camera sau | Liệt kê video input sau khi có quyền và chọn device phù hợp |
| Iframe không mở camera | Parent policy hoặc iframe allow thiếu | Kiểm tra response header của parent, thuộc tính allow và Console |
| Camera vẫn bật sau khi rời component | Track chưa được stop | Kiểm tra getTracks() và cleanup/unmount |
| Permission query bị reject | Browser không hỗ trợ descriptor camera | Xử lý thành unknown; vẫn thử getUserMedia sau hành động người dùng |
| Video có stream nhưng không phát | Autoplay policy hoặc phần tử video chưa sẵn sàng | Bắt lỗi play() và cho người dùng thao tác phát |

## 12. Checklist triển khai quyền camera

- [ ] Ứng dụng chỉ yêu cầu camera trong secure context.
- [ ] Có giải thích rõ lý do xin quyền trước khi mở camera.
- [ ] Request chỉ bắt đầu sau hành động chủ động của người dùng.
- [ ] Chỉ xin video nếu không cần microphone.
- [ ] Không dựa vào Permissions API để thay thế getUserMedia().
- [ ] Hỗ trợ browser không triển khai descriptor camera.
- [ ] Permissions Policy giới hạn đúng document và iframe được phép.
- [ ] Iframe cross-origin có allow phù hợp và được parent delegate.
- [ ] Constraints có fallback hợp lý; không ép exact nếu không cần.
- [ ] Có xử lý NotAllowedError, NotFoundError, NotReadableError và OverconstrainedError.
- [ ] Dừng mọi MediaStreamTrack khi kết thúc hoặc component unmount.
- [ ] Xử lý request pending và stream trả về muộn.
- [ ] Không upload hoặc lưu frame ngoài mục đích đã thông báo.
- [ ] Có trạng thái camera rõ ràng và nút tắt dễ tìm.
- [ ] Đã kiểm thử browser, thiết bị, OS và luồng nhúng thực tế.

## 13. Câu hỏi tự kiểm tra

**1.** API chính để yêu cầu camera trong browser là gì?  
**Trả lời:** navigator.mediaDevices.getUserMedia() với constraint video.

**2.** Vì sao camera thường chỉ hoạt động trên HTTPS hoặc localhost?  
**Trả lời:** getUserMedia() yêu cầu secure context để bảo vệ quyền truy cập thiết bị nhạy cảm.

**3.** Permissions API query camera có tự hiển thị prompt không?  
**Trả lời:** Không. Nó chỉ truy vấn trạng thái nếu browser hỗ trợ descriptor; prompt được xử lý khi ứng dụng yêu cầu media.

**4.** granted có bảo đảm camera mở được không?  
**Trả lời:** Không. Thiết bị có thể không tồn tại, đang bận, bị rút hoặc bị hệ điều hành chặn.

**5.** Vì sao iframe cross-origin cần cả Permissions Policy và thuộc tính allow?  
**Trả lời:** Parent policy xác định origin được delegate; thuộc tính allow cấp tính năng cho container iframe. Người dùng vẫn phải cấp permission cho origin child.

**6.** ideal khác exact trong constraints như thế nào?  
**Trả lời:** ideal là ưu tiên có thể được điều chỉnh; exact là yêu cầu bắt buộc và có thể làm request thất bại.

**7.** Vì sao phải gọi track.stop()?  
**Trả lời:** Để kết thúc việc sử dụng track và giải phóng camera; pause video hoặc xóa srcObject không thay thế việc dừng track.

**8.** track.stop() có thu hồi permission của origin không?  
**Trả lời:** Không. Nó dừng stream hiện tại; người dùng quản lý việc thu hồi permission qua browser hoặc hệ điều hành.

**9.** NotAllowedError có luôn có nghĩa người dùng nhấn Block không?  
**Trả lời:** Không. Lỗi có thể do browser permission, Permissions Policy, OS privacy hoặc điều kiện bảo mật.

**10.** Vì sao ứng dụng cần xử lý request getUserMedia đang pending?  
**Trả lời:** Người dùng có thể bỏ qua prompt; nếu stream trả về sau khi giao diện đã đóng, ứng dụng phải dừng track thay vì tiếp tục dùng camera.

## Tổng kết

Quyền camera là sự kết hợp giữa secure context, quyết định permission của người dùng, Permissions Policy và khả năng thực tế của thiết bị. Dùng getUserMedia() để yêu cầu stream sau hành động rõ ràng; dùng Permissions API chỉ như tín hiệu trạng thái tùy browser; giới hạn quyền iframe bằng header và thuộc tính allow; chọn constraints có fallback; và luôn dừng mọi track khi kết thúc. Ứng dụng cần xử lý lỗi theo từng lớp, minh bạch về mục đích sử dụng và giảm tối đa việc thu thập hoặc lưu trữ hình ảnh.
