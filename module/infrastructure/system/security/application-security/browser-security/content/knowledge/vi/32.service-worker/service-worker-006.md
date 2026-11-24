# Update lifecycle: vòng đời cập nhật Service Worker an toàn

## 1. Update lifecycle là gì?

Service Worker là script chạy trong môi trường worker do browser quản lý, thường đóng vai trò trung gian giữa trang web và mạng để hỗ trợ offline, cache, push và xử lý request. Một Service Worker đã được đăng ký có thể tồn tại qua nhiều lần tải trang. Khi website phát hành phiên bản worker mới, browser phải tải, kiểm tra, cài đặt và chuyển quyền điều khiển từ worker cũ sang worker mới.

Quá trình đó được gọi là **update lifecycle**. Nó quyết định thời điểm worker mới bắt đầu chạy, khi nào worker cũ ngừng điều khiển các tab, cache nào được giữ hoặc xóa, và liệu các tab đang mở có tiếp tục hoạt động đúng trong lúc cập nhật hay không.

Một bản cập nhật Service Worker có thể tác động đồng thời tới nhiều tab của cùng origin. Nếu worker mới xóa cache cũ quá sớm hoặc thay đổi giao thức dữ liệu không tương thích với trang đang mở, người dùng có thể gặp lỗi tải tài nguyên, mất dữ liệu offline hoặc giao diện nửa cũ nửa mới.

Bài học thuộc chương **Service worker** của module **SECURITY_APPLICATION_SECURITY_BROWSER_SECURITY**. Module phân tích ranh giới bảo mật giữa browser, origin, cookie và ứng dụng web; nghiên cứu Same-Origin Policy, CORS, XSS, CSRF, CSP, Trusted Types và security headers. Bài này tập trung đúng vào **Update lifecycle**: phát hiện phiên bản mới, các trạng thái installing/waiting/active, cài đặt nguyên tử, kích hoạt, phối hợp nhiều tab và triển khai cập nhật không làm hỏng ứng dụng.

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Mô tả các trạng thái của ServiceWorker và vòng đời cài đặt/cập nhật.
2. Giải thích browser phát hiện thay đổi script và so sánh phiên bản worker.
3. Phân biệt update check, install, waiting và activate.
4. Hiểu vai trò của HTTP cache và tùy chọn updateViaCache.
5. Dùng install event và waitUntil() để precache theo cách nguyên tử.
6. Giải thích vì sao install thất bại thì worker cũ tiếp tục hoạt động.
7. Phân biệt skipWaiting() với clients.claim().
8. Xử lý updatefound, statechange và controllerchange.
9. Thiết kế cache versioning và cleanup an toàn.
10. Phối hợp cập nhật khi nhiều tab đang mở.
11. Xây dựng UX thông báo cập nhật và reload có kiểm soát.
12. Kiểm tra update lifecycle bằng DevTools và các bài lab.

## 2. Điều kiện để đăng ký và cập nhật Service Worker

Service Worker được đăng ký từ trang web bằng navigator.serviceWorker.register(). Trong production, trang và script Service Worker phải được phục vụ qua secure context, thường là HTTPS với certificate hợp lệ. Các địa chỉ loopback như localhost được browser xem là trustworthy trong môi trường phát triển theo quy tắc tương ứng.

Ví dụ:

~~~js
if ("serviceWorker" in navigator && window.isSecureContext) {
  const registration = await navigator.serviceWorker.register("/sw.js", {
    scope: "/"
  });

  console.log("Service Worker scope:", registration.scope);
}
~~~

Các điều kiện cơ bản:

- Browser hỗ trợ Service Worker.
- Document chạy trong secure context.
- Script worker được tải từ cùng origin với trang đăng ký.
- Scope nằm trong phạm vi được phép của script URL hoặc được server cho phép mở rộng bằng Service-Worker-Allowed.
- Response script có MIME type và nội dung hợp lệ cho loại worker.
- Không bị CSP hoặc lỗi mạng ngăn tải script.

Update lifecycle bắt đầu từ một registration. Gọi register() với cùng script URL và scope có thể trả về registration hiện có, đồng thời browser có thể thực hiện kiểm tra cập nhật theo thuật toán của nền tảng.

### 2.1. Registration và worker là hai đối tượng khác nhau

ServiceWorkerRegistration đại diện cho đăng ký của một scope. Nó có thể tham chiếu tới:

- installing: worker đang cài đặt.
- waiting: worker đã cài xong nhưng đang chờ quyền activate.
- active: worker đang hoặc đã trở thành worker active của registration.

Một ServiceWorker object có state riêng như parsed, installing, installed, activating, activated hoặc redundant. Không nhầm registration.waiting với state string "waiting"; worker trong registration.waiting thường có state "installed".

### 2.2. Scope xác định những trang có thể được điều khiển

Worker đăng ký tại /app/sw.js với scope mặc định /app/ thường điều khiển các URL trong phạm vi /app/. Một worker ở /sw.js có thể có scope / nếu server cho phép và đăng ký yêu cầu scope đó.

Scope không quyết định worker có quyền đọc dữ liệu tùy ý của origin khác. Nó xác định các client URL có thể thuộc phạm vi điều khiển của registration.

## 3. Các trạng thái trong Service Worker lifecycle

ServiceWorker.state có các trạng thái chuẩn:

| State | Ý nghĩa |
| --- | --- |
| parsed | Script đã được phân tích cú pháp, đang ở giai đoạn chuẩn bị. |
| installing | Worker đang chạy install event. |
| installed | Install hoàn tất; worker có thể chờ activate nếu đã có worker active điều khiển client. |
| activating | Worker đang chạy activate event. |
| activated | Worker đã active và có thể xử lý các event phù hợp. |
| redundant | Worker không còn được sử dụng, ví dụ install thất bại hoặc đã bị thay thế. |

Luồng khái quát:

~~~mermaid
stateDiagram-v2
    [*] --> parsed
    parsed --> installing
    installing --> installed: install thành công
    installing --> redundant: install thất bại
    installed --> activating: không cần chờ hoặc được skipWaiting
    activating --> activated: activate hoàn tất
    activating --> redundant: không thể tiếp tục
    installed --> redundant: worker bị thay thế hoặc loại bỏ
    activated --> redundant: worker cũ bị thay thế
~~~

