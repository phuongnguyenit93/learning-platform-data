# Certificate warning: hiểu và xử lý cảnh báo chứng chỉ HTTPS

## 1. Certificate warning có ý nghĩa gì?

Khi truy cập một website qua HTTPS, trình duyệt thiết lập kết nối TLS và kiểm tra chứng chỉ số mà server cung cấp. Chứng chỉ giúp xác minh server đang trình bày danh tính phù hợp với hostname người dùng truy cập, đồng thời thiết lập cơ sở tin cậy cho kênh được mã hóa.

Nếu browser không xác minh được chứng chỉ, nó có thể hiển thị trang cảnh báo như “Your connection is not private”, “Potential Security Risk Ahead” hoặc thông báo tương đương. Tên và mã lỗi cụ thể khác nhau theo browser.

**Certificate warning** nghĩa là browser không thể xác nhận đầy đủ danh tính TLS của endpoint theo chính sách tin cậy hiện tại. TLS có thể đã thương lượng được các tham số mã hóa, nhưng browser không chấp nhận danh tính peer nên thường chặn việc tiếp tục trao đổi dữ liệu ứng dụng. Một attacker đứng giữa có thể giả mạo endpoint và đọc hoặc sửa dữ liệu nếu người dùng bỏ qua cảnh báo.

Không phải mọi cảnh báo đều chứng minh website đang bị tấn công. Nguyên nhân có thể là chứng chỉ hết hạn, sai hostname, thiếu intermediate certificate, đồng hồ máy sai, cấu hình CDN/load balancer chưa đồng bộ, captive portal hoặc TLS inspection của mạng doanh nghiệp. Dù nguyên nhân là gì, không nên bỏ qua cảnh báo trên một website thật khi chưa xác định và khắc phục được vấn đề.

Trong module bảo mật trình duyệt, certificate warning gắn với TLS, certificate chain, hostname verification, HSTS, secure cookies, origin và các security headers. Bài học này giải thích cách browser đánh giá chứng chỉ, những lỗi thường gặp và quy trình chẩn đoán an toàn.

Sau bài học, bạn có thể:

- Giải thích các bước cơ bản browser dùng để xác minh TLS certificate.
- Nhận diện lỗi hostname/SAN, thời hạn, trust chain và certificate authority.
- Phân biệt lỗi cấu hình với dấu hiệu có thể liên quan đến MITM.
- Hiểu HSTS khiến browser xử lý certificate error nghiêm ngặt hơn ra sao.
- Kiểm tra certificate bằng browser, curl và OpenSSL.
- Thiết lập quy trình cấp mới, gia hạn, triển khai và giám sát chứng chỉ.

## 2. Browser xác minh chứng chỉ trong TLS như thế nào?

Khi kết nối HTTPS, server gửi certificate trong quá trình TLS handshake. Browser kiểm tra chứng chỉ và chuỗi chứng chỉ trước khi tin cậy danh tính server.

Quy trình khái quát:

```text
Người dùng mở https://shop.example.com
                 │
                 ▼
Browser bắt đầu TLS handshake
                 │
                 ▼
Server gửi certificate và intermediate chain
                 │
                 ▼
Browser kiểm tra hostname, thời hạn,
chữ ký, mục đích sử dụng và trust chain
                 │
          ┌──────┴──────┐
          │             │
          ▼             ▼
     Hợp lệ         Không hợp lệ
          │             │
          ▼             ▼
Tiếp tục TLS      Hiển thị certificate
handshake          warning / chặn kết nối
          │
          ▼
Kênh HTTPS được thiết lập
```

Các kiểm tra chính gồm:

1. **Hostname verification:** certificate có hợp lệ cho hostname trong URL hay không.
2. **Validity period:** thời điểm hiện tại có nằm trong `Not Before` và `Not After` không.
3. **Trust chain:** certificate có thể nối tới một root CA được trust store tin cậy không.
4. **Signature và thuật toán:** chữ ký, key và thuật toán có đáp ứng chính sách browser không.
5. **Extended Key Usage và constraints:** certificate có được cấp cho mục đích TLS server và tuân thủ các ràng buộc liên quan không.
6. **Revocation/status:** browser có phát hiện certificate bị thu hồi hoặc trạng thái không hợp lệ theo cơ chế mà browser sử dụng hay không.

Các browser có thể khác nhau về trust store, chính sách thuật toán, Certificate Transparency và cách xử lý truy vấn trạng thái thu hồi. Vì vậy, cùng một endpoint đôi khi có biểu hiện khác nhau trên các máy hoặc browser khác nhau.

### 2.1 Mã hóa không đồng nghĩa với xác thực server

TLS cung cấp kênh được mã hóa và xác thực endpoint khi chứng chỉ được kiểm tra thành công. Nếu browser cảnh báo certificate, người dùng không nên kết luận rằng kết nối vẫn an toàn chỉ vì biểu tượng hoặc giao thức hiển thị HTTPS.

Một kẻ tấn công có thể tạo một kết nối TLS được mã hóa tới chính họ. Điều cần xác minh là danh tính trong certificate có khớp hostname và chain có được trust hay không.

## 3. Những thành phần quan trọng trong certificate

