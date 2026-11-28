# Ánh xạ context bằng ContextMapper và AbstractContextMapper

Khi tìm kiếm entry trên LDAP, ứng dụng Java thường cần biến dữ liệu directory thành đối tượng nghiệp vụ: hồ sơ nhân viên, thông tin liên hệ, thành viên nhóm hoặc một DTO trả về API. Trong **Spring Data LDAP**, repository có thể tự ánh xạ entry sang entity bằng annotation. Nhưng khi cần chủ động đọc DN, chọn thuộc tính, xử lý giá trị nhiều phần tử hoặc tạo đối tượng chỉ đọc theo yêu cầu, **Spring LDAP** cung cấp hai công cụ quan trọng: `ContextMapper<T>` và `AbstractContextMapper<T>`.

Bài này thuộc chương **Ánh xạ kết quả**, tập trung vào cách **ánh xạ context LDAP sang đối tượng Java** và lựa chọn giữa hai API trên. Để theo dõi được ví dụ, bạn cần biết LDAP entry có DN, `objectClass`, các thuộc tính tuân theo schema, và việc đọc entry phụ thuộc vào URL, base DN, filter và quyền của tài khoản bind. Kết quả mapping sau đó có thể được sử dụng trong ứng dụng Spring Data LDAP bên cạnh repository và `LdapTemplate`.

## 1. Mục tiêu

Sau bài học, bạn có thể:

1. Giải thích vì sao `ContextMapper` nhận **context của entry**, không chỉ nhận một tập `Attributes`.
2. Đọc dữ liệu qua `DirContextOperations`: `getDn()`, `getStringAttribute()` và `getStringAttributes()`.
3. Tự viết `ContextMapper<T>` trực tiếp bằng class hoặc lambda và kế thừa `AbstractContextMapper<T>`.
4. Gắn mapper vào `LdapTemplate.search(...)` và `LdapTemplate.lookup(...)`.
5. Xử lý giá trị tùy chọn, thuộc tính nhiều giá trị, DN tương đối, lỗi schema và quyền đọc.
6. Chọn đúng công cụ giữa `AttributesMapper`, `ContextMapper` và ánh xạ entity bằng `@Entry`/`LdapRepository`.

## 2. Kết quả LDAP không tự trở thành Java object

Giả sử directory thử nghiệm có entry:

~~~ldif
dn: uid=lan,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: lan
cn: Lan Nguyen
sn: Nguyen
mail: lan@example.org
telephoneNumber: +84-28-1234-5678
telephoneNumber: +84-90-123-4567
~~~

LDIF ở trên minh họa một entry LDAP, không phải định dạng mà `LdapTemplate.search(...)` trực tiếp trả về. Mỗi entry có:

- **DN:** tên phân biệt của entry trong cây thư mục.
- **Attributes:** `uid`, `cn`, `mail`, `telephoneNumber`…; thuộc tính có thể có một hoặc nhiều giá trị.
- **Schema/objectClass:** các ràng buộc quy định thuộc tính có thể hoặc phải có. Ví dụ `inetOrgPerson` thường được dùng cho hồ sơ người dùng, nhưng không phải mọi directory đều có schema giống nhau.

Ứng dụng chỉ cần DTO:

~~~java
import java.util.List;

public record PersonContact(
        String relativeDn,
        String uid,
        String displayName,
        String email,
        List<String> phoneNumbers) {
}
~~~

Mapper sẽ đọc từng thuộc tính của entry và tạo `PersonContact`, đồng thời giữ lại DN để định danh entry. Việc gọi getter trên context **chỉ đọc dữ liệu**; tự nó không ghi thay đổi trở lại LDAP.

### Luồng ánh xạ

~~~mermaid
flowchart LR
    A["LDAP server: entry + attributes"] --> B["LdapTemplate search/lookup"]
    B --> C["DirContextOperations"]
    C --> D["ContextMapper hoặc AbstractContextMapper"]
    D --> E["PersonContact / DTO Java"]
~~~

`LdapTemplate` nhận kết quả LDAP, tạo một context adapter tương ứng rồi gọi mapper cho mỗi entry. Với `search`, từng entry được ánh xạ để tạo danh sách; với `lookup`, mapper biến entry được tìm theo DN thành một đối tượng.

## 3. `ContextMapper<T>` là gì?

`org.springframework.ldap.core.ContextMapper<T>` là một giao diện xác định cách chuyển **một context được trả về** thành giá trị kiểu `T`. Phương thức cốt lõi là `mapFromContext(Object ctx)`.

