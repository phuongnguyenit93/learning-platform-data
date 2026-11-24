# Certificate revocation — Thu hồi chứng chỉ số trong xác thực

> **Chương:** Certificate authentication  
> **Chủ đề:** Certificate revocation  
> **Phạm vi:** Bài học thuộc module SECURITY_AUTHENTICATION_FUNDAMENTALS, tìm hiểu xác thực danh tính qua credential, mật khẩu, MFA, passkey, chứng chỉ, token, phiên, liên kết danh tính và khôi phục tài khoản. Bài này tập trung vào cách một hệ thống PKI tuyên bố chứng chỉ không còn được tin cậy trước hoặc sau ngày hết hạn, cách verifier kiểm tra trạng thái thu hồi và tác động đến xác thực TLS/mTLS.

## 1. Certificate revocation là gì?

**Certificate revocation (thu hồi chứng chỉ)** là quá trình một Certificate Authority (CA) hoặc hệ thống PKI có thẩm quyền đánh dấu một chứng chỉ đã phát hành là **không còn được chấp nhận trước thời điểm hết hạn ghi trong chứng chỉ**. Verifier kiểm tra trạng thái thu hồi để quyết định có tiếp tục tin chứng chỉ trong một lần xác thực hay không.

Một chứng chỉ X.509 thường chứa public key, subject, issuer, serial number, thời hạn hiệu lực, mục đích sử dụng, các extension và chữ ký của CA. Chữ ký hợp lệ chỉ cho biết chứng chỉ được ký bởi issuer tương ứng và nội dung chưa bị sửa. Nó **không chứng minh chứng chỉ vẫn còn được phép sử dụng**. Khóa riêng có thể đã bị lộ, thiết bị có thể bị mất, nhân viên có thể rời tổ chức, hoặc CA có thể phát hiện lỗi trong quá trình cấp phát.

Ví dụ: một máy chủ nội bộ có chứng chỉ client dùng để xác thực mTLS với API. Máy chủ bị xâm nhập và khóa riêng có thể đã bị sao chép. Tổ chức yêu cầu CA thu hồi chứng chỉ đó. Từ thời điểm chính sách có hiệu lực, verifier phải từ chối chứng chỉ bị thu hồi, kể cả khi chữ ký và ngày hết hạn vẫn hợp lệ.

**Thu hồi khác hết hạn:**

- **Expiration:** chứng chỉ tự hết hiệu lực theo trường `NotAfter`; verifier từ chối sau thời điểm đó.
- **Revocation:** trạng thái được công bố hoặc truy vấn để báo chứng chỉ không còn được tin cậy trước khi hết hạn.
- **Suspension/hold:** một số hệ thống có trạng thái tạm giữ (ví dụ reason code certificateHold); chứng chỉ có thể được gỡ trạng thái hold theo quy tắc PKI, khác với thu hồi vĩnh viễn.
- **Reissuance:** cấp chứng chỉ mới không tự động thu hồi chứng chỉ cũ. Nếu khóa cũ có rủi ro, phải thu hồi rõ ràng và kiểm tra trạng thái.

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích vì sao chứng chỉ đã ký và còn hạn vẫn có thể phải bị từ chối.
2. Phân biệt expiration, revocation, suspension và certificate replacement.
3. Mô tả CRL, delta CRL, OCSP và OCSP stapling.
4. Thiết kế chính sách hard-fail/soft-fail theo rủi ro và loại dịch vụ.
5. Hiểu thời gian phát hiện, công bố, cache và phân phối trạng thái thu hồi.
6. Đánh giá ảnh hưởng của thu hồi đến TLS, mTLS, client authentication và hệ thống nội bộ.
7. Xây dựng quy trình xử lý khóa riêng bị lộ, thu hồi, cấp lại, giám sát và kiểm thử.

## 2. Vì sao PKI cần cơ chế thu hồi?

PKI tạo niềm tin bằng chuỗi chứng chỉ: verifier tin một trust anchor, kiểm tra các chứng chỉ trung gian và chứng chỉ cuối (leaf/end-entity) theo chính sách. Tuy nhiên, niềm tin có thể thay đổi trước khi chứng chỉ hết hạn.

Các tình huống thường cần thu hồi:

| Tình huống | Lý do thu hồi | Hành động tiếp theo |
| --- | --- | --- |
| Private key bị lộ hoặc nghi bị sao chép | Kẻ tấn công có thể ký hoặc xác thực như chủ sở hữu | Thu hồi nhanh, thay khóa, điều tra phạm vi ảnh hưởng. |
| Thiết bị/máy chủ bị mất hoặc thanh lý | Không còn kiểm soát được khóa và môi trường sử dụng | Thu hồi chứng chỉ thiết bị, cấp lại nếu thiết bị mới hợp lệ. |
| Nhân viên rời tổ chức hoặc đổi vai trò | Danh tính/ủy quyền gắn với chứng chỉ không còn phù hợp | Thu hồi chứng chỉ cá nhân hoặc thiết bị, gỡ quyền ở hệ thống liên quan. |
| Chứng chỉ cấp nhầm subject/SAN | Danh tính trong chứng chỉ không đúng hoặc vượt phạm vi | Thu hồi và cấp lại với danh tính đã xác minh. |
| CA phát hiện lỗi cấp phát hoặc xác minh | Chứng chỉ có thể không đáp ứng policy | Thu hồi theo quy trình CA, thông báo và thay thế. |
| Thuật toán/khóa không còn an toàn | Khả năng bảo vệ của credential không đạt yêu cầu | Thu hồi/chuyển đổi theo kế hoạch crypto-agility. |
| Dịch vụ hoặc workload bị decommission | Credential không còn cần thiết | Thu hồi, xóa khóa an toàn, cập nhật inventory. |
| Chứng chỉ trung gian hoặc CA bị xâm nhập | Có thể ảnh hưởng nhiều chứng chỉ trong chuỗi | Xử lý trust anchor/intermediate, cập nhật trust store và ứng phó diện rộng. |

Thu hồi là một phần của **vòng đời credential**. Nếu tổ chức chỉ phát hành và gia hạn chứng chỉ mà không có inventory, chủ sở hữu, quy trình báo mất khóa và kiểm tra trạng thái ở verifier, PKI có thể tiếp tục chấp nhận credential đã mất an toàn.

### Thu hồi chứng chỉ không đồng nghĩa xóa quyền ở mọi nơi

Một chứng chỉ có thể được dùng để xác thực vào nhiều dịch vụ. Thu hồi ở CA chỉ cung cấp tín hiệu trạng thái chứng chỉ; từng relying party phải thực sự kiểm tra và thực thi tín hiệu đó. Ngoài ra, nếu ứng dụng đã tạo session hoặc token sau lần xác thực trước đó, thu hồi chứng chỉ **không tự động hủy session/token đã cấp**. Cần chính sách thu hồi phiên, token và quyền độc lập.

## 3. Vị trí thu hồi trong quá trình kiểm tra chứng chỉ

Một verifier không nên chỉ kiểm tra chữ ký. Việc xác thực chứng chỉ thường bao gồm nhiều điều kiện:

1. Xây dựng và kiểm tra certification path tới trust anchor được cấu hình.
2. Kiểm tra chữ ký từng chứng chỉ, thời hạn `NotBefore/NotAfter`, Basic Constraints, Key Usage và Extended Key Usage.
3. Kiểm tra subject/SAN và ánh xạ danh tính theo mục đích sử dụng.
4. Kiểm tra thuật toán, kích thước khóa, chính sách CA và các ràng buộc của relying party.
5. Kiểm tra trạng thái thu hồi của chứng chỉ cần thiết theo policy.
6. Chỉ sau khi toàn bộ điều kiện đạt mới chấp nhận chứng chỉ để xác thực principal.

~~~mermaid
flowchart TD
    A["Nhận certificate chain"] --> B["Build path tới trust anchor"]
    B --> C{"Chữ ký và path hợp lệ?"}
    C -- "Không" --> X["Từ chối"]
    C -- "Có" --> D["Kiểm tra thời hạn, usage, identity"]
    D --> E{"Các điều kiện certificate đạt?"}
    E -- "Không" --> X
    E -- "Có" --> F["Kiểm tra revocation theo policy"]
    F --> G{"Trạng thái đáng tin và không bị thu hồi?"}
    G -- "Không / revoked" --> X
    G -- "Có" --> H["Xác thực certificate / principal"]
    H --> I["Authorization và tạo session/token theo policy"]
~~~

**Lưu ý:** không phải mọi certificate trong mọi path đều được xử lý thu hồi theo cùng cách trong mọi profile. Phạm vi kiểm tra phụ thuộc chuẩn, loại chứng chỉ, CA policy, trust anchor và ứng dụng. Verifier cần tuân thủ profile và policy đã chọn, không tự suy ra rằng chỉ kiểm tra leaf là luôn đủ hoặc luôn phải truy vấn mọi chứng chỉ trong chuỗi.

## 4. Certificate Revocation List (CRL)

**CRL** là danh sách do CA ký, liệt kê serial number của các chứng chỉ đã bị thu hồi cùng thông tin liên quan. Client/verifier tải CRL từ điểm phân phối được công bố trong chứng chỉ (thường qua CRL Distribution Points) hoặc từ nguồn tin cậy cấu hình sẵn.

CRL thường có:

- **Issuer:** CA phát hành CRL.
- **This Update:** thời điểm CRL hiện tại được phát hành.
- **Next Update:** thời điểm dự kiến phải có CRL mới.
- **Revoked Certificates:** serial number và ngày thu hồi; có thể kèm reason code và extension.
- **Signature:** chữ ký của CA/CRL issuer để verifier xác minh nguồn và tính toàn vẹn.
- **CRL Number:** số thứ tự giúp nhận biết phiên bản, phát hiện rollback theo policy.
- **Issuing Distribution Point:** có thể giới hạn phạm vi CRL (ví dụ loại chứng chỉ hoặc phân vùng).

