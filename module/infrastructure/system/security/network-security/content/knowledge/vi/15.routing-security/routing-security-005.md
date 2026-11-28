# Route leak

> **Chương:** Routing security  
> **Mô-đun:** SECURITY_NETWORK_SECURITY  
> **Trọng tâm:** Hiểu và phòng ngừa rò rỉ tuyến định tuyến BGP vượt phạm vi được phép; phân biệt với route hijack và việc chia sẻ route giữa VRF có chủ đích; thiết kế chính sách import/export, kiểm tra bằng chứng control plane và data plane, giám sát liên AS, ứng phó sự cố và xây dựng kiến trúc mạng phòng vệ nhiều lớp.

## 1. Route leak là gì?

**Route leak** (rò rỉ tuyến) trong bối cảnh **BGP giữa các Autonomous System (AS)** là việc một AS **quảng bá thông tin định tuyến ra ngoài phạm vi phân phối được phép hoặc dự kiến**, khiến các mạng khác có thể chọn một đường đi không phù hợp với quan hệ kết nối và chính sách định tuyến. RFC 7908 mô tả và phân loại những vấn đề này trong định tuyến liên miền.

Ví dụ: một doanh nghiệp kết nối tới **hai nhà cung cấp Internet**. Doanh nghiệp học được nhiều prefix từ Nhà mạng A để sử dụng cho lưu lượng của chính mình, nhưng do lỗi export policy lại quảng bá các tuyến đã học từ A sang Nhà mạng B. B có thể coi tuyến doanh nghiệp quảng bá là tuyến đi qua một **customer**, chọn đường tới doanh nghiệp rồi chuyển traffic cho những prefix không hề do doanh nghiệp cung cấp. Doanh nghiệp bất ngờ bị biến thành **điểm trung chuyển (unintended transit)** và đường đi của traffic có thể thay đổi nghiêm trọng.

**Không phải mọi thông báo BGP bất ngờ đều là route leak.** Một prefix bị một AS lạ tuyên bố là nguồn phát có thể là **route origin hijack**; một subnet bị trộn giữa VRF có thể là **internal route leaking**; hai mạng dùng CIDR chồng lấn có thể là **routing ambiguity**. Chúng liên quan nhưng không giống nhau và cần cách xác minh khác nhau.

Route leak có thể xuất phát từ **lỗi cấu hình**, thao tác thay đổi thiếu kiểm thử, sai quan hệ customer/provider/peer, thiết bị hoặc hệ điều hành mạng bị lỗi, hoặc hành vi cố ý. Đừng mặc định mọi route leak đều là tấn công có chủ đích.

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Diễn giải các khái niệm **AS, eBGP, AS_PATH, prefix, import/export policy, customer/provider/peer** và đường đi **valley-free**.
2. Phân biệt **route leak, route hijack, route injection**, sai lệch **VRF route leaking** và sự cố data plane.
3. Giải thích vì sao **RPKI Route Origin Validation (ROV)** cần thiết nhưng **không tự ngăn mọi route leak**.
4. Xây dựng ma trận phân phối tuyến theo quan hệ BGP và nguyên tắc **default deny / explicit export**.
5. Hiểu cách **BGP Roles và Only-To-Customer (OTC)** hỗ trợ phòng chống route leak theo RFC 9234, cùng các giới hạn triển khai.
6. Thiết kế giám sát từ router, route collector, flow telemetry, hệ thống ứng dụng và dữ liệu từ nhà cung cấp.
7. Thực hiện runbook cô lập, rollback, kiểm tra route propagation và xác minh khôi phục có kiểm soát.

## 2. Nền tảng định tuyến liên miền: AS, BGP và prefix

Internet gồm nhiều **Autonomous System (AS)** do các tổ chức vận hành theo chính sách định tuyến riêng. BGP trao đổi thông tin về **prefix IP** và các thuộc tính của đường đi giữa các router/AS. Trong một mạng doanh nghiệp cũng có thể dùng **iBGP** để chia sẻ route nội bộ, nhưng **route leak liên miền** chủ yếu được bàn đến ở ranh giới **eBGP** giữa các AS.

| Khái niệm | Ý nghĩa | Liên quan route leak |
|---|---|---|
| **AS/ASN** | Tổ chức hoặc miền chính sách định tuyến với số AS | Xác định quan hệ giữa các bên phát/tuyến và trách nhiệm vận hành |
| **NLRI/prefix** | Đích mạng được quảng bá, như 203.0.113.0/24 | Đối tượng có thể bị xuất ra ngoài phạm vi |
| **eBGP peer** | Router BGP ở AS khác | Ranh giới cần import/export policy rõ ràng |
| **AS_PATH** | Chuỗi AS mà thông tin tuyến đã đi qua theo BGP | Hỗ trợ nhận diện đường đi bất thường và ngăn loop thông thường |
| **NEXT_HOP** | Next hop để chuyển traffic theo BGP | Quyết định đường đi data plane khi route được chọn và cài đặt |
| **LOCAL_PREF** | Thuộc tính ưu tiên trong một AS theo chính sách | Có thể khiến một tuyến từ customer được chọn dù không phải đường mong đợi |
| **BGP communities** | Nhãn policy do các bên thỏa thuận sử dụng | Giúp điều khiển export nhưng không tự bảo đảm peer thực thi đúng |
| **RIB/FIB** | Bảng thông tin định tuyến / bảng chuyển tiếp thực tế | Tuyến được học chưa chắc đã là tuyến đang chuyển packet |
| **RPKI/ROV** | Kiểm tra quyền **origin AS** công bố prefix theo ROA | Không kiểm chứng đầy đủ tính đúng của quan hệ transit trong AS_PATH |

**Hai mặt cần quan sát:** **control plane** (BGP nhận, lựa chọn, quảng bá route) và **data plane** (traffic thực tế đi qua router/next hop nào). Một router có thể **nhận** route bị leak mà không chọn làm best path; hoặc một route bị quảng bá ra nhiều peer nhưng ở một số nơi chưa trở thành đường chuyển tiếp thực sự. Không đồng nhất “thấy route trong BGP” với “traffic chắc chắn đã đi theo route đó”.

### 2.1. Tại sao BGP cần policy rõ ràng?

BGP vận hành dựa trên chính sách và thỏa thuận kết nối giữa các mạng. Nó không mặc nhiên hiểu được một AS có được phép **chuyển tiếp traffic giữa hai nhà mạng** hay chỉ được phép truy cập Internet cho chính các prefix của mình.

Do đó kiểm soát ở biên eBGP thường gồm:

- **Import policy:** chấp nhận prefix/AS_PATH/thuộc tính nào từ neighbor.
- **Export policy:** được phép quảng bá prefix nào tới neighbor.
- **Business relationship:** neighbor là customer, provider hay peer.
- **Origin/route validation:** RPKI ROV, prefix filter và các tín hiệu xác thực thích hợp.
- **Operational safeguards:** max-prefix, kiểm soát thay đổi, giám sát và điều phối sự cố.

Không có **explicit export policy**, một lỗi redistribution hoặc policy rộng có thể làm router chuyển nhiều route vốn chỉ để sử dụng nội bộ ra eBGP session.

## 3. Customer, provider, peer và nguyên tắc valley-free

Trong mô hình kinh tế định tuyến Internet phổ biến:

- **Customer** trả phí cho **provider** để được kết nối qua mạng provider.
- **Provider** cung cấp kết nối cho customer và có thể cung cấp transit tới những mạng khác.
- **Peer** trao đổi traffic giữa các mạng theo thỏa thuận peering; peering thường **không đồng nghĩa** hai bên phải chuyển traffic giữa các provider hoặc peer khác của nhau.

Theo nguyên tắc **valley-free** (mô hình chính sách điển hình, không phải quy tắc bắt buộc cho mọi quan hệ thương mại), một AS thường:

- Có thể quảng bá **prefix của mình và route học từ customer** tới customer, peer hoặc provider theo hợp đồng và policy.
- Chỉ quảng bá **route học từ peer hoặc provider** cho **customer** của mình khi cung cấp transit; thông thường **không** đưa route đó sang peer/provider khác.
- Không tự chuyển traffic giữa hai nhà cung cấp hoặc giữa hai peer nếu tổ chức không có trách nhiệm transit tương ứng.

