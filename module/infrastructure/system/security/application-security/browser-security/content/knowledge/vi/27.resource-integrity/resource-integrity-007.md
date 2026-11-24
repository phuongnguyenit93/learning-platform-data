# Integrity failure: chẩn đoán và xử lý khi kiểm tra toàn vẹn tài nguyên thất bại

## 1. Integrity failure là gì?

Một trang web thường tải JavaScript, CSS, font và các tài nguyên khác từ ứng dụng, CDN hoặc nhà cung cấp bên ngoài. Nếu nội dung của một tài nguyên thay đổi ngoài dự kiến, browser có thể nhận được mã khác với phiên bản mà ứng dụng đã kiểm tra và phê duyệt.

**Integrity failure** xảy ra khi cơ chế kiểm tra tính toàn vẹn không xác nhận được tài nguyên nhận về đúng với nội dung mong đợi. Với Subresource Integrity (SRI), browser tính digest của tài nguyên rồi so sánh với hash được khai báo trong HTML. Nếu không có digest hợp lệ khớp, browser chặn việc sử dụng tài nguyên đó.

Ví dụ, trang khai báo một script từ CDN với `integrity="sha384-..."`. CDN bị thay nội dung, cache trả về một bản build khác hoặc quá trình deploy cập nhật file mà quên cập nhật hash trong HTML. Browser phát hiện digest không khớp và không thực thi script.

Điều này có thể là dấu hiệu của sự cố bảo mật, chẳng hạn CDN hoặc đường phân phối bị can thiệp. Nó cũng có thể đến từ lỗi phát hành bình thường: hash cũ, cache stale, minifier thay đổi output, asset chưa đồng bộ giữa các edge hoặc CORS cấu hình sai.

Không nên tắt SRI hay xóa thuộc tính `integrity` chỉ để trang tải lại được. Hãy xác định chính xác tài nguyên, response thực tế và nguồn tạo hash trước khi cập nhật metadata.

Trong module bảo mật trình duyệt, integrity failure liên quan đến SRI, CORS, CSP, CDN, TLS, cache và quy trình phát hành frontend. Bài học này tập trung vào cách browser xử lý lỗi, phân biệt lỗi digest với lỗi tải tài nguyên, và khôi phục ứng dụng an toàn.

Sau bài học, bạn có thể:

- Giải thích cách browser kiểm tra SRI và chặn tài nguyên không khớp.
- Phân biệt integrity mismatch, CORS failure, network failure và metadata không hợp lệ.
- Tạo hash SHA-384 từ đúng artifact được phát hành.
- Cấu hình `integrity` và `crossorigin` cho script/style cross-origin.
- Chẩn đoán lỗi bằng DevTools, curl và OpenSSL.
- Triển khai fallback có kiểm soát và xử lý cache/deploy không đồng bộ.
- Thiết kế CI/CD để cập nhật asset và integrity metadata nhất quán.

## 2. Vì sao cần kiểm tra tính toàn vẹn tài nguyên?

HTTPS bảo vệ dữ liệu trên đường truyền và xác thực server theo certificate. Tuy nhiên, một trang có thể chủ động tải script từ một CDN hoặc nhà cung cấp bên thứ ba. Nếu tài khoản CDN bị chiếm, bucket public bị ghi đè hoặc pipeline của nhà cung cấp phát hành nhầm file, browser vẫn có thể tải nội dung hợp lệ về mặt TLS từ đúng hostname nhưng nội dung không còn là bản mà ứng dụng đã phê duyệt.

SRI giúp trang ràng buộc tài nguyên với một nội dung cụ thể bằng cryptographic hash. Khi hash được lưu trong HTML đáng tin cậy, browser có thể phát hiện file khác với bản đã được duyệt.

Ví dụ:

```html
<script
  src="https://cdn.example.net/libs/widget-4.2.1.min.js"
  integrity="sha384-BASE64_DIGEST"
  crossorigin="anonymous"></script>
```

Nếu response body không khớp digest đã khai báo, browser không thực thi script đó.

### 2.1 SRI bảo vệ điều gì?

SRI phù hợp để kiểm tra một số tài nguyên được tham chiếu tĩnh từ HTML, đặc biệt là:

- External JavaScript qua phần tử `script`.
- Stylesheet qua phần tử `link` với `rel="stylesheet"`.
- Các trường hợp sử dụng Fetch API có tùy chọn `integrity`, khi browser hỗ trợ và request phù hợp.

SRI giúp phát hiện tài nguyên bị thay đổi so với hash đã pin. Nó đặc biệt hữu ích khi tải thư viện từ CDN hoặc host do bên thứ ba vận hành.

### 2.2 SRI không bảo vệ điều gì?

SRI không:

- Xác minh HTML chứa thuộc tính `integrity` có đáng tin hay không.
- Ngăn attacker thay cả HTML lẫn hash nếu họ kiểm soát được trang.
- Thay thế TLS, CSP, CORS, authentication hoặc authorization.
- Chứng minh thư viện đã pin là an toàn về mặt chức năng.
- Tự kiểm tra mọi script được tải động hoặc mọi dependency bên trong ứng dụng.
- Bảo đảm tài nguyên luôn sẵn sàng; hash đúng không ngăn lỗi mạng hoặc CDN outage.

Nếu attacker kiểm soát HTML, họ có thể thay URL và digest cùng lúc. Vì vậy, cần bảo vệ HTML, pipeline phát hành, quyền quản trị CDN và nguồn tạo integrity metadata.

## 3. Browser kiểm tra SRI như thế nào?

Ở mức khái quát, browser thực hiện các bước:

1. Đọc URL và giá trị `integrity` từ phần tử `script` hoặc `link`.
2. Thực hiện request theo chế độ phù hợp, bao gồm kiểm tra CORS khi tài nguyên nằm ở origin khác.
3. Nhận response và tính digest trên nội dung tài nguyên.
4. So sánh digest thực tế với metadata được khai báo.
5. Nếu có digest hợp lệ khớp, tiếp tục xử lý script/style theo các chính sách browser khác.
6. Nếu không có digest hợp lệ khớp, từ chối thực thi script hoặc áp dụng stylesheet.

Luồng minh họa:

```text
HTML có URL + integrity hash
             │
             ▼
Browser tải tài nguyên
             │
             ▼
Response có thể đọc/kiểm tra?
        ┌────┴─────┐
        │          │
       Có         Không
        │          │
        ▼          ▼
Tính digest    CORS / network /
thực tế        response failure
        │
        ▼
So sánh với hash đã pin
        │
   ┌────┴─────┐
   │          │
  Khớp      Không khớp
   │          │
   ▼          ▼
Cho phép     Chặn script/style
xử lý tiếp   và báo lỗi
```

SRI là một bước kiểm tra trước khi browser sử dụng nội dung tài nguyên. Nó không thay thế các chính sách khác như CSP `script-src` hoặc `style-src`; tài nguyên còn phải đáp ứng những chính sách đó.

### 3.1 Hash được tính trên nội dung nào?

Hash phải được tạo từ đúng nội dung tài nguyên mà browser nhận sau khi response được giải mã theo cơ chế truyền tải. Hãy tạo hash từ artifact cuối cùng sau build, bundle, minify và các bước biến đổi của hệ thống phân phối.

Không tạo hash từ source file ban đầu nếu server thực tế phục vụ một file đã được bundle hoặc biến đổi. CDN có thể tối ưu JavaScript/CSS hoặc trả nội dung khác theo cấu hình; nếu byte nội dung cuối cùng thay đổi, digest cũng thay đổi.

### 3.2 Metadata phải có thuật toán được hỗ trợ

SRI sử dụng digest theo định dạng `algorithm-base64digest`. Các thuật toán phổ biến là:

| Thuật toán | Ví dụ tiền tố | Khuyến nghị |
| --- | --- | --- |
| SHA-256 | `sha256-` | Được hỗ trợ rộng, nhưng nên ưu tiên thuật toán mạnh hơn khi phù hợp. |
| SHA-384 | `sha384-` | Lựa chọn phổ biến, cân bằng giữa hỗ trợ và độ mạnh. |
| SHA-512 | `sha512-` | Mạnh, nhưng digest dài hơn. |

Không dùng SHA-1 cho SRI mới. Trong metadata có nhiều digest, browser ưu tiên nhóm thuật toán mạnh nhất mà nó hỗ trợ; nếu nhóm mạnh nhất có nhiều digest, một digest trong nhóm đó phải khớp. Vì vậy, không nên liệt kê hash của nhiều phiên bản nội dung khác nhau với kỳ vọng browser tự chọn một bản bất kỳ.

## 4. Các dạng integrity failure thường gặp

Không phải mọi lỗi tải script đều là hash mismatch. Cần phân loại trước khi xử lý.

| Dạng lỗi | Dấu hiệu | Nguyên nhân thường gặp |
| --- | --- | --- |
| Digest mismatch | Console báo không tìm thấy digest hợp lệ trong `integrity` | File trên CDN khác nội dung được pin; HTML dùng hash cũ. |
| Metadata không hợp lệ | Hash sai định dạng hoặc không có thuật toán được hỗ trợ | Sai tiền tố, Base64 bị cắt, dấu cách/quote lỗi hoặc thuật toán không hỗ trợ. |
| CORS failure | Console/Network báo CORS; response không được phép dùng | Server tài nguyên không trả `Access-Control-Allow-Origin` phù hợp. |
| Network failure | DNS, TLS, timeout, 404, 5xx hoặc offline | Tài nguyên không tải được hoặc endpoint lỗi. |
| Cache không đồng bộ | Chỉ một số người dùng/edge bị lỗi | HTML mới đi cùng asset cũ hoặc HTML cũ đi cùng asset mới. |
| Build/CDN transform | Hash thay đổi sau khi publish | Minifier, optimizer hoặc CDN thay đổi nội dung sau khi hash được tạo. |
| URL/redirect sai | Tài nguyên cuối khác asset dự kiến | Alias CDN, redirect hoặc cấu hình version trỏ nhầm file. |

