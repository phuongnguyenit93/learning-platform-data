# Background script: service worker chạy nền trong extension Manifest V3

Trong browser extension, background script xử lý các sự kiện không phụ thuộc vào việc người dùng đang mở popup hay một trang extension cụ thể. Với Manifest V3, Chrome dùng **extension service worker** làm background context. Service worker được browser khởi động khi có sự kiện cần xử lý và có thể bị dừng khi không còn hoạt động; nó không phải một tiến trình chạy liên tục.

Khác với background page của Manifest V2, extension service worker không có DOM, không có window và không thể dựa vào biến global để lưu trạng thái lâu dài. Nó đăng ký event listener ở phạm vi top-level, xử lý message, alarm, tab/action và network event phù hợp, rồi lưu trạng thái cần giữ qua lần khởi động vào chrome.storage hoặc IndexedDB.

Bài học thuộc chương **Browser extension**, theo đề bài **Background script**, trong phạm vi **SECURITY_APPLICATION_SECURITY_BROWSER_SECURITY**: phân tích ranh giới bảo mật giữa trình duyệt, origin, cookie và ứng dụng web để hiểu Same-Origin Policy, CORS và các cơ chế cách ly; thực hành phòng vệ XSS, CSRF, clickjacking bằng CSP, Trusted Types, security headers và kiểm chứng hành vi thực tế.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

1. Phân biệt background page kiểu cũ với extension service worker của Manifest V3.
2. Giải thích lifecycle event-driven, cold start và lý do worker có thể bị terminate.
3. Khai báo background service worker trong manifest.
4. Đăng ký event listener đồng bộ ở top-level để browser có thể khôi phục worker.
5. Lưu trạng thái lâu dài bằng chrome.storage hoặc IndexedDB.
6. Dùng chrome.alarms thay cho timer cần tồn tại qua worker restart.
7. Thiết kế message passing an toàn giữa popup, content script và background worker.
8. Xác minh sender, tab, frame, origin và schema của message.
9. Áp dụng permissions, host_permissions và activeTab theo nguyên tắc least privilege.
10. Hiểu khác biệt quyền network giữa extension service worker và content script.
11. Bảo vệ extension khỏi XSS, code injection, dữ liệu không tin cậy và lộ secret.
12. Debug, kiểm thử cold start, alarm, message và storage bằng DevTools.

## 2. Background script trong Manifest V3

Extension thường có nhiều execution context:

| Context | Nhiệm vụ | Đặc điểm bảo mật |
| --- | --- | --- |
| Popup | UI ngắn hạn khi người dùng bấm icon | Có thể đóng bất cứ lúc nào; không dùng làm nơi giữ trạng thái lâu dài. |
| Options page | Cấu hình extension | Extension page có quyền theo manifest; cần bảo vệ form và dữ liệu cấu hình. |
| Content script | Đọc/tương tác DOM trang web | Chạy trong isolated world nhưng chia sẻ DOM với trang; dữ liệu trang là không tin cậy. |
| Background service worker | Điều phối event, message, storage, API và network | Có quyền extension nhưng không có DOM/window; lifecycle do browser quản lý. |
| Offscreen document | Thực hiện một số tác vụ cần DOM khi API cho phép | Là document extension có vòng đời và lý do tạo riêng; không thay background worker tùy tiện. |

### Manifest V2 và Manifest V3

Manifest V2 thường dùng background page hoặc event page. Manifest V3 chuyển background logic của Chrome sang extension service worker.

| Đặc điểm | Background page kiểu cũ | MV3 extension service worker |
| --- | --- | --- |
| Runtime | Page/context tồn tại lâu hơn | Event-driven, có thể dừng và khởi động lại |
| DOM | Background page có DOM | Không có DOM hoặc window |
| Global variables | Có thể tồn tại trong vòng đời page | Chỉ tồn tại trong một worker instance |
| Timer | Timer chạy theo page lifecycle | Không được dựa vào timer để giữ worker sống |
| Persistent state | Có thể dựa vào page state (không nên cho dữ liệu quan trọng) | Dùng storage/IndexedDB |
| Network | Theo quyền extension và browser | Theo quyền extension và service worker APIs |

Không port nguyên xi background page sang MV3. Mã cần được thiết kế để xử lý một event độc lập, đọc trạng thái bền vững khi cần và ghi kết quả trước khi event kết thúc.

## 3. Khai báo background service worker

Manifest V3 khai báo worker trong trường background.service_worker:

```json
{
  "manifest_version": 3,
  "name": "Browser Security Lab",
  "version": "1.0.0",
  "description": "Extension minh họa background service worker",
  "permissions": [
    "storage",
    "alarms",
    "activeTab",
    "scripting"
  ],
  "host_permissions": [
    "https://api.example.test/*"
  ],
  "background": {
    "service_worker": "service-worker.js"
  },
  "action": {
    "default_title": "Kiểm tra trang hiện tại"
  },
  "content_scripts": [
    {
      "matches": [
        "https://app.example.test/*"
      ],
      "js": [
        "content.js"
      ],
      "run_at": "document_idle"
    }
  ]
}
```

Đây là manifest tối giản để học. Quyền thật của extension phải được giới hạn theo tính năng cần có; không sao chép host permission rộng vào production.

### service_worker path

- Đường dẫn tương đối tới JavaScript file trong package extension.
- File phải được đóng gói cùng extension.
- Không tải file worker từ remote host.
- Worker có thể dùng JavaScript module nếu khai báo cấu hình module được browser mục tiêu hỗ trợ.
- Không dùng dynamic import hoặc cơ chế tải code từ xa như một cách cập nhật logic extension.

