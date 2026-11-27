# Chọn attribute trả về trong search

Một ứng dụng dùng **Spring LDAP** thường chỉ cần vài trường để hiển thị danh sách người dùng: `uid`, `cn` và `mail`. Tuy nhiên, nếu yêu cầu LDAP search trả toàn bộ thuộc tính của mỗi entry, phản hồi có thể chứa cả ảnh `jpegPhoto`, thông tin chi tiết không dùng đến hoặc dữ liệu có dung lượng lớn. Việc **chọn attribute trả về** (attribute selection/projection) giúp kết quả đúng nhu cầu, giảm dữ liệu truyền qua mạng và làm rõ hợp đồng dữ liệu giữa LDAP với ứng dụng.

Đây là bài thuộc chương **Search scope** của module **SPRING_LDAP**. Bài học đặt việc chọn thuộc tính trong tổng thể một phép tìm kiếm LDAP: **base DN**, **scope**, **filter**, **requested attributes** và quyền truy cập. Bạn sẽ thực hành bằng `LdapTemplate`, `LdapQueryBuilder`, `SearchControls` của JNDI, đồng thời hiểu cách xử lý thuộc tính không được trả về.

Sau bài này, bạn có thể:

- Phân biệt thuộc tính được **dùng trong filter** với thuộc tính được **yêu cầu trả về**.
- Chọn một danh sách thuộc tính cụ thể hoặc các lựa chọn đặc biệt `*`, `+` và `1.1`.
- Hiểu mặc định của LDAP SearchRequest và sự khác biệt cần chú ý khi dùng `SearchControls` của JNDI.
- Viết truy vấn Spring LDAP chỉ lấy các trường cần thiết và ánh xạ `Attributes` an toàn.
- Chẩn đoán việc một thuộc tính không xuất hiện trong kết quả, kể cả trường hợp thiếu dữ liệu, quyền truy cập hoặc khác biệt server.

## 1. Một phép LDAP search gồm những gì?

Xét thư mục giả định:

```text
dc=example,dc=org
├── ou=people
│   ├── uid=lan
│   ├── uid=minh
│   └── uid=ha
└── ou=groups
    └── cn=developers
```

Giả sử người dùng có một số thuộc tính như:

```ldif
dn: uid=lan,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: lan
cn: Lan Nguyen
sn: Nguyen
mail: lan@example.org
telephoneNumber: +84 123 456 789
```

Một search có thể được mô tả bằng năm thành phần:

| Thành phần | Ví dụ | Trả lời câu hỏi |
| --- | --- | --- |
| **Base DN** | `ou=people,dc=example,dc=org` | Bắt đầu ở nhánh nào? |
| **Scope** | Subtree | Xem entry gốc, con trực tiếp hay cả cây con? |
| **Filter** | `(objectClass=inetOrgPerson)` | Entry nào thỏa điều kiện? |
| **Requested attributes** | `uid`, `cn`, `mail` | Với mỗi entry khớp, cần gửi lại thuộc tính nào? |
| **Controls/limits** | Giới hạn số kết quả, thời gian | Cách ràng buộc phép tìm kiếm? |

**Search scope** quyết định *tập entry có thể được xét*. **Filter** quyết định *entry nào khớp*. **Requested attributes** quyết định *dữ liệu thuộc tính nào được yêu cầu trong các entry trả về*. Ba khái niệm này độc lập.

Ví dụ cùng một entry `uid=lan` khớp filter:

```text
Filter:             (objectClass=inetOrgPerson)
Requested attrs:    uid, cn
Returned entry:     DN + { uid: lan, cn: Lan Nguyen }
```

Dù entry còn có `sn`, `mail` và `telephoneNumber`, ứng dụng chỉ yêu cầu `uid` và `cn`. Server có thể chỉ trả những thuộc tính được yêu cầu và được phép xem.

## 2. Danh sách thuộc tính trả về hoạt động ra sao?