### 4.1 Digest mismatch không đồng nghĩa chắc chắn bị tấn công

Nếu file được cập nhật hợp lệ nhưng HTML vẫn giữ hash cũ, browser vẫn phải chặn tài nguyên. Đây là hành vi đúng: browser không thể tự biết thay đổi đó có được đội phát triển phê duyệt hay không.

Hãy đối chiếu hash trong HTML với artifact trong release manifest và response thực tế. Nếu không giải thích được vì sao nội dung thay đổi, xử lý như một sự cố integrity cho tới khi nguồn gốc được xác minh.

### 4.2 CORS failure khác digest mismatch

Với tài nguyên cross-origin, browser cần một CORS response hợp lệ để SRI có thể kiểm tra. Nếu server không cấp quyền CORS, browser không thể sử dụng response theo yêu cầu và resource load thất bại. Việc thay hash không sửa được lỗi CORS.

### 4.3 Network failure không phải integrity mismatch

Nếu CDN trả 404, TLS lỗi hoặc request timeout, browser không có response body hợp lệ để so digest. Sửa `integrity` trong trường hợp này chỉ che khuất nguyên nhân thật.

## 5. Cấu hình SRI cho script và stylesheet

Thuộc tính `integrity` chứa một hoặc nhiều digest metadata. Ví dụ script:

```html
<script
  src="https://cdn.example.net/libs/widget-4.2.1.min.js"
  integrity="sha384-BASE64_DIGEST"
  crossorigin="anonymous"
  defer></script>
```

Ví dụ stylesheet:

```html
<link
  rel="stylesheet"
  href="https://cdn.example.net/css/site-4.2.1.min.css"
  integrity="sha384-BASE64_DIGEST"
  crossorigin="anonymous">
```

Thay `BASE64_DIGEST` bằng digest được tạo từ đúng artifact. Không copy chuỗi ví dụ vào production.

### 5.1 SRI cho tài nguyên cùng origin

Với tài nguyên cùng origin, browser có thể tải và kiểm tra digest mà không cần mở CORS cho một origin khác. Ví dụ:

```html
<script
  src="/assets/app.8c2f1.js"
  integrity="sha384-BASE64_DIGEST"
  defer></script>
```

Vẫn cần giữ hash đồng bộ với file được phát hành. Cùng origin không có nghĩa nội dung không thể bị thay đổi do deploy lỗi, cache cũ hoặc máy chủ bị xâm nhập.

### 5.2 SRI cho tài nguyên cross-origin cần CORS

Khi dùng SRI với tài nguyên cross-origin, request cần chạy theo CORS mode và server tài nguyên phải cho phép origin của trang. Thuộc tính `crossorigin` trên `script` hoặc `link` thiết lập chế độ CORS phù hợp.

Nếu bỏ thuộc tính `crossorigin` trên một script cross-origin, request thông thường dùng chế độ `no-cors`. Response opaque không đáp ứng bước CORS check cần thiết cho SRI, vì vậy browser không thể chấp nhận tài nguyên theo cách này. Với CDN public, hãy khai báo `crossorigin="anonymous"` và cấu hình CORS ở server.

Với tài nguyên public không cần cookie cross-origin:

```html
<script
  src="https://cdn.example.net/library.min.js"
  integrity="sha384-BASE64_DIGEST"
  crossorigin="anonymous"></script>
```

Server CDN có thể trả:

```http
Access-Control-Allow-Origin: *
```

Wildcard phù hợp với tài nguyên công khai không dùng credentials. Nếu muốn giới hạn origin, server có thể trả chính xác origin của ứng dụng và quản lý `Vary: Origin` khi response thay đổi theo request origin.

### 5.3 anonymous và use-credentials

| Giá trị | Credentials mode | Khi nào dùng |
| --- | --- | --- |
| `crossorigin="anonymous"` | `same-origin`: credentials có thể được gửi cho same-origin, không gửi cho cross-origin. | Lựa chọn thông thường cho thư viện/CDN public. |
| `crossorigin="use-credentials"` | `include`: có thể gửi credentials cross-origin. | Chỉ khi tài nguyên thật sự cần cookie hoặc HTTP authentication cross-origin. |

Với `use-credentials`, server phải trả `Access-Control-Allow-Origin` là origin cụ thể, không được là `*`, và phải có:

```http
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
Vary: Origin
```

