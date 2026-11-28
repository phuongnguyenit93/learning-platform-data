# RPKI: Xác thực quyền công bố prefix trong định tuyến BGP

## 1. RPKI là gì và tại sao cần?

**Resource Public Key Infrastructure (RPKI)** là hạ tầng khóa công khai dùng để tạo và kiểm tra những xác nhận có chữ ký số liên quan đến **quyền sử dụng tài nguyên số Internet**, chủ yếu là các dải địa chỉ IP và số hiệu hệ tự trị (**Autonomous System Number — ASN**). Ứng dụng quan trọng của RPKI trong định tuyến Internet là tạo và kiểm chứng **Route Origin Authorization (ROA)**: xác nhận một hệ tự trị nào được tài nguyên IP cho phép **khởi phát một prefix BGP**.

RPKI thuộc chương **Routing security** của học phần **SECURITY_NETWORK_SECURITY**. Nó bổ sung cho phòng vệ nhiều lớp gồm phân đoạn mạng, firewall, VPN, IDS/IPS, bảo vệ DNS, giám sát lưu lượng và kiến trúc mạng an toàn. Nếu các lớp này kiểm soát kết nối hoặc lưu lượng trong mạng, RPKI tập trung vào một câu hỏi ở **mạng liên miền Internet**: *Thông báo một prefix BGP với origin ASN như vậy có phù hợp một ủy quyền đã được xác thực hay không?*

**Tình huống:** một tổ chức sở hữu prefix IP và để nhà mạng AS64496 công bố prefix này ra Internet. Nếu một AS khác bất ngờ phát thông báo có cùng prefix nhưng tự nhận mình là origin, các mạng thực hiện **Route Origin Validation (ROV)** có thể phát hiện thông báo đó là **RPKI Invalid**, với điều kiện có ROA phù hợp và dữ liệu xác thực được cập nhật. Từ đó, mạng nhận route có thể từ chối hoặc giảm ưu tiên route sai theo chính sách vận hành.

RPKI **không bảo đảm** rằng mọi route trên Internet đều được bảo vệ, không chứng thực toàn bộ đường đi AS_PATH và không thay thế các biện pháp chống tấn công trên router. Cần phân biệt **cấp phát tài nguyên**, **ủy quyền origin**, **xác thực origin**, và **quyết định chọn route BGP**.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Mô tả mối quan hệ giữa prefix, origin ASN, BGP và rủi ro route hijack.
2. Giải thích trust anchor, resource certificate, ROA, VRP, validator, RTR và ROV.
3. Phân loại route thành **Valid**, **Invalid** hoặc **NotFound** bằng điều kiện prefix/ASN/maxLength.
4. Thiết kế ROA an toàn cho mạng single-homed, multihomed và giai đoạn chuyển nhà cung cấp.
5. Phân biệt trạng thái xác thực RPKI với chính sách cho phép/loại route của router.
6. Đề xuất lộ trình triển khai, dự phòng validator, kiểm soát thay đổi, logging và xử lý sai ROA.
7. Xác định giới hạn của RPKI và cách kết hợp với prefix filtering, IRR, BGP policy và các cơ chế bảo vệ khác.

## 2. BGP origin và các rủi ro định tuyến

**BGP (Border Gateway Protocol)** là giao thức định tuyến liên miền được các hệ tự trị sử dụng để trao đổi khả năng tiếp cận các prefix IP. Một thông báo BGP thường có một **NLRI/prefix** và các thuộc tính, trong đó có thông tin **AS_PATH**. Khi phân tích xác thực origin, hệ thống lấy ra **origin ASN** theo quy tắc của BGP và chuẩn áp dụng.

Ví dụ minh họa:

~~~text
Prefix:        203.0.113.0/24
Origin ASN:    AS64496
AS_PATH:       64497 64496  (minh họa góc nhìn từ một peer)

Ý nghĩa: route này biểu đạt prefix 203.0.113.0/24
được khởi phát bởi AS64496, sau đó đi qua AS64497.
~~~

AS64496 và AS64497 là các ASN **dành cho tài liệu** theo RFC 5398. Prefix 203.0.113.0/24 là dải **TEST-NET-3** theo RFC 5737. Ví dụ không nhằm mô tả route thực sự có thể sử dụng trên Internet công cộng.

### 2.1. Một số tình huống rủi ro

| Tình huống | Điều gì xảy ra? | RPKI Origin Validation giúp gì? |
| --- | --- | --- |
| **Origin hijack** | AS không được ủy quyền công bố một prefix với origin của chính nó | Có thể đánh dấu Invalid nếu có ROA/VRP bao phủ prefix và không khớp |
| **More-specific hijack** | AS khác công bố subnet chi tiết hơn để thu hút traffic theo longest-prefix match | Có thể Invalid nếu subnet nằm trong ROA bao phủ nhưng origin/maxLength không được phép |
| **Lỗi vận hành của chính chủ sở hữu** | AS thật công bố prefix với origin khác ROA hoặc dài hơn maxLength | Cũng có thể Invalid: chữ ký không phân biệt nhầm lẫn và ác ý |
| **Route leak** | Một mạng truyền route ra peer/nhà mạng không đúng quan hệ chính sách | RPKI origin validation **không trực tiếp xác minh đường truyền route** |
| **AS_PATH giả mạo với origin hợp lệ** | Thông báo mạo nhận đường đi nhưng giữ origin phù hợp ROA | ROV có thể vẫn xem origin Valid; cần bảo vệ đường đi/bộ lọc bổ sung |
| **Công bố prefix chưa có ROA** | Không có thông tin xác nhận origin phù hợp trong tập dữ liệu xác thực | Thường là **NotFound**, không tự đồng nghĩa tấn công |

RPKI đặc biệt hữu ích trước một số **origin hijack**, nhưng không loại trừ toàn bộ các con đường gây thay đổi hướng lưu lượng. Một route **Valid** theo ROA vẫn có thể bị thao túng ở các khía cạnh không thuộc phạm vi xác thực origin.

### 2.2. Longest-prefix match và more-specific

Trong chuyển tiếp IP, router thường ưu tiên tuyến có **prefix cụ thể hơn** khi nhiều tuyến cùng khớp địa chỉ đích. Vì vậy việc công bố một more-specific có thể ảnh hưởng hướng đi traffic dù mạng vẫn công bố aggregate.

Tuy nhiên, một more-specific được RPKI đánh giá Invalid không có nghĩa nó chắc chắn đang được Internet chấp nhận. Những chính sách lọc prefix, giới hạn độ dài prefix ở các nhà mạng và điều kiện truyền bá BGP **hoạt động độc lập** với kết quả RPKI. Ví dụ một prefix IPv4 /25 thường bị nhiều mạng lọc theo chính sách độ dài, nhưng nó vẫn có thể dùng để **minh họa logic kiểm tra maxLength** trong lab.

## 3. Kiến trúc RPKI: Từ quyền tài nguyên đến router

RPKI dựa trên chuỗi chứng chỉ và dữ liệu được ký để xác nhận một tổ chức có quyền phát hành thông tin liên quan đến tài nguyên IP/ASN được ủy quyền. Thông thường các tổ chức đăng ký Internet như **RIR** vận hành hạ tầng và trust anchor theo phạm vi tài nguyên; chủ thể nắm giữ tài nguyên tạo ROA thông qua dịch vụ/cơ chế được cấp quyền.

~~~mermaid
flowchart TD
    TA[Trust anchor / TAL] --> CERT[Chuỗi resource certificates]
    CERT --> ROA[ROA đã ký: prefix / origin ASN / maxLength]
    ROA --> PUB[Kho công bố RPKI<br/>RRDP hoặc rsync]
    PUB --> VAL[RPKI relying-party validator]
    VAL --> VRP[Validated ROA Payloads - VRPs]
    VRP --> RTR[Cache-to-router / RTR]
    RTR --> ROUTER[BGP router chạy ROV]
    BGP[BGP update từ peer] --> ROUTER
    ROUTER --> POLICY[Chính sách import / best path]
~~~