### 3.1. Ma trận export cơ bản

| Route được học từ | Export cho customer | Export cho peer | Export cho provider |
|---|---|---|---|
| **Prefix được AS sở hữu/quảng bá hợp lệ** | Có thể cho phép | Có thể cho phép | Có thể cho phép |
| **Route từ customer** | Thường cho phép | Thường cho phép | Thường cho phép |
| **Route từ peer** | Thường cho phép | **Không** theo valley-free mặc định | **Không** theo valley-free mặc định |
| **Route từ provider** | Thường cho phép | **Không** theo valley-free mặc định | **Không** theo valley-free mặc định |

**Bảng là chính sách tham chiếu**, không phải cấu hình tự động áp dụng cho mọi hợp đồng. Có thể có thỏa thuận transit đặc biệt, partial transit, remote peering, route server ở Internet Exchange, hoặc các ngoại lệ khác. Mọi ngoại lệ phải được **tài liệu hóa, phê duyệt, giới hạn scope và kiểm thử**, không tự suy từ một quan hệ BGP là được phép phát mọi route.

### 3.2. Vì sao gọi là valley-free?

Một đường AS điển hình có thể đi **từ customer lên provider**, sau đó tùy thiết kế qua **một quan hệ peer**, rồi **xuống mạng customer** tới đích. Khi đã chuyển sang nhánh đi xuống, việc bất ngờ tiếp tục “đi lên” qua một provider khác do một AS quảng bá trái policy là một dấu hiệu cần kiểm tra.

~~~mermaid
flowchart LR
    U[AS phía nguồn] -->|Lên provider| P[Provider AS]
    P -->|Peering nếu có| Q[Peer AS]
    Q -->|Xuống customer| D[AS phía đích]
    L[AS multihomed] -. Route đã học từ provider A .-> B[Provider B]
    B -. Unintended transit qua L .-> L
~~~

Không thể quyết định mọi route leak chỉ bằng cách đếm số AS hop. **AS_PATH ngắn hay dài không tự chứng minh policy đúng/sai**; cần biết quan hệ kinh doanh, điều kiện xuất tuyến, thuộc tính BGP và bằng chứng propagation.

## 4. Ví dụ route leak do AS multihomed

Giả sử một tổ chức có **AS65020** kết nối tới hai provider:

- **AS65010 (Provider A):** cung cấp route Internet cho AS65020.
- **AS65030 (Provider B):** cũng cung cấp route Internet cho AS65020.
- **AS65020:** chỉ cần Internet connectivity cho prefix riêng, **không đăng ký cung cấp transit giữa A và B**.

Các ASN và prefix dưới đây là **dữ liệu mô phỏng dành cho học tập**; không phải mạng hoạt động.

~~~mermaid
flowchart TD
    D[Destination prefix 203.0.113.0/24] --> A[Provider A - AS65010]
    A -->|Route được học hợp lệ| C[Doanh nghiệp - AS65020]
    B[Provider B - AS65030] -->|BGP session khác| C
    C -. Lỗi export: quảng bá route học từ A .-> B
    B -. Có thể chọn đường qua customer 65020 .-> C
    C -->|Nếu data plane chuyển tiếp| A
~~~

**Diễn biến:**

1. AS65020 học prefix 203.0.113.0/24 từ A.
2. Một lỗi export policy khiến AS65020 **quảng bá lại tuyến đó cho B**.
3. B có thể nhìn thấy đường AS_PATH đi qua **65020 rồi 65010** và coi đây là tuyến do customer mang tới.
4. Theo chính sách best-path của B, tuyến từ customer đôi khi có **LOCAL_PREF cao hơn** một tuyến từ peer/provider, nên B có thể chọn route qua AS65020.
5. Traffic tới prefix nói trên có thể bị chuyển qua AS65020, nơi không được thiết kế để nhận lượng transit đó.

### 4.1. Những hậu quả có thể xảy ra

- **Nghẽn link:** AS65020 bất ngờ nhận lưu lượng transit lớn.
- **Mất khả dụng:** link, firewall, BGP session hoặc thiết bị chuyển tiếp không đủ công suất.
- **Đường đi dài, không ổn định:** phát sinh latency, packet drop, routing churn.
- **Đường đi không mong đợi:** traffic qua AS, quốc gia hoặc nhà vận hành không được chủ dịch vụ dự kiến.
- **Asymmetric routing:** đường đi và đường về khác nhau, có thể ảnh hưởng stateful firewall, NAT hoặc giám sát.
- **Rủi ro riêng tư:** metadata, địa chỉ hoặc traffic không mã hóa có thể bị quan sát ở tuyến ngoài dự kiến; **TLS/VPN đúng cấu hình vẫn là lớp bảo vệ nội dung**, nhưng không sửa sai đường định tuyến.

**Không chắc B sẽ chọn route leaked:** quyết định còn phụ thuộc import filter, RPKI, LOCAL_PREF, đường đi thay thế và toàn bộ quy trình chọn tuyến. Phân tích phải kiểm tra BGP RIB, route được chọn, export tới các peer tiếp theo và data-plane telemetry.

## 5. Route leak khác route hijack, route interception và internal route leaking

| Hiện tượng | Đặc trưng | Dấu hiệu phân biệt |
|---|---|---|
| **BGP route leak** | Một AS phân phối route học được ra ngoài phạm vi cho phép | Origin AS có thể **vẫn đúng**, nhưng quan hệ transit/đường AS bị sai |
| **Origin hijack** | Một AS công bố prefix như thể chính nó là origin dù không được phép | Origin AS thay đổi, có thể bị RPKI ROV phân loại Invalid |
| **Subprefix hijack** | Công bố prefix **cụ thể hơn** để hút traffic theo longest-prefix match | Độ dài prefix và origin khác kỳ vọng; tùy ROA và chính sách |
| **Route interception** | Traffic bị hút qua đường ngoài dự kiến nhưng vẫn có thể được chuyển tiếp tới đích | Cần bằng chứng data plane, không chỉ AS_PATH |
| **Route blackholing** | Traffic bị chuyển tới đích không trả lời hoặc bị drop có chủ đích | Cần xác định policy RTBH hay lỗi, không mặc định là leak |
| **VRF route leaking** | Nhập/xuất route giữa các bảng định tuyến/tenant trong một mạng | Có thể là **kiến trúc hợp lệ** nếu có policy và trust boundary rõ |
| **CIDR overlap** | Hai site/tenant dùng prefix trùng khi kết nối | Route ambiguity có thể xảy ra ngay cả không có BGP leak |
| **Route redistribution error** | Route từ static/IGP/connected được đưa vào BGP ngoài ý muốn | Có thể gây route leak nếu vượt phạm vi quảng bá được phép |

**Phân biệt quan trọng:** RPKI ROV chủ yếu kiểm tra **prefix–origin AS**. Nếu một route leak **giữ nguyên origin AS hợp lệ** và chỉ thay đổi đoạn trung gian của AS_PATH, RPKI có thể vẫn báo **Valid**. Vì vậy “RPKI Valid” **không đồng nghĩa “đường đi không bị route leak”**.

## 6. Các kịch bản route leak thường gặp

RFC 7908 phân loại nhiều tình huống dựa trên **route được học từ đâu, bị quảng bá cho ai** và tác động. Một số ví dụ dễ nhận biết:

| Tình huống | Lỗi policy chính | Tác động tiềm tàng |
|---|---|---|
| **Customer của hai provider làm transit ngoài ý muốn** | Export route học từ Provider A sang Provider B | Hút traffic qua AS không đủ năng lực |
| **Peer-to-provider leak** | Export route học từ peer tới provider khác | Vi phạm thỏa thuận peering, đổi đường Internet |
| **Provider-to-peer leak** | Export route học từ provider tới peer khác | AS trở thành transit không được dự kiến |
| **Leak nhiều prefix/full table** | Redistribution/export rộng thay vì prefix được phép | RIB/FIB tăng mạnh, tải control plane và downstream |
| **Leak route cụ thể hơn hoặc đặc biệt** | Export nhầm route chỉ dành cho nội bộ/kết nối riêng | Traffic bị chọn về đường lạ, có thể mất dịch vụ |
| **Leak khi thay đổi policy/template** | Route-map/prefix-list/role bị gỡ, đảo điều kiện hoặc sai thứ tự | Một sự kiện triển khai làm nhiều peer nhận sai tuyến |
| **Leak IPv6 AFI/SAFI** | Kiểm soát IPv4 đúng nhưng IPv6 thiếu export filter | Bypass chính sách mong đợi cho IPv6 |

