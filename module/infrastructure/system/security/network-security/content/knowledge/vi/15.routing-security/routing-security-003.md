# BGP security

**BGP security** (bảo mật Border Gateway Protocol) là tập hợp nguyên tắc, chính sách và cơ chế vận hành nhằm **giới hạn việc ai có thể thiết lập phiên BGP, những tuyến nào được chấp nhận hoặc quảng bá, và làm thế nào để phát hiện – ứng phó khi thông tin định tuyến bị sai lệch**. Mục tiêu quan trọng là giữ lưu lượng đi theo những đường đã được phê duyệt, giảm khả năng mất kết nối, chuyển hướng ngoài ý muốn hoặc rò rỉ thông tin định tuyến giữa các mạng.

**Border Gateway Protocol (BGP)** là giao thức định tuyến giữa các hệ tự trị (**Autonomous System – AS**) và cũng được sử dụng trong những hạ tầng lớn như trung tâm dữ liệu, mạng nhà cung cấp dịch vụ, kết nối cloud và mạng hybrid. Khác với firewall quyết định một kết nối cụ thể được phép đi qua hay không, BGP giúp xác định **đường đi để đưa gói tin tới một prefix**. Nếu đường định tuyến bị công bố hoặc lựa chọn sai, các lớp phòng vệ khác có thể quan sát lưu lượng ở vị trí không như thiết kế.

Trong module **SECURITY_NETWORK_SECURITY**, BGP security là một phần của kiến trúc phòng vệ mạng cùng với phân đoạn, firewall, VPN, IDS/IPS, kiểm soát kết nối, DNS, Wi-Fi và cloud. **BGP không tự xác thực quyền sở hữu prefix bằng mật mã và không mã hóa dữ liệu người dùng** chỉ vì hai router có phiên peering. Phòng vệ hiệu quả phải kết hợp chính sách tuyến, xác thực nguồn gốc định tuyến, bảo vệ phiên, giám sát và quản lý thay đổi.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích vai trò của ASN, IP prefix, BGP peer, UPDATE, AS_PATH, NEXT_HOP và các thuộc tính định tuyến quan trọng.
2. Phân biệt **prefix hijack**, **more-specific hijack**, **route leak** và lỗi cấu hình BGP không cố ý.
3. Thiết kế **import/export policy** theo quan hệ customer, provider, peer và nguyên tắc cấp quyền tối thiểu.
4. Giải thích **RPKI**, **ROA**, **Route Origin Validation (ROV)** và ba kết quả Valid, Invalid, NotFound.
5. Phân biệt ROV xác thực **origin AS** với các công nghệ hoặc cơ chế đánh giá **AS path**.
6. Áp dụng kiểm soát phiên BGP: peer ACL, TCP authentication khi hỗ trợ, GTSM, bảo vệ control plane và prefix limit.
7. Xây dựng monitoring cho BGP announcement/withdrawal, route churn, RPKI và các thay đổi tuyến bất thường.
8. Viết runbook xử lý route leak/hijack, có kiểm thử và rollback an toàn trong lab.

## 2. BGP hoạt động ở mức khái niệm

### 2.1. Autonomous System và ASN

Một **Autonomous System** là tập hợp mạng IP thuộc một chính sách quản trị định tuyến chung trong ngữ cảnh BGP. **Autonomous System Number (ASN)** là số dùng để nhận diện AS trong quá trình trao đổi thông tin định tuyến. Có AS công cộng và ASN được dành cho mục đích riêng hoặc tài liệu.

Ví dụ một doanh nghiệp vận hành AS riêng và kết nối hai ISP. Router biên trao đổi tuyến với các router của ISP; dựa vào thông tin nhận được và chính sách cục bộ, doanh nghiệp lựa chọn đường ra. Doanh nghiệp có thể quảng bá những prefix mà mình được phép quảng bá để đối tác biết đường đưa traffic đến dịch vụ.

**BGP không phải bằng chứng mật mã rằng một AS được phép sử dụng một prefix.** Nếu không có cơ chế lọc và xác thực nguồn gốc, một peer có thể gửi thông tin định tuyến không đúng hoặc không được ủy quyền.

### 2.2. Những thành phần của một BGP route

| Thành phần | Ý nghĩa | Liên quan bảo mật |
| --- | --- | --- |
| **NLRI / IP prefix** | Dải địa chỉ được quảng bá, ví dụ 203.0.113.0/24 | Prefix nào có thể bị công bố sai hoặc quá chi tiết? |
| **AS_PATH** | Chuỗi AS được truyền trong thông tin tuyến | Hỗ trợ phòng lặp và chính sách đường đi; không tự có chữ ký xác thực toàn chuỗi |
| **NEXT_HOP** | Địa chỉ next hop để chuyển tiếp | Cần phù hợp topology, tránh next hop không thể đi tới hoặc không được phép |
| **LOCAL_PREF** | Thuộc tính ưu tiên trong AS đối với lựa chọn đường | Chính sách cục bộ có thể làm traffic đổi hướng |
| **MED** | Thuộc tính gợi ý lựa chọn điểm vào trong một số tình huống | Không phải cơ chế chứng minh tuyến an toàn |
| **Communities** | Nhãn/chỉ thị chính sách được chuyển theo thỏa thuận | Có thể điều khiển export, ưu tiên hoặc hành động từ phía đối tác; cần lọc theo nguồn |
| **ROUTE SOURCE / neighbor** | Peer và hướng học tuyến | Cần biết tuyến đến từ customer, provider hay peer |
| **RPKI origin state** | Valid, Invalid, NotFound từ kiểm tra ROA | Giúp đánh giá AS origin có được chủ tài nguyên ủy quyền hay không |

**Phân biệt quan trọng:** thuộc tính BGP **ORIGIN** (IGP/EGP/INCOMPLETE) **không phải** khái niệm **origin AS** của RPKI Origin Validation. Khi nói ROV, “origin” là AS được xem là nguồn quảng bá prefix theo AS_PATH và quy tắc xác định origin của BGP, không phải giá trị ORIGIN attribute.

### 2.3. Phiên BGP và trao đổi UPDATE

BGP thông thường dùng **TCP cổng 179** để thiết lập phiên giữa các router. Sau khi phiên hình thành, các peer trao đổi thông tin khả năng, thuộc tính và các bản tin **UPDATE** để công bố hoặc rút các tuyến.

Một tuyến không nhất thiết được cài vào bảng chuyển tiếp chỉ vì peer đã gửi UPDATE. Router còn đánh giá **import policy**, tính hợp lệ thuộc tính, khả năng reachability của next hop, lựa chọn best path và các điều kiện triển khai khác.

~~~mermaid
sequenceDiagram
    participant A as Router doanh nghiệp
    participant B as Router ISP
    A->>B: Kết nối TCP / thiết lập BGP session
    B-->>A: OPEN và xác nhận phiên
    Note over A,B: Trao đổi capabilities, tiến đến phiên hoạt động
    B-->>A: UPDATE: prefix + path attributes
    Note over A: Import policy / RPKI / route selection
    A-->>B: UPDATE / withdrawal theo export policy
    Note over A,B: Route thay đổi theo thông tin và chính sách
~~~

Sơ đồ là giản lược về mặt giáo dục: quá trình khởi tạo phiên thực tế có các trạng thái FSM, KEEPALIVE, notification và thương lượng capability. **Xác lập được TCP session không đồng nghĩa một peer được phép quảng bá mọi prefix**.

## 3. eBGP, iBGP và ranh giới tin cậy

- **eBGP (External BGP)**: trao đổi giữa các AS khác nhau. Đây là nơi chính sách theo quan hệ kinh doanh và phạm vi prefix cần được kiểm tra nghiêm ngặt.
- **iBGP (Internal BGP)**: phân phối thông tin BGP giữa router thuộc cùng AS. Cần bảo vệ các phiên, route reflector, next hop, chính sách và quyền điều khiển nội bộ.
- **BGP route reflector (RR)**: giúp giảm số phiên iBGP cần thiết trong mạng lớn. RR là thành phần control plane quan trọng: cấu hình sai hoặc tài khoản điều khiển bị chiếm có thể tác động diện rộng.

Điểm đáng chú ý là **mức tin cậy phụ thuộc nguồn thông tin và quan hệ mạng**, không chỉ tên giao thức. Một route học từ đối tác cloud, khách hàng transit, nhà cung cấp MPLS hoặc router nội bộ đều cần chính sách phù hợp với ranh giới đó.

