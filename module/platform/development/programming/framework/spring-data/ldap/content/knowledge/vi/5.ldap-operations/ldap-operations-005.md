# Mã kết quả LDAP và thông tin lỗi trả về

Khi ứng dụng Java làm việc với LDAP, mỗi thao tác như Bind, Search, Add, Modify, Delete hay Modify DN có thể **thành công, bị từ chối hoặc chỉ hoàn tất một phần**. Để xử lý đúng, ta phải phân biệt **mã kết quả LDAP do máy chủ gửi**, **thông tin chẩn đoán đi kèm** và **ngoại lệ mà thư viện Java đưa lên tầng ứng dụng**. Những thứ này có liên quan nhưng không phải một.

Bài học thuộc chương **Thao tác LDAP** của mô-đun `SPRING_DATA_LDAP`. Bạn sẽ đọc các trường của `LDAPResult`, nhận diện các mã phổ biến, ánh xạ chúng sang cách xử lý phù hợp trong Spring Data LDAP/`LdapTemplate`, và kiểm chứng trên directory thật. Ví dụ gắn với DN, `objectClass`, schema, repository, filter an toàn, CRUD, TLS và kiểm thử tích hợp.

> **Nguyên tắc cốt lõi:** mã LDAP cho biết **server xử lý thao tác như thế nào**; mã HTTP cho biết **API muốn thông báo gì với người gọi**; còn thông điệp chẩn đoán LDAP là **dữ liệu từ server**, không phải hợp đồng ổn định để client phân tích hoặc hiển thị nguyên văn.

## 1. Kết quả mong đợi

Sau bài học, bạn có thể:

1. Đọc được `resultCode`, `matchedDN`, `diagnosticMessage` và `referral` của một kết quả LDAP.
2. Giải thích khác biệt giữa **Search không có entry**, `noSuchObject (32)`, `invalidCredentials (49)`, `insufficientAccessRights (50)` và `entryAlreadyExists (68)`.
3. Nhóm các mã lỗi theo tình huống: xác thực, cấu trúc DN/schema, thuộc tính, giới hạn truy vấn, trạng thái server và referral.
4. Phân biệt các mã đặc biệt `compareFalse (5)`, `compareTrue (6)`, `saslBindInProgress (14)` với lỗi vận hành thông thường.
5. Dự đoán các ngoại lệ JNDI/Spring LDAP thường thấy khi dùng `LdapTemplate` hoặc repository.
6. Chọn cách phản hồi HTTP an toàn: không biến lỗi hạ tầng thành 404, không tiết lộ thông tin Bind và không tuyên bố Search đầy đủ khi thực tế bị giới hạn.
7. Thiết kế test thực tế để kích hoạt những mã kết quả quan trọng mà không cần sửa dữ liệu production.

## 2. Bối cảnh: một directory để làm ví dụ

Giả sử LDAP server có dữ liệu:

~~~text
dc=example,dc=org
├── ou=people
│   ├── uid=lan
│   └── uid=minh
├── ou=groups
│   └── cn=engineering
└── ou=service
    └── cn=svc-reader
~~~

Entry người dùng minh họa:

~~~ldif
dn: uid=lan,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: lan
cn: Nguyen Thi Lan
sn: Nguyen
mail: lan@example.org
~~~

`inetOrgPerson` kế thừa `person`, nên `cn` và `sn` là thuộc tính bắt buộc. Tài khoản `cn=svc-reader,ou=service,dc=example,dc=org` có thể có quyền đọc nhánh `ou=people` nhưng không nhất thiết có quyền Add/Modify/Delete. Nhờ vậy, ta có thể quan sát cả mã liên quan schema lẫn ACL.

Trong bài, các domain, mật khẩu và hồ sơ chỉ là **giá trị giả lập**. Hãy dùng một LDAP test server có TLS và cấu hình ACL riêng; không thử gây lỗi trên tài khoản hoặc nhóm thực tế.

## 3. LDAPResult nằm ở đâu trong giao thức?

Theo RFC 4511, nhiều response LDAP chứa một cấu trúc `LDAPResult`. Ở dạng giản lược:

~~~text
LDAPResult
├── resultCode          ENUMERATED
├── matchedDN           LDAPDN
├── diagnosticMessage   LDAPString
└── referral            LDAP URLs (tùy chọn)
~~~

Một `LDAPMessage` còn có `messageID` để ghép response với request; vì vậy **`messageID` không phải mã lỗi**, còn `resultCode` mới là trường phân loại kết quả của thao tác.

Các response thường mang `LDAPResult`:

| Request | Response hoàn tất | Điểm cần chú ý |
| --- | --- | --- |
| Bind | `BindResponse` | `invalidCredentials (49)` phổ biến khi xác thực thất bại. |
| Search | `SearchResultDone` | Có thể có nhiều `SearchResultEntry` và `SearchResultReference` **trước** thông điệp kết thúc. |
| Modify | `ModifyResponse` | Lỗi thuộc tính/schema/quyền thường thể hiện bằng resultCode. |
| Add | `AddResponse` | Có thể trả `entryAlreadyExists (68)` hoặc `objectClassViolation (65)`. |
| Delete | `DelResponse` | Có thể trả `noSuchObject (32)` hoặc `notAllowedOnNonLeaf (66)`. |
| Modify DN | `ModifyDNResponse` | Phụ thuộc RDN, parent, quyền và giới hạn server. |
| Compare | `CompareResponse` | `compareTrue (6)` và `compareFalse (5)` là kết quả hợp lệ của phép Compare. |
| Extended operation | `ExtendedResponse` | Có thể chứa LDAPResult và trường mở rộng tùy operation. |

**Ngoại lệ quan trọng:** `UnbindRequest` dùng để đóng phiên LDAP **không có response xác nhận thông thường**. `AbandonRequest` cũng không có response dành riêng. Do đó đừng đợi `resultCode` sau khi gửi Unbind hoặc Abandon.

### Dòng thời gian một LDAP Search

~~~mermaid
sequenceDiagram
    participant App as Ứng dụng Java
    participant Dir as LDAP server
    App->>Dir: SearchRequest(base, scope, filter)
    Dir-->>App: SearchResultEntry: uid=lan
    Dir-->>App: SearchResultEntry: uid=minh
    opt Có phân vùng khác
        Dir-->>App: SearchResultReference
    end
    Dir-->>App: SearchResultDone: resultCode + LDAPResult
    Note over App: Chỉ biết kết quả Search đã hoàn tất như thế nào sau SearchResultDone
~~~

Khi server trả `sizeLimitExceeded (4)` hoặc `timeLimitExceeded (3)`, client có thể đã nhận **một số entry trước đó**. Danh sách ấy không được coi là đầy đủ chỉ vì có dữ liệu.

## 4. Ý nghĩa từng trường LDAPResult

