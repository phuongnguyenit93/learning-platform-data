# Xóa dữ liệu nhạy cảm bằng Developer Tools

## 1. Vì sao cần biết cách xóa dữ liệu nhạy cảm?

Trong quá trình phát triển và kiểm thử ứng dụng web, browser có thể lưu nhiều dữ liệu ngoài những gì đang hiển thị trên trang: cookie phiên đăng nhập, token, thông tin người dùng, dữ liệu form, bản ghi IndexedDB, Cache Storage, response HTTP cache, log Console và nội dung request/response trong Network panel. Một phần dữ liệu được ứng dụng chủ động lưu; phần khác do browser, service worker hoặc công cụ giám sát giữ lại để hỗ trợ hoạt động.

Khi dùng chung máy kiểm thử, chuyển tài khoản, xử lý sự cố hoặc chuẩn bị bàn giao môi trường, dữ liệu còn sót có thể làm lộ thông tin hoặc khiến lần kiểm thử tiếp theo dùng nhầm trạng thái cũ. Developer Tools cho phép quan sát và xóa nhiều loại dữ liệu theo origin, đồng thời giúp xác nhận ứng dụng đã thực sự xóa những gì.

Tuy nhiên, thao tác xóa trong DevTools có phạm vi cụ thể. Xóa danh sách request trong Network chỉ xóa nội dung đang hiển thị trong panel; nó không thu hồi request đã gửi, không xóa log server và không tự xóa cookie hay IndexedDB. Xóa site data cũng không xóa mọi bản sao của dữ liệu ở backend, analytics, proxy, backup hoặc hệ thống logging.

Bài học này hướng dẫn xác định đúng nơi dữ liệu được lưu, chọn thao tác xóa phù hợp và kiểm tra lại kết quả. Hãy thực hành trong môi trường local/staging với dữ liệu giả. Nếu đang điều tra sự cố bảo mật, cần tuân theo quy trình bảo toàn chứng cứ trước khi xóa log hoặc trạng thái liên quan.

Sau bài học, bạn có thể:

- Phân biệt dữ liệu trong DevTools panel với dữ liệu được browser lưu.
- Xóa Network log và Console output đúng phạm vi.
- Xóa cookie, localStorage, sessionStorage và IndexedDB theo origin.
- Xóa Cache Storage và quản lý Service Worker.
- Phân biệt site data với HTTP cache, history, downloads và saved passwords.
- Dùng Application → Storage để kiểm tra và xóa dữ liệu của site.
- Xác minh ứng dụng không tự tạo lại dữ liệu nhạy cảm sau khi xóa.
- Thiết kế logout và account-switch flow có xóa client state phù hợp.
- Nhận biết dữ liệu vẫn tồn tại ở server-side systems sau khi browser đã xóa.

## 2. Xác định dữ liệu đang nằm ở đâu

Trước khi xóa, cần phân loại dữ liệu. Mỗi nơi có thao tác và phạm vi khác nhau:

| Nơi lưu/hiển thị | Ví dụ | Công cụ/thao tác |
| --- | --- | --- |
| Network panel | Request URL, headers, payload, response preview | Clear network log; đóng DevTools; tránh export HAR chứa bí mật |
| Console panel | Log, object, token vô tình được in ra | Clear console; tắt Preserve log; sửa logging source |
| Cookies | Session ID, refresh cookie, preference | Application → Storage → Cookies |
| Web Storage | localStorage, sessionStorage | Application → Local Storage/Session Storage hoặc Clear site data |
| IndexedDB | Cache nghiệp vụ, offline records, user profile | Application → IndexedDB hoặc Clear site data |
| Cache Storage | Response do service worker/app cache | Application → Cache Storage |
| Service Worker | Script điều khiển request/offline behavior | Application → Service Workers → Unregister |
| HTTP cache | CSS, JS, image và response cacheable | Network → Disable cache/Empty cache and hard reload hoặc browser settings |
| Browser history/downloads | URL đã mở, tên file đã tải | Browser history/download UI hoặc privacy settings |
| Backend/observability | Account record, API log, APM trace | API/admin workflow và retention controls của hệ thống |

### 2.1 Một dữ liệu có thể có nhiều bản sao

Ví dụ access token có thể xuất hiện trong memory của JavaScript, localStorage, request Authorization header, Console log và APM trace nếu ứng dụng ghi sai. Xóa localStorage không xóa biến token đang nằm trong memory của tab hiện tại. Clear Network panel không thu hồi token ở backend.

Hãy bắt đầu bằng câu hỏi: dữ liệu nào cần xóa, nó được lưu ở đâu, ai có quyền truy cập và hệ thống nào có thể đã nhận một bản sao? Câu trả lời quyết định phạm vi thao tác.

### 2.2 Origin và phạm vi storage

Web Storage, IndexedDB và nhiều API storage được phân vùng theo origin, thường gồm scheme, host và port. Ví dụ:

```text
https://app.example.test
https://app.example.test:8443
http://app.example.test
https://files.example.test
```

