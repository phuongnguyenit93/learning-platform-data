# Kiểm tra storage và service worker

## Mục tiêu thực hành

Sau bài này, bạn có thể:

- Kiểm kê cookie, localStorage, sessionStorage, IndexedDB, CacheStorage và Service Worker của một origin.
- Phân biệt phạm vi lưu trữ theo origin, site, cookie domain/path và Service Worker scope.
- Xác định dữ liệu nào JavaScript cùng origin có thể đọc, dữ liệu nào được gửi tự động theo request và dữ liệu nào chỉ quan sát được qua DevTools hoặc phía server.
- Phát hiện token, thông tin phiên, dữ liệu cá nhân hoặc response nhạy cảm được lưu sai nơi.
- Kiểm tra registration, scope, controller, trạng thái, script URL, cache và hành vi fetch của Service Worker.
- Tái hiện các tình huống stale cache, worker cũ, cache dư thừa và dữ liệu còn tồn tại sau khi đăng xuất.
- Dọn dữ liệu theo đúng phạm vi, xử lý registration và xác minh trạng thái sau khắc phục.
- Lập biên bản kiểm thử có bằng chứng, kết luận và hành động khắc phục.

## 1. Phạm vi và nguyên tắc kiểm tra

Storage và Service Worker là hai phần của cùng một bề mặt dữ liệu phía trình duyệt. Storage giữ dữ liệu giữa các lần điều hướng hoặc phiên làm việc; Service Worker có thể điều khiển request trong scope và dùng CacheStorage để giữ response. Nếu kiểm tra riêng lẻ, bạn có thể bỏ sót dữ liệu được lưu ở nơi khác hoặc một worker vẫn tiếp tục phục vụ nội dung cũ.

Bài thực hành dùng một ứng dụng cục bộ với dữ liệu giả. Bạn sẽ tạo dữ liệu demo, kiểm kê các kho lưu trữ, đăng ký Service Worker, quan sát request và thực hiện cleanup có giới hạn.

Không nhập mật khẩu, access token, refresh token, cookie phiên thật, dữ liệu khách hàng hoặc thông tin nội bộ vào lab. Trong môi trường thật, chỉ kiểm tra dữ liệu khi có quyền và tuân theo quy trình xử lý dữ liệu của tổ chức.

### 1.1. Phân biệt các loại storage

| Cơ chế | Phạm vi chính | JavaScript trang cùng origin | Tự gửi theo HTTP request |
|---|---|---|---|
| Cookie | Domain/host, path và thuộc tính cookie | Có, trừ HttpOnly | Có, theo domain/path/Secure/SameSite |
| localStorage | Origin | Có | Không |
| sessionStorage | Origin và top-level browsing context/tab | Có | Không |
| IndexedDB | Origin | Có | Không |
| CacheStorage | Origin | Có qua Cache API | Chỉ khi Service Worker hoặc code chủ động dùng cache để trả request |
| Service Worker registration | Origin và scope URL | Registration API trong phạm vi được phép | Worker có thể xử lý request trong scope |

Điểm quan trọng:

- Origin gồm scheme, host và port. Hai port khác nhau là hai origin khác nhau đối với Web Storage, IndexedDB và CacheStorage.
- Cookie không được phân vùng theo port. Cookie có thể được gửi đến các port khác nhau của cùng host nếu domain/path/secure và các thuộc tính khác phù hợp.
- Service Worker scope giới hạn những client và URL worker có thể điều khiển; CacheStorage là kho theo origin và không tự bị giới hạn theo scope của một registration.
- localStorage, sessionStorage, IndexedDB và CacheStorage không tự động được đính kèm vào request như cookie.
- CORS kiểm soát việc JavaScript đọc response cross-origin; nó không cho phép một origin đọc storage của origin khác.
- Các trình duyệt có thể partition một số storage trong ngữ cảnh third-party để tăng quyền riêng tư. Không thiết kế ứng dụng dựa vào việc storage third-party luôn chia sẻ xuyên site.

### 1.2. Trust boundary cần nhớ

~~~mermaid
flowchart TD
    A["Website origin"] --> B["JavaScript runtime"]
    B --> C["localStorage / sessionStorage"]
    B --> D["IndexedDB"]
    B --> E["CacheStorage"]
    B --> F["Cookie API qua document.cookie"]
    G["HTTP response"] --> H["Set-Cookie"]
    H --> I["Cookie jar của browser"]
    I --> J["Request phù hợp domain/path/policy"]
    K["Service Worker registration"] --> L["Worker trong scope"]
    L --> E
    L --> M["Fetch event / network"]
    C --> N["Dữ liệu có thể bị đọc nếu XSS chạy cùng origin"]
    D --> N
    E --> N
    F --> N
~~~

Nếu attacker thực thi JavaScript cùng origin thông qua XSS, dữ liệu trong Web Storage, IndexedDB và CacheStorage có thể bị đọc hoặc thay đổi. HttpOnly ngăn JavaScript đọc trực tiếp cookie, nhưng XSS vẫn có thể thực hiện hành động bằng phiên đang đăng nhập hoặc đọc dữ liệu mà trang hiển thị.

## 2. Chuẩn bị môi trường lab

### 2.1. Công cụ

- Node.js phiên bản còn được hỗ trợ.
- Chrome, Edge hoặc Firefox hiện đại.
- DevTools với các tab Application/Storage, Network và Console.
- Terminal để chạy máy chủ loopback.

Service Worker yêu cầu secure context. HTTPS là lựa chọn cho môi trường thật; localhost và loopback được trình duyệt coi là secure context phục vụ phát triển. Lab chỉ lắng nghe trên 127.0.0.1.

### 2.2. Cấu trúc thư mục

Tạo một thư mục tạm với cấu trúc:

~~~text
storage-sw-lab/
  server.js
  public/
    index.html
    app.js
    sw.js
    offline.html
~~~

### 2.3. Máy chủ Node.js tối giản

Tạo server.js:

~~~javascript
const http = require("node:http");
const fs = require("node:fs");
const path = require("node:path");

const HOST = "127.0.0.1";
const PORT = 8080;
const ROOT = path.join(__dirname, "public");

const FILES = new Map([
  ["/", "index.html"],
  ["/index.html", "index.html"],
  ["/app.js", "app.js"],
  ["/sw.js", "sw.js"],
  ["/offline.html", "offline.html"]
]);

const TYPES = {
  ".html": "text/html; charset=utf-8",
  ".js": "application/javascript; charset=utf-8"
};

const server = http.createServer((req, res) => {
  const url = new URL(req.url, "http://" + HOST + ":" + PORT);

  if (req.method === "GET" && url.pathname === "/set-cookie") {
    res.writeHead(200, {
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": "no-store",
      "Set-Cookie": "lab_http_only=demo-session; HttpOnly; SameSite=Lax; Path=/; Max-Age=600"
    });
    res.end(JSON.stringify({ cookieSet: true }));
    return;
  }

  if (req.method === "GET" && url.pathname === "/clear-cookie") {
    res.writeHead(200, {
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": "no-store",
      "Set-Cookie": "lab_http_only=; HttpOnly; SameSite=Lax; Path=/; Max-Age=0"
    });
    res.end(JSON.stringify({ cookieCleared: true }));
    return;
  }

  if (req.method !== "GET") {
    res.writeHead(405, {
      "Content-Type": "text/plain; charset=utf-8",
      "Cache-Control": "no-store",
      "Allow": "GET"
    });
    res.end("Method not allowed");
    return;
  }

  const relative = FILES.get(url.pathname);

  if (!relative) {
    res.writeHead(404, { "Cache-Control": "no-store" });
    res.end("Not found");
    return;
  }

  const filePath = path.join(ROOT, relative);

  fs.readFile(filePath, (error, data) => {
    if (error) {
      res.writeHead(404, { "Cache-Control": "no-store" });
      res.end("File not found");
      return;
    }

    const headers = {
      "Content-Type": TYPES[path.extname(filePath)] || "application/octet-stream",
      "Cache-Control": url.pathname === "/sw.js" ? "no-cache" : "no-store",
      "X-Content-Type-Options": "nosniff"
    };

    res.writeHead(200, headers);
    res.end(data);
  });
});

