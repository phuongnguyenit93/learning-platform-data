# Extension permission: mô hình quyền và nguyên tắc cấp quyền tối thiểu

## Mục tiêu học tập

Sau bài học, người học có thể:

1. Giải thích vì sao browser extension cần permission và permission bảo vệ ranh giới nào.
2. Phân biệt quyền API trong permissions với quyền truy cập website trong host_permissions.
3. Phân biệt required permissions, optional permissions và quyền được cấp tạm thời.
4. Thiết kế activeTab để chỉ truy cập tab người dùng chủ động chọn.
5. Đọc và giới hạn host match patterns, tránh cấp quyền trên toàn bộ website khi không cần.
6. Đánh giá rủi ro của các permission nhạy cảm như tabs, cookies, history, downloads, debugger và nativeMessaging.
7. Kiểm soát content scripts, extension service worker và messaging giữa page với extension.
8. Xử lý việc người dùng cấp, từ chối, thu hồi hoặc thay đổi quyền trong runtime.
9. Hiểu khác biệt giữa extension permission, site permission, CORS và browser permission.
10. Kiểm thử quyền extension bằng DevTools, trang quản lý extension và ma trận kiểm thử.

> **Bối cảnh:** Module Browser Security phân tích ranh giới bảo mật giữa trình duyệt, origin, cookie và ứng dụng web để hiểu Same-Origin Policy, CORS và các cơ chế cách ly; đồng thời thực hành phòng vệ XSS, CSRF, clickjacking bằng CSP, Trusted Types và security headers. Browser extension có thể nhận quyền đọc tab, truy cập website, quan sát request hoặc giao tiếp với ứng dụng native. Permission là ranh giới đặc quyền quan trọng; cần cấp đúng quyền, đúng website và đúng thời điểm.

## 1. Vì sao extension cần permission?

Browser extension là phần mềm chạy bên trong browser nhưng có thể được cấp năng lực vượt quá một website thông thường. Tùy nền tảng và permission, extension có thể:

- Đọc hoặc sửa nội dung trang web.
- Chèn content script vào các website được phép.
- Đọc URL, tiêu đề hoặc metadata của tab.
- Quan sát hoặc thay đổi một số request mạng.
- Quản lý download, bookmark hoặc history.
- Đọc cookie của các host được cấp quyền.
- Lưu dữ liệu trong extension storage.
- Giao tiếp với chương trình native qua Native Messaging.
- Thay đổi proxy hoặc cấu hình browser trong phạm vi API được phép.

Nếu một extension bị xâm nhập, chứa mã độc hoặc được cấp quyền quá rộng, hậu quả có thể lan tới nhiều website mà người dùng truy cập. Permission model giúp browser yêu cầu khai báo năng lực và cho người dùng cơ hội xem xét.

### Permission không phải một nút Allow duy nhất

Quyền extension thường gồm nhiều lớp:

1. API permission: cho phép gọi một nhóm API của browser.
2. Host permission: cho phép extension truy cập các website hoặc origin cụ thể.
3. Temporary grant: quyền tạm thời do hành động người dùng tạo ra, ví dụ activeTab.
4. Site permission: quyền của website đối với camera, microphone, location hoặc notification; đây là cơ chế riêng.
5. Enterprise policy: chính sách quản trị có thể cho phép, chặn hoặc cấu hình extension.

Một API có thể yêu cầu cả API permission và host permission. Có host permission không có nghĩa extension tự động có mọi API; có API permission cũng không có nghĩa extension được đọc mọi website.

## 2. Manifest V3 và nơi khai báo permission

Extension khai báo metadata, quyền và entry point trong manifest.json. Với Chrome Manifest V3, cấu trúc cơ bản có thể như sau:

    {
      "manifest_version": 3,
      "name": "Example Tab Helper",
      "version": "1.0.0",
      "description": "Thao tác trên tab sau khi người dùng yêu cầu",
      "permissions": [
        "activeTab",
        "scripting",
        "storage"
      ],
      "background": {
        "service_worker": "service-worker.js"
      },
      "action": {
        "default_title": "Phân tích tab hiện tại"
      }
    }

Ví dụ này không khai báo host_permissions cố định. Extension dùng activeTab để xin quyền tạm thời đối với tab mà người dùng chủ động kích hoạt, scripting để chạy script khi được phép và storage để lưu dữ liệu extension.

### permissions

Trường permissions khai báo quyền dùng API của browser, ví dụ:

    "permissions": [
      "storage",
      "downloads",
      "notifications"
    ]

Các permission cụ thể và cách browser hiển thị cảnh báo có thể khác giữa Chrome, Firefox, Edge và các nền tảng khác.

### host_permissions

Trường host_permissions khai báo website mà extension cần truy cập:

    "host_permissions": [
      "https://portal.example.test/*"
    ]

Host permission có thể cần cho việc đọc dữ liệu từ website, gọi một số API trên host hoặc chạy content script theo cấu hình. Nó không tự cấp quyền truy cập website không nằm trong phạm vi được khai báo hoặc được người dùng cấp.

### content_scripts.matches

Content script có thể khai báo pattern website cần chạy:

    "content_scripts": [
      {
        "matches": [
          "https://portal.example.test/*"
        ],
        "js": ["content.js"],
        "run_at": "document_idle"
      }
    ]

matches xác định nơi content script được chèn. Đây là một phần của thiết kế host access và cần được rà soát cùng host_permissions, optional_host_permissions và browser behavior.

### optional_permissions và optional_host_permissions

Quyền không cần cho mọi người dùng hoặc mọi phiên nên được cân nhắc cấp theo yêu cầu:

    {
      "manifest_version": 3,
      "name": "Optional Export Helper",
      "version": "1.0.0",
      "permissions": [
        "storage"
      ],
      "optional_permissions": [
        "downloads"
      ],
      "optional_host_permissions": [
        "https://reports.example.test/*"
      ]
    }

Extension có thể yêu cầu quyền bổ sung khi người dùng bật tính năng tương ứng. Người dùng có thể từ chối; tính năng phải có fallback rõ ràng.

## 3. API permission và host permission khác nhau

Đây là hai khái niệm thường bị nhầm lẫn.

