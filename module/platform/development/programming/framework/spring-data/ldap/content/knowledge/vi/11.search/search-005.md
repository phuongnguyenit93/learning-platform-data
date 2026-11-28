# Đọc thuộc tính vận hành và kiểm tra quyền máy chủ

## 1. Vấn đề: tại sao tìm được người dùng nhưng không thấy metadata?

Trong **Spring Data LDAP**, ứng dụng truy cập dịch vụ thư mục LDAP qua `LdapRepository`, ánh xạ entry thành object Java bằng ODM hoặc dùng `LdapTemplate` để truy vấn trực tiếp. Người học thường tìm được các thuộc tính `uid`, `cn`, `sn`, `mail` nhưng lại không thấy thời gian tạo, thời gian chỉnh sửa, danh tính đã sửa hoặc mã định danh entry.

Ví dụ, một bản ghi người dùng có:

```ldif
dn: uid=linh,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: linh
cn: Linh Nguyen
sn: Nguyen
mail: linh@example.org
```

Đối với một số directory, máy chủ còn duy trì metadata như `createTimestamp`, `modifyTimestamp`, `creatorsName`, `modifiersName` hoặc `entryUUID`. Các trường này thường là **thuộc tính vận hành** (*operational attributes*), không được trả về theo cùng cơ chế mặc định với thuộc tính ứng dụng thông thường.

Tuy nhiên, việc yêu cầu metadata thành công **không có nghĩa** tài khoản ứng dụng được phép xem mọi thuộc tính. LDAP server quyết định quyền truy cập thực tế dựa trên **danh tính bind**, subtree, attribute, thao tác và các chính sách riêng của hệ thống. Bài học này tập trung vào hai năng lực liên quan:

1. **Yêu cầu và đọc đúng thuộc tính vận hành** qua LDAP Search, `LdapTemplate` và các API Java.
2. **Kiểm tra quyền máy chủ một cách có bằng chứng**, không nhầm dữ liệu bị ẩn với dữ liệu không tồn tại, không biến lỗi quyền thành kết quả rỗng.

### Kết quả học tập

Sau bài, bạn có thể:

- Phân biệt **user attributes** và **operational attributes**, cùng tác dụng của `*`, `+` và danh sách tên thuộc tính tường minh.
- Đọc metadata vận hành bằng `ldapsearch`, `LdapTemplate`/`LdapQueryBuilder` và `SearchControls` của JNDI.
- Hiểu ý nghĩa của Root DSE và cách kiểm tra khả năng hỗ trợ `+` mà không suy diễn rằng một server đã cấp quyền đọc.
- Xác minh tài khoản bind đang dùng, phân biệt quyền **search**, **compare**, **read** và **write** theo chính sách của LDAP server.
- Thiết kế kiểm thử **cho phép** và **từ chối** trên directory thử nghiệm, với DN, filter và kết nối an toàn.
- Phát hiện tình huống kết quả rỗng, thuộc tính bị bỏ qua, sai base DN, lỗi schema/ACL hoặc mất kết nối.

## 2. Thuộc tính thông thường và thuộc tính vận hành

LDAP entry gồm các cặp tên attribute và một hoặc nhiều giá trị. Phân loại attribute phụ thuộc vào định nghĩa schema, **không** phụ thuộc vào việc tên có trông giống metadata hay không.

| Nhóm | Ví dụ | Mục đích | Điểm cần chú ý |
| --- | --- | --- | --- |
| **User attributes** | `uid`, `cn`, `sn`, `mail`, `telephoneNumber` | Dữ liệu người dùng/ứng dụng. | Thường được yêu cầu khi không chỉ định danh sách thuộc tính. |
| **Operational attributes** | `createTimestamp`, `modifyTimestamp` | Thời điểm server tạo hoặc sửa entry. | Thường phải yêu cầu rõ bằng tên hoặc cơ chế `+`. |
| **Operational attributes** | `creatorsName`, `modifiersName` | DN danh tính liên quan đến thao tác tạo/sửa. | Có thể bị che bởi ACL hoặc không có trên một số triển khai. |
| **Operational attributes** | `entryUUID` | Định danh entry theo cơ chế LDAP được server hỗ trợ. | Không mặc định đồng nhất với `objectGUID` của Active Directory. |
| **Operational attributes** | `structuralObjectClass`, `subschemaSubentry`, `hasSubordinates` | Metadata cấu trúc/schema hoặc trạng thái cây. | Mức hỗ trợ và quyền đọc tùy server. |
| **Directory-specific attributes** | `whenCreated`, `whenChanged`, `objectGUID`, `uSNChanged` | Thông tin phổ biến trong một số directory, đặc biệt Active Directory. | Không tự suy ra chúng đều thuộc cùng loại `operational` trong mọi schema. |

Các thuộc tính `createTimestamp` và `modifyTimestamp` thường có dạng **Generalized Time** như `20261126100530Z`. Đừng mặc định chúng là `LocalDateTime`, cũng đừng loại bỏ ký hiệu múi giờ; parser phải tuân định dạng thực tế và biến thể được server trả về.

### 2.1. Không phải metadata nào cũng có thể sửa

Những thuộc tính do directory **duy trì tự động** thường bị hạn chế hoặc không cho client tự ghi, dù ứng dụng có thể đọc. Không dùng `LdapTemplate.modifyAttributes` để “sửa” `createTimestamp` hay `entryUUID`; việc máy chủ trả lỗi là hành vi phù hợp với mô hình dữ liệu. Thay đổi quyền read cũng không tự cấp quyền write.

Ngược lại, `description` tuy đôi khi dùng ghi chú vận hành vẫn là user attribute trong nhiều schema. Hãy kiểm tra schema và tài liệu server thay vì phân loại theo tên.

### 2.2. Metadata không phải lịch sử kiểm toán đầy đủ

`modifiersName` và `modifyTimestamp` cho biết thông tin **lần thay đổi được server ghi nhận theo contract của nó**, không phải toàn bộ danh sách ai đã sửa gì, khi nào, với giá trị trước/sau. Nếu mọi request đều bind bằng một **service account**, `modifiersName` có thể phản ánh tài khoản dịch vụ, không phản ánh người dùng HTTP đã yêu cầu hành động.

