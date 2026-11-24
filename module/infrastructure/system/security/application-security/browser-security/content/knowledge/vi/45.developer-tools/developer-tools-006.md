# Browser storage inspection: kiểm tra dữ liệu lưu trong trình duyệt

## Mục tiêu học tập

Sau bài học, người học có thể:

1. Mở đúng công cụ Application hoặc Storage trong DevTools để kiểm tra dữ liệu của website.
2. Phân biệt cookie, localStorage, sessionStorage, IndexedDB, Cache Storage và HTTP cache.
3. Giải thích phạm vi origin, top-level site và storage partitioning của browser.
4. Đọc các thuộc tính cookie như Domain, Path, Secure, HttpOnly, SameSite, Expires và Partitioned.
5. Kiểm tra dữ liệu Web Storage, IndexedDB và Cache Storage mà không vô tình làm lộ credential.
6. Kiểm tra service worker, cache offline và dữ liệu theo từng frame.
7. Hiểu quota, eviction, persistent storage và vòng đời dữ liệu.
8. Dùng Console và Network để đối chiếu dữ liệu lưu với request/response.
9. Đánh giá rủi ro XSS, CSRF, token persistence và dữ liệu nhạy cảm còn sót lại.
10. Xóa storage có chọn lọc, kiểm thử logout và ghi nhận kết quả an toàn.

> **Bối cảnh:** Module Browser Security phân tích ranh giới bảo mật giữa trình duyệt, origin, cookie và ứng dụng web để hiểu Same-Origin Policy, CORS và các cơ chế cách ly; đồng thời thực hành phòng vệ XSS, CSRF, clickjacking bằng CSP, Trusted Types và security headers. Browser storage inspection giúp xác minh dữ liệu thực sự được lưu ở đâu, có phạm vi truy cập nào, tồn tại bao lâu và có thể bị lộ qua script hoặc request hay không.

## 1. Vì sao cần kiểm tra browser storage?

Ứng dụng web thường lưu trạng thái để giữ phiên đăng nhập, tùy chọn giao diện, dữ liệu offline, kết quả API hoặc nội dung người dùng vừa thao tác. Dữ liệu có thể nằm ở nhiều nơi và có vòng đời khác nhau.

Ví dụ một ứng dụng có thể sử dụng:

- Cookie để gửi session identifier trong request.
- localStorage để lưu tùy chọn giao diện.
- sessionStorage để lưu trạng thái của một tab.
- IndexedDB để lưu dữ liệu offline hoặc bản nháp lớn.
- Cache Storage để giữ response do service worker quản lý.
- HTTP cache để tái sử dụng tài nguyên theo cache header.
- Origin Private File System (OPFS) để lưu file riêng cho origin.

Nếu chỉ nhìn cookie, người kiểm thử có thể bỏ sót token trong localStorage, dữ liệu cá nhân trong IndexedDB hoặc response nhạy cảm trong Cache Storage.

### Các câu hỏi cần trả lời khi inspection

1. Dữ liệu được lưu trong loại storage nào?
2. Storage thuộc origin, tab hay top-level site nào?
3. Script nào có thể đọc dữ liệu?
4. Dữ liệu có được gửi tự động trong request không?
5. Dữ liệu tồn tại sau reload, đóng tab, logout hay đóng browser không?
6. Dữ liệu có bị phân vùng trong third-party context không?
7. Khi xóa dữ liệu, service worker và cache có còn giữ bản sao không?
8. Có credential hoặc PII nào đang được lưu lâu hơn mục đích cần thiết không?

## 2. Mở Application hoặc Storage trong DevTools

Trong Chrome và các browser Chromium, khu vực kiểm tra storage thường nằm trong tab **Application** của DevTools. Một số browser hoặc phiên bản có thể dùng tên **Storage** hoặc bố trí khác.

### Mở DevTools

1. Mở website cần kiểm tra trong môi trường được phép.
2. Mở DevTools bằng menu browser hoặc phím tắt tương ứng.
3. Chọn tab Application.
4. Nếu tab không hiển thị, mở menu tab overflow hoặc More tools rồi chọn Application.
5. Trong sidebar, mở từng nhóm Storage, Cookies, IndexedDB, Cache Storage và Service Workers.

### Chọn đúng frame và origin

Một trang có thể chứa iframe từ nhiều origin. Storage của top-level document và storage của iframe có thể khác nhau.

Trước khi đọc dữ liệu:

- Xác định URL và origin của trang đang kiểm tra.
- Xác định frame nào đang sở hữu dữ liệu.
- Kiểm tra top-level site nếu frame là third-party.
- Không giả định mọi mục trong sidebar đều thuộc cùng một origin.
- Đối chiếu origin hiển thị trong DevTools với URL thực tế.

### Giao diện thay đổi theo browser

Tên menu, vị trí nút Clear site data, cách hiển thị cookie partition và IndexedDB có thể khác giữa Chrome, Edge, Firefox và Safari. Hãy dùng khái niệm storage và phạm vi bảo mật làm chuẩn, sau đó đối chiếu UI của browser mục tiêu.

## 3. Origin, site và storage key

Muốn đọc đúng storage, cần phân biệt origin với site.

### Origin

Origin được xác định bởi scheme, host và port:

    https://app.example.test:443

Các URL dưới đây có origin khác nhau:

    https://app.example.test
    http://app.example.test
    https://api.example.test
    https://app.example.test:8443

localStorage và IndexedDB thông thường được phân vùng theo origin. Một origin khác không thể tự đọc storage của origin hiện tại qua JavaScript thông thường.

### Site

Khái niệm site thường dựa trên scheme và registrable domain theo quy tắc browser/public suffix. Site không đồng nghĩa với origin.

Ví dụ:

    https://app.example.test
    https://api.example.test

Hai origin khác nhau nhưng thường cùng site. SameSite cookie và một số cơ chế chống tracking dùng khái niệm site, trong khi localStorage dùng origin.

### Storage key và partitioning

Browser hiện đại có thể phân vùng storage theo storage key, không chỉ origin đơn giản. Trong third-party context, top-level site có thể là một phần của key để ngăn cùng một bên thứ ba chia sẻ state xuyên nhiều website.