| Trường | Ý nghĩa | Cách dùng an toàn |
| --- | --- | --- |
| `resultCode` | Mã chuẩn hóa cho kết quả thao tác. | Dùng để phân loại tình huống; phải xét thêm loại request và ngữ cảnh. |
| `matchedDN` | DN khớp gần nhất trong một số tình huống lỗi phân giải tên. | Hỗ trợ chẩn đoán base/DN; có thể rỗng và có thể bị chính sách server giới hạn. |
| `diagnosticMessage` | Chuỗi mô tả bổ sung do server cung cấp. | Chỉ dùng để hỗ trợ vận hành; không phụ thuộc chuỗi/không trả nguyên văn ra API. |
| `referral` | Danh sách LDAP URL dẫn tới server/nhánh khác, nếu có. | Áp chính sách đích, TLS, danh tính trước khi follow; không tự động chuyển credential. |

### 4.1. `matchedDN` không phải “DN bị lỗi”

Giả sử bạn Search ở:

~~~text
ou=unknown,dc=example,dc=org
~~~

và chỉ `dc=example,dc=org` đang tồn tại. Một số server có thể trả:

~~~text
resultCode: 32 (noSuchObject)
matchedDN: dc=example,dc=org
diagnosticMessage: <mô tả của server>
~~~

`matchedDN` cho biết phần tên tồn tại/khớp gần nhất mà server có thể thông báo, **không phải tên entry mà client cần tạo hoặc cần xóa**. Không nên dựa vào nó để tự động tạo OU còn thiếu. Đừng coi giá trị trả về là bằng chứng người gọi có quyền đọc mọi entry trong nhánh đó.

### 4.2. `diagnosticMessage` không có định dạng chuẩn cho từng nhà cung cấp

Thông điệp có thể là tiếng Anh hoặc ngôn ngữ khác, có thể chứa mã phụ, tên schema, thuộc tính, DN, chi tiết xác thực hay chính sách riêng của directory. Ví dụ Active Directory có thể đặt thông tin bổ sung trong chuỗi chẩn đoán. Chuỗi này có thể thay đổi sau bản nâng cấp server.

Vì thế:

- **Không** so khớp chuỗi kiểu `contains("Invalid credentials")` để quyết định phân quyền.
- **Không** dựa vào subcode của một vendor như một phần của HTTP API công khai.
- **Không** trả nguyên văn thông điệp trong response REST hoặc đưa vào log không kiểm soát.
- Chỉ ghi mã/lớp lỗi chuẩn hóa, request ID và metadata được cho phép; giữ diagnostic chi tiết trong vùng vận hành bảo mật khi thật sự cần.

### 4.3. `referral` không phải quyền truy cập

Một `resultCode=10` có thể kèm các URL LDAP khác. Đích được đề xuất **không tự được tin cậy** và có thể đòi hỏi danh tính/credential riêng. Search còn có `SearchResultReference` không nhất thiết là một `LDAPResult` kết thúc. Xử lý referral phải xét policy topology và tính đầy đủ của kết quả.

## 5. Bảng mã kết quả LDAP thường gặp

Mã dưới đây thuộc tập resultCode của LDAPv3 (RFC 4511) và thường gặp trong môi trường OpenLDAP hoặc các directory tương thích. **Không phải mọi server đều hỗ trợ mọi extension hoặc có cùng chi tiết diagnostic**.

### 5.1. Thành công, kết quả đặc biệt và lỗi giao thức

| Mã | Tên chuẩn | Ý nghĩa ngắn | Lưu ý |
| ---: | --- | --- | --- |
| **0** | `success` | Thao tác hoàn tất theo semantics của operation. | Search có thể trả **0 entry**; thành công không đồng nghĩa “tìm thấy người”. |
| **1** | `operationsError` | Lỗi vận hành phía server. | Cần kiểm tra logs/giới hạn server; không tự kết luận input sai. |
| **2** | `protocolError` | Dữ liệu giao thức/yêu cầu không hợp lệ. | Kiểm tra client, version, control và kết nối. |
| **5** | `compareFalse` | Phép Compare đã thực hiện và kết quả FALSE. | Không đồng nghĩa lỗi server. |
| **6** | `compareTrue` | Phép Compare đã thực hiện và kết quả TRUE. | Không đồng nghĩa `success (0)` của Search. |
| **7** | `authMethodNotSupported` | Cơ chế xác thực không được hỗ trợ. | Cân nhắc cơ chế Bind phù hợp. |
| **8** | `strongerAuthRequired` | Server yêu cầu cơ chế xác thực mạnh hơn. | Không tắt bảo mật để vượt lỗi. |
| **10** | `referral` | Có thể chuyển yêu cầu đến đích khác. | Kiểm tra topology, TLS, credential trước khi theo. |
| **12** | `unavailableCriticalExtension` | Server không hỗ trợ control/extension bắt buộc. | Kiểm tra criticality và khả năng tương thích. |
| **13** | `confidentialityRequired` | Cần mức bảo mật đường truyền thích hợp. | Dùng LDAPS hoặc StartTLS được xác minh. |
| **14** | `saslBindInProgress` | Một bước trung gian của SASL Bind nhiều lượt. | Không coi là authentication cuối cùng thành công. |

**So sánh kết quả Compare:** `5` hoặc `6` có thể là kết quả **hợp lệ** của `CompareRequest`. Không nên viết logic “mọi mã khác 0 là lỗi ứng dụng” mà bỏ qua loại operation.

### 5.2. Giới hạn Search, tải và trạng thái server

| Mã | Tên chuẩn | Ý nghĩa | Cách xử lý |
| ---: | --- | --- | --- |
| **3** | `timeLimitExceeded` | Search vượt giới hạn thời gian. | Xem kết quả là **có thể chưa đầy đủ**; thu hẹp scope/filter, điều chỉnh timeout hợp lý. |
| **4** | `sizeLimitExceeded` | Search vượt giới hạn kích thước kết quả. | Không tuyên bố danh sách đầy đủ; thiết kế giới hạn hoặc phân trang. |
| **11** | `adminLimitExceeded` | Vượt một giới hạn quản trị khác. | Kiểm tra chính sách directory, index và mô hình truy vấn. |
| **51** | `busy` | Server đang bận. | Retry có giới hạn/backoff nếu operation an toàn để retry. |
| **52** | `unavailable` | Dịch vụ LDAP không sẵn sàng. | Cân nhắc HTTP 503, health check và circuit breaker. |
| **53** | `unwillingToPerform` | Server từ chối thực hiện operation theo chính sách/trạng thái. | Không tự suy luận là credential sai. |
| **54** | `loopDetect` | Server phát hiện vòng lặp trong quá trình xử lý. | Kiểm tra alias/referral/topology. |
| **80** | `other` | Lỗi khác không phân loại được ở các mã trên. | Kiểm tra diagnostic an toàn và server logs. |

**Phân biệt limit của client và server:** `LdapQueryBuilder.countLimit(...)` yêu cầu giới hạn tìm kiếm, còn server có thể áp limit chặt hơn. `sizeLimitExceeded` không đồng nghĩa server đã trả đúng bằng số entry mà application mong muốn. LDAP không mặc định trả thứ tự ổn định hay phân trang tự động.

### 5.3. Thuộc tính, schema và so khớp

