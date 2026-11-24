# Cache test

## Mục tiêu

Kiểm thử cache trong ứng dụng web nhằm xác nhận dữ liệu được lưu, tái sử dụng và làm mới đúng chính sách bảo mật. Một lỗi cache có thể khiến người dùng nhìn thấy dữ liệu của phiên trước, nhận nội dung cũ sau khi quyền truy cập thay đổi, hoặc khiến cache dùng chung phân phối một phản hồi riêng tư cho nhiều người dùng.

Sau bài này, bạn có thể:

- Phân biệt HTTP cache, cache dùng chung ở proxy/CDN, Back/Forward Cache (bfcache) và Cache API của Service Worker.
- Đọc và đánh giá các chỉ thị `Cache-Control`, `ETag`, `Last-Modified`, `Vary` và `Age`.
- Kiểm tra việc cách ly dữ liệu giữa hai tài khoản, việc xác thực lại phản hồi và khả năng cache poisoning.
- Thu thập bằng chứng từ DevTools và `curl`, sau đó xác định nguyên nhân khi kết quả không đúng chính sách.

## 1. Phạm vi và mô hình cache

Cache giúp giảm độ trễ và tải máy chủ bằng cách giữ bản sao của phản hồi. Trong kiểm thử bảo mật, cần xác định rõ thành phần nào đang giữ bản sao và thành phần nào có quyền tái sử dụng nó.

| Loại cache | Nơi lưu | Rủi ro cần kiểm tra |
|---|---|---|
| HTTP cache riêng tư | Trình duyệt của một hồ sơ người dùng | Trang tài khoản còn hiển thị sau đăng xuất hoặc đổi tài khoản trên cùng thiết bị |
| Shared cache | Reverse proxy, CDN hoặc proxy doanh nghiệp | Phản hồi của người dùng A được phục vụ cho người dùng B |
| Cache API | Storage do ứng dụng hoặc Service Worker quản lý theo origin | Mã ứng dụng chủ động lưu API riêng tư rồi trả lại khi offline hoặc ở phiên khác |
| Back/Forward Cache (bfcache) | Snapshot tài liệu trong bộ nhớ của trình duyệt để quay lại trang trước | Nội dung nhạy cảm xuất hiện khi người dùng nhấn Back sau khi đăng xuất |

HTTP cache và Cache API là hai cơ chế khác nhau. HTTP cache tuân theo các quy tắc cache HTTP và header của phản hồi. Cache API là kho lưu trữ mà mã JavaScript quản lý trực tiếp; ứng dụng phải tự quyết định nội dung nào được ghi, đọc và xóa. Không thể suy ra Cache API an toàn chỉ từ `Cache-Control: no-store`.

bfcache cũng không phải HTTP cache. Trình duyệt có thể khôi phục snapshot của cả tài liệu khi người dùng quay lại bằng nút Back hoặc Forward. Hành vi bfcache thay đổi theo trình duyệt và phiên bản; phải kiểm tra trực tiếp trên các trình duyệt được hỗ trợ.

## 2. Đọc chính sách HTTP cache

Các chỉ thị dưới đây thường xuất hiện trong header `Cache-Control` của phản hồi:

| Chỉ thị | Ý nghĩa khi kiểm thử |
|---|---|
| `no-store` | Cache HTTP không được lưu phản hồi. Dùng cho nội dung nhạy cảm cần tránh lưu trong HTTP cache. Chỉ thị này không xóa bản sao đã tồn tại và không tự ngăn ứng dụng ghi dữ liệu vào Cache API, IndexedDB hoặc bộ nhớ khác. |
| `no-cache` | Phản hồi có thể được lưu, nhưng phải xác thực lại với máy chủ trước khi tái sử dụng. Không có nghĩa là “không lưu”. |
| `private` | Cache riêng tư của trình duyệt có thể lưu phản hồi; shared cache không được lưu phản hồi đó. Đây là chỉ thị phù hợp với một số nội dung cá nhân có thể lưu cục bộ. |
| `public` | Cho phép shared cache lưu phản hồi trong các trường hợp mà mặc định có thể hạn chế việc lưu. Chỉ dùng khi nội dung thực sự công khai. |
| `max-age=N` | Phản hồi được xem là còn mới trong N giây đối với cache riêng tư. |
| `s-maxage=N` | Thời gian còn mới dành cho shared cache; có ưu tiên cao hơn `max-age` trong shared cache. |
| `must-revalidate` | Khi phản hồi đã cũ, cache phải xác thực thành công trước khi sử dụng lại. |
| `immutable` | Báo rằng biểu diễn không thay đổi trong thời gian còn mới; thường dùng cho tài nguyên tĩnh có tên chứa hash phiên bản. |

