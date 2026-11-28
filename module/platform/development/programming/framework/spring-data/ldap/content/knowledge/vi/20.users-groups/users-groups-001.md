# Mô hình người dùng với person, organizationalPerson và inetOrgPerson

Trong một directory LDAP, người dùng được biểu diễn bằng **entry** nằm trong cây thư mục (DIT), có **Distinguished Name (DN)**, các thuộc tính và tập `objectClass` xác định cấu trúc hợp lệ. Ba object class thường gặp để mô hình hóa con người là `person`, `organizationalPerson` và `inetOrgPerson`. Chúng có **quan hệ kế thừa**, vì vậy việc chọn class ảnh hưởng trực tiếp đến những thuộc tính bắt buộc/được phép lưu trữ, cách tìm kiếm và cách ánh xạ entry sang đối tượng Java bằng Spring Data LDAP.

Bài học thuộc chương **Người dùng và nhóm** của `SPRING_DATA_LDAP`. Trọng tâm là thiết kế entry người dùng đúng schema, phân biệt các lớp object class, và kết nối mô hình đó với repository, `LdapTemplate`, CRUD, kiểm soát DN, filter, kết nối an toàn và kiểm thử với LDAP directory.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích sự khác nhau giữa entry, DN, RDN, thuộc tính, object class và schema LDAP.
- Mô tả cây kế thừa `top → person → organizationalPerson → inetOrgPerson` và biết thuộc tính nào luôn bắt buộc.
- Chọn `person`, `organizationalPerson` hoặc `inetOrgPerson` theo dữ liệu nghiệp vụ cần lưu.
- Tạo entry người dùng hợp lệ dưới dạng LDIF; phân biệt `uid`, `cn` và DN.
- Ánh xạ entry bằng `@Entry`, `@Id` và `@Attribute`, tìm người dùng qua Spring Data LDAP repository hoặc `LdapTemplate`.
- Nhận diện lỗi schema, sai DN, trùng định danh, lộ mật khẩu và LDAP filter injection.

## 2. Entry, DN, objectClass và schema liên hệ thế nào?

Hãy hình dung một thư mục có cấu trúc:

~~~text
dc=example,dc=org
├── ou=people
│   ├── cn=Pham Van An
│   ├── cn=Tran Thi Mai
│   └── uid=lan
└── ou=groups
    └── cn=engineering
~~~

Mỗi dòng bên dưới `ou=people` tương ứng một **entry**. Một entry có:

| Thành phần | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| DN | Tên phân biệt entry trong toàn bộ cây. | `uid=lan,ou=people,dc=example,dc=org` |
| RDN | Thành phần tên của entry tại vị trí cha hiện tại. | `uid=lan` |
| Attribute | Cặp tên thuộc tính và một hoặc nhiều giá trị. | `cn: Nguyen Thi Lan`, `mail: lan@example.org` |
| `objectClass` | Khai báo kiểu entry và những thuộc tính được phép/cần có. | `inetOrgPerson` |
| LDAP schema | Các quy tắc kiểm tra object class, kiểu dữ liệu và thuộc tính. | `person` yêu cầu `cn` và `sn` |

**DN là địa chỉ của entry**, còn `uid` hoặc `mail` là thuộc tính bên trong entry. Không được giả định `uid` luôn là RDN: một entry `inetOrgPerson` có thể dùng `cn=...` làm RDN mà vẫn có `uid`. Ngược lại, khi dùng `uid=lan` làm RDN, thuộc tính `uid` cần có giá trị khớp với RDN theo quy tắc tên của LDAP.

Schema còn quy định loại object class:

- **STRUCTURAL:** Xác định bản chất cấu trúc của entry; các class trong cùng chuỗi kế thừa có thể cùng xuất hiện trong `objectClass`.
- **AUXILIARY:** Bổ sung thuộc tính theo cơ chế mà schema của server cho phép.
- **ABSTRACT:** Dùng làm gốc/khung cho object class khác; ví dụ `top`.

