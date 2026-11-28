# Ánh xạ thuộc tính nhiều giá trị và kiểu nhị phân

Trong LDAP, một attribute có thể chứa **một hoặc nhiều giá trị**. Giá trị có thể là chuỗi, DN, số, thời gian hoặc dữ liệu nhị phân. Khi dùng Spring Data LDAP, entity Java cần biểu diễn đúng cả **cardinality** (số lượng giá trị) lẫn **kiểu dữ liệu** của attribute. Nếu mô hình Java chỉ có String trong khi directory lưu nhiều giá trị, ứng dụng có thể làm mất dữ liệu khi cập nhật. Nếu một attribute nhị phân bị đọc như chuỗi, byte có thể bị chuyển đổi sai và làm hỏng ảnh hoặc chứng thư.

Spring Data LDAP repository sử dụng entity được ánh xạ bằng **Spring LDAP Object-Directory Mapping (ODM)**. ODM cung cấp các annotation như @Entry, @Id, @Attribute và converter để chuyển giữa entry LDAP với object Java. Bài học này tập trung vào cách biểu diễn thuộc tính đa trị bằng collection, ánh xạ DN-valued attribute, đọc/ghi dữ liệu nhị phân bằng byte array, cấu hình JNDI binary attributes và xử lý trường hợp Active Directory trả thuộc tính lớn theo từng range.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích vì sao một LDAP attribute có thể có nhiều giá trị và khi nào schema giới hạn một giá trị.
- Chọn String, Set<String>, Name, Set<Name> hoặc byte[] phù hợp với attribute.
- Ánh xạ thuộc tính nhiều giá trị bằng Spring LDAP ODM.
- Ánh xạ giá trị DN như member/uniqueMember thành Name.
- Dùng @Attribute(type = Attribute.Type.BINARY) để đánh dấu thuộc tính nhị phân.
- Cấu hình JNDI LDAP provider trả custom binary attribute dưới dạng byte[].
- Phân biệt Base64 trong LDIF với kiểu dữ liệu Java và dữ liệu truyền trên LDAP.
- Đọc/ghi thuộc tính nhị phân có kiểm soát kích thước và quyền truy cập.
- Xử lý thuộc tính đa trị rất lớn trên Active Directory bằng incremental retrieval.
- Kiểm thử mapping, cập nhật từng giá trị, dữ liệu nhị phân và trường hợp thiếu thuộc tính.

## 2. Cardinality của LDAP attribute

LDAP attribute không giống một cột SQL luôn có một ô dữ liệu. Mỗi attribute trên một entry có thể có:

- Không có giá trị: attribute không xuất hiện trong entry.
- Một giá trị: ví dụ một cn, một jpegPhoto.
- Nhiều giá trị: ví dụ nhiều địa chỉ mail, nhiều thành viên member.

Schema attribute type quyết định liệu attribute có được phép có nhiều giá trị hay không. Nếu định nghĩa có SINGLE-VALUE, entry chỉ được có tối đa một giá trị cho attribute đó. Nếu không có ràng buộc này, attribute thường có thể đa trị, trừ khi một quy tắc schema/vendor khác giới hạn.

Ví dụ entry:

```ldif
dn: uid=alice,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: alice
cn: Alice Nguyen
sn: Nguyen
mail: alice@example.org
mail: alice@work.example.org
```

mail có hai giá trị. Một entity chỉ có String mail không thể biểu diễn đầy đủ cả hai giá trị. Dùng collection phù hợp với schema và nghiệp vụ.

### 2.1. Giá trị LDAP không mặc định có thứ tự

LDAP attribute thông thường là tập giá trị không có thứ tự. Không nên dựa vào thứ tự server trả về để xác định email chính, thành viên đầu tiên, giá trị ưu tiên hoặc giá trị mới nhất.

Nếu nghiệp vụ cần một giá trị chính, hãy biểu diễn quy tắc đó rõ ràng, chẳng hạn bằng một attribute riêng primaryMail hoặc một thuộc tính đánh dấu. Không suy ra ý nghĩa từ vị trí của phần tử trong collection.

Trong Java, Set<T> thường phù hợp với semantics tập hợp của LDAP. Nếu cần giữ thứ tự ở tầng ứng dụng, có thể chuyển sang List<T> sau khi đọc và áp dụng quy tắc sắp xếp xác định; thứ tự đó là quy ước ứng dụng, không phải thứ tự do LDAP bảo đảm.

### 2.2. Không suy luận cardinality từ dữ liệu mẫu

Nếu một entry chỉ có một giá trị mail, điều đó không chứng minh schema giới hạn mail là single-value. Hãy kiểm tra định nghĩa schema:

- SINGLE-VALUE có xuất hiện không?
- Object class nào cho phép attribute?
- Attribute có được kế thừa từ superclass không?
- Server có extension hoặc policy riêng không?

Kiểu Java phải theo schema thực tế, không theo số giá trị đang có trong một fixture.

## 3. Ánh xạ thuộc tính nhiều giá trị bằng ODM

Spring LDAP ODM ánh xạ field của entity sang attribute LDAP. Với thuộc tính chuỗi đa trị, collection như Set<String> có thể biểu diễn tập giá trị. Với thuộc tính chứa DN, ODM hỗ trợ Set<Name>.

