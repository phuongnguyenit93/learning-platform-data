# Permission test: kiểm thử quyền truy cập các tính năng nhạy cảm của trình duyệt

> **Chương:** Kiểm thử nâng cao  
> **Học phần:** SECURITY_APPLICATION_SECURITY_BROWSER_SECURITY — phân tích ranh giới bảo mật giữa trình duyệt, origin, cookie và ứng dụng web để hiểu Same-Origin Policy, CORS và các cơ chế cách ly; thực hành phòng vệ XSS, CSRF, clickjacking bằng CSP, Trusted Types, security headers và kiểm chứng hành vi thực tế.

**Permission test** là kiểm thử cách ứng dụng yêu cầu, sử dụng, phản ứng với việc từ chối và xử lý thay đổi quyền của các tính năng trình duyệt. Những tính năng thường cần kiểm thử gồm geolocation, camera, microphone, notifications, clipboard, fullscreen, screen capture, Bluetooth, USB và các API truy cập thiết bị khác.

Một permission test đầy đủ phải phân biệt ít nhất bốn lớp: API có tồn tại trong browser hay không; origin có được phép dùng feature theo Permissions Policy hay không; browser đã cấp quyền cho origin chưa; và hệ điều hành/thiết bị có cho phép thao tác hay không. Trạng thái permission là một phần của quyết định, không phải bằng chứng rằng API chắc chắn sẽ thành công.

Bài này xây dựng quy trình kiểm thử theo trạng thái và ngữ cảnh, dùng Permissions API để quan sát khi được hỗ trợ, gọi API thật để xác minh hành vi, kiểm tra user activation, secure context, iframe delegation và quyền hệ điều hành. Phần automation sử dụng Playwright để cấp quyền trong browser context và CDP cho một số ca Chromium-specific; phần manual test giúp xác nhận prompt thật, thu hồi quyền và hành vi trên browser/mobile mà automation không mô phỏng đầy đủ.

## Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt API availability, Permissions API state, Permissions Policy, browser grant và OS/device permission.
2. Giải thích ba trạng thái phổ biến granted, denied và prompt.
3. Dùng navigator.permissions.query() mà không nhầm nó với thao tác xin quyền.
4. Kiểm thử API thật thay vì chỉ kiểm tra permission state.
5. Phân loại lỗi NotAllowedError, SecurityError, NotFoundError, NotReadableError, AbortError và lỗi riêng của từng API.
6. Kiểm thử secure context, user activation và trạng thái focus khi API yêu cầu.
7. Kiểm tra quyền trong top-level document, same-origin iframe và cross-origin iframe.
8. Đánh giá tác động của Permissions-Policy header và iframe allow attribute.
9. Kiểm thử vòng đời quyền: prompt, grant, deny, reload, revoke và đổi browser profile.
10. Thiết kế test matrix cho browser desktop, mobile và WebView.
11. Tự động hóa các ca ổn định bằng Playwright và nhận diện giới hạn browser-specific.
12. Bảo đảm ứng dụng xin quyền đúng thời điểm, dùng đúng phạm vi và có fallback an toàn.

## 1. Mô hình quyền của browser

### 1.1 Permission không phải một boolean duy nhất

Một API chỉ hoạt động khi nhiều điều kiện cùng thỏa mãn:

~~~text
Ứng dụng muốn gọi một browser API
              |
              v
API có được runtime hỗ trợ?
              |
              v
Document có secure context?
              |
              v
Permissions Policy có cho feature ở origin/frame này?
              |
              v
Browser permission state là gì?
   +----------+-----------+
   |          |           |
 granted    prompt      denied
   |          |           |
   |          v           v
   |      User decision   API bị từ chối
   |          |
   +----------+
              |
              v
User activation / focus / API-specific preconditions?
              |
              v
OS permission và thiết bị có sẵn?
              |
              v
API thực thi hoặc trả lỗi
~~~

Ví dụ, browser permission của camera có thể là granted nhưng API vẫn thất bại vì hệ điều hành chưa cấp quyền camera cho browser, camera đang bị ứng dụng khác sử dụng hoặc thiết bị không tồn tại. Ngược lại, API có thể không xuất hiện vì browser không hỗ trợ dù permission state không phải denied.

### 1.2 Bốn lớp cần tách riêng

| Lớp | Câu hỏi kiểm thử | Ví dụ |
|---|---|---|
| API capability | Runtime có expose API không? | navigator.mediaDevices.getUserMedia tồn tại |
| Permissions Policy | Document/frame có được dùng feature không? | camera bị chặn bởi response header |
| Browser permission | Người dùng đã cho origin quyền chưa? | camera permission là granted/denied/prompt |
| OS và thiết bị | Browser/OS có truy cập được thiết bị không? | OS chặn camera hoặc không có microphone |

CORS là một cơ chế khác. CORS quyết định script có được đọc response cross-origin; nó không cấp camera, geolocation hay clipboard permission.

### 1.3 Quyền thường gắn với origin và browser profile

Browser thường lưu quyết định permission theo origin và profile; với một số ngữ cảnh nhúng, khóa permission còn xét top-level origin cùng origin của frame. Origin gồm scheme, host và port. Các địa chỉ sau là những origin khác nhau:

- http://localhost:3000
- http://localhost:3001
- https://app.example.com
- http://app.example.com

Không suy ra quyền từ hostname đơn lẻ. Quyền ở profile thường không tự chuyển sang profile khác, cửa sổ riêng tư, browser khác hoặc WebView. Chính sách doanh nghiệp và cài đặt người dùng cũng có thể thay đổi hành vi.

### 1.4 Grant không đồng nghĩa authorization

Permission camera cho phép trang yêu cầu dùng camera theo chính sách browser. Nó không chứng minh người dùng có quyền truy cập tài khoản, hồ sơ hoặc tài nguyên của ứng dụng.

Server vẫn phải xác thực và phân quyền từng thao tác. Không dùng browser permission state làm căn cứ cho quyền nghiệp vụ phía server.

## 2. Permissions API và ba trạng thái

### 2.1 query() chỉ đọc trạng thái

Permissions API cung cấp cách hỏi trạng thái một permission descriptor:

~~~js
async function readPermission(name) {
  if (!navigator.permissions?.query) {
    return { supported: false, reason: "Permissions API unavailable" };
  }

  try {
    const status = await navigator.permissions.query({ name });

    return {
      supported: true,
      state: status.state
    };
  } catch (error) {
    return {
      supported: false,
      reason: error.name
    };
  }
}

readPermission("geolocation").then(console.log);
~~~

query() không hiển thị prompt và không cấp quyền. Một số browser chỉ hỗ trợ một tập descriptor nhất định; descriptor lạ hoặc chưa được triển khai có thể làm query reject. Hãy xử lý lỗi thay vì coi việc query thất bại là trạng thái denied.

### 2.2 granted, denied và prompt

| State | Ý nghĩa | Hành vi cần kiểm thử |
|---|---|---|
| granted | Browser cho phép feature theo permission state hiện tại | Gọi API thật và kiểm tra điều kiện thiết bị/OS |
| denied | Browser báo feature bị từ chối trong context hiện tại | UI giải thích cách thay đổi quyền; API không được giả định thành công |
| prompt | Browser có thể hỏi người dùng khi API được gọi | Chỉ yêu cầu ở thời điểm phù hợp, thường sau hành động rõ ràng |

prompt không bảo đảm browser sẽ hiển thị hộp thoại. Prompt có thể bị chặn bởi Permissions Policy, user activation, cài đặt browser, quyền đã bị từ chối trước đó hoặc quy tắc riêng của API.