| Loại quyền | Ví dụ | Cho phép điều gì? |
| --- | --- | --- |
| API permission | storage | Gọi API lưu dữ liệu extension |
| API permission | downloads | Dùng API quản lý download theo quyền browser cấp |
| API permission | tabs | Truy cập một số thông tin nhạy cảm của tab |
| Host permission | https://portal.example.test/* | Truy cập host trong phạm vi pattern được cấp |
| Host permission | https://*.example.test/* | Truy cập host phù hợp dưới domain được khai báo |
| Temporary grant | activeTab | Tạm cấp quyền host cho tab người dùng vừa chủ động chọn |

### Có API permission nhưng thiếu host permission

Extension có thể có scripting nhưng không có host permission hoặc activeTab cho tab mục tiêu. Khi đó, việc chèn script vào tab có thể bị từ chối.

### Có host permission nhưng thiếu API permission

Extension có thể được phép truy cập một host nhưng vẫn thiếu API permission cần thiết để dùng API đặc biệt như downloads hoặc cookies.

### Host permission không phải quyền sở hữu website

Host permission chỉ là quyền mà browser cấp cho extension trong môi trường browser. Nó không cho extension quyền vượt qua authentication, authorization hoặc chính sách của server. Server vẫn phải xác minh session, token và quyền truy cập cho mọi request.

## 4. Required và optional permission

### Required permission

Required permission được khai báo ngay từ đầu khi extension cài đặt hoặc cập nhật. Người dùng có thể thấy cảnh báo hoặc thông tin quyền theo giao diện browser.

Chỉ khai báo required permission nếu chức năng cốt lõi thực sự không thể hoạt động nếu thiếu quyền đó.

### Optional permission

Optional permission chỉ được yêu cầu khi người dùng bật chức năng cần quyền. Ví dụ:

- Extension quản lý tab chỉ cần downloads khi người dùng bật chức năng lưu báo cáo.
- Extension làm việc với một portal chỉ cần host permission khi người dùng kết nối portal đó.
- Extension không cần đọc clipboard trong mọi phiên; chỉ yêu cầu clipboardRead cho chức năng dán đặc biệt nếu browser hỗ trợ và có lý do rõ.

### Lợi ích của optional permission

- Giảm quyền được cấp khi cài đặt.
- Người dùng hiểu vì sao extension cần quyền ở thời điểm sử dụng.
- Giảm hậu quả nếu extension bị xâm nhập trước khi người dùng bật tính năng.
- Có thể thu hồi quyền khi không còn cần.

Optional permission không tự động an toàn. Extension vẫn phải giải thích mục đích, xử lý trường hợp người dùng từ chối và tránh yêu cầu quyền lặp lại gây áp lực.

### Người dùng có thể giới hạn site access

Một số browser cung cấp lựa chọn như chỉ cho extension truy cập khi người dùng bấm, chỉ trên các website cụ thể hoặc trên mọi website. Khi host permission bị withheld, extension không được giả định quyền đã có chỉ vì pattern xuất hiện trong manifest. Phải kiểm tra trạng thái quyền và xử lý việc người dùng cấp quyền theo giao diện browser.

Extension không được tự bật lại site access sau khi người dùng đã giới hạn. Các lựa chọn, tên menu và cách browser lưu grant thay đổi theo nền tảng/version; hãy kiểm thử trên browser thực tế.

### Không có cảnh báo không có nghĩa permission vô hại

Browser có thể không hiển thị cảnh báo cài đặt riêng cho một số permission hoặc host pattern. Điều đó không có nghĩa dữ liệu được truy cập là không nhạy cảm. Review nội bộ vẫn phải đánh giá tác động của quyền như tabs, history, clipboard, cookies và host access.

## 5. activeTab: quyền tạm thời theo hành động người dùng

activeTab cho phép extension có quyền tạm thời đối với tab đang hoạt động sau một số thao tác rõ ràng của người dùng, chẳng hạn bấm nút extension action hoặc dùng command được người dùng kích hoạt.

Ví dụ:

    {
      "manifest_version": 3,
      "name": "Selected Tab Inspector",
      "version": "1.0.0",
      "permissions": [
        "activeTab",
        "scripting"
      ],
      "action": {
        "default_title": "Đọc tiêu đề trang"
      },
      "background": {
        "service_worker": "service-worker.js"
      }
    }

Trong service-worker.js:

    chrome.action.onClicked.addListener(async (tab) => {
      if (!tab.id) return;

      const results = await chrome.scripting.executeScript({
        target: { tabId: tab.id },
        func: () => ({
          title: document.title,
          url: location.href
        })
      });

      console.log(results);
    });

### activeTab giảm quyền lâu dài

Thay vì yêu cầu quyền đọc mọi website, extension chỉ nhận temporary grant khi người dùng chủ động chọn tab. Điều này phù hợp với:

- Công cụ trích xuất thông tin trang hiện tại.
- Bộ đọc nội dung theo yêu cầu.
- Công cụ chụp hoặc phân tích tab đang mở.
- Extension chỉ hoạt động khi người dùng bấm nút.

### Giới hạn của activeTab

- Không phải quyền vĩnh viễn cho mọi tab.
- Quyền có thể hết hiệu lực khi tab đóng hoặc điều hướng sang origin khác, theo quy tắc browser.
- Không cấp quyền truy cập mọi website trong mọi thời điểm.
- Không thay thế các permission API khác nếu API yêu cầu.
- Không biến trang bị browser bảo vệ đặc biệt thành trang có thể script tùy ý.

Hành vi chi tiết có thể khác theo browser và loại thao tác kích hoạt. Hãy kiểm tra tài liệu nền tảng mục tiêu.

## 6. Host match patterns

Host permission và content script thường dùng match pattern:

    https://portal.example.test/*

Một pattern thường gồm scheme, host và path.

### Ví dụ

| Pattern | Phạm vi |
| --- | --- |
| https://portal.example.test/* | HTTPS trên host portal.example.test |
| https://*.example.test/* | HTTPS trên domain và subdomain phù hợp |
| http://localhost/* | HTTP localhost cho môi trường phát triển |
| http://*/* | Rất rộng trên HTTP |
| https://*/* | Rất rộng trên HTTPS |
| &lt;all_urls&gt; | Phạm vi rất rộng trong các scheme mà browser hỗ trợ cho pattern này |

