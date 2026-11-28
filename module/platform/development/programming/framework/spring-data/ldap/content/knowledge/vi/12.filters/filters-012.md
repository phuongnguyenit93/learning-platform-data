# Extensible matching và kiểm tra khả năng hỗ trợ của máy chủ

## 1. Khi equality filter thông thường chưa đủ

Filter LDAP thông thường như:

```text
(cn=Linh Nguyen)
```

được so sánh bằng equality matching rule mặc định mà schema khai báo cho attribute `cn`. Với `cn`, schema phổ biến thường dùng `caseIgnoreMatch`, nên truy vấn có thể không phân biệt chữ hoa/chữ thường.

Nhưng một nghiệp vụ có thể cần quy tắc so sánh khác:

- Tìm tên **phân biệt hoa/thường**.
- So sánh DN theo ngữ nghĩa DN thay vì so sánh chuỗi.
- So sánh số theo integer syntax.
- So sánh thời gian theo Generalized Time matching rule.
- Tìm theo các thuộc tính trong DN của entry, ngoài các attribute thông thường.

LDAP hỗ trợ **extensible matching** thông qua extensibleMatch filter item. Nó cho phép client chỉ định matching rule sẽ dùng khi so sánh assertion value với giá trị attribute.

Ví dụ:

```text
(cn:caseExactMatch:=Linh Nguyen)
```

Filter này yêu cầu server dùng `caseExactMatch` cho `cn`, thay vì mặc định equality rule của attribute.

Trong module **SPRING_DATA_LDAP**, Spring Data LDAP cung cấp repository và ODM để ánh xạ entry LDAP sang Java; Spring LDAP cung cấp `LdapTemplate` và query builder để tìm kiếm. Extensible matching là khả năng ở tầng LDAP Search filter. Ứng dụng cần dựng đúng filter, chọn rule phù hợp schema và kiểm tra server thực tế có hỗ trợ tổ hợp rule/attribute đó hay không.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích matching rule và extensibleMatch khác equality filter thông thường thế nào.
2. Đọc cú pháp `(attribute[:dn][:matchingRule]:=assertionValue)`.
3. Chọn matching rule theo syntax của attribute và assertion value.
4. Dùng tên rule hoặc OID trong filter.
5. Phân biệt `:dn` với matching rule `distinguishedNameMatch`.
6. Khám phá schema qua `subschemaSubentry`, `matchingRules` và `matchingRuleUse`.
7. Hiểu vì sao Root DSE không có thuộc tính chuẩn `supportedMatchingRules`.
8. Dùng `LdapQueryBuilder.filter(format, params)` hoặc JNDI parameterized search để gửi filter an toàn.
9. Viết integration test kiểm chứng matching rule trên đúng loại LDAP server.

## 2. Matching rule là gì?

LDAP lưu giá trị attribute theo syntax, nhưng syntax và quy tắc so sánh là hai khái niệm khác nhau:

- **Syntax** xác định hình dạng/kiểu dữ liệu của value, ví dụ Directory String, Integer, Distinguished Name hoặc Generalized Time.
- **Matching rule** xác định cách so sánh một value với assertion value trong Search/Compare và một số thao tác khác.

Một attribute type có thể khai báo các matching rule mặc định:

```text
attributeType:
  EQUALITY  caseIgnoreMatch
  ORDERING  caseIgnoreOrderingMatch
  SUBSTR    caseIgnoreSubstringsMatch
```

Khi filter dùng equality:

```text
(cn=Linh Nguyen)
```

server dùng equality matching rule được định nghĩa cho attribute `cn`. Khi filter dùng extensible matching:

```text
(cn:2.5.13.5:=Linh Nguyen)
```

client yêu cầu dùng matching rule có OID `2.5.13.5`, tức `caseExactMatch`, nếu rule được server nhận diện và áp dụng được cho attribute/syntax này.

### 2.1. Matching rule không phải là schema attribute

Matching rule không phải một thuộc tính người dùng ghi vào entry như `cn` hoặc `mail`. Nó là định nghĩa schema mô tả cách so sánh. OID định danh matching rule; server triển khai logic để đánh giá assertion.

Một matching rule có:

- Tên mô tả, ví dụ `caseExactMatch`.
- OID, ví dụ `2.5.13.5`.
- Syntax của assertion value.
- Mục đích/loại so sánh mà rule hỗ trợ.

### 2.2. Extensible matching không phải extensibleObject

Hai tên gần giống nhưng khác nhau:

| Khái niệm | Ý nghĩa |
| --- | --- |
| **Extensible matching / extensibleMatch** | Một loại filter item cho phép chỉ định matching rule khi tìm kiếm. |
| **`extensibleObject` object class** | Auxiliary object class cho phép entry chứa các user attribute theo quy tắc schema của nó. |

Thêm `extensibleObject` vào entry không tự bật extensible matching trên server. Ngược lại, dùng extensibleMatch không đòi hỏi entry phải có object class `extensibleObject`.

