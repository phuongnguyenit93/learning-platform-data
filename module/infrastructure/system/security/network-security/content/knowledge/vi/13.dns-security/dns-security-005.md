# DNSSEC

**DNSSEC (Domain Name System Security Extensions)** là tập hợp cơ chế mở rộng DNS để **xác thực nguồn gốc dữ liệu DNS** (*data origin authentication*) và **kiểm tra tính toàn vẹn của dữ liệu trả lời** (*data integrity*) thông qua chữ ký số và chuỗi tin cậy. Khi DNSSEC được triển khai đúng và bên phân giải thực hiện kiểm tra hợp lệ, kẻ tấn công khó có thể thay một bản ghi DNS đã được ký bằng dữ liệu giả mà vẫn khiến câu trả lời vượt qua quá trình xác minh.

DNSSEC giải quyết một vấn đề cụ thể: **làm thế nào để biết dữ liệu DNS nhận được tương ứng với dữ liệu do vùng DNS có thẩm quyền công bố và được xác thực theo chuỗi tin cậy?** DNSSEC không mã hóa truy vấn, không che tên miền người dùng tra cứu và không khẳng định website hay IP đích an toàn. Nó cũng không ngăn người quản trị hợp lệ vô tình ký một bản ghi sai.

Trong module **SECURITY_NETWORK_SECURITY**, DNSSEC là một lớp bảo vệ DNS cần phối hợp với phân đoạn mạng, firewall, VPN, IDS/IPS, xác thực kết nối, mạng không dây, cloud, giám sát truy vấn và bảo vệ ứng dụng. Bài học tập trung vào cách DNSSEC hoạt động, cách triển khai – kiểm tra – giám sát và cách xử lý sự cố khi quá trình xác thực thất bại.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích các thuộc tính bảo mật DNSSEC cung cấp và những thuộc tính nó **không** cung cấp.
2. Mô tả quan hệ giữa **authoritative DNS**, **recursive resolver**, **validating resolver** và client.
3. Nhận diện vai trò của **DNSKEY, RRSIG, DS, NSEC và NSEC3**.
4. Giải thích **chain of trust** từ root qua TLD tới vùng tên miền cần xác thực.
5. Phân biệt kết quả xác thực **secure**, **insecure**, **bogus** và **indeterminate**.
6. Hiểu ý nghĩa thực tế của các cờ **DO, AD, CD** khi tra cứu DNS.
7. Lập kế hoạch ký vùng, công bố DS, thay khóa và di chuyển DNS provider mà không gây gián đoạn phân giải.
8. Chẩn đoán tình huống DNSSEC dẫn đến SERVFAIL, chữ ký hết hạn hoặc DS không còn khớp.
9. Xây dựng bài kiểm tra và hệ thống giám sát DNSSEC trong môi trường được phép.

## 2. Vì sao DNS truyền thống cần bổ sung bảo mật?

DNS chuyển tên như **www.shop.example** thành dữ liệu tài nguyên, ví dụ địa chỉ IP, MX, CNAME hoặc các bản ghi khác. Trong mô hình DNS truyền thống, việc nhận được một phản hồi **không tự mang bằng chứng chữ ký số** chứng minh dữ liệu đó được vùng có thẩm quyền công bố.

Nếu kẻ tấn công kiểm soát được một điểm trong đường phân giải, lợi dụng lỗ hổng phần mềm hoặc đầu độc cache, người dùng có thể nhận bản ghi giả, ví dụ một địa chỉ IP không thuộc dịch vụ thật. **DNS cache poisoning** là một trong những rủi ro khiến DNSSEC được phát triển. DNSSEC sử dụng chữ ký số để validating resolver kiểm tra tính xác thực của dữ liệu đã ký, nhờ đó giảm nguy cơ chấp nhận câu trả lời bị sửa trái phép trên đường truyền hoặc trong cache.

Tuy nhiên, cần phân biệt ba câu hỏi:

| Câu hỏi | Lớp kiểm soát phù hợp |
| --- | --- |
| Dữ liệu DNS được vùng có thẩm quyền ký và không bị thay đổi trái phép? | **DNSSEC** khi có chuỗi tin cậy và validator hợp lệ |
| Truy vấn và phản hồi giữa client với resolver có được bảo vệ khỏi nghe lén và sửa đổi trên đường đó? | **DoT/DoH**, hoặc kênh bảo mật tương đương tùy kiến trúc |
| Ứng dụng HTTPS có kết nối đúng máy chủ và mã hóa dữ liệu ứng dụng không? | **TLS**, kiểm tra chứng thư và danh tính dịch vụ |

Ba mục tiêu liên quan nhưng **không thể thay thế cho nhau**. DNSSEC không bảo vệ tính bí mật của tên miền được tra cứu; DoH/DoT mã hóa đường truyền tới resolver nhưng không tự chứng minh resolver đã xác thực dữ liệu nguồn bằng DNSSEC.

## 3. Các thành phần trong đường phân giải DNSSEC

| Thành phần | Vai trò | Trách nhiệm liên quan DNSSEC |
| --- | --- | --- |
| **Client / stub resolver** | Gửi truy vấn DNS để ứng dụng sử dụng | Có thể tin cậy resolver đã cấu hình hoặc tự xác minh DNSSEC nếu có hỗ trợ |
| **Recursive resolver** | Hỏi các máy chủ DNS khác và cache kết quả | Lấy dữ liệu cần thiết, xử lý cache và trả lời client |
| **Validating resolver** | Recursive resolver hoặc thành phần có chức năng xác minh DNSSEC | Kiểm tra chữ ký và chuỗi tin cậy từ trust anchor |
| **Authoritative nameserver** | Công bố bản ghi thuộc vùng mà nó có thẩm quyền | Phục vụ RRset, DNSKEY, RRSIG và chứng cứ không tồn tại khi vùng được ký |
| **DNS operator / DNS provider** | Vận hành vùng DNS và quy trình thay đổi | Ký vùng, quản lý khóa, gia hạn chữ ký, đảm bảo nameserver nhất quán |
| **Registrar / registry / parent zone** | Quản lý ủy quyền tên miền và thông tin parent | Đưa bản ghi DS thích hợp vào vùng cha theo quy trình |

Một resolver có khả năng truy vấn recursive **không nhất thiết đã bật DNSSEC validation**. Tương tự, một tên miền đã được ký **không đảm bảo mọi thiết bị cuối đều nhận được kết quả đã xác thực** nếu client dùng resolver không kiểm tra, hoặc nếu đường từ resolver đến client bị thao túng.

### 3.1. Dữ liệu được ký ở đâu và xác thực ở đâu?