Pattern wildcard không có nghĩa extension truy cập được mọi trang browser nội bộ, trang extension khác hoặc trang được browser bảo vệ. Một số host/scheme yêu cầu người dùng bật quyền riêng, ví dụ file URL.

### Tránh &lt;all_urls&gt;

Không dùng &lt;all_urls&gt; chỉ để tránh phải xác định website. Nó có thể khiến extension truy cập lượng lớn dữ liệu duyệt web và làm cảnh báo cài đặt đáng lo ngại.

Nếu chức năng chỉ cần một portal:

    "host_permissions": [
      "https://portal.example.test/*"
    ]

Nếu cần nhiều portal:

    "host_permissions": [
      "https://crm.example.test/*",
      "https://reports.example.test/*"
    ]

Không khai báo cả *.example.test nếu chỉ có hai host cụ thể cần dùng.

### Scheme và wildcard

Chỉ cho phép scheme cần thiết. Nếu website luôn dùng HTTPS, không thêm HTTP. Với wildcard subdomain, xác định cả domain gốc và các subdomain có thực sự thuộc cùng trust boundary không.

### Path trong host permission

Path có thể giúp mô tả match pattern cho content scripts, nhưng mức cấp host access có thể được browser quản lý theo origin/host chứ không phải authorization chi tiết trên từng route. Không coi path pattern là cơ chế bảo vệ dữ liệu nghiệp vụ. Server vẫn phải kiểm tra quyền trên từng endpoint.

## 7. Những permission nhạy cảm thường gặp

Tên permission và cảnh báo có thể khác theo browser/version. Bảng dưới mô tả rủi ro khái quát, không phải danh sách đầy đủ mọi API.

| Permission/API | Năng lực có thể mở | Rủi ro nếu cấp quá rộng |
| --- | --- | --- |
| tabs | Đọc metadata nhạy cảm của tab như URL/title khi được cấp quyền phù hợp | Lộ lịch sử hoạt động và thông tin trang |
| history | Đọc hoặc quản lý lịch sử duyệt web | Theo dõi hoạt động riêng tư |
| cookies | Đọc/ghi cookie cho host được cấp quyền | Chiếm session hoặc đọc trạng thái xác thực nếu cookie có thể truy cập |
| webRequest | Quan sát một số request và metadata theo API/policy | Lộ URL, header hoặc metadata mạng |
| declarativeNetRequest | Áp dụng rule chặn/redirect/modify request theo giới hạn browser | Chặn hoặc thay đổi luồng mạng ngoài dự kiến |
| downloads | Theo dõi hoặc quản lý download | Lộ tên file, URL và hoạt động tải |
| clipboardRead | Đọc clipboard theo quyền và điều kiện browser | Lộ mật khẩu hoặc nội dung người dùng vừa sao chép |
| clipboardWrite | Ghi nội dung vào clipboard | Ghi đè dữ liệu người dùng hoặc gây lừa đảo |
| debugger | Gắn debugger vào target và quan sát/điều khiển sâu | Đọc dữ liệu trang và thao tác nhạy cảm |
| nativeMessaging | Giao tiếp với native host trên máy | Mở đường tới dữ liệu và hành động ngoài browser |
| proxy | Cấu hình proxy trong phạm vi API | Thay đổi đường đi của traffic |
| management | Quản lý hoặc quan sát extension khác theo API | Lộ phần mềm đã cài và tác động cấu hình extension |
| webNavigation | Quan sát sự kiện navigation | Theo dõi trang và hành vi điều hướng |
| notifications | Hiển thị notification | Giả mạo cảnh báo hoặc gây phiền nhiễu |
| identity | Dùng API xác thực/identity của nền tảng | Sai cấu hình có thể làm lộ token hoặc luồng đăng nhập |

### tabs không đồng nghĩa với host permission

tabs permission chủ yếu mở khả năng đọc các thuộc tính nhạy cảm như URL, title hoặc favicon của tab. Để inject script hoặc đọc DOM, extension còn cần quyền phù hợp như activeTab hoặc host permission cùng scripting/content script.

Không khai báo tabs nếu chỉ cần tab.id hoặc khả năng lắng nghe sự kiện không nhạy cảm mà browser cho phép không cần permission đó.

### cookies cần host permission

API cookies thường cần permission cookies cùng host permission cho domain liên quan. Không xin quyền cookies trên mọi website nếu chỉ cần thao tác cookie của một dịch vụ cụ thể.

Cookie HttpOnly không thể bị JavaScript trang đọc trực tiếp, nhưng extension có quyền cookies phù hợp có thể có khả năng đọc cookie theo API browser và host access. Đây là lý do extension permission cần được xem là đặc quyền cao.

### webRequest và declarativeNetRequest

Trong Chrome Manifest V3, khả năng dùng webRequest để quan sát request bị giới hạn so với Manifest V2; blocking request thông thường được chuyển sang declarativeNetRequest. Có ngoại lệ hoặc khác biệt theo enterprise policy và browser.

Không thiết kế extension cross-browser bằng cách giả định mọi nền tảng có cùng quyền chặn request. Xác định browser/version và API hỗ trợ trước khi triển khai.

### debugger và nativeMessaging

Đây là các quyền có tác động lớn. Chỉ dùng khi chức năng cốt lõi thực sự cần điều khiển debugging hoặc giao tiếp với ứng dụng native. Kiểm tra nguồn native host, quyền file/process, input validation và cơ chế cập nhật riêng.

## 8. Permission của extension và site permission

Extension permission không thay thế permission của website đối với thiết bị hoặc feature của browser.

Ví dụ:

- Extension có host permission với một website không có nghĩa website đó được phép dùng camera.
- Extension gọi getUserMedia vẫn chịu secure context và cơ chế browser/user consent tương ứng với context thực thi.
- Extension permission không tự cấp quyền geolocation hoặc notification cho website.
- Quyền extension không làm biến mất prompt của hệ điều hành hoặc browser.

### Phân biệt các lớp