Một số điểm dễ hiểu sai:

- `Cache-Control: no-cache` cho phép lưu phản hồi, nhưng yêu cầu xác thực lại trước khi dùng. Nếu cần cấm lưu trong HTTP cache, hãy kiểm tra `no-store`.
- `max-age=0` khiến phản hồi lập tức hết thời gian còn mới; nó không tương đương với `no-store`.
- Có `Set-Cookie` không tự động chứng minh rằng phản hồi sẽ không được cache. Hãy kiểm tra chính sách cache thực tế.
- Không dựa vào `Pragma: no-cache` hoặc `Expires: 0` như biện pháp thay thế cho `Cache-Control` hiện đại. Chúng có thể xuất hiện để tương thích hệ thống cũ, nhưng cần đánh giá header chính.
- Request header `Cache-Control: no-cache` có thể yêu cầu cache xác thực lại. Nó không chứng minh rằng phản hồi sẽ không được lưu sau lần tải đó.

Với dữ liệu cá nhân hoặc bí mật, một cấu hình thường gặp là:

```http
Cache-Control: private, no-store
```

Với nội dung cá nhân được phép lưu ở trình duyệt nhưng phải kiểm tra quyền và phiên bản mỗi lần sử dụng, có thể cân nhắc:

```http
Cache-Control: private, no-cache
ETag: "profile-version-42"
```

Lựa chọn chính sách phụ thuộc vào độ nhạy cảm, yêu cầu offline và mô hình thiết bị. Không áp dụng một cấu hình cho mọi loại tài nguyên. Tài nguyên tĩnh công khai có tên phiên bản bất biến có thể dùng thời gian cache dài, ví dụ `Cache-Control: public, max-age=31536000, immutable`.

## 3. Cache key, biến thể và xác thực lại

Cache key xác định một yêu cầu có thể dùng lại phản hồi nào. Khóa cơ bản thường dựa trên phương thức và URI đích; cache có thể xét thêm các header được liệt kê trong `Vary`. Cách chuẩn hóa URL và khóa cụ thể có thể khác nhau giữa trình duyệt, reverse proxy và CDN.

Ví dụ, nếu máy chủ trả nội dung khác nhau theo `Accept-Language`, phản hồi nên khai báo:

```http
Vary: Accept-Language
```

Nếu máy chủ phản chiếu origin được phép vào `Access-Control-Allow-Origin`, phản hồi cần khai báo `Vary: Origin` để cache phân biệt các biến thể theo `Origin`:

```http
Access-Control-Allow-Origin: https://client.example.test
Vary: Origin
```

Thiếu `Vary` có thể khiến cache trả header hoặc nội dung của biến thể trước cho yêu cầu có header khác. Ngược lại, thêm quá nhiều header vào `Vary` có thể làm giảm hiệu quả cache. Không nên dùng `Vary: Cookie` như giải pháp duy nhất để cách ly trang cá nhân; với nội dung riêng tư, hãy đặt chính sách `private` hoặc `no-store` phù hợp và xác minh cả cache phía CDN.

`ETag` và `Last-Modified` hỗ trợ xác thực lại:

1. Máy chủ trả nội dung cùng `ETag` hoặc `Last-Modified`.
2. Khi bản sao đã cũ, cache gửi `If-None-Match` hoặc `If-Modified-Since`.
3. Nếu biểu diễn vẫn giống nhau và yêu cầu được phép truy cập, máy chủ có thể trả `304 Not Modified`; trình duyệt dùng phần thân đã lưu.
4. Nếu biểu diễn thay đổi, máy chủ trả nội dung mới, thường với mã `200` và validator mới.

