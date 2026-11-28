# Subject Alternative Name cho hostname: Xác thực đúng danh tính dịch vụ qua chứng thư số

## 1. SAN giải quyết bài toán nào?

Khi ứng dụng kết nối tới `api.lab.example.test` bằng HTTPS, nó không chỉ cần **mã hóa dữ liệu** mà còn phải biết máy chủ bên kia **có đúng là dịch vụ mang tên đó hay không**. Nếu không kiểm tra danh tính, một điểm truy cập Wi-Fi giả, DNS bị can thiệp hoặc proxy ngoài ý muốn có thể dẫn ứng dụng tới một endpoint khác và thiết lập một kênh mã hóa với **chính endpoint giả**.

**Subject Alternative Name (SAN)** là một **extension của chứng thư số X.509** dùng để khai báo những **danh tính mà chứng thư được cấp cho**, ví dụ tên DNS (`dNSName`) hoặc địa chỉ IP (`iPAddress`). Trong mô hình TLS có chứng thư máy chủ, ứng dụng dùng danh tính dịch vụ dự kiến kết nối để so khớp với thông tin thích hợp trong SAN của chứng thư, đồng thời kiểm tra chuỗi tin cậy, hiệu lực và các điều kiện bảo mật khác.

Ví dụ, một chứng thư có các SAN:

~~~text
X509v3 Subject Alternative Name:
    DNS:api.lab.example.test
    DNS:admin.lab.example.test
~~~

Ứng dụng muốn kết nối `https://api.lab.example.test/` có thể tìm được DNS-ID phù hợp. Nhưng khi truy cập `https://files.lab.example.test/`, cùng chứng thư đó **không khớp hostname**, dù hai tên có thể trỏ tới một IP, và dù chứng thư còn hạn hoặc do CA được tin cậy cấp.

**Mục tiêu học tập:**

1. Hiểu SAN là gì, vì sao hostname được kiểm tra trong SAN thay vì chỉ dựa vào Common Name (CN).
2. Phân biệt `dNSName`, `iPAddress` và những loại SAN khác, cùng phạm vi sử dụng của từng loại.
3. Giải thích quy tắc khớp DNS hostname, wildcard, alias/CNAME và hostname quốc tế (IDN).
4. Phân biệt **SAN validation**, **certificate chain validation**, **TLS SNI**, **DNS lookup** và **HTTP Host**.
5. Thiết kế SAN inventory khi có CDN, reverse proxy, load balancer, API, nhiều virtual hosts và mTLS.
6. Kiểm tra chứng thư, CSR và hostname bằng OpenSSL/cURL trong phòng lab có phép; xây ma trận test dương/âm.
7. Lập quy trình cấp, gia hạn, thay đổi SAN và phản ứng khi phát hành sai chứng thư.

Chủ đề thuộc chương **PKI và chứng thư cho mạng** trong module **SECURITY_NETWORK_SECURITY**. Nó kết nối trực tiếp với TLS, DNS security, firewall, VPN, Wi-Fi, IDS/IPS và kiến trúc cloud: route hoặc DNS có thể đưa packet tới địa chỉ đích, còn việc **xác minh danh tính hostname được trình bày trong chứng thư** góp phần quyết định ứng dụng có nên tin endpoint đó hay không.

> **An toàn thực hành:** ví dụ dùng các tên trong `example.test` và IP dành cho tài liệu (`192.0.2.0/24`, `198.51.100.0/24`, `203.0.113.0/24`, `2001:db8::/32`). Chúng không mặc nhiên tồn tại hoặc có CA tin cậy. Chỉ kiểm tra endpoint do bạn quản lý/được phép truy cập; không xuất private key hay tắt xác minh chứng thư để làm bài thực hành.

## 2. SAN nằm ở đâu trong chứng thư X.509?

Chứng thư X.509 là cấu trúc dữ liệu chứa **public key, danh tính/chủ thể, thời hạn, issuer, chữ ký CA và các extension**. SAN thường là một extension quan trọng đối với việc kiểm tra danh tính của máy chủ TLS. Cần tách vai trò của các trường:

| Thành phần | Vai trò | Điều không nên suy ra |
|---|---|---|
| **Subject** | Thông tin về chủ thể được cấp chứng thư | Không tự xác minh hostname chỉ vì Subject có tên dễ đọc |
| **Common Name (CN)** | Một thuộc tính trong Subject, lịch sử từng được dùng cho tên host | Không thay thế SAN DNS-ID theo hướng dẫn xác minh tên dịch vụ hiện đại |
| **SAN: dNSName** | Khai báo tên DNS mà chứng thư có thể đại diện | Không tự xác nhận quyền quản trị từng tên nếu CA phát hành sai |
| **SAN: iPAddress** | Khai báo địa chỉ IP để khớp khi kết nối bằng IP literal | Không tương đương `DNS:192.0.2.20` dạng chuỗi |
| **Public key / signature algorithm** | Gắn public key với chứng thư và bảo vệ thông tin được CA ký | Không chứng minh server hiện đang giữ private key nếu chưa xác thực trong giao thức |
| **Issuer / certificate chain** | Dẫn đến trust anchor/CA theo policy client | Không đủ nếu SAN không khớp hostname |
| **Validity** | Khoảng thời gian chứng thư được cấp hiệu lực | Chứng thư chưa hết hạn không chứng minh hostname đúng |
| **Key Usage / Extended Key Usage** | Ràng buộc mục đích sử dụng khóa/chứng thư, như `serverAuth` | Không tạo quyền truy cập API cho người dùng |
| **Basic Constraints / CA flag** | Phân biệt CA và end-entity theo mô hình PKI | Chứng thư máy chủ không nên được dùng làm CA |

### 2.1. Cấu trúc SAN mở rộng

Trong RFC 5280, extension có Object Identifier **2.5.29.17**, thường hiển thị là `X509v3 Subject Alternative Name`. Nó chứa nhiều phần tử `GeneralName`, mỗi phần tử có một **loại danh tính** và giá trị tương ứng.

~~~text
X.509 Certificate
├── Subject: CN=api.lab.example.test
├── Issuer: CN=Lab Issuing CA
├── Validity: notBefore / notAfter
├── Subject Public Key Info: ...
├── Extensions
│   ├── Key Usage: Digital Signature
│   ├── Extended Key Usage: TLS Web Server Authentication
│   ├── Basic Constraints: CA:FALSE
│   └── Subject Alternative Name (OID 2.5.29.17)
│       ├── dNSName: api.lab.example.test
│       ├── dNSName: admin.lab.example.test
│       └── iPAddress: 192.0.2.20
└── Signature by issuing CA
~~~

**Đây là chứng thư minh họa**, không phải nội dung được xuất từ một máy chủ thật. Việc có `Subject CN` giống một tên SAN có thể giúp quản trị dễ đọc nhưng **không phải lý do để client bỏ qua kiểm tra SAN**.

### 2.2. SAN có thể chứa những kiểu danh tính nào?

| GeneralName | Dùng trong bối cảnh nào? | Lưu ý |
|---|---|---|
| **dNSName** | Xác thực máy chủ bằng tên DNS trong giao thức dịch vụ phù hợp | Dùng DNS-ID để so tên được yêu cầu |
| **iPAddress** | Truy cập dịch vụ bằng địa chỉ IP literal | Phải kiểm tra loại IP-ID, không so chuỗi IP với dNSName |
| **uniformResourceIdentifier** | Danh tính dựa trên URI trong profile/chính sách ứng dụng | Không tự thay thế DNS-ID của HTTPS |
| **rfc822Name** | Địa chỉ email trong những profile chứng thư phù hợp | Không phải trường hostname web |
| **otherName** | Các danh tính theo OID/profile chuyên biệt, ví dụ một số dạng principal | Phải có logic validation tương ứng |
| **directoryName** | Tên cấu trúc dạng X.500 trong một số PKI | Không đồng nghĩa hostname DNS |

Điều cần nhớ là **“có SAN” chưa đủ**: ứng dụng phải so khớp **đúng loại danh tính** với danh tính kỳ vọng trong ngữ cảnh kết nối. Trên một dịch vụ web truy cập bằng tên DNS, SAN chỉ chứa email hoặc URI không tự làm thỏa điều kiện DNS hostname.

## 3. Quy trình xác thực hostname: nhiều kiểm tra, một quyết định

### 3.1. Bốn điều kiện độc lập

Trong kết nối HTTPS dùng chứng thư server, client thường phải kiểm tra:

1. **Đúng danh tính dịch vụ:** tên mà ứng dụng định kết nối phải khớp một danh tính phù hợp trong SAN.
2. **Đúng chuỗi tin cậy:** chứng thư được ký bởi CA/trust anchor được client tin theo chính sách, intermediate chain hợp lệ.
3. **Đúng điều kiện chứng thư:** còn hiệu lực, key usage/EKU phù hợp, thuật toán và chính sách kiểm tra trạng thái/thu hồi theo yêu cầu.
4. **Đúng bằng chứng khóa trong handshake:** server chứng minh có khả năng sử dụng private key tương ứng và phiên TLS kết thúc xác minh theo giao thức.

~~~mermaid
flowchart TD
    U["Ứng dụng yêu cầu api.lab.example.test"] --> C["Nhận chứng thư X.509 qua TLS"]
    C --> T{"Chain / CA / validity / usage hợp lệ?"}
    T -- "Không" --> R["TỪ CHỐI kết nối"]
    T -- "Có" --> N{"SAN phù hợp tên dịch vụ cần truy cập?"}
    N -- "Không" --> R
    N -- "Có" --> K{"TLS handshake chứng minh khóa và integrity?"}
    K -- "Không" --> R
    K -- "Có" --> A["Tiếp tục TLS; authorization ứng dụng kiểm tra riêng"]
~~~

Sơ đồ mang tính khái niệm; các bước kiểm tra có thể xảy ra ở thứ tự khác nhau trong thư viện TLS. **Tất cả điều kiện áp dụng phải đạt** để phiên được tin cậy. Một certificate có SAN trùng hostname vẫn có thể bị từ chối do CA không đáng tin hoặc hết hạn.

