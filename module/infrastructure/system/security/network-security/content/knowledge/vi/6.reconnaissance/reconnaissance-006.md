# Banner leakage: rò rỉ thông tin dịch vụ trong reconnaissance

Khi truy cập một dịch vụ, máy khách có thể nhận được thông tin về phần mềm, phiên bản, hệ điều hành, cấu trúc triển khai hoặc thành phần trung gian trước cả khi đăng nhập. Chẳng hạn, một phản hồi HTTP công khai chứa `Server: nginx/1.24.0`, hoặc màn hình lỗi công khai hiển thị tên framework và đường dẫn mã nguồn. Các dấu hiệu đó giúp quản trị viên kiểm kê hệ thống nhưng cũng có thể hỗ trợ người ngoài **nhận diện công nghệ và thu hẹp phạm vi tìm kiếm điểm yếu**.

Hiện tượng **banner leakage** (lộ thông tin qua banner/dấu hiệu nhận dạng dịch vụ) là nội dung quan trọng của giai đoạn **Reconnaissance** trong module **SECURITY_NETWORK_SECURITY**. Nắm được cách banner xuất hiện và cách xác minh chúng giúp bảo vệ hạ tầng mạng từ firewall, phân đoạn, VPN và IDS/IPS đến DNS, web/API, mạng không dây và dịch vụ đám mây. Bài này tập trung vào kiểm kê, phân tích nguy cơ và giảm tiết lộ thông tin trên **tài sản được phép kiểm tra**.

## 1. Banner là gì? Khi nào trở thành rò rỉ?

### 1.1. Khái niệm banner và fingerprint

**Banner** là chuỗi hoặc tập thông tin một dịch vụ cung cấp trong quá trình kết nối, bắt tay giao thức, yêu cầu/đáp ứng hoặc khi hiển thị lỗi. Banner có thể là dòng chào của SSH/SMTP/FTP, header HTTP, tên máy chủ, phiên bản server, hoặc trang lỗi chứa thông tin triển khai.

**Service fingerprinting** là quá trình suy đoán loại sản phẩm, phiên bản hoặc cấu hình từ một hay nhiều dấu hiệu: banner, thông điệp giao thức, header, chứng chỉ TLS, cách trả mã lỗi và các đặc điểm hành vi. Fingerprint **không nhất thiết phản ánh đúng** phần mềm đang chạy: CDN, reverse proxy, container image đã vá, cấu hình tùy biến hoặc lớp tương thích có thể làm kết quả khác thực tế.

So sánh:

| Thuật ngữ | Ý nghĩa | Ví dụ |
|---|---|---|
| **Banner** | Thông điệp/metadata do dịch vụ cung cấp | `SSH-2.0-OpenSSH_9.x` |
| **Banner grabbing** | Đọc thông điệp nhận dạng theo giao thức | Nhận HTTP response header của máy chủ do mình quản lý |
| **Fingerprinting** | Kết hợp dấu hiệu để nhận diện công nghệ | Suy luận có reverse proxy ở phía trước ứng dụng |
| **Information disclosure** | Thông tin vượt mức cần thiết bị lộ cho chủ thể không nên biết | Stack trace hoặc đường dẫn nội bộ xuất hiện trên trang lỗi công khai |
| **Vulnerability** | Điểm yếu có thể bị khai thác gây tác động bảo mật | Thành phần có lỗi bảo mật thực sự, chưa được vá và có đường khai thác phù hợp |

**Nhìn thấy tên hoặc phiên bản sản phẩm không tự chứng minh tồn tại lỗ hổng.** Muốn xác nhận rủi ro phải biết bản build, trạng thái bản vá, cấu hình, phạm vi phơi bày và đường khai thác. Một bản vá có thể được *backport* vào phiên bản có số hiệu cũ, nên kết luận chỉ từ banner dễ sai.

### 1.2. Thông tin công khai cần thiết và thông tin dư thừa

Không phải mọi thông tin nhận dạng đều là lỗi:

- Dòng định danh giao thức SSH mang thông tin phiên bản giao thức và nhận dạng phần mềm; một phần dữ liệu là thành tố bình thường của quá trình kết nối.
- Chứng chỉ TLS thường phải cung cấp tên miền và dữ liệu chứng chỉ để bên kết nối xác minh máy chủ; thông tin này về bản chất là công khai.
- Header HTTP như `Content-Type`, `Cache-Control` hay một số trường phục vụ proxy có chức năng giao thức.
- Trái lại, **stack trace, đường dẫn trên máy chủ, hostname nội bộ, thông tin phiên bản chi tiết không cần thiết, tên image/container hoặc cấu hình bí mật** thường không nên trả ra cho khách không tin cậy.

