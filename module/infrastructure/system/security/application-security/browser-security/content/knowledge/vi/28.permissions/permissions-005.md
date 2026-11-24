# Notifications: xin quyền và hiển thị thông báo an toàn trong browser

## 1. Notifications API là gì?

**Notifications API** cho phép một website yêu cầu browser hiển thị thông báo ngoài vùng nội dung của trang, thường ở khu vực notification center của hệ điều hành hoặc giao diện thông báo của browser. Ứng dụng có thể dùng thông báo để báo tin nhắn mới, trạng thái đơn hàng, nhắc lịch hoặc cập nhật mà người dùng đã chủ động đăng ký.

Ví dụ một trang muốn hiển thị thông báo:

~~~js
const notification = new Notification("Có tin nhắn mới", {
  body: "Bạn vừa nhận được một tin nhắn.",
  icon: "/icons/notification.png"
});
~~~

Đoạn code chỉ hoạt động khi browser hỗ trợ Notifications API, trang chạy trong secure context và origin đã được người dùng cấp quyền thông báo. Ứng dụng không được tự ý bật thông báo chỉ vì người dùng mở trang.

Quyền thông báo là một **permission do browser và người dùng quản lý**. Website có thể hỏi trạng thái, yêu cầu quyền trong một tương tác phù hợp và phản ứng với kết quả. Người dùng có thể từ chối, thu hồi quyền hoặc chặn thông báo trong cài đặt browser/hệ điều hành.

Bài học thuộc chương **Permissions** của module **SECURITY_APPLICATION_SECURITY_BROWSER_SECURITY**. Module phân tích ranh giới bảo mật giữa browser, origin, cookie và ứng dụng web; thực hành Same-Origin Policy, CORS, XSS, CSRF, clickjacking, CSP, Trusted Types và security headers. Bài này tập trung vào quyền notifications, vòng đời yêu cầu quyền, thông báo foreground/service worker, Push API và các rủi ro về quyền riêng tư.

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích Notifications API và vai trò của permission.
2. Phân biệt trạng thái Notification.permission với Permission API state.
3. Yêu cầu quyền đúng thời điểm sau hành động rõ ràng của người dùng.
4. Kiểm tra secure context và browser support trước khi dùng API.
5. Tạo notification trong trang và hiểu giới hạn của Notification constructor.
6. Dùng service worker registration để hiển thị thông báo persistent.
7. Phân biệt Notifications API với Push API và push subscription.
8. Hiểu quyền thông báo trong iframe và Permissions Policy.
9. Thiết kế nội dung notification không làm lộ dữ liệu nhạy cảm.
10. Xử lý permission bị từ chối, thu hồi hoặc bị browser/hệ điều hành chặn.
11. Debug hành vi notification bằng DevTools và cài đặt site/browser.

## 2. Permission bảo vệ điều gì?

Thông báo xuất hiện ngoài trang web. Chúng có thể hiển thị khi người dùng đang làm việc ở ứng dụng khác, trên màn hình khóa hoặc trong khu vực thông báo của thiết bị. Vì vậy, việc cho phép một website gửi thông báo là một quyền ảnh hưởng tới trải nghiệm và quyền riêng tư của người dùng.

Nếu website nào cũng được tự do gửi thông báo, người dùng có thể bị:

- Làm phiền bởi quảng cáo hoặc thông báo lặp lại.
- Đánh lừa bằng nội dung giả mạo cảnh báo hệ thống.
- Lộ nội dung tin nhắn, mã xác nhận hoặc dữ liệu cá nhân trên màn hình khóa.
- Dẫn tới trang giả mạo qua thao tác bấm notification.
- Bị theo dõi mức độ hoạt động thông qua hệ thống push hoặc hành vi tương tác.

Browser yêu cầu permission để người dùng quyết định origin nào được hiển thị thông báo. Permission này không phải quyền truy cập chung vào tài khoản, không cấp quyền đọc file và cũng không chứng minh website đáng tin về mọi mặt.

### 2.1. Permission thường gắn với origin

Quyền thông báo thường được lưu theo origin hoặc phạm vi site do browser quản lý. Origin gồm scheme, host và port. Vì vậy, các địa chỉ sau có thể có trạng thái permission khác nhau:

~~~text
https://app.example.test
https://admin.example.test
http://app.example.test
https://app.example.test:8443
~~~

Không giả định cấp quyền cho một subdomain sẽ tự động cấp quyền cho mọi subdomain khác. Browser profile, chế độ riêng tư, chính sách doanh nghiệp và cài đặt thiết bị cũng có thể ảnh hưởng kết quả.

### 2.2. Permission không phải authorization nghiệp vụ

Nếu người dùng cấp quyền notifications, website chỉ được phép yêu cầu browser hiển thị thông báo theo API và policy liên quan. Điều đó không có nghĩa người dùng đã cấp quyền xem một đơn hàng, tài khoản hoặc dữ liệu riêng tư.

Server vẫn phải xác thực user, kiểm tra quyền truy cập tài nguyên và chỉ gửi nội dung phù hợp tới thiết bị đã đăng ký. Không dùng notification permission thay cho authentication hoặc authorization.

## 3. Ba trạng thái của Notification.permission

Thuộc tính:

~~~js
Notification.permission
~~~

trả về một trong ba giá trị:

| Giá trị | Ý nghĩa | Cách ứng dụng nên phản ứng |
| --- | --- | --- |
| `"default"` | Người dùng chưa đưa ra quyết định rõ ràng hoặc browser chưa có quyền được lưu. | Giải thích lợi ích rồi chờ người dùng chủ động yêu cầu. |
| `"granted"` | Browser cho phép origin hiển thị notification. | Có thể hiển thị thông báo theo nhu cầu hợp lệ. |
| `"denied"` | Quyền đã bị từ chối hoặc bị chặn. | Không tiếp tục gọi prompt; hướng dẫn người dùng mở cài đặt nếu họ muốn đổi. |

