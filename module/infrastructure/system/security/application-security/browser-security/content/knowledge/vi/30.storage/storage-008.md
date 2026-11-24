# Xóa dữ liệu storage: kiểm soát phạm vi, quota và khả năng khôi phục

Ứng dụng web lưu dữ liệu ở nhiều nơi trong trình duyệt: localStorage, sessionStorage, IndexedDB, Cache Storage, cookie, service worker và Origin Private File System (OPFS). Khi người dùng đăng xuất, yêu cầu xóa tài khoản, đổi môi trường hoặc cần xử lý dữ liệu lỗi, thao tác xóa phải nhắm đúng loại dữ liệu và đúng phạm vi. Xóa localStorage không tự xóa cookie, IndexedDB hay cache; xóa cache cũng không bảo đảm service worker đã bị gỡ.

Bài học tập trung vào việc kiểm kê và xóa dữ liệu storage một cách có kiểm soát. Người học sẽ thực hành kiểm tra dữ liệu bằng DevTools, đo quota, yêu cầu persistence, mô phỏng lỗi ghi và xây dựng quy trình backup/recovery. Các API xóa phía client chỉ xóa dữ liệu trong phạm vi origin/quyền mà browser cho phép; chúng không phải cam kết xóa vật lý an toàn trên thiết bị.

Bài học thuộc chương **Storage**, theo đề bài **Xóa dữ liệu storage**, trong phạm vi **SECURITY_APPLICATION_SECURITY_BROWSER_SECURITY**: phân tích ranh giới bảo mật giữa trình duyệt, origin, cookie và ứng dụng web để hiểu Same-Origin Policy, CORS và các cơ chế cách ly; thực hành phòng vệ XSS, CSRF, clickjacking bằng CSP, Trusted Types, security headers và kiểm chứng hành vi thực tế.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

1. Liệt kê các nơi ứng dụng web có thể lưu dữ liệu và xác định API xóa tương ứng.
2. Phân biệt xóa một key, xóa một database, xóa Cache Storage, xóa cookie và xóa toàn bộ site data.
3. Dùng DevTools để xem dung lượng, database, cache, cookie và service worker.
4. Đọc quota/usage bằng Storage API và xử lý QuotaExceededError.
5. Hiểu persist()/persisted() và giới hạn của persistent storage.
6. Xử lý database đang mở khiến thao tác xóa IndexedDB bị blocked.
7. Thiết kế backup, migration và recovery trước khi xóa hoặc nâng schema.
8. Dùng Clear-Site-Data đúng phạm vi và hiểu tác động lên subdomain.
9. Xây dựng quy trình xóa dữ liệu khi logout hoặc xóa tài khoản mà không dựa hoàn toàn vào JavaScript phía client.

## 2. Bản đồ các loại dữ liệu trong browser

Trước khi xóa, phải xác định dữ liệu đang nằm ở đâu. Các API có vòng đời và phạm vi khác nhau:

| Nơi lưu | API/công cụ | Ví dụ dữ liệu | Cách xóa |
| --- | --- | --- | --- |
| Local Storage | localStorage | Tùy chọn giao diện, cờ trạng thái, dữ liệu nhỏ dạng chuỗi | removeItem() hoặc clear() |
| Session Storage | sessionStorage | Trạng thái tạm theo tab/browsing context | removeItem() hoặc clear() |
| IndexedDB | indexedDB | Bản ghi, dữ liệu offline, hàng đợi đồng bộ | deleteDatabase() hoặc xóa record/object store |
| Cache Storage | caches | Response do ứng dụng/service worker cache | caches.delete() hoặc xóa cache cụ thể |
| Cookies | document.cookie, Set-Cookie | Session ID, tùy chọn server-side | Expire cookie đúng name/path/domain; HttpOnly phải xử lý từ server |
| Service worker registration | navigator.serviceWorker | Worker điều khiển trang và xử lý offline | registration.unregister() |
| OPFS | navigator.storage.getDirectory() | File dữ liệu riêng của origin | removeEntry() hoặc xóa file/thư mục do ứng dụng quản lý |
| HTTP cache | Browser/network cache | Tài nguyên HTTP cacheable | Browser controls hoặc Clear-Site-Data cache |

Những nơi này không phải một kho duy nhất. Ví dụ:

- localStorage.clear() không xóa IndexedDB.
- caches.delete() không xóa HTTP cache của browser.
- Xóa Cache Storage không tự động unregister service worker.
- document.cookie không thể xóa cookie có thuộc tính HttpOnly.
- Xóa dữ liệu phía client không vô hiệu hóa session ở server.

**Nguyên tắc:** kiểm kê dữ liệu theo chức năng và chủ sở hữu trước khi gọi API xóa. Không dùng một lệnh tổng quát khi ứng dụng chỉ cần xóa một nhóm dữ liệu.

