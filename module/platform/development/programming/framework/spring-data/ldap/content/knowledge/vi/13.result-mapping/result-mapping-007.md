# Giữ DN của entry trong kết quả ánh xạ

Trong **SPRING_DATA_LDAP**, ứng dụng Java truy cập dịch vụ thư mục LDAP bằng Spring Data LDAP repository hoặc `LdapTemplate`. Directory tổ chức entry thành cây phân cấp, mỗi entry được nhận diện bằng **DN** (*Distinguished Name*), gắn với `objectClass`, schema và nhiều thuộc tính. Khi tìm kiếm, lập trình viên thường ánh xạ `uid`, `cn`, `mail` thành DTO. Tuy nhiên, nếu DTO không giữ DN, ứng dụng có thể **đọc đúng người nhưng không biết chính xác entry nào cần thao tác tiếp**.

Ví dụ màn hình danh bạ tìm `uid=lan`. Một người dùng có thể nằm tại `uid=lan,ou=employees,dc=example,dc=org`, người khác nằm tại `uid=lan,ou=partners,dc=example,dc=org`. Hai kết quả có cùng `uid` nhưng **khác DN**. Nếu chỉ trả tên đăng nhập rồi tự dựng lại DN theo một container cố định, thao tác xem chi tiết, đổi email hoặc thêm thành viên nhóm có thể nhắm nhầm entry.

Bài học thuộc chương **Ánh xạ kết quả**, tập trung vào cách **giữ DN của chính entry đã tìm thấy** trong kết quả Spring LDAP, phân biệt DN tương đối/đầy đủ, sử dụng `ContextMapper`, `DirContextOperations` và `@Id` của ODM, đồng thời kiểm thử việc không làm mất thông tin định danh khi chỉ lấy một số thuộc tính.

Sau bài này, bạn sẽ:

- Giải thích vì sao DN khác `uid`, `cn` và khác tên của một thuộc tính thông thường.
- Biết khi nào `AttributesMapper` không đủ và cần `ContextMapper`.
- Lấy `ctx.getDn()` và `ctx.getNameInNamespace()` theo đúng ngữ cảnh `ContextSource.base`.
- Thiết kế DTO có cả dữ liệu hiển thị lẫn định danh của entry; không nhầm DN tương đối với DN đầy đủ.
- Dùng DN thu được cho `lookup`, `modifyAttributes`, `rename` và `groupOfNames.member` khi phù hợp.
- Hiểu giới hạn khi entry đổi DN, nhiều directory/replica, referral, ACL và dữ liệu nhạy cảm.
- Viết unit test/integration test kiểm chứng ánh xạ DN và phòng lỗi nhầm đích.

## 1. Kết quả tìm kiếm LDAP có gì ngoài Attributes?

Một entry mẫu:

```ldif
dn: uid=lan,ou=employees,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: lan
cn: Lan Nguyen
sn: Nguyen
mail: lan@example.org
```

DN của entry là:

```text
uid=lan,ou=employees,dc=example,dc=org
```

Ở dạng chuỗi theo RFC 4514, DN gồm các **RDN** (*Relative Distinguished Name*) ngăn cách bằng dấu phẩy; RDN cụ thể nhất đứng bên trái. Nó biểu diễn **vị trí/tên của entry trong LDAP namespace**, còn các thuộc tính như `uid` hay `cn` là dữ liệu của entry.

Một truy vấn có thể có ba phần độc lập:

```text
ContextSource.base = dc=example,dc=org
Search base        = ou=employees
Search filter      = (&(objectClass=inetOrgPerson)(uid=lan))
Returning attrs    = uid,cn,mail

Server tìm entry theo base/scope/filter
               |
               v
SearchResultEntry:
  objectName = uid=lan,ou=employees,dc=example,dc=org
  attributes = {uid=lan, cn=Lan Nguyen, mail=lan@example.org}
               |
               v
Mapper -> DTO có dữ liệu + DN của entry
```

Theo giao thức LDAP, **tên entry và tập thuộc tính là hai phần riêng** của `SearchResultEntry`. Một client chỉ yêu cầu ba thuộc tính `uid`, `cn`, `mail` vẫn có thể nhận **tên entry** trong metadata kết quả. Không cần thêm `dn` vào danh sách returning attributes để lấy tên đó. Tham khảo RFC 4511 và API Spring LDAP ở cuối bài.

### 1.1. Vì sao không dựng DN từ thuộc tính hiển thị?

Hai entry hoàn toàn có thể có:

```ldif
dn: uid=lan,ou=employees,dc=example,dc=org
uid: lan
cn: Lan Nguyen

dn: cn=Lan Nguyen,ou=contractors,dc=example,dc=org
uid: lan
cn: Lan Nguyen
```

Đây là các **đoạn LDIF minh họa**, không phải file import hoàn chỉnh vì thiếu `objectClass`/các thuộc tính bắt buộc. Chúng cho thấy:

| Thuộc tính/định danh | Entry nhân viên | Entry cộng tác viên |
|---|---|---|
| `uid` | `lan` | `lan` |
| `cn` | `Lan Nguyen` | `Lan Nguyen` |
| RDN | `uid=lan` | `cn=Lan Nguyen` |
| Parent DN | `ou=employees,dc=example,dc=org` | `ou=contractors,dc=example,dc=org` |
| DN đầy đủ | `uid=lan,ou=employees,dc=example,dc=org` | `cn=Lan Nguyen,ou=contractors,dc=example,dc=org` |

Nếu chương trình dùng công thức `"uid=" + uid + ",ou=employees,..."` để khôi phục DN của mọi kết quả, entry thứ hai bị ánh xạ sai. Ngay cả khi một tổ chức có quy tắc RDN cố định, **DN trả về từ kết quả thực** vẫn là nguồn thích hợp hơn cho luồng tra cứu đã xảy ra.

## 2. So sánh AttributesMapper và ContextMapper

Spring LDAP có hai giao diện thường dùng để chuyển LDAP search result thành Java object:

| Tiêu chí | `AttributesMapper<T>` | `ContextMapper<T>` |
|---|---|---|
| Mapper nhận | `javax.naming.directory.Attributes` | Một object context, thường là `DirContextAdapter` |
| Đọc `cn`, `mail` | `attrs.get("cn")`, `attrs.get("mail")` | `ctx.getStringAttribute("cn")`, `ctx.getStringAttribute("mail")` |
| Lấy DN từ metadata kết quả | **Không trực tiếp** | **Có**, qua `DirContextOperations` |
| Có thể giữ tên tương đối | Không có sẵn trong `Attributes` | `ctx.getDn()` |
| Có thể lấy tên trong LDAP namespace | Không từ `Attributes` thuần | `ctx.getNameInNamespace()` |
| Phù hợp | DTO chỉ cần thuộc tính | DTO cần thuộc tính **và DN**, hoặc xử lý `DirContextAdapter` |

Ví dụ chỉ lấy dữ liệu:

```java
AttributesMapper<PersonCard> mapper = attrs ->
        new PersonCard(
                (String) attrs.get("uid").get(),
                (String) attrs.get("cn").get());
```

Nếu `PersonCard` chỉ có `uid` và `cn`, sau khi mapper trả về sẽ không còn **DN của entry trong kết quả**. `AttributesMapper` không thể suy ra DN chính xác khi tên thực không nhất thiết được đặt theo `uid`. Đặc biệt, `attrs.get("dn")` thường trả `null` vì **`dn` không phải thuộc tính chuẩn luôn nằm trong `Attributes`**.

Một số server có thuộc tính như `distinguishedName` (ví dụ môi trường Active Directory) nhưng đó là hành vi theo backend/schema, **không phải thay thế có tính di động** cho metadata DN của search result.

**Quy tắc chọn:** nếu DTO được dùng để mở trang chi tiết, tạo liên kết nhóm, sửa/xóa/đổi tên một entry cụ thể hoặc kiểm tra identity trên nhiều OU, hãy cân nhắc `ContextMapper` ngay từ đầu.

## 3. Lấy DN đúng cách qua DirContextOperations

Khi `ContextSource` dùng `DefaultDirObjectFactory` mặc định, Spring LDAP tạo `DirContextAdapter` cho các entry tìm được. `ContextMapper<T>` nhận object đó; có thể ép sang `DirContextOperations` để truy cập cả thuộc tính lẫn tên.

Ví dụ ngắn:

```java
import org.springframework.ldap.core.ContextMapper;
import org.springframework.ldap.core.DirContextOperations;

ContextMapper<String> dnMapper = source -> {
    DirContextOperations ctx = (DirContextOperations) source;
    return ctx.getDn().toString();
};
```

Ở đây `ctx.getDn()` trả một `javax.naming.Name`, thông thường là `LdapName`. **Theo Javadoc Spring LDAP hiện hành, nó là DN tương đối với base path của `ContextSource`**, không phải mặc nhiên là DN đầy đủ toàn directory.

### 3.1. DN tương đối và DN đầy đủ

Với cấu hình:

```yaml
spring:
  ldap:
    urls: ldaps://ldap.example.org:636
    base: dc=example,dc=org
    username: cn=reader,ou=service,dc=example,dc=org
    password: ${LDAP_BIND_PASSWORD}
```

và entry `uid=lan,ou=employees,dc=example,dc=org`:

| API | Ví dụ kết quả | Mục đích |
|---|---|---|
| `ctx.getDn()` | `uid=lan,ou=employees` | Tên **tương đối với `dc=example,dc=org`**; dùng trong nhiều lời gọi `LdapTemplate` |
| `ctx.getNameInNamespace()` | `uid=lan,ou=employees,dc=example,dc=org` | Tên entry trong LDAP namespace; thường là **DN đầy đủ** |
| `ctx.getStringAttribute("uid")` | `lan` | Giá trị thuộc tính login, **không phải** DN |
| Search base của query | `ou=employees` | Vùng tìm kiếm, **không nhất thiết** trùng DN của entry |

Khác biệt đặc biệt quan trọng: **DN tương đối của `DirContextAdapter` là tương đối với base do context source quản lý**, không đơn giản là “phần còn lại sau search base”. Nếu query dùng `.base("ou=employees")` và context base là `dc=example,dc=org`, kết quả có thể là `uid=lan,ou=employees`, chứ không phải chỉ `uid=lan`.

Khi cần DN đầy đủ, `getNameInNamespace()` là API nên xét trước. Kết quả phải được kiểm chứng trên backend/provider và topology thực tế, đặc biệt nếu có **referral, alias hoặc nhiều naming context**. Một DN đầy đủ vẫn **không bao gồm hostname/port** của LDAP server; DN và LDAP URL là hai loại định danh khác nhau.

### 3.2. Giữ cả hai dạng trong DTO

Một DTO gọn, dễ trả qua REST API, có thể giữ:

**`PersonSearchHit.java`**

```java
package com.example.ldap;

public record PersonSearchHit(
        String relativeDn,
        String fullDn,
        String uid,
        String displayName,
        String email
) {}
```

Hai trường `relativeDn` và `fullDn` có **hợp đồng khác nhau**; đừng đổi tên cả hai thành một trường `id` chung chung nếu hệ thống có nhiều context base. Trong DTO truyền qua JSON, dùng chuỗi thuận tiện hơn lưu thẳng `Name` có thể thay đổi trạng thái. Khi thực hiện LDAP operation, **parse lại thành `LdapName`**, xác minh phạm vi và lựa chọn đúng dạng DN theo API.

Nếu ứng dụng chỉ cần DN trong nội bộ, cũng có thể giữ bản sao `Name`. Tuy nhiên `Name` là interface có các implementation **mutable**; khi lưu vào cache hoặc chia sẻ giữa các thread, phải sao chép/bao gói phù hợp, tránh một tầng khác thay đổi các RDN của đối tượng đã lưu.

## 4. Ví dụ hoàn chỉnh: tìm user và giữ DN trong DTO

Giả sử LDAP directory sử dụng `dc=example,dc=org` làm base kết nối, chứa các user `inetOrgPerson` ở `ou=employees`. Java 17 trở lên hỗ trợ `record` và Spring LDAP cung cấp `AbstractContextMapper<T>`.

**`PersonDirectorySearch.java`**

```java
package com.example.ldap;

import java.util.List;

import javax.naming.Name;
import javax.naming.ldap.LdapName;

import org.springframework.ldap.core.ContextMapper;
import org.springframework.ldap.core.DirContextOperations;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.core.support.AbstractContextMapper;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.SearchScope;
import org.springframework.stereotype.Repository;

import static org.springframework.ldap.query.LdapQueryBuilder.query;

@Repository
public class PersonDirectorySearch {

    private final LdapTemplate ldapTemplate;

    public PersonDirectorySearch(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public static final ContextMapper<PersonSearchHit> PERSON_MAPPER =
            new AbstractContextMapper<>() {
                @Override
                protected PersonSearchHit doMapFromContext(
                        DirContextOperations ctx) {

                    String uid = required(ctx, "uid");
                    String cn = required(ctx, "cn");

                    return new PersonSearchHit(
                            ctx.getDn().toString(),
                            ctx.getNameInNamespace(),
                            uid,
                            cn,
                            ctx.getStringAttribute("mail"));
                }
            };

    public List<PersonSearchHit> findByUid(String uid) {
        if (uid == null || uid.isBlank()) {
            throw new IllegalArgumentException("uid không được rỗng");
        }

        LdapQuery ldapQuery = query()
                .base("ou=employees")
                .searchScope(SearchScope.SUBTREE)
                .attributes("uid", "cn", "mail")
                .countLimit(100)
                .where("objectClass").is("inetOrgPerson")
                .and("uid").is(uid);

        return ldapTemplate.search(ldapQuery, PERSON_MAPPER);
    }

    public PersonSearchHit findByRelativeDn(Name relativeDn) {
        return ldapTemplate.lookup(
                relativeDn,
                new String[]{"uid", "cn", "mail"},
                PERSON_MAPPER);
    }

    private static String required(DirContextOperations ctx, String attr) {
        String value = ctx.getStringAttribute(attr);
        if (value == null || value.isBlank()) {
            throw new IllegalStateException(
                    "Entry thiếu thuộc tính cần ánh xạ: " + attr);
        }
        return value;
    }
}
```