### Cách verifier dùng CRL

1. Xác định CRL issuer phù hợp với chứng chỉ cần kiểm tra.
2. Lấy CRL từ nguồn được phép, kiểm tra chữ ký, issuer, phạm vi và thời gian.
3. Kiểm tra CRL có còn mới theo policy hay đã quá `NextUpdate`.
4. Tìm serial number của chứng chỉ trong danh sách.
5. Nếu có serial, áp dụng reason/status tương ứng và từ chối hoặc xử lý theo chính sách.
6. Nếu không có serial trong một CRL hợp lệ và đầy đủ phạm vi, verifier có thể coi chứng chỉ không bị liệt kê là revoked tại thời điểm trạng thái CRL đó được phát hành.

### Ưu điểm và giới hạn

| Ưu điểm | Giới hạn |
| --- | --- |
| Verifier có thể tải trước và kiểm tra offline trong thời gian CRL còn mới | CRL lớn khi CA cấp nhiều chứng chỉ và thu hồi nhiều lần. |
| Một lần tải có thể kiểm tra nhiều chứng chỉ cùng phạm vi | Trạng thái mới không đến verifier ngay lập tức; phụ thuộc lịch phát hành/phân phối. |
| Chữ ký CRL cho phép xác minh nguồn và tính toàn vẹn | CRL quá hạn hoặc không tải được cần chính sách xử lý rõ ràng. |
| Phù hợp môi trường mạng nội bộ/ít thay đổi hoặc cần cache | Có thể tăng băng thông, bộ nhớ và độ trễ cập nhật. |

### Delta CRL

**Delta CRL** chỉ chứa thay đổi kể từ một CRL cơ sở (base CRL), giúp giảm kích thước truyền khi CA có nhiều chứng chỉ và danh sách thu hồi lớn. Verifier cần ghép delta CRL với đúng base CRL, kiểm tra số CRL, issuer, phạm vi và thời hạn; không được dùng delta độc lập như một danh sách đầy đủ nếu profile yêu cầu base.

CRL partitioning hoặc indirect CRL cũng có thể được dùng trong PKI lớn. Những cơ chế này làm việc chọn đúng issuer/phạm vi quan trọng hơn; nếu verifier tải nhầm CRL hoặc bỏ sót phân vùng, kết quả “không thấy serial” không có nghĩa chứng chỉ hợp lệ.

## 5. Online Certificate Status Protocol (OCSP)

**OCSP** là giao thức cho phép verifier hỏi một responder về trạng thái của một chứng chỉ cụ thể thay vì tải toàn bộ CRL. Request thường xác định issuer và serial của chứng chỉ; response có trạng thái như:

- **good:** responder không ghi nhận chứng chỉ bị thu hồi trong phạm vi và thời điểm phản hồi. Không nên diễn giải rộng thành “chứng chỉ chắc chắn hợp lệ trong mọi khía cạnh”.
- **revoked:** chứng chỉ đã bị thu hồi; response có thể có thời điểm thu hồi và reason.
- **unknown:** responder không thể xác định trạng thái theo dữ liệu hiện có.

OCSP response cần được xác minh chữ ký và danh tính responder theo quy tắc PKI. Responder có thể được CA ủy quyền (delegated responder) và chứng chỉ responder phải có mục đích phù hợp. Không tin response chỉ vì nó đến từ một URL trông giống CA.

### OCSP request/response

~~~mermaid
sequenceDiagram
    participant V as Verifier
    participant O as OCSP Responder
    V->>O: OCSPRequest (issuer + serial)
    O->>O: Tra trạng thái certificate
    O-->>V: OCSPResponse (good/revoked/unknown)
    V->>V: Verify signature, responder, freshness
    V->>V: Apply hard-fail / soft-fail policy
~~~

Các trường thời gian quan trọng gồm:

- **producedAt:** khi responder tạo response.
- **thisUpdate:** thời điểm trạng thái được xác nhận.
- **nextUpdate:** thời điểm dự kiến có response mới, nếu có.
- **revocationTime:** thời điểm thu hồi trong response revoked.
- **nonce:** có thể dùng để ràng buộc request/response và giảm replay khi được hỗ trợ theo profile; việc dùng nonce có ảnh hưởng cache và khả năng triển khai.

Verifier cần kiểm tra freshness theo policy, xác minh response dành cho đúng certificate/issuer, không chấp nhận response cũ hoặc bị phát lại vượt quá thời gian cho phép. `good` là một tuyên bố trạng thái của responder, không thay thế kiểm tra path, validity, usage và identity.

### Ưu điểm và giới hạn

| Ưu điểm | Giới hạn |
| --- | --- |
| Tra cứu trạng thái một chứng chỉ, response thường nhỏ | Verifier phụ thuộc kết nối responder hoặc cache hợp lệ. |
| Có thể cập nhật nhanh hơn CRL nếu CA/responder phát hành kịp thời | Tạo lưu lượng truy vấn và tải cho responder. |
| Có trạng thái rõ ràng good/revoked/unknown | Lộ metadata về chứng chỉ/dịch vụ đang truy cập cho responder tùy kiến trúc. |
| Có thể cache response trong thời gian phù hợp | Cache cũ làm chậm nhận biết thu hồi; response mới có thể không sẵn có. |