## 3. Phạm vi xóa: key, origin, site và profile

### Xóa một key

Khi chỉ một thiết lập hoặc một mục dữ liệu không còn hợp lệ, xóa đúng key:

```js
localStorage.removeItem('ui.theme');
sessionStorage.removeItem('checkout.draft');
```

Đây là lựa chọn phù hợp khi dữ liệu khác trong cùng storage vẫn cần được giữ.

### Xóa toàn bộ một storage area

```js
localStorage.clear();
sessionStorage.clear();
```

clear() xóa tất cả key trong storage area của origin hiện tại (và session storage context hiện tại đối với sessionStorage). Không gọi clear() nếu ứng dụng có nhiều tính năng cùng dùng một storage area mà không có quy ước namespace.

### Xóa dữ liệu của origin

Browser DevTools và Clear-Site-Data có thể xóa nhiều loại dữ liệu gắn với origin. Phạm vi cụ thể phụ thuộc browser và directive. Cần phân biệt origin với site: hai subdomain có thể cùng site nhưng là hai origin khác nhau.

### Xóa dữ liệu trong profile browser

Người dùng có thể xóa site data từ cài đặt browser. Đây là thao tác do người dùng điều khiển, có thể ảnh hưởng nhiều ứng dụng đang dùng cùng hostname hoặc cookie domain. Hướng dẫn người dùng chọn đúng site và phạm vi, tránh yêu cầu xóa toàn bộ lịch sử/profile nếu không cần.

## 4. Xóa Local Storage và Session Storage

Web Storage chỉ lưu chuỗi key/value. JSON object thường được serialize trước khi lưu và parse khi đọc.

### Xóa một mục hoặc toàn bộ dữ liệu

```js
// Xóa đúng một key
localStorage.removeItem('profile.cache');

// Xóa toàn bộ localStorage của origin hiện tại
localStorage.clear();

// Xóa sessionStorage của browsing context hiện tại
sessionStorage.clear();
```

### Dùng namespace để tránh xóa nhầm

Nếu nhiều module cùng dùng localStorage, quy ước prefix:

```js
const APP_PREFIX = 'browser-security:';

function removeAppLocalStorage() {
  const keys = [];

  for (let index = 0; index < localStorage.length; index += 1) {
    const key = localStorage.key(index);
    if (key && key.startsWith(APP_PREFIX)) {
      keys.push(key);
    }
  }

  for (const key of keys) {
    localStorage.removeItem(key);
  }
}
```

Thu thập danh sách key trước khi xóa giúp tránh thay đổi chỉ số trong lúc duyệt storage. Prefix cũng giúp module chỉ xóa dữ liệu do chính nó sở hữu.

### Giới hạn bảo mật

Local Storage và Session Storage không phải kho bí mật. JavaScript cùng origin, bao gồm script bị chèn qua XSS, có thể đọc dữ liệu trong đó. Không lưu session token hoặc dữ liệu xác thực có giá trị cao trong localStorage nếu kiến trúc có thể dùng cookie HttpOnly phù hợp.

Xóa localStorage không thu hồi token đã bị sao chép trước đó. Server phải có cơ chế revoke session/token và kiểm tra trạng thái ở các request tiếp theo.

## 5. Xóa IndexedDB

IndexedDB là database bất đồng bộ, có thể chứa nhiều object store và index. Cần phân biệt:

- Xóa một record bằng objectStore.delete(key).
- Xóa object store trong transaction/version upgrade.
- Xóa toàn bộ database bằng indexedDB.deleteDatabase(name).

### Xóa một database

```js
function deleteDatabase(databaseName) {
  return new Promise((resolve, reject) => {
    const request = indexedDB.deleteDatabase(databaseName);

    request.onsuccess = () => resolve();
    request.onerror = () => reject(request.error);
    request.onblocked = () => {
      console.warn('Database đang được một tab hoặc context khác mở.');
    };
  });
}

deleteDatabase('browser-security-cache')
  .then(() => console.log('Database đã được xóa'))
  .catch((error) => console.error('Không thể xóa database:', error));
```

### Vì sao deleteDatabase có thể bị blocked?

Nếu một tab, worker hoặc context khác vẫn giữ kết nối database, thao tác xóa có thể phát blocked và chờ các kết nối đó đóng. Ứng dụng nên xử lý versionchange trên mọi kết nối:

```js
const openRequest = indexedDB.open('browser-security-cache', 1);

openRequest.onsuccess = () => {
  const db = openRequest.result;

  db.onversionchange = () => {
    db.close();
    console.log('Đã đóng kết nối để nhường migration/xóa database.');
  };
};
```

Khi nhận versionchange, tab đang mở nên đóng connection và thông báo nếu cần reload. Nếu bỏ qua, một tab cũ có thể giữ database ở trạng thái khiến tab khác không nâng version hoặc xóa được.