| Cơ chế | Chủ thể | Ví dụ |
| --- | --- | --- |
| Extension API permission | Extension | downloads, storage, cookies |
| Extension host permission | Extension đối với website | https://portal.example.test/* |
| Website permission | Origin/document | camera, microphone, location |
| OS permission | Ứng dụng/browser trên hệ điều hành | Camera, microphone, notification |
| Server authorization | Người dùng/session trên backend | Được tải báo cáo của tenant nào |

Không suy ra quyền ở lớp này từ việc đã cấp quyền ở lớp khác.

## 9. Content script và ranh giới thực thi

Content script chạy trong trang được match nhưng thường có isolated world riêng cho JavaScript environment. Biến và function của content script không tự động chia sẻ với JavaScript page.

Tuy vậy, DOM là tài nguyên dùng chung. Content script đọc/ghi DOM có thể gặp dữ liệu do trang kiểm soát và có thể bị ảnh hưởng bởi nội dung độc hại trong DOM.

### Isolated world không có nghĩa DOM đáng tin

Ví dụ content script:

    const title = document.querySelector("h1")?.textContent;

Giá trị title do website kiểm soát. Không dùng nó như lệnh, selector đặc quyền, URL đích hoặc HTML an toàn mà không validate.

### Tránh innerHTML

Không chèn dữ liệu từ page vào HTML:

    resultPanel.innerHTML = pageProvidedText;

Ưu tiên:

    resultPanel.textContent = pageProvidedText;

Nếu cần tạo markup, dùng DOM API và kiểm soát giá trị từng node. Trusted Types và CSP có thể hỗ trợ giảm DOM XSS, nhưng không thay input validation và thiết kế message an toàn.

### MAIN world

Một số API cho phép chạy script trong MAIN world để tương tác với JavaScript của trang. MAIN world chia sẻ environment với page và chịu ảnh hưởng của script page. Không đặt secret hoặc privileged extension API vào MAIN world; không tin dữ liệu trả về từ đó.

Chỉ dùng MAIN world khi cần tích hợp với page runtime và đã xác định rõ dữ liệu nào có thể bị page sửa.

### CSP của extension và CSP của page

Extension pages/service worker có CSP riêng theo manifest và giới hạn nền tảng. Content script có execution world khác với page script; CSP của extension không phải một sandbox hoàn chỉnh cho DOM mà content script tương tác.

Không dùng eval hoặc remote hosted code. Với Manifest V3, extension package phải chứa code thực thi theo chính sách của nền tảng; việc tải JavaScript từ server rồi thực thi thường bị cấm hoặc hạn chế nghiêm ngặt.

## 10. Messaging giữa content script và extension

Content script thường gửi message tới service worker/background để yêu cầu hành động có đặc quyền.

Ví dụ:

    chrome.runtime.sendMessage({
      type: "GET_SETTINGS"
    });

Service worker nhận message:

    chrome.runtime.onMessage.addListener(
      (message, sender, sendResponse) => {
        if (sender.id !== chrome.runtime.id) {
          return;
        }

        if (message?.type === "GET_SETTINGS") {
          sendResponse({ theme: "system" });
        }
      }
    );

Đây chỉ là khung minh họa. Trong ứng dụng thực, phải xác minh sender, tab, frame và schema message theo loại request.

### Không coi message là đáng tin chỉ vì đến từ content script

Page có thể thao túng DOM mà content script đọc. Một content script có lỗi có thể gửi dữ liệu không hợp lệ tới service worker. Nếu service worker có quyền downloads, cookies hoặc tabs, message có thể trở thành lệnh đặc quyền.

### Kiểm tra sender

Tùy loại message, kiểm tra:

- sender.id có đúng extension ID không.
- sender.url hoặc sender.origin có thuộc website mong đợi không.
- sender.tab.id có phải tab mà người dùng vừa chọn không.
- sender.frameId có được phép gửi loại lệnh đó không.
- Message type có nằm trong allowlist không.
- Field có đúng kiểu, độ dài và format không.

Không chỉ kiểm tra sender.id nếu message có thể đến từ nhiều content script/frame trong cùng extension.

### Dùng schema và allowlist command

Ví dụ:

    function isValidExportRequest(message) {
      return (
        message &&
        message.type === "EXPORT_TEXT" &&
        typeof message.text === "string" &&
        message.text.length <= 100000
      );
    }

Không tạo API message tổng quát kiểu EXECUTE, FETCH_ANY_URL hoặc RUN_SCRIPT cho content script. Mỗi command nên có mục đích hẹp và quyền tối thiểu.

### Không để page gọi trực tiếp privileged message

Nếu extension expose window.postMessage bridge cho page, page có thể gửi message giả. Bridge phải kiểm tra origin, schema, action allowlist và không trả dữ liệu nhạy cảm. Không coi event.source hoặc một secret hardcoded trong page là authentication đủ mạnh.

## 11. Extension service worker và quyền đặc quyền

Trong Manifest V3, background logic của Chrome thường chạy trong extension service worker. Service worker có thể được browser đánh thức khi có event rồi bị dừng khi idle.

Điều này ảnh hưởng cách thiết kế permission:

- Không giả định global state luôn tồn tại.
- Lưu state cần thiết trong storage phù hợp.
- Xử lý event và message idempotent khi có thể.
- Không lưu secret lâu dài trong biến global rồi coi đó là bảo vệ.
- Chỉ thực hiện hành động đặc quyền sau khi kiểm tra nguồn yêu cầu.

### Service worker là nơi tập trung đặc quyền

Nếu content script chỉ đọc DOM nhưng service worker có quyền cookies, downloads và host access rộng, service worker là điểm nhạy cảm. Hãy giữ API surface nhỏ, command rõ ràng và không chuyển tiếp tùy tiện URL hoặc dữ liệu page.

### Không fetch URL bất kỳ theo message

Tránh:

    chrome.runtime.onMessage.addListener((message) => {
      if (message.type === "FETCH") {
        return fetch(message.url);
      }
    });

Message như vậy có thể biến extension thành confused deputy, dùng host permission hoặc credential của extension để fetch URL do page kiểm soát.

Thay vào đó, allowlist host và endpoint, kiểm tra scheme/host/path, method, redirect và nội dung response. Không gửi credential tới URL tùy ý.