Ví dụ khai báo module trong Chrome:

```json
{
  "manifest_version": 3,
  "name": "Module Worker Example",
  "version": "1.0.0",
  "background": {
    "service_worker": "service-worker.js",
    "type": "module"
  }
}
```

Với module worker, dùng static import từ file đã đóng gói. Nếu cần hỗ trợ nhiều browser, kiểm tra manifest schema và khả năng module service worker của từng browser; không giả định mọi API extension hoàn toàn giống Chrome.

## 4. Lifecycle: worker được đánh thức theo event

Extension service worker không chạy liên tục. Browser có thể khởi động worker khi:

- Extension được cài đặt, cập nhật hoặc browser khởi động.
- Người dùng bấm extension action.
- Popup hoặc extension page gửi message.
- Content script gửi message.
- Alarm tới hạn.
- Một extension API event khác được đăng ký xảy ra.

Sau khi xử lý xong, worker có thể bị terminate. Chrome có các giới hạn lifecycle theo phiên bản và loại hoạt động; trong cấu hình thông thường, worker có thể bị dừng sau một khoảng idle khoảng 30 giây, và các event/API call kéo dài cũng có giới hạn riêng. Hãy thiết kế theo nguyên tắc worker có thể dừng bất kỳ lúc nào sau khi event hoàn tất, thay vì phụ thuộc một mốc thời gian cố định.

### Cold start

Cold start là khi browser tạo một instance service worker mới để xử lý event. Toàn bộ biến global được khởi tạo lại:

```js
let requestCount = 0;

chrome.runtime.onMessage.addListener((message) => {
  requestCount += 1;
  console.log('Requests in this worker instance:', requestCount);
});
```

requestCount chỉ phản ánh số message trong instance hiện tại. Khi worker bị terminate và khởi động lại, nó trở về 0. Không dùng global variable để lưu user preference, token, job progress hoặc trạng thái cần tồn tại qua restart.

### Event listener phải được đăng ký ở top-level

Đăng ký listener ngay khi worker được evaluate:

```js
chrome.runtime.onInstalled.addListener((details) => {
  console.log('Extension installed or updated:', details.reason);
});

chrome.runtime.onStartup.addListener(() => {
  console.log('Browser started');
});

chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === 'refresh-status') {
    void refreshStatus();
  }
});
```

Không đợi một Promise, fetch hoặc callback bất đồng bộ rồi mới đăng ký listener. Nếu listener được đăng ký trễ sau khi worker đã khởi động để xử lý event, browser có thể không tìm thấy handler cho event đó.

### Không giữ worker sống bằng vòng lặp

Tránh:

- setInterval để polling vô hạn.
- Vòng lặp chạy nền chỉ để giữ extension hoạt động.
- Promise không bao giờ settle.
- Port/message connection được giữ chỉ để chống terminate.
- Timer giả định worker sẽ tồn tại tới một thời điểm cụ thể.

Hãy xử lý event, lưu tiến độ và kết thúc. Nếu cần công việc định kỳ, dùng chrome.alarms. Nếu tác vụ dài, chia thành bước có thể tiếp tục sau khi worker khởi động lại.

## 5. Đăng ký event và khởi tạo extension

### onInstalled

onInstalled được phát khi extension được cài, cập nhật hoặc browser cập nhật. details.reason giúp phân biệt:

- install: extension mới được cài.
- update: extension được cập nhật.
- chrome_update: browser được cập nhật.
- shared_module_update: trường hợp module chia sẻ được cập nhật trong mô hình liên quan.

Ví dụ tạo alarm khi cài/cập nhật:

```js
const STATUS_ALARM = 'refresh-status';

chrome.runtime.onInstalled.addListener((details) => {
  if (details.reason === 'install') {
    chrome.storage.local.set({
      preferences: {
        enabled: true
      }
    });
  }

  ensureStatusAlarm();
});

function ensureStatusAlarm() {
  chrome.alarms.get(STATUS_ALARM, (existing) => {
    if (!existing) {
      chrome.alarms.create(STATUS_ALARM, {
        periodInMinutes: 30
      });
    }
  });
}
```

Ví dụ dùng callback để minh họa cách tương thích với API event. Trong code thực tế, kiểm tra API signature và Promise support theo browser/version mà extension hỗ trợ.

### onStartup

onStartup được phát khi profile/browser khởi động. Có thể dùng để kiểm tra lại alarm hoặc đồng bộ metadata cần thiết:

```js
chrome.runtime.onStartup.addListener(() => {
  ensureStatusAlarm();
});
```

Không giả định mọi alarm chắc chắn còn nguyên qua mọi lần restart hoặc thay đổi version/browser. Kiểm tra alarm hiện có và tạo lại nếu cần.

### Khởi tạo idempotent

Initialization nên idempotent: gọi nhiều lần không tạo nhiều alarm, listener trùng hoặc dữ liệu mặc định bị ghi đè.

- Dùng tên alarm cố định.
- Kiểm tra trạng thái trước khi tạo.
- Chỉ tạo default preference khi chưa có.
- Không xóa user settings trong onStartup.
- Xử lý update/migration theo version lưu trong storage.

## 6. Lưu trạng thái qua worker restart

Background service worker không có localStorage và không có window. Dùng extension storage APIs hoặc IndexedDB tùy loại dữ liệu.

### chrome.storage.local

Lưu dữ liệu cục bộ trong profile:

