# Thực thi thao tác cấp thấp qua ContextExecutor

Trong **Spring Data LDAP**, phần lớn chức năng thông thường có thể giải quyết bằng **LdapRepository** hoặc các phương thức tiện ích của **LdapTemplate** như `search`, `lookup`, `bind`, `modifyAttributes`, `rename` và `unbind`. Tuy nhiên, đôi khi ứng dụng cần gọi trực tiếp một phương thức của **JNDI DirContext** chưa có overload tương ứng trong `LdapTemplate`, hoặc cần thực hiện một số bước liên quan trên **cùng một context**. **ContextExecutor<T>** là cơ chế extension dành cho những tình huống như vậy.

Bài học thuộc chương **LdapTemplate** giải thích khi nào nên sử dụng `ContextExecutor`, cách chọn **executeReadOnly** hoặc **executeReadWrite**, vòng đời context, việc xử lý `NamingException`, các ví dụ với DN/attribute và một thao tác LDAP Modify cấp thấp. Đồng thời, bài chỉ rõ giới hạn về **transaction**, **ACL**, **connection pooling**, **LDAP filter injection**, tính nhất quán và kiểm thử trên directory.

> **Quy tắc chọn API:** Hãy dùng phương thức cấp cao của `LdapTemplate` hoặc repository khi đã có phương thức phù hợp. `ContextExecutor` dành cho yêu cầu đặc biệt ở cấp **DirContext**, không phải con đường mặc định để viết lại mọi lệnh LDAP.

## 1. ContextExecutor nằm ở đâu trong kiến trúc Spring LDAP?

~~~mermaid
flowchart TD
    A["Ứng dụng Spring Boot"] --> B["Service nghiệp vụ"]
    B --> C["Spring Data LDAP / LdapRepository"]
    B --> D["LdapTemplate"]
    C --> D
    D --> E["executeReadOnly / executeReadWrite"]
    E --> F["ContextExecutor<T> callback"]
    F --> G["JNDI DirContext"]
    G --> H[("LDAP directory: DN, schema, ACL, entry")]
    I["ContextSource: endpoint, base DN, bind DN, TLS, pooling"] -. "Cấp và thu hồi context" .-> E
~~~

Phân biệt trách nhiệm:

| Thành phần | Vai trò | Ví dụ |
| --- | --- | --- |
| **LdapRepository** | Ánh xạ một entry theo **@Entry**, **@Id**, **@Attribute** thành Java object | `findByUid("linh")` |
| **LdapTemplate** | Cung cấp API CRUD/search và quản lý context cho các LDAP operation | `lookup(...)`, `search(...)`, `modifyAttributes(...)` |
| **ContextSource** | Tạo context với endpoint, base DN, bind identity; có thể có pool | `LdapContextSource` |
| **ContextExecutor<T>** | Nhận **DirContext** đã được cấp để gọi thao tác JNDI tùy chỉnh | `ctx.lookupLink(...)` |
| **JNDI DirContext** | Giao diện Java cho LDAP lookup, search, binding và sửa thuộc tính | `getAttributes`, `modifyAttributes`, `rename` |
| **LDAP server** | Áp dụng DN, objectClass/schema, filter, ACL và LDAP result codes | OpenLDAP, Active Directory |

**ContextExecutor không tự mở socket, không tự bind và không tự đóng context.** Nó được `LdapTemplate` gọi sau khi template lấy context từ **ContextSource**. Kết thúc callback, `LdapTemplate` quản lý việc đóng/trả context, kể cả khi lời gọi JNDI báo ngoại lệ.

## 2. Hợp đồng API của ContextExecutor<T>

Spring LDAP định nghĩa một functional interface (diễn giải rút gọn):

~~~java
import javax.naming.NamingException;
import javax.naming.directory.DirContext;

@FunctionalInterface
public interface ContextExecutor<T> {
    T executeWithContext(DirContext ctx) throws NamingException;
}
~~~

Interface thực dùng từ thư viện là **org.springframework.ldap.core.ContextExecutor**, không cần tự tạo bản sao trong ứng dụng. Phần mã ở trên chỉ trình bày hợp đồng để người học nhìn rõ kiểu tham số và ngoại lệ.

`T` là kết quả callback trả về cho người gọi. Nó có thể là **String**, **Boolean**, một **record/DTO**, **Attributes** đã xử lý hoặc **Void** nếu thao tác chỉ có side effect. Tính generic cho phép code sau đây không cần ép kiểu từ Object:

~~~java
import org.springframework.ldap.core.ContextExecutor;

ContextExecutor<String> executor = ctx -> {
    return ctx.getNameInNamespace();
};

String contextBase = ldapTemplate.executeReadOnly(executor);
~~~

Mã nằm trong một method có **ldapTemplate** đã được inject. `ctx.getNameInNamespace()` là một phương thức kế thừa từ **Context**; tùy provider và ContextSource, nó cung cấp tên đang gắn với context, không nhất thiết là DN của entry đang tìm. Để lấy DN của một entry cụ thể, nên dùng kết quả **SearchResult** hoặc mapper có thông tin DN.

### 2.1. Hai phương thức execute của LdapTemplate

Các chữ ký sử dụng:

~~~java
<T> T executeReadOnly(ContextExecutor<T> executor);
<T> T executeReadWrite(ContextExecutor<T> executor);
~~~

| Phương thức | Lấy context từ | Dành cho |
| --- | --- | --- |
| **executeReadOnly(...)** | **ContextSource.getReadOnlyContext()** | Lookup, đọc thuộc tính, thao tác chỉ đọc không có overload thuận tiện |
| **executeReadWrite(...)** | **ContextSource.getReadWriteContext()** | Thao tác có khả năng ghi hoặc một chuỗi thao tác đặc biệt |

**Read-only không có nghĩa LDAP server tự từ chối mọi ghi chỉ vì tên phương thức.** Quyền thực tế được quyết định bởi **bind identity, ACL, server và cách ContextSource cấp context**. Không dùng việc chọn executeReadOnly như biện pháp thay thế ACL. Với thao tác có side effect, hãy chủ động chọn read-write và dùng tài khoản có đúng quyền tối thiểu.

### 2.2. Không phải SearchExecutor

Spring LDAP có một extension point khác:

| Interface | Callback làm gì? | API nên gọi |
| --- | --- | --- |
| **ContextExecutor<T>** | Thực hiện một thao tác tùy chỉnh trên **DirContext**, trả **T** | `executeReadOnly` / `executeReadWrite` |
| **SearchExecutor** | Thực thi một **LDAP search** tùy chỉnh, trả **NamingEnumeration** cho handler quản lý | `LdapTemplate.search(SearchExecutor, NameClassPairCallbackHandler)` |
| **AttributesMapper<T>** | Ánh xạ **Attributes** của từng kết quả search sang **T** | `LdapTemplate.search(..., mapper)` |
| **ContextMapper<T>** | Ánh xạ entry/context và DN sang **T** | `LdapTemplate.search(..., mapper)` |

Javadoc của `LdapTemplate.executeReadOnly` nêu rõ nó **không nhằm dùng cho tìm kiếm thông thường**; dùng các overload `search` hoặc **SearchExecutor** nếu cần tùy biến yêu cầu Search. Điều này giúp thư viện quản lý **NamingEnumeration**, xử lý kết quả từng entry, callback mapper và chính sách tìm kiếm đúng mục đích.

## 3. Lifecycle: LdapTemplate làm gì trước và sau callback?

Cấu trúc xử lý (pseudocode theo ý nghĩa, không phải bản sao source code):

~~~java
public <T> T executeReadOnly(ContextExecutor<T> executor) {
    DirContext context = contextSource.getReadOnlyContext();
    try {
        return executor.executeWithContext(context);
    } catch (javax.naming.NamingException ex) {
        throw convertToSpringLdapException(ex);
    } finally {
        closeOrReturnToPool(context);
    }
}
~~~

Hai hàm **convertToSpringLdapException(...)** và **closeOrReturnToPool(...)** chỉ là tên **pseudocode**, không phải API có sẵn để gọi. Thực tế Spring LDAP dùng cơ chế dịch ngoại lệ và **LdapUtils.closeContext(...)**. `executeReadWrite` tuân theo nguyên tắc tương tự nhưng lấy read-write context.

Những cam kết hữu ích:

1. **Lấy context:** Template dùng **ContextSource** đang được cấu hình với host, port, TLS, base DN, bind DN hoặc pooling.
2. **Gọi callback:** `executeWithContext(ctx)` được thực thi **đồng bộ** trên thread hiện tại.
3. **Dịch ngoại lệ:** `javax.naming.NamingException` phát sinh từ callback được chuyển sang họ ngoại lệ runtime của Spring LDAP.
4. **Thu hồi context:** Trong **finally**, context được đóng hoặc trả pool; người viết callback không phải đóng chính `ctx`.
5. **Trả kết quả:** `T` đi từ callback về service; kết quả nên là giá trị Java đã hoàn tất, không còn lệ thuộc context.

**Quan trọng:** Nếu callback chỉ trả về một `NamingEnumeration` đang mở hoặc một `DirContext` con mà client cần dùng tiếp, context cha đã bị đóng sau khi callback trả về. Việc sử dụng tài nguyên lười (**lazy**) bên ngoài callback có thể gây lỗi hoặc leak. Hãy materialize thành DTO trong callback, và đóng các enumeration/context con do chính callback tạo.

## 4. Cấu hình tối thiểu cho ví dụ LDAP

Giả sử directory lab:

~~~text
dc=lab,dc=example
├── ou=people
│   ├── uid=linh
│   └── uid=an
└── ou=groups
    └── cn=developers
~~~

LDIF mẫu của người dùng:

~~~ldif
dn: uid=linh,ou=people,dc=lab,dc=example
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: linh
cn: Linh Nguyen
sn: Nguyen
mail: linh@lab.example
~~~

Entry nhóm:

~~~ldif
dn: cn=developers,ou=groups,dc=lab,dc=example
objectClass: top
objectClass: groupOfNames
cn: developers
member: uid=linh,ou=people,dc=lab,dc=example
~~~

Những LDIF này dùng dữ liệu giả. Khi import vào server lab, phải tạo suffix và OU cha trước; nếu entry cha đã tồn tại thì không import trùng. **groupOfNames** thường yêu cầu ít nhất một thuộc tính **member**, nên dữ liệu mẫu đã có một thành viên.

Ví dụ cấu hình Spring Boot dùng **spring-boot-starter-data-ldap**:

~~~yaml
spring:
  ldap:
    urls: "ldaps://ldap.lab.example:636"
    base: "dc=lab,dc=example"
    username: "uid=reader,ou=services,dc=lab,dc=example"
    password: "${LDAP_BIND_PASSWORD}"
    base-environment:
      "[com.sun.jndi.ldap.connect.timeout]": "3000"
      "[com.sun.jndi.ldap.read.timeout]": "5000"
~~~

Giả định tài khoản reader được tạo riêng, có mật khẩu trong nguồn secret an toàn và có quyền đọc được cấp theo **ACL**. Để thử ví dụ ghi, cần một tài khoản hoặc ContextSource read-write riêng được cấp quyền phù hợp trong lab. Không dùng tài khoản admin hoặc ghi mật khẩu vào mã chỉ để làm ví dụ hoạt động.

**Base DN trong ContextExecutor:** Với **ContextSource base = dc=lab,dc=example**, đường dẫn truyền cho `ctx.getAttributes(...)`, `ctx.lookupLink(...)` hoặc `ctx.modifyAttributes(...)` thường là **DN tương đối với base** như `uid=linh,ou=people`. Trong **ldapsearch -b**, ngược lại, thường dùng full DN **uid=linh,ou=people,dc=lab,dc=example**.

## 5. Ví dụ đọc cấp thấp: lấy attributes theo DN

Đây là ví dụ rõ nhất để thấy callback nhận **DirContext**. Dù `LdapTemplate` đã có cách lookup attribute thuận tiện hơn, ví dụ minh họa việc tự điều khiển JNDI `getAttributes`.

~~~java
import java.util.Optional;
import javax.naming.NamingException;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;
import org.springframework.ldap.core.ContextExecutor;
import org.springframework.ldap.core.LdapTemplate;

public final class PersonAttributeReader {
    private final LdapTemplate ldapTemplate;

