# Giới hạn kích thước và độ phức tạp của payload

> **Module:** `SECURITY_TOKEN_SECURITY_JWT` — **Security - JSON Web Token (JWT)**. **Chương:** Thiết kế claims. Bài viết áp dụng cho hệ thống JWT nói chung, không phụ thuộc ngôn ngữ lập trình, nền tảng hoặc framework.

## 1. Vì sao phải giới hạn payload JWT?

Payload JWT thường chứa Claims Set dưới dạng JSON. Khi issuer thêm nhiều claim, chuỗi dài, mảng lớn hoặc object lồng sâu, token tăng kích thước và việc tạo, truyền, parse, xác minh, cache và ghi nhận token đều tốn thêm tài nguyên.

Một payload quá lớn hoặc quá phức tạp có thể gây ra:

- request vượt giới hạn header của client, proxy, gateway hoặc resource server;
- cookie vượt giới hạn mà trình duyệt hoặc hạ tầng chấp nhận;
- tăng băng thông và độ trễ trên mọi request mang bearer token;
- tăng bộ nhớ tạm, CPU giải mã Base64URL, parse JSON, xác minh chữ ký hoặc giải mã JWE;
- tăng kích thước cache key, log, message và dữ liệu telemetry;
- parser bị khai thác bằng object lồng sâu, mảng rất lớn, chuỗi khổng lồ hoặc số lượng claim bất thường;
- token bị từ chối không nhất quán giữa các thành phần vì mỗi tầng có giới hạn khác nhau.

**Giới hạn payload là một phần của thiết kế bảo mật và vận hành**, không chỉ là tối ưu hiệu năng. JWT thường được gửi lặp lại trong nhiều request; vài kilobyte thừa trong một token có thể nhân lên thành lượng dữ liệu đáng kể khi API có lưu lượng cao.

Mục tiêu là phát hành token đủ thông tin để bên nhận thực hiện đúng quyết định trong phạm vi cần thiết, đồng thời đặt giới hạn rõ ràng cho kích thước và độ phức tạp của dữ liệu.

## 2. Phân biệt payload size và compact token size

Hai đại lượng này có liên quan nhưng không giống nhau:

- **Payload size:** số byte của JSON Claims Set sau khi serialize thành UTF-8.
- **Compact token size:** tổng số ký tự của chuỗi JWT sau Base64URL encoding và ghép các segment bằng dấu chấm.

Với JWS Compact Serialization:

~~~text
token = BASE64URL(protected_header)
      + "."
      + BASE64URL(payload)
      + "."
      + BASE64URL(signature)
~~~

Base64URL làm dữ liệu lớn hơn. Với dữ liệu có kích thước `n` byte, kích thước Base64 xấp xỉ:

\[
L_{b64} \approx 4 \times \lceil n/3 \rceil
\]

JOSE bỏ padding cuối, nên chiều dài thực có thể ngắn hơn một ít. Có thể ước lượng nhanh rằng Base64URL làm tăng khoảng một phần ba kích thước byte đầu vào.

Vì vậy, payload JSON 3 KB không có nghĩa compact JWT chỉ dài 3 KB. Token còn có protected header, chữ ký, hai dấu chấm và chi phí encoding.

Với JWE Compact Serialization, token có năm segment: protected header, encrypted key, IV, ciphertext và authentication tag. Ciphertext thường có kích thước gần với plaintext đối với các chế độ mã hóa hiện đại, nhưng IV, tag, encrypted key, header và Base64URL làm token tăng thêm. Không nên giả định JWE luôn nhỏ hơn JWS.

### 2.1. Đo đúng ở cấp byte

Độ dài chuỗi ký tự không luôn bằng số byte truyền đi. Payload JSON có thể chứa Unicode:

~~~json
{
  "display_name": "Nguyễn Văn An",
  "department": "Nghiên cứu và Phát triển"
}
~~~

Một ký tự Unicode có thể chiếm nhiều byte trong UTF-8. Vì vậy, schema và giới hạn phải xác định rõ đo theo **byte UTF-8 sau serialization**, không chỉ đếm số ký tự hoặc số trường.

Cần đo riêng:

- số byte payload JSON UTF-8;
- số byte protected header JSON UTF-8;
- số ký tự compact token;
- số byte header HTTP hoặc cookie thực tế sau khi đóng gói;
- tổng kích thước request khi token được gửi cùng các header khác.

### 2.2. Không có một giới hạn JWT phổ quát

JWT/JWS/JWE không đưa ra một giới hạn kích thước token chung áp dụng cho mọi hệ thống. Giới hạn thực tế phụ thuộc:

- HTTP server và client;
- reverse proxy, load balancer, API gateway, WAF;
- cách token được gửi trong Authorization header, cookie hoặc message;
- giới hạn của browser/cookie store;
- thư viện JOSE/JWT và parser JSON;
- kiến trúc cache, logging và message broker.

Do đó, không thể chỉ dựa vào một con số chung trên Internet để kết luận token của hệ thống sẽ hoạt động. Cần đặt giới hạn nội bộ và kiểm tra xuyên suốt đường truyền thật.

## 3. Những thành phần làm payload phình to

Một số loại claim dễ khiến token tăng kích thước:

| Thành phần | Ví dụ | Nguy cơ |
| --- | --- | --- |
| Danh sách role dài | Hàng trăm nhóm hoặc vai trò | Payload tăng, quyền khó kiểm soát và dễ lỗi thời |
| Danh sách permission chi tiết | Quyền trên từng bản ghi | Token rất lớn, snapshot quyền nhanh lỗi thời |
| Hồ sơ người dùng | Tên, địa chỉ, số điện thoại, ảnh, thuộc tính tổ chức | Lộ dữ liệu và lặp lại ở mọi request |
| Danh sách tenant | Tất cả tổ chức người dùng từng tham gia | Không phản ánh tenant đang được chọn |
| Dữ liệu nghiệp vụ | Đơn hàng, cấu hình, thông tin thanh toán | Biến JWT thành nơi chứa dữ liệu không phù hợp |
| Object lồng nhau | Profile → organization → teams → permissions | Parser tốn tài nguyên, schema phức tạp |
| Claim tùy chỉnh lặp lại | Nhiều bản sao cùng thông tin dưới tên khác | Lãng phí và có thể gây mâu thuẫn |
| Chuỗi không giới hạn | Metadata, description, user-agent | Có thể bị lợi dụng để tạo token/request rất lớn |

JWT thường nên chứa định danh và thông tin authorization gọn cần thiết cho audience, thay vì mang toàn bộ dữ liệu mà hệ thống có thể truy vấn.

### 3.1. Claim quyền không nên liệt kê mọi đối tượng

Ví dụ không tốt:

~~~json
{
  "sub": "user-84",
  "orders_allowed": [
    "order-000001",
    "order-000002",
    "order-000003",
    "order-000004"
  ]
}
~~~

Nếu người dùng có hàng nghìn đơn hàng, danh sách sẽ làm payload lớn và nhanh lỗi thời. Thay vào đó, token có thể chứa scope và tenant context:

~~~json
{
  "sub": "user-84",
  "aud": "https://api.example.net/orders",
  "tenant_id": "tenant-a",
  "scope": "orders:read"
}
~~~

Orders API tự kiểm tra quyền trên từng đơn hàng. Token biểu thị loại hành động và ngữ cảnh; dữ liệu quan hệ chi tiết được kiểm tra tại resource server.

## 4. Nguyên tắc tối thiểu hóa claims

Cách hiệu quả nhất để giảm payload là **không đưa claim không cần thiết vào token**.

Trước khi thêm một claim, hãy hỏi:

1. Resource server hoặc client nhận token có thực sự cần claim này không?
2. Claim có thể được suy ra an toàn từ claim khác hoặc lấy từ nguồn nội bộ không?
3. Claim có chứa dữ liệu cá nhân hoặc dữ liệu nghiệp vụ nhạy cảm không?
4. Giá trị có thay đổi thường xuyên khiến token nhanh lỗi thời không?
5. Claim có cần thiết cho mọi request hay chỉ một thao tác hiếm?
6. Có thể dùng định danh/tham chiếu ngắn và tra cứu phía máy chủ không?
7. Claim có thể làm lộ cấu trúc nội bộ, danh sách tenant hoặc quyền của người dùng không?

Một claim chỉ hữu ích cho một API không nên tự động xuất hiện trong token dành cho API khác. Thiết kế audience-specific giúp giới hạn cả quyền lẫn dữ liệu được tiết lộ.

### 4.1. Ưu tiên dữ liệu tối thiểu và có ngữ nghĩa rõ

Nên ưu tiên:

- định danh subject ổn định thay vì toàn bộ hồ sơ;
- scope/permission ngắn gọn thay vì danh sách mô tả dài;
- một tenant đang được chọn thay vì mọi tenant;
- claim boolean hoặc enum nhỏ khi thật sự cần;
- thời gian và trạng thái tối thiểu phục vụ quyết định;
- claim riêng có hợp đồng rõ ràng và giới hạn kích thước.

Tránh đưa vào token:

- mật khẩu, OTP, recovery code hoặc secret;
- private key, client secret, API key;
- toàn bộ profile hoặc dữ liệu cá nhân không cần thiết;
- nội dung nghiệp vụ như đơn hàng, hóa đơn, giao dịch;
- danh sách lớn các object hoặc quyền trên từng bản ghi;
- dữ liệu có thể truy vấn nhanh và an toàn ở resource server.

Payload của JWS được ký nhưng không được mã hóa. Người giữ token có thể đọc các segment header và payload sau Base64URL decode. JWE bảo vệ tính bí mật nhưng không làm cho việc đưa dữ liệu dư thừa trở nên hợp lý.

## 5. Định nghĩa giới hạn cấu trúc, không chỉ giới hạn tổng byte

Chỉ đặt một giới hạn tổng kích thước chưa đủ. Một payload nhỏ vẫn có thể có cấu trúc phức tạp khiến parser hoặc policy engine xử lý tốn kém.

Schema của mỗi token profile nên có các giới hạn sau:

| Giới hạn | Ý nghĩa |
| --- | --- |
| Maximum payload bytes | Số byte tối đa của JSON Claims Set UTF-8 |
| Maximum compact token length | Tổng chiều dài token tối đa khi truyền |
| Maximum header bytes | Kích thước protected header tối đa |
| Maximum claim count | Số member tối đa trong Claims Set |
| Maximum string length | Độ dài tối đa của từng chuỗi hoặc nhóm claim |
| Maximum array items | Số phần tử tối đa trong mỗi mảng |
| Maximum object depth | Độ sâu object/array lồng nhau |
| Maximum numeric range | Miền giá trị hợp lệ cho claim số |
| Maximum nesting/extension size | Giới hạn cho extension hoặc cấu trúc lồng |
| Maximum parsing time/resources | Ngân sách CPU/bộ nhớ cho xử lý token |

Giới hạn phải được áp dụng cả khi **phát hành** lẫn **tiếp nhận**. Issuer không phát hành token vượt giới hạn mà resource server không thể chấp nhận; resource server cũng không được dựa vào giả định rằng mọi token đến từ issuer đều nhỏ và đơn giản.

### 5.1. Giới hạn số lượng claim

Mỗi claim thêm tên, dấu phân cách, giá trị và phần encoding. Nhiều claim ngắn vẫn có thể làm payload lớn và khó quản lý.

- Định nghĩa allowlist claim theo profile.
- Không cho client tự thêm tên claim.
- Giới hạn số claim tùy chỉnh.
- Tránh chứa cùng một thông tin ở nhiều claim có ý nghĩa trùng nhau.
- Từ chối hoặc bỏ qua extension không được hỗ trợ theo chính sách profile.
- Không tạo claim động từ dữ liệu tùy ý của người dùng.

### 5.2. Giới hạn độ dài chuỗi

Các trường như `sub`, `iss`, `aud`, `scope`, `client_id` và claim riêng cần có giới hạn phù hợp. Giới hạn cần phản ánh định dạng và hợp đồng, không cắt chuỗi một cách im lặng.

Không nên cắt ngắn subject hoặc audience để vừa kích thước vì có thể thay đổi định danh hoặc làm hai giá trị khác nhau trở thành một. Nếu một trường vượt giới hạn, hãy từ chối dữ liệu hoặc thay đổi thiết kế claim.

### 5.3. Giới hạn mảng và object lồng nhau

Mảng lớn và object sâu làm tăng số thao tác parse, cấp phát bộ nhớ và kiểm tra authorization. Nếu profile không cần object lồng nhau, nên giới hạn schema ở các kiểu đơn giản.

Ví dụ, thay vì:

~~~json
{
  "identity": {
    "organization": {
      "units": [
        {
          "name": "Unit A",
          "teams": [
            {
              "name": "Team 1",
              "permissions": ["read", "update", "approve"]
            }
          ]
        }
      ]
    }
  }
}
~~~

có thể dùng các claim gọn:

~~~json
{
  "sub": "user-84",
  "tenant_id": "tenant-a",
  "scope": "orders:read orders:update"
}
~~~

Nếu bên nhận cần dữ liệu tổ chức hoặc quyền chi tiết, hãy truy vấn dịch vụ có thẩm quyền hoặc dùng một reference có kiểm soát.

## 6. Chọn claim nhúng hay tham chiếu dữ liệu phía máy chủ

Không phải dữ liệu nào cũng nên nằm trong JWT. Có hai cách thiết kế:

- **Self-contained claims:** JWT mang các claim cần thiết để resource server xác minh và ra quyết định cục bộ.
- **Reference-based / opaque reference:** token mang định danh hoặc tham chiếu; resource server tra cứu dữ liệu/quyền ở máy chủ.