**Cảnh báo:** tên loại và ví dụ ở bảng chỉ giúp học cách nhận diện, **không thay thế** các phân loại chính xác trong RFC hoặc mô hình policy của một AS cụ thể. Khi diễn giải một sự kiện thực, cần xem **trước và sau thay đổi**, đường truyền chính sách, hợp đồng liên kết và công bố của các nhà vận hành.

## 7. BGP path selection: vì sao route bị leak có thể được chọn?

Một route leak chỉ gây thay đổi chuyển tiếp khi router ở đâu đó **chấp nhận và chọn** đường bị leak (hoặc ít nhất quảng bá tiếp khiến AS khác chọn). BGP best-path là quy trình có nhiều thuộc tính và bước lựa chọn, có khác biệt giữa các nhà cung cấp.

Những yếu tố thường liên quan:

- **LOCAL_PREF:** route từ customer có thể được ưu tiên theo chính sách kinh tế hơn route từ peer/provider.
- **AS_PATH:** độ dài đường đi là một tín hiệu trong nhiều triển khai, nhưng không luôn mạnh hơn LOCAL_PREF.
- **Origin validation/filter:** route bị reject vì RPKI Invalid, prefix không được phép hoặc policy AS_PATH sẽ không tham gia chọn.
- **Next hop reachability và IGP cost:** route phải có next hop hợp lệ và điều kiện data plane phù hợp.
- **Các cơ chế khác:** MED, route reflectors, ECMP, multipath, communities và chính sách riêng theo thiết bị.

**Không giả định “AS_PATH dài hơn sẽ tự bị bỏ qua”.** Một tuyến leaked có AS_PATH dài vẫn có thể được chọn nếu policy đặt LOCAL_PREF cao, trong khi một tuyến rất ngắn cũng có thể bị chặn ngay từ import policy.

### 7.1. BGP RIB không đồng nghĩa FIB

| Tầng | Câu hỏi cần xác minh |
|---|---|
| **Adj-RIB-In / received routes** | Neighbor đã gửi gì tới router? Có policy nào chặn trước khi đưa vào RIB? |
| **Local BGP RIB** | Những route nào được giữ, route nào là best path? |
| **Adj-RIB-Out / advertised routes** | Router thực sự quảng bá gì tới từng neighbor? |
| **Routing table / FIB** | Prefix nào được cài để chuyển tiếp, next hop và interface nào được dùng? |
| **Traffic / flow data** | Traffic hợp lệ có thật sự đi theo đường bất thường hay không? |

Một thiết bị không nhất thiết cho xem **đầy đủ Adj-RIB-In hoặc Adj-RIB-Out** nếu chưa bật chức năng tương ứng hoặc do giới hạn nền tảng. Lệnh hiển thị received/advertised routes phải được kiểm tra theo vendor và phiên bản; một số chế độ hiển thị dữ liệu trước/sau policy khác nhau.

## 8. Biện pháp căn bản: kiểm soát import và export theo hợp đồng

**Một route leak là vấn đề chính sách phân phối tuyến**. Cách phòng ngừa quan trọng nhất là **định nghĩa chính xác prefix được nhận, được quảng bá và quan hệ BGP liên quan**.

### 8.1. Export allowlist tại biên

Với doanh nghiệp không cung cấp transit cho mạng khác, policy export đơn giản thường có ý định:

1. Chỉ quảng bá **prefix do doanh nghiệp thực sự được phép phát** và các route nằm trong danh sách được phê duyệt.
2. Không quảng bá cho bất kỳ provider/peer nào các tuyến học từ provider/peer khác.
3. Kiểm soát redistribution từ connected/static/IGP/iBGP, không “redistribute everything”.
4. Có rule mặc định **deny** nếu route không được liệt kê.
5. Kiểm thử cả IPv4 và IPv6, mọi session chính và dự phòng.

### 8.2. Import filter từ customer/peer/provider

| Neighbor | Điều cần kiểm tra khi nhập route |
|---|---|
| **Customer** | Chỉ chấp nhận prefix thuộc phạm vi customer/customer cone được phép quảng bá; route origin và AS_PATH hợp lý theo policy |
| **Peer** | Chấp nhận theo peering agreement, prefix/AS cone phù hợp và khả năng RPKI |
| **Provider** | Kiểm soát prefix mặc định/full/partial table theo hợp đồng, loại các route không mong đợi |
| **Route server tại IXP** | Hiểu mô hình route-server/RS-client và cơ chế truyền AS_PATH, chính sách được IXP áp dụng |

**Prefix filter không phải cứ dài càng tốt**: khách hàng cung cấp transit hợp lệ có thể cần quảng bá các prefix của mạng customer phía dưới. Bộ lọc phải dựa vào **nguồn dữ liệu đăng ký và hợp đồng**, không chỉ chấp nhận một ASN đơn lẻ khi mạng khách hàng thực sự vận hành customer cone.

### 8.3. Policy giả mã cho doanh nghiệp chỉ cần upstream

~~~text
# PSEUDOCODE - KHÔNG chạy trực tiếp trên router.
# Doanh nghiệp AS65020 chỉ được quảng bá prefix riêng.

neighbor Provider_A:
    relationship = customer-to-provider
    import = approved-provider-routes
    export = ONLY(approved-own-prefixes)
    otherwise = DENY

neighbor Provider_B:
    relationship = customer-to-provider
    import = approved-provider-routes
    export = ONLY(approved-own-prefixes)
    otherwise = DENY

route_learned_from Provider_A:
    never_export_to Provider_B unless explicit, approved transit contract

route_learned_from Provider_B:
    never_export_to Provider_A unless explicit, approved transit contract

log changes, verify advertised-routes, enforce change control
~~~

Đây là **đặc tả mong muốn**, không phải cú pháp cho FRRouting, Junos, IOS hoặc một cloud router. Phải chuyển thành route policy cụ thể theo vendor và thử trong môi trường được cấp phép. Quan trọng hơn, với doanh nghiệp nhận **default route** từ hai provider, **đừng bao giờ xuất lại default route** cho provider khác chỉ vì nó đang nằm trong RIB nội bộ.

## 9. RFC 8212: mặc định từ chối eBGP khi thiếu policy

RFC 8212 mô tả hành vi **không nhận và không quảng bá route qua eBGP khi chưa có policy import/export phù hợp**. Tinh thần chính là **không phụ thuộc vào việc thiếu cấu hình lọc để cho phép mọi tuyến**.

Về mặt thiết kế, nên:

- Yêu cầu **explicit import policy** cho mọi phiên eBGP.
- Yêu cầu **explicit export policy** cho mọi phiên eBGP.
- Tạo cảnh báo khi policy bị gỡ, scope quá rộng hoặc tham chiếu vào đối tượng không tồn tại.
- Đưa bài kiểm thử quảng bá tuyến vào pipeline **trước và sau triển khai**.
- Xác minh nền tảng có hỗ trợ và đã bật semantics tương ứng; không giả định mọi router tự triển khai RFC 8212 theo cấu hình mặc định.

**Một policy được đặt tên không bảo đảm an toàn.** Ví dụ policy “EXPORT-ONLY-CUSTOMER” có thể chứa một điều kiện match-all ngoài ý muốn. Cần kiểm tra **nội dung, thứ tự rule, kết quả khi không match và dữ liệu advertised-routes**.

## 10. BGP Roles và thuộc tính OTC theo RFC 9234

RFC 9234 đưa ra cơ chế **BGP Roles** và thuộc tính **Only-To-Customer (OTC)** để giúp phát hiện và ngăn một số dạng route leak. Ý tưởng là cung cấp thêm thông tin về **quan hệ kinh doanh và hướng phân phối tuyến**, thay vì chỉ cố suy luận từ prefix/origin.

### 10.1. BGP Roles