Để kiểm toán đầy đủ, cần cơ chế audit server/ứng dụng riêng với chính sách lưu giữ và bảo vệ dữ liệu phù hợp.

## 3. Chọn thuộc tính trả về trong LDAP Search

Theo LDAPv3 và RFC 3673, danh sách `attributes` của SearchRequest có ngữ nghĩa riêng:

| Cách yêu cầu | Ý nghĩa | Điều không được suy diễn |
| --- | --- | --- |
| Không chỉ định attributes | Theo LDAPv3, yêu cầu **all user attributes**. | Không có nghĩa yêu cầu toàn bộ operational attributes. |
| `*` | Yêu cầu toàn bộ **user attributes**. | Không thay cho `+`. |
| `+` | Yêu cầu **operational attributes** khi server hỗ trợ RFC 3673. | Không bảo đảm tất cả đều được trả nếu ACL hoặc giới hạn khác áp dụng. |
| `*` và `+` | Yêu cầu cả user và operational attributes. | Không bỏ qua chính sách access control. |
| `uid`, `cn`, `createTimestamp` | Chỉ yêu cầu các tên attribute được liệt kê. | Server có thể không trả attribute vắng mặt hoặc không được phép đọc. |
| `1.1` khi dùng riêng | Yêu cầu **không trả attribute nào** (chỉ nhận entry/DN và kết quả search). | Không phải một attribute có tên `1.1`. |

Điểm tinh tế từ **RFC 3673**: server có thể không hỗ trợ `+`, hoặc có một số operational attributes tốn kém chỉ trả **khi yêu cầu đích danh**, ngay cả khi đã có `+`. Bên cạnh đó, **quyền đọc** vẫn áp dụng; không thấy metadata không đủ để kết luận thuộc tính không tồn tại.

### 3.1. So sánh bốn truy vấn

Giả sử user `uid=linh` tồn tại:

```bash
# Chỉ các user attributes:
ldapsearch -LLL -x -H "ldaps://ldap.example.org:636" \
  -D "uid=svc-reader,ou=service-accounts,dc=example,dc=org" -W \
  -b "uid=linh,ou=people,dc=example,dc=org" -s base \
  "(objectClass=*)" "*"

# Chỉ yêu cầu operational attributes:
ldapsearch -LLL -x -H "ldaps://ldap.example.org:636" \
  -D "uid=svc-reader,ou=service-accounts,dc=example,dc=org" -W \
  -b "uid=linh,ou=people,dc=example,dc=org" -s base \
  "(objectClass=*)" "+"

# Yêu cầu cả hai nhóm:
ldapsearch -LLL -x -H "ldaps://ldap.example.org:636" \
  -D "uid=svc-reader,ou=service-accounts,dc=example,dc=org" -W \
  -b "uid=linh,ou=people,dc=example,dc=org" -s base \
  "(objectClass=*)" "*" "+"

# Tập trung vào các tên metadata cụ thể:
ldapsearch -LLL -x -H "ldaps://ldap.example.org:636" \
  -D "uid=svc-reader,ou=service-accounts,dc=example,dc=org" -W \
  -b "uid=linh,ou=people,dc=example,dc=org" -s base \
  "(objectClass=*)" uid cn createTimestamp modifyTimestamp entryUUID
```

Trong ví dụ:

- `-x` yêu cầu simple authentication; `-D` chỉ định **bind DN**; `-W` yêu cầu nhập secret qua prompt, tránh viết trực tiếp secret trong command line.
- `-b` chỉ định **DN đầy đủ** vì `ldapsearch` truy vấn trực tiếp server.
- `-s base` chỉ kiểm tra đúng một entry, không quét cả subtree.
- Dấu nháy quanh `*`/`+` là để shell không diễn giải ký tự đặc biệt.
- Server thực tế có thể không trả mọi thuộc tính trong ví dụ, kể cả khi truy vấn đúng.

Không thực hiện những lệnh này với tài khoản quản trị trên directory production chỉ để “xem cho đủ metadata”. Hãy thử trước với bind account có phạm vi quyền như ứng dụng cần dùng.

## 4. Phân biệt kết quả không có attribute với lỗi quyền

Khi mapper nhận `Attributes attrs`, nếu `attrs.get("modifyTimestamp") == null`, có **nhiều khả năng**:

1. Entry đang được truy vấn không có thuộc tính đó.
2. Client không yêu cầu thuộc tính đó, ví dụ chỉ yêu cầu `*`.
3. Server không hỗ trợ tên attribute hoặc không hỗ trợ cơ chế `+` mong muốn.
4. Attribute có nhưng ACL chặn đọc và server chọn cách **không trả về**.
5. Truy vấn nhắm sai DN, OU hoặc server, nên đang xem một entry khác.
6. Mapping/returning-attributes đã giới hạn dữ liệu trước khi vào mapper.

Chỉ riêng `null` không phân biệt được các khả năng này. **Cần kiểm tra có cấu trúc**, từ DN, danh tính bind, thuộc tính yêu cầu, quyền đến kết quả so sánh dưới một tài khoản test có thẩm quyền.

### 4.1. Search thấy entry không đồng nghĩa đọc được mọi field

LDAP server có thể phân biệt quyền tìm kiếm và quyền đọc. Với một số ACL, client có thể:

- **Search** theo `uid` để biết entry phù hợp.
- Nhận **DN** của entry nhưng không được đọc `mail` hay `creatorsName`.
- **Compare** một giá trị theo quyền riêng mà không được phép lấy toàn bộ giá trị.
- Bị từ chối **Modify** dù có thể đọc.

Các hành vi cụ thể khác nhau giữa OpenLDAP, Active Directory và những LDAP server khác. Không mặc định quyền `search` kéo theo quyền `read`, hay quyền `read` kéo theo `write`.

### 4.2. Không có dữ liệu không đồng nghĩa lỗi LDAP

