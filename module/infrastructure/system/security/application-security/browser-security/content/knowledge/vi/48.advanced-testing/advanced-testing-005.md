# Service worker test

Kiểm thử service worker là quá trình xác minh worker được đăng ký đúng origin và scope, chuyển trạng thái đúng, chỉ xử lý request và message theo thiết kế, đồng thời không làm rò rỉ dữ liệu qua cache hoặc các tác vụ nền. Service worker chạy trong một ngữ cảnh riêng, không có DOM, có thể được browser đánh thức khi có event ngay cả lúc không có page đang mở và có quyền can thiệp vào các request thuộc phạm vi kiểm soát. Vì vậy, một lỗi trong worker có thể ảnh hưởng đến nhiều trang hoặc nhiều lần truy cập sau đó.

Trong bảo mật trình duyệt, service worker thường được dùng cho offline support, cache tài nguyên, push notification và đồng bộ nền. Những chức năng này mở thêm các đường xử lý dữ liệu: request đi qua `fetch` handler, response được lưu trong Cache Storage, message đến từ page hoặc worker khác, và phiên bản mới có thể thay thế worker cũ khi nhiều tab vẫn đang mở.

Mục tiêu của service worker test là chứng minh các ranh giới này được giữ đúng. Kiểm thử cần bao gồm cả hành vi thông thường, tình huống lỗi, cập nhật phiên bản và các đầu vào không tin cậy. Một service worker hoạt động tốt ở lần cài đầu tiên vẫn có thể gây lỗi bảo mật khi cache dữ liệu cá nhân, xử lý URL do trang cung cấp hoặc kích hoạt phiên bản mới trong lúc client cũ còn chạy.

## Service worker chạy trong ranh giới nào?

Service worker là script chạy trong môi trường worker do browser quản lý. Nó không thể truy cập trực tiếp `window`, DOM hoặc `localStorage`; thay vào đó, nó giao tiếp với các page client qua message và dùng các API phù hợp như `fetch`, Cache Storage và IndexedDB. Service worker gắn với một origin và một scope cụ thể.

~~~mermaid
flowchart TD
    Page[Page trong origin] -->|register và postMessage| Reg[ServiceWorkerRegistration]
    Reg --> SW[Service worker]
    SW -->|fetch event| Net[Network]
    SW -->|Cache API| Cache[Cache Storage]
    SW -->|IndexedDB| DB[IndexedDB]
    SW <-->|Client message| Other[Page hoặc client khác trong scope]
    SW -->|push / sync event nếu hỗ trợ| BG[Tác vụ nền]
~~~

Các điểm ranh giới cần ghi nhận:

- **Origin:** worker chỉ kiểm soát tài nguyên và client trong origin của nó. Trang ở origin khác không thể đăng ký worker để chiếm quyền nội dung của origin này.
- **Scope:** scope xác định những URL nào có thể được worker kiểm soát. Mặc định, scope là thư mục chứa file script worker; response header `Service-Worker-Allowed` có thể cho phép scope rộng hơn.
- **Secure context:** đăng ký service worker yêu cầu secure context. HTTPS là cách triển khai thông thường; `localhost` và loopback được browser coi là môi trường đáng tin cậy cho phát triển.
- **Lifecycle:** worker có thể bị dừng khi không hoạt động và được khởi động lại khi có event. Không dựa vào biến toàn cục để giữ trạng thái lâu dài.
- **Client:** page chỉ có `navigator.serviceWorker.controller` khi đang được một worker kiểm soát. Trang tải đầu tiên sau khi đăng ký có thể chưa được kiểm soát cho đến lần điều hướng sau, trừ khi worker chủ động gọi `clients.claim()`.

Service worker không bỏ qua Same-Origin Policy hoặc CORS. Request cross-origin do worker thực hiện vẫn chịu các quy tắc fetch và CORS tương ứng. Một response `opaque` từ request `no-cors` không cho worker đọc status hoặc header; cần cân nhắc kỹ trước khi đưa response đó vào cache.

