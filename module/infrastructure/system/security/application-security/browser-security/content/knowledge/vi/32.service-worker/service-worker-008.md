# Service worker takeover

**Service worker takeover** là thời điểm một service worker đang chờ hoặc vừa được kích hoạt trở thành worker điều khiển các trang thuộc phạm vi đăng ký của nó. Đây là một phần bình thường trong vòng đời Service Worker: browser tải phiên bản mới, cài đặt nó, chờ các trang đang dùng phiên bản cũ kết thúc, rồi chuyển quyền điều khiển sang phiên bản mới.

Hai API thường được dùng để rút ngắn quá trình chuyển giao là **skipWaiting()** và **clients.claim()**. skipWaiting() cho phép worker mới bỏ qua trạng thái waiting để được kích hoạt dù các trang cũ vẫn đang mở. clients.claim() cho phép worker đã active nhận quyền điều khiển các client hiện có trong scope và phát sự kiện controllerchange ở các trang bị chuyển quyền.

Takeover cũng có thể trở thành sự cố bảo mật. Service worker có thể trung gian xử lý các request do trang đang được nó kiểm soát khởi tạo, trả response từ cache hoặc thay đổi response trước khi trang nhận. Nếu attacker kiểm soát được script service worker cùng origin và đăng ký nó với scope rộng, mã độc có thể tiếp tục ảnh hưởng các lần truy cập sau, kể cả khi đoạn XSS ban đầu không còn xuất hiện trên trang.

Bài học thuộc chương **Service worker** trong module **Browser Security** (SECURITY_APPLICATION_SECURITY_BROWSER_SECURITY). Nội dung phân tích ranh giới giữa browser, origin, cookie và ứng dụng web; tập trung vào lifecycle takeover, skipWaiting(), clients.claim(), scope, rủi ro chiếm quyền điều khiển và cách triển khai cập nhật an toàn.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích takeover trong lifecycle của service worker và phân biệt takeover bình thường với takeover do script bị xâm phạm.
2. Mô tả các trạng thái installing, installed/waiting, activating, activated và redundant.
3. Phân biệt vai trò của skipWaiting() và clients.claim().
4. Theo dõi registration, waiting worker, active worker, controller và sự kiện controllerchange.
5. Giải thích scope, giới hạn same-origin và vai trò của header Service-Worker-Allowed.
6. Nhận diện cách XSS, endpoint upload, deployment pipeline hoặc tài khoản publish có thể dẫn tới đăng ký worker không mong muốn.
7. Dùng CSP worker-src và Trusted Types để giới hạn nguồn script URL đăng ký.
8. Thiết kế cập nhật tương thích giữa phiên bản trang, service worker, cache và API backend.
9. Kiểm tra takeover bằng DevTools và Node.js lab có phiên bản worker v1, v2 waiting và v2 fast takeover.
10. Xây dựng quy trình phát hiện, thu hồi registration đáng ngờ và khôi phục ứng dụng.

## 2. Takeover là gì?

Service worker chạy trong một worker context riêng, không có DOM và không hoạt động liên tục như một thread luôn mở. Browser đánh thức nó khi có event cần xử lý, ví dụ fetch, message, push hoặc lifecycle event; khi rảnh, browser có thể dừng execution context để tiết kiệm tài nguyên.

Registration được lưu lâu dài hơn vòng đời của một instance service worker. Khi một trang nằm trong scope được tải, browser có thể gắn trang đó với worker đang active. Worker có thể xử lý fetch event của các trang do nó kiểm soát và quyết định dùng network, cache hoặc response do chính worker tạo.

**Takeover** mô tả việc thay đổi worker đang điều khiển client:

- Lần cài đặt đầu: worker mới được cài và active; trang hiện đang mở chỉ được kiểm soát ngay nếu worker gọi clients.claim(), nếu không trang thường cần navigation/reload tiếp theo.
- Cập nhật thông thường: worker mới được cài nhưng ở trạng thái waiting trong khi worker cũ vẫn kiểm soát các trang đang mở.
- Cập nhật nhanh: worker mới gọi skipWaiting() để được active sớm; sau đó clients.claim() có thể chuyển các trang đang mở sang worker mới.

Takeover tự nó không phải hành vi độc hại. Ứng dụng PWA thường dùng nó để phát hành bản sửa lỗi hoặc cập nhật offline cache. Rủi ro xuất hiện khi worker mới chưa tương thích với các trang cũ, hoặc khi script được đăng ký không còn là artifact mà nhóm phát triển đã phê duyệt.

### 2.1. Service worker có thể tác động tới điều gì?

Một service worker đang kiểm soát trang có thể:

- Nhận fetch event cho request do trang được kiểm soát khởi tạo.
- Trả response từ Cache Storage hoặc tạo response mới.
- Gọi network rồi xử lý response trước khi trả lại cho trang.
- Điều hướng hoặc thay đổi nội dung mà trang nhận qua các response.
- Gửi message tới client trong scope và phối hợp với mã trang.
- Duy trì dữ liệu trong Cache Storage hoặc IndexedDB giữa các lần mở trang.

Service worker không có quyền truy cập trực tiếp vào DOM của trang, localStorage hoặc giao diện người dùng. Tuy nhiên, nếu nó trả về HTML hoặc JavaScript đã bị thay đổi cho một trang cùng origin, mã được tải trong trang đó có thể chạy với quyền của trang. Worker cũng có thể quan sát và xử lý dữ liệu request/response mà nó trung gian, nên response API nhạy cảm có thể bị ảnh hưởng.

### 2.2. Takeover bình thường và takeover bị xâm phạm

| Khía cạnh | Takeover bình thường | Takeover bị xâm phạm |
| --- | --- | --- |
| Nguồn script | Artifact đã review và deploy | Script cùng origin bị thay đổi hoặc URL đăng ký bị điều khiển |
| Mục tiêu | Cập nhật chức năng, cache hoặc sửa lỗi | Duy trì khả năng can thiệp request và nội dung |
| Thời điểm | Theo lifecycle hoặc sau thao tác người dùng | Có thể kích hoạt nhanh bằng skipWaiting() và clients.claim() |
| Phạm vi | Scope đã được thiết kế | Có thể bị mở rộng quá mức |
| Kiểm soát | Version, compatibility, rollback | Khó phát hiện nếu không kiểm tra registration và scriptURL |

## 3. Lifecycle và điểm chuyển quyền điều khiển

