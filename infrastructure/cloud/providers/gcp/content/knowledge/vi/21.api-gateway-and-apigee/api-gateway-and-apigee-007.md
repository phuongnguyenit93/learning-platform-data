# Apigee policies cho xác thực và quản lý lưu lượng

Một nền tảng học trực tuyến cung cấp API tra cứu khóa học cho đối tác. Nếu mọi request đi thẳng tới backend, một API key bị lộ có thể bị khai thác để gọi hàng nghìn lần mỗi giây; ngược lại, một đối tác hợp lệ cũng có thể vô tình dùng hết tài nguyên khi chạy batch. **Apigee** cho phép đặt các **policies** trên API proxy để nhận diện client, kiểm soát quyền gọi API, làm mượt tải đột biến và giới hạn lượng sử dụng theo ứng dụng.

Trong chương **API Gateway và Apigee** thuộc module **CLOUD_PROVIDERS_GCP**, bài học này tập trung vào cấu hình và vận hành policy trong Apigee, liên hệ IAM, VPC, Cloud Run/GKE backend, logging, SLO và chi phí. Khác với Google Cloud **API Gateway**, Apigee cung cấp hệ sinh thái API products, developer apps và những policy có thể kết hợp ngay trong các luồng xử lý proxy. Không nên sao chép XML policy Apigee vào API Gateway rồi kỳ vọng hai sản phẩm dùng cùng cấu hình.

**Sau bài học, bạn có thể:**

1. Chọn giữa `VerifyAPIKey`, `OAuthV2` và `VerifyJWT` theo cơ chế danh tính và loại token.
2. Gắn policy vào `ProxyEndpoint`/`TargetEndpoint`, kiểm soát thứ tự thực thi và điều kiện của flow.
3. Phân biệt `SpikeArrest` (kiểm soát tốc độ/burst) với `Quota` (hạn mức sử dụng theo kỳ).
4. Thiết kế đếm theo app/API product thay vì dùng chung một counter không chủ đích.
5. Kiểm thử request hợp lệ, thiếu/sai credential, vượt giới hạn, lỗi backend và xử lý lỗi không lộ bí mật.
6. Theo dõi số liệu, thay đổi giới hạn và có phương án rollback khi bảo vệ API thực tế.

## 1. Policy nằm ở đâu trong đường đi của request?

**API proxy** là lớp tiếp nhận request của client, áp dụng các bước xử lý rồi chuyển tới **target** (ví dụ Cloud Run, GKE hoặc backend tự vận hành). Policy có thể xác thực, thay đổi header, định tuyến, giới hạn tải và tạo phản hồi lỗi trước khi backend nhận request.

~~~mermaid
flowchart LR
    CLIENT["Đối tác / ứng dụng"] --> ENTRY["Apigee API proxy"]
    ENTRY --> AUTH["VerifyAPIKey hoặc<br/>OAuthV2 / VerifyJWT"]
    AUTH --> SPIKE["SpikeArrest<br/>chặn đột biến"]
    SPIKE --> QUOTA["Quota<br/>hạn mức theo app"]
    QUOTA --> TARGET["Backend Cloud Run / GKE"]
    TARGET --> CLIENT
~~~

Sơ đồ minh họa **một phương án**; không phải proxy nào cũng phải áp **cả ba** cơ chế API key, OAuth và JWT. Chọn một hoặc nhiều cơ chế dựa trên hợp đồng bảo mật thực tế, sau đó bảo đảm request không có quyền **không thể đi nhầm vào một flow được bỏ qua xác thực**.

### 1.1. Đường thực thi trong Apigee

Một API proxy có **ProxyEndpoint** (phía client) và thường có **TargetEndpoint** (phía backend). Trên mỗi endpoint, những phần chính gồm:

| Thành phần | Thời điểm | Ví dụ |
| --- | --- | --- |
| `PreFlow/Request` của ProxyEndpoint | Đầu luồng request tại gateway | Verify credential, áp SpikeArrest/Quota. |
| Conditional `Flow` | Chỉ chạy khi điều kiện của flow khớp | Yêu cầu scope riêng cho `POST /orders`. |
| `PostFlow/Request` | Sau conditional request flows | Xử lý header, bước chung còn cần trước khi đi target. |
| `TargetEndpoint` request/response | Xử lý giao tiếp với backend | Xác thực tới backend, chuyển đổi request/response. |
| `PostFlow/Response` và fault handling | Trả kết quả cho client | Header, log, lỗi đã chuẩn hóa. |

Với nhiều conditional flows cùng khớp, **flow đầu tiên** theo thứ tự có điều kiện đúng được thực thi trong phân đoạn đó. Vì vậy thứ tự và vị trí policy là một phần của thiết kế an toàn, không chỉ là vấn đề tổ chức XML.

### 1.2. Thứ tự đặt policy ảnh hưởng cả bảo mật lẫn quota

Phương án thông dụng cho API đối tác dựa trên API key:

1. **VerifyAPIKey:** chỉ tiếp tục khi key hợp lệ và app có quyền với API product/resource.
2. **SpikeArrest:** chặn tốc độ request tức thời; khi cần per-client, lấy ID từ **danh tính đã xác minh**.
3. **Quota:** trừ hạn mức theo app/product với bộ đếm đã xác định.
4. **AssignMessage/biện pháp tương đương:** gỡ client credential khỏi request chuyển xuống backend nếu backend không cần.
5. **Route to target:** gọi backend có cơ chế xác thực riêng nếu backend là dịch vụ private.

Nếu SpikeArrest/Quota chạy **trước** khi xác thực, một header `client-id` do người gọi tự đặt có thể làm sai cách gom nhóm counter hoặc khiến request vô danh tiêu thụ quota của khách hàng khác. Nếu cần bảo vệ gateway **trước cả authentication** khỏi một đợt flood rất lớn, có thể đặt một lớp giới hạn tổng riêng trước VerifyAPIKey, nhưng phải xem đó là **bộ đếm chung**, không phải hạn mức theo app đã xác minh.

### 1.3. API product và developer app