### 2.3 PermissionStatus và onchange

PermissionStatus có state và event change. Ứng dụng có thể cập nhật UI khi browser thông báo trạng thái thay đổi:

~~~js
async function watchPermission(name, onChange) {
  if (!navigator.permissions?.query) return null;

  try {
    const status = await navigator.permissions.query({ name });

    onChange(status.state);

    status.addEventListener("change", () => {
      onChange(status.state);
    });

    return status;
  } catch {
    return null;
  }
}

watchPermission("geolocation", state => {
  console.log("Geolocation permission:", state);
});
~~~

Không giả định mọi browser phát change giống nhau hoặc ngay khi người dùng thay đổi setting ở mọi bối cảnh. Với test quan trọng, hãy quay lại trang, query lại state và gọi API thật.

### 2.4 Descriptor support không đồng đều

Các descriptor thường gặp gồm geolocation, notifications, camera, microphone, clipboard-read và clipboard-write. Mức hỗ trợ Permissions API thay đổi theo browser và phiên bản; có API không có descriptor tương ứng được triển khai đồng đều.

Hãy tách hai bài test:

1. Browser có hỗ trợ query descriptor hay không?
2. Browser có thực thi API và áp dụng quyền đúng hay không?

Nếu query camera bị từ chối vì descriptor không được hỗ trợ, không kết luận camera API bị chặn. Kiểm tra navigator.mediaDevices và gọi getUserMedia trong một test có tương tác người dùng.

### 2.5 Notification có giao diện riêng

Notification API cung cấp Notification.permission với các giá trị granted, denied hoặc default. default thường có nghĩa là người dùng chưa đưa ra quyết định và ứng dụng chưa có quyền hiển thị notification.

Notifications là một permission mạnh nhưng không phải policy-controlled feature của Permissions Policy. Vì vậy, không thêm directive notifications vào header Permissions-Policy; hãy kiểm tra Notification.permission và requestPermission() theo quy tắc riêng của API. Đây là ví dụ cho thấy một permission có thể thuộc Permissions API mà không có directive Permissions Policy tương ứng.

~~~js
async function requestNotificationsFromClick() {
  if (!("Notification" in window)) {
    return "unsupported";
  }

  if (Notification.permission === "granted") {
    return "granted";
  }

  if (Notification.permission === "denied") {
    return "denied";
  }

  const result = await Notification.requestPermission();
  return result;
}
~~~

Gọi requestPermission() sau một thao tác người dùng rõ ràng. Browser có thể hạn chế prompt nếu ứng dụng hỏi ngay khi tải trang hoặc lặp lại nhiều lần.

## 3. Chuẩn bị test environment

### 3.1 Dùng HTTPS hoặc localhost

Các API nhạy cảm thường yêu cầu secure context. Production nên dùng HTTPS. Browser coi localhost và một số loopback address là potentially trustworthy cho phát triển, nhưng môi trường test vẫn phải dùng đúng host và scheme.

~~~js
console.log({
  secureContext: window.isSecureContext,
  origin: window.location.origin,
  serviceWorker: "serviceWorker" in navigator,
  geolocation: "geolocation" in navigator,
  mediaDevices: Boolean(navigator.mediaDevices)
});
~~~

Không dùng địa chỉ LAN HTTP rồi giả định hành vi giống localhost. Một trang http://192.168.x.x có thể không phải secure context.

### 3.2 Tạo profile sạch

Permission state có thể tồn tại giữa các lần tải trang. Để test prompt ban đầu:

- Dùng browser profile mới hoặc automation context mới.
- Xóa permission của origin trong Site settings.
- Xóa các policy doanh nghiệp nếu môi trường cho phép.
- Kiểm tra browser không chạy trong chế độ private có chính sách khác.
- Ghi lại phiên bản browser và hệ điều hành.

Không dùng một profile đã cấp camera từ trước để kiểm thử lần đầu xin quyền.

### 3.3 Ghi nhận môi trường

Mỗi test run nên ghi:

- Browser family và version.
- Engine/version nếu biết.
- OS và version.
- Origin, scheme và port.
- Top-level page hay iframe.
- API/feature được kiểm thử.
- Permission state ban đầu.
- Permissions Policy header và iframe allow.
- Thiết bị thật hay thiết bị giả lập.
- User activation có được tạo bằng thao tác thật hay không.

### 3.4 Không dùng dữ liệu thiết bị thật trong test không cần thiết

Với geolocation, dùng tọa độ giả lập. Với camera/microphone, ưu tiên fake device trong automation. Nếu phải kiểm tra thiết bị thật, không lưu video, âm thanh hoặc tọa độ; chỉ ghi nhận pass/fail và lỗi đã chuẩn hóa.

## 4. Kiểm thử permission theo vòng đời

### 4.1 State transition matrix

| Bước | State trước | Thao tác | Kết quả cần quan sát |
|---|---|---|---|
| P01 | Chưa có quyết định | Mở trang | UI không tự xin quyền nếu chưa cần |
| P02 | prompt/default | Người dùng bấm nút feature | Browser có thể hiển thị prompt |
| P03 | prompt | Người dùng Allow | State có thể chuyển granted; API được thử lại |
| P04 | prompt | Người dùng Block | State chuyển denied; UI có hướng dẫn |
| P05 | granted | Reload | Kiểm tra quyền có còn theo profile/origin |
| P06 | granted | Revoke trong Site settings | State/API phản ánh thay đổi sau khi browser cập nhật |
| P07 | denied | Reload | Không lặp prompt liên tục |
| P08 | denied | Người dùng đổi setting sang Allow | UI cập nhật khi quay lại hoặc query lại |
| P09 | granted | Đóng tab/mở tab mới cùng profile | Kiểm tra persistence theo browser |
| P10 | granted | Dùng profile riêng tư hoặc profile khác | Không giả định quyền được chia sẻ |
| P11 | granted | Đổi origin scheme/port | Quyền không được suy rộng sang origin mới |
| P12 | granted | OS thu hồi quyền thiết bị | API có thể thất bại dù browser state vẫn báo granted |

### 4.2 Test prompt đúng thời điểm

Ứng dụng nên giải thích lý do trước khi yêu cầu permission và gọi API sau thao tác rõ ràng. Test các trường hợp:

- Không có prompt khi trang vừa tải.
- Prompt chỉ xuất hiện sau nút có nhãn mô tả feature.
- Người dùng có thể hủy hoặc bỏ qua prompt.
- Người dùng từ chối không bị lặp prompt liên tục.
- Có hướng dẫn mở Site settings khi state denied.
- Ứng dụng vẫn hoạt động ở chế độ không có feature.

Không tạo giao diện giả giống browser permission prompt. Điều đó dễ gây nhầm lẫn và làm người dùng cấp quyền ngoài ý muốn.

### 4.3 Test grant và gọi API thật

Permission state granted không đủ. Gọi API thật với thiết bị và điều kiện phù hợp. Ví dụ geolocation:

~~~js
function testGeolocation() {
  return new Promise((resolve, reject) => {
    if (!navigator.geolocation) {
      reject(new Error("Geolocation API unavailable"));
      return;
    }

    navigator.geolocation.getCurrentPosition(
      () => resolve({ result: "success" }),
      error => reject(error),
      {
        enableHighAccuracy: false,
        timeout: 5000,
        maximumAge: 0
      }
    );
  });
}
~~~

