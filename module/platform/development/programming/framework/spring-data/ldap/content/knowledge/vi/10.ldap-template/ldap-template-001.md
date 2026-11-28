# Sử dụng LdapTemplate cho các thao tác đọc và ghi

## Mục tiêu bài học

Trong ứng dụng Java, **Spring Data LDAP** hỗ trợ truy cập dịch vụ thư mục LDAP bằng repository và ánh xạ các entry trong cây thư mục thành đối tượng Java. Bên cạnh repository, **LdapTemplate** (thuộc Spring LDAP) cung cấp API ở mức thấp hơn để thao tác trực tiếp với distinguished name (DN), thuộc tính của entry và bộ lọc LDAP. Bài này tập trung vào việc dùng LdapTemplate để **đọc, tìm kiếm, tạo, cập nhật và xóa entry** một cách có kiểm soát.

Sau bài học, bạn có thể:

- Giải thích vai trò của DN, base DN, relative DN, objectClass, schema và quyền truy cập khi gọi LdapTemplate.
- Chọn đúng thao tác **lookup**, **search**, **bind**, **modifyAttributes**, **rename** và **unbind**.
- Ánh xạ các thuộc tính của entry sang đối tượng Java và thực hiện CRUD với ví dụ cụ thể.
- Xây dựng truy vấn, DN an toàn từ dữ liệu đầu vào; xử lý các lỗi thường gặp.
- Cấu hình kết nối có bảo mật và kiểm chứng hành vi trên một LDAP directory phục vụ phát triển/kiểm thử.

## 1. Đặt LdapTemplate vào mô hình LDAP

LDAP lưu dữ liệu theo **cây các entry**, mỗi entry có DN duy nhất trong cây và tập thuộc tính được ràng buộc bởi schema. Ví dụ một cây thư mục:

~~~text
dc=example,dc=org
├── ou=people
│   ├── uid=alice
│   └── uid=bob
└── ou=service-accounts
    └── uid=svc-app
~~~

DN đầy đủ của Alice là **uid=alice,ou=people,dc=example,dc=org**. Nếu ứng dụng cấu hình **base DN = dc=example,dc=org**, phần DN truyền cho LdapTemplate thường là **uid=alice,ou=people**, tức DN tương đối so với base. Ngược lại, thao tác tìm kiếm có thể chọn base **ou=people** để giới hạn một nhánh. Không nên vô tình ghép base DN thêm lần nữa vào DN tương đối.

Một entry người dùng theo schema phổ biến có thể chứa:

~~~ldif
dn: uid=alice,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: alice
cn: Alice Nguyen
sn: Nguyen
mail: alice@example.org
~~~

Các objectClass xác định kiểu entry và thuộc tính hợp lệ. Chẳng hạn **person** yêu cầu **cn** và **sn**, còn **inetOrgPerson** là lớp mở rộng thường dùng cho hồ sơ người. **uid** trong ví dụ vừa là thuộc tính vừa là thành phần RDN của entry. Không thể thêm tùy ý một thuộc tính nếu schema hoặc ACL của directory không cho phép.

LdapTemplate dùng **ContextSource** để tạo kết nối JNDI, thực thi thao tác và chuyển đổi nhiều ngoại lệ JNDI thành ngoại lệ thuộc Spring LDAP. Sử dụng nó khi cần điều khiển trực tiếp DN, bộ lọc tìm kiếm hoặc các thay đổi thuộc tính. Repository vẫn phù hợp khi ứng dụng đã có lớp ánh xạ entry và cần các phương thức truy cập dạng repository; hai cách có thể cùng tồn tại.

| Nhu cầu | API thường dùng | Kết quả |
| --- | --- | --- |
| Đọc chính xác một DN đã biết | **lookup(dn, mapper)** | Một entry hoặc lỗi nếu DN không tồn tại |
| Tìm nhiều entry theo thuộc tính | **search(query, mapper)** | Danh sách entry phù hợp |
| Tạo entry ở một DN mới | **bind(dn, null, attributes)** | Entry mới; lỗi nếu DN đã tồn tại |
| Sửa một số thuộc tính | **modifyAttributes(dn, items)** | Thay đổi thuộc tính trên entry |
| Đổi DN/RDN của entry | **rename(oldDn, newDn)** | Di chuyển/đổi tên theo khả năng của server |
| Xóa entry | **unbind(dn)** | Xóa entry; có thể bị từ chối nếu còn entry con |

