# Service worker update

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Mô tả vòng đời cập nhật của Service Worker và phân biệt installing, waiting, activating, activated, redundant.
- Giải thích vì sao một worker mới có thể nằm ở trạng thái waiting khi phiên bản cũ vẫn điều khiển các tab.
- Chủ động kiểm tra bản cập nhật bằng ServiceWorkerRegistration.update() và theo dõi updatefound, statechange, controllerchange.
- Đánh giá tác động của skipWaiting() và clients.claim() đối với các tab đang mở.
- Thiết kế chiến lược cache, đặt tên cache theo phiên bản và dọn cache cũ an toàn.
- Triển khai bản cập nhật theo thứ tự phù hợp, giữ tương thích giữa HTML, JavaScript, API và asset cũ.
- Theo dõi rollout, phát hiện lỗi sau cập nhật và triển khai rollback.
- Kiểm thử cập nhật online, offline, khi có nhiều tab và khi bản cài đặt mới thất bại.

## 1. Service Worker update là gì?

Service Worker là một worker chạy nền do trình duyệt quản lý, thường dùng để chặn request trong phạm vi được đăng ký, quản lý cache, hỗ trợ trải nghiệm offline và nhận một số sự kiện như push hoặc sync. Nó không chạy liên tục như một tiến trình máy chủ; trình duyệt có thể dừng worker khi không còn việc và khởi động lại khi có sự kiện.

Service Worker update là quá trình trình duyệt phát hiện phiên bản script mới, cài đặt worker mới, chuyển worker đó sang trạng thái active và để các trang trong scope sử dụng phiên bản mới theo quy tắc vòng đời. Quá trình này có ảnh hưởng trực tiếp đến nội dung được cache và những request mà worker có thể xử lý.

Cần tách ba phiên bản có thể khác nhau trong một thời điểm:

- **Phiên bản ứng dụng đang mở:** HTML và JavaScript đã tải vào từng tab. Một tab có thể tiếp tục chạy mã cũ trong bộ nhớ.
- **Phiên bản Service Worker active:** worker đang điều khiển các client trong scope và xử lý fetch event của chúng.
- **Phiên bản Service Worker waiting:** worker mới đã cài đặt thành công nhưng đang chờ worker cũ nhường quyền điều khiển.

Việc cập nhật file sw.js trên máy chủ không đồng nghĩa mọi tab lập tức chạy ứng dụng mới. Trình duyệt cần kiểm tra script, cài đặt worker mới và xử lý trạng thái waiting/activation. Sau đó, ứng dụng có thể cần tải lại trang để dùng HTML và asset của bản phát hành mới.

Một lần cập nhật được vận hành tốt phải bảo đảm các thành phần tương thích trong khoảng thời gian mà tab cũ và worker mới có thể cùng tồn tại.

## 2. Vòng đời cập nhật của Service Worker

### 2.1. Các trạng thái chính

| Trạng thái | Ý nghĩa | Điều cần quan sát |
|---|---|---|
| installing | Worker mới đang chạy install event | Tải tài nguyên precache và chuẩn bị dữ liệu |
| installed | Worker đã cài đặt xong; với bản cập nhật, thường ở trạng thái waiting | Worker cũ vẫn có thể đang điều khiển các tab |
| activating | Worker mới đang chạy activate event | Dọn cache cũ, migration và chuẩn bị nhận client |
| activated | Worker đã active | Có thể xử lý fetch và các sự kiện thuộc vòng đời |
| redundant | Worker không còn được sử dụng | Cài đặt thất bại, bị thay thế hoặc registration bị hủy |

Khi cài lần đầu, không có worker cũ điều khiển trang nên worker mới thường chuyển sang activate sau khi install thành công. Khi cập nhật một registration đang hoạt động, worker mới thường chờ đến khi không còn client do worker cũ điều khiển.

Một worker mới không thể chuyển sang active nếu install event thất bại. Ví dụ, cache.addAll() có thể reject khi một URL precache trả 404 hoặc response không hợp lệ. Khi đó worker mới trở thành redundant và worker cũ tiếp tục hoạt động.

### 2.2. Trình tự cập nhật

~~~mermaid
flowchart TD
    A["Trình duyệt kiểm tra script"] --> B{"Script hoặc import thay đổi?"}
    B -- "Không" --> C["Giữ registration hiện tại"]
    B -- "Có" --> D["Tạo worker mới: installing"]
    D --> E["Chạy install và precache"]
    E --> F{"Install thành công?"}
    F -- "Không" --> G["Worker mới redundant; worker cũ tiếp tục"]
    F -- "Có" --> H["Worker mới installed / waiting"]
    H --> I{"Worker cũ còn client?"}
    I -- "Có" --> J["Tiếp tục chờ hoặc dùng skipWaiting"]
    I -- "Không" --> K["activate event"]
    J --> K
    K --> L["Dọn cache và migration"]
    L --> M["Worker mới activated"]
    M --> N["Client dùng controller mới khi phù hợp"]
~~~

Quy trình cập nhật thông thường:

1. Trình duyệt kiểm tra URL script của registration.
2. Nếu phát hiện nội dung script mới, trình duyệt tạo worker mới và chạy install event.
3. Worker mới tải hoặc chuẩn bị tài nguyên cần thiết. Nếu install thất bại, worker mới không thay worker active.
4. Khi install thành công, worker mới ở trạng thái installed. Nếu worker cũ còn điều khiển client, worker mới thường chờ.
5. Khi đủ điều kiện, activate event chạy. Worker mới có thể dọn cache cũ và thực hiện migration.
6. Worker mới trở thành active. Trang đang mở có thể cần reload để lấy HTML và asset mới.

Trình duyệt tự quyết định thời điểm kiểm tra update. Có thể có lần kiểm tra khi điều hướng hoặc khi trình duyệt xử lý registration; không nên dựa vào một khoảng thời gian cố định. Ứng dụng có thể gọi registration.update() để yêu cầu kiểm tra, nhưng kết quả vẫn phụ thuộc mạng, chính sách cache và thuật toán cập nhật của trình duyệt.

### 2.3. Khi nào trình duyệt coi script đã thay đổi?

Trình duyệt tải script Service Worker và kiểm tra nội dung của script cùng các script được import theo thuật toán cập nhật. Nếu nội dung không thay đổi theo phép so sánh của trình duyệt, worker mới không được cài chỉ vì tên file hoặc số phiên bản trong cơ sở dữ liệu ứng dụng thay đổi.

Vì vậy:

- Sửa nội dung sw.js hoặc một script được import có thể kích hoạt bản cập nhật.
- Chỉ tăng biến version ở server nhưng không làm thay đổi script được kiểm tra thì không đủ.
- Không nên thêm timestamp ngẫu nhiên vào URL đăng ký mỗi lần tải trang; cách đó có thể tạo nhiều registration hoặc gây cập nhật không cần thiết.
- Hãy dùng release ID hoặc cache version có chủ đích để dễ theo dõi và dọn cache.

## 3. Kiểm tra cập nhật từ trang ứng dụng

### 3.1. Đăng ký Service Worker

Đăng ký worker trong secure context. HTTPS là yêu cầu trên môi trường thật; localhost và loopback được trình duyệt coi là môi trường đáng tin cậy cho phát triển.