Hai bên ở ranh giới eBGP có thể dùng cơ chế role negotiation theo RFC 9234 để xác nhận quan hệ như **Provider, Customer, Peer** và một số vai trò dành cho route server/route-server client. Ví dụ một phía xem mình là **Provider** thì phía đối diện phải có vai trò tương ứng **Customer** theo semantics của cơ chế.

**Vai trò cấu hình không tự chứng minh quan hệ pháp lý hoặc hợp đồng.** Nó cần được thiết lập đúng bởi các nhà vận hành và có sự hỗ trợ tương thích từ thiết bị hai phía.

### 10.2. Thuộc tính OTC

**OTC** mang tín hiệu để thiết bị có thể xác định route **chỉ được quảng bá tiếp cho customer** theo logic của RFC. Trong một số tình huống route được học từ provider/peer, cơ chế OTC giúp hạn chế việc mang route đó sang những neighbor không phải customer.

| Thành phần | Lợi ích | Giới hạn |
|---|---|---|
| **BGP Roles** | Làm rõ relationship tại eBGP session theo cơ chế chuẩn | Cần cấu hình role đúng và hỗ trợ của thiết bị/neighbor |
| **OTC attribute** | Giúp phát hiện/ngăn các kiểu truyền route không phù hợp relationship | Cần thực thi đúng quy tắc RFC tại các AS liên quan |
| **Import/export filter** | Ràng buộc prefix và scope trong hợp đồng vận hành | Vẫn bắt buộc; role/OTC không thay mọi điều kiện policy |
| **Giám sát AS path** | Phát hiện biến động bất thường ngay cả khi thiết bị chưa hỗ trợ OTC | Tín hiệu cảnh báo, không phải phán quyết tự động |

**Không coi OTC là một “cờ cho phép route an toàn”.** Phải hiểu xử lý cụ thể khi nhận/quảng bá route, cách hệ thống BGP nâng cấp/triển khai hỗn hợp và khả năng có neighbor không hỗ trợ cơ chế. Các trường hợp đặc biệt, route server và hợp đồng transit không chuẩn cần được xem xét theo RFC và vendor documentation.

## 11. RPKI, ROV và lý do Valid vẫn có thể bị leak

**Resource Public Key Infrastructure (RPKI)** cung cấp cơ sở để chủ sở hữu tài nguyên IP công bố quyền gắn **prefix với origin AS** thông qua ROA (Route Origin Authorization). **Route Origin Validation (ROV)** dùng dữ liệu này để phân loại một route BGP về mặt origin.

| Trạng thái thường gặp | Ý nghĩa khái quát | Có chắc không bị route leak? |
|---|---|---|
| **Valid** | Prefix và origin AS phù hợp với một ROA có hiệu lực theo quy tắc validation | **Không.** AS trung gian có thể truyền route sai quan hệ |
| **Invalid** | Có dữ liệu ROA liên quan nhưng origin/max-length không thỏa điều kiện | Không; route có thể là hijack, misconfiguration hoặc sự cố ROA |
| **NotFound/Unknown** | Không có dữ liệu ROA phù hợp để đưa kết luận origin | Không; thiếu bằng chứng origin chứ không xác thực đường đi |

### 11.1. Tình huống minh họa

Prefix **203.0.113.0/24** được origin AS65040 quảng bá hợp lệ. Một AS65020 học route từ Provider A rồi xuất nhầm sang Provider B, **không thay origin AS65040**. Nếu kiểm tra ROA phù hợp, tuyến qua AS65020 có thể tiếp tục được phân loại **RPKI Valid** mặc dù đã bị leak.

**Bài học:** ROV giúp giảm rủi ro **origin hijack**, nhưng không kiểm tra đầy đủ **đường transit có đúng hợp đồng customer/provider/peer hay không**. Muốn phòng chống route leak cần export/import filtering, BGP Roles/OTC khi hỗ trợ và quan sát propagation.

### 11.2. Những kiểm soát bổ sung

- **RPKI ROV ở import** theo policy đã kiểm thử; tránh coi NotFound là tương đương Invalid.
- **IRR/prefix-filter data** với kiểm tra freshness và quyền sở hữu đối tượng; IRR không được mặc định đáng tin tuyệt đối.
- **AS_PATH policy** theo customer cone khi có dữ liệu tin cậy; AS_PATH chỉ là một tín hiệu, không đủ thay kiểm soát quan hệ BGP.
- **BGP communities**, ví dụ NO_EXPORT/NO_ADVERTISE theo RFC 1997 khi phù hợp; chúng có tác dụng giới hạn phổ biến route tùy hành vi xử lý, nhưng không thay policy ở ranh giới.
- **Max-prefix safeguard** để hạn chế sự cố nhận quá nhiều tuyến; không phân biệt tuyến tốt/xấu và có thể khiến session bị ngắt.

### 11.3. Lưu ý về max-prefix

**Max-prefix** là một “hàng rào” vận hành, không phải bằng chứng một route hợp lệ. Nếu customer thông thường chỉ quảng bá vài chục prefix nhưng đột nhiên gửi rất nhiều route, ngưỡng có thể phát cảnh báo hoặc chặn theo cơ chế nền tảng. Tuy nhiên ngưỡng thấp sai sẽ khiến **đường BGP hợp lệ ngừng hoạt động** trong các đợt mở rộng mạng. Cần baseline, khoảng dự phòng, owner và kế hoạch khôi phục.

## 12. Route leak trong mạng nội bộ: VRF và route targets

Trong vận hành doanh nghiệp, từ **route leaking** còn được dùng cho hành động **chia sẻ route giữa các Virtual Routing and Forwarding instances (VRF)** hoặc các bảng định tuyến khác. Đó có thể là một tính năng hợp lệ để một nhóm người dùng truy cập **shared services** như DNS, logging hoặc hệ thống cập nhật.

Ví dụ:

~~~mermaid
flowchart LR
    U[VRF USERS - 10.40.20.0/24] --> F[Policy enforcement / Shared gateway]
    M[VRF MANAGEMENT - 10.40.90.0/27] --> F
    F --> S[VRF SHARED - DNS/Monitoring]
    U --x M
~~~

**Yêu cầu bảo mật:** chỉ import/export prefix cần thiết, xác định đường đi qua firewall/ACL phù hợp, và kiểm tra **chiều về**. Tạo reachability giữa VRF không tự thực thi nguyên tắc least privilege; traffic có thể đi qua định tuyến mà không đi qua firewall mong muốn.

### 12.1. Khác nhau giữa hai nghĩa “route leak”

| Route leak liên AS | VRF route leaking nội bộ |
|---|---|
| Thường mang nghĩa **sự cố** export BGP vượt phạm vi business relationship | Có thể là **cấu hình mong muốn** để chia sẻ một số route |
| Ranh giới **AS/provider/customer/peer** | Ranh giới **VRF/tenant/zone** |
| Phát hiện bằng BGP propagation, AS_PATH, policy neighbor | Phát hiện bằng route import/export, route target, next hop, zone/ACL |
| Rủi ro là đổi đường Internet, transit ngoài ý muốn, gián đoạn | Rủi ro là lộ đường truy cập giữa các zone hoặc sai routing nội bộ |
| Biện pháp trọng tâm là eBGP import/export và RPKI/OTC | Biện pháp trọng tâm là explicit route targets, prefix scope, firewall và segmentation |

**Không tự kết luận** một cấu hình chứa tên “route-leak” là lỗi bảo mật. Phải đối chiếu với kiến trúc và ma trận luồng đã được phê duyệt.

### 12.2. Rủi ro khi leaking route giữa VRF

- Nhập **default route** hoặc subnet quản trị vào VRF khách ngoài ý muốn.
- Export quá rộng prefix liên tenant hoặc mở đường đi **bỏ qua firewall**.
- Gây **asymmetric routing** khiến stateful firewall hoặc NAT không nhận phản hồi đúng.
- Chồng lấn prefix, route recursion hoặc mất khả năng xác định next hop.
- Một thay đổi route target làm mở rộng phạm vi truy cập của workload cloud/on-prem.

Khi dùng EVPN/MPLS VPN hoặc BGP-based VRF, việc **import/export route target** cần được quản lý chặt, nhưng route target không phải một biện pháp xác thực danh tính hoặc phân quyền tầng ứng dụng.

