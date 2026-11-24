# Thiết lập cookie an toàn

Cookie là cơ chế browser lưu một lượng dữ liệu nhỏ và tự gửi lại trong những request phù hợp với phạm vi cookie. Ứng dụng web thường dùng cookie để duy trì session đăng nhập, lưu trạng thái cần thiết hoặc hỗ trợ một luồng xác thực. Vì browser tự quản lý việc gửi cookie, cấu hình sai có thể tạo điều kiện cho đánh cắp session, CSRF, cookie injection hoặc rò rỉ dữ liệu qua các subdomain và ngữ cảnh cross-site.

Bài thực hành này xây dựng một cookie session an toàn cho ứng dụng web, kiểm tra các thuộc tính bảo vệ trên browser và xác minh logout/CSRF. Trọng tâm là hiểu mỗi thuộc tính bảo vệ điều gì, giới hạn của nó ở đâu và cách kiểm chứng bằng DevTools, request thực tế và test tự động.

## Bối cảnh thực hành

Giả sử có ứng dụng quản lý tài khoản tại `https://app.example.test`. Người dùng đăng nhập bằng username/password; server tạo session và browser lưu session identifier trong cookie. API thay đổi dữ liệu sử dụng session cookie để xác định người gọi.

Mục tiêu của bài thực hành:

1. Tạo session identifier ngẫu nhiên, khó đoán và được lưu ở server.
2. Gửi cookie với `Secure`, `HttpOnly`, `SameSite` và phạm vi host phù hợp.
3. Xoay vòng session identifier sau đăng nhập và thay đổi đặc quyền.
4. Thu hồi session ở server khi logout và xóa cookie đúng phạm vi.
5. Bảo vệ request thay đổi trạng thái trước CSRF.
6. Kiểm tra hành vi trên browser, gồm HTTPS, subdomain, top-level navigation, iframe và cross-site request.

Môi trường nên dùng domain thử nghiệm và HTTPS. Có thể dùng chứng thư local được tin cậy hoặc môi trường staging. Không thực hiện bài tập bằng session sản xuất, tài khoản thật hoặc cookie của người khác.

## 1. Hiểu cookie và phạm vi gửi

Cookie được server tạo qua response header `Set-Cookie`. Browser lưu cookie theo các thuộc tính được chỉ định rồi tự đính kèm nó vào request phù hợp.

Ví dụ:

~~~http
Set-Cookie: session=opaque-value; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Khi request phù hợp được gửi, browser có thể thêm header:

~~~http
Cookie: session=opaque-value
~~~

`Set-Cookie` là response header; `Cookie` là request header. JavaScript trong page không được đọc trực tiếp `Set-Cookie` qua Fetch API vì đây là forbidden response header. JavaScript cũng không thể đọc cookie có `HttpOnly` bằng `document.cookie`.

Nếu response cần đặt nhiều cookie, server phải gửi nhiều header `Set-Cookie` riêng. Không gộp chúng thành một chuỗi phân tách bằng dấu phẩy vì thuộc tính `Expires` cũng có dấu phẩy và có thể làm browser parse sai.

### Host-only và Domain cookie

Nếu `Set-Cookie` không có thuộc tính `Domain`, cookie là host-only: browser chỉ gửi cookie đến đúng host đã đặt nó. Ví dụ, cookie được đặt bởi `app.example.test` sẽ không tự động gửi đến `api.example.test`.

Nếu khai báo:

~~~http
Set-Cookie: session=opaque-value; Domain=example.test; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

cookie có thể được gửi đến `example.test` và các subdomain phù hợp như `app.example.test` hoặc `api.example.test`. Điều này mở rộng phạm vi nhận cookie. Một subdomain yếu hoặc bị chiếm quyền có thể làm tăng rủi ro cookie injection, session confusion hoặc lộ cookie.

Với cookie session của ứng dụng, nên bỏ `Domain` để giữ phạm vi host-only trừ khi kiến trúc thực sự cần chia sẻ cookie giữa nhiều subdomain. Dấu chấm đứng đầu trong `Domain=.example.test` không tạo khác biệt đáng kể trong cách browser hiện đại xử lý domain cookie.

### Path

