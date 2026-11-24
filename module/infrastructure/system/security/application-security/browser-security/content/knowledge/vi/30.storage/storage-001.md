# Web storage: vùng lưu trữ, vòng đời và ranh giới bảo mật

## 1. Web storage là gì?

**Web Storage API** cung cấp hai vùng lưu trữ key-value cho JavaScript trong trình duyệt: `localStorage` và `sessionStorage`. Cả hai lưu key và value dưới dạng chuỗi, được phân tách theo origin và có API đồng bộ, đơn giản.

Ví dụ:

```js
localStorage.setItem("theme", "dark");

const theme = localStorage.getItem("theme");
console.log(theme); // "dark"
```

Dữ liệu trong `localStorage` thường tồn tại qua lần tải lại trang và các phiên browser cho đến khi người dùng hoặc ứng dụng xóa. `sessionStorage` gắn với page session của một top-level browsing context; dữ liệu thường mất khi tab/window đóng.

Web Storage hữu ích cho tùy chọn giao diện, trạng thái tạm và dữ liệu nhỏ không nhạy cảm. Nó không phải database có transaction, không phải vùng bí mật và không nên là nơi lưu session token hoặc dữ liệu xác thực quan trọng.

Bài viết thuộc chương **Storage** của module **SECURITY_APPLICATION_SECURITY_BROWSER_SECURITY**. Chủ đề kết nối Web Storage với các vùng lưu trữ khác của browser, vòng đời dữ liệu, origin, Same-Origin Policy (SOP), XSS, cookie, quota và cơ chế xóa/partition dữ liệu.

Sau bài học, bạn có thể:

- Phân biệt `localStorage` và `sessionStorage` theo phạm vi và vòng đời.
- Giải thích origin nào có thể đọc hoặc ghi một storage area.
- Dùng các phương thức `getItem`, `setItem`, `removeItem` và `clear` an toàn.
- Lưu dữ liệu có cấu trúc bằng JSON và kiểm tra dữ liệu sau khi đọc.
- Hiểu storage event, đồng bộ giữa tab và race condition.
- So sánh Web Storage với cookie, IndexedDB, Cache Storage và các vùng lưu trữ khác.
- Nhận diện quota, eviction, private browsing và storage partitioning.
- Đánh giá rủi ro XSS, CSRF và dữ liệu nhạy cảm trong browser storage.
- Thực hành kiểm chứng localStorage/sessionStorage bằng DevTools và hai origin local.

## 2. Bản đồ các vùng lưu trữ trong browser

Browser không có một vùng lưu trữ duy nhất. Mỗi API phục vụ mục đích khác nhau và có quy tắc về phạm vi, vòng đời, khả năng truy cập và đồng bộ riêng.

| Cơ chế | Dữ liệu thường lưu | Phạm vi chính | Đặc điểm |
|---|---|---|---|
| `localStorage` | Tùy chọn, trạng thái nhỏ | Origin | Key-value chuỗi, đồng bộ, thường tồn tại qua phiên browser |
| `sessionStorage` | Trạng thái của một tab/page session | Origin + top-level browsing context | Key-value chuỗi, đồng bộ, page session riêng |
| Cookies | Session identifier, tùy chọn server cần đọc | Domain/Path và các thuộc tính cookie | Browser tự gửi theo request phù hợp; có Secure, HttpOnly, SameSite |
| IndexedDB | Dữ liệu có cấu trúc, object lớn, offline data | Origin/storage partition | API bất đồng bộ, transaction, structured clone |
| Cache Storage | Request/Response cache | Origin/storage partition | Thường dùng với Service Worker và offline strategy |
| OPFS (Origin Private File System) | File riêng của ứng dụng, dữ liệu nhị phân | Origin/storage partition | File system riêng do browser quản lý, hỗ trợ khác nhau |
| JavaScript memory | State hiện tại, object đang xử lý | Document/worker runtime | Mất khi runtime kết thúc; không phải nơi lưu bền vững |

**Web Storage** trong bài này tập trung vào `localStorage` và `sessionStorage`. Những API khác được đặt trong bản đồ để tránh nhầm rằng mọi dữ liệu browser đều có cùng vòng đời hoặc cùng mô hình bảo mật.

### 2.1. Web Storage không phải cookie

Cookie có thể được browser tự động gửi đến server trong request phù hợp. Web Storage không tự động được đính kèm vào HTTP request; JavaScript phải chủ động đọc và gửi dữ liệu nếu ứng dụng cần.

Cookie có các thuộc tính như `HttpOnly`, `Secure`, `SameSite`, `Domain` và `Path`. Web Storage không có cơ chế `HttpOnly`: script cùng origin có thể đọc dữ liệu trong storage.

Vì vậy:

- Cookie phù hợp với một số session identifier do server quản lý, khi được cấu hình an toàn.
- Web Storage phù hợp với dữ liệu nhỏ phía client, không nhạy cảm.
- Không chuyển token nhạy cảm sang localStorage chỉ để tránh CSRF; XSS có thể đọc và lấy token đó.

### 2.2. IndexedDB và Cache Storage

IndexedDB phù hợp với dữ liệu có cấu trúc, lượng lớn hơn và thao tác bất đồng bộ. Nó hỗ trợ object store, index và transaction. Ứng dụng có thể lưu dữ liệu offline, bản nháp hoặc dữ liệu cần truy vấn.

Cache Storage lưu các cặp Request/Response, thường được Service Worker sử dụng để hỗ trợ offline và tối ưu tải tài nguyên. Cache có thể chứa response nhạy cảm nếu ứng dụng cache sai; cần chiến lược versioning, invalidation và kiểm soát dữ liệu riêng tư.

