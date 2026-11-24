# Storage cleanup

## Mục tiêu bài học

Sau bài này, bạn có thể:

- Xác định dữ liệu nào cần được dọn khi đăng xuất, đổi tài khoản, đổi tenant, hết hạn lưu trữ hoặc người dùng yêu cầu xóa dữ liệu.
- Chọn đúng API để xóa cookie, `localStorage`, `sessionStorage`, IndexedDB và Cache API theo phạm vi mà ứng dụng sở hữu.
- Xử lý các trường hợp dữ liệu còn được giữ bởi tab khác, kết nối IndexedDB đang mở hoặc service worker.
- Kiểm chứng việc dọn dữ liệu bằng DevTools và bằng hành vi của ứng dụng sau khi đăng nhập lại.
- Nhận biết giới hạn của việc xóa dữ liệu phía trình duyệt và phối hợp với máy chủ để kết thúc phiên, thu hồi quyền truy cập.

## 1. Vì sao cần có chính sách dọn dữ liệu

Dữ liệu trong trình duyệt có thể tồn tại lâu hơn một lần tải trang. `localStorage`, IndexedDB và Cache API thường tồn tại qua nhiều lần đóng mở tab hoặc khởi động lại trình duyệt. Cookie có thể được gửi tự động trong những request phù hợp với domain, path, thuộc tính SameSite và các quy tắc phân vùng của trình duyệt. Một ứng dụng vì thế có thể tiếp tục giữ thông tin của người dùng trước sau khi họ đăng xuất hoặc chuyển sang tài khoản khác.

Điều này tạo ra một số rủi ro thực tế:

- Người dùng tiếp theo trên cùng thiết bị nhìn thấy tên, hồ sơ, bản nháp hoặc dữ liệu nghiệp vụ của tài khoản trước.
- Một tab cũ tiếp tục hiển thị dữ liệu đã tải trước khi phiên đăng nhập kết thúc.
- Service worker trả về bản cache cũ hoặc dữ liệu riêng tư khi ứng dụng đang ở chế độ offline.
- Token hoặc mã định danh phiên còn tồn tại trong storage dù máy chủ đã hoặc chưa thu hồi phiên.
- Dữ liệu hết thời hạn lưu giữ vẫn chiếm dung lượng và tiếp tục được xử lý.

Storage cleanup là một phần của vòng đời dữ liệu. Ứng dụng cần xác định dữ liệu nào được phép tồn tại, dữ liệu thuộc về ai, điều kiện nào kết thúc nhu cầu sử dụng và thành phần nào chịu trách nhiệm xóa. Một lệnh `clear()` duy nhất không thể thay thế chính sách đó vì các API có phạm vi, vòng đời và quyền truy cập khác nhau.

Việc xóa storage cũng không thay thế kiểm tra quyền ở máy chủ. Nếu máy chủ vẫn chấp nhận session cũ, người dùng có thể tạo request hợp lệ trở lại dù giao diện đã xóa dữ liệu cục bộ. Ngược lại, thu hồi session ở máy chủ không tự động xóa bản sao hồ sơ hoặc bản nháp đã lưu trong IndexedDB.

## 2. Xác định phạm vi của từng vùng lưu trữ

Trước khi viết cleanup, hãy lập danh sách các vùng mà ứng dụng thực sự sử dụng. Bảng sau mô tả phạm vi thường gặp; trình duyệt có thể áp dụng thêm storage partitioning cho một số ngữ cảnh nhúng.