Trong Apigee, người quản trị tạo **API product** xác định API proxy/resource/operation mà một đối tác được dùng. Developer đăng ký **developer app**, ứng dụng liên kết với một hoặc nhiều API products và nhận API key. `VerifyAPIKey` kiểm tra key, trạng thái app và quyền đối với sản phẩm API, từ đó có thể cung cấp các **flow variables** cho bước quota/routing phía sau.

**Đừng nhầm API key với tài khoản người dùng cuối.** Key chủ yếu nhận diện ứng dụng/đối tác được đăng ký; nếu thao tác yêu cầu quyền của từng học viên hoặc nhân viên, phải có xác thực và phân quyền ở mức người dùng (OIDC/OAuth, scope/claim và logic nghiệp vụ).

## 2. Ba cách xác thực phổ biến

### 2.1. `VerifyAPIKey`: xác minh ứng dụng và API product

Ví dụ Apigee policy nhận key qua header riêng:

~~~xml
<VerifyAPIKey name="VAK-Partner">
  <APIKey ref="request.header.x-api-key"/>
</VerifyAPIKey>
~~~

Client minh họa:

~~~bash
# Dùng API key của ứng dụng LAB đã được đăng ký và phê duyệt
curl --fail-with-body --silent --show-error \
  -H "x-api-key: $LAB_API_KEY" \
  "https://API_PROXY_HOST/partner/v1/courses"
~~~

Không đưa key vào query string vì có thể bị ghi trong browser history, analytics, reverse-proxy logs. Ngay cả với header, log request vẫn có thể lưu key nếu bạn ghi toàn bộ headers; phải có **redaction**. API key không được coi là bằng chứng danh tính một **người dùng** cụ thể.

Khi `VAK-Partner` thành công, Apigee tạo biến như `verifyapikey.VAK-Partner.client_id`. Có thể dùng nó để gắn quota theo **key đã được xác minh**, thay vì tin header `client-id` tùy ý từ client.

### 2.2. `OAuthV2`: xác minh access token do Apigee quản lý

Khi proxy sử dụng OAuth access token được Apigee phát hành/quản lý, policy sau kiểm tra token trong `Authorization: Bearer ...`:

~~~xml
<OAuthV2 name="OA-VerifyAccessToken">
  <Operation>VerifyAccessToken</Operation>
</OAuthV2>
~~~

Thông thường gắn policy này tại request PreFlow của API được bảo vệ. Khi cấu hình `Scope`, cần hiểu semantics cụ thể: nhiều scope nằm trong **một** thẻ `<Scope>READ WRITE</Scope>` của VerifyAccessToken được xem theo logic **OR** (có ít nhất một scope), không tự hiểu là cần cả hai. Nếu nghiệp vụ yêu cầu **AND**, thiết kế kiểm tra riêng phù hợp.

**Không dùng `OAuthV2/VerifyAccessToken` để mặc định xác minh mọi JWT access token từ Identity Provider bên ngoài.** Token bên ngoài có thể cần `VerifyJWT` (JWT ký), policy xác thực OAuth/JWT chuyên biệt hoặc introspection (opaque token) qua service được tin cậy. Trước khi chọn, xác định **ai phát hành token** và **ai có thể xác minh nó**.

### 2.3. `VerifyJWT`: kiểm tra chữ ký và claims của JWT

Với OIDC/JWT access token được ký bằng RS256 từ một issuer đáng tin cậy, một ví dụ cấu hình:

~~~xml
<VerifyJWT name="VJWT-Partner">
  <Algorithm>RS256</Algorithm>
  <PublicKey>
    <JWKS uri="https://ISSUER_HOST/.well-known/jwks.json"/>
  </PublicKey>
  <Issuer>https://ISSUER_HOST/</Issuer>
  <Audience>https://api.example.com/partner</Audience>
</VerifyJWT>
~~~

Đây là **mẫu cần thay bằng issuer/JWKS/audience thực tế**, không phải policy sẵn dùng. Khi không có thẻ `<Source>`, `VerifyJWT` lấy token từ header `Authorization` và tự loại tiền tố `Bearer`. Nếu chỉ định `<Source>request.header.authorization</Source>`, policy **không tự gỡ tiền tố** đó, dễ khiến token bị từ chối — một khác biệt quan trọng với mặc định.

Ngoài chữ ký và `exp`/`nbf`, nên kiểm tra **issuer, audience, thuật toán, key rotation**, scope/claim cần thiết và ánh xạ quyền nghiệp vụ. Chỉ giải mã phần payload JWT hoặc thấy một chuỗi có dạng JWT **không phải xác thực**. JWKS qua URL có cơ chế cache; có thể có độ trễ khi issuer thay đổi khóa, cần thử chu kỳ rotation.

### 2.4. So sánh để tránh dùng sai

| Phương án | Xác nhận điều gì? | Phù hợp | Giới hạn cần nhớ |
| --- | --- | --- | --- |
| VerifyAPIKey | Key và quyền app/API product | API đối tác, nhận diện consumer app | Không tự định danh người dùng cuối; key có thể bị chia sẻ/lộ. |
| OAuthV2 VerifyAccessToken | Access token theo cơ chế OAuthV2 Apigee | API dùng OAuth tokens do Apigee quản lý | Token của issuer khác phải có chiến lược xác minh tương thích. |
| VerifyJWT | Chữ ký JWT, hạn và claims cấu hình | JWT từ Identity Provider tin cậy | Không mặc định kiểm tra mọi quyền nghiệp vụ hoặc revocation tức thời. |
| Backend authorization | Quyền cụ thể của user/tenant với tài nguyên | Mọi API có dữ liệu nhạy cảm | Gateway auth không thay thế kiểm soát truy cập theo bản ghi. |

Các policy an ninh có thể thuộc nhóm **Standard** hoặc **Extensible** và ảnh hưởng đến licensing/chi phí theo Apigee edition. Trước triển khai rộng, kiểm tra policy availability/entitlement của organization đang sử dụng.

## 3. `SpikeArrest`: bảo vệ backend khỏi đột biến lưu lượng

`SpikeArrest` đặt ngưỡng request theo **giây** (`ps`) hoặc **phút** (`pm`), nhằm giảm burst gây nghẽn backend. Đây là kiểm soát **tốc độ ngắn hạn**, không phải hạn mức kinh doanh kiểu “100.000 lời gọi/tháng”.