server.listen(PORT, HOST, () => {
  console.log("Lab: http://" + HOST + ":" + PORT + "/");
});
~~~

Máy chủ chỉ phục vụ các đường dẫn trong allowlist và chỉ lắng nghe loopback. Endpoint /set-cookie tạo cookie giả có HttpOnly để so sánh với cookie có thể đọc bằng JavaScript. Cookie lab không chứa danh tính hoặc quyền truy cập thật.

### 2.4. Trang HTML

Tạo public/index.html:

~~~html
<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Storage và Service Worker lab</title>
</head>
<body>
  <h1>Storage và Service Worker lab</h1>
  <p>Origin: <strong id="origin"></strong></p>
  <p>Controller: <strong id="controller">chưa có</strong></p>

  <button id="populate">Tạo dữ liệu demo</button>
  <button id="inspect">Kiểm kê storage</button>
  <button id="register">Đăng ký Service Worker</button>
  <button id="unregister">Hủy registration</button>
  <button id="cleanup">Dọn dữ liệu demo</button>

  <pre id="output">Chưa thực hiện kiểm tra.</pre>

  <script src="/app.js" defer></script>
</body>
</html>
~~~

### 2.5. Service Worker

Tạo public/sw.js:

~~~javascript
const CACHE_PREFIX = "storage-sw-lab-worker-";
const CACHE_NAME = CACHE_PREFIX + "v1";
const PRECACHE_URLS = ["/offline.html"];

self.addEventListener("install", (event) => {
  event.waitUntil((async () => {
    const cache = await caches.open(CACHE_NAME);
    await cache.addAll(PRECACHE_URLS);
  })());
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
    url.origin !== self.location.origin ||
    request.mode !== "navigate"
  ) {
    return;
  }

  event.respondWith((async () => {
    try {
      return await fetch(request);
    } catch (error) {
      const cache = await caches.open(CACHE_NAME);
      return (await cache.match("/offline.html")) || Response.error();
    }
  })());
});
~~~

Worker chỉ xử lý navigation GET cùng origin và trả offline fallback khi network lỗi. Worker không cache API hoặc response có dữ liệu người dùng.

### 2.6. JavaScript tạo và kiểm kê dữ liệu

Tạo public/app.js:

~~~javascript
const DB_NAME = "storage-sw-lab";
const STORE_NAME = "notes";
const CACHE_NAME = "storage-sw-lab-demo-data";

const output = document.querySelector("#output");
const controllerLabel = document.querySelector("#controller");

document.querySelector("#origin").textContent = location.origin;

function show(value) {
  output.textContent = JSON.stringify(value, null, 2);
}

function openDatabase() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, 1);

    request.onupgradeneeded = () => {
      const db = request.result;

      if (!db.objectStoreNames.contains(STORE_NAME)) {
        db.createObjectStore(STORE_NAME, { keyPath: "id" });
      }
    };

    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

async function putDemoRecord() {
  const db = await openDatabase();

  try {
    await new Promise((resolve, reject) => {
      const transaction = db.transaction(STORE_NAME, "readwrite");
      transaction.objectStore(STORE_NAME).put({
        id: "demo-note-1",
        title: "Ghi chú thử nghiệm",
        text: "Dữ liệu giả để kiểm tra IndexedDB",
        createdAt: new Date().toISOString()
      });

      transaction.oncomplete = resolve;
      transaction.onerror = () => reject(transaction.error);
      transaction.onabort = () => reject(transaction.error);
    });
  } finally {
    db.close();
  }
}

async function readDemoRecords() {
  const db = await openDatabase();

  try {
    return await new Promise((resolve, reject) => {
      const transaction = db.transaction(STORE_NAME, "readonly");
      const request = transaction.objectStore(STORE_NAME).getAll();

      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    });
  } finally {
    db.close();
  }
}

async function populateDemoData() {
  localStorage.setItem("lab_theme", "dark");
  localStorage.setItem("lab_profile", JSON.stringify({
    displayName: "Người dùng thử nghiệm",
    role: "demo"
  }));

  sessionStorage.setItem("lab_tab_state", "form-open");

  document.cookie = "lab_preference=compact; Path=/; SameSite=Lax; Max-Age=600";

  const cookieResponse = await fetch("/set-cookie", {
    credentials: "same-origin",
    cache: "no-store"
  });

  if (!cookieResponse.ok) {
    throw new Error("Không tạo được HttpOnly cookie");
  }

  await putDemoRecord();

  const cache = await caches.open(CACHE_NAME);
  await cache.put(
    new Request("/lab-cache-entry"),
    new Response("Dữ liệu cache giả", {
      headers: { "Content-Type": "text/plain; charset=utf-8" }
    })
  );

  show({ result: "Đã tạo dữ liệu demo", origin: location.origin });
}

async function inspectStorage() {
  const local = {};
  const session = {};

  for (let i = 0; i < localStorage.length; i += 1) {
    const key = localStorage.key(i);
    if (key && key.startsWith("lab_")) {
      local[key] = localStorage.getItem(key);
    }
  }

  for (let i = 0; i < sessionStorage.length; i += 1) {
    const key = sessionStorage.key(i);
    if (key && key.startsWith("lab_")) {
      session[key] = sessionStorage.getItem(key);
    }
  }

  const registrations = "serviceWorker" in navigator
    ? await navigator.serviceWorker.getRegistrations()
    : [];

  const registrationInfo = registrations.map((registration) => ({
    scope: registration.scope,
    active: registration.active ? {
      scriptURL: registration.active.scriptURL,
      state: registration.active.state
    } : null,
    waiting: registration.waiting ? {
      scriptURL: registration.waiting.scriptURL,
      state: registration.waiting.state
    } : null,
    installing: registration.installing ? {
      scriptURL: registration.installing.scriptURL,
      state: registration.installing.state
    } : null
  }));

  const cacheNames = await caches.keys();
  const cacheInfo = [];

  for (const name of cacheNames) {
    if (!name.startsWith("storage-sw-lab-")) {
      continue;
    }

    const cache = await caches.open(name);
    cacheInfo.push({
      name,
      requests: (await cache.keys()).map((request) => request.url)
    });
  }

  const storageEstimate = navigator.storage &&
    navigator.storage.estimate
    ? await navigator.storage.estimate()
    : null;

  let databaseRecords;

  if (typeof indexedDB.databases === "function") {
    const databases = await indexedDB.databases();
    const exists = databases.some((database) => database.name === DB_NAME);
    databaseRecords = exists
      ? await readDemoRecords().catch((error) => ({ error: error.message }))
      : "Database chưa tồn tại";
  } else {
    databaseRecords =
      "Browser không hỗ trợ indexedDB.databases(); kiểm tra database trong DevTools";
  }

  const controller = navigator.serviceWorker &&
    navigator.serviceWorker.controller
    ? {
        scriptURL: navigator.serviceWorker.controller.scriptURL,
        state: navigator.serviceWorker.controller.state
      }
    : null;

  show({
    origin: location.origin,
    documentCookie: document.cookie,
    note: "document.cookie không hiển thị cookie HttpOnly",
    localStorage: local,
    sessionStorage: session,
    indexedDB: databaseRecords,
    cacheStorage: cacheInfo,
    serviceWorker: {
      controller,
      registrations: registrationInfo
    },
    storageEstimate
  });
}

async function registerWorker() {
  if (!("serviceWorker" in navigator)) {
    throw new Error("Trình duyệt không hỗ trợ Service Worker");
  }

  const registration = await navigator.serviceWorker.register("/sw.js", {
    scope: "/",
    updateViaCache: "none"
  });

  show({
    registered: true,
    scope: registration.scope,
    active: registration.active ? registration.active.state : null,
    waiting: registration.waiting ? registration.waiting.state : null
  });
}