~~~javascript
async function registerAppWorker() {
  if (!("serviceWorker" in navigator)) {
    console.warn("Trình duyệt không hỗ trợ Service Worker");
    return null;
  }

  const registration = await navigator.serviceWorker.register("/sw.js", {
    scope: "/",
    updateViaCache: "none"
  });

  console.log("Service Worker scope:", registration.scope);
  return registration;
}
~~~

Scope quyết định các URL nào có thể được worker điều khiển. Mặc định scope bị giới hạn theo thư mục chứa script; nếu cần scope rộng hơn thư mục đó, máy chủ phải cấu hình Service-Worker-Allowed phù hợp. Không mở rộng scope chỉ để tiện triển khai.

Tên và đường dẫn script nên ổn định qua các phiên bản. Nội dung của script thay đổi để kích hoạt update check; không cần đổi URL mỗi lần phát hành.

### 3.2. Theo dõi updatefound và statechange

registration.updatefound được phát khi registration bắt đầu cài một worker mới. registration.installing tham chiếu worker đang cài; statechange cho biết trạng thái của worker đó thay đổi.

~~~javascript
function watchWorkerUpdate(registration) {
  const updateButton = document.querySelector("#apply-update");
  const watchedWorkers = new WeakSet();

  function showWaitingWorker() {
    if (!registration.waiting || !navigator.serviceWorker.controller) {
      return;
    }

    updateButton.hidden = false;
    updateButton.textContent = "Cập nhật ứng dụng";
  }

  function watchWorker(worker) {
    if (!worker || watchedWorkers.has(worker)) {
      return;
    }

    watchedWorkers.add(worker);
    worker.addEventListener("statechange", () => {
      console.log("Worker state:", worker.state);

      if (
        worker.state === "installed" &&
        navigator.serviceWorker.controller
      ) {
        showWaitingWorker();
      }

      if (worker.state === "redundant") {
        console.error("Worker mới không cài đặt thành công");
      }
    });
  }

  registration.addEventListener("updatefound", () => {
    watchWorker(registration.installing);
  });

  watchWorker(registration.installing);
  if (registration.waiting && navigator.serviceWorker.controller) {
    showWaitingWorker();
  }
}
~~~

Điều kiện navigator.serviceWorker.controller giúp phân biệt lần cài đầu với lần cập nhật. Ở lần cài đầu, trang chưa có controller cũ; ứng dụng thường không cần hiển thị nút cập nhật.

Không nên coi state installed luôn có nghĩa là một bản cập nhật đang chờ. Hãy xem registration.waiting và trạng thái controller hiện tại.

### 3.3. Kiểm tra thủ công

Ứng dụng có thể cung cấp nút để người dùng yêu cầu kiểm tra bản mới:

~~~javascript
async function checkForWorkerUpdate(registration) {
  try {
    await registration.update();
    console.log("Đã yêu cầu kiểm tra phiên bản Service Worker");
  } catch (error) {
    console.error("Không thể kiểm tra bản cập nhật:", error);
  }
}

document.querySelector("#check-update").addEventListener("click", () => {
  checkForWorkerUpdate(registration);
});
~~~

registration.update() không đồng nghĩa worker mới chắc chắn được cài. Nếu script chưa thay đổi, mạng lỗi hoặc máy chủ trả nội dung cũ do cache, registration vẫn giữ phiên bản hiện tại.

Không gọi update() liên tục theo vòng lặp ngắn. Có thể kiểm tra khi người dùng mở mục thông tin phiên bản, sau khi đăng nhập hoặc theo lịch vận hành hợp lý; tránh tạo lưu lượng và log không cần thiết.

## 4. Waiting, skipWaiting và clients.claim

### 4.1. Vì sao worker mới phải chờ?

Giả sử người dùng mở ba tab:

- Tab A đang chạy HTML và JavaScript của release 10.
- Tab B cũng đang chạy release 10.
- Tab C mở sau đó và đang được worker active của release 10 điều khiển.

Khi release 11 được cài, worker mới thường ở trạng thái waiting. Điều này tránh để một số tab cũ tiếp tục chạy với worker mới trong khi tab khác vẫn đang dùng worker cũ.

Nếu worker mới tự động active khi tab cũ vẫn mở, ứng dụng có thể rơi vào trạng thái trộn phiên bản:

- JavaScript cũ gọi API mới với cấu trúc dữ liệu khác.
- Worker mới chỉ cache asset release 11 nhưng tab cũ vẫn yêu cầu asset release 10.
- Worker mới đổi quy tắc route hoặc response trong khi trang cũ đang chờ một định dạng khác.
- Một lần reload có thể làm mất dữ liệu biểu mẫu chưa lưu.

Cơ chế waiting tạo một điểm đồng bộ. Đội phát triển có thể chờ người dùng đóng tab cũ hoặc chủ động cho phép cập nhật sau khi bảo đảm tương thích.

### 4.2. skipWaiting()

self.skipWaiting() yêu cầu worker đang waiting bỏ qua giai đoạn chờ và chuyển sang quá trình activate sớm hơn. Nó không tự tải lại tất cả trang.

Dùng skipWaiting khi:

- Bản mới tương thích với các client cũ đang mở.
- API và cấu trúc dữ liệu có thể phục vụ cả hai phiên bản trong giai đoạn chuyển tiếp.
- Ứng dụng có thông báo và quy trình reload rõ ràng.
- Đội vận hành chấp nhận việc worker mới có thể bắt đầu xử lý client trong lúc tab cũ còn chạy.

Không gọi skipWaiting() một cách mặc định trong mọi install event. Với ứng dụng có biểu mẫu dài, giao dịch hoặc quy trình nhiều bước, nên cho người dùng hoàn tất hoặc lưu trạng thái trước khi áp dụng bản mới.

### 4.3. clients.claim()

self.clients.claim() trong activate event yêu cầu worker active nhận quyền điều khiển các client phù hợp trong scope mà chưa được điều khiển bởi worker này. Khi controller thay đổi, trang nhận sự kiện controllerchange.

clients.claim() thường được dùng khi muốn worker mới nhanh chóng điều khiển các trang đang mở trong scope. Nó cần được đánh giá cùng skipWaiting và cách reload của ứng dụng.

Hai API có vai trò khác nhau:

| API | Tác động |
|---|---|
| skipWaiting() | Cho worker đang waiting chuyển sang activate sớm |
| clients.claim() | Cho worker active nhận quyền điều khiển các client phù hợp trong scope |
| controllerchange | Sự kiện ở trang khi controller của trang thay đổi |

Gọi clients.claim() không tự reload trang và không bảo đảm mã JavaScript trong trang được tải lại. Ứng dụng phải quyết định khi nào reload, lưu trạng thái và thông báo cho người dùng.

### 4.4. Quy trình cập nhật do người dùng xác nhận

Một mô hình phổ biến là:

1. Trang phát hiện registration.waiting.
2. Giao diện thông báo có bản cập nhật và nêu ảnh hưởng.
3. Người dùng lưu công việc hoặc xác nhận cập nhật.
4. Trang gửi message có loại lệnh cố định đến worker waiting.
5. Worker gọi skipWaiting().
6. Worker chạy activate, dọn cache theo chính sách và gọi clients.claim() nếu thiết kế yêu cầu.
7. Trang nhận controllerchange và reload một lần khi đã được người dùng cho phép.

Ví dụ phía trang:

~~~javascript
let reloadAfterActivation = false;

navigator.serviceWorker.addEventListener("controllerchange", () => {
  if (!reloadAfterActivation) {
    return;
  }

  reloadAfterActivation = false;
  window.location.reload();
});