Nếu doanh nghiệp kết nối hai ISP, default route từ ISP có thể là điều mong muốn; nhưng nhận hoặc chuyển tiếp **mọi prefix không giới hạn** có thể vượt xa nhu cầu kinh doanh và năng lực thiết bị.

## 4. Các rủi ro bảo mật chính của BGP

### 4.1. Prefix hijacking

**Prefix hijacking** là tình huống một AS quảng bá một prefix mà nó không được phép quảng bá theo quyền và chính sách có hiệu lực. Điều này có thể xuất phát từ hành vi cố ý hoặc lỗi cấu hình. Khi những mạng khác chấp nhận tuyến sai, traffic tới prefix đó có thể bị:

- **Mất kết nối / blackhole**, nếu tuyến dẫn tới nơi không thể phục vụ.
- **Chuyển hướng**, nếu traffic đi tới hạ tầng không mong muốn.
- **Can thiệp hoặc giám sát trái phép** trong một số mô hình và điều kiện mạng cụ thể.

Không phải mọi thay đổi origin AS đều là tấn công: **multi-origin AS (MOAS)** có thể hợp lệ trong mạng đa nhà cung cấp hoặc phương án dự phòng. Phải xác minh với quyền quản lý prefix và kế hoạch routing.

### 4.2. More-specific prefix hijack

Trong định tuyến IP, **longest-prefix match** khiến một route cụ thể hơn thường được sử dụng cho các địa chỉ mà nó bao phủ, miễn tuyến được cài vào bảng chuyển tiếp và chính sách cho phép. Vì vậy, một công bố sai **203.0.113.0/25** có thể ảnh hưởng đến một phần traffic của prefix **203.0.113.0/24** mà một AS khác đang công bố.

**More-specific advertisement không tự là tấn công.** Traffic engineering hợp lệ có thể sử dụng các prefix cụ thể hơn trong phạm vi được phép. Điều cần xác minh là quyền công bố, origin, export policy và mức prefix length được mạng tiếp nhận chấp nhận.

### 4.3. Route leak

**Route leak** xảy ra khi thông tin định tuyến được quảng bá vượt qua ranh giới chính sách hoặc quan hệ mạng mà tuyến đó đáng lẽ phải tuân theo. Ví dụ một AS học route từ provider A rồi quảng bá route đó sang provider B dù mình **không được phép làm transit** giữa hai nhà cung cấp.

Một route leak có thể gây vòng chuyển tiếp, tắc nghẽn, mất kết nối hoặc thay đổi đường đi lưu lượng. **RPKI Origin Validation có thể đánh giá tuyến bị leak là Valid**, vì origin AS của prefix vẫn đúng; vấn đề nằm ở **đường lan truyền** chứ không chỉ origin.

### 4.4. Sai cấu hình và thao túng chính sách

Các nguyên nhân thường gặp:

- Route map quá rộng, thiếu danh sách prefix được phép.
- Nhầm địa chỉ peer, remote ASN hoặc chính sách customer/provider.
- Lộ thông tin quản trị router, thay đổi BGP policy ngoài quy trình.
- Quảng bá nhầm route nội bộ, route mặc định hoặc prefix chưa được phép.
- Thay đổi cộng đồng BGP (*communities*) khiến tuyến lan rộng ngoài ý định.
- Thay đổi next hop, LOCAL_PREF hoặc route reflector làm mất reachability.
- Công bố ROA sai hoặc quản lý khóa RPKI không phù hợp, tạo kết quả Invalid ngoài ý muốn.

**BGP security phải bảo vệ cả lỗi vận hành** vì tác động của một thay đổi sai có thể tương tự tác động của một sự cố tấn công.

## 5. Mô hình đe dọa: tài sản, điểm tin cậy và hậu quả

| Tài sản / thành phần | Đường có thể phát sinh rủi ro | Hậu quả tiềm năng | Kiểm soát ưu tiên |
| --- | --- | --- | --- |
| Public IP prefixes | Peer ngoài quảng bá không được ủy quyền | Hijack, mất traffic, đổi origin | ROA/ROV, prefix filtering, external monitoring |
| eBGP customer edge | Customer gửi tuyến ngoài phạm vi | Route leak, table growth | Import filter theo nguồn, max-prefix, ROA/IRR |
| eBGP provider/peer edge | Route nhận bị sai hoặc leak | Thay đổi đường đi, nghẽn | ROV, chính sách theo vai trò, route monitoring |
| Router control plane | TCP session và lưu lượng tới CPU | Peer resets, DoS, phiên bất thường | Peer ACL, session auth khi phù hợp, CoPP, GTSM |
| BGP route reflector | Lỗi cấu hình hoặc quyền quản trị | Suy giảm routing nội bộ trên diện rộng | IAM/AAA, change control, monitoring và redundancy |
| RPKI validator/cache | Dữ liệu ROA stale hoặc mất kết nối | Chọn tuyến sai/ảnh hưởng ROV theo chính sách | HA, dữ liệu cập nhật, telemetry, fail-policy được phê duyệt |
| Cloud/hybrid edge | Quảng bá prefix qua VPN/direct connect | Route leak giữa môi trường, thay đổi reachability | Import/export, route limits, phân đoạn, IAM, giám sát |

**BGP tác động đến control plane và đường đi của data plane.** Việc có tuyến đúng không thay thế firewall/IDS/IPS; việc có firewall đúng cũng không chứng minh route ngoài Internet đang đi theo đường dự kiến.

## 6. Import policy và export policy: tuyến nào được tin?

### 6.1. Import policy

**Import policy** xét những tuyến nhận được từ peer trước khi chúng có thể ảnh hưởng đến bảng định tuyến. Một bộ lọc điển hình có thể kiểm tra:

- Prefix cụ thể hoặc tập prefix được chấp nhận từ peer.
- Giới hạn prefix length để tránh công bố quá chi tiết không được phép.
- Tính hợp lệ origin qua **RPKI ROV** khi dữ liệu hỗ trợ.
- AS_PATH và các đặc điểm route không phù hợp quan hệ.
- Số lượng prefix nhận vào, tốc độ thay đổi và những điều kiện bất thường.
- Bogon/special-use prefixes theo ngữ cảnh, tránh vô tình công bố hoặc học những địa chỉ không nên đi trên Internet.

**Không nên chỉ dựa vào IP ASN của một peer để tự động tin tất cả những prefix nó gửi.** Một peer bị cấu hình sai vẫn có thể phát thông tin định tuyến hợp lệ về cú pháp nhưng không thuộc quyền quảng bá của nó.

### 6.2. Export policy

**Export policy** kiểm soát những tuyến router gửi cho peer. Đây là lớp phòng vệ quan trọng chống **route leak do chính mạng mình**.

Ví dụ:

- Doanh nghiệp không cung cấp transit không nên quảng bá route học từ ISP A sang ISP B.
- Nhà cung cấp transit nên kiểm tra chính sách để không xuất các route private/infrastructure nội bộ ra Internet.
- Một customer nên chỉ gửi những prefix của chính họ hoặc prefix mà họ thực sự được phép cung cấp cho provider.

### 6.3. Quan hệ customer, provider, peer

Trong mô hình kinh tế định tuyến Internet thường được dùng để giảng dạy:

| Đích export | Những route thường được phép export | Lý do |
| --- | --- | --- |
| **Customer** | Route của chính AS và route hợp lệ học từ customer, peer, provider theo thỏa thuận transit | Provider cung cấp dịch vụ chuyển tiếp cho customer |
| **Provider** | Route của chính AS và các route từ customer được phép xuất | Không tự trở thành transit miễn phí giữa hai provider |
| **Peer** | Route của chính AS và route từ customer được phép xuất | Peering thường không bao gồm chuyển tiếp route từ provider/peer khác |

Đây là **nguyên tắc điển hình**, không phải luật bắt buộc cho mọi thỏa thuận. Có các mạng có quan hệ đặc thù, dịch vụ transit khác hoặc chính sách thương mại riêng; thực thi phải bám **hợp đồng và quyền được phê duyệt**.

### 6.4. Ví dụ route leak