`Path` giới hạn những đường dẫn request mà browser gửi cookie đến. Ví dụ `Path=/account` giới hạn cookie vào đường dẫn phù hợp dưới `/account`. Tuy nhiên, `Path` không phải ranh giới bảo mật giữa các ứng dụng cùng host: các ứng dụng có thể có cách đọc hoặc gây request khác nhau, và không nên dùng Path để thay thế việc tách host hoặc kiểm soát quyền.

Cookie có prefix `__Host-` yêu cầu `Path=/`, nên phù hợp với cookie session cần phạm vi host-only rõ ràng.

## 2. Chọn thuộc tính bảo mật

| Thuộc tính | Tác dụng | Lưu ý khi cấu hình |
|---|---|---|
| `Secure` | Browser chỉ gửi cookie qua kết nối bảo mật HTTPS | Production phải dùng HTTPS; cần kiểm tra TLS termination và cấu hình proxy |
| `HttpOnly` | JavaScript không đọc được cookie qua `document.cookie` | Không ngăn XSS thực hiện request trong session của người dùng |
| `SameSite=Strict` | Hạn chế gửi cookie trong ngữ cảnh cross-site | Có thể làm gián đoạn luồng quay về từ identity provider hoặc website ngoài |
| `SameSite=Lax` | Cho phép một số điều hướng top-level an toàn từ site khác, hạn chế nhiều request cross-site khác | Thường phù hợp với session web thông thường; vẫn cần CSRF token và kiểm tra request |
| `SameSite=None` | Cho phép cookie tham gia ngữ cảnh cross-site theo quy tắc SameSite | Phải đi cùng `Secure`; browser vẫn có thể chặn third-party cookie theo chính sách riêng tư |
| `Domain` | Mở rộng cookie đến host và subdomain phù hợp | Tránh đặt nếu không cần chia sẻ giữa subdomain |
| `Path` | Giới hạn URL path gửi cookie | Không phải ranh giới bảo mật giữa ứng dụng cùng host |
| `Max-Age` / `Expires` | Đặt thời gian tồn tại ở browser | Server session phải có TTL và khả năng thu hồi tương ứng |
| `Partitioned` | Lưu cookie theo phân vùng top-level site trong browser hỗ trợ CHIPS | Cần `Secure`; kiểm tra kỹ ngữ cảnh nhúng và hỗ trợ browser |

### Secure

`Secure` yêu cầu browser chỉ gửi cookie qua kết nối bảo mật. Thuộc tính này không tự chuyển HTTP sang HTTPS và không thay thế HSTS. Nếu ứng dụng còn endpoint HTTP, cần redirect hợp lý và triển khai HSTS sau khi xác minh toàn bộ subdomain có thể phục vụ HTTPS.

### HttpOnly

`HttpOnly` giảm nguy cơ JavaScript đọc trực tiếp session cookie. Nếu page có XSS, script độc hại vẫn có thể gửi request bằng cookie mà browser tự đính kèm và thực hiện hành động trong session. Vì vậy, `HttpOnly` cần đi cùng phòng chống XSS, CSRF và authorization ở server.

### SameSite

`SameSite` kiểm soát việc gửi cookie trong ngữ cảnh same-site và cross-site. Site không đồng nghĩa với origin: `https://app.example.test` và `https://api.example.test` là hai origin khác nhau nhưng thường được xem là cùng site nếu cùng scheme và registrable domain.

- `Strict`: cookie chỉ được gửi trong ngữ cảnh same-site. Mức hạn chế cao nhưng có thể làm mất session trong lần điều hướng trở về từ website ngoài.
- `Lax`: cookie được gửi trong ngữ cảnh same-site và một số điều hướng top-level an toàn từ site khác, thường là phương thức an toàn như GET. Nó hạn chế nhiều request cross-site dạng subresource hoặc form POST.
- `None`: cho phép cookie trong ngữ cảnh cross-site theo quy tắc SameSite; phải có `Secure`. Chính sách chặn third-party cookie hoặc partitioning của browser vẫn có thể ảnh hưởng.