Mã `304` tự nó không phải lỗ hổng. Tuy nhiên, máy chủ vẫn phải kiểm tra xác thực và quyền truy cập trước khi quyết định trả `304`. Không được dùng validator như bằng chứng người gửi có quyền đọc dữ liệu. Khi đổi tài khoản hoặc quyền, phản hồi cũ không được trở thành cách vượt qua kiểm tra truy cập.

## 4. Chuẩn bị môi trường kiểm thử

Thực hiện trong staging hoặc môi trường được phép kiểm thử. Chuẩn bị hai tài khoản thử nghiệm A và B có dữ liệu nhận diện khác nhau, chẳng hạn tên hiển thị và mã hồ sơ giả. Không dùng dữ liệu khách hàng thật.

Mở hai hồ sơ trình duyệt độc lập hoặc hai phiên riêng biệt để so sánh hành vi. Với bài kiểm tra đổi tài khoản trên cùng thiết bị, đăng nhập A, truy cập trang riêng tư, đăng xuất rồi đăng nhập B trong cùng hồ sơ trình duyệt. Ghi lại URL, phương thức, mã trạng thái và các header liên quan. Không đưa cookie phiên hoặc token thật vào ảnh chụp, báo cáo hay lệnh có thể được lưu trong lịch sử terminal.

Trong Chrome hoặc Edge DevTools:

1. Mở tab **Network**, bật **Preserve log** để giữ lịch sử yêu cầu khi điều hướng.
2. Tải trang và chọn request HTML/API cần kiểm tra.
3. Xem **Headers** để ghi lại `Cache-Control`, `Vary`, `ETag`, `Last-Modified`, `Age`, `Date` và các header do CDN cung cấp như `X-Cache` hoặc `CF-Cache-Status` nếu có.
4. Quan sát cột **Size** hoặc thông tin request để nhận biết phản hồi đến từ memory cache, disk cache hay mạng.
5. Mở **Application → Cache Storage** để kiểm tra các cache do Service Worker tạo.

Tùy chọn **Disable cache** trong DevTools làm thay đổi điều kiện thử nghiệm và thường chỉ có hiệu lực khi DevTools đang mở. Không bật tùy chọn này trong phép thử xác nhận cache có tái sử dụng phản hồi hay không. Có thể dùng nó ở một lượt riêng để so sánh đường đi qua mạng.

## 5. Các phép thử bảo mật

### 5.1. Kiểm tra phản hồi riêng tư không lọt vào cache dùng chung

**Mục tiêu:** xác nhận trang hồ sơ, hóa đơn, lịch sử giao dịch hoặc API cá nhân không được CDN/proxy lưu và phân phối cho tài khoản khác.

Thực hiện:

1. Đăng nhập tài khoản A và gọi một URL cá nhân, ví dụ `/account/profile`.
2. Ghi lại nội dung nhận diện của A, `Cache-Control`, `Age`, `X-Cache` hoặc header tương đương.
3. Đăng nhập tài khoản B trong phiên độc lập và gọi đúng URL đó.
4. So sánh nội dung và header. Lặp lại nhiều lần để quan sát trạng thái HIT/MISS nếu hạ tầng có cung cấp.
5. Thực hiện cùng phép thử với các endpoint tải xuống hoặc trả dữ liệu nhạy cảm.

Kết quả mong đợi: B chỉ nhận dữ liệu của B; phản hồi cá nhân có chính sách cache phù hợp, thường là `private` hoặc `no-store`; shared cache không trả bản sao của A. Một header `X-Cache: HIT` không tự động là lỗi nếu tài nguyên được thiết kế công khai, nhưng HIT trên phản hồi cá nhân cần được điều tra ngay.

### 5.2. Kiểm tra đăng xuất và chuyển tài khoản