Sơ đồ mô tả các trạng thái phổ biến. Browser có thể quản lý thời điểm chạy worker và chuyển trạng thái theo thuật toán riêng; worker không phải process luôn chạy liên tục.

### 3.1. Worker không chạy liên tục như trang

Browser có thể dừng Service Worker khi không còn event cần xử lý và khởi động lại khi có event mới. Biến global trong worker không phải nơi lưu trạng thái bền vững.

Dữ liệu cần tồn tại qua lần worker bị dừng phải được lưu trong IndexedDB, Cache Storage hoặc một kho phù hợp. Không dựa vào timer hoặc biến trong memory để biết chắc update lifecycle đã hoàn tất.

## 4. Registration update: browser phát hiện phiên bản mới

Browser kiểm tra script Service Worker theo cơ chế update algorithm. Việc kiểm tra có thể được kích hoạt khi:

- Trang đăng ký lại worker bằng register().
- Trang gọi registration.update().
- Browser điều hướng tới một URL trong scope và thực hiện kiểm tra theo chính sách của nó.

Browser có thể throttling hoặc gộp update checks để tránh tải mạng quá thường xuyên. Không giả định cứ mỗi lần mở tab là luôn tải lại toàn bộ worker script.

Ví dụ yêu cầu kiểm tra tường minh:

~~~js
const registration = await navigator.serviceWorker.ready;
await registration.update();
~~~

update() yêu cầu browser kiểm tra script đã đăng ký. Nó không buộc cài đặt một worker mới nếu nội dung script không thay đổi hoặc response không hợp lệ.

### 4.1. register() không có nghĩa luôn cài worker mới

Nếu ứng dụng gọi register() nhiều lần với cùng script URL và scope, browser thường tái sử dụng registration. Browser có thể kiểm tra update, nhưng nếu script không có thay đổi có ý nghĩa thì không tạo một vòng install mới.

Không gọi register() lặp trong mỗi component render. Đặt đăng ký ở bootstrap phù hợp và quản lý lỗi tập trung.

### 4.2. updatefound event

Khi registration phát hiện một worker mới và worker bắt đầu cài đặt, registration phát ra updatefound. Ứng dụng có thể theo dõi worker mới qua registration.installing:

~~~js
registration.addEventListener("updatefound", () => {
  const worker = registration.installing;

  if (!worker) return;

  worker.addEventListener("statechange", () => {
    console.log("Worker state:", worker.state);
  });
});
~~~

updatefound cho biết có worker mới đang được cài đặt. Nó không đồng nghĩa update đã hoàn tất hoặc người dùng đã được chuyển sang phiên bản mới.

## 5. Browser so sánh script như thế nào?

Browser tải lại script worker và các script được import theo thuật toán update. Nếu nội dung script mới khác phiên bản đã cài theo quy tắc so sánh của Service Worker update algorithm, browser có thể tạo worker mới và chạy install.

Trong thực tế, thay đổi byte của main script hoặc các imported script liên quan có thể khiến browser phát hiện update. Chỉ đổi timestamp ở server hoặc deploy lại cùng nội dung không nhất thiết tạo phiên bản mới.

Không nên dựa vào một query parameter ngẫu nhiên ở mỗi lần load để ép worker update liên tục. Điều đó làm tăng request và có thể gây cập nhật không cần thiết.

### 5.1. Thay đổi comment cũng có thể tạo update

Vì browser so sánh nội dung script, thay đổi comment hoặc whitespace trong script có thể làm worker được xem là khác. Ngược lại, thay đổi file tài nguyên mà worker không import và không kiểm tra theo cơ chế liên quan có thể không kích hoạt update worker.

Nếu muốn phát hành ứng dụng mới, cần có quy trình build/deploy nhất quán cho worker script và các asset mà worker quản lý.

### 5.2. Imported scripts

Với classic worker, importScripts() tải script phụ thuộc. Với module Service Worker, static import và module graph cũng tham gia vào quá trình tải script theo hỗ trợ của browser.

Thay đổi imported script có thể làm browser phát hiện worker update. Hãy quản lý dependency và cache header cho cả main script lẫn file được import, không chỉ sw.js.

## 6. updateViaCache và HTTP cache

Service WorkerRegistration có tùy chọn updateViaCache để điều khiển việc browser dùng HTTP cache khi kiểm tra script worker và imported scripts.

Ba giá trị:

| Giá trị | Main Service Worker script | Imported scripts |
| --- | --- | --- |
| imports | Không dùng HTTP cache cho main script theo update check; imported scripts có thể dùng cache. | Có thể dùng HTTP cache. |
| all | Có thể dùng HTTP cache cho main script và imported scripts. | Có thể dùng HTTP cache. |
| none | Bỏ qua HTTP cache cho main script và imported scripts trong update check. | Bỏ qua HTTP cache. |

Giá trị mặc định là imports. Tùy chọn này liên quan tới **update checks**; nó không có nghĩa mọi fetch() mà Service Worker thực hiện trong runtime đều bỏ qua HTTP cache.

Ví dụ:

~~~js
const registration = await navigator.serviceWorker.register("/sw.js", {
  scope: "/",
  updateViaCache: "none"
});
~~~

### 6.1. Chọn updateViaCache phù hợp

- imports: lựa chọn mặc định cân bằng; main script được kiểm tra mới, imported scripts có thể chịu HTTP cache.
- all: chỉ dùng khi đã hiểu cache header và có quy trình invalidation rõ.
- none: hữu ích khi muốn update check không dựa vào HTTP cache cho cả script phụ thuộc, nhưng tăng request tới server.

Không dùng none để che một cấu hình CDN sai. Cần đặt cache header phù hợp và xác minh response thực tế.

### 6.2. Cache-Control cho script worker

Một cấu hình phổ biến là phục vụ main worker script với Cache-Control: no-cache để browser có thể revalidate khi kiểm tra update. no-cache cho phép lưu response nhưng yêu cầu xác minh trước khi dùng lại; nó không giống no-store.

Imported scripts cần chính sách cache phù hợp với updateViaCache. Nếu script phụ thuộc bị cache quá lâu, browser có thể không nhận nội dung mới ngay khi bạn mong đợi.

### 6.3. CDN và deployment order

