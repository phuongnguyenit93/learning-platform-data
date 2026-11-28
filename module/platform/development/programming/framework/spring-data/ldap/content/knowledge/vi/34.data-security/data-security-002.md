# Giới hạn khôi phục đối tượng JNDI từ dữ liệu thư mục không đáng tin cậy

## Mục tiêu bài học

Trong **Spring Data LDAP**, một ứng dụng Java có thể dùng repository để ánh xạ entry LDAP sang đối tượng Java hoặc dùng **LdapTemplate** để tìm kiếm và đọc các thuộc tính trực tiếp. Tuy nhiên, ở tầng thấp hơn, **JNDI (Java Naming and Directory Interface)** còn có khả năng trả về **đối tượng Java** được dựng lại từ dữ liệu lưu trong một naming/directory service. Nếu ứng dụng cho phép đường xử lý này hoạt động trên dữ liệu LDAP do đối tượng không đáng tin cậy kiểm soát, việc đọc thư mục có thể vượt khỏi mục đích lấy dữ liệu.

Bài học trong chương **Bảo mật dữ liệu** này giải thích **rủi ro khôi phục đối tượng JNDI (JNDI object reconstruction)** và cách thu hẹp khả năng đó trong ứng dụng Spring LDAP.

Sau khi học, bạn có thể:

- Phân biệt **đọc Attributes** với **khôi phục đối tượng Java** thông qua JNDI.
- Hiểu các dạng dữ liệu LDAP có liên quan đến Java object reference, object factory hoặc dữ liệu tuần tự hóa.
- Chỉ ra điều kiện khiến dữ liệu thư mục không đáng tin cậy trở thành đầu vào nguy hiểm đối với cơ chế tạo đối tượng.
- Sử dụng **LdapTemplate + AttributesMapper** hoặc **Spring Data LDAP ODM** để ánh xạ một tập thuộc tính được định trước sang kiểu Java của ứng dụng.
- Áp dụng các giới hạn đối với LDAP endpoint, referral, tải mã từ xa, Java deserialization, quyền ghi schema và truy cập theo DN.
- Thiết kế bài kiểm thử cho dữ liệu LDAP bất thường mà không cần dựng một payload khai thác.

## 1. Vì sao dữ liệu trong directory có thể không đáng tin cậy?

LDAP tổ chức các entry theo cây DN. Ví dụ:

~~~text
dc=example,dc=org
├── ou=people
│   ├── uid=an
│   └── uid=binh
└── ou=service-accounts
    └── uid=svc-app
~~~

Ứng dụng kết nối tới LDAP bằng tài khoản dịch vụ, tìm người dùng theo **uid**, rồi hiển thị **cn** và **mail**. Nhìn qua, đây chỉ là thao tác đọc. Nhưng những entry hoặc thuộc tính trong directory có thể do nhiều nguồn thay đổi:

- Người dùng có quyền tự sửa một số thuộc tính trong hồ sơ.
- Một công cụ đồng bộ nhân sự hoặc quy trình nhập dữ liệu ghi nội dung từ bên ngoài.
- Một nhóm quản trị được cấp quyền ghi rộng hơn mức cần thiết.
- Directory bị cấu hình sai ACL, bị xâm nhập hoặc có một referral dẫn tới máy chủ khác.

Vì thế, **kết nối được tới LDAP server hợp lệ không đủ để chứng minh mọi giá trị trong LDAP đều đáng tin cậy**. Ngay cả qua LDAPS, một giá trị do người dùng tự ghi vẫn là dữ liệu từ nguồn có mức tin cậy thấp hơn ứng dụng Java.

**Mối đe dọa cần phòng tránh:** ứng dụng định đọc dữ liệu nhưng vô tình yêu cầu JNDI diễn giải dữ liệu ấy như chỉ dẫn về lớp Java, object factory, reference hoặc luồng đối tượng được serialize. Hậu quả phụ thuộc JDK, thư viện, cấu hình và gadget/class có sẵn; không phải mọi entry chứa tên class đều tự động gây thực thi mã.

## 2. Đọc thuộc tính và khôi phục đối tượng là hai việc khác nhau

Xét hai cách sử dụng JNDI với một DN:

~~~java
import javax.naming.directory.Attributes;
import javax.naming.directory.DirContext;

