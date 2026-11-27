# Matching rule khi sort attribute

## Mục tiêu học tập

Trong chương **Phân trang và sorting** của **Spring LDAP**, sắp xếp danh sách entry không đơn thuần là yêu cầu server xếp theo một thuộc tính. LDAP còn cần biết **quy tắc so sánh** tương ứng với kiểu dữ liệu của thuộc tính. Quy tắc này được gọi là **matching rule**, đặc biệt là nhóm `ORDERING`.

Sau bài này, bạn có thể:

- Phân biệt `EQUALITY`, `ORDERING` và `SUBSTR` trong schema LDAP.
- Giải thích vì sao sắp xếp chuỗi, số nguyên, thời gian cần quy tắc phù hợp, và vì sao sắp xếp LDAP có thể khác thứ tự theo ngôn ngữ người dùng.
- Hiểu trường `orderingRule` trong **server-side sort control** theo RFC 2891; biết khi nào dùng rule từ schema và khi nào chỉ định OID tường minh.
- Dùng `LdapTemplate.search(...)` với `SortControlDirContextProcessor`, hoặc JNDI `SortKey` khi cần chọn matching rule cụ thể.
- Kiểm tra phản hồi sort từ server, xử lý `inappropriateMatching`, dữ liệu thiếu khóa, nhiều giá trị và khóa bằng nhau.
- Kết hợp sort với paged results mà không làm sai thứ tự trên toàn bộ tập dữ liệu.

Các ví dụ dùng **Spring LDAP** với `LdapTemplate` và `ContextSource`, nhưng nguyên lý so khớp cũng áp dụng khi truy vấn bằng JNDI, `LdapClient` hoặc ODM. Các API chỉ gửi yêu cầu; LDAP server và schema quyết định quy tắc nào thực sự hỗ trợ.

## 1. Vì sao sort cần matching rule?

Giả sử dưới `ou=people,dc=example,dc=org` có các entry:

~~~ldif
dn: uid=u01,ou=people,dc=example,dc=org
objectClass: inetOrgPerson
uid: u01
cn: Anh
sn: Nguyen

dn: uid=u02,ou=people,dc=example,dc=org
objectClass: inetOrgPerson
uid: u02
cn: anh
sn: Tran

dn: uid=u03,ou=people,dc=example,dc=org
objectClass: inetOrgPerson
uid: u03
cn: Bình
sn: Le
~~~

Khi chọn `cn` làm khóa sắp xếp, server phải trả lời: `Anh` và `anh` có tương đương không? Dấu tiếng Việt được xử lý thế nào? Nếu hai giá trị bằng nhau theo rule, entry nào đứng trước? Những câu hỏi này được xác định bởi **quy tắc so sánh**, các khóa phụ và hành vi server, chứ không chỉ bởi tên attribute.

Chẳng hạn `caseIgnoreOrderingMatch` so sánh chuỗi sau bước chuẩn bị phù hợp và xử lý khác biệt chữ hoa/thường; `caseExactOrderingMatch` vẫn phân biệt chữ hoa/thường. Cả hai đều **không phải mặc định là collation theo tiếng Việt**.

> **Phân biệt:** LDAP server-side sort sắp xếp kết quả trên server trước khi gửi về. Lấy một trang rồi gọi `list.sort(...)` trong Java chỉ sắp xếp **trang đó**, không bảo đảm toàn bộ kết quả LDAP được sắp xếp đúng.

## 2. EQUALITY, ORDERING và SYNTAX trong schema

Một loại thuộc tính (attribute type) trong schema LDAP có thể mô tả:

| Thành phần | Vai trò | Liên quan đến sort |
| --- | --- | --- |
| `SYNTAX` | Loại giá trị hợp lệ: Directory String, Integer, Generalized Time... | Quyết định rule nào có thể áp dụng |
| `EQUALITY` | So sánh hai giá trị có bằng nhau không | Không tự định nghĩa quan hệ trước/sau |
| `ORDERING` | So sánh thứ tự các giá trị | Rule dùng cho sort khi có và được server hỗ trợ |
| `SUBSTR` | So khớp chuỗi con trong filter | Không thay thế ORDERING |
| `SUP` | Attribute cha có thể cung cấp các định nghĩa được kế thừa | Cần xét định nghĩa thực tế sau kế thừa |
| `SINGLE-VALUE` | Giới hạn thuộc tính chỉ có một giá trị | Tránh nhập nhằng với thuộc tính đa giá trị |