```js
async function savePreferences(preferences) {
  await chrome.storage.local.set({
    preferences
  });
}

async function loadPreferences() {
  const result = await chrome.storage.local.get('preferences');
  return result.preferences ?? {
    enabled: true
  };
}
```

Phù hợp với cấu hình, trạng thái extension và dữ liệu cần tồn tại qua worker restart. Storage này không phải secret vault; không lưu password, session cookie hoặc access token nếu không có thiết kế bảo vệ rõ ràng.

### chrome.storage.session

storage.session giữ dữ liệu trong bộ nhớ của browser session và tồn tại qua worker restart trong session đó. Nó phù hợp với trạng thái tạm thời không cần đồng bộ xuống disk, nhưng bị xóa khi browser session/extension lifecycle tương ứng kết thúc.

Mặc định storage.session không được content scripts truy cập; không thay đổi access level nếu không có nhu cầu cụ thể.

### chrome.storage.sync

storage.sync có thể đồng bộ dữ liệu cấu hình giữa các browser profile đã bật sync và có quota/giới hạn kích thước. Không dùng cho dữ liệu lớn, dữ liệu nhạy cảm hoặc trạng thái cần consistency mạnh.

### chrome.storage.managed

storage.managed chứa policy do quản trị viên tổ chức cung cấp cho extension enterprise. Đây là nguồn cấu hình do admin kiểm soát; extension không thể tùy ý ghi dữ liệu vào đó.

### So sánh storage

| API | Tồn tại qua worker restart | Qua browser restart | Mục đích |
| --- | --- | --- | --- |
| Biến global | Không | Không | Cache tạm trong instance. |
| storage.session | Có trong browser session | Không | State tạm theo session. |
| storage.local | Có | Có | Settings và state cục bộ. |
| storage.sync | Có | Có, theo sync/account | Settings nhỏ cần đồng bộ. |
| storage.managed | Theo policy admin | Theo policy admin | Cấu hình enterprise chỉ đọc. |
| IndexedDB | Có | Có | Dữ liệu có cấu trúc hoặc lượng lớn hơn. |

### Giới hạn truy cập storage

Extension storage có thể được dùng từ nhiều context. Với dữ liệu chỉ background/extension page cần truy cập, giới hạn access level nếu API/browser hỗ trợ:

```js
chrome.storage.local.setAccessLevel({
  accessLevel: 'TRUSTED_CONTEXTS'
});
```

Thực hiện cấu hình này sớm trong lifecycle và kiểm tra browser support. Không mở storage cho content script nếu không cần; content script tương tác với trang web có thể xử lý dữ liệu không tin cậy.

### Storage thay đổi

Có thể lắng nghe thay đổi:

```js
chrome.storage.onChanged.addListener((changes, areaName) => {
  if (areaName === 'local' && changes.preferences) {
    console.log('Preferences changed');
  }
});
```

Chỉ log metadata cần thiết, không log giá trị chứa secret hoặc dữ liệu cá nhân.

### IndexedDB

IndexedDB có thể dùng từ service worker để lưu dữ liệu có cấu trúc, queue công việc hoặc cache dữ liệu do extension quản lý. Nó bất đồng bộ và phù hợp hơn cho dữ liệu lớn/phức tạp so với lưu một object nhỏ trong storage.local.

IndexedDB không tự giải quyết xung đột giữa các context. Cần transaction, schema version và xử lý migration phù hợp.

## 7. Alarm thay cho timer nền

Service worker có thể bị dừng, vì vậy setInterval không phải scheduler đáng tin cậy:

```js
// Không dùng làm lịch nền lâu dài:
setInterval(refreshStatus, 30 * 60 * 1000);
```

Dùng chrome.alarms:

```js
const STATUS_ALARM = 'refresh-status';

function scheduleStatusRefresh() {
  chrome.alarms.create(STATUS_ALARM, {
    delayInMinutes: 1,
    periodInMinutes: 30
  });
}

chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name !== STATUS_ALARM) return;

  void refreshStatus().catch((error) => {
    console.error('Status refresh failed:', error);
  });
});
```

Alarm đánh thức service worker khi tới hạn và phù hợp với công việc định kỳ. Thời điểm chạy có thể bị trì hoãn do browser/device state; không dùng alarm làm đồng hồ chính xác cho giao dịch hoặc bảo mật.

### Không dùng alarm cho deadline bảo mật duy nhất

Nếu một token/session hết hạn, server phải kiểm tra expiry khi request tới. Không dựa vào alarm để revoke đúng giây. Alarm chỉ hỗ trợ housekeeping hoặc đồng bộ trạng thái; server-side expiry là nguồn quyết định.

### Công việc dài cần checkpoint

Nếu tác vụ có nhiều bước:

1. Đọc job state từ storage.
2. Thực hiện một bước có giới hạn.
3. Lưu checkpoint và kết quả.
4. Nếu còn việc, lên alarm/queue bước tiếp theo.
5. Khi worker được đánh thức, tiếp tục từ checkpoint.

Thiết kế thao tác idempotent để worker restart hoặc event được gửi lại không gây gửi trùng request hoặc ghi trùng dữ liệu.

## 8. Message passing giữa các context

Popup, options page, content script và background worker có thể trao đổi message bằng runtime messaging.

| API | Dùng khi |
| --- | --- |
| chrome.runtime.sendMessage | Gửi một message tới listener trong extension. |
| chrome.tabs.sendMessage | Gửi message tới content script trong tab/frame cụ thể. |
| chrome.runtime.onMessage | Nhận message một lần. |
| chrome.runtime.connect | Mở Port để trao đổi nhiều message. |
| chrome.runtime.onConnect | Nhận Port từ context khác. |

