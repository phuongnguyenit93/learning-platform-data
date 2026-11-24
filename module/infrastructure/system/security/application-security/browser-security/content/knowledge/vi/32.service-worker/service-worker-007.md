# Offline data

## 1. Dữ liệu offline trong ứng dụng web là gì?

**Offline data** là dữ liệu ứng dụng lưu trong browser để người dùng tiếp tục xem hoặc chuẩn bị công việc khi mạng chậm, mất kết nối hoặc server tạm thời không truy cập được. Service Worker thường điều phối việc tải tài nguyên và phản hồi request; Cache Storage lưu các cặp Request/Response; IndexedDB lưu dữ liệu có cấu trúc, bản nháp và hàng đợi thao tác cần đồng bộ.

Ví dụ một ứng dụng bán hàng có thể cache HTML/CSS/JavaScript để mở được giao diện khi mất mạng, lưu danh sách sản phẩm công khai để xem lại, và giữ bản nháp đơn hàng trong IndexedDB để gửi khi kết nối trở lại. Ba loại dữ liệu này có yêu cầu khác nhau về độ mới, tính riêng tư, tính toàn vẹn và cách xử lý xung đột.

Offline không có nghĩa browser trở thành nguồn dữ liệu có thẩm quyền. Dữ liệu local có thể cũ, bị người dùng sửa, bị xóa do quota/eviction hoặc không còn phù hợp với tài khoản hiện tại. Server vẫn phải xác thực và kiểm tra quyền khi nhận thao tác đồng bộ. Ứng dụng cần thể hiện rõ dữ liệu nào đang offline, lần cập nhật gần nhất và thao tác nào chưa được server xác nhận.

Bài học này tập trung vào cách thiết kế vòng đời offline data với Service Worker, Cache Storage và IndexedDB; lựa chọn chiến lược cache; cập nhật phiên bản; xử lý quota; bảo vệ dữ liệu riêng tư; và đồng bộ các thay đổi khi mạng trở lại.

### Kết quả học tập

Sau bài này, người học có thể:

1. Phân biệt vai trò của Service Worker, Cache Storage và IndexedDB.
2. Chọn chiến lược cache theo loại dữ liệu và yêu cầu freshness.
3. Thiết kế cache versioning, activation và cleanup an toàn.
4. Xây dựng offline shell và fallback mà không cache nhầm dữ liệu tài khoản.
5. Lưu bản nháp/hàng đợi mutation trong IndexedDB.
6. Đồng bộ lại bằng Background Sync khi được hỗ trợ và có fallback khi không hỗ trợ.
7. Xử lý idempotency, retry, conflict và dữ liệu stale.
8. Quản lý quota, eviction, persistence và trạng thái kết nối.
9. Thiết kế logout, account switching và retention cho dữ liệu offline.
10. Kiểm tra luồng offline/online bằng DevTools và ma trận test.

## 2. Ba thành phần chính và ranh giới của chúng

### 2.1. Service Worker điều phối request

Service Worker là script chạy trong môi trường worker riêng, có thể nhận các event như `install`, `activate`, `fetch`, `message` và `sync` (tùy hỗ trợ browser). Nó có thể can thiệp vào request thuộc scope đã đăng ký và trả response từ network, Cache Storage hoặc một fallback.

Service Worker không phải một tab ẩn chạy liên tục. Browser có thể dừng worker khi không cần và khởi động lại khi event mới đến. Vì vậy, không dựa vào biến global trong Service Worker để giữ trạng thái lâu dài; dữ liệu cần tồn tại qua lần worker bị dừng phải lưu trong Cache Storage hoặc IndexedDB.

Service Worker được đăng ký theo origin và scope. Thông thường cần HTTPS; `localhost` được xem là môi trường đáng tin cậy cho phát triển. File script và scope phải nằm trong phạm vi được phép của origin. Một service worker ở `/app/sw.js` mặc định có scope `/app/`, trừ khi server cho phép scope rộng hơn qua header `Service-Worker-Allowed`.

### 2.2. Cache Storage lưu response

Cache Storage lưu các cặp Request/Response theo tên cache:

```js
const cache = await caches.open("public-assets-v3");
await cache.put(
  "/assets/logo.svg",
  new Response("<svg></svg>", {
    headers: { "Content-Type": "image/svg+xml" }
  })
);

const cached = await cache.match("/assets/logo.svg");
```

Trong ứng dụng thực tế, thường cache response lấy từ network và dùng `response.clone()` vì body stream chỉ tiêu thụ được một lần:

```js
async function fetchAndCache(request) {
  const response = await fetch(request);
  if (response.ok) {
    const cache = await caches.open("public-assets-v3");
    await cache.put(request, response.clone());
  }
  return response;
}
```

Cache Storage phù hợp với asset, app shell và response có cache policy do ứng dụng quản lý. Nó không tự động hết hạn theo một TTL do ứng dụng tưởng tượng ra. Cần chủ động xóa, thay cache version hoặc kiểm tra metadata.

### 2.3. IndexedDB lưu dữ liệu có cấu trúc

IndexedDB là database bất đồng bộ, phù hợp với record, bản nháp, dữ liệu offline và outbox chờ đồng bộ. Ví dụ một bản nháp có thể chứa:

```js
const draftRecord = {
  id: "draft-123",
  accountKey: "account-opaque-7",
  updatedAt: 1790000000000,
  status: "pending",
  payload: {
    title: "Ghi chú công việc",
    body: "Nội dung bản nháp"
  }
};
```

`accountKey` ở đây chỉ là khóa phân vùng dữ liệu phía client, không phải bằng chứng xác thực. Server phải kiểm tra danh tính và quyền khi nhận payload.