Sơ đồ tách biệt **khâu kiểm tra chữ ký** và **khâu áp dụng chính sách định tuyến**. Một router triển khai ROV thường không phải tự tải từng chứng chỉ và ROA từ Internet; nó lấy **VRP đã được validator kiểm tra** qua giao thức hoặc cơ chế cung cấp dữ liệu phù hợp.

### 3.1. Trust anchor và TAL

**Trust anchor** là gốc tin cậy dùng để bắt đầu xác minh chuỗi chứng chỉ RPKI. **Trust Anchor Locator (TAL)** cung cấp thông tin để relying party tìm và nhận diện khóa/gốc tin cậy phù hợp. Một validator cần có danh sách TAL được quản lý, cập nhật và kiểm soát nguồn cung cấp.

Không đánh đồng trust anchor với “danh sách IP được phép vào firewall”. Trust anchor liên quan đến **xác minh chữ ký và quyền trên tài nguyên số**, chứ không trực tiếp là ACL truy cập mạng.

### 3.2. Resource certificate

Chứng chỉ tài nguyên trong RPKI gắn khóa công khai với **tập IP prefix và/hoặc ASN được ủy quyền**. Chuỗi chứng chỉ cho phép validator kiểm tra rằng chủ thể ký ROA có quyền đối với tài nguyên được khai báo, tuân theo hiệu lực và các ràng buộc tương ứng.

Một chứng chỉ hợp lệ chỉ cung cấp một phần bằng chứng; validator còn cần xử lý trạng thái hết hạn, thu hồi, cấu trúc đối tượng, danh sách công bố và tính nhất quán của dữ liệu.

### 3.3. ROA — Route Origin Authorization

**ROA** là đối tượng ký số xác nhận một **origin ASN** được phép công bố một hoặc nhiều prefix với độ dài prefix tối đa tương ứng. Với mỗi prefix trong ROA, thuộc tính **maxLength** giới hạn mức độ chi tiết của những route có thể được xem là khớp về độ dài.

Một cấu hình ROA minh họa có thể được mô tả:

~~~yaml
# Minh họa ý nghĩa của một mục ROA, KHÔNG phải cú pháp đối tượng RPKI đã ký.
origin_asn: AS64496
prefix: 203.0.113.0/24
max_length: 24
~~~

Đối tượng ROA thực tế có cấu trúc và chữ ký theo chuẩn RPKI; bản YAML ở đây **chỉ diễn giải ý nghĩa**, không thể đưa trực tiếp vào router để tạo ủy quyền.

### 3.4. VRP — Validated ROA Payload

Sau khi xác minh chuỗi tin cậy và ROA, validator tạo các **Validated ROA Payloads (VRP)** mà bộ định tuyến dùng làm đầu vào xác thực origin. Mỗi VRP biểu diễn thông tin tương ứng với:

~~~text
VRP = (IP prefix, maxLength, origin ASN)
VD:  (203.0.113.0/24, 24, AS64496)
~~~

**Phân biệt:** ROA là **đối tượng có chữ ký** trong kho RPKI; VRP là **kết quả dữ liệu đã được validator xác minh** để router so khớp với thông báo BGP. Người quản trị không nên coi một danh sách VRP tự nhập bằng tay là tương đương chuỗi xác minh RPKI thực sự.

### 3.5. Repository, RRDP và rsync

Các đối tượng RPKI được công bố qua hạ tầng repository. Validator thường thu thập dữ liệu bằng các cơ chế được hỗ trợ như **RPKI Repository Delta Protocol (RRDP)** hoặc **rsync**. Nó xác minh chứng chỉ, ROA, trạng thái thu hồi và tính hợp lệ của dữ liệu rồi tạo tập VRP mới.

Một lỗi tải repository có thể khiến tập VRP **bị cũ hoặc thiếu** nếu hệ thống không xử lý nguồn dữ liệu đúng cách. Do đó cần theo dõi trạng thái cập nhật, thời gian dữ liệu và các cảnh báo xác minh thay vì chỉ nhìn kết nối từ router tới validator.

### 3.6. RTR và ROV

**RPKI-to-Router (RTR)** là giao thức đưa VRP đã được xác minh từ validator/cache đến router. **Route Origin Validation (ROV)** là quá trình router dùng VRP để đánh giá origin của route nhận từ BGP.

RTR **không tự thay thế việc xác minh chữ ký ở validator**. Cần bảo vệ kênh trao đổi validator–router bằng mạng quản trị/ACL và phương pháp bảo mật phù hợp với triển khai, cũng như theo dõi việc router dùng dữ liệu cũ. Router vẫn có **BGP import policy** riêng để quyết định nhận, từ chối hay giảm ưu tiên một route.

## 4. Quy tắc Valid, Invalid và NotFound

Giả sử router đang xác minh một route có **prefix P** và **origin ASN A** dựa trên tập VRP hợp lệ.

Một VRP có thể **bao phủ (cover)** route nếu:

1. Route và VRP thuộc **cùng họ địa chỉ** (IPv4 hoặc IPv6).
2. Prefix route là **bằng hoặc cụ thể hơn** (nằm hoàn toàn trong) prefix của VRP.

Từ đó phân loại:

| Trạng thái | Điều kiện |
| --- | --- |
| **Valid** | Có **ít nhất một VRP bao phủ** và đồng thời **origin ASN trùng** với route, **độ dài route không vượt maxLength** của VRP đó |
| **Invalid** | Có **ít nhất một VRP bao phủ**, nhưng **không VRP nào** cho phép đồng thời origin ASN và độ dài prefix route |
| **NotFound** | **Không có VRP nào bao phủ** route trong tập dữ liệu đang dùng |

Tên trạng thái NotFound cũng có thể được hiển thị là **Unknown** hoặc **Not Validated** tùy công cụ. Quan trọng là phân biệt nó với **Invalid**. Trạng thái NotFound **không tự có nghĩa route xấu**; nó chỉ thiếu dữ liệu ủy quyền origin trong tập VRP đã được validator cung cấp.

### 4.1. Bảng ví dụ theo một VRP

Giả định tập VRP dùng cho lab **chỉ có**:

~~~text
Prefix = 203.0.113.0/24
MaxLength = 24
Authorized origin = AS64496
~~~

| BGP route được kiểm tra | Origin ASN | Trạng thái | Lý do |
| --- | --- | --- | --- |
| 203.0.113.0/24 | AS64496 | **Valid** | ASN khớp và /24 không vượt maxLength 24 |
| 203.0.113.0/24 | AS64497 | **Invalid** | Prefix có VRP bao phủ nhưng origin ASN khác |
| 203.0.113.0/25 | AS64496 | **Invalid** | Origin đúng nhưng /25 dài hơn maxLength 24 |
| 203.0.113.128/25 | AS64497 | **Invalid** | Vừa khác ASN vừa vượt maxLength |
| 198.51.100.0/24 | AS64497 | **NotFound** | Không có VRP bao phủ prefix này |
| 203.0.112.0/23 | AS64496 | **NotFound** | Prefix /23 rộng hơn VRP /24 nên không nằm trong VRP |

Hai ví dụ /25 và /23 dùng để **hiểu logic xác thực**, không phải khuyến nghị công bố các độ dài đó lên Internet công cộng. Chúng có thể bị lọc bởi chính sách prefix khác dù trạng thái RPKI ra sao.

### 4.2. Một prefix có thể có nhiều VRP hợp lệ

Đôi khi một prefix cần được công bố với **nhiều origin ASN hợp pháp** trong kiến trúc nhiều nhà mạng hoặc quá trình chuyển đổi. Có thể tồn tại nhiều ROA/VRP cho cùng hoặc các prefix liên quan.

Giả sử thêm VRP:

~~~text
(203.0.113.0/24, maxLength 24, AS64497)
~~~

Khi đó route **203.0.113.0/24 origin AS64497** trở thành **Valid** trong tập VRP minh họa, vì **ít nhất một VRP** bao phủ và cho phép nó. Một VRP khác không khớp **không làm route Invalid** nếu đã có VRP khớp đủ điều kiện.

Đừng tự giả định mọi kiến trúc nhiều nhà mạng đều cần nhiều origin ASN. Một mạng có thể quảng bá qua nhiều upstream nhưng giữ **một origin ASN duy nhất**. ROA phải phản ánh **origin trong BGP thật**, không phải mọi ASN của các nhà mạng transit nằm trong AS_PATH.