Ở class trên:

1. `PERSON_MAPPER` dùng `AbstractContextMapper` nên method `doMapFromContext(DirContextOperations ctx)` được nhận trực tiếp, không phải tự ép kiểu từ `Object`.
2. `ctx.getDn().toString()` lưu tên tương đối với `ContextSource.base`.
3. `ctx.getNameInNamespace()` lưu tên đầy đủ trong namespace của entry.
4. `.attributes("uid", "cn", "mail")` yêu cầu **chỉ các thuộc tính cần ánh xạ**; metadata DN vẫn có sẵn qua context mapper.
5. `.where("uid").is(uid)` tạo điều kiện và xử lý giá trị filter theo API Spring LDAP. Không nối chuỗi `"(uid=" + uid + ")"` từ input chưa tin cậy.
6. `.countLimit(100)` chỉ giới hạn số entry trả về cho lần tìm kiếm; **không** phải cơ chế phân trang.
7. `findByUid` trả `List` vì một login có thể không duy nhất trên nhiều nhánh/tenant nếu directory không cưỡng chế uniqueness theo phạm vi mà ứng dụng muốn.
8. `findByRelativeDn` dùng overload `lookup(Name, String[], ContextMapper)`, chứng minh có thể vừa **chỉ yêu cầu ba thuộc tính** vừa giữ DN.

Ví dụ cách gọi:

```java
List<PersonSearchHit> results = directorySearch.findByUid("lan");

for (PersonSearchHit hit : results) {
    System.out.println(hit.uid());
    System.out.println(hit.displayName());
    System.out.println(hit.relativeDn());
    System.out.println(hit.fullDn());
}
```

Không ghi DN thật vào log production như cách `System.out.println` minh họa. DN có thể lộ thông tin tài khoản, bộ phận, OU và cấu trúc nội bộ. Nên dùng log ở mức phù hợp, làm sạch hoặc dùng correlation ID.

### 4.1. Nếu muốn viết lambda ContextMapper trực tiếp

Không bắt buộc kế thừa `AbstractContextMapper`:

```java
import org.springframework.ldap.core.ContextMapper;
import org.springframework.ldap.core.DirContextOperations;

ContextMapper<PersonSearchHit> mapper = value -> {
    DirContextOperations ctx = (DirContextOperations) value;
    return new PersonSearchHit(
            ctx.getDn().toString(),
            ctx.getNameInNamespace(),
            ctx.getStringAttribute("uid"),
            ctx.getStringAttribute("cn"),
            ctx.getStringAttribute("mail"));
};
```

Đây là cùng cách tiếp cận về mặt dữ liệu, nhưng lambda không kiểm tra thuộc tính bắt buộc và phải ép kiểu. `AbstractContextMapper` xử lý việc ép kiểu cho bạn. Cả hai giả định `ContextSource` dùng `DirObjectFactory` tương thích, mặc định là `DefaultDirObjectFactory` tạo `DirContextAdapter`. Nếu hệ thống thay factory và không còn trả `DirContextOperations`, cần sửa mapper phù hợp thay vì ép kiểu mù.

## 5. Projection thuộc tính vẫn giữ được DN

Nhiều lập trình viên tưởng phải trả toàn bộ attributes mới lấy được DN. Không đúng: **LDAP SearchResultEntry chứa tên entry riêng**.

```text
filter  = (uid=lan)
attrs   = [uid, cn, mail]
output  = {
  relativeDn: "uid=lan,ou=employees",
  fullDn:     "uid=lan,ou=employees,dc=example,dc=org",
  uid:        "lan",
  name:       "Lan Nguyen",
  email:      "lan@example.org"
}
```

Không cần:

```java
// Không cần thêm "dn" vào danh sách returning attributes.
// .attributes("uid", "cn", "mail", "dn")
```

Thêm `dn` có thể không mang lại gì vì đó không phải thuộc tính user thông thường. Nếu dùng `AttributesMapper` và cố truy vấn `distinguishedName` trên một LDAP server khác, giải pháp có thể tình cờ chạy ở server đó nhưng **không portable**.

| Dữ liệu cần | Chọn cách ánh xạ |
|---|---|
| `cn`, `mail`, không có thao tác khác | `AttributesMapper` thường đủ |
| `cn`, `mail` và DN để mở trang chi tiết | `ContextMapper` |
| Chỉ lấy DN/đếm entry | `ContextMapper` với projection nhỏ hoặc `1.1` theo khả năng API/server |
| Entity LDAP đầy đủ có định danh | ODM `@Id` kiểu `Name` |
| Thuộc tính operational như `entryUUID` | Yêu cầu riêng theo schema/ACL; không mặc định có trong `*` |

Để giảm payload, vẫn nên chỉ yêu cầu `uid`, `cn`, `mail` khi màn hình chỉ sử dụng ba trường. **DN không miễn phí về bảo mật**: dù không nằm trong returning attributes, nó vẫn có thể là thông tin nội bộ cần hạn chế hiển thị.

### 5.1. Khi thiếu thuộc tính không có nghĩa entry vô danh

Giả sử LDAP server vì ACL không cho trả `mail`, mapper vẫn có thể nhận:

```text
relativeDn = uid=lan,ou=employees
fullDn     = uid=lan,ou=employees,dc=example,dc=org
uid        = lan
cn         = Lan Nguyen
mail       = null
```

DN của entry vẫn có thể được biết trong kết quả; **sự vắng mặt của `mail` không có nghĩa email chắc chắn không tồn tại**. Nó có thể vắng vì không được yêu cầu, không tồn tại hoặc bị ACL che. Mẫu mapper trên xử lý `mail` tùy chọn, còn `uid`/`cn` là bắt buộc theo hợp đồng DTO.

## 6. Dùng DN trả về để lookup, thay vì đoán lại

Sau khi người dùng chọn một kết quả, service có thể cần tra chi tiết đúng entry:

```java
import javax.naming.Name;
import javax.naming.ldap.LdapName;

PersonSearchHit selected = results.get(0);

// Chỉ dùng sau khi service đã xác minh quyền và trust boundary.
Name target = new LdapName(selected.relativeDn());

PersonSearchHit detail = directorySearch.findByRelativeDn(target);
```

**Quan trọng:** ví dụ trên giả định `selected` đến từ DAO trong cùng request/trust boundary. Nếu client gửi `relativeDn` qua HTTP, không được coi nó là “đã xác minh” chỉ vì parse được thành `LdapName`. Cần kiểm tra authorization, tenant, subtree cho phép và trạng thái entry hiện tại.