Trong test bảo mật, không cần lưu latitude/longitude. Chỉ xác nhận API thành công hoặc ghi loại lỗi.

### 4.4 Test deny và fallback

Khi người dùng từ chối, ứng dụng phải:

- Không crash hoặc tạo unhandled rejection.
- Không tiếp tục gọi API theo vòng lặp.
- Không giả vờ rằng feature đã hoạt động.
- Hiển thị trạng thái rõ ràng và hướng dẫn phù hợp.
- Cho phép dùng chức năng thay thế nếu có.
- Không ép người dùng bật quyền để tiếp tục một tác vụ không cần feature đó.

### 4.5 Test revoke trong lúc trang đang mở

Thu hồi quyền có thể xảy ra từ browser settings hoặc OS settings. Tùy API và browser, trang có thể nhận PermissionStatus change, API call kế tiếp thất bại hoặc stream hiện tại bị dừng.

Test riêng:

- Thu hồi khi trang đang idle.
- Thu hồi khi stream camera/microphone đang mở.
- Thu hồi khi geolocation watch đang chạy.
- Thu hồi rồi gọi API lần nữa.
- Quay lại tab sau khi thay đổi setting.
- Kiểm tra cleanup: stop MediaStream tracks, clear watch và cập nhật UI.

Không giả định mọi API phát event giống nhau khi permission bị thu hồi.

## 5. Kiểm thử theo từng browser API

### 5.1 Geolocation

API: navigator.geolocation.getCurrentPosition() và watchPosition().

Test:

- API tồn tại và secure context.
- prompt/granted/denied.
- User Allow, Block, dismiss và timeout.
- Position unavailable và timeout.
- watchPosition được clear khi component unmount hoặc user tắt feature.
- Permission bị thu hồi trong lúc watch đang chạy.
- iframe cross-origin có được delegate hay không.
- Không log tọa độ thật.

Geolocation error có code riêng:

| Code | Hằng số | Ý nghĩa |
|---|---|---|
| 1 | PERMISSION_DENIED | Browser từ chối quyền hoặc policy ngăn truy cập |
| 2 | POSITION_UNAVAILABLE | Không xác định được vị trí |
| 3 | TIMEOUT | Không có kết quả trong thời hạn yêu cầu |

PERMISSION_DENIED không luôn chứng minh người dùng bấm Block; Permissions Policy hoặc browser setting cũng có thể ngăn truy cập.

### 5.2 Camera và microphone

API: navigator.mediaDevices.getUserMedia().

~~~js
async function testCamera() {
  if (!navigator.mediaDevices?.getUserMedia) {
    throw new Error("MediaDevices API unavailable");
  }

  let stream;

  try {
    stream = await navigator.mediaDevices.getUserMedia({
      audio: false,
      video: true
    });

    return { result: "success", tracks: stream.getVideoTracks().length };
  } finally {
    stream?.getTracks().forEach(track => track.stop());
  }
}
~~~

Test:

- Camera và microphone được yêu cầu riêng theo nhu cầu.
- Deny camera không tự động làm ứng dụng xin microphone.
- User có thể chọn thiết bị nếu có nhiều thiết bị.
- Không có thiết bị trả NotFoundError.
- Thiết bị bận hoặc OS chặn có thể trả NotReadableError.
- Constraint không thỏa mãn có thể trả OverconstrainedError.
- User từ chối hoặc policy chặn có thể trả NotAllowedError.
- Stop tất cả track sau test để đèn camera tắt.
- Không lưu stream hoặc ghi âm ngoài mục đích test.

Không dùng getUserMedia khi page load. Hãy gọi từ thao tác rõ ràng của người dùng và giải thích lý do.

### 5.3 Notifications

Test:

- Notification API có tồn tại.
- Notification.permission ban đầu.
- requestPermission chỉ chạy sau thao tác người dùng.
- Allow, deny và default.
- Browser chặn prompt hoặc yêu cầu cài đặt PWA trên một số nền tảng.
- Không gửi notification có nội dung nhạy cảm trên màn hình khóa.
- Service Worker notification và Push permission được kiểm thử riêng.

Permission notifications không chứng minh Push API hoặc service worker đã sẵn sàng.

### 5.4 Clipboard

Các API: navigator.clipboard.readText(), writeText(), read() và write().

Test:

- Secure context.
- User activation/focus nếu browser yêu cầu.
- Permission descriptor clipboard-read/clipboard-write nếu query được hỗ trợ.
- Đọc và ghi với thao tác người dùng rõ ràng.
- Browser có thể cho write nhưng hạn chế read.
- Paste event từ người dùng khác với gọi clipboard.readText().
- Permission state không bảo đảm mọi thao tác clipboard đều thành công.

Không đọc clipboard tự động khi trang tải hoặc gửi nội dung clipboard lên server để debug.

### 5.5 Fullscreen

API: Element.requestFullscreen() và document.exitFullscreen().

Test:

- API tồn tại.
- requestFullscreen được gọi sau transient user activation.
- Document không bị Permissions Policy chặn.
- iframe cần allow="fullscreen" khi thích hợp.
- Escape, chuyển tab và navigation thoát fullscreen.
- fullscreenchange event cập nhật UI.
- Không coi fullscreen là permission prompt thông thường; user activation và policy là điều kiện quan trọng.

### 5.6 Screen capture

API: navigator.mediaDevices.getDisplayMedia().

Test:

- API và secure context.
- Gọi sau user activation.
- Browser hiển thị chooser chọn màn hình/window/tab.
- User cancel chooser.
- Track kết thúc khi user bấm Stop sharing.
- Lắng nghe track ended và cập nhật UI.
- Không lưu hoặc truyền screen capture nếu chưa có mục đích rõ ràng.

Không giả định Playwright grantPermissions có thể bỏ qua chooser. Screen capture thường có UI chọn nguồn riêng; automation cần cơ chế riêng theo browser và môi trường.

### 5.7 Bluetooth, USB, Serial và HID

Các API thiết bị thường yêu cầu secure context, user activation, lựa chọn thiết bị và có thể có permission lưu theo device. Chúng không nhất thiết có descriptor Permissions API tương ứng hoặc hỗ trợ đồng đều.

Test:

- Feature detection.
- Browser/OS compatibility.
- User activation trước khi mở chooser.
- Người dùng cancel chooser.
- Thiết bị không hỗ trợ hoặc disconnect.
- Origin chỉ truy cập thiết bị đã được người dùng chọn.
- Thu hồi quyền thiết bị trong site settings.
- Không enumerate hoặc truy cập thiết bị ngoài mục đích.

Không dùng automation giả lập permission chung để kết luận chooser thiết bị thật hoạt động đúng.

## 6. Permissions Policy và iframe

### 6.1 Browser permission và Permissions Policy là hai lớp khác nhau

Browser permission thể hiện quyết định của người dùng hoặc browser profile. Permissions Policy giới hạn document và frame nào được sử dụng feature.

Ví dụ response header:

~~~http
Permissions-Policy: geolocation=(self), camera=(), microphone=(), fullscreen=(self "https://video.example.net"), display-capture=(self)
~~~

Trong ví dụ:

- Geolocation được phép cho same-origin.
- Camera và microphone bị tắt cho mọi origin.
- Fullscreen được phép cho same-origin và origin video đã chỉ định.

Nếu policy chặn feature, việc người dùng đã grant browser permission không làm policy tự mở lại.

Khi Permissions Policy chặn một powerful feature, Permissions API có thể phản ánh state là denied. Vì vậy, state denied không luôn chứng minh người dùng đã bấm Block; hãy đối chiếu response header, iframe policy và browser settings. Notifications là ngoại lệ vì nó không phải policy-controlled feature.

