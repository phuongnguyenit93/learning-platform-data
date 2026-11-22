# Chống phát lại assertion và đánh giá cơ chế lưu vết dùng chung giữa các nút

Trong SAML 2.0 federation, **Service Provider (SP)** nhận một `SAMLResponse` từ Identity Provider (IdP), xác minh các assertion rồi tạo phiên đăng nhập. Một assertion có chữ ký hợp lệ, đúng issuer/audience và còn trong thời hạn **vẫn không nên được chấp nhận lần thứ hai**: kẻ tấn công có thể sao chép thông điệp từ một thiết bị hoặc yêu cầu trước đó và gửi lại khi nó còn hiệu lực. Đó là **replay attack** (tấn công phát lại).

Bài này tập trung vào hai câu hỏi kỹ thuật gắn liền nhau:

1. **Chống phát lại SAML assertion:** SP nhận diện chính xác assertion đã dùng, từ chối lần dùng tiếp theo, lựa chọn TTL không ngắn hơn cửa sổ hiệu lực.
2. **Đánh giá lưu vết dùng chung giữa các nút:** khi nhiều instance Spring Security cùng nhận callback, làm thế nào chỉ một instance được phép tiêu thụ cùng một assertion, kể cả lúc request đến đồng thời, cache bị gián đoạn hoặc có failover?

**Nguyên tắc:** kiểm tra chữ ký/issuer/audience/thời hạn và **replay protection** là các điều kiện **phải kết hợp**. Một cache chống replay không thay thế validator SAML; ngược lại, validator SAML không tự chứng minh một assertion chưa từng được dùng trên các máy chủ khác.

## 1. Mô hình tấn công: chữ ký đúng nhưng bị dùng lại

Giả sử IdP phát hành assertion `_assertion-7` cho ứng dụng báo cáo, bearer `SubjectConfirmationData@NotOnOrAfter=10:05Z`.

~~~text
                   IdP
                    |
            SAMLResponse + assertion _assertion-7
                    |
        +-----------v-----------+
        | Browser người dùng    |
        +-----------+-----------+
                    | POST /login/saml2/sso/corporate
                    v
              SP Node A
        - chữ ký hợp lệ
        - audience/recipient đúng
        - assertion còn hiệu lực
        - chưa thấy _assertion-7 -> chấp nhận
                    |
              phiên đăng nhập

Tấn công / phát lại cùng assertion trước 10:05Z:
        HTTP POST SAMLResponse y hệt
                    |
                    v
              SP Node B
        - chữ ký vẫn hợp lệ
        - assertion vẫn còn hiệu lực
        - nếu chỉ có cache cục bộ B: "chưa thấy"
                    |
             ĐĂNG NHẬP LẦN HAI (lỗi!)
~~~

Kẻ tấn công không nhất thiết phải sửa chữ ký. Chữ ký bảo vệ **tính toàn vẹn và nguồn phát hành**, không bảo vệ việc **một thông điệp đã được sử dụng trước đó**. Cần lưu một **replay marker** (dấu đã dùng) dùng chung cho mọi node có thể xử lý cùng một luồng SSO.

Trong Web Browser SSO, một SAML bearer assertion thường được đưa qua trình duyệt tới SP; do đó cửa sổ thời gian ngắn và các ràng buộc `InResponseTo`, session, recipient có ý nghĩa quan trọng. Tuy vậy, chỉ dựa vào `InResponseTo` là chưa đủ khi ứng dụng hỗ trợ IdP-initiated SSO, sử dụng repository yếu hoặc có nhiều node không chia sẻ trạng thái.

### 1.1. Bốn dạng trạng thái đừng đánh đồng

| Trạng thái | Khóa/nguồn điển hình | Câu hỏi được giải quyết |
| --- | --- | --- |
| **AuthnRequest pending** | `AuthnRequest@ID` gắn phiên trình duyệt, `Saml2AuthenticationRequestRepository`. | Callback có thuộc **giao dịch đăng nhập đã khởi tạo ở phiên này** không? |
| **Response replay** | `Response@ID` + issuer/context đáng tin. | Cùng **Response** đã được xử lý trước đó chưa? |
| **Assertion replay** | `Assertion@ID` + issuer/context đáng tin. | Cùng **assertion** đã được dùng để chứng minh danh tính trước đây chưa? |
| **Phiên ứng dụng** | Session cookie/`SecurityContext` của SP. | Người dùng đã có phiên trong ứng dụng chưa và phiên còn hợp lệ không? |

Điểm quan trọng: **Response ID khác Assertion ID**, và một assertion có thể được bao trong nhiều thông điệp `Response` hoặc đi qua profile/binding khác. Vì vậy đánh dấu **chỉ Response ID** không đủ thay thế đánh dấu **assertion ID**. Cache `AuthnRequest` cũng không phải cache assertion đã dùng.

## 2. Nghĩa vụ từ đặc tả và các ranh giới của bảo vệ

OASIS **Profiles for the OASIS Security Assertion Markup Language (SAML) V2.0**, phần **Web Browser SSO HTTP-POST-specific processing rules (§4.1.4.5)**, yêu cầu SP chống phát lại **bearer assertions** bằng cách duy trì tập các **ID đã dùng** trong thời gian assertion còn được coi là hợp lệ dựa trên `SubjectConfirmationData@NotOnOrAfter`.

Điều này cho thấy hai đặc tính không thể bỏ qua:

- **Định danh:** dựa trên **assertion ID** đã được phát hành, sau khi xác minh assertion thuộc issuer đáng tin.
- **Thời gian lưu:** ít nhất bao phủ **toàn bộ khoảng còn có thể chấp nhận** assertion đó (bao gồm dung sai đồng hồ theo cấu hình validator).

Với những binding/profile khác, phải áp dụng quy tắc tương ứng, nhưng dùng một bộ chống replay thống nhất cho các assertion được phép tạo phiên đăng nhập vẫn là thiết kế phòng vệ hữu ích.

### 2.1. `<OneTimeUse>` có thay thế cache không?

SAML Core định nghĩa `<saml:OneTimeUse/>` là một condition cho biết assertion chỉ nên được sử dụng một lần. Tuy nhiên:

- `OneTimeUse` **không phải database**; nó không thể tự nhớ lần sử dụng đã diễn ra trên node A.
- IdP có thể **không đưa `OneTimeUse`** trong mọi assertion. Điều đó không loại bỏ nghĩa vụ bảo vệ bearer replay theo Web SSO HTTP-POST profile.
- Nếu assertion chứa `OneTimeUse`, SP phải xử lý theo condition đó qua validator/cơ chế lưu dấu thích hợp, không bỏ qua chỉ vì các condition khác đạt.
- Validator conditions theo thư viện/phiên bản có thể chưa được nối với **shared replay store** bạn mong muốn; phải kiểm tra thực tế, không suy đoán rằng có `OneTimeUse` thì mặc định an toàn nhiều node.

**Phân biệt:** chính sách **one-time consumption của bearer assertion** trong SP là cơ chế bảo vệ vận hành; `OneTimeUse` là một biểu thức điều kiện trong assertion được ký. Hai khái niệm liên quan nhưng không đồng nhất.

### 2.2. Điều gì chưa được giải quyết chỉ bằng replay cache?

Một assertion **chưa từng xuất hiện trong cache** vẫn có thể không hợp lệ vì chữ ký giả, issuer lạ, recipient sai, audience dành SP khác, chưa tới `NotBefore`, đã qua `NotOnOrAfter`, sai `InResponseTo` hoặc subject confirmation không đúng. Mặt khác, một response có chữ ký và nội dung hợp lệ **vẫn phải bị từ chối** nếu assertion ID đã tiêu thụ.

Do đó, replay cache là **điều kiện bổ sung**; không phải cơ chế để bỏ kiểm tra XML Signature, SAML Conditions hay phiên trình duyệt.

## 3. Nhận diện assertion nào đã dùng

Một SAML assertion có `ID` riêng, ví dụ:

~~~xml
<saml:Assertion
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="_assertion-7"
    Version="2.0"
    IssueInstant="2026-11-07T03:00:00Z">
  <saml:Issuer>urn:example:idp:corporate</saml:Issuer>
  <saml:Conditions
      NotBefore="2026-11-07T03:00:00Z"
      NotOnOrAfter="2026-11-07T03:06:00Z">
    <saml:AudienceRestriction>
      <saml:Audience>urn:example:sp:reports</saml:Audience>
    </saml:AudienceRestriction>
  </saml:Conditions>
  <saml:Subject>
    <saml:SubjectConfirmation
        Method="urn:oasis:names:tc:SAML:2.0:cm:bearer">
      <saml:SubjectConfirmationData
          Recipient="https://sp.example.org/login/saml2/sso/corporate"
          InResponseTo="_request-123"
          NotOnOrAfter="2026-11-07T03:05:00Z"/>
    </saml:SubjectConfirmation>
  </saml:Subject>
</saml:Assertion>
~~~

Đây là **XML rút gọn minh họa vị trí ID và timestamp**, chưa có chữ ký, status và các dữ kiện xác thực đầy đủ nên **không dùng làm assertion đăng nhập thật**.

### 3.1. Khóa replay nên chứa gì?

Một khóa ổn định có thể được tạo từ:

~~~text
replay:v1:<spEntityId-or-application-namespace>:
          SHA-256(<trustedIssuer> || separator || <assertionId>)
~~~

Các thành phần:

- **`assertionId`**: lấy từ đối tượng assertion **đã được xác minh nguồn gốc/chữ ký phù hợp**, không tự tạo ID từ request mới.
- **`trustedIssuer`**: định danh IdP đã được kiểm chứng từ `RelyingPartyRegistration`/validator. Đảm bảo không thể để attacker tùy ý chọn namespace.
- **Namespace SP/ứng dụng**: phân lập các ứng dụng, môi trường và use case có trust boundary riêng. **Mọi node cùng SP** phải dùng **cùng quy tắc key**, không chèn hostname/pod ID của từng node.
- **Prefix/version**: để nâng cấp định dạng khóa, kiểm soát vận hành và loại marker khác nhau.

Hash cho khóa giúp tránh lưu thẳng ID có ký tự lạ/độ dài không mong đợi vào key, và giúp tên key đồng nhất. **SHA-256 ở đây phục vụ định dạng khóa, không phải bằng chứng xác thực.** Không dùng NameID/email làm replay key: cùng người dùng có thể đăng nhập nhiều lần hợp lệ với assertion ID khác; ngược lại, attacker có thể dùng lại assertion mà không thay NameID.

Một số kiến trúc còn đánh dấu `Response@ID` ở namespace riêng để bảo vệ bổ sung. **Assertion ID vẫn là khóa chính** cho chống phát lại bearer assertion. Nếu một SAMLResponse chứa nhiều assertion được dùng để thiết lập cùng một identity context, phải xác minh từng assertion và bảo đảm không có assertion đã dùng nào được chấp nhận; thiết kế atomic all-or-nothing khi nhiều marker là cần thiết, thay vì chấp nhận một phần.

### 3.2. Định danh lấy từ dữ liệu đã kiểm chứng

Tránh cho attacker làm đầy Redis bằng hàng triệu ID tự khai: trước khi ghi marker, phải giới hạn kích thước request, parse XML an toàn, chọn registration đáng tin, xác minh signature/issuer/recipient/audience/conditions và chính sách giao dịch. Chỉ **assertion đã vượt qua xác minh cần thiết** mới đủ điều kiện tham gia bước đánh dấu đã dùng.

Chú ý các tình huống chữ ký Response và chữ ký Assertion theo binding/profile. Khi Response được ký nhưng assertion không được ký độc lập trong một profile được hỗ trợ, mã phải bảo đảm assertion đem dùng **chính là nội dung được chữ ký Response bảo vệ**, chống XML Signature Wrapping. Không chọn `Assertion@ID` từ XPath chưa tin cậy rồi dùng một assertion khác để tạo principal.

## 4. Pipeline xác minh an toàn với replay gate

Sơ đồ xử lý cho một **SAMLResponse tại ACS** trong ứng dụng Spring Security:

~~~text
Browser POST /login/saml2/sso/{registrationId}
        |
        v
Saml2WebSsoAuthenticationFilter
        |
Saml2AuthenticationTokenConverter
        |  tìm RelyingPartyRegistration, request gốc
        v
AuthenticationManager / OpenSAML provider
        |
        +--> Parse / decrypt theo profile
        +--> Signature và trust anchor đúng
        +--> Issuer, status, destination/recipient
        +--> Audience, Conditions, bearer confirmation
        +--> InResponseTo / session, policy unsolicited SSO
        |
        v