document.querySelector("#apply-update").addEventListener("click", () => {
  const waitingWorker = registration.waiting;

  if (!waitingWorker) {
    return;
  }

  reloadAfterActivation = true;
  waitingWorker.postMessage({ type: "SKIP_WAITING" });
});
~~~

Ví dụ phía Service Worker:

~~~javascript
self.addEventListener("message", (event) => {
  if (!event.data || event.data.type !== "SKIP_WAITING") {
    return;
  }

  event.waitUntil(self.skipWaiting());
});
~~~

Trong ứng dụng thật, nút cập nhật chỉ nên xuất hiện khi có worker waiting. Cần ngăn bấm lặp, xử lý trường hợp worker đã chuyển trạng thái và tránh reload khi người dùng còn dữ liệu chưa lưu.

## 5. Cấu trúc Service Worker theo phiên bản

### 5.1. Đặt tên cache có namespace

Cache Storage thuộc origin và có thể được nhiều Service Worker hoặc ứng dụng cùng origin sử dụng. Không nên xóa mọi cache trong activate event.

Dùng prefix riêng cho ứng dụng và gắn release ID vào tên cache:

~~~javascript
const CACHE_PREFIX = "portal-shell-";
const CACHE_NAME = CACHE_PREFIX + "release-12";

const PRECACHE_URLS = [
  "/offline.html",
  "/assets/app.4d19a.js",
  "/assets/app.8b2f1.css"
];
~~~

Tên asset có hash hoặc release ID giúp phân biệt file bất biến giữa các bản. Nếu cùng một URL nhưng nội dung thay đổi, cache cũ có thể tiếp tục trả nội dung không mong muốn.

### 5.2. Install: chuẩn bị tài nguyên trước khi activate

~~~javascript
self.addEventListener("install", (event) => {
  event.waitUntil((async () => {
    const cache = await caches.open(CACHE_NAME);
    await cache.addAll(PRECACHE_URLS);
  })());
});
~~~

cache.addAll() chỉ hoàn tất khi các request trong danh sách thành công theo điều kiện của Cache API. Nếu một asset chưa được deploy, trả 404 hoặc không thể lưu, install có thể thất bại.

Do đó, phải bảo đảm tất cả asset mà worker mới cần đã tồn tại trên máy chủ trước khi phát hành script worker mới. Với ứng dụng lớn, có thể tải và kiểm tra tài nguyên theo từng nhóm, nhưng phải xác định rõ điều kiện để install được xem là thành công.

Không precache dữ liệu cá nhân, response có token hoặc nội dung tài khoản chỉ để hỗ trợ offline. CacheStorage không phải kho bí mật; dữ liệu có thể tồn tại trên thiết bị và bị đọc bởi script cùng origin có quyền phù hợp.

### 5.3. Activate: dọn cache cũ có giới hạn

~~~javascript
self.addEventListener("activate", (event) => {
  event.waitUntil((async () => {
    const cacheNames = await caches.keys();

    await Promise.all(
      cacheNames
        .filter((name) =>
          name.startsWith(CACHE_PREFIX) && name !== CACHE_NAME
        )
        .map((name) => caches.delete(name))
    );

    await self.clients.claim();
  })());
});
~~~

Chỉ xóa cache thuộc namespace của ứng dụng. Một origin có thể chứa nhiều ứng dụng con hoặc nhiều worker; xóa tất cả cache có thể phá hỏng ứng dụng khác.

Dọn cache cũ cũng cần phối hợp với vòng đời client. Nếu tab cũ còn tham chiếu asset cũ, việc xóa cache cũ có thể khiến asset đó phải tải lại từ máy chủ. Máy chủ cần giữ các asset có hash cũ đủ lâu để client cũ vẫn hoạt động.

Với hệ thống có nhiều phiên bản cùng tồn tại, có thể trì hoãn dọn cache cho đến khi không còn client dùng release cũ, hoặc giữ một số cache cũ theo chính sách dung lượng. Không xóa cache chỉ dựa trên giả định rằng mọi tab đã reload.

### 5.4. Chọn chiến lược fetch phù hợp

Không nên dùng một chiến lược cache cho mọi loại request.

| Loại tài nguyên | Chiến lược thường phù hợp | Lưu ý vận hành |
|---|---|---|
| Asset tĩnh có hash | Cache-first | URL đổi theo nội dung; giữ file cũ trên server |
| HTML điều hướng | Network-first hoặc không cache | Tránh trang cũ tham chiếu asset đã xóa |
| API tài khoản | Network-only | Không lưu response riêng tư vào cache chung |
| Request POST/PUT/PATCH/DELETE | Không cache | Không phát lại thao tác thay đổi trạng thái |
| Trang offline | Precache | Nội dung tĩnh, không chứa thông tin người dùng |
| Dữ liệu công khai ít thay đổi | Stale-while-revalidate nếu có yêu cầu rõ | Xác định thời hạn và khả năng chấp nhận dữ liệu cũ |

Ví dụ chỉ cache asset tĩnh có version trong URL, bỏ qua API và request khác origin:

~~~javascript
self.addEventListener("fetch", (event) => {
  const request = event.request;
  const url = new URL(request.url);

  if (
    request.method !== "GET" ||
    url.origin !== self.location.origin ||
    !url.pathname.startsWith("/assets/")
  ) {
    return;
  }

  event.respondWith((async () => {
    const cache = await caches.open(CACHE_NAME);
    const cached = await cache.match(request);

    if (cached) {
      return cached;
    }

    const response = await fetch(request);

    if (response.ok && response.type === "basic") {
      await cache.put(request, response.clone());
    }

    return response;
  })());
});
~~~

Ví dụ navigation network-first với offline fallback:

~~~javascript
self.addEventListener("fetch", (event) => {
  const request = event.request;

  if (request.method !== "GET" || request.mode !== "navigate") {
    return;
  }

  event.respondWith((async () => {
    try {
      return await fetch(request);
    } catch {
      const cache = await caches.open(CACHE_NAME);
      return (await cache.match("/offline.html")) || Response.error();
    }
  })());
});
~~~

Hai ví dụ là các nhánh có thể ghép vào cùng một fetch listener. Nếu kết hợp, chỉ gọi event.respondWith() một lần cho mỗi request và xác định thứ tự route rõ ràng. Không cache response API hoặc trang đã xác thực nếu chưa có thiết kế phân vùng dữ liệu, quyền riêng tư và hết hạn.

## 6. Cache header và kiểm tra phiên bản script

### 6.1. Không để sw.js bị CDN giữ quá lâu

Nếu HTTP cache hoặc CDN phục vụ mã Service Worker cũ, trình duyệt có thể không thấy bản cập nhật đúng lúc. Nên cấu hình URL script worker để có thể revalidate thường xuyên.

Một response header thường dùng cho sw.js:

~~~http
Cache-Control: no-cache
Content-Type: application/javascript; charset=utf-8
~~~

no-cache cho phép lưu response nhưng yêu cầu kiểm tra lại trước khi dùng theo quy tắc HTTP cache. Có thể dùng updateViaCache để điều chỉnh cách trình duyệt dùng HTTP cache cho script chính và các script được import.

### 6.2. updateViaCache

Khi đăng ký worker, updateViaCache có ba giá trị:

| Giá trị | Cách dùng HTTP cache khi kiểm tra update |
|---|---|
| imports | Mặc định; script Service Worker chính được kiểm tra không qua HTTP cache, các script import có thể dùng HTTP cache |
| all | Script chính và các script import có thể dùng HTTP cache |
| none | Bỏ qua HTTP cache cho script chính và các script import |