| Mã | Tên chuẩn | Ví dụ thường gặp |
| ---: | --- | --- |
| **16** | `noSuchAttribute` | Thử xóa một giá trị thuộc tính không tồn tại. |
| **17** | `undefinedAttributeType` | Thuộc tính trong request không được schema server biết đến. |
| **18** | `inappropriateMatching` | Dùng matching rule không phù hợp cho thuộc tính. |
| **19** | `constraintViolation` | Vi phạm giới hạn giá trị hoặc quy tắc schema/chính sách. |
| **20** | `attributeOrValueExists` | Thêm giá trị đã tồn tại vào thuộc tính. |
| **21** | `invalidAttributeSyntax` | Giá trị thuộc tính sai cú pháp LDAP được khai báo. |
| **65** | `objectClassViolation` | Thiếu `cn` hoặc `sn` khi tạo `inetOrgPerson`; thuộc tính không được class cho phép. |
| **69** | `objectClassModsProhibited` | Thao tác thay `objectClass` bị server cấm. |

Ví dụ, `groupOfNames` yêu cầu `cn` và tối thiểu một `member`. Một lệnh Modify xóa **giá trị cuối cùng** của `member` có thể bị server từ chối vì vi phạm schema. Trái lại, thêm lại một giá trị `member` đã có có thể bị từ chối với mã `20`.

**Đừng hardcode “mã X chắc chắn chỉ có một nguyên nhân”.** Server có thể dùng mã khác tùy loại thao tác, ACL, schema và extension. Cần đối chiếu loại operation, trạng thái entry và response thực tế.

### 5.4. Tên, cấu trúc cây và quyền

| Mã | Tên chuẩn | Tình huống |
| ---: | --- | --- |
| **32** | `noSuchObject` | DN đích hoặc search base không tồn tại. |
| **33** | `aliasProblem` | Có vấn đề xử lý alias. |
| **34** | `invalidDNSyntax` | DN sai cú pháp. |
| **36** | `aliasDereferencingProblem` | Không thể dereference alias theo yêu cầu. |
| **48** | `inappropriateAuthentication` | Kiểu xác thực không phù hợp với operation/chính sách. |
| **49** | `invalidCredentials` | Xác thực thất bại; không mặc định biết chính xác sai username hay password. |
| **50** | `insufficientAccessRights` | Bind account không đủ quyền thao tác/thuộc tính. |
| **64** | `namingViolation` | Vị trí/RDN/đặt tên vi phạm quy tắc schema hoặc server. |
| **66** | `notAllowedOnNonLeaf` | Xóa một entry vẫn có entry con, khi server không cho phép. |
| **67** | `notAllowedOnRDN` | Cố sửa/xóa thuộc tính làm thành phần RDN theo cách bị cấm. |
| **68** | `entryAlreadyExists` | DN được Add/Rename tới đã tồn tại. |
| **71** | `affectsMultipleDSAs` | Thao tác ảnh hưởng nhiều directory system agents, ví dụ Move qua biên giới server không được hỗ trợ. |

Một DN có thể **hợp lệ về cú pháp** nhưng **không tồn tại** hoặc **không được phép ghi**. Vì thế `invalidDNSyntax (34)`, `noSuchObject (32)` và `insufficientAccessRights (50)` là ba loại tình huống khác nhau.

## 6. Những cặp tình huống dễ nhầm

### 6.1. Search rỗng với `success (0)` khác `noSuchObject (32)`

Giả sử `ou=people,dc=example,dc=org` tồn tại.

**Truy vấn A:** tìm `uid=khongton tai` theo một filter hợp lệ nhưng không có entry khớp.

~~~text
Search base: ou=people,dc=example,dc=org
Filter:      (uid=khongtontai)
Response:    SearchResultDone, resultCode=success (0)
Entries:     []
~~~

**Truy vấn B:** tìm dưới OU không tồn tại.

~~~text
Search base: ou=khongtontai,dc=example,dc=org
Filter:      (uid=lan)
Response:    SearchResultDone, resultCode=noSuchObject (32)
Entries:     Không phải một Search thành công với 0 kết quả
~~~

Hậu quả đối với API:

- Nếu Search thành công nhưng không khớp, API có thể trả `200 []` (với endpoint danh sách).
- Nếu service yêu cầu một DN cụ thể nhưng entry đó không tồn tại, API có thể trả `404`.
- Nếu `noSuchObject` do **cấu hình sai base OU**, đó là lỗi ứng dụng/hạ tầng, **không phải “người dùng không tồn tại”**. Không ánh xạ mọi 32 thành 404 một cách mù quáng.

### 6.2. `invalidCredentials (49)` khác `insufficientAccessRights (50)`

- `49` liên quan việc **Bind/xác thực** thất bại.
- `50` liên quan một **operation đã được gửi trong context hiện tại** nhưng không đủ quyền để thực hiện.

Dù service account Bind thành công, nó vẫn có thể chỉ được Search và không được Modify. Ngược lại, khi Bind lỗi 49, không nên tiếp tục thực hiện thao tác nhạy cảm dưới giả định “đã đăng nhập”.

Trong hệ thống xác thực người dùng cuối, mã 49 có thể trả về HTTP **401** với thông báo chung. Nhưng nếu **mật khẩu tài khoản dịch vụ của ứng dụng** bị sai, trả 401 cho người gọi HTTP là gây hiểu nhầm; đây là lỗi cấu hình/tích hợp cần được báo về hệ thống vận hành mà không lộ secret.

### 6.3. `attributeOrValueExists (20)` khác `entryAlreadyExists (68)`

~~~text
ADD entry uid=lan,ou=people,... đã có       -> thường là 68
MODIFY thêm mail=lan@example.org đã có       -> có thể là 20
~~~

`entryAlreadyExists` liên quan **DN của entry**. `attributeOrValueExists` liên quan **giá trị thuộc tính** trong một entry.

### 6.4. Giới hạn Search không phải “không có dữ liệu”

Khi Search bị dừng do `3`, `4` hoặc `11`, server có thể đã gửi một phần entry. Nếu ứng dụng bỏ qua trạng thái cuối, người dùng có thể tưởng rằng danh bạ chỉ có những entry đã nhận được.

Trong báo cáo hay phân trang, cần thể hiện kết quả chưa đầy đủ hoặc báo lỗi có kiểm soát. **Không** dùng `sizeLimitExceeded` để tuyên bố “đủ N bản ghi” mà không có cơ chế phân trang đúng và kiểm chứng server.

## 7. Thử nghiệm mã kết quả bằng công cụ LDAP CLI

Có thể kiểm tra các tình huống trên bằng `ldapsearch`, `ldapadd` và `ldapmodify`. Ví dụ dùng server thử nghiệm ở `ldaps://ldap.example.org:636` và nhập mật khẩu qua `-W` để không đưa secret vào command line.

### 7.1. Search thành công, có entry

~~~bash
ldapsearch -LLL -x \
  -H ldaps://ldap.example.org:636 \
  -D "cn=svc-reader,ou=service,dc=example,dc=org" -W \
  -b "ou=people,dc=example,dc=org" -s one \
  "(&(objectClass=inetOrgPerson)(uid=lan))" \
  dn uid cn sn mail
~~~

Dự kiến thấy entry `uid=lan`. Tùy tùy chọn của CLI, bản tóm tắt result code có thể không hiện khi không có lỗi; đó không phải bằng chứng giao thức không có `SearchResultDone`.

