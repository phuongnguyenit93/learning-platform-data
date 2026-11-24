# Storage quota: giới hạn lưu trữ, eviction và xóa dữ liệu theo site

## 1. Storage quota là gì?

Browser cho phép website lưu dữ liệu ở nhiều nơi: IndexedDB, Cache API, Origin Private File System (OPFS), Web Storage và cookie. Dữ liệu có thể phục vụ offline, lưu bản nháp, cache tài nguyên, đồng bộ công việc hoặc giữ trạng thái giao diện.

Tuy nhiên, dung lượng thiết bị có giới hạn. Browser cần quyết định mỗi origin được dùng bao nhiêu bộ nhớ, khi nào từ chối ghi thêm và dữ liệu nào có thể bị xóa khi thiết bị thiếu dung lượng. Cơ chế giới hạn này được gọi chung là **storage quota**.

Quota không phải một con số cố định áp dụng cho mọi browser. Hạn mức phụ thuộc browser, hệ điều hành, dung lượng còn trống, chế độ riêng tư, loại storage, trạng thái cài đặt ứng dụng và chính sách quản lý dữ liệu của browser. Ứng dụng phải kiểm tra dung lượng gần đúng, xử lý lỗi hết quota và có chiến lược dọn dữ liệu.

Bài học thuộc chương **Storage** của module **SECURITY_APPLICATION_SECURITY_BROWSER_SECURITY**. Module phân tích ranh giới bảo mật giữa browser, origin, cookie và ứng dụng web, đồng thời thực hành Same-Origin Policy, CORS, XSS, CSRF, CSP, Trusted Types và security headers. Bài này tập trung vào quota và eviction, tương tác giữa cookie với các kho lưu trữ, Clear-Site-Data và cách xóa dữ liệu theo site khi logout hoặc xử lý quyền riêng tư.

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích storage quota, usage và eviction trong browser.
2. Dùng StorageManager.estimate(), persist() và persisted() khi browser hỗ trợ.
3. Phân biệt best-effort storage với persistent storage.
4. Nhận diện QuotaExceededError và thiết kế xử lý khi ghi dữ liệu thất bại.
5. Phân biệt cookie với localStorage, sessionStorage, IndexedDB, Cache Storage và OPFS.
6. Hiểu vì sao cookie không nên được xem là một phần của quota Web Storage.
7. Giải thích phạm vi dữ liệu theo origin, browsing context và storage partitioning.
8. Dùng Clear-Site-Data để yêu cầu browser xóa cache, cookie hoặc storage theo directive.
9. Phân biệt xóa dữ liệu phía browser với thu hồi session/token phía server.
10. Hướng dẫn người dùng xóa site data thủ công và kiểm chứng bằng DevTools.
11. Lập kế hoạch retention, cleanup, logout và phục hồi dữ liệu an toàn.

## 2. Browser lưu dữ liệu ở đâu?

Mỗi API lưu trữ có mô hình, vòng đời và giới hạn riêng. Không nên gom mọi thứ thành một “database của website”.

| Cơ chế | Dữ liệu thường lưu | Đặc điểm |
| --- | --- | --- |
| Cookies | Session identifier, preference nhỏ, metadata request | Browser có thể tự gửi cookie theo request phù hợp; có giới hạn kích thước và số lượng riêng. |
| localStorage | Cặp key/value dạng string | Đồng bộ, tồn tại qua lần mở trang, giới hạn riêng theo browser. |
| sessionStorage | Cặp key/value dạng string | Gắn với origin và page session/browsing context; thường mất khi session tab kết thúc. |
| IndexedDB | Object store, record, blob, dữ liệu ứng dụng | Bất đồng bộ, phù hợp dữ liệu có cấu trúc và dung lượng lớn hơn Web Storage. |
| Cache Storage | Request/Response cache | Thường dùng với service worker và offline support. |
| OPFS | File riêng của origin | Lưu file/byte dữ liệu lớn trong Origin Private File System. |
| HTTP cache | Response tài nguyên theo HTTP caching rules | Browser quản lý theo cache headers và chính sách riêng. |

Các kho này không có cùng quota hoặc cùng cách eviction. Browser có thể dùng một quota manager chung cho một số loại storage, nhưng cách tính và giới hạn chi tiết là implementation-specific.

### 2.1. Cookie không phải Web Storage

Cookie là cơ chế HTTP state có quy tắc riêng. Browser có thể tự đính kèm cookie vào request dựa trên domain, path, Secure, SameSite và các điều kiện khác.

Web Storage và IndexedDB được JavaScript đọc/ghi theo API riêng. Cookie có thể được đọc qua document.cookie nếu không có HttpOnly; cookie HttpOnly không hiển thị cho JavaScript.

Không dùng cookie để lưu lượng lớn hoặc cache dữ liệu ứng dụng. Cookie được gửi kèm request phù hợp, làm tăng request size và có thể tạo rủi ro lộ dữ liệu nếu cấu hình sai.

### 2.2. Storage quota không phải giới hạn duy nhất của mọi API

localStorage có giới hạn riêng và thao tác đồng bộ. Cookie bị giới hạn theo kích thước từng cookie, số lượng và chính sách browser. IndexedDB, Cache Storage và OPFS thường chịu quota manager của browser.

Vì vậy, StorageManager.estimate() không phải công cụ dự báo chính xác số byte có thể ghi cho mọi API. Cần kiểm tra quota của browser mục tiêu và xử lý lỗi ngay tại API thực hiện ghi.

## 3. Origin và phạm vi lưu trữ

Nhiều kho lưu trữ web được phân tách theo origin. Origin gồm scheme, host và port.

Ví dụ:

~~~text
https://app.example.test
https://admin.example.test
http://app.example.test
https://app.example.test:8443
~~~

Các địa chỉ trên là origin khác nhau. Dữ liệu localStorage hoặc IndexedDB của một origin không tự động được chia sẻ với origin khác.

### 3.1. Same-origin không có nghĩa cùng site

Origin và site là hai khái niệm khác nhau. Cookie SameSite dựa trên khái niệm site; localStorage và IndexedDB thường được gắn với origin. Hai subdomain có thể cùng site nhưng khác origin.