## 6. OCSP stapling

**OCSP stapling** cho phép TLS server lấy OCSP response đã ký từ responder và gửi kèm trong handshake TLS, để client không cần tự truy vấn responder trong mỗi kết nối. Server đóng vai trò cung cấp response; client vẫn phải kiểm tra chữ ký, certificate status và freshness.

Luồng cơ bản:

1. TLS server lấy OCSP response cho chứng chỉ của mình từ responder.
2. Server cache response hợp lệ và làm mới trước khi hết hạn.
3. Khi handshake, server gửi response trong TLS CertificateStatus/OCSP stapling theo phiên bản TLS và profile hỗ trợ.
4. Client xác minh response, kiểm tra nó tương ứng với certificate đang được dùng và đánh giá freshness.
5. Nếu response revoked, client từ chối chứng chỉ. Nếu response thiếu/cũ/không hợp lệ, client áp dụng policy của mình.

### Lợi ích

- Giảm số lượng truy vấn trực tiếp từ client tới OCSP responder.
- Giảm độ trễ và tránh một số vấn đề riêng tư khi responder không nhìn thấy từng client truy cập.
- Cho phép server chuẩn bị response trước và phân phối qua TLS handshake.

### Giới hạn

- Server phải chủ động làm mới response; nếu stapled response hết hạn, client có thể từ chối hoặc xử lý theo policy.
- Không phải mọi client/server đều hỗ trợ giống nhau; phải kiểm tra hành vi thực tế.
- Stapling response không thay thế xác minh chữ ký, freshness, chain và các điều kiện certificate khác.
- **Must-Staple** (TLS Feature extension) có thể yêu cầu client chỉ chấp nhận khi server cung cấp status response phù hợp; cần hiểu hỗ trợ của client và profile trước khi triển khai.
- Stapling thường áp dụng cho chứng chỉ server TLS; không nên giả định nó giải quyết mọi trường hợp thu hồi client certificate trong mTLS.

## 7. So sánh CRL, OCSP và OCSP stapling

| Tiêu chí | CRL | OCSP | OCSP stapling |
| --- | --- | --- | --- |
| Cách lấy trạng thái | Tải danh sách serial đã thu hồi | Hỏi responder cho chứng chỉ cụ thể | Server gửi response OCSP đã lấy trước |
| Dữ liệu | Danh sách có thể lớn | Response theo certificate | Response theo certificate được staple |
| Tải mạng | Tải định kỳ, cache dùng cho nhiều cert | Có thể phát sinh truy vấn theo cert | Server làm mới; client không phải query trực tiếp |
| Freshness | Theo thisUpdate/nextUpdate và lịch CRL | Theo response timestamps | Theo OCSP response được server cache |
| Riêng tư | Tải danh sách có thể ít lộ từng cert đang dùng | Responder có thể thấy truy vấn cert | Giảm truy vấn trực tiếp của client |
| Khả năng offline | Có thể kiểm tra khi CRL còn mới | Cần response đã cache hoặc stapled | Client nhận response từ server trong handshake |
| Điểm vận hành | Kích thước, lịch phát hành, phân phối | Availability và tải responder | Làm mới/cache và tương thích client |

Không có cơ chế nào tự bảo đảm trạng thái thu hồi được cập nhật tức thời. Độ mới phụ thuộc thời gian phát hiện, thời gian CA xử lý, thời gian phát hành trạng thái, cache, phân phối và cách verifier kiểm tra.

## 8. Hard-fail và soft-fail khi không thể kiểm tra trạng thái

Một quyết định khó trong revocation checking là: **verifier nên làm gì nếu không thể lấy hoặc xác minh trạng thái thu hồi?**

- **Hard-fail:** nếu không thể kiểm tra trạng thái theo yêu cầu, từ chối chứng chỉ hoặc từ chối kết nối.
- **Soft-fail:** nếu dịch vụ trạng thái không khả dụng, tiếp tục theo một chính sách ngoại lệ, có thể dựa vào response/cache còn đủ tin cậy hoặc cho phép tạm thời.

Không có lựa chọn tuyệt đối phù hợp mọi hệ thống. Hard-fail tăng bảo vệ khi cần biết chứng chỉ có bị thu hồi không, nhưng responder/network outage có thể làm gián đoạn dịch vụ. Soft-fail tăng khả năng sẵn sàng nhưng có thể chấp nhận một chứng chỉ đã bị thu hồi trong thời gian không kiểm tra được.