| Vùng lưu trữ | Phạm vi và vòng đời | Cách dọn phù hợp |
| --- | --- | --- |
| Cookie | Được gửi theo domain, path, Secure, SameSite và các thuộc tính liên quan. Cookie có thể là host-only, có Domain hoặc được phân vùng. | Máy chủ gửi `Set-Cookie` hết hạn với cùng tên, domain và path. JavaScript chỉ thao tác được cookie không có `HttpOnly`. |
| `localStorage` | Theo origin; các tab cùng origin có thể dùng chung dữ liệu. Thường tồn tại sau khi đóng tab và khởi động lại trình duyệt. | Xóa các key do ứng dụng sở hữu bằng `removeItem()`. |
| `sessionStorage` | Theo origin và browsing context cấp cao nhất, thường tương ứng với từng tab. Tồn tại qua điều hướng trong tab và kết thúc khi tab hoặc cửa sổ đóng. | Xóa các key của phiên hiện tại bằng `removeItem()`. Không coi việc đóng tab là quy trình đăng xuất đầy đủ. |
| IndexedDB | Theo storage key của ngữ cảnh; thường được dùng chung giữa các trang cùng origin trong cùng phân vùng. Dữ liệu tồn tại lâu dài. | Xóa record theo tài khoản trong transaction, hoặc xóa database riêng của ứng dụng bằng `indexedDB.deleteDatabase()`. |
| Cache API | Lưu các `Request`/`Response` trong Cache Storage của ngữ cảnh. Tên cache do ứng dụng đặt; service worker thường quản lý cache. | Xóa đúng cache do ứng dụng sở hữu bằng `caches.delete()`. |
| HTTP cache | Do trình duyệt quản lý theo các HTTP caching header và chính sách của trình duyệt. | Thiết lập `Cache-Control` phù hợp; cân nhắc `Clear-Site-Data` khi cần reset phạm vi rộng. |
| Bộ nhớ trong JavaScript | State của framework, biến, worker và các object còn được tham chiếu trong trang. | Reset state, hủy tác vụ, gửi thông điệp cho worker và giải phóng tham chiếu do ứng dụng quản lý. Không có API bảo đảm ghi đè tức thời mọi byte trong RAM. |

Cookie có một điểm khác biệt quan trọng: tên cookie chưa đủ để xác định cookie cần xóa. Một cookie có cùng tên nhưng khác domain hoặc path có thể là cookie khác. Cookie `HttpOnly` không xuất hiện trong `document.cookie`, vì vậy mã JavaScript không thể xóa nó. Cookie phiên xác thực nên được máy chủ kết thúc bằng response `Set-Cookie` tương ứng.

Với cookie có thuộc tính `Partitioned`, dữ liệu còn gắn với partition key của top-level site. Khi kiểm thử cleanup, hãy kiểm tra đúng ngữ cảnh nhúng và phân vùng mà cookie được tạo ra.

Origin cũng là ranh giới bảo mật của phần lớn Web Storage và IndexedDB. Một trang không thể dùng JavaScript để xóa storage của origin khác. Với nội dung bên thứ ba được nhúng, trình duyệt có thể phân vùng storage theo top-level site. Vì vậy, thao tác trên storage của trang cha không đồng nghĩa đã xóa dữ liệu thuộc phân vùng của iframe bên thứ ba.

## 3. Xây dựng chính sách cleanup theo sự kiện

Không phải mọi sự kiện đều cần xóa mọi loại dữ liệu. Hãy phân loại dữ liệu thành dữ liệu công khai dùng chung, dữ liệu riêng của tài khoản, dữ liệu tạm thời và dữ liệu xác thực. Sau đó xác định hành động cho từng sự kiện.

| Sự kiện | Hành động nên thực hiện | Điểm cần kiểm tra |
| --- | --- | --- |
| Đăng xuất | Thu hồi session ở máy chủ; hết hạn cookie xác thực; xóa state, key, record và cache riêng tư của tài khoản; thông báo cho tab khác. | API riêng tư phải từ chối session cũ; trang cũ không được tiếp tục hiển thị dữ liệu nhạy cảm. |
| Chuyển tài khoản | Hoàn tất logout của tài khoản cũ rồi mới khởi tạo state tài khoản mới; xóa hoặc cô lập dữ liệu cũ. | Không được hiển thị cache của tài khoản A trong giao diện tài khoản B. |
| Chuyển tenant hoặc tổ chức | Xóa state gắn với tenant cũ hoặc dùng namespace tách biệt có kiểm tra quyền. | Không dùng một cache key chung cho nhiều tenant nếu response chứa dữ liệu riêng. |
| Hết hạn dữ liệu | Xóa record đã quá hạn theo chính sách retention; thực hiện theo batch nếu tập dữ liệu lớn. | Kiểm tra `expiresAt` ở cả lúc đọc và lúc chạy tác vụ dọn. |
| Người dùng yêu cầu xóa tài khoản hoặc dữ liệu | Gửi yêu cầu xóa đến máy chủ và các hệ thống xử lý liên quan; dọn bản sao cục bộ thuộc ứng dụng. | Xóa local storage không chứng minh dữ liệu đã bị xóa khỏi máy chủ, bản sao lưu hoặc nhà cung cấp khác. |
| Đặt lại ứng dụng | Xóa đúng vùng dữ liệu do ứng dụng sở hữu và khởi tạo lại cấu hình mặc định. | Không xóa dữ liệu của ứng dụng khác cùng origin hoặc dữ liệu dùng chung ngoài phạm vi yêu cầu. |

