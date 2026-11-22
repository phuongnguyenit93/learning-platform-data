# Kiểm tra scheme, máy đích, cổng và đường dẫn trước khi mở kết nối

## 1. Vì sao phải kiểm tra URI/URL trước khi kết nối?

Giả sử một ứng dụng Java nhận chuỗi URL từ người dùng để gọi API, tải một tài nguyên hoặc chuyển tiếp request. Nếu ứng dụng chỉ kiểm tra rằng chuỗi “trông giống một URL” rồi gọi `HttpClient.send(...)` hoặc `URL.openStream()`, nó có thể gửi kết nối đến sai giao thức, sai máy, sai cổng hoặc sai đường dẫn. Ngay cả URL hợp lệ theo cú pháp cũng có thể **không được phép theo chính sách của ứng dụng**.

Bài học này tập trung vào một thao tác cụ thể: **xác thực đầu vào URL/URI và quyết định đích kết nối trước hành động gây I/O mạng**, trong bối cảnh Java Advanced Networking. Các lớp bảo vệ cần thiết khi đích do bên ngoài kiểm soát cũng được giải thích, đặc biệt khi phòng tránh Server-Side Request Forgery (SSRF).

Sau bài học, bạn cần:
- Phân rã một URI thành **scheme**, **authority/host**, **port**, **path**, **query** và **fragment** mà không dựa vào xử lý chuỗi tùy tiện.
- Thiết kế **allowlist rõ ràng** cho scheme, host, port, đường dẫn; phát hiện user-info, authority sai cú pháp và đường dẫn bị mã hóa/chuẩn hóa không như dự kiến.
- Dùng `java.net.URI` để kiểm tra đầu vào trước khi mở kết nối bằng `java.net.http.HttpClient`; hiểu sự khác nhau giữa **kiểm tra chuỗi URI** và **kiểm soát máy thật sự được kết nối sau DNS**.
- Xử lý đúng URL tương đối, redirect, DNS rebinding, proxy, IPv4/IPv6, timeout và các lỗi phổ biến.

**Nguyên tắc:** “URL parse thành công” chỉ chứng minh một phần cú pháp; “URL đã được duyệt” phải có nghĩa là tất cả chính sách cho **đích và tài nguyên cụ thể** đều đã được kiểm tra. Việc mở socket vẫn cần các kiểm soát mạng tương ứng.

## 2. Giải phẫu một địa chỉ URL

Xét chuỗi:

```text
https://api.example.com:8443/v1/items/42?lang=vi#details
└─┬─┘ └──────┬─────┘ └┬─┘ └─────┬────┘ └──┬──┘ └──┬──┘
scheme       host     port      path       query   fragment
```

| Thành phần | Ý nghĩa | API trong `java.net.URI` | Vấn đề cần kiểm tra |
| --- | --- | --- | --- |
| Scheme | Giao thức/cách diễn giải tài nguyên, ví dụ `https` | `getScheme()` | Chỉ cho phép protocol mà ứng dụng chủ đích hỗ trợ |
| Authority | Phần sau `//`, có thể chứa user-info, host và port | `getRawAuthority()` | Không tin nguyên chuỗi authority hoặc tách bằng dấu `:` một cách thủ công |
| Host | Tên DNS hoặc IP literal | `getHost()` | Host phải có mặt, parse được và nằm trong danh sách đích hợp lệ |
| User-info | Phần trước `@` trong authority | `getRawUserInfo()` | Thường từ chối; dễ gây nhầm người đọc và rò rỉ credential |
| Port | Cổng TCP đích | `getPort()` | `-1` nghĩa là không khai báo tường minh, **không** có nghĩa port -1 sẽ được kết nối |
| Path | Đường dẫn tài nguyên trên server | `getRawPath()` / `getPath()` | Kiểm tra đúng route, dot-segment, percent-encoding và quy tắc decode |
| Query | Tham số sau `?` | `getRawQuery()` | Không phải path; có thể ảnh hưởng xử lý nghiệp vụ nên cần chính sách riêng |
| Fragment | Phần sau `#` | `getRawFragment()` | Không gửi như phần HTTP request-target; thường không cần trong URL backend |

`URI` có thể là **absolute** (`https://...`) hoặc **relative** (`../items`, `//other.example/path`). URI absolute cũng có thể là **opaque** như `mailto:name@example.com`. Một request HTTP thông thường cần URI **absolute, hierarchical**, có scheme và host hợp lệ.

Các phương thức `URI` chỉ phân tích cú pháp, **không tự gửi request**. Có thể kiểm tra rất nhiều URI bất hợp lệ/không được phép mà không phát sinh bất kỳ kết nối mạng nào.

## 3. Xây dựng chính sách từ nhu cầu kết nối thực tế

Trước khi viết code, trả lời bốn câu hỏi:

1. **Scheme nào được phép?** Ví dụ dịch vụ chỉ gọi HTTPS thì chỉ nhận `https`. Không có lý do tự động cho phép `http`, `file`, `jar`, `ftp`, `gopher` hay bất kỳ protocol khác.
2. **Máy đích nào được phép?** Ví dụ đúng một host `api.example.com`; nếu cho nhiều host, liệt kê cụ thể thay vì chấp nhận một chuỗi “có chứa example.com”.
3. **Cổng nào được phép?** Nếu gọi HTTPS chuẩn thì port có hiệu lực là 443. Phân biệt URL bỏ port với URL chỉ định 443; từ chối 80, 8080, 8443… nếu hệ thống không cho phép.
4. **Đường dẫn nào được phép?** Ví dụ chỉ gọi `/v1/items` và `/v1/items/<id>` với `id` giới hạn. Đừng dùng điều kiện quá rộng `path.startsWith("/v1")` vì nó cũng có thể nhận `/v1-admin`.

