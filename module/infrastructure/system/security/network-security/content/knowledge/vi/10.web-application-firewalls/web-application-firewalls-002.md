# Managed rule và custom rule

> **Chương:** Web application firewall  
> **Mô-đun:** SECURITY_NETWORK_SECURITY  
> **Trọng tâm:** Xây dựng và vận hành chính sách Web Application Firewall (WAF) bằng cách kết hợp các bộ quy tắc được quản lý và quy tắc do tổ chức tự viết; kiểm soát độ phủ, thứ tự ưu tiên, ngoại lệ, tác động tới ứng dụng, logging và các lớp phòng vệ mạng liên quan.

## 1. Vì sao cần hai loại rule trong WAF?

**Web Application Firewall (WAF)** quan sát và xử lý lưu lượng HTTP/HTTPS tại vị trí triển khai phù hợp, chẳng hạn CDN, reverse proxy, load balancer hoặc API gateway. Một chính sách WAF thường gồm **managed rule** (quy tắc/bộ quy tắc được nhà cung cấp hay cộng đồng duy trì) và **custom rule** (quy tắc do đội vận hành định nghĩa theo ứng dụng của mình).

Managed rules cung cấp nền tảng phát hiện các mẫu tấn công web phổ biến, giúp triển khai nhanh hơn và hưởng lợi từ các bản cập nhật chữ ký hoặc logic phát hiện. Custom rules diễn đạt **những điều chỉ tổ chức biết rõ**: endpoint quản trị nào phải được hạn chế, API nào chỉ chấp nhận JSON, khách hàng nào có giới hạn truy cập riêng hoặc dải mạng nào không được gọi dịch vụ.

Hai loại rule **bổ sung** nhau:

- Dùng managed rules để giảm công sức duy trì những mẫu tấn công đã biết và có độ phủ chung.
- Dùng custom rules để áp dụng chính sách truy cập, API contract, giới hạn hành vi và các tình huống cụ thể.
- Kiểm thử và theo dõi cả hai, vì chữ ký có thể bỏ sót hành vi nguy hiểm, còn điều kiện tự viết có thể chặn sai khách hàng hợp lệ.

**Nguyên tắc quan trọng:** Có managed rule không đồng nghĩa hệ thống an toàn. Có custom rule cũng không chứng minh các đường truy cập đã được bảo vệ. Mức bảo vệ phụ thuộc **traffic thật sự đi qua WAF**, khả năng WAF đọc request, cách các rule tương tác và khả năng xác minh hành vi ứng dụng.

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt managed rule, managed rule group, custom rule và exception/override.
2. Lựa chọn cách phối hợp rule theo rủi ro, endpoint, phương thức HTTP, nguồn truy cập và trạng thái ứng dụng.
3. Phân tích ưu tiên, hành động kết thúc, hành động chỉ ghi nhận và hậu quả của allow rule quá rộng.
4. Tuning false positive mà vẫn bảo vệ được những endpoint nhạy cảm.
5. Thiết kế quy trình đưa rule vào monitor, kiểm thử, bật chặn, theo dõi và rollback.
6. Gắn WAF với phân đoạn, firewall L3/L4, VPN, DNS, cloud, IDS/IPS và threat modeling.

## 2. Thuật ngữ và phạm vi quyết định

| Thuật ngữ | Diễn giải | Ví dụ |
|---|---|---|
| **Managed rule** | Quy tắc phát hiện được một bên cung cấp hoặc duy trì; tổ chức sử dụng theo điều kiện và cơ chế của WAF | Phát hiện một lớp payload có dấu hiệu SQL injection |
| **Managed rule group / rule set** | Tập quy tắc được nhóm theo chủ đề, phiên bản hoặc chính sách | Nhóm bảo vệ tấn công web phổ biến |
| **Custom rule** | Điều kiện và hành động do đội vận hành tự thiết kế | Chặn phương thức ngoài GET/POST trên một API cụ thể |
| **Rule ID** | Định danh để log, đối chiếu tài liệu, tuning và kiểm thử | MY-API-METHOD-001 |
| **Match condition** | Điều kiện để rule nhận diện request | Host, URI path, method, source IP, header, body, score |
| **Action** | Cách WAF xử lý request khi match | Allow, Block, Count/Log, Challenge, Rate limit tùy sản phẩm |
| **Priority / order** | Cách engine quyết định rule hoặc group nào được đánh giá trước | Rule ưu tiên cao xử lý trước một nhóm mặc định |
| **Override / exclusion** | Tùy chỉnh hành động hoặc trường kiểm tra của managed rule theo khả năng nền tảng | Đưa một rule cụ thể về chế độ Count ở một endpoint |
| **Scope-down** | Thu hẹp tập request mà một nhóm rule được áp dụng | Chỉ áp một rule group cho host api.example.com |
| **False positive** | Request hợp lệ bị phát hiện/chặn nhầm | Nội dung bài viết chứa đoạn mã bị coi là khai thác |
| **False negative** | Request nguy hiểm đi qua mà không bị nhận diện | Kịch bản tấn công không có chữ ký hoặc WAF không parse được |

Các từ trên mô tả **khái niệm chung**. Mỗi WAF có kiểu group, priority, override, action và cách phân tích request riêng; không thể sao chép nguyên mẫu chính sách của một hãng sang hãng khác mà không xác nhận semantics.

## 3. So sánh managed rule và custom rule

| Tiêu chí | Managed rule | Custom rule |
|---|---|---|
| **Ai duy trì logic?** | Nhà cung cấp, cộng đồng hoặc bên thứ ba được lựa chọn | Đội ứng dụng, an ninh mạng hoặc quản trị WAF |
| **Mục tiêu thường gặp** | Mẫu khai thác, bất thường giao thức, bot hoặc hành vi đã biết | Chính sách riêng của domain, endpoint, tenant, danh tính, hạn mức |
| **Thời gian triển khai** | Nhanh nếu tương thích ứng dụng | Cần khảo sát, thiết kế, review và thử nghiệm |
| **Độ bao phủ** | Tương đối rộng với nhóm hành vi được hỗ trợ | Hẹp hay rộng tùy điều kiện tự viết |
| **Điều chỉnh** | Bật/tắt group, version, scope, override, exclusion nếu hỗ trợ | Tự chỉnh điều kiện, threshold và hành động |
| **Rủi ro chính** | False positive, bản cập nhật thay đổi hành vi, blind spot ngoài phạm vi chữ ký | Rule sai logic, allow quá rộng, thứ tự sai, quy tắc lỗi thời |
| **Bảo trì** | Theo dõi thông báo cập nhật, regression test và exception | Gắn với thay đổi API, sản phẩm, quyền truy cập và lưu lượng |
| **Bằng chứng hiệu quả** | Event theo rule ID, loại tấn công, kết quả test và điều tra | Truy vết policy, test đúng endpoint, log và chủ sở hữu |