## 3. Cú pháp extensibleMatch theo RFC 4515

Filter có hai dạng chính:

```text
(attribute[:dn][:matchingRule]:=assertionValue)

([:dn]matchingRule:=assertionValue)
```

Ví dụ:

```text
(cn:caseExactMatch:=Linh Nguyen)
(cn:2.5.13.5:=Linh Nguyen)
(cn:dn:2.5.13.5:=Linh Nguyen)
(:2.5.13.2:=Linh)
```

Thành phần:

| Thành phần | Ý nghĩa |
| --- | --- |
| `attribute` | Attribute type cần so sánh; có thể vắng mặt ở dạng generic. |
| `:dn` | Yêu cầu kiểm tra thêm các AVA trong DN của entry. |
| `:matchingRule` | Tên descriptor hoặc OID của matching rule. |
| `:=` | Dấu phân cách của extensibleMatch. |
| `assertionValue` | Giá trị được diễn giải theo syntax của matching rule. |

Thứ tự theo grammar là attribute, tùy chọn `:dn`, tùy chọn `:matchingRule`, rồi `:=` và assertion value. Không tự đảo thứ tự các thành phần.

### 3.1. Không ghi matching rule vẫn có thể là extensibleMatch

Ví dụ:

```text
(cn:=Linh Nguyen)
```

Nếu matchingRule bị bỏ qua, `type` phải có mặt và server thực hiện equality match cho attribute đó. Do đó, filter này **không tự chọn một quy tắc so sánh mới**; nó dùng equality matching rule của `cn`.

### 3.2. Bỏ attribute để áp dụng rule cho các attribute tương thích

Ví dụ:

```text
(:2.5.13.2:=Linh)
```

Khi không chỉ định attribute, server so sánh assertion value với các attribute trong entry có hỗ trợ matching rule đó. Cách này có thể mở rộng phạm vi match ngoài dự định và tốn tài nguyên; chỉ dùng khi nghiệp vụ thật sự cần tìm trên nhiều attribute.

### 3.3. `:dn` có ý nghĩa gì?

Ví dụ:

```text
(cn:dn:2.5.13.5:=Engineering)
```

`dnAttributes` được đặt TRUE. Ngoài các attribute trong entry, server còn áp dụng phép so sánh lên các AttributeValueAssertion trong DN của entry. Với filter trên, các AVA có attribute type `cn` trong DN cũng được xét.

`:dn` **không** có nghĩa là:

- Dùng matching rule `distinguishedNameMatch`.
- So sánh toàn bộ DN của entry với assertion value.
- Tự tìm tất cả entry con trong DN.

Đó là cờ yêu cầu xét thêm các attribute nằm trong tên phân biệt của entry. Mặc định cờ này là FALSE.

## 4. Các matching rule thường gặp

Các matching rule được định danh bằng OID. Một số rule chuẩn theo RFC 4517:

| Matching rule | OID | Ý nghĩa | Ví dụ kiểu dữ liệu phù hợp |
| --- | --- | --- | --- |
| `caseIgnoreMatch` | `2.5.13.2` | Equality không phân biệt hoa/thường theo quy tắc chuẩn bị chuỗi của LDAP. | Directory String. |
| `caseExactMatch` | `2.5.13.5` | Equality phân biệt hoa/thường. | Directory String. |
| `distinguishedNameMatch` | `2.5.13.1` | So sánh hai DN theo ngữ nghĩa DN. | Distinguished Name. |
| `integerMatch` | `2.5.13.14` | So sánh giá trị số nguyên. | Integer. |
| `generalizedTimeMatch` | `2.5.13.27` | So sánh thời điểm Generalized Time. | Generalized Time. |
| `caseIgnoreSubstringsMatch` | `2.5.13.4` | So sánh chuỗi theo ngữ nghĩa substring không phân biệt hoa/thường. | Directory String; assertion syntax là Substring Assertion. |

Các ví dụ này không có nghĩa mọi rule áp dụng được cho mọi attribute. Assertion value phải đúng syntax mà rule yêu cầu; attribute syntax cũng phải tương thích với rule.

### 4.1. caseIgnoreMatch và caseExactMatch

Giả sử directory có hai entry:

```ldif
dn: uid=linh,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: linh
cn: Linh Nguyen
sn: Nguyen

dn: uid=linh-upper,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: linh-upper
cn: LINH NGUYEN
sn: Nguyen
```

Nếu schema cho phép hai rule trên áp dụng với `cn`:

```text
(cn:2.5.13.2:=Linh Nguyen)
  -> có thể khớp cả hai entry vì caseIgnoreMatch không phân biệt hoa/thường.

(cn:2.5.13.5:=Linh Nguyen)
  -> chỉ khớp entry có cn đúng kiểu chữ "Linh Nguyen".
```

`caseExactMatch` vẫn tuân theo quy tắc chuẩn bị assertion/value của matching rule. Không nên đồng nhất nó với `String.equals` của Java trong mọi trường hợp Unicode hoặc khoảng trắng.