Không bật credentials chỉ để sửa CORS. Gửi cookie cross-origin làm tăng phạm vi dữ liệu và phụ thuộc vào chính sách cookie như SameSite.

### 5.4 CORS không thay thế SRI

CORS trả lời câu hỏi origin nào được phép đọc response. SRI trả lời câu hỏi nội dung nhận được có khớp digest đã pin hay không.

- CORS thành công không chứng minh script an toàn hoặc đúng phiên bản.
- SRI hash đúng không tự cấp quyền CORS cho response cross-origin.
- Hai cơ chế cùng hoạt động khi ứng dụng tải tài nguyên cross-origin có pin integrity.

## 6. Tạo hash từ artifact đã phát hành

Digest phải được tạo từ file cuối cùng được đưa lên CDN/server, sau khi build đã hoàn tất. Một quy trình đơn giản:

1. Build và minify tài nguyên.
2. Chạy các bước tối ưu/transform giống môi trường production.
3. Xác định đúng file cuối cùng sẽ được upload.
4. Tạo SHA-384 digest ở dạng Base64.
5. Đưa digest vào HTML hoặc manifest được sinh tự động.
6. Kiểm tra lại response mà browser thực sự nhận.

### 6.1 Dùng OpenSSL

Với file `widget.min.js`:

```bash
openssl dgst -sha384 -binary widget.min.js | openssl base64 -A
```

Lệnh trả về chuỗi Base64. Ghép tiền tố `sha384-` để tạo giá trị SRI:

```text
sha384-BASE64_OUTPUT_FROM_OPENSSL
```

Không dùng output hex mặc định của `openssl dgst` làm giá trị `integrity`; SRI cần digest Base64.

### 6.2 Dùng Node.js

Có thể sinh metadata trong build script:

```javascript
import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";

const bytes = await readFile("dist/widget.min.js");
const digest = createHash("sha384")
  .update(bytes)
  .digest("base64");

console.log("sha384-" + digest);
```

Đây là ví dụ tạo digest cho file local. Build pipeline cần bảo đảm file `dist/widget.min.js` chính là artifact sẽ được publish và không còn bước nào sửa nội dung sau khi tính hash.

### 6.3 Hash phải khớp đúng phiên bản

Ví dụ:

| Artifact | Digest | HTML tham chiếu |
| --- | --- | --- |
| `widget-4.2.1.min.js` | SHA-384 của file 4.2.1 | Pin hash của 4.2.1 |
| `widget-4.2.2.min.js` | SHA-384 của file 4.2.2 | Pin hash của 4.2.2 |

Không cập nhật nội dung tại một URL versioned mà không cập nhật HTML và integrity metadata tương ứng. Tốt nhất dùng tên file có version hoặc content hash để mỗi URL đại diện cho một nội dung bất biến.

## 7. Xử lý lỗi bằng DevTools

DevTools giúp xác định browser đã tải gì và vì sao từ chối tài nguyên.

### 7.1 Kiểm tra Console

Mở DevTools → Console và tìm thông báo liên quan đến:

- Failed to find a valid digest in the `integrity` attribute.
- Cross-origin resource sharing (CORS) blocked.
- Failed to load resource, status 404 hoặc 5xx.
- Certificate/TLS error, DNS failure hoặc timeout.
- Content Security Policy đã chặn script/style.

Thông báo có thể khác theo browser. Hãy dùng Console để phân loại, sau đó kiểm tra request cụ thể trong Network.

### 7.2 Kiểm tra Network

1. Mở DevTools → Network.
2. Bật Preserve log nếu trang có redirect hoặc điều hướng.
3. Reload trang và lọc theo JS hoặc CSS.
4. Chọn request bị lỗi, xem Request URL, Status, Initiator và Response Headers.
5. Kiểm tra response có bị redirect tới URL ngoài dự kiến không.
6. Mở tab Response/Preview nếu browser cho phép xem nội dung.
7. Đối chiếu nội dung, hash trong HTML và artifact release.

Nếu request bị chặn trước khi response có thể đọc được do CORS, Network panel và Console thường cho biết lỗi CORS. Không suy ra digest mismatch chỉ từ việc script không chạy.

### 7.3 Kiểm tra thuộc tính trong Elements

Chọn phần tử `script` hoặc `link` và xác nhận:

- `src` hoặc `href` đúng URL versioned.
- `integrity` có tiền tố thuật toán và Base64 đầy đủ.
- `crossorigin` phù hợp với chế độ credentials.
- Không có script khác cùng URL nhưng thiếu integrity do code chèn động.

Kiểm tra HTML response gốc và DOM sau khi JavaScript chạy; một framework hoặc loader có thể tạo thêm resource element lúc runtime.

## 8. Kiểm tra độc lập bằng curl và OpenSSL

Có thể tải asset để tính lại digest:

```bash
curl -fsSL https://cdn.example.net/libs/widget-4.2.1.min.js -o widget.min.js
openssl dgst -sha384 -binary widget.min.js | openssl base64 -A
```

So sánh kết quả với hash trong HTML. Nếu khác:

1. Xác nhận URL và redirect cuối cùng.
2. So sánh file tải được với artifact trong release.
3. Kiểm tra CDN có minify, rewrite hoặc optimize response không.
4. Kiểm tra cache và các edge có phục vụ cùng nội dung không.
5. Kiểm tra request browser có nhận cùng representation với curl không.

curl không thực thi CORS hoặc SRI. Nó giúp lấy response và so hash, nhưng kết quả cuối cùng phải được xác nhận trong browser với đúng request mode và response headers.

### 8.1 Đừng hash nhầm file

Những sai lệch thường gặp:

- Tính hash file source nhưng phát hành bundle đã minify.
- Tính hash trước khi pipeline chèn banner/version/build metadata.
- Tính hash file local nhưng CDN trả một bản khác theo URL hoặc cache.
- Copy hash từ release trước.
- Dán digest hex thay vì Base64.
- Thêm khoảng trắng hoặc cắt mất ký tự Base64 khi render HTML.

## 9. Fallback khi tài nguyên bị chặn

Khi SRI thất bại, browser không tự tìm một bản thay thế. Nếu ứng dụng cần high availability, có thể chuẩn bị fallback đã được phê duyệt và có integrity hash riêng.

Ví dụ loader đơn giản:

```javascript
function loadPinnedScript(src, integrity) {
  return new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = src;
    script.integrity = integrity;
    script.crossOrigin = "anonymous";
    script.onload = () => resolve();
    script.onerror = () => reject(new Error("Pinned script failed"));
    document.head.append(script);
  });
}

async function loadWidget() {
  try {
    await loadPinnedScript(
      "https://cdn-a.example.net/widget-4.2.1.js",
      "sha384-PRIMARY_DIGEST"
    );
  } catch {
    await loadPinnedScript(
      "https://cdn-b.example.net/widget-4.2.1.js",
      "sha384-BACKUP_DIGEST"
    );
  }
}
```

Hai digest phải được tạo và phê duyệt độc lập cho đúng artifact ở từng URL. Nếu hai CDN phục vụ cùng byte nội dung, digest có thể giống nhau; nếu khác nội dung, chỉ dùng digest đã được xác minh cho từng bản.

### 9.1 Fallback phải chịu CSP và CORS

Fallback vẫn phải tuân thủ:

- CSP `script-src` phải cho phép nguồn backup theo chính sách của trang.
- CORS response của CDN backup phải phù hợp với `crossorigin`.
- Script backup phải có integrity metadata riêng.
- Loader không được nhận URL tùy ý từ query string, message hoặc dữ liệu không tin cậy.
- Cần giới hạn số lần thử để tránh vòng lặp tải vô hạn.

Không tạo fallback bằng cách xóa `integrity`, dùng `eval()` hoặc chèn HTML từ nguồn không xác minh.

### 9.2 Không che giấu incident bằng fallback

Nếu primary asset bất ngờ mismatch, ghi nhận sự kiện, giữ lại URL, thời điểm, digest và response để điều tra. Fallback có thể duy trì chức năng nhưng không nên xóa dấu vết hoặc làm mất cảnh báo về CDN/asset bị thay đổi.

## 10. Cập nhật tài nguyên mà không gây integrity failure

SRI ràng buộc HTML với byte nội dung cụ thể. Vì vậy, release HTML và asset cần được triển khai nhất quán.

Một thứ tự an toàn thường là:

1. Build asset mới với URL versioned hoặc content-hashed.
2. Tính digest từ artifact cuối cùng.
3. Upload asset mới lên tất cả nơi phân phối.
4. Xác minh URL mới trả đúng nội dung và CORS headers.
5. Phát hành HTML tham chiếu URL và digest mới.
6. Giữ asset cũ trong khoảng thời gian đủ dài để HTML cũ trong cache vẫn hoạt động.
7. Sau thời gian chuyển tiếp, mới dọn asset cũ theo retention policy.

Nếu phát HTML mới trước khi asset mới có mặt trên mọi CDN edge, người dùng có thể gặp 404 hoặc mismatch. Nếu ghi đè asset cũ tại URL không versioned, HTML cũ đang cache có thể bị mismatch.

### 10.1 Cache HTML và cache asset

Nên thiết kế cache policy khác nhau:

- HTML thường cần revalidation hoặc thời gian cache phù hợp để cập nhật nhanh.
- Asset có content hash trong tên file có thể cache lâu và immutable.
- Asset versioned cũ cần được giữ đủ lâu cho các client còn HTML cũ.
- Service worker cần cập nhật cache version một cách nguyên tử, tránh trộn HTML mới với asset cũ.

### 10.2 Release manifest

