# Permission review

## Mục tiêu bài học

Sau bài này, bạn có thể:

- Lập inventory các quyền mà ứng dụng browser, website, iframe, extension và backend đang sử dụng.
- Phân biệt quyền do người dùng cấp cho browser API với authorization của ứng dụng và quyền truy cập tài nguyên phía server.
- Rà soát quyền camera, microphone, geolocation, notifications, clipboard, sensor và các API nhạy cảm khác.
- Kiểm tra `Permissions-Policy`, quyền được ủy quyền cho iframe và phạm vi host permission của browser extension.
- Xác minh cookie, credential, CORS và CSP không bị hiểu nhầm thành cơ chế cấp quyền nghiệp vụ.
- Thiết kế quy trình cấp quyền theo nhu cầu, thu hồi, xử lý từ chối và giảm quyền khi tính năng không còn cần.
- Thực hiện permission review định kỳ, ghi nhận bằng chứng và phát hiện quyền vượt quá nhu cầu thực tế.

## 1. Permission review là gì?

Permission review là hoạt động rà soát có hệ thống các quyền mà ứng dụng và những thành phần liên quan đang nắm giữ. Trong môi trường browser, quyền có thể được cấp bởi người dùng thông qua prompt của browser, được giới hạn bởi response header, được khai báo trong manifest của extension hoặc được quyết định bởi backend qua role và scope.

Một ứng dụng có thể yêu cầu camera để quét mã, microphone để gọi thoại, geolocation để hiển thị địa điểm, notification để nhắc lịch hoặc clipboard để hỗ trợ thao tác sao chép. Nếu quyền được cấp quá rộng, được giữ quá lâu hoặc không còn cần thiết, rủi ro tăng lên khi website có XSS, dependency bị xâm nhập, extension có lỗi hoặc tài khoản bị chiếm.

Rà soát quyền cần trả lời các câu hỏi:

- Tính năng nào cần quyền và vì sao?
- Quyền được cấp cho origin, frame, extension hay principal nào?
- Quyền có được yêu cầu đúng thời điểm người dùng cần tính năng không?
- Nếu người dùng từ chối hoặc thu hồi quyền, ứng dụng có hoạt động an toàn không?
- Quyền có được giới hạn theo thời gian, tài nguyên, hành động và dữ liệu không?
- Ai chịu trách nhiệm sở hữu quyền, kiểm tra lại và thu hồi khi không còn cần?
- Bằng chứng nào chứng minh quyền đang được thực thi như thiết kế?

Permission review không chỉ là kiểm tra danh sách prompt đã xuất hiện. Nó là một phần của vận hành bảo mật: inventory, phê duyệt, giám sát, rà soát định kỳ, xử lý thay đổi và thu hồi quyền.

## 2. Phân biệt các lớp quyền trong browser security

Nhiều cơ chế có tên gọi hoặc biểu hiện giống “permission” nhưng giải quyết những câu hỏi khác nhau.

| Lớp | Ai quyết định? | Câu hỏi được trả lời | Ví dụ |
| --- | --- | --- | --- |
| Browser permission | Người dùng và browser, đôi khi có thêm policy của tổ chức/OS. | Origin hoặc document có được dùng một capability của thiết bị/browser không? | Camera, microphone, geolocation, notifications. |
| Permissions Policy | Server của document cha và chính sách nhúng của frame. | Document/frame nào được phép sử dụng một số browser feature? | `camera=()`, `geolocation=(self)`. |
| Application authorization | Backend và hệ thống identity/access management. | Người dùng đã xác thực có được thực hiện hành động trên resource này không? | Xem hồ sơ, xuất báo cáo, quản trị tenant. |
| OAuth/OIDC scope | Authorization server và resource server. | Client/token được phép gọi những API hoặc phạm vi nào? | `profile:read`, `files:download`. |
| Host permission của extension | Người dùng, browser và manifest/quy trình cấp quyền extension. | Extension có thể chạy content script hoặc truy cập host nào? | `https://portal.example.com/*`, `activeTab`. |
| Cookie policy | Server đặt thuộc tính; browser áp dụng quy tắc cookie/privacy. | Cookie có được lưu, gửi hoặc đọc trong ngữ cảnh hiện tại không? | `Secure`, `HttpOnly`, `SameSite`, `Partitioned`. |
| CORS | Server khai báo; browser kiểm tra khi JavaScript đọc response cross-origin. | JavaScript từ origin nào được đọc response? | `Access-Control-Allow-Origin`. |
| CSP | Server đặt policy; browser thực thi. | Trang được tải/chạy những loại resource hoặc script nào? | `script-src`, `frame-ancestors`. |

Các lớp này bổ sung cho nhau. Người dùng cấp quyền camera không có nghĩa tài khoản được phép truy cập mọi cuộc gọi. CORS cho phép một origin đọc response không có nghĩa origin đó đã được xác thực. Cookie được gửi không có nghĩa backend phải chấp nhận request. CSP cho phép script chạy không có nghĩa script đó được phép đọc mọi resource phía server.

Một quy trình review tốt luôn xác định đúng lớp quyền đang được rà soát trước khi đưa ra kết luận.

## 3. Xây dựng permission inventory

Không thể rà soát quyền nếu không biết quyền đang được sử dụng ở đâu. Hãy lập inventory theo tính năng, principal, origin và chủ sở hữu.

Một bản ghi nên có các trường:

| Trường | Nội dung cần ghi |
| --- | --- |
| Permission/capability | Tên quyền hoặc API cần sử dụng. |
| Feature | Tính năng nghiệp vụ sử dụng quyền. |
| Principal | Người dùng, role, service account, extension hoặc frame được cấp quyền. |
| Origin/host | Website, API hoặc host mà quyền áp dụng. |
| Scope | Resource, method, action, dữ liệu hoặc frame được phép. |
| Justification | Lý do nghiệp vụ và hậu quả nếu không cấp quyền. |
| Grant mechanism | Browser prompt, manifest, policy header, role, OAuth scope hoặc cấu hình tổ chức. |
| Lifetime | Một lần, trong phiên, đến khi thu hồi, hoặc thời hạn token. |
| Owner | Nhóm chịu trách nhiệm kỹ thuật/nghiệp vụ. |
| Evidence | Test, manifest, response header, log hoặc cấu hình chứng minh. |
| Review date | Ngày rà soát gần nhất và thời hạn rà soát tiếp theo. |
| Revocation path | Cách thu hồi quyền và cách kiểm tra sau thu hồi. |

Ví dụ inventory rút gọn:

| Feature | Quyền | Phạm vi | Lý do | Review |
| --- | --- | --- | --- | --- |
| Gọi video | Camera, microphone | Origin ứng dụng; chỉ khi người dùng bắt đầu cuộc gọi | Thu hình/âm thanh cho cuộc gọi đang diễn ra | Mỗi release thay đổi media flow và theo chu kỳ vận hành |
| Bản đồ | Geolocation | Chỉ màn hình tìm địa điểm | Đề xuất vị trí gần người dùng | Khi thay đổi provider hoặc API location |
| Nhắc lịch | Notifications | Origin ứng dụng | Hiển thị nhắc lịch đã đăng ký | Khi thay đổi notification flow |
| Chia sẻ báo cáo | Clipboard write | Sau thao tác sao chép của người dùng | Sao chép liên kết hoặc mã tham chiếu | Khi thay đổi chức năng export/share |
| Extension hỗ trợ portal | Host permission | Một số route của portal | Đánh dấu liên kết và hiển thị công cụ hỗ trợ | Mỗi lần thêm host hoặc API extension |
| Quản trị tenant | Backend role/scope | Tenant được phân công | Quản lý người dùng trong tenant | Khi thay đổi role, nhân sự hoặc cấu trúc tenant |

Inventory cần phản ánh quyền thực tế trong production. Source code có thể khai báo một quyền nhưng feature không còn sử dụng; ngược lại, dependency hoặc extension có thể yêu cầu quyền mới mà chủ sở hữu tính năng chưa ghi nhận.

## 4. Browser permissions API

Browser cung cấp các API yêu cầu capability của người dùng hoặc thiết bị. Ví dụ phổ biến gồm:

- Geolocation: lấy vị trí thiết bị.
- Camera và microphone: truy cập thiết bị media qua `getUserMedia()`.
- Notifications: hiển thị thông báo của origin.
- Clipboard: đọc hoặc ghi clipboard theo điều kiện browser.
- MIDI, Bluetooth, USB, Serial, HID và một số sensor: truy cập thiết bị hoặc capability đặc thù.

Không phải mọi API đều dùng cùng một prompt, cùng một lifetime hoặc cùng một cơ chế query. Hỗ trợ `Permissions API` cũng khác giữa browser và từng permission descriptor.

### 4.1. Trạng thái `granted`, `prompt` và `denied`

`navigator.permissions.query()` có thể trả về `PermissionStatus` với trạng thái:

| Trạng thái | Ý nghĩa khái quát | Cách ứng dụng xử lý |
| --- | --- | --- |
| `granted` | Browser hiện cho phép capability theo policy và trạng thái quyền hiện tại. | Chỉ sử dụng khi người dùng thực sự kích hoạt tính năng; vẫn xử lý lỗi khi capability không khả dụng. |
| `prompt` | Chưa có quyết định cấp/từ chối rõ ràng hoặc browser có thể cần hỏi người dùng. | Giải thích nhu cầu rồi gọi API đúng thời điểm; không hỏi ngay khi trang vừa tải. |
| `denied` | Quyền bị từ chối bởi người dùng, browser, policy hoặc một lớp quản trị. | Cung cấp hướng dẫn phù hợp và fallback; không lặp prompt hoặc tìm cách vượt qua quyết định. |

Ví dụ query geolocation:

```js
async function getGeolocationPermissionState() {
  if (!navigator.permissions?.query) {
    return "unsupported";
  }

  try {
    const status = await navigator.permissions.query({ name: "geolocation" });
    return status.state;
  } catch {
    // Permission descriptor có thể không được browser hỗ trợ.
    return "unsupported";
  }
}
```

Query permission không tự hiển thị prompt và không chứng minh API sẽ thành công. Browser có thể trả `granted` nhưng thiết bị không có camera, người dùng chưa kết nối thiết bị hoặc OS từ chối truy cập. Ngược lại, một số API không hỗ trợ descriptor tương ứng dù API chính vẫn có thể được gọi theo quy tắc riêng.

### 4.2. Theo dõi thay đổi quyền

`PermissionStatus` có thể phát sự kiện `change` khi trạng thái quyền thay đổi:

```js
async function watchGeolocationPermission() {
  if (!navigator.permissions?.query) return null;

  try {
    const status = await navigator.permissions.query({ name: "geolocation" });
    const update = () => {
      document.dispatchEvent(new CustomEvent("app:location-permission-change", {
        detail: { state: status.state }
      }));
    };

    status.addEventListener("change", update);
    update();

    return () => status.removeEventListener("change", update);
  } catch {
    return null;
  }
}
```

Ví dụ dùng custom event nội bộ để cập nhật UI. Nếu trang có script không tin cậy hoặc XSS, event/DOM không phải kênh bí mật; không đặt token hay dữ liệu nhạy cảm vào `detail`. Hãy dọn listener khi component hoặc feature kết thúc.

### 4.3. Quyền không đồng nghĩa với khả năng sử dụng

Ứng dụng phải xử lý riêng các tình huống:

- API không tồn tại trong browser hiện tại.
- Permission descriptor không được hỗ trợ.
- Quyền đang ở trạng thái `prompt` hoặc `denied`.
- Người dùng cấp quyền nhưng thiết bị không có hoặc đang được ứng dụng khác sử dụng.
- OS-level privacy setting chặn thiết bị.
- Trang không ở secure context.
- Permissions Policy chặn document hoặc iframe.
- Browser thay đổi quyền hoặc thu hồi quyền giữa lúc tính năng đang chạy.

Không hiển thị “đã bật camera” chỉ dựa trên `permissions.query()`. Hãy xác minh kết quả thật của `getUserMedia()` và trạng thái track.

## 5. Yêu cầu quyền đúng thời điểm

Prompt xuất hiện khi người dùng hiểu rõ hành động và lợi ích. Yêu cầu quyền ngay khi mở trang, trước khi giải thích hoặc khi người dùng chưa dùng tính năng có thể gây mất tin tưởng và làm tăng tỷ lệ từ chối.

Một flow phù hợp:

1. Người dùng chọn “Bắt đầu cuộc gọi video”.
2. Giao diện giải thích cần camera và microphone để truyền hình/âm thanh.
3. Ứng dụng kiểm tra API có hỗ trợ và gọi `getUserMedia()`.
4. Nếu browser hiển thị prompt, người dùng tự quyết định.
5. Nếu được cấp, ứng dụng hiển thị trạng thái thiết bị đang hoạt động và cung cấp nút tắt.
6. Nếu bị từ chối, ứng dụng cho phép tiếp tục ở chế độ chỉ âm thanh hoặc hướng dẫn mở site settings.

Không:

- Yêu cầu camera/microphone khi người dùng chỉ mở trang giới thiệu.
- Gọi lại API liên tục để cố làm prompt xuất hiện sau khi người dùng từ chối.
- Che khuất hoặc gây áp lực để người dùng cấp quyền.
- Mô tả sai mục đích, ví dụ yêu cầu geolocation với lý do không liên quan.
- Coi việc bấm “Allow” là đồng ý với mọi mục đích xử lý dữ liệu tiếp theo.

Quyền browser chỉ cho phép truy cập capability theo chính sách browser. Việc ghi, truyền, lưu trữ hoặc chia sẻ dữ liệu thu được vẫn phải tuân theo mục đích, authorization và chính sách dữ liệu của ứng dụng.

## 6. Rà soát các quyền nhạy cảm phổ biến

### 6.1. Camera và microphone

Rà soát:

- Chỉ yêu cầu khi người dùng bắt đầu chức năng cần media.
- Trang dùng HTTPS hoặc secure context hợp lệ.
- `Permissions-Policy` chỉ cho phép origin/frame cần thiết.
- Không bật camera/microphone tự động sau navigation nếu không có hành động rõ ràng và cơ sở hợp lệ.
- Dừng `MediaStreamTrack` khi người dùng kết thúc hoặc rời tính năng.
- Không giữ stream sống trong background khi không cần.
- Không ghi âm/ghi hình hoặc upload media ngoài mục đích đã thông báo.
- Kiểm tra quyền OS và browser có thể thay đổi trong lúc session đang chạy.

Ví dụ dừng media:

```js
function stopMediaStream(stream) {
  for (const track of stream?.getTracks?.() ?? []) {
    track.stop();
  }
}
```

Test cần xác minh camera/microphone được dừng khi kết thúc cuộc gọi, logout hoặc component bị hủy. Dừng track giải phóng việc sử dụng thiết bị của stream đó; nó không xóa bản ghi đã upload hoặc revoke quyền browser đã cấp.

### 6.2. Geolocation

Rà soát:

- Chỉ yêu cầu vị trí khi người dùng kích hoạt tính năng cần vị trí.
- Chọn `enableHighAccuracy`, `timeout` và `maximumAge` theo nhu cầu; không mặc định cần độ chính xác cao.
- Chỉ lấy vị trí một lần nếu chức năng không cần theo dõi liên tục.
- Nếu dùng `watchPosition()`, luôn gọi `clearWatch()` khi không còn cần.
- Không lưu tọa độ chi tiết hoặc gửi về analytics nếu không có mục đích rõ.
- Cung cấp cách nhập địa chỉ thủ công khi người dùng từ chối.

Ví dụ quản lý watch:

```js
let watchId;

function startLocationWatch(onPosition, onError) {
  if (!navigator.geolocation) {
    onError(new Error("Geolocation is unavailable"));
    return null;
  }

  watchId = navigator.geolocation.watchPosition(onPosition, onError, {
    enableHighAccuracy: false,
    maximumAge: 30_000,
    timeout: 10_000
  });
  return watchId;
}

function stopLocationWatch() {
  if (watchId !== undefined) {
    navigator.geolocation.clearWatch(watchId);
    watchId = undefined;
  }
}
```