### 3.2. Reference identity phải đến từ đâu?

Giả sử code gọi URL `https://api.lab.example.test/v1/orders`. **Reference identity** cho việc so khớp DNS hostname thường lấy từ **tên dịch vụ mà ứng dụng định kết nối**, ở đây là `api.lab.example.test`, không phải:

- Tên được CA điền sẵn trong chứng thư nhận được.
- Một tên tự chọn từ `Subject CN`.
- Tên mà DNS CNAME chuyển hướng tới trong lúc phân giải.
- Giá trị HTTP Host do proxy không đáng tin thay đổi.
- Một hostname attacker cung cấp qua redirect mà ứng dụng không có chính sách chấp nhận.

Quy tắc identity verification chi tiết thuộc profile giao thức và thư viện client; với DNS-ID của dịch vụ TLS, **RFC 9525** là tài liệu nền tảng hiện đại. Có những ứng dụng cần service identity theo **URI-ID hoặc SRV-ID** khi profile của chúng định nghĩa rõ; không chuyển loại SAN tùy ý.

### 3.3. Common Name không còn là nguồn chính để khớp tên

Trong các hệ thống cũ, `Subject CN=www.example.com` có thể từng được dùng để kiểm tra hostname. Tuy nhiên, chuẩn xác minh danh tính dịch vụ hiện đại **RFC 9525 yêu cầu không dùng CN-ID để thay thế các định danh SAN phù hợp**. Một số phần mềm legacy còn fallback về CN, nhưng không nên dựa vào đó để cấp mới chứng thư.

Ví dụ:

~~~text
Requested hostname: payments.lab.example.test

Certificate:
  Subject: CN=payments.lab.example.test
  SAN: DNS=api.lab.example.test

Expected with modern DNS-ID verification:
  FAIL: SAN không có payments.lab.example.test
~~~

Một chứng thư có CN “đẹp” nhưng **thiếu DNS-ID cần thiết** vẫn không đáp ứng mục tiêu xác thực hostname.

## 4. Quy tắc SAN dNSName: khớp chính xác và wildcard

### 4.1. Khớp hostname thông thường

Nếu URL yêu cầu `https://api.lab.example.test/`, certificate có `DNS:api.lab.example.test` là **một ứng viên khớp danh tính**. Việc tên đó là cùng một IP với `www.lab.example.test` không làm tên `www` tự khớp khi certificate không có SAN tương ứng.

DNS name matching thông thường **không phân biệt hoa thường** theo quy tắc DNS và profile ứng dụng. Tuy nhiên, không được hiểu điều đó là có thể bỏ qua **chuẩn hóa tên miền, IDN hoặc những điều kiện profile**. Ngoài ra, dấu chấm kết thúc FQDN, chuỗi URL và cách thư viện phân tích tên phải được xử lý đúng; nên dùng thư viện TLS/HTTP được bảo trì thay vì viết hàm so khớp tùy tiện.

### 4.2. Wildcard SAN đại diện được cho những tên nào?

Một `dNSName` có wildcard như `DNS:*.lab.example.test` thường dùng để đại diện cho **một nhãn bên trái** của `lab.example.test`. Theo mô hình matching chặt thông dụng:

| SAN trong chứng thư | Hostname được yêu cầu | Kết quả về tên |
|---|---|---|
| `DNS:api.lab.example.test` | `api.lab.example.test` | **MATCH** |
| `DNS:api.lab.example.test` | `admin.lab.example.test` | **NO MATCH** |
| `DNS:*.lab.example.test` | `api.lab.example.test` | **MATCH** |
| `DNS:*.lab.example.test` | `a.lab.example.test` | **MATCH** |
| `DNS:*.lab.example.test` | `lab.example.test` | **NO MATCH** |
| `DNS:*.lab.example.test` | `v1.api.lab.example.test` | **NO MATCH** |
| `DNS:*.lab.example.test` | `api.other.example.test` | **NO MATCH** |
| `DNS:api.lab.example.test` | `API.LAB.EXAMPLE.TEST` | **MATCH**, theo so khớp DNS thông thường |

**Lưu ý:** wildcard không đại diện cho số nhãn tùy ý. Trong RFC 9525, wildcard được giới hạn ở **toàn bộ nhãn trái nhất**, không dùng kiểu wildcard một phần như `f*.example.com`. Đối với CA công khai còn có các quy tắc phát hành và kiểm soát quyền sở hữu miền; không nên tìm cách dùng wildcard cho public suffix hoặc tên ngoài quyền quản lý.

### 4.3. Muốn bao phủ apex và subdomain phải làm sao?

~~~text
Service expects:
  https://lab.example.test
  https://www.lab.example.test
  https://api.lab.example.test

Possible SAN inventory:
  DNS:lab.example.test
  DNS:*.lab.example.test

Or explicit SAN list:
  DNS:lab.example.test
  DNS:www.lab.example.test
  DNS:api.lab.example.test
~~~

**`*.lab.example.test` không bao phủ `lab.example.test`**. Khi chỉ có vài tên, liệt kê SAN cụ thể giúp dễ kiểm soát phạm vi. Wildcard thuận tiện cho nhiều subdomain một tầng nhưng làm tăng tác động nếu private key bị lộ, và cần chính sách cấp phát/thu hồi phù hợp.

### 4.4. URL scheme, path và port không phải DNS-ID

Tên `api.lab.example.test` trong SAN không chứa `https://`, `/v1/orders` hay `:8443`. Danh tính DNS hostname cho TLS khác với **HTTP path, cổng TCP hoặc routing rule**. Ví dụ server ở `https://api.lab.example.test:8443/` vẫn kiểm tra DNS hostname `api.lab.example.test` đối với DNS-ID; cổng 8443 là thông tin kết nối, không phải một phần của dNSName.

## 5. Kết nối bằng IP: cần SAN iPAddress, không phải DNS mang chuỗi IP

Khi client định kết nối trực tiếp tới `https://192.0.2.20/`, danh tính tham chiếu là **địa chỉ IP**. Khi profile TLS/ứng dụng hỗ trợ IP literal, certificate cần có SAN loại **`iPAddress`** với giá trị IP đó. RFC 5280 biểu diễn iPAddress bằng **octets**, không chỉ một chuỗi văn bản giống địa chỉ IP.

~~~text
Case A:
  URL: https://192.0.2.20/
  SAN: IP Address:192.0.2.20
  => Có thể MATCH IP-ID khi các kiểm tra khác đạt

Case B:
  URL: https://192.0.2.20/
  SAN: DNS:192.0.2.20
  => KHÔNG phải SAN iPAddress đúng loại cho IP literal

Case C:
  URL: https://api.lab.example.test/
  DNS resolves to: 192.0.2.20
  SAN: DNS:api.lab.example.test
  => Có thể MATCH DNS-ID, IP là địa chỉ vận chuyển
~~~

Một chứng thư có cả `DNS:api.lab.example.test` và `IP Address:192.0.2.20` có thể phục vụ hai cách truy cập nếu CA/policy cho phép và client xác minh đúng kiểu danh tính. **Không tự thêm mọi IP nội bộ vào chứng thư công khai**: cần xét chính sách CA, phạm vi công khai thông tin và vòng đời thay đổi IP.

**IPv6** cũng dùng SAN `iPAddress` theo biểu diễn nhị phân đúng. Khi client gọi `https://[2001:db8::20]/`, phải kiểm tra IPv6 address identity tương ứng, không “chuyển” cú pháp dấu ngoặc vuông của URL vào DNS-ID.

## 6. DNS, CNAME, SNI và HTTP Host: bốn khái niệm khác nhau

### 6.1. Một yêu cầu đi qua các lớp

~~~mermaid
flowchart TD
    U["URL: https://shop.lab.example.test/"] --> D["DNS resolution"]
    D --> C["CNAME: shop → edge.cdn.lab.example.test"]
    C --> I["A/AAAA: địa chỉ Edge"]
    I --> T["TLS ClientHello có thể mang SNI shop.lab.example.test"]
    T --> P["Edge chọn chứng thư theo SNI/cấu hình"]
    P --> V["Client kiểm tra SAN cho shop.lab.example.test"]
    V --> H["HTTP Host / :authority để route request"]
~~~

**DNS CNAME** là một kiểu alias khi phân giải tên. Nó không chuyển danh tính mà HTTPS client ban đầu định xác thực thành tên đích CNAME. Nếu client gọi `shop.lab.example.test` nhưng DNS trỏ CNAME tới `edge.cdn.lab.example.test`, chứng thư mà edge xuất trình phải **phù hợp `shop.lab.example.test`**, không chỉ phù hợp tên nội bộ của CDN.

### 6.2. SNI chọn certificate, SAN xác thực identity

**Server Name Indication (SNI)** là thông tin mà nhiều TLS client gửi trong ClientHello để server biết **tên dịch vụ client muốn kết nối**, từ đó có thể chọn virtual host và chứng thư phù hợp. SNI và SAN thường liên hệ với cùng một hostname nhưng **vai trò khác nhau**:

| Thành phần | Nguồn/công dụng chính | Có chứng minh danh tính không? |
|---|---|---|
| **DNS A/AAAA/CNAME** | Tìm địa chỉ/alias được định tuyến | Không thay thế xác minh chứng thư |
| **TLS SNI** | Gợi ý tên cho server lựa chọn certificate/context | **Không**, SNI tự thân không xác thực server |
| **Certificate SAN** | Mang danh tính để client so với reference identity | Có ý nghĩa khi kết hợp chain, key và chính sách xác minh |
| **HTTP Host / HTTP/2 `:authority`** | Xác định tài nguyên/virtual host ở tầng HTTP | Không tự thay thế TLS identity validation |
| **TLS ALPN** | Thương lượng giao thức ứng dụng, ví dụ HTTP/1.1 hoặc HTTP/2 | Không xác nhận hostname |