Nên đặt tên key, database và cache có namespace rõ ràng, ví dụ `portal:user-profile`, `portal-user-data-v3` và `portal-user-api-v2`. Khi có nhiều tài khoản hoặc tenant, record cần có định danh chủ sở hữu. Với dữ liệu có thể lưu lâu, nên lưu thời điểm hết hạn hoặc phiên bản schema để ứng dụng chủ động dọn dữ liệu cũ.

Tránh gọi `localStorage.clear()` hoặc xóa toàn bộ Cache Storage trong một ứng dụng có nhiều module cùng origin. Những thao tác đó có thể xóa cấu hình dùng chung, lựa chọn ngôn ngữ, dữ liệu của module khác hoặc cache tài nguyên tĩnh cần thiết để ứng dụng hoạt động. Hãy ưu tiên xóa đúng key, record, database hoặc cache mà module sở hữu.

## 4. Xóa Web Storage theo key

Với `localStorage` và `sessionStorage`, hãy duy trì danh sách key do từng module sở hữu. Ví dụ:

```js
const ACCOUNT_LOCAL_KEYS = [
  "portal:user-profile",
  "portal:user-preferences",
  "portal:last-private-view"
];

const ACCOUNT_SESSION_KEYS = [
  "portal:temporary-form",
  "portal:pending-navigation"
];

function clearAccountWebStorage() {
  const failures = [];

  try {
    for (const key of ACCOUNT_LOCAL_KEYS) {
      localStorage.removeItem(key);
    }
  } catch (error) {
    failures.push({ area: "localStorage", error });
  }

  try {
    for (const key of ACCOUNT_SESSION_KEYS) {
      sessionStorage.removeItem(key);
    }
  } catch (error) {
    failures.push({ area: "sessionStorage", error });
  }

  return failures;
}
```

Ví dụ này bắt lỗi theo từng vùng để ứng dụng có thể ghi nhận rằng cleanup chưa hoàn tất. Việc truy cập storage có thể thất bại trong một số ngữ cảnh bị giới hạn quyền hoặc khi trình duyệt áp dụng chính sách riêng tư. Không nên bỏ qua lỗi rồi báo cho người dùng rằng mọi dữ liệu đã được xóa.

`sessionStorage` thường chỉ đại diện cho tab hiện tại. Nếu người dùng đăng xuất trong một tab, các tab khác vẫn có thể giữ state và dữ liệu đã tải. Cần phối hợp giữa các tab như phần 7, đồng thời yêu cầu máy chủ xác thực lại mọi request cần quyền truy cập.

## 5. Xóa IndexedDB và xử lý kết nối đang mở

IndexedDB thường chứa dữ liệu có cấu trúc như hồ sơ, bản nháp, hàng đợi đồng bộ hoặc dữ liệu offline. Có hai cách dọn chính:

- Nếu database dùng chung cho nhiều tài khoản hoặc module, xóa record thuộc tài khoản hiện tại bằng transaction và điều kiện lọc theo owner ID.
- Nếu database chỉ chứa dữ liệu riêng của một ứng dụng hoặc một vùng nghiệp vụ, có thể xóa toàn bộ database bằng `indexedDB.deleteDatabase(name)`.

Ví dụ xóa một database riêng của ứng dụng:

```js
function deleteDatabase(name) {
  return new Promise((resolve, reject) => {
    const request = indexedDB.deleteDatabase(name);

    request.onsuccess = () => resolve();
    request.onerror = () => {
      reject(request.error || new Error(`Cannot delete database: ${name}`));
    };
    request.onblocked = () => {
      // Hiển thị trạng thái: một tab khác vẫn đang giữ kết nối database.
      console.warn(`Database deletion is blocked: ${name}`);
    };
  });
}

async function clearAccountDatabase() {
  await deleteDatabase("portal-user-data-v3");
}
```

Lệnh xóa có thể phát sinh sự kiện `blocked` nếu một tab hoặc worker khác vẫn giữ kết nối database. Khi đó request chưa hoàn tất. Ứng dụng nên đóng kết nối khi nhận `versionchange`:

```js
const request = indexedDB.open("portal-user-data-v3");

request.onsuccess = () => {
  const db = request.result;
  db.onversionchange = () => {
    db.close();
  };
};
```

Khi xóa database bị block, giao diện có thể yêu cầu các tab còn lại đóng kết nối hoặc tự chuyển chúng sang trạng thái đăng xuất. Không nên giả định `deleteDatabase()` đã xóa xong chỉ vì hàm đã được gọi; hãy chờ `onsuccess` và xử lý `onerror`/`onblocked`.