Replay gate (cùng một trust decision)
        |  key = namespace + issuer + assertion ID
        |  INSERT-IF-ABSENT (atomic, shared)
        |
        +-- Đã tồn tại ----------> REJECT (không tạo Authentication)
        +-- Store không sẵn sàng -> FAIL CLOSED
        +-- Insert thành công ---> tiếp tục
                                   |
                                   v
                         Saml2Authentication
                                   |
                             SecurityContext / SP session
~~~

Sơ đồ diễn tả **yêu cầu bảo mật**, không phải thứ tự chính xác của mọi bước nội bộ OpenSAML. Khi tùy biến provider, phải chọn extension point mà trước **khi phát `Authentication` thành công** đã có đủ dữ liệu đáng tin để đánh dấu atomic. Không tự chạy một servlet filter lấy ID từ XML chưa xác minh, rồi tin rằng cache đã an toàn.

### 4.1. Vị trí ghi marker và xử lý lỗi

- **Không chỉ `GET key` rồi `SET key`**: hai node có thể cùng đọc “chưa dùng” và cùng chấp nhận.
- **Không đánh dấu bằng thao tác không nguyên tử**: bảo vệ replay cần một thao tác **insert-if-absent** mà chỉ một node thắng.
- **Không xóa marker chỉ vì login thất bại ở bước sau**: một assertion đã được xử lý không nên trở lại trạng thái chưa dùng. Nếu phần kiểm tra nghiệp vụ thất bại sau khi marker được ghi, yêu cầu người dùng bắt đầu SSO mới.
- **Nếu store trả lỗi/timeout**, không tự coi assertion là mới; hành vi an toàn mặc định là **từ chối tạm thời** và cho người dùng khởi tạo login lại.
- **Nếu marker đã có**, phải từ chối trước khi cấp session mới, kể cả signature/audience/thời hạn vẫn đúng.
- **Nếu authentication bị hủy trước khi chạm replay gate**, không phải phát marker để “đánh dấu” XML chưa xác minh.

Ở hệ thống lớn, cần xác định thời điểm tiêu thụ so với các bước custom mapping/provisioning. Một phương án dễ an toàn là **xác minh SAML → tiêu thụ assertion atomic → xử lý ứng dụng**, không rollback marker chỉ vì bước provision hoặc lưu session lỗi.

## 5. Tính TTL: lưu marker đến khi nào?

Cửa sổ có thể dùng assertion bị giới hạn bởi nhiều timestamp:

1. `Conditions@NotBefore`: sớm nhất được chấp nhận.
2. `Conditions@NotOnOrAfter`: mốc hết hạn assertion (biên phải loại trừ).
3. `SubjectConfirmationData@NotOnOrAfter`: hạn bearer confirmation, quan trọng trực tiếp cho Web SSO.
4. Dung sai đồng hồ (**clock skew**) được validator cho phép.
5. Giới hạn riêng của SP về độ mới và thời gian thực hiện SSO; nếu cần giới hạn bảo mật rõ hơn, khai báo bằng chính sách.
6. Nếu có nhiều subject confirmation hợp lệ hoặc profile cho phép lựa chọn xác nhận khác nhau, phải xác định **mốc muộn nhất mà cùng assertion vẫn có thể được bất kỳ đường xác minh được phép nào chấp nhận**.

**Quy tắc an toàn:** marker **không được hết hạn trước thời điểm cuối cùng SP còn có thể chấp nhận chính assertion đó**, sau khi áp dụng đúng skew và mọi nhánh xác minh được cấu hình. Có thể thêm một biên an toàn nhỏ để bao phủ lệch đồng hồ giữa các node, lịch dọn cache và độ trễ xử lý.

Ví dụ các timestamp (UTC):

| Điều kiện | Giá trị |
| --- | --- |
| `IssueInstant` | `10:00:00Z` |
| `Conditions@NotOnOrAfter` | `10:06:00Z` |
| Bearer `SubjectConfirmationData@NotOnOrAfter` | `10:05:00Z` |
| Skew tương thích đã cấu hình | 30 giây |
| SP chấp nhận assertion qua đúng bearer confirmation này đến | Trước khoảng `10:05:30Z`, nếu không có ràng buộc chặt hơn |

Nếu assertion được chấp nhận tại `10:02:00Z`, **không đặt replay TTL = 30 giây**; assertion có thể còn hợp lệ nhiều phút. Với ví dụ này, giữ marker ít nhất qua **`10:05:30Z`** và một biên an toàn vận hành. TTL ở thời điểm ghi phải là khoảng còn lại tính tới mốc đó, không phải luôn dùng `NotOnOrAfter - IssueInstant`.

Giả sử chính sách bảo vệ và nguồn thời gian đã kiểm chứng tính ra `retentionUntil=10:05:45Z`; lúc `10:02:00Z`, TTL sẽ là **225 giây**. Lưu ý đây là **ví dụ số học cho một trường hợp**, không có một công thức “min hai hạn” đúng cho mọi assertion có nhiều confirmation/profile. Phần tính TTL phải bám **cùng chính sách acceptance** của validator; khi profile không cung cấp hạn có thể xác định an toàn, SP nên từ chối hoặc áp dụng giới hạn độ mới bắt buộc trước khi chấp nhận.

### 5.1. Tại sao TTL quá ngắn nguy hiểm?

Nếu ID marker hết hạn ở Redis lúc `10:03Z` nhưng SP còn có thể chấp nhận assertion đến `10:05Z`, replay lúc `10:04Z` sẽ trở thành “chưa từng thấy”. Ngược lại, TTL dài hơn một chút chỉ tốn thêm bộ nhớ; TTL quá ngắn **phá trực tiếp cơ chế bảo vệ**.

Không lấy thời hạn của **HTTP session cookie** hoặc **SAML `SessionNotOnOrAfter`** để thay TTL của assertion: chúng mô tả vòng đời phiên ứng dụng/phiên IdP, không nhất thiết là cửa sổ bearer assertion có thể trình tại ACS.

### 5.2. Cần có cận trên

Nếu IdP gửi assertion không có giới hạn thời gian phù hợp profile, hoặc SP cho skew quá lớn, cache có thể phải giữ ID vô thời hạn. Thiết kế đúng là **đặt chính sách từ chối assertion thiếu hạn hợp lệ/không đảm bảo thời hạn tối đa**, không chỉ giới hạn TTL cache tùy ý rồi vô tình cho replay sau khi marker biến mất.