Nếu server chọn sai certificate vì SNI/virtual-host mapping sai, client đúng phải phát hiện **hostname mismatch** hoặc lỗi certificate tương ứng. Không yêu cầu người dùng nhấn “continue anyway” để vòng qua cấu hình sai.

### 6.3. Alias tới CDN, ingress hoặc service mesh

Với CDN, external hostname (ví dụ `shop.lab.example.test`) và hostname kỹ thuật (`origin-23.internal.example.test`) là **hai danh tính ở hai TLS hops khác nhau**:

- Browser → CDN: certificate edge phải hợp với `shop.lab.example.test`.
- CDN → origin: CDN phải xác thực hostname/service identity được cấu hình cho **origin TLS connection**, không mặc định lấy tên DNS của CDN.
- Ingress → microservice: nếu có TLS/mTLS riêng, certificate backend phải có SAN phù hợp với **danh tính backend được chính sách tin cậy**.

Đúng SAN ở frontend **không chứng minh** các hop backend được mã hóa hoặc xác thực đúng.

## 7. IDN, chữ hoa/thường và xử lý hostname an toàn

Tên miền có ký tự quốc tế (*Internationalized Domain Names, IDN*) có thể được biểu diễn dưới dạng **Unicode/U-label** ở giao diện người dùng và dạng **ASCII-compatible A-label (Punycode)** khi cần đưa vào ngữ cảnh DNS/TLS. `dNSName` trong X.509 dùng kiểu IA5String, vì vậy hệ thống cần áp dụng xử lý IDNA đúng thay vì nhét trực tiếp ký tự Unicode tùy tiện vào dNSName.

**Hướng vận hành:**

1. Xác định **reference identity** từ URL hoặc cấu hình tin cậy của ứng dụng.
2. Chuẩn hóa tên theo profile IDNA/DNS tương ứng trước khi so khớp.
3. Dùng API hostname verification chính thức của TLS library; không tự viết hàm lowercase/replace chuỗi đủ loại.
4. Không coi tên Unicode trông giống nhau là đồng nhất về mặt mật mã: các ký tự khác bộ chữ có thể tạo **homograph** dù hình thức gần giống.
5. Không tự động tin SAN do một bên trung gian gửi trong HTTP header hoặc phát sinh sau DNS redirect.

Ví dụ: `paymеnt.example.test` (có thể chứa ký tự trông giống `e` nhưng thuộc bảng chữ khác) **không mặc nhiên là cùng hostname** với `payment.example.test`. Cần dùng URL chuẩn, danh tính đúng, xác minh cert và các biện pháp chống phishing; dấu ổ khóa TLS **không chứng minh website không lừa đảo**.

## 8. Lập danh mục SAN cho dịch vụ nhiều hostname

Trong vận hành mạng, một dịch vụ có thể được truy cập qua nhiều tên: domain công khai, alias dành cho mobile app, FQDN nội bộ, tên ingress hoặc hostname của môi trường thử nghiệm. Điều quan trọng là xác định **client thực sự kết nối bằng tên nào ở từng TLS hop**, rồi xây danh sách SAN tối thiểu.

### 8.1. Ví dụ inventory

| Điểm TLS kết thúc | Tên client thực sự sử dụng | Loại SAN thích hợp | Ghi chú |
|---|---|---|---|
| Public edge / CDN | `shop.lab.example.test` | `dNSName=shop.lab.example.test` | Client xác minh tên URL public |
| Public API gateway | `api.lab.example.test` | `dNSName=api.lab.example.test` | Mobile app và browser |
| Internal ingress | `api.int.lab.example.test` | `dNSName=api.int.lab.example.test` | Chứng thư từ private PKI nếu phù hợp |
| Backend origin | `origin-1.internal.lab.example.test` | `dNSName=origin-1.internal.lab.example.test` | Proxy xác minh tên origin theo policy |
| API gọi trực tiếp bằng IP | `192.0.2.20` | `iPAddress=192.0.2.20` | Chỉ khi ứng dụng thật sự dùng IP và CA cho phép |
| Service mesh | Identity kiểu service/URI theo profile | URI SAN hoặc identity type của service mesh | Không giả định dNSName luôn là identity workload |

Các tên là **giả định**. Không nhất thiết gom tất cả vào một chứng thư: nhiều certificate nhỏ theo trust boundary, chủ sở hữu và chu kỳ gia hạn có thể an toàn và dễ vận hành hơn một certificate đa SAN quá lớn.

### 8.2. SAN explicit hay wildcard?

**Explicit SAN** (`DNS:api.lab.example.test`, `DNS:admin.lab.example.test`) phù hợp khi danh sách hostname hữu hạn, ranh giới bảo mật khác nhau hoặc cần quản lý chủ sở hữu theo dịch vụ. **Wildcard SAN** (`DNS:*.lab.example.test`) hữu ích cho nhiều subdomain cùng một nhãn và cùng phạm vi tin cậy.

| Tiêu chí | Explicit SAN | Wildcard SAN |
|---|---|---|
| Phạm vi danh tính | Tên được liệt kê cụ thể | Có thể bao phủ nhiều tên một nhãn |
| Khi thêm hostname mới | Thường cần cấp/cập nhật chứng thư | Có thể không cần cấp lại nếu wildcard phù hợp |
| Khi khóa riêng bị lộ | Tác động đến các tên trên chứng thư đó | Có thể ảnh hưởng toàn bộ nhóm hostname khớp wildcard |
| Phân định ownership | Dễ gắn với từng dịch vụ | Cần kiểm soát rất chặt người được quyền dùng khóa wildcard |
| Theo dõi certificate inventory | Có thể nhiều certificate cần gia hạn | Ít certificate nhưng phạm vi quyền lớn |
| Apex (`lab.example.test`) | Bao phủ nếu liệt kê rõ | `*.lab.example.test` **không** bao phủ apex |

**Thiết kế tối thiểu quyền:** không dùng một wildcard và một private key chung cho các team/tenant không cùng trust boundary chỉ vì nó giúp tiết kiệm công sức cấp cert. Chia certificate theo trách nhiệm ứng dụng, CA policy, key isolation và phạm vi phát hành.

### 8.3. Một tên được phục vụ trên nhiều IP hoặc nhiều vùng

Một hostname có thể resolve tới nhiều địa chỉ A/AAAA, CDN edges, load balancers hoặc các vùng active–active. **SAN gắn với tên dịch vụ**, không gắn với việc DNS hiện tại đang trả IP nào. Mỗi endpoint TLS có thể phục vụ cùng certificate hoặc certificate riêng, miễn certificate mà client thực sự nhận được **được xác minh hợp lệ cho hostname yêu cầu**.

Khi failover, kiểm tra certificate của **tất cả đích dự phòng**, gồm SNI routing, SAN, chain, hiệu lực, khóa và cấu hình upstream verification. TTL DNS thấp không sửa được một chứng thư thiếu SAN ở vùng dự phòng.

## 9. Xin cấp chứng thư: CSR có SAN, CA phát hành mới quyết định

### 9.1. Chuỗi trách nhiệm

~~~mermaid
flowchart LR
    O["Service owner: danh sách hostname đã duyệt"] --> P["PKI policy / domain control"]
    P --> K["Tạo private key an toàn"]
    K --> Q["CSR đề xuất SAN"]
    Q --> CA["CA kiểm tra quyền và cấp certificate"]
    CA --> D["Certificate có SAN do CA phát hành"]
    D --> E["Triển khai TLS endpoint"]
    E --> V["Client xác minh SAN, chain, key"]
    V -. "Audit / renewal" .-> O
~~~

**CSR (Certificate Signing Request)** thường chứa public key, Subject và các extension **được yêu cầu**, trong đó có thể có SAN. CA phải áp dụng chính sách cấp chứng thư và xác minh quyền đối với các danh tính. **SAN trong CSR không đồng nghĩa SAN đã xuất hiện trong certificate do CA ký**; CA có thể từ chối, sửa hoặc không chấp nhận yêu cầu tùy policy.

### 9.2. Ví dụ OpenSSL CSR config trong lab

Đây là **nội dung một file cấu hình minh họa** `san-request.cnf`, dùng khi owner đã có private key hợp lệ được quản lý an toàn:

~~~ini
[ req ]
prompt = no
distinguished_name = dn
req_extensions = req_ext

[ dn ]
CN = api.lab.example.test
O = Example Lab

[ req_ext ]
subjectAltName = @san_entries

[ san_entries ]
DNS.1 = api.lab.example.test
DNS.2 = api-alt.lab.example.test
IP.1 = 192.0.2.20
~~~

Với một private key **đã có và được bảo vệ** ở phòng lab, cú pháp đề xuất CSR:

~~~bash
# Chỉ là thao tác khi xây lab/PKI được phép, không chạy trên production tùy tiện.
# File lab-server.key phải được quản lý và cấp quyền truy cập phù hợp.
openssl req -new \
  -key lab-server.key \
  -out lab-server.csr \
  -config san-request.cnf

# Chỉ đọc CSR: xác nhận SAN nằm ở yêu cầu, chưa phải certificate đã cấp.
openssl req -in lab-server.csr -noout -text
~~~

**Không dùng ví dụ này để đưa địa chỉ IP của tổ chức vào certificate công khai**. Chỉ thêm `IP.1` khi dịch vụ thật sự cần xác minh IP literal, CA/profile chấp thuận và có chính sách vòng đời IP rõ ràng. Trong triển khai thực tế, private key nên được sinh/lưu trong key store, TPM/HSM hoặc secret manager tùy mức đảm bảo; không sao chép key ra ticket hoặc repository.

### 9.3. Xác minh chứng thư sau khi CA cấp

Quy trình không dừng ở CSR:

1. Kiểm tra CA đã phát hành **đúng tên và đúng loại SAN** (`dNSName` hoặc `iPAddress`).
2. Kiểm tra Subject, issuer, chain/intermediate, EKU `serverAuth`, Key Usage và hiệu lực.
3. Đảm bảo certificate **khớp private key đang được TLS server sử dụng**.
4. Kiểm tra SNI virtual host/default certificate, các phiên bản TLS và cipher chính sách.
5. Thực hiện **positive và negative hostname validation tests** từ client đại diện.
6. Lưu inventory: certificate fingerprint/serial, SAN set, owner, CA, ngày hết hạn, endpoint triển khai và lịch gia hạn.

