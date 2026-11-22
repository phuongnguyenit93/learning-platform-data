# Polling Token Endpoint bằng device_code

## 1. Mục tiêu và tình huống sử dụng

**OAuth 2.0 Device Authorization Grant** (RFC 8628) giải quyết bài toán thiết bị có khả năng nhập liệu hạn chế hoặc không có trình duyệt phù hợp: TV, máy chơi game, thiết bị trình chiếu, đầu phát đa phương tiện hoặc ứng dụng dòng lệnh. Thiết bị hiển thị hướng dẫn; người dùng dùng **một thiết bị khác có trình duyệt** để đăng nhập và chấp thuận quyền. Trong khi đó, ứng dụng trên thiết bị ban đầu gọi **Token Endpoint nhiều lần theo một khoảng thời gian được quy định** để biết người dùng đã hoàn tất hay chưa. Quá trình gọi lặp lại này gọi là **polling**.

Với **Spring Security** và **Spring Authorization Server** chạy trong **Spring Boot**, phần lớn logic kiểm tra device code nằm ở các filter/provider của Authorization Server. Tuy nhiên, **vòng lặp polling, lịch chờ, xử lý các mã lỗi giao thức và bảo vệ trạng thái UI** là trách nhiệm của **OAuth client trên thiết bị**. Cấu hình server đúng chưa đủ nếu client gửi hàng trăm yêu cầu mỗi giây hoặc bỏ qua lỗi <code>slow_down</code>.

Ví dụ xuyên suốt:

- Authorization Server: <code>https://auth.example.com</code>.
- OAuth public client trên TV: <code>living-room-tv</code>.
- Scope cần xin: <code>media.read</code>.
- Device Authorization Endpoint: <code>POST /oauth2/device_authorization</code>.
- Device Verification Endpoint: <code>/oauth2/device_verification</code> (người dùng mở bằng trình duyệt trên điện thoại).
- Token Endpoint: <code>POST /oauth2/token</code> (TV chủ động polling).

Sau bài, bạn có thể:

1. Phân biệt **<code>device_code</code>**, **<code>user_code</code>**, <code>verification_uri</code> và <code>verification_uri_complete</code>.
2. Tạo chính xác Token Request với grant <code>urn:ietf:params:oauth:grant-type:device_code</code>.
3. Xây vòng lặp polling tôn trọng <code>interval</code>, thời hạn <code>expires_in</code> và yêu cầu giảm tần suất khi có lỗi.
4. Xử lý đúng <code>authorization_pending</code>, <code>slow_down</code>, <code>access_denied</code>, <code>expired_token</code> cùng những lỗi OAuth khác.
5. Hiểu cách Spring Authorization Server liên kết device code với client, authorization, xác thực người dùng và consent.
6. Viết client polling bằng Java và thiết kế kiểm thử lịch polling không cần chờ theo thời gian thật.
7. Triển khai an toàn trong môi trường nhiều instance, mất kết nối mạng, người dùng hủy và thiết bị có tài nguyên hạn chế.

**Phạm vi phiên bản:** Những đoạn Java cấu hình server dùng phong cách <code>OAuth2AuthorizationServerConfigurer.authorizationServer()</code> và <code>HttpSecurity.with(...)</code> quen thuộc trong Spring Authorization Server 1.x. Ở những bản Spring Security đã tích hợp Authorization Server, API/package có thể thay đổi; kiểm tra bản đang chạy. Ví dụ client dùng <code>RestClient</code> (Spring Framework 6.1+) và Java 17+. Mã là minh họa kiến trúc, không phải toàn bộ source của một dự án triển khai.

## 2. Device Authorization khác Authorization Code như thế nào?

Trong Authorization Code Flow, **trình duyệt được dùng để ủy quyền thường nằm cùng ngữ cảnh với OAuth client**, có redirect URI và trao authorization code. Device Authorization Flow tách thành hai tác nhân:

1. **Thiết bị OAuth client**: hiển thị hướng dẫn và tự gọi token endpoint.
2. **Trình duyệt của người dùng**: mở URL verification, nhập mã và đăng nhập/chấp thuận.

Thiết bị không phải liên tục kiểm tra một trang HTML, không nhập mật khẩu trên TV và không tự nhận dữ liệu đăng nhập từ điện thoại. Nó chỉ gửi <code>device_code</code> cho Token Endpoint đến khi server thông báo thành công hoặc có lý do phải dừng.

~~~mermaid
sequenceDiagram
    autonumber
    participant D as TV / Public OAuth Client
    participant AS as Authorization Server
    participant B as Trình duyệt trên điện thoại
    D->>AS: POST /oauth2/device_authorization (client_id, scope)
    AS-->>D: device_code, user_code, verification_uri, expires_in, interval
    D-->>D: Hiển thị URL và user_code cho người dùng
    D->>AS: POST /oauth2/token (device_code grant)
    AS-->>D: authorization_pending
    B->>AS: Mở verification_uri và nhập user_code
    AS-->>B: Đăng nhập + consent theo chính sách
    B->>AS: Chấp thuận quyền cho thiết bị
    D->>AS: Poll sau khoảng thời gian hợp lệ
    AS-->>D: access_token, token_type, expires_in, scope nếu phù hợp
    D-->>D: Lưu access token an toàn và sử dụng API
~~~

Đây là sơ đồ **thành công**. Nếu người dùng từ chối, thiết bị nhận <code>access_denied</code>; nếu người dùng không hoàn tất trước hạn, thiết bị gặp <code>expired_token</code> hoặc tự nhận biết hết thời gian. Việc server chưa có câu trả lời cuối cùng là trạng thái **bình thường**, được biểu diễn bằng <code>authorization_pending</code>.

### 2.1. Hai endpoint không thể dùng thay thế

| Endpoint | Request đến từ ai? | Nhiệm vụ |
| --- | --- | --- |
| <code>/oauth2/device_authorization</code> | Thiết bị, một lần để khởi tạo phiên | Cấp <code>device_code</code>, <code>user_code</code>, verification URL, TTL và polling interval. |
| <code>/oauth2/device_verification</code> | Người dùng qua trình duyệt trên thiết bị khác | Đăng nhập, xác minh <code>user_code</code>, kiểm tra tên client và quyết định consent. |
| <code>/oauth2/token</code> | Thiết bị, nhiều lần theo interval | Kiểm tra <code>device_code</code> và trạng thái authorization để trả lỗi pending/slow_down hoặc access token. |

Trong Spring Authorization Server, các path trên là **giá trị mặc định phổ biến**; có thể thay bằng <code>AuthorizationServerSettings</code>. OAuth client nên dùng thông tin endpoint đã cấu hình hoặc discovery metadata phù hợp, không tự ghép URL từ issuer một cách thiếu kiểm tra.

## 3. Khởi tạo phiên để lấy <code>device_code</code>

### 3.1. Device Authorization Request

Với public client đã đăng ký có ID <code>living-room-tv</code>:

~~~http
POST /oauth2/device_authorization HTTP/1.1
Host: auth.example.com
Content-Type: application/x-www-form-urlencoded

client_id=living-room-tv&scope=media.read
~~~