### 6.1. Tránh ghép trùng base DN

Với `ContextSource.base=dc=example,dc=org`:

```text
DN tương đối (cho LdapTemplate):
  uid=lan,ou=employees

DN đầy đủ (để tham chiếu LDAP):
  uid=lan,ou=employees,dc=example,dc=org
```

Không đưa DN đầy đủ vào API vốn diễn giải `Name` là **tương đối với base** mà không kiểm tra hợp đồng. Tùy cách ghép của provider/context, có thể tạo đường dẫn sai:

```text
uid=lan,ou=employees,dc=example,dc=org,dc=example,dc=org
```

Trường hợp khác: nếu `ContextSource.base` đã là `ou=employees,dc=example,dc=org`, `ctx.getDn()` có thể chỉ là `uid=lan`. Đó không phải lỗi mất dữ liệu; đó là **thay đổi hệ tọa độ** của DN tương đối. Hãy ghi rõ base nào tương ứng với từng DAO/repository.

### 6.2. Xây lại full DN khi biết base đáng tin

Nếu API đích chỉ trả DN tương đối và bạn có `base` từ cấu hình đáng tin, có thể ghép bằng **đối tượng Name**, không nối chuỗi tùy tiện:

```java
import javax.naming.Name;
import javax.naming.ldap.LdapName;
import org.springframework.ldap.support.LdapNameBuilder;

LdapName contextBase = new LdapName("dc=example,dc=org");
Name relativeDn = new LdapName("uid=lan,ou=employees");

LdapName fullDn = LdapNameBuilder.newInstance(contextBase)
        .add(relativeDn)
        .build();

// uid=lan,ou=employees,dc=example,dc=org
```

Đây là trường hợp phù hợp của `LdapNameBuilder.add(Name)`. Không đưa dữ liệu người dùng chưa xác minh vào `add(String)` như một đoạn DN; với **giá trị RDN động**, dùng `add("uid", rawUid)` để thư viện escape đúng.

Spring LDAP cũng có cơ chế cung cấp base path cho Spring-managed bean qua `BaseLdapNameAware` và `BaseLdapPathBeanPostProcessor` nếu cần tái sử dụng base trong nhiều service. Khi có nhiều `ContextSource`, phải chỉ định rõ nguồn base đúng; không tự chọn base của directory khác để ghép tên.

## 7. Dùng full DN trong thuộc tính thành viên nhóm

Với schema `groupOfNames`, thuộc tính `member` là **DN tham chiếu tới người dùng**, không phải chuỗi username:

```ldif
dn: cn=app_readers,ou=groups,dc=example,dc=org
objectClass: top
objectClass: groupOfNames
cn: app_readers
member: uid=lan,ou=employees,dc=example,dc=org
```

Khi tìm user rồi thêm vào nhóm, hãy lấy **full DN đã giữ lại** từ kết quả:

```java
import javax.naming.Name;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;

import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

void addToReadersGroup(
        LdapTemplate ldapTemplate, PersonSearchHit person) {

    // Group target là tên tương đối với ContextSource.base.
    Name groupRelativeDn = LdapNameBuilder.newInstance("ou=groups")
            .add("cn", "app_readers")
            .build();

    // Giá trị member là DN đầy đủ của người dùng.
    ModificationItem addMember = new ModificationItem(
            DirContext.ADD_ATTRIBUTE,
            new BasicAttribute("member", person.fullDn()));

    ldapTemplate.modifyAttributes(
            groupRelativeDn, new ModificationItem[]{addMember});
}
```

Trong ví dụ này:

- `groupRelativeDn` trỏ tới nhóm dưới base hiện tại.
- `person.fullDn()` là giá trị của **thuộc tính `member`** có syntax DN.
- Không dùng `person.relativeDn()` làm giá trị member nếu schema yêu cầu DN đầy đủ.
- Không dùng `person.uid()` làm member của `groupOfNames`; đó là cách hiểu sai schema.
- Nếu directory sử dụng `posixGroup.memberUid`, dữ liệu cần là **login**, không phải DN — phải đổi mô hình theo schema thực, không dùng code `groupOfNames` nguyên xi.

**Điều kiện an toàn:** trước khi sửa membership, hãy xác minh entry thuộc directory/tenant đáng tin, group nằm trong nhánh được phép và caller có quyền quản lý nhóm. LDAP server vẫn phải cưỡng chế ACL/schema. Nếu người dùng đã đổi DN giữa lúc đọc và lúc sửa nhóm, tham chiếu trong `member` có thể trở nên lỗi thời; việc giữ DN không tạo giao dịch xuyên hai entry.

## 8. Truy vấn khi DN dùng để sửa thuộc tính hoặc đổi tên

Khi cần chỉnh sửa email của entry đã chọn, đừng tìm lại bằng `uid` rồi chọn bừa kết quả đầu tiên:

```java
import javax.naming.Name;
import javax.naming.ldap.LdapName;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;

void changeEmail(
        LdapTemplate ldapTemplate, PersonSearchHit selected,
        String newEmail) throws Exception {

    Name target = new LdapName(selected.relativeDn());

    ModificationItem replaceMail = new ModificationItem(
            DirContext.REPLACE_ATTRIBUTE,
            new BasicAttribute("mail", newEmail));

    ldapTemplate.modifyAttributes(
            target, new ModificationItem[]{replaceMail});
}
```

Đây là ví dụ đường đi của DN **đã được ứng dụng kiểm soát**. Trong production phải thêm validation email, authorization, tenant boundary, xác minh identity và conflict handling. **Lưu DN không tự chống race condition**: một request khác có thể đổi mail, delete hoặc rename entry trước khi thao tác này được server thực hiện.

### 8.1. Rename làm thay đổi DN

Ví dụ:

```text
Trước:
  uid=lan,ou=employees,dc=example,dc=org

Đổi RDN:
  uid=lan.nguyen,ou=employees,dc=example,dc=org

Hoặc chuyển OU:
  uid=lan,ou=contractors,dc=example,dc=org
```

`LdapTemplate.rename(oldRelativeDn, newRelativeDn)` thay đổi DN trên server theo khả năng provider/backend. Sau rename:

- DTO đã lưu `oldRelativeDn` có thể không còn tra cứu được.
- Group `member` đang chứa DN cũ có thể không được cập nhật nếu server thiếu referential-integrity plugin.
- Các link hoặc cache keyed by DN cần invalidation.
- Nếu identity của người dùng phải bền vững qua rename, DN **không phải một khóa vĩnh viễn**.

Một số server cung cấp định danh ổn định hơn, ví dụ `entryUUID` (LDAP server hỗ trợ theo schema) hoặc `objectGUID` (Active Directory). Những thuộc tính này thường là operational/vendor-specific, phải **yêu cầu rõ, kiểm tra ACL và xác minh semantics**, không mặc định có sẵn trong `.attributes("*")`. Khi dùng chúng làm business identity, vẫn cần DN hiện tại làm **địa chỉ để thao tác LDAP**.