### 4.3. maxLength và rủi ro mở quá rộng

Giả sử có ROA cho **203.0.113.0/24, AS64496**:

| maxLength | Các độ dài có thể khớp cùng origin (trong phạm vi /24) | Đánh đổi |
| --- | --- | --- |
| **24** | Chỉ /24 | Chặt nhất nếu chỉ công bố aggregate /24 |
| **25** | /24 hoặc /25 | Cho phép more-specific /25, kể cả khi chưa thực sự cần |
| **32** | Từ /24 đến /32 | Mở rộng đáng kể quyền origination cho các more-specific |

Chọn **maxLength nhỏ nhất đủ cho các công bố BGP hợp pháp**, và xem xét ROA cụ thể cho prefix thực sự được công bố. maxLength rộng làm tăng tập các route có thể được đánh giá Valid nếu kẻ xấu có thể phát thông báo với **origin ASN khớp** nhưng qua đường không hợp pháp; RPKI **không** xác minh toàn bộ AS_PATH.

Không đặt maxLength bằng /32 (IPv4) hoặc /128 (IPv6) như thói quen chung. Kích thước và policy route thực sự phải được phê duyệt bởi nhóm định tuyến.

## 5. Thuật toán kiểm tra origin ở mức khái niệm

Một cách trực quan để mô tả ROV:

~~~text
input:
    route = (prefix_P, origin_ASN_A)
    vrps = tập VRP đã được validator xác minh

covering = [
    v in vrps
    where v.address_family == route.address_family
      and route.prefix nằm trong v.prefix
]

if covering rỗng:
    return NOT_FOUND

for each v in covering:
    if route.origin_ASN == v.origin_ASN
       and route.prefix_length <= v.maxLength:
        return VALID

return INVALID
~~~

Đây là **giả mã học thuật**, không xử lý mọi chi tiết BGP origin-AS extraction, AS_SET, cập nhật từng phần, cache consistency hoặc lỗi parsing. Router và validator thực tế phải tuân theo các RFC và phần mềm tương ứng. Không tự phát triển một ROV engine production chỉ từ đoạn giả mã này.

### 5.1. Những điều dễ nhầm trong điều kiện so khớp

- **Prefix không có ROA** nhưng nằm hoàn toàn ngoài mọi VRP liên quan: **NotFound**, không phải Invalid.
- **Origin ASN khớp** nhưng route quá cụ thể so với maxLength: **Invalid**.
- **Prefix được VRP bao phủ** nhưng origin ASN sai: **Invalid**, kể cả khi ASN đó là transit AS thật.
- **Nhiều VRP**, trong đó một VRP cho phép đầy đủ: **Valid**.
- **Route prefix rộng hơn VRP** (không phải subnet của VRP): thường **không được VRP đó bao phủ**.
- **RPKI Invalid** không tự nói nguyên nhân là tấn công; một ROA sai cũng gây Invalid.
- **RPKI Valid** không tự bảo đảm traffic được chuyển theo đúng đường, không chứng minh ứng dụng đích an toàn.

## 6. ROV và quyết định nhận/chọn route BGP

Xác thực origin và **chính sách định tuyến** là hai bước tách biệt. Router có thể dùng trạng thái RPKI như một điều kiện trong chính sách import, nhưng vẫn xét route-policy, prefix-list, AS-PATH, local preference, quan hệ peer và các thuộc tính BGP khác.

~~~mermaid
flowchart TD
    B[BGP update nhận từ peer] --> F[Chính sách cơ sở: peer/prefix/AS path]
    F --> R[Kiểm tra origin với VRP]
    R --> S{RPKI state}
    S -->|Invalid| D[Thông thường từ chối theo policy đã thử nghiệm]
    S -->|Valid| N[Tiếp tục kiểm tra route policy và best path]
    S -->|NotFound| U[Xử lý theo policy, không mặc định coi là tấn công]
    N --> T[Cân nhắc cài tuyến / quảng bá tiếp theo]
    U --> T
~~~

Lưu đồ minh họa cách **thiết kế policy**, không phải thứ tự cứng của mọi router hay tất cả các bước ra quyết định BGP. Một router có thể đánh giá điều kiện ROV ở các pha khác nhau tùy phần mềm và cấu hình.

### 6.1. Có nên chặn tất cả Invalid?

**Reject Invalid** là chính sách phòng vệ được nhiều mạng áp dụng khi triển khai ROV. Nó có thể làm giảm khả năng những route có origin sai được chấp nhận. Tuy nhiên:

- Một tổ chức **tạo nhầm ROA** cũng có thể làm route hợp pháp trở thành Invalid và bị mạng khác từ chối.
- Chỉ nên bật enforcement sau khi kiểm tra **nguồn VRP, phạm vi peer, trạng thái ROA của prefix sở hữu, dự phòng validator, telemetry và phương án rollback**.
- Không áp dụng chính sách “chặn NotFound như Invalid” một cách tự động: NotFound thường chỉ biểu thị chưa có VRP phù hợp.
- Hành vi xử lý khi validator mất kết nối hoặc dữ liệu hết hạn là một quyết định **riêng**, không đồng nghĩa một route đã được xác thực Invalid.

### 6.2. Valid không có nghĩa bắt buộc chọn route

Hai route cùng prefix có thể đều Valid nhưng đi qua đường AS khác nhau. BGP tiếp tục áp dụng chính sách và quá trình chọn best path. Những route khác không khớp prefix-list, vi phạm quan hệ peering hoặc chứa thông tin AS_PATH bất thường vẫn có thể bị từ chối dù origin Valid.

### 6.3. RPKI hỗ trợ nhưng không thay thế policy peering

RPKI không xác thực tất cả các hop trong AS_PATH, cũng không xác minh mục đích kinh doanh của một quan hệ transit/customer/peer. Bởi vậy nó cần kết hợp với:

1. **Prefix filter** theo dải mà khách hàng/peer được phép công bố.
2. **AS-PATH policy** và kiểm soát quan hệ peering.
3. **Max-prefix limits** và giám sát các thay đổi đột biến.
4. **IRR-based filtering** khi phù hợp và có dữ liệu đáng tin.
5. **BGP session security** và bảo vệ management plane.
6. **ROV** như một tín hiệu bổ sung về quyền origin của prefix.

## 7. Thiết kế ROA an toàn cho tài nguyên của tổ chức

RPKI chỉ giúp xác thực đúng nếu **ROA phản ánh những route BGP được phép công bố thực sự**. Quá trình tạo, sửa và xóa ROA phải được quản lý như thay đổi quan trọng về định tuyến, không phải một thao tác tài liệu vô hại.

### 7.1. Kiểm kê trước khi phát hành ROA

Với mỗi prefix có quyền quản trị, cần xác định:

| Thuộc tính | Câu hỏi cần trả lời |
| --- | --- |
| Quyền tài nguyên | Tổ chức nào đang có quyền quản lý prefix trong chuỗi chứng chỉ RPKI? |
| Độ dài prefix | Prefix thực tế được công bố là /24, /48 hay more-specific nào khác? |
| Origin ASN | ASN nào **đứng ở vị trí origin** trong các thông báo BGP hiện tại và dự kiến? |
| Nhà cung cấp/upstream | Những nhà mạng nào chuyển tiếp route? Có thay đổi origin ASN hay chỉ đổi đường đi? |
| Multihoming/anycast | Có nhiều origin ASN hợp pháp cho cùng prefix hay không? |
| maxLength | Có cần cho phép các more-specific không, và cho phép chính xác đến độ dài nào? |
| Vòng đời | Khi nào bắt đầu dùng origin mới, và khi nào thu hồi quyền origin cũ? |
| Owner/phê duyệt | Nhóm nào duyệt thay đổi, ai có quyền tạo/xóa ROA, ai giám sát? |

**Không tạo ROA cho mọi upstream AS** chỉ vì các AS đó nằm trong AS_PATH. Nếu tổ chức sử dụng **AS64496 làm origin** và AS64497 chỉ vận chuyển route, ROA cho AS64496 có thể đã phù hợp. ROA dành cho ASN khác chỉ cần khi **ASN đó thật sự là origin được phép**.