Nếu certificate có SAN thiếu hoặc sai, phải **sửa yêu cầu/điều kiện CA và cấp lại đúng**. Không thêm hostname bằng cách sửa trường hiển thị Subject trên máy chủ; SAN là một phần của nội dung certificate được chữ ký CA bảo vệ.

## 10. ACME, DNS challenge và Certificate Transparency

### 10.1. ACME hỗ trợ việc gì?

**ACME** (Automated Certificate Management Environment, RFC 8555) giúp tự động hóa quy trình **yêu cầu, xác minh quyền kiểm soát identifier và cấp/gia hạn chứng thư** với CA hỗ trợ. Những cơ chế validation thường gặp gồm **HTTP-01** hoặc **DNS-01** theo khả năng và chính sách.

Quy trình đơn giản:

~~~mermaid
sequenceDiagram
    participant O as ACME Client / Service Owner
    participant C as ACME CA
    participant D as DNS hoặc HTTP validation endpoint
    O->>C: Yêu cầu certificate cho danh sách identifier
    C-->>O: Challenge được hỗ trợ
    O->>D: Chuẩn bị proof of control theo challenge
    C->>D: Kiểm tra identifier control
    D-->>C: Bằng chứng được chấp nhận / từ chối
    C-->>O: Certificate hoặc lỗi policy
    O->>O: Triển khai, xác minh SAN, lập lịch gia hạn
~~~

**HTTP-01** phù hợp một số tên được phục vụ qua HTTP theo quy định challenge; **DNS-01** dùng bản ghi DNS chứng minh kiểm soát tên miền và được dùng phổ biến cho wildcard khi CA hỗ trợ. Các quy tắc cấp phát cụ thể phụ thuộc CA, profile và identifier. Không có nghĩa “nếu ghi SAN trong CSR thì CA buộc phải ký”.

### 10.2. Ai được phép thay DNS để xin certificate?

Quyền chỉnh bản ghi DNS validation là quyền nhạy cảm vì có thể giúp chứng minh quyền điều khiển một hostname. Khi dùng ACME DNS-01:

- Hạn chế phạm vi **API token DNS** chỉ ở zone/record/chức năng thực sự cần.
- Không ghi token vào source code, log CI hoặc pipeline artifacts.
- Dùng vault/secret manager và cơ chế xoay credential.
- Tách quyền **yêu cầu certificate** với quyền **đưa certificate lên các endpoint nhạy cảm** khi kiến trúc yêu cầu.
- Audit record validation, danh sách SAN được xin, và các lần gia hạn thất bại.

### 10.3. Certificate Transparency (CT) và tính riêng tư tên miền

Certificate công khai do CA tin cậy cấp thường phải tuân thủ các yêu cầu **Certificate Transparency**, làm xuất hiện thông tin certificate và danh sách tên SAN trong các log công khai theo profile áp dụng. Do đó, đừng xem hostname trong chứng thư public là **bí mật về topology**.

Ví dụ, các tên `admin.lab.example.test` hoặc `origin-internal.lab.example.test` khi xuất hiện trên public certificate có thể tiết lộ mô hình đặt tên mà tổ chức không muốn công bố. Cân nhắc **private PKI** cho tên nội bộ khi phù hợp và tránh dựa vào “ẩn hostname” như biện pháp an toàn duy nhất.

CT hỗ trợ phát hiện certificate không mong muốn nhưng **không tự ngăn mọi sai sót cấp phát, không thay thế certificate validation trên client hoặc kiểm soát khóa riêng**.

### 10.4. Vòng đời và gia hạn

Certificate hết hạn có thể gây outage ngay cả khi SAN đúng. Ngược lại, certificate còn hạn nhưng **không có hostname mới** cũng gây lỗi cho một phần client. Quy trình gia hạn nên có:

1. Phát hiện certificate sắp hết hạn; owner rõ và cảnh báo trước theo nhu cầu.
2. So danh sách SAN **thực tế đang dùng** với SAN được đề xuất cấp mới.
3. Cấp/gia hạn và kiểm tra đầy đủ certificate chain, SAN, policy, private key.
4. Triển khai **theo đợt** tới các TLS endpoints, gồm vùng backup và IPv4/IPv6.
5. Chạy positive/negative tests theo hostname từ các client ở những trust boundaries khác nhau.
6. Theo dõi lỗi handshake, cert mismatch, SNI default certificate và chuẩn bị rollback.

## 11. Thực hành đọc certificate và SAN bằng OpenSSL

Những lệnh sau chỉ chạy trong lab được phép. Giả sử `lab-server.pem` là **chứng thư công khai đã nhận** và `lab-root-ca.pem` là CA mà lab tin cậy. Không cần hoặc không nên đưa private key vào bước kiểm tra SAN.

### 11.1. Đọc SAN, Subject và thời hạn từ certificate

~~~bash
# Đọc thông tin cơ bản của certificate (không cần private key).
openssl x509 -in lab-server.pem \
  -noout -subject -issuer -serial -dates

# Chỉ đọc extension SAN.
openssl x509 -in lab-server.pem \
  -noout -ext subjectAltName

# Đọc mục đích sử dụng khi OpenSSL hỗ trợ tên extension này.
openssl x509 -in lab-server.pem \
  -noout -ext extendedKeyUsage
~~~

Ví dụ đầu ra minh họa:

~~~text
X509v3 Subject Alternative Name:
    DNS:api.lab.example.test, DNS:api-alt.lab.example.test,
    IP Address:192.0.2.20
~~~

**Đây là dữ liệu giả định.** Việc kiểm tra certificate tĩnh giúp biết certificate có SAN gì, nhưng **không chứng minh server live hiện đang gửi đúng certificate đó**. Muốn biết cấu hình hiệu lực phải thử TLS handshake với đúng hostname/SNI.

### 11.2. Kiểm tra HTTPS server theo DNS hostname

~~~bash
# Test TLS server lab tại 192.0.2.20.
# SNI dùng để chọn virtual host, verify_hostname kiểm tra reference identity.
# CAfile là lab CA được phê duyệt, không phải chấp nhận CA tùy tiện.
openssl s_client \
  -connect 192.0.2.20:443 \
  -servername api.lab.example.test \
  -verify_hostname api.lab.example.test \
  -CAfile lab-root-ca.pem \
  -verify_return_error \
  -brief < /dev/null
~~~

**Cần xem:** certificate chain verification, hostname verification, negotiated TLS protocol/cipher và kết quả hoàn tất handshake. Một dòng “CONNECTED” chỉ cho biết kết nối TCP hoặc một giai đoạn bắt tay đã xảy ra; **không phải kết luận authentication PASS**. Đồng thời kiểm tra exit code và thông báo lỗi thực.

### 11.3. So tên yêu cầu bằng chính thao tác client HTTP

~~~bash
# Chỉ một HTTP HEAD request qua TLS; đổi IP theo server lab của bạn.
# --resolve ghi đè DNS cho phép thử nhưng giữ URL hostname để kiểm tra SAN.
curl --head --verbose \
  --connect-timeout 3 --max-time 10 \
  --cacert lab-root-ca.pem \
  --resolve api.lab.example.test:443:192.0.2.20 \
  https://api.lab.example.test/health
~~~

`--resolve` **không hủy kiểm tra certificate**: client vẫn định kết nối `api.lab.example.test`, dùng hostname đó để xác minh TLS theo chính sách. Nếu certificate của IP được thử chỉ có `DNS:other.lab.example.test`, client phải từ chối với **hostname mismatch** khi verification được bật.

### 11.4. Xác minh khi URL dùng IP literal

~~~bash
# Truy cập bằng IP là một trường hợp identity khác.
# Server lab phải có SAN loại IP Address:192.0.2.20.
openssl s_client \
  -connect 192.0.2.20:443 \
  -verify_ip 192.0.2.20 \
  -CAfile lab-root-ca.pem \
  -verify_return_error \
  -brief < /dev/null
~~~

`-verify_ip` là phép kiểm tra **IP-ID**, khác `-verify_hostname` cho tên DNS. Khi server dùng virtual host chọn certificate theo tên, test IP literal có thể nhận default certificate không chứa IP SAN và thất bại. Điều này **không tự chứng minh lỗi của CA** mà có thể do policy ứng dụng không hỗ trợ truy cập qua IP.

### 11.5. Kiểm tra certificate có được cấp với SAN yêu cầu không

~~~bash
# So CSR (yêu cầu) và certificate (được CA cấp) trong lab.
openssl req -in lab-server.csr -noout -text
openssl x509 -in lab-server.pem -noout -ext subjectAltName

# Xác minh certificate theo DNS hostname khi có CA tin cậy.
# Với chain nhiều cấp có thể cần cung cấp intermediate phù hợp.
openssl verify \
  -CAfile lab-root-ca.pem \
  -verify_hostname api.lab.example.test \
  lab-server.pem
~~~

Kết quả `openssl verify` có thể không PASS nếu chưa cung cấp intermediate/chain cần thiết, không đúng CA hoặc certificate có mục đích sử dụng chưa phù hợp. **Không diễn giải mọi lỗi verify thành SAN mismatch**; xem mã/thông điệp và kiểm tra chính xác trường nào sai.

## 12. Thiết kế phép thử hostname mismatch có positive control

Một test âm tính đáng tin cậy cần chứng minh cùng môi trường **có thể kết nối được khi chứng thư đúng**, và chỉ thất bại khi **danh tính không đúng**:

| Test | Client gọi | SAN trên cert server lab | Kỳ vọng |
|---|---|---|---|
| Positive control | `https://api.lab.example.test` | `DNS:api.lab.example.test` | **PASS** nếu chain, key và policy khác hợp lệ |
| Wrong DNS name | `https://admin.lab.example.test` | `DNS:api.lab.example.test` | **FAIL** hostname mismatch |
| CN-only attempt | `https://admin.lab.example.test` | `CN=admin.lab.example.test`, SAN chỉ có `DNS:api.lab.example.test` | **FAIL** theo xác minh DNS-ID hiện đại |
| Wildcard one label | `https://a.lab.example.test` | `DNS:*.lab.example.test` | **PASS** nếu các điều kiện khác hợp lệ |
| Wildcard apex | `https://lab.example.test` | `DNS:*.lab.example.test` | **FAIL** tên không khớp |
| Wildcard deeper | `https://v1.a.lab.example.test` | `DNS:*.lab.example.test` | **FAIL** tên không khớp |
| IP literal | `https://192.0.2.20` | `IP Address:192.0.2.20` | **PASS** nếu IP-ID và chain hợp lệ |
| IP type confusion | `https://192.0.2.20` | `DNS:192.0.2.20` | **FAIL** về loại identity |
| Wrong CA | `https://api.lab.example.test` | SAN đúng, CA không được client tin | **FAIL** về chain/trust |
| Expired certificate | `https://api.lab.example.test` | SAN đúng, chứng thư hết hạn | **FAIL** về validity |

Các kết quả **PASS/FAIL trong bảng là kỳ vọng lý thuyết**, không phải kết quả thực thi. Một certificate không được cấp đúng hoặc server không chạy thì test âm tính có thể kết thúc bằng TCP timeout thay vì lỗi SAN; khi đó cần ghi **INCONCLUSIVE**, không nhận là PASS.

### 12.1. Vì sao không dùng cURL `--insecure` để sửa lỗi?

`curl -k` hoặc `--insecure` bỏ các kiểm tra certificate mà bình thường cURL phải thực hiện. Điều này vô hiệu hóa bằng chứng rằng **client chỉ gửi dữ liệu đến endpoint được xác thực đúng**. Nếu bật trong production, một attacker điều khiển đường đi hoặc một proxy ngoài ý muốn có thể dễ dàng tự xuất trình chứng thư không đáng tin mà ứng dụng vẫn tiếp tục giao tiếp.

Khi đang chẩn đoán, hãy xem hostname, SNI, CA chain, SAN, giờ hệ thống, hiệu lực, proxy và backend trước. Nếu cần kết nối không có CA công khai trong lab, cấu hình **trust anchor lab rõ ràng bằng `--cacert` hoặc trust store đúng**, không bỏ xác thực.

## 13. SAN trong mTLS và định danh máy/ứng dụng

Ở **server-authenticated TLS**, client xác minh một danh tính server phù hợp với dịch vụ đã yêu cầu. Trong **mutual TLS (mTLS)**, server còn yêu cầu certificate client và phải kiểm tra danh tính client theo **chính sách ứng dụng/PKI**. Không thể đơn giản áp dụng cùng một quy tắc “hostname URL phải có trong SAN client” cho mọi hệ thống.

### 13.1. Client identity khác server hostname

| Ngữ cảnh | Danh tính thường được xác thực | Loại SAN có thể dùng |
|---|---|---|
| Browser → HTTPS `api.lab.example.test` | Server cung cấp API cho hostname đã gọi | DNS-ID (`dNSName`) |
| Client kết nối bằng IP literal | Server tại địa chỉ IP đã gọi | IP-ID (`iPAddress`) |
| Service A → Service B qua mTLS | Server B theo DNS/service profile; Client A theo workload identity policy | DNS-ID, URI-ID, otherName hoặc kiểu identity được profile cho phép |
| Máy quản trị → thiết bị mạng dùng mTLS | Thiết bị/server và danh tính client theo PKI vận hành | Tùy certificate profile và authorization |

Một service mesh có thể gán client identity bằng **URI SAN**, ví dụ định dạng kiểu `spiffe://trust-domain/ns/namespace/sa/service-account` khi tuân theo hệ sinh thái SPIFFE và cấu hình đúng. Đó **không phải** một DNS hostname để đem so bằng bộ kiểm tra hostname thông thường.

Ví dụ chính sách mTLS:

~~~text
Incoming connection to: payments.internal.lab.example.test
Expected server DNS-ID: payments.internal.lab.example.test
Client certificate identity: approved-workload-id

TLS:
  Verify server certificate chain + DNS-ID
  Verify client certificate chain + configured identity type

Authorization:
  Only approved-workload-id may call POST /payments/settle
~~~

**mTLS authentication không tự thực hiện authorization.** Một client có chứng thư hợp lệ vẫn phải được gắn với vai trò/quyền cần thiết. Nếu ứng dụng chỉ kiểm tra “certificate chain hợp lệ” mà không kiểm tra đúng danh tính hoặc quyền, bất kỳ client được CA tin trong phạm vi rộng có thể nhận quyền vượt quá thiết kế.

### 13.2. Private PKI và name constraints

Private PKI có thể quản lý các tên nội bộ, certificate ngắn hạn, cấp phát workload identities và vòng đời khóa tự động. Khi có nhiều subordinate CA, **name constraints** theo profile PKI có thể hỗ trợ giới hạn phạm vi danh tính mà một CA được quyền cấp, nhưng cấu hình/phần mềm kiểm chứng phải hỗ trợ đúng chuẩn.

Không nên coi name constraints thay cho **kiểm soát phát hành, phê duyệt SAN, phân quyền sử dụng CA, bảo vệ private key và audit**. Nếu trust store thêm một CA nội bộ quyền quá rộng, nó có thể khiến một số client tin những chứng thư ngoài phạm vi intended.

## 14. Đa tầng TLS: SAN của từng hop không nhất thiết giống nhau

### 14.1. Kịch bản nhiều điểm TLS termination

~~~mermaid
flowchart LR
    B["Browser: shop.lab.example.test"] <-->|"TLS #1: DNS-ID shop.lab.example.test"| C["CDN edge"]
    C <-->|"TLS #2: DNS-ID origin-1.internal.lab.example.test"| L["Origin Load Balancer"]
    L <-->|"TLS #3: DNS-ID catalog.service.lab.example.test"| A["API service"]
    A <-->|"mTLS hoặc TLS với identity riêng"| D["Database"]
~~~

Trong sơ đồ:

1. Browser **không** kiểm tra SAN của `origin-1.internal.lab.example.test`, vì nó đang xác thực certificate của **CDN endpoint**.
2. CDN phải xác minh certificate backend theo **tên origin được cấu hình và tin cậy**; DNS lookup backend không tự chọn danh tính xác thực thay client.
3. LB hoặc proxy kết nối API có thể dùng một service DNS-ID khác phù hợp service discovery.
4. Mỗi hop có certificate, CA, SNI, reference identity, cipher và log riêng.

Đừng mặc định sử dụng một certificate wildcard duy nhất và một private key cho **browser-facing edge, ingress nội bộ và database**. Những hop này có thể thuộc các team, CA và trust boundaries khác nhau; chia phạm vi khóa và certificate giảm nguy cơ lan truyền sự cố.

### 14.2. Default certificate và SNI routing

Server phục vụ nhiều HTTPS virtual hosts trên cùng IP thường chọn certificate theo **SNI**. Nếu hostname mới chưa được map hoặc SNI chưa tới đúng server block, endpoint có thể trả **default certificate** cho một tên khác. Kết nối TCP và TLS thậm chí có thể đi được một phần nhưng client phải phát hiện SAN mismatch.

Trong triển khai có proxy, hãy so:

- Hostname trong URL client.
- SNI thực sự được gửi ở **mỗi TLS hop**.
- Certificate chain mà client từng hop **thực tế nhận được**.
- Hostname verification được dùng ở upstream.
- HTTP `Host` / `:authority` được forward để chọn ứng dụng.
- Các cấu hình IPv4/IPv6, cổng bổ sung và đường backup.

**SNI không phải bằng chứng server được xác thực.** Nó giúp server chọn certificate; chỉ **client kiểm tra SAN/chain/handshake** mới kết luận về identity tương ứng.

### 14.3. Certificate thay đổi theo vị trí địa lý hoặc DNS load balancing

Nhiều vùng có thể phục vụ cùng hostname bằng các certificate khác nhau. Điều kiện an toàn là **mọi certificate có thể xuất hiện tại endpoint đều đáp ứng chính sách cho hostname**, không phải mọi vùng bắt buộc có serial/fingerprint giống nhau. Theo dõi tính đồng nhất của **danh tính và trust** thay vì chỉ so certificate bytes.

## 15. Những rủi ro bảo mật liên quan đến SAN

### 15.1. Hostname confusion

Một ứng dụng có thể dùng sai reference identity, ví dụ lấy hostname từ **URL redirect không đáng tin hoặc `Host` header do bên ngoài kiểm soát** để quyết định danh tính TLS upstream. Hậu quả có thể là chọn sai endpoint hoặc chấp nhận một chứng thư vốn hợp lệ **cho một tên khác**, nhưng không phải dịch vụ được ứng dụng dự kiến gọi.

Phòng vệ: cấu hình **đích và danh tính kỳ vọng** từ policy tin cậy, validate URL và origin, giới hạn redirect, tránh tự động gắn trust chỉ vì một chứng thư được CA công khai cấp.

### 15.2. Wildcard scope và private key compromise

Một private key tương ứng certificate `*.lab.example.test` có thể được dùng để chứng minh danh tính cho **nhiều hostname khớp wildcard** trong phạm vi tin cậy. Nếu key bị lộ, attacker có thể cố giả mạo nhiều dịch vụ cùng nhóm tên. Biện pháp:

- Dùng **explicit SAN hoặc wildcard theo domain/trust boundary**.
- Không phân phát cùng private key tới quá nhiều máy/nhóm vận hành.
- Dùng key management, HSM/secret manager và rotation khi phù hợp.
- Có quy trình thu hồi/cấp lại nếu nghi bị lộ key.
- Giám sát phát hành chứng thư bất thường và endpoint mới.

### 15.3. CA misissuance và trust store