Lưu ý `"default"` không đồng nghĩa với `"granted"`. Ứng dụng không được giả định có thể hiển thị notification khi trạng thái còn default.

### 3.1. Phân biệt với Permissions API state

Permissions API có thể trả về PermissionStatus.state:

- `"prompt"`: browser có thể cần hỏi người dùng.
- `"granted"`: quyền đã được cấp.
- `"denied"`: quyền bị từ chối hoặc bị chặn.

Với Notifications API, `Notification.permission` dùng chuỗi `"default"` cho trạng thái chưa có quyết định, trong khi Permissions API thường biểu diễn trạng thái tương ứng là `"prompt"`.

Hai API có cách biểu diễn khác nhau. Không so sánh chuỗi của chúng như thể cùng một enum.

### 3.2. Permission có thể thay đổi

Người dùng có thể thu hồi quyền trong site settings hoặc cài đặt hệ điều hành. Browser cũng có thể tự động reset permission của site ít hoạt động, dùng quiet UI hoặc thay đổi cách hỏi quyền theo mức độ tương tác.

Không lưu trạng thái granted vĩnh viễn trong localStorage rồi tin rằng nó còn đúng. Kiểm tra trạng thái hiện tại trước khi thực hiện chức năng cần notification và xử lý trường hợp quyền đã đổi.

## 4. Notifications API cần secure context

Notifications API được thiết kế cho secure context. Trong môi trường production, hãy phục vụ trang qua HTTPS với certificate hợp lệ.

Một số địa chỉ loopback như localhost có thể được browser xem là trustworthy origin cho phát triển. Ngoại lệ này không có nghĩa mọi địa chỉ mạng nội bộ hoặc HTTP trong production đều an toàn.

Kiểm tra cơ bản:

~~~js
if (!window.isSecureContext) {
  console.warn("Notifications cần secure context.");
}
~~~

Kiểm tra API có tồn tại:

~~~js
if (!("Notification" in window)) {
  console.warn("Browser này không hỗ trợ Notifications API.");
}
~~~

Cả hai điều kiện đều cần được xem xét trước khi hiển thị giao diện xin quyền. Browser không hỗ trợ API hoặc trang không ở secure context thì ứng dụng cần cung cấp phương án thay thế.

## 5. Xin quyền sau hành động rõ ràng của người dùng

Không nên gọi `Notification.requestPermission()` ngay khi trang vừa tải. Một prompt bất ngờ khiến người dùng khó hiểu website cần quyền để làm gì và dễ dẫn tới từ chối.

Một luồng UX tốt:

1. Người dùng sử dụng chức năng có giá trị như theo dõi đơn hàng hoặc nhận tin nhắn.
2. Ứng dụng giải thích loại thông báo sẽ gửi và tần suất dự kiến.
3. Người dùng bấm nút rõ ràng như “Bật thông báo”.
4. Ứng dụng gọi requestPermission trong handler của hành động đó.
5. Giao diện phản hồi theo granted, denied hoặc default.

Ví dụ HTML:

~~~html
<button id="enable-notifications" type="button">
  Bật thông báo
</button>
<p id="notification-status" role="status" aria-live="polite"></p>
~~~

JavaScript:

~~~js
const button = document.querySelector("#enable-notifications");
const status = document.querySelector("#notification-status");

button.addEventListener("click", async () => {
  if (!("Notification" in window)) {
    status.textContent = "Browser không hỗ trợ thông báo.";
    return;
  }

  if (!window.isSecureContext) {
    status.textContent = "Hãy mở ứng dụng qua HTTPS.";
    return;
  }

  const permission = await Notification.requestPermission();

  if (permission === "granted") {
    status.textContent = "Bạn đã bật thông báo.";
  } else if (permission === "denied") {
    status.textContent = "Quyền thông báo đang bị chặn.";
  } else {
    status.textContent = "Bạn chưa quyết định bật thông báo.";
  }
});
~~~

### 5.1. User gesture và browser prompt

Browser hiện đại thường yêu cầu hoặc ưu tiên một thao tác trực tiếp từ người dùng trước khi hiển thị permission prompt. Một số browser có thể từ chối, trì hoãn hoặc không hiển thị prompt nếu request không xuất phát từ tương tác phù hợp.

Không giả định gọi requestPermission từ timer, page load, background task hoặc callback bất kỳ sẽ luôn hiển thị hộp thoại. Hãy gọi trực tiếp từ handler của nút mà người dùng vừa bấm.

### 5.2. Không hỏi lại liên tục

Nếu người dùng chọn denied, gọi requestPermission nhiều lần không giúp thay đổi quyết định. Browser có thể chặn prompt tiếp theo hoặc đưa site vào quiet permission UI.

Hãy hiển thị hướng dẫn ngắn để người dùng tự mở cài đặt site/browser nếu họ muốn bật lại. Không tạo vòng lặp prompt, popup gây áp lực hoặc chặn chức năng cốt lõi chỉ vì người dùng không cấp quyền notification.

## 6. Notification.requestPermission()

API:

~~~js
const permission = await Notification.requestPermission();
~~~

trả về Promise giải quyết thành `"granted"`, `"denied"` hoặc `"default"`.

Ví dụ hàm có kiểm tra điều kiện:

~~~js
async function askForNotificationPermission() {
  if (!("Notification" in window)) {
    return "unsupported";
  }

  if (!window.isSecureContext) {
    return "insecure-context";
  }

  if (Notification.permission === "granted") {
    return "granted";
  }

  if (Notification.permission === "denied") {
    return "denied";
  }

  return await Notification.requestPermission();
}
~~~

Hàm này không tự tạo user gesture. Cần gọi nó từ một event handler phù hợp:

~~~js
enableButton.addEventListener("click", async () => {
  const result = await askForNotificationPermission();
  renderPermissionState(result);
});
~~~

### 6.1. Callback cũ

Một số code legacy dùng callback:

~~~js
Notification.requestPermission((permission) => {
  console.log(permission);
});
~~~

Promise-based form là cách viết phù hợp cho code mới. Hỗ trợ callback cũ và chi tiết tương thích có thể khác giữa browser; không viết ứng dụng mới phụ thuộc vào callback signature.

### 6.2. Bắt lỗi và trạng thái unsupported

Permission request có thể không hoạt động vì browser không hỗ trợ, context không an toàn, policy chặn hoặc browser không cho phép prompt trong ngữ cảnh hiện tại.

~~~js
async function requestPermissionSafely() {
  if (!("Notification" in window)) {
    return { state: "unsupported" };
  }

  if (!window.isSecureContext) {
    return { state: "insecure-context" };
  }

  try {
    const state = await Notification.requestPermission();
    return { state };
  } catch (error) {
    return {
      state: "error",
      reason: error.name
    };
  }
}
~~~

Không hiển thị stack trace hoặc thông tin kỹ thuật dài cho người dùng cuối. Ghi log tối thiểu để chẩn đoán và không log dữ liệu cá nhân.

## 7. Kiểm tra quyền bằng Permissions API

Permissions API cho phép truy vấn trạng thái permission theo một descriptor:

~~~js
const status = await navigator.permissions.query({
  name: "notifications"
});

console.log(status.state);
~~~

Nếu browser hỗ trợ descriptor này, state thường là `"granted"`, `"denied"` hoặc `"prompt"`.

Ví dụ theo dõi thay đổi:

~~~js
async function watchNotificationPermission() {
  if (!navigator.permissions?.query) {
    return null;
  }

  try {
    const status = await navigator.permissions.query({
      name: "notifications"
    });

    status.addEventListener("change", () => {
      console.log("Notification permission:", status.state);
      updateNotificationUI(status.state);
    });

    return status;
  } catch {
    // Browser có thể không hỗ trợ descriptor notifications.
    return null;
  }
}
~~~

### 7.1. Permissions API không cấp quyền

query chỉ đọc trạng thái permission. Nó không hiển thị prompt và không biến prompt thành granted.

Để yêu cầu quyền Notifications API, dùng Notification.requestPermission() trong tương tác người dùng phù hợp. Đừng nhầm Permissions API với một API tự cấp quyền.

### 7.2. Hỗ trợ không đồng nhất

Permissions API và từng permission descriptor không được hỗ trợ giống nhau ở mọi browser. Luôn dùng feature detection và try/catch. Nếu query thất bại, có thể dùng Notification.permission khi Notifications API tồn tại.

Ví dụ hàm đọc trạng thái:

~~~js
async function getNotificationState() {
  if (!("Notification" in window)) {
    return "unsupported";
  }

  if (navigator.permissions?.query) {
    try {
      const result = await navigator.permissions.query({
        name: "notifications"
      });
      return result.state;
    } catch {
      // Dùng fallback bên dưới.
    }
  }

  if (Notification.permission === "default") {
    return "prompt";
  }

  return Notification.permission;
}
~~~

Fallback chuyển default thành prompt để giao diện dùng một mô hình thống nhất. Không ghi đè trạng thái thật của Notification.permission.

## 8. Tạo notification trong trang đang mở

Khi permission đã granted, một trang có thể tạo notification:

~~~js
const notification = new Notification("Đơn hàng đã được xác nhận", {
  body: "Đơn hàng của bạn đang được chuẩn bị.",
  icon: "/icons/notification.png",
  tag: "order-status"
});
~~~

Các option phổ biến:

| Option | Ý nghĩa |
| --- | --- |
| body | Nội dung ngắn hiển thị dưới tiêu đề. |
| icon | URL icon của thông báo. |
| badge | Biểu tượng nhỏ trên một số nền tảng. |
| tag | Nhóm thông báo để browser có thể thay thế thông báo cùng tag. |
| data | Dữ liệu có cấu trúc gắn với notification object. |
| silent | Yêu cầu hiển thị không phát âm thanh nếu nền tảng hỗ trợ. |
| renotify | Điều khiển việc thông báo lại khi thay thế notification cùng tag trong các trường hợp được hỗ trợ. |

Không phải option nào cũng được mọi browser hoặc hệ điều hành hỗ trợ giống nhau. Coi option là gợi ý cho nền tảng, không phải bảo đảm giao diện hoặc âm thanh cụ thể.

### 8.1. Notification constructor có giới hạn

`new Notification()` tạo notification từ trang đang mở. API này không phải lựa chọn phù hợp cho mọi browser/mobile platform; một số môi trường yêu cầu dùng service worker notification thay cho constructor trực tiếp.

Nếu cần notification tồn tại độc lập với vòng đời tab hoặc hỗ trợ push/background, dùng ServiceWorkerRegistration.showNotification() khi browser hỗ trợ.

### 8.2. Hiển thị sau khi permission đã granted

Ví dụ hàm chỉ hiển thị khi quyền đã được cấp:

~~~js
function showForegroundNotification(title, body) {
  if (!("Notification" in window)) {
    return false;
  }

  if (Notification.permission !== "granted") {
    return false;
  }

  try {
    new Notification(title, {
      body,
      icon: "/icons/notification.png"
    });
    return true;
  } catch {
    return false;
  }
}
~~~