được xem là các origin khác nhau. Xóa dữ liệu của một origin không có nghĩa đã xóa dữ liệu của origin khác. Một số browser còn partition storage theo top-level site hoặc context; dữ liệu bên thứ ba có thể nằm trong partition riêng.

## 3. Chuẩn bị trước khi xóa

Trước khi thao tác:

1. Xác nhận đang ở đúng browser profile và đúng origin.
2. Xác định đây là local/staging hay production.
3. Ghi lại loại dữ liệu và mục tiêu cần xóa.
4. Nếu cần tái hiện lỗi, lưu request ID và metadata không nhạy cảm trước khi clear.
5. Không copy token, cookie hoặc password vào ticket/chat để làm bằng chứng.
6. Kiểm tra có tab khác hoặc service worker đang ghi lại dữ liệu hay không.

### 3.1 Dùng dữ liệu giả khi kiểm thử

Tạo tài khoản thử nghiệm và giá trị canary không cấp quyền, ví dụ `DEVTOOLS_CANARY_42`. Không đưa access token, session cookie hoặc dữ liệu khách hàng thật vào lab. Có thể kiểm tra thao tác xóa bằng cách tìm chuỗi canary trong storage và xác nhận nó không còn sau khi clear.

### 3.2 Lưu ý khi dùng profile chia sẻ

Browser profile có thể chứa dữ liệu của nhiều website và nhiều tài khoản. Tránh dùng nút xóa toàn bộ browsing data nếu mục tiêu chỉ là xóa dữ liệu của một origin. Với máy dùng chung, ưu tiên profile kiểm thử riêng và quy trình teardown rõ ràng.

## 4. Xóa danh sách request trong Network panel

Network panel hiển thị các request được ghi nhận trong phiên DevTools. Mỗi entry có thể chứa URL, request headers, cookies, query string, request payload, response body, timing và initiator.

### 4.1 Clear Network log

Trong Chrome DevTools:

1. Mở DevTools bằng F12 hoặc Ctrl+Shift+I.
2. Chọn tab **Network**.
3. Dừng hoặc hoàn tất thao tác đang kiểm thử nếu cần giữ metadata để phân tích.
4. Nhấn nút Clear network log (biểu tượng xóa ở thanh công cụ Network).
5. Xác nhận danh sách request hiện tại đã trống.

Thao tác này xóa các entry đang hiển thị trong Network panel. Nó không xóa dữ liệu đã gửi tới server, browser storage, cookie, cache hoặc server access log.

### 4.2 Preserve log

Tùy chọn **Preserve log** giữ lại request khi trang điều hướng hoặc reload. Nếu bật, request cũ có thể tiếp tục xuất hiện sau navigation khiến người kiểm thử tưởng rằng dữ liệu chưa được xóa.

- Tắt Preserve log khi muốn bắt đầu một phiên quan sát sạch.
- Clear network log trước khi tái hiện.
- Kiểm tra lại sau navigation để phân biệt request mới với entry được giữ lại.

### 4.3 Disable cache không phải xóa cache

Checkbox **Disable cache** trong Network panel khiến browser bỏ qua HTTP cache trong khi DevTools đang mở theo hành vi của browser. Nó hữu ích khi kiểm thử tải tài nguyên mới, nhưng không phải thao tác xóa toàn bộ cache đã lưu.

Để xóa HTTP cache, dùng thao tác Empty cache and hard reload hoặc privacy settings của browser. Cách xóa và phạm vi có thể thay đổi theo phiên bản.

### 4.4 HAR export có thể chứa dữ liệu nhạy cảm

Export HAR có thể bao gồm URL, query, request/response headers, cookie và payload. Không chia sẻ HAR thô nếu chưa kiểm tra và loại bỏ dữ liệu nhạy cảm. Bật tùy chọn sanitize khi công cụ hỗ trợ, sau đó vẫn rà soát file export trước khi gửi.

## 5. Xóa nội dung trong Console

Console thường hiển thị log ứng dụng, warning, exception, object và giá trị được developer in ra. Nếu code vô tình gọi `console.log(token)` hoặc in toàn bộ request object, bí mật có thể xuất hiện tại đây.

### 5.1 Clear Console

1. Chọn tab **Console**.
2. Nhấn Clear console hoặc dùng phím tắt tương ứng với browser.
3. Tắt **Preserve log** nếu không muốn log tiếp tục tồn tại qua navigation.
4. Reload hoặc thực hiện lại thao tác để quan sát log mới.

Clear Console chỉ xóa nội dung đang hiển thị trong panel. Nó không sửa source code, không xóa log được gửi tới telemetry và không xóa dữ liệu mà ứng dụng lưu ở storage.

### 5.2 Lệnh console.clear()

Trong JavaScript, `console.clear()` yêu cầu Console được làm sạch:

```javascript
console.clear();
```

Đây là thao tác giao diện hỗ trợ debug, không phải biện pháp xóa secret an toàn. Browser có thể giữ lại log khi Preserve log bật hoặc theo hành vi riêng của DevTools.

### 5.3 Ngăn dữ liệu nhạy cảm xuất hiện trở lại

