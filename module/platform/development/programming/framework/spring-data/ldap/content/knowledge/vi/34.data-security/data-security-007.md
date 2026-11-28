# Giới hạn thuộc tính nhạy cảm được đọc hoặc trả về API

Trong **Spring Data LDAP**, một entry có thể chứa nhiều thuộc tính hơn mức một màn hình hoặc API thực sự cần. Hồ sơ nhân viên có thể lưu `uid`, `cn`, `mail`, `telephoneNumber`, `jpegPhoto`, thông tin nhóm, chứng chỉ và các thuộc tính chỉ dành cho quản trị. Nếu mọi truy vấn đều tải toàn bộ entry rồi trả trực tiếp entity ra JSON, ứng dụng có nguy cơ **đọc thừa, truyền thừa và làm lộ dữ liệu**.

Giới hạn thuộc tính cần được thực hiện ở ba lớp phối hợp:

1. **LDAP query projection:** yêu cầu directory chỉ trả về những attribute mà use case cần.
2. **Directory access control:** giới hạn service account được phép đọc attribute/entry nào ở phía LDAP server.
3. **API response allowlist:** ánh xạ dữ liệu sang DTO có những trường được phép công khai, không serialize entity LDAP trực tiếp.

```text
HTTP request
    |
    v
Authorization theo người gọi và đối tượng
    |
    v
LDAP query: chỉ yêu cầu uid, cn, mail
    |
    v
LDAP ACL: chỉ trả thuộc tính service account được phép đọc
    |
    v
AttributesMapper -> DTO có allowlist
    |
    v
API response: chỉ các trường đã phê duyệt
```

Ba lớp này giải quyết các vấn đề khác nhau. **Chỉ chọn attribute trong query không thay thế ACL**; **ACL không thay thế authorization của API**; và **DTO không làm giảm lượng dữ liệu đã tải từ LDAP nếu query vẫn lấy tất cả**.

Sau bài học, bạn có thể:

- Chọn attribute cần thiết bằng `LdapQueryBuilder.attributes(...)` hoặc `SearchControls.setReturningAttributes(...)`.
- Phân biệt danh sách attribute được trả về với attribute được dùng trong filter.
- Dùng `AttributesMapper`/DTO để chỉ đưa trường đã duyệt vào API.
- Thiết lập quyền đọc tối thiểu cho LDAP service account và hiểu ACL theo attribute.
- Không trả mật khẩu, dữ liệu binary, membership nội bộ hoặc operational attribute khi không có yêu cầu được phê duyệt.
- Hiểu giới hạn của `@Attribute(readonly = true)`, `@Transient` và repository entity.
- Kiểm thử cả trường hợp attribute bị thiếu, bị ACL che giấu, đa trị và dữ liệu nhạy cảm không xuất hiện trong response/log.

## 1. Dữ liệu LDAP không phải tất cả đều dành cho API

Ví dụ một entry nhân viên:

```ldif
dn: uid=lan,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: lan
cn: Nguyen Thi Lan
sn: Nguyen
givenName: Thi Lan
mail: lan@example.org
mail: lan.work@example.org
telephoneNumber: +84 28 5555 0101
description: Internal platform engineer
manager: uid=manager01,ou=people,dc=example,dc=org
memberOf: cn=payroll-admins,ou=groups,dc=example,dc=org
jpegPhoto:: /9j/4AAQSkZJRgABAQ...
```

Đây là dữ liệu minh họa. Schema và attribute thực tế phụ thuộc directory product; `memberOf` có ở một số directory (đặc biệt Active Directory) nhưng không phải attribute bắt buộc của mọi LDAP server.

Một trang danh bạ có thể chỉ cần `uid`, `cn` và `mail`. Những trường còn lại có thể nhạy cảm hoặc không liên quan:

| Attribute | Mục đích thường gặp | Rủi ro khi trả không kiểm soát |
| --- | --- | --- |
| `uid` | Định danh đăng nhập | Tiết lộ mã tài khoản nội bộ |
| `cn`, `givenName`, `sn` | Hiển thị tên | Dữ liệu cá nhân |
| `mail` | Liên hệ | Lộ email, hỗ trợ spam/phishing |
| `telephoneNumber` | Liên hệ nội bộ | Lộ số điện thoại cá nhân/công việc |
| `manager` | Quan hệ quản lý | Tiết lộ cấu trúc tổ chức |
| `memberOf`, `member`, `uniqueMember` | Membership nhóm | Lộ nhóm đặc quyền và cấu trúc phân quyền |
| `jpegPhoto`, `thumbnailPhoto` | Ảnh | Dữ liệu cá nhân, payload lớn |
| `userCertificate` | Chứng chỉ | Thông tin định danh/hạ tầng |
| `userPassword` | Thông tin xác thực trong một số schema | Không trả như dữ liệu hồ sơ |
| `modifyTimestamp`, `createTimestamp` | Operational metadata | Có thể tiết lộ thời điểm và hoạt động nội bộ |

**Không có một danh sách attribute nhạy cảm áp dụng cho mọi tổ chức.** Phải phân loại theo mục đích sử dụng, quy định bảo vệ dữ liệu, schema và chính sách nội bộ. Mặc định an toàn là chỉ cho phép những trường cần thiết và đã được phê duyệt.

### 1.1. DN không phải attribute thông thường

DN của entry là tên phân cấp, ví dụ:

```text
uid=lan,ou=people,dc=example,dc=org
```

DN không phải một attribute tên `dn` mà mọi LDAP search có thể yêu cầu giống `cn` hoặc `mail`. Khi cần DN, dùng thông tin tên từ JNDI/Spring LDAP, ví dụ `DirContextOperations.getNameInNamespace()` hoặc mapping `@Id Name dn` của ODM. Đừng tự tạo response field DN bằng cách ghép chuỗi nếu có thể lấy tên entry đã parse.

DN có thể tiết lộ OU, tenant, bộ phận hoặc định danh người dùng. Chỉ trả DN đầy đủ nếu API thực sự cần; thường DTO nên dùng mã định danh công khai được phê duyệt thay vì full DN.

## 2. Ba lớp bảo vệ có nhiệm vụ khác nhau

| Lớp | Câu hỏi cần trả lời | Cơ chế |
| --- | --- | --- |
| Query projection | Truy vấn này cần đọc attribute nào? | `LdapQueryBuilder.attributes(...)`, `SearchControls.returningAttributes` |
| LDAP ACL | Principal kết nối có được phép đọc attribute này không? | Access control của directory, service account least privilege |
| API DTO | Người gọi endpoint này được nhận trường nào? | DTO/response model allowlist và authorization |