**Không đánh đồng “managed” với “đáng tin tuyệt đối”.** Mỗi rule set có giả định về HTTP parsing, loại traffic được hỗ trợ, giới hạn request body và chiến lược false positive. Hơn nữa, ứng dụng có thể có những rủi ro như **Broken Object Level Authorization (BOLA)** hoặc lạm dụng nghiệp vụ mà một chữ ký web chung không nhận ra.

## 4. Managed rule hoạt động như thế nào?

Một managed rule group thường chứa nhiều rule hoặc logic phát hiện được nhà cung cấp duy trì. Tùy engine, việc khớp có thể dựa trên **signature**, **anomaly scoring**, **reputation**, **bot signal**, **giao thức sai định dạng**, hoặc các kết hợp của chúng.

### 4.1. Những nhóm bảo vệ thường gặp

| Nhóm | Tín hiệu minh họa | Giới hạn |
|---|---|---|
| **SQL injection (SQLi)** | Chuỗi và cấu trúc đầu vào nghi vấn liên quan câu truy vấn | Không thay prepared statements và quyền DB tối thiểu |
| **Cross-Site Scripting (XSS)** | Payload có dấu hiệu chèn nội dung thực thi | Không loại bỏ DOM XSS, output encoding sai hoặc mọi biến thể |
| **Path traversal / local file inclusion** | Request tìm cách truy cập path/file ngoài phạm vi | Phụ thuộc URI normalization và cách origin xử lý đường dẫn |
| **Command injection / RCE indicators** | Dấu hiệu đầu vào có thể dẫn tới thực thi lệnh | Không thay API an toàn, validation và sandbox |
| **Protocol/HTTP anomalies** | Header/body bất thường, phương thức không hợp lệ hoặc request framing | Có thể chặn nhầm client cũ hoặc trường hợp hợp lệ hiếm |
| **Reputation / automation / bot** | IP/ASN, fingerprint, tốc độ hay mẫu hành vi có nguy cơ | Không thể xác định danh tính hoặc ý định chỉ từ một tín hiệu |
| **Known-vulnerability patterns** | Payload gợi nhắc lỗ hổng hoặc sản phẩm phổ biến | Cần đúng độ phủ, bản vá và kiểm soát lỗ hổng tại origin |

Một số rule group áp dụng **ngưỡng điểm bất thường**: nhiều dấu hiệu cùng cộng vào một score, sau đó engine mới quyết định block. Trong cơ chế khác, mỗi rule có thể chặn ngay. Vì vậy, khi điều tra cần biết **request bị chặn bởi rule cụ thể hay bởi ngưỡng tổng**, cùng phiên bản và cấu hình đang hoạt động.

### 4.2. Phiên bản, cập nhật và vòng đời

Nhà cung cấp có thể thay đổi managed rules để bổ sung nhận diện, giảm false positive hoặc xử lý lỗ hổng mới. Điều đó giúp bảo vệ nhưng cũng có thể gây thay đổi trong cách ứng dụng hợp lệ được xử lý.

Khi có cập nhật, nhóm vận hành cần biết:

- **Phiên bản/group nào đang áp dụng?** Nền tảng tự cập nhật, pin phiên bản hay cho lịch chuyển đổi?
- **Phạm vi thay đổi là gì?** Thêm rule ID, đổi hành động, sửa parser, tăng giảm độ nhạy hoặc ngừng hỗ trợ phiên bản cũ?
- **Có tác động gì tới API?** Request upload, JSON lồng nhau, đường dẫn chứa đoạn mã, API dành cho đối tác có thể gặp false positive.
- **Rollback thực hiện thế nào?** Có thể quay về phiên bản, override hành động hoặc khôi phục policy đã lưu trong thời hạn cần thiết không?

**Không dựa vào tên rule group như một cam kết bảo vệ mọi endpoint**. Cần bảo đảm group được gắn đúng resource/host, đúng chế độ, có log và được phép thực thi quyết định mong muốn.

## 5. Custom rule giải quyết nhu cầu gì?

Custom rule phù hợp để diễn đạt yêu cầu cụ thể cho một ứng dụng hoặc phân đoạn dịch vụ. Các kiểu phổ biến:

1. **Theo đường dẫn và phương thức:** ví dụ chỉ cho GET/POST trên một API có contract ổn định.
2. **Theo host/domain:** tách chính sách admin.example.com khỏi api.example.com.
3. **Theo IP/CIDR hoặc vùng mạng:** bảo vệ endpoint nội bộ, hạn chế nguồn khách không cần thiết; tránh coi IP allowlist là xác thực.
4. **Theo thuộc tính HTTP:** Content-Type, header được chuẩn hóa, kích thước request, query parameter hoặc dạng body.
5. **Theo tốc độ/hạn mức:** bảo vệ /login, /search, /export hoặc API tốn tài nguyên.
6. **Theo nhãn và kết quả phát hiện:** kết hợp tín hiệu managed rules/bot detection nếu engine cho phép.
7. **Theo phiên bản hoặc tenant:** bảo vệ endpoint beta, đối tác hoặc dịch vụ có yêu cầu riêng.

**Cảnh báo về header do client gửi:** không nên cho phép truy cập quản trị chỉ vì request có header như X-Internal-User: true. Nếu header có thể bị client tự tạo, rule có thể bị vượt qua. Dùng danh tính xác minh tại cổng tin cậy (VPN/ZTNA, mTLS, IAM, API gateway) và chỉ tin header từ proxy được xác thực, có quy trình ghi đè/lọc header phù hợp.

### 5.1. Ví dụ một số custom rule