| Bối cảnh | Hướng chính sách thường cân nhắc | Lý do |
| --- | --- | --- |
| mTLS cho API quản trị hoặc quyền đặc biệt | Ưu tiên hard-fail hoặc nguồn trạng thái/cache được kiểm soát chặt | Chấp nhận nhầm certificate có thể mở quyền cao. |
| Client certificate cho hệ thống nội bộ trọng yếu | Hard-fail với hạ tầng CRL/OCSP dự phòng | Cần trạng thái thu hồi đáng tin và tính sẵn sàng có thiết kế. |
| Web browsing thông thường | Hành vi phụ thuộc browser và policy; có thể có fallback | Availability và trải nghiệm người dùng được cân bằng với rủi ro. |
| Môi trường cô lập/offline | Dùng CRL được phân phối trước, giới hạn tuổi; từ chối khi quá cũ theo policy | Không có responder trực tuyến nên freshness phải được quản lý rõ. |
| Hệ thống thanh toán/định danh nhạy cảm | Tránh soft-fail không giới hạn; dùng cache/replica có SLA | Cần tránh outage biến thành bypass thu hồi. |

### Soft-fail không có nghĩa bỏ qua mọi lỗi

Có thể phân biệt:
- **Revoked:** phải từ chối theo policy, không được coi như lỗi mạng để soft-fail.
- **Unknown:** responder không xác định; cần chính sách rõ, thường không nên coi như good.
- **Unavailable/timeout:** không lấy được response; xử lý theo hard/soft-fail và freshness.
- **Stale response:** response đã quá thời hạn chấp nhận; không dùng như trạng thái mới.
- **Invalid signature/wrong issuer:** dữ liệu không đáng tin; không chấp nhận response đó.

Một thiết kế an toàn có thể soft-fail chỉ khi response không thể lấy do outage tạm thời, nhưng vẫn phải giới hạn thời gian và phạm vi; không soft-fail khi nhận được trạng thái revoked hoặc response giả mạo. Cần log và cảnh báo mỗi lần fallback.

## 9. Freshness, cache và độ trễ thu hồi

Thu hồi không phải sự kiện tức thời trên toàn mạng. Có nhiều mốc thời gian:

~~~text
T0: Private key bị lộ / thiết bị bị mất
T1: Tổ chức phát hiện và yêu cầu thu hồi
T2: CA xác minh yêu cầu và cập nhật trạng thái
T3: CRL/OCSP response mới được phát hành
T4: Cache, proxy, server và verifier nhận trạng thái mới
T5: Các lần xác thực tiếp theo từ chối certificate
~~~

Khoảng thời gian từ T0 đến T5 là **revocation propagation window**. Trong khoảng này, một verifier có thể chưa biết chứng chỉ đã bị thu hồi. Mục tiêu vận hành là giảm cửa sổ này theo rủi ro và khả năng hạ tầng.

### Cache cần những quy tắc gì?

- Cache key phải gắn đúng issuer/serial và phạm vi response, không chỉ serial đơn lẻ nếu có thể trùng giữa CA.
- Không dùng response vượt quá `nextUpdate` hoặc freshness policy.
- Có thể cache trạng thái revoked lâu hơn trạng thái good, theo policy; trạng thái revoked không nên bị “quên” chỉ vì cache TTL ngắn.
- Không dùng cache cũ khi đã có tín hiệu thu hồi mới hơn.
- Đồng bộ đồng hồ server/responder; clock skew có thể làm response hợp lệ bị xem là tương lai hoặc đã cũ.
- Khi đổi CA/issuer hoặc trust configuration, phải làm mới cache tương ứng.
- Phân biệt cache response OCSP với cache path/certificate và cache session của ứng dụng.

**Cache không được biến stale-good thành good vô thời hạn.** Nếu status source không khả dụng, verifier cần biết tuổi response và áp dụng hard/soft-fail đúng policy.

### CRL schedule và OCSP SLA

CA nên công bố lịch phát hành, thisUpdate/nextUpdate, thời gian xử lý yêu cầu thu hồi và kênh khẩn cấp. Verifier nên giám sát:
- tuổi CRL/OCSP response đang dùng,
- thời gian từ yêu cầu thu hồi đến phát hành,
- độ trễ phân phối tới verifier,
- tỷ lệ timeout/unknown/stale,
- số lần soft-fail,
- số chứng chỉ bị từ chối vì revoked.

## 10. Certificate status không thay thế các kiểm tra PKI khác

Một certificate có OCSP `good` hoặc không nằm trong CRL vẫn có thể không hợp lệ cho giao dịch:

- Chữ ký CA không hợp lệ hoặc chain không tới trust anchor.
- Certificate đã hết hạn hoặc chưa tới NotBefore.
- SAN/subject không khớp hostname hoặc danh tính client mong đợi.
- Key Usage hoặc Extended Key Usage không cho phép mục đích xác thực.
- Basic Constraints/path length hoặc name constraints bị vi phạm.
- Thuật toán/chính sách mật mã không được phép.
- Certificate được cấp bởi CA không nằm trong trust store của verifier.
- Account/identity được ánh xạ từ certificate đã bị vô hiệu ở ứng dụng, dù chứng chỉ chưa revoked.