Một server certificate thường chứa:

| Trường | Ý nghĩa |
| --- | --- |
| Subject | Danh tính được certificate mô tả; có thể chứa thông tin tổ chức/hostname tùy loại chứng chỉ. |
| Subject Alternative Name (SAN) | Danh sách DNS names hoặc IP addresses mà certificate bảo vệ. |
| Issuer | CA đã ký certificate trực tiếp. |
| Not Before / Not After | Khoảng thời gian certificate có hiệu lực. |
| Public key | Khóa công khai dùng trong cơ chế TLS tương ứng. |
| Signature algorithm | Thuật toán CA dùng để ký certificate. |
| Extended Key Usage (EKU) | Mục đích sử dụng, ví dụ TLS Web Server Authentication. |
| Basic Constraints | Cho biết certificate có phải CA certificate và các ràng buộc liên quan. |

### 3.1 SAN và hostname verification

Với website hiện đại, browser kiểm tra hostname theo Subject Alternative Name (SAN). Ví dụ certificate có SAN:

```text
DNS:shop.example.com
DNS:www.example.com
```

thì certificate có thể hợp lệ cho hai hostname đó, nếu các kiểm tra khác cũng đạt.

Nếu người dùng truy cập `api.example.com` nhưng certificate chỉ có `shop.example.com`, browser sẽ báo lỗi hostname mismatch. Việc hai hostname cùng thuộc một domain gốc không làm certificate tự động hợp lệ.

Không nên dựa vào Common Name (CN) như cơ chế thay thế SAN trong triển khai hiện đại. Certificate cho HTTPS cần có SAN phù hợp với hostname thực tế.

### 3.2 Wildcard certificate có phạm vi giới hạn

Certificate có SAN `*.example.com` thường bao phủ một nhãn con như `shop.example.com` hoặc `api.example.com`. Nó không bao phủ `example.com` và cũng không bao phủ nhiều cấp như `a.shop.example.com`.

Nếu hệ thống phục vụ cả domain gốc lẫn subdomain, cần liệt kê các DNS names phù hợp trong SAN hoặc cấp certificate riêng.

### 3.3 Scheme, host và port

Certificate xác minh danh tính hostname, không phải một URL path cụ thể. `https://shop.example.com/orders` và `https://shop.example.com/profile` dùng cùng hostname; certificate không giới hạn quyền truy cập theo path.

Port cũng không được liệt kê như một phần của DNS SAN. Browser kiểm tra hostname trong URL và các quy tắc TLS; việc ứng dụng chạy trên port nào không biến một certificate sai hostname thành hợp lệ.

## 4. Certificate chain và CA trust

Browser thường không tin certificate server chỉ vì server tự gửi nó. Browser cần xây dựng được một chuỗi chữ ký hợp lệ tới một root CA có trong trust store mà browser/OS sử dụng.

Một chuỗi phổ biến:

```text
Root CA (đã được trust store tin cậy)
          │ ký
          ▼
Intermediate CA
          │ ký
          ▼
Leaf certificate (shop.example.com)
          │
          ▼
TLS server
```

Server thường cần gửi leaf certificate cùng các intermediate certificates cần thiết. Root certificate thường đã có trong trust store của client và không cần server gửi lại.

### 4.1 Lỗi thiếu intermediate certificate

Nếu server chỉ gửi leaf certificate mà bỏ intermediate, một số client có thể không xây dựng được chain hoàn chỉnh. Một số browser hoặc hệ điều hành có thể tìm intermediate từ cache hoặc cơ chế tải bổ sung, khiến lỗi chỉ xuất hiện trên một số thiết bị.

Không dựa vào khả năng tự tải intermediate của client. Cấu hình server/CDN nên gửi đầy đủ intermediate chain theo yêu cầu của CA.

### 4.2 Self-signed certificate

Certificate tự ký không được trust store công khai tin cậy theo mặc định. Nó có thể phù hợp cho lab hoặc mạng nội bộ khi một CA nội bộ được cài đặt và quản lý có chủ đích, nhưng certificate tự ký tùy tiện sẽ tạo cảnh báo cho người dùng.

Trong production public website, dùng certificate từ CA được browser tin cậy. Với hệ thống nội bộ, dùng private PKI có quy trình phân phối root CA an toàn và quản lý vòng đời chứng chỉ.

### 4.3 Trust store khác nhau giữa thiết bị

Browser có thể dùng trust store riêng hoặc dựa vào trust store của hệ điều hành. Máy cũ có thể thiếu root CA mới; thiết bị doanh nghiệp có thể cài private root CA; container hoặc runtime server có thể có CA bundle khác máy người dùng.

Vì vậy, cần kiểm tra lỗi trên nhiều môi trường và xác định trust store thực tế của client. Không khắc phục bằng cách yêu cầu mọi người cài một root CA không rõ nguồn gốc.

## 5. Các loại certificate warning thường gặp

Thông báo cụ thể tùy browser, nhưng có thể nhóm theo nguyên nhân:

| Nhóm lỗi | Ví dụ mã/thông báo | Nguyên nhân thường gặp |
| --- | --- | --- |
| Hostname mismatch | `NET::ERR_CERT_COMMON_NAME_INVALID` hoặc tên tương đương | SAN không chứa hostname người dùng truy cập; CDN/SNI chọn nhầm certificate. |
| Certificate hết hạn hoặc chưa có hiệu lực | `NET::ERR_CERT_DATE_INVALID` | Certificate đã quá `Not After`, chưa tới `Not Before` hoặc đồng hồ client sai. |
| CA không được tin cậy | `NET::ERR_CERT_AUTHORITY_INVALID` | Self-signed, thiếu chain, root CA không có trong trust store hoặc TLS inspection không được tin cậy. |
| Certificate bị thu hồi | Revoked certificate error | CA đã thu hồi certificate, ví dụ do private key bị lộ hoặc cấp sai. |
| Chain không hợp lệ | Authority/issuer/chain error | Intermediate thiếu, chữ ký sai hoặc chain không thể xây dựng tới root tin cậy. |
| Thuật toán hoặc key không còn được chấp nhận | Weak signature/key hoặc policy error | Certificate dùng thuật toán, key size hoặc tham số không đáp ứng chính sách hiện tại. |
| Lỗi chính sách bổ sung | Certificate Transparency hoặc constraint error | Certificate không đáp ứng chính sách browser/CA tương ứng. |

Các mã ở trên là ví dụ, không phải danh sách đầy đủ hoặc quy ước chung cho mọi browser. Hãy đọc cả mã lỗi và chi tiết certificate trong browser.

### 5.1 Hostname mismatch

Ví dụ:

- Người dùng truy cập `https://store.example.com`.
- Server gửi certificate chỉ có SAN `DNS:api.example.com`.
- Browser từ chối vì danh tính không khớp hostname.

Nguyên nhân thường nằm ở:

- Cấu hình virtual host/SNI chọn nhầm certificate.
- CDN hoặc load balancer chưa gắn certificate cho hostname mới.
- DNS trỏ tới server cũ.
- Certificate được cấp nhưng thiếu SAN cho domain gốc hoặc subdomain.
- Redirect dẫn tới hostname chưa được certificate bảo vệ.

Khắc phục bằng cách cấp certificate có SAN phù hợp và gắn đúng certificate vào endpoint phục vụ hostname đó. Không yêu cầu người dùng truy cập hostname khác chỉ để tránh cảnh báo nếu URL chính thức của sản phẩm vẫn sai.

### 5.2 Certificate expired hoặc not yet valid

Certificate có thời gian hiệu lực. Nếu server quên gia hạn, browser sẽ từ chối certificate đã hết hạn. Nếu certificate có `Not Before` nằm trong tương lai, có thể CA/server đã cấp hoặc triển khai nhầm thời điểm; cũng cần kiểm tra đồng hồ của máy client.

Không khắc phục bằng cách chỉnh lùi ngày hệ thống để bỏ qua cảnh báo. Hãy kiểm tra giờ hệ thống bằng nguồn thời gian đáng tin cậy và cấp/triển khai certificate hợp lệ.

### 5.3 Authority invalid hoặc self-signed

Browser có thể không xây dựng được trust chain vì:

- Server gửi certificate tự ký.
- Server thiếu intermediate certificate.
- Root CA chưa được trust store tin cậy.
- Thiết bị đang dùng CA bundle cũ.
- Proxy/TLS inspection thay certificate bằng CA nội bộ chưa được cài đặt hợp lệ.

Hãy xác định issuer và chain trong certificate viewer. Không cài root CA từ popup, email hoặc website không được xác minh.

### 5.4 Revocation và trạng thái certificate

CA có thể thu hồi certificate trước ngày hết hạn, ví dụ private key bị lộ hoặc certificate được cấp sai. CRL và OCSP là những cơ chế phổ biến để phân phối thông tin thu hồi; một số server dùng OCSP stapling để gửi trạng thái đã ký trong quá trình TLS.

Browser khác nhau về cách kiểm tra revocation, cache và phản ứng khi dịch vụ kiểm tra không truy cập được. Không phải mọi browser đều hard-fail trong mọi tình huống responder không phản hồi. Khi có cảnh báo revoked cụ thể, cần coi đây là sự cố nghiêm trọng và thay certificate theo quy trình CA.

## 6. Đồng hồ hệ thống và các lỗi môi trường

Một certificate hợp lệ vẫn có thể bị browser từ chối nếu thời gian trên thiết bị sai đáng kể. Kiểm tra:

- Ngày, giờ và múi giờ của hệ điều hành.
- Đồng bộ thời gian tự động qua nguồn NTP đáng tin.
- Máy ảo, container hoặc thiết bị nhúng có giữ đúng thời gian sau reboot không.
- Đồng hồ server và hệ thống cấp phát certificate có đồng bộ không.

Nếu nhiều website HTTPS độc lập cùng hiển thị lỗi date invalid trên một máy, hãy kiểm tra đồng hồ và trust store của máy trước. Nếu chỉ một hostname bị lỗi, ưu tiên kiểm tra certificate được endpoint đó phục vụ.

### 6.1 Captive portal của Wi-Fi công cộng