Việc **ký vùng** thường do người vận hành authoritative DNS hoặc hệ thống ký chuyên dụng thực hiện. Khi truy vấn tới, nameserver cung cấp dữ liệu đã ký. Bên xác minh thường là **validating resolver**, nơi biết một **trust anchor** đáng tin cậy và có thể kiểm tra đường liên kết chữ ký đến zone đích.

~~~mermaid
flowchart LR
    C["Ứng dụng / stub resolver"] -->|"Truy vấn"| R["Recursive + validating resolver"]
    R -->|"Hỏi dữ liệu tin cậy"| ROOT["Root DNS"]
    R -->|"Hỏi ủy quyền / DS"| TLD["TLD / parent zone"]
    R -->|"Hỏi RRset, RRSIG, DNSKEY"| AUTH["Authoritative DNS của zone"]
    ROOT -. "Chuỗi tin cậy" .-> TLD
    TLD -. "DS xác thực DNSKEY" .-> AUTH
    R -->|"Kết quả xác thực hoặc lỗi"| C
~~~

Sơ đồ thể hiện các vai trò logic: trong thực tế có cache, nhiều authoritative server, resolver chuyển tiếp và các truy vấn không nhất thiết được gửi lại cho tất cả thành phần mỗi lần.

## 4. Các loại bản ghi cốt lõi

### 4.1. DNSKEY: khóa công khai của vùng

**DNSKEY** công bố khóa công khai mà validator sử dụng để xác minh chữ ký DNSSEC. Khóa bí mật tương ứng phải được bảo vệ bởi hệ thống vận hành vùng DNS; **không được công khai private key trong DNS hoặc repository**.

Trong mô hình vận hành truyền thống thường phân biệt:

- **Zone Signing Key (ZSK):** khóa dùng ký phần lớn các RRset dữ liệu của vùng.
- **Key Signing Key (KSK):** khóa thường dùng ký RRset DNSKEY; bản ghi DS ở parent thường trỏ tới KSK.

Đây là **cách phân vai vận hành**, không phải yêu cầu bắt buộc rằng mọi zone phải có hai khóa vật lý khác nhau. Một zone có thể dùng **Combined Signing Key (CSK)** hoặc cách quản lý khóa khác, miễn các quan hệ DNSSEC phù hợp giao thức.

### 4.2. RRSIG: chữ ký cho tập bản ghi

DNSSEC ký theo **RRset** (*Resource Record Set*): các bản ghi có cùng owner name, class và type được xem là một tập. **RRSIG** là bản ghi chứa chữ ký số và thông tin để validator xác minh RRset đó bằng DNSKEY phù hợp.

Một RRSIG có các thông tin như thuật toán, key tag, thời điểm chữ ký bắt đầu có hiệu lực (*inception*), thời điểm hết hạn (*expiration*) và loại RRset được ký. Vì vậy **đồng hồ sai hoặc chữ ký hết hạn** có thể khiến một vùng được ký trở nên không hợp lệ đối với validating resolver.

**DNSSEC chứng minh tính xác thực của cả tập bản ghi**, không có nghĩa bản ghi trỏ đến hệ thống đúng hoặc còn hoạt động. Ví dụ, một địa chỉ IP sai do người quản trị đưa vào zone rồi ký hợp lệ vẫn có thể vượt qua DNSSEC validation.

### 4.3. DS: liên kết vùng cha tới vùng con

**DS (Delegation Signer)** được công bố trong **vùng cha** và chứa thông tin tóm tắt mã hóa (*digest*) gắn với một DNSKEY của vùng con. Vùng cha có DNSSEC bảo vệ DS để validator kiểm tra khóa của vùng con có được ủy quyền từ chuỗi tin cậy phía trên hay không.

Ví dụ khái niệm:

- Vùng cha **example** công bố DS cho vùng con **shop.example**.
- Vùng con **shop.example** công bố DNSKEY và RRSIG của chính nó.
- Validator kiểm tra DS được vùng cha xác thực, rồi dùng DS để liên kết tới DNSKEY phù hợp của vùng con.

Các tên ở đây chỉ là **mô hình giả lập phục vụ học tập**. Trên Internet thật, registry/registrar có quy trình quản lý DS riêng. **DS nằm tại parent, không phải một bản ghi có thể tự thêm ở child rồi coi như đã tạo trust chain công khai.**

### 4.4. NSEC và NSEC3: bằng chứng về việc không tồn tại

DNSSEC không chỉ xác nhận những bản ghi **có tồn tại**. Khi một tên hoặc loại bản ghi không tồn tại, resolver cần xác minh rằng câu trả lời phủ định (NXDOMAIN hoặc NODATA) không bị giả mạo.

- **NSEC** cung cấp chứng cứ có ký số về khoảng tên/bản ghi không tồn tại, đồng thời có thể làm lộ cấu trúc tên của zone qua cơ chế liệt kê.
- **NSEC3** sử dụng giá trị băm của tên nhằm giảm khả năng liệt kê trực tiếp một số tên; tuy nhiên **không đảm bảo che giấu hoàn toàn tên miền** trước đoán từ điển, phân tích bản ghi công khai hoặc những nguồn dữ liệu khác.

NSEC3 có lựa chọn triển khai như opt-out với những đánh đổi về xác thực và vận hành; cần tuân thủ tài liệu của nền tảng ký vùng thay vì bật mặc định mà không hiểu ảnh hưởng.

### 4.5. Bảng tóm tắt

| Record | Vị trí thường gặp | Mục đích |
| --- | --- | --- |
| DNSKEY | Zone được ký | Công bố khóa công khai dùng để xác minh |
| RRSIG | Cùng zone với RRset được ký | Chữ ký số và thời hạn hiệu lực của RRset |
| DS | Parent zone của zone được ủy quyền | Gắn khóa vùng con vào chuỗi tin cậy của vùng cha |
| NSEC | Zone ký theo NSEC | Xác thực sự không tồn tại của tên/loại bản ghi |
| NSEC3 | Zone ký theo NSEC3 | Xác thực phủ định sử dụng tên băm, giảm lộ danh sách trực tiếp |

Những thuật ngữ như **KSK**, **ZSK** mô tả vai trò khóa; **DNSKEY**, **RRSIG**, **DS** mới là các loại bản ghi DNS.

## 5. Chain of trust hoạt động ra sao?

**Chain of trust** (chuỗi tin cậy) là mối liên hệ xác thực từ một trust anchor mà validator tin tưởng đến DNSKEY và chữ ký của zone cần kiểm tra.