Revocation là **một kiểm tra trong quá trình validation**, không phải thay thế certificate path validation và application authorization.

## 11. Thu hồi trong TLS server authentication

Khi trình duyệt hoặc client kết nối TLS tới server, server trình bày certificate chain. Client có thể kiểm tra trạng thái thu hồi bằng CRL/OCSP/stapling tùy nền tảng, trust store và policy.

Nếu certificate server bị thu hồi do private key bị lộ, tổ chức cần:
1. Ngừng sử dụng key/certificate bị ảnh hưởng.
2. Thu hồi chứng chỉ ở CA và phát hành certificate mới với key mới.
3. Cập nhật load balancer, reverse proxy, CDN, ingress và mọi endpoint đang dùng certificate.
4. Kiểm tra stapling response được làm mới; không tiếp tục phát response cũ.
5. Giám sát client rejection và các bản sao certificate cũ còn được triển khai.
6. Nếu key bị lộ, điều tra các dịch vụ khác dùng cùng key hoặc cùng credential.

Một số client có thể soft-fail khi không truy cập được OCSP; không nên giả định tất cả browser đều kiểm tra revocation theo cùng một cách. Hành vi phụ thuộc nền tảng, cache, policy và cơ chế như stapling/CRLite hoặc danh sách trạng thái riêng.

## 12. Thu hồi trong mTLS và client certificate authentication

Trong **mutual TLS (mTLS)**, cả client và server đều có thể trình bày chứng chỉ. Server xác thực client certificate, sau đó ánh xạ certificate identity tới account, device hoặc workload. Thu hồi client certificate đặc biệt quan trọng khi:
- laptop/agent bị mất,
- workload bị xâm nhập,
- nhân viên rời tổ chức,
- private key bị lộ,
- thiết bị bị decommission,
- certificate được cấp nhầm quyền.

Luồng mTLS:

~~~mermaid
sequenceDiagram
    participant C as Client / Workload
    participant S as API Server
    participant P as PKI status service
    C->>S: TLS ClientHello + certificate chain
    S->>S: Validate chain, SAN, EKU, policy
    S->>P: Check CRL/OCSP/cache according to policy
    P-->>S: good / revoked / unknown / unavailable
    S->>S: Apply revocation policy
    alt certificate trusted and not revoked
        S-->>C: TLS established
        S->>S: Map certificate identity to principal
        S->>S: Authorization for API action
    else revoked or unacceptable status
        S-->>C: Abort handshake / reject
    end
~~~

**Không dùng subject DN làm định danh duy nhất một cách mù quáng.** Nên xác định mapping theo issuer, serial/fingerprint hoặc SAN/URI SAN theo profile đã định; kiểm tra EKU, trust chain và trạng thái certificate. Một certificate hợp lệ vẫn không tự cấp mọi quyền API: principal phải được phân quyền theo resource và tenant.

### Thu hồi chứng chỉ không tự thu hồi session đã tạo

Giả sử client mTLS đã xác thực lúc 09:00, nhận access token có thời hạn 30 phút. Lúc 09:05, CA thu hồi client certificate. Nếu API chỉ kiểm tra JWT và không ràng buộc token với trạng thái certificate, token có thể vẫn được sử dụng đến khi hết hạn hoặc bị thu hồi theo cơ chế khác.

Các lựa chọn giảm cửa sổ:
- access token ngắn hạn,
- certificate-bound/sender-constrained token theo kiến trúc hỗ trợ,
- introspection hoặc trạng thái credential/session ở server,
- revoke session/token khi nhận sự kiện thu hồi,
- kiểm tra certificate status ở mỗi handshake mới,
- giới hạn scope/audience và thời gian hiệu lực.

Không giả định revocation status được kiểm tra lại trên mỗi HTTP request nếu TLS connection được giữ lâu hoặc token độc lập với certificate.

## 13. Thu hồi chứng chỉ CA và intermediate CA

Thu hồi leaf certificate là một trường hợp; khi CA hoặc intermediate CA bị xâm nhập, phạm vi ảnh hưởng rộng hơn.

- Nếu **intermediate CA** bị compromise, có thể cần loại intermediate khỏi trust store, phát hành trust configuration mới, thu hồi hoặc thay thế các leaf certificate liên quan và điều tra các chứng chỉ được cấp trong thời gian rủi ro.
- Nếu **root CA** không còn đáng tin, việc loại root khỏi trust store là thay đổi trust anchor, không chỉ là thu hồi một leaf certificate. Cần quy trình cập nhật trust store ở client/server, thiết bị và hệ thống ngoại tuyến.
- Nếu certificate CA bị thu hồi trong một PKI hierarchy, verifier phải xử lý theo profile và path validation policy; không tự giả định OCSP/CRL của leaf là đủ.

Sự cố CA có thể cần phối hợp nhiều nhóm: PKI, security operations, platform, endpoint management, application owners và nhà cung cấp. Phải có inventory chứng chỉ, issuer, serial, subject/SAN, nơi triển khai và owner để khoanh vùng.

## 14. Quy trình vận hành thu hồi và cấp lại