Ví dụ:

~~~javascript
navigator.serviceWorker.register("/sw.js", {
  scope: "/",
  updateViaCache: "none"
});
~~~

none hữu ích khi cần tránh phụ thuộc bản import cũ đang nằm trong HTTP cache, nhưng không thay thế việc cấu hình CDN, cache header và quy trình phát hành đúng. Không chọn giá trị này theo thói quen nếu hệ thống có nhiều script lớn và đã có cơ chế cache hợp lý.

### 6.3. Script được import

Nếu Service Worker dùng importScripts() hoặc module import, các file đó cũng cần được phát hành và kiểm soát như một phần của release.

- Giữ URL import ổn định hoặc có version rõ ràng.
- Đặt cache header phù hợp với updateViaCache.
- Đảm bảo file import có sẵn trước khi worker mới cài đặt.
- Không tải mã thực thi từ nguồn không được kiểm soát.
- Kiểm tra nội dung và quyền thay đổi các file import trong pipeline phát hành.

Một worker script mới nhưng import script cũ có thể tạo ra một tổ hợp logic không như mong đợi. Hãy kiểm thử cả graph script, không chỉ file sw.js.

## 7. Quy trình phát hành bản cập nhật

### 7.1. Chuẩn bị release

Trước khi deploy:

1. Tạo release ID và ghi lại commit hoặc artifact tương ứng.
2. Build các asset tĩnh với tên có hash nội dung.
3. Kiểm tra precache manifest và xác minh mọi URL tồn tại.
4. Kiểm thử install event trong môi trường staging.
5. Kiểm tra tương thích giữa worker mới, HTML, JavaScript và API.
6. Xác định có dùng waiting để người dùng xác nhận hay dùng skipWaiting.
7. Chuẩn bị cách theo dõi lỗi và rollback.

Không dùng số phiên bản trong giao diện làm bằng chứng duy nhất về nội dung đang chạy. Ghi release ID riêng cho worker, ứng dụng và API để có thể đối chiếu.

### 7.2. Thứ tự triển khai

Một trình tự triển khai an toàn thường gồm:

- Đưa asset mới có hash lên máy chủ trước.
- Xác minh các asset mới trả đúng status, MIME type và nội dung.
- Phát hành Service Worker script mới cùng precache list tương ứng.
- Đưa HTML hoặc entrypoint mới vào phục vụ theo kế hoạch release.
- Giữ các asset cũ trong thời gian chuyển tiếp để tab cũ không bị 404.
- Theo dõi tỷ lệ install thành công, waiting, activation và lỗi tải asset.

Trong thời gian chuyển tiếp, worker cũ và trang cũ có thể vẫn tồn tại. API và asset server nên tương thích ngược đủ lâu để cả client cũ lẫn mới hoạt động. Nếu thay đổi schema hoặc endpoint không tương thích, hãy triển khai theo nhiều giai đoạn thay vì buộc mọi tab chuyển cùng lúc.

### 7.3. Chọn chính sách kích hoạt

| Loại ứng dụng | Chính sách thường phù hợp |
|---|---|
| Trang thông tin công khai, không có thao tác đang lưu | Có thể tự động kích hoạt nếu app tương thích |
| Dashboard có biểu mẫu hoặc dữ liệu chưa lưu | Hiển thị thông báo, cho người dùng lưu rồi xác nhận |
| Ứng dụng giao dịch hoặc quản trị | Chờ điểm an toàn, có thể yêu cầu xác nhận và kiểm tra trạng thái phiên |
| Ứng dụng cần cập nhật bảo mật khẩn cấp | Có thể dùng skipWaiting sau khi đánh giá tương thích, kết hợp reload có kiểm soát |
| Ứng dụng hỗ trợ offline dài hạn | Cần giữ asset cũ và chiến lược migration rõ ràng |

Không có một chính sách duy nhất phù hợp cho mọi ứng dụng. Quyết định phải dựa trên tác động của việc thay worker trong khi các tab còn mở.

## 8. Migration dữ liệu và tương thích ngược

Service Worker update có thể đi kèm thay đổi IndexedDB, CacheStorage hoặc cấu trúc dữ liệu mà ứng dụng lưu trên thiết bị. Migration cần có kế hoạch riêng vì nhiều tab và worker có thể hoạt động ở thời điểm khác nhau.

### 8.1. IndexedDB

Khi thay đổi schema IndexedDB, version upgrade có thể phát sinh sự kiện blocked nếu tab khác đang giữ kết nối database cũ. Ứng dụng nên:

- Lắng nghe versionchange và đóng kết nối database khi được yêu cầu.
- Hiển thị thông báo cho tab cũ nếu cần reload.
- Giữ migration có thể chạy lại an toàn khi có lỗi.
- Không xóa store hoặc dữ liệu người dùng nếu chưa có chính sách lưu trữ và khôi phục.
- Kiểm thử trường hợp hai tab mở ở hai phiên bản ứng dụng khác nhau.

Worker mới không tự động bảo đảm mọi trang đã nâng schema. Nếu migration chạy trong activate, hãy đánh giá thời gian, khả năng bị gián đoạn và tương thích với các tab cũ.

### 8.2. CacheStorage

CacheStorage không có transaction chung cho nhiều cache theo nghĩa migration ứng dụng. Hãy tạo cache mới, điền đủ tài nguyên, rồi mới chuyển worker sang dùng cache đó. Nếu install thất bại, worker cũ vẫn có thể tiếp tục dùng cache cũ.

Không ghi đè cache đang được phiên bản cũ sử dụng bằng nội dung mới có cùng URL nếu ứng dụng cần bảo đảm tính nhất quán. Dùng tên file có hash hoặc cache version để tách nội dung.

### 8.3. Tương thích API

Trong giai đoạn rollout:

- API mới nên chấp nhận payload của client cũ nếu có thể.
- Client mới nên xử lý response từ server cũ trong khoảng chuyển tiếp.
- Không xóa endpoint cũ ngay khi phát hành worker mới.
- Có telemetry để biết client release nào còn hoạt động.
- Chỉ bỏ tương thích cũ sau khi thời gian hỗ trợ và số lượng client cũ đạt điều kiện vận hành.

## 9. Rollback và xử lý sự cố cập nhật

### 9.1. Rollback Service Worker

Nếu release mới gây lỗi:

1. Xác định release ID của worker và asset đang gây lỗi.
2. Chuẩn bị một bản worker đã biết là tốt, có thể dùng cache namespace và quy tắc fetch an toàn.
3. Deploy asset cần thiết trước khi deploy worker rollback.
4. Phát hành script worker rollback với nội dung khác worker đang active để trình duyệt nhận ra bản mới.
5. Theo dõi update check, install, waiting và activation.
6. Nếu cần skipWaiting, xác minh tương thích với các tab còn mở và chuẩn bị reload.
7. Giữ asset cũ đủ lâu để client không bị lỗi 404.
8. Xác minh tỷ lệ lỗi và phiên bản controller sau rollback.

Trình duyệt không dựa vào số phiên bản semver để quyết định worker mới hơn hay cũ hơn. Nó kiểm tra nội dung script theo thuật toán update. Vì vậy, rollback là một lần phát hành worker có nội dung khác với worker hiện tại; hãy ghi release ID để con người theo dõi.