Không log:

- Password, OTP, access/refresh token hoặc session ID.
- Cookie header, Authorization header và private key.
- Toàn bộ request/response object khi có thể chứa credential.
- Form body hoặc profile cá nhân không cần thiết.

Thay vào đó, log request ID, route template, status code, duration và error code. Redaction cần được thực hiện trước khi log được chuyển sang collector/APM.

## 6. Xóa dữ liệu bằng Application → Storage

Tab **Application** là nơi thuận tiện để kiểm tra nhiều loại site data.

Trong Chrome DevTools:

1. Chọn **Application**.
2. Mở nhóm **Storage**.
3. Kiểm tra dung lượng và loại storage đang được sử dụng.
4. Chọn **Clear site data** để xóa dữ liệu site được browser hỗ trợ trong phạm vi hiện tại.
5. Reload trang và kiểm tra ứng dụng có tạo lại dữ liệu hay không.

Các mục được hiển thị có thể thay đổi theo browser/version. Tùy chọn clear thường bao gồm cookie, local/session storage, IndexedDB, Cache Storage và một số loại site data khác. HTTP cache, browser history, download history, saved passwords và dữ liệu server-side có thể cần thao tác riêng.

### 6.1 Chọn đúng origin

Application panel hiển thị storage theo origin hoặc storage partition. Kiểm tra host, scheme và port trước khi xóa. Nếu ứng dụng dùng nhiều subdomain, xóa `app.example.test` không tự động xóa `files.example.test`.

### 6.2 Kiểm tra lại sau Clear site data

Sau khi clear:

- Mở lại các mục Cookies, Local Storage, Session Storage, IndexedDB và Cache Storage.
- Xác nhận dữ liệu mục tiêu không còn.
- Reload trang và theo dõi Network để xem app có gọi API khôi phục state hay không.
- Kiểm tra Service Worker nếu offline cache vẫn phục vụ nội dung cũ.

Clear site data là thao tác mạnh đối với origin đã chọn. Nó có thể đăng xuất user, xóa offline data hoặc làm mất trạng thái chưa đồng bộ. Chỉ thực hiện khi phạm vi xóa đã rõ.

## 7. Xóa Cookies trong Application panel

Cookie có thể giữ session ID, refresh credential, CSRF token hoặc preference. Trong Application → Storage → Cookies:

1. Chọn origin/domain tương ứng.
2. Xem danh sách cookie và thuộc tính.
3. Chọn cookie mục tiêu.
4. Dùng Delete hoặc Clear để xóa cookie đã chọn/theo origin.
5. Reload và kiểm tra response Set-Cookie có tạo lại cookie hay không.

### 7.1 Cookie HttpOnly

`HttpOnly` ngăn JavaScript truy cập cookie qua `document.cookie`, nhưng không làm cookie vô hình với mọi công cụ quản trị browser. DevTools có thể hiển thị và cho phép xóa cookie trong Application panel. Đây là thao tác browser-side; server session vẫn có thể còn hiệu lực nếu backend chưa revoke.

### 7.2 Cookie scope

Cookie được xác định bởi các thuộc tính như name, domain/host, path và partition context. Một cookie cùng tên có thể tồn tại ở path hoặc scope khác. Khi kiểm tra cookie còn sót, xem toàn bộ danh sách và thuộc tính thay vì chỉ tìm theo tên.

### 7.3 Xóa cookie không tương đương logout server-side

Xóa cookie khiến browser không gửi giá trị đó trong request tiếp theo. Nếu server vẫn chấp nhận session ID đã bị lộ, attacker có thể tiếp tục dùng bản sao của session. Logout an toàn cần endpoint revoke/invalidate session ở server, sau đó xóa cookie ở browser với đúng scope.

### 7.4 Cookie có thể được tạo lại

Sau khi xóa, reload hoặc gọi API có thể nhận Set-Cookie mới. Nếu cookie xuất hiện trở lại, xác định request/response tạo nó và kiểm tra luồng đăng nhập, refresh hoặc session bootstrap.

## 8. Xóa localStorage và sessionStorage

Trong Application panel:

1. Mở **Local Storage** hoặc **Session Storage**.
2. Chọn origin.
3. Xem key/value cần xóa.
4. Chọn một row để delete hoặc dùng Clear all cho storage tương ứng.
5. Reload và kiểm tra ứng dụng không còn đọc được giá trị cũ.

### 8.1 Xóa qua Console

Trong Console của đúng origin:

```javascript
// Xóa toàn bộ localStorage của origin hiện tại.
localStorage.clear();

// Xóa toàn bộ sessionStorage của tab/browsing context hiện tại.
sessionStorage.clear();

// Chỉ xóa một key nếu biết chính xác key cần bỏ.
localStorage.removeItem("profile-cache");
sessionStorage.removeItem("draft-form");
```

Các lệnh này chỉ tác động storage của origin hiện tại. Không chạy từ một tab khác rồi kỳ vọng xóa dữ liệu của origin ứng dụng. Nếu cần xóa một key cụ thể, ưu tiên `removeItem()` để giữ các dữ liệu khác.

