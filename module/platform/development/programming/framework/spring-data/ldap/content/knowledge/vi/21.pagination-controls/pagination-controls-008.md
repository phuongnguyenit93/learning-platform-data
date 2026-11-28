# Sắp xếp phía máy chủ qua control khi được hỗ trợ

Trong **Spring Data LDAP**, một truy vấn có thể tìm thấy nhiều entry trong cùng một naming context. Ứng dụng thường muốn hiển thị danh bạ theo tên, nhân viên theo mã, nhóm theo tên hoặc kết quả theo nhiều khóa. Nếu tải toàn bộ kết quả về Java rồi mới sắp xếp, ứng dụng phải giữ và xử lý dữ liệu trong bộ nhớ. Nếu chỉ tải một trang rồi sắp xếp trang đó, thứ tự của trang có thể không đại diện cho **thứ tự toàn bộ tập kết quả**.

LDAP có một cơ chế riêng cho yêu cầu này: **Server Side Sort control**, được định nghĩa trong **RFC 2891**. Client gửi sort request control cùng LDAP SearchRequest để yêu cầu directory server sắp xếp kết quả theo một hoặc nhiều attribute. Server gửi response control để thông báo việc sắp xếp thành công hay thất bại.

Spring LDAP tích hợp control này thông qua `LdapTemplate` và `DirContextProcessor`. Ở Spring LDAP **4.1 trở lên**, API hiện đại là `SortControlExchange` kết hợp `ControlExchangeDirContextProcessor`. Các phiên bản cũ hơn có `SortControlDirContextProcessor`; class này đã deprecated từ 4.1.

Sau bài học, bạn có thể:

- Phân biệt sắp xếp phía server bằng LDAP control với sắp xếp phía client trong Java.
- Xác định request OID và response OID của RFC 2891.
- Khai báo một hoặc nhiều sort key và hiểu thứ tự ưu tiên của chúng.
- Gắn sort control vào search qua Spring LDAP.
- Đọc response control để xác nhận server thật sự đã sắp xếp.
- Chọn cách xử lý khi server không hỗ trợ sort hoặc không thể áp dụng matching rule.
- Kết hợp server-side sort với paged results đúng quy tắc.
- Tránh lỗi về schema, attribute đa trị, giá trị bị thiếu, giới hạn server, bảo mật và hiệu năng.

## 1. Sắp xếp kết quả LDAP ở tầng nào?

Giả sử directory chứa các entry:

```ldif
dn: uid=mai,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: mai
cn: Mai Tran
sn: Tran
mail: mai@example.org

dn: uid=lan,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: lan
cn: Lan Nguyen
sn: Nguyen
mail: lan@example.org

dn: uid=minh,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: minh
cn: Minh Pham
sn: Pham
mail: minh@example.org
```

Ứng dụng tìm tất cả `inetOrgPerson` dưới `ou=people` và muốn sắp xếp theo `cn`:

```text
LDAP server
    |
    v
SearchRequest + SortRequestControl(cn)
    |
    v
Tìm entry phù hợp
    |
    v
Sắp xếp theo ordering matching rule của cn
    |
    v
Trả SearchResultEntry theo thứ tự
    |
    v
SearchResultDone + SortResponseControl
```

Kết quả kỳ vọng:

| Thứ tự | UID | CN |
| ---: | --- | --- |
| 1 | `lan` | Lan Nguyen |
| 2 | `mai` | Mai Tran |
| 3 | `minh` | Minh Pham |

**Sắp xếp ở server** có nghĩa directory server áp dụng quy tắc sắp xếp trước khi gửi kết quả về client. Client không cần tải toàn bộ tập kết quả để tự so sánh. Tuy nhiên, server-side sort **không tự động phân trang**, không tự tăng size limit và cũng không đảm bảo server có thể sắp xếp mọi attribute.

### 1.1. So sánh với sắp xếp ở Java

| Cách | Nơi sắp xếp | Đặc điểm |
| --- | --- | --- |
| `list.sort(...)` | Client | Cần tải các phần tử cần sắp xếp về ứng dụng |
| `Comparator.comparing(Person::getCn)` | Client | Dùng quy tắc so sánh của Java |
| Sort từng trang trong Java | Client, sau mỗi lần fetch | Chỉ sắp xếp nội bộ từng trang, không tạo thứ tự toàn cục |
| Sort control + paged results | Directory server | Server sắp xếp tập kết quả rồi client nhận từng trang nếu server hỗ trợ cả hai |

Nếu có 10.000 entry, client lấy trang đầu 100 entry rồi gọi `sort(...)`, kết quả chỉ được sắp xếp trong **100 entry đã lấy**. Một entry đứng đầu theo tên có thể nằm ở trang khác và không xuất hiện trong trang đầu. Server-side sort giúp server xác định thứ tự toàn tập trước khi chia trang.

### 1.2. Khi nào nên dùng server-side sort?

Phù hợp khi:

- Directory chứa nhiều entry và cần thứ tự nhất quán trên toàn tập tìm kiếm.
- Ứng dụng cần kết hợp sort với paged results.
- Quy tắc so sánh của LDAP schema/matching rule là quy tắc mong muốn.
- Server có hỗ trợ control và có thể xử lý sort key.

Sắp xếp phía client vẫn hợp lý nếu tập dữ liệu đã được giới hạn nhỏ và tải đầy đủ, hoặc cần thứ tự nghiệp vụ không thể biểu diễn bằng LDAP matching rule. Không nên giả định một cách sort phù hợp cho mọi endpoint. Hãy xác định **tập kết quả**, **thứ tự cần có** và **nơi chịu chi phí xử lý**.