| ID | Scope | Điều kiện chính | Action dự kiến | Điểm cần xác minh |
|---|---|---|---|---|
| C-001 | api.example.com/v1/orders | Method ngoài tập được API hỗ trợ | Block hoặc để app trả 405 theo contract | OPTIONS/CORS, PATCH hay endpoint mở rộng |
| C-002 | api.example.com/v1/orders | Content-Type ngoài định dạng hỗ trợ cho request có body | Block có chọn lọc | Content negotiation, charset và API clients |
| C-003 | app.example.com/admin/* | Client không qua kênh admin được xác thực | Deny hoặc redirect qua cổng admin tùy kiến trúc | Không tin IP/header chưa xác minh; authz ở app vẫn bắt buộc |
| C-004 | api.example.com/v1/search | Tốc độ request cao từ một client/tenant | Rate limit/challenge | NAT chia sẻ, burst hợp lệ, token/tenant ID xác thực |
| C-005 | Tên miền cụ thể | Dải IP đã xác minh thuộc nguồn abuse | Block có hạn và review | Thay đổi IP, shared hosting, rủi ro chặn nhầm |
| C-006 | API upload | Body vượt giới hạn cho endpoint thử nghiệm | Block hoặc trả lỗi phù hợp | Giới hạn kiểm tra body của WAF, streaming, multipart |

Không đưa mọi trường hợp vào một rule tổng quát. Khi có thể, dùng **scope hẹp, tên rõ, owner và bằng chứng API contract** để tránh tác động sang endpoint khác.

## 6. Cách WAF phối hợp managed và custom rule

Mô hình khái niệm:

~~~mermaid
flowchart TD
    A[HTTPS request đi đến điểm WAF] --> B[TLS termination / HTTP parsing]
    B --> C[Custom controls cho đường dẫn và nguồn]
    C --> D{Có kết quả kết thúc theo policy?}
    D -- Có --> E[Allow / Block / Challenge theo engine]
    D -- Không --> F[Managed rule groups]
    F --> G[Signals, signatures hoặc anomaly score]
    G --> H{Có vượt điều kiện chặn?}
    H -- Có --> I[Block hoặc challenge]
    H -- Không --> J[Rule khác / default action]
    J --> K[Application / API gateway]
    E --> L[WAF logging và metrics]
    I --> L
    K --> L
~~~

Sơ đồ này chỉ minh họa **các lớp quyết định**, không ấn định thứ tự áp dụng cho mọi nhà cung cấp. Có WAF xét custom rule trước managed group, có sản phẩm cho gắn chính sách theo phase hoặc anomaly score; có rule **ALLOW kết thúc việc đánh giá**, trong khi **COUNT chỉ ghi nhận rồi tiếp tục**. Cần đọc tài liệu của engine và thử chính xác thứ tự chạy.

### 6.1. Thứ tự và hành động kết thúc

Giả sử một WAF có cơ chế **first terminating action** (dừng khi gặp hành động kết thúc). Xem ví dụ:

| Thứ tự | Rule | Action | Hệ quả |
|---|---|---|---|
| 10 | Nếu nguồn nằm trong “trusted office IP” | ALLOW | Có thể **bỏ qua** managed rules phía sau đối với request này |
| 20 | Managed SQLi/XSS group | BLOCK khi match | Không được chạy cho request đã ALLOW ở trên |
| 30 | Default action | ALLOW | Chỉ áp dụng khi chưa có hành động kết thúc khác |

Để giảm rủi ro, **không dùng ALLOW sớm cho một CIDR rộng chỉ để tránh false positive**, trừ khi đã xác minh đầy đủ tác dụng của ALLOW trong engine. Một cách phù hợp hơn có thể là **loại trừ đúng biến/field hoặc rule ID gây chặn nhầm**, hay thu hẹp scope theo endpoint, giữ các managed rules khác tiếp tục đánh giá.

### 6.2. Override, exclusion và scope-down khác nhau

| Cơ chế | Thay đổi | Rủi ro nếu dùng rộng |
|---|---|---|
| **Override action** | Đổi cách xử lý kết quả của một rule hoặc nhóm, ví dụ BLOCK thành COUNT theo sản phẩm | Request vẫn được nhận diện nhưng không còn bị chặn |
| **Exclusion** | Bỏ một biến/trường nhất định khỏi kiểm tra của rule/group khi hỗ trợ | Tạo điểm mù đối với dữ liệu tại trường bị loại trừ |
| **Scope-down** | Không áp managed group cho các request ngoài điều kiện định trước | Những endpoint ngoài scope không hưởng bảo vệ của group |
| **Custom allow rule** | Cho phép một tập request; có thể kết thúc xử lý tùy engine | Có thể vô tình bỏ qua toàn bộ lớp kiểm tra về sau |
| **Custom block rule** | Từ chối request khớp điều kiện cụ thể | Có thể chặn khách hàng hợp lệ nếu điều kiện/mức độ tin cậy không đúng |

Khi lựa chọn, đánh giá: **có bao nhiêu request chịu ảnh hưởng**, **đường tấn công nào không còn bị kiểm tra**, **thông tin nào chứng minh đây là false positive** và **ai chịu trách nhiệm phê duyệt**.

## 7. Kiến trúc ví dụ: bảo vệ website và API

Giả sử công ty vận hành website thương mại điện tử và HTTP API:

- app.example.com: trang web public và trang đăng nhập.
- api.example.com: API đơn hàng, tìm kiếm và upload file.
- Origin chạy trong subnet riêng trên cloud; DB nằm trong subnet hạn chế hơn.
- Nhân viên quản trị qua kênh VPN/ZTNA và hệ thống danh tính; SOC nhận log và cảnh báo.

~~~mermaid
flowchart TB
    U[Internet clients] -->|HTTPS| W[CDN / WAF]
    W -->|HTTPS được kiểm soát| A[Private application / API origin]
    A -->|DB port và identity phù hợp| D[(Database)]
    P[VPN hoặc ZTNA admin] --> J[Admin gateway / bastion]
    J --> M[Ứng dụng quản trị]
    W -. Rule events .-> S[SOC / SIEM]
    A -. Application và auth logs .-> S
    J -. Admin access logs .-> S
~~~

**Phân đoạn và firewall L3/L4** phải bảo đảm origin chỉ nhận traffic từ đường proxy/cổng kết nối cho phép; nếu origin có public IP cho truy cập trực tiếp, chính sách WAF dễ bị bypass. DNS trỏ về WAF chỉ là cơ chế khám phá endpoint, **không phải biện pháp cưỡng chế traffic phải đi qua WAF**.

### 7.1. Một bộ policy phối hợp

| Lớp | Rule minh họa | Mục đích | Chế độ đề xuất lúc đầu |
|---|---|---|---|
| Network / origin | Chỉ edge proxy tin cậy vào origin HTTPS; deny đường trực tiếp | Buộc luồng public qua điểm kiểm soát | Kiểm thử enforcement riêng |
| Managed | Web attack baseline: SQLi, XSS, traversal, protocol anomalies | Giảm các mẫu khai thác phổ biến | Theo dõi rồi bật BLOCK có chọn lọc |
| Managed | Bot/reputation signals nếu có | Bổ sung tín hiệu chống automation | Theo dõi tỷ lệ match và false positive |
| Custom | /admin/* chỉ tiếp cận qua cổng quản trị được xác thực | Giảm bề mặt quản trị public | Kiểm thử allow/deny và authz |
| Custom | /v1/orders giới hạn method, Content-Type theo API contract | Kiểm soát hành vi API dự kiến | Count rồi block theo endpoint |
| Custom | /login và /search có rate limit theo baseline | Hạn chế request flood và abuse | Monitor/tune ngưỡng trước |
| Custom | Ngoại lệ hẹp cho một trường của endpoint upload | Xử lý false positive cụ thể | Có owner, hạn sử dụng, regression test |
| Application | Quyền theo user, token, tenant và object | Ngăn BOLA/IDOR và lạm dụng nghiệp vụ | Luôn kiểm tra tại application/API |
| Detection | Correlate WAF events với app/auth/network logs | Điều tra và đánh giá rủi ro tồn dư | Giám sát liên tục |

Đây là **ma trận chính sách logic**, không phải cú pháp rule của một hãng. Trình tự và cách ghép action phải được xác định theo WAF cụ thể; số rule, giới hạn request body và chi phí xử lý cũng ảnh hưởng kiến trúc.

### 7.2. Hồ sơ policy dạng giả mã

~~~yaml
# Pseudocode phục vụ thiết kế; không phải cấu hình trực tiếp của WAF
policy_id: WAF-WEB-API-002
application: "Web and API"
owners: ["Network Security", "Application Team"]
environment: "production"
hosts: ["app.example.com", "api.example.com"]
baseline_managed_group:
  enabled: true
  version_policy: "Track provider release and test before rollout where possible"
  initial_mode: "count"
  targeted_action_after_validation: "block"
custom_rules:
  - id: "C-001"
    scope: "api.example.com/v1/orders"
    condition: "method not permitted by the current API contract"
    action_after_validation: "block"
  - id: "C-002"
    scope: "app.example.com/login"
    condition: "request rate exceeds measured per-client threshold"
    action_after_validation: "rate_limit"
  - id: "C-003"
    scope: "app.example.com/admin/*"
    condition: "request not from verified admin access path"
    action_after_validation: "block"
exceptions:
  - managed_rule_id: "example-managed-id"
    scope: "specific endpoint and parsed field"
    reason: "Confirmed false positive with reproducible test"
    expires: "Reviewed on the next release"
logging:
  correlate_with: ["reverse_proxy", "api_gateway", "application", "identity"]
validation:
  allow_cases: ["Legitimate order API calls", "Known benign upload"]
  deny_cases: ["Forbidden method", "Unauthorized admin access path"]
  rollback: "Restore previous versioned policy"
~~~

Giả mã nêu **ý định bảo vệ**. Trên hệ thống thật, các khái niệm như “verified admin access path”, nhóm luật, số lượng rule, priority, tên biến và việc override phụ thuộc hoàn toàn vào engine.

## 8. Thiết kế custom rule theo ngữ cảnh API

### 8.1. URL và method

Chỉ cho phép các method được API thực sự hỗ trợ, ví dụ GET và POST cho một endpoint đặt hàng, có thể giúp giảm bề mặt tiếp xúc. Nhưng không được tự chặn **OPTIONS** khi client trình duyệt cần CORS preflight, hay chặn PATCH/DELETE trên những endpoint có chức năng hợp lệ.

Khi WAF và origin chuẩn hóa path khác nhau, một rule đơn giản theo chuỗi URI có thể bỏ sót đường dẫn tương đương hoặc chặn nhầm. Cần hiểu URL decoding, encoded slash, case sensitivity, query string và cách router ứng dụng phân giải path.

### 8.2. Header và body

Kiểm tra Content-Type, kích thước body và JSON schema theo từng endpoint. Đối với upload file hoặc form nhiều phần, giới hạn phù hợp thường khác API JSON. Một số WAF chỉ **kiểm tra một phần request body** hoặc có chế độ xử lý đặc biệt khi body vượt giới hạn; không được coi phần body ngoài vùng được kiểm tra là đã được bảo vệ.

API gateway và ứng dụng vẫn phải validate dữ liệu ở điểm thực thi. Một request vượt qua WAF **không chứng minh** dữ liệu hợp lệ hay người dùng có quyền.

### 8.3. Rate limit

Chọn khóa tính quota phù hợp: **IP client đã xác minh**, tài khoản, tenant, API key đã kiểm chứng, hoặc tổ hợp tín hiệu. Rate limit theo IP có thể chặn nhầm nhiều nhân viên dùng chung NAT và có thể bị phân tán tải từ nhiều IP để né ngưỡng.

Thiết lập ngưỡng từ **baseline thực tế**, bao gồm burst hợp lệ, retry tự động và traffic cao điểm. Hành động có thể là 429, challenge, tạm chặn hoặc giới hạn ở gateway, tùy nền tảng. Đừng áp dụng một ngưỡng cho mọi endpoint có chi phí xử lý khác nhau.

### 8.4. Geo/IP filtering và bot signals

Chính sách dựa vào địa lý/IP reputation chỉ là **tín hiệu rủi ro**, không xác thực người dùng hoặc xác định ý định. VPN, proxy, nhà mạng di động, cloud hosting và NAT có thể làm địa chỉ hiển thị khác vị trí thực. Dùng kết hợp những yếu tố mạnh hơn như identity, phiên, hành vi và xác minh của application khi cần.

## 9. False positive: khi managed rule chặn traffic hợp lệ

Tình huống: ứng dụng cho phép người dùng đăng một bài hướng dẫn lập trình. Bài viết chứa các chuỗi ví dụ trông giống payload XSS hoặc SQLi, dẫn đến managed rule báo nguy cơ và WAF trả 403.

**Không nên lập tức tắt mọi managed rule.** Trước hết kiểm tra:

1. Request có đi qua đúng host, endpoint và WAF policy không?
2. Rule ID, group, phiên bản, action, match field và thời điểm xảy ra?
3. Nội dung có thực sự hợp lệ theo API contract, được application xử lý an toàn và thuộc tài khoản có quyền?
4. Lỗi đến từ WAF, API gateway hay chính ứng dụng? Kiểm tra correlation/request ID.
5. Có thể thu hẹp exception đến **một trường dữ liệu, endpoint, rule ID và phiên bản** không?

### 9.1. Thứ tự ưu tiên khi sửa false positive

| Lựa chọn | Khi nào cân nhắc | Điểm cần cảnh giác |
|---|---|---|
| Sửa ứng dụng/contract nếu bất thường do thiết kế sai | Ứng dụng gửi request không nhất quán hoặc cần validation rõ | Không ép ứng dụng đổi hành vi hợp lệ chỉ để khớp signature |
| Chỉnh rule/threshold theo hướng dẫn nhà cung cấp | WAF có tham số độ nhạy, anomaly threshold phù hợp | Có thể giảm khả năng phát hiện diện rộng |
| Chuyển một managed rule sang COUNT trong phạm vi hẹp | Cần quan sát khi xác minh false positive | Request trùng mẫu tấn công sẽ không bị rule đó chặn trong phạm vi này |
| Exclude đúng trường hoặc biến đã kiểm chứng | Một field như nội dung bài viết gây match thường xuyên | Dữ liệu trong trường được bỏ kiểm tra có thể mang payload khác |
| Scope-down một nhóm rule theo endpoint | Group chỉ phù hợp một số route đã khảo sát | Những route ngoài scope sẽ mất lớp bảo vệ của group |
| Disable cả managed group / Allow toàn IP | Chỉ có thể là biện pháp khẩn cấp được đánh giá và có kiểm soát | Tạo lỗ hổng lớn, có thể bypass các rule tiếp theo |

Tất cả ngoại lệ nên có **owner**, lý do, chứng cứ request hợp lệ đã được làm sạch dữ liệu nhạy cảm, **thời hạn rà soát**, phiên bản rule liên quan và phép thử hồi quy.

### 9.2. Phân biệt log COUNT và chặn thực tế

Chế độ **COUNT/LOG/MONITOR** có thể ghi nhận request trùng chữ ký nhưng vẫn cho phép nó tiếp tục qua rule khác hoặc đến origin, tùy engine. Nếu chỉ nhìn số “matches” mà không biết final action, có thể nhầm rằng hệ thống đã chặn tấn công. Dashboard nên hiển thị **matched rule**, **action tại rule** và **final request disposition** khi nền tảng cung cấp.

## 10. False negative và những điểm mù ngoài chữ ký

Ngay cả managed rule phổ biến vẫn có thể bỏ sót:

- Yêu cầu nguy hiểm đã bị **biến đổi encoding** hoặc khác cách parser của WAF đọc nội dung.
- **Request body vượt ngưỡng** mà WAF chỉ đọc một phần, hoặc giao thức API không được parse sâu.
- Traffic đi **trực tiếp đến origin**, qua route/VPN/peering hoặc hostname chưa gắn policy WAF.
- Hành vi **BOLA/IDOR**, phân quyền sai, logic thanh toán, lộ dữ liệu qua endpoint hợp lệ.
- Lỗi **HTTP request desynchronization**, khi proxy/WAF và origin diễn giải framing không đồng nhất.
- Traffic qua **WebSocket, gRPC, GraphQL, HTTP/2, HTTP/3** ở mức tính năng WAF chưa hỗ trợ đầy đủ.

Khi xây threat model cần xác định **phần nào được WAF bảo vệ**, **phần nào do network firewall, identity, API gateway và application chịu trách nhiệm**. Bảo vệ nhiều lớp nhằm giảm tác động nếu một rule không khớp hoặc một điểm kiểm soát bị bypass.

## 11. Logging và bằng chứng đánh giá rule

Một chính sách WAF cần có khả năng **giải thích tại sao request được cho qua hoặc bị chặn**. Các trường quan sát thường cần:

| Trường log/metric | Ý nghĩa |
|---|---|
| UTC timestamp, edge/region, policy version | Đối chiếu thời điểm và cấu hình nào đang tác động |
| Request/correlation ID | Nối WAF → reverse proxy → API → application log |
| Trusted client IP, proxy chain context | Khoanh vùng nguồn theo ranh giới proxy được xác minh |
| Host, path, method, HTTP status | Xác định endpoint và hoạt động phát sinh |
| Managed group ID, rule ID, label/anomaly score | Biết tín hiệu phát hiện và loại rule có liên quan |
| Custom rule ID và điều kiện match | Truy nguyên chính sách riêng của ứng dụng |
| Rule action và final action | Phân biệt COUNT với BLOCK/ALLOW cuối cùng |
| Origin status, latency, response size (nếu có) | Nhận biết lỗi do WAF hay do upstream |
| Tenant/session đã xác minh, nếu được phép ghi | Ghép dữ liệu với hành vi nghiệp vụ |

**Dữ liệu nhạy cảm:** request có thể chứa Authorization header, cookie, token, dữ liệu cá nhân hoặc payload nghiệp vụ. Hạn chế log body, che/redact secret và PII, kiểm soát quyền đọc log, retention và truy vết truy cập. Không đưa token còn hiệu lực vào ticket hoặc dashboard hỗ trợ.

### 11.1. Các chỉ số vận hành

- **Tỷ lệ allow/block/challenge/count** theo hostname, endpoint và rule ID.
- **Tỷ lệ false positive** được xác minh, số ngoại lệ còn hiệu lực và số ngoại lệ hết hạn.
- **403/429/5xx** và độ trễ phản hồi trước/sau mỗi thay đổi rule.
- Tỷ lệ API/hostname public **thực sự đi qua WAF**, bao gồm kiểm tra trực tiếp origin.
- Số lượng managed rule cập nhật chưa được kiểm thử hồi quy và số custom rule không có owner.
- Mức độ đầy đủ của log, correlation ID, thời gian gửi event tới SIEM/SOC.

Không diễn giải số lượng block tăng như bằng chứng chắc chắn WAF hiệu quả hơn: đó cũng có thể là bot traffic tăng, false positive sau bản phát hành hoặc một thay đổi về cách đếm.

## 12. Quy trình phát hành rule an toàn

Một policy có thể làm gián đoạn giao dịch thật. Do vậy quy trình phát hành cần kết hợp đội ứng dụng, Network Security, SOC và chủ dịch vụ.

~~~mermaid
flowchart TD
    A[Inventory và API contract] --> B[Threat model / chọn managed groups]
    B --> C[Thiết kế custom rules và test cases]
    C --> D[Review priority, scope, exception]
    D --> E[Triển khai ở COUNT/MONITOR nếu hỗ trợ]
    E --> F[Phân tích traffic hợp lệ và event match]
    F --> G[Hiệu chỉnh false positive]
    G --> H[Bật BLOCK/challenge chọn lọc]
    H --> I[Kiểm thử allow/deny và origin bypass]
    I --> J[Theo dõi, rollback khi cần và review thay đổi]
    J --> B
~~~

### Bước 1 — Kiểm kê

Liệt kê domain, API, phương thức, Content-Type, upload, WebSocket/gRPC nếu có, lưu lượng từ đối tác và các đường quản trị. Xác định TLS termination, forwarded headers và endpoint origin. Nếu còn đường truy cập ngoài WAF, xử lý cùng lúc ở firewall/route/origin authentication.

### Bước 2 — Thiết kế và review

Chọn managed groups theo ứng dụng, đánh giá những rule đã biết gây false positive và thiết kế custom rules cho nhu cầu riêng. Review **priority, final action, default action, dữ liệu match, rate key và tác động lên ứng dụng**.

### Bước 3 — Monitor và thử nghiệm

Bật COUNT/MONITOR nếu nền tảng có chức năng này. Quan sát traffic hợp lệ có tính mùa vụ, lượng request từ mobile app, đối tác, NAT doanh nghiệp và các endpoint ít dùng. Kiểm tra cả **rule matched nhưng final action không chặn**.

### Bước 4 — Bật thực thi theo từng nhóm

Triển khai theo pilot/canary, endpoint hoặc nhóm rule khi nền tảng hỗ trợ. Có **bản policy cũ**, quyền rollback, kênh quản trị an toàn và phương án khi WAF/edge bị lỗi. Không bật block cho mọi managed rule cùng lúc nếu chưa biết tác động.

### Bước 5 — Kiểm thử và giám sát sau đổi

Kiểm thử luồng được phép và bị cấm, lỗi API, nguồn log, tỷ lệ 403/429/5xx và độ trễ. Khi có sự cố, dùng rule ID, request ID và phiên bản chính sách để khoanh vùng; rollback hoặc sửa đúng rule có vấn đề.

### Bước 6 — Bảo trì theo thay đổi

Khi API đổi schema, phương thức, path, tốc độ; khi nhà cung cấp cập nhật managed set; hoặc khi có lỗ hổng/sự cố mới, phải đánh giá lại rule và ngoại lệ. Theo dõi **cấu hình thực tế so với policy-as-code**, tránh drift hoặc thay đổi trực tiếp không kiểm soát.

## 13. Ma trận kiểm thử managed và custom rules

Kiểm thử cần được thực hiện **trên hệ thống được phép**, ưu tiên staging hoặc endpoint thử nghiệm và dữ liệu an toàn. Mục tiêu là kiểm tra cơ chế, không tạo tải tấn công lên hệ thống thật.

| Test | Loại | Kịch bản | Kết quả mong đợi | Bằng chứng |
|---|---|---|---|---|
| T-01 | Managed | Request hợp lệ chứa dữ liệu bình thường | Không bị chặn sai | Application success, WAF final action |
| T-02 | Managed | Mẫu kiểm thử an toàn do nhà cung cấp/quy trình nội bộ xác nhận khớp một rule | COUNT/BLOCK đúng chế độ | Group ID, rule ID, event và final action |
| T-03 | Managed | Nội dung hợp lệ có đoạn mã dễ gây false positive | Không bị chặn ngoài dự kiến sau tuning | Match field, exclusion/override hẹp |
| T-04 | Custom | API dùng method được contract hỗ trợ | Được xử lý thành công | HTTP status, WAF log, origin log |
| T-05 | Custom | API nhận method không hỗ trợ | Từ chối theo contract tại WAF/app | Rule ID hoặc 405 từ application |
| T-06 | Custom | Client hợp lệ đạt đỉnh traffic bình thường | Không bị rate-limit hàng loạt | Rate metrics, client/tenant context |
| T-07 | Custom | Endpoint thử nghiệm vượt hạn mức ở mức an toàn | Rate limit theo cấu hình | Action, quota metric, phản hồi HTTP |
| T-08 | Kết hợp | Request match custom COUNT và managed BLOCK | Hành động cuối theo semantics đã xác nhận | Thứ tự đánh giá, managed event và final action |
| T-09 | Kết hợp | Request match custom ALLOW sớm và managed group | Kết quả đã được review, không tạo bypass ngoài dự kiến | Event/trace xác nhận group có hoặc không được xét |
| T-10 | Ngoại lệ | Request hợp lệ trên field được exclude | Hợp lệ mà vẫn giữ lớp bảo vệ khác | Exclusion scope, các rule còn hoạt động |
| T-11 | Mạng | Truy cập trực tiếp origin theo bài thử được duyệt | Bị chặn ở network/origin policy | Firewall log, route và origin log |
| T-12 | Cập nhật | Đổi phiên bản managed group | Luồng nghiệp vụ không thoái lui | Regression suite, rule diff, metrics |
| T-13 | Vận hành | Rollback về policy trước | Dịch vụ phục hồi, đúng phiên bản | Policy change log, hiệu năng và event |

### 13.1. Một số lệnh kiểm thử HTTP cơ bản

Các lệnh chỉ minh họa request thông thường. Chúng không xác minh hiệu quả chống khai thác chuyên sâu và không nên chạy endpoint thay đổi trạng thái trên production khi chưa có dữ liệu/ủy quyền phù hợp.

~~~bash
# Kiểm tra website public qua HTTPS và xem status/header
curl -sS -i https://app.example.com/

# Kiểm tra CORS preflight cho API theo contract dự kiến
curl -sS -i -X OPTIONS 'https://api.example.com/v1/orders' \
  -H 'Origin: https://app.example.com' \
  -H 'Access-Control-Request-Method: POST'

# Xác minh method không được hỗ trợ theo thiết kế endpoint
curl -sS -i -X TRACE 'https://api.example.com/v1/orders'

# Đo status và thời gian để so trước/sau thay đổi policy
curl -sS -o /dev/null -w 'http=%{http_code} total=%{time_total}\n' \
  https://app.example.com/
~~~

HTTP **403** có thể do WAF, API gateway hoặc ứng dụng trả về; **429** có thể đến từ WAF hoặc một thành phần hạn mức khác. Chỉ nhìn status chưa đủ để quy trách nhiệm cho rule: cần correlation ID, log tại từng hop và final action.

## 14. Quản trị rule và hạ tầng như mã

Một hệ thống WAF nhiều rule dễ phát sinh **rule trùng lặp, ngoại lệ không hết hạn, thay đổi không được kiểm thử và cấu hình lệch (drift)**. Policy-as-code giúp review và truy vết, nhưng không tự bảo đảm mọi thay đổi được deploy như dự kiến.

Mỗi rule hoặc ngoại lệ nên ghi:

| Thuộc tính | Vì sao cần |
|---|---|
| **Rule ID/tên** | Theo dõi trong log và kết quả kiểm thử |
| **Loại và nhóm** | Managed group/version hay custom policy |
| **Owner và change ticket** | Xác định người chịu trách nhiệm và lý do |
| **Host/endpoint/field/identity scope** | Biết chính xác traffic chịu tác động |
| **Action và priority** | Tránh vô tình cho phép hoặc chặn ngoài dự kiến |
| **Bằng chứng thiết kế** | API contract, threat model và rủi ro đang xử lý |
| **Trạng thái rollout** | Monitor, canary, block, rollback hoặc tạm ngưng |
| **Validation/metrics** | Bằng chứng lưu lượng hợp lệ và case chặn đạt yêu cầu |
| **Ngày review/expiration** | Xóa exception tạm và rule không còn dùng |
| **Rủi ro tồn dư** | Các kịch bản còn có thể vượt qua kiểm soát |

Quy trình review nên phát hiện: **ALLOW rộng đứng trước managed rules**, custom rule không có owner, ngoại lệ toàn domain để giải quyết một field, managed group đang COUNT vĩnh viễn mà không có quyết định chấp nhận rủi ro, hoặc endpoint mới chưa nằm trong scope.

## 15. Kết hợp WAF với các lớp bảo mật mạng

WAF là một lớp của **defense in depth**. Tài sản và đường tấn công khác nhau cần kiểm soát ở nơi có đủ ngữ cảnh:

| Lớp | Vai trò liên quan managed/custom rules |
|---|---|
| **Phân đoạn mạng, VLAN/subnet, cloud VPC/VNet** | Giới hạn truy cập giữa Internet, ứng dụng, DB và quản trị; ngăn đường bypass WAF |
| **L3/L4 firewall, security group, NACL** | Chỉ cho phép edge/proxy gọi origin đúng cổng; deny đường trực tiếp khi cần |
| **VPN/ZTNA và xác thực** | Kiểm soát danh tính và thiết bị cho giao diện quản trị; không dùng IP allowlist như thay thế MFA |
| **API gateway và ứng dụng** | Schema validation, quota, authn/authz theo user/tenant/object, bảo vệ logic nghiệp vụ |
| **IDS/IPS/NDR** | Quan sát hành vi ngoài HTTP và luồng east–west không đi qua WAF |
| **DNS security** | Quản lý public hostname, resolver, bản ghi và thay đổi DNS; DNS riêng nó không ép traffic đi qua WAF |
| **Wi-Fi/NAC/endpoint** | Kiểm soát thiết bị nội bộ và lateral movement, thứ WAF public có thể không thấy |
| **Anti-DDoS/CDN/ISP** | Chống volumetric flood và nghẽn kết nối trước lớp HTTP khi cần |
| **SOC/SIEM và incident response** | Liên kết WAF rule event với ứng dụng, danh tính và hạ tầng để xử lý sự cố |

### Vì sao chỉ WAF không đủ?

Khi attacker có được tài khoản hợp lệ, họ có thể gọi API bằng request đúng cú pháp nhưng truy cập **object thuộc người khác** nếu ứng dụng thiếu kiểm tra quyền. Managed signatures chưa chắc phát hiện; custom rule theo path/method cũng không biết quyền nghiệp vụ. Phải kiểm tra **authorization ở ứng dụng**, ghi log theo user/object và đánh giá abuse theo threat model.

Ngược lại, một WAF cấu hình quá chặt có thể chặn health check, upload, CORS, API client hoặc request hợp lệ từ VPN; hệ thống vẫn “an toàn trên sơ đồ” nhưng mất khả năng phục vụ. Quyết định chặn phải đi cùng kiểm thử vận hành.

## 16. Ba tình huống xử lý thực tế

### Tình huống A — Managed SQLi rule chặn nhầm trường mô tả sản phẩm

Ứng dụng cho nhập mô tả sản phẩm chứa ví dụ SQL hợp lệ. Sau cập nhật managed rule group, nhiều request POST nhận 403.

**Điều tra:** đối chiếu thời điểm cập nhật, group/rule ID, match field, final action và request ID; xác nhận ứng dụng đang encode/validate an toàn. Sau đó áp dụng **exclusion hoặc override hẹp** đúng trường, route và rule gây lỗi, chạy regression test với các mẫu request hợp lệ và tình huống nguy cơ được cấp phép.

**Tránh:** tắt cả managed group hoặc ALLOW toàn IP văn phòng vì một endpoint lỗi.

### Tình huống B — Custom ALLOW để phục vụ đối tác làm mất kiểm tra managed rules

Đội vận hành thêm một custom ALLOW cho toàn bộ IP của đối tác, đặt trước managed group. Trong engine có terminating action, request từ IP này không tiếp tục được kiểm tra mẫu khai thác web.

**Điều tra:** xem semantics ưu tiên và final action, loại traffic cần thật sự tin cậy, khả năng đối tác dùng chung NAT và nguy cơ tài khoản/thiết bị đối tác bị xâm nhập. Sửa chính sách thành **exception hẹp theo endpoint/rule** hoặc mô hình tin cậy phù hợp; giữ phần kiểm tra WAF cần thiết và xác minh bằng test T-08/T-09.

**Bài học:** “trusted source” không có nghĩa mọi payload từ nguồn ấy đều an toàn.

### Tình huống C — Custom rate limit khiến người dùng sau NAT bị khóa

Website đặt giới hạn theo IP trên /login. Sau một đợt đăng nhập đồng loạt, nhiều nhân viên cùng dùng NAT của văn phòng nhận 429, dù mỗi người có tần suất bình thường.

**Điều tra:** xem baseline theo thời gian, trusted client IP, số người chia sẻ NAT, bot signal, số lần gọi do retry và khả năng giới hạn theo danh tính/phiên hợp lệ. Điều chỉnh khóa và ngưỡng, phân biệt giới hạn trước/sau xác thực; quan sát 429 và login success rate sau rollout.

**Tránh:** whitelist toàn bộ mạng công ty khỏi tất cả các rule chống abuse chỉ để hết 429.

## 17. Những ngộ nhận phổ biến

| Ngộ nhận | Cách hiểu đúng |
|---|---|
| “Managed rule đã bật thì mọi endpoint được bảo vệ.” | Còn phụ thuộc scope, mode, đường đi, version, parser và giới hạn WAF. |
| “Rule do nhà cung cấp quản lý thì không cần test.” | Bản cập nhật có thể thay đổi hành vi và gây false positive/negative. |
| “Custom rule có priority cao luôn bảo vệ tốt hơn.” | Priority và terminating action có thể tạo bypass nếu dùng ALLOW quá rộng. |
| “COUNT ghi nhận tấn công nghĩa là đã chặn.” | COUNT/monitor thường chỉ quan sát; phải xem final action. |
| “Có thể loại trừ toàn bộ endpoint khi một trường dữ liệu bị chặn nhầm.” | Exclusion nên hẹp nhất đủ giải quyết nguyên nhân, tránh mất lớp bảo vệ khác. |
| “IP allowlist xác thực được danh tính.” | IP có thể dùng chung, thay đổi hoặc chỉ thể hiện proxy/NAT; dùng identity và xác thực phù hợp. |
| “Bộ rule chống SQLi bảo đảm không lộ dữ liệu.” | Rủi ro còn đến từ authz, cấu hình, logic và đường truy cập ngoài WAF. |
| “DNS trỏ về WAF là chắc không bypass được.” | Cần network/origin enforcement; direct-origin route vẫn có thể tồn tại. |
| “Một bộ rule phù hợp mọi API.” | Contract, phương thức, payload, client và giới hạn protocol khác nhau. |

## 18. Checklist trước khi đưa chính sách vào production

- [ ] Biết rõ endpoint, domain, API contract và traffic nào thực sự đi qua WAF.
- [ ] Xác nhận TLS termination, nguồn client IP tin cậy và khả năng đọc body của engine.
- [ ] Gắn đúng managed groups, phiên bản, chế độ và phạm vi cần bảo vệ.
- [ ] Xác minh custom rule theo hostname, path, method, body/header, identity và threshold.
- [ ] Kiểm tra thứ tự ưu tiên, action kết thúc và trường hợp ALLOW có thể bỏ qua managed group.
- [ ] Chỉ tạo override/exclusion theo rule, endpoint và field có bằng chứng false positive.
- [ ] Đã có owner, hạn review, lý do và trường hợp kiểm thử cho từng exception.
- [ ] Không áp rate limit theo IP cứng nhắc khi có NAT, proxy hoặc nhiều tenant.
- [ ] Kiểm thử cả request hợp lệ, request bị cấm, trường hợp COUNT/ALLOW kết hợp và origin bypass.
- [ ] Có kiểm thử hồi quy khi API, proxy, TLS hoặc managed rule group thay đổi.
- [ ] Dùng log WAF, proxy, ứng dụng, identity và firewall với correlation ID phù hợp.
- [ ] Bảo vệ thông tin nhạy cảm trong log, không ghi token/mật khẩu vào ticket.
- [ ] Giám sát tỷ lệ 403/429/5xx, độ trễ, error rate và false positive sau rollout.
- [ ] Bảo vệ quyền quản trị policy bằng IAM/MFA, change control và lịch sử thay đổi.
- [ ] Có bản policy trước, rollback được kiểm chứng và cơ chế vận hành khi edge/WAF gián đoạn.
- [ ] Kết hợp network segmentation, origin ACL, IDS/IPS, VPN/ZTNA và phân quyền ứng dụng.

## 19. Câu hỏi tự kiểm tra

**1. Managed rule và custom rule khác nhau ở đâu?**  
Managed rule do bên cung cấp/cộng đồng duy trì và thường bảo vệ mẫu nguy cơ chung; custom rule do tổ chức thiết kế cho endpoint, API, nguồn truy cập và ràng buộc riêng. Cả hai cần kiểm thử.

**2. Vì sao một custom ALLOW đặt sớm có thể làm yếu bảo vệ?**  
Ở WAF có hành động ALLOW kết thúc xử lý, request match sẽ không đi tiếp qua managed groups phía sau. Tùy sản phẩm, phải kiểm chứng chính xác semantics.

**3. Khi một trường mô tả chứa đoạn mã hợp lệ bị managed rule chặn, nên làm gì?**  
Xác minh false positive bằng rule ID, match field và app log, rồi ưu tiên exclusion/override **hẹp** có owner, thời hạn và regression test; tránh tắt toàn bộ nhóm luật.

**4. COUNT có tương đương BLOCK không?**  
Không. COUNT/monitor ghi nhận theo cơ chế nền tảng; request có thể vẫn tiếp tục xử lý. Cần theo dõi final action.

**5. Vì sao rule chỉ cho phép POST trên API có thể làm lỗi ứng dụng trình duyệt?**  
Trình duyệt có thể gửi OPTIONS cho CORS preflight; contract còn có thể cần GET/PATCH/DELETE. Phải kiểm tra phương thức thực tế trước khi chặn.

**6. WAF đã dùng managed rules cho SQLi thì còn cần prepared statements không?**  
Cần. WAF không chặn được mọi biến thể và có thể bị bypass; ứng dụng phải dùng truy vấn tham số hóa và phân quyền DB tối thiểu.

**7. Dựa vào đâu để biết cập nhật managed rule group đã an toàn?**  
So phiên bản và thay đổi, chạy test allow/deny, kiểm tra event/403/429/5xx và hiệu năng, có rollback, quan sát người dùng thật và false positive sau rollout.

**8. Vì sao cần phân đoạn và firewall origin dù đã có WAF trên CDN?**  
WAF không thể kiểm soát lưu lượng đi trực tiếp tới origin hay những đường nội bộ khác. Route, security group, ACL và xác thực edge-origin phải buộc đường truy cập phù hợp.

## 20. Tài liệu tham khảo

- [OWASP Core Rule Set (CRS)](https://coreruleset.org/): ví dụ về bộ managed/open-source rules, phát hiện theo mẫu và anomaly scoring.
- [OWASP Web Application Firewall](https://owasp.org/www-community/Web_Application_Firewall): khái niệm và vai trò WAF trong bảo vệ ứng dụng.
- [OWASP Top 10](https://owasp.org/www-project-top-ten/): bối cảnh các nhóm rủi ro ứng dụng web.
- [OWASP API Security](https://owasp.org/API-Security/): các nguy cơ API, đặc biệt những lỗi kiểm soát quyền không thể giải quyết chỉ bằng chữ ký WAF.
- [OWASP Application Security Verification Standard (ASVS)](https://owasp.org/www-project-application-security-verification-standard/): nền tảng kiểm chứng bảo mật ứng dụng và API.
- [NIST SP 800-41 Rev. 1 — Guidelines on Firewalls and Firewall Policy](https://csrc.nist.gov/pubs/sp/800/41/r1/final): quản trị policy, rule và phòng vệ mạng.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): ngữ nghĩa HTTP, phương thức và response status.

**Ghi nhớ:** Managed rule cung cấp năng lực phát hiện phổ biến; custom rule gắn WAF với kiến trúc và nhu cầu ứng dụng. Một chính sách hiệu quả cần **độ phủ đúng, hành động và thứ tự đúng, ngoại lệ hẹp, bằng chứng kiểm thử và quy trình theo dõi cập nhật**; đồng thời dựa vào xác thực, phân quyền ứng dụng, firewall mạng, phân đoạn và giám sát để quản lý rủi ro còn lại.