Một số mạng Wi-Fi yêu cầu người dùng đăng nhập qua captive portal. Trước khi xác thực, mạng có thể chặn hoặc chuyển hướng request. Khi người dùng mở một website HTTPS, browser có thể gặp certificate mismatch vì portal đang trả certificate của chính nó thay cho certificate của website.

Không nhập mật khẩu hoặc dữ liệu thanh toán qua trang cảnh báo certificate. Nếu nghi captive portal:

1. Mở trang kiểm tra kết nối HTTP không nhạy cảm do hệ điều hành/browser sử dụng, hoặc trang hướng dẫn chính thức của nhà cung cấp mạng.
2. Hoàn tất đăng nhập Wi-Fi qua portal hợp lệ.
3. Đóng tab cảnh báo và truy cập lại website HTTPS bằng URL chính thức.
4. Nếu cảnh báo vẫn còn, dừng truy cập và kiểm tra mạng/thiết bị.

### 6.2 TLS inspection trong mạng doanh nghiệp

Một số tổ chức dùng proxy để kiểm tra TLS. Proxy tạo certificate mới cho website và ký bằng private CA của tổ chức. Nếu thiết bị được quản lý và root CA được cài đặt qua kênh IT chính thức, browser có thể tin chain đó.

Nếu certificate issuer bất ngờ đổi sang một CA không rõ nguồn gốc, đặc biệt trên mạng công cộng hoặc thiết bị cá nhân, không tự cài CA đó. Hãy xác minh với bộ phận IT qua kênh liên lạc độc lập.

## 7. HSTS bảo vệ HTTPS như thế nào?

## 7. HSTS bảo vệ HTTPS như thế nào?

**HTTP Strict Transport Security (HSTS)** là response header yêu cầu browser chỉ truy cập hostname qua HTTPS trong một khoảng thời gian. Ví dụ:

```http
Strict-Transport-Security: max-age=31536000; includeSubDomains
```

Khi browser nhận header hợp lệ qua một kết nối HTTPS không có lỗi certificate, nó ghi nhớ chính sách và tự nâng cấp các lần truy cập HTTP sau thành HTTPS trong thời gian `max-age`.

HSTS giúp giảm nguy cơ:

- Người dùng nhập hoặc mở URL `http://` và bị downgrade.
- Attacker trên mạng chặn lần chuyển hướng HTTP sang HTTPS.
- Người dùng bị dẫn tới phiên bản HTTP không được mã hóa.
- Người dùng bỏ qua certificate error trên hostname đang chịu HSTS.

### 7.1 HSTS làm certificate error nghiêm ngặt hơn

Khi hostname đang có HSTS policy (được ghi nhớ hoặc nằm trong preload list), browser phải xử lý lỗi certificate như lỗi không thể bỏ qua bằng cách thông thường. Người dùng không được cung cấp lựa chọn tiếp tục truy cập không an toàn như một số trang lỗi certificate thông thường.

Đây là chủ đích bảo vệ: nếu người dùng có thể click-through certificate error, attacker có thể lợi dụng lỗi cấu hình hoặc MITM để đánh lừa họ tiếp tục.

Vì vậy, bật HSTS làm tăng yêu cầu vận hành TLS. Certificate hết hạn, sai hostname hoặc chain lỗi có thể khiến toàn bộ người dùng bị khóa khỏi hostname cho tới khi server sửa xong.

### 7.2 HSTS không cấp certificate và không sửa TLS

HSTS chỉ yêu cầu browser dùng HTTPS và thực thi chính sách nghiêm ngặt. Nó không:

- Cấp hoặc gia hạn certificate.
- Làm certificate sai hostname trở nên hợp lệ.
- Thay thế certificate chain đầy đủ.
- Sửa cấu hình TLS protocol/cipher.
- Bảo vệ hostname chưa nằm trong policy nếu người dùng truy cập lần đầu qua HTTP và hostname chưa được preload.

HSTS cần đi cùng certificate hợp lệ và quy trình gia hạn đáng tin cậy.

## 8. Các directive của Strict-Transport-Security

Ví dụ:

```http
Strict-Transport-Security: max-age=31536000; includeSubDomains; preload
```

| Directive | Ý nghĩa |
| --- | --- |
| `max-age` | Thời gian tính bằng giây mà browser ghi nhớ HSTS policy. |
| `includeSubDomains` | Áp dụng chính sách cho các subdomain của hostname đã phát header. |
| `preload` | Token thể hiện ý định/điều kiện tham gia preload program; bản thân token không tự thêm domain vào danh sách preload của browser. |

### 8.1 max-age

`max-age=31536000` tương đương khoảng một năm. Nếu browser nhận policy mới từ response HTTPS hợp lệ, thời hạn được cập nhật theo giá trị mới.

`max-age=0` được dùng để yêu cầu browser xóa HSTS policy đã lưu cho hostname đó. Header này cũng phải được gửi qua HTTPS hợp lệ; khi certificate đã hỏng và browser không cho kết nối, không thể dựa vào một response HTTP thường để xóa policy.

### 8.2 includeSubDomains

Khi dùng `includeSubDomains`, tất cả subdomain thuộc phạm vi hostname đều phải phục vụ HTTPS hợp lệ. Điều này có thể ảnh hưởng:

- Subdomain cũ chưa có certificate.
- Dịch vụ nội bộ chỉ chạy HTTP.
- Máy chủ mail/webmail hoặc control panel.
- Hệ thống staging, test và thiết bị legacy.
- Dịch vụ do bên thứ ba vận hành.

Chỉ bật `includeSubDomains` sau khi đã kiểm kê và xác nhận mọi subdomain trong phạm vi có thể hỗ trợ HTTPS ổn định.

### 8.3 Preload

Một số browser phân phối sẵn danh sách hostname HSTS preload. Hostname trong danh sách được browser xử lý như HSTS ngay cả trước khi người dùng truy cập lần đầu.

Token `preload` trong header không tự động đưa website vào preload list. Chủ website phải đáp ứng tiêu chí của chương trình preload, gửi đăng ký theo quy trình của chương trình và duy trì HTTPS trên toàn bộ phạm vi đã khai báo.

Gỡ một hostname khỏi preload list không có hiệu lực tức thì trên mọi phiên bản browser. Hãy coi quyết định preload là cam kết vận hành dài hạn, không phải một toggle thử nghiệm.

### 8.4 HSTS chỉ được tin khi nhận qua HTTPS

Browser bỏ qua `Strict-Transport-Security` nếu header được gửi qua kết nối HTTP không an toàn. Điều này ngăn attacker trên mạng chèn một policy giả hoặc yêu cầu browser xóa policy qua HTTP.

## 9. Triển khai HSTS an toàn

Không nên bật `includeSubDomains` và preload ngay khi chưa hiểu toàn bộ hostname. Có thể triển khai theo giai đoạn:

1. Bảo đảm hostname chính có certificate hợp lệ và tự động gia hạn.
2. Chuyển toàn bộ traffic sang HTTPS và kiểm tra redirect HTTP → HTTPS.
3. Bắt đầu với `max-age` ngắn trong giai đoạn thử nghiệm, ví dụ vài phút hoặc vài giờ.
4. Theo dõi lỗi certificate, subdomain và tích hợp bên thứ ba.
5. Tăng `max-age` khi đã ổn định.
6. Chỉ thêm `includeSubDomains` sau khi toàn bộ subdomain đã sẵn sàng.
7. Chỉ cân nhắc preload khi đã đáp ứng tiêu chí và chấp nhận cam kết dài hạn.

Ví dụ giai đoạn đầu:

```http
Strict-Transport-Security: max-age=300
```

Ví dụ sau khi hệ thống đã ổn định:

```http
Strict-Transport-Security: max-age=31536000; includeSubDomains
```

Giá trị thử nghiệm ngắn chỉ nên dùng trong giai đoạn rollout có kiểm soát. Khi đã đưa policy dài hạn tới browser, việc rollback có thể cần thời gian vì client giữ policy đã nhận.

## 10. Người dùng nên làm gì khi thấy certificate warning?

Với một website thật, cách xử lý an toàn là dừng thao tác nhạy cảm và xác định nguyên nhân trước khi tiếp tục.

### 10.1 Nếu bạn là người dùng

1. Không nhập mật khẩu, mã OTP, thông tin thanh toán hoặc dữ liệu cá nhân trên trang cảnh báo.
2. Kiểm tra hostname trên thanh địa chỉ có đúng website dự định truy cập không.
3. Kiểm tra ngày giờ của thiết bị và trạng thái kết nối mạng.
4. Nếu đang dùng Wi-Fi công cộng, xác minh captive portal qua hướng dẫn chính thức.
5. Thử lại bằng mạng đáng tin cậy khác nếu có thể.
6. Liên hệ chủ website hoặc bộ phận IT qua kênh đã biết trước, không dùng thông tin liên hệ xuất hiện trong trang cảnh báo.

Không cài certificate, root CA hoặc extension do trang cảnh báo đề nghị. Một website hợp lệ sẽ cần sửa cấu hình server/CA nếu certificate của nó bị lỗi.

### 10.2 Nếu bạn vận hành website

1. Ghi lại hostname, thời điểm, browser, hệ điều hành và mã lỗi.
2. Kiểm tra certificate mà endpoint thực tế đang phục vụ, bao gồm SAN, thời hạn, issuer và chain.
3. Kiểm tra SNI, virtual host, CDN, load balancer và mọi node trong cụm.
4. Kiểm tra DNS và redirect chain.
5. Xác minh lỗi có xuất hiện ở nhiều mạng và thiết bị hay chỉ một môi trường.
6. Gia hạn/cấp lại certificate hoặc sửa chain/configuration rồi kiểm tra lại.
7. Theo dõi lỗi sau khi triển khai; nếu có khả năng private key bị lộ, thực hiện quy trình thu hồi và thay key/certificate.

## 11. Xem certificate trong browser

Browser cung cấp giao diện xem certificate và thông tin kết nối. Tên menu thay đổi theo browser/phiên bản, nhưng quy trình chung là:

1. Mở website qua HTTPS.
2. Chọn biểu tượng điều khiển thông tin site ở cạnh thanh địa chỉ.
3. Mở phần Connection/Security hoặc Certificate details.
4. Xem Subject/SAN, Issuer, Validity và certification path nếu browser cung cấp.
5. So sánh SAN với hostname đang mở.
6. Kiểm tra ngày hết hạn, intermediate và root CA.