## 12. Yêu cầu optional permission trong runtime

Extension có thể yêu cầu optional permission khi người dùng bật chức năng. Ví dụ:

    async function enableDownloads() {
      const granted = await chrome.permissions.request({
        permissions: ["downloads"]
      });

      if (!granted) {
        showMessage("Bạn chưa cấp quyền tải xuống.");
        return false;
      }

      enableExportFeature();
      return true;
    }

Lời gọi request cần diễn ra trong user gesture phù hợp theo quy tắc browser. Không gọi ngay khi cài extension hoặc lặp đi lặp lại khi người dùng từ chối.

### Yêu cầu optional host permission

Ví dụ:

    async function connectPortal() {
      const granted = await chrome.permissions.request({
        origins: [
          "https://portal.example.test/*"
        ]
      });

      if (!granted) {
        showMessage("Chưa có quyền truy cập portal.");
        return;
      }

      connectToPortal();
    }

### Kiểm tra quyền đã có

    const hasDownloads = await chrome.permissions.contains({
      permissions: ["downloads"]
    });

    const hasPortal = await chrome.permissions.contains({
      origins: ["https://portal.example.test/*"]
    });

Không giả định permission request luôn được cấp. Kiểm tra trạng thái trước khi dùng API và xử lý lỗi khi permission bị thu hồi giữa chừng.

### Lắng nghe thay đổi quyền

    chrome.permissions.onRemoved.addListener((removed) => {
      updateFeaturesAfterPermissionChange(removed);
    });

    chrome.permissions.onAdded.addListener((added) => {
      updateFeaturesAfterPermissionChange(added);
    });

API cụ thể có thể khác tên hoặc hỗ trợ theo browser. Thiết kế feature theo trạng thái permission thực tế, không chỉ theo cấu hình manifest.

## 13. Quyền có thể bị thu hồi hoặc thay đổi

Người dùng có thể thay đổi site access hoặc thu hồi optional permission trong trang quản lý extension. Browser cũng có thể yêu cầu xác nhận lại khi extension cập nhật thêm quyền.

Extension cần:

- Kiểm tra quyền trước khi gọi API.
- Bắt lỗi permission denied.
- Cập nhật UI khi quyền bị thu hồi.
- Không tiếp tục polling hoặc inject script khi không còn quyền.
- Xóa dữ liệu tạm không còn cần.
- Cho phép người dùng bật lại chức năng qua hành động rõ ràng.

### Permission removal và dữ liệu đã lưu

Thu hồi permission không nhất thiết xóa dữ liệu extension đã lưu trước đó. Nếu dữ liệu được thu thập khi quyền còn hiệu lực, extension cần chính sách retention và xóa dữ liệu riêng.

Không coi việc người dùng revoke host permission là lệnh tự động xóa mọi log hoặc bản sao đã gửi tới server. Hãy có quy trình dữ liệu rõ ràng.

### Cập nhật extension và tăng quyền

Khi version mới yêu cầu thêm permission, browser có thể hiển thị cảnh báo hoặc yêu cầu người dùng chấp thuận lại tùy nền tảng. Không thêm permission rộng trong một bản cập nhật mà không giải thích chức năng mới.

## 14. Host permission, CORS và network request

Host permission và CORS đều liên quan cross-origin nhưng phục vụ các đối tượng khác nhau.

| Cơ chế | Kiểm soát điều gì? |
| --- | --- |
| CORS | Browser có cho JavaScript của một origin đọc response cross-origin hay không |
| Host permission | Extension được browser cho truy cập host nào qua các API extension tương ứng |
| Same-Origin Policy | Giới hạn tương tác giữa các origin theo quy tắc browser |
| Server authorization | Request có được phép truy cập tài nguyên hay không |

### Host permission không phải quyền bỏ qua server authorization

Extension có host permission vẫn cần server chấp nhận session/token hợp lệ và kiểm tra quyền user. Host permission không biến request thành admin request.

### Extension service worker fetch

Trong Chrome extension Manifest V3, extension service worker có thể thực hiện cross-origin fetch tới host được khai báo trong host_permissions theo quy tắc extension platform. Content script và page script có các giới hạn khác; không giả định mọi fetch từ mọi context đều được host permission giải quyết giống nhau.

### Không dùng host permission để lấy dữ liệu không được phép

Permission là sự cho phép từ browser đối với extension, không phải sự đồng ý của website hoặc người sở hữu dữ liệu. Tuân thủ authentication, authorization, terms và chính sách dữ liệu của dịch vụ đích.

## 15. Cross-browser và khác biệt nền tảng

Chrome, Firefox, Edge và Safari có các API tương đồng nhưng không hoàn toàn giống nhau:

- Tên namespace có thể là chrome.* hoặc browser.*.
- Manifest V2/V3 và thời điểm hỗ trợ khác nhau.
- webRequest, declarativeNetRequest và blocking behavior khác nhau.
- Permission warning và giao diện site access khác nhau.
- activeTab, optional host permissions và match pattern có chi tiết khác nhau.
- Extension service worker/background lifecycle khác nhau.
- Một số API chỉ có trên một nền tảng hoặc cần polyfill.

### Không giả định manifest chạy giống nhau mọi browser

Xác định:

1. Browser mục tiêu và version tối thiểu.
2. Manifest version hỗ trợ.
3. API và permission thực sự có.
4. Cách browser hiển thị và thu hồi permission.
5. Hành vi khi extension bị suspend/restart.
6. Giới hạn của site access, private browsing và file URL.

Dùng feature detection và adapter phù hợp thay vì chỉ kiểm tra tên browser.

### Private browsing

Extension có thể cần người dùng bật riêng quyền chạy trong private/incognito mode. Không mặc định extension được truy cập dữ liệu private browsing chỉ vì đã cài đặt.

Nếu chức năng không cần hoạt động ở private mode, giữ mặc định tắt. Nếu cần, giải thích rõ dữ liệu nào có thể được truy cập và lưu.

### File URL và trang nội bộ browser

Truy cập file URL thường cần người dùng bật một tùy chọn riêng và có giới hạn. Trang browser nội bộ như chrome:// hoặc trang quản lý extension thường bị bảo vệ, không thể inject tùy ý.