| Tiêu chí | Self-contained JWT | Token/reference có tra cứu |
| --- | --- | --- |
| Kích thước token | Tăng theo số claim | Thường nhỏ hơn |
| Độ trễ request | Có thể xác minh offline | Có thêm truy vấn hoặc introspection |
| Cập nhật quyền | Claim là snapshot cho tới khi token hết hạn/thu hồi | Có thể phản ánh trạng thái mới nhanh hơn |
| Khả năng hoạt động khi backend lỗi | Có thể tiếp tục xác minh nếu không cần trạng thái ngoài | Phụ thuộc dịch vụ tra cứu |
| Quyền riêng tư | Payload có thể tiết lộ nhiều thông tin | Có thể chỉ lộ reference, dữ liệu ở máy chủ |
| Vận hành | Cần quản lý TTL, audience và payload | Cần bảo vệ, mở rộng và giám sát kho trạng thái |

Có thể dùng mô hình kết hợp: JWT mang subject, issuer, audience, thời gian và một số scope nhỏ; quyền chi tiết hoặc profile được tra cứu ở resource server.

Reference không được trở thành ID dễ đoán cho phép truy cập dữ liệu. Resource server vẫn phải xác minh token và authorization; biết một reference không đồng nghĩa có quyền đọc dữ liệu.

## 7. Tác động đến HTTP header, cookie và đường truyền

JWT thường được truyền trong HTTP Authorization header:

~~~http
Authorization: Bearer <compact-jwt>
~~~

Header này có thể đi qua client, CDN/WAF, reverse proxy, load balancer, API gateway và application server. Mỗi thành phần có giới hạn riêng về tổng header, từng field và request line.

Nếu token quá lớn:

- proxy có thể trả lỗi trước khi request tới ứng dụng;
- gateway có thể từ chối trong khi một đường gọi nội bộ vẫn chấp nhận;
- header bị chia nhỏ hoặc xử lý khác nhau giữa các tầng;
- log/trace có thể phình to nếu vô tình ghi header;
- HTTP/2 hoặc HTTP/3 header compression không loại bỏ giới hạn kích thước logic hay rủi ro token lớn.

Khi truyền JWT trong cookie, cần xét giới hạn cookie của trình duyệt, giới hạn tổng cookie theo domain và kích thước header Cookie gửi về server. Token lớn có thể khiến cookie bị từ chối, bị cắt hoặc làm mọi request cùng domain mang nhiều dữ liệu hơn.

Không có một giới hạn header/cookie duy nhất cho mọi browser và proxy. Hãy xác định ngưỡng nhỏ nhất trên đường truyền thật và để token nhỏ hơn ngưỡng đó với khoảng dự phòng.

### 7.1. Không chuyển token lớn sang URL

Đưa bearer token vào query string hoặc URL path không giải quyết vấn đề kích thước. URL có thể bị lưu trong browser history, server log, analytics, referrer hoặc hệ thống giám sát. URL cũng có giới hạn độ dài khác nhau giữa client và hạ tầng.

Dùng kênh truyền được thiết kế cho credential (ví dụ Authorization header hoặc cookie với thuộc tính bảo mật phù hợp) và giữ token trong giới hạn hợp lý. Không dùng URL như nơi chứa token chỉ vì header quá lớn.

### 7.2. Xử lý lỗi kích thước ở tầng HTTP

Nếu request header vượt giới hạn, HTTP server hoặc intermediary có thể từ chối trước khi JWT parser chạy. HTTP 431 Request Header Fields Too Large được định nghĩa cho trường hợp header quá lớn, nhưng hành vi thực tế còn phụ thuộc hạ tầng. Không nên giả định mọi thành phần đều trả cùng mã lỗi.

Cần quan sát response từ từng tầng và thống nhất cấu hình. Không tăng giới hạn vô hạn ở gateway để “sửa” token phình to; trước hết hãy xác định claim nào không cần thiết.

## 8. Tác động đến hiệu năng và khả năng mở rộng

Mỗi byte JWT được truyền lại trên nhiều request. Khi một API được gọi thường xuyên, token lớn làm tăng:

- network egress/ingress;
- chi phí TLS record và truyền dữ liệu;
- bộ nhớ cho request context và buffer;
- CPU giải mã Base64URL, parse JSON và kiểm tra schema;
- chi phí ký/xác minh hoặc mã hóa/giải mã;
- kích thước cache key và chi phí lưu trữ;
- độ trễ và nguy cơ vượt timeout khi request đồng thời cao.

Nếu token được gửi trong mọi request, giảm vài KB có thể tạo ra khác biệt đáng kể ở lưu lượng lớn. Nên đo ở cấp request thực tế, không chỉ benchmark hàm tạo JWT riêng lẻ.