Ví dụ:

- Service account có quyền đọc `mail` nhưng không được đọc `userPassword`.
- Trang danh bạ yêu cầu `uid`, `cn`, `mail`.
- API trả `PersonSummary(uid, displayName, emails)`.
- Endpoint chi tiết có thể trả thêm `telephoneNumber` cho nhóm người gọi được cấp quyền.

Nếu chỉ có DTO mà query vẫn đọc tất cả, dữ liệu nhạy cảm đã đi vào heap, mapper, debug tool hoặc trace trước khi bị loại khỏi response. Nếu chỉ có query projection mà API serialize cả entity, field khác có thể được thêm vào về sau mà không ai nhận ra. Nếu chỉ có ACL nhưng service account được cấp quyền đọc toàn bộ DIT, ứng dụng vẫn có thể vô tình trả thừa dữ liệu.

**Hãy thiết kế allowlist từ đầu đến cuối**, không dùng blacklist kiểu “lấy tất cả rồi bỏ một vài field nhạy cảm”.

## 3. Chọn attribute bằng LdapQueryBuilder

Spring LDAP cung cấp `LdapQueryBuilder.attributes(...)` để khai báo những thuộc tính cần được trả về trong kết quả search.

```java
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;
import org.springframework.ldap.query.SearchScope;

LdapQuery query = LdapQueryBuilder.query()
        .base("ou=people")
        .searchScope(SearchScope.ONELEVEL)
        .attributes("uid", "cn", "mail")
        .where("objectClass").is("inetOrgPerson")
        .and("uid").is("lan");
```

Giả sử `ContextSource` có base `dc=example,dc=org`:

- `base("ou=people")` giới hạn vùng tìm tương đối với base.
- `searchScope(SearchScope.ONELEVEL)` chỉ tìm entry con trực tiếp.
- `attributes("uid", "cn", "mail")` chỉ yêu cầu ba attribute trong kết quả.
- `objectClass` và `uid` là điều kiện chọn entry trong filter.

**Danh sách attributes và filter là hai phần độc lập.** `objectClass` được dùng trong filter không bắt buộc phải được trả về; nếu mapper không cần nó, đừng thêm vào projection. Ngược lại, attribute được yêu cầu trả về không tự giới hạn entry nào được tìm.

### 3.1. Projection theo use case

Trang danh bạ:

```java
LdapQuery directoryCardQuery = LdapQueryBuilder.query()
        .base("ou=people")
        .searchScope(SearchScope.ONELEVEL)
        .attributes("uid", "cn", "mail")
        .where("objectClass").is("inetOrgPerson");
```

Trang liên hệ nội bộ có quyền cao hơn:

```java
LdapQuery internalContactQuery = LdapQueryBuilder.query()
        .base("ou=people")
        .searchScope(SearchScope.ONELEVEL)
        .attributes("uid", "cn", "mail", "telephoneNumber")
        .where("objectClass").is("inetOrgPerson");
```

Hai use case có **allowlist khác nhau**. Không xây một truy vấn chung lấy mọi attribute rồi để từng controller tự loại trường.

### 3.2. Không nhận danh sách attribute tùy ý từ client

Tránh API kiểu:

```text
GET /api/people/lan?attributes=uid,cn,userPassword,memberOf
```

Nếu client tự quyết định attribute nào được đọc/trả, một lỗi kiểm soát đầu vào có thể biến endpoint hồ sơ thành công cụ dò dữ liệu directory. Kể cả khi đã kiểm tra quyền, client không nên có quyền chọn tên attribute tùy ý.

Thay vào đó, định nghĩa các projection cố định ở server:

```java
public enum PersonView {
    DIRECTORY_CARD,
    INTERNAL_CONTACT
}
```

Service nhận một view đã được authorization kiểm soát rồi ánh xạ sang **một truy vấn allowlist cụ thể**. Nếu use case mới cần thêm attribute, phải thay đổi code, review quyền và test response.

## 4. Chọn attribute bằng JNDI SearchControls

Khi cần điều khiển search ở mức JNDI, có thể dùng `SearchControls.setReturningAttributes(...)`:

```java
import javax.naming.directory.SearchControls;

SearchControls controls = new SearchControls();
controls.setSearchScope(SearchControls.ONELEVEL_SCOPE);
controls.setReturningAttributes(
        new String[] {"uid", "cn", "mail"});
controls.setCountLimit(100);
controls.setTimeLimit(2_000);
```

`returningAttributes` chỉ định những attribute được yêu cầu trả về. `countLimit` là số entry, còn `timeLimit` của JNDI là **millisecond**. Những giới hạn này giúp hạn chế dữ liệu/tải, không thay thế ACL.

Trong JNDI, `null` cho danh sách returning attributes thường có nghĩa yêu cầu tất cả thuộc tính theo mặc định của provider. Vì vậy, không truyền `null` khi mục tiêu là projection hẹp. LDAP có selector đặc biệt `1.1` để không yêu cầu attribute nào khi dùng như selector duy nhất; hãy kiểm tra hành vi provider cụ thể trước khi dùng.

### 4.1. Các selector đặc biệt

| Selector | Ý nghĩa thường gặp | Lưu ý |
| --- | --- | --- |
| `*` | Các user attributes | Có thể trả rất nhiều trường, không dùng cho API danh bạ mặc định |
| `+` | Operational attributes | Có thể nhạy cảm; chỉ yêu cầu khi cần |
| `1.1` | Không yêu cầu attribute nào (khi dùng như selector duy nhất) | Hữu ích khi chỉ cần kiểm tra entry, tùy provider |
| `uid`, `cn`, `mail` | Attribute cụ thể | Lựa chọn rõ ràng, dễ review |

Đừng nhầm `*` trong filter với `*` trong danh sách attribute. Trong filter `(cn=Lan*)`, dấu sao có nghĩa substring/prefix matching; trong danh sách attribute, `*` là selector các user attributes. Cùng ký tự nhưng thuộc hai cú pháp khác nhau.

### 4.2. Projection không hạn chế việc server đánh giá filter

```java
LdapQuery query = LdapQueryBuilder.query()
        .base("ou=groups")
        .attributes("cn")
        .where("member").is(fullUserDn);
```