Nếu database chứa cả dữ liệu công khai và dữ liệu riêng tư, xóa toàn bộ database khi logout có thể làm mất dữ liệu dùng chung. Khi đó hãy xóa các object store hoặc record gắn với tài khoản bằng transaction. Việc xóa cần được thiết kế cùng schema, không nên dựa vào một thao tác xóa toàn bộ chỉ vì thuận tiện.

## 6. Dọn Cache API và dữ liệu do service worker quản lý

Cache API lưu response theo tên cache. Ứng dụng nên đặt tên cache theo mục đích và phiên bản, ví dụ `portal-static-v4` cho tài nguyên tĩnh và `portal-user-api-v2` cho dữ liệu riêng tư. Khi logout, chỉ xóa cache có chứa dữ liệu tài khoản:

```js
async function clearAccountCaches() {
  if (!("caches" in window)) return [];

  const failures = [];
  let names;
  try {
    names = await caches.keys();
  } catch (error) {
    return [{ area: "CacheStorage", error }];
  }
  const accountCaches = names.filter((name) =>
    name.startsWith("portal-user-")
  );

  await Promise.all(accountCaches.map(async (name) => {
    try {
      await caches.delete(name);
    } catch (error) {
      failures.push({ cache: name, error });
    }
  }));

  return failures;
}
```

Service worker có thể tiếp tục chạy sau khi trang đã điều hướng hoặc đóng. Nếu service worker vẫn có logic ghi lại response riêng tư vào cache, dữ liệu có thể xuất hiện trở lại ngay sau cleanup. Vì vậy:

- Không cache response chứa thông tin nhạy cảm hoặc response phụ thuộc session nếu không có yêu cầu offline được thiết kế rõ ràng.
- Dùng allowlist cho URL được phép cache; tránh cache mọi request chỉ vì request thành công.
- Khi logout, gửi thông điệp cho service worker để dừng đồng bộ tài khoản cũ và xóa cache riêng tư do nó quản lý.
- Khi đổi tài khoản, bảo đảm cache key và dữ liệu cache được phân biệt theo tài khoản hoặc tenant.
- Chỉ unregister service worker khi thực sự muốn gỡ cơ chế worker của ứng dụng. Unregister worker không tự động thay thế việc xóa các cache mà ứng dụng đã tạo.

`Cache-Control: no-store` trên response nhạy cảm giúp kiểm soát HTTP cache, nhưng không ngăn mã service worker chủ động gọi `cache.put()` để lưu response. Chính sách Cache API phải được kiểm soát trong code của service worker.

## 7. Phối hợp logout giữa máy chủ và nhiều tab

Một quy trình logout đáng tin cậy cần kết thúc phiên ở máy chủ trước hoặc đồng thời với cleanup cục bộ. Máy chủ cần thu hồi session hoặc refresh token theo thiết kế xác thực, sau đó gửi cookie hết hạn. Ví dụ với cookie host-only có tiền tố `__Host-`:

```http
Set-Cookie: __Host-session=; Max-Age=0; Path=/; Secure; HttpOnly; SameSite=Lax
```

Response phải dùng đúng tên, domain và path của cookie cần xóa. Với cookie `__Host-`, `Secure` và `Path=/` là các yêu cầu của tiền tố và không được đặt `Domain`. Nếu ứng dụng đang dùng cookie với thuộc tính khác, máy chủ phải gửi cookie hết hạn khớp phạm vi cookie cũ. JavaScript không thể đọc hoặc xóa cookie `HttpOnly`.

Một luồng logout phía client có thể gọi endpoint đã được bảo vệ bằng cơ chế chống CSRF, rồi dọn các vùng do ứng dụng sở hữu:

```js
async function logout() {
  const response = await fetch("/api/logout", {
    method: "POST",
    credentials: "same-origin",
    headers: {
      "X-CSRF-Token": getCsrfToken()
    }
  });

  if (!response.ok) {
    throw new Error("The server did not confirm logout.");
  }

  notifyOtherTabsOfLogout();
  const storageFailures = clearAccountWebStorage();
  const cacheFailures = await clearAccountCaches();
  const databaseFailures = [];
  try {
    await clearAccountDatabase();
  } catch (error) {
    databaseFailures.push(error);
  }

  resetInMemoryAccountState();

  if (storageFailures.length || cacheFailures.length || databaseFailures.length) {
    reportCleanupFailure({ storageFailures, cacheFailures, databaseFailures });
  }

  window.location.replace("/login");
}
```