Service worker có các trạng thái chính:

| State | Ý nghĩa |
| --- | --- |
| installing | Browser đang cài worker và xử lý event install |
| installed / waiting | Cài đặt thành công; worker có thể chờ worker cũ nhường quyền |
| activating | Browser đang chạy event activate |
| activated | Worker đã active và có thể kiểm soát client trong scope |
| redundant | Worker không còn được sử dụng, ví dụ cài đặt thất bại hoặc đã bị thay thế |

### 3.1. Lần cài đặt đầu tiên

~~~mermaid
flowchart TD
    A["Trang đăng ký service worker"] --> B["Browser tải script"]
    B --> C["install"]
    C --> D{"Install hoàn tất thành công?"}
    D -->|Không| E["redundant"]
    D -->|Có| F["activate"]
    F --> G["Worker active"]
    G --> H{"Có gọi clients.claim()?"}
    H -->|Có| I["Claim client đang mở trong scope"]
    H -->|Không| J["Trang mới hoặc lần reload sau được kiểm soát"]
~~~

Khi cài worker lần đầu, không có worker cũ cần chờ. Sau khi activate, worker kiểm soát các trang được mở sau đó trong scope. Các trang đã mở trước khi registration hoàn tất thường vẫn không có controller cho tới khi reload; clients.claim() cho phép active worker nhận các client phù hợp đang mở.

### 3.2. Cập nhật thông thường

Khi browser phát hiện script mới khác phiên bản đang dùng, nó cài worker mới ở background. Worker cũ tiếp tục active và xử lý các trang đang được nó kiểm soát. Worker mới ở trạng thái waiting cho đến khi không còn client do worker cũ kiểm soát và các event đang xử lý hoàn tất.

~~~mermaid
sequenceDiagram
    participant P as Trang đang mở
    participant W1 as Worker v1
    participant W2 as Worker v2
    P->>W1: Request trong scope
    W1-->>P: Response theo v1
    Note over W2: Browser tải script v2
    W2->>W2: install thành công
    Note over W1,W2: v1 active, v2 waiting
    P->>W1: Tiếp tục request
    W1-->>P: Response theo v1
    P-->>W1: Client đóng
    W2->>W2: activate
    Note over W2: v2 trở thành active
~~~

Cơ chế chờ giúp tránh việc hai phiên bản service worker điều khiển các trang đang chạy cùng lúc trong cùng registration. Nó cũng giúp trang cũ không bị chuyển sang worker mới giữa một phiên làm việc nếu ứng dụng chưa chủ động cho phép.

### 3.3. Cập nhật nhanh

Nếu worker mới gọi skipWaiting() trong quá trình install, browser có thể kích hoạt worker đó dù worker cũ vẫn có client đang mở. Sau khi worker mới active, clients.claim() có thể đổi controller của các client trong scope.

~~~mermaid
sequenceDiagram
    participant P as Trang đang mở
    participant W1 as Worker v1
    participant W2 as Worker v2
    P->>W1: Request trong scope
    W1-->>P: Response v1
    Note over W2: Browser cài script v2
    W2->>W2: skipWaiting()
    W2->>W2: activate
    W2->>P: clients.claim()
    P-->>P: controllerchange
    P->>W2: Request tiếp theo
    W2-->>P: Response v2
~~~

Trang đang mở có thể vẫn giữ JavaScript, DOM và trạng thái bộ nhớ của bản giao diện cũ, trong khi request tiếp theo được worker v2 xử lý. Đây là điểm dễ tạo lỗi tương thích nếu worker mới đổi cache key, cấu trúc response, API hoặc schema dữ liệu.

## 4. skipWaiting() và clients.claim() khác nhau thế nào?

Hai API thường được nhắc cùng nhau nhưng giải quyết hai bước khác nhau.

### 4.1. skipWaiting()

skipWaiting() cho phép worker đang waiting chuyển sang active mà không phải đợi các client đang được worker cũ kiểm soát đóng lại.

Ví dụ:

~~~js
self.addEventListener('install', (event) => {
  event.waitUntil(self.skipWaiting());
});
~~~

Gọi skipWaiting() không bỏ qua bước install. Nếu install thất bại, worker không trở thành phiên bản active hợp lệ. API này cũng không tự động bảo đảm mọi trang đang mở đổi controller ngay lập tức.

### 4.2. clients.claim()

clients.claim() được gọi bởi worker đã active. Nó đặt worker đó làm controller cho các client hiện có trong scope. Các trang bị chuyển controller nhận sự kiện controllerchange trên navigator.serviceWorker.

~~~js
self.addEventListener('activate', (event) => {
  event.waitUntil(clients.claim());
});
~~~

clients.claim() không làm worker waiting bỏ qua hàng chờ. Nếu worker mới chưa active, gọi clients.claim() không thể biến nó thành active.

### 4.3. Kết hợp hai API

~~~js
self.addEventListener('install', (event) => {
  event.waitUntil(self.skipWaiting());
});

self.addEventListener('activate', (event) => {
  event.waitUntil(clients.claim());
});
~~~

Kết hợp này cho phép bản mới được active sớm và nhận các client đang mở trong scope. Chỉ dùng khi phiên bản mới tương thích với những trang cũ còn đang chạy, hoặc khi ứng dụng đã có cơ chế yêu cầu người dùng reload/chuyển phiên an toàn.

### 4.4. Khi nào nên để worker chờ?

Giữ worker ở trạng thái waiting thường phù hợp khi:

- Trang có các thao tác dài như thanh toán, upload hoặc chỉnh sửa biểu mẫu.
- Worker mới thay đổi cấu trúc cache hoặc API response.
- Ứng dụng cần người dùng xác nhận trước khi reload.
- Backend đang trong giai đoạn chuyển đổi và cần hỗ trợ cả hai phiên bản client.

Có thể gửi thông báo “Có bản cập nhật, tải lại để áp dụng” và chỉ yêu cầu trang reload khi người dùng hoàn thành thao tác hiện tại. Nếu cần kích hoạt theo lựa chọn người dùng, trang có thể gửi message tới waiting worker để worker gọi skipWaiting().

## 5. Scope quyết định worker có thể kiểm soát trang nào

Service worker chỉ được đăng ký từ secure context, thông thường là HTTPS; browser cho phép localhost như một ngoại lệ phục vụ phát triển. Script URL và scope phải cùng origin với trang đăng ký.