### 4.2. distinguishedNameMatch

Attribute `member` của group có thể chứa DN đầy đủ:

```ldif
dn: cn=developers,ou=groups,dc=example,dc=org
objectClass: top
objectClass: groupOfNames
cn: developers
member: uid=linh,ou=people,dc=example,dc=org
```

Có thể viết:

```text
(member:2.5.13.1:=uid=linh,ou=people,dc=example,dc=org)
```

để yêu cầu `distinguishedNameMatch`. Với schema thông dụng, equality matching rule mặc định của DN-valued attribute `member` cũng là `distinguishedNameMatch`, nên ví dụ explicit rule có thể cho kết quả tương đương equality thường. Lợi ích của explicit rule là thể hiện rõ semantics đang yêu cầu.

Nếu assertion value chứa ký tự cần escape trong filter string, phải filter-encode assertion value theo RFC 4515. Nếu dùng Spring query parameter hoặc JNDI filter arguments, để API tham số hóa encode giá trị; không encode trước rồi encode lần nữa.

### 4.3. integerMatch và generalizedTimeMatch

Không dùng `caseExactMatch` cho một attribute có Integer syntax. Tương tự, assertion của `generalizedTimeMatch` phải có dạng thời gian mà syntax đó chấp nhận.

Ví dụ minh họa:

```text
(uidNumber:2.5.13.14:=1001)
(createTimestamp:2.5.13.27:=20261126120000Z)
```

Chỉ dùng các filter này nếu schema của server khai báo attribute tương ứng có syntax phù hợp và matching rule được phép áp dụng. Tên attribute ví dụ không tự bảo đảm schema của mọi directory giống nhau.

## 5. Matching rule phải phù hợp với syntax

Một rule có thể được nhận diện nhưng không phù hợp với attribute được chỉ định. Ví dụ:

```text
(uidNumber:2.5.13.5:=1001)
```

không phải truy vấn hợp lệ theo nghĩa ngữ nghĩa nếu `uidNumber` có Integer syntax mà `caseExactMatch` yêu cầu Directory String.

Khi đánh giá extensibleMatch, cần xác minh ba điều:

1. Server nhận diện matching rule ID (descriptor hoặc OID).
2. Matching rule phù hợp với attribute type và syntax của nó.
3. Assertion value có thể được parse theo assertion syntax của matching rule.

RFC 4511 quy định filter item có thể có kết quả **Undefined** nếu matching rule không được nhận diện, không phù hợp với attribute type hoặc assertion value không hợp lệ. Search chỉ trả entry mà filter đánh giá TRUE. Vì vậy, một filter không hỗ trợ có thể trả về rỗng mà không nhất thiết có một lỗi cú pháp dễ thấy.

## 6. Kiểm tra schema: matchingRules và matchingRuleUse

Schema LDAP có thể công bố:

- `matchingRules`: các định nghĩa matching rule, gồm OID, tên và syntax của assertion.
- `matchingRuleUse`: các định nghĩa cho biết matching rule áp dụng với attribute type nào, thông qua danh sách `APPLIES`.
- `attributeTypes`: syntax và matching rule mặc định (`EQUALITY`, `ORDERING`, `SUBSTR`) của từng attribute type.

Các schema attribute này là operational attributes, nên client cần yêu cầu rõ khi Search.

### 6.1. Bắt đầu từ Root DSE

Root DSE có thể công bố `subschemaSubentry` để chỉ ra DN của subschema entry kiểm soát Root DSE. Một số thuộc tính Root DSE chuẩn khác gồm `namingContexts`, `supportedControl`, `supportedExtension`, `supportedFeatures`, `supportedLDAPVersion` và `supportedSASLMechanisms`.

Ví dụ dùng OpenLDAP command-line client để đọc Root DSE:

```bash
ldapsearch -LLL -x -H "ldaps://ldap-test.example.org:636" \
  -D "uid=svc-reader,ou=service-accounts,dc=example,dc=org" -W \
  -b "" -s base "(objectClass=*)" \
  subschemaSubentry namingContexts supportedLDAPVersion \
  supportedControl supportedExtension supportedFeatures
```

Lệnh này dùng base rỗng và scope base để đọc Root DSE. Thay endpoint và bind DN bằng cấu hình test của bạn.

**Không có thuộc tính Root DSE chuẩn tên `supportedMatchingRules`.** `extensibleMatch` là một filter item trong LDAP SearchRequest, không phải LDAP control hay extended operation. Vì thế, không thể kết luận server hỗ trợ matching rule chỉ bằng cách tìm OID trong `supportedControl` hoặc `supportedExtension`.

### 6.2. Đọc subschema entry

Nếu Root DSE trả về:

```text
subschemaSubentry: cn=Subschema
```

hãy dùng đúng DN đó để truy vấn:

```bash
ldapsearch -LLL -x -H "ldaps://ldap-test.example.org:636" \
  -D "uid=svc-reader,ou=service-accounts,dc=example,dc=org" -W \
  -b "cn=Subschema" -s base "(objectClass=subschema)" \
  matchingRules matchingRuleUse attributeTypes
```

DN trong ví dụ chỉ là minh họa. Luôn dùng giá trị `subschemaSubentry` server trả về; không mặc định mọi server dùng `cn=Subschema`.

### 6.3. Lấy subschema kiểm soát một entry cụ thể

RFC 4512 lưu ý subschema có thể áp dụng cho một phần của cây directory. Nếu cần xác minh rule cho entry trong một OU cụ thể:

1. Đọc entry đó với scope base và yêu cầu attribute operational `subschemaSubentry`.
2. Dùng DN được trả về để Search scope base với filter `(objectClass=subschema)`.
3. Yêu cầu `matchingRules`, `matchingRuleUse` và `attributeTypes`.

Không giả định subschema trỏ từ Root DSE luôn kiểm soát tất cả naming context/entry của server.

### 6.4. Đọc kết quả schema như thế nào?

Ví dụ định nghĩa rule:

```text
( 2.5.13.5
  NAME 'caseExactMatch'
  SYNTAX 1.3.6.1.4.1.1466.115.121.1.15 )
```

Ví dụ matching rule use có thể chỉ ra rule áp dụng cho một số attribute:

```text
( 2.5.13.5
  NAME 'caseExactMatch'
  APPLIES ( cn $ sn ) )
```

Đây là ví dụ cấu trúc schema; danh sách APPLIES thực tế do server công bố. Hãy kiểm tra attribute type cần dùng có trong danh sách phù hợp hay không.

**Lưu ý:** `matchingRuleUse` là thông tin server có thể công bố khi hỗ trợ extensibleMatch; RFC cho phép server không cung cấp nó. RFC 4512 cũng nói client không nên giả định schema được công bố là đầy đủ, server hỗ trợ mọi thứ đã công bố hoặc không hỗ trợ những gì chưa công bố. Schema discovery là một phần bằng chứng, không thay thế active test.

## 7. Kiểm tra khả năng hỗ trợ của máy chủ

Không nên suy luận khả năng chỉ từ vendor name hoặc phiên bản. Cùng một họ server có thể khác nhau do:

- Phiên bản và cấu hình schema.
- Custom matching rule/plugin/module đã cài.
- ACL của bind identity.
- Naming context/subschema đang được truy vấn.
- Attribute syntax và matching rule use.
- Replica hoặc endpoint mà ứng dụng đang kết nối.

Một quy trình kiểm tra có thể thực hiện:

```text
1. Kết nối đúng endpoint, TLS và bind identity của ứng dụng.
2. Đọc Root DSE và subschemaSubentry.
3. Đọc matchingRules, matchingRuleUse, attributeTypes.
4. Xác nhận rule ID, syntax và APPLIES cho attribute.
5. Chạy active probe với fixture đã biết kết quả.
6. Ghi nhận endpoint, server version, bind identity và kết quả.
7. Nếu không hỗ trợ, chọn fallback phù hợp nghiệp vụ.
```

### 7.1. Active probe với dữ liệu kiểm thử

Để kiểm tra `caseExactMatch` trên `cn`, tạo hai fixture có giá trị chỉ khác hoa/thường:

```ldif
dn: uid=probe-exact,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: probe-exact
cn: Linh Nguyen
sn: Nguyen

dn: uid=probe-upper,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: probe-upper
cn: LINH NGUYEN
sn: Nguyen
```

Trước hết, kiểm tra dữ liệu có tồn tại và bind identity nhìn thấy cả hai. Sau đó chạy:

```text
(cn:2.5.13.2:=Linh Nguyen)
  kỳ vọng: probe-exact và probe-upper

(cn:2.5.13.5:=Linh Nguyen)
  kỳ vọng: probe-exact
```

Nếu equality filter thường và caseIgnoreMatch đều không tìm thấy hai fixture, test chưa chứng minh được hỗ trợ hay không; có thể DN/base/ACL/fixture sai. Nếu baseline tìm thấy cả hai nhưng extensible filter không trả kết quả hoặc báo lỗi, cần điều tra matching rule support/applicability.

### 7.2. Kết quả probe không chỉ có pass/fail

| Kết quả | Diễn giải |
| --- | --- |
| Schema có rule và APPLIES; probe đúng | Có bằng chứng tốt cho tổ hợp endpoint/rule/attribute/identity đã test. |
| Schema có rule nhưng không có matchingRuleUse | Chưa đủ thông tin về applicability; cần active probe và tài liệu server. |
| Schema không công bố rule nhưng probe thành công | Server có thể hỗ trợ rule không công bố; ghi nhận hành vi thực tế và vendor/version. |
| Probe trả rỗng nhưng baseline cũng rỗng | Test fixture hoặc search setup chưa hợp lệ; chưa thể kết luận. |
| Baseline có kết quả, extensible filter rỗng | Có thể rule không hỗ trợ, không phù hợp syntax hoặc assertion sai. |
| Server trả lỗi inappropriateMatching/unwillingToPerform | Kiểm tra matching rule, syntax, attribute applicability và implementation. |