Cần phân biệt **bề mặt tiết lộ** (cái gì hiện ra) với **mức rủi ro** (thông tin đó giúp gây tác động gì, trong điều kiện nào). Mục tiêu là giảm dữ liệu không cần thiết và xử lý lỗ hổng gốc, không dựa duy nhất vào việc giấu tên công nghệ.

## 2. Banner thường lộ từ đâu?

### 2.1. HTTP/HTTPS và giao diện API

Ví dụ phản hồi giả định:

~~~http
HTTP/1.1 200 OK
Server: nginx/1.24.0
X-Powered-By: Express
Content-Type: application/json
Via: 1.1 edge-gateway

{"status":"ok"}
~~~

Ở đây:

- `Server` có thể chỉ ra phần mềm web server hoặc proxy đang trả phản hồi.
- `X-Powered-By`, `X-AspNet-Version`, `X-Generator` (khi tồn tại) có thể cho biết nền tảng, framework hoặc công cụ sinh nội dung.
- `Via`, các header cache, gateway hoặc CDN có thể gợi ý thành phần trung gian; ý nghĩa từng header phụ thuộc dịch vụ.
- Cookie name, tên endpoint, thông điệp lỗi và nội dung HTML/JavaScript cũng có thể giúp suy luận cấu trúc ứng dụng, kể cả khi `Server` đã bị rút gọn.

Một response header `Server: nginx` **không khẳng định** backend là nginx: có thể đó là reverse proxy phía trước Java, Node.js hoặc một dịch vụ khác. Dòng `X-Powered-By` cũng có thể được tự đặt, chỉnh sửa hoặc để lại bởi hệ thống cũ.

Các tình huống cần kiểm tra riêng:

| Điểm quan sát | Thông tin có thể xuất hiện | Vì sao dễ bị bỏ sót |
|---|---|---|
| Trang chính trả `200` | `Server`, `X-Powered-By`, tên framework | Đội phát triển chỉ thử chức năng |
| Redirect `301`/`302` | Header của gateway, tên host đích | Chỉ kiểm tra URL cuối |
| Lỗi `400`/`404`/`405` | Trang lỗi mặc định, chữ ký framework, phiên bản | Không kiểm tra đường dẫn sai hoặc method sai |
| Lỗi `500`/`502`/`503` | Stack trace, hostname upstream, dấu hiệu load balancer | Lỗi hiếm gặp hoặc phát sinh ở lớp khác |
| API nội bộ hoặc giao diện quản trị | Tên sản phẩm, build number, debug endpoint | Chỉ đánh giá domain công khai |
| Nội dung tĩnh và tài nguyên front-end | HTML generator, comment, sourcemap, tên package | Header đã được ẩn nhưng artifact vẫn tiết lộ |

Lỗi trong ứng dụng cần được ghi chi tiết **vào log nội bộ phù hợp**, còn phản hồi tới người dùng nên mang thông điệp vừa đủ và mã yêu cầu để hỗ trợ tra cứu.

### 2.2. SSH, SMTP, FTP và các dịch vụ khác

Một số giao thức tự cung cấp lời chào hoặc định danh:

~~~text
SSH-2.0-OpenSSH_9.x

220 mail.example.test ESMTP Service Ready

220 FTP service ready
~~~

Các dòng trên chỉ là minh họa, không phải kết quả đo của hệ thống thật.

| Giao thức | Dấu hiệu thường gặp | Điểm cần đánh giá |
|---|---|---|
| **SSH** | Chuỗi định danh `SSH-2.0-...`, danh sách khả năng bắt tay | Có lộ sản phẩm/build không? Xác thực khóa, MFA/bastion và bản vá đã phù hợp chưa? |
| **SMTP** | Dòng `220`, hostname, các khả năng `EHLO` | Có lộ hostname nội bộ hoặc tên sản phẩm không? Cấu hình SMTP, TLS và relay có an toàn không? |
| **FTP** | Dòng `220`, tên phần mềm/phiên bản, phản hồi trạng thái | Dịch vụ có thực sự cần mở không? Có thể thay bằng giao thức mã hóa phù hợp không? |
| **HTTP proxy/load balancer** | `Server`, `Via`, trang lỗi do proxy tạo | Kiểm tra cả phản hồi do proxy tự phát sinh và phản hồi từ backend |
| **Cơ sở dữ liệu/thiết bị mạng** | Thông điệp chào, metadata khi truy cập hoặc đăng nhập | Có phơi bày cổng quản trị ra vùng không cần thiết không? Đã hạn chế nguồn và quyền chưa? |

Một số banner do chuẩn giao thức hoặc khả năng tương thích yêu cầu. **Không nên loại bỏ bừa mọi ký tự nhận dạng** nếu làm hỏng bắt tay, kiểm tra chứng chỉ, giám sát hoặc tương thích với client. Việc tắt lời chào không thay thế xác thực, cập nhật bản vá hay chặn truy cập trái phép.