### 2.4. Chọn đúng nơi lưu

| Loại dữ liệu | Nơi lưu thường phù hợp | Lý do |
| --- | --- | --- |
| HTML offline shell, CSS, JS, icon | Cache Storage | Là tài nguyên Request/Response, thường được version cùng bản phát hành |
| Ảnh/tài liệu public cần xem offline | Cache Storage | Có thể cache theo URL và policy rõ |
| Record nghiệp vụ cần tìm kiếm/sắp xếp | IndexedDB | Dữ liệu có cấu trúc, truy vấn và cập nhật theo transaction |
| Bản nháp chưa gửi | IndexedDB | Cần lưu bền hơn memory và quản lý trạng thái đồng bộ |
| Mutation đang chờ server xác nhận | IndexedDB outbox | Có thể retry sau khi worker bị dừng hoặc browser offline |
| Session secret/access token | Không đưa vào offline cache/outbox | Tăng nguy cơ lộ credential và replay |
| Trạng thái loading tạm thời | Memory | Không cần lưu qua lần mở ứng dụng |

Service Worker không thể dùng `localStorage` hoặc DOM như một page script. Dùng IndexedDB, Cache Storage và message giữa page/worker để chia sẻ trạng thái cần thiết.

## 3. Xác định yêu cầu offline trước khi cache

Không nên bật offline cho mọi dữ liệu chỉ vì browser cung cấp Cache API. Hãy phân loại theo bốn câu hỏi:

1. Người dùng cần làm gì khi mất mạng: xem, tìm kiếm, soạn thảo hay gửi thay đổi?
2. Dữ liệu có công khai, cá nhân hay bí mật?
3. Dữ liệu cũ tối đa bao lâu vẫn còn hữu ích?
4. Khi có mạng lại, thay đổi được merge, ghi đè hay yêu cầu người dùng giải quyết?

### 3.1. Phân loại dữ liệu

| Nhóm | Ví dụ | Offline behavior |
| --- | --- | --- |
| App shell | CSS, JavaScript, icon, offline page | Cache trước, dùng để mở giao diện |
| Public reference data | Danh mục, hướng dẫn công khai | Cache có thời hạn/freshness và hiển thị ngày cập nhật |
| User-specific read data | Danh sách đơn hàng của tài khoản | Chỉ cache nếu nghiệp vụ cho phép; phân vùng user và dọn khi logout |
| Draft | Nội dung form chưa gửi | Lưu IndexedDB; báo rõ chưa được server xác nhận |
| Pending mutation | Tạo ghi chú, cập nhật đơn hàng | Outbox có idempotency và conflict handling |
| Secret/authentication | Password, refresh token, session credential | Không đưa vào Cache Storage hoặc outbox offline |

### 3.2. Đặt freshness requirement

Dữ liệu offline luôn có thể cũ. Với mỗi loại record, định nghĩa:

- `fetchedAt`: lần cuối lấy từ server.
- `expiresAt` hoặc `maxAge`: ngưỡng ứng dụng coi dữ liệu là stale.
- `serverVersion` hoặc `ETag`: phiên bản server đã trả.
- `updatedAt`: thời điểm người dùng sửa bản local.
- `syncState`: `clean`, `pending`, `conflict` hoặc `failed`.

Không dùng đồng hồ client làm bằng chứng bảo mật. `Date.now()` hữu ích cho UX/retention, nhưng người dùng có thể đổi clock. Quyết định chấp nhận mutation, giá và quyền phải dựa trên server.

### 3.3. Trạng thái offline cần rõ ràng

Giao diện nên phân biệt:

- Đang online và dữ liệu mới.
- Đang online nhưng đang hiển thị bản cache cũ.
- Offline và chỉ xem được bản lưu gần nhất.
- Có thay đổi local đang chờ đồng bộ.
- Đồng bộ thất bại hoặc có xung đột cần người dùng xử lý.

Không hiển thị “Đã lưu” nếu chỉ mới ghi vào IndexedDB. Dùng thông báo chính xác như “Đã lưu trên thiết bị — chờ đồng bộ” cho tới khi server xác nhận.

## 4. Các chiến lược cache phổ biến

### 4.1. Cache-first

Đọc cache trước; nếu không có thì lấy network và lưu bản mới.

```js
async function cacheFirst(request, cacheName) {
  const cache = await caches.open(cacheName);
  const cached = await cache.match(request);
  if (cached) return cached;

  const response = await fetch(request);
  if (response.ok) {
    await cache.put(request, response.clone());
  }
  return response;
}
```

Phù hợp với asset có tên chứa content hash hoặc phiên bản bất biến. Với dữ liệu thay đổi thường xuyên, cache-first có thể trả bản cũ vô thời hạn nếu không có cơ chế invalidation.

### 4.2. Network-first

Thử network trước; nếu network thất bại thì dùng cache:

```js
async function networkFirst(request, cacheName) {
  const cache = await caches.open(cacheName);

  try {
    const response = await fetch(request);
    if (response.ok) {
      await cache.put(request, response.clone());
    }
    return response;
  } catch {
    const cached = await cache.match(request);
    if (cached) return cached;
    throw new Error("Không có mạng và không có bản lưu phù hợp.");
  }
}
```

Phù hợp với dữ liệu cần mới hơn nhưng vẫn có fallback. Lưu ý `fetch()` không reject chỉ vì server trả HTTP 404 hoặc 500; cần kiểm tra `response.ok` và chỉ cache response hợp lệ theo policy.

### 4.3. Stale-while-revalidate