Một filter không hợp lệ về mặt matching semantics có thể đánh giá Undefined thay vì làm Search trả một lỗi rõ ràng. Vì vậy, active probe phải có **baseline dương tính** và dữ liệu có kết quả kỳ vọng.

## 8. Dùng extensibleMatch với Spring LDAP

### 8.1. LdapQueryBuilder cho filter format và tham số

Spring LDAP hiện cung cấp `LdapQueryBuilder.filter(String filterFormat, Object... params)`. Phương thức nhận filter format theo `MessageFormat` và encode các tham số bằng `LdapEncoder.filterEncode`.

Đây là cách phù hợp để giữ cấu trúc extensible filter cố định, trong khi assertion value là dữ liệu động:

```java
import static org.springframework.ldap.query.LdapQueryBuilder.query;

import java.util.List;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;

String searchName = request.getName();

LdapQuery exactNameQuery = query()
    .base("ou=people")
    .filter("(cn:2.5.13.5:={0})", searchName);

List<String> uids = ldapTemplate.search(
    exactNameQuery,
    (AttributesMapper<String>) attrs ->
        (String) attrs.get("uid").get()
);
```

Trong ví dụ:

- Attribute `cn` được viết cố định trong code.
- Matching rule OID `2.5.13.5` được chọn từ code/configuration đã kiểm soát.
- `searchName` là assertion value động và được Spring encode.
- Base `ou=people` giới hạn phạm vi Search.

### 8.2. Vì sao không dùng where().is()?

Các tiêu chí thông dụng của `LdapQueryBuilder.where` gồm equality, greater-than-or-equal, less-than-or-equal, like, presence và not. API fluent đó không cung cấp một tham số matching rule tùy ý cho extensibleMatch.

Khi cần extensibleMatch, dùng `filter(format, params)` với phần cấu trúc do ứng dụng cố định. Không tự ghép input vào `filter(String hardcodedFilter)` vì overload raw filter không tự validate/escape chuỗi.

Các derived query của `LdapRepository` hữu ích cho điều kiện tìm kiếm phổ biến, nhưng không có tham số để chọn matching rule OID tùy ý. Với extensibleMatch, hãy đặt truy vấn trong custom repository implementation hoặc service dùng `LdapTemplate`/`LdapClient`; giữ rule và attribute trong code đã kiểm soát.

### 8.3. Không dùng matching rule ID do caller tự gửi

Không viết:

```java
String filter = "(" + request.getAttribute()
    + ":" + request.getMatchingRule()
    + ":=" + request.getValue() + ")";
```

Caller không nên điều khiển:

- Attribute description.
- Matching rule descriptor/OID.
- Cờ `:dn`.
- Search base và scope.

Hãy ánh xạ lựa chọn nghiệp vụ sang một cấu hình cho phép:

```java
enum NameSearchMode {
    CASE_INSENSITIVE("2.5.13.2"),
    CASE_SENSITIVE("2.5.13.5");

    private final String matchingRuleOid;

    NameSearchMode(String matchingRuleOid) {
        this.matchingRuleOid = matchingRuleOid;
    }

    String matchingRuleOid() {
        return matchingRuleOid;
    }
}
```

Nếu cần nhiều attribute, định nghĩa allowlist attribute riêng. Đừng cho API nhận OID tùy ý rồi chạy filter trên toàn subtree.

## 9. Dùng LdapEncoder khi tự dựng raw filter

Một số code cũ dùng overload raw filter string của `LdapTemplate.search`. Khi đó ứng dụng phải encode assertion value đúng một lần:

```java
import org.springframework.ldap.support.LdapEncoder;

String searchName = request.getName();
String safeValue = LdapEncoder.filterEncode(searchName);

String filter = "(cn:2.5.13.5:=" + safeValue + ")";

List<String> uids = ldapTemplate.search(
    "ou=people",
    filter,
    (AttributesMapper<String>) attrs ->
        (String) attrs.get("uid").get()
);
```

Chỉ `searchName` được encode. Attribute, OID và cấu trúc filter là literal do code định nghĩa.

### 9.1. Không encode hai lần

Nếu dùng:

```java
query().filter("(cn:2.5.13.5:={0})", searchName);
```

thì Spring đã encode tham số. Không gọi `LdapEncoder.filterEncode` trước rồi đưa kết quả đã encode vào tham số nữa. Làm như vậy có thể khiến backslash trong escape sequence trở thành dữ liệu literal và thay đổi assertion value.

### 9.2. JNDI parameterized search

JNDI có overload `DirContext.search` nhận filter expression và mảng tham số:

```java
SearchControls controls = new SearchControls();
controls.setSearchScope(SearchControls.SUBTREE_SCOPE);
controls.setReturningAttributes(new String[] {"uid", "cn"});

NamingEnumeration<SearchResult> results = context.search(
    "ou=people",
    "(cn:2.5.13.5:={0})",
    new Object[] {searchName},
    controls
);

try {
    while (results.hasMore()) {
        SearchResult result = results.next();
        // Xử lý kết quả.
    }
} finally {
    results.close();
}
```

Provider thay tham số bằng assertion value được encode phù hợp. Không tự thay `{0}` bằng `String.replace`/`String.format`. Attribute và matching rule vẫn phải cố định hoặc lấy từ allowlist.

## 10. Ví dụ dùng :dn để tìm theo thuộc tính trong DN

Giả sử một entry có DN:

```text
cn=Engineering,ou=groups,dc=example,dc=org
```

Entry đó có thể có attribute `description` khác với tên trong RDN. Filter:

```text
(cn:dn:2.5.13.5:=Engineering)
```

yêu cầu matching trên `cn` trong entry và xét thêm AVA `cn=Engineering` trong DN.

Trong Spring LDAP:

```java
LdapQuery queryByDnAttribute = query()
    .base("ou=groups")
    .filter("(cn:dn:2.5.13.5:={0})", "Engineering");
```

Không cần tạo attribute `cn` giả chỉ để truy vấn DN component; `:dn` yêu cầu server xét naming attributes. Tuy nhiên, server phải hỗ trợ extensibleMatch và rule tương ứng.

## 11. Tìm theo DN-valued attribute

Một tình huống khác là attribute chứa DN đầy đủ, ví dụ `member`:

```ldif
dn: cn=developers,ou=groups,dc=example,dc=org
objectClass: top
objectClass: groupOfNames
cn: developers
member: uid=linh,ou=people,dc=example,dc=org
```

`member` có Distinguished Name syntax và thường dùng `distinguishedNameMatch`. Có thể yêu cầu rõ:

```java
Name memberDn = LdapNameBuilder
    .newInstance("dc=example,dc=org")
    .add("ou", "people")
    .add("uid", "linh")
    .build();

LdapQuery groups = query()
    .base("ou=groups")
    .filter("(member:2.5.13.1:={0})", memberDn.toString());
```

Ở đây `memberDn` là giá trị DN được dựng an toàn; `LdapQueryBuilder.filter(format, params)` filter-encode chuỗi DN khi đưa vào assertion value. Không tự filter-encode trước khi truyền vào tham số.

## 12. Phân biệt extensibleMatch với các filter khác

| Filter | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Equality | `(cn=Linh Nguyen)` | Dùng equality matching rule mặc định của attribute. |
| Greater-or-equal | `(uidNumber>=1000)` | Dùng ordering matching rule của attribute. |
| Approximate | `(cn~=Linh Nguyen)` | Dùng approximate algorithm theo implementation; semantics có thể phụ thuộc server. |
| Substring | `(cn=Lin*)` | Dùng substring matching rule mặc định. |
| Extensible | `(cn:2.5.13.5:=Linh Nguyen)` | Chỉ định matching rule tường minh. |

Extensible matching không tự có nghĩa là:

- Fuzzy search hay phonetic search. Chỉ có nếu matching rule tương ứng tồn tại và server hỗ trợ.
- Full-text search.
- Tìm kiếm substring. Cần chọn rule và assertion syntax phù hợp.
- Mở rộng schema hoặc tạo matching rule mới.

Nó là cách chọn một matching rule có sẵn/được server triển khai cho một assertion cụ thể.

## 13. Hiệu năng và phạm vi Search

Extensible matching có thể tốn kém nếu:

- Không chỉ định attribute, khiến server phải kiểm tra nhiều attribute.
- Search base quá rộng.
- Matching rule không có index tương ứng.
- Assertion rule yêu cầu chuẩn hóa hoặc so sánh phức tạp.
- Kết quả có thể lớn và ứng dụng không giới hạn số lượng.

Hãy:

1. Chỉ rõ attribute nếu nghiệp vụ biết attribute cần tìm.
2. Giới hạn base DN và search scope.
3. Dùng count/time limit hợp lý.
4. Kiểm tra index và query performance theo tài liệu vendor.
5. Đo latency trên dữ liệu gần thực tế.
6. Tránh query không có attribute nếu không thật sự cần.

Không giả định việc có index cho equality mặc định đồng nghĩa server có index tối ưu cho mọi extensible matching rule.

## 14. Kiểm thử extensible matching bằng JUnit

Test sau là **contract/integration test** cho LDAP test server. Fixture phải có hai user:

- `uid=probe-exact`, `cn=Linh Nguyen`.
- `uid=probe-upper`, `cn=LINH NGUYEN`.

Schema của test server phải cho phép `caseIgnoreMatch` và `caseExactMatch` áp dụng cho `cn`.