## 2. RFC 2891 và hai LDAP control

RFC 2891 định nghĩa hai control:

| Control | OID | Vai trò |
| --- | --- | --- |
| Sort Request Control | `1.2.840.113556.1.4.473` | Client yêu cầu server sắp xếp kết quả search |
| Sort Response Control | `1.2.840.113556.1.4.474` | Server thông báo kết quả của thao tác sort |

Request control chứa danh sách sort key. Mỗi key xác định:

- `attributeType`: attribute dùng để sắp xếp.
- `orderingRule`: matching rule để so sánh; tùy chọn, nếu bỏ qua thì dùng ordering matching rule của attribute theo schema.
- `reverseOrder`: đảo chiều thứ tự; mặc định là `false`.

Danh sách sort key được sắp theo thứ tự **ưu tiên cao đến thấp**. Server so sánh key thứ nhất trước; nếu hai entry bằng nhau theo key đó, server dùng key tiếp theo.

### 2.1. Ví dụ nhiều sort key

Yêu cầu sắp xếp theo:

1. `sn` tăng dần.
2. Nếu trùng `sn`, sắp theo `givenName` tăng dần.
3. Nếu vẫn trùng, sắp theo `uid` tăng dần.

```text
SortKeyList:
  1. sn
  2. givenName
  3. uid
```

Ví dụ:

| SN | Given name | UID |
| --- | --- | --- |
| Nguyen | An | an01 |
| Nguyen | Lan | lan02 |
| Nguyen | Lan | lan08 |
| Pham | Minh | minh01 |
| Tran | Mai | mai01 |

Sort key `uid` cuối cùng giúp thứ tự ổn định hơn khi tên trùng. Đây là **tie-breaker** hữu ích cho phân trang, miễn `uid` có giá trị phù hợp và duy nhất trong tập tìm kiếm.

### 2.2. Response control độc lập với kết quả search

Một điểm rất quan trọng của RFC 2891: **sort result code độc lập với result code của LDAP Search operation**.

```text
SearchResultDone:
  LDAP operation result = success (0)
  SortResponseControl:
    sortResult = noSuchAttribute (16)
```

Search có thể hoàn thành và trả các entry, nhưng server không sắp xếp được theo key yêu cầu. Nếu client chỉ kiểm tra LDAP operation không lỗi, nó có thể nhầm kết quả chưa sắp xếp thành kết quả đã sắp xếp.

Vì vậy, **phải kiểm tra SortResponseControl**. Không suy luận rằng kết quả đã được sort chỉ vì search không ném exception, danh sách trông có vẻ đúng thứ tự hoặc server trả `SearchResultDone success`.

## 3. Sort key và matching rule của schema

Server không nhất thiết so sánh attribute giống cách Java gọi `String.compareTo(...)`. LDAP sort control dùng **ordering matching rule** gắn với attribute type hoặc rule được client chỉ định.

| Attribute | Kiểu dữ liệu mong muốn | Điều cần kiểm tra |
| --- | --- | --- |
| `cn` | Directory String | Ordering rule và cách so sánh hoa/thường |
| `sn` | Directory String | Ordering rule của surname |
| `uid` | Directory String | Quy tắc so sánh identifier |
| `employeeNumber` | Integer hoặc Directory String tùy schema | Nếu lưu dạng chuỗi, thứ tự có thể là lexical |
| `modifyTimestamp` | Generalized Time | Server có ordering matching rule tương ứng |

### 3.1. Thứ tự chuỗi khác thứ tự số

Nếu `employeeNumber` được lưu như chuỗi:

```text
2
10
100
20
```

Sort từ điển có thể cho:

```text
10
100
2
20
```

Nếu nghiệp vụ cần thứ tự số học, attribute cần syntax và ordering matching rule phù hợp với kiểu số. **Đổi kiểu Java sau khi đọc không thay đổi cách server đã sort**.

### 3.2. Ordering rule mặc định

Khi request không chỉ định `orderingRule`, server dùng ordering matching rule được schema định nghĩa cho attribute. Đây thường là lựa chọn đúng vì directory biết cú pháp và quy tắc so sánh của dữ liệu.

Không nên chọn matching rule OID tùy tiện. Nếu rule không phù hợp attribute type, server có thể trả lỗi `inappropriateMatching (18)`. Nếu attribute không tồn tại hoặc không nhận diện được, có thể gặp `noSuchAttribute (16)` hoặc lỗi khác theo server.

### 3.3. Giá trị bị thiếu và attribute đa trị

RFC 2891 quy định một entry không có giá trị cho sort key được xem như có giá trị `NULL`. Với một sort key:

- Ở thứ tự tăng dần, giá trị NULL được xếp sau các giá trị hợp lệ.
- Khi đảo chiều, giá trị NULL có thể đứng trước các giá trị hợp lệ.

Nếu attribute sort key có nhiều giá trị, RFC 2891 nói server nên dùng **giá trị nhỏ nhất** theo ordering rule của attribute, trừ khi có control khác ảnh hưởng thứ tự.

Vì thế, không nên dùng attribute đa trị làm khóa sort nếu nghiệp vụ cần một giá trị chính duy nhất mà schema không thể hiện rõ.

## 4. SortControlExchange trong Spring LDAP 4.1+

Spring LDAP **4.1** giới thiệu:

- `org.springframework.ldap.control.SortControlExchange`
- `org.springframework.ldap.control.ControlExchangeDirContextProcessor`