Một certificate có SAN phù hợp nhưng **được cấp sai quyền** là rủi ro nghiêm trọng nếu client cũng tin CA tương ứng. Kiểm tra SAN giải quyết phần **“tên có khớp”**, còn quy trình cấp phát và trust store giải quyết phần **“ai được quyền cam kết danh tính đó”**.

Cần quản lý CA tin cậy, kiểm soát DNS/ACME/API token, audit certificate issuance và theo dõi CT khi áp dụng. Không thêm CA root tùy tiện vào mọi laptop chỉ để “chữa lỗi” cho một service cụ thể.

### 15.4. SAN enumeration, thông tin công khai và quyền riêng tư

Nhiều SAN trong một certificate công khai có thể tiết lộ danh sách host liên quan. **Không coi tên host nội bộ là bí mật dài hạn**, nhưng cũng không đưa danh sách MGMT, môi trường test hoặc tên hệ thống nhạy cảm vào chứng thư public nếu không cần. Phân tách public/private PKI và áp dụng naming policy hợp lý.

### 15.5. Chứng thư đúng SAN nhưng hết hạn hoặc sai EKU

SAN matching chỉ là một phần:

- Chứng thư hết hạn: client phải từ chối theo policy.
- Missing/intermediate CA sai: chain không xây được đến trust anchor.
- EKU/key usage không phù hợp `serverAuth`: certificate không hợp ngữ cảnh TLS server.
- Server có certificate đúng tên nhưng **private key không khớp**: handshake không thể chứng minh quyền sở hữu khóa.
- Thu hồi certificate hoặc trust bị rút: client cần xử lý theo cơ chế kiểm tra trạng thái và chính sách thực tế.

Do đó, một “lỗi HTTPS” cần phân loại chính xác trước khi kết luận là **thiếu SAN**.

## 16. Chẩn đoán các lỗi SAN và hostname thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xác minh |
|---|---|---|
| `hostname mismatch` | SAN thiếu tên URL | Đọc SAN trên certificate live; so hostname mà client yêu cầu |
| CN đúng nhưng client vẫn reject | SAN không có DNS-ID phù hợp; client không fallback CN | Xem certificate extension SAN và verifier policy |
| Cert có `*.example.test` nhưng apex lỗi | Wildcard không khớp `example.test` | Thêm explicit apex SAN hoặc certificate riêng |
| Cert wildcard không khớp `a.b.example.test` | Wildcard chỉ khớp một nhãn | Thiết kế SAN cho đúng mức subdomain |
| CNAME trỏ CDN nhưng TLS lỗi | CDN certificate thiếu tên public alias | Xác minh SAN của edge với hostname URL ban đầu |
| Chỉ một vùng/địa chỉ lỗi | Certificate deploy thiếu ở node backup/IPv6 | Kiểm tra mọi endpoint, SNI và chain trên từng node |
| `s_client` hiện cert khác với cURL | SNI, default vhost, IP/backend khác | So `-servername`, URL, `--resolve`, phiên bản và proxy |
| Dùng URL IP nhưng cert có DNS tên IP | Sai loại `dNSName` vs `iPAddress` | Xem extension và test `-verify_ip` |
| `unable to get local issuer certificate` | Thiếu CA/intermediate hoặc trust store khác | Kiểm tra chain, issuer, CA bundle |
| `certificate has expired` | Hết hạn, rotation lỗi, đồng hồ sai | Xem notAfter, thời gian hệ thống, deploy history |
| Cert chain đúng nhưng serverAuth lỗi | EKU/key usage không đúng ngữ cảnh | Kiểm tra EKU, certificate profile và validator |
| mTLS handshake được nhưng API 403 | Client identity đã xác thực nhưng không được cấp quyền | So SAN identity, RBAC/authorization, logs |
| Reverse proxy gọi backend HTTPS vẫn gặp MITM risk | Upstream certificate verification bị tắt hoặc sai hostname | Kiểm tra upstream CA và `verify name` config |
| Certificate đã gia hạn nhưng một số client vẫn lỗi | Endpoint còn dùng cert cũ, load balancer chưa reload, cache/connection | So serial, fingerprint và chain theo từng đường |
| SAN chứa IDN hiển thị khác ý định | IDNA/A-label normalization hoặc tên confusable | So reference identity chuẩn hóa và dNSName thực |
| Certificate đúng nhưng HTTP 404/401 | TLS thành công, ứng dụng/Host/authorization lỗi | Tách TLS logs khỏi HTTP response |

### 16.1. Trình tự phân tích một lỗi hostname

1. **Ghi hostname chính xác** từ URL/config của client, port, thời gian UTC và route.
2. **Kiểm tra DNS** A/AAAA/CNAME và địa chỉ client thực sự kết nối.
3. **Kiểm tra SNI**, certificate được server live trả, tránh nhầm default vhost.
4. Đọc **SAN dNSName/iPAddress** và so đúng loại với reference identity.
5. Nếu tên khớp, xem **chain, CA, validity, EKU, revocation policy và handshake**.
6. Với proxy/CDN, lặp lại phép thử ở **từng TLS hop**, không chỉ ở public edge.
7. Nếu TLS PASS nhưng giao dịch lỗi, tiếp tục điều tra **Host routing, firewall, DNS, authentication/authorization và backend**.

### 16.2. Sai lầm khi dùng hostname trong file hosts

Khi debug, kỹ sư có thể tạm ánh xạ `api.lab.example.test` → `192.0.2.20` trong file hosts hoặc dùng `curl --resolve`. Việc này chỉ ảnh hưởng **chọn địa chỉ đích**, không đổi danh tính của URL mà TLS client cần xác minh. Đây là tính chất hữu ích để thử certificate của vùng dự phòng **trước khi cập nhật DNS**.

Ngược lại, đổi URL thành `https://192.0.2.20` không còn kiểm tra DNS-ID `api.lab.example.test`: lúc đó là test **IP literal** với yêu cầu danh tính khác. Không nên so hai phép thử như thể chúng hoàn toàn tương đương.

## 17. Quy trình triển khai thay đổi SAN có kiểm soát

### Bước 1 — Thu danh sách hostname và TLS endpoints

Tổng hợp URL người dùng gọi, các host alias, internal service DNS, SNI và TLS termination points; phân nhóm theo environment (prod/staging), team sở hữu, CA và trust boundary. Kiểm tra IPv4/IPv6, CDN, các vùng backup và dịch vụ mesh.

### Bước 2 — Xác định loại identity

Phân loại **DNS hostname (`dNSName`)**, **IP literal (`iPAddress`)** và identity kiểu URI/service dành cho profile ứng dụng cụ thể. Không đưa chuỗi IP vào dNSName hay dùng hostname verification cho URI-ID không phù hợp.

### Bước 3 — Giới hạn SAN tối thiểu

Chọn explicit SAN, wildcard hoặc certificate riêng theo **quyền hạn, mức nhạy cảm và tần suất thay đổi**. Xem lại ai được phép cấp certificate cho từng hostname, tránh trộn tên public với quản trị nội bộ không cần thiết.

### Bước 4 — Xin cấp và kiểm tra

Tạo CSR/ACME request theo quy trình được phê duyệt, xác minh quyền điều khiển domain, nhận certificate, so SAN/chain/EKU/validity với request. Bảo vệ private key xuyên suốt.

### Bước 5 — Triển khai thử / canary

Đưa certificate tới endpoint pilot, xác minh bằng `openssl s_client` với đúng SNI và hostname. Thử cả **positive control và negative control**; xem application health, proxy logs và client TLS errors.

### Bước 6 — Rollout production có theo dõi

Triển khai từng nhóm, kiểm tra **edge, origin, các node/region, IPv4/IPv6**, không quên reload/restart theo cơ chế an toàn của server. Đo handshake failures, certificate mismatch, client success và certificate serial/fingerprint đang phục vụ.

### Bước 7 — Thu hồi và cập nhật inventory

Khi mọi endpoint đã chuyển thành công, thu hồi/loại bỏ certificate/key cũ theo policy, cập nhật owner và lịch gia hạn. Nếu có suspected key compromise, chuyển sang incident response và quy trình reissue/revoke thích hợp.

~~~mermaid
flowchart TD
    A["Danh sách hostname / reference identity"] --> B["Phân nhóm trust boundary và cert owner"]
    B --> C["Chọn SAN + CA profile"]
    C --> D["CSR / ACME authorization"]
    D --> E["CA phát hành certificate"]
    E --> F["Đọc SAN, chain, EKU, validity"]
    F --> G{"Đúng yêu cầu?"}
    G -- "Không" --> C
    G -- "Có" --> H["Canary trên TLS endpoints"]
    H --> I["Test đúng/sai hostname, SNI, IP và app"]
    I --> J{"Đạt policy và SLO?"}
    J -- "Không" --> K["Rollback / sửa cert hoặc mapping"]
    J -- "Có" --> L["Rollout / audit / renewal monitoring"]
~~~

## 18. Case study: DNS failover thành công nhưng HTTPS không hoạt động

### 18.1. Bối cảnh giả định

Một tổ chức triển khai:

- Dịch vụ public: `billing.lab.example.test`.
- Primary region A: `192.0.2.20`, đã có certificate chứa `DNS:billing.lab.example.test`.
- Standby region B: `198.51.100.20`, đang chạy reverse proxy với certificate **chỉ chứa `DNS:standby.lab.example.test`**.
- DNS health-based failover cập nhật A record khi region A unhealthy.
- Ứng dụng browser và API client **bật certificate validation đầy đủ**.

Khi vùng A mất kết nối, DNS authoritative và nhiều resolver chuyển sang B. Network monitoring thấy TCP/443 trên B vẫn mở, nhưng người dùng gặp **TLS hostname mismatch** khi truy cập `https://billing.lab.example.test`.

~~~mermaid
flowchart LR
    C["Client gọi billing.lab.example.test"] --> R["DNS / failover policy"]
    R -- "Primary khỏe" --> A["Region A: cert SAN billing.lab.example.test"]
    R -- "Primary lỗi" --> B["Region B: cert SAN standby.lab.example.test"]
    B -. "Tên client cần không có trong SAN" .-> X["TLS hostname verification FAIL"]