| Hiện tượng | Có thể có nghĩa | Cách phân biệt |
| --- | --- | --- |
| Search trả `[]` | Không khớp filter, sai search base/scope, hoặc quyền search không đủ. | Kiểm tra trên LDAP test với cùng filter/base và principal khác được phép. |
| Entry có DN, nhưng thiếu `modifyTimestamp` | Chưa yêu cầu, server không trả, attribute vắng mặt hoặc ACL ẩn. | Thử yêu cầu **đúng tên** và so sánh quyền. |
| `insufficientAccessRights` (LDAP code 50) | Thao tác bị ACL từ chối. | Đối chiếu quyền theo DN, attribute, operation và bind identity. |
| `noSuchObject` (code 32) | Base/entry không tồn tại hoặc bị che theo chính sách server. | Kiểm tra DN thật, quyền traverse và OU. |
| `invalidCredentials` (code 49) | Bind DN/password/cơ chế xác thực không hợp lệ. | Kiểm tra secret và principal; không kết luận search ACL sai. |
| `undefinedAttributeType` (code 17) | Tên attr không được schema nhận biết ở thao tác tương ứng. | Kiểm tra schema và khả năng server. |
| `CommunicationException`/TLS error | Không kết nối/không duy trì được kênh LDAP. | Kiểm tra URL, certificate, DNS, timeout; đây không phải “không có metadata”. |

Một phương thức service **không nên tự động trả “user không tồn tại” chỉ vì thiếu một operational attribute**. Nếu metadata là điều kiện bắt buộc để nghiệp vụ hoạt động, phải báo lỗi có cấu trúc hoặc đánh dấu trạng thái không xác định, không tự tạo giá trị giả.

## 5. Xác minh Root DSE và tính năng máy chủ

LDAP **Root DSE** là entry đặc biệt tại **DN rỗng** (`""`). Nó có thể cung cấp thông tin như:

| Attribute Root DSE | Ý nghĩa điển hình |
| --- | --- |
| `namingContexts` | Các naming context mà server công bố. |
| `supportedLDAPVersion` | Các phiên bản LDAP protocol được công bố. |
| `supportedControl` | Danh sách OID control server công bố hỗ trợ. |
| `supportedExtension` | Danh sách extended operation được công bố. |
| `supportedFeatures` | Danh sách LDAP features được công bố. |
| `subschemaSubentry` | DN entry chứa thông tin schema mà server công bố. |

RFC 3673 khuyến nghị server hỗ trợ `+` công bố feature OID:

```text
1.3.6.1.4.1.4203.1.5.1
```

Đây là **feature OID** trong `supportedFeatures`, **không phải LDAP control OID**. Không tìm OID này trong `supportedControl` rồi kết luận server không hỗ trợ `+`. Và ngay cả khi feature được công bố, server vẫn có thể che các attribute vận hành theo ACL.

### 5.1. Kiểm tra bằng ldapsearch

```bash
ldapsearch -LLL -x \
  -H "ldaps://ldap.example.org:636" \
  -b "" -s base \
  "(objectClass=*)" \
  namingContexts supportedLDAPVersion \
  supportedFeatures supportedControl supportedExtension
```

Root DSE có thể cho đọc ẩn danh hoặc yêu cầu xác thực tùy policy; nếu anonymous không đủ quyền, dùng `-D ... -W` phù hợp. Cũng không được giả định mọi Root DSE của mọi server đều trả tất cả thuộc tính trong ví dụ.

**Lưu ý về base DN:** `spring.ldap.base=dc=example,dc=org` là đường dẫn gốc của các thao tác Spring LDAP thông thường. Truy vấn Root DSE yêu cầu **DN rỗng tại gốc server**, không phải DN rỗng *tương đối* rồi bị gắn tiếp `dc=example,dc=org`. Khi cần đọc Root DSE, nên dùng LDAP client/JNDI context riêng **không gắn non-empty base DN**.

### 5.2. Ví dụ JNDI đọc Root DSE

```java
import java.util.Hashtable;
import javax.naming.Context;
import javax.naming.directory.Attributes;
import javax.naming.directory.InitialDirContext;

public class RootDseReader {
    public static void main(String[] args) throws Exception {
        Hashtable<String, Object> env = new Hashtable<>();
        env.put(Context.INITIAL_CONTEXT_FACTORY,
                "com.sun.jndi.ldap.LdapCtxFactory");
        env.put(Context.PROVIDER_URL, "ldaps://ldap.example.org:636");
        env.put(Context.SECURITY_AUTHENTICATION, "simple");
        env.put(Context.SECURITY_PRINCIPAL,
                System.getenv("LDAP_BIND_DN"));
        env.put(Context.SECURITY_CREDENTIALS,
                System.getenv("LDAP_BIND_PASSWORD"));
        env.put("com.sun.jndi.ldap.connect.timeout", "3000");
        env.put("com.sun.jndi.ldap.read.timeout", "5000");

        InitialDirContext context = new InitialDirContext(env);
        try {
            Attributes root = context.getAttributes("", new String[] {
                "namingContexts",
                "supportedFeatures",
                "supportedControl"
            });
            System.out.println(
                "Root DSE features available: "
                + (root.get("supportedFeatures") != null)
            );
        } finally {
            context.close();
        }
    }
}
```

Đây là **mã minh họa cho một môi trường đã cấu hình truststore và có biến môi trường credential hợp lệ**. Không in toàn bộ Root DSE/credentials vào log ở production; `supportedFeatures` xuất hiện hay không cũng không chứng minh service account đọc được `createTimestamp` của người dùng.

## 6. Spring LDAP: yêu cầu operational attributes bằng LdapTemplate

Với Spring Boot, `spring-boot-starter-data-ldap` cung cấp hạ tầng Spring LDAP. Ví dụ:

```yaml
spring:
  ldap:
    urls: ${LDAP_URL:ldaps://ldap.example.org:636}
    base: dc=example,dc=org
    username: ${LDAP_BIND_DN}
    password: ${LDAP_BIND_PASSWORD}
```

Mặc định ở ví dụ, `ContextSource` có base DN `dc=example,dc=org`. Vì vậy `LdapTemplate` nhận **DN tương đối** như `ou=people` hoặc `uid=linh,ou=people`.

### 6.1. Cách đơn giản: tìm bằng filter an toàn, yêu cầu tên cụ thể