    public PersonAttributeReader(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public record PersonSummary(
        String uid,
        String commonName,
        String email
    ) {}

    public PersonSummary readPerson(String relativeDn) {
        ContextExecutor<PersonSummary> executor = ctx -> {
            Attributes attributes = ctx.getAttributes(
                relativeDn,
                new String[]{"uid", "cn", "mail"}
            );

            return new PersonSummary(
                requiredString(attributes, "uid"),
                requiredString(attributes, "cn"),
                optionalString(attributes, "mail").orElse(null)
            );
        };
        return ldapTemplate.executeReadOnly(executor);
    }

    private static String requiredString(
            Attributes attrs, String id) throws NamingException {
        Attribute attr = attrs.get(id);
        if (attr == null || attr.size() != 1) {
            throw new IllegalStateException(
                "Expected one visible LDAP attribute: " + id);
        }
        Object raw = attr.get();
        if (!(raw instanceof String text)) {
            throw new IllegalStateException(
                "LDAP attribute must be textual: " + id);
        }
        return text;
    }

    private static Optional<String> optionalString(
            Attributes attrs, String id) throws NamingException {
        Attribute attr = attrs.get(id);
        if (attr == null || attr.size() == 0) {
            return Optional.empty();
        }
        Object raw = attr.get();
        if (!(raw instanceof String text)) {
            throw new IllegalStateException(
                "LDAP attribute must be textual: " + id);
        }
        return Optional.of(text);
    }
}
~~~

Ví dụ gọi:

~~~java
PersonAttributeReader.PersonSummary data =
    reader.readPerson("uid=linh,ou=people");
~~~

**Giải thích kỹ thuật:**

- **ContextExecutor<PersonSummary>** khai báo kiểu kết quả để tránh ép kiểu bằng tay.
- **ctx.getAttributes(relativeDn, ids)** yêu cầu ba attribute cụ thể. Việc chỉ yêu cầu vài field giúp giảm dữ liệu truyền qua mạng.
- **requiredString(...)** cố ý kiểm tra **uid** và **cn** có đúng một giá trị nhìn thấy trong kết quả. Nếu schema/ACL khác, ứng dụng cần điều chỉnh contract.
- **optionalString("mail")** không ép một attribute thiếu thành lỗi JNDI. Tuy nhiên, thiếu mail có thể là do **không có dữ liệu**, **ACL** hoặc server không trả attribute.
- Giá trị trả là **record** đã copy dữ liệu; không trả đối tượng context hoặc enumeration còn mở.

**Giới hạn:** LDAP attribute có thể đa trị. Nếu **mail** chứa nhiều địa chỉ, **optionalString(...)** chỉ nhận một giá trị không có bảo đảm ưu tiên. Khi nghiệp vụ cần mọi email, phải dùng **Attribute.getAll()** hoặc mapper có kiểu **Set/List**, không xem giá trị đầu tiên là email chính.

### 5.1. Dựng DN từ input đúng cách

Phương thức trên nhận relative DN để tập trung giải thích ContextExecutor. Trong ứng dụng có **uid** đến từ HTTP request, không được ghép chuỗi:

~~~java
// Sai: input có thể làm thay đổi cấu trúc DN.
String dn = "uid=" + userInput + ",ou=people";
~~~

Nên tạo **RDN** qua JNDI:

~~~java
import javax.naming.ldap.LdapName;
import javax.naming.ldap.Rdn;

LdapName relativeDn = new LdapName("ou=people");
relativeDn.add(new Rdn("uid", userInput));

PersonAttributeReader.PersonSummary person =
    reader.readPerson(relativeDn.toString());
~~~

**Rdn** xử lý escaping của giá trị DN. Các ký tự escape của **DN** khác với escape của **LDAP filter**; không dùng một hàm tự chế cho cả hai ngữ cảnh.

## 6. Ví dụ đúng mục đích: gọi DirContext.lookupLink

Trong tài liệu chính thức Spring LDAP, ví dụ điển hình cho **ContextExecutor** là **lookupLink(...)** — phương thức của JNDI **Context/DirContext** không có một overload tương ứng trong **LdapTemplate**.

~~~java
import javax.naming.Name;
import org.springframework.ldap.core.LdapTemplate;

public final class LinkLookupService {
    private final LdapTemplate ldapTemplate;

