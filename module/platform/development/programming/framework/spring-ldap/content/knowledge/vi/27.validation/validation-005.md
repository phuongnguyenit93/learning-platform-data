# Không dùng filter để thay thế validation toàn diện

Trong **Spring LDAP**, search filter giúp ứng dụng *chọn entry nào cần tìm* trong dịch vụ thư mục. Một filter được escape đúng có thể ngăn người dùng thay đổi cấu trúc biểu thức tìm kiếm, nhưng không thể tự trả lời những câu hỏi như: `uid` có đúng chính sách đặt tên không, người dùng có quyền tra cứu không, entry có thỏa schema không, hay một thao tác tạo mới có an toàn và hợp lệ về nghiệp vụ không.

Bài học thuộc chương **Validation** của module **SPRING_LDAP**. Nội dung tập trung vào giới hạn của LDAP filter, cách kết hợp **input validation, business validation, schema validation và kiểm soát truy cập** khi truy vấn hoặc thao tác entry thông qua `LdapTemplate`, `LdapClient` hay ODM. Ví dụ sử dụng Java 17+ và một LDAP directory giả định có base DN `dc=example,dc=org`; khi `ContextSource` đã cấu hình base này, những DN như `ou=people` được hiểu là **tương đối với base**.

## 1. LDAP filter thực sự làm gì?

Một LDAP search thường cần ít nhất ba thông tin: **search base**, **search scope** và **filter**. Filter là biểu thức để directory kiểm tra entry nào thỏa điều kiện tìm kiếm, ví dụ:

```ldap
(uid=alice)
```

Hoặc kết hợp nhiều điều kiện:

```ldap
(&(objectClass=inetOrgPerson)(uid=alice))
```

Phép `&` là AND; `|` là OR; `!` là NOT. Filter `(uid=*)` kiểm tra sự hiện diện của `uid`. Một dấu `*` chưa được escape trong assertion value có thể biểu diễn wildcard cho substring matching. Server áp dụng matching rule của attribute theo schema và trả các entry **phù hợp với truy vấn và quyền truy cập của LDAP identity đang dùng**.

Filter **không phải** schema validator tổng quát. Một filter có thể lọc ra các entry chứa `cn`, nhưng kết quả đó không chứng minh một yêu cầu `create` hoặc `modify` tiếp theo sẽ được phép thực thi.

| Thành phần | Trách nhiệm | Điều không thể suy ra |
| --- | --- | --- |
| **Filter** | Chọn entry phù hợp điều kiện tìm kiếm | Input tuân thủ mọi quy tắc nghiệp vụ |
| **Search base và scope** | Giới hạn phần cây thư mục được tìm | Người gọi API được phép đọc/sửa mọi entry trong nhánh |
| **Input validation** | Kiểm tra hợp đồng giá trị đầu vào | Entry tồn tại hoặc server đồng ý cho thao tác |
| **Business validation** | Kiểm tra vai trò, trạng thái và quy tắc giữa các trường | LDAP schema chắc chắn chấp nhận dữ liệu |
| **Schema validation** | Kiểm tra `objectClass`, `MUST`, `MAY`, cú pháp/số lượng giá trị | Quyền ghi và trạng thái thực tại thời điểm thao tác |
| **ACL và LDAP server** | Quyết định kết quả truy cập và thao tác thật | Thay thế được toàn bộ chính sách nghiệp vụ ứng dụng |

Một cách diễn đạt dễ nhớ: **filter trả lời “entry nào khớp?”; validation trả lời “dữ liệu và thao tác này có hợp lệ không?”**

## 2. Vì sao filter không thể thay thế validation?

### 2.1. Escape đúng chỉ giải quyết bài toán cú pháp filter

Giả sử API cho phép tra cứu người dùng theo `uid`, nhưng chỉ chấp nhận mã định danh dài 1–64 ký tự thuộc tập chữ cái ASCII, chữ số, dấu chấm, gạch dưới và gạch ngang.