## Kiểm tra đăng ký và scope

Đăng ký worker thường được thực hiện từ page:

~~~javascript
if ('serviceWorker' in navigator) {
  window.addEventListener('load', async () => {
    try {
      const registration = await navigator.serviceWorker.register('/sw.js', {
        scope: '/'
      });

      console.info('Service worker registration state', {
        scope: registration.scope,
        active: registration.active?.state ?? null
      });
    } catch (error) {
      // Không ghi token hoặc URL có dữ liệu nhạy cảm vào log.
      console.error('Service worker registration failed', error.name);
    }
  });
}
~~~

Khi review, xác minh:

1. Worker script được tải từ origin dự kiến và qua HTTPS trong môi trường triển khai.
2. URL script, scope và response header `Service-Worker-Allowed` không mở rộng quyền ngoài ý muốn.
3. File worker được trả về với JavaScript MIME type phù hợp; không trả nhầm HTML trang đăng nhập hoặc trang lỗi có status thành công.
4. Route đăng ký không redirect sang origin khác và không phụ thuộc vào một đường dẫn do người dùng điều khiển.
5. Một trang ngoài scope không bị worker kiểm soát; một trang trong scope được kiểm soát theo thiết kế sau khi lifecycle hoàn tất.

Ví dụ, worker ở `/app/sw.js` mặc định chỉ có thể kiểm soát URL dưới `/app/`. Nếu muốn worker đó kiểm soát `/`, server phải cho phép scope rộng hơn bằng `Service-Worker-Allowed: /`. Review cần xác nhận việc mở rộng này là chủ ý, vì nó làm tăng số route có thể bị fetch handler tác động.

Không nhầm `registration.scope` với URL của file script. Script xác định mã được chạy; scope xác định các client có thể bị worker kiểm soát. Hai giá trị có thể khác nhau và cần được kiểm tra riêng.

## Kiểm tra lifecycle và cập nhật

Lifecycle tiêu chuẩn của một worker mới gồm các trạng thái chính:

~~~mermaid
stateDiagram-v2
    [*] --> parsed: Script được tải và phân tích
    parsed --> installing: install event
    installing --> installed: Cài đặt thành công
    installed --> activating: Không còn worker cũ chặn hoặc skipWaiting
    activating --> activated: activate hoàn tất
    parsed --> redundant: Script lỗi
    installing --> redundant: install thất bại
    activating --> redundant: activate thất bại
    activated --> redundant: Worker bị thay thế hoặc unregister
~~~

Trong `install`, worker thường chuẩn bị cache ban đầu. Trong `activate`, worker có thể dọn cache phiên bản cũ và thực hiện migration. Một worker mới có thể ở trạng thái `waiting` trong khi worker cũ vẫn kiểm soát các tab đang mở.

Các thuộc tính cần quan sát trên `ServiceWorkerRegistration` gồm `installing`, `waiting`, `active`, `scope`, `updateViaCache` và sự kiện `updatefound`. Trên đối tượng `ServiceWorker`, các trạng thái thường gặp là `installing`, `installed`, `activating`, `activated` và `redundant`.

Kiểm thử các tình huống:

- Cài lần đầu: worker install và activate thành công; cache cần thiết được tạo đủ.
- Install thất bại: ví dụ một URL trong `cache.addAll()` trả lỗi. Worker mới phải bị loại bỏ và worker cũ tiếp tục hoạt động nếu có.
- Activate thất bại: worker không được đánh dấu hoạt động thành công khi migration hoặc dọn cache thất bại.
- Có tab cũ đang mở: worker mới có thể ở `waiting`; ứng dụng cần xử lý thông báo cập nhật và thời điểm chuyển phiên bản rõ ràng.
- Cập nhật worker: thay đổi nội dung script, import hoặc tài nguyên liên quan để xác minh browser phát hiện bản mới.
- Unregister: đăng ký bị xóa, nhưng Cache Storage và IndexedDB không tự động bị xóa. Kiểm thử phải xác minh chính sách dọn dữ liệu riêng.