Message passing là ranh giới tin cậy quan trọng: content script có thể đọc dữ liệu do trang web điều khiển và gửi lên background. Background có quyền extension rộng hơn, vì vậy phải xác minh mọi message.

### Message schema

Thiết kế message có type rõ ràng và dữ liệu tối thiểu:

```js
{
  type: 'GET_STATUS',
  requestId: 'req-123'
}
```

Không nhận một message tự do rồi thực thi tên API, tên function hoặc code mà sender cung cấp.

### Xác minh sender

Trong onMessage, sender có thể cung cấp:

- sender.id: extension ID của sender.
- sender.url: URL context gửi message.
- sender.origin: origin khi có.
- sender.tab: thông tin tab nếu message đến từ tab.
- sender.frameId: frame gửi message.

Chính sách nên phân biệt extension page và content script:

- Extension page: xác nhận sender.id là extension hiện tại và sender.url thuộc extension origin.
- Content script: xác nhận sender.id, tab/frame phù hợp và sender.url thuộc host được extension hỗ trợ.
- External extension/web page: chỉ nhận nếu có use case rõ, cấu hình externally_connectable và xác minh sender riêng.

Không coi sender.tab.url luôn tồn tại. Không chấp nhận sender.url chỉ vì nó chứa một chuỗi hostname; parse URL và so khớp origin chính xác.

### Listener bất đồng bộ

Ví dụ dùng sendResponse callback:

```js
chrome.runtime.onMessage.addListener(
  (message, sender, sendResponse) => {
    if (message?.type !== 'GET_STATUS') {
      return;
    }

    if (sender.id !== chrome.runtime.id) {
      return;
    }

    readStatus()
      .then((status) => {
        sendResponse({
          ok: true,
          status
        });
      })
      .catch(() => {
        sendResponse({
          ok: false,
          error: 'STATUS_UNAVAILABLE'
        });
      });

    return true;
  }
);
```

return true giữ message response channel mở để gọi sendResponse sau khi Promise hoàn tất trong các browser/API implementation dùng callback semantics. Một số browser hỗ trợ trả Promise trực tiếp; chọn cách theo browser target và tài liệu API tương ứng.

### Validate payload

Ví dụ kiểm tra message từ content script:

```js
function isAllowedContentSender(sender) {
  if (sender.id !== chrome.runtime.id) return false;
  if (!sender.tab || sender.frameId !== 0) return false;
  if (!sender.url) return false;

  try {
    const url = new URL(sender.url);
    return url.origin === 'https://app.example.test';
  } catch {
    return false;
  }
}

function isPageStatusMessage(message) {
  return message !== null &&
    typeof message === 'object' &&
    message.type === 'GET_STATUS';
}
```

Sau khi validate sender, vẫn phải validate từng field và giới hạn kích thước message. Sender hợp lệ không có nghĩa payload đáng tin; nội dung DOM mà content script đọc được vẫn do website kiểm soát.

## 9. Ví dụ background worker tối thiểu

File service-worker.js:

```js
const STATUS_ALARM = 'refresh-status';
const ALLOWED_PAGE_ORIGIN = 'https://app.example.test';

chrome.runtime.onInstalled.addListener(() => {
  ensureStatusAlarm();
});

chrome.runtime.onStartup.addListener(() => {
  ensureStatusAlarm();
});

chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === STATUS_ALARM) {
    refreshStatus().catch(() => {
      console.error('Status refresh failed');
    });
  }
});

chrome.runtime.onMessage.addListener(
  (message, sender, sendResponse) => {
    if (!isAllowedContentSender(sender)) return;
    if (!isPageStatusMessage(message)) return;

    readStatus()
      .then((status) => {
        sendResponse({ ok: true, status });
      })
      .catch(() => {
        sendResponse({
          ok: false,
          error: 'STATUS_UNAVAILABLE'
        });
      });

    return true;
  }
);

chrome.action.onClicked.addListener((tab) => {
  if (!tab.id) return;

  chrome.tabs.sendMessage(tab.id, {
    type: 'RUN_PAGE_CHECK'
  }).catch(() => {
    // Tab may not have a content script or may have navigated.
  });
});

function ensureStatusAlarm() {
  chrome.alarms.get(STATUS_ALARM, (alarm) => {
    if (!alarm) {
      chrome.alarms.create(STATUS_ALARM, {
        periodInMinutes: 30
      });
    }
  });
}

function isAllowedContentSender(sender) {
  if (sender.id !== chrome.runtime.id) return false;
  if (!sender.tab || sender.frameId !== 0 || !sender.url) {
    return false;
  }

  try {
    return new URL(sender.url).origin === ALLOWED_PAGE_ORIGIN;
  } catch {
    return false;
  }
}

function isPageStatusMessage(message) {
  return message !== null &&
    typeof message === 'object' &&
    message.type === 'GET_STATUS';
}

async function readStatus() {
  const result = await chrome.storage.local.get('lastStatus');
  return result.lastStatus ?? null;
}

async function refreshStatus() {
  // Placeholder: fetch only data allowed by the extension's host permissions.
  const status = {
    checkedAt: Date.now(),
    state: 'ok'
  };

  await chrome.storage.local.set({
    lastStatus: status
  });
}
```

Ví dụ này minh họa cấu trúc event-driven và kiểm tra sender. Production cần bổ sung error handling, schema validation, rate limiting phù hợp, kiểm soát dữ liệu và chính sách quyền cụ thể.