`person`, `organizationalPerson` và `inetOrgPerson` đều là **STRUCTURAL** và nằm trên cùng một chuỗi kế thừa. Chúng **không** phải ba kiểu độc lập để gắn tùy ý cho một entry.

## 3. Cây kế thừa person → organizationalPerson → inetOrgPerson

~~~mermaid
flowchart TD
    A["top (ABSTRACT)"] --> B["person (STRUCTURAL)"]
    B --> C["organizationalPerson (STRUCTURAL)"]
    C --> D["inetOrgPerson (STRUCTURAL)"]
    B -.-> E["Bắt buộc: cn, sn"]
    C -.-> F["Bổ sung thông tin công việc / tổ chức"]
    D -.-> G["Bổ sung uid, mail, displayName, ..."]
~~~

Mọi class con **kế thừa** các thuộc tính bắt buộc (`MUST`) và các thuộc tính được phép (`MAY`) của class cha.

| Object class | Mục đích | Thuộc tính `MUST` | Ví dụ thuộc tính `MAY` nổi bật |
| --- | --- | --- | --- |
| `person` | Thông tin tối thiểu về một cá nhân. | `cn`, `sn` | `description`, `telephoneNumber`, `userPassword`, `seeAlso` |
| `organizationalPerson` | Cá nhân trong một tổ chức, có thông tin chức vụ/đơn vị. | Kế thừa `cn`, `sn`; không bổ sung `MUST` mới. | `title`, `ou`, `l`, `postalAddress`, `postalCode` |
| `inetOrgPerson` | Người dùng có nhiều thuộc tính phù hợp ứng dụng mạng và doanh nghiệp. | Kế thừa `cn`, `sn`; không bổ sung `MUST` mới. | `uid`, `mail`, `givenName`, `displayName`, `employeeNumber`, `mobile` |

Các cột `MAY` chỉ liệt kê **ví dụ tiêu biểu**, không phải toàn bộ schema; directory còn có thể triển khai object class, thuộc tính mở rộng theo nhà cung cấp. Cần kiểm tra schema thực tế của server khi thêm thuộc tính đặc thù.

### 3.1. person: mô hình tối thiểu

`person` phù hợp khi chỉ cần biết một cá nhân có tên và họ:

~~~ldif
dn: cn=Pham Van An,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
cn: Pham Van An
sn: Pham
description: External contact
~~~

Điểm cần chú ý:

- `cn` (*common name*) và `sn` (*surname*) là **bắt buộc**. Nếu thiếu một trong hai, server có thể trả lỗi `objectClassViolation`.
- `cn` không nhất thiết là một định danh đăng nhập ổn định. Tên hiển thị có thể đổi và có thể trùng giữa nhiều người.
- `userPassword` nằm trong tập thuộc tính mà `person` có thể cho phép, nhưng **có thể lưu không có nghĩa là phải lưu**. Cách lưu/truy cập/kiểm tra mật khẩu phụ thuộc cấu hình server và chính sách bảo mật.

### 3.2. organizationalPerson: thêm ngữ cảnh tổ chức

`organizationalPerson` kế thừa `person` và cho phép lưu thêm các thuộc tính liên quan đến vị trí công việc, chẳng hạn `title` và `ou`:

~~~ldif
dn: cn=Tran Thi Mai,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
cn: Tran Thi Mai
sn: Tran
title: QA Engineer
ou: Quality Assurance
telephoneNumber: +84 28 5555 0101
~~~

`organizationalPerson` không yêu cầu phải có `title` hay `ou`. Entry trong ví dụ vẫn cần `cn` và `sn` vì chúng được **kế thừa** từ `person`.

### 3.3. inetOrgPerson: mô hình người dùng thường dùng trong ứng dụng

`inetOrgPerson` kế thừa `organizationalPerson` rồi bổ sung nhiều thuộc tính phổ biến như `uid`, `mail`, `givenName`, `displayName`, `employeeNumber`. Đây thường là lựa chọn tiện dụng cho tài khoản người dùng trong ứng dụng LDAP doanh nghiệp.