`skipWaiting()` cho phép worker đang chờ chuyển sang giai đoạn activate sớm hơn. `clients.claim()` cho phép worker active nhận quyền kiểm soát các client phù hợp đang mở. Hai API này hữu ích khi cập nhật nhanh, nhưng có thể khiến page đang chạy mã cũ bị điều khiển bởi worker mới với cache hoặc giao thức message khác. Hãy kiểm thử tương thích giữa phiên bản page và worker, đặc biệt khi thay đổi schema cache, API message hoặc đường dẫn asset.

Đừng giả định `registration.update()` đồng nghĩa worker mới đã active và kiểm soát page. Cần quan sát `updatefound`, trạng thái `installing`/`waiting`/`active`, `controllerchange` và thực hiện điều hướng hoặc reload theo đúng thiết kế.

## Kiểm tra fetch handler và phạm vi request

Fetch handler là một trong những bề mặt bảo mật quan trọng nhất. Worker có thể trả response từ cache, gọi network, chuyển hướng hoặc tạo offline fallback. Một handler tổng quát có thể vô tình cache response cá nhân, phục vụ dữ liệu sai người dùng hoặc biến một URL do người dùng kiểm soát thành request nền.

Ví dụ worker cache-first giới hạn rõ ràng vào một số tài nguyên tĩnh cùng origin:

~~~javascript
const CACHE_NAME = 'site-static-v3';
const STATIC_PATHS = new Set([
  '/assets/app.css',
  '/assets/app.js',
  '/assets/logo.svg'
]);

self.addEventListener('install', (event) => {
  event.waitUntil((async () => {
    const cache = await caches.open(CACHE_NAME);
    await cache.addAll([...STATIC_PATHS]);
  })());
});

self.addEventListener('fetch', (event) => {
  const request = event.request;
  const url = new URL(request.url);

  if (request.method !== 'GET') return;
  if (url.origin !== self.location.origin) return;
  if (!STATIC_PATHS.has(url.pathname)) return;
  if (url.search) return;
  if (request.cache === 'no-store') return;
  if (request.headers.has('Authorization')) return;

  event.respondWith((async () => {
    const cache = await caches.open(CACHE_NAME);
    const cached = await cache.match(request);
    if (cached) return cached;

    const response = await fetch(request);
    const cacheControl = response.headers.get('Cache-Control') || '';
    const isPrivate = /\b(private|no-store)\b/i.test(cacheControl);

    if (response.status === 200 && response.type === 'basic' && !isPrivate) {
      await cache.put(request, response.clone());
    }

    return response;
  })());
});
~~~

Ví dụ này cố ý chỉ cache một danh sách đường dẫn tĩnh đã biết. Nó bỏ qua request không phải GET, request cross-origin, request `no-store` và request có header Authorization. Nó cũng không lưu response có `Cache-Control: private` hoặc `no-store`, và chỉ cache response cùng origin có type `basic`.

Đây là mẫu minh họa, không phải policy cache phù hợp cho mọi ứng dụng. Nếu ứng dụng dùng cookie để xác thực, request không nhất thiết có header Authorization; vì vậy allowlist đường dẫn vẫn phải loại trừ API, trang tài khoản, response cá nhân và mọi route có dữ liệu theo người dùng. Không dùng một điều kiện đơn giản để suy ra response là công khai.

### Các phép thử fetch cần có

| Đầu vào | Kết quả mong đợi |
|---|---|
| GET đến asset tĩnh trong allowlist | Worker có thể trả từ cache hoặc network theo chiến lược đã chọn |
| POST, PUT, DELETE | Không bị đưa vào cache tĩnh; được xử lý theo request gốc hoặc handler riêng |
| Request đến `/api/profile` | Không được cache nếu chứa dữ liệu cá nhân hoặc phụ thuộc phiên |
| Request cross-origin | Không bị cache theo quy tắc same-origin ở ví dụ; CORS vẫn do browser thực thi |
| Response `Cache-Control: private` hoặc `no-store` | Không ghi vào Cache Storage |
| URL có query string bất thường | Không được mở rộng allowlist do chỉ kiểm tra prefix; phải so khớp route đã chuẩn hóa |
| Response lỗi hoặc redirect ngoài dự kiến | Không ghi cache theo chính sách; xử lý lỗi không làm lộ dữ liệu |