Ví dụ định nghĩa *minh họa*, không phải schema chuẩn có sẵn:

~~~text
( 1.3.6.1.4.1.99999.1.100
  NAME 'staffPriority'
  DESC 'Muc uu tien trong thu nghiem'
  EQUALITY integerMatch
  ORDERING integerOrderingMatch
  SYNTAX 1.3.6.1.4.1.1466.115.121.1.27
  SINGLE-VALUE )
~~~

OID `1.3.6.1.4.1.99999.1.100` chỉ để giải thích cấu trúc; khi triển khai thật phải dùng OID được tổ chức quản lý hợp lệ. Trong ví dụ, `staffPriority` có syntax Integer, `EQUALITY integerMatch` và `ORDERING integerOrderingMatch`. Do đó, **nếu server hỗ trợ**, các giá trị 2, 10 và 100 được so sánh theo số học.

Nếu schema chỉ có:

~~~text
EQUALITY caseIgnoreMatch
SUBSTR caseIgnoreSubstringsMatch
~~~

thì không thể suy ra `ORDERING caseIgnoreOrderingMatch` tự động tồn tại. Một số attribute chuẩn có EQUALITY nhưng **không khai báo ORDERING mặc định**; server-side sort không chỉ dựa vào việc attribute có thể dùng trong filter equality.

### Khi số lại bị sắp xếp như chuỗi

~~~text
Dữ liệu:           2   10   100
Thứ tự kiểu chuỗi: 10  100  2
Thứ tự số nguyên:  2   10   100
~~~

Ví dụ này giúp phân biệt ngữ nghĩa; **không** được ép `integerOrderingMatch` lên một thuộc tính có syntax Directory String chỉ vì các giá trị trông giống số. Rule không tương thích syntax có thể dẫn đến lỗi `inappropriateMatching`.

## 3. Một số ORDERING rule trong RFC 4517

| Tên matching rule | OID | Ý nghĩa |
| --- | --- | --- |
| `caseIgnoreOrderingMatch` | `2.5.13.3` | Thứ tự chuỗi thuộc syntax tương thích sau bước chuẩn bị và xử lý chữ hoa/thường |
| `caseExactOrderingMatch` | `2.5.13.6` | Thứ tự chuỗi thuộc syntax tương thích, vẫn phân biệt chữ hoa/thường |
| `integerOrderingMatch` | `2.5.13.15` | Thứ tự số nguyên theo giá trị toán học |
| `generalizedTimeOrderingMatch` | `2.5.13.28` | So sánh thời gian Generalized Time theo ngữ nghĩa được chuẩn hóa |

Cả tên và OID đều có ý nghĩa trong schema. Khi gửi `SortKey` từ JNDI, sử dụng OID rõ ràng giúp tránh phụ thuộc cách đặt tên, nhưng vẫn phải xác minh rule được server chấp nhận và **phù hợp với thuộc tính**.

### Không đồng nghĩa với sắp xếp theo locale

`caseIgnoreOrderingMatch` không tự tạo thứ tự bảng chữ cái tiếng Việt như ứng dụng văn bản. Nếu giao diện cần thứ tự `A, Ă, Â, B...`, cần kiểm tra khả năng collation của LDAP server hoặc sử dụng tầng tìm kiếm có collation phù hợp. Đổi từ `caseIgnoreOrderingMatch` sang `caseExactOrderingMatch` không phải giải pháp cho yêu cầu đó.

## 4. RFC 2891: điều khiển sort ở cấp giao thức LDAP

Server-Side Sorting Control có:

- **Request OID:** `1.2.840.113556.1.4.473`.
- **Response OID:** `1.2.840.113556.1.4.474`.

Request chứa một hoặc nhiều sort key:

~~~text
SortKeyList ::= SEQUENCE OF {
    attributeType   // Thuộc tính cần sort
    orderingRule    // MatchingRuleId, có thể bỏ qua
    reverseOrder    // false là tăng dần
}
~~~

Các key được áp dụng theo thứ tự ưu tiên, từ khóa đầu đến khóa cuối.

**Quy tắc cốt lõi của `orderingRule`:**