### 6.2 iframe cần delegation phù hợp

Ví dụ parent cho phép origin widget dùng geolocation:

~~~http
Permissions-Policy: geolocation=(self "https://maps.example.net")
~~~

~~~html
<iframe
  src="https://maps.example.net/embed"
  allow="geolocation"
  title="Bản đồ">
</iframe>
~~~

Cả policy của ancestor và allow attribute của iframe phải phù hợp. Child không thể bật lại feature đã bị ancestor tắt.

### 6.3 Test ma trận frame

| Ca | Parent policy | iframe allow | Origin child | Kết quả cần xác minh |
|---|---|---|---|---|
| F01 | Cho self và child | Có feature | Cross-origin được liệt kê | API có thể tiếp tục tới bước browser permission |
| F02 | Chỉ cho self | Có feature | Cross-origin không được liệt kê | Feature vẫn bị policy giới hạn |
| F03 | Tắt feature | allow rộng | Same/cross-origin | Child không thể mở lại |
| F04 | Cho child | Thiếu allow | Cross-origin | Container policy có thể không delegate |
| F05 | Cho child | Có allow | Same-origin child | Kiểm tra inheritance và policy hiệu lực |
| F06 | Cho child | Có allow | Redirect sang origin khác | Kiểm tra origin đích và delegation |

### 6.4 Test response header, không chỉ cấu hình server

Dùng DevTools Network kiểm tra response HTML cuối cùng của parent và từng iframe. CDN, proxy hoặc middleware có thể xóa/ghi đè Permissions-Policy. Ghi nhận URL sau redirect và origin chính xác gồm scheme, host và port.

### 6.5 Sandbox và policy cùng ảnh hưởng

iframe sandbox có thể thay đổi origin thành opaque origin nếu không có allow-same-origin, đồng thời giới hạn script và navigation. Permissions Policy không thay thế sandbox, CSP frame-src hoặc frame-ancestors. Test các cơ chế riêng biệt và phối hợp theo thiết kế.

## 7. User activation, focus và điều kiện API

### 7.1 Permission grant không tạo user activation

Một số API yêu cầu transient user activation, ví dụ fullscreen, getDisplayMedia và clipboard read ở nhiều browser. Grant permission không thay thế thao tác người dùng.

~~~js
button.addEventListener("click", async () => {
  try {
    await document.documentElement.requestFullscreen();
  } catch (error) {
    showError(error.name);
  }
});
~~~

Nếu gọi requestFullscreen từ timer hoặc tự động sau page load, API có thể reject dù feature được policy cho phép.

### 7.2 Automation phải tạo input giống người dùng

Trong Playwright, dùng locator.click() để tạo thao tác tương tác:

~~~js
await page.getByRole("button", { name: "Bật fullscreen" }).click();
~~~

Không dùng page.evaluate() để gọi API cần activation rồi kết luận rằng người dùng thật cũng bị chặn. evaluate chạy script trong page nhưng không đại diện cho thao tác input tin cậy của người dùng.

### 7.3 Focus và visibility

Clipboard, notifications và một số API khác có điều kiện phụ thuộc tab đang active, document focus hoặc visibility. Test:

- Tab active và foreground.
- Tab background.
- Window mất focus.
- Document hidden.
- Browser permission granted nhưng focus không thỏa mãn.

Ghi nhận lỗi thực tế thay vì suy ra nguyên nhân chỉ từ permission state.

## 8. Phân loại lỗi khi test permission

### 8.1 DOMException phổ biến

| Error name | Nguyên nhân có thể | Cách kiểm tra tiếp |
|---|---|---|
| NotAllowedError | User deny, policy block, thiếu activation hoặc browser từ chối | Kiểm tra permission, Permissions Policy, user gesture và Console |
| SecurityError | Secure context hoặc security restriction | Kiểm tra scheme, origin và policy |
| NotFoundError | Không có thiết bị/track phù hợp | Kiểm tra thiết bị và constraints |
| NotReadableError | Thiết bị có nhưng không đọc được, có thể đang bận hoặc OS chặn | Kiểm tra OS settings, thiết bị và app khác |
| AbortError | Thao tác bị hủy hoặc không thể hoàn tất | Kiểm tra lifecycle và thiết bị |
| OverconstrainedError | Constraints không thể đáp ứng | Đọc constraint gây lỗi và nới điều kiện |
| TypeError | API/descriptor/argument không hợp lệ hoặc thiếu điều kiện | Kiểm tra feature detection và cấu trúc tham số |

Tên lỗi và thông điệp có thể khác theo API/browser. Không hiển thị nguyên message nội bộ của browser như một lời giải thích chắc chắn về nguyên nhân.

### 8.2 Phân biệt deny với không có thiết bị

Camera denied và camera không tồn tại là hai tình huống khác nhau:

- Denied: người dùng hoặc policy không cho phép truy cập.
- NotFoundError: không có thiết bị/track thỏa mãn.
- NotReadableError: thiết bị không đọc được dù có thể tồn tại.
- OverconstrainedError: yêu cầu constraint không thể đáp ứng.

UI nên đưa ra hướng dẫn phù hợp thay vì chỉ hiển thị "Không thể mở camera".

### 8.3 Không dựa vào error message để phân loại máy móc

Message text có thể thay đổi theo browser và ngôn ngữ. Dùng error.name, error.code nếu API định nghĩa, trạng thái permission khi hỗ trợ và ngữ cảnh request. Không parse chuỗi message để quyết định quyền hoặc hành động bảo mật.

## 9. Thiết kế bộ test thủ công

### 9.1 Checklist cho mỗi feature

Với mỗi feature, chạy các ca:

1. API không được hỗ trợ.
2. Secure context không thỏa mãn.
3. Permission state prompt/default.
4. User grant.
5. User deny.
6. User dismiss/cancel.
7. Permission đã grant từ trước.
8. Permission đã deny từ trước.
9. Revoke khi trang đang mở.
10. Revoke rồi reload.
11. Browser profile mới.
12. OS permission bị tắt.
13. Thiết bị không tồn tại.
14. Thiết bị bận hoặc không đọc được.
15. API gọi không có user activation.
16. Permissions Policy chặn.
17. iframe delegation hợp lệ.
18. iframe delegation thiếu hoặc origin sai.
19. Browser mobile/WebView.
20. Fallback UI và cleanup.

### 9.2 Test không cấp quyền

Một ứng dụng tốt vẫn phải có đường đi hữu ích khi người dùng từ chối. Kiểm tra:

- Người dùng có thể bỏ qua feature.
- Nội dung chính không bị khóa vô lý.
- Không liên tục hiển thị prompt.
- Có hướng dẫn bật lại quyền trong browser settings.
- Không gửi request tới API thiết bị sau khi deny.
- Không lưu dữ liệu cũ và giả vờ là dữ liệu mới.
- Không log nội dung nhạy cảm.

### 9.3 Test quyền tối thiểu

Đánh giá ứng dụng có yêu cầu quyền quá sớm hoặc quá rộng không:

- Chỉ xin camera khi người dùng bật chức năng camera.
- Chỉ xin microphone nếu tác vụ cần âm thanh.
- Không xin geolocation cho trang không dùng vị trí.
- Không yêu cầu clipboard read khi chỉ cần write.
- Không dùng camera/microphone để thay thế một chức năng có thể hoạt động bằng input thường.
- Không yêu cầu quyền cho toàn bộ widget nếu chỉ một frame cần feature.

