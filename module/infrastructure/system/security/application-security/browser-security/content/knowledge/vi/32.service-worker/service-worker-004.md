# Fetch interception: điều phối request và response bằng Service Worker

> **Chương:** Service worker  
> **Học phần:** SECURITY_APPLICATION_SECURITY_BROWSER_SECURITY — phân tích ranh giới bảo mật giữa trình duyệt, origin, cookie và ứng dụng web để hiểu Same-Origin Policy, CORS và các cơ chế cách ly; thực hành phòng vệ XSS, CSRF, clickjacking bằng CSP, Trusted Types, security headers và kiểm chứng hành vi thực tế.

**Fetch interception** là khả năng Service Worker nhận sự kiện fetch từ các trang đang được nó kiểm soát, sau đó quyết định để browser xử lý request theo mặc định hay tự cung cấp một response. Service Worker có thể trả response từ Cache API, gọi mạng rồi chuyển tiếp response, tạo response tổng hợp hoặc dùng trang dự phòng khi offline.

Đây là nền tảng cho offline support, cache chiến lược, điều phối tài nguyên và tối ưu điều hướng. Tuy nhiên, Service Worker nằm trên đường đi của request nên một lỗi routing hoặc cache key có thể làm sai nội dung, trả dữ liệu cũ, làm lộ response riêng tư hoặc khiến toàn bộ ứng dụng không tải được.

Bài này tập trung vào FetchEvent, Request/Response, respondWith(), waitUntil(), các chiến lược network-only, cache-first, network-first và stale-while-revalidate. Phần thực hành tạo ứng dụng Node.js trên localhost để quan sát request được phục vụ từ cache, đi qua network hoặc nhận trang offline.

## Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích request nào được Service Worker kiểm soát và phạm vi của fetch event.
2. Đọc các thuộc tính quan trọng của FetchEvent và Request như url, method, mode, destination, credentials và headers.
3. Gọi respondWith() đúng thời điểm và chỉ một lần cho mỗi event.
4. Phân biệt respondWith() với waitUntil() và biết khi nào cần giữ tác vụ nền.
5. Chọn chiến lược network-only, cache-first, network-first hoặc stale-while-revalidate theo loại tài nguyên.
6. Dùng Cache API an toàn, version cache và clone Request/Response đúng cách.
7. Giải thích CORS, opaque response và các giới hạn khi intercept tài nguyên cross-origin.
8. Tránh cache dữ liệu cá nhân, request không idempotent, response lỗi và nội dung không đáng tin.
9. Xử lý navigation, Range request, redirect, lỗi mạng và cache fallback.
10. Kiểm tra hành vi bằng DevTools và thực hành với một Service Worker hoàn chỉnh trên localhost.

## 1. Fetch interception hoạt động ở đâu?

### 1.1 Service Worker đứng giữa controlled page và quá trình fetch

Sau khi một Service Worker được đăng ký, cài đặt và kiểm soát một client, browser có thể phát fetch event vào global scope của worker khi client tạo request. Request có thể đến từ:

- Điều hướng trang trong phạm vi scope.
- Tải JavaScript, CSS, ảnh, font và các subresource khác.
- fetch() hoặc XMLHttpRequest được gọi từ trang.
- Request tài nguyên được tạo bởi browser khi hiển thị document.

Service Worker nhận FetchEvent chứa Request mà browser định gửi. Handler có thể gọi respondWith() để thay response mặc định bằng response do worker cung cấp.

~~~text
Trang đang được Service Worker kiểm soát
              |
              | navigation / fetch() / image / script / CSS
              v
         FetchEvent
              |
              v
     Service Worker kiểm tra Request
              |
       +------+----------------------+
       |                             |
       | Không gọi respondWith()     | Gọi respondWith(Promise<Response>)
       |                             |
       v                             v
 Browser tự fetch như bình thường   Worker chọn response
                                     |
                         +-----------+-----------+
                         |           |           |
                         v           v           v
                       Cache       Network     Response tự tạo
                         |           |           |
                         +-----------+-----------+
                                     |
                                     v
                               Trang nhận Response
~~~

Service Worker có thể hoạt động như một proxy ở phía browser, nhưng nó không phải proxy mạng tổng quát. Nó chỉ xử lý request phát sinh từ các client mà nó kiểm soát và chịu các quy tắc Fetch, SOP, CORS, secure context cùng giới hạn của Service Worker.

### 1.2 Điều kiện để request được intercept

Các điều kiện quan trọng:

- Service Worker phải được đăng ký thành công và đã active.
- Trang hoặc client phải nằm trong scope của registration và đang được worker kiểm soát.
- Service Worker chỉ hoạt động trong secure context. HTTPS là lựa chọn triển khai production; localhost/loopback được browser coi là môi trường đáng tin cậy cho phát triển.
- Request phải đi qua cơ chế fetch mà Service Worker có thể quan sát.
- Trình duyệt có thể chưa dispatch request qua worker ở lần tải đầu tiên trước khi trang được kiểm soát.

Kiểm tra trang hiện tại:

~~~js
console.log('Secure context:', window.isSecureContext);
console.log('Controller:', navigator.serviceWorker?.controller);
~~~

Nếu controller là null, trang hiện tại chưa được kiểm soát. Đăng ký thành công không đồng nghĩa mọi request của tab hiện tại lập tức được intercept. Hãy chờ worker active và controllerchange, hoặc tải lại trang theo hướng dẫn của ứng dụng.

### 1.3 Scope quyết định phạm vi kiểm soát

Ví dụ đăng ký worker ở root:

~~~js
await navigator.serviceWorker.register('/sw.js', {
  scope: '/'
});
~~~

Worker ở /sw.js có scope mặc định là thư mục chứa script, tức /. Nếu script ở /js/sw.js thì scope mặc định chỉ là /js/ và các đường dẫn con. Muốn mở rộng scope ra ngoài thư mục chứa script, server phải cho phép bằng header Service-Worker-Allowed phù hợp.

Scope là đường dẫn URL trên cùng origin. Một worker không thể kiểm soát document thuộc origin khác. Kiểm tra scope và controller trước khi kết luận fetch handler không chạy.

### 1.4 Request cross-origin có thể xuất hiện trong fetch event

Một trang được kiểm soát có thể tải ảnh hoặc gọi fetch tới origin khác. Fetch event của trang vẫn có thể được phát ra cho request đó. Tuy nhiên, việc intercept không xóa bỏ ranh giới origin:

- CORS vẫn quyết định JavaScript có được đọc response cross-origin hay không.
- Request no-cors có thể nhận opaque response, không đọc được status hoặc body.
- Service Worker không thể biến một request CORS thất bại thành response mà script được quyền đọc.
- Nếu không xử lý request cross-origin, hãy để browser fetch mặc định bằng cách không gọi respondWith().

Trong bài thực hành, worker chỉ cache tài nguyên cùng origin. Đây là lựa chọn an toàn để tập trung vào routing và Cache API.

### 1.5 Request do chính Service Worker tạo

Lời gọi fetch() từ global scope của Service Worker được gửi ra mạng và không quay vòng lại chính fetch handler của worker đó. Điều này tránh vòng lặp vô hạn khi worker gọi fetch(event.request) để lấy response từ network.

Ví dụ:

~~~js
self.addEventListener('fetch', event => {
  if (event.request.url.endsWith('/data.json')) {
    event.respondWith(fetch(event.request));
  }
});
~~~

Worker nhận request từ client, gọi fetch() để chuyển tiếp ra network rồi trả response cho client. Lời gọi fetch() bên trong worker không kích hoạt lại cùng handler.

## 2. Đọc FetchEvent và Request

### 2.1 FetchEvent cung cấp ngữ cảnh của request

Các thuộc tính hữu ích:

| Thuộc tính | Ý nghĩa |
|---|---|
| event.request | Request mà browser muốn thực hiện |
| event.clientId | ID của client cùng origin đã khởi tạo request, nếu có |
| event.resultingClientId | ID client mới sau navigation, nếu có |
| event.preloadResponse | Promise của navigation preload response, nếu preload được bật |
| event.isReload | Cho biết request navigation được tạo từ thao tác reload |
| event.handled | Promise thể hiện event đã được xử lý xong trong các browser hỗ trợ |

Không phải request nào cũng có clientId hoặc resultingClientId. Với navigation, resultingClientId có thể hữu ích để liên kết document mới với client trước đó.