Không dùng `url.pathname.startsWith('/assets')` làm allowlist duy nhất nếu có các route gần giống hoặc đường dẫn được chuẩn hóa khác nhau. Hãy so khớp đường dẫn chính xác hoặc dùng quy tắc route đã kiểm thử. Với các cache key có query string, mặc định Cache API xem query là một phần của request; tùy chọn bỏ qua query có thể làm các biến thể khác nhau dùng chung response và gây lẫn dữ liệu.

## Kiểm thử Cache Storage và cache poisoning

Cache Storage khác HTTP cache của browser. Nó được service worker thao tác trực tiếp và có thể tồn tại qua nhiều lần đóng/mở tab. Một response đã được cache có thể tiếp tục được phục vụ ngay cả khi server đã thay đổi nếu chiến lược update và invalidation không đúng.

Kiểm tra các điểm sau:

- Cache chỉ chứa tài nguyên đã được cho phép và không chứa trang cá nhân, API nhạy cảm, response có token hoặc dữ liệu theo session.
- Cache name có phiên bản rõ ràng; activate chỉ xóa cache thuộc namespace của ứng dụng, không xóa cache của ứng dụng khác trên cùng origin.
- Không cache response lỗi, response ngoài origin hoặc response chưa kiểm tra theo policy.
- Không dùng dữ liệu query, header hoặc message không tin cậy để chọn cache key hay ghi đè response cho người dùng khác.
- Cache cũ được dọn sau cập nhật; cache mới được tạo đầy đủ trước khi worker mới được kích hoạt.
- Đăng xuất, đổi tài khoản hoặc thu hồi quyền có chính sách xóa dữ liệu nhạy cảm phù hợp.

Cache poisoning có thể xảy ra khi worker lưu một response được tạo từ đầu vào không tin cậy hoặc khi cache key không phân biệt đúng các biến thể. Ví dụ, một handler dùng `ignoreSearch: true` cho `/api/profile` có thể bỏ qua query phân biệt tài khoản hoặc ngôn ngữ. Một handler cache mọi response GET có thể lưu trang HTML cá nhân hóa rồi phục vụ lại cho người dùng khác trên cùng browser profile.

Không dựa vào Cache Storage như kho bí mật. Các script cùng origin có thể có khả năng đọc dữ liệu cache; XSS trong ứng dụng có thể khai thác quyền cùng origin để đọc hoặc thay đổi dữ liệu lưu trữ. Dữ liệu nhạy cảm nên được hạn chế lưu offline; nếu bắt buộc, cần thiết kế mã hóa, vòng đời và quản lý khóa phù hợp, đồng thời đánh giá khả năng XSS truy cập dữ liệu khi ứng dụng đang chạy.

## Kiểm tra message giữa page và worker

Page và service worker thường dùng `navigator.serviceWorker.controller.postMessage()` để trao đổi. Message event không tự động đáng tin chỉ vì đến từ một page cùng origin. Nếu trang có XSS hoặc nội dung không tin cậy điều khiển được, nó có thể gửi message giả để yêu cầu worker thực hiện hành động.

Ví dụ handler chỉ hỗ trợ một yêu cầu đọc phiên bản không nhạy cảm:

~~~javascript
const BUILD_VERSION = '3.2.0';
const APP_ORIGIN = self.location.origin;