## 2. Chuẩn bị kết nối và cây dữ liệu

Trong ứng dụng Spring Boot đã dùng Spring Data LDAP, có thể khai báo dependency Gradle:

~~~groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-ldap")
}
~~~

Ví dụ cấu hình kết nối trong môi trường có LDAPS và directory riêng:

~~~yaml
spring:
  ldap:
    urls: ldaps://ldap.example.org:636
    base: dc=example,dc=org
    username: uid=svc-app,ou=service-accounts,dc=example,dc=org
    password: ${LDAP_BIND_PASSWORD}
~~~

Ở cấu hình này, username là **DN dùng để xác thực (bind DN)**, còn **base** là gốc cho các thao tác của ứng dụng; hai giá trị có mục đích khác nhau. Tài khoản dịch vụ cần quyền đọc/ghi thích hợp trên nhánh **ou=people**. Mật khẩu lấy từ biến môi trường hoặc kho bí mật, không đưa vào mã nguồn.

Khi Spring Boot đã tự cấu hình **LdapTemplate**, có thể inject trực tiếp vào service. Trong dự án tự cấu hình Spring LDAP, cần đăng ký **ContextSource** và **LdapTemplate** tương ứng. Kết nối LDAPS chỉ thực sự an toàn nếu ứng dụng kiểm tra chứng chỉ máy chủ qua truststore/CA được tin cậy; không tắt xác minh TLS để giải quyết lỗi chứng chỉ.

Trước khi chạy ví dụ, directory phải có **dc=example,dc=org** và **ou=people**. LDIF khởi tạo tối thiểu cho một directory thử nghiệm chưa có dữ liệu gốc có thể gồm:

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

Tùy cấu hình LDAP server, suffix có thể được tạo từ trước; chỉ nhập các entry chưa tồn tại và bảo đảm tài khoản dùng cho thử nghiệm có quyền cần thiết.

## 3. Ví dụ service: ánh xạ entry và CRUD

Ví dụ dưới đây sử dụng Java 17 trở lên, Spring LDAP và một nhánh người dùng **ou=people**. Để tập trung vào LdapTemplate, dữ liệu được ánh xạ bằng **AttributesMapper** mà không cần entity có annotation. Đối tượng **Person** là một bản ghi Java, không phải một entry LDAP tự động.

~~~java
package org.example.directory;

public record Person(
        String uid,
        String fullName,
        String lastName,
        String mail
) {}
~~~

Service hoàn chỉnh:

~~~java
package org.example.directory;

import java.util.List;
import java.util.Optional;
import javax.naming.Name;
import javax.naming.NamingException;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.BasicAttributes;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;

import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;
import org.springframework.stereotype.Service;

import static org.springframework.ldap.query.LdapQueryBuilder.query;

@Service
public class PersonDirectoryService {

    private static final String PEOPLE_BASE = "ou=people";

    private static final AttributesMapper<Person> PERSON_MAPPER = attrs ->
            new Person(
                    value(attrs, "uid"),
                    value(attrs, "cn"),
                    value(attrs, "sn"),
                    value(attrs, "mail")
            );

    private final LdapTemplate ldapTemplate;

    public PersonDirectoryService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    // Đọc theo DN xác định: không tồn tại -> ngoại lệ từ LDAP.
    public Person lookupByUid(String uid) {
        return ldapTemplate.lookup(personDn(uid), PERSON_MAPPER);
    }

    // Tìm theo bộ lọc: không có kết quả -> Optional.empty().
    public Optional<Person> findByUid(String uid) {
        validateUid(uid);
        List<Person> matches = ldapTemplate.search(
                query().base(PEOPLE_BASE)
                        .where("objectClass").is("inetOrgPerson")
                        .and("uid").is(uid),
                PERSON_MAPPER
        );

        if (matches.size() > 1) {
            throw new IllegalStateException(
                    "Có nhiều entry trùng uid trong ou=people: " + uid);
        }
        return matches.stream().findFirst();
    }