Không suy luận rằng cookie và IndexedDB có cùng phạm vi chỉ vì chúng cùng nằm dưới một domain cha.

### 3.2. Storage partitioning

Browser hiện đại có thể phân vùng một số trạng thái theo top-level site để giảm tracking cross-site. Khi đó, cùng một origin nhúng trong hai website top-level khác nhau có thể nhận storage partition khác nhau.

Phạm vi cụ thể tùy browser và API. Không giả định iframe bên thứ ba luôn nhìn thấy cùng localStorage, cookie hoặc cache như khi mở origin đó ở tab top-level.

### 3.3. Origin không phải ranh giới tài khoản

Hai người dùng đăng nhập cùng một origin có thể dùng chung localStorage/IndexedDB của origin đó trên cùng browser profile. Ứng dụng phải tự phân tách dữ liệu theo user/tenant và xóa hoặc thay đổi namespace khi đăng xuất/đổi tài khoản.

Không dựa vào origin để cô lập dữ liệu giữa các tài khoản dùng chung thiết bị.

## 4. StorageManager API

StorageManager được truy cập qua:

~~~js
navigator.storage
~~~

Các phương thức quan trọng:

| API | Vai trò |
| --- | --- |
| estimate() | Ước lượng usage và quota. |
| persist() | Yêu cầu browser cấp persistent storage cho origin. |
| persisted() | Kiểm tra origin hiện đang có persistent storage hay không. |

Không phải browser nào cũng hỗ trợ đầy đủ. Dùng feature detection và xử lý lỗi.

~~~js
if (navigator.storage) {
  console.log("StorageManager được hỗ trợ");
} else {
  console.log("Browser không hỗ trợ StorageManager");
}
~~~

StorageManager không cung cấp quyền tùy ý tăng dung lượng. Browser vẫn kiểm soát quota và quyết định dựa trên thiết bị/chính sách.

## 5. Đọc usage và quota bằng estimate()

API:

~~~js
const estimate = await navigator.storage.estimate();

console.log({
  usage: estimate.usage,
  quota: estimate.quota,
  usageDetails: estimate.usageDetails
});
~~~

Các trường phổ biến:

- usage: ước lượng số byte đang được dùng trong storage scope mà browser báo cáo.
- quota: ước lượng hạn mức tối đa hiện tại.
- usageDetails: thông tin chi tiết theo loại storage nếu browser cung cấp.

Giá trị là ước lượng, không phải cam kết. Browser có thể làm tròn hoặc giảm độ chính xác để hạn chế fingerprinting. usageDetails có thể không tồn tại hoặc có cấu trúc khác giữa browser.

### 5.1. Tính phần dung lượng còn lại gần đúng

~~~js
async function getStorageCapacity() {
  if (!navigator.storage?.estimate) {
    return null;
  }

  const { usage = 0, quota = 0 } =
    await navigator.storage.estimate();

  return {
    usage,
    quota,
    remaining: Math.max(0, quota - usage),
    usageRatio: quota > 0 ? usage / quota : null
  };
}
~~~

remaining chỉ là phép trừ từ estimate tại thời điểm gọi. Trong lúc ứng dụng chạy, tab khác hoặc worker có thể ghi dữ liệu, browser có thể thay quota và các API có thể có giới hạn riêng. Không dùng con số này như một bảo đảm rằng lần ghi tiếp theo sẽ thành công.

### 5.2. Hiển thị dung lượng cho người dùng

Nếu ứng dụng cho phép tải file offline, có thể hiển thị mức sử dụng gần đúng để người dùng quản lý dữ liệu. Tránh hiển thị quota như một hạn mức cố định của browser hoặc hứa rằng người dùng còn chính xác từng byte.

Nếu estimate không khả dụng, giao diện nên ẩn thông tin chi tiết hoặc chỉ hiển thị trạng thái lưu trữ tổng quát.

## 6. Quota khác nhau giữa browser và thiết bị

Không có một con số quota phổ quát cho mọi origin. Browser có thể tính theo:

- Dung lượng thiết bị còn trống.
- Tổng dung lượng đĩa mà browser được phép dùng.
- Kích thước profile hoặc storage partition.
- Loại storage API.
- Chế độ private/incognito.
- Mức độ người dùng tương tác hoặc cài đặt ứng dụng.
- Chính sách của browser, hệ điều hành hoặc quản trị viên.

Một website có thể lưu được nhiều dữ liệu trên desktop nhưng ít hơn trên mobile. Cùng browser nhưng thiết bị gần đầy bộ nhớ có thể có quota khác.

Không hard-code “mọi browser đều cho 5 GB” hoặc một giá trị tương tự. Hãy dùng estimate nếu có và xử lý QuotaExceededError.

### 6.1. Estimate không phải phép đo chính xác

Browser có thể làm tròn usage/quota, bỏ một số loại storage khỏi usageDetails hoặc tính theo partition. Kết quả chỉ phục vụ lập kế hoạch và UX. Không dùng nó để chứng minh dữ liệu đã được lưu đầy đủ hoặc để quyết định quyền truy cập.

### 6.2. Private browsing

Trong private/incognito mode, storage có thể bị giới hạn, nằm trong vùng tạm thời hoặc bị xóa khi phiên riêng tư kết thúc. Persistent storage có thể không được cấp hoặc không hoạt động giống profile thông thường.

Không giả định dữ liệu offline sẽ tồn tại sau khi người dùng đóng cửa sổ private. Với dữ liệu quan trọng, cần đồng bộ server và thông báo rõ trạng thái lưu cục bộ.

## 7. Best-effort storage và eviction

Mặc định, phần lớn web storage hoạt động theo mô hình **best-effort**. Browser cố gắng giữ dữ liệu nhưng có thể xóa khi thiếu dung lượng hoặc theo chính sách quản lý storage.

Eviction là quá trình browser thu hồi dữ liệu lưu trữ để giải phóng bộ nhớ. Browser có thể xóa dữ liệu của một origin hoặc storage bucket theo chính sách riêng.

Các yếu tố có thể ảnh hưởng:

- Storage pressure trên thiết bị.
- Origin ít được sử dụng gần đây.
- Chế độ private hoặc dữ liệu tạm.
- Quy tắc eviction của browser.
- Storage partition hoặc bucket cụ thể.