Đây là cấu trúc request, không phải lệnh có thể gửi tới một server không tồn tại. Cần dùng **HTTPS** và URL encoding cho form body. Một confidential client có yêu cầu client authentication phải thực hiện phương thức đã đăng ký; thiết bị không thể giữ client secret an toàn thường nên được đăng ký **public client**, không hard-code secret vào firmware để giả vờ bảo mật.

### 3.2. Device Authorization Response

Ví dụ response theo RFC 8628:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store

{
  "device_code": "secret-device-code-value",
  "user_code": "JXHP-4QMN",
  "verification_uri": "https://auth.example.com/oauth2/device_verification",
  "verification_uri_complete": "https://auth.example.com/oauth2/device_verification?user_code=JXHP-4QMN",
  "expires_in": 600,
  "interval": 5
}
~~~

Các giá trị chỉ để minh họa, không có hiệu lực thực. Ý nghĩa chính:

| Trường | Theo RFC 8628 | Người dùng/thiết bị cần làm gì? |
| --- | --- | --- |
| <code>device_code</code> | **Bắt buộc**, chuỗi khó đoán | Thiết bị giữ bí mật và dùng trong token polling; **không hiển thị cho người dùng**. |
| <code>user_code</code> | **Bắt buộc**, mã dễ nhập | Hiển thị để người dùng nhập trong trình duyệt. |
| <code>verification_uri</code> | **Bắt buộc** | Hiển thị địa chỉ HTTPS mà người dùng cần mở trên điện thoại/máy tính. |
| <code>verification_uri_complete</code> | **Tùy chọn** | Có thể dùng cho QR/deep link để giảm thao tác nhập; vẫn cần kiểm soát phishing và xác nhận. |
| <code>expires_in</code> | **Bắt buộc**, đơn vị giây | Thời gian sống của device code **và user code**; client phải dừng khi hết. |
| <code>interval</code> | **Tùy chọn**, đơn vị giây | Khoảng chờ tối thiểu giữa các lần gửi yêu cầu token; **nếu không có thì mặc định 5 giây**. |

Không nhầm <code>expires_in</code> trong response này với <code>expires_in</code> của access token được cấp sau khi người dùng duyệt: chúng mô tả **hai credential khác nhau**.

### 3.3. <code>user_code</code> khác <code>device_code</code>

<code>user_code</code> được thiết kế để con người có thể đọc và nhập, nên thường ngắn hơn và cần rate limit ở giao diện verification để ngăn brute force. <code>device_code</code> được thiết kế là giá trị bí mật khó đoán, **chỉ** được đưa vào token polling request.

**Sai:** Gửi <code>user_code=JXHP-4QMN</code> đến <code>/oauth2/token</code> thay vì <code>device_code</code>.

**Đúng:** Người dùng nhập <code>user_code</code> trên điện thoại; TV giữ <code>device_code</code> và gửi giá trị đó theo chu kỳ tới Token Endpoint.

## 4. Poll Token Endpoint với grant <code>device_code</code>

Theo RFC 8628 §3.4, sau khi hiển thị hướng dẫn, client gửi một yêu cầu token có các tham số:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.com
Content-Type: application/x-www-form-urlencoded

grant_type=urn%3Aietf%3Aparams%3Aoauth%3Agrant-type%3Adevice_code&
device_code=secret-device-code-value&
client_id=living-room-tv
~~~

Các dòng body được ngắt để dễ đọc; request thật phải URL-encode đúng thành một form body. Giá trị <code>grant_type</code> khi giải mã là:

~~~text
urn:ietf:params:oauth:grant-type:device_code
~~~

| Tham số | Quy tắc |
| --- | --- |
| <code>grant_type</code> | **Bắt buộc** và phải chính xác là URN nói trên. Không dùng chuỗi rút gọn <code>device_code</code>. |
| <code>device_code</code> | **Bắt buộc**, lấy từ Device Authorization Response; không phải user code. |
| <code>client_id</code> | **Bắt buộc nếu client không xác thực bằng client credentials**. Public client thường phải gửi trường này. |
| Client authentication | **Bắt buộc nếu client đã được cấp credentials hoặc có yêu cầu xác thực khác**; dùng đúng phương thức đăng ký, ví dụ HTTP Basic, private_key_jwt hoặc mTLS khi phù hợp. |

RFC không yêu cầu gửi <code>scope</code> lại trong token polling: scope đã được ràng buộc với device authorization request trước đó và quyết định của người dùng. Không tự thêm scope mới trong lúc polling để cố leo thang quyền.

**Một lần polling không phải một lượt cấp quyền mới.** Mỗi request chỉ hỏi trạng thái của **cùng device code** trong cùng phiên, không tạo lại code nếu đang chờ, không đổi client ID và không chuyển token từ một thiết bị sang client khác.

## 5. Máy trạng thái polling

### 5.1. Luồng ở phía OAuth client

~~~mermaid
flowchart TD
    A["Nhận device_code + expires_in + interval"] --> B["Hiển thị verification URI và user_code"]
    B --> C{"Người dùng hủy hoặc hết TTL?"}
    C -- Có --> X["Dừng polling, xóa device_code khỏi bộ nhớ"]
    C -- Không --> D["POST /oauth2/token với device_code"]
    D --> E{"Token response"}
    E -- "200 + access_token" --> S["Thành công, lưu token an toàn, dừng"]
    E -- "authorization_pending" --> W["Đợi tối thiểu interval hiện tại"]
    E -- "slow_down" --> I["Tăng interval thêm 5 giây"]
    I --> W
    E -- "access_denied" --> N["Dừng: người dùng từ chối"]
    E -- "expired_token" --> X
    E -- "Lỗi OAuth khác" --> F["Dừng và xử lý lỗi an toàn"]
    E -- "Connection timeout" --> T["Giảm tần suất, ví dụ exponential backoff"]
    T --> W
    W --> C
~~~

Phần xác minh và cập nhật trạng thái thiết bị nằm ở Authorization Server; client không cần biết bảng dữ liệu hoặc filter nội bộ. Một máy trạng thái client có thể định nghĩa:

| Trạng thái client | Diễn giải | Chuyển tiếp |
| --- | --- | --- |
| <code>WAITING_FOR_USER</code> | Vừa hiển thị user code, chưa có quyết định. | Poll theo khoảng chờ. |
| <code>POLLING</code> | Gửi token request đã được lên lịch. | Đọc response. |
| <code>BACKING_OFF</code> | Nhận <code>slow_down</code> hoặc timeout kết nối. | Tăng thời gian chờ, sau đó poll lại. |
| <code>AUTHORIZED</code> | Nhận access token hợp lệ theo cấu trúc response. | Dừng poll, sử dụng token cho đúng Resource Server. |
| <code>DENIED</code> | Người dùng từ chối. | Dừng, không retry cùng device code. |
| <code>EXPIRED</code> | Device code đã hết hiệu lực. | Dừng, có thể bắt đầu flow mới **sau tương tác người dùng**. |
| <code>CANCELLED</code> | Người dùng hủy trên TV/CLI hoặc ứng dụng đóng. | Hủy lịch và làm sạch trạng thái; không phát token tự động. |
| <code>FAILED</code> | Lỗi client/grant/giao thức khác. | Dừng và nêu lỗi an toàn. |