### 2.3. Browser memory và storage bền vững

State trong JavaScript memory mất khi document/worker bị hủy. Đây là nơi phù hợp cho dữ liệu đang xử lý, nhưng không tồn tại sau reload trừ khi ứng dụng tái tạo từ nguồn khác.

Dữ liệu lưu bằng API browser có thể sống lâu hơn runtime, nhưng vẫn chịu quyền xóa của người dùng, quota, chính sách riêng tư, chế độ private browsing và quy tắc eviction của browser. Không coi bất kỳ client-side storage nào là nơi lưu trữ bền vững duy nhất cho dữ liệu nghiệp vụ quan trọng.

## 3. Origin là ranh giới của Web Storage

### 3.1. Origin gồm scheme, host và port

Origin thông thường được xác định bởi ba thành phần:

- **Scheme:** `http` hoặc `https`.
- **Host:** hostname hoặc địa chỉ IP.
- **Port:** cổng hiệu lực.

Path không thuộc origin. Ví dụ:

```text
https://app.example.com/profile
https://app.example.com/settings
```

Hai URL này cùng origin và dùng chung localStorage. Nhưng các URL sau khác origin:

```text
http://app.example.com
https://app.example.com
https://app.example.com:8443
https://admin.example.com
```

HTTP và HTTPS có storage area riêng. Khác port hoặc hostname cũng tạo origin khác.

### 3.2. localStorage được chia sẻ giữa các document cùng origin

Các tab/window cùng origin thường truy cập cùng một localStorage area:

```js
// Tab A
localStorage.setItem("app:theme", "dark");

// Tab B, cùng origin
console.log(localStorage.getItem("app:theme")); // "dark"
```

Path không tạo ranh giới bảo mật. `https://app.example.com/account` và `https://app.example.com/help` dùng chung localStorage. Nếu nhiều ứng dụng cùng chạy trên một origin, chúng cần namespace key và phối hợp quy ước dữ liệu.

Không dùng key namespacing như một cơ chế phân quyền. Script chạy được trong cùng origin vẫn có thể đọc hoặc xóa key của ứng dụng khác.

### 3.3. sessionStorage có thêm ranh giới browsing context

`sessionStorage` được phân tách theo origin và top-level browsing context. Hai tab độc lập cùng origin có sessionStorage riêng:

```js
// Tab A
sessionStorage.setItem("draft-step", "2");

// Tab B, cùng origin nhưng tab riêng
console.log(sessionStorage.getItem("draft-step")); // null
```

Một iframe cùng origin bên trong cùng top-level tab có thể chia sẻ sessionStorage area tương ứng với origin đó trong page session.

Nếu mở một tab/window mới có opener, browser thường khởi tạo sessionStorage của tab mới bằng bản sao ban đầu từ opener. Sau đó hai tab có storage area độc lập; thay đổi ở tab này không tự đồng bộ sang tab kia. Dùng `noopener` khi không muốn cửa sổ mới nhận bản sao sessionStorage ban đầu.

### 3.4. Opaque origin và sandbox

Tài liệu có opaque origin, ví dụ một số iframe sandbox thiếu `allow-same-origin`, không có origin tuple thông thường để dùng Web Storage. Truy cập `localStorage` hoặc `sessionStorage` có thể ném `SecurityError`.

Ví dụ:

```html
<iframe src="/preview.html" sandbox="allow-scripts"></iframe>
```

Dù URL ban đầu cùng host với parent, sandbox có thể ép tài liệu con thành opaque origin. Đừng giả định storage hoạt động chỉ vì đường dẫn URL giống nhau.

Với URL đặc biệt như `file:`, hành vi storage có thể khác giữa browser. Dùng HTTP localhost hoặc HTTPS cho lab và ứng dụng thực tế; không dựa vào hành vi file URL làm hợp đồng bảo mật.

## 4. localStorage và sessionStorage khác nhau thế nào?

| Thuộc tính | localStorage | sessionStorage |
|---|---|---|
| Phạm vi | Origin | Origin + top-level browsing context |
| Chia sẻ giữa tab độc lập | Có, nếu cùng origin và không bị partition khác | Không; mỗi page session riêng |
| Tồn tại sau reload | Có | Có |
| Tồn tại sau khi đóng tab | Thường có | Page session kết thúc; browser có thể khôi phục session theo tính năng restore |
| Tồn tại sau khi đóng browser | Thường có | Thường không, trừ hành vi khôi phục session do browser cung cấp |
| Đồng bộ API | Có | Có |
| Kiểu dữ liệu | String key/value | String key/value |
| Transaction nhiều thao tác | Không | Không |
| Có thể bị XSS cùng origin đọc | Có | Có |

### 4.1. Vòng đời localStorage

localStorage thường tồn tại qua:

- Điều hướng sang trang khác cùng origin.
- Reload document.
- Đóng và mở lại tab.
- Đóng và mở lại browser.

Dữ liệu có thể bị xóa khi người dùng clear site data, ứng dụng gọi remove/clear, browser áp dụng chính sách riêng tư hoặc môi trường private browsing kết thúc. Một số browser còn giới hạn hoặc thay đổi khả năng lưu theo cài đặt.

Hãy dùng localStorage cho dữ liệu có thể tái tạo hoặc người dùng có thể nhập lại. Không dùng nó làm nguồn duy nhất cho đơn hàng, thanh toán, quyền truy cập hoặc dữ liệu server cần bảo đảm tính nhất quán.

### 4.2. Vòng đời sessionStorage

sessionStorage tồn tại trong page session của top-level browsing context:

- Reload hoặc restore trang trong cùng tab thường giữ dữ liệu.
- Điều hướng trong cùng tab không tự xóa dữ liệu.
- Tab khác có sessionStorage riêng.
- Tab mới mở từ opener có thể nhận bản sao ban đầu, rồi hoạt động độc lập.
- Đóng tab/page session thường kết thúc vùng lưu trữ đó; session restore của browser có thể khôi phục trạng thái.

Tên `sessionStorage` không có nghĩa dữ liệu được server session quản lý hoặc tự động gắn với tài khoản. Đây vẫn là dữ liệu client-side, có thể bị script cùng origin đọc và sửa.

## 5. Thao tác Web Storage

### 5.1. Các phương thức cơ bản

| Phương thức | Ý nghĩa |
|---|---|
| `setItem(key, value)` | Ghi hoặc thay thế value của key |
| `getItem(key)` | Đọc value; trả `null` nếu key không tồn tại |
| `removeItem(key)` | Xóa một key |
| `clear()` | Xóa toàn bộ key trong storage area hiện tại |
| `key(index)` | Lấy tên key tại vị trí index |
| `length` | Số lượng key hiện có |

Ví dụ:

```js
const storage = window.localStorage;

storage.setItem("app:theme", "dark");
const theme = storage.getItem("app:theme");

storage.removeItem("app:theme");
```

Nên dùng các phương thức chính thức thay vì cú pháp property như `localStorage.theme`. Property access có thể xung đột với tên thuộc tính của object và khiến hành vi khó đoán. Web Storage là API đồng bộ, nên thao tác đọc/ghi chạy ngay trên main thread; tránh lưu payload lớn hoặc gọi liên tục trong vòng lặp giao diện. Với dữ liệu lớn và thao tác thường xuyên, cân nhắc IndexedDB bất đồng bộ.

### 5.2. Web Storage chỉ lưu chuỗi

Giá trị được chuyển thành string. Nếu truyền object trực tiếp, kết quả thường là `"[object Object]"`:

```js
localStorage.setItem("preferences", { theme: "dark" });

console.log(localStorage.getItem("preferences"));
// "[object Object]"
```

Dùng JSON khi cần lưu dữ liệu có cấu trúc:

```js
const preferences = {
  theme: "dark",
  compactMode: true
};

localStorage.setItem(
  "app:preferences:v1",
  JSON.stringify(preferences)
);
```

Khi đọc lại, parse JSON và kiểm tra schema:

```js
function readPreferences() {
  try {
    const raw = window.localStorage.getItem("app:preferences:v1");

    if (raw === null) {
      return { theme: "system", compactMode: false };
    }

    const value = JSON.parse(raw);

    if (
      value === null ||
      typeof value !== "object" ||
      Array.isArray(value)
    ) {
      throw new TypeError("Preferences phải là object");
    }

    const theme = ["light", "dark", "system"].includes(value.theme)
      ? value.theme
      : "system";

    return {
      theme,
      compactMode: value.compactMode === true
    };
  } catch {
    return { theme: "system", compactMode: false };
  }
}
```

JSON parse thành công không có nghĩa dữ liệu đáng tin. Dữ liệu có thể bị sửa bằng DevTools, extension, script XSS hoặc phiên bản ứng dụng cũ. Kiểm tra kiểu, enum, giới hạn độ dài và schema trước khi sử dụng.

### 5.3. Xử lý lỗi khi đọc và ghi

Truy cập storage có thể thất bại do browser policy, opaque origin, cài đặt người dùng hoặc quota. Getter `window.localStorage` cũng có thể ném `SecurityError`, nên hãy bắt lỗi quanh cả việc lấy storage và thao tác.

```js
function savePreference(key, value) {
  try {
    window.localStorage.setItem(key, value);
    return true;
  } catch (error) {
    if (error.name === "QuotaExceededError") {
      console.warn("Storage đã hết quota.");
    } else if (error.name === "SecurityError") {
      console.warn("Browser không cho phép truy cập storage.");
    } else {
      console.warn("Không thể lưu dữ liệu.");
    }
    return false;
  }
}
```

Không xóa toàn bộ storage chỉ để xử lý quota nếu ứng dụng cùng origin có thể chứa dữ liệu khác. Xóa key thuộc namespace của ứng dụng, cho người dùng biết dữ liệu nào sẽ bị loại bỏ và có fallback phù hợp.

### 5.4. Xóa dữ liệu có namespace

`clear()` xóa mọi key trong storage area của origin hiện tại, kể cả key do module hoặc ứng dụng khác cùng origin tạo ra. Thường nên xóa key thuộc namespace của ứng dụng:

```js
const APP_KEYS = [
  "app:preferences:v1",
  "app:draft:v2",
  "app:last-page"
];

function clearAppStorage() {
  for (const key of APP_KEYS) {
    localStorage.removeItem(key);
    sessionStorage.removeItem(key);
  }
}
```

Namespace giúp tránh xóa nhầm dữ liệu của ứng dụng khác. Nó không tạo ranh giới quyền truy cập giữa script cùng origin.

## 6. Storage event và đồng bộ giữa tab

### 6.1. localStorage phát storage event ở document khác

Khi một document thay đổi localStorage, các document khác đang dùng cùng storage area có thể nhận sự kiện `storage`. Document tạo thay đổi không nhận event của chính nó.

Ví dụ:

```js
window.addEventListener("storage", (event) => {
  if (event.key !== "app:theme") return;

  console.log("Theme changed in another document:", event.newValue);
});
```

Các thuộc tính hữu ích:

| Thuộc tính | Ý nghĩa |
|---|---|
| `event.key` | Key thay đổi; `null` nếu gọi clear |
| `event.oldValue` | Giá trị trước thay đổi |
| `event.newValue` | Giá trị mới; `null` nếu key bị xóa hoặc clear |
| `event.url` | URL của document tạo thay đổi |
| `event.storageArea` | Storage object tương ứng |