### 3.1. Ví dụ 10 request/giây cho mỗi client đã xác minh

~~~xml
<SpikeArrest name="SA-Partner">
  <Identifier ref="verifyapikey.VAK-Partner.client_id"/>
  <Rate>10ps</Rate>
  <UseEffectiveCount>true</UseEffectiveCount>
</SpikeArrest>
~~~

Ý nghĩa:

- `<Rate>10ps</Rate>`: ngưỡng 10 request/giây; không có nghĩa backend luôn được phép nhận chính xác 10 request trong **mọi** cửa sổ 1 giây do thuật toán và phân phối tải.
- `<Identifier .../>`: tách hạn mức theo **API key đã được VerifyAPIKey xác minh**. Bỏ Identifier thì có thể tạo giới hạn chung cho toàn proxy.
- `<UseEffectiveCount>true</UseEffectiveCount>`: dùng cơ chế đếm hiệu quả/đồng bộ được khuyến nghị cho Apigee; với Apigee production, **không nên để `false`** chỉ vì thấy một ví dụ cũ dùng thuật toán smoothing.

**Thứ tự bắt buộc của ví dụ:** `VAK-Partner` phải chạy trước `SA-Partner`, nếu không biến `verifyapikey.VAK-Partner.client_id` chưa có. Nếu thiết kế bảo vệ nhiều loại API (JWT, API key, guest traffic), phải xác định identifier đúng cho từng nhánh thay vì tái sử dụng một biến rỗng.

### 3.2. Phân biệt per-client limit và global limit

| Mục tiêu | Cấu hình khái niệm | Hệ quả |
| --- | --- | --- |
| Bảo vệ toàn backend | SpikeArrest không có `Identifier` | Mọi consumer chia sẻ một mức ngưỡng; một consumer có thể ảnh hưởng các consumer khác. |
| Bảo vệ từng đối tác | `Identifier` = client ID đã xác minh | Mỗi đối tác có ngưỡng riêng, giảm tranh chấp giữa các app. |
| Bảo vệ từng tuyến quan trọng | Đặt policy riêng hoặc conditional flow theo path/method | Không áp một ngưỡng cứng cho cả GET nhẹ và POST nặng. |
| Phân biệt gói service | `Rate ref` lấy giá trị từ cấu hình **đáng tin**, như API product/KVM được quản lý | Không cho khách hàng tự khai `rate=100000ps` rồi dùng trực tiếp. |

**SpikeArrest không thay thế** Cloud Armor/WAF, bảo vệ hạ tầng, cân bằng tải, autoscaling hoặc circuit breaker. Một lượng nhỏ request nhưng tốn nhiều CPU vẫn có thể gây quá tải; cần đánh giá cost-per-request, timeout và cơ chế backpressure ở backend.

### 3.3. Mối quan hệ với độ trễ

Nếu backend xử lý tối đa 50 RPS ổn định, việc đặt SpikeArrest 100ps cho một app không chắc an toàn. Giới hạn nên dựa trên **load test** có latency p95/p99, số request đồng thời, kích thước payload và số khách hàng hoạt động.

Ví dụ có ba partner, mỗi partner được 10ps: tổng lý thuyết có thể tới **30ps** chưa kể nguồn khác. Muốn giới hạn tổng backend còn 20ps, cần lớp bảo vệ tổng riêng cùng với kiểm soát per-client; việc đặt ba giới hạn per-client không tự tạo một global cap.

## 4. `Quota`: giới hạn mức sử dụng theo kỳ

`Quota` quản lý lượng request đã sử dụng trong **cửa sổ thời gian**. Nó phù hợp hợp đồng API product như “1.000 lời gọi/giờ theo app” hoặc “100.000 lời gọi/ngày”, có counter để phục vụ báo cáo và từ chối những request vượt quota.

### 4.1. Ví dụ giới hạn 1.000 request/giờ theo client

~~~xml
<Quota name="Q-PartnerHour">
  <Identifier ref="verifyapikey.VAK-Partner.client_id"/>
  <Allow count="1000"/>
  <Interval>1</Interval>
  <TimeUnit>hour</TimeUnit>
</Quota>
~~~

Trong ví dụ, mỗi `client_id` đã qua VerifyAPIKey có quota riêng. Nếu **bỏ** `Identifier`, policy có thể dùng một counter chung cho proxy thay vì counter theo từng đối tác. Không dùng `request.queryparam.partner` chưa xác thực làm identifier, vì client có thể đổi giá trị đó để tránh quota.

**Thời điểm reset** phụ thuộc loại quota và quy tắc đếm của Apigee; không mặc định “mọi counter đều reset lúc 00:00 UTC” nếu chưa chọn rõ kiểu calendar và `StartTime`. Với nhu cầu tính tiền hoặc hạn mức hợp đồng phức tạp, phải thống nhất **cửa sổ thời gian, đơn vị đếm, thao tác được tính và chính sách retry** trước khi triển khai.

### 4.2. Quota theo API product

Apigee cho phép khai báo quota trên **API product** hoặc **operation**; khi muốn chính sách sử dụng cấu hình đó, `Quota` có thể tham chiếu policy xác thực đã chạy trước:

~~~xml
<Quota name="Q-FromProduct">
  <UseQuotaConfigInAPIProduct stepName="VAK-Partner">
    <DefaultConfig>
      <Allow>1000</Allow>
      <Interval>1</Interval>
      <TimeUnit>day</TimeUnit>
    </DefaultConfig>
  </UseQuotaConfigInAPIProduct>
</Quota>
~~~

`DefaultConfig` chỉ là **fallback khi API product không định nghĩa mức quota tương ứng**. Với cấu hình theo operation, quy tắc ưu tiên và **counter scope** (`PRODUCT`/`PROXY`) phải được xác định trong API product; có thể xuất hiện **counter độc lập theo operation**, không phải một bucket tổng chung như người vận hành tưởng.

Đừng vô tình chạy **cả `Q-PartnerHour` và `Q-FromProduct`** trên cùng request nếu ý định chỉ là một quota duy nhất: hai policy có thể đếm hai giới hạn khác nhau. Chọn một mô hình theo hợp đồng API và kiểm tra rõ thao tác nào làm tăng counter.