## 13. Route leak trong cloud, VPN và hệ thống lai

### 13.1. Kết nối on-prem qua VPN hoặc Direct Connect/Interconnect

Mạng doanh nghiệp có thể học route từ on-prem, đối tác, VPN, SD-WAN và cloud transit. Một cấu hình sai **route propagation** có thể đưa prefix của đối tác vào một miền không được phép hoặc khiến một site quảng bá nhầm đường mặc định.

Ví dụ có hai kết nối tới cloud, một đường được thiết kế làm primary và một đường chỉ dự phòng. Một lỗi import/export khiến route từ đối tác A xuất ra site B; traffic có thể đi vòng qua mạng không định cung cấp transit.

### 13.2. VPC/VNet và các routing domain

Cloud route table, transit gateway, hub-and-spoke, peering, network virtual appliance và managed VPN có semantics riêng. **Không giả định mọi “propagate route” trong cloud là BGP route leak theo RFC 7908**; nó có thể là lỗi phân phối route nội bộ hoặc route target. Phải kiểm tra **tài nguyên phát route, attachment, bảng route được liên kết, bảng route được propagate, prefix, next hop và policy firewall**.

### 13.3. VLAN/subnet, DNS, Wi-Fi và quản trị

Một route sai có thể cho phép **Guest Wi-Fi** tiếp cận mạng Management, hoặc làm các truy vấn DNS của subnet ứng dụng đi qua resolver không mong đợi. Tuy nhiên **route tồn tại chưa bảo đảm traffic được phép** nếu firewall/ACL thực thi đúng; và **firewall chỉ hiệu quả khi luồng thực đi qua nó**. Khi điều tra, phải xác minh cả định tuyến và enforcement.

Các hệ thống đặc biệt dễ chịu ảnh hưởng: DNS resolver, VPN concentrator, IDS/IPS sensor, log collector, identity provider và đường **out-of-band management**. Nếu thay route làm mất các hệ thống điều khiển này, việc xử lý sự cố có thể khó hơn.

## 14. Threat modeling cho route leak

Để mô hình hóa mối đe dọa, xác định **tài sản định tuyến**, **bên được phép nhận route**, **quyền thay policy**, **vùng traffic có thể bị đổi đường** và **tác động nếu một neighbor truyền sai prefix**.

| Tài sản / trust boundary | Tình huống nguy cơ | Kiểm soát |
|---|---|---|
| **eBGP export tới provider** | Export full table hoặc route học từ provider khác | Explicit allowlist, policy review, advertised-routes test |
| **eBGP import từ customer** | Customer gửi route của provider/peer ngoài quyền | Prefix/customer cone filtering, OTC/roles khi có, max-prefix |
| **RPKI cache/ROA** | Origin validation thiếu, sai hoặc dữ liệu stale | ROV policy, monitoring validator và ROA lifecycle |
| **BGP control plane** | Đổi policy trái phép hoặc session bất thường | RBAC/MFA, quản lý cấu hình, peer authentication theo khả năng, CoPP |
| **VRF/tenant boundary** | Nhập nhầm route của zone nhạy cảm | Import/export scope, ACL/firewall, tests |
| **Cloud transit/VPN** | Propagate prefix ngoài scope hợp đồng | Attachment/route table review, IPAM, cloud flow logs |
| **Data plane** | Traffic đi vòng qua AS, link, firewall hoặc IDS ngoài dự kiến | Flow telemetry, active checks có phép, path comparison |
| **SOC/NOC telemetry** | Không phát hiện leak hoặc không xem được root cause | Route monitoring, config changes, ISP notifications, event correlation |

**Rủi ro tồn dư:** BGP Roles/OTC và ROV có thể không được mọi AS triển khai; sự cố vẫn có thể đến từ phần mạng không do doanh nghiệp vận hành. Do đó phải kết hợp **giảm khả năng phát sai route tại biên của mình** và **giám sát những route liên quan được quan sát từ bên ngoài**.

## 15. Giám sát route leak từ control plane

### 15.1. Nguồn dữ liệu có ích

- **Router BGP state:** neighbors, received/accepted/best routes, advertised-routes, policy version và log update.
- **RPKI validator state:** tỷ lệ Valid/Invalid/NotFound, thời điểm refresh và lỗi đồng bộ.
- **BGP monitoring/route collectors:** dữ liệu public từ các điểm quan sát như **RIPE RIS, RouteViews** hoặc telemetry của provider/monitoring service.
- **Configuration/change management:** diff prefix-list, route-map, policy-statement, neighbor roles, route target và quyền người thay đổi.
- **Flow/traffic telemetry:** bps/pps theo interface và peer, NetFlow/IPFIX/sFlow nếu có, thay đổi next hop hoặc phân bố traffic.
- **Application SLI:** DNS, VPN, HTTPS, API availability, latency và sự cố của đối tác.

**Giới hạn:** route collectors chỉ thấy **những tuyến được các peer của collector quảng bá và cho phép quan sát**; chúng không có bản đồ đầy đủ mọi RIB Internet. Không thấy leak ở một collector **không chứng minh route không bị leak**, cũng như một AS_PATH lạ chưa đủ chứng minh vi phạm hợp đồng.

### 15.2. Những tín hiệu cảnh báo nên theo dõi

| Dấu hiệu | Khả năng cần điều tra | Bằng chứng bổ sung |
|---|---|---|
| **Export route count** tăng đột ngột | Policy match-all, redistribute nhầm, full-table leak | Diff cấu hình, advertised route set, neighbor |
| Customer gửi prefix không thuộc tập được phép | Leak hoặc dữ liệu đăng ký/filter lỗi | IRR, prefix ownership, customer cone, hợp đồng |
| AS_PATH mới cho prefix trọng yếu | Route đi qua AS không mong đợi | Collector đa điểm, provider confirmation, local RIB |
| RPKI Valid nhưng đường AS rất bất thường | Route leak vẫn có thể xảy ra | Relationship/role, route propagation, OTC |
| Link transit và CPU router tăng | Traffic hút qua AS trung gian | Flow logs, interface counters, FIB |
| Tăng BGP updates/withdrawals | Route churn hoặc policy đang thay đổi | Session logs, timing, route collector |
| Nguyên tắc route boundary bị vi phạm | Guest/management/partner VRF nhìn thấy prefix lạ | VRF route table, route target, enforcement |
| Delay/packet loss sau đổi route policy | Đường đi mới không đủ năng lực hoặc bất đối xứng | Traceroute có phép, path telemetry, app SLI |

### 15.3. Baseline trước khi alert

Baseline nên theo từng **neighbor/AFI/SAFI, prefix set, số route được quảng bá, các AS_PATH thường thấy và volume traffic**. Một provider đổi peering policy, bảo trì link hoặc traffic engineering hợp lệ có thể khiến AS_PATH thay đổi. Vì vậy alert nên gắn **impact và thay đổi thực tế**, không chỉ số lượng AS hop tăng.

## 16. Phân tích BGP control plane bằng lệnh chỉ đọc

Các ví dụ dưới đây là **mang tính minh họa**. Chỉ chạy trên router hoặc lab có quyền truy cập; tên lệnh và kết quả phụ thuộc vào phần mềm/vendor. Trong quá trình đầu tiên, **không chạy clear BGP, shutdown neighbor, chỉnh policy hoặc redistribute** để “thử xem sao”.

### 16.1. Ví dụ với FRRouting vtysh

~~~bash
# Kiểm tra trạng thái eBGP và số route theo address family IPv4
vtysh -c 'show bgp ipv4 unicast summary'

# Xem đường BGP của một prefix tài liệu (chỉ có nếu lab có prefix này)
vtysh -c 'show bgp ipv4 unicast 203.0.113.0/24'

# Xem route đang quảng bá cho neighbor trong lab (thay IP neighbor phù hợp)
vtysh -c 'show bgp ipv4 unicast neighbors 192.0.2.1 advertised-routes'

# Kiểm tra bảng route mà hệ điều hành đang dùng
ip route
ip -6 route
~~~

Lệnh **advertised-routes** và khả năng hiển thị received-routes/adjacency tùy cấu hình FRR và version. Đừng coi output một câu lệnh là bằng chứng chắc chắn policy được thực thi đúng ở mọi hop.

