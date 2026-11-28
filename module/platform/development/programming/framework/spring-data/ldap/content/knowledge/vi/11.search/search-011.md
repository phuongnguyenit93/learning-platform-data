# Kiểm tra quyền truy cập khi kết quả bị thiếu mà không có lỗi

Trong **SPRING_DATA_LDAP**, ứng dụng Java (các ví dụ Java dùng cú pháp Java 17+) truy cập directory qua Spring Data LDAP repository, Spring LDAP ODM và `LdapTemplate`. Các entry được tổ chức theo DN (*Distinguished Name*), `objectClass` và schema. Khi tìm kiếm, ứng dụng thường kỳ vọng một filter đúng sẽ trả về entry tương ứng; nhưng có tình huống LDAP trả về **success với danh sách rỗng**, hoặc trả entry nhưng thiếu một số attribute, dù dữ liệu vẫn tồn tại trong directory.

Nguyên nhân có thể là filter/base DN sai, search scope không phù hợp, dữ liệu thực sự không tồn tại, hoặc quyền ACL của Bind identity giới hạn những gì client được nhìn thấy. Một số directory chủ động che giấu sự tồn tại của entry/attribute: chúng xử lý giá trị bị cấm như thể nó không tồn tại. Khi đó ứng dụng không nhận được exception để phân biệt.

Ví dụ: entry của nhân viên Lan có attribute `mail`, nhưng tài khoản ứng dụng chỉ có quyền đọc `uid` và `cn`. Search có thể vẫn trả entry cùng các attribute được phép, trong khi `mail` không xuất hiện. Trong một số directory, filter `(mail=lan@example.org)` cũng có thể không tìm thấy entry vì giá trị `mail` bị xem như không tồn tại đối với danh tính hiện tại.

Bài học này giúp bạn phân biệt **không có kết quả** với **không có quyền nhìn thấy kết quả**, hiểu quyền search/read ở cấp entry và attribute, kiểm tra LDAP result code, chẩn đoán bằng Bind identity thực tế và viết kiểm thử ACL an toàn.

Sau bài này, bạn có thể:

- Giải thích vì sao LDAP Search có thể kết thúc bằng result code `success` nhưng trả zero entry.
- Phân biệt quyền nhìn thấy entry, dùng attribute trong filter và đọc giá trị attribute.
- Nhận biết hành vi che giấu attribute của Active Directory và mô hình quyền search/read của OpenLDAP.
- Hiểu cách `LdapTemplate.search()` và `searchForObject()` biểu diễn kết quả rỗng.
- Kiểm tra base DN, scope, filter, requested attributes, paging và Bind identity.
- So sánh kết quả giữa user cần chẩn đoán và tài khoản kiểm tra có quyền được phê duyệt.
- Kiểm thử các trường hợp thiếu quyền mà không làm lộ dữ liệu người dùng khác.

## 1. LDAP success không có nghĩa là mọi dữ liệu đều hiển thị

LDAP Search gồm một request và một chuỗi response. Server có thể gửi zero hoặc nhiều `SearchResultEntry`, sau đó gửi `SearchResultDone` chứa result code. Nếu không có entry nào phù hợp với request dưới góc nhìn của Bind identity hiện tại, server vẫn có thể kết thúc Search với `success (0)`.

```text
SearchRequest
  baseObject = ou=people,dc=example,dc=org
  scope      = wholeSubtree
  filter     = (&(objectClass=inetOrgPerson)(uid=lan))
  attributes = uid, cn, mail
       |
       v
LDAP server đánh giá filter và ACL
       |
       +-- SearchResultEntry (0 hoặc nhiều entry)
       |
       v
SearchResultDone: resultCode = success (0)
```

Result code `success` xác nhận thao tác giao thức đã kết thúc thành công theo cách server xử lý. Nó không chứng minh:

- Directory không chứa entry nào khác ngoài các entry đã trả.
- Bind identity có quyền liệt kê toàn bộ entry trong subtree.
- Mọi attribute được yêu cầu đều được phép đọc.
- Filter có thể sử dụng mọi attribute mà ứng dụng đưa vào.
- Server đã tìm kiếm trên mọi directory/server được tham chiếu.

RFC 4511 quy định Search được thực hiện **subject to access controls and other restrictions**. Một entry match filter chỉ được trả cùng những attribute được phép theo access control. Danh sách attribute trong `SearchResultEntry` thậm chí có thể rỗng nếu không có attribute nào được yêu cầu hoặc được phép trả về. Vì vậy, client cần đọc cả nội dung entry lẫn trạng thái hoàn tất Search, không suy luận quyền từ một danh sách kết quả đơn lẻ.

### 1.1. Hai dạng thiếu dữ liệu khác nhau

| Dấu hiệu ở client | Điều có thể xảy ra |
|---|---|
| Search trả `success`, zero entry | Không có entry match; base/scope/filter sai; entry bị che theo ACL; filter dùng attribute không nhìn thấy |
| Search trả entry nhưng thiếu `mail` | Attribute không tồn tại; không được yêu cầu; bị ACL ẩn; mapper/projection bỏ qua |
| Search trả entry nhưng attribute rỗng | Attribute không có value; value bị ACL che; request chỉ lấy type; server policy |
| Search ném lỗi quyền | Server từ chối rõ thao tác, ví dụ `insufficientAccessRights (50)` hoặc lỗi bảo mật được provider ánh xạ |
| Search trả partial result | Referral, time/size limit hoặc lỗi continuation; client có thể cấu hình bỏ qua một số exception |

**Không có một dấu hiệu duy nhất đủ để kết luận ACL.** Hãy xác minh request và identity trước, rồi kiểm tra quyền theo từng lớp.

### 1.2. LDAP filter có thể đánh giá thành Undefined

RFC 4511 yêu cầu server đánh giá filter theo logic ba giá trị: `TRUE`, `FALSE` hoặc `Undefined`.

- `TRUE`: entry match filter; entry có thể được đưa vào kết quả, subject to ACL.
- `FALSE`: entry không match và bị bỏ qua.
- `Undefined`: server không thể xác định phép so sánh, ví dụ attribute type/matching rule không được nhận biết hoặc assertion value không hợp lệ; entry bị bỏ qua.