### 9.4 Test multi-tab và account switch

Permission browser thường thuộc origin/profile chứ không thuộc tài khoản ứng dụng. Khi người dùng đăng xuất rồi đăng nhập tài khoản khác, quyền camera vẫn có thể còn granted cho cùng origin.

Test đảm bảo ứng dụng:

- Không coi permission là session authentication.
- Không giữ stream cũ sau logout.
- Stop tracks và giải phóng tài nguyên.
- Xóa dữ liệu người dùng khỏi UI.
- Không chia sẻ kết quả permission hoặc dữ liệu thiết bị giữa account.
- Không gửi dữ liệu từ session cũ sau khi đổi tài khoản.

## 10. Tự động hóa với Playwright

### 10.1 Automation phù hợp với ca nào?

Playwright hữu ích để kiểm tra:

- UI khi API permission state đã được grant.
- API geolocation với tọa độ giả lập.
- UI fallback khi permission bị đặt denied trong Chromium.
- Permission theo origin/context.
- Không có request permission khi page load.
- Cleanup stream và trạng thái giao diện.
- Regression của flow khi reload.

Automation không thay thế manual test cho prompt thật, OS permission dialog, browser chooser, thiết bị thật, profile doanh nghiệp và browser WebView. API grant của automation thay đổi theo engine/browser.

### 10.2 Cài đặt

Trong thư mục test riêng:

~~~bash
npm init -y
npm install --save-dev @playwright/test
npx playwright install chromium
~~~

Ví dụ dưới đây dùng Chromium. Nếu chạy Firefox hoặc WebKit, kiểm tra permission descriptor và khả năng giả lập trong phiên bản Playwright tương ứng.

### 10.3 Trang test tối thiểu

Trang ứng dụng cần có nút geolocation với ID geo và vùng kết quả result. Khi click, trang gọi getCurrentPosition và chỉ hiển thị thành công/lỗi, không hiển thị tọa độ:

~~~js
const result = document.querySelector("#result");

document.querySelector("#geo").addEventListener("click", () => {
  if (!navigator.geolocation) {
    result.textContent = "UNSUPPORTED";
    return;
  }

  navigator.geolocation.getCurrentPosition(
    () => {
      result.textContent = "SUCCESS";
    },
    error => {
      result.textContent = "ERROR:" + error.code;
    },
    {
      timeout: 5000,
      maximumAge: 0
    }
  );
});
~~~

### 10.4 Test grant geolocation

~~~ts
import { test, expect } from "@playwright/test";

test("geolocation succeeds when permission is granted", async ({ browser }) => {
  const origin = "http://localhost:3000";
  const context = await browser.newContext();

  await context.grantPermissions(["geolocation"], { origin });
  await context.setGeolocation({
    latitude: 21.0285,
    longitude: 105.8542
  });

  const page = await context.newPage();
  await page.goto(origin);

  await page.locator("#geo").click();
  await expect(page.locator("#result")).toHaveText("SUCCESS");

  await context.close();
});
~~~

Tọa độ là dữ liệu giả lập cho test. Ứng dụng chỉ xác nhận API thành công và không hiển thị hoặc gửi tọa độ.

### 10.5 Test denied trong Chromium bằng CDP

Playwright có API grant/clear permissions; để đặt state denied tường minh trong Chromium, có thể dùng Chrome DevTools Protocol. Đây là test Chromium-specific, không phải API portable cho mọi engine:

~~~ts
import { test, expect } from "@playwright/test";

test("geolocation is denied in Chromium", async ({ browser, browserName }) => {
  test.skip(browserName !== "chromium", "Browser.setPermission is Chromium-specific");
  const origin = "http://localhost:3000";
  const context = await browser.newContext();
  const page = await context.newPage();

  const cdp = await context.newCDPSession(page);

  await cdp.send("Browser.setPermission", {
    permission: { name: "geolocation" },
    setting: "denied",
    origin
  });

  await page.goto(origin);
  await page.locator("#geo").click();

  await expect(page.locator("#result")).toHaveText("ERROR:1");

  await context.close();
});
~~~

Nếu browser/Playwright version không hỗ trợ CDP command này, bỏ qua ca automation và thực hiện deny bằng Site settings trong manual test. Không thay nó bằng giả định rằng grantPermissions([]) luôn có nghĩa denied ở mọi browser.

### 10.6 Test permission query

~~~ts
import { test, expect } from "@playwright/test";

test("permission query is observable when descriptor is supported", async ({ page }) => {
  await page.goto("http://localhost:3000");

  const result = await page.evaluate(async () => {
    if (!navigator.permissions?.query) {
      return "api-unsupported";
    }

    try {
      const status = await navigator.permissions.query({
        name: "geolocation"
      });

      return status.state;
    } catch (error) {
      return "descriptor-unsupported:" + error.name;
    }
  });

  const normalized = result.startsWith("descriptor-unsupported:")
    ? "api-unsupported"
    : result;

  expect(["granted", "denied", "prompt", "api-unsupported"])
    .toContain(normalized);
});
~~~

Test này chỉ kiểm tra query behavior. Nó không chứng minh API geolocation sẽ thành công; cần test gọi API thật như hai ca ở trên.

### 10.7 Test không xin quyền khi page load

~~~ts
import { test, expect } from "@playwright/test";

test("page load does not invoke geolocation", async ({ page }) => {
  await page.addInitScript(() => {
    const original = navigator.geolocation.getCurrentPosition.bind(
      navigator.geolocation
    );

    let calls = 0;

    Object.defineProperty(window, "__geoCalls", {
      get: () => calls
    });

    Object.defineProperty(navigator.geolocation, "getCurrentPosition", {
      configurable: true,
      value: (...args: Parameters<Geolocation["getCurrentPosition"]>) => {
        calls += 1;
        return original(...args);
      }
    });
  });

  await page.goto("http://localhost:3000");
  await expect.poll(() => page.evaluate(
    () => (window as Window & { __geoCalls?: number }).__geoCalls
  ))
    .toBe(0);
});
~~~

Đây là kiểm tra hành vi code của ứng dụng, không phải mô phỏng prompt browser. Trong test suite TypeScript, có thể khai báo kiểu cho __geoCalls hoặc dùng fixture riêng để tránh ép kiểu không cần thiết.

### 10.8 Dọn permission giữa các test

Mỗi test nên dùng BrowserContext mới để cô lập cookie, storage và permission override. Có thể dùng:

~~~js
await context.clearPermissions();
await context.close();
~~~

clearPermissions xóa override do automation đặt; nó không xóa mọi setting OS hoặc chính sách doanh nghiệp. Đóng context sau mỗi test giúp tránh state rò sang test tiếp theo.

### 10.9 Camera và microphone với fake device

Chromium có thể chạy với fake media device để test luồng getUserMedia mà không dùng camera thật. Ví dụ cấu hình launch args:

~~~ts
import { defineConfig } from "@playwright/test";

export default defineConfig({
  use: {
    launchOptions: {
      args: [
        "--use-fake-device-for-media-stream",
        "--use-fake-ui-for-media-stream"
      ]
    }
  }
});
~~~

Cấp quyền trong context:

~~~ts
await context.grantPermissions(
  ["camera", "microphone"],
  { origin: "http://localhost:3000" }
);
~~~

Các cờ này dành cho Chromium và có thể thay đổi theo browser build. Test fake device chỉ xác nhận luồng ứng dụng; vẫn cần manual test với thiết bị thật và OS permission.

