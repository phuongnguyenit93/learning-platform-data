# Subscription, sản phẩm API và developer portal

Một nhóm phát triển có REST API phục vụ khách hàng nội bộ, đối tác và ứng dụng di động. Họ muốn công bố tài liệu, cho phép lập trình viên đăng ký sử dụng, cấp credential cho từng ứng dụng, giới hạn lưu lượng và thu hồi quyền khi hợp đồng kết thúc. Nếu chỉ công khai URL backend và chia sẻ một API key dùng chung, nhóm vận hành sẽ khó biết ai đang gọi API, khó khóa riêng một khách hàng và khó thay đổi chính sách mà không sửa code.

**Azure API Management (APIM)** giúp quản lý vòng đời công bố và tiêu thụ API bằng một **gateway**, các **API**, **products**, **subscriptions**, **policies** và **developer portal**. Trong APIM, product là gói API và điều kiện sử dụng; subscription là quyền truy cập tương ứng với một phạm vi và có thể cung cấp các subscription keys; developer portal là nơi người dùng khám phá tài liệu, đăng ký và thử gọi API. Những thành phần này bổ trợ nhau nhưng **không thay thế cơ chế xác thực/phân quyền nghiệp vụ** như Microsoft Entra ID, OAuth 2.0 hoặc xác thực phía backend.

Bài thuộc chương **API và tích hợp quy trình** của module **CLOUD_PROVIDERS_AZURE**. Module khám phá hệ sinh thái Microsoft Azure từ subscription, resource group, Microsoft Entra ID đến mạng ảo, compute, lưu trữ và dữ liệu; đồng thời học triển khai, giám sát, bảo vệ và kiểm soát chi phí kiến trúc ứng dụng. Ở chương này, APIM đứng giữa bên tiêu thụ và backend để **công bố có kiểm soát**, tích hợp dịch vụ, giám sát và quản lý trải nghiệm API developer.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Mô tả luồng **consumer → gateway → backend** và vị trí của developer portal.
- Phân biệt API, operation, product, group, user, subscription và subscription key trong APIM.
- Chọn phạm vi subscription phù hợp: **product, single API hoặc all APIs** theo nhu cầu và quyền quản trị.
- Thiết kế sản phẩm API có trạng thái công bố, yêu cầu subscription, phê duyệt và giới hạn truy cập.
- Hiểu lifecycle của subscription: tạo, yêu cầu phê duyệt, kích hoạt, tạm dừng, thu hồi và luân chuyển keys.
- Cấu hình developer portal để người dùng khám phá API, đọc OpenAPI, thử gọi API và yêu cầu subscription.
- Phân biệt **subscription key** với OAuth2 access token, JWT, mTLS và backend authorization.
- Áp dụng rate limit, quota, JWT validation, CORS và giám sát theo đúng scope chính sách.
- Xây quy trình CI/CD/IaC cho API và product mà không phát tán secrets.
- Xử lý các lỗi như 401/403, sản phẩm không hiển thị, Try it thất bại, rate limit 429 và backend 502.

## 2. Kiến trúc API Management

~~~text
         API developer / đối tác
                  |
                  v
        Developer portal (tài liệu,
        onboarding, subscription)
                  |
                  | Lấy credential / hiểu API
                  v
          Client application
                  |
                  | HTTPS request
                  | Subscription key và/hoặc JWT
                  v
        Azure API Management gateway
          +-----------------------+
          | API + operation route |
          | Subscription checks   |
          | Inbound policies      |
          | Backend forwarding    |
          | Outbound/on-error     |
          +-----------+-----------+
                      |
                      | HTTPS, private networking,
                      | backend auth nếu cần
                      v
             Backend: App Service /
             AKS / Functions / VM / API
                      |
                      v
                   Response
~~~

Ba mặt phẳng cần nhận diện:

| Thành phần | Chức năng chính | Lưu ý |
|---|---|---|
| **Management plane** | Định nghĩa APIs, products, subscriptions, groups, users, policies | Có quyền tạo/sửa cấu hình qua Azure RBAC và APIM management interfaces |
| **Gateway/data plane** | Nhận requests, áp dụng chính sách, gọi backend và trả response | Không tự trở thành backend nghiệp vụ |
| **Developer portal** | Tài liệu, đăng ký và thử gọi API | Không phải gateway và không phải hệ thống billing mặc định |

**APIM gateway** có hostname mặc định dạng **<APIM_NAME>.azure-api.net** theo cấu hình dịch vụ; có thể sử dụng custom domain/TLS theo khả năng tier. **Developer portal** có URL riêng tùy kiểu portal/cấu hình và không phải hostname để application trực tiếp gửi API traffic.

### Điểm khác giữa APIM và backend

APIM có thể xác thực, kiểm tra token, cache, biến đổi header, giới hạn rate và định tuyến. Backend vẫn chịu trách nhiệm **kiểm tra quyền nghiệp vụ**, thực thi transaction, bảo vệ dữ liệu và đối phó lỗi. Một API có subscription key đúng chưa chắc được phép xem hóa đơn của tài khoản khác.

## 3. Từ API tới product và subscription

Hãy xét một nhóm API:

~~~text
APIM service: apim-contoso
|
+-- API: Catalog
|     +-- GET /products
|     +-- GET /products/{id}
|
+-- API: Orders
|     +-- POST /orders
|     +-- GET /orders/{id}
|
+-- API: Inventory
      +-- GET /stock/{sku}

Products:
  Catalog Starter  -> API Catalog
  Partner Commerce -> API Catalog + Orders
  Internal Ops     -> API Orders + Inventory

Subscriptions:
  mobile-store-subscription -> Catalog Starter
  partner-abc-subscription  -> Partner Commerce
~~~

Một API có thể thuộc **nhiều products**; mỗi product bao gồm một hoặc nhiều APIs; và mỗi consumer có thể có **nhiều subscriptions** phục vụ các ứng dụng/gói khác nhau. APIM **không bắt buộc một API chỉ thuộc một product**.

### Bảng phân biệt đối tượng

| Đối tượng | Ý nghĩa | Ví dụ |
|---|---|---|
| **API** | Định nghĩa giao diện, base path, backend và operations | Orders API |
| **Operation** | Phương thức + URL template + schema/response | POST /orders |
| **Product** | Gói APIs, mô tả, chính sách và điều kiện đăng ký | Partner Commerce |
| **Group** | Nhóm người dùng được phép nhìn/truy cập product theo cấu hình | Partners |
| **User** | Danh tính developer trong APIM | developer@partner.example |
| **Subscription** | Entitlement thuộc một scope, owner và trạng thái | partner-abc-orders |
| **Subscription key** | Credential dùng để chứng minh subscription khi yêu cầu key | Primary/secondary key |
| **Policy** | Logic gateway kiểm tra/biến đổi/giới hạn request | rate-limit, validate-jwt |

Lưu ý **subscription ở đây là APIM subscription**, **không phải Azure subscription** thanh toán tài nguyên cloud. Azure subscription là một ranh giới billing/management của Azure; APIM subscription là đối tượng truy cập API trong một APIM service.

## 4. Sản phẩm API (product) là gì?

**Product** đóng gói một tập API để công bố cho một loại khách hàng/use case. Một product có thể có:

- Tên hiển thị, mô tả, terms of use và định danh kỹ thuật.
- Tập API mà người dùng có thể tiêu thụ thông qua product.
- Trạng thái **Published/Not published**.
- Cấu hình **Subscription required**.
- Tùy chọn **Requires approval** đối với yêu cầu đăng ký theo cơ chế hỗ trợ.
- Chính sách (policies) ở scope product như rate-limit/quota.
- Quyền hiển thị/khả năng đăng ký theo **groups** và cấu hình portal.
- Giới hạn số subscriptions cho mỗi user theo thuộc tính/khả năng hỗ trợ.

### Ví dụ phân tầng gói

| Product | APIs | Subscription | Phê duyệt | Chính sách gợi ý |
|---|---|---|---|---|
| **Public Catalog** | Catalog GET | Có thể không yêu cầu theo thiết kế | Không | Throttle theo IP/client, chỉ đọc |
| **Developer Sandbox** | Catalog + Orders sandbox | Yêu cầu | Có thể tự cấp | Rate thấp, backend giả |
| **Partner Commerce** | Catalog + Orders | Yêu cầu | Có | Rate/quota theo subscription, JWT validation |
| **Internal Operations** | Inventory + Orders admin | Yêu cầu và IAM riêng | Theo quy trình | Private networking, RBAC/JWT, audit |

Đây là **thiết kế minh họa**, không phải các mức giá hay cấu hình mặc định của APIM. Đặt tên product là "Premium" hoặc ghi một "price" trong mô tả **không tự biến APIM thành hệ thống thu tiền, lập hóa đơn hay tính phí API call**. Nếu bán API thương mại, cần giải pháp hợp đồng/billing riêng và đối soát usage.

### Product không phải pricing plan

Sản phẩm giúp biểu đạt **gói quyền truy cập**, không tự xử lý thanh toán. Có thể dùng product để gắn chính sách như quota, nhưng việc thu phí, hợp đồng, gia hạn, thuế và xuất hóa đơn phải do hệ thống khác đảm nhiệm nếu tổ chức cần.

## 5. Published, subscription required và requires approval

Ba thuộc tính dễ bị nhầm:

| Thuộc tính | Ý nghĩa | Hiểu sai thường gặp |
|---|---|---|
| **Published** | Product được công bố để người có quyền phù hợp khám phá/đăng ký | "Published" không tự làm API public vô điều kiện |
| **Subscription required** | Việc sử dụng API qua product cần subscription key theo cơ chế APIM | Không đồng nghĩa đã xác thực người dùng cuối |
| **Requires approval** | Yêu cầu đăng ký phải được phê duyệt trước khi sử dụng | Không tự phê duyệt hợp đồng kinh doanh hoặc KYC |

