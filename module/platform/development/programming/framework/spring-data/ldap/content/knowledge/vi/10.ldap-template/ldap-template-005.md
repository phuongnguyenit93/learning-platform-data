# Sử dụng DirContextAdapter để truy cập thuộc tính

## Mục tiêu bài học

Trong **SPRING_DATA_LDAP**, ứng dụng Java thường truy cập LDAP directory theo hai cách: dùng **Spring Data LDAP repository** để ánh xạ entry thành object Java hoặc dùng **LdapTemplate** để đọc và ghi trực tiếp những thuộc tính LDAP. Khi làm việc ở mức LdapTemplate, lớp **DirContextAdapter** giúp việc đọc, thay đổi thuộc tính và quản lý thuộc tính đa giá trị gọn hơn so với thao tác trực tiếp trên **javax.naming.directory.Attributes**.

Bài thuộc chương **LdapTemplate**, tập trung vào câu hỏi: **DirContextAdapter đại diện cho gì, có thể dùng thế nào để truy cập thuộc tính, và vì sao nó hữu ích khi cập nhật LDAP entry?**

Sau bài học, bạn có thể:

- Giải thích vai trò của **DirContextAdapter**, **DirContextOperations**, **ContextMapper**, **AttributesMapper**, **LdapTemplate** và **ContextSource**.
- Đọc thuộc tính một giá trị hoặc nhiều giá trị bằng **getStringAttribute**, **getStringAttributes**, **getObjectAttribute**, **getObjectAttributes**.
- Tạo entry bằng **new DirContextAdapter(dn)**, **setAttributeValue(s)** và **ldapTemplate.bind(ctx)**.
- Cập nhật entry bằng **ldapTemplate.lookupContext(dn)**, thay đổi thuộc tính và **ldapTemplate.modifyAttributes(ctx)**.
- Hiểu **update mode**, **getModificationItems()**, **setAttributeValues**, **addAttributeValue**, **removeAttributeValue**.
- Xử lý DN làm giá trị thành viên nhóm, thuộc tính bị thiếu, thuộc tính nhị phân, quyền LDAP và schema.
- Truy vấn an toàn, giới hạn phạm vi/thuộc tính, và kiểm thử với directory thay vì chỉ mock Java object.

## 1. Từ entry LDAP tới object Java

Ví dụ một LDAP directory có dữ liệu:

~~~text
dc=example,dc=org
├── ou=people
│   └── uid=an
└── ou=groups
    └── cn=backend
~~~

Entry người dùng An:

~~~ldif
dn: uid=an,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: an
cn: An Tran
sn: Tran
mail: an@example.org
telephoneNumber: +84 28 1234 5678
description: Ky su backend
~~~

**DN** xác định vị trí entry trong cây; **objectClass** quy định loại entry và tập thuộc tính hợp lệ; các thuộc tính như **cn**, **sn**, **mail** chứa dữ liệu thực tế. Một thuộc tính có thể có một hoặc nhiều giá trị, và không phải giá trị nào cũng là String.

Với JNDI thuần, bạn thường gặp:

~~~java
import javax.naming.directory.Attributes;
import javax.naming.directory.Attribute;

Attributes attrs = /* dữ liệu trả từ LDAP */;
Attribute cnAttr = attrs.get("cn");
String cn = cnAttr == null ? null : (String) cnAttr.get();
~~~

Khi dùng **DirContextAdapter**, cách đọc thường gọn hơn:

~~~java
import org.springframework.ldap.core.DirContextOperations;

DirContextOperations ctx = /* nhận từ LdapTemplate */;
String cn = ctx.getStringAttribute("cn");
String[] objectClasses = ctx.getStringAttributes("objectClass");
~~~

Đây không phải cơ chế tạo schema mới hay cache toàn bộ directory. Adapter là **lớp bọc ngữ nghĩa một entry LDAP**, giữ các attributes đã đọc cùng DN và cung cấp các phương thức thuận tiện để đọc/sửa chúng.

## 2. DirContextAdapter là gì?

**org.springframework.ldap.core.DirContextAdapter** là một lớp của Spring LDAP, triển khai giao diện **DirContextOperations** và những giao diện thích hợp khác của JNDI/LDAP. Lớp này được thiết kế cho thao tác trên **entry và attributes**, đặc biệt khi tạo/cập nhật dữ liệu.

Khi Spring LDAP sử dụng **DefaultDirObjectFactory** (thông thường là mặc định của ContextSource), entry được lấy bằng những API context-oriented có thể được biểu diễn dưới dạng DirContextAdapter. Bạn thường lập trình dựa trên **DirContextOperations**, thay vì gắn chặt service với lớp triển khai cụ thể.

| Thành phần | Nhiệm vụ | Ví dụ |
| --- | --- | --- |
| **ContextSource** | Tạo LDAP context với URL, base DN, credentials và cấu hình kết nối | **LdapContextSource** |
| **LdapTemplate** | Thực hiện lookup/search/bind/modify và quản lý context | **lookupContext**, **modifyAttributes** |
| **DirContextAdapter** | Biểu diễn entry, lưu thuộc tính, hỗ trợ tính thay đổi | **new DirContextAdapter(dn)** |
| **DirContextOperations** | Giao diện đọc/sửa thuộc tính ở mức entry | **getStringAttribute**, **setAttributeValue** |
| **ContextMapper<T>** | Ánh xạ một context/adapter sang object nghiệp vụ | Entry → **PersonView** |
| **AttributesMapper<T>** | Ánh xạ **Attributes** sang object nghiệp vụ | Attributes → **PersonView** |
| **Spring Data LDAP ODM** | Ánh xạ bằng **@Entry**, **@Id**, **@Attribute** | **PersonEntry** |

**Cần phân biệt DirContextAdapter với DirContext của JNDI:** adapter **không phải một triển khai đầy đủ của mọi thao tác DirContext**. Một số phương thức JNDI không phù hợp với mục đích lớp này và có thể ném **UnsupportedOperationException**. Hãy dùng adapter cho dữ liệu entry và dùng **LdapTemplate** cho các thao tác với directory.

### 2.1. Sơ đồ đường đi dữ liệu

~~~mermaid
flowchart TD
    A["Service / Repository"] --> B["LdapTemplate"]
    B --> C["ContextSource / JNDI"]
    C --> D["LDAP server: entry, schema, ACL"]
    D --> C
    C --> E["DirContextAdapter / DirContextOperations"]
    E --> F["ContextMapper: đọc các thuộc tính cần thiết"]
    F --> G["DTO hoặc domain object"]
    E --> H["setAttributeValue(s) / add-remove"]
    H --> I["getModificationItems()"]
    I --> B
~~~

Sơ đồ chỉ diễn tả logic. Mỗi lời gọi không nhất thiết phải tạo mới adapter qua từng ô; đối với tạo entry, chính ứng dụng có thể gọi **new DirContextAdapter(dn)**.