### 10.10 Automation và user activation

Dùng page.click()/locator.click() cho thao tác cần activation. Không dùng evaluate để gọi API trực tiếp rồi kết luận rằng user activation đã được mô phỏng.

Một số browser automation có thể xử lý activation khác nhau. Nếu fullscreen, clipboard hoặc display capture thất bại trong automation, đối chiếu manual test và tài liệu browser trước khi coi đó là lỗi ứng dụng.

## 11. Lab manual: kiểm tra quyền trên localhost

### 11.1 Cấu trúc thư mục

~~~text
permission-test-lab/
  server.mjs
  public/
    index.html
    app.js
~~~

### 11.2 Tạo server.mjs

~~~js
import { createServer } from "node:http";
import { readFile } from "node:fs/promises";

const root = new URL("./public/", import.meta.url);
const files = new Map([
  ["/", ["index.html", "text/html; charset=utf-8"]],
  ["/index.html", ["index.html", "text/html; charset=utf-8"]],
  ["/app.js", ["app.js", "text/javascript; charset=utf-8"]]
]);

const server = createServer(async (req, res) => {
  const url = new URL(req.url || "/", "http://localhost:3000");

  if (req.method !== "GET" && req.method !== "HEAD") {
    res.writeHead(405, { "Allow": "GET, HEAD" });
    return res.end();
  }

  const entry = files.get(url.pathname);

  if (!entry) {
    res.writeHead(404, {
      "Content-Type": "text/plain; charset=utf-8",
      "X-Content-Type-Options": "nosniff"
    });
    return res.end("Not found");
  }

  try {
    const body = await readFile(new URL(entry[0], root));

    res.writeHead(200, {
      "Content-Type": entry[1],
      "Cache-Control": "no-store",
      "X-Content-Type-Options": "nosniff",
      "Permissions-Policy":
        "geolocation=(self), camera=(self), microphone=(self), fullscreen=(self)",
      "Content-Security-Policy":
        "default-src 'self'; script-src 'self'; style-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'"
    });

    if (req.method === "HEAD") return res.end();
    return res.end(body);
  } catch {
    res.writeHead(500);
    return res.end("Cannot read lab file");
  }
});

server.listen(3000, "localhost", () => {
  console.log("Permission test lab: http://localhost:3000");
});
~~~

### 11.3 Tạo public/index.html

~~~html
<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Permission test lab</title>
  <script src="/app.js" defer></script>
</head>
<body>
  <main>
    <h1>Permission test lab</h1>
    <p id="environment"></p>

    <section>
      <h2>Trạng thái có thể query</h2>
      <button id="inspect" type="button">Đọc permission state</button>
      <pre id="states">Chưa kiểm tra.</pre>
    </section>

    <section>
      <h2>Geolocation</h2>
      <button id="geo" type="button">Thử đọc vị trí</button>
    </section>

    <section>
      <h2>Camera</h2>
      <button id="camera" type="button">Thử camera</button>
    </section>

    <section>
      <h2>Microphone</h2>
      <button id="microphone" type="button">Thử microphone</button>
    </section>

    <section>
      <h2>Notifications</h2>
      <button id="notification" type="button">Xin notification permission</button>
    </section>

    <section>
      <h2>Kết quả</h2>
      <pre id="result">Chưa thực hiện thao tác.</pre>
    </section>
  </main>
</body>
</html>
~~~

### 11.4 Tạo public/app.js

~~~js
const environment = document.querySelector("#environment");
const states = document.querySelector("#states");
const result = document.querySelector("#result");

environment.textContent = JSON.stringify({
  secureContext: window.isSecureContext,
  origin: location.origin,
  geolocationApi: Boolean(navigator.geolocation),
  mediaDevicesApi: Boolean(navigator.mediaDevices?.getUserMedia),
  notificationApi: "Notification" in window,
  permissionsApi: Boolean(navigator.permissions?.query)
}, null, 2);

async function queryPermission(name) {
  if (!navigator.permissions?.query) {
    return { state: "unsupported-api" };
  }

  try {
    const status = await navigator.permissions.query({ name });

    status.addEventListener("change", () => {
      console.info("Permission changed:", name, status.state);
    });

    return { state: status.state };
  } catch (error) {
    return { state: "descriptor-unsupported", error: error.name };
  }
}

document.querySelector("#inspect").addEventListener("click", async () => {
  const names = [
    "geolocation",
    "camera",
    "microphone",
    "notifications",
    "clipboard-read"
  ];

  const entries = await Promise.all(
    names.map(async name => [name, await queryPermission(name)])
  );

  states.textContent = JSON.stringify(Object.fromEntries(entries), null, 2);
});

document.querySelector("#geo").addEventListener("click", () => {
  if (!navigator.geolocation) {
    result.textContent = "Geolocation API unavailable";
    return;
  }

  navigator.geolocation.getCurrentPosition(
    () => {
      result.textContent = "Geolocation SUCCESS; tọa độ không được hiển thị.";
    },
    error => {
      result.textContent = JSON.stringify({
        result: "Geolocation ERROR",
        code: error.code,
        message: error.message
      }, null, 2);
    },
    {
      timeout: 8000,
      maximumAge: 0,
      enableHighAccuracy: false
    }
  );
});

async function testMedia(kind) {
  if (!navigator.mediaDevices?.getUserMedia) {
    result.textContent = "MediaDevices API unavailable";
    return;
  }

  let stream;

  try {
    stream = await navigator.mediaDevices.getUserMedia({
      audio: kind === "audio",
      video: kind === "video"
    });

    result.textContent = kind + " SUCCESS";
  } catch (error) {
    result.textContent = kind + " ERROR: " + error.name;
  } finally {
    stream?.getTracks().forEach(track => track.stop());
  }
}

document.querySelector("#camera").addEventListener("click", () => {
  void testMedia("video");
});

document.querySelector("#microphone").addEventListener("click", () => {
  void testMedia("audio");
});

document.querySelector("#notification").addEventListener("click", async () => {
  if (!("Notification" in window)) {
    result.textContent = "Notification API unavailable";
    return;
  }

  try {
    const permission = await Notification.requestPermission();
    result.textContent = "Notification permission: " + permission;
  } catch (error) {
    result.textContent = "Notification ERROR: " + error.name;
  }
});
~~~

### 11.5 Chạy lab

~~~bash
node server.mjs
~~~

Mở:

~~~text
http://localhost:3000
~~~

Kiểm tra secureContext là true. Mở DevTools → Network và xác nhận response HTML có Permissions-Policy. Lab không tự xin quyền khi trang tải.

### 11.6 Chạy các ca manual

1. Bấm Đọc permission state và ghi nhận descriptor nào được browser hỗ trợ.
2. Bấm Thử đọc vị trí; chọn Allow, Block hoặc dismiss theo từng lượt test.
3. Reset permission trong Site settings rồi tải lại để kiểm tra prompt ban đầu.
4. Bấm Thử camera và microphone riêng; xác nhận track được stop sau khi test.
5. Bấm Xin notification permission sau khi đọc giải thích.
6. Thu hồi quyền trong Site settings rồi quay lại tab và thử API lần nữa.
7. Tắt quyền camera của browser trong OS settings và thử lại để phân biệt browser với OS.
8. Chạy cùng test trên browser khác hoặc profile riêng tư và ghi lại khác biệt.

Không dùng vị trí hoặc thiết bị thật cho dữ liệu production; lab không lưu tọa độ, ảnh, âm thanh hay notification payload.