Một product không published có thể không được hiển thị/cho đăng ký thông thường trong developer portal. Nhưng **không nên xem trạng thái portal là security boundary duy nhất**: vẫn phải đánh giá API-level settings, các subscriptions ở scope khác, access restrictions, policies và backend.

Một product **không yêu cầu subscription** có thể được gọi theo quy tắc truy cập gateway/API mà không cần product subscription key. Khi đó vẫn cần **JWT/OAuth, mTLS, IP restriction, backend authorization hoặc cơ chế khác** nếu API không dành cho anonymous access.

### Quy trình phê duyệt product có kiểm soát

~~~text
Developer thấy product trong portal
      |
      v
Đọc docs / terms of use
      |
      v
Gửi subscription request
      |
      +-- Không cần approval --> Kích hoạt theo cấu hình
      |
      +-- Requires approval --> Pending / reviewed
                                   |
                            Approve hoặc Reject
                                   |
                                   v
                            Subscription active
                                   |
                            Cấp/hiển thị key
~~~

Các bước UI/trạng thái chính xác tùy cấu hình portal và APIM service. Với các khách hàng cần hợp đồng, có thể đặt một **quy trình approval ngoài APIM** trước khi quản trị viên kích hoạt subscription.

## 6. Subscription trong APIM có phạm vi nào?

APIM hỗ trợ những phạm vi subscription khác nhau theo cách quản trị được dịch vụ hỗ trợ, thường bao gồm:

| Scope | Hành vi | Khi phù hợp |
|---|---|---|
| **Product scope** | Cho quyền gọi các APIs được cấp qua một product phù hợp | Partner đăng ký một gói, cần quota/gói rõ ràng |
| **Single-API scope** | Quyền trực tiếp với một API, không nhất thiết phụ thuộc product enrollment | Ứng dụng nội bộ tích hợp một API cụ thể |
| **All-APIs / service scope** | Quyền rộng đối với APIs trong APIM service theo cơ chế hỗ trợ | Hệ thống quản trị/tích hợp được tin cậy, hạn chế rất chặt |

**Subscription ở scope rộng không phải cơ chế tương đương product approval.** Một key all-APIs có thể truy cập nhiều API hơn dự kiến của một nhóm partners. Nếu cấp rộng, mỗi lần thêm API mới có thể mở rộng bề mặt truy cập cho client đó theo cấu hình APIM.

APIM có thể có subscription nội bộ/đặc biệt do nền tảng tạo cho người quản trị/test theo model hiện hành. **Không đưa một key quản trị hoặc all-access vào ứng dụng của khách hàng** chỉ vì thử API dễ hơn.

### Một user có thể có nhiều subscriptions

Một developer có thể có:

- Subscription cho ứng dụng mobile sandbox.
- Subscription cho backend commerce production.
- Subscription cho API riêng mà họ được cấp quyền thử nghiệm.

Hãy quản lý **subscription theo ứng dụng, môi trường và mục đích sử dụng**, thay vì phát một key dùng chung cho tất cả partners. Khi cần thu hồi đối tác A, không làm ảnh hưởng đối tác B.

## 7. Primary key và secondary key

Với APIM subscriptions yêu cầu key, service cung cấp **primary** và **secondary subscription key** để client có thể luân chuyển credential mà hạn chế downtime.

~~~text
Subscription: partner-abc-prod
    |
    +-- Primary key (đang được client dùng)
    |
    +-- Secondary key (key dự phòng / phục vụ rotation)
~~~

Các key có **quyền tương đương trong cùng subscription**; không phải primary có quyền ghi còn secondary chỉ được đọc. Việc chọn key nào để gửi request không thay đổi scope product/API được cấp.

### Mẫu header phổ biến

~~~http
GET /catalog/products HTTP/1.1
Host: <APIM_GATEWAY_HOST>
Ocp-Apim-Subscription-Key: <VALID_SUBSCRIPTION_KEY>
Accept: application/json
~~~

Header mặc định thường là **Ocp-Apim-Subscription-Key**. APIM có thể cho phép cấu hình tên header/query parameter trên API hoặc có cách đưa key qua query string, nhưng **không nên truyền secrets qua URL** vì chúng dễ nằm trong logs, browser history, monitoring/referrer và công cụ chia sẻ liên kết.

### Rotation không gián đoạn ở mức thiết kế

1. Kiểm kê client đang dùng primary key và các phụ thuộc.
2. Xác nhận secondary key đang hợp lệ hoặc regenerate **key chưa được sử dụng**.
3. Đưa secondary key qua secret manager an toàn và cập nhật client.
4. Quan sát traffic/401 và xác minh mọi client đã chuyển sang secondary.
5. Regenerate primary key cũ khi hết thời gian chuyển, làm nó không còn hợp lệ.
6. Lưu audit, cập nhật runbook và thiết lập lần rotation tiếp theo.

**Không regenerate cả hai key cùng lúc** nếu chưa có kế hoạch chuyển toàn bộ clients. Regenerate một key sẽ làm các client vẫn dùng key đó bị từ chối ngay sau khi thay đổi có hiệu lực.

Không bao giờ commit key vào Git, đưa trực tiếp vào JavaScript frontend public, Dockerfile hoặc ảnh screenshot; một **subscription key là secret** dù nó không phải OAuth access token.

## 8. Subscription lifecycle và quyền thu hồi

Một subscription có owner/scope, tên hiển thị, keys và trạng thái. Tùy API/portal/management model, có thể có các trạng thái như **Submitted/Pending**, **Active**, **Suspended**, **Rejected**, **Cancelled** hoặc trạng thái tương ứng.

Mục tiêu vận hành:

| Thao tác | Khi nào dùng | Hệ quả cần kiểm tra |
|---|---|---|
| **Create/request** | Developer muốn dùng product/API | Có phê duyệt hoặc active theo policy |
| **Approve/activate** | Đã qua onboarding/terms | Client có thể dùng key nếu gateway/other auth cho phép |
| **Suspend** | Tạm khóa vi phạm/quá hạn | Requests dựa vào subscription đó bị ảnh hưởng |
| **Reactivate** | Đã khắc phục và được phê duyệt | Theo dõi audit và khả năng truy cập lại |
| **Regenerate key** | Credential lộ/rotation định kỳ | Các clients dùng key cũ cần cập nhật |
| **Cancel/delete** | Ngừng hợp đồng/dọn tài khoản | Tránh làm mất audit cần lưu theo policy |

Trong nhiều kịch bản có thể cấp **API-scoped subscription** trực tiếp từ quản trị viên mà không cần user tự đăng ký qua developer portal. Vậy nên "không thấy nút Subscribe" không có nghĩa subscription không tồn tại hoặc không thể tạo qua management plane.

### Khi key bị lộ

Runbook:

1. Đánh giá phạm vi subscription và các client sử dụng.
2. Nếu có nguy cơ lạm dụng tức thời, suspend subscription hoặc rotate key theo ưu tiên bảo mật/khả dụng.
3. Kiểm tra gateway logs, rate, IP, API operations, thời điểm bất thường.
4. Không hiển thị full key trong ticket hoặc log điều tra.
5. Phân phối key thay thế qua secret vault có audit.
6. Bổ sung IAM/network/token validation để giảm tác hại nếu key lại bị lộ.

Với subscription key dùng ở browser/mobile, hãy xem lại kiến trúc: secrets nhúng vào ứng dụng phát hành cho người dùng cuối rất khó giữ bí mật. Có thể dùng backend-for-frontend hoặc token-based access để tránh đặt credential nhạy cảm trong client public.

## 9. API product và group membership

APIM có mô hình **groups** giúp quản lý quyền nhìn thấy/sử dụng products theo cấu hình portal và subscription workflow.

Các nhóm built-in thường gặp gồm **Administrators**, **Developers** và **Guests**; ngoài ra có thể tạo custom groups hoặc tích hợp nhóm/danh tính ngoài theo tính năng và mô hình xác thực hiện hành.

~~~text
User: developer@partner.example
        |
        v
Group: Partners
        |
        v
Visible Product: Partner Commerce
        |
        v
Subscription request/approval
        |
        v
Subscription key with product scope
~~~

### Group visibility và gateway authorization khác nhau

Một product được gắn group Partners sẽ điều khiển **ai được tìm thấy/đăng ký product thông qua APIM developer experience** theo cấu hình. Nhưng **group membership không tự giải quyết mọi yêu cầu authorization** ở backend, và không nên dùng chỉ group visibility để bảo vệ dữ liệu.

Ví dụ cần kết hợp:

- APIM subscription hợp lệ ở scope đúng.
- OAuth/JWT để xác định application/user.
- Scope/role/claim validation ở gateway và backend.
- Tenant-level authorization để ngăn partner A xem dữ liệu của partner B.
- Network restrictions khi API nội bộ.

Nếu partner bị loại khỏi group nhưng vẫn có subscription active hoặc một key cấp ở scope khác, cần kiểm tra/thu hồi quyền thật sự. **Xóa user khỏi nhóm không mặc nhiên tương đương thu hồi mọi key hoặc token**.

## 10. Developer portal là gì?

**Developer portal** của APIM là giao diện dành cho người xây ứng dụng dùng API. Thông thường portal có:

- Danh mục APIs và products mà user được xem.
- Tài liệu endpoint, operations, parameters, response schemas.
- OpenAPI description và ví dụ request/response.
- Nội dung onboarding, điều khoản, hướng dẫn tích hợp và code examples.
- Đăng ký, quản lý subscriptions/keys theo vai trò và cấu hình.
- Tính năng **Try it** để thử request API qua APIM gateway.
- Trang nội dung được tùy biến về branding, navigation, documentation và các tích hợp được hỗ trợ.

Portal **không phải nguồn thực thi API**. Khi người dùng bấm **Try it**, request vẫn đi tới **APIM gateway**; tùy API, họ vẫn cần subscription key, OAuth/JWT hoặc authorization khác.

### Managed portal, self-hosted portal và tính năng hỗ trợ

APIM có trải nghiệm developer portal được Azure quản lý và các khả năng triển khai/tùy biến khác nhau theo tier/phiên bản. Việc self-host portal có thể cần tự vận hành hosting, cập nhật, CORS, authentication và cấu hình tích hợp. **Không tự suy rằng mọi APIM tier đều hỗ trợ cùng bộ tính năng developer portal và custom domain**; hãy kiểm tra service tier đã chọn và tài liệu hiện hành.

### Trước khi công bố portal

1. Kiểm tra domain, HTTPS/TLS certificate và định tuyến.
2. Cấu hình identity provider và registration/sign-in policies.
3. Chỉ hiển thị APIs/products đã được phê duyệt.
4. Gỡ example chứa secret hoặc URL backend nội bộ không được công bố.
5. Đặt ToS/privacy notice và thông tin support.
6. Kiểm thử bằng tài khoản developer thật với quyền tối thiểu, không chỉ tài khoản admin.

## 11. Onboarding developer từ đăng ký đến request đầu tiên

Một quy trình bên ngoài cho một đối tác:

~~~text
Partner nhận lời mời/tài liệu onboarding
       |
       v
Mở developer portal bằng HTTPS
       |
       v
Đăng ký hoặc đăng nhập bằng identity được hỗ trợ
       |
       v
Đọc API reference + products + terms
       |
       v
Chọn Partner Commerce, gửi yêu cầu subscription
       |
       +-- Pending approval -> người quản trị kiểm tra
       |
       v
Subscription Active -> nhận key an toàn
       |
       v
Gọi API qua gateway, kèm key và JWT nếu cần
       |
       v
Theo dõi 200/401/403/429, hạn mức và support
~~~

### Quy trình cần làm rõ ở doanh nghiệp

- Ai phê duyệt đối tác, và cần kiểm tra hợp đồng/tenant nào?
- Một người có được đăng ký nhiều applications/subscriptions không?
- Product nào áp dụng cho sandbox và production?
- Key được phân phối, lưu trong secret vault và rotate theo chu kỳ nào?
- Tài liệu breaking changes được thông báo thế nào?
- Ai có thể suspend subscription và phê duyệt kích hoạt lại?
- Khi user rời công ty đối tác, ai sở hữu và quản lý subscription?

Đừng chỉ cấp key vào email rồi coi onboarding đã hoàn tất. Một mô hình tốt cần **chủ sở hữu, audit, support, môi trường thử nghiệm và quy trình thu hồi**.

## 12. Cấu hình products bằng Azure Portal

Giả sử đã có một **APIM service lab**, và một API **Catalog** được import hoặc tạo từ OpenAPI. Mục tiêu là tạo product dành cho partner và kiểm tra việc đăng ký.

### Bước 1: chọn đúng APIM service