Server vẫn đánh giá `member` để tìm group, dù client chỉ yêu cầu nhận `cn`. Đây là hành vi bình thường. Tuy nhiên, nếu endpoint cho phép caller tùy ý filter theo `memberOf` hoặc `userPassword`, kết quả tìm thấy/không tìm thấy có thể tiết lộ thông tin gián tiếp. Vì thế cần **allowlist cả filter field và returned attribute**, không chỉ projection.

## 5. Ánh xạ sang DTO bằng AttributesMapper

Một DTO dành cho trang danh bạ:

```java
import java.util.List;

public record PersonSummary(
        String uid,
        String displayName,
        List<String> emails) {
}
```

DTO chỉ có ba trường được duyệt. Dùng `AttributesMapper<PersonSummary>`:

```java
import java.util.ArrayList;
import java.util.List;
import javax.naming.NamingEnumeration;
import javax.naming.NamingException;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;
import org.springframework.ldap.core.AttributesMapper;

public final class PersonSummaryMapper
        implements AttributesMapper<PersonSummary> {

    @Override
    public PersonSummary mapFromAttributes(Attributes attrs)
            throws NamingException {
        String uid = readSingleString(attrs, "uid");
        String cn = readSingleString(attrs, "cn");
        List<String> mail = readStringValues(attrs, "mail");
        return new PersonSummary(uid, cn, mail);
    }

    private static String readSingleString(
            Attributes attrs, String name) throws NamingException {
        Attribute attribute = attrs.get(name);
        if (attribute == null || attribute.size() == 0) {
            return null;
        }
        Object value = attribute.get();
        if (!(value instanceof String text)) {
            throw new IllegalStateException(
                    "Expected text attribute: " + name);
        }
        return text;
    }

    private static List<String> readStringValues(
            Attributes attrs, String name) throws NamingException {
        Attribute attribute = attrs.get(name);
        if (attribute == null) {
            return List.of();
        }
        List<String> result = new ArrayList<>();
        NamingEnumeration<?> values = attribute.getAll();
        try {
            while (values.hasMore()) {
                Object value = values.next();
                if (!(value instanceof String text)) {
                    throw new IllegalStateException(
                            "Expected text attribute: " + name);
                }
                result.add(text);
            }
        } finally {
            values.close();
        }
        return List.copyOf(result);
    }
}
```

Mapper chỉ đọc `uid`, `cn` và `mail`. Nếu directory trả `jpegPhoto`, `memberOf` hoặc attribute khác ngoài projection, chúng không có chỗ trong DTO và không được đưa ra API.

**Lưu ý về dữ liệu đa trị:** `mail` có thể chứa nhiều giá trị. Không nên gọi `attribute.get()` rồi giả định phần tử đầu tiên là email chính. Ví dụ duyệt tất cả giá trị và trả danh sách. Nếu nghiệp vụ cần một email chính, cần quy tắc dữ liệu rõ ràng.

### 5.1. Kết hợp query projection và mapper

```java
import java.util.List;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;
import org.springframework.ldap.query.SearchScope;

public class PersonDirectoryReader {
    private final LdapTemplate ldapTemplate;

    public PersonDirectoryReader(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<PersonSummary> findDirectoryCards(String uid) {
        LdapQuery query = LdapQueryBuilder.query()
                .base("ou=people")
                .searchScope(SearchScope.ONELEVEL)
                .attributes("uid", "cn", "mail")
                .where("objectClass").is("inetOrgPerson")
                .and("uid").is(uid);
        return ldapTemplate.search(query, new PersonSummaryMapper());
    }
}
```

`.is(uid)` dùng cơ chế xây filter và escape giá trị, thay vì ghép chuỗi từ input. Query cũng giới hạn base/scope và attribute selection. Trong ứng dụng thật, cần kiểm tra quyền của người gọi trước khi truy vấn và xử lý kết quả rỗng theo hợp đồng API.

### 5.2. Lookup một entry đã biết DN

```java
import javax.naming.Name;
import org.springframework.ldap.core.LdapTemplate;

public PersonSummary readOne(
        LdapTemplate ldapTemplate, Name relativeDn) {
    return ldapTemplate.lookup(
            relativeDn,
            new String[] {"uid", "cn", "mail"},
            new PersonSummaryMapper());
}
```

Đây là cách đọc một entry theo DN tương đối với base của `ContextSource`. DN phải đến từ nguồn đã được xác minh hoặc được dựng bằng `LdapNameBuilder`; không ghép DN tùy tiện từ input. Quyền truy cập vào entry và thuộc tính vẫn do ACL và policy ứng dụng quyết định.

## 6. Không serialize trực tiếp LDAP entity ra JSON

Một entity ODM có thể chứa nhiều field:

```java
@Entry(
    base = "ou=people",
    objectClasses = {
        "top", "person", "organizationalPerson", "inetOrgPerson"
    })
public class PersonEntry {
    @Id
    private Name dn;

    @Attribute(name = "uid")
    private String uid;

    @Attribute(name = "cn")
    private String fullName;

    @Attribute(name = "mail")
    private Set<String> emails;

    @Attribute(name = "telephoneNumber")
    private String telephoneNumber;

    @Attribute(name = "memberOf")
    private Set<Name> groups;

    @Attribute(name = "jpegPhoto", type = Attribute.Type.BINARY)
    private byte[] photo;

    @Attribute(name = "userCertificate", type = Attribute.Type.BINARY)
    private byte[] certificate;
}
```

Đây là entity minh họa; việc ánh xạ `memberOf` hay `userCertificate` còn phụ thuộc schema/provider và quyền. Nếu controller trả trực tiếp entity, Jackson có thể serialize mọi getter public mà entity cung cấp, bao gồm field chưa được thiết kế cho API.

Không nên:

```java
// RỦI RO: API response phụ thuộc toàn bộ field/getter của LDAP entity.
return ResponseEntity.ok(personRepository.findById(dn).orElseThrow());
```

Nên ánh xạ sang DTO:

```java
public record DirectoryCardResponse(
        String uid,
        String displayName,
        List<String> emails) {
}

DirectoryCardResponse toResponse(PersonSummary summary) {
    return new DirectoryCardResponse(
            summary.uid(),
            summary.displayName(),
            summary.emails());
}
```

Response DTO là **hợp đồng công khai** của API. Thêm field vào LDAP entity không tự động làm API công khai thêm dữ liệu. Khi use case cần trường khác, tạo DTO/endpoint hoặc projection có allowlist riêng và kiểm tra authorization.