Không tìm cách vượt các giới hạn này bằng debugger, redirect hoặc kỹ thuật khác.

## 16. Permission warning và trải nghiệm người dùng

Browser có thể hiển thị cảnh báo permission khi cài đặt hoặc cập nhật. Cảnh báo là một phần của UX bảo mật, nhưng người dùng thường khó đánh giá quyền kỹ thuật.

Extension nên giải thích:

- Quyền cần dùng cho tính năng nào.
- Website nào sẽ được truy cập.
- Dữ liệu nào sẽ được đọc hoặc thay đổi.
- Dữ liệu có được gửi tới server bên ngoài không.
- Người dùng có thể tắt tính năng hoặc thu hồi quyền ở đâu.

### Xin quyền đúng thời điểm

Tốt:

1. Người dùng bật tính năng “Đọc nội dung portal”.
2. Extension giải thích cần truy cập portal.example.test.
3. Browser hiển thị prompt quyền nếu cần.
4. Extension chỉ chạy chức năng sau khi được cấp quyền.

Không tốt:

1. Extension vừa cài đã yêu cầu &lt;all_urls&gt;, history, cookies, clipboard và downloads.
2. Không giải thích chức năng nào cần quyền nào.
3. Người dùng phải chấp nhận toàn bộ mới dùng được tính năng không liên quan.

### Không gây áp lực cấp quyền

Nếu người dùng từ chối:

- Giải thích chức năng nào bị giới hạn.
- Cho phép tiếp tục dùng phần còn lại.
- Không hiện prompt liên tục.
- Không giả mạo thông báo browser.
- Không tự thay đổi permission scope.

## 17. Permission review và least privilege

Trước khi phát hành extension, lập bảng ánh xạ từng permission với tính năng và code path sử dụng.

Ví dụ:

| Permission | Tính năng | Có thể dùng quyền hẹp hơn? | Quyết định |
| --- | --- | --- | --- |
| storage | Lưu tùy chọn extension | Không cần quyền website | Required |
| activeTab | Đọc tab sau click | Có thể thay host access lâu dài | Required |
| scripting | Inject script theo yêu cầu | Chỉ dùng cùng activeTab | Required |
| downloads | Export file | Có thể là optional | Optional |
| history | Không có tính năng tương ứng | Không | Loại bỏ |
| cookies | Không có tính năng tương ứng | Không | Loại bỏ |
| &lt;all_urls&gt; | Chỉ cần một portal | Dùng exact host pattern | Loại bỏ |

### Câu hỏi rà soát

Với mỗi permission, hỏi:

1. Tính năng nào gọi API cần permission?
2. Có thể dùng activeTab thay host permission lâu dài không?
3. Có thể dùng optional permission thay required không?
4. Có thể giới hạn host hoặc scheme không?
5. Permission có làm lộ URL, cookie, nội dung trang hoặc dữ liệu clipboard không?
6. Nếu extension bị compromise, permission cho phép attacker làm gì?
7. Có thể thực hiện chức năng ở server hoặc qua API hẹp hơn không?
8. Permission có còn được sử dụng trong code hiện tại không?

### Permission không dùng phải xóa

Permission thừa vẫn làm tăng quyền khi extension bị xâm nhập và khiến người dùng khó hiểu. Xóa khỏi manifest, code và tài liệu. Không giữ permission “để sau này có thể cần”.

## 18. Threat model cho extension permission

Các tài sản cần bảo vệ:

- Cookie/session và access token.
- Nội dung trang và dữ liệu người dùng.
- URL, lịch sử và thông tin tab.
- Clipboard.
- File tải xuống.
- Cấu hình browser và proxy.
- Dữ liệu lưu trong extension storage.
- Kênh Native Messaging và dữ liệu trên máy.

### Đối thủ và nguồn dữ liệu không tin cậy

- Website độc hại mà extension được phép chạy.
- Quảng cáo hoặc script bên thứ ba trong website.
- Page DOM bị attacker kiểm soát.
- Content script có lỗi.
- Extension dependency bị compromise.
- Native host có lỗ hổng.
- Message giả hoặc dữ liệu gửi từ frame không mong đợi.
- Người dùng cấp nhầm host permission quá rộng.

### Kịch bản rủi ro

| Kịch bản | Nguyên nhân | Biện pháp |
| --- | --- | --- |
| Đọc dữ liệu mọi website | &lt;all_urls&gt; không cần thiết | Exact host allowlist hoặc activeTab |
| Đọc cookie phiên | cookies + host permission rộng | Không xin cookies nếu không cần; giới hạn host |
| Extension bị page lừa fetch URL khác | Message handler nhận URL tùy ý | Allowlist endpoint và validate redirect |
| XSS qua DOM page | Content script dùng innerHTML | textContent, sanitizer và validation |
| Privileged command bị giả | Message không kiểm tra sender/schema | Validate sender, frame, command và payload |
| Native host bị lạm dụng | NativeMessaging không kiểm tra input | Schema, allowlist và giới hạn hành động |
| Clipboard bị đọc ngoài ý muốn | clipboardRead được cấp thường trực | Optional permission và user gesture |
| Download không mong muốn | downloads được dùng tự động | User confirmation và scope hẹp |
| Network bị chuyển hướng | Proxy permission rộng | Chỉ cấp proxy khi chức năng bắt buộc |
| Quyền tăng âm thầm | Update thêm permission không giải thích | Release review và permission change notice |

## 19. Lab: tạo extension chỉ thao tác tab được chọn

Lab minh họa cách dùng activeTab và scripting thay vì xin quyền đọc mọi website. Chạy trong thư mục test riêng và chỉ cài extension do bạn kiểm soát.

### manifest.json

    {
      "manifest_version": 3,
      "name": "Selected Tab Title",
      "version": "1.0.0",
      "permissions": [
        "activeTab",
        "scripting"
      ],
      "action": {
        "default_title": "Đọc tiêu đề tab"
      },
      "background": {
        "service_worker": "service-worker.js"
      }
    }