### 7.2. Search thành công, không có entry

~~~bash
ldapsearch -x \
  -H ldaps://ldap.example.org:636 \
  -D "cn=svc-reader,ou=service,dc=example,dc=org" -W \
  -b "ou=people,dc=example,dc=org" -s one \
  "(uid=khongtontai)" dn uid
~~~

Kỳ vọng `result: 0 Success` hoặc biểu diễn tương đương, nhưng **không có SearchResultEntry**.

### 7.3. Search base không tồn tại

~~~bash
ldapsearch -x \
  -H ldaps://ldap.example.org:636 \
  -D "cn=svc-reader,ou=service,dc=example,dc=org" -W \
  -b "ou=missing,dc=example,dc=org" -s sub \
  "(objectClass=*)" dn
~~~

Trong directory test và với ACL cho phép thấy sự khác biệt, dự kiến gặp `No such object (32)`. Một số server có thể kèm `matchedDN` cho tổ tiên gần nhất. **Lưu ý:** server có ACL đặc thù có thể che sự tồn tại của entry; không suy luận tuyệt đối từ kết quả của một tài khoản không đủ quyền.

### 7.4. Bind sai credential

~~~bash
ldapwhoami -x \
  -H ldaps://ldap.example.org:636 \
  -D "cn=svc-reader,ou=service,dc=example,dc=org" -W
~~~

Để thử lỗi, nhập **mật khẩu sai có chủ đích** trong môi trường test, không làm lộ mật khẩu thật. Kỳ vọng một lỗi xác thực, thường là `Invalid credentials (49)`. Chính sách khóa tài khoản có thể giới hạn số lần thử; không brute-force hoặc lặp nhiều lần trên directory dùng chung.

### 7.5. Gây lỗi schema trong directory test

Thử thêm một `inetOrgPerson` thiếu `sn` qua `ldapadd` bằng **tài khoản ghi test**:

~~~ldif
dn: uid=broken,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: broken
cn: Broken Example
~~~

Nếu schema và quyền Add được thiết lập đúng, server thường từ chối vì `objectClassViolation (65)`. Đừng thử một LDIF lỗi với tài khoản chỉ đọc rồi kết luận mã 65 không tồn tại: server có thể từ chối sớm hơn bằng **`insufficientAccessRights (50)`**.

### 7.6. Kịch bản entry trùng

Sau khi có `uid=lan`, thử Add lại **cùng DN** trong directory test. Kết quả thường là `Already exists (68)`. Không dùng lệnh này như cách “cập nhật” entry; thao tác cập nhật phải dùng Modify với chính sách thuộc tính rõ ràng.

## 8. Đọc lỗi trong Java: JNDI và Spring LDAP

Hai tầng thư viện có cách trình bày lỗi khác nhau.

### 8.1. JNDI ở tầng thấp

JNDI sử dụng các lớp checked exception thuộc `javax.naming`, ví dụ:

- `javax.naming.AuthenticationException`: lỗi xác thực, thường liên quan Bind.
- `javax.naming.NameNotFoundException`: tên đối tượng không được phân giải.
- `javax.naming.NameAlreadyBoundException`: tên đã gắn với một đối tượng.
- `javax.naming.directory.SchemaViolationException`: vi phạm schema.
- `javax.naming.CommunicationException`: lỗi giao tiếp, có thể không nhận được LDAPResult từ server.
- `javax.naming.PartialResultException` hoặc `SizeLimitExceededException`: tình huống Search chưa đầy đủ.

Các exception này **không phải chính các số resultCode**. JNDI LDAP provider chuyển đổi kết quả giao thức thành các lớp exception và message theo triển khai; một loại exception cũng có thể xuất hiện do nhiều nguyên nhân.

Ví dụ tại tầng JNDI:

~~~java
try {
    // Một lời gọi JNDI DirContext, ví dụ ctx.lookup(dn)
} catch (javax.naming.AuthenticationException ex) {
    // Xác thực/Bind thất bại; không lộ message cho end user.
} catch (javax.naming.NameNotFoundException ex) {
    // DN không được tìm thấy hoặc không thể phân giải.
} catch (javax.naming.NamingException ex) {
    // Kiểm tra lớp lỗi và root cause theo log nội bộ an toàn.
}
~~~

Trong `javax.naming.NamingException`, các phương thức như `getExplanation()`, `getResolvedName()`, `getRemainingName()` và `getRootCause()` có thể hữu ích cho chẩn đoán. Chúng không được mặc định đưa ra ngoài HTTP response hoặc log đại trà vì có thể chứa cấu trúc directory, host hoặc chi tiết Bind.

### 8.2. Spring LDAP chuyển lỗi thành unchecked exception

`LdapTemplate` xử lý JNDI và chuyển những exception thành hierarchy `org.springframework.ldap.*`, ví dụ:

~~~text
org.springframework.ldap.NamingException (unchecked)
├── org.springframework.ldap.AuthenticationException
├── org.springframework.ldap.NameNotFoundException
├── org.springframework.ldap.NameAlreadyBoundException
└── ... các exception LDAP khác
~~~

Đây là **sơ đồ khái niệm**, không phải danh sách đầy đủ mọi lớp và mối quan hệ kế thừa. Những loại cụ thể phụ thuộc phiên bản Spring LDAP.

Một điểm dễ nhầm là có **hai lớp tên gần giống nhau**:

~~~java
javax.naming.NameNotFoundException        // JNDI, checked
org.springframework.ldap.NameNotFoundException // Spring LDAP, unchecked
~~~

Khi gọi `LdapTemplate`, mã ở tầng service thường xử lý lớp exception của **Spring LDAP** thay vì mặc định bắt lớp JNDI. Để biết thêm diagnostic từ provider, có thể kiểm tra `getCause()` một cách an toàn trong hệ thống observability.

### 8.3. Đừng kỳ vọng lấy được raw resultCode từ mọi Spring exception

Thư viện có thể phân loại lỗi dưới dạng exception class và thông tin cause; mã số LDAP gốc **không được bảo đảm luôn lộ ra qua một API thống nhất** của `LdapTemplate`. Tránh viết logic phân tích một chuỗi exception cố định bằng regex như `"LDAP: error code 49"` — nhiều provider và phiên bản khác nhau dùng cách hiển thị khác nhau.

Khi cần quan sát mã số chính xác để điều tra, dùng LDAP CLI, log phía server hoặc một lớp client thấp hơn có cơ chế cung cấp raw protocol response rõ ràng. Đừng giả định error message của thư viện là một protocol API ổn định.

## 9. Ví dụ service phân biệt Search rỗng và lookup thiếu DN

Giả định Spring Boot đã cấu hình `spring.ldap.base=dc=example,dc=org`, `LdapTemplate` kết nối qua LDAPS bằng tài khoản chỉ đọc.

`DirectoryPersonView.java`:

~~~java
package com.example.directory.api;

public record DirectoryPersonView(
        String uid,
        String commonName,
        String email
) {}
~~~

`DirectoryLookupService.java`:

~~~java
package com.example.directory.service;