    public LinkLookupService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public Object lookupLink(Name relativeName) {
        return ldapTemplate.executeReadOnly(
            ctx -> ctx.lookupLink(relativeName)
        );
    }
}
~~~

Về ngữ nghĩa JNDI, **lookupLink** trả về binding/link của tên được cung cấp mà không theo liên kết cuối theo một số loại naming system. Tuy nhiên, **LDAP alias/referral không hoàn toàn tương đương với JNDI LinkRef**; LDAP provider/server cụ thể có thể hỗ trợ khác nhau hoặc ném **OperationNotSupportedException**. Không coi ví dụ này là lời hứa rằng mọi OpenLDAP hoặc AD đều trả một LinkRef từ một LDAP alias.

**Mục đích bài học:** Cho thấy cách dùng `executeReadOnly(ctx -> ctx.someJndiMethod(...))` để gọi phương thức ở cấp thấp mà vẫn tận dụng cơ chế lấy context, dịch ngoại lệ và close của template.

### 6.1. Khi nào không cần ContextExecutor?

Nếu mục đích chỉ là lookup một entry đã biết:

~~~java
// Cách đơn giản khi LdapTemplate đã có phương thức phù hợp:
Object entry = ldapTemplate.lookup("uid=linh,ou=people");
~~~

Nếu mục đích tìm nhiều entry bằng filter:

~~~java
import static org.springframework.ldap.query.LdapQueryBuilder.query;

List<String> names = ldapTemplate.search(
    query().base("ou=people")
           .where("uid").is(uid),
    (org.springframework.ldap.core.AttributesMapper<String>)
        attrs -> (String) attrs.get("cn").get()
);
~~~

Ví dụ `List` nằm trong method có import **java.util.List**, biến **uid**, và bean **ldapTemplate**. Đây là cách khuyến nghị hơn so với viết `ctx.search(...)` trong `ContextExecutor`, vì `LdapTemplate.search` xử lý callback từng kết quả và dọn **NamingEnumeration** đúng mục đích.

## 7. Thao tác ghi đặc biệt với executeReadWrite

Đối với CRUD thông thường, ưu tiên:

~~~java
ldapTemplate.bind(relativeDn, null, attributes);
ldapTemplate.modifyAttributes(relativeDn, modificationItems);
ldapTemplate.rename(oldRelativeDn, newRelativeDn);
ldapTemplate.unbind(relativeDn);
~~~

Các biến trong đoạn trên biểu diễn `Name` hoặc kiểu tham số thích hợp, cùng một tập **Attributes**/**ModificationItem[]** đã được chuẩn bị. Đây là các API đã có sẵn, nên không cần viết lại toàn bộ bằng ContextExecutor.

Khi cần phối hợp nhiều bước trên cùng context, có thể dùng `executeReadWrite`. Ví dụ muốn **thêm một member** vào nhóm rồi đọc lại tập member vừa nhận từ server:

~~~java
import java.util.ArrayList;
import java.util.List;
import javax.naming.NamingEnumeration;
import javax.naming.NamingException;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;
import org.springframework.ldap.core.LdapTemplate;

public final class GroupMemberWriter {
    private final LdapTemplate ldapTemplate;

    public GroupMemberWriter(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<String> addMemberAndReadBack(
            String relativeGroupDn, String fullMemberDn) {
        return ldapTemplate.executeReadWrite(ctx -> {
            ModificationItem item = new ModificationItem(
                DirContext.ADD_ATTRIBUTE,
                new BasicAttribute("member", fullMemberDn)
            );
            ctx.modifyAttributes(
                relativeGroupDn, new ModificationItem[]{item});

            Attributes after = ctx.getAttributes(
                relativeGroupDn, new String[]{"member"});
            Attribute members = after.get("member");
            if (members == null) {
                return List.of();
            }

            List<String> result = new ArrayList<>();
            NamingEnumeration<?> values = members.getAll();
            try {
                while (values.hasMore()) {
                    Object raw = values.next();
                    if (!(raw instanceof String dn)) {
                        throw new IllegalStateException(
                            "member must contain DN text");
                    }
                    result.add(dn);
                }
            } finally {
                values.close();
            }
            return List.copyOf(result);
        });
    }
}
~~~

Ví dụ giả định:

~~~java
List<String> members = writer.addMemberAndReadBack(
    "cn=developers,ou=groups",
    "uid=an,ou=people,dc=lab,dc=example"
);
~~~

**Những điều cần phân biệt:**

1. **Group DN truyền vào context** là DN **tương đối** với base **dc=lab,dc=example** của ContextSource.
2. **member** trong **groupOfNames** chứa **DN đầy đủ của entry thành viên**. Không thay bằng uid trần.
3. **ADD_ATTRIBUTE** chỉ thêm một giá trị, không gửi REPLACE cả tập member từ bản snapshot cũ. Nếu giá trị đã tồn tại, server có thể trả **attributeOrValueExists (20)**.
4. `ctx.modifyAttributes(...)` cần bind identity có **quyền ghi** và entry hợp lệ theo schema/ACL.
5. Kết quả trả về là **List<String>** đã materialize; không có **NamingEnumeration** chạy ra ngoài callback.
6. Việc đọc lại trên cùng context hữu ích cho feedback, nhưng không tạo transaction đa thao tác; một writer khác vẫn có thể sửa entry giữa bước Modify và bước đọc.

**Cảnh báo về dữ liệu đầu vào:** `fullMemberDn` trong ví dụ phải được tạo/xác minh từ một **LdapName/Rdn** hoặc một DN đã được xác thực, không lấy nguyên văn từ input người dùng chưa kiểm soát rồi tự cho phép họ thêm bất kỳ member nào. Việc kiểm tra nghiệp vụ và authorization phải thực hiện trước khi gọi callback.

## 8. ExecuteReadWrite không có nghĩa nhiều thao tác thành transaction

Một callback có thể chứa nhiều lệnh JNDI:

~~~text
executeReadWrite(ctx -> {
    Modify A
    Modify B
    Read A
    return result
})
~~~

Tất cả được gọi qua **cùng một DirContext**, nhưng **không mặc nhiên nằm trong transaction ACID**. Theo LDAPv3, một **ModifyRequest** trên **một entry** có ngữ nghĩa nguyên tử đối với các thay đổi bên trong request đó; điều này không khiến hai ModifyRequest khác nhau tự rollback cùng nhau.

Giả sử:

~~~text
Modify member của nhóm A: thành công
Modify description của nhóm B: thất bại do ACL

Kết quả: nhóm A có thể đã thay đổi,
          nhóm B không thay đổi.
~~~

Một **NamingException** ở thao tác thứ hai không tự khôi phục thao tác thứ nhất. Nếu nghiệp vụ cần phối hợp thay đổi trên nhiều entry, phải thiết kế **compensation**, trạng thái trung gian, thao tác idempotent hoặc khả năng transaction/extension đặc biệt mà server thực sự hỗ trợ. Không coi ContextExecutor là transaction boundary chỉ vì nó là một callback Java duy nhất.

### 8.1. Không dùng read-modify-REPLACE mù quáng

Hai request có thể cùng đọc tập **member** rồi thay toàn bộ:

~~~text
Ban đầu: member = {Linh}
Request A đọc {Linh}, thêm An rồi REPLACE {Linh, An}
Request B đọc {Linh}, thêm Bình rồi REPLACE {Linh, Bình}
Sau cùng: có thể mất giá trị An
~~~

Đây là **lost update**, không được ngăn bằng việc chạy các bước trong một `executeReadWrite`. Nếu muốn thêm một giá trị, dùng **ADD_ATTRIBUTE**; khi cần thay toàn tập, cân nhắc kiểm soát phiên bản/Assertion Control nếu directory server hỗ trợ và yêu cầu nghiệp vụ cần thiết.

## 9. Những điều callback phải và không được làm

**Nên làm trong callback:**

- Gọi một phương thức JNDI chưa có API template tương đương.
- Thực hiện thao tác trên đúng **relative DN** và đúng LDAP endpoint.
- Kiểm tra **attribute** có tồn tại/đúng kiểu hay không, xử lý giá trị đơn/đa trị và trả về DTO bất biến.
- Đóng tài nguyên **NamingEnumeration** hoặc context con do callback tự mở.
- Giữ thông tin lỗi gốc để Spring dịch và service xử lý.

**Không nên làm trong callback:**

- `ctx.close()` trên context **được template cấp**; LdapTemplate sẽ quản lý nó.
- Lưu `ctx` vào field singleton, cache hoặc trả về ngoài để tái sử dụng ở request khác.
- Trả `NamingEnumeration` chưa duyệt hết cho controller/service.
- Thực hiện network call HTTP dài hoặc `Thread.sleep` khi đang giữ LDAP context.
- Gửi mật khẩu, thông tin cá nhân hoặc toàn bộ entry vào log để debug.
- Nối chuỗi LDAP filter từ input chưa escape.
- Đặt nhiều thay đổi không liên quan vào một callback rồi giả định transaction.

### 9.1. Vì sao không nên giữ context lâu?

Một context đang được mượn là tài nguyên hữu hạn. Với Spring LDAP pooling, thời gian giữ context lâu làm tăng số **active**, khiến request khác phải chờ **maxWait** hoặc bị từ chối. Callback nên thực hiện công việc LDAP thật sự cần thiết rồi trả ngay **kết quả đã materialize**.

### 9.2. Thao tác search vẫn dùng overload chuyên biệt

Nếu cần **SearchControls**, filter tham số hóa và callback riêng, dùng API `search(...)` của LdapTemplate hoặc **SearchExecutor**. Khi tự triển khai search bằng JNDI trong một callback bất thường, bạn phải tự xử lý **NamingEnumeration**, partial result, referral, size/time limits và exception. Đây không phải lý do phù hợp để bỏ qua API đã có.

## 10. Cách xử lý ngoại lệ giữa JNDI và Spring LDAP

Các phương thức của **DirContext** có thể ném ngoại lệ kiểm tra (**checked exception**) thuộc họ **javax.naming.NamingException**. Khi thực thi callback qua `LdapTemplate.executeReadOnly` hoặc `executeReadWrite`, template bắt **NamingException** phát sinh từ callback và dùng cơ chế chuyển đổi sang ngoại lệ runtime của Spring LDAP.

| Tầng JNDI / LDAP | Biểu hiện | Tầng Spring LDAP thường gặp | Ý nghĩa chẩn đoán |
| --- | --- | --- | --- |
| **javax.naming.NameNotFoundException** / LDAP 32 | DN lookup hoặc search base không tồn tại | **org.springframework.ldap.NameNotFoundException** | Sai DN, nhánh đã đổi hoặc ACL che |
| **javax.naming.AuthenticationException** / LDAP 49 | Bind sai thông tin xác thực | **org.springframework.ldap.AuthenticationException** | Kiểm tra bind DN/password/cơ chế xác thực |
| **javax.naming.NoPermissionException** / LDAP 50 | Bị từ chối quyền | **org.springframework.ldap.NoPermissionException** | Cần xem ACL, không tăng pool |
| **javax.naming.directory.AttributeInUseException** / LDAP 20 | Thêm một attribute value đã tồn tại | Ngoại lệ LDAP tương ứng đã được dịch | Ví dụ ADD member trùng |
| **javax.naming.CommunicationException** | Kết nối, TLS hoặc phản hồi thất bại | **org.springframework.ldap.CommunicationException** | Kiểm tra mạng, timeout, SSL và cause |
| **javax.naming.TimeLimitExceededException** / LDAP 3 | Quá giới hạn tìm kiếm | **org.springframework.ldap.TimeLimitExceededException** | Điều chỉnh filter, index và search limit |
| **javax.naming.directory.SchemaViolationException** / LDAP 65 (điển hình) | Vi phạm objectClass/schema | Ngoại lệ schema tương ứng | Kiểm tra MUST/MAY, syntax và ACL |

Tên cụ thể và cause chain phụ thuộc thao tác, provider và phiên bản; **không suy đoán mọi lỗi đều là một class duy nhất**. Thông báo gốc của LDAP/JNDI đôi khi chứa DN, host, attribute hoặc thông tin nhạy cảm, vì vậy chỉ đưa bản rút gọn phù hợp vào HTTP response.

### 10.1. Catch ngoại lệ ở service, không nuốt lỗi trong callback

Ví dụ một service dự kiến kiểm tra entry có tồn tại:

~~~java
import org.springframework.ldap.NameNotFoundException;
import org.springframework.ldap.core.LdapTemplate;

public final class EntryExistenceService {
    private final LdapTemplate ldapTemplate;

    public EntryExistenceService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public boolean exists(String relativeDn) {
        try {
            return ldapTemplate.executeReadOnly(ctx -> {
                ctx.getAttributes(
                    relativeDn, new String[]{"objectClass"});
                return true;
            });
        } catch (NameNotFoundException ex) {
            // DN trực tiếp được tra cứu không tồn tại/không được thấy.
            // Chỉ coi là false nếu contract và ACL cho phép diễn giải đó.
            return false;
        }
    }
}
~~~

Ví dụ này minh họa cách bắt **org.springframework.ldap.NameNotFoundException** ở phía gọi `LdapTemplate`, không phải `javax.naming.NameNotFoundException`. **Không dùng cách trả false vô điều kiện** trong hệ thống có ACL che entry hoặc khi **relativeDn** là cấu hình cứng phải tồn tại: ở đó, một NameNotFound có thể là lỗi hệ thống cần cảnh báo.

Nếu yêu cầu là kiểm tra tồn tại bằng API có sẵn, **LdapTemplate.lookup** hoặc phương thức lookup/exists thích hợp thường gọn hơn; ví dụ `ContextExecutor` ở trên giúp thấy nơi đặt catch trong luồng extension.

### 10.2. Runtime exception và cleanup

Spring LDAP chuyển **NamingException** phát sinh trong callback. Nếu callback tự ném **IllegalArgumentException** hoặc **IllegalStateException** vì dữ liệu không hợp lệ, các unchecked exception này không được “đổi” thành NamingException; chúng vẫn lan ra service. Dù vậy, khối cleanup của template vẫn thực hiện việc đóng/trả context.

Không bắt `Exception` rồi `return List.of()` cho mọi lỗi; điều đó biến lỗi mạng, quyền hoặc schema thành tín hiệu “người dùng không tồn tại”.

## 11. ContextExecutor với thao tác thấp hơn: hạn chế và phương án thay thế

Khi một phương thức JNDI chưa có overload trong `LdapTemplate`, callback có thể sử dụng trực tiếp:

~~~java
// Bên trong lambda ContextExecutor, tùy ngữ cảnh:
ctx.lookupLink(relativeName);
ctx.getAttributes(relativeName, attributeIds);
ctx.getSchema(relativeName);
ctx.getSchemaClassDefinition(relativeName);
~~~

Đây là **các phương thức của DirContext/Context**, không có nghĩa mọi LDAP provider đều triển khai toàn bộ chức năng schema/alias tương đương. Đặc biệt `getSchema` và `getSchemaClassDefinition` có thể trả một **DirContext khác**; nếu mở context phụ như vậy thì callback phải tự quản lý/đóng nó, không trả một context đang mở ra ngoài.

Ví dụ đọc thông tin schema với đóng tài nguyên context con:

~~~java
import javax.naming.directory.DirContext;
import org.springframework.ldap.core.LdapTemplate;

public final class SchemaProbe {
    private final LdapTemplate ldapTemplate;

    public SchemaProbe(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public boolean schemaContextAvailable(String relativeDn) {
        return ldapTemplate.executeReadOnly(ctx -> {
            DirContext schema = ctx.getSchema(relativeDn);
            if (schema == null) {
                return false;
            }
            try {
                return true;
            } finally {
                schema.close();
            }
        });
    }
}
~~~

**Cảnh báo:** Một số JNDI LDAP provider hoặc directory server không hỗ trợ cơ chế truy cập schema như trên, hoặc trả lỗi do ACL. Ứng dụng phải kiểm thử trên server mục tiêu; khi chỉ cần xác nhận objectClass của entry, dùng **getAttributes(..., "objectClass")** thường đơn giản hơn.

### 11.1. Không nhầm đồng bộ nhiều bước trên cùng context với nhất quán dữ liệu

Trong một callback, việc gọi JNDI tuần tự có thể giúp tránh tạo nhiều context không cần thiết. Nhưng:

- Nó **không khóa entry** để ngăn các LDAP client khác sửa.
- Nó **không hứa** các replica khác đã nhìn thấy thay đổi.
- Nó **không tạo** transaction phân tán nhiều entry.
- Nếu có lỗi sau một lệnh ghi thành công, thao tác trước đó có thể đã được áp dụng.
- Khi một read timeout xảy ra sau Modify, server có thể đã ghi nhưng client chưa nhận được kết quả.

Do đó phải giải quyết tính nhất quán ở tầng thiết kế nghiệp vụ và khả năng server, không ở tên `executeReadWrite`.

### 11.2. Có dùng ContextExecutor để mở StartTLS không?

**Không nên coi callback ContextExecutor thông thường là cách thiết lập TLS phiên dài hạn.** StartTLS cần được thực hiện đúng thứ tự kết nối, xác minh certificate và quản lý trạng thái socket. Khi template hoàn thành callback, context được trả hoặc đóng; việc thay đổi trạng thái TLS trên context được pool có thể không an toàn.

Hãy cấu hình **LDAPS** hoặc **StartTLS** theo **ContextSource/LDAP client** và vòng đời được tài liệu thư viện hỗ trợ. Nếu không có hỗ trợ trong mô hình đang dùng, chọn giải pháp client/context riêng được thiết kế cho StartTLS. Không bỏ xác minh TLS hoặc dùng simple bind trên kết nối không được bảo vệ chỉ vì callback JNDI linh hoạt hơn.

## 12. Bảo mật DN, filter và quyền khi gọi JNDI cấp thấp

`ContextExecutor` đặt quyền gọi API JNDI trực tiếp trong tay ứng dụng. Điều này mở rộng khả năng nhưng cũng làm tăng trách nhiệm:

### 12.1. Escape DN và LDAP filter theo hai quy tắc riêng

Với DN động, dùng **LdapName/Rdn**:

~~~java
import javax.naming.ldap.LdapName;
import javax.naming.ldap.Rdn;

LdapName relativePersonDn = new LdapName("ou=people");
relativePersonDn.add(new Rdn("uid", userSuppliedUid));
~~~

Với search filter, dùng `LdapQueryBuilder`:

~~~java
import static org.springframework.ldap.query.LdapQueryBuilder.query;

var search = query().base("ou=people")
    .where("uid").is(userSuppliedUid);
~~~

Hoặc dùng JNDI `DirContext.search` với filter arguments **`(uid={0})`**, không nối thẳng input vào filter. **DN escaping** và **filter escaping** theo các quy tắc khác nhau; dùng sai sẽ gây query sai, LDAP injection hoặc truy cập nhánh ngoài ý định.

### 12.2. Ràng buộc vùng truy cập

Không cho HTTP request trực tiếp quyết định một **relative DN** bất kỳ rồi truyền vào `ctx.modifyAttributes` hoặc `ctx.unbind`:

- Chỉ cho phép nhánh hợp lệ, ví dụ **ou=people** hoặc **ou=groups** theo chức năng.
- Kiểm tra danh tính người gọi và chính sách nghiệp vụ trước khi Modify/Delete/Rename.
- Bind tài khoản LDAP của ứng dụng với **quyền tối thiểu**, không dùng rootDN để “đơn giản hóa” ví dụ.
- Khi nhận DN tham chiếu, parse bằng JNDI và xác minh nó thuộc vùng được phép; không so sánh suffix chỉ bằng chuỗi dễ sai escaping/case.
- Với thuộc tính đa trị, chọn **ADD/REMOVE** khi muốn chỉnh một giá trị, tránh REPLACE toàn bộ từ dữ liệu cũ nếu không kiểm soát đồng thời.

### 12.3. Secrets và TLS

- Dùng **LDAPS hoặc StartTLS** với certificate chain và hostname verification phù hợp.
- Lấy bind password từ biến môi trường/secret manager; không log `Context.SECURITY_CREDENTIALS`.
- Không in toàn bộ `ctx.getEnvironment()` vì có thể chứa bind credentials.
- Không gửi raw LDAP exception/stack trace kèm DN nội bộ vào API công khai.
- Đặt JNDI **connect/read timeout** và giới hạn time/size cho những truy vấn có thể tốn tài nguyên.

Đọc được một DN hay objectClass không cho người gọi quyền thực hiện LDAP Modify trên entry đó. **ACL phía server** vẫn phải được thực thi.

## 13. Hiệu năng, pooling và phạm vi một callback

### 13.1. Mượn context đúng thời gian cần thiết

Một lần gọi `executeReadOnly` hoặc `executeReadWrite` lấy một context rồi giữ nó trong suốt callback. Với **PooledContextSource**, context đó được đánh dấu **active** cho tới khi template trả lại. Nếu callback gọi thêm API từ xa không liên quan, thực hiện chờ hoặc chuyển sang công việc CPU dài, các thread khác có thể thiếu connection.

Tốt nhất nên:

1. Chuẩn bị dữ liệu/validate input **trước** callback.
2. Trong callback, chỉ làm các lệnh LDAP cần cùng context.
3. Chuyển **Attributes** sang DTO gọn; đóng enumeration/context con.
4. Trả kết quả ngay, để `LdapTemplate` giải phóng context.
5. Sau callback mới thực hiện logic nghiệp vụ không cần LDAP connection.

### 13.2. Callback trên cùng context không đồng nghĩa cùng socket mãi mãi

**ContextSource** và provider quản lý cách mở, mượn và đóng/reuse connection. Một `DirContext` có thể được bọc bởi Spring LDAP pooling hoặc thực thi qua provider có logic kết nối. Không dựa vào “đây là một callback” để suy đoán ID socket vật lý hoặc tính nhất quán giữa mọi LDAP replica.

### 13.3. Thao tác chậm và timeout

Có thể cấu hình JNDI environment:

~~~yaml
spring:
  ldap:
    base-environment:
      "[com.sun.jndi.ldap.connect.timeout]": "3000"
      "[com.sun.jndi.ldap.read.timeout]": "5000"
~~~

**Connect timeout** giới hạn một số thời gian mở TCP; **read timeout** giới hạn chờ LDAP response. Các ngưỡng này không tự trở thành tổng deadline của callback nếu nó chứa nhiều thao tác. Cũng cần xét thời gian chờ **borrow từ pool**, TLS, DNS, LDAP referral, nhiều endpoint và retries.

Nếu LDAP provider ném CommunicationException do timeout, callback không nên giữ context để thử lại vô hạn. Hãy để template giải phóng/từ bỏ context theo cơ chế thích hợp và đưa quyết định retry lên service. Với thao tác ghi, phải xác minh trạng thái để tránh áp dụng hai lần.

## 14. Kiểm thử ContextExecutor với directory

Một **unit test chỉ mock ContextExecutor/DirContext** có thể xác minh branching của Java nhưng không kiểm tra việc nối base DN, LDAP result code, ACL hoặc behavior thực sự của provider. Nên bổ sung **integration test với LDAP nhúng hoặc server lab** có schema tương ứng.

### 14.1. Dữ liệu LDIF test

Directory test cần:

- Suffix **dc=lab,dc=example**, nhánh **ou=people** và **ou=groups**.
- Entry người dùng **uid=linh** có **cn**, **sn** và **uid**.
- Entry nhóm **cn=developers** có **member=uid=linh,...**.
- Một tài khoản **reader** chỉ được search/read.
- Một tài khoản **writer** có quyền Modify thành viên nhóm trong lab.

Hai entry mẫu được trình bày ở phần 4; cần import **entry cha trước, entry con sau**. Nếu directory nhúng tự cấp quyền mở rộng, đừng suy ra ACL của OpenLDAP/AD sẽ giống hệt. Trường hợp ACL và schema tùy chỉnh nên kiểm thử thêm trên loại server triển khai thật.

### 14.2. Integration test đọc bằng callback

Ví dụ dùng JUnit 5 và Spring Boot test:

~~~java
import javax.naming.directory.Attributes;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.ldap.NameNotFoundException;
import org.springframework.ldap.core.LdapTemplate;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringBootTest
class ContextExecutorIntegrationTest {
    @Autowired
    LdapTemplate ldapTemplate;

    @Test
    void readsAttributeThroughReadOnlyContext() {
        String name = ldapTemplate.executeReadOnly(ctx -> {
            Attributes attributes = ctx.getAttributes(
                "uid=linh,ou=people", new String[]{"cn"});
            return (String) attributes.get("cn").get();
        });

        assertEquals("Linh Nguyen", name);
    }

    @Test
    void missingDnIsNotAnEmptySearchResult() {
        assertThrows(NameNotFoundException.class, () ->
            ldapTemplate.executeReadOnly(ctx ->
                ctx.getAttributes(
                    "uid=khong-co,ou=people", new String[]{"uid"})));
    }
}
~~~

Đây là **mẫu integration test**, yêu cầu ứng dụng test có Spring Boot configuration, bean `LdapTemplate`, LDAP directory đã khởi động và dữ liệu mẫu. Không thể chạy chỉ bằng cách sao chép class khi chưa cấp datasource directory, bind DN, truststore và test dependencies tương ứng.

Điểm kiểm tra thứ hai: đọc trực tiếp một DN không tồn tại thường ném **NameNotFoundException**, khác với một **Search** hợp lệ dưới base có sẵn nhưng filter không khớp (trả danh sách rỗng).

### 14.3. Kiểm thử thao tác ghi có cleanup

Test write nên được chạy với directory lab và bind identity có quyền, không dùng directory production. Quy trình:

1. Tạo group test với một member hợp lệ.
2. Gọi `executeReadWrite` để ADD một member thứ hai.
3. Đọc lại **member** và kiểm tra theo **tập DN**, không theo thứ tự LDAP.
4. Thử ADD lại cùng member; kiểm tra mã lỗi/exception theo schema server.
5. Đảm bảo cleanup: xóa member đã thêm hoặc xóa group test theo đúng quy trình.
6. Thử lỗi quyền/nhánh không tồn tại, xem callback ném lỗi và context được giải phóng.

Nếu groupOfNames yêu cầu ít nhất một member, không xóa member cuối cùng rồi kỳ vọng entry vẫn hợp lệ. Nếu muốn test ghi đồng thời, kiểm thử riêng lost update, không giả định ContextExecutor khóa entry.

### 14.4. Kiểm thử lifecycle/pooling

Với Spring LDAP Pool2, có thể quan sát `getNumActive()` trước/sau nhiều lần callback thành công và callback ném exception. Sau khi tất cả callback hoàn thành, active contexts phải được trả về pool, với điều kiện không còn request khác đang dùng cùng bean.

Khi test trên môi trường có nhiều thread, không assert số active tuyệt đối nếu một request khác vẫn đang chạy; dùng một pool test riêng để có kết quả xác định. Không tự gọi `ctx.close()` trong callback để “chắc chắn không leak”, vì hành động đó xung đột với cơ chế thu hồi context của template.

## 15. Bảng lựa chọn API cho từng tình huống

| Nhu cầu | API ưu tiên | Vì sao? |
| --- | --- | --- |
| Tìm người theo uid/mail/objectClass | **LdapTemplate.search(LdapQuery, mapper)** hoặc repository | Query builder, mapping, resource cleanup |
| Tìm kiếm có SearchControls cực đặc thù | **LdapTemplate.search(SearchExecutor, handler)** | Quản lý enumeration và callback đúng ngữ nghĩa search |
| Đọc một entry đã biết DN | **LdapTemplate.lookup(...)** | Đã có overload sẵn, gọn |
| Gọi `lookupLink` hoặc JNDI method thiếu overload | **executeReadOnly(ContextExecutor<T>)** | Truy cập trực tiếp DirContext, không tự lấy/đóng context |
| Kết hợp một vài thao tác ghi/đọc trên cùng context | **executeReadWrite(ContextExecutor<T>)** nếu thật sự cần | Tự kiểm soát thứ tự thao tác cấp thấp |
| Thêm một giá trị member | **LdapTemplate.modifyAttributes(...)** với ADD | Không REPLACE cả tập, tránh lost update đơn giản |
| Tạo entry theo objectClass/schema | **LdapRepository.save(...)** hoặc **LdapTemplate.bind(...)** | ODM/API chuyên dụng dễ bảo trì |
| Đổi DN / move entry | **LdapTemplate.rename(...)** | Đã có thao tác rõ nghĩa |
| Kiểm soát xác thực người dùng | Luồng **Spring Security LDAP** phù hợp | Không lẫn pool context dịch vụ với user bind |
| Thao tác transaction đa entry | Thiết kế riêng theo khả năng server và nghiệp vụ | ContextExecutor không mặc định là transaction |

## 16. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Import sai **ContextExecutor** | Tự tạo interface hoặc import package không đúng | Dùng **org.springframework.ldap.core.ContextExecutor** |
| Code dùng `executeReadOnly` để ghi | Nhầm ý nghĩa READ/WRITE, cấu hình bind DN khác | Dùng executeReadWrite và quyền phù hợp |
| Truy vấn trả rỗng khi DN full được truyền | ContextSource đã có base, bị lặp suffix | Dùng **relative DN** đúng API |
| Callback trả NamingEnumeration rồi lỗi sau đó | Context đã được template đóng | Materialize và đóng enumeration trong callback |
| Pool active tăng mãi | Mượn context thủ công mà không close hoặc callback quá lâu | Dùng LdapTemplate, close context mượn thủ công |
| Group member bị mất sau hai lần update | Hai request REPLACE snapshot cũ | Dùng ADD/REMOVE delta hoặc cơ chế concurrency |
| LDAP code 32 | DN đích/search base không tồn tại hoặc ACL che | Đối chiếu DN, base, quyền và endpoint |
| LDAP code 20 khi ADD member | Giá trị đã có trên entry | Đặt quy tắc duplicate/idempotency |
| LDAP code 50 khi Modify | Bind identity không đủ quyền | Kiểm tra ACL, không dùng admin làm workaround |
| LDAP code 65 khi cập nhật | Vi phạm objectClass/schema | Kiểm tra MUST/MAY và cú pháp attribute |
| Callback chậm dù server khỏe | Giữ context khi làm tác vụ ngoài LDAP | Di chuyển công việc ngoài callback |
| Retry Modify tạo kết quả bất ngờ | Server có thể đã ghi trước read timeout | Kiểm tra trạng thái trước khi retry |
| `lookupLink` bị OperationNotSupported | Directory/provider không hỗ trợ cách lookup | Kiểm thử đúng server, chọn API tương thích |
| Test qua mock PASS nhưng integration FAIL | Mock không mô phỏng ACL/schema/LDAP result | Dùng directory nhúng hoặc test server phù hợp |

## 17. Bài thực hành và câu hỏi ôn tập

**Bài thực hành:** Tạo directory lab như phần 4, sau đó triển khai ba phương thức:

1. `readPerson(relativeDn)` dùng `executeReadOnly`, lấy **uid/cn/mail** và trả DTO.
2. `lookupLink(relativeDn)` dùng `executeReadOnly`, quan sát behavior thực của LDAP provider khi entry bình thường/alias.
3. `addMemberAndReadBack(groupDn, memberDn)` dùng `executeReadWrite`, ADD member và đọc lại danh sách.

Với mỗi phương thức, viết test thành công và test exception. Cố ý gây **noSuchObject (32)** hoặc **insufficientAccessRights (50)** trong lab; xác nhận exception được dịch về Spring LDAP và context được giải phóng. Đối chiếu với cách viết bằng `LdapTemplate.lookup`/`modifyAttributes` và giải thích API nào dễ bảo trì hơn.

**Câu hỏi ôn tập:**

1. `ContextExecutor<T>` khác `AttributesMapper<T>` và `SearchExecutor` ở chỗ nào?
2. `executeReadOnly` và `executeReadWrite` lấy context từ đâu?
3. Tại sao không được `ctx.close()` trên context mà `LdapTemplate` cấp trong callback?
4. Một callback có thể trả **NamingEnumeration** ra service hay không? Vì sao?
5. Khi JNDI ném `javax.naming.NameNotFoundException`, code gọi LdapTemplate thường nhận loại ngoại lệ nào?
6. Vì sao việc chạy hai Modify trong cùng `executeReadWrite` không tự tạo transaction?
7. Làm sao tạo relative DN chứa uid động mà không ghép chuỗi không an toàn?
8. Khi chỉ thêm một thành viên nhóm, nên dùng ADD_ATTRIBUTE hay REPLACE_ATTRIBUTE? Vì sao?
9. Nếu dùng PooledContextSource, callback dài có thể ảnh hưởng số active/waiters như thế nào?
10. Vì sao test trên directory thật/nhúng vẫn cần thiết dù unit test có thể mock DirContext?

**Ghi nhớ:** `ContextExecutor<T>` là cổng mở có kiểm soát từ **LdapTemplate** xuống **JNDI DirContext**. Dùng **executeReadOnly** cho thao tác đọc đặc biệt, **executeReadWrite** cho thao tác có ghi; để template tự lấy context, dịch `NamingException` và đóng/trả context. **Không lạm dụng nó cho search hoặc CRUD đã có API tương đương**, không trả tài nguyên JNDI lười ra ngoài, không coi callback là transaction và luôn thực thi chính sách DN/filter an toàn, TLS, ACL và kiểm thử tích hợp.

## Tài liệu tham khảo

- [Spring LDAP — Adding Missing Overloaded API Methods](https://docs.spring.io/spring-ldap/reference/adding-missing-overloaded-api-methods.html): ví dụ chính thức `ContextExecutor`, `lookupLink` và phân biệt `SearchExecutor`.
- [Spring LDAP — ContextExecutor API](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/ContextExecutor.html): `executeWithContext(DirContext)`.
- [Spring LDAP — LdapTemplate API](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/LdapTemplate.html): `executeReadOnly`, `executeReadWrite`, lookup/search/modify và xử lý context.
- [Spring LDAP — LdapOperations API](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/LdapOperations.html): lựa chọn thao tác LDAP cấp cao.
- [Spring LDAP — Exception Handling](https://docs.spring.io/spring-ldap/reference/exception-handling.html): cách chuyển ngoại lệ JNDI sang runtime LDAP.
- [Oracle JNDI — DirContext](https://docs.oracle.com/en/java/javase/21/docs/api/java.naming/javax/naming/directory/DirContext.html): getAttributes, modifyAttributes, schema và search.
- [Oracle JNDI — Context](https://docs.oracle.com/en/java/javase/21/docs/api/java.naming/javax/naming/Context.html): lookupLink và lifecycle của context.
- [RFC 4511 — LDAPv3 Protocol](https://www.rfc-editor.org/rfc/rfc4511.html): Modify, Search, DN và các LDAP result codes.
- [RFC 4515 — LDAP Search Filters](https://www.rfc-editor.org/rfc/rfc4515.html): escaping giá trị filter.
- [Spring Data LDAP — Reference](https://docs.spring.io/spring-data/ldap/reference/): repository và object-directory mapping.