Đảm bảo đồng hồ các node được đồng bộ. Dùng `Instant` thay vì local time strings, tính thời hạn từ dữ liệu đã xác minh; TTL cần dương và có giới hạn theo chính sách. Thời gian hết hạn trong Redis chạy độc lập với đồng hồ ứng dụng nhưng việc tính `PX` từ timestamp vẫn phụ thuộc clock của node: đo skew và dùng một nguồn thời gian thống nhất.

## 6. Store dùng chung: những đặc tính bắt buộc

Khi SP có hai hay nhiều replica/pod/VM:

~~~text
                Load Balancer
                      |
           +----------+----------+
           |                     |
        SP Node A             SP Node B
       Validator A           Validator B
           |                     |
           +----------+----------+
                      |
             SHARED REPLAY STORE
        atomic insert-if-absent + TTL
                      |
                một kết quả
            winner: accept marker
            loser: replay detected
~~~

**Điều kiện tối thiểu** của shared replay store:

| Thuộc tính | Vì sao bắt buộc |
| --- | --- |
| **Một không gian khóa** cho cùng SP/issuer | Mọi node phải hỏi cùng nơi; không chia cache theo hostname/pod ID. |
| **Atomic check-and-set** | Hai callback đồng thời chỉ một được xem là lần đầu. |
| **TTL phù hợp cửa sổ chấp nhận** | Không xóa dấu khi assertion còn dùng được. |
| **Read/write consistency đủ mạnh** | Node B phải thấy marker node A đã ghi trước khi B quyết định chấp nhận. |
| **Fail closed** | Store lỗi không biến thành “cache miss” hoặc “lần đầu”. |
| **Capacity và eviction phù hợp** | Marker không tự mất vì RAM thiếu trước khi TTL hết. |
| **Hỗ trợ thay đổi node/failover** | Scale-out, deploy rolling, pod restart không xóa toàn bộ replay history. |
| **Bảo mật kết nối và phân quyền** | TLS, ACL, secret rotation, không cho tác nhân khác xóa marker. |
| **Quan sát/audit** | Phân biệt replay thật, callback trùng do reload, clock skew, cache outage. |

**Sticky session không đủ**: có thể giảm lỗi correlation nhưng không bảo đảm một assertion sẽ luôn quay về một node. Khi load balancer failover, rolling deployment hoặc cố tình gửi request song song, một assertion vẫn có thể tới node khác.

### 6.1. So sánh các lựa chọn

| Giải pháp | Ưu điểm | Rủi ro/giới hạn | Khuyến nghị |
| --- | --- | --- | --- |
| `ConcurrentHashMap`/Caffeine trên mỗi node | Nhanh, đơn giản, TTL tùy cấu hình. | **Chỉ cục bộ**, node A/B không chia marker. Restart mất dấu. | Chỉ cho demo/một node với giả định hạn chế; không đủ cho cluster. |
| Sticky sessions | Hỗ trợ lưu `AuthnRequest` theo node. | Không ngăn replay tới node khác và không bền khi thay node. | Chỉ hỗ trợ routing, không thay replay store. |
| Redis dùng chung, `SET key value NX PX ttl` | Atomic trên một key, TTL tự động, latency thấp. | Replication/failover/eviction/durability phải thiết kế riêng. | Phù hợp thực tế khi đáp ứng đầy đủ điều kiện HA và failure policy. |
| SQL có **unique constraint** và bảng expiry | Ghi trùng được DB ngăn, có transaction/durability và audit. | Tăng tải DB, cần cleanup và tối ưu chỉ mục. | Đáng cân nhắc khi yêu cầu chặt về nhất quán/durability cao. |
| Distributed map/cache có `putIfAbsent` tuyến tính | Có thể có API phù hợp, TTL. | Phải kiểm chứng semantics của sản phẩm khi partition/failover. | Chỉ chấp nhận nếu thực sự có bảo đảm nguyên tử, không chỉ eventual consistency. |
| Bloom filter | Ít RAM khi lưu ID. | Có false positive và có thể thiếu khả năng xóa/TTL chính xác; cơ chế đồng bộ phức tạp. | Không nên dùng làm điểm quyết định cho phép đăng nhập nếu không có exact store. |

Redis được nhắc nhiều vì hỗ trợ `SET ... NX EX/PX`, **không có nghĩa mọi triển khai Redis HA tự động có tính tuyến tính hoặc bền khi failover**. Nếu security requirement không chấp nhận mất một marker đã xác nhận ghi, phải đánh giá cơ chế durability/consensus/transaction tương ứng; nếu không đạt, thiết kế kiểm soát rủi ro và fail-safe rõ ràng.

## 7. Redis: thao tác nguyên tử đúng và sai

### 7.1. Lệnh đúng

~~~redis
SET saml:replay:v1:reports:80b4a7f... used NX PX 240000
~~~

Mô hình:

- `NX`: chỉ tạo key **nếu chưa tồn tại**.
- `PX 240000`: TTL **240.000 ms = 4 phút**, chỉ là ví dụ; TTL thực tế phải tính từ cửa sổ còn chấp nhận assertion.
- Giá trị `used` chỉ là marker; có thể lưu thời điểm/metadata tối thiểu nếu cần audit, nhưng tránh PII.
- Nếu Redis trả **`OK`**, node vừa ghi marker lần đầu và có thể cho phép tiến trình đăng nhập tiếp tục (sau các điều kiện xác thực khác).
- Nếu Redis trả **nil/null** do key đã tồn tại, đó là replay/duplicate: **từ chối**.
- Nếu kết nối timeout/Redis trả lỗi, đó là **UNKNOWN**: **không cho qua**.

Lưu ý: cùng một key luôn được dùng cho cùng tuple issuer + assertion ID + namespace SP. Redis triển khai atomic cho **một lệnh trên một key**; đừng chia thành `GET` và `SET` riêng.

### 7.2. Race condition của cách làm sai

~~~text
Node A: GET key  -> nil
Node B: GET key  -> nil
Node A: SET key  -> OK
Node B: SET key  -> OK
Node A: ACCEPT
Node B: ACCEPT

Cả hai đã cấp phiên cho cùng assertion.
~~~