Một quy trình có kiểm soát nên bao gồm:

### 14.1. Phát hiện và tiếp nhận

Nguồn yêu cầu: báo mất thiết bị, cảnh báo EDR, nhân viên rời công ty, phát hiện key leak, kiểm toán, CA notification hoặc tự động hóa từ certificate inventory. Xác định certificate cụ thể bằng issuer + serial/fingerprint; không chỉ dựa vào common name có thể trùng.

### 14.2. Xác minh thẩm quyền

Kiểm tra người yêu cầu có quyền yêu cầu thu hồi theo policy. Với private key compromise, ưu tiên xử lý khẩn cấp theo quy trình incident response; không để quy trình phê duyệt kéo dài làm tăng cửa sổ rủi ro. Với trường hợp thay đổi thông thường, lưu bằng chứng và người phê duyệt.

### 14.3. Thu hồi tại CA

CA cập nhật trạng thái, reason code và thời điểm thu hồi; phát hành CRL/OCSP response theo SLA. Nếu có nhiều CA hoặc intermediate, xác định đúng issuer và kênh status. Lưu request ID và kết quả CA để audit.

### 14.4. Phân phối và thực thi

- Đảm bảo CRL/OCSP mới được công bố và responder hoạt động.
- Làm mới cache/OCSP stapling ở server.
- Cập nhật verifier, trust store hoặc policy nếu cần.
- Xác minh các endpoint thực sự từ chối certificate revoked.
- Thu hồi session/token và quyền ứng dụng liên quan nếu có.
- Vô hiệu certificate cũ trong inventory/configuration management.

### 14.5. Cấp lại credential

Tạo key pair mới trong môi trường an toàn, xác minh lại identity/ownership và cấp certificate mới với SAN, EKU, validity và policy tối thiểu cần thiết. Không tái sử dụng private key nghi đã bị lộ. Cập nhật secret store/HSM/device, triển khai certificate mới và kiểm tra kết nối trước khi đóng sự cố.

### 14.6. Điều tra và hậu kiểm

Xác định thời điểm compromise, hệ thống đã chấp nhận chứng chỉ trong khoảng nào, token/session nào đã được tạo, dữ liệu nào có thể bị truy cập. Lưu log không chứa private key; bổ sung phát hiện, rút ngắn propagation window hoặc cải thiện inventory/SLA.

## 15. Reason code và trạng thái thu hồi

CRL/OCSP có thể cung cấp reason code giúp mô tả lý do thu hồi. Một số reason phổ biến trong X.509 gồm:
- **keyCompromise:** khóa riêng có thể bị lộ.
- **cACompromise:** khóa CA bị compromise.
- **affiliationChanged:** quan hệ tổ chức thay đổi.
- **superseded:** chứng chỉ được thay thế.
- **cessationOfOperation:** ngừng hoạt động.
- **certificateHold:** tạm giữ theo cơ chế cho phép.
- **privilegeWithdrawn:** đặc quyền liên quan bị thu hồi.
- **removeFromCRL:** dùng trong một số luồng xử lý delta CRL/hold theo quy tắc chuẩn.

Không phải mọi CA hay profile đều dùng mọi reason code; ý nghĩa và khả năng đảo trạng thái phụ thuộc chuẩn và chính sách. Verifier thường không nên tự quyết định rằng một reason code “ít nghiêm trọng” cho phép tiếp tục tin certificate nếu trạng thái đã được xác định là revoked/không được chấp nhận.

**CertificateHold** có thể có cách xử lý khác thu hồi vĩnh viễn, nhưng phải theo đúng profile; không tự coi một serial đã bị hold rồi sau đó không xuất hiện trong CRL mới là hợp lệ nếu không kiểm tra cơ chế delta/base và trạng thái cập nhật.

## 16. Kiểm thử revocation và failure modes

| Ca kiểm thử | Kết quả mong đợi |
| --- | --- |
| Certificate hợp lệ, không bị liệt kê trong CRL mới | Tiếp tục các bước validation khác. |
| Certificate có serial trong CRL hợp lệ | Từ chối theo policy. |
| CRL hết hạn/qua NextUpdate | Không coi trạng thái là fresh; áp dụng hard/soft-fail đã cấu hình. |
| CRL chữ ký sai hoặc issuer không đúng | Từ chối CRL, không dùng như trạng thái đáng tin. |
| Delta CRL thiếu base tương ứng | Không coi delta là danh sách đầy đủ; xử lý lỗi theo profile. |
| OCSP trả revoked | Từ chối certificate. |
| OCSP trả unknown | Áp dụng policy rõ; không tự coi là good. |
| OCSP response chữ ký sai | Từ chối response. |
| OCSP response sai serial/issuer | Từ chối response. |
| OCSP response stale | Không dùng như trạng thái hiện hành. |
| OCSP responder timeout | Hard-fail hoặc soft-fail có giới hạn theo policy. |
| OCSP stapling response revoked | Client từ chối certificate server. |
| OCSP stapling thiếu/cũ khi profile yêu cầu | Từ chối theo policy/client behavior. |
| Certificate bị thu hồi nhưng JWT đã phát hành vẫn còn hạn | Token/session policy xử lý riêng; không giả định tự thu hồi. |
| Client mTLS certificate revoked | Handshake hoặc xác thực bị từ chối theo policy. |
| Certificate thay thế nhưng key cũ vẫn được dùng | Phát hiện và từ chối certificate/key cũ đã revoke. |
| Cache status của issuer A dùng cho issuer B | Không được phép; cache key phải gắn issuer và serial/phạm vi. |
| Clock lệch làm response có timestamp tương lai | Từ chối hoặc xử lý theo clock-skew policy; cảnh báo đồng hồ. |
| CertificateHold được gỡ | Xử lý theo CRL/OCSP/profile và cập nhật cache đúng cách. |
| Intermediate CA bị compromise | Áp dụng trust-store/path remediation, không chỉ kiểm tra leaf. |