## 9. Spring Data LDAP ODM: @Id giữ DN

Ngoài `LdapTemplate`, Spring Data LDAP repository dùng **Object-Directory Mapping (ODM)**. Theo tài liệu Spring Data LDAP, entity được đánh dấu `@Entry` có thể chứa `@Id` kiểu `javax.naming.Name` để lưu DN.

**`PersonEntry.java`**

```java
package com.example.ldap;

import javax.naming.Name;
import org.springframework.ldap.odm.annotations.Attribute;
import org.springframework.ldap.odm.annotations.Entry;
import org.springframework.ldap.odm.annotations.Id;

@Entry(
        base = "ou=employees",
        objectClasses = {
                "top", "person", "organizationalPerson", "inetOrgPerson"
        }
)
public class PersonEntry {

    @Id
    private Name dn;

    @Attribute(name = "uid")
    private String uid;

    @Attribute(name = "cn")
    private String displayName;

    @Attribute(name = "sn")
    private String surname;

    @Attribute(name = "mail")
    private String email;

    public PersonEntry() {}

    public Name getDn() { return dn; }
    public void setDn(Name dn) { this.dn = dn; }

    public String getUid() { return uid; }
    public void setUid(String uid) { this.uid = uid; }

    public String getDisplayName() { return displayName; }
    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }

    public String getSurname() { return surname; }
    public void setSurname(String surname) {
        this.surname = surname;
    }

    public String getEmail() { return email; }
    public void setEmail(String email) { this.email = email; }
}
```

**`PersonRepository.java`**

```java
package com.example.ldap;

import org.springframework.data.ldap.repository.LdapRepository;

public interface PersonRepository extends LdapRepository<PersonEntry> {
}
```

`LdapRepository<T>` có **một type parameter** và dùng `Name` làm ID; không viết `LdapRepository<PersonEntry, Long>` như JPA. `@Id` ở đây phải là annotation của **Spring LDAP ODM**, không phải `jakarta.persistence.Id` hay một annotation `@Id` của datastore khác.

Sau khi repository đọc entry, trường `dn` của entity giữ tên theo **quy ước mapping/base** của Spring LDAP trong cấu hình hiện tại. Khi truyền sang code khác hoặc đối chiếu với giá trị `groupOfNames.member`, hãy xác minh đó là **DN tương đối hay đầy đủ**; không mặc nhiên coi `person.getDn().toString()` luôn có suffix `dc=example,dc=org`.

`@DnAttribute` có thể hỗ trợ ánh xạ một thành phần DN vào property Java, ví dụ `uid` của RDN, nhưng **không thay thế `@Id Name`** khi cần giữ toàn bộ đường dẫn DN. Cần tuân thủ quy tắc `@DnAttribute` của phiên bản ODM, nhất là khi entry có nhiều RDN hoặc dùng RDN đa trị.

### 9.1. Khi nào dùng ODM, khi nào dùng ContextMapper?

| Nhu cầu | Cách cân nhắc |
|---|---|
| Entity có vòng đời lưu/đọc theo repository | ODM `@Entry` + `@Id Name` |
| Chỉ đọc vài thuộc tính thành DTO và cần giữ DN | `LdapTemplate.search(query, ContextMapper)` |
| Trả danh sách tìm kiếm nhẹ, không dùng entity để ghi | `PersonSearchHit` riêng |
| Cập nhật một thuộc tính cụ thể theo DN đã chọn | `LdapTemplate.modifyAttributes` với `ModificationItem` |
| Cần DN đầy đủ cho group membership | `getNameInNamespace()` hoặc ghép với base đáng tin |

**Cảnh báo ghi dữ liệu:** không lấy một DTO chỉ có `uid`/`cn`/`mail` rồi gán vào entity ODM và gọi `repository.save(...)` khi không hiểu cách mapper xử lý thuộc tính vắng mặt. Nó có thể làm mất/đổi các thuộc tính không được load. Read projection và write entity nên có hợp đồng riêng, nhất là trên entry chứa `objectClass` và nhiều giá trị.

## 10. So sánh DN theo cấu trúc thay vì chuỗi tùy tiện

DN có cú pháp RFC 4514. Dấu phẩy, dấu cộng, dấu bằng, dấu gạch chéo ngược và khoảng trắng đặc biệt có thể xuất hiện trong **giá trị RDN**, được escape khi biểu diễn thành chuỗi:

```text
Giá trị uid:
  lan,team

DN hiển thị:
  uid=lan\,team,ou=employees,dc=example,dc=org
```

Sai:

```java
String rawUid = "lan,team";
String guessedDn = "uid=" + rawUid + ",ou=employees,dc=example,dc=org";
// Parser có thể hiểu dấu phẩy trong input là dấu phân cách RDN.
```

Đúng khi **đã biết** vị trí:

```java
import javax.naming.ldap.LdapName;
import org.springframework.ldap.support.LdapNameBuilder;

String rawUid = "lan,team";
LdapName safelyBuilt = LdapNameBuilder
        .newInstance("dc=example,dc=org")
        .add("ou", "employees")
        .add("uid", rawUid)
        .build();
```

Tuy nhiên, trong bài toán **ánh xạ kết quả**, cách tốt nhất vẫn là giữ **DN từ server** bằng `ContextMapper`, không tự xây lại chỉ từ `uid` khi bạn không biết chắc cây LDAP đang dùng naming rule nào.

### 10.1. Kiểm tra DN thuộc nhánh đáng tin

Khi nhận một full DN cần xác định nó có nằm trong subtree cho phép không, hãy parse cấu trúc:

```java
import javax.naming.Name;
import javax.naming.ldap.LdapName;

LdapName expectedBranch =
        new LdapName("ou=employees,dc=example,dc=org");
LdapName userFullDn =
        new LdapName("uid=lan,ou=employees,dc=example,dc=org");

boolean inside = userFullDn.startsWith(expectedBranch);
// true: Name được so khớp từ các thành phần ít cụ thể nhất.
```

Đừng dùng `fullDnString.endsWith("dc=example,dc=org")` để tạo hàng rào bảo mật. Chuỗi DN có thể được escape theo nhiều cách, khác khoảng trắng/case và không thể so khớp cấu trúc tin cậy chỉ bằng `String.endsWith`.

Với `LdapName`, `startsWith` so sánh các RDN từ phía ít cụ thể nhất; điều này **khác trực giác** khi nhìn chuỗi DN có leaf ở bên trái. Ngay cả khi DN nằm trong nhánh cho phép, **vẫn cần authorization ở service và LDAP ACL**. DN parsing không tự kiểm tra người gọi có quyền sửa entry.

### 10.2. Cắt suffix base bằng Name, không dùng substring

