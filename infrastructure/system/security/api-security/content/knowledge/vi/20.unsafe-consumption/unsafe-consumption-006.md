# Giới hạn redirect, response size và nested payload

Một API có thể xác thực đúng người gọi và kiểm tra quyền đầy đủ nhưng vẫn bị làm cạn tài nguyên bởi dữ liệu hoặc phản hồi quá lớn. Một endpoint tải nội dung từ URL do client cung cấp có thể bị dẫn qua nhiều redirect tới dịch vụ nội bộ; một upstream có thể trả về body hàng gigabyte hoặc dữ liệu nén nở ra rất lớn; một JSON lồng hàng nghìn cấp có thể làm parser tràn stack hoặc tiêu tốn CPU và bộ nhớ. Đây là nhóm rủi ro **unsafe consumption of APIs**: hệ thống tiêu thụ tài nguyên từ request, response hoặc dịch vụ phụ thuộc mà không đặt giới hạn phù hợp.

Ba điểm cần kiểm soát trong bài này là:

- **Redirect:** số lần chuyển hướng, đích đến và thay đổi method/credential qua từng hop.
- **Response size:** số byte thực tế, kích thước sau giải nén, header, thời gian và tài nguyên khi đọc response.
- **Nested payload:** độ sâu, số phần tử, độ dài trường và độ phức tạp của cấu trúc dữ liệu.

Giới hạn phải được thực thi ở nhiều lớp: gateway/reverse proxy, HTTP client, parser, service và hạ tầng mạng. Chỉ giới hạn `Content-Length` hoặc chỉ đặt timeout không đủ để bảo vệ toàn bộ luồng xử lý.

## 1. Vì sao redirect, response size và nested payload là bề mặt tấn công?

Hãy xét endpoint cho phép người dùng nhập URL để tạo bản xem trước tài liệu:

```http
POST /api/v1/previews HTTP/1.1
Authorization: Bearer <access-token>
Content-Type: application/json

{
  "url": "https://files.example.net/document"
}
```

Server gọi URL đó, nhận response, giải nén nếu cần, parse nội dung rồi tạo preview. Một request có thể kích hoạt cả chuỗi tiêu thụ tài nguyên:

1. URL trả `302` tới một host khác; server tiếp tục theo redirect.
2. Đích mới trả tiếp redirect, khiến server tạo nhiều kết nối.
3. Response có `Content-Length` rất lớn hoặc không có header này.
4. Body nén nhỏ nhưng khi giải nén tăng lên hàng gigabyte.
5. Nội dung JSON/XML có cấu trúc lồng sâu hoặc số lượng node rất lớn.
6. Parser và renderer tiếp tục tạo object graph, hình ảnh hoặc tài liệu lớn trong bộ nhớ.

Kết quả có thể là SSRF, cạn connection pool, CPU cao, heap exhaustion, thread bị giữ lâu, hàng đợi công việc tăng hoặc chi phí gọi dịch vụ ngoài tăng đột biến. Kẻ tấn công không nhất thiết phải gửi một request lớn; nhiều request nhỏ có thể cùng kích hoạt tác vụ đắt tiền.

## 2. Giới hạn redirect theo chính sách rõ ràng

Redirect là phản hồi HTTP yêu cầu client gửi request tới URI khác. Các status thường gặp gồm `301`, `302`, `303`, `307` và `308`. HTTP client có thể tự động theo redirect, nhưng hành vi mặc định của thư viện không nhất thiết phù hợp với chính sách bảo mật của ứng dụng.

Một endpoint tải URL từ bên ngoài nên có chính sách redirect tường minh:

- Tắt tự động redirect nếu cần kiểm tra từng đích đến.
- Chỉ cho phép số hop nhỏ, ví dụ tối đa 3 hoặc 5; con số thực tế dựa trên nghiệp vụ.
- Phát hiện vòng lặp redirect và giới hạn tổng thời gian cho toàn bộ chuỗi.
- Chỉ cho phép scheme cần thiết, thường là `https`; từ chối downgrade từ HTTPS sang HTTP.
- Kiểm tra host, port, DNS và địa chỉ IP ở từng hop, không chỉ URL ban đầu.
- Không chuyển tiếp `Authorization`, cookie, API key hoặc header bí mật sang origin khác.
- Chỉ cho phép method và loại nội dung phù hợp với chức năng; với chức năng tải tài nguyên, ưu tiên chỉ dùng `GET`.
- Không để redirect thay đổi phạm vi quyền hoặc biến một thao tác đọc thành request có side effect.