~~~

### 18.2. Điều tra theo các lớp

| Quan sát | Ý nghĩa | Hành động |
|---|---|---|
| DNS trả B đúng | DNS failover đã thay đổi đích | Không kết luận end-to-end đã phục hồi |
| TCP/443 tại B mở | Cổng dịch vụ tiếp nhận TCP | Chưa chứng minh TLS identity đúng |
| SNI từ client là `billing.lab.example.test` | Client muốn dịch vụ public | Kiểm tra virtual host/cert mapping của B |
| SAN của certificate B chỉ có `standby.lab.example.test` | Không khớp public hostname | Xin cấp/triển khai certificate có SAN đúng |
| Client từ chối HTTPS | Authentication đang ngăn tin endpoint sai | Không “sửa” bằng cách tắt xác minh cert |

### 18.3. Phương án khắc phục

1. **Trước failover:** kiểm tra các vùng dự phòng bằng `curl --resolve billing.lab.example.test:443:198.51.100.20` để **giữ nguyên hostname** mà ép kết nối tới IP standby.
2. Xin cấp hoặc triển khai certificate đúng SAN cho public hostname lên region B; kiểm tra chain, SNI, expiry, Key Usage/EKU và quyền key.
3. Đồng bộ cấu hình TLS và health check. Health endpoint chỉ trả HTTP 200 dưới một tên khác **không chứng minh** public hostname TLS sẽ hoạt động.
4. Chạy thử từ nhiều client/trust stores; xác nhận các browser và API clients thực hiện được request có xác minh certificate.
5. Gắn **hostname TLS verification** vào tiêu chí readiness của vùng dự phòng, cùng kiểm tra database, firewall, routing và dịch vụ phụ thuộc.

### 18.4. Kết quả kỳ vọng của diễn tập (giả định)

~~~text
Test: FAILOVER-SAN-LAB-01
Source URL: https://billing.lab.example.test/health
Standby IP: 198.51.100.20

Before fix:
  DNS answer: standby
  TCP/443: reachable
  Presented certificate SAN: standby.lab.example.test
  TLS hostname validation: FAIL

After planned fix:
  Presented certificate SAN includes: billing.lab.example.test
  TLS chain validation: PASS (if CA/trust/expiry correct)
  TLS hostname validation: PASS
  Application health: PASS if backend healthy

Status: illustrative scenario; actual test not executed
~~~

**Bài học:** **route/DNS failover và TLS hostname verification là hai lớp độc lập nhưng cùng quyết định tính sẵn sàng**. Không làm suy yếu TLS authentication để che một lỗi vận hành SAN.

## 19. Ma trận kiểm thử SAN, hostname và chuỗi tin cậy

| Test ID | Mục tiêu | Cách xác minh | Điều kiện PASS |
|---|---|---|---|
| **SAN-01** | Certificate công khai có DNS SAN theo inventory | Đọc SAN trên cert live và so whitelist được duyệt | Tất cả tên bắt buộc xuất hiện đúng loại, không có SAN ngoài quyền |
| **SAN-02** | DNS hostname chính xác được chấp nhận | OpenSSL/cURL với URL đúng, SNI và CA phù hợp | Chain, hostname, handshake và request đều hợp lệ |
| **SAN-03** | DNS hostname sai bị từ chối | Một endpoint lab có cert hợp lệ cho tên khác | Lỗi hostname verification rõ ràng; positive control thành công |
| **SAN-04** | CN không được dùng để bypass SAN | Cert test CN trùng nhưng SAN DNS-ID không trùng | Client từ chối theo policy hiện đại |
| **SAN-05** | Wildcard khớp đúng một cấp | Test `a.lab.example.test` với `*.lab.example.test` | Khớp khi các điều kiện khác hợp lệ |
| **SAN-06** | Wildcard không khớp apex hoặc hai cấp | Test `lab.example.test`, `v1.a.lab.example.test` | Không nhận wildcard ngoài phạm vi |
| **SAN-07** | IP literal dùng đúng loại | OpenSSL `-verify_ip` với IP SAN | IP-ID trùng, không lẫn dNSName có chuỗi IP |
| **SAN-08** | DNS alias/CNAME không làm đổi reference identity | Dùng `curl --resolve` giữ hostname gốc tới edge | Edge có cert đúng tên URL client yêu cầu |
| **SNI-01** | Đúng virtual host ở mọi TLS endpoint | Truy vấn với SNI của từng dịch vụ; so serial/SAN | Không nhận default cert sai tên |
| **CHAIN-01** | Certificate chain tin cậy | Xác minh trust anchor, intermediate, signature, validity | Không có lỗi chain, expiry hoặc trust |
| **EKU-01** | Certificate đúng mục đích TLS server | Kiểm tra EKU, Key Usage và server policy | Không dùng cert sai mục đích |
| **MTLS-01** | Client certificate identity được kiểm đúng | Test client hợp lệ và client sai identity trong lab | Chỉ client có đúng danh tính/quyền được chấp nhận |
| **REGION-01** | Backup region có SAN giống yêu cầu dịch vụ | Ép kết nối tới IP vùng dự phòng với URL không đổi | DNS hostname xác minh được trên tất cả vùng |
| **IPV6-01** | IPv4/IPv6 trả certificate đúng | Test qua cả A và AAAA khi kiến trúc dual-stack | Không có stack trả certificate sai hoặc hết hạn |
| **ACME-01** | SAN được CA cấp đúng yêu cầu | So CSR/ACME identifiers với certificate phát hành | Tên và loại identifier đúng policy, không cấp vượt phạm vi |
| **ROT-01** | Gia hạn không đổi sai SAN | So cert trước/sau, canary và client telemetry | Không mất hostname được sử dụng hoặc xuất hiện cert cũ bất ngờ |
| **LOG-01** | Không rò rỉ khóa trong bằng chứng | Review logs/test artifacts | Không có private key, access token hay session secrets |
| **FAIL-01** | DNS failover không làm TLS mismatch | Mô phỏng failover trên lab có phép | Endpoint thay thế trình cert phù hợp tên public và app hoạt động |

### 19.1. Quy tắc kết luận

- **PASS:** có đủ bằng chứng đúng với tiêu chí, ví dụ server lab trả cert hợp lệ cho SAN cần thiết, client xác minh thành công, còn trường hợp đổi hostname bị từ chối với lỗi verification.
- **FAIL:** bằng chứng trái mục tiêu, ví dụ origin backup thiếu SAN public, client chấp nhận hostname không nằm trong SAN, hoặc cert từ CA không tin cậy vẫn được cho qua.
- **INCONCLUSIVE:** chưa thể kết luận, ví dụ server không mở cổng, CA test chưa được cấu hình, DNS lỗi, route khác dẫn tới endpoint không mong muốn hoặc log không có kết quả hostname verification.

Không xem kết quả **“handshake failed”** là đủ chứng minh kiểm soát SAN hoạt động. Một sự cố network/firewall bất kỳ cũng có thể làm handshake lỗi. Phải tách **kết quả mạng, kết quả chain, kết quả identity và kết quả ứng dụng**.

### 19.2. Mẫu ghi bằng chứng

~~~yaml
exercise_id: TLS-SAN-LAB-001
environment: isolated-authorized-lab
requested_hostname: api.lab.example.test
requested_scheme: https
tls_endpoint_ip: 192.0.2.20
reference_identity_type: dNSName
expected_certificate_san:
  - api.lab.example.test
expected_checks:
  ca_chain: valid
  certificate_validity: valid
  server_hostname_match: true
  handshake: completed
  http_health: success
evidence:
  - observed-certificate-san
  - observed-issuer-validity-and-serial
  - openssl-verify-result
  - curl-hostname-validation-result
  - timestamp-and-endpoint-route
result: pending-execution
~~~

Tất cả giá trị trong mẫu **chỉ là bài tập**, chưa xác nhận đã chạy trên server thật. Khi lưu bằng chứng, không thêm private key hay dữ liệu mật.

## 20. Những ngộ nhận cần tránh

| Ngộ nhận | Điều chính xác cần nhớ |
|---|---|
| “CN đúng là đủ, không cần SAN.” | Client hiện đại cần DNS-ID SAN phù hợp; RFC 9525 không dùng CN-ID thay thế. |
| “Có SAN nghĩa là chứng thư đáng tin.” | Còn phải xác minh CA/chain, hiệu lực, mục đích, thuật toán, handshake và quyền. |
| “CNAME trỏ tới CDN nên cert chỉ cần tên CDN.” | Browser xác thực **hostname URL ban đầu**, không phải tên CNAME đích. |
| “SNI là cơ chế xác thực danh tính.” | SNI là tín hiệu lựa chọn virtual host/certificate; client vẫn phải verify SAN. |
| “Wildcard bao phủ cả apex và mọi cấp con.” | Wildcard thông dụng chỉ khớp một nhãn trái nhất; apex phải liệt kê riêng. |
| “`DNS:192.0.2.20` giống `IP Address:192.0.2.20`.” | Đây là hai loại GeneralName khác nhau, không thay thế trong IP-ID validation. |
| “Đổi IP không cần kiểm tra cert.” | Mỗi endpoint/region phải phục vụ certificate phù hợp hostname. |
| “Có HTTPS phía CDN thì origin luôn an toàn.” | Backend là một TLS hop khác, cần identity validation riêng khi chính sách yêu cầu. |
| “`curl --resolve` bỏ qua xác minh certificate.” | Nó chỉ chỉ định địa chỉ kết nối; hostname trong URL vẫn được verify nếu không tắt kiểm tra. |
| “`-k` là cách khắc phục hostname mismatch.” | `-k` bỏ kiểm tra, làm mất bảo vệ danh tính; phải sửa SAN/SNI/chain. |
| “CSR ghi SAN nào thì certificate chắc chắn có SAN đó.” | CA quyết định nội dung được cấp sau kiểm tra quyền và policy. |
| “Một wildcard key nên dùng chung mọi service cho tiện.” | Làm tăng blast radius và phức tạp phân quyền/trust boundary. |
| “Có CA công khai thì mọi tên trên certificate đều bí mật.” | Nhiều cert công khai có thông tin SAN xuất hiện trong CT logs. |
| “mTLS cert client có DNS SAN thì tự được gọi mọi API.” | Identity xác thực chưa đồng nghĩa quyền truy cập; cần authorization. |
| “TLS báo OK chứng minh DNS routing, WAF và ứng dụng đúng.” | TLS chỉ là một lớp; vẫn phải kiểm tra luồng nghiệp vụ và access policies. |