Đối với ứng dụng chỉ có một vài đích tin cậy, **allowlist theo (scheme, host, port, path)** thường rõ ràng và an toàn hơn blacklist tên/địa chỉ “nguy hiểm”. Chính sách cần được xác định theo nghiệp vụ; ví dụ dưới đây cố ý dùng chính sách hẹp để dễ chứng minh.

Một trình tự kiểm tra hợp lý:

```text
Chuỗi đầu vào
    │
    ▼
URI parse (không I/O mạng)
    │
    ├── Không hợp lệ / relative / opaque ──────────► TỪ CHỐI
    ▼
Scheme trong allowlist?
    │
    ├── Không ──────────────────────────────────────► TỪ CHỐI
    ▼
Host parse được? Không user-info? Host được phép?
    │
    ├── Không ──────────────────────────────────────► TỪ CHỐI
    ▼
Port hiệu lực được phép?
    │
    ├── Không ──────────────────────────────────────► TỪ CHỐI
    ▼
Path + query + fragment theo chính sách?
    │
    ├── Không ──────────────────────────────────────► TỪ CHỐI
    ▼
URI qua kiểm tra cú pháp/nghiệp vụ
    │
    ▼
Kiểm soát DNS, IP đích, proxy, redirect, egress
    │
    ▼
Mới cho HTTP client tạo kết nối
```

Sơ đồ thể hiện các **lớp kiểm tra độc lập**. Qua được phần chuỗi URI không có nghĩa là đã hoàn thành bước DNS/IP hoặc kiểm soát mạng.

## 4. Kiểm tra scheme đúng cách

Scheme của URI có thể viết khác chữ hoa/thường theo cú pháp, vì vậy dùng `equalsIgnoreCase` hoặc chuẩn hóa để so sánh.

```java
URI uri = URI.create("HTTPS://api.example.com/v1/items");
boolean allowed = "https".equalsIgnoreCase(uri.getScheme());
```

Đoạn trên chỉ minh họa phép so sánh scheme, **chưa đủ** để duyệt một URL. Những đầu vào sau có ý nghĩa khác hẳn:

| Đầu vào | Đánh giá |
| --- | --- |
| `https://api.example.com/v1/items` | Ứng viên hợp lệ cho chính sách HTTPS |
| `http://api.example.com/v1/items` | Phải từ chối nếu yêu cầu HTTPS |
| `file:///etc/hosts` | Scheme khác; không dùng như HTTP endpoint |
| `mailto:user@example.com` | URI absolute nhưng **opaque**, không có host HTTP |
| `//api.example.com/v1/items` | URI network-path reference, **chưa có scheme** |
| `/v1/items` | URI relative, cần trusted base nếu nghiệp vụ cho phép |
| `javascript:...` | Scheme khác, không phải địa chỉ HTTP server mà ứng dụng được phép mở |

Không dùng `startsWith("https")` để xác minh scheme: một chuỗi có thể chỉ tình cờ bắt đầu bằng các ký tự đó. Hãy parse bằng `URI` rồi xét `getScheme()`, `isAbsolute()`, `isOpaque()`.

**HTTPS không tự giải quyết mọi rủi ro:** một request `https` vẫn có thể đi tới host nội bộ không được phép, redirect sang nơi khác hoặc chọn đích ngoài chính sách do DNS/proxy. HTTPS bảo vệ đường truyền và xác thực tên khi cấu hình đúng; nó không thay thế kiểm soát đích.

## 5. Kiểm tra host, authority và danh tính máy đích

### 5.1. Dùng `getHost()`, không tách URL bằng chuỗi

Ví dụ:

```text
https://api.example.com.evil.test/v1/items
https://api.example.com@evil.test/v1/items
https://user:secret@api.example.com/v1/items
https://api.example.com:badport/v1/items
https://[::1]:443/v1/items
```

- Chuỗi đầu chỉ **chứa** tên miền được tin ở đầu; host thực tế là `api.example.com.evil.test`.
- Chuỗi thứ hai có phần `api.example.com` là **user-info**, host thực tế là `evil.test`.
- Chuỗi thứ ba thực sự trỏ tới `api.example.com` nhưng kèm user-info có thể gây nhầm, rò rỉ mật khẩu qua log/history hoặc qua các cách xử lý khác. Chính sách API thông thường nên từ chối user-info.
- Chuỗi thứ tư có authority không parse được thành server-based host/port hợp lệ trong Java `URI`; `getHost()` có thể trả `null`. Không được coi `getPort() == -1` của chuỗi này là “thiếu port hợp lệ” rồi chấp nhận.
- Chuỗi cuối là IPv6 loopback literal. Dấu hai chấm thuộc cú pháp địa chỉ IPv6 bên trong `[...]`; không tách host/port bằng `split(":")`.

Dùng `getRawAuthority()` để phục vụ chẩn đoán, nhưng **không** so sánh nguyên authority như một host. Dùng `getHost()` để lấy host đã được URI parser nhận diện, `getRawUserInfo()` để từ chối credential trong URL và `getPort()` để xác định port tường minh.

### 5.2. So khớp host chính xác