Không dựa vào SameSite như lớp CSRF duy nhất. Một subdomain bị chiếm quyền có thể cùng site với ứng dụng nhưng khác origin. Nếu endpoint nhận cookie và không kiểm tra CSRF, request phát sinh từ subdomain đó có thể vẫn là rủi ro.

## 3. Chọn prefix cho cookie session

Browser hiện đại hỗ trợ các prefix giúp áp đặt một số quy tắc khi chấp nhận cookie:

- `__Secure-`: cookie phải được đặt từ secure origin và có thuộc tính `Secure`.
- `__Host-`: cookie phải được đặt từ secure origin, có `Secure`, không có `Domain` và phải có `Path=/`.

Với session cookie của ứng dụng tại `app.example.test`, chọn tên `__Host-session`. Ví dụ:

~~~http
Set-Cookie: __Host-session=RANDOM_OPAQUE_SESSION_ID; Path=/; Max-Age=1800; Secure; HttpOnly; SameSite=Lax
~~~

Cookie này có các đặc điểm:

- Chỉ được gửi đến host đã đặt cookie vì không có `Domain`.
- Chỉ được gửi qua HTTPS.
- JavaScript không đọc được giá trị vì có `HttpOnly`.
- Browser áp dụng quy tắc Lax cho ngữ cảnh cross-site.
- Thời hạn ở browser là 30 phút kể từ lúc đặt hoặc cập nhật cookie.
- Prefix `__Host-` giúp browser hỗ trợ prefix từ chối cookie nếu có `Domain` hoặc `Path` khác `/`.

Khi cùng xuất hiện, `Max-Age` có ưu tiên hơn `Expires`. Nên đặt TTL session ở server bằng hoặc ngắn hơn thời hạn cookie; cookie còn ở browser không có nghĩa session server vẫn hợp lệ. Cookie session không có `Expires`/`Max-Age` cũng không được đảm bảo biến mất khi browser đóng vì tính năng khôi phục phiên có thể giữ lại trạng thái.

Không dùng prefix như bằng chứng duy nhất. Server vẫn phải đặt đúng thuộc tính, xác minh cấu hình và kiểm tra browser mục tiêu. Với browser cũ không thực thi prefix, các thuộc tính `Secure`, `Path` và việc bỏ `Domain` vẫn phải được cấu hình trực tiếp.

## 4. Tạo session an toàn ở server

Cookie session nên chứa một identifier ngẫu nhiên, không chứa role, quyền hoặc dữ liệu cá nhân có thể được client tự diễn giải. Dữ liệu session và trạng thái đăng nhập nên được lưu ở server hoặc session store có khả năng thu hồi.

Một cấu hình minh họa với Express và `express-session`:

~~~javascript
import session from 'express-session';

app.use(session({
  name: '__Host-session',
  secret: process.env.SESSION_SECRET,
  store: sharedSessionStore,
  resave: false,
  saveUninitialized: false,
  cookie: {
    path: '/',
    secure: true,
    httpOnly: true,
    sameSite: 'lax',
    maxAge: 30 * 60 * 1000
  }
}));
~~~

`sharedSessionStore` là session store do ứng dụng cung cấp; không dùng MemoryStore mặc định cho production. Không khai báo `domain` để cookie giữ host-only. `SESSION_SECRET` phải là secret ngẫu nhiên, được quản lý qua secret manager và có quy trình rotation. Trong production, cấu hình TLS và proxy tin cậy đúng cách nếu HTTPS kết thúc ở reverse proxy; không tin `X-Forwarded-Proto` từ mọi client.

### Xoay vòng session sau đăng nhập

Sau khi xác thực username/password thành công, tạo session identifier mới để ngăn session fixation. Với `express-session`, có thể regenerate session trước khi lưu danh tính:

~~~javascript
app.post('/login', async (req, res, next) => {
  const user = await authenticateCredentials(req.body);
  if (!user) return res.sendStatus(401);

  req.session.regenerate((error) => {
    if (error) return next(error);

    req.session.userId = user.id;
    req.session.authenticatedAt = Date.now();

    req.session.save((saveError) => {
      if (saveError) return next(saveError);
      return res.sendStatus(204);
    });
  });
});
~~~