### 5.2. Kết quả ở phía Authorization Server

Khi nhận một polling request, server phải xác minh đúng client, device code thuộc authorization hợp lệ, code chưa hết hạn/chưa bị sử dụng thành công và quyết định của End-User. Khái quát:

~~~text
Device code không tồn tại / sai client / không hợp lệ
  -> từ chối request

Device code hợp lệ nhưng End-User chưa duyệt
  -> authorization_pending

Client poll nhanh quá mức mà server yêu cầu giảm tốc
  -> slow_down (nếu triển khai chính sách này)

End-User từ chối
  -> access_denied

Device code hết hạn
  -> expired_token

End-User đã duyệt + client/token request hợp lệ
  -> phát access token và đánh dấu device code không thể dùng lại
~~~

Những nhánh trên là logic giao thức; chi tiết lỗi cho token không tồn tại, client không hợp lệ hoặc token đã bị dùng có thể khác theo phiên bản/provider. Client không nên dựa vào một HTTP status duy nhất để xác định nhánh, mà cần đọc **JSON <code>error</code>** theo OAuth.

## 6. Bốn mã lỗi đặc thù mà poller phải hiểu

### 6.1. <code>authorization_pending</code>

Nếu người dùng chưa hoàn thành các bước đăng nhập/consent, token endpoint trả lỗi:

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/json
Cache-Control: no-store

{"error":"authorization_pending"}
~~~

Đây là **trạng thái dự kiến** của Device Flow, không phải lỗi ứng dụng cần báo động mỗi lần xảy ra. Client giữ phiên và **chờ ít nhất interval hiện tại trước lần polling tiếp theo**. Không tạo device code khác, không đổi scope và không hiển thị “Đăng nhập thất bại” cho người dùng chỉ vì pending.

### 6.2. <code>slow_down</code>

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/json

{"error":"slow_down"}
~~~

RFC 8628 quy định poller phải **tăng interval thêm 5 giây** từ lúc nhận lỗi này, áp dụng cho **lần polling kế tiếp và tất cả lần sau**. Ví dụ interval trước là 5 giây, sau một <code>slow_down</code> thành 10 giây; nếu lại nhận <code>slow_down</code>, thành 15 giây.

Không chỉ chờ thêm 5 giây ở một lần rồi quay về interval cũ. Không dùng chính HTTP 400 để tự động retry ngay lập tức; làm vậy vừa sai giao thức vừa tăng tải và khả năng bị rate limit.

### 6.3. <code>access_denied</code>

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/json

{"error":"access_denied"}
~~~

End-User từ chối hoặc ủy quyền không được chấp thuận. Client **dừng polling ngay**, dọn mã thiết bị và cho người dùng thấy thông báo phù hợp. Không tự gửi một device authorization request mới nhằm “vượt qua” quyết định từ chối; nếu muốn thử lại, cần một hành động rõ ràng của người dùng.

### 6.4. <code>expired_token</code>

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/json

{"error":"expired_token"}
~~~

<code>device_code</code> hết hạn, phiên device authorization đã kết thúc. Client **dừng polling** và xóa giá trị device code đang giữ. Nếu cần tiếp tục, có thể khởi tạo flow mới nhưng nên đợi tương tác của người dùng để tránh polling không cần thiết.

### 6.5. Mọi lỗi OAuth khác

Các lỗi như <code>invalid_client</code>, <code>invalid_request</code>, <code>unauthorized_client</code>, <code>unsupported_grant_type</code> hoặc lỗi token không hợp lệ không cho phép poller tiếp tục vô hạn. RFC 8628 quy định: với **mã lỗi khác** <code>authorization_pending</code> và <code>slow_down</code>, client **phải dừng polling** rồi xử lý thích hợp.

Nếu server trả <code>429 Too Many Requests</code>, lỗi proxy, HTML hoặc JSON không hợp lệ, đó không phải lời mời retry ngay lập tức. Cần tuân thủ hướng dẫn vận hành đáng tin cậy nếu có; nếu không có hợp đồng retry rõ ràng, dừng an toàn, không đánh đồng với <code>authorization_pending</code>.

## 7. Tính toán <code>interval</code>, <code>expires_in</code> và lịch polling

### 7.1. Khoảng chờ tối thiểu

Ví dụ response ban đầu:

~~~json
{
  "device_code": "secret-device-code-value",
  "user_code": "JXHP-4QMN",
  "verification_uri": "https://auth.example.com/oauth2/device_verification",
  "expires_in": 600,
  "interval": 5
}
~~~

Client có thể gửi lần poll đầu tiên sau khi đã hiển thị hướng dẫn; **giữa những polling request liên tiếp** cần bảo đảm khoảng chờ tối thiểu. Một chiến lược dễ kiểm soát là **chờ đủ interval sau khi response trước hoàn tất** rồi mới gửi request tiếp theo; cách này có thể chậm hơn một chút nhưng không vô tình vượt tần suất cho phép.

Nếu server **không trả <code>interval</code>**, dùng **5 giây**, không mặc định 0 hoặc 1 giây. Nếu server trả giá trị không hợp lệ, nên coi đó là lỗi giao thức hoặc áp dụng fallback an toàn không nhanh hơn quy tắc, tránh vòng lặp quá tải.

### 7.2. Ví dụ trục thời gian

~~~text
T = 0s   Device Authorization Response: expires_in=600, interval=5
T = 0s   Poll lần 1  -> authorization_pending
T = 5s   Poll lần 2  -> authorization_pending
T = 10s  Poll lần 3  -> slow_down
                    interval mới = 5 + 5 = 10 giây
T = 20s  Poll lần 4  -> authorization_pending
T = 30s  Poll lần 5  -> 200 OK + access_token
          DỪNG POLLING
~~~

Các mốc là minh họa bỏ qua độ trễ mạng. Điều quan trọng không phải lúc nào cũng poll đúng các giây tròn, mà là **không sớm hơn khoảng chờ tối thiểu** và dừng ngay khi có trạng thái cuối cùng.

### 7.3. Timeout kết nối: giảm tần suất, không retry tức thì

Khi client **không thể kết nối hoặc gặp connection timeout**, RFC 8628 yêu cầu client **tự giảm tần suất polling trước khi retry**. Phương pháp được khuyến nghị là **exponential backoff**. Ví dụ:

~~~text
interval đang là 5 giây
Connection timeout lần 1 -> chờ tối thiểu 10 giây
Connection timeout lần 2 -> chờ tối thiểu 20 giây
Connection timeout lần 3 -> chờ tối thiểu 40 giây
~~~

Đây là ví dụ chính sách tăng dần; không có nghĩa bắt buộc chính xác các mốc trên. Nếu một request sau đó trả <code>slow_down</code>, vẫn phải tăng thêm 5 giây so với interval đang áp dụng. Nếu deadline đến trước thời điểm poll tiếp theo, **dừng** thay vì cố gửi một request muộn.