### 3.1. Ví dụ Person có nhiều địa chỉ email

LDIF:

```ldif
dn: uid=alice,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: alice
cn: Alice Nguyen
sn: Nguyen
mail: alice@example.org
mail: alice@work.example.org
```

Entity:

```java
package com.example.directory;

import java.util.HashSet;
import java.util.Set;
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
public class Person {
    @Id
    private Name dn;

    @Attribute(name = "uid")
    private String uid;

    @Attribute(name = "cn")
    private String commonName;

    @Attribute(name = "sn")
    private String surname;

    @Attribute(name = "mail")
    private Set<String> mailAddresses = new HashSet<>();

    protected Person() {
    }

    public Name getDn() {
        return dn;
    }

    public Set<String> getMailAddresses() {
        return mailAddresses;
    }

    public void setMailAddresses(Set<String> mailAddresses) {
        this.mailAddresses = mailAddresses;
    }

    public void addMailAddress(String address) {
        this.mailAddresses.add(address);
    }

    public void removeMailAddress(String address) {
        this.mailAddresses.remove(address);
    }
}
```

Các điểm quan trọng:

- @Entry khai báo object class mà entity đại diện.
- @Id ánh xạ DN, field phải là javax.naming.Name hoặc kiểu dẫn xuất.
- @Attribute(name = "mail") ánh xạ field mailAddresses sang attribute mail.
- Set<String> biểu diễn nhiều giá trị chuỗi.
- Khởi tạo collection giúp code nghiệp vụ thêm/xóa giá trị thuận tiện. Cần kiểm tra cách mapper xử lý attribute vắng mặt trong phiên bản Spring LDAP đang dùng.

Tên field Java có thể khác tên attribute LDAP khi chỉ định name. Nếu bỏ @Attribute, ODM mặc định ánh xạ field theo tên field Java; vì vậy hãy dùng annotation khi tên khác nhau hoặc cần cấu hình syntax/type.

Repository dùng cùng entity ODM:

```java
package com.example.directory;

import java.util.List;
import org.springframework.data.ldap.repository.LdapRepository;

public interface PersonRepository extends LdapRepository<Person> {
    List<Person> findByUid(String uid);
}
```

Field uid kiểu String trong ví dụ giả định directory profile của ứng dụng bảo đảm một uid cho mỗi entry. Một số schema cho phép uid nhiều giá trị; nếu server mục tiêu cho phép điều đó, hãy ánh xạ uid thành Set<String> và kiểm thử với dữ liệu thực tế.

### 3.2. Cập nhật một giá trị trong tập

Sau khi đọc entity:

```java
Person person = ldapTemplate.findByDn(personDn, Person.class);

person.addMailAddress("alice.secondary@example.org");
person.removeMailAddress("alice@work.example.org");

ldapTemplate.update(person);
```

ODM tính toán các thay đổi attribute khi gọi update. Với tập giá trị chuỗi, hãy xác định trước quy tắc equality của schema và cách ứng dụng chuẩn hóa địa chỉ email. LDAP matching rule và String.equals() của Java không nhất thiết giống nhau về hoa thường hoặc chuẩn hóa.

Nếu không muốn cập nhật toàn bộ entity, có thể dùng LdapTemplate.modifyAttributes(...) để thêm/xóa đúng attribute. Cách này hữu ích khi chỉ cần thay đổi một phần dữ liệu và muốn tránh ghi đè các field khác.

### 3.3. Không thay toàn bộ collection khi chỉ muốn thêm một giá trị

```java
// Có thể làm mất các email khác nếu collection chưa được đọc đầy đủ.
person.setMailAddresses(Set.of("new@example.org"));
ldapTemplate.update(person);
```

Nếu mail đang có nhiều giá trị, việc thay collection bằng một tập mới có thể xóa những giá trị không được giữ lại. Trước khi dùng setMailAddresses, phải biết collection hiện tại có đầy đủ hay không và service có quyền sở hữu toàn bộ tập giá trị hay không.

## 4. Ánh xạ thuộc tính chứa DN

Nhiều thuộc tính đa trị lưu DN của entry khác thay vì chuỗi mô tả thông thường. Ví dụ member của group có thể chứa DN người dùng:

```ldif
dn: cn=backend,ou=groups,dc=example,dc=org
objectClass: top
objectClass: groupOfNames
cn: backend
member: uid=alice,ou=people,dc=example,dc=org
member: uid=bob,ou=people,dc=example,dc=org
```

Spring LDAP ODM hỗ trợ javax.naming.Name làm giá trị attribute. Đây là lựa chọn tốt hơn String nếu ứng dụng cần so sánh DN theo cấu trúc.

### 4.1. Dùng Set<Name> cho uniqueMember

Ví dụ với groupOfUniqueNames:

```ldif
dn: cn=backend,ou=groups,dc=example,dc=org
objectClass: top
objectClass: groupOfUniqueNames
cn: backend
uniqueMember: uid=alice,ou=people,dc=example,dc=org
uniqueMember: uid=bob,ou=people,dc=example,dc=org
```

Entity:

```java
package com.example.directory;

import java.util.HashSet;
import java.util.Set;
import javax.naming.Name;

import org.springframework.ldap.odm.annotations.Attribute;
import org.springframework.ldap.odm.annotations.DnAttribute;
import org.springframework.ldap.odm.annotations.Entry;
import org.springframework.ldap.odm.annotations.Id;

@Entry(
    objectClasses = {"top", "groupOfUniqueNames"},
    base = "ou=groups"
)
public class DirectoryGroup {
    @Id
    private Name dn;

    @Attribute(name = "cn")
    @DnAttribute("cn")
    private String name;

    @Attribute(name = "uniqueMember")
    private Set<Name> members = new HashSet<>();

    protected DirectoryGroup() {
    }

    public Name getDn() {
        return dn;
    }

    public Set<Name> getMembers() {
        return members;
    }

    public void setMembers(Set<Name> members) {
        this.members = members;
    }

    public void addMember(Name member) {
        members.add(member);
    }

    public void removeMember(Name member) {
        members.remove(member);
    }
}
```

Spring LDAP ODM dùng DN equality khi tính toán thay đổi tập DN trong ví dụ group membership. Điều này giúp không coi hai cách viết văn bản khác nhau của cùng một DN là hai thành viên khác nhau chỉ vì khác format.

### 4.2. Tạo LdapName an toàn

Không ghép DN từ chuỗi do người dùng nhập bằng phép nối thủ công. Dùng LdapNameBuilder hoặc LdapName:

```java
import javax.naming.ldap.LdapName;
import org.springframework.ldap.support.LdapNameBuilder;

LdapName memberDn = LdapNameBuilder.newInstance()
        .add("dc", "example")
        .add("dc", "org")
        .add("ou", "people")
        .add("uid", "alice")
        .build();

group.addMember(memberDn);
```

Name biểu diễn cấu trúc DN, không phải một chuỗi tùy ý. Khi hiển thị/log, có thể gọi toString(), nhưng không nên dùng chuỗi format để thay thế so sánh DN theo semantics LDAP.

### 4.3. DnAttribute khác với attribute-valued DN

Ba trường hợp khác nhau:

- @Id Name dn: DN của chính entry hiện tại.
- @Attribute(name = "uniqueMember") Set<Name> members: DN của các entry khác được lưu trong attribute.
- @DnAttribute("cn") String name: lấy một thành phần RDN từ DN của entry hiện tại.

@DnAttribute chỉ hỗ trợ field String. Nó không phải annotation để ánh xạ Set<Name> hoặc DN đầy đủ. Nếu field chỉ lấy từ DN mà không phải LDAP attribute riêng, kết hợp @Transient theo hướng dẫn ODM.

## 5. Ánh xạ thuộc tính nhị phân

Một số attribute chứa octet hoặc dữ liệu ASN.1/binary, chẳng hạn:

- jpegPhoto: ảnh JPEG.
- userCertificate: chứng thư X.509.
- cACertificate: chứng thư CA.
- userSMIMECertificate: chứng thư S/MIME.
- photo, personalSignature hoặc custom attribute có syntax nhị phân.

JNDI LDAP provider có thể trả attribute dạng String hoặc byte[]. Spring LDAP ODM cho phép chỉ rõ cách provider cần trả field bằng @Attribute(type = Attribute.Type.BINARY).

### 5.1. Entity có ảnh JPEG

```java
package com.example.directory;

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
public class PersonPhoto {
    @Id
    private Name dn;

    @Attribute(
        name = "jpegPhoto",
        type = Attribute.Type.BINARY
    )
    private byte[] photo;

    protected PersonPhoto() {
    }

    public byte[] getPhoto() {
        return photo;
    }

    public void setPhoto(byte[] photo) {
        this.photo = photo;
    }
}
```

Attribute.Type.BINARY có nghĩa JNDI provider trả giá trị của field dưới dạng byte[]. Nó không tự kiểm tra nội dung thật sự là JPEG, cũng không thay thế validation định dạng ảnh ở tầng ứng dụng.

Nếu schema attribute có syntax OID cụ thể, có thể khai báo syntax trong @Attribute. Syntax giúp ODM chọn converter phù hợp và tăng độ chính xác khi chuyển đổi.

### 5.2. Ví dụ attribute chứng thư

```java
@Attribute(
    name = "userCertificate",
    type = Attribute.Type.BINARY
)
private byte[] userCertificate;
```

Đây là ví dụ một giá trị. Nếu directory lưu nhiều chứng thư trong cùng attribute, cần xác minh kiểu collection và converter được hỗ trợ trong phiên bản ODM đang dùng. Với nhiều giá trị binary hoặc yêu cầu kiểm soát từng byte array, có thể đọc javax.naming.directory.Attributes trực tiếp qua AttributesMapper và chuyển đổi tường minh thay vì giả định mọi collection binary đều được map giống collection chuỗi.

### 5.3. Phân biệt Base64 trong LDIF với byte[]

LDIF dùng Base64 để biểu diễn giá trị có byte không thể ghi an toàn dưới dạng văn bản. Ví dụ:

```ldif
jpegPhoto:: /9j/4AAQSkZJRgABAQ...
```