onblocked là tín hiệu để cập nhật UI và chờ context khác đóng kết nối. Không nên giả định callback onsuccess sẽ chạy ngay sau khi gọi deleteDatabase().

### Liệt kê database để kiểm tra

Một số browser hỗ trợ indexedDB.databases():

```js
if (typeof indexedDB.databases === 'function') {
  const databases = await indexedDB.databases();
  console.table(databases);
} else {
  console.log('Browser không hỗ trợ liệt kê IndexedDB databases.');
}
```

Đây là API không nên coi là khả dụng ở mọi browser/webview. Ứng dụng nên biết tên database do mình tạo thay vì phụ thuộc vào khả năng liệt kê để xóa tất cả.

### Xóa record thay vì database

Nếu chỉ cần xóa dữ liệu của một người dùng hoặc một nhóm record, hãy dùng transaction và object store cụ thể. Xóa toàn bộ database có thể làm mất dữ liệu offline, hàng đợi chưa đồng bộ hoặc trạng thái migration mà tính năng khác cần.

## 6. Xóa Cache Storage và service worker

Cache Storage lưu các Request/Response do ứng dụng tạo, thường dùng cho offline và service worker.

### Liệt kê và xóa cache

```js
async function listCacheNames() {
  const names = await caches.keys();
  console.table(names);
  return names;
}

async function deleteCache(cacheName) {
  return caches.delete(cacheName);
}

async function deleteAppCaches(prefix) {
  const names = await caches.keys();
  const ownedNames = names.filter((name) => name.startsWith(prefix));

  const results = await Promise.all(
    ownedNames.map((name) => caches.delete(name))
  );

  return results;
}
```

caches.delete(name) trả về boolean cho biết cache có được xóa hay không. Chỉ xóa cache do ứng dụng quản lý; prefix/version giúp tránh xóa cache của module khác trên cùng origin.

### Xóa cache không đồng nghĩa gỡ service worker

Service worker registration là một tài nguyên riêng:

```js
async function unregisterAppWorkers() {
  const registrations =
    await navigator.serviceWorker.getRegistrations();

  const results = await Promise.all(
    registrations.map((registration) => registration.unregister())
  );

  return results;
}
```

unregister() yêu cầu gỡ registration; worker đang chạy hoặc đang kiểm soát client có thể còn tồn tại cho tới khi các client liên quan đóng/điều hướng. Ngoài ra, service worker có thể đăng ký lại nếu ứng dụng vẫn chạy mã đăng ký.

Nếu cần xóa dữ liệu offline, hãy phối hợp:

1. Ngừng luồng tạo cache mới hoặc đặt phiên bản ứng dụng vào trạng thái cleanup.
2. Xóa đúng Cache Storage namespace.
3. Unregister worker nếu tính năng không còn cần.
4. Đóng tab/reload theo hướng dẫn khi worker cũ còn kiểm soát trang.
5. Kiểm tra lại sau khi tải trang để xác nhận dữ liệu không bị tạo lại.

### HTTP cache khác Cache Storage

Cache Storage do ứng dụng truy cập qua Cache API. HTTP cache do browser quản lý dựa trên header HTTP và chính sách cache. Xóa cache bằng caches.delete() không xóa HTTP cache. Muốn kiểm tra HTTP cache, dùng DevTools Network hoặc browser controls; server có thể dùng Cache-Control để điều khiển freshness/revalidation.

## 7. Xóa cookie

Cookie được browser quản lý theo các thuộc tính như name, domain, path, expiry, Secure, SameSite và có thể có partitioning. Xóa cookie cần khớp phạm vi cookie đã tạo.

### Cookie không phải localStorage

document.cookie chỉ cho JavaScript đọc/ghi những cookie không bị HttpOnly và được phép theo context hiện tại. Nó không thể đọc hoặc xóa cookie HttpOnly.

### Expire cookie phía client

Ví dụ cookie được tạo với Path=/:

```js
document.cookie =
  'ui-preference=; Max-Age=0; Path=/; SameSite=Lax; Secure';
```

Nếu cookie ban đầu có Domain cụ thể, Path khác hoặc thuộc tính Partitioned, cần xóa đúng phạm vi tương ứng. Cookie cùng tên nhưng khác Path/Domain có thể là những cookie khác nhau.

Không đặt Domain tùy tiện khi xóa. Cookie host-only và cookie Domain có phạm vi khác nhau.

### HttpOnly cookie phải được server thu hồi

Để xóa cookie phiên HttpOnly, server gửi một Set-Cookie mới với cùng name và scope, đặt thời hạn hết hạn:

```http
Set-Cookie: session=; Max-Age=0; Path=/; Secure; HttpOnly; SameSite=Lax
```