Ví dụ một iframe:

    Top-level site A
      └── iframe tracker.example

    Top-level site B
      └── iframe tracker.example

Browser có thể cung cấp hai vùng storage tách biệt cho tracker.example trong hai top-level site khác nhau. Chi tiết phụ thuộc browser, API và chính sách privacy.

### Không suy ra storage access chỉ từ URL

Hai trang có cùng origin nhưng nằm trong context partition khác nhau có thể không nhìn thấy cùng state. Ngược lại, hai subdomain khác nhau không chia sẻ localStorage chỉ vì cùng registrable domain.

Khi kiểm thử, ghi nhận cả origin, top-level site, frame và browser version.

## 4. Cookie trong DevTools

Cookie là dữ liệu browser lưu và có thể gửi kèm request theo Domain, Path, Secure, SameSite, thời hạn và các quy tắc khác.

Trong Chrome DevTools:

1. Mở Application.
2. Mở Storage → Cookies.
3. Chọn đúng origin/host trong danh sách.
4. Xem từng cookie và thuộc tính.
5. Đối chiếu với request trong Network.

Không sao chép cookie value vào báo cáo, ticket hoặc chat. Session cookie thường là credential có thể bị sử dụng nếu bị lộ.

### Các thuộc tính cần kiểm tra

| Thuộc tính | Ý nghĩa | Câu hỏi kiểm tra |
| --- | --- | --- |
| Name | Tên cookie | Tên có tiết lộ dữ liệu nhạy cảm không? |
| Value | Giá trị cookie | Có phải session/token hoặc PII không? |
| Domain | Host hoặc domain áp dụng | Có cần chia sẻ cho subdomain không? |
| Path | Path request được gửi kèm | Phạm vi có rộng hơn nhu cầu không? |
| Expires / Max-Age | Thời điểm hết hạn hoặc tuổi thọ | Cookie tồn tại lâu hơn mục đích không? |
| Secure | Chỉ gửi qua kết nối an toàn theo quy tắc cookie | Cookie xác thực đã bật Secure chưa? |
| HttpOnly | Không cho JavaScript đọc qua document.cookie | Session cookie đã bật HttpOnly chưa? |
| SameSite | Hạn chế gửi cookie trong ngữ cảnh cross-site | Lax, Strict hay None có phù hợp không? |
| Partitioned | Cookie được phân vùng theo top-level site trong mô hình hỗ trợ | Có cần cookie partitioned không? |

### Host-only và Domain cookie

Nếu cookie không có Domain attribute, nó thường là host-only và chỉ gửi tới host đã tạo cookie.

Nếu cookie đặt:

    Domain=example.test

nó có thể được gửi tới domain đó và các subdomain phù hợp. Chỉ mở rộng Domain khi ứng dụng thực sự cần chia sẻ session giữa các subdomain.

### Path không phải ranh giới bảo mật mạnh

Path quyết định request path nào nhận cookie, nhưng không nên coi Path là cơ chế cô lập dữ liệu giữa các ứng dụng cùng host. Các ứng dụng cùng host có thể có những tương tác khác và server phải kiểm tra session/authorization riêng.

### Secure

Secure giới hạn việc gửi cookie qua kết nối không an toàn theo quy tắc cookie. Nó không mã hóa cookie trong browser profile và không ngăn script cùng origin đọc cookie nếu cookie không có HttpOnly.

### HttpOnly

HttpOnly ngăn JavaScript page đọc cookie qua document.cookie. Cookie vẫn được browser gửi tự động theo quy tắc cookie và vẫn có thể được xem trong DevTools bởi người có quyền kiểm soát browser profile.

HttpOnly giảm nguy cơ đánh cắp cookie bằng XSS, nhưng XSS vẫn có thể gửi request thay người dùng trong phiên hiện tại.

### SameSite

- Strict: hạn chế gửi cookie trong các ngữ cảnh cross-site.
- Lax: cho phép một số navigation top-level an toàn theo quy tắc browser.
- None: cho phép cookie trong ngữ cảnh cross-site khi đáp ứng điều kiện Secure.

SameSite hỗ trợ giảm CSRF nhưng không thay thế CSRF token, kiểm tra Origin/Referer hoặc các biện pháp phù hợp với threat model.

### Partitioned cookie

Cookie có thuộc tính Partitioned (CHIPS) được phân vùng theo top-level site trong các browser hỗ trợ. Điều này giúp một dịch vụ bên thứ ba duy trì state riêng theo từng site nhúng.

Ví dụ cấu hình thường gặp:

    Set-Cookie: __Host-widget-session=opaque; Path=/; Secure; SameSite=None; Partitioned

Partitioned cookie vẫn là cookie và cần kiểm tra Secure, phạm vi host, thời hạn và mục đích. Với cookie dùng trong third-party context, SameSite=None thường được khai báo cùng Secure; kiểm tra yêu cầu cụ thể của browser mục tiêu. Không giả định mọi browser hỗ trợ giống nhau.

### Prefix cookie

Một số prefix đặt thêm yêu cầu cho cookie:

- __Host- yêu cầu Secure, Path=/ và không có Domain.
- __Secure- yêu cầu cookie có thuộc tính Secure.

Ví dụ:

    Set-Cookie: __Host-session=opaque; Path=/; Secure; HttpOnly; SameSite=Lax

Đây là cấu hình minh họa cho session cookie. Cần điều chỉnh SameSite và luồng đăng nhập theo kiến trúc thật.

## 5. document.cookie và giới hạn inspection

JavaScript có thể đọc các cookie không có HttpOnly và phù hợp với document hiện tại:

    console.log(document.cookie);

Lệnh này có thể làm lộ credential trong Console history hoặc ảnh chụp. Không chạy trên tài khoản production nếu không có lý do và quy trình bảo vệ dữ liệu.

### Vì sao document.cookie không hiển thị mọi cookie?

- Cookie HttpOnly không được JavaScript đọc.
- Cookie không thuộc host/path hiện tại không xuất hiện.
- Cookie hết hạn hoặc bị browser chặn không được trả về.
- Cookie partitioned và third-party policy có thể ảnh hưởng khả năng truy cập.