### 4.3. Quota và SpikeArrest khác nhau thế nào?

| Tiêu chí | SpikeArrest | Quota |
| --- | --- | --- |
| Mục tiêu | Chặn burst/tốc độ cao trong khoảng ngắn | Giới hạn tổng sử dụng theo kỳ |
| Ngưỡng | `10ps`, `100pm` | `1000/hour`, `100000/day` |
| Đếm theo ai? | Toàn proxy hoặc `Identifier` | Counter theo proxy/app/product/operation tùy cấu hình |
| Vượt giới hạn | Trả fault ngay, thường được ánh xạ thành **429** | Từ chối khi hết quota, thường được ánh xạ thành **429** |
| Phù hợp | Bảo vệ latency và capacity backend | SLA/hợp đồng với developer, fair-use |
| Thay thế nhau? | **Không** | **Không** |

Một đối tác dùng 1.000 request trong **một phút** có thể chưa vượt quota 10.000/ngày nhưng vẫn gây nghẽn backend; SpikeArrest giúp xử lý phần tức thời. Ngược lại, một app gọi đều 1 request/giây có thể không vượt SpikeArrest 10ps nhưng sẽ vượt quota 1.000/giờ sau đủ thời gian.

### 4.4. Flow variables phục vụ phản hồi hạn mức

Quota tạo các biến như:

~~~text
ratelimit.Q-PartnerHour.allowed.count
ratelimit.Q-PartnerHour.used.count
ratelimit.Q-PartnerHour.expiry.time
~~~

Có thể dùng `AssignMessage` để đặt các response headers thông báo hạn mức còn lại/thời điểm reset. Nhưng phải xác định ý nghĩa, độ mới và quy tắc định dạng header; **không** đưa flow variable chứa API key hoặc access token vào response. Counter và báo cáo analytics có thể có khác biệt do cách tính, phân phối và chính sách; không dùng log tự viết thay sổ tính phí nếu chưa kiểm chứng reconciliation.

## 5. Gắn các policy vào flow theo thứ tự an toàn

Ví dụ này chọn **một mô hình xác thực bằng API key**, SpikeArrest và quota theo app. Mỗi chính sách tồn tại dưới dạng file policy riêng, ví dụ:

~~~text
apiproxy/
  policies/
    VAK-Partner.xml
    SA-Partner.xml
    Q-PartnerHour.xml
    AM-StripKey.xml
  proxies/
    default.xml
~~~

**Trích đoạn** trong `ProxyEndpoint` (không phải toàn bộ API proxy bundle):

~~~xml
<PreFlow name="PreFlow">
  <Request>
    <Step><Name>VAK-Partner</Name></Step>
    <Step><Name>SA-Partner</Name></Step>
    <Step><Name>Q-PartnerHour</Name></Step>
    <Step><Name>AM-StripKey</Name></Step>
  </Request>
  <Response/>
</PreFlow>
~~~

Policy gỡ credential trước khi chuyển request về backend khi backend không cần chính header client key:

~~~xml
<AssignMessage name="AM-StripKey">
  <Remove>
    <Headers>
      <Header name="x-api-key"/>
    </Headers>
  </Remove>
  <AssignTo createNew="false" type="request"/>
</AssignMessage>
~~~

**Thứ tự xử lý** trong request PreFlow đi từ trên xuống: verify → spike → quota → strip. Mỗi policy có `name` khớp với `Step/Name`. Một policy XML được thêm vào bundle nhưng **không gắn vào flow** thì không tự chạy chỉ vì file tồn tại.

### 5.1. Không chạy một policy nhầm ở mọi endpoint

Nếu `GET /health` là endpoint kiểm tra nội bộ không yêu cầu API key, có thể tạo conditional step hoặc route riêng, nhưng phải:

1. Chỉ cho phép **đúng đường dẫn và method** đã được phê duyệt, không dùng pattern quá rộng như “bất kỳ path nào chứa health”.
2. Đảm bảo những endpoint có dữ liệu/quyền đều được bảo vệ trong **mọi flow phù hợp**.
3. Kiểm tra cả encoded path, query, trailing slash và route đến target; không để `/admin` vô tình đi qua nhánh health.
4. Bảo vệ health endpoint bằng ingress/network control nếu không định công khai.

Chỗ đặt policy là một phần **security review**. Dùng `continueOnError="false"` cho các policy xác thực/giới hạn chính yếu để không vô tình **fail open** khi policy trả lỗi.

### 5.2. Lớp bảo vệ backend vẫn cần thiết

Một API key hợp lệ tới proxy không có nghĩa target private Cloud Run/GKE sẽ tự chấp nhận request. Target có thể yêu cầu **ID token/service identity, mTLS, private network hoặc IAM** theo loại backend. Đó là một lớp khác, phải thiết kế trên **TargetEndpoint/service callout** hoặc mạng được hỗ trợ. Không mở Cloud Run backend công khai để “xử lý nhanh” lỗi xác thực trên proxy.

## 6. Trả lỗi nhất quán mà không tiết lộ thông tin nhạy cảm

Khi policy fail, Apigee chuyển sang fault handling theo cấu hình. Dùng `FaultRules` và `DefaultFaultRule` hoặc cơ chế chuẩn hóa lỗi được hỗ trợ để trả thông điệp nhất quán. Không đặt `continueOnError="true"` cho VerifyAPIKey/OAuth/VerifyJWT chỉ để endpoint tiếp tục phục vụ khi thiếu credential.

| Kịch bản | HTTP status thường chọn | Nội dung phản hồi nên thể hiện | Tránh |
| --- | --- | --- | --- |
| Không cung cấp/sai/expired credential | **401** | Yêu cầu xác thực không hợp lệ | In key/token, secret, stack trace hoặc config. |
| Principal hợp lệ nhưng không được phép với resource | **403** theo thiết kế authorization | Không đủ quyền gọi thao tác | Tiết lộ chính sách backend chi tiết. |
| Vượt SpikeArrest hoặc Quota | **429** | Đã vượt giới hạn; có thể retry theo hướng dẫn | Hứa thời gian reset sai hoặc yêu cầu retry liên tục. |
| Backend tạm quá tải | **503/502/504** tùy nguồn lỗi | Dịch vụ chưa sẵn sàng | Trả 401 khiến client liên tục đổi key. |
| Lỗi cấu hình policy, key store hoặc kết nối quản trị | Thường **5xx** | Mã lỗi nội bộ để theo dõi | Fail open hoặc báo nhầm “quota hết”. |