Ngay cả việc gọi `SETNX` rồi `EXPIRE` trong **hai lệnh riêng** cũng không tối ưu: nếu node chết giữa hai lệnh, marker có thể không có TTL, phình kho dữ liệu. `SET key value NX PX ttl` gộp điều kiện tạo và hạn sống trong một thao tác.

### 7.3. Đừng coi replay marker là khóa cần “unlock”

Marker `used` thể hiện một sự kiện **đã tiêu thụ**, không phải distributed lock đang giữ tài nguyên để xử lý tạm thời. Vì thế sau login thành công **không `DEL key`**. Sau lỗi ở bước tạo phiên cũng thường **không DEL** để cho assertion dùng lại: cách đó mở khả năng replay trong những cửa sổ xử lý thất bại không chắc chắn.

Nếu yêu cầu trải qua nhiều bước và cần trạng thái `PENDING`/`CONSUMED`, hãy định nghĩa protocol chuyển trạng thái atomic, recovery và timeout rõ ràng. **Không áp dụng hướng dẫn “unlock bằng DEL” của distributed lock một cách máy móc cho replay marker**.

### 7.4. Các điều kiện Redis cần xem xét

- **Eviction policy:** `allkeys-lru`, `allkeys-lfu` hoặc `volatile-ttl` có thể xóa marker trước TTL khi thiếu RAM. Điều này làm replay có thể qua. Dùng chính sách/capacity bảo đảm marker không bị đẩy sớm; khi hết RAM cần **báo lỗi và fail closed**, không âm thầm tiếp tục.
- **Failover:** Redis replica thường sao chép bất đồng bộ; một lần `SET NX` đã được primary báo `OK` có thể chưa tới replica trước khi primary lỗi. Sau failover, marker bị mất có thể cho cùng assertion được chấp nhận lại. `WAIT`/AOF giảm một phần rủi ro tùy cấu hình nhưng **không mặc nhiên biến mọi failover thành xác nhận bền/tuyến tính**.
- **Replication read:** không tra “key có tồn tại?” qua replica trễ rồi ra quyết định. Dùng thao tác conditional write trên điểm sở hữu nhất quán của key.
- **Partition:** khi mất kết nối tới shared store, reject callback thay vì tạo cache local rồi ghép sau.
- **ACL/TLS:** chỉ service SAML được quyền ghi/đọc marker theo namespace; không cho ứng dụng khác xóa hoặc reset replay data.
- **Deployment:** cùng environment, cùng SP, cùng namespace xuyên qua rolling update; không xóa marker chỉ vì deploy phiên bản mới.

## 8. Java 17: mô phỏng hai node cùng dùng bộ dấu phát lại

Đoạn chương trình sau dùng **Java 17 thuần**, mô phỏng hai node đi qua cùng một bộ lưu dấu có thao tác nguyên tử. Nó giúp hiểu race và khóa định danh, **không triển khai SAML thật, không có Redis, không có TTL eviction và không xác minh chữ ký**. Trong hệ thống production, thay `ConcurrentHashMap` bằng shared store thực và thực hiện toàn bộ SAML validation trước khi gọi `markFirstUse`.

Tệp **`ReplayGuardDemo.java`**:

~~~java
import java.time.Instant;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicInteger;

public class ReplayGuardDemo {
    static class SharedStore {
        // Shared giữa các node mô phỏng trong cùng JVM.
        private final Set<String> used = ConcurrentHashMap.newKeySet();

        boolean markFirstUse(String trustedIssuer, String assertionId) {
            return used.add(trustedIssuer + "|" + assertionId);
        }
    }

    static class Node {
        private final SharedStore store;

        Node(SharedStore store) {
            this.store = store;
        }

        boolean accept(String issuer, String id,
                       Instant now, Instant validUntil) {
            // Minh họa một điều kiện thời gian, không phải SAML validator.
            if (!now.isBefore(validUntil)) {
                return false;
            }
            return store.markFirstUse(issuer, id);
        }
    }