DevTools có thể hiển thị cookie HttpOnly mà JavaScript không đọc được. Điều đó không có nghĩa page script cũng có quyền đọc cookie này.

### Cookie không phải localStorage

Cookie có thể được gửi tự động trong request theo quy tắc domain/path/SameSite. localStorage thì không tự động được gắn vào HTTP request; JavaScript phải đọc rồi chủ động gửi.

Sự khác nhau này ảnh hưởng trực tiếp tới CSRF và XSS:

- Cookie session tự động gửi tạo rủi ro CSRF nếu endpoint không có biện pháp bảo vệ.
- Token trong localStorage giảm một số cơ chế gửi tự động nhưng dễ bị script cùng origin đọc khi có XSS.

## 6. localStorage inspection

localStorage lưu cặp key/value dạng chuỗi và thường tồn tại qua reload, đóng tab và mở lại browser profile, cho tới khi bị xóa hoặc browser dọn dữ liệu.

Trong DevTools:

1. Mở Application → Storage → Local Storage.
2. Chọn origin.
3. Quan sát danh sách key/value, dung lượng và thao tác sửa/xóa.
4. Xác định dữ liệu nào thuộc ứng dụng, SDK hoặc thư viện bên thứ ba.

### Đặc điểm

- Phạm vi thông thường theo origin.
- Dữ liệu lưu dưới dạng string.
- API đồng bộ, thao tác lớn có thể chặn main thread.
- Không có thuộc tính HttpOnly, Secure hoặc SameSite như cookie.
- JavaScript chạy cùng origin có thể đọc/ghi.
- Không tự gửi theo request.

### Kiểm tra bằng Console

Trong môi trường test:

    localStorage.setItem("demo-theme", "dark");
    localStorage.getItem("demo-theme");
    localStorage.removeItem("demo-theme");

Xem số lượng entry:

    localStorage.length;

Liệt kê key cho dữ liệu test:

    Array.from(
      { length: localStorage.length },
      (_, index) => localStorage.key(index)
    );

Không dump toàn bộ value vào Console hoặc log. Key cũng có thể chứa email, account ID hoặc dữ liệu cá nhân; chỉ kiểm tra metadata cần thiết.

### Rủi ro bảo mật

Không lưu password, refresh token dài hạn hoặc dữ liệu nhạy cảm không cần thiết trong localStorage. Bất kỳ JavaScript nào chạy được trong origin, kể cả script bên thứ ba hoặc XSS, có thể đọc dữ liệu này.

localStorage không có expiration tự động theo từng item. Ứng dụng cần tự quản lý version, thời hạn và cleanup.

### Storage event

Khi một document khác cùng storage area thay đổi localStorage, các document liên quan có thể nhận sự kiện storage. Document thực hiện thay đổi không nhận event của chính thao tác đó.

Ví dụ chỉ ghi tên key trong môi trường test:

    window.addEventListener("storage", (event) => {
      console.log("Storage key changed:", event.key);
    });

Không log oldValue/newValue trong môi trường có dữ liệu thật vì có thể chứa token hoặc PII.

## 7. sessionStorage inspection

sessionStorage cũng lưu key/value dạng chuỗi nhưng gắn với origin và top-level browsing context, thường tương ứng với tab.

Trong DevTools:

1. Mở Application → Storage → Session Storage.
2. Chọn origin của tab.
3. Kiểm tra key/value và vòng đời.
4. Mở tab mới và so sánh state.
5. Đóng tab rồi mở lại để quan sát dữ liệu session kết thúc.

### Đặc điểm

- Phân vùng theo origin và browsing context.
- Thường tồn tại qua reload trong cùng tab.
- Bị xóa khi tab/window kết thúc theo vòng đời session.
- Không tự gửi theo request.
- JavaScript cùng origin có thể đọc/ghi.

### Tab mới và opener

Khi một browsing context mới được tạo với opener, browser có thể khởi tạo sessionStorage bằng bản sao ban đầu của opener theo quy tắc HTML. Sau đó hai vùng storage độc lập; thay đổi ở tab này không tự đồng bộ sang tab kia.

Nếu tạo cửa sổ với noopener hoặc context không có opener, hành vi khởi tạo khác. Không giả định mọi tab mới đều bắt đầu với sessionStorage rỗng.

### Dùng đúng mục đích

sessionStorage phù hợp với trạng thái tạm của một tab như wizard state hoặc draft ngắn hạn. Nó không phải nơi an toàn để lưu secret: XSS cùng origin vẫn có thể đọc, và dữ liệu có thể được giữ lâu hơn dự kiến khi tab còn mở.

## 8. IndexedDB inspection

IndexedDB là database bất đồng bộ trong browser, phù hợp với dữ liệu có cấu trúc và dung lượng lớn hơn Web Storage.

Trong DevTools:

1. Mở Application → Storage → IndexedDB.
2. Mở database theo origin.
3. Xem object store và index.
4. Chọn object store để duyệt record.
5. Kiểm tra key path, record count và cấu trúc dữ liệu.
6. Dùng nút refresh nếu ứng dụng vừa thay đổi schema hoặc dữ liệu.

### Thành phần IndexedDB

| Thành phần | Ý nghĩa |
| --- | --- |
| Database | Database có tên và version |
| Object store | Kho record tương tự bảng nhưng không phải SQL table |
| Key | Định danh record |
| Key path | Thuộc tính dùng làm key |
| Index | Cấu trúc tìm kiếm theo thuộc tính |
| Transaction | Nhóm thao tác đọc/ghi có phạm vi và mode |

### Ví dụ tạo database test

    const request = indexedDB.open("demo-notes", 1);

    request.onupgradeneeded = () => {
      const db = request.result;
      db.createObjectStore("notes", {
        keyPath: "id"
      });
    };

    request.onsuccess = () => {
      const db = request.result;
      const transaction = db.transaction(
        "notes",
        "readwrite"
      );
      transaction.objectStore("notes").put({
        id: "note-1",
        title: "Demo",
        body: "Test data only"
      });
    };