~~~ldif
dn: uid=lan,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: lan
cn: Nguyen Thi Lan
sn: Nguyen
givenName: Lan
displayName: Nguyen Thi Lan
mail: lan@example.org
title: Backend Developer
ou: Engineering
~~~

Ở đây:

- `uid=lan` là **RDN**; toàn bộ chuỗi `uid=lan,ou=people,dc=example,dc=org` mới là **DN**.
- `cn` và `sn` vẫn bắt buộc mặc dù `inetOrgPerson` không tự khai báo thêm `MUST`.
- `uid` và `mail` là thuộc tính được phép, **không bắt buộc** chỉ vì đã sử dụng `inetOrgPerson`.
- Các thuộc tính tùy chọn không tự bảo đảm duy nhất trong toàn directory. Chính sách định danh/kiểm soát trùng phụ thuộc ứng dụng, dữ liệu và cấu hình server.

**Vì sao LDIF liệt kê cả bốn `objectClass`?** Việc ghi `top` và toàn bộ chuỗi cha giúp entry dễ đọc, nhất quán với mô hình schema và với cách nhiều directory biểu diễn tập lớp của entry. Khi dùng Spring LDAP ODM, metadata mapping có thể khai báo các class cần thiết; hãy kiểm chứng kết quả tạo entry trên server thực tế.

## 4. Chọn object class nào?

| Yêu cầu | Lựa chọn thường phù hợp | Lý do |
| --- | --- | --- |
| Lưu một người liên hệ tối thiểu với tên/họ | `person` | Ít thuộc tính nghiệp vụ, vẫn tuân thủ schema. |
| Lưu hồ sơ nhân sự với phòng ban/chức vụ | `organizationalPerson` | Có các thuộc tính tổ chức như `ou`, `title`. |
| Lưu người dùng ứng dụng có `uid`, email, thông tin công việc | `inetOrgPerson` | Có đủ các thuộc tính người dùng phổ biến và kế thừa lớp tổ chức. |
| Lưu nhóm và thành viên | Object class nhóm, ví dụ `groupOfNames` | Nhóm là entry loại khác, không phải class con của `person`. |

Không nên “nâng cấp” tất cả entry thành `inetOrgPerson` nếu chúng là những đối tượng khác con người; cũng không nên thêm những class **STRUCTURAL** không cùng chuỗi kế thừa chỉ để nhận thêm một thuộc tính. Nếu cần mở rộng schema, hãy dùng class/thuộc tính mà directory hỗ trợ và thiết kế đúng quy tắc STRUCTURAL/AUXILIARY.

## 5. Quan hệ giữa người dùng và nhóm

Chủ đề “Người dùng và nhóm” cần phân biệt entry người dùng với entry nhóm. `inetOrgPerson` mô tả **con người**, còn nhóm có thể dùng `groupOfNames`, trong đó `member` trỏ tới **DN của thành viên**:

~~~ldif
dn: cn=engineering,ou=groups,dc=example,dc=org
objectClass: top
objectClass: groupOfNames
cn: engineering
member: uid=lan,ou=people,dc=example,dc=org
member: cn=Tran Thi Mai,ou=people,dc=example,dc=org
~~~

Trong schema chuẩn, `groupOfNames` yêu cầu `cn` và ít nhất một `member`. Vì thành viên được tham chiếu bằng DN, việc **đổi DN** của một người dùng có thể ảnh hưởng liên kết nhóm, tùy server có cơ chế tự cập nhật tham chiếu hay không.

Đừng mặc định entry người dùng luôn có thuộc tính `memberOf`. Thuộc tính này thường là thuộc tính tính toán hoặc phần mở rộng phụ thuộc directory. Khi kiểm tra tư cách thành viên, hãy hiểu schema/đặc tính server và cân nhắc truy vấn nhóm theo `member=<DN>`.

## 6. Ánh xạ inetOrgPerson sang Java bằng Spring Data LDAP

Với Spring Data LDAP, mô hình entity kết nối dữ liệu LDAP với đối tượng Java. Có thể khai báo:

- `@Entry`: class Java ánh xạ sang entry LDAP, chỉ định base và `objectClasses`.
- `@Id`: thuộc tính giữ DN của entry, thường dùng kiểu `javax.naming.Name`.
- `@Attribute`: ánh xạ một thuộc tính LDAP sang trường Java.
- `LdapRepository`: thực hiện các thao tác đọc/ghi theo mô hình repository.

### 6.1. Entity cho entry người dùng

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
public class DirectoryPerson {

    @Id
    private Name dn;

    @Attribute(name = "uid")
    private String uid;

    @Attribute(name = "cn")
    private String commonName;

    @Attribute(name = "sn")
    private String surname;

    @Attribute(name = "givenName")
    private String givenName;

    @Attribute(name = "mail")
    private String email;

    public Name getDn() { return dn; }
    public void setDn(Name dn) { this.dn = dn; }

    public String getUid() { return uid; }
    public void setUid(String uid) { this.uid = uid; }

    public String getCommonName() { return commonName; }
    public void setCommonName(String commonName) { this.commonName = commonName; }

    public String getSurname() { return surname; }
    public void setSurname(String surname) { this.surname = surname; }

    public String getGivenName() { return givenName; }
    public void setGivenName(String givenName) { this.givenName = givenName; }

    public String getEmail() { return email; }
    public void setEmail(String email) { this.email = email; }
}
~~~

Ví dụ trên sử dụng **ODM annotations của Spring LDAP**, có mặt trong hệ sinh thái Spring Data LDAP. `@Id` không đại diện cho cột khóa chính trong CSDL quan hệ: nó biểu diễn tên phân biệt của **entry** trong LDAP.

Nếu server cho phép một thuộc tính có nhiều giá trị (`cn`, `mail`, v.v.), ánh xạ nó sang một `String` duy nhất chỉ phù hợp khi **quy ước nghiệp vụ bảo đảm một giá trị**. Nếu cần bảo toàn nhiều giá trị, hãy chọn kiểu collection và kiểm thử khả năng ánh xạ với phiên bản Spring LDAP đang sử dụng.

### 6.2. Repository tìm người dùng

~~~java
import java.util.List;
import java.util.Optional;

import org.springframework.data.ldap.repository.LdapRepository;

public interface DirectoryPersonRepository
        extends LdapRepository<DirectoryPerson> {

    Optional<DirectoryPerson> findByUid(String uid);

    List<DirectoryPerson> findBySurname(String surname);
}
~~~

Cấu hình kết nối giả định:

~~~yaml
spring:
  ldap:
    urls: ldaps://ldap.example.org:636
    base: dc=example,dc=org
    username: cn=svc-reader,ou=service,dc=example,dc=org
    password: YOUR_SECRET_FROM_ENV
~~~

Ở đây `@Entry(base = "ou=people")` mô tả nhánh entry tương đối với phần gốc cấu hình, còn `spring.ldap.base` chỉ định gốc directory cho context. Chi tiết biểu diễn DN tương đối/đầy đủ có thể phụ thuộc cách ứng dụng tạo entity và cấu hình `ContextSource`; hãy kiểm thử đọc, tạo và đổi tên DN trên directory đang dùng.

Phương thức `findByUid` được sinh từ tên phương thức dựa trên thuộc tính `uid` của entity. Tuy nhiên, `Optional` mang giả định **tối đa một** kết quả; nếu dữ liệu directory có nhiều entry trùng `uid`, cần có ràng buộc nhất quán và xử lý lỗi phù hợp.

### 6.3. Truy vấn rõ ràng với LdapTemplate

Nếu cần điều khiển phạm vi tìm kiếm và filter:

~~~java
import java.util.List;

import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;

public class DirectoryLookup {
    private final LdapTemplate ldapTemplate;