~~~mermaid
flowchart LR
    PA["Provider A"] -->|"Tuyến học từ A"| E["Enterprise AS: không cung cấp transit"]
    E -. "Export sai, không được phép" .-> PB["Provider B"]
    PB -->|"Lan truyền nếu không lọc"| T["Những AS khác"]
    E -->|"Chỉ export prefix được phép"| OK["Route policy đúng"]
~~~

Nếu enterprise không được quyền transit, tuyến học từ A **không nên** được chuyển sang B. Vấn đề ở đây là **đường lan truyền**, ngay cả khi origin AS của prefix trong tuyến nhận từ A là hợp lệ.

## 7. Prefix filtering, AS_PATH filtering và giới hạn bảng tuyến

### 7.1. Prefix allowlist theo quan hệ

Khi nhận prefix từ customer, nên có **danh sách prefix thực sự được ủy quyền** theo registry, IRR, RPKI, hợp đồng và quy trình quản trị của tổ chức. Không nên tự cấp quyền rộng chỉ dựa vào người gửi.

Đối với mạng không cung cấp transit, export policy có thể giới hạn chặt vào tập prefix của doanh nghiệp và những dịch vụ được phê duyệt. Khi đường uplink phục vụ nhiều sản phẩm, cần chính sách phân biệt theo peer và address family IPv4/IPv6.

### 7.2. Prefix length

Một rule prefix filter có thể quyết định:

- Chỉ chấp nhận những prefix **chính xác** trong allowlist.
- Hoặc cho phép các prefix cụ thể hơn **trong giới hạn** nếu nghiệp vụ thực sự cần traffic engineering.
- Từ chối prefix quá ngắn/quá dài theo chính sách Internet transit và loại địa chỉ.

**Không có một quy tắc prefix length tuyệt đối đúng cho mọi mạng**. Các ngưỡng thường gặp ngoài Internet khác nhau giữa IPv4, IPv6, sản phẩm, mục đích peering và chính sách của upstream. Cần đối chiếu với yêu cầu vận hành thật, tránh chọn một ngưỡng rồi coi như bảo mật toàn diện.

### 7.3. AS_PATH filtering

AS_PATH giúp router biết các AS đã xuất hiện trong đường BGP được quảng bá. Quy tắc có thể từ chối tuyến chứa ASN không được mong đợi, có cấu trúc đáng ngờ hoặc vi phạm thỏa thuận peering.

Tuy nhiên, **AS_PATH thông thường không được xác thực mật mã end-to-end**. Một router có khả năng phát UPDATE không đáng tin có thể gửi thông tin AS_PATH sai lệch; dùng regex AS_PATH không phải bằng chứng tuyến an toàn.

### 7.4. Maximum prefix limits

**Max-prefix** giới hạn số lượng route mà peer được phép gửi hoặc số route được tính theo phạm vi hỗ trợ. Khi vượt ngưỡng, thiết bị có thể cảnh báo, từ chối thêm tuyến, ngắt session hoặc xử lý khác.

Ưu điểm: giảm một số rủi ro tràn bảng hoặc lỗi quảng bá hàng loạt. Nhược điểm: ngưỡng quá thấp có thể **ngắt peering hợp lệ khi bảng Internet tăng hoặc dịch vụ mở rộng**.

Trước khi cấu hình cần ghi rõ:

1. Peer truyền **full table**, default route hay một tập prefix được lọc?
2. Chỉ số max-prefix được đếm **trước hay sau chính sách** trên nền tảng đang dùng?
3. Có ngưỡng cảnh báo trước giới hạn cứng không?
4. Khi chạm giới hạn, session có bị reset, shutdown hay chỉ log?
5. Cơ chế tự khôi phục và khả năng rollback ra sao?

## 8. RPKI: xác thực quyền công bố origin AS

**Resource Public Key Infrastructure (RPKI)** là hạ tầng khóa công khai liên kết tài nguyên số Internet (IP prefixes, ASN) với chứng thư tài nguyên và các đối tượng được ký. Một ứng dụng bảo mật định tuyến quan trọng của RPKI là **Route Origin Authorization (ROA)**.

Một **ROA** cho biết một tổ chức nắm quyền tài nguyên đã **ủy quyền một ASN được phép làm origin** cho một prefix, với độ dài prefix tối đa được khai báo (*maxLength*).

**Route Origin Validation (ROV)** sử dụng dữ liệu ROA đã được kiểm tra bởi RPKI validator để đánh giá tính hợp lệ origin của một route BGP.

~~~mermaid
flowchart TD
    H["Chủ quyền tài nguyên IP"] --> ROA["ROA: prefix, ASN, maxLength"]
    ROA --> PKI["Kho đối tượng RPKI được ký"]
    PKI --> V["RPKI validator/cache"]
    V --> VP["Validated ROA Payloads / dữ liệu origin đã xác thực"]
    VP --> RTR["Kênh truyền dữ liệu validator tới router"]
    RTR --> BR["BGP router: Route Origin Validation"]
    BR --> P{"ROV result"}
    P -->|Valid| A["Chính sách có thể chấp nhận"]
    P -->|Invalid| D["Chính sách có thể từ chối"]
    P -->|NotFound| N["Áp dụng chính sách riêng cho unknown origin"]
~~~

**Giới hạn quan trọng:** ROV chỉ kiểm tra **origin AS gắn với prefix**, không xác thực toàn bộ đường AS_PATH, NEXT_HOP, thỏa thuận peering hoặc quyền đọc dữ liệu ứng dụng. Một route leak vẫn có thể mang trạng thái **Valid**.

### 8.1. Ba trạng thái ROV

| Trạng thái | Ý nghĩa | Diễn giải |
| --- | --- | --- |
| **Valid** | Có ít nhất một ROA bao phủ prefix và cho phép origin ASN với prefix length phù hợp | Origin được ủy quyền theo dữ liệu ROA hiện tại |
| **Invalid** | Có ROA bao phủ prefix nhưng không ROA phù hợp nào cho phép đồng thời origin ASN và độ dài công bố | Có thể là hijack hoặc **ROA cấu hình sai** |
| **NotFound** | Không có ROA đủ điều kiện bao phủ route cần kiểm tra | Không có chứng cứ origin qua ROA, **không tự là độc hại** |

Một số triển khai dùng tên **NotFound**, **Unknown** hoặc thuật ngữ tương đương cho trạng thái thiếu ROA; phải đối chiếu cách đặt tên trên nền tảng thực tế.

**Không đánh đồng Invalid với “chắc chắn kẻ tấn công”.** Chủ prefix có thể tạo sai maxLength, đổi nhà cung cấp hoặc chưa cập nhật ROA. Dù vậy, trong chính sách được kiểm chứng và triển khai đầy đủ, **reject Invalid** là một lựa chọn phòng vệ quan trọng của ROV.

## 9. Ví dụ ROA, maxLength và kết quả ROV

Sử dụng hai ASN dành cho tài liệu **AS64496** và **AS64497**, cùng các prefix thuộc dải IPv4 **TEST-NET** được dành cho ví dụ. Những thông tin này **chỉ để học cách so khớp**, không phải route hoặc ROA có thể dùng trên Internet công cộng.

Giả sử RPKI validator trong bài học có một ROA như sau:

~~~yaml
roaExample:
  prefix: 203.0.113.0/24
  authorizedOriginAsn: 64496
  maxLength: 24
  note: "Dữ liệu giả lập trong bài học; không tạo ROA thật cho TEST-NET"
~~~

Đánh giá các BGP announcement:

| Prefix được quảng bá | Origin AS | Kết quả | Giải thích |
| --- | --- | --- | --- |
| 203.0.113.0/24 | AS64496 | **Valid** | Đúng origin và độ dài bằng /24 |
| 203.0.113.0/24 | AS64497 | **Invalid** | Prefix có ROA bao phủ nhưng ASN không được phép |
| 203.0.113.0/25 | AS64496 | **Invalid** | Prefix cụ thể hơn vượt giới hạn maxLength /24 |
| 203.0.113.128/25 | AS64497 | **Invalid** | Sai cả origin và độ dài tối đa |
| 198.51.100.0/24 | AS64496 | **NotFound** | Giả định không có ROA nào bao phủ prefix này |

**maxLength không phải mặc định cho phép mọi more-specific prefix.** Nếu chủ tài nguyên chỉ muốn quảng bá /24, không nên đặt maxLength /25 hoặc /32 cho thuận tiện. Mở rộng maxLength làm nhiều công bố cụ thể hơn đủ điều kiện được gắn **Valid** theo ROV, dù công bố đó có được mong muốn hay không vẫn cần chính sách khác xác minh.