`SortControlExchange` ghép request control và response control. `ControlExchangeDirContextProcessor` gắn request control vào `LdapContext` trước search, rồi lấy response control sau search.

Đây là API được Spring LDAP khuyến nghị thay thế `SortControlDirContextProcessor` đã deprecated.

### 4.1. Ví dụ tìm nhân viên theo CN

Giả sử `LdapContextSource` đã cấu hình base `dc=example,dc=org`. Ta tìm `inetOrgPerson` dưới `ou=people` và yêu cầu server sort theo `cn`:

```java
import java.util.List;
import javax.naming.NamingException;
import javax.naming.directory.SearchControls;
import javax.naming.ldap.SortControl;
import javax.naming.ldap.SortResponseControl;
import org.springframework.ldap.control.ControlExchangeDirContextProcessor;
import org.springframework.ldap.control.SortControlExchange;
import org.springframework.ldap.core.LdapTemplate;

public List<PersonSummary> findPeopleSortedByCn(
        LdapTemplate ldapTemplate) throws NamingException {

    SearchControls controls = new SearchControls();
    controls.setSearchScope(SearchControls.SUBTREE_SCOPE);
    controls.setReturningAttributes(
            new String[] {"uid", "cn", "sn", "mail"});
    controls.setCountLimit(200);
    controls.setTimeLimit(3_000);

    SortControlExchange exchange =
            new SortControlExchange("cn", "uid");

    ControlExchangeDirContextProcessor<SortControl, SortResponseControl>
            processor =
            new ControlExchangeDirContextProcessor<>(exchange);

    List<PersonSummary> people = ldapTemplate.search(
            "ou=people",
            "(objectClass=inetOrgPerson)",
            controls,
            personSummaryMapper(),
            processor);

    SortResponseControl response = processor.getExchange().getResponse();
    if (response == null || !response.isSorted()) {
        throw new IllegalStateException(
                "LDAP server did not confirm the requested sort");
    }
    return people;
}
```

Đây là ví dụ theo API Spring LDAP 4.1+. Phương thức `personSummaryMapper()` là mapper do ứng dụng định nghĩa, trả về DTO; ví dụ lược bỏ phần cài đặt mapper để tập trung vào control.

**Những điểm cần hiểu:**

- `new SortControlExchange("cn", "uid")` khai báo danh sách thuộc tính sắp xếp theo thứ tự ưu tiên.
- `ControlExchangeDirContextProcessor` thực hiện vòng đời request/response control.
- `LdapTemplate.search(..., processor)` gọi processor quanh thao tác search.
- `processor.getExchange().getResponse()` lấy response control đã nhận.
- Nếu response bị thiếu hoặc `isSorted()` không thành công, ứng dụng không được trả danh sách với cam kết “đã sort”.

Phương thức `SortResponseControl.isSorted()` có thể ném `NamingException` khi sort result là lỗi. Trong service thực tế, hãy chuyển lỗi này thành exception nghiệp vụ hoặc lỗi hạ tầng phù hợp, đồng thời giữ lại mã lỗi để quan sát.

### 4.2. Chỉ tạo processor cho từng search

Không giữ một `ControlExchangeDirContextProcessor` hoặc exchange có response cũ làm field singleton rồi dùng lại cho nhiều request. Processor giữ trạng thái response control của lần search; tạo instance mới cho mỗi lần tìm kiếm giúp tránh trộn response giữa các truy vấn đồng thời.

### 4.3. Kiểm tra response rõ ràng hơn

```java
SortResponseControl response = processor.getExchange().getResponse();

if (response == null) {
    throw new IllegalStateException(
            "Directory omitted the sort response control");
}

if (response.getResultCode() != 0) {
    String failedAttribute = response.getAttributeID();
    throw new IllegalStateException(
            "LDAP sort failed; resultCode="
                    + response.getResultCode()
                    + ", attribute="
                    + failedAttribute);
}
```

Result code `0` nghĩa là sort thành công. Nếu response control không xuất hiện, RFC 2891 khuyến nghị client giả định sort control đã bị bỏ qua. Không âm thầm fallback sang dữ liệu chưa sort nếu hợp đồng API đòi hỏi thứ tự chính xác.

## 5. Spring LDAP cũ hơn: SortControlDirContextProcessor

Trong các phiên bản Spring LDAP trước 4.1, có thể gặp:

```java
import org.springframework.ldap.control.SortControlDirContextProcessor;
```

Ví dụ:

```java
SearchControls controls = new SearchControls();
controls.setSearchScope(SearchControls.SUBTREE_SCOPE);
controls.setReturningAttributes(new String[] {"uid", "cn"});

SortControlDirContextProcessor processor =
        new SortControlDirContextProcessor("cn");

List<PersonSummary> people = ldapTemplate.search(
        "ou=people",
        "(objectClass=inetOrgPerson)",
        controls,
        personSummaryMapper(),
        processor);

if (!processor.isSorted()) {
    throw new IllegalStateException(
            "LDAP server did not sort the results");
}
```

`SortControlDirContextProcessor` cung cấp `isSorted()` và `getResultCode()` để kiểm tra response. Class này có trạng thái nên **tạo instance mới cho từng search**.

**Lưu ý phiên bản:** API này có trong Spring LDAP 3.3, nhưng đã deprecated trong Spring LDAP 4.1 và được thay bằng `SortControlExchange` cùng `ControlExchangeDirContextProcessor`. Khi dùng Spring Boot, kiểm tra phiên bản Spring LDAP được quản lý bởi BOM trước khi chọn import; không trộn ví dụ 4.1+ vào dự án chỉ có 3.x.

## 6. Criticality: server phải sort hay có thể bỏ qua?