    // Tìm tất cả người trong nhánh; giới hạn số lượng ở production.
    public List<Person> listPeople() {
        return ldapTemplate.search(
                query().base(PEOPLE_BASE)
                        .where("objectClass").is("inetOrgPerson"),
                PERSON_MAPPER
        );
    }

    // Tạo một entry mới, theo schema inetOrgPerson.
    public void create(Person person) {
        if (person == null
                || person.fullName() == null || person.fullName().isBlank()
                || person.lastName() == null || person.lastName().isBlank()) {
            throw new IllegalArgumentException("cn và sn là bắt buộc");
        }
        validateUid(person.uid());

        Attributes attrs = new BasicAttributes(true);
        BasicAttribute classes = new BasicAttribute("objectClass");
        classes.add("top");
        classes.add("person");
        classes.add("organizationalPerson");
        classes.add("inetOrgPerson");
        attrs.put(classes);
        attrs.put("uid", person.uid());
        attrs.put("cn", person.fullName());
        attrs.put("sn", person.lastName());

        if (person.mail() != null && !person.mail().isBlank()) {
            attrs.put("mail", person.mail());
        }

        ldapTemplate.bind(personDn(person.uid()), null, attrs);
    }

    // Chỉ sửa mail, không thay thế những thuộc tính khác.
    public void updateMail(String uid, String mail) {
        if (mail == null || mail.isBlank()) {
            throw new IllegalArgumentException("mail không được rỗng");
        }
        ldapTemplate.modifyAttributes(
                personDn(uid),
                new ModificationItem[] {
                        new ModificationItem(
                                DirContext.REPLACE_ATTRIBUTE,
                                new BasicAttribute("mail", mail))
                }
        );
    }

    // Xóa entry theo DN.
    public void deleteByUid(String uid) {
        ldapTemplate.unbind(personDn(uid));
    }

    private static Name personDn(String uid) {
        validateUid(uid);
        return LdapNameBuilder.newInstance(PEOPLE_BASE)
                .add("uid", uid)
                .build();
    }

    private static void validateUid(String uid) {
        if (uid == null || !uid.matches("[a-zA-Z0-9._-]{1,64}")) {
            throw new IllegalArgumentException("Định dạng uid không hợp lệ");
        }
    }

    private static String value(Attributes attrs, String name)
            throws NamingException {
        Attribute attribute = attrs.get(name);
        return attribute == null ? null : (String) attribute.get();
    }
}
~~~

Giải thích các điểm chính trong code:

1. **AttributesMapper** đọc các thuộc tính đã trả về và tạo **Person**. Thuộc tính tùy chọn **mail** có thể là **null**. Trong mô hình phức tạp, LDAP cho phép thuộc tính nhiều giá trị nên cần đọc toàn bộ các giá trị thay vì chỉ gọi **get()**.
2. **personDn(uid)** tạo DN tương đối **uid=alice,ou=people** bằng **LdapNameBuilder**. Builder xử lý cú pháp/escaping của thành phần DN; phép nối chuỗi thủ công dễ làm hỏng DN hoặc cho phép đầu vào tác động đến cấu trúc DN.
3. **search(query, mapper)** dùng **LdapQueryBuilder** để xây bộ lọc. **where(...).is(...)** biểu diễn so khớp chính xác và xử lý escaping giá trị bộ lọc LDAP.
4. **BasicAttributes(true)** tạo tập thuộc tính với tên thuộc tính không phân biệt hoa/thường. **bind** tạo entry có objectClass và các thuộc tính bắt buộc theo schema.
5. **modifyAttributes** sử dụng mã thao tác JNDI **REPLACE_ATTRIBUTE**; không cần lấy toàn bộ entry về rồi ghi đè. **unbind** chỉ xóa đúng DN được chỉ định.

Đây là ví dụ đào tạo nên chưa có phân trang, giới hạn kết quả, kiểm tra trùng uid toàn hệ thống, chính sách định dạng email hoặc lớp chuyển lỗi sang HTTP. Các phần đó cần bổ sung theo directory và yêu cầu ứng dụng thực tế.

## 4. Đọc dữ liệu: lookup và search khác nhau thế nào?