Với localStorage, các tab cùng origin có thể nhận event. Đây là tín hiệu để đồng bộ UI, không phải message bus đáng tin cậy hoặc cơ chế khóa giao dịch.

### 6.2. sessionStorage event có phạm vi hẹp hơn

Storage event của sessionStorage chỉ được gửi tới các document khác có cùng session storage area trong cùng top-level browsing context, ví dụ iframe cùng origin. Nó không dùng để đồng bộ sessionStorage giữa hai tab độc lập.

Nếu cần đồng bộ giữa nhiều tab, localStorage event hoặc BroadcastChannel có thể phù hợp hơn. Dù dùng cơ chế nào, chỉ gửi tín hiệu trạng thái không nhạy cảm và xác thực/kiểm tra dữ liệu trước khi xử lý.

### 6.3. Tránh race condition

Web Storage API đồng bộ và không có transaction cho chuỗi thao tác read-modify-write. Hai tab có thể đọc cùng một giá trị cũ, cùng cập nhật rồi ghi đè kết quả của nhau.

Ví dụ:

```js
const count = Number(localStorage.getItem("app:count") || 0);
localStorage.setItem("app:count", String(count + 1));
```

Đoạn code này không bảo đảm bộ đếm chính xác khi nhiều tab cập nhật đồng thời. Nếu cần transaction, index, truy vấn hoặc đồng bộ nhiều client, dùng IndexedDB hoặc để server quản lý trạng thái có tính nhất quán.

### 6.4. Không dùng storage event để truyền bí mật

Storage event có thể chứa oldValue/newValue. Không ghi access token, OTP, password, session secret hoặc dữ liệu riêng tư vào key chỉ để thông báo cho tab khác.

Event đến từ một storage area dùng chung; ứng dụng cần kiểm tra key, schema và giá trị. Không đưa nội dung event trực tiếp vào HTML hoặc thực thi nó như code.

## 7. Quota, eviction và persistence

### 7.1. Quota không phải hằng số chung cho mọi browser

Browser đặt giới hạn storage theo API, origin, thiết bị, dung lượng trống và chính sách implementation. Không nên giả định một con số cố định áp dụng cho mọi browser hoặc mọi loại storage.

Khi ghi vượt giới hạn, Web Storage có thể ném `QuotaExceededError`. Ứng dụng nên lưu dữ liệu nhỏ, xử lý lỗi và tránh dùng localStorage như database cho file hoặc object lớn.

### 7.2. Ước lượng dung lượng storage

Storage Manager API có thể cung cấp thông tin ước lượng:

```js
async function inspectStorage() {
  if (!navigator.storage?.estimate) {
    return null;
  }

  const estimate = await navigator.storage.estimate();

  return {
    usageBytes: estimate.usage,
    quotaBytes: estimate.quota
  };
}

console.log(await inspectStorage());
```

Các con số là ước lượng cho storage của origin theo browser, không phải phép đo riêng chính xác cho localStorage. Không dùng quota estimate để quyết định có thể ghi một payload cụ thể mà không bắt lỗi.

### 7.3. Persistent storage

Một số browser hỗ trợ yêu cầu chế độ persistent cho origin:

```js
async function requestPersistentStorage() {
  if (!navigator.storage?.persist) {
    return false;
  }

  return navigator.storage.persist();
}
```

Browser có thể tự quyết định cấp hoặc từ chối dựa trên chính sách, mức độ tương tác và các tín hiệu khác. `persist()` không phải quyền truy cập thiết bị, không ngăn người dùng xóa dữ liệu và không biến Web Storage thành database có backup.

### 7.4. Eviction và xóa dữ liệu

Cần phân biệt:

- **Xóa chủ động:** người dùng clear browsing data/site data hoặc ứng dụng xóa key.
- **Private browsing:** dữ liệu có thể chỉ tồn tại trong phiên riêng tư và bị xóa khi phiên kết thúc.
- **Quota/eviction:** browser có thể dọn một số dữ liệu theo chính sách dung lượng và loại storage.
- **Storage partitioning:** dữ liệu bên thứ ba có thể được tách theo top-level site.
- **Thiết bị/browser policy:** enterprise setting hoặc chế độ riêng tư có thể hạn chế lưu trữ.

localStorage thường được giữ qua phiên browser thông thường, nhưng không có cam kết giữ vĩnh viễn. Hãy cung cấp fallback và đồng bộ dữ liệu nghiệp vụ quan trọng với server khi phù hợp.

## 8. Storage partitioning và third-party context

### 8.1. Third-party storage có thể bị phân vùng

Browser ngày càng giới hạn việc một bên thứ ba theo dõi người dùng qua nhiều website. Một số browser partition storage theo top-level site.

Ví dụ cùng một widget tại `https://widget.example.net` được nhúng vào hai website:

```text
https://shop.example.com
https://news.example.org
```

Trong browser áp dụng partitioning, widget có thể nhận storage area riêng cho từng top-level site. Dữ liệu tạo khi nhúng trong shop không nhất thiết xuất hiện khi nhúng trong news.

### 8.2. Origin vẫn là cơ sở, partition có thể bổ sung khóa

Origin là ranh giới cơ bản của Web Storage. Privacy partitioning có thể bổ sung top-level site vào khóa lưu trữ của context bên thứ ba. Cách áp dụng cụ thể thay đổi theo browser, phiên bản, chế độ riêng tư và API.

Không giả định một third-party iframe luôn chia sẻ localStorage toàn cục giữa mọi website. Hãy kiểm thử browser mục tiêu và thiết kế widget sao cho không phụ thuộc vào khả năng theo dõi cross-site.