**Mục tiêu:** phát hiện dữ liệu của phiên trước còn được hiển thị từ cache trình duyệt.

Thực hiện trong cùng một hồ sơ trình duyệt:

1. Đăng nhập A, mở trang có dữ liệu cá nhân và ghi nhận nội dung.
2. Đăng xuất theo luồng chính thức của ứng dụng.
3. Dùng nút Back để quay lại trang vừa xem, sau đó thử tải lại trang.
4. Đăng nhập B và mở cùng URL.
5. Lặp lại bằng một tab mới và bằng cách đóng/mở lại trình duyệt nếu quy trình hỗ trợ.

Kết quả mong đợi: dữ liệu của A không được trình bày như dữ liệu hiện tại của B hoặc người dùng chưa đăng nhập. Nếu trang được khôi phục từ bfcache, ứng dụng cần xử lý trạng thái trang khi được hiển thị lại, kiểm tra phiên/quyền trước khi tiếp tục cho phép thao tác và che dữ liệu nhạy cảm khi cần. Sự kiện `pageshow` có thuộc tính `persisted` giúp nhận biết trang được khôi phục từ bfcache:

```javascript
window.addEventListener("pageshow", (event) => {
  if (event.persisted) {
    // Làm mới trạng thái phiên/quyền trước khi hiển thị dữ liệu nhạy cảm.
    // Có thể che nội dung cho đến khi việc kiểm tra hoàn tất.
  }
});
```

Đừng kết luận bfcache đã được xử lý chỉ vì response có `no-store`; hãy kiểm tra hành vi thực tế trên từng trình duyệt được hỗ trợ.

### 5.3. Kiểm tra xác thực lại bằng ETag

**Mục tiêu:** bảo đảm cache không dùng phản hồi cũ để bỏ qua xác thực hoặc kiểm tra quyền.

Thực hiện:

1. Lấy phản hồi của tài khoản A và ghi lại `ETag`.
2. Gửi lại yêu cầu với `If-None-Match` tương ứng khi phiên A còn hợp lệ; quan sát phản hồi `304` hoặc `200` theo trạng thái dữ liệu.
3. Đăng xuất A hoặc thu hồi quyền của A.
4. Gửi yêu cầu có validator cũ trong trạng thái chưa đăng nhập hoặc bằng tài khoản B.
5. Kiểm tra máy chủ có thực hiện xác thực và phân quyền trước khi trả `304` hay không.

Ví dụ dùng cookie phiên giả lập; thay bằng cơ chế xác thực thử nghiệm của môi trường staging. Không dùng cookie thật trong lệnh có thể được lưu hoặc chia sẻ:

```bash
curl -i \
  -H 'Cookie: session=TEST_SESSION_A' \
  -H 'If-None-Match: "profile-version-42"' \
  https://app.example.test/account/profile
```

Kết quả mong đợi: yêu cầu không có quyền nhận phản hồi từ chối phù hợp, chẳng hạn `401` hoặc `403` theo thiết kế. Không được trả `304` khiến trình duyệt tái sử dụng nội dung riêng tư mà người dùng hiện tại không còn quyền xem. Nếu nội dung thực sự giống nhau và người gọi vẫn có quyền, `304` có thể là kết quả hợp lệ.

### 5.4. Kiểm tra `Vary` và các biến thể phản hồi

**Mục tiêu:** xác nhận cache phân biệt các phản hồi phụ thuộc vào header yêu cầu.

Thực hiện hai yêu cầu đến cùng URL nhưng dùng các giá trị `Accept-Language` khác nhau, hoặc hai `Origin` hợp lệ khác nhau với endpoint CORS phản chiếu origin. Ghi lại nội dung, `Content-Language`, `Access-Control-Allow-Origin` và `Vary`.

Ví dụ:

```bash
curl -i -H 'Accept-Language: vi' https://app.example.test/help
curl -i -H 'Accept-Language: en' https://app.example.test/help
```