### 9.1. Hai origin ASN cho cùng prefix

Một prefix có thể được quảng bá hợp lệ từ **nhiều AS** theo thiết kế multi-homing hoặc kiến trúc mạng của doanh nghiệp. Trong trường hợp được ủy quyền, chủ tài nguyên có thể cần **nhiều ROA** cho những origin AS thật sự được dùng.

Không tự động xem **MOAS** là chiếm đoạt tuyến, và cũng không tự cấp phép nhiều origin ASN nếu không có bằng chứng nghiệp vụ. Cần rà soát hợp đồng, routing plan, thay đổi dự kiến và quyền tạo ROA.

### 9.2. Một tiền tố khác và giới hạn bao phủ

ROA dành cho **203.0.113.0/24** không xác thực được **198.51.100.0/24** vì không bao phủ dải thứ hai. **NotFound** không đồng nghĩa “ROA bị sai” nếu tài nguyên chưa ký; muốn chuyển sang trạng thái Valid cần chủ tài nguyên công bố ROA thích hợp theo quy trình.

## 10. Triển khai RPKI/ROV an toàn

Một mạng muốn triển khai ROV cần phân biệt hai trách nhiệm:

- **ROA publication:** chủ tài nguyên IP tạo và quản lý quyền origin cho những prefix thuộc quyền họ.
- **ROV enforcement:** router của mạng tiếp nhận sử dụng dữ liệu đã được RPKI validator xác minh để ra quyết định với route BGP đến từ peer.

**ROA chỉ được tạo bởi bên thực sự có quyền đối với tài nguyên.** Một doanh nghiệp không nên tự tạo ROA cho prefix của ISP hoặc đối tác chỉ vì đang dùng tuyến đi qua họ.

### 10.1. Quy trình phía chủ prefix

1. Kiểm kê tất cả prefix công bố, nguồn gốc phân bổ tài nguyên và origin ASN hiện tại.
2. Kiểm tra trạng thái multi-homing, các prefix cụ thể hơn có được phép và đã được thỏa thuận hay chưa.
3. Tạo ROA với **ASN và maxLength tối thiểu phù hợp** từ hệ thống quản lý tài nguyên được ủy quyền.
4. Xác minh dữ liệu ROA đã xuất hiện và validator nhìn thấy trạng thái đúng.
5. Theo dõi origin changes, các Invalid có liên quan và vòng đời khóa/chứng thư.
6. Khi đổi ISP, ASN, traffic engineering hoặc nhà cung cấp, cập nhật ROA theo kế hoạch **trước/sau** thay đổi phù hợp với thời gian lan truyền dữ liệu xác thực.

### 10.2. Quy trình phía mạng nhận route

1. Thiết lập RPKI validator/cache tin cậy, theo dõi độ mới và khả năng truy cập.
2. Kết nối router với validator theo cơ chế được hỗ trợ (thường dùng giao thức **RPKI-to-Router** hoặc cách cung cấp validated payload tương đương).
3. Bắt đầu **observe/monitor**: ghi tỷ lệ Valid/Invalid/NotFound mà chưa thay đổi lớn routing.
4. Xác minh những Invalid trùng với tuyến kinh doanh quan trọng, phối hợp chủ prefix để sửa ROA sai.
5. Chuyển sang **reject Invalid** theo chính sách mạng và change control đã phê duyệt.
6. Kiểm tra các trường hợp validator mất kết nối, dữ liệu stale hoặc rollback khi sự cố.

**Không nên mặc định drop NotFound trên Internet**: nhiều prefix chưa có ROA hợp lệ vẫn có thể là tuyến hoạt động bình thường. Chính sách chấp nhận NotFound nhưng theo dõi và áp dụng các bộ lọc khác thường được đánh giá riêng với chính sách reject Invalid.

### 10.3. Validator mất kết nối hoặc dữ liệu cũ

Router có thể còn giữ dữ liệu đã đồng bộ hoặc thay đổi cách đánh giá khi cache hết hạn, tùy implementation và chính sách. Nếu RPKI validator lỗi, **không suy rằng toàn bộ route lập tức trở thành Invalid**. Phải kiểm tra trạng thái RTR/validator, thời gian dữ liệu, fail mode và mức ảnh hưởng trước khi xử lý.

Một triển khai lớn nên có **khả năng dự phòng**, cảnh báo freshness và quy trình khôi phục. Sử dụng dữ liệu RPKI không đáng tin hoặc quá cũ có thể dẫn đến quyết định không phù hợp với trạng thái ROA hiện hành.

## 11. AS_PATH security, BGPsec, ASPA và route-leak prevention

### 11.1. ROV không xác thực toàn bộ AS_PATH

Giả sử một tuyến đến với đúng origin AS được ROA cho phép, nhưng đi qua một chuỗi AS trái chính sách transit hoặc peering. **ROV vẫn có thể trả Valid**. BGP security phải bổ sung kiểm soát đường lan truyền, lọc peer và các cơ chế phát hiện route leak.

### 11.2. BGPsec

**BGPsec** là cơ chế mở rộng nhằm cung cấp khả năng xác minh mật mã những thành phần đường AS nhất định trong BGP UPDATE với các điều kiện triển khai và tương tác phù hợp. Đây là hướng bảo vệ khác với ROV chỉ dựa trên origin.

Trong thực tế, **khả năng hỗ trợ và mức triển khai BGPsec không đồng đều**, và việc dùng BGPsec không phải lời bảo đảm toàn bộ đường chuyển tiếp dữ liệu hoặc mọi chính sách kinh doanh được xác thực. Một mạng muốn đánh giá phải xác minh tính tương thích thiết bị/peer và chi phí vận hành, thay vì giả định có thể bật BGPsec trên tất cả peering.

### 11.3. ASPA

**Autonomous System Provider Authorization (ASPA)** là một hướng dùng dữ liệu ủy quyền có ký trong hệ sinh thái RPKI để hỗ trợ đánh giá quan hệ provider của AS và phát hiện một số đường lan truyền bất thường, tùy trạng thái chuẩn hóa và mức hỗ trợ tại thời điểm triển khai.

ASPA giải quyết nhóm vấn đề liên quan **đường AS/route leak**, khác trọng tâm ROV. Không nên ghi rằng một mạng đã chống được mọi route leak chỉ vì sử dụng ASPA hoặc coi tính năng là phổ biến ở mọi router. Cần kiểm tra tài liệu tiêu chuẩn và năng lực triển khai đang dùng.

### 11.4. BGP Roles và OTC

Một cơ chế hỗ trợ phòng route leak khác là **BGP Roles** và thuộc tính **Only-to-Customer (OTC)** theo các quy tắc giao thức có liên quan. Peers có thể thống nhất vai trò theo quan hệ customer/provider/peer; những điều kiện OTC được thiết kế để giúp phát hiện hoặc hạn chế việc route vượt qua quan hệ xuất tuyến không được phép.

Vai trò trong BGP **phải phản ánh quan hệ thật và được hai bên cấu hình phù hợp**. Cấu hình sai vai trò hoặc chỉ triển khai một phía có thể gây khác biệt vận hành; không nên tự giả định tính năng đã hoạt động vì thiết bị có hỗ trợ cú pháp.

## 12. Bảo vệ chính phiên BGP

Ngay cả khi import/export policy tốt, phiên BGP cũng cần được bảo vệ để giảm rủi ro kết nối trái phép, giả mạo phiên, làm ngắt peering hoặc gây quá tải control plane.

### 12.1. Peer ACL và giới hạn quyền kết nối

- Chỉ cho địa chỉ peer đã phê duyệt kết nối tới cổng **TCP 179** trên interface hoặc vùng phù hợp.
- Không công bố giao diện quản trị router ra mạng không tin cậy nếu không có nhu cầu được chấp thuận.
- Dùng chính sách chống spoofing tại điểm phù hợp, quản lý route tới peer loopback khi dùng eBGP multihop.
- Đặt control plane vào vùng quản trị riêng, ghi log phiên mới, phiên rớt và các kết nối không phù hợp.

Một ACL cho phép TCP 179 **không tự xác thực đúng router đối tác**. Cần kết hợp xác thực phiên khi có hỗ trợ và xác thực quản trị thiết bị.