Đây là khung tích hợp; `getCsrfToken()`, `notifyOtherTabsOfLogout()`, `resetInMemoryAccountState()` và `reportCleanupFailure()` cần được triển khai theo ứng dụng. Nếu cleanup IndexedDB thất bại hoặc bị block, hệ thống cần hiển thị/truy vết trạng thái đó. Các route và API riêng tư vẫn phải kiểm tra session ở máy chủ, kể cả khi cleanup phía client chưa hoàn tất.

Có thể dùng `BroadcastChannel` để báo các tab cùng origin khi logout:

```js
const authChannel = new BroadcastChannel("portal-auth");

authChannel.addEventListener("message", ({ data }) => {
  if (data?.type !== "logout") return;

  closeAccountDatabaseConnections();
  resetInMemoryAccountState();
  window.location.replace("/login");
});

function notifyOtherTabsOfLogout() {
  authChannel.postMessage({ type: "logout" });
}
```

Các tab nhận thông điệp cần đóng kết nối IndexedDB, hủy request hoặc tác vụ đồng bộ liên quan đến tài khoản cũ, xóa state đang hiển thị và điều hướng đến trang đăng nhập. Với trình duyệt không hỗ trợ `BroadcastChannel`, có thể dùng sự kiện `storage` làm phương án dự phòng. Dù dùng cơ chế nào, đây chỉ là đồng bộ giao diện giữa các tab; máy chủ vẫn là nơi quyết định request có được phép hay không.

Đối với trang chứa dữ liệu nhạy cảm, hãy cấu hình cache header phù hợp, thường là `Cache-Control: no-store`, và kiểm tra lại trạng thái xác thực khi điều hướng hoặc khôi phục trang từ back-forward cache. Việc xóa local state không bảo đảm nội dung đã render biến mất khỏi mọi bản chụp, log hoặc bộ nhớ của trình duyệt.

## 8. Khi nào dùng Clear-Site-Data

Trên HTTPS, `Clear-Site-Data` là HTTP response header cho phép máy chủ yêu cầu trình duyệt xóa một số nhóm dữ liệu gắn với site/origin. Ví dụ:

```http
Clear-Site-Data: "cache", "cookies", "storage"
```

Đây là biện pháp reset phạm vi rộng, hữu ích trong một số luồng logout hoặc khi cần loại bỏ dữ liệu cũ sau sự cố. Tác động cụ thể phụ thuộc directive và mức hỗ trợ của trình duyệt. Directive `cookies` có thể ảnh hưởng các cookie ngoài cookie của riêng module; directive `storage` có thể xóa nhiều loại dữ liệu phía client; directive `cache` tác động đến cache do trình duyệt quản lý. Header này không phải công cụ chọn từng key hoặc từng record.

Chỉ dùng khi phạm vi site có thể được phép reset rộng. Nếu nhiều ứng dụng không liên quan dùng chung domain hoặc origin, thao tác này có thể làm người dùng bị đăng xuất khỏi ứng dụng khác hoặc mất dữ liệu cần giữ. Hãy kiểm thử trên các trình duyệt mục tiêu và không xem header là bằng chứng rằng dữ liệu trên máy chủ đã bị xóa.

## 9. Dọn dữ liệu hết hạn và giới hạn lưu giữ

Không nên đợi đến lúc logout mới dọn mọi dữ liệu. Với dữ liệu offline hoặc bản nháp, hãy định nghĩa thời hạn lưu giữ ngay khi tạo record. Ví dụ record có thể chứa `createdAt`, `updatedAt` và `expiresAt`; ứng dụng kiểm tra `expiresAt` trước khi hiển thị hoặc đồng bộ, sau đó chạy tác vụ dọn theo batch.

Khi dung lượng lưu trữ gần giới hạn, `navigator.storage.estimate()` có thể cung cấp ước lượng dung lượng đã dùng và quota. `navigator.storage.persist()` có thể yêu cầu trình duyệt giảm khả năng tự động eviction trong một số trường hợp. Hai API này không phải API cleanup: persistence không miễn trừ ứng dụng khỏi chính sách retention, và eviction do trình duyệt quyết định không thay thế việc xóa dữ liệu theo yêu cầu của ứng dụng.