Sort request control có trường **criticality**:

| Criticality | Hành vi khi server không hỗ trợ hoặc không thể sort |
| --- | --- |
| `TRUE` | Server phải thực hiện sort hoặc từ chối search; không được trả kết quả như thể đã sort |
| `FALSE` | Server có thể bỏ qua sort control và trả kết quả search không được sắp xếp |

Nếu sort là yêu cầu bắt buộc của hợp đồng API, ứng dụng phải dùng chính sách fail-closed: không trả kết quả chưa được xác nhận là đã sort.

### 6.1. JNDI SortControl khi cần chỉ định criticality

JNDI cung cấp `javax.naming.ldap.SortControl`:

```java
import javax.naming.ldap.Control;
import javax.naming.ldap.LdapContext;
import javax.naming.ldap.SortControl;
import javax.naming.ldap.Control;
import javax.naming.ldap.SortKey;

SortControl sortControl = new SortControl(
        new SortKey[] {
            new SortKey("sn"),
            new SortKey("givenName"),
            new SortKey("uid")
        },
        Control.CRITICAL);

LdapContext context = (LdapContext) contextSource.getReadOnlyContext();
try {
    context.setRequestControls(new Control[] {sortControl});
    // Thực hiện context.search(...), đọc hết NamingEnumeration,
    // rồi lấy context.getResponseControls().
} finally {
    context.close();
}
```

Đây là ví dụ JNDI trực tiếp, minh họa cách tạo control với criticality rõ ràng. Khi dùng `LdapTemplate`, nên ưu tiên API control exchange của phiên bản tương ứng; nếu cần cấu hình criticality đặc biệt mà wrapper không cung cấp, có thể triển khai `ControlExchange` riêng hoặc `DirContextProcessor` phù hợp.

### 6.2. SortControlExchange và criticality

Constructor công khai của `SortControlExchange` nhận danh sách tên attribute cần sort. Nó là abstraction tiện dụng để trao đổi request/response; nếu use case cần điều khiển tham số thấp hơn như `SortKey` đảo chiều, matching rule hoặc criticality cụ thể, cần kiểm tra API của phiên bản Spring LDAP đang dùng và có thể cần tạo request control JNDI tùy chỉnh.

Không suy đoán criticality từ việc server đã trả kết quả. Dù control có criticality nào, **response control vẫn phải được kiểm tra** trước khi ứng dụng khẳng định thứ tự.

## 7. Sắp xếp giảm dần và matching rule tùy chỉnh

JNDI có `SortKey` cho phép khai báo chiều tăng/giảm và matching rule:

```java
import javax.naming.ldap.SortControl;
import javax.naming.ldap.SortKey;

SortKey[] keys = {
    new SortKey("modifyTimestamp", false, null),
    new SortKey("uid", true, null)
};

SortControl sortControl = new SortControl(
        keys,
        Control.CRITICAL);
```

Ý nghĩa:

- `modifyTimestamp` giảm dần (mới nhất trước).
- Nếu thời điểm trùng, `uid` tăng dần.
- `null` ở tham số matching rule nghĩa là dùng ordering matching rule mặc định của attribute theo schema.

Nếu cần matching rule cụ thể, truyền tên hoặc OID phù hợp:

```java
SortKey lastNameKey = new SortKey(
        "sn",
        true,
        "2.5.13.3");
```

OID trong ví dụ là một matching rule phổ biến; **chỉ dùng khi rule đó được server hỗ trợ và phù hợp syntax của attribute**. Không copy một OID từ ví dụ vào mọi schema.

### 7.1. Nhiều khóa với chiều khác nhau

Ví dụ nghiệp vụ:

1. Trạng thái ưu tiên giảm dần theo attribute có ordering rule phù hợp.
2. Ngày tạo tăng dần.
3. UID tăng dần để ổn định.

```java
SortKey[] keys = {
    new SortKey("priority", false, null),
    new SortKey("createTimestamp", true, null),
    new SortKey("uid", true, null)
};
```

Tên attribute và matching rule phải tồn tại trong schema. Nếu `priority` được lưu thành chuỗi, server có thể sắp xếp lexical thay vì số học; cần xác định syntax trước khi dùng.

## 8. Server-side sort và paged results

Sort control và paged results là **hai control độc lập**:

- RFC 2891: sắp xếp toàn bộ tập kết quả.
- RFC 2696: chia tập kết quả thành các trang và tiếp tục bằng cookie.

Khi kết hợp, RFC 2891 quy định sort key list phải được gửi trong **mọi SearchRequest của cùng một chuỗi paging** và **không được thay đổi** giữa các request. Server cần sắp xếp toàn bộ tập kết quả trước khi trả các trang; không được chỉ sort từng trang riêng lẻ vì sẽ tạo thứ tự sai toàn cục.

```text
Search page 1: filter F, sort cn+uid, page size 100
       |
       v
Server sort toàn bộ tập kết quả
       |
       v
Trả entry 1..100 + cookie A + sort response
       |
       v
Search page 2: filter F, sort cn+uid, cookie A
       |
       v
Trả entry 101..200 + cookie B + sort response
       |
       v
Tiếp tục cho đến khi cookie rỗng
```

### 8.1. Không sort từng trang sau khi nhận

Sai:

```text
Page 1 -> client sort 100 entry
Page 2 -> client sort 100 entry
Page 3 -> client sort 100 entry
```

Kết quả không đảm bảo thứ tự toàn cục giữa các trang.

Đúng:

```text
Server sort toàn bộ tập kết quả
       |
       v
Server chia thành page 1, page 2, page 3
       |
       v
Client đọc từng page theo cookie
```

### 8.2. Kết nối và cookie

Paged results dùng cookie do server cấp. Để tiếp tục một chuỗi paging, client phải tuân thủ yêu cầu của server/provider về việc tái sử dụng connection/context. Spring LDAP cung cấp `SingleContextSource` để thực hiện nhiều lần search qua cùng một context:

```java
SingleContextSource.doWithSingleContext(
        contextSource,
        operations -> {
            // Tạo paged-results processor.
            // Mỗi vòng lặp giữ nguyên sort key list.
            // Search page kế tiếp bằng cookie từ response trước.
            return readAllPages(operations);
        });
```

Đây là code rút gọn; chi tiết cookie/processor phụ thuộc API paging của phiên bản Spring LDAP. Nếu dùng `PagedResultsControlExchangeDirContextProcessor` (Spring LDAP 4.1+), giữ nguyên sort key list trong suốt vòng lặp và kiểm tra sort response theo từng response page theo yêu cầu của server.

**Không đổi sort key giữa các trang** của cùng result set. Nếu muốn đổi từ `cn` sang `uid`, hãy bắt đầu một chuỗi search/paging mới.

### 8.3. Sort không thay thế giới hạn kết quả

Server-side sort không tự bỏ qua:

- Client `countLimit`.
- Server administrative size limit.
- Search time limit.
- ACL và quyền đọc.
- Giới hạn tài nguyên của server.

Một search có sort control vẫn có thể trả `sizeLimitExceeded` hoặc `timeLimitExceeded`. Paging không được xem là cách vượt quyền hay né giới hạn quản trị.

## 9. Sort key, tie-breaker và tính ổn định của phân trang

Nếu sort theo `cn` nhưng nhiều người có cùng CN, thứ tự giữa họ có thể không ổn định khi server không có key phụ. Khi kết hợp paging, điều này có thể làm entry xuất hiện ở trang khác sau lần truy vấn kế tiếp, hoặc gây trùng/thiếu entry khi dữ liệu thay đổi.

Hãy chọn key phụ ổn định:

```java
SortControlExchange exchange =
        new SortControlExchange("cn", "uid");
```

Nếu `uid` duy nhất trong naming context, nó làm tie-breaker tốt hơn. Nếu nhiều OU có thể chứa cùng UID, cần chọn attribute hoặc khóa phù hợp phạm vi search.

**Sort ổn định không đồng nghĩa snapshot nhất quán.** Nếu directory thay đổi giữa các page, tập kết quả vẫn có thể đổi tùy server và control; RFC 2696 không tự tạo snapshot giao dịch cho toàn bộ result set.

## 10. Search scope và sort key

Sort chỉ áp dụng cho những entry đã khớp base, scope và filter.

| Search scope | Entry được xét |
| --- | --- |
| `OBJECT_SCOPE` | Chính entry tại base |
| `ONELEVEL_SCOPE` | Các entry con trực tiếp |
| `SUBTREE_SCOPE` | Base và các entry bên dưới |

Ví dụ:

```java
SearchControls controls = new SearchControls();
controls.setSearchScope(SearchControls.SUBTREE_SCOPE);
controls.setReturningAttributes(
        new String[] {"uid", "cn", "sn"});
```

Nếu dùng `ONELEVEL_SCOPE` ở `ou=people` nhưng người dùng nằm dưới `ou=contractors,ou=people`, họ không thuộc tập kết quả và sẽ không được sort. Khi thấy thiếu entry, kiểm tra base/scope/filter trước khi nghi ngờ sort control.

### 10.1. Sort key không bắt buộc là returned attribute

Server có thể dùng sort key để sắp xếp ngay cả khi client không yêu cầu trả attribute đó trong danh sách returning attributes. Tuy nhiên:

- Nếu mapper cần hiển thị giá trị, hãy yêu cầu trả attribute.
- Nếu muốn kiểm tra tie-breaker phía client, hãy yêu cầu attribute tương ứng.
- Không trả dữ liệu nhạy cảm chỉ vì nó là sort key; cân nhắc ACL và side channel qua thứ tự.

## 11. Hạn chế server, index và hiệu năng

Server-side sort chuyển công việc sắp xếp sang directory server; điều đó không có nghĩa thao tác miễn phí. Server có thể phải thu thập, so sánh và sắp xếp nhiều entry trước khi gửi kết quả.

Các yếu tố ảnh hưởng:

- Số lượng entry khớp filter.
- Sort key có index phù hợp hay không.
- Schema và matching rule.
- Số lượng sort key.
- Số lượng giá trị trong attribute đa trị.
- Server load, memory và giới hạn administrative.
- Search scope và filter selectivity.

Một số directory có yêu cầu hoặc tối ưu đặc biệt đối với index sort key; một số có thể từ chối sort trên attribute không hỗ trợ. Cấu hình index là **server-specific**, không được tạo chỉ mục bằng annotation Spring Data LDAP.

### 11.1. Tối ưu trước khi tăng giới hạn

Nếu sort chậm:

1. Thu hẹp base DN và search scope.
2. Dùng filter chọn lọc, tận dụng equality/substring index phù hợp.
3. Chỉ yêu cầu các attribute response cần thiết.
4. Giảm số sort key nếu nghiệp vụ cho phép.
5. Kiểm tra ordering rule và index của sort key trên server.
6. Đo latency và server log trước/sau thay đổi.

Không tăng timeout hoặc count limit một cách mù quáng. Sort toàn bộ một tập rất lớn có thể tiêu tốn CPU/bộ nhớ của directory và ảnh hưởng client khác.