Không chạy đoạn tạo database test trên origin production nếu chưa được phép; nó tạo dữ liệu persistent trong profile.

### Kiểm tra dữ liệu lớn

IndexedDB có thể chứa Blob, File, object lồng nhau và dữ liệu offline. DevTools có thể không hiển thị mọi byte hoặc cấu trúc phức tạp thuận tiện.

Không export record thật để đính kèm ticket nếu chưa redaction. Record có thể chứa token, PII, dữ liệu thanh toán hoặc nội dung nhạy cảm.

### Xóa database

Xóa database trong DevTools có thể khiến ứng dụng mất dữ liệu offline, draft hoặc queue chưa đồng bộ. Chỉ thực hiện trên test profile hoặc khi đã xác nhận tác động.

Ứng dụng cũng có thể mở database và chặn thao tác versionchange; DevTools có thể yêu cầu đóng connection hoặc refresh trước khi xóa.

## 9. Cache Storage inspection

Cache Storage là API lưu trữ response theo Cache API, thường được service worker sử dụng để hỗ trợ offline hoặc tối ưu mạng.

Nó khác HTTP cache của browser:

| Cache Storage | HTTP cache |
| --- | --- |
| Do ứng dụng quản lý qua Cache API | Browser quản lý theo HTTP caching semantics |
| Thường được service worker sử dụng | Dựa trên response headers như Cache-Control, ETag, Vary |
| Có thể chứa response theo logic app | Có thể tái sử dụng response theo cache policy |
| Hiển thị trong Application → Cache Storage | Kiểm tra qua Network và browser cache controls |

### Kiểm tra Cache Storage

1. Mở Application → Cache Storage.
2. Chọn cache name.
3. Kiểm tra request URL và response metadata.
4. Mở response cần thiết trong môi trường test.
5. Đối chiếu cache version với service worker đang hoạt động.
6. Xác nhận response riêng tư không bị cache hoặc chia sẻ sai user.

### Cache có thể chứa dữ liệu nhạy cảm

Nếu service worker cache API response cá nhân hóa, dữ liệu có thể còn lại sau logout hoặc chuyển user nếu ứng dụng không xóa cache đúng cách.

Không cache response nhạy cảm theo URL chung mà không phân tách user/tenant. Cân nhắc Cache-Control và logic cache của service worker; HTTP cache header không tự quản lý mọi entry do Cache API tạo.

### Xóa Cache Storage

Xóa cache có thể làm ứng dụng offline không hoạt động cho tới khi tải lại tài nguyên. Kiểm tra service worker có tái tạo cache ngay sau khi xóa không.

### Disable cache trong Network không xóa Cache Storage

Tùy chọn Disable cache trong Network panel chủ yếu tắt việc dùng HTTP browser cache khi DevTools đang mở. Nó không xóa Cache Storage entries do Cache API tạo và không thay thế thao tác xóa cache trong Application panel. Khi debug offline hoặc service worker, kiểm tra riêng cả HTTP cache, Cache Storage và service worker controller.

## 10. Service Worker inspection

Service worker là script chạy trong môi trường riêng, có thể xử lý fetch event, push, background sync và quản lý cache theo khả năng browser.

Trong DevTools:

1. Mở Application → Service Workers.
2. Kiểm tra script URL, scope và trạng thái.
3. Xem worker đang activated, waiting hoặc redundant.
4. Dùng Update hoặc Unregister trong môi trường test khi cần.
5. Kiểm tra option bypass for network hoặc offline nếu browser cung cấp.
6. Đối chiếu Cache Storage với version worker.

### Scope

Scope xác định phạm vi URL mà service worker có thể kiểm soát. Scope không phải cơ chế authorization cho dữ liệu server.

### Unregister không xóa cache

Unregister service worker không tự động xóa mọi Cache Storage entry. Cache có thể vẫn tồn tại cho tới khi ứng dụng hoặc người dùng xóa.

Ngược lại, xóa cache không nhất thiết unregister service worker. Khi debug offline, cần kiểm tra cả hai trạng thái.

### Waiting worker và lifecycle

Worker mới có thể ở trạng thái waiting cho tới khi các client đang mở không còn dùng worker cũ hoặc cơ chế skipWaiting/clients.claim được áp dụng. Khi kiểm tra lỗi cache cũ, xem controller của tab và worker đang active thay vì chỉ nhìn file script mới trên server.

## 11. OPFS và các dạng storage khác

Origin Private File System (OPFS) cung cấp vùng file riêng cho origin trong các browser hỗ trợ. Nó thường được dùng cho ứng dụng xử lý file, dữ liệu lớn hoặc database engine chạy trong browser.

Ví dụ truy cập thư mục gốc:

    const root = await navigator.storage.getDirectory();

OPFS không phải thư mục tùy ý trên ổ đĩa mà website có thể duyệt toàn bộ. Nó được browser quản lý theo origin/storage key và quyền truy cập của API.
Truy cập OPFS cũng yêu cầu secure context trong các browser hiện đại.

### Storage estimate

Có thể xem ước lượng dung lượng:

    const estimate = await navigator.storage.estimate();
    console.log({
      usage: estimate.usage,
      quota: estimate.quota
    });

Storage API yêu cầu secure context trong các browser hiện đại. Không log chi tiết dữ liệu người dùng; usage và quota chỉ là số liệu ước lượng của browser.

### Persistent storage

Ứng dụng có thể yêu cầu persistent storage:

    const granted = await navigator.storage.persist();

Kiểm tra trạng thái:

    const persisted = await navigator.storage.persisted();

Browser quyết định có cấp hay không dựa trên policy và tín hiệu sử dụng. Persistent không có nghĩa dữ liệu được backup, không bao giờ mất hoặc được bảo vệ khỏi XSS.

### Eviction

Browser có thể xóa dữ liệu storage theo quota, áp lực dung lượng, chính sách profile hoặc thao tác người dùng. Persistent storage có thể được bảo vệ tốt hơn khỏi một số eviction tự động, nhưng vẫn có thể bị xóa bởi người dùng hoặc quản trị.