Scope là phạm vi URL của các document mà worker có thể kiểm soát. Nó được xác định khi gọi navigator.serviceWorker.register().

~~~js
navigator.serviceWorker.register('/sw.js', {
  scope: '/',
});
~~~

Trong ví dụ trên, script nằm ở root và scope là root nên worker có thể kiểm soát các trang thuộc origin bên dưới đường dẫn /.

### 5.1. Scope mặc định

Nếu không truyền scope, scope mặc định là thư mục chứa script service worker:

| Script URL | Scope mặc định |
| --- | --- |
| /sw.js | / |
| /assets/sw.js | /assets/ |
| /app/sw.js | /app/ |

Đặt script ở thư mục con thường giúp giới hạn blast radius. Nếu cần một script nằm trong thư mục con nhưng kiểm soát scope rộng hơn, server phải chủ động cho phép bằng response header Service-Worker-Allowed.

### 5.2. Service-Worker-Allowed có thể mở rộng scope

Ví dụ script nằm ở /assets/sw.js nhưng ứng dụng muốn scope là root:

~~~http
Service-Worker-Allowed: /
~~~

Sau đó có thể đăng ký:

~~~js
navigator.serviceWorker.register('/assets/sw.js', {
  scope: '/',
});
~~~

Header này phải được trả trong response của chính file service worker. Nó mở rộng phạm vi tối đa mà script được phép đăng ký. Không thêm nó chỉ để registration “chạy được”; hãy xác định các trang cần worker kiểm soát và chỉ cấp scope rộng khi có lý do rõ ràng.

### 5.3. Scope không vượt qua origin

Một worker ở https://app.example.com không thể kiểm soát document của https://payments.example.net. Khác subdomain, scheme hoặc port là khác origin.

Một origin có thể có nhiều registration với scope khác nhau. Khi scope chồng lấn, browser chọn registration có scope cụ thể nhất cho document. Tránh tạo các scope chồng lấn nếu kiến trúc không thực sự cần.

### 5.4. Scope là phạm vi client, không phải allowlist API

Scope xác định document nào có thể bị worker kiểm soát. Khi một document đã được kiểm soát, fetch event có thể được phát cho các request mà document đó khởi tạo, kể cả request tới tài nguyên bên ngoài. Vì vậy, không nên hiểu scope chỉ là danh sách URL tài nguyên mà worker được phép đọc.

## 6. Service worker takeover có thể bị khai thác ra sao?

Một takeover độc hại thường cần attacker có khả năng đưa script service worker do họ kiểm soát vào một URL cùng origin và khiến browser đăng ký URL đó với scope phù hợp.

Một số con đường có thể dẫn tới điều kiện này:

- **Compromise deployment:** attacker chiếm tài khoản deploy, CI/CD hoặc quyền ghi static assets và thay file worker.
- **Compromise origin/CDN:** endpoint cùng origin phục vụ script worker bị sửa nội dung.
- **Upload cùng origin không an toàn:** ứng dụng lưu file người dùng dưới cùng origin, cho phép file JavaScript được phục vụ như script có thể đăng ký.
- **XSS kết hợp endpoint script có thể kiểm soát:** attacker thực thi JavaScript trong trang và có một URL cùng origin trả về script do attacker kiểm soát.
- **URL đăng ký không đáng tin:** ứng dụng lấy scriptURL từ query, message, API response hoặc dữ liệu người dùng mà không kiểm tra.

Chỉ có khả năng chạy một đoạn inline JavaScript qua XSS không đồng nghĩa attacker có thể đăng ký tùy ý script từ origin khác hoặc từ blob URL. Service worker có yêu cầu same-origin và secure context; attacker còn cần một script URL phù hợp trên origin của ứng dụng hoặc khả năng thay đổi nội dung script được phục vụ tại đó.

### 6.1. Vì sao takeover có thể tồn tại sau khi XSS biến mất?

Một đoạn XSS thường chỉ chạy khi trang có payload hoặc lỗ hổng được khai thác. Khi service worker độc hại đã đăng ký thành công, registration tồn tại độc lập với tab ban đầu. Browser có thể khởi động worker lại khi có event phù hợp.

Worker độc hại có thể:

1. Kiểm soát các document trong scope.
2. Can thiệp response HTML hoặc JavaScript mà các document nhận.
3. Thay nội dung offline cache hoặc trả response cũ/giả.
4. Chuyển hướng request hoặc gửi dữ liệu response tới endpoint ngoài.
5. Tiếp tục ảnh hưởng các lần truy cập tiếp theo cho tới khi registration và script được xử lý.

Service worker không chạy liên tục trong nền và không tự động có quyền đọc DOM, localStorage hoặc cookie như một trang. Tuy nhiên, khả năng trung gian fetch và trả nội dung cho trang cùng origin vẫn tạo ra tác động lớn.

### 6.2. Phạm vi takeover phụ thuộc scope

Worker có scope / có thể kiểm soát nhiều trang hơn worker chỉ có scope /app/. Nếu một worker độc hại được đăng ký ở root, nó có thể ảnh hưởng các route quan trọng như đăng nhập, tài khoản, thanh toán hoặc API được gọi từ các trang trong scope.

Một scope rộng không tự cấp quyền server-side cho attacker. Backend vẫn phải xác thực và phân quyền request. Tuy vậy, worker có thể thay đổi những gì client gửi/nhận và tạo nội dung giả để lừa người dùng hoặc can thiệp luồng ứng dụng.

### 6.3. Rủi ro từ phiên bản và cache

Takeover nhanh có thể tạo ra các tổ hợp:

- Trang v1 nhưng worker v2.
- Trang v2 nhưng cache vẫn là schema v1.
- Worker mới xóa cache mà tab cũ vẫn cần.
- Response API đã đổi cấu trúc nhưng JavaScript cũ chưa reload.
- Service worker mới phục vụ asset không cùng release với HTML hiện tại.

Đây vừa là rủi ro availability vừa có thể thành rủi ro bảo mật nếu kiểm tra authorization hoặc nội dung bảo vệ bị lệch giữa client, worker và server.

## 7. Bảo vệ điểm đăng ký service worker

Đăng ký worker là một thao tác có ảnh hưởng lâu dài. Hãy coi scriptURL là một đầu vào bảo mật, không phải chuỗi URL thông thường.

### 7.1. Dùng script URL cố định do ứng dụng quản lý