### 6.3. Notifications và Push

Notifications cho phép origin hiển thị thông báo theo cơ chế browser/OS. Push có thể cần service worker và subscription với push service.

Rà soát:

- Chỉ hỏi quyền sau khi người dùng bật tính năng nhắc lịch hoặc thông báo.
- Không yêu cầu quyền chỉ để gửi quảng cáo hoặc tăng engagement ngoài mong đợi.
- Xử lý trạng thái `default`, `granted` và `denied` của Notifications API.
- Có cách tắt thông báo trong ứng dụng và hủy subscription khi người dùng tắt tính năng.
- Không chứa dữ liệu nhạy cảm trên lock screen hoặc notification preview.
- Không coi `Notification.permission === "granted"` là bảo đảm notification luôn được hiển thị; OS/browser có thể chặn hoặc trì hoãn.

Khi hủy Push subscription, kiểm tra cả trạng thái ở client và backend. Xóa subscription khỏi database và xử lý endpoint cũ theo thiết kế; không để endpoint push không còn dùng tiếp tục nhận dữ liệu.

### 6.4. Clipboard

Clipboard read/write có thể tiếp xúc dữ liệu người dùng bên ngoài trang. Rà soát:

- Chỉ đọc clipboard khi có hành động rõ ràng và browser cho phép.
- Chỉ ghi đúng nội dung người dùng yêu cầu sao chép.
- Không tự động đọc clipboard khi tải trang hoặc theo dõi thay đổi clipboard.
- Không đưa token, password hoặc dữ liệu nhạy cảm vào clipboard trừ khi chức năng yêu cầu và có cảnh báo phù hợp.
- Kiểm tra secure context, permission/activation và browser support.

Không giả định `navigator.permissions.query({ name: "clipboard-read" })` được hỗ trợ giống nhau trên mọi browser. Clipboard API có thể dùng user activation hoặc quy tắc riêng ngay cả khi Permissions API không trả descriptor tương ứng.

### 6.5. Bluetooth, USB, Serial, HID và sensor

Các API thiết bị có thể cấp quyền cho một thiết bị cụ thể hoặc phiên làm việc, thường qua picker do browser kiểm soát. Rà soát:

- Chỉ mở picker sau thao tác người dùng có mục đích rõ.
- Chọn đúng device và service/characteristic cần thiết.
- Không quét hoặc kết nối thiết bị hàng loạt khi không cần.
- Xử lý disconnect, device removal và permission revocation.
- Không gửi dữ liệu thiết bị ra server ngoài mục đích đã thông báo.
- Kiểm tra secure context, browser support và chính sách doanh nghiệp.

Không coi quyền cho một thiết bị là quyền truy cập mọi thiết bị cùng loại. Kiểm tra danh sách thiết bị được phép và trạng thái kết nối trong browser mục tiêu.

## 7. Permissions Policy và quyền của iframe

Permissions Policy cho phép website giới hạn những browser feature mà document và frame có thể sử dụng. Đây là cơ chế giới hạn theo document, khác với prompt do người dùng cấp.

Ví dụ response header:

```http
Permissions-Policy: camera=(), microphone=(), geolocation=(self), payment=()
```

Trong ví dụ:

- `camera=()` và `microphone=()` tắt các feature đó trong document/frame theo policy.
- `geolocation=(self)` chỉ cho phép same-origin context theo allowlist.
- `payment=()` tắt Payment API nếu ứng dụng không sử dụng.

Chỉ cấu hình feature mà browser hỗ trợ và đối chiếu cú pháp hiện hành của từng feature. Không sao chép một allowlist dài từ dự án khác mà không hiểu tác động.

### 7.1. Ủy quyền có chọn lọc cho iframe

Document cha có thể giới hạn quyền trong header và dùng thuộc tính `allow` để ủy quyền một số feature cho iframe cần thiết.

Ví dụ:

```http
Permissions-Policy: camera=(), microphone=(), geolocation=(self "https://maps.example.test")
```

```html
<iframe
  src="https://maps.example.test/embed"
  title="Bản đồ"
  allow="geolocation">
</iframe>
```

Header của document cha phải cho phép origin được ủy quyền; thuộc tính `allow` của iframe tiếp tục giới hạn feature cho frame đó. Browser còn áp dụng permission của người dùng và các điều kiện khác. `allow` không thể tự mở rộng vượt qua policy của ancestor.

Rà soát từng iframe:

- Origin nào sở hữu frame?
- Frame cần feature nào và cho thao tác gì?
- Có thể bỏ feature khỏi `allow` không?
- Frame có redirect sang origin khác không?
- Có iframe động hoặc third-party script tạo frame ngoài inventory không?
- Frame có `sandbox` phù hợp và không cấp quyền dư không?

Không dùng `allow="camera; microphone; geolocation; ..."` cho mọi iframe nếu widget chỉ cần hiển thị nội dung. Nếu iframe không cần camera, microphone, geolocation hoặc payment, không ủy quyền các feature đó.

### 7.2. Permissions Policy và sandbox iframe

`Permissions-Policy` kiểm soát feature browser; thuộc tính `sandbox` giới hạn năng lực của iframe như script, form, popup và origin behavior. Hai cơ chế có mục đích khác nhau và có thể kết hợp.