### 8.1. Đo lường phù hợp

Theo dõi phân bố kích thước thay vì chỉ trung bình:

- p50, p90, p95, p99 của compact token length;
- payload byte size theo token profile và audience;
- số token bị từ chối vì vượt giới hạn;
- thời gian parse, verify, decrypt và authorization;
- tỷ lệ lỗi header quá lớn ở gateway/proxy;
- tỷ lệ token chứa claim tùy chỉnh lớn hoặc array nhiều phần tử.

Không dùng raw token, subject hoặc giá trị claim nhạy cảm làm label metric có cardinality cao. Chỉ ghi bucket kích thước, token profile, audience class hoặc reason code phù hợp.

## 9. JWS, JWE và nén payload

### 9.1. JWS không tự nén payload

JWS ký nội dung; Base64URL chỉ mã hóa biểu diễn byte, không nén. Một payload JSON lớn vẫn tạo ra token lớn hơn sau Base64URL encoding.

Không tự nén JSON rồi nhét byte nén vào payload JWS nếu profile bên nhận không định nghĩa cách xử lý đó. Việc này làm giảm khả năng tương tác và có thể tạo một định dạng riêng khó xác minh.

### 9.2. JWE có tham số zip trong một số profile

JWE định nghĩa tham số header `zip` cho nén plaintext trước khi mã hóa trong các trường hợp được hỗ trợ, ví dụ DEFLATE. Nén có thể giảm kích thước nếu payload có nhiều chuỗi lặp, nhưng không nên coi đây là cách thay thế tối thiểu hóa claims.

Cần lưu ý:

- header và các segment JWE vẫn có overhead;
- dữ liệu ngẫu nhiên hoặc đã nén có thể không giảm kích thước;
- bên nhận phải hỗ trợ đúng thuật toán/profile nén;
- giải nén cần giới hạn kích thước output và tài nguyên để chống decompression bomb;
- nén nội dung do attacker kiểm soát cùng secret trong một thông điệp mã hóa có thể tạo side channel dựa trên độ dài trong một số thiết kế;
- không tự động chấp nhận `zip` từ header chưa tin cậy nếu profile không cho phép.

### 9.3. Nén không che giấu nội dung JWS

Base64URL không phải mã hóa bảo mật. Với JWS, payload vẫn có thể đọc được. Nếu dữ liệu nhạy cảm không nên lộ cho người giữ token, hãy loại bỏ dữ liệu đó hoặc dùng thiết kế mã hóa phù hợp. Không thêm thông tin nhạy cảm chỉ vì đã dùng JWE.

## 10. Quy trình đặt và thực thi giới hạn

Một quy trình thực tế:

1. **Phân loại token profile:** access token, ID token, assertion, token nội bộ hoặc token dùng một lần.
2. **Xác định nơi truyền:** Authorization header, cookie, message hoặc kênh khác.
3. **Đo baseline:** thu thập kích thước token hiện tại và phân bố claim theo audience.
4. **Đặt giới hạn:** payload bytes, compact token length, header, claim count, string length, array cardinality, nesting depth và parse budget.
5. **Tối thiểu hóa:** loại bỏ claim không cần, rút gọn scope, tránh nhúng danh sách lớn.
6. **Đồng bộ cấu hình:** issuer, gateway, proxy, client và resource server dùng giới hạn tương thích.
7. **Validate khi phát hành:** không ký token vượt schema/limit.
8. **Validate khi tiếp nhận:** từ chối sớm token quá lớn hoặc cấu trúc vượt giới hạn trước khi thực hiện xử lý tốn kém.
9. **Giám sát và điều chỉnh:** theo dõi lỗi, latency và thay đổi kích thước theo phiên bản.

Sơ đồ:

~~~mermaid
flowchart TD
    A["Chọn token profile và audience"] --> B["Xác định nơi token được truyền"]
    B --> C["Đo kích thước payload/token hiện tại"]
    C --> D["Định nghĩa byte, count, depth và time limits"]
    D --> E["Tối thiểu hóa claims"]
    E --> F["Validate schema trước khi ký"]
    F --> G{"Payload/token nằm trong giới hạn?"}
    G -- "Không" --> X["Từ chối phát hành và ghi reason code"]
    G -- "Có" --> H["Ký hoặc mã hóa theo profile"]
    H --> I["Kiểm tra ở gateway/resource server"]
    I --> J["Theo dõi kích thước, lỗi và latency"]
~~~

### 10.1. Giới hạn ở cả issuer và resource server

Issuer kiểm soát token mình tạo ra nên phải enforce giới hạn trước khi ký. Resource server cần tự giới hạn đầu vào vì:

- token có thể đến từ issuer khác;
- gateway có thể bị bypass;
- token có thể bị gửi sai endpoint;
- parser phải chống dữ liệu bất thường ngay cả khi chữ ký cuối cùng không hợp lệ.

Không chỉ kiểm tra sau khi parse hoàn toàn. Hãy giới hạn tổng chiều dài và segment trước khi cấp phát buffer lớn hoặc giải mã; giới hạn JSON depth/member trong parser; sau đó xác minh mật mã và claims theo profile.

## 11. Ví dụ thiết kế payload trước và sau tối thiểu hóa

### 11.1. Payload phình to

~~~json
{
  "iss": "https://auth.example.net",
  "sub": "user-84",
  "aud": [
    "https://api.example.net/orders",
    "https://api.example.net/payments",
    "https://api.example.net/users"
  ],
  "profile": {
    "name": "Nguyễn Văn An",
    "email": "an@example.net",
    "phone": "+84...",
    "address": "...",
    "department": "...",
    "avatar": "..."
  },
  "tenants": [
    "tenant-a",
    "tenant-b",
    "tenant-c"
  ],
  "all_roles": [
    "employee",
    "manager",
    "auditor",
    "support",
    "..."
  ],
  "all_permissions": [
    "orders:read",
    "orders:update",
    "orders:refund",
    "users:read",
    "users:manage",
    "..."
  ],
  "exp": 1900000900
}
~~~

Vấn đề:

- token dùng nhiều audience dù request chỉ cần Orders API;
- profile chứa dữ liệu không cần cho authorization;
- danh sách tenant và role không phản ánh ngữ cảnh đang chọn;
- permission quá rộng và có thể nhanh lỗi thời;
- token tiết lộ dữ liệu cá nhân cho mọi bên có thể đọc payload JWS.

### 11.2. Payload tối thiểu theo một resource

~~~json
{
  "iss": "https://auth.example.net",
  "sub": "user-84",
  "aud": "https://api.example.net/orders",
  "tenant_id": "tenant-a",
  "scope": "orders:read",
  "iat": 1900000000,
  "exp": 1900000900
}
~~~

Token ngắn hơn, audience rõ hơn và quyền bị giới hạn theo tenant. Orders API tra cứu profile hoặc kiểm tra ownership khi cần; token không mang toàn bộ dữ liệu người dùng.

### 11.3. Khi cần nhiều quyền chi tiết

Nếu một ứng dụng cần hàng trăm permission trên nhiều object, không nên mặc định nhét toàn bộ danh sách vào JWT. Có thể:

- dùng scope tổng quát theo action/resource;
- dùng policy decision tại resource server;
- tra cứu quyền theo subject, tenant và object;
- dùng token reference hoặc introspection khi cần trạng thái mới;
- chia yêu cầu thành các token audience-specific;
- thiết kế grant có giới hạn thời gian và quyền.

Chọn phương án theo trade-off giữa tính độc lập của JWT, độ trễ tra cứu và yêu cầu thu hồi quyền.

## 12. Mã giả validate kích thước và độ phức tạp

Mã giả dưới đây minh họa các giới hạn trước khi ký:

~~~text
function validatePayloadBudget(claims, profile):
    serialized = safeJsonSerializeUtf8(
        claims,
        rejectDuplicateMemberNames = true
    )

    require serialized.byteLength <= profile.maxPayloadBytes
    require countTopLevelClaims(claims) <= profile.maxClaimCount
    require jsonDepth(claims) <= profile.maxNestingDepth

    for each (name, value) in claims:
        require name.length <= profile.maxClaimNameLength
        require valueWithinTypeSpecificLimits(
            name,
            value,
            profile.claimRules[name]
        )

    require noForbiddenClaims(claims, profile)
    return serialized


function issueJwt(context):
    profile = tokenProfiles.require(context.tokenType)
    claims = buildMinimalClaimsFromTrustedSources(context)

    payloadBytes = validatePayloadBudget(claims, profile)
    header = buildProtectedHeaderFromPolicy(profile)

    token = joseSigner.sign(header, payloadBytes, profile.signingKey)
    require token.length <= profile.maxCompactTokenLength

    return token
~~~

Issuer nên kiểm tra cả payload bytes và compact token length sau khi ký vì kích thước cuối còn phụ thuộc header, chữ ký, thuật toán và encoding. Nếu vượt giới hạn, không trả token; cần điều chỉnh schema hoặc cách biểu diễn claims.

Mã giả ở resource server:

~~~text
function acceptIncomingToken(token, endpointPolicy):
    require token is a string
    require token.length <= endpointPolicy.maxCompactTokenLength

    parts = splitPreservingEmptySegments(token, ".")
    require parts.count in endpointPolicy.allowedSegmentCounts

    enforceSegmentLengthLimits(parts, endpointPolicy)
    parseHeaderWithLimits(parts[0], endpointPolicy.jsonLimits)

    verifiedObject = verifyOrDecryptWithTrustedJosePolicy(
        token,
        endpointPolicy
    )

    claims = parseVerifiedClaimsWithLimits(
        verifiedObject.payload,
        endpointPolicy.jsonLimits
    )

    require claims.byteLength <= endpointPolicy.maxPayloadBytes
    require countClaims(claims) <= endpointPolicy.maxClaimCount
    require jsonDepth(claims) <= endpointPolicy.maxNestingDepth

    return validateClaimsAndAuthorize(claims, endpointPolicy)
~~~

Việc parse header trước xác minh chỉ phục vụ chọn thuật toán/khóa ứng viên trong allowlist. Với JWE, không parse plaintext trước khi xác thực tag và giải mã thành công. Cần dùng thư viện JOSE đã được kiểm chứng thay vì tự triển khai thuật toán ký hoặc mã hóa.

## 13. Kiểm thử giới hạn và trường hợp biên

Bộ kiểm thử cần xác minh cả trường hợp hợp lệ lẫn dữ liệu vượt giới hạn:

| Nhóm | Trường hợp | Kết quả mong đợi |
| --- | --- | --- |
| Payload bytes | Đúng ngưỡng tối đa | Được xử lý nếu mọi giới hạn khác đạt |
| Payload bytes | Vượt một byte | Từ chối phát hành/tiếp nhận theo policy |
| Compact length | Token vượt giới hạn tổng | Từ chối sớm |
| Unicode | Chuỗi đa byte làm payload vượt ngưỡng | Đếm byte UTF-8 chính xác |
| Claim count | Số claim đúng ngưỡng và vượt ngưỡng | Ranh giới được xử lý nhất quán |
| String | Claim string quá dài | Từ chối, không cắt im lặng |
| Array | Danh sách permission rất lớn | Từ chối hoặc thay đổi mô hình dữ liệu |
| Nesting | JSON lồng sâu bất thường | Parser từ chối trong giới hạn tài nguyên |
| Duplicate | Tên claim trùng lặp | Từ chối theo parser policy |
| JWE | Ciphertext lớn hoặc giải nén output quá lớn | Giới hạn giải mã/giải nén |
| HTTP | Header Authorization vượt giới hạn proxy | Quan sát đúng lỗi ở tầng hạ tầng |
| Cookie | JWT khiến Cookie header vượt giới hạn | Không phát hành/cấu hình vượt khả năng client |
| Compatibility | Token do issuer tạo đi qua mọi proxy/API | Tất cả tầng chấp nhận nhất quán |
| Performance | Nhiều request đồng thời với token gần ngưỡng | CPU/bộ nhớ/latency trong ngân sách |

Nên kiểm thử bằng payload lớn có cấu trúc thực tế, Unicode, mảng nhiều phần tử, object lồng sâu và các claim tùy chỉnh. Fuzz testing có thể phát hiện parser tiêu tốn tài nguyên hoặc xử lý sai giới hạn.

### 13.1. Kiểm thử xuyên suốt đường truyền

Không chỉ test ở unit test của issuer. Cần gửi token có kích thước gần giới hạn qua:

1. client thực tế;
2. CDN/WAF hoặc edge gateway;
3. reverse proxy/load balancer;
4. API gateway;
5. HTTP server;
6. resource server và thư viện JOSE/JWT;
7. cache, tracing và logging nếu token đi qua các thành phần đó.

Đặt giới hạn theo thành phần có ngưỡng nhỏ nhất, cộng khoảng dự phòng cho các header khác. Một token vừa khít giới hạn tối đa của proxy có thể thất bại khi request còn Cookie, trace headers hoặc header nghiệp vụ khác.

## 14. Xử lý lỗi và giám sát

Khi payload hoặc token vượt giới hạn:

- từ chối trước khi thực hiện thao tác tốn kém không cần thiết;
- trả lỗi phù hợp giao thức và không tiết lộ nội dung claim;
- không tự cắt payload, bỏ claim hoặc sửa token để làm nó vừa giới hạn;
- ghi reason code như `payload_too_large`, `token_too_large`, `claim_count_exceeded` hoặc `nesting_limit_exceeded`;
- không log JWT nguyên vẹn;
- theo dõi tỷ lệ token vượt ngưỡng theo profile/audience và phiên bản schema;
- cảnh báo khi kích thước p95/p99 tăng đột biến sau một thay đổi claim.