// Đọc dữ liệu thuộc tính để tự kiểm tra và ánh xạ.
Attributes attrs = dirContext.getAttributes(
        "uid=an,ou=people,dc=example,dc=org",
        new String[] {"uid", "cn", "mail"});

// Gọi lookup tổng quát: kiểu kết quả là Object.
// Tránh dùng đường đi này cho entry do nguồn không đáng tin cậy kiểm soát.
Object value = dirContext.lookup(
        "uid=an,ou=people,dc=example,dc=org");
~~~

Với **getAttributes**, mã ứng dụng nhận tập thuộc tính LDAP để quyết định sẽ đọc và chuyển đổi các giá trị nào. Với **lookup tổng quát của JNDI**, provider có thể tham gia vào cơ chế dựng lại đối tượng, tùy nội dung entry, cấu hình provider và biện pháp bảo vệ của JDK.

Đây là sự khác biệt về **ranh giới tin cậy**:

| Mục đích | Cách tiếp cận | Ý nghĩa bảo mật |
| --- | --- | --- |
| Đọc hồ sơ người dùng | **getAttributes** với danh sách thuộc tính xác định | Ứng dụng chủ động kiểm tra kiểu và giá trị dữ liệu |
| Tìm người dùng theo điều kiện | **SearchControls** chỉ trả attributes, hoặc **LdapTemplate.search** với **AttributesMapper** | Không yêu cầu trả đối tượng Java do provider dựng lại |
| Dựng object từ tên/JNDI reference | **Context.lookup/DirContext.lookup** tổng quát, object factory | Có thêm cơ chế giải thích dữ liệu và tạo instance |
| Phục hồi object từ byte stream | Java deserialization, ví dụ **ObjectInputStream** | Có rủi ro do kiểu đối tượng và đồ thị object không được kiểm soát |

Trong Spring LDAP, **LdapTemplate.lookup(dn, AttributesMapper)** dùng để ánh xạ *Attributes* vào kiểu do lập trình viên xác định. Không nhầm phương thức này với lệnh **DirContext.lookup(...)** tổng quát của JNDI. Khi dùng API, luôn đọc chính xác overload và kiểu dữ liệu callback nhận được.

### 2.1. Những thuộc tính LDAP liên quan đến cơ chế Java object

Một số triển khai JNDI LDAP hiểu những mô tả chuyên biệt dành cho Java object, ví dụ:

| Tên thuộc tính hoặc khái niệm | Vai trò có thể có trong cơ chế JNDI LDAP |
| --- | --- |
| **javaClassName** | Tên lớp Java được mô tả trong entry |
| **javaSerializedData** | Dữ liệu Java object đã được tuần tự hóa |
| **javaFactory** | Tên object factory có thể được dùng để tạo object |
| **javaCodeBase** | Địa chỉ codebase liên quan đến việc tìm lớp của factory theo cơ chế lịch sử |
| **javaReferenceAddress** | Dữ liệu địa chỉ/tham số trong một Java Reference |
| **javaSerializedObject**, **javaNamingReference** | Các objectClass đặc thù của schema Java object trong JNDI LDAP |

Những tên này là **dữ liệu đặc thù của cơ chế ánh xạ đối tượng Java**, không phải thuộc tính cơ bản của entry **inetOrgPerson**. Một entry hồ sơ bình thường chỉ cần các thuộc tính như **uid**, **cn**, **sn**, **mail** theo schema.

Việc entry chứa **javaClassName** hoặc tên một objectClass Java không tự nó chứng minh có lỗ hổng. Rủi ro xuất hiện khi **đường gọi trong ứng dụng hoặc provider** sử dụng metadata đó để dựng object, tải lớp, gọi factory hoặc giải tuần tự hóa bằng những cơ chế có khả năng nguy hiểm.

## 3. Mô hình rủi ro: dữ liệu trở thành hướng dẫn tạo đối tượng

Một đường đi rủi ro có thể được mô tả như sau:

~~~mermaid
flowchart TD
    A["Nguồn không đáng tin cậy sửa entry LDAP"] --> B["Ứng dụng đọc DN/entry"]
    B --> C{"Đường API nào?"}
    C -->|AttributesMapper / getAttributes| D["Chỉ trích xuất trường được phép"]
    D --> E["Kiểm tra kiểu, độ dài và nội dung"]
    E --> F["Tạo DTO do ứng dụng định nghĩa"]
    C -->|JNDI object reconstruction| G["JNDI diễn giải metadata Java object"]
    G --> H["Factory / reference / serialized object tùy cấu hình"]
    H --> I["Rủi ro phụ thuộc JDK, classpath và quyền của ứng dụng"]