### 16.2. Ví dụ trên hệ thống router có CLI khác

~~~text
# Cú pháp là tên tác vụ cần tìm trên vendor CLI, KHÔNG phải lệnh chung.
show BGP neighbors and session states
show routes received or accepted from a specific peer
show routes advertised to a specific peer
show best path and associated AS_PATH, NEXT_HOP, LOCAL_PREF
show route-policy / prefix-list match and counters
show RPKI origin-validation state
show FIB route and interface/next hop
show BGP update, change and session logs
~~~

**Dữ liệu quan trọng là hai tập riêng biệt:** route **được nhập** và route **được xuất** tới từng neighbor. Rất nhiều cấu hình route leak xuất phát từ export policy; chỉ xem bảng route tổng không đủ.

### 16.3. Phân tích data plane với quyền kiểm tra

~~~bash
# Tìm tuyến từ host/router Linux tới một đích được phép kiểm thử
ip route get 203.0.113.24

# Kiểm tra tuyến IPv6 nếu lab có route tương ứng
ip -6 route

# Quan sát interface traffic/error counters
ip -s link show
~~~

Đối với route Internet thực, có thể so dữ liệu traceroute/flow telemetry **tại điểm quan sát được phép**. Nhưng traceroute có thể bị ảnh hưởng bởi ACL, ICMP rate limit, ECMP, MPLS, NAT hoặc đường đi bất đối xứng; nó **không chứng minh đầy đủ AS-level path**. Cần đối chiếu với BGP RIB và dữ liệu từ nhà vận hành.

## 17. Điều tra sự cố: minh họa một thay đổi export policy sai

### 17.1. Bối cảnh

Doanh nghiệp AS65020 kết nối eBGP đến Provider A (AS65010) và Provider B (AS65030). Theo policy được duyệt, doanh nghiệp chỉ quảng bá prefix do mình quản lý. Sau một change window, B bắt đầu nhìn thấy nhiều prefix có origin thuộc các AS không phải 65020 qua AS_PATH chứa **65020 65010 ...**.

### 17.2. Tín hiệu có thể xuất hiện

| Mốc giả định | Nguồn | Quan sát |
|---|---|---|
| 09:00 | Change management | Triển khai phiên bản route policy mới |
| 09:03 | Router AS65020 | Advertised-route count tới B tăng bất thường |
| 09:05 | Provider B | Route nhận từ customer AS65020 vượt profile dự kiến |
| 09:07 | Monitoring | BGP collector nhìn thấy AS_PATH mới qua 65020 |
| 09:09 | NOC | Link tới B tăng traffic, packet drop xuất hiện |
| 09:11 | SRE | VPN hoặc API latency tăng do path bất đối xứng |

**Đây là timeline mô phỏng.** Phân tích thực phải đối chiếu mốc giờ, version cấu hình, nguyên nhân tăng route count, route được B chấp nhận/best path và tác động user-facing.

### 17.3. Câu hỏi điều tra cần trả lời

1. Route bị nghi leak **được học từ đâu**, quảng bá cho **neighbor nào**, và có nằm ngoài hợp đồng không?
2. Prefix và origin AS có thay đổi hay chỉ **AS_PATH transit** thay đổi?
3. Router có **thực sự quảng bá** tuyến ra B sau policy, hay chỉ có trong local RIB?
4. B đã **nhận/chấp nhận/chọn** tuyến hay bị import filter loại bỏ?
5. Có traffic thực đi qua AS65020, gây nghẽn, latency hoặc mất phiên không?
6. Sự kiện bắt đầu sau **thay đổi nào**, tác nhân/owner nào và rollback version nào?
7. Có cả **IPv6** hoặc VRF/cloud propagation cùng thay đổi không?

Khi báo sự cố, phân biệt **suspected leak**, **confirmed policy violation** và **observed traffic impact**. Đây là các mức kết luận khác nhau.

## 18. Runbook ứng phó route leak

### Giai đoạn 0 — Chuẩn bị trước sự cố

1. Lưu **inventory AS/ASN, peering/provider/customer relationships, sessions, prefix scope, IPv4/IPv6 và policy owner**.
2. Có **versioned import/export policy**, danh sách prefix được phép và test trước triển khai.
3. Định nghĩa người chịu trách nhiệm ở NOC, SOC, Network Engineering, ISP và đối tác.
4. Tích hợp **BGP session/update logs, advertised-route counts, RPKI state, collector alerts, flow telemetry và service SLI**.
5. Chuẩn bị rollback qua change control, kênh liên lạc ngoài băng và phương án khi mất một uplink.

### Giai đoạn 1 — Phát hiện và xác minh

- Ghi thời điểm, prefix/AFI/SAFI, neighbor và AS_PATH bất thường.
- Đối chiếu **policy được phê duyệt** với route thực sự nhận/quảng bá.
- Kiểm tra **RPKI Valid/Invalid/NotFound**, nhưng không dùng ROV làm kết luận duy nhất.
- Xác minh có phải route leak liên AS hay chỉ route target/VRF import được phép.
- Kiểm tra tác động **user-facing**, không chỉ biểu đồ BGP.

### Giai đoạn 2 — Khoanh vùng và giảm thiểu có phê duyệt

Nếu route được xác nhận đã export ngoài ý muốn, lựa chọn ưu tiên thường là **khôi phục export policy đúng và ngăn tiếp tục quảng bá sai** tại nguồn. Việc sửa có thể dẫn tới BGP withdraw/update và thay đổi đường đi diện rộng, nên phải theo **runbook được cấp quyền**, có phương án rollback và phối hợp ISP/neighbor.

| Hành động ở mức quyết định | Lợi ích | Rủi ro cần đánh giá |
|---|---|---|
| Khôi phục export allowlist trước khi thay đổi | Ngừng phát route ngoài phạm vi theo policy đã duyệt | Thay đổi nhanh có thể thu hồi cả route hợp lệ nếu baseline sai |
| Thêm filter nhận tuyến ở provider/peer liên quan | Giảm tác động khi downstream còn nhận route leaked | Cần phối hợp provider và xác minh prefix khách hàng hợp lệ |
| Thu hẹp redistribution/route target | Chặn nguồn route không đúng vào BGP/VRF | Có thể ảnh hưởng dịch vụ dựa vào đường route đó |
| Giảm/thu hồi policy ngoại lệ có thời hạn | Hạn chế phạm vi rủi ro | Phải biết mục đích ngoại lệ |
| Tạm ngắt BGP session bằng quy trình khẩn cấp | Có thể hạn chế lan truyền khi không kiểm soát được policy | **Đánh đổi lớn:** có thể mất Internet connectivity, VPN hoặc nhiều dịch vụ |
| Kiểm soát đường đi với provider | Hỗ trợ chặn propagation ngoài phạm vi | Cần xác nhận provider nhận route nào và route đã truyền cho ai |

**Không tự thực thi lệnh clear BGP, shutdown session hoặc thay LOCAL_PREF trên production** chỉ vì thấy AS_PATH lạ. Chúng có thể gây outage nghiêm trọng hơn hoặc làm tình hình khó khôi phục.

### Giai đoạn 3 — Theo dõi withdraw và phục hồi

Một khi policy đã được sửa, route cũ có thể cần **thời gian hội tụ** và phụ thuộc cách downstream xử lý BGP updates. Phải theo dõi:

- Số prefix được **advertise/accept** sau sửa đúng phạm vi.
- BGP route collectors ở nhiều điểm không còn thấy path ngoài ý muốn khi có độ phủ.
- Downstream/provider xác nhận route leaked đã được withdraw hoặc không còn được chọn.
- **FIB/flow data** không còn đưa traffic qua transit bất ngờ.
- Packet drop, latency, DNS/VPN/API SLI hồi phục.
- Các prefix hợp lệ vẫn quảng bá và truy cập được qua uplink chính/dự phòng.

**Không xem việc một session BGP đã về Established là đủ kết luận sự cố kết thúc.** Session có thể hoạt động bình thường trong khi export policy vẫn sai.

### Giai đoạn 4 — Hậu kiểm