## 3. Đọc thuộc tính: kiểu dữ liệu và số lượng giá trị

DirContextOperations có nhóm phương thức truy cập thuộc tính hữu ích:

| Phương thức | Kết quả | Lưu ý |
| --- | --- | --- |
| **getStringAttribute("cn")** | String hoặc null | Chỉ trả **một** giá trị; nếu thuộc tính đa giá trị sẽ không trả tất cả |
| **getStringAttributes("objectClass")** | String[] hoặc null | Dành cho nhiều giá trị kiểu chuỗi; không suy thứ tự có ý nghĩa |
| **getObjectAttribute("jpegPhoto")** | Object hoặc null | Có thể là **byte[]**, cần kiểm tra kiểu |
| **getObjectAttributes("member")** | Object[] hoặc null | Dùng khi cần xử lý giá trị không nhất thiết là chuỗi |
| **attributeExists("mail")** | boolean | Kiểm tra tên thuộc tính có tồn tại trong dữ liệu adapter đã nhận |
| **getAttributes()** | Attributes | Truy cập JNDI attributes thô khi cần |
| **getDn()** | Name | DN mà adapter giữ, thông thường **tương đối với base của ContextSource** |

**Không gọi getStringAttribute trên thuộc tính đa giá trị rồi coi đó là toàn bộ dữ liệu.** Ví dụ objectClass có thể chứa **top**, **person**, **organizationalPerson** và **inetOrgPerson**; phải dùng **getStringAttributes** nếu muốn đọc tất cả.

**Giá trị null có ngữ nghĩa cần thận trọng:** thuộc tính không có trong adapter có thể vì server không lưu nó, tài khoản không được đọc, hoặc truy vấn chỉ yêu cầu một tập thuộc tính con. Đừng tự động suy rằng entry gốc chắc chắn không chứa thuộc tính đó.

### 3.1. Xử lý thuộc tính nhiều giá trị

Một nhóm có thể lưu:

~~~ldif
dn: cn=backend,ou=groups,dc=example,dc=org
objectClass: top
objectClass: groupOfNames
cn: backend
member: uid=an,ou=people,dc=example,dc=org
member: uid=binh,ou=people,dc=example,dc=org
~~~

Đọc danh sách DN thành viên:

~~~java
DirContextOperations group = ldapTemplate.lookupContext(groupDn);
String[] members = group.getStringAttributes("member");

if (members != null) {
    for (String memberDn : members) {
        System.out.println(memberDn);
    }
}
~~~

Ví dụ này nằm trong service đã có **ldapTemplate** và **groupDn** (một **Name** tương đối với base DN của ContextSource). Không dựa vào thứ tự trả về của **member** để quyết định ai là thành viên đầu tiên; thuộc tính đa giá trị thông thường không phải danh sách có thứ tự.

### 3.2. Thuộc tính nhị phân

Một thuộc tính LDAP như **jpegPhoto** có thể chứa dữ liệu nhị phân:

~~~java
Object raw = ctx.getObjectAttribute("jpegPhoto");

if (raw instanceof byte[] photoBytes) {
    if (photoBytes.length > 1_000_000) {
        throw new IllegalArgumentException("Ảnh vượt giới hạn");
    }
    // Xử lý byte[] theo logic ứng dụng, không ghi dữ liệu ảnh ra log.
}
~~~

Không dùng **getStringAttribute("jpegPhoto")** rồi tự ép kiểu sang ảnh. Cũng không giả định mọi kiểu giá trị từ directory đáng tin: cần kiểm tra kiểu thực tế, độ dài, schema và quyền truy cập trước khi dùng dữ liệu ở tầng HTTP/UI.

## 4. Cấu hình Spring Boot cho các ví dụ

Giả sử ứng dụng dùng Spring Boot cùng Spring LDAP:

~~~groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-ldap")
}
~~~

~~~yaml
spring:
  ldap:
    urls: ldaps://ldap.example.org:636
    base: dc=example,dc=org
    username: uid=svc-app,ou=service-accounts,dc=example,dc=org
    password: ${LDAP_BIND_PASSWORD}
~~~

Các ví dụ sau giả định:

1. Directory đã có suffix **dc=example,dc=org**, các nhánh **ou=people** và **ou=groups**.
2. LDAP server hỗ trợ schema **inetOrgPerson** và **groupOfNames**.
3. JVM tin CA của máy chủ LDAPS và xác minh **hostname SAN**; không dùng cách bỏ qua kiểm tra TLS.
4. Bind account có quyền đọc/ghi **đúng những entry cần thiết**. Nên tách quyền read-only và writer theo yêu cầu ứng dụng thật.
5. Mỗi **Name** truyền vào LdapTemplate là DN **tương đối với base=dc=example,dc=org**, trừ trường hợp API đã được thiết kế khác.

Ví dụ:

~~~text
LDAP base:          dc=example,dc=org
DN đầy đủ:          uid=an,ou=people,dc=example,dc=org
DN truyền lookup:   uid=an,ou=people
~~~

Nếu cấu hình base đã có **dc=example,dc=org**, không ghép lặp nó vào DN tương đối rồi đưa thẳng vào **lookupContext**.

## 5. Đọc một entry bằng lookupContext

Khi biết DN của entry, dùng **LdapTemplate.lookupContext(Name)** để nhận một **DirContextOperations**:

~~~java
package org.example.directory;

import java.util.Arrays;
import javax.naming.Name;

import org.springframework.ldap.core.DirContextOperations;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;
import org.springframework.stereotype.Service;

@Service
public class EntryInspector {
    private final LdapTemplate ldapTemplate;