HTTP status thực tế phụ thuộc policy, fault variables và cách bạn ánh xạ lỗi; **không được suy rằng mọi policy violation luôn tự trả đúng JSON/status mong muốn**. Kiểm tra response thật ở môi trường thử nghiệm.

### 6.1. Mẫu cấu trúc phản hồi lỗi

Một API contract có thể dùng định dạng JSON thống nhất:

~~~json
{
  "error": {
    "code": "RATE_LIMIT_EXCEEDED",
    "message": "Yeu cau vuot qua gioi han cho phep",
    "requestId": "request-id-an-toan-de-tra-cuu"
  }
}
~~~

Có thể dùng `AssignMessage` để tạo body/status và `RaiseFault` trong những nhánh kiểm tra tự xây; khi xử lý lỗi do policy gốc, dùng FaultRules được kiểm tra theo đúng `fault.name`/`errorcode`. Trong production, giữ thông điệp không chứa policy XML, JWT claims nhạy cảm hoặc tham số kết nối backend.

Nếu cung cấp `Retry-After`, chỉ đặt sau khi bạn xác định được **thời gian có thể thử lại** theo loại lỗi/cửa sổ; retry có backoff và jitter tốt hơn việc client gọi đồng loạt ngay lúc reset quota.

### 6.2. Không để policy vô tình lộ API key

- Ưu tiên nhận key trong **header** và chỉ dùng **HTTPS**.
- Gỡ header key/token trước khi gửi target khi backend không cần (nếu backend cần danh tính đã xác thực, gửi **identity context do gateway tạo**, có cơ chế chống giả mạo, không tin header do client tự khai).
- Cấu hình debug/log redaction; không in toàn bộ request headers, query, body hoặc flow variables chứa secret.
- Hạn chế người được phép sử dụng **Apigee Debug** và truy cập các thông tin có thể xuất hiện trong trace.
- Khi key lộ, revoke/regenerate theo quy trình, thông báo owner app và kiểm tra hành vi bất thường.

## 7. Lab có kiểm soát: partner API được xác thực và giới hạn

**Mục tiêu:** trong Apigee **organization và environment lab đã được cấp**, bảo vệ một API proxy trỏ tới target mẫu; kiểm chứng đúng thứ tự VerifyAPIKey → SpikeArrest → Quota. Không tự tạo Apigee organization/network infrastructure trong bài này vì các tài nguyên đó có **điều kiện cấp phép, kết nối và chi phí** riêng.

### 7.1. Chuẩn bị

Cần có:

- Một organization, environment và environment group Apigee **thử nghiệm**, với hostname HTTPS định tuyến tới environment tương ứng.
- API proxy lab, backend HTTP có thể nhận request kiểm tra, ví dụ endpoint nội bộ trả `200 OK`; tuyệt đối không dùng backend production nhạy cảm.
- Quyền Apigee đủ để tạo/chỉnh policy và deploy proxy **ở environment lab**, tạo API product và developer app.
- Hai developer apps/keys **được phê duyệt** để kiểm tra tách counter theo consumer.
- Giao diện Apigee Proxy Editor hoặc quy trình CI/CD quản lý API proxy bundle; có khả năng xem Debug/analytics theo quyền.
- Giới hạn thử tải thấp; không tạo load test lớn ngoài hạn mức được duyệt.

Trước khi thay đổi, xác minh **đúng organization, environment, proxy revision và base path**. Nếu proxy đang có policy bảo mật, **không ghi đè**; tạo proxy lab riêng hoặc nhánh cấu hình có review.

### 7.2. Khởi tạo API product và developer app

Thực hiện trong UI hoặc quy trình quản lý tổ chức:

1. Tạo API product lab chỉ cho phép **proxy và resource path `/partner/v1/courses`** được định nghĩa.
2. Tạo developer/app A và developer/app B; liên kết từng app với API product, bảo đảm trạng thái **approved**.
3. Ghi nhận consumer key của từng app trong **secret store phù hợp**, không commit vào repo hoặc chia sẻ qua chat.
4. Nếu API product có cấu hình quota, ghi rõ **counter scope**, giới hạn và operation được tính; trong lab ban đầu dùng **Quota cố định** để dễ quan sát.

**Thử âm tính quan trọng:** dùng key của một app **không được cấp quyền cho API product/resource này** phải bị từ chối dù key ấy hợp lệ ở sản phẩm khác.

### 7.3. Cấu hình policy cho lab

Chọn ba policy trong request PreFlow:

**`VAK-Lab.xml`**

~~~xml
<VerifyAPIKey name="VAK-Lab">
  <APIKey ref="request.header.x-api-key"/>
</VerifyAPIKey>
~~~

**`SA-Lab.xml`**

~~~xml
<SpikeArrest name="SA-Lab">
  <Identifier ref="verifyapikey.VAK-Lab.client_id"/>
  <Rate>2ps</Rate>
  <UseEffectiveCount>true</UseEffectiveCount>
</SpikeArrest>
~~~

**`Q-Lab.xml`**

~~~xml
<Quota name="Q-Lab">
  <Identifier ref="verifyapikey.VAK-Lab.client_id"/>
  <Allow count="5"/>
  <Interval>1</Interval>
  <TimeUnit>minute</TimeUnit>
</Quota>
~~~

Gắn vào request PreFlow theo thứ tự:

~~~xml
<PreFlow name="PreFlow">
  <Request>
    <Step><Name>VAK-Lab</Name></Step>
    <Step><Name>SA-Lab</Name></Step>
    <Step><Name>Q-Lab</Name></Step>
  </Request>
  <Response/>
</PreFlow>
~~~

Đây là **những đoạn cấu hình policy/flow**, không phải một API proxy bundle đầy đủ có thể deploy độc lập. Cần cấu hình ProxyEndpoint/TargetEndpoint, route, hostname và revision phù hợp, dùng công cụ xác minh XML/policy theo Apigee trước khi deploy.