1. Vào [Azure Portal](https://portal.azure.com) và chọn đúng subscription/resource group.
2. Mở **API Management services** rồi chọn instance thử nghiệm.
3. Xem **tier**, region, gateway hostname, network access và quyền quản trị hiện tại.
4. Vào mục **APIs**, kiểm tra API Catalog có operations và backend URL hợp lệ.
5. Kiểm tra API có yêu cầu subscription hay không, base path và policies đã kế thừa.

Không chỉnh một APIM instance production chỉ vì lab chưa có product. Các thay đổi policy/subscription có thể ảnh hưởng mọi consumers.

### Bước 2: tạo product

1. Trong APIM, tìm **Products**.
2. Chọn **Add/Create product** theo giao diện hiện hành.
3. Nhập tên **Partner Catalog**, product ID, mô tả và terms of use.
4. Bật **Subscription required**.
5. Bật **Requires approval** nếu cần quản trị viên xét duyệt.
6. Chọn trạng thái **Published** khi đã sẵn sàng công bố.
7. Lưu product.

Ví dụ các thuộc tính:

~~~text
Display name: Partner Catalog
Product ID: partner-catalog
Description: Product catalog API for approved partners
Subscription required: true
Approval required: true
State: published
Subscription limit: tùy yêu cầu và tính năng hỗ trợ
~~~

### Bước 3: gắn API và group

1. Trong product **Partner Catalog**, chọn thêm **Catalog API** vào product.
2. Thêm group **Partners** hoặc nhóm developer test phù hợp.
3. Không cấp product cho **Guests** nếu API không dành cho anonymous onboarding.
4. Kiểm tra trạng thái product được published và visible đối với một user thuộc group.
5. Kiểm tra backend/gateway policies không cho vượt scope ngoài ý muốn.

### Bước 4: thêm policy sử dụng

Đặt giới hạn tốc độ/quota phù hợp, bắt đầu ở mức thấp cho sandbox. Đọc kỹ các API/policies đã có ở global/API/operation scope để tránh trùng hoặc ghi đè rules.

### Bước 5: kiểm tra bằng developer user

Đăng nhập portal với user **không phải Administrator**. Kiểm tra:

- Product được hiển thị khi user thuộc group phù hợp.
- User ngoài group không thể tự đăng ký product theo quy trình mong muốn.
- Subscription request yêu cầu approval nếu đã bật.
- Sau approval, key gọi được Catalog API.
- Key không tự có quyền gọi API khác không thuộc scope.
- Gateway vẫn kiểm tra JWT/backend permissions nếu chính sách yêu cầu.

**Quyền truy cập phải được chứng minh bằng thử nghiệm đối chứng**, không chỉ bằng việc nút Subscribe có xuất hiện.

## 13. Import và công bố API trước khi thêm vào product

Một product không thay API definition. Trước khi developer có thể dùng API, cần có **API definition** đúng:

| Thuộc tính API | Ví dụ | Vì sao quan trọng? |
|---|---|---|
| **API display name** | Catalog API | Tên cho developer |
| **API ID** | catalog-v1 | Identifier ổn định cho IaC/policies |
| **API URL suffix** | catalog | Gateway nhận đường dẫn /catalog/... |
| **Web service URL/backend** | https://catalog.internal.example | Nơi gateway chuyển request |
| **Operations** | GET /products, GET /products/{id} | Route/schema được portal mô tả |
| **Subscription settings** | Required/optional theo API/product | Tác động tới request validation |
| **OpenAPI document** | OpenAPI 3.x được hỗ trợ | Tài liệu và Try it |

Ví dụ OpenAPI **trích đoạn đủ cấu trúc chính** cho một GET operation:

~~~yaml
openapi: 3.0.3
info:
  title: Catalog API
  version: 1.0.0
servers:
  - url: https://api.example.test
paths:
  /products:
    get:
      operationId: listProducts
      summary: List products
      responses:
        "200":
          description: Product list returned
          content:
            application/json:
              schema:
                type: array
                items:
                  type: object
                  properties:
                    id:
                      type: string
                    name:
                      type: string
~~~

**api.example.test** là địa chỉ ví dụ, không phải backend đã được tạo. Khi import OpenAPI vào APIM, hãy xác minh gateway path, backend URL, query/header names, request/response schemas và policy từ API cũ. Import thành công không kiểm tra hết backend permissions.

### API revisions và versions khác products

APIM hỗ trợ các khái niệm **API revisions** và **API versions/version sets** trong các trường hợp được hỗ trợ:

- **Revision** giúp điều chỉnh định nghĩa/policies mà không nhất thiết thay hợp đồng public version.
- **Version** biểu đạt các hợp đồng API khác nhau, ví dụ **v1/v2**.
- **Product** nhóm APIs và xác định điều kiện sử dụng.
- **Subscription** cấp quyền tiêu thụ theo scope.

Không đặt tên product là "v2" rồi kết luận đã version hóa endpoint. Product plan và API contract version có vòng đời riêng; khi ngừng v1, cần chính sách thông báo, migration và thu hồi phù hợp.

## 14. Đăng ký subscription và thử request

Một developer đã được cấp product **Partner Catalog** và có subscription **Active** có thể gọi gateway theo endpoint do APIM công bố.

Ví dụ với Bash:

~~~bash
GATEWAY="<APIM_GATEWAY_HOST>"    # ví dụ myapim.azure-api.net
SUBSCRIPTION_KEY="<TEST_KEY>"    # lấy từ secret store trong lab

curl --fail-with-body --silent --show-error \
  -H "Ocp-Apim-Subscription-Key: $SUBSCRIPTION_KEY" \
  -H "Accept: application/json" \
  "https://$GATEWAY/catalog/products"
~~~

**Lưu ý:** tùy phiên bản curl trên máy, tùy chọn **--fail-with-body** có thể không được hỗ trợ; có thể dùng **curl -i** để đọc status. Đừng lưu key thật vào script/repository hay đưa ra stdout. Với môi trường người dùng chung, dùng secret store và tránh shell tracing.

### Kết quả cần diễn giải

| Kết quả | Có thể cho biết điều gì? | Kiểm tra tiếp |
|---|---|---|
| **200 OK** | Key và các chính sách liên quan có thể đã chấp nhận request | Nội dung nghiệp vụ đúng chưa, có leak dữ liệu không? |
| **401 Unauthorized** | Key thiếu/sai hoặc JWT/auth policy từ chối | Gateway response, auth headers, scope, token |
| **403 Forbidden** | Subscription không active/quyền không đủ, hoặc access policy từ chối | Subscription state, product/API scope, JWT roles, network |
| **404 Not Found** | API operation/path không khớp hoặc backend trả 404 | API URL suffix, revision, operation template, backend logs |
| **429 Too Many Requests** | Rate-limit/quota policy có thể chặn | Policy, counter key, thời gian reset, Retry-After khi có |
| **502/503** | Backend/gateway không kết nối/khả dụng theo điều kiện thực tế | Backend URL, TLS, DNS, VNet, health và logs |

Mã lỗi không tự chỉ ra một nguyên nhân duy nhất; gateway policies có thể tùy chỉnh status/response. Cần correlation ID, trace/log và kiểm tra backend.

### Kiểm thử không có key

~~~bash
curl -i "https://<APIM_GATEWAY_HOST>/catalog/products"
~~~

Nếu API/product đang yêu cầu subscription, request không có key thường bị từ chối theo cơ chế APIM. Nhưng **một request không có key được chấp nhận** có thể do API/product đang cho anonymous access, chính sách đã thay đổi, hoặc request không đi qua tuyến dự kiến; phải xác minh từng trường hợp.

### Kiểm thử key từ product khác

Dùng một subscription dành riêng cho product **Catalog Starter** rồi thử API chỉ thuộc **Internal Ops**. Kỳ vọng bị từ chối **nếu key đó không có scope phù hợp và API không mở public qua product/API khác**. Khi có key all-APIs hoặc product/API khác cho quyền, kết quả có thể khác; kiểm tra entitlement thực tế, không dựa vào tên key.

## 15. Subscription key không phải OAuth access token

Một trong những hiểu nhầm nguy hiểm là xem subscription key như chứng cứ cho biết **người dùng cuối là ai**.

| Khía cạnh | APIM subscription key | OAuth 2.0 / JWT access token |
|---|---|---|
| Đối tượng chính | Chứng minh subscription ở APIM | Claims về client/user, issuer, audience, scopes/roles |
| Cấp phát | APIM tạo hoặc quản trị subscription/key | Identity provider/token endpoint |
| Hết hạn | Theo lifecycle/rotation của subscription key | Theo token validity/exp, chính sách IdP |
| Phạm vi | API/product/all-APIs tùy subscription | Resources, scopes, roles, claims |
| Điều khiển | Active/suspended/key regeneration | Issuer/audience/scope validation, revocation strategy |
| Rủi ro | Shared secret có thể bị sao chép | Token có thể bị lộ/lạm dụng; cần kiểm tra chữ ký và claims |

Một partner có key hợp lệ **không được mặc nhiên xem mọi order**. Dữ liệu **tenantId, userId, scopes/roles** phải được kiểm tra theo mô hình security được thiết kế, và backend cần thực thi authorization nghiệp vụ.

### Kết hợp nhiều lớp

~~~text
Request:
  Ocp-Apim-Subscription-Key: subscription của Partner ABC
  Authorization: Bearer <ACCESS_TOKEN>
           |
           v
APIM:
  1. Subscription scope có được phép?
  2. JWT issuer/audience/signature/expiry đúng?
  3. Rate-limit/quota phù hợp?
  4. Header forwarding an toàn?
           |
           v
Backend:
  5. Principal/tenant/scopes có quyền làm thao tác không?
  6. Object ID thuộc tenant nào?
~~~

**Phân quyền theo đối tượng trong backend vẫn thiết yếu**. Không chấp nhận một query parameter **tenantId** do client tự gửi làm bằng chứng họ thuộc tenant đó.

## 16. OAuth 2.0 và sign-in developer portal là hai bài toán

Một developer có thể đăng nhập portal qua **Microsoft Entra ID** hoặc identity provider được hỗ trợ để xem tài liệu và subscriptions. Đó là **đăng nhập developer portal**. Khi API được bảo vệ bằng OAuth 2.0, ứng dụng client còn cần **access token phù hợp với API/resource**.

| Hoạt động | Danh tính liên quan | Lưu ý |
|---|---|---|
| Đăng nhập developer portal | Developer account (IdP được cấu hình) | Điều khiển trải nghiệm người dùng portal |
| Yêu cầu subscription product | APIM user/group/approval workflow | Điều khiển entitlement |
| Try it một API có OAuth | OAuth client/authorization server/token flow | Cần cấu hình để portal xin token đúng audience/scopes |
| Gọi production API từ app | Client application/service principal hoặc end user | Backend authorization vẫn phải thực hiện |

**Đăng nhập portal thành công không tự tạo một Bearer token để gọi mọi API.** Ngược lại, một ứng dụng có token hợp lệ chưa chắc có APIM subscription key nếu product/API bắt buộc đăng ký.

### Cấu hình Try it với OAuth

Để người dùng thử API có OAuth:

1. Cấu hình **authorization server/OAuth integration** hoặc trải nghiệm token acquisition theo khả năng portal/APIM hiện hành.
2. Đăng ký client application với identity provider và redirect URI chính xác.
3. Chọn flow phù hợp (ví dụ authorization code + PKCE cho public clients).
4. Xác định audience/scopes/permissions cần xin.
5. Cấu hình API security scheme để portal biết token phải được đưa vào **Authorization** header.
6. Kiểm thử bằng developer có quyền, không dùng global admin làm bằng chứng.

Không đặt **client secret** của confidential client trong JavaScript public. Với client browser/public app, dùng flow không đòi giữ client secret (ví dụ PKCE) theo hướng dẫn hiện hành.

## 17. Policies và phạm vi kế thừa

APIM policies là các quy tắc gateway áp dụng ở những phần pipeline:

- **Inbound:** xác thực, rate limit, rewrite URI, set-header, IP filtering, cache lookup.
- **Backend:** cách forward request tới backend hoặc chọn backend.
- **Outbound:** chỉnh response header, cache store, transformation.
- **On-error:** xử lý lỗi, telemetry, response tùy chính sách.

Policy có thể được gắn ở các scope như **global (all APIs)**, **product**, **API** và **operation** theo mô hình hỗ trợ. Khi một API thuộc nhiều products hoặc request không đi qua product subscription, **đường áp dụng product policy phụ thuộc subscription/route context**, không tự hiểu product policy luôn áp dụng cho mọi cách gọi API.

### Kế thừa bằng phần tử base

Ví dụ một policy XML **khái niệm về cấu trúc**:

~~~xml
<policies>
  <inbound>
    <base />
    <set-header name="x-api-channel" exists-action="override">
      <value>partner</value>
    </set-header>
  </inbound>
  <backend>
    <base />
  </backend>
  <outbound>
    <base />
  </outbound>
  <on-error>
    <base />
  </on-error>
</policies>
~~~

**<base />** thường biểu thị vị trí kế thừa policies từ scope cao hơn. Nếu bỏ base hoặc đặt sai thứ tự, có thể bỏ qua kiểm soát dự kiến từ global/API scope hoặc thay đổi hành vi. **Đừng copy policy lên production mà chưa xem effective policy**, nhất là khi API dùng nhiều products hoặc có policy kiểm tra token.

### Policies không miễn trừ backend validation

Ví dụ APIM có thể kiểm tra header và JWT, nhưng backend vẫn cần xác định **user/tenant có quyền truy cập resource ID**. APIM rate limit không thay thế bảo vệ khỏi SQL injection, và một policy CORS không phải authentication.

## 18. Giới hạn request theo subscription

Hai kiểu kiểm soát hay dùng:

| Chính sách | Ý nghĩa | Ví dụ |
|---|---|---|
| **Rate limit** | Giới hạn số requests trong khoảng thời gian ngắn | 100 calls mỗi 60 giây |
| **Quota** | Giới hạn tổng số calls/dung lượng theo kỳ | 10.000 calls mỗi ngày |

APIM có policy như **rate-limit**, **rate-limit-by-key**, **quota** hoặc **quota-by-key** tùy tier/gateway và phạm vi hỗ trợ. Counter có thể gắn theo subscription hoặc một biểu thức định danh khác.

### Rate limit theo subscription

Ví dụ XML minh họa cho policy được hỗ trợ ở gateway:

~~~xml
<policies>
  <inbound>
    <base />
    <rate-limit-by-key
      calls="60"
      renewal-period="60"
      counter-key="@(context.Subscription?.Id ?? &quot;anonymous&quot;)" />
  </inbound>
  <backend>
    <base />
  </backend>
  <outbound>
    <base />
  </outbound>
  <on-error>
    <base />
  </on-error>
</policies>
~~~

Đây là **ví dụ có điều kiện**: expression dùng context.Subscription.Id nếu request có subscription; nếu product không yêu cầu subscription và nhận anonymous traffic, **tất cả anonymous requests có thể rơi vào cùng counter key**, không phải giới hạn riêng từng người. Với yêu cầu production, cần quyết định chính sách theo **principal ID từ token đã xác minh, client app ID hoặc subscription identity** và kiểm tra support matrix của gateway/tier.

**Không dùng một header bất kỳ như x-user-id chưa được xác thực làm counter-key**: client có thể tự đổi giá trị để né rate limit. Với JWT, chỉ dùng claim sau khi token đã được xác minh.

### Rate limit phân tán có độ xấp xỉ

Với APIM nhiều region, self-hosted gateways hoặc nhiều gateway units, counters có thể có các đặc tính cập nhật/đồng bộ riêng. **Không cam kết chính xác tuyệt đối 60 requests tại mọi mili-giây trên toàn cầu** nếu chưa xác minh mô hình nhất quán của sản phẩm. Giới hạn gateway là một lớp bảo vệ, backend vẫn cần chịu tải và bảo vệ tài nguyên nhạy cảm.

### HTTP 429

Khi rate/quota vượt ngưỡng, APIM thường có thể trả **429 Too Many Requests**, tùy chính sách và customizations. Client cần:

- Đọc thông tin **Retry-After** hoặc headers được cung cấp khi có.
- Backoff với jitter, không retry nóng đồng thời.
- Giới hạn song song, batch/cache khi phù hợp.
- Không dùng subscription key khác để né quota trái điều khoản.

## 19. Chặn token sai bằng validate-jwt

Để kiểm soát API có user/client auth, APIM hỗ trợ các policy xác minh JWT theo cấu hình được hỗ trợ. Ví dụ **minh họa** validate-jwt:

~~~xml
<policies>
  <inbound>
    <base />
    <validate-jwt header-name="Authorization"
                  require-scheme="Bearer"
                  failed-validation-httpcode="401"
                  failed-validation-error-message="Unauthorized">
      <openid-config
        url="https://login.microsoftonline.com/TENANT_ID/v2.0/.well-known/openid-configuration" />
      <audiences>
        <audience>api://API_APPLICATION_ID</audience>
      </audiences>
    </validate-jwt>
  </inbound>
  <backend>
    <base />
  </backend>
  <outbound>
    <base />
  </outbound>
  <on-error>
    <base />
  </on-error>
</policies>
~~~

Phải thay **TENANT_ID** và **API_APPLICATION_ID** bằng cấu hình Entra ID thực tế; API audience có thể là App ID URI hoặc client ID theo cách resource server được đăng ký. Kiểm tra policy schema/tier, issuer, algorithm, token lifetime, claims bắt buộc và môi trường cloud. Ví dụ trên **chưa có kiểm tra scopes/roles cụ thể**; khi yêu cầu least privilege, phải bổ sung kiểm tra claims ở APIM/backend phù hợp.

### Tránh cấu hình quá rộng

- Không chấp nhận token với audience của API khác.
- Không chỉ kiểm tra JWT có ba đoạn văn bản mà bỏ chữ ký/issuer.
- Không chấp nhận bất kỳ issuer nào khi tổ chức chỉ cho một tenant/issuer.
- Không gán tenant quyền xem dữ liệu chỉ vì có token hợp lệ.
- Không ghi full Authorization header hoặc token vào log để debug.

Một access token hợp lệ chưa chắc có quyền **POST /orders**. Backend hoặc gateway phải kiểm tra scopes/roles, tenant identity và resource-level authorization.

## 20. CORS và trải nghiệm Try it trong developer portal

Nút **Try it** thường thực thi request từ trình duyệt. Trình duyệt có thể chặn request vì **CORS** khi origin của developer portal khác origin của APIM gateway.

~~~text
Browser at https://portal.example.test
      |
      | Request to https://api.example.test
      v
Browser performs preflight if required
      |
      v
APIM CORS policy -> Allowed origins/methods/headers?
      |
      +-- Allowed -> actual API request
      |
      +-- Blocked -> browser reports CORS error
~~~

### CORS policy minh họa

~~~xml
<cors allow-credentials="false">
  <allowed-origins>
    <origin>https://portal.example.test</origin>
  </allowed-origins>
  <allowed-methods>
    <method>GET</method>
    <method>POST</method>
  </allowed-methods>
  <allowed-headers>
    <header>authorization</header>
    <header>ocp-apim-subscription-key</header>
    <header>content-type</header>
  </allowed-headers>
</cors>
~~~

Đây là **policy fragment**, không phải tài liệu policies XML hoàn chỉnh. Phải đặt ở vị trí **inbound** theo hiệu lực/kế thừa được APIM hỗ trợ, xác minh origin thật của portal và các headers/preflight yêu cầu.

**CORS không phải hệ thống authorization**: một client server-side như curl không bị browser CORS sandbox ngăn tương tự. Không sử dụng allowed-origins làm ranh giới bảo mật cho API chứa dữ liệu nhạy cảm. Dùng JWT/permission/network protection thực sự.

### Try it thất bại nhưng curl thành công

Kiểm tra:

1. Browser DevTools: lỗi CORS/preflight hay HTTP 401/403 thật?
2. Portal đang gọi **đúng gateway hostname**, không phải backend nội bộ?
3. Allowed origin có khớp developer portal custom domain không?
4. APIM policy có cho header **Ocp-Apim-Subscription-Key** và **Authorization**?
5. Token có audience/scope đúng và subscription đang active?
6. Network restrictions/private gateway có cho browser public truy cập không?

Đừng mở wildcard origin và đưa secrets ra client chỉ để cho nút Try it hoạt động.

## 21. Backend authentication và bảo vệ đường bypass

APIM bảo vệ một API **chỉ khi request thực sự đi qua gateway**. Nếu backend App Service/Functions vẫn public với URL gốc và không có authorization riêng, người dùng có thể bỏ qua APIM subscription checks và rate limits.

~~~text
Client --> APIM Gateway --> Backend API     (đường được quản lý)

Client -----------------> Backend API     (đường bypass nếu backend mở)
~~~

Các biện pháp:

- Giới hạn backend ingress bằng private networking, VNet Integration, Private Endpoint, access restrictions hoặc cơ chế được hỗ trợ.
- Xác thực **APIM → backend** bằng managed identity, mTLS, OAuth hoặc backend credentials được quản lý.
- Không tin header nội bộ chỉ vì client tự đặt cùng tên; backend cần kiểm tra nguồn hoặc chữ ký/identity.
- Dùng HTTPS/TLS và quy trình certificate rotation.
- Kiểm tra routing khi backend ở AKS, Functions, App Service hoặc mạng on-prem.

### Managed identity từ APIM tới backend

Trong một số cấu hình, APIM có thể dùng **managed identity** để lấy access token khi gọi backend là Azure resource/API bảo vệ bởi Entra ID. Khi thiết kế cần kiểm tra:

1. APIM identity đã bật.
2. Backend/identity provider biết resource audience của API.
3. APIM được cấp role/app permission thích hợp.
4. Policy **authentication-managed-identity** ở scope phù hợp và cơ chế lấy token được hỗ trợ.
5. Backend validate token/issuer/audience/authorization đúng.

Không coi subscription key là backend credential mặc định. Subscription key được trình client cung cấp để APIM gateway xét entitlement; backend nên có một cơ chế xác thực riêng nếu cần.

## 22. Product policy và API policy có thể tương tác

Giả sử **Catalog API** thuộc cả Product A và Product B:

~~~text
Catalog API
   |
   +-- Product A (quota 10,000/day)
   |
   +-- Product B (quota 100,000/day)
~~~

Khi client sử dụng **product-scoped subscription** hợp lệ, request có thể chịu policy product tương ứng cùng các policies toàn cục/API/operation theo effective pipeline. Nhưng nếu client dùng **API-scoped hoặc all-APIs subscription**, đừng mặc định gateway luôn chọn Product A hay B để áp hạn mức.

### Thiết kế tránh lỗ hổng policy

- Đặt **kiểm soát tối thiểu bắt buộc** như authentication/JWT validation ở scope phù hợp (global/API/operation) để không phụ thuộc product-specific subscription context nếu cần bảo vệ mọi request.
- Đặt **quota thương mại/tier-specific** ở product scope khi request entitlement đi qua product.
- Xác minh **effective policy** cho các tình huống product key, API key, all-access key và anonymous call.
- Tránh lặp policy rate ở nhiều scope không chủ đích vì có thể tạo nhiều counters hoặc kết quả khác kỳ vọng.
- Dùng tests để chứng minh key từ product có quyền hẹp không gọi được operations ngoài scope.

**Phạm vi subscription là một phần của mô hình authorization và policy execution.** Thiết kế product đẹp trên Portal chưa đủ nếu một API-scoped key hoặc một policy ở scope khác tạo đường đi ngoài mong đợi.

## 23. Quản trị developer portal an toàn

Portal mang thương hiệu doanh nghiệp và thường là điểm tiếp xúc đầu tiên của đối tác. Nhưng vì có thể hiển thị documentation, subscriptions và credential, nó cần quản trị như một ứng dụng có dữ liệu nhạy cảm.

### Những lớp bảo vệ

| Lớp | Kiểm soát đề xuất |
|---|---|
| **Identity** | Chọn sign-in provider được hỗ trợ, ưu tiên Entra ID hoặc tổ chức IdP |
| **User lifecycle** | Quy trình mời, phê duyệt, khóa user nghỉ việc, thu hồi subscriptions |
| **Groups** | Gắn product theo nhóm, kiểm tra quyền với user thực tế |
| **Secrets** | Không ghi primary/secondary keys vào docs, analytics hoặc ảnh chụp màn hình |
| **TLS** | HTTPS, custom domain certificate và rotation khi áp dụng |
| **Content** | Version control các hướng dẫn/cảnh báo API breaking changes |
| **Try it** | CORS, token acquisition và không gọi nguồn dữ liệu production từ ví dụ nguy hiểm |
| **Audit** | Theo dõi thay đổi users, products, subscriptions, policies |
| **Support** | Địa chỉ hỗ trợ, SLA, terms, status page, deprecation notices |

### Portal content phải được công bố có chủ đích

Một tài liệu OpenAPI có thể chứa examples với token, URL database hoặc trường dữ liệu PII. Trước khi publish:

- Xóa toàn bộ credentials thật.
- Dùng domains và user IDs giả trong examples.
- Giải thích HTTP status, pagination, retry và request limits.
- Tách **sandbox URL** và **production URL**.
- Ghi API version, ngày deprecation/sunset và cách migration nếu có.
- Kiểm tra rằng các operation nội bộ không vô tình lọt vào product công khai.

### Quản trị quyền người sửa portal

Developer sử dụng portal không nên có quyền thay đổi cấu hình APIM management plane. Người quản trị nội dung/website cần được cấp quyền theo vai trò và phạm vi được hỗ trợ; hạn chế người có thể đổi **APIs, policies, products và subscription state** trong Azure Portal. Ghi nhận change reviews và audit khi công bố tài liệu mới.

## 24. Cấu hình qua IaC thay vì chỉ bấm Portal

Khi có nhiều APIM services (dev/staging/prod), việc sửa products thủ công dễ tạo drift:

~~~text
Dev:
  Partner Commerce -> Catalog + Orders
  subscriptionRequired=true
  quota=10,000

Prod:
  Partner Commerce -> chỉ Catalog (lỗi thiếu Orders)
  subscriptionRequired=false   (lỗi chính sách)
  quota không có              (lỗi drift)
~~~

Nên quản lý dưới dạng **Infrastructure as Code** hoặc APIM automation theo quy trình tổ chức:

- API definitions/OpenAPI documents và API versions/revisions.
- Product IDs, display names, description và published state.
- Quan hệ product ↔ API, product ↔ group.
- Global/product/API/operation policies.
- Backend definitions và named values (ưu tiên Key Vault references cho secrets).
- Diagnostics, logs, tags và alert configuration.
- Developer portal content/configuration theo khả năng công cụ.
- Subscription lifecycle có dữ liệu nhạy cảm, được quản trị qua workflow riêng thay vì ghi key vào Git.

### Ví dụ Bicep khai báo product

Một **trích đoạn Bicep** mô tả product APIM; cần được đưa vào module có tham số phù hợp và kiểm tra apiVersion được hỗ trợ tại thời điểm áp dụng:

~~~bicep
param apimName string
param productId string = 'partner-catalog'

resource apim 'Microsoft.ApiManagement/service@2022-08-01' existing = {
  name: apimName
}

resource product 'Microsoft.ApiManagement/service/products@2022-08-01' = {
  parent: apim
  name: productId
  properties: {
    displayName: 'Partner Catalog'
    description: 'Catalog API for approved partners'
    state: 'published'
    subscriptionRequired: true
    approvalRequired: true
    subscriptionsLimit: 1
  }
}
~~~

Đây là **mẫu khai báo resource product**, **chưa tạo liên kết API hay group**, và không tạo một hệ thống onboarding hoàn chỉnh. Cần thêm resource/automation cho API associations, group associations và policies theo version schema hiện hành. **Không đặt subscription primary/secondary keys vào Bicep**, vì secrets có thể bị lộ qua source, deployment history hoặc state.

### API versioning và tính ổn định của product IDs

Nếu thay đổi product ID thường xuyên, subscriptions và portal links có thể bị ảnh hưởng. Phân biệt:

- **ID kỹ thuật** dùng làm tham chiếu trong IaC/API.
- **Display name** cho developer, có thể được cập nhật theo thiết kế.
- **API version** xác định hợp đồng request/response.
- **Product version/gói** là quyết định business/entitlement, không nhất thiết trùng API version.

Khi thay đổi product/API associations, đừng xóa product cũ trước khi đánh giá các subscriptions đang active.

## 25. Vận hành nhiều môi trường APIM

Một doanh nghiệp thường có API backend ở dev/staging/prod. Nếu dùng cùng một APIM service và product cho tất cả môi trường, rủi ro:

- Partner thử nghiệm có thể vô tình gọi backend production.
- Một policy rate limit trên dev ảnh hưởng client thật.
- Key cấp cho sandbox có quyền gọi API production theo scope không kiểm soát.
- Developer portal lẫn tài liệu v1/v2 và môi trường.

### Mẫu tách biệt

~~~text
Git / IaC + approved API definitions
             |
      +------+------+----------------+
      |             |                |
      v             v                v
 APIM DEV       APIM STAGING      APIM PROD
  Product A       Product A         Product A
  Key dev         Key staging       Key production
  Backend dev     Backend staging   Backend prod
  Portal dev      Portal staging    Portal production
~~~

Đây là một kiến trúc tham khảo. Việc tạo ba APIM instances có thể tốn chi phí đáng kể, tùy tier/SKU. Một số tổ chức dùng APIM service dùng chung với phân chia API/products và policies đủ mạnh; khi đó phải đánh giá **risk, isolation, management plane permissions, network và lifecycle**.

### Những cấu hình phải khác nhau

| Thành phần | Dev/staging | Production |
|---|---|---|
| Backend endpoint | Test/mock/sandbox | Endpoint nghiệp vụ thật |
| Subscription | Keys thử nghiệm riêng | Keys có quy trình phê duyệt/rotation |
| OAuth audience/issuer | App registrations test | App registrations prod |
| Quota/rate | Dùng để thử stress giới hạn, không phá backend | Theo SLA/contract và capacity |
| Logging | Có thể chi tiết hơn nhưng không lộ secrets | Thu tối thiểu hữu ích, tuân thủ dữ liệu |
| Developer portal | Nội dung thử nghiệm, không cam kết production | Docs/version/ToS chính thức |
| IaC approval | Build/test tự động | Change review và rollback |
| Identity/network | RBAC sandbox | Least privilege, private connectivity khi cần |

**Một biến môi trường tên APP_ENV không tạo isolation**. Phải kiểm tra subscriptions keys, identity, product scope và backend thật trong từng môi trường.

## 26. Giám sát subscriptions, products và gateway

Các tín hiệu quan trọng cho API platform:

| Tín hiệu | Câu hỏi vận hành |
|---|---|
| Request count/RPS | Có bao nhiêu request qua APIM? |
| HTTP 4xx/5xx | Lỗi tới từ client, policy hay backend? |
| 401/403 | Tăng lỗi key/JWT hay thay đổi IAM? |
| 429 | Có product/client nào vượt rate/quota? |
| Latency gateway vs backend | Nút nghẽn là policy hay backend? |
| Subscription usage | Gói/consumer nào cần được tư vấn giới hạn? |
| Backend availability | APIM không tới backend hay backend lỗi? |
| Cache hit/miss nếu dùng | Có giảm tải backend đúng kỳ vọng? |
| Changes to policies/products | Ai sửa cấu hình trước khi lỗi xuất hiện? |
| Portal usage | Developer có tìm đúng docs và hoàn thành onboarding không? |

**Azure Monitor**, API Management diagnostics và Application Insights/Log Analytics có thể hỗ trợ theo mức tích hợp và tier. Không mặc định một metric hoặc dimension có sẵn trên mọi SKU/region/gateway topology.

### Nguyên tắc logging

- Không ghi **Ocp-Apim-Subscription-Key**, Authorization header, client secrets, cookies hoặc PII vào logs.
- Đặt retention và access controls phù hợp.
- Gắn correlation/request ID an toàn giữa gateway và backend.
- Tách APIM management Activity Log khỏi runtime gateway traffic logs.
- Khi điều tra rate/quota, xác định **scope, subscription ID hoặc hash/tokenized identity** chứ không lưu raw key.
- Xác minh schema Log Analytics trước khi viết KQL, vì tên tables/columns khác theo cách cấu hình diagnostics.

### Cách diễn giải spike 401

Một đợt tăng HTTP 401 ngay sau rotation key có thể cho thấy:

1. Một client vẫn giữ key cũ.
2. API đã bật subscription required hoặc product scope thay đổi.
3. JWT access token bị sai audience/issuer/expired.
4. Request đi vào revision/host khác.

Phân tích **gateway response, policy trace/correlation, subscription ID, deployment timeline và client version**. Không vội bật anonymous access cho production.

## 27. Quy trình CI/CD cho API product và portal

Một pipeline APIM không nên chỉ deploy API definition mà quên product membership.

~~~mermaid
flowchart TD
  A[Commit OpenAPI + product IaC + policy] --> B[Schema lint + security checks]
  B --> C[Deploy APIM dev]
  C --> D[Attach API to product + groups]
  D --> E[Test subscription + JWT + negative cases]
  E --> F[Staging approval]
  F --> G[Deploy staging + portal/docs review]
  G --> H{Production approval?}
  H -- No --> I[Stop, remediate]
  H -- Yes --> J[Deploy prod with versioned config]
  J --> K[Smoke tests, monitoring, notify developers]
  K --> L{Healthy?}
  L -- No --> M[Rollback policies/API config safely]
  L -- Yes --> N[Record release]
~~~

### Test cases bắt buộc

- Product published, chỉ hiển thị cho groups được phép.
- User không thuộc group không thể tự đăng ký product nhạy cảm theo workflow.
- Product subscription active gọi được API trong scope.
- API/product subscription không gọi được API ngoài entitlement.
- Key bị suspend/regenerate không còn hợp lệ (kiểm tra ở môi trường test).
- JWT thiếu, sai audience hoặc expired bị từ chối theo policy.
- CORS chỉ cho origins/headers chính xác.
- Rate limit/quota tạo 429 theo điều kiện đã đặt.
- Backend bypass bị chặn theo thiết kế.
- Portal Try it hoạt động với identity test, không dùng admin secrets.
- Logging không chứa keys/tokens.

**Không thử quota bằng cách gửi lượng tải phá hoại lên API production**. Dùng sandbox và công cụ rate-limited với giới hạn đã được phê duyệt.

### Rollback cần xét subscription lifecycle

Trở về product/policy definition cũ không tự xóa subscriptions đã phát hành hoặc khôi phục keys đã rotate. Nếu xóa product rồi tạo lại, các liên kết và quyền có thể thay đổi. Hãy:

1. Lưu versioned API/policy/product configuration trước rollout.
2. Có trạng thái danh sách subscriptions, products và associations cần giữ.
3. Chỉ thay đổi các đối tượng được phê duyệt và có kế hoạch quay lui.
4. Nếu cấu hình mới làm mở quyền rộng, ưu tiên khôi phục policy bảo vệ trước.
5. Thử lại quyền bằng identity đối chứng sau rollback.

## 28. Tình huống thực tế A: partner báo lỗi 401 sau khi nhận key

**Bối cảnh:** đối tác ABC được phê duyệt dùng product Partner Commerce, nhận primary key trong secret vault. Họ gọi:

~~~http
GET /orders/123 HTTP/1.1
Host: <APIM_GATEWAY_HOST>
Ocp-Apim-Subscription-Key: <PARTNER_ABC_KEY>
~~~

Gateway trả **401**. Đội phát triển cho rằng key hỏng và muốn cấp một key all-access.

### Phân tích có hệ thống

1. **Hostname/path:** request đã tới đúng APIM gateway chưa, có đúng API URL suffix và operation không?
2. **Subscription state:** key thuộc subscription Active, không phải Pending/Suspended?
3. **Subscription scope:** Partner Commerce chứa Orders API, hay product chỉ có Catalog?
4. **Key rotation:** key client đang dùng là primary/secondary mới hay key đã regenerate?
5. **API subscription settings:** API yêu cầu key; request có đúng header-name và không bị proxy xóa?
6. **JWT policy:** Orders API có **validate-jwt** yêu cầu Bearer token ngoài subscription key không?
7. **Backend response:** 401 có phải do backend trả thay vì APIM subscription validation?

### Cách xử lý

- Đọc gateway error/correlation an toàn, không yêu cầu đối tác gửi raw key vào email.
- Xác minh product/API membership và trạng thái subscription.
- Nếu cần JWT, cung cấp hướng dẫn token flow/audience/scopes.
- Kiểm tra bằng một test client đã được cấp đúng quyền, không dùng all-access key để che vấn đề.
- Khi khắc phục, cập nhật tài liệu portal, thêm negative tests và RCA.

**Không cấp key all-APIs làm cách sửa 401**. Việc đó có thể cho đối tác quyền gọi các API khác không thuộc hợp đồng.

## 29. Tình huống thực tế B: developer portal không thấy product

**Bối cảnh:** nhóm vừa tạo product Internal Operations, đã add API Inventory, nhưng developer test không tìm thấy product trong portal.

Những khả năng:

- Product còn **Not published**.
- Product không được gắn với group mà developer thuộc.
- User đăng nhập bằng danh tính khác với APIM user đã được cấp group.
- Portal content/configuration chưa được publish/cập nhật theo mô hình dùng.
- Product không có APIs hoặc bị lọc bởi quyền/trạng thái.
- Portal đang trỏ sang APIM instance/environment khác.

### Checklist xử lý

1. Kiểm tra product state, name/ID và API associations.
2. Kiểm tra group associations và user membership.
3. Dùng một developer test thuộc group để đăng nhập lại, không dùng admin.
4. Kiểm tra portal đang đọc đúng APIM service, domain và nội dung đã công bố.
5. Xác minh subscription workflow và approval setting.
6. Không chuyển product sang public/open chỉ để tạo khả năng hiển thị khi sản phẩm dành cho nội bộ.

Khi product xuất hiện, **vẫn phải thử entitlement ở gateway** để chứng minh user chỉ truy cập API phù hợp.

## 30. Tình huống thực tế C: API bị gọi quá hạn mức

**Bối cảnh:** product Developer Sandbox giới hạn **60 calls/phút/subscription**. Một client gửi 300 requests/phút và phản hồi 429 tăng mạnh.

### Phân tích

- Rate-limit có đang đặt đúng policy scope không?
- Counter key có thực sự chia theo **subscription ID** hoặc client identity đã xác minh?
- Nếu không có key, anonymous traffic có bị gom chung không?
- Một API có nhiều products/key scope có thể đi qua những effective policies khác nhau không?
- Workload dùng nhiều gateway units/regions có ảnh hưởng tới độ chính xác counters?
- Client có retry nóng và nhân lưu lượng không?

### Hướng giải quyết

1. Đọc biểu đồ RPS/429 và phân biệt các subscriptions.
2. Xác minh giới hạn với một client sandbox.
3. Hướng dẫn client retry/backoff, caching, pagination hoặc batching.
4. Chỉ tăng quota sau khi đánh giá backend capacity và hợp đồng.
5. Nếu có lạm dụng/credential leak, suspend/rotate key và audit.

**Không tắt toàn bộ rate-limit của APIM production** chỉ để làm biểu đồ 429 về 0; mục tiêu là bảo vệ backend và công bằng sử dụng.

## 31. Bài thực hành: công bố Catalog API cho đối tác

### Yêu cầu

Bài thực hành có hai mức:

- **Thiết kế/read-only:** không cần tạo tài nguyên Azure, phù hợp nếu không có ngân sách/permission.
- **Sandbox có APIM:** tạo/chỉnh một product trên APIM lab đã được cấp quyền, không sửa production.

Giả định có Catalog API gồm **GET /catalog/products** và **GET /catalog/products/{id}**. Mục tiêu:

1. Product **Partner Catalog**, Published.
2. Subscription required và requires approval.
3. Chỉ group Partners được đăng ký.
4. Rate giới hạn 60 requests/phút/subscription.
5. Partner thử API bằng key sau approval.
6. API quan trọng vẫn yêu cầu JWT/claims authorization nếu có dữ liệu riêng.
7. Không lộ key trong docs/log.

### Phần A: thiết kế đối tượng

| Đối tượng | Cấu hình lab | Bằng chứng cần kiểm tra |
|---|---|---|
| API | Catalog, suffix catalog, backend test | Operations/paths đúng |
| Product | Partner Catalog | Published, subscriptionRequired |
| Group | Partners | Developer test được thuộc group |
| Approval | Required | Yêu cầu có trạng thái chờ và được duyệt |
| Subscription | partner-client-test | Active, scope = product |
| Key | Primary/secondary | Chỉ lưu trong secret store, không ghi report |
| Rate-limit | 60/60s | 429 khi vượt trong lab |
| Portal | API docs, ToS, Try it | User test thấy nội dung và gọi được |
| JWT policy | Theo API cần bảo vệ | Token sai bị từ chối |
| Monitoring | Request status và latency | Phân biệt lỗi key, JWT và backend |

### Phần B: chuẩn bị Portal/APIM sandbox

1. Xác nhận APIM service dùng cho lab, đúng subscription và tier.
2. Import/create Catalog API với backend **thử nghiệm**, không dùng dữ liệu production.
3. Tạo product Partner Catalog, cấu hình Published, subscription required và requires approval.
4. Gắn Catalog API và group Partners.
5. Thêm rate-limit phù hợp sau khi xem global/API policies hiện có.
6. Tạo hai developer test: **partner-user** và **outsider-user**.
7. Kiểm tra outsider không thể tự đăng ký sản phẩm nhạy cảm.
8. Partner yêu cầu subscription, admin duyệt theo workflow.
9. Lấy key bằng giao diện/secret channel được phép, không chụp ảnh hoặc copy vào báo cáo.
10. Gọi API qua gateway và xác minh response, lỗi 401 khi thiếu key.

### Phần C: kiểm tra request trong lab

Mẫu test thành công:

~~~bash
GATEWAY="<LAB_APIM_GATEWAY_HOST>"
KEY="<KEY_FROM_SECURE_SOURCE>"

curl -i \
  -H "Ocp-Apim-Subscription-Key: $KEY" \
  "https://$GATEWAY/catalog/products"
~~~

Mẫu test thiếu key:

~~~bash
curl -i "https://$GATEWAY/catalog/products"
~~~

Mẫu test không đúng scope: dùng một **key test khác** chỉ được cấp product không có Catalog, hoặc thử key Partner Catalog trên API nội bộ không thuộc entitlement. Không thực hiện test lên dữ liệu thật.

### Phần D: kiểm tra Try it

1. Mở developer portal bằng user Partners.
2. Tìm product Partner Catalog → Catalog API → operation GET /products.
3. Chọn subscription hợp lệ và OAuth login/token khi API yêu cầu.
4. Dùng **Try it** gửi request tới gateway sandbox.
5. Nếu lỗi, dùng Browser DevTools phân biệt CORS, 401/403 và network.
6. Xác nhận không có raw subscription key/JWT trong documentation hoặc shareable URLs.

### Phần E: ghi nhận kết quả

| Trường báo cáo | Giá trị học viên ghi |
|---|---|
| APIM service + environment | Tên môi trường lab |
| API + operations | Tên/path của Catalog |
| Product state | Published/Not published |
| Group visibility | Ai được thấy/đăng ký |
| Subscription scope | Product/API/service |
| Approval result | Pending → Active, thời điểm |
| HTTP test | Status + latency + correlation |
| Security negative test | Không key/sai key/sai scope/invalid JWT |
| Rate limit | Số request test, 429 và retry behavior |
| Portal | Docs/Try it/CORS đã kiểm tra |
| Secret safety | Chỉ ghi nơi quản lý key, **không ghi key** |
| Cost/cleanup | Tài nguyên được dùng, người chịu trách nhiệm |

Nếu chỉ có quyền đọc, hãy mô tả kiến trúc, Bicep/product configuration dự kiến, policies và ma trận test mà không tạo APIM service mới.

### Dọn dẹp an toàn

- Chỉ xóa product/subscription/users **do chính lab tạo**, sau khi xác nhận không có client khác phụ thuộc.
- Không regenerate keys của production để kiểm thử rotation.
- Không xóa APIM service hoặc resource group dùng chung.
- Xóa test secrets khỏi local shells/CI artifacts theo quy trình.
- Ghi lại trạng thái trước/sau và xác nhận subscriptions test đã bị thu hồi nếu không cần nữa.

## 32. Bảo mật và chi phí khi phân phối API

### Những chi phí cần xem

| Thành phần | Nhóm chi phí |
|---|---|
| **APIM service tier/units** | Capacity hoặc đơn vị tính phí theo SKU/plan hiện hành |
| **Gateway requests** | Số lượng calls/throughput theo tier và khả năng tính phí |
| **Networking** | Private endpoints, VNet, NAT, egress, custom domain/certificate |
| **Azure Monitor/Application Insights** | Logs, metrics ingestion, retention và alerts |
| **Developer portal customization** | Hosting/maintenance nếu self-hosted, công sức nội dung |
| **Backend service** | App Service, AKS, Functions, databases, compute/requests |
| **Identity/Key Vault** | Authentication integration, secret operations, logging |
| **CI/CD** | Build runner, IaC drift checks, release testing |

Không khẳng định một mức giá cố định mà không xét **region, tier, capacity, gateway topology, requests và dịch vụ phụ thuộc**. Sử dụng **Azure Pricing Calculator** và **Cost Management**. **APIM product không tự tạo hóa đơn khách hàng**, và **budget alerts không tự dừng mọi chi phí**.

### 10 nguyên tắc bảo mật nên nhớ

1. Subscription keys là **secrets**, không đặt trong source/frontend public.
2. Product approval không thay thế user/tenant authorization.
3. Gateway subscription checks không thay backend security.
4. JWT phải được kiểm tra chữ ký/issuer/audience/expiry và scopes/roles thích hợp.
5. Product membership chỉ là một lớp entitlement/portal experience.
6. Chính sách bảo mật quan trọng cần xét cả API-scoped/all-APIs subscriptions.
7. Backend không nên mở đường bypass APIM nếu thiết kế yêu cầu chỉ qua gateway.
8. Logging/tracing không được chứa raw keys, tokens hoặc dữ liệu cá nhân không cần thiết.
9. Key rotation và suspension cần có runbook, audit và thông báo đối tác.
10. Developer portal/Try it phải dùng HTTPS, CORS đúng, identity an toàn và docs không chứa credentials thật.

## 33. Checklist trước khi công bố API production

- [ ] Đã xác định API backend, URL suffix, operations, schemas và version/revision.
- [ ] Product rõ mục đích, published state, groups và điều kiện subscription/approval.
- [ ] Đã kiểm tra Product ↔ API và Product ↔ Group associations.
- [ ] Có quy trình developer onboarding, ToS, support, deprecation và ownership.
- [ ] Đã kiểm tra scope của product/API/all-APIs subscriptions và loại bỏ quyền quá rộng.
- [ ] Không dùng global/admin subscription key cho các clients bên ngoài.
- [ ] Primary/secondary keys được giữ trong secret manager, có rotation plan.
- [ ] Dùng JWT/OAuth/mTLS/managed identity theo yêu cầu thay vì chỉ key.
- [ ] Backend có authorization theo tenant/object và được bảo vệ khỏi bypass.
- [ ] Rate-limit/quota có counter key dựa trên identity hợp lệ và mức giới hạn phù hợp capacity.
- [ ] Effective policies global/product/API/operation đã được rà soát.
- [ ] Developer portal được công bố và test bằng user không phải admin.
- [ ] Try it sử dụng đúng gateway, CORS, OAuth audience và subscription key.
- [ ] Negative tests: key thiếu/sai/suspended, wrong scope, JWT invalid, outsider user.
- [ ] Logging/audit/alerting bật đúng, không thu raw credentials/PII.
- [ ] IaC/pipeline quản lý OpenAPI, products, groups, policies và configurations.
- [ ] Rollback không xóa nhầm subscriptions của đối tác đang hoạt động.
- [ ] Có runbook xử lý 401/403/429/502 và quy trình thu hồi key khẩn cấp.
- [ ] Đã xét chi phí APIM tier/units, log ingestion và backend.

## 34. Câu hỏi tự kiểm tra

1. APIM subscription khác Azure subscription quản lý tài nguyên như thế nào?
2. API, operation, product và subscription có quan hệ gì?
3. Một API có thể thuộc nhiều products không? Điều đó tác động policy như thế nào?
4. Product Published có đồng nghĩa API trở thành anonymous public không?
5. Subscription required khác Requires approval ở chỗ nào?
6. Subscription key ở product scope khác single-API và all-APIs scope ra sao?
7. Vì sao không cấp all-APIs key cho partner chỉ cần Catalog API?
8. Primary và secondary keys có quyền khác nhau không? Luân chuyển ra sao để giảm downtime?
9. Vì sao subscription key không đủ xác định user/tenant và quyền xem order?
10. Đăng nhập developer portal và lấy OAuth token để gọi API có phải một quá trình không?
11. Nhóm Partners trong APIM có thay thế backend authorization không?
12. Vì sao product visibility không phải ranh giới bảo mật duy nhất?
13. Khi request có product-scoped key và API-scoped key, cần kiểm tra policy nào?
14. Rate-limit và quota khác nhau ra sao? Tại sao anonymous traffic có thể bị gom chung counter?
15. Điều gì nguy hiểm khi dùng header x-user-id chưa xác thực làm rate-limit counter key?
16. CORS có ngăn một server-side client gọi API trái phép không?
17. Nếu Try it trả lỗi CORS nhưng curl thành công, các kiểm tra đầu tiên là gì?
18. Vì sao một backend public có thể làm vô hiệu hóa kiểm soát gateway?
19. Một request 401 có thể xuất phát từ subscription check hay JWT policy ở đâu?
20. Khi rotate key, vì sao không regenerate cả hai keys cùng lúc?
21. Product API có tự thanh toán và lập hóa đơn theo số request không?
22. Những thành phần nào cần version control/IaC khi phát hành một API mới?
23. Khi rollback policy, vì sao vẫn cần giữ trạng thái subscriptions và API associations?
24. Nếu portal không hiển thị product, cần kiểm tra state, group và user nào?
25. Sau khi công bố API, các metrics/logs nào chứng minh trải nghiệm client đang ổn?

## 35. Tài liệu tham khảo

- [Azure API Management overview](https://learn.microsoft.com/azure/api-management/api-management-key-concepts) — các thành phần API, product, policy, gateway và developer portal.
- [Create and publish an API product](https://learn.microsoft.com/azure/api-management/api-management-howto-add-products) — products, APIs và groups.
- [Subscriptions in Azure API Management](https://learn.microsoft.com/azure/api-management/api-management-subscriptions) — scope, trạng thái và quản lý keys.
- [Subscriptions for access to APIs](https://learn.microsoft.com/azure/api-management/api-management-howto-create-subscriptions) — đăng ký và vận hành subscription.
- [Developer portal overview](https://learn.microsoft.com/azure/api-management/api-management-howto-developer-portal) — managed portal, nội dung và trải nghiệm developer.
- [Developer portal administration](https://learn.microsoft.com/azure/api-management/api-management-howto-developer-portal-customize) — tùy biến và công bố portal.
- [Azure API Management policies](https://learn.microsoft.com/azure/api-management/api-management-howto-policies) — inbound/backend/outbound/on-error và scope.
- [API Management policy reference](https://learn.microsoft.com/azure/api-management/api-management-policies) — catalog các policies.
- [Rate limit by key policy](https://learn.microsoft.com/azure/api-management/rate-limit-by-key-policy) — hạn mức theo counter-key.
- [Quota by key policy](https://learn.microsoft.com/azure/api-management/quota-by-key-policy) — quota theo kỳ.
- [Validate JWT policy](https://learn.microsoft.com/azure/api-management/validate-jwt-policy) — xác minh token.
- [CORS policy](https://learn.microsoft.com/azure/api-management/cors-policy) — cho phép browser origins.
- [Authentication with managed identity policy](https://learn.microsoft.com/azure/api-management/authentication-managed-identity-policy) — APIM gọi backend bảo vệ bằng Entra ID.
- [Azure API Management monitoring](https://learn.microsoft.com/azure/api-management/api-management-howto-use-azure-monitor) — giám sát gateway.
- [Azure API Management infrastructure as code](https://learn.microsoft.com/azure/azure-resource-manager/bicep/overview) — dùng Bicep quản lý tài nguyên Azure.
- [Azure Pricing Calculator](https://azure.microsoft.com/pricing/calculator/) — dự toán giá APIM và dịch vụ phụ thuộc.

**Kết luận:** Trong Azure API Management, **API** định nghĩa chức năng, **product** đóng gói gói quyền tiêu thụ, **subscription** xác nhận entitlement và **developer portal** hỗ trợ khám phá, onboarding, thử nghiệm. Muốn công bố API an toàn, không chỉ tạo product rồi phát key: cần xác minh scope và vòng đời subscriptions, nhóm người dùng, JWT/authorization, policies, CORS, mạng/backend, logging và quy trình phát hành có thể rollback. Khi các lớp này được quản lý nhất quán, đội phát triển vừa mở API cho đối tác thuận tiện vừa giữ được kiểm soát bảo mật, vận hành và chi phí.