### 12.2. TCP MD5 và TCP-AO

Một số BGP deployment dùng **TCP MD5 Signature Option** hoặc **TCP Authentication Option (TCP-AO)** để giúp bảo vệ tính xác thực và toàn vẹn các TCP segment của phiên theo cơ chế giao thức.

| Cơ chế | Ý nghĩa | Cần lưu ý |
| --- | --- | --- |
| **TCP MD5** | Cơ chế xác thực dựa trên khóa chia sẻ được nhiều thiết bị BGP hỗ trợ | MD5 có những hạn chế mật mã và vận hành; cần đánh giá yêu cầu, khả năng thiết bị |
| **TCP-AO** | Cơ chế xác thực TCP hiện đại hơn với khả năng quản lý khóa/phương pháp mật mã linh hoạt | Chỉ sử dụng khi **cả hai peer** và thiết bị thực sự hỗ trợ, đã kiểm thử tương tác |

Những cơ chế này bảo vệ **phiên TCP giữa peer**, không ký toàn bộ chuỗi thông tin định tuyến qua nhiều AS, cũng **không mã hóa dữ liệu người dùng**. Khóa chia sẻ phải được quản lý bí mật, xoay vòng, ghi chủ sở hữu và thay đổi theo quy trình của hai bên; cấu hình không đồng nhất có thể làm peering không lên.

### 12.3. GTSM / TTL Security

**Generalized TTL Security Mechanism (GTSM)** giúp giảm khả năng một số gói BGP giả mạo đến từ nơi cách xa peer bằng việc kiểm tra TTL/Hop Limit theo giả định topology.

Với **eBGP trực tiếp**, các hệ thống có thể sử dụng cơ chế gửi TTL/Hop Limit cao (thường 255) và kiểm tra mức nhận theo quy tắc. Nếu eBGP **multihop**, không được dùng cấu hình TTL Security dành cho một hop mà chưa điều chỉnh theo đường đi thực tế và hỗ trợ nền tảng.

**GTSM không phải xác thực mật mã**, không chống mọi tấn công từ thiết bị lân cận và không thay thế peer ACL hoặc quản lý khóa.

### 12.4. Control Plane Policing (CoPP)

**CoPP** và các kiểm soát CPU của router giới hạn hoặc ưu tiên lưu lượng tới control plane theo chính sách, nhằm giảm nguy cơ các gói không mong muốn làm nghẽn CPU hoặc tài nguyên điều khiển.

Cần tránh cấu hình quá chặt khiến **KEEPALIVE, BFD, TCP 179 hoặc giao thức quản trị hợp lệ** bị drop dẫn đến reset phiên. CoPP cũng không thay thế năng lực lọc ở upstream khi đường vào đã bị bão hòa.

### 12.5. BFD và độ sẵn sàng

**Bidirectional Forwarding Detection (BFD)** có thể giúp phát hiện nhanh mất đường chuyển tiếp và hỗ trợ cơ chế hội tụ, nhưng **BFD không tự là chức năng bảo mật BGP**. Nếu dùng, phải đánh giá tính năng xác thực khi hỗ trợ, CoPP và ảnh hưởng false-positive link failure tới tính ổn định định tuyến.

## 13. Topology ví dụ: doanh nghiệp kết nối hai nhà cung cấp

Giả sử doanh nghiệp vận hành AS64496 và quảng bá một prefix tài liệu **203.0.113.0/24** trong **lab mô phỏng**. Nó kết nối với **Provider A (AS64497)** và **Provider B (AS64498)**. Toàn bộ ASN, IP prefix đều là giá trị dành cho **tài liệu**, không đại diện peering trên Internet thật.

~~~mermaid
flowchart TB
    C["Enterprise AS64496<br/>Prefix minh họa 203.0.113.0/24"] -->|"eBGP, export theo allowlist"| A["Provider A AS64497"]
    C -->|"eBGP, export theo allowlist"| B["Provider B AS64498"]
    A --> X["Mạng ngoài / các AS khác"]
    B --> X
    A -. "Route học từ A không export sang B nếu không được quyền transit" .-> C
    B -. "Route học từ B không export sang A nếu không được quyền transit" .-> C
    C -. "Logs / RPKI / route events" .-> SOC["NOC / SOC monitoring"]
~~~

### 13.1. Chính sách cần có

- **Inbound từ ISP A/B:** chấp nhận những route được thỏa thuận, kiểm tra RPKI ROV nếu dữ liệu sẵn có, xử lý full table/default route theo năng lực và chính sách thực.
- **Outbound đến ISP A/B:** chỉ quảng bá đúng prefix thuộc quyền doanh nghiệp; không quảng bá những route học từ nhà cung cấp còn lại nếu không cung cấp transit.
- **BGP session:** chỉ kết nối tới peer được phê duyệt, dùng cơ chế xác thực phiên nếu hỗ trợ và quản lý khóa đúng quy trình.
- **Availability:** có monitoring session state, latency, route count, convergence, các tuyến dự phòng và phương án rollback.
- **Data plane:** firewall và phân đoạn vẫn kiểm soát đường truy cập giữa DMZ, application, data và management, bất kể tuyến Internet chọn ISP nào.

### 13.2. Ma trận chính sách tuyến

| Nguồn | Đích | Đối tượng | Quyết định dự kiến |
| --- | --- | --- | --- |
| Enterprise | ISP A | Prefix own/authorized | **Export** theo allowlist |
| Enterprise | ISP B | Prefix own/authorized | **Export** theo allowlist |
| Route học từ ISP A | ISP B | Provider-learned route | **Không export** nếu không có quyền transit |
| Route học từ ISP B | ISP A | Provider-learned route | **Không export** nếu không có quyền transit |
| Route origin Invalid | Router edge inbound | RPKI Invalid | Reject theo ROV policy được phê duyệt |
| Route origin NotFound | Router edge inbound | RPKI NotFound | Xử lý theo chính sách; không tự xem là tấn công |
| Route vượt giới hạn prefix | Router edge | Quá ngưỡng đã thiết kế | Cảnh báo và xử lý theo hành vi nền tảng |

### 13.3. Policy minh họa trung lập với sản phẩm

~~~yaml
bgpSecurityPolicy:
  environment: isolated-training-lab
  localAsn: 64496
  ownPrefixes:
    - "203.0.113.0/24"
  peers:
    - name: provider-a
      remoteAsn: 64497
      relationship: provider
      session:
        peerAcl: required
        tcpAuthentication: evaluate-both-ends
        gtsm: evaluate-topology
        controlPlaneProtection: required
      import:
        originValidation: monitor-then-reject-invalid
        prefixPolicy: approved-provider-routes
        maxPrefix: baseline-with-alert-and-rollback
      export:
        allow: own-authorized-prefixes-only
        deny: provider-and-peer-learned-transit-routes
    - name: provider-b
      remoteAsn: 64498
      relationship: provider
      session:
        peerAcl: required
        tcpAuthentication: evaluate-both-ends
        gtsm: evaluate-topology
        controlPlaneProtection: required
      import:
        originValidation: monitor-then-reject-invalid
        prefixPolicy: approved-provider-routes
        maxPrefix: baseline-with-alert-and-rollback
      export:
        allow: own-authorized-prefixes-only
        deny: provider-and-peer-learned-transit-routes
  rpki:
    owner: routing-operations
    localValidatorMonitoring: enabled
    invalidRouteHandling: change-controlled
    notFoundHandling: policy-defined
  operations:
    requirePeerOwner: true
    logAcceptedAndRejectedAnnouncements: true
    monitorPrefixOriginChanges: true
    recordConfigVersions: true
    rollbackTestedInLab: true
~~~

YAML này chỉ thể hiện **nguyên tắc**, không phải cấu hình thiết bị có thể dán trực tiếp vào router. Những giá trị như **baseline-with-alert-and-rollback** cần được chuyển thành ngưỡng cụ thể sau đo đạc; **monitor-then-reject-invalid** là kế hoạch triển khai có giai đoạn, không có nghĩa một rule đồng thời vừa monitor vừa reject.

## 14. BGP security trong cloud, VPN và môi trường hybrid

### 14.1. Kết nối cloud qua BGP

Những mô hình như dedicated interconnect, private connectivity hoặc VPN site-to-site có thể sử dụng BGP để trao đổi tuyến giữa doanh nghiệp và cloud network.