Hàm này không thay thế xử lý lỗi nền tảng. Hệ điều hành có thể đang tắt notification cho browser, bật chế độ focus/do-not-disturb hoặc ẩn banner; permission granted không bảo đảm người dùng sẽ nhìn thấy ngay thông báo.

## 9. Sự kiện click và close

Notification object có các event như click, close, show và error tùy implementation.

Ví dụ:

~~~js
const notification = new Notification("Có cập nhật mới", {
  body: "Mở ứng dụng để xem chi tiết."
});

notification.addEventListener("click", () => {
  window.focus();
  notification.close();
});

notification.addEventListener("close", () => {
  console.log("Notification đã đóng.");
});
~~~

Không giả định event show/error được hỗ trợ giống nhau ở mọi browser. Thiết kế chức năng cốt lõi không nên phụ thuộc vào một event ít được hỗ trợ.

### 9.1. Không coi click là xác nhận giao dịch

Click notification chỉ cho biết người dùng đã tương tác với thông báo. Nó không thay xác nhận trong ứng dụng, không xác thực danh tính và không phải bằng chứng người dùng đã đọc toàn bộ nội dung.

Với giao dịch nhạy cảm, mở ứng dụng rồi hiển thị thông tin đầy đủ và yêu cầu bước xác nhận phù hợp. Server vẫn phải kiểm tra session, quyền và trạng thái giao dịch.

### 9.2. Điều hướng từ notification phải được kiểm tra

Nếu notification chứa URL trong data, không đưa URL tùy ý vào location. Parse URL và giới hạn origin/path:

~~~js
function getSafeNotificationUrl(value) {
  const url = new URL(value || "/inbox", window.location.origin);

  if (url.origin !== window.location.origin) {
    throw new TypeError("Notification URL không hợp lệ");
  }

  return url.href;
}
~~~

Chỉ điều hướng tới route do ứng dụng kiểm soát. Không tin payload notification chỉ vì nó đến từ service worker hoặc backend.

## 10. Service worker và persistent notification

Notification constructor gắn với trang đang mở. Nếu ứng dụng cần hiển thị notification từ service worker, dùng:

~~~js
self.registration.showNotification("Có tin nhắn mới", {
  body: "Bạn có một tin nhắn chưa đọc.",
  icon: "/icons/notification.png"
});
~~~

Service worker có thể được đánh thức bởi push event hoặc một số sự kiện nền được browser hỗ trợ. Nó không có DOM window như trang web và không dùng `new Notification()` theo cách của foreground page.

Đăng ký service worker:

~~~js
if ("serviceWorker" in navigator && window.isSecureContext) {
  const registration = await navigator.serviceWorker.register("/sw.js");
  console.log("Service worker scope:", registration.scope);
}
~~~

Sau khi đăng ký, có thể lấy registration sẵn sàng:

~~~js
const registration = await navigator.serviceWorker.ready;
await registration.showNotification("Nhắc lịch", {
  body: "Cuộc hẹn của bạn sắp bắt đầu.",
  icon: "/icons/notification.png"
});
~~~

### 10.1. showNotification vẫn cần permission

Service worker không có đường tắt để bỏ qua notification permission. Browser vẫn kiểm tra quyền của origin và các chính sách liên quan. Nếu permission đã bị thu hồi, lời gọi có thể thất bại.

~~~js
try {
  await registration.showNotification("Thông báo", {
    body: "Nội dung cập nhật."
  });
} catch (error) {
  console.error("Không thể hiển thị notification:", error.name);
}
~~~

Không lặp vô hạn khi browser từ chối. Cập nhật trạng thái ứng dụng và cho người dùng biết thông báo đang không khả dụng.

### 10.2. Xử lý notificationclick trong service worker

Service worker có thể xử lý click và mở hoặc focus cửa sổ ứng dụng:

~~~js
self.addEventListener("notificationclick", (event) => {
  event.notification.close();

  const path = event.notification.data?.path || "/inbox";
  const target = new URL(path, self.location.origin);

  if (target.origin !== self.location.origin) {
    return;
  }

  event.waitUntil(
    self.clients.matchAll({
      type: "window",
      includeUncontrolled: true
    }).then((clients) => {
      for (const client of clients) {
        if (new URL(client.url).origin === self.location.origin) {
          return client.focus();
        }
      }

      return self.clients.openWindow(target.href);
    })
  );
});
~~~

Ví dụ này chỉ cho phép route cùng origin. Trong ứng dụng thật, còn cần allowlist path, xác minh user session khi trang mở ra và không để notification payload chọn URL tùy ý.

## 11. Notifications API và Push API khác nhau

Hai API thường được dùng cùng nhau nhưng không đồng nghĩa:

| Cơ chế | Vai trò |
| --- | --- |
| Notifications API | Yêu cầu quyền và hiển thị notification. |
| Service Worker API | Chạy code nền theo vòng đời do browser quản lý và hiển thị persistent notification. |
| Push API | Nhận message từ push service khi ứng dụng không nhất thiết đang mở. |
| Permissions API | Truy vấn trạng thái permission được browser hỗ trợ. |

Cấp notification permission không tự động tạo push subscription. Ứng dụng cần đăng ký service worker, xin subscription qua PushManager và gửi subscription tới backend theo một quy trình riêng.

### 11.1. Tạo push subscription

Ví dụ khái quát sau khi người dùng đã chủ động bật thông báo và permission là granted:

~~~js
const registration = await navigator.serviceWorker.ready;

