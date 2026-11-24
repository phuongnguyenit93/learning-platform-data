# Storage test

## Mục tiêu bài học

Sau bài này, bạn có thể:

- Lập kế hoạch kiểm thử các vùng lưu trữ phía browser: cookies, `localStorage`, `sessionStorage`, IndexedDB và Cache Storage.
- Xác minh dữ liệu được phân vùng theo origin, browsing context hoặc top-level site theo đúng cơ chế và browser mục tiêu.
- Kiểm tra quyền truy cập, thời gian tồn tại, đồng bộ giữa tab, quota, eviction và persistence.
- Phát hiện token hoặc dữ liệu nhạy cảm bị lưu ở nơi JavaScript cùng origin có thể đọc.
- Kiểm thử logout, đổi tài khoản, thu hồi session và dọn dữ liệu offline.
- Dùng Playwright cùng browser context riêng để tạo test storage lặp lại và cô lập.
- Phân biệt hành vi browser storage với cache HTTP, service worker và storage phía server.

## 1. Vì sao cần kiểm thử storage?

Ứng dụng web lưu trạng thái trong browser để duy trì đăng nhập, ghi nhớ tùy chọn, hỗ trợ offline, giảm request và đồng bộ giữa các tab. Mỗi API có phạm vi, vòng đời, giới hạn và quy tắc bảo mật khác nhau. Một lỗi storage có thể làm dữ liệu của tài khoản cũ xuất hiện sau khi đổi người dùng, khiến token bị đọc khi xảy ra XSS, làm ứng dụng dùng trạng thái lỗi thời hoặc làm mất dữ liệu offline chưa đồng bộ.

Kiểm thử storage cần xác minh hành vi thực tế của browser, không chỉ kiểm tra hàm `setItem()` hoặc schema IndexedDB. Ví dụ, test có thể chứng minh ứng dụng gọi hàm xóa localStorage khi logout nhưng vẫn bỏ sót IndexedDB, Cache Storage hoặc cookie. Một service worker có thể tiếp tục trả response từ Cache Storage sau khi cookie session đã bị thu hồi. Một third-party iframe có thể nhận vùng storage riêng theo top-level site, khác với khi mở cùng origin đó ở top-level.

Hãy bắt đầu từ câu hỏi dữ liệu nào được lưu, ai có thể đọc, dữ liệu sống bao lâu, khi nào cần xóa và browser có thể tự xóa hoặc phân vùng dữ liệu trong trường hợp nào.

## 2. Phân loại các vùng lưu trữ

| Cơ chế | Phạm vi chính | Vòng đời và đặc điểm | Điểm cần kiểm thử |
| --- | --- | --- | --- |
| Cookie | Theo domain/host, path, thuộc tính và chính sách site/partition của browser. | Có thể tồn tại đến thời hạn hết hạn; session cookie có vòng đời theo session browser nhưng cách khôi phục session tùy browser. | `Secure`, `HttpOnly`, `SameSite`, `Domain`, `Path`, `Partitioned`, expiration và request context. |
| `localStorage` | Origin; trong một số ngữ cảnh bên thứ ba còn chịu storage partitioning. | Thường tồn tại qua lần đóng/mở browser cho đến khi bị xóa hoặc browser eviction. Đồng bộ, API blocking. | Origin isolation, XSS exposure, quota, cross-tab `storage` event và logout cleanup. |
| `sessionStorage` | Origin trong một top-level browsing context/tab. | Thường kết thúc khi tab/window đóng; tab mới có thể nhận bản sao ban đầu khi được mở từ opener theo quy tắc browser. | Cách ly tab, reload, opener copy behavior và dữ liệu còn sau navigation. |
| IndexedDB | Origin, có thể chịu partitioning trong third-party context. | Database bất đồng bộ, hỗ trợ object store, index và transaction; dữ liệu có thể tồn tại lâu dài. | Schema upgrade, transaction, version conflict, quota, dữ liệu nhạy cảm và cleanup. |
| Cache Storage | Storage do ứng dụng/service worker quản lý theo origin và storage partition. | Giữ `Request`/`Response` do code ghi vào cache cho đến khi xóa hoặc browser eviction. | Cache key, dữ liệu riêng tư, logout, versioning và khác biệt với HTTP cache. |
| Storage Buckets / OPFS | API lưu trữ theo origin/bucket tùy browser hỗ trợ. | Dành cho dữ liệu ứng dụng lớn hoặc file; quota và support phụ thuộc browser. | Support matrix, quota, cleanup, persistence và isolation. |

Cookie thường được dùng để browser gửi credential cùng request; Web Storage và IndexedDB được JavaScript cùng origin đọc trực tiếp. Cache Storage lưu response do ứng dụng chủ động quản lý. Các cơ chế này không thể thay thế cho nhau và cũng không được dọn bằng cùng một lệnh.

## 3. Threat model và security invariant

Trước khi viết test, xác định dữ liệu và hành vi cần bảo vệ.