### 7.2. Single-origin

Giả sử tổ chức muốn công bố duy nhất:

~~~text
BGP origin: AS64496
IPv4 prefix: 203.0.113.0/24
No more-specific announcements
~~~

Một mục ủy quyền đơn giản có thể là:

~~~text
ROA: 203.0.113.0/24, origin AS64496, maxLength 24
~~~

Route đúng /24 với origin AS64496 là Valid. Nếu một bên công bố cùng prefix với AS khác, route đó có thể Invalid; nếu tổ chức vô tình công bố /25 với cùng AS64496, route /25 cũng Invalid theo VRP này.

### 7.3. Multihoming, anycast và nhiều origin

Một prefix có thể phục vụ ở nhiều trung tâm dữ liệu hoặc qua nhiều nhà cung cấp nhưng vẫn mang **cùng origin ASN**. Trong trường hợp này không tự phát sinh nhu cầu ROA bổ sung.

Nếu kiến trúc **thật sự cho phép nhiều origin ASN** (chẳng hạn chuyển origin giữa các bên vận hành hoặc một mô hình multi-origin được phê duyệt), có thể cần nhiều ủy quyền, ví dụ:

~~~text
203.0.113.0/24, maxLength 24, origin AS64496
203.0.113.0/24, maxLength 24, origin AS64497
~~~

Khi có cả hai VRP hợp lệ, hai origin tương ứng có thể được phân loại Valid. Tuy nhiên việc mở thêm origin cũng làm **rộng phạm vi những origin được ROV chấp nhận**. Cần có owner, giải trình và lịch thu hồi khi một origin không còn dùng.

### 7.4. Chuyển nhà cung cấp hoặc đổi origin ASN

Một sai lầm nguy hiểm là đổi thông báo BGP sang origin mới **trước khi** các bộ xác thực có dữ liệu ROA hỗ trợ origin đó.

Quy trình khái niệm có kiểm soát:

1. Kiểm kê các prefix hiện tại và origin ASN đang công bố trên từng đường/peer.
2. Chuẩn bị ROA cho **origin mới** bên cạnh ROA cũ, nếu mô hình chuyển đổi cần hai origin đồng thời.
3. Chờ dữ liệu được công bố, các validator cập nhật và VRP mới **thực sự quan sát được** từ các điểm kiểm tra đã xác định.
4. Kiểm tra policy prefix/IRR/BGP khác và thông số maxLength; không chỉ nhìn RPKI.
5. Thay đổi công bố BGP có kiểm soát, theo dõi reachability và trạng thái route từ nhiều điểm quan sát.
6. Sau khi chắc chắn không còn sử dụng origin cũ, thu hồi ROA cũ theo quy trình và giám sát tiếp.

Không có khoảng thời gian chờ cố định đảm bảo mọi validator trên Internet đã nhận dữ liệu mới. Repository, validator polling và cơ chế đồng bộ giữa các mạng khác nhau. Vì vậy bước 3 phải dựa vào **quan sát thực tế**, không chỉ chờ một số phút mang tính suy đoán.

### 7.5. maxLength quá rộng và ROA thiếu

Hai lỗi có hậu quả khác nhau:

- **ROA thiếu origin/prefix hợp pháp:** route có thể **Invalid** nếu được VRP khác bao phủ nhưng không phù hợp. Kết quả là các mạng reject Invalid có thể làm giảm reachability.
- **ROA maxLength quá rộng:** route more-specific với origin được phép có thể được xem Valid, ngay cả khi doanh nghiệp không muốn các more-specific đó xuất hiện; làm yếu mục tiêu giới hạn mức ủy quyền.

Một ROA không tồn tại cho prefix **không đồng nghĩa** mọi route của prefix đó là Invalid; nếu không có VRP bao phủ, chúng được phân loại NotFound. Đây là lý do cần phân biệt **coverage** và **tính đúng của ủy quyền hiện có**.

### 7.6. Quản lý quyền truy cập và khóa

Vì ROA tác động đến khả năng được các mạng khác chấp nhận route, cần:

- Tài khoản quản trị RPKI được bảo vệ bằng xác thực mạnh và quyền tối thiểu.
- Quy trình phê duyệt hai lớp cho thay đổi prefix, origin ASN và maxLength quan trọng.
- Lưu lịch sử ai tạo/sửa/xóa ROA, thời gian, ticket và kết quả xác minh.
- Kiểm soát khóa/chứng chỉ theo phương thức RPKI đang sử dụng; tránh chia sẻ thông tin bí mật.
- Kiểm thử các thay đổi trước và sau khi cập nhật, đặc biệt khi chuyển đổi ASN hoặc hợp nhất tài nguyên.

RPKI có thể được vận hành qua dịch vụ RIR quản lý hoặc qua CA do chủ thể tài nguyên vận hành. Quy trình ký/công bố cụ thể **phụ thuộc lựa chọn triển khai**; không đưa private key hoặc token quản trị vào script và tài liệu đào tạo.

## 8. Vận hành relying-party validator và RTR cache

### 8.1. Những thành phần cần chạy liên tục

Một mạng dùng ROV thường cần:

1. **Validator** tải dữ liệu repository, xác minh chuỗi chứng chỉ/ROA và phát sinh VRP.
2. **Cache/RTR service** cung cấp VRP đến router. Có thể cùng tiến trình với validator hoặc kiến trúc khác.
3. **BGP router** nhận VRP, so sánh với route và thực thi policy.
4. **Hệ thống giám sát** theo dõi tuổi dữ liệu, lỗi đồng bộ, trạng thái phiên RTR và phân bố trạng thái route.

### 8.2. Khả năng sẵn sàng và dự phòng

Đối với mạng quan trọng, nên cân nhắc **nhiều validator/cache độc lập** để tránh một tiến trình hoặc máy đơn lẻ làm điểm hỏng. Tùy nền tảng, router có thể kết nối tới nhiều cache theo thứ tự ưu tiên hoặc cơ chế dự phòng.

Tuy nhiên, hai validator chạy cùng cấu hình sai, cùng nguồn truy cập mất kết nối hoặc dùng trust anchor lỗi **không tạo dự phòng độc lập thực sự**. Cần kiểm soát:

- Kết nối repository qua RRDP/rsync, DNS và thời gian hệ thống.
- Trust anchor/TAL và chính sách cập nhật.
- Dung lượng đĩa, CPU/RAM, queue và thời gian refresh.
- Bảo vệ kênh router–cache, địa chỉ cache và điều khiển truy cập từ router.
- Kiểm soát phiên bản phần mềm và các thay đổi dữ liệu xác thực.

### 8.3. Dữ liệu lỗi, dữ liệu cũ và trạng thái route

Một cache mất kết nối với router, một validator không lấy được repository, một ROA hết hạn và một route **RPKI Invalid** là **bốn tình huống khác nhau**.

| Hiện tượng | Bản chất | Phương án điều tra |
| --- | --- | --- |
| RTR session down | Router không trao đổi dữ liệu với cache bình thường | Kết nối quản trị, cổng, ACL, dịch vụ cache, log router |
| Cache VRP quá cũ | Validator/cache không làm mới dữ liệu theo thiết kế | RRDP/rsync, trust chain, đồng hồ, trạng thái đồng bộ |
| Chứng chỉ/ROA bị từ chối xác minh | Dữ liệu ký không đủ điều kiện theo validator | Nguyên nhân xác thực, hết hạn/thu hồi, repository |
| Route Invalid với VRP hiện hành | Origin ASN hoặc maxLength không phù hợp VRP bao phủ | ROA, origin AS thật, prefix length, dữ liệu cache |
| Route NotFound | Không có VRP bao phủ ở tập dữ liệu sử dụng | Kiểm tra coverage, chất lượng dữ liệu và chủ prefix |

**Fail policy khi mất dữ liệu RPKI** cần được thiết kế theo mức rủi ro và khả năng phục vụ. Tự biến tất cả route thành Invalid khi mất cache có thể gây mất kết nối lớn; tự coi mọi xác thực là thành công vĩnh viễn cũng tạo khoảng trống bảo vệ. Hành vi thực tế khi RTR session down hoặc cache hết hạn phải được xác minh trong router/phiên bản đang triển khai và có kịch bản khôi phục.