## 21. Bài tập vận dụng

### Bài 1 — Hostname và SAN

Client gọi `https://api.lab.example.test` trong khi certificate có `DNS:www.lab.example.test` và `Subject CN=api.lab.example.test`. Điều gì xảy ra theo cách xác minh DNS-ID hiện đại?

*Đáp án gợi ý:* hostname mismatch vì SAN thiếu `api.lab.example.test`; không fallback về CN.

### Bài 2 — Wildcard

Một certificate chỉ có `DNS:*.shop.lab.example.test`. Hãy phân loại khả năng khớp: `web.shop.lab.example.test`, `shop.lab.example.test` và `v2.web.shop.lab.example.test`.

*Đáp án gợi ý:* chỉ tên đầu tiên khớp theo quy tắc wildcard một nhãn.

### Bài 3 — CNAME

`shop.lab.example.test` là CNAME của `edge.cdn.lab.example.test`. Edge có certificate chỉ chứa SAN cho `edge.cdn.lab.example.test`. Browser truy cập URL gốc có thể xác thực thành công không?

*Đáp án gợi ý:* không, nếu certificate thiếu `shop.lab.example.test`, mặc dù DNS alias phân giải đúng.

### Bài 4 — SNI

Hai website A và B dùng chung IP:443. Khi client nhận certificate B lúc truy cập A, cần kiểm tra những gì?

*Gợi ý:* URL host, SNI, virtual-host mapping, default certificate, CA chain và SAN của certificate thực tế. Không bỏ verification.

### Bài 5 — IP literal

Client kết nối `https://192.0.2.20/`; certificate có `DNS:api.lab.example.test` nhưng không có IP SAN. Cách nào vừa giúp kiểm thử đúng endpoint vừa giữ bảo mật hostname khi ứng dụng thực sự dùng tên DNS?

*Gợi ý:* dùng URL `https://api.lab.example.test/` và `curl --resolve api.lab.example.test:443:192.0.2.20`, giữ nguyên reference identity; không đổi URL thành IP.

### Bài 6 — Chứng thư còn hạn

Certificate có SAN đúng nhưng do CA không có trong trust store của client cấp. Client nên xử lý thế nào?

*Đáp án gợi ý:* từ chối theo policy. Với private PKI, triển khai đúng CA tin cậy qua kênh quản lý chính thức, không chấp nhận mọi CA.

### Bài 7 — mTLS

Certificate của Service A chứa một URI identity hợp lệ. Có nên lấy tên URL API làm DNS-ID để xác thực certificate client A không?

*Đáp án gợi ý:* không tự động. Server phải xác minh **đúng loại client identity** được profile mTLS quy định và kiểm tra quyền ứng dụng riêng.

### Bài 8 — CT và quyền riêng tư

Một nhóm muốn cấp public certificate với SAN chứa `db-admin.prod.lab.example.test`. Những rủi ro và lựa chọn nào cần cân nhắc?

*Gợi ý:* SAN có thể lộ trong CT; xem nhu cầu public CA, private PKI, tên public/internal và bảo vệ truy cập thực, không coi hostname là bí mật.

### Bài 9 — Failover

DNS đã trả IP backup và TCP/443 mở, nhưng browser báo hostname mismatch. Hai lớp nào đang cho kết quả trái nhau?

*Gợi ý:* DNS/routing reachability đã đổi đích, còn TLS certificate identity của endpoint backup thiếu hostname public. Kiểm tra SAN/SNI/CA của backup.

### Bài 10 — CSR

CSR có `DNS:api.lab.example.test`, nhưng certificate đã ký không có trường này. Có nên sửa trực tiếp certificate trên disk bằng cách thêm SAN không?

*Đáp án gợi ý:* không. SAN nằm trong phần được CA ký, nên cần CA cấp lại certificate đúng sau kiểm tra yêu cầu và quyền.

### Bài 11 — Khi một test âm tính chưa đủ

Một request tới server có certificate sai tên bị timeout. Có thể kết luận client đã từ chối do hostname mismatch không?

*Đáp án gợi ý:* chưa. Có thể do network/service lỗi. Cần positive control, TLS logs và thông báo verification cụ thể; nếu thiếu, ghi INCONCLUSIVE.

### Bài 12 — Nhiều cert ở nhiều vùng

Hai vùng dùng certificate khác serial number, nhưng cả hai đều được CA phù hợp cấp, đều có SAN `api.lab.example.test` và còn hạn. Có nhất thiết phải thay để dùng cùng một certificate không?

*Gợi ý:* không bắt buộc. Điều quan trọng là mỗi vùng đáp ứng identity verification, trust và lifecycle policy; tách key có thể có lợi cho phạm vi rủi ro.

## 22. Checklist thiết kế, cấp phát và vận hành SAN

- [ ] Xác định **reference hostname** từ URL/config tin cậy của từng client và từng TLS hop.
- [ ] Có inventory **DNS aliases, A/AAAA, CDN, ingress, origin, multi-region** và người sở hữu.
- [ ] SAN `dNSName` được cấp cho **đúng FQDN**; không lấy `Subject CN` thay thế.
- [ ] Truy cập bằng IP literal chỉ được cho phép khi certificate có **`iPAddress`** đúng và policy chấp thuận.
- [ ] Kiểm tra wildcard khớp **đúng một nhãn**, có explicit apex SAN khi cần và giới hạn quyền dùng wildcard key.
- [ ] Xác minh **CA chain, hostname, validity, EKU/key usage, TLS handshake** theo profile.
- [ ] Kiểm tra **SNI và certificate thực tế** trên mọi virtual host và default server.
- [ ] Với CNAME/CDN, TLS client vẫn xác minh **tên URL dự kiến**, không tự đổi sang tên đích CNAME.
- [ ] Với backend TLS/mTLS, từng hop có **danh tính, trust store và quyền truy cập** riêng.
- [ ] Không dùng `--insecure`, bỏ CA verification, sửa match rules tùy tiện hoặc hạ cấp TLS để chữa lỗi SAN.
- [ ] CSR/ACME request được **CA xác thực quyền**, SAN được so lại sau khi chứng thư thực tế được cấp.
- [ ] Private key và quyền cập nhật DNS/ACME được quản lý theo **least privilege**, có audit và rotation.
- [ ] Certificate công khai không vô tình tiết lộ SAN nội bộ nhạy cảm khi có cách phân tách PKI thích hợp.
- [ ] Có **positive/negative tests** cho hostname đúng/sai, wildcard, IP literal, CA, expiry, SNI và vùng dự phòng.
- [ ] Có cảnh báo **certificate expiry**, coverage của từng hostname, kế hoạch canary/rollback và hậu kiểm sau gia hạn.
- [ ] Không xem kết nối TLS thành công là bằng chứng đã đạt authorization, segmentation hay ứng dụng an toàn.

**Ghi nhớ:** SAN không chỉ là một danh sách tên để certificate “trông đẹp hơn”. SAN đóng vai trò **ràng buộc chứng thư với danh tính dịch vụ mà client mong đợi**, cùng certificate chain và quá trình TLS handshake giúp chống giả mạo endpoint. Muốn bảo vệ đường truyền toàn diện, phải kiểm soát **cách xác định hostname, quyền cấp chứng thư, quản lý khóa, cấu hình SNI/TLS của từng hop và bằng chứng kiểm thử từ client thật**.

### Tài liệu tham khảo

- [RFC 5280 — Internet X.509 Public Key Infrastructure Certificate and CRL Profile](https://www.rfc-editor.org/rfc/rfc5280): cấu trúc chứng thư và extension Subject Alternative Name.
- [RFC 9525 — Service Identity in TLS](https://www.rfc-editor.org/rfc/rfc9525): xác minh danh tính dịch vụ, DNS-ID, wildcard và loại bỏ CN-ID fallback.
- [RFC 8446 — The Transport Layer Security (TLS) Protocol Version 1.3](https://www.rfc-editor.org/rfc/rfc8446): handshake và certificate-based authentication trong TLS 1.3.
- [RFC 8555 — Automatic Certificate Management Environment (ACME)](https://www.rfc-editor.org/rfc/rfc8555): quy trình tự động xin cấp và gia hạn certificate.
- [RFC 5890 — Internationalized Domain Names for Applications (IDNA): Definitions and Document Framework](https://www.rfc-editor.org/rfc/rfc5890): A-label, U-label và IDN.
- [RFC 5891 — Internationalized Domain Names in Applications (IDNA): Protocol](https://www.rfc-editor.org/rfc/rfc5891): xử lý tên miền quốc tế.
- [RFC 6066 — Transport Layer Security Extensions](https://www.rfc-editor.org/rfc/rfc6066): Server Name Indication (SNI).
- [RFC 9325 — Recommendations for Secure Use of TLS and DTLS](https://www.rfc-editor.org/rfc/rfc9325): vận hành TLS và sử dụng chứng thư an toàn.
- [NIST SP 800-52 Rev. 2 — Guidelines for the Selection, Configuration, and Use of TLS Implementations](https://csrc.nist.gov/pubs/sp/800/52/r2/final): xây policy TLS.
- [OWASP Transport Layer Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Transport_Layer_Security_Cheat_Sheet.html): cấu hình và kiểm tra TLS trong ứng dụng.
- [CA/Browser Forum — TLS Baseline Requirements](https://cabforum.org/working-groups/server/baseline-requirements/): chính sách phát hành certificate công khai cho TLS.