Đối với DNS công khai, nhiều validating resolver bắt đầu từ **trust anchor của root DNS** được cung cấp/cập nhật theo cơ chế tin cậy của resolver. Root ký dữ liệu ủy quyền cần thiết để xác thực TLD; TLD ký DS liên kết tới vùng con; cuối cùng zone con ký RRset chứa dữ liệu cần trả lời.

~~~mermaid
flowchart TD
    TA["Trust anchor: root DNSKEY được tin cậy"] --> R["Xác minh DNSKEY/RRSIG của root"]
    R --> D1["Xác minh DS cho TLD"]
    D1 --> K1["Đối chiếu DNSKEY của TLD và chữ ký"]
    K1 --> D2["Xác minh DS của zone con tại TLD"]
    D2 --> K2["Đối chiếu DNSKEY của zone con"]
    K2 --> A["Xác minh RRSIG trên RRset A/AAAA/MX/..."]
    A --> OK["Kết quả được xác thực theo chuỗi tin cậy"]
~~~

Nếu một vùng cha **đã được ký** chứng thực rằng **không có DS** cho một delegation, validator có thể nhận biết đường tới vùng con đó là **insecure delegation** theo mô hình DNSSEC, thay vì mặc nhiên coi đó là tấn công. Nhưng nếu parent công bố DS và DNSKEY/RRSIG của child **không khớp**, kết quả có thể bị đánh giá là **bogus** và quá trình phân giải thất bại.

### 5.1. Ví dụ tình huống hợp lệ

Giả sử người quản trị ký zone **shop.example** trong một môi trường đào tạo có parent và trust anchor tương ứng. Vùng con công bố DNSKEY, RRSIG cho bản ghi web, còn parent công bố DS phù hợp. Một validating resolver có trust anchor của môi trường đó sẽ:

1. Xác thực dữ liệu DNSSEC của parent từ trust anchor.
2. Kiểm tra DS của shop.example và đối chiếu với DNSKEY vùng con.
3. Xác minh RRSIG của RRset chứa địa chỉ web.
4. Trả dữ liệu khi tất cả bước hợp lệ, theo chính sách resolver.

Các tên **.example** dùng để minh họa, không phải ví dụ một chuỗi DNSSEC công khai có thể phân giải ngay trên Internet.

### 5.2. Khi có DS nhưng không có khóa phù hợp

Nếu registrar/registry còn giữ DS trỏ đến khóa cũ nhưng nhà cung cấp DNS mới đã ngừng công bố DNSKEY đó, resolver có thể không xác minh được vùng con. Trong mô hình validating resolver thông thường, việc xác thực thất bại dẫn đến **SERVFAIL** hoặc một lỗi phân giải tương đương, dù nameserver vẫn trả dữ liệu A/AAAA.

**Đây là lỗi vận hành rất quan trọng:** di chuyển DNS provider, xoay khóa hoặc tắt ký zone phải được phối hợp với trạng thái DS ở parent, thời gian cache và chính sách xác thực.

## 6. Trạng thái kết quả DNSSEC validation

Các trạng thái khái niệm thường gặp:

| Trạng thái | Ý nghĩa | Cách diễn giải |
| --- | --- | --- |
| **Secure** | Có chuỗi tin cậy và dữ liệu được xác minh hợp lệ | Chữ ký phù hợp tại thời điểm xác minh; không đồng nghĩa máy chủ đích an toàn |
| **Insecure** | Phần dữ liệu không có chuỗi ký DNSSEC bắt buộc, và trạng thái thiếu ký được chấp nhận hợp lệ trong mô hình ủy quyền | Không được bảo vệ bằng DNSSEC end-to-end; không tự là lỗi |
| **Bogus** | Dữ liệu phải xác thực theo chuỗi tin cậy nhưng kiểm tra thất bại | Thường dẫn tới SERVFAIL tại validating resolver |
| **Indeterminate** | Không đủ cơ sở hoặc thiếu trust anchor thích hợp để đưa ra kết luận xác thực | Cần xem cấu hình và ngữ cảnh resolver |

**Secure** không chứng minh “trang web sạch mã độc”; nó chỉ nói dữ liệu DNS được xác thực theo cơ chế DNSSEC. **Insecure** không tự chứng minh có đầu độc DNS; tên miền có thể đơn giản chưa triển khai DNSSEC.

### 6.1. SERVFAIL khác NXDOMAIN

- **NXDOMAIN:** theo ngữ nghĩa DNS, tên được hỏi không tồn tại; đối với vùng ký DNSSEC có thể kèm bằng chứng phủ định được ký.
- **NOERROR/NODATA:** tên có thể tồn tại nhưng không có RRset đúng loại đang hỏi; với DNSSEC có thể được xác thực bằng NSEC/NSEC3.
- **SERVFAIL:** resolver gặp lỗi xử lý, truy vấn hoặc xác thực; **không đồng nghĩa tên miền không tồn tại**.

Do đó, một tên miền ký DNSSEC bị SERVFAIL không nên được xử lý bằng cách tự động đổi nó thành NXDOMAIN hoặc thay đổi bản ghi nếu chưa biết nguyên nhân.

## 7. Cờ DO, AD và CD trong truy vấn và phản hồi

Ba cờ thường được dùng khi quan sát DNSSEC:

| Cờ | Ý nghĩa | Điều cần nhớ |
| --- | --- | --- |
| **DO** (*DNSSEC OK*) | Bit trong phần mở rộng EDNS cho biết client/resolver sẵn sàng nhận dữ liệu DNSSEC liên quan | Yêu cầu dữ liệu phục vụ DNSSEC, **không tự bật DNSSEC validation** |
| **AD** (*Authenticated Data*) | Bit trong DNS header có thể cho biết resolver đã xác thực dữ liệu liên quan theo chính sách | Chỉ có ý nghĩa đáng tin nếu tin cậy resolver và đường phản hồi; không phải chữ ký |
| **CD** (*Checking Disabled*) | Yêu cầu resolver không áp dụng kiểm tra DNSSEC theo cách thông thường đối với truy vấn | Hữu ích trong chẩn đoán; không phải cách sửa lỗi hay biện pháp bảo mật |

Ví dụ, công cụ **dig +dnssec** thường yêu cầu các bản ghi DNSSEC bằng DO bit, nhưng **dig mặc định không thực hiện đầy đủ quá trình xác minh chữ ký chỉ vì có tham số này**. Nếu thấy AD trên phản hồi, cần hiểu đó là tín hiệu của resolver mà bạn đang hỏi, không phải bằng chứng bất biến có thể tin trên một đường kết nối không được bảo vệ.

### 7.1. Một số giới hạn khi diễn giải phản hồi