### Content script tương ứng

```js
chrome.runtime.onMessage.addListener((message) => {
  if (message?.type !== 'RUN_PAGE_CHECK') return;

  chrome.runtime.sendMessage({
    type: 'GET_STATUS'
  }).then((response) => {
    console.log('Background response:', response);
  }).catch(() => {
    console.warn('Background worker unavailable');
  });
});
```

Ví dụ này chỉ gửi một message không kèm dữ liệu trang vì background chỉ cần đọc trạng thái đã lưu. Nếu tính năng cần title hoặc URL, mở rộng schema có kiểm soát, giới hạn độ dài và chỉ gửi field thực sự cần; không để content script gửi URL tùy ý để background fetch mà không có allowlist.

## 10. Quyền extension và host permissions

Background worker có thể truy cập API theo permissions trong manifest. Mỗi permission làm tăng quyền của extension và tác động đến cảnh báo cài đặt hoặc quyền riêng tư.

### permissions

Một số permission thường gặp:

| Permission | Dùng cho |
| --- | --- |
| storage | chrome.storage |
| alarms | Lập lịch event bằng alarm |
| tabs | Đọc một số thuộc tính nhạy cảm của tab như URL/title/favIconUrl; không cần chỉ để gửi message tới tab |
| activeTab | Quyền tạm thời với tab sau user gesture phù hợp |
| scripting | Inject script/CSS theo quyền tab/host |
| notifications | Hiển thị notification |
| contextMenus | Tạo context menu |
| webNavigation | Quan sát navigation event theo permission |
| declarativeNetRequest | Rule network request theo API và quyền được khai báo |

Chỉ yêu cầu permission khi tính năng cần nó. Không thêm tabs, history, webRequest hoặc quyền rộng chỉ để tiện debug.

### host_permissions

Host permissions cấp quyền extension truy cập origin/host cụ thể qua API extension phù hợp và cross-origin request trong extension context:

```json
{
  "host_permissions": [
    "https://api.example.test/*"
  ]
}
```

Không dùng <all_urls> nếu chỉ cần một API host. Với Chrome, phần path trong host permission match pattern không giới hạn quyền theo path; quyền được cấp theo scheme/host. Nếu chỉ muốn gọi một số endpoint, vẫn phải kiểm tra origin, path và method bằng allowlist trong code trước khi fetch.

### activeTab và scripting

Nếu extension chỉ cần thao tác trên tab sau khi người dùng bấm icon, activeTab kết hợp scripting có thể giảm quyền thường trực:

```js
chrome.action.onClicked.addListener(async (tab) => {
  if (!tab.id) return;

  await chrome.scripting.executeScript({
    target: {
      tabId: tab.id
    },
    files: ['page-check.js']
  });
});
```

Kiểm tra quyền tạm thời, frame target và trang bị hạn chế như browser internal pages. Không cố inject vào chrome://, Chrome Web Store hoặc origin mà browser cấm.

### Optional permissions

Với tính năng chỉ một số người dùng cần, cân nhắc optional_permissions và optional_host_permissions rồi xin quyền khi người dùng chủ động bật tính năng. Giải thích rõ extension cần truy cập website nào và vì sao.

## 11. Background fetch, CORS và ranh giới origin

Extension service worker và content script có quyền network khác nhau:

- Content script chạy trong context của trang và chịu các giới hạn web platform của trang đối với request cross-origin.
- Extension service worker có thể thực hiện request tới host đã được khai báo trong host_permissions theo quyền extension/browser.
- Host permission không tự động cấp quyền cho website thường hoặc content script.
- API server vẫn cần authentication, authorization, rate limit và kiểm tra dữ liệu.

Ví dụ fetch từ extension service worker:

```js
async function fetchPublicStatus() {
  const response = await fetch(
    'https://api.example.test/v1/status',
    {
      method: 'GET',
      credentials: 'omit',
      headers: {
        'Accept': 'application/json'
      }
    }
  );

  if (!response.ok) {
    throw new Error('STATUS_REQUEST_FAILED');
  }

  return response.json();
}
```

Host https://api.example.test/* cần nằm trong host_permissions phù hợp. credentials: omit tránh gửi cookie ambient của API trong request này. Nếu API cần credential, thiết kế authentication riêng và không hardcode secret trong extension package.

### CORS không phải authorization

CORS là cơ chế browser điều khiển việc JavaScript đọc response cross-origin. Nó không chứng minh request được phép về mặt nghiệp vụ. Server vẫn phải xác thực người dùng và kiểm tra quyền trên từng resource.

Extension có host permission có thể có network capability mà page script không có. Vì vậy, không biến background worker thành open proxy: message từ content script không được chỉ định URL tùy ý để worker fetch thay nó.

### URL allowlist

Nếu worker cần gọi nhiều endpoint, parse URL và kiểm tra origin/path/method:

```js
function isAllowedApiUrl(value) {
  try {
    const url = new URL(value);
    return url.origin === 'https://api.example.test' &&
      url.pathname.startsWith('/v1/public/');
  } catch {
    return false;
  }
}
```

Không kiểm tra bằng substring như includes('example.test'); hostname giả có thể chứa chuỗi đó. Kiểm tra cả origin, path, method và redirect behavior theo yêu cầu. Nếu API không cần redirect, từ chối redirect hoặc kiểm tra URL cuối theo policy.

## 12. Content script, isolated world và dữ liệu không tin cậy