Hai dấu hai chấm (::) báo rằng giá trị LDIF được mã hóa Base64. Khi đọc bằng JNDI/ODM, ứng dụng nhận byte gốc dưới dạng byte[] nếu provider được cấu hình đúng. Không cần tự giải mã Base64 lần nữa nếu JNDI đã trả byte gốc.

Không chuyển byte[] sang new String(bytes) để lưu ảnh/chứng thư. Việc giải mã theo charset có thể làm thay đổi byte và làm hỏng dữ liệu. Base64 chỉ nên dùng ở ranh giới cần biểu diễn binary thành văn bản, chẳng hạn JSON hoặc LDIF.

## 6. Cấu hình JNDI cho custom binary attributes

JNDI LDAP provider có danh sách attribute nhị phân mặc định. Nếu ứng dụng sử dụng một custom attribute có syntax không phải chuỗi, có thể khai báo thuộc tính đó qua environment property:

java.naming.ldap.attributes.binary

Giá trị là danh sách tên attribute cách nhau bằng dấu cách. Ví dụ:

```java
import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ldap.core.support.LdapContextSource;

@Configuration
public class LdapConfiguration {
    @Bean
    public LdapContextSource contextSource() {
        LdapContextSource source = new LdapContextSource();
        source.setUrl("ldaps://ldap.example.org:636");
        source.setBase("dc=example,dc=org");
        source.setUserDn("cn=app-reader,ou=services,dc=example,dc=org");
        source.setPassword(System.getenv("LDAP_BIND_PASSWORD"));

        source.setBaseEnvironmentProperties(Map.of(
                "java.naming.ldap.attributes.binary",
                "jpegPhoto appBinaryData appSigningKey"
        ));

        source.afterPropertiesSet();
        return source;
    }
}
```

Ví dụ minh họa một bean LdapContextSource; trong ứng dụng thực tế hãy quản lý URL, bind DN và password bằng cấu hình bên ngoài/secret store. Không ghi credential vào source code.

Lưu ý:

- Property này dành cho JNDI LDAP provider; provider khác có thể có cách cấu hình riêng.
- Nó mở rộng danh sách attribute được provider coi là binary, không biến mọi attribute thành binary.
- Tên attribute phải khớp tên server trả về.
- @Attribute(type = BINARY) và cấu hình provider cần nhất quán: ODM mong byte[], còn JNDI phải thực sự trả byte[].
- Sau khi cấu hình, kiểm tra giá trị bằng integration test trên cùng loại JDK/provider với môi trường triển khai.

### 6.1. ;binary là attribute option, không phải Base64

LDAP có attribute option ;binary dùng cho một số trường hợp truyền dữ liệu binary, đặc biệt dữ liệu ASN.1 encoded như certificate. Đây là option trong tên thuộc tính yêu cầu trên giao thức, không phải ký hiệu Base64 trong LDIF.

| Ký hiệu | Ý nghĩa |
| --- | --- |
| jpegPhoto:: ... trong LDIF | Giá trị LDIF được biểu diễn bằng Base64. |
| userCertificate;binary | Attribute description có option binary khi truy cập theo giao thức. |
| Attribute.Type.BINARY | ODM yêu cầu JNDI provider trả byte[]. |
| java.naming.ldap.attributes.binary | JNDI provider property để chỉ định thêm attribute được trả dạng byte[]. |

Không tự thêm ;binary vào mọi attribute có dữ liệu byte. Hãy làm theo schema, quy tắc của attribute và yêu cầu của LDAP server.

## 7. Đọc nhiều giá trị binary bằng AttributesMapper

Khi một attribute binary có nhiều giá trị hoặc cần xử lý trực tiếp từng giá trị, có thể dùng LdapTemplate.lookup(...) với AttributesMapper.

Ví dụ:

```java
import java.util.ArrayList;
import java.util.List;
import javax.naming.Name;
import javax.naming.NamingEnumeration;
import javax.naming.NamingException;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;

import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;

public class CertificateReader {
    private final LdapTemplate ldapTemplate;

    public CertificateReader(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<byte[]> readCertificates(Name dn) {
        return ldapTemplate.lookup(
                dn,
                new String[]{"userCertificate"},
                (AttributesMapper<List<byte[]>>) attrs ->
                        extractBinaryValues(attrs, "userCertificate"));
    }

    private List<byte[]> extractBinaryValues(
            Attributes attrs, String attributeName)
            throws NamingException {

        Attribute attribute = attrs.get(attributeName);
        if (attribute == null) {
            return List.of();
        }

        List<byte[]> values = new ArrayList<>();
        NamingEnumeration<?> all = attribute.getAll();
        try {
            while (all.hasMore()) {
                Object value = all.next();
                if (!(value instanceof byte[] bytes)) {
                    throw new IllegalStateException(
                            "Expected binary value for " + attributeName);
                }
                values.add(bytes);
            }
        } finally {
            all.close();
        }
        return List.copyOf(values);
    }
}
```

Đoạn code giả định JNDI provider đã được cấu hình để trả userCertificate dưới dạng byte[]. NamingEnumeration được đóng trong finally ngay cả khi việc chuyển đổi thất bại.

Ví dụ này đọc toàn bộ giá trị vào bộ nhớ; không dùng cho binary payload rất lớn nếu không có giới hạn kích thước.