~~~

Ví dụ giả định: dịch vụ directory chỉ cần lấy **cn** của người dùng. Một entry có thêm các thuộc tính Java object được dựng nhằm tác động đến JNDI. Nếu mã Java đọc **Attributes** và chỉ chấp nhận **cn** kiểu chuỗi, các thuộc tính thừa không có ý nghĩa đối với mapper đó. Nếu mã gọi đường **lookup** có hỗ trợ dựng object, phạm vi xử lý có thể rộng hơn nhiều.

Các trường hợp thường được bàn đến gồm:

1. **Remote codebase loading:** ở các môi trường JDK cũ hoặc cấu hình thiếu an toàn, cơ chế JNDI có thể cố tìm lớp factory qua một codebase do dữ liệu tham chiếu cung cấp. Các bản JDK được cập nhật đã siết chặt những khả năng này; không nên dựa vào giả định rằng JDK nào cũng có cùng mặc định.
2. **Local object factory:** ngay cả khi cấm tải code từ xa, một factory đã tồn tại trên classpath có thể được tham chiếu và sử dụng nếu cấu hình/API cho phép. Vì thế việc chặn remote codebase **không đồng nghĩa đã vô hiệu hóa mọi cách dựng object**.
3. **Java serialized object:** dữ liệu chứa byte stream của Java object có thể gây rủi ro nếu được giải tuần tự hóa. Chính sách cho phép giải tuần tự hóa và các bộ lọc cũng phụ thuộc phiên bản JDK; trường hợp sử dụng thật phải được thẩm định rõ.
4. **Referral tới LDAP server khác:** nếu ứng dụng tự động đi theo referral, dữ liệu có thể được lấy từ một endpoint nằm ngoài ranh giới tin cậy đã xác định.

Không có một bước đơn giản như “chỉ chặn một thuộc tính” để thay thế kiểm soát đường gọi và quyền dữ liệu. Mục tiêu chính là **không cho dữ liệu LDAP quyết định lớp/factory Java nào được khởi tạo**.

## 4. Mẫu đọc dữ liệu an toàn bằng LdapTemplate

Trong Spring Data LDAP, API thường dùng là repository và **LdapTemplate**. Khi chỉ cần hồ sơ người dùng, ta có thể định nghĩa **DTO** nhỏ, ánh xạ từ **Attributes** và kiểm tra các thuộc tính cần thiết.

Giả sử directory có:

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
~~~

Trong cấu hình Spring LDAP, **base DN = dc=example,dc=org**. Mẫu service Java 17+:

~~~java
package org.example.directory;

import java.util.List;
import java.util.Optional;
import javax.naming.NamingException;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;

import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.stereotype.Service;

import static org.springframework.ldap.query.LdapQueryBuilder.query;

record PersonView(String uid, String fullName, String email) {}

@Service
public class SafePersonDirectory {

    private static final String PEOPLE_BASE = "ou=people";

    private static final AttributesMapper<PersonView> PERSON_MAPPER =
            SafePersonDirectory::toPersonView;

    private final LdapTemplate ldapTemplate;

    public SafePersonDirectory(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public Optional<PersonView> findByUid(String uid) {
        // Quy tắc dữ liệu nghiệp vụ; không nhận DN/filter thô từ client.
        if (uid == null || !uid.matches("[A-Za-z0-9._-]{1,64}")) {
            throw new IllegalArgumentException("uid không hợp lệ");
        }

        List<PersonView> result = ldapTemplate.search(
                query().base(PEOPLE_BASE)
                        .attributes("uid", "cn", "mail")
                        .where("objectClass").is("inetOrgPerson")
                        .and("uid").is(uid),
                PERSON_MAPPER
        );

        if (result.size() > 1) {
            throw new IllegalStateException("Nhiều entry trùng uid");
        }
        return result.stream().findFirst();
    }

    // Package-private để test mapper riêng biệt.
    static PersonView toPersonView(Attributes attributes)
            throws NamingException {
        return new PersonView(
                requiredString(attributes, "uid", 64),
                requiredString(attributes, "cn", 256),
                optionalString(attributes, "mail", 320)
        );
    }

    private static String requiredString(
            Attributes attributes, String name, int maxLength)
            throws NamingException {
        String value = optionalString(attributes, name, maxLength);
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("Thiếu " + name);
        }
        return value;
    }