~~~js
if ('serviceWorker' in navigator && window.isSecureContext) {
  navigator.serviceWorker.register('/sw.js', {
    scope: '/app/',
  }).catch((error) => {
    console.error('Service worker registration failed:', error);
  });
}
~~~

Không lấy script URL hoặc scope trực tiếp từ:

- Query parameter do người dùng kiểm soát.
- postMessage từ iframe hoặc cửa sổ không tin cậy.
- API response không được xác minh.
- Giá trị nhập trong form hoặc cấu hình có thể sửa bởi user.

Nếu cần chọn worker theo sản phẩm, dùng danh sách URL cố định trong code và kiểm tra giá trị lựa chọn với allowlist.

### 7.2. CSP worker-src

CSP directive worker-src giới hạn nguồn được phép cho Worker, SharedWorker và ServiceWorker script.

~~~http
Content-Security-Policy: default-src 'self'; script-src 'self'; worker-src 'self'; object-src 'none'; base-uri 'self'
~~~

Nếu worker-src không có, browser có thể fallback lần lượt sang child-src, script-src hoặc default-src. Nên khai báo worker-src tường minh để policy dễ kiểm tra.

worker-src 'self' ngăn đăng ký script worker từ origin ngoài danh sách. Tuy nhiên, nó không phân biệt file hợp lệ và file độc hại cùng origin. Nếu attacker đã sửa được /sw.js hoặc có endpoint cùng origin phục vụ script độc hại, allowlist self vẫn cho phép URL đó. Cần bảo vệ cả nguồn phát hành và quyền ghi file.

### 7.3. Trusted Types cho scriptURL

MDN mô tả tham số scriptURL của register() là injection sink. Khi ứng dụng thực thi Trusted Types với require-trusted-types-for 'script', hãy truyền TrustedScriptURL được tạo bởi policy có kiểm tra allowlist.

~~~http
Content-Security-Policy: require-trusted-types-for 'script'; trusted-types sw-registration
~~~

~~~js
const swPolicy = trustedTypes.createPolicy('sw-registration', {
  createScriptURL(input) {
    const url = new URL(input, location.origin);

    if (
      url.origin !== location.origin ||
      url.pathname !== '/sw.js' ||
      url.search !== '' ||
      url.hash !== ''
    ) {
      throw new TypeError('Service worker URL không nằm trong allowlist');
    }

    return url.href;
  },
});

navigator.serviceWorker.register(
  swPolicy.createScriptURL('/sw.js'),
  { scope: '/app/' },
);
~~~

Policy phải do ứng dụng kiểm soát và không được biến thành hàm “tin mọi chuỗi”. Trusted Types giúp kiểm soát dữ liệu đi vào sink; nó không sửa được trường hợp attacker đã thực thi mã tùy ý và có thể gọi API với URL được cho phép.

### 7.4. Bảo vệ artifact và endpoint cùng origin

- Chỉ pipeline phát hành được phép ghi file service worker.
- Không phục vụ file upload của người dùng như JavaScript trên origin ứng dụng.
- Tách nội dung do người dùng tải lên sang origin riêng không chia sẻ trust với ứng dụng.
- Bảo vệ token CI/CD, quyền ghi bucket/CDN và tài khoản quản trị hosting.
- Phục vụ worker bằng MIME type JavaScript hợp lệ.
- Kiểm tra redirect và response thực tế của URL script.
- Dùng HTTPS cho toàn bộ ứng dụng và tài nguyên quan trọng.
- Giữ scope nhỏ nhất có thể và tránh mở rộng bằng Service-Worker-Allowed nếu không cần.

## 8. Thiết kế cập nhật an toàn

### 8.1. Chuẩn bị tài nguyên trước khi takeover

Trong install event, tạo cache version mới và tải các asset cốt lõi. Dùng event.waitUntil() để browser chỉ đánh dấu cài đặt thành công khi các bước chuẩn bị hoàn tất.

~~~js
const CACHE_NAME = 'app-v2';
const CORE_ASSETS = [
  '/app/',
  '/app/index.html',
  '/app/app.js',
  '/app/styles.css',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(CORE_ASSETS);
    }),
  );
});
~~~

Nếu addAll() thất bại, promise bị reject và quá trình install không hoàn tất. Worker cũ tiếp tục phục vụ trang; điều này giúp tránh kích hoạt một worker mới chưa có đủ asset bắt buộc.

### 8.2. Chỉ dọn cache cũ sau khi worker mới active

Worker mới nên dùng tên cache version riêng. Khi activate, dọn các cache cũ thuộc ứng dụng sau khi worker cũ đã nhường quyền:

~~~js
const CACHE_NAME = 'app-v2';

self.addEventListener('activate', (event) => {
  event.waitUntil(
    (async () => {
      const names = await caches.keys();
      await Promise.all(
        names
          .filter((name) => name.startsWith('app-') && name !== CACHE_NAME)
          .map((name) => caches.delete(name)),
      );
      await clients.claim();
    })(),
  );
});
~~~

Không xóa cache v1 ngay trong install của v2. Worker v1 vẫn có thể đang kiểm soát các tab và cần cache cũ để xử lý request. Khi dùng skipWaiting(), cần đặc biệt kiểm tra tương thích giữa các tab cũ và cache mới.

### 8.3. Giữ tương thích giữa trang và worker

Một số chiến lược:

- API backend hỗ trợ song song request từ client v1 và v2 trong giai đoạn chuyển đổi.
- Worker mới tiếp tục xử lý cache key và response cũ trong một khoảng chuyển tiếp.
- Cache asset theo version hoặc content hash để tránh ghi đè asset đang được tab cũ dùng.
- Chỉ xóa cache cũ khi chắc chắn worker mới và các client còn lại không cần nó.
- Dùng schema migration theo hướng tương thích ngược; tránh đổi schema IndexedDB theo cách làm hỏng tab đang chạy.
- Với thao tác quan trọng, yêu cầu người dùng hoàn tất hoặc lưu trạng thái trước khi reload.

### 8.4. Dùng thông báo cập nhật có kiểm soát

Thay vì luôn gọi skipWaiting() ngay khi có bản mới:

1. Để worker mới ở waiting.
2. Trang phát hiện registration.waiting.
3. Hiển thị thông báo có bản cập nhật.
4. Người dùng chọn “Cập nhật”.
5. Trang gửi message tới waiting worker.
6. Worker gọi skipWaiting().
7. Khi controllerchange xảy ra, trang reload ở thời điểm phù hợp.