Khi đang ở trang interstitial cảnh báo, browser có thể cung cấp nút xem chi tiết certificate hoặc mã lỗi. Không cần chọn tùy chọn tiếp tục truy cập để xem thông tin.

### 11.1 Câu hỏi khi đọc certificate

- Hostname trong URL có xuất hiện trong SAN không?
- Certificate đã hết hạn hoặc chưa tới ngày hiệu lực chưa?
- Issuer có phải CA dự kiến của tổ chức không?
- Chain có đủ intermediate certificates không?
- Certificate có mục đích TLS server phù hợp không?
- Certificate có bất ngờ được ký bởi một private CA lạ không?
- Nhiều hostname sau cùng một CDN có đang nhận nhầm certificate không?

Nếu browser chỉ hiển thị một phần chain, dùng công cụ kiểm tra TLS ở phía client hoặc hệ thống giám sát để xem chain server gửi.

## 12. Kiểm tra bằng curl và OpenSSL

Các công cụ dòng lệnh giúp kiểm tra endpoint độc lập với giao diện browser. Chúng không thay thế kiểm thử trên browser vì trust store, chính sách và hành vi có thể khác.

### 12.1 curl

Kiểm tra kết nối và certificate:

```bash
curl -Iv https://shop.example.com/
```

`-I` yêu cầu response headers, `-v` hiển thị thông tin kết nối chi tiết. Nếu certificate không hợp lệ, curl thường dừng với lỗi xác minh TLS thay vì tải nội dung.

Không dùng `-k` hoặc `--insecure` để tuyên bố endpoint an toàn. Những tùy chọn này bỏ qua xác minh certificate và chỉ hữu ích cho chẩn đoán có kiểm soát khi bạn hiểu rõ rủi ro.

### 12.2 OpenSSL s_client

Kiểm tra certificate chain và hostname:

```bash
openssl s_client \
  -connect shop.example.com:443 \
  -servername shop.example.com \
  -showcerts \
  -verify_return_error \
  -verify_hostname shop.example.com
```

Các tùy chọn:

- `-connect`: địa chỉ và port cần kết nối.
- `-servername`: gửi SNI để server chọn certificate cho đúng hostname.
- `-showcerts`: hiển thị các certificate server gửi.
- `-verify_return_error`: yêu cầu báo lỗi xác minh thay vì chỉ tiếp tục hiển thị thông tin.
- `-verify_hostname`: kiểm tra hostname theo certificate.

Nếu bỏ `-servername`, server dùng virtual hosting có thể gửi certificate mặc định cho hostname khác và tạo kết quả chẩn đoán sai.

### 12.3 Xem ngày và SAN của certificate

Có thể lưu leaf certificate từ output OpenSSL rồi kiểm tra:

```bash
openssl x509 -in server-cert.pem -noout -subject -issuer -dates -ext subjectAltName
```

Kết quả giúp xác nhận Subject, Issuer, thời hạn và SAN. Để đánh giá chain đầy đủ, cần kiểm tra cả intermediate certificates và trust store mà client sử dụng.

### 12.4 Khác biệt trust store

curl/OpenSSL có thể dùng CA bundle riêng. Browser có thể dùng trust store của browser hoặc hệ điều hành. Vì vậy:

- curl thành công không đảm bảo mọi browser đều tin certificate.
- curl thất bại không tự chứng minh browser cũng sẽ thất bại.
- Kết quả phải được đối chiếu với browser, thiết bị và mạng thực tế.

## 13. Cấu hình HSTS tại server

HSTS được gửi bằng HTTP response header qua HTTPS. Nên đặt ở tầng có thể áp dụng nhất quán cho các response của hostname.

### 13.1 Nginx

Ví dụ trên virtual host HTTPS:

```nginx
server {
    listen 443 ssl;
    server_name shop.example.com;

    add_header Strict-Transport-Security "max-age=31536000" always;

    # TLS certificate and application configuration
}
```

Chỉ thêm `includeSubDomains` sau khi đã kiểm kê tất cả subdomain:

```nginx
add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
```

Kiểm tra quy tắc kế thừa `add_header` ở các block `http`, `server` và `location`. Nếu location có `add_header` riêng, header từ cấp trên có thể không được kế thừa như dự kiến.

### 13.2 Apache HTTP Server

Ví dụ:

```apache
Header always set Strict-Transport-Security "max-age=31536000"
```

Đảm bảo module headers được bật và directive nằm trong virtual host HTTPS phù hợp. Tránh phát HSTS cho hostname chưa sẵn sàng HTTPS hoặc áp dụng nhầm policy của domain cha cho host không thuộc phạm vi.

### 13.3 Ứng dụng Java

Có thể đặt header trong security filter dùng chung:

```java
response.setHeader(
    "Strict-Transport-Security",
    "max-age=31536000"
);
```

Filter chỉ nên phát header cho request HTTPS đã được proxy tin cậy xác định đúng. Nếu TLS kết thúc ở reverse proxy, ứng dụng phải dùng cấu hình proxy đáng tin cậy để nhận biết scheme bên ngoài; không tin một header forwarding tùy ý do client tự gửi.