self.addEventListener('message', (event) => {
  let sourceUrl;
  try {
    if (!event.source || !('url' in event.source)) return;
    sourceUrl = new URL(event.source.url);
  } catch {
    return;
  }

  const scopeUrl = new URL(self.registration.scope);
  if (sourceUrl.origin !== APP_ORIGIN) return;
  if (!sourceUrl.pathname.startsWith(scopeUrl.pathname)) return;

  const message = event.data;
  if (!message || typeof message !== 'object') return;
  if (message.type !== 'GET_BUILD_VERSION') return;

  const port = event.ports[0];
  if (!port) return;

  port.postMessage({
    type: 'BUILD_VERSION',
    version: BUILD_VERSION
  });
});
~~~

Trong production, cần bắt lỗi khi phân tích URL của `event.source.url`, kiểm tra schema đầy đủ và xác định rõ loại source được hỗ trợ. Ví dụ trên chỉ minh họa cách giới hạn origin và loại message. Kiểm tra origin không đủ để chứng minh message an toàn: page cùng origin vẫn có thể bị XSS. Không tạo các lệnh tổng quát như `EXECUTE`, `FETCH_URL`, `READ_COOKIE` hoặc `DELETE_ALL_DATA` mà không có quyền và điều kiện nghiệp vụ được kiểm soát chặt chẽ.

Các phép thử message:

1. Message đúng schema từ page được phép phải nhận response đúng định dạng.
2. Message thiếu trường, sai kiểu, quá dài hoặc có object lồng bất thường phải bị từ chối an toàn.
3. Message có type không được hỗ trợ không được kích hoạt hành động đặc quyền.
4. Message từ client ngoài scope hoặc nguồn không hợp lệ không được xử lý như yêu cầu tin cậy.
5. Worker không trả token, dữ liệu cá nhân hoặc dữ liệu cache cho mọi client cùng origin nếu không có kiểm tra quyền riêng.
6. Nhiều tab gửi message đồng thời không được nhận nhầm response hoặc trạng thái của tab khác.

Nếu dùng `MessageChannel`, kiểm tra worker chỉ trả response qua port tương ứng và đóng port khi hoàn tất. Không dùng một biến toàn cục duy nhất để ghép request-response của nhiều tab.

## Kiểm thử offline và navigation fallback

Offline support cần kiểm thử riêng cho navigation và subresource. Một trang fallback có thể hữu ích khi người dùng mất mạng, nhưng không nên trả HTML fallback cho mọi request vì API hoặc request POST có thể bị hiểu nhầm là thành công.

Kiểm tra:

- Navigation GET khi online tải đúng document từ server.
- Navigation GET khi offline trả fallback dành cho người dùng, không chứa dữ liệu cá nhân cũ.
- API request khi offline trả lỗi phù hợp theo hợp đồng API; không trả HTML offline page với status 200 nếu client đang mong JSON.
- POST hoặc các method thay đổi dữ liệu không được phát lại tự động trừ khi thiết kế có idempotency key và cơ chế retry an toàn.
- Request có query hoặc header ảnh hưởng nội dung không bị dùng chung cache với request khác.
- Fallback không làm lộ thông tin route riêng tư, tên tài khoản hoặc dữ liệu đã lưu của session trước.

Nếu worker dùng navigation preload, kiểm thử cả trường hợp preload thành công, timeout và response lỗi. Navigation preload có thể giảm độ trễ bằng cách bắt đầu network request song song với việc khởi động worker; handler phải chọn đúng response và không tạo hai lần ghi dữ liệu ngoài ý muốn.

## Kiểm thử push notification và tác vụ nền

Nếu ứng dụng dùng Push API, push event được chuyển đến service worker kể cả khi page không mở. Review payload như dữ liệu đầu vào cần kiểm tra: parse JSON an toàn, giới hạn kích thước và không hiển thị nội dung tùy ý dưới dạng HTML.

Với `notificationclick`, kiểm tra URL đích được chuẩn hóa và giới hạn về origin/route được phép. Không để payload push điều khiển worker mở một URL tùy ý hoặc điều hướng người dùng đến trang lừa đảo. Nếu dùng Background Sync, kiểm tra retry có giới hạn, thao tác có idempotent và dữ liệu được lưu hàng đợi có thời hạn phù hợp.