### 2.2 Request có các thuộc tính giúp chọn chiến lược

~~~js
self.addEventListener('fetch', event => {
  const request = event.request;
  const url = new URL(request.url);

  console.log({
    url: url.href,
    origin: url.origin,
    method: request.method,
    mode: request.mode,
    destination: request.destination,
    credentials: request.credentials,
    cache: request.cache,
    redirect: request.redirect
  });
});
~~~

Các thuộc tính thường dùng:

| Thuộc tính | Cách dùng trong routing |
|---|---|
| url | Xác định origin, pathname và query |
| method | Thường chỉ cache GET |
| mode | Phân biệt same-origin, cors, no-cors và navigate |
| destination | Phân loại script, style, image, document, font, worker... |
| credentials | Nhận diện chính sách credential của request |
| cache | Nhận diện request có yêu cầu no-store hoặc revalidation |
| redirect | Cách Fetch xử lý redirect |
| headers | Kiểm tra Accept, Authorization, Range và header nghiệp vụ |

destination có thể là chuỗi rỗng với fetch() tổng quát. Đừng dựa vào destination một mình; hãy kết hợp URL, method và mục đích nghiệp vụ.

### 2.3 Phân biệt navigation và subresource

Navigation request thường có:

~~~js
event.request.mode === 'navigate'
~~~

Nó xảy ra khi browser tải một document cho tab hoặc iframe. Subresource request có thể có destination như script, style, image hoặc font. fetch() do ứng dụng gọi thường có destination rỗng.

Chiến lược cho navigation thường khác API:

- Navigation có thể cần network-first và offline page.
- Asset phiên bản hóa có thể dùng cache-first.
- API public có thể dùng stale-while-revalidate.
- API riêng tư hoặc request ghi dữ liệu nên đi network-only.

### 2.4 Không sửa method để ép cache

Cache API được thiết kế chủ yếu cho request GET. Hãy để POST, PUT, PATCH, DELETE và các thao tác nghiệp vụ đi qua network theo mặc định, trừ khi có một thiết kế riêng đã kiểm tra kỹ tính idempotent và semantics của request.

Một request POST có thể tạo đơn hàng, thanh toán, thay đổi hồ sơ hoặc gửi biểu mẫu. Trả response cũ từ cache có thể làm sai nghiệp vụ hoặc che giấu trạng thái server.

## 3. respondWith(): thay response mặc định

### 3.1 Gọi respondWith() ngay trong event listener

respondWith() nhận Response hoặc Promise giải quyết thành Response. Nó phải được gọi đồng bộ trong lần dispatch handler:

~~~js
self.addEventListener('fetch', event => {
  if (event.request.url.endsWith('/message.txt')) {
    event.respondWith(
      fetch(event.request)
    );
  }
});
~~~

Promise có thể thực hiện công việc bất đồng bộ. Điều bắt buộc là gọi respondWith() trước khi handler kết thúc, không đợi một await hoặc .then() bên ngoài rồi mới gọi.

Sai:

~~~js
self.addEventListener('fetch', async event => {
  await somePreparation();
  event.respondWith(fetch(event.request));
});
~~~

Đúng:

~~~js
self.addEventListener('fetch', event => {
  event.respondWith((async () => {
    await somePreparation();
    return fetch(event.request);
  })());
});
~~~

Biểu thức async được truyền vào respondWith() ngay lập tức; Promise của nó có thể hoàn tất sau.

### 3.2 Mỗi FetchEvent chỉ gọi respondWith() một lần

Nếu nhiều listener cùng đăng ký fetch event, listener được gọi theo thứ tự đăng ký. Listener đầu tiên gọi respondWith() sẽ chiếm quyền cung cấp response cho request. Gọi lần thứ hai cho cùng event có thể gây InvalidStateError.

Nên có một router tập trung để quyết định handler nào sở hữu request. Tránh nhiều module độc lập cùng cố intercept một URL mà không có quy ước thứ tự.

### 3.3 Không gọi respondWith() nghĩa là browser tự xử lý

Đây là cách pass-through đơn giản:

~~~js
self.addEventListener('fetch', event => {
  if (event.request.method !== 'GET') {
    return;
  }

  const url = new URL(event.request.url);

  if (url.origin !== self.location.origin) {
    return;
  }

  // Không gọi respondWith(): browser thực hiện request như bình thường.
});
~~~

Đây thường là lựa chọn tốt nhất cho request mà worker không cần thay đổi. Không cần viết lại mọi request chỉ để gọi fetch(event.request).

### 3.4 fetch(event.request) là pass-through có kiểm soát

Khi gọi respondWith(fetch(event.request)), worker thay thế đường fetch mặc định bằng một fetch do worker khởi tạo rồi trả response đó về client. Cách này hữu ích khi muốn quan sát lỗi hoặc bổ sung xử lý sau network.

Tuy nhiên, nếu không cần xử lý gì thêm, không gọi respondWith() sẽ đơn giản hơn. Worker vẫn nhận được event, nhưng browser tiếp tục quy trình fetch gốc.

### 3.5 Response phải phù hợp với request

Response trả về cần phù hợp với loại tài nguyên mà browser đang yêu cầu. Ví dụ, request image cần body ảnh hợp lệ; request document cần nội dung document phù hợp.

Fetch còn đặt giới hạn giữa Request.mode và Response.type. Ví dụ, opaque response chỉ có thể được trả cho request no-cors; opaqueredirect chỉ phù hợp với request manual; response type cors không thể được trả cho request same-origin. Không tạo response giả để vượt CORS hoặc rò rỉ dữ liệu cross-origin.

Nếu Promise truyền vào respondWith() reject hoặc không tạo được Response hợp lệ, browser xử lý như network error đối với request đó.

## 4. waitUntil(): giữ tác vụ nền sống đủ lâu

### 4.1 Khác nhau giữa respondWith() và waitUntil()

| Method | Mục đích | Ví dụ |
|---|---|---|
| respondWith(promise) | Chọn response cho request đang được intercept | Trả cache hoặc network response |
| waitUntil(promise) | Kéo dài lifetime của event cho công việc bổ sung | Lưu response clone vào cache sau khi đã có response |

Ví dụ, trang cần nhận response ngay nhưng worker vẫn muốn lưu bản sao để lần sau dùng cache:

~~~js
async function cacheAndReturn(request, event) {
  const response = await fetch(request);

  const cachePromise = caches.open('runtime-v1').then(cache => {
    return cache.put(request, response.clone());
  });

  event.waitUntil(cachePromise);

  return response;
}

self.addEventListener('fetch', event => {
  if (event.request.url.endsWith('/catalog.json')) {
    event.respondWith(cacheAndReturn(event.request, event));
  }
});
~~~

response.clone() tạo bản sao stream để một bản được trả cho browser và bản còn lại được Cache API đọc. Body của Response gốc chỉ có thể được tiêu thụ một lần.

### 4.2 Service Worker có thể bị dừng khi rảnh

Browser có thể terminate Service Worker để tiết kiệm tài nguyên rồi khởi động lại khi event mới đến. Không coi biến global trong worker là nơi lưu trạng thái lâu dài. Dữ liệu cần tồn tại qua lần worker dừng/khởi động phải được lưu trong Cache API, IndexedDB hoặc storage phù hợp.

waitUntil() giúp browser biết một công việc gắn với event vẫn còn cần hoàn tất. Nó không biến worker thành tiến trình chạy nền liên tục.

### 4.3 Xử lý lỗi của tác vụ nền

Nếu việc lưu cache thất bại, không nhất thiết phải làm request chính thất bại. Có thể bắt lỗi cache riêng:

~~~js
const savePromise = cache.put(request, response.clone())
  .catch(error => {
    console.warn('Không lưu được response vào cache:', error);
  });

event.waitUntil(savePromise);
return response;
~~~

Cách này giữ trải nghiệm network response ngay cả khi storage quota, cache hoặc thiết bị gặp lỗi. Với tác vụ quan trọng về tính nhất quán, hãy xác định rõ khi nào lỗi lưu cache phải ảnh hưởng đến response.

## 5. Các chiến lược fetch phổ biến

### 5.1 Network-only

Mọi request phù hợp đi qua network. Có thể không gọi respondWith() để browser tự fetch, hoặc gọi respondWith(fetch(request)) nếu cần xử lý lỗi/response.

Phù hợp với:

- API có dữ liệu cá nhân hoặc thay đổi liên tục.
- Request tạo/cập nhật/xóa dữ liệu.
- Thanh toán và giao dịch.
- Endpoint cần xác thực hoặc kiểm tra quyền mới nhất.
- Request có semantics không thể replay từ cache.

Không dùng cache làm nơi xác thực. Server vẫn phải kiểm tra authorization cho mọi thao tác.

### 5.2 Cache-first

Tìm cache trước; nếu có thì trả ngay. Nếu không có, tải network và có thể lưu response hợp lệ:

~~~js
async function cacheFirst(request, event) {
  const cache = await caches.open('assets-v1');
  const cached = await cache.match(request);

  if (cached) {
    return cached;
  }

  const response = await fetch(request);

  if (response.status === 200 && response.type === 'basic') {
    event.waitUntil(
      cache.put(request, response.clone()).catch(() => undefined)
    );
  }

  return response;
}
~~~

Phù hợp với asset tĩnh có URL phiên bản hóa như /assets/app.8f31.js, ảnh/logo và font cùng origin. Khi nội dung đổi, phát hành URL mới hoặc đổi cache version.

Không dùng cache-first cho HTML cá nhân hóa hoặc API có dữ liệu theo session nếu chưa có thiết kế cache key và invalidation rõ ràng.

### 5.3 Network-first

Thử network trước. Nếu request lỗi ở tầng mạng, dùng cache fallback:

~~~js
async function networkFirst(request) {
  try {
    return await fetch(request);
  } catch (error) {
    const cached = await caches.match(request);

    if (cached) {
      return cached;
    }

    throw error;
  }
}
~~~

Phù hợp với document hoặc nội dung cần mới khi có mạng nhưng vẫn cần trải nghiệm offline. Có thể dùng offline page riêng cho navigation.

Lưu ý fetch() không reject chỉ vì server trả HTTP 404 hoặc 500. Promise vẫn resolve thành Response có status tương ứng. Đoạn catch trên chỉ chạy với lỗi network như mất kết nối, DNS/TLS failure hoặc request bị browser từ chối. Nếu muốn xử lý HTTP status cụ thể, phải kiểm tra response.status/response.ok.

### 5.4 Stale-while-revalidate

Trả bản cache nếu có, đồng thời tải phiên bản mới ở nền để cập nhật cho lần sau:

~~~js
function staleWhileRevalidate(request, event) {
  const refreshPromise = (async () => {
    const response = await fetch(request);

    if (response.status === 200 && response.type === 'basic') {
      const cache = await caches.open('public-data-v1');
      await cache.put(request, response.clone());
    }

    return response;
  })();

  event.waitUntil(
    refreshPromise.then(() => undefined, () => undefined)
  );

  return (async () => {
    const cache = await caches.open('public-data-v1');
    const cached = await cache.match(request);

    if (cached) {
      return cached;
    }

    try {
      return await refreshPromise;
    } catch {
      return new Response('Dữ liệu hiện chưa khả dụng.', {
        status: 503,
        headers: { 'Content-Type': 'text/plain; charset=utf-8' }
      });
    }
  })();
}
~~~

Phù hợp với nội dung công khai có thể chấp nhận độ trễ nhỏ như danh mục, bài viết hoặc feed. Không dùng cho số dư tài khoản, trạng thái thanh toán, dữ liệu y tế, token, hồ sơ riêng tư hoặc nội dung cần tính nhất quán tức thời.

### 5.5 So sánh chiến lược

| Chiến lược | Nguồn ưu tiên | Khi offline | Dùng phù hợp |
|---|---|---|---|
| Network-only | Network | Request thất bại | API riêng tư, giao dịch |
| Cache-first | Cache | Trả bản đã lưu | Asset phiên bản hóa |
| Network-first | Network | Dùng cache/fallback khi lỗi mạng | Navigation, nội dung cần mới |
| Stale-while-revalidate | Cache trước, network nền | Trả bản cũ nếu có | Nội dung công khai chấp nhận stale |

Chiến lược không nên được chọn chỉ vì tên gọi. Hãy dựa vào độ nhạy cảm dữ liệu, tần suất thay đổi, yêu cầu offline, khả năng invalidation và hậu quả nếu response cũ được sử dụng.

## 6. Routing request và viết fetch handler

### 6.1 Lọc request trước khi can thiệp

Một router cơ bản:

~~~js
self.addEventListener('fetch', event => {
  const request = event.request;
  const url = new URL(request.url);

  // Không cache thao tác ghi dữ liệu.
  if (request.method !== 'GET') return;

  // Chỉ xử lý URL cùng origin trong router này.
  if (url.origin !== self.location.origin) return;

  // Range request cần semantics 206/Content-Range riêng.
  if (request.headers.has('range')) return;

  // Tôn trọng request yêu cầu không lưu.
  if (request.cache === 'no-store') return;

  if (request.mode === 'navigate') {
    event.respondWith(networkFirstNavigation(request));
    return;
  }

  if (url.pathname.startsWith('/assets/')) {
    event.respondWith(cacheFirstAsset(request, event));
    return;
  }

  if (url.pathname === '/api/public-feed') {
    event.respondWith(staleWhileRevalidate(request, event));
  }
});
~~~

Router không intercept các request không khớp. Browser tiếp tục xử lý mặc định. Hãy giữ các nhánh rõ ràng và kiểm tra URL bằng URL API thay vì nối chuỗi hoặc kiểm tra suffix thiếu chính xác.

### 6.2 Dùng request.destination để phân loại tài nguyên

~~~js
self.addEventListener('fetch', event => {
  const request = event.request;

  if (request.method !== 'GET') return;

  switch (request.destination) {
    case 'script':
    case 'style':
    case 'image':
    case 'font':
      // Có thể áp dụng cache policy cho asset đã xác định.
      break;

    case 'document':
      // Navigation request thường có mode navigate.
      break;

    default:
      // Request fetch tổng quát hoặc loại khác.
      break;
  }
});
~~~

destination giúp phân biệt resource browser tải cho trang với fetch() do code gọi. Tuy nhiên, nó có thể rỗng; hãy kết hợp với pathname và nghiệp vụ.

### 6.3 Tạo response tổng hợp

Service Worker có thể tạo response:

~~~js
self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);

  if (
    event.request.method === 'GET' &&
    url.origin === self.location.origin &&
    url.pathname === '/health/offline'
  ) {
    event.respondWith(new Response(
      JSON.stringify({ status: 'offline-ready' }),
      {
        status: 200,
        headers: {
          'Content-Type': 'application/json; charset=utf-8',
          'Cache-Control': 'no-store'
        }
      }
    ));
  }
});
~~~

Response tổng hợp hữu ích cho health check, fallback nhỏ hoặc dữ liệu được tạo từ cache. Không giả mạo kết quả API nghiệp vụ thành status 200 khi server thật không xử lý thành công.

### 6.4 Chọn response lỗi phù hợp

- Trả Response với status 404 nếu route không tồn tại.
- Trả status 503 nếu chức năng tạm thời không khả dụng và muốn client nhận HTTP response có thể kiểm tra.
- Dùng Response.error() nếu muốn biến request thành network error, khiến fetch() ở client reject.
- Không trả status 200 cùng thông báo lỗi nếu ứng dụng dựa vào response.ok/status để xử lý.

## 7. Cache API và vòng đời response

### 7.1 Cache API là kho key/value theo origin

CacheStorage chứa nhiều Cache có tên. Mỗi Cache lưu cặp Request/Response. Worker tự quyết định khi nào mở cache, cập nhật, xóa và invalidation.

~~~js
const cache = await caches.open('static-v3');
await cache.put('/assets/app.js', response.clone());

const cached = await cache.match('/assets/app.js');
~~~

Dùng tên cache có version để quản lý schema/nội dung. Tránh dùng caches.match() toàn cục một cách thiếu kiểm soát nếu nhiều cache có thể chứa cùng URL; mở cache cụ thể cho từng loại dữ liệu giúp giảm va chạm.

### 7.2 Cache API không tự tuân theo HTTP cache headers

Cache API không tự áp dụng thời hạn max-age, no-cache hoặc no-store như HTTP cache thông thường. Entry không tự hết hạn; ứng dụng phải tự quyết định freshness, revalidation và deletion.