Một rủi ro thường gặp là **quảng bá prefix quá rộng** hoặc nhập nhầm route giữa các VPC/VNet và trung tâm dữ liệu, khiến:

- Mạng quản trị có đường đến những subnet không dự kiến.
- Traffic đi nhầm từ môi trường test sang production.
- Route mặc định chuyển hướng qua cloud/on-premises không mong muốn.
- Đường kết nối dự phòng làm mất reachability hoặc phá mô hình phân đoạn.

Cloud security group và firewall vẫn có thể chặn lưu lượng theo policy, nhưng chúng **không sửa được mọi sai lệch route**. Cần quản lý cả route advertisement, acceptance, IAM cho quyền thay đổi cấu hình và log của gateway.

### 14.2. VPN

VPN thường bảo vệ tính bí mật và toàn vẹn **trên đoạn tunnel** khi cấu hình đúng. Nếu BGP chạy bên trong VPN, điều này bảo vệ đường vận chuyển phù hợp với cơ chế tunnel nhưng **không tự xác thực mọi prefix được quảng bá**.

Do đó vẫn phải dùng **prefix filters, max-prefix, policy theo peer** và các cơ chế bảo vệ BGP tương ứng. Một phiên BGP lên được qua tunnel không có nghĩa peer được phép quảng bá route tới mọi VLAN hoặc subnet nội bộ.

### 14.3. MPLS và kết nối của đối tác

Mạng MPLS hoặc kết nối riêng của nhà cung cấp có thể tạo đường liên thông giữa nhiều địa điểm. Trên những mạng này, BGP route targets, import/export và chính sách phân đoạn cũng cần quản trị chặt chẽ theo sản phẩm.

**Đường riêng không tương đương route an toàn mặc định.** Lỗi quảng bá từ CE/PE hoặc chính sách đối tác có thể làm route xuất hiện sai nơi; cần phân công trách nhiệm rõ ràng giữa enterprise và provider.

### 14.4. IPv6

Doanh nghiệp dual stack cần kiểm soát **cả IPv4 và IPv6 BGP address families**. Prefix filters, ROAs, ROV, max-prefix và monitoring phải xét từng họ địa chỉ phù hợp.

Chỉ bảo vệ IPv4 nhưng quên IPv6 có thể để lại đường chuyển tiếp hoặc công bố tuyến ngoài ý muốn, nhất là khi dịch vụ có bản ghi DNS AAAA và ứng dụng ưu tiên IPv6.

## 15. Giám sát BGP: quan sát cả control plane và trải nghiệm dịch vụ

**Một phiên BGP vẫn ở trạng thái Established không chứng minh route đang đúng.** Để phát hiện route hijack hoặc leak, cần xem cả route được chọn, origin, AS_PATH, thay đổi phạm vi quảng bá và tác động người dùng.

| Nhóm chỉ số | Ví dụ cần quan sát | Ý nghĩa |
| --- | --- | --- |
| Session health | Peer Established/Idle, resets, uptime, notification | Phát hiện mất phiên và bất ổn transport/control plane |
| Prefix counts | Nhận vào/quảng bá, accepted/rejected, max-prefix utilization | Cảnh báo route leak và tràn bảng |
| RPKI | Valid/Invalid/NotFound, validator freshness, RTR state | Phát hiện mismatch hoặc sai trạng thái xác thực |
| Origin monitoring | Origin ASN của prefix doanh nghiệp trên các điểm quan sát | Phát hiện quảng bá khác ASN dự kiến |
| AS_PATH monitoring | Đường AS bất thường, thay đổi lan truyền, route leaks | Phát hiện sai lệch đường đi và export policy |
| Routing churn | UPDATE/withdrawal rate, thay đổi best path | Phát hiện biến động bất thường hoặc flap |
| Data plane | Loss/latency, traceroute có kiểm soát, reachability | Đối chiếu tác động thực tế trên kết nối |
| Business services | DNS success, TLS handshake, API availability | Phân biệt sự cố routing và lỗi ứng dụng |

### 15.1. Vì sao cần điểm quan sát ngoài mạng?

Router nội bộ có thể chỉ biết những route mà peer trực tiếp gửi đến. Để biết prefix doanh nghiệp đang được các AS khác nhìn thấy như thế nào, có thể sử dụng **route collectors, looking glasses, public BGP monitoring hoặc dịch vụ quan sát ngoài mạng** phù hợp.

Không nên kết luận toàn Internet đã thấy route sai chỉ vì một collector có tín hiệu khác thường; các vantage point khác nhau có thể quan sát những đường đi khác nhau. Cần so sánh nhiều nguồn và ghi rõ thời điểm đo.

### 15.2. Log mẫu giả lập

~~~json
{
  "timestamp": "2026-11-28T11:20:00+07:00",
  "event": "bgp_origin_change_candidate",
  "sensor": "training-route-collector",
  "prefix": "203.0.113.0/24",
  "expected_origin_asn": 64496,
  "observed_origin_asn": 64497,
  "rpki_state": "Invalid",
  "observed_at": "synthetic-external-vantage",
  "local_edge_action": "not-yet-verified",
  "classification": "investigate-origin-authority-and-change-window",
  "data_classification": "synthetic-training-event"
}
~~~

Sự kiện trên chỉ là **tín hiệu cần điều tra**, không đủ kết luận AS nào cố ý tấn công. Cần xác minh chủ prefix, ROA, hợp đồng và thay đổi cấu hình có được cấp phép hay không. **Observed origin** là thông tin ở điểm quan sát cụ thể; cần đối chiếu với nhiều nguồn.

### 15.3. Những cảnh báo ưu tiên

- Prefix của tổ chức đột ngột được nhìn thấy với **origin ASN khác** mà không có change ticket.
- Một peer gửi lượng route vượt baseline hoặc xuất hiện nhiều more-specific prefixes ngoài dự kiến.
- Tỷ lệ **RPKI Invalid** tăng bất thường sau thay đổi ROA/peer.
- Export policy thay đổi khiến route học từ provider/peer xuất sang đối tác khác.
- Số phiên BGP reset tăng, BGP notification bất thường hoặc router control plane gần quá tải.
- Đường tới một dịch vụ thay đổi mạnh, đồng thời TLS/API availability suy giảm.

## 16. Quy trình ứng phó khi nghi ngờ BGP hijack hoặc route leak

Một **runbook** tốt cần phân biệt **phát hiện**, **xác thực quyền**, **khoanh vùng tác động**, **giảm thiểu** và **phục hồi**.

### Giai đoạn 1 – Thu thập bằng chứng

1. Ghi **prefix, ASN được dự kiến, origin đang quan sát, AS_PATH, thời điểm, điểm đo và khu vực ảnh hưởng**.
2. Kiểm tra phiên BGP, thay đổi router config, policy, RPKI state và những phiên thay đổi gần đây.
3. Đối chiếu thông tin tài nguyên IP và ROA với đơn vị chủ sở hữu có thẩm quyền.
4. Kiểm tra các sự kiện bảo trì, chuyển ISP, cloud route update, traffic engineering hoặc MOAS đã được duyệt.
5. Xác định người dùng/dịch vụ có bị mất kết nối hay chuyển đường hay không từ nhiều mạng.

### Giai đoạn 2 – Phân loại sơ bộ

| Kết quả ban đầu | Hướng điều tra |
| --- | --- |
| Origin khác dự kiến và RPKI Invalid | Kiểm tra quyền công bố, ROA sai hoặc hijack |
| Origin đúng nhưng AS_PATH/đường lan truyền bất thường | Kiểm tra route leak và thỏa thuận export |
| Phiên BGP reset nhiều nhưng prefix không đổi | Kiểm tra kết nối, session auth, GTSM, CoPP và sự cố thiết bị |
| Route tới một subnet cloud không như kế hoạch | Kiểm tra BGP hybrid, import/export, route table và mạng liên kết |
| Chỉ một collector thấy thay đổi, chưa có tác động | Tiếp tục xác minh vantage point và thời gian cache |

### Giai đoạn 3 – Phối hợp giảm thiểu

Những hành động có thể phù hợp **sau khi xác định nguồn và được phê duyệt**:

- Chỉnh prefix filters hoặc export policy trên router do doanh nghiệp kiểm soát.
- Liên hệ upstream/peer/NOC để yêu cầu kiểm tra, lọc hoặc rút route sai.
- Sửa ROA khi thực sự sai, phối hợp thời gian dữ liệu RPKI được cập nhật.
- Chuyển tuyến dự phòng theo kế hoạch và kiểm tra tác động tới những dịch vụ quan trọng.
- Tăng giám sát và bảo vệ kênh quản trị nếu có dấu hiệu thay đổi trái phép.

**Không nên đối phó bằng cách tùy tiện quảng bá một prefix cụ thể hơn lên Internet.** Việc này có thể bị nhiều mạng lọc, gây thêm mất ổn định, vượt quyền quảng bá và tác động tới các bên khác.

### Giai đoạn 4 – Xác minh phục hồi

1. Đối chiếu accepted/advertised routes ở từng peer.
2. Kiểm tra origin và AS_PATH tại nhiều nguồn quan sát ngoài mạng.
3. Xác minh trạng thái RPKI và cấu hình ROA/validator có nhất quán không.
4. Kiểm tra reachability, DNS/TLS và dịch vụ ứng dụng từ nhiều mạng.
5. Ghi timeline, ticket, quyết định và bài học cập nhật vào runbook.

**Không kết luận đã khắc phục chỉ vì một router thấy route đúng**: cần xem sự lan truyền ngoài mạng và kết quả thật của người dùng.

## 17. Triển khai BGP security theo từng giai đoạn

### Bước 1 – Kiểm kê quyền và topology

Liệt kê ASN, public prefixes, quyền đối với tài nguyên, peer, quan hệ customer/provider/peer, BGP route reflectors, kết nối VPN/cloud và IPAM. Xác định ai có quyền sửa route policy, ROA, peer session, prefix filters và những trạng thái cần phê duyệt.

### Bước 2 – Thiết kế import/export policy

Tạo allowlist theo nguồn và đích, lọc prefix bất hợp lệ, kiểm tra AS_PATH, thiết kế max-prefix và xác định chính sách với full table/default route. Đặt xuất tuyến theo **vai trò và quyền transit thực tế**, không dùng policy allow-all như trạng thái cuối.

### Bước 3 – Bảo vệ kết nối control plane

Giới hạn nguồn tới TCP 179, cơ chế xác thực phiên nếu khả thi, GTSM theo topology, CoPP và phân quyền quản trị router. Kiểm tra thay đổi khóa ở **cả hai phía peer** để tránh mất BGP session.

### Bước 4 – Triển khai ROA và ROV

Chủ prefix chuẩn bị ROA với maxLength phù hợp. NOC triển khai validator, quan sát Valid/Invalid/NotFound, kiểm tra các Invalid hợp lệ phát sinh do cấu hình và thực hiện reject Invalid theo kế hoạch. Cấu hình giám sát dữ liệu cache và đường rollback.

### Bước 5 – Kiểm thử với route mô phỏng

Thử tình huống đúng/sai prefix, sai origin, more-specific, route leak, vượt max-prefix và peer reset **trong lab cô lập**. Không thực hiện quảng bá giả lên public Internet để “kiểm tra”.

### Bước 6 – Triển khai sản xuất có giám sát

Thay đổi theo nhóm peer, có backup cấu hình, change window, người phê duyệt và giám sát tác động. Theo dõi cả route count và kết nối thật, không chỉ BGP Established.

### Bước 7 – Rà soát định kỳ

Cập nhật danh mục prefix, ROA, peer contract, phiên bản router, chính sách export, ký khóa, kiểm thử failover, monitoring ngoài mạng và quy trình incident response.

## 18. Ma trận kiểm thử an toàn trong lab

**Lab phải tách biệt khỏi hệ thống production và Internet routing thật.** Các ASN 64496–64511 và những dải TEST-NET được dùng trong bài để tránh nhầm với tài nguyên công cộng của tổ chức khác. Phép thử chỉ cần tạo **route updates mô phỏng trên router lab** hoặc dùng dữ liệu quan sát được cấp phép; không quảng bá các prefix tài liệu ra Internet.

| Mã | Tình huống kiểm thử | Kỳ vọng |
| --- | --- | --- |
| T-01 | Peer đúng ASN gửi prefix nằm trong allowlist | Được chấp nhận theo import policy |
| T-02 | Peer customer gửi prefix nằm ngoài phạm vi được duyệt | Bị từ chối, có log hoặc counter |
| T-03 | Route /24 có origin và maxLength đúng ROA giả lập | ROV trả Valid |
| T-04 | Cùng /24 nhưng origin khác được ROA cho phép | ROV trả Invalid |
| T-05 | /25 vượt maxLength /24, cùng origin | ROV trả Invalid |
| T-06 | Prefix không được ROA nào bao phủ | ROV trả NotFound, xử lý theo policy đã định |
| T-07 | Router học route từ provider A và thử export sang provider B | Export policy từ chối route leak |
| T-08 | Peer giả lập vượt ngưỡng max-prefix đã thiết kế | Cảnh báo/điều khiển theo đúng hành vi nền tảng |
| T-09 | Thay đổi khóa phiên ở một phía lab | Xác minh phản ứng phiên và runbook khôi phục |
| T-10 | RPKI validator mất kết nối trong lab | Hành vi dữ liệu stale/fail policy đúng thiết kế |
| T-11 | IPv6 prefix của lab có ROV và filter riêng | Chính sách IPv6 hoạt động như kỳ vọng |
| T-12 | Đổi đường ISP dự phòng trong mô phỏng | Route và reachability đúng; không xuất nhầm transit |

### 18.1. Chứng cứ cho từng ca thử

Mỗi ca nên ghi lại:

1. Mã ca thử, topology, phiên bản cấu hình và thời gian.
2. Peer ASN, prefix, hướng import/export và quan hệ peer.
3. ROA giả lập, trạng thái validator và kỳ vọng ROV.
4. Route được chấp nhận/từ chối, lý do, policy/rule ID nếu hệ thống hỗ trợ.
5. Best path, FIB/reachability và biểu hiện tại dịch vụ giả lập.
6. Tác động tới các route khác và cách rollback đã được xác minh.

Không đánh giá thành công chỉ vì một lệnh show BGP chứa prefix: route có thể tồn tại trong bảng nhận nhưng đã bị lọc khỏi bảng tốt nhất, hoặc đã chọn nhưng next hop không reachable.

## 19. Các sai lầm thường gặp

| Sai lầm | Rủi ro | Hướng xử lý |
| --- | --- | --- |
| Chỉ dùng TCP peer password và coi là chống hijack | Origin/prefix sai vẫn có thể được peer hợp lệ gửi | Import/export policy và RPKI ROV |
| Tin mọi route từ peer có kết nối riêng | Route leak hoặc công bố sai lan truyền | Lọc theo quan hệ và quyền prefix |
| Dùng ROV và cho rằng đã bảo vệ cả AS_PATH | Route leak có origin Valid vẫn có thể xảy ra | Policy, BGP Roles/OTC hoặc công nghệ hỗ trợ đường AS |
| Chặn mọi NotFound | Có thể làm mất những route hợp lệ chưa có ROA | Xử lý NotFound theo chính sách và dữ liệu thực |
| ROA maxLength mở quá rộng | Cho phép origin Valid cho nhiều more-specific ngoài nhu cầu | Cấp đúng phạm vi và giám sát |
| ROA sai khi đổi ASN/ISP | Route hợp lệ trở thành Invalid | Phối hợp thay đổi tài nguyên và ROV |
| Max-prefix đặt cứng không có cảnh báo | Peer hợp lệ có thể bị ngắt khi bảng tăng | Baseline, warning, kiểm tra behavior và rollback |
| Không có export filter | Mạng vô tình trở thành transit/route leaker | Allowlist export theo quan hệ |
| Chỉ kiểm tra Established | Không thấy đường đi bị đổi hoặc route sai | Theo dõi prefix, origin, path, service metrics |
| Không kiểm thử IPv6 | Đường IPv6 có chính sách yếu hơn | ROV/filter/monitoring cho cả hai address families |
| Đặt GTSM không xét eBGP multihop | BGP session bị từ chối ngoài ý muốn | Kiểm tra topology và cài đặt hai phía |
| Lộ thông tin quản trị router | Có thể bị thay đổi BGP policy/ROA | AAA/MFA, quyền tối thiểu, audit và phân đoạn quản trị |
| Giải quyết nghi hijack bằng route cụ thể hơn không được phép | Thêm bất ổn, ảnh hưởng mạng khác | Phối hợp upstream, lọc route theo thẩm quyền |