**Tại sao rate 2ps và quota 5/min?** Đó là giới hạn thấp để kiểm thử nhanh; không phải giá trị khuyến nghị cho production. SpikeArrest có thể từ chối một burst trước khi quota 5/min được dùng hết — vì vậy các phép thử **quota** phải gửi request chậm đủ để không chạm SpikeArrest.

### 7.4. Kiểm tra yêu cầu hợp lệ và lỗi credential

Đặt biến trong một shell của máy đã được phép gửi request tới hostname Apigee lab:

~~~bash
export API_BASE="https://YOUR_APIGEE_LAB_HOST/partner/v1"
export API_KEY_A="YOUR_LAB_APP_A_KEY"
export API_KEY_B="YOUR_LAB_APP_B_KEY"

# 1. Key A hợp lệ, giới hạn chưa dùng hết
curl --silent --show-error --include \
  -H "x-api-key: $API_KEY_A" \
  "$API_BASE/courses"

# 2. Thiếu key: phải bị từ chối
curl --silent --show-error --include "$API_BASE/courses"

# 3. Key sai: phải bị từ chối
curl --silent --show-error --include \
  -H "x-api-key: invalid-lab-key" \
  "$API_BASE/courses"
~~~

**Không chạy với key production** hoặc gắn command shell chứa key vào ticket/log. Các biến môi trường được minh họa cho lab; trên máy dùng chung phải bảo vệ shell history/process logs và xóa credential khi hoàn tất.

Kỳ vọng: request hợp lệ nhận phản hồi backend; request thiếu/sai key bị chặn ở gateway trước khi target xử lý. Kiểm chứng bằng **trace/Debug được ẩn secret** và backend access logs, không chỉ status code.

### 7.5. Kiểm tra quota và tách counter theo app

Với `Q-Lab` tối đa 5 request/phút, sau khi qua cửa sổ reset và không có traffic khác dùng key A:

~~~bash
# Gửi chậm để bài thử quota không vô tình bị SpikeArrest chặn trước
for i in 1 2 3 4 5 6; do
  curl --silent --show-error --output /dev/null \
    --write-out "A request $i: %{http_code}\n" \
    -H "x-api-key: $API_KEY_A" \
    "$API_BASE/courses"
  sleep 1
done

# Thử app B với key khác ngay sau đó
curl --silent --show-error --include \
  -H "x-api-key: $API_KEY_B" \
  "$API_BASE/courses"
~~~

Kỳ vọng: **request thứ sáu** của A trong cùng cửa sổ quota bị từ chối, trong khi B có quota riêng và vẫn có thể được chấp nhận. Nếu không đúng, kiểm tra:

- Trong lúc chạy bài, có request nào khác dùng key A/B không?
- Cửa sổ quota reset khi nào và policy dùng loại counter nào?
- `Identifier` có thực sự là `verifyapikey.VAK-Lab.client_id`, sau policy VerifyAPIKey?
- Có một policy SpikeArrest hoặc Quota khác đang chạy trên cùng flow?
- API product và operation mapping có khớp resource không?

**Không ép kết luận request thứ sáu phải nhận một body/status cố định** nếu tổ chức đang có FaultRules khác; ghi lại response thực và mã fault để so sánh với thiết kế.

### 7.6. Kiểm tra SpikeArrest tách khỏi quota

Chờ cửa sổ quota mới hoặc dùng app/key lab khác chưa tiêu thụ quota; gửi một burst **nhỏ, có giới hạn** vượt 2ps:

~~~bash
for i in 1 2 3 4; do
  curl --silent --show-error --output /dev/null \
    --write-out "burst $i: %{http_code}\n" \
    -H "x-api-key: $API_KEY_B" \
    "$API_BASE/courses" &
done
wait
~~~

Có thể có request bị từ chối ở SpikeArrest, tùy cách đếm, concurrency, thuật toán và trạng thái proxy. Chỉ dùng bốn request trong lab để chứng minh nguyên tắc; không tăng lên hàng nghìn request hoặc load test production chỉ vì số lần thử đầu chưa sinh 429.

### 7.7. Dọn và hoàn nguyên

Khi kết thúc, **chỉ với tài nguyên do lab tạo và đã được duyệt**:

1. Lưu evidence không chứa key/token: revision, policy names, flow order, request status, fault code, quota metrics.
2. Gỡ traffic/deploy **đúng proxy revision lab** hoặc khôi phục revision trước nếu có quy trình quản lý thay đổi.
3. Thu hồi developer app credentials dùng thử nếu không còn sử dụng; cân nhắc API product lab chỉ khi không có app khác phụ thuộc.
4. Xác nhận backend lab không còn bị gọi bởi proxy hoặc automation thử nghiệm.
5. Kiểm tra Apigee analytics, chi phí/quota đã tiêu thụ và những log có thể chứa dữ liệu nhạy cảm; xử lý theo chính sách.

Không xóa API product, app, environment hoặc proxy dùng chung chỉ để “dọn sạch” bài tập. Bài học **không** yêu cầu tạo/xóa organization thật; chúng có phạm vi quản trị và chi phí lớn hơn một API proxy.

## 8. Giám sát, tuning và xử lý sự cố

### 8.1. Phân biệt bốn nhóm lỗi

| Dấu hiệu | Lớp nguyên nhân | Kiểm tra trước |
| --- | --- | --- |
| `401`, fault `InvalidApiKey` hoặc thiếu key | VerifyAPIKey | App approved chưa? Key đúng? API product có proxy/resource/path này không? |
| `401`/`403` với Bearer token | OAuthV2/VerifyJWT hoặc authorization | Issuer, audience, algorithm, expiry, scope và danh tính đã được policy xác minh. |
| `429` trước khi quota kỳ dùng hết | SpikeArrest hoặc fault rule khác | `Rate`, `Identifier`, `UseEffectiveCount`, burst và request đến cùng thời điểm. |
| `429` sau số lượng request ổn định | Quota | Cửa sổ, count, counter scope, product/operation, app key và retry. |
| `502/503/504`, latency cao nhưng policy pass | Target/egress hoặc backend | Target URL, DNS/TLS, IAM Cloud Run, VPC path, timeout, concurrency và load test. |
| `500` khi thêm policy | XML, flow variable/step, policy entitlement hoặc config | Validation/deploy logs, Debug, policy names và đúng environment. |
| App B dùng chung quota với app A | Identifier không có/không resolve hoặc cấu hình counter chung | Kiểm tra VerifyAPIKey chạy trước, policy name/flow variable và shared counter. |
| API key hợp lệ nhưng gọi path không được | API product operation/resource mismatch | Product association, path suffix/method, app status và proxy deployment. |