```java
package com.example.directory;

import static org.springframework.ldap.query.LdapQueryBuilder.query;

import java.util.List;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.stereotype.Service;

@Service
public class DirectoryMetadataService {

    private final LdapTemplate ldapTemplate;

    public DirectoryMetadataService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<PersonMetadata> findByUid(String uid) {
        return ldapTemplate.search(
            query()
                .base("ou=people")
                .attributes(
                    "uid",
                    "cn",
                    "createTimestamp",
                    "modifyTimestamp",
                    "creatorsName",
                    "modifiersName",
                    "entryUUID"
                )
                .where("uid").is(uid),
            (AttributesMapper<PersonMetadata>) attrs ->
                new PersonMetadata(
                    optional(attrs, "uid"),
                    optional(attrs, "cn"),
                    optional(attrs, "createTimestamp"),
                    optional(attrs, "modifyTimestamp"),
                    optional(attrs, "creatorsName"),
                    optional(attrs, "modifiersName"),
                    optional(attrs, "entryUUID")
                )
        );
    }

    private static String optional(Attributes attrs, String name)
            throws javax.naming.NamingException {
        Attribute attribute = attrs.get(name);
        return attribute == null
            ? null
            : (String) attribute.get();
    }

    public record PersonMetadata(
        String uid,
        String commonName,
        String createdAt,
        String modifiedAt,
        String createdByDn,
        String modifiedByDn,
        String entryUuid
    ) {}
}
```

Giải thích:

- `query().base("ou=people")` giới hạn vùng tìm kiếm tương đối với base DN đã cấu hình.
- `.where("uid").is(uid)` xây **LDAP filter an toàn** cho giá trị đầu vào; không ghép `"(uid=" + uid + ")"` thủ công.
- `.attributes(...)` yêu cầu rõ các tên user và operational attributes. Đây là **projection**, không cấp thêm quyền.
- `AttributesMapper` nhận những giá trị server **thực sự trả**; một field bị thiếu vẫn có thể là `null`. Không diễn giải `null` thành “chưa từng sửa”.
- `createTimestamp` và `modifyTimestamp` ở đây được giữ dưới dạng `String` để không giả định parser/format server. `entryUUID` cũng là string khi server trả ở dạng attribute thông thường, nhưng khác với giá trị nhị phân như `objectGUID` trên một số directory.

Trong ứng dụng thật, nên kiểm tra `uid` có thực sự được trả khi nghiệp vụ đòi hỏi hay không. Quyết định xử lý entry vắng hoặc bị ẩn phải dựa trên yêu cầu sản phẩm và quyền read/search thực tế.

### 6.2. Yêu cầu `*` và `+` qua LdapQueryBuilder

Nếu đang chẩn đoán metadata trong LDAP test:

```java
List<Attributes> entries = ldapTemplate.search(
    query()
        .base("ou=people")
        .attributes("*", "+")
        .where("uid").is("linh"),
    (AttributesMapper<Attributes>) attrs -> attrs
);
```

Đoạn này yêu cầu cả user attributes và operational attributes theo RFC 3673. Nhưng **không nên sử dụng `*` và `+` cho mọi HTTP request** khi chỉ cần vài field: có thể làm lộ hoặc tải về nhiều metadata không cần thiết, gây chi phí và khó kiểm soát chính sách bảo mật.

Một số directory không trả các operational attributes đắt đỏ trừ khi được yêu cầu theo tên; nếu cần một thuộc tính cụ thể, dùng `.attributes("uid", "modifyTimestamp")` hoặc cơ chế tương đương.

### 6.3. Dùng SearchControls cho truy vấn chính xác một entry

Khi đã biết DN và muốn đọc duy nhất entry đó, có thể dùng `SearchControls.OBJECT_SCOPE`:

```java
import java.util.List;
import javax.naming.Name;
import javax.naming.directory.Attributes;
import javax.naming.directory.SearchControls;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

Name userDn = LdapNameBuilder.newInstance("ou=people")
    .add("uid", "linh")
    .build();

SearchControls controls = new SearchControls();
controls.setSearchScope(SearchControls.OBJECT_SCOPE);
controls.setReturningAttributes(new String[] {
    "uid", "createTimestamp", "modifyTimestamp", "entryUUID"
});

List<Attributes> results = ldapTemplate.search(
    userDn,
    "(objectClass=*)",
    controls,
    (AttributesMapper<Attributes>) attrs -> attrs
);
```

Ở đây `userDn` là DN **tương đối** với `ContextSource`. `OBJECT_SCOPE` là chỉ kiểm tra entry tại chính DN đó; nó khác `SUBTREE_SCOPE` khi tìm trong một OU nhiều entry. Việc truyền danh sách `returningAttributes` không “nâng quyền” tài khoản bind.

> **Lưu ý về API:** chỉ sử dụng các overload `LdapTemplate.search` phù hợp phiên bản Spring LDAP đang chạy. `LdapQueryBuilder.attributes(...)` và overload `search(..., SearchControls, AttributesMapper)` là hai cách diễn đạt projection/truy vấn; không cần dùng cả hai cho cùng lời gọi.

## 7. Spring Data LDAP Repository và ODM có vai trò gì?

Spring Data LDAP mapping một entry thành Java object:

```java
import javax.naming.Name;
import org.springframework.ldap.odm.annotations.Attribute;
import org.springframework.ldap.odm.annotations.DnAttribute;
import org.springframework.ldap.odm.annotations.Entry;
import org.springframework.ldap.odm.annotations.Id;

@Entry(
    base = "ou=people",
    objectClasses = {
        "top", "person", "organizationalPerson", "inetOrgPerson"
    }
)
public class DirectoryPerson {
    @Id private Name dn;

    @DnAttribute(value = "uid", index = 0)
    @Attribute(name = "uid")
    private String uid;

    @Attribute(name = "cn")
    private String commonName;

    @Attribute(name = "sn")
    private String surname;

    @Attribute(name = "mail")
    private String mail;

    public DirectoryPerson() {}
    // Bổ sung getter/setter trong project thực hành.
}
```

Repository:

```java
import java.util.Optional;
import org.springframework.data.ldap.repository.LdapRepository;

public interface DirectoryPersonRepository
        extends LdapRepository<DirectoryPerson> {
    Optional<DirectoryPerson> findByUid(String uid);
}
```

Repository/ODM thuận tiện cho CRUD và truy vấn người dùng, nhưng:

1. `findByUid` chỉ mô tả truy vấn theo property `uid`, **không** tự cam kết trả mọi operational attribute.
2. Các attribute do server quản lý thường là **read-only**. Không thêm field metadata vào entity rồi mặc định `save()` được phép ghi chúng.
3. Một entity có `@Entry.base` không phải ranh giới bảo mật. Nếu principal bind có quyền lớn, code khác vẫn có thể truy cập ngoài vùng dự định.
4. Khi muốn một bản chụp metadata chỉ để kiểm tra, dùng `LdapTemplate` với **projection rõ ràng** và DTO riêng thường giúp kiểm soát tốt hơn.

Không nhầm ID `@Id Name` trong ODM với `entryUUID` do LDAP server cung cấp. DN có thể thay đổi khi rename/move, còn UUID do server cấp có mục đích khác; những chi tiết đồng bộ giữa chúng phụ thuộc server.

## 8. Kiểm tra chính xác tài khoản mà LDAP server nhận diện

Trong nhiều ứng dụng, người dùng HTTP được xác thực bằng Spring Security, nhưng các lời gọi `LdapTemplate` lại dùng một **service bind DN** chung. Khi truy cập bị chặn, phải biết **LDAP principal thật**, không suy ra nó từ người dùng đang đăng nhập vào API.

### 8.1. Kiểm tra cấu hình phía Spring

```yaml
spring:
  ldap:
    urls: ${LDAP_URL:ldaps://ldap.example.org:636}
    base: dc=example,dc=org
    username: ${LDAP_BIND_DN}
    password: ${LDAP_BIND_PASSWORD}
```

Kiểm tra biến môi trường, active profile, bean `ContextSource` tự tạo, connection pool và việc ứng dụng có nhiều `LdapTemplate` được cấu hình với **bind identity khác nhau** hay không.

**Tuyệt đối không log password** để debug. Nếu cần chẩn đoán danh tính, log một alias an toàn như `ldapPrincipal=people-reader` thay vì in đầy đủ secret hay file cấu hình.

### 8.2. Dùng ldapwhoami

Nếu LDAP client và server hỗ trợ **Who Am I? Extended Operation**:

```bash
ldapwhoami -x \
  -H "ldaps://ldap.example.org:636" \
  -D "uid=svc-reader,ou=service-accounts,dc=example,dc=org" -W
```

Ví dụ response có thể là:

```text
dn:uid=svc-reader,ou=service-accounts,dc=example,dc=org
```

Đây là cách xác minh **authorization identity** server thấy sau bind, nếu server hỗ trợ operation và principal có quyền dùng nó. Không suy ra một danh tính xác thực thành công sẽ có quyền search/write ở mọi OU.

### 8.3. Quyền search, compare, read và write

| Khả năng | Ví dụ kiểm tra | Điều cần hiểu |
| --- | --- | --- |
| Bind/authenticate | `ldapwhoami` hoặc thao tác bind hợp lệ | Xác thực thành công **không** bao gồm quyền đọc. |
| Search | `ldapsearch -b ou=people "(uid=linh)"` | Có thể biết kết quả khớp nhưng không đọc được mọi attribute. |
| Compare | `ldapcompare DN "uid:linh"` | Có thể biết đúng/sai một giá trị; không đồng nghĩa đọc toàn bộ giá trị. |
| Read | Yêu cầu `uid`, `mail`, `modifyTimestamp` | Thường bị giới hạn theo DN/attribute và danh tính bind. |
| Modify | `ldapmodify` trong directory test | Bị chặn đối với read-only account, ngay cả khi Search thành công. |
| Delete/Rename | Thao tác thay đổi entry/đường dẫn | Có thể cần quyền riêng ở entry/parent theo directory. |

Thang quyền chi tiết và ý nghĩa cụ thể phụ thuộc LDAP server; OpenLDAP, Active Directory và các directory khác có mô hình ACL/ACI khác nhau. Đừng viết ứng dụng dựa trên giả định “được search thì nhất định được read”.

## 9. Cách kiểm tra quyền server an toàn, có thể tái lập

### 9.1. Chuẩn bị ma trận kiểm chứng

Giả sử tài khoản `svc-reader` chỉ cần:

- Tìm theo `uid` dưới `ou=people`.
- Đọc `uid`, `cn` và `mail`.
- Đọc `modifyTimestamp` **nếu được phê duyệt**, phục vụ kiểm tra thay đổi.
- **Không** được sửa email, xóa user hoặc truy cập `ou=service-accounts`.

Ma trận:

| Test | Kỳ vọng cho reader | Mức kiểm chứng |
| --- | --- | --- |
| Bind qua TLS | Thành công với secret hợp lệ. | Xác thực và bảo mật kênh. |
| Search `(uid=linh)` trong `ou=people` | Trả entry phù hợp. | Search + phạm vi DN. |
| Read `cn`/`mail` | Trả giá trị nếu được ACL cho phép. | Read theo attribute. |
| Read `modifyTimestamp` | Trả hoặc không trả theo policy đã định. | Operational attribute + ACL. |
| Search subtree ngoài phạm vi | Bị chặn hoặc không nhìn thấy dữ liệu. | Phân vùng truy cập. |
| Modify `mail` trên user thử nghiệm | Bị từ chối. | Negative test quyền write. |
| Delete user thử nghiệm | Bị từ chối. | Negative test quyền delete. |
| Đọc thuộc tính mật khẩu | Không lộ giá trị. | Bảo vệ attribute nhạy cảm. |

Test quyền cần xác minh **kết quả thực tế**, không chỉ việc Java method có được gọi. Với read bị chặn, server đôi khi trả **thiếu attribute hoặc không có entry** thay vì ném exception. Với write bị chặn, thường có LDAP result code **50 (insufficientAccessRights)**, nhưng cách bọc exception phụ thuộc API và server.