Điều này đặc biệt quan trọng với dữ liệu riêng tư. Nếu response có Cache-Control: no-store hoặc private, worker phải chủ động từ chối lưu. Không cho rằng header tự động ngăn Cache API lưu response.

Ví dụ kiểm tra trước khi cache:

~~~js
function isCacheableResponse(response) {
  if (!response || response.status !== 200) return false;
  if (response.type !== 'basic') return false;

  const cacheControl = response.headers.get('Cache-Control') || '';
  if (/\b(no-store|no-cache|private)\b/i.test(cacheControl)) {
    return false;
  }

  const vary = response.headers.get('Vary') || '';
  if (vary.trim() === '*') return false;

  return true;
}
~~~

Đây là bộ lọc cơ bản cho cache cùng origin. Ứng dụng thực tế cần thêm allowlist URL, kiểm tra content type, chính sách dữ liệu và TTL riêng.

### 7.3 Cache key phải giữ đúng biến thể request

Cache.match() xét URL và các header được nêu trong Vary. Không dùng ignoreSearch: true chỉ để tăng cache hit nếu query string có thể phân biệt người dùng, ngôn ngữ, bộ lọc, phiên bản hoặc dữ liệu.

Ví dụ /api/items?page=1 và /api/items?page=2 không nhất thiết là cùng một nội dung. Nếu bỏ query khỏi cache key, worker có thể trả trang dữ liệu sai.

### 7.4 Clone Request/Response trước khi dùng hai lần

Request và Response có body dạng stream. Khi body đã được đọc hoặc tiêu thụ, không thể đọc lại cùng stream.

~~~js
const response = await fetch(request);
const copyForCache = response.clone();

event.waitUntil(cache.put(request, copyForCache));
return response;
~~~

Nếu cần đọc body Request để kiểm tra rồi vẫn gửi network, hãy clone Request trước khi đọc. Không clone tùy tiện mọi request; clone stream có thể làm tăng buffering và bộ nhớ nếu một nhánh đọc chậm.

### 7.5 Cache quota và eviction

CacheStorage có giới hạn dung lượng theo origin. Browser có thể xóa dữ liệu storage khi thiếu dung lượng hoặc theo chính sách quản lý storage. Không coi Cache API là nơi lưu dữ liệu vĩnh viễn.

Nên:

- Chỉ lưu resource có giá trị offline rõ ràng.
- Xóa cache version cũ trong activate.
- Đặt giới hạn và dọn runtime cache.
- Theo dõi dung lượng bằng StorageManager.estimate() khi cần.
- Có fallback network khi cache bị xóa.

### 7.6 Version cache và cập nhật worker

Ví dụ:

~~~js
const STATIC_CACHE = 'app-static-v4';
const RUNTIME_CACHE = 'app-runtime-v4';

self.addEventListener('activate', event => {
  event.waitUntil((async () => {
    const keep = [STATIC_CACHE, RUNTIME_CACHE];
    const names = await caches.keys();

    await Promise.all(
      names
        .filter(name => name.startsWith('app-') && !keep.includes(name))
        .map(name => caches.delete(name))
    );

    await self.clients.claim();
  })());
});
~~~

Chỉ xóa cache do ứng dụng sở hữu, không xóa cache không liên quan. Khi đổi cache schema hoặc URL, phối hợp worker version với tài nguyên HTML/JS để tránh worker mới điều khiển trang cũ mà không tương thích.

## 8. CORS, opaque response và cross-origin

### 8.1 Service Worker không vượt qua CORS

Nếu page gọi fetch() cross-origin ở mode cors, browser vẫn yêu cầu server đích trả CORS headers hợp lệ. Việc request đi qua Service Worker không bỏ qua kiểm tra này.

Ví dụ:

~~~js
const response = await fetch('https://api.example.net/data', {
  mode: 'cors',
  credentials: 'omit'
});
~~~

Nếu server không cho phép origin hiện tại, request vẫn thất bại theo CORS. Worker không thể thêm Access-Control-Allow-Origin vào response của server để hợp thức hóa một request đã bị CORS chặn ở tầng browser.

### 8.2 Opaque response của no-cors

Request no-cors có thể nhận Response type opaque. Worker không thể đọc status, headers hoặc body của response đó; status hiển thị là 0.

~~~js
const response = await fetch(
  'https://cdn.example.net/public-image.png',
  { mode: 'no-cors' }
);

console.log(response.type);   // Có thể là "opaque"
console.log(response.status); // 0
~~~

Cache.put() có thể lưu opaque response trong một số trường hợp, nhưng Cache.add()/addAll() không lưu opaque response. Không dùng opaque response như bằng chứng tải thành công vì worker không thể kiểm tra status hoặc nội dung. Chỉ cache loại tài nguyên public đã được đánh giá và có lý do rõ ràng.

### 8.3 respondWith() có giới hạn theo Response.type

Một số quy tắc:

- Opaque response chỉ có thể được trả cho request mode no-cors.
- Opaque redirect response chỉ phù hợp với request mode manual.
- Response type cors không thể được trả cho request mode same-origin.

Nếu response type không tương thích với request mode, Fetch có thể trả network error. Đừng cố chuyển đổi response type bằng cách tạo Response mới từ body opaque; body không thể đọc được.

### 8.4 Cache resource cross-origin cần chính sách riêng

Nếu cần cache resource cross-origin, hãy xác định:

- Request mode là cors hay no-cors?
- Server có CORS hoặc CORP phù hợp không?
- Response có phải opaque không?
- Resource có public và bất biến không?
- Có redirect sang origin khác không?
- Có cần credential/cookie không?

Bài lab chỉ cache resource cùng origin để không che khuất những quy tắc này.

## 9. Navigation, redirect và Range request

### 9.1 Navigation fallback chỉ nên áp dụng cho document

Network-first cho navigation thường được dùng để trả nội dung mới khi có mạng và offline page khi request mạng thất bại:

~~~js
async function networkFirstNavigation(request) {
  try {
    return await fetch(request);
  } catch {
    const offline = await caches.match('/offline.html');

    return offline || new Response(
      'Không có kết nối mạng.',
      {
        status: 503,
        headers: { 'Content-Type': 'text/plain; charset=utf-8' }
      }
    );
  }
}
~~~

Chỉ áp dụng cho request mode navigate và URL thuộc origin/scope đã kiểm soát. Không trả index.html cho mọi request không khớp; làm vậy có thể khiến API nhận HTML thay vì JSON hoặc che giấu lỗi route.

### 9.2 Phân biệt network error với HTTP error

fetch() reject khi có lỗi network hoặc request bị browser chặn. Response HTTP 404/500 vẫn resolve bình thường. Nếu chỉ fallback trong catch, worker sẽ trả 404/500 từ server như bình thường và chỉ hiển thị offline page khi thực sự không lấy được response.

Nếu muốn fallback khi server trả 5xx, hãy kiểm tra response.status một cách có chủ đích. Không fallback cho mọi status khác 200 nếu điều đó sẽ che lỗi xác thực, phân quyền hoặc route.

### 9.3 Redirect

fetch() theo mặc định có thể follow redirect theo request.redirect. Nếu URL đích đổi origin, CORS và các quy tắc Fetch vẫn áp dụng. Kiểm tra response.redirected, response.url và redirect chain khi chẩn đoán lỗi.

Không cache redirect hoặc response cuối cùng vào một key khác mà không hiểu semantics. Khi ứng dụng cần giữ URL cuối cùng, hãy kiểm tra cách browser sử dụng Response.url với loại request tương ứng.

### 9.4 Range request và media

Trình phát audio/video có thể gửi Range header để yêu cầu một phần byte. Server có thể trả 206 Partial Content cùng Content-Range.

Nếu worker trả toàn bộ file 200 cho một Range request hoặc cache response 206 rồi dùng nó như response đầy đủ cho request khác, playback và seek có thể lỗi. Cache.put() có thể lưu cặp Request/Response, nhưng việc lưu một đoạn byte riêng không tự tạo cache logic đúng cho các Range request tiếp theo. Cache.add()/addAll() chỉ lưu response có status thuộc nhóm 200; hãy pass-through Range nếu chưa triển khai đầy đủ semantics byte-range.

Cách an toàn cho router thông thường là pass-through request có Range header:

~~~js
if (event.request.headers.has('range')) {
  return;
}
~~~

Chỉ tự xử lý Range khi đã triển khai đúng byte range, Content-Range, Content-Length, status 206 và các trường hợp nhiều range cần thiết.