Với một số lỗi về attribute description, matching rule hoặc assertion syntax, RFC quy định server **không trả lỗi LDAP** mà đánh giá filter thành `Undefined`. Đây là một lý do filter sai hoặc không tương thích có thể tạo kết quả rỗng mà không có exception.

Ngoài ra, một số server còn áp dụng ACL khi đánh giá filter. Active Directory là ví dụ rõ ràng: attribute không có quyền đọc có thể được xử lý như thể attribute đó không tồn tại, kể cả khi attribute được dùng trong filter. Không được khái quát hành vi riêng của AD thành quy tắc giống hệt cho mọi LDAP server.

## 2. Phân biệt quyền trên entry và attribute

Quyền LDAP không phải một cờ `canReadDirectory` duy nhất. Server có thể quyết định độc lập liệu một Bind identity có được:

- Nhìn thấy entry trong cây directory.
- Dùng attribute làm điều kiện filter.
- Đọc giá trị attribute được trả về.
- So sánh một giá trị với attribute bằng LDAP Compare.
- Sửa attribute hoặc rename/delete entry.

Do đó, có thể xảy ra trường hợp user được nhìn thấy một entry nhưng không được đọc một số thuộc tính; hoặc được dùng một thuộc tính trong filter nhưng không được lấy giá trị của nó.

### 2.1. OpenLDAP: search và read là hai quyền khác nhau

OpenLDAP định nghĩa các access level trong ACL. Các quyền quan trọng với bài này:

| Access level | Ý nghĩa |
|---|---|
| `disclose` | Được tiết lộ thông tin về entry trong một số lỗi |
| `auth` | Được dùng giá trị attribute để xác thực Bind |
| `compare` | Được dùng cho LDAP Compare |
| `search` | Được dùng attribute trong search filter |
| `read` | Được đọc giá trị attribute trong kết quả |
| `write` | Được sửa/rename theo phạm vi quyền |
| `manage` | Quyền quản trị cao hơn |

Các mức là tích lũy theo thứ tự: `read` bao gồm các quyền thấp hơn như `search`, `compare`, `auth` và `disclose`. Nhưng cấp `search` không tự cấp quyền `read`.

Ví dụ ACL minh họa cho attribute `mail`:

```text
olcAccess: to attrs=mail
  by self read
  by users search
  by * none
```

Trong ví dụ, người dùng đã xác thực có thể dùng `mail` trong filter, nhưng không được đọc giá trị `mail` của entry người khác. Chủ thể của entry (`self`) có quyền đọc. Đây chỉ là một rule minh họa; ACL thực tế còn phụ thuộc thứ tự rule, target, scope, các rule trước đó và cấu hình database.

Với OpenLDAP, khi kiểm tra một search không có kết quả, hãy xem cả:

- Quyền search trên entry/nhánh cần duyệt.
- Quyền `search` đối với attribute xuất hiện trong filter.
- Quyền `read` đối với attribute cần trả về.
- Quyền `disclose` có ảnh hưởng đến thông tin lỗi hay không.

### 2.2. Active Directory: attribute bị ẩn có thể được coi là không tồn tại

Active Directory áp dụng access check theo security descriptor. Theo đặc tả MS-ADTS:

- Để object được hiển thị trong search, thông thường requester cần `RIGHT_DS_LIST_CONTENTS` trên parent object.
- Để đọc một attribute, requester thông thường cần `RIGHT_DS_READ_PROPERTY` trên attribute hoặc property set tương ứng của object.
- Nếu không có quyền đọc, giá trị attribute có thể được xử lý như **không tồn tại** trong danh sách attribute trả về và trong LDAP filter.

Ví dụ:

```text
Entry:
  uid = lan
  cn  = Lan Nguyen
  mail = lan@example.org

Bind identity có quyền:
  đọc uid, cn
  không có READ_PROPERTY trên mail

Search filter:
  (&(objectClass=inetOrgPerson)(mail=lan@example.org))

Kết quả có thể thấy:
  success, 0 entries
```

Ở đây entry vẫn tồn tại, nhưng server xử lý `mail` như thể không có đối với requester. Quyền cụ thể có thể chịu ngoại lệ do special attributes, search flags, property sets và cấu hình AD; hãy kiểm tra tài liệu/ACL của đúng thuộc tính và object.

**Hệ quả:** thử `mail=*` hoặc equality filter với một địa chỉ email không phải cách đáng tin cậy để xác minh sự tồn tại của entry nếu caller không có quyền đọc/search attribute đó.

### 2.3. Quyền search không đồng nghĩa quyền đọc

| Tình huống | OpenLDAP (mô hình ACL) | Active Directory (mô hình access check phổ biến) |
|---|---|---|
| Có quyền nhìn thấy entry | Phụ thuộc quyền trên entry/nhánh | Thường cần LIST_CONTENTS trên parent |
| Có quyền dùng attribute trong filter | `search` trên attribute | Thường gắn với khả năng đọc/được phép search attribute theo AD access check |
| Có quyền trả giá trị attribute | `read` trên attribute | `READ_PROPERTY` trên attribute/property set |
| Thiếu quyền đọc attribute | Có thể trả entry nhưng bỏ attribute | Giá trị được coi như không tồn tại trong kết quả và filter |
| Thiếu quyền rõ ràng cho operation | Có thể trả insufficient access hoặc che theo ACL | Có thể trả lỗi hoặc che tùy operation/security policy |

Hãy luôn phân biệt quyền theo sản phẩm directory. Không copy ACL OpenLDAP sang AD hoặc suy luận ACL AD từ tên access level của OpenLDAP.

## 3. Những nguyên nhân khác cũng tạo kết quả rỗng

Trước khi kết luận ACL, hãy loại trừ lỗi request. LDAP Search có nhiều thành phần; chỉ cần một thành phần khác với dữ liệu thực tế là kết quả có thể rỗng.

| Thành phần | Câu hỏi cần kiểm tra |
|---|---|
| Base DN | DN có đúng spelling, escaping và naming context không? |
| Search scope | Có đang dùng BASE/ONELEVEL trong khi entry nằm sâu hơn không? |
| Filter | Attribute name, objectClass, matching rule và assertion value có đúng không? |
| Requested attributes | Client có thực sự yêu cầu attribute cần đọc không? |
| Bind identity | ContextSource đã Bind bằng DN nào, anonymous hay service account? |
| Search controls | Có `typesOnly`, count limit, time limit, paging/sort controls không? |
| Referral | Entry nằm ở naming context/server khác có được tiếp tục search không? |
| Directory replica | Query đang đi tới DC/replica nào; dữ liệu đã replicate chưa? |