| Dữ liệu/hành vi | Rủi ro | Invariant nên kiểm tra |
| --- | --- | --- |
| Access/refresh token | Script cùng origin hoặc XSS đọc và gửi token ra ngoài. | Token nhạy cảm không nằm trong Web Storage/DOM; cookie xác thực dùng thuộc tính phù hợp nếu kiến trúc chọn cookie. |
| Hồ sơ và dữ liệu tài khoản | User B nhìn thấy dữ liệu user A sau logout/login. | Dữ liệu riêng tư được xóa hoặc phân vùng theo account; server luôn xác thực quyền khi tải lại. |
| Cache API | Service worker trả response riêng tư đã lưu. | Route riêng tư không được đưa vào Cache Storage nếu không có thiết kế offline được phê duyệt. |
| Third-party widget | Widget đọc trạng thái của cùng origin ở top-level hoặc site khác. | Storage được phân vùng/chặn theo policy browser; ứng dụng không dựa vào third-party state không được bảo đảm. |
| Offline draft | Dữ liệu chưa đồng bộ bị mất hoặc bị user khác đọc. | Draft được gắn account, có retention và xử lý đổi tài khoản rõ ràng. |
| Cookie session | Cookie bị gửi sai host/path/site hoặc JavaScript đọc được. | Cookie chỉ được gửi trong ngữ cảnh dự kiến và không bị script đọc nếu yêu cầu `HttpOnly`. |
| Dữ liệu lâu dài | Browser tự eviction hoặc quota đầy. | Ứng dụng xử lý lỗi quota, đồng bộ và khôi phục mà không hỏng trạng thái. |

Một invariant tốt mô tả kết quả quan sát được. Ví dụ: “Sau khi user A logout và user B đăng nhập trong cùng browser profile, không API hoặc cache nào hiển thị dữ liệu A”. Invariant này cần kiểm tra cả storage do ứng dụng quản lý và authorization ở server.

## 4. Origin, site và partitioning

`localStorage`, `sessionStorage` và IndexedDB thường được truy cập theo origin. Origin gồm scheme, host và port. Hai URL có cùng hostname nhưng khác scheme hoặc port vẫn là origin khác.

Cookie sử dụng domain/host, path, Secure, SameSite và các quy tắc cookie riêng; khái niệm site không giống origin. Storage partitioning còn có thể chia vùng dữ liệu bên thứ ba theo top-level site.

Ví dụ môi trường test:

```text
https://app.example.test
  └── Ứng dụng chính

https://api.example.test
  └── API khác origin nhưng cùng schemeful site với app

https://shop.example.test
  └── Top-level site A, nhúng widget.vendor.test

https://news.other.test
  └── Top-level site B, nhúng cùng widget.vendor.test

https://widget.vendor.test
  └── Third-party iframe cần kiểm tra partitioning
```

`app.example.test` và `api.example.test` khác origin nhưng thường cùng schemeful site. `shop.example.test` và `news.other.test` là hai site khác nhau. Dùng HTTPS và certificate hợp lệ để kiểm tra cookie `Secure`, `SameSite=None` và các API yêu cầu secure context.

Không dùng một kết quả từ `localhost` để suy ra hành vi cookie/partitioning trên mọi domain production. `localhost` có một số xử lý đặc biệt đối với secure context. Hãy dùng hostname test riêng, không trỏ đến production và ghi rõ browser/version cùng privacy settings.

## 5. Thiết lập môi trường test cô lập

Mỗi test cần trạng thái storage có thể kiểm soát. Playwright browser context là cách hữu ích để cô lập cookie và storage giữa test.

Nguyên tắc:

- Tạo context mới cho test độc lập; không chia sẻ session giữa test không liên quan.
- Dùng user, tenant, marker và dữ liệu giả.
- Cố định hostname, HTTPS certificate và browser version trong CI.
- Tắt service worker cho test không liên quan đến service worker; bật rõ ràng cho test Cache Storage/offline.
- Tránh chạy song song nếu test dùng chung account hoặc resource mutable.
- Dọn database, file, cache, user fixture và job sau test.
- Không sử dụng profile production hoặc cookie/token thật.

Ví dụ tạo context:

```ts
import { test, expect } from "@playwright/test";

test("storage state is isolated between browser contexts", async ({ browser }) => {
  const contextA = await browser.newContext();
  const contextB = await browser.newContext();

  const pageA = await contextA.newPage();
  const pageB = await contextB.newPage();

  await pageA.goto("https://app.example.test/storage-lab");
  await pageB.goto("https://app.example.test/storage-lab");

  await pageA.evaluate(() => localStorage.setItem("test-marker", "context-a"));
  const valueInB = await pageB.evaluate(() => localStorage.getItem("test-marker"));

  expect(valueInB).toBeNull();

  await contextA.close();
  await contextB.close();
});
```

Hai context có browser storage riêng dù cùng truy cập một origin. Không nhầm context isolation với việc hai tab trong cùng context bị cách ly; các tab trong cùng context thường chia sẻ cookie và localStorage của origin.

## 6. Kiểm thử localStorage

`localStorage` là kho key/value đồng bộ theo origin. Nó phù hợp với preference hoặc dữ liệu ít nhạy cảm cần tồn tại qua reload, nhưng mọi JavaScript chạy cùng origin có thể đọc dữ liệu. Nếu ứng dụng có XSS, attacker thường có thể đọc localStorage.

### 6.1. Kiểm tra origin isolation

Test ghi marker trên origin A rồi xác nhận origin B không đọc được:

```ts
test("localStorage is isolated by origin", async ({ page }) => {
  await page.goto("https://app.example.test/storage-lab");
  await page.evaluate(() => localStorage.setItem("origin-marker", "app-only"));

  await page.goto("https://attacker.test/storage-lab");
  const value = await page.evaluate(() => localStorage.getItem("origin-marker"));

  expect(value).toBeNull();
});
```

Không chỉ test hai host. Có thể bổ sung test cùng host khác port hoặc HTTP/HTTPS để xác minh đủ ba thành phần origin. Môi trường phải cấu hình hostname và port ổn định.

### 6.2. Kiểm tra dữ liệu nhạy cảm