### 8.2 Khác biệt giữa localStorage và sessionStorage

| Thuộc tính | localStorage | sessionStorage |
| --- | --- | --- |
| Phạm vi | Origin | Origin và tab/top-level browsing context |
| Thời gian tồn tại | Qua reload và thường qua lần mở browser | Thường kết thúc khi tab/window đóng |
| Chia sẻ giữa tab | Các tab cùng origin có thể truy cập cùng storage area | Mỗi tab có storage area riêng; tab mở bằng opener có một số quy tắc khởi tạo đặc biệt |
| API xóa | `clear()`, `removeItem()` | `clear()`, `removeItem()` |

Đừng giả định đóng tab là đã xóa mọi dữ liệu nhạy cảm. localStorage tồn tại lâu hơn; IndexedDB và Cache Storage cũng không tự mất khi tab đóng.

### 8.3 Memory của JavaScript vẫn có thể giữ dữ liệu

`localStorage.clear()` không xóa biến JavaScript đã đọc trước đó:

```javascript
const token = localStorage.getItem("access-token");
localStorage.clear();

// Biến token vẫn còn trong memory của runtime hiện tại.
console.log(Boolean(token));
```

Sau logout, ứng dụng cần xóa state trong memory, dừng timer/refresh loop, hủy request phù hợp và điều hướng sang trạng thái đã đăng xuất. Reload hoặc đóng tab có thể kết thúc runtime hiện tại, nhưng không thu hồi credential phía server.

## 9. Xóa IndexedDB

IndexedDB lưu dữ liệu có cấu trúc và có thể chứa offline records, bản nháp, cache API hoặc profile. Trong Application → IndexedDB:

1. Mở database của origin.
2. Chọn object store cần kiểm tra.
3. Xem record và xác định dữ liệu mục tiêu.
4. Xóa record cụ thể nếu chỉ cần loại bỏ một mục.
5. Xóa database nếu muốn reset toàn bộ state của database đó.
6. Reload và kiểm tra ứng dụng có tạo database hoặc record mới không.

### 9.1 Xóa database qua Console

```javascript
function deleteDatabase(name) {
  return new Promise((resolve, reject) => {
    const request = indexedDB.deleteDatabase(name);
    request.onsuccess = () => resolve();
    request.onerror = () => reject(request.error);
    request.onblocked = () => {
      console.warn("Close other tabs/connections before deleting", name);
    };
  });
}

await deleteDatabase("app-cache");
```

Tên database phải lấy từ Application panel hoặc tài liệu ứng dụng. Không đoán tên và không xóa database của origin khác.

### 9.2 Blocked deletion

IndexedDB có thể giữ connection đang mở từ tab hiện tại, tab khác hoặc worker. Khi có connection chưa đóng, thao tác delete có thể phát `blocked` và chưa hoàn tất. Đóng các tab/worker liên quan hoặc để ứng dụng xử lý sự kiện `versionchange` để đóng connection.

Không báo xóa thành công chỉ vì đã gọi `deleteDatabase()`. Chờ `onsuccess`, xử lý `onerror` và kiểm tra lại danh sách database.

### 9.3 Xóa database có thể làm mất dữ liệu chưa đồng bộ

Ứng dụng offline có thể lưu thay đổi chưa gửi server trong IndexedDB. Xóa database có thể làm mất các thay đổi đó. Trước khi clear, kiểm tra trạng thái đồng bộ và chính sách khôi phục; chỉ dùng thao tác này khi dữ liệu có thể tái tạo hoặc đã được xử lý.

## 10. Xóa Cache Storage

Cache Storage thường được dùng bởi Service Worker hoặc ứng dụng web để lưu response cho offline behavior. Nó khác HTTP cache của browser.

Trong Application → Cache Storage:

1. Chọn cache name.
2. Kiểm tra request/response đang được lưu.
3. Xóa entry cụ thể hoặc xóa cache.
4. Kiểm tra các cache name còn lại.
5. Reload và xem service worker có tạo lại cache hay không.

### 10.1 Xóa cache bằng Console

```javascript
async function clearAppCaches() {
  const names = await caches.keys();
  await Promise.all(names.map((name) => caches.delete(name)));
  return names;
}

const removedCacheNames = await clearAppCaches();
console.log("Deleted Cache Storage entries:", removedCacheNames.length);
```

Đoạn mã xóa mọi Cache Storage cache của origin hiện tại. Chỉ chạy trong profile kiểm thử khi đã xác nhận không cần giữ offline data. Trong ứng dụng thật, nên xóa đúng cache name hoặc dùng versioned cache cleanup của ứng dụng.

### 10.2 Xóa Cache Storage không xóa HTTP cache

Một response có thể được lưu trong Cache Storage và HTTP cache cùng lúc. Xóa một nơi không bảo đảm nơi kia đã trống. Khi điều tra nội dung cũ, kiểm tra cả Application → Cache Storage, Network cache behavior và response headers như `Cache-Control`.