1. **Bỏ trống orderingRule:** LDAP dùng ORDERING matching rule định nghĩa cho attribute trong schema. Nếu không có rule phù hợp, server có thể không sort được.
2. **Có orderingRule:** server kiểm tra rule được chỉ định có phù hợp với attribute không. Nếu không phù hợp, sort response thường báo `inappropriateMatching`.
3. **reverseOrder=true:** đổi chiều sort, không tự đổi matching rule.
4. **Nhiều khóa:** khi khóa đầu bằng nhau theo rule, server dùng khóa kế tiếp nếu hỗ trợ, giúp thứ tự rõ ràng hơn.
5. **Tránh lặp attributeType:** RFC 2891 yêu cầu mỗi attribute chỉ xuất hiện một lần trong danh sách sort key; lặp lại có thể khiến server trả lỗi.

Ví dụ request logic:

~~~text
Key 1:
  attributeType = cn
  orderingRule  = 2.5.13.3
  reverseOrder  = false

Key 2:
  attributeType = uid
  orderingRule  = 2.5.13.3
  reverseOrder  = false
~~~

Dòng thứ hai chỉ hợp lệ nếu máy chủ cho phép `caseIgnoreOrderingMatch` áp dụng cho `uid`. Các key không cần có cùng rule; thực tế hãy chọn rule tương thích syntax của từng trường.

### 4.1. Tại sao phải đọc sort response?

Response control chứa `sortResult` độc lập với mã kết quả Search. Trong các trường hợp server không hỗ trợ hoặc không xử lý được sort:

- Nếu request control đặt **criticality=true**, server không hỗ trợ phải từ chối thay vì âm thầm trả dữ liệu không sắp xếp.
- Nếu **criticality=false**, server có thể bỏ qua sort và trả các entry không có bảo đảm thứ tự.
- Nếu sort response có mã khác 0, ứng dụng phải xử lý lỗi của sort, kể cả khi phần Search có kết quả.
- Nếu **không có sort response**, theo RFC client nên coi sort đã bị bỏ qua. Khi tìm kiếm không trả entry hoặc thất bại, server cũng có thể không trả sort response.

Một số mã kết quả trong sort response:

| Mã | Tên LDAP | Ý nghĩa điển hình |
| --- | --- | --- |
| 0 | `success` | Server xác nhận kết quả được sắp xếp |
| 16 | `noSuchAttribute` | Sort key chứa loại attribute không được nhận diện |
| 18 | `inappropriateMatching` | Rule không được nhận diện hoặc không phù hợp |
| 11 | `adminLimitExceeded` | Vượt giới hạn xử lý của server |
| 50 | `insufficientAccessRights` | Thiếu quyền để server xử lý sort |
| 53 | `unwillingToPerform` | Server từ chối yêu cầu |

**Chỉ được xem kết quả là đã sort khi có bằng chứng phù hợp từ server.** Bỏ qua lỗi matching rule có thể làm UI hiển thị thứ tự sai, nhất là khi dùng phân trang.

## 5. Sắp xếp với `LdapTemplate`

Ở các phiên bản Spring LDAP có hỗ trợ, `org.springframework.ldap.control.SortControlDirContextProcessor` cung cấp cách yêu cầu server-side sort theo một attribute.

Ví dụ dưới đây giả định `ContextSource` có base DN `dc=example,dc=org`; `ou=people` đã tồn tại và LDAP server hỗ trợ sort theo `cn` với quy tắc phù hợp.

~~~java
import java.util.List;
import javax.naming.directory.SearchControls;

import org.springframework.ldap.control.SortControlDirContextProcessor;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.stereotype.Service;

@Service
public class PersonSortService {

    private final LdapTemplate ldapTemplate;

    public PersonSortService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<String> findNamesSorted() {
        SearchControls sc = new SearchControls();
        sc.setSearchScope(SearchControls.ONELEVEL_SCOPE);
        sc.setReturningAttributes(new String[] {"cn"});

        SortControlDirContextProcessor sort =
            new SortControlDirContextProcessor("cn");

        AttributesMapper<String> mapper =
            attrs -> (String) attrs.get("cn").get();

        List<String> names = ldapTemplate.search(
            "ou=people",
            "(objectClass=inetOrgPerson)",
            sc,
            mapper,
            sort
        );

        if (!sort.isSorted()) {
            throw new IllegalStateException(
                "LDAP không xác nhận sort: " + sort.getResultCode()
            );
        }
        return names;
    }
}
~~~

**Những điểm cần chú ý:**