    private static String optionalString(
            Attributes attributes, String name, int maxLength)
            throws NamingException {
        Attribute attribute = attributes.get(name);
        if (attribute == null || attribute.size() == 0) {
            return null;
        }
        if (attribute.size() != 1) {
            throw new IllegalArgumentException(
                    "Thuộc tính phải có một giá trị: " + name);
        }

        Object raw = attribute.get();
        if (!(raw instanceof String value)
                || value.length() > maxLength) {
            throw new IllegalArgumentException(
                    "Kiểu hoặc độ dài không hợp lệ: " + name);
        }
        return value;
    }
}
~~~

Ví dụ này có những lựa chọn bảo mật chủ ý:

1. **Chỉ tìm trong ou=people**, không cho request tùy ý đổi base DN hoặc duyệt toàn bộ directory.
2. **LdapQueryBuilder** escape giá trị bộ lọc LDAP, không ghép chuỗi điều kiện từ đầu vào.
3. **attributes("uid", "cn", "mail")** yêu cầu chỉ trả các thuộc tính phục vụ nghiệp vụ.
4. **AttributesMapper** trích xuất các giá trị và tự tạo **PersonView** của ứng dụng, không suy luận class Java từ các thuộc tính directory.
5. **instanceof String**, giới hạn độ dài và kiểm tra số lượng giá trị giúp chặn kiểu hoặc cấu trúc dữ liệu bất thường ngay tại ranh giới.
6. Nhóm mã không gọi **ObjectInputStream**, không dùng **javaClassName** để tải lớp, không đưa nội dung directory vào **Class.forName** và không gọi JNDI object factory.

**Lưu ý về giới hạn:** giới hạn độ dài và regex chỉ là ví dụ cho giao diện người dùng này. Chúng không thay cho validation theo đặc tả trường (email, Unicode, giới hạn địa phương...) hoặc chính sách chống lạm dụng truy vấn. Nếu tìm kiếm nhiều kết quả, cần thêm giới hạn kết quả, timeout và phân trang phù hợp.

### 4.1. Với DN đã biết, vẫn có thể ánh xạ Attributes

Khi DN tương đối đã được xây an toàn, ví dụ **uid=an,ou=people**, có thể sử dụng overload của LdapTemplate nhận mapper:

~~~java
import javax.naming.Name;
import org.springframework.ldap.support.LdapNameBuilder;

Name personDn = LdapNameBuilder.newInstance("ou=people")
        .add("uid", "an")
        .build();

PersonView person = ldapTemplate.lookup(
        personDn, SafePersonDirectory::toPersonView);
~~~

Ở đây, **lookup** của Spring LDAP được gọi cùng **AttributesMapper** nên kết quả là DTO do ứng dụng tạo từ Attributes. Nó không có cùng cách sử dụng với lời gọi **DirContext.lookup(dn)** trả đối tượng tổng quát. Dù vậy, cần đánh giá bất cứ API hoặc custom mapper nào tự động phục hồi Java object từ thuộc tính không đáng tin cậy.

### 4.2. Khi dùng Spring Data LDAP repository

Spring Data LDAP **Object-Directory Mapping (ODM)** cho phép ánh xạ entry sang Java class cố định:

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

    @Attribute(name = "mail")
    private String mail;

    public PersonEntry() {}
    // Getter/setter theo nhu cầu của ứng dụng.
}
~~~

Ví dụ repository:

~~~java
import org.springframework.data.ldap.repository.LdapRepository;

public interface PersonRepository extends LdapRepository<PersonEntry> {
}
~~~

Ở mô hình này, **PersonEntry** là kiểu do mã ứng dụng định nghĩa. Các annotation của Spring LDAP hướng dẫn ánh xạ trường; chúng **không phải chỉ thị lấy tên lớp từ entry LDAP để tải tùy ý vào JVM**. Tuy nhiên, nếu ứng dụng tự viết converter, custom repository, custom ContextMapper hoặc gọi JNDI tổng quát để khôi phục object thì phải kiểm toán những đoạn code đó. Một lớp ODM thông thường không tự động bảo vệ mọi đoạn JNDI bên ngoài repository.

## 5. Thiết lập ranh giới tin cậy cho JNDI/LDAP