### 9.2. Đối chiếu cùng DN, filter, thuộc tính và server

Khi reader không thấy `modifyTimestamp`, người vận hành có thể đối chiếu với một **tài khoản kiểm thử có thẩm quyền** (trên directory test):

```text
Reader:
  host: ldap-test.example.org:636
  base: uid=linh,ou=people,dc=example,dc=org
  scope: base
  attrs: uid,modifyTimestamp
  result: uid có; modifyTimestamp bị thiếu

Auditor/test identity:
  host: ldap-test.example.org:636
  base: uid=linh,ou=people,dc=example,dc=org
  scope: base
  attrs: uid,modifyTimestamp
  result: uid có; modifyTimestamp có

Giả thuyết hợp lý: khác biệt quyền read attribute.
Vẫn phải xem ACL và các rule riêng của server để xác nhận.
```

**Đừng tự chuyển ứng dụng production sang admin bind** chỉ để metadata hiện ra. Thay vào đó, người quản trị directory cần xác định quyền được phê duyệt rồi cập nhật ACL tối thiểu và kiểm thử lại.

### 9.3. Công cụ ldapcompare

Ví dụ trên directory test:

```bash
ldapcompare -x \
  -H "ldaps://ldap-test.example.org:636" \
  -D "uid=svc-reader,ou=service-accounts,dc=example,dc=org" -W \
  "uid=linh,ou=people,dc=example,dc=org" "uid:linh"
```

Nếu server trả compare true/false, điều đó chứng minh khả năng **compare trong điều kiện cụ thể**, không chứng minh service account có quyền đọc `uid` dưới mọi ngữ cảnh. Một kết quả bị từ chối cũng có thể là do ACL hoặc loại attribute và chính sách server.

### 9.4. Không thử ghi trái phép lên dữ liệu thật

Để kiểm chứng read-only account bị chặn khi sửa, chỉ dùng **entry test riêng** và directory test:

```ldif
dn: uid=lab-user,ou=people,dc=example,dc=org
changetype: modify
replace: mail
mail: should-not-be-written@example.org
```

```bash
ldapmodify -x \
  -H "ldaps://ldap-test.example.org:636" \
  -D "uid=svc-reader,ou=service-accounts,dc=example,dc=org" -W \
  -f forbidden-modify.ldif
```

Kỳ vọng: server **từ chối** Modify; kiểm tra bằng identity được phép xác nhận `mail` của fixture **không đổi**. Nếu lệnh thành công, ACL của reader đã quá rộng, cần dừng và sửa chính sách trên test server. Không thực hiện test này trên entry người thật hay production.

## 10. Integration test Spring LDAP với hai mức quyền

Unit test có thể mock repository và assert service gọi đúng query. Nhưng unit test **không thể chứng minh** server áp ACL, trả operational attributes hoặc hỗ trợ `+`. Cần integration test với LDAP server/ACL thật và credentials thử nghiệm.

Giả sử Spring Test có bean `readerLdapTemplate` cấu hình tài khoản chỉ đọc, entry fixture `uid=lab-reader` đã tồn tại. Ví dụ JUnit 5:

```java
package com.example.directory;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.util.List;
import javax.naming.Name;
import javax.naming.directory.Attribute;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.SearchControls;
import javax.naming.directory.ModificationItem;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.ldap.NoPermissionException;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

@SpringBootTest
class OperationalAttributeAccessIT {

    @Autowired
    @Qualifier("readerLdapTemplate")
    private LdapTemplate reader;

    private final Name fixtureDn =
        LdapNameBuilder.newInstance("ou=people")
            .add("uid", "lab-reader")
            .build();

    @Test
    void readerSeesApprovedAttributes() {
        List<String> names = reader.search(
            fixtureDn, "(objectClass=*)",
            SearchControls.OBJECT_SCOPE,
            new String[] {"uid", "cn", "modifyTimestamp"},
            (AttributesMapper<String>) attrs ->
                (String) attrs.get("uid").get()
        );

        assertThat(names).containsExactly("lab-reader");
        // modifyTimestamp có/không tùy ACL được duyệt:
        // kiểm chứng riêng với test data và policy của server.
    }

    @Test
    void readerCannotModifyMail() {
        ModificationItem item = new ModificationItem(
            DirContext.REPLACE_ATTRIBUTE,
            new BasicAttribute(
                "mail", "forbidden-change@example.org"
            )
        );

        assertThatThrownBy(() ->
            reader.modifyAttributes(
                fixtureDn, new ModificationItem[] {item}
            )
        ).isInstanceOf(NoPermissionException.class);
    }
}
```

Test này yêu cầu:

- Directory test có OU và entry fixture; không chạy trên production.
- Tài khoản reader có quyền search/read `uid`; **không** có quyền write `mail`.
- Kết quả expected dựa trên ACL thật, không áp dụng vô điều kiện cho mọi LDAP server.
- Kiểm tra riêng `modifyTimestamp` khi chính sách yêu cầu nó được phép đọc; field vắng không mặc nhiên là test failure.
- Sau một negative modify test, xác minh trạng thái entry bằng tài khoản test có thẩm quyền.

## 11. Hiểu quyền server không đồng nghĩa phát hiện “effective rights” tự động

Không có một API `LdapRepository.hasPermission(dn, "modify")` phổ quát và đáng tin cậy cho mọi LDAP directory. Các server có thể cung cấp **effective rights controls**, ACI introspection hoặc công cụ quản trị riêng, nhưng đó là **tính năng tùy sản phẩm**, không nằm trong CRUD repository chuẩn.

| Cách kiểm tra | Giá trị | Giới hạn |
| --- | --- | --- |
| Xem ACL/ACI/server policy | Biết nguyên nhân và phạm vi quyền theo cấu hình. | Cần quyền quản trị/đọc policy và hiểu rule inheritance. |
| Thử một thao tác **được phép** | Chứng minh đường đi làm việc trong hoàn cảnh cụ thể. | Không bao quát mọi DN/attribute. |
| Negative test trên fixture riêng | Phát hiện quyền quá rộng. | Không được thực hiện trên dữ liệu production. |
| Server-specific effective rights | Có thể thấy quyền hiệu lực mà server hỗ trợ công bố. | Phụ thuộc vendor, OID, ACL và phiên bản; không phải chuẩn chung. |
| Đọc Root DSE `supportedControl` | Biết server công bố control nào. | Công bố tính năng **không** đồng nghĩa được phép sử dụng hoặc có quyền đọc dữ liệu. |