### Kiểm thử propagation end-to-end

1. Tạo certificate test từ CA thử nghiệm và cài vào client/server.
2. Xác nhận handshake/xác thực thành công trước khi thu hồi.
3. Thu hồi certificate qua CA test.
4. Chờ trạng thái mới được phát hành, tải về và làm mới cache theo SLA thử nghiệm.
5. Thử lại handshake/validation từ từng verifier.
6. Xác nhận mọi verifier bắt đầu từ chối trong propagation window đã đặt.
7. Kiểm tra token/session đã cấp trước thời điểm thu hồi có bị xử lý theo policy hay không.
8. Khôi phục môi trường test và ghi nhận thời gian từng mốc.

Không thử thu hồi chứng chỉ production hoặc trust anchor nếu không có change/incident authorization phù hợp. Bài học chỉ mô tả quy trình; thao tác thật phải theo quy trình quản trị PKI của tổ chức.

## 17. Thiết kế chính sách hard-fail/soft-fail theo rủi ro

Một policy cần xác định rõ:
- loại certificate (server TLS, client mTLS, user certificate, code signing, CA/intermediate),
- tài sản và mức quyền nếu certificate được chấp nhận nhầm,
- nguồn trạng thái (CRL, OCSP, stapling, cache nội bộ),
- tuổi tối đa của trạng thái được chấp nhận,
- xử lý revoked, unknown, stale, invalid và unavailable,
- timeout, retry, failover và cache behavior,
- cách giám sát và cảnh báo,
- ảnh hưởng đến session/token đã phát hành.

Ví dụ policy minh họa:

| Certificate | Trạng thái | Hướng xử lý minh họa |
| --- | --- | --- |
| Client cert cho API quản trị | Revoked | Hard deny; thu hồi session/token liên quan. |
| Client cert cho API quản trị | OCSP unavailable nhưng cache còn fresh trong SLA | Có thể dùng cache đã xác minh theo policy; cảnh báo trạng thái responder. |
| Client cert cho API quản trị | Chỉ có stale status | Từ chối hoặc chuyển quy trình dự phòng được phê duyệt; không dùng vô hạn. |
| Server certificate public web | OCSP response unavailable | Hành vi tùy client/browser; server duy trì stapling fresh và certificate rotation. |
| Certificate thiết bị trong mạng cô lập | Không thể truy vấn OCSP | Dùng CRL phân phối nội bộ với tuổi tối đa và quy trình cập nhật rõ. |
| Certificate workload có quyền đọc dữ liệu nhạy cảm | Unknown | Không tự coi là good; dùng fail-closed hoặc quy trình xử lý riêng. |

Bảng này là gợi ý thiết kế, không phải yêu cầu chung của mọi tiêu chuẩn. Quyết định cuối cùng cần xem threat model, khả năng sẵn sàng, chuẩn áp dụng và rủi ro vận hành.

## 18. Ghi nhớ

**Certificate revocation cho verifier biết một chứng chỉ đã bị mất niềm tin trước khi hết hạn.** CRL cung cấp danh sách thu hồi có thể tải và cache; OCSP cung cấp trạng thái theo từng chứng chỉ; OCSP stapling giúp server gửi response cho client trong TLS. Dù dùng cơ chế nào, verifier vẫn phải kiểm tra chữ ký response, issuer/phạm vi, freshness và áp dụng chính sách hard-fail/soft-fail rõ ràng.

Thu hồi chỉ hiệu quả khi toàn bộ chuỗi vận hành hoạt động: phát hiện, xác minh yêu cầu, cập nhật CA, phân phối trạng thái, làm mới cache, thực thi ở verifier, thu hồi session/token liên quan và cấp credential mới. Khi review hệ thống, hãy hỏi: **Ai có quyền thu hồi? Verifier biết trạng thái mới trong bao lâu? Nếu OCSP/CRL không khả dụng thì hệ thống làm gì? Chứng chỉ bị thu hồi có thể vẫn dùng qua session/token cũ không? Làm sao chứng minh mọi endpoint đã ngừng tin credential đó?**