Nếu CDN có nhiều edge, có thể tồn tại thời điểm một số người dùng nhận main worker script mới nhưng imported script hoặc asset chưa được phân phối đồng bộ. Phát hành theo thứ tự an toàn: upload asset có version trước, xác minh đã có mặt, sau đó publish worker/script tham chiếu tới asset mới.

Dùng asset filename có hash giúp nội dung bất biến theo version và tránh cache cũ trả nội dung khác với tên file.

## 7. Install event và precache

Khi worker mới được cài đặt, browser phát install event. Ứng dụng thường dùng event.waitUntil() để yêu cầu browser chờ tác vụ cài đặt hoàn tất.

Ví dụ:

~~~js
const CACHE_NAME = "app-shell-v2";
const APP_SHELL = [
  "/",
  "/offline.html",
  "/styles/app.css",
  "/scripts/app.js"
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(APP_SHELL);
    })
  );
});
~~~

Nếu cache.addAll() thất bại với một tài nguyên bắt buộc, Promise bị reject và install có thể thất bại. Browser không chuyển worker mới thành active. Nếu đã có worker cũ đang active, worker cũ tiếp tục phục vụ client.

### 7.1. waitUntil() là một phần của lifecycle

waitUntil() kéo dài thời gian xử lý event cho tới khi Promise hoàn tất. Nếu không dùng waitUntil() cho tác vụ bất đồng bộ quan trọng, browser có thể kết thúc worker trước khi tác vụ hoàn tất.

Gọi waitUntil() đồng bộ trong event handler, không đợi một khoảng thời gian rồi mới gọi. Đối với install, chỉ resolve khi tài nguyên bắt buộc đã được chuẩn bị xong.

### 7.2. Precache theo cách nguyên tử

Nếu worker cần một tập tài nguyên tối thiểu để hoạt động, cài đặt nên chỉ thành công khi toàn bộ tập đó đã được cache. Điều này tránh trạng thái worker mới active nhưng thiếu một file thiết yếu.

Không bắt lỗi rồi vẫn resolve install nếu asset bắt buộc không tải được. Nếu muốn một số tài nguyên là optional, tách rõ chúng khỏi tập bắt buộc và xử lý fallback có chủ đích.

## 8. Install thất bại và rollback tự nhiên

Nếu install event reject hoặc một Promise được truyền vào waitUntil() thất bại, worker mới trở thành redundant. Browser giữ worker active trước đó nếu có.

Đây là một đặc tính an toàn quan trọng: phiên bản đang phục vụ người dùng không bị thay chỉ vì phiên bản mới tải thiếu asset hoặc lỗi cài đặt.

Luồng:

~~~mermaid
flowchart TD
    A["Worker cũ active"] --> B["Browser tìm thấy script mới"]
    B --> C["Worker mới installing"]
    C --> D{"Install và precache thành công?"}
    D -->| "Không" | E["Worker mới redundant"]
    E --> F["Worker cũ tiếp tục điều khiển"]
    D -->| "Có" | G["Worker mới installed"]
    G --> H["Chờ hoặc chuyển sang activate"]
~~~

### 8.1. Không tự xóa cache đang dùng trước khi install thành công

Tránh xóa cache phiên bản cũ trong install event trước khi cache phiên bản mới hoàn tất. Nếu install thất bại sau khi đã xóa cache cũ, worker cũ có thể vẫn active nhưng mất dữ liệu mà nó cần để phục vụ offline.

Dùng cache name có version riêng cho từng release. Tạo và điền cache mới trong install; chỉ dọn cache cũ ở giai đoạn activate khi điều kiện tương thích cho phép.

### 8.2. Install failure cần được quan sát

Ghi nhận lỗi precache và tài nguyên thất bại mà không log token hoặc dữ liệu nhạy cảm. Kiểm tra Network để tìm 404, MIME mismatch, TLS error, CSP, CORS hoặc lỗi cache. Worker install thất bại có thể không hiển thị như lỗi của trang thông thường, vì vậy cần theo dõi registration và Console.

## 9. Waiting state: worker mới chờ worker cũ

Nếu một worker đang active và còn điều khiển các client, worker mới sau khi install thành công thường chuyển sang installed và ở trạng thái chờ trong registration.waiting.

Worker mới chưa nhận quyền điều khiển client. Worker cũ tiếp tục xử lý fetch/message cho các trang đang được nó kiểm soát.

Waiting giúp tránh việc một tab đang chạy code cũ đột ngột nhận một worker mới có logic hoặc cache không tương thích.

### 9.1. Khi nào worker waiting được activate?

Thông thường, worker mới chờ cho tới khi không còn client nào đang được worker cũ điều khiển, ví dụ các tab cũ đã đóng hoặc điều hướng sang trang ngoài scope. Khi điều kiện đó đạt, browser có thể kích hoạt worker mới.

Không cần yêu cầu người dùng đóng mọi tab theo cách thủ công nếu ứng dụng có thể hiển thị thông báo cập nhật và chờ lifecycle tự nhiên. Tuy nhiên, một tab chạy lâu có thể giữ worker cũ active trong thời gian dài.

### 9.2. registration.waiting

Trang có thể kiểm tra:

~~~js
if (registration.waiting) {
  console.log("Có bản cập nhật đang chờ");
}
~~~

Worker waiting có state "installed". Ứng dụng có thể hiển thị nút “Cập nhật ngay” nếu sản phẩm muốn người dùng chủ động chuyển phiên bản.

Không tự gửi skipWaiting ngay khi thấy registration.waiting nếu chưa đánh giá tương thích với các tab hiện tại.

## 10. skipWaiting(): bỏ qua giai đoạn chờ

self.skipWaiting() yêu cầu browser cho phép worker đang waiting bỏ qua thời gian chờ để tiến tới activate sớm hơn.

Ví dụ:

~~~js
self.addEventListener("install", (event) => {
  event.waitUntil(
    (async () => {
      await precacheRequiredAssets();
      await self.skipWaiting();
    })()
  );
});
~~~

skipWaiting() không phải thao tác “cập nhật toàn bộ tab ngay lập tức” và cũng không tự làm trang reload. Nó tác động tới quá trình lifecycle của worker; worker mới vẫn cần đi qua activate.

### 10.1. Rủi ro khi dùng skipWaiting tự động