Trả cache ngay nếu có, đồng thời cập nhật ở nền:

```js
async function staleWhileRevalidate(request, cacheName) {
  const cache = await caches.open(cacheName);
  const cached = await cache.match(request);

  const refresh = fetch(request).then(async response => {
    if (response.ok) {
      await cache.put(request, response.clone());
    }
    return response;
  });

  if (cached) {
    // Không chờ refresh để trả nội dung; lỗi refresh được xử lý riêng.
    refresh.catch(() => {});
    return cached;
  }

  return refresh;
}
```

Phù hợp với dữ liệu công khai ít nhạy cảm mà bản cũ vẫn hữu ích, ví dụ danh mục hoặc bài hướng dẫn. UI cần cho biết dữ liệu có thể cũ và cập nhật thời điểm mới nhất.

Không dùng stale-while-revalidate mặc định cho số dư, trạng thái thanh toán, quyền truy cập, dữ liệu nhạy cảm hoặc thông tin thay đổi theo người dùng. Không để response riêng tư của tài khoản trước xuất hiện khi người khác đăng nhập cùng profile.

### 4.4. Network-only và cache-only

- `network-only`: luôn gọi server; phù hợp với dữ liệu nhạy cảm hoặc hành động cần quyết định hiện tại. Khi offline, hiển thị không khả dụng.
- `cache-only`: chỉ trả bản cache đã có; phù hợp với asset offline shell hoặc dữ liệu snapshot mà UX chấp nhận.
- `fallback`: network thất bại thì trả offline page hoặc thông báo có kiểm soát.

Không có một chiến lược duy nhất cho toàn bộ ứng dụng. Có thể chọn theo request destination/path, nhưng cần allowlist route và method rõ ràng.

### 4.5. Bảng lựa chọn

| Nhu cầu | Chiến lược gợi ý | Rủi ro cần xử lý |
| --- | --- | --- |
| Asset có content hash | Cache-first | Giữ cache version cũ quá lâu |
| Navigation cần nội dung mới | Network-first + offline shell | Không cache trang private tùy tiện |
| Tài liệu public ít thay đổi | Stale-while-revalidate | Hiển thị timestamp/stale state |
| API riêng tư hoặc quyền hiện tại | Network-only | Không có dữ liệu khi offline |
| Offline app shell | Cache-only sau install | Precache thiếu asset làm install thất bại |

## 5. Cache Storage không tự áp dụng mọi HTTP cache rule

Cache API là kho do ứng dụng quản lý. Không giả định browser sẽ tự áp dụng `Cache-Control: max-age`, `no-store` hoặc freshness như HTTP cache thông thường cho mọi thao tác `Cache.put()`. Ứng dụng quyết định response nào được ghi, lúc nào refresh và lúc nào xóa.

Vì vậy:

- Kiểm tra request method và URL trước khi cache.
- Chỉ cache response `GET` được chọn rõ ràng.
- Kiểm tra `response.ok`, loại nội dung và nguồn response.
- Không cache response chứa session, token hoặc dữ liệu riêng tư theo mặc định.
- Không cache opaque response một cách tùy tiện vì JavaScript không đọc được status/body để xác minh nội dung.
- Có version, metadata hoặc TTL do ứng dụng thực thi.
- Xóa cache cũ khi dữ liệu không còn hợp lệ.

`Cache-Control: no-store` trên response là chỉ dẫn quan trọng cho HTTP cache và các tầng trung gian, nhưng Cache API do code chủ động ghi cần được kiểm soát riêng. Nếu ứng dụng thấy `no-store`, hãy tôn trọng policy đó và không tự đưa response vào Cache Storage.

### 5.1. Kiểm tra trước khi cache

Ví dụ helper chỉ nhận response GET same-origin và loại bỏ response được server đánh dấu không lưu:

```js
function isCacheableResponse(request, response) {
  const url = new URL(request.url);

  if (request.method !== "GET") return false;
  if (url.origin !== self.location.origin) return false;
  if (!response || !response.ok) return false;
  if (response.type === "opaque") return false;

  const cacheControl = response.headers.get("Cache-Control") || "";
  if (/\bno-store\b/i.test(cacheControl)) return false;

  const contentType = response.headers.get("Content-Type") || "";
  if (!/^(text\/|application\/javascript|application\/json|image\/)/i.test(contentType)) {
    return false;
  }

  return true;
}
```

Đây chỉ là một baseline. Allowlist theo route và loại dữ liệu thường an toàn hơn một regex content type rộng. Với response user-specific, cần quyết định riêng về account isolation, cache key và cleanup.

## 6. Vòng đời Service Worker và cache versioning

### 6.1. Install: chuẩn bị app shell

Trong `install`, có thể precache các file cần để mở ứng dụng offline:

```js
const SHELL_CACHE = "app-shell-v4";
const SHELL_FILES = [
  "/offline.html",
  "/assets/app.4f21.css",
  "/assets/app.91ac.js",
  "/assets/logo.svg"
];

self.addEventListener("install", event => {
  event.waitUntil((async () => {
    const cache = await caches.open(SHELL_CACHE);
    await cache.addAll(SHELL_FILES);
  })());
});
```

`cache.addAll()` thất bại nếu một trong các request không tải được hoặc response không hợp lệ. Đây có thể là hành vi mong muốn để không activate một worker có app shell thiếu file. Hãy kiểm tra đường dẫn, status và deployment order.

### 6.2. Activate: dọn cache version cũ

Khi worker mới activate, có thể xóa cache do chính ứng dụng quản lý:

```js
const CURRENT_CACHES = new Set([
  "app-shell-v4",
  "public-data-v2"
]);

self.addEventListener("activate", event => {
  event.waitUntil((async () => {
    const names = await caches.keys();

    await Promise.all(
      names
        .filter(name =>
          (name.startsWith("app-shell-") || name.startsWith("public-data-")) &&
          !CURRENT_CACHES.has(name)
        )
        .map(name => caches.delete(name))
    );

    await self.clients.claim();
  })());
});
```

Chỉ xóa cache có prefix thuộc quyền sở hữu của ứng dụng. Không xóa mọi cache trên origin vì ứng dụng khác cùng origin hoặc module khác có thể quản lý cache riêng. Với nhiều tab, cần cân nhắc tương thích giữa page shell cũ và worker mới trước khi cleanup.

### 6.3. `skipWaiting()` và `clients.claim()`

`skipWaiting()` yêu cầu worker mới bỏ qua trạng thái waiting; `clients.claim()` khiến worker active nhận quyền điều khiển các client phù hợp. Chúng có thể giúp phát hành nhanh, nhưng có rủi ro worker mới điều khiển page đang chạy code cũ.

Chỉ dùng khi API contract, cache schema và page version tương thích. Với thay đổi lớn, hiển thị thông báo “Có phiên bản mới” và yêu cầu người dùng reload ở thời điểm an toàn. Không ép reload khi người dùng đang nhập form hoặc có mutation chưa đồng bộ.

### 6.4. Version cache theo nội dung

Dùng tên cache có version hoặc content hash:

- `app-shell-v4` cho app shell.
- `public-catalog-v7` cho dữ liệu public.
- `private-drafts-v2` cho schema draft nếu thật sự cần cache riêng.

Đổi version khi nội dung hoặc schema thay đổi. Với IndexedDB, dùng version database và `onupgradeneeded` để migrate schema. Không dùng cache version như cơ chế bảo mật; nó chỉ giúp quản lý vòng đời.

## 7. Điều phối fetch trong Service Worker

Service Worker có thể phân loại request trước khi chọn chiến lược. Một mẫu an toàn nên bắt đầu bằng giới hạn method và origin:

```js
self.addEventListener("fetch", event => {
  const request = event.request;
  const url = new URL(request.url);

  if (request.method !== "GET") return;
  if (url.origin !== self.location.origin) return;

  if (url.pathname.startsWith("/assets/")) {
    event.respondWith(cacheFirst(request, "app-shell-v4"));
    return;
  }

  if (url.pathname === "/offline.html") {
    event.respondWith(
      caches.match("/offline.html")
        .then(response => response || fetch(request))
    );
  }
});
```

Không intercept mọi request rồi cache theo mặc định. Các request POST/PUT/PATCH/DELETE cần semantics nghiệp vụ, xác thực, CSRF và retry riêng. Cache API cũng không phải hàng đợi mutation; hãy dùng IndexedDB cho outbox.

### 7.1. Navigation fallback

Một navigation có thể thử network và trả offline shell nếu fetch thất bại:

```js
async function navigationFallback(request) {
  try {
    return await fetch(request);
  } catch {
    const offlinePage = await caches.match("/offline.html");
    if (offlinePage) return offlinePage;

    return new Response("Bạn đang offline.", {
      status: 503,
      headers: { "Content-Type": "text/plain; charset=utf-8" }
    });
  }
}
```

Chỉ fallback khi network request lỗi. HTTP 404/500 là response hợp lệ ở tầng Fetch và không tự động đi vào `catch`; nếu muốn fallback theo status, hãy thiết kế rule riêng. Không thay response lỗi server bằng trang offline một cách âm thầm vì sẽ che giấu sự cố thật.

### 7.2. Không cache private navigation mặc định

Trang `/account`, `/billing` hoặc `/admin` có thể chứa dữ liệu riêng tư. Dù navigation request là GET, không có nghĩa response được phép lưu offline. Có thể network-only cho các route này, hoặc triển khai snapshot riêng với account partition, retention, cleanup và authorization đã đánh giá.

### 7.3. Cache invalidation sau mutation

Khi server xác nhận một mutation, hãy invalidation những cache liên quan hoặc cập nhật snapshot từ response mới. Không tự sửa cache như thể server đã chấp nhận khi request vẫn pending hoặc bị từ chối.

Nếu mutation offline, lưu nó ở outbox và đánh dấu UI là pending. Sau khi server xác nhận, cập nhật dữ liệu local bằng version mới từ server. Nếu bị conflict, giữ bản nháp và yêu cầu xử lý thay vì âm thầm ghi đè.
## 8. Lưu thay đổi offline bằng IndexedDB outbox

Cache Storage được thiết kế cho response GET; không dùng nó để xếp hàng POST/PUT/PATCH/DELETE. Khi người dùng tạo hoặc sửa dữ liệu offline, lưu mutation vào IndexedDB dưới dạng một record có trạng thái và mã idempotency.

### 8.1. Cấu trúc outbox record

Một record có thể chứa:

```js
const outboxRecord = {
  id: "local-op-uuid",
  accountKey: "opaque-account-key",
  operation: "update-note",
  endpoint: "/api/notes/123",
  method: "PATCH",
  idempotencyKey: "stable-operation-key",
  payload: { title: "Tiêu đề mới" },
  createdAt: 1790000000000,
  attempts: 0,
  state: "pending"
};
```

Chỉ lưu payload cần để thực hiện thao tác. Không lưu session cookie, access token, refresh token hoặc CSRF secret dài hạn trong outbox. Browser tự gửi cookie same-origin khi worker gọi endpoint; server vẫn phải xác thực session, kiểm tra CSRF và authorization.