- Một resolver có thể đã kiểm tra DNSSEC nhưng không đặt AD do chính sách hoặc cách client gửi truy vấn.
- Một phản hồi không có RRSIG trong phần ANSWER không tự chứng minh zone không ký, do cách truy vấn, cache hoặc cách resolver trả lời.
- Có thể yêu cầu CD để tìm dữ liệu phục vụ điều tra lỗi validation, nhưng **không được coi việc bật CD cho người dùng cuối là giải pháp lâu dài**.
- Nếu đang sử dụng forwarder, cần biết thành phần **nào thật sự thực hiện validation** và đường từ nó tới client có được tin cậy không.

## 8. Vòng đời triển khai DNSSEC cho một zone

Để triển khai DNSSEC an toàn cần phối hợp **vùng DNS, khóa ký, parent DS, thời gian truyền cache và khả năng giám sát**.

### Bước 1 – Kiểm kê và xác định trách nhiệm

Xác định tên miền và những zone đang quản lý, nhà cung cấp authoritative DNS, registrar, tài khoản quản trị, người có quyền sửa DS, chính sách backup và địa chỉ liên hệ khi xảy ra sự cố.

Kiểm tra các dịch vụ phụ thuộc DNS: web, API, email, VPN, DNS resolver nội bộ, cloud workloads và những điểm tích hợp của đối tác. Cần hiểu **ai sở hữu zone** và **ai có quyền chỉnh bản ghi ở parent**.

### Bước 2 – Kiểm tra năng lực nhà cung cấp

Xác định authoritative DNS có hỗ trợ DNSSEC signing, DNSKEY/RRSIG, NSEC/NSEC3, xoay khóa tự động và monitoring không. Nếu dùng nhiều DNS provider, phải có chiến lược ký đa nhà cung cấp phù hợp; không đơn giản cộng RRset từ các provider chưa đồng bộ.

### Bước 3 – Chuẩn bị khóa và ký vùng

Chọn cơ chế quản lý khóa và thuật toán được hệ sinh thái resolver hỗ trợ, theo chính sách của tổ chức và nhà cung cấp. Private key phải được kiểm soát quyền, lưu giữ an toàn và có khả năng phục hồi trong trường hợp cần thiết. Nên có lịch giám sát chữ ký và gia hạn tự động trước khi hết hạn.

### Bước 4 – Xác minh nội dung ký trước khi công bố DS

Kiểm tra rằng DNSKEY xuất hiện đầy đủ ở authoritative nameserver, RRSIG có thời hạn hợp lệ, RRset được phục vụ nhất quán và phản hồi phủ định có NSEC/NSEC3 khi cần. Trong giai đoạn chuẩn bị, DNSSEC có thể chưa được liên kết từ parent; kết quả xác thực công khai khi đó còn phụ thuộc tình trạng delegation.

### Bước 5 – Công bố DS tại parent theo quy trình registrar

Khi child đã sẵn sàng, đưa thông tin DS phù hợp lên parent qua registrar hoặc registry. Không tự giả định rằng đã bật tính năng DNSSEC ở DNS provider thì DS tự xuất hiện và chính xác ở parent.

**Giai đoạn công bố DS là điểm chuyển quan trọng:** khi validating resolver nhận được chuỗi từ parent đến child, mọi lỗi khóa hoặc chữ ký có thể khiến truy vấn cho zone chuyển thành bogus.

### Bước 6 – Kiểm thử từ nhiều validating resolver

Kiểm tra bản ghi phổ biến, bản ghi phủ định, IPv4/IPv6, cả UDP/TCP DNS và thời điểm trước/sau TTL. Theo dõi phản hồi của authoritative DNS và kết quả validation độc lập để xác định lỗi thuộc zone, parent hay mạng.

### Bước 7 – Duy trì, giám sát và xoay khóa

Thiết lập cảnh báo cho:

- RRSIG sắp hết hạn hoặc đã hết hạn.
- DNSKEY và DS thiếu, sai hoặc không nhất quán.
- Thay đổi đột ngột ở parent delegation hoặc nameserver.
- SERVFAIL và lỗi validation tăng.
- Kết nối DNS TCP/UDP thất bại, response bị cắt hoặc gián đoạn phân giải.

Lưu lại quy trình **key rollover, chuyển nhà cung cấp, khóa bị lộ và khôi phục** trước khi cần sử dụng trong sự cố.

## 9. KSK, ZSK, CSK và key rollover

**Key rollover** là quá trình thay khóa ký mà vẫn duy trì khả năng xác minh cho dữ liệu có thể còn nằm trong cache ở resolver.

### 9.1. Rollover ZSK

Trong mô hình dùng KSK và ZSK tách biệt, thay ZSK chủ yếu liên quan đến những RRset dữ liệu được ký bằng ZSK. Quy trình thường bao gồm:

1. Chuẩn bị khóa mới và lịch hiệu lực.
2. Công bố DNSKEY cần thiết để validator có thể xác minh chữ ký mới.
3. Chuyển ký RRset theo cơ chế nhà cung cấp, có tính tới thời gian cache và RRSIG.
4. Chỉ gỡ khóa hoặc chữ ký cũ khi những dữ liệu còn dùng khóa cũ đã hết vòng đời cần thiết.
5. Quan sát validation trong suốt quá trình và xác minh hậu chuyển đổi.

Chi tiết **pre-publish**, **double-signature** hoặc các phương pháp khác thay đổi theo nền tảng. Không tự chọn một khoảng chờ cứng nếu chưa tính TTL, thời gian lan truyền và cơ chế ký của hệ thống.

### 9.2. Rollover KSK và DS ở parent

Khi thay khóa được DS liên kết, cần phối hợp **DNSKEY ở child** với **DS ở parent**. Nếu parent trỏ tới khóa đã bị xóa hoặc child chưa công bố khóa phù hợp, validating resolver có thể coi zone là bogus.

Một kế hoạch bảo thủ thường phải cho phép giai đoạn **đồng tồn tại** cần thiết giữa khóa cũ và mới, công bố/cập nhật DS theo quy trình parent, chờ dữ liệu cache hết hiệu lực và kiểm tra validation trước khi rút hoàn toàn khóa cũ.

Không có một thứ tự đơn lẻ phù hợp mọi quy trình nhà cung cấp, nhất là khi chuyển provider hoặc dùng CSK. **Dùng runbook được thử nghiệm của nhà cung cấp/registry và thực hiện thay đổi có giám sát.**

### 9.3. Rủi ro do private key bị lộ