Nếu worker mới activate trong khi các tab cũ vẫn đang chạy JavaScript bundle cũ, các tab đó có thể gửi request mà worker mới không hiểu hoặc nhận asset từ cache mới không tương thích.

Ví dụ:
- Tab cũ yêu cầu /assets/app-old.js.
- Worker mới chỉ precache /assets/app-new.js.
- Worker mới xóa cache cũ.
- Tab cũ tiếp tục hoạt động và không tải được chunk động cũ.

Đây là lỗi phối hợp phiên bản, không chỉ là lỗi cache.

### 10.2. Chỉ bỏ qua waiting khi có chiến lược tương thích

skipWaiting có thể phù hợp khi:
- Bản cập nhật sửa lỗi bảo mật cần áp dụng nhanh.
- Worker và ứng dụng cũ/mới tương thích ngược.
- Cache cũ vẫn được giữ đủ lâu.
- Có UX rõ ràng để thông báo reload.
- Backend API hỗ trợ cả phiên bản client cũ và mới trong thời gian chuyển tiếp.

Không dùng skipWaiting mặc định chỉ vì muốn bản mới xuất hiện nhanh.

## 11. clients.claim(): nhận quyền điều khiển client

self.clients.claim() được gọi từ worker active, thường trong activate event. Nó yêu cầu worker mới claim các client trong scope đủ điều kiện, kể cả trang đã tải trước đó mà chưa được worker điều khiển.

Ví dụ:

~~~js
self.addEventListener("activate", (event) => {
  event.waitUntil(self.clients.claim());
});
~~~

Khi controller của một trang thay đổi, trang có thể nhận controllerchange event.

### 11.1. clients.claim() không bỏ qua waiting

clients.claim() và skipWaiting() giải quyết hai vấn đề khác nhau:

- skipWaiting(): cho phép worker waiting tiến tới activate mà không đợi các client cũ kết thúc.
- clients.claim(): worker đã active nhận quyền điều khiển các client phù hợp trong scope.

clients.claim() không tự kích hoạt worker đang waiting. Nếu worker chưa active thì gọi claim không thay thế bước activate.

### 11.2. claim có thể làm trang đang mở đổi controller

Khi worker mới claim client, trang có thể nhận controllerchange. Nếu ứng dụng không tương thích với worker mới, việc thay controller giữa phiên có thể gây lỗi.

Dùng claim khi trang và worker có giao thức tương thích. Với first install, claim giúp trang hiện tại được điều khiển ngay mà không phải chờ lần navigation tiếp theo.

## 12. Phân biệt skipWaiting và clients.claim

| Cơ chế | Giai đoạn | Mục tiêu | Tác động |
| --- | --- | --- | --- |
| skipWaiting() | Worker đang waiting/install lifecycle | Bỏ qua thời gian chờ để tiến tới activate | Worker mới có thể activate trong khi client cũ vẫn mở. |
| clients.claim() | Worker đã active | Nhận quyền điều khiển client trong scope | Client có thể phát controllerchange. |

Có thể dùng cả hai trong cùng một release, nhưng phải hiểu tác động kết hợp. skipWaiting không tự claim mọi tab; clients.claim không tự bỏ qua worker cũ đang điều khiển client.

### 12.1. Ví dụ luồng người dùng chọn cập nhật

Worker:

~~~js
self.addEventListener("message", (event) => {
  if (event.data?.type === "SKIP_WAITING") {
    event.waitUntil(self.skipWaiting());
  }
});
~~~

Trang:

~~~js
if (registration.waiting) {
  showUpdateButton(() => {
    registration.waiting.postMessage({
      type: "SKIP_WAITING"
    });
  });
}
~~~

Worker mới có thể activate sau message. Trang cần theo dõi controllerchange và reload có kiểm soát nếu ứng dụng cần đồng bộ bundle với worker mới.

## 13. activate event và migration

Khi worker mới được phép trở thành active, browser phát activate event. Đây là nơi thường dùng để:
- Chuẩn bị schema hoặc metadata storage mới.
- Dọn cache cũ nếu không còn client phụ thuộc.
- Thiết lập trạng thái cần thiết cho worker mới.
- Claim clients nếu chiến lược yêu cầu.

Ví dụ cleanup cache trong chiến lược **không ép skipWaiting**, khi worker cũ đã nhường lifecycle bình thường:

~~~js
const CACHE_NAME = "app-shell-v3";

self.addEventListener("activate", (event) => {
  event.waitUntil(
    (async () => {
      const names = await caches.keys();

      await Promise.all(
        names
          .filter((name) =>
            name.startsWith("app-shell-") && name !== CACHE_NAME
          )
          .map((name) => caches.delete(name))
      );
    })()
  );
});
~~~

Đoạn cleanup này giả định cache prefix chỉ thuộc ứng dụng và worker mới activate theo lifecycle chờ tự nhiên. Nếu dùng skipWaiting trong khi tab cũ vẫn mở, không xóa cache cũ một cách máy móc.

### 13.1. activate cũng cần waitUntil()

Nếu cleanup hoặc migration là điều kiện để worker hoạt động đúng, truyền Promise vào event.waitUntil(). Browser sẽ chờ tác vụ đó trong lifecycle event.

Không chạy migration bất đồng bộ ngoài waitUntil() rồi giả định worker luôn sống tới khi xong. Worker có thể bị dừng khi event hoàn tất.

### 13.2. Migration dữ liệu cần tương thích

Nếu thay đổi IndexedDB schema, dùng version upgrade transaction và xử lý các tab cũ đang giữ database connection. Nhiều tab có thể khiến upgrade bị blocked cho tới khi connection cũ đóng.

Không xóa database chỉ để ép schema mới nếu còn dữ liệu người dùng chưa đồng bộ. Thiết kế migration có backup/rollback phù hợp và kiểm tra tương thích giữa code cũ với schema mới.

## 14. Multi-tab: nhiều trang có thể dùng worker khác nhau trong lúc update

Một origin có thể có nhiều tab đang mở. Chúng có thể cùng được điều khiển bởi worker cũ. Worker mới có thể đã cài xong nhưng đang chờ.

Ví dụ:

~~~text
Tab A ─┐
Tab B ─┼── Worker v1 đang active
Tab C ─┘

Worker v2 đã install xong
Worker v2 đang waiting
~~~

Khi Tab A đóng nhưng Tab B/C vẫn mở và còn được v1 điều khiển, worker v2 có thể tiếp tục chờ.