async function unregisterLabWorker() {
  const registrations = await navigator.serviceWorker.getRegistrations();
  const expectedScript = new URL("/sw.js", location.origin).href;
  const target = registrations.filter((registration) =>
    new URL(registration.scope).origin === location.origin &&
    new URL(registration.scope).pathname === "/" &&
    [registration.active, registration.waiting, registration.installing]
      .some((worker) => worker && worker.scriptURL === expectedScript)
  );

  const results = [];

  for (const registration of target) {
    results.push({
      scope: registration.scope,
      unregistered: await registration.unregister()
    });
  }

  show({
    unregisterResults: results,
    note: "Tab hiện tại có thể vẫn được controller cũ điều khiển cho đến khi điều hướng hoặc đóng tab."
  });
}

function deleteDemoDatabase() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.deleteDatabase(DB_NAME);
    request.onsuccess = () => resolve(true);
    request.onerror = () => reject(request.error);
    request.onblocked = () => reject(
      new Error("Database đang được tab hoặc kết nối khác giữ mở")
    );
  });
}

async function cleanupDemoData() {
  localStorage.removeItem("lab_theme");
  localStorage.removeItem("lab_profile");
  sessionStorage.removeItem("lab_tab_state");

  document.cookie =
    "lab_preference=; Path=/; SameSite=Lax; Max-Age=0";

  const cacheDeleted = await caches.delete(CACHE_NAME);
  const databaseDeleted = await deleteDemoDatabase().catch((error) => ({
    error: error.message
  }));
  const cookieResponse = await fetch("/clear-cookie", {
    credentials: "same-origin",
    cache: "no-store"
  });

  show({
    localAndSessionKeysRemoved: true,
    demoCookieExpired: cookieResponse.ok,
    demoCacheDeleted: cacheDeleted,
    demoDatabaseDeleted: databaseDeleted,
    note: "Cache của Service Worker có tên riêng và được dọn độc lập sau khi unregister."
  });
}

document.querySelector("#populate").addEventListener("click", () => {
  populateDemoData().catch((error) => show({ error: error.message }));
});

document.querySelector("#inspect").addEventListener("click", () => {
  inspectStorage().catch((error) => show({ error: error.message }));
});

document.querySelector("#register").addEventListener("click", () => {
  registerWorker().catch((error) => show({ error: error.message }));
});

document.querySelector("#unregister").addEventListener("click", () => {
  unregisterLabWorker().catch((error) => show({ error: error.message }));
});

document.querySelector("#cleanup").addEventListener("click", () => {
  cleanupDemoData().catch((error) => show({ error: error.message }));
});

if ("serviceWorker" in navigator) {
  navigator.serviceWorker.addEventListener("controllerchange", () => {
    controllerLabel.textContent = "controller đã thay đổi";
  });

  controllerLabel.textContent = navigator.serviceWorker.controller
    ? navigator.serviceWorker.controller.scriptURL
    : "chưa có controller";
}
~~~

Mã này chỉ tạo và xóa các key có prefix lab_ cùng database/cache mang tên dành riêng cho lab. Nó không xóa toàn bộ storage của origin.

### 2.7. Chạy ứng dụng

Tại thư mục storage-sw-lab, chạy:

~~~powershell
node .\server.js
~~~

Mở:

~~~text
http://127.0.0.1:8080/
~~~

Mở DevTools trước khi bắt đầu. Chọn Application (Chrome/Edge) hoặc Storage (Firefox) tùy trình duyệt.

## 3. Kiểm kê Web Storage

### 3.1. localStorage

localStorage lưu các cặp key/value dạng chuỗi theo origin. Dữ liệu thường tồn tại qua reload và lần mở trình duyệt tiếp theo, trừ khi người dùng hoặc trình duyệt xóa dữ liệu.

Trong lab, bấm Tạo dữ liệu demo rồi chạy trong Console:

~~~javascript
Object.keys(localStorage)
  .filter((key) => key.startsWith("lab_"))
  .map((key) => ({
    key,
    value: localStorage.getItem(key)
  }));
~~~

Kiểm tra:

- Key có tên rõ ràng và có namespace của ứng dụng không?
- Giá trị có chứa token, mật khẩu, dữ liệu định danh hoặc thông tin nhạy cảm không?
- Dữ liệu có được xóa khi logout hoặc khi hết hạn không?
- Có key cũ của phiên bản trước còn tồn tại không?
- Ứng dụng có parse JSON an toàn và xử lý dữ liệu hỏng không?

localStorage là API đồng bộ. Truy cập nhiều hoặc lưu dữ liệu lớn trên main thread có thể làm giao diện chậm. Không lưu access token hoặc refresh token dài hạn trong localStorage nếu có thể tránh; JavaScript cùng origin, bao gồm mã XSS, có thể đọc chúng.

### 3.2. sessionStorage

sessionStorage được phân vùng theo origin và top-level browsing context. Dữ liệu thường tồn tại khi reload tab nhưng bị xóa khi tab/window kết thúc. Một tab mới có thể nhận bản sao ban đầu từ opener trong một số cách mở tab, nhưng sau đó thay đổi không đồng bộ giữa hai tab.

Trong lab, bấm Tạo dữ liệu demo rồi chạy:

~~~javascript
Object.keys(sessionStorage)
  .filter((key) => key.startsWith("lab_"))
  .map((key) => ({
    key,
    value: sessionStorage.getItem(key)
  }));
~~~

Thử:

1. Reload tab hiện tại và kiểm tra key lab_tab_state.
2. Mở URL lab trong tab mới và kiểm tra sessionStorage.
3. Mở tab mới bằng thao tác có opener nếu muốn quan sát hành vi khởi tạo bản sao; kết quả phụ thuộc cách mở tab và trình duyệt.
4. Thay đổi key trong một tab và kiểm tra tab còn lại.

Không dùng sessionStorage để lưu bí mật với giả định dữ liệu không thể bị XSS đọc. Nó chỉ giới hạn vòng đời và browsing context.

### 3.3. Storage event

Sự kiện storage được phát ở các document khác cùng storage area khi một tab thay đổi localStorage. Nó không được phát trong chính tab thực hiện thay đổi. sessionStorage không đồng bộ giữa các tab thông thường, nên không dùng storage event như kênh đồng bộ sessionStorage xuyên tab.

Ví dụ kiểm tra localStorage event:

~~~javascript
window.addEventListener("storage", (event) => {
  console.log({
    key: event.key,
    oldValue: event.oldValue,
    newValue: event.newValue,
    url: event.url
  });
});
~~~

Mở lab ở hai tab cùng origin. Trong một tab chạy:

~~~javascript
localStorage.setItem("lab_sync_probe", "changed");
~~~

Tab còn lại nhận storage event. Xóa key sau khi kiểm tra:

~~~javascript
localStorage.removeItem("lab_sync_probe");
~~~

Không ghi nội dung nhạy cảm vào log event hoặc console trong môi trường thật.

## 4. Kiểm tra cookie

### 4.1. Cookie có thể đọc bằng JavaScript

Trong lab, cookie lab_preference được tạo bằng document.cookie. Kiểm tra:

~~~javascript
document.cookie;
~~~

Cookie này không có HttpOnly nên JavaScript có thể nhìn thấy trong document.cookie khi domain/path phù hợp. Hãy mở Application/Storage > Cookies để xem các thuộc tính.

### 4.2. Cookie HttpOnly

Bấm Tạo dữ liệu demo để server trả cookie lab_http_only có HttpOnly. Sau đó so sánh:

- document.cookie không hiển thị lab_http_only.
- DevTools vẫn có thể hiển thị cookie và thuộc tính của nó.
- Request đến cùng host/path phù hợp có thể tự gửi cookie theo quy tắc trình duyệt.
- Server có thể đọc cookie trong request.

HttpOnly ngăn JavaScript trang đọc cookie trực tiếp. Nó không ngăn XSS gửi request đã xác thực bằng cookie đó. Vì vậy, vẫn cần output encoding, CSP, Trusted Types phù hợp, CSRF protection và authorization phía server. Lab không đặt Secure vì server chạy HTTP trên loopback; cookie production cần Secure và HTTPS.