```text
uid = "alice"         → hợp lệ theo chính sách ứng dụng mẫu
uid = "alice*"        → không hợp lệ theo chính sách đó
uid = ""              → không hợp lệ
uid = "admin,ou=ops"  → không hợp lệ
```

Nếu đưa `alice*` vào bộ xây filter **đúng cách như một giá trị equality**, dấu `*` sẽ được escape thành **ký tự dữ liệu**, thay vì wildcard. Điều này bảo vệ cú pháp truy vấn. Tuy nhiên, vì chính sách ứng dụng **cấm** dấu `*` trong `uid`, request vẫn cần bị từ chối **trước khi tìm kiếm**.

Ngược lại, dù filter vô tình tìm được một entry, điều đó cũng không chứng minh `uid` ban đầu hợp lệ theo hợp đồng API.

### 2.2. Filter chỉ đánh giá dữ liệu hiện có, không xác nhận dữ liệu sắp ghi

Filter `(&(objectClass=inetOrgPerson)(uid=alice))` chỉ tìm trong các entry đã tồn tại. Nó không thể xác minh toàn bộ nội dung của entry mới:

```ldif
dn: uid=alice,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: alice
cn: Alice Nguyen
# Thiếu sn: ràng buộc MUST kế thừa từ person
```

Một filter khớp với `uid` hay `objectClass` không kiểm tra được `sn` còn thiếu trong payload tạo mới. Server có thể trả `objectClassViolation` khi `bind`. Validation ứng dụng nên kiểm tra `sn` sớm, đồng thời vẫn dựa vào directory để xác minh schema cuối cùng.

### 2.3. Search có kết quả không bảo đảm thao tác hợp lệ

Ứng dụng vừa tìm thấy entry `uid=alice` không có nghĩa:

- Caller của HTTP API có quyền xem hồ sơ cá nhân hoặc đổi mật khẩu của Alice.
- LDAP account dùng để search cũng có quyền `modify`, `delete` hay `modDN`.
- Attribute định sửa thuộc `MAY`/được schema hỗ trợ và được ACL cho phép.
- Entry vẫn ở trạng thái cũ tại thời điểm ghi; nó có thể bị thay đổi hoặc xóa giữa hai request.

**Quyền truy cập phải được kiểm tra đúng tầng và đúng thao tác**. Search filter là một điều kiện truy vấn, không thay thế authorization và LDAP ACL.

### 2.4. Không tìm thấy entry không đồng nghĩa input sai

Search thành công nhưng trả danh sách rỗng có thể do: entry không tồn tại, filter quá chặt, search base/scope không bao phủ entry, hoặc LDAP identity không được nhìn thấy nội dung phù hợp. Ngoài ra, thao tác search có thể thất bại với một exception riêng như sai base, timeout hoặc thiếu quyền. Cần phân biệt:

| Kết quả | Ý nghĩa khả dĩ | Cách ứng dụng xử lý |
| --- | --- | --- |
| Search thành công, 0 entry | Không có entry hiển thị phù hợp tiêu chí | Trả rỗng hoặc not-found theo hợp đồng nghiệp vụ |
| Search thành công, 1 entry | Có một entry phù hợp | Còn phải kiểm tra authorization, dữ liệu trả và bối cảnh thao tác |
| Search thành công, nhiều entry | Tiêu chí chưa duy nhất trong tập đang xét | Xử lý đa kết quả; không tự chọn bản ghi đầu tiên khi yêu cầu duy nhất |
| Search ném lỗi LDAP/kết nối | Directory không hoàn tất truy vấn như kỳ vọng | Phân loại lỗi directory, không kết luận input sai |

## 3. Ngăn LDAP filter injection nhưng vẫn validate nội dung

### 3.1. Tránh ghép filter bằng chuỗi

Đoạn code sau lấy `uid` do người dùng cung cấp và ghép trực tiếp vào cú pháp filter:

```java
// Không an toàn nếu uid lấy từ request chưa được xử lý đúng.
String unsafeFilter = "(uid=" + uidFromRequest + ")";
List<?> entries = ldapTemplate.search(
        "ou=people",
        unsafeFilter,
        attrs -> attrs.get("cn").get()
);
```

Trong cú pháp filter LDAP (RFC 4515), các ký tự đặc biệt trong assertion value gồm `*`, `(`, `)`, dấu gạch chéo ngược và NUL. Nếu nhúng trực tiếp input vào filter, một giá trị chứa ký tự điều khiển cú pháp có thể làm filter sai cấu trúc hoặc đổi ý nghĩa truy vấn. Đây là dạng **LDAP filter injection**.

Đường xử lý đúng cần hai bước **độc lập**:

1. **Validate input** theo hợp đồng nghiệp vụ: ví dụ regex/giới hạn cho `uid`, độ dài tối đa, lựa chọn trường tìm kiếm được phép.
2. **Dùng API xây filter có escape assertion value** để dữ liệu đầu vào không thể trở thành toán tử/cấu trúc của filter.

Ví dụ Spring LDAP:

```java
import static org.springframework.ldap.query.LdapQueryBuilder.query;

var ldapQuery = query()
        .base("ou=people")
        .where("uid").is(uidFromRequest);

var entries = ldapTemplate.search(
        ldapQuery,
        attrs -> attrs.get("cn").get()
);
```

`where("uid").is(value)` xây điều kiện equality với **giá trị được escape cho filter**. Cần giữ `"uid"` là trường do ứng dụng chọn, không để client tự chèn tên attribute, toán tử hoặc toàn bộ filter thô. Filter được tạo đúng vẫn không chặn được các giá trị trái quy tắc nghiệp vụ nếu ứng dụng không validate riêng.

### 3.2. Phân biệt escape filter, escape DN và validation

| Dữ liệu được dùng ở đâu | Công cụ đúng | Sai lầm thường gặp |
| --- | --- | --- |
| Assertion value trong search filter | `LdapQueryBuilder`/`EqualsFilter` hoặc công cụ escape filter | Nối chuỗi `"(uid=" + input + ")"` |
| Giá trị của RDN trong DN | `LdapNameBuilder`/`Rdn` | Dùng cách escape filter hoặc nối `"uid=" + input` |
| Giá trị attribute khi `bind`/`modify` | `Attributes`/`ModificationItem`, kiểm tra schema và domain | Escape theo filter rồi lưu chuỗi đã escape |
| Quy tắc nghiệp vụ của input | Jakarta Bean Validation và service/domain validator | Tin rằng filter escape đã làm input hợp lệ |

Ví dụ, ký tự `*` trong filter có thể là wildcard nếu dùng trong substring assertion, nhưng khi nó là **dữ liệu literal** cần được escape. Trong DN, tập ký tự và quy tắc escape khác. Escape không thay đổi quyết định về việc `uid` có được phép chứa dấu `*` hay không.

> **Ghi nhớ:** Không cần tự viết bộ encode bằng nhiều lệnh `String.replace`. Sử dụng bộ xây filter/DN của thư viện, sau đó kiểm thử các ký tự đặc biệt và đầu vào biên theo đúng chức năng API.

### 3.3. Wildcard là một tính năng riêng, cần quy tắc riêng

Có khác biệt giữa hai API nghiệp vụ:

- **Tìm theo UID chính xác:** không cho wildcard; dùng điều kiện equality, ví dụ `where("uid").is(validUid)`.
- **Gợi ý tên theo tiền tố:** có thể cho người dùng nhập phần tiền tố, nhưng ứng dụng phải giới hạn độ dài, tập ký tự, scope, số kết quả và tự quyết định vị trí wildcard. Dùng bộ xây filter có hỗ trợ substring và escape các ký tự dữ liệu.