Kết quả mong đợi: mỗi yêu cầu nhận đúng biến thể. Nếu nội dung hoặc header thay đổi theo một request header, phản hồi cacheable phải khai báo `Vary` tương ứng hoặc dùng chính sách không cache phù hợp. Kiểm tra cả chiều ngược lại: yêu cầu tiếng Việt sau yêu cầu tiếng Anh không được nhận bản tiếng Anh do cache tái sử dụng sai biến thể.

### 5.5. Kiểm tra cache poisoning

**Mục tiêu:** tìm trường hợp đầu vào của request làm thay đổi phản hồi nhưng không được tính vào cache key.

Một tình huống thường gặp là ứng dụng dựng URL tuyệt đối, liên kết hoặc nội dung phản hồi từ header `Host` hay `X-Forwarded-Host`, trong khi CDN chỉ dùng URL chuẩn làm cache key. Nếu phản hồi bị lưu, yêu cầu sau có thể nhận nội dung được tạo từ header của yêu cầu trước.

Trong staging, dùng một header thử nghiệm không chứa payload nguy hiểm và kiểm tra:

1. Header nào làm thay đổi nội dung hoặc header của phản hồi?
2. Cache key ở CDN/proxy có phân biệt giá trị header đó không?
3. Sau khi gửi yêu cầu với giá trị thử nghiệm A, yêu cầu chuẩn tiếp theo có nhận lại phản hồi bị ảnh hưởng không?
4. Thay đổi query string, thứ tự tham số, chữ hoa/thường, dấu gạch chéo cuối hoặc cách mã hóa URL có tạo ra khóa cache ngoài dự kiến không?

Kết quả mong đợi: ứng dụng chỉ tin cậy host/proxy đã cấu hình, chuẩn hóa URL nhất quán và không cache phản hồi bị ảnh hưởng bởi header không được đưa vào cache key. Không thử nghiệm đầu độc cache trên hệ thống production hoặc cache dùng chung của người khác.

### 5.6. Kiểm tra Cache API của Service Worker

**Mục tiêu:** xác nhận ứng dụng chỉ ghi tài nguyên được phép vào Cache Storage và không lưu API cá nhân ngoài ý muốn.

Trong DevTools, mở **Application → Cache Storage**, xem tên cache và danh sách request. Có thể liệt kê các mục trong Console của trang cùng origin bằng đoạn mã sau; chỉ chạy trong môi trường thử nghiệm vì URL có thể chứa thông tin nhạy cảm:

```javascript
async function listCacheEntries() {
  const names = await caches.keys();
  const rows = [];

  for (const name of names) {
    const cache = await caches.open(name);
    const requests = await cache.keys();

    for (const request of requests) {
      rows.push({
        cache: name,
        method: request.method,
        url: request.url,
      });
    }
  }

  console.table(rows);
}

listCacheEntries();
```

Kiểm tra các câu hỏi sau:

- Có endpoint như `/api/me`, `/account`, `/orders` hoặc URL chứa mã định danh cá nhân trong Cache Storage không?
- Cache có phân biệt phiên người dùng không, và có bị tái sử dụng sau khi đăng xuất/đăng nhập tài khoản khác không?
- Khi dữ liệu thay đổi hoặc người dùng đăng xuất, ứng dụng có xóa các mục liên quan theo đúng chính sách không?
- Luồng offline có trả dữ liệu cá nhân cũ mà không kiểm tra trạng thái phiên không?
- Mã Service Worker có xử lý đúng query string và `Vary` không? Các tùy chọn `ignoreSearch`, `ignoreMethod`, `ignoreVary` của `Cache.match()` có thể làm thay đổi cách khớp request.

Cache API không tự hết hạn mục theo `Cache-Control` và ứng dụng phải tự quản lý vòng đời cache. Vì vậy, cần đọc cả logic `cache.put()`, `cache.match()`, `cache.delete()` và quy trình nâng phiên bản cache trong Service Worker.

Ví dụ dưới đây chỉ minh họa chiến lược cache-first cho thư mục tài nguyên tĩnh công khai đã được dành riêng. Không mở rộng điều kiện này sang API hoặc đường dẫn chứa nội dung cá nhân:

```javascript
self.addEventListener("fetch", (event) => {
  const request = event.request;
  const url = new URL(request.url);

  if (request.method !== "GET" || url.origin !== self.location.origin) {
    return;
  }

  // /assets/ chỉ chứa tài nguyên tĩnh công khai có phiên bản.
  if (!url.pathname.startsWith("/assets/")) {
    return;
  }

  event.respondWith((async () => {
    const cache = await caches.open("public-assets-v1");
    const cached = await cache.match(request);
    if (cached) return cached;

    const response = await fetch(request);
    if (response.ok && response.type === "basic") {
      await cache.put(request, response.clone());
    }
    return response;
  })());
});
```

Khi áp dụng mẫu, phải bảo đảm `/assets/` thực sự chỉ phục vụ nội dung công khai và có chiến lược đổi tên/xóa cache khi phát hành phiên bản mới. Việc giới hạn theo đường dẫn chỉ an toàn khi quy ước nội dung của đường dẫn đó được kiểm soát.

### 5.7. Kiểm tra cache của trình duyệt và shared cache bằng `curl`

`curl` hữu ích để xem header HTTP mà không phụ thuộc giao diện trình duyệt. Ví dụ sau chỉ gửi yêu cầu đến máy chủ thử nghiệm:

```bash
curl -sS -D - -o /dev/null https://app.example.test/public/catalog
```

Đọc các header `Cache-Control`, `Age`, `Date`, `ETag`, `Vary` và header trạng thái cache của hạ tầng. Gửi lại yêu cầu để xem `Age` tăng hoặc trạng thái chuyển từ MISS sang HIT nếu cache có bật.

Để kiểm tra phản hồi có yêu cầu xác thực, dùng tài khoản thử nghiệm và cookie phiên tạm thời trong môi trường riêng. Không sao chép cookie thật vào báo cáo hoặc lệnh được chia sẻ:

```bash
curl -i \
  -H 'Cookie: session=TEST_SESSION_A' \
  https://app.example.test/account/profile
```

Thực hiện lại bằng phiên B với cùng URL. Kết quả mong đợi là dữ liệu của mỗi tài khoản được giữ riêng và shared cache không phân phối nhầm phản hồi. Nếu cần kiểm tra việc tái xác thực, thêm `Cache-Control: no-cache` vào request để yêu cầu cache xác thực lại, rồi đối chiếu với lần gọi thông thường.

## 6. Ma trận kết quả mong đợi

| Phép thử | Kết quả đạt |
|---|---|
| Tài khoản A rồi tài khoản B gọi cùng URL cá nhân | B chỉ nhận dữ liệu B; không có HIT dùng chung dữ liệu A |
| Đăng xuất rồi nhấn Back | Nội dung nhạy cảm không được tiếp tục sử dụng như phiên hợp lệ; trạng thái phiên được kiểm tra lại |
| Gửi validator cũ sau khi mất quyền | Máy chủ xác thực và phân quyền trước; không trả `304` để tái sử dụng nội dung không còn được phép xem |
| Thay đổi header có trong `Vary` | Cache trả đúng biến thể theo header |
| Header không tin cậy làm thay đổi phản hồi | Phản hồi không bị lưu và phân phối chéo ngoài dự kiến |
| Kiểm tra Cache Storage | Không có dữ liệu cá nhân được lưu ngoài chính sách; mục cache được xóa hoặc làm mới đúng lúc |
| Tải lại tài nguyên công khai có phiên bản | Có thể nhận HIT trong thời gian còn mới; nội dung vẫn đúng phiên bản |