Không dựa vào một thuật toán eviction cụ thể nếu browser không cam kết. Ứng dụng cần sẵn sàng cho trường hợp cache hoặc dữ liệu local biến mất.

### 7.1. Cache có thể bị xóa trước dữ liệu quan trọng

Dữ liệu trong Cache Storage thường có thể tái tạo từ server. Nếu cache bị eviction, ứng dụng nên tải lại tài nguyên khi có mạng.

IndexedDB có thể chứa dữ liệu offline do người dùng tạo. Nếu dữ liệu này không thể tái tạo, cần cân nhắc đồng bộ server, export/backup và persistent storage.

Phân loại dữ liệu theo khả năng tái tạo giúp quyết định cái gì có thể dọn trước.

### 7.2. Eviction không phải logout

Browser xóa storage vì quota không đồng nghĩa server đã thu hồi session. Cookie có thể còn tồn tại trong khi IndexedDB bị xóa, hoặc ngược lại. Ứng dụng phải xử lý trạng thái không đồng bộ giữa các kho.

Không giả định người dùng đã đăng xuất chỉ vì cache mất hoặc IndexedDB trống.

## 8. Yêu cầu persistent storage bằng persist()

Ứng dụng có thể yêu cầu browser đánh dấu storage của origin là persistent:

~~~js
const granted = await navigator.storage.persist();
console.log("Persistent storage:", granted);
~~~

Nếu trả true, browser cho biết storage đã được cấp chế độ persistent theo cơ chế hỗ trợ. Điều này giúp giảm nguy cơ browser tự động eviction dữ liệu trong điều kiện storage pressure.

Tuy nhiên, persistent không có nghĩa dữ liệu bất tử. Người dùng vẫn có thể xóa site data, gỡ ứng dụng/profile, reset browser hoặc thiết bị. Browser và hệ điều hành vẫn có quyền quản lý storage trong các trường hợp đặc biệt.

### 8.1. Browser quyết định có cấp hay không

persist() không phải hộp thoại bắt buộc và không bảo đảm luôn trả true. Browser có thể dựa trên engagement, cài đặt PWA, bookmark, mức độ sử dụng hoặc heuristic khác.

Không gọi persist() lặp đi lặp lại để ép browser cấp quyền. Chỉ yêu cầu khi ứng dụng có lý do rõ ràng, chẳng hạn dữ liệu offline do người dùng tạo và khó khôi phục.

### 8.2. Kiểm tra trạng thái persistent

~~~js
const isPersistent = await navigator.storage.persisted();
console.log(isPersistent);
~~~

persisted() trả lời origin hiện có persistent storage hay không. Nó không kiểm tra từng record có còn nguyên, có được đồng bộ server hay có thể đọc được hay không.

### 8.3. Persistent storage vẫn có thể bị người dùng xóa

Người dùng chủ động chọn “Clear site data” hoặc xóa dữ liệu website trong browser settings vẫn có thể xóa dữ liệu persistent. Đây là quyền kiểm soát dữ liệu của người dùng; ứng dụng không được cố chống lại thao tác xóa.

## 9. Ghi dữ liệu và xử lý QuotaExceededError

Không nên chỉ kiểm tra estimate rồi giả định lần ghi sẽ thành công. Quota có thể thay đổi giữa lúc đo và lúc ghi; API cũng có thể áp dụng giới hạn riêng.

Ví dụ IndexedDB write:

~~~js
function saveRecord(store, record) {
  return new Promise((resolve, reject) => {
    const request = store.put(record);

    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

try {
  await saveRecord(store, largeRecord);
} catch (error) {
  if (error?.name === "QuotaExceededError") {
    // Dọn cache có thể tái tạo, sau đó cho người dùng thử lại.
  } else {
    throw error;
  }
}
~~~

Trong IndexedDB, lỗi có thể xuất hiện ở request hoặc transaction. Cần lắng nghe transaction.onerror/abort và bảo đảm rollback/cleanup đúng cách; ví dụ trên chỉ minh họa cách phân loại lỗi tại request.

### 9.1. Chiến lược khi hết quota

Một chiến lược thực tế:

1. Xác định dữ liệu nào có thể tái tạo.
2. Xóa cache cũ hoặc bản tải offline đã hết hạn.
3. Giữ dữ liệu người dùng chưa đồng bộ.
4. Thử ghi lại trong transaction mới.
5. Nếu vẫn thất bại, thông báo dung lượng không đủ.
6. Cung cấp lựa chọn xóa dữ liệu offline hoặc giải phóng dung lượng.
7. Đồng bộ dữ liệu quan trọng trước khi xóa.

Không tự động xóa toàn bộ IndexedDB chỉ để ghi được một file mới. Điều đó có thể làm mất bản nháp hoặc công việc chưa đồng bộ.

### 9.2. Không xóa dữ liệu trong transaction đang lỗi

Khi transaction IndexedDB đã abort do quota, không tiếp tục dùng transaction đó để dọn cache hoặc ghi lại. Hoàn tất xử lý transaction, thực hiện cleanup trong transaction mới và retry có giới hạn.

Tránh vòng lặp retry vô hạn; nếu quota vẫn không đủ, dừng và yêu cầu người dùng chọn cách giải phóng dung lượng.

## 10. localStorage và sessionStorage có giới hạn riêng

Web Storage cung cấp key/value dạng string:

~~~js
localStorage.setItem("theme", "dark");
sessionStorage.setItem("draft-step", "2");
~~~

Các API này đồng bộ. Ghi một lượng dữ liệu lớn có thể chặn main thread và làm giao diện chậm.

Quota và giới hạn Web Storage thường được browser quản lý riêng với IndexedDB/Cache/OPFS. Không giả định estimate() phản ánh chính xác khả năng ghi localStorage. Luôn bắt lỗi khi setItem:

~~~js
try {
  localStorage.setItem("preferences", JSON.stringify(preferences));
} catch (error) {
  if (error?.name === "QuotaExceededError") {
    showStorageLimitMessage();
  } else {
    throw error;
  }
}
~~~

### 10.1. Không lưu dữ liệu lớn hoặc secret trong localStorage

localStorage không có HttpOnly; JavaScript cùng origin có thể đọc dữ liệu. Nếu ứng dụng có XSS, script độc có thể lấy token hoặc dữ liệu đã lưu.

Không lưu access token dài hạn, refresh token hoặc session secret trong localStorage chỉ vì nó tiện. Ưu tiên cookie HttpOnly/Secure/SameSite cho session khi phù hợp kiến trúc, kết hợp CSRF defense và kiểm soát XSS.

### 10.2. sessionStorage không phải bộ nhớ bí mật

sessionStorage có vòng đời gắn với page session/browsing context, nhưng JavaScript cùng origin vẫn đọc được. Không dùng nó như vault cho secret chống XSS. Khi tab bị đóng, dữ liệu thường bị loại bỏ, nhưng browser session restore và hành vi implementation có thể ảnh hưởng chi tiết vòng đời.

## 11. IndexedDB, Cache Storage và OPFS

Đây là các API thường dùng cho dữ liệu lớn hơn:

- IndexedDB: record, object store, index, transaction và dữ liệu có cấu trúc.
- Cache Storage: lưu cặp Request/Response, thường phục vụ offline/PWA.
- OPFS: file và byte data riêng cho origin, hữu ích cho xử lý file hoặc dữ liệu lớn.

Các kho này thường chịu quota management của browser. Ứng dụng nên có chiến lược dọn cache và đồng bộ dữ liệu người dùng trước khi quota cạn.

### 11.1. Cache Storage có thể tái tạo

Cache API thường lưu tài nguyên có thể tải lại. Khi dọn cache, cần giữ versioning của service worker và tránh xóa cache đang được worker hiện tại sử dụng nếu ứng dụng cần nó.

Ví dụ liệt kê cache:

~~~js
const cacheNames = await caches.keys();
console.log(cacheNames);
~~~

Xóa một cache theo tên đã biết:

~~~js
await caches.delete("static-assets-v3");
~~~

Không xóa mọi cache một cách mù quáng nếu nhiều ứng dụng cùng origin hoặc service worker dùng cache khác nhau. Thiết kế tên cache có namespace và version.

### 11.2. OPFS và file người dùng

OPFS phù hợp dữ liệu file riêng của origin, nhưng file vẫn chịu quota và có thể bị xóa bởi người dùng hoặc browser policy. Nếu file là nội dung do người dùng tạo, cần có export/sync trước khi dọn.

Không nhầm OPFS với thư mục file tùy ý của hệ điều hành; ứng dụng web chỉ truy cập vùng sandboxed theo API.

## 12. Cookie và quota: hai hệ thống quản lý khác nhau

Cookie có giới hạn riêng và được browser quản lý trong cookie store. StorageManager estimate không phải công cụ để đo dung lượng cookie hoặc dự đoán số cookie còn có thể tạo.

Các thuộc tính quan trọng:

- Domain và Path: xác định request/host/path mà cookie áp dụng.
- Secure: chỉ gửi qua secure transport theo quy tắc cookie.
- HttpOnly: ngăn JavaScript đọc cookie qua document.cookie.
- SameSite: kiểm soát một số ngữ cảnh gửi cookie cross-site.
- Max-Age/Expires: thời hạn lưu cookie.
- Partitioned: cookie partitioned trong browser hỗ trợ, thường được gọi là CHIPS.

### 12.1. Cookie được gửi tự động theo request

Khác localStorage, cookie phù hợp có thể tự động được browser đính kèm vào HTTP request. Điều này khiến cookie hữu ích cho session nhưng cũng tạo rủi ro CSRF nếu request thay đổi trạng thái không được bảo vệ.

Không đặt dữ liệu lớn vào cookie. Mỗi request có thể mang cookie, làm tăng băng thông và giới hạn header.

### 12.2. Xóa cookie cần đúng scope

Để xóa cookie bằng response Set-Cookie, server cần gửi cùng tên và phạm vi Domain/Path phù hợp, đặt Max-Age=0 hoặc Expires trong quá khứ.

Ví dụ cookie host-only:

~~~http
Set-Cookie: session=; Path=/; Max-Age=0; Secure; HttpOnly; SameSite=Lax
~~~

Nếu cookie cũ được tạo với Domain=.example.test hoặc Path khác, response xóa phải khớp scope tương ứng. Cookie host-only và cookie domain-scoped không hoàn toàn giống nhau.

JavaScript document.cookie không thể xóa cookie HttpOnly. Server phải gửi Set-Cookie để hết hạn cookie đó.

### 12.3. Xóa cookie không thu hồi session phía server

Xóa cookie trong browser chỉ loại bỏ credential phía client. Nếu server vẫn chấp nhận session ID cũ, người đã sao chép session ID vẫn có thể sử dụng nó cho tới khi hết hạn hoặc bị thu hồi.

Logout an toàn cần:
- Thu hồi session/token phía server.
- Hết hạn cookie phía client với đúng Domain/Path.
- Xóa token/cache nhạy cảm phía client nếu ứng dụng có lưu.
- Xóa dữ liệu nhạy cảm khỏi IndexedDB/localStorage theo chính sách.
- Xử lý service worker/cache có thể giữ response chứa dữ liệu cá nhân.

## 13. Cookie và Web Storage khi logout hoặc đổi tài khoản

Cookie session, localStorage, IndexedDB và Cache Storage có thể cùng tồn tại trên một origin nhưng có vòng đời khác nhau. Chỉ xóa một kho có thể để lại dữ liệu user cũ.

Ví dụ một ứng dụng lưu:
- Session cookie HttpOnly do server quản lý.
- Preference giao diện trong localStorage.
- Bản nháp trong IndexedDB.
- API response trong Cache Storage.
- File offline trong OPFS.

Khi người dùng đăng xuất hoặc chuyển tài khoản, cần phân loại dữ liệu:

| Dữ liệu | Hành động thường cần |
| --- | --- |
| Server session | Thu hồi ở server. |
| Session cookie | Hết hạn bằng Set-Cookie đúng scope. |
| Access/refresh token phía client | Thu hồi hoặc xóa theo thiết kế xác thực. |
| Cache response chứa dữ liệu cá nhân | Xóa cache tương ứng. |
| IndexedDB record theo user | Xóa hoặc tách namespace và khóa quyền truy cập. |
| Preference không nhạy cảm | Có thể giữ nếu chính sách sản phẩm cho phép. |
| Offline file người dùng | Đồng bộ/export trước khi xóa nếu cần giữ lại. |

Không xóa toàn bộ site data theo mặc định nếu ứng dụng cần giữ preference hoặc dữ liệu offline chưa đồng bộ. Ngược lại, không chỉ xóa cookie rồi để dữ liệu riêng tư của tài khoản trước nằm lại cho người dùng tiếp theo.

## 14. Clear-Site-Data là gì?

**Clear-Site-Data** là HTTP response header cho phép website yêu cầu browser xóa một số loại dữ liệu gắn với origin hoặc site theo directive được hỗ trợ.

Ví dụ:

~~~http
Clear-Site-Data: "cache", "cookies", "storage"
~~~

Header này thường được dùng trong luồng logout, xử lý sự cố hoặc khi cần xóa cache/storage cũ sau một thay đổi bảo mật.

Clear-Site-Data là yêu cầu gửi từ server qua response. Nó không phải JavaScript API để một trang tùy ý xóa dữ liệu của origin khác. Browser chỉ xử lý header trong điều kiện an toàn theo chuẩn, thường yêu cầu response qua HTTPS; không dùng HTTP thường để yêu cầu xóa dữ liệu.

### 14.1. Các directive thường gặp

| Directive | Ý nghĩa khái quát |
| --- | --- |
| "cache" | Yêu cầu xóa HTTP cache liên quan tới origin/site theo browser implementation. |
| "cookies" | Yêu cầu xóa cookie và một số trạng thái xác thực liên quan trong phạm vi được định nghĩa. |
| "storage" | Yêu cầu xóa storage như Web Storage, IndexedDB, Cache Storage và dữ liệu storage được browser hỗ trợ. |
| "executionContexts" | Yêu cầu browser reload các browsing context liên quan tới origin theo hỗ trợ. |
| "clientHints" | Yêu cầu xóa trạng thái Client Hints liên quan nếu browser hỗ trợ. |
| "*" | Yêu cầu xóa tất cả nhóm dữ liệu mà browser hỗ trợ trong cơ chế này. |

Mức hỗ trợ directive khác nhau giữa browser. Kiểm tra compatibility của browser mục tiêu và không giả định mọi loại dữ liệu trên mọi thiết bị đều được xóa giống nhau.

### 14.2. "cookies" có phạm vi rộng hơn một cookie session

Directive "cookies" có thể ảnh hưởng cookie của origin và phạm vi domain liên quan, gồm một số subdomain theo quy tắc của Clear-Site-Data. Nó có thể đăng xuất người dùng khỏi các ứng dụng khác dùng cookie domain chung.

Không dùng "cookies" nếu chỉ muốn xóa một cookie riêng lẻ; hãy gửi Set-Cookie hết hạn đúng tên/domain/path. Clear-Site-Data phù hợp hơn khi chủ đích là dọn dữ liệu trên diện rộng cho site.

### 14.3. "storage" không đồng nghĩa xóa cookie

Cookie và storage là các nhóm directive riêng. Nếu response chỉ có:

~~~http
Clear-Site-Data: "storage"
~~~

thì không nên giả định cookie session cũng bị xóa. Nếu cần xóa cả hai, khai báo rõ:

~~~http
Clear-Site-Data: "cookies", "storage"
~~~

Và nếu cần xóa HTTP cache, thêm "cache". Hãy kiểm tra browser support và kết quả thực tế.

### 14.4. Cẩn trọng với wildcard

~~~http
Clear-Site-Data: "*"
~~~

có thể xóa nhiều loại dữ liệu mà browser hỗ trợ, gây mất cache, đăng nhập và dữ liệu local. Chỉ dùng khi chủ đích thực sự là reset toàn bộ site data và đã đánh giá tác động tới các ứng dụng cùng domain.

Ưu tiên liệt kê directive cụ thể để reviewer thấy rõ dữ liệu nào sẽ bị yêu cầu xóa.

## 15. Clear-Site-Data trong luồng logout

Một response logout có thể gửi:

~~~http
HTTP/1.1 200 OK
Clear-Site-Data: "cache", "cookies", "storage"
Content-Type: application/json
~~~

Tuy nhiên, header chỉ là một phần của logout. Server vẫn phải thu hồi session/token trước hoặc trong cùng transaction nghiệp vụ. Nếu chỉ gửi Clear-Site-Data mà server còn chấp nhận session ID cũ, credential đã bị sao chép vẫn có thể được sử dụng.

Một luồng logout tổng quát:

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant B as Browser
    participant S as Server
    U->>B: Chọn Đăng xuất
    B->>S: POST /logout (cookie + CSRF token)
    S->>S: Thu hồi session phía server
    S-->>B: Response + Set-Cookie hết hạn + Clear-Site-Data
    B->>B: Xóa dữ liệu theo directive được hỗ trợ
    B-->>U: Hiển thị trạng thái đã đăng xuất
~~~

Request logout thay đổi trạng thái nên cần CSRF defense phù hợp. Không dùng GET endpoint để logout chỉ vì muốn browser tự tải URL.

### 15.1. Có nên thêm "executionContexts"?

Nếu response gửi:

~~~http
Clear-Site-Data: "executionContexts"
~~~

browser hỗ trợ có thể reload các browsing context liên quan. Điều này có thể giúp các tab khác nhận trạng thái logout hoặc tải lại ứng dụng sau khi dữ liệu bị xóa.

Tuy nhiên, reload có thể làm gián đoạn biểu mẫu hoặc công việc đang diễn ra. Hãy kiểm tra hỗ trợ, cảnh báo người dùng khi phù hợp và phối hợp BroadcastChannel/storage event/server session invalidation nếu cần đồng bộ tab. Không thêm directive này một cách máy móc.

### 15.2. Không phải cơ chế logout đa thiết bị

Clear-Site-Data chỉ tác động dữ liệu browser trong phạm vi mà response và browser xử lý. Nó không xóa cookie trên điện thoại khác, không xóa storage ở browser profile khác và không thu hồi session ở các thiết bị khác. Backend cần quản lý session theo user/device và hỗ trợ revoke riêng.

## 16. Clear-Site-Data và cache

Directive "cache" yêu cầu xóa HTTP cache theo phạm vi được browser hỗ trợ. Đây không phải lệnh đảm bảo xóa mọi cache do ứng dụng tự tạo ở mọi storage API.

Cache Storage thường thuộc nhóm storage. Nếu cần dọn service worker cache, xem xét directive "storage" hoặc cleanup logic cụ thể trong service worker.

Không nhầm:
- HTTP cache: browser quản lý response theo HTTP caching.
- Cache Storage: JavaScript/service worker lưu Request/Response qua Cache API.
- Memory cache: cache runtime do browser quản lý, vòng đời khác.
- CDN/proxy cache: cache ngoài browser, phải purge ở hạ tầng tương ứng.

Clear-Site-Data không tự purge CDN cache hoặc reverse proxy cache trên server.

## 17. Xóa dữ liệu site thủ công trong browser

Người dùng có thể xóa site data trong cài đặt browser. Tên menu thay đổi theo browser/version nhưng thường nằm trong Privacy, Site settings, Cookies and site data hoặc Clear browsing data.

Với Chrome/Chromium, có thể mở thông tin site từ thanh địa chỉ hoặc vào Site settings để xóa dữ liệu của site. Trong DevTools, Application → Storage có thể hiển thị loại dữ liệu origin sử dụng và nút Clear site data.

Thao tác này thường xóa nhiều loại dữ liệu liên quan tới site như cookie, local storage, IndexedDB, Cache Storage và service worker registrations tùy browser. Nó có thể khiến người dùng bị đăng xuất hoặc mất dữ liệu offline chưa đồng bộ.

### 17.1. Clear site data trong DevTools

Quy trình kiểm tra trong môi trường development:

1. Mở trang của origin cần kiểm tra.
2. Mở DevTools.
3. Chọn Application.
4. Mở Storage hoặc Clear storage tùy phiên bản.
5. Xem các nhóm dữ liệu được chọn.
6. Thực hiện Clear site data.
7. Reload trang và xác minh trạng thái storage/service worker.

Không thực hiện trên profile chứa dữ liệu quan trọng nếu chưa hiểu phạm vi xóa. Đây là thao tác xóa dữ liệu thật của origin trong browser profile hiện tại.

### 17.2. Xóa một nhóm dữ liệu có chọn lọc

Nếu mục tiêu chỉ là xóa cache ứng dụng, dùng Cache API hoặc công cụ browser tương ứng. Nếu chỉ muốn xóa một preference, xóa key localStorage tương ứng. Nếu muốn xóa một record, dùng transaction IndexedDB.

Không yêu cầu người dùng xóa toàn bộ site data để sửa một lỗi cache nhỏ nếu có thể xử lý có chọn lọc.

## 18. Clear-Site-Data không phải API quản lý dữ liệu server

Clear-Site-Data không:
- Xóa record trong database server.
- Thu hồi access token đã bị sao chép ở nơi khác.
- Xóa dữ liệu từ thiết bị hoặc browser khác.
- Xóa CDN/reverse proxy cache ở hạ tầng ngoài browser.
- Bảo đảm xóa file mà người dùng đã tải về.
- Thay thế server-side logout hoặc revoke token.
- Xóa dữ liệu của origin khác mà website không kiểm soát.

Nếu cần xóa tài khoản hoặc dữ liệu server theo yêu cầu quyền riêng tư, phải thực hiện workflow phía server và quy trình dữ liệu riêng. Clear-Site-Data chỉ là một phần dọn trạng thái client.

## 19. Storage và Service Worker

Service worker có thể giữ Cache Storage và tiếp tục phục vụ tài nguyên offline. Khi xóa site data, service worker registration và cache liên quan có thể bị xóa theo directive/browser behavior.

Ứng dụng nên có cơ chế version cache:

~~~js
const CACHE_NAME = "app-shell-v4";

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) =>
      cache.addAll(["/", "/offline.html", "/styles/app.css"])
    )
  );
});
~~~