Ví dụ iframe nội dung không tin cậy:

```html
<iframe
  src="https://usercontent.example.test/preview"
  sandbox
  referrerpolicy="no-referrer"
  title="Bản xem trước nội dung">
</iframe>
```

Không thêm `allow-scripts`, `allow-same-origin`, `allow-forms` hoặc `allow-popups` trừ khi chức năng cần. Tổ hợp `allow-scripts` và `allow-same-origin` trên iframe cùng origin với trang cha có thể làm suy yếu mục đích sandbox. Kiểm thử các hành vi cần thiết thay vì chỉ xác nhận attribute có mặt.

## 8. Permission Policy không thay thế CORS, CSP hoặc authorization

Các policy browser có thể cùng xuất hiện nhưng giới hạn khác nhau:

| Cơ chế | Giới hạn | Không giải quyết |
| --- | --- | --- |
| Permissions Policy | Browser feature nào document/frame được dùng. | Quyền truy cập API nghiệp vụ hoặc dữ liệu backend. |
| CSP | Nguồn resource/script và một số hành vi document. | Quyền của người dùng đối với resource phía server. |
| CORS | JavaScript origin nào được đọc response cross-origin. | Chặn mọi request cross-site hoặc thay thế CSRF protection. |
| SOP | Quyền đọc giữa các browsing context/origin. | Authorization nghiệp vụ và mọi side effect của request. |
| Cookie attributes | Khi nào cookie được lưu/gửi/đọc. | Xác minh quyền của principal ở backend. |
| Backend authorization | Principal được làm gì trên resource nào. | Quyền truy cập camera, clipboard hoặc thiết bị của browser. |

Ví dụ, nếu API trả `Access-Control-Allow-Origin: https://partner.example`, JavaScript của partner có thể đọc response theo CORS. Điều đó không có nghĩa partner được phép đọc mọi account. Backend vẫn phải xác thực token/session và kiểm tra scope/tenant cho từng resource.

Tương tự, nếu browser cấp geolocation cho origin, server không được mặc định người dùng đã đồng ý lưu tọa độ lâu dài hoặc chia sẻ với đối tác. Consent và mục đích xử lý dữ liệu là quyết định riêng.

## 9. Rà soát quyền của browser extension

Extension có thể có quyền rộng hơn website thông thường vì được cấp API riêng. Rà soát manifest và quyền thực tế sau cài đặt/cập nhật.

Các mục cần kiểm tra:

- `permissions`: API extension nào được yêu cầu, ví dụ `storage`, `scripting`, `tabs` hoặc `downloads`.
- `host_permissions`: host nào extension có thể truy cập qua API cần quyền host.
- `content_scripts.matches`: website nào nhận content script.
- `optional_permissions` và `optional_host_permissions`: quyền nào chỉ được xin khi người dùng kích hoạt tính năng.
- `activeTab`: có thể thay quyền host thường trực bằng quyền tạm thời theo thao tác người dùng không?
- `web_accessible_resources`: tài nguyên nào được website tải; có chứa dữ liệu nội bộ không?
- Message handlers: content script/page có thể yêu cầu service worker thực hiện hành động đặc quyền nào?
- Extension update: có quyền mới nào được thêm và người dùng có được thông báo theo cơ chế browser không?

Không cấp `<all_urls>` hoặc quyền `cookies`, `webRequest`, `debugger`, `nativeMessaging` nếu tính năng không cần. Mỗi quyền nên có owner, justification và test chứng minh phạm vi thực tế.

### 9.1. Quyền tùy chọn và cấp quyền đúng lúc

Nếu extension chỉ cần truy cập một trang sau khi người dùng bấm nút, cân nhắc `activeTab` hoặc optional host permission. Khi yêu cầu quyền mới, giải thích host/API nào sẽ được truy cập và tính năng nào cần quyền đó.

Service worker vẫn phải xác minh `sender.id`, URL, tab/frame và message schema. Có host permission không có nghĩa mọi message từ content script đều được phép gọi mọi API extension.

## 10. Backend roles, OAuth scopes và service permissions

Permission review của browser security cũng cần đối chiếu quyền backend vì browser thường giữ cookie hoặc token đại diện cho principal.

Rà soát:

- Role có đúng chức năng công việc và tenant không?
- Scope OAuth có tối thiểu theo API/resource cần dùng không?
- Access token có audience đúng resource server không?
- Refresh token có rotation, expiry và revoke path phù hợp không?
- API có kiểm tra object-level authorization thay vì chỉ kiểm tra role chung không?
- Service account và API key có owner, expiry và phạm vi mạng/resource rõ không?
- Khi người dùng bị xóa, chuyển nhóm hoặc đổi tenant, quyền cũ có bị thu hồi không?

Ví dụ, quyền browser cho phép trang đọc clipboard không đồng nghĩa user có quyền export toàn bộ hồ sơ. Endpoint export cần kiểm tra role, scope, tenant và quyền trên từng resource. Không tin các giá trị `userId`, `tenantId`, role hoặc scope do JavaScript gửi trong body.

## 11. Thu hồi quyền và xử lý khi người dùng từ chối

Ứng dụng không thể tự ý vượt qua lựa chọn của người dùng trong browser. Một số browser có giao diện site settings để người dùng thay đổi quyền; quyền OS có thể được quản lý riêng. Không phải API nào cũng có phương thức JavaScript để thu hồi grant.