## 8. Hiểu converter và syntax

@Attribute có bốn thành phần thường cần quan tâm:

| Thành phần | Ý nghĩa |
| --- | --- |
| name | Tên LDAP attribute mà field đại diện. |
| type | Chọn dữ liệu JNDI trả về dạng String hay byte[]. |
| syntax | Syntax OID của attribute, có thể giúp converter chọn phép chuyển đổi chính xác hơn. |
| readonly | Cho phép đọc nhưng không persist field trở lại LDAP. |

Spring LDAP ODM dùng converter manager để chuyển giá trị giữa LDAP và Java. Nếu không có converter phù hợp, quá trình mapping có thể ném ConverterException.

### 8.1. Khi nào cần converter tùy chỉnh?

Converter hữu ích khi:

- Attribute LDAP là Generalized Time nhưng Java model muốn dùng Instant.
- Giá trị LDAP là chuỗi mã hóa theo format nghiệp vụ.
- Attribute binary chứa cấu trúc ASN.1 cần chuyển thành X509Certificate.
- Custom syntax cần một Java value object.
- Ứng dụng muốn chuẩn hóa dữ liệu trước khi lưu.

Với Spring Boot, có thể đăng ký Converter như bean để ObjectDirectoryMapper sử dụng qua ConversionService theo cấu hình hiện hành. Nếu không dùng Boot, cần cấu hình ObjectDirectoryMapper/ConversionService tương ứng. Kiểm tra API converter của đúng phiên bản Spring LDAP trước khi triển khai.

### 8.2. Không nhầm syntax với Attribute.Type

syntax mô tả kiểu dữ liệu theo schema LDAP. Attribute.Type quyết định JNDI provider trả Java value dưới dạng String hay byte[].

Ví dụ:

- Attribute có syntax Directory String thường được đọc dạng String.
- Attribute có syntax Octet String thường cần dữ liệu nhị phân.
- Attribute.Type.BINARY không xác nhận schema là Octet String; nó chỉ điều khiển cách JNDI provider trả giá trị cho field.

Hai thông tin phải phù hợp với schema và provider thực tế.

## 9. Giới hạn kích thước và thuộc tính đa trị rất lớn

Thuộc tính đa trị có thể chứa rất nhiều giá trị. Một ví dụ điển hình là membership của group trong Active Directory.

Active Directory thường không trả toàn bộ giá trị của một thuộc tính đa trị có số lượng rất lớn trong một response. Với thuộc tính vượt khoảng **1.500 giá trị**, server có thể trả theo cơ chế incremental retrieval/ranged retrieval. Client cần yêu cầu các range tiếp theo để lấy đủ dữ liệu.

Điều này khác với LDAP paged results:

| Cơ chế | Giải quyết vấn đề |
| --- | --- |
| Paged results control | Chia tập **entry kết quả search** thành nhiều trang. |
| AD ranged retrieval | Chia các **giá trị của một attribute trên một entry** thành nhiều range. |

Một search trả về một group vẫn có thể chỉ chứa một phần giá trị member, dù search không có paging.

### 9.1. Dùng DefaultIncrementalAttributesMapper

Spring LDAP cung cấp DefaultIncrementalAttributesMapper để đọc đầy đủ các giá trị của thuộc tính theo cơ chế ranged retrieval của Active Directory.

Ví dụ lookup một group theo DN:

```java
import javax.naming.Name;
import javax.naming.directory.Attributes;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.core.support.DefaultIncrementalAttributesMapper;

public Attributes readAllMembers(
        LdapTemplate ldapTemplate, Name groupDn) {

    return DefaultIncrementalAttributesMapper.lookupAttributes(
            ldapTemplate,
            groupDn,
            new String[]{"member"});
}
```

lookupAttributes thực hiện các lookup tiếp theo khi server trả range marker. Có thể dùng lookupAttributeValues(...) nếu chỉ cần list giá trị của một attribute.

Lưu ý quan trọng:

- Mapper này được thiết kế cho **lookup theo DN**, không hỗ trợ search trực tiếp.
- Instance mapper có trạng thái; không chia sẻ một instance giữa nhiều thread.
- Nếu cần điều khiển page size hoặc xử lý từng vòng, tạo instance riêng cho mỗi thao tác và gọi tiếp với getAttributesForLookup() khi hasMore() còn đúng.
- Không mặc định mọi LDAP server đều dùng cơ chế range giống Active Directory.
- Cần test với phiên bản AD/domain controller thực tế và quyền đọc attribute.

### 9.2. Không tải toàn bộ membership vào entity một cách vô điều kiện

Một group có hàng chục nghìn thành viên có thể làm tăng bộ nhớ heap, thời gian bind/mapping, payload qua mạng và thời gian cập nhật entity.

Nếu chỉ cần kiểm tra một thành viên, dùng filter/operation phù hợp thay vì đọc toàn bộ member. Nếu cần toàn bộ danh sách, dùng incremental retrieval và xử lý theo batch. Cân nhắc thiết kế phân trang ở tầng ứng dụng hoặc mô hình membership riêng cho các trường hợp rất lớn.

## 10. Cập nhật collection và thao tác từng attribute