### 14.1. Một tab không nên tự giả định mọi tab đã reload

Nếu một tab chọn “Cập nhật ngay”, các tab khác có thể vẫn đang chạy bundle cũ. Khi worker mới activate/claim, các tab đó có thể đổi controller trong khi state JavaScript vẫn là phiên bản cũ.

Cân nhắc thông báo giữa tab bằng BroadcastChannel hoặc cơ chế tương đương, nhưng không dùng message như bằng chứng bảo mật. Mỗi tab cần xử lý controllerchange và reload hoặc chuyển trạng thái theo thiết kế.

### 14.2. Thông báo update cho mọi tab

Có thể dùng BroadcastChannel để thông báo trạng thái cập nhật:

~~~js
const channel = new BroadcastChannel("app-update");

channel.postMessage({
  type: "UPDATE_AVAILABLE",
  version: "v3"
});
~~~

Tab khác lắng nghe:

~~~js
channel.addEventListener("message", (event) => {
  if (event.data?.type === "UPDATE_AVAILABLE") {
    showUpdateNotice();
  }
});
~~~

Thông tin version ở đây phục vụ UX. Không dùng message từ tab khác để cấp quyền hoặc xác thực người dùng.

## 15. Cache versioning và tính tương thích

Cache Storage không tự biết cache nào là mới nhất theo ý nghĩa nghiệp vụ. Ứng dụng cần đặt tên cache có version:

~~~js
const STATIC_CACHE = "static-v7";
const RUNTIME_CACHE = "runtime-v7";
~~~

Worker mới có thể precache tài nguyên vào cache version mới. Worker cũ tiếp tục dùng cache version cũ cho tới khi nó không còn active/không còn client theo lifecycle thông thường.

### 15.1. Không dùng một cache name cho mọi release

Nếu worker mới ghi đè tài nguyên vào cache đang dùng bởi worker cũ, tab cũ có thể nhận asset khác với bundle đã tải. Dùng cache version riêng để tránh ghi đè không kiểm soát.

### 15.2. Giữ cache cũ khi có client cũ

Nếu dùng skipWaiting, các client cũ có thể vẫn tồn tại sau khi worker mới activate. Giữ cache cũ cho tới khi không còn client cần nó hoặc bảo đảm worker mới có thể phục vụ cả asset version cũ và mới.

Một cách đơn giản hơn là không ép skipWaiting, để worker mới chờ các client cũ kết thúc rồi mới activate và cleanup cache cũ trong activate.

### 15.3. Runtime cache cần chính sách riêng

Không xóa runtime cache chứa dữ liệu người dùng hoặc response offline quan trọng chỉ vì đổi static asset version. Phân biệt:
- App shell có thể tải lại.
- Runtime resource cache có thể tái tạo.
- User data cache cần retention/authorization.
- Offline changes chưa đồng bộ phải được giữ hoặc backup.

## 16. Compatibility giữa HTML, JavaScript, worker và API

Service Worker update không diễn ra riêng lẻ. Một release có thể thay đổi:
- HTML shell.
- JavaScript bundle và dynamic chunks.
- CSS/font/image.
- Cache key và routing.
- IndexedDB schema.
- API contract.
- Background sync hoặc push message format.

Nếu worker mới activate trước khi CDN có đủ asset hoặc backend API đã bỏ field mà client cũ cần, ứng dụng có thể hỏng.

Chiến lược an toàn:
1. Publish asset có hash trước.
2. Đảm bảo asset cũ vẫn phục vụ trong giai đoạn chuyển tiếp.
3. Deploy backend tương thích cả client cũ và mới.
4. Publish worker tham chiếu tới asset mới.
5. Theo dõi install/activate và lỗi fetch.
6. Chỉ dọn asset cũ khi không còn client cần.

### 16.1. API backward compatibility

Backend thường cần hỗ trợ một khoảng thời gian nhiều phiên bản frontend cùng tồn tại. Service Worker có thể chờ lâu nếu tab cũ mở cả ngày; không nên giả định mọi client sẽ nâng cấp đồng thời.

Version API hoặc payload khi thay đổi breaking và có kế hoạch deprecation. Không dùng worker update để ép một client cũ gửi dữ liệu theo schema mới mà không có migration.

## 17. controllerchange và reload có kiểm soát

Trang có thể lắng nghe controllerchange khi worker điều khiển trang thay đổi:

~~~js
let refreshing = false;

navigator.serviceWorker.addEventListener("controllerchange", () => {
  if (refreshing) return;
  refreshing = true;
  window.location.reload();
});
~~~

Đây là pattern phổ biến khi ứng dụng muốn tải lại bundle để đồng bộ với worker mới. Tuy nhiên, reload tự động có thể làm mất form chưa lưu hoặc thao tác đang diễn ra.

### 17.1. Chỉ reload khi phù hợp

- Nếu có dữ liệu form chưa lưu, lưu draft hoặc hỏi người dùng trước.
- Nếu update được người dùng chấp nhận, hiển thị trạng thái và thực hiện reload đúng lúc.
- Tránh reload lặp bằng flag.
- Phân biệt first install với update có controller cũ.
- Kiểm tra trang đã ở phiên bản bundle tương thích chưa.

Không reload vô điều kiện trên mọi controllerchange nếu ứng dụng có nhiều route hoặc thao tác dài.

### 17.2. controllerchange không phải updatefound

- updatefound: registration bắt đầu cài worker mới.
- statechange: state của một ServiceWorker object thay đổi.
- controllerchange: controller của trang hiện tại thay đổi.

Ba event có thời điểm và ý nghĩa khác nhau. Dùng event đúng cho UI tương ứng.

## 18. UX thông báo cập nhật

Một giao diện cập nhật có thể có các trạng thái:

| Trạng thái | Hành động UI |
| --- | --- |
| Đang kiểm tra | Không cần làm gián đoạn người dùng. |
| Đang tải/cài worker mới | Tiếp tục dùng phiên bản hiện tại. |
| Worker mới waiting | Hiển thị thông báo “Có bản cập nhật”. |
| Người dùng chọn cập nhật | Gửi message tới worker waiting để yêu cầu skipWaiting nếu chiến lược cho phép. |
| Controller thay đổi | Lưu trạng thái cần thiết và reload hoặc chuyển tiếp. |
| Install thất bại | Giữ phiên bản hiện tại, ghi nhận lỗi và thử lại ở lần update check sau. |