Khi quyền bị từ chối:

- Dừng thao tác cần capability đó.
- Giải thích tính năng nào bị ảnh hưởng và cung cấp fallback.
- Không lặp prompt liên tục hoặc chuyển sang API khác để né quyết định.
- Cho phép người dùng tiếp tục các tính năng không cần quyền.
- Chỉ hướng dẫn mở site settings khi người dùng muốn bật lại.

Khi người dùng tắt tính năng hoặc logout:

- Dừng media stream bằng `track.stop()`.
- Dừng geolocation watch bằng `clearWatch()`.
- Hủy Push subscription nếu người dùng tắt push theo thiết kế.
- Dọn state và dữ liệu đã lưu theo retention policy.
- Thu hồi session/token phía server khi logout hoặc access bị thu hồi.
- Xóa extension permission qua browser UI hoặc cơ chế quản trị phù hợp nếu quyền thuộc extension.

Không dùng `navigator.permissions.revoke()` như giải pháp phổ quát; hỗ trợ API này đã thay đổi và không có mặt đồng nhất trên browser hiện đại. Với nhiều permission, người dùng phải thu hồi qua giao diện cài đặt browser/OS. Ứng dụng cần phát hiện trạng thái thay đổi và xử lý an toàn.

## 12. Permission review theo vòng đời vận hành

Rà soát quyền nên diễn ra định kỳ và khi có thay đổi làm thay đổi bề mặt tấn công.

Các thời điểm cần review:

- Trước release có thêm browser API, iframe, extension permission hoặc third-party integration.
- Khi thêm origin, subdomain, CDN, analytics SDK hoặc vendor script.
- Khi thay đổi role, OAuth scope, service account hoặc API authorization.
- Khi thay đổi luồng login, SSO, cookie, token hoặc session.
- Khi browser thay đổi privacy policy hoặc ngừng hỗ trợ một API.
- Khi có incident, XSS, dependency compromise hoặc nghi ngờ lạm dụng quyền.
- Khi nhân sự, vendor, tenant hoặc service owner thay đổi.
- Theo chu kỳ review định kỳ được tổ chức quy định.

### 12.1. Quy trình review

1. **Thu thập:** lấy permission inventory từ manifest, code, response header, IAM, OAuth provider và cấu hình triển khai.
2. **Đối chiếu:** so sánh quyền đã khai báo với API/feature thực sự sử dụng và telemetry.
3. **Đánh giá:** xác định phạm vi, dữ liệu, thời gian tồn tại, khả năng lạm dụng và tác động nếu bị chiếm.
4. **Xác nhận owner:** yêu cầu nhóm sở hữu giải thích lý do nghiệp vụ và người phê duyệt.
5. **Thu hẹp:** bỏ quyền thừa, giới hạn origin, frame, scope, role, method hoặc thời gian.
6. **Kiểm thử:** xác minh quyền hợp lệ vẫn hoạt động và hành vi ngoài phạm vi bị từ chối.
7. **Triển khai:** thay đổi theo release/configuration process có kiểm soát.
8. **Giám sát:** theo dõi lỗi, quyền mới phát sinh, request bị từ chối và hành vi bất thường.
9. **Ghi nhận:** lưu kết quả, exception, owner và ngày review tiếp theo.

Không xóa quyền chỉ dựa trên việc không thấy request trong một khoảng thời gian ngắn. Hãy kiểm tra luồng hiếm, fallback, feature flag và yêu cầu pháp lý/nghiệp vụ trước khi thu hồi.

### 12.2. Xử lý exception

Một quyền rộng đôi khi cần thiết cho một tính năng đặc thù. Exception cần có:

- Lý do cụ thể và phạm vi chính xác.
- Người phê duyệt và owner chịu trách nhiệm.
- Biện pháp bù trừ.
- Thời hạn hoặc ngày xem xét lại.
- Điều kiện thu hồi khi feature/vendor không còn dùng.
- Test chứng minh quyền chỉ được dùng trong ngữ cảnh được duyệt.

Không để exception trở thành quyền vĩnh viễn không có owner.

## 13. Logging, monitoring và phát hiện lạm dụng

Ứng dụng nên ghi nhận sự kiện liên quan đến quyền ở mức tối thiểu cần thiết:

- Feature bắt đầu yêu cầu permission và kết quả grant/deny nếu browser/API cung cấp.
- Người dùng bật/tắt tính năng có dùng camera, microphone, location hoặc notifications.
- Backend authorization denied, scope mismatch hoặc tenant boundary violation.
- Extension permission thay đổi hoặc host mới được thêm qua release.
- CSP/Permissions Policy violation nếu có cơ chế report phù hợp.
- Push subscription tạo, rotate, hủy hoặc lỗi.
- Quyền service account/API key được cấp, thay đổi hoặc thu hồi.

Không ghi tọa độ chính xác, nội dung clipboard, audio/video, token, cookie hoặc payload nhạy cảm chỉ để chứng minh permission được dùng. Thường chỉ cần event code, permission name, origin đã chuẩn hóa, feature, kết quả và correlation ID.

### 13.1. Chỉ số vận hành

Có thể theo dõi:

- Tỷ lệ grant/deny theo feature và browser family ở mức tổng hợp.
- Số permission được yêu cầu nhưng feature không sử dụng sau khi được cấp.
- Số iframe hoặc host mới xuất hiện trong inventory.
- Tỷ lệ API bị từ chối do authorization/scope mismatch.
- Số extension permission thay đổi theo release.
- Số token/service account quá hạn hoặc chưa có owner.
- Thời gian từ khi yêu cầu thu hồi đến khi xác minh đã thu hồi.