Nếu nghiệp vụ không cần redirect, hãy từ chối mọi response redirect. Tắt redirect là lựa chọn đơn giản và dễ kiểm soát nhất đối với nhiều endpoint fetch URL.

### Hiểu sự khác nhau giữa các mã redirect

| Status | Hành vi thường gặp của client | Điểm cần chú ý |
|---|---|---|
| `301 Moved Permanently` | Redirect vĩnh viễn; một số client có thể đổi POST thành GET | Không dựa vào hành vi tự động của thư viện cho request có body |
| `302 Found` | Redirect tạm thời; hành vi với POST có thể khác giữa client | Cần định nghĩa method policy rõ |
| `303 See Other` | Thường chuyển sang GET (trừ HEAD) | Body request ban đầu không được gửi lại như một POST thông thường |
| `307 Temporary Redirect` | Giữ nguyên method và body | Có thể gửi lại payload tới origin khác |
| `308 Permanent Redirect` | Giữ nguyên method và body | Có thể gửi lại payload tới origin khác trong thời gian dài |

Nếu HTTP client tự theo redirect, nó có thể tự quyết định method, body, header và cách xử lý credential. Với API có dữ liệu nhạy cảm, hãy tự kiểm soát redirect hoặc chỉ cho phép một tập hành vi đã được kiểm thử.

### Giới hạn số hop và thời gian tổng

Giới hạn từng request timeout chưa đủ nếu mỗi hop đều mất gần hết timeout. Ví dụ, 5 redirect với timeout 10 giây mỗi hop có thể giữ worker gần 50 giây. Đặt cả:

- `maxRedirects`: số lần redirect tối đa.
- Connect timeout: thời gian thiết lập kết nối.
- Response/read timeout: thời gian chờ dữ liệu hoặc khoảng thời gian không nhận thêm dữ liệu.
- Overall deadline: thời gian tối đa cho toàn bộ chuỗi redirect và đọc body.
- Max response headers: giới hạn số lượng và tổng kích thước header.

Deadline tổng phải được truyền qua từng hop và không được reset lại khi redirect. Nếu deadline đã hết, dừng request và đóng kết nối/stream.

## 3. Kiểm tra đích đến ở từng redirect để ngăn SSRF

Không chỉ kiểm tra URL đầu tiên. Mỗi response redirect có thể đưa server tới một host, port hoặc IP khác. Đích đến mới phải trải qua cùng một chính sách kiểm tra như URL ban đầu.

Một quy trình kiểm tra có thể gồm:

1. Parse `Location` thành URI hợp lệ; xử lý cả URI tuyệt đối và URI tương đối theo base URI hiện tại.
2. Chuẩn hóa scheme, hostname, port và đường dẫn theo một quy tắc nhất quán.
3. Kiểm tra scheme trong allowlist; từ chối `file:`, `ftp:`, `gopher:` và scheme không được hỗ trợ.
4. Kiểm tra hostname và port theo allowlist của nghiệp vụ.
5. Phân giải DNS và kiểm tra toàn bộ địa chỉ IP trả về.
6. Từ chối loopback, private, link-local, multicast, unspecified và các dải địa chỉ đặc biệt theo chính sách IPv4/IPv6.
7. Kết nối tới đúng địa chỉ đã kiểm tra hoặc dùng egress proxy có thực thi cùng chính sách để giảm DNS rebinding/TOCTOU.
8. Kiểm tra lại mọi redirect tiếp theo và không gửi credential qua origin không được phép.

Ví dụ đích cần chặn tùy môi trường gồm `127.0.0.1`, `::1`, địa chỉ RFC1918, IPv6 unique-local, link-local và endpoint metadata của nền tảng cloud. Không chỉ chặn một hostname metadata cố định; cần kiểm soát dải mạng và đường egress thực tế.

### DNS rebinding và TOCTOU

Một hostname có thể trả về IP công khai lúc kiểm tra rồi trả về IP nội bộ lúc kết nối. Nếu ứng dụng kiểm tra DNS một lần nhưng HTTP client phân giải lại ở thời điểm khác, attacker có thể khai thác khoảng cách giữa check và use.