```java
package com.example.directory;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.ldap.query.LdapQueryBuilder.query;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;

@SpringBootTest
class ExtensibleMatchIT {

    @Autowired
    private LdapTemplate ldapTemplate;

    private List<String> searchByFilter(String filterFormat,
                                        String assertionValue) {
        LdapQuery ldapQuery = query()
            .base("ou=people")
            .filter(filterFormat, assertionValue);

        return ldapTemplate.search(
            ldapQuery,
            (AttributesMapper<String>) attrs ->
                (String) attrs.get("uid").get()
        );
    }

    @Test
    void caseExactAndCaseIgnoreUseDifferentRules() {
        // Baseline equality filter kiểm tra fixture và quyền đọc trước.
        LdapQuery baselineQuery = query()
            .base("ou=people")
            .where("cn").is("Linh Nguyen");
        List<String> baseline = ldapTemplate.search(
            baselineQuery,
            (AttributesMapper<String>) attrs ->
                (String) attrs.get("uid").get()
        );

        assertThat(baseline)
            .containsExactlyInAnyOrder("probe-exact", "probe-upper");

        List<String> exact = searchByFilter(
            "(cn:2.5.13.5:={0})", "Linh Nguyen");

        assertThat(exact).containsExactly("probe-exact");
    }
}
```

Test này kiểm tra:

- LDAP server tìm được fixture bằng `caseIgnoreMatch`.
- `caseExactMatch` phân biệt khác biệt hoa/thường.
- Tham số assertion được truyền qua query builder.
- Kết quả được đọc lại từ directory, không phải so sánh chuỗi Java tại client.

Nếu server test không hỗ trợ extensibleMatch hoặc không cho dùng `caseExactMatch` với `cn`, test sẽ thất bại. Đó là kết quả có ích của contract test; hãy xác minh schema, server capability và fixture trước khi kết luận nguyên nhân.

### 14.1. Test DN attribute

Nếu muốn kiểm tra `:dn`, tạo fixture có RDN `cn=Engineering` và một entry khác chỉ có attribute `cn=Engineering` nhưng DN không có AVA đó. Sau đó so sánh:

```text
(cn:2.5.13.5:=Engineering)
(cn:dn:2.5.13.5:=Engineering)
```

Filter thứ hai có thể tìm thêm entry có `cn=Engineering` trong DN. Thiết kế fixture sao cho chỉ khác vị trí attribute, để test xác minh đúng semantics của `dnAttributes`.

### 14.2. Test unsupported rule

Không nên cố tình gửi OID ngẫu nhiên lên production. Trong một server test riêng, có thể kiểm tra behavior khi matching rule không được nhận diện:

- Server có thể đánh giá filter item là Undefined, khiến entry không được trả về.
- Một số implementation có thể trả LDAP error như `inappropriateMatching` hoặc lỗi khác.
- Cần ghi nhận behavior thực tế của server/version, không giả định mọi implementation trả cùng result code.

## 15. Khi server không hỗ trợ

Nếu server không hỗ trợ extensibleMatch hoặc rule không áp dụng được:

1. Dùng equality filter mặc định nếu semantics nghiệp vụ chấp nhận.
2. Chọn matching rule khác đã được server hỗ trợ và phù hợp syntax.
3. Nếu cần semantics riêng, thiết kế attribute tìm kiếm chuyên biệt với schema/matching rule được quản trị viên triển khai.
4. Với tập dữ liệu nhỏ và giới hạn, có thể đọc một tập kết quả có kiểm soát rồi lọc ở ứng dụng; không quét toàn directory cho một truy vấn thường xuyên.
5. Nếu triển khai custom matching rule, cần kiểm tra khả năng tương thích giữa các replica, server version và môi trường dự phòng.

Không âm thầm fallback từ case-sensitive sang case-insensitive nếu điều đó làm thay đổi quyền truy cập hoặc kết quả nghiệp vụ. Hãy trả trạng thái không hỗ trợ hoặc áp dụng một policy fallback đã được xác định.

## 16. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Filter không trả kết quả | Matching rule không nhận diện/không áp dụng, assertion syntax sai hoặc fixture không đúng. | Chạy baseline equality, kiểm tra matchingRules/matchingRuleUse và active probe. |
| `inappropriateMatching` | Rule không phù hợp attribute/syntax hoặc implementation từ chối filter. | Đối chiếu attributeTypes, matchingRuleUse và tài liệu server. |
| `undefined` hoặc không có entry | Matching rule chưa biết, assertion value không parse được hoặc rule không phù hợp. | Kiểm tra OID, syntax và assertion value. |
| Descriptor không nhận diện | Server không công bố/không chấp nhận short name. | Dùng numeric OID chuẩn nếu server hỗ trợ. |
| OID đúng nhưng kết quả khác dự kiến | Matching rule semantics hoặc attribute syntax không như giả định. | Đọc schema và tạo fixture tối thiểu để xác minh. |
| `:dn` không tìm thấy entry | Entry DN không có AVA tương ứng hoặc cờ bị đặt sai vị trí. | Kiểm tra DN thực và grammar `attribute:dn:rule:=value`. |
| Spring query không parse được filter | Filter format/placeholder hoặc MessageFormat sai. | Giữ filter pattern cố định, truyền assertion qua params. |
| Query trả quá nhiều entry | Bỏ attribute, dùng matching rule generic hoặc base/scope quá rộng. | Chỉ định attribute và giới hạn Search. |
| Root DSE không có supportedMatchingRules | Đây không phải Root DSE attribute chuẩn. | Đọc subschema và chạy active probe. |
| Schema không có matchingRuleUse | Server có thể không công bố attribute này. | Không kết luận ngay; kiểm tra matchingRules và active probe. |