Đây là ví dụ rút gọn; ứng dụng cần validate body, giới hạn thử mật khẩu, xử lý lỗi và bảo vệ CSRF phù hợp. Regenerate tạo session ID mới; session cũ không được tiếp tục có quyền đã xác thực. Cũng nên xem xét xoay vòng session sau thay đổi đặc quyền hoặc bước xác thực tăng cường.

Không tự tạo session ID bằng timestamp, số tăng dần, username hoặc `Math.random()`. Dùng session framework đã được kiểm tra hoặc bộ sinh số ngẫu nhiên mật mã, với độ dài và entropy phù hợp.

## 5. Logout và thu hồi cookie

Xóa cookie ở browser là chưa đủ. Server phải vô hiệu hóa session identifier tương ứng trong session store để cookie cũ không thể tiếp tục sử dụng.

Ví dụ:

~~~javascript
app.post('/logout', requireAuthenticatedUser, (req, res, next) => {
  req.session.destroy((error) => {
    if (error) return next(error);

    res.clearCookie('__Host-session', {
      path: '/',
      secure: true,
      httpOnly: true,
      sameSite: 'lax'
    });

    return res.sendStatus(204);
  });
});
~~~

Tùy phiên bản và cấu hình middleware, có thể dùng cơ chế destroy/regenerate tương ứng của session framework. Việc xóa cookie phải khớp tên, host/domain và path đã dùng khi tạo cookie. Với `__Host-session`, giữ `Path=/` và không thêm `Domain` khi xóa.

Sau logout, kiểm thử cả hai điều kiện: browser không còn gửi cookie session và server từ chối session ID cũ nếu client cố phát lại. Response logout nên có `Cache-Control: no-store` khi phù hợp để tránh lưu response nhạy cảm trong cache dùng chung.

## 6. Phòng CSRF cho request dùng cookie

Browser có thể tự đính kèm cookie vào request. Một website khác có thể tìm cách khiến browser gửi request đến ứng dụng đang đăng nhập. SameSite giảm một số ngữ cảnh gửi cookie, nhưng không thay thế CSRF token và kiểm tra ở server.

Với request thay đổi trạng thái như POST, PUT, PATCH hoặc DELETE, có thể kết hợp:

1. CSRF token gắn với session (synchronizer token) hoặc cơ chế tương đương đã được đánh giá.
2. Kiểm tra `Origin` khớp chính xác origin ứng dụng đối với request browser phù hợp.
3. Dùng Fetch Metadata như `Sec-Fetch-Site` làm tín hiệu bổ sung để từ chối request cross-site ngoài dự kiến.
4. Chọn `SameSite=Lax` hoặc `Strict` theo luồng ứng dụng.
5. Không thực hiện thay đổi trạng thái bằng GET.

Ví dụ middleware khái niệm:

~~~javascript
const APP_ORIGIN = 'https://app.example.test';
const SAFE_METHODS = new Set(['GET', 'HEAD', 'OPTIONS']);

function protectStateChange(req, res, next) {
  if (SAFE_METHODS.has(req.method)) return next();

  if (req.get('Origin') !== APP_ORIGIN) {
    return res.sendStatus(403);
  }

  const token = req.body?.csrfToken;
  if (!verifyCsrfTokenForSession(token, req.session)) {
    return res.sendStatus(403);
  }

  const fetchSite = req.get('Sec-Fetch-Site');
  if (fetchSite === 'cross-site') {
    return res.sendStatus(403);
  }

  return next();
}
~~~

`verifyCsrfTokenForSession` là hàm ứng dụng cần triển khai: token phải khó đoán, gắn với session, được so sánh an toàn và không được chấp nhận lại ngoài chính sách. Đây là ví dụ minh họa; cần xử lý rõ trường hợp header `Origin` vắng mặt theo loại client và hợp đồng API. Không bỏ qua CSRF token chỉ vì `Sec-Fetch-Site` không tồn tại trên một browser cũ.

Không đặt CSRF token trong URL vì URL có thể xuất hiện trong history, log, referrer hoặc hệ thống phân tích. Với ứng dụng dùng cookie, mọi endpoint thay đổi trạng thái cần được đánh giá CSRF, kể cả API được gọi bằng JavaScript.

## 7. Luồng cross-origin và subdomain