### 4.3. Thuộc tính cần kiểm tra

| Thuộc tính | Câu hỏi kiểm tra |
|---|---|
| Secure | Cookie có chỉ được gửi qua HTTPS không? |
| HttpOnly | Cookie phiên có tránh bị JavaScript đọc trực tiếp không? |
| SameSite | Cookie có được gửi trong ngữ cảnh cross-site nào? |
| Domain | Cookie có bị mở rộng đến subdomain không cần thiết không? |
| Path | Cookie có phạm vi path rộng hơn nhu cầu không? |
| Expires/Max-Age | Thời hạn có phù hợp và có giới hạn không? |
| Prefix __Host- | Có Secure, Path=/ và không có Domain không? |
| Prefix __Secure- | Có được đặt qua secure origin theo yêu cầu prefix không? |

Cookie không được phân vùng theo port. Nếu ứng dụng có nhiều service trên các port khác nhau của cùng host, cần hiểu rằng cookie phù hợp có thể được gửi đến nhiều port. Không dùng port để cô lập cookie giữa các ứng dụng.

SameSite và site không giống origin. Hai subdomain khác nhau có thể là cross-origin nhưng vẫn same-site. Cần kiểm tra cả schemeful site, domain và ngữ cảnh điều hướng thực tế.

### 4.4. Cookie và CSRF

Cookie được browser tự động đính kèm khi request phù hợp domain/path và chính sách cookie. Một trang khác có thể kích hoạt một số request cross-site dù JavaScript của trang đó không đọc được response.

Với endpoint thay đổi trạng thái:

- Không dùng GET để thực hiện hành động thay đổi dữ liệu.
- Dùng CSRF token hoặc cơ chế bảo vệ đã được đánh giá.
- Kiểm tra Origin/Referer và Fetch Metadata khi phù hợp.
- Cấu hình SameSite theo yêu cầu, nhưng không xem nó là lớp duy nhất.
- Xác minh quyền của người dùng ở phía server.

CORS kiểm soát việc đọc response từ JavaScript cross-origin; nó không ngăn mọi request cross-origin được gửi.

## 5. Kiểm tra IndexedDB

### 5.1. IndexedDB lưu dữ liệu gì?

IndexedDB là kho dữ liệu bất đồng bộ theo origin, hỗ trợ object store, index và transaction. Ứng dụng có thể dùng nó cho dữ liệu offline, bản nháp, hàng đợi đồng bộ hoặc dữ liệu có cấu trúc.

Trong DevTools, mở Application/Storage > IndexedDB > storage-sw-lab > notes. Kiểm tra:

- Database name và version.
- Object store và keyPath.
- Số record và loại dữ liệu.
- Có dữ liệu nhạy cảm hoặc token không?
- Có record cũ sau logout hoặc đổi tài khoản không?
- Migration schema có được kiểm soát không?

Trong Console, đọc record demo:

~~~javascript
const request = indexedDB.open("storage-sw-lab", 1);

request.onsuccess = () => {
  const db = request.result;
  const transaction = db.transaction("notes", "readonly");
  const readRequest = transaction.objectStore("notes").getAll();

  readRequest.onsuccess = () => console.table(readRequest.result);
  transaction.oncomplete = () => db.close();
};
~~~

### 5.2. Xóa database có kiểm soát

Chỉ xóa database dành riêng cho lab:

~~~javascript
const deleteRequest = indexedDB.deleteDatabase("storage-sw-lab");

deleteRequest.onsuccess = () => console.log("Đã xóa database lab");
deleteRequest.onerror = () => console.error(deleteRequest.error);
deleteRequest.onblocked = () => {
  console.warn("Một tab hoặc connection khác đang giữ database mở");
};
~~~

Nếu onblocked xuất hiện, đóng các tab lab hoặc đóng kết nối database đang mở rồi thử lại. Trong ứng dụng thật, cần xử lý sự kiện versionchange để tab cũ đóng kết nối khi có migration.

Không xóa database chỉ vì tên lạ. Trước khi xóa, ghi nhận tên, version, owner và dữ liệu bị ảnh hưởng.

### 5.3. Dữ liệu nhạy cảm và XSS

IndexedDB không phải kho bí mật. JavaScript cùng origin có thể truy cập database mà ứng dụng được phép mở. XSS có thể đọc hoặc thay đổi record, kể cả khi dữ liệu được lưu dưới dạng object thay vì chuỗi.

Nếu cần lưu dữ liệu nhạy cảm offline, phải đánh giá threat model thiết bị, khóa mã hóa, vòng đời khóa, khả năng XSS, logout, đồng bộ và xóa dữ liệu. Mã hóa dữ liệu bằng khóa mà JavaScript cùng origin có thể lấy được không tự động bảo vệ trước XSS.

## 6. Kiểm tra CacheStorage

### 6.1. Liệt kê cache và request

Sau khi đăng ký Service Worker, worker tạo cache storage-sw-lab-worker-v1 và app tạo cache storage-sw-lab-demo-data. Bấm Kiểm kê storage hoặc chạy:

~~~javascript
const names = await caches.keys();

const inventory = [];

for (const name of names) {
  if (!name.startsWith("storage-sw-lab-")) continue;

  const cache = await caches.open(name);
  const requests = await cache.keys();

  inventory.push({
    name,
    urls: requests.map((request) => request.url)
  });
}

console.table(inventory);
~~~

Mở Application/Storage > Cache Storage và kiểm tra:

- Tên cache có namespace và version không?
- Cache chứa asset công khai hay response theo tài khoản?
- Có URL API, URL có query nhạy cảm hoặc response chứa dữ liệu cá nhân không?
- Có cache cũ không còn được dùng?
- Cache có thể bị ghi đè bởi request hoặc nội dung không tin cậy không?
- Có chính sách dọn cache khi logout, đổi tenant hoặc cập nhật không?

### 6.2. CacheStorage và HTTP cache khác nhau

CacheStorage là API lưu trữ do ứng dụng hoặc Service Worker quản lý. HTTP cache là cache của trình duyệt/proxy tuân theo header như Cache-Control, ETag và Last-Modified. Xóa một loại không đồng nghĩa loại kia được xóa.

Một request có thể được phục vụ từ CacheStorage bởi Service Worker trước khi HTTP cache hoặc network được sử dụng. Khi điều tra response cũ, kiểm tra cả:

- CacheStorage.
- Network tab và cột Size/Transferred.
- Response header Cache-Control, ETag, Age và Vary.
- Service Worker fetch handler.
- CDN hoặc reverse proxy phía server.

### 6.3. Không cache response riêng tư tùy tiện

Không cache chung response phụ thuộc cookie, Authorization, user ID, tenant hoặc quyền truy cập. Nếu ứng dụng cần offline data, phải có thiết kế phân vùng theo người dùng, hết hạn, logout cleanup, xóa khi đổi tài khoản và xử lý thiết bị dùng chung.

Không dựa vào việc cache URL giống nhau để giả định dữ liệu giống nhau. Response có thể phụ thuộc header, cookie, locale hoặc danh tính. Cần xác định cache key và policy rõ ràng.

## 7. Kiểm tra Service Worker registration và controller

### 7.1. Đăng ký và scope

Bấm Đăng ký Service Worker. Mở Application > Service Workers hoặc Storage > Service Workers tùy trình duyệt.

Kiểm tra:

- Script URL: /sw.js.
- Scope: /.
- State: installing, installed, activating, activated hoặc redundant.
- Registration có active, waiting hoặc installing worker không?
- Trang hiện tại có controller không?
- Worker có đang xử lý navigation hoặc fetch không?

Trong Console:

~~~javascript
const registrations = await navigator.serviceWorker.getRegistrations();

console.table(registrations.map((registration) => ({
  scope: registration.scope,
  active: registration.active && registration.active.scriptURL,
  waiting: registration.waiting && registration.waiting.scriptURL,
  installing: registration.installing && registration.installing.scriptURL
})));
~~~