Nếu muốn tìm `cn` bắt đầu bằng `An`, ứng dụng có thể có ý định tạo điều kiện substring dạng `(cn=An*)`. Dấu `*` **do ứng dụng quyết định**, không phải một phần cấu trúc được client tùy ý nhập. Không chấp nhận chuỗi filter nguyên bản như `(|(uid=*)(mail=*))` rồi coi đó là dữ liệu tìm kiếm bình thường.

## 4. Áp dụng validation trước khi gọi LdapTemplate

Ví dụ dưới đây là một endpoint tra cứu `uid` chính xác, yêu cầu `uid` phù hợp chính sách đặt tên. Ngoài filter, service còn khống chế search base, scope và object class. Không có chỗ để caller đưa vào LDAP filter tùy ý.

```java
import java.util.List;
import java.util.regex.Pattern;

import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.SearchScope;

import static org.springframework.ldap.query.LdapQueryBuilder.query;

public final class PeopleLookupService {
    private static final Pattern UID =
            Pattern.compile("[A-Za-z0-9._-]{1,64}");
    private final LdapTemplate ldapTemplate;

    public PeopleLookupService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public record PersonLookup(String uid) {}
    public record PersonSummary(String uid, String cn) {}

    public List<PersonSummary> findByUid(PersonLookup request) {
        validate(request); // Không có lời gọi LDAP ở đây.

        LdapQuery ldapQuery = query()
                .base("ou=people")
                .searchScope(SearchScope.ONELEVEL)
                .where("objectClass").is("inetOrgPerson")
                .and("uid").is(request.uid());

        return ldapTemplate.search(
                ldapQuery,
                (AttributesMapper<PersonSummary>) attrs ->
                        new PersonSummary(
                                (String) attrs.get("uid").get(),
                                (String) attrs.get("cn").get())
        );
    }

    private static void validate(PersonLookup request) {
        if (request == null || request.uid() == null
                || !UID.matcher(request.uid()).matches()) {
            throw new IllegalArgumentException("uid không hợp lệ");
        }
    }
}
```

Giả định ở ví dụ: endpoint chỉ làm việc với người dùng là **con trực tiếp** của `ou=people`, và tài khoản directory được phép đọc `uid`/`cn`. Nếu server có ACL che thuộc tính, code mapper nên kiểm tra thuộc tính vắng mặt và xử lý theo hợp đồng API thay vì giả định luôn nhận đầy đủ. `SearchScope.ONELEVEL` là quyết định phạm vi truy vấn; **không thay thế kiểm tra quyền của người gọi API**.

Luồng thực hiện là:

1. Nhận `PersonLookup`, kiểm tra `uid` trước mạng.
2. Xây filter equality có escape từ `uid` hợp lệ.
3. Giữ base `ou=people`, scope `ONELEVEL` và class `inetOrgPerson` trong code.
4. Gửi search qua `LdapTemplate`.
5. Giải thích kết quả rỗng/một/nhiều entry và lỗi server ở service/API; áp dụng authorization trước khi trả dữ liệu nhạy cảm.

Không cần thêm một filter thô do client gửi để thực hiện bất kỳ bước nào trong số này.

### 4.1. Nếu trường tìm kiếm là lựa chọn động, dùng allowlist

Một API có thể cho chọn tìm theo `uid` **hoặc** `mail`. Không cho client nhập `attributeName` tùy ý, rồi gọi `where(attributeName)`:

```java
import java.util.Locale;

static String allowedAttribute(String requestedField) {
    if (requestedField == null) {
        throw new IllegalArgumentException("Thiếu trường tìm kiếm");
    }
    return switch (requestedField.toLowerCase(Locale.ROOT)) {
        case "uid" -> "uid";
        case "mail" -> "mail";
        default -> throw new IllegalArgumentException(
                "Trường tìm kiếm không được hỗ trợ");
    };
}
```

Sau khi chọn được tên attribute **do service xác định**, tiếp tục validate giá trị theo chính sách của từng trường: `uid` cần mẫu định danh, `mail` cần kiểm tra email/độ dài/miền nếu nghiệp vụ yêu cầu. Không sử dụng một regex chung cho mọi attribute vì mỗi kiểu dữ liệu có cú pháp và ràng buộc khác nhau.