DNSSEC chỉ bảo vệ được khi khóa ký được bảo vệ. Nếu một private key bị lộ, kẻ có khóa có thể tạo chữ ký hợp lệ theo phạm vi khóa/chuỗi tin cậy và làm suy yếu mục tiêu xác thực. Cần có kế hoạch thay thế khóa, thay DS nếu liên quan, quản lý bằng chứng và khóa cũ, đồng thời bảo vệ tài khoản DNS/registrar bằng MFA và quyền tối thiểu.

## 10. Di chuyển authoritative DNS provider và xử lý DS

Di chuyển zone DNS là một trong những tình huống dễ gây lỗi DNSSEC.

Giả sử zone đang được ký tại **Provider A**, parent đang có DS trỏ tới khóa của A. Doanh nghiệp đổi sang **Provider B** nhưng B sử dụng khóa khác. Nếu nameserver được chuyển sang B trong khi DS tại parent vẫn trỏ tới khóa A và B không công bố khóa được tin cậy tương ứng, kết quả có thể là **SERVFAIL trên validating resolver**.

Các hướng xử lý phụ thuộc năng lực provider và yêu cầu sẵn sàng:

- **Chuyển đổi giữ chuỗi tin cậy:** phối hợp DNSKEY, DS, ký zone và thời điểm chuyển NS theo một kế hoạch ký đa nhà cung cấp hoặc chuyển khóa được hỗ trợ.
- **Chuyển đổi qua giai đoạn chưa được liên kết bằng DS:** có thể dùng trong những hoàn cảnh thích hợp khi phải di chuyển giữa các nền tảng không tương thích; điều này **tạm làm mất bảo vệ DNSSEC theo chuỗi công khai** và cần đánh giá rủi ro, thời gian cache, approval và kiểm tra cẩn thận.

Không nên coi “xóa DS ngay lập tức” là thao tác khắc phục không có rủi ro: bản ghi DS cũ có thể còn trong cache, và việc bỏ DS làm mất xác thực DNSSEC tại delegation. Cần phối hợp với registrar, DNS provider, SOC/NOC và chủ dịch vụ.

### 10.1. Checklist di chuyển

| Hạng mục | Câu hỏi cần trả lời |
| --- | --- |
| Parent DS | DS hiện tại trỏ tới khóa nào, ai có quyền sửa, TTL liên quan? |
| Child DNSKEY | Provider mới công bố những khóa nào và ai ký chúng? |
| RRSIG | Chữ ký còn hạn đến khi nào, cả hai provider có trả dữ liệu nhất quán không? |
| NS delegation | NS ở parent và NS trong child được cập nhật theo trình tự nào? |
| Cache | Dữ liệu cũ còn được resolver giữ trong bao lâu? |
| Monitoring | Có kiểm tra secure/bogus từ nhiều mạng và thời điểm không? |
| Rollback | Có thể quay lại trạng thái được ký hợp lệ mà không tạo DS mismatch không? |

## 11. Vận hành kiểm tra DNSSEC bằng công cụ

Những lệnh dưới đây **chỉ minh họa cách đọc kết quả**. Thay tên miền bằng zone bạn sở hữu hoặc được phép kiểm tra, và thay IP resolver bằng địa chỉ **resolver thử nghiệm đang hoạt động**. Không kỳ vọng một tên minh họa trong tài liệu sẽ trả về dữ liệu thực.

### 11.1. Yêu cầu dữ liệu DNSSEC với dig

~~~bash
# Hỏi DNSKEY ở apex và yêu cầu dữ liệu DNSSEC.
dig +dnssec +multi @127.0.0.1 your-domain.tld DNSKEY

# Hỏi DS: trong mô hình DNSSEC, DS của zone do parent công bố.
dig +dnssec +multi @127.0.0.1 your-domain.tld DS

# Hỏi dữ liệu A và các bản ghi DNSSEC liên quan khi resolver cung cấp.
dig +dnssec +multi @127.0.0.1 www.your-domain.tld A

# Kiểm tra phản hồi phủ định (tên được chọn không tồn tại trong zone thử nghiệm).
dig +dnssec +multi @127.0.0.1 missing-label.your-domain.tld A
~~~

**Lưu ý:** các lệnh gửi DNS query thật tới resolver ở địa chỉ đã chọn. Nếu trên máy không có resolver tại **127.0.0.1**, cần thay bằng resolver trong lab. **dig +dnssec** yêu cầu DO bit và in các dữ liệu DNSSEC được trả về; nó **không tự tạo quy trình xác minh hoàn chỉnh** giống validating resolver.

### 11.2. Kiểm tra validation

Trong môi trường có **delv** và trust anchor phù hợp, có thể kiểm tra khả năng xác minh:

~~~bash
delv @127.0.0.1 www.your-domain.tld A
~~~

Công cụ và các trust anchor có sẵn phụ thuộc máy cài đặt. Với một **zone riêng trong lab** không thuộc chuỗi root công khai, phải cấu hình trust anchor riêng theo hướng dẫn resolver/công cụ; không thể mong các resolver Internet xác nhận zone tùy ý.

### 11.3. Các bước đọc kết quả

1. Kiểm tra **response code**: NOERROR, NXDOMAIN, SERVFAIL hay lỗi vận chuyển.
2. Kiểm tra **DO/AD/CD**, nguồn resolver đang hỏi và có tin cậy nó không.
3. Kiểm tra **DNSKEY, DS và RRSIG** có mặt khi phù hợp, thời gian hiệu lực và thuật toán có được hỗ trợ không.
4. Với kết quả phủ định, kiểm tra chứng cứ **NSEC/NSEC3** và sự hợp lệ của chữ ký.
5. Nếu chỉ validating resolver trả SERVFAIL, nhưng authoritative vẫn cung cấp dữ liệu, cần điều tra validation chain thay vì sửa bản ghi A vội vàng.

Không được dựa vào một phản hồi duy nhất để kết luận toàn bộ deployment đã đúng. Cần xét cache, nhiều nameserver, nhiều mạng, IPv4/IPv6 và quá trình chuyển khóa.

## 12. Các lỗi DNSSEC thường gặp và cách khoanh vùng