Trong giao thức LDAP, SearchRequest có trường `attributes` chứa danh sách **attribute descriptions** được yêu cầu. Danh sách này có thể gồm các tên cụ thể hoặc những giá trị đặc biệt. Theo [RFC 4511, mục SearchRequest](https://www.rfc-editor.org/rfc/rfc4511), có các cách sử dụng quan trọng:

| Danh sách yêu cầu (ý nghĩa ở mức giao thức) | Kết quả được yêu cầu |
| --- | --- |
| `["uid", "cn", "mail"]` | Chỉ các thuộc tính `uid`, `cn`, `mail`. |
| `[]` — danh sách trống trong SearchRequest LDAP | Mặc định: **tất cả user attributes**. |
| `["*"]` | Tất cả **user attributes**. |
| `["1.1"]` | **Không trả về thuộc tính nào**. |
| `["uid", "cn", "+"]` | `uid` và `cn`, kèm các operational attributes được phép và server hỗ trợ. |
| `["*", "+"]` | User attributes và operational attributes theo khả năng server và quyền truy cập. |

Một **user attribute** ở đây là nhóm thuộc tính được giao thức phân loại là thuộc tính thông thường của entry, ví dụ `uid`, `cn`, `mail`. Tên “user” không có nghĩa chỉ thuộc tính của tài khoản người dùng; group hay organizational unit cũng có user attributes của riêng chúng.

**Operational attributes** là những thuộc tính phục vụ hoạt động của directory, chẳng hạn `createTimestamp`, `modifyTimestamp` hoặc `creatorsName` nếu server hỗ trợ và cho phép đọc. Chúng thường **không được trả mặc định** cùng danh sách user attributes.

### Danh sách trống, `*` và `1.1` không giống nhau

Ở mức **LDAP SearchRequest**, không chỉ định tên thuộc tính nào (danh sách trống) có nghĩa là **yêu cầu tất cả user attributes**. Ký hiệu `*` là cách yêu cầu tường minh cùng nhóm user attributes. Ngược lại, chuỗi `1.1` (OID đặc biệt) thể hiện ý định **không lấy attribute**.

Ví dụ khi ứng dụng chỉ muốn biết một entry có tồn tại hoặc thu thập DN của entry khớp, nó có thể yêu cầu không lấy thuộc tính:

```text
Base:             ou=people,dc=example,dc=org
Filter:           (uid=lan)
Requested attrs:  1.1
Kết quả:          entry khớp kèm DN, không có tập thuộc tính dữ liệu
```

Quy tắc này nằm ở **giao thức LDAP**. Khi làm việc qua Java JNDI, cần xem cả hợp đồng của `SearchControls`: một mảng thuộc tính rỗng trong JNDI được dùng để yêu cầu không có thuộc tính, khác với **danh sách trống trong SearchRequest** trên đường truyền. Phần JNDI bên dưới sẽ minh họa rõ.

## 3. Attribute dùng trong filter không buộc phải được trả về

Đây là nhầm lẫn thường gặp nhất.

Giả sử filter:

```ldap
(&(objectClass=inetOrgPerson)(mail=*))
```

và danh sách thuộc tính trả về chỉ là:

```text
uid, cn
```

Server vẫn có thể đánh giá điều kiện `objectClass` và `mail` để chọn entry, trong khi ứng dụng **không yêu cầu nhận lại** hai thuộc tính đó. Filter và danh sách thuộc tính trả về đảm nhiệm hai vai trò độc lập.

| Thuộc tính | Dùng để lọc? | Yêu cầu trả về? |
| --- | --- | --- |
| `objectClass` | Có | Không |
| `mail` | Có (presence) | Không |
| `uid` | Không | Có |
| `cn` | Không | Có |

Một ví dụ khác:

```text
Filter:      (uid=lan)
Attributes:  cn, mail
```

Trong trường hợp này, `uid` vẫn quyết định entry nào được chọn, nhưng kết quả có thể chỉ chứa `cn` và `mail`. Vì vậy, code mapper không nên cố đọc `uid` nếu nó không nằm trong projection.

**Quyền truy cập vẫn áp dụng.** Không yêu cầu trả một thuộc tính không đồng nghĩa ứng dụng được phép dùng thuộc tính đó để lọc trên mọi server. Quyền tìm kiếm/filter và quyền đọc/nhìn thấy thuộc tính có thể được xử lý theo ACL riêng.

## 4. Chọn chính xác các attribute cần dùng

Khi UI chỉ cần danh sách người dùng, hãy chỉ yêu cầu những trường thực sự hiển thị:

```text
uid, cn, mail
```

So với yêu cầu mặc định tất cả user attributes, cách này có thể giảm dữ liệu trả về, đặc biệt nếu entry chứa ảnh, chứng chỉ hoặc các thuộc tính nhiều giá trị.

| Nhu cầu của màn hình/API | Thuộc tính nên yêu cầu |
| --- | --- |
| Danh sách người dùng | `uid`, `cn`, `mail` |
| Danh sách nhóm | `cn`, thêm thuộc tính cần thiết theo schema nhóm |
| Trang chi tiết cá nhân | `uid`, `cn`, `mail`, `telephoneNumber` nếu được phép |
| Kiểm tra entry có tồn tại | Không cần attribute dữ liệu (dùng `1.1` hoặc cơ chế phù hợp ở API) |
| Hiển thị ảnh đại diện | `jpegPhoto` khi thực sự cần, cân nhắc lấy riêng |
| Xem thông tin thay đổi entry | Thuộc tính vận hành liên quan, nếu server hỗ trợ và ACL cho phép |

**Không giả định mọi entry đều có cùng schema.** Nếu filter quá rộng, những entry được trả có thể thiếu `uid` hoặc `cn`. Trong Spring LDAP, cần xử lý `Attributes.get(name) == null` thay vì ép kiểu trực tiếp mà không kiểm tra.

### Chọn attribute không phải cơ chế phân quyền

Bằng cách không yêu cầu `telephoneNumber`, một endpoint sẽ không vô tình gửi số điện thoại của entry vào DTO. Tuy nhiên, đây chỉ là **giảm dữ liệu và giới hạn hợp đồng phản hồi**, không thay thế ACL: một client khác có thể vẫn yêu cầu attribute đó nếu tài khoản bind có quyền.

Các thuộc tính nhạy cảm cần được bảo vệ bằng quyền LDAP, chính sách ứng dụng, TLS và giới hạn API. Danh sách requested attributes **không tự cấp hay thu hồi quyền** trên directory.

## 5. `*` và `+`: user attributes và operational attributes

### `*`: các thuộc tính thông thường

Filter có thể chọn entry người dùng, trong khi `*` yêu cầu mọi user attribute mà server quyết định được phép trả:

```text
Requested attributes: *
```

Đây là lựa chọn hữu ích khi thăm dò directory trong môi trường test hoặc công cụ quản trị, nhưng **không nhất thiết phù hợp** với API danh sách nhiều entry vì dữ liệu có thể lớn và không ổn định theo schema.

### `+`: các thuộc tính vận hành

[**RFC 3673**](https://www.rfc-editor.org/rfc/rfc3673) quy định tùy chọn `+` để yêu cầu operational attributes nếu server hỗ trợ. Ví dụ:

```text
Requested attributes: +
```

Các attribute có thể bao gồm `createTimestamp` và `modifyTimestamp`, nhưng **không bảo đảm server nào cũng hỗ trợ cùng tập** hoặc luôn trả chúng. ACL cũng có thể hạn chế truy cập.

Có thể kết hợp:

```text
uid, cn, +
```

Khi đó ứng dụng chỉ yêu cầu hai user attributes được nêu và các operational attributes khả dụng. Còn:

```text
*, +
```

là cách yêu cầu cả hai nhóm, theo khả năng server.

### Có thể yêu cầu operational attribute bằng tên

Nếu chỉ quan tâm `modifyTimestamp`, thường nên yêu cầu **tên cụ thể** thay vì toàn bộ `+`:

```text
uid, modifyTimestamp
```

Cách này giúp mục đích rõ ràng hơn và tiết kiệm dữ liệu. Server vẫn có thể bỏ qua thuộc tính không tồn tại hoặc không được phép trả về.

Một số hệ thống có thuộc tính riêng như `memberOf` (phụ thuộc server/overlay hoặc Active Directory). Không coi các tên hoặc tùy chọn có trên một server là mặc định chung cho mọi triển khai LDAP.

## 6. `1.1`: chỉ lấy DN hoặc kiểm tra entry khớp

OID đặc biệt `1.1` có nghĩa **không lấy attribute** khi được yêu cầu một mình:

```text
Requested attributes: 1.1
```

LDAP SearchResultEntry vẫn có **object name (DN)** và có thể có danh sách thuộc tính rỗng. DN là một phần cấu trúc của kết quả LDAP, **không phải** một user attribute tên `dn` mà luôn phải yêu cầu trả về.

Những tình huống hữu ích:

- Kiểm tra entry nào khớp filter mà không cần dữ liệu chi tiết.
- Thu thập tên của các entry để xử lý tiếp.
- Giảm dung lượng khi chỉ quan tâm kết quả có tồn tại hay không.

Không trộn `1.1` với các tên thuộc tính nếu mục đích là “không lấy attribute”. Theo quy tắc giao thức, `1.1` không mang ý nghĩa lọc bớt các attribute khác trong cùng danh sách; để tránh hiểu nhầm, hãy dùng riêng `1.1` khi muốn lấy danh sách thuộc tính rỗng.

**Điểm cần chú ý trong Spring LDAP:** `AttributesMapper` chỉ nhìn thấy các thuộc tính đã được trả về, nên nó **không thích hợp để đọc DN** nếu bạn cố lấy DN từ thuộc tính `dn`. Để làm việc với tên entry, chọn API/mapper có ngữ cảnh entry, chẳng hạn `ContextMapper` với `DirContextOperations.getDn()`, rồi xác định tên được biểu diễn tương đối so với base nào của ứng dụng.

## 7. Spring LDAP: projection bằng `LdapQueryBuilder.attributes(...)`

Giả sử `ContextSource` đã được cấu hình an toàn với base `dc=example,dc=org` và đã có `LdapTemplate` trong service. Để tìm người dùng dưới nhánh `ou=people`, chỉ yêu cầu `uid`, `cn` và `mail`.

```java
import java.util.List;
import javax.naming.NamingException;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;

public class UserDirectoryService {
    private final LdapTemplate ldapTemplate;

    public UserDirectoryService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<UserSummary> listPeople() {
        LdapQuery query = LdapQueryBuilder.query()
            .base("ou=people")
            .attributes("uid", "cn", "mail")
            .where("objectClass").is("inetOrgPerson");

        return ldapTemplate.search(
            query,
            (AttributesMapper<UserSummary>) attrs ->
                new UserSummary(
                    firstText(attrs, "uid"),
                    firstText(attrs, "cn"),
                    firstText(attrs, "mail")
                )
        );
    }

    private static String firstText(Attributes attrs, String name)
            throws NamingException {
        Attribute attribute = attrs.get(name);
        if (attribute == null || attribute.size() == 0) {
            return null;
        }
        Object value = attribute.get();
        if (!(value instanceof String)) {
            throw new IllegalStateException(
                "Attribute " + name + " không phải String"
            );
        }
        return (String) value;
    }

    public static class UserSummary {
        public final String uid;
        public final String cn;
        public final String mail;

        public UserSummary(String uid, String cn, String mail) {
            this.uid = uid;
            this.cn = cn;
            this.mail = mail;
        }
    }
}
```

Diễn giải:

1. `.base("ou=people")` xác định **nhánh tìm kiếm tương đối** so với base đã cấu hình trong `ContextSource`.
2. `.where("objectClass").is("inetOrgPerson")` xác định **filter**.
3. `.attributes("uid", "cn", "mail")` xác định **projection**: chỉ yêu cầu ba thuộc tính.
4. `ldapTemplate.search(query, mapper)` trả danh sách DTO `UserSummary`; mapper chỉ đọc các thuộc tính đã yêu cầu.
5. Hàm `firstText` xử lý trường hợp thuộc tính bị thiếu và từ chối kiểu bất ngờ, tránh `NullPointerException` hoặc `ClassCastException` khó hiểu.

**Vì sao filter dùng `objectClass` nhưng mapper không đọc nó?** Vì ứng dụng không yêu cầu trả lại `objectClass`. Thuộc tính vẫn có thể được dùng trong filter mà không xuất hiện trong `Attributes` kết quả.

Ví dụ lấy một giá trị bằng `Attribute.get()` chỉ minh họa ánh xạ một trường. Nếu thuộc tính **đa trị**, `get()` không cho bạn toàn bộ tập giá trị; hãy dùng `Attribute.getAll()` và định nghĩa cách biểu diễn danh sách trong DTO.

### Khác biệt giữa `LdapTemplate` và `LdapClient`

`LdapClient` cung cấp API thuận tiện hơn cho nhiều thao tác LDAP ở những phiên bản Spring LDAP hỗ trợ, còn `LdapTemplate` là cách phổ biến để thực hiện search với callback. Dù dùng API nào, nguyên tắc vẫn như nhau: **yêu cầu đúng attribute**, xử lý giá trị có thể thiếu, và không dùng projection thay thế kiểm soát quyền. Kiểm tra chữ ký API theo phiên bản Spring LDAP của dự án trước khi chuyển ví dụ giữa các client.

## 8. Chọn attribute qua JNDI `SearchControls`

Đôi khi bạn cần điều khiển scope, số kết quả, thời gian và attributes trong một đối tượng. JNDI cung cấp `javax.naming.directory.SearchControls`, và `LdapTemplate` có overload cho phép dùng nó.

```java
import java.util.List;
import javax.naming.directory.SearchControls;
import org.springframework.ldap.core.AttributesMapper;

// Trong service đã có ldapTemplate:
SearchControls controls = new SearchControls();
controls.setSearchScope(SearchControls.SUBTREE_SCOPE);
controls.setReturningAttributes(
    new String[] { "uid", "cn", "mail" }
);
controls.setCountLimit(100);
controls.setTimeLimit(3000); // Mili giây.

List<String> displayNames = ldapTemplate.search(
    "ou=people",
    "(objectClass=inetOrgPerson)",
    controls,
    (AttributesMapper<String>) attrs -> {
        if (attrs.get("cn") == null) {
            return null;
        }
        return (String) attrs.get("cn").get();
    }
);
```

Ở đây:

- `setSearchScope(SearchControls.SUBTREE_SCOPE)` xác định phạm vi subtree.
- `setReturningAttributes(...)` chỉ định các thuộc tính cần nhận.
- `setCountLimit(100)` và `setTimeLimit(3000)` ràng buộc phép tìm kiếm ở mức API; cách thực thi, lỗi giới hạn và tương tác với server phụ thuộc provider.
- Search base `ou=people` thường là tên tương đối khi `ContextSource` đã có base `dc=example,dc=org`.

Các giới hạn search **không tương đương với phân trang**. Nếu ứng dụng cần tải nhiều trang kết quả ổn định trên directory lớn, cần giải pháp pagination mà LDAP server và API hỗ trợ.

### Chú ý: mảng rỗng trong JNDI khác danh sách trống ở giao thức LDAP

`SearchControls.setReturningAttributes` có semantics của **JNDI API**:

| Java JNDI | Mục đích |
| --- | --- |
| `setReturningAttributes(new String[] {"uid", "cn"})` | Yêu cầu `uid` và `cn`. |
| `setReturningAttributes(null)` | Yêu cầu tất cả user attributes (mặc định theo JNDI). |
| `setReturningAttributes(new String[0])` | Yêu cầu **không có attribute nào**. |

Hãy phân biệt với **LDAP SearchRequest**: danh sách tên thuộc tính **trống ở giao thức** mang nghĩa lấy tất cả user attributes. Provider JNDI sẽ ánh xạ ý định của API vào yêu cầu giao thức phù hợp; đừng suy luận rằng `new String[0]` chắc chắn được gửi đi thành một danh sách rỗng mang cùng nghĩa với RFC 4511.

Đây là lý do khi chuyển một ví dụ từ LDAP protocol sang Java, phải đọc **hợp đồng của API trung gian** thay vì chỉ nhìn ký hiệu `[]`.

## 9. Nếu attribute không xuất hiện trong kết quả, điều đó có nghĩa gì?

Trong Java, đoạn sau có thể trả `null`:

```java
Attribute mail = attrs.get("mail");
```

Không nên kết luận ngay rằng “entry không có email”. Một attribute không xuất hiện trong kết quả có thể vì:

1. **Không được yêu cầu:** projection chỉ lấy `uid` và `cn`; `mail` bị lược khỏi response theo chủ ý.
2. **Entry thực sự không có attribute:** ví dụ người dùng chưa khai báo email.
3. **Quyền truy cập:** tài khoản bind không được đọc hoặc thấy `mail`.
4. **Tên attribute/option không phù hợp:** server có thể không hỗ trợ một attribute description hoặc option được yêu cầu.
5. **Khác biệt server/schema:** ví dụ trường `memberOf` chỉ có trên một số directory với cấu hình phù hợp.
6. **Đặc thù attribute vận hành:** operational attribute có thể yêu cầu rõ tên hoặc `+` và vẫn tùy quyền/server.

Nên phân biệt các tình huống này từ **cấu hình truy vấn**, **schema và ACL** và **dữ liệu thực tế**. Nếu bạn vừa thêm thuộc tính vào mapper mà quên thêm vào `.attributes(...)`, việc đọc ra `null` là kết quả hoàn toàn có thể dự đoán.

### DN và `objectClass` có tự động nằm trong `Attributes` không?

DN là **tên của entry trong phản hồi search**, không phải thuộc tính dữ liệu thông thường bắt buộc có tên `dn`. Vì thế, chọn `"uid", "cn"` không làm DN biến mất khỏi định danh của SearchResultEntry; nhưng `AttributesMapper` không nhất thiết phơi bày DN qua một thuộc tính thông thường.

`objectClass` là một thuộc tính LDAP. Nếu bạn yêu cầu chỉ `uid` và `cn`, thì **không nên mong** mapper tự thấy `objectClass`, dù filter sử dụng nó.

Tùy server, có thể gặp thuộc tính đặc thù như `distinguishedName` trên Active Directory; không đồng nhất thuộc tính riêng này với trường DN của giao thức LDAP.

## 10. Chọn attributes khi dữ liệu lớn hoặc nhạy cảm

Các entry LDAP có thể chứa dữ liệu lớn hoặc có tính riêng tư như `jpegPhoto`, chứng chỉ, thông tin liên hệ hoặc thuộc tính đa trị. Một projection phù hợp giúp:

- Giảm lưu lượng trên mỗi entry khi kết quả search chứa hàng trăm hoặc hàng nghìn entry.
- Tránh giải mã hoặc sao chép `byte[]` không cần thiết.
- Giữ DTO gọn và ổn định khi schema trên server có thêm attribute.
- Tránh vô tình đưa thông tin ngoài yêu cầu nghiệp vụ vào API hoặc log.
- Dễ kiểm thử vì biết rõ contract “search này trả những trường nào”.

Ví dụ màn hình danh sách chỉ cần `uid`, `cn`, `mail`. Khi người dùng mở trang hồ sơ và thực sự muốn xem ảnh, ứng dụng có thể gọi thao tác riêng để lấy `jpegPhoto`. Cách chia này giảm khả năng đọc ảnh hàng loạt khi không cần.

### Projection không kiểm soát số entry tìm được

Nếu filter `(objectClass=*)` trên toàn cây khớp 100.000 entry, dù chỉ yêu cầu `uid`, truy vấn vẫn có thể tốn nhiều tài nguyên do số entry cần xét. Cần kết hợp:

- **Base DN hẹp:** ví dụ `ou=people` thay vì toàn bộ directory.
- **Scope phù hợp:** chỉ tìm con trực tiếp nếu nghiệp vụ không cần subtree.
- **Filter cụ thể:** equality trên các thuộc tính có index phù hợp thường tốt hơn filter quá rộng.
- **Giới hạn số kết quả, thời gian và phân trang** theo khả năng server.
- **Projection tối thiểu:** chỉ lấy các attribute cần cho phản hồi.

Do đó, chọn attribute là **một phần của thiết kế search hiệu quả**, không thể thay thế các phần còn lại.

## 11. Kiểm thử projection và xử lý lỗi

Khi kiểm thử tích hợp với LDAP test server hoặc directory nội bộ đã được phân quyền, tạo một entry có `uid`, `cn`, `mail`, `sn` và một attribute tùy chọn. Sau đó kiểm tra:

| Kịch bản | Yêu cầu | Điều cần xác nhận |
| --- | --- | --- |
| Danh sách cột tối thiểu | `uid`, `cn` | Có hai thuộc tính, không phụ thuộc `mail`/`sn` trong mapper. |
| Filter khác projection | Filter `(mail=*)`, chỉ trả `uid` | Entry vẫn được lọc theo `mail`; mapper không đòi `mail`. |
| User attributes mặc định | Mặc định hoặc `*` | Các user attributes được phép xuất hiện theo server. |
| Operational attributes | `modifyTimestamp` hoặc `+` | Giá trị được trả nếu server/ACL hỗ trợ. |
| Không lấy attribute | `1.1` ở mức giao thức / cấu hình API phù hợp | Vẫn có entry khớp và DN, không lấy dữ liệu attribute. |
| Thuộc tính vắng mặt | Yêu cầu `mail` trên entry không có mail | Mapper xử lý `null` đúng. |
| Dữ liệu nhị phân lớn | Chỉ yêu cầu `uid` và `cn` | Không trả ảnh `jpegPhoto` trong kết quả. |
| Kết quả nhiều entry | Giới hạn count/time | Phản ứng đúng khi server/provider áp dụng giới hạn. |
| Quyền bị hạn chế | Tài khoản không được xem một attribute | Không suy luận thiếu dữ liệu chỉ từ projection; xử lý theo chính sách. |

Nếu test server hỗ trợ operational attributes khác server sản xuất, hãy tách kết quả *mà giao thức cho phép* khỏi *kết quả mà sản phẩm LDAP cụ thể cung cấp*. Tránh viết kiểm thử giả định mọi server đều trả `modifyTimestamp`.

### Những lỗi thường gặp

| Hiện tượng | Nguyên nhân điển hình | Cách xử lý |
| --- | --- | --- |
| Mapper trả `null` cho `mail` | Quên yêu cầu `mail` trong `attributes(...)`. | Thêm `mail` vào projection nếu DTO cần nó. |
| Dữ liệu trả về quá lớn | Không chỉ định attributes hoặc dùng `*`. | Chỉ yêu cầu trường cần thiết, tách ảnh ra thao tác riêng. |
| Mong thấy `createTimestamp` nhưng không có | Đây là operational attribute. | Thử yêu cầu rõ tên hoặc `+`; kiểm tra server và ACL. |
| Tưởng `1.1` là tên của một trường | Nhầm OID đặc biệt với user attribute. | Dùng `1.1` một mình khi muốn không lấy attribute. |
| Muốn có DN nhưng `attrs.get("dn")` rỗng | DN nằm trong thành phần name của search result. | Dùng API có ngữ cảnh entry để lấy DN. |
| Filter dùng `mail` nhưng mapper thiếu `mail` | Filter và projection là hai phần khác nhau. | Chỉ đọc attribute đã yêu cầu trả về. |
| Sửa `setReturningAttributes(new String[0])` rồi không nhận dữ liệu | JNDI mảng rỗng yêu cầu không có attribute. | Dùng danh sách tên cụ thể hoặc `null` theo nhu cầu. |
| Search đúng trên OpenLDAP nhưng thiếu field ở AD | Schema, attribute description, ACL khác nhau. | Kiểm tra tài liệu server và phép tìm bằng tài khoản thực tế. |

## 12. Tình huống thực hành

Bạn xây dựng endpoint **GET /directory/people**. Mỗi dòng trên giao diện chỉ có mã người dùng, tên và email. `ContextSource` đã có base `dc=example,dc=org`, và các entry người dùng ở nhánh `ou=people`.

**Câu hỏi 1.** Search base tương đối, filter và requested attributes phù hợp là gì?

**Lời giải:**

```text
Base:       ou=people
Filter:     (objectClass=inetOrgPerson)
Attributes: uid, cn, mail
```

Với Spring LDAP:

```java
LdapQuery query = LdapQueryBuilder.query()
    .base("ou=people")
    .attributes("uid", "cn", "mail")
    .where("objectClass").is("inetOrgPerson");
```

**Câu hỏi 2.** Vì sao không cần thêm `objectClass` vào `attributes(...)` dù filter sử dụng nó?

**Lời giải:** Server dùng `objectClass` để đánh giá điều kiện lọc. Projection chỉ quyết định những dữ liệu cần gửi lại. UI không hiển thị `objectClass` thì không cần yêu cầu nó.

**Câu hỏi 3.** Khi API chỉ cần biết các entry nào khớp, không cần đọc thuộc tính, nên chọn gì?

**Lời giải:** Ở mức giao thức, yêu cầu `1.1` một mình. Khi dùng API Java cụ thể, chọn chức năng tương ứng của API và mapper có thể nhận tên entry/DN nếu cần. Với JNDI `SearchControls`, mảng rỗng thể hiện ý định không lấy attributes.

**Câu hỏi 4.** Có nên dùng `*` cho danh sách người dùng rất dài vì “cấu hình đơn giản” không?

**Lời giải:** Chỉ dùng `*` nếu thật sự cần tất cả user attributes. Với danh sách, projection `uid`, `cn`, `mail` thường rõ ràng và tiết kiệm hơn, đặc biệt nếu entry có `jpegPhoto` hoặc attribute đa trị lớn.

**Câu hỏi 5.** API yêu cầu `mail` nhưng mapper trả `null`. Có thể kết luận người dùng không có email không?

**Lời giải:** Chưa thể. Phải xét schema, quyền truy cập của tài khoản bind, tên attribute, dữ liệu và behavior của server. `null` chỉ chứng minh kết quả trả về không có giá trị để mapper đọc.

**Câu hỏi 6.** Muốn xem `modifyTimestamp`, nên yêu cầu `*` hay `+`?

**Lời giải:** `modifyTimestamp` là operational attribute trên các server hỗ trợ. Yêu cầu **trực tiếp `modifyTimestamp`** khi chỉ cần nó, hoặc thử `+` khi cần nhiều operational attributes và server hỗ trợ RFC 3673. `*` chủ yếu yêu cầu user attributes.

## 13. Ghi nhớ

**Chọn attribute trả về** là bước thiết kế riêng của một LDAP search, song song với base, scope và filter. Filter có thể dùng một attribute mà kết quả không cần trả lại. Ở mức giao thức, **danh sách trống** hoặc `*` yêu cầu tất cả user attributes; `+` yêu cầu operational attributes theo khả năng server; `1.1` yêu cầu không có attribute. Khi dùng **JNDI SearchControls**, **`null`** tương ứng yêu cầu tất cả thuộc tính thông thường, còn **mảng rỗng** thể hiện không lấy attribute.

Trong **Spring LDAP**, dùng `LdapQueryBuilder.attributes(...)` hoặc `SearchControls.setReturningAttributes(...)` để nêu rõ projection. Mapper phải xử lý giá trị có thể vắng mặt, không phụ thuộc vào những thuộc tính chỉ được dùng trong filter. Chọn đúng trường giúp giảm dữ liệu, nhưng quyền LDAP, TLS và giới hạn search vẫn phải được thực thi riêng.

Nguồn tham khảo: [RFC 4511 – Lightweight Directory Access Protocol (LDAP): The Protocol](https://www.rfc-editor.org/rfc/rfc4511), [RFC 4512 – LDAP Directory Information Models](https://www.rfc-editor.org/rfc/rfc4512), [RFC 3673 – All Operational Attributes](https://www.rfc-editor.org/rfc/rfc3673) và Java JNDI API `javax.naming.directory.SearchControls`.