Tên cookie, Path và Domain phải khớp cookie ban đầu. Đồng thời server cần invalidate session tương ứng; expire cookie ở browser không tự thu hồi session phía server nếu token/session ID đã bị sao chép.

### Logout đúng thứ tự

Một quy trình logout an toàn thường:

1. Server xác thực yêu cầu logout và invalidate session/token phía server.
2. Server gửi cookie hết hạn với scope khớp cookie phiên.
3. Ứng dụng xóa dữ liệu client thuộc phiên hiện tại theo namespace.
4. Xóa cache chứa dữ liệu riêng tư và xử lý service worker theo thiết kế.
5. Điều hướng tới trang đã đăng xuất và xác minh back/forward cache không làm lộ giao diện phiên cũ.

Không coi việc gọi localStorage.clear() là logout hoàn chỉnh.

## 8. Xóa dữ liệu OPFS

Origin Private File System (OPFS) cung cấp vùng file riêng cho origin thông qua Storage API. Nếu ứng dụng dùng OPFS, phải đưa nó vào inventory và cleanup riêng.

Ví dụ xóa một file trong thư mục gốc:

```js
async function deleteOpfsFile(fileName) {
  const root = await navigator.storage.getDirectory();
  await root.removeEntry(fileName);
}
```

Xóa thư mục con và nội dung bên trong:

```js
async function deleteOpfsDirectory(directoryName) {
  const root = await navigator.storage.getDirectory();
  await root.removeEntry(directoryName, { recursive: true });
}
```

API OPFS và hỗ trợ đồng đều cần được kiểm tra trên browser mục tiêu. Chỉ xóa file/thư mục thuộc namespace của ứng dụng; không xóa toàn bộ root nếu ứng dụng hoặc module khác đang lưu dữ liệu cần giữ.

## 9. Clear-Site-Data: yêu cầu browser xóa dữ liệu qua response

Header Clear-Site-Data cho phép server yêu cầu browser xóa một số loại dữ liệu liên quan tới origin trả response. Header này thường hữu ích cho logout, sự cố bảo mật hoặc quy trình reset ứng dụng.

Ví dụ:

```http
Clear-Site-Data: "cache", "cookies", "storage"
```

Các directive thường gặp:

| Directive | Phạm vi khái quát |
| --- | --- |
| "cache" | Yêu cầu xóa cache HTTP liên quan tới origin theo hỗ trợ của browser. |
| "cookies" | Xóa cookie trong phạm vi domain liên quan; có thể ảnh hưởng các subdomain và ứng dụng khác cùng registered domain. |
| "storage" | Xóa dữ liệu storage của origin như DOM storage, IndexedDB, Cache Storage và các loại được browser hỗ trợ. |
| "*" | Yêu cầu xóa tất cả nhóm dữ liệu mà browser hỗ trợ trong cơ chế này. |

Hỗ trợ và phạm vi chi tiết có thể khác giữa browser. Header phải được gửi từ secure context/HTTPS để browser xử lý theo yêu cầu của chuẩn. Kiểm tra tài liệu browser mục tiêu và thử nghiệm trên staging trước khi bật rộng.

### Cẩn trọng với cookies directive

"cookies" có thể tác động tới cookie thuộc registered domain và subdomain, không chỉ một ứng dụng ở một origin. Nếu app.example.com, auth.example.com và shop.example.com dùng chung domain cookie hoặc có cookie liên quan, xóa cookie có thể đăng xuất nhiều dịch vụ.

Chỉ dùng directive này khi đã đánh giá tác động trên toàn domain. Nếu cần logout một ứng dụng, server có thể expire đúng cookie phiên theo scope thay vì xóa cookie diện rộng.

### Clear-Site-Data không thay thế xóa phía server

Header yêu cầu browser dọn dữ liệu local. Nó không tự xóa bản ghi trong database server, không revoke session trong backend và không bảo đảm xóa bản sao đã export hoặc đồng bộ sang thiết bị khác.

Nếu cần xóa tài khoản, server phải thực hiện quy trình xóa dữ liệu phía backend theo chính sách sản phẩm và pháp lý; Clear-Site-Data chỉ xử lý phần dữ liệu browser trong phạm vi được hỗ trợ.

## 10. Kiểm tra quota và usage bằng Storage API

Browser cấp dung lượng storage theo chính sách riêng. Không có một quota cố định áp dụng cho mọi browser, thiết bị, profile hoặc origin.

navigator.storage.estimate() trả về ước lượng usage và quota:

```js
async function inspectStorageUsage() {
  if (!navigator.storage?.estimate) {
    return { supported: false };
  }

  const estimate = await navigator.storage.estimate();

  return {
    supported: true,
    usage: estimate.usage ?? 0,
    quota: estimate.quota ?? 0,
    usageDetails: estimate.usageDetails ?? null
  };
}

console.log(await inspectStorageUsage());
```