| Triệu chứng | Nguyên nhân có thể | Kiểm tra ưu tiên |
| --- | --- | --- |
| Resolver xác thực trả SERVFAIL, non-validating resolver có vẻ trả được A | Chữ ký không hợp lệ, DS mismatch, DNSKEY thiếu hoặc dữ liệu DNSSEC lỗi | Kiểm tra chuỗi DS → DNSKEY → RRSIG; xem log validator |
| Chỉ xảy ra sau khi đổi DNS provider | Parent DS còn trỏ tới khóa cũ, DNSKEY/NS chưa đồng bộ | Đối chiếu parent DS và child DNSKEY, trạng thái cache |
| Chỉ một số tên hoặc loại bản ghi lỗi | RRset/RRSIG thiếu hoặc không nhất quán; bằng chứng phủ định lỗi | Kiểm tra RRset, RRSIG cùng tên/type, NSEC/NSEC3 |
| Lỗi xuất hiện gần thời điểm hết hạn chữ ký | RRSIG đã hết hạn hoặc đồng hồ sai | Kiểm tra inception/expiration và thời gian máy ký/validator |
| UDP DNS thất bại nhưng TCP DNS dùng được | Vấn đề kích thước phản hồi, EDNS, MTU, phân mảnh hoặc lọc đường mạng | Kiểm tra resolver, firewall UDP/TCP 53, phản hồi cắt ngắn |
| Một số resolver lỗi, số khác hoạt động | Cache khác nhau, trust anchor, thuật toán hoặc chính sách xác thực khác | So sánh log, thời điểm, danh sách resolver |
| NXDOMAIN có chữ ký nhưng client không truy cập được | Tên thật sự thiếu hoặc ứng dụng hỏi sai tên | Phân biệt phủ định hợp lệ với lỗi cấu hình dữ liệu |
| Thấy DNSKEY và RRSIG nhưng không có trạng thái secure | Chưa có DS ở parent hoặc không có trust anchor phù hợp | Kiểm tra chuỗi từ parent và cấu hình validator |

### 12.1. Vì sao SERVFAIL không đủ chẩn đoán?

SERVFAIL có thể xuất hiện do **DNSSEC validation thất bại**, nhưng cũng có thể do authoritative server không truy cập được, timeout, chuyển tiếp lỗi hoặc những vấn đề resolver khác. Muốn kết luận DNSSEC là nguyên nhân, phải xem **validation log, chuỗi chữ ký, trạng thái parent/child và khả năng truy cập các nameserver**.

### 12.2. RRSIG hết hạn và vấn đề đồng hồ

Chữ ký DNSSEC có các mốc inception/expiration. Nếu hệ thống ký vùng ngừng hoạt động và không gia hạn chữ ký trước khi hết hạn, validating resolver có thể từ chối dữ liệu vốn vẫn còn nằm trong authoritative zone. Đồng hồ ở server ký hoặc validating resolver sai cũng có thể gây lỗi thời gian.

Biện pháp: theo dõi **thời gian còn hiệu lực của RRSIG** và hệ thống đồng bộ thời gian, cảnh báo đủ sớm để khắc phục; đừng chờ người dùng gặp SERVFAIL mới phát hiện.

### 12.3. UDP/TCP, EDNS và phản hồi lớn

Phản hồi DNSSEC có thể lớn hơn DNS không ký do RRSIG, DNSKEY và chứng cứ phủ định. Khi phản hồi UDP không truyền được đầy đủ, DNS có thể cần cơ chế **truncated response** và thử lại bằng **TCP 53**. Firewall hoặc network ACL chặn TCP 53, xử lý EDNS không đúng hoặc làm mất mảnh UDP có thể gây lỗi phân giải không ổn định.

Do đó, bảo vệ DNS không đồng nghĩa “chỉ cho UDP 53”. Cần kiểm thử đường UDP và TCP, kích thước phản hồi, EDNS buffer và MTU trong phạm vi hạ tầng được quản lý.

## 13. DNSSEC không giải quyết những rủi ro nào?

| Rủi ro / nhu cầu | DNSSEC có giải quyết trực tiếp không? | Biện pháp bổ sung |
| --- | --- | --- |
| Đầu độc bản ghi của zone đã ký khi validator hoạt động đúng | Có, bằng xác thực nguồn gốc và toàn vẹn trong giới hạn chuỗi tin cậy | Cập nhật resolver, bảo vệ trust anchor và vận hành khóa |
| Nghe lén tên miền trong truy vấn DNS | **Không** | DoT/DoH hoặc kênh bảo mật, cùng chính sách quyền riêng tư |
| Giả mạo phản hồi giữa stub và resolver không được tin cậy | Không tự đảm bảo toàn bộ đoạn này | Resolver đáng tin cậy, kênh bảo mật hoặc validation tại client |
| DNS provider hoặc tài khoản registrar bị chiếm quyền | **Không** | MFA, least privilege, audit, khóa bảo vệ và quy trình thay đổi |
| Chủ zone ký một bản ghi sai hoặc độc hại | **Không** | Quy trình kiểm soát thay đổi, asset inventory, kiểm tra dữ liệu |
| Website dùng chứng thư TLS không hợp lệ | **Không** | Xác minh TLS và danh tính máy chủ |
| DDoS vào authoritative DNS | **Không** | Anycast/capacity, DDoS protection, giám sát và dự phòng |
| DNS tunneling và dữ liệu đi qua DNS hợp lệ | Không tự ngăn | DNS monitoring, egress policy, IDS/IPS và điều tra |
| Tấn công lừa người dùng bằng tên miền khác đã được đăng ký | Không tự ngăn | Nhận diện tên miền, bảo vệ trình duyệt/email, giáo dục và cảnh báo |
| Tên miền nội bộ chưa có chain of trust phù hợp | Không tự tạo trust anchor | Thiết kế trust anchor và DNSSEC nội bộ nếu có yêu cầu |

**Một DNSSEC signature hợp lệ chứng minh dữ liệu thuộc vùng được ký theo cơ chế tin cậy; nó không phải chứng chỉ “nội dung an toàn”.** Đừng dùng DNSSEC làm lý do bỏ qua kiểm tra HTTPS, phân quyền API hoặc giám sát DNS.

## 14. Phối hợp DNSSEC với DoH, DoT, DANE và các lớp bảo vệ mạng

### 14.1. DNSSEC và DNS over HTTPS / DNS over TLS

**DoH** và **DoT** bảo vệ truy vấn/responses giữa client và resolver ở mức kênh, nhằm giảm nguy cơ nghe lén hoặc sửa đổi trên đoạn đó. **DNSSEC** bảo vệ dữ liệu đã ký từ authoritative zone theo chuỗi tin cậy tới nơi validation. Một kiến trúc có thể dùng **cả DNSSEC validation tại resolver và DoH/DoT giữa client với resolver**.

Nếu resolver không xác thực DNSSEC, việc mã hóa kết nối tới resolver vẫn không tự chứng minh các bản ghi nhận được là đúng theo authoritative zone.

### 14.2. DANE và TLSA

**DANE (DNS-based Authentication of Named Entities)** là họ cơ chế sử dụng DNSSEC để xác thực những liên kết liên quan TLS, thường thông qua bản ghi **TLSA** trong những dịch vụ hỗ trợ. Một số hệ thống email có thể dùng DANE theo thiết kế phù hợp.