Việc trình duyệt eviction dữ liệu do áp lực dung lượng cũng không phải cơ chế bảo đảm xóa an toàn. Ứng dụng không thể dựa vào eviction để kết thúc session, thu hồi quyền hoặc đáp ứng yêu cầu xóa dữ liệu. Nếu dữ liệu được lưu trong OPFS hoặc một vùng lưu trữ riêng khác, hãy bổ sung vùng đó vào danh mục cleanup và dùng API tương ứng để xóa các entry do ứng dụng sở hữu.

## 10. Kiểm chứng bằng DevTools

Hãy kiểm tra cả dữ liệu được lưu và hành vi thực tế của ứng dụng. Một quy trình kiểm thử có thể thực hiện như sau:

1. Đăng nhập bằng tài khoản A, tạo một bản nháp hoặc dữ liệu thử có thể nhận biết rõ.
2. Mở cùng ứng dụng ở hai tab. Kiểm tra dữ liệu trong Application/Storage: Cookies, Local Storage, Session Storage, IndexedDB và Cache Storage.
3. Logout ở tab thứ nhất. Kiểm tra response của `/api/logout`, cookie hết hạn và request tiếp theo đến API riêng tư bị từ chối khi dùng session cũ.
4. Kiểm tra tab thứ hai đã nhận thông báo logout, đóng kết nối cần thiết và không còn hiển thị dữ liệu của A.
5. Mở lại ứng dụng và đăng nhập bằng tài khoản B. Xác nhận hồ sơ, bản nháp, cache API và dữ liệu offline của A không xuất hiện.
6. Thử lại khi một tab vẫn giữ kết nối IndexedDB để xác nhận giao diện xử lý `blocked` và chỉ báo hoàn tất sau khi request xóa thành công.
7. Kiểm tra service worker và Cache Storage sau khi reload hoặc chuyển offline để bảo đảm worker không ghi lại dữ liệu riêng tư đã dọn.

Trong DevTools, mục Application thường cho phép xem và xóa thủ công storage của site. Đây là công cụ chẩn đoán hữu ích, nhưng thao tác xóa thủ công không chứng minh quy trình logout của ứng dụng hoạt động đúng. Hãy kiểm thử bằng luồng người dùng thực tế và quan sát cả Network lẫn Storage.

## 11. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Dùng `localStorage.clear()` cho logout | Xóa cả key thuộc module hoặc ứng dụng khác cùng origin. | Duy trì danh sách key và xóa theo namespace. |
| Gán `document.cookie` để xóa mọi cookie | Không xóa được cookie `HttpOnly`; cookie có domain/path khác vẫn tồn tại. | Máy chủ gửi `Set-Cookie` hết hạn với phạm vi khớp cookie gốc. |
| Xem `sessionStorage` là dữ liệu chỉ có trong một phiên đăng nhập | Tab khác có thể còn state và dữ liệu cũ. | Đồng bộ logout đa tab và xác thực lại ở máy chủ. |
| Gọi `deleteDatabase()` rồi điều hướng ngay | Database có thể đang bị block hoặc gặp lỗi. | Chờ `onsuccess`, xử lý `onblocked` và đóng kết nối ở tab/worker khác. |
| Xóa Cache API nhưng không cập nhật service worker | Worker có thể tiếp tục phục vụ hoặc ghi lại response riêng tư. | Thiết kế allowlist cache, thông điệp logout và kiểm thử offline. |
| Chỉ xóa dữ liệu client | Session máy chủ vẫn có thể còn hiệu lực hoặc dữ liệu vẫn tồn tại ở backend. | Thu hồi session ở máy chủ và thực hiện quy trình xóa dữ liệu ở backend khi cần. |
| Coi eviction hoặc `persist()` là cleanup | Dữ liệu có thể còn lại hoặc bị xóa theo quyết định của trình duyệt. | Thực hiện retention và xóa chủ động theo vòng đời dữ liệu. |

Cuối cùng, cleanup trong trình duyệt là thao tác quản lý dữ liệu ứng dụng, không phải cam kết xóa an toàn theo nghĩa pháp chứng. Ứng dụng không kiểm soát được mọi bản sao trong RAM, ảnh chụp màn hình, file người dùng tải xuống, extension, log mạng, hệ thống đồng bộ hoặc bản sao lưu phía máy chủ. Cách giảm rủi ro hiệu quả nhất là không lưu dữ liệu nhạy cảm không cần thiết, giới hạn thời gian lưu, kiểm tra quyền ở máy chủ và xóa các bản sao mà ứng dụng thực sự quản lý khi vòng đời dữ liệu kết thúc.