## 11. Unregister Service Worker

Service Worker có thể intercept request, trả response từ Cache Storage và tiếp tục hoạt động khi không có tab hiển thị. Khi xóa site data hoặc thay đổi cache, cần kiểm tra worker:

1. Mở Application → Service Workers.
2. Xem registration, scope và trạng thái worker.
3. Chọn **Unregister** nếu muốn gỡ registration của origin trong môi trường kiểm thử.
4. Reload trang để kiểm tra worker có được đăng ký lại hay không.

### 11.1 Unregister không tự động xóa mọi cache

Gỡ registration Service Worker không nên được coi là thao tác xóa Cache Storage. Hãy kiểm tra và xóa cache riêng nếu mục tiêu là xóa dữ liệu offline. Các tab đang được worker kiểm soát có thể tiếp tục ở trạng thái cũ cho đến khi được reload/đóng và vòng đời worker hoàn tất.

### 11.2 Ứng dụng có thể đăng ký lại worker

Nếu code ứng dụng vẫn gọi `navigator.serviceWorker.register()`, worker có thể xuất hiện lại sau reload. Để kiểm tra teardown, tìm registration source và xác nhận app không tự khởi tạo lại trong môi trường test.

### 11.3 Unregister worker bằng Console

```javascript
const registrations = await navigator.serviceWorker.getRegistrations();
const results = await Promise.all(
  registrations.map((registration) => registration.unregister())
);

console.log("Unregistered:", results.filter(Boolean).length);
```

Lệnh trên tác động các registration trong phạm vi origin hiện tại. Nó không xóa Cache Storage, IndexedDB hoặc cookie. Kiểm tra kết quả và reload để xác nhận.

## 12. Xóa HTTP cache

HTTP cache lưu response theo quy tắc caching của HTTP và browser. Nó thường chứa CSS, JavaScript, ảnh, font hoặc response GET cacheable. Cache này khác Cache Storage do ứng dụng/service worker quản lý.

### 12.1 Empty cache and hard reload

Trong Chrome, có thể:

1. Mở DevTools.
2. Nhấn giữ hoặc click phải nút Reload của browser.
3. Chọn **Empty cache and hard reload** nếu tùy chọn xuất hiện.

Thao tác này hữu ích khi cần kiểm thử tài nguyên được tải lại. Nó không xóa cookie, localStorage, IndexedDB hoặc log server.

### 12.2 Disable cache

Network → **Disable cache** thường chỉ có hiệu lực khi DevTools mở. Nó bỏ qua HTTP cache trong lần kiểm thử tiếp theo, nhưng không đồng nghĩa dữ liệu cache đã được xóa khỏi profile.

### 12.3 Cache-Control

Server quyết định khả năng cache bằng response headers. Với response chứa thông tin riêng tư hoặc credential, cân nhắc:

```http
Cache-Control: no-store
```

`no-store` yêu cầu cache không lưu response theo semantics HTTP caching. Nó không xóa các bản sao đã lưu trước đó và không thay thế xóa Cache Storage do JavaScript quản lý.

## 13. History, downloads và dữ liệu browser profile

Application → Storage không phải nơi quản lý mọi dữ liệu browser. Các mục sau có thể cần thao tác trong browser settings:

| Dữ liệu | Nơi quản lý thường gặp |
| --- | --- |
| Browsing history | History page hoặc Clear browsing data |
| Download history | Downloads page |
| File đã tải xuống | Filesystem; xóa file bằng công cụ hệ điều hành |
| Saved passwords/passkeys | Password manager/browser settings |
| Autofill/form data | Privacy/autofill settings |
| Site permissions | Site settings |
| Cached images/files | Clear browsing data hoặc browser cache controls |

Xóa download history không xóa file đã tải khỏi filesystem. Xóa file trong filesystem cũng không nhất thiết xóa entry lịch sử download. Hai việc có phạm vi khác nhau.

### 13.1 Clear browsing data theo thời gian

Browser thường cho phép chọn khoảng thời gian như last hour, last 24 hours, last 7 days hoặc all time và chọn loại dữ liệu cần xóa. Đọc kỹ checkbox trước khi xác nhận; chọn sai có thể xóa password đã lưu, history hoặc dữ liệu của nhiều website.

### 13.2 Profile riêng cho kiểm thử

Một browser profile chuyên dụng giúp giới hạn dữ liệu lẫn giữa dự án và tài khoản. Khi kết thúc phiên test, có thể xóa site data hoặc bỏ profile kiểm thử theo chính sách môi trường. Không cần dùng profile cá nhân để thử các tình huống logout, storage reset hoặc cookie scope.

## 14. Dữ liệu phía server không thể xóa bằng DevTools

DevTools chỉ quản lý dữ liệu mà browser profile hoặc trang hiện tại có quyền quan sát/thao tác. Khi request đã tới server, một số bản sao có thể tồn tại ở:

- Database nghiệp vụ và object storage.
- Session store, token store và cache phía backend.
- Access log của web server, reverse proxy, CDN và WAF.
- APM trace, error reporting, analytics và session replay.
- Message queue, event stream, data warehouse và SIEM.
- Snapshot, backup, archive và export.