Không hiển thị prompt update mỗi lần trang load nếu không có worker waiting. Tránh ép reload giữa thao tác thanh toán, nhập liệu hoặc upload.

### 18.1. Nội dung thông báo

Thông báo nên nêu:
- Có phiên bản mới.
- Lợi ích hoặc lý do cần cập nhật.
- Liệu cập nhật có reload trang hay không.
- Người dùng có thể tiếp tục sau hay cần cập nhật ngay.

Không dùng giao diện gây nhầm lẫn hoặc giả mạo thông báo hệ điều hành. Update UI thuộc ứng dụng và cần có thể truy cập bằng bàn phím/screen reader.

## 19. Ví dụ tích hợp: đăng ký và theo dõi update

Ví dụ phía trang:

~~~js
async function registerAppWorker() {
  if (!("serviceWorker" in navigator) || !window.isSecureContext) {
    return null;
  }

  const registration = await navigator.serviceWorker.register("/sw.js", {
    scope: "/",
    updateViaCache: "imports"
  });

  registration.addEventListener("updatefound", () => {
    const installing = registration.installing;
    if (!installing) return;

    installing.addEventListener("statechange", () => {
      if (
        installing.state === "installed" &&
        navigator.serviceWorker.controller
      ) {
        showUpdateAvailable();
      }
    });
  });

  if (registration.waiting && navigator.serviceWorker.controller) {
    showUpdateAvailable();
  }

  return registration;
}
~~~

Trong ví dụ, showUpdateAvailable() là hàm UI của ứng dụng. Chỉ hiển thị update notice khi có worker mới chờ và trang đã có controller cũ. First install có thể không cần prompt.

### 19.1. Xử lý nút cập nhật

~~~js
function activateWaitingWorker(registration) {
  const waiting = registration.waiting;
  if (!waiting) return;

  waiting.postMessage({
    type: "SKIP_WAITING"
  });
}
~~~

Worker cần listener cho message type đó và chỉ gọi skipWaiting theo chính sách release:

~~~js
self.addEventListener("message", (event) => {
  if (event.data?.type === "SKIP_WAITING") {
    event.waitUntil(self.skipWaiting());
  }
});
~~~

Không nhận mọi message rồi gọi skipWaiting. Kiểm tra schema và loại message, đồng thời cân nhắc việc message từ trang cùng origin vẫn là yêu cầu lifecycle chứ không phải quyết định bảo mật.

### 19.2. Theo dõi controllerchange một lần

~~~js
let reloadPending = false;

navigator.serviceWorker.addEventListener("controllerchange", () => {
  if (reloadPending) return;
  reloadPending = true;

  if (hasUnsavedWork()) {
    showReloadWhenReadyNotice();
    return;
  }

  window.location.reload();
});
~~~

Ví dụ minh họa ý tưởng. hasUnsavedWork() và showReloadWhenReadyNotice() là logic sản phẩm; cần bảo đảm khi người dùng chọn reload thì ứng dụng thực hiện đúng một lần và không bỏ dữ liệu chưa lưu.

## 20. Rollback và xử lý worker lỗi

Có hai tình huống khác nhau:

**Worker mới install thất bại:** browser không activate worker đó; worker cũ tiếp tục active. Đây là rollback tự nhiên của giai đoạn cài đặt.

**Worker mới đã activate nhưng có bug:** browser không tự động quay lại worker cũ chỉ vì ứng dụng phát hiện lỗi runtime. Cần phát hành một phiên bản worker mới sửa lỗi hoặc triển khai quy trình rollback server/CDN để browser nhận script khác.

### 20.1. Rollback sau activate

Quy trình xử lý:
1. Dừng rollout asset/backend gây lỗi nếu có thể.
2. Khôi phục worker script tốt đã biết hoặc phát hành bản sửa mới.
3. Đảm bảo nội dung script mới khác bản đang cài để update algorithm nhận ra.
4. Kiểm tra asset, cache và API compatibility.
5. Theo dõi registration update và tỉ lệ install/activate.
6. Giữ cache dữ liệu người dùng cần phục hồi.

Không giả định chỉ đổi file trên server sẽ lập tức đổi worker ở mọi browser; update check và cache policy vẫn chi phối thời điểm nhận bản mới.

### 20.2. unregister không phải rollback tức thời

registration.unregister() yêu cầu hủy đăng ký. Nó không đồng nghĩa mọi tab đang mở lập tức mất controller hoặc mọi Cache Storage bị xóa. Client đang được điều khiển có thể tiếp tục chịu ảnh hưởng cho tới khi lifecycle của tab thay đổi.

Unregister cũng không tự xóa cache. Nếu cần dọn cache, thực hiện riêng với namespace đã xác định và không xóa dữ liệu người dùng chưa đồng bộ.

## 21. Update check và chiến lược phát hành

Một quy trình release an toàn có thể gồm:

1. Build worker và assets có version/hash.
2. Upload assets mới trước.
3. Kiểm tra CDN đã phân phối asset.
4. Cập nhật worker script để tham chiếu asset mới.
5. Giữ asset cũ trong thời gian tương thích.
6. Theo dõi updatefound, install failure và activation.
7. Chỉ dọn cache cũ khi client cũ không còn cần.
8. Quan sát lỗi fetch, offline và API trong giai đoạn rollout.

Không cache worker script vô thời hạn. Đặt Cache-Control và updateViaCache theo mục tiêu. Cũng không ép browser update liên tục bằng query string ngẫu nhiên.

### 21.1. Canary và rollout theo nhóm

Với ứng dụng lớn, có thể rollout worker/asset theo nhóm người dùng hoặc region nếu hạ tầng hỗ trợ. Theo dõi:
- Tỷ lệ install thành công.
- Tỷ lệ worker waiting lâu.
- Tỷ lệ activate và controllerchange.
- Lỗi tải asset sau update.
- Lỗi IndexedDB migration.
- Lỗi API do client/server version mismatch.
- Tỉ lệ reload và session bị gián đoạn.

Không dùng dữ liệu telemetry chứa token hoặc thông tin cá nhân không cần thiết.

### 21.2. Bảo vệ đường phát hành worker