- Tên DNS không phân biệt hoa/thường: có thể chuẩn hóa `toLowerCase(Locale.ROOT)` rồi so khớp chính xác với allowlist. `Locale.ROOT` tránh những khác biệt chuyển chữ thường theo locale của JVM.
- **Không** dùng `contains("example.com")` hay `endsWith("example.com")` nếu chính sách chỉ cho đúng `api.example.com`.
- Nếu chính sách cho phép subdomain của `example.com`, cần định nghĩa chính xác việc nhận chính domain và/hoặc suffix có **ranh giới dấu chấm**, chẳng hạn `.example.com`; cần cân nhắc các subdomain chưa được kiểm soát, wildcard DNS và khả năng chiếm quyền subdomain.
- FQDN với dấu chấm cuối, IP literal, IPv6 trong dấu `[]`, hostname quốc tế IDN/punycode và tên nội bộ đều cần chính sách rõ ràng. Đừng tự ý loại bỏ dấu chấm cuối, chuyển IDN hoặc thay IPv6 format theo cách không nhất quán với lớp kết nối.
- `URI.getHost()` có thể là `null` đối với authority không ở dạng host server-based mà Java nhận diện; **từ chối fail closed** trong chính sách yêu cầu HTTP(S) host.

Tên quốc tế có thể biểu diễn qua **Punycode** (`xn--...`). Java có `java.net.IDN.toASCII(...)`, nhưng nếu hệ thống muốn hỗ trợ Unicode domain, quy trình Unicode normalization/IDNA, hạn chế ký tự và so khớp dạng chuẩn phải được thiết kế thống nhất với HTTP client và DNS. Ví dụ thực hành bên dưới chủ động **chỉ allowlist một hostname ASCII**; nó không tự đổi hoặc chấp nhận các cách viết tên khác.

### 5.3. Host đúng cú pháp chưa bảo đảm IP đích được phép

Tên DNS có thể trỏ tới nhiều A/AAAA record; các bản ghi có thể thay đổi theo thời gian, theo resolver và vị trí mạng. Một tên hợp lệ có thể bất ngờ phân giải thành IP loopback, link-local, private/ULA hoặc mạng nội bộ nhạy cảm. Ngược lại, IP có thể được viết theo nhiều cách khác nhau và được parser/resolver diễn giải khác nhau.

Đối với URL do người dùng tùy ý cung cấp (webhook, image fetcher, URL preview, proxy), cần xem đây là bài toán **SSRF**: kiểm soát IP đích ở bước kết nối, không chỉ kiểm tra chuỗi host. Đọc mục 10 để thấy vì sao gọi `InetAddress.getAllByName(...)` rồi vài mili-giây sau để `HttpClient` tự resolve lại **chưa phải biện pháp hoàn chỉnh**.

## 6. Kiểm tra port và port mặc định

`URI.getPort()` trả:
- Một số nguyên khi URL khai báo cổng mà parser nhận diện, ví dụ `https://host:8443/a` → 8443.
- `-1` khi **không khai báo** cổng, ví dụ `https://host/a` → -1.

Để xác định port hiệu lực cho HTTP thông thường:

```text
http://host/a       -> port hiệu lực 80
https://host/a      -> port hiệu lực 443
https://host:443/a  -> port hiệu lực 443
https://host:8443/a -> port hiệu lực 8443
```

Hãy kiểm tra cả **scheme** trước khi áp quy tắc port mặc định; port mặc định là quy tắc của protocol/client, không phải một con số gắn cứng với mọi URI. Khi ghi policy, nêu rõ có cho phép port tường minh trùng default hay không.

Với một socket TCP/UDP nói chung, cổng đích hợp lệ là **1..65535**; port 0 thường dùng trong ngữ cảnh **bind local ephemeral port**, không phải một cổng đích hữu dụng để gọi service. URI parser không nhất thiết từ chối mọi trường hợp vượt miền cổng chỉ vì cú pháp port có chữ số. Ví dụ `https://host:99999/a` vẫn có thể trả `getPort() == 99999`, nên cần policy kiểm tra.

Ví dụ bài này chỉ cho phép HTTPS 443:
- `getPort() == -1` hoặc `getPort() == 443` → có thể tiếp tục.
- Mọi port khác → từ chối.
- Authority sai cú pháp, khiến `getHost() == null` → từ chối ở bước host, không rơi vào nhánh “mặc định 443”.

Đừng kiểm tra port bằng `endsWith(":443")` trên toàn URL: nó có thể nằm ở path, query, user-info hoặc khác ký pháp IPv6.

## 7. Kiểm tra đường dẫn: raw, decoded và chuẩn hóa

### 7.1. Raw path khác decoded path

Java cung cấp:
- `getRawPath()`: giữ nguyên chuỗi percent-encoding (ví dụ `%2F`, `%2e`).
- `getPath()`: trả về đường dẫn đã giải mã percent-encoding.
- `normalize()`: chuẩn hóa một số dot-segment *theo cú pháp URI* nhưng **không phải một bộ lọc bảo mật tổng quát**.

Ví dụ:

```text
URI:      https://api.example.com/v1/%2e%2e/admin
raw path: /v1/%2e%2e/admin
path:     /v1/../admin
```

Nếu ứng dụng chỉ kiểm tra `getRawPath().startsWith("/v1/")`, nó có thể chấp nhận một path mà server/proxy sau giải mã coi là `/admin`. Ngay cả `uri.normalize()` cũng không tự thay thế kiểm tra percent-encoded dot segment. Những cách viết `%2e`, `%2f`, `%5c` và chuỗi mã hóa lồng nhau có thể bị xử lý khác nhau ở proxy, router và backend.