Push subscription chứa endpoint và khóa cần bảo vệ. Không ghi subscription, endpoint push hoặc payload nhạy cảm vào log công khai. Khi người dùng đăng xuất hoặc thu hồi quyền, xác minh ứng dụng xử lý subscription và dữ liệu hàng đợi theo chính sách đã công bố.

## Kiểm thử cập nhật và tính nhất quán phiên bản

Một rủi ro đặc trưng của service worker là page và worker có thể chạy hai phiên bản khác nhau. Ví dụ, page cũ gửi message schema v1 nhưng worker mới chỉ chấp nhận schema v2; hoặc worker mới xóa cache cũ trong khi tab cũ vẫn cần asset cũ.

Hãy kiểm thử các kịch bản:

- Tab A đang mở bằng worker v1; tab B kích hoạt cập nhật v2.
- Worker v2 cài đặt nhưng bị chờ vì v1 vẫn kiểm soát client.
- Người dùng chọn cập nhật ngay và v2 gọi `skipWaiting()`/`clients.claim()`.
- Tab cũ gửi message, request hoặc tham chiếu asset theo giao thức v1 sau khi v2 active.
- Cache v1 được giữ hoặc xóa theo chính sách tương thích; không xóa sớm tài nguyên mà client cũ còn cần.
- Cập nhật thất bại giữa chừng và browser tiếp tục dùng worker cũ.

Thiết kế an toàn thường giữ tương thích trong một khoảng chuyển đổi: worker mới hiểu message cũ trong thời gian cần thiết, cache được version hóa và việc xóa cache cũ chỉ diễn ra khi không còn client phụ thuộc. Nếu cần chuyển đổi tức thời, phải có cơ chế buộc reload và thông báo rõ ràng cho người dùng.

Thuộc tính `updateViaCache` của registration ảnh hưởng cách browser dùng HTTP cache khi kiểm tra script worker và các script import. Giá trị thường gặp là `imports` (mặc định), `all` và `none`. Kiểm thử quy trình deploy cần xác minh browser phát hiện script mới theo cấu hình thực tế, CDN không phục vụ worker cũ ngoài dự kiến và các file import không bị lệch phiên bản.

## Kiểm thử bằng DevTools

Trong Chrome DevTools, mở tab Application rồi chọn Service Workers. Tại đây có thể quan sát script URL, scope, trạng thái, thời điểm update, worker đang chạy và các thao tác như Update, Skip waiting hoặc Unregister.

Chọn Cache Storage để xem cache name, request key và response đã lưu. Chọn Storage để kiểm tra dữ liệu liên quan trong origin. Dùng Network để xác định request nào được worker xử lý, request nào đi thẳng network và response có đến từ service worker hay không. Khi kiểm tra offline, bật chế độ Offline trong DevTools hoặc dùng chức năng mô phỏng offline của automation.

Một số thao tác hữu ích:

- **Update:** yêu cầu browser kiểm tra bản script mới.
- **Unregister:** xóa registration; thao tác này không tự xóa Cache Storage hoặc IndexedDB.
- **Skip waiting:** yêu cầu worker waiting chuyển sang activate sớm; chỉ dùng khi đang kiểm thử hành vi cập nhật.
- **Offline:** xác minh fallback và cache hoạt động khi network bị ngắt.
- **Update on reload:** tiện ích phát triển giúp kiểm tra worker mới trong lần reload; không nên coi đây là hành vi production.

Sau khi kiểm thử, khôi phục trạng thái browser và xóa profile thử nghiệm nếu nó chứa dữ liệu test cần loại bỏ. Không dùng Unregister như cách duy nhất để xác nhận dữ liệu đã được xóa.

## Tự động hóa kiểm thử bằng Playwright