### lookup: biết chính xác DN

Khi đã biết DN tương đối của Alice, gọi:

~~~java
Person alice = personDirectoryService.lookupByUid("alice");
System.out.println(alice.fullName());
~~~

LdapTemplate truy cập trực tiếp **uid=alice,ou=people** dưới base **dc=example,dc=org**. Nếu không có entry tại DN này, thao tác sẽ phát sinh ngoại lệ tương ứng với LDAP. **lookup** thích hợp với khóa định danh/DN đã biết; không cần dựng bộ lọc tìm kiếm.

### search: biết điều kiện, chưa biết DN

Khi cần tìm người theo thuộc tính, sử dụng **search**:

~~~java
Optional<Person> alice = personDirectoryService.findByUid("alice");
List<Person> people = personDirectoryService.listPeople();
~~~

Trong ví dụ, bộ lọc tương ứng với **findByUid** có ý nghĩa:

~~~ldap
(&(objectClass=inetOrgPerson)(uid=alice))
~~~

Điểm khác biệt thực tế: **search** trả về danh sách, nên kết quả rỗng không đồng nghĩa với lỗi kết nối. Mỗi LDAP directory có thể khác nhau về quy tắc duy nhất của **uid**; không nên giả định **uid** là duy nhất trên toàn bộ cây khi chưa có ràng buộc nghiệp vụ hoặc kiểm soát dữ liệu. Ví dụ kiểm tra trường hợp có nhiều bản ghi trong cùng nhánh rồi báo lỗi.

Mặc định tìm kiếm có thể trả nhiều entry hơn dự kiến. Với dữ liệu lớn, cần xác định **search scope** (object/one-level/subtree), giới hạn số kết quả/thời gian, phân trang nếu server hỗ trợ và chỉ yêu cầu các thuộc tính cần dùng. Nếu tìm kiếm rộng hoặc entry có nhiều thuộc tính nhị phân, chi phí đọc và truyền dữ liệu tăng đáng kể.

## 5. Tạo mới: bind và kiểm tra schema

Gọi service:

~~~java
personDirectoryService.create(
        new Person("alice", "Alice Nguyen", "Nguyen", "alice@example.org")
);
~~~

Lệnh **bind** gửi entry đến DN **uid=alice,ou=people**. Thao tác chỉ thành công khi:

- **ou=people** đã tồn tại và DN **uid=alice,ou=people** chưa tồn tại.
- Tài khoản kết nối có quyền thêm entry tại nhánh đích.
- Các **objectClass** và thuộc tính tuân thủ schema; ví dụ **cn**, **sn** không rỗng.
- Giá trị RDN và dữ liệu của entry nhất quán theo quy tắc server.

Nếu DN đã tồn tại, đừng coi **bind** là cập nhật. Khi cần sửa entry có sẵn, dùng thao tác cập nhật rõ ràng. Không nên mặc định thử tạo rồi tự động ghi đè khi gặp lỗi trùng DN: đó có thể là lỗi dữ liệu hoặc thao tác đồng thời cần giải quyết ở tầng nghiệp vụ.

## 6. Cập nhật: modifyAttributes, rename và rebind

Khi chỉ cần đổi email, gọi:

~~~java
personDirectoryService.updateMail("alice", "alice.new@example.org");
~~~

**DirContext.REPLACE_ATTRIBUTE** thay giá trị thuộc tính **mail**; các thuộc tính như **uid**, **cn**, **sn**, **objectClass** không bị thay đổi bởi yêu cầu này. JNDI cũng hỗ trợ hai thao tác khác:

| Mã thao tác | Công dụng | Điểm cần chú ý |
| --- | --- | --- |
| **ADD_ATTRIBUTE** | Thêm thuộc tính hoặc giá trị | Có thể bị từ chối nếu giá trị trùng hoặc schema không cho phép |
| **REPLACE_ATTRIBUTE** | Thay các giá trị của thuộc tính | Có thể làm mất giá trị khác ở thuộc tính nhiều giá trị |
| **REMOVE_ATTRIBUTE** | Xóa thuộc tính hoặc giá trị | Không thể xóa thuộc tính bắt buộc hoặc giá trị đang được bảo vệ |