Cleanup cache cũ:

~~~js
self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((names) =>
      Promise.all(
        names
          .filter((name) => name.startsWith("app-shell-") && name !== CACHE_NAME)
          .map((name) => caches.delete(name))
      )
    )
  );
});
~~~

Chỉ xóa cache thuộc namespace của ứng dụng. Tránh xóa cache của ứng dụng khác cùng origin nếu nhiều app share origin.

### 19.1. Service worker có thể giữ code cũ sau deploy

Nếu browser vẫn chạy service worker cũ, ứng dụng có thể tiếp tục tải bundle/config cũ hoặc hiển thị dữ liệu cũ. Khi debug, kiểm tra service worker registration, active/waiting worker và Cache Storage.

Clear site data có thể giải quyết trạng thái local bị hỏng nhưng cũng làm mất dữ liệu offline. Ưu tiên versioning và migration đúng trước khi yêu cầu người dùng xóa toàn bộ dữ liệu.

## 20. Storage quota và bảo vệ quyền riêng tư

Storage có thể chứa dữ liệu nhạy cảm dù nó không tự động gửi trong mỗi request. Nếu nhiều người dùng dùng chung browser profile, dữ liệu còn sót lại có thể bị tài khoản tiếp theo đọc nếu ứng dụng không phân tách đúng.