### 8.3. Storage Access API không phải đường tắt chung

Một số browser cung cấp Storage Access API để tài liệu nhúng yêu cầu quyền truy cập một số trạng thái storage/cookie không bị partition trong điều kiện nhất định. API có thể cần user activation, permission hoặc điều kiện chính sách cụ thể.

Không dùng API này để vượt quyết định riêng tư của người dùng. Nếu ứng dụng cần đăng nhập trong iframe, hãy xem xét kiến trúc redirect/top-level sign-in hoặc flow được browser hỗ trợ và giải thích rõ cho người dùng.

## 9. Ranh giới bảo mật: XSS, CSRF và dữ liệu nhạy cảm

### 9.1. XSS có thể đọc và sửa Web Storage

Web Storage không có HttpOnly. Nếu attacker thực thi JavaScript trong origin của ứng dụng qua XSS, script đó có thể đọc, sửa hoặc xóa localStorage/sessionStorage:

```js
// Minh họa rủi ro: script cùng origin có thể đọc key.
const draft = localStorage.getItem("app:draft:v2");
console.log(draft);
```

Nếu access token hoặc dữ liệu nhạy cảm được lưu trong localStorage, XSS có thể lấy chúng. Chuyển dữ liệu sang sessionStorage không giải quyết vấn đề: script cùng origin vẫn có thể đọc nó khi trang hoạt động.

Các biện pháp phòng vệ:

- Tránh lưu credential, refresh token, session secret hoặc dữ liệu cá nhân nhạy cảm trong Web Storage.
- Sửa XSS source-to-sink flow bằng output encoding và DOM API an toàn.
- Dùng CSP và Trusted Types như lớp giảm thiểu phù hợp.
- Giới hạn quyền của script bên thứ ba và dependency.
- Chỉ lưu dữ liệu UI không nhạy cảm, có thể tái tạo hoặc người dùng có thể nhập lại.

CSP không ngăn một script hợp lệ cùng origin đọc localStorage nếu script đó đã chạy. Vì vậy, ngăn XSS và giảm dữ liệu nhạy cảm lưu phía client là hai yêu cầu song song.

### 9.2. Web Storage và CSRF

Web Storage không tự động được browser gửi cùng request như cookie. Vì thế, dữ liệu trong localStorage không có cùng kiểu CSRF exposure do cookie tự động đính kèm.

Tuy nhiên, điều đó không biến Web Storage thành giải pháp authentication an toàn. Nếu JavaScript đọc token từ storage rồi thêm vào request, XSS có thể lấy token hoặc thực hiện request thay mặt người dùng. Cookie HttpOnly giảm khả năng script đọc session identifier, nhưng cookie-based authentication vẫn cần CSRF defense như SameSite, CSRF token và kiểm tra nguồn request phù hợp.

### 9.3. Không lưu password, OTP hoặc token dài hạn

Không lưu các dữ liệu sau trong localStorage/sessionStorage:

- Password hoặc PIN.
- OTP, recovery code hoặc mã xác thực dùng một lần.
- Access token/refresh token có quyền rộng hoặc thời hạn dài.
- Session identifier cần được bảo vệ khỏi JavaScript.
- Thông tin thanh toán hoặc dữ liệu sức khỏe nhạy cảm.
- Nội dung bí mật mà script cùng origin không được phép đọc.

Nếu sản phẩm cần giữ đăng nhập, ưu tiên thiết kế session phía server với cookie được cấu hình phù hợp, ví dụ Secure, HttpOnly và SameSite, rồi triển khai CSRF protection tương ứng.

### 9.4. Dữ liệu trong storage luôn là input không tin cậy

Người dùng có thể sửa storage qua DevTools, extension, script XSS hoặc một phiên bản ứng dụng khác. Không dùng giá trị localStorage để quyết định quyền admin, giá sản phẩm, trạng thái thanh toán hoặc quyền truy cập tài nguyên.

Server phải xác minh mọi dữ liệu ảnh hưởng tới authorization, giá trị tài chính hoặc trạng thái nghiệp vụ. Client-side validation chỉ cải thiện UX, không thay thế kiểm tra server-side.

## 10. Thiết kế lưu trữ an toàn

### 10.1. Chỉ lưu những gì thực sự cần

Trước khi thêm key, hãy xác định:

- Dữ liệu có thể tái tạo từ server không?
- Có chứa credential hoặc dữ liệu nhạy cảm không?
- Có cần tồn tại qua reload không?
- Có cần chia sẻ giữa tab không?
- Có cần query/transaction hay chỉ là một tùy chọn nhỏ?
- Người dùng xóa dữ liệu thì ứng dụng sẽ phản ứng ra sao?

Nếu chỉ cần một tùy chọn giao diện, localStorage phù hợp. Nếu chỉ cần state trong tab, sessionStorage hoặc memory có thể đủ. Nếu cần nhiều record và transaction, hãy cân nhắc IndexedDB.

### 10.2. Version key và migration

Dùng key có version để thay đổi schema có kiểm soát:

```js
const KEY = "app:preferences:v2";

function writePreferences(value) {
  const safeValue = {
    theme: ["light", "dark", "system"].includes(value.theme)
      ? value.theme
      : "system",
    compactMode: value.compactMode === true
  };

  localStorage.setItem(KEY, JSON.stringify(safeValue));
}
```

Khi schema thay đổi, đọc version cũ, validate rồi chuyển đổi có kiểm soát. Không parse rồi merge object tùy ý vào config hoặc prototype của ứng dụng.

### 10.3. Không dựa vào clear() cho logout an toàn

Nếu ứng dụng cần đăng xuất:

1. Gửi yêu cầu logout tới server để vô hiệu hóa session nếu kiến trúc yêu cầu.
2. Xóa cookie/session theo cơ chế server.
3. Xóa các key UI/cache thuộc namespace ứng dụng.
4. Dừng tác vụ đang chạy và điều hướng về trạng thái chưa đăng nhập.
5. Nếu cần đồng bộ tab, phát tín hiệu logout không chứa secret.

`localStorage.clear()` không vô hiệu hóa session ở server và có thể xóa dữ liệu của ứng dụng khác cùng origin.

### 10.4. Không mã hóa client-side để thay thế ranh giới XSS

Mã hóa dữ liệu trong localStorage không bảo vệ được secret nếu JavaScript cùng origin có thể lấy cả ciphertext lẫn khóa giải mã. XSS có thể gọi cùng hàm giải mã hoặc đọc dữ liệu sau khi ứng dụng mở khóa.

Mã hóa phía client có thể hữu ích cho một mô hình bảo vệ cụ thể khi khóa được giữ bên ngoài JavaScript origin, nhưng không nên dùng như lời giải chung cho việc lưu access token trong localStorage.

## 11. So sánh nhanh khi chọn API

| Nhu cầu | Lựa chọn thường phù hợp | Lưu ý |
|---|---|---|
| Theme, ngôn ngữ, tùy chọn nhỏ qua nhiều phiên | localStorage | Không chứa secret; có thể bị xóa |
| Wizard/draft chỉ trong một tab | sessionStorage | Không phải server session; XSS vẫn đọc được |
| Session identifier do server quản lý | Cookie phù hợp | Secure, HttpOnly, SameSite và CSRF defense |
| Dữ liệu offline có cấu trúc | IndexedDB | Async, transaction; quản lý quota/migration |
| Cache request/response | Cache Storage | Versioning, invalidation và tránh cache private response |
| File/dữ liệu nhị phân lớn | OPFS hoặc API phù hợp | Hỗ trợ và quota phụ thuộc browser |
| State đang xử lý trong UI | JavaScript memory | Mất khi runtime kết thúc |

Đừng chọn storage chỉ dựa vào dung lượng. Hãy cân nhắc ai có thể đọc dữ liệu, browser gửi dữ liệu khi nào, dữ liệu sống bao lâu và ứng dụng cần đảm bảo tính nhất quán ở đâu.

## 12. Lab local: quan sát localStorage và sessionStorage

Lab tạo một trang nhỏ để thử ghi/đọc/xóa hai loại storage và quan sát storage event. Dùng localhost/loopback qua HTTP; không dùng file URL vì hành vi storage của file URL không phải nền tảng ổn định.

### 12.1. Tạo file storage-lab.html

```html
<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Web Storage lab</title>
</head>
<body>
  <h1>Web Storage lab</h1>
  <p id="origin"></p>
  <p id="status" aria-live="polite"></p>

  <label>
    Value
    <input id="value" value="hello" maxlength="100">
  </label>

  <section>
    <h2>localStorage</h2>
    <button id="local-write">Ghi localStorage</button>
    <button id="local-read">Đọc localStorage</button>
    <button id="local-remove">Xóa key localStorage</button>
  </section>

  <section>
    <h2>sessionStorage</h2>
    <button id="session-write">Ghi sessionStorage</button>
    <button id="session-read">Đọc sessionStorage</button>
    <button id="session-remove">Xóa key sessionStorage</button>
  </section>

  <pre id="output"></pre>

  <script>
    const KEY = "storage-lab:message";
    const input = document.getElementById("value");
    const output = document.getElementById("output");
    const status = document.getElementById("status");

    document.getElementById("origin").textContent =
      "Origin: " + location.origin;

    function show(label, value) {
      output.textContent = label + ": " + String(value);
    }

    function runStorage(operation) {
      try {
        operation();
      } catch (error) {
        status.textContent = error.name + ": storage operation failed";
      }
    }

    document.getElementById("local-write").addEventListener("click", () => {
      runStorage(() => {
        localStorage.setItem(KEY, input.value);
        show("localStorage saved", input.value);
      });
    });

    document.getElementById("local-read").addEventListener("click", () => {
      runStorage(() => show("localStorage value", localStorage.getItem(KEY)));
    });

    document.getElementById("local-remove").addEventListener("click", () => {
      runStorage(() => {
        localStorage.removeItem(KEY);
        show("localStorage removed", KEY);
      });
    });

    document.getElementById("session-write").addEventListener("click", () => {
      runStorage(() => {
        sessionStorage.setItem(KEY, input.value);
        show("sessionStorage saved", input.value);
      });
    });

    document.getElementById("session-read").addEventListener("click", () => {
      runStorage(() => show("sessionStorage value", sessionStorage.getItem(KEY)));
    });

    document.getElementById("session-remove").addEventListener("click", () => {
      runStorage(() => {
        sessionStorage.removeItem(KEY);
        show("sessionStorage removed", KEY);
      });
    });

    window.addEventListener("storage", (event) => {
      if (event.key !== KEY && event.key !== null) return;

      status.textContent = [
        "Storage event từ document khác",
        "key: " + event.key,
        "oldValue: " + event.oldValue,
        "newValue: " + event.newValue,
        "url: " + event.url
      ].join(" | ");
    });
  </script>
</body>
</html>
```

### 12.2. Chạy local server

Tạo file `storage-lab-server.mjs`:

```js
import { createServer } from "node:http";
import { readFile } from "node:fs/promises";

const html = await readFile(
  new URL("./storage-lab.html", import.meta.url)
);

createServer((req, res) => {
  if (req.url !== "/" && req.url !== "/index.html") {
    res.writeHead(404).end("Not found");
    return;
  }

  res.writeHead(200, {
    "Content-Type": "text/html; charset=utf-8",
    "Cache-Control": "no-store"
  });
  res.end(html);
}).listen(8080, "0.0.0.0", () => {
  console.log("Open http://localhost:8080");
  console.log("Or http://127.0.0.1:8080");
});
```

Chạy:

```bash
node storage-lab-server.mjs
```

Mở `http://localhost:8080`.

### 12.3. Thử vòng đời và phạm vi

1. Ghi một giá trị vào localStorage và sessionStorage.
2. Reload cùng tab rồi đọc lại cả hai key.
3. Mở tab mới cùng origin và đọc lại: localStorage có thể được chia sẻ; sessionStorage của tab mới độc lập.
4. Thử mở tab mới qua một link có opener để quan sát sessionStorage ban đầu có thể được sao chép; sau đó thay đổi mỗi tab và xác nhận chúng không đồng bộ.
5. Đóng tab rồi mở lại cùng origin: localStorage thường còn; sessionStorage của page session cũ kết thúc.
6. Mở hai tab cùng origin, ghi localStorage ở tab A và quan sát storage event ở tab B. Tab A không nhận event của chính thao tác đó.
7. Thay URL từ localhost sang 127.0.0.1 hoặc đổi port để tạo origin khác; storage không được chia sẻ giữa các origin khác nhau.
8. Trong DevTools Application/Storage, xem key, value và xóa riêng key lab.

Kết quả có thể chịu ảnh hưởng bởi browser, session restore, private mode và privacy partitioning. Ghi nhận browser/phiên bản khi so sánh.

### 12.4. Kiểm tra storage event

Storage event chỉ được gửi tới document khác dùng cùng storage area. Thử:

- Ghi localStorage ở tab A; tab B cùng origin nhận event.
- Ghi localStorage trong tab A; tab A không nhận event của chính nó.
- Ghi sessionStorage ở tab A; tab B độc lập không nhận event sessionStorage.
- Nếu có iframe cùng origin trong tab A, thay đổi sessionStorage có thể tạo event ở document iframe cùng page session.

Không dùng event làm bằng chứng người gửi đã được xác thực. Storage event chỉ phản ánh một thay đổi trong vùng lưu trữ dùng chung.

### 12.5. Kiểm tra lỗi và private browsing

Thử trong môi trường test:

- Chặn site data hoặc thay đổi quyền lưu trữ trong cài đặt browser.
- Mở cửa sổ private/incognito và ghi một giá trị không nhạy cảm.
- Đóng toàn bộ phiên private rồi mở lại để quan sát dữ liệu có được giữ không.
- Thử sandbox iframe thiếu allow-same-origin và xem truy cập storage có thể ném SecurityError.
- Ghi một payload lớn có kiểm soát để quan sát quota error; không lặp ghi vô hạn.

Không dùng dữ liệu cá nhân hoặc token thật trong lab.

## 13. Checklist review Web Storage

Trước khi dùng Web Storage trong sản phẩm, hãy kiểm tra:

1. **Mục đích:** Dữ liệu có thực sự cần lưu ở client không?
2. **Phân loại:** Có credential, token, OTP, password hoặc dữ liệu nhạy cảm không?
3. **API:** Nên dùng localStorage, sessionStorage, IndexedDB hay memory?
4. **Origin:** Các trang cùng origin có chia sẻ key không? Có ứng dụng khác trên cùng origin không?
5. **Iframe:** Tài liệu có opaque origin hoặc bị storage partitioning không?
6. **Lifecycle:** Dữ liệu có thể bị xóa khi đóng tab, clear site data, private session hoặc eviction không?
7. **Quota:** Có xử lý SecurityError và QuotaExceededError không?
8. **Schema:** Có parse, validate, version và giới hạn kích thước dữ liệu không?
9. **XSS:** Nếu script cùng origin bị thực thi, dữ liệu nào có thể bị đọc hoặc sửa?
10. **CSRF:** Có hiểu rằng Web Storage không tự gửi theo request và cookie vẫn cần CSRF defense không?
11. **Events:** Có xử lý storage event mà không coi nó là kênh tin cậy không?
12. **Concurrency:** Có tránh read-modify-write khi cần transaction hoặc tính nhất quán không?
13. **Cleanup:** Logout có xóa đúng namespace và vô hiệu hóa session phía server không?
14. **Partitioning:** Third-party iframe có phụ thuộc vào storage toàn cục không?
15. **Testing:** Đã thử tab, origin, iframe, private mode và browser mục tiêu chưa?

## 14. Những hiểu lầm phổ biến

| Nhận định sai | Cách hiểu đúng |
|---|---|
| "localStorage an toàn vì chỉ browser lưu." | Script cùng origin và XSS có thể đọc, sửa, xóa dữ liệu. |
| "sessionStorage chống được XSS." | Script trong cùng document vẫn truy cập được sessionStorage. |
| "Hai trang cùng domain luôn chia sẻ storage." | Origin tính scheme, host và port; subdomain hoặc port khác có storage riêng. |
| "Path tạo vùng localStorage riêng." | Path không thuộc origin; các path cùng origin dùng chung localStorage. |
| "Web Storage tự gửi lên server." | JavaScript phải chủ động đọc và gửi; cookie có cơ chế gửi tự động riêng. |
| "localStorage là database có transaction." | API đồng bộ key-value, không có transaction nhiều thao tác. |
| "sessionStorage luôn mất ngay khi reload." | Reload cùng page session thường giữ dữ liệu. |
| "Tab mới luôn có sessionStorage trống." | Tab có opener có thể nhận bản sao ban đầu rồi hoạt động độc lập. |
| "clear() chỉ xóa dữ liệu ứng dụng hiện tại." | clear() xóa toàn bộ key trong storage area của origin. |
| "Quota giống nhau ở mọi browser." | Giới hạn và eviction phụ thuộc browser, API, thiết bị và policy. |
| "CORS bảo vệ localStorage." | SOP giới hạn truy cập theo origin; CORS không phải quyền truy cập Web Storage. |
| "Mã hóa token trong localStorage giải quyết XSS." | Script cùng origin có thể lấy khóa hoặc dữ liệu sau giải mã nếu chạy trong app. |
| "Không có storage event nghĩa là không có thay đổi." | Event không phát trong document tạo thay đổi và chỉ đến context cùng storage area. |
| "Private browsing lưu dữ liệu như phiên thường." | Dữ liệu private thường có vòng đời riêng và có thể bị xóa khi phiên kết thúc. |