### 5.1. Cố định endpoint, bảo vệ kết nối và quyền ghi

Ví dụ Spring Boot:

~~~yaml
spring:
  ldap:
    urls: ldaps://ldap.example.org:636
    base: dc=example,dc=org
    username: uid=svc-read,ou=service-accounts,dc=example,dc=org
    password: ${LDAP_BIND_PASSWORD}
~~~

Trong hệ thống thực tế:

- **Cố định URL và cổng LDAP** bằng cấu hình tin cậy; không nhận một URL kiểu **ldap://...** tùy ý từ request rồi chuyển vào JNDI.
- **Dùng LDAPS hoặc StartTLS** với xác minh CA/chứng chỉ và hostname. TLS giúp bảo vệ đường truyền và xác thực server, không tự xác nhận rằng nội dung mỗi entry là an toàn.
- **Phân quyền tài khoản dịch vụ:** tài khoản chỉ đọc hồ sơ không cần quyền tạo/sửa objectClass hoặc những thuộc tính chứa metadata Java object. Giới hạn phạm vi đọc theo nhánh và thuộc tính khi có thể.
- **Bảo vệ mật khẩu bind** trong secret manager hoặc biến môi trường; không ghi chúng vào source code, log, hoặc payload phản hồi.
- **Giới hạn quyền quản trị schema** và cơ chế nhập dữ liệu. Chỉ tài khoản đủ thẩm quyền mới được thay đổi schema/dữ liệu đặc thù JNDI nếu hệ thống có nhu cầu hợp lệ.

Nếu dữ liệu người dùng được đồng bộ từ nhiều nguồn, hãy xác định rõ nguồn có thể sửa từng trường và cách kiểm tra/ghi audit. Một máy chủ LDAP xác thực hợp lệ vẫn có thể chứa entry do tài khoản không đáng tin cậy tạo.

### 5.2. Không cho phép dữ liệu quyết định class hoặc factory Java

Quy tắc lập trình:

- Chỉ ánh xạ **những thuộc tính đã định nghĩa** sang những class Java đã biết trong mã nguồn.
- Không gọi **Class.forName(valueFromLdap)** hoặc khởi tạo class theo tên nằm trong **javaClassName**, **javaFactory** hoặc các trường dữ liệu tương tự.
- Không tạo **ObjectInputStream** từ **javaSerializedData** hay các byte array lấy từ LDAP không đáng tin cậy.
- Không bật khả năng tải object factory từ remote codebase để “sửa lỗi” JNDI.
- Không dùng JNDI **Context.lookup(...)** tổng quát để đọc hồ sơ người dùng nếu chỉ cần LDAP attributes.
- Không để một custom deserializer/converter chuyển dữ liệu LDAP sang bất kỳ loại Java object nào theo yêu cầu bên ngoài.

Nếu một ứng dụng cũ **thực sự cần** Java object được lưu trong directory, phải coi đó là một giao thức riêng có danh sách class/factory được phê duyệt, giới hạn định dạng và quyền ghi, kiểm toán version/runtime, đồng thời có chiến lược thay thế bằng dữ liệu thuần. Tránh khôi phục object trực tiếp từ dữ liệu do người dùng hoặc đối tác có thể ghi.

### 5.3. Hiểu đúng các biện pháp bảo vệ của JDK

Một số JDK có các thuộc tính hệ thống giới hạn tải class từ remote LDAP codebase hoặc xử lý Java serialized object. Chẳng hạn, **com.sun.jndi.ldap.object.trustURLCodebase** là cấu hình đặc thù của nhà cung cấp JDK/phiên bản, liên quan tới việc tin cậy đường dẫn codebase của object factory.

Các điểm cần nhớ:

1. **Không bật trustURLCodebase=true** như một mẹo để ứng dụng LDAP hoạt động.
2. Kiểm tra **giá trị mặc định và phạm vi hỗ trợ của chính phiên bản JDK** đang triển khai. Một số phiên bản hiện đại siết chặt hoặc thay đổi hành vi JNDI; không khẳng định một thuộc tính hệ thống hoạt động giống nhau ở mọi JDK.
3. Việc chặn remote codebase **không loại bỏ** rủi ro từ local object factory, deserialization hoặc mã ứng dụng tự tạo object từ dữ liệu thư mục.
4. **ObjectInputFilter** (cơ chế lọc deserialization của Java) là một lớp phòng vệ bổ sung nếu ứng dụng buộc phải xử lý dữ liệu serialized, **không thay thế** việc tránh deserialize dữ liệu không đáng tin cậy.