### 8.4. RTR là dữ liệu cấp cho router, không phải Internet BGP

Giao thức RTR truyền VRP từ cache đến router, **không phải** giao thức quảng bá route giữa các ASN. Một đường RTR đang hoạt động cũng không chứng minh router đã áp dụng policy reject Invalid; cần quan sát **trạng thái VRP trong router và kết quả import route**.

## 9. Các bước triển khai ROV trên mạng thực tế

### Bước 1 — Kiểm kê BGP và tài nguyên

Xác định ASN của tổ chức, các prefix IPv4/IPv6, upstream/peer, tập origin ASN đang dùng, những thông báo more-specific và các thay đổi dự kiến. Đối chiếu quyền tài nguyên, route đang nhìn thấy và ROA hiện hữu.

### Bước 2 — Đánh giá mức bao phủ và chất lượng ROA

Với từng prefix cần bảo vệ, đánh giá:

- Có VRP bao phủ không?
- Origin ASN có đúng với BGP advertisement không?
- maxLength có bao phủ đúng độ dài route hợp pháp không?
- Có ROA cũ cho ASN đã rời hệ thống không?
- Có route Valid, Invalid, NotFound ngoài dự kiến không?

**Ưu tiên sửa lỗi ROA ảnh hưởng chính mạng mình** trước khi bật chính sách từ chối Invalid trên diện rộng.

### Bước 3 — Triển khai validator/cache

Chọn giải pháp validator có thể kiểm tra chữ ký và cập nhật repository, cấu hình nguồn trust anchor đáng tin, đồng bộ thời gian, logging và dự phòng phù hợp. Không thiết lập một cache từ nguồn không kiểm soát rồi mặc nhiên coi VRP là đáng tin.

### Bước 4 — Kết nối router và giám sát ở chế độ quan sát

Thiết lập RTR theo hướng dẫn nền tảng và **xem VRP count/trạng thái phiên/tuổi dữ liệu**. Trong giai đoạn đầu, gắn nhãn route Valid/Invalid/NotFound và ghi log/metric nhưng chưa từ chối hàng loạt nếu chưa kiểm thử.

### Bước 5 — Đối chiếu route Invalid thật

Phân nhóm:

- Lỗi ROA của tài nguyên thuộc quyền quản trị của chính tổ chức.
- Lỗi origin/more-specific của khách hàng và đối tác đã xác minh.
- Route bất thường có dấu hiệu hijack hoặc nhầm lẫn cấu hình từ nguồn khác.
- Sai lệch do cache/validator/route parser.

Một số route Invalid có thể xuất phát từ sai sót vận hành hợp pháp, nhưng điều đó **không** có nghĩa nên cho qua tất cả Invalid. Mục tiêu là kiểm tra dữ liệu, phối hợp owner và triển khai chính sách có nhận thức về tác động.

### Bước 6 — Thử enforcement trên phạm vi kiểm soát

Khi policy và dữ liệu đủ tin cậy, kiểm thử reject Invalid trên router/peer phù hợp với khả năng rollback, theo dõi số route bị loại, reachability ứng dụng và sự thay đổi trong routing table. Cần phân biệt **traffic mất do BGP policy** với lỗi DNS, firewall hoặc ứng dụng.

### Bước 7 — Mở rộng và theo dõi sau triển khai

Triển khai theo nhóm peer/edge có kiểm soát, kiểm tra các prefix quan trọng, đo trạng thái valid/invalid/notfound và khả năng dự phòng cache. Định kỳ thử quy trình khi validator mất kết nối và khi thay đổi origin có ROA mới.

### Bước 8 — Đưa quản trị ROA vào quy trình thay đổi mạng

Bất kỳ thay đổi nào về:

- Prefix được quảng bá hoặc more-specific.
- Origin ASN, merger, migration, anycast, multihoming.
- Quyền tài nguyên IP/ASN hoặc nhà cung cấp quản lý ROA.
- Chính sách import BGP hoặc cache/validator.

đều cần bước **kiểm tra RPKI impact** trong runbook và ticket. Không để thay đổi định tuyến và ROA được thực hiện bởi hai nhóm độc lập mà không trao đổi lịch.

## 10. Quan hệ với các cơ chế bảo vệ BGP khác

| Cơ chế | Mục tiêu | Có thay thế RPKI origin validation không? |
| --- | --- | --- |
| **RPKI ROA + ROV** | Xác minh origin ASN được chủ tài nguyên ủy quyền cho prefix/độ dài | Chính là cơ chế cần học |
| **Prefix-list theo peer** | Giới hạn những prefix một peer được phép công bố | Không, vì nguồn thông tin và điểm kiểm tra khác |
| **IRR-based filters** | Dùng dữ liệu registry để xây chính sách prefix/ASN | Không; độ chính xác và quy trình xác minh khác RPKI |
| **AS_PATH filtering** | Chặn các mẫu AS_PATH không phù hợp chính sách | Không; ROA không xác minh toàn bộ AS_PATH |
| **Max-prefix** | Giới hạn số lượng route từ một peer | Không; không xác minh nguồn gốc prefix |
| **BGP session authentication / TCP protection** | Bảo vệ phiên BGP giữa hai neighbor khỏi một số tấn công | Không xác minh quyền của một origin ASN trên toàn Internet |
| **BGPsec** | Hướng tới xác minh mật mã các bước quảng bá đường AS của route trong mô hình được hỗ trợ | Mục tiêu khác và yêu cầu triển khai riêng, không tự có khi bật ROV |
| **ASPA** | Cơ chế ủy quyền quan hệ provider-AS cho các kiểm tra đường đi trong hệ sinh thái liên miền | Bổ sung cho origin validation; phụ thuộc chuẩn và mức triển khai |
| **BGP route monitoring** | Phát hiện thay đổi origin, prefix và đường đi bất thường | Cung cấp khả năng quan sát; không tự thực thi chính sách chặn |
| **DNSSEC** | Xác thực dữ liệu DNS trong phạm vi chuỗi tin cậy DNSSEC | Bảo vệ một lớp khác, không xác minh origin BGP |

**Đối với bảo vệ phiên BGP**, các kỹ thuật có thể gồm xác thực neighbor theo khả năng thiết bị, TTL security, quản lý cổng TCP, giới hạn prefix và control-plane policing. Chúng bảo vệ một số nguy cơ ở mức phiên/hạ tầng, **không chứng minh** origin của từng prefix đã được chủ thể tài nguyên cho phép.

### 10.1. RPKI không ngăn mọi route leak

Giả sử một nhà mạng công bố lại một route sang peer không phù hợp chính sách nhưng vẫn giữ origin ASN hợp pháp. Kết quả origin validation có thể vẫn **Valid**, mặc dù quá trình lan truyền route có vấn đề. Chống route leak cần những quy tắc và công cụ xét **quan hệ AS, hướng xuất/nhập và đường đi**, cùng việc giám sát route từ nhiều góc nhìn.

### 10.2. RPKI không xác thực nội dung ứng dụng

Một prefix được công bố với origin ASN hợp lệ không chứng minh các máy trong prefix được vá lỗi, DNS an toàn hay ứng dụng HTTPS không độc hại. Firewall, VPN, IDS/IPS, WAF, bảo vệ DNS và xác thực người dùng vẫn cần thiết.

### 10.3. Bảo vệ RPKI như một thành phần điều khiển quan trọng

Validator/cache và tài khoản quản trị ROA có ảnh hưởng đến quyết định routing. Vì vậy:

- Đặt validator/cache trong vùng quản trị có ACL và logging phù hợp.
- Hạn chế ai có thể thay đổi ROA, TAL và chính sách ROV.
- Kiểm tra nguồn thời gian/NTP, tính toàn vẹn cấu hình, cập nhật bản vá.
- Có khả năng khôi phục config và xem lại lịch sử quyết định.
- Theo dõi luồng nội bộ giữa router, validator, dịch vụ quản lý và các nguồn cập nhật.

Đây là cách kết nối kiến thức **routing security** với phân đoạn, firewall và quản lý danh tính trong tổng thể **SECURITY_NETWORK_SECURITY**.