### 6.1. Tránh blacklist dựa trên tên field

Một cách yếu là serialize entity rồi xóa `userPassword` và `jpegPhoto` bằng bộ lọc generic. Khi schema thêm `employeeNumber` hoặc `memberOf`, dữ liệu mới có thể bị lộ vì blacklist chưa được cập nhật.

Allowlist DTO có lợi thế:

- Chỉ trường được khai báo mới xuất hiện.
- Code review nhìn thấy rõ hợp đồng response.
- Unit test có thể xác nhận các trường không mong muốn không tồn tại.
- Thêm attribute LDAP mới không tự mở rộng API.

### 6.2. Không dùng Map tùy ý làm response

Tránh đưa toàn bộ `Attributes` vào `Map<String, Object>` rồi trả JSON. Đây là kiểu trả dữ liệu quá rộng và dễ làm lộ trường mới từ schema. Nếu cần response linh hoạt, vẫn phải định nghĩa allowlist attribute phía server và kiểm tra quyền trên từng view; không nhận tên attribute tùy ý từ client.

## 7. LDAP ACL: giới hạn quyền đọc ngay tại directory

Query projection giúp giảm dữ liệu được gửi tới ứng dụng, nhưng **LDAP server mới là nơi thực thi quyền truy cập thực sự**. Tài khoản bind của ứng dụng nên có quyền tối thiểu:

```text
Application service account
   ├── READ uid, cn, mail trong ou=people
   ├── READ telephoneNumber chỉ trong use case được duyệt
   ├── NO READ userPassword
   ├── NO READ private credential attributes
   └── NO WRITE person entries nếu service chỉ cần tra cứu
```

Directory có thể hỗ trợ ACL theo entry, subtree, attribute hoặc value tùy sản phẩm. Cách cấu hình khác nhau giữa OpenLDAP, Active Directory, 389 Directory Server và các sản phẩm LDAP khác; **không có một file ACL chung cho mọi server**.

### 7.1. Service account chỉ đọc

```yaml
app:
  ldap:
    url: ldaps://directory.example.org:636
    base: dc=example,dc=org
    bind-dn: uid=directory-card-reader,ou=services,dc=example,dc=org
    bind-password: ${LDAP_CARD_READER_PASSWORD}
```

Tài khoản `directory-card-reader` được quản trị viên cấp quyền đọc đúng các thuộc tính phục vụ danh bạ. Password lấy từ secret store/environment, không commit vào YAML hoặc source code.

Nếu service khác cần sửa hồ sơ, hãy cân nhắc **tài khoản riêng với quyền ghi đúng nhánh/attribute** thay vì nâng quyền reader dùng chung. Tách credential giúp giảm tác động nếu một endpoint bị khai thác.

### 7.2. ACL theo attribute và hành vi khi không có quyền

Khi account không có quyền đọc một attribute, directory có thể **không trả attribute đó** trong kết quả thay vì ném lỗi cho toàn bộ search. Ví dụ:

```text
Entry thật:
uid=lan
cn=Nguyen Thi Lan
mail=lan@example.org
telephoneNumber=+84...

Service account chỉ có quyền đọc uid và cn:
Kết quả client có thể nhìn thấy:
uid=lan
cn=Nguyen Thi Lan
```

Vì vậy:

- Attribute vắng mặt có thể là **không tồn tại**, **không được trả do ACL**, hoặc **không được yêu cầu trong projection**.
- `null` không chứng minh rằng user không có số điện thoại.
- Không trả lỗi chi tiết kiểu “user có memberOf=payroll-admins nhưng bạn không được đọc” cho caller không có quyền.
- Cần phối hợp kiểm tra ACL với quản trị directory và test bằng **đúng bind account production**, không chỉ bằng admin.

### 7.3. Quyền đọc khác quyền ghi

Một account có thể được đọc `mail` nhưng không được sửa `mail`; có thể được đọc `cn` nhưng không được xem `userCertificate`. Không giả định một ACL “read entry” có nghĩa mọi attribute đều được phép.

| Attribute | Service cần | Quyền tối thiểu |
| --- | --- | --- |
| `uid` | Tìm user | Read trong nhánh được phép |
| `cn` | Hiển thị tên | Read |
| `mail` | Danh bạ | Read nếu chính sách cho phép |
| `telephoneNumber` | Một số màn hình nội bộ | Read giới hạn theo use case/role |
| `memberOf` | Authorization/group lookup | Read cho service chuyên trách; không công khai tùy tiện |
| `userPassword` | Xác thực | Thông thường không cấp quyền đọc; dùng LDAP bind |
| `jpegPhoto` | Endpoint ảnh | Read riêng nếu được phép, giới hạn kích thước |

### 7.4. Mật khẩu LDAP không phải field hồ sơ

**Không đọc hoặc trả `userPassword` qua API danh bạ.** Trong nhiều directory, password được lưu dạng hash hoặc có cơ chế xử lý đặc biệt; quyền đọc attribute này có thể cho phép offline password guessing nếu hash bị lộ.

Để xác thực người dùng, dùng cơ chế bind phù hợp như Spring Security LDAP/LDAP bind thay vì lấy mật khẩu ra để so sánh trong Java. Với Active Directory, `unicodePwd` là thuộc tính đặc biệt có quy tắc ghi/đọc và bảo vệ riêng; không coi nó như field văn bản thông thường.

## 8. Authorization theo người gọi và theo entry

Ngay cả khi LDAP service account được giới hạn, API vẫn phải kiểm tra **ai được đọc hồ sơ nào**. Quyền xem danh bạ toàn công ty khác quyền xem hồ sơ của chính mình hoặc quyền xem số điện thoại nội bộ.

Ví dụ với Spring Security method security:

```java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class PersonDirectoryService {

    @PreAuthorize("@directoryAccess.canReadPerson(authentication, #uid)")
    public PersonSummary findPerson(String uid) {
        // Thực hiện query allowlist uid/cn/mail sau khi authorize.
        return readSummaryFromLdap(uid);
    }
}
```

Đoạn code giả định ứng dụng đã bật method security, ví dụ `@EnableMethodSecurity`, và bean `directoryAccess` triển khai kiểm tra quyền phù hợp. Không chỉ kiểm tra role chung `hasRole("USER")` rồi cho mọi người đọc mọi DN.

### 8.1. Chống IDOR/BOLA

Một endpoint:

```text
GET /api/people/{uid}
```

có thể bị khai thác nếu người gọi chỉ cần thay `uid` từ chính mình sang người khác. Cần kiểm tra:

- Người gọi có quyền đọc **đối tượng đích** không?
- Có quyền xem toàn bộ email/phone hay chỉ trường công khai?
- DN có thuộc tenant/OU mà principal được phép truy cập không?
- UID có duy nhất trong đúng naming context không?
- Kết quả rỗng do không tồn tại hay do không được phép có bị lộ khác nhau không?

Đối với multi-tenant LDAP, không cho client gửi `base DN` hoặc chọn directory tùy ý. Nguồn và nhánh phải được quyết định từ tenant đã xác thực, allowlist server-side và chính sách truy cập.

### 8.2. Tách view theo quyền

| View | Người gọi | Attribute trả về |
| --- | --- | --- |
| `DirectoryCard` | Người dùng có quyền tra cứu danh bạ | `uid`, `cn`, `mail` |
| `InternalContact` | Nhân viên có quyền xem liên hệ nội bộ | `uid`, `cn`, `mail`, `telephoneNumber` |
| `AdminProfile` | Quản trị nhân sự được phê duyệt | Tập thuộc tính cụ thể đã duyệt |
| `AuthenticationData` | Thành phần xác thực chuyên trách | Không trả password/hash ra API hồ sơ |

Đừng tạo một view `FULL` mặc định. Nếu có view quản trị, hãy liệt kê từng attribute và mục đích; không dùng selector `*` chỉ vì người gọi có role admin.

## 9. Repository và ODM: không phải cơ chế bảo vệ API

Một entity ODM có thể khai báo:

```java
@Attribute(name = "telephoneNumber")
private String telephoneNumber;

@Attribute(name = "userCertificate", type = Attribute.Type.BINARY)
private byte[] certificate;

@Attribute(name = "modifyTimestamp", readonly = true)
private String modifiedAt;
```

Những annotation này phục vụ **mapping**:

- `@Attribute(name=...)` liên hệ field với LDAP attribute.
- `type=BINARY` chọn biểu diễn binary ở ODM.
- `readonly=true` nói rằng ODM không persist field đó khi ghi entity.
- `@Transient` loại field ứng dụng khỏi mapping.

**Không annotation nào trong số này là ACL hoặc authorization rule.** Nếu entity đã đọc được `telephoneNumber`, controller vẫn có thể trả field đó dù người gọi không được phép.

### 9.1. Repository thường trả entity theo mapping

```java
public interface PersonRepository
        extends LdapRepository<PersonEntry> {
    Optional<PersonEntry> findByUid(String uid);
}
```

Repository thuận tiện cho CRUD entity. Tuy nhiên, khi API chỉ cần một số attribute, không nên giả định một derived query method tự tạo projection tối thiểu theo hợp đồng bảo mật của API. Entity ODM có thể ánh xạ nhiều field; hãy kiểm tra hành vi cụ thể của phiên bản đang dùng.

Với endpoint cần projection rõ ràng, **dùng `LdapTemplate.search(query, AttributesMapper)` hoặc `lookup(dn, returningAttributes, mapper)`** là cách dễ kiểm soát hơn. Nếu vẫn dùng repository, ánh xạ kết quả sang DTO allowlist trước khi trả response.

### 9.2. Không update một entity được đọc bằng projection hẹp

Một DTO chỉ có `uid` và `cn` không chứa toàn bộ thuộc tính của entry. Nếu biến projection đó thành entity thiếu field rồi gọi `ldapTemplate.update(entity)` hoặc `repository.save(entity)`, tùy mapping và update semantics, bạn có thể vô tình xóa/ghi đè các attribute không có trong object.

**Không round-trip một projection đọc chỉ thành entity để cập nhật.** Đối với write, tải/kiểm soát dữ liệu cần thiết hoặc dùng thao tác `modifyAttributes` cụ thể (ADD/REMOVE/REPLACE) cho đúng attribute. Tách DTO đọc và command model ghi giúp tránh ghi đè dữ liệu không được trả về.

### 9.3. readonly không đồng nghĩa “không thể đọc”

`@Attribute(readonly = true)` thường có nghĩa **được ánh xạ khi đọc nhưng không persist khi ODM ghi**. Nó không ẩn field khỏi getter/JSON. Nếu field nhạy cảm, phải loại khỏi DTO hoặc không đọc bằng service account/use case đó.

Tương tự, `@Transient` chỉ bỏ qua mapping ODM; không chặn một truy vấn JNDI thủ công lấy cùng attribute.

## 10. Binary attributes và dữ liệu kích thước lớn

Những attribute như `jpegPhoto`, `thumbnailPhoto` hoặc `userCertificate;binary` có thể chứa dữ liệu lớn hoặc nhạy cảm. Nếu trang danh bạ chỉ cần tên, không yêu cầu những bytes này.

### 10.1. Không tải binary nếu không cần

Query danh bạ:

```java
.attributes("uid", "cn", "mail")
```

Query riêng cho ảnh (sau khi authorization):

```java
.attributes("jpegPhoto")
```

Không dùng `attributes("*")` hoặc `attributes(null)` cho mọi endpoint. Nếu cần trả ảnh, kiểm tra authorization, kích thước tối đa, định dạng thật và response content type. Base64 chỉ mã hóa cách biểu diễn bytes thành text, không phải cơ chế bảo mật.

### 10.2. Chứng chỉ và thông tin xác thực

Chứng chỉ X.509 có thể được lưu trong attribute binary. Một API quản lý chứng chỉ chuyên biệt có thể cần trả bytes cho principal được phép, nhưng API danh bạ thông thường không nên có field `certificate`.

Tuyệt đối không trả:

- `userPassword` hoặc hash password.
- Private key/secret key nếu directory/schema có lưu.
- Binary credential hoặc token chỉ vì mapper có thể đọc được.

### 10.3. Hạn mức và chống lạm dụng

Projection hẹp vẫn cần:

- `countLimit` và `timeLimit` phù hợp.
- Giới hạn kích thước từng blob ở directory/API.
- Rate limit cho endpoint tìm kiếm và ảnh.
- Search base/scope chọn lọc, filter parameterized.
- Cache có TTL và invalidation phù hợp nếu dữ liệu nhạy cảm được cache.
- Không tạo metric label từ DN, email hoặc UID tùy ý.

## 11. Operational attributes và selector `+`

LDAP có các operational attributes như `createTimestamp`, `modifyTimestamp`, `creatorsName` và `modifiersName`. Chúng không phải lúc nào cũng được trả về khi search chỉ yêu cầu user attributes.