    public EntryInspector(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public PersonView getPerson(String uid) {
        validateUid(uid);

        Name dn = LdapNameBuilder.newInstance("ou=people")
                .add("uid", uid)
                .build();

        DirContextOperations ctx = ldapTemplate.lookupContext(dn);

        String actualUid = ctx.getStringAttribute("uid");
        String cn = ctx.getStringAttribute("cn");
        String sn = ctx.getStringAttribute("sn");
        String mail = ctx.getStringAttribute("mail");
        String[] classes = ctx.getStringAttributes("objectClass");

        if (actualUid == null || cn == null || sn == null) {
            throw new IllegalStateException(
                    "Entry thiếu thuộc tính theo hợp đồng ứng dụng");
        }

        return new PersonView(
                actualUid, cn, sn, mail,
                classes == null ? new String[0] : classes.clone());
    }

    private static void validateUid(String uid) {
        if (uid == null || !uid.matches("[A-Za-z0-9._-]{1,64}")) {
            throw new IllegalArgumentException("uid không hợp lệ");
        }
    }

    public record PersonView(
            String uid, String cn, String sn,
            String mail, String[] objectClasses) {}
}
~~~

Ở đây **LdapNameBuilder** bảo vệ cú pháp DN bằng cách tạo một **RDN uid** hợp lệ, thay vì nối chuỗi raw input. Code kiểm tra một số thuộc tính bắt buộc của hợp đồng ứng dụng; LDAP server có thể có schema và ACL khác khiến dữ liệu nhận về không như mong đợi.

**Điều kiện quan trọng:** phương thức này chỉ đúng khi entry được đặt RDN theo **uid** ngay dưới **ou=people**. Nếu directory đặt RDN bằng **cn** hoặc người dùng nằm trong OU lồng nhau, cần tìm bằng filter để lấy DN thật, không đoán đường đi từ uid.

### 5.1. Đọc chọn lọc qua ContextMapper

LdapTemplate có overload **lookup(Name, String[], ContextMapper<T>)** cho phép yêu cầu chỉ những thuộc tính cần đọc:

~~~java
import java.util.List;
import javax.naming.Name;

import org.springframework.ldap.core.ContextMapper;
import org.springframework.ldap.core.DirContextOperations;
import org.springframework.ldap.support.LdapNameBuilder;

Name dn = LdapNameBuilder.newInstance("ou=people")
        .add("uid", "an")
        .build();

ContextMapper<String> mapper = rawContext -> {
    DirContextOperations ctx = (DirContextOperations) rawContext;
    return ctx.getStringAttribute("cn");
};

String cn = ldapTemplate.lookup(
        dn, new String[]{"cn"}, mapper);
~~~

Với **ContextMapper**, tham số được ánh xạ từ một context, thường là **DirContextAdapter**. Khi chỉ cần attributes mà không cần các tiện ích của adapter, **AttributesMapper** là lựa chọn đơn giản hơn:

~~~java
import org.springframework.ldap.core.AttributesMapper;

String name = ldapTemplate.lookup(
        dn,
        new String[]{"cn"},
        (AttributesMapper<String>) attrs ->
                (String) attrs.get("cn").get());
~~~

Việc yêu cầu chỉ **cn** giúp tránh kéo những thuộc tính không cần cho danh sách hiển thị. Nếu dùng **ContextMapper** theo cách này, đừng coi các attribute không được yêu cầu là “không tồn tại trên server”.

## 6. Tìm nhiều entry bằng ContextMapper và LdapQueryBuilder

Khi chưa biết DN, hãy tìm theo filter. **LdapTemplate.search(LdapQuery, ContextMapper<T>)** truyền từng entry tìm được cho mapper:

~~~java
package org.example.directory;

import java.util.List;
import org.springframework.ldap.core.ContextMapper;
import org.springframework.ldap.core.DirContextOperations;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.SearchScope;
import org.springframework.stereotype.Service;

import static org.springframework.ldap.query.LdapQueryBuilder.query;

@Service
public class PersonSearchService {
    private final LdapTemplate ldapTemplate;

    public PersonSearchService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<PersonSummary> searchByUid(String uid) {
        if (uid == null || !uid.matches("[A-Za-z0-9._-]{1,64}")) {
            throw new IllegalArgumentException("uid không hợp lệ");
        }

        ContextMapper<PersonSummary> mapper = rawContext -> {
            DirContextOperations ctx =
                    (DirContextOperations) rawContext;

            return new PersonSummary(
                    ctx.getStringAttribute("uid"),
                    ctx.getStringAttribute("cn"),
                    ctx.getStringAttribute("mail"),
                    ctx.getDn().toString());
        };

        return ldapTemplate.search(
                query()
                    .base("ou=people")
                    .searchScope(SearchScope.SUBTREE)
                    .attributes("uid", "cn", "mail")
                    .countLimit(100)
                    .timeLimit(2000)
                    .where("objectClass").is("inetOrgPerson")
                    .and("uid").is(uid),
                mapper);
    }