Ứng dụng cần đồng bộ dữ liệu quan trọng lên server theo thiết kế, xử lý quota exceeded và không giả định browser storage là bản sao duy nhất.

## 12. Storage partitioning và third-party context

Browser có thể phân vùng storage của bên thứ ba theo top-level site nhằm giảm tracking xuyên site.

Ví dụ:

    https://shop.example.test
      └── iframe https://widget.vendor.test

    https://news.example.test
      └── iframe https://widget.vendor.test

Widget có thể nhận storage partition riêng ở hai trang cha. Cookie third-party, localStorage, IndexedDB và các API khác có quy tắc partition/permission khác nhau tùy browser.

### Kiểm tra trong DevTools

- Xác định frame sở hữu storage.
- Xác định top-level site.
- Xem cookie có cột partition key hoặc thuộc tính Partitioned hay không nếu UI hỗ trợ.
- So sánh cùng iframe trên hai top-level site khác nhau.
- Thử trong profile sạch và phiên bản browser mục tiêu.

### Không nhầm partitioning với same-origin

Hai context có cùng origin của iframe vẫn có thể có storage state khác nhau do top-level partition. Ngược lại, cùng site nhưng khác origin không chia sẻ localStorage.

### Storage Access API

Một số browser cung cấp Storage Access API để embedded third-party content yêu cầu quyền truy cập storage không phân vùng trong những điều kiện nhất định. API này có prompt, policy và yêu cầu user activation tùy browser.

Không giả định iframe luôn đọc được cookie hoặc storage third-party. Kiểm tra hành vi thực tế, quyền được cấp và fallback khi bị từ chối.

## 13. Storage và rủi ro XSS

JavaScript cùng origin có thể đọc localStorage, sessionStorage, IndexedDB và Cache Storage mà ứng dụng có quyền truy cập. Nếu XSS chạy được trong origin, attacker có thể đọc dữ liệu hoặc thực hiện hành động thay người dùng.

### Token trong localStorage

Lưu access token trong localStorage khiến token có thể bị đọc bởi script cùng origin. XSS có thể lấy token và gửi ra ngoài.

Biện pháp giảm rủi ro:

- Phòng XSS bằng output encoding và sanitization theo ngữ cảnh.
- Dùng CSP và Trusted Types khi phù hợp.
- Hạn chế third-party script.
- Không lưu refresh token dài hạn trong Web Storage nếu kiến trúc có lựa chọn an toàn hơn.
- Cân nhắc BFF và session cookie HttpOnly, Secure, SameSite.
- Giới hạn thời hạn và scope token.

BFF không loại bỏ XSS: script độc hại vẫn có thể gửi request same-origin thay người dùng trong phiên hiện tại. Cookie HttpOnly ngăn đọc giá trị cookie, không ngăn mọi hành động.

### Web Storage không có HttpOnly

Không thể gắn HttpOnly cho localStorage hoặc sessionStorage. Nếu dữ liệu cần được bảo vệ khỏi JavaScript page, hãy đánh giá lại kiến trúc lưu trữ thay vì tự mã hóa bằng key cũng nằm trong JavaScript.

### IndexedDB cũng không phải vùng bí mật

IndexedDB có thể chứa dữ liệu lớn hoặc offline nhưng vẫn thuộc quyền của origin. XSS cùng origin có thể gọi API IndexedDB và đọc record mà ứng dụng cho phép.

## 14. Storage và rủi ro CSRF

CSRF thường liên quan credential browser tự gửi, đặc biệt là cookie session. DevTools giúp xác minh cookie có được gửi trong request hay không.

### Kiểm tra cookie request

1. Mở Network.
2. Thực hiện request tới endpoint nhạy cảm trong môi trường test.
3. Chọn request và xem Cookies hoặc Request Headers.
4. Kiểm tra cookie nào được gửi và lý do bị loại nếu browser hiển thị.
5. Đối chiếu SameSite, Secure, domain và context navigation.

### Web Storage và CSRF

localStorage/sessionStorage không tự động được browser gửi theo request cross-site. Nhưng nếu JavaScript đọc token từ storage rồi gắn vào Authorization header, request có thể có mô hình CSRF khác và vẫn chịu XSS/token theft.

Không kết luận ứng dụng miễn nhiễm CSRF chỉ vì token nằm trong localStorage. Hãy kiểm tra endpoint, credential, CORS, XSS và cách client tạo request.

### Cookie SameSite không thay mọi CSRF defense

SameSite có thể giảm request cross-site mang cookie, nhưng cần xem:

- Các luồng top-level navigation.
- Cookie None; Secure.
- Subdomain cùng site nhưng khác origin.
- Browser compatibility và legacy clients.
- Endpoint chấp nhận method nào.
- Origin/Referer validation và CSRF token.

## 15. Kiểm tra dữ liệu theo vòng đời

Storage inspection không chỉ là đọc value; cần kiểm tra thời điểm dữ liệu được tạo, giữ và xóa.

### Reload

- localStorage thường còn.
- sessionStorage thường còn trong cùng tab.
- IndexedDB còn.
- Cache Storage còn.
- Cookie còn nếu chưa hết hạn và không bị xóa.
- Service worker tiếp tục theo lifecycle riêng.

### Đóng tab

- sessionStorage của browsing context kết thúc.
- localStorage, IndexedDB, Cache Storage và cookie thường còn.
- Service worker có thể tiếp tục tồn tại hoặc được đánh thức theo event browser.

### Logout

Kiểm tra:

- Server có revoke session/token không?
- Cookie session có bị expire/xóa đúng domain/path không?
- Token trong localStorage/sessionStorage có bị xóa không?
- IndexedDB có giữ dữ liệu nhạy cảm không?
- Cache Storage có giữ API response cá nhân hóa không?
- Service worker có tiếp tục trả dữ liệu cache cũ không?
- Các tab khác có được thông báo session đã kết thúc không?

Logout chỉ xóa cookie mà để access token trong localStorage hoặc dữ liệu nhạy cảm trong cache có thể tạo session residue.

### Clear site data

Clear site data có thể xóa cookie, Web Storage, IndexedDB, Cache Storage và dữ liệu khác của site theo browser. Nó có thể làm mất draft, offline data hoặc trạng thái chưa đồng bộ.