Khi cập nhật nhiều giá trị, cần chọn đúng operation:

| LDAP modification | Tác dụng | Tình huống |
| --- | --- | --- |
| ADD_ATTRIBUTE | Thêm một hoặc nhiều giá trị. | Thêm email hoặc thành viên mới. |
| REMOVE_ATTRIBUTE | Xóa attribute hoặc giá trị được chỉ định theo request. | Xóa một thành viên hoặc xóa toàn bộ attribute. |
| REPLACE_ATTRIBUTE | Thay tập giá trị hiện tại. | Thay toàn bộ danh sách khi ứng dụng sở hữu tập dữ liệu. |

Ví dụ thêm một thành viên:

```java
import javax.naming.Name;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;
import org.springframework.ldap.core.LdapTemplate;

public void addGroupMember(
        LdapTemplate ldapTemplate,
        Name groupDn,
        Name memberDn) {

    BasicAttribute member = new BasicAttribute("uniqueMember");
    member.add(memberDn);

    ldapTemplate.modifyAttributes(
            groupDn,
            new ModificationItem[]{
                new ModificationItem(
                        DirContext.ADD_ATTRIBUTE, member)
            });
}
```

Ví dụ xóa đúng một thành viên:

```java
public void removeGroupMember(
        LdapTemplate ldapTemplate,
        Name groupDn,
        Name memberDn) {

    BasicAttribute member = new BasicAttribute("uniqueMember");
    member.add(memberDn);

    ldapTemplate.modifyAttributes(
            groupDn,
            new ModificationItem[]{
                new ModificationItem(
                        DirContext.REMOVE_ATTRIBUTE, member)
            });
}
```

Các ví dụ giả định schema và ACL cho phép sửa uniqueMember. Với groupOfUniqueNames, schema chuẩn yêu cầu có ít nhất một uniqueMember; xóa thành viên cuối cùng có thể bị server từ chối do vi phạm schema. Hãy xử lý trường hợp nhóm rỗng theo mô hình dữ liệu được directory cho phép.

### 10.1. Tránh ghi đè các giá trị không được đọc

Nếu server trả một phần giá trị (ví dụ AD range retrieval) nhưng entity chỉ chứa tập giá trị đó, gọi update(entity) có thể làm mất các giá trị còn lại tùy cách mapping/update. Đối với attribute rất lớn:

- Không dùng ODM entity partial như thể nó chứa toàn bộ tập.
- Dùng incremental retrieval để đọc đầy đủ nếu cần reconcile.
- Dùng ADD_ATTRIBUTE/REMOVE_ATTRIBUTE để thay đổi đúng một giá trị.
- Không dùng REPLACE_ATTRIBUTE trừ khi đã có toàn bộ tập mong muốn.

## 11. Tối ưu truy vấn và xử lý binary

Binary attributes có thể lớn hơn nhiều so với chuỗi thông thường. Một truy vấn trả về nhiều ảnh hoặc chứng thư cùng lúc có thể tăng đáng kể băng thông và heap.

Các thực hành tốt:

- Chỉ yêu cầu binary attribute khi thật sự cần.
- Khi tìm danh sách người dùng, chỉ trả uid, cn, mail; không tải jpegPhoto trong mọi search.
- Dùng lookup theo DN cho thao tác lấy ảnh/chứng thư của một entry cụ thể.
- Giới hạn kích thước file ở tầng ứng dụng trước khi ghi.
- Xác thực nội dung (magic bytes, parser ảnh/chứng thư) thay vì tin vào phần mở rộng hoặc MIME type do client gửi.
- Kiểm tra quyền đọc/ghi; binary attribute có thể chứa dữ liệu nhạy cảm.
- Không log byte array, certificate private material hoặc nội dung ảnh.
- Nếu payload lớn, cân nhắc lưu file/object storage và chỉ lưu metadata/reference trong LDAP.

byte[] giữ toàn bộ payload trong heap. Một ảnh 8 MB được tải vào hàng trăm request đồng thời có thể gây áp lực lớn lên bộ nhớ dù từng request riêng lẻ có vẻ nhỏ. Đặt giới hạn kích thước, số request đọc binary đồng thời, timeout và giới hạn response ở tầng API.

## 12. Kiểm thử mapping nhiều giá trị và binary

Unit test cho service không đủ chứng minh JNDI provider trả đúng kiểu dữ liệu. Cần integration test với directory test cùng cấu hình binary attribute.

### 12.1. Fixture LDIF

Ví dụ người dùng có nhiều email và ảnh:

```ldif
dn: uid=alice,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: alice
cn: Alice Nguyen
sn: Nguyen
mail: alice@example.org
mail: alice@work.example.org
jpegPhoto:: AQIDBA==
```

AQIDBA== chỉ là byte mẫu để kiểm tra luồng binary, không phải ảnh JPEG hợp lệ. Test xử lý ảnh thật cần fixture JPEG hợp lệ và kiểm tra magic bytes/decoder.

### 12.2. Integration test cho nhiều giá trị