### 3.1. Base DN và scope

Ba scope thường gặp:

- `BASE`: chỉ tìm chính entry tại base DN.
- `ONELEVEL`: chỉ tìm các entry con trực tiếp.
- `SUBTREE`: tìm base và toàn bộ cây con.

Ví dụ entry:

```text
dc=example,dc=org
└── ou=people
    └── ou=engineering
        └── uid=lan
```

Search base `ou=people,dc=example,dc=org` với `ONELEVEL` không trả `uid=lan` vì entry nằm dưới `ou=engineering`. Với cùng filter, `SUBTREE` có thể tìm thấy entry nếu ACL cho phép.

Đừng tự động đổi mọi search sang `SUBTREE` để "sửa" kết quả rỗng. Scope rộng hơn có thể làm lộ hoặc đọc nhiều entry hơn dự kiến, tăng tải server và thay đổi phạm vi nghiệp vụ. Chọn base/scope theo đúng ranh giới OU và quyền được cấp.

### 3.2. Filter và matching rule

Kiểm tra từng assertion của filter. Ví dụ:

```text
(&(objectClass=inetOrgPerson)(uid=lan))
(&(objectClass=person)(uid=lan))
(&(objectClass=inetOrgPerson)(mail=lan@example.org))
```

Các filter này không tương đương. Entry có thể mang `inetOrgPerson` nhưng không có objectClass hoặc attribute mà ứng dụng giả định. Giá trị chuỗi còn chịu matching rule của schema: `caseIgnoreMatch`, `caseExactMatch`, matching rule theo locale hoặc quy tắc riêng của server.

Nếu filter dùng một attribute bị ACL che, server có thể coi assertion như false/undefined. Do đó, thử filter rộng hơn chỉ để kiểm tra sự tồn tại cần được thực hiện bằng identity chẩn đoán có quyền phù hợp, không phải bằng cách mở quyền cho mọi request.

### 3.3. Requested attributes và mapper

LDAP Search chỉ trả các attribute được yêu cầu và được phép trả. Nếu `SearchControls` yêu cầu riêng `uid` và `cn`, việc `mail` không xuất hiện trong `Attributes` là bình thường:

```java
SearchControls controls = new SearchControls();
controls.setSearchScope(SearchControls.SUBTREE_SCOPE);
controls.setReturningAttributes(new String[]{"uid", "cn"});
```

Khi dùng `LdapTemplate.search` với danh sách attribute, đối số `attrs` xác định projection. Giá trị `null` thường có nghĩa yêu cầu tất cả attribute mà server cho phép trả, nhưng điều đó vẫn chịu ACL và policy của server. Không nên dùng `null` như một cách vượt qua quyền.

Trong mapper:

```java
AttributesMapper<PersonSummary> mapper = attributes -> {
    Attribute uidAttribute = attributes.get("uid");
    Attribute mailAttribute = attributes.get("mail");

    String uid = uidAttribute == null
            ? null
            : (String) uidAttribute.get();

    String mail = mailAttribute == null
            ? null
            : (String) mailAttribute.get();

    return new PersonSummary(uid, mail);
};
```

Nếu `mailAttribute == null`, mapper chỉ biết rằng attribute không có trong payload nhận được. Nó không thể tự phân biệt:

- Entry thực sự không có `mail`.
- Search không yêu cầu `mail`.
- Server ẩn `mail` vì ACL.
- Một mapper/projection ở tầng khác đã bỏ `mail`.

Đừng chuyển mọi trường hợp này thành chuỗi rỗng `""`; giữ trạng thái thiếu rõ ràng để tầng nghiệp vụ quyết định.

### 3.4. Time limit, size limit và paging

Một search lớn có thể bị giới hạn bởi client hoặc server:

- `sizeLimit`: giới hạn số entry tối đa.
- `timeLimit`: giới hạn thời gian search.
- Paged results: phải tiếp tục lấy các page cho đến khi cookie kết thúc.
- Referral/continuation: có thể cần tiếp tục ở server khác.

LDAP có result code riêng cho `sizeLimitExceeded (4)` và `timeLimitExceeded (3)`. Một số cấu hình Spring LDAP có thể bỏ qua một số exception giới hạn/partial result; khi đó ứng dụng có nguy cơ chỉ nhận phần đã đọc được. Hãy kiểm tra cấu hình `LdapTemplate`, log và response controls trước khi gọi kết quả là đầy đủ.

## 4. Spring LDAP biểu diễn kết quả thiếu như thế nào?

### 4.1. Search trả List rỗng

`LdapTemplate.search(query, mapper)` trả danh sách các entry đã được nhận và map. Nếu server trả SearchDone success nhưng không có entry nào nhìn thấy/match, kết quả thường là list rỗng:

```java
import java.util.List;

import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.SearchScope;

import static org.springframework.ldap.query.LdapQueryBuilder.query;

record PersonSummary(String uid, String cn, String mail) {}

class PersonDirectory {
    private final LdapTemplate ldapTemplate;

    PersonDirectory(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<PersonSummary> findPeople(String uid) {
        LdapQuery ldapQuery = query()
                .base("ou=people")
                .searchScope(SearchScope.SUBTREE)
                .attributes("uid", "cn", "mail")
                .where("objectClass").is("inetOrgPerson")
                .and("uid").is(uid);

        AttributesMapper<PersonSummary> mapper = attributes -> {
            String foundUid = attributes.get("uid") == null
                    ? null
                    : (String) attributes.get("uid").get();
            String cn = attributes.get("cn") == null
                    ? null
                    : (String) attributes.get("cn").get();
            String mail = attributes.get("mail") == null
                    || attributes.get("mail").size() == 0
                    ? null
                    : (String) attributes.get("mail").get();
            return new PersonSummary(foundUid, cn, mail);
        };

        return ldapTemplate.search(ldapQuery, mapper);
    }
}
```