Kiểm tra controller của trang:

~~~javascript
navigator.serviceWorker.controller
  ? {
      scriptURL: navigator.serviceWorker.controller.scriptURL,
      state: navigator.serviceWorker.controller.state
    }
  : "Trang hiện không có controller";
~~~

Registration và controller là hai khái niệm khác nhau. Một registration có thể có active worker nhưng trang hiện tại chưa được worker đó điều khiển cho đến khi trang điều hướng hoặc worker claim client. Hãy kiểm tra cả hai.

### 7.2. Scope không phải storage boundary

Scope xác định các URL/client worker có thể điều khiển. Nó không tạo một kho CacheStorage riêng. Các worker cùng origin có thể truy cập CacheStorage của origin theo API và quyền thực thi của chúng.

Ví dụ, worker có scope /app/ chỉ điều khiển client trong phạm vi phù hợp với /app/, nhưng code worker vẫn có thể gọi caches.keys() để liệt kê các cache của origin. Vì vậy, namespace cache và quy tắc dọn cache cần tránh xung đột giữa các ứng dụng cùng origin.

### 7.3. Worker và origin

Service Worker script phải cùng origin với trang đăng ký, trừ các quy tắc đặc biệt không nên dựa vào trong thiết kế thông thường. Service Worker cần secure context; HTTPS được dùng trong production, localhost/loopback dùng cho phát triển.

Một worker có thể can thiệp request trong scope, trả cache response, chuyển request ra network hoặc trả fallback. Vì vậy, kiểm tra nội dung script và fetch handler quan trọng không kém việc kiểm tra registration.

### 7.4. Theo dõi trạng thái và update

Trong Console:

~~~javascript
const registration = await navigator.serviceWorker.getRegistration();

if (registration) {
  console.log({
    scope: registration.scope,
    active: registration.active && registration.active.state,
    waiting: registration.waiting && registration.waiting.state,
    installing: registration.installing && registration.installing.state
  });

  registration.addEventListener("updatefound", () => {
    const worker = registration.installing;

    if (worker) {
      worker.addEventListener("statechange", () => {
        console.log("Worker state:", worker.state);
      });
    }
  });
}
~~~

Một worker mới có thể ở waiting khi worker cũ vẫn điều khiển tab. Đừng gọi skipWaiting một cách tùy tiện trong lúc điều tra; việc đó thay đổi trạng thái hệ thống và có thể ảnh hưởng các tab đang mở.

## 8. Kiểm tra hành vi fetch và Network

### 8.1. Quan sát request được Service Worker xử lý

Trong Network, bật cột hoặc bộ lọc cho Service Worker nếu trình duyệt hỗ trợ. Reload trang sau khi worker active.

Kiểm tra:

- Request navigation có đi qua Service Worker không?
- Response đến từ ServiceWorker hay network?
- Offline fallback có được trả khi tắt network không?
- Worker có tạo request đến endpoint không cần thiết không?
- API response có bị cache không?
- Có request bị chuyển hướng hoặc sửa URL không?

Thử offline:

1. Mở Network và bật Offline trong DevTools.
2. Reload trang.
3. Worker trả /offline.html nếu navigation được điều khiển và tài nguyên đã precache.
4. Tắt Offline và reload lại.

Đừng dùng thao tác offline trên hồ sơ trình duyệt chứa phiên công việc đang hoạt động.

### 8.2. Xem request và response từ worker

Trong DevTools, kiểm tra request URL, method, initiator, status, response headers và nội dung response. Nếu response khác dự kiến, kiểm tra fetch handler theo thứ tự:

1. Điều kiện method.
2. Origin và scope.
3. URL/path matching.
4. Cache name và cache match.
5. Network fallback.
6. Response clone/put.
7. Error handling.

Không log body hoặc cookie nhạy cảm khi debug. Ghi request ID và loại lỗi thay cho dữ liệu bí mật.

### 8.3. Kiểm tra CSP và security headers

Service Worker script và document chịu các chính sách bảo mật liên quan. Với ứng dụng web:

- CSP của document cần có worker-src phù hợp với nguồn Service Worker.
- Script worker cần được phục vụ với MIME type JavaScript đúng.
- X-Content-Type-Options: nosniff giúp tránh một số cách diễn giải MIME không mong muốn.
- HTTPS phải được dùng trong production.
- Không cho worker tải mã thực thi tùy ý từ nguồn không tin cậy.
- Kiểm tra Cache-Control của sw.js để trình duyệt có thể kiểm tra update theo kế hoạch.

CSP không thay thế việc kiểm soát script URL, scope và nội dung worker. Nếu worker bị thay đổi độc hại trên server hoặc qua quy trình phát hành, CSP cùng origin không tự chứng minh nội dung worker là an toàn.

## 9. Kiểm tra ranh giới origin và site

### 9.1. Hai port là hai origin

Chạy cùng một server trên một port khác hoặc dùng một server dev khác, ví dụ:

- http://127.0.0.1:8080
- http://127.0.0.1:8081

Dữ liệu localStorage, sessionStorage, IndexedDB và CacheStorage ở hai origin không chia sẻ theo cơ chế origin storage thông thường. Service Worker registration cũng tách theo origin.

Cookie có thể được gửi tới cả hai port vì cookie không phân vùng theo port. Hãy kiểm tra cookie host/path/secure thay vì giả định port tạo vùng cookie riêng.

### 9.2. Path khác nhau vẫn cùng origin

Hai URL:

- http://127.0.0.1:8080/app/
- http://127.0.0.1:8080/admin/

cùng origin. localStorage và IndexedDB không được cô lập theo path. Service Worker scope có thể giới hạn client được điều khiển, nhưng không làm cho Web Storage trở thành kho riêng của từng path.

Nếu nhiều ứng dụng không tin cậy cùng host, cân nhắc tách origin bằng subdomain hoặc host riêng và cấu hình cookie Domain thật chặt. Không dựa vào path để cô lập dữ liệu có mức tin cậy khác nhau.

### 9.3. Site và third-party storage

Một số chính sách cookie và storage dùng khái niệm site thay vì origin. Trình duyệt hiện đại có thể partition hoặc hạn chế third-party cookie/storage. Kết quả phụ thuộc trình duyệt, cấu hình quyền riêng tư và ngữ cảnh nhúng.

Khi kiểm thử:

- Phân biệt top-level navigation với iframe third-party.
- Ghi lại top-level site và embedded origin.
- Kiểm tra cookie SameSite, Secure và third-party cookie policy.
- Không kết luận hai origin chia sẻ dữ liệu chỉ vì chúng cùng registrable domain.
- Không kết luận storage luôn có sẵn trong iframe cross-site.

## 10. Dọn storage và Service Worker an toàn

### 10.1. Dọn từng loại dữ liệu

Dùng DevTools để xóa theo key hoặc store khi có thể. Với ứng dụng thật, xác định owner và mục đích dữ liệu trước khi xóa.

| Loại | Cleanup có mục tiêu | Kiểm tra sau cleanup |
|---|---|---|
| localStorage | removeItem cho key thuộc ứng dụng | Key không còn trong danh sách |
| sessionStorage | removeItem cho key của tab | Tab hiện tại không còn key |
| Cookie | Expire đúng cookie với Domain/Path tương ứng | Cookie biến mất khỏi cookie jar |
| IndexedDB | Xóa database/store cụ thể sau khi đóng kết nối | Database/store không còn |
| CacheStorage | Xóa cache có namespace của ứng dụng | Cache và request entry không còn |
| Service Worker | unregister đúng registration/scope | Registration không còn sau kiểm tra |
| HTTP cache | Clear cache theo DevTools hoặc policy trình duyệt | Network tải lại response phù hợp |

Không xóa mọi cache hoặc mọi database trên origin nếu chưa biết ứng dụng nào sở hữu chúng.

### 10.2. Logout và đổi tài khoản

Logout cần xử lý mọi vị trí lưu trạng thái xác thực:

- Server thu hồi hoặc kết thúc session.
- Expire cookie đúng Domain và Path.
- Xóa token hoặc state tạm nếu ứng dụng có lưu.
- Xóa dữ liệu cá nhân được cache theo user.
- Xóa bản nháp hoặc hàng đợi có chứa dữ liệu tài khoản nếu policy yêu cầu.
- Ngăn tab cũ tiếp tục hiển thị dữ liệu của tài khoản trước.
- Xác minh Service Worker không phục vụ response cá nhân từ cache.

Nếu người dùng chuyển tài khoản trên cùng browser profile, cần phân vùng cache/data theo danh tính hoặc xóa dữ liệu của tài khoản cũ trước khi hiển thị dữ liệu mới. Chỉ xóa cookie không xóa localStorage, IndexedDB hoặc CacheStorage.

### 10.3. Unregister không đồng nghĩa xóa cache

ServiceWorkerRegistration.unregister() hủy registration, nhưng không tự xóa CacheStorage. Ngược lại, xóa cache không hủy registration. Worker đang điều khiển tab hiện tại có thể tiếp tục làm controller cho đến khi client điều hướng, đóng hoặc vòng đời được hoàn tất.

Trong lab, bấm Hủy registration. Sau đó bấm Kiểm kê storage và kiểm tra:

- Registration có biến mất không?
- Controller hiện tại còn không?
- Cache storage-sw-lab-worker-v1 còn không?
- Offline fallback còn được lưu không?

Sau đó reload hoặc đóng tab và kiểm tra lại controller. Xóa cache riêng bằng DevTools hoặc lệnh có namespace; không giả định unregister đã dọn mọi dữ liệu.

Để xóa riêng cache của worker sau khi registration đã được hủy, chạy:

~~~javascript
await caches.delete("storage-sw-lab-worker-v1");
~~~

Lệnh trên chỉ xóa cache có tên chính xác của lab. Trong ứng dụng thật, hãy xác minh cache owner và version trước khi xóa.

### 10.4. Clear-Site-Data

Server có thể dùng response header Clear-Site-Data để yêu cầu browser xóa một số nhóm dữ liệu của origin, ví dụ cache, cookies hoặc storage. Đây là thao tác rộng, có thể ảnh hưởng nhiều ứng dụng cùng origin và các phiên người dùng.

Chỉ sử dụng khi:

- Origin được dành riêng cho ứng dụng hoặc tác động đã được đánh giá.
- Các nhóm dữ liệu cần xóa được xác định chính xác.
- Người dùng được xử lý phù hợp nếu cần đăng xuất.
- Đã kiểm thử trên các browser mục tiêu.
- Có kế hoạch cho Service Worker registration và dữ liệu cần giữ.

Không phát Clear-Site-Data: "*" một cách tùy tiện trên shared origin. Header này không thay thế runbook xóa dữ liệu cụ thể.

## 11. Điều tra dấu hiệu bất thường

### 11.1. Dấu hiệu trong storage

- localStorage hoặc IndexedDB chứa access token/refresh token dài hạn không có lý do rõ ràng.
- Có key không thuộc namespace ứng dụng hoặc xuất hiện sau một bản cập nhật.
- Dữ liệu người dùng cũ vẫn còn sau logout.
- Nhiều bản sao dữ liệu nhạy cảm nằm trong Web Storage và CacheStorage.
- Cache chứa response API cá nhân hoặc URL có token/query secret.
- Dữ liệu được đồng bộ qua storage không có giải thích về mục đích và thời hạn.
- Một database hoặc cache tăng dung lượng bất thường.
- Ứng dụng ghi nội dung từ DOM hoặc URL vào storage mà không kiểm tra.

Một key lạ không tự động là mã độc. Hãy xác định thời điểm tạo, code path ghi dữ liệu, phiên bản ứng dụng và chức năng liên quan.

### 11.2. Dấu hiệu trong Service Worker

- Registration có script URL hoặc scope không thuộc ứng dụng.
- Worker xuất hiện sau khi cài extension hoặc truy cập website không liên quan.
- Script URL thay đổi bất ngờ.
- Worker mới có quyền kiểm soát path rộng hơn chức năng cần thiết.
- Fetch handler gửi request đến domain không được công bố.
- Worker cache trang đăng nhập, response API cá nhân hoặc nội dung biểu mẫu.
- Worker tự thay đổi điều hướng, chèn nội dung hoặc phục vụ asset cũ không giải thích được.
- Worker được cập nhật liên tục hoặc có trạng thái redundant bất thường.
- Registration còn tồn tại sau khi ứng dụng đã gỡ bỏ tính năng PWA.

Service Worker là tài nguyên theo origin. Một website có thể đăng ký worker để điều khiển URL trong scope; vì vậy, kiểm tra registration khi điều tra hành vi bất thường của một origin là cần thiết.

### 11.3. Dấu hiệu trong Network

- Request đến endpoint không có trong tài liệu ứng dụng.
- Worker tạo request nền khi người dùng không thực hiện chức năng tương ứng.
- Response được phục vụ từ cache dù ứng dụng kỳ vọng network.
- Cookie hoặc dữ liệu định danh xuất hiện trên request đến host không mong muốn.
- Có redirect, script hoặc asset tải từ domain lạ.
- Response header cache cho phép lưu dữ liệu cá nhân vào shared cache.
- Có request lặp lại bất thường sau khi tab đóng/mở hoặc sau khi worker update.

Ghi lại URL đã che query nhạy cảm, initiator, thời điểm, status, response headers và release ID. Không gửi token hoặc cookie vào báo cáo sự cố.

## 12. Quy trình kiểm tra tích hợp

Thực hiện theo thứ tự để có thể đối chiếu cùng một trạng thái ứng dụng.

### Bước 1: Ghi nhận origin và trạng thái ban đầu

- Ghi scheme, host, port và URL.
- Ghi browser và version.
- Ghi tab đang mở, trạng thái đăng nhập demo và Service Worker controller.
- Chụp danh sách storage ban đầu.

### Bước 2: Tạo dữ liệu demo

- Bấm Tạo dữ liệu demo.
- Xác minh localStorage và sessionStorage.
- Xác minh cookie có thể đọc bằng JavaScript.
- Xác minh HttpOnly cookie qua DevTools.
- Xác minh record trong IndexedDB.
- Xác minh cache entry trong CacheStorage.

### Bước 3: Đăng ký Service Worker

- Bấm Đăng ký Service Worker.
- Xác minh script URL và scope.
- Theo dõi state transitions.
- Xác minh active worker và controller.
- Xác minh cache offline được tạo.

### Bước 4: Kiểm tra fetch và offline

- Reload khi online và quan sát request.
- Bật Offline trong DevTools.
- Reload và xác minh offline fallback.
- Tắt Offline và xác minh network trở lại.
- Kiểm tra worker không cache dữ liệu nhạy cảm.

### Bước 5: Đánh giá rủi ro

- Xác định dữ liệu nhạy cảm có ở storage nào không.
- Đối chiếu cookie flags.
- Kiểm tra cache namespace, scope và script URL.
- Xem response có thể bị stale hoặc phục vụ sai user không.
- Đánh giá XSS, CSRF, logout và multi-account behavior.

### Bước 6: Cleanup có kiểm soát

- Xóa key demo.
- Xóa database demo sau khi đóng kết nối.
- Xóa cache demo theo tên.
- Expire cookie demo.
- Unregister worker nếu lab kết thúc.
- Sau khi unregister, xóa cache storage-sw-lab-worker-v1 nếu cần cleanup hoàn toàn.
- Reload và kiểm tra trạng thái cuối.

### Bước 7: Ghi kết quả

- Ghi test ID, browser/version, origin và thời điểm.
- Ghi storage key/cache/database đã kiểm tra.
- Ghi worker script URL, scope, state và controller.
- Ghi request/response liên quan đã che dữ liệu nhạy cảm.
- Ghi kết luận, mức độ ảnh hưởng và hành động khắc phục.

## 13. Ma trận kiểm thử