import java.util.List;
import javax.naming.Name;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;

import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;
import org.springframework.ldap.query.SearchScope;
import org.springframework.ldap.support.LdapNameBuilder;
import org.springframework.stereotype.Service;

import com.example.directory.api.DirectoryPersonView;

@Service
public class DirectoryLookupService {

    private final LdapTemplate ldapTemplate;

    public DirectoryLookupService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    // SEARCH: không khớp filter là danh sách rỗng, không phải 32.
    public List<DirectoryPersonView> searchByUid(String uid) {
        validateUid(uid);

        LdapQuery query = LdapQueryBuilder.query()
                .base("ou=people")
                .searchScope(SearchScope.ONELEVEL)
                .countLimit(20)
                .where("objectClass").is("inetOrgPerson")
                .and("uid").is(uid);

        return ldapTemplate.search(
                query,
                (AttributesMapper<DirectoryPersonView>)
                    DirectoryLookupService::mapEntry
        );
    }

    // LOOKUP: truy cập một DN cụ thể; DN không có có thể dẫn
    // đến NameNotFoundException của Spring LDAP.
    public DirectoryPersonView getByDn(String uid) {
        validateUid(uid);
        Name dn = LdapNameBuilder.newInstance("ou=people")
                .add("uid", uid)
                .build();

        return ldapTemplate.lookup(
                dn,
                new String[] { "uid", "cn", "mail" },
                (AttributesMapper<DirectoryPersonView>)
                    DirectoryLookupService::mapEntry
        );
    }

    private static DirectoryPersonView mapEntry(Attributes attrs)
            throws javax.naming.NamingException {
        return new DirectoryPersonView(
                value(attrs, "uid"),
                value(attrs, "cn"),
                value(attrs, "mail")
        );
    }

    private static String value(Attributes attrs, String name)
            throws javax.naming.NamingException {
        Attribute attr = attrs.get(name);
        return attr == null ? null : (String) attr.get();
    }

    private static void validateUid(String uid) {
        if (uid == null
                || !uid.matches("[a-z][a-z0-9._-]{2,31}")) {
            throw new IllegalArgumentException("Invalid uid");
        }
    }
}
~~~

### Vì sao có hai phương thức?

| Phương thức | Operation | Khi không có người dùng |
| --- | --- | --- |
| `searchByUid("khongtontai")` | Search ở `ou=people` với filter `(uid=...)`. | Search có thể thành công với danh sách rỗng. |
| `getByDn("khongtontai")` | Lookup DN cụ thể `uid=...,ou=people`. | Có thể phát sinh `org.springframework.ldap.NameNotFoundException`. |

**Chú ý scope và ACL:** Search có thể trả rỗng vì filter không khớp, vì tài khoản Bind không được thấy entry hoặc vì cấu hình search base/scope không đúng. Với API cần khẳng định người dùng không tồn tại, nên phân tích quyền và ngữ cảnh thay vì chỉ suy luận từ một lần tìm rỗng.

Các thao tác filter trong `LdapQueryBuilder` encode giá trị an toàn. Còn `LdapNameBuilder` xây DN theo RFC 4514; hai cơ chế escaping này khác nhau.

## 10. Chuyển lỗi LDAP thành HTTP response có chủ đích

Một REST API có thể đưa cùng lỗi LDAP tới những HTTP code **khác nhau tùy use case**. Không có bản ánh xạ một-một chuẩn từ LDAP resultCode sang HTTP status.

### 10.1. Bảng quy tắc gợi ý

| Tình huống ứng dụng | LDAP/JNDI thường gặp | HTTP gợi ý | Ghi chú |
| --- | --- | ---: | --- |
| Tìm danh sách không có người khớp | `Search success (0)`, 0 entry | 200 + `[]` | Không phải lỗi. |
| Truy cập một người theo DN mà không tồn tại | `noSuchObject (32)`/NameNotFound | 404 | Chỉ khi base/config đã được xác nhận hợp lệ. |
| Request tạo entry trùng DN | `entryAlreadyExists (68)` | 409 | Có thể có race giữa check và Add; xử lý tại server. |
| Client gửi dữ liệu vi phạm quy tắc nghiệp vụ | `constraintViolation (19)`/schema | 400 hoặc 422 | Không trả nguyên schema details; còn phải phân biệt lỗi mapping của server. |
| Login người dùng thất bại | `invalidCredentials (49)` | 401 | Trả thông báo chung, tránh tiết lộ sự tồn tại của username. |
| Người gọi HTTP không có quyền thao tác | Authorization ở tầng API | 403 | Không cần thực hiện LDAP Modify. |
| Service account thiếu quyền LDAP | `insufficientAccessRights (50)` | 500 hoặc 503 tùy chính sách | Là lỗi tích hợp/cấu hình, không mặc định là 403 của người gọi. |
| Server bận/không sẵn sàng | `busy (51)`/`unavailable (52)` | 503 | Có thể retry theo chính sách nếu operation idempotent. |
| LDAP timeout | `timeLimitExceeded (3)`/network timeout | 503 hoặc 504 | Không trả danh sách Search một phần như đầy đủ. |
| Referral chưa được phép | `referral (10)` | 502/503 hoặc partial rõ ràng | Đích ngoài allowlist không được tự động theo. |
| Lỗi giao thức/Mapping không mong đợi | `protocolError (2)`/`other (80)` | 500/502 | Lưu thông tin kiểm toán nội bộ, response chung. |

`HTTP 403` thể hiện **người gọi không được phép**; `LDAP 50` thể hiện **LDAP Bind account đang dùng không đủ quyền**. Trong một API dùng service account cố định, đây không phải luôn là cùng người/danh tính.

### 10.2. Ví dụ handler ở tầng Spring MVC

`DirectoryErrorHandler.java`:

~~~java
package com.example.directory.web;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.ldap.NameAlreadyBoundException;
import org.springframework.ldap.NameNotFoundException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class DirectoryErrorHandler {

    public record ApiError(String code, String message) {}

    @ExceptionHandler(NameNotFoundException.class)
    public ResponseEntity<ApiError> missingEntry() {
        return ResponseEntity.status(HttpStatus.NOT_FOUND).body(
                new ApiError(
                        "DIRECTORY_ENTRY_NOT_FOUND",
                        "Directory entry was not found"));
    }

    @ExceptionHandler(NameAlreadyBoundException.class)
    public ResponseEntity<ApiError> duplicateEntry() {
        return ResponseEntity.status(HttpStatus.CONFLICT).body(
                new ApiError(
                        "DIRECTORY_ENTRY_EXISTS",
                        "Directory entry already exists"));
    }

    @ExceptionHandler(org.springframework.ldap.NamingException.class)
    public ResponseEntity<ApiError> unexpectedDirectoryError() {
        return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE).body(
                new ApiError(
                        "DIRECTORY_ERROR",
                        "Directory operation could not be completed"));
    }
}
~~~

**Giới hạn của ví dụ:** handler trên minh họa cách **không tiết lộ `ex.getMessage()`** và phân biệt lỗi tên cụ thể. `NamingException` là nhóm rộng; triển khai production phải phân loại chi tiết các exception về lỗi cấu hình, schema, authorization, timeout và network; không trả 503 cho **mọi** loại lỗi một cách máy móc. Nếu 404 do cấu hình search base sai, cũng không nên coi là lỗi dữ liệu do client.