### 11.7 Test Permissions Policy chặn feature

Đổi header geolocation trong server thành:

~~~http
Permissions-Policy: geolocation=(), camera=(self), microphone=(self), fullscreen=(self)
~~~

Khởi động lại server, tải lại trang và thử geolocation. API có thể bị chặn dù browser permission trước đó là granted. Kết quả cụ thể và error name có thể khác theo browser; đối chiếu Console và response header.

### 11.8 Dọn lab

Dừng Node server bằng Ctrl+C. Thu hồi permission của localhost trong Site settings nếu cần. Không xóa permission profile dùng cho công việc khác.

## 12. Ma trận tương thích và phạm vi automation

### 12.1 Không có một ma trận permission chung cho mọi API

Hỗ trợ thay đổi theo browser, phiên bản, OS, API và descriptor. Một browser có thể hỗ trợ camera nhưng không hỗ trợ query camera descriptor qua Permissions API. Một API có thể tồn tại nhưng bị policy hoặc user activation giới hạn.

Ghi nhận theo capability cụ thể thay vì chỉ đánh dấu browser là hỗ trợ/không hỗ trợ.

### 12.2 Ma trận kiểm thử khuyến nghị

| Runtime | Permissions API | Geolocation | Camera/mic | Notifications | Ghi chú |
|---|---|---|---|---|---|
| Chromium desktop | Query nhiều descriptor phổ biến; vẫn cần feature detection | Hỗ trợ trong secure context | Hỗ trợ với thiết bị và OS permission | Hỗ trợ; prompt có thể bị hạn chế | Playwright/CDP có khả năng automation rộng |
| Firefox desktop | Descriptor support khác Chromium | Hỗ trợ trong secure context | Hỗ trợ tùy OS/device | Hỗ trợ với chính sách riêng | Kiểm tra permission UI và automation theo version |
| Safari macOS | Descriptor support giới hạn hơn tùy phiên bản | Hỗ trợ trong secure context | Phụ thuộc WebKit, OS privacy settings và thiết bị | Hỗ trợ theo chính sách Safari | Kiểm thử thực tế trên Safari |
| Chrome Android | Browser/OS permission cùng ảnh hưởng | Hỗ trợ | Phụ thuộc Android permission và thiết bị | Hỗ trợ theo browser/PWA context | Kiểm tra cả tab và installed PWA nếu liên quan |
| Safari iOS | Hỗ trợ và prompt chịu quy tắc WebKit/iOS | Hỗ trợ theo secure context và setting | Quyền camera/mic chịu OS và WebKit | Có giới hạn theo phiên bản và PWA context | Kiểm thử trên thiết bị thật |
| Android WebView | Phụ thuộc WebView và host app | Cần host app xử lý permission phù hợp | Host app phải khai báo và cấp OS permission | Phụ thuộc WebView/host app | Test native bridge và WebChromeClient |
| Embedded browser | Có thể bị giới hạn | Phụ thuộc host | Phụ thuộc host và OS | Có thể khác browser chính | Không suy rộng từ browser desktop |

Đây là ma trận phạm vi kiểm thử, không phải cam kết phiên bản tối thiểu. Trước release, kiểm tra browser support hiện tại của từng API và descriptor; xác minh cả thiết bị/OS được hỗ trợ.

### 12.3 Playwright không thay thế browser matrix

Playwright có thể chạy Chromium, Firefox và WebKit, nhưng API grant permission không bảo đảm cùng semantics giữa các engine. CDP chỉ áp dụng cho Chromium-based browser. Test automation nên ghi engine và version trong kết quả.

Dùng automation cho regression ổn định, manual test cho prompt thật, OS setting, thiết bị và browser embedded.

### 12.4 WebDriver và browser-specific permission controls

WebDriver có thể điều khiển thao tác người dùng và browser session, nhưng permission prompt/OS chooser không được chuẩn hóa đầy đủ thành một API portable cho mọi browser. Selenium, Playwright và CDP có khả năng khác nhau.

Nếu test cần kiểm tra dialog thật, dùng browser profile sạch và quy trình manual/OS-specific. Không giả lập một click vào prompt rồi tuyên bố tất cả browser xử lý giống nhau.

## 13. Chẩn đoán lỗi permission test

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| navigator.permissions.query reject | Descriptor không được hỗ trợ hoặc tham số không hợp lệ | Feature detect, catch lỗi và test API trực tiếp |
| State granted nhưng API lỗi | OS/device, user activation, policy hoặc API condition | Kiểm tra error name, OS settings và policy |
| State prompt nhưng không hiện prompt | API chưa được gọi, thiếu activation hoặc browser chặn prompt | Gọi từ user gesture và kiểm tra Console |
| Geolocation trả code 1 | User deny hoặc Permissions Policy chặn | Kiểm tra Site settings và response header |
| Camera trả NotFoundError | Không có thiết bị phù hợp | Kiểm tra thiết bị và constraints |
| Camera trả NotReadableError | Thiết bị bận hoặc OS không cho browser truy cập | Đóng app khác, kiểm tra OS privacy setting |
| API lỗi trong HTTP page | Không phải secure context | Dùng HTTPS hoặc localhost |
| iframe bị chặn dù user đã grant | Ancestor policy hoặc allow attribute không phù hợp | Kiểm tra toàn bộ frame chain |
| Playwright khác browser thật | Permission emulation và user activation khác | Ghi engine/version và chạy manual regression |
| Permission vẫn granted sau logout | Permission gắn với origin/profile, không phải account | Stop stream và tách permission khỏi session |
| Thu hồi quyền nhưng UI không đổi ngay | Browser không phát change hoặc component không query lại | Query khi tab focus/visibility trở lại |
| OS đã cấp quyền nhưng browser bị deny | Browser-level permission riêng | Kiểm tra Site settings |
| Browser grant nhưng OS deny | OS permission riêng | Bật quyền cho browser trong OS settings |
| Fullscreen thất bại | Thiếu user activation hoặc policy | Gọi từ click và kiểm tra allow/header |
| Screen capture không mở chooser trong test | Automation không mô phỏng chooser | Manual test hoặc cơ chế browser-specific |

## 14. Ma trận test case tổng hợp

| ID | Feature | State/Context | Kết quả cần xác nhận |
|---|---|---|---|
| PT01 | Geolocation | Secure + granted | API thành công với vị trí giả lập |
| PT02 | Geolocation | Denied | Error code 1 và fallback |
| PT03 | Geolocation | Policy disabled | API bị chặn; không coi là user deny chắc chắn |
| PT04 | Geolocation | Insecure context | API không khả dụng hoặc bị chặn |
| PT05 | Geolocation | Timeout | UI kết thúc chờ và không giữ spinner |
| PT06 | Camera | Granted + fake device | getUserMedia thành công, track được stop |
| PT07 | Camera | Denied | NotAllowedError hoặc lỗi phù hợp; UI hướng dẫn |
| PT08 | Camera | No device | NotFoundError |
| PT09 | Camera | Device busy/OS denied | NotReadableError hoặc lỗi browser-specific |
| PT10 | Microphone | Camera denied, microphone granted | Quyền được xử lý độc lập |
| PT11 | Notifications | Default | Prompt chỉ sau user action |
| PT12 | Notifications | Denied | Không lặp prompt; UI hướng dẫn setting |
| PT13 | Clipboard | No user activation | API bị từ chối theo browser policy |
| PT14 | Clipboard | User gesture + granted | Thao tác phù hợp thành công |
| PT15 | Fullscreen | Click activation | Vào fullscreen nếu policy cho phép |
| PT16 | Fullscreen | Timer/no activation | Request thất bại |
| PT17 | Screen capture | User cancel chooser | UI trở về trạng thái idle |
| PT18 | Screen capture | User stops sharing | Track ended và UI cập nhật |
| PT19 | iframe | Child origin được delegate | API có thể tiếp tục tới permission check |
| PT20 | iframe | Child không nằm allowlist | Feature bị policy giới hạn |
| PT21 | iframe | Ancestor tắt feature | Child không bật lại được |
| PT22 | Lifecycle | Grant rồi reload | Kiểm tra persistence trong profile |
| PT23 | Lifecycle | Revoke khi đang chạy | UI cleanup và lần gọi sau thất bại |
| PT24 | Account | Logout/login account khác | Không giữ stream hoặc dữ liệu session cũ |
| PT25 | Browser profile | Profile mới | Không kế thừa grant ngoài dự kiến |
| PT26 | OS | Browser grant, OS deny | API không được coi là thành công |
| PT27 | Automation | Context mới | State cô lập giữa test |
| PT28 | Automation | CDP denied | Chỉ áp dụng Chromium, kết quả ghi rõ engine |