### 11.2. Giới hạn bảo mật

RFC 2891 lưu ý server-side sorting có thể được kết hợp với việc thay đổi filter để đọc dần một tập lớn dữ liệu, kể cả khi server có administrative limit về số record trả về trong một search. Vì vậy:

- Duy trì ACL phù hợp cho entry và attribute.
- Giữ administrative limit ở server.
- Không cho client tùy ý chọn sort key hoặc filter attribute nhạy cảm.
- Áp dụng rate limit và giám sát search lớn.
- Không dùng sort control như một cách né giới hạn kết quả.

## 12. Sort control không phải Sort trong Java hay Spring Data

Các khái niệm sau có thể cùng mang tên “sort”, nhưng không tương đương:

| Cơ chế | Tầng | Có gửi LDAP sort control không? |
| --- | --- | --- |
| `list.sort(comparator)` | Java client | Không |
| `Comparator.comparing(Person::getCn)` | Java client | Không |
| Spring Data `Sort`/repository abstraction (nếu module/version hỗ trợ) | Spring Data | Không nên mặc định rằng có |
| JNDI `SortControl` | LDAP protocol client | Có |
| Spring LDAP `SortControlExchange` | LDAP protocol client | Có |
| Spring LDAP `SortControlDirContextProcessor` (API cũ) | LDAP protocol client | Có |

Một repository method trả về kết quả theo thứ tự không chứng minh server-side sort control đã được gửi. Khi cần xác nhận control, hãy kiểm tra response control hoặc quan sát LDAP request trong integration test.

Với sort control tùy chỉnh, `LdapTemplate` và `DirContextProcessor` là điểm tích hợp rõ ràng. Đừng giả định `Pageable`/`Sort` của một module Spring Data bất kỳ được dịch thành RFC 2891 control nếu tài liệu/version không xác nhận.

## 13. Các mã lỗi sort thường gặp

Sort response control có result code riêng. Một số mã đáng chú ý theo RFC 2891:

| Result code | Tên | Ý nghĩa thường gặp |
| ---: | --- | --- |
| 0 | `success` | Server đã sort theo key yêu cầu |
| 1 | `operationsError` | Lỗi xử lý nội bộ |
| 3 | `timeLimitExceeded` | Không hoàn tất sort trong thời gian cho phép |
| 8 | `strongAuthRequired` | Server yêu cầu xác thực mạnh hơn để trả kết quả đã sort |
| 11 | `adminLimitExceeded` | Vượt giới hạn quản trị |
| 16 | `noSuchAttribute` | Không nhận diện được sort attribute |
| 18 | `inappropriateMatching` | Matching rule không phù hợp |
| 50 | `insufficientAccessRights` | Không đủ quyền để trả kết quả đã sort |
| 51 | `busy` | Server quá tải |
| 53 | `unwillingToPerform` | Server không thể/không muốn thực hiện sort |
| 80 | `other` | Lỗi khác |

Đây là **sort result code trong response control**, không phải lúc nào cũng là LDAP operation result code của SearchRequest. Hãy ghi nhận cả hai nếu server cung cấp.

## 14. Xử lý khi server không hỗ trợ sort

Một server có thể không hỗ trợ RFC 2891, hoặc hỗ trợ control nhưng không hỗ trợ attribute/matching rule cụ thể.

### 14.1. API bắt buộc có thứ tự

Ví dụ export dữ liệu theo đúng thứ tự để đối soát:

- Gửi sort control.
- Kiểm tra response control.
- Nếu không có response hoặc sort result thất bại, **không trả kết quả như thể đã sort**.
- Trả lỗi phù hợp hoặc chuyển sang đường xử lý khác có bảo đảm.

### 14.2. API chỉ ưu tiên thứ tự

Ví dụ danh sách gợi ý:

- Có thể chấp nhận kết quả chưa sort nếu hợp đồng cho phép.
- Ghi rõ fallback đã xảy ra.
- Nếu sort ở Java, chỉ làm sau khi đã nhận **toàn bộ tập kết quả cần sắp xếp**.
- Không sort từng trang rồi tuyên bố toàn bộ directory đã được sắp xếp.

### 14.3. Fallback phải có giới hạn

Nếu fallback client-side:

- Giới hạn số entry tải về.
- Không tải toàn bộ DIT vô hạn.
- Không fallback cho dữ liệu phân quyền hoặc compliance nếu thứ tự/đầy đủ là điều kiện nghiệp vụ.
- Đo và log trạng thái `server-sort-success` hay `client-sort-fallback`.

## 15. Kiểm thử server-side sorting

Unit test cho việc tạo DTO không chứng minh LDAP server đã sort. Cần integration test với directory hỗ trợ control hoặc test server phù hợp.

### 15.1. Chuẩn bị dữ liệu có thứ tự khác nhau

Seed các entry cố ý không theo thứ tự:

```ldif
dn: uid=person03,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: person03
cn: Tran Mai
sn: Tran

dn: uid=person01,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: person01
cn: Nguyen Lan
sn: Nguyen

dn: uid=person02,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: person02
cn: Pham Minh
sn: Pham
```

Search theo `cn` tăng dần phải trả theo thứ tự:

```text
Nguyen Lan
Pham Minh
Tran Mai
```

Không seed theo thứ tự đã sort, vì test như vậy có thể pass ngay cả khi server bỏ qua control.

### 15.2. Kiểm tra response control

Integration test cần:

1. Gửi search với sort key.
2. Đọc hết search result enumeration.
3. Kiểm tra response control có tồn tại.
4. Xác nhận `SortResponseControl.isSorted()` là true hoặc result code là 0.
5. Kiểm tra thứ tự entry thực tế.
6. Thử sort key không tồn tại hoặc matching rule không hợp lệ trên server test, xác minh ứng dụng không báo thành công.

### 15.3. Kiểm thử criticality

Với JNDI direct:

- Criticality `TRUE` và server không hỗ trợ: kỳ vọng server từ chối search với `unavailableCriticalExtension`.
- Criticality `FALSE`: server có thể bỏ qua sort control và trả kết quả không sort.

Đừng chỉ kiểm tra có entry được trả về. Hãy xác minh cả operation result và sort response.

### 15.4. Kiểm thử khi kết hợp paging

Tạo ít nhất vài trăm entry và:

- Dùng page size nhỏ để tạo nhiều trang.
- Giữ nguyên sort key list ở mọi page request.
- Xác minh toàn bộ kết quả khi ghép các page vẫn theo thứ tự toàn cục.
- Kiểm tra sort response control ở từng page nếu server gửi.
- Thử thay sort key giữa các page trong test negative và xác minh ứng dụng không làm vậy.
- Mô phỏng dữ liệu thay đổi giữa các trang để hiểu giới hạn snapshot.

### 15.5. Kiểm thử trường hợp đặc biệt

| Tình huống | Kỳ vọng cần xác minh |
| --- | --- |
| Hai entry trùng CN | Sort key phụ tạo thứ tự ổn định |
| Entry thiếu CN | Vị trí NULL theo RFC và chiều sort |
| Attribute đa trị | Server dùng ordering rule phù hợp, giá trị nhỏ nhất theo RFC nếu áp dụng |
| Sort key là chuỗi chứa số | Thứ tự phù hợp syntax/matching rule, không mặc định là số học |
| Sort key không có trong schema | Response control báo lỗi phù hợp |
| Account thiếu quyền sort | Server có thể từ chối với lỗi quyền |
| Directory không hỗ trợ control | Không khẳng định kết quả đã sort |
| Search vượt time/size limit | Xử lý độc lập với sort response |
| Paged result | Sort key list không thay đổi giữa các page |

## 16. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Danh sách trông có vẻ sorted nhưng response control không có | Server bỏ qua control hoặc provider không trả response | Không coi là đã xác nhận; kiểm tra criticality/server support |
| Search thành công nhưng sort thất bại | Search result và sort result là hai mã độc lập | Kiểm tra `SortResponseControl` |
| `unavailableCriticalExtension` | Server không hỗ trợ control bắt buộc hoặc không thể thực hiện | Kiểm tra sản phẩm/version/cấu hình |
| `noSuchAttribute (16)` | Sort key không có/không nhận diện trong schema | Kiểm tra attribute type và chính tả |
| `inappropriateMatching (18)` | Ordering rule không phù hợp syntax | Bỏ matching rule tùy chỉnh hoặc chọn rule đúng |
| Kết quả chuỗi số sai thứ tự mong muốn | Attribute lưu dạng string, ordering lexical | Sửa schema/data model hoặc dùng kiểu số đúng |
| Entry thiếu CN đứng ở cuối/đầu | Giá trị sort key NULL theo quy tắc RFC | Xử lý null trong yêu cầu nghiệp vụ |
| Hai entry cùng CN đổi vị trí giữa lần gọi | Không có tie-breaker | Thêm key ổn định như UID |
| Trang đầu không chứa tên nhỏ nhất | Sort từng trang ở client hoặc server không sort toàn tập | Dùng sort control kết hợp paging đúng chuẩn |
| Sort rất chậm | Tập kết quả lớn, thiếu index, nhiều key | Thu hẹp query, xem index và server log |
| Repository trả kết quả không đúng thứ tự | Repository abstraction không gửi control mong muốn | Dùng LdapTemplate/control processor hoặc xác minh implementation |
| `SortControlDirContextProcessor` bị deprecated | Đang dùng API Spring LDAP cũ trong 4.1+ | Chuyển sang SortControlExchange/ControlExchangeDirContextProcessor |
| `getResponse()` là null | Server/provider không trả sort response control | Xem là chưa xác nhận; kiểm tra hỗ trợ và control request |
| Response control cũ bị đọc lại | Dùng lại processor có trạng thái | Tạo processor mới cho mỗi search |
| Sort theo attribute không được trả về | Nhầm sort key với returned attributes | Sort key không bắt buộc phải trả, nhưng mapper cần thì thêm projection |
| Dùng sort để lấy dần toàn directory | Lạm dụng control để né administrative limit | ACL, limit server, rate limit và kiểm soát truy vấn |

## 17. Bài tập áp dụng

**Câu 1.** Bạn cần sắp xếp nhân viên theo `sn`, sau đó `givenName`, cuối cùng `uid`. Hãy giải thích thứ tự ưu tiên của ba sort key.

*Gợi ý:* Sort key đầu tiên có ưu tiên cao nhất. Các key sau chỉ dùng khi các key trước bằng nhau.

**Câu 2.** Search trả LDAP result code `success` nhưng SortResponseControl báo `noSuchAttribute (16)`. API có được tuyên bố dữ liệu đã sắp xếp không?

*Gợi ý:* Không. Sort result độc lập với search result; phải kiểm tra response control.

**Câu 3.** Sự khác nhau giữa criticality `TRUE` và `FALSE` là gì khi server không hỗ trợ sort control?

*Gợi ý:* TRUE yêu cầu server thực hiện hoặc từ chối search; FALSE cho phép server bỏ qua control và trả kết quả không sort.