Không coi mọi <code>ResourceAccessException</code> trong Java là lỗi mạng có thể retry: lỗi xác minh chứng chỉ TLS, cấu hình DNS sai cố định hoặc endpoint không đáng tin có thể cần **dừng và xử lý** thay vì tiếp tục hàng trăm lần.

### 7.4. Deadline và đồng hồ

<code>expires_in</code> được tính bằng giây từ lúc Authorization Server phát response. Ở client, dùng **monotonic clock** như <code>System.nanoTime()</code> để theo dõi khoảng thời gian còn lại; không dùng mỗi <code>LocalDateTime.now()</code> vì đồng hồ hệ thống có thể bị thay đổi.

Không lưu TTL 600 giây rồi tái khởi động ứng dụng và coi còn đủ 600 giây. Khi muốn hỗ trợ resume, phải lưu deadline thực với thông tin đủ tin cậy, xử lý thời gian offline và chấp nhận server là nguồn quyết định cuối cùng. Với TV/CLI đơn giản, dọn phiên cũ khi ứng dụng khởi động lại thường dễ kiểm soát hơn.

## 8. Mã Java: một poller dùng <code>RestClient</code>

### 8.1. Mô hình dữ liệu

Ứng dụng client nhận response khởi tạo device authorization, lưu trong bộ nhớ riêng cho phiên:

~~~java
// Mã chạy trong OAuth CLIENT trên TV/CLI, KHÔNG phải filter của AS.
record DeviceSession(
    String clientId,
    String deviceCode,
    long expiresInSeconds,
    Long intervalSeconds
) {}

record TokenHttpResponse(int httpStatus, JsonNode body) {}
~~~

Những trường <code>user_code</code>, <code>verification_uri</code> phục vụ UI hiển thị riêng; poller **không cần gửi user code** về token endpoint. Nếu phần mềm dùng confidential client thì phải bổ sung client authentication theo đăng ký; đoạn dưới là **public client** gửi <code>client_id</code>.

### 8.2. Gửi một polling request và đọc cả response lỗi

~~~java
final class DeviceTokenHttpClient {
    private final RestClient restClient;
    private final ObjectMapper mapper;

    DeviceTokenHttpClient(RestClient restClient, ObjectMapper mapper) {
        this.restClient = restClient;
        this.mapper = mapper;
    }

    TokenHttpResponse pollOnce(DeviceSession session) {
        MultiValueMap<String, String> form = new LinkedMultiValueMap<>();
        form.add("grant_type", AuthorizationGrantType.DEVICE_CODE.getValue());
        form.add("device_code", session.deviceCode());
        form.add("client_id", session.clientId());

        return restClient.post()
            .uri("https://auth.example.com/oauth2/token")
            .contentType(MediaType.APPLICATION_FORM_URLENCODED)
            .body(form)
            .exchange((request, response) -> {
                JsonNode body = mapper.readTree(response.getBody());
                return new TokenHttpResponse(
                    response.getStatusCode().value(), body);
            });
    }
}
~~~

Chọn <code>exchange(...)</code> thay vì gọi <code>retrieve().body(...)</code> đơn giản vì token endpoint trả **HTTP 400 chứa JSON <code>error</code> hoàn toàn hợp lệ về mặt Device Flow**. Cần đọc được response body khi server trả <code>authorization_pending</code> hay <code>slow_down</code>.

Các import được lược bỏ. Đây là ví dụ cho Spring Framework 6.1+; trong Spring Boot, nên inject một <code>RestClient</code> được tạo bằng <code>RestClient.Builder</code>, có cấu hình TLS, connection timeout, read timeout và HTTP client đáng tin. Không ghi response JSON chứa access token hay raw device code ra log. Ví dụ URI là endpoint cố định; khi AS tùy chỉnh token endpoint, phải lấy URL chính thức đã cấu hình.

### 8.3. Vòng lặp xử lý response

Đoạn sau có chủ đích dùng **blocking API trong một background worker**, phù hợp với CLI hoặc tác vụ riêng của ứng dụng desktop. **Không gọi trực tiếp trong thread xử lý HTTP request của Spring MVC hoặc trên event-loop của WebFlux**; trong ứng dụng reactive nên dùng scheduler/reactor tương ứng.

~~~java
final class DeviceCodePoller {
    private final DeviceTokenHttpClient tokenClient;

    DeviceCodePoller(DeviceTokenHttpClient tokenClient) {
        this.tokenClient = tokenClient;
    }

    // Trả JSON token response. Không log/serialize raw token tùy tiện.
    JsonNode awaitToken(DeviceSession session) throws InterruptedException {
        if (session.expiresInSeconds() <= 0) {
            throw new IllegalArgumentException("Invalid device code TTL");
        }

        long ttlNanos = TimeUnit.SECONDS.toNanos(
            session.expiresInSeconds());
        long startedAt = System.nanoTime();
        long intervalSeconds = session.intervalSeconds() == null
            ? 5L : Math.max(1L, session.intervalSeconds());
        boolean first = true;

        while (!Thread.currentThread().isInterrupted()) {
            long remainingNanos = ttlNanos
                - (System.nanoTime() - startedAt);
            if (remainingNanos <= 0) {
                throw new IllegalStateException("device_code expired");
            }

            // Poll đầu tiên có thể gửi ngay sau khi hiển thị chỉ dẫn.
            // Các lần sau phải đợi tối thiểu interval hiện tại.
            if (!first) {
                long waitNanos = TimeUnit.SECONDS.toNanos(intervalSeconds);
                if (waitNanos >= remainingNanos) {
                    throw new IllegalStateException("device_code expired");
                }
                TimeUnit.NANOSECONDS.sleep(waitNanos);
            }
            first = false;

            if (System.nanoTime() - startedAt >= ttlNanos) {
                throw new IllegalStateException("device_code expired");
            }

            TokenHttpResponse result;
            try {
                result = tokenClient.pollOnce(session);
            } catch (ResourceAccessException networkError) {
                if (!causedByTimeout(networkError)) {
                    throw networkError; // Không retry mọi lỗi mạng/TLS.
                }
                // Backoff tăng gấp đôi, giới hạn tràn số.
                intervalSeconds = intervalSeconds > Long.MAX_VALUE / 2
                    ? Long.MAX_VALUE : intervalSeconds * 2;
                continue;
            }

            JsonNode body = result.body();
            if (body == null || !body.isObject()) {
                throw new IllegalStateException("Invalid token response");
            }

            if (result.httpStatus() >= 200
                    && result.httpStatus() < 300) {
                if (!body.hasNonNull("access_token")) {
                    throw new IllegalStateException("Missing access_token");
                }
                return body;  // Đã thành công: dừng hẳn polling.
            }

            String error = body.path("error").asText("");
            switch (error) {
                case "authorization_pending" -> {
                    // Không đổi interval, poll lại sau thời gian chờ.
                }
                case "slow_down" -> {
                    // RFC 8628: +5 giây cho các request tiếp theo.
                    intervalSeconds = intervalSeconds > Long.MAX_VALUE - 5
                        ? Long.MAX_VALUE : intervalSeconds + 5;
                }
                case "access_denied" ->
                    throw new IllegalStateException("User denied request");
                case "expired_token" ->
                    throw new IllegalStateException("device_code expired");
                default ->
                    throw new IllegalStateException(
                        "Device token request failed: " + error);
            }
        }
        throw new InterruptedException("Polling cancelled");
    }