Phép kiểm tra prefix rộng như `path.startsWith("/public")` cũng nhận `/public-admin` hoặc `/publicity`. Đường dẫn có thể chứa `/./`, `/../`, `//`, dấu `\`, phần trăm mã hóa, dấu chấm phức hợp hoặc Unicode normalization. Quy tắc xử lý phải thống nhất với **thành phần cuối cùng nhận request**.

### 7.2. Chọn chính sách path đúng với use case

Có hai hướng chính:

1. **API có tập route hẹp:** chỉ cho phép đúng các mẫu raw path mà ứng dụng sử dụng, chẳng hạn `/v1/items` hoặc `/v1/items/<id>` với ID theo regex ASCII. Đây là cách demo ở mục 8; nó *chủ động từ chối mọi percent-encoding trong path*, nên các biến thể được mã hóa không thể lách qua bộ so khớp.
2. **Ứng dụng cho phép path linh hoạt:** phải xác định rõ có chấp nhận encoded slash, Unicode, dấu chấm, nhiều lần decode hay không; canonicalize đúng một cách thống nhất với máy đích và xác minh cả sau bước resolve/redirect. Không nên dùng `URLDecoder` tùy tiện cho path: nó được thiết kế cho form encoding và có thể diễn giải dấu `+` thành khoảng trắng, không đúng mọi ngữ cảnh URL path.

**Quan trọng:** Không có một phép `normalize()` hay regex chung nào giải quyết mọi path traversal và authorization. Khi đường dẫn đại diện cho tài nguyên riêng tư, backend vẫn phải **ủy quyền theo tài nguyên cuối cùng**, ngoài bước kiểm tra URL của client.

### 7.3. Query và fragment không phải path

`https://host/v1/items?limit=10#section` có path `/v1/items`, query `limit=10` và fragment `section`. Nếu API chỉ cho phép `limit` từ 1 đến 50, việc path hợp lệ **không đồng nghĩa** query hợp lệ. Fragment thường không được gửi tới máy chủ HTTP; trong request backend, có thể từ chối để tránh mơ hồ.

Quy tắc ví dụ: chấp nhận query trống, hoặc đúng một tham số `limit=<1..50>`; từ chối các tham số khác, giá trị không hợp lệ, nhiều tham số hoặc fragment. Chính sách này **cố ý rất hẹp** và chỉ nhằm minh họa kiểm tra cụ thể trước khi kết nối.

## 8. Ví dụ Java 17+: kiểm tra toàn bộ URI mà không truy cập mạng

**Bài toán:** service chỉ được gọi HTTPS tới host `api.example.com`, port 443, một trong hai dạng path:
- `/v1/items`
- `/v1/items/<id>`, trong đó `id` có 1–32 ký tự chữ cái ASCII, chữ số, `_` hoặc `-`.

Cho phép query trống hoặc `limit=1..50`; không cho user-info, fragment, percent-encoding trong path hoặc URL relative. Ví dụ sử dụng `URI` thuần, **không resolve DNS và không mở socket**. Nó kiểm tra phần chuỗi URL với chính sách cụ thể; các kiểm soát mạng còn lại được trình bày ở mục 10–11.

Lưu file `UrlPreflight.java`:

```java
import java.net.URI;
import java.net.URISyntaxException;
import java.util.Locale;
import java.util.Set;
import java.util.regex.Pattern;

public class UrlPreflight {
    private static final Set<String> HOSTS = Set.of("api.example.com");
    private static final Pattern PATH =
            Pattern.compile("/v1/items(?:/[A-Za-z0-9_-]{1,32})?");
    private static final Pattern QUERY =
            Pattern.compile("limit=(?:[1-9]|[1-4][0-9]|50)");

    public record Approved(URI uri, String host, int port, String rawPath) { }

    public static Approved validate(String input) {
        if (input == null || input.length() > 2048) {
            throw new IllegalArgumentException("input");
        }
        final URI uri;
        try {
            uri = new URI(input);
        } catch (URISyntaxException ex) {
            throw new IllegalArgumentException("syntax");
        }
        if (!uri.isAbsolute() || uri.isOpaque()) {
            throw new IllegalArgumentException("absolute URI");
        }
        if (!"https".equalsIgnoreCase(uri.getScheme())) {
            throw new IllegalArgumentException("scheme");
        }
        if (uri.getRawUserInfo() != null) {
            throw new IllegalArgumentException("userinfo");
        }
        String host = uri.getHost();
        if (host == null || !HOSTS.contains(host.toLowerCase(Locale.ROOT))) {
            throw new IllegalArgumentException("host");
        }
        int explicitPort = uri.getPort();
        if (explicitPort != -1 && explicitPort != 443) {
            throw new IllegalArgumentException("port");
        }
        if (uri.getRawFragment() != null) {
            throw new IllegalArgumentException("fragment");
        }
        String rawPath = uri.getRawPath();
        if (rawPath == null || !PATH.matcher(rawPath).matches()) {
            throw new IllegalArgumentException("path");
        }
        String rawQuery = uri.getRawQuery();
        if (rawQuery != null && !QUERY.matcher(rawQuery).matches()) {
            throw new IllegalArgumentException("query");
        }
        return new Approved(uri, host.toLowerCase(Locale.ROOT), 443, rawPath);
    }

    public static void main(String[] args) {
        String[] samples = {
            "https://api.example.com/v1/items",
            "HTTPS://API.EXAMPLE.COM:443/v1/items/Ab_7",
            "https://api.example.com/v1/items?limit=10",
            "http://api.example.com/v1/items",
            "https://api.example.com:8443/v1/items",
            "https://api.example.com.evil.test/v1/items",
            "https://user@api.example.com/v1/items",
            "https://api.example.com/v1/items/../admin",
            "https://api.example.com/v1/%2e%2e/admin",
            "https://api.example.com/v1/items/abc%2Fdef",
            "https://api.example.com/v1/items?limit=100",
            "//api.example.com/v1/items",
            "file:///tmp/private",
            "https://api.example.com/v1/items#section"
        };
        for (int i = 0; i < samples.length; i++) {
            try {
                Approved approved = validate(samples[i]);
                System.out.printf("%02d ACCEPT %s:%d %s%n",
                        i + 1, approved.host(), approved.port(), approved.rawPath());
            } catch (IllegalArgumentException ex) {
                System.out.printf("%02d REJECT %s%n", i + 1, ex.getMessage());
            }
        }
    }
}
```