Không dùng `@ExceptionHandler` để che lỗi mà không ghi log/metrics trong phạm vi nội bộ; response công khai và telemetry vận hành là hai kênh khác nhau.

## 11. Xử lý mã lỗi khi thực hiện CRUD

### 11.1. Create/Add

Khi tạo entry `inetOrgPerson`:

~~~java
import javax.naming.Name;
import javax.naming.directory.Attributes;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.BasicAttributes;

import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

public void addPerson(LdapTemplate template) {
    Name dn = LdapNameBuilder.newInstance("ou=people")
            .add("uid", "mai")
            .build();

    Attributes attrs = new BasicAttributes(true);
    BasicAttribute classes = new BasicAttribute("objectClass");
    classes.add("top");
    classes.add("person");
    classes.add("organizationalPerson");
    classes.add("inetOrgPerson");
    attrs.put(classes);

    attrs.put("uid", "mai");
    attrs.put("cn", "Tran Thi Mai");
    attrs.put("sn", "Tran");

    template.bind(dn, null, attrs);
}
~~~

Trong `LdapTemplate`, `bind(dn, null, attrs)` là **Add entry** (khác LDAP BindRequest dùng để xác thực). Những lỗi cần xét: `entryAlreadyExists (68)`, `noSuchObject (32)` nếu parent thiếu, `objectClassViolation (65)` nếu attributes không hợp schema và `insufficientAccessRights (50)` nếu tài khoản không có quyền tạo.

### 11.2. Modify

Một yêu cầu thay đúng thuộc tính `title`:

~~~java
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;

ModificationItem change = new ModificationItem(
        DirContext.REPLACE_ATTRIBUTE,
        new BasicAttribute("title", "Senior Developer")
);

ldapTemplate.modifyAttributes(
        dn, new ModificationItem[] { change });
~~~

Khi xóa một giá trị thuộc tính đa trị, hãy dùng `REMOVE_ATTRIBUTE` chỉ định **giá trị cần xóa**; đừng thay cả danh sách chỉ để xóa một phần tử. Các mã có thể gặp: `noSuchAttribute (16)`, `attributeOrValueExists (20)`, `constraintViolation (19)`, `invalidAttributeSyntax (21)`, `objectClassViolation (65)` hoặc `insufficientAccessRights (50)`.

### 11.3. Delete và Modify DN

Nếu Delete một OU vẫn còn người dùng con, server có thể báo `notAllowedOnNonLeaf (66)`. Nếu Rename đưa entry tới một DN đang tồn tại, có thể báo `entryAlreadyExists (68)`; nếu thay một phần tên vi phạm quy tắc schema hoặc quyền, có thể gặp `namingViolation (64)`, `notAllowedOnRDN (67)` hoặc `insufficientAccessRights (50)`.

**Lưu ý:** một operation LDAP được server chấp nhận không tạo ra transaction nhiều lệnh cho cả workflow Java. Khi thao tác qua nhiều entry, cần thiết kế idempotency, kiểm thử cạnh tranh và phương án đối soát. Cơ chế compensating transaction của Spring LDAP (nếu dùng) cũng **không đảm bảo ACID hoặc rollback trong mọi tình huống lỗi mạng**.

## 12. Khi lỗi xảy ra trước khi nhận LDAPResult

Không phải mọi lỗi mà Spring LDAP ném ra đều có mã `resultCode` từ server.

Ví dụ:

- Không phân giải được hostname LDAP.
- Kết nối TCP bị từ chối hoặc timeout trước khi có response.
- TLS handshake thất bại do CA chưa được tin cậy hoặc hostname không khớp.
- Kết nối bị đóng giữa khi request đang gửi.
- Hệ thống hết tài nguyên hoặc lỗi trong client/provider.

Trong các tình huống này, ứng dụng có thể nhận `CommunicationException`, lỗi SSL, timeout hoặc exception tầng thấp khác. **Không tự gán** chúng thành `LDAP 52` hay `LDAP 49` nếu server chưa thực sự gửi mã đó.

~~~mermaid
flowchart TD
    A["Gửi operation LDAP"] --> B{"Đã có LDAPResult hợp lệ?"}
    B -->|"Không"| C["Transport/TLS/DNS/client error"]
    B -->|"Có"| D["Đọc resultCode theo loại operation"]
    D --> E{"success / kết quả đặc biệt?"}
    E -->|"Có"| F["Xử lý dữ liệu hoặc Compare/SASL state"]
    E -->|"Không"| G["Phân loại schema, auth, ACL, limit, server"]
    C --> H["Không bịa mã LDAP; log loại lỗi kết nối"]
    G --> I["Xử lý an toàn, retry hoặc fail"]
~~~

### Timeout có nhiều lớp

- **Connection timeout:** thời gian kết nối ban đầu.
- **Read/socket timeout:** thời gian chờ dữ liệu trên kết nối.
- **LDAP server time limit:** giới hạn xử lý Search mà server áp dụng; có thể trả resultCode `3`.
- **Application deadline:** thời gian tối đa cho một yêu cầu HTTP/luồng nghiệp vụ.

Chúng không phải một thứ. Nếu người học chỉ cấu hình `LdapQueryBuilder.timeLimit(...)` mà không giới hạn connect/read timeout, API vẫn có nguy cơ treo trong một số lỗi mạng.

## 13. Retry an toàn và idempotency

Một chính sách “cứ gặp lỗi thì retry” đặc biệt nguy hiểm với thao tác ghi LDAP. Nếu kết nối mất **sau khi server đã Add thành công nhưng trước khi client nhận response**, lần retry thứ hai có thể nhận `entryAlreadyExists (68)`. Mã đó **không chứng minh** yêu cầu đầu thất bại; nó có thể là bằng chứng entry đã được tạo.

| Operation | Khi nào retry tương đối an toàn? | Bẫy cần tránh |
| --- | --- | --- |
| Search | Thường có thể retry khi gặp lỗi tạm thời, với limit và timeout. | Không coi kết quả partial là đầy đủ; thay đổi dữ liệu giữa các lần Search. |
| Compare | Có thể retry nếu chỉ đọc, không có side effect của hệ thống xung quanh. | Kết quả có thể đổi khi attribute được cập nhật. |
| Add | Chỉ retry có kiểm soát bằng request ID/idempotency hoặc kiểm tra trạng thái thực tế. | Lặp Add có thể trả mã 68. |
| Modify | Tùy thao tác và điều kiện; `REPLACE_ATTRIBUTE` đặt cùng giá trị có thể gần idempotent hơn `ADD_ATTRIBUTE`. | Thêm lặp có thể mã 20; thay đổi đồng thời có thể ghi đè dữ liệu khác. |
| Delete | Xem semantics nghiệp vụ: “đảm bảo không tồn tại” có thể xem 32 là trạng thái đã đạt. | Không mặc định mọi `noSuchObject` đều là thành công nếu base sai. |
| Modify DN | Cần kiểm tra tên nguồn/đích và tham chiếu. | Retry mù có thể chuyển/xung đột với DN khác. |