Selector `+` có thể yêu cầu operational attributes trong những directory/provider hỗ trợ:

```text
attributes: uid, cn, mail
       -> user attributes được chọn

attributes: +
       -> operational attributes

attributes: *, +
       -> user và operational attributes
```

Không thêm `+` vào truy vấn chung để “lấy cho đủ”. Operational metadata có thể tiết lộ danh tính service account, thời điểm cập nhật hoặc thông tin quản trị. Nếu API audit cần `modifyTimestamp`, hãy yêu cầu riêng field đó (nếu server hỗ trợ) và chỉ trả cho principal được phép.

## 12. Filter cũng có thể làm lộ dữ liệu

Giới hạn returned attributes không ngăn ứng dụng dùng attribute nhạy cảm trong filter:

```java
// Chỉ trả uid/cn nhưng filter dựa trên memberOf.
LdapQuery query = LdapQueryBuilder.query()
        .base("ou=people")
        .attributes("uid", "cn")
        .where("memberOf").is(
            "cn=payroll-admins,ou=groups,dc=example,dc=org");
```

Caller có thể không nhìn thấy `memberOf`, nhưng nếu API cho phép thay filter hoặc quan sát người nào xuất hiện, họ có thể suy luận ai thuộc nhóm payroll. Đây là **side channel qua kết quả tìm kiếm**.

Vì vậy:

- Allowlist attribute được dùng trong filter.
- Không expose raw LDAP filter cho client.
- Không để client chọn tùy ý base DN/scope.
- Phân quyền theo kết quả và đối tượng, không chỉ theo endpoint.
- Giới hạn thông báo lỗi và khác biệt response nếu chúng tiết lộ trạng thái nhạy cảm.

Luôn dùng builder hoặc filter escaping theo RFC 4515; không nối input trực tiếp vào filter. Escape filter không thay thế authorization.

## 13. Cache, log, tracing và lỗi

### 13.1. Cache cũng là một nơi lưu dữ liệu nhạy cảm

Nếu cache `PersonEntry` đầy đủ, dù API trả DTO hẹp, heap/cache vẫn giữ field nhạy cảm. Hãy cache **DTO theo view** nếu phù hợp, hoặc cache từng tập dữ liệu theo quyền/tenant. Cache key phải bao gồm ngữ cảnh cần thiết để không dùng nhầm dữ liệu giữa tenant hoặc principal.

Xác định:

- TTL theo độ nhạy và yêu cầu freshness.
- Invalidation khi nhân viên đổi phòng ban, email hoặc quyền.
- Cách xử lý logout/thu hồi quyền.
- Quyền truy cập cache store và encryption at rest nếu cần.
- Không dùng cache dùng chung để trả response có field khác nhau cho hai role.

### 13.2. Log và trace không được sao chép nguyên LDAP entry

Không log:

- Toàn bộ `Attributes.toString()` hoặc entity `toString()`.
- Raw filter có chứa email, UID, DN hoặc membership.
- `userPassword`, hash, certificate, ảnh hoặc Base64.
- Response JSON đầy đủ nếu response có PII/field nhạy cảm.

Nên log các trường có kiểm soát:

| Trường log | Ví dụ |
| --- | --- |
| Operation | `ldap.search.person-summary` |
| Directory alias | `staff-directory` |
| Projection name | `directory-card` |
| Result | `success/not-found/denied/timeout` |
| Attribute count | `3` |
| Duration | `25 ms` |
| Correlation ID | ID do hệ thống quản lý |

Không đưa UID/DN/email làm metric label vì cardinality cao và có thể là dữ liệu cá nhân. Tracing tag chỉ nên mô tả loại operation, logical directory và trạng thái tổng quát.

### 13.3. Phân biệt không tồn tại và không được phép đọc

LDAP server có thể ẩn attribute do ACL mà không báo lỗi toàn search. API không nên trả thông báo phân biệt quá chi tiết cho caller không có quyền.

Ở service nội bộ, cần telemetry đủ để quản trị viên biết:

- Search hoàn tất nhưng entry không có attribute.
- Attribute có thể bị ACL che giấu.
- Query projection không yêu cầu attribute đó.
- Schema hoặc converter có vấn đề.

Không suy luận “không có số điện thoại” chỉ vì `telephoneNumber == null`; phải xem hợp đồng và quyền đọc.

## 14. Ví dụ API với DTO allowlist và authorization

Ví dụ service:

```java
import java.util.Optional;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class DirectoryCardService {
    private final PersonDirectoryReader reader;

    public DirectoryCardService(PersonDirectoryReader reader) {
        this.reader = reader;
    }

    @PreAuthorize("@directoryAccess.canReadPerson(authentication, #uid)")
    public Optional<PersonSummary> getCard(String uid) {
        return reader.findDirectoryCards(uid).stream().findFirst();
    }
}
```

Trong ví dụ, `PersonDirectoryReader` thực hiện projection hẹp ở mục 5.1; bean `directoryAccess` kiểm tra quyền trên **đối tượng cụ thể**. Nếu `uid` không duy nhất trong base, service phải xử lý nhiều kết quả theo quy tắc rõ ràng, không tùy tiện lấy phần tử đầu.

Controller:

```java
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DirectoryCardController {
    private final DirectoryCardService service;

    public DirectoryCardController(DirectoryCardService service) {
        this.service = service;
    }

    @GetMapping("/api/directory/people/{uid}")
    public ResponseEntity<PersonSummary> getCard(
            @PathVariable String uid) {
        return ResponseEntity.of(service.getCard(uid));
    }
}
```

Response chỉ có `uid`, `displayName`, `emails`; không thể tự xuất hiện `telephoneNumber`, `memberOf`, `jpegPhoto` hay `userPassword` nếu DTO không có những trường đó.

**Lưu ý:** Controller/service phải được cấu hình method security trong ứng dụng (ví dụ `@EnableMethodSecurity`). Không coi annotation trong code mẫu là bằng chứng toàn hệ thống đã bật authorization.

## 15. Kiểm thử bảo mật thuộc tính

Kiểm thử phải xác minh cả **truy vấn**, **quyền LDAP** và **response API**. Một unit test mapper không chứng minh ACL production đã đúng.

### 15.1. Unit test DTO không có trường nhạy cảm