Playwright có thể kiểm tra đăng ký, scope, controller và hành vi offline. Ví dụ sau giả định ứng dụng tự đăng ký `/sw.js` khi mở trang `/sw-test/` và worker kiểm soát scope `/`:

~~~javascript
import { test, expect } from '@playwright/test';

test('registers a worker with the expected scope', async ({ page }) => {
  await page.goto('/sw-test/');

  const registration = await page.evaluate(async () => {
    const reg = await navigator.serviceWorker.ready;
    return {
      scope: reg.scope,
      activeState: reg.active?.state ?? null
    };
  });

  expect(registration.scope).toBe('https://app.example.test/');
  expect(registration.activeState).toBe('activated');

  await page.reload();
  await expect.poll(() => page.evaluate(() => Boolean(navigator.serviceWorker.controller)))
    .toBe(true);
});

test('serves an allowlisted static asset while offline', async ({ page, context }) => {
  await page.goto('/sw-test/');
  await page.evaluate(async () => {
    await navigator.serviceWorker.ready;
    return true;
  });
  await page.reload();

  const warmResult = await page.evaluate(async () => {
    const response = await fetch('/assets/app.js');
    return { ok: response.ok, body: await response.text() };
  });
  expect(warmResult.ok).toBe(true);

  await context.setOffline(true);
  const offlineResult = await page.evaluate(async () => {
    try {
      const response = await fetch('/assets/app.js');
      return { ok: response.ok, body: await response.text() };
    } catch {
      return { ok: false, body: '' };
    }
  });

  expect(offlineResult.ok).toBe(true);
  expect(offlineResult.body).toBe(warmResult.body);
  await context.setOffline(false);
});
~~~

Đây là ví dụ khung cần điều chỉnh theo origin và fixture của dự án. `navigator.serviceWorker.ready` chờ registration có active worker, nhưng không đảm bảo page hiện tại đã được điều khiển; vì vậy ví dụ reload rồi mới kiểm tra `controller`. Nếu worker gọi `clients.claim()`, thời điểm được kiểm soát có thể khác, nên test cần chờ sự kiện hoặc điều kiện thực tế thay vì dựa vào sleep cố định.

Khi dùng Playwright, mặc định browser context cho phép service worker. Nếu cấu hình `serviceWorkers: 'block'`, các test service worker sẽ không hoạt động như production. Không dùng route interception như bằng chứng duy nhất về fetch handler, vì service worker có thể ảnh hưởng cách Playwright quan sát request. Kết hợp kiểm tra từ page, browser context và DevTools protocol theo nhu cầu.

## Các lỗi thường gặp trong service worker test

| Lỗi | Hệ quả | Cách kiểm tra hoặc sửa |
|---|---|---|
| Chỉ kiểm tra `register()` không kiểm tra controller | Page hiện tại có thể chưa được worker kiểm soát | Chờ active worker và kiểm tra sau navigation hoặc `clients.claim()` |
| Scope rộng ngoài nhu cầu | Worker có thể can thiệp nhiều route hơn dự kiến | Kiểm tra scope và `Service-Worker-Allowed` |
| Cache mọi GET response | Có thể lưu dữ liệu cá nhân hoặc response theo session | Chỉ cache asset công khai trong allowlist rõ ràng |
| Dùng `ignoreSearch: true` tùy tiện | Các URL có query khác nhau có thể dùng chung cache entry | Xác định cache key và query có ý nghĩa |
| Xóa mọi cache trong activate | Làm mất cache của ứng dụng khác trên cùng origin hoặc phá client cũ | Dùng namespace và version cache riêng |
| Gọi `skipWaiting()` không kiểm tra tương thích | Worker mới có thể điều khiển page cũ | Test phiên bản page/worker và quy trình reload |
| Tin message từ page cùng origin | XSS có thể gửi message độc hại | Kiểm tra schema, source, quyền và allowlist hành động |
| Unregister nhưng cho rằng dữ liệu đã xóa | Cache Storage và IndexedDB vẫn có thể tồn tại | Kiểm tra và xóa từng kho theo chính sách |
| Dùng service worker để vượt CORS | Request cross-origin vẫn bị áp dụng quy tắc fetch/CORS | Kiểm thử preflight, credentials và response type |
| Test offline chỉ trên trang chủ | API hoặc route khác có thể trả fallback sai | Test navigation, asset, API và method riêng biệt |