    public DirectoryLookup(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<String> findCommonNamesByUid(String uid) {
        if (uid == null || uid.isBlank()) {
            return List.of();
        }

        LdapQuery query = LdapQueryBuilder.query()
                .base("ou=people")
                .where("objectClass").is("inetOrgPerson")
                .and("uid").is(uid);

        return ldapTemplate.search(
                query,
                (AttributesMapper<String>) attrs ->
                        (String) attrs.get("cn").get()
        );
    }
}
~~~

`LdapQueryBuilder` tạo bộ lọc từ tên thuộc tính và **giá trị đầu vào được escape** theo cách của thư viện, phù hợp hơn việc nối chuỗi kiểu `"(uid=" + uid + ")"`. Nếu cần xử lý thêm quyền truy cập, số lượng kết quả hoặc thuộc tính đa giá trị, có thể chọn mapper và chiến lược truy vấn chuyên biệt.

Đừng trộn lẫn **LDAP filter escaping** và **DN escaping**: chúng dùng quy tắc khác nhau. Với DN tạo từ đầu vào người dùng, hãy sử dụng API xây dựng DN như `LdapNameBuilder` hoặc `LdapName`, không ghép chuỗi DN thủ công.

## 7. Tạo và cập nhật entry đúng schema

Một ứng dụng cần xác định rõ định danh, thuộc tính bắt buộc và chính sách đổi tên trước khi thực hiện CRUD.

### 7.1. Trước khi tạo (Create)

Giả sử muốn thêm người dùng có `uid=linh`:

1. Kiểm tra `uid` theo quy tắc định danh của doanh nghiệp; không cho phép rỗng.
2. Chuẩn bị DN hợp lệ, ví dụ `uid=linh,ou=people,dc=example,dc=org`.
3. Gán chuỗi `objectClass` thích hợp cho `inetOrgPerson`.
4. Cung cấp cả `cn` và `sn`, cùng `uid` dùng làm RDN.
5. Nếu cần, gán `mail`, `givenName`, `title`; không ép mọi thuộc tính tùy chọn phải có.
6. Lưu entry bằng repository/`LdapTemplate` với tài khoản có quyền tạo ở nhánh tương ứng.
7. Xác minh có đúng một entry mang định danh theo quy ước nghiệp vụ.

**Lưu ý race condition:** Truy vấn “chưa tồn tại” trước khi tạo không tự giải quyết việc hai request đồng thời cố tạo cùng một entry. Directory thường chặn **trùng DN**, nhưng điều đó không đồng nghĩa tự bảo đảm `uid` duy nhất giữa các nhánh hoặc ở các DN khác nhau.

### 7.2. Khi cập nhật (Update)

Có thể sửa `mail`, `title`, `telephoneNumber` trong phạm vi schema và ACL. Trước khi lưu, phải bảo toàn `cn`, `sn` và tập object class thích hợp.

Không biến `cn` hoặc `uid` thành “khóa bất biến” chỉ vì nó từng nằm trong DN. Nếu sửa thuộc tính đang được dùng làm RDN, có thể cần **Modify DN / Rename** thay vì chỉ sửa attribute. Đổi DN có thể ảnh hưởng nhóm, tham chiếu và các hệ thống bên ngoài giữ DN cũ.

### 7.3. Khi xóa (Delete)

Xóa entry là thao tác trên DN và phụ thuộc quyền ACL. Trước khi xóa nên xác định chính sách xử lý tham chiếu nhóm, ứng dụng đã lưu DN, và yêu cầu lưu vết. LDAP không mặc nhiên xử lý liên đới như khóa ngoại trong cơ sở dữ liệu quan hệ.

## 8. Bảo mật khi lưu và truy vấn người dùng

Các entry người dùng thường chứa dữ liệu cá nhân và đôi khi cả thuộc tính hỗ trợ xác thực. Hãy áp dụng những nguyên tắc sau:

- Dùng **LDAPS** hoặc **StartTLS được thiết lập thành công trước khi Bind**; kiểm tra chứng chỉ và tên máy chủ.
- Dùng tài khoản dịch vụ có quyền tối thiểu cần thiết, nhất là khi tìm người dùng hoặc đọc nhóm; không mặc định tài khoản này có quyền sửa mọi entry.
- Không ánh xạ hoặc trả về `userPassword` như dữ liệu hồ sơ thông thường. Không lưu mật khẩu plaintext hay in mật khẩu trong log; cơ chế lưu trữ/kiểm chứng do directory quản lý.
- Chỉ đọc những thuộc tính cần cho nghiệp vụ; kiểm tra quyền đọc `mail`, số điện thoại và thông tin nhân sự theo chính sách.
- Dùng bộ dựng filter/escaping API để xử lý đầu vào; kiểm tra kết quả nhiều entry thay vì ngầm chọn bản ghi đầu tiên.
- Xác thực người dùng bằng Bind phù hợp thay vì coi “tìm thấy DN” là đăng nhập thành công. Phải từ chối mật khẩu rỗng tại tầng ứng dụng.

Cần phân biệt **xác thực** (Bind chứng minh thông tin đăng nhập) với **phân quyền** (ACL LDAP và chính sách ứng dụng). `inetOrgPerson` mô tả cấu trúc hồ sơ; nó **không tự tạo quyền**, không tự sinh mật khẩu và không tự bảo đảm tài khoản được đăng nhập.

## 9. Những lỗi thường gặp

| Lỗi thiết kế hoặc thao tác | Dấu hiệu/hệ quả | Cách khắc phục |
| --- | --- | --- |
| Entry `person` không có `sn` | Bị từ chối theo schema, thường có `objectClassViolation`. | Bổ sung cả `cn` và `sn`. |
| Đặt `mail` trên entry chỉ khai báo `person` | Server có thể từ chối thuộc tính không được phép. | Chọn object class hỗ trợ `mail`, ví dụ `inetOrgPerson`. |
| Gắn hai structural class độc lập | Vi phạm quy tắc structural object class. | Chỉ dùng chuỗi kế thừa hợp lệ; cân nhắc auxiliary phù hợp. |
| Cho rằng `uid` mặc nhiên duy nhất | Hai entry khác DN có thể cùng `uid`. | Quy định phạm vi duy nhất và cấu hình/kiểm tra ràng buộc. |
| Coi `cn` là username | Tên người có thể trùng hoặc đổi. | Quy ước định danh ổn định riêng (`uid` hoặc ID nghiệp vụ). |
| Sửa RDN như một thuộc tính thông thường | DN và tham chiếu có thể không khớp kỳ vọng. | Dùng thao tác Rename/Modify DN và rà soát tham chiếu. |
| Ghép chuỗi tạo filter LDAP | Ký tự đặc biệt có thể thay đổi ý nghĩa filter. | Dùng `LdapQueryBuilder` hoặc escaping filter chuẩn. |
| Map thuộc tính đa giá trị thành một chuỗi mà không có quy ước | Mất thông tin hoặc cập nhật không chính xác. | Thiết kế kiểu dữ liệu phù hợp và kiểm thử. |
| Coi `memberOf` luôn tồn tại | Không tìm được nhóm trên directory khác. | Truy vấn nhóm theo schema đã xác minh. |

## 10. Bài thực hành kiểm thử với directory

Chuẩn bị một LDAP test server (ví dụ OpenLDAP hoặc một LDAP directory nhúng mà môi trường Spring hỗ trợ), bật schema và tạo nhánh `ou=people`, `ou=groups`. Không sử dụng mật khẩu và thông tin cá nhân thật.

Có thể kiểm tra entry sau khi tạo bằng tiện ích `ldapsearch` (tùy môi trường cài đặt), nhập mật khẩu an toàn qua `-W`:

~~~bash
ldapsearch -x \
  -H ldaps://ldap.example.org:636 \
  -D "cn=svc-reader,ou=service,dc=example,dc=org" -W \
  -b "ou=people,dc=example,dc=org" \
  "(uid=lan)" dn objectClass cn sn uid mail title
~~~

Lệnh này minh họa việc tìm entry và lấy các thuộc tính cần thiết. LDAP server thử nghiệm phải cấu hình TLS và trust certificate hợp lệ.

### Ma trận trường hợp nên kiểm thử

| Ca kiểm thử | Kết quả mong đợi |
| --- | --- |
| Tạo `person` với `cn` và `sn` | Entry hợp lệ, có thể đọc lại. |
| Tạo `person` thiếu `sn` | Server từ chối do vi phạm schema. |
| Tạo `organizationalPerson` với `title`, `ou` | Lưu/đọc được các thuộc tính mở rộng, vẫn có `cn` và `sn`. |
| Tạo `inetOrgPerson` có `uid` và `mail` | Query theo `uid` tìm đúng entry và các trường Java ánh xạ phù hợp. |
| Tạo entry chỉ có `person` nhưng chứa `mail` | Server tuân thủ schema từ chối nếu không có object class khác cho phép `mail`. |
| Tìm `uid` chứa các ký tự đặc biệt của LDAP filter | Không bị thay đổi cấu trúc filter, không trả ra các entry ngoài ý muốn. |
| Thêm hai entry khác DN nhưng trùng `uid` | Kiểm tra ứng dụng/directory có áp dụng chính sách duy nhất không; không mặc định schema tự chặn. |
| Đổi DN của user đang nằm trong nhóm | Kiểm tra `member` có được cập nhật đúng theo chính sách server/ứng dụng. |
| Đọc `mail` bằng account không có quyền | ACL từ chối hoặc ẩn thuộc tính đúng chính sách. |

Ở mức Spring Data LDAP, viết kiểm thử tích hợp cho repository và `LdapTemplate` trên directory thật/nhúng, khởi tạo LDIF fixture và **dọn dữ liệu sau kiểm thử**. Nên kiểm tra dữ liệu đọc lại từ directory sau các thao tác tạo, sửa, đổi DN và xóa thay vì chỉ kiểm tra object Java trước khi lưu.

## 11. Câu hỏi tự ôn tập

1. `inetOrgPerson` kế thừa từ class nào, và vì sao một entry `inetOrgPerson` vẫn phải có `cn`, `sn`?
2. `uid` khác DN thế nào? Vì sao hai entry khác DN vẫn có thể trùng `uid`?
3. Nếu cần `mail` và `displayName`, lựa chọn giữa `person` và `inetOrgPerson` khác nhau ở điểm gì?
4. Nếu người dùng đổi username đang dùng làm RDN, thao tác LDAP nào cần cân nhắc?
5. Vì sao ánh xạ `mail` thành `String` có thể không phù hợp với mọi directory?
6. `memberOf` và `member` khác nhau ra sao trong mô hình nhóm?
7. Vì sao tìm thấy entry `inetOrgPerson` chưa đủ để kết luận người dùng đã đăng nhập thành công?

**Ghi nhớ:** `person` đặt nền tảng với `cn` và `sn`; `organizationalPerson` bổ sung thuộc tính tổ chức; `inetOrgPerson` bổ sung thuộc tính người dùng thông dụng như `uid` và `mail`. Cả ba cùng nằm trên một chuỗi kế thừa structural. Trong Spring Data LDAP, hãy ánh xạ **đúng schema**, quản lý **DN rõ ràng**, truy vấn **filter an toàn** và kiểm thử trên directory có cấu hình thực tế.

### Tài liệu tham khảo

- [RFC 4512 — LDAP: Directory Information Models](https://www.rfc-editor.org/rfc/rfc4512): mô hình entry, schema và quan hệ object class.
- [RFC 4519 — LDAP: Schema for User Applications](https://www.rfc-editor.org/rfc/rfc4519): định nghĩa `person`, `organizationalPerson`, `groupOfNames` và nhiều thuộc tính chuẩn.
- [RFC 2798 — Definition of the inetOrgPerson LDAP Object Class](https://www.rfc-editor.org/rfc/rfc2798): định nghĩa `inetOrgPerson` và những thuộc tính mở rộng.
- [Spring Data LDAP Reference](https://docs.spring.io/spring-data/ldap/reference/): repository và các quy ước ánh xạ với LDAP.
- [Spring LDAP Reference](https://docs.spring.io/spring-ldap/reference/): `LdapTemplate`, ODM annotations, context, kết nối và truy vấn.