Cookie, SameSite, CORS và Fetch credentials giải quyết những vấn đề khác nhau. Ví dụ `https://app.example.test` gọi `https://api.example.test`:

- Hai địa chỉ là cross-origin vì host khác nhau.
- Chúng thường là same-site nếu cùng scheme và registrable domain.
- Cookie host-only của `api.example.test` chỉ được gửi đến API host, không gửi đến `app.example.test`.
- Với Fetch, request cross-origin cần `credentials: 'include'` nếu muốn browser đính kèm cookie phù hợp.
- Server API cần CORS cho đúng origin, ví dụ `Access-Control-Allow-Origin: https://app.example.test`, `Access-Control-Allow-Credentials: true` và `Vary: Origin`.
- CORS không thay thế authorization hoặc CSRF protection ở API.

Ví dụ request:

~~~javascript
const response = await fetch('https://api.example.test/account', {
  method: 'GET',
  credentials: 'include'
});
~~~

Không dùng `Access-Control-Allow-Origin: *` cùng credentials. Nếu API chỉ cần được gọi từ một frontend, allowlist chính xác origin và kiểm tra quyền của session trên server.

### Luồng đăng nhập qua identity provider

`SameSite=Strict` có thể làm cookie session không được gửi trong lần quay lại từ một website bên ngoài. `Lax` thường phù hợp hơn với callback OAuth/OIDC qua top-level GET navigation. Nếu dùng `response_mode=form_post` hoặc một luồng cross-site POST, cookie Lax có thể không được gửi; cần thiết kế cookie giao dịch ngắn hạn và kiểm tra `state`/nonce theo giao thức, thay vì hạ toàn bộ session cookie xuống cấu hình rộng mà không đánh giá.

Nếu thật sự cần cookie trong iframe cross-site, có thể cần `SameSite=None; Secure`, nhưng browser có thể chặn third-party cookie. Hãy xem xét kiến trúc first-party/BFF hoặc cơ chế partitioned storage thay vì giả định mọi browser đều cho phép cookie third-party.

## 8. Cookie partitioning và CHIPS

Cookie có thuộc tính `Partitioned` được lưu theo phân vùng top-level site trong browser hỗ trợ CHIPS. Điều này hữu ích cho một số dịch vụ nhúng cần trạng thái riêng theo từng website cha, chẳng hạn widget hỗ trợ khách hàng.

Ví dụ cấu hình cho một cookie dùng trong ngữ cảnh nhúng cross-site:

~~~http
Set-Cookie: __Secure-widget-session=opaque-value; Path=/; Max-Age=900; Secure; HttpOnly; SameSite=None; Partitioned
~~~

`Partitioned` yêu cầu `Secure`. `SameSite=None` cho phép cookie tham gia ngữ cảnh cross-site theo quy tắc SameSite; browser vẫn áp dụng chính sách partitioning và quyền riêng tư của nó. Cookie partitioned không phải cách chia sẻ session đăng nhập chính giữa nhiều website và không thay thế kiểm tra quyền ở server.

Chỉ dùng CHIPS khi chức năng nhúng có yêu cầu rõ. Kiểm tra browser hỗ trợ, cách xóa partitioned cookie, hành vi khi người dùng mở cùng widget từ hai top-level site và trường hợp browser chặn cookie third-party hoàn toàn.

## 9. Kiểm tra cookie bằng DevTools

Trong Chrome hoặc Edge, mở DevTools:

1. Chọn **Application** → **Storage** → **Cookies** và chọn origin của ứng dụng.
2. Kiểm tra tên cookie, Domain, Path, Expires/Max-Age, Secure, HttpOnly, SameSite và Partitioned nếu có.
3. Chọn **Network**, thực hiện đăng nhập và mở response của request login.
4. Kiểm tra `Set-Cookie` trong response headers. Nếu browser từ chối cookie, xem cảnh báo hoặc blocked reason trong DevTools.
5. Mở request tiếp theo và kiểm tra header `Cookie` có session ID phù hợp.
6. Chạy `document.cookie` trong Console và xác nhận session cookie `HttpOnly` không xuất hiện.
7. Logout, tải lại trang và kiểm tra cookie đã bị xóa; thử request cũ để xác nhận server đã thu hồi session.