### 8.2. Ghi mutation vào IndexedDB

Ví dụ tối giản mở database và thêm một record. Trong ứng dụng thật, cần schema migration và xử lý quota/error đầy đủ:

```js
function openOutboxDb() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open("offline-outbox", 1);

    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains("outbox")) {
        db.createObjectStore("outbox", { keyPath: "id" });
      }
    };

    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

async function enqueueMutation(record) {
  const db = await openOutboxDb();

  return new Promise((resolve, reject) => {
    const transaction = db.transaction("outbox", "readwrite");
    transaction.objectStore("outbox").add(record);

    transaction.oncomplete = () => {
      db.close();
      resolve();
    };
    transaction.onerror = () => {
      db.close();
      reject(transaction.error);
    };
    transaction.onabort = () => {
      db.close();
      reject(transaction.error || new Error("Outbox transaction aborted"));
    };
  });
}
```

Gọi `enqueueMutation()` chỉ xác nhận record đã được lưu local. UI cần hiển thị “Đang chờ đồng bộ”, không thông báo thao tác đã được server chấp nhận.

### 8.3. Idempotency và retry

Mạng có thể ngắt sau khi server đã xử lý request nhưng trước khi browser nhận response. Khi retry, cùng một thao tác có thể được gửi hai lần. Gửi một `Idempotency-Key` ổn định cho mỗi operation; server cần lưu kết quả theo key và principal, rồi trả lại kết quả trước đó khi nhận retry trùng.

Không tạo key mới mỗi lần retry. Không coi HTTP status bất kỳ là thành công:

- `2xx`: server xác nhận; đánh dấu record hoàn tất và cập nhật dữ liệu local bằng response server.
- `401`: session không hợp lệ; dừng hàng đợi và yêu cầu đăng nhập.
- `403`: quyền hoặc CSRF check thất bại; không retry vô hạn.
- `409` hoặc `412`: có thể có conflict/version mismatch; chuyển record sang trạng thái cần xử lý.
- `429`, lỗi mạng hoặc `5xx`: retry có backoff, tôn trọng `Retry-After` nếu có.
- `400`/`422`: payload không hợp lệ; đánh dấu lỗi để người dùng sửa hoặc loại bỏ.

### 8.4. Background Sync và fallback

Background Sync cho phép đăng ký một lần đồng bộ để browser thử phát event `sync` khi có điều kiện. API không được hỗ trợ đồng đều và browser không cam kết worker sẽ chạy ngay đúng thời điểm mong muốn. Không dựa vào Background Sync như một scheduler đảm bảo.

Ví dụ đăng ký:

```js
async function requestOutboxSync() {
  if (!("serviceWorker" in navigator)) return false;

  const registration = await navigator.serviceWorker.ready;

  if (!("sync" in registration)) {
    return false;
  }

  try {
    await registration.sync.register("flush-offline-outbox");
    return true;
  } catch {
    return false;
  }
}
```

Nếu không hỗ trợ hoặc đăng ký thất bại, ứng dụng có thể thử đồng bộ khi mở lại trang, khi người dùng nhấn “Thử lại”, hoặc khi trang nhận event `online`. `navigator.onLine` chỉ là tín hiệu gần đúng; request thực tế mới xác nhận server có thể truy cập.

### 8.5. Nguyên tắc triển khai worker sync

Một handler có thể điều phối việc gửi outbox:

```js
self.addEventListener("sync", event => {
  if (event.tag === "flush-offline-outbox") {
    event.waitUntil(flushOfflineOutbox());
  }
});
```

`flushOfflineOutbox()` cần đọc các record pending từ IndexedDB, xác minh session/account hiện tại qua endpoint same-origin, lấy CSRF token còn hiệu lực khi kiến trúc cần, rồi gửi từng mutation với `Idempotency-Key`. Chỉ đánh dấu completed sau khi server xác nhận. Nếu session không còn hợp lệ, dừng và chờ người dùng đăng nhập; không phát lại queue của tài khoản cũ dưới phiên của tài khoản mới.

## 9. Xung đột và tính toàn vẹn dữ liệu

### 9.1. Vì sao có conflict?

Trong lúc thiết bị offline, người dùng có thể sửa cùng record ở một thiết bị khác hoặc server có thể cập nhật dữ liệu bởi một quy trình khác. Khi online trở lại, bản local không còn là phiên bản mới nhất.

Ví dụ:

- Thiết bị A offline sửa địa chỉ giao hàng.
- Thiết bị B online cũng sửa địa chỉ đó.
- Thiết bị A đồng bộ bản cũ sau đó.

Nếu server chấp nhận ghi đè vô điều kiện, một thay đổi hợp lệ có thể bị mất.

### 9.2. Optimistic concurrency

Dùng version hoặc ETag để server phát hiện client đang cập nhật từ phiên bản cũ:

```http
GET /api/notes/123
ETag: "note-v18"
```

Client gửi mutation kèm version đã đọc:

```http
PATCH /api/notes/123
If-Match: "note-v18"
Content-Type: application/json
```

Nếu record đã đổi, server trả `412 Precondition Failed` hoặc mã conflict theo contract. Client tải phiên bản mới, hiển thị khác biệt và yêu cầu người dùng chọn cách merge. Với một số dữ liệu có thể merge tự động theo field; với số tiền, trạng thái thanh toán, quyền và dữ liệu pháp lý, cần quy tắc nghiệp vụ rõ ràng ở server.

### 9.3. Không tin timestamp client