Worker mới có thể xử lý request, đọc/ghi cache và nhận message trong scope của nó. Vì vậy, quyền sửa worker script hoặc asset mà worker tin cậy là một phần quan trọng của chuỗi cung ứng phần mềm.

- Chỉ deploy worker từ pipeline và tài khoản phát hành được kiểm soát.
- Bảo vệ CDN, object storage và quyền ghi vào đường dẫn worker script.
- Phục vụ script qua HTTPS và kiểm tra certificate/redirect của endpoint.
- Tránh import script runtime từ host bên thứ ba không cần thiết.
- Rà soát dependency và build artifact trước khi phát hành.
- Dùng CSP worker-src phù hợp trên document để giới hạn nguồn tạo worker; hiểu rằng CSP không thay kiểm soát quyền deploy script.
- Không nhúng token, private key hoặc cấu hình bí mật vào worker bundle.

Nếu worker script bị thay bằng nội dung độc, browser có thể cài và chạy nó như một bản cập nhật hợp lệ theo origin. Hãy bảo vệ quyền ghi và quy trình release như bảo vệ mã backend quan trọng.

## 22. DevTools: quan sát update lifecycle

Trong Chrome/Chromium DevTools, Application panel thường có mục Service Workers. Tại đó có thể quan sát:
- Script URL và scope.
- State của worker.
- Registration đang active/waiting/installing.
- Controller của trang.
- Nút Update, Skip waiting, Stop hoặc Unregister tùy phiên bản DevTools.

Network panel giúp xem request tải script worker, response status, cache behavior và các asset precache. Console có thể hiển thị lỗi install, activate, waitUntil hoặc fetch handler.

Tên tab và nút thay đổi theo browser/version. Không dựa vào một nút DevTools để thay thế việc hiểu lifecycle thật.

### 22.1. Bật Update on reload

DevTools có thể cung cấp tùy chọn Update on reload. Khi bật, browser có thể kiểm tra và kích hoạt worker mới theo cách hỗ trợ debug, thường làm thay đổi hành vi waiting bình thường.

Dùng nó để thử nhanh trong lab. Không suy luận rằng production luôn tự skip waiting chỉ vì tùy chọn này đang bật trong DevTools.

### 22.2. Kiểm tra worker đang điều khiển trang

Trong Console:

~~~js
console.log({
  controller: navigator.serviceWorker.controller?.scriptURL,
  ready: (await navigator.serviceWorker.ready).active?.scriptURL
});
~~~

controller phản ánh worker hiện đang điều khiển trang. registration.active/ready.active cho biết worker active của registration. Chúng có thể khác trong một số thời điểm, đặc biệt khi trang mới tải hoặc registration vừa thay đổi.

## 23. Thực hành A — Quan sát first install và update

Tạo một ứng dụng lab HTTPS với worker đơn giản:

~~~js
self.addEventListener("install", (event) => {
  console.log("install v1");
});

self.addEventListener("activate", (event) => {
  console.log("activate v1");
});
~~~

Đăng ký worker, reload trang và quan sát Application → Service Workers. Sau đó thay nội dung log thành v2, lưu script và gọi registration.update().

Ghi nhận:
- updatefound có xuất hiện không?
- Worker mới ở installing rồi installed hay không?
- Có worker cũ active không?
- registration.waiting có worker mới không?
- Đóng tab cũ hoặc điều hướng ra ngoài scope thì worker mới có activate không?

Dùng origin test và không thao tác trên ứng dụng production.

## 24. Thực hành B — Install thất bại và worker cũ

Tạo worker v1 active. Sau đó phát hành v2 với precache một file chắc chắn trả 404:

~~~js
self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open("lab-v2").then((cache) => {
      return cache.addAll([
        "/index.html",
        "/missing-required-asset.js"
      ]);
    })
  );
});
~~~

Chạy update check và quan sát state của v2. Xác minh:
- v2 không trở thành active.
- Worker v1 vẫn điều khiển client.
- Lỗi precache xuất hiện trong Console/Network.
- Sau khi sửa asset và phát hành script mới, browser có thể thử update lại.

Không xóa cache v1 trong lúc thử install lỗi.

## 25. Thực hành C — Waiting, skipWaiting và clients.claim

Tạo hai tab cùng origin được worker v1 điều khiển. Phát hành worker v2 không gọi skipWaiting.

Quan sát v2 ở waiting. Sau đó thêm message handler cho SKIP_WAITING và gọi self.skipWaiting() khi người dùng bấm nút cập nhật.

Thử thêm clients.claim() trong activate. Quan sát controllerchange ở cả hai tab.

Ghi nhận sự khác nhau:
- skipWaiting cho phép v2 activate dù tab cũ còn mở.
- clients.claim giúp v2 nhận các client trong scope sau khi active.
- controllerchange thông báo controller của từng tab thay đổi.
- Nếu reload tự động, các tab có thể mất form chưa lưu nếu không có UX phù hợp.

## 26. Thực hành D — Cache versioning và tương thích nhiều tab

Tạo hai phiên bản app shell:
- v1 dùng cache app-shell-v1 và bundle app-v1.js.
- v2 dùng cache app-shell-v2 và bundle app-v2.js.

Mở một tab chạy v1, sau đó phát hành v2. Thử hai chiến lược:
1. Để v2 waiting cho tới khi tab v1 đóng.
2. Dùng skipWaiting và clients.claim khi tab v1 vẫn mở.

Quan sát request asset, cache nào bị xóa và liệu tab v1 còn tải được dynamic chunk hay không. Sửa chiến lược bằng cách giữ cache cũ hoặc bảo đảm tương thích ngược. Dùng dữ liệu test, không dùng profile production.

## 27. Checklist review Update lifecycle