Các nguyên tắc:

- Không lưu secret dài hạn trong localStorage/sessionStorage nếu có phương án an toàn hơn.
- Phân vùng dữ liệu theo user/tenant và kiểm tra quyền ở server.
- Xóa dữ liệu nhạy cảm khi logout hoặc đổi tài khoản.
- Giữ dữ liệu chưa đồng bộ cho tới khi có phương án backup/export.
- Dùng cache-control phù hợp cho response cá nhân.
- Tránh cache response chứa thông tin nhạy cảm vào Cache Storage nếu không cần offline.
- Xử lý dữ liệu trong service worker và background sync theo cùng policy.
- Thông báo rõ dữ liệu nào được lưu offline và cách người dùng xóa nó.

Quota cao hơn không có nghĩa ứng dụng nên lưu nhiều dữ liệu cá nhân hơn. Chỉ lưu dữ liệu cần thiết và có thời hạn retention rõ.

## 21. Thiết kế cleanup an toàn theo loại dữ liệu

Một hàm cleanup nên nhận mục tiêu cụ thể thay vì xóa mọi thứ:

~~~js
async function clearAppCaches() {
  const names = await caches.keys();

  await Promise.all(
    names
      .filter((name) => name.startsWith("app-cache-"))
      .map((name) => caches.delete(name))
  );
}
~~~