Ý nghĩa:

- usage: dung lượng ước tính đang được sử dụng.
- quota: giới hạn ước tính browser hiện cấp cho origin/storage bucket.
- usageDetails: breakdown theo loại storage nếu browser cung cấp; có thể không có hoặc không đầy đủ.

Đây là số liệu ước lượng. Browser có thể tính thêm overhead, làm tròn hoặc thay đổi quota theo dung lượng thiết bị và chính sách quản lý.

### Tính tỷ lệ sử dụng

```js
async function getStorageRatio() {
  const { usage = 0, quota = 0 } =
    await navigator.storage.estimate();

  return {
    usage,
    quota,
    ratio: quota > 0 ? usage / quota : null
  };
}
```

Không hiển thị tỷ lệ như cam kết chính xác còn bao nhiêu byte. Hãy dùng nó để cảnh báo sớm và chuẩn bị cleanup, không thay thế xử lý lỗi khi ghi.

## 11. QuotaExceededError và chiến lược ghi an toàn

Khi storage đầy hoặc browser không cấp thêm dung lượng, thao tác ghi có thể thất bại. Tên lỗi thường gặp là QuotaExceededError, nhưng API cụ thể có thể biểu diễn lỗi qua exception, request error hoặc transaction abort.

Ví dụ với localStorage:

```js
function saveDraft(key, value) {
  try {
    localStorage.setItem(key, value);
    return { ok: true };
  } catch (error) {
    if (error.name === 'QuotaExceededError') {
      return { ok: false, reason: 'quota-exceeded' };
    }

    throw error;
  }
}
```

Với IndexedDB, cần lắng nghe error/abort trên request và transaction. Không chỉ kiểm tra promise wrapper của ứng dụng nếu wrapper có thể che mất lỗi transaction.

### Khi gần hết quota

Một chiến lược phù hợp:

1. Xác định dữ liệu nào là cache có thể tái tạo và dữ liệu nào là dữ liệu người dùng.
2. Xóa cache cũ hoặc cache version không còn dùng.
3. Nén/giảm kích thước dữ liệu nếu phù hợp.
4. Chia ghi thành transaction nhỏ có thể retry an toàn.
5. Giữ bản nháp hoặc bản backup trước khi thay thế dữ liệu quan trọng.
6. Thông báo rõ nếu người dùng cần giải phóng dung lượng hoặc xuất dữ liệu.

Không tự động xóa dữ liệu người dùng để giải phóng quota khi chưa có chính sách và xác nhận phù hợp. Cache thường có thể tái tạo; bản ghi offline chưa đồng bộ có thể không thể phục hồi.

## 12. Persistence: yêu cầu lưu trữ bền vững

Storage API có hai phương thức quan trọng:

- navigator.storage.persisted() kiểm tra origin/storage bucket hiện có được đánh dấu persistent hay chưa.
- navigator.storage.persist() yêu cầu browser cấp persistent storage.

Ví dụ:

```js
async function requestPersistentStorage() {
  if (!navigator.storage?.persisted ||
      !navigator.storage?.persist) {
    return { supported: false, persisted: false };
  }

  const before = await navigator.storage.persisted();
  const granted = before || await navigator.storage.persist();
  const after = await navigator.storage.persisted();

  return {
    supported: true,
    wasPersistent: before,
    requestGranted: granted,
    isPersistent: after
  };
}

console.log(await requestPersistentStorage());
```

Browser có thể tự quyết định dựa trên mức độ người dùng tương tác, cài đặt, dung lượng thiết bị và chính sách riêng. persist() có thể trả về false; ứng dụng không thể ép browser cấp persistent storage.

### Persistent không có nghĩa là không thể bị xóa

Persistent storage chủ yếu bảo vệ dữ liệu khỏi cơ chế tự động eviction do áp lực dung lượng. Nó không ngăn:

- Người dùng xóa site data trong cài đặt browser.
- Người dùng xóa dữ liệu qua DevTools.
- Ứng dụng gọi API xóa.
- Profile browser bị xóa hoặc thiết bị được reset.
- Dữ liệu bị mất do lỗi thiết bị, lỗi phần mềm hoặc đồng bộ thất bại.

Vì vậy, persistence không thay thế backup, export hoặc đồng bộ dữ liệu quan trọng.

## 13. Eviction và recovery

Browser có thể thu hồi dữ liệu storage của origin để giải phóng dung lượng, đặc biệt với storage không persistent. Điều kiện và thuật toán phụ thuộc browser, hệ điều hành, dung lượng còn lại, mức độ sử dụng và trạng thái persistence.

### Phân loại dữ liệu trước khi lưu