## 15. Câu hỏi ôn tập

1. Web Storage API gồm những vùng lưu trữ nào?
2. localStorage khác sessionStorage về phạm vi và vòng đời ra sao?
3. Origin được xác định bởi những thành phần nào?
4. Vì sao hai path cùng origin dùng chung localStorage?
5. Vì sao HTTP và HTTPS có storage area khác nhau?
6. Khi mở tab mới có opener, sessionStorage có thể được khởi tạo như thế nào?
7. Web Storage lưu object trực tiếp hay chỉ lưu chuỗi?
8. Vì sao cần validate dữ liệu sau JSON.parse?
9. Storage event được gửi tới document nào và có phát ở document tạo thay đổi không?
10. Vì sao read-modify-write trên localStorage không bảo đảm transaction?
11. QuotaExceededError và SecurityError có thể xuất hiện trong trường hợp nào?
12. Storage partitioning ảnh hưởng third-party iframe như thế nào?
13. Vì sao localStorage không phù hợp để lưu access token nhạy cảm?
14. Web Storage giảm một kiểu CSRF exposure nào nhưng vẫn có rủi ro gì?
15. Khi nào nên chọn IndexedDB hoặc Cache Storage thay cho Web Storage?

**Đáp án định hướng:** (1) localStorage và sessionStorage. (2) localStorage chia sẻ giữa document cùng origin và thường tồn tại qua phiên; sessionStorage gắn với origin cùng top-level browsing context/page session. (3) Scheme, host và port. (4) Path không thuộc origin. (5) Scheme là một phần của origin. (6) Có thể nhận bản sao ban đầu từ opener rồi độc lập. (7) Chuỗi key/value; object cần serialize. (8) Dữ liệu có thể bị sửa hoặc không đúng schema dù JSON hợp lệ. (9) Các document khác dùng cùng storage area; document tạo thay đổi không nhận event. (10) API không cung cấp transaction/lock cho chuỗi thao tác. (11) QuotaExceededError khi vượt quota; SecurityError khi origin/policy không cho phép truy cập. (12) Storage có thể được phân vùng theo top-level site. (13) XSS cùng origin có thể đọc token. (14) Storage không tự gửi theo request như cookie; nhưng XSS có thể đọc token và gửi request. (15) IndexedDB cho dữ liệu có cấu trúc và transaction; Cache Storage cho Request/Response và offline caching.

## 16. Tài liệu tham khảo

- [WHATWG — Web Storage](https://html.spec.whatwg.org/multipage/webstorage.html): Đặc tả localStorage, sessionStorage và storage event.
- [MDN — Web Storage API](https://developer.mozilla.org/en-US/docs/Web/API/Web_Storage_API): Tổng quan API và cách sử dụng.
- [MDN — Window.localStorage](https://developer.mozilla.org/en-US/docs/Web/API/Window/localStorage): Phạm vi origin, vòng đời và ngoại lệ.
- [MDN — Window.sessionStorage](https://developer.mozilla.org/en-US/docs/Web/API/Window/sessionStorage): Page session, tab và opener behavior.
- [MDN — StorageEvent](https://developer.mozilla.org/en-US/docs/Web/API/StorageEvent): Các thuộc tính và phạm vi storage event.
- [MDN — Storage quotas and eviction criteria](https://developer.mozilla.org/en-US/docs/Web/API/Storage_API/Storage_quotas_and_eviction_criteria): Quota, persistence và eviction.
- [MDN — Storage API](https://developer.mozilla.org/en-US/docs/Web/API/Storage_API): Ước lượng và quản lý storage của origin.
- [MDN — IndexedDB API](https://developer.mozilla.org/en-US/docs/Web/API/IndexedDB_API): Database bất đồng bộ phía client.
- [MDN — Cache API](https://developer.mozilla.org/en-US/docs/Web/API/Cache): Lưu trữ Request/Response.
- [OWASP — HTML5 Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/HTML5_Security_Cheat_Sheet.html): Rủi ro lưu trữ client-side và khuyến nghị bảo mật.
- [OWASP — Cross Site Scripting Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet.html): Ngăn script injection có thể đọc dữ liệu cùng origin.

**Kết nối với mô hình bảo mật web:** Web Storage chia sẻ dữ liệu theo origin; localStorage thường sống qua phiên browser còn sessionStorage gắn với page session của một tab. SOP xác định document nào có thể truy cập vùng lưu trữ, nhưng XSS cùng origin vẫn đọc và sửa được dữ liệu. Cookie, IndexedDB và Cache Storage có vòng đời, cách gửi dữ liệu và ranh giới riêng; hãy chọn API theo mục đích, tránh lưu secret phía client, xử lý quota/eviction và coi mọi dữ liệu đọc từ storage là input không tin cậy.