if (Notification.permission !== "granted") {
  throw new Error("Chưa có quyền thông báo.");
}

const subscription = await registration.pushManager.subscribe({
  userVisibleOnly: true,
  applicationServerKey: vapidPublicKey
});

await saveSubscriptionOnServer(subscription);
~~~

`vapidPublicKey` là public application server key đã được cấu hình. Hàm saveSubscriptionOnServer cần gửi dữ liệu qua HTTPS và gắn subscription với tài khoản đã xác thực.

Browser support, yêu cầu user-visible notification và cách tích hợp Push service có thể khác nhau. Không coi ví dụ là toàn bộ triển khai Push API.

### 11.2. Thu hồi push subscription

Khi người dùng tắt thông báo trong ứng dụng hoặc đăng xuất khỏi tài khoản, cân nhắc xóa subscription ở backend và gọi unsubscribe nếu phù hợp:

~~~js
const registration = await navigator.serviceWorker.ready;
const subscription = await registration.pushManager.getSubscription();

if (subscription) {
  await removeSubscriptionOnServer(subscription);
  await subscription.unsubscribe();
}
~~~

Thứ tự và cách xử lý lỗi cần phù hợp với backend. Endpoint trong PushSubscription là dữ liệu nhạy cảm dạng capability; không ghi toàn bộ endpoint hoặc khóa vào log công khai.

### 11.3. Push permission và notification permission

Push subscription thường phụ thuộc quyền hiển thị thông báo và yêu cầu userVisibleOnly theo Push API. Nhưng hai khái niệm vẫn khác nhau: permission cho phép hiển thị notification; subscription đăng ký endpoint nhận push. Khi một trong hai thay đổi, ứng dụng cần đồng bộ trạng thái với backend.

## 12. Notification permission trong iframe

Không giả định iframe có thể tự do hiển thị prompt xin quyền. Browser có thể hạn chế hoặc từ chối permission request từ iframe, đặc biệt trong ngữ cảnh cross-origin, để tránh một widget bên thứ ba tự yêu cầu quyền thay cho trang host.

Thiết kế phù hợp thường là:

1. Trang top-level giải thích tính năng và xin quyền trong tương tác trực tiếp của người dùng.
2. Nếu widget cần gửi yêu cầu, parent kiểm tra origin/source và schema bằng postMessage.
3. Parent quyết định có thực hiện hành động trong quyền của ứng dụng hay không.
4. Không chuyển credential hoặc quyền rộng cho iframe chỉ để bật thông báo.

### 12.1. Permissions Policy

Một số browser hỗ trợ directive Permissions Policy cho notifications. Ví dụ:

~~~http
Permissions-Policy: notifications=()
~~~

có thể được dùng để hạn chế tài liệu hiện tại sử dụng Notifications API theo implementation hỗ trợ. Một allowlist cụ thể có thể được khai báo khi sản phẩm thật sự cần:

~~~http
Permissions-Policy: notifications=(self "https://widget.example.test")
~~~

Permissions Policy chỉ giới hạn khả năng sử dụng tính năng trong document/frame. Nó **không tự cấp notification permission** và không thay quyết định của người dùng. Cần kiểm tra browser support và cú pháp header ở môi trường mục tiêu trước khi dựa vào directive này.

## 13. Nội dung notification và quyền riêng tư

Notification có thể xuất hiện ở màn hình khóa, thiết bị dùng chung hoặc khi người dùng đang chia sẻ màn hình. Vì vậy, nội dung nên tối thiểu và không làm lộ dữ liệu.

Ví dụ nên dùng:

~~~js
new Notification("Bạn có cập nhật tài khoản", {
  body: "Mở ứng dụng để xem chi tiết.",
  icon: "/icons/notification.png"
});
~~~

Tránh đưa trực tiếp vào body:

- Mã OTP hoặc mã khôi phục.
- Access token, refresh token, session ID.
- Số thẻ, số dư hoặc toàn bộ thông tin giao dịch.
- Nội dung tin nhắn riêng tư nếu người dùng chưa chọn cách hiển thị.
- Địa chỉ nhà hoặc dữ liệu định danh không cần thiết.

Nếu sản phẩm cần hiển thị preview tin nhắn, cho người dùng tùy chọn ẩn nội dung nhạy cảm trên notification. Dùng nội dung trung tính và yêu cầu mở ứng dụng để xem chi tiết.

### 13.1. Không coi notification là kênh xác thực

Notification có thể bị giả mạo về mặt nội dung bởi website có permission, bị hiển thị trên thiết bị không an toàn hoặc bị người khác nhìn thấy. Không dùng notification để gửi OTP duy nhất hoặc thay kênh xác thực đã thiết kế.

### 13.2. Chống phishing và deep link giả mạo

Notification nên nhận diện rõ thương hiệu/app theo thiết kế của browser và hệ điều hành, nhưng không giả định mọi nền tảng luôn hiển thị origin. Khi click, mở ứng dụng qua route nội bộ đã kiểm tra và xác minh session. Không chuyển user tới URL lấy trực tiếp từ payload chưa xác thực.

## 14. XSS và notification permission

Nếu một website có XSS, script độc có thể chạy trong origin và sử dụng những API mà origin đã được cấp quyền. Nếu permission notifications là granted, XSS có thể tạo thông báo gây nhầm lẫn hoặc dẫn người dùng tới nội dung giả.

Vì vậy:

- Notification permission không phải biện pháp chống XSS.
- CSP và Trusted Types giúp giảm một số đường DOM XSS.
- Output encoding, safe DOM APIs và kiểm tra source-to-sink vẫn quan trọng.
- Server cần xác thực và phân quyền các API mà script có thể gọi.
- Notification payload phải được xử lý như dữ liệu, không phải HTML hoặc code.