Các biện pháp giảm rủi ro:

- Kiểm tra tất cả A/AAAA record và từ chối nếu có địa chỉ không được phép.
- Gắn kết quả phân giải đã kiểm tra với kết nối thực tế, hoặc dùng egress proxy kiểm tra đích ở thời điểm kết nối.
- Xử lý CNAME chain và phân giải lại theo chính sách; không chỉ kiểm tra chuỗi hostname ban đầu.
- Kiểm tra địa chỉ IPv4-mapped IPv6 và các biểu diễn IP bất thường.
- Không cho phép client tự chọn proxy, resolver hoặc `Host` header tùy ý.
- Kết hợp allowlist ứng dụng với firewall/network policy chặn outbound tới mạng nội bộ và metadata.

Kiểm tra chuỗi URL bằng regex không đủ. Cần kiểm tra URI đã parse, kết quả DNS và địa chỉ mà socket thực sự kết nối tới.

### Không chuyển tiếp credential qua origin khác

Khi redirect từ `https://service-a.example` sang `https://service-b.example`, không tự động gửi tiếp `Authorization`, `Cookie`, `Proxy-Authorization`, API key hoặc header chứa dữ liệu nội bộ. Mặc định an toàn là loại bỏ credential khi origin thay đổi; nếu cần credential cho đích mới, phải lấy credential riêng theo policy và audience của đích đó.

Origin bao gồm scheme, host và port. Chỉ so sánh hostname là chưa đủ nếu port hoặc scheme thay đổi. Không chuyển tiếp client certificate hoặc proxy credential theo cách vô tình mở rộng danh tính sang một đích khác.

## 4. Response size: không tin Content-Length

`Content-Length` hữu ích để từ chối sớm response quá lớn, nhưng không phải nguồn duy nhất để quyết định kích thước body:

- Header có thể bị thiếu với response streaming hoặc chunked.
- Server có thể khai báo sai hoặc không nhất quán với số byte thực tế.
- Body có thể được nén; số byte truyền đi nhỏ hơn nhiều so với dữ liệu sau giải nén.
- Một số HTTP client tự động giải nén và không còn cung cấp cho ứng dụng kích thước wire ban đầu.
- Response có thể phát dữ liệu vô hạn hoặc rất chậm mà không vi phạm giới hạn từng chunk.

Do đó, cần đếm byte thực tế khi đọc stream và áp dụng giới hạn cả trước lẫn sau giải nén. Nếu `Content-Length` lớn hơn giới hạn, có thể từ chối sớm; nếu nhỏ hoặc vắng mặt, vẫn phải đếm byte cho tới khi stream kết thúc.

### Giới hạn nhiều lớp

| Giới hạn | Mục tiêu |
|---|---|
| Max response header bytes/count | Ngăn header quá lớn hoặc quá nhiều |
| Max wire bytes | Giới hạn dữ liệu truyền từ upstream |
| Max decoded bytes | Giới hạn dữ liệu sau giải nén |
| Max expansion ratio | Phát hiện dữ liệu nén nở bất thường |
| Max body read duration | Không giữ tài nguyên vô hạn |
| Max idle/read timeout | Dừng stream không tiếp tục gửi dữ liệu |
| Max concurrent fetches | Giới hạn số kết nối/tác vụ cùng lúc |
| Max buffered bytes | Giới hạn dữ liệu giữ trong RAM |

Các giới hạn phải được đặt theo loại nội dung. Một ảnh thumbnail, tài liệu PDF và báo cáo CSV có kích thước hợp lệ rất khác nhau. Không chọn một con số lớn chung cho mọi endpoint chỉ để tránh lỗi người dùng.

## 5. Chống decompression bomb và response nén quá mức

Một response gzip nhỏ có thể giải nén thành dữ liệu rất lớn. Nếu ứng dụng chỉ giới hạn byte truyền qua mạng, attacker có thể dùng compression bomb để tiêu thụ heap, CPU hoặc dung lượng tạm.

Hãy áp dụng:

- Giới hạn kích thước compressed bytes và decompressed bytes độc lập.
- Giới hạn tỷ lệ nở (expansion ratio) nếu định dạng và thư viện hỗ trợ đo an toàn.
- Giới hạn thời gian giải nén và số luồng xử lý đồng thời.
- Chỉ hỗ trợ các content encoding cần thiết; từ chối encoding không được hỗ trợ.
- Tránh tự giải nén nhiều lớp hoặc chấp nhận chuỗi encoding không giới hạn.
- Đặt giới hạn cho archive entry count, tổng kích thước giải nén và kích thước từng entry nếu xử lý ZIP/TAR.

Không giải nén toàn bộ nội dung vào RAM. Ưu tiên streaming, ghi vào vùng tạm có quota dung lượng, kiểm tra giới hạn trong lúc giải nén và xóa file tạm khi thành công hoặc thất bại.

## 6. Kiểm tra Content-Type và định dạng thực tế

Không tin `Content-Type` do upstream khai báo như bằng chứng rằng nội dung an toàn. Một server có thể trả HTML, JSON, XML, PDF hoặc dữ liệu nhị phân với header sai hoặc cố tình đánh lừa.

Hãy quy định allowlist loại nội dung cho từng chức năng:

- Endpoint chỉ cần JSON thì từ chối HTML/XML và content type không hỗ trợ.
- Endpoint preview PDF chỉ nhận định dạng PDF đã xác minh, với parser được cập nhật và giới hạn tài nguyên.
- Upload ảnh cần kiểm tra signature/magic bytes và giải mã bằng thư viện an toàn; không chỉ dựa vào extension.
- Không tự động render HTML/JavaScript từ URL bên ngoài trong origin ứng dụng chính.
- Tránh sniffing tùy tiện; response tải về nên được phục vụ với `Content-Disposition` và `X-Content-Type-Options: nosniff` phù hợp.

Nếu nội dung được lưu rồi phục vụ lại cho người dùng, hãy tách origin lưu file khỏi ứng dụng chính, đặt quyền truy cập riêng và cân nhắc quét malware theo mô hình đe dọa.

## 7. Nested payload: giới hạn độ sâu và độ phức tạp

Một JSON nhỏ về số byte vẫn có thể tạo cấu trúc rất tốn tài nguyên nếu lồng sâu hoặc có quá nhiều node:

```json
{
  "node": {
    "node": {
      "node": {
        "node": {
          "value": "..."
        }
      }
    }
  }
}
```

Một payload có thể gây vấn đề qua:

- Độ sâu object/array lớn làm parser hoặc code đệ quy tràn stack.
- Số lượng field, array item hoặc node rất lớn làm tăng bộ nhớ và thời gian duyệt.
- Chuỗi rất dài hoặc số có hàng triệu chữ số gây tiêu thụ CPU/RAM.
- Object lồng nhau lặp lại khiến validation và mapping tạo nhiều bản sao.
- Reference hoặc alias trong định dạng hỗ trợ tham chiếu có thể tạo cấu trúc phức tạp hoặc chu kỳ.
- Duplicate JSON key làm các parser hoặc tầng gateway/backend hiểu request khác nhau.

Đừng chỉ đặt giới hạn body size. Một payload 500 KB với hàng chục nghìn object nhỏ hoặc độ sâu cực lớn vẫn có thể gây tải đáng kể.

### Các giới hạn cho JSON

Một policy JSON có thể quy định:

| Thuộc tính | Ví dụ giới hạn minh họa |
|---|---:|
| Request body sau giải nén | 1 MB |
| Nesting depth | 32 cấp |
| Tổng token/node | 20.000 |
| Số phần tử trong một array | 1.000 |
| Số field trong một object | 100 |
| Độ dài string | 8.000 ký tự |
| Độ dài number token | 64 ký tự |

Đây chỉ là giá trị ví dụ. Giới hạn thật cần dựa trên schema và use case. Với endpoint batch, có thể cần giới hạn thấp hơn; với import hợp lệ, có thể dùng cơ chế upload/tác vụ riêng thay vì nâng body limit cho toàn bộ API.

Nên từ chối duplicate key hoặc định nghĩa rõ cách xử lý để gateway, validator và backend không diễn giải cùng một JSON theo các giá trị khác nhau. Không để parser bỏ qua một số trường trong khi tầng authorization lại đọc giá trị khác.