### 13.4 HSTS và reverse proxy

Nếu TLS kết thúc ở CDN/load balancer, hãy quyết định rõ tầng nào là nguồn phát HSTS. Kiểm tra response cuối mà browser nhận, không chỉ response giữa proxy và backend. Tránh phát nhiều giá trị HSTS mâu thuẫn hoặc để một route lỗi bỏ sót header.

## 14. Quản lý vòng đời certificate

Certificate warning thường là kết quả của lỗi vận hành có thể phòng tránh. Hãy quản lý chứng chỉ như một tài sản có thời hạn:

- Dùng quy trình cấp phát tự động như ACME khi phù hợp.
- Tự động gia hạn trước ngày hết hạn với khoảng đệm đủ lớn.
- Giám sát expiry của mọi hostname và endpoint, bao gồm CDN, load balancer và origin.
- Kiểm tra gia hạn thành công đã được deploy tới mọi node, không chỉ CA đã cấp certificate mới.
- Theo dõi SAN, issuer, chain và cấu hình SNI sau mỗi lần thay certificate.
- Bảo vệ private key, giới hạn quyền truy cập và thay key khi có nghi ngờ lộ lọt.
- Lưu inventory hostname, owner, CA, ngày hết hạn và nơi triển khai.
- Kiểm thử cảnh báo trên staging trước khi thay certificate production.

### 14.1 Gia hạn tự động vẫn cần xác minh triển khai

Một job ACME có thể cấp certificate mới thành công nhưng web server vẫn tiếp tục phục vụ certificate cũ nếu:

- Hook reload server không chạy.
- File path mà web server đọc không được cập nhật.
- Một node trong cụm không nhận certificate mới.
- CDN hoặc load balancer còn giữ certificate cũ.
- SNI map vẫn trỏ tới certificate cũ.

Sau gia hạn, kiểm tra certificate từ bên ngoài qua hostname production và xác nhận mọi edge/node phục vụ cùng một certificate hợp lệ.

### 14.2 Cảnh báo expiry

Thiết lập giám sát theo số ngày còn lại trước expiry, đồng thời cảnh báo khi:

- Certificate mới chưa được triển khai.
- SAN không còn khớp hostname.
- Chain thay đổi hoặc thiếu intermediate.
- Endpoint trả certificate khác với inventory.
- TLS handshake hoặc xác minh chain bắt đầu thất bại.

Đừng chỉ giám sát ngày hết hạn. Một certificate còn hạn vẫn có thể sai hostname, sai chain hoặc bị thu hồi.

## 15. Chẩn đoán theo triệu chứng

| Triệu chứng | Kiểm tra đầu tiên | Hướng khắc phục |
| --- | --- | --- |
| Chỉ một hostname báo mismatch | SAN, SNI, virtual host và redirect | Cấp/gắn đúng certificate cho hostname. |
| Tất cả hostname cùng lỗi date invalid trên một máy | Clock và timezone của client | Đồng bộ thời gian; sau đó kiểm tra endpoint. |
| Chỉ một số thiết bị báo authority invalid | Trust store, intermediate chain và OS/browser version | Cài chain đúng ở server; cập nhật trust store qua kênh quản trị hợp lệ. |
| Lỗi sau khi thay CDN/load balancer | Certificate mapping, SNI và propagation | Đồng bộ certificate tới mọi edge/node. |
| Lỗi chỉ xuất hiện trong Wi-Fi công cộng | Captive portal hoặc TLS interception | Xác thực portal hợp lệ hoặc đổi sang mạng đáng tin. |
| Lỗi chỉ xuất hiện trên mạng doanh nghiệp | TLS inspection/private CA | Xác minh cấu hình proxy với IT. |
| Certificate còn hạn nhưng browser báo revoked | Trạng thái OCSP/CRL hoặc certificate thực tế được phục vụ | Xác minh CA; thay certificate nếu đã bị thu hồi. |
| HSTS khiến không thể tiếp tục qua warning | HSTS cache/preload và lỗi TLS thật | Sửa certificate/server; không tìm cách click-through. |

## 16. Không bỏ qua certificate warning

Các lựa chọn “Proceed”, “Accept risk” hoặc cờ bỏ xác minh TLS làm mất cơ chế xác thực server. Khi đó, người dùng có thể gửi thông tin nhạy cảm tới endpoint do attacker kiểm soát.

Không khuyến khích:

- Click tiếp tục trên website production chỉ vì cần truy cập gấp.
- Dùng `curl -k` hoặc `--insecure` trong script production.
- Tắt certificate verification trong HTTP client hoặc browser automation.
- Cài root CA không rõ nguồn gốc.
- Tắt HSTS hoặc xóa browser state để vượt qua cảnh báo.
- Chỉnh ngày giờ hệ thống để certificate có vẻ còn hiệu lực.

Nếu là lab nội bộ, tạo CA phát triển riêng, bảo vệ private key và cài root certificate qua trust mechanism có kiểm soát. Dùng hostname lab phù hợp SAN và chỉ tin CA đó trên thiết bị thử nghiệm. Không dùng ngoại lệ của browser như cấu hình lâu dài.