Để xóa riêng thuộc tính **mail** tùy chọn, có thể dùng:

~~~java
ldapTemplate.modifyAttributes(
        personDn("alice"),
        new ModificationItem[] {
                new ModificationItem(
                        DirContext.REMOVE_ATTRIBUTE,
                        new BasicAttribute("mail"))
        }
);
~~~

Ví dụ trên cần nằm trong service nơi có **ldapTemplate** và **personDn**. Nếu **mail** không tồn tại, server có thể trả lỗi tùy cách xử lý yêu cầu. Với thuộc tính nhiều giá trị như **memberOf** hoặc **telephoneNumber**, phải xác định muốn thay toàn bộ tập giá trị hay chỉ thêm/xóa một giá trị cụ thể.

**rename(oldDn, newDn)** dùng khi cần đổi RDN hoặc DN. Ví dụ đổi **uid=alice,ou=people** thành **uid=alice2,ou=people**. Đây là thay đổi định danh của entry, không phải cập nhật đơn thuần thuộc tính **cn**. Cần xem hành vi của server với thuộc tính RDN cũ, liên kết tham chiếu, quyền di chuyển và giới hạn đổi parent.

**rebind** là thao tác ghi lại binding của một entry với đối tượng/attributes được cung cấp. Nó có ngữ nghĩa thay thế ở mức rộng hơn, nên dễ ghi đè ngoài ý muốn các thuộc tính chưa đọc hoặc do directory quản lý. Khi cập nhật từng trường của entry đang tồn tại, **modifyAttributes** thường rõ ràng và an toàn hơn.

## 7. Xóa entry: unbind

~~~java
personDirectoryService.deleteByUid("alice");
~~~

Lệnh **unbind** xóa entry tại DN đã chỉ định. Khác với SQL, đây không phải lệnh xóa mọi bản ghi trong một bảng; nó tác động đến một node cụ thể của cây LDAP. Server thông thường không cho xóa entry nếu bên dưới còn entry con. ACL, thao tác đồng thời và tham chiếu từ hệ thống khác cũng có thể ảnh hưởng đến tính hợp lệ của việc xóa.

Với API nghiệp vụ, nên xác định rõ quyền xóa, cách xác nhận người dùng mục tiêu và chính sách giữ hồ sơ. Nếu chỉ cần vô hiệu hóa tài khoản, hãy dùng thuộc tính/quy trình phù hợp với schema và directory đang triển khai thay vì mặc định xóa entry.

## 8. Chống LDAP injection và tránh sai DN

LDAP có **hai ngữ cảnh cú pháp cần escaping riêng**:

| Dữ liệu | Nơi sử dụng | Cách xây dựng |
| --- | --- | --- |
| Giá trị một RDN, chẳng hạn **uid** | DN của entry | **LdapNameBuilder** hoặc API **LdapName/Rdn** |
| Giá trị trong điều kiện tìm kiếm | LDAP search filter | **LdapQueryBuilder**, hoặc bộ xây dựng **Filter** của Spring LDAP |

Không dựng filter bằng cách nối trực tiếp dữ liệu từ request vào chuỗi như **(uid= + input + )**. Các ký tự đặc biệt *****, **(**, **)**, dấu gạch chéo ngược và ký tự NUL có quy tắc escaping trong filter. Với truy vấn so khớp chính xác, nên dùng:

~~~java
ldapTemplate.search(
        query().base("ou=people").where("uid").is(uidFromRequest),
        PERSON_MAPPER
);
~~~

Tương tự, không ghép DN bằng **"uid=" + uidFromRequest + ",ou=people"**. DN cũng có ký tự đặc biệt và quy tắc thứ tự RDN. **LdapNameBuilder** giúp biểu diễn DN theo cấu trúc. Việc giới hạn định dạng **uid** trong ví dụ là quy tắc nghiệp vụ bổ sung, không thay thế nhu cầu tạo DN và filter bằng API an toàn. Cũng cần cố định/kiểm soát nhánh tìm kiếm theo quyền của người dùng; escaping đúng không bảo đảm một truy vấn quá rộng là phù hợp.