Không đưa title/body từ nguồn không tin cậy vào HTML của trang. Notification API hiển thị text theo cơ chế của nền tảng, nhưng khi ứng dụng render lại payload trong DOM, phải áp dụng quy tắc xử lý DOM tương ứng.

## 15. Trạng thái granted không bảo đảm thông báo xuất hiện

Ngay cả khi:

~~~js
Notification.permission === "granted"
~~~

notification vẫn có thể không xuất hiện như mong đợi vì:

- Browser hoặc hệ điều hành đã tắt notification của ứng dụng/browser.
- Focus Assist, Do Not Disturb hoặc chế độ tập trung đang bật.
- Người dùng đang dùng chế độ tiết kiệm pin hoặc giới hạn hoạt động nền.
- Browser đang chạy trong môi trường không hỗ trợ kiểu notification đó.
- Notification bị thay thế do cùng tag hoặc bị hệ điều hành nhóm lại.
- Trang/service worker gặp lỗi khi tạo notification.
- Người dùng đã thay đổi cài đặt sau lần kiểm tra trước.

Ứng dụng nên cung cấp trạng thái “đã bật quyền” và trạng thái “đã đăng ký nhận cập nhật” một cách riêng biệt. Không tuyên bố chắc chắn người dùng đã nhìn thấy notification chỉ vì API trả về thành công.

## 16. Quiet UI, permission abuse và cách xin quyền có trách nhiệm

Browser có thể dùng quiet permission UI, tự động giảm prompt hoặc chặn lời gọi xin quyền nếu website có hành vi gây phiền. Một số browser có thể tự reset quyền của site ít hoạt động.

Để tránh làm giảm trust:

- Chỉ xin quyền sau khi người dùng hiểu giá trị.
- Nói rõ loại thông báo và tần suất.
- Không gắn việc xin quyền với nút không liên quan.
- Không lặp prompt sau khi denied.
- Có cách tắt thông báo dễ tìm trong ứng dụng.
- Tôn trọng unsubscribe và preference của từng loại notification.
- Không gửi notification quảng cáo nếu người dùng chỉ đăng ký cập nhật giao dịch.
- Không tạo nhiều notification giống nhau để gây chú ý.

Permission prompt là quyết định của người dùng, không phải một bước bắt buộc để hoàn tất tác vụ không liên quan.

## 17. Quản lý preference và unsubscribe trong ứng dụng

Browser permission cho biết origin có được phép hiển thị notification hay không. Nó không biểu diễn đầy đủ preference nghiệp vụ như người dùng muốn nhận loại thông báo nào.

Nên tách hai lớp:

| Lớp | Ví dụ trạng thái |
| --- | --- |
| Browser permission | default, granted, denied. |
| App preference | đơn hàng bật, marketing tắt, nhắc lịch bật. |
| Push subscription | đã đăng ký endpoint, chưa đăng ký, subscription hết hiệu lực. |
| Device/OS delivery | browser/OS có thể hiển thị hoặc đang tắt notification. |

Cung cấp trang cài đặt trong ứng dụng để bật/tắt từng nhóm thông báo. Nếu user tắt notification ở app, ngừng gửi push tương ứng và cập nhật backend. Nếu permission bị thu hồi ở browser, không tiếp tục cố gửi như thể thiết bị vẫn nhận được.

## 18. Hỗ trợ browser và graceful fallback

Không phải mọi browser đều hỗ trợ cùng tập API hoặc cùng cách hiển thị. Cần kiểm tra:

- Notification có tồn tại trong window không.
- Trang có phải secure context không.
- requestPermission có hoạt động trong top-level context không.
- Permissions API có hỗ trợ descriptor notifications không.
- Service worker và showNotification có được hỗ trợ không.
- PushManager và Push API có khả dụng không.
- Hệ điều hành/browser có cho phép notification delivery không.

Fallback có thể là:

- Badge hoặc banner trong ứng dụng.
- Inbox notification nội bộ.
- Email hoặc kênh khác đã được người dùng đăng ký.
- Polling khi trang đang mở, nếu phù hợp tải hệ thống.

Không làm mất chức năng cốt lõi khi người dùng từ chối notification. Không yêu cầu họ đổi browser chỉ để tiếp tục dùng ứng dụng nếu có phương án thay thế hợp lý.

## 19. Ví dụ hoàn chỉnh: nút bật thông báo

HTML:

~~~html
<button id="enable-notifications" type="button">
  Bật thông báo
</button>
<p id="permission-state" role="status" aria-live="polite"></p>
~~~

JavaScript:

~~~js
const enableButton = document.querySelector("#enable-notifications");
const stateText = document.querySelector("#permission-state");

async function refreshPermissionUI() {
  if (!("Notification" in window)) {
    stateText.textContent = "Browser không hỗ trợ thông báo.";
    enableButton.disabled = true;
    return;
  }

  if (!window.isSecureContext) {
    stateText.textContent = "Hãy mở ứng dụng qua HTTPS.";
    enableButton.disabled = true;
    return;
  }

  const permission = Notification.permission;

  if (permission === "granted") {
    stateText.textContent = "Thông báo đã được cho phép.";
    enableButton.textContent = "Kiểm tra thông báo";
  } else if (permission === "denied") {
    stateText.textContent = "Quyền bị chặn trong cài đặt browser.";
    enableButton.disabled = true;
  } else {
    stateText.textContent = "Bạn chưa bật thông báo.";
  }
}