### 2.3. TLS, DNS, Wi-Fi và nền tảng đám mây

- **TLS:** chứng chỉ cung cấp Subject, SAN, issuer và thời hạn; chính sách TLS và bộ giao thức có thể phản ánh cấu hình. Tên miền xuất hiện trong chứng chỉ được cấp công khai và trong hệ sinh thái Certificate Transparency tùy trường hợp, nên không nên coi chúng là bí mật.
- **DNS:** bản ghi công khai, tên máy chủ/điểm dịch vụ và một số TXT/SRV record có thể cung cấp thông tin về hạ tầng hoặc nhà cung cấp. Cần kiểm soát nội dung công bố; bảo vệ DNS không chỉ bằng giấu tên.
- **Wi-Fi:** SSID và thông tin phát quảng bá có thể hé lộ tên tổ chức hoặc loại mạng. Ẩn SSID không thay thế xác thực Wi-Fi mạnh, phân đoạn khách/nhân viên và cấu hình access point.
- **Cloud/CDN:** header phản hồi, trang lỗi của load balancer, endpoint object storage, tên host hoặc thông báo quyền truy cập có thể cho biết dịch vụ trung gian. Đảm bảo cấu hình public access, IAM, đường quản trị và dữ liệu không lộ là ưu tiên cao hơn việc chỉ xóa header.

Trong cả bốn trường hợp, đánh giá phải xét **đơn vị sở hữu thông tin, đối tượng được xem và mục đích công bố**. Một tên miền công khai phục vụ HTTPS có ý nghĩa khác với một hostname của database chỉ nên nằm trong mạng riêng.

## 3. Banner leakage hỗ trợ reconnaissance như thế nào?

**Reconnaissance** là quá trình thu thập hiểu biết về bề mặt hệ thống trước khi quyết định bước phân tích tiếp theo. Với vai trò phòng thủ, cần hình dung rằng dữ liệu mà hệ thống trả ra công khai có thể được tổng hợp thành hồ sơ công nghệ.

~~~mermaid
flowchart TD
    A["Bề mặt dịch vụ mà người ngoài nhìn thấy"] --> B["Metadata: header, lời chào, lỗi, chứng chỉ"]
    B --> C["Giả thuyết về công nghệ, phiên bản và topology"]
    C --> D{"Đã kiểm chứng bằng cấu hình và kiểm kê nội bộ?"}
    D -->|"Chưa"| E["Ghi nhận là giả thuyết, tránh kết luận sai"]
    D -->|"Có"| F["Đối chiếu bản vá, quyền truy cập và biện pháp bảo vệ"]
    E --> F
    F --> G["Đánh giá rủi ro, khắc phục và giám sát"]
~~~

Người ngoài có thể kết hợp nhiều dấu hiệu để suy đoán một thành phần. Ví dụ `Server` gợi ý reverse proxy, tên cookie gợi ý framework, nội dung lỗi cho biết dạng ứng dụng và một endpoint công khai cho biết loại công nghệ hỗ trợ. Nhưng **đó vẫn chỉ là giả thuyết** cho tới khi có bằng chứng phù hợp.

### 3.1. Hai cách thu thập dấu hiệu

| Cách thức | Ví dụ trong hoạt động được phép | Giới hạn cần hiểu |
|---|---|---|
| **Quan sát thụ động** | Đọc response đã có trong log, trình duyệt, bản ghi kiểm kê, chứng chỉ và dữ liệu công khai | Có thể cũ, không đầy đủ hoặc mô tả proxy thay vì backend |
| **Kiểm tra chủ động có kiểm soát** | Gửi một số yêu cầu HTTP/HTTPS thông thường tới dịch vụ mình quản lý; kiểm tra phản hồi lỗi theo bộ ca thử đã phê duyệt | Tạo lưu lượng thật, cần có phạm vi, giới hạn tốc độ và tránh ảnh hưởng người dùng |

Chỉ kiểm tra tài sản có quyền quản lý hoặc được ủy quyền. Đối với hệ thống sản xuất, dùng những yêu cầu thông thường hoặc môi trường staging trước; không cố kích hoạt lỗi gây gián đoạn hay lấy thông tin không thuộc phạm vi.

### 3.2. Ví dụ luồng đánh giá trong hệ thống doanh nghiệp

Giả sử hệ thống có:

~~~mermaid
sequenceDiagram
    participant C as Client được phép
    participant G as CDN / Reverse proxy
    participant A as API
    participant L as Log nội bộ

    C->>G: GET /health
    G->>A: Chuyển tiếp yêu cầu
    A-->>G: HTTP 200 + metadata backend
    G-->>C: HTTP 200 + header công khai
    C->>G: GET /duong-dan-khong-ton-tai
    G->>A: Chuyển tiếp yêu cầu
    A-->>G: HTTP 404 + lỗi ứng dụng
    G-->>C: HTTP 404 + thông điệp cần thiết
    A->>L: Ghi chi tiết phục vụ điều tra