Chạy bằng JDK 17 trở lên:

```bash
javac UrlPreflight.java
java UrlPreflight
```

Stdout chính xác với dữ liệu mẫu:

```text
01 ACCEPT api.example.com:443 /v1/items
02 ACCEPT api.example.com:443 /v1/items/Ab_7
03 ACCEPT api.example.com:443 /v1/items
04 REJECT scheme
05 REJECT port
06 REJECT host
07 REJECT userinfo
08 REJECT path
09 REJECT path
10 REJECT path
11 REJECT query
12 REJECT absolute URI
13 REJECT scheme
14 REJECT fragment
```

### Giải thích từng nhóm test

- **01–03 chấp nhận:** scheme/host không phân biệt hoa thường; port có thể được bỏ qua nếu mặc định là 443; query `limit=10` thuộc allowlist.
- **04 từ chối scheme:** HTTP khác HTTPS.
- **05 từ chối port:** server HTTPS trên 8443 không thuộc chính sách.
- **06 từ chối host:** chuỗi `api.example.com.evil.test` không bằng `api.example.com`.
- **07 từ chối user-info:** dấu `@` không được chấp nhận trong URL đầu vào.
- **08–10 từ chối path:** `..`, `%2e%2e`, `%2F` đều không phù hợp mẫu raw path đã định nghĩa.
- **11 từ chối query:** `limit=100` ngoài khoảng cho phép.
- **12 từ chối relative URI:** thiếu scheme; không tự lấy scheme từ nơi khác.
- **13 từ chối scheme file:** `file:///tmp/private` không phải HTTPS.
- **14 từ chối fragment:** phần `#section` không phục vụ nghiệp vụ request.

Ví dụ cố ý không dùng DNS; vì vậy kết quả luôn xác định và không phụ thuộc mạng. Kết quả `ACCEPT` ở đây có nghĩa là **qua bộ lọc URI này**, **chưa phải bảo đảm có quyền kết nối**. Trước khi deploy, thay allowlist placeholder bằng host thật do ứng dụng sở hữu/quản lý và áp dụng chính sách DNS/IP/egress ở mục 10.

### Tại sao mẫu path lại khắt khe?

`Pattern.compile("/v1/items(?:/[A-Za-z0-9_-]{1,32})?")` chỉ chấp nhận path gồm ký tự đã liệt kê và đúng cấu trúc route. Vì matcher `matches()` so toàn bộ chuỗi, các biến thể `/v1/items-extra`, `/v1/items/123/../../admin` và `/v1/items/%2e%2e` bị từ chối. Trong ứng dụng có ID chứa Unicode hoặc escape, bạn phải định nghĩa cách canonicalize và xác minh theo route cuối cùng, **không nới regex một cách tùy tiện**.

`URI` và `Approved` trong ví dụ bất biến; caller có thể truyền `approved.uri()` tới API HTTP sau khi các policy khác đã hoàn tất. Tránh tình trạng validate một chuỗi rồi nối thêm path/query từ input không tin cậy **sau** validation.

## 9. Xử lý URL tương đối và `URI.resolve`

Một URL tương đối như `/v1/items` không tự xác định được máy đích. Nếu nghiệp vụ nhận URL tương đối, chỉ resolve trên **base URI được cấu hình và tin cậy**, rồi chạy **toàn bộ policy trên URI kết quả**. Không resolve chuỗi do người dùng cung cấp lên base rồi mặc nhiên cho rằng đích vẫn nằm trong phạm vi trước đó.

Ví dụ:

```java
import java.net.URI;

public class ResolveDemo {
    public static void main(String[] args) {
        URI base = URI.create("https://api.example.com/v1/");
        System.out.println(base.resolve("items/42"));
        System.out.println(base.resolve("../admin"));
        System.out.println(base.resolve("//other.example/v1/items"));
    }
}
```

```bash
javac ResolveDemo.java
java ResolveDemo
```

```text
https://api.example.com/v1/items/42
https://api.example.com/admin
https://other.example/v1/items
```

Hai ví dụ sau có thể thoát khỏi path gốc hoặc thay host dù đầu vào là **relative reference**. Áp dụng `UrlPreflight.validate(resolved.toString())` trên kết quả; hai URI đó sẽ bị chính sách của mục 8 từ chối. Nếu chỉ cho phép một nhánh đường dẫn, cần kiểm tra **path sau resolve**, không chỉ path người dùng nhập trước resolve.

Lưu ý `normalize()` không phân quyền tài nguyên và không giải quyết hết các cách mã hóa. URI không thay đổi cấu trúc do backend hoặc proxy thực hiện sau đó, nên chính sách phải thống nhất xuyên tầng.

## 10. DNS, IP đích và SSRF: bước kiểm tra chuỗi chưa đủ

### 10.1. Một host được phép có thể phân giải tới IP bị cấm

Giả sử ứng dụng cho phép một hostname nhất định. Ở thời điểm kiểm tra, DNS trả một IP public; ngay sau đó, khi HTTP client tự tạo socket, resolver trả `127.0.0.1`, `10.x.x.x`, `169.254.x.x`, IPv6 loopback hoặc ULA. Đây là dạng **DNS rebinding / TOCTOU** (time of check versus time of use). Một phép `InetAddress.getAllByName(host)` đơn lẻ rồi để HTTP client **tự phân giải lần nữa** không ràng buộc IP đã kiểm tra với IP socket sẽ dùng.