```java
import java.util.List;

PersonSummary summary = new PersonSummary(
        "lan",
        "Nguyen Thi Lan",
        List.of("lan@example.org"));

if (!"lan".equals(summary.uid())) {
    throw new AssertionError("Unexpected UID");
}
if (summary.getClass().getRecordComponents().length != 3) {
    throw new AssertionError("Directory card has unexpected fields");
}
```

Test này xác nhận DTO có ba record components. Trong dự án thực, có thể kiểm tra JSON serialize để bảo đảm đúng ba thuộc tính công khai.

### 15.2. Test projection với LDAP test server

Seed một entry có cả attribute được phép và nhạy cảm:

```ldif
dn: uid=lan,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: lan
cn: Nguyen Thi Lan
sn: Nguyen
mail: lan@example.org
telephoneNumber: +84 28 5555 0101
description: Internal note for test only
```

Với query `attributes("uid", "cn", "mail")`:

1. Mapper nhận được các attribute cần thiết.
2. Response DTO có đúng các trường được duyệt.
3. `telephoneNumber` và `description` không xuất hiện trong JSON.
4. Query không yêu cầu `jpegPhoto`, `memberOf` hoặc `userCertificate`.
5. Filter dùng UID literal; input có `*`, ngoặc và dấu gạch chéo ngược không biến thành filter mới.

Nếu muốn xác minh request attributes thật sự được gửi, dùng test LDAP server/protocol instrumentation hoặc wrapper có thể ghi nhận SearchControls; đừng chỉ assert DTO vì DTO có thể bỏ field sau khi đã tải toàn bộ entry.

### 15.3. Test ACL bằng đúng service account

Tạo hai principal trong directory test:

- `directory-card-reader`: được đọc `uid`, `cn`, `mail`.
- `directory-admin-test`: có quyền quản trị dữ liệu test.

Kiểm tra:

| Test | Kỳ vọng |
| --- | --- |
| Reader search `uid`, `cn`, `mail` | Thành công |
| Reader yêu cầu `telephoneNumber` bị ACL cấm | Attribute có thể bị ẩn hoặc access bị từ chối tùy server |
| Reader yêu cầu `userPassword` | Không được đọc/không xuất hiện |
| Admin test đọc thuộc tính test được phép | Kết quả phù hợp ACL |
| API danh bạ chạy với reader | Chỉ trả DTO allowlist |
| API chi tiết không có quyền | Bị từ chối dù service account có thể đọc LDAP |

**Chạy integration test với principal giống production** (quyền tối thiểu tương ứng), không dùng admin account rồi kết luận service account cũng an toàn.

### 15.4. Test API response

Với endpoint:

```text
GET /api/directory/people/lan
```

Assert:

- Status code và dữ liệu khi caller có quyền.
- Caller không có quyền nhận 403 hoặc response được chính sách định nghĩa; không lộ raw DN/filter.
- JSON có `uid`, `displayName`, `emails`.
- JSON **không có** `userPassword`, `telephoneNumber`, `memberOf`, `jpegPhoto`, `certificate`, `description` nếu view không được phép.
- Không có dữ liệu của tenant/directory khác khi UID trùng.
- Log/trace không chứa password, raw LDAP entry, raw filter hay email không được phép.
- Khi attribute bị ACL che giấu, API không tự suy ra hoặc tiết lộ lý do chi tiết cho người gọi.

### 15.5. Test regression khi entity mở rộng

Khi developer thêm field mới vào `PersonEntry`, test response phải vẫn chỉ có allowlist DTO. Đây là regression test quan trọng: **thêm attribute vào LDAP entity không được làm thay đổi API contract**.

## 16. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| API trả cả `telephoneNumber` dù UI không cần | Serialize trực tiếp ODM entity | Dùng DTO allowlist |
| Search lấy nhiều dữ liệu nhưng response chỉ có ba field | Chỉ lọc ở controller | Thêm `.attributes("uid", "cn", "mail")` |
| Attribute thiếu bị hiểu là không tồn tại | ACL hoặc projection đã ẩn attribute | Phân biệt absent/not requested/not readable theo ngữ cảnh |
| Query dùng `memberOf` làm filter tùy ý | Có thể suy luận membership nhạy cảm | Allowlist filter và authorization |
| Endpoint nhận `attributes=...` từ client | Client điều khiển projection | Chọn view server-side |
| `userPassword` xuất hiện trong log | Log toàn bộ entity/Attributes | Redaction, không log raw object |
| `jpegPhoto` làm heap tăng | Tải binary ở truy vấn danh sách | Projection hẹp, endpoint ảnh riêng, giới hạn kích thước |
| Operational metadata bị trả ra | Dùng selector `+` hoặc lấy tất cả | Chỉ yêu cầu operational attribute đã duyệt |
| `@Attribute(readonly=true)` bị coi là ẩn field | Nhầm mapping với authorization | Dùng DTO/ACL, không serialize entity |
| `@Transient` được coi là cấm truy cập | Chỉ bỏ qua ODM mapping | Kiểm soát mọi query và ACL |
| Repository trả entity nhiều field | ODM mapping theo entity | Dùng LdapTemplate projection cho use case API |
| Projection DTO được đưa vào update | Thiếu attribute bị ghi/xóa ngoài ý muốn | Tách read DTO và write command; dùng modify cụ thể |
| Null bị coi là “không có dữ liệu” | ACL có thể che giấu attribute | Không suy luận quá mức; kiểm tra bằng principal test |
| Reader account đọc được mọi thứ | ACL cấp quyền rộng | Tạo service account least privilege |
| UID trùng giữa tenant | Search base/nguồn không cố định | Chọn directory/base theo tenant đã xác thực |
| Metric cardinality tăng | Dùng DN/UID/email làm label | Chỉ dùng tag hữu hạn như operation, source, result |

## 17. Checklist thiết kế trước khi mở endpoint

Trước khi công bố một API đọc LDAP, hãy trả lời:

1. **Mục đích:** use case cần chính xác những attribute nào?
2. **Nguồn:** directory, base DN và tenant nào được phép truy vấn?
3. **Filter:** attribute nào được dùng làm điều kiện tìm kiếm? Có lộ membership/trạng thái nhạy cảm không?
4. **ACL:** service account được phép đọc đúng các trường cần thiết chưa?
5. **Authorization:** caller được xem đối tượng và trường dữ liệu nào?
6. **Projection:** query có khai báo allowlist attribute không?
7. **DTO:** response có chỉ các field đã duyệt, không serialize entity trực tiếp không?
8. **Binary:** ảnh/chứng chỉ có cần thiết không, có endpoint riêng và hạn mức không?
9. **Operational:** có vô tình yêu cầu `+`/toàn bộ attribute không?
10. **Null/ACL:** xử lý ra sao khi attribute không có hoặc bị che giấu?
11. **Logging/cache:** dữ liệu nhạy cảm có đi vào log, trace, metric, cache không?
12. **Testing:** integration test có dùng đúng service account và xác minh JSON không?