~~~

Cần xem xét **ai tạo ra từng header và từng trang lỗi**. Nếu CDN phát sinh `502`, sửa header trong ứng dụng sẽ không sửa được banner ở trang lỗi do CDN tạo. Nếu backend trả stack trace, chỉ cấu hình proxy ẩn `Server` cũng chưa khắc phục được lộ dữ liệu trong response body.

## 4. Thực hành kiểm tra an toàn trên môi trường của mình

### 4.1. Xác định phạm vi và điều kiện thử

Ví dụ hệ thống thử nghiệm HTTP chạy trên `127.0.0.1:8080`. Chỉ dùng địa chỉ đó khi bạn **đã chủ động chạy dịch vụ nội bộ** trên cổng tương ứng; nếu không có dịch vụ, lỗi kết nối là kết quả bình thường.

Trên Windows PowerShell có thể dùng `curl.exe` để tránh nhầm với alias `curl` của một số phiên bản PowerShell:

~~~powershell
# Chỉ lấy header của tài nguyên do mình quản lý
curl.exe -I http://127.0.0.1:8080/

# Xem cả header và nội dung một trang không tồn tại
curl.exe -i http://127.0.0.1:8080/khong-ton-tai
~~~

Lệnh `-I` dùng method `HEAD`. Một số dịch vụ không xử lý HEAD giống GET; vì vậy kết quả HEAD **không đại diện đầy đủ** cho mọi đường xử lý và mọi mã lỗi. Dùng `-i` để quan sát header của phản hồi thường, đặc biệt khi cần kiểm tra body lỗi.

Với một dịch vụ HTTPS **được phép kiểm tra**, giữ nguyên xác minh chứng chỉ của client khi dùng `curl.exe`; đừng bỏ qua lỗi TLS bằng tùy chọn tắt xác thực chỉ để lấy banner.

Ví dụ kết quả mô phỏng:

~~~http
HTTP/1.1 404 Not Found
Server: nginx/1.24.0
X-Powered-By: Express
Content-Type: text/html; charset=utf-8

<h1>Page not found</h1>
~~~

Quan sát: hai trường `Server` và `X-Powered-By` làm lộ dấu hiệu công nghệ; phần body minh họa chưa tiết lộ stack trace. Không thể kết luận hệ thống có lỗi bảo mật từ số phiên bản hiển thị.

### 4.2. Dùng Java 11+ để đọc header từ dịch vụ nội bộ

Với ứng dụng Java, có thể xây một bước kiểm tra nhỏ chỉ đọc một số trường đã biết, tránh ghi toàn bộ header vì chúng có thể chứa cookie hoặc dữ liệu nhạy cảm:

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

public class LocalBannerCheck {
    public static void main(String[] args) throws Exception {
        URI target = URI.create("http://127.0.0.1:8080/");
        HttpClient client = HttpClient.newHttpClient();
        HttpRequest request = HttpRequest.newBuilder(target)
                .method("HEAD", HttpRequest.BodyPublishers.noBody())
                .build();

        HttpResponse<Void> response = client.send(
                request, HttpResponse.BodyHandlers.discarding());
        System.out.println("HTTP status: " + response.statusCode());

        for (String name : new String[] {"server", "x-powered-by", "via"}) {
            response.headers().firstValue(name)
                    .ifPresent(value -> System.out.println(name + ": " + value));
        }
    }
}
~~~

Đây là công cụ minh họa cho **kiểm tra một endpoint nội bộ**, không phải bộ quét đánh giá bảo mật toàn diện. Nó không truy vấn các đường lỗi, không kiểm tra SSH/SMTP và cũng không chứng minh việc ẩn header hoàn toàn ở các lớp khác.

### 4.3. Ghi nhận kết quả thành bằng chứng

Một bảng kiểm kê gọn:

| Trường | Ví dụ ghi nhận | Mục đích |
|---|---|---|
| Asset | Web gateway thử nghiệm | Xác định hệ thống sở hữu |
| Endpoint/trạng thái | `GET /` — `200`; `GET /khong-ton-tai` — `404` | Phân biệt nhiều nhánh phản hồi |
| Nguồn phản hồi | Gateway hoặc ứng dụng (đã xác nhận) | Tránh sửa sai thành phần |
| Metadata hiện ra | `Server: nginx/1.24.0` | Bằng chứng cụ thể |
| Đối tượng có thể xem | Người dùng Internet / nhân viên / admin | Xác định mức độ phơi bày |
| Tác động dự kiến | Tiết lộ stack hoặc phiên bản; chưa có khai thác được chứng minh | Phân biệt thông tin và lỗ hổng |
| Kiểm soát hiện có | TLS, WAF, cập nhật bản vá, phân đoạn, xác thực | Đánh giá rủi ro còn lại |
| Owner, trạng thái xử lý | Đội Platform, chờ xác minh | Có người chịu trách nhiệm |