enableButton.addEventListener("click", async () => {
  if (!("Notification" in window) || !window.isSecureContext) {
    return;
  }

  if (Notification.permission === "default") {
    await Notification.requestPermission();
  }

  await refreshPermissionUI();

  if (Notification.permission === "granted") {
    try {
      new Notification("Thông báo đã sẵn sàng", {
        body: "Bạn có thể quản lý loại thông báo trong phần cài đặt.",
        icon: "/icons/notification.png",
        tag: "permission-confirmation"
      });
    } catch {
      stateText.textContent =
        "Quyền đã được cấp nhưng browser không hiển thị được thông báo này.";
    }
  }
});

refreshPermissionUI();
~~~

Trong sản phẩm thật, nên chỉ hiển thị notification thử nghiệm sau khi người dùng hiểu nút sẽ làm gì. Cũng cần xử lý permission thay đổi khi trang còn mở, chẳng hạn bằng Permissions API nếu browser hỗ trợ.

## 20. Debug Notifications API

Khi notification không hiển thị:

1. Mở DevTools Console và kiểm tra Notification có tồn tại không.
2. Kiểm tra window.isSecureContext.
3. Đọc Notification.permission.
4. Nếu cần, truy vấn navigator.permissions.query({name: "notifications"}) và bắt lỗi unsupported.
5. Kiểm tra browser có hiển thị permission prompt hay đã dùng quiet UI.
6. Kiểm tra site settings của origin hiện tại.
7. Kiểm tra cài đặt notification của browser trong hệ điều hành.
8. Nếu dùng service worker, kiểm tra registration, scope và trạng thái active.
9. Kiểm tra lỗi từ showNotification hoặc notification event.
10. Nếu dùng Push API, kiểm tra subscription và backend delivery riêng.
11. Xem notification có bị tag thay thế hoặc bị hệ điều hành nhóm lại không.
12. Thử trên browser/OS khác để xác định giới hạn nền tảng.

### 20.1. Phân biệt các lớp lỗi

| Hiện tượng | Nơi cần kiểm tra |
| --- | --- |
| Không có API | Browser support và secure context. |
| Permission là default | Chưa có quyết định hoặc prompt chưa được chấp nhận. |
| Permission là denied | Site settings/browser permission. |
| showNotification reject | Service worker, permission và API support. |
| Push không tới | Subscription, VAPID, backend và Push service. |
| API báo granted nhưng không thấy banner | OS settings, focus mode, browser notification center và UI policy. |

Đừng debug push delivery bằng cách chỉ gọi new Notification trong page. Hai đường hiển thị có vòng đời và điều kiện khác nhau.

## 21. Thực hành A — Quan sát permission states

Trên một trang HTTPS do bạn kiểm soát, mở Console:

~~~js
console.log({
  supported: "Notification" in window,
  secureContext: window.isSecureContext,
  permission: "Notification" in window
    ? Notification.permission
    : "unsupported"
});
~~~

Nếu Permissions API hỗ trợ:

~~~js
navigator.permissions.query({ name: "notifications" })
  .then((status) => console.log(status.state))
  .catch((error) => console.log("Không hỗ trợ descriptor:", error.name));
~~~

So sánh trạng thái khi chưa quyết định, sau khi cấp quyền và sau khi thu hồi quyền trong site settings. Ghi nhận sự khác biệt giữa default và prompt.

## 22. Thực hành B — Yêu cầu quyền bằng user gesture

Tạo nút “Bật thông báo”. Gắn Notification.requestPermission vào click handler. Thử các trường hợp:

1. Người dùng bấm và chọn Allow.
2. Người dùng chọn Block.
3. Người dùng đóng prompt hoặc để browser xử lý theo mặc định.
4. Tải lại trang và kiểm tra trạng thái.
5. Thu hồi quyền trong cài đặt rồi quay lại trang.

Quan sát Console và giao diện. Không gọi requestPermission tự động khi page load và không lặp prompt sau khi người dùng từ chối.

## 23. Thực hành C — Foreground và service worker notification

Trước hết, khi permission granted, tạo notification foreground bằng Notification constructor trên browser hỗ trợ.

Sau đó đăng ký service worker trên HTTPS và dùng registration.showNotification(). So sánh:

- Notification foreground gắn với trang đang mở.
- Service worker notification có thể được tạo từ worker context theo API hỗ trợ.
- Notification click trong service worker được xử lý bằng notificationclick event.
- Permission vẫn là điều kiện cần ở cả hai đường.

Không dùng dữ liệu người dùng thật trong bài lab. Dùng nội dung công khai và route nội bộ cố định.

## 24. Thực hành D — Phân biệt notification với push subscription

Trong môi trường staging:

1. Xin notification permission sau thao tác click.
2. Đăng ký service worker.
3. Kiểm tra PushManager có tồn tại không.
4. Tạo subscription với userVisibleOnly và VAPID public key test.
5. Gửi subscription tới backend staging qua HTTPS.
6. Gửi một push test và quan sát push event trong service worker.
7. Gọi showNotification từ worker.
8. Thử unsubscribe và xóa subscription khỏi backend.

Ghi nhận lỗi permission, subscription và delivery ở từng lớp. Không đưa endpoint subscription hoặc khóa riêng vào báo cáo công khai.

## 25. Checklist review Notifications