Ví dụ full DN được **trả về từ nguồn đáng tin** nhưng API `LdapTemplate` muốn DN tương đối với `dc=example,dc=org`:

```java
import javax.naming.Name;
import javax.naming.ldap.LdapName;

Name fullDn = new LdapName(
        "uid=lan,ou=employees,dc=example,dc=org");
Name configuredBase = new LdapName("dc=example,dc=org");

if (!fullDn.startsWith(configuredBase)) {
    throw new IllegalArgumentException(
            "Entry không thuộc naming context được cấu hình");
}

Name relativeDn = fullDn.getSuffix(configuredBase.size());
// uid=lan,ou=employees
```

Đây là phép chuyển đổi **chỉ phù hợp khi đã biết chính xác base của context đích**. Với referral hoặc nhiều naming context, base của source và target có thể khác nhau. Không tự bóc suffix của một DN thuộc directory khác để gửi sang server hiện tại.

## 11. Một DN không đủ để mô tả mọi dạng identity

DN trả lời câu hỏi **“entry ở vị trí nào trong directory?”** chứ không phải mọi câu hỏi về định danh lâu dài:

| Định danh | Mục đích | Có thay đổi không? |
|---|---|---|
| `uid` | Login name thuộc tính của user | Có thể đổi hoặc trùng trên OU khác tùy chính sách |
| `cn` | Tên hiển thị hoặc naming attribute | Có thể đổi, không luôn duy nhất |
| DN | Locator của entry trong LDAP namespace | **Đổi khi rename/move** |
| `entryUUID` | ID do một số server cấp (operational) | Thường ổn định hơn DN, phụ thuộc backend |
| `objectGUID` | ID đặc thù Active Directory | Có semantics riêng của AD |
| LDAP server/tenant identifier | Xác định directory authority | Cần nếu ứng dụng kết nối nhiều LDAP server/domain |

Nếu lưu trữ dữ liệu ngoài LDAP (ví dụ hệ thống duyệt hồ sơ), chỉ có `fullDn` không đảm bảo identity luôn đúng sau rename hoặc chuyển OU. Có thể cần cặp `directoryId + stableEntryId` và một dịch vụ ánh xạ sang **DN hiện tại**. Dù vậy, khi gọi JNDI Modify/Delete, ứng dụng vẫn cần **địa chỉ DN phù hợp với server đích**.

**Referrals:** khi search đi qua referral, kết quả có thể thuộc naming context/server được giới thiệu, tùy cách provider theo dõi referral. `DirContextOperations` có `isReferral()` và `getReferralUrl()` ở một số đường đi. Nếu hệ thống có referrals, hãy xác định rõ **LDAP endpoint + naming context + full DN** trước khi dùng kết quả cho thao tác ghi; không coi `fullDn` đơn lẻ là khóa duy nhất giữa hai directory độc lập.

## 12. Bảo mật và thiết kế API trả DTO có DN

DN có thể chứa:

- Tên đăng nhập, bộ phận, địa điểm hoặc cấu trúc tổ chức (OU).
- Nhánh quản trị, dịch vụ, hệ thống hoặc tenant.
- RDN có giá trị nhạy cảm theo quy ước đặt tên của directory.

Vì thế, một API trả `fullDn` không hẳn phù hợp cho frontend công khai. Tách hai loại dữ liệu:

```text
DTO nội bộ:
  relativeDn, fullDn, uid, cn, mail
                 |
                 | Authorization + redaction
                 v
DTO công khai:
  opaqueId, displayName, email được phép hiển thị
```

Khi người dùng click `opaqueId`, backend tra ánh xạ được cấp quyền tới DN hiện tại. Tránh để client tự gửi DN tùy ý để service có bind account mạnh dùng `lookup`/`modifyAttributes` trực tiếp. Dù sử dụng `LdapName` để parse, **DN traversal trong vùng không được phép** vẫn là nguy cơ authorization nếu base và ACL không được cưỡng chế.

Nguyên tắc:

1. Chỉ truy vấn những nhánh người gọi được phép xem.
2. Trả DN ra ngoài API **khi thực sự có yêu cầu nghiệp vụ**, áp dụng data minimization.
3. Nếu dùng DN ở route HTTP, cần mã hóa URI đúng cách; không ghép thẳng chuỗi RFC 4514 vào URL.
4. Không gắn DN đầy đủ vào metric tags, log không bảo vệ hoặc thông báo lỗi trả ra trình duyệt.
5. Kiểm tra ACL của LDAP server cùng authorization ở ứng dụng khi thao tác đọc/ghi.
6. Dùng `LdapNameBuilder.add(attribute, rawValue)` cho RDN động; đừng nhầm **DN escaping** với **LDAP filter escaping**.
7. Nếu có caching, đánh dấu chính xác directory/base/tenant và invalidation sau rename/delete.

**Quan trọng:** giữ DN của result là **để biết đúng entry**, không phải cấp phép tự động với entry đó.

## 13. Kiểm thử unit mapper có giữ DN không?

Không cần LDAP server để kiểm tra mapper có chép cả hai dạng tên. `DirContextAdapter` có constructor nhận `Attributes`, DN tương đối và base:

**`PersonMapperTest.java`**

```java
package com.example.ldap;

import javax.naming.directory.Attributes;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.BasicAttributes;
import javax.naming.ldap.LdapName;

import org.junit.jupiter.api.Test;
import org.springframework.ldap.core.DirContextAdapter;

import static org.junit.jupiter.api.Assertions.assertEquals;

class PersonMapperTest {

    @Test
    void preservesBothRelativeAndFullDn() throws Exception {
        Attributes attrs = new BasicAttributes(true);
        attrs.put(new BasicAttribute("uid", "lan"));
        attrs.put(new BasicAttribute("cn", "Lan Nguyen"));
        attrs.put(new BasicAttribute("mail", "lan@example.org"));

        LdapName relative =
                new LdapName("uid=lan,ou=employees");
        LdapName contextBase =
                new LdapName("dc=example,dc=org");

        DirContextAdapter adapter =
                new DirContextAdapter(attrs, relative, contextBase);

        PersonSearchHit result =
                PersonDirectorySearch.PERSON_MAPPER
                        .mapFromContext(adapter);

        assertEquals("uid=lan,ou=employees", result.relativeDn());
        assertEquals(
                new LdapName(
                        "uid=lan,ou=employees,dc=example,dc=org"),
                new LdapName(result.fullDn()));
        assertEquals("lan", result.uid());
        assertEquals("Lan Nguyen", result.displayName());
        assertEquals("lan@example.org", result.email());
    }
}
```

Unit test này xác minh **logic mapping** của `ContextMapper` với context adapter giả lập. Nó không chứng minh directory thật trả đúng DN cho search, referral hoặc ACL — cần integration test. So sánh `LdapName` theo cấu trúc hữu ích hơn so sánh mọi biến thể chuỗi escape/case.

### 13.1. Test ký tự đặc biệt ở RDN