- `SortControlDirContextProcessor("cn")` truyền **tên khóa sort**, không cung cấp constructor để chỉ định ORDERING rule tường minh.
- Processor là đối tượng có trạng thái; tạo mới cho mỗi truy vấn.
- Yêu cầu LDAP control cần context hỗ trợ `LdapContext` (thường dùng `LdapContextSource` với Spring LDAP), không chỉ một `DirContext` thiếu khả năng LDAPv3 control.
- `cn` ở đây là ví dụ thực tế. **Không phải mọi schema/server đều có ORDERING mặc định cho `cn`.** Nếu không được hỗ trợ, cần kiểm tra định nghĩa attribute và dùng API có thể chỉ định matching rule phù hợp.
- Nếu search hợp lệ nhưng không có entry, RFC cho phép server không trả sort response; code trên cố ý yêu cầu **xác nhận nghiêm ngặt**, nên ứng dụng thực tế có thể xử lý kết quả rỗng riêng theo yêu cầu nghiệp vụ.

Ở một số phiên bản Spring LDAP mới, `SortControlDirContextProcessor` được đánh dấu deprecated và tài liệu hướng dẫn sử dụng `ControlExchangeDirContextProcessor`/`SortControlExchange`. Hãy đối chiếu API đúng với phiên bản dependency trong ứng dụng.

## 6. Chỉ định rule tường minh với `javax.naming.ldap.SortKey`

Để nêu rõ `orderingRule`, JNDI hỗ trợ:

~~~java
import javax.naming.ldap.SortKey;

SortKey byCn = new SortKey(
    "cn",
    true,       // ascending
    "2.5.13.3" // caseIgnoreOrderingMatch
);

SortKey byPriority = new SortKey(
    "staffPriority",
    true,
    "2.5.13.15" // integerOrderingMatch, nếu syntax phù hợp
);
~~~

Tham số thứ ba là **matching rule ID**; nếu đặt `null`, server sẽ dùng rule ORDERING của attribute theo schema, khi có.

Dùng `SortControl` để mã hóa request:

~~~java
import javax.naming.ldap.SortControl;
import javax.naming.ldap.SortKey;

SortKey[] keys = {
    new SortKey("cn", true, "2.5.13.3"),
    new SortKey("uid", true, "2.5.13.3")
};

SortControl requestControl = new SortControl(keys, true);
// Tham số true: yêu cầu critical.
// Constructor có thể ném java.io.IOException.
~~~

### 6.1. Tích hợp vào Spring LDAP bằng processor tùy chỉnh

Khi cần chỉ định rule cụ thể, có thể triển khai một `DirContextProcessor`. Lớp `AbstractRequestControlDirContextProcessor` giúp gắn request control vào `LdapContext` và bảo toàn những request control có sẵn.

~~~java
import java.io.IOException;
import javax.naming.NamingException;
import javax.naming.directory.DirContext;
import javax.naming.ldap.Control;
import javax.naming.ldap.LdapContext;
import javax.naming.ldap.SortControl;
import javax.naming.ldap.SortKey;
import javax.naming.ldap.SortResponseControl;

import org.springframework.ldap.control.AbstractRequestControlDirContextProcessor;

public final class RuleSortProcessor
        extends AbstractRequestControlDirContextProcessor {

    private final SortKey[] keys;

    public RuleSortProcessor(SortKey... keys) {
        this.keys = keys.clone();
    }

    @Override
    public Control createRequestControl() {
        try {
            return new SortControl(keys, true);
        } catch (IOException ex) {
            throw new IllegalArgumentException(
                "Không mã hóa được sort control", ex);
        }
    }

    @Override
    public void postProcess(DirContext context) throws NamingException {
        LdapContext ldap = (LdapContext) context;
        Control[] responses = ldap.getResponseControls();

        if (responses != null) {
            for (Control c : responses) {
                if (!SortResponseControl.OID.equals(c.getID())) {
                    continue;
                }

                SortResponseControl response;
                if (c instanceof SortResponseControl) {
                    response = (SortResponseControl) c;
                } else {
                    try {
                        response = new SortResponseControl(
                            c.getID(), c.isCritical(), c.getEncodedValue()
                        );
                    } catch (IOException ex) {
                        NamingException error =
                            new NamingException("Không giải mã được sort response");
                        error.initCause(ex);
                        throw error;
                    }
                }

                if (!response.isSorted()) {
                    NamingException error = response.getException();
                    if (error != null) {
                        throw error;
                    }
                    throw new NamingException(
                        "Sort thất bại: " + response.getResultCode()
                    );
                }
                return;
            }
        }

        throw new NamingException("Thiếu LDAP sort response control");
    }
}
~~~