DANE **không phải tên gọi khác của DNSSEC**. Nó cần DNSSEC hợp lệ để tin cậy vào dữ liệu TLSA và còn phụ thuộc cách giao thức/ứng dụng sử dụng. Không nên mặc định mọi trình duyệt web hiện đại đều xác minh TLS theo DANE.

### 14.3. Segmentation, firewall và VPN

DNS resolver nội bộ cần được đưa vào ma trận kết nối:

- Client chỉ nên hỏi những resolver được phê duyệt theo chính sách, tránh tự ý cho mọi máy liên lạc với mọi DNS server.
- Resolver cần đường ra phù hợp tới authoritative DNS qua UDP/TCP 53 hoặc đến forwarder được phê duyệt.
- Giao diện quản trị DNS và quyền đổi DS/DNSKEY phải tách khỏi mạng khách và giới hạn theo người quản trị.
- Nếu DNS lưu thông qua VPN, cần xác định nơi resolver thực thi validation và đường tới authoritative server.

**Packet filtering không xác minh được DNSSEC signature**; nó điều khiển khả năng kết nối. Một rule cho phép UDP 53 không thay thế validation.

### 14.4. IDS/IPS và DNS logging

IDS/IPS có thể phát hiện mẫu truy vấn DNS bất thường, lưu lượng không đúng chính sách hoặc dấu hiệu DNS tunneling trong phần dữ liệu quan sát được. Nhưng **việc một câu trả lời có chữ ký DNSSEC hợp lệ** không chứng minh nó không chứa tên miền độc hại hoặc không bị người dùng lợi dụng sai mục đích. Cần kết hợp DNS logs, threat intelligence có kiểm chứng và nhật ký ứng dụng.

### 14.5. Cloud và mạng không dây

Trong cloud, DNS resolver hoặc DNS zone có thể là managed service. Cần xác định nhà cung cấp hỗ trợ signing, validation, DS delegation, audit và rollover ở mức nào; đừng nhầm khả năng ký zone với khả năng validation của resolver.

Với mạng Wi-Fi, khách kết nối có thể nhận resolver qua DHCP hoặc cấu hình tương đương. Nếu client tin một resolver không được quản lý và kết nối không được bảo vệ, DNSSEC ở authoritative zone chưa đủ để bảo đảm đoạn phản hồi tới client được tin cậy. Cần bảo vệ cấp phát cấu hình mạng, giới hạn DNS egress và chọn kênh resolver phù hợp.

## 15. Kiến trúc triển khai và vận hành: ví dụ giả lập

Một doanh nghiệp có dịch vụ web, email và VPN. Các thành phần:

- Vùng DNS công khai **shop.example** được ký DNSSEC trong một lab có trust anchor/parent tương ứng.
- Hai authoritative nameserver do DNS provider quản lý, cần đồng bộ RRset và chữ ký.
- Recursive validating resolver dành cho ứng dụng nội bộ.
- Edge firewall chỉ cho phép những luồng DNS cần thiết, bao gồm UDP và TCP 53 theo thiết kế.
- SOC giám sát lỗi validation, SERVFAIL, DNSKEY/DS và các chỉ số availability.

~~~mermaid
flowchart TD
    U["User / ứng dụng"] -->|"DNS qua kênh được quản lý"| V["Validating resolver"]
    V -->|"DNS UDP/TCP 53"| F{"Network policy"}
    F --> P["Parent DNS: DS"]
    F --> A["Authoritative DNS: DNSKEY, RRSIG, RRset"]
    P -. "Chain of trust" .-> V
    A -. "Dữ liệu đã ký" .-> V
    V -->|"Dữ liệu secure hoặc lỗi validation"| U
    P -. "Thay đổi DS" .-> S["Registrar / DNS operations"]
    A -. "Ký vùng / rollover" .-> S
    V -. "SERVFAIL, validation, latency" .-> M["SOC / Monitoring"]
    A -. "RRSIG expiry, DNSKEY" .-> M
~~~

### 15.1. Mẫu hồ sơ cấu hình/giám sát

~~~yaml
dnssecOperations:
  zone: shop.example
  environment: synthetic-training
  authoritativeDns:
    managedBy: dns-operations
    signingEnabled: true
    expectedRecords:
      - DNSKEY
      - RRSIG
      - NSEC-or-NSEC3
  delegation:
    parentDsRequiredForPublicChain: true
    registrarOwner: domain-operations
    checkDsDnskeyConsistency: true
  validation:
    resolverOwner: network-platform
    trustAnchor: lab-defined
    verifyPositiveResponses: true
    verifyNegativeResponses: true
  monitoring:
    checkSignatureExpiry: true
    checkParentChildKeyMatch: true
    trackServfailAndValidationErrors: true
    checkUdpAndTcp53: true
    checkAuthoritativeConsistency: true
  changeControl:
    requireApprovedRolloverPlan: true
    trackTtlAndCacheWindow: true
    keepRollbackProcedure: true
    limitDnsAndRegistrarAdminAccess: true
~~~

YAML trên chỉ là **mô hình vận hành**, không phải cấu hình cho BIND, Unbound, PowerDNS, cloud DNS hay bất kỳ registrar nào. Với môi trường thật, phải đối chiếu tài liệu của sản phẩm và quy trình bảo mật của tổ chức.

## 16. Kịch bản sự cố: người dùng nhận SERVFAIL sau khi đổi DNS provider

Giả sử một doanh nghiệp đang dùng DNSSEC ở Provider A, sau đó chuyển authoritative nameserver sang Provider B. Người dùng dùng validating resolver báo lỗi không vào được website; một số resolver không bật validation vẫn trả về A record.

### 16.1. Những dữ kiện cần kiểm tra

1. **Parent:** DS hiện tại có còn trỏ tới DNSKEY của A không?
2. **Child:** Provider B đang công bố DNSKEY nào? Có RRSIG hợp lệ cho các RRset được yêu cầu không?
3. **Resolver:** kết quả validation là bogus, insecure hay có timeout do mạng?
4. **Thời gian:** những bản ghi cũ ở parent/child đã hết TTL chưa? RRSIG có còn hiệu lực theo đồng hồ validator không?
5. **Đường mạng:** UDP/TCP 53 và khả năng truy cập tất cả authoritative nameserver có ổn định không?
6. **Phạm vi:** lỗi xuất hiện ở mọi resolver hay chỉ một số resolver/cache hoặc tuyến?

### 16.2. Phân tích và quyết định

Nếu parent DS khớp khóa A nhưng child chỉ có khóa B, chuỗi tin cậy bị đứt. Đây là **lỗi DNSSEC vận hành**, không tự chứng minh có tấn công vào DNS. Đội vận hành cần phục hồi chuỗi DS–DNSKEY–RRSIG hợp lệ theo kế hoạch và có thể cần phối hợp registrar/provider.