## 17. Checklist triển khai

- [ ] Đã xác định nhu cầu thực sự cần extensibleMatch thay cho equality mặc định.
- [ ] Đã xác định syntax của attribute và assertion value.
- [ ] Matching rule được chọn bằng descriptor/OID đã kiểm soát.
- [ ] Rule tương thích với attribute type và syntax.
- [ ] Đã đọc subschema phù hợp với entry/naming context.
- [ ] Đã kiểm tra matchingRules và matchingRuleUse nếu server công bố.
- [ ] Không dùng supportedControl/supportedExtension để suy luận extensibleMatch.
- [ ] Có active probe với fixture và baseline equality.
- [ ] Assertion value được filter-encode đúng một lần.
- [ ] Không cho caller tùy ý truyền attribute, matching rule OID hoặc :dn.
- [ ] Search base, scope, count/time limit được giới hạn.
- [ ] Đã kiểm tra hiệu năng/index trên đúng server.
- [ ] Có contract test trên đúng vendor/version nếu dùng rule đặc thù.
- [ ] Có fallback rõ ràng nếu server không hỗ trợ.

## 18. Bài tập vận dụng

1. Viết filter tìm `cn` bằng `caseExactMatch` OID `2.5.13.5` và giải thích khác biệt với `(cn=value)`.
2. Viết filter dùng `caseIgnoreMatch` OID `2.5.13.2`. Hai giá trị chỉ khác hoa/thường có kết quả ra sao?
3. Giải thích `(cn:=Linh)` có ý nghĩa gì khi không chỉ định matching rule.
4. Viết filter `(cn:dn:2.5.13.5:=Engineering)` và mô tả chính xác `:dn` bổ sung những giá trị nào vào phép so sánh.
5. Giải thích vì sao `distinguishedNameMatch` OID `2.5.13.1` khác cờ `:dn`.
6. Tại sao `integerMatch` không phù hợp cho một attribute có Directory String syntax?
7. Nêu vai trò của `matchingRules` và `matchingRuleUse` trong subschema.
8. Vì sao `supportedControl` không chứng minh server hỗ trợ extensibleMatch?
9. Thiết kế active probe cho caseExactMatch với hai entry có `cn` chỉ khác hoa/thường.
10. Viết Spring LDAP query bằng `LdapQueryBuilder.filter(format, params)` để assertion value không bị filter injection.
11. Server trả zero results cho extensible filter. Cần kiểm tra gì trước khi kết luận server không hỗ trợ?
12. Đề xuất fallback khi ứng dụng cần tìm tên phân biệt hoa/thường nhưng server không hỗ trợ matching rule cần thiết.

## 19. Tài liệu tham khảo

- [RFC 4511 — LDAP Protocol, SearchRequest.extensibleMatch](https://www.rfc-editor.org/rfc/rfc4511): cấu trúc MatchingRuleAssertion, cách đánh giá matchingRule, type, matchValue và dnAttributes.
- [RFC 4515 — String Representation of Search Filters](https://www.rfc-editor.org/rfc/rfc4515): grammar extensible filter, descriptor/OID, `:dn` và assertion value encoding.
- [RFC 4517 — LDAP Syntaxes and Matching Rules](https://www.rfc-editor.org/rfc/rfc4517): matching rule definitions, assertion syntax, OID, caseIgnoreMatch, caseExactMatch, distinguishedNameMatch và applicability.
- [RFC 4512 — Directory Information Models](https://www.rfc-editor.org/rfc/rfc4512): subschemaSubentry, matchingRules, matchingRuleUse, attributeTypes và Root DSE.
- [Spring LDAP — Advanced LDAP Queries](https://docs.spring.io/spring-ldap/reference/query-builder-advanced.html): LdapQueryBuilder, hardcoded filter và filter parameters.
- [Spring LDAP API — LdapQueryBuilder](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/query/LdapQueryBuilder.html): `filter(String, Object...)` và các tham số query.
- [Spring LDAP API — LdapTemplate](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/LdapTemplate.html): các overload search nhận LdapQuery hoặc raw filter.
- [Spring LDAP API — LdapEncoder](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/support/LdapEncoder.html): filterEncode assertion value.
- [Oracle Java SE — DirContext](https://docs.oracle.com/en/java/javase/17/docs/api/java.naming/javax/naming/directory/DirContext.html): JNDI search với filter expression và filter arguments.