Không chỉ đổi số phiên bản trong backend rồi kỳ vọng trình duyệt tự quay về worker cũ. Script cần được phục vụ qua URL registration và update check phải nhìn thấy nội dung rollback.

### 9.2. Install thất bại

Dấu hiệu:

- Worker mới chuyển redundant.
- install event reject hoặc có lỗi trong DevTools.
- Một URL trong precache trả 404, redirect không mong đợi hoặc lỗi mạng.
- Cache quota hoặc storage có thể không đủ.

Cách xử lý:

- Kiểm tra request tài nguyên trong Network và worker console.
- Xác minh toàn bộ URL precache có sẵn và trả status hợp lệ.
- Kiểm tra MIME type, redirect, CSP và quyền truy cập.
- Giữ worker cũ và cache cũ hoạt động trong khi sửa bản phát hành.
- Tạo release mới đã sửa lỗi và chạy lại kiểm thử.

### 9.3. Worker mới active nhưng ứng dụng lỗi

Dấu hiệu:

- Tab reload liên tục sau controllerchange.
- Trang mới không tải được asset do cache hoặc server thiếu file.
- API trả lỗi do payload client/server không tương thích.
- Offline fallback trả trang sai hoặc chứa nội dung cũ.
- Một số tab hoạt động, tab khác bị lỗi theo release.

Cách xử lý:

- Ghi nhận controller script URL, release ID và client URL.
- Kiểm tra cache name, asset hash và response status.
- Kiểm tra controllerchange handler có reload lặp hay không.
- Xác minh server còn giữ asset cũ.
- Kiểm tra migration IndexedDB và dữ liệu được lưu trong cache.
- Triển khai worker rollback hoặc hotfix theo quy trình phát hành.

### 9.4. Gỡ bỏ Service Worker

Không nên chỉ xóa file sw.js khỏi máy chủ và cho rằng worker đã ngừng hoạt động. Worker active có thể tiếp tục điều khiển các client hiện tại.

Nếu cần ngừng hỗ trợ:

- Phát hành một worker cuối cùng có hành vi tối giản và rõ ràng.
- Trong activate, chỉ dọn cache thuộc namespace của ứng dụng.
- Có thể gọi registration.unregister() để hủy registration.
- Giữ trang và asset cần thiết trên server trong thời gian client cũ đóng hoặc điều hướng lại.
- Kiểm tra các tab đang mở và trạng thái controller trước khi kết thúc vận hành.

unregister() ngăn registration tiếp tục được sử dụng cho các lần điều khiển mới, nhưng không nên giả định nó lập tức dừng mọi worker đang phục vụ client hiện tại. Cần kiểm thử quy trình retire trên các trình duyệt mục tiêu.

## 10. Giám sát sau phát hành

### 10.1. Chỉ số nên theo dõi

| Chỉ số | Dấu hiệu cần chú ý |
|---|---|
| Update check | Lần kiểm tra không thành công, script không cập nhật |
| Install success rate | Tỷ lệ worker mới cài đặt thành công |
| Waiting duration | Worker chờ quá lâu so với kỳ vọng |
| Activation rate | Worker đã cài nhưng không chuyển sang active |
| Precache failure | Asset thiếu, lỗi mạng, quota hoặc MIME sai |
| Controller version | Release worker đang điều khiển trang |
| Asset 404 | Tab cũ yêu cầu asset đã bị xóa |
| Reload failure | Trang lỗi sau controllerchange hoặc reload lặp |
| Offline fallback | Tỷ lệ và lỗi khi chuyển sang trang offline |
| API compatibility | Lỗi tăng theo release của client hoặc worker |

Không ghi cookie, token, nội dung biểu mẫu hoặc URL query có dữ liệu cá nhân vào telemetry. Chỉ thu thập release ID, trạng thái, loại lỗi, browser/version và thông tin kỹ thuật tối thiểu.

### 10.2. Ghi nhận phiên bản trong worker

Có thể khai báo release ID trong script để dễ đối chiếu:

~~~javascript
const WORKER_RELEASE = "portal-2026.11.22.3";

self.addEventListener("message", (event) => {
  if (event.data?.type === "GET_WORKER_RELEASE") {
    event.ports[0]?.postMessage({ release: WORKER_RELEASE });
  }
});
~~~

Trang có thể gửi message đến controller để lấy release ID đang xử lý. Hãy xác thực loại message và không đưa dữ liệu người dùng vào message chỉ để phục vụ telemetry.

Release ID trong worker giúp xác định code đang chạy; nó không thay thế việc kiểm tra registration.active, registration.waiting và controller của từng tab.

## 11. Lab: kiểm tra Service Worker update trên localhost

Lab này tạo một ứng dụng tĩnh và Service Worker trên loopback. Bạn sẽ cài release 1, phát hành release 2, quan sát waiting, xác nhận cập nhật và thử rollback. Chỉ dùng dữ liệu giả.

### 11.1. Cấu trúc thư mục

Tạo thư mục tạm với cấu trúc:

~~~text
service-worker-lab/
  server.js
  public/
    index.html
    register.js
    sw.js
    offline.html
    assets/
      app-v1.js
~~~

### 11.2. Máy chủ static tối giản

Tạo server.js:

~~~javascript
const http = require("node:http");
const fs = require("node:fs");
const path = require("node:path");

const ROOT = path.join(__dirname, "public");

const files = new Map([
  ["/", "index.html"],
  ["/index.html", "index.html"],
  ["/register.js", "register.js"],
  ["/sw.js", "sw.js"],
  ["/offline.html", "offline.html"],
  ["/assets/app-v1.js", "assets/app-v1.js"],
  ["/assets/app-v2.js", "assets/app-v2.js"]
]);

const contentTypes = {
  ".html": "text/html; charset=utf-8",
  ".js": "application/javascript; charset=utf-8"
};

const server = http.createServer((req, res) => {
  const url = new URL(req.url, "http://127.0.0.1:8080");
  const relativePath = files.get(url.pathname);

  if (!relativePath || req.method !== "GET") {
    res.writeHead(404, { "Cache-Control": "no-store" });
    res.end("Not found");
    return;
  }

  const filePath = path.join(ROOT, relativePath);

  fs.readFile(filePath, (error, data) => {
    if (error) {
      res.writeHead(404, { "Cache-Control": "no-store" });
      res.end("File not found");
      return;
    }

    const isVersionedAsset = url.pathname.startsWith("/assets/");
    const headers = {
      "Content-Type": contentTypes[path.extname(filePath)] || "application/octet-stream",
      "Cache-Control": isVersionedAsset
        ? "public, max-age=31536000, immutable"
        : "no-cache"
    };

    res.writeHead(200, headers);
    res.end(data);
  });
});

server.listen(8080, "127.0.0.1", () => {
  console.log("Lab: http://127.0.0.1:8080/");
});
~~~

Máy chủ chỉ lắng nghe trên loopback và chỉ phục vụ những đường dẫn có trong allowlist. Không mở máy chủ lab ra mạng công cộng.

### 11.3. Trang ứng dụng

Tạo public/index.html:

~~~html
<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Service Worker update lab</title>
</head>
<body>
  <h1>Service Worker update lab</h1>
  <p>Ứng dụng: <strong id="app-version">đang tải...</strong></p>
  <p>Worker: <strong id="worker-state">chưa kiểm tra</strong></p>
  <button id="check-update">Kiểm tra bản mới</button>
  <button id="apply-update" hidden>Cập nhật ứng dụng</button>
  <pre id="log"></pre>
  <script src="/assets/app-v1.js" defer></script>
  <script src="/register.js" defer></script>