| Loại dữ liệu | Ví dụ | Cách phục hồi |
| --- | --- | --- |
| Cache có thể tái tạo | Ảnh, response API công khai, bundle | Tải lại từ server/CDN. |
| Dữ liệu tạm | Search history tạm, filter UI | Khởi tạo lại hoặc yêu cầu người dùng nhập. |
| Dữ liệu người dùng chưa đồng bộ | Bản nháp, hàng đợi offline | Backup/export hoặc đồng bộ server; cần cảnh báo rõ. |
| Dữ liệu authoritative | Hồ sơ, đơn hàng, quyền tài khoản | Lấy lại từ backend sau xác thực. |
| Credential/session | Session cookie, token | Khôi phục bằng luồng đăng nhập/refresh an toàn, không backup credential tùy tiện. |

### Recovery không bắt đầu bằng cách xóa mọi thứ

Khi ứng dụng phát hiện dữ liệu lỗi:

1. Xác định loại storage và phiên bản schema.
2. Kiểm tra xem dữ liệu có thể đọc hoặc export được không.
3. Sao lưu phần còn đọc được trước khi destructive reset.
4. Chỉ xóa namespace/database/cache bị lỗi.
5. Khởi tạo schema/cache mới.
6. Đồng bộ lại từ server hoặc import backup.
7. Ghi nhận trạng thái recovery mà không log dữ liệu nhạy cảm.

Nếu IndexedDB migration thất bại, không lập tức xóa database chứa dữ liệu offline chưa đồng bộ. Cần có đường phục hồi hoặc yêu cầu người dùng export trước.

### Thiết kế dữ liệu có thể tái tạo

- Dùng versioned cache name để xóa cache cũ sau khi cache mới hoạt động.
- Giữ dữ liệu quan trọng trong backend có backup phù hợp.
- Có export/import cho dữ liệu người dùng tạo offline nếu sản phẩm cần.
- Dùng transaction để cập nhật nhất quán.
- Thiết kế retry idempotent cho đồng bộ.
- Không xem browser storage là bản lưu duy nhất của dữ liệu quan trọng.

## 14. Kiểm tra và xóa dữ liệu bằng DevTools

DevTools giúp xác định dữ liệu nào đang tồn tại và kiểm tra thao tác xóa. Tên tab có thể khác theo browser; hướng dẫn dưới đây mô tả Chromium DevTools phổ biến.

### Application → Storage

Mở DevTools → **Application** → **Storage**:

- Xem loại storage được browser quản lý cho origin.
- Dùng phần usage/quota nếu phiên bản DevTools cung cấp.
- Chọn **Clear site data** để xóa nhóm dữ liệu được hỗ trợ.
- Kiểm tra các checkbox trước khi xác nhận, vì thao tác có thể xóa IndexedDB, Local and session storage, Cache Storage, cookies hoặc service workers tùy browser/phiên bản.

Clear site data là thao tác destructive. Trong lab, dùng origin thử nghiệm. Trong production, không hướng dẫn người dùng xóa toàn bộ site data nếu chỉ cần xóa một mục.

### Kiểm tra từng storage area

| DevTools panel | Việc cần kiểm tra |
| --- | --- |
| Local Storage | Key/value, origin, dữ liệu còn sót sau logout. |
| Session Storage | Dữ liệu theo tab/browsing context. |
| IndexedDB | Database, object store, record và schema version. |
| Cache Storage | Cache name, request/response được lưu. |
| Cookies | Name, Domain, Path, Expires, Secure, HttpOnly, SameSite. |
| Service Workers | Registration, scope, status, client đang được worker kiểm soát. |
| Storage/Quota | Usage, quota và persistence nếu browser hiển thị. |

### Network

Mở Network và kiểm tra:

- Response Set-Cookie khi logout.
- Header Clear-Site-Data nếu server sử dụng.
- Request/response sau khi xóa để phát hiện service worker hoặc ứng dụng tạo lại dữ liệu.
- Cache status và response header để phân biệt HTTP cache với Cache Storage.

### Application → Service Workers

Kiểm tra worker có registration nào còn hoạt động. Thử unregister trong lab, reload trang và quan sát ứng dụng có đăng ký lại worker hay không. Nếu có, tìm mã bootstrap đăng ký worker và điều kiện kích hoạt.

### Xác nhận sau khi xóa

Không dừng ở việc nút Clear báo thành công. Hãy reload trang, kiểm tra lại từng storage area và quan sát request mạng. Dữ liệu có thể được tạo lại bởi ứng dụng, worker hoặc API sau lần tải tiếp theo.

## 15. Thực hành tổng hợp: quota, persistence, xóa và recovery

Thực hành trên origin local/HTTPS do người học kiểm soát. Chỉ dùng dữ liệu giả; không thử xóa site data của tài khoản hoặc website production.

### 15.1. Tạo dữ liệu mẫu

Mở Console:

```js
localStorage.setItem('lab.preference', 'dark');
sessionStorage.setItem('lab.tab-state', 'draft');

await new Promise((resolve, reject) => {
  const request = indexedDB.open('storage-lab', 1);

  request.onupgradeneeded = () => {
    request.result.createObjectStore('notes', {
      keyPath: 'id'
    });
  };

  request.onsuccess = () => {
    const db = request.result;
    const transaction = db.transaction('notes', 'readwrite');
    transaction.objectStore('notes').put({
      id: 'note-1',
      text: 'Dữ liệu thử nghiệm'
    });
    transaction.oncomplete = () => {
      db.close();
      resolve();
    };
    transaction.onerror = () => reject(transaction.error);
  };

  request.onerror = () => reject(request.error);
});

const cache = await caches.open('storage-lab-v1');
await cache.put(
  '/lab-resource',
  new Response('cache demo')
);
```

Mở Application panel và xác nhận các mục đã xuất hiện trong Local Storage, Session Storage, IndexedDB và Cache Storage.

### 15.2. Đo quota và persistence

```js
const estimate = await navigator.storage.estimate();
const persisted = navigator.storage.persisted
  ? await navigator.storage.persisted()
  : null;

console.log({
  usage: estimate.usage,
  quota: estimate.quota,
  usageDetails: estimate.usageDetails,
  persisted
});
```

Ghi lại số liệu quan sát được. Thử yêu cầu persistence:

```js
const persistResult = navigator.storage.persist
  ? await navigator.storage.persist()
  : false;
console.log({ persistResult });
```

Kết quả false không phải lỗi lập trình; browser có quyền từ chối yêu cầu.

### 15.3. Xóa theo namespace

```js
localStorage.removeItem('lab.preference');
sessionStorage.removeItem('lab.tab-state');
await caches.delete('storage-lab-v1');
```

Kiểm tra các key và cache đã biến mất. Database storage-lab vẫn còn vì chưa gọi API xóa IndexedDB.

### 15.4. Xóa IndexedDB và quan sát blocked

Đóng tất cả connection của database rồi chạy:

```js
await new Promise((resolve, reject) => {
  const request = indexedDB.deleteDatabase('storage-lab');

  request.onsuccess = () => resolve();
  request.onerror = () => reject(request.error);
  request.onblocked = () => {
    console.warn('Hãy đóng các tab/context đang giữ database.');
  };
});
```

Thử mở database ở tab thứ hai trước khi xóa để quan sát sự kiện blocked. Sau đó đóng connection ở tab thứ hai và xác nhận thao tác xóa hoàn tất.

### 15.5. Xóa service worker nếu lab có đăng ký

```js
const registrations =
  await navigator.serviceWorker.getRegistrations();
console.table(
  registrations.map((registration) => ({
    scope: registration.scope,
    active: Boolean(registration.active)
  }))
);
```

Trong lab, thử unregister registration thuộc ứng dụng rồi reload. Xác nhận worker không tự đăng ký lại nếu ứng dụng đã tắt chức năng đó.

### 15.6. Thử Clear-Site-Data

Trên response HTTPS của route reset thử nghiệm, server gửi:

```http
Clear-Site-Data: "cache", "storage"
```

Tải route bằng browser profile thử nghiệm, sau đó kiểm tra Application panel. Nếu thử cookies, chỉ dùng domain lab không chia sẻ cookie với ứng dụng khác và ghi nhận phạm vi subdomain theo browser.

### 15.7. Mô phỏng recovery

Trước khi xóa database mẫu, export record ra một object/JSON trong bộ nhớ hoặc file thử nghiệm. Xóa database, tạo lại schema rồi import record. Xác minh dữ liệu khôi phục đúng và transaction hoàn tất.

Không dùng bản export chứa token/session hoặc dữ liệu cá nhân thật. Trong ứng dụng thực tế, backup cần kiểm soát quyền truy cập và vòng đời riêng.

### 15.8. Bằng chứng cần lưu

| Bằng chứng | Điều cần xác nhận |
| --- | --- |
| Application panel trước xóa | Dữ liệu mẫu có trong các storage area đã tạo. |
| Storage estimate | Có usage/quota và persistence state nếu browser hỗ trợ. |
| Xóa namespace | Chỉ key/cache thuộc lab bị xóa. |
| IndexedDB blocked | Connection mở ở context khác có thể trì hoãn deleteDatabase. |
| Service worker | Unregister và cache deletion là hai thao tác riêng. |
| Clear-Site-Data | Browser xử lý directive theo phạm vi hỗ trợ. |
| Recovery | Dữ liệu mẫu được export, database tạo lại và record import thành công. |