Khi list rỗng, chỉ có thể kết luận **không có entry nào được trả cho request này**. Không được kết luận chắc chắn user không tồn tại hoặc caller không có quyền.

Trong ví dụ, mapper nhận `mail == null` nếu giá trị không có trong payload. Nó không nhận metadata giải thích server đã ẩn attribute hay attribute chưa từng được lưu.

### 4.2. Search một entry duy nhất

`searchForObject()` và `searchForContext()` yêu cầu đúng một kết quả. Theo API hiện hành, Spring LDAP ném `IncorrectResultSizeDataAccessException` nếu không có entry hoặc có nhiều hơn một entry.

Nếu server che entry do ACL, phía ứng dụng vẫn có thể nhận `IncorrectResultSizeDataAccessException` như trường hợp không có entry match. Exception này mô tả cardinality của kết quả mà client nhìn thấy, không phải bằng chứng về sự tồn tại toàn cục hoặc quyết định ACL.

Không bắt `IncorrectResultSizeDataAccessException` rồi chuyển thành "access denied" nếu chưa có bằng chứng. Cũng không bắt nó rồi tự động chạy lại cùng query bằng tài khoản admin.

### 4.3. NameNotFoundException có thể được hiểu là không có kết quả

Javadoc `LdapTemplate.search(SearchExecutor, ...)` ghi rõ `NameNotFoundException` có thể được bỏ qua và diễn giải là không có entry được tìm thấy. Trong Spring LDAP hiện hành, `ignoreNameNotFoundException` mặc định là `false`; nếu ứng dụng bật thành `true`, base DN sai/không tìm thấy có thể biểu hiện như danh sách rỗng. Các phiên bản cũ có thể có default khác, vì vậy hãy kiểm tra phiên bản và cấu hình thực tế.

Trong chẩn đoán, hãy xác minh base DN bằng một thao tác phù hợp và identity được phép kiểm tra. Nếu ứng dụng cần phân biệt base không tồn tại với kết quả rỗng, xem cấu hình `ignoreNameNotFoundException` của phiên bản Spring LDAP đang dùng và kiểm thử hành vi sau khi thay đổi. Đừng bật lỗi này một cách mù quáng nếu hệ thống phụ thuộc vào cách xử lý referral/AD hiện tại.

### 4.4. Khi server từ chối rõ ràng

LDAP result code `insufficientAccessRights (50)` cho biết requester không đủ quyền thực hiện operation. JNDI provider và Spring LDAP có thể ánh xạ lỗi bảo mật sang exception runtime trong hierarchy của Spring LDAP, ví dụ `NoPermissionException` hoặc `NamingSecurityException`, tùy exception gốc và provider.

Nhưng không phải mọi ACL đều được biểu diễn bằng result code 50. Directory có thể:

- Ẩn entry hoặc attribute và trả Search success.
- Thay lỗi quyền bằng lỗi khác để tránh tiết lộ sự tồn tại của entry.
- Trả `noSuchObject (32)` khi không muốn xác nhận target.
- Trả `insufficientAccessRights (50)` khi quyết định từ chối operation một cách rõ ràng.

RFC 4511 lưu ý result code có thể được thay thế để ngăn tiết lộ trái phép, ví dụ thay `insufficientAccessRights` bằng `noSuchObject`. Diagnostic message cũng không phải giao diện chuẩn để ứng dụng suy luận ACL; nội dung có thể khác theo server/version.

### 4.5. Các cờ bỏ qua exception có thể làm kết quả trông đầy đủ hơn thực tế

Spring LDAP hiện hành cung cấp các cờ:

| Property | Default hiện hành | Ảnh hưởng |
|---|---:|---|
| `ignoreNameNotFoundException` | false | Nếu bật, `NameNotFoundException` do base không tìm thấy được coi như không có entry |
| `ignorePartialResultException` | false | Nếu bật, `PartialResultException` bị bỏ qua; có thể mất kết quả ở referral |
| `ignoreSizeLimitExceededException` | true | Nếu bật, `SizeLimitExceededException` bị bỏ qua; list có thể chỉ chứa phần entry đã đọc |

Đặc biệt với Active Directory, `PartialResultException` có thể xuất hiện do server không xử lý referral tự động như client mong đợi. Bật `ignorePartialResultException` có thể giúp query chạy tiếp, nhưng cũng có nghĩa referral bị bỏ qua và không có bảo đảm đã tìm hết các naming context.

Ví dụ cấu hình Java để làm lỗi rõ ràng trong một môi trường chẩn đoán:

```java
LdapTemplate diagnosticTemplate = new LdapTemplate(contextSource);
diagnosticTemplate.setIgnoreNameNotFoundException(false);
diagnosticTemplate.setIgnorePartialResultException(false);
diagnosticTemplate.setIgnoreSizeLimitExceededException(false);
```

Đây là cấu hình để **phát hiện vấn đề khi chẩn đoán**. Trước khi áp dụng vào production, kiểm tra tác động với AD referral, paging và count limit. Nếu nghiệp vụ chủ ý dùng count limit để lấy top-N kết quả, việc bỏ qua size-limit exception có thể là quyết định có chủ đích; khi đó API phải thể hiện rõ đây là kết quả giới hạn, không phải danh sách đầy đủ.

## 5. Quy trình chẩn đoán theo từng lớp

Mục tiêu chẩn đoán là xác định request bị lệch ở đâu mà không mở rộng quyền cho người dùng cuối. Hãy làm theo thứ tự dưới đây để tránh nhầm lỗi filter với lỗi ACL.

### Bước 1: xác nhận Bind identity thực tế

Ghi nhận:

- LDAP endpoint/host và port mà ứng dụng đang dùng.
- Bind DN hoặc authentication mechanism được cấu hình trong `ContextSource`.
- Ứng dụng đang dùng service account, user Bind, SASL hay proxy authorization.
- Pool/connection có thể tái sử dụng context đã Bind bằng identity trước đó hay không.
- Base DN mặc định và các environment property ảnh hưởng đến kết nối.

Có thể dùng `ldapwhoami` để kiểm tra một lần Bind bằng credential tương ứng:

```bash
ldapwhoami -x -H ldaps://ldap.example.org:636 \
  -D "uid=lan,ou=people,dc=example,dc=org" -W
```