    private boolean causedByTimeout(Throwable error) {
        for (Throwable cause = error;
                cause != null; cause = cause.getCause()) {
            if (cause instanceof SocketTimeoutException
                    || cause instanceof HttpTimeoutException) {
                return true;
            }
        }
        return false;
    }
}
~~~

**Phạm vi mẫu mã:**

- <code>RestClient</code>, <code>ObjectMapper</code>, <code>JsonNode</code>, <code>LinkedMultiValueMap</code> và <code>AuthorizationGrantType.DEVICE_CODE</code> là các thành phần thư viện; cần import/dependency đúng phiên bản. <code>HttpTimeoutException</code> thuộc <code>java.net.http</code>.
- Cần cấu hình HTTP timeouts, cancellation, nguồn endpoint, client authentication phù hợp, kiểm tra <code>token_type</code>/<code>expires_in</code>, lưu token an toàn và chính sách xử lý lỗi ứng dụng ở tầng gọi.
- Poller có thể chờ lâu; chạy bằng một worker/background task duy nhất cho mỗi device session. Nếu người dùng hủy, gọi <code>Future.cancel(true)</code> hoặc cơ chế hủy tương ứng và bảo đảm HTTP call cũng được hủy/timeout.
- Kể cả khi client theo đúng deadline, **Authorization Server là bên quyết định code đã hết hạn thật chưa**. Response thành công phải được xác minh theo hợp đồng token endpoint; không tin nội dung giả từ một URL không đúng issuer hoặc TLS không hợp lệ.
- Không dùng một retry interceptor tự động của HTTP client để retry request có status 400: nó có thể phá vỡ interval mà poller đã tính.

Đối với ứng dụng dùng nhiều device session đồng thời, nên có cấu trúc session state tách biệt theo phiên, không dùng biến global <code>deviceCode</code> hay <code>intervalSeconds</code> dùng chung. Đừng chạy nhiều poller cho **cùng device code**.

## 9. Cấu hình Spring Authorization Server để hỗ trợ Device Grant

### 9.1. Đăng ký client và TTL cho device code

Ví dụ public client cho TV:

~~~java
RegisteredClient tvClient = RegisteredClient.withId("tv-record-001")
    .clientId("living-room-tv")
    .clientAuthenticationMethod(ClientAuthenticationMethod.NONE)
    .authorizationGrantType(AuthorizationGrantType.DEVICE_CODE)
    .scope("media.read")
    .clientSettings(ClientSettings.builder()
        .requireAuthorizationConsent(true)
        .build())
    .tokenSettings(TokenSettings.builder()
        .deviceCodeTimeToLive(Duration.ofMinutes(10))
        .accessTokenTimeToLive(Duration.ofMinutes(15))
        .build())
    .build();
~~~

<code>ClientAuthenticationMethod.NONE</code> mô tả public client không có secret dùng để xác thực. <code>AuthorizationGrantType.DEVICE_CODE</code> đăng ký grant với giá trị URN của RFC 8628. <code>deviceCodeTimeToLive</code> cấu hình TTL do server phát hành; **khác với access token TTL**. Các thời hạn là ví dụ và cần cân nhắc trải nghiệm nhập code, tải polling, rủi ro bị tấn công và chính sách thực tế.

Nếu client có khả năng giữ secret riêng và được đăng ký là confidential client, cách xác thực ở token endpoint phải được cấu hình theo phương thức được phép. Không hard-code cùng một client secret vào hàng nghìn TV rồi coi đó là bí mật chỉ của một thiết bị.

**Đừng nhầm** <code>RegisteredClient.getId()</code> (ID nội bộ) với <code>clientId</code> (ID gửi trong form). Server phải gắn device authorization với đúng client đã đăng ký; public client ID có thể bị biết công khai nên chính **device_code**, trạng thái authorization và kiểm soát phía server phải có đủ entropy/bảo vệ phù hợp.

### 9.2. SecurityFilterChain và các endpoint

~~~java
@Bean
@Order(1)
SecurityFilterChain authorizationServerChain(HttpSecurity http)
        throws Exception {
    OAuth2AuthorizationServerConfigurer authorizationServer =
        OAuth2AuthorizationServerConfigurer.authorizationServer();

    http
        .securityMatcher(authorizationServer.getEndpointsMatcher())
        .with(authorizationServer, server -> server
            .deviceAuthorizationEndpoint(Customizer.withDefaults())
            .deviceVerificationEndpoint(Customizer.withDefaults()))
        .authorizeHttpRequests(authorize ->
            authorize.anyRequest().authenticated())
        .exceptionHandling(exceptions -> exceptions
            .defaultAuthenticationEntryPointFor(
                new LoginUrlAuthenticationEntryPoint("/login"),
                new MediaTypeRequestMatcher(MediaType.TEXT_HTML)));

    return http.build();
}
~~~

Đây là **khung cấu hình AS**. Ứng dụng còn cần các bean như <code>RegisteredClientRepository</code>, <code>OAuth2AuthorizationService</code>, <code>AuthorizationServerSettings</code>, user authentication, token generator, JWK/decoder nếu dùng JWT/OIDC và một chain Web/form login cho bước người dùng xác minh thiết bị.

Trong Spring Authorization Server:

- <code>OAuth2DeviceAuthorizationEndpointFilter</code> xử lý request tạo device/user code.
- <code>OAuth2DeviceVerificationEndpointFilter</code> xử lý người dùng nhập user code và consent.
- <code>OAuth2TokenEndpointFilter</code> nhận token polling request; phía sau có converter/provider xử lý device code grant như <code>OAuth2DeviceCodeAuthenticationConverter</code> và <code>OAuth2DeviceCodeAuthenticationProvider</code> ở những phiên bản hỗ trợ.
- <code>OAuth2AuthorizationService</code> lưu/truy xuất trạng thái liên quan device authorization, token và quyết định của flow.

Không xây một controller <code>/oauth2/token</code> riêng chỉ để poll khi đã dùng Spring Authorization Server. Bỏ qua filter/provider của framework có thể khiến client binding, code TTL, trạng thái consent và phát hành token không được kiểm tra đầy đủ.

### 9.3. Endpoint settings và issuer

~~~java
@Bean
AuthorizationServerSettings authorizationServerSettings() {
    return AuthorizationServerSettings.builder()
        .issuer("https://auth.example.com")
        .deviceAuthorizationEndpoint("/oauth2/device_authorization")
        .deviceVerificationEndpoint("/oauth2/device_verification")
        .tokenEndpoint("/oauth2/token")
        .build();
}
~~~

Ví dụ dùng các path thông thường để minh họa. Khi thay đổi endpoint, cập nhật cả client, reverse proxy, metadata và kiểm thử; **không suy ra token endpoint bằng cách nối chuỗi**. Issuer phải là URL công khai ổn định mà Resource Server/client tin cậy. Với reverse proxy cần xử lý forwarded headers từ nguồn đáng tin.