Điểm cần hiểu: tham số được khai báo kiểu `Object` ở hợp đồng mapper, nhưng trong luồng tìm kiếm LDAP thông thường của Spring LDAP, bạn sẽ xử lý nó như một `DirContextOperations` (thường là adapter được Spring tạo từ kết quả entry).

`DirContextOperations` cung cấp API thuận tiện:

| API | Mục đích | Ví dụ |
| --- | --- | --- |
| `getDn()` | Lấy DN mà context adapter đang giữ, dưới dạng `Name`. | `uid=lan,ou=people` trong ví dụ base DN bên dưới. |
| `getStringAttribute("uid")` | Lấy một giá trị dạng chuỗi của thuộc tính. | `lan`. |
| `getStringAttribute("mail")` | Lấy một giá trị chuỗi; có thể không có. | `lan@example.org` hoặc `null`. |
| `getStringAttributes("telephoneNumber")` | Lấy các giá trị chuỗi của một attribute. | Mảng các số điện thoại. |
| `getObjectAttribute(...)` | Lấy giá trị không ép sẵn về `String` khi cần xử lý kiểu khác. | Thuộc tính có giá trị nhị phân/kiểu đặc biệt. |
| `getAttributes()` | Truy cập bộ thuộc tính JNDI để xử lý nâng cao. | Kiểm tra một attribute hoặc metadata. |

**Đối với DN:** `getDn()` trả về DN gắn với context và thường được biểu diễn tương đối với base được cấu hình trong `ContextSource`. Đừng mặc định chuỗi này luôn là **DN tuyệt đối** hoặc là **DN tương đối với search base**. Khi cần DN đầy đủ để trao đổi với hệ thống khác, phải xác định rõ base của context và dựng/chuẩn hóa bằng API DN phù hợp; tránh nối chuỗi không kiểm soát.

### Ví dụ 1 — triển khai `ContextMapper` trực tiếp

~~~java
import java.util.Arrays;
import java.util.List;
import org.springframework.ldap.core.ContextMapper;
import org.springframework.ldap.core.DirContextOperations;

public final class PersonDirectContextMapper
        implements ContextMapper<PersonContact> {

    @Override
    public PersonContact mapFromContext(Object source) {
        DirContextOperations entry = (DirContextOperations) source;

        String[] phones = entry.getStringAttributes("telephoneNumber");
        List<String> phoneNumbers = phones == null
                ? List.of()
                : List.copyOf(Arrays.asList(phones));

        return new PersonContact(
                entry.getDn().toString(),
                entry.getStringAttribute("uid"),
                entry.getStringAttribute("cn"),
                entry.getStringAttribute("mail"),
                phoneNumbers
        );
    }
}
~~~

Mỗi lần ánh xạ, mapper thực hiện ba việc: **đọc context**, **chuyển dữ liệu** và **tạo đối tượng đầu ra**. Không cần gọi LDAP server lần nữa chỉ để lấy thuộc tính đã được trả về cùng kết quả.

Điểm bất tiện là phải ép kiểu `Object` sang `DirContextOperations` trong `mapFromContext`. Khi dùng mapper thường xuyên, `AbstractContextMapper` loại bỏ thao tác lặp này.

### Viết ngắn bằng lambda

Vì `ContextMapper<T>` có một phương thức chức năng, có thể dùng lambda khi logic ngắn:

~~~java
import org.springframework.ldap.core.ContextMapper;
import org.springframework.ldap.core.DirContextOperations;

ContextMapper<String> displayNameMapper = source -> {
    DirContextOperations entry = (DirContextOperations) source;
    return entry.getStringAttribute("cn");
};
~~~

Đây là lựa chọn phù hợp nếu chỉ cần một hoặc vài thuộc tính. Nếu nhiều truy vấn cần cùng quy tắc ánh xạ, tách mapper thành class để tái sử dụng và kiểm thử.

## 4. `AbstractContextMapper<T>` giúp gì?

`org.springframework.ldap.core.support.AbstractContextMapper<T>` là lớp cơ sở thực thi `ContextMapper<T>`. Bạn kế thừa và ghi đè phương thức:

~~~java
protected T doMapFromContext(DirContextOperations ctx)
~~~