Chỉ dùng trên test profile hoặc sau khi xác nhận tác động với người sở hữu dữ liệu.

## 16. Workflow inspection có hệ thống

### Bước 1 — Ghi nhận môi trường

Ghi:

- Browser và version.
- URL/origin đang kiểm tra.
- Top-level site.
- Frame đang chọn.
- Profile thường hay private.
- Có extension hoặc policy doanh nghiệp nào ảnh hưởng không.

Không ghi account ID, cookie value hoặc token vào biên bản.

### Bước 2 — Kiểm tra từng loại storage

Theo thứ tự:

1. Cookies.
2. Local Storage.
3. Session Storage.
4. IndexedDB.
5. Cache Storage.
6. Service Workers.
7. OPFS hoặc storage khác nếu ứng dụng sử dụng.

Với mỗi loại, ghi key/schema, mục đích, thời hạn và dữ liệu nhạy cảm ở mức phân loại. Không sao chép raw value nếu không cần.

### Bước 3 — Đối chiếu Network

1. Mở Network và bật Preserve log khi cần kiểm tra redirect/navigation.
2. Thực hiện luồng login, thao tác dữ liệu, reload và logout.
3. Kiểm tra request Cookie, Set-Cookie, Authorization và response cache headers.
4. Đối chiếu response có được đưa vào Cache Storage hay không.
5. Kiểm tra request có gửi dữ liệu từ Web Storage qua body/header không.

Preserve log giữ lại request qua navigation trong phiên DevTools; HAR export có thể chứa URL, header, cookie và body. Không export HAR thật nếu chưa redaction.

### Bước 4 — Kiểm tra logout và xóa dữ liệu

1. Ghi nhận loại storage có dữ liệu trước logout.
2. Thực hiện logout.
3. Reload và thử truy cập route riêng tư.
4. Kiểm tra storage còn lại.
5. Mở tab khác cùng ứng dụng và quan sát đồng bộ trạng thái.
6. Xác nhận server từ chối session đã revoke.

### Bước 5 — Kiểm tra partition

1. Dùng hai top-level site test.
2. Nhúng cùng third-party iframe.
3. Quan sát storage và cookie trong từng context.
4. Thử browser profile sạch.
5. Ghi nhận khác biệt theo browser/version.

## 17. Console inspection an toàn

Console hữu ích để kiểm tra API, nhưng có thể lưu output trong history, log hoặc ảnh chụp. Dùng dữ liệu test và chỉ in metadata cần thiết.

### Kiểm tra số lượng localStorage entry

    console.log("localStorage entries:", localStorage.length);

### Kiểm tra một key test cụ thể

    const demoValue = localStorage.getItem("demo-theme");
    console.log("demo-theme exists:", demoValue !== null);

Không in value của key có thể chứa token hoặc PII.

### Kiểm tra sessionStorage

    console.log("sessionStorage entries:", sessionStorage.length);

### Kiểm tra IndexedDB database names

    if (indexedDB.databases) {
      const databases = await indexedDB.databases();
      console.log(
        databases.map((db) => ({
          name: db.name,
          version: db.version
        }))
      );
    }

API databases() không được hỗ trợ đồng nhất ở mọi browser. Không in object store record thật vào Console.

### Kiểm tra storage estimate

    const estimate = await navigator.storage.estimate();
    console.log({
      usage: estimate.usage,
      quota: estimate.quota
    });

### Kiểm tra cookie từ JavaScript

    console.log(
      "document.cookie is available:",
      typeof document.cookie === "string"
    );

Không in document.cookie. Dùng Application → Cookies để kiểm tra thuộc tính; nhớ rằng DevTools có thể hiển thị giá trị credential.

## 18. Xóa dữ liệu có chọn lọc và tác động

DevTools thường cung cấp thao tác xóa theo storage type hoặc Clear site data.

### Xóa một localStorage key

Trong môi trường test:

    localStorage.removeItem("demo-theme");

### Xóa toàn bộ localStorage của origin

    localStorage.clear();

Thao tác này ảnh hưởng mọi dữ liệu localStorage của origin hiện tại, không chỉ ứng dụng đang mở nếu nhiều ứng dụng cùng origin.

### Xóa sessionStorage

    sessionStorage.clear();

Chỉ ảnh hưởng storage area của browsing context hiện tại.

### Xóa IndexedDB

Có thể xóa database trong Application panel hoặc dùng API deleteDatabase. Trước khi xóa, kiểm tra ứng dụng có dữ liệu offline hoặc draft chưa đồng bộ.

### Xóa Cache Storage

Trong Console:

    const cacheNames = await caches.keys();
    console.log("Cache count:", cacheNames.length);

Xóa cache test cụ thể:

    await caches.delete("app-cache-v1");

Không xóa tất cả cache trên profile thật nếu chưa hiểu tác động. Service worker có thể tạo lại cache khi fetch hoặc install.

### Xóa cookie

Xóa cookie phải khớp name, domain và path; cookie partitioned còn có partition context. Dùng Application panel để xem đúng cookie và thao tác có chủ đích.

### Clear site data

Clear site data là thao tác rộng. Nó có thể xóa cookie, storage, cache và dữ liệu liên quan. Ghi lại trạng thái trước khi xóa và chỉ thực hiện trên môi trường test hoặc với sự cho phép rõ ràng.

## 19. Privacy khi dùng DevTools

DevTools có quyền hiển thị nhiều dữ liệu mà JavaScript page không đọc được, ví dụ cookie HttpOnly. Vì vậy, người thao tác DevTools phải bảo vệ dữ liệu như khi truy cập hệ thống nhạy cảm.

Không:

- Chụp ảnh có cookie/token/PII hiển thị.
- Paste session cookie vào Console hoặc chat.
- Export HAR chứa Authorization/Cookie rồi gửi nguyên trạng.
- Chia sẻ profile browser hoặc thư mục user data.
- Bật remote debugging trên máy không tin cậy.
- Để DevTools mở trên thiết bị dùng chung khi đang hiển thị tài khoản thật.
- Dùng Console snippet không rõ nguồn gốc để dump toàn bộ storage.