Không nên “khắc phục nhanh” bằng cách vô hiệu validation cho tất cả client hoặc xóa DS khi chưa hiểu cache và đánh đổi bảo mật. Hành động khẩn cấp phải có người có thẩm quyền phê duyệt, đường rollback và xác minh từ các validating resolver sau thay đổi.

### 16.3. Xác nhận khôi phục

Kiểm tra dữ liệu A/AAAA/MX quan trọng, NXDOMAIN/NODATA có chứng cứ hợp lệ, trạng thái secure tại resolver được tin cậy và tỷ lệ SERVFAIL giảm. Đồng thời kiểm tra website HTTPS, email hoặc VPN hoạt động vì **DNSSEC hợp lệ không tự xác minh toàn bộ dịch vụ nghiệp vụ đã phục hồi**.

## 17. Bài tập và câu hỏi tự kiểm tra

### Câu hỏi 1

DNSSEC bảo vệ tính bí mật của truy vấn DNS hay tính xác thực/toàn vẹn của dữ liệu DNS? Cần công nghệ gì để bảo vệ đường truyền client–resolver?

**Gợi ý:** DNSSEC bảo vệ xác thực nguồn và toàn vẹn dữ liệu đã ký; dùng DoT/DoH hoặc kênh bảo mật phù hợp để bảo vệ truy vấn/responses trên đoạn client–resolver.

### Câu hỏi 2

Tại sao ký zone và xuất hiện DNSKEY/RRSIG chưa đủ để kết luận zone đã được bảo vệ theo chuỗi tin cậy của DNS root công khai?

**Gợi ý:** cần liên kết hợp lệ từ parent thông qua DS và cấu hình trust anchor phía validator.

### Câu hỏi 3

DS đặt tại child zone hay parent zone? Điều gì xảy ra nếu parent DS còn trỏ tới khóa đã bị xóa ở child?

**Gợi ý:** DS nằm ở parent; mismatch có thể làm validating resolver đánh giá zone là bogus và trả lỗi phân giải.

### Câu hỏi 4

Trong một vùng ký DNSSEC, làm sao resolver xác minh câu trả lời rằng tên hoặc RRset không tồn tại?

**Gợi ý:** dùng chứng cứ phủ định có chữ ký qua NSEC/NSEC3, theo giao thức và trạng thái zone.

### Câu hỏi 5

Khác biệt giữa **insecure delegation** và **bogus validation** là gì?

**Gợi ý:** insecure có thể là sự thiếu DS được chấp nhận hợp lệ; bogus là dữ liệu lẽ ra phải xác thực nhưng không vượt qua kiểm tra.

### Câu hỏi 6

Tại sao dig +dnssec không tự chứng minh dữ liệu đã được xác minh? Bit AD có giới hạn gì?

**Gợi ý:** yêu cầu DO bit không tự thực hiện xác minh; AD là dấu hiệu do resolver đặt và chỉ đáng tin theo quan hệ tin cậy/kênh trả lời.

### Câu hỏi 7

Vì sao DNSSEC làm tăng nhu cầu kiểm thử DNS TCP 53 cũng như UDP 53?

**Gợi ý:** chữ ký và DNSKEY làm phản hồi lớn hơn; có thể cần fallback sang TCP khi UDP bị cắt ngắn hoặc không phù hợp kích thước đường truyền.

### Câu hỏi 8

Một bản ghi A sai được người quản trị công bố rồi ký hợp lệ có vượt qua validation không? Điều này cho thấy giới hạn gì?

**Gợi ý:** có thể vẫn hợp lệ về mặt DNSSEC; công nghệ không đánh giá địa chỉ có đúng nghiệp vụ hay không.

### Bài tập thực hành trên giấy

Thiết kế kế hoạch kích hoạt DNSSEC cho zone thuộc quyền quản lý của bạn (hoặc zone giả lập trong lab). Bài làm phải có:

1. Danh mục authoritative DNS, recursive validating resolver, registrar và chủ sở hữu.
2. Sơ đồ **root/parent → DS → DNSKEY/RRSIG ở child → RRset**.
3. Kế hoạch công bố DS, TTL/cache và cách xác nhận chuỗi trước/sau chuyển đổi.
4. Các phép kiểm thử positive response và negative response, trạng thái secure/insecure/bogus.
5. Danh sách log/counter theo dõi RRSIG expiry, DS mismatch, SERVFAIL, UDP/TCP 53.
6. Phương án khôi phục nếu khóa hết hạn hoặc di chuyển provider làm đứt chuỗi.
7. Những kiểm soát còn cần ngoài DNSSEC: TLS, DoH/DoT, MFA, firewall, VPN, IDS/IPS và quản lý thay đổi.

Một kế hoạch đạt yêu cầu khi **bảo vệ được chuỗi tin cậy mà vẫn duy trì tính sẵn sàng của phân giải DNS**, có phân công chủ sở hữu và bằng chứng kiểm thử.

## 18. Những điều cần ghi nhớ

- **DNSSEC xác thực nguồn gốc và tính toàn vẹn của dữ liệu DNS đã ký**, không mã hóa truy vấn và không tự chứng minh website/IP an toàn.
- **DNSKEY là khóa công khai, RRSIG là chữ ký RRset, DS ở parent tạo liên kết tin cậy**, còn NSEC/NSEC3 chứng minh sự không tồn tại của tên/loại bản ghi.
- **Chuỗi tin cậy và validating resolver là điều kiện quyết định.** Một zone có DNSKEY/RRSIG chưa chắc đã được xác thực từ trust anchor công khai.
- **Secure, insecure, bogus và indeterminate có ý nghĩa khác nhau**; SERVFAIL có thể do DNSSEC lỗi nhưng cũng có thể do sự cố DNS khác.
- **DO không đồng nghĩa validation; AD cần quan hệ tin cậy với resolver; CD chỉ phục vụ những mục đích như chẩn đoán.**
- **Key rollover và thay DNS provider đòi hỏi phối hợp DS, DNSKEY, RRSIG, TTL và cache** để tránh biến zone hợp lệ thành bogus.
- **Phải giám sát chữ ký hết hạn, DS mismatch, thời gian, phản hồi UDP/TCP và khả năng phục vụ của authoritative/resolver.**
- **DNSSEC là một lớp trong phòng vệ mạng nhiều tầng**, cần phối hợp TLS, DoH/DoT, IAM/MFA, firewall, IDS/IPS, giám sát và kiểm soát thay đổi.