Ví dụ trang gửi message:

~~~js
const registration = await navigator.serviceWorker.getRegistration();

if (registration?.waiting) {
  registration.waiting.postMessage({
    type: 'SKIP_WAITING',
  });
}
~~~

Worker xử lý message:

~~~js
self.addEventListener('message', (event) => {
  if (event.data?.type === 'SKIP_WAITING') {
    self.skipWaiting();
  }
});
~~~

Trang có thể nghe controllerchange và chỉ reload sau khi người dùng chấp nhận bản cập nhật:

~~~js
let reloadAfterUpdate = false;

async function applyWaitingUpdate() {
  const registration = await navigator.serviceWorker.getRegistration();

  if (registration?.waiting) {
    reloadAfterUpdate = true;
    registration.waiting.postMessage({
      type: 'SKIP_WAITING',
    });
  }
}

navigator.serviceWorker.addEventListener('controllerchange', () => {
  if (reloadAfterUpdate) {
    reloadAfterUpdate = false;
    window.location.reload();
  }
});
~~~

Gọi applyWaitingUpdate() sau khi người dùng xác nhận cập nhật và ứng dụng đã lưu trạng thái cần thiết. Cờ reloadAfterUpdate giúp trang không reload chỉ vì controllerchange xảy ra trong lần cài đặt đầu tiên hoặc một thay đổi controller ngoài luồng cập nhật có chủ đích.

## 9. Phát hiện worker takeover bất thường

### 9.1. Kiểm tra controller hiện tại

~~~js
const controller = navigator.serviceWorker.controller;

console.log({
  controlled: Boolean(controller),
  scriptURL: controller?.scriptURL ?? null,
  state: controller?.state ?? null,
});
~~~

controller là worker hiện đang kiểm soát document. Nếu null, document hiện tại chưa được service worker kiểm soát.

### 9.2. Liệt kê registration

~~~js
const registrations = await navigator.serviceWorker.getRegistrations();

for (const registration of registrations) {
  console.log({
    scope: registration.scope,
    installing: registration.installing?.scriptURL ?? null,
    waiting: registration.waiting?.scriptURL ?? null,
    active: registration.active?.scriptURL ?? null,
    updateViaCache: registration.updateViaCache,
  });
}
~~~

Đối chiếu scope và scriptURL với danh sách worker đã được ứng dụng phê duyệt. Một registration lạ ở scope root có thể ảnh hưởng nhiều route hơn dự kiến.

### 9.3. Theo dõi update và controllerchange

~~~js
const registration = await navigator.serviceWorker.getRegistration();

registration?.addEventListener('updatefound', () => {
  const worker = registration.installing;

  worker?.addEventListener('statechange', () => {
    console.log('Worker state:', worker.state, worker.scriptURL);
  });
});

navigator.serviceWorker.addEventListener('controllerchange', () => {
  console.log(
    'Controller changed:',
    navigator.serviceWorker.controller?.scriptURL,
  );
});
~~~

controllerchange là tín hiệu hữu ích để phát hiện trang vừa được worker khác tiếp quản. Trong hệ thống production, ghi nhận version worker, scope, thời điểm update và release ứng dụng để hỗ trợ điều tra.

### 9.4. DevTools

Trong Chrome/Edge DevTools:

1. Mở Application.
2. Chọn Service Workers.
3. Kiểm tra script URL, scope, trạng thái activated/waiting và các tùy chọn update.
4. Mở Cache Storage để kiểm tra cache do ứng dụng tạo.
5. Mở Network, bật Preserve log và xem request có được xử lý bởi service worker hay không.
6. So sánh response header, response body và initiator khi có dấu hiệu nội dung bị thay đổi.

Tên menu và chi tiết hiển thị có thể khác giữa browser. Firefox có bảng Storage/Application tương ứng.

## 10. Xử lý khi nghi ngờ service worker bị chiếm quyền

Khi có dấu hiệu worker lạ, cần xử lý cả script nguồn, registration, cache và các client đang mở. Chỉ gọi unregister() không đảm bảo mọi tab đang mở lập tức ngừng dùng controller hiện tại.

Quy trình đề xuất:

1. **Khoanh vùng nguồn phát hành:** kiểm tra file worker trên origin/CDN, lịch sử deploy, tài khoản publish và quyền ghi static assets.
2. **Chặn đường ghi bị xâm phạm:** thu hồi token hoặc tài khoản bị lộ, khóa pipeline/endpoint upload liên quan và deploy artifact đã xác minh.
3. **Kiểm tra registration:** liệt kê scope, active, waiting, installing và scriptURL trên các browser tái hiện được sự cố.
4. **Phát hành worker sạch:** phục vụ script đã review tại URL cùng origin và đúng scope cần thiết.
5. **Chọn takeover phù hợp:** dùng skipWaiting() nếu cần thu hồi nhanh và worker mới tương thích; nếu không, hướng dẫn người dùng đóng tab/reload theo kế hoạch.
6. **Gỡ registration đáng ngờ:** gọi registration.unregister() hoặc dùng DevTools để unregister; kiểm tra lại sau khi các client liên quan được đóng và tải lại.
7. **Dọn cache có kiểm soát:** xóa cache do worker độc hại tạo sau khi xác định dữ liệu cần giữ và đảm bảo worker sạch đang phục vụ.
8. **Kiểm tra lại response:** xác nhận HTML, script, API và asset không còn bị worker cũ hoặc cache cũ thay đổi.
9. **Đánh giá dữ liệu:** nếu worker có thể đã chuyển tiếp response nhạy cảm ra ngoài, xử lý sự cố token/session và dữ liệu theo quy trình ứng dụng.
10. **Theo dõi tái xuất hiện:** kiểm tra registration và scriptURL sau reload, navigation mới và lần mở browser tiếp theo.

Không xóa toàn bộ cache hoặc unregister mọi worker một cách mù quáng nếu ứng dụng có nhiều registration hợp lệ. Xác định scope và cache prefix trước để tránh làm hỏng các tính năng không liên quan.

## 11. Thực hành: quan sát takeover bằng Node.js

Bài lab dùng **Node.js 18 trở lên**, không cần package ngoài. Browser cho phép service worker trên localhost như một secure context phục vụ phát triển.

Lab chạy một origin:

- http://localhost:3000: trang ứng dụng.
- /sw.js?version=1: worker v1.
- /sw.js?version=2: worker v2 chờ worker cũ nhường quyền.
- /sw.js?version=2&fast=1: worker v2 gọi skipWaiting() và clients.claim() để takeover nhanh.