Lệnh trả về authorization identity của Bind nếu server hỗ trợ Who Am I extended operation. Nó giúp xác nhận credential đã dùng cho phép thử. Tuy nhiên, chạy lệnh riêng không chứng minh một connection đã nằm trong pool của ứng dụng đang mang cùng identity. Với ứng dụng dùng pool hoặc proxy authorization, hãy kiểm tra identity của chính connection/application path theo cơ chế server hỗ trợ và cấu hình ContextSource thực tế.

Không ghi password, bind token hoặc toàn bộ SecurityContext vào log. Chỉ log loại principal đã được kiểm soát, ví dụ `SERVICE_ACCOUNT` hoặc mã actor đã pseudonymize.

### Bước 2: cố định toàn bộ SearchRequest

Trước khi so sánh quyền, ghi lại cùng một bộ tham số:

| Tham số | Ví dụ |
|---|---|
| Endpoint | `ldaps://ldap.example.org:636` |
| Base DN | `ou=people,dc=example,dc=org` |
| Scope | `sub` |
| Filter | `(&(objectClass=inetOrgPerson)(uid=lan))` |
| Attributes | `uid cn mail` |
| Referral policy | follow/ignore/throw theo cấu hình hiện tại |
| Limits | client/server size limit và time limit |
| Paging/sort | request controls và trạng thái cookie |

Đừng so sánh hai kết quả nếu một lệnh dùng `SUBTREE`, lệnh kia dùng `ONELEVEL`; hoặc một lệnh trả tất cả attribute còn lệnh kia chỉ trả `uid`. Những khác biệt này làm kết quả không còn đối chiếu được.

### Bước 3: chạy cùng SearchRequest bằng Bind identity của ứng dụng

Ví dụ OpenLDAP command-line client:

```bash
ldapsearch -LLL -x -H ldaps://ldap.example.org:636 \
  -D "uid=lan,ou=people,dc=example,dc=org" -W \
  -b "ou=people,dc=example,dc=org" -s sub \
  "(&(objectClass=inetOrgPerson)(uid=lan))" \
  uid cn mail
```

`-W` yêu cầu nhập password tương tác, tránh để password xuất hiện trong command history hoặc process list. Dùng đúng endpoint, base, scope, filter và attribute projection như ứng dụng.

### Bước 4: so sánh bằng tài khoản chẩn đoán được phê duyệt

Nếu chính sách tổ chức cho phép, chạy **cùng request** bằng một tài khoản chẩn đoán có quyền xem entry/attribute cần kiểm tra:

```bash
ldapsearch -LLL -x -H ldaps://ldap.example.org:636 \
  -D "cn=ldap-audit,ou=service,dc=example,dc=org" -W \
  -b "ou=people,dc=example,dc=org" -s sub \
  "(&(objectClass=inetOrgPerson)(uid=lan))" \
  uid cn mail
```

Tài khoản chẩn đoán chỉ dùng trong quy trình vận hành có kiểm soát; không cấp credential này cho ứng dụng và không dùng nó làm fallback tự động khi query của user rỗng.

Diễn giải:

| Identity ứng dụng | Identity chẩn đoán | Khả năng cần kiểm tra |
|---|---|---|
| Có entry | Có entry | Request có thể đúng; kiểm tra attribute projection/ACL của từng field |
| Không có entry | Có entry | ACL, Bind identity, search permission hoặc attribute trong filter là nghi vấn chính |
| Có entry, thiếu `mail` | Có entry, có `mail` | Attribute-level read permission là nghi vấn chính |
| Không có entry | Không có entry | Base/filter/scope, dữ liệu, replica, referral hoặc cả hai identity đều không có quyền |
| Khác nhau theo server | Khác nhau theo server | Replication, Global Catalog, referral hoặc naming context có thể khác |

Kết quả chênh lệch là **bằng chứng định hướng**, không phải kết luận tự động. Đảm bảo cả hai lệnh chạy cùng server/replica và cùng request trước khi quy lỗi cho ACL.

### Bước 5: tách kiểm tra entry, filter và attribute

Khi có một DN test đã biết và được phép dùng trong môi trường kiểm thử, thực hiện các phép thử tách biệt:

1. Search entry theo một thuộc tính định danh mà caller được phép dùng.
2. Trả về `uid`/`cn` trước, sau đó yêu cầu riêng attribute đang thiếu.
3. Thử dùng attribute nghi vấn trong filter, rồi so sánh với filter dùng attribute khác mà caller được phép search.
4. Nếu directory hỗ trợ, dùng Compare operation chỉ trong bài kiểm thử ACL được phê duyệt để xác định quyền compare; không biến Compare thành API dò sự tồn tại của dữ liệu.
5. Đối chiếu kết quả với server-side ACL/effective access.

Ví dụ ma trận:

| Search/filter | Attribute trả về | Điều cần tách |
|---|---|---|
| `(uid=lan)` | `uid cn` | Entry có nhìn thấy được không? |
| `(uid=lan)` | `uid cn mail` | Có quyền đọc `mail` không? |
| `(mail=lan@example.org)` | `uid` | Có quyền dùng `mail` trong filter không? |
| `(objectClass=inetOrgPerson)` | `uid` | Search scope/entry visibility có phù hợp không? |

Chỉ dùng DN test và dữ liệu giả trong môi trường thử nghiệm. Trong production, không tạo hàng loạt query để suy đoán attribute nhạy cảm của user khác.

## 6. Kiểm tra ACL theo sản phẩm directory

### 6.1. OpenLDAP: dùng slapacl

OpenLDAP cung cấp `slapacl` để đánh giá ACL của server đối với một authentication DN và target entry cụ thể. Ví dụ:

```bash
slapacl -F /etc/ldap/slapd.d \
  -D "uid=lan,ou=people,dc=example,dc=org" \
  -b "uid=target,ou=people,dc=example,dc=org" \
  "entry/search" "mail/search" "mail/read"
```

Trong lệnh:

- `-D` là authentication DN giả định để chọn nhánh `by` trong ACL.
- `-b` là DN của entry đích đang kiểm tra.
- `entry/search` kiểm tra quyền search trên entry pseudo-attribute.
- `mail/search` kiểm tra quyền dùng `mail` trong filter.
- `mail/read` kiểm tra quyền đọc giá trị `mail`.