## 10. Rủi ro bảo mật khi intercept và cache

### 10.1 Cache poisoning

Cache poisoning xảy ra khi worker lưu nội dung không đáng tin hoặc dùng cache key không phân biệt đúng biến thể. Attacker có thể lợi dụng query string, header, redirect hoặc endpoint có nội dung theo người dùng để khiến người khác nhận response sai.

Giảm rủi ro:

- Chỉ cache URL nằm trong allowlist.
- Dùng cache name riêng cho từng nhóm resource.
- Không bỏ query khỏi cache key nếu query có ý nghĩa.
- Chỉ lưu response có status và content type mong đợi.
- Kiểm tra origin và redirect.
- Không cache opaque response không rõ nguồn.
- Xóa cache cũ khi thay schema hoặc phát hiện dữ liệu sai.

### 10.2 Không cache dữ liệu cá nhân theo mặc định

CacheStorage thuộc origin, không tự tách cache theo tài khoản người dùng đang đăng nhập. Nếu ứng dụng cache response riêng tư rồi người dùng đăng xuất và người khác đăng nhập trên cùng browser profile, response cũ có thể được trả nhầm.

Không cache theo mặc định:

- Hồ sơ cá nhân.
- Lịch sử giao dịch.
- Số dư, đơn hàng hoặc thông tin thanh toán.
- Token, session data hoặc response có Authorization.
- API phụ thuộc cookie/session.
- Response có Cache-Control: private hoặc no-store.

Nếu nghiệp vụ bắt buộc cache dữ liệu riêng tư, cần thiết kế partitioning theo user/session, invalidation khi logout/account switch, TTL, encryption-at-rest nếu phù hợp và kiểm thử đa tài khoản. Không chỉ thêm user ID vào URL rồi coi là đủ an toàn.

### 10.3 Không cache request ghi dữ liệu

POST/PUT/PATCH/DELETE không nên đi qua cache strategy thông thường. Đừng replay thao tác thanh toán hoặc tạo đơn hàng khi offline rồi gửi lại tự động nếu chưa có cơ chế idempotency key, trạng thái đồng bộ và xử lý trùng lặp ở server.

### 10.4 Không dùng Service Worker làm ranh giới authorization

Người dùng có thể xóa cache, unregister worker, thay đổi môi trường hoặc gọi API theo đường khác. Server phải kiểm tra authentication, authorization, CSRF và dữ liệu đầu vào cho mọi request. Worker chỉ điều phối trải nghiệm phía client, không thay server-side access control.

### 10.5 Tránh che giấu lỗi bảo mật bằng fallback

Không trả bản cache cũ cho endpoint logout, revoke token, payment status hoặc quyền truy cập vừa thay đổi. Nếu server trả 401/403, không thay bằng response cache 200 cũ. Fallback phải giữ nguyên ý nghĩa bảo mật của status và nghiệp vụ.

### 10.6 Cẩn trọng với request và response body

- Không log Authorization, cookie hoặc dữ liệu cá nhân trong fetch handler.
- Không đọc body rồi quên clone trước khi chuyển tiếp.
- Không tạo lại Request làm mất mode, credentials, redirect hoặc integrity.
- Không sửa header bị browser kiểm soát như Cookie/Host.
- Không dùng URL do người dùng kiểm soát để chọn cache key mà không validate.
- Giới hạn kích thước response được cache và có chiến lược dọn dẹp.

## 11. Navigation preload

### 11.1 Vấn đề khởi động worker khi navigation

Khi browser điều hướng, đôi khi nó phải khởi động Service Worker trước khi worker có thể xử lý fetch event. Navigation preload cho phép browser bắt đầu request network song song với quá trình khởi động worker, giảm độ trễ.

### 11.2 Bật preload trong activate

~~~js
self.addEventListener('activate', event => {
  event.waitUntil((async () => {
    if (self.registration.navigationPreload) {
      await self.registration.navigationPreload.enable();
    }

    await self.clients.claim();
  })());
});
~~~

### 11.3 Dùng preload response

~~~js
async function navigationWithPreload(event) {
  try {
    const preloaded = await event.preloadResponse;

    if (preloaded) {
      return preloaded;
    }

    return await fetch(event.request);
  } catch {
    const offline = await caches.match('/offline.html');
    return offline || new Response('Offline', { status: 503 });
  }
}

self.addEventListener('fetch', event => {
  if (event.request.mode === 'navigate') {
    event.respondWith(navigationWithPreload(event));
  }
});
~~~

event.preloadResponse có thể resolve thành undefined nếu request không phải navigation hoặc preload chưa được bật. Luôn có fallback sang fetch(request). Chỉ bật preload nếu chiến lược navigation có thể sử dụng response đó; không bật rồi bỏ quên request preload không được dùng.

## 12. Debug Fetch interception trong DevTools

### 12.1 Xác nhận trang đang được kiểm soát

Mở Console:

~~~js
console.log(navigator.serviceWorker.controller);
~~~

Nếu null, fetch handler chưa kiểm soát trang hiện tại. Kiểm tra registration, scope, secure context và trạng thái worker.

### 12.2 Application/Storage → Service Workers

Trong Chrome/Edge DevTools:

- Mở Application → Service Workers.
- Kiểm tra script URL, scope và trạng thái installing/waiting/activated.
- Dùng Update để kiểm tra bản worker mới.
- Dùng Skip waiting khi thử nghiệm cập nhật nếu hiểu ảnh hưởng.
- Dùng Unregister để xóa registration khi cần reset lab.
- Dùng Bypass for network để so sánh request có và không qua Service Worker.

Tên và vị trí tab có thể khác theo phiên bản browser. Firefox và Safari có công cụ tương đương nhưng giao diện không giống Chromium.

### 12.3 Network panel

Trong Network, chọn request và kiểm tra:

- Request URL, method và status.
- Initiator và redirect chain.
- Response có nguồn từ ServiceWorker hay network.
- Request có được phục vụ từ Cache Storage hay không.
- Response headers, content type và body.
- Timing để so sánh cache hit và network.

Một request có thể được Service Worker xử lý rồi worker lại gọi network. Vì vậy, việc thấy network request không chứng minh worker không can thiệp.

### 12.4 Kiểm tra Cache Storage

Trong Application → Cache Storage, mở cache theo tên và kiểm tra key/response. Xóa cache riêng của lab khi cần thử lại cache miss. Không xóa toàn bộ site data trên môi trường có dữ liệu người dùng thật.

### 12.5 Ghi log có chọn lọc

~~~js
self.addEventListener('fetch', event => {
  const request = event.request;
  const url = new URL(request.url);

  console.debug('[SW fetch]', {
    method: request.method,
    path: url.pathname,
    mode: request.mode,
    destination: request.destination
  });
});
~~~

Không log query chứa token, email, identifier hoặc thông tin cá nhân. Log chỉ nên giúp xác định route và loại request.

## 13. Thực hành: xây dựng Fetch interception lab với Node.js

Lab tạo một ứng dụng tại localhost:3000 và một Service Worker kiểm soát scope /. Worker áp dụng ba chiến lược:

- Cache-first cho asset phiên bản hóa trong /assets/.
- Stale-while-revalidate cho endpoint public /api/public-feed.
- Network-first cho navigation, với offline.html làm fallback.
- /api/time không được router xử lý, nên browser fetch mặc định.
- Request không phải GET, request Range và request cache=no-store được pass-through.

Lab chỉ dùng dữ liệu demo. Endpoint public-feed không phụ thuộc cookie hoặc tài khoản.

### 13.1 Cấu trúc thư mục

~~~text
fetch-interception-lab/
  server.mjs
  public/
    index.html
    offline.html
    sw.js
    assets/
      app.js
      style.css
      demo-v1.txt
~~~

### 13.2 Tạo file server.mjs

~~~js
import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';

const publicRoot = new URL('./public/', import.meta.url);