Timestamp trên thiết bị có thể sai hoặc bị sửa. Dùng server version, sequence hoặc ETag làm căn cứ concurrency. Timestamp client vẫn hữu ích để sắp xếp bản nháp và hỗ trợ UX, nhưng không được quyết định quyền, giá hoặc thứ tự giao dịch có thẩm quyền.

### 9.4. Tách local draft khỏi server state

Lưu trạng thái riêng:

- `local-draft`: người dùng đang chỉnh sửa.
- `pending`: đã xếp hàng chờ gửi.
- `synced`: server đã xác nhận.
- `conflict`: server từ chối vì version không còn mới.
- `failed`: lỗi cần hành động hoặc payload không thể gửi.

Không cập nhật nhãn `synced` chỉ vì `fetch()` đã resolve. Phải kiểm tra status, parse response và xử lý contract server.

## 10. Quota, eviction và persistence

### 10.1. Dung lượng storage có giới hạn

Browser áp dụng quota theo origin/storage key, nền tảng và tình trạng thiết bị. Khi vượt quota, thao tác Cache Storage hoặc IndexedDB có thể thất bại. Browser cũng có thể eviction dữ liệu khi thiếu dung lượng hoặc theo chính sách riêng.

Vì vậy, offline data không phải bản sao lưu lâu dài. Nếu dữ liệu có giá trị nghiệp vụ, cần có khả năng đồng bộ lên server và khôi phục lại sau khi browser xóa storage.

### 10.2. Ước lượng dung lượng

Storage Manager API có thể cung cấp ước lượng:

```js
async function inspectStorage() {
  if (!navigator.storage?.estimate) {
    return null;
  }

  const estimate = await navigator.storage.estimate();

  return {
    usageBytes: estimate.usage ?? 0,
    quotaBytes: estimate.quota ?? 0
  };
}
```

Đây là số ước lượng, không phải cam kết quota còn trống. Dung lượng có thể thay đổi sau đó; luôn bắt lỗi khi ghi Cache Storage/IndexedDB và có fallback UX.

### 10.3. Xin persistent storage

Có thể hỏi browser cho phép origin dùng persistent storage:

```js
async function requestPersistentStorage() {
  if (!navigator.storage?.persist) {
    return false;
  }

  try {
    return await navigator.storage.persist();
  } catch {
    return false;
  }
}
```

Browser có thể từ chối yêu cầu. `persist()` không mã hóa dữ liệu, không ngăn người dùng xóa site data và không bảo vệ trước XSS. Chỉ xin persistence khi ứng dụng có lý do hợp lý, chẳng hạn dữ liệu offline do người dùng tạo mà mất đi sẽ gây thiệt hại.

### 10.4. Xử lý quota error

- Giới hạn kích thước file và số bản cache.
- Xóa cache version cũ hoặc dữ liệu public đã hết hạn.
- Giữ draft/outbox chưa đồng bộ ở mức ưu tiên phù hợp.
- Không xóa dữ liệu pending của người dùng để giải phóng dung lượng mà không thông báo.
- Cho phép người dùng tải lại dữ liệu từ server khi có mạng.
- Hiển thị lỗi lưu local nếu transaction bị abort hoặc quota exceeded.

Nếu storage đã đầy, ứng dụng không được giả vờ đã lưu draft. Chỉ hiển thị xác nhận sau khi transaction hoàn tất thành công.

## 11. Bảo vệ dữ liệu offline và account boundary

### 11.1. Cache private là quyết định bảo mật

Service Worker và Cache Storage cùng origin có thể truy cập dữ liệu mà origin được phép. Nếu ứng dụng cache response chứa hồ sơ, hóa đơn hoặc thông tin riêng tư, một người dùng khác trên cùng browser profile có thể nhìn thấy dữ liệu cũ nếu account switching không dọn đúng cách.

Ưu tiên network-only cho response nhạy cảm. Nếu nghiệp vụ bắt buộc offline:

- Chỉ cache trường dữ liệu tối thiểu.
- Phân vùng record/cache theo account context.
- Xác minh tài khoản hiện tại trước khi đọc hoặc đồng bộ.
- Có retention và cleanup rõ.
- Không cache response có token/session secret.
- Không dùng account key phía client làm authorization.

### 11.2. Account switching và logout

Khi logout hoặc chuyển tài khoản:

1. Gửi yêu cầu revoke session tới server.
2. Dừng sync đang chạy và đánh dấu queue của account cũ là paused.
3. Xóa cache/draft private theo account nếu policy yêu cầu.
4. Không gửi queue cũ bằng cookie của account mới.
5. Dừng tác vụ background và xóa dữ liệu nhạy cảm trong memory.
6. Khi tài khoản cũ đăng nhập lại, chỉ resume queue sau khi server xác minh đúng principal.

Không xóa outbox pending một cách âm thầm nếu người dùng có thể mất nội dung đã soạn. Cần chính sách rõ: giữ local draft, cho người dùng export, hoặc yêu cầu xác nhận trước khi xóa.

### 11.3. XSS vẫn có thể đọc offline data

Cache Storage và IndexedDB không phải secret vault. Script độc hại chạy cùng origin có thể truy cập dữ liệu qua API mà origin cho phép. Service Worker không làm dữ liệu offline miễn nhiễm XSS.

Phòng vệ cần kết hợp:

- Output encoding và DOM API an toàn.
- CSP/Trusted Types phù hợp.
- Giảm script bên thứ ba và dùng SRI khi thích hợp.
- Không lưu credential dài hạn trong Cache Storage/IndexedDB.
- Giới hạn dữ liệu offline và retention.
- Server authorization cho mọi mutation.

