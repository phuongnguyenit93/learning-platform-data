# Recovery page cache policy

## 1. Cache policy bảo vệ điều gì trong luồng khôi phục?

Trang khôi phục tài khoản có thể chứa email được che một phần, trạng thái xác minh, token chống CSRF, thông tin thiết bị hoặc hướng dẫn dành riêng cho một lần recovery. Các dữ liệu này cần xuất hiện đúng người, đúng thời điểm và đúng bước.

Ví dụ:

1. Người dùng A mở biểu mẫu khôi phục MFA trên máy dùng chung.
2. A hoàn tất thao tác và rời trang.
3. Người dùng B mở lại cùng URL hoặc bấm Back.
4. Một bản sao cũ có thể làm B thấy thông tin của A hoặc một giao diện có vẻ vẫn còn quyền tiếp tục.

Một tình huống khác xảy ra khi CDN lưu HTML theo đường dẫn nhưng bỏ qua query và cookie: response dành cho một lần khôi phục có thể được phục vụ cho người khác.

**Recovery page cache policy** là thiết kế quyết định dữ liệu recovery được lưu ở đâu, được tái sử dụng khi nào và cách ứng dụng xử lý bản hiển thị đã cũ. Nó cần phối hợp với việc kiểm tra quyền tại server. Không có chính sách cache nào tự biến một token hết hạn thành hợp lệ.

Các URL, cookie và giá trị trong bài chỉ để minh họa.

## 2. Có nhiều lớp giữ lại nội dung

Không nên dùng từ “cache trình duyệt” để chỉ mọi bản sao.

| Lớp | Nội dung có thể được giữ | Quyết định thiết kế |
| --- | --- | --- |
| HTTP cache trong trình duyệt | Response HTML, JSON, tài nguyên | Áp dụng chính sách HTTP phù hợp từng response |
| Shared cache tại proxy hoặc CDN | Response phục vụ nhiều client | Bypass lưu và đọc cache cho các route recovery nhạy cảm |
| Service Worker Cache API | Request/response do mã ứng dụng lưu | Loại recovery khỏi chiến lược cache và offline fallback |
| Back/forward cache, gọi tắt bfcache | Trạng thái trang khi điều hướng lịch sử | Xử lý việc trang được phục hồi với trạng thái cũ |
| Bộ nhớ và lưu trữ ứng dụng | State trong JavaScript, localStorage, IndexedDB | Không tự lưu bí mật hoặc biểu mẫu recovery để phục hồi tiện lợi |

Một response đi qua CDN trước khi đến trình duyệt. Nếu CDN đã trả bản sao sai, header mà origin dự định gửi ở request mới chưa chắc đã có cơ hội đến client.

Ngược lại, response đã có header đúng vẫn có thể bị mã ứng dụng chủ động lưu vào một cơ chế khác. Vì thế, cần xác định từng lớp chịu trách nhiệm thay vì chỉ thêm một header rồi coi toàn bộ vấn đề đã được giải quyết.

## 3. Phân biệt các chỉ thị HTTP thường gặp

Với response, các chỉ thị sau có ý nghĩa khác nhau:

| Chỉ thị | Ý nghĩa chính |
| --- | --- |
| `no-store` | Không lưu response để tái sử dụng trong HTTP cache |
| `no-cache` | Phải xác thực lại trước khi tái sử dụng bản lưu |
| `private` | Shared cache không lưu; private cache vẫn có thể lưu |
| `max-age=0` | Thời gian freshness bằng không |
| `must-revalidate` | Bản stale phải được xác thực lại trước khi dùng |