Với tính năng nhận URL không tin cậy, một attacker có thể cố dẫn request của server tới nội bộ, ví dụ cổng quản trị, loopback, địa chỉ cloud metadata hoặc các dịch vụ không được công khai. Nguy cơ còn tồn tại nếu app kiểm tra `https` và regex tên miền nhưng **không kiểm soát đích ở kết nối thực tế**.

### 10.2. Hướng phòng vệ nhiều lớp

1. **Ưu tiên đích cố định:** nếu ứng dụng chỉ gọi API của đối tác, để người dùng chọn mã tài nguyên/tham số thay vì tự nhập URL host; cấu hình URL đích ở phía server.
2. **Allowlist scheme/host/port/path:** như ví dụ mục 8, chỉ chấp nhận những gì use case cần. Nếu cho phép IP literal, hãy dùng validator IP chuẩn, kiểm tra cả IPv4/IPv6 và phạm vi mạng được phép.
3. **Kiểm soát DNS/IP sau phân giải:** xét **tất cả** IP candidate (A/AAAA, CNAME khi liên quan), không chỉ IP đầu tiên; chặn các phạm vi không được phép như loopback, private/ULA, link-local, multicast, unspecified và các khối đặc biệt khác theo chính sách hệ thống. Chỉ dùng `isSiteLocalAddress()` là thiếu, vì nó không nhận diện đầy đủ IPv6 ULA và nhiều reserved ranges.
4. **Ràng buộc IP đã duyệt với kết nối:** sử dụng transport/client hoặc cơ chế mạng cho phép bảo đảm socket thực sự đi tới IP được phép, đồng thời vẫn kiểm tra TLS theo hostname đúng (Host, SNI, chứng chỉ). **Không** chỉ thay URL bằng IP rồi bỏ kiểm tra chứng chỉ/TLS.
5. **Chặn ở tầng mạng:** egress firewall, network policy, private subnet ACL, proxy được kiểm soát, hạn chế kết nối từ workload tới mạng quản trị/cloud metadata. Đây là lớp bảo vệ quan trọng khi URI code bị bypass.
6. **Kiểm tra lại ở mọi redirect, retry và fallback:** host/IP/port có thể thay đổi giữa các request.

**Ghi chú quan trọng:** Java `HttpClient` tiêu chuẩn không cung cấp một API đơn giản để “validate DNS A/AAAA rồi pin chính xác các IP ấy cho request này” trong mọi tình huống HTTPS, proxy và redirect. Đừng coi một đoạn gọi `getAllByName` là triển khai SSRF-resistant hoàn chỉnh. Ứng dụng yêu cầu bảo vệ SSRF mạnh cần transport/egress được quản trị phù hợp, cùng kiểm soát TLS.

### 10.3. Khi nào có thể dùng allowlist hostname đơn giản?

Đối với service chỉ gọi **một endpoint do tổ chức sở hữu** qua DNS tin cậy, allowlist chính xác và egress giới hạn thường là giải pháp tốt. Với URL “tùy ý trên Internet” do người dùng gửi vào, bề mặt tấn công rộng hơn nhiều; cần lớp IP, redirect, DNS và mạng chặt chẽ. Không suy ra “host public” chỉ vì không khớp ba dải private IPv4.

## 11. Redirect và thời điểm thực sự mở kết nối

Trong Java 17, `java.net.http.HttpClient` chỉ gửi request khi gọi `send(...)` hoặc `sendAsync(...)`, không phải lúc tạo `HttpRequest`. `URL.openConnection()` chỉ trả đối tượng `URLConnection`; kết nối thật thường diễn ra khi gọi `connect()` hoặc thao tác I/O như `getInputStream()`. Vì vậy phải chạy policy **trước** các hành động đó.

Một HTTP response `301`/`302`/`303`/`307`/`308` có thể chứa `Location` đến URL khác:
- `https://api.example.com/v1/items` → `https://internal.example/admin`
- `https://api.example.com/v1/items` → `http://api.example.com:8080/debug`
- `https://api.example.com/v1/items` → `//other.example/private`

Kiểm tra URL đầu tiên **không** tự động kiểm tra các URL được redirect tới.

Java `HttpClient.Redirect.NEVER` tắt theo redirect tự động (đây cũng là chính sách mặc định của builder Java 17). Khi dùng URL đầu vào nhạy cảm, nên cấu hình rõ `NEVER`; nếu nghiệp vụ cần theo redirect, xử lý theo từng bước, giới hạn số lần và chạy lại **đầy đủ** chính sách. Chú ý redirect tương đối cần resolve trên URI hiện tại trước khi validate.

### Mảnh code minh họa cho bước gọi HTTP

Đoạn sau là **mã nằm bên trong một phương thức**, sử dụng lớp `UrlPreflight` ở mục 8; không phải một file Java độc lập. Nó biểu diễn đúng thứ tự validate → tạo request → kết nối, không gửi request trong ví dụ bài này.

```java
UrlPreflight.Approved approved =
        UrlPreflight.validate(userSuppliedUrl);

// Các policy DNS/IP/egress bổ sung phải được thực thi bởi
// transport/network trước khi kết nối nếu URL không đáng tin.
HttpClient client = HttpClient.newBuilder()
        .followRedirects(HttpClient.Redirect.NEVER)
        .connectTimeout(Duration.ofSeconds(3))
        .build();

HttpRequest request = HttpRequest.newBuilder(approved.uri())
        .timeout(Duration.ofSeconds(10))
        .GET()
        .build();

HttpResponse<Void> response =
        client.send(request, HttpResponse.BodyHandlers.discarding());

// Nếu nghiệp vụ cho phép redirect, cần tự lấy Location,
// currentUri.resolve(location), validate URI đích mới,
// kiểm tra DNS/IP/egress lần nữa và giới hạn số lần redirect.
```