Không lưu trữ/chia sẻ nguyên bản header chứa `Authorization`, `Set-Cookie`, session token hoặc khóa bí mật trong báo cáo. Nếu cần minh chứng, dùng dữ liệu đã che và mô tả cụ thể vị trí xuất hiện.

## 5. Đánh giá mức rủi ro đúng bản chất

Một banner đầy đủ thường là **finding về thông tin**. Mức ưu tiên phụ thuộc vào khả năng tác động thực tế:

| Tình huống | Diễn giải | Hành động hợp lý |
|---|---|---|
| `Server: nginx` trên website công khai | Dấu hiệu chung về thành phần, thường ít nhạy cảm | Ghi nhận; duy trì bản vá và cấu hình bảo mật |
| Banner công khai kèm số phiên bản cụ thể | Có thể giúp xác định phạm vi công nghệ | Rút gọn metadata không cần thiết; đối chiếu bản vá thực tế |
| Header cho biết tên ứng dụng nội bộ hoặc hostname | Có thể tiết lộ topology hoặc môi trường | Kiểm tra nguồn tạo header; loại bỏ thông tin không cần thiết |
| Lỗi công khai chứa stack trace, đường dẫn, nội dung truy vấn | Tiết lộ thông tin triển khai nhiều hơn banner thông thường | Ưu tiên sửa xử lý lỗi; tránh log bí mật; rà soát tác động |
| Console quản trị với banner sản phẩm bị truy cập từ Internet | Kết hợp khả năng tiếp cận vùng đặc quyền | Giới hạn đường quản trị, xác thực mạnh, rà soát bản vá và logging |
| Dịch vụ thực sự tồn tại lỗi có thể khai thác | Rủi ro nằm ở lỗi và đường khai thác, không chỉ ở banner | Vá/giảm thiểu lỗ hổng và giảm bề mặt tấn công |

Khi đánh giá, cần hỏi:

1. **Thông tin có công khai không?** Có thể nhận từ Internet, mạng khách hay chỉ tài khoản quản trị?
2. **Dữ liệu mới hay đã lỗi thời?** Header tại gateway có mô tả đúng phiên bản backend không?
3. **Thông tin có nhạy cảm không?** Tên sản phẩm chung khác với username, tên máy nội bộ, cấu hình bảo mật hoặc bí mật xác thực.
4. **Có liên quan tới lỗ hổng đã xác minh?** Kiểm tra bản vá và cấu hình theo kiểm kê đáng tin cậy, không chỉ tra cứu một chuỗi phiên bản.
5. **Có kiểm soát bù trừ nào?** Segmentation, firewall, VPN/ZTNA, IAM, MFA, rate limit, log/IDS/IPS và chính sách egress.
6. **Tác động nếu bị kết hợp với yếu tố khác?** Ví dụ phiên bản lộ ra trong khi giao diện admin công khai và thiếu kiểm soát truy cập.

**Mất khả năng nhìn thấy phiên bản từ bên ngoài không có nghĩa là hết lỗ hổng.** Một dịch vụ vẫn cần patching, hardening, xác thực và phân quyền dù không trả banner.

## 6. Giảm banner leakage theo từng lớp

### 6.1. HTTP server và reverse proxy

Với Nginx, cấu hình thường dùng để giảm việc hiển thị phiên bản trong header và trang lỗi mặc định:

~~~nginx
http {
    server_tokens off;
    # Những cấu hình HTTP/server/location khác...
}
~~~

**Giới hạn:** `server_tokens off` thường **rút phiên bản**, nhưng không đảm bảo xóa hẳn tên `nginx` khỏi header; các lớp reverse proxy/CDN khác có thể tạo banner riêng. Cần kiểm tra toàn bộ đường đi trước khi kết luận đã xử lý xong.

Với Apache HTTP Server:

~~~apache
ServerTokens Prod
ServerSignature Off
~~~

`ServerTokens Prod` thường rút gọn trường `Server` về thông tin sản phẩm, còn `ServerSignature Off` tránh xuất hiện chữ ký trong những trang lỗi/footer do Apache tạo. Chúng không xử lý phiên bản framework được ứng dụng tự công bố.

Với ứng dụng Node.js sử dụng Express, có thể tắt header mặc định:

~~~javascript
app.disable('x-powered-by');
~~~

Với Spring Boot, cần kiểm tra cách hiển thị lỗi và không đưa stack trace hoặc dữ liệu nội bộ ra phản hồi công khai; ví dụ cấu hình ứng dụng có thể dùng:

~~~properties
server.error.include-message=never
server.error.include-stacktrace=never
server.error.include-binding-errors=never
~~~

Các khóa trên chỉ chi phối phần lỗi theo cơ chế của Spring Boot đang dùng; chúng **không bảo đảm** loại bỏ mọi trang lỗi do gateway, thư viện, servlet container hoặc thành phần khác sinh ra. Kiểm tra phiên bản framework và đường xử lý lỗi thực tế trước khi áp dụng.

### 6.2. Xử lý lỗi nhất quán

Với API, phản hồi lỗi nên có **mã trạng thái phù hợp**, thông báo đơn giản và mã tương quan:

~~~http
HTTP/1.1 500 Internal Server Error
Content-Type: application/json
Cache-Control: no-store

{"error":"internal_error","requestId":"req-demo-123"}
~~~

Log nội bộ có thể giữ stack trace phục vụ điều tra nhưng phải giới hạn quyền và lọc token, mật khẩu, khóa, PII không cần thiết. Mã `requestId` giúp liên hệ phản hồi công khai với sự kiện nội bộ mà không công bố chi tiết triển khai.

Kiểm tra cả những tình huống ứng dụng không trực tiếp tạo lỗi: gateway timeout, upstream unavailable, lỗi xác thực trước khi vào backend, lỗi proxy, lỗi DNS nội bộ và lỗi trang tĩnh.

### 6.3. Dịch vụ mạng, thiết bị và kênh quản trị

Với SSH/SMTP/FTP hoặc giao diện quản trị của firewall, VPN, thiết bị không dây, ưu tiên:

- **Chỉ công bố dịch vụ thực sự cần thiết**; chặn đường truy cập ngoài phạm vi bằng firewall/ACL, phân đoạn hoặc kênh quản trị được bảo vệ.
- **Cập nhật phần mềm và firmware** theo inventory, kiểm tra thay đổi cấu hình, vô hiệu hóa giao thức/khả năng cũ không dùng.
- **Xác thực mạnh và quyền tối thiểu**; dùng khóa/bastion/MFA ở những vị trí phù hợp, kiểm soát cấu hình quản trị và lịch sử thao tác.
- **Cấu hình lời chào hợp lý** theo sản phẩm và chuẩn giao thức; tránh hostname nội bộ, số bản build quá chi tiết hoặc thông tin hỗ trợ không cần công khai.
- **Giám sát và giới hạn lưu lượng** tại ingress/egress; kết hợp IDS/IPS với log xác thực, cấu hình và telemetry.

Không sửa banner theo cách **mạo danh sản phẩm/phiên bản** để đánh lạc hướng công cụ kiểm kê nội bộ. Nếu chủ đích giảm tiết lộ, hãy có cơ chế quản lý inventory đáng tin cậy ở phía vận hành.

### 6.4. Pipeline triển khai, frontend và cloud

Kiểm tra cả nguồn ngoài header:

- Không xuất bản file debug, bản sao cấu hình, stack trace, tên thư mục build, sourcemap chứa nội dung nhạy cảm hoặc manifest nội bộ mà không có yêu cầu.
- Không đưa secret vào bundle JavaScript, HTML, lỗi trả về hoặc log. Bí mật đã bị lộ cần được **thu hồi/đổi** và đánh giá tác động; chỉ xóa file hoặc header là chưa đủ.
- Review cấu hình CDN, load balancer, API gateway và object storage; mỗi lớp có thể sinh header và trang lỗi riêng.
- Quản lý DNS, TLS certificate, cloud IAM, quyền public, vùng private endpoint và hạ tầng quản trị theo nhu cầu truy cập thực.
- Duy trì danh mục phần mềm, bản vá và cấu hình **ở phía nội bộ** để khả năng quan sát vận hành không phụ thuộc banner công khai.

## 7. Kiến trúc phòng vệ và trust boundary liên quan

~~~mermaid
flowchart LR
    subgraph NET["Mạng ngoài / chưa được xác thực"]
        C["Client"]
    end
    subgraph EDGE["Ranh giới 1: Edge công khai"]
        W["WAF / CDN / Gateway"]
    end
    subgraph APP["Ranh giới 2: Dịch vụ ứng dụng"]
        A["Web / API"]
    end
    subgraph OPS["Ranh giới 3: Vùng quản trị"]
        M["Inventory / Log / Quản lý bản vá"]
    end
    C -->|"HTTPS / yêu cầu từ client"| W
    W -->|"HTTPS / phản hồi và metadata công khai"| C
    W -->|"Luồng cho phép / xác thực phía backend"| A
    A -->|"Log có kiểm soát / dữ liệu inventory"| M
~~~