## 7. Phân tích lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng điều tra |
|---|---|---|
| Người dùng B nhìn thấy dữ liệu A | Shared cache lưu phản hồi cá nhân; cache key thiếu yếu tố phân biệt; Service Worker dùng lại cache chung | Kiểm tra `Cache-Control`, `Vary`, trạng thái CDN và Cache Storage; tái hiện với hai tài khoản |
| Trang cũ xuất hiện sau đăng xuất | HTTP cache hoặc bfcache khôi phục tài liệu; ứng dụng chưa kiểm tra lại phiên khi trang được hiển thị | Phân biệt nguồn phản hồi trong Network; kiểm tra sự kiện `pageshow` và luồng đăng xuất |
| API trả dữ liệu cũ dù máy chủ đã cập nhật | `max-age` quá dài; validator không đổi đúng; Cache API không được làm mới | Kiểm tra `Age`, `ETag`, `Last-Modified` và logic Service Worker |
| Nội dung ngôn ngữ hoặc CORS bị trộn | Thiếu hoặc sai `Vary` | So sánh phản hồi khi thay `Accept-Language` hoặc `Origin` |
| Bản cache thay đổi theo header lạ | Ứng dụng tin cậy header proxy không đúng hoặc cache key không xét header đó | Xác định header ảnh hưởng phản hồi, sau đó kiểm tra cấu hình proxy và cache key |
| DevTools không tái hiện được HIT | Đang bật Disable cache, request bị bypass, hoặc cache đã hết hạn | Đóng tùy chọn Disable cache, kiểm tra lại trong phiên mới và ghi nhận điều kiện thử |

Không kết luận có rò rỉ chỉ từ một header `HIT`, `MISS` hoặc `304`. Cần đối chiếu nội dung trả về, danh tính tài khoản, trạng thái xác thực, cache key và đường đi thực tế của request. Tương tự, không kết luận an toàn chỉ vì một lần tải trang trả `200` từ mạng; phải kiểm tra cả lần tái sử dụng cache và điều kiện đổi phiên.

## 8. Quy trình ghi nhận bằng chứng

Với mỗi phát hiện, ghi lại:

1. Môi trường, trình duyệt và phiên bản; loại cache đang kiểm tra.
2. Tài khoản thử nghiệm, trạng thái đăng nhập và bước tái hiện.
3. URL, phương thức, các request header liên quan và mã trạng thái.
4. Response header quan trọng: `Cache-Control`, `Vary`, `ETag`, `Age` và header trạng thái CDN nếu có.
5. Nguồn phản hồi: mạng, memory cache, disk cache, Cache Storage hay bfcache.
6. Nội dung nhận được có đúng người dùng và đúng phiên hay không. Dùng dữ liệu giả và che token, cookie, thông tin cá nhân khỏi bằng chứng.
7. Kết quả mong đợi, kết quả thực tế, mức độ ảnh hưởng và điều kiện cần để tái hiện.

Một phép thử chỉ được đánh dấu đạt khi đã kiểm tra cả đường đi bình thường lẫn tình huống đổi phiên, hết hạn hoặc mất quyền có liên quan. Với nội dung cá nhân, phải có bằng chứng cho thấy tài khoản khác không thể nhận hoặc tiếp tục sử dụng bản sao cũ.

## 9. Checklist hoàn tất

- [ ] Đã phân loại HTTP cache, shared cache, Cache API và bfcache.
- [ ] Đã xác nhận chính sách `Cache-Control` phù hợp với từng nhóm nội dung.
- [ ] Đã thử cùng URL bằng hai tài khoản và kiểm tra khả năng rò rỉ chéo.
- [ ] Đã thử đăng xuất, đăng nhập lại và điều hướng Back/Forward.
- [ ] Đã kiểm tra xác thực lại bằng `ETag` hoặc `Last-Modified` khi có sử dụng validator.
- [ ] Đã kiểm tra `Vary` cho các header làm thay đổi biểu diễn.
- [ ] Đã rà soát Cache Storage và luồng offline của Service Worker.
- [ ] Đã kiểm tra header ảnh hưởng phản hồi và khả năng cache poisoning trong staging.
- [ ] Đã lưu bằng chứng đã loại bỏ cookie, token và dữ liệu cá nhân.

Kiểm thử cache hoàn tất khi mỗi loại cache có chính sách rõ ràng, phản hồi công khai có thể được tái sử dụng đúng cách, và dữ liệu riêng tư luôn được bảo vệ qua các tình huống tải lại, đổi tài khoản, đăng xuất, hết hạn và thu hồi quyền.