## 5. Filter không thay thế authorization và quy tắc nghiệp vụ

Giả sử nhân viên A tìm thấy entry của nhân viên B bằng filter `(uid=bob)`. Điều kiện này chỉ chứng minh rằng directory trả một entry phù hợp cho LDAP identity đang dùng; nó **không xác nhận A được xem hoặc chỉnh sửa hồ sơ B**.

Trong mô hình ứng dụng dùng **service account** để truy cập LDAP, server thường thấy danh tính service, không trực tiếp thấy người dùng của HTTP API. Do đó:

- Ứng dụng phải xác định **caller** và kiểm tra quyền đối với tài nguyên, hành động và tổ chức của entry.
- Tài khoản dịch vụ cần ACL tối thiểu cần thiết; quyền tìm kiếm, quyền đọc attribute, quyền sửa, xóa và đổi DN là các quyền có thể khác nhau.
- Có thể dùng filter để giới hạn **tập ứng viên** theo tổ chức/trạng thái, nhưng nếu kết quả truy vấn được dùng cho quyết định bảo mật thì phải bảo đảm tiêu chí được xây từ thuộc tính và ngữ cảnh **đáng tin cậy**; không tin một tham số `department` do caller tự khai báo là bằng chứng quyền truy cập.
- Với thao tác cập nhật nhạy cảm, cần xem xét thay đổi trạng thái giữa search và modify; không giả định search trước đó khóa entry.

Ví dụ về một yêu cầu thay email: caller cần được phép sửa người dùng đó, email mới phải thỏa chính sách nghiệp vụ, attribute `mail` phải được schema cho phép và thao tác LDAP cuối cùng phải qua ACL. Một filter `(uid=alice)` **không thực hiện thay** bất kỳ kiểm tra nào trong các kiểm tra này.

### 5.1. Không xác thực mật khẩu bằng search filter

Không viết filter như:

```ldap
(&(uid=alice)(userPassword=somePassword))
```

Đó không phải cách xác thực LDAP đáng tin cậy: attribute mật khẩu có thể bị che bởi ACL, lưu bằng phương thức hash hoặc được hệ thống xác thực xử lý riêng. Việc truy vấn giá trị `userPassword` còn làm tăng nguy cơ lộ secret qua filter/log. Với chức năng đăng nhập, hãy dùng **luồng xác thực LDAP phù hợp** như bind theo danh tính người dùng qua kết nối được bảo vệ bằng TLS và cấu hình Spring LDAP/Spring Security tương ứng. Đồng thời áp dụng giới hạn thử đăng nhập, thông báo lỗi trung tính và chính sách phiên ở tầng ứng dụng.

## 6. Search filter không kiểm chứng schema của entry

LDAP schema quy định object class, attribute bắt buộc (`MUST`), attribute có thể xuất hiện (`MAY`), syntax và thuộc tính đơn/đa giá trị. Ví dụ với chuỗi `top → person → organizationalPerson → inetOrgPerson`, `cn` và `sn` là `MUST` kế thừa từ `person`. `uid` có thể được ứng dụng yêu cầu thêm để tạo RDN, dù không phải `MUST` của `inetOrgPerson`.

**Tìm kiếm một entry** với `(objectClass=inetOrgPerson)` không có nghĩa:

- Request sắp gửi `bind` có đủ `cn`/`sn`.
- Một tập `ModificationItem` không xóa mất `sn` sau khi sửa.
- Client được ghi attribute chỉ vì nó xuất hiện trong `MAY`.
- Một giá trị `member` của nhóm hợp lệ là DN thuộc phạm vi được phép.
- Directory triển khai đúng schema mà ứng dụng đang giả định.

Ví dụ một thao tác tạo entry nên thực hiện:

```text
Input: uid, cn, sn, mail
   ↓
Kiểm tra định dạng + quy tắc nghiệp vụ
   ↓
Chọn profile objectClass và attribute cho phép
   ↓
Kiểm tra MUST/giá trị/kiểu/số lượng trước ghi
   ↓
Xây DN bằng LdapNameBuilder (không dùng filter)
   ↓
LdapTemplate.bind(...) → server kiểm tra schema + ACL + trạng thái
```

Filter không xuất hiện trong luồng tạo entry này vì **không bắt buộc phải search trước khi bind**. Nếu ứng dụng search để “kiểm tra có tồn tại” trước khi tạo, kết quả đó vẫn không ngăn được trường hợp hai yêu cầu song song cùng tạo một DN: server quyết định xung đột tại thời điểm ghi. Với tính duy nhất của một attribute *không nằm trong DN*, còn phải xem cơ chế unique constraint thực tế trên directory; tìm kiếm trước không tự tạo ràng buộc duy nhất.

## 7. Không dùng filter để kiểm soát toàn bộ tài nguyên truy vấn

Ngay cả filter được escape đúng vẫn có thể gây truy vấn quá rộng hoặc quá tốn kém nếu endpoint không có giới hạn. Ví dụ: tìm theo tiền tố một ký tự trong hàng triệu entry, search toàn bộ subtree hoặc yêu cầu trả về quá nhiều attribute.

Nên kiểm soát thêm:

| Hạng mục | Quy tắc thực hành | Vì sao cần |
| --- | --- | --- |
| **Search base** | Giữ cố định hoặc cho chọn từ tập DN được phép; parse DN bằng API LDAP | Tránh quét nhầm nhánh ngoài phạm vi nghiệp vụ |
| **Search scope** | Chọn `OBJECT`, `ONELEVEL` hoặc `SUBTREE` theo use case | Giảm số entry cần xem và chi phí truy vấn |
| **Filter field** | Dùng allowlist attribute/toán tử | Không cho caller quyết định cấu trúc search tùy ý |
| **Độ dài giá trị** | Đặt `min/max` phù hợp; đặc biệt cho prefix/substring | Tránh truy vấn quá rộng và input bất thường |
| **Số kết quả** | Đặt giới hạn và dùng paging khi cần | Kiểm soát tải và dung lượng phản hồi |
| **Thời gian xử lý** | Cấu hình time limit/timeout tại tầng phù hợp | Tránh giữ tài nguyên vô hạn |
| **Attribute trả về** | Chỉ lấy những attribute cần thiết, kiểm tra quyền trước khi gửi ra API | Giảm dữ liệu cá nhân bị lộ |
| **Sort, referral, alias** | Quy định rõ hành vi nếu server hỗ trợ | Tránh kết quả/phạm vi bất ngờ |
| **Quyền truy cập** | Kiểm tra quyền của caller và ACL cho service identity | Filter không phải cơ chế phân quyền |

Giới hạn ở client/service có ý nghĩa nhưng không thay thế **giới hạn phía server**. Những chính sách time/size limit của directory, kiểm soát truy cập và quan sát truy vấn chậm vẫn cần thiết. Nếu directory trả kết quả một phần hoặc lỗi `sizeLimitExceeded`, ứng dụng phải xử lý minh bạch, không âm thầm coi danh sách một phần là kết quả đầy đủ cho quyết định quan trọng.

### 7.1. Kết quả search là dữ liệu từ nguồn ngoài

Khi LDAP server trả lại `cn`, `description`, `mail` hoặc attribute khác, ứng dụng vẫn cần:

- Kiểm tra kiểu dữ liệu, attribute có/không có và đa giá trị theo cách mapper hỗ trợ.
- Kiểm tra dữ liệu trước khi đưa vào logic nghiệp vụ, đặc biệt nếu schema thực khác profile.
- Encode đúng ngữ cảnh đầu ra khi hiển thị trong HTML; escape LDAP filter **không thay thế HTML escaping**.
- Tránh log toàn bộ attributes hoặc hiển thị dữ liệu vượt quyền caller.