## 16. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| localStorage.clear() nhưng dữ liệu vẫn còn | Dữ liệu nằm trong IndexedDB, cookie hoặc Cache Storage | Kiểm tra từng storage area trong Application. |
| Xóa cache nhưng offline vẫn hoạt động | Service worker còn chạy hoặc HTTP cache còn dữ liệu | Kiểm tra Service Workers và Network cache. |
| deleteDatabase() bị blocked | Tab/worker khác vẫn mở connection | Xử lý versionchange, đóng mọi connection và thử lại. |
| Cookie vẫn tồn tại | Sai Path/Domain hoặc cookie HttpOnly | Kiểm tra cookie attributes và expire từ server. |
| Storage usage không giảm ngay | Browser cập nhật số liệu bất đồng bộ, dữ liệu khác vẫn còn hoặc overhead | Reload/đo lại và kiểm tra từng loại storage. |
| persist() trả false | Browser không cấp persistent storage theo policy | Xử lý như storage có thể bị eviction; duy trì backup. |
| Ghi dữ liệu lỗi | Quota đầy hoặc storage bị giới hạn | Bắt QuotaExceededError/transaction abort và cleanup có chọn lọc. |
| Dữ liệu xuất hiện lại sau Clear-Site-Data | Ứng dụng/worker/API tạo lại dữ liệu sau reload | Theo dõi Network, service worker và luồng bootstrap. |
| Xóa toàn site làm mất dữ liệu module khác | Nhiều tính năng cùng dùng một origin | Dùng namespace và xóa theo owner khi có thể. |

## 17. Checklist production

| Hạng mục | Câu hỏi rà soát | Kết quả mong đợi |
| --- | --- | --- |
| Inventory | Đã liệt kê local/session storage, IDB, Cache API, cookies, worker và OPFS chưa? | Có owner và chính sách retention cho từng nhóm. |
| Scope | Thao tác xóa nhắm key, database, cache, cookie hay toàn origin? | Phạm vi tối thiểu đáp ứng yêu cầu. |
| Namespace | Nhiều module có dùng chung origin/storage area không? | Prefix và tên database/cache có quy ước rõ. |
| IndexedDB | Có xử lý versionchange, blocked, error và transaction abort không? | Không giữ connection cũ làm kẹt migration/xóa. |
| Service worker | Có phân biệt cache deletion với unregister không? | Cleanup xử lý cả hai theo vòng đời ứng dụng. |
| Cookies | Có expire đúng name, Path, Domain và xử lý HttpOnly phía server không? | Cookie phiên được thu hồi đúng scope. |
| Server session | Logout có invalidate session/token ở backend không? | Credential bị revoke phía server. |
| Quota | Có đo usage/quota và bắt lỗi khi ghi không? | Có cleanup cache và xử lý quota có kiểm soát. |
| Persistence | Có giả định dữ liệu persistent không bao giờ mất không? | Luôn có backup/recovery cho dữ liệu quan trọng. |
| Recovery | Có export, migration, retry và restore path không? | Có thể khôi phục dữ liệu chưa đồng bộ. |
| Clear-Site-Data | Directive có ảnh hưởng cookie/subdomain khác không? | Đánh giá domain scope và browser support trước khi bật. |
| DevTools | Đã xác minh trước/sau xóa trên browser mục tiêu chưa? | Có bằng chứng Application, Network và Service Workers. |
| Privacy | Có lưu credential hoặc dữ liệu nhạy cảm quá mức trong browser storage không? | Thu thập tối thiểu, mã hóa phù hợp và server-side controls. |

## 18. Câu hỏi tự kiểm tra

1. Vì sao localStorage.clear() không xóa toàn bộ dữ liệu mà website đã lưu?
2. Khác biệt giữa xóa một key, xóa một IndexedDB database và Clear-Site-Data là gì?
3. Vì sao deleteDatabase() có thể bị blocked và ứng dụng nên xử lý versionchange ra sao?
4. Cache Storage khác HTTP cache như thế nào?
5. Vì sao xóa Cache Storage không đồng nghĩa unregister service worker?
6. Tại sao JavaScript không thể xóa cookie HttpOnly và server cần làm gì khi logout?
7. navigator.storage.estimate() cung cấp usage/quota với giới hạn nào?
8. persist() có bảo đảm dữ liệu không bao giờ bị xóa không?
9. Khi gặp QuotaExceededError, vì sao phải phân biệt cache tái tạo với dữ liệu offline chưa đồng bộ?
10. Làm thế nào kiểm tra bằng DevTools rằng dữ liệu đã bị xóa và không bị service worker/app tạo lại?

**Tiêu chí hoàn thành:** người học có thể kiểm kê đúng các storage area, xóa dữ liệu theo phạm vi nhỏ nhất, xác minh quota và persistence, xử lý IndexedDB blocked và cookie HttpOnly đúng cách, dùng DevTools để kiểm tra trước/sau, đồng thời có backup/recovery cho dữ liệu quan trọng trước khi thực hiện thao tác destructive.