Nếu cần tìm gần đúng hoặc tìm tiền tố, phải xác định rõ phần ký tự đại diện do ứng dụng chủ động thêm, và escape phần giá trị người dùng cung cấp theo quy tắc filter. Không trao quyền quyết định cấu trúc filter cho chuỗi nhập tự do.

## 9. Xử lý lỗi và tính nhất quán

LdapTemplate chuyển các lỗi LDAP/JNDI phổ biến thành các exception của Spring LDAP. Cần tách **không tìm thấy**, **vi phạm dữ liệu**, **không đủ quyền** và **lỗi hạ tầng**, thay vì trả chung một thông báo như “LDAP thất bại”.

| Tình huống | Biểu hiện có thể gặp | Cách xử lý |
| --- | --- | --- |
| lookup một DN không tồn tại | Lỗi name not found | Chuyển thành kết quả “không có tài khoản” nếu nghiệp vụ cho phép |
| search không có kết quả | Danh sách rỗng | Trả danh sách rỗng hoặc Optional.empty() |
| bind trùng DN | Lỗi already bound/entry already exists | Xử lý xung đột định danh, không tự động ghi đè |
| Thiếu **cn/sn** hoặc sai objectClass | Schema violation | Xem lại dữ liệu và schema, không retry vô hạn |
| Thiếu quyền thêm/sửa/xóa | Insufficient access rights | Kiểm tra ACL và quyền của bind DN |
| Sai thông tin xác thực, TLS, server không sẵn sàng | Authentication/communication failure | Kiểm tra cấu hình, chứng chỉ, timeout và trạng thái directory |
| search quá rộng | Size/time limit hoặc kết quả bị giới hạn | Thu hẹp base/filter, dùng limit và phân trang |

LDAP thường không cung cấp giao dịch nhiều entry giống cơ sở dữ liệu quan hệ. Một chuỗi **bind → modify → unbind** trên nhiều entry không mặc nhiên là một transaction nguyên tử. Khi nghiệp vụ phải cập nhật nhiều hệ thống, cần thiết kế thao tác có thể thực hiện lại an toàn, cơ chế bù trừ và ghi nhận trạng thái thay vì giả định có rollback xuyên hệ thống.

Việc **findByUid** rồi **create** không bảo đảm tránh race condition: một tác vụ khác vẫn có thể tạo DN trong khoảng giữa hai lệnh. Hãy coi lỗi “entry đã tồn tại” của lệnh **bind** là cơ chế xác nhận cuối cùng khi ghi.

## 10. Bảo mật khi đọc và ghi LDAP

- **Bảo vệ kết nối:** dùng LDAPS hoặc StartTLS khi server hỗ trợ; xác minh CA/chứng chỉ và hostname, tránh truyền thông tin xác thực qua LDAP thuần trên mạng không tin cậy.
- **Phân quyền tối thiểu:** tài khoản dịch vụ chỉ được đọc các thuộc tính cần thiết và ghi đúng nhánh được phép. Tách tài khoản/chính sách theo nhu cầu nếu thao tác đọc và ghi có mức quyền khác nhau.
- **Bảo vệ bí mật:** cấu hình mật khẩu từ secret manager/biến môi trường; không ghi DN kèm mật khẩu, giá trị nhạy cảm hoặc toàn bộ Attributes vào log.
- **Giới hạn dữ liệu:** kiểm soát trường được phép sửa; không nhận tên thuộc tính tùy ý từ client rồi chuyển trực tiếp thành ModificationItem.
- **Bảo vệ tìm kiếm:** dùng filter builder, giới hạn base và phạm vi tìm kiếm, timeout, số lượng kết quả; cân nhắc giới hạn tần suất truy vấn.
- **Kiểm soát thay đổi:** ghi audit cho thao tác tạo/sửa/xóa với người thực hiện và DN mục tiêu, nhưng không lưu mật khẩu hay thuộc tính bí mật.

Không tùy ý cập nhật **userPassword** như trường văn bản thường: mỗi directory có quy tắc riêng về băm mật khẩu, chính sách mật khẩu, quyền thay đổi và các extended operation có liên quan. Cần dùng cơ chế quản lý mật khẩu được server hỗ trợ.