Xóa một số key preference:

~~~js
localStorage.removeItem("temporary-filter");
localStorage.removeItem("last-opened-panel");
~~~

Xóa IndexedDB cần dùng API migration/cleanup phù hợp với database schema. Ví dụ xóa database:

~~~js
const request = indexedDB.deleteDatabase("app-offline-data");

request.onsuccess = () => console.log("Database đã xóa");
request.onerror = () => console.error("Không thể xóa database");
request.onblocked = () => {
  console.warn("Tab khác còn giữ kết nối IndexedDB");
};
~~~

Đóng các kết nối IndexedDB đang mở trước khi xóa database. onblocked có thể xảy ra nếu tab hoặc worker khác vẫn giữ connection. Không xóa database nếu còn dữ liệu người dùng chưa đồng bộ.

### 21.1. Xóa theo namespace/user

Nếu ứng dụng cần giữ preference chung nhưng xóa dữ liệu tài khoản, đặt namespace rõ ràng:

~~~text
app:preferences
app:user:123:offline-records
app:user:123:cache-index
~~~

Khi logout user 123, cleanup namespace tương ứng và thu hồi session. Không tin user ID lưu ở client để cấp quyền; backend phải xác thực lại mọi thao tác.

## 22. Quota và dữ liệu người dùng chưa đồng bộ

Offline-first app cần phân biệt:
- Cache có thể tải lại.
- Dữ liệu đã đồng bộ server.
- Dữ liệu mới tạo chưa đồng bộ.
- File người dùng chỉ tồn tại local.
- Metadata phục vụ đồng bộ.

Khi quota gần đầy, ưu tiên xóa cache tái tạo trước. Với dữ liệu chưa đồng bộ, cung cấp sync/export hoặc cảnh báo trước khi người dùng xóa. Nếu browser eviction xảy ra ngoài dự kiến, ứng dụng cần phát hiện thiếu dữ liệu và phục hồi từ server nếu có.

Không hứa dữ liệu local sẽ tồn tại mãi, kể cả khi persist() trả true.

## 23. Thực hành A — Đo usage/quota

Trên trang HTTPS hoặc localhost do bạn kiểm soát, mở Console:

~~~js
const estimate = await navigator.storage.estimate();

console.table({
  usage: estimate.usage,
  quota: estimate.quota,
  remaining: estimate.quota - estimate.usage
});

console.log(estimate.usageDetails);
~~~

Ghi nhận kết quả trước và sau khi lưu dữ liệu test vào IndexedDB hoặc Cache Storage. Không suy luận cookie quota từ kết quả này.

Nếu StorageManager không hỗ trợ, ghi nhận unsupported và tiếp tục kiểm tra từng API bằng cách thử ghi dữ liệu nhỏ có kiểm soát.

## 24. Thực hành B — Kiểm tra persistent storage

~~~js
if (navigator.storage?.persisted) {
  console.log("Đã persistent:", await navigator.storage.persisted());
}

if (navigator.storage?.persist) {
  const granted = await navigator.storage.persist();
  console.log("Yêu cầu persistent:", granted);
}
~~~

So sánh trạng thái trước/sau và trên browser profile khác. Kết quả phụ thuộc browser policy và không bảo đảm mọi thiết bị sẽ cấp persistent storage.

## 25. Thực hành C — Kiểm tra Clear-Site-Data trong staging

Trên HTTPS staging origin do bạn quản lý, cấu hình response endpoint logout:

~~~http
HTTP/1.1 200 OK
Clear-Site-Data: "cache", "cookies", "storage"
Set-Cookie: session=; Path=/; Max-Age=0; Secure; HttpOnly; SameSite=Lax
Content-Type: application/json
~~~

Trước khi gọi endpoint, lưu dữ liệu test vào localStorage, IndexedDB và Cache Storage. Gọi logout rồi kiểm tra:

- Cookie session đã hết hạn đúng scope chưa?
- localStorage/IndexedDB/Cache Storage có được xóa theo browser support không?
- Service worker registration còn tồn tại không?
- Các tab khác có bị ảnh hưởng không?
- Server session đã bị revoke chưa?

Dùng tài khoản và dữ liệu staging. Không chạy header này trên production nếu chưa đánh giá phạm vi cookie/subdomain và dữ liệu offline.

## 26. Thực hành D — Xóa site data thủ công

Trong browser profile thử nghiệm:

1. Mở origin staging.
2. Tạo dữ liệu test trong localStorage, IndexedDB và Cache Storage.
3. Đăng ký service worker test.
4. Mở DevTools → Application → Storage/Clear storage.
5. Chọn Clear site data.
6. Reload trang.
7. Xác minh dữ liệu nào đã mất và API nào cần đăng ký lại.

Ghi nhận browser/version vì phạm vi và UI có thể khác nhau. Không dùng profile làm việc có dữ liệu quan trọng cho bài lab.

## 27. Checklist review Storage quota và site data