Một ACL có thể cho phép đọc `uid` tại một entry nhưng cấm `uid` tại nhánh khác. Kiểm tra một user thành công không cho phép kết luận tài khoản reader “có quyền đọc mọi user”.

### 11.1. Quyền được xét ở thời điểm thao tác

Giữa hai lần gọi `LdapTemplate`, quyền có thể thay đổi do quản trị viên sửa ACL, entry được chuyển OU, token/security group thay đổi hoặc ứng dụng đổi bind identity. Vì vậy:

- Không cache vô hạn kết quả “đã được phép”.
- Không thay thế ACL server bằng cờ Boolean lưu trong ứng dụng.
- Khi thao tác bị từ chối, giữ nguyên lỗi nghiệp vụ/backend phù hợp và không tăng quyền tự động.
- Với nhiều endpoint LDAP hoặc failover, kiểm tra quyền trên server đang thực sự phục vụ request.

## 12. Kiểm tra thuộc tính operational khi dùng Active Directory

Không được giả định mọi directory đều dùng `entryUUID`, `createTimestamp` và `modifyTimestamp`. Ví dụ một số triển khai Active Directory thường làm việc với:

- `whenCreated`, `whenChanged`: thời điểm theo mô hình attribute của Active Directory.
- `objectGUID`: định danh đối tượng thường được nhận dưới dạng dữ liệu **binary**, cần chuyển đổi theo format của AD.
- `uSNChanged`: số phiên bản thay đổi theo semantics của domain controller, không phải timestamp và không nên dùng như số phiên bản toàn cục của mọi DC.

Các thuộc tính này **không được tự coi là tương đương về schema, cách trả dữ liệu hay quyền** với `entryUUID`/`modifyTimestamp` trên OpenLDAP. Hãy đọc Root DSE, schema và tài liệu server cụ thể; yêu cầu rõ tên attribute, so sánh kết quả bằng bind identity được cấp và xử lý kiểu dữ liệu chính xác.

Nếu ứng dụng phải hỗ trợ nhiều vendor, nên xây lớp adapter/DTO:

```text
LDAP server A: entryUUID, modifyTimestamp
LDAP server B: objectGUID, whenChanged
                |
                v
        DirectoryEntryMetadata
           id, modifiedAt
```

Lớp adapter chỉ nên biến đổi dữ liệu khi đã xác định được semantics và độ tin cậy; không gán `0` hoặc ngày hiện tại cho metadata không đọc được vì có thể làm hỏng quá trình đồng bộ.

## 13. Bảo mật thông tin metadata và hiệu năng search

### 13.1. Vì sao operational attributes có thể nhạy cảm?

`creatorsName` và `modifiersName` có thể tiết lộ DN của nhân sự, service account, OU nội bộ hoặc quy trình quản trị. `entryUUID` có thể hỗ trợ liên kết dữ liệu giữa các hệ thống. `subschemaSubentry` hay Root DSE có thể lộ metadata của hạ tầng.

Vì vậy:

- Chỉ yêu cầu **attribute cần thiết** cho nghiệp vụ.
- Không trả raw `Attributes` hoặc `*`/`+` trực tiếp qua REST cho người dùng cuối.
- Áp dụng ACL theo **bind identity và attribute** trên LDAP server.
- Dùng DTO allowlist và phân quyền HTTP như lớp bảo vệ bổ sung, **không thay cho ACL**.
- Không log hàng loạt full DN, email, metadata hay userPassword trong dữ liệu chẩn đoán.

### 13.2. Tối ưu search

Không chạy `subtree search` với `(objectClass=*)` và `*`/`+` trên toàn directory chỉ để xem “có những gì”. Điều này có thể trả rất nhiều entry và attribute, đụng giới hạn server hoặc làm chậm dịch vụ.

Thay vào đó:

1. Chọn **base DN hẹp**, ví dụ `ou=people`.
2. Dùng filter theo UID, thuộc tính có index phù hợp và `LdapQueryBuilder` để escape dữ liệu.
3. Chỉ yêu cầu `uid`, `modifyTimestamp` hoặc đúng các attribute cần dùng.
4. Dùng `OBJECT_SCOPE` khi đã biết DN; không cần quét cả subtree.
5. Thiết lập time limit/count limit phù hợp; với tìm kiếm lớn, cân nhắc LDAP paging controls và connection lifecycle, không mặc định `Pageable` của JPA áp dụng.
6. Quan sát kết quả bất thường: số entry, thời gian, thiếu field, lỗi quyền, timeout.

Quyền **không** phải công cụ tiết kiệm băng thông. Mục tiêu là cấp quyền tối thiểu ở server và thiết kế projection/search nhỏ ở client, đồng thời.

## 14. Quy trình chẩn đoán từng bước

Khi `LdapTemplate` không trả `modifyTimestamp` hoặc một thuộc tính vận hành khác:

1. **Xác nhận entry thực:** dùng `ldapsearch -b FULL_DN -s base` trên directory test với tài khoản có quyền kiểm tra; ghi lại DN.
2. **Xác nhận base DN của Spring:** `spring.ldap.base=dc=example,dc=org` nghĩa là code thường truyền `uid=linh,ou=people`, không lặp full DN.
3. **Xác nhận request projection:** mặc định thường chỉ user attributes; cần thêm `modifyTimestamp` hoặc `+`.
4. **Xác nhận Root DSE/capability:** kiểm tra `supportedFeatures` OID RFC 3673 và tài liệu server, nhưng đừng suy luận khả năng đọc.
5. **Xác nhận principal:** kiểm tra `LDAP_BIND_DN`/`ContextSource`, `ldapwhoami` nếu hỗ trợ; tránh nhầm HTTP user với bind user.
6. **So sánh cùng truy vấn dưới account được phép:** cùng endpoint, DN, scope, filter, danh sách attribute; khác nhau chỉ ở identity.
7. **Kiểm tra ACL:** search, read theo OU/entry/attribute; một số server ẩn attribute thay vì ném exception.
8. **Kiểm tra vendor/schema:** thuộc tính có tên khác hoặc không tồn tại trên server? Attribute binary hay string?
9. **Kiểm thử âm tính ở directory test:** tài khoản reader phải bị chặn Modify và truy cập subtree nhạy cảm.
10. **Sửa đúng lớp:** projection, mapping, bind config, ACL tối thiểu hoặc adapter vendor; không dùng admin credential để “chữa” mọi lỗi.