</body>
</html>
~~~

Tạo public/assets/app-v1.js:

~~~javascript
document.querySelector("#app-version").textContent = "release 1";
~~~

Tạo public/offline.html:

~~~html
<!doctype html>
<html lang="vi">
<head><meta charset="utf-8"><title>Offline</title></head>
<body>
  <h1>Đang ngoại tuyến</h1>
  <p>Không thể tải trang từ máy chủ. Hãy kết nối lại và thử lại.</p>
</body>
</html>
~~~

### 11.4. Đăng ký và theo dõi update

Tạo public/register.js:

~~~javascript
(async () => {
  const log = document.querySelector("#log");
  const state = document.querySelector("#worker-state");
  const checkButton = document.querySelector("#check-update");
  const applyButton = document.querySelector("#apply-update");

  let registration;
  let reloadAfterActivation = false;

  function writeLog(message) {
    log.textContent += message + "\n";
  }

  function showWaitingUpdate() {
    if (registration?.waiting && navigator.serviceWorker.controller) {
      applyButton.hidden = false;
      state.textContent = "Có bản cập nhật đang chờ";
    }
  }

  try {
    registration = await navigator.serviceWorker.register("/sw.js", {
      scope: "/",
      updateViaCache: "none"
    });

    writeLog("Scope: " + registration.scope);

    registration.addEventListener("updatefound", () => {
      const worker = registration.installing;
      if (!worker) return;

      worker.addEventListener("statechange", () => {
        state.textContent = worker.state;
        writeLog("Worker state: " + worker.state);

        if (
          worker.state === "installed" &&
          navigator.serviceWorker.controller
        ) {
          showWaitingUpdate();
        }
      });
    });

    if (registration.waiting && navigator.serviceWorker.controller) {
      showWaitingUpdate();
    }

    checkButton.addEventListener("click", async () => {
      try {
        await registration.update();
        writeLog("Đã yêu cầu kiểm tra update");
        showWaitingUpdate();
      } catch (error) {
        writeLog("Update check lỗi: " + error.message);
      }
    });

    applyButton.addEventListener("click", () => {
      const waiting = registration.waiting;
      if (!waiting) return;

      reloadAfterActivation = true;
      waiting.postMessage({ type: "SKIP_WAITING" });
    });

    navigator.serviceWorker.addEventListener("controllerchange", () => {
      writeLog("Controller đã thay đổi");

      if (reloadAfterActivation) {
        reloadAfterActivation = false;
        window.location.reload();
      }
    });
  } catch (error) {
    state.textContent = "Đăng ký thất bại";
    writeLog("Service Worker lỗi: " + error.message);
  }
})();
~~~

### 11.5. Service Worker release 1

Tạo public/sw.js:

~~~javascript
const CACHE_PREFIX = "sw-update-lab-";
const CACHE_NAME = CACHE_PREFIX + "release-1";

const PRECACHE_URLS = [
  "/offline.html",
  "/assets/app-v1.js"
];

self.addEventListener("install", (event) => {
  event.waitUntil((async () => {
    const cache = await caches.open(CACHE_NAME);
    await cache.addAll(PRECACHE_URLS);
  })());
});

self.addEventListener("message", (event) => {
  if (event.data?.type === "SKIP_WAITING") {
    event.waitUntil(self.skipWaiting());
  }
});

self.addEventListener("activate", (event) => {
  event.waitUntil((async () => {
    const names = await caches.keys();

    await Promise.all(
      names
        .filter((name) =>
          name.startsWith(CACHE_PREFIX) && name !== CACHE_NAME
        )
        .map((name) => caches.delete(name))
    );

    await self.clients.claim();
  })());
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  const url = new URL(request.url);

  if (
    request.method !== "GET" ||
    url.origin !== self.location.origin
  ) {
    return;
  }

  if (url.pathname.startsWith("/assets/")) {
    event.respondWith((async () => {
      const cache = await caches.open(CACHE_NAME);
      const cached = await cache.match(request);

      if (cached) return cached;

      const response = await fetch(request);

      if (response.ok && response.type === "basic") {
        await cache.put(request, response.clone());
      }

      return response;
    })());
    return;
  }

  if (request.mode === "navigate") {
    event.respondWith((async () => {
      try {
        return await fetch(request);
      } catch {
        const cache = await caches.open(CACHE_NAME);
        return (await cache.match("/offline.html")) || Response.error();
      }
    })());
  }
});
~~~

### 11.6. Chạy release 1

Trong terminal tại thư mục service-worker-lab:

~~~powershell
node .\server.js
~~~

Mở http://127.0.0.1:8080/. Mở DevTools và kiểm tra Application hoặc Storage > Service Workers tùy trình duyệt.

Xác minh:

1. Trang hiển thị release 1.
2. Registration có scope /.
3. Worker cài đặt và chuyển sang activated.
4. Cache Storage có cache sw-update-lab-release-1.
5. Asset app-v1.js có trong cache.
6. Reload trang và kiểm tra controller.

### 11.7. Phát hành release 2

Tạo public/assets/app-v2.js:

~~~javascript
document.querySelector("#app-version").textContent = "release 2";
~~~

Sửa public/index.html để script ứng dụng trỏ đến:

~~~html
<script src="/assets/app-v2.js" defer></script>
~~~

Sửa public/sw.js:

- Đổi CACHE_NAME thành sw-update-lab-release-2.
- Thay /assets/app-v1.js trong PRECACHE_URLS bằng /assets/app-v2.js.
- Giữ nguyên URL /sw.js và scope.

Trình tự thực hành:

1. Tạo app-v2.js trước.
2. Cập nhật index.html và xác minh file mới được phục vụ.
3. Cập nhật sw.js sau cùng.
4. Quay lại tab release 1 và bấm Kiểm tra bản mới.
5. Quan sát updatefound và state installed.
6. Xác minh registration.waiting tồn tại.
7. Bấm Cập nhật ứng dụng.
8. Quan sát activate và controllerchange.
9. Trang reload và hiển thị release 2.
10. Kiểm tra cache mới và trạng thái worker.

Trong lab, worker mới dùng skipWaiting theo thao tác người dùng và clients.claim trong activate. Đây là lựa chọn có chủ đích để quan sát chuyển trạng thái. Ứng dụng thật cần đánh giá dữ liệu chưa lưu và tương thích giữa các tab trước khi dùng cách này.

### 11.8. Thử rollback

Để mô phỏng rollback:

1. Giữ public/assets/app-v1.js trên máy chủ và khôi phục public/index.html để tham chiếu app-v1.js.
2. Tạo script worker rollback có nội dung khác worker release 2, dùng cache namespace release-1-rollback và precache app-v1.js.
3. Phục vụ asset và HTML rollback trước, sau đó phát hành sw.js rollback.
4. Quay lại tab release 2 và yêu cầu kiểm tra update.
5. Quan sát worker rollback chuyển installing rồi waiting.
6. Xác nhận cập nhật sau khi tab đã sẵn sàng.
7. Kiểm tra trang reload hiển thị release 1, asset cũ tải được và ứng dụng hoạt động.

Không chỉ thay chuỗi version nếu nội dung worker không thay đổi. Hãy bảo đảm nội dung script thực sự khác worker đang active để update algorithm nhận diện bản mới.

### 11.9. Thử install thất bại