## Quy trình kiểm thử trước khi phát hành

1. Xác định origin, script URL, scope và các route được worker kiểm soát.
2. Kiểm tra secure context, MIME type, redirect, CSP `worker-src` và header `Service-Worker-Allowed`.
3. Kiểm thử install, activate, waiting, update, lỗi cài đặt và unregister.
4. Kiểm tra fetch handler với method, origin, path, query, header, redirect và response khác nhau.
5. Xác minh Cache Storage chỉ giữ dữ liệu được phép; kiểm tra cache poisoning, cache key và invalidation.
6. Kiểm thử message từ page, nhiều tab, schema sai và nguồn không hợp lệ.
7. Kiểm tra offline fallback, navigation preload, push hoặc sync nếu ứng dụng sử dụng.
8. Kiểm thử cập nhật khi tab cũ còn mở và xác minh tính tương thích page/worker/cache.
9. Chạy test tự động trên browser mục tiêu và lưu lại kết quả, phiên bản worker, scope và trạng thái cache.
10. Xóa profile thử nghiệm và dữ liệu test theo quy trình, rồi xác minh môi trường sạch.

## Checklist service worker test

- [ ] Registration chỉ chạy trên secure context và đúng origin.
- [ ] Script URL, scope và `Service-Worker-Allowed` nằm trong phạm vi dự kiến.
- [ ] Response script có MIME type phù hợp và không redirect ngoài ý muốn.
- [ ] Lifecycle install, activate, waiting, update và lỗi đã được kiểm tra.
- [ ] Page hiện tại chỉ được coi là controlled khi `navigator.serviceWorker.controller` xác nhận.
- [ ] Fetch handler giới hạn method, origin và allowlist đường dẫn.
- [ ] API, response cá nhân, `private` và `no-store` không bị cache.
- [ ] Cache key, query string, versioning và dọn cache không gây lẫn dữ liệu.
- [ ] Message handler kiểm tra source, schema và loại hành động được phép.
- [ ] Offline fallback không làm sai hợp đồng API hoặc phát lại thao tác ghi dữ liệu.
- [ ] Push, notification click và background sync được kiểm tra nếu có sử dụng.
- [ ] Cập nhật worker không phá page cũ hoặc cache đang được client sử dụng.
- [ ] Unregister, logout và xóa dữ liệu được kiểm tra riêng.
- [ ] Đã kiểm thử bằng browser thực tế và automation với service worker được bật.

## Câu hỏi tự kiểm tra

1. Vì sao page có thể đăng ký service worker thành công nhưng `navigator.serviceWorker.controller` vẫn là `null`?
2. `scope` và URL của worker script có vai trò khác nhau như thế nào?
3. Vì sao cache mọi response GET có thể làm lộ dữ liệu giữa các phiên hoặc tài khoản?
4. `skipWaiting()` và `clients.claim()` có thể gây lỗi tương thích nào khi nhiều tab đang mở?
5. Vì sao message từ page cùng origin vẫn phải được kiểm tra schema và quyền?
6. Vì sao `unregister()` không đủ để xác nhận toàn bộ dữ liệu offline đã bị xóa?

Service worker là một thành phần có vòng đời độc lập và có thể tác động đến nhiều lần truy cập sau khi page ban đầu đã đóng. Một bài kiểm thử đầy đủ phải quan sát cả registration, lifecycle, scope, fetch, cache, message và update. Hãy dùng dữ liệu thử nghiệm, kiểm tra browser thực tế và lưu bằng chứng cho từng ranh giới để phát hiện sớm lỗi có thể làm lộ dữ liệu hoặc trao quyền ngoài dự kiến.