    public record PersonSummary(
            String uid, String cn, String mail,
            String relativeDn) {}
}
~~~

Điểm đáng chú ý:

- **ContextMapper** đọc được **ctx.getDn()** bên cạnh thuộc tính, hữu ích nếu ứng dụng phải biết tên entry thực tế.
- **getDn()** của adapter được mô tả là DN tương đối với base đã thiết lập. Hãy kiểm tra quy ước base của ContextSource và cách mapper được gọi trước khi hiển thị hoặc dùng DN ở nơi khác.
- **LdapQueryBuilder** mã hóa giá trị filter; không ghép **(uid=** với chuỗi do người dùng nhập.
- **countLimit**, **timeLimit** và **attributes** giới hạn lượng dữ liệu/chi phí; chúng không thay thế quyền đọc, timeout kết nối hoặc kiểm thử hiệu năng.
- Nếu directory có nhiều entry cùng uid dưới các OU khác nhau, phương thức trả **List** là chính xác hơn việc tự giả định uid duy nhất trên toàn cây.

**ContextMapper và AttributesMapper là hai lựa chọn khác nhau**, không phải một cái luôn tốt hơn cái còn lại. Nếu chỉ đọc vài attribute để xây DTO, AttributesMapper thường đơn giản; nếu cần DN và các phương thức của DirContextOperations, ContextMapper rất thuận tiện.

## 7. Tạo entry mới với DirContextAdapter

Tạo entry LDAP không chỉ là đặt DN. Server kiểm tra **objectClass**, các thuộc tính **MUST/MAY**, schema và ACL. Với **inetOrgPerson**, thuộc tính **cn** và **sn** bắt buộc thông qua chuỗi kế thừa **person → organizationalPerson → inetOrgPerson**.

Ví dụ dùng **new DirContextAdapter(dn)**:

~~~java
package org.example.directory;

import javax.naming.Name;

import org.springframework.ldap.core.DirContextAdapter;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;
import org.springframework.stereotype.Service;

@Service
public class PersonWriter {
    private final LdapTemplate ldapTemplate;

    public PersonWriter(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public void createPerson(
            String uid, String commonName,
            String surname, String email) {
        if (uid == null || !uid.matches("[A-Za-z0-9._-]{1,64}")) {
            throw new IllegalArgumentException("uid không hợp lệ");
        }
        if (commonName == null || commonName.isBlank()
                || surname == null || surname.isBlank()) {
            throw new IllegalArgumentException("cn/sn bắt buộc");
        }

        Name dn = LdapNameBuilder.newInstance("ou=people")
                .add("uid", uid)
                .build();

        DirContextAdapter ctx = new DirContextAdapter(dn);
        ctx.setAttributeValues("objectClass", new String[]{
                "top", "person", "organizationalPerson", "inetOrgPerson"
        });
        ctx.setAttributeValue("uid", uid);
        ctx.setAttributeValue("cn", commonName);
        ctx.setAttributeValue("sn", surname);

        if (email != null && !email.isBlank()) {
            ctx.setAttributeValue("mail", email);
        }

        ldapTemplate.bind(ctx);
    }
}
~~~

Ở đây:

1. **DirContextAdapter(dn)** được tạo ở trạng thái dành cho entry mới, chứa DN cần bind.
2. **setAttributeValues** phù hợp cho **objectClass** vì objectClass là thuộc tính đa giá trị.
3. **setAttributeValue** đặt một giá trị cho **uid/cn/sn/mail**.
4. **ldapTemplate.bind(ctx)** tạo entry trên LDAP server với DN/attributes mà adapter cung cấp.

**Adapter không tự tạo các parent**: **ou=people,dc=example,dc=org** phải có trước. Nếu DN bị trùng, thao tác tạo thường thất bại với lỗi **entryAlreadyExists**. Nếu thiếu **sn**, sai objectClass hoặc không có ACL, server từ chối thao tác mặc dù class Java vẫn biên dịch.

**Không cần gọi setUpdateMode(true) cho adapter mới chỉ dùng để bind**. Update mode dành cho tính toán khác biệt khi cập nhật entry đã tồn tại.

## 8. Cập nhật entry với lookupContext và modifyAttributes

**Đây là phần DirContextAdapter đặc biệt hữu ích.** Thay vì tự xây một mảng **ModificationItem[]** cho từng trường, ta tải adapter của entry đã tồn tại, sửa các thuộc tính cần thiết rồi để adapter tính ra các thay đổi.

Ví dụ chỉnh số điện thoại và mô tả:

~~~java
package org.example.directory;

import javax.naming.Name;
import org.springframework.ldap.core.DirContextOperations;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;
import org.springframework.stereotype.Service;

@Service
public class PersonUpdater {
    private final LdapTemplate ldapTemplate;

    public PersonUpdater(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public void updateContact(
            String uid, String phone, String description) {
        if (uid == null || !uid.matches("[A-Za-z0-9._-]{1,64}")) {
            throw new IllegalArgumentException("uid không hợp lệ");
        }

        Name dn = LdapNameBuilder.newInstance("ou=people")
                .add("uid", uid)
                .build();

        // Đọc dữ liệu hiện tại: adapter ở update mode.
        DirContextOperations ctx = ldapTemplate.lookupContext(dn);

        // Chỉ sửa những thuộc tính nghiệp vụ được phép thay đổi.
        ctx.setAttributeValue("telephoneNumber", phone);
        ctx.setAttributeValue("description", description);

        // Spring LDAP tạo các ModificationItem dựa trên thay đổi.
        ldapTemplate.modifyAttributes(ctx);
    }
}
~~~

**lookupContext** mang về entry đã tồn tại với trạng thái theo dõi thay đổi phù hợp. Khi gọi **setAttributeValue**, adapter so sánh với dữ liệu ban đầu và chuẩn bị các modification. **modifyAttributes(ctx)** dùng **ctx.getDn()** và **ctx.getModificationItems()** để gửi LDAP Modify operation.

So với việc đọc rồi ghi lại toàn bộ entry qua rebind, **modifyAttributes** giúp giới hạn thay đổi vào những thuộc tính được sửa, giảm nguy cơ tác động ngoài ý muốn tới các trường khác. Tuy nhiên, đây không phải cơ chế khóa lạc quan tự động: **hai client đồng thời sửa cùng thuộc tính vẫn có thể ghi đè thay đổi của nhau**, trừ khi ứng dụng/server triển khai điều kiện cạnh tranh phù hợp.

### 8.1. Adapter tính thay đổi như thế nào?

Đoạn code minh họa:

~~~java
DirContextOperations ctx = ldapTemplate.lookupContext(dn);

ctx.setAttributeValue("description", "Chuyen sang team platform");
ctx.setAttributeValue("telephoneNumber", "+84 28 2222 3333");

// Có thể xem để chẩn đoán; thường không cần tự xây mảng này.
javax.naming.directory.ModificationItem[] changes =
        ctx.getModificationItems();

ldapTemplate.modifyAttributes(ctx);
~~~

Các loại thay đổi LDAP có thể gồm **ADD_ATTRIBUTE**, **REPLACE_ATTRIBUTE**, **REMOVE_ATTRIBUTE**. Adapter tính các modification dựa trên trạng thái đã đọc và những cập nhật đã đặt, không phải lúc nào cũng phát sinh **REPLACE** cho toàn bộ entry.

Hãy phân biệt:

- **setAttributeValue("description", "...")**: đặt một giá trị cho thuộc tính ở adapter.
- **getModificationItems()**: lấy danh sách thay đổi dự kiến.
- **ldapTemplate.modifyAttributes(ctx)**: **thực sự gửi thao tác thay đổi** tới server.

Chỉ gọi setter lên adapter **chưa cập nhật LDAP server**. Và chỉ đọc **getModificationItems()** cũng không thực thi thay đổi.

### 8.2. Update mode và phương thức update()

**DirContextAdapter.setUpdateMode(boolean)** điều khiển việc adapter có theo dõi thay đổi tương đối với dữ liệu gốc hay không:

| Trạng thái | Ý nghĩa |
| --- | --- |
| **new DirContextAdapter(dn)** | Dành cho entry mới; đặt attributes để bind |
| **lookupContext(dn)** | Entry đã tồn tại; adapter thường ở **update mode** |
| **setUpdateMode(true)** | Cho phép tính modification của một adapter được khởi tạo phù hợp để cập nhật |
| **getModificationItems()** | Trả các thay đổi mà adapter đang theo dõi |
| **update()** của adapter | Cập nhật trạng thái nội bộ và **xóa danh sách modification đang theo dõi** |

Đừng nhầm **ctx.update()** với **ldapTemplate.modifyAttributes(ctx)**. **ctx.update() không phải cách lưu dữ liệu lên LDAP server**; nó làm mới trạng thái/ghi nhận các thay đổi trong adapter và có thể khiến danh sách modification trở thành rỗng. Vì vậy không gọi **ctx.update()** ngay trước **modifyAttributes(ctx)** khi bạn muốn gửi những thay đổi vừa tính.

Khi tự dựng adapter từ Attributes để cập nhật thay vì nhận từ lookup, phải thiết lập **DN**, dữ liệu gốc và **update mode** chính xác. Cách đơn giản và ít lỗi hơn là **lookupContext(dn)** rồi sửa các trường cần thiết.

## 9. Thuộc tính đa giá trị: set, add và remove

Đối với **objectClass**, **member**, **uniqueMember** hoặc những thuộc tính đa giá trị khác, cần chọn đúng ý định của thao tác:

| Phương thức | Ý định |
| --- | --- |
| **setAttributeValues(name, values)** | Đặt lại tập giá trị của thuộc tính |
| **addAttributeValue(name, value)** | Bổ sung một giá trị |
| **removeAttributeValue(name, value)** | Loại bỏ một giá trị cụ thể |
| **getStringAttributes(name)** | Đọc các giá trị chuỗi hiện có |
| **getObjectAttributes(name)** | Đọc các giá trị object hiện có |

Ví dụ một entry nhóm dùng **groupOfNames**:

~~~ldif
dn: cn=backend,ou=groups,dc=example,dc=org
objectClass: top
objectClass: groupOfNames
cn: backend
member: uid=an,ou=people,dc=example,dc=org
member: uid=binh,ou=people,dc=example,dc=org
~~~

Nếu muốn thêm Chi vào nhóm mà không thay toàn bộ danh sách:

~~~java
import javax.naming.Name;
import org.springframework.ldap.core.DirContextOperations;
import org.springframework.ldap.support.LdapNameBuilder;

Name groupDn = LdapNameBuilder.newInstance("ou=groups")
        .add("cn", "backend")
        .build();

Name fullMemberDn = LdapNameBuilder
        .newInstance("dc=example,dc=org")
        .add("ou", "people")
        .add("uid", "chi")
        .build();

DirContextOperations group = ldapTemplate.lookupContext(groupDn);
group.addAttributeValue("member", fullMemberDn);
ldapTemplate.modifyAttributes(group);
~~~

Chú ý **hai loại DN** trong ví dụ:

- **groupDn** là DN **tương đối** để LdapTemplate định vị entry nhóm theo base đã cấu hình.
- **fullMemberDn** là **DN đầy đủ** được lưu như một giá trị của thuộc tính **member**.

Như vậy không được tự lược bỏ **dc=example,dc=org** khỏi DN tham chiếu thành viên chỉ vì ContextSource có base đó.

### 9.1. Vì sao nên truyền Name thay vì String cho giá trị DN?

**DirContextAdapter** hiểu các giá trị **javax.naming.Name** khi tính thay đổi thuộc tính chứa DN. Hai cách viết một DN khác nhau về chữ hoa/thường hoặc khoảng trắng giữa các RDN có thể đại diện cùng một tên LDAP. Sử dụng **Name** giúp adapter so sánh giá trị theo ngữ nghĩa DN khi phù hợp, tránh phát sinh thêm/xóa không cần thiết do so sánh chuỗi thuần túy.

Ví dụ:

~~~text
uid=an,ou=people,dc=example,dc=org
UID=an, OU=people, DC=example, DC=org
~~~

Hai chuỗi trên có thể tương ứng cùng một DN theo cú pháp và matching rule LDAP. Không sử dụng **String.equals(...)** làm tiêu chuẩn duy nhất để quyết định membership thay đổi.

Đây là khả năng hỗ trợ tính modification của adapter, **không** có nghĩa mọi directory đều cho phép mọi giá trị DN, hoặc server tự kiểm tra tài khoản được tham chiếu tồn tại.

### 9.2. Xóa một thành viên, không xóa cả thuộc tính

~~~java
DirContextOperations group = ldapTemplate.lookupContext(groupDn);
group.removeAttributeValue("member", fullMemberDn);
ldapTemplate.modifyAttributes(group);
~~~

**removeAttributeValue** xóa một giá trị cụ thể khỏi thuộc tính trong adapter. Nó không phải yêu cầu xóa cả entry nhóm. Với **groupOfNames**, **member** là thuộc tính bắt buộc: nếu bạn xóa **thành viên cuối cùng**, server có thể từ chối do vi phạm schema.

Khi nhiều client cùng sửa membership, nên cân nhắc thao tác LDAP Modify có kiểm tra điều kiện, quy tắc bảo toàn membership và việc đọc lại trạng thái. Adapter giúp so sánh giá trị nhưng không tự bảo đảm transaction hay concurrency cho hệ thống.

### 9.3. Khác nhau giữa setAttributeValues và addAttributeValue

~~~java
// Thay tập giá trị dự kiến bằng hai DN:
group.setAttributeValues("member", new Object[]{memberDn1, memberDn2});

// Chỉ bổ sung một DN:
group.addAttributeValue("member", memberDn3);
~~~

**setAttributeValues** thường dùng khi ứng dụng quản lý **toàn bộ tập giá trị**; **addAttributeValue** thích hợp khi chỉ thêm một thành viên. Khi update mode hoạt động, adapter có thể tính các thao tác thêm/xóa riêng lẻ thay vì thay thế toàn bộ thuộc tính đa giá trị.

**Đừng dựa vào thứ tự của thuộc tính đa giá trị** nếu schema không quy định thứ tự. Overload **setAttributeValues(name, values, orderMatters)** cho phép nêu rõ liệu đổi thứ tự có cần được coi là thay đổi; chỉ đặt **orderMatters=true** khi thuộc tính và nghiệp vụ thực sự có thứ tự.

Với thuộc tính **không có equality matching rule**, một số server không hỗ trợ thao tác xóa từng giá trị giống các thuộc tính thông thường. Trong các phiên bản Spring LDAP hỗ trợ, có thể tùy chỉnh chiến lược tính modification để buộc thay thế toàn bộ thuộc tính; cần kiểm tra API theo phiên bản và schema đích. Đừng tự động áp dụng cùng chiến lược sửa member cho mọi thuộc tính.

## 10. Chọn giữa ContextMapper, AttributesMapper và ODM

Một use case chỉ hiển thị tên/email thường không cần giữ toàn bộ DirContextAdapter:

~~~java
import org.springframework.ldap.core.AttributesMapper;

List<String> names = ldapTemplate.search(
        query().base("ou=people")
               .attributes("cn")
               .where("uid").is("an"),
        (AttributesMapper<String>) attrs ->
                (String) attrs.get("cn").get());
~~~

Khi muốn dùng DN, đọc nhiều giá trị hoặc sửa dữ liệu có theo dõi thay đổi, **ContextMapper/DirContextOperations** thường phù hợp hơn:

~~~java
import org.springframework.ldap.core.ContextMapper;
import org.springframework.ldap.core.DirContextOperations;

ContextMapper<String> mapper = raw -> {
    DirContextOperations ctx = (DirContextOperations) raw;
    return ctx.getDn() + " -> " + ctx.getStringAttribute("cn");
};
~~~

Nếu ứng dụng chủ yếu CRUD đối tượng theo schema cố định, **Spring Data LDAP ODM/repository** giúp giảm mã ánh xạ thủ công:

~~~java
import javax.naming.Name;
import org.springframework.ldap.odm.annotations.Attribute;
import org.springframework.ldap.odm.annotations.Entry;
import org.springframework.ldap.odm.annotations.Id;

@Entry(
    base = "ou=people",
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
    private String cn;

    @Attribute(name = "sn")
    private String sn;

    public PersonEntry() {}
    // Getter và setter phù hợp với ứng dụng.
}
~~~

| Tiêu chí | AttributesMapper | ContextMapper + DirContextAdapter | ODM / LdapRepository |
| --- | --- | --- | --- |
| Đọc dữ liệu đơn giản | Tốt | Tốt | Tốt |
| Lấy DN của entry trong mapper | Không trực tiếp từ Attributes | **ctx.getDn()** | **@Id** |
| Thuộc tính nhiều giá trị | Tự xử lý Attributes/Attribute | **getStringAttributes/getObjectAttributes** | Mapping theo property |
| Theo dõi thay đổi để modify | Không phải mục tiêu chính | **getModificationItems** | Hạ tầng ODM/repository xử lý |
| Kiểm soát thao tác từng thuộc tính | Thường dùng LdapTemplate riêng | **set/add/remove attribute** | Ít tường minh hơn |
| Mức phụ thuộc entity class | Không bắt buộc ODM | Không bắt buộc ODM | Cần ODM metadata |

Ba cách tiếp cận có thể cùng tồn tại trong một ứng dụng. Ví dụ: repository để đọc profile thường ngày, LdapTemplate + ContextMapper để kiểm tra DN/thuộc tính hiếm gặp, và DirContextAdapter để thay đổi thuộc tính nhóm một cách tường minh.

## 11. Các giới hạn quan trọng của DirContextAdapter

### 11.1. Adapter chỉ biết thuộc tính đã được nạp

LDAP server có những **operational attributes** như createTimestamp, modifyTimestamp hoặc thông tin đặc thù của nhà cung cấp. Nhiều operational attribute không được trả về trong search thông thường nếu client không yêu cầu.

Nếu adapter không được nạp thuộc tính ấy, **attributeExists** hoặc **removeAttributeValue** có thể không xử lý theo điều bạn hình dung, vì đối với adapter thuộc tính đang “không có”. Muốn đọc operational attribute hợp lệ cần dùng overload lookup/search có danh sách thuộc tính phù hợp, đồng thời kiểm tra server có trả về và account có quyền hay không.

~~~java
import org.springframework.ldap.core.ContextMapper;
import org.springframework.ldap.core.DirContextOperations;

ContextMapper<String> mapper = raw -> {
    DirContextOperations ctx = (DirContextOperations) raw;
    return ctx.getStringAttribute("modifyTimestamp");
};

String modifiedAt = ldapTemplate.lookup(
        personDn, new String[]{"modifyTimestamp"}, mapper);
~~~

Ví dụ nằm trong service đã có **personDn** và ldapTemplate. **modifyTimestamp** thường là thuộc tính do server quản lý; không viết logic cố cập nhật hoặc xóa nó như thuộc tính nghiệp vụ. Nếu server không hỗ trợ, không trả hoặc không cho đọc, kết quả có thể null.

### 11.2. Thay đổi objectClass và thuộc tính RDN không đơn giản

Ví dụ bạn đã tạo một **inetOrgPerson**; không thể biến entry ấy thành **organizationalUnit** chỉ bằng cách thay giá trị objectClass mà bỏ qua ràng buộc STRUCTURAL schema.

Tương tự, **ctx.setAttributeValue("uid", "an2")** không mặc nhiên thực hiện **LDAP Modify DN** để đổi RDN từ **uid=an** sang **uid=an2**. Đổi tên/di chuyển entry cần quy trình rename/modify DN phù hợp, có thể kéo theo cập nhật tham chiếu nhóm và quy tắc ACL.

### 11.3. Không tự giải quyết concurrency

Giả sử:

1. Client A đọc **telephoneNumber=111**.
2. Client B đọc **telephoneNumber=111**, rồi đổi thành **222**.
3. Client A đổi thành **333** và ghi sau.

Adapter giúp tính giá trị cần thay từ dữ liệu A đã đọc nhưng **không tự phát hiện** rằng B vừa cập nhật. Với dữ liệu có yêu cầu chặt về đồng thời, cần cơ chế kiểm tra phiên bản/điều kiện trên server nếu hỗ trợ, hoặc quy trình đối soát nghiệp vụ.

### 11.4. Adapter không thay thế server-side validation

DirContextAdapter không xác nhận LDAP server có schema **inetOrgPerson**, liệu **mail** có hợp lệ theo cú pháp hay không, tài khoản có quyền sửa **member**, hoặc DN đích đã tồn tại. Những điều đó được kiểm tra ở LDAP server hoặc ứng dụng trước khi gửi request.

### 11.5. Không dùng adapter như một Context JNDI đầy đủ

Một số phương thức của giao diện JNDI **Context/DirContext** có trên lớp nhằm tương thích kiểu, nhưng không nhất thiết được hỗ trợ đầy đủ. Lựa chọn đáng tin cậy khi tìm kiếm/đọc/ghi là các thao tác được Spring LDAP công bố trên **LdapTemplate/LdapOperations**.

## 12. An toàn khi đọc và sửa thuộc tính

Các nguyên tắc bảo mật vẫn áp dụng ngay cả khi dùng adapter:

- **Giới hạn endpoint:** cấu hình LDAP URL/base DN thuộc nguồn tin cậy; không lấy URL tùy ý từ user rồi kết nối.
- **Bảo vệ kết nối:** dùng LDAPS hoặc StartTLS với kiểm tra CA và hostname; không tắt xác minh certificate.
- **Quyền tối thiểu:** tài khoản chỉ đọc không cần quyền modify, writer chỉ được sửa đúng OU và attribute được phép.
- **DN an toàn:** dùng **LdapNameBuilder** và Name/Rdn; không ghép DN từ request.
- **Filter an toàn:** dùng **LdapQueryBuilder** hoặc Filter API; không tự nối chuỗi filter.
- **Allowlist trường có thể sửa:** client không được gửi trực tiếp tên attribute tùy ý rồi gọi **setAttributeValue(userAttributeName, rawValue)**.
- **Dữ liệu không đáng tin cậy:** kiểm tra kiểu, độ dài, số lượng và cú pháp trước khi dùng; không dùng tên lớp/metadata lấy từ LDAP để dựng tùy ý Java object.
- **Log có chọn lọc:** tránh ghi mật khẩu, binary attribute, PII và toàn bộ dữ liệu LDAP ra log.
- **Giới hạn truy vấn:** giới hạn base/scope/attributes/count/time cho search rộng.

**Lưu ý về JNDI object reconstruction:** DirContextAdapter là lớp bọc được Spring LDAP thiết kế để làm việc với attributes. Nó không phải giấy phép để gọi mọi biến thể **Context.lookup(...)** của JNDI trên dữ liệu không đáng tin cậy. Với luồng nghiệp vụ chỉ cần dữ liệu, dùng mapper cố định và chỉ đọc các trường được phê duyệt.

## 13. Kiểm thử với LDAP directory

Nên có cả **unit test** của mapping và **integration test** với LDAP directory có schema tương đương môi trường đích. Một DirContextAdapter tự tạo trong unit test không kiểm chứng được thao tác bind/modify thật sự được server chấp nhận.

### 13.1. Unit test truy cập thuộc tính

~~~java
package org.example.directory;

import javax.naming.Name;
import java.util.Set;
import org.junit.jupiter.api.Test;
import org.springframework.ldap.core.DirContextAdapter;
import org.springframework.ldap.support.LdapNameBuilder;

import static org.junit.jupiter.api.Assertions.*;

class DirContextAdapterTest {

    @Test
    void readsSingleAndMultiValueAttributes() {
        Name dn = LdapNameBuilder.newInstance("ou=people")
                .add("uid", "an").build();

        DirContextAdapter ctx = new DirContextAdapter(dn);
        ctx.setAttributeValue("cn", "An Tran");
        ctx.setAttributeValues("objectClass",
                new String[]{"top", "person", "inetOrgPerson"});
        // Áp dụng thay đổi vào trạng thái nội bộ của adapter để đọc lại.
        ctx.update();

        assertEquals("An Tran", ctx.getStringAttribute("cn"));
        assertNull(ctx.getStringAttribute("mail"));
        assertEquals(
                Set.of("top", "person", "inetOrgPerson"),
                Set.of(ctx.getStringAttributes("objectClass")));
    }

    @Test
    void computesModificationsForExistingAttributes() {
        Name dn = LdapNameBuilder.newInstance("ou=people")
                .add("uid", "an").build();

        DirContextAdapter ctx = new DirContextAdapter(dn);
        ctx.setAttributeValue("description", "Cu");

        // Ghi nhận giá trị hiện tại như dữ liệu đã nạp.
        ctx.update();
        ctx.setUpdateMode(true);

        ctx.setAttributeValue("description", "Moi");
        assertTrue(ctx.getModificationItems().length > 0);
        // Chỉ kiểm thử adapter; không có LDAP network I/O ở đây.
    }
}
~~~

Trong test đầu, thuộc tính **objectClass** là nhiều giá trị. Tuy nhiên, nếu không cần quan tâm thứ tự, nên so sánh **tập giá trị** thay vì dựa vào thứ tự của getStringAttributes; môi trường directory thực tế có thể trả thứ tự khác nhau. Test thứ hai cho thấy adapter ghi nhận thay đổi, nhưng **không gửi LDAP Modify**.

### 13.2. Integration test: tạo, đọc, cập nhật rồi đọc lại

Chuẩn bị directory thử nghiệm có:

~~~ldif
dn: dc=example,dc=org
objectClass: top
objectClass: domain
dc: example

dn: ou=people,dc=example,dc=org
objectClass: top
objectClass: organizationalUnit
ou: people
~~~

Sau đó chạy các thao tác theo thứ tự:

~~~text
1. PersonWriter.createPerson("test-an", "Test An", "An", "test@example.org")
2. EntryInspector.getPerson("test-an")  -> cn=Test An, sn=An
3. PersonUpdater.updateContact("test-an", "0123456789", "Da cap nhat")
4. ldapTemplate.lookupContext(...) -> telephoneNumber, description mới
5. Dọn entry test bằng ldapTemplate.unbind(dn) nếu có quyền
~~~

Đây là quy trình test, không phải lệnh script chạy tự động. Khi dọn dữ liệu phải giới hạn DN thuộc **OU kiểm thử**, không dùng thao tác unbind trên DN lấy tùy ý từ client.

### 13.3. Ma trận kiểm thử

| Ca kiểm thử | Thao tác | Kết quả cần xác minh |
| --- | --- | --- |
| **Thuộc tính một giá trị** | Đọc **cn** bằng getStringAttribute | Nhận đúng String hoặc null nếu không có |
| **Thuộc tính đa giá trị** | Đọc **objectClass/member** | Nhận các giá trị, không làm mất phần tử |
| **Thuộc tính nhị phân** | Đọc **jpegPhoto** | Kiểm tra kiểu **byte[]** và giới hạn kích thước |
| **Tạo entry** | new adapter → bind(ctx) | Entry thật được tạo với DN/schema hợp lệ |
| **Sửa một thuộc tính** | lookupContext → setAttributeValue → modifyAttributes | Chỉ trường mục tiêu được đổi |
| **Không có thay đổi** | Đặt lại cùng giá trị | Modification không cần thiết được giảm thiểu nếu cơ chế so sánh hỗ trợ |
| **Thêm member** | addAttributeValue với Name | Thành viên mới được thêm đúng, không ghi đè các giá trị cũ |
| **Xóa member** | removeAttributeValue với Name | Chỉ giá trị mục tiêu bị loại bỏ |
| **Xóa thành viên cuối** | GroupOfNames chỉ còn một member | LDAP server từ chối nếu vi phạm MUST |
| **DN đặc biệt** | Username hoặc tên chứa ký tự cần escaping | Builder tạo DN đúng; không mở rộng phạm vi |
| **Attribute thiếu** | Đọc trường không có/không được request | Mapper xử lý null rõ ràng |
| **Sai schema** | Thêm inetOrgPerson thiếu sn | Server trả lỗi schema |
| **ACL** | Dùng tài khoản read-only để modify | Server từ chối, dữ liệu không đổi |
| **TLS** | Dùng certificate sai CA/hostname | Kết nối bị từ chối an toàn |
| **Concurrent update** | Hai client sửa cùng field | Phát hiện khả năng ghi đè và áp chính sách nghiệp vụ |

Khi chạy integration test, log **DN và LDAP result code** cùng thời điểm; tránh log password hoặc thuộc tính bí mật. Test với directory nhúng cần đối chiếu schema/ACL riêng trước khi kết luận giống OpenLDAP hoặc Active Directory thực tế.

## 14. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Hướng giải quyết |
| --- | --- | --- |
| **ClassCastException** khi ép Context | ContextSource không dùng DefaultDirObjectFactory hoặc API trả kiểu khác | Kiểm tra ContextSource/mapper và API lookup |
| **NullPointerException** từ getStringAttributes | Thuộc tính không được trả hoặc không tồn tại | Kiểm tra null; yêu cầu đúng attributes |
| **Chỉ đọc được một objectClass/member** | Dùng getStringAttribute cho thuộc tính đa giá trị | Dùng getStringAttributes/getObjectAttributes |
| **Setter chạy nhưng LDAP không đổi** | Chưa gọi modifyAttributes(ctx) | Gửi LDAP Modify bằng LdapTemplate |
| **getModificationItems rỗng bất ngờ** | Adapter không ở update mode, chưa nạp dữ liệu gốc hoặc gọi update() quá sớm | Ưu tiên lookupContext rồi sửa |
| **entryAlreadyExists (68)** | Tạo trùng DN | Kiểm tra và xử lý xung đột thao tác bind |
| **objectClassViolation (65)** | Thiếu cn/sn, member hoặc schema không hợp lệ | Kiểm tra MUST/MAY và objectClass |
| **noSuchObject (32)** | Sai DN/base hoặc parent không tồn tại | Đối chiếu DN tương đối và đầy đủ |
| **insufficientAccessRights (50)** | Bind account thiếu quyền | Kiểm tra ACL, phân tách read/write |
| **invalidAttributeSyntax (21)** | Kiểu/cú pháp giá trị không phù hợp schema | Kiểm tra attribute type và giá trị |
| **Lỗi TLS/PKIX/hostname** | CA/truststore/SAN chưa đúng | Sửa chứng chỉ/kết nối; không tắt xác minh |
| **Mất update khi nhiều người cùng sửa** | Race condition giữa lookup và modify | Dùng quy trình kiểm soát đồng thời/đối soát |

**Phân biệt lỗi trong Java và lỗi trên LDAP server:** ví dụ **ClassCastException** có thể phát sinh trong mapper trước khi gửi Modify, còn **objectClassViolation** đến từ directory khi server kiểm tra dữ liệu. Chẩn đoán phải xem root cause và bước thực sự đã được thực thi.

## 15. Những hiểu nhầm cần tránh

**“DirContextAdapter là ORM đầy đủ cho LDAP.”** Không. Nó là adapter mức entry/attributes; **Spring Data LDAP ODM** là mô hình ánh xạ declarative bằng @Entry/@Attribute và repository.

**“Thêm setAttributeValue là server đổi ngay.”** Không. Setter thay đổi trạng thái adapter; cần gọi **LdapTemplate.modifyAttributes** hoặc thao tác ghi phù hợp.

**“ctx.update() sẽ gửi thay đổi đến LDAP.”** Không. Đây là cập nhật trạng thái nội bộ adapter, có thể xóa danh sách pending modifications.

**“getStringAttribute lấy được toàn bộ giá trị của attribute.”** Không. Với thuộc tính nhiều giá trị, dùng **getStringAttributes**.

**“getDn luôn trả DN đầy đủ của directory.”** Không. Cần xem base DN/ContextSource; trong Spring LDAP, DN của adapter thường là dạng tương đối với base đã cấu hình.

**“Có Name là không cần kiểm tra schema.”** Không. Name giúp tạo/so sánh DN; objectClass, syntax, ACL và ràng buộc của directory vẫn cần được kiểm tra.

**“Adapter tự chống ghi đè đồng thời.”** Không. Nó tính thay đổi theo snapshot đã đọc, không tự khóa entry trên server.

**“Đọc Attributes qua adapter khiến dữ liệu LDAP tự động đáng tin cậy.”** Không. Giá trị trong directory vẫn có thể đến từ nguồn ít tin cậy; mapper phải kiểm soát trường/kiểu được sử dụng.

## 16. Tổng kết và bài tập

**DirContextAdapter** giúp đơn giản hóa việc truy cập và chỉnh sửa các LDAP attributes trong **LdapTemplate**. Thay vì tự lặp qua JNDI Attribute/NamingEnumeration và tự xây mọi ModificationItem, bạn có thể dùng **getStringAttribute(s)**, **setAttributeValue(s)**, **addAttributeValue**, **removeAttributeValue**, sau đó để adapter hỗ trợ tính thay đổi và gọi **ldapTemplate.modifyAttributes(ctx)**.

Khi cần đọc dữ liệu, chọn **ContextMapper** nếu cần DN và các tiện ích của **DirContextOperations**, hoặc **AttributesMapper** nếu chỉ cần các trường từ Attributes. Với nghiệp vụ CRUD theo class Java cố định, **Spring Data LDAP repository/ODM** vẫn là lựa chọn tốt; các cách có thể kết hợp trong cùng ứng dụng.

Trong mọi trường hợp, cần phân biệt **DN tương đối của thao tác** với **DN đầy đủ của thuộc tính tham chiếu**, dùng **LdapNameBuilder/LdapQueryBuilder** để tránh injection, kiểm tra **objectClass/schema**, quản lý ACL và kết nối LDAPS/StartTLS an toàn, đồng thời xác minh kết quả trên directory thật.

**Bài tập:**

1. Viết một ContextMapper đọc **uid**, **cn**, **sn** và **getDn()** của người dùng. Giải thích vì sao nó có thông tin khác với AttributesMapper.
2. Dùng **new DirContextAdapter(dn)** tạo entry inetOrgPerson. Hãy liệt kê những thuộc tính bắt buộc và giải thích tại sao thiếu **sn** gây lỗi.
3. Đọc một entry, gọi **setAttributeValue("description", "...")** rồi xem **getModificationItems()**. Điều gì xảy ra nếu chưa gọi modifyAttributes?
4. Đọc **objectClass** và **member** bằng getStringAttributes. Vì sao không dựa vào thứ tự các phần tử?
5. Viết chức năng thêm thành viên groupOfNames dùng **Name** và **addAttributeValue**. Vì sao phải phân biệt DN đầy đủ của member với DN tương đối của group?
6. Dự đoán kết quả khi gọi **ctx.update()** trước **ldapTemplate.modifyAttributes(ctx)**. Tại sao đây là sai lầm khi muốn lưu thay đổi?
7. Dùng ContextMapper để đọc **modifyTimestamp** khi server có hỗ trợ; vì sao cần yêu cầu operational attribute một cách tường minh?
8. Thiết kế integration test với hai client cùng sửa **telephoneNumber**. Adapter có tự phát hiện lost update không? Bạn sẽ thêm cơ chế nào nếu dữ liệu yêu cầu tính nhất quán cao?

### Tài liệu tham khảo

- [Spring LDAP — Simplifying Attribute Access and Manipulation with DirContextAdapter](https://docs.spring.io/spring-ldap/reference/dirobjectfactory.html) — ví dụ lookup/search, ContextMapper và tính toán modifications.
- [Spring LDAP — DirContextAdapter API](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/DirContextAdapter.html) — get/set/add/remove attributes, update mode và DN.
- [Spring LDAP — LdapTemplate API](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/LdapTemplate.html) — lookupContext, bind, modifyAttributes, lookup/search.
- [Spring LDAP — FAQ](https://docs.spring.io/spring-ldap/reference/faq.html) — operational attributes và giới hạn dữ liệu trong adapter.
- [RFC 4512 — LDAP: Directory Information Models](https://www.rfc-editor.org/rfc/rfc4512) — DN, attributes, schema và objectClasses.
- [RFC 4514 — String Representation of Distinguished Names](https://www.rfc-editor.org/rfc/rfc4514) và [RFC 4515 — Search Filters](https://www.rfc-editor.org/rfc/rfc4515) — escaping DN/filter.
- [Spring Data LDAP Reference](https://docs.spring.io/spring-data/ldap/reference/) — ODM và repository song song với LdapTemplate.