```java
package com.example.directory;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.Set;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest
@ActiveProfiles("integration-test")
class MultiValuedAttributeIT {
    @Autowired PersonRepository repository;

    @Test
    void mapsAllMailValues() {
        Person person = repository.findByUid("alice")
                .stream()
                .findFirst()
                .orElseThrow();

        assertEquals(
                Set.of("alice@example.org", "alice@work.example.org"),
                person.getMailAddresses());
    }
}
```

Test giả định repository có method findByUid và directory test đã seed fixture. Không chạy fixture ghi dữ liệu trên LDAP production.

### 12.3. Integration test cho binary

```java
package com.example.directory;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import javax.naming.ldap.LdapName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.ldap.core.LdapTemplate;

@SpringBootTest
@ActiveProfiles("integration-test")
class BinaryAttributeIT {
    @Autowired LdapTemplate ldapTemplate;

    @Test
    void readsBinaryAttributeWithoutCharsetConversion() throws Exception {
        PersonPhoto person = ldapTemplate.findByDn(
                new LdapName("uid=alice,ou=people"),
                PersonPhoto.class);

        assertNotNull(person.getPhoto());
        assertArrayEquals(
                new byte[]{1, 2, 3, 4},
                person.getPhoto());
    }
}
```

Test giả định profile integration-test kết nối tới directory test, base DN là dc=example,dc=org, JNDI provider nhận jpegPhoto dưới dạng binary và fixture dùng AQIDBA==. Nếu môi trường dùng base DN đầy đủ trong LdapName, điều chỉnh DN cho đúng cấu hình.

### 12.4. Các trường hợp cần có trong test suite

| Trường hợp | Kết quả mong đợi |
| --- | --- |
| Attribute đa trị có hai giá trị | ODM map đủ cả hai giá trị. |
| Attribute vắng mặt | Java field phản ánh trạng thái không có giá trị theo mapping/configuration. |
| Thêm một giá trị | Các giá trị cũ vẫn còn. |
| Xóa một giá trị | Chỉ giá trị được chọn bị xóa. |
| Replace toàn bộ tập | Chỉ dùng khi tập đầu vào là đầy đủ và có chủ đích. |
| Attribute DN-valued | Mapping thành Set<Name> và equality theo DN. |
| Binary attribute | JNDI trả byte[], byte không bị chuyển qua charset. |
| Custom binary attribute | JNDI property được cấu hình và test xác nhận byte array. |
| Binary rỗng/vắng mặt | Xử lý null/empty theo contract. |
| Binary vượt giới hạn | Ứng dụng từ chối hoặc xử lý theo policy. |
| AD group trên 1.500 members | Incremental retrieval lấy đủ values khi lookup. |
| Attribute bị giới hạn bởi ACL | Lỗi quyền được phân biệt với lỗi mapping. |

## 13. Lỗi thường gặp và cách khắc phục

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Chỉ thấy một giá trị trong Java | Field scalar trong khi LDAP attribute đa trị. | Dùng collection phù hợp và xác minh schema/cardinality. |
| Mất các giá trị cũ sau update | Replace collection bằng tập chưa đầy đủ. | Đọc đủ dữ liệu hoặc dùng ADD_ATTRIBUTE/REMOVE_ATTRIBUTE. |
| Giá trị group không so sánh đúng | DN được lưu thành chuỗi và so sánh text. | Dùng Name/Set<Name> khi ODM hỗ trợ. |
| ConverterException | Không có converter cho kiểu Java/syntax. | Kiểm tra syntax OID, Attribute.Type, converter và Java field. |
| Binary bị lỗi hoặc không phải byte[] | JNDI provider coi custom attribute là string. | Cấu hình java.naming.ldap.attributes.binary và type = BINARY. |
| Ảnh/chứng thư hỏng sau round trip | Chuyển byte[] qua charset hoặc Base64 sai số lần. | Giữ nguyên byte[], chỉ Base64 tại ranh giới văn bản. |
| ODM không đọc attribute | Sai tên, thiếu quyền hoặc projection không yêu cầu field. | Kiểm tra schema, ACL, attribute name và danh sách attributes truy vấn. |
| Active Directory chỉ trả một phần member | Thuộc tính dùng ranged retrieval. | Dùng DefaultIncrementalAttributesMapper cho lookup theo DN. |
| Incremental mapper trả thiếu dữ liệu khi search | Mapper chỉ hỗ trợ lookup, không hỗ trợ search. | Lookup từng DN hoặc thiết kế xử lý range phù hợp. |
| Update group rỗng bị từ chối | Schema groupOfNames/groupOfUniqueNames yêu cầu ít nhất một member. | Thiết kế trạng thái nhóm rỗng theo schema và nghiệp vụ. |
| Heap tăng khi đọc ảnh | Tải nhiều binary attribute cùng lúc hoặc không giới hạn size. | Projection, concurrency limit, payload limit hoặc lưu binary ngoài LDAP. |

## 14. Bài tập thực hành

**Bài 1.** Một LDAP entry có hai giá trị mail. Java field nên dùng String hay Set<String>?

**Đáp án:** Dùng Set<String> nếu attribute được schema cho phép nhiều giá trị và ứng dụng cần giữ toàn bộ giá trị. String chỉ phù hợp khi schema/profile bảo đảm một giá trị.

**Bài 2.** Vì sao uniqueMember phù hợp với Set<Name> hơn Set<String>?