Vì vậy, **ưu tiên loại bỏ đường khôi phục object** trong nghiệp vụ đọc LDAP. Thiết lập JVM, cấu hình container và cập nhật bản vá là những lớp phòng vệ quan trọng nhưng không nên trở thành kiểm soát duy nhất.

### 5.4. Giới hạn referral và endpoint chuyển hướng

**LDAP referral** có thể chỉ đến một LDAP endpoint khác. Đây là cơ chế LDAP độc lập với Java object reference, nhưng vẫn làm thay đổi nơi ứng dụng lấy dữ liệu.

Nếu không có nhu cầu truy vấn xuyên directory, hãy cấu hình JNDI không tự động follow referral. Trong JNDI, có thể dùng:

~~~java
import java.util.Hashtable;
import javax.naming.Context;
import javax.naming.directory.InitialDirContext;

Hashtable<String, Object> env = new Hashtable<>();
env.put(Context.INITIAL_CONTEXT_FACTORY,
        "com.sun.jndi.ldap.LdapCtxFactory");
env.put(Context.PROVIDER_URL,
        "ldaps://ldap.example.org:636/dc=example,dc=org");
env.put(Context.REFERRAL, "throw");

// Thiếu cấu hình xác thực/truststore: đây chỉ minh họa referral policy.
InitialDirContext ctx = new InitialDirContext(env);
~~~

**Context.REFERRAL = "throw"** khiến provider báo referral thay vì âm thầm theo nó; ứng dụng phải xử lý tình huống này theo chính sách của mình. Ví dụ trên chỉ minh họa chính sách referral bằng JNDI thuần, không phải cấu hình kết nối hoàn chỉnh. Trong Spring LDAP, cấu hình cùng chính sách trên **ContextSource/JNDI environment** đang dùng.

Khi nghiệp vụ thật sự yêu cầu follow referral, cần danh sách endpoint được phép, TLS phù hợp, kiểm tra hostname/certificate, giới hạn số lần chuyển hướng và quyền truy cập. Không tự động đi theo mọi địa chỉ trả về từ directory.

## 6. Những hiểu nhầm thường gặp

| Nhận định | Điều cần hiểu |
| --- | --- |
| “Đã dùng LDAPS nên mọi entry đều đáng tin.” | TLS bảo vệ kênh truyền; entry vẫn có thể chứa dữ liệu do tài khoản mức tin cậy thấp ghi. |
| “Ứng dụng chỉ đọc LDAP thì không thể xảy ra vấn đề.” | Một API đọc có thể kích hoạt object reconstruction nếu sử dụng đường JNDI có khả năng dựng object. |
| “Cấm tải codebase từ xa nghĩa là an toàn tuyệt đối.” | Các factory/class cục bộ và deserialization vẫn cần được xem xét. |
| “Mọi lookup của Spring LDAP đều nguy hiểm.” | **LdapTemplate.lookup(dn, AttributesMapper)** ánh xạ Attributes khác với **DirContext.lookup(dn)** tổng quát. |
| “Thêm filter objectClass=inetOrgPerson sẽ vô hiệu mọi JNDI object.” | Filter làm hẹp kết quả nhưng không kiểm soát cách mapper/factory xử lý giá trị và không thay thế ACL. |
| “Chặn thuộc tính javaSerializedData là đủ.” | Cần loại bỏ đường object reconstruction và kiểm tra cả factory/reference, custom converter, referral. |
| “LDAP injection và JNDI object reconstruction là cùng một lỗi.” | LDAP injection thay đổi ngữ nghĩa filter/DN; object reconstruction liên quan đến dữ liệu được chuyển thành object Java. |

Hai vấn đề **LDAP injection** và **JNDI object reconstruction** có thể cùng xuất hiện nếu ứng dụng cho phép đầu vào quyết định DN/filter rồi dùng một API dựng object, nhưng cách khắc phục là **hai lớp kiểm soát khác nhau**: xây DN/filter an toàn **và** giữ dữ liệu LDAP dưới dạng dữ liệu.

## 7. Ví dụ kiểm thử ranh giới dữ liệu