Gọi từ service (sử dụng `SearchControls sc` và `AttributesMapper<String> mapper` đã khai báo trong ví dụ trước):

~~~java
RuleSortProcessor sort = new RuleSortProcessor(
    new SortKey("cn", true, "2.5.13.3")
);

List<String> names = ldapTemplate.search(
    "ou=people",
    "(objectClass=inetOrgPerson)",
    sc,
    mapper,
    sort
);
~~~

Lớp trên là ví dụ **xác nhận sort nghiêm ngặt**. Nó ném lỗi khi server không trả response, kể cả với truy vấn rỗng mà RFC cho phép bỏ response; cần xử lý ca này theo hợp đồng nghiệp vụ nếu ứng dụng cho phép tập kết quả rỗng. Nếu dùng Spring LDAP phiên bản mới có API control exchange, ưu tiên API tương ứng thay vì duy trì mã tùy chỉnh khi không cần thiết.

**Quan trọng:** Đừng chỉ gửi request control rồi bỏ qua `SortResponseControl`. Một sort key không hợp lệ có thể làm sort thất bại mà quá trình tìm kiếm vẫn trả dữ liệu.

### 6.2. Tạo khóa phụ khi có dữ liệu trùng

~~~java
RuleSortProcessor sort = new RuleSortProcessor(
    new SortKey("sn", true, "2.5.13.3"),
    new SortKey("uid", false, "2.5.13.3")
);
~~~

Nếu được server chấp nhận, kết quả sẽ ưu tiên `sn` tăng dần; khi `sn` bằng nhau, dùng `uid` giảm dần. Mỗi khóa có thể dùng **rule khác nhau** tùy syntax của trường. Muốn thứ tự đủ ổn định để hiển thị phân trang, nên chọn một khóa phụ đủ phân biệt và kiểm tra quy tắc sort trên server.

## 7. Entry thiếu thuộc tính và attribute đa giá trị

### 7.1. Không có sort key

RFC 2891 xem entry thiếu attribute được dùng làm sort key có giá trị **NULL**, và NULL được xếp sau mọi giá trị có thật khi tăng dần theo một khóa. Với thứ tự giảm dần, NULL nằm trước.

~~~text
ASC  : An, Binh, Cuong, [không có tên]
DESC : [không có tên], Cuong, Binh, An
~~~

Ví dụ minh họa vị trí NULL, không khẳng định thứ tự tiếng Việt cụ thể. Nếu nhiều entry đều thiếu khóa, thứ tự giữa chúng chưa được xác định hoàn toàn nếu không có khóa phụ.

### 7.2. Attribute nhiều giá trị

Giả sử entry có:

~~~ldif
cn: An
cn: Anh
~~~

Theo RFC 2891, nếu không có control khác ảnh hưởng sort, máy chủ **SHOULD** dùng giá trị nhỏ nhất của attribute theo quy tắc ORDERING để quyết định vị trí của entry nhiều giá trị. Đây không phải khẳng định bắt buộc với mọi server/triển khai. Khi nghiệp vụ cần tên hiển thị duy nhất, nên thiết kế trường một giá trị phù hợp hơn.

### 7.3. Hai giá trị bằng nhau theo matching rule

Với `caseIgnoreOrderingMatch`, `Anh` và `anh` có thể được coi như nhau trong so sánh. Khi chỉ sort theo `cn`, LDAP không tự xác định một khóa phá hòa. Có thể chọn `uid` hoặc định danh ổn định khác làm khóa phụ **nếu server hỗ trợ ORDERING rule phù hợp cho khóa đó**.

Thứ tự nhiều lần tìm vẫn có thể thay đổi khi dữ liệu được tạo, sửa, rename hoặc move trong lúc tìm kiếm; server-side sort không tự cung cấp snapshot giao dịch.

## 8. Matching rule khi kết hợp sort và paging

Simple Paged Results Control (RFC 2696) dùng cookie để xin trang tiếp. Nếu kết hợp với sort control theo RFC 2891, server cần **sắp xếp toàn bộ tập kết quả logic trước khi phân trang**, thay vì chỉ sort riêng từng trang.