Với `busy (51)` hoặc `unavailable (52)`, có thể cân nhắc retry **giới hạn số lần**, exponential backoff và jitter. Không retry liên tục trên lỗi `invalidCredentials (49)`, `insufficientAccessRights (50)` hoặc schema violation (65): đó thường là vấn đề cần sửa cấu hình/dữ liệu, không tự hết sau một khoảng chờ.

## 14. Quy tắc bảo mật khi ghi và trả thông tin lỗi

Thông báo lỗi LDAP có thể chứa dữ liệu nhạy cảm. Khi phục vụ REST API, cần áp dụng ranh giới:

1. **Không lộ Bind DN, mật khẩu, địa chỉ nội bộ và diagnostic gốc** trong JSON công khai.
2. Dùng thông báo chung cho đăng nhập thất bại; tránh trả “tài khoản không tồn tại” khác biệt rõ với “mật khẩu sai”.
3. Với `LDAP 49`, không phản hồi các mã phụ của directory để người gọi suy ra trạng thái tài khoản.
4. Với `LDAP 50`, kiểm tra ACL bằng chính tài khoản dịch vụ; không nâng quyền admin chỉ để một API hoạt động.
5. Kết nối qua **LDAPS hoặc StartTLS hoàn tất trước Simple Bind**, xác minh chứng chỉ và hostname. Nếu server báo `strongerAuthRequired (8)` hoặc `confidentialityRequired (13)`, sửa cấu hình bảo mật thay vì hạ cấp.
6. Dùng `LdapQueryBuilder` hoặc filter class để encode **giá trị filter**; dùng `LdapNameBuilder` để escape **DN**. Hai chuẩn escaping khác nhau.
7. Với `referral (10)`, chỉ theo đích nằm trong chính sách cho phép, sử dụng credential riêng; không gửi secret hiện tại sang bất kỳ URL được trả về.
8. Hạn chế logging: có request ID, operation, mã/lớp lỗi, thời điểm và vùng dữ liệu; không ghi nguyên payload, mật khẩu, diagnostic hoặc thông tin định danh không cần thiết.

Ví dụ phản hồi công khai phù hợp:

~~~json
{
  "code": "DIRECTORY_UNAVAILABLE",
  "message": "Directory service is temporarily unavailable",
  "requestId": "req-test-1042"
}
~~~

`requestId` là mã do ứng dụng tạo để đối chiếu với log nội bộ, **không chứa DN/secret**. Người vận hành có thể tra mã đó để tìm exception class và các chi tiết được phép lưu.

## 15. Ma trận kiểm thử thực tế

Dành riêng một LDAP test server có schema `inetOrgPerson`, tài khoản đọc/ghi thử nghiệm, fixture `ou=people` và entry mẫu. Không tạo lỗi trên directory đang phục vụ đăng nhập của người dùng thật.

| Tình huống | Cách tạo | Mã/biểu hiện mong đợi | Điều phải assert |
| --- | --- | --- | --- |
| Search tìm thấy Lan | Filter `(uid=lan)` dưới OU đúng. | `success (0)`, có entry. | Mapping đúng thuộc tính. |
| Search không khớp | Filter `(uid=khongtontai)` dưới OU đúng. | `success (0)`, 0 entry. | Trả `[]`, không ném 404. |
| Search dưới OU không có | Base `ou=missing,...`. | Thường `noSuchObject (32)`. | Không coi là kết quả rỗng bình thường. |
| Sai mật khẩu Bind | Nhập mật khẩu sai ở test account. | Thường `invalidCredentials (49)`. | Không log secret; không brute force. |
| Account chỉ đọc cố Add | `ldapadd` hoặc `LdapTemplate.bind`. | Thường `insufficientAccessRights (50)`. | Không tăng quyền để test pass. |
| Tạo entry trùng | Add cùng DN đã tồn tại. | `entryAlreadyExists (68)`. | API trả conflict đúng ngữ cảnh. |
| Tạo `inetOrgPerson` thiếu `sn` | LDIF sai schema. | Thường `objectClassViolation (65)`. | Bắt lỗi schema, không retry. |
| Thêm thuộc tính chưa khai báo | Add/Modify loại thuộc tính lạ. | `undefinedAttributeType (17)`. | Phân biệt với input sai format. |
| Thêm giá trị đã có | Modify `ADD_ATTRIBUTE` giá trị trùng. | `attributeOrValueExists (20)`. | Xử lý idempotency phù hợp. |
| Xóa giá trị không tồn tại | Modify `REMOVE_ATTRIBUTE` sai giá trị. | `noSuchAttribute (16)` hoặc response server tương ứng. | Không thay cả thuộc tính đa trị. |
| Xóa OU có entry con | Delete `ou=people` còn người dùng. | `notAllowedOnNonLeaf (66)`. | Không xóa đệ quy ngoài ý định. |
| Search vượt giới hạn | Nạp đủ fixture, giới hạn size/time. | `sizeLimitExceeded (4)` hoặc `timeLimitExceeded (3)`. | Không tuyên bố kết quả đầy đủ. |
| Server dừng trước request | Tắt test directory tạm thời. | Lỗi kết nối; có thể không có LDAPResult. | Không bịa mã LDAP từ lỗi TCP. |
| Sai truststore | Dùng CA không tin cậy trên test server. | TLS handshake lỗi, có thể không có LDAPResult. | Không fallback plaintext. |
| Referral sang server khác | Thiết lập referral test. | `referral (10)` hoặc SearchResultReference. | Không tự chuyển secret. |
| Compare thuộc tính | Compare đúng/sai một giá trị. | `compareTrue (6)` hoặc `compareFalse (5)`. | Không coi 5/6 là lỗi hạ tầng. |

### 15.1. Unit test tầng service

Dùng mock `LdapTemplate` để kiểm tra:

- Search trả danh sách rỗng thì service giữ trạng thái “không khớp”.
- `NameNotFoundException` ở lookup được chuyển 404 **đúng use case**, không áp dụng cho mọi lỗi base.
- `NameAlreadyBoundException` ở create được chuyển 409.
- Exception LDAP không mong đợi được chuyển thành response chung không chứa `getMessage()`.
- Không gọi retry sau authentication/schema/ACL failure.

Unit test **không chứng minh** mã LDAP server sẽ trả ra, vì mock không thực thi schema, ACL hoặc giao thức. Cần thêm test tích hợp.

### 15.2. Kiểm thử tích hợp với directory

Dùng Docker/container hoặc server LDAP dành riêng cho test. Fixture tạo OU/người dùng/nhóm với thuộc tính hợp lệ; một tài khoản chỉ đọc và một tài khoản ghi giới hạn. Với các ca gây lỗi, dùng đúng Bind DN, lệnh/operation và trạng thái fixture để tránh nhận mã **khác do lỗi xảy ra sớm hơn**.

Ví dụ, để xác minh `objectClassViolation (65)`, account test phải **có quyền Add** vào OU. Nếu dùng account readonly, có thể chỉ nhận `insufficientAccessRights (50)`; đó là kết quả đúng nhưng không kiểm chứng được lỗi schema.