Nếu một phiên bản mới thêm claim làm token tăng kích thước, cần rollout có kiểm soát. Resource server phải sẵn sàng với schema/limit mới trước khi issuer phát hành token theo định dạng mới.

Không tăng giới hạn vô hạn để che một claim thiết kế kém. Trước hết hãy xác định dữ liệu nào thật sự cần thiết, liệu có thể tham chiếu hoặc truy vấn tại resource server hay không.

## 15. Những sai lầm cần tránh

- Chỉ giới hạn số ký tự mà không đo byte UTF-8 và compact token length.
- Giả định JWT có một giới hạn kích thước chuẩn áp dụng ở mọi môi trường.
- Quên overhead Base64URL, protected header, signature, IV hoặc authentication tag.
- Nhét toàn bộ profile, danh sách role, permission và tenant vào token.
- Dùng payload JWT như cache dữ liệu nghiệp vụ.
- Giới hạn tổng byte nhưng không giới hạn claim count, string length, array size và nesting depth.
- Chỉ validate ở issuer mà không giới hạn token đầu vào tại resource server.
- Tăng giới hạn proxy mà không đánh giá tác động tới memory, CPU và request concurrency.
- Chuyển token lớn sang URL query string.
- Coi JWS Base64URL là mã hóa bảo mật.
- Dùng nén để thay thế tối thiểu hóa claims hoặc không giới hạn giải nén.
- Cắt chuỗi hoặc bỏ claim im lặng khi token vượt ngưỡng.
- Log toàn bộ JWT để điều tra lỗi kích thước.
- Rollout claim mới mà không kiểm thử end-to-end với gateway và consumer.

## 16. Checklist thiết kế payload

**Thiết kế claims:**

- [ ] Mỗi claim có mục đích rõ ràng cho audience nhận token.
- [ ] Payload không chứa profile hoặc dữ liệu nghiệp vụ không cần thiết.
- [ ] Scope/permission được tối thiểu hóa và không liệt kê hàng loạt object.
- [ ] Claim riêng có allowlist, kiểu và giới hạn rõ ràng.
- [ ] Dữ liệu có thể tra cứu an toàn không bị nhúng dư thừa vào token.

**Giới hạn cấu trúc:**

- [ ] Có max payload bytes tính trên UTF-8 serialization.
- [ ] Có max compact token length và max protected header bytes.
- [ ] Có max claim count, string length, array items và nesting depth.
- [ ] Có giới hạn parse time, memory và kích thước giải nén nếu hỗ trợ JWE compression.
- [ ] Giới hạn được enforce trước khi ký và khi tiếp nhận.

**Tương thích và vận hành:**

- [ ] Đã kiểm tra giới hạn của client, browser, cookie, proxy, gateway và server.
- [ ] Token nhỏ hơn ngưỡng đường truyền nhỏ nhất với khoảng dự phòng.
- [ ] Có kiểm thử token gần ngưỡng và vượt ngưỡng.
- [ ] Có metric phân bố kích thước, lỗi parser và latency.
- [ ] Log không chứa token hoặc claim nhạy cảm nguyên vẹn.
- [ ] Thay đổi schema/claim được rollout đồng bộ với consumer.

## 17. Tài liệu tham khảo

- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): cấu trúc JWT và Claims Set.
- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515): JWS Compact Serialization và Base64URL.
- [RFC 7516 — JSON Web Encryption (JWE)](https://www.rfc-editor.org/rfc/rfc7516): JWE Compact Serialization, encrypted payload và tham số nén `zip`.
- [RFC 7518 — JSON Web Algorithms (JWA)](https://www.rfc-editor.org/rfc/rfc7518): thuật toán JOSE, IV, tag và các tham số mã hóa.
- [RFC 6585 — Additional HTTP Status Codes](https://www.rfc-editor.org/rfc/rfc6585): HTTP 431 Request Header Fields Too Large.
- [RFC 4648 — The Base16, Base32, and Base64 Data Encodings](https://www.rfc-editor.org/rfc/rfc4648): Base64URL encoding.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): ngữ nghĩa HTTP và xử lý header.
- [OWASP Denial of Service Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Denial_of_Service_Cheat_Sheet.html): giới hạn tài nguyên và giảm rủi ro DoS.

**Ghi nhớ:** Hãy giới hạn cả kích thước lẫn độ phức tạp của payload. Đo byte UTF-8 và compact token size, tối thiểu hóa claim theo audience, giới hạn chuỗi/mảng/độ sâu, kiểm tra ở cả issuer và resource server, đồng thời xác minh khả năng đi qua toàn bộ hạ tầng. JWT nhỏ, rõ mục đích và có schema giới hạn giúp giảm chi phí truyền tải, parser abuse và rủi ro lộ dữ liệu.