## 8. Kiểm soát XML, YAML, multipart và archive

Nested payload không chỉ là JSON. Mỗi định dạng có đặc điểm riêng:

| Định dạng | Rủi ro | Kiểm soát chính |
|---|---|---|
| XML | XXE, entity expansion, cấu trúc lồng sâu | Tắt DTD/external entities, secure processing, giới hạn depth/node/bytes |
| YAML | Alias/anchor expansion, object construction nguy hiểm | Safe constructor, tắt tag không tin cậy, giới hạn alias/depth/node |
| Multipart | Quá nhiều part, field lớn, filename/path bất thường | Giới hạn tổng request, số part, field size, file size và tên file |
| ZIP/TAR | Zip bomb, archive traversal, số lượng entry lớn | Giới hạn entry count, tổng size giải nén, ratio, path canonicalization |
| GraphQL | Query depth/complexity lớn, alias lặp | Depth limit, complexity/cost analysis, pagination và timeout |

Với XML, cần tắt external entity và DTD khi không có nhu cầu nghiệp vụ. Với YAML, chỉ dùng chế độ parse an toàn; không cho payload bên ngoài khởi tạo object/class tùy ý. Với archive, không ghi entry theo path trực tiếp; chuẩn hóa và xác minh đường dẫn nằm trong thư mục đích sau khi giải mã, đồng thời ngăn symlink/path traversal.

## 9. Giới hạn độ phức tạp theo schema và business rule

Parser chỉ biết cấu trúc cú pháp. Ứng dụng cần kiểm tra ý nghĩa và chi phí nghiệp vụ:

- Số lượng item trong batch không vượt mức cho phép.
- Mỗi ID tham chiếu có kiểu hợp lệ và thuộc phạm vi caller.
- Số tầng nested object phù hợp với domain model.
- Không cho phép client gửi cây quan hệ tùy ý hoặc yêu cầu expand mọi relation.
- Field filter, sort và projection phải thuộc allowlist.
- Không cho phép query có độ sâu hoặc số phép join không giới hạn.
- Các thao tác lồng nhau phải có giới hạn số side effect và tổng cost.

Ví dụ một endpoint tạo đơn hàng có thể nhận tối đa 50 item. Nếu client gửi 50 item nhưng mỗi item có mảng con hàng nghìn phần tử, giới hạn item ngoài cùng không đủ. Hãy xác định giới hạn cho từng collection lồng nhau và tổng số node/operation của request.

Với GraphQL, giới hạn số byte query không đủ vì một query ngắn có thể yêu cầu dữ liệu lồng sâu và nhân bản qua alias. Cần giới hạn depth, complexity/cost, pagination và resolver concurrency; nên phân tích query trước khi thực thi.

## 10. Đọc response theo streaming thay vì buffer không giới hạn

Một lỗi thường gặp là tải toàn bộ response vào `byte[]` hoặc `String` rồi mới kiểm tra độ dài. Khi đó, bộ nhớ đã bị tiêu thụ trước khi giới hạn được áp dụng.

Mẫu xử lý an toàn:

1. Kiểm tra status, header và `Content-Length` nếu có để từ chối sớm.
2. Mở response stream và đọc từng chunk.
3. Cộng dồn số byte thực tế; dừng ngay khi vượt giới hạn.
4. Nếu có giải nén, đếm cả compressed và decompressed bytes.
5. Áp dụng deadline/read timeout trong lúc đọc.
6. Ghi vào buffer giới hạn hoặc file tạm có quota, không giữ toàn bộ dữ liệu lớn trong heap.
7. Chỉ chuyển sang parser sau khi content type, kích thước và policy đã đạt.
8. Đóng stream, response và xóa file tạm trong mọi đường thành công/thất bại.

Nếu API cần chuyển tiếp dữ liệu lớn cho client, có thể stream qua response với backpressure và giới hạn tổng bytes/thời gian. Không cần giữ toàn bộ response trong bộ nhớ. Tuy nhiên, vẫn phải xác minh quyền, loại nội dung và chính sách cache trước khi gửi dữ liệu ra ngoài.

## 11. Ví dụ cấu hình WebClient với Reactor Netty

Với Spring WebFlux, có thể cấu hình HTTP client không tự theo redirect, giới hạn thời gian và giới hạn dữ liệu mà codec được phép buffer:

```java
@Bean
WebClient externalFetchClient() {
    HttpClient httpClient = HttpClient.create(
            ConnectionProvider.builder("external-fetch")
                .maxConnections(50)
                .pendingAcquireMaxCount(100)
                .build())
        .followRedirect(false)
        .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 3_000)
        .responseTimeout(Duration.ofSeconds(5));

    return WebClient.builder()
        .clientConnector(new ReactorClientHttpConnector(httpClient))
        .codecs(codecs -> codecs.defaultCodecs()
            .maxInMemorySize(2 * 1024 * 1024))
        .build();
}
```

Đây là cấu hình minh họa, cần các dependency/import Reactor Netty và Spring WebFlux tương thích với phiên bản dự án. `followRedirect(false)` buộc ứng dụng tự quyết định redirect; `responseTimeout` không thay thế deadline tổng cho toàn bộ quá trình; `maxInMemorySize` giới hạn dữ liệu codec buffer trong các đường xử lý tương ứng, không phải giới hạn byte tổng cho mọi response streaming. `maxConnections` và pending acquire giới hạn áp lực lên connection pool, không thay thế rate limit theo client.

Khi đọc response lớn, dùng API streaming và tự đếm byte. Nếu gọi `bodyToMono(String.class)` hoặc `bodyToMono(byte[].class)`, dữ liệu thường phải được buffer để tạo giá trị cuối cùng; không dùng cách đó cho response không có giới hạn rõ.

### Luồng xử lý redirect có kiểm soát

Có thể mô hình hóa bằng pseudocode:

```text
currentUri = validateInitialUri(inputUrl)
deadline = now + overallTimeout

for hop from 0 to maxRedirects:
    assert deadline not expired
    validate scheme, host, port and DNS/IP for currentUri
    request = build GET without forwarding credentials to new origin
    response = send with auto-redirect disabled and bounded timeouts

    if response is not redirect:
        validate status, headers and content type
        stream body while counting wire/decoded bytes
        stop when any size/deadline limit is exceeded
        return bounded result

    if redirect is not allowed or hop == maxRedirects:
        reject response

    nextUri = resolve Location against currentUri
    validate nextUri from the beginning
    close current response
    currentUri = nextUri

reject redirect limit exceeded
```

Pseudocode nhấn mạnh rằng mỗi hop phải được kiểm tra lại. Trong triển khai thực tế, cần bảo đảm DNS/IP được kiểm tra gắn với kết nối thực tế hoặc được kiểm soát ở egress proxy; chỉ gọi `InetAddress.getAllByName()` rồi để HTTP client tự phân giải lại có thể vẫn còn khoảng TOCTOU.

## 12. Giới hạn ở gateway, application và network

Không đặt toàn bộ trách nhiệm ở một lớp:

| Lớp | Giới hạn phù hợp |
|---|---|
| CDN/WAF/API gateway | Request body size, header size, rate limit, timeout, số kết nối, upload limit |
| Application server | Schema validation, nested depth, số phần tử, business cost, concurrency |
| HTTP client outbound | Redirect policy, connect/read/overall timeout, response bytes, content encoding |
| Parser/decoder | Depth, token/node count, string/number length, archive expansion |
| Network/egress | Allowlist destination, chặn private/metadata ranges, giới hạn outbound |
| Worker/queue | Queue length, job concurrency, deadline, retry count, dead-letter policy |
| OS/container | CPU, memory, file descriptor, ephemeral storage và process limit |

Gateway có thể từ chối body lớn trước khi ứng dụng nhận request, nhưng không biết đầy đủ business cost của từng payload. Application hiểu schema và quyền, nhưng cần network egress policy để ngăn kết nối nội bộ. Các lớp bổ sung cho nhau.

## 13. Xử lý lỗi khi vượt giới hạn

Chọn status code phù hợp với loại giới hạn và hướng dẫn client sửa request hoặc thử lại:

| Tình huống | HTTP status thường dùng | Mã lỗi gợi ý |
|---|---:|---|
| Request body vượt giới hạn | `413 Content Too Large` | `REQUEST_BODY_TOO_LARGE` |
| Nested depth hoặc số node vượt schema limit | `400` hoặc `422` theo contract | `PAYLOAD_COMPLEXITY_LIMIT_EXCEEDED` |
| Response upstream quá lớn khi server fetch hộ | `502` hoặc lỗi nghiệp vụ fetch theo contract | `UPSTREAM_RESPONSE_TOO_LARGE` |
| Redirect vượt số hop | `502` hoặc lỗi policy theo contract | `REDIRECT_LIMIT_EXCEEDED` |
| Đích redirect bị policy chặn | `400`, `403` hoặc lỗi fetch theo contract | `REDIRECT_TARGET_NOT_ALLOWED` |
| Quá thời gian chờ upstream | `504 Gateway Timeout` | `UPSTREAM_TIMEOUT` |
| Quá giới hạn request đồng thời | `429` hoặc `503` theo lớp áp dụng | `CONCURRENCY_LIMIT_EXCEEDED` |

Không trả URL nội bộ, IP bị chặn, kết quả DNS hoặc chi tiết firewall cho caller nếu điều đó giúp dò mạng nội bộ. Có thể trả thông báo chung rằng đích không được phép. Log nội bộ giữ reason code và request ID để điều tra.

Nếu server đang fetch URL thay mặt client, lỗi response quá lớn là lỗi xử lý upstream; không nên trả `413` như thể chính request body của client vượt giới hạn, trừ khi contract định nghĩa rõ đây là giới hạn của thao tác client yêu cầu.

## 14. Bảo vệ retry và tác vụ bất đồng bộ

Một request fetch có thể timeout sau khi upstream đã xử lý xong hoặc worker có thể chết giữa lúc tải response. Retry không kiểm soát có thể tạo nhiều kết nối và tải lặp cùng một tài nguyên lớn.

Hãy áp dụng:

- Giới hạn số lần retry và dùng exponential backoff với jitter.
- Chỉ retry lỗi tạm thời; không retry lỗi scheme/host bị policy chặn hoặc payload vượt giới hạn.
- Đặt deadline tổng xuyên suốt retry, không reset timeout cho mỗi lần thử.
- Dùng idempotency key hoặc job ID cho tác vụ có side effect.
- Giới hạn số job trong queue và số worker đồng thời.
- Hủy fetch khi client hủy request nếu nghiệp vụ cho phép; không để upstream tiếp tục tiêu thụ tài nguyên vô ích.
- Ghi trạng thái job và dọn dữ liệu tạm khi retry hoặc thất bại.

Retry không được phép vượt qua policy redirect, response size hoặc nested payload. Mọi lần thử lại phải chịu cùng giới hạn hoặc giới hạn chặt hơn.

## 15. Kiểm thử redirect, response size và nested payload

Kiểm thử cần bao gồm cả đường hợp lệ, biên giới và dữ liệu độc hại. Có thể dùng mock HTTP server trong môi trường test để điều khiển redirect, header và body.

| Nhóm | Ca kiểm thử |
|---|---|
| Redirect count | 0, đúng số hop tối đa và vượt một hop |
| Redirect loop | A chuyển B, B chuyển lại A |
| Redirect scheme | HTTPS sang HTTP, `file:`, scheme không hỗ trợ |
| Redirect host | Host ngoài allowlist, port khác, hostname dạng IP |
| DNS/IP | Loopback, private, link-local, IPv6 local, CNAME tới IP bị chặn, nhiều A/AAAA record |
| DNS rebinding | DNS trả IP công khai khi check rồi đổi sang IP nội bộ trước connect |
| Credential forwarding | Redirect cross-origin không mang Authorization/cookie/API key |
| Redirect method | `301/302/303/307/308` không làm thay đổi method/body ngoài policy |
| Response size | Content-Length lớn, nhỏ giả, thiếu, chunked và body vượt giới hạn giữa stream |
| Compression | Gzip/brotli expansion, encoding không hỗ trợ, nhiều lớp nén |
| Timeout | Connect chậm, header chậm, body chậm, stream treo và tổng deadline hết |
| Headers | Quá nhiều header, header quá dài hoặc giá trị bất thường |
| Nested JSON | Depth vượt ngưỡng, array lớn, nhiều node, string/number quá dài, duplicate key |
| XML/YAML | XXE, entity expansion, alias expansion, depth lớn và tag không được phép |
| Multipart/archive | Quá nhiều part, file lớn, zip bomb, archive path traversal |
| Concurrency | Nhiều fetch lớn đồng thời, connection pool đầy và queue vượt giới hạn |
| Cleanup | Stream/connection/file tạm được đóng và dọn khi thành công, lỗi hoặc cancel |