const files = new Map([
  ['/', {
    file: 'index.html',
    type: 'text/html; charset=utf-8',
    cache: 'no-cache'
  }],
  ['/index.html', {
    file: 'index.html',
    type: 'text/html; charset=utf-8',
    cache: 'no-cache'
  }],
  ['/offline.html', {
    file: 'offline.html',
    type: 'text/html; charset=utf-8',
    cache: 'no-cache'
  }],
  ['/sw.js', {
    file: 'sw.js',
    type: 'text/javascript; charset=utf-8',
    cache: 'no-cache'
  }],
  ['/assets/app.js', {
    file: 'assets/app.js',
    type: 'text/javascript; charset=utf-8',
    cache: 'public, max-age=31536000, immutable'
  }],
  ['/assets/style.css', {
    file: 'assets/style.css',
    type: 'text/css; charset=utf-8',
    cache: 'public, max-age=31536000, immutable'
  }],
  ['/assets/demo-v1.txt', {
    file: 'assets/demo-v1.txt',
    type: 'text/plain; charset=utf-8',
    cache: 'public, max-age=31536000, immutable'
  }]
]);

const server = createServer(async (req, res) => {
  const url = new URL(req.url || '/', 'http://localhost');

  if (req.method !== 'GET' && req.method !== 'HEAD') {
    res.writeHead(405, { 'Allow': 'GET, HEAD' });
    return res.end('Method not allowed');
  }

  if (url.pathname === '/api/time') {
    res.writeHead(200, {
      'Content-Type': 'application/json; charset=utf-8',
      'Cache-Control': 'no-store'
    });

    if (req.method === 'HEAD') return res.end();
    return res.end(JSON.stringify({
      now: new Date().toISOString(),
      source: 'network-only'
    }));
  }

  if (url.pathname === '/api/public-feed') {
    res.writeHead(200, {
      'Content-Type': 'application/json; charset=utf-8',
      'Cache-Control': 'public, max-age=15'
    });

    if (req.method === 'HEAD') return res.end();
    return res.end(JSON.stringify({
      generatedAt: new Date().toISOString(),
      items: [
        'Thông báo công khai A',
        'Thông báo công khai B'
      ]
    }));
  }

  const entry = files.get(url.pathname);

  if (!entry) {
    res.writeHead(404, {
      'Content-Type': 'text/plain; charset=utf-8',
      'Cache-Control': 'no-store'
    });
    return res.end('Not found');
  }

  try {
    const body = await readFile(new URL(entry.file, publicRoot));

    res.writeHead(200, {
      'Content-Type': entry.type,
      'Cache-Control': entry.cache,
      'X-Content-Type-Options': 'nosniff'
    });

    if (req.method === 'HEAD') return res.end();
    return res.end(body);
  } catch {
    res.writeHead(500, {
      'Content-Type': 'text/plain; charset=utf-8'
    });
    return res.end('Could not read lab file');
  }
});

server.listen(3000, 'localhost', () => {
  console.log('Fetch interception lab: http://localhost:3000');
});
~~~

### 13.3 Tạo public/index.html

~~~html
<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Fetch interception lab</title>
  <link rel="stylesheet" href="/assets/style.css">
  <script src="/assets/app.js" defer></script>
</head>
<body>
  <main>
    <h1>Fetch interception lab</h1>
    <p id="controller-status" role="status">Đang đăng ký Service Worker...</p>

    <section>
      <h2>Cache-first asset</h2>
      <button id="load-asset" type="button" disabled>
        Tải asset phiên bản hóa
      </button>
    </section>

    <section>
      <h2>Stale-while-revalidate</h2>
      <button id="load-feed" type="button" disabled>
        Tải public feed
      </button>
    </section>

    <section>
      <h2>Network pass-through</h2>
      <button id="load-time" type="button" disabled>
        Tải thời gian từ network
      </button>
    </section>

    <section>
      <h2>Kết quả</h2>
      <pre id="result">Chưa có request.</pre>
    </section>

    <p>
      Khi đã online, hãy mở lại trang với DevTools Network ở chế độ Offline
      để kiểm tra navigation fallback.
    </p>
  </main>
</body>
</html>
~~~

### 13.4 Tạo public/offline.html

~~~html
<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Đang offline</title>
</head>
<body>
  <main>
    <h1>Bạn đang offline</h1>
    <p>Không thể tải trang mới từ network. Hãy kiểm tra kết nối rồi thử lại.</p>
    <a href="/">Thử tải lại trang chính</a>
  </main>
</body>
</html>
~~~

### 13.5 Tạo public/assets/style.css

~~~css
body {
  margin: 0;
  padding: 2rem;
  color: #172033;
  background: #f4f6fa;
  font: 16px/1.5 system-ui, sans-serif;
}

main {
  max-width: 760px;
  margin: 0 auto;
}

section {
  margin: 1rem 0;
  padding: 1rem;
  background: white;
  border: 1px solid #d8deea;
  border-radius: 8px;
}

button {
  padding: 0.6rem 0.9rem;
  cursor: pointer;
}

button:disabled {
  cursor: not-allowed;
  opacity: 0.5;
}

pre {
  overflow-wrap: anywhere;
  white-space: pre-wrap;
  padding: 1rem;
  background: #101827;
  color: #f4f6fa;
  border-radius: 6px;
}
~~~

### 13.6 Tạo public/assets/demo-v1.txt

~~~text
Asset demo v1
Nếu request đầu tiên đi qua network, Service Worker sẽ lưu bản sao.
Các lần tiếp theo có thể được phục vụ từ Cache Storage.
~~~

### 13.7 Tạo public/assets/app.js

~~~js
const statusElement = document.querySelector('#controller-status');
const resultElement = document.querySelector('#result');

const buttons = [
  document.querySelector('#load-asset'),
  document.querySelector('#load-feed'),
  document.querySelector('#load-time')
];

function showResult(value) {
  resultElement.textContent = value;
}

function updateControllerStatus() {
  const controlled = Boolean(navigator.serviceWorker?.controller);

  statusElement.textContent = controlled
    ? 'Trang đang được Service Worker kiểm soát.'
    : 'Worker chưa kiểm soát tab. Hãy chờ activate hoặc tải lại trang.';

  for (const button of buttons) {
    button.disabled = !controlled;
  }
}

async function fetchText(url) {
  const response = await fetch(url);

  if (!response.ok) {
    throw new Error('HTTP ' + response.status);
  }

  return response.text();
}

document.querySelector('#load-asset').addEventListener('click', async () => {
  try {
    const text = await fetchText('/assets/demo-v1.txt');
    showResult('Asset response:\n' + text);
  } catch (error) {
    showResult('Asset request failed: ' + error.message);
  }
});

document.querySelector('#load-feed').addEventListener('click', async () => {
  try {
    const response = await fetch('/api/public-feed');

    if (!response.ok) {
      throw new Error('HTTP ' + response.status);
    }

    const data = await response.json();
    showResult('Public feed:\n' + JSON.stringify(data, null, 2));
  } catch (error) {
    showResult('Feed request failed: ' + error.message);
  }
});

document.querySelector('#load-time').addEventListener('click', async () => {
  try {
    const response = await fetch('/api/time');

    if (!response.ok) {
      throw new Error('HTTP ' + response.status);
    }

    const data = await response.json();
    showResult('Network-only endpoint:\n' + JSON.stringify(data, null, 2));
  } catch (error) {
    showResult('Time request failed: ' + error.message);
  }
});

if ('serviceWorker' in navigator) {
  navigator.serviceWorker.addEventListener(
    'controllerchange',
    updateControllerStatus
  );

  navigator.serviceWorker.register('/sw.js')
    .then(async () => {
      await navigator.serviceWorker.ready;
      updateControllerStatus();
    })
    .catch(error => {
      statusElement.textContent =
        'Không đăng ký được Service Worker: ' + error.message;
    });
} else {
  statusElement.textContent =
    'Browser không hỗ trợ Service Worker.';
}
~~~

### 13.8 Tạo public/sw.js

~~~js
const STATIC_CACHE = 'fetch-lab-static-v1';
const RUNTIME_CACHE = 'fetch-lab-runtime-v1';

const PRECACHE_URLS = [
  '/',
  '/index.html',
  '/offline.html',
  '/assets/app.js',
  '/assets/style.css'
];

self.addEventListener('install', event => {
  event.waitUntil((async () => {
    const cache = await caches.open(STATIC_CACHE);
    await cache.addAll(PRECACHE_URLS);
  })());
});

self.addEventListener('activate', event => {
  event.waitUntil((async () => {
    const keep = [STATIC_CACHE, RUNTIME_CACHE];
    const names = await caches.keys();

    await Promise.all(
      names
        .filter(name =>
          name.startsWith('fetch-lab-') && !keep.includes(name)
        )
        .map(name => caches.delete(name))
    );

    await self.clients.claim();
  })());
});