Khi UID chứa dấu phẩy, một mapper đúng **không được tạo thêm RDN ngoài ý muốn**. Có thể dùng:

```java
import javax.naming.ldap.LdapName;
import org.springframework.ldap.support.LdapNameBuilder;

LdapName full = LdapNameBuilder
        .newInstance("dc=example,dc=org")
        .add("ou", "employees")
        .add("uid", "lan,team")
        .build();

assertEquals(4, full.size());
assertEquals("lan,team",
        full.getRdn(full.size() - 1).getValue());
```

Nếu giá trị có dấu phẩy được parse thành RDN thứ năm, code đang dùng cách ghép chuỗi DN sai. `LdapName` chứa các RDN theo cấu trúc; số lượng RDN và giá trị leaf là bằng chứng tốt hơn chỉ kiểm tra `String.contains("\\,")`.

## 14. Kiểm thử tích hợp với LDAP directory thật

Thiết lập LDAP test directory, ví dụ:

```ldif
dn: ou=employees,dc=example,dc=org
objectClass: top
objectClass: organizationalUnit
ou: employees

dn: uid=lan,ou=employees,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: lan
cn: Lan Nguyen
sn: Nguyen
mail: lan@example.org
```

Fixture giả định `dc=example,dc=org` đã tồn tại. `ContextSource.base` được đặt là `dc=example,dc=org` và bind identity có quyền đọc `ou=employees`.

**`PersonDirectorySearchIT.java`**

```java
package com.example.ldap;

import java.util.List;
import javax.naming.ldap.LdapName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest
class PersonDirectorySearchIT {

    @Autowired
    PersonDirectorySearch directorySearch;

    @Test
    void searchKeepsExactEntryDn() throws Exception {
        List<PersonSearchHit> results =
                directorySearch.findByUid("lan");

        assertEquals(1, results.size());
        PersonSearchHit hit = results.get(0);

        assertEquals(
                new LdapName("uid=lan,ou=employees"),
                new LdapName(hit.relativeDn()));

        assertEquals(
                new LdapName(
                        "uid=lan,ou=employees,dc=example,dc=org"),
                new LdapName(hit.fullDn()));

        assertEquals("lan", hit.uid());
        assertEquals("Lan Nguyen", hit.displayName());

        PersonSearchHit reread = directorySearch.findByRelativeDn(
                new LdapName(hit.relativeDn()));
        assertEquals(
                new LdapName(hit.fullDn()),
                new LdapName(reread.fullDn()));
    }
}
```

Test này cần một LDAP server thật hoặc embedded/testcontainer directory có dữ liệu và quyền phù hợp. **Không giả định** `@SpringBootTest` sẽ tự khởi động LDAP server. Nếu server dùng alias/referral, replication hoặc định tuyến qua nhiều naming contexts, cần mở rộng kịch bản trước khi khẳng định tất cả DN đều có dạng như fixture.

### 14.1. Ma trận tình huống cần kiểm tra

| Tình huống | Kết quả mong đợi |
|---|---|
| Search ở `ou=employees`, base context là `dc=example,dc=org` | `relativeDn` chứa `ou=employees`, `fullDn` chứa đủ suffix |
| Đổi context base thành `ou=employees,dc=example,dc=org` | DN tương đối thay đổi đúng theo base |
| Chỉ request `uid`, `cn`, `mail` | DTO vẫn có DN, không cần attribute `dn` |
| Hai entry cùng `uid` ở hai OU | DTO giữ hai DN khác nhau; không tự gộp theo login |
| Entry có `cn` khác RDN | DN từ server được giữ, không dựng lại từ `cn` |
| RDN có `,`, `+` hoặc `\\` | Mapper không tách RDN bằng `String.split` |
| LDAP không trả `mail` | DTO email `null` nhưng vẫn có DN |
| LDAP không trả `cn` do ACL/schema | Mapper báo lỗi theo hợp đồng; không trả đối tượng thiếu identity hiển thị mà không biết |
| Search bị size limit/referral | Không coi danh sách một phần là toàn directory |
| Entry bị rename sau search | Lookup qua old DN lỗi hoặc trỏ trạng thái khác; cần refresh |
| Thêm user vào `groupOfNames.member` | Dùng full DN, server kiểm tra syntax/ACL |
| User không thuộc nhánh được phép | Service từ chối trước khi lookup/modify |
| Spring Data LDAP repository `@Id Name` | DN giữ đúng theo mapping/ContextSource.base |
| DN đến từ referral hoặc directory khác | Không tự gửi nó sang context source sai endpoint |

### 14.2. Kiểm thử quyền và sự thay đổi của DN

Với test có quyền ghi:

1. Tạo entry mới dưới OU riêng của test bằng `LdapNameBuilder`.
2. Search và lưu cả DN tương đối/đầy đủ vào DTO.
3. Thử cập nhật một thuộc tính qua `modifyAttributes` bằng relative DN của DTO.
4. Đổi RDN hoặc chuyển OU bằng `rename` theo khả năng server.
5. Xác nhận DN cũ không còn là locator hiện tại; search lại và nhận DN mới.
6. Kiểm tra quan hệ nhóm hoặc cache ngoài LDAP đã được cập nhật/chính sách reconciliation phù hợp.
7. Thử với tài khoản không được phép rename/modify; server phải từ chối.

Đây là kịch bản **trên directory test**, không được chạy các thao tác ghi hoặc rename trên directory production chỉ để kiểm chứng mapper.

## 15. Các lỗi phổ biến khi làm mất DN

| Triệu chứng | Nguyên nhân | Cách khắc phục |
|---|---|---|
| Search trả user nhưng không thể mở trang chi tiết | DTO chỉ có `uid`/`cn` | Dùng `ContextMapper`, giữ `relativeDn`/`fullDn` |
| `attrs.get("dn")` trả `null` | DN là metadata SearchResultEntry, không phải thuộc tính user chuẩn | Dùng `DirContextOperations.getDn()` |
| Thao tác modify báo `NameNotFoundException` | Dùng full DN trong context mong relative DN; hoặc entry đã move | Kiểm tra `ContextSource.base` và DN hiện tại |
| Group có `member` nhưng membership không được nhận | Lưu relative DN hoặc username thay full DN | Dùng DN đầy đủ theo schema `groupOfNames` |
| Hai kết quả cùng `uid` bị ghi đè trong Map | Chọn `uid` làm khóa khi nó không duy nhất trong scope | Dùng identity phù hợp và quản lý DN/tenant |
| DN từ `ctx.getDn()` thiếu suffix | Đây là DN tương đối với context base | Dùng `getNameInNamespace()` hoặc ghép base đáng tin |
| DN từ `getNameInNamespace()` không đúng kỳ vọng trong referral | Khác naming context/provider | Kiểm tra endpoint/referral và mapping test |
| `ClassCastException` khi dùng `ContextMapper` | Custom `DirObjectFactory` không trả `DirContextOperations` | Sửa factory/mapper hoặc cấu hình mặc định |
| Kết quả đổi tên nhưng cache vẫn trỏ DN cũ | DN là locator có thể thay đổi | Invalidate cache, dùng stable ID phù hợp nếu cần |
| Nhóm/entry bị nhầm sau ký tự đặc biệt | Nối hoặc split DN bằng chuỗi | Dùng `LdapName` và `LdapNameBuilder` |
| Đã có DN nên cho sửa mọi entry | Thiếu authorization và LDAP ACL | Kiểm tra tenant/subtree/role và quyền server |
| Ghi log full DN của toàn bộ người dùng | Thiếu data minimization | Ẩn hoặc loại bỏ DN nhạy cảm khỏi log/metrics |