Một kiểm thử đơn vị hữu ích là xác nhận mapper chỉ đọc những trường được phê duyệt, bỏ qua các thuộc tính không liên quan tới đối tượng nghiệp vụ.

~~~java
package org.example.directory;

import javax.naming.directory.Attributes;
import javax.naming.directory.BasicAttributes;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class SafePersonDirectoryTest {

    @Test
    void ignoresUnknownJndiMetadata() throws Exception {
        Attributes attrs = new BasicAttributes(true);
        attrs.put("uid", "an");
        attrs.put("cn", "An Tran");
        attrs.put("mail", "an@example.org");

        // Chỉ là metadata test: không chứa factory hay payload thực thi.
        attrs.put("javaClassName", "example.UnexpectedClass");
        attrs.put("javaCodeBase", "https://untrusted.invalid/classes/");

        PersonView person = SafePersonDirectory.toPersonView(attrs);

        assertEquals("an", person.uid());
        assertEquals("An Tran", person.fullName());
        assertEquals("an@example.org", person.email());
    }

    @Test
    void rejectsUnexpectedAttributeType() {
        Attributes attrs = new BasicAttributes(true);
        attrs.put("uid", "an");
        attrs.put("cn", new byte[] {1, 2, 3});

        assertThrows(IllegalArgumentException.class,
                () -> SafePersonDirectory.toPersonView(attrs));
    }
}
~~~

Test này xác minh **logic mapper**, không chứng minh mọi đường JNDI trong ứng dụng đều an toàn. Trong integration test, cần bảo đảm các hoạt động đọc entry thực sự đi qua **LdapTemplate/AttributesMapper** hoặc ODM đã được kiểm toán, chứ không đi vòng qua **DirContext.lookup** tổng quát.

### 7.1. Ma trận kiểm thử tích hợp

Chuẩn bị một directory thử nghiệm với **dc=example,dc=org**, **ou=people**, schema **inetOrgPerson**, tài khoản đọc hạn chế và kết nối TLS được xác minh. Chạy trên dữ liệu kiểm thử cô lập, không tạo payload thực thi hoặc chạy mã untrusted.

| Ca kiểm thử | Đầu vào / thao tác | Kết quả kỳ vọng |
| --- | --- | --- |
| Hồ sơ hợp lệ | Entry có uid/cn/mail kiểu chuỗi | Chuyển được thành PersonView |
| Thuộc tính thừa | Có thêm tên thuộc tính không nằm trong allowlist | Mapper bỏ qua, dữ liệu đầu ra không đổi |
| Kiểu bất thường | cn trả về byte[] thay vì String | Validation từ chối |
| Thiếu thuộc tính bắt buộc | Thiếu uid hoặc cn | Mapper từ chối, không tạo đối tượng thiếu dữ liệu |
| Nhiều giá trị ở trường đơn | cn có nhiều giá trị | Mapper từ chối thay vì chọn tùy ý |
| Tìm kiếm sai scope | uid tồn tại ngoài ou=people | Truy vấn cố định base không trả entry ngoài phạm vi |
| Đầu vào filter đặc biệt | uid có ký tự điều khiển/filter | Validation hoặc filter builder xử lý, không mở rộng truy vấn |
| Dữ liệu tham chiếu bất thường | Entry có metadata Java không liên quan | Không kích hoạt đường dựng object trong luồng được kiểm toán |
| Referral không tin cậy | Server trả LDAP referral | Theo chính sách **throw/ignore**, không tự động kết nối endpoint ngoài danh sách |
| Bảo vệ kết nối | Chứng chỉ server không hợp lệ | Kết nối thất bại; không tắt xác minh TLS |
| Phân quyền | Bind account chỉ được đọc hồ sơ | Không thể tự sửa các entry hoặc dữ liệu đặc thù Java object |

Khi kiểm tra, nên quan sát log của lớp ứng dụng, yêu cầu LDAP thực tế và phiên bản JDK để xác định **đường API nào đã được gọi**. Không in toàn bộ Attributes hoặc dữ liệu nhạy cảm ra log. Các thử nghiệm về bảo vệ JNDI theo phiên bản cần chạy trong môi trường kiểm soát, không đưa địa chỉ tải mã từ xa hoặc chuỗi serialized không được kiểm chứng vào directory sản xuất.

## 8. Checklist áp dụng vào hệ thống