- [ ] Kiểm tra Notification API support trước khi dùng.
- [ ] Chỉ yêu cầu notification permission trong secure context.
- [ ] Xin quyền sau hành động rõ ràng của người dùng.
- [ ] Giải thích loại notification và lợi ích trước khi mở prompt.
- [ ] Không gọi requestPermission tự động khi page load.
- [ ] Không lặp prompt sau khi denied hoặc default.
- [ ] Phân biệt Notification.permission default với Permissions API prompt.
- [ ] Bắt lỗi khi query Permissions API descriptor không được hỗ trợ.
- [ ] Xử lý permission thay đổi hoặc bị thu hồi.
- [ ] Chỉ tạo foreground notification khi permission granted.
- [ ] Dùng serviceWorkerRegistration.showNotification cho luồng persistent/background phù hợp.
- [ ] Phân biệt Notification constructor với service worker notification.
- [ ] Không coi notification permission là authentication hoặc authorization.
- [ ] Tách notification permission, app preference và push subscription.
- [ ] Bảo vệ PushSubscription endpoint và liên kết subscription với tài khoản đã xác thực.
- [ ] Có luồng unsubscribe khi người dùng tắt hoặc đăng xuất.
- [ ] Kiểm tra Permissions Policy và giới hạn iframe nếu browser hỗ trợ.
- [ ] Không gửi OTP, token, session ID hoặc dữ liệu nhạy cảm trong notification.
- [ ] Validate URL/deep link khi notification được bấm.
- [ ] Không tin payload push; kiểm tra schema và trạng thái nghiệp vụ.
- [ ] Không dựa vào notification click để xác nhận giao dịch.
- [ ] Có fallback in-app khi browser/OS không hỗ trợ hoặc người dùng từ chối.
- [ ] Debug riêng permission, service worker, push delivery và OS notification settings.
- [ ] Tôn trọng preference và unsubscribe của người dùng.

## 26. Những ngộ nhận thường gặp

| Nhận định | Đánh giá | Giải thích |
| --- | --- | --- |
| “Mở website là có thể gửi notification.” | **Sai** | Cần API support, secure context và permission phù hợp. |
| “Notification.permission mặc định là prompt.” | **Sai** | Giá trị của API này là default; Permissions API có thể dùng prompt. |
| “Gọi requestPermission khi page load là cách tốt nhất.” | **Sai** | Nên xin sau hành động có ý nghĩa của người dùng. |
| “Permissions API query sẽ hiển thị prompt.” | **Sai** | Query chỉ đọc trạng thái; requestPermission mới yêu cầu quyền. |
| “Granted bảo đảm notification sẽ xuất hiện trên màn hình.” | **Sai** | OS/browser có thể tắt banner hoặc nhóm/ẩn notification. |
| “Từ chối một lần thì có thể prompt lại liên tục.” | **Sai** | Browser có thể chặn prompt; người dùng cần tự đổi site settings. |
| “Cấp notification permission tự tạo push subscription.” | **Sai** | PushManager subscription là bước riêng. |
| “new Notification() dùng được trong mọi service worker.” | **Sai** | Worker dùng registration.showNotification() theo API hỗ trợ. |
| “Iframe có thể xin quyền giống top-level page.” | **Sai** | Browser có thể hạn chế permission request từ iframe, nhất là cross-origin. |
| “Permissions-Policy notifications cấp quyền cho widget.” | **Sai** | Policy chỉ giới hạn tính năng; user permission vẫn cần thiết. |
| “Notification là kênh an toàn để gửi OTP hoặc token.” | **Sai** | Nội dung có thể lộ trên lock screen hoặc thiết bị dùng chung. |
| “Notification click chứng minh user đã xác nhận giao dịch.” | **Sai** | Click chỉ là tương tác; server và UI vẫn cần xác thực nghiệp vụ. |
| “XSS không thể tạo notification nếu permission đã được cấp từ trước.” | **Sai** | Script chạy cùng origin có thể sử dụng quyền của origin. |
| “Push API và Notifications API là một.” | **Sai** | Push nhận message nền; Notifications hiển thị nội dung cho người dùng. |
| “Nếu page không thấy notification thì chắc chắn permission bị denied.” | **Sai** | Có thể do OS, browser, service worker, tag hoặc push delivery. |

## 27. Tổng kết

Notifications API cho phép website hiển thị thông báo ngoài trang, nhưng cần permission do browser và người dùng quản lý. Ứng dụng nên kiểm tra secure context và browser support, giải thích lợi ích rồi yêu cầu quyền trong một hành động rõ ràng. Trạng thái default, granted và denied phải được xử lý khác nhau; không lặp prompt khi người dùng đã từ chối.

Notifications API có thể hiển thị thông báo từ trang đang mở; service worker có thể dùng showNotification cho luồng persistent/background. Push API là bước riêng để nhận message từ push service và cần subscription được quản lý an toàn. Permission đã cấp không bảo đảm OS sẽ hiển thị banner, và cũng không thay authentication, authorization hoặc kiểm soát quyền riêng tư.

Ba nguyên tắc cần nhớ:

1. **Xin quyền có trách nhiệm:** chỉ hỏi khi người dùng hiểu tính năng, sau một thao tác rõ ràng; tôn trọng denied và thay đổi permission.
2. **Tách permission khỏi push và preference:** browser permission, cài đặt notification trong app, push subscription và khả năng hiển thị của OS là các trạng thái riêng.
3. **Bảo vệ nội dung và hành động:** không gửi secret hoặc dữ liệu nhạy cảm, kiểm tra deep link, validate payload và xác minh nghiệp vụ khi người dùng mở ứng dụng.

Khi review chức năng notification, hãy hỏi: **browser có hỗ trợ và trang có secure context không, người dùng đã chủ động cấp quyền chưa, trạng thái permission hiện tại là gì, thông báo được tạo từ page hay service worker, push subscription còn hợp lệ không, và nội dung có làm lộ dữ liệu hoặc dẫn người dùng tới đích không tin cậy không?** Trả lời rõ các câu hỏi này giúp sử dụng Notifications API đúng mục đích và tôn trọng quyền kiểm soát của người dùng.