## 11. Giám sát RPKI và đánh giá hiệu quả bảo vệ

RPKI không phải một cơ chế chỉ “bật một lần rồi quên”. Dữ liệu tài nguyên, ROA, route quảng bá và phiên validator–router thay đổi theo thời gian. Giám sát cần phản ánh **trạng thái kiểm tra**, **độ tin cậy của dữ liệu xác thực** và **ảnh hưởng lên định tuyến/dịch vụ**.

### 11.1. Các chỉ số cần có

| Nhóm | Chỉ số/tín hiệu | Ý nghĩa |
| --- | --- | --- |
| Validator health | Lần cập nhật thành công cuối, lỗi repository, thời gian xử lý | Biết dữ liệu có được làm mới không |
| VRP | Tổng VRP IPv4/IPv6, thay đổi theo thời gian, tuổi snapshot | Phát hiện dữ liệu biến mất hoặc tăng bất thường |
| Trust chain | Lỗi TAL, chứng chỉ, ROA, thu hồi, hết hạn | Phân biệt lỗi nguồn dữ liệu và route sai |
| RTR | Số phiên đang hoạt động, mất kết nối, tuổi dữ liệu router nhận | Biết router có nguồn VRP dùng được không |
| BGP route states | Valid, Invalid, NotFound theo peer, prefix, AFI/SAFI | Theo dõi kết quả origin validation |
| Enforcement | Số route bị reject/giảm ưu tiên theo rule ROV | Kiểm chứng chính sách thực thi |
| Reachability | Sự thay đổi đường đi, lỗi ứng dụng, ảnh hưởng prefix quan trọng | Phát hiện tác động vận hành |
| ROA management | ROA tạo/sửa/xóa, maxLength mới, ASN mới, ticket | Phát hiện thay đổi nhầm hoặc trái phép |
| Capacity | CPU, RAM, disk, network của validator/cache và router | Ngăn lỗi vận hành do tài nguyên |

Một số sản phẩm không xuất trực tiếp tất cả chỉ số ở trên. Khi đó cần kết hợp log, API quản trị, BGP telemetry và hệ thống giám sát tương ứng. **Không lấy số VRP tăng** làm thước đo chất lượng duy nhất: có thể tăng do một đợt ROA hợp pháp, nhưng cũng có thể báo hiệu thay đổi bất thường cần xác minh.

### 11.2. Nhật ký ví dụ để liên hệ ROV với BGP

~~~text
time=2026-11-28T10:00:00Z
router=edge-lab-01 peer=198.51.100.2
prefix=203.0.113.0/24 origin_asn=AS64497
rpki_state=INVALID
policy_action=REJECT
vrp_snapshot=lab-20261128-a
reason=origin_asn_not_authorized
~~~

Đây là **log minh họa do bài học xây dựng**, không phải định dạng chuẩn bắt buộc của router. Đọc log:

1. Router nhận route cho prefix trong ví dụ từ một peer.
2. Origin AS64497 không khớp VRP minh họa cho AS64496.
3. Policy của **router này** đã từ chối route.
4. Bản ghi **không chứng minh** tất cả router trên Internet đều đã từ chối route đó.
5. Bản ghi **không tự chứng minh** nguồn cố ý tấn công; có thể là lỗi origin hoặc lỗi ROA.

Việc ghép log router với **snapshot VRP tại thời điểm đánh giá** đặc biệt hữu ích: ROA/VRP có thể được sửa sau sự kiện, nên kiểm tra trạng thái hiện tại chưa chắc tái hiện đúng lý do một route bị đánh giá Invalid trong quá khứ.

### 11.3. Các cảnh báo đáng ưu tiên

- Một prefix quan trọng do chính tổ chức sở hữu **đột ngột chuyển từ Valid sang Invalid**.
- ROA bị xóa hoặc đổi origin ASN/maxLength ngoài lịch thay đổi.
- Tập VRP giảm/tăng lớn bất thường kèm lỗi cập nhật hoặc repository.
- Mất kết nối đến tất cả RTR cache, dữ liệu router quá cũ hoặc thời gian hệ thống sai.
- Một lượng lớn route bị reject sau thay đổi phiên bản router/validator/policy.
- Prefix không còn reachable ở các điểm quan sát độc lập sau cập nhật ROA.
- Một số peer công bố origin khác dự kiến hoặc xuất hiện more-specific ngoài policy.

Không dùng một cảnh báo đơn lẻ để kết luận sự cố đang diễn ra. Cần xác minh **tài nguyên, route BGP thực tế, tập VRP, thời gian, dữ liệu đa nguồn và ảnh hưởng người dùng**.

## 12. Chẩn đoán route RPKI Invalid hoặc dịch vụ mất kết nối

Khi một prefix bị đánh giá Invalid hoặc biến mất khỏi bảng route, cần **truy nguyên nguyên nhân trước khi tắt ROV**. Bởi vì Invalid có thể do lỗi cấu hình hợp pháp, route hijack hoặc dữ liệu không đồng bộ.

~~~mermaid
flowchart TD
    A[Route bất ngờ Invalid / không reachable] --> B{Router thấy prefix và origin ASN nào?}
    B --> C[Đối chiếu BGP update, AS_PATH, prefix length]
    C --> D{Có VRP bao phủ trong cache đang dùng?}
    D -->|Không| E[Kiểm tra NotFound, TAL, repository, cache freshness]
    D -->|Có| F{Origin ASN và maxLength khớp ít nhất một VRP?}
    F -->|Không| G[Kiểm tra ROA, origin change, more-specific, quyền tài nguyên]
    F -->|Có| H[Kiểm tra policy, dữ liệu router, cách đọc trạng thái]
    G --> I[Chỉnh thay đổi có owner, xác minh dữ liệu lan truyền]
    E --> I
    H --> I
    I --> J[Kiểm tra lại ROV và reachability từ nhiều điểm]
~~~

### 12.1. Lỗi thường gặp: AS đúng nhưng prefix quá dài

**Hiện tượng:** ROA 203.0.113.0/24, AS64496, maxLength 24; BGP lại công bố **203.0.113.0/25** với origin AS64496.

**Kết quả:** prefix /25 bị đánh giá **Invalid** theo VRP trên vì độ dài 25 vượt maxLength 24.

**Hướng xử lý:** kiểm tra vì sao xuất hiện /25, có được phê duyệt hay không và các bộ lọc Internet có chấp nhận /25 không. Chỉ mở rộng maxLength khi route đó **thực sự cần và được cho phép**, thay vì tăng vô điều kiện để biến trạng thái sang Valid.

### 12.2. Lỗi thường gặp: Chuyển origin ASN nhưng quên ROA

**Hiện tượng:** tổ chức đổi origin từ AS64496 sang AS64497 nhưng chỉ còn ROA cho AS64496.

**Kết quả:** route có origin AS64497, prefix trùng ROA bao phủ có thể **Invalid**. Các mạng reject Invalid có thể làm một phần người dùng không kết nối tới prefix.

**Hướng xử lý:** xác minh quyền tài nguyên và thay đổi BGP, cấp ROA phù hợp qua đơn vị có thẩm quyền, theo dõi VRP cập nhật và route reachability. Nếu cần rollback quảng bá BGP, phải làm theo runbook bảo đảm tuyến hợp lệ; không vội sửa policy toàn bộ mạng chỉ để bỏ qua dữ liệu sai của một prefix.

### 12.3. Lỗi thường gặp: Validator nhìn thấy ROA nhưng router không thấy VRP

Khả năng:

- Phiên RTR mất kết nối hoặc bị ACL/firewall chặn.
- Validator mới cập nhật nhưng router còn dùng cache/phiên cũ.
- Cấu hình AFI/SAFI, địa chỉ cache hoặc chính sách trên router không đúng.
- Cache hết hạn hay gặp lỗi đồng bộ.
- Router thực thi ROV bằng nguồn dữ liệu khác với nguồn quản trị viên đang quan sát.

**Hướng xử lý:** kiểm tra log cả validator và router, thời gian/snapshot dữ liệu, phiên RTR và các chính sách hiệu lực. Không coi “ROA đã xuất hiện trên giao diện nhà đăng ký” là bằng chứng mọi router đã nhận VRP mới.