Xóa cookie hoặc localStorage không xóa các bản sao này. Xóa Network log cũng không thu hồi request đã gửi. Nếu cần xóa dữ liệu tài khoản, dùng API hoặc quy trình quản trị được ứng dụng cung cấp; nếu cần xóa log, phải theo retention policy và quy trình của hệ thống logging.

### 14.1 Revoke session và token

Logout đúng nghĩa thường cần:

1. Gọi endpoint logout/revoke bằng session hiện tại.
2. Backend invalidate session hoặc refresh token family theo policy.
3. Backend gửi cookie hết hạn với đúng name, path và domain scope.
4. Frontend xóa token/state trong memory và các storage do ứng dụng quản lý.
5. Frontend xóa cache chứa dữ liệu riêng tư và dừng tác vụ nền.
6. Điều hướng tới trang đã đăng xuất và xác nhận request tiếp theo không còn dùng credential cũ.

Nếu chỉ xóa cookie trong DevTools, session phía server có thể còn hiệu lực. Nếu chỉ xóa access token ở browser, token đã bị sao chép vẫn có thể dùng tới khi hết hạn hoặc bị revoke.

### 14.2 Xóa dữ liệu người dùng

Yêu cầu xóa dữ liệu tài khoản cần được xử lý ở backend theo quy trình sản phẩm/pháp lý. Backend có thể cần xóa hoặc ẩn dữ liệu trong database, object storage, search index và hệ thống downstream; backup có thể tuân theo chu kỳ retention riêng.

Không dùng DevTools để giả định một yêu cầu xóa dữ liệu đã hoàn tất. Kiểm tra trạng thái API/admin workflow và xác nhận phạm vi dữ liệu đã xử lý theo chính sách.

### 14.3 Bảo toàn chứng cứ khi điều tra sự cố

Nếu đang điều tra token leakage, account compromise hoặc hành vi bất thường, không xóa log/Network evidence một cách vội vàng. Ghi lại request ID, timestamp, actor và metadata không nhạy cảm theo incident process. Bảo toàn log ở hệ thống có thẩm quyền, revoke credential khi cần và hạn chế quyền truy cập vào dữ liệu lộ.

## 15. Thiết kế logout và cleanup ở ứng dụng

DevTools hữu ích để kiểm tra, nhưng ứng dụng phải có cleanup logic nhất quán. Một logout flow không nên chỉ xóa một key rồi để các bản sao khác tiếp tục tồn tại.

### 15.1 Xóa các key do ứng dụng sở hữu

Nếu ứng dụng chỉ dùng một số key đã định nghĩa, xóa rõ từng key:

```javascript
function clearClientAuthState() {
  localStorage.removeItem("access-token");
  localStorage.removeItem("user-profile");
  sessionStorage.removeItem("oauth-state");
  sessionStorage.removeItem("pkce-verifier");
}
```

Tên key chỉ là ví dụ. Ứng dụng cần quản lý danh sách key thực tế và tránh xóa dữ liệu không thuộc quyền sở hữu của module đang logout.

### 15.2 Xóa cache riêng tư

Nếu app lưu response riêng tư trong Cache Storage, dùng cache name được version hóa và xóa đúng cache:

```javascript
async function clearPrivateCache() {
  await caches.delete("private-api-v3");
}
```

Không xóa cache tĩnh dùng chung nếu không cần; điều đó có thể làm app tải lại toàn bộ asset và ảnh hưởng offline experience.

### 15.3 Dừng worker và tác vụ nền

Logout cần xem xét:

- Web Worker đang giữ dữ liệu trong memory.
- Service Worker đang quản lý cache hoặc background sync.
- Timer refresh token và polling.
- WebSocket/EventSource đang mở.
- Request đang chạy và retry queue.
- BroadcastChannel/storage event giữa các tab.

Thông báo logout giữa các tab chỉ nên truyền sự kiện như `LOGOUT`; không gửi token hoặc cookie qua channel. Mỗi tab cần xóa state trong memory và dừng request tiếp theo.

### 15.4 Cookie cần được xóa ở server

JavaScript không thể xóa cookie `HttpOnly` bằng `document.cookie`. Server nên trả `Set-Cookie` hết hạn với cùng cookie name và scope thích hợp. Nếu có cookie cùng tên ở path/domain khác, cần xử lý đúng từng cookie.

## 16. Lab: tạo dữ liệu canary rồi xóa bằng DevTools

Lab chạy trên origin local/staging với dữ liệu giả. Không dùng credential thật.

### 16.1 Tạo dữ liệu thử nghiệm

Mở Console tại một trang local có HTTPS hoặc localhost, rồi chạy:

```javascript
localStorage.setItem("lab-secret", "DEVTOOLS_CANARY_42");
sessionStorage.setItem("lab-session", "DEVTOOLS_CANARY_42");

const dbRequest = indexedDB.open("devtools-lab", 1);
dbRequest.onupgradeneeded = () => {
  dbRequest.result.createObjectStore("records", { keyPath: "id" });
};
dbRequest.onsuccess = () => {
  const db = dbRequest.result;
  const tx = db.transaction("records", "readwrite");
  tx.objectStore("records").put({
    id: "sample-1",
    value: "DEVTOOLS_CANARY_42"
  });
  tx.oncomplete = () => db.close();
};

const cache = await caches.open("devtools-lab-cache");
await cache.put(
  "/lab-canary",
  new Response("DEVTOOLS_CANARY_42", {
    headers: { "Content-Type": "text/plain" }
  })
);
```

### 16.2 Xác nhận dữ liệu tồn tại

1. Application → Local Storage: tìm key `lab-secret`.
2. Application → Session Storage: tìm key `lab-session`.
3. Application → IndexedDB → `devtools-lab` → `records`: tìm record `sample-1`.
4. Application → Cache Storage → `devtools-lab-cache`: xem entry `/lab-canary`.
5. Network và Console: quan sát request/log của lab nếu đã tạo.

### 16.3 Xóa từng loại

- Xóa hai key Web Storage trong Application panel.
- Xóa database `devtools-lab` sau khi đóng connection.
- Xóa cache `devtools-lab-cache`.
- Clear Network log và Console output.
- Reload rồi kiểm tra các mục không còn.

Có thể dùng Console để xác minh:

```javascript
console.log(localStorage.getItem("lab-secret"));
console.log(sessionStorage.getItem("lab-session"));
console.log(await caches.keys());
```

Kết quả mong đợi là `null`, `null` và danh sách cache không còn `devtools-lab-cache`. Kiểm tra IndexedDB trong Application panel để xác nhận database đã bị xóa.

### 16.4 Thử Clear site data

Tạo lại dữ liệu canary, sau đó dùng Application → Storage → Clear site data. Reload trang và kiểm tra lại từng loại storage. Nếu dữ liệu xuất hiện lại, xác định code khởi tạo hoặc service worker đang seed dữ liệu.

## 17. Quy trình kiểm tra sau khi xóa

Một thao tác xóa chỉ hoàn tất khi đã xác minh kết quả và hiểu dữ liệu có được tạo lại hay không:

1. Xác định origin và profile trước khi xóa.
2. Clear đúng storage/panel theo mục tiêu.
3. Reload hoặc mở tab mới trong cùng profile.
4. Kiểm tra Application panel không còn cookie/storage/cache mục tiêu.
5. Kiểm tra Service Worker registration và Cache Storage.
6. Quan sát Network để xem API có khôi phục state hay `Set-Cookie` tạo cookie mới.
7. Kiểm tra Console không còn log cũ được Preserve log giữ lại.
8. Đăng xuất/đăng nhập bằng tài khoản test khác để xác nhận không rò state giữa user.
9. Nếu cần server-side deletion, xác minh qua API/admin workflow riêng.

### 17.1 Phân biệt dữ liệu đã xóa và dữ liệu được tạo lại

Nếu key biến mất ngay sau Clear site data nhưng xuất hiện sau reload, có thể ứng dụng đã tải state từ backend hoặc chạy initialization code. Điều này không nhất thiết là thao tác xóa thất bại. Kiểm tra thời điểm xuất hiện, initiator và request liên quan để xác định nguồn tái tạo.

### 17.2 Kiểm tra tab khác

localStorage và một số cookie có thể dùng chung giữa các tab cùng origin. Một tab khác có thể ghi lại dữ liệu sau khi tab hiện tại đã xóa. Đóng hoặc reload các tab test, dừng worker và kiểm tra lại sau khi môi trường ổn định.

## 18. Những nhầm lẫn thường gặp

| Nhầm lẫn | Thực tế | Cách kiểm tra |
| --- | --- | --- |
| Clear Network log xóa request khỏi server | Chỉ xóa entry trong panel. | Kiểm tra server log/request ID ở hệ thống có thẩm quyền. |
| Clear Console xóa log telemetry | Chỉ làm sạch Console UI. | Kiểm tra logger/collector và source code. |
| Xóa localStorage sẽ xóa token trong memory | Biến JavaScript vẫn còn trong runtime. | Kiểm tra logout state và reload/close tab. |
| Xóa cookie là logout hoàn toàn | Session phía server có thể còn hiệu lực. | Gọi revoke/logout và thử credential cũ trong test. |
| Unregister Service Worker xóa Cache Storage | Cache Storage là nơi lưu riêng. | Kiểm tra Application → Cache Storage. |
| Disable cache xóa HTTP cache | Nó thường chỉ bỏ qua cache khi DevTools mở. | Dùng Empty cache and hard reload hoặc browser settings. |
| Clear site data xóa mọi thứ trên browser | History, downloads, saved passwords và server data có thể còn. | Kiểm tra từng nơi theo mục tiêu. |
| Xóa download history xóa file | File vẫn nằm trên filesystem. | Kiểm tra thư mục download. |
| Xóa ở một origin xóa cả subdomain | Origin/storage partition khác nhau. | Kiểm tra scheme, host, port và partition. |
| Xóa browser data thu hồi token đã lộ | Bản sao token có thể vẫn được dùng. | Revoke token/session ở backend. |