Trang sẽ hiển thị registration state, controller scriptURL và response từ endpoint /sw-version. Khi worker kiểm soát trang, endpoint này được worker trả về phiên bản của nó thay vì response từ server.

### 11.1. Tạo file service-worker-takeover-lab.mjs

~~~js
import { createServer } from 'node:http';

const appHtml = [
  '<!doctype html>',
  '<html lang="vi"><head><meta charset="utf-8">',
  '<meta name="viewport" content="width=device-width, initial-scale=1">',
  '<title>Service worker takeover lab</title>',
  '<style>',
  'body{font:16px system-ui,sans-serif;max-width:850px;margin:32px auto;padding:0 16px}',
  'button{margin:4px;padding:8px 12px}pre{white-space:pre-wrap;background:#f2f2f2;padding:12px}',
  '</style></head><body>',
  '<h1>Service worker takeover</h1>',
  '<p>Đăng ký v1, cài v2 ở trạng thái waiting, rồi thử v2 fast takeover.</p>',
  '<button id="v1">Đăng ký worker v1</button>',
  '<button id="v2-wait">Cài v2 và chờ</button>',
  '<button id="v2-fast">Cài v2 fast takeover</button>',
  '<button id="inspect">Kiểm tra trạng thái</button>',
  '<button id="fetch-version">Gọi /sw-version</button>',
  '<h2>Registration</h2><pre id="registration">Chưa kiểm tra.</pre>',
  '<h2>Controller</h2><pre id="controller">Chưa kiểm tra.</pre>',
  '<h2>Response</h2><pre id="response">Chưa gọi endpoint.</pre>',
  '<script src="/app.js" defer></script>',
  '</body></html>',
].join('\n');

const appJs = [
  "const registrationOutput = document.querySelector('#registration');",
  "const controllerOutput = document.querySelector('#controller');",
  "const responseOutput = document.querySelector('#response');",
  'let currentRegistration = null;',
  '',
  'function workerInfo(worker) {',
  "  if (!worker) return '—';",
  "  return worker.state + ' | ' + worker.scriptURL;",
  '}',
  '',
  'function render() {',
  "  const controller = navigator.serviceWorker.controller;",
  '  controllerOutput.textContent = controller',
  "    ? workerInfo(controller)",
  "    : 'Trang hiện chưa có controller';",
  '  if (!currentRegistration) {',
  "    registrationOutput.textContent = 'Không tìm thấy registration trong scope hiện tại';",
  '    return;',
  '  }',
  '  registrationOutput.textContent = [',
  "    'scope: ' + currentRegistration.scope,",
  "    'installing: ' + workerInfo(currentRegistration.installing),",
  "    'waiting: ' + workerInfo(currentRegistration.waiting),",
  "    'active: ' + workerInfo(currentRegistration.active),",
  '  ].join("\\n");',
  '}',
  '',
  'function watchRegistration(registration) {',
  '  currentRegistration = registration;',
  "  registration.addEventListener('updatefound', () => {",
  '    const installing = registration.installing;',
  "    installing?.addEventListener('statechange', render);",
  '    render();',
  '  });',
  '  registration.installing?.addEventListener("statechange", render);',
  '  registration.waiting?.addEventListener("statechange", render);',
  '  registration.active?.addEventListener("statechange", render);',
  '  render();',
  '}',
  '',
  'async function registerVersion(version, fast) {',
  '  const scriptURL = "/sw.js?version=" + version + (fast ? "&fast=1" : "");',
  '  const registration = await navigator.serviceWorker.register(scriptURL, {',
  "    scope: '/',",
  '  });',
  '  watchRegistration(registration);',
  '  await inspect();',
  '}',
  '',
  'async function inspect() {',
  "  currentRegistration = await navigator.serviceWorker.getRegistration('/');",
  '  render();',
  '}',
  '',
  'async function fetchVersion() {',
  "  const response = await fetch('/sw-version', { cache: 'no-store' });",
  '  responseOutput.textContent = await response.text();',
  '}',
  '',
  "document.querySelector('#v1').addEventListener('click', () => registerVersion('1', false).catch(showError));",
  "document.querySelector('#v2-wait').addEventListener('click', () => registerVersion('2', false).catch(showError));",
  "document.querySelector('#v2-fast').addEventListener('click', () => registerVersion('2', true).catch(showError));",
  "document.querySelector('#inspect').addEventListener('click', () => inspect().catch(showError));",
  "document.querySelector('#fetch-version').addEventListener('click', () => fetchVersion().catch(showError));",
  '',
  'function showError(error) {',
  "  responseOutput.textContent = 'Lỗi: ' + error.message;",
  '}',
  '',
  "navigator.serviceWorker.addEventListener('controllerchange', () => {",
  '  render();',
  '  fetchVersion().catch(showError);',
  '});',
  '',
  "navigator.serviceWorker.getRegistration('/').then((registration) => {",
  '  if (registration) watchRegistration(registration);',
  '  else render();',
  '});',
].join('\n');

function serviceWorkerSource(version, fast) {
  return [
    'const VERSION = ' + JSON.stringify(version) + ';',
    'const FAST_TAKEOVER = ' + String(fast) + ';',
    '',
    'self.addEventListener("install", (event) => {',
    '  if (FAST_TAKEOVER) {',
    '    event.waitUntil(self.skipWaiting());',
    '  }',
    '});',
    '',
    'self.addEventListener("activate", (event) => {',
    '  event.waitUntil(self.clients.claim());',
    '});',
    '',
    'self.addEventListener("fetch", (event) => {',
    '  const url = new URL(event.request.url);',
    '  if (url.origin === self.location.origin && url.pathname === "/sw-version") {',
    '    event.respondWith(new Response("Response từ service worker " + VERSION, {',
    '      headers: {',
    '        "Content-Type": "text/plain; charset=utf-8",',
    '        "Cache-Control": "no-store",',
    '      },',
    '    }));',
    '  }',
    '});',
  ].join('\n');
}