## 20. Tình huống tổng hợp: route leak sau khi thay đổi kết nối cloud

Một doanh nghiệp kết nối hai nhà cung cấp Internet và một cloud gateway có BGP. Sau khi bật một chính sách mới để đưa mạng ứng dụng từ cloud về trung tâm dữ liệu, SOC thấy số route xuất tuyến qua ISP B tăng mạnh. Đồng thời một số đường truy cập có độ trễ bất thường.

**Giả thuyết 1 – Route leak:** router doanh nghiệp đã học các route từ ISP A hoặc cloud rồi xuất sang ISP B ngoài thỏa thuận. Kiểm tra export policy, communities và danh sách route advertised tại ISP B.

**Giả thuyết 2 – Thay đổi được duyệt:** doanh nghiệp đang cung cấp transit hoặc quảng bá thêm prefix đúng quyền theo một kế hoạch đã được phê duyệt. Cần tìm change ticket, hợp đồng và thông tin từ chủ dịch vụ; không mặc định có tấn công.

**Giả thuyết 3 – Route selection thay đổi:** LOCAL_PREF, next hop hoặc route policy làm lưu lượng của doanh nghiệp chọn đường không mong đợi, nhưng không có route leak ra ngoài. Cần kiểm tra best path và reachability từ điểm khác nhau.

**Giả thuyết 4 – RPKI hoặc prefix filtering:** một số route được đánh giá Invalid hoặc rơi ngoài allowlist, khiến traffic chọn đường dự phòng. Phải đối chiếu ROV state, ROA và change window.

### Cách xác minh

1. Ghi bản sao an toàn của route table và export/import policy ở các peer liên quan.
2. Đối chiếu prefix mới, origin, AS_PATH và nguồn đã học với thỏa thuận route.
3. So sánh thông tin từ hai ISP và các nguồn nhìn từ ngoài mạng khi có.
4. Khoanh vùng route sai và đề xuất chỉnh **đúng policy** thay vì tắt toàn bộ BGP.
5. Theo dõi đường kết nối tới API, DB và gateway cloud; xác nhận firewall/segmentation vẫn đúng.
6. Sau thay đổi, xác minh advertised routes trở lại phạm vi được phép và chỉ số dịch vụ phục hồi.

**Kết luận:** ROV Origin Valid là tín hiệu hữu ích nhưng không đủ để chứng minh route không bị leak. BGP security phải bắt đầu từ **quyền công bố và ranh giới export**, rồi kết hợp phát hiện, giám sát và kiểm soát phiên.

## 21. Câu hỏi và bài tập tự kiểm tra

### Câu hỏi 1

BGP security khác firewall packet filtering ở điều gì?

**Gợi ý:** BGP policy ảnh hưởng đường định tuyến và việc công bố prefix giữa các router/AS; firewall quyết định lưu lượng nào được đi qua ranh giới mạng theo policy.

### Câu hỏi 2

Route hijack và route leak khác nhau như thế nào? Vì sao RPKI ROV có thể không phát hiện một route leak?

**Gợi ý:** hijack liên quan quyền origin/công bố prefix; leak là lan truyền tuyến trái chính sách. Origin vẫn có thể đúng dù đường export sai.

### Câu hỏi 3

Một ROA 203.0.113.0/24, AS64496, maxLength 24. Kết quả ROV đối với route 203.0.113.0/25 origin AS64496 là gì?

**Gợi ý:** Invalid vì độ dài /25 vượt maxLength /24 trong ROA bao phủ.

### Câu hỏi 4

NotFound có nên bị coi là Invalid hoặc bị chặn mặc định trong mọi mạng không?

**Gợi ý:** Không. NotFound cho biết chưa có ROA bao phủ; nhiều tuyến hợp lệ chưa có ROA, nên cần policy có đánh giá tác động.

### Câu hỏi 5

Vì sao cùng một prefix có thể xuất hiện từ nhiều origin ASN hợp lệ?

**Gợi ý:** MOAS có thể được ủy quyền trong multi-homing hoặc kiến trúc đặc thù; cần xác minh quyền và ROA tương ứng.

### Câu hỏi 6

TCP MD5/TCP-AO và GTSM bảo vệ khía cạnh nào? Chúng có xác thực chuỗi AS_PATH trên Internet không?

**Gợi ý:** bảo vệ phiên TCP giữa các peer hoặc hạn chế một số nguồn gói từ xa; không ký mật mã toàn bộ đường AS như một thuộc tính BGP chuẩn thông thường.

### Câu hỏi 7

Vì sao doanh nghiệp không cung cấp transit không nên export route học từ Provider A sang Provider B?

**Gợi ý:** điều đó có thể làm mạng trở thành điểm trung chuyển trái thỏa thuận và tạo route leak.

### Câu hỏi 8

Một BGP peer vẫn Established nhưng người dùng mất truy cập dịch vụ. Bạn sẽ xem những gì?

**Gợi ý:** accepted routes, best path, NEXT_HOP, ROV, route table/FIB, điều khiển firewall và khả năng truy cập từ nhiều mạng.

### Bài tập thiết kế trên giấy

Doanh nghiệp **AS64496** có hai ISP, một cloud gateway qua BGP và cần công bố một prefix IPv4 cùng một prefix IPv6 **giả lập**. Hãy:

1. Vẽ topology và ghi rõ quan hệ provider/peer/customer, các trust zone và đường quản trị.
2. Lập bảng import/export cho từng peer, chỉ rõ những tuyến được phép gửi sang ISP khác.
3. Tạo một ROA giả lập có maxLength phù hợp và ba BGP route để phân loại Valid, Invalid, NotFound.
4. Chỉ ra một kịch bản prefix hijack và một kịch bản route leak, cùng log và điểm quan sát cần dùng.
5. Đề xuất kiểm soát phiên TCP 179, bảo vệ control plane, max-prefix và trạng thái khi RPKI validator lỗi.
6. Viết kế hoạch triển khai theo từng giai đoạn và kiểm thử không quảng bá route ra Internet.
7. Đề xuất runbook xử lý sự cố có người chịu trách nhiệm, phương án rollback và cách xác minh tác động ở lớp dịch vụ.

**Tiêu chí đạt:** chính sách tuyến phải mô tả được **ai có quyền công bố prefix, tuyến nào được nhập/xuất, hệ thống xác thực ra sao và làm thế nào để biết thay đổi đang ảnh hưởng người dùng thật**.

## 22. Những điều cần ghi nhớ

- **BGP security bảo vệ việc thiết lập peering và trao đổi/quảng bá tuyến**, không chỉ bảo vệ một phiên TCP hoặc một địa chỉ IP.
- **Prefix hijack** liên quan quyền công bố prefix; **route leak** liên quan lan truyền tuyến trái chính sách. Hai rủi ro cần những biện pháp bổ sung khác nhau.
- **Import/export allowlists, prefix/AS_PATH filtering và max-prefix** là nền tảng bảo vệ định tuyến; phải thiết kế theo quan hệ customer, peer, provider và quyền transit thực tế.
- **RPKI ROA/ROV xác thực origin AS** với trạng thái Valid, Invalid, NotFound; **không** xác thực toàn AS_PATH hoặc đảm bảo data plane không bị chuyển hướng.
- **Chặn Invalid phải dựa trên dữ liệu ROA/validator đáng tin và triển khai có kiểm soát; NotFound không tự là tấn công.**
- **TCP authentication, GTSM, peer ACL, CoPP và quản trị router** giúp bảo vệ control plane, nhưng không thay thế chính sách tuyến hay ROV.
- **BGP Roles/OTC, BGPsec và ASPA** bổ sung hướng bảo vệ đường lan truyền tùy hỗ trợ, không nên coi chúng được triển khai ở mọi mạng.
- **Luôn giám sát origin/path từ cả trong và ngoài mạng, IPv4/IPv6, route count, log và khả năng truy cập dịch vụ.** Một BGP session Established chưa đủ chứng minh routing an toàn.
- **Thử nghiệm trong lab cô lập, quản lý thay đổi, xác minh và rollback** là yêu cầu thiết yếu vì cấu hình BGP sai có thể ảnh hưởng rất rộng.