Các import cần thiết cho mảnh code: `java.net.http.HttpClient`, `HttpRequest`, `HttpResponse`, `java.time.Duration`. Biến `userSuppliedUrl` do caller cung cấp. Một triển khai thật cần xử lý `IOException`/`InterruptedException`, HTTP status, response size, timeout, hủy request và logging phù hợp; mảnh code trên chủ yếu giải thích **vị trí đặt bước preflight**.

**Lưu ý về proxy:** HTTP client có thể dùng proxy mặc định hoặc proxy được cấu hình. Proxy có thể là điểm thực hiện DNS/routing thực tế; chính sách kiểm soát host/IP cần phù hợp với **đường đi qua proxy**, không chỉ resolver tại ứng dụng.

## 12. Những biên đặc biệt cần quyết định bằng policy

### 12.1. Host là IP literal

`https://127.0.0.1/...`, `https://[::1]/...`, `https://169.254.169.254/...` hay một IP private không tự mang nghĩa “được phép” chỉ vì parse đúng. Một ứng dụng chỉ cho host `api.example.com` nên từ chối tất cả IP literal. Nếu ứng dụng cần hỗ trợ IP literal, hãy kiểm tra dạng IP **chuẩn và các dải được phép**, bao gồm IPv4-mapped IPv6, scope identifier và địa chỉ đặc biệt; đừng dựa vào blacklist chuỗi như `"127."`.

### 12.2. Tên miền quốc tế, dấu chấm cuối và tên gần giống

`api.example.com.` có thể là cách viết DNS absolute của cùng một tên trong một số hệ thống, nhưng chuỗi so khớp host chính xác của ví dụ sẽ **từ chối** vì nó không bằng `api.example.com`. Chính sách có thể chủ động chọn normalize chấm cuối, nhưng phải bảo đảm hành vi tương ứng ở resolver/TLS và logging. Homograph Unicode, IDN và tên miền trông gần giống cần xử lý riêng; đừng “tin theo mắt”.

### 12.3. Đường dẫn có dấu `?`, `#` hoặc nhiều lớp encode

`?` phân tách query và `#` phân tách fragment ở cú pháp URI; nếu muốn ký tự ấy là dữ liệu path thì phải percent-encode. Nhưng khi percent-encoding xuất hiện, server/proxy có thể giải mã; route authorization phải hiểu cùng cách diễn giải. Ví dụ chính sách ở mục 8 đơn giản hơn bằng cách **không cho phép percent-encoding trong path**.

### 12.4. Phân biệt HTTP URL và file path

`file:///var/log/app.log` là một URI có scheme `file`, không phải một URL HTTP. Tuyệt đối không chuyển một URL đầu vào tùy ý thành thao tác đọc file chỉ vì có thể gọi `toURL()` hoặc `openStream()`. Nếu nghiệp vụ là tải file từ filesystem thì phải xây dựng chính sách filesystem riêng: root directory được phép, xử lý symbolic links, real path và phân quyền file.

### 12.5. Chiều dài, query, request và tài nguyên

Giới hạn độ dài URL, số lượng tham số, loại method, request body và response size theo use case; đặt timeout và giới hạn retry. Bước preflight chỉ là một phần của giới hạn tài nguyên. Ví dụ giới hạn input 2.048 ký tự ở mục 8 là lựa chọn minh họa, **không phải chuẩn chung** cho mọi hệ thống.

## 13. Quy trình triển khai với lỗi rõ ràng

Một hàm preflight nên nhận chuỗi URL rồi trả về:
- **Đối tượng đã được duyệt** chứa URI và thông tin host/port/path đã xác nhận; hoặc
- **Lỗi có mã rõ ràng** (scheme/host/port/path/query…), để caller từ chối trước I/O.

Không nên:
- Validate URL rồi **nối** một chuỗi path do người dùng kiểm soát sau đó mà không validate lại.
- Dùng regex bao trùm toàn bộ URL mà không có URI parser để phân tách các thành phần.
- Trả nguyên nội dung URL (có thể chứa token/query bí mật) vào log hoặc exception; ưu tiên log mã từ chối và thông tin đã được làm sạch.
- Tự động đổi `http` thành `https` hoặc thay host/port/path không hợp lệ bằng giá trị “an toàn” rồi tiếp tục mà không có quy tắc nghiệp vụ rõ ràng.
- Cho phép HTTP client tự theo mọi redirect trong khi chỉ kiểm tra URL đầu tiên.
- Vô hiệu hóa xác minh TLS/chứng chỉ để “sửa” một lỗi kết nối.

Gợi ý cách kiểm thử theo lớp:

| Test | Đầu vào | Kỳ vọng |
| --- | --- | --- |
| Scheme | `http://api.example.com/v1/items` | Reject |
| Host giả giống | `https://api.example.com.evil.test/v1/items` | Reject |
| User-info | `https://api.example.com@evil.test/v1/items` | Reject (host thực tế là evil.test) |
| Port ngoài policy | `https://api.example.com:8443/v1/items` | Reject |
| Default HTTPS port | `https://api.example.com/v1/items` | Accept với port hiệu lực 443 |
| Path đúng | `https://api.example.com/v1/items/abc_2` | Accept |
| Prefix dễ nhầm | `https://api.example.com/v1/items-extra` | Reject |
| Dot segment | `https://api.example.com/v1/items/../admin` | Reject |
| Encoded dot/slash | `https://api.example.com/v1/%2e%2e/admin` | Reject |
| Query ngoài policy | `https://api.example.com/v1/items?limit=999` | Reject |
| Host đổi khi redirect | `Location: //other.example/secret` | Validate lại URI đích; reject theo host |
| DNS đổi sau check | hostname ban đầu public rồi resolve tới private | Phải bị chặn ở IP/transport/egress, **không thể chứng minh chỉ bằng hàm mục 8** |