createServer((req, res) => {
  const url = new URL(req.url, 'http://localhost:3000');

  if (url.pathname === '/') {
    res.writeHead(200, {
      'Content-Type': 'text/html; charset=utf-8',
      'Cache-Control': 'no-store',
      'Content-Security-Policy':
        "default-src 'self'; script-src 'self'; style-src 'unsafe-inline'; worker-src 'self'; object-src 'none'; base-uri 'self'",
    });
    res.end(appHtml);
    return;
  }

  if (url.pathname === '/app.js') {
    res.writeHead(200, {
      'Content-Type': 'text/javascript; charset=utf-8',
      'Cache-Control': 'no-store',
    });
    res.end(appJs);
    return;
  }

  if (url.pathname === '/sw.js') {
    const version = url.searchParams.get('version') || '1';
    const fast = url.searchParams.get('fast') === '1';
    res.writeHead(200, {
      'Content-Type': 'text/javascript; charset=utf-8',
      'Cache-Control': 'no-cache',
    });
    res.end(serviceWorkerSource(version, fast));
    return;
  }

  if (url.pathname === '/sw-version') {
    res.writeHead(200, {
      'Content-Type': 'text/plain; charset=utf-8',
      'Cache-Control': 'no-store',
    });
    res.end('Response trực tiếp từ Node.js server; trang chưa được service worker kiểm soát.');
    return;
  }

  res.writeHead(404, { 'Content-Type': 'text/plain; charset=utf-8' });
  res.end('Not found');
}).listen(3000, () => {
  console.log('Open http://localhost:3000');
});
~~~

### 11.2. Chạy lab

~~~bash
node service-worker-takeover-lab.mjs
~~~

Mở http://localhost:3000 trong một browser tab. Nếu trước đó đã chạy lab ở cùng origin, hãy kiểm tra và gỡ registration cũ trong DevTools trước khi bắt đầu.

### 11.3. Đăng ký v1

1. Nhấn **Đăng ký worker v1**.
2. Browser tải /sw.js?version=1, chạy install và activate.
3. Worker gọi clients.claim(), nên trang hiện tại có thể được kiểm soát ngay.
4. Nhấn **Gọi /sw-version**; response sẽ ghi phiên bản worker v1.
5. Mở một tab thứ hai cùng origin để quan sát một client khác cũng được worker kiểm soát.

### 11.4. Cài v2 ở trạng thái waiting

1. Giữ các tab đang được v1 kiểm soát mở.
2. Nhấn **Cài v2 và chờ**.
3. Browser đăng ký script v2 cho cùng scope /.
4. v2 cài đặt nhưng không gọi skipWaiting(), nên nó ở trạng thái waiting trong khi v1 còn kiểm soát client.
5. Phần Registration hiển thị active v1 và waiting v2.

Đóng tất cả tab đang được v1 kiểm soát. Khi client cũ đã đóng và event đang xử lý hoàn tất, v2 có thể activate. Mở lại trang và nhấn **Gọi /sw-version** để quan sát response từ v2.

### 11.5. Thử fast takeover

1. Đăng ký lại v1 nếu cần một worker active làm mốc.
2. Giữ trang đang được v1 kiểm soát mở.
3. Nhấn **Cài v2 fast takeover**.
4. Script v2 có tham số fast=1 nên gọi skipWaiting() trong install.
5. Sau activate, v2 gọi clients.claim().
6. Trang nhận controllerchange; phần Controller đổi sang URL script v2.
7. Nhấn **Gọi /sw-version** để xác nhận response đã do v2 xử lý.

### 11.6. Kiểm tra trong DevTools

- Application → Service Workers: xem script URL, scope, trạng thái active/waiting.
- Network: xem request /sw-version và xác định response có qua service worker hay không.
- Console: quan sát lỗi registration hoặc lỗi lifecycle.
- Application → Cache Storage: lab này không tạo cache, nhưng mục này hữu ích khi kiểm tra ứng dụng thực tế.
- Mở thêm tab cùng origin để quan sát việc worker mới claim nhiều client trong scope.

### 11.7. Giới hạn lab

- Lab dùng localhost và một origin, không mô phỏng attacker chiếm hosting hoặc CDN.
- Worker chỉ thay response của endpoint /sw-version; không sửa HTML hoặc thu thập dữ liệu.
- Browser có thể giữ registration từ lần chạy trước; cần kiểm tra scope và unregister worker cũ trước khi lặp lại.
- Trạng thái waiting phụ thuộc việc còn client nào do worker cũ kiểm soát.
- Lab không thay thế kiểm thử tương thích cache, IndexedDB, API backend hoặc quy trình phát hành production.

## 12. Những lỗi thường gặp khi takeover

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Luôn gọi skipWaiting() ngay khi install | Trang cũ có thể bị worker mới tiếp quản giữa phiên | Chỉ bật fast takeover khi tương thích hoặc có luồng reload rõ ràng |
| Nghĩ skipWaiting() tự đổi controller của mọi tab | Một số trang vẫn giữ controller cũ nếu không có clients.claim() hoặc reload | Hiểu riêng bước activate và claim |
| Nghĩ clients.claim() kích hoạt worker waiting | Worker chưa active không thể claim client | Đợi activation hoặc dùng skipWaiting() có chủ đích |
| Xóa cache cũ trong install | Worker cũ có thể đang cần cache đó | Tạo cache version mới và dọn cache trong activate |
| Đặt scope root mà không cần thiết | Worker có thể ảnh hưởng nhiều route | Giới hạn scope theo khu vực ứng dụng |
| Mở rộng scope bằng Service-Worker-Allowed tùy tiện | Tăng blast radius khi script bị xâm phạm | Chỉ mở rộng khi có yêu cầu kiến trúc đã review |
| Lấy scriptURL từ input người dùng | Có thể tạo đường đăng ký worker ngoài dự kiến | Dùng URL cố định, allowlist và Trusted Types |
| Chỉ dùng worker-src 'self' để chống mọi takeover | Script độc hại cùng origin vẫn có thể khớp self | Bảo vệ endpoint, artifact, upload và quyền deploy |
| Chỉ unregister mà không kiểm tra client/cache | Tab đang mở hoặc cache cũ có thể tiếp tục gây nhầm lẫn | Đóng/reload client, xác minh controller và dọn cache có kiểm soát |
| Không theo dõi controllerchange | Trang không biết worker mới đã nhận quyền điều khiển | Theo dõi controller và version trong telemetry |

## 13. Checklist bảo mật service worker takeover