### service-worker.js

    chrome.action.onClicked.addListener(async (tab) => {
      if (!tab.id) return;

      try {
        const results = await chrome.scripting.executeScript({
          target: {
            tabId: tab.id
          },
          func: () => ({
            title: document.title,
            origin: location.origin
          })
        });

        console.log(results[0]?.result);
      } catch (error) {
        console.error("Không thể đọc tab hiện tại:", error);
      }
    });

### Thực hành

1. Mở trang quản lý extension của browser.
2. Bật Developer mode nếu browser yêu cầu.
3. Load unpacked extension từ thư mục lab.
4. Mở một website test thông thường.
5. Bấm icon extension.
6. Kiểm tra service worker console và kết quả title/origin.
7. Mở trang browser nội bộ hoặc tab bị bảo vệ và quan sát lỗi bị từ chối.
8. Điều hướng tab sang origin khác rồi thử lại bằng thao tác click mới.
9. Mở manifest và xác nhận không có &lt;all_urls&gt; hoặc host_permissions rộng.

Lab không đọc cookie, không thu thập lịch sử và không gửi dữ liệu lên server.

## 20. Kiểm thử permission bằng DevTools và browser UI

### Bước 1 — Kiểm tra manifest

1. Mở extension source.
2. Kiểm tra manifest.json.
3. Liệt kê permissions, optional_permissions, host_permissions và optional_host_permissions.
4. Kiểm tra content_scripts.matches.
5. Tìm &lt;all_urls&gt;, wildcard scheme và file access.
6. Đối chiếu từng permission với tính năng thực sự.

### Bước 2 — Kiểm tra quyền đã cấp

1. Mở trang quản lý extension.
2. Xem site access và quyền được cấp.
3. Thử chuyển từ “On all sites” sang “On click” hoặc site cụ thể nếu browser hỗ trợ.
4. Kiểm tra private/incognito access đang tắt nếu không cần.
5. Thu hồi optional permission và xác nhận extension xử lý đúng.

### Bước 3 — Kiểm tra activeTab

1. Cài extension lab.
2. Mở website test.
3. Không click extension và quan sát extension không tự inject.
4. Click action để cấp temporary grant.
5. Điều hướng sang origin khác.
6. Thử lại mà không click và xác nhận quyền cũ không được giả định còn hiệu lực.

### Bước 4 — Kiểm tra messaging

1. Gửi message hợp lệ từ content script.
2. Gửi message sai type.
3. Gửi message có field sai kiểu hoặc vượt giới hạn.
4. Gửi message từ frame không được phép.
5. Xác nhận service worker từ chối command không hợp lệ.
6. Kiểm tra không có generic command thực thi URL hoặc script tùy ý.

### Bước 5 — Kiểm tra network

1. Mở DevTools của extension service worker.
2. Gửi request tới host được cấp quyền.
3. Thử host không nằm trong host permission.
4. Quan sát CORS, host permission và server authorization riêng biệt.
5. Xác nhận redirect không đưa credential tới host ngoài allowlist.

### Ma trận kiểm thử

| Ca kiểm thử | Điều kiện | Kết quả mong đợi |
| --- | --- | --- |
| API permission có | storage được khai báo | Extension dùng storage API |
| API permission thiếu | downloads không được cấp | Feature download bị giới hạn và UI báo rõ |
| Host permission chính xác | portal host được cấp | Extension truy cập host trong phạm vi policy |
| Host permission thiếu | Host khác | Request/injection bị browser chặn theo API |
| activeTab | Người dùng click action | Temporary grant cho tab được chọn |
| activeTab hết hiệu lực | Tab đổi origin hoặc đóng | Extension không giả định quyền cũ còn |
| Optional permission | Người dùng chấp nhận | Feature liên quan hoạt động |
| Optional permission từ chối | Người dùng từ chối | Feature fallback, không lặp prompt |
| Permission revoked | Người dùng thu hồi | Extension xử lý lỗi và dừng chức năng liên quan |
| &lt;all_urls&gt; | Review manifest | Chỉ giữ nếu có lý do thực sự và được phê duyệt |
| tabs vs host | Chỉ có tabs | Không mặc định có quyền đọc DOM mọi tab |
| cookies | Thiếu host permission | Cookie API không được dùng cho host ngoài phạm vi |
| Content script DOM | Page trả dữ liệu giả | Extension xử lý như input không tin cậy |
| Message schema | Payload sai | Service worker từ chối |
| Sender validation | Message từ frame không mong đợi | Từ chối command nhạy cảm |
| MAIN world | Page sửa dữ liệu bridge | Extension không tin dữ liệu page |
| Cross-origin Fetch | Host permission/CORS khác nhau | Xác định rõ context và policy; server vẫn authorization |
| Private browsing | Chưa bật quyền | Extension không hoạt động trong private mode |
| File URL | Chưa bật quyền file | Không inject vào file URL |
| Browser internal page | chrome:// hoặc trang được bảo vệ | Injection bị từ chối |
| MV3 service worker | Worker bị suspend/restart | State được khôi phục và event xử lý đúng |
| Permission update | Version thêm quyền | Browser hiển thị thay đổi theo policy nền tảng |

## 21. Sai lầm thường gặp

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Xin &lt;all_urls&gt; cho tiện | Extension có phạm vi website quá rộng | Exact host allowlist hoặc activeTab |
| Nhầm permissions với host_permissions | Khai báo thiếu hoặc cấp quá quyền | Rà soát API và host riêng |
| Nghĩ activeTab là quyền vĩnh viễn | Dùng quyền sau khi tab đổi context | Xử lý temporary grant theo browser |
| Nghĩ tabs cho phép đọc DOM mọi website | Bỏ qua host permission/scripting | Kiểm tra từng lớp quyền |
| Dùng cookies trên mọi host | Tăng nguy cơ lộ session | Chỉ cấp host và cookies khi thật sự cần |
| Coi isolated world làm DOM đáng tin | DOM XSS hoặc command injection | Validate dữ liệu page và tránh innerHTML |
| Tin mọi message từ content script | Page có thể gián tiếp điều khiển API đặc quyền | Validate sender, schema và allowlist command |
| Cho service worker fetch URL tùy ý | Confused deputy và credential leakage | Allowlist host/endpoint/method/redirect |
| Dùng MAIN world để chứa secret | Page có thể đọc hoặc sửa dữ liệu | Không đưa secret/privileged API vào MAIN world |
| Nghĩ host permission thay CORS | Nhầm quyền extension và page script | Phân biệt context request |
| Nghĩ host permission thay server authorization | Truy cập dữ liệu vượt quyền user | Backend kiểm tra mọi request |
| Xin tất cả quyền khi cài đặt | UX xấu và tăng blast radius | Optional permission theo tính năng |
| Không xử lý permission bị revoke | Extension lỗi hoặc tiếp tục hành động sai | Kiểm tra và lắng nghe thay đổi quyền |
| Dùng API MV2 trong MV3 như cũ | Extension không hoạt động trên browser mục tiêu | Kiểm tra manifest/API theo version |
| Mặc định bật private access | Có thể đọc hoạt động riêng tư ngoài mong đợi | Tắt nếu không cần, giải thích trước khi bật |
| Không rà soát permission khi release | Version mới âm thầm mở rộng quyền | Permission diff và review trước phát hành |