### 11.4. Mã hóa phía client có giới hạn

Mã hóa dữ liệu offline có thể giúp khi kẻ tấn công chỉ sao chép được storage mà không có khóa. Nhưng nếu ứng dụng tự động lấy khóa và giải mã khi mở trang, XSS có thể gọi thao tác decrypt hoặc đọc plaintext sau khi giải mã. Non-extractable CryptoKey ngăn export raw key, không ngăn script cùng origin sử dụng key mà ứng dụng đã mở.

Không dùng mã hóa phía client để thay thế data minimization, kiểm soát XSS, session protection hoặc server authorization.

### 11.5. Service worker script là thành phần có đặc quyền trong origin

Service Worker có thể điều khiển request trong scope. Bảo vệ file worker khỏi bị thay thế bằng cách:

- Phục vụ script qua HTTPS và kiểm soát quyền deploy.
- Giữ scope hẹp nhất có thể.
- Không cho phép user-uploaded content nằm trong scope có thể đăng ký worker.
- Không tải logic worker từ nguồn bên thứ ba không tin cậy.
- Rà soát thay đổi worker và cache strategy như code bảo mật trọng yếu.
- Có quy trình cập nhật/rollback khi worker mới làm hỏng offline behavior.

## 12. Thực hành: app shell hoạt động offline

Bài lab tạo một trang đơn giản và một Service Worker. Trang được mở lần đầu khi online; worker precache offline page và asset, sau đó trả fallback khi navigation thất bại. Lab không cache API hay dữ liệu tài khoản.

### 12.1. Tạo `index.html`

```html
<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Offline data lab</title>
  <link rel="stylesheet" href="/app.css">
</head>
<body>
  <h1>Offline data lab</h1>
  <p id="status">Đang tải ứng dụng.</p>
  <button id="check" type="button">Kiểm tra kết nối</button>
  <script src="/app.js"></script>
</body>
</html>
```

### 12.2. Tạo `app.css`

```css
body {
  max-width: 42rem;
  margin: 3rem auto;
  padding: 0 1rem;
  font: 16px/1.5 system-ui, sans-serif;
}

button {
  padding: 0.6rem 1rem;
}
```

### 12.3. Tạo `app.js`

```js
const status = document.querySelector("#status");

function renderConnection() {
  status.textContent = navigator.onLine
    ? "Browser báo đang online; request thực tế vẫn cần xác nhận."
    : "Browser báo offline.";
}

document.querySelector("#check").addEventListener("click", renderConnection);
window.addEventListener("online", renderConnection);
window.addEventListener("offline", renderConnection);
renderConnection();

if ("serviceWorker" in navigator && window.isSecureContext) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/sw.js")
      .catch(error => {
        status.textContent = "Không đăng ký được Service Worker: " + error.message;
      });
  });
}
```

### 12.4. Tạo `offline.html`

```html
<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Đang offline</title>
</head>
<body>
  <h1>Bạn đang offline</h1>
  <p>Không thể tải trang mới. Hãy kết nối lại để tiếp tục.</p>
</body>
</html>
```

### 12.5. Tạo `sw.js`

```js
const SHELL_CACHE = "offline-lab-shell-v1";
const SHELL_FILES = [
  "/offline.html",
  "/app.css",
  "/app.js"
];

self.addEventListener("install", event => {
  event.waitUntil((async () => {
    const cache = await caches.open(SHELL_CACHE);
    await cache.addAll(SHELL_FILES);
    await self.skipWaiting();
  })());
});

self.addEventListener("activate", event => {
  event.waitUntil((async () => {
    const names = await caches.keys();

    await Promise.all(
      names
        .filter(name =>
          name.startsWith("offline-lab-shell-") &&
          name !== SHELL_CACHE
        )
        .map(name => caches.delete(name))
    );

    await self.clients.claim();
  })());
});

self.addEventListener("fetch", event => {
  const request = event.request;
  const url = new URL(request.url);

  if (request.method !== "GET" || url.origin !== self.location.origin) {
    return;
  }

  if (url.pathname === "/app.css" || url.pathname === "/app.js") {
    event.respondWith((async () => {
      const cache = await caches.open(SHELL_CACHE);
      const cached = await cache.match(request);
      if (cached) return cached;

      const response = await fetch(request);
      if (response.ok) {
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
        return (await caches.match("/offline.html")) ||
          new Response("Offline", { status: 503 });
      }
    })());
  }
});
```

### 12.6. Chạy và kiểm tra

1. Phục vụ thư mục lab qua HTTPS hoặc `localhost`; không mở file trực tiếp bằng `file://`.
2. Mở trang khi online, kiểm tra Service Worker đã activated trong DevTools → Application → Service Workers.
3. Reload thêm một lần để xác nhận worker điều khiển trang.
4. Trong DevTools → Network, bật chế độ Offline.
5. Điều hướng tới một URL trong cùng origin; browser sẽ hiển thị `offline.html` khi network fetch thất bại.
6. Tải lại asset `/app.css` và `/app.js`; chúng được phục vụ từ Cache Storage.
7. Tắt Offline và reload; trang được tải từ network.
8. Thay tên cache version, cập nhật file worker và quan sát install/activate cùng cleanup.
9. Kiểm tra Cache Storage chỉ chứa app shell; không có API response hoặc dữ liệu tài khoản.

Lưu ý: lần cài đặt đầu tiên cần online để precache thành công. Chế độ Offline trong DevTools là công cụ mô phỏng; nó không mô phỏng mọi trường hợp mất mạng, DNS lỗi, timeout hoặc server trả 5xx.

## 13. Ma trận kiểm thử offline data