### 12.4. Lỗi thường gặp: Route Valid nhưng traffic vẫn không tới đích

**Valid** chỉ nói về origin authorization. Kết nối còn phụ thuộc:

1. Router có chọn và cài route vào forwarding table không.
2. Đường đi và đường về, chính sách peering và khả năng truyền bá route.
3. Firewall/ACL/VPN và các điểm chặn ở lớp mạng.
4. DNS, endpoint, load balancer và trạng thái ứng dụng.
5. Tình trạng congestion, mất gói hoặc lỗi MTU trên tuyến.

Khi một route Valid nhưng không reachable, không nên quy nguyên nhân cho ROA nếu chưa kiểm tra các lớp này.

### 12.5. Lỗi thường gặp: NotFound bị hiểu là Invalid

Một prefix chưa có ROA hoặc chưa có VRP bao phủ **không mặc định là tấn công**. Nếu policy tổ chức từ chối tất cả NotFound mà chưa có lý do, có thể làm mất kết nối tới rất nhiều mạng chưa triển khai ROA.

**Hướng xử lý:** phân biệt ba trạng thái trên router, xác minh cấu hình policy và trường hợp ngoại lệ. Khi cần chính sách chặt hơn cho tập prefix thuộc quyền quản trị riêng, hãy thiết kế cụ thể theo nhóm tài sản thay vì thay đổi mặc định cho toàn Internet một cách thiếu kiểm soát.

### 12.6. Lỗi thường gặp: Chữ ký/ROA không hợp lệ

Một validator có thể loại đối tượng RPKI vì lỗi chuỗi chứng chỉ, hết hạn, thu hồi, quyền tài nguyên không phù hợp hoặc dữ liệu repository bị hỏng. Đối tượng **bị validator loại trước khi tạo VRP** không tương đương một route BGP đã được đánh giá Invalid.

Nếu không có VRP nào còn bao phủ một route, route có thể trở thành **NotFound** trong tập VRP hiện tại, dù trước đó từng Valid. Cần phân biệt lỗi **kiểm tra đối tượng RPKI** với kết quả **kiểm tra route dựa trên VRP**.

## 13. Bài thực hành phân loại route không cần thao tác với Internet

Bài tập dùng các prefix/ASN dành cho tài liệu. Không yêu cầu tạo BGP session hoặc sửa ROA thật; chỉ cần áp dụng đúng công thức so khớp.

### 13.1. Tập VRP giả định của phòng lab

~~~json
[
  {
    "prefix": "203.0.113.0/24",
    "maxLength": 24,
    "originASN": "AS64496"
  },
  {
    "prefix": "2001:db8:100::/48",
    "maxLength": 48,
    "originASN": "AS64496"
  }
]
~~~

JSON trên là **dữ liệu huấn luyện**, không phải object ROA có chữ ký và không phải cam kết định dạng JSON của một validator cụ thể.

### 13.2. Phân loại các thông báo

| STT | BGP prefix | Origin | Kết quả |
| --- | --- | --- | --- |
| 1 | 203.0.113.0/24 | AS64496 | **Valid** |
| 2 | 203.0.113.0/24 | AS64497 | **Invalid** |
| 3 | 203.0.113.64/26 | AS64496 | **Invalid** |
| 4 | 198.51.100.0/24 | AS64497 | **NotFound** |
| 5 | 2001:db8:100::/48 | AS64496 | **Valid** |
| 6 | 2001:db8:100::/49 | AS64496 | **Invalid** |
| 7 | 2001:db8:200::/48 | AS64496 | **NotFound** |
| 8 | 203.0.112.0/23 | AS64496 | **NotFound** |

**Giải thích:** các route 3 và 6 có ASN khớp nhưng prefix dài hơn maxLength. Route 2 có prefix đúng nhưng origin ASN khác. Route 4, 7 và 8 không được một VRP nào trong tập minh họa bao phủ theo điều kiện xác thực.

### 13.3. Thay đổi một VRP và phân loại lại

Giả sử bổ sung VRP:

~~~text
203.0.113.0/24, maxLength 26, origin AS64496
~~~

Khi đó route **203.0.113.64/26 origin AS64496** trong bảng trở thành **Valid**, vì đã có một VRP cho phép đến /26. Route **203.0.113.0/24 origin AS64497** vẫn **Invalid** vì origin không khớp với bất kỳ VRP nào trong tập giả định.

Đây là ví dụ về lý do phải hiểu **maxLength như một phạm vi ủy quyền**, không đơn giản là tham số làm cho trạng thái trên dashboard “xanh” hơn.

### 13.4. Checklist khi xem router trong phòng lab

Trên một router được phép quản trị (sử dụng lệnh theo tài liệu đúng sản phẩm/phiên bản), hãy thu thập:

1. Danh sách phiên BGP và prefix nhận từ peer.
2. Prefix length và **origin ASN thực** mà router xác định cho route.
3. Tập VRP/cache mà router đang sử dụng, trạng thái RTR và thời điểm cập nhật.
4. RPKI state của từng route.
5. Rule BGP import và hành động khi route là Invalid, Valid hoặc NotFound.
6. Best path/RIB và bảng forwarding khi cần kiểm tra reachability.
7. Nhật ký route bị loại, route thay đổi trạng thái và phiên cache bị mất.

Ưu tiên **lệnh đọc** và phân tích dữ liệu có sẵn. Không thử công bố route giả lên Internet hoặc sửa ROA tài nguyên thật chỉ để xác minh công thức. Nếu cần kịch bản failover, dùng thiết bị giả lập/lab cô lập và có quyền quản trị.

## 14. Tình huống tổng hợp: Thay đổi nhà mạng gây RPKI Invalid

**Bối cảnh:** tổ chức vận hành prefix minh họa **203.0.113.0/24**, đang có origin **AS64496** và ROA tương ứng:

~~~text
ROA current:
  Prefix: 203.0.113.0/24
  Origin: AS64496
  MaxLength: 24
~~~

Nhóm vận hành dự định chuyển sang nhà cung cấp mới để origin trở thành **AS64497**. Do không cập nhật ROA trước, router ở một số mạng thực hiện ROV bắt đầu đánh dấu thông báo mới **Invalid**. Người dùng ở các mạng khác nhau báo tình trạng kết nối không nhất quán.

### 14.1. Phân tích sự cố

1. Route mới với AS64497 **không khớp** ROA hiện có cho AS64496.
2. ROV có thể đánh dấu Invalid ở nơi nhận dữ liệu đầy đủ.
3. Không phải mọi mạng đều có cùng chính sách Reject Invalid; vì vậy ảnh hưởng có thể **không đồng đều**.
4. Nếu đồng thời route cũ vẫn được truyền hợp lệ ở một số vị trí, khả năng tiếp cận có thể thay đổi theo điểm nhìn và BGP best path.
5. Đổi maxLength từ 24 lên 32 **không xử lý lỗi origin ASN**; maxLength giải quyết độ dài prefix, không phải ASN.

### 14.2. Cách chuẩn bị chuyển đổi đúng

Trong kịch bản có quyền quản trị tài nguyên:

1. Xác định tất cả prefix/ASN sẽ thay đổi và những route dự kiến trong giai đoạn chuyển tiếp.
2. Tạo ROA bổ sung cho AS64497 với **đúng prefix và maxLength cần dùng** trước khi đổi origin.
3. Kiểm tra VRP mới đã được validator phù hợp xác minh, dữ liệu trên router giám sát có trạng thái cập nhật.
4. Phối hợp bộ lọc IRR/prefix và lịch thay đổi BGP của các nhà cung cấp.
5. Chuyển đổi theo kế hoạch, đo trạng thái Valid/Invalid và reachability ở nhiều điểm.
6. Khi hoàn tất và không còn route từ AS64496, thu hồi ROA cũ theo thủ tục đã phê duyệt.

### 14.3. Bài học từ sự cố

Không tách hoạt động **ROA authorization** khỏi kế hoạch thay đổi **BGP origination**. Nên có một checklist chung giữa người quản trị tài nguyên IP, kỹ sư định tuyến, nhóm giám sát và nhà mạng liên quan.