### 15.3. Kiểm tra tính nhất quán khi gặp lỗi giới hạn

Khi Search bị `sizeLimitExceeded` hoặc `timeLimitExceeded`, ứng dụng không được:

- Tự động coi danh sách vừa nhận là toàn bộ directory.
- Lưu danh sách đó vào cache với nhãn “đã đồng bộ xong”.
- Chuyển thành HTTP 200 không có cờ partial nếu sản phẩm cam kết đầy đủ.
- Tự tăng giới hạn vô hạn để “hết lỗi” khi chưa đánh giá index và resource server.

Nếu cần duyệt tập entry lớn, hãy nghiên cứu **Simple Paged Results Control** (nếu directory hỗ trợ), giới hạn scope/filter và cơ chế đồng bộ phù hợp; không tự giả định sizeLimit là phân trang.

## 16. Checklist vận hành để chẩn đoán lỗi

Khi nhận lỗi LDAP trong Spring Data LDAP, đi theo thứ tự:

1. **Operation nào thất bại?** Bind, Search, Add, Modify, Delete hay Modify DN?
2. **Có LDAPResult thực sự không?** Nếu chỉ là DNS/TLS/timeout, phân loại lỗi transport trước.
3. **Kết quả là thành công, special result hay failure?** Nhớ `5/6` của Compare và `14` của SASL Bind.
4. **DN gốc/đích có đúng?** Kiểm tra `spring.ldap.base`, `@Entry(base)`, `@Id`, search base/scope.
5. **Schema có phù hợp?** `objectClass`, `cn`/`sn`, attribute type, matching rule, giá trị đa trị.
6. **Danh tính Bind nào đang dùng?** Quyền Search khác quyền Modify; kiểm tra ACL bằng cùng account.
7. **Có referral hoặc partial result không?** Không bỏ qua đích khác hoặc dữ liệu thiếu.
8. **Có retry an toàn không?** Kiểm tra operation idempotent và trạng thái server trước khi thử lại.
9. **Thông tin lỗi có nhạy cảm không?** Chỉ log dữ liệu được phép, không trả diagnostic nguyên văn.
10. **Có test tái hiện được không?** Nếu là lỗi cấu hình, thêm test integration để ngăn tái xuất hiện.

~~~mermaid
flowchart TD
    A["Có lỗi khi gọi LDAP"] --> B{"Server đã trả LDAPResult?"}
    B -->|"Không"| C["Điều tra DNS, TCP, TLS, timeout"]
    B -->|"Có"| D{"Operation và resultCode?"}
    D -->|"success / compare / SASL step"| E["Xử lý theo semantics của operation"]
    D -->|"49 / 50"| F["Kiểm tra Bind identity, ACL"]
    D -->|"16–21 / 64–69"| G["Kiểm tra schema, DN, thuộc tính, trạng thái entry"]
    D -->|"3 / 4 / 11"| H["Đánh dấu partial, tối ưu Search"]
    D -->|"51 / 52"| I["Health/retry có giới hạn"]
    D -->|"10"| J["Chính sách referral / credential"]
    D -->|"Khác"| K["Log an toàn và điều tra server"]
    C --> L["HTTP response được chuẩn hóa"]
    E --> L
    F --> L
    G --> L
    H --> L
    I --> L
    J --> L
    K --> L
~~~

## 17. Câu hỏi tự đánh giá

1. `resultCode` khác `messageID` trong LDAPMessage ra sao?
2. Vì sao `SearchResultDone` với mã 0 vẫn có thể đi kèm danh sách kết quả rỗng?
3. Khi nào `noSuchObject (32)` phản ánh cấu hình search base sai thay vì “không có người dùng”?
4. `matchedDN` mang ý nghĩa gì và tại sao không nên đưa trực tiếp vào HTTP error?
5. `diagnosticMessage` có thể được parse bằng các chuỗi cố định để xác định nguyên nhân không?
6. Vì sao `compareFalse (5)` không nên coi như lỗi LDAP server?
7. `saslBindInProgress (14)` có nghĩa authentication đã thành công chưa?
8. `invalidCredentials (49)` khác `insufficientAccessRights (50)` ở điểm nào?
9. Tại sao Add cùng DN bị `68` nhưng Add một giá trị thuộc tính đã có có thể bị `20`?
10. Khi LDAP trả `sizeLimitExceeded (4)` sau vài `SearchResultEntry`, kết quả đó có hoàn chỉnh không?
11. Vì sao lỗi TLS handshake có thể không có `LDAPResult`?
12. Trong Spring LDAP, khi nào nên bắt `org.springframework.ldap.NameNotFoundException` thay vì JNDI checked exception?
13. Có nên chuyển mọi `LDAP 50` thành HTTP 403 không? Vì sao?
14. Nếu retry Add nhận `entryAlreadyExists (68)`, có thể kết luận thao tác trước chắc chắn thất bại không?
15. Vì sao một referral không được coi là đích đáng tin cậy để chuyển tiếp mật khẩu?

**Ghi nhớ:** `LDAPResult` cung cấp **`resultCode`**, `matchedDN`, `diagnosticMessage` và đôi khi `referral`; cách xử lý luôn phụ thuộc **loại thao tác**. Phân biệt Search rỗng với DN không tồn tại, xác thực với phân quyền, lỗi server với lỗi transport; trong Java, Spring LDAP thường đưa lỗi qua exception thay vì lộ raw mã số. HTTP API phải có hợp đồng lỗi riêng, không rò rỉ thông tin directory và không che giấu kết quả Search chưa đầy đủ.

### Tài liệu tham khảo

- [RFC 4511 — Lightweight Directory Access Protocol (LDAP): The Protocol](https://www.rfc-editor.org/rfc/rfc4511): cấu trúc LDAPResult, các resultCode và phản hồi của Bind/Search/Add/Modify/Delete/Compare.
- [RFC 4512 — LDAP: Directory Information Models](https://www.rfc-editor.org/rfc/rfc4512): DIT, DN, objectClass và schema.
- [RFC 4513 — LDAP Authentication Methods and Security Mechanisms](https://www.rfc-editor.org/rfc/rfc4513): Bind, xác thực và bảo vệ kết nối.
- [RFC 4515 — LDAP: String Representation of Search Filters](https://www.rfc-editor.org/rfc/rfc4515): filter, đặc biệt việc escape giá trị tìm kiếm.
- [RFC 4516 — LDAP: Uniform Resource Locator](https://www.rfc-editor.org/rfc/rfc4516): URL trong referral.
- [Spring LDAP Reference](https://docs.spring.io/spring-ldap/reference/): LdapTemplate, error translation và cấu hình ContextSource.
- [Spring LDAP – LdapTemplate API](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/LdapTemplate.html): Search, Bind/Modify và hoạt động của template.
- [Spring Data LDAP Reference](https://docs.spring.io/spring-data/ldap/reference/): repository và ODM mapping.
- [Java SE – NamingException](https://docs.oracle.com/en/java/javase/21/docs/api/java.naming/javax/naming/NamingException.html): JNDI exception, root cause, resolved/remaining name và explanation.