function isCacheableResponse(response) {
  if (!response || response.status !== 200) return false;
  if (response.type !== 'basic') return false;

  const cacheControl = response.headers.get('Cache-Control') || '';
  if (/\b(no-store|no-cache|private)\b/i.test(cacheControl)) {
    return false;
  }

  const vary = response.headers.get('Vary') || '';
  if (vary.trim() === '*') return false;

  return true;
}

async function cacheFirstAsset(request, event) {
  const cache = await caches.open(STATIC_CACHE);
  const cached = await cache.match(request);

  if (cached) {
    console.log('[cache-first] cache hit:', request.url);
    return cached;
  }

  console.log('[cache-first] network miss:', request.url);
  const response = await fetch(request);

  if (isCacheableResponse(response)) {
    const savePromise = cache.put(request, response.clone())
      .catch(error => {
        console.warn('[cache-first] cache write failed:', error);
      });

    event.waitUntil(savePromise);
  }

  return response;
}

async function networkFirstNavigation(request) {
  try {
    console.log('[network-first] navigation:', request.url);
    return await fetch(request);
  } catch (error) {
    console.warn('[network-first] network failed:', error);

    const cache = await caches.open(STATIC_CACHE);
    const offline = await cache.match('/offline.html');

    if (offline) return offline;

    return new Response('Không có kết nối mạng.', {
      status: 503,
      headers: { 'Content-Type': 'text/plain; charset=utf-8' }
    });
  }
}

function staleWhileRevalidate(request, event) {
  const refreshPromise = (async () => {
    const response = await fetch(request);

    if (isCacheableResponse(response)) {
      const cache = await caches.open(RUNTIME_CACHE);
      await cache.put(request, response.clone());
    }

    return response;
  })();

  // Giữ tác vụ cập nhật cache sống sau khi response chính được trả.
  event.waitUntil(
    refreshPromise.then(
      () => undefined,
      error => console.warn('[swr] refresh failed:', error)
    )
  );

  return (async () => {
    const cache = await caches.open(RUNTIME_CACHE);
    const cached = await cache.match(request);

    if (cached) {
      console.log('[swr] return cached response:', request.url);
      return cached;
    }

    try {
      console.log('[swr] no cache; wait for network:', request.url);
      return await refreshPromise;
    } catch {
      return new Response(
        JSON.stringify({ error: 'Public feed tạm thời không khả dụng.' }),
        {
          status: 503,
          headers: { 'Content-Type': 'application/json; charset=utf-8' }
        }
      );
    }
  })();
}

self.addEventListener('fetch', event => {
  const request = event.request;
  const url = new URL(request.url);

  console.log('[fetch event]', {
    method: request.method,
    path: url.pathname,
    mode: request.mode,
    destination: request.destination
  });

  // Không cache thao tác ghi, Range hoặc request yêu cầu no-store.
  if (request.method !== 'GET') return;
  if (url.origin !== self.location.origin) return;
  if (request.headers.has('range')) return;
  if (request.cache === 'no-store') return;
  if (request.headers.has('authorization')) return;

  if (request.mode === 'navigate') {
    event.respondWith(networkFirstNavigation(request));
    return;
  }

  if (url.pathname.startsWith('/assets/')) {
    event.respondWith(cacheFirstAsset(request, event));
    return;
  }

  if (url.pathname === '/api/public-feed') {
    event.respondWith(staleWhileRevalidate(request, event));
    return;
  }

  // /api/time và các route khác được browser fetch theo mặc định.
});
~~~

### 13.9 Chạy lab

Từ thư mục fetch-interception-lab:

~~~bash
node server.mjs
~~~

Mở:

~~~text
http://localhost:3000
~~~

Chờ trạng thái cho biết trang đã được Service Worker kiểm soát. Nếu tab chưa có controller sau lần đầu đăng ký, tải lại trang rồi thử các nút.

### 13.10 Thử cache-first

1. Bấm “Tải asset phiên bản hóa” lần đầu.
2. Mở DevTools → Network và kiểm tra request /assets/demo-v1.txt.
3. Bấm lại lần hai.
4. Kiểm tra response được phục vụ từ Service Worker/Cache Storage.
5. Mở Application → Cache Storage → fetch-lab-static-v1 để xem entry.

Asset được lưu sau lần tải network đầu tiên. Nếu sửa nội dung file demo-v1.txt nhưng giữ nguyên URL, cache có thể tiếp tục trả bản cũ. Hãy đổi URL/version hoặc xóa cache trong DevTools để kiểm tra bản mới.

### 13.11 Thử stale-while-revalidate

1. Bấm “Tải public feed” lần đầu để lấy response network và lưu cache.
2. Bấm lần hai để nhận response cache trong khi worker cập nhật cache ở nền.
3. Chờ một lúc rồi bấm lại để quan sát generatedAt thay đổi.
4. Mở Console để xem log [swr] và Network để xem request refresh.

Endpoint này là public demo. Không dùng chiến lược này cho API cá nhân hóa hoặc response phụ thuộc cookie/session.

### 13.12 Thử network pass-through

Bấm “Tải thời gian từ network”. Worker nhận fetch event nhưng không gọi respondWith() cho /api/time. Browser tự thực hiện request và server tạo timestamp mới.

Mở Console để phân biệt hai việc: worker có thể quan sát fetch event, nhưng vì handler không chiếm response nên request đi theo quy trình mặc định.

### 13.13 Thử offline navigation

1. Tải trang khi đang online để Service Worker active và cache offline.html.
2. Mở DevTools → Network và bật Offline.
3. Reload trang tại localhost:3000.
4. Worker thử fetch navigation; khi network request reject, nó trả offline.html từ Cache Storage.
5. Tắt Offline và reload lại để trở về trang chính.

Nếu tab chưa được controller kiểm soát hoặc offline.html chưa được precache thành công, fallback có thể không chạy. Kiểm tra Application → Service Workers và Cache Storage.

### 13.14 Thử request bị pass-through

Trong Console của trang, chạy:

~~~js
fetch('/api/time', { method: 'POST' })
  .then(response => response.text())
  .then(console.log);
~~~

Server trả 405 vì lab chỉ hỗ trợ GET/HEAD. Service Worker không cache hoặc replay POST; browser gửi request theo mặc định.

Có thể thử Range request bằng một tài nguyên media phù hợp. Router bỏ qua request có Range header để browser và server xử lý byte range bình thường.

### 13.15 Dọn lab

Khi hoàn tất:

- Dừng Node server.
- Application → Service Workers → Unregister.
- Application → Cache Storage → xóa hai cache fetch-lab-static-v1 và fetch-lab-runtime-v1.
- Reload trang để xác nhận ứng dụng không còn bị worker cũ kiểm soát.

## 14. Chẩn đoán lỗi Fetch interception

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Không thấy fetch event | Trang chưa được controller kiểm soát hoặc request ngoài scope | Kiểm tra controller, registration và scope |
| Worker đăng ký thất bại | Không có secure context, script URL sai hoặc scope vượt quyền | Dùng HTTPS/localhost, kiểm tra đường dẫn và Service-Worker-Allowed |
| respondWith() gây InvalidStateError | Gọi nhiều lần hoặc gọi sau khi handler đã kết thúc | Gọi đồng bộ một lần trong listener |
| Client nhận network error | Promise trong respondWith reject hoặc response không tương thích request mode | Kiểm tra catch, Response.type và Request.mode |
| Cache miss liên tục | Cache key khác URL/query/header hoặc cache version bị đổi | Kiểm tra Cache.match, Vary và tên cache |
| Response body bị lỗi khi cache | Body đã bị tiêu thụ trước khi cache.put | Clone Response/Request trước khi đọc hoặc lưu |
| HTTP 404 không chạy catch | fetch() resolve bình thường với Response 404 | Kiểm tra response.ok/status |
| Offline page không xuất hiện | offline.html chưa được precache hoặc request không phải navigation | Kiểm tra install, cache và request.mode |
| Trang trả HTML cho API | Router fallback quá rộng | Chỉ áp dụng offline shell cho navigation cùng origin |
| Media không seek được | Worker xử lý Range như response đầy đủ | Pass-through Range hoặc triển khai 206 đúng |
| CDN request bị lỗi CORS | Worker không thể bỏ qua CORS | Sửa CORS tại resource server hoặc để browser xử lý mặc định |
| Opaque response có status 0 | Request no-cors | Không dựa vào status/body opaque; chỉ cache resource public đã được đánh giá |
| Dữ liệu cũ sau logout | Cache chứa response cá nhân hóa và không được invalidation | Không cache dữ liệu riêng tư hoặc thiết kế purge/session partitioning |
| Cache không tự hết hạn | Cache API không tự áp dụng max-age | Tự quản lý TTL, revalidation và deletion |
| Worker mới không active | Worker cũ còn control clients hoặc update đang chờ | Kiểm tra lifecycle, waiting worker và chiến lược rollout |