Đừng giải quyết lỗi bằng cách bắt toàn bộ `Exception` rồi trả `List.of()`: điều đó khiến lỗi mạng, quyền truy cập, DN sai, referral hay mapper lỗi bị hiểu nhầm thành “không tìm thấy user”.

## 16. Bài tập thực hành

1. Viết một `ContextMapper<PersonSearchHit>` dùng `DirContextOperations` để trả `relativeDn`, `fullDn`, `uid`, `cn` và `mail`.
2. Cấu hình `ContextSource.base=dc=example,dc=org`; tìm dưới `ou=employees` và kiểm chứng relative DN giữ nguyên cả `ou=employees`.
3. Tạo thêm entry `uid=lan,ou=partners,dc=example,dc=org` và đổi base tìm kiếm sang một scope bao trùm cả hai OU; kết quả phải giữ **hai DN khác nhau**.
4. Tạo entry có RDN `uid=lan\,team` bằng builder, kiểm tra `LdapName.getRdn(...).getValue()` vẫn là `lan,team`.
5. Chuyển DTO sang `AttributesMapper` rồi so sánh: bạn còn lấy được DN chính xác từ kết quả bằng cách nào?
6. Dùng full DN đã ánh xạ làm giá trị `groupOfNames.member` trong LDAP test; phân biệt với việc dùng relative DN để gọi `LdapTemplate.modifyAttributes`.
7. Thử rename entry trong directory test, tìm lại DN mới và xác định chỗ cần invalidation cache.
8. Bổ sung REST DTO công khai dùng opaque ID thay vì đưa full DN ra client; làm rõ authorization khi backend giải quyết ID thành DN.
9. Dùng ODM `@Entry`/`@Id Name` để đọc cùng entry, đối chiếu DN với `ContextMapper` trong cùng context base.

## 17. Câu hỏi tự kiểm tra

1. Vì sao `uid` hoặc `cn` không luôn đủ để khôi phục DN của một entry đã được tìm thấy?
2. `AttributesMapper` và `ContextMapper` khác nhau thế nào về khả năng giữ tên entry?
3. Với `ContextSource.base=dc=example,dc=org`, `ctx.getDn()` và `ctx.getNameInNamespace()` thường trả các dạng tên nào?
4. `ctx.getDn()` có tương đối với search base `ou=employees` hay với base của `ContextSource`?
5. Tại sao `.attributes("uid", "cn", "mail")` vẫn cho phép `ContextMapper` lấy DN?
6. Vì sao `attrs.get("dn")` không phải phương pháp LDAP portable để lấy DN?
7. Cần lưu dạng DN nào trong `groupOfNames.member`, và dạng DN nào thường dùng cho `LdapTemplate.lookup` với base cố định?
8. Nếu đổi `ContextSource.base`, trường `relativeDn` trong DTO thay đổi ra sao?
9. Vì sao `LdapName.startsWith(...)` thích hợp hơn `String.endsWith(...)` khi kiểm tra subtree?
10. Khi một entry đổi RDN/OU, DN cũ có còn là identity bền vững không?
11. ODM `@Id Name` giúp gì cho entity Spring Data LDAP, và vì sao không dùng kiểu ID như `Long`?
12. Một DTO có DN có được quyền sửa entry tương ứng không? Cần thêm những kiểm tra nào?
13. Khi tìm kiếm có referral, vì sao cần biết cả endpoint và naming context trước khi dùng DN cho thao tác ghi?

**Ghi nhớ:** khi kết quả LDAP phải được **tra cứu lại, sửa, đổi tên hoặc dùng trong quan hệ nhóm**, hãy giữ **DN của chính entry được server trả về**. `AttributesMapper` chỉ nhận thuộc tính, còn `ContextMapper`/`DirContextOperations` cung cấp `getDn()` (tương đối với base) và `getNameInNamespace()` (tên trong LDAP namespace). Trong Spring Data LDAP ODM, `@Id Name` lưu định danh của entity. DN là locator **có thể thay đổi** sau rename/move; luôn tôn trọng context base, schema, ACL, tenant và ranh giới directory, đồng thời kiểm thử bằng dữ liệu thực thay vì đoán DN từ `uid`.

### Tài liệu tham khảo

- IETF [RFC 4511 — LDAP: The Protocol](https://www.rfc-editor.org/rfc/rfc4511): `SearchResultEntry`, `objectName` và danh sách thuộc tính trả về.
- IETF [RFC 4514 — String Representation of Distinguished Names](https://www.rfc-editor.org/rfc/rfc4514): RDN, thứ tự thành phần và escape DN.
- Spring LDAP Reference — [Simplifying Attribute Access with DirContextAdapter](https://docs.spring.io/spring-ldap/reference/dirobjectfactory.html): ánh xạ với `ContextMapper` và `DirContextAdapter`.
- Spring LDAP API — [`DirContextAdapter`](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/core/DirContextAdapter.html): `getDn()`, `getNameInNamespace()`, constructors và đọc attribute.
- Spring LDAP API — [`ContextMapper`](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/ContextMapper.html), [`AbstractContextMapper`](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/support/AbstractContextMapper.html).
- Spring LDAP API — [`LdapTemplate`](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/core/LdapTemplate.html): `search(LdapQuery, ContextMapper)` và `lookup(Name, String[], ContextMapper)`.
- Spring LDAP Reference — [Obtaining a Reference to the Base LDAP Path](https://docs.spring.io/spring-ldap/reference/configuration.html): `BaseLdapNameAware` và ghép base path để tạo full DN.
- Spring LDAP API — [`LdapNameBuilder`](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/support/LdapNameBuilder.html): thao tác với `LdapName` có cấu trúc.
- Spring Data LDAP — [Object-Directory Mapping](https://docs.spring.io/spring-ldap/reference/odm.html), [Spring Data LDAP Repository Usage](https://docs.spring.io/spring-data/ldap/reference/ldap/usage.html): `@Entry`, `@Id Name`, entity ID và ánh xạ.
- Oracle Java SE — [`LdapName`](https://docs.oracle.com/en/java/javase/17/docs/api/java.naming/javax/naming/ldap/LdapName.html), [`Name`](https://docs.oracle.com/en/java/javase/17/docs/api/java.naming/javax/naming/Name.html).