- [ ] Xác định API nào đang lưu dữ liệu: cookie, Web Storage, IndexedDB, Cache Storage, OPFS.
- [ ] Không coi cookie là một phần của StorageManager quota.
- [ ] Dùng navigator.storage.estimate() như số liệu ước lượng, không phải bảo đảm.
- [ ] Kiểm tra navigator.storage.persisted() trước khi hiển thị trạng thái persistent.
- [ ] Chỉ yêu cầu persist() khi dữ liệu thực sự khó tái tạo.
- [ ] Xử lý QuotaExceededError ở từng API/transaction.
- [ ] Dọn cache có thể tái tạo trước dữ liệu người dùng chưa đồng bộ.
- [ ] Không retry ghi vô hạn khi quota cạn.
- [ ] Phân biệt best-effort và persistent storage.
- [ ] Kiểm tra hành vi private browsing và storage partitioning.
- [ ] Không dùng localStorage/sessionStorage làm kho secret chống XSS.
- [ ] Xóa cookie bằng đúng Domain/Path; server xử lý cookie HttpOnly.
- [ ] Thu hồi session/token ở server khi logout.
- [ ] Phân loại dữ liệu cần giữ và dữ liệu cần xóa khi đổi tài khoản.
- [ ] Dùng Clear-Site-Data qua HTTPS và directive cụ thể.
- [ ] Hiểu "cookies" có thể ảnh hưởng cookie domain/subdomain liên quan.
- [ ] Không giả định "storage" tự xóa cookie.
- [ ] Chỉ dùng "*" khi thật sự muốn reset toàn bộ nhóm dữ liệu hỗ trợ.
- [ ] Đánh giá "executionContexts" vì có thể reload tab đang hoạt động.
- [ ] Không nhầm browser HTTP cache với Cache Storage hoặc CDN cache.
- [ ] Kiểm tra service worker và cache version sau deploy.
- [ ] Hướng dẫn người dùng xóa site data thủ công và cảnh báo mất dữ liệu offline.
- [ ] Có sync/export trước khi xóa dữ liệu local chưa đồng bộ.
- [ ] Kiểm thử trên browser/version và thiết bị mục tiêu.

## 28. Những ngộ nhận thường gặp

| Nhận định | Đánh giá | Giải thích |
| --- | --- | --- |
| “Mọi browser đều cấp một quota cố định cho website.” | **Sai** | Quota phụ thuộc browser, thiết bị, storage type và policy. |
| “estimate() cho biết chính xác còn ghi được bao nhiêu byte.” | **Sai** | Đây là ước lượng, có thể làm tròn và thay đổi. |
| “persist() đảm bảo dữ liệu không bao giờ bị xóa.” | **Sai** | Người dùng vẫn có thể xóa site data hoặc reset profile. |
| “Cookie được tính chung với IndexedDB quota.” | **Sai** | Cookie có cookie store và giới hạn riêng. |
| “localStorage phù hợp để lưu file lớn.” | **Sai** | Web Storage đồng bộ và có giới hạn nhỏ hơn các kho phù hợp dữ liệu lớn. |
| “sessionStorage là nơi lưu secret an toàn.” | **Sai** | JavaScript cùng origin vẫn có thể đọc dữ liệu. |
| “Eviction đồng nghĩa user đã logout.” | **Sai** | Cookie/session và các kho storage có vòng đời khác nhau. |
| “Xóa cookie là thu hồi session phía server.” | **Sai** | Server phải revoke session/token riêng. |
| “Clear-Site-Data storage luôn xóa cookie.” | **Sai** | cookies và storage là directive riêng. |
| “Clear-Site-Data chỉ xóa đúng một cookie.” | **Sai** | Directive cookies có phạm vi rộng theo site/domain liên quan. |
| “Clear-Site-Data xóa database và CDN cache trên server.” | **Sai** | Header yêu cầu browser xóa dữ liệu client trong phạm vi hỗ trợ. |
| “Clear-Site-Data '*' luôn an toàn cho logout.” | **Sai** | Có thể xóa cache, dữ liệu offline và trạng thái dùng chung. |
| “Browser không hỗ trợ Clear-Site-Data thì không thể logout.” | **Sai** | Server revoke session và Set-Cookie vẫn là nền tảng; client có thể cleanup bằng API phù hợp. |
| “DevTools Clear site data chỉ xóa cache.” | **Sai** | Nó có thể xóa cookie, storage và service worker tùy lựa chọn/browser. |
| “Dữ liệu của hai user trên cùng origin tự được tách riêng.” | **Sai** | Ứng dụng phải phân vùng dữ liệu theo user/tenant. |
| “Cache Storage, HTTP cache và CDN cache là một.” | **Sai** | Chúng thuộc các lớp quản lý khác nhau. |

## 29. Tổng kết

Storage quota là cơ chế browser quản lý dung lượng và vòng đời dữ liệu mà website lưu. estimate() cung cấp số liệu gần đúng; persist() có thể giảm nguy cơ eviction tự động nhưng không ngăn người dùng xóa dữ liệu. Ứng dụng cần xử lý quota failure, ưu tiên dọn cache tái tạo và bảo vệ dữ liệu chưa đồng bộ.

Cookie có cookie store, phạm vi và giới hạn riêng; chúng không nên bị nhầm với localStorage, IndexedDB hay Cache Storage. Khi logout, phải thu hồi session phía server, hết hạn cookie đúng scope và dọn các kho client theo chính sách dữ liệu.

Clear-Site-Data cho phép server yêu cầu browser xóa các nhóm dữ liệu như cache, cookies và storage. Đây là cơ chế dọn dữ liệu phía client, không thay revoke session hoặc xóa dữ liệu server. Cần chọn directive cụ thể, đánh giá tác động subdomain và kiểm thử browser hỗ trợ trước khi triển khai.

Ba nguyên tắc cần nhớ:

1. **Đo và xử lý quota có dự phòng:** estimate chỉ là ước lượng; bắt QuotaExceededError, dọn cache tái tạo và bảo vệ dữ liệu chưa đồng bộ.
2. **Tách cookie khỏi storage:** cookie được gửi theo HTTP request và có scope riêng; Web Storage/IndexedDB/Cache/OPFS có quota và vòng đời khác. Logout phải xử lý cả client lẫn server.
3. **Xóa dữ liệu theo chủ đích:** Clear-Site-Data và thao tác Clear site data có thể xóa nhiều loại dữ liệu; chọn đúng phạm vi, cảnh báo tác động và không nhầm xóa browser data với thu hồi session.

Khi review storage của một ứng dụng, hãy hỏi: **dữ liệu nằm ở API nào, quota được đo và xử lý ra sao, dữ liệu nào có thể tái tạo, cookie có scope nào, logout đã revoke session chưa, Clear-Site-Data sẽ xóa những gì, và người dùng có thể khôi phục dữ liệu offline chưa đồng bộ không?** Trả lời rõ các câu hỏi này giúp quản lý dung lượng mà vẫn tôn trọng quyền kiểm soát dữ liệu của người dùng.