## 19. Checklist review Xóa dữ liệu nhạy cảm

- [ ] Đã xác định đúng browser profile, origin và storage partition.
- [ ] Network log đã được clear nếu có request metadata nhạy cảm hiển thị.
- [ ] Preserve log được kiểm tra và tắt khi không cần giữ lịch sử điều hướng.
- [ ] Console output đã được clear và source code không log credential.
- [ ] Cookies đã được kiểm tra theo name, domain/host, path và partition.
- [ ] Session cookie HttpOnly được xóa qua browser/server flow phù hợp.
- [ ] localStorage và sessionStorage đã được kiểm tra.
- [ ] IndexedDB record/database đã được xóa và xác nhận không bị blocked.
- [ ] Cache Storage đã được xóa đúng cache.
- [ ] Service Worker đã được unregister nếu mục tiêu yêu cầu; cache được xử lý riêng.
- [ ] HTTP cache được xử lý bằng thao tác phù hợp.
- [ ] History, downloads, saved passwords và file trên filesystem được phân biệt rõ.
- [ ] Ứng dụng không tự tái tạo dữ liệu ngoài dự kiến sau reload.
- [ ] Logout đã revoke session/token phía server.
- [ ] Backend/logging/backup deletion được xử lý qua quy trình riêng khi cần.
- [ ] Dữ liệu canary không còn ở các vị trí browser đã kiểm tra.

## 20. Câu hỏi tự kiểm tra

1. Clear Network log khác Clear site data như thế nào?
2. Vì sao request đã gửi không thể bị thu hồi bằng cách clear Network panel?
3. Preserve log ảnh hưởng ra sao tới việc quan sát request sau navigation?
4. Vì sao HAR export có thể chứa credential?
5. `HttpOnly` ngăn JavaScript làm gì và DevTools có thể làm gì với cookie?
6. localStorage khác sessionStorage ở phạm vi và vòng đời nào?
7. Vì sao xóa localStorage không xóa biến token trong memory?
8. IndexedDB delete có thể bị blocked trong trường hợp nào?
9. Cache Storage khác HTTP cache ở điểm nào?
10. Unregister Service Worker có tự xóa Cache Storage không?
11. Vì sao xóa cookie không thay thế server-side session revocation?
12. Clear site data có xóa browser history và file đã download không?
13. Cần làm gì khi dữ liệu xuất hiện lại sau khi reload?
14. Vì sao không nên clear log trong khi đang bảo toàn chứng cứ sự cố?

## 21. Tổng kết

Developer Tools giúp quan sát và xóa nhiều loại dữ liệu browser theo origin: cookie, localStorage, sessionStorage, IndexedDB, Cache Storage và Service Worker state. Network và Console panel cũng có thể giữ URL, payload, response preview hoặc log nhạy cảm trong giao diện debug. Mỗi thao tác có phạm vi riêng: clear panel không xóa browser storage; xóa Cache Storage không xóa HTTP cache; unregister Service Worker không tự bảo đảm cache đã bị xóa.

Trước khi clear, xác định đúng profile, origin, loại dữ liệu và nguy cơ mất state chưa đồng bộ. Sau khi xóa, reload và kiểm tra dữ liệu có được tạo lại từ code, service worker hoặc backend hay không. Dùng canary data trong lab để xác minh mà không đưa credential thật vào môi trường kiểm thử.

DevTools không xóa được bản sao ở backend, APM, CDN, SIEM, backup hoặc filesystem. Logout cần revoke session/token phía server, xóa cookie đúng scope và dọn state phía client. Khi xử lý incident, bảo toàn chứng cứ theo quy trình trước khi xóa. Xóa dữ liệu nhạy cảm hiệu quả đòi hỏi xác định đúng nơi lưu, xóa đúng lớp và xác minh kết quả ở từng hệ thống liên quan.

## 22. Tài liệu tham khảo

- [Chrome DevTools: View and edit storage](https://developer.chrome.com/docs/devtools/storage/)
- [Chrome DevTools: Network panel](https://developer.chrome.com/docs/devtools/network/)
- [Chrome DevTools: Console overview](https://developer.chrome.com/docs/devtools/console/)
- [MDN: Storage.clear()](https://developer.mozilla.org/docs/Web/API/Storage/clear)
- [MDN: IndexedDB API](https://developer.mozilla.org/docs/Web/API/IndexedDB_API)
- [MDN: CacheStorage](https://developer.mozilla.org/docs/Web/API/CacheStorage)
- [MDN: ServiceWorkerRegistration.unregister()](https://developer.mozilla.org/docs/Web/API/ServiceWorkerRegistration/unregister)
- [MDN: HTTP caching](https://developer.mozilla.org/docs/Web/HTTP/Caching)
- [MDN: Clear-Site-Data header](https://developer.mozilla.org/docs/Web/HTTP/Headers/Clear-Site-Data)