## 15. Câu hỏi tự kiểm tra và gợi ý

**1. RPKI có chứng minh toàn bộ AS_PATH là hợp pháp không?**

Không. ROA/ROV kiểm tra sự phù hợp của **origin ASN** với quyền ủy quyền cho prefix và maxLength; các hop khác trên đường AS cần cơ chế/chính sách bổ sung.

**2. Một route không có ROA bao phủ có phải Invalid không?**

Không. Theo mô hình origin validation, nếu không có VRP nào bao phủ route, trạng thái là **NotFound**.

**3. Vì sao maxLength 24 có thể làm route /25 cùng ASN trở thành Invalid?**

Vì /25 cụ thể hơn giới hạn tối đa /24 được ủy quyền, mặc dù origin ASN khớp.

**4. Có hai VRP bao phủ, một VRP khớp ASN và maxLength còn VRP kia không khớp. Route là Valid hay Invalid?**

**Valid**, vì chỉ cần **ít nhất một** VRP bao phủ và khớp đầy đủ.

**5. Nếu prefix được truyền qua hai nhà mạng, có bắt buộc tạo hai ROA theo ASN của mỗi nhà mạng không?**

Không. Chỉ tạo ROA theo **origin ASN thực sự được phép**, không phải tất cả transit ASN.

**6. RPKI Valid có đồng nghĩa website ở địa chỉ đó là an toàn không?**

Không. RPKI không xác minh TLS của website, dữ liệu DNS, quyền truy cập hoặc mức an toàn của hệ điều hành/ứng dụng.

**7. Khi validator mất kết nối, có nên chuyển mọi route sang Invalid không?**

Không thể suy ra điều đó. Cần phân biệt **dữ liệu cache không sẵn sàng** với **route có VRP bao phủ nhưng không khớp**; fail policy phải được định nghĩa và kiểm thử theo router thực tế.

**8. Vì sao một mạng vẫn có thể bị route leak dù ROA đúng?**

Vì origin vẫn hợp lệ nhưng **cách route được truyền qua quan hệ AS** có thể trái chính sách; ROV không kiểm chứng toàn bộ quá trình lan truyền.

**9. Tại sao không nên đặt maxLength /32 cho mọi ROA IPv4?**

Vì mở rộng phạm vi ủy quyền more-specific không cần thiết, làm yếu ranh giới kiểm soát origin của các prefix con.

**10. Một route từng Valid nhưng sau đó Invalid; những điều đầu tiên cần đối chiếu là gì?**

Prefix, độ dài, origin ASN trong BGP, VRP hiện hành, lịch sử thay đổi ROA, dữ liệu validator/cache, thời điểm và route policy.

**11. Vì sao log Invalid không đủ kết luận nhà mạng phát route đang tấn công?**

Route sai có thể do đổi origin chưa cập nhật ROA, cấu hình more-specific, trạng thái dữ liệu khác nhau hoặc nhầm lẫn vận hành. Cần điều tra bằng chứng và quyền tài nguyên.

**12. Tại sao phải kiểm tra reachability sau khi thay ROA dù dữ liệu đã hiển thị đúng?**

Vì cache của các mạng cập nhật khác thời điểm, BGP còn áp dụng các chính sách khác, và đường đi/ứng dụng có thể có lỗi độc lập với RPKI.

## 16. Các sai lầm cần tránh

| Hiểu lầm | Cách hiểu đúng |
| --- | --- |
| “RPKI bảo đảm mọi route Internet đều không bị giả mạo.” | RPKI origin validation bảo vệ một thuộc tính cụ thể; có giới hạn coverage/triển khai. |
| “Có ROA nghĩa là router tự động lọc Invalid.” | Router cần VRP, ROV và import policy được cấu hình/kiểm tra. |
| “ROA là cùng thứ với VRP.” | ROA là đối tượng đã ký; VRP là dữ liệu xác minh từ validator. |
| “Invalid chắc chắn là tấn công.” | Có thể do sai origin, maxLength hoặc lỗi thay đổi ROA. |
| “NotFound chắc chắn là route độc hại.” | Có thể chỉ chưa có VRP bao phủ prefix. |
| “Valid nghĩa là route sẽ được chọn làm best path.” | BGP còn xét những thuộc tính và chính sách khác. |
| “Valid nghĩa là AS_PATH không bị giả mạo.” | ROA/ROV không xác minh toàn bộ AS_PATH. |
| “ASN của mọi upstream đều cần thêm vào ROA.” | Phải phân biệt origin ASN với transit ASN. |
| “Đặt maxLength lớn nhất để tránh sự cố.” | Mở rộng ủy quyền more-specific hơn nhu cầu thực tế. |
| “ROA vừa tạo có hiệu lực ngay tại mọi router.” | Cần phân phối repository, xác minh, RTR và cập nhật dữ liệu giữa các mạng. |
| “RTR session up chứng minh ROV đã bật.” | Cần kiểm tra trạng thái route và hành động chính sách. |
| “Nếu dịch vụ lỗi thì tắt RPKI là bước đầu tiên.” | Phải xác minh prefix/origin/VRP/route policy và có rollback được kiểm soát. |
| “RPKI thay thế firewall, VPN và IDS/IPS.” | Các lớp bảo vệ có mục tiêu và điểm thực thi khác nhau. |

## 17. Tổng kết

**RPKI** cung cấp hạ tầng chứng chỉ cho phép chủ thể có quyền tài nguyên IP tạo **ROA** xác nhận origin ASN được phép công bố prefix BGP. Validator kiểm tra các đối tượng này và tạo **VRP**; router nhận VRP qua **RTR** và thực hiện **Route Origin Validation**. Ba kết quả **Valid, Invalid, NotFound** phải được hiểu đúng theo điều kiện bao phủ prefix, origin ASN và maxLength.

Trong thực tế, điều quan trọng không chỉ là “có ROA” mà còn là **ROA đúng với route dự kiến, dữ liệu validator được cập nhật, router thực thi policy phù hợp và quy trình thay đổi được kiểm soát**. RPKI giúp giảm rủi ro một số dạng origin hijack nhưng không xác minh toàn bộ AS_PATH, không loại bỏ route leak và không đảm bảo ứng dụng ở đích an toàn.

Trong học phần **SECURITY_NETWORK_SECURITY**, RPKI là lớp **bảo vệ tính đúng đắn của thông tin định tuyến liên miền**, bổ sung cho prefix/AS-PATH filtering, firewall, phân đoạn, bảo vệ DNS, VPN, IDS/IPS và giám sát đa điểm. Hiệu quả phụ thuộc vào vận hành liên tục, khả năng quan sát và phối hợp giữa chủ tài nguyên, nhóm BGP và những mạng lựa chọn thực thi ROV.

### Tài liệu tham khảo

- **RFC 6480 — An Infrastructure to Support Secure Internet Routing:** kiến trúc và chuỗi tin cậy RPKI.
- **RFC 6482 — A Profile for Route Origin Authorizations (ROAs):** cấu trúc, origin ASN, prefix và maxLength trong ROA.
- **RFC 6811 — BGP Prefix Origin Validation:** quy tắc phân loại Valid, Invalid và NotFound.
- **RFC 8210 — The Resource Public Key Infrastructure (RPKI) to Router Protocol, Version 1:** trao đổi VRP giữa cache và router.
- **RFC 8182 — The RPKI Repository Delta Protocol (RRDP):** cơ chế phân phối/cập nhật dữ liệu repository.
- **RFC 7730 — Resource Public Key Infrastructure (RPKI) Trust Anchor Locator:** mô tả TAL.
- **RFC 6487 — A Profile for X.509 PKIX Resource Certificates:** chứng chỉ tài nguyên IP/ASN.
- **RFC 5737 — IPv4 Address Blocks Reserved for Documentation:** dải địa chỉ IPv4 minh họa.
- **RFC 5398 — Autonomous System (AS) Number Reservation for Documentation Use:** các ASN dành cho ví dụ tài liệu.
- **RIPE NCC, APNIC và các tổ chức đăng ký tài nguyên Internet — tài liệu RPKI/ROA:** hướng dẫn quyền tài nguyên, vận hành ROA và kiểm tra trạng thái theo vùng quản lý.