Phải kiểm tra **fault code và nguồn lỗi**, không kết luận chỉ dựa vào HTTP status. Ví dụ 429 có thể do SpikeArrest, Quota hoặc lớp gateway/load balancer khác. Nếu tình huống xảy ra sau khi deploy revision mới, so sánh flow order, names và điều kiện với revision trước.

### 8.2. Các chỉ số tối thiểu

- **Gateway:** request count theo proxy/operation/app, p50/p95/p99 latency, policy faults, tỷ lệ 4xx/5xx.
- **An ninh:** key invalid/revoked, JWT issuer/audience failures, client mới, đường request lạ, thay đổi IAM và API product.
- **Traffic:** SpikeArrest violations và Quota violations theo identifier, mức usage của từng app so với quota/contract.
- **Backend:** error rate, concurrency, CPU, connection pool, thời gian xử lý request và khả năng autoscale.
- **Chi phí:** số request/API calls, policy entitlement, capacity Apigee, lưu lượng tới backend, Cloud Logging/analytics và các dịch vụ phụ.

Apigee cung cấp API Analytics/Debug theo tổ chức và quyền truy cập. Trong môi trường production, giới hạn quyền dùng Debug, cấu hình **masking/redaction** và retention: một trace có thể vô tình chứa header `Authorization`, `x-api-key`, client secrets, cookie hoặc payload nhạy cảm.

### 8.3. Quy trình thay đổi giới hạn

~~~mermaid
flowchart TD
    S["Đo RPS/latency theo app,<br/>backend capacity và SLO"] --> D["Chọn Rate / Quota / Identifier"]
    D --> TEST["Test staging: valid/invalid,<br/>burst, reset, 429, key rotation"]
    TEST --> CAN["Deploy revision có review<br/>và giám sát tăng cường"]
    CAN --> G{"SLO, security và<br/>chi phí đạt?"}
    G -->|Có| KEEP["Giữ config, lưu baseline"]
    G -->|Không| ROLLBACK["Rollback revision / policy<br/>theo change plan"]
    KEEP --> S
    ROLLBACK --> S
~~~

**Không chỉ nâng Rate vì partner phàn nàn 429:** cần biết partner có bị chặn vì burst 2ps, quota theo ngày, lỗi client retry không idempotent hay vì backend đã vượt capacity. Nếu nâng giới hạn tổng mà backend Cloud Run/GKE có số instance hoặc database connections tối đa thấp, gateway có thể chuyển được nhiều request hơn nhưng dịch vụ đích lại tăng 503.

### 8.4. Retry và idempotency

Ứng dụng gọi API nên xử lý 429/5xx có **exponential backoff, jitter, deadline và retry budget**. Với thao tác POST thanh toán/đăng ký, thêm **idempotency key** và transaction handling: khi timeout, request đầu có thể đã được backend xử lý thành công, do đó retry mù quáng có thể tạo trùng giao dịch.

Nếu quota đếm request tại đầu proxy, một request đã bị backend từ chối hoặc retry nhiều lần có thể vẫn ảnh hưởng usage theo chính sách đã chọn. Xác định **thế nào là một đơn vị tính phí/hạn mức** trong API contract, rồi kiểm chứng bằng test; đừng mặc định “chỉ 2xx mới trừ quota”.

## 9. Tình huống thiết kế và bài tập

### Tình huống A — Đối tác dùng hết băng thông backend

API tra cứu khóa học có ba đối tác: Bronze, Silver và Gold. Backend được benchmark đạt khoảng **120 RPS** khi p99 vẫn dưới SLO; mỗi yêu cầu đọc nhỏ tương đối tương đồng. Bronze gọi không đều và gửi burst 300 request ngay đầu phút; Gold gọi đều 40 RPS. Hãy đề xuất:

1. Một ngưỡng **global protection** giúp tránh backend bị dồn tải.
2. Ngưỡng SpikeArrest riêng theo **app identity** hoặc API product đã xác minh.
3. Quota từng gói (ví dụ mỗi ngày) phù hợp hợp đồng.
4. Cách kiểm chứng rằng Gold không bị ảnh hưởng bởi app Bronze khi bị burst.

**Định hướng:** dùng **VerifyAPIKey** để xác minh app và product; **SpikeArrest per-client** để hạn chế burst Bronze; **Quota** để thực thi tổng số request theo gói; có thể thêm một mức global protection trong phạm vi backend thực chịu được. Không lấy đơn giản 120 RPS chia đều cho ba đối tác: cần dự phòng, read/write mix, tính toán concurrency, latency và tải nguồn khác.

### Tình huống B — Token hợp lệ nhưng thuộc sai audience

Partner gửi JWT được ký đúng RS256, còn hạn và dùng key trong JWKS đúng. Tuy nhiên token có `aud=api-A` nhưng request tới `api-B`.

**Yêu cầu:** request có nên được chấp nhận không? Cấu hình policy nào cần bảo vệ điều này?

**Đáp án định hướng:** **không** nếu B yêu cầu audience riêng; `VerifyJWT` phải kiểm tra `Issuer` và `Audience` phù hợp B, cùng thuật toán/khóa và claim bắt buộc. Chỉ kiểm tra chữ ký là không đủ để ngăn token phát cho dịch vụ A bị dùng sai ở dịch vụ B.

### Tình huống C — Quota hết dù traffic thấp

Một developer app gọi API 1 RPS và bị 429 sau một thời gian; SpikeArrest đặt `10ps`, quota đặt `1000/hour`.

**Yêu cầu:** giải thích vì sao 1 RPS vẫn bị từ chối và hướng điều tra.