Ứng dụng không nên lưu password, session token hoặc refresh token dài hạn trong localStorage nếu không có threat model chấp nhận rủi ro XSS tương ứng. Test có thể duyệt key/value trong test profile để phát hiện tên key hoặc marker nhạy cảm đã biết, nhưng không log toàn bộ nội dung storage vào CI report.

Ví dụ kiểm tra danh sách key:

```ts
test("authentication secrets are not stored in localStorage", async ({ page }) => {
  await page.goto("https://app.example.test/account");

  const keys = await page.evaluate(() =>
    Array.from({ length: localStorage.length }, (_, index) =>
      localStorage.key(index)
    ).filter((key): key is string => key !== null)
  );

  expect(keys).not.toContain("access_token");
  expect(keys).not.toContain("refresh_token");
  expect(keys).not.toContain("session_secret");
});
```

Đây là regression test theo quy ước đặt tên của ứng dụng, không phải bằng chứng tuyệt đối không có secret. Token có thể được lưu dưới key khác, mã hóa hoặc nằm trong IndexedDB. Cần rà soát schema và nơi ghi dữ liệu cùng code review.

### 6.3. Kiểm tra storage event giữa tab

Khi một document thay đổi localStorage, các document khác cùng origin trong phạm vi storage phù hợp có thể nhận `storage` event. Document thực hiện thay đổi không nhận event đó. Test có thể mở hai page trong cùng browser context:

```ts
test("localStorage changes notify another same-origin tab", async ({ context }) => {
  const pageA = await context.newPage();
  const pageB = await context.newPage();
  await pageA.goto("https://app.example.test/storage-lab");
  await pageB.goto("https://app.example.test/storage-lab");

  const eventPromise = pageB.evaluate(() => new Promise<string>((resolve) => {
    window.addEventListener("storage", (event) => {
      if (event.key === "theme") resolve(String(event.newValue));
    }, { once: true });
  }));

  await pageA.evaluate(() => localStorage.setItem("theme", "dark"));
  expect(await eventPromise).toBe("dark");
});
```

Storage event không phải cơ chế xác thực hoặc đồng bộ transaction. Không gửi token qua event. Nếu dùng event để đồng bộ logout, mọi tab vẫn cần xác minh session với server và xóa state riêng của mình.

## 7. Kiểm thử sessionStorage

`sessionStorage` được phân vùng theo origin và top-level browsing context. Nó tồn tại qua reload của cùng tab, nhưng thường không chia sẻ như localStorage giữa các tab độc lập. Khi tab được mở với opener, browser có thể khởi tạo tab mới bằng bản sao sessionStorage ban đầu; sau đó hai bản có thể thay đổi độc lập.

Test nên xác minh:

- Giá trị còn sau reload trong cùng tab.
- Tab độc lập không nhìn thấy giá trị sessionStorage của tab khác.
- Tab được mở từ opener có hành vi copy ban đầu phù hợp với browser mục tiêu.
- Navigation cross-origin không cho trang đích đọc sessionStorage của origin cũ.
- Dữ liệu nhạy cảm không bị giữ lâu hơn nhu cầu.

Ví dụ kiểm tra tab độc lập:

```ts
test("sessionStorage is not shared with an independent tab", async ({ context }) => {
  const pageA = await context.newPage();
  await pageA.goto("https://app.example.test/storage-lab");
  await pageA.evaluate(() => sessionStorage.setItem("tab-marker", "tab-a"));

  const pageB = await context.newPage();
  await pageB.goto("https://app.example.test/storage-lab");
  const value = await pageB.evaluate(() => sessionStorage.getItem("tab-marker"));

  expect(value).toBeNull();
});
```

Không dùng `sessionStorage` làm kho token bí mật trước XSS. JavaScript cùng origin trong tab vẫn có thể đọc nó. Tên gọi “session” cũng không đồng nghĩa với session xác thực phía server.

## 8. Kiểm thử cookie

Cookie có quy tắc riêng và thường được browser tự gửi trong request. Hãy kiểm tra cả `Set-Cookie` từ server, metadata trong browser context và request thực tế.

### 8.1. Thuộc tính cookie

Với session cookie, một cấu hình phổ biến là:

```http
Set-Cookie: __Host-session=opaque-test-value; Path=/; Secure; HttpOnly; SameSite=Lax
```

Prefix `__Host-` yêu cầu cookie được tạo từ secure origin, có `Path=/` và không có thuộc tính `Domain`. Browser sẽ từ chối cookie không đáp ứng các điều kiện của prefix này. `SameSite` phải được chọn theo luồng ứng dụng; SSO hoặc embedded use case có thể cần thiết kế khác.

Ví dụ Playwright kiểm tra metadata mà không in giá trị cookie:

```ts
test("session cookie has secure attributes", async ({ page, context }) => {
  await page.goto("https://app.example.test/login");
  await page.getByLabel("Username").fill("storage-test-user");
  await page.getByLabel("Password").fill("test-password");
  await page.getByRole("button", { name: "Sign in" }).click();

  const cookies = await context.cookies("https://app.example.test");
  const session = cookies.find((cookie) => cookie.name === "__Host-session");

  expect(session).toBeDefined();
  expect(session?.secure).toBe(true);
  expect(session?.httpOnly).toBe(true);
  expect(session?.path).toBe("/");
  expect(session?.sameSite).toBe("Lax");
});
```

Không log `cookies` object vì nó chứa giá trị cookie. Nếu ứng dụng dùng `SameSite=None`, kiểm tra thêm `Secure` và thử đúng third-party context. Browser privacy setting vẫn có thể hạn chế cookie bên thứ ba.

### 8.2. Cookie gửi theo request context

Kiểm tra cookie trong các tình huống:

- Request same-origin.
- Request cross-origin nhưng same-site giữa subdomain.
- Top-level navigation từ site khác.
- Cross-site form POST.
- Fetch cross-origin với `credentials: "include"`.
- Iframe bên thứ ba và cookie có `Partitioned` nếu sản phẩm hỗ trợ CHIPS.

`document.cookie` không hiển thị cookie `HttpOnly`; điều đó không có nghĩa browser không gửi cookie. Dùng endpoint test chỉ trả về boolean cookie có mặt hay không, hoặc kiểm tra request trong test runner mà không lưu giá trị vào report.

### 8.3. Logout và thu hồi session

Logout cần thu hồi session phía server và hết hạn cookie bằng đúng domain/path đã tạo cookie. Xóa cookie ở client mà không revoke session server-side là chưa đủ. Ngược lại, revoke server session mà UI vẫn giữ dữ liệu cache cũng có thể làm lộ thông tin cũ trên màn hình.

Test cần xác minh:

- Cookie session bị xóa/expire sau logout.
- Request tiếp theo dùng cookie cũ bị server từ chối.
- Tab khác nhận tín hiệu logout và xóa state cục bộ.
- User B không thấy dữ liệu của user A trong cùng browser profile.
- Back/Forward restore không hiển thị dữ liệu cũ mà không revalidate.

## 9. Kiểm thử IndexedDB

IndexedDB là database bất đồng bộ theo origin, phù hợp với dữ liệu có cấu trúc, index và lượng dữ liệu lớn hơn Web Storage. Transaction cung cấp cơ chế nhất quán, nhưng code cần xử lý lỗi, version upgrade và transaction bị abort.

### 9.1. Kiểm tra persistence và origin isolation

Một test cơ bản có thể tạo database, ghi marker, reload rồi đọc lại:

```ts
test("IndexedDB data persists across reload for the same origin", async ({ page }) => {
  await page.goto("https://app.example.test/storage-lab");

  await page.evaluate(async () => {
    const openRequest = indexedDB.open("storage-test", 1);
    const db = await new Promise<IDBDatabase>((resolve, reject) => {
      openRequest.onupgradeneeded = () => {
        openRequest.result.createObjectStore("settings");
      };
      openRequest.onsuccess = () => resolve(openRequest.result);
      openRequest.onerror = () => reject(openRequest.error);
    });

    await new Promise<void>((resolve, reject) => {
      const transaction = db.transaction("settings", "readwrite");
      transaction.objectStore("settings").put("dark", "theme");
      transaction.oncomplete = () => resolve();
      transaction.onabort = () => reject(transaction.error);
      transaction.onerror = () => reject(transaction.error);
    });
    db.close();
  });

  await page.reload();
  const value = await page.evaluate(async () => {
    const request = indexedDB.open("storage-test", 1);
    const db = await new Promise<IDBDatabase>((resolve, reject) => {
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    });

    const result = await new Promise<unknown>((resolve, reject) => {
      const transaction = db.transaction("settings", "readonly");
      const getRequest = transaction.objectStore("settings").get("theme");
      getRequest.onsuccess = () => resolve(getRequest.result);
      getRequest.onerror = () => reject(getRequest.error);
    });
    db.close();
    return result;
  });

  expect(value).toBe("dark");
});
```

Ví dụ minh họa luồng mở database và transaction; code production cần đóng database khi không dùng, xử lý `versionchange`, `blocked`, `abort` và lỗi quota. Không dùng một tên database cố định chung giữa test song song nếu chúng cùng ghi dữ liệu.

### 9.2. Version upgrade và nhiều tab

Khi tăng version database, browser phát `versionchange` đến connection cũ. Nếu tab cũ không đóng connection, upgrade ở tab mới có thể bị `blocked`. Test nên mở hai page cùng origin:

1. Page A mở database version 1 và giữ connection.
2. Page B yêu cầu mở version 2.
3. Xác nhận Page A nhận `versionchange`.
4. Đóng connection ở Page A.
5. Xác nhận upgrade hoàn tất ở Page B.

Ứng dụng nên xử lý `db.onversionchange` để đóng connection cũ và thông báo reload/update nếu cần. Không xóa database tự động chỉ vì upgrade bị blocked; có thể làm mất dữ liệu chưa đồng bộ.

### 9.3. Transaction và tính toàn vẹn

Kiểm thử các trường hợp:

- Nhiều thao tác trong một transaction cùng commit hoặc abort theo mong đợi.
- Lỗi quota hoặc exception làm transaction không để lại trạng thái nửa chừng.
- Schema upgrade không làm mất dữ liệu cần giữ.
- Unique index từ chối dữ liệu trùng.
- Dữ liệu theo account được phân vùng/namespace đúng.
- Logout xóa hoặc vô hiệu hóa record riêng tư theo policy.

Không giả định IndexedDB là nơi an toàn để lưu token chỉ vì API bất đồng bộ hoặc khó quan sát hơn localStorage. JavaScript cùng origin có thể truy vấn database.

## 10. Kiểm thử Cache Storage và Service Worker

Cache Storage cho phép service worker hoặc page lưu `Request`/`Response` theo cache name. Đây là cache do ứng dụng quản lý; nó khác browser HTTP cache. Một response có `Cache-Control: no-store` vẫn có thể bị code chủ động đưa vào Cache Storage bằng `cache.put()`.

### 10.1. Kiểm tra không cache response riêng tư

Test có thể mở ứng dụng rồi liệt kê cache names và request keys:

```ts
test("private API responses are not stored in Cache Storage", async ({ page }) => {
  await page.goto("https://app.example.test/account");

  const privateEntries = await page.evaluate(async () => {
    const names = await caches.keys();
    const matches: string[] = [];

    for (const name of names) {
      const cache = await caches.open(name);
      const requests = await cache.keys();
      for (const request of requests) {
        if (new URL(request.url).pathname.startsWith("/api/private/")) {
          matches.push(request.url);
        }
      }
    }
    return matches;
  });

  expect(privateEntries).toEqual([]);
});
```

Nếu ứng dụng có thiết kế offline riêng cho dữ liệu cá nhân, thay assertion bằng policy cụ thể về account partition, encryption, retention và logout cleanup. Không mặc định mọi API riêng tư đều được phép cache chỉ vì service worker tồn tại.

### 10.2. Cache version và cleanup

Khi deploy, service worker thường tạo cache version mới và xóa cache cũ trong `activate`. Test cần xác minh:

- Cache version mới được tạo sau activation.
- Cache cũ bị xóa theo allowlist/version policy.
- Không xóa cache của origin khác hoặc cache không thuộc ứng dụng.
- Response riêng tư không được thêm vào cache static.
- Worker đang chờ được activate theo lifecycle dự kiến.
- Offline fallback không trả nhầm response từ user hoặc tenant khác.

### 10.3. Logout

Logout cần dọn các cache do ứng dụng quản lý có chứa dữ liệu theo user. Có thể xóa cache name dành riêng cho account, nhưng cần tránh xóa cache static dùng chung nếu không cần. Nếu nhiều tab đang dùng service worker, gửi thông báo logout và yêu cầu mỗi tab xóa state của mình; server vẫn phải revoke session.

## 11. Storage partitioning và third-party context

Browser có thể partition hoặc hạn chế storage trong third-party context để giảm tracking. Cùng một `widget.vendor.test` có thể nhận storage khác nhau khi được nhúng dưới `shop.example.test` và `news.other.test`. Hành vi chính xác phụ thuộc browser, version, API và privacy settings.

### 11.1. Thiết kế test

1. Tạo một browser context mới.
2. Mở top-level site A và nhúng `widget.vendor.test`.
3. Trong iframe, ghi marker vô hại vào storage API cần kiểm tra.
4. Điều hướng top-level page sang site B và nhúng cùng widget origin.
5. Kiểm tra marker có xuất hiện hay không.
6. Ghi rõ browser partition, block hay cho phép state dùng chung.

Không dùng hai browser context riêng cho hai top-level site nếu mục tiêu là kiểm tra partitioning theo top-level site trong cùng profile; context riêng đã tự cô lập storage và có thể làm test mất ý nghĩa.

### 11.2. Cookie partitioning và CHIPS

Cookie có thuộc tính `Partitioned` (CHIPS) cho phép cookie third-party được phân vùng theo top-level site trong browser hỗ trợ. Test cần xác minh cookie được gửi trong partition tương ứng và không được dùng chung giữa các top-level site ngoài thiết kế.

Không coi CHIPS là giải pháp chung cho mọi third-party state. Cần kiểm tra browser support, `Secure`, cấu hình cookie và yêu cầu nghiệp vụ. Nếu browser không hỗ trợ, đánh dấu test `unsupported` thay vì coi là pass.

### 11.3. Storage Access API

Một số use case embedded cần truy cập state first-party. Storage Access API có thể cho iframe yêu cầu quyền truy cập theo điều kiện browser, user activation và chính sách privacy. Test cần bao gồm cả trường hợp được cấp và bị từ chối, prompt hoặc điều kiện user gesture. Không tự động cấp quyền để làm test pass; ứng dụng phải có fallback khi người dùng từ chối.

## 12. Quota, eviction và persistent storage

Browser giới hạn dung lượng storage theo origin, bucket, profile hoặc chính sách nội bộ. Không có một con số quota cố định áp dụng cho mọi browser, thiết bị và chế độ riêng tư.

### 12.1. Quan sát quota

`navigator.storage.estimate()` trả về ước lượng `usage` và `quota` khi API được hỗ trợ:

```js
const estimate = await navigator.storage.estimate();
console.log({
  usage: estimate.usage,
  quota: estimate.quota
});
```

Các giá trị có thể được làm tròn, thay đổi theo thời điểm và không đảm bảo dung lượng còn lại sẽ được cấp cho lần ghi tiếp theo. Không dùng kết quả estimate làm authorization hoặc cam kết dung lượng. Tránh gửi số liệu storage chi tiết về telemetry nếu không cần vì chúng có thể góp phần fingerprinting.

### 12.2. Xử lý QuotaExceededError

Test không nên cố ghi dữ liệu cho đến khi đầy ổ đĩa hoặc làm cạn quota thật của browser profile. Thay vào đó:

- Dùng adapter storage có thể giả lập lỗi quota ở unit/integration test.
- Đặt quota ứng dụng nhỏ trong fixture và xác minh code dừng trước giới hạn.
- Dùng dữ liệu fixture có kích thước nhỏ, giới hạn tổng byte và cleanup sau test.
- Xác nhận transaction bị abort không để lại trạng thái không nhất quán.
- Xác nhận UI thông báo lỗi và cho phép retry/export/xóa dữ liệu theo policy.

Ví dụ xử lý lỗi:

```js
async function saveDraft(store, draft) {
  try {
    await store.put(draft);
    return { ok: true };
  } catch (error) {
    if (error?.name === "QuotaExceededError") {
      return { ok: false, reason: "storage-full" };
    }
    throw error;
  }
}
```

Test cần xác minh ứng dụng không báo “đã lưu” khi write thất bại. Với draft quan trọng, hãy giữ nội dung ở memory cho đến khi ghi thành công hoặc thông báo rõ cho người dùng.