Nếu cần chia sẻ bằng chứng:

- Dùng dữ liệu giả hoặc staging.
- Che value và giữ lại tên thuộc tính cần thiết.
- Redact URL query, Authorization, Cookie và Set-Cookie.
- Chỉ giữ status, domain, attribute và timestamp cần cho phân tích.
- Xóa file HAR/screenshot tạm sau khi hoàn thành theo chính sách.

### Remote debugging

Remote debugging protocol có thể cho client điều khiển browser, đọc DOM, network và storage. Không mở cổng remote debugging ra mạng công cộng hoặc cấp cho process không tin cậy.

## 20. Kiểm thử bảo mật storage

### Kiểm tra token persistence

1. Đăng nhập bằng user test.
2. Kiểm tra cookie và Web Storage.
3. Xác định token/session identifier có nằm trong localStorage, sessionStorage hoặc IndexedDB không.
4. Logout.
5. Reload và kiểm tra token cũ còn được gửi hay không.
6. Xác nhận server từ chối credential đã revoke/hết hạn.

### Kiểm tra HttpOnly

1. Xem cookie session trong Application → Cookies.
2. Xác nhận HttpOnly được bật.
3. Kiểm tra document.cookie không trả cookie đó.
4. Kiểm tra request vẫn gửi cookie theo policy khi user sử dụng ứng dụng.

### Kiểm tra SameSite/CSRF

1. Ghi nhận SameSite và Secure.
2. Dùng môi trường test với hai site.
3. Thực hiện navigation và request cross-site theo kịch bản.
4. Quan sát cookie có được gửi hay không.
5. Kiểm tra CSRF token hoặc Origin validation ở server.

Không kết luận CSRF đã được xử lý chỉ từ thuộc tính SameSite.

### Kiểm tra cache residue

1. Mở dữ liệu riêng tư bằng user A.
2. Kiểm tra Cache Storage và HTTP cache behavior.
3. Logout user A.
4. Đăng nhập user B trong cùng profile test.
5. Thử truy cập dữ liệu đã cache.
6. Xác nhận không hiển thị response của user A.

### Kiểm tra XSS exposure

1. Dùng trang lab có dữ liệu test.
2. Kiểm tra storage có chứa token hoặc PII không cần thiết.
3. Đánh giá script nào trong origin có thể đọc storage.
4. Kiểm tra CSP, Trusted Types và third-party script inventory.
5. Xác nhận dữ liệu nhạy cảm không bị gửi tới endpoint ngoài dự kiến.

## 21. Ma trận kiểm thử tổng hợp

| Ca kiểm thử | Thao tác | Kết quả mong đợi |
| --- | --- | --- |
| Origin boundary | Mở hai origin khác nhau | Web Storage không tự chia sẻ |
| Same site, different origin | So sánh hai subdomain | localStorage tách biệt |
| Third-party partition | Nhúng cùng iframe trên hai top-level site | Storage có thể được phân vùng theo browser |
| Cookie HttpOnly | So sánh DevTools với document.cookie | DevTools có thể hiển thị; page JS không đọc được |
| Cookie Secure | Thử request trên HTTP test | Cookie Secure không được gửi theo quy tắc |
| Cookie SameSite | Thử navigation cross-site | Hành vi theo Lax/Strict/None |
| Partitioned cookie | Kiểm tra ở hai top-level site | Partition key/state khác nhau nếu browser hỗ trợ |
| localStorage persistence | Reload tab | Dữ liệu còn cho tới khi bị xóa |
| sessionStorage | Reload cùng tab và mở tab mới | Cùng tab giữ state; tab mới có context riêng theo opener rules |
| storage event | Thay localStorage ở tab khác | Document liên quan nhận event |
| IndexedDB | Tạo database test | Database/object store hiển thị trong DevTools |
| Cache Storage | Service worker cache response test | Entry xuất hiện trong Cache Storage |
| HTTP cache | Reload tài nguyên có cache header | Network thể hiện cache behavior |
| Service worker unregister | Unregister worker | Cache Storage không mặc nhiên bị xóa |
| Logout | Xóa session | Token/cache nhạy cảm không còn dùng được |
| Quota | Kiểm tra estimate | Browser trả usage/quota ước lượng |
| Persistent storage | Gọi persist() | Browser quyết định cấp hay không |
| Clear site data | Xóa dữ liệu test | Các storage liên quan bị xóa theo browser |
| HAR privacy | Export test request | Credential và PII được redacted |
| Cache isolation | Đổi user trong cùng profile | Không thấy response riêng tư của user trước |
| Storage XSS | Đánh giá script cùng origin | Dữ liệu Web Storage/IndexedDB được coi là có thể bị đọc nếu XSS |
| Console hygiene | Kiểm tra key/metadata | Không in raw token hoặc PII |

## 22. Sai lầm thường gặp

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Chỉ kiểm tra cookie | Bỏ sót token và dữ liệu trong Web Storage/IndexedDB/cache | Kiểm tra tất cả storage type |
| Nhầm site với origin | Cho rằng subdomain chia sẻ localStorage | So sánh scheme, host và port |
| Nghĩ HttpOnly làm cookie vô hình trong DevTools | Đánh giá sai khả năng inspection | Phân biệt DevTools với JavaScript page |
| Nghĩ Secure mã hóa cookie trong profile | Bỏ qua bảo vệ dữ liệu trên thiết bị | Dùng OS/profile security và giảm thời gian lưu |
| Lưu refresh token lâu dài trong localStorage | XSS có thể đọc token | Cân nhắc BFF/HttpOnly session và token ngắn hạn |
| Nghĩ sessionStorage luôn rỗng ở tab mới | Bỏ qua opener copy behavior | Kiểm tra opener/noopener và browsing context |
| Nghĩ xóa cookie là logout hoàn chỉnh | Token hoặc cache vẫn còn | Xóa/revoke mọi credential và cache liên quan |
| Nghĩ unregister service worker xóa cache | Response cũ vẫn còn trong Cache Storage | Kiểm tra và xóa từng loại riêng |
| Nhầm Cache Storage với HTTP cache | Bỏ sót cache do service worker quản lý | Kiểm tra cả Application và Network |
| Nghĩ clear site data không mất dữ liệu | Mất draft/offline queue | Xác nhận đồng bộ và tác động trước khi xóa |
| Dump toàn bộ storage vào Console | Lộ token/PII qua log và screenshot | Chỉ in metadata cần thiết |
| Export HAR nguyên trạng | Cookie, Authorization và query bị lộ | Redact trước khi chia sẻ |
| Nghĩ storage partitioning giống nhau mọi browser | Test sai hành vi third-party | Ghi browser/version và top-level site |
| Nghĩ persistent storage không thể mất | Mất dữ liệu do user/admin xóa | Đồng bộ dữ liệu quan trọng và xử lý eviction |
| Dùng storage key như authorization | IDOR hoặc truy cập trái phép | Server kiểm tra quyền mỗi request |