Test phải xác nhận không chỉ status code mà cả số byte đã đọc, số kết nối mở, thời gian, queue, memory behavior và side effect. Với DNS rebinding, cần kiểm thử ở lớp resolver/egress proxy thực tế; mock URL parser đơn thuần không đủ.

## 16. Giám sát việc tiêu thụ tài nguyên

Các metric hữu ích gồm:

- Số redirect mỗi request, số redirect bị từ chối và số lần vượt hop limit.
- Host/scheme/port category của đích đến theo allowlist, không ghi query chứa bí mật.
- Compressed bytes, decoded bytes, expansion ratio và response body bị cắt do limit.
- Thời gian connect, thời gian nhận header, thời gian đọc body và overall duration.
- Số request bị từ chối do nested depth, node count, string length hoặc body size.
- HTTP client connection pool usage, pending acquire, timeout và connection reset.
- CPU, heap, garbage collection, temporary storage, queue length và worker concurrency.
- Số lần retry, cancellation và job bị đưa vào dead-letter queue.

Không ghi raw URL có query token, header Authorization, cookie hoặc body nhạy cảm. Có thể log scheme, host đã chuẩn hóa, port, route template, reason code, request ID và kích thước đã đo. Host/IP cần được xử lý theo chính sách dữ liệu và quyền truy cập log.

Đặt cảnh báo khi số redirect trung bình tăng bất thường, response expansion ratio cao, nhiều request bị chặn vì body lớn, connection pool cạn, heap/CPU tăng hoặc queue kéo dài. Một sự kiện riêng lẻ chưa chắc là tấn công; cần kết hợp identity, tenant, endpoint và pattern sử dụng.

## 17. Checklist giới hạn redirect, response size và nested payload

- [ ] Redirect được tắt hoặc kiểm soát thủ công theo allowlist và số hop tối đa.
- [ ] Mỗi `Location` được parse, chuẩn hóa và xác minh scheme/host/port/DNS/IP lại từ đầu.
- [ ] Có bảo vệ DNS rebinding/TOCTOU và egress policy chặn mạng nội bộ/metadata.
- [ ] Không chuyển tiếp Authorization, cookie, API key hoặc credential sang origin khác.
- [ ] Có connect timeout, read timeout, overall deadline, header limit và concurrency limit.
- [ ] Không tin riêng `Content-Length`; đếm byte thực tế trong stream.
- [ ] Giới hạn compressed bytes, decoded bytes, expansion ratio và dung lượng tạm.
- [ ] Content-Type và định dạng thực tế được kiểm tra theo allowlist.
- [ ] JSON/XML/YAML/multipart/archive có giới hạn depth, node, field, item, string, number và entry.
- [ ] GraphQL hoặc truy vấn lồng nhau có depth/cost limit và pagination.
- [ ] Parser và decoder không buffer toàn bộ dữ liệu không giới hạn.
- [ ] Retry có backoff, giới hạn số lần, deadline tổng và idempotency phù hợp.
- [ ] Queue, worker, connection pool, CPU, memory và temporary storage có giới hạn.
- [ ] Test bao gồm redirect loop, cross-origin, DNS rebinding, decompression bomb và nested payload cực đoan.
- [ ] Log/metric đủ phát hiện lạm dụng nhưng không ghi token, URL secret hoặc body nhạy cảm.

## Kết luận

Redirect, response size và nested payload đều có thể khuếch đại một request nhỏ thành nhiều kết nối, nhiều byte, nhiều object hoặc một lượng xử lý rất lớn. Hãy kiểm soát từng redirect và đích IP thực tế, không chuyển credential qua origin khác, đếm byte khi streaming cả trước và sau giải nén, đồng thời giới hạn độ sâu và độ phức tạp của mọi định dạng payload. Kết hợp timeout tổng, concurrency, egress policy, parser constraints, kiểm thử và giám sát giúp API tiêu thụ dữ liệu từ client/upstream trong một ngân sách tài nguyên xác định.