**Câu 4.** Một entry có hai giá trị `mail`. Nếu sort theo `mail`, có thể giả định server dùng giá trị đầu tiên không?

*Gợi ý:* Không. RFC quy định server nên dùng giá trị nhỏ nhất theo ordering rule khi attribute đa trị và không có control khác ảnh hưởng.

**Câu 5.** Bạn sort trang 1, trang 2 và trang 3 riêng bằng Java. Điều đó có đảm bảo thứ tự toàn cục không?

*Gợi ý:* Không. Phải sort toàn bộ tập trước khi chia trang, ví dụ server-side sort control kết hợp paged results theo RFC.

**Câu 6.** Server trả entry nhưng không có SortResponseControl. Có thể mặc định control đã thành công không?

*Gợi ý:* Không. RFC 2891 khuyến nghị client giả định control bị bỏ qua nếu response control không xuất hiện.

**Câu 7.** `employeeNumber` được lưu dưới dạng chuỗi. Vì sao thứ tự `10` có thể đứng trước `2`?

*Gợi ý:* Server áp dụng ordering matching rule theo schema; chuỗi có thể được so sánh lexical. Cần syntax/matching rule số học phù hợp.

**Câu 8.** Search dưới toàn naming context, filter rộng, sort theo `cn` mất nhiều giây. Hãy nêu các bước điều tra trước khi tăng timeout.

*Gợi ý:* Thu hẹp base/scope/filter, kiểm tra index sort key, số entry khớp, matching rule và server log.

**Câu 9.** Trong Spring LDAP 4.1+, class nào thay thế `SortControlDirContextProcessor`?

*Gợi ý:* `SortControlExchange` kết hợp `ControlExchangeDirContextProcessor`.

**Câu 10.** Vì sao nên thêm `uid` sau `cn` khi phân trang danh bạ?

*Gợi ý:* Nhiều entry có thể trùng CN. UID tạo thứ tự phụ ổn định hơn trong phạm vi naming context nếu duy nhất.

## 18. Ghi nhớ

- **Server-side sort** là LDAP control theo **RFC 2891**, không phải Java `Comparator` và không tự động tương đương với Spring Data `Sort`.
- Request OID là **`1.2.840.113556.1.4.473`**, response OID là **`1.2.840.113556.1.4.474`**.
- Sort key được khai báo theo thứ tự ưu tiên cao đến thấp; server dùng ordering matching rule theo schema nếu client không chỉ định rule riêng.
- Giá trị thiếu được xem là NULL; attribute đa trị có quy tắc sort riêng theo RFC.
- **Search success không chứng minh sort success.** Phải đọc `SortResponseControl` và chỉ xác nhận khi result code là 0/`isSorted()` true.
- Nếu response control không có, giả định sort control đã bị bỏ qua; không tự coi danh sách đã sorted.
- Criticality TRUE yêu cầu server sort hoặc từ chối search; FALSE cho phép server bỏ qua control.
- Spring LDAP 4.1+ khuyến nghị `SortControlExchange` + `ControlExchangeDirContextProcessor`; `SortControlDirContextProcessor` đã deprecated.
- Khi kết hợp RFC 2696 paged results, giữ sort key list giống nhau trong mọi page request; server phải sort toàn result set, không sort từng page riêng.
- Sort control không thay thế size/time limit, ACL, index hoặc administrative policy; sort trên tập lớn có thể tốn tài nguyên.
- Thêm tie-breaker ổn định nếu cần thứ tự nhất quán; sort không tự tạo snapshot khi directory thay đổi.

**Tài liệu tham khảo chính thức:**

- [RFC 2891 — LDAP Control Extension for Server Side Sorting of Search Results](https://www.rfc-editor.org/rfc/rfc2891): request/response controls, criticality, sort result, nhiều sort key, giá trị NULL và tương tác paging.
- [Spring LDAP API — SortControlExchange](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/control/SortControlExchange.html): API mới từ Spring LDAP 4.1 để quản lý sort request/response.
- [Spring LDAP API — ControlExchangeDirContextProcessor](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/control/ControlExchangeDirContextProcessor.html): gắn request control và đọc response control qua `DirContextProcessor`.
- [Spring LDAP API — SortControlDirContextProcessor](https://docs.spring.io/spring-ldap/docs/3.3.x/api/org/springframework/ldap/control/SortControlDirContextProcessor.html): API sort processor ở dòng Spring LDAP 3.3; đã deprecated từ 4.1.
- [Java API — SortControl](https://docs.oracle.com/en/java/javase/17/docs/api/java.naming/javax/naming/ldap/SortControl.html): JNDI sort request control và criticality.
- [Java API — SortKey](https://docs.oracle.com/en/java/javase/17/docs/api/java.naming/javax/naming/ldap/SortKey.html): attribute ID, chiều sort và matching rule.
- [Java API — SortResponseControl](https://docs.oracle.com/en/java/javase/17/docs/api/java.naming/javax/naming/ldap/SortResponseControl.html): `isSorted()`, result code, attribute gây lỗi.
- [Spring LDAP — Processing the DirContext](https://docs.spring.io/spring-ldap/reference/processing-the-dircontext.html): tích hợp request/response control qua processor.
- [RFC 2696 — LDAP Control Extension for Simple Paged Results Manipulation](https://www.rfc-editor.org/rfc/rfc2696): cookie và phân trang kết quả LDAP.
- [Spring Data LDAP Reference](https://docs.spring.io/spring-data/ldap/reference/): repository abstraction và các thao tác LDAP.