1. **Lập danh sách tất cả lệnh JNDI** đang dùng: Context.lookup, DirContext.lookup, search có yêu cầu trả Java object, ObjectFactory, custom deserializer, converter; xác định luồng nào đọc LDAP entry có thể bị người dùng sửa.
2. **Chuyển các use case chỉ cần dữ liệu** sang LdapTemplate với AttributesMapper hoặc ODM class cố định. Chỉ trả các attribute cần thiết; validate kiểu, số lượng và độ dài.
3. **Chặn đầu vào tác động đến endpoint và cú pháp**: URL LDAP/base DN nằm trong cấu hình đáng tin; DN dùng LdapNameBuilder, filter dùng LdapQueryBuilder.
4. **Rà soát quyền ghi** vào entry có metadata Java, objectClass đặc thù và nhánh được tra cứu; kiểm tra cả luồng đồng bộ từ hệ thống ngoài.
5. **Kiểm tra JDK và thư viện thực tế**: cập nhật bản vá, duy trì chính sách không tin cậy remote codebase, tránh Java deserialization từ LDAP, dùng bộ lọc nếu buộc phải có.
6. **Giới hạn referral**; chỉ cho phép endpoint đã được xác minh khi có nhu cầu liên directory.
7. **Kiểm thử luồng đọc** với dữ liệu bất thường, bảo đảm không có khởi tạo Java object theo tên class lấy từ LDAP; bổ sung giám sát và logging có chọn lọc.

## 9. Tổng kết và câu hỏi tự luyện

Giới hạn khôi phục đối tượng JNDI từ dữ liệu thư mục không đáng tin cậy là việc **giữ dữ liệu LDAP ở dạng Attributes**, chỉ ánh xạ thành các kiểu đã biết theo nhu cầu nghiệp vụ và **ngăn dữ liệu ấy điều khiển cơ chế tạo Java object**. Cách triển khai thông thường trong **Spring Data LDAP** là dùng repository/ODM với class cố định hoặc **LdapTemplate + AttributesMapper**, cùng kiểm soát DN, filter, quyền LDAP, TLS, referral và phiên bản JDK.

Cần phân biệt **“directory trả về dữ liệu”** với **“JNDI diễn giải dữ liệu để dựng object”**. Chỉ có metadata Java trong một entry không mặc nhiên tạo lỗ hổng; rủi ro phụ thuộc vào đường API được gọi và các khả năng được bật ở runtime. Vì vậy kiểm toán đường xử lý và loại bỏ cơ chế không cần dùng hiệu quả hơn việc chỉ tìm kiếm một tên thuộc tính nguy hiểm.

**Câu hỏi tự luyện:**

1. Vì sao **DirContext.lookup(dn)** tổng quát có ranh giới tin cậy khác **LdapTemplate.lookup(dn, AttributesMapper)**?
2. Tại sao **trustURLCodebase=false** không chứng minh hệ thống an toàn khỏi mọi hình thức khôi phục object?
3. Một entry có **javaClassName** và **javaCodeBase** sẽ trở thành nguy hiểm trong điều kiện nào? Điều gì xảy ra nếu mapper chỉ đọc **uid** và **cn**?
4. Nếu user được phép tự sửa một số thuộc tính LDAP, vì sao LDAPS vẫn không đủ để tin cậy toàn bộ giá trị trả về?
5. Bạn sẽ kiểm thử thế nào để bảo đảm một luồng truy vấn LDAP không đi theo referral ngoài phạm vi và không dựng Java object từ metadata của entry?

### Tài liệu tham khảo

- [Oracle Java — JNDI Objects](https://docs.oracle.com/javase/tutorial/jndi/objects/) — nền tảng về đối tượng trong JNDI, reference và object factory.
- [Oracle Java — JNDI LDAP Provider](https://docs.oracle.com/javase/8/docs/technotes/guides/jndi/jndi-ldap.html) — khả năng và cấu hình của LDAP provider (cần đối chiếu theo phiên bản Java đang sử dụng).
- [OpenJDK JEP 290 — Filter Incoming Serialization Data](https://openjdk.org/jeps/290) — cơ chế lọc dữ liệu deserialization.
- [Spring LDAP Reference](https://docs.spring.io/spring-ldap/reference/) — LdapTemplate, AttributesMapper, truy vấn LDAP.
- [Spring Data LDAP Reference](https://docs.spring.io/spring-data/ldap/reference/) — repository và Object-Directory Mapping.