Lớp cơ sở đảm nhiệm phần chuyển context về `DirContextOperations` trước khi gọi `doMapFromContext(...)`. Vì vậy, phương thức bạn viết nhận **đúng kiểu dữ liệu** để đọc DN và attribute; không cần ép kiểu thủ công ở mỗi mapper.

### Ví dụ 2 — mapper tái sử dụng với `AbstractContextMapper`

~~~java
import java.util.Arrays;
import java.util.List;
import org.springframework.ldap.core.DirContextOperations;
import org.springframework.ldap.core.support.AbstractContextMapper;

public final class PersonContextMapper
        extends AbstractContextMapper<PersonContact> {

    @Override
    protected PersonContact doMapFromContext(DirContextOperations entry) {
        String uid = entry.getStringAttribute("uid");
        if (uid == null || uid.isBlank()) {
            throw new IllegalArgumentException("Entry thiếu uid bắt buộc");
        }

        String[] phones = entry.getStringAttributes("telephoneNumber");
        List<String> phoneNumbers = phones == null
                ? List.of()
                : List.copyOf(Arrays.asList(phones));

        return new PersonContact(
                entry.getDn().toString(),
                uid,
                entry.getStringAttribute("cn"),
                entry.getStringAttribute("mail"),
                phoneNumbers
        );
    }
}
~~~

Ở đây có hai quyết định có chủ ý:

1. `uid` được xem là bắt buộc đối với DTO này. Nếu server trả entry không có `uid`, mapper báo lỗi thay vì lặng lẽ tạo hồ sơ thiếu định danh. Trong một ứng dụng khác, bạn có thể dùng DN làm định danh chính hoặc đánh dấu dữ liệu chưa hợp lệ theo quy định nghiệp vụ.
2. `telephoneNumber` có thể có **nhiều giá trị** hoặc không có. Code chuẩn hóa thành danh sách rỗng khi attribute không tồn tại; không chỉ lấy số đầu tiên.

Mapper trên dùng mã Java 17+ (record, `List.of`, `List.copyOf`), phù hợp với một ứng dụng Spring Boot thế hệ hiện đại. Nếu directory có số điện thoại bị trống hoặc định dạng không hợp lệ, quy tắc chuẩn hóa cần được định nghĩa rõ ở tầng dịch vụ.

### So sánh cách viết

| Tiêu chí | `ContextMapper<T>` trực tiếp | `AbstractContextMapper<T>` |
| --- | --- | --- |
| Phải viết phương thức | `mapFromContext(Object)` | `doMapFromContext(DirContextOperations)` |
| Có cần ép kiểu ở phần logic? | Có, nếu cần API của `DirContextOperations`. | Không, base class đã thực hiện. |
| Dùng lambda | Có, tiện cho trường hợp rất ngắn. | Không phải giao diện lambda; tạo class kế thừa. |
| Tái sử dụng cho nhiều truy vấn | Có. | Có, thường rõ nghĩa hơn với mapper nhiều bước. |
| Kết quả | Đối tượng kiểu `T`. | Đối tượng kiểu `T`. |
| Có tự lưu dữ liệu lên LDAP? | Không. | Không. |

**Không có khác biệt về mục tiêu:** cả hai dùng để chuyển một entry LDAP thành giá trị Java. `AbstractContextMapper` là cách tổ chức và kiểm soát kiểu tốt hơn khi logic mapping nhiều bước.

## 5. Sử dụng mapper với `LdapTemplate.search(...)`

Đầu tiên, cấu hình Spring Boot để kết nối directory. Ví dụ:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-ldap")
}
~~~