Build pipeline nên tạo manifest liên kết:

| Trường | Ví dụ |
| --- | --- |
| Asset URL | `/assets/app.8c2f1.js` |
| Version/build ID | `release-2026.11.22.3` |
| Algorithm | `sha384` |
| Digest | Base64 digest |
| File size | Số byte của artifact |
| Build artifact checksum | Checksum dùng để đối chiếu trong pipeline |

Manifest giúp reviewer xác nhận hash trong HTML đến từ artifact nào và release nào.

## 11. SRI, CSP và các lớp bảo vệ liên quan

SRI và Content Security Policy (CSP) giải quyết hai câu hỏi khác nhau:

| Cơ chế | Kiểm soát |
| --- | --- |
| CSP `script-src` / `style-src` | Nguồn nào được phép cung cấp script hoặc stylesheet; có thể giới hạn bằng origin, nonce hoặc hash tùy loại nội dung. |
| SRI `integrity` | Nội dung tài nguyên bên ngoài có khớp digest đã pin hay không. |
| CORS | Origin nào được phép dùng response cross-origin theo request mode. |
| TLS | Kết nối tới endpoint có được mã hóa và xác thực theo certificate hay không. |

Ví dụ CSP chỉ cho phép script từ ứng dụng và CDN:

```http
Content-Security-Policy: script-src 'self' https://cdn.example.net
```

Sau đó, SRI pin đúng file từ CDN:

```html
<script
  src="https://cdn.example.net/widget-4.2.1.min.js"
  integrity="sha384-BASE64_DIGEST"
  crossorigin="anonymous"></script>
```

CSP cho phép nguồn CDN, còn SRI xác minh byte nội dung của resource cụ thể. Nếu CSP chặn nguồn, request có thể bị chặn trước khi SRI trở thành vấn đề. Nếu CSP cho phép nhưng digest sai, SRI vẫn chặn tài nguyên.

### 11.1 SRI không xác minh inline script

SRI được thiết kế cho tài nguyên được tải ngoài qua các cơ chế hỗ trợ. Với inline script, dùng CSP nonce hoặc CSP hash theo đúng mô hình triển khai. Không đặt thuộc tính `integrity` lên inline script với kỳ vọng nó sẽ pin nội dung inline.

### 11.2 Dependency được tải tiếp

Pin một script entry không nên được hiểu là tự động pin toàn bộ tài nguyên mà script đó tải sau này. Ví dụ, loader có thể tạo thêm script element hoặc import dependency từ một URL khác. Hãy kiểm kê dependency graph, áp dụng integrity metadata cho tài nguyên phù hợp và giới hạn nguồn bằng CSP.

## 12. Kiểm thử integrity failure trong lab

Thực hiện trên trang thử nghiệm và asset do bạn kiểm soát. Mục tiêu là quan sát browser chặn một file khi digest không khớp.

### 12.1 Tạo một file JavaScript nhỏ

Tạo file `integrity-demo.js`:

```javascript
console.log("Trusted demo asset loaded");
document.documentElement.dataset.integrityDemo = "loaded";
```

Tính SHA-384 của file:

```bash
openssl dgst -sha384 -binary integrity-demo.js | openssl base64 -A
```

Copy kết quả Base64 và ghép tiền tố `sha384-`.

### 12.2 Nhúng file với hash đúng

```html
<!doctype html>
<html lang="vi">
  <head>
    <meta charset="utf-8">
    <title>SRI test</title>
  </head>
  <body>
    <script
      src="/integrity-demo.js"
      integrity="sha384-PASTE_REAL_DIGEST_HERE"></script>
  </body>
</html>
```

Khi hash khớp, Console ghi thông báo và `document.documentElement.dataset.integrityDemo` có giá trị `loaded`.

### 12.3 Thay đổi một byte của file

Sửa nội dung JavaScript, ví dụ đổi chuỗi log thành `Modified asset loaded`, nhưng giữ nguyên hash trong HTML. Reload trang.

Kết quả mong đợi:

- Browser tải response.
- Digest thực tế không khớp hash metadata.
- Script không được thực thi.
- Console ghi lỗi SRI.
- Dataset `integrityDemo` không được đặt thành `loaded`.

Không cần thử nghiệm bằng cách xóa `integrity`; việc đó loại bỏ chính kiểm tra cần quan sát.

### 12.4 Kiểm thử CORS cho CDN giả lập

Nếu chạy trang và asset ở hai port khác nhau, chúng là hai origin khác nhau. Với script cross-origin có SRI, cấu hình server asset trả CORS header phù hợp và thêm `crossorigin="anonymous"` vào element.

Thử bỏ CORS header để quan sát request bị chặn vì CORS. Sau đó khôi phục CORS nhưng giữ hash sai để phân biệt CORS failure với digest mismatch.

### 12.5 Kiểm tra event lỗi

Có thể lắng nghe sự kiện:

```javascript
const script = document.querySelector("#vendor-script");

script.addEventListener("load", () => {
  console.log("Script loaded and passed resource checks");
});

script.addEventListener("error", () => {
  console.error("Script resource failed to load or validate");
});
```

Sự kiện `error` không tự cho biết chắc chắn nguyên nhân là digest mismatch. Hãy kết hợp với Console và Network để phân loại CORS, network, CSP và SRI.

## 13. Xử lý integrity failure như một sự cố

Nếu một tài nguyên production bất ngờ mismatch mà chưa có release được phê duyệt, cần giữ lại bằng chứng trước khi sửa.

Quy trình xử lý:

1. Ghi lại URL, hostname, thời gian, browser, request ID nếu có và thông báo Console.
2. Lưu giá trị `integrity` trong HTML đang được phục vụ.
3. Tải và lưu response asset qua đường phân phối đang gặp lỗi.
4. Tính digest của response và so sánh với release artifact đáng tin cậy.
5. Kiểm tra CDN, bucket, tài khoản deploy, pipeline và lịch sử thay đổi.
6. Xác định thay đổi là release hợp lệ, cache inconsistency hay nội dung không được phê duyệt.
7. Nếu nghi ngờ bị can thiệp, cô lập hoặc thu hồi asset, kiểm tra quyền truy cập và thay credentials/keys theo incident process.
8. Chỉ phát hành hash mới sau khi nội dung đã được review và phê duyệt.

Không cập nhật hash chỉ vì digest mới đang được CDN phục vụ. Làm vậy có thể biến một thay đổi độc hại thành nội dung được tin cậy.

### 13.1 Bảo toàn bằng chứng

Giữ:

- HTML response có URL và integrity metadata.
- Asset response thực tế và digest tính được.
- Response headers, redirect chain và cache headers.
- Timestamp, CDN edge/region và request identifiers.
- Build artifact, release manifest và lịch sử deploy.

Nếu tài nguyên có chứa dữ liệu nhạy cảm hoặc thông tin khách hàng, xử lý bản lưu theo chính sách bảo vệ dữ liệu nội bộ.

### 13.2 Khi đã xác nhận release hợp lệ

Nếu asset thay đổi do một release hợp lệ, tạo digest mới từ artifact đã duyệt, phát hành HTML mới cùng URL versioned, xác minh CORS và SRI trên staging, rồi triển khai theo thứ tự upload asset trước và HTML sau.

Nếu thay đổi không được giải thích hoặc không xác định được nguồn gốc, không cập nhật hash để bỏ qua cảnh báo.

## 14. Tự động hóa kiểm tra trong CI/CD

Pipeline nên sinh integrity metadata từ build artifact và kiểm tra lại trước khi deploy.

Các bước đề xuất:

1. Build asset một lần và lưu artifact bất biến.
2. Tạo digest từ đúng file trong artifact.
3. Sinh HTML hoặc manifest tham chiếu digest.
4. Kiểm tra URL, thuật toán và định dạng Base64.
5. Tải lại asset từ staging/CDN và tính digest lần nữa.
6. So sánh digest tải về với manifest.
7. Kiểm tra CORS headers cho asset cross-origin.
8. Chạy browser test xác nhận script/style được chấp nhận.
9. Deploy asset trước, HTML sau.
10. Giữ lại asset cũ trong thời gian cache transition.

### 14.1 Kiểm tra manifest bằng Node.js

Ví dụ script kiểm tra file và sinh SRI:

```javascript
import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";

async function sriFor(path) {
  const bytes = await readFile(path);
  const digest = createHash("sha384")
    .update(bytes)
    .digest("base64");
  return "sha384-" + digest;
}

const integrity = await sriFor("dist/widget.min.js");
console.log(integrity);
```

Trong pipeline thật, ghi kết quả vào manifest có version/build ID và dùng cùng artifact cho bước upload. Không build lại file giữa lúc tính hash và publish vì output có thể khác.

### 14.2 Kiểm tra sau deploy

Sau khi deploy staging:

- Fetch URL public của asset.
- Tính digest từ response nhận được.
- So sánh với digest trong manifest.
- Xác minh `Access-Control-Allow-Origin` khi asset cross-origin.
- Mở trang bằng browser và kiểm tra Console/Network.
- Thử cache cold và cache warm, cùng các edge/region nếu có CDN.

Một unit test cho hàm tạo hash không đủ để phát hiện CDN phục vụ nhầm file. Cần kiểm tra artifact đã đi hết đường phân phối.

## 15. Các lỗi triển khai thường gặp