1. **Kiểm kê registration:** ghi nhận scriptURL, scope, version và owner của từng worker.
2. **Giới hạn scope:** chọn phạm vi nhỏ nhất; kiểm tra mọi header Service-Worker-Allowed.
3. **Giữ scriptURL cố định:** không lấy từ input, query hoặc message không tin cậy.
4. **Bảo vệ worker-src:** khai báo CSP worker-src tường minh.
5. **Dùng Trusted Types:** kiểm soát TrustedScriptURL khi ứng dụng bật enforcement.
6. **Bảo vệ origin:** không phục vụ user-uploaded JavaScript cùng origin ứng dụng.
7. **Bảo vệ pipeline:** giới hạn quyền ghi artifact, CDN, token deploy và tài khoản maintainer.
8. **Quản lý update:** theo dõi updatefound, installing, waiting và active.
9. **Dùng skipWaiting có điều kiện:** xác minh tương thích trước khi chuyển quyền khi tab cũ còn mở.
10. **Dùng clients.claim có chủ đích:** biết rõ các client trong scope sẽ đổi controller.
11. **Version hóa cache:** không ghi đè cache cũ trước khi worker cũ ngừng dùng.
12. **Tương thích backend:** hỗ trợ request từ client cũ trong giai đoạn chuyển đổi.
13. **Thông báo người dùng:** cho phép hoàn tất thao tác trước khi reload nếu cần.
14. **Theo dõi runtime:** ghi nhận controller scriptURL, scope, update và lỗi fetch.
15. **Chuẩn bị incident response:** biết cách kiểm tra registration, deploy worker sạch, unregister và dọn cache.

## 14. Những nhầm lẫn cần tránh

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| “Takeover luôn là tấn công.” | Đây là một bước lifecycle bình thường; rủi ro phụ thuộc nguồn script và cách chuyển quyền. |
| “skipWaiting() và clients.claim() làm cùng một việc.” | skipWaiting() thúc đẩy activation; clients.claim() nhận quyền điều khiển client sau activation. |
| “Worker active nghĩa mọi tab hiện tại đã đổi controller.” | Tab đang mở có thể cần clients.claim() hoặc navigation/reload. |
| “Service worker chạy liên tục sau khi đăng ký.” | Browser có thể dừng worker khi idle và khởi động lại khi có event; registration vẫn tồn tại. |
| “Service worker có thể đọc DOM và localStorage.” | Worker không có DOM hoặc Web Storage; nó có thể trung gian fetch và dùng storage API riêng như Cache Storage/IndexedDB. |
| “XSS luôn cho phép đăng ký script worker tùy ý.” | Script URL phải cùng origin và trong secure context; attacker cần endpoint cùng origin phục vụ script mà họ kiểm soát. |
| “worker-src 'self' chặn mọi script độc hại.” | Nó hạn chế nguồn theo origin; file độc hại cùng origin vẫn có thể khớp self. |
| “Scope chỉ giới hạn URL đích của fetch.” | Scope xác định document/client được kiểm soát; request do client đó tạo có thể được worker xử lý. |
| “Unregister xong thì mọi tab lập tức không còn controller.” | Cần kiểm tra client đang mở, reload/đóng tab và xác minh lại sau khi thu hồi registration. |
| “Cập nhật nhanh luôn tốt hơn chờ.” | Fast takeover có thể làm trang cũ và worker mới không tương thích. |

## 15. Câu hỏi tự đánh giá

**Câu 1.** Service worker takeover là gì?

**Gợi ý trả lời:** Là việc worker mới trở thành active và/hoặc nhận quyền điều khiển các client trong scope thay cho worker trước đó.

**Câu 2.** Worker mới thường ở trạng thái nào khi worker cũ vẫn kiểm soát các tab?

**Gợi ý trả lời:** Worker mới ở trạng thái installed/waiting sau khi install thành công.

**Câu 3.** skipWaiting() làm gì?

**Gợi ý trả lời:** Cho phép worker waiting tiến tới active dù client của worker cũ vẫn đang mở.

**Câu 4.** clients.claim() làm gì?

**Gợi ý trả lời:** Active worker đặt mình làm controller cho các client trong scope và các trang bị chuyển quyền nhận controllerchange.

**Câu 5.** Vì sao fast takeover có thể gây lỗi?

**Gợi ý trả lời:** Trang cũ có thể tiếp tục chạy JavaScript v1 nhưng request đã do worker v2 xử lý, tạo mismatch về API, cache hoặc schema dữ liệu.

**Câu 6.** Scope mặc định được xác định thế nào?

**Gợi ý trả lời:** Là thư mục chứa script service worker; muốn mở rộng vượt thư mục này cần header Service-Worker-Allowed phù hợp.

**Câu 7.** Vì sao XSS không tự động cho phép đăng ký worker từ bất kỳ URL nào?

**Gợi ý trả lời:** Script URL và scope phải cùng origin với trang đăng ký và service worker cần secure context; attacker cần một script endpoint cùng origin phù hợp.

**Câu 8.** worker-src 'self' bảo vệ điều gì và giới hạn ra sao?

**Gợi ý trả lời:** Nó giới hạn nguồn script worker theo origin hiện tại, nhưng không phân biệt file hợp lệ với file độc hại được phục vụ từ cùng origin.

**Câu 9.** Khi nghi ngờ worker độc hại, vì sao chỉ unregister chưa đủ?

**Gợi ý trả lời:** Cần kiểm tra client đang mở, controller, script nguồn, cache và dữ liệu có thể đã bị ảnh hưởng; các tab hiện tại có thể cần đóng hoặc reload.

## Tài liệu tham khảo

- W3C — [Service Workers](https://www.w3.org/TR/service-workers/), lifecycle, skipWaiting() và clients.claim().
- MDN — [Using Service Workers](https://developer.mozilla.org/en-US/docs/Web/API/Service_Worker_API/Using_Service_Workers).
- MDN — [ServiceWorkerGlobalScope.skipWaiting()](https://developer.mozilla.org/en-US/docs/Web/API/ServiceWorkerGlobalScope/skipWaiting).
- MDN — [Clients.claim()](https://developer.mozilla.org/en-US/docs/Web/API/Clients/claim).
- MDN — [ServiceWorkerContainer.register()](https://developer.mozilla.org/en-US/docs/Web/API/ServiceWorkerContainer/register).
- MDN — [Service-Worker-Allowed header](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Service-Worker-Allowed).
- MDN — [CSP worker-src](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Security-Policy/worker-src).
- MDN — [ServiceWorkerRegistration.unregister()](https://developer.mozilla.org/en-US/docs/Web/API/ServiceWorkerRegistration/unregister).