~~~text
Server:
  search(base, filter, scope)
            |
            v
       Tập entry khớp
            |
            v
      Sort theo matching rule
            |
            v
  Page 1 → cookie → Page 2 → cookie → Page cuối

Cách sai:
  lấy Page 1 → sort Page 1
  lấy Page 2 → sort Page 2
  => toàn bộ danh sách có thể không được sắp xếp đúng
~~~

Khi đọc từng trang:

1. Giữ nguyên **sortKeyList** (attribute, `orderingRule`, chiều sort, thứ tự các khóa) trên tất cả request của cùng chuỗi phân trang.
2. Giữ nguyên search base, filter và search scope; chỉ thay cookie theo phản hồi server.
3. Kiểm tra sort response ở từng trang khi có; không dùng thứ tự nhận được để đoán server đã sort.
4. Không coi cookie là số trang và không ghép cookie của một truy vấn sang truy vấn khác.
5. Chấp nhận thực tế rằng thay đổi đồng thời có thể gây lặp/thiếu entry, kể cả khi đã sort thành công.

Spring LDAP có thể kết hợp các `DirContextProcessor` qua `AggregateDirContextProcessor` hoặc API control exchange của phiên bản đang dùng. Cần thử khả năng kết hợp sort và paged results trên server thật, cùng quyền, filter và index sẽ sử dụng ở môi trường triển khai.

## 9. Xử lý lỗi, hiệu năng và bảo mật

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `inappropriateMatching` | Rule không hợp với attribute/syntax hoặc không được server hỗ trợ | Kiểm tra schema và đổi rule hợp lệ |
| `noSuchAttribute` | Tên attribute làm sort key không được nhận diện | Xem định nghĩa schema, tên và OID |
| Thiếu sort response | Server bỏ control hoặc không trả response trong trường hợp cho phép | Không khẳng định dữ liệu đã sort khi thiếu bằng chứng |
| `unavailableCriticalExtension` | Server không hỗ trợ request control critical | Dùng server/tính năng khác hoặc thay chiến lược |
| Sort chậm hoặc bị từ chối | Nhiều kết quả, thiếu index, giới hạn máy chủ | Thu hẹp filter/scope, tối ưu index và giới hạn tài nguyên |
| `10` đứng trước `2` | Sort theo dạng chuỗi | Xem lại SYNTAX/ORDERING |
| Tên có dấu sắp xếp khác UI mong muốn | LDAP rule không phải collation locale | Xác định yêu cầu ngôn ngữ và khả năng server |
| Trùng/thiếu khi paging | Dữ liệu thay đổi đồng thời hoặc controls không ổn định | Thiết kế đồng bộ idempotent và đối soát |

Có thể xem `supportedControl` tại **Root DSE** để kiểm tra server quảng bá request OID `1.2.840.113556.1.4.473`. Xem `subschemaSubentry`, `attributeTypes` và `matchingRules` để hiểu rule và syntax. Việc server quảng bá OID không bảo đảm mọi attribute và mọi orderingRule đều được chấp nhận.

Trong ứng dụng thực tế, **không truyền nguyên xi tên attribute hoặc OID rule tùy ý từ HTTP request**. Hãy tạo whitelist trường được phép sort, mapping mỗi trường với rule phù hợp và đặt giới hạn page size/time/concurrency để tránh tạo truy vấn tiêu tốn tài nguyên. Sử dụng LDAPS hoặc StartTLS với chứng chỉ được kiểm tra, tài khoản bind có quyền tối thiểu và tránh log dữ liệu LDAP nhạy cảm.

## 10. Bài thực hành và kiểm thử

Hãy dùng môi trường LDAP thử nghiệm có hỗ trợ RFC 2891, cấu hình schema rõ ràng, rồi thử các trường hợp:

| Ca kiểm thử | Thiết lập | Kết quả cần xác minh |
| --- | --- | --- |
| Rule mặc định | Attribute có ORDERING trong schema; bỏ orderingRule | Server sử dụng rule đã định nghĩa |
| Rule explicit | Chọn `caseIgnoreOrderingMatch` cho chuỗi tương thích | Response xác nhận sort nếu được hỗ trợ |
| Rule sai syntax | Chọn `integerOrderingMatch` cho attribute chuỗi | Sort lỗi thích hợp, thường `inappropriateMatching` |
| Ascending/descending | Đổi cờ `ascending` trên cùng khóa | Thứ tự đảo đúng chiều |
| Hai khóa | Hai entry có `sn` giống nhau, `uid` khác nhau | Khóa thứ hai phân định thứ tự |
| Thiếu attribute | Có entry không có attribute làm sort key | Kiểm tra vị trí NULL |
| Attribute đa giá trị | Một entry có nhiều giá trị cùng tên attribute | Xem server chọn giá trị so sánh nào |
| Control bị bỏ qua | Server không hỗ trợ sort và criticality=false | Ứng dụng không nhận kết quả như đã sort |
| Tập rỗng | Filter không khớp entry nào | Xử lý hợp lệ dù server có thể bỏ sort response |
| Sort + paging | 13 entry, page size 5 | Toàn bộ tập có thứ tự thống nhất qua các trang |
| Dữ liệu biến động | Đổi giá trị khóa giữa hai trang | Không mặc định có snapshot nhất quán |

Khi kiểm thử, so sánh **danh sách khóa và thứ tự kết quả thực tế** với quy tắc đã khai báo; kiểm tra cả mã sort response. Một test chỉ xác nhận API trả về đúng số entry không đủ chứng minh sorting đã thành công.

### Câu hỏi tự đánh giá

1. `EQUALITY caseIgnoreMatch` có đồng nghĩa đã có `ORDERING caseIgnoreOrderingMatch` không?
2. Nếu bỏ `orderingRule` trong `SortKey`, LDAP sẽ dùng quy tắc nào?
3. Vì sao không nên dùng `integerOrderingMatch` với attribute có syntax Directory String?
4. Hai entry có khóa `cn` tương đương theo rule được sắp xếp thế nào nếu không có khóa phụ?
5. Vì sao kết quả Search thành công chưa đủ để kết luận sort thành công?
6. Sort từng trang sau khi nhận có tương đương sort trên toàn bộ kết quả trước khi phân trang không?
7. Muốn sắp xếp tên theo cách người Việt thường đọc, bạn cần xác minh điều gì với LDAP server?

## 11. Ghi nhớ

**Matching rule quyết định ngữ nghĩa so sánh khi sort.** Cần phân biệt `EQUALITY` và `ORDERING`, xác định syntax của attribute, rồi dùng quy tắc được server cho phép. Trong RFC 2891, bỏ `orderingRule` nghĩa là sử dụng ORDERING rule mặc định của attribute; chỉ định rule tường minh có thể giúp xác định chính sách sort nhưng không vượt qua được giới hạn schema hoặc server.

Với **Spring LDAP**, `SortControlDirContextProcessor` phù hợp cho sort đơn giản theo tên attribute; khi cần `orderingRule` tường minh có thể sử dụng JNDI `SortKey`/`SortControl` và processor phù hợp với phiên bản thư viện. Luôn kiểm tra **sort response**, lưu ý thuộc tính thiếu/đa giá trị và giữ nguyên các khóa sort khi phân trang. Sorting của LDAP không tự tạo collation theo ngôn ngữ, snapshot nhất quán hoặc khả năng nhảy đến trang tùy ý.

## Tài liệu tham khảo

- [RFC 2891 — LDAP Control Extension for Server Side Sorting](https://www.rfc-editor.org/rfc/rfc2891): `SortKeyList`, `orderingRule`, `sortResult` và kết hợp paged results.
- [RFC 4512 — LDAP Directory Information Models](https://www.rfc-editor.org/rfc/rfc4512): schema, EQUALITY, ORDERING và SYNTAX.
- [RFC 4517 — LDAP Syntaxes and Matching Rules](https://www.rfc-editor.org/rfc/rfc4517): các matching rule chuẩn và OID.
- [RFC 2696 — LDAP Simple Paged Results](https://www.rfc-editor.org/rfc/rfc2696): cookie và phân trang.
- [Spring LDAP — Processing the DirContext](https://docs.spring.io/spring-ldap/reference/processing-the-dircontext.html): cơ chế `DirContextProcessor` và controls.
- [Spring LDAP — LdapTemplate API](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/LdapTemplate.html): các overload `search(...)`.
- [Java — SortKey API](https://docs.oracle.com/en/java/javase/25/docs/api/java.naming/javax/naming/ldap/SortKey.html): chọn attribute, chiều sort, matching rule.
- [Java — SortResponseControl API](https://docs.oracle.com/en/java/javase/25/docs/api/java.naming/javax/naming/ldap/SortResponseControl.html): xác nhận kết quả sort.