### 12.3. Eviction và persist()

Browser có thể xóa dữ liệu best-effort khi thiếu dung lượng hoặc theo chính sách quản lý storage. `navigator.storage.persist()` có thể yêu cầu browser cấp persistent storage; browser quyết định theo policy và có thể trả `false`. `persisted()` cho biết trạng thái hiện tại nếu được hỗ trợ.

Không giả định persistent storage luôn được cấp hoặc ngăn mọi trường hợp người dùng xóa dữ liệu. Test cần kiểm tra cả nhánh được cấp và không được cấp, và ứng dụng phải hoạt động khi storage có thể bị eviction. Dữ liệu quan trọng cần đồng bộ lên server hoặc có cơ chế export/recovery phù hợp.

## 13. Clear storage và logout

Logout là ranh giới quan trọng giữa hai danh tính dùng cùng browser profile. Việc xóa localStorage không tự động xóa sessionStorage, IndexedDB, Cache Storage, cookie hoặc state trong JavaScript memory.

Một quy trình logout có thể cần:

1. Revoke session phía server.
2. Hết hạn cookie session với đúng domain/path/attributes.
3. Xóa token và state xác thực khỏi memory.
4. Xóa localStorage/sessionStorage key do ứng dụng quản lý.
5. Xóa record riêng tư trong IndexedDB hoặc đánh dấu dữ liệu không còn truy cập được.
6. Xóa Cache Storage có chứa dữ liệu theo user.
7. Gửi tín hiệu đến tab khác để dọn state và điều hướng về login.
8. Xác minh API từ chối session cũ và dữ liệu user A không xuất hiện với user B.

Không xóa toàn bộ origin storage một cách mù quáng nếu ứng dụng có dữ liệu offline chưa đồng bộ cần giữ. Phân loại dữ liệu theo account, retention và khả năng phục hồi trước khi cleanup.

### 13.1. Storage event và BroadcastChannel

`storage` event có thể báo thay đổi localStorage cho document khác cùng origin theo quy tắc của browser. `BroadcastChannel` cho phép các context cùng origin trao đổi thông điệp. Cả hai đều là cơ chế đồng bộ UI, không phải nguồn xác thực.

Ví dụ gửi tín hiệu logout không chứa token:

```js
const authChannel = new BroadcastChannel("app-auth");

function notifyLogout() {
  authChannel.postMessage({ type: "logout" });
}

authChannel.addEventListener("message", ({ data }) => {
  if (data?.type !== "logout") return;
  clearInMemoryUserState();
  clearPrivateAppStorage();
  window.location.replace("/login");
});
```

Mỗi tab vẫn phải gọi server hoặc điều hướng đến endpoint xác minh session. Không truyền access token, cookie hoặc dữ liệu hồ sơ trong BroadcastChannel.

## 14. Clear-Site-Data và xóa dữ liệu theo origin

Response header `Clear-Site-Data` có thể yêu cầu browser xóa một số loại dữ liệu liên quan đến origin, ví dụ cache, cookies hoặc storage theo directive được hỗ trợ. Hành vi và phạm vi hỗ trợ cần kiểm tra trên browser mục tiêu; không dùng header này thay cho logout/revocation server-side.

Ví dụ cấu hình minh họa:

```http
Clear-Site-Data: "cache", "cookies", "storage"
```

Header có tác động rộng đến dữ liệu origin. Chỉ sử dụng khi sản phẩm hiểu rõ dữ liệu nào sẽ bị xóa, các subdomain/cookie scope bị ảnh hưởng và khả năng mất dữ liệu offline. Test trong profile riêng, không phát header này trên production để thử nghiệm. Kiểm tra response thực tế, browser support và các vùng dữ liệu sau khi browser xử lý.

`Clear-Site-Data` không thay thế việc xóa session trong database, thu hồi refresh token hoặc invalidation cache ở CDN/server. Nó cũng không xóa dữ liệu ở origin khác.

## 15. Kiểm thử storage qua Playwright

Playwright có thể điều khiển page, browser context và cookie. Dùng `page.evaluate()` để chạy code trong đúng origin browser khi cần kiểm tra Web Storage, IndexedDB hoặc Cache API. Không dùng API request trực tiếp để kết luận browser storage policy.

### 15.1. Seed localStorage trước khi ứng dụng khởi chạy

```ts
test("application handles a stored preference", async ({ page }) => {
  await page.addInitScript(({ origin, key, value }) => {
    if (location.origin === origin) {
      localStorage.setItem(key, value);
    }
  }, {
    origin: "https://app.example.test",
    key: "theme",
    value: "dark"
  });

  await page.goto("https://app.example.test/settings");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
});
```

`addInitScript` chạy trước script của trang trên các navigation phù hợp. Hãy giới hạn theo origin để không seed dữ liệu vào iframe hoặc host khác. Không seed session token thật; dùng fixture state không có quyền truy cập production.

### 15.2. Kiểm tra cookie mà không làm lộ giá trị

```ts
const cookies = await context.cookies("https://app.example.test");
const summary = cookies.map(({ name, secure, httpOnly, sameSite, path }) => ({
  name,
  secure,
  httpOnly,
  sameSite,
  path
}));
expect(summary.some((cookie) => cookie.name === "__Host-session" && cookie.httpOnly && cookie.secure)).toBe(true);
```

Chỉ đưa metadata cần thiết vào assertion. Không `console.log(cookies)` hoặc đính kèm giá trị cookie vào report.

### 15.3. IndexedDB và Cache Storage