| ID | Thành phần | Tình huống | Kết quả mong đợi |
|---|---|---|---|
| ST-01 | Origin | Hai port khác nhau | Web Storage, IndexedDB và CacheStorage tách origin |
| ST-02 | localStorage | Reload trang | Key demo còn tồn tại |
| ST-03 | sessionStorage | Reload tab | Key demo còn trong tab |
| ST-04 | sessionStorage | Mở tab độc lập | Không mặc định chia sẻ thay đổi giữa hai tab |
| ST-05 | Cookie | Đọc document.cookie | Cookie HttpOnly không xuất hiện |
| ST-06 | Cookie | Request cùng host/path | Cookie phù hợp được gửi theo policy |
| ST-07 | Cookie | So sánh port | Cookie không được cô lập theo port |
| ST-08 | IndexedDB | Đọc record | Record demo được trả về |
| ST-09 | IndexedDB | Xóa database khi connection mở | Có thể bị blocked cho đến khi connection đóng |
| ST-10 | CacheStorage | Liệt kê cache | Cache theo namespace được nhìn thấy |
| ST-11 | CacheStorage | Xóa một cache | Cache khác của origin còn nguyên |
| ST-12 | Service Worker | Đăng ký lần đầu | Worker install và activate |
| ST-13 | Service Worker | Kiểm tra controller | Script URL và state đúng |
| ST-14 | Service Worker | Offline navigation | Offline fallback được trả |
| ST-15 | Service Worker | Unregister | Registration bị hủy; cache không tự xóa |
| ST-16 | Service Worker | Reload sau unregister | Trang không còn controller khi client chuyển vòng đời phù hợp |
| ST-17 | Logout | Xóa cookie nhưng giữ storage | Dữ liệu Web Storage/IDB/cache vẫn cần cleanup riêng |
| ST-18 | Cache | Response cá nhân | Không được lưu vào cache dùng chung |
| ST-19 | Network | Worker fetch event | Request chỉ được xử lý theo route/method đã định |
| ST-20 | Cleanup | Dọn dữ liệu demo | Chỉ key/database/cache của lab bị xóa |

### 13.1. Tiêu chí PASS

Một test chỉ PASS khi:

- Origin và phạm vi storage được xác định đúng.
- Không có secret hoặc dữ liệu cá nhân không cần thiết trong storage.
- Cookie có thuộc tính phù hợp và được gửi theo đúng policy.
- IndexedDB và CacheStorage có owner, namespace và cleanup rõ ràng.
- Service Worker có script URL, scope và hành vi fetch mong đợi.
- Unregister, cache deletion và data cleanup được kiểm tra riêng.
- Network không cho thấy request hoặc response bất thường.
- Kết quả có bằng chứng và không lộ dữ liệu nhạy cảm.

Không đánh dấu PASS chỉ vì trang tải thành công. Cần kiểm tra cả dữ liệu tồn dư sau logout, trạng thái offline và hành vi khi Service Worker không còn registration.

## 14. Mẫu biên bản kiểm tra

| Trường | Nội dung cần ghi |
|---|---|
| Test ID | ST-xx |
| Ngày giờ | Thời điểm và múi giờ |
| Browser | Tên, version, profile |
| Origin | Scheme, host, port |
| Application release | Release ID hoặc commit |
| Storage inspected | Cookie, localStorage, sessionStorage, IndexedDB, CacheStorage |
| Sensitive data | Loại dữ liệu, vị trí, có/không |
| Service Worker | Script URL, scope, state, controller |
| Cache | Tên cache và URL entry |
| Network evidence | Request, initiator, status, response source |
| Cleanup | Key/database/cache/registration đã xử lý |
| Result | PASS/FAIL và lý do |
| Remediation | Owner, hành động và thời hạn |

Bằng chứng cần che token, cookie value, email, user ID, query nhạy cảm và nội dung tài liệu. Chỉ giữ dữ liệu tối thiểu đủ để tái hiện vấn đề.

## 15. Những lỗi thường gặp

**Cho rằng HttpOnly làm cookie biến mất khỏi DevTools.** HttpOnly ngăn JavaScript đọc cookie qua document.cookie; DevTools và server vẫn có thể quan sát cookie theo quyền phù hợp.

**Cho rằng localStorage an toàn vì không tự gửi lên server.** XSS chạy cùng origin có thể đọc và gửi dữ liệu localStorage. Việc không tự đính kèm vào request không làm dữ liệu trở thành bí mật.

**Cho rằng sessionStorage an toàn hơn trước XSS.** sessionStorage giới hạn browsing context và vòng đời, nhưng JavaScript cùng origin vẫn đọc được.

**Cho rằng IndexedDB mã hóa dữ liệu.** IndexedDB lưu object theo origin; API không tự mã hóa dữ liệu để chống XSS.

**Cho rằng xóa cookie sẽ xóa toàn bộ phiên phía client.** localStorage, IndexedDB, CacheStorage và Service Worker registration có vòng đời riêng.

**Cho rằng unregister Service Worker sẽ xóa cache.** Registration và CacheStorage là hai cơ chế khác nhau. Cần cleanup cả hai nếu policy yêu cầu.

**Cho rằng scope giới hạn CacheStorage.** Scope giới hạn client mà worker điều khiển; CacheStorage là kho theo origin.

**Cho rằng hai port khác nhau có cookie jar riêng.** Cookie không phân vùng theo port, dù Web Storage và IndexedDB phân vùng theo origin.

**Cho rằng offline cache luôn an toàn.** Cache có thể giữ response cá nhân hoặc nội dung cũ. Cần namespace, policy, expiry và cleanup.

**Xóa toàn bộ site data ngay khi thấy key lạ.** Cần xác định owner và tác động trước khi xóa để không làm mất dữ liệu cần điều tra hoặc phá ứng dụng khác cùng origin.

## 16. Checklist đánh giá cuối cùng

### Storage

- [ ] Xác định origin và profile đang kiểm tra.
- [ ] Liệt kê localStorage và sessionStorage.
- [ ] Kiểm tra cookie flags và cookie domain/path.
- [ ] Xác định cookie HttpOnly qua DevTools hoặc server.
- [ ] Kiểm tra IndexedDB database, version, store và record.
- [ ] Kiểm tra CacheStorage name và request entries.
- [ ] Tìm token, dữ liệu cá nhân và dữ liệu tồn dư.
- [ ] Kiểm tra cleanup khi logout và đổi tài khoản.

### Service Worker

- [ ] Xác minh script URL và scope.
- [ ] Kiểm tra installing, waiting, active và redundant.
- [ ] Xác minh controller của tab.
- [ ] Kiểm tra fetch handler và network initiator.
- [ ] Kiểm tra offline fallback.
- [ ] Kiểm tra update và asset cũ.
- [ ] Kiểm tra cache namespace và dữ liệu được lưu.
- [ ] Xác minh unregister và cache cleanup độc lập.

### Khắc phục và bằng chứng

- [ ] Chỉ xóa dữ liệu thuộc ứng dụng hoặc lab đã xác định.
- [ ] Không ghi secret vào console, log hoặc ảnh chụp.
- [ ] Giữ bằng chứng trước cleanup khi có sự cố.
- [ ] Kiểm tra lại sau cleanup.
- [ ] Ghi owner, mức độ ảnh hưởng và remediation.
- [ ] Xác minh trên browser/version mục tiêu.

## 17. Câu hỏi tự kiểm tra

### Câu 1

localStorage được phân vùng theo yếu tố nào?

A. Chỉ theo path.  
B. Theo origin gồm scheme, host và port.  
C. Theo IP client.  
D. Theo tên tab.

**Đáp án: B.** localStorage là storage theo origin; path không tạo vùng tách biệt.

### Câu 2

Hai ứng dụng ở cùng host nhưng khác port có chia sẻ localStorage không?

A. Có, vì host giống nhau.  
B. Không, vì port là một phần của origin.  
C. Chỉ khi dùng cookie HttpOnly.  
D. Chỉ khi cùng path.