Content script thường chạy trong isolated world: JavaScript global scope tách khỏi page script, nhưng cả hai cùng truy cập DOM. Isolated world giúp giảm va chạm biến và một số kiểu can thiệp trực tiếp, nhưng không làm DOM trở thành dữ liệu đáng tin.

### Những gì page có thể kiểm soát

- Nội dung text/attribute trong DOM.
- Form field và URL.
- Event phát sinh từ DOM.
- Các node mà content script đọc.
- Thông tin được page script ghi vào DOM hoặc custom event.

Nếu content script đọc nội dung rồi gửi cho background, background phải coi đó là input không tin cậy.

### Không dùng DOM làm kênh bí mật

Không đặt API secret, extension token hoặc dữ liệu privileged vào DOM với giả định page script không đọc được. Page script có thể quan sát/chỉnh DOM và kích hoạt event.

### Main world injection

Một số extension cần tương tác với page JavaScript world. Khi inject vào MAIN world, code chạy cùng môi trường với script của trang và chịu rủi ro bị page script can thiệp. Chỉ dùng khi cần; giữ logic privileged trong background và trao đổi qua message schema hẹp.

### Không đưa page data vào HTML sink

Không ghép text lấy từ trang vào innerHTML. Dùng textContent, createElement và API an toàn. Tránh eval, Function constructor và inline script.

## 13. Bảo vệ message và quyền đặc biệt

Background worker là context có quyền cao; lỗi xác thực message có thể biến thành confused deputy — extension dùng quyền của nó thay mặt một sender không đáng tin.

### Các kiểm soát cần có

1. Xác minh sender.id.
2. Xác minh sender.url/origin bằng URL parser và exact allowlist.
3. Giới hạn sender.tab và sender.frameId nếu chức năng chỉ dành cho tab chính.
4. Kiểm tra message type theo allowlist.
5. Validate schema, kiểu dữ liệu, độ dài và enum.
6. Không nhận URL, path, permission hoặc function name tùy ý.
7. Kiểm tra quyền user/session trước hành động nhạy cảm.
8. Giới hạn tốc độ message/action nếu cần.
9. Trả lỗi tổng quát, không tiết lộ internal state.
10. Không log token hoặc nội dung trang nhạy cảm.

### Không tin dữ liệu từ content script

Content script có thể được extension cài vào trang do attacker kiểm soát. Dù sender.id đúng extension, payload có thể chứa HTML, URL, text hoặc event do page attacker tạo ra. Kiểm tra nguồn gửi và kiểm tra dữ liệu là hai bước khác nhau.

### External messaging

Chỉ khai báo externally_connectable khi có tích hợp từ website/extension khác. Giới hạn matches/IDs cụ thể; không mở cho mọi trang. Trong onMessageExternal, xác minh sender.url/id và xác thực request theo protocol riêng.

## 14. Extension security policy và remote code

Manifest V3 giới hạn extension không được tải và thực thi remote hosted code như một cách thay đổi logic. Code thực thi phải nằm trong package extension đã review/phát hành.

Tránh:

- eval() và new Function().
- Script source từ CDN/website bên ngoài.
- Tải JavaScript rồi đưa vào script element.
- Dùng cấu hình từ server để tạo code tùy ý.
- Thực thi nội dung trang web như code extension.

Có thể tải dữ liệu hoặc cấu hình từ server, nhưng dữ liệu không được biến thành mã thực thi. Dùng schema, allowlist và validation.

### Content Security Policy

Extension pages có CSP riêng theo manifest và browser. Giữ policy nghiêm, chỉ cho script đã đóng gói chạy. Không nới policy để cho phép unsafe-eval hoặc remote script nhằm làm thư viện cũ hoạt động; thay thế thư viện hoặc điều chỉnh build.

### Dependency

- Bundle dependency vào package.
- Theo dõi phiên bản và lỗ hổng.
- Giảm dependency trong background.
- Không dùng thư viện không cần thiết có quyền truy cập storage/network.
- Review update và nguồn phát hành.

## 15. Alarm, event và xử lý lỗi

Event handler nên có error boundary rõ ràng. Một rejected Promise không được xử lý có thể làm tác vụ thất bại và khó debug.

Ví dụ:

```js
chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name !== 'refresh-status') return;

  refreshStatus().catch((error) => {
    console.error('refresh-status failed:', error);
    return recordFailure({
      code: 'STATUS_REFRESH_FAILED',
      at: Date.now()
    });
  });
});
```

Không log error object nếu nó có thể chứa request URL, headers hoặc dữ liệu nhạy cảm. Chuẩn hóa lỗi thành mã và correlation ID.

### Idempotency

Browser có thể gửi lại event, worker có thể restart giữa quy trình hoặc người dùng bấm nhiều lần. Tác vụ nên idempotent:

- Gắn operation ID.
- Lưu trạng thái đang xử lý/đã hoàn tất.
- Tránh tạo bản ghi hoặc notification trùng.
- Dùng server idempotency key nếu gọi API có side effect.
- Cập nhật checkpoint trước khi kết thúc event.

### Retry

Retry cần backoff và giới hạn:

- Phân biệt lỗi network tạm thời với 4xx không retry.
- Giới hạn số lần thử.
- Dùng alarm cho retry sau này thay vì timer dài trong worker.
- Không retry hành động nhạy cảm nếu không có idempotency.
- Tôn trọng Retry-After khi API cung cấp.

## 16. Debug background service worker

### Mở service worker DevTools

Trong Chrome:

1. Mở chrome://extensions.
2. Bật Developer mode.
3. Tìm extension đang phát triển.
4. Chọn liên kết Inspect views/Service Worker để mở DevTools của worker.
5. Quan sát Console, Sources và Network.