**Đáp án:** Mỗi giá trị là DN có cấu trúc. Name cho phép xử lý DN theo cấu trúc và equality thay vì chỉ so sánh chuỗi biểu diễn.

**Bài 3.** @Attribute(type = Attribute.Type.BINARY) có biến một chuỗi Base64 thành ảnh JPEG hợp lệ không?

**Đáp án:** Không. Annotation chỉ chỉ định kiểu dữ liệu JNDI provider trả về dạng byte[]. Nó không xác thực nội dung hoặc giải mã Base64 tùy tiện.

**Bài 4.** Vì sao không nên dùng new String(photoBytes) để lưu ảnh?

**Đáp án:** Charset decoding có thể thay đổi byte. Binary phải được giữ dưới dạng byte[]; Base64 chỉ dùng khi cần biểu diễn binary thành văn bản.

**Bài 5.** Custom binary attribute không được JNDI nhận dạng mặc định. Cần cấu hình gì?

**Đáp án:** Có thể thêm tên attribute vào java.naming.ldap.attributes.binary qua base environment properties của ContextSource, đồng thời khai báo Attribute.Type.BINARY trong ODM khi phù hợp.

**Bài 6.** Một group trong Active Directory có hơn 1.500 thành viên nhưng lookup chỉ thấy một phần. Vì sao?

**Đáp án:** AD có thể dùng ranged retrieval cho multi-valued attribute lớn. Dùng DefaultIncrementalAttributesMapper để lấy các range tiếp theo khi lookup theo DN.

**Bài 7.** Có thể dùng DefaultIncrementalAttributesMapper trực tiếp cho search trả về nhiều group không?

**Đáp án:** Không. Utility này hỗ trợ lookup theo DN, không hỗ trợ search. Cần lấy DN từng group rồi lookup attribute hoặc triển khai cơ chế range phù hợp.

**Bài 8.** Khi xóa thành viên cuối cùng khỏi groupOfUniqueNames, vì sao server có thể từ chối?

**Đáp án:** Schema chuẩn yêu cầu uniqueMember hiện diện. Entry không còn member sẽ vi phạm object class; cần mô hình hóa trạng thái nhóm rỗng phù hợp schema.

## 15. Ghi nhớ

- LDAP attribute có thể có nhiều giá trị; schema SINGLE-VALUE mới giới hạn tối đa một giá trị.
- Với thuộc tính chuỗi đa trị, dùng collection như Set<String>; với thuộc tính chứa DN, ODM hỗ trợ Set<Name>.
- Giá trị LDAP không mặc định có thứ tự. Không dùng vị trí trong collection để biểu diễn ưu tiên nghiệp vụ.
- @Attribute(type = Attribute.Type.BINARY) yêu cầu JNDI provider trả byte[]; syntax giúp converter hiểu dạng dữ liệu.
- Với custom binary attribute, có thể cấu hình java.naming.ldap.attributes.binary qua ContextSource.setBaseEnvironmentProperties(...).
- Base64 trong LDIF chỉ là cách biểu diễn văn bản; không chuyển binary sang String để lưu trữ.
- Khi cập nhật tập giá trị, phân biệt ADD_ATTRIBUTE, REMOVE_ATTRIBUTE và REPLACE_ATTRIBUTE; replace có thể xóa các giá trị không được giữ lại.
- Active Directory có thể trả attribute đa trị lớn theo range; Spring LDAP DefaultIncrementalAttributesMapper hỗ trợ incremental retrieval cho lookup theo DN.
- Không tải binary hoặc membership rất lớn khi không cần; giới hạn kích thước, concurrency và quyền truy cập.
- Kiểm thử trên đúng JNDI provider/directory server của môi trường triển khai, bao gồm multi-value, binary và ranged retrieval.

## Tài liệu tham khảo

- [Spring LDAP — Object-Directory Mapping (ODM)](https://docs.spring.io/spring-ldap/reference/odm.html): @Entry, @Id, @Attribute, mapping Set<Name> và LdapTemplate.
- [Spring LDAP API — Attribute](https://docs.spring.io/spring-ldap/docs/3.3.x/api/org/springframework/ldap/odm/annotations/Attribute.html): type, syntax, readonly và binary/string mapping.
- [Spring LDAP API — DefaultIncrementalAttributesMapper](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/support/DefaultIncrementalAttributesMapper.html): incremental retrieval cho multi-valued properties của Active Directory.
- [Spring LDAP — Utilities](https://docs.spring.io/spring-ldap/reference/utilities.html): xử lý thuộc tính đa trị lớn trên Active Directory.
- [Oracle — JNDI/LDAP Supplement: LDAP-specific Properties](https://docs.oracle.com/javase/8/docs/technotes/guides/jndi/jndi-ldap-gl.html): java.naming.ldap.attributes.binary.
- [Oracle — JNDI LDAP Attributes](https://docs.oracle.com/javase/jndi/tutorial/ldap/misc/attrs.html): binary attribute, attribute options và cách JNDI trả byte array.
- [Spring LDAP — Spring LDAP Repositories](https://docs.spring.io/spring-ldap/reference/repositories.html): repository sử dụng entity ODM và giới hạn đặc thù của LDAP repository.