## 15. Ma trận kiểm thử Fetch interception

| ID | Request | Điều kiện | Kết quả mong đợi |
|---|---|---|---|
| F01 | GET /assets/demo-v1.txt | Cache miss | Network response được trả và lưu cache |
| F02 | GET /assets/demo-v1.txt | Cache hit | Trả response từ Cache Storage |
| F03 | GET /api/public-feed | Chưa có cache | Đợi network, lưu response |
| F04 | GET /api/public-feed | Đã có cache | Trả cache và refresh ở nền |
| F05 | Navigation GET / | Online | Network response được trả |
| F06 | Navigation GET / | Offline, offline page đã precache | Trả offline.html |
| F07 | GET /api/time | Route không được xử lý | Browser thực hiện fetch mặc định |
| F08 | POST /api/time | Method khác GET | Pass-through, không cache |
| F09 | GET có Range header | Resource media | Pass-through hoặc xử lý Range chuyên biệt |
| F10 | GET cross-origin | Router chỉ cho same-origin | Pass-through; CORS vẫn áp dụng |
| F11 | Response HTTP 404 | Network fetch resolve | Client nhận status 404, không coi là network rejection |
| F12 | Response có Cache-Control private/no-store | Runtime cache | Không lưu response |
| F13 | Response Vary: * | Runtime cache | Không lưu response |
| F14 | Response body cần trả và cache | Cache write nền | Clone response; body gốc vẫn đọc được |
| F15 | Browser xóa cache do quota | Cache miss sau eviction | Strategy fetch network hoặc fallback phù hợp |

## 16. Câu hỏi tự kiểm tra

**Câu 1.** Fetch event được phát ra trong trường hợp nào?

**Đáp án:** Khi một client đang được Service Worker kiểm soát tạo request fetch, bao gồm navigation và tải subresource như script, CSS, ảnh, cũng như fetch/XHR từ trang.

**Câu 2.** respondWith() nhận loại giá trị nào?

**Đáp án:** Response hoặc Promise giải quyết thành Response. Nó phải được gọi đồng bộ trong fetch event listener và chỉ gọi một lần cho mỗi event.

**Câu 3.** Nếu không gọi respondWith(), điều gì xảy ra?

**Đáp án:** Browser thực hiện request theo quy trình fetch mặc định, như thể worker không thay response của request đó.

**Câu 4.** waitUntil() khác respondWith() thế nào?

**Đáp án:** respondWith() chọn response cho request; waitUntil() giữ event sống đủ lâu để hoàn tất tác vụ bổ sung như lưu response clone vào cache.

**Câu 5.** Vì sao cần response.clone() khi vừa trả response vừa lưu cache?

**Đáp án:** Body của Response là stream có thể tiêu thụ một lần. Clone tạo một nhánh để trả cho browser và một nhánh để Cache API lưu.

**Câu 6.** Vì sao không nên cache POST hoặc request thanh toán theo chiến lược thông thường?

**Đáp án:** Request có thể tạo tác dụng phụ và không an toàn khi replay. Cache có thể trả kết quả cũ hoặc gây gửi thao tác trùng; server vẫn cần idempotency và kiểm soát nghiệp vụ.

**Câu 7.** Cache API có tự hết hạn theo Cache-Control max-age không?

**Đáp án:** Không. Ứng dụng phải tự quản lý freshness, TTL, revalidation và xóa entry.

**Câu 8.** Vì sao fetch() trả HTTP 404 không đi vào catch?

**Đáp án:** HTTP 404 là Response hợp lệ ở tầng Fetch. Promise chỉ reject với lỗi network hoặc lỗi khiến request không hoàn tất; cần kiểm tra response.status/ok.

**Câu 9.** Service Worker có thể dùng để bỏ qua CORS không?

**Đáp án:** Không. CORS và giới hạn Response.type vẫn áp dụng. Worker không cấp quyền đọc response cross-origin cho script.

**Câu 10.** Vì sao cần pass-through Range request nếu chưa triển khai byte-range?

**Đáp án:** Media player cần status 206, Content-Range và đúng đoạn byte. Trả full response hoặc cache response partial sai cách có thể làm seek/playback lỗi.

## 17. Checklist triển khai Fetch interception

Trước khi phát hành Service Worker có fetch handler, hãy kiểm tra:

1. **Scope:** xác nhận script URL, registration scope và các client được kiểm soát.
2. **Secure context:** production dùng HTTPS và local lab dùng localhost.
3. **Routing:** chỉ intercept request đã được phân loại; request không khớp được browser xử lý mặc định.
4. **Method:** chỉ cache GET trong chiến lược thông thường; pass-through thao tác ghi.
5. **Origin:** xác định rõ same-origin/cross-origin và giữ nguyên CORS.
6. **respondWith:** gọi đồng bộ và một lần cho mỗi FetchEvent.
7. **waitUntil:** giữ tác vụ cache nền sống và xử lý lỗi độc lập.
8. **Body stream:** clone Request/Response trước khi dùng hai lần.
9. **Cache key:** giữ query và Vary semantics; tránh ignoreSearch thiếu kiểm soát.
10. **Cache policy:** kiểm tra status, content type, Cache-Control, Vary và nguồn response.
11. **Private data:** không cache response phụ thuộc session, cookie hoặc Authorization theo mặc định.
12. **Opaque response:** hiểu status 0 và không cache resource không rõ nguồn.
13. **Navigation:** chỉ dùng offline shell cho document navigation đúng scope.
14. **Range:** pass-through hoặc triển khai 206/Content-Range đầy đủ.
15. **Lifecycle:** version cache, xóa cache cũ có chọn lọc và kiểm tra worker waiting/active.
16. **Quota:** giới hạn cache, dọn runtime entries và có network fallback.
17. **Observability:** log tối thiểu, không ghi token/cookie/dữ liệu cá nhân.
18. **DevTools:** kiểm tra response source, cache hit, offline behavior và bypass for network.
19. **Regression:** test online/offline, account switch, redirect, CORS, 404/500 và browser mục tiêu.
20. **Server security:** mọi API vẫn phải kiểm tra authentication, authorization, CSRF và dữ liệu đầu vào.

**Ghi nhớ:** Fetch interception cho Service Worker quyền điều phối response của các request từ client được kiểm soát. Hãy dùng respondWith() để chọn response, waitUntil() cho tác vụ nền, chọn cache strategy theo độ nhạy cảm và vòng đời dữ liệu, đồng thời giữ nguyên các quy tắc Fetch/CORS. Cache đúng loại tài nguyên và giữ server làm nơi thực thi authorization.

## Tài liệu tham khảo

- [MDN — ServiceWorkerGlobalScope: fetch event](https://developer.mozilla.org/en-US/docs/Web/API/ServiceWorkerGlobalScope/fetch_event)
- [MDN — FetchEvent](https://developer.mozilla.org/en-US/docs/Web/API/FetchEvent)
- [MDN — FetchEvent.respondWith()](https://developer.mozilla.org/en-US/docs/Web/API/FetchEvent/respondWith)
- [MDN — ExtendableEvent.waitUntil()](https://developer.mozilla.org/en-US/docs/Web/API/ExtendableEvent/waitUntil)
- [MDN — Using Service Workers](https://developer.mozilla.org/en-US/docs/Web/API/Service_Worker_API/Using_Service_Workers)
- [MDN — Cache](https://developer.mozilla.org/en-US/docs/Web/API/Cache)
- [MDN — Cache.put()](https://developer.mozilla.org/en-US/docs/Web/API/Cache/put)
- [MDN — Fetch API](https://developer.mozilla.org/en-US/docs/Web/API/Fetch_API)
- [MDN — Fetch: Using Fetch](https://developer.mozilla.org/en-US/docs/Web/API/Fetch_API/Using_Fetch)
- [W3C — Service Workers](https://w3c.github.io/ServiceWorker/)