Tên và vị trí nút có thể thay đổi theo phiên bản Chrome. Nếu worker chưa chạy, phát một event như bấm action hoặc gửi message để browser khởi động nó.

### Kiểm tra worker restart

1. Mở DevTools của extension service worker.
2. Quan sát log khởi tạo và event.
3. Dùng nút Stop trong trang extensions để dừng worker khi đang debug.
4. Bấm action hoặc gửi message để đánh thức worker.
5. Xác nhận biến global được khởi tạo lại.
6. Xác nhận state đã lưu trong storage vẫn còn.

Đây là cách kiểm tra code có phụ thuộc worker chạy liên tục hay không.

### Kiểm tra storage

Trong DevTools, kiểm tra extension storage/IndexedDB theo context được hỗ trợ. Có thể quan sát bằng console:

```js
await chrome.storage.local.get(null);
```

Chỉ chạy trên profile lab. Không copy dữ liệu nhạy cảm từ storage vào issue, log hoặc ảnh chụp.

### Kiểm tra message

- Đặt breakpoint trong onMessage.
- Kiểm tra sender.id, sender.url, sender.tab và sender.frameId.
- Xem payload có đúng schema không.
- Thử gửi message sai type hoặc field để xác nhận bị từ chối.
- Kiểm tra response/error handling ở popup/content script.

### Kiểm tra network

- Quan sát request từ extension service worker.
- Kiểm tra host permission đã khai báo.
- Kiểm tra redirect và URL cuối.
- Kiểm tra credentials mode.
- Xác nhận response không ghi secret vào console.

## 17. Thực hành: xây dựng background worker lab

Thực hành trong extension local do người học kiểm soát. Không cài extension thử nghiệm không rõ nguồn lên profile chứa tài khoản thật.

### 17.1. Tạo cấu trúc

```text
extension-lab/
  manifest.json
  service-worker.js
  content.js
  popup.html
  popup.js
```

Khai báo manifest MV3 với storage, alarms, activeTab, scripting và host permission cho một API lab. Không dùng all_urls nếu bài lab chỉ cần app.example.test và api.example.test.

### 17.2. Kiểm tra event registration

Đăng ký onInstalled, onStartup, alarms.onAlarm, runtime.onMessage và action.onClicked ở top-level.

Kỳ vọng:

- Worker được browser đánh thức bởi event.
- Listener hoạt động ngay cả sau khi worker bị terminate và khởi động lại.
- Không cần mở popup để nhận alarm.

### 17.3. Kiểm tra global state

Thêm counter global và tăng mỗi lần nhận message. Dừng worker rồi gửi message lần nữa.

Kỳ vọng: counter trở về giá trị khởi tạo. Đây là bằng chứng global variable không phải persistent storage.

### 17.4. Kiểm tra storage

Lưu preference vào storage.local, restart worker và đọc lại.

Kỳ vọng: preference vẫn tồn tại. Lưu một giá trị tạm vào storage.session và kiểm tra hành vi khi worker restart trong cùng browser session.

### 17.5. Kiểm tra alarm

Tạo alarm lab với chu kỳ phù hợp giới hạn browser, log thời điểm event được xử lý và restart worker.

Kỳ vọng: alarm đánh thức worker; không cần setInterval để giữ worker sống. Ghi nhận rằng alarm có thể bị trì hoãn và không phải scheduler thời gian thực.

### 17.6. Kiểm tra message sender

Gửi message từ content script được match trên app.example.test. Sau đó thử:

- Message có type không nằm allowlist.
- Payload thiếu field.
- Payload có field sai kiểu.
- Message từ frame không được phép.
- Message từ origin khác.

Kỳ vọng: background từ chối message không hợp lệ và không gọi privileged API.

### 17.7. Kiểm tra fetch permission

Từ background worker gọi API host được khai báo. Sau đó thử một host không được khai báo.

Kỳ vọng: request tới host đã cấp quyền hoạt động theo browser policy; request tới host ngoài quyền bị chặn hoặc không được phép. Content script không tự thừa hưởng toàn bộ host permission của worker.

### 17.8. Kiểm tra storage access level

Nếu browser hỗ trợ setAccessLevel, đặt storage.local chỉ cho trusted contexts. Kiểm tra content script không đọc được dữ liệu chỉ background cần truy cập.

Không lưu secret thật trong bài lab.

### 17.9. Kiểm tra restart và error recovery

Cho worker dừng giữa một job giả lập, sau đó phát event tiếp theo để khởi động lại. Đọc checkpoint và tiếp tục job.

Kỳ vọng: không mất tiến độ đã commit và không thực hiện side effect trùng.

### 17.10. Bằng chứng cần lưu

| Bằng chứng | Điều cần xác nhận |
| --- | --- |
| Manifest | service_worker khai báo đúng và quyền tối thiểu. |
| Event listeners | Listener được đăng ký top-level. |
| Cold start | Worker khởi động lại và global state reset. |
| Persistent state | storage.local/IndexedDB giữ state qua restart. |
| Session state | storage.session giữ state trong browser session theo thiết kế. |
| Alarm | Event được phát mà không cần timer giữ worker sống. |
| Message validation | Sender và payload sai bị từ chối. |
| Host permissions | Fetch chỉ tới host được cấp quyền. |
| Storage access | Content script không đọc storage trusted-only. |
| Recovery | Job tiếp tục từ checkpoint và tránh side effect trùng. |