| Mã | Tình huống | Kết quả mong muốn |
| --- | --- | --- |
| OFF-01 | Cài worker khi online và precache thành công | App shell được lưu đúng cache version |
| OFF-02 | Một file precache trả lỗi | Install thất bại; worker thiếu asset không activate |
| OFF-03 | Mở trang khi offline sau lần cài | Offline fallback hiển thị |
| OFF-04 | Asset có trong cache | Cache-first trả bản đã lưu |
| OFF-05 | Asset version mới được deploy | Worker/cache version mới được cài và cleanup có kiểm soát |
| OFF-06 | Network-first gặp lỗi mạng | Trả bản cache nếu có; nếu không có thì hiển thị lỗi rõ |
| OFF-07 | Server trả 500 | Không nhầm HTTP error response với network rejection |
| OFF-08 | API private được gọi | Không cache mặc định |
| OFF-09 | Dữ liệu public stale | UI thể hiện thời điểm cập nhật và trạng thái stale |
| OFF-10 | Mutation được lưu vào outbox | UI báo pending, chưa xác nhận server |
| OFF-11 | Request retry sau timeout | Idempotency key ngăn tạo thao tác trùng |
| OFF-12 | Server trả 409/412 | Mutation chuyển conflict, không ghi đè âm thầm |
| OFF-13 | Background Sync không được hỗ trợ | Foreground/manual retry vẫn hoạt động |
| OFF-14 | Session hết hạn khi outbox đang chờ | Queue dừng; không gửi bằng tài khoản khác |
| OFF-15 | Đổi tài khoản trên cùng profile | Cache/draft private không rò giữa hai tài khoản |
| OFF-16 | Logout | Session revoke và dữ liệu offline được xử lý theo policy |
| OFF-17 | Storage quota exceeded | Không báo đã lưu nếu transaction thất bại |
| OFF-18 | Browser eviction | Ứng dụng khôi phục dữ liệu từ server hoặc thông báo mất cache |
| OFF-19 | User chỉnh đồng thời trên thiết bị khác | ETag/version phát hiện conflict |
| OFF-20 | XSS cùng origin | Không giả định Cache Storage/IndexedDB bảo vệ plaintext |
| OFF-21 | navigator.onLine báo online nhưng server không tới được | Request thực tế xác định trạng thái lỗi |
| OFF-22 | Worker mới activate trong tab đang dùng app cũ | Contract/cache schema tương thích hoặc yêu cầu reload an toàn |

## 14. Quy trình triển khai và checklist

### 14.1. Quy trình triển khai

1. Xác định use case offline: đọc dữ liệu, tạo draft hay đồng bộ mutation.
2. Phân loại dữ liệu public, private và secret; loại bỏ dữ liệu không cần lưu.
3. Chọn Cache Storage cho response và IndexedDB cho record/outbox.
4. Chọn cache strategy theo freshness và độ nhạy cảm.
5. Thiết kế cache/database version, migration và cleanup.
6. Xây dựng outbox có idempotency, retry, CSRF và conflict handling.
7. Phân vùng dữ liệu theo account; xử lý logout/account switching.
8. Xử lý quota, eviction và persistence request.
9. Kiểm thử online/offline, nhiều tab, nhiều tài khoản và worker update.
10. Theo dõi lỗi đồng bộ, cache miss, stale data và dữ liệu pending sau release.

### 14.2. Checklist

- [ ] Xác định chính xác dữ liệu nào cần khả năng offline.
- [ ] Không cache mọi request theo mặc định.
- [ ] Chỉ cache GET same-origin được allowlist và response đã kiểm tra.
- [ ] Không cache credential, token hoặc response private nếu chưa có thiết kế bảo vệ rõ.
- [ ] Dùng Cache Storage cho response và IndexedDB cho dữ liệu có cấu trúc/outbox.
- [ ] Đặt cache version và chỉ xóa cache thuộc quyền sở hữu của ứng dụng.
- [ ] Không dùng skipWaiting()/clients.claim() nếu page version chưa tương thích.
- [ ] Thể hiện freshness và trạng thái pending/conflict trong UI.
- [ ] Dùng idempotency key ổn định cho mutation retry.
- [ ] Server xác thực session, CSRF, authorization và version cho mỗi mutation.
- [ ] Background Sync có foreground/manual fallback.
- [ ] Không xem navigator.onLine là bằng chứng server truy cập được.
- [ ] Xử lý quota, eviction, persist denial và transaction failure.
- [ ] Phân vùng dữ liệu theo tài khoản và cleanup khi logout/account switching.
- [ ] Không giả định mã hóa phía client hoặc Service Worker ngăn XSS.
- [ ] Kiểm tra redirect, cache update và nhiều tab khi phát hành worker mới.
- [ ] Xác minh bằng DevTools Application, Network và ma trận offline/online.

### Ghi nhớ

**Offline data cần một chính sách rõ cho nơi lưu, độ mới, quyền truy cập và đồng bộ.** Service Worker điều phối request; Cache Storage lưu response; IndexedDB lưu record và outbox. Cache-first phù hợp với asset bất biến, network-first phù hợp dữ liệu cần mới, còn stale-while-revalidate chỉ nên dùng cho dữ liệu mà bản cũ vẫn an toàn và hữu ích. Mutation offline cần idempotency, retry và conflict handling ở server. Browser có thể eviction storage, XSS cùng origin có thể đọc dữ liệu offline, và logout phải xử lý cả session lẫn cache/draft/queue theo tài khoản. Luôn hiển thị rõ dữ liệu local đã lưu hay đã được server xác nhận.