## 17. Những lỗi vận hành thường gặp

| Lỗi | Hậu quả | Cách phòng tránh |
| --- | --- | --- |
| Chỉ kiểm tra ngày hết hạn | Certificate còn hạn nhưng sai SAN hoặc chain. | Giám sát cả hostname, chain, issuer và expiry. |
| Chỉ triển khai certificate lên một node | Một số request đi tới node vẫn phục vụ certificate cũ. | Kiểm tra mọi node/edge sau deploy. |
| Quên SNI mapping | Server gửi certificate mặc định của hostname khác. | Test từng hostname với SNI. |
| Thiếu intermediate | Một số client không xây dựng được trust chain. | Cài full chain theo hướng dẫn CA. |
| Dùng CN nhưng thiếu SAN | Browser hiện đại không xác minh hostname theo cách mong đợi. | Cấp certificate có SAN chính xác. |
| Bật includeSubDomains quá sớm | Subdomain HTTP/legacy bị buộc dùng HTTPS và có thể ngừng hoạt động. | Inventory subdomain và rollout theo giai đoạn. |
| Thêm preload mà chưa sẵn sàng | Browser có thể ép HTTPS ngay lần truy cập đầu và khó rollback nhanh. | Kiểm tra toàn bộ host và cam kết vận hành trước khi đăng ký. |
| Chỉ test bằng curl | Khác biệt trust store/browser policy không được phát hiện. | Test browser trên nhiều OS và mạng. |
| Bỏ qua warning trong automation | Test có thể che giấu lỗi TLS production. | Giữ certificate verification bật trong CI/production. |

## 18. Checklist TLS và certificate warning

- [ ] Mọi hostname production có certificate SAN phù hợp.
- [ ] Certificate còn hiệu lực và đồng hồ client/server được đồng bộ.
- [ ] Server gửi leaf và intermediate chain cần thiết.
- [ ] Certificate được ký bởi CA được client mục tiêu tin cậy.
- [ ] SNI/virtual host/CDN/load balancer phục vụ đúng certificate.
- [ ] Có quy trình gia hạn tự động và cảnh báo expiry.
- [ ] Sau renew, certificate mới đã được triển khai tới mọi node/edge.
- [ ] Có giám sát SAN, issuer, chain và trạng thái TLS.
- [ ] HSTS chỉ được phát qua HTTPS hợp lệ.
- [ ] max-age được tăng theo giai đoạn có kiểm soát.
- [ ] includeSubDomains chỉ bật khi mọi subdomain đã sẵn sàng.
- [ ] Preload chỉ được cân nhắc sau khi đáp ứng tiêu chí và hiểu thời gian rollback.
- [ ] Popup, proxy, captive portal và TLS inspection đã được xem xét khi debug.
- [ ] Không có script production bỏ qua certificate verification.
- [ ] Đã kiểm thử bằng browser, curl và OpenSSL.

## 19. Câu hỏi tự kiểm tra

1. Certificate warning cho biết điều gì về danh tính server?
2. Vì sao một kết nối TLS được mã hóa vẫn có thể không an toàn nếu certificate không hợp lệ?
3. SAN có vai trò gì trong hostname verification?
4. Wildcard `*.example.com` bao phủ những hostname nào và không bao phủ hostname nào?
5. Vì sao server cần gửi intermediate certificates?
6. Đồng hồ client sai có thể tạo certificate warning như thế nào?
7. TLS inspection của doanh nghiệp khác MITM trái phép ở điểm nào trong mô hình tin cậy?
8. HSTS làm browser xử lý certificate error ra sao?
9. Vì sao token `preload` không tự thêm domain vào browser preload list?
10. Vì sao cần kiểm tra certificate sau khi ACME renew và deploy?
11. `curl -k` làm mất kiểm tra nào?
12. Cần làm gì khi browser báo certificate đã bị thu hồi?

## 20. Tổng kết

Certificate warning xuất hiện khi browser không xác minh được danh tính TLS của endpoint theo chính sách tin cậy hiện tại. Nguyên nhân phổ biến gồm SAN/hostname mismatch, certificate hết hạn hoặc chưa có hiệu lực, chain thiếu, CA không được tin cậy, revocation, đồng hồ sai hoặc TLS inspection. Hãy kiểm tra certificate, issuer, SAN, validity và chain trên endpoint thực tế; đối chiếu kết quả giữa browser, curl và OpenSSL.

HSTS yêu cầu browser dùng HTTPS và khiến certificate error trên hostname đã có policy trở thành lỗi không thể bỏ qua bằng cách thông thường. `max-age`, `includeSubDomains` và preload cần được triển khai theo giai đoạn vì có thể ảnh hưởng toàn bộ subdomain và làm rollback khó hơn. Quản lý certificate cần có inventory, tự động gia hạn, triển khai tới mọi node, giám sát expiry/chain và kiểm tra sau deploy. Khi gặp cảnh báo, dừng thao tác nhạy cảm và sửa nguyên nhân TLS; không tắt xác minh certificate hoặc hướng dẫn người dùng bỏ qua warning.