| Lỗi | Hậu quả | Cách phòng tránh |
| --- | --- | --- |
| Tính hash trước bước minify | Digest không khớp file production. | Tính hash sau mọi bước biến đổi. |
| Ghi đè URL asset cũ | HTML đang cache có hash không còn khớp. | Dùng URL versioned/content-hashed. |
| Quên `crossorigin` cho CDN | CORS/SRI không thể xác minh response cross-origin. | Dùng `crossorigin="anonymous"` và cấu hình CORS. |
| CDN thiếu CORS header | Browser chặn request trước khi dùng tài nguyên. | Cấu hình ACAO phù hợp tại CDN/origin. |
| Dùng `Access-Control-Allow-Origin: *` với credentials | CORS không chấp nhận wildcard cho credentialed response. | Trả origin cụ thể và ACAC true nếu thực sự cần credentials. |
| Dán digest hex | Metadata không đúng định dạng SRI. | Dùng Base64 digest. |
| Cập nhật hash để bỏ qua mismatch lạ | Có thể tin nhầm asset bị thay đổi. | Xác minh artifact/release trước khi pin hash mới. |
| Fallback không có hash | Backup trở thành đường tải không được kiểm tra. | Pin integrity riêng cho backup. |
| Chỉ test curl | Không kiểm tra CORS/SRI enforcement trong browser. | Thực hiện browser test trên staging. |
| Xóa asset cũ quá sớm | HTML cũ trong cache hoặc service worker bị lỗi tải. | Giữ asset theo cache transition/retention. |

## 16. Checklist xử lý và phòng ngừa

- [ ] Xác định chính xác URL và loại tài nguyên bị lỗi.
- [ ] Phân biệt digest mismatch với CORS, CSP, TLS và network failure.
- [ ] Lưu HTML đang phục vụ cùng integrity metadata.
- [ ] Tải và lưu response asset để đối chiếu.
- [ ] So sánh với artifact và manifest từ release được phê duyệt.
- [ ] Tạo SHA-384 hoặc SHA-512 Base64 từ artifact cuối cùng.
- [ ] Có `crossorigin` phù hợp cho tài nguyên cross-origin.
- [ ] Server CDN trả CORS headers đúng với credentials mode.
- [ ] CSP vẫn giới hạn nguồn script/style cần thiết.
- [ ] Fallback có integrity riêng và bị giới hạn nguồn.
- [ ] Không bỏ integrity để chữa lỗi tạm thời.
- [ ] Asset URL versioned hoặc content-hashed.
- [ ] Upload asset trước khi phát hành HTML mới.
- [ ] Giữ asset cũ đủ lâu cho HTML/cache cũ.
- [ ] CI/CD xác minh digest cả trước và sau publish.
- [ ] Browser test xác nhận script/style bị chặn khi digest sai.

## 17. Câu hỏi tự kiểm tra

1. SRI kiểm tra điều gì trước khi browser sử dụng script hoặc stylesheet?
2. Vì sao HTTPS không tự phát hiện một thư viện CDN bị thay nội dung?
3. Browser xử lý script thế nào khi digest không khớp?
4. Integrity mismatch khác CORS failure và network failure ra sao?
5. Vì sao hash phải được tạo từ artifact cuối cùng sau build?
6. Tại sao SRI cross-origin cần CORS và thuộc tính `crossorigin`?
7. `anonymous` khác `use-credentials` ở credentials mode như thế nào?
8. Vì sao CORS thành công không chứng minh nội dung script đáng tin?
9. Vì sao không nên cập nhật hash mới trước khi xác minh asset?
10. Vì sao fallback cũng cần integrity metadata?
11. Làm thế nào để deploy HTML và asset mà không tạo cache mismatch?
12. Những bằng chứng nào cần giữ lại khi integrity failure xuất hiện trên production?

## 18. Tổng kết

Integrity failure xảy ra khi browser không xác minh được nội dung tài nguyên với hash đã pin hoặc không thể tải/kiểm tra response theo chính sách yêu cầu. Với SRI, browser chặn script không thực thi hoặc stylesheet không được áp dụng khi digest không hợp lệ. Hãy phân biệt lỗi digest với CORS, CSP, TLS, network và cache trước khi sửa.

Tạo hash SHA-384/SHA-512 Base64 từ artifact cuối cùng sau build, ghép metadata vào `integrity` và dùng `crossorigin="anonymous"` cho phần lớn tài nguyên CDN public. Nếu cần credentials cross-origin, cấu hình CORS với origin cụ thể và `Access-Control-Allow-Credentials: true`. SRI bổ sung cho CSP và TLS; nó không thay thế việc bảo vệ HTML hoặc xác minh release.

Khi gặp mismatch bất thường, lưu response và metadata, đối chiếu với artifact đã phê duyệt rồi mới quyết định cập nhật hash. Trong CI/CD, sinh manifest tự động, kiểm tra digest sau publish, triển khai asset trước HTML và giữ phiên bản cũ trong thời gian cache transition. Không xóa thuộc tính integrity hoặc pin một digest mới chưa được xác minh chỉ để làm trang hoạt động trở lại.