Một dịch vụ có thể lộ banner từ **ba vị trí**: gateway tự sinh, backend trả qua gateway và trang lỗi/asset của đường triển khai. Đi qua WAF hoặc phân đoạn mạng giúp hạn chế đường kết nối, nhưng không tự lọc thông điệp lỗi từ ứng dụng.

Liên hệ với threat modeling:

| Tài sản hoặc luồng | Ranh giới tin cậy | Mối lo | Kiểm soát |
|---|---|---|---|
| Client → gateway | Internet → edge | Header công khai hé lộ sản phẩm hoặc endpoint quản trị | Cấu hình response, giới hạn đường truy cập, WAF/rate limit |
| Gateway → API | Edge → app | Header/stack trace backend được proxy ra công khai | Xử lý lỗi, header sanitation, xác thực upstream, test 4xx/5xx |
| API → log | App → vùng quan sát | Token, đường dẫn nội bộ hay thông tin người dùng xuất hiện trong log | Lọc log, IAM, retention, mã tương quan |
| Nhân viên → control plane | Người dùng → quyền quản trị | Giao diện quản trị phơi bày tên sản phẩm và đường điều khiển | MFA, VPN/ZTNA khi phù hợp, quyền tối thiểu, audit |
| Dịch vụ → DNS/IdP/cloud | App → bên thứ ba | Metadata hạ tầng lan sang các miền khác | Quản lý endpoint, egress, hợp đồng tin cậy, kiểm soát dữ liệu |

Việc thiết kế phòng thủ đúng yêu cầu **tại mỗi ranh giới chỉ gửi dữ liệu mà phía nhận thực sự cần**, đồng thời giữ đủ dữ liệu chẩn đoán trong hệ thống quan sát an toàn.

## 8. Kiểm chứng sau thay đổi

Sau khi thay đổi cấu hình, cần xác minh bằng **kiểm thử hành vi** từ đúng vị trí truy cập:

| Ca thử | Trước thay đổi (ví dụ) | Tiêu chí sau thay đổi |
|---|---|---|
| `GET /` trả `200` | `Server: nginx/1.24.0` | Không phát phiên bản cụ thể nếu không cần |
| `GET /khong-ton-tai` trả `404` | Trang lỗi ghi tên framework | Không có đường dẫn nội bộ hay phiên bản chi tiết |
| Backend lỗi và gateway trả `502` | Trang lỗi lộ hostname upstream | Chỉ có thông tin cần thiết cho client, log nội bộ giữ mã tương quan |
| Truy cập giao diện admin từ Internet | Mở banner đăng nhập hoặc thiết bị | Không thể truy cập ngoài đường quản trị được phê duyệt |
| Nhiều edge/region/instance | Một điểm đã ẩn header, điểm khác chưa | Chính sách và cấu hình được áp nhất quán |
| Công cụ inventory nội bộ | Phụ thuộc dữ liệu header công khai | Vẫn xác định chính xác bản build và patch level qua nguồn quản trị tin cậy |

Khi thực hiện kiểm tra:

1. Ghi lại endpoint, vùng mạng, thời gian, response status, header **đã loại dữ liệu nhạy cảm** và thành phần đã sinh phản hồi.
2. So sánh các ca GET/HEAD, redirect, đường dẫn sai và lỗi do gateway/ứng dụng phát sinh trong phạm vi cho phép.
3. Kiểm tra phản hồi từ nhiều instance/region nếu dịch vụ triển khai phân tán; tránh chỉ kiểm tra một node.
4. Xác nhận việc sửa banner không phá chức năng, không thay đổi cơ chế xác thực, cache, CORS hay bắt tay giao thức cần thiết.
5. Chạy kiểm kê bản vá và cấu hình an toàn độc lập. Đóng finding chỉ khi tiêu chí kỹ thuật và mức phơi bày đã được kiểm chứng.

Không chạy thử gây tải lớn hoặc cố tạo lỗi sản xuất. Với nhánh lỗi khó tái hiện, nên dùng staging, kiểm thử tích hợp hoặc quan sát log đã có.

## 9. Tình huống thực tế: xử lý không triệt để ở nhiều lớp

Một tổ chức vận hành web qua CDN, reverse proxy và ứng dụng Java. Đội vận hành phát hiện header ngoài Internet cho biết tên và phiên bản reverse proxy. Họ rút gọn `Server` ở proxy và xác nhận trang chủ không còn số phiên bản.

Tuy nhiên, khi upstream tạm không khả dụng, CDN tạo trang `502` riêng có chữ ký sản phẩm. Một endpoint của ứng dụng cũng trả thông điệp lỗi chứa tên package Java và đường dẫn trong container. Như vậy **hai nguồn tiết lộ còn lại nằm ở những lớp khác**, nên thay đổi ở proxy không giải quyết toàn bộ rủi ro.