- [ ] Đăng ký worker chỉ trong secure context và browser hỗ trợ.
- [ ] Script worker cùng origin và scope đúng nhu cầu.
- [ ] Hiểu scope mặc định và Service-Worker-Allowed nếu mở rộng scope.
- [ ] Phân biệt registration.installing, waiting, active với ServiceWorker.state.
- [ ] Theo dõi updatefound và statechange đúng mục đích.
- [ ] Dùng registration.update() có chủ đích; không poll quá thường xuyên.
- [ ] Đặt Cache-Control phù hợp cho main worker script và imported scripts.
- [ ] Chọn updateViaCache (imports/all/none) dựa trên cache strategy.
- [ ] Không dựa vào query string ngẫu nhiên để ép update.
- [ ] Dùng install event và waitUntil() cho precache bắt buộc.
- [ ] Nếu install thất bại, giữ worker cũ và cache cũ hoạt động.
- [ ] Không xóa cache cũ trong install trước khi worker mới sẵn sàng.
- [ ] Hiểu worker mới có thể ở waiting khi worker cũ còn client.
- [ ] Không gọi skipWaiting tự động nếu chưa có chiến lược tương thích.
- [ ] Phân biệt skipWaiting() và clients.claim().
- [ ] Xử lý controllerchange và reload có kiểm soát.
- [ ] Bảo vệ form/draft chưa lưu trước khi reload.
- [ ] Version hóa cache và asset filename.
- [ ] Giữ asset cũ trong thời gian client cũ còn có thể cần.
- [ ] Không xóa runtime cache hoặc dữ liệu user chỉ vì đổi static cache version.
- [ ] Migration IndexedDB có xử lý connection cũ và dữ liệu chưa đồng bộ.
- [ ] Backend API tương thích với nhiều phiên bản client trong rollout.
- [ ] Có phương án rollback sau khi worker đã activate.
- [ ] Hiểu unregister không tự xóa cache và không lập tức thay đổi mọi tab.
- [ ] Kiểm tra nhiều tab, browser/version và offline mode bằng DevTools.
- [ ] Telemetry update không chứa token hoặc PII không cần thiết.

## 28. Những ngộ nhận thường gặp

| Nhận định | Đánh giá | Giải thích |
| --- | --- | --- |
| “Sửa sw.js là mọi tab cập nhật ngay.” | **Sai** | Browser cần update check, install và activate theo lifecycle. |
| “Gọi register() luôn tạo worker mới.” | **Sai** | Browser có thể tái sử dụng registration và chỉ cài khi script thay đổi. |
| “update() ép browser cài bất kỳ nội dung nào.” | **Sai** | Nó yêu cầu kiểm tra; script phải khác và hợp lệ. |
| “Worker installed nghĩa là đã điều khiển trang.” | **Sai** | Installed có thể là waiting; controller là trạng thái riêng của client. |
| “Worker mới luôn activate ngay sau install.” | **Sai** | Nó có thể chờ worker cũ không còn điều khiển client. |
| “skipWaiting() tự reload mọi tab.” | **Sai** | Nó bỏ qua giai đoạn chờ; không tự reload trang. |
| “clients.claim() bỏ qua waiting.” | **Sai** | claim chỉ áp dụng khi worker đã active. |
| “skipWaiting và clients.claim là cùng một API.” | **Sai** | Một API thay đổi tiến trình activate, API kia nhận quyền điều khiển client. |
| “Install lỗi thì worker cũ bị thay.” | **Sai** | Worker mới thất bại trở thành redundant; worker cũ tiếp tục active. |
| “Có thể xóa cache cũ trong install.” | **Sai** | Install mới có thể thất bại và làm worker cũ mất cache cần thiết. |
| “activate luôn an toàn để xóa mọi cache.” | **Sai** | Với skipWaiting, tab cũ có thể còn mở và cần cache cũ. |
| “updateViaCache điều khiển mọi fetch runtime.” | **Sai** | Nó điều khiển HTTP cache khi kiểm tra script worker/imports. |
| “no-cache nghĩa là không lưu cache.” | **Sai** | no-cache cho phép lưu nhưng yêu cầu revalidate; no-store mới cấm lưu theo HTTP caching. |
| “unregister xóa Cache Storage.” | **Sai** | Unregister và xóa cache là thao tác riêng. |
| “Worker luôn chạy trong memory.” | **Sai** | Browser có thể dừng và khởi động worker theo event. |
| “controllerchange nghĩa là updatefound.” | **Sai** | Một event báo worker mới được phát hiện, event kia báo controller của trang đổi. |
| “Mỗi tab luôn dùng cùng phiên bản JS và worker.” | **Sai** | Tab cũ có thể chạy bundle cũ trong khi registration đang có worker mới waiting/active. |
| “Rollback sau activate tự động xảy ra.” | **Sai** | Cần phát hành script khác hoặc quy trình rollback có kiểm soát. |

## 29. Tổng kết

Update lifecycle điều phối cách browser phát hiện, cài đặt và kích hoạt phiên bản Service Worker mới. Browser không thay worker active chỉ vì server đã có file mới: nó cần kiểm tra script, tạo worker mới, chạy install thành công rồi mới chuyển sang waiting hoặc activate. Nếu install thất bại, worker cũ tiếp tục phục vụ.

skipWaiting() và clients.claim() là hai công cụ khác nhau. skipWaiting cho phép worker waiting tiến tới activate sớm; clients.claim giúp worker đã active nhận các client trong scope. Kết hợp chúng có thể cập nhật nhanh nhưng cũng khiến tab đang chạy bundle cũ đổi controller giữa phiên. Cache versioning, tương thích asset/API và UX reload có kiểm soát là điều kiện quan trọng.

Ba nguyên tắc cần nhớ:

1. **Cài đặt nguyên tử:** precache tài nguyên bắt buộc trong install bằng waitUntil(); chỉ để worker mới tiến tiếp khi cài đặt thành công và giữ worker cũ nếu có lỗi.
2. **Chuyển phiên bản có chủ đích:** hiểu waiting, skipWaiting, clients.claim và controllerchange; không ép update khi chưa đánh giá các tab đang mở.
3. **Giữ tương thích trong rollout:** version hóa cache/asset, giữ tài nguyên cũ khi client cũ còn dùng, migrate dữ liệu an toàn và hỗ trợ API nhiều phiên bản.

Khi review một release Service Worker, hãy hỏi: **browser đã phát hiện script mới chưa, worker mới đang ở state nào, install có hoàn tất toàn bộ precache không, worker cũ còn client nào không, có đang dùng skipWaiting/clients.claim không, tab cũ có còn tải được asset/cache cần thiết, và rollback sau activate sẽ diễn ra thế nào?** Trả lời rõ các câu hỏi này giúp cập nhật ứng dụng mà không làm gián đoạn dữ liệu hoặc phiên làm việc của người dùng.