## 11. Kiểm thử với một LDAP directory

Một bài kiểm thử tích hợp có giá trị phải chạy trên directory kiểm thử có schema và quyền gần với môi trường mục tiêu. Có thể dùng OpenLDAP trong container hoặc LDAP in-memory dành riêng cho test; lưu ý kết quả với server in-memory chưa chắc phản ánh đầy đủ ACL, TLS hay schema của hệ thống thật.

Chuẩn bị **dc=example,dc=org**, **ou=people**, tài khoản bind có quyền thử nghiệm, và dữ liệu seed độc lập cho mỗi ca. Chạy các bước sau rồi kiểm tra entry thực tế bằng công cụ LDAP client hoặc một lookup/search độc lập:

| Ca kiểm thử | Hành động | Kết quả mong đợi |
| --- | --- | --- |
| Tạo mới | create Alice | DN tồn tại, có objectClass, uid, cn, sn, mail hợp lệ |
| Đọc theo DN | lookupByUid("alice") | Các trường Person đúng với entry |
| Tìm theo filter | findByUid("alice") | Một kết quả; uid khác cho kết quả rỗng |
| Liệt kê | listPeople() | Chỉ lấy người thuộc nhánh và objectClass đã chọn |
| Sửa thuộc tính | updateMail("alice", ...) | mail thay đổi; cn và sn giữ nguyên |
| Xóa entry | deleteByUid("alice") | lookup lại báo không có entry |
| Trùng DN | create hai lần cùng uid | Lần sau bị từ chối; dữ liệu cũ không bị ghi đè |
| Sai schema/quyền | Thiếu sn hoặc bind DN không có quyền ghi | Server từ chối đúng nguyên nhân |
| Đầu vào bất thường | uid có dấu sao, dấu phẩy, dấu ngoặc | Validation hoặc filter/DN builder xử lý đúng, không mở rộng phạm vi truy vấn |
| Kết nối không an toàn | Sai chứng chỉ hoặc sai credentials | Kết nối/xác thực thất bại; ứng dụng không bỏ qua xác minh TLS |

Ví dụ luồng thực hành ngắn:

~~~java
Person initial = new Person(
        "alice", "Alice Nguyen", "Nguyen", "alice@example.org");

personDirectoryService.create(initial);

Person loaded = personDirectoryService.lookupByUid("alice");
assert loaded.fullName().equals("Alice Nguyen");

personDirectoryService.updateMail("alice", "alice.new@example.org");
assert personDirectoryService.lookupByUid("alice")
        .mail().equals("alice.new@example.org");

personDirectoryService.deleteByUid("alice");
assert personDirectoryService.findByUid("alice").isEmpty();
~~~

Đoạn trên minh họa thứ tự kiểm chứng, chưa phải test JUnit độc lập: Java **assert** chỉ chạy khi bật assertions, và test thật cần có setup/teardown, assertions của framework cùng cơ chế khởi tạo directory cô lập. Trong dự án, nên dùng JUnit với fixture/LDIF và dọn dữ liệu sau test; không chạy ca create/delete trên directory sản xuất.

## 12. Tổng kết và bài tập

Đường đi của một thao tác LDAP là: **cấu hình ContextSource/base DN → tạo DN hoặc bộ lọc → LdapTemplate gọi server → LDAP kiểm tra schema/ACL → ánh xạ kết quả hoặc xử lý ngoại lệ**. Với DN đã biết, dùng **lookup**; với điều kiện theo thuộc tính, dùng **search**; với entry mới, dùng **bind**; thay một phần thuộc tính bằng **modifyAttributes**; đổi DN bằng **rename**; xóa entry bằng **unbind**.

Để tự luyện tập, hãy bổ sung vào service phương thức tìm theo **mail** với filter builder, phương thức sửa **cn** nhưng giữ nguyên **sn**, và một ca kiểm thử cố ý tạo trùng DN. Sau đó kiểm tra lại kết quả bằng LDAP client, giải thích vì sao **search** trả danh sách rỗng trong khi **lookup** của DN không tồn tại phát sinh ngoại lệ, và chứng minh tài khoản chỉ có quyền đọc không thể gọi **bind** hoặc **modifyAttributes** thành công.