## 15. Câu hỏi tự kiểm tra

**Câu 1.** Permissions API query() có hiển thị prompt không?

**Đáp án:** Không. query() chỉ đọc trạng thái permission descriptor nếu browser hỗ trợ. API thật mới có thể kích hoạt prompt.

**Câu 2.** Permission state granted có bảo đảm camera mở được không?

**Đáp án:** Không. OS permission, thiết bị, user activation, Permissions Policy và điều kiện API vẫn có thể làm thao tác thất bại.

**Câu 3.** CORS có cấp quyền geolocation hoặc camera không?

**Đáp án:** Không. CORS kiểm soát khả năng đọc response cross-origin; permission và Permissions Policy kiểm soát feature trình duyệt.

**Câu 4.** Vì sao cần test secure context?

**Đáp án:** Nhiều API nhạy cảm chỉ được expose trong secure context. HTTP LAN không nhất thiết được browser coi là trustworthy như localhost.

**Câu 5.** Vì sao không gọi requestPermission ngay khi page load?

**Đáp án:** Prompt bất ngờ làm người dùng khó hiểu mục đích, có thể bị browser hạn chế và khuyến khích cấp quyền không cần thiết. Hãy xin sau hành động có chủ đích.

**Câu 6.** Permissions Policy khác browser permission thế nào?

**Đáp án:** Browser permission phản ánh quyết định của browser/người dùng; Permissions Policy giới hạn document và frame nào được sử dụng feature. Child không thể mở lại feature bị ancestor tắt.

**Câu 7.** NotAllowedError luôn có nghĩa người dùng bấm Block?

**Đáp án:** Không. Policy, thiếu activation hoặc browser/OS restriction cũng có thể dẫn đến lỗi từ chối.

**Câu 8.** Vì sao test camera cần stop MediaStream tracks?

**Đáp án:** Để giải phóng thiết bị, dừng capture và tránh giữ camera/microphone hoạt động sau test.

**Câu 9.** Vì sao Playwright CDP permission test không portable?

**Đáp án:** CDP là giao thức của Chromium. Firefox, WebKit, Safari, WebView và OS chooser có cơ chế riêng.

**Câu 10.** Permission có thuộc về tài khoản ứng dụng không?

**Đáp án:** Thông thường permission được quản lý theo origin và browser profile. Logout không tự thu hồi permission; ứng dụng phải cleanup stream và dữ liệu session riêng.

## 16. Checklist trước khi release

### Thiết kế và UX

- [ ] Chỉ yêu cầu feature thực sự cần thiết.
- [ ] Giải thích mục đích trước khi mở prompt.
- [ ] Xin quyền sau thao tác rõ ràng của người dùng.
- [ ] Có đường đi hữu ích khi người dùng deny hoặc dismiss.
- [ ] Không lặp prompt liên tục.
- [ ] Không giả mạo giao diện browser permission prompt.

### Browser và API

- [ ] Kiểm tra API availability.
- [ ] Kiểm tra secure context.
- [ ] Query Permissions API có try/catch.
- [ ] Không coi descriptor unsupported là denied.
- [ ] Gọi API thật sau khi kiểm tra state.
- [ ] Kiểm tra user activation/focus khi API yêu cầu.
- [ ] Phân loại error name/code theo API.
- [ ] Không log tọa độ, video, audio hoặc clipboard data.

### Policy và frame

- [ ] Kiểm tra Permissions-Policy trên response HTML thực tế.
- [ ] Kiểm tra toàn bộ ancestor policy.
- [ ] Kiểm tra iframe allow attribute và origin chính xác.
- [ ] Kiểm tra sandbox độc lập với Permissions Policy.
- [ ] Test redirect và origin đích nếu có iframe navigation.
- [ ] Không dùng CORS như cơ chế cấp permission.

### Automation và vận hành

- [ ] Dùng browser context mới cho mỗi test.
- [ ] Grant/revoke permission theo origin rõ ràng.
- [ ] Ghi engine/version cho test CDP-specific.
- [ ] Dùng fake device và tọa độ giả lập khi phù hợp.
- [ ] Manual test prompt thật và OS settings.
- [ ] Test profile riêng tư, mobile và WebView mục tiêu.
- [ ] Stop stream, clear watch và cleanup khi test kết thúc.
- [ ] Không coi automation là bằng chứng tương thích mọi browser.
- [ ] Ghi kết quả và lỗi mà không chứa dữ liệu nhạy cảm.

**Ghi nhớ:** Permission test phải xác minh toàn bộ đường đi từ API capability, secure context và Permissions Policy đến browser grant, user activation, OS và thiết bị. Hãy kết hợp state inspection với lời gọi API thật, test cả grant/deny/revoke, giữ quyền ở mức tối thiểu và dùng automation đúng phạm vi mà browser hỗ trợ.

## Tài liệu tham khảo

- [W3C — Permissions](https://www.w3.org/TR/permissions/)
- [W3C — Permissions Registry](https://www.w3.org/TR/permissions/#permissions-registry)
- [W3C — Permissions Policy](https://www.w3.org/TR/permissions-policy/)
- [MDN — Permissions API](https://developer.mozilla.org/en-US/docs/Web/API/Permissions_API)
- [MDN — Permissions Policy guide and relationship with Permissions API](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Permissions_Policy)
- [MDN — Permissions.query()](https://developer.mozilla.org/en-US/docs/Web/API/Permissions/query)
- [MDN — PermissionStatus](https://developer.mozilla.org/en-US/docs/Web/API/PermissionStatus)
- [MDN — Geolocation API](https://developer.mozilla.org/en-US/docs/Web/API/Geolocation_API)
- [MDN — MediaDevices.getUserMedia()](https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getUserMedia)
- [MDN — Notification.requestPermission()](https://developer.mozilla.org/en-US/docs/Web/API/Notification/requestPermission_static)
- [MDN — Permissions-Policy header](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Permissions-Policy)
- [Playwright — BrowserContext.grantPermissions()](https://playwright.dev/docs/api/class-browsercontext#browser-context-grant-permissions)
- [Playwright — BrowserContext.clearPermissions()](https://playwright.dev/docs/api/class-browsercontext#browser-context-clear-permissions)
- [Chrome DevTools Protocol — Browser.setPermission](https://chromedevtools.github.io/devtools-protocol/tot/Browser/#method-setPermission)