Không dùng tỷ lệ grant/deny để gây áp lực người dùng hoặc tự động yêu cầu lại quyền. Dữ liệu permission có thể tiết lộ đặc điểm thiết bị và hành vi; áp dụng aggregation, access control và retention phù hợp.

## 14. Kiểm thử permission review

Kiểm thử cần bao gồm cả trạng thái cho phép, từ chối, không hỗ trợ và thay đổi giữa chừng.

| Kịch bản | Cách kiểm tra | Kết quả mong đợi |
| --- | --- | --- |
| Permission chưa được hỏi | Mở feature lần đầu, chưa có grant. | App giải thích nhu cầu và chỉ gọi API sau thao tác người dùng phù hợp. |
| Permission được cấp | Cấp quyền trong browser test context hoặc site settings. | Feature hoạt động đúng và chỉ dùng capability trong thời gian cần. |
| Permission bị từ chối | Từ chối trong browser hoặc dùng fixture trạng thái denied. | App hiển thị fallback, không lặp prompt hoặc crash. |
| Permission bị thu hồi | Thu hồi từ site settings trong khi app đang mở. | App nhận biết lỗi/thay đổi, dừng feature và cập nhật UI. |
| API không hỗ trợ | Chạy trên browser không có API/descriptor. | App fallback an toàn; không coi unsupported là granted. |
| OS/device từ chối | Browser báo lỗi khi thiết bị không sẵn sàng. | App xử lý lỗi riêng với permission denied. |
| Iframe không được ủy quyền | Nhúng widget dưới policy chặn camera/geolocation. | Feature bị chặn trong frame dù người dùng có thể đã cấp quyền ở nơi khác. |
| Iframe được ủy quyền | Header và `allow` giới hạn đúng origin. | Chỉ frame được chỉ định có thể yêu cầu feature theo browser policy. |
| Extension host scope | Mở trang trong và ngoài match pattern. | Content script chỉ chạy ở host được cấp. |
| Backend role | User thiếu role gọi endpoint trực tiếp. | Server từ chối dù browser UI có hiển thị nút hoặc cookie hợp lệ. |
| OAuth scope | Token thiếu scope gọi API cần scope đó. | Resource server trả lỗi authorization; không dựa vào CORS. |
| Logout/revoke | Logout rồi gọi lại API bằng session cũ. | Server từ chối; browser state và feature stream được dọn. |

### 14.1. Kiểm tra browser permission bằng Playwright

Playwright có thể cấp một số quyền cho browser context để test nhánh được phép. Danh sách permission được hỗ trợ tùy browser engine.

```ts
import { test, expect } from "@playwright/test";

test("location feature works when geolocation is granted", async ({ browser }) => {
  const context = await browser.newContext({
    permissions: ["geolocation"],
    geolocation: { latitude: 10.7769, longitude: 106.7009 }
  });

  const page = await context.newPage();
  await page.goto("https://app.example.test/location");
  await page.getByRole("button", { name: "Use my location" }).click();

  await expect(page.getByTestId("location-status")).toHaveText("Location available");
  await context.close();
});
```

Đây là fixture tọa độ giả lập. Không dùng vị trí thật của người kiểm thử. Test này xác minh nhánh grant; không chứng minh prompt UI hoặc hành vi từ chối. Dùng unit test cho nhánh permission denied, và manual/cross-browser test khi cần xác minh prompt hoặc site settings thực tế.

### 14.2. Kiểm tra Permissions Policy

Tạo một fixture iframe có API feature cần kiểm tra. Cấu hình response header của parent để chặn feature, sau đó xác minh frame không thể sử dụng API. Chạy test tương ứng trên browser hỗ trợ feature đó.

Ví dụ cấu hình server test:

```http
Permissions-Policy: geolocation=()
```

Với iframe được phép, cấu hình allowlist cho origin cụ thể và thuộc tính `allow` phù hợp. Test âm tính phải xác nhận frame ngoài allowlist vẫn bị chặn. Không chỉ assert header string; kiểm tra kết quả API và trạng thái UI.

### 14.3. Kiểm tra backend authorization

Gọi API trực tiếp bằng test client với:

- User không có role.
- Token thiếu scope.
- User thuộc tenant khác.
- Session đã revoke.
- Resource ID hợp lệ nhưng không thuộc principal.

Kết quả phải bị từ chối ở server. Đây là integration/API test; browser permission không thay thế được các kiểm tra này.