Đường dẫn `-F` phải trỏ tới config directory của đúng instance OpenLDAP. `slapacl` cần chạy trên máy chủ hoặc môi trường có quyền đọc cấu hình directory; nó đánh giá rule hiện có, không thay đổi ACL. Nếu ACL phụ thuộc peername, TLS, SASL SSF, proxy authorization hoặc dữ liệu của object khác, phải cung cấp/kiểm tra các yếu tố đó vì một phép thử đơn giản có thể không mô phỏng đủ phiên thực tế.

Kiểm tra thứ tự `olcAccess`: rule đầu tiên phù hợp có thể quyết định kết quả. Một rule `to attrs=mail` ở phía sau không có tác dụng nếu một rule trước đó đã match rộng hơn. Cũng cần xem ACL ở entry/nhánh cha, không chỉ ACL cho attribute.

### 6.2. Active Directory: kiểm tra quyền trên parent và property

Trong AD, kiểm tra Security Descriptor và quyền hiệu lực ở cả object cha lẫn object đích:

- `List Contents` trên parent/naming context để object có thể xuất hiện trong search.
- Nếu môi trường bật cơ chế `List Object` qua heuristic `fDoListObject`, kiểm tra thêm `RIGHT_DS_LIST_OBJECT` trên object; AD không thực thi quyền này theo mặc định.
- `Read Property` trên attribute hoặc property set chứa attribute.
- Quyền có được kế thừa từ OU không; inheritance có bị chặn hay không.
- Attribute có thuộc nhóm special attributes hoặc có search flags/dSHeuristics làm thay đổi access check không.
- Ứng dụng đang query domain controller nào; query Global Catalog có thể trả tập attribute khác với domain LDAP endpoint.

Dùng công cụ quản trị AD được tổ chức phê duyệt (ví dụ Advanced Security Settings/Effective Access hoặc công cụ kiểm tra security descriptor) để đánh giá quyền của đúng principal trên đúng object. Không chỉ nhìn thấy một ACE trong danh sách rồi kết luận user có quyền: cần tính cả deny ACE, group membership, inheritance, property set và security context thực tế.

### 6.3. Không sửa ACL chỉ để làm biến mất triệu chứng

Khi tìm ra thiếu quyền, xác định chính xác thao tác nghiệp vụ cần:

- Search/list entry?
- Dùng attribute nào trong filter?
- Đọc attribute nào?
- Compare hay modify?

Chỉ cấp quyền tối thiểu cho đúng principal, target và attribute. Ví dụ, nếu ứng dụng chỉ cần lọc theo `mail` nhưng không cần hiển thị địa chỉ, có thể chính sách cho phép search mà không cấp read trên attribute trong một số cấu hình OpenLDAP. Với AD, hãy xác minh hành vi và quyền thực tế theo access check của AD.

Không cấp quyền `read` rộng trên toàn subtree nếu ứng dụng chỉ cần một vài attribute. Không cấp `GenericAll`/quyền quản trị để chữa một lỗi search.

## 7. Kiểm thử quyền và kết quả bị che

Một embedded LDAP server mặc định có thể không mô phỏng đầy đủ ACL của OpenLDAP hoặc Active Directory. Với chủ đề này, integration test phải dùng directory test có ACL tương đương môi trường triển khai.

### 7.1. Chuẩn bị dữ liệu test

Tạo hai người dùng và một tài khoản kiểm tra có quyền rộng hơn trong **directory test riêng**:

```text
dc=example,dc=org
└── ou=people
    ├── uid=lan
    │   ├── objectClass: inetOrgPerson
    │   ├── uid: lan
    │   ├── cn: Lan Nguyen
    │   └── mail: lan@example.org
    └── uid=binh
        ├── objectClass: inetOrgPerson
        ├── uid: binh
        ├── cn: Binh Tran
        └── mail: binh@example.org
```

Đặt ACL khác nhau cho `lan`, `binh` và `ldap-audit`. Ví dụ:

- `lan` nhìn thấy `uid` và `cn`; `mail` không được đọc.
- `binh` được đọc `uid`, `cn`, `mail`.
- `ldap-audit` có quyền chẩn đoán đã được phê duyệt trên các entry test.

Nếu dùng OpenLDAP, có thể tạo rule test để user có quyền `search` trên `mail` nhưng không có `read`, từ đó chứng minh filter và attribute return là hai quyền khác nhau. Nếu dùng AD, tạo ACL test để một user thiếu `READ_PROPERTY` trên `mail`; xác minh hành vi filter theo đặc tả AD trên đúng phiên bản server.

### 7.2. Integration test bằng hai Bind identity

Ví dụ kiểm thử khái niệm với hai `LdapTemplate` đã cấu hình `ContextSource` riêng cho user và diagnostic account:

```java
import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.ldap.query.LdapQueryBuilder.query;

import org.junit.jupiter.api.Test;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.SearchScope;

class DirectoryVisibilityIntegrationTest {

    private final LdapTemplate lanTemplate;
    private final LdapTemplate auditTemplate;

    DirectoryVisibilityIntegrationTest(
            LdapTemplate lanTemplate,
            LdapTemplate auditTemplate) {
        this.lanTemplate = lanTemplate;
        this.auditTemplate = auditTemplate;
    }

    @Test
    void comparesVisibleResultsForSameSearchRequest() {
        LdapQuery sameQuery = query()
                .base("ou=people")
                .searchScope(SearchScope.SUBTREE)
                .attributes("uid", "cn", "mail")
                .where("objectClass").is("inetOrgPerson")
                .and("uid").is("lan");

        var lanResults = lanTemplate.search(
                sameQuery, attrs -> attrs.get("uid").get());
        var auditResults = auditTemplate.search(
                sameQuery, attrs -> attrs.get("uid").get());
        var lanMail = lanTemplate.search(
                sameQuery, attrs -> attrs.get("mail") == null
                        || attrs.get("mail").size() == 0
                        ? "<hidden-or-absent>"
                        : attrs.get("mail").get().toString());
        var auditMail = auditTemplate.search(
                sameQuery, attrs -> attrs.get("mail") == null
                        || attrs.get("mail").size() == 0
                        ? "<hidden-or-absent>"
                        : attrs.get("mail").get().toString());

        // Kỳ vọng này chỉ đúng với ACL test đã thiết kế:
        assertThat(auditResults).containsExactly("lan");
        assertThat(lanResults).containsExactly("lan");
        assertThat(lanMail).containsExactly("<hidden-or-absent>");
        assertThat(auditMail).containsExactly("lan@example.org");
    }
}
```