## 18. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Listener không nhận event | Đăng ký listener sau async initialization | Đăng ký top-level đồng bộ, load state bên trong handler. |
| Worker dừng và mất state | Dùng global variable như persistent storage | Lưu state vào chrome.storage/IndexedDB. |
| Timer không chạy khi worker dừng | Dùng setInterval/setTimeout cho lịch nền | Dùng chrome.alarms. |
| Alarm chạy nhiều lần | Tạo alarm mới mỗi startup mà không kiểm tra | Dùng tên cố định và kiểm tra alarm tồn tại. |
| Message không có response | Quên return true với callback async hoặc không gọi sendResponse | Dùng đúng async messaging pattern theo browser target. |
| Background thực hiện lệnh ngoài ý muốn | Tin message content script hoặc page | Validate sender, schema, allowlist và quyền. |
| Extension thành open proxy | Worker fetch URL tùy ý do content script gửi | Chỉ cho phép endpoint/origin/path/method cụ thể. |
| Content script đọc được secret | Mở storage access level quá rộng | Giới hạn TRUSTED_CONTEXTS và không lưu secret không cần thiết. |
| CORS bị hiểu sai | Nghĩ host permission là authorization server-side | API vẫn xác thực và kiểm tra quyền; CORS không thay authorization. |
| Dữ liệu DOM gây lỗi privileged action | Tin nội dung page do content script gửi | Coi DOM/message là input không tin cậy và validate. |
| Worker dùng DOM/window | Port code từ background page | Chuyển thao tác DOM vào content script/offscreen document có kiểm soát. |
| MV3 extension bị từ chối code | Tải remote script hoặc dùng eval | Bundle code đã review trong extension package. |
| Job bị chạy trùng sau restart | Không có checkpoint/idempotency | Lưu trạng thái và dùng operation ID. |

## 19. Checklist production

| Hạng mục | Câu hỏi rà soát | Kết quả mong đợi |
| --- | --- | --- |
| Manifest | Có dùng Manifest V3 và khai báo service_worker đúng? | Worker nằm trong package extension. |
| Lifecycle | Code có chịu được cold start/termination? | Không phụ thuộc global state hoặc worker sống liên tục. |
| Listener | Event listener có đăng ký top-level? | Browser tìm thấy handler sau restart. |
| Initialization | Init có idempotent? | Không tạo alarm/listener/data trùng. |
| Persistent state | State có được lưu đúng storage? | storage.local/IndexedDB; session state dùng storage.session. |
| Secrets | Có lưu password/token trong storage không? | Tránh secret; có threat model và kiểm soát nếu bắt buộc. |
| Storage access | Content scripts có đọc storage không cần thiết? | Giới hạn trusted contexts khi hỗ trợ. |
| Alarm | Công việc định kỳ có dùng chrome.alarms? | Không phụ thuộc timer trong worker. |
| Long jobs | Job có checkpoint và idempotency? | Có thể tiếp tục sau restart mà không lặp side effect. |
| Messaging | Có validate sender.id/url/tab/frame? | Chỉ context được phép gửi lệnh. |
| Payload | Message có schema, type và size limit? | Không thực thi lệnh tùy ý. |
| Permissions | Manifest có quyền dư thừa? | Least privilege và optional permission khi phù hợp. |
| Host permissions | Có dùng all_urls không cần thiết? | Chỉ allowlist host/path cần thiết. |
| Network | Background fetch có URL allowlist và credentials policy? | Không làm open proxy; API authorization riêng. |
| Content scripts | DOM/page data có được coi là untrusted? | Validate và encode an toàn. |
| Remote code | Có eval hoặc remote hosted code? | Code được bundle/review trong package. |
| CSP | Extension page có policy nghiêm? | Không nới unsafe-eval/remote script. |
| Logging | Có log token, cookie, page content hoặc full URL? | Redact và giới hạn retention. |
| Debugging | Có test stop/restart worker và alarm? | Cold start và recovery được xác minh. |
| Browser support | Có kiểm tra API differences theo browser/version? | Manifest/API compatibility được test. |

## 20. Câu hỏi tự kiểm tra

1. Background page của Manifest V2 khác extension service worker Manifest V3 như thế nào?
2. Vì sao background service worker không phải một tiến trình chạy liên tục?
3. Cold start ảnh hưởng global variable ra sao?
4. Vì sao event listener nên được đăng ký đồng bộ ở top-level?
5. Khi nào dùng storage.local, storage.session, storage.sync và IndexedDB?
6. Vì sao setInterval không phù hợp làm scheduler nền lâu dài?
7. chrome.alarms có những giới hạn nào so với scheduler thời gian thực?
8. Message passing giữa content script và background có rủi ro confused deputy nào?
9. sender.id, sender.url, sender.tab và sender.frameId giúp kiểm tra điều gì?
10. Vì sao payload từ content script vẫn là dữ liệu không tin cậy?
11. activeTab khác host_permissions như thế nào?
12. Vì sao background fetch không được biến thành open proxy?
13. CORS và host permission khác authorization ra sao?
14. Vì sao Manifest V3 hạn chế remote hosted code và eval?
15. Làm thế nào kiểm tra worker restart, storage và alarm bằng DevTools?

**Tiêu chí hoàn thành:** người học có thể khai báo và triển khai Manifest V3 background service worker, đăng ký event listener top-level, thiết kế state persistence và alarm, xác minh message sender/payload, giới hạn permissions/host access, bảo vệ network và storage, đồng thời kiểm chứng cold start, restart và recovery bằng DevTools trong môi trường lab.