Một filter đúng cú pháp không làm cho **giá trị attribute trả về** tự động trở thành dữ liệu an toàn cho mọi đích sử dụng.

## 8. Phân biệt lỗi validation với lỗi tìm kiếm/directory

Để ứng dụng phản hồi đúng, nên chia lỗi theo nơi phát hiện và trách nhiệm khắc phục:

| Tình huống | Nhóm lỗi | Phản hồi và cách xử lý |
| --- | --- | --- |
| `uid` chứa ký tự bị chính sách cấm | Input validation | Từ chối trước search, trả field error |
| Người dùng cố chọn attribute ngoài allowlist | Input/business validation | Từ chối trước search |
| Caller không có quyền đọc hồ sơ | Authorization | Trả lỗi truy cập phù hợp, không tiết lộ nội dung |
| Search thành công nhưng danh sách rỗng | Kết quả nghiệp vụ | Trả empty/not-found theo API, không gán lỗi cú pháp |
| Không thể kết nối/TLS handshake lỗi | Directory/connectivity | Thông báo phụ thuộc tạm thời, log/giám sát |
| LDAP `noSuchObject` | Directory operation | Kiểm tra base DN, nhánh và trạng thái thư mục |
| LDAP `sizeLimitExceeded`/`timeLimitExceeded` | Search giới hạn | Giảm scope, paging, chỉnh giới hạn hoặc điều tra tải |
| Create/modify trả `objectClassViolation` | Schema/directory | Kiểm tra payload, profile schema và directory |
| Create trùng DN | Directory state/concurrency | Xử lý conflict; không xem filter search trước là khóa |

Không gửi trực tiếp `exception.getMessage()` về client: thông điệp LDAP có thể chứa DN, filter, host hoặc dữ liệu nhạy cảm. Nên dùng mã lỗi ứng dụng ổn định, `correlationId`, log thông tin đã làm sạch và giữ cause nội bộ để điều tra.

## 9. Kiểm thử: filter an toàn và validation hiệu quả là hai yêu cầu riêng

### 9.1. Unit test: input sai phải dừng trước I/O

Với Mockito và JUnit 5:

```java
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verifyNoInteractions;

import org.junit.jupiter.api.Test;
import org.springframework.ldap.core.LdapTemplate;

class PeopleLookupServiceTest {
    @Test
    void invalidUidNeverSearchesDirectory() {
        LdapTemplate template = mock(LdapTemplate.class);
        var service = new PeopleLookupService(template);

        assertThrows(IllegalArgumentException.class, () ->
                service.findByUid(
                        new PeopleLookupService.PersonLookup("alice*")));

        verifyNoInteractions(template);
    }

    @Test
    void emptyUidNeverSearchesDirectory() {
        LdapTemplate template = mock(LdapTemplate.class);
        var service = new PeopleLookupService(template);

        assertThrows(IllegalArgumentException.class, () ->
                service.findByUid(
                        new PeopleLookupService.PersonLookup("")));

        verifyNoInteractions(template);
    }
}
```

Các test này không xác minh cú pháp filter. Chúng xác minh **policy đầu vào** đã chặn trước lúc gọi `LdapTemplate`.

### 9.2. Unit test: filter builder giữ ký tự đặc biệt là dữ liệu

Với chức năng tìm tên hiển thị cho phép dấu ngoặc và dấu `*` như ký tự literal, cần kiểm thử đường escape **riêng**. Ví dụ:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;
import org.springframework.ldap.filter.EqualsFilter;