Chạy test trong page của origin ứng dụng để gọi `indexedDB.open()` và `caches.keys()`. Với Cache Storage, kiểm tra request keys để phát hiện route riêng tư. Với IndexedDB, kiểm tra schema và record marker; tránh dump toàn bộ record có dữ liệu cá nhân.

### 15.4. Kiểm tra logout và đổi tài khoản

Một scenario end-to-end:

1. Đăng nhập user A trong context.
2. Tạo dữ liệu marker trong localStorage, IndexedDB và Cache Storage theo fixture.
3. Mở tab thứ hai cùng context và xác nhận state A được chia sẻ đúng nơi thiết kế cho phép.
4. Logout user A.
5. Xác minh session bị revoke và storage riêng tư được dọn theo policy.
6. Đăng nhập user B trong cùng context.
7. Mở lại route và xác nhận chỉ dữ liệu B xuất hiện.
8. Kiểm tra Back/Forward và offline fallback không hiển thị dữ liệu A.

Test cần assert trạng thái server/database hoặc gọi endpoint test để xác minh quyền. Việc key biến mất khỏi localStorage không chứng minh dữ liệu A đã bị xóa khỏi IndexedDB, Cache Storage hoặc server.

## 16. Ma trận kiểm thử storage

| Nhóm | Kịch bản | Kết quả mong đợi |
| --- | --- | --- |
| localStorage | Cùng origin, reload, tab khác | Dữ liệu tồn tại theo thiết kế; tab cùng origin nhận event khi tab khác ghi. |
| localStorage | Khác scheme/host/port | Origin khác không đọc được dữ liệu. |
| localStorage | XSS threat review | Không có token/secret nhạy cảm có thể đọc trực tiếp. |
| sessionStorage | Reload cùng tab | Dữ liệu tồn tại trong session của tab. |
| sessionStorage | Tab độc lập | Không dùng chung state ngoài hành vi opener-copy được kiểm tra riêng. |
| Cookie | Secure/HttpOnly/SameSite | Browser gửi cookie đúng request context; JS không đọc HttpOnly cookie. |
| Cookie | Logout/revoke | Cookie hết hạn và server từ chối session cũ. |
| IndexedDB | Reload và transaction | Record hợp lệ tồn tại; transaction commit/abort nhất quán. |
| IndexedDB | Version upgrade nhiều tab | Connection cũ xử lý `versionchange`; upgrade không treo vô hạn. |
| Cache Storage | Static asset | Chỉ tài nguyên public/allowlist được cache. |
| Cache Storage | API riêng tư | Không bị `cache.put()` hoặc trả lại cho user khác ngoài policy. |
| Partitioning | Cùng widget ở hai top-level site | Kết quả block/partition/share phù hợp browser support và privacy policy. |
| Quota | Write vượt quota ứng dụng | App xử lý lỗi, không báo lưu thành công giả. |
| Persistence | `persist()` được cấp/từ chối | App hoạt động đúng trong cả hai nhánh. |
| Eviction | Dữ liệu best-effort bị mất | App phục hồi/sync hoặc yêu cầu tải lại an toàn. |
| Logout | A → logout → B | Không còn dữ liệu riêng tư của A trong tab, cache hoặc storage được quản lý. |
| Clear-Site-Data | Test trên profile riêng | Browser xóa đúng loại dữ liệu được yêu cầu theo support. |

## 17. Cross-browser và privacy testing

Storage behavior có thể khác theo engine, phiên bản, chế độ riêng tư, tracking protection và cài đặt người dùng. Hãy chạy suite cốt lõi trên browser mà sản phẩm hỗ trợ và ghi nhận feature-specific result.

| Nhóm | Chromium | Firefox | WebKit/Safari | Cách báo cáo |
| --- | --- | --- | --- | --- |
| Web Storage/IndexedDB | Bắt buộc | Bắt buộc | Bắt buộc | Kiểm tra isolation, persistence và transaction. |
| Cookie flags | Bắt buộc | Bắt buộc | Bắt buộc | Ghi request context và privacy settings. |
| Third-party storage | Theo version/policy | Theo version/policy | Theo version/policy | Phân biệt blocked, partitioned và granted access. |
| CHIPS/Partitioned cookie | Feature-specific | Feature-specific | Feature-specific | Đánh dấu unsupported nếu browser chưa hỗ trợ. |
| Storage Access API | Feature-specific | Feature-specific | Feature-specific | Test cả user grant và deny. |
| Persistent storage | Theo policy browser | Theo policy browser | Theo policy browser | Không giả định `persist()` luôn trả true. |
| Cache Storage/service worker | Bắt buộc nếu app dùng | Bắt buộc nếu app dùng | Bắt buộc nếu app dùng | Kiểm tra lifecycle và cleanup. |

Không gộp `unsupported` hoặc `skipped` thành `passed`. Nếu browser không hỗ trợ một API, ghi rõ version, lý do và fallback của ứng dụng. Private browsing có thể thay đổi quota, persistence và vòng đời dữ liệu; test riêng nếu sản phẩm tuyên bố hỗ trợ chế độ đó.

## 18. Tránh test phá hoại và false positive

Storage test có thể gây tác dụng phụ nếu ghi lượng dữ liệu lớn, xóa nhầm profile hoặc chạy song song trên cùng account. Hãy dùng quota ứng dụng nhỏ và adapter giả lập thay vì làm đầy storage browser thật.

Các nguyên tắc:

- Không ghi lặp vô hạn để tìm quota thật.
- Không xóa site data của profile người dùng thật.
- Không dùng production account để kiểm tra logout hoặc eviction.
- Không giả định `navigator.storage.estimate()` trả quota chính xác tuyệt đối.
- Không kết luận storage event đã đồng bộ server state.
- Không coi Cache-Control là lệnh ngăn Cache Storage ghi response thủ công.
- Không coi `HttpOnly` là bảo vệ dữ liệu khỏi mọi script; nó chỉ ngăn JavaScript đọc cookie.
- Không coi storage partitioning là giống nhau trên mọi browser/version.
- Không log record, cookie, token hoặc nội dung draft vào test output.
- Không dùng retry để che race condition trong IndexedDB upgrade hoặc logout.

Nếu test fail, phân biệt lỗi ứng dụng, lỗi fixture, quota/environment, browser support và privacy setting. Lưu browser/version cùng bước tái hiện tối thiểu.

## 19. Báo cáo kết quả

Mỗi finding nên có:

- Storage API và origin/top-level site liên quan.
- Browser engine/version, OS và privacy mode.
- Build/commit, môi trường và test fixture.
- Account/tenant giả lập và trạng thái trước test.
- Bước tái hiện, kết quả mong đợi và thực tế.
- Key/record marker đã làm sạch, không có giá trị bí mật.
- Kết quả request/server authorization nếu có.
- Phân biệt `blocked`, `partitioned`, `evicted`, `quota exceeded` và `unsupported`.
- Ảnh hưởng, hướng khắc phục và regression test.

Không đính kèm database dump, cookie jar, storageState JSON, IndexedDB record thật hoặc trace chứa credential. Playwright `storageState` có thể chứa cookie và localStorage; coi file này là bí mật, giới hạn quyền truy cập và xóa sau khi test. Không commit storage state của tài khoản thật vào repository.

## 20. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Chỉ xóa localStorage khi logout | Cookie, IndexedDB, Cache Storage hoặc state trong memory vẫn còn. | Có inventory storage và cleanup theo account; revoke session server-side. |
| Lưu token trong localStorage | XSS cùng origin có thể đọc và gửi token. | Tránh lưu credential dài hạn trong Web Storage; đánh giá cookie HttpOnly và threat model. |
| Nghĩ sessionStorage là session xác thực | Dữ liệu chỉ thuộc tab context, không chứng minh server session còn hợp lệ. | Xác minh session với server; dùng storage cho state UI phù hợp. |
| Tin `HttpOnly` bảo vệ mọi dữ liệu | Script vẫn có thể thực hiện request bằng cookie và đọc response nếu cùng origin. | Kết hợp XSS defense, CSRF defense, authorization và cookie policy. |
| Nghĩ `no-store` ngăn Cache Storage | Service worker vẫn có thể tự ghi response bằng Cache API. | Kiểm tra code fetch handler và cache allowlist. |
| Dùng hai context riêng để test partitioning | Test chỉ chứng minh context isolation, không chứng minh partition theo top-level site. | Dùng cùng context, thay top-level site và nhúng cùng third-party origin. |
| Giả định quota cố định | Test không ổn định giữa thiết bị/browser. | Kiểm tra quota ứng dụng và giả lập QuotaExceededError. |
| Dùng `persist()` như bảo đảm không mất dữ liệu | Browser có thể từ chối hoặc người dùng xóa storage. | Có sync/recovery và xử lý nhánh không được cấp. |
| Xóa database khi upgrade bị blocked | Có thể làm mất dữ liệu chưa đồng bộ. | Xử lý `versionchange`, đóng connection và thông báo reload. |
| Log toàn bộ storageState | Lộ cookie, token và dữ liệu cá nhân trong artifact. | Dùng fixture giả, chỉ assert metadata cần thiết và bảo vệ artifact. |

## 21. Bài thực hành

Xây dựng một staging app có đăng nhập, preference, draft offline và service worker. Dùng hai tài khoản thử A/B, hai top-level site test và dữ liệu marker.

1. Tạo Playwright browser context riêng và chứng minh localStorage được phân vùng giữa context.
2. Kiểm tra localStorage theo origin và sessionStorage theo tab.
3. Mở hai tab cùng origin, kiểm tra `storage` event và đồng bộ logout không truyền token.
4. Kiểm tra cookie session có `Secure`, `HttpOnly`, `SameSite` và prefix phù hợp; xác minh server revoke session sau logout.
5. Ghi/read một marker trong IndexedDB; thử transaction abort và version upgrade khi tab khác còn connection.
6. Kiểm tra Cache Storage chỉ chứa asset public và không lưu response API riêng tư.
7. Nhúng cùng widget origin dưới hai top-level site trong cùng context; ghi nhận storage bị block, partition hay dùng chung theo browser.
8. Giả lập lỗi quota bằng adapter hoặc ngưỡng ứng dụng nhỏ; xác minh UI không báo lưu thành công khi write thất bại.
9. Kiểm tra nhánh `navigator.storage.persist()` được cấp và bị từ chối nếu browser hỗ trợ.
10. Đăng nhập A, tạo dữ liệu ở từng storage, logout, đăng nhập B và xác nhận dữ liệu riêng tư A không còn hiển thị.
11. Thử Back/Forward và offline mode để bảo đảm cache không phục vụ dữ liệu cũ.
12. Chạy suite trên Chromium, Firefox và WebKit; ghi rõ `passed`, `failed`, `skipped` và `unsupported`.
13. Xuất report đã làm sạch, không chứa cookie, token, database dump hoặc storageState thật.

Hoàn thành bài thực hành khi bạn chứng minh được từng storage API có phạm vi và vòng đời đúng như thiết kế, dữ liệu nhạy cảm không bị lộ qua JavaScript hoặc cache, quota/lỗi được xử lý an toàn, và logout/đổi tài khoản không làm rò dữ liệu giữa hai người dùng.