### 9.4. Storage trong môi trường nhiều instance

In-memory authorization service phù hợp học/test, nhưng khi có hai node, một node tạo device code còn node khác nhận polling thì không thể mong state đồng nhất nếu mỗi node dùng kho riêng.

Với hệ thống vận hành thực tế, cân nhắc <code>JdbcOAuth2AuthorizationService</code> hoặc backend bền vững phù hợp, schema/migration đúng phiên bản, index cho tra cứu token, TTL cleanup, transaction và các kiểm soát atomic cho chuyển từ pending sang approved/issued. Việc cấp access token thành công phải tránh **hai poll request đồng thời cùng sử dụng một device code để lấy hai token trái chính sách**.

## 10. Tại sao polling đúng interval là yêu cầu bảo mật và vận hành?

### 10.1. Client polling quá nhanh

Với 10.000 TV, nếu mỗi TV polling 20 lần/giây, token endpoint có thể nhận 200.000 request/giây chỉ cho một chức năng chờ người dùng duyệt. Khi mỗi TV chờ 5 giây, mức request trung bình khi ổn định giảm còn khoảng 2.000 request/giây. Đây là phép tính tải minh họa; lưu lượng thực phụ thuộc số thiết bị đang pending, thời gian sống của phiên và các đợt đồng bộ.

Máy chủ phải có rate limiting thích hợp và có thể trả <code>slow_down</code> khi cần. Client phải tuân thủ tín hiệu đó, không dùng retry HTTP của framework che giấu lịch polling.

### 10.2. Cơ chế chống abuse

Authorization Server nên kiểm soát:

| Rủi ro | Biện pháp |
| --- | --- |
| Đoán <code>user_code</code> | Mã có entropy phù hợp, thời hạn ngắn, giới hạn lượt nhập thử, chống enumeration và rate limit. |
| Đoán <code>device_code</code> | Device code khó đoán, lưu an toàn, không log, giới hạn request theo client/network/risk. |
| Poll nhanh quá mức | Lưu/giám sát nhịp polling nếu cần, trả <code>slow_down</code>, rate limit và áp dụng chính sách backend. |
| Dùng code của client khác | Xác minh device code thuộc đúng client/authorization đã tạo. |
| Code đã dùng lại | Chỉ một lần chuyển trạng thái thành công; từ chối reuse/race nếu policy yêu cầu. |
| Người dùng bị dẫn đến trang giả | Hiển thị chính xác HTTPS verification URI và tên ứng dụng; không tạo QR/link từ dữ liệu không tin cậy. |
| Kẻ tấn công lừa nạn nhân cấp quyền cho thiết bị của hắn | Trình duyệt verification hiển thị tên client, thiết bị/phiên nếu có, scope và xác nhận rõ ràng. |

Đặc biệt, **remote phishing** là rủi ro của Device Flow: kẻ tấn công có thể bắt đầu flow trên thiết bị của hắn rồi lừa người dùng khác nhập user code tương ứng. Việc người dùng nhập code trên website thật chưa đủ chứng minh người đó định cấp quyền cho **đúng thiết bị**. Giao diện verification/consent nên cho người dùng kiểm tra client/thiết bị đang liên kết và cảnh báo khi họ không tự khởi tạo thao tác.

### 10.3. Không thay cơ chế bảo mật bằng trạng thái UI

Một TV hiển thị “Đã kết nối” **không đủ** chứng minh token có thể dùng cho mọi API. Client phải nhận token response hợp lệ, kiểm tra token type, scope và lifetime, sau đó Resource Server tiếp tục xác minh access token, issuer, audience, thời hạn và quyền truy cập tài nguyên.

Ngược lại, UI điện thoại báo “Thành công” cũng không tự đẩy access token qua trình duyệt tới TV; chính token polling tiếp theo mới cho phép TV biết authorization đã được duyệt.

## 11. Hủy, hết hạn, mạng chập chờn và resume

### 11.1. Người dùng hủy trên TV trước khi có quyết định

Khi người dùng nhấn “Hủy” hoặc đóng màn hình:

1. Dừng scheduler/tác vụ polling và hủy HTTP request đang chờ nếu có thể.
2. Xóa <code>device_code</code> khỏi bộ nhớ của phiên, xóa user code khỏi màn hình.
3. Không tạo lại một flow mới tự động, trừ khi người dùng yêu cầu.
4. Nếu hệ thống cung cấp cơ chế hủy server-side đáng tin cậy, dùng theo chính sách; **RFC 8628 không định nghĩa một endpoint hủy device code bắt buộc**.

Việc dừng ở client **không tự đảm bảo** bản ghi pending được xóa ngay ở server; nó phải hết hạn theo TTL hoặc được xử lý bởi một quy trình hủy riêng.

### 11.2. Người dùng từ chối trên điện thoại

Token endpoint sẽ đưa trạng thái denial qua <code>access_denied</code> theo giao thức khi client poll. Client dừng và hiển thị thông báo rõ ràng. Không lén polling tiếp, không tự bật lại consent bằng device code mới.

### 11.3. Thiết bị mất mạng

Khi connection timeout, tăng interval và thử lại **trong cửa sổ TTL**, đồng thời thông báo UI “Đang chờ kết nối” nếu cần. Khi offline kéo dài vượt hạn, dừng. Đừng cộng thêm <code>expires_in</code> mỗi khi timeout như thể code được gia hạn.

Nếu đã nhận token thành công nhưng mất kết nối trước khi client đọc được response, server có thể đã đánh dấu device code là consumed. Client cần xử lý kết quả không chắc chắn: poll tiếp **sau backoff** có thể nhận lỗi do code đã dùng; không tự cho rằng lần trước chưa hề phát token. Đối với flow cần tính idempotency, hãy dựa vào semantics và khả năng của server; không “bỏ qua consumed check” để giải quyết.

### 11.4. Trạng thái sau restart và clock

Nếu muốn tiếp tục sau restart, cần thiết kế lưu trữ device code được mã hóa, deadline tin cậy, client ID, endpoint và trạng thái nhịp polling; giảm nguy cơ log/backup lộ bearer credential. Với thiết bị đơn giản, **hủy phiên cũ và yêu cầu bắt đầu lại** thường an toàn và dễ kiểm soát hơn.

## 12. Kiểm thử polling và token endpoint

### 12.1. Test state machine không cần chờ thật

Để kiểm thử chính xác lịch polling mà không dùng <code>Thread.sleep(5000)</code> trong unit test, tách ba thành phần:

1. <code>TokenTransport</code>: gửi request và trả response HTTP/JSON được fake trong test.
2. <code>Clock/Scheduler</code>: clock đơn điệu hoặc virtual time, có thể tiến thời gian chủ động.
3. <code>DeviceCodePoller</code>: state machine xử lý response, quyết định lúc nào được poll.

Mã sample ở phần 8 minh họa thuật toán blocking; khi đưa vào thư viện/test lớn, nên refactor để inject scheduler/clock. Các ca test mẫu:

~~~text
Given interval=5, expires_in=600
Responses:
  #1 authorization_pending
  #2 authorization_pending
  #3 slow_down
  #4 authorization_pending
  #5 success
Assert:
  Poll times >= [0, 5, 10, 20, 30] giây tính từ thời điểm bắt đầu
  Chỉ đúng một lần nhận token thành công; không request sau success
~~~

Không ghi các mốc <code>[0,5,10,20,30]</code> thành điều kiện bằng nhau nếu độ trễ mạng tồn tại; chỉ cần chứng minh **không nhanh hơn khoảng tối thiểu**. Nếu test mock response có thời gian xử lý, lịch có thể chậm hơn.

### 12.2. Ma trận giao thức cần có

| Trường hợp | Phản hồi hoặc hành vi mong đợi |
| --- | --- |
| Chưa nhận quyết định End-User | <code>authorization_pending</code>; client đợi interval rồi poll lại. |
| Không có <code>interval</code> trong response đầu | Client dùng mặc định **5 giây**. |
| Có <code>interval=8</code> | Client đợi tối thiểu **8 giây** giữa các lần poll. |
| Một <code>slow_down</code> sau interval 8 | Interval thành **13 giây** cho mọi lần sau. |
| Hai <code>slow_down</code> liên tiếp | Interval tăng thêm tổng cộng **10 giây** so với trước. |
| Connection timeout | Giảm tần suất, ví dụ exponential backoff; không retry tức thì. |
| Người dùng chấp thuận | Token endpoint trả token thành công; client dừng poll. |
| Người dùng từ chối | <code>access_denied</code>; dừng hoàn toàn với code đó. |
| <code>device_code</code> hết hạn ở server | <code>expired_token</code>; dừng và cho phép flow mới khi người dùng yêu cầu. |
| Local deadline hết trước lần poll kế | Không gửi request quá hạn. |
| Dùng <code>user_code</code> tại token endpoint | Bị từ chối; không cấp token. |
| Sai <code>grant_type</code> | Không được chấp nhận như device grant hợp lệ. |
| Public client thiếu <code>client_id</code> | Bị từ chối theo quy tắc RFC 8628. |
| Code được cấp cho client A, client B đem poll | Bị từ chối; không phát token cho client B. |
| Confidential client sai credential | Bị từ chối; không chỉ dựa vào client ID gửi trong body. |
| Code đã thành công rồi bị gửi lại | Không cấp lại token ngoài chính sách; bảo đảm one-time use. |
| Hai poll đồng thời từ cùng code | Không có hai lần phát hành thành công trái phép. |
| Scope bị thay ở request polling | Không được mở rộng quyền đã yêu cầu/consent. |
| AS trả 400 với <code>invalid_client</code> | Dừng; không retry vô hạn. |
| Server trả HTML/JSON không hợp lệ | Dừng an toàn hoặc thực hiện xử lý lỗi kết nối theo policy, không coi là pending. |
| Hủy trên thiết bị | Tác vụ polling được hủy; không tiếp tục phát request. |
| Session của người dùng ở verification page bị hết hạn | Người dùng cần xác thực lại theo server; thiết bị vẫn phải tôn trọng TTL/interval. |

### 12.3. Integration test Spring Authorization Server

Với <code>MockMvc</code> hoặc HTTP client thật, nên kiểm tra theo ba giai đoạn:

1. **Tạo phiên:** Đăng ký client test có <code>AuthorizationGrantType.DEVICE_CODE</code>, gửi <code>POST /oauth2/device_authorization</code>, lấy <code>device_code</code>, <code>user_code</code>, <code>expires_in</code>, <code>interval</code>.
2. **Pending:** Gửi <code>POST /oauth2/token</code> với grant URN, device code và client ID phù hợp. Kiểm tra response lỗi pending và state trong <code>OAuth2AuthorizationService</code> chưa bị cấp quyền.
3. **Người dùng duyệt:** Thực hiện login/verification/consent qua chain UI thật hoặc setup trạng thái authorized có kiểm soát ở integration test, rồi poll sau interval; xác minh access token được phát hành, giới hạn scope và không dùng lại code thành công.

Ví dụ một assertion khi còn pending (giả định test đã tạo <code>deviceCode</code> hợp lệ):

~~~java
mockMvc.perform(post("/oauth2/token")
        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
        .param("grant_type",
            AuthorizationGrantType.DEVICE_CODE.getValue())
        .param("device_code", deviceCode)
        .param("client_id", "living-room-tv"))
    .andExpect(status().isBadRequest())
    .andExpect(jsonPath("$.error")
        .value("authorization_pending"));
~~~

Đây là **đoạn test mẫu**, chỉ đúng nếu public client, chain và registered client được cấu hình phù hợp; phải lấy code từ một device authorization request thực trong test. Nếu framework/phiên bản bổ sung kiểm tra đặc thù, điều chỉnh fixture cho đúng, không bỏ qua bảo mật chỉ để test xanh.

### 12.4. Kiểm thử tải và khả năng sống sót khi nhiều node

Một hệ thống hàng nghìn TV cần kiểm thử:

- Nhiều clients bắt đầu phiên cùng lúc: server chịu được rate, không ghi log credential, giới hạn tài nguyên.
- Một device code được tạo ở node A nhưng poll vào node B: sử dụng kho authorization chung.
- Chuyển trạng thái pending → approved và poll xảy ra đồng thời: phát token chính xác một lần.
- Thay đổi <code>slow_down</code> ở server: client giảm tần suất; không có retry interceptor phá giới hạn.
- Code bị brute force hoặc nhiều IP poll một code: giới hạn và cảnh báo, không lộ quyết định của người dùng.
- Rolling deploy/restart: phiên đang chờ không mất nếu dùng storage bền vững đã thiết kế; hoặc hành vi mất phiên được tài liệu hóa.

## 13. Những lỗi triển khai thường gặp

### Lỗi 1: Poll mỗi 100 ms cho “cảm giác realtime”

RFC 8628 yêu cầu tuân thủ <code>interval</code>; một TV polling quá nhanh sẽ tạo tải không cần thiết và dễ gặp rate limiting. UI có thể hiển thị animation/progress cục bộ mà không tăng tần suất HTTP.

### Lỗi 2: Nhận <code>slow_down</code> nhưng chỉ ngủ 5 giây một lần

Nếu interval ban đầu là 5 và server trả <code>slow_down</code>, lần sau phải chờ **10 giây**, rồi giữ ít nhất 10 giây cho các lần tiếp theo; lần slow_down tiếp theo thành 15 giây. Không quay lại 5 khi gặp <code>authorization_pending</code>.

### Lỗi 3: Nhầm <code>user_code</code> với <code>device_code</code>

<code>user_code</code> để người dùng nhập trên browser; <code>device_code</code> để client trình tại token endpoint. Đưa user code vào token polling không hợp lệ và có thể tăng rủi ro nếu bắt đầu log mã bí mật.

### Lỗi 4: Xử lý mọi HTTP 400 là “đang chờ”