**Đáp án: B.** Hai port khác nhau tạo hai origin khác nhau cho Web Storage.

### Câu 3

Cookie có được cô lập theo port không?

A. Có, giống localStorage.  
B. Không; cookie được xác định bởi domain/host, path và các thuộc tính khác, không theo port.  
C. Chỉ cookie Secure mới theo port.  
D. Chỉ cookie HttpOnly mới theo port.

**Đáp án: B.** Không dùng port để cô lập cookie giữa các ứng dụng cùng host.

### Câu 4

HttpOnly bảo vệ điều gì?

A. Ngăn mọi request gửi cookie.  
B. Ngăn JavaScript trang đọc cookie qua document.cookie.  
C. Mã hóa cookie trong DevTools.  
D. Ngăn XSS thực hiện request đã xác thực.

**Đáp án: B.** HttpOnly giảm khả năng đánh cắp giá trị cookie trực tiếp, nhưng XSS vẫn có thể thực hiện hành động trong phiên.

### Câu 5

IndexedDB có tự mã hóa dữ liệu để chống XSS không?

A. Có, mặc định.  
B. Không; JavaScript cùng origin có thể truy cập database mà ứng dụng được phép mở.  
C. Chỉ khi database lớn hơn 1 MB.  
D. Chỉ trong chế độ private.

**Đáp án: B.** IndexedDB là storage API, không phải lớp bảo vệ bí mật trước mã chạy cùng origin.

### Câu 6

Unregister Service Worker có tự xóa CacheStorage không?

A. Có, xóa mọi cache của origin.  
B. Không; registration và CacheStorage phải được xử lý riêng.  
C. Chỉ xóa cache HTTP.  
D. Chỉ xóa localStorage.

**Đáp án: B.** Hủy registration không tự động xóa cache do ứng dụng quản lý.

### Câu 7

Service Worker scope giới hạn điều gì?

A. Tất cả database của origin.  
B. Những client/URL worker có thể điều khiển.  
C. Cookie domain.  
D. localStorage path.

**Đáp án: B.** Scope điều khiển phạm vi client, không tạo storage namespace riêng.

### Câu 8

Sau logout, cookie đã bị expire nhưng dữ liệu profile vẫn còn trong IndexedDB. Điều gì cần làm?

A. Không cần vì cookie đã mất.  
B. Áp dụng cleanup dữ liệu theo user trong IndexedDB và các storage khác theo policy.  
C. Chỉ reload trang.  
D. Đổi port của API.

**Đáp án: B.** Mỗi loại storage có vòng đời riêng; logout phải xử lý dữ liệu còn tồn dư.

### Câu 9

Hai URL khác path nhưng cùng scheme, host và port có cùng origin không?

A. Không, path là một phần origin.  
B. Có, path không tham gia xác định origin.  
C. Chỉ khi dùng HTTPS.  
D. Chỉ khi cùng cookie.

**Đáp án: B.** Origin gồm scheme, host và port.

### Câu 10

Một Service Worker cache response API có chứa thông tin tài khoản. Rủi ro chính là gì?

A. CacheStorage tự động xóa response.  
B. Dữ liệu riêng tư có thể tồn tại trên thiết bị hoặc bị phục vụ sai user nếu cache không được phân vùng và cleanup đúng.  
C. Browser tự chuyển response thành public.  
D. CORS tự mã hóa cache.

**Đáp án: B.** Cache cần được thiết kế theo danh tính, thời hạn, logout và quyền riêng tư.

### Câu 11

Khi xóa IndexedDB database, sự kiện onblocked thường gợi ý điều gì?

A. Browser đã xóa database thành công.  
B. Một kết nối khác đang giữ database mở và cản trở thao tác xóa/nâng version.  
C. Cookie HttpOnly bị lỗi.  
D. Service Worker đã unregister.

**Đáp án: B.** Cần đóng kết nối ở các tab liên quan rồi thực hiện lại theo quy trình.

### Câu 12

Khi điều tra worker lạ, bằng chứng nào hữu ích nhất?

A. Chỉ tên hiển thị của website.  
B. Script URL, scope, state, controller, fetch behavior, cache entries và thời điểm xuất hiện.  
C. Màu favicon.  
D. Số lượng tab đang mở.

**Đáp án: B.** Các dữ liệu này giúp xác định worker thuộc ứng dụng nào và có thể điều khiển request nào.

## 18. Thuật ngữ cần nhớ

| Thuật ngữ | Ý nghĩa |
|---|---|
| Origin | Bộ ba scheme, host và port |
| Site | Khái niệm dùng trong một số chính sách cookie và privacy, khác origin |
| Cookie jar | Kho cookie do trình duyệt quản lý |
| HttpOnly | Thuộc tính ngăn JavaScript đọc cookie trực tiếp |
| SameSite | Thuộc tính kiểm soát gửi cookie trong ngữ cảnh same-site/cross-site |
| localStorage | Kho key/value đồng bộ theo origin |
| sessionStorage | Kho key/value theo origin và browsing context |
| IndexedDB | Cơ sở dữ liệu bất đồng bộ theo origin |
| CacheStorage | API lưu các Cache object theo origin |
| Service Worker | Worker do trình duyệt quản lý để xử lý sự kiện và request trong scope |
| Registration | Đăng ký Service Worker gắn với script URL và scope |
| Scope | Phạm vi URL/client worker có thể điều khiển |
| Controller | Service Worker đang điều khiển một document |
| Precache | Tài nguyên được tải và lưu trước, thường trong install event |
| Storage estimate | Ước lượng dung lượng sử dụng và quota do browser cung cấp |
| Cleanup | Xóa dữ liệu theo phạm vi và policy đã xác định |
| Stale cache | Nội dung cache cũ không còn phù hợp với phiên bản hoặc trạng thái hiện tại |

## Tài liệu tham khảo

- MDN Web Docs — [Storage API](https://developer.mozilla.org/en-US/docs/Web/API/Storage_API): tổng quan storage và quota của trình duyệt.
- MDN Web Docs — [Web Storage API](https://developer.mozilla.org/en-US/docs/Web/API/Web_Storage_API): localStorage, sessionStorage và storage event.
- MDN Web Docs — [IndexedDB API](https://developer.mozilla.org/en-US/docs/Web/API/IndexedDB_API): database và transaction phía client.
- MDN Web Docs — [Cache](https://developer.mozilla.org/en-US/docs/Web/API/Cache): lưu và truy xuất response bằng Cache API.
- MDN Web Docs — [CacheStorage](https://developer.mozilla.org/en-US/docs/Web/API/CacheStorage): quản lý tập cache theo origin.
- MDN Web Docs — [Service Worker API](https://developer.mozilla.org/en-US/docs/Web/API/Service_Worker_API): registration, scope, lifecycle và fetch event.
- MDN Web Docs — [Using Service Workers](https://developer.mozilla.org/en-US/docs/Web/API/Service_Worker_API/Using_Service_Workers): cách đăng ký và kiểm tra Service Worker.
- MDN Web Docs — [HTTP cookies](https://developer.mozilla.org/en-US/docs/Web/HTTP/Cookies): thuộc tính cookie, HttpOnly, Secure và SameSite.
- MDN Web Docs — [StorageManager.estimate()](https://developer.mozilla.org/en-US/docs/Web/API/StorageManager/estimate): ước lượng dung lượng storage.
- WHATWG — [HTML Standard: Web Storage](https://html.spec.whatwg.org/multipage/webstorage.html): quy tắc localStorage và sessionStorage.
- WHATWG — [Fetch Standard](https://fetch.spec.whatwg.org/): request, credentials, cache và các quy tắc fetch.
- W3C — [Service Workers specification](https://w3c.github.io/ServiceWorker/): registration, scope, update và lifecycle.

Các giới hạn quota, partitioning, DevTools và chính sách cookie có thể khác giữa trình duyệt. Ghi rõ browser/version trong biên bản và xác minh bằng hành vi thực tế thay vì suy luận chỉ từ tên storage.