Có thể kiểm tra header nhanh bằng curl trên môi trường thử nghiệm:

~~~bash
curl -sS -D - -o /dev/null https://app.example.test/login
~~~

`curl` cho biết server đã gửi header nào, nhưng không mô phỏng đầy đủ cookie policy của browser, SameSite, third-party cookie blocking hoặc CORS. Cần kiểm tra thêm trong browser thực tế.

Lưu ý: `document.cookie` không hiển thị cookie HttpOnly. Đây là hành vi mong đợi, không phải bằng chứng cookie chưa được đặt. DevTools và browser context API có thể hiển thị cookie HttpOnly cho mục đích chẩn đoán.

## 10. Tự động hóa kiểm thử bằng Playwright

Ví dụ sau giả định test fixture đã đăng nhập vào `https://app.example.test` và server phát `__Host-session`:

~~~javascript
import { test, expect, request } from '@playwright/test';

test('session cookie has secure attributes and is hidden from page JavaScript', async ({ page, context }) => {
  await loginAsTestUser(page);

  const cookies = await context.cookies('https://app.example.test');
  const sessionCookie = cookies.find((cookie) => cookie.name === '__Host-session');

  expect(sessionCookie).toBeTruthy();
  expect(sessionCookie.secure).toBe(true);
  expect(sessionCookie.httpOnly).toBe(true);
  expect(sessionCookie.sameSite).toBe('Lax');
  expect(sessionCookie.path).toBe('/');

  const visibleCookies = await page.evaluate(() => document.cookie);
  expect(visibleCookies).not.toContain('__Host-session=');
});

test('logout removes the browser cookie and invalidates the server session', async ({ page, context }) => {
  await loginAsTestUser(page);

  const before = await context.cookies('https://app.example.test');
  const oldSession = before.find((cookie) => cookie.name === '__Host-session');
  expect(oldSession).toBeTruthy();

  await logoutWithCsrf(page);

  const after = await context.cookies('https://app.example.test');
  expect(after.some((cookie) => cookie.name === '__Host-session')).toBe(false);

  // Dùng API request context độc lập để gửi lại cookie cũ đã giữ trong bộ nhớ test.
  const replayContext = await request.newContext({
    baseURL: 'https://app.example.test'
  });
  const replay = await replayContext.get('/api/account', {
    headers: { Cookie: `__Host-session=${oldSession.value}` }
  });
  expect(replay.status()).toBe(401);
  await replayContext.dispose();
});
~~~

`loginAsTestUser` và `logoutWithCsrf` là helper test của dự án; helper logout phải lấy và gửi CSRF token hợp lệ. Import `request` cùng `test` và `expect` từ `@playwright/test`. API request context độc lập trong ví dụ không dùng cookie jar của browser; test chủ động gửi lại giá trị session cũ đã giữ trong bộ nhớ để chứng minh server đã thu hồi session. Không in giá trị này ra log hoặc artifact.

Test bổ sung nên kiểm tra:

- Cookie `__Host-session` bị browser từ chối nếu server cố đặt `Domain` hoặc `Path` khác `/`.
- Cookie không được gửi qua HTTP và chỉ xuất hiện trên HTTPS.
- Cookie host-only không được gửi đến subdomain khác.
- Request cross-site trong iframe và form POST không nhận cookie theo cấu hình SameSite đã chọn.
- Request same-site nhưng cross-origin có gửi cookie đúng khi Fetch dùng `credentials: 'include'` và CORS được cấu hình chính xác.
- Browser không hỗ trợ hoặc chặn third-party cookie vẫn có fallback sản phẩm an toàn.

## 11. Ma trận kiểm thử thực tế