## 15. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Yêu cầu mọi permission khi tải trang | Người dùng bị hỏi trước khi hiểu nhu cầu và dễ từ chối. | Yêu cầu theo thao tác rõ ràng, đúng feature. |
| Nghĩ `granted` bảo đảm API luôn hoạt động | OS, thiết bị, policy hoặc trạng thái runtime vẫn có thể chặn. | Xử lý lỗi API thực tế và thiết bị unavailable. |
| Nghĩ CORS là authorization | Origin được đọc response có thể bị cấp quá rộng; API vẫn cần authz. | Kiểm tra identity, role, scope và resource ở server. |
| Nghĩ `Permissions-Policy` cấp quyền người dùng | Header chỉ giới hạn feature, không thay browser prompt. | Kiểm tra cả policy, user grant và API result. |
| Ủy quyền mọi feature cho mọi iframe | Third-party frame có thể truy cập capability không cần thiết. | Allowlist frame origin và feature tối thiểu. |
| Không dừng media/geolocation khi kết thúc | Thiết bị tiếp tục hoạt động hoặc vị trí tiếp tục được lấy. | Gọi `track.stop()` và `clearWatch()` khi kết thúc. |
| Không xử lý permission revoke | UI vẫn giả định feature đang hoạt động. | Theo dõi thay đổi khi hỗ trợ và xử lý lỗi runtime. |
| Coi `HttpOnly` là quyền truy cập API | Script vẫn có thể gửi request bằng cookie. | Bảo vệ CSRF, authorization và XSS riêng. |
| Cấp host permission extension quá rộng | Extension có thể đọc hoặc thao tác trên nhiều website ngoài nhu cầu. | Dùng host hẹp, optional permission hoặc `activeTab`. |
| Không review OAuth/service scopes | Service hoặc client giữ quyền lâu dài vượt nhu cầu. | Inventory owner, scope tối thiểu, expiry và revoke. |
| Không có fallback khi user từ chối | Tính năng lỗi hoặc ứng dụng ép người dùng cấp quyền. | Thiết kế trải nghiệm degraded mode và nhập liệu thủ công khi phù hợp. |
| Log dữ liệu thu được từ permission | Lộ vị trí, clipboard, media hoặc định danh nhạy cảm. | Log event metadata tối thiểu, không log payload. |

## 16. Checklist permission review định kỳ

### Browser API và user grant

- [ ] Mỗi browser permission có feature owner và lý do nghiệp vụ.
- [ ] Permission chỉ được yêu cầu khi người dùng kích hoạt tính năng cần nó.
- [ ] Ứng dụng xử lý `granted`, `prompt`, `denied` và `unsupported`.
- [ ] Có fallback khi người dùng từ chối hoặc thu hồi quyền.
- [ ] Camera/microphone stream và geolocation watch được dừng đúng lúc.
- [ ] Không lưu/truyền dữ liệu thu được ngoài mục đích đã xác định.

### Document, iframe và extension

- [ ] `Permissions-Policy` được cấu hình theo feature cần dùng.
- [ ] Iframe chỉ nhận feature được ủy quyền và có origin allowlist rõ.
- [ ] Iframe không tin cậy có sandbox phù hợp.
- [ ] Extension `permissions`, `host_permissions` và `matches` ở mức tối thiểu.
- [ ] Optional permission/`activeTab` được dùng khi phù hợp.
- [ ] Message handler kiểm tra sender, frame, schema và action.

### Backend và credential

- [ ] Role, OAuth scope, audience và tenant permission có owner.
- [ ] API kiểm tra authorization ở server cho từng resource/action.
- [ ] Cookie có thuộc tính phù hợp và session có revoke path.
- [ ] CORS không cấp origin rộng hơn nhu cầu và không được coi là authorization.
- [ ] Token/service account/API key có expiry, rotation và quy trình thu hồi.

### Vận hành và bằng chứng

- [ ] Inventory có ngày review, owner và evidence.
- [ ] Quyền mới được rà soát trước release hoặc tích hợp vendor.
- [ ] Exception có approver, lý do, biện pháp bù trừ và ngày hết hạn/review.
- [ ] Monitoring không ghi token, cookie, tọa độ, clipboard hoặc media payload.
- [ ] Test grant, deny, revoke, unsupported và cross-browser đã chạy.
- [ ] Có xác minh sau khi thu hồi quyền và cleanup dữ liệu liên quan.

## 17. Bài thực hành

Thực hiện permission review cho một staging app có tính năng bản đồ, cuộc gọi video, notification, iframe bản đồ bên thứ ba và một extension hỗ trợ portal. Dùng account và dữ liệu giả.

1. Lập inventory quyền browser, iframe, extension, cookie và backend role/scope.
2. Xác định feature owner, origin, scope, lifetime và lý do cho từng quyền.
3. Kiểm tra ứng dụng chỉ yêu cầu geolocation khi người dùng bấm “Dùng vị trí của tôi”.
4. Kiểm tra camera/microphone chỉ bật khi cuộc gọi bắt đầu và track được dừng khi kết thúc.
5. Cấu hình `Permissions-Policy` để chặn feature không cần và chỉ ủy quyền geolocation cho iframe bản đồ được duyệt.
6. Thử permission denied, unsupported và revoke; xác nhận ứng dụng có fallback.
7. Rà soát extension manifest, thu hẹp host permission và kiểm tra message handler.
8. Gọi API bằng user thiếu role hoặc token thiếu scope; xác nhận server từ chối.
9. Kiểm tra cookie, CORS và CSP để bảo đảm không dùng chúng thay cho authorization.
10. Kiểm tra log/telemetry không chứa tọa độ, clipboard, media payload, token hoặc cookie.
11. Ghi nhận quyền thừa, đề xuất thu hẹp, owner, approver và ngày review tiếp theo.
12. Chạy regression test cho grant, deny, revoke và các browser mục tiêu.

Hoàn thành bài thực hành khi mọi quyền đều có mục đích, owner, phạm vi và cách thu hồi; browser chỉ cấp capability cho document/frame cần thiết; backend vẫn kiểm tra authorization độc lập; và ứng dụng xử lý an toàn khi người dùng từ chối hoặc thu hồi quyền.