1. Tạm đổi một URL trong PRECACHE_URLS thành đường dẫn không tồn tại.
2. Thay đổi nội dung sw.js để tạo một bản update mới.
3. Bấm Kiểm tra bản mới.
4. Xem worker chuyển redundant sau khi install thất bại.
5. Xác minh worker active cũ vẫn điều khiển trang.
6. Khôi phục URL chính xác và phát hành lại worker đã sửa.

Kết quả mong đợi: worker mới không thay worker cũ khi install thất bại. Ghi lại lỗi request trong Network và lỗi install trong console của Service Worker.

## 12. Ma trận kiểm thử vận hành

| ID | Tình huống | Kết quả mong đợi |
|---|---|---|
| SWU-01 | Cài lần đầu | Worker install và activate thành công |
| SWU-02 | Script không thay đổi | Không tạo worker version mới |
| SWU-03 | Script thay đổi | updatefound xuất hiện, worker mới bắt đầu installing |
| SWU-04 | Precache thành công | Worker chuyển installed và chờ nếu worker cũ còn client |
| SWU-05 | Precache có URL 404 | Worker mới redundant; worker cũ vẫn active |
| SWU-06 | Đóng mọi tab cũ | Worker waiting có thể chuyển activate |
| SWU-07 | Gọi skipWaiting | Worker waiting chuyển sang quá trình activate |
| SWU-08 | Gọi clients.claim | Worker active nhận client phù hợp trong scope |
| SWU-09 | controllerchange | Trang nhận sự kiện khi controller thay đổi |
| SWU-10 | Nhiều tab có dữ liệu chưa lưu | Không reload ngoài ý muốn; dữ liệu được giữ |
| SWU-11 | Asset hash mới | Asset mới được tải và cache đúng release |
| SWU-12 | Asset cũ còn được client yêu cầu | Server vẫn phục vụ asset cũ trong thời gian chuyển tiếp |
| SWU-13 | API request | Không bị cache hoặc phát lại ngoài chủ đích |
| SWU-14 | Offline navigation | Trả offline fallback đã precache |
| SWU-15 | HTTP cache giữ import script cũ | updateViaCache và cache header tạo kết quả như policy |
| SWU-16 | Rollback worker | Worker rollback được nhận diện và cài đặt |
| SWU-17 | Dọn cache | Chỉ cache có namespace của ứng dụng bị xóa |
| SWU-18 | Unregister | Registration bị hủy; client hiện tại được xử lý theo vòng đời thực tế |

## 13. Checklist phát hành

### Trước khi deploy

- [ ] Ghi release ID cho ứng dụng, Service Worker và asset.
- [ ] Xác minh script worker được phục vụ qua HTTPS ở môi trường thật.
- [ ] Xác minh MIME type JavaScript và cache header của sw.js.
- [ ] Kiểm tra scope và Service-Worker-Allowed.
- [ ] Xác minh tất cả URL precache đã có trên server.
- [ ] Kiểm tra asset có tên hash hoặc version rõ ràng.
- [ ] Kiểm thử install và activate trong staging.
- [ ] Kiểm tra worker cũ có tương thích với API và asset mới.
- [ ] Quyết định chính sách waiting, skipWaiting và clients.claim.
- [ ] Chuẩn bị rollback và giữ asset cũ.

### Trong rollout

- [ ] Theo dõi updatefound, installing, waiting và activating.
- [ ] Ghi nhận tỷ lệ install thành công và lỗi precache.
- [ ] Kiểm tra worker active/controller theo release ID.
- [ ] Kiểm tra reload và controllerchange.
- [ ] Theo dõi lỗi 404 của asset cũ và mới.
- [ ] Kiểm tra dữ liệu chưa lưu trước khi reload tab.
- [ ] Theo dõi lỗi API theo phiên bản client.

### Sau deploy

- [ ] Xác nhận người dùng nhận được release mới.
- [ ] Kiểm tra cache namespace và dung lượng.
- [ ] Dọn cache cũ đúng phạm vi.
- [ ] Giữ asset cũ trong thời gian hỗ trợ client cũ.
- [ ] Kiểm tra offline fallback.
- [ ] Kiểm tra không cache dữ liệu riêng tư.
- [ ] Ghi lại kết quả và quyết định rollback/hoàn tất.

## 14. Những hiểu lầm thường gặp

**“Deploy sw.js là mọi tab cập nhật ngay.”** Trình duyệt cần kiểm tra script, cài worker mới và xử lý waiting/activation. Tab đang mở có thể tiếp tục chạy JavaScript cũ.

**“installed nghĩa là worker đã active.”** installed có thể là trạng thái waiting khi worker cũ vẫn điều khiển client.

**“skipWaiting tự reload trang.”** skipWaiting chỉ yêu cầu bỏ qua giai đoạn chờ. Ứng dụng phải xử lý controllerchange và reload nếu cần.

**“clients.claim thay thế skipWaiting.”** Hai API có vai trò khác nhau. Một API thúc đẩy worker waiting chuyển activate; API kia yêu cầu worker active nhận client trong scope.

**“CacheStorage tự hết hạn cache cũ.”** CacheStorage không tự quản lý phiên bản theo logic ứng dụng. Cần đặt tên cache, dọn cache và xử lý quota.

**“Chỉ cần xóa cache cũ khi activate.”** Tab cũ có thể vẫn yêu cầu asset cũ. Phải giữ asset trên server và bảo đảm tương thích trong thời gian chuyển tiếp.

**“registration.update() luôn cài bản mới.”** Hàm này yêu cầu kiểm tra update; script không đổi, cache, mạng hoặc lỗi install vẫn có thể khiến worker không cập nhật.

**“unregister() lập tức dừng mọi client.”** Client đang được điều khiển có thể tiếp tục chạy theo vòng đời hiện tại. Cần kiểm thử quy trình retire.

**“Service Worker là nơi an toàn để lưu token.”** CacheStorage và IndexedDB không phải kho bí mật. Không lưu token hoặc dữ liệu xác thực nhạy cảm nếu không có thiết kế bảo vệ phù hợp.

## 15. Câu hỏi tự kiểm tra

### Câu 1

Một worker mới đã cài đặt thành công nhưng vẫn ở trạng thái installed trong khi tab cũ còn mở. Trạng thái này thường có nghĩa gì?

A. Worker mới đã bị xóa.  
B. Worker mới đang waiting để worker cũ nhường quyền điều khiển.  
C. Máy chủ đã mất kết nối.  
D. CacheStorage bị hỏng.

**Đáp án: B.** Với một registration đang có active worker điều khiển client, worker mới thường chờ đến khi client cũ không còn được điều khiển.

### Câu 2

API nào yêu cầu worker đang waiting bỏ qua giai đoạn chờ?

A. clients.claim().  
B. registration.unregister().  
C. self.skipWaiting().  
D. caches.delete().

**Đáp án: C.** skipWaiting thúc đẩy worker waiting chuyển sang activate sớm hơn.

### Câu 3

Vai trò của clients.claim() là gì?

A. Xóa cache cũ.  
B. Cho worker active nhận quyền điều khiển các client phù hợp trong scope.  
C. Tải lại mọi tab.  
D. Kiểm tra script mới.

**Đáp án: B.** clients.claim() không tự reload trang; controllerchange có thể được phát khi controller thay đổi.

### Câu 4

Nếu cache.addAll() thất bại trong install event, điều gì thường xảy ra?