Trong Device Flow, HTTP 400 có thể biểu diễn <code>authorization_pending</code>, <code>slow_down</code>, <code>access_denied</code>, <code>expired_token</code> hoặc lỗi client nghiêm trọng. Phải parse JSON <code>error</code> và quyết định đúng nhánh; chỉ hai mã đầu là điều kiện tiếp tục polling.

### Lỗi 5: Retry tự động với cùng device code sau khi hết hạn

Khi hết TTL hoặc nhận <code>expired_token</code>, dừng. Nếu người dùng muốn thử lại, **khởi tạo một Device Authorization Request mới** để nhận cặp device/user code mới; không tái sử dụng code cũ.

### Lỗi 6: Không giới hạn request đồng thời

Hai background workers dùng chung device code có thể poll cùng lúc, tăng tải và tạo race khi server vừa phát token. Thiết kế một poller/session và dùng atomic state khi nhận success; backend phải chống reuse.

### Lỗi 7: Xem <code>ClientAuthenticationMethod.NONE</code> là hoàn toàn không cần kiểm tra

Public client không giữ secret nhưng vẫn phải có <code>client_id</code> đăng ký, device code hợp lệ, liên kết client–authorization, trạng thái End-User, scope hợp lệ và policy kiểm soát. Không trao device code hoặc access token cho client khác chỉ vì cả hai đều public.

### Lỗi 8: Dùng <code>verification_uri_complete</code> cho mọi mục đích

<code>verification_uri_complete</code> giúp tạo QR/deep link, **không** phải URL để gửi device code đến token endpoint hay đường dẫn hoàn tất authorization trên TV. Khi hiển thị QR, cần tránh remote phishing, kiểm tra hostname và bảo vệ người dùng trước các yêu cầu không do mình chủ động bắt đầu.

### Lỗi 9: Bỏ qua thời hạn và trạng thái khi server có nhiều node

Nếu device code được tạo tại node A nhưng node B không tìm thấy do dùng kho in-memory riêng, polling có thể liên tục lỗi. Chọn kho dùng chung và transaction đúng cho production, hoặc xác định rõ giới hạn chỉ dùng một node trong demo.

## 14. Checklist production

| Lĩnh vực | Kiểm tra |
| --- | --- |
| Chuẩn giao thức | Grant URN, tham số form, endpoint đúng và HTTPS. |
| Polling interval | Mặc định 5 giây nếu thiếu, không gửi quá nhanh, tôn trọng <code>slow_down</code>. |
| Deadline | Dùng TTL từ <code>expires_in</code> với đồng hồ monotonic; không poll sau hạn. |
| Xử lý lỗi | Pending/slow_down được retry; denied/expired/lỗi khác phải dừng. |
| Network resilience | Exponential backoff khi timeout; TLS lỗi phải được xử lý an toàn. |
| Client registration | Có quyền device grant, đúng client ID/authentication method/scope. |
| Credential security | Device code và token không lộ trong URL, log, analytics, crash report hay backup không bảo vệ. |
| Server storage | Trạng thái device authorization, user verification, consent và token nhất quán nhiều node. |
| One-time issuance | Chống race và reuse device code khi đã phát hành thành công. |
| Abuse protection | Rate limit tại verification, device code endpoint và token polling. |
| UX | Hiển thị URL/code rõ, trạng thái chờ, nút hủy, hướng dẫn khi hết hạn và cảnh báo phishing. |
| Audit/monitoring | Theo dõi tỷ lệ pending/denied/expired, slow_down, latency, số active sessions và unusual rates. |
| Testing | Virtual-time state tests, HTTP integration tests, multi-node, concurrency, cancellation và timeout. |

## 15. Bài tập tự thực hành

Bạn đang phát triển ứng dụng trên smart TV cho dịch vụ đọc thư viện nội bộ. TV có <code>client_id=library-tv</code>; người dùng cấp <code>books.read</code> bằng điện thoại. Authorization Server có ba instance Spring Boot phía sau load balancer, và Device Authorization Response trả <code>expires_in=420</code>, <code>interval=7</code>.

1. Viết HTTP request tạo device code, phân biệt dữ liệu hiển thị cho người dùng và dữ liệu cần giữ bí mật.
2. Viết token polling request với grant URN chính xác, <code>device_code</code> và <code>client_id</code>. Giải thích vì sao TV không gửi <code>user_code</code> đến token endpoint.
3. Vẽ lịch polling khi ba response đầu lần lượt là <code>authorization_pending</code>, <code>slow_down</code>, <code>authorization_pending</code>. Xác định interval mới cho lần tiếp theo.
4. Với <code>interval=7</code> nhưng request gặp connection timeout, đề xuất exponential backoff và thời điểm dừng khi TTL còn rất ít.
5. Thiết kế state machine có trạng thái pending, slow down, authorized, denied, expired, cancelled, failed. Không cho retry sau <code>access_denied</code>.
6. Viết <code>RegisteredClient</code> cho public TV với <code>AuthorizationGrantType.DEVICE_CODE</code> và <code>TokenSettings.deviceCodeTimeToLive(...)</code>; chỉ ra phần cấu hình AS chain.
7. Giải thích backend cần lưu gì để node A tạo code, node B nhận polling và node C xử lý người dùng xác minh.
8. Thiết kế integration test cho hai poll request đồng thời ngay sau khi user chấp thuận, bảo đảm không phát token lặp trái chính sách.
9. Đề xuất cách bảo vệ người dùng khi một kẻ tấn công gửi cho họ URL và user code thuộc thiết bị của kẻ tấn công.
10. Viết test virtual-time kiểm tra client không nhanh hơn interval, tăng 5 giây mỗi lần slow_down và dừng ngay khi nhận token.

**Kết quả mong đợi:** Một thiết kế đúng phải chứng minh được **device code là credential gắn với phiên ủy quyền**, **polling tuân thủ RFC 8628**, **không có token trước khi End-User chấp thuận**, và **không tiếp tục hỏi token sau khi đã thành công, bị từ chối hoặc hết hạn**.

## 16. Tài liệu đối chiếu

- [RFC 8628 — OAuth 2.0 Device Authorization Grant](https://www.rfc-editor.org/rfc/rfc8628): toàn bộ giao thức, đặc biệt §3.2 (response), §3.4 (token request), §3.5 (polling và errors), §5 (security).
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): token endpoint, client authentication và response/errors.
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414): công bố device authorization endpoint và grant types qua metadata.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): quản lý token và bảo vệ các luồng OAuth 2.0.
- [Spring Authorization Server — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html): Device Authorization/Verification Endpoint, Token Endpoint và các filter/configurer.
- [Spring Authorization Server — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html): Java DSL, endpoint settings và issuer.
- [Spring Authorization Server — Core Model Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): <code>RegisteredClient</code>, <code>OAuth2Authorization</code> và lưu trữ authorization.
- [Spring Authorization Server — TokenSettings API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/settings/TokenSettings.html): <code>deviceCodeTimeToLive</code> và các token lifetime settings.
- [Spring Security — Authorization Server (phiên bản mới)](https://docs.spring.io/spring-security/reference/servlet/oauth2/authorization-server/): hướng dẫn tích hợp Authorization Server trong nhánh Spring Security mới hơn.