Tổng kết **nguyên nhân gốc, policy version, phạm vi prefix/neighbor/AS bị tác động, data plane impact, thời gian phát hiện, quyết định giảm thiểu, thời gian hồi phục và rủi ro còn lại**. Bổ sung test CI, policy linting, peer-role validation, RPKI, giám sát và điều khoản phối hợp với provider khi cần.

~~~mermaid
flowchart TD
    A[Alert: route/path/advertised count bất thường] --> B[Kiểm tra policy và quan hệ neighbor]
    B --> C{Đã xác minh export/import ngoài scope?}
    C -- Chưa --> D[Đối chiếu collector, provider, RIB và change log]
    D --> B
    C -- Có --> E[Giữ bằng chứng, đánh giá tác động và điều phối owner]
    E --> F[Khôi phục policy đúng / phối hợp upstream theo phê duyệt]
    F --> G[Theo dõi withdraw, best path, FIB và traffic]
    G --> H{Route đúng và dịch vụ phục hồi?}
    H -- Chưa --> E
    H -- Rồi --> I[Hậu kiểm, test regression và ngăn tái diễn]
~~~

## 19. Kiểm thử phòng vệ mà không tạo route leak thật

**Không tự quảng bá full table, prefix không thuộc quyền quản lý hoặc route giả ra Internet để “kiểm thử”.** Các thao tác BGP có thể ảnh hưởng nhiều mạng ngoài phạm vi sở hữu. Nên kiểm thử ở **lab cô lập, hệ thống mô phỏng policy, snapshot RIB và config diff**, hoặc diễn tập với nhà cung cấp theo phạm vi được phê duyệt.

### 19.1. Ma trận kiểm thử tham chiếu

| Test | Tình huống | Kết quả mong đợi | Bằng chứng |
|---|---|---|---|
| **T-01** | Doanh nghiệp export prefix của chính mình tới hai provider | Chỉ các prefix đã phê duyệt được quảng bá | Adj-RIB-Out/advertised route set |
| **T-02** | Có route học từ Provider A, kiểm tra export tới Provider B | Không xuất route của A sang B nếu không có hợp đồng transit | Policy test và advertised routes |
| **T-03** | Customer gửi route của provider/peer ngoài quyền trong lab | Import policy từ chối | Neighbor policy counters và local RIB |
| **T-04** | RPKI Invalid route trong môi trường test | Policy ROV áp đúng hành động đã duyệt | Origin validation state và route decision |
| **T-05** | RPKI Valid nhưng route mô phỏng vi phạm valley-free | Hệ thống giám sát/phòng vệ quan hệ vẫn phát hiện | Role/OTC, relationship policy hoặc alert |
| **T-06** | Thiếu policy import/export tại session thử | Mặc định deny theo chuẩn thiết kế | Router config và test result |
| **T-07** | Quá ngưỡng max-prefix trong lab | Hành vi cảnh báo/bảo vệ đúng thiết kế, không ảnh hưởng production | Logs, threshold và failback test |
| **T-08** | Thay policy trên IPv4 và IPv6 | Không có address family nào quảng bá sai scope | Per-AFI advertised routes |
| **T-09** | Route leak có chủ đích giữa VRF Users và Shared Services | Chỉ prefix cần thiết được import, traffic đi qua policy gateway | VRF tables, ACL/firewall logs |
| **T-10** | Thử thay route target giữa tenant trong lab | Không mở đường giữa tenant trái policy | Route targets, route tables, reachability |
| **T-11** | Sự kiện export policy bất thường được mô phỏng bằng log | Alert hiển thị neighbor, prefix, version và owner | SOC/NOC alert, ticket và timeline |
| **T-12** | Khôi phục phiên bản policy trước trong lab | Prefix hợp lệ không mất, route ngoài scope được loại | CI test, RIB/FIB snapshots |
| **T-13** | Một collector không thấy route nhưng provider báo có | Hệ thống không kết luận false negative từ một nguồn | Nhiều vantage points và xác nhận provider |
| **T-14** | Data plane thay đổi sau policy | Route thực không bypass firewall/IDS quan trọng | Flow logs, FIB, service SLI |

### 19.2. Cấu trúc policy-as-code minh họa

~~~yaml
# Chính sách mong muốn phục vụ review/CI; không phải cú pháp router.
bgp_edge_policy:
  local_asn: 65020
  role: "enterprise-customer-no-transit"
  own_prefixes:
    ipv4: ["198.51.100.0/24"]
    ipv6: ["2001:db8:20::/48"]
  peers:
    - name: "provider-a"
      asn: 65010
      relationship: "provider"
      import: "approved-provider-routes"
      export: "only-own-prefixes"
    - name: "provider-b"
      asn: 65030
      relationship: "provider"
      import: "approved-provider-routes"
      export: "only-own-prefixes"
  safeguards:
    default_import: "deny-without-explicit-policy"
    default_export: "deny-without-explicit-policy"
    check_ipv4_and_ipv6: true
    require_change_owner: true
    max_prefix: "tuned-per-neighbor-not-a-static-global-number"
    rpki_rov: "follow-approved-policy"
    bgp_roles_otc: "enable-only-when-roles-and-support-validated"
  regression_tests:
    - "never-export-provider-a-learned-routes-to-provider-b"
    - "never-export-provider-b-learned-routes-to-provider-a"
    - "export-only-approved-own-prefixes"
    - "verify-advertised-routes-per-neighbor-and-afi"
~~~

Các prefix và ASN trong khối đều dành cho **minh họa nội bộ**. Chính sách production cần dùng prefix sở hữu thực, quan hệ neighbor thực và trình biên dịch/cấu hình theo nền tảng. **Một file policy-as-code chỉ có ích nếu kết quả được deploy và RIB quảng bá thực tế khớp với policy**.

## 20. Các tình huống vận hành và cách suy luận

### Tình huống A — Provider nhận route tăng bất thường sau cấu hình mới

**Hiện tượng:** sau deploy, số prefix xuất tới một provider tăng mạnh nhưng BGP session vẫn Established.

**Phân tích:** kiểm tra change diff, match sequence, prefix-list, redistribution và advertised-routes. Phân biệt route hợp lệ từ customer cone với route học từ provider/peer. Khôi phục export policy đã xác minh theo quy trình khi phát hiện trái scope, phối hợp provider xác nhận withdraw.

**Bài học:** sức khỏe phiên BGP không đại diện cho sự đúng đắn của chính sách route.

### Tình huống B — RPKI Valid nhưng AS_PATH khác thường

**Hiện tượng:** route của một prefix quan trọng có origin AS hợp lệ, nhưng một AS vốn chỉ là customer lại xuất hiện thành transit giữa hai provider.

**Phân tích:** xem relationship, OTC/role (nếu triển khai), AS_PATH, collector đa điểm, import/export policy và flow telemetry. **ROV Valid chỉ hỗ trợ kiểm tra origin**, nên không được loại trừ khả năng route leak.

### Tình huống C — Cloud guest network truy cập được mạng quản trị

**Hiện tượng:** một VRF/VPC route propagation rule làm mạng Guest biết route tới Management.

**Phân tích:** đây là **internal route leaking** hoặc policy routing sai, không nhất thiết là route leak liên AS. Kiểm tra attachment, route target, route tables, ACL/firewall và đường đi/về. Sửa route propagation và enforcement, không chỉ xóa một entry tạm.

### Tình huống D — Max-prefix khiến mất một eBGP session

**Hiện tượng:** provider mở rộng hợp lệ lượng prefix, hoặc mạng customer tăng quy mô; router vượt ngưỡng max-prefix và áp cơ chế bảo vệ khiến traffic gián đoạn.

**Phân tích:** xác minh thay đổi được phê duyệt, số prefix thực, baseline và lý do threshold. Không chỉ tăng ngưỡng vô hạn vì “cần session lên”; phải giữ biện pháp phát hiện abnormal route count.

### Tình huống E — IPv4 ổn nhưng IPv6 có đường bất thường

**Hiện tượng:** route policy IPv4 đã chặn đúng export leak nhưng IPv6 vẫn quảng bá route học từ neighbor ngoài scope.

**Phân tích:** kiểm tra **AFI/SAFI, prefix-set IPv6, export policy của neighbor, RPKI IPv6 và advertised-routes IPv6**. Cần regression tests tách theo address family.