Đây là các khái niệm trong [RFC 9111 về HTTP Caching](https://www.rfc-editor.org/rfc/rfc9111.html#name-response-directives).

Ví dụ, `private, no-cache` có thể phù hợp cho một số trang cá nhân cần xác thực lại, nhưng vẫn không diễn đạt mục tiêu “không lưu response recovery nhạy cảm”. Bài này chọn `no-store` cho nhóm response đó.

```http
HTTP/1.1 200 OK
Content-Type: text/html; charset=UTF-8
Cache-Control: no-store
```

`no-cache` không đồng nghĩa “không có cache”. `private` không đồng nghĩa “người dùng khác trên cùng máy không thể nhìn thấy”. Tên chỉ thị cần được đọc theo cơ chế lưu và tái sử dụng, không theo nghĩa đời thường của từ.

Không cần ghép mọi chỉ thị vào một chuỗi dài để tạo cảm giác mạnh hơn. Các header như `Pragma` hoặc thời điểm `Expires` trong quá khứ không thay thế mục tiêu của `no-store`.

## 4. Chính sách mặc định cho vùng recovery

Thiết kế minh họa sử dụng quy tắc sau:

> Mọi response chứa dữ liệu hoặc trạng thái của một lần khôi phục đều nhận `Cache-Control: no-store`.

[OWASP HTTP Headers Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/HTTP_Headers_Cheat_Sheet.html#cache-control) cũng nêu `no-store` để tránh lưu response chứa thông tin nhạy cảm.

Phạm vi nên dựa vào dữ liệu và route, không chỉ dựa vào HTTP status:

| Response | Chính sách trong thiết kế |
| --- | --- |
| Trang tiếp nhận liên kết có token | `no-store` |
| Biểu mẫu đặt lại mật khẩu | `no-store` |
| Trang xác minh mất MFA hoặc passkey | `no-store` |
| JSON mô tả bước recovery đang được phép | `no-store` |
| Redirect sau khi đổi token lấy phiên giới hạn | `no-store` |
| Thông báo token hết hạn, đã dùng hoặc không hợp lệ | `no-store` |
| Kết quả hoàn tất hay hủy một lần recovery | `no-store` |
| JavaScript/CSS chung có tên theo nội dung, không cá nhân hóa | Có thể dùng chính sách cache tài nguyên tĩnh riêng |

Một trang lỗi không trở thành dữ liệu công khai chỉ vì trả `400`, `404` hoặc `410`. Nó vẫn có thể chứa thông tin từ request hoặc trạng thái recovery.

Cũng không nên suy ra rằng POST làm mọi response tự an toàn khỏi lưu trữ. Quy tắc của vùng recovery phải áp dụng độc lập với giả định đó.

Nếu HTML chỉ là khung tĩnh hoàn toàn không chứa dữ liệu người dùng, có thể thiết kế cache riêng cho khung. Khi đó, dữ liệu recovery phải được lấy qua endpoint không lưu cache, và giao diện chưa được coi là có quyền tiếp tục trước khi nhận trạng thái hợp lệ từ server. Với nhiều ứng dụng, dùng `no-store` cho toàn bộ HTML recovery giúp giảm số ngoại lệ phải quản lý.

## 5. Gắn chính sách trước các nhánh xử lý

Nếu chỉ đặt header trong nhánh thành công, các nhánh lỗi hoặc middleware chuyển hướng có thể bỏ sót chính sách.

Pseudocode cho một pipeline phục vụ recovery:

```text
if request belongs to sensitive recovery routes:
    mark response as no-store before rendering or handling errors
    bypass application response cache

execute route logic

if an error response or redirect replaces the original response:
    preserve the recovery no-store policy

send response
```

Đây là mô hình trách nhiệm, không phải đoạn cấu hình dùng nguyên xi cho mọi framework. Nơi triển khai có thể là filter, middleware hoặc lớp tạo response, miễn chính sách đi theo response cuối cùng.

Ví dụ redirect sau một POST hợp lệ:

```http
HTTP/1.1 303 See Other
Location: /recovery/continue
Cache-Control: no-store
Referrer-Policy: no-referrer
Set-Cookie: recovery_session=DEMO_NOT_VALID; Path=/recovery; Secure; HttpOnly; SameSite=Lax
```

Trang ở `/recovery/continue` cũng phải có chính sách của chính nó. Header trên redirect không thay thế header cho response đích. Các API ngoài đường dẫn cookie cần thiết kế phiên và phạm vi cookie phù hợp; ví dụ trên không cấp phiên recovery cho toàn bộ ứng dụng.

`Referrer-Policy` xử lý thông tin nguồn của request tiếp theo. Nó là lớp bảo vệ khác với cache policy, dù cả hai thường xuất hiện trên trang mang token.

Với response nhạy cảm, thiết kế không cần tối ưu bằng validator `ETag` hay `Last-Modified`. Nếu ứng dụng chủ động hỗ trợ conditional request, không được để một nhánh trả `304` bỏ qua việc kiểm tra phiên hoặc quyền recovery hiện tại. `304` gắn với tái sử dụng một biểu diễn đã lưu, không phải thông báo “người dùng đã được xác thực”.

## 6. Shared cache: không biến URL thành ranh giới người dùng

Xét cấu hình nguy hiểm:

```text
Origin response:
  /recovery/form?token=TOKEN_A
  contains masked address and recovery form state

CDN cache key:
  hostname + pathname
  query and cookies are ignored
```

Nếu response bị lưu, request với `TOKEN_B` có thể gặp nội dung của `TOKEN_A`. Đây là rò dữ liệu ngay cả khi backend vẫn từ chối mọi thao tác không có quyền.

Hướng thiết kế cho vùng recovery:

- Định nghĩa route nhạy cảm trên cùng cách chuẩn hóa URL mà ứng dụng sử dụng.
- Bypass cả đọc bản cache hiện có và ghi response mới tại CDN/proxy.
- Giữ header từ origin; tránh rule “cache mọi HTML” ghi đè chính sách.
- Không phục vụ bản stale của response recovery khi origin lỗi hoặc mất kết nối.
- Bao phủ cả đường dẫn đã rewrite, các phiên bản ngôn ngữ và endpoint API liên quan.

Chỉ thêm cookie vào cache key không đạt cùng mục tiêu với việc không lưu nội dung nhạy cảm. Nó còn tạo nhiều biến thể dữ liệu cá nhân trong shared cache. `Vary: Cookie` cũng không thay cho quyết định không lưu.

Khi có `Set-Cookie`, không nên mặc nhiên coi toàn bộ hạ tầng sẽ bỏ qua cache. Cấu hình thực tế của các lớp trung gian vẫn cần tuân theo chính sách route.

Tài nguyên tĩnh không cá nhân hóa có thể tiếp tục được cache. Không để HTML recovery nhạy cảm dùng chung rule chỉ vì đường dẫn của nó có phần mở rộng giống một tài nguyên tĩnh.

## 7. Service Worker cần quyết định riêng

Theo [tài liệu chính thức về chiến lược cache của Service Worker](https://developer.chrome.com/docs/workbox/caching-strategies-overview/#the_cache_interface_versus_the_http_cache), Cache API tách biệt với HTTP cache. `Cache-Control` không quyết định những gì mã ứng dụng chủ động đưa vào Cache API.

Vì vậy, các thao tác sau không phù hợp với response recovery nhạy cảm:

```javascript
// Ví dụ điều cần tránh: chủ động giữ một response recovery.
await cache.put(request, recoveryResponse.clone());
```

Thiết kế phù hợp hơn là định tuyến recovery tới mạng và không có fallback chứa dữ liệu cũ. Ví dụ dưới đây là một nhánh trong router Service Worker duy nhất của ứng dụng:

```javascript
self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  const isRecovery =
    url.origin === self.location.origin &&
    (
      url.pathname === "/recovery" ||
      url.pathname.startsWith("/recovery/") ||
      url.pathname === "/api/recovery" ||
      url.pathname.startsWith("/api/recovery/")
    );

  if (isRecovery) {
    event.respondWith(
      fetch(event.request, { cache: "no-store" }).catch(() =>
        new Response("Can ket noi mang de tiep tuc khoi phuc.", {
          status: 503,
          headers: {
            "Content-Type": "text/plain; charset=UTF-8",
            "Cache-Control": "no-store"
          }
        })
      )
    );
    return;
  }

  // Các chiến lược cho route khác thuộc router của ứng dụng.
});
```

Phạm vi đường dẫn trong ví dụ cần được thay bằng mapping thật, bao gồm route theo ngôn ngữ hoặc route sau rewrite. Nhánh này phải được tích hợp vào luồng định tuyến chính; không chỉ thêm một listener rồi để nhánh cache tổng quát khác vẫn xử lý cùng dữ liệu.

Chế độ `cache: "no-store"` ở fetch điều khiển việc dùng HTTP cache cho request đó. Nó không xóa các bản đã bị mã cũ lưu trong Cache API, cũng không thay cho response header từ server hoặc rule bypass của CDN.

Không đưa các URL token vào danh sách precache. Không đồng bộ lại offline một POST đổi mật khẩu, gỡ MFA hoặc đăng ký passkey chỉ vì thư viện có tính năng background sync: lúc phát lại, quyền và ngữ cảnh có thể đã đổi.

## 8. Back/forward cache không phải HTTP cache

Bfcache có thể giữ một trang đã tải cùng trạng thái của nó để phục hồi nhanh khi người dùng Back hoặc Forward. Một biểu mẫu cũ có thể trở lại mà không tương đương việc tải một response mới từ server.

Không khẳng định `Cache-Control: no-store` luôn ngăn bfcache trên mọi trình duyệt. [Tài liệu Chrome về no-store và bfcache](https://developer.chrome.com/docs/web-platform/bfcache-ccns) mô tả việc cho phép một số trang `no-store` vào bfcache với các điều kiện riêng. Hành vi này khác với HTTP cache và có thể thay đổi theo trình duyệt.

Thiết kế giao diện recovery nên coi việc trang được phục hồi là thời điểm trạng thái có thể đã cũ:

1. Vô hiệu hóa thao tác nhạy cảm trong lúc đồng bộ trạng thái.
2. Yêu cầu server xác nhận phiên còn hạn và bước hiện tại.
3. Nếu quyền đã hết hoặc thao tác đã hoàn tất, chuyển sang thông báo trung tính.
4. Chỉ mở thao tác phù hợp với trạng thái mới được xác nhận.
5. Nếu mất mạng, không cho phép dựa vào dữ liệu cũ để tiếp tục.

Sự kiện `pageshow` và thuộc tính `persisted` hỗ trợ nhận biết việc phục hồi; xem [hướng dẫn bfcache của web.dev](https://web.dev/articles/bfcache#observe_when_a_page_is_restored_from_bfcache). Ứng dụng cũng có thể cần đồng bộ khi tab quay lại sau thời gian dài, kể cả khi không có sự kiện phục hồi bfcache.

Việc ẩn hoặc xóa dữ liệu nhạy cảm khỏi giao diện trước khi rời trang giúp giảm nguy cơ hiển thị lại. Tuy nhiên, callback vòng đời không được bảo đảm chạy trong mọi tình huống kết thúc tiến trình. Không hứa rằng một handler phía client sẽ xóa hết ảnh chụp trạng thái hoặc mọi dấu vết trên thiết bị.

## 9. Server vẫn là nơi quyết định quyền

Một biểu mẫu được phục hồi có thể còn hiện nút “Tiếp tục” dù token đã dùng. Điều đó là vấn đề giao diện; nó chỉ trở thành khả năng thực hiện trái phép nếu server tin trạng thái cũ từ client.

Mỗi thao tác thay đổi tài khoản cần xác minh lại:

- Phiên recovery còn hiệu lực và chưa bị thu hồi.
- Phiên gắn với đúng tài khoản và mục đích.
- Bước xác minh cần thiết đã hoàn tất.
- Token hoặc quyền một lần chưa được tiêu thụ.
- Request đạt các yêu cầu chống CSRF và chống lạm dụng tương ứng.

Chuyển trạng thái cần nguyên tử để hai tab hoặc hai request đồng thời không dùng lại quyền một lần. Ví dụ:

```text
state before:
  recovery session allows password reset

on valid final submission:
  atomically consume reset permission and update password

state after:
  same session cannot submit another reset
  stale browser form receives an unavailable/expired outcome
```

Khôi phục mật khẩu, gỡ MFA và đăng ký passkey là những mục đích khác nhau. Việc lấy được một biểu mẫu cũ hoặc một phiên chỉ dành cho mật khẩu không cấp quyền thay các yếu tố xác thực khác.

Kết quả hoàn tất cũng không nên trở thành bản sao cache chứa bí mật mới. Ví dụ, không đưa mã khôi phục vừa cấp vào URL để trang thành công có thể được mở lại tùy ý.

## 10. Khi đã từng cache sai trước đó

Thêm header mới bảo vệ các response nhận chính sách mới; nó không phải lệnh thu hồi mọi bản sao từng tồn tại.

Một kế hoạch khắc phục có thể gồm:

| Nơi từng lưu dữ liệu | Cách xử lý có phạm vi |
| --- | --- |
| CDN hoặc reverse proxy | Bypass route và vô hiệu hóa các bản cache liên quan |
| Cache API của phiên bản Service Worker cũ | Migration xóa đúng cache/key recovery đã biết |
| State hoặc storage do ứng dụng tự tạo | Dừng ghi và xóa đúng dữ liệu recovery thuộc phạm vi sửa |
| HTTP cache hoặc lịch sử trên thiết bị người dùng | Giảm dữ liệu còn giá trị, thu hồi quyền nếu cần; không giả định có thể xóa từ xa toàn bộ |
| Phiên recovery tạo từ token có khả năng lộ | Xử lý theo phạm vi sự cố và quyền đã cấp |

Không xóa toàn bộ dữ liệu của origin một cách mặc định chỉ để xử lý một route. Hành động đó có thể ảnh hưởng tài khoản đang dùng, dữ liệu offline hợp lệ hoặc ứng dụng khác cùng origin. Cần hiểu chính xác phạm vi trước khi dùng cơ chế dọn dữ liệu rộng.

Nếu bản cache chứa token còn hiệu lực hoặc dữ liệu đủ để tiếp tục recovery, cần xem xét thu hồi token và phiên liên quan. Nếu chỉ có thông tin hiển thị, vẫn phải đánh giá rò dữ liệu nhưng không nên suy luận ngay rằng mọi tài khoản đã bị chiếm đoạt.

Mục tiêu khắc phục gồm cả ngừng tạo bản sao mới và giảm giá trị của bản sao đã có.

## 11. Những giới hạn cần hiểu rõ

| Nhận định sai | Cách hiểu phù hợp |
| --- | --- |
| `no-cache` cấm lưu response | Nó yêu cầu xác thực lại trước khi dùng bản lưu |
| `private` ngăn người dùng sau trên cùng máy xem lại | Nó phân biệt shared cache với private cache |
| Có `no-store` thì Back luôn tải lại từ mạng | Bfcache và lịch sử có cơ chế riêng |
| Response có cookie thì CDN chắc chắn không lưu | Cần chính sách route và cấu hình trung gian phù hợp |
| Tắt cache ở client là đủ | Origin, shared cache và mã ứng dụng đều có trách nhiệm |
| Cache policy làm token không thể bị lộ | Log, referrer, mã trang và nội dung chia sẻ là các đường khác |
| Giao diện vẫn hiện biểu mẫu nghĩa là quyền còn hiệu lực | Server phải xác định quyền hiện tại ở mỗi thao tác |

Chính sách trong bài giữ response recovery nhạy cảm ngoài HTTP cache, loại chúng khỏi cache do ứng dụng điều khiển, và xử lý giao diện phục hồi như một trạng thái có thể đã cũ. Quyền thay đổi tài khoản luôn được quyết định từ trạng thái hiện hành phía server.