class FilterEncodingTest {
    @Test
    void specialCharactersCannotBecomeFilterOperators() {
        EqualsFilter filter = new EqualsFilter("cn", "A*(B)");

        // Theo cú pháp LDAP filter: '*' -> \2a, '(' -> \28, ')' -> \29.
        assertEquals("(cn=A\\2a\\28B\\29)", filter.encode());
    }
}
```

Điểm cần kiểm tra là ký tự đặc biệt trong **giá trị** được biểu diễn như dữ liệu, không làm thay đổi cây biểu thức filter. Tùy phiên bản/công cụ encode, nên đối chiếu cách viết ký tự hex và matching behavior trong kiểm thử tích hợp, không tự lập trình lại filter encoder.

### 9.3. Bảng tình huống kiểm thử tích hợp

| Ca kiểm thử | Điều cần xác minh |
| --- | --- |
| Tra cứu `uid=alice` hợp lệ | Query đúng search base/scope, chỉ tìm trong `ou=people` |
| `uid` sai định dạng | Không có lời gọi LDAP |
| Tên hiển thị chứa `*`, `(`, `)`, dấu gạch chéo ngược | Filter builder xử lý đúng theo cú pháp; không mở rộng kết quả bất ngờ |
| Client gửi tên field không có trong allowlist | Bị chặn trước khi dựng query |
| Search trả 0 entry | API giải thích đúng kết quả rỗng, không nhầm lỗi directory |
| Search trả nhiều entry với tiêu chí yêu cầu duy nhất | Không tự lấy entry đầu làm sự thật duy nhất |
| LDAP service account không có quyền đọc attribute | API không lộ dữ liệu, mapper xử lý attribute thiếu |
| Truy vấn quá rộng/đạt size limit | Xử lý giới hạn, paging và kết quả một phần hợp lý |
| Tạo `inetOrgPerson` thiếu `sn` | Server từ chối schema, dù search filter đã được xây đúng |
| Hai request cùng tạo một DN | Server phát hiện xung đột; pre-search không bảo đảm uniqueness |
| LDAP/TLS unavailable | Phân loại lỗi kết nối; không đổ cho input |

Nên kiểm thử trên directory riêng có schema/ACL tương ứng với môi trường mục tiêu. Test filter injection, giới hạn tìm kiếm và lỗi mạng cần dữ liệu giả, tài khoản thử nghiệm và quan sát mức tải phù hợp.

## 10. Checklist để không nhầm filter với validation toàn diện

- [ ] Xác định filter chỉ có nhiệm vụ **chọn entry** phù hợp với tìm kiếm.
- [ ] Validate dữ liệu đầu vào theo quy tắc từng field, kể cả khi filter encoder có escape.
- [ ] Dùng `LdapQueryBuilder` hoặc bộ xây filter phù hợp; không nối dữ liệu người dùng thành filter thô.
- [ ] Chỉ cho chọn attribute/toán tử từ allowlist; tự quản lý vị trí wildcard khi có tìm kiếm substring.
- [ ] Phân biệt filter escaping, DN escaping và kiểm tra giá trị attribute.
- [ ] Cố định hoặc giới hạn search base/scope; đặt giới hạn số kết quả, thời gian và paging hợp lý.
- [ ] Kiểm tra authorization của caller và ACL của tài khoản LDAP theo từng thao tác.
- [ ] Không dùng search filter để so mật khẩu thay cho cơ chế xác thực/bind phù hợp.
- [ ] Trước create/update, xác minh object class, các `MUST` kế thừa và quy tắc nghiệp vụ; để server xác minh cuối cùng.
- [ ] Không coi pre-search là cơ chế bảo đảm DN/attribute duy nhất trong môi trường có cạnh tranh.
- [ ] Phân biệt search rỗng, thiếu quyền, lỗi base, lỗi schema và lỗi kết nối.
- [ ] Kiểm thử độc lập **input policy**, **filter escaping**, **authorization**, **schema validation** và xử lý lỗi.

**Kết luận:** Spring LDAP cung cấp API xây search filter an toàn, nhưng filter chỉ kiểm soát *điều kiện chọn entry*. Một hệ thống quản lý thư mục đáng tin cậy phải đồng thời có input validation, business validation, schema validation, DN handling, authorization, giới hạn truy vấn và xử lý lỗi directory. Chỉ khi các tầng này phối hợp, dữ liệu hợp lệ mới được tìm đúng phạm vi và thao tác LDAP mới được thực hiện đúng quy tắc.