**Đáp án định hướng:** 1 RPS tương đương **3.600 request/giờ**, vượt quota **1.000/giờ** dù chưa chạm 10ps. Phân biệt rate/burst với tổng quota. Kiểm tra cửa sổ, retry, counter scope và app ID trước khi nâng quota.

### Tình huống D — Bị giả mạo identifier

Một policy `Quota` dùng `request.header.customer-id` làm `Identifier`. Bất kỳ client nào cũng có thể tự đổi header này; sau khi nhận 429 họ thử giá trị khác và lại gọi được.

**Yêu cầu:** xác định lỗ hổng và cách khắc phục.

**Đáp án định hướng:** identifier chưa tin cậy; thay bằng `verifyapikey.<policy-name>.client_id` hoặc claim đã được JWT/OAuth policy **xác thực** rồi chuẩn hóa. Kiểm thử tách quota giữa hai app, key rotation và trường hợp flow variable rỗng; không dựa vào header tùy ý từ Internet.

### Tình huống E — Proxy nâng cấp, 401 tăng đột biến

Sau khi thêm JWT vào PreFlow, mọi partner vốn dùng API key đều bị 401 dù key vẫn hợp lệ.

**Yêu cầu:** xác định nguyên nhân có khả năng cao và hai cách sửa phù hợp.

**Định hướng:** nếu gắn cả `VerifyAPIKey` và `VerifyJWT` không điều kiện trong một PreFlow, request bị yêu cầu **đồng thời hai credential**. Nếu API contract cho phép **hai hình thức độc lập**, phải thiết kế các conditional flows/branches rõ ràng và chống bypass; nếu contract chuyển sang JWT, cần kế hoạch migration, cấp token và giao tiếp với partner trước cutover. Không đặt `continueOnError=true` để mọi request lướt qua policy.

## 10. Câu hỏi tự kiểm tra

**1. Policy XML đã có trong bundle có tự chạy không?**  
Không; phải gắn bằng `Step` vào flow tương ứng hoặc cấu hình thực thi phù hợp.

**2. `VerifyAPIKey` có xác minh người dùng cuối không?**  
Không mặc định. Nó xác minh app/key và quyền API product/resource.

**3. `OAuthV2 VerifyAccessToken` có xác minh mọi JWT từ Identity Provider bên ngoài không?**  
Không tự động; phải chọn policy xác minh token theo issuer/định dạng thực tế.

**4. `VerifyJWT` có tự xóa Bearer prefix khi dùng mặc định `Authorization` không?**  
Có. Nhưng khi tự thêm `Source` trỏ tới header chứa cả prefix, chính sách không tự loại bỏ prefix ấy.

**5. Phân biệt 20ps SpikeArrest và quota 10.000/ngày?**  
20ps là giới hạn tốc độ/burst; quota là tổng số request theo kỳ. Một client có thể vượt cái này mà chưa vượt cái kia.

**6. Không có `Identifier` trong Quota thì có thể xảy ra gì?**  
Các request có thể dùng chung counter của proxy thay vì tách theo từng app.

**7. Vì sao phải kiểm tra thứ tự VerifyAPIKey → SpikeArrest/Quota?**  
Để những policy lưu lượng dùng biến danh tính **đã xác minh**, không dùng biến chưa có hoặc header giả mạo.

**8. Tại sao không dùng `continueOnError=true` cho policy xác thực?**  
Có thể dẫn tới request không được xác minh vẫn đi tiếp (fail open) nếu flow xử lý không chặn riêng.

**9. Trả 429 đã đủ chống DDoS hoặc giảm tải backend chưa?**  
Chưa. Cần protection nhiều lớp, tải kiểm thử, timeout, IAM/network và autoscaling hợp lý.

**10. Điều kiện nào cho phép proxy giới hạn đúng theo API product của app?**  
App phải được xác minh và liên kết với API product/operation đúng; Quota phải dùng đúng cấu hình/counter scope.

## 11. Tài liệu chính thức

- [Apigee — What are policies?](https://cloud.google.com/apigee/docs/api-platform/fundamentals/what-are-policies): policy XML, attachment và trách nhiệm.
- [Apigee — Controlling proxies with flows](https://cloud.google.com/apigee/docs/api-platform/fundamentals/what-are-flows): PreFlow, conditional flows, PostFlow và thứ tự.
- [VerifyAPIKey policy](https://cloud.google.com/apigee/docs/api-platform/reference/policies/verify-api-key-policy): API products, developer apps và flow variables.
- [OAuthV2 policy](https://cloud.google.com/apigee/docs/api-platform/reference/policies/oauthv2-policy): VerifyAccessToken và scope.
- [VerifyJWT policy](https://cloud.google.com/apigee/docs/api-platform/reference/policies/verify-jwt-policy): issuer, audience, key/JWKS, Source và claims.
- [SpikeArrest policy](https://cloud.google.com/apigee/docs/api-platform/reference/policies/spike-arrest-policy): Rate, Identifier, UseEffectiveCount và burst.
- [Quota policy](https://cloud.google.com/apigee/docs/api-platform/reference/policies/quota-policy): counter, time window và API product quota.
- [AssignMessage policy](https://cloud.google.com/apigee/docs/api-platform/reference/policies/assign-message-policy): xóa/thêm header và tạo response.
- [RaiseFault policy](https://cloud.google.com/apigee/docs/api-platform/reference/policies/raise-fault-policy): lỗi được quản lý.
- [Apigee policies reference](https://cloud.google.com/apigee/docs/api-platform/reference/policies/reference-overview-policy): nhóm policy, các điều kiện sử dụng.
- [Apigee security](https://cloud.google.com/apigee/docs/api-platform/security/overview): bảo mật API proxy, token và yêu cầu truy cập.

Tính năng, policy entitlement, quota, giới hạn lưu lượng và chi phí có thể khác giữa **Apigee, Apigee hybrid, organization/edition và thời điểm triển khai**. Trước khi dùng thật, xác minh tài liệu chính thức, API product mapping, flow order và phản hồi lỗi trong **environment được phê duyệt**. Một thiết kế tốt phải chứng minh rằng **request không có quyền bị chặn**, **đối tác hợp lệ không chiếm hết tài nguyên của nhau**, **backend được bảo vệ khi burst**, và **quyền truy cập vẫn được kiểm soát ở tầng nghiệp vụ**.