    public static void main(String[] args) throws InterruptedException {
        SharedStore shared = new SharedStore();
        Node nodeA = new Node(shared);
        Node nodeB = new Node(shared);

        Instant now = Instant.parse("2026-11-07T03:00:00Z");
        Instant expires = now.plusSeconds(300);

        System.out.println(nodeA.accept(
                "trusted-idp", "_assertion-1", now, expires));
        System.out.println(nodeB.accept(
                "trusted-idp", "_assertion-1", now, expires));
        System.out.println(nodeB.accept(
                "another-idp", "_assertion-1", now, expires));
        System.out.println(nodeA.accept(
                "trusted-idp", "_expired",
                now.plusSeconds(301), expires));

        CountDownLatch start = new CountDownLatch(1);
        CountDownLatch done = new CountDownLatch(2);
        AtomicInteger successes = new AtomicInteger();

        Runnable attempt = () -> {
            try {
                start.await();
                if (nodeA.accept(
                        "trusted-idp", "_racing", now, expires)) {
                    successes.incrementAndGet();
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            } finally {
                done.countDown();
            }
        };

        new Thread(attempt).start();
        new Thread(() -> {
            try {
                start.await();
                if (nodeB.accept(
                        "trusted-idp", "_racing", now, expires)) {
                    successes.incrementAndGet();
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            } finally {
                done.countDown();
            }
        }).start();

        start.countDown();
        done.await();
        System.out.println(successes.get());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac ReplayGuardDemo.java
java ReplayGuardDemo
~~~

**Kết quả chính xác:**

~~~text
true
false
true
false
1
~~~

Ý nghĩa:

1. Node A là bên đầu tiên đánh dấu `_assertion-1`, nên kết quả `true`.
2. Node B sử dụng cùng issuer + assertion ID nên nhận `false`.
3. Assertion ID trùng nhưng **issuer đã được xác minh khác** tạo namespace khác, nên có thể được chấp nhận về mặt chống replay (các kiểm tra tin cậy khác vẫn bắt buộc).
4. Assertion đã quá hạn bị từ chối, không được đánh dấu như một login mới.
5. Hai thread cùng chạy thử `_racing`; nhờ thao tác atomic trên **cùng SharedStore**, chính xác **một** thread thắng; thứ tự thắng không xác định nhưng `successes.get()` luôn là 1.

Demo cố ý không có cơ chế dọn marker và chỉ đúng cho **một JVM**; không được dùng `ConcurrentHashMap.newKeySet()` làm replay cache cho cluster hoặc coi thời gian trong demo là toàn bộ điều kiện SAML. Một ứng dụng thực phải tính `validUntil` từ các conditions/subject confirmations đã được thư viện xác minh.

## 9. Tích hợp Spring Security SAML 2.0 an toàn

Trong Servlet stack, callback SAML đi qua `Saml2WebSsoAuthenticationFilter`, converter và `AuthenticationManager` đến OpenSAML provider. Đường dẫn thường gặp là:

~~~text
POST /login/saml2/sso/{registrationId}
    -> Saml2WebSsoAuthenticationFilter
    -> Saml2AuthenticationTokenConverter
    -> Saml2AuthenticationToken
    -> OpenSAML authentication provider
    -> Saml2Authentication (nếu thành công)
~~~

Spring Security có thể sử dụng **`OpenSaml4AuthenticationProvider`** hoặc **`OpenSaml5AuthenticationProvider`** tùy phiên bản. Tài liệu mới cho thấy `OpenSaml5AuthenticationProvider.AssertionValidator` có khả năng thêm condition validator, ví dụ OpenSAML **`OneTimeUseConditionValidator`**. Nhưng **chưa thể kết luận rằng mọi cấu hình SAML login của ứng dụng đã có một cache assertion-used phân tán**. Phải khảo sát cấu hình validator, replay-store được nối vào đâu và hành vi dưới tải đồng thời.

### 9.1. Cấu hình cơ bản không thay cho replay gate

Ví dụ `SecurityFilterChain` trong một dự án Spring Boot có dependency SAML service provider:

~~~java
package example.federation;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SamlSecurityConfig {
    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/**", "/error").permitAll()
                .anyRequest().authenticated())
            .saml2Login(Customizer.withDefaults());
        return http.build();
    }
}
~~~

Đây là **đoạn cấu hình thuộc dự án Spring Boot**, không phải class có thể biên dịch/chạy chỉ với JDK. Ngoài dependency `spring-security-saml2-service-provider`, cần IdP metadata/trust credentials, SP entityID và ACS công khai chính xác. Đoạn mã khởi động SAML login **không chứng minh** rằng replay gate dùng Redis đã được cấu hình; cần một bước kiểm chứng triển khai riêng.

### 9.2. Chọn extension point đúng

Các nhóm phương án tùy biến trong hệ thống thực:

| Nhu cầu | Điểm mở rộng | Điều bắt buộc |
| --- | --- | --- |
| Dùng `OneTimeUse` hoặc điều kiện assertion mở rộng | Assertion validator/condition validator của OpenSAML provider theo phiên bản. | **Giữ default validators** và bổ sung condition handler, không vô hiệu hóa audience, subject confirmation, thời gian. |
| Từ chối replay mọi bearer assertion Web SSO | Replay-check component được gọi **sau xác minh dữ liệu SAML** và **trước khi công nhận Authentication**. | Key từ issuer + assertion ID đáng tin, thao tác atomic với shared store. |
| Phối hợp nhiều node | Redis/SQL shared replay repository. | TTL, retry policy, fail-closed, consistency, capacity. |
| Giữ yêu cầu login gốc | `Saml2AuthenticationRequestRepository`, thường gắn `HttpSession`. | Tương quan `InResponseTo` và browser session; không xem là replay cache dùng chung. |
| Map attributes và quyền | Response authentication converter hoặc business service sau khi verified. | Không cấp quyền từ assertion chưa qua replay gate và các validator. |

**Không ghi marker trong filter tùy ý trước khi xác minh chữ ký**: attacker có thể spam ID tùy chọn, gây đầy kho dữ liệu hoặc “preempt” một ID. **Không chèn replay logic vào success handler rồi giả định an toàn** nếu trước đó Authentication/session đã được công bố hoặc callback đồng thời đều vượt qua validator; phải bảo đảm gate là điều kiện tiên quyết có tính nguyên tử để cấp phiên.

### 9.3. Pseudocode tích hợp với Redis

Đây là **pseudocode kiến trúc**, không phải API Spring Security/OpenSAML có thể copy và chạy trực tiếp:

~~~text
verifySaml(response, trustedRegistration, pendingRequest)
    -> verifiedAssertions, verifiedIssuer, acceptanceWindows

for every bearer assertion used for login:
    derive key from SP namespace, verifiedIssuer, verifiedAssertionId
    derive retentionUntil from last possible acceptance time + safety margin
    require redis SET key "used" NX PX remainingMillis == OK

if all security checks and all needed replay reservations succeeded:
    create Saml2Authentication
else:
    throw AuthenticationException
~~~

Nếu phải đánh dấu **nhiều assertion trong cùng một Response**, vòng lặp `SET NX` độc lập có thể tạo trạng thái nửa chừng khi một marker đã tồn tại. Về bảo mật, không được cấp session trong trường hợp nửa chừng đó; về vận hành, nên có một giao thức dự trữ atomic all-or-nothing (ví dụ transaction/compare-and-set ở store hỗ trợ) hoặc chỉ chấp nhận cấu trúc SAML mà mọi assertion sử dụng có thể được bảo vệ nhất quán. Với Redis Cluster, atomic multi-key Lua/transaction đòi các key nằm trong cùng hash slot; không mặc định nhiều key phân tán có cùng tính nguyên tử như một `SET NX`.

## 10. Phân tích HA: khi dùng chung store vẫn có thể bị replay

Nhiều nhóm triển khai Redis vì “đã shared” nhưng bỏ sót rủi ro sau:

### 10.1. Hai node ghi đồng thời

Nếu cả hai dùng cùng một Redis primary/key và **`SET NX PX`**, một node thắng. Nếu mỗi node dùng cache local rồi ghi Redis bất đồng bộ, cả hai có thể cấp session trước khi nhận biết trùng. **Quyết định allow/deny phải dựa trên kết quả ghi marker atomic**, không dựa trên một event gửi background.

### 10.2. Redis primary lỗi ngay sau khi xác nhận ghi

Giả sử primary xác nhận `OK` cho assertion A rồi chết **trước khi replica nhận marker**. Replica được promote không có A; callback replay được xử lý trên primary mới, `NX` trả `OK` lần nữa. Về kỹ thuật, đây là **mất dấu đã tiêu thụ**, không phải do hai request không đồng thời.

Đánh giá yêu cầu bảo mật/durability và phương án: tính chất replication, AOF, xác nhận replica, chiến lược failover, hoặc chuyển tới datastore có bảo đảm transaction/consistency chặt hơn. **Không nói Redis mặc định “exactly-once qua mọi failover”**. Nếu không thể bảo đảm tuyệt đối, phải mô tả residual risk, kiểm soát timeout/TLL ngắn và khả năng tạm dừng SSO khi store không nhất quán.

### 10.3. Lỗi kết nối, timeout và kết quả không chắc chắn

Một `SET NX` có thể đã được Redis thực hiện nhưng response tới node bị mất. Lúc đó node **không biết** marker được tạo hay chưa. Hành vi an toàn: **không cấp phiên trên kết quả chưa chắc chắn**, báo lỗi có thể retry **bằng giao dịch đăng nhập mới**. Nếu retry cùng assertion, kể cả nó có thể đã được ghi, phải từ chối theo chính sách single-use; không “cho qua vì lần trước timeout”.

### 10.4. Cache eviction và deploy

Marker có TTL 5 phút không có nghĩa nó chắc chắn tồn tại 5 phút nếu chính sách eviction cho phép xóa sớm hoặc thao tác deploy xóa key namespace. Kiểm tra chính sách bộ nhớ, độ sẵn sàng, restart, persistence và rollout. Xóa toàn bộ cache giữa ca đăng nhập làm mở cửa phát lại các assertion chưa hết hạn.

### 10.5. Nhiều vùng địa lý

Nếu SP ở Region A và Region B dùng hai Redis độc lập rồi đồng bộ **eventually consistent**, assertion có thể được chấp nhận ở cả hai trong thời gian replication lag. Muốn bảo đảm chỉ một lần toàn hệ thống, cần **một điểm quyết định nguyên tử trên cùng key** hoặc kiến trúc nhất quán mạnh tương đương. Nếu không đáp ứng được SLA toàn cầu, phải ghi rõ giới hạn và thiết kế định tuyến an toàn thay vì gọi đó là “global replay prevention”.

## 11. Bảng kiểm và tình huống thử nghiệm

| Bài kiểm thử | Kết quả mong đợi |
| --- | --- |
| Một bearer assertion hợp lệ, lần nhận đầu tiên. | Được chấp nhận sau xác minh đầy đủ và ghi marker thành công. |
| Gửi lại chính assertion đó tới cùng node khi còn hạn. | Bị từ chối vì marker đã tồn tại. |
| Gửi lại chính assertion đó tới node khác ngay sau lần đầu. | Bị từ chối **trên shared store**. |
| Đồng thời POST cùng assertion tới hai node. | **Chỉ một** callback có thể qua replay gate; không cấp hai phiên. |
| Cùng `Response@ID` nhưng assertion đã thay đổi/chữ ký sai. | Bị từ chối bởi validator; response ID không thay xác minh XML. |
| Assertion ID giống nhau nhưng issuer đã xác minh khác. | Không bị collision theo key của issuer khác; các điều kiện tin cậy vẫn phải đạt. |
| Replay sau lúc marker TTL kết thúc nhưng assertion cũng đã hết cửa sổ hiệu lực. | Validator thời gian từ chối, không tạo login. |
| Marker bị xóa **trước** hạn còn có thể dùng assertion. | Đây là lỗi bảo mật cần phát hiện/cảnh báo; không chấp nhận cơ chế đó. |
| Redis trả lỗi hoặc timeout. | **Fail closed**, không mở cache local fallback. |
| Redis `NX` trả nil vì key tồn tại. | Bắt lỗi replay/duplicate, không tự retry và ghi đè marker. |
| Restart cả hai node Spring Security. | Marker vẫn tồn tại ở shared store; assertion cũ không được chấp nhận. |
| Failover Redis trước khi replica đồng bộ marker. | Kiểm thử khả năng mất marker/đặt yêu cầu durability; không tuyên bố an toàn nếu mất. |
| Một node lệch đồng hồ trong dung sai cấu hình. | TTL vẫn bao phủ cửa sổ xác thực tối đa, không xóa sớm. |
| Response chứa nhiều assertions sử dụng cho login. | Mỗi assertion có ID/validation riêng; không cho qua một phần nếu marker trùng. |
| `OneTimeUse` hiện diện và validator mặc định không xử lý điều kiện đó. | Phải có validator phù hợp; không bỏ qua condition không hiểu. |
| IdP-initiated SSO không có `InResponseTo`. | Áp dụng chính sách unsolicited riêng, replay gate vẫn bắt buộc. |
| Assertion hợp lệ nhưng user đã bị disable trong ứng dụng. | Không cấp quyền ứng dụng; marker đã tiêu thụ không được xóa để dùng lại. |

**Test concurrency** phải có load balancer thực, hai instance độc lập, hai HTTP request song song cùng một SAMLResponse có chữ ký hợp lệ và cùng shared store. Không chỉ unit test `ConcurrentHashMap` cục bộ rồi kết luận đã chứng minh an toàn cluster.

## 12. Quan sát và vận hành

Cần có log/metric để phân biệt **tấn công thật**, **người dùng nhấn F5**, **trình duyệt retry POST**, **lỗi session** và **sự cố store**:

| Metric / dấu vết | Ý nghĩa |
| --- | --- |
| `saml_replay_first_use_total` | Số marker tạo thành công. |
| `saml_replay_duplicate_total` | Số lần key tồn tại, bị từ chối. |
| `saml_replay_store_error_total` | Lỗi kết nối, timeout, capacity hoặc failover. |
| `saml_replay_gate_latency` | Độ trễ quyết định cho phép/từ chối. |
| `saml_replay_ttl_below_policy_total` | Tính TTL quá ngắn hoặc không thể xác định an toàn. |
| `saml_clock_skew_rejection_total` | Assertion bị từ chối vì thời gian/đồng hồ. |
| `saml_in_response_to_rejection_total` | Tương quan AuthnRequest/phiên không khớp. |

Các tên metric là **gợi ý thiết kế** không phải metrics mặc định Spring Security. Nếu đột ngột tăng duplicate, cần xem request từ một người dùng (double submit) hay từ nhiều IP/session; không vội gắn nhãn tấn công dựa trên một đếm đơn lẻ.

Ghi **issuer registration đã xác minh, ID hash ngắn dùng cho correlation, timestamp UTC, node, lý do từ chối và thời gian phản hồi store**. Không log nguyên `SAMLResponse`, assertion XML, NameID, cookie, khóa bí mật hoặc dữ liệu cá nhân. Dùng dashboard theo node/region và cảnh báo khi Redis memory tăng, eviction > 0 hoặc failover làm mất marker.

Capacity planning gần đúng: số marker đang sống phụ thuộc **tốc độ SSO × thời gian lưu trung bình** cộng overhead key/value và replication. Cần load test trong peak login, có đầu ra kiểm toán và kế hoạch khi store đầy: **deny new SSO tạm thời**, không bật fallback allow-all.

## 13. Các sai lầm phổ biến

| Cách làm sai | Hậu quả | Cách sửa |
| --- | --- | --- |
| Chỉ xác minh chữ ký/audience/thời hạn. | Assertion ký hợp lệ có thể dùng lại trong cửa sổ còn hiệu lực. | Thêm replay gate dựa trên assertion ID. |
| Chỉ cache `Response@ID`. | Assertion có thể được đóng gói lại trong Response khác. | Cache `Assertion@ID`, có thể bổ sung response ID riêng. |
| Dùng NameID/email làm key. | Chặn đăng nhập hợp lệ khác hoặc collision giữa người dùng. | Dùng verified issuer + assertion ID + SP namespace. |
| Chỉ dùng `HttpSession` của node. | Replay đến node khác có thể qua. | Shared store cho mọi instance. |
| Redis `GET` rồi `SET`. | Race condition, hai node cùng cho qua. | `SET key value NX PX ttl` nguyên tử. |
| `SETNX` và `EXPIRE` tách hai lệnh. | Có thể tạo marker không có TTL khi có lỗi giữa hai bước. | Gộp điều kiện tạo và TTL. |
| Chọn TTL cố định quá ngắn. | Marker hết hạn trong khi assertion vẫn có thể được chấp nhận. | TTL bám acceptance window và clock skew. |
| Xóa marker khi logout hoặc khi SP session hết hạn. | Cho assertion cũ dùng lại trước khi hết thời gian. | Marker sống độc lập theo thời hạn assertion. |
| Xóa marker khi success handler/provisioning lỗi. | Assertion đã tiêu thụ trở thành reusable. | Giữ marker và bắt đầu login mới khi cần. |
| Fail-open nếu Redis mất kết nối. | Bảo vệ replay biến mất đúng lúc hệ thống suy yếu. | Fail closed và báo lỗi thân thiện. |
| Redis có replication nên tự coi là exactly-once. | Failover có thể mất marker được primary ghi. | Đánh giá durability/consistency và residual risk. |
| Tự parse XML để lấy `Assertion@ID` trước khi xác minh chữ ký. | Bị gửi ID giả, gây DoS, sai assertion được kiểm chứng. | Chỉ dùng ID từ assertion được validator chấp nhận. |
| Tin rằng `OneTimeUse` đã tự lưu dấu. | Điều kiện có thể được đọc mà không có kho trạng thái cần thiết. | Kết nối validator với replay-store phù hợp. |
| Thay Spring default validators bằng validator chỉ kiểm tra cache. | Bỏ lỡ issuer, audience, recipient, thời hạn, chữ ký. | Kế thừa/giữ default validation và bổ sung gate. |

## 14. Tự kiểm tra hiểu biết

1. **Vì sao chữ ký hợp lệ không đủ ngăn replay?** — Vì cùng chữ ký có thể được gửi lại nguyên vẹn trước khi assertion hết hạn.
2. **SAML bearer assertion có ID hay chỉ SAML Response có ID?** — Mỗi assertion có **ID riêng**, phải theo dõi ID được dùng.
3. **Cần chia sẻ trạng thái nào qua các node?** — Replay marker của assertion; AuthnRequest/session còn cần cơ chế correlation phù hợp.
4. **Có thể dùng `ConcurrentHashMap` của từng pod thay Redis không?** — Không, nếu nhiều pod cùng xử lý SSO.
5. **Vì sao `GET` rồi `SET` không an toàn?** — Hai node có thể cùng thấy key trống rồi đều cho đăng nhập.
6. **`SET ... NX PX` trả null có nghĩa gì?** — Key đã tồn tại; không được chấp nhận lại.
7. **Cache lỗi thì cho login để tăng availability có ổn không?** — Không nếu bảo vệ replay là điều kiện bảo mật bắt buộc; cần **fail closed**.
8. **TTL có thể ngắn hơn `SubjectConfirmationData@NotOnOrAfter` không?** — Không, nếu SP còn có thể chấp nhận assertion khi marker biến mất; phải tính cả skew và các nhánh acceptance.
9. **Khi Redis primary failover mất ghi gần nhất, hai node còn bảo đảm exactly-once không?** — Không; phải đánh giá hoặc tăng cường durability/consistency.
10. **Nếu login thất bại sau khi marker đã được ghi, có nên `DEL` để người dùng thử lại cùng Response?** — Không; dùng giao dịch SSO mới.
11. **Có `OneTimeUse` trong XML thì đã an toàn cluster?** — Không, cần validator và shared used-ID state thực tế.
12. **Assertion đã hết hạn nhưng marker đã bị dọn: replay có qua không?** — Không nếu validator thời gian hoạt động đúng; đó là lý do replay gate và time validation luôn phải cùng áp dụng.

## 15. Tài liệu tham khảo

- [OASIS SAML V2.0 Profiles — §4.1.4.5, HTTP-POST replay prevention](https://docs.oasis-open.org/security/saml/v2.0/saml-profiles-2.0-os.pdf)
- [OASIS SAML V2.0 Core — Assertion ID, Conditions, OneTimeUse](https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf)
- [OASIS SAML V2.0 Errata 05 — bearer SubjectConfirmationData, InResponseTo](https://docs.oasis-open.org/security/saml/v2.0/errata05/os/saml-v2.0-errata05-os.html)
- [Spring Security — SAML 2.0 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html)
- [Spring Security — Authenticating SAML Responses, OpenSaml5 AssertionValidator và OneTimeUseConditionValidator](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html)
- [Spring Security — AuthnRequest và Saml2AuthenticationRequestRepository](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication-requests.html)
- [Redis SET — các tùy chọn NX, EX, PX và kết quả](https://redis.io/docs/latest/commands/set/)
- [Redis Persistence và cơ chế sao chép (tham khảo vận hành HA)](https://redis.io/docs/latest/operate/oss_and_stack/management/persistence/)