Để test phần DNS/redirect mà không truy cập Internet thật, có thể dùng HTTP server giả lập hoặc controlled DNS trong môi trường tích hợp, đồng thời kiểm tra **socket đích thực tế**, không chỉ giá trị URL trả về từ hàm preflight.

## 14. Lỗi phổ biến và cách chẩn đoán

1. **“`new URI(input)` không ném lỗi nên có thể gọi mạng.”** Sai: parser không xác minh đích có nằm trong allowlist hoặc có quyền truy cập.
2. **“Host có chứa chuỗi tin cậy là ổn.”** Sai: `api.example.com.evil.test` là một host khác; `user@host` cũng khiến parsing khác dự đoán bằng mắt.
3. **“`getPort() == -1` luôn là port sai.”** Sai: thiếu port tường minh có thể dùng port mặc định theo scheme. Nhưng authority không parse được phải được từ chối từ bước host.
4. **“Path bắt đầu bằng prefix yêu cầu là được.”** Sai nếu không có ranh giới path segment; `/v1/items-admin`, `..` hoặc percent-encoding có thể dẫn đến tài nguyên khác.
5. **“`normalize()` xử lý tất cả path traversal.”** Sai: percent-encoding, double decoding và khác biệt giữa proxy/backend có thể làm kết quả khác dự kiến.
6. **“Đã kiểm tra IP từ DNS trước `send` nên socket chắc chắn tới IP đó.”** Sai nếu client lại resolve một lần nữa; đây là TOCTOU/DNS rebinding.
7. **“Đã chặn private IPv4 nên chắc chắn không tới mạng nội bộ.”** Sai: còn IPv6 loopback/ULA/link-local, IPv4-mapped address, shared/reserved ranges, proxy và kiến trúc mạng khác.
8. **“Chỉ có một URL ban đầu cần kiểm tra.”** Sai nếu client theo HTTP redirects hoặc caller resolve URI relative và đổi đích.
9. **“HTTPS bảo đảm URL an toàn.”** Sai: HTTPS không quyết định hostname có được policy cho phép, cũng không bảo vệ khỏi mọi SSRF nếu kết nối tới máy không mong muốn.
10. **“Đổi `URL` sang `URI` tự động giải quyết SSRF.”** Sai: URI giúp parse rõ ràng, còn SSRF cần chính sách đích và enforcement tại thời điểm kết nối.

Khi gặp lỗi kết nối, hãy xác định **URL sau resolve/redirect** và các thành phần scheme, host, port, path trước; sau đó kiểm tra DNS, routing, proxy, chứng chỉ TLS, firewall và timeout. Không dùng một lỗi kết nối mạng để suy ra URL input đã sai cú pháp, cũng không dùng parse thành công để suy ra máy đích có thể truy cập được.

## 15. Câu hỏi tự kiểm tra

**Câu 1.** Tại sao kiểm tra `input.startsWith("https://api.example.com")` không đủ?  
**Đáp án:** chuỗi `https://api.example.com.evil.test` vẫn khớp prefix nhưng host thực tế khác. Cần parse `URI` và so khớp host đầy đủ theo allowlist.

**Câu 2.** `https://api.example.com/v1/items` có `getPort() == -1`. Có lỗi không?  
**Đáp án:** không. Với HTTPS, 443 là port mặc định. Nếu chính sách chỉ cho 443, URL có thể hợp lệ sau khi các thành phần khác được duyệt.

**Câu 3.** Vì sao `getRawPath()` và `getPath()` cần được phân biệt?  
**Đáp án:** raw path giữ percent-encoding; decoded path có thể xuất hiện `..`, `/` hoặc ký tự khác. Không được giả định proxy và backend diễn giải giống một phép kiểm tra prefix trên raw string.

**Câu 4.** `URI.resolve("../admin")` trên base `https://api.example.com/v1/` trả gì? Có nằm trong chính sách bài ví dụ không?  
**Đáp án:** trả `https://api.example.com/admin`; bị từ chối do path không nằm trong tập route cho phép.

**Câu 5.** Vì sao chỉ gọi `InetAddress.getAllByName(host)` rồi `HttpClient.send` chưa chống DNS rebinding?  
**Đáp án:** client có thể phân giải lại và dùng IP khác lúc mở socket. Phải kiểm soát đích thực tế (connection binding/transport/egress), mọi IP ứng viên, redirect và retry.

**Câu 6.** Redirect `Location: //other.example/v1/items` được xử lý thế nào?  
**Đáp án:** resolve so với URI hiện tại tạo URL có host `other.example`, sau đó chạy lại scheme/host/port/path và DNS/IP/egress policy. Theo allowlist `api.example.com` của ví dụ, phải từ chối.

## 16. Tài liệu đối chiếu

- Java SE 17 `URI` (parser, raw/decoded components, normalize, resolve): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URI.html
- Java SE 17 `URL` và `URLConnection` (thời điểm mở connection): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URL.html
- Java SE 17 `HttpClient` (redirect policy, send): https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html
- Java SE 17 `HttpClient.Builder` (default redirect NEVER, timeout): https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.Builder.html
- OWASP Server-Side Request Forgery Prevention Cheat Sheet (allowlist, DNS rebinding và egress): https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html
- RFC 3986, Uniform Resource Identifier: Generic Syntax: https://www.rfc-editor.org/rfc/rfc3986