## 23. Câu hỏi củng cố

**Câu 1.** localStorage được phân vùng theo yếu tố nào?

**Giải đáp:** Thông thường theo origin gồm scheme, host và port; browser còn có thể áp dụng storage partitioning trong third-party context.

**Câu 2.** sessionStorage khác localStorage thế nào?

**Giải đáp:** sessionStorage gắn với origin và top-level browsing context, thường theo tab; localStorage tồn tại lâu hơn và được chia sẻ giữa document cùng origin trong cùng storage partition.

**Câu 3.** Vì sao HttpOnly cookie vẫn xuất hiện trong DevTools?

**Giải đáp:** HttpOnly ngăn JavaScript page đọc cookie qua document.cookie, không ngăn DevTools của người kiểm tra browser profile hiển thị thuộc tính và giá trị.

**Câu 4.** SameSite có thay thế CSRF token không?

**Giải đáp:** Không. SameSite giảm một số request cross-site mang cookie, nhưng cần đánh giá navigation, subdomain, browser và endpoint; CSRF token/Origin validation vẫn có thể cần.

**Câu 5.** Cache Storage khác HTTP cache thế nào?

**Giải đáp:** Cache Storage do ứng dụng quản lý qua Cache API, thường bởi service worker; HTTP cache do browser quản lý theo HTTP caching semantics và response headers.

**Câu 6.** Unregister service worker có xóa Cache Storage không?

**Giải đáp:** Không mặc nhiên. Cần kiểm tra và xóa cache riêng.

**Câu 7.** Vì sao logout phải kiểm tra IndexedDB và Cache Storage?

**Giải đáp:** Chúng có thể còn dữ liệu cá nhân hoặc response đã cache sau khi session cookie bị xóa.

**Câu 8.** Persistent storage có bảo đảm dữ liệu không bị xóa không?

**Giải đáp:** Không. Browser có thể bảo vệ khỏi một số eviction tự động, nhưng người dùng hoặc quản trị vẫn có thể xóa dữ liệu.

**Câu 9.** Có nên paste document.cookie vào ticket không?

**Giải đáp:** Không. Cookie có thể là credential. Chỉ ghi metadata cần thiết và redaction giá trị.

**Câu 10.** Storage partitioning ảnh hưởng thế nào tới iframe third-party?

**Giải đáp:** Cùng một third-party origin có thể nhận storage riêng theo từng top-level site, tùy browser và API.

## 24. Tổng kết

Browser storage inspection phải bao quát cookie, localStorage, sessionStorage, IndexedDB, Cache Storage, HTTP cache, service worker và các vùng như OPFS khi ứng dụng sử dụng. Mỗi loại có phạm vi, API, vòng đời và cơ chế gửi dữ liệu khác nhau. Origin được xác định bởi scheme, host và port; site và storage key có thể bổ sung ngữ cảnh top-level để phân vùng dữ liệu bên thứ ba.

DevTools Application/Storage giúp xem dữ liệu và thuộc tính mà JavaScript page không nhất thiết đọc được, đặc biệt là HttpOnly cookie. Hãy đối chiếu storage với Network, kiểm tra logout, cache và partitioning, đồng thời tránh in raw value hoặc export HAR chưa redaction.

Web Storage và IndexedDB không phải vùng bí mật trước XSS. Cookie HttpOnly giảm khả năng script đọc session value nhưng không ngăn XSS gửi request thay người dùng. Cache Storage có thể giữ response cá nhân hóa sau logout nếu ứng dụng không quản lý đúng. Clear site data, xóa database hoặc cache có thể làm mất dữ liệu offline; chỉ thực hiện có chủ đích trong profile test hoặc sau khi xác nhận tác động.

## Tài liệu tham khảo

1. [Chrome DevTools — Application panel](https://developer.chrome.com/docs/devtools/application): kiểm tra storage, cookie, IndexedDB, Cache Storage và service worker.
2. [MDN — Web Storage API](https://developer.mozilla.org/en-US/docs/Web/API/Web_Storage_API): localStorage, sessionStorage và storage event.
3. [MDN — IndexedDB API](https://developer.mozilla.org/en-US/docs/Web/API/IndexedDB_API): database trong browser và transaction.
4. [MDN — Cache API](https://developer.mozilla.org/en-US/docs/Web/API/Cache): Cache Storage và response caching.
5. [MDN — Service Worker API](https://developer.mozilla.org/en-US/docs/Web/API/Service_Worker_API): lifecycle và request interception.
6. [MDN — Cookies](https://developer.mozilla.org/en-US/docs/Web/HTTP/Cookies): cookie attributes, scope và bảo mật.
7. [MDN — Storage API](https://developer.mozilla.org/en-US/docs/Web/API/Storage_API): quota, estimate và persistent storage.
8. [WHATWG — HTML Standard: Web Storage](https://html.spec.whatwg.org/multipage/webstorage.html): quy tắc localStorage/sessionStorage và storage event.
9. [W3C — Storage Standard](https://storage.spec.whatwg.org/): storage key, bucket và partitioning concepts.
10. [OWASP — HTML5 Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/HTML5_Security_Cheat_Sheet.html): rủi ro Web Storage và dữ liệu phía client.