| Kịch bản | Cách thực hiện | Kết quả mong đợi |
|---|---|---|
| HTTPS | Đăng nhập qua HTTPS | Browser lưu và gửi cookie Secure |
| HTTP | Thử trên endpoint HTTP trong môi trường test | Cookie Secure không được gửi qua HTTP |
| JavaScript | Chạy `document.cookie` | Không đọc được session cookie HttpOnly |
| Host-only | Gọi subdomain khác | Cookie không được gửi đến host khác |
| Prefix | Thử đặt `__Host-session` với Domain hoặc Path khác `/` | Browser hỗ trợ prefix từ chối cookie không hợp lệ |
| SameSite Strict | Điều hướng từ site ngoài về ứng dụng | Cookie không được gửi trong ngữ cảnh cross-site bị Strict hạn chế |
| SameSite Lax | Điều hướng top-level GET từ site ngoài | Cookie có thể được gửi theo quy tắc Lax; kiểm tra browser mục tiêu |
| SameSite Lax + POST | Gửi form POST cross-site | Cookie Lax không được kỳ vọng gửi trong luồng POST cross-site thông thường |
| SameSite None | Thử ngữ cảnh cross-site | Cookie cần Secure; browser vẫn có thể chặn third-party cookie |
| CSRF token | Gửi POST thiếu token hoặc token sai | Server từ chối request |
| Session fixation | Giữ session ID trước login rồi đăng nhập | Server cấp session ID mới; ID cũ không có quyền đã xác thực |
| Logout | Logout rồi phát lại session cũ | Browser xóa cookie và server từ chối session cũ |
| Expiration | Chờ hết TTL hoặc thu hồi session ở server | Session hết hạn hoặc bị thu hồi dù client còn giữ bản cookie cũ |
| Nhiều browser | Chạy trên Chromium, Firefox, Safari và browser trong phạm vi hỗ trợ | Thuộc tính và luồng xác thực hoạt động theo ma trận đã công bố |

Không kiểm thử bằng cách sao chép cookie thật vào log hoặc chia sẻ qua ticket. Nếu cần kiểm tra replay, dùng session test ngắn hạn trong môi trường cô lập và thu hồi ngay sau khi hoàn tất.

## 12. Lỗi cấu hình thường gặp

| Lỗi | Rủi ro | Cách sửa |
|---|---|---|
| Thiếu `Secure` | Cookie có thể bị gửi qua HTTP | Bật HTTPS và đặt Secure; triển khai HSTS phù hợp |
| Thiếu `HttpOnly` trên session cookie | JavaScript có thể đọc trực tiếp cookie | Bật HttpOnly; vẫn xử lý XSS và quyền session |
| Dùng `SameSite=None` cho mọi cookie | Mở rộng gửi cookie cross-site | Chọn Strict/Lax theo luồng; chỉ dùng None khi có yêu cầu |
| Đặt `Domain=example.test` không cần thiết | Cookie được chia sẻ đến nhiều subdomain | Bỏ Domain để tạo host-only cookie |
| Dùng `Path` như ranh giới bảo mật | Ứng dụng cùng host có thể không được cách ly như kỳ vọng | Tách host hoặc áp dụng kiểm soát ở server; dùng Path đúng chức năng |
| Session ID cố định sau đăng nhập | Có thể bị session fixation | Regenerate session sau xác thực và thay đổi đặc quyền |
| Chỉ xóa cookie khi logout | Session phía server vẫn có thể còn hiệu lực | Thu hồi session trong store rồi xóa cookie |
| Không có CSRF token vì đã dùng SameSite | Vẫn có thể có request same-site từ subdomain hoặc luồng đặc biệt | Thêm CSRF token và kiểm tra Origin/Fetch Metadata |
| Dùng cookie JWT như dữ liệu bí mật | Payload JWT thường có thể decode; token có thể bị replay | Giới hạn TTL, xác minh chữ ký/claim, thu hồi và không lưu secret trong payload |
| Gộp nhiều `Set-Cookie` thành một header comma-separated | Cookie có thể bị parse sai, nhất là khi Expires chứa dấu phẩy | Gửi nhiều header `Set-Cookie` riêng biệt |

## 13. Bài thực hành tổng hợp

Hãy triển khai một luồng đăng nhập cho `app.example.test` với các yêu cầu sau:

1. Server tạo session ID ngẫu nhiên và lưu trạng thái session ở server-side store.
2. Cookie có tên `__Host-session`, không có `Domain`, `Path=/`, `Secure`, `HttpOnly`, `SameSite=Lax` và TTL 30 phút.
3. Session ID được regenerate sau khi đăng nhập thành công.
4. Mọi request thay đổi trạng thái đều cần CSRF token gắn với session; kiểm tra Origin chính xác và Fetch Metadata khi có.
5. Logout thu hồi session ở server, xóa cookie với đúng tên/path và trả response không cache.
6. API kiểm tra authorization theo user và object; không dùng dữ liệu role từ browser.
7. Kiểm thử trên ít nhất hai browser engine và một chế độ private browsing nếu nằm trong phạm vi hỗ trợ.

### Kết quả cần nộp trong môi trường thực hành

- Header `Set-Cookie` của response đăng nhập đã được làm sạch, không chứa session value thật.
- Ảnh hoặc log DevTools thể hiện Secure, HttpOnly, SameSite, Path và host-only scope.
- Kết quả kiểm tra `document.cookie` không đọc được session cookie.
- Bằng chứng session ID thay đổi sau đăng nhập và ID cũ bị từ chối.
- Bằng chứng logout xóa cookie và thu hồi session ở server.
- Kết quả test CSRF với token hợp lệ, thiếu token và token sai.
- Kết quả test subdomain, cross-site navigation, form POST và browser compatibility.
- Ghi chú những luồng cần ngoại lệ SameSite, ví dụ OAuth callback hoặc embedded widget, kèm lý do và biện pháp bảo vệ bổ sung.

## Checklist hoàn tất

- [ ] Cookie session dùng tên prefix phù hợp, ưu tiên `__Host-` khi kiến trúc đáp ứng yêu cầu.
- [ ] Cookie có `Secure`, `HttpOnly`, `SameSite` được chọn theo luồng và `Path=/` với `__Host-`.
- [ ] Không khai báo `Domain` nếu không cần chia sẻ cookie giữa subdomain.
- [ ] Session ID ngẫu nhiên, opaque, lưu trạng thái ở server và có TTL/thu hồi.
- [ ] Session được regenerate sau đăng nhập và thay đổi đặc quyền.
- [ ] Logout thu hồi session server-side và xóa cookie đúng phạm vi.
- [ ] CSRF token và kiểm tra request được áp dụng cho mọi thao tác thay đổi trạng thái.
- [ ] Không dùng GET để thay đổi dữ liệu.
- [ ] CORS, Fetch credentials và SameSite được phân biệt khi thiết kế cross-origin.
- [ ] Third-party cookie và CHIPS được đánh giá riêng nếu ứng dụng có nội dung nhúng.
- [ ] DevTools xác nhận response và request cookie đúng như thiết kế.
- [ ] Test tự động kiểm tra thuộc tính, HttpOnly, rotation, logout và replay.
- [ ] Đã kiểm tra trên các browser mục tiêu và chế độ riêng tư phù hợp.
- [ ] Không lưu cookie value, session ID hoặc token thật trong log và bằng chứng chia sẻ.

## Câu hỏi tự kiểm tra

1. Sự khác nhau giữa host-only cookie và cookie có `Domain` là gì?
2. Vì sao `Path` không nên được dùng làm ranh giới bảo mật giữa hai ứng dụng cùng host?
3. `HttpOnly` ngăn điều gì và không ngăn điều gì khi ứng dụng có XSS?
4. Khi nào nên chọn `SameSite=Strict`, `Lax` hoặc `None`?
5. Vì sao cookie `__Host-` không được có `Domain` và bắt buộc `Path=/`?
6. Tại sao logout phải thu hồi session ở server thay vì chỉ xóa cookie ở browser?
7. CORS, SameSite và CSRF token giải quyết những vấn đề khác nhau như thế nào?
8. Vì sao request từ subdomain cùng site vẫn cần được xem xét trong mô hình CSRF?

Cookie an toàn là kết quả của cả cấu hình browser và quản lý session ở server. Chọn đúng phạm vi host, bật thuộc tính bảo vệ, xoay vòng và thu hồi session, kiểm tra CSRF và thử trên browser thực tế sẽ giảm nguy cơ session bị lạm dụng. Hãy ghi lại cấu hình đã xác minh và chạy lại bộ test khi thay đổi domain, subdomain, luồng đăng nhập, reverse proxy hoặc chính sách cookie của browser.