## 22. Câu hỏi củng cố

**Câu 1.** permissions và host_permissions khác nhau thế nào?

**Giải đáp:** permissions cấp năng lực dùng API extension; host_permissions xác định website mà extension được truy cập theo policy browser.

**Câu 2.** activeTab có tác dụng gì?

**Giải đáp:** Cấp quyền host tạm thời cho tab người dùng chủ động chọn, giúp tránh quyền truy cập mọi website lâu dài.

**Câu 3.** Vì sao không nên dùng &lt;all_urls&gt;?

**Giải đáp:** Nó mở rộng phạm vi website rất lớn, tăng nguy cơ lộ dữ liệu và tác động khi extension bị compromise.

**Câu 4.** tabs permission có đồng nghĩa với quyền đọc DOM mọi tab không?

**Giải đáp:** Không. Đọc DOM hoặc inject script còn cần host permission hoặc temporary grant và API phù hợp như scripting.

**Câu 5.** Content script chạy trong isolated world có an toàn khi đọc DOM không?

**Giải đáp:** Không mặc nhiên. JavaScript environment tách biệt nhưng DOM vẫn được page kiểm soát; dữ liệu DOM phải được coi là input không tin cậy.

**Câu 6.** Vì sao phải kiểm tra message từ content script?

**Giải đáp:** Message có thể mang dữ liệu do page điều khiển. Service worker có quyền đặc quyền cần xác minh sender, frame, schema và command.

**Câu 7.** Host permission có thay CORS không?

**Giải đáp:** Không. Host permission áp dụng cho extension context theo API; CORS kiểm soát việc JavaScript page đọc response cross-origin.

**Câu 8.** Host permission có thay authorization của server không?

**Giải đáp:** Không. Backend vẫn phải xác thực và kiểm tra quyền trên từng tài nguyên.

**Câu 9.** Khi nào nên dùng optional permission?

**Giải đáp:** Khi chức năng chỉ cần quyền ở một số thời điểm hoặc do người dùng chủ động bật; extension có thể xin quyền khi user gesture phù hợp.

**Câu 10.** Extension cần làm gì khi permission bị thu hồi?

**Giải đáp:** Dừng chức năng phụ thuộc quyền, cập nhật UI, xử lý lỗi và không tiếp tục request/injection dựa trên quyền cũ.

## 23. Tổng kết

Extension permission là ranh giới đặc quyền giữa extension với browser, website và dữ liệu người dùng. Cần phân biệt API permission, host permission, temporary grant như activeTab, site permission và server authorization. Mỗi lớp trả lời một câu hỏi khác nhau; không thể dùng quyền ở lớp này để thay thế lớp khác.

Ưu tiên least privilege: chỉ khai báo API thực sự cần, giới hạn host và scheme, dùng optional permission cho tính năng tùy chọn và activeTab khi người dùng chủ động chọn tab. Tránh &lt;all_urls&gt;, cookies, history, debugger, proxy hoặc nativeMessaging nếu chức năng không bắt buộc. Permission bị thu hồi phải được xử lý như một trạng thái runtime bình thường.

Content script và service worker tạo thành ranh giới tin cậy quan trọng. DOM và message từ page phải được xem là dữ liệu không tin cậy; kiểm tra sender, frame, schema và command trước khi thực hiện hành động đặc quyền. Host permission không thay CORS hoặc authorization phía server. Cuối cùng, rà soát permission ở mỗi lần release, giải thích quyền bằng ngôn ngữ người dùng và kiểm thử cả trường hợp được cấp, bị từ chối và bị thu hồi.

## Tài liệu tham khảo

1. [Chrome Extensions — Declare permissions](https://developer.chrome.com/docs/extensions/develop/concepts/declare-permissions): permissions, host permissions và optional permissions.
2. [Chrome Extensions — activeTab](https://developer.chrome.com/docs/extensions/develop/concepts/activeTab): quyền tạm thời sau thao tác người dùng.
3. [Chrome Extensions — Match patterns](https://developer.chrome.com/docs/extensions/develop/concepts/match-patterns): cú pháp host match patterns.
4. [Chrome Extensions — Content scripts](https://developer.chrome.com/docs/extensions/develop/concepts/content-scripts): content script, isolated world và host access.
5. [Chrome Extensions — Message passing](https://developer.chrome.com/docs/extensions/develop/concepts/messaging): messaging giữa content script và extension contexts.
6. [Chrome Extensions — Network requests](https://developer.chrome.com/docs/extensions/develop/concepts/network-requests): host permissions và cross-origin requests trong extension.
7. [Chrome Extensions — Manifest V3 migration](https://developer.chrome.com/docs/extensions/develop/migrate/what-is-mv3): service worker và thay đổi kiến trúc Manifest V3.
8. [MDN — permissions](https://developer.mozilla.org/en-US/docs/Mozilla/Add-ons/WebExtensions/manifest.json/permissions): permission model của WebExtensions.
9. [MDN — optional_permissions](https://developer.mozilla.org/en-US/docs/Mozilla/Add-ons/WebExtensions/manifest.json/optional_permissions): quyền tùy chọn và yêu cầu runtime.