Ví dụ trên minh họa kiểm tra **entry visibility** khi ACL vẫn cho phép Lan nhìn thấy entry. Nếu test cần mô phỏng object-level hiding, thay assertion của `lanResults` theo chính sách ACL của directory test, ví dụ empty list. Không dùng một assertion chung cho mọi sản phẩm LDAP: OpenLDAP ACL và AD access check có thể biểu diễn cùng một hạn chế theo cách khác nhau.

### 7.3. Test attribute-level visibility

Với ACL cho phép user nhìn thấy entry nhưng không đọc `mail`, kiểm tra:

1. Search theo `uid=lan` trả entry.
2. Mapper đọc được `uid` và `cn`.
3. `Attributes.get("mail")` là `null` hoặc không chứa giá trị theo hành vi server.
4. Search filter theo `mail` cho kết quả phù hợp với quyền `search`/access check của server.
5. Cùng request bằng diagnostic identity trả `mail` nếu ACL test cho phép.

Với OpenLDAP, nếu user có `mail/search` nhưng không có `mail/read`, filter có thể match nhưng giá trị không được trả. Với AD, nếu user không có quyền đọc attribute, filter có thể hành xử như attribute không tồn tại. Test phải phản ánh đúng server đang chạy.

### 7.4. Ma trận integration test nên có

| Test case | Kết quả mong đợi |
|---|---|
| Đúng base/filter/scope, user có quyền đầy đủ | Entry và attribute cần thiết được trả |
| Không có entry match thật | Search success với zero entry |
| Base DN sai, `ignoreNameNotFoundException=false` | Lỗi base không tồn tại được giữ lại |
| Base DN sai, cấu hình bỏ qua NameNotFound | Hành vi được test rõ; không nhầm với no-match |
| Scope ONELEVEL khi entry ở subtree sâu hơn | Không tìm thấy entry |
| Projection bỏ `mail` | Mapper không nhận `mail` dù user có ACL |
| User không có quyền đọc `mail` | Entry/attribute bị che theo server ACL |
| User thiếu quyền dùng `mail` trong filter | Kết quả filter theo `mail` phản ánh chính sách server |
| `sizeLimit` bị vượt | Exception/partial-result behavior được phát hiện |
| Referral không được theo | Kết quả được đánh dấu không đầy đủ hoặc lỗi được giữ lại |
| Hai Bind identity chạy cùng request | Kết quả khác nhau đúng theo ACL đã thiết kế |
| Pool/context dùng sai Bind identity | Test thất bại và báo rõ identity thực tế |

### 7.5. Kiểm tra mapper khi attribute không xuất hiện

Unit test cho mapper nên xác nhận rằng attribute thiếu không làm code lỗi hoặc tự biến thành dữ liệu hợp lệ giả:

```java
import javax.naming.directory.Attribute;
import org.springframework.ldap.core.AttributesMapper;

AttributesMapper<PersonSummary> mapper = attrs -> {
    Attribute mailAttribute = attrs.get("mail");
    String mail = mailAttribute == null || mailAttribute.size() == 0
            ? null
            : (String) mailAttribute.get();
    return new PersonSummary(
            (String) attrs.get("uid").get(),
            (String) attrs.get("cn").get(),
            mail);
};
```

Kiểm tra `mail == null` chỉ bảo đảm mapper xử lý payload thiếu. Nó không xác định nguyên nhân là ACL hay dữ liệu không tồn tại. Phần phân biệt đó thuộc integration test với directory và identity thực.

## 8. Thiết kế tầng service khi kết quả có thể bị che

### 8.1. Không biến kết quả rỗng thành kết luận về ACL

Một service có thể biểu diễn kết quả nội bộ theo hướng trung lập:

```java
public sealed interface PersonLookupResult {
    record Found(PersonSummary person) implements PersonLookupResult {}
    record NoVisibleMatch() implements PersonLookupResult {}
}
```

`NoVisibleMatch` có nghĩa request hiện tại không trả entry nào. Nó không khẳng định entry không tồn tại trong toàn directory và cũng không khẳng định user thiếu quyền. Nếu nghiệp vụ cần phân biệt nguyên nhân, phải có bước chẩn đoán riêng với identity/quyền được phê duyệt; không suy ra từ empty list.

### 8.2. Không tự động fallback sang tài khoản quyền cao

Tránh mô hình:

```text
Search bằng credential người dùng
       |
       +-- Có kết quả -> trả về
       |
       +-- Rỗng -> retry bằng admin/service account
                        |
                        v
                 Trả dữ liệu cho người dùng
```

Fallback như vậy có thể biến một giới hạn ACL thành đường vượt quyền. Nếu service account được dùng cho truy vấn nghiệp vụ, phân quyền người dùng phải được thực hiện rõ ở tầng ứng dụng trước khi đọc dữ liệu; service account phải có quyền tối thiểu và query phải giới hạn theo tenant/ownership. Không dùng kết quả admin để âm thầm bù cho kết quả user.

### 8.3. Cẩn trọng với cache

RFC 4511 yêu cầu implementation cache dữ liệu LDAP phải bảo đảm access control vẫn được duy trì khi thông tin cache được cung cấp cho nhiều client. Một cache dùng chung có thể làm lộ dữ liệu nếu kết quả được lấy dưới identity có quyền rộng rồi trả cho identity bị hạn chế.

Nếu cache kết quả search:

- Key phải phản ánh tenant và authorization context cần thiết, không chỉ filter/base.
- Không chia sẻ entry/attribute nhạy cảm giữa các Bind identity nếu ACL khác nhau.
- Có chiến lược invalidation khi ACL/group membership thay đổi.
- Cache không được biến `NoVisibleMatch` của user A thành dữ liệu từ query admin hoặc user B.
- Không lưu attribute bị che như một giá trị rỗng vĩnh viễn nếu lần truy vấn sau có thể dùng identity/quyền khác.

### 8.4. Tránh tạo existence oracle