### Tình huống F — Route collector không thấy lỗi, người dùng vẫn chậm

**Hiện tượng:** NOC có báo cáo latency tăng và provider nói từng nhận route không đúng, nhưng một collector public không ghi lại AS_PATH bất thường.

**Phân tích:** collector chỉ có **vantage point giới hạn**; có thể không thấy peer hoặc route không được chọn/quảng bá tới collector. Cần kiểm tra local/provider RIB, flow data, FIB và mốc thay đổi.

## 21. Checklist bảo vệ routing khỏi route leak

- [ ] Biết đầy đủ ASN, prefix sở hữu, AS business relationships và người chịu trách nhiệm từng eBGP session.
- [ ] Có **explicit import/export policy** cho mọi neighbor, theo từng address family; không mặc định cho phép mọi route.
- [ ] Doanh nghiệp không cung cấp transit chỉ xuất **prefix được phê duyệt**, không xuất route đã học từ provider/peer khác.
- [ ] Với ISP/customer networks, import filter dựa trên prefix được phép và customer cone thực.
- [ ] Đã review redistribution static/IGP/connected và các biến thể default route.
- [ ] Có kiểm soát **RPKI ROV** thích hợp, hiểu Valid không đồng nghĩa không có leak.
- [ ] Xem xét **BGP Roles/OTC theo RFC 9234** khi thiết bị và các neighbor hỗ trợ, cấu hình role phù hợp.
- [ ] Có max-prefix và cảnh báo route-count bất thường theo baseline của từng neighbor, không dùng một ngưỡng chung.
- [ ] Kiểm thử **IPv4/IPv6**, peering chính/dự phòng, route server, VPN/cloud và các đường redistributions.
- [ ] Có giám sát **received/accepted/advertised routes**, AS_PATH, policy version, update/withdraw và route origin validation.
- [ ] Có giám sát từ **nhiều nguồn/vantage point** và phối hợp provider, không dựa vào một collector duy nhất.
- [ ] So control plane với FIB/flow data, packet loss, DNS/VPN/API availability và đường qua firewall/IDS.
- [ ] Hạn chế quyền sửa BGP policy; có MFA/RBAC, peer management security và audit cấu hình.
- [ ] Có policy-as-code hoặc cơ chế review diff, test regression trước khi triển khai.
- [ ] Không để default route hoặc route nhạy cảm bị leak giữa VRF/tenant/zone mà thiếu firewall/ACL.
- [ ] Có runbook xác minh, khôi phục export policy và điều phối provider trước thao tác ảnh hưởng production.
- [ ] Có rollback, đường quản trị dự phòng và phương án khi một BGP session bị ngắt.
- [ ] Giữ bằng chứng timeline, config version, route propagation và tác động thực tế để hậu kiểm.
- [ ] Kiểm tra route mới sau failover, thay đổi provider, mở rộng customer, cloud transit hoặc thay route target.

## 22. Câu hỏi tự kiểm tra

**1. Route leak khác origin hijack như thế nào?**  
Route leak thường là phân phối route vượt scope dù origin AS có thể còn đúng; origin hijack là AS công bố prefix như origin không được phép. Cả hai có thể xảy ra đồng thời trong sự cố phức tạp.

**2. Doanh nghiệp có hai provider có nên quảng bá route từ Provider A sang Provider B không?**  
Thông thường **không** nếu doanh nghiệp không ký hợp đồng cung cấp transit. Export nên chỉ cho phép prefix được sở hữu hoặc scope được phê duyệt.

**3. Vì sao RPKI Valid không chứng minh không có route leak?**  
ROV kiểm tra prefix và origin AS; nó không xác thực đầy đủ quan hệ kinh doanh hoặc tính hợp lệ của mọi AS trung gian trên AS_PATH.

**4. Valley-free có phải luật kỹ thuật tuyệt đối cho mọi mạng không?**  
Không. Đây là mô hình quan hệ định tuyến phổ biến; hợp đồng peering/transit đặc biệt có thể khác. Cần kiểm tra policy cụ thể của các AS liên quan.

**5. BGP Roles/OTC giúp giải quyết vấn đề nào?**  
Chúng hỗ trợ nhận diện quan hệ neighbor và hạn chế route bị truyền sang neighbor không phù hợp theo RFC 9234. Cần hỗ trợ và cấu hình đúng ở các bên, không thay import/export policy.

**6. Tại sao session BGP Established vẫn có thể đang leak?**  
Established chỉ cho biết phiên BGP hoạt động; policy vẫn có thể quảng bá các route không được phép.

**7. Max-prefix có chặn mọi route leak không?**  
Không. Một leak chỉ có vài prefix vẫn có thể nguy hiểm; max-prefix phát hiện lượng route quá lớn và có thể gây ngắt session nếu ngưỡng đặt sai.

**8. Route xuất hiện trong BGP RIB đã chắc chắn được dùng để chuyển traffic chưa?**  
Chưa. Cần xem best path, FIB, next hop và dữ liệu flow; router có thể giữ route nhưng không chọn.

**9. VRF route leaking có luôn là lỗ hổng không?**  
Không. Chia sẻ route giữa VRF có thể phục vụ DNS hoặc shared services. Vấn đề phát sinh khi vượt scope, bỏ qua trust boundary hoặc thiếu enforcement.

**10. Tại sao không nên clear eBGP session ngay khi thấy một AS_PATH lạ?**  
Vì route có thể là thay đổi hợp lệ và thao tác session có thể làm mất Internet/VPN hoặc ảnh hưởng nhiều mạng. Phải thu bằng chứng, xác minh policy và điều phối hành động theo runbook.

## 23. Tài liệu tham khảo

- [RFC 7908 — Problem Definition and Classification of BGP Route Leaks](https://www.rfc-editor.org/rfc/rfc7908): định nghĩa và phân loại rò rỉ tuyến BGP.
- [RFC 9234 — Route Leak Prevention and Detection Using Roles in UPDATE and OPEN Messages](https://www.rfc-editor.org/rfc/rfc9234): BGP Roles và OTC.
- [RFC 8212 — Default External BGP (EBGP) Route Propagation Behavior without Policies](https://www.rfc-editor.org/rfc/rfc8212): yêu cầu policy rõ ràng cho import/export eBGP.
- [RFC 7454 — BGP Operations and Security](https://www.rfc-editor.org/rfc/rfc7454): thực hành vận hành và bảo vệ BGP.
- [RFC 4271 — A Border Gateway Protocol 4 (BGP-4)](https://www.rfc-editor.org/rfc/rfc4271): nền tảng protocol và thuộc tính BGP.
- [RFC 6811 — BGP Prefix Origin Validation](https://www.rfc-editor.org/rfc/rfc6811): mô hình kiểm tra origin của route dựa trên RPKI.
- [RFC 6480 — An Infrastructure to Support Secure Internet Routing](https://www.rfc-editor.org/rfc/rfc6480): tổng quan hạ tầng RPKI.
- [RFC 1997 — BGP Communities Attribute](https://www.rfc-editor.org/rfc/rfc1997): cơ chế communities và các giá trị điều khiển phân phối route.
- [MANRS — Mutually Agreed Norms for Routing Security](https://www.manrs.org/): các chuẩn thực hành cộng đồng về lọc route, chống spoofing, phối hợp và xác minh thông tin định tuyến.
- [RIPE RIS — Routing Information Service](https://ris.ripe.net/): hệ thống quan sát BGP theo các vantage point công cộng.
- [University of Oregon RouteViews](https://www.routeviews.org/): dữ liệu thu thập định tuyến phục vụ quan sát và phân tích.

**Ghi nhớ:** Route leak là vấn đề **quảng bá tuyến vượt phạm vi chính sách**, không nhất thiết là giả mạo origin. Phòng vệ hiệu quả dựa trên **quan hệ customer/provider/peer rõ ràng, import/export allowlist, RPKI ROV kết hợp kiểm soát đường đi, BGP Roles/OTC khi hỗ trợ và giám sát route propagation từ nhiều phía**. Khi xử lý sự cố, phải xác minh **control plane lẫn data plane**, bảo vệ các tuyến hợp lệ và điều phối thay đổi với nhà mạng thay vì thao tác BGP production khi chưa có bằng chứng.