~~~yaml
spring:
  ldap:
    urls: ${LDAP_URL:ldaps://ldap.example.org:636}
    base: ${LDAP_BASE_DN:dc=example,dc=org}
    username: ${LDAP_BIND_DN}
    password: ${LDAP_BIND_PASSWORD}
~~~

`LDAP_BIND_DN` là danh tính dịch vụ có quyền tìm kiếm entry, chẳng hạn `cn=app-reader,ou=services,dc=example,dc=org`. `spring.ldap.base` là gốc directory, còn `ou=people` trong truy vấn dưới đây là nhánh tương đối với gốc ấy. Giá trị mặc định trong ví dụ chỉ để đọc hiểu; phải có server, entry và tài khoản thật tương ứng mới thực thi được.

Service dùng `PersonContextMapper`:

~~~java
import java.util.List;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;
import org.springframework.stereotype.Service;

@Service
public class PersonDirectoryService {
    private final LdapTemplate ldapTemplate;
    private final PersonContextMapper mapper = new PersonContextMapper();

    public PersonDirectoryService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<PersonContact> findByUid(String uid) {
        LdapQuery query = LdapQueryBuilder.query()
                .base("ou=people")
                .attributes("uid", "cn", "mail", "telephoneNumber")
                .where("objectClass").is("inetOrgPerson")
                .and("uid").is(uid);

        return ldapTemplate.search(query, mapper);
    }
}
~~~

Trình tự xử lý:

1. `LdapQueryBuilder` xây yêu cầu tìm kiếm dưới `ou=people` và thêm filter cho `objectClass`, `uid`.
2. `attributes(...)` yêu cầu các thuộc tính cần cho `PersonContact`, giảm dữ liệu truyền về khi entry có nhiều attribute. DN được lưu trong context adapter, không phải một attribute thông thường cần liệt kê như `cn`.
3. `ldapTemplate.search(query, mapper)` gọi mapper cho mỗi entry phù hợp và trả danh sách `PersonContact`. Danh sách rỗng có nghĩa **không tìm thấy entry được trả về** dưới điều kiện/cấu hình/quyền hiện tại, không chứng minh directory không có entry ở nơi khác.

Điều kiện `.where("uid").is(uid)` xử lý giá trị filter theo API Spring LDAP; không nối chuỗi `"(uid=" + uid + ")"` từ dữ liệu không tin cậy. Với các truy vấn có user input, kiểm tra thêm độ dài, format và giới hạn số kết quả ở tầng ứng dụng. Đừng tạo filter trực tiếp từ input mà không escape.

### Trường hợp chỉ cần tên hiển thị

Nếu service không cần cả DTO, một `ContextMapper<String>` ngắn sẽ đủ:

~~~java
import java.util.List;
import org.springframework.ldap.core.ContextMapper;
import org.springframework.ldap.core.DirContextOperations;

ContextMapper<String> mapper = source ->
        ((DirContextOperations) source).getStringAttribute("cn");

List<String> names = ldapTemplate.search(
        LdapQueryBuilder.query()
                .base("ou=people")
                .attributes("cn")
                .where("objectClass").is("inetOrgPerson"),
        mapper);
~~~

Đoạn này minh họa một phần thân phương thức hoặc một đoạn code nơi `ldapTemplate` đã có sẵn. Trong project thật, đặt logic vào service và cân nhắc trả DTO chỉ có các trường được phép công khai.

## 6. Sử dụng mapper với `LdapTemplate.lookup(...)`

Khi đã biết **DN của entry**, dùng `lookup` để đọc entry đích thay vì search theo filter:

~~~java
import javax.naming.Name;
import org.springframework.ldap.support.LdapNameBuilder;

public PersonContact getByKnownUid(String uid) {
    Name relativeDn = LdapNameBuilder.newInstance()
            .add("ou", "people")
            .add("uid", uid)
            .build();

    return ldapTemplate.lookup(relativeDn, mapper);
}
~~~

Ví dụ giả định DN của người dùng **thực sự** có RDN `uid=<giá trị>` và nằm dưới `ou=people`. Với `spring.ldap.base=dc=example,dc=org`, DN tương đối mong đợi là `uid=lan,ou=people`.

**Không thay thế search bằng lookup một cách máy móc:** trong nhiều directory, tên đăng nhập `uid` chỉ là attribute, còn RDN của user có thể là `cn` hoặc định dạng khác. Lúc đó phải **search để tìm DN thật**, hoặc lấy DN từ nguồn có thẩm quyền, rồi mới lookup. `LdapNameBuilder` xử lý escaping cho thành phần DN; không ghép trực tiếp `"uid=" + uid + ",ou=people"` từ input.

Nếu DN không tồn tại, lookup có thể phát sinh ngoại lệ LDAP tương ứng (được Spring chuyển thành nhóm `DataAccessException` phù hợp); service cần có chính sách chuyển lỗi thành HTTP `404` hoặc thông báo nghiệp vụ, không trả stack trace thô cho client.

## 7. Giá trị đơn, nhiều giá trị, thuộc tính thiếu và kiểu đặc biệt

Một mapper có chất lượng không chỉ đọc thuộc tính “trong điều kiện đẹp”. Directory thực tế thay đổi theo schema, ACL và tình trạng dữ liệu.

### 7.1. Thuộc tính đơn và thuộc tính nhiều giá trị

`getStringAttribute("cn")` phù hợp khi chỉ muốn một giá trị. Ngược lại, đối với một attribute nhiều giá trị như `telephoneNumber` hoặc một số thuộc tính chứa DN thành viên nhóm, dùng `getStringAttributes(...)` và lưu dạng `List<String>` hoặc tập hợp thích hợp. Nếu thứ tự giá trị không được schema/ứng dụng bảo đảm, **đừng dùng thứ tự trả về làm thứ tự ưu tiên**.

Ví dụ:

~~~java
String displayName = entry.getStringAttribute("cn");
String[] phones = entry.getStringAttributes("telephoneNumber");

List<String> allPhones = phones == null
        ? List.of()
        : List.copyOf(Arrays.asList(phones));
~~~

Đoạn mã giả định `entry` là `DirContextOperations` và đã import `java.util.Arrays`, `java.util.List`.

### 7.2. Phân biệt thiếu thuộc tính với chuỗi rỗng

Thuộc tính có thể không được trả về do **không tồn tại**, **ACL không cho đọc** hoặc **truy vấn giới hạn attribute**. Đừng tự suy rằng `mail == null` có nghĩa người dùng chưa có email. Trong `PersonContact`, trường `email` nullable mang nghĩa “không nhận được giá trị”.

Chọn chính sách theo nghiệp vụ:

- **Bắt buộc:** thiếu `uid` thì báo lỗi mapping vì không thể định danh dữ liệu.
- **Tùy chọn:** thiếu `mail` thì giữ `null` hoặc dùng `Optional` ở lớp service.
- **Nhiều giá trị:** thiếu `telephoneNumber` thì trả danh sách rỗng.
- **Dữ liệu nhạy cảm:** không tự yêu cầu thêm toàn bộ attribute để “sửa lỗi thiếu dữ liệu” nếu ứng dụng không cần hoặc không có quyền.

Nếu một search trả vài trăm entry và chỉ một entry thiếu trường bắt buộc, việc mapper ném exception có thể làm **toàn bộ lời gọi search thất bại**. Hãy quyết định rõ ứng dụng cần fail-fast, bỏ qua entry lỗi có log kiểm soát, hay trả một trạng thái dữ liệu không hợp lệ; tránh silently bỏ dữ liệu mà nghiệp vụ cho là quan trọng.

### 7.3. Đừng giả định mọi attribute là `String`

Hầu hết ví dụ hồ sơ dùng thuộc tính văn bản, nhưng LDAP còn có attribute nhị phân, timestamp, DN và giá trị với quy tắc cú pháp riêng. Với ảnh hoặc certificate, không xử lý như chuỗi UTF-8 thông thường. Cân nhắc `getObjectAttribute(...)`/JNDI `Attributes` và cấu hình môi trường JNDI phù hợp để lấy `byte[]`; chuyển đổi sang kiểu Java chuyên biệt ở một lớp rõ ràng.

Tương tự, các chuỗi DN của thành viên nhóm nên được parse bằng `LdapName`/API DN khi cần so sánh cấu trúc, thay vì so sánh chuỗi theo cách phân biệt hoa/thường tùy tiện. Việc so khớp DN và attribute phụ thuộc quy tắc schema của directory.

## 8. Phân biệt `ContextMapper`, `AttributesMapper` và repository ODM

Spring LDAP và Spring Data LDAP có nhiều cơ chế ánh xạ kết quả. Chọn theo dữ liệu cần lấy và mức độ trừu tượng mong muốn.

| Công cụ | Thứ mapper nhận | Khi phù hợp |
| --- | --- | --- |
| `AttributesMapper<T>` | `javax.naming.directory.Attributes` | Chỉ cần attribute của entry, ví dụ tên hoặc email, không cần DN/context. |
| `ContextMapper<T>` | Một context, thường thao tác qua `DirContextOperations` | Cần DN, metadata context và attribute, logic ngắn hoặc dùng lambda. |
| `AbstractContextMapper<T>` | `DirContextOperations` đã được kiểu hóa trong `doMapFromContext` | Cần mapper đọc DN và nhiều attribute, tái sử dụng qua nhiều search/lookup. |
| Spring Data LDAP `@Entry` + `LdapRepository` | Framework tự ánh xạ entry sang entity ODM | CRUD và query theo repository, muốn làm việc với entity được quản lý bằng annotation. |

### So sánh nhanh bằng mã

Khi chỉ cần `cn`:

~~~java
import org.springframework.ldap.core.AttributesMapper;

AttributesMapper<String> cnOnly =
        attrs -> (String) attrs.get("cn").get();
~~~

Khi cần cả DN và `cn`:

~~~java
import org.springframework.ldap.core.ContextMapper;
import org.springframework.ldap.core.DirContextOperations;

ContextMapper<String> dnAndCn = source -> {
    DirContextOperations entry = (DirContextOperations) source;
    return entry.getDn() + " | " + entry.getStringAttribute("cn");
};
~~~

Với ánh xạ entity:

~~~java
import javax.naming.Name;
import org.springframework.ldap.odm.annotations.Attribute;
import org.springframework.ldap.odm.annotations.Entry;
import org.springframework.ldap.odm.annotations.Id;

@Entry(base = "ou=people", objectClasses = {"inetOrgPerson"})
public class PersonEntry {
    @Id
    private Name dn;

    @Attribute(name = "uid")
    private String uid;

    @Attribute(name = "cn")
    private String commonName;
}
~~~

Entity mẫu minh họa annotation, chưa gồm phương thức truy cập field hoặc logic CRUD. Trong Spring Data LDAP, `@Id` phải là annotation của LDAP ODM (`org.springframework.ldap.odm.annotations.Id`), không phải annotation JPA. Nếu dùng repository để quản lý entry thật, phải bảo đảm `@Entry`, tập `objectClass` và các field khớp schema của server.

**Lựa chọn gợi ý:** bắt đầu bằng repository nếu bài toán là quản lý entity LDAP rõ ràng. Chọn `LdapTemplate` với `AbstractContextMapper` khi cần một phép chiếu DTO chủ động, DN và dữ liệu trả về không trùng cấu trúc entity, hoặc cần truy vấn/logic ánh xạ đặc thù.

## 9. Kiểm thử mapper mà không cần kết nối LDAP thật

Điểm thuận lợi của việc đưa logic mapping vào class là có thể kiểm thử thuần Java với `DirContextAdapter`. Mapper chỉ cần một context giả lập có DN và attribute, không cần mở socket tới directory.

Ví dụ JUnit 5:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import java.util.List;
import javax.naming.ldap.LdapName;
import org.junit.jupiter.api.Test;
import org.springframework.ldap.core.DirContextAdapter;

class PersonContextMapperTest {

    @Test
    void mapsDnAndMultiValueAttribute() throws Exception {
        DirContextAdapter entry = new DirContextAdapter(
                new LdapName("uid=lan,ou=people"));
        entry.setAttributeValue("uid", "lan");
        entry.setAttributeValue("cn", "Lan Nguyen");
        entry.setAttributeValue("mail", "lan@example.org");
        entry.setAttributeValues("telephoneNumber",
                new String[] {"+84-28-1234-5678", "+84-90-123-4567"});

        PersonContact actual = new PersonContextMapper()
                .mapFromContext(entry);

        assertEquals("uid=lan,ou=people", actual.relativeDn());
        assertEquals("lan", actual.uid());
        assertEquals("Lan Nguyen", actual.displayName());
        assertEquals("lan@example.org", actual.email());
        assertEquals(List.of(
                "+84-28-1234-5678",
                "+84-90-123-4567"), actual.phoneNumbers());
    }
}
~~~

Với `AbstractContextMapper`, `mapFromContext(...)` của lớp cơ sở sẽ gọi `doMapFromContext(...)`. Test đảm bảo mapping nhận đúng DN và không làm mất thuộc tính nhiều giá trị. Trong dự án thật cần dependency JUnit 5 và tổ chức file/package/import phù hợp.

Nên bổ sung test cho **thiếu email**, **thiếu telephoneNumber**, **thiếu uid** và **trường có ký tự Unicode**. Đây là kiểm thử logic Java; nó chưa chứng minh truy vấn thật hoạt động đúng. Kiểm thử tích hợp với LDAP thử nghiệm vẫn cần để xác nhận base DN, filter, schema, ACL, TLS và kiểu dữ liệu thực sự server trả về.

### Kiểm thử truy vấn với directory

Giả sử tài khoản dịch vụ có quyền đọc nhánh `ou=people`, có thể đối chiếu kết quả Spring LDAP với công cụ `ldapsearch`:

~~~bash
ldapsearch -LLL -x \
  -H "ldaps://ldap.example.org:636" \
  -D "cn=app-reader,ou=services,dc=example,dc=org" -W \
  -b "ou=people,dc=example,dc=org" -s sub \
  "(&(objectClass=inetOrgPerson)(uid=lan))" \
  dn uid cn mail telephoneNumber
~~~

`-W` yêu cầu nhập mật khẩu tương tác; tránh ghi secret vào lịch sử lệnh. Nếu kết quả `ldapsearch` có `telephoneNumber` mà DTO thiếu, kiểm tra tên attribute và projection trong query, quyền đọc và cách mapper xử lý nhiều giá trị. Nếu LDAP trả không có entry, mapper không có gì để ánh xạ: phải kiểm tra URL, base, filter hoặc ACL trước.

## 10. Hiệu năng và an toàn khi ánh xạ kết quả

**Chỉ yêu cầu attribute cần thiết.** Một entry directory có thể mang nhiều giá trị lớn hoặc nhạy cảm. Dùng `attributes(...)` và xác định rõ DTO trả ra API để hạn chế dữ liệu. Không log cả context/entry nếu có thông tin cá nhân, credential, group nội bộ hoặc attribute bí mật.

**Mapper nên không có side effect.** Đừng gọi network, ghi LDAP, gọi database cho từng entry hoặc thay đổi context trong `doMapFromContext`. Với truy vấn trả 1.000 entry, mapper chạy 1.000 lần; thao tác I/O bên trong rất dễ thành vấn đề N+1 và khó kiểm soát lỗi. Nếu cần enrich dữ liệu, gom dữ liệu và xử lý ở service với chính sách cache/giới hạn rõ ràng.

**Không dùng mapping thay authorization.** `LdapTemplate`/repository có thể đọc bằng tài khoản dịch vụ; kết quả mapping không chứng minh người gọi HTTP có quyền xem DTO. Bảo vệ controller/service bằng Spring Security hoặc cơ chế tương ứng, đồng thời áp dụng ACL tối thiểu ở server LDAP.

**An toàn filter và DN.** Escape giá trị trong filter bằng `LdapQueryBuilder`, escape RDN bằng `LdapNameBuilder`. Đây là hai định dạng khác nhau; escape filter không tự xử lý DN và ngược lại.

**Hiểu giới hạn tìm kiếm.** Search base, scope, filter, size/time limits và phân trang (nếu cần) ảnh hưởng lớn tới kết quả. Đừng kéo cả directory vào bộ nhớ chỉ để tìm một người dùng; dùng filter càng cụ thể càng tốt, có kiểm soát tải cho các API có đầu vào người dùng.

## 11. Chẩn đoán lỗi ánh xạ

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `ClassCastException` khi ép `Object` sang `DirContextOperations` | Mapper được gọi với context không phù hợp hoặc dùng nhầm API. | Dùng mapper trong overload `LdapTemplate` đúng; cân nhắc `AbstractContextMapper`. |
| `NullPointerException` khi đọc `cn`/`mail` | Attribute không được trả về, khác tên, bị ACL ẩn hoặc mapper giả định luôn có. | Đối chiếu LDIF, projection và schema; xử lý null có chủ ý. |
| Chỉ nhận một số điện thoại | Dùng `getStringAttribute(...)` cho attribute nhiều giá trị. | Dùng `getStringAttributes(...)` và danh sách. |
| DN có dạng ngắn hơn mong đợi | DN trên adapter là tương đối với base ngữ cảnh. | Kiểm tra `spring.ldap.base` và giữ DN dưới dạng `Name` khi thao tác tiếp. |
| `search` trả danh sách rỗng | Base/filter/scope sai hoặc LDAP không trả entry do ACL. | Thử `ldapsearch` với cùng điều kiện, xem schema và quyền đọc. |
| Mapper báo thiếu `uid` | Entry thật thiếu `uid`, query không yêu cầu attribute hoặc user không được phép đọc. | Kiểm tra projection `attributes(...)`, mapping và schema. |
| Giá trị thuộc tính nhị phân không đọc được | Dùng getter chuỗi với kiểu dữ liệu không phải chuỗi. | Đọc kiểu object/bytes và cấu hình binary attributes cho JNDI nếu cần. |
| LDAP result code `49`, `50` hoặc TLS error | Lỗi bind/ACL/TLS xảy ra trước hoặc ngoài logic mapper. | Kiểm tra tài khoản, chứng chỉ và quyền server; mapper không sửa được lỗi kết nối. |

Lỗi mapping có thể được Spring truyền ra ngoài dưới dạng runtime exception; lỗi LDAP có thể được dịch thành `DataAccessException` phù hợp. Khi đưa ra API, tầng service/controller cần chuẩn hóa phản hồi và không phơi bày DN nội bộ, mật khẩu hoặc stack trace.

## 12. Bài tập thực hành

Directory có cấu trúc:

~~~text
dc=company,dc=internal
└── ou=employees
    ├── uid=an
    └── uid=binh
~~~

Entry `uid=an` có `uid=an`, `cn=An Tran`, `mail=an@company.internal` và hai giá trị `telephoneNumber`. Entry `uid=binh` có `uid=binh`, `cn=Binh Le` và không có `mail`/`telephoneNumber`. Ứng dụng cấu hình `spring.ldap.base=dc=company,dc=internal`.

**Yêu cầu:**

1. Viết `ContextMapper<PersonContact>` dùng lambda nhận một entry và trả `uid`, `cn`, `mail` cùng danh sách số điện thoại.
2. Tách logic sang class kế thừa `AbstractContextMapper<PersonContact>`; giải thích tại sao không còn cần ép kiểu `Object` sang `DirContextOperations` trong `doMapFromContext`.
3. Tạo `LdapQueryBuilder` để tìm `uid=an` dưới base `ou=employees`, chỉ lấy những attribute DTO sử dụng.
4. Nếu đổi `spring.ldap.base` thành `ou=employees,dc=company,dc=internal`, điều gì cần thay đổi trong base query để tránh lặp nhánh?
5. Với entry `uid=binh`, hãy chọn chính sách cho `mail` và `telephoneNumber`; phân biệt trường null và list rỗng.
6. Nêu trường hợp nên chọn `AttributesMapper`, `AbstractContextMapper` hoặc `LdapRepository`.
7. Cho biết mapper có được tự cấp quyền người dùng hoặc ghi cập nhật trở lại server chỉ vì đọc được context không.

**Gợi ý đáp án:**

- `ContextMapper` trực tiếp nhận `Object` và cast sang `DirContextOperations`; `AbstractContextMapper` dùng `doMapFromContext(DirContextOperations)`.
- Với base directory `dc=company,dc=internal`, search base tương đối là `ou=employees`; nếu đã cấu hình `spring.ldap.base=ou=employees,dc=company,dc=internal`, search base có thể là gốc tương đối rỗng, không lặp `ou=employees`.
- Dùng `getStringAttribute("mail")` và cho phép `null` với email không có; dùng `getStringAttributes("telephoneNumber")` và đưa về `List.of()` khi vắng.
- `AttributesMapper` phù hợp phép chiếu chỉ cần attribute; `AbstractContextMapper` cho DTO cần DN và logic tùy biến; `LdapRepository` cho entity/CRUD theo ODM.
- Mapper không thực hiện authentication, authorization hoặc tự lưu context. Quyền truy cập được kiểm tra tại ứng dụng và bởi ACL của tài khoản bind trên directory.

## 13. Ghi nhớ

`ContextMapper<T>` ánh xạ **context của một entry LDAP** sang một đối tượng Java. `AbstractContextMapper<T>` cung cấp phương thức `doMapFromContext(DirContextOperations)` để thực hiện cùng nhiệm vụ thuận tiện hơn, rõ kiểu hơn và dễ tái sử dụng.

Khi chỉ cần thuộc tính, cân nhắc `AttributesMapper`; khi cần **DN và logic mapping chi tiết**, dùng `ContextMapper`/`AbstractContextMapper`; khi quản lý entry theo mô hình entity, dùng `@Entry` cùng `LdapRepository`. Luôn xác định chính xác base DN, projection, schema, giá trị nhiều phần tử và ACL, đồng thời kiểm thử cả mapper độc lập lẫn truy vấn với directory thật hoặc môi trường thử nghiệm.

### Tài liệu tham khảo

- [Spring LDAP Reference — Basic Usage](https://docs.spring.io/spring-ldap/reference/basic.html)
- [Spring LDAP Reference — DirContextAdapter](https://docs.spring.io/spring-ldap/reference/dircontextadapter.html)
- [Spring LDAP Reference — LDAP Query Builder](https://docs.spring.io/spring-ldap/reference/query-builder-advanced.html)
- [Spring Data LDAP Reference](https://docs.spring.io/spring-data/ldap/reference/)
- [Java JNDI — DirContext](https://docs.oracle.com/en/java/javase/17/docs/api/java.naming/javax/naming/directory/DirContext.html)