Một API trả `403` khi entry tồn tại nhưng caller không có quyền, và `404` khi entry không tồn tại, có thể tiết lộ sự tồn tại của user/attribute. Chính sách response phụ thuộc nghiệp vụ, nhưng nên xem xét trả thông điệp trung lập cho cả hai trường hợp khi thông tin tồn tại cần được bảo vệ.

Không đưa DN, `matchedDN`, diagnostic message hoặc tên attribute nhạy cảm vào response công khai. Log nội bộ chỉ ghi dữ liệu đủ để điều tra và tuân thủ chính sách bảo vệ dữ liệu.

## 9. Những anti-pattern thường gặp

| Anti-pattern | Vì sao sai | Cách xử lý |
|---|---|---|
| Empty list nghĩa là entry không tồn tại | Server có thể lọc entry theo ACL | Diễn giải là không có entry được trả cho request |
| Attribute null nghĩa là attribute không được lưu | Có thể không được yêu cầu hoặc bị ẩn | Kiểm tra projection và quyền bằng identity chẩn đoán |
| Mọi kết quả rỗng đều báo access denied | Có thể là filter/base/scope sai | Chẩn đoán request trước, không suy đoán ACL |
| Tự retry bằng admin khi list rỗng | Có thể vượt quyền caller | Authorization tường minh, không fallback nâng quyền |
| Dùng `mail=*` để dò email ẩn | Có thể tạo existence oracle | Kiểm tra ACL trên directory test |
| Bật ignore mọi exception để tránh lỗi | Có thể che partial result/referral/limit | Cấu hình rõ, log và test độ đầy đủ |
| Dùng `SUBTREE` cho mọi query | Mở rộng phạm vi dữ liệu và tải | Chọn base/scope theo nghiệp vụ |
| Cache chung theo filter/base | Bỏ qua khác biệt ACL giữa principal | Phân vùng cache theo authorization context |
| Log toàn bộ DN/attribute/diagnostic | Có thể tiết lộ thông tin directory | Log mã actor, request ID và kết quả tổng quát |

## 10. Câu hỏi tự đánh giá

1. Vì sao LDAP Search có thể trả `success (0)` nhưng zero entry?
2. `SearchResultEntry` và `SearchResultDone` có vai trò gì?
3. LDAP filter có những giá trị đánh giá nào? Khi nào filter có thể thành `Undefined`?
4. OpenLDAP phân biệt `search` và `read` như thế nào?
5. Trong Active Directory, quyền `List Contents` và `Read Property` ảnh hưởng đến search ra sao?
6. Vì sao attribute bị ẩn trong AD có thể làm filter theo attribute đó trả zero entry?
7. Vì sao `Attributes.get("mail") == null` không đủ chứng minh attribute không tồn tại?
8. `LdapTemplate.search()` khác `searchForObject()` ở cách biểu diễn kết quả như thế nào?
9. `ignoreNameNotFoundException`, `ignorePartialResultException` và `ignoreSizeLimitExceededException` có thể ảnh hưởng đến độ đầy đủ của kết quả ra sao?
10. Vì sao phải so sánh cùng SearchRequest bằng Bind identity ứng dụng và identity chẩn đoán?
11. `slapacl` giúp kiểm tra những quyền nào trong OpenLDAP?
12. Vì sao không nên retry bằng admin account khi query của user trả empty list?
13. Cache LDAP cần bảo đảm access control giữa các client như thế nào?
14. Làm sao thiết kế API tránh tiết lộ sự tồn tại của entry bị bảo vệ?

**Ghi nhớ:** kết quả LDAP là góc nhìn của **Bind identity + SearchRequest + ACL + directory server**, không phải bản kiểm kê toàn bộ dữ liệu. Một search success với zero entry hoặc một attribute bị thiếu có thể là no-match thực sự, request sai, projection không yêu cầu, hoặc quyền bị che. Hãy tách quyền nhìn thấy entry, dùng attribute trong filter và đọc attribute; xác nhận base/scope/filter/identity; so sánh với tài khoản chẩn đoán được phê duyệt; kiểm tra ACL theo đúng sản phẩm; và không dùng fallback/cache để vượt qua quyền.

### Tài liệu tham khảo

- IETF [RFC 4511 — LDAP: The Protocol](https://www.rfc-editor.org/rfc/rfc4511): SearchRequest, filter logic, SearchResultEntry/Done, access control và result code.
- Microsoft Learn — [MS-ADTS: Access Checks](https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-adts/8271b44d-a755-4872-a762-1ac57152099d): quyền hiển thị object, `RIGHT_DS_LIST_CONTENTS`, `RIGHT_DS_READ_PROPERTY` và cách attribute không visible được xử lý như không tồn tại.
- Microsoft Learn — [MS-ADTS: Access Rights](https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-adts/990fb975-ab31-4bc1-8b75-5da132cd4584): định nghĩa `RIGHT_DS_LIST_CONTENTS`, `RIGHT_DS_LIST_OBJECT` và `RIGHT_DS_READ_PROPERTY`.
- OpenLDAP Administrator's Guide — [Access Control](https://www.openldap.org/doc/admin26/access-control.html): access levels `disclose`, `auth`, `compare`, `search`, `read`, `write`, `manage`.
- OpenLDAP man page — [slapacl(8)](https://man7.org/linux/man-pages/man8/slapacl.8.html): kiểm tra quyền theo authentication DN, target DN và attribute access.
- Spring LDAP API — [LdapTemplate](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/LdapTemplate.html): search, mapper, search controls và các cờ bỏ qua exception.
- Spring LDAP API — [LdapOperations](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/core/LdapOperations.html): `search`, `searchForObject`, `searchForContext` và exception cardinality.
- Spring LDAP API — [LdapQueryBuilder](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/query/LdapQueryBuilder.html): base, search scope, attribute projection, count/time limit và filter builder.
- Spring LDAP — [Configuration](https://docs.spring.io/spring-ldap/reference/configuration.html): default search scope, count/time limit và cấu hình xử lý NameNotFound/PartialResult.
- Spring LDAP API — [NoPermissionException](https://docs.spring.io/spring-ldap/docs/3.3.x/api/org/springframework/ldap/NoPermissionException.html): exception runtime tương ứng JNDI NoPermissionException.