Hướng xử lý:

1. **Xác định nguồn từng dấu hiệu:** CDN, reverse proxy hay ứng dụng; đối chiếu log/request ID.
2. **Loại bỏ metadata không cần thiết:** cấu hình banner và trang lỗi ở từng lớp hỗ trợ tùy chỉnh.
3. **Xử lý lỗi ứng dụng:** trả thông điệp ngắn cho client, ghi chi tiết vào log được bảo vệ, loại bỏ secret trong log.
4. **Kiểm tra bảo vệ gốc:** cập nhật các thành phần liên quan, giới hạn đường quản trị, kiểm tra phân quyền giữa các lớp và các luồng nội bộ.
5. **Xác minh lại:** đối chiếu các nhánh 200/301/404/500/502, nhiều instance và góc nhìn người dùng ngoài mạng.

**Kết luận của ca kiểm tra** nên ghi: “Đã hạn chế thông tin phiên bản được công bố tại các thành phần A/B/C, xác minh trên các nhánh phản hồi X/Y/Z; bản vá và bảo vệ truy cập được theo dõi độc lập.” Điều này chính xác hơn tuyên bố “đã hết lỗ hổng” chỉ vì không còn thấy banner.

## 10. Bài tập tự đánh giá

**Bối cảnh:** Hệ thống bán hàng có gateway công khai, ứng dụng Spring Boot nằm trong subnet riêng, database và công cụ giám sát. Khi kiểm tra trên môi trường thử nghiệm, người quản trị thấy:

~~~http
HTTP/1.1 404 Not Found
Server: gateway/2.3
Content-Type: application/json

{"error":"No handler found","trace":"at com.demo.order.OrderController..."}
~~~

Với phản hồi này, hãy trả lời:

1. Có những dấu hiệu nhận dạng nào? Dấu hiệu nào thuộc header, dấu hiệu nào nằm trong body?
2. Có thể kết luận backend đang dùng gateway phiên bản 2.3 hay Spring Boot có một CVE cụ thể không? Vì sao?
3. Ở những lớp nào cần chỉnh sửa để tránh lộ thông tin qua cả `200`, `404` và `502`?
4. Tại sao che header không thay thế cập nhật bản vá, giới hạn quản trị và phân quyền API?
5. Có thể làm gì để giữ đủ chi tiết phục vụ xử lý sự cố mà không công khai stack trace?

**Gợi ý đối chiếu:** `Server` chỉ cho biết dấu hiệu từ đường phản hồi đang quan sát, chưa chứng minh backend nào trả header. Body chứa đường dẫn tên package/stack trace và nên được thay bằng thông báo lỗi trung tính cùng request ID. Phải kiểm tra gateway, ứng dụng và hệ thống tạo lỗi upstream; thực hiện patching và kiểm soát truy cập riêng biệt.

## 11. Checklist kiểm tra banner leakage

- [ ] Có danh mục dịch vụ/cổng/endpoint và người phụ trách theo vùng mạng hoặc cloud account.
- [ ] Xác định đối tượng nào có thể xem banner: Internet, Wi-Fi khách, mạng nhân viên, ứng dụng khác hoặc vùng quản trị.
- [ ] Kiểm tra các dấu hiệu HTTP `Server`, `X-Powered-By`, thông tin proxy và các phản hồi lỗi 4xx/5xx.
- [ ] Xem xét lời chào và khả năng giao thức của SSH/SMTP/FTP khi dịch vụ hiện diện và thuộc phạm vi.
- [ ] Phân biệt metadata cần cho giao thức (TLS, HTTP, SSH) với thông tin triển khai không cần công khai.
- [ ] Đối chiếu dấu hiệu nhận dạng với inventory và trạng thái bản vá; không suy ra lỗ hổng chỉ từ chuỗi phiên bản.
- [ ] Kiểm tra cả CDN/gateway/load balancer/backend, nhiều môi trường và các nhánh response khác nhau.
- [ ] Loại bỏ stack trace, đường dẫn nội bộ và dữ liệu nhạy cảm khỏi phản hồi công khai; giữ log nội bộ đúng quyền.
- [ ] Bảo vệ interface quản trị bằng phân đoạn, firewall, xác thực mạnh và quyền tối thiểu.
- [ ] Có bằng chứng trước/sau thay đổi và xác nhận hệ thống tiếp tục hoạt động đúng.

**Ghi nhớ:** Banner leakage làm tăng lượng thông tin mà một bên chưa được tin cậy có thể quan sát về dịch vụ. Cách phòng vệ hiệu quả là **giảm công bố metadata không cần thiết, quản lý tài sản và bản vá chính xác, hạn chế bề mặt truy cập và kiểm soát dữ liệu ở từng ranh giới mạng**.