### Bảng nhận biết nguyên nhân nhanh

| Triệu chứng | Khả năng ưu tiên kiểm tra | Không nên làm |
| --- | --- | --- |
| `uid` có nhưng `modifyTimestamp` không có | Projection, ACL, server feature. | Kết luận entry chưa từng được sửa. |
| `+` không trả gì | Server không hỗ trợ, ACL, hoặc attribute cần yêu cầu tên riêng. | Tự cho rằng server có lỗi nặng. |
| Search user trả danh sách rỗng | Filter, scope, base DN, ACL search. | Mặc định tạo lại user cùng DN. |
| Bind thành công nhưng Modify bị cấm | Quyền read/search có, write không có. | Nâng tài khoản lên admin. |
| Root DSE được đọc nhưng entry không thấy | Root DSE và entry có ACL riêng. | Suy ra có quyền đọc mọi dữ liệu. |
| Lỗi TLS hoặc `CommunicationException` | Kênh truyền/certificate/timeout. | Trả `404 user not found`. |
| `objectGUID` không parse được thành string | Dữ liệu binary/vendored attribute. | Ép `(String)` vô điều kiện. |

## 15. Bài tập ứng dụng và checklist

### Bài tập

1. Với entry `uid=linh`, viết ba lệnh `ldapsearch` yêu cầu (a) user attributes, (b) operational attributes, (c) chỉ `uid` và `modifyTimestamp`. Dự đoán kết quả nếu reader chỉ có quyền đọc `uid`.
2. Giải thích vì sao `*` và `+` không giống nhau; tại sao kết quả `+` có thể không chứa một operational attribute dù server hỗ trợ RFC 3673?
3. Viết phương thức Spring LDAP tìm một user theo UID và trả DTO `{uid, createdAt, modifiedAt}`; dùng `LdapQueryBuilder` và xử lý field bị thiếu.
4. Tạo truy vấn `OBJECT_SCOPE` cho DN cụ thể bằng `SearchControls`; so sánh phạm vi và chi phí với `SUBTREE_SCOPE` trên `ou=people`.
5. Dùng `ldapwhoami` để xác nhận identity của service account; thiết kế test chứng minh có quyền search nhưng không có quyền Modify trên fixture.
6. So sánh `entryUUID` trên một directory với `objectGUID` của Active Directory; nêu lý do không nên ép cả hai theo một kiểu string đơn giản.
7. Một ứng dụng nhận `modifyTimestamp=null`, nhưng tài khoản auditor đọc được metadata. Hãy phân tích các bước phân biệt lỗi projection và lỗi ACL, không dùng admin bind trong production.
8. Giải thích vì sao kết quả `supportedControl` hoặc `supportedFeatures` của Root DSE không phải bằng chứng service account được phép sửa entry.

### Checklist nghiệm thu

- [ ] Hiểu DN, RDN, base DN và vị trí của entry trong LDAP tree.
- [ ] Phân biệt được user attributes và operational attributes.
- [ ] Biết cách yêu cầu `*`, `+` và tên attribute tường minh.
- [ ] Không đồng nhất `null`/missing attribute với “không có quyền”.
- [ ] Không đồng nhất search kết quả rỗng với “entry chắc chắn không tồn tại”.
- [ ] Kiểm tra được Root DSE và hiểu phạm vi của `supportedFeatures`.
- [ ] Sử dụng `LdapTemplate`/`LdapQueryBuilder` để đọc metadata an toàn.
- [ ] Hiểu khác biệt giữa permission của HTTP principal và LDAP bind identity.
- [ ] Có test được phép và test bị từ chối trên directory thử nghiệm.
- [ ] Không dùng tài khoản admin, kết nối plaintext hoặc raw metadata rộng trong ứng dụng production.

## 16. Tài liệu tham khảo

- [RFC 4511 — LDAP Protocol](https://www.rfc-editor.org/rfc/rfc4511): SearchRequest, trả attribute, LDAP result code và thao tác directory.
- [RFC 4512 — LDAP Directory Information Models](https://www.rfc-editor.org/rfc/rfc4512): phân loại attribute theo schema, operational attributes và Root DSE.
- [RFC 3673 — All Operational Attributes](https://www.rfc-editor.org/rfc/rfc3673): `+`, giới hạn trả kết quả và feature OID.
- [RFC 4530 — LDAP entryUUID Operational Attribute](https://www.rfc-editor.org/rfc/rfc4530): thuộc tính `entryUUID`.
- [RFC 4532 — LDAP Who Am I? Operation](https://www.rfc-editor.org/rfc/rfc4532): xác định authorization identity sau bind.
- [RFC 4513 — LDAP Authentication Methods and Security Mechanisms](https://www.rfc-editor.org/rfc/rfc4513): bind và bảo mật giao tiếp.
- [Spring LDAP — Advanced Queries](https://docs.spring.io/spring-ldap/reference/query-builder-advanced.html): `LdapQueryBuilder`, search scope và attributes projection.
- [Spring LDAP — LdapTemplate API](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/core/LdapTemplate.html): `search`, `AttributesMapper` và `SearchControls`.
- [Spring Data LDAP Reference](https://docs.spring.io/spring-data/ldap/reference/): ODM và repository, phạm vi sử dụng với LDAP.
- [OpenLDAP Administrator's Guide — Access Control](https://www.openldap.org/doc/admin24/access-control.html): quyền search/read/write, rule ACL và hiệu ứng khi quyền không đủ.