## 18. Bài tập tự luyện

**Câu 1.** Trang danh bạ chỉ cần `uid`, `cn`, `mail`. Vì sao nên dùng `.attributes("uid", "cn", "mail")` thay vì lấy entity đầy đủ rồi xóa field trước khi trả API?

*Gợi ý:* Projection giảm dữ liệu được yêu cầu/truyền về; DTO ngăn dữ liệu thừa xuất hiện trong response. Lọc sau khi tải không bảo vệ heap, trace hoặc mapper.

**Câu 2.** Query dùng `memberOf` trong filter nhưng không yêu cầu trả `memberOf`. Caller có thể suy luận membership không?

*Gợi ý:* Có thể qua kết quả entry xuất hiện/không xuất hiện. Cần allowlist filter và authorization, không chỉ allowlist returned attributes.

**Câu 3.** Directory account không có quyền đọc `telephoneNumber`, mapper nhận `null`. Có thể kết luận user không có số điện thoại không?

*Gợi ý:* Không. Attribute có thể bị ACL che giấu hoặc không được yêu cầu. Cần phân biệt trạng thái theo hợp đồng và principal.

**Câu 4.** `@Attribute(readonly = true)` có ngăn Jackson serialize field không?

*Gợi ý:* Không. Đây là mapping option của ODM; hãy dùng DTO response allowlist.

**Câu 5.** Tại sao không trả `PersonEntry` từ repository trực tiếp?

*Gợi ý:* Entity có thể chứa field LDAP nội bộ, binary và attribute mới được thêm về sau. DTO giữ hợp đồng API ổn định.

**Câu 6.** Khi nào nên yêu cầu selector `+`?

*Gợi ý:* Chỉ khi use case cần operational attributes cụ thể và caller được phép; không dùng như mặc định cho danh bạ.

**Câu 7.** Có nên cho client gửi `attributes=uid,cn,userPassword` để tự chọn response không?

*Gợi ý:* Không. Server chọn projection theo view/role đã được duyệt; client không điều khiển attribute tùy ý.

**Câu 8.** Service account có quyền đọc toàn bộ directory. DTO đã đủ để bảo vệ dữ liệu chưa?

*Gợi ý:* Chưa. Query projection, ACL least privilege và DTO cần phối hợp. Một lỗi ở code có thể làm lộ mọi dữ liệu mà account đọc được.

**Câu 9.** Một projection DTO chỉ có `uid` và `cn` có nên được chuyển ngược thành entity rồi gọi `repository.save(...)` không?

*Gợi ý:* Không nên. Field thiếu có thể bị xử lý như giá trị rỗng/xóa tùy update semantics. Dùng command model và modify cụ thể.

**Câu 10.** Vì sao test mapper bằng admin account chưa đủ?

*Gợi ý:* Admin có thể đọc mọi attribute; cần test bằng đúng service account/ACL mà ứng dụng dùng ở production.

## 19. Ghi nhớ

- **Chỉ đọc đúng dữ liệu cần thiết:** dùng `LdapQueryBuilder.attributes(...)` hoặc `SearchControls.setReturningAttributes(...)`.
- **Filter và returned attributes là hai phần khác nhau:** không trả `memberOf` vẫn có thể làm lộ membership qua kết quả filter.
- **ACL phía LDAP là lớp bảo vệ dữ liệu thực sự:** service account chỉ nên đọc những attribute và subtree cần cho chức năng.
- **API dùng DTO allowlist:** không serialize trực tiếp entity ODM, `Attributes` hay `DirContextOperations`.
- **`userPassword` không phải dữ liệu hồ sơ:** xác thực bằng bind phù hợp; không đọc hoặc trả password/hash.
- **`@Attribute(readonly=true)` không ẩn field**, `@Transient` không phải ACL; cả hai chỉ điều khiển mapping ODM.
- **Projection không phải entity đầy đủ để ghi lại:** tránh round-trip DTO hẹp thành update entity.
- **Binary và operational attributes cần use case riêng:** không dùng `*`/`+` hoặc tải ảnh/chứng chỉ cho truy vấn danh bạ.
- **Kiểm thử bằng principal production tương đương:** xác minh projection, ACL, authorization, JSON, log, trace và cache.

**Tài liệu tham khảo chính thức:**

- [Spring LDAP — Advanced LDAP Queries](https://docs.spring.io/spring-ldap/reference/query-builder-advanced.html): chọn base, scope, attributes, count/time limit và filter.
- [Spring LDAP API — LdapQueryBuilder](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/query/LdapQueryBuilder.html): fluent query builder và attribute selection.
- [Spring LDAP API — LdapTemplate](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/core/LdapTemplate.html): search/lookup với returning attributes và mapper.
- [Spring LDAP API — AttributesMapper](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/core/AttributesMapper.html): ánh xạ JNDI attributes thành DTO.
- [Spring LDAP — Object-Directory Mapping](https://docs.spring.io/spring-ldap/reference/odm.html): `@Entry`, `@Id`, `@Attribute`, `@Transient` và entity mapping.
- [Spring Data LDAP Reference](https://docs.spring.io/spring-data/ldap/reference/): repository, query methods và giới hạn abstraction.
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): authorization ở service method.
- [Oracle JNDI — Search Operations](https://docs.oracle.com/javase/tutorial/jndi/ops/search.html): `SearchControls`, scope và returning attributes.
- [Java API — SearchControls](https://docs.oracle.com/en/java/javase/21/docs/api/java.naming/javax/naming/directory/SearchControls.html): `setReturningAttributes`, count limit và time limit.
- [RFC 4511 — LDAP: The Protocol](https://www.rfc-editor.org/rfc/rfc4511): SearchRequest và danh sách attributes được yêu cầu.
- [RFC 4512 — LDAP Directory Information Models](https://www.rfc-editor.org/rfc/rfc4512): attribute types, operational attributes và schema.
- [RFC 4515 — LDAP Search Filter Representation](https://www.rfc-editor.org/rfc/rfc4515): cú pháp filter và escaping.