A. Worker mới vẫn active.  
B. Worker mới cài đặt thất bại và trở thành redundant; worker cũ tiếp tục.  
C. Trình duyệt tự xóa mọi cache.  
D. Mọi tab tự reload.

**Đáp án: B.** install event reject làm worker mới không thể thay worker active.

### Câu 5

Vì sao cần cache name có namespace riêng?

A. Để tăng tốc DNS.  
B. Để chỉ xóa cache của ứng dụng mình khi activate.  
C. Để thay đổi origin.  
D. Để bỏ qua HTTPS.

**Đáp án: B.** CacheStorage dùng chung theo origin; xóa cache không phân biệt có thể phá ứng dụng khác.

### Câu 6

Một trang cũ vẫn yêu cầu app.abc123.js sau khi worker mới active. Cách vận hành phù hợp là gì?

A. Xóa ngay toàn bộ asset cũ.  
B. Giữ asset có hash cũ trên server trong thời gian chuyển tiếp.  
C. Chặn mọi request GET.  
D. Gửi POST để thay file.

**Đáp án: B.** Tab cũ có thể tiếp tục tham chiếu asset cũ cho đến khi reload.

### Câu 7

updateViaCache có giá trị none có ý nghĩa gì?

A. Không sử dụng CacheStorage.  
B. Bỏ qua HTTP cache cho script Service Worker chính và các script import khi kiểm tra update.  
C. Tắt mọi cache của trình duyệt.  
D. Xóa cache API.

**Đáp án: B.** updateViaCache điều chỉnh cách dùng HTTP cache cho script worker và các script import.

### Câu 8

registration.update() bảo đảm điều gì?

A. Luôn kích hoạt worker mới.  
B. Yêu cầu trình duyệt thực hiện kiểm tra update.  
C. Tự động xóa cache cũ.  
D. Tự reload trang.

**Đáp án: B.** Kết quả còn phụ thuộc nội dung script, mạng, cache và điều kiện cập nhật.

### Câu 9

Vì sao skipWaiting tự động có thể gây lỗi?

A. Nó thay đổi scheme của trang.  
B. Worker mới có thể hoạt động trong khi tab cũ vẫn chạy mã ứng dụng cũ.  
C. Nó xóa cookie HttpOnly.  
D. Nó tắt HTTPS.

**Đáp án: B.** Worker mới và client cũ có thể không tương thích về asset, API hoặc cấu trúc dữ liệu.

### Câu 10

Rollback Service Worker cần điều kiện nào để trình duyệt nhận bản rollback?

A. Chỉ thay đổi số phiên bản ở API.  
B. Phục vụ nội dung script khác worker hiện tại và để trình duyệt kiểm tra update.  
C. Xóa mọi file asset.  
D. Đổi tên domain.

**Đáp án: B.** Thuật toán update dựa vào nội dung script, không dựa riêng vào số phiên bản semver.

### Câu 11

Vì sao không nên cache mọi response API trong Service Worker?

A. API không thể dùng GET.  
B. Response có thể chứa dữ liệu riêng tư hoặc phụ thuộc tài khoản và cần chính sách cache riêng.  
C. Cache API chỉ lưu HTML.  
D. CacheStorage không hỗ trợ JSON.

**Đáp án: B.** Chỉ cache dữ liệu công khai hoặc dữ liệu đã có thiết kế phân vùng, hết hạn và quyền riêng tư phù hợp.

### Câu 12

Khi cần retire Service Worker, gọi unregister() có nghĩa gì?

A. Mọi client hiện tại lập tức bị đóng.  
B. Registration được hủy, nhưng client đang được điều khiển có thể tiếp tục theo vòng đời hiện tại.  
C. Máy chủ tự xóa sw.js.  
D. Browser tự xóa toàn bộ CacheStorage của origin.

**Đáp án: B.** Cần phối hợp release cuối, dọn cache có giới hạn và kiểm tra client đang mở.

## 16. Thuật ngữ cần nhớ

| Thuật ngữ | Ý nghĩa |
|---|---|
| Service Worker | Worker do trình duyệt quản lý, xử lý sự kiện và request trong scope |
| Registration | Đăng ký Service Worker gắn với script URL và scope |
| Scope | Phạm vi URL mà worker có thể điều khiển |
| Installing | Trạng thái worker đang cài đặt |
| Waiting | Worker đã cài nhưng đang chờ worker cũ nhường quyền |
| Activating | Worker đang chạy activate event |
| Activated | Worker đã active |
| Redundant | Worker không còn được sử dụng |
| skipWaiting | Yêu cầu worker waiting bỏ qua giai đoạn chờ |
| clients.claim | Yêu cầu worker active nhận client phù hợp trong scope |
| controllerchange | Sự kiện khi controller của trang thay đổi |
| updatefound | Sự kiện registration bắt đầu cài worker mới |
| CacheStorage | API lưu và truy xuất các cache theo origin |
| Precache | Tải và lưu trước tài nguyên trong install |
| updateViaCache | Cấu hình dùng HTTP cache cho script worker và script import |
| Rollback | Phát hành lại một phiên bản đã biết là tốt để khôi phục hoạt động |
| Immutable asset | Tài nguyên có URL gắn với nội dung, không thay đổi tại cùng URL |

## Tài liệu tham khảo

- MDN Web Docs — [Service Worker API](https://developer.mozilla.org/en-US/docs/Web/API/Service_Worker_API): tổng quan kiến trúc và vòng đời Service Worker.
- MDN Web Docs — [ServiceWorkerRegistration.update()](https://developer.mozilla.org/en-US/docs/Web/API/ServiceWorkerRegistration/update): kiểm tra bản cập nhật script.
- MDN Web Docs — [ServiceWorkerRegistration.updateViaCache](https://developer.mozilla.org/en-US/docs/Web/API/ServiceWorkerRegistration/updateViaCache): cách cấu hình HTTP cache cho script worker và script import.
- MDN Web Docs — [ServiceWorkerGlobalScope.skipWaiting()](https://developer.mozilla.org/en-US/docs/Web/API/ServiceWorkerGlobalScope/skipWaiting): bỏ qua giai đoạn waiting.
- MDN Web Docs — [Clients.claim()](https://developer.mozilla.org/en-US/docs/Web/API/Clients/claim): nhận quyền điều khiển client trong scope.
- MDN Web Docs — [ServiceWorkerRegistration.updatefound](https://developer.mozilla.org/en-US/docs/Web/API/ServiceWorkerRegistration/updatefound_event): sự kiện phát hiện worker mới.
- MDN Web Docs — [ServiceWorkerContainer.controllerchange](https://developer.mozilla.org/en-US/docs/Web/API/ServiceWorkerContainer/controllerchange_event): sự kiện thay đổi controller.
- MDN Web Docs — [Cache](https://developer.mozilla.org/en-US/docs/Web/API/Cache): lưu và truy xuất response trong CacheStorage.
- W3C — [Service Workers specification](https://w3c.github.io/ServiceWorker/): thuật toán registration, update và lifecycle.
- web.dev — [The service worker lifecycle](https://web.dev/articles/service-worker-lifecycle): giải thích vòng đời và chiến lược cập nhật.

Các chi tiết lifecycle và chính sách cache có thể khác theo trình duyệt và phiên bản. Khi phát hành, hãy kiểm thử trên các trình duyệt mục tiêu, giữ asset cũ trong thời gian chuyển tiếp và xác minh rollback bằng hành vi thực tế.

