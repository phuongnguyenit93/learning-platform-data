# Nạp schema và dữ liệu LDIF xác định trước để kiểm thử Spring Data LDAP

Khi viết ứng dụng **Spring Data LDAP**, một unit test dùng mock có thể xác minh rằng service gọi đúng phương thức repository hoặc `LdapTemplate`. Nhưng nó không thể chứng minh directory thực sự chấp nhận một entry theo `objectClass`, ánh xạ đúng `@Attribute`, kiểm tra DN hay thực hiện bộ lọc theo schema. Để kiểm chứng các hành vi đó, cần **kiểm thử tích hợp với một directory chứa schema và dữ liệu biết trước**.

Phương pháp phổ biến là khởi tạo LDAP server dành riêng cho test, **nạp schema trước**, rồi **nạp các entry từ tệp LDIF cố định** (*fixture*). Mỗi lần chạy kiểm thử bắt đầu từ cùng một trạng thái, giúp kết quả có thể lặp lại, dễ debug và không phụ thuộc vào dữ liệu của môi trường production.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt **schema**, **dữ liệu LDIF**, **entry gốc/cha**, **test fixture** và **môi trường directory**.
- Viết LDIF chứa entry đúng DN, `objectClass`, các thuộc tính bắt buộc theo `MUST` và thuộc tính tùy chọn theo `MAY`.
- Giải thích thứ tự **khởi tạo server → nạp schema → tạo entry cha → nạp entry con → chạy test**.
- Phân biệt nạp dữ liệu theo schema chuẩn với việc thêm schema tùy chỉnh vào OpenLDAP `cn=config`.
- Nạp, kiểm tra và cô lập fixture bằng lệnh LDAP; cấu hình `LdapTemplate`/repository đọc directory test.
- Viết kiểm thử tích hợp xác minh truy vấn, ODM, lọc theo thuộc tính hiện diện và các lỗi schema; bảo đảm test không đụng vào production.

## 2. Vì sao dữ liệu kiểm thử phải xác định trước?

Giả sử một test yêu cầu:

```java
List<PersonEntry> people = repository.findByEmailIsNotNull();
assertEquals(1, people.size());
```

Nếu chạy trên một directory dùng chung, một đồng nghiệp thêm người dùng có `mail` cũng có thể khiến test thất bại dù code đúng. Ngược lại, một entry bị xóa có thể khiến test báo lỗi không liên quan đến thay đổi mã nguồn. Fixture xác định trước giải quyết vấn đề này bằng cách quy định **cây LDAP và tập dữ liệu đầu vào**.

Ví dụ trạng thái directory mong muốn:

```text
dc=org
└── dc=example
    └── ou=people
        ├── uid=alice    cn=Alice Nguyen, sn=Nguyen, mail=alice@example.org
        └── uid=bob      cn=Bob Tran, sn=Tran, không có mail
```

Trong cây thực tế, DN được viết từ **lá đến gốc**:

```text
uid=alice,ou=people,dc=example,dc=org
```

Từ đây, có thể kiểm tra rằng truy vấn `uid=alice` trả đúng Alice, tìm thuộc tính `mail` hiện diện chỉ trả Alice, và search scope `ONELEVEL` tại `ou=people` chỉ xét con trực tiếp.

### Các thành phần trong một test tích hợp

| Thành phần | Chức năng | Ví dụ |
| --- | --- | --- |
| Directory test | LDAP server chỉ dành cho kiểm thử. | Một container OpenLDAP độc lập hoặc LDAP embedded. |
| Schema | Định nghĩa object class, thuộc tính, kiểu giá trị và matching rule. | `person`/`inetOrgPerson`; có thể có lớp tùy chỉnh. |
| Entry cha | Cây nền để entry con có chỗ tồn tại. | `dc=example,dc=org`, `ou=people,...` |
| LDIF fixture | Mô tả entry và giá trị cố định. | Alice có `mail`, Bob không có `mail`. |
| Test application | Kết nối và thao tác qua Spring Data LDAP. | `LdapRepository`, `LdapTemplate`, JUnit 5. |
| Assertions | Xác minh dữ liệu thực tế thay vì suy đoán từ mock. | Đúng hai `uid`; chỉ Alice có `mail`. |

## 3. Chọn chiến lược directory cho môi trường test

Có nhiều cách dựng LDAP test server:

| Chiến lược | Ưu điểm | Điều cần chú ý |
| --- | --- | --- |
| **Container LDAP khởi tạo từ ảnh cố định** | Gần môi trường thực tế, hỗ trợ schema và ACL của sản phẩm directory đã chọn. | Cần container runtime; phải cố định image version và biết cơ chế bootstrap. |
| **Embedded/in-memory LDAP** | Khởi tạo nhanh, dễ tách vòng đời theo test suite. | Schema, extension, matching rule, ACL có thể khác OpenLDAP/AD production. |
| **Server test quản lý riêng** | Có thể chia sẻ giữa nhiều job. | Dễ bị nhiễm dữ liệu từ job khác; phải tạo naming context riêng và reset đáng tin cậy. |

**Nguyên tắc:** nếu ứng dụng chạy trên OpenLDAP và cần kiểm thử schema/ACL cụ thể, nên có ít nhất một lớp integration test trên **OpenLDAP phiên bản phù hợp**. In-memory LDAP phù hợp với các test nhanh, nhưng một kết quả tốt trên in-memory server không bảo đảm tự động đúng trên mọi directory khác.

Nên ưu tiên **directory mới cho mỗi suite hoặc mỗi pipeline**. Đừng nạp fixture vào directory đang phục vụ người dùng thật. Địa chỉ, DN quản trị và mật khẩu test phải được tách riêng khỏi cấu hình production.

## 4. LDIF là gì và cần tuân thủ quy tắc nào?

**LDAP Data Interchange Format (LDIF)** là định dạng văn bản dùng để biểu diễn entry LDAP hoặc các thao tác thay đổi entry. Nó được mô tả trong RFC 2849.

Một entry LDIF cơ bản gồm:

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
```

Quy tắc cần nhớ:

- `dn:` xác định **Distinguished Name** đầy đủ của entry. Các RDN tách bằng dấu phẩy theo cú pháp DN LDAP.
- Mỗi dòng `tênThuocTinh: giaTri` biểu diễn một giá trị. Thuộc tính đa giá trị thường có **nhiều dòng cùng tên**, ví dụ nhiều `objectClass`.
- Một **dòng trống** tách hai bản ghi LDIF. Nếu quên dòng trống, trình nạp có thể đọc sai bản ghi.
- Giá trị cần được mã hóa theo LDIF: dữ liệu UTF-8 không biểu diễn an toàn theo dạng text thường có thể dùng cú pháp **base64 `::`**; không tự mã hóa mọi Unicode thành chuỗi escape Java.
- LDIF có quy tắc **folding**: dòng vật lý bắt đầu bằng một dấu cách có thể nối với dòng trước. Khi sửa fixture, cần giữ nguyên nội dung sau khi unfold.
- `dn`, `objectClass` và tên thuộc tính phải khớp schema; việc tệp có cú pháp LDIF hợp lệ **không chứng minh** directory sẽ chấp nhận entry.

Đừng nhầm hai loại LDIF:

| Loại LDIF | Nội dung | Khi sử dụng |
| --- | --- | --- |
| **Dữ liệu entry** | Các block bắt đầu bằng `dn:` và danh sách thuộc tính; không có `changetype`. | Seed một directory trống hoặc import snapshot. |
| **Thao tác thay đổi** | `dn:` kèm `changetype: add/modify/delete/moddn` và cú pháp thao tác. | Thực thi thay đổi qua `ldapmodify` hoặc công cụ tương đương. |

Trong bài này, fixture người dùng là **entry LDIF thuần**, thích hợp để import vào directory test mới.

## 5. Nạp fixture sử dụng schema chuẩn LDAP

Đa số directory LDAP đã cài sẵn các lớp chuẩn như `top`, `domain`, `organizationalUnit`, `person`, `organizationalPerson`, `inetOrgPerson`. Với những lớp này, thường **không cần** tạo định nghĩa schema mới; chỉ cần chắc chắn schema tương ứng đã được server bật.

Ví dụ minh họa tổ chức fixture:

```text
src/test/resources/ldap/
├── 01-base.ldif
├── 02-people.ldif
└── 03-persons.ldif
```

Đây là đường dẫn minh họa **bên trong dự án Java của người học**, không phải các tệp do bài học tự sinh. Việc tách theo nhóm giúp kiểm soát thứ tự và dễ xác định entry nào gây lỗi.

### 5.1. Bước 1 — Entry gốc: `01-base.ldif`

Với directory test **chưa có naming context** `dc=example,dc=org` và được cấu hình cho phép tạo naming context đó:

```ldif
dn: dc=example,dc=org
objectClass: top
objectClass: domain
dc: example
```

**Điểm cần chú ý:** nhiều LDAP image/container đã **tự tạo** suffix/naming context khi khởi động. Khi server đã có `dc=example,dc=org`, **không import lại** entry này, vì thao tác có thể báo `entryAlreadyExists`. Cách xử lý đúng là phân biệt **server tự tạo root** và **server yêu cầu seed root**, không cố dùng chung hai bước nạp cho mọi sản phẩm LDAP.

### 5.2. Bước 2 — Entry cha: `02-people.ldif`

Sau khi có naming context:

```ldif
dn: ou=people,dc=example,dc=org
objectClass: top
objectClass: organizationalUnit
ou: people
```

Entry `ou=people` phải được tạo **trước** khi nhập `uid=alice` và `uid=bob` bên dưới. Nếu thiếu entry cha, server thường trả `noSuchObject`, không thể “tự tạo mọi parent” chỉ vì một DN con có chuỗi đầy đủ.

### 5.3. Bước 3 — Entry người dùng: `03-persons.ldif`

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

dn: uid=bob,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: bob
cn: Bob Tran
sn: Tran
```

Đặt ý đồ fixture rõ ràng:

- **Alice** có `uid`, `cn`, `sn` và `mail`.
- **Bob** có `uid`, `cn`, `sn` nhưng **không có `mail`**. Đây là dữ liệu cần thiết để kiểm tra truy vấn **thuộc tính hiện diện/vắng mặt**, không phải thiếu sót ngẫu nhiên.
- `cn` và `sn` là các thuộc tính `MUST` được kế thừa từ `person`. `uid` và `mail` được dùng theo nhu cầu ứng dụng; `mail` thường là `MAY` trong `inetOrgPerson`.
- Không lưu mật khẩu thật vào fixture. Nếu bài kiểm thử cần đăng nhập, tạo tài khoản test chuyên dụng, chính sách credential riêng và tránh đưa bí mật vào repository.

Hai entry dùng DN khác nhau, nên có thể được thêm vào cùng directory test. Giá trị tên, email và UID nên cố định, dễ hiểu và không trùng với dữ liệu được tạo trong những test khác.

### 5.4. Kiểm tra schema và dữ liệu trước khi import

Trước khi nạp:

1. Xác nhận directory **đã bật** các định nghĩa `domain`, `organizationalUnit` và `inetOrgPerson`.
2. Xác nhận suffix `dc=example,dc=org` được server cấu hình hỗ trợ.
3. Kiểm tra **đường dẫn và thứ tự**: root (nếu cần) → `ou=people` → các entry người dùng.
4. Kiểm tra LDIF được lưu ở UTF-8, có dòng trống giữa các entry và không có DN trùng.
5. Kiểm tra người dùng LDAP dùng để nạp dữ liệu có quyền thêm entry tại các DN test.

## 6. Khi nào phải nạp schema tùy chỉnh?

Nếu kiểm thử cần một thuộc tính **không có trong schema chuẩn** như `employeeCode`, không thể chỉ thêm dòng `employeeCode: E-1001` vào entry `inetOrgPerson` rồi mong server chấp nhận. Directory cần có **attribute type** và **object class cho phép thuộc tính đó**.

Ví dụ schema tùy chỉnh cho **OpenLDAP dùng dynamic configuration `cn=config`**. Đây là **minh họa riêng cho OpenLDAP**, không phải một schema LDIF có thể nạp nguyên vẹn vào ApacheDS, Active Directory hoặc mọi embedded server.

### 6.1. Tệp `schema-training.ldif` cho OpenLDAP `cn=config`

```ldif
dn: cn=training,cn=schema,cn=config
objectClass: olcSchemaConfig
cn: training
olcAttributeTypes: ( 1.3.6.1.4.1.32473.1.1 NAME 'employeeCode' DESC 'Demo employee code' EQUALITY caseIgnoreMatch SUBSTR caseIgnoreSubstringsMatch SYNTAX 1.3.6.1.4.1.1466.115.121.1.15 SINGLE-VALUE )
olcObjectClasses: ( 1.3.6.1.4.1.32473.2.1 NAME 'trainingAux' DESC 'Demo auxiliary class' SUP top AUXILIARY MUST employeeCode )
```

Giải thích:

- `olcAttributeTypes` định nghĩa thuộc tính `employeeCode`, cú pháp Directory String, cách so khớp bằng và chuỗi con, và giới hạn `SINGLE-VALUE`.
- `olcObjectClasses` định nghĩa auxiliary class `trainingAux` có `MUST employeeCode`.
- Dải OID `1.3.6.1.4.1.32473` được dùng cho **ví dụ tài liệu**; **không** sao chép làm OID sản phẩm. Hệ thống thực tế phải có nhánh OID được cấp phù hợp.
- Dòng dài trong ví dụ vẫn là **một giá trị thuộc tính LDIF**. Nếu cần xuống dòng, phải dùng quy tắc folding của LDIF để không làm thay đổi cú pháp schema.

Nạp định nghĩa này vào **configuration database**, không phải vào suffix dữ liệu `dc=example,dc=org`. Trong nhiều cấu hình OpenLDAP, tài khoản quản trị thông thường của suffix **không** có quyền sửa `cn=config`.

Ví dụ với một OpenLDAP test container có bật **LDAPI** và quyền quản trị phù hợp:

```bash
ldapadd -Y EXTERNAL -H ldapi:/// \
  -f src/test/resources/ldap/schema-training.ldif
```

Lệnh trên chỉ áp dụng khi cơ chế SASL EXTERNAL qua local socket được cấu hình và người gọi có quyền cập nhật `cn=config`. Nếu container không hỗ trợ, cần dùng **cơ chế bootstrap schema được image/server hỗ trợ** hoặc tài khoản cấu hình được ủy quyền; không cố dùng tài khoản LDAP người dùng để sửa schema.

**Thứ tự bắt buộc:** cài/bật schema trước khi tạo entry dùng `trainingAux` hoặc `employeeCode`. Nếu cố nạp entry trước, server có thể báo object class/attribute type chưa được nhận diện hoặc vi phạm schema.

### 6.2. Fixture sử dụng schema tùy chỉnh

Trong **một suite riêng** đã bật schema `trainingAux`, Alice có thể được mô tả như sau:

```ldif
dn: uid=alice,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
objectClass: trainingAux
uid: alice
cn: Alice Nguyen
sn: Nguyen
mail: alice@example.org
employeeCode: E-1001
```

**Không nạp đồng thời** entry Alice từ `03-persons.ldif` và entry Alice trong ví dụ này vào cùng directory: chúng có **trùng DN**. Hãy chọn **một trong hai bộ fixture**, hoặc tạo một dữ liệu thay đổi theo đúng cú pháp `changetype: modify` sau khi schema đã nạp.

Trong test schema âm tính, một entry có `objectClass: trainingAux` **nhưng thiếu `employeeCode`** phải bị directory test từ chối vì `MUST` của auxiliary class. Đó là bài kiểm tra có giá trị: nó chứng minh schema tùy chỉnh thật sự đang được thi hành, thay vì chỉ chứng minh ứng dụng đọc được một chuỗi từ LDIF.

## 7. Nạp và xác minh fixture bằng công cụ LDAP

Các ví dụ sau giả định OpenLDAP **test** lắng nghe tại `ldap://127.0.0.1:1389`; admin dữ liệu là `cn=admin,dc=example,dc=org` và suffix đã được tạo. Port, tài khoản và cấu hình cụ thể phải phù hợp với test server đang chạy.

### 7.1. Nạp đúng thứ tự

```bash
# Nếu server đã tự tạo dc=example,dc=org, bỏ qua 01-base.ldif.
# Chỉ dùng 01-base.ldif nếu server chưa có root và cho phép tạo root.
# ldapadd -x -H ldap://127.0.0.1:1389 \
#   -D "cn=admin,dc=example,dc=org" -W \
#   -f src/test/resources/ldap/01-base.ldif

ldapadd -x -H ldap://127.0.0.1:1389 \
  -D "cn=admin,dc=example,dc=org" -W \
  -f src/test/resources/ldap/02-people.ldif

ldapadd -x -H ldap://127.0.0.1:1389 \
  -D "cn=admin,dc=example,dc=org" -W \
  -f src/test/resources/ldap/03-persons.ldif
```

`-W` yêu cầu nhập mật khẩu tương tác, tránh ghi mật khẩu vào lệnh. `ldapadd` là thao tác **thêm mới**; chạy lại nguyên bộ fixture trên directory chưa được reset thường gây lỗi `entryAlreadyExists`. Điều đó không nên bị giấu bằng cách bỏ qua mọi lỗi.

Trong môi trường dùng TLS, phải cấu hình trust store/chứng chỉ và URL phù hợp. URL `ldap://127.0.0.1:1389` ở trên chỉ là minh họa kết nối **localhost của server test cô lập**; không dùng kết nối plaintext trên mạng thật.

### 7.2. Kiểm tra entry cha và nội dung

```bash
ldapsearch -x -LLL -H ldap://127.0.0.1:1389 \
  -D "cn=admin,dc=example,dc=org" -W \
  -b "ou=people,dc=example,dc=org" \
  -s one "(objectClass=inetOrgPerson)" uid cn sn mail
```

Kỳ vọng truy vấn trả **đúng hai entry** `uid=alice` và `uid=bob`, không có người dùng khác dưới `ou=people`. Alice có `mail`; Bob không có `mail`. Lệnh `-s one` chỉ xét các entry con trực tiếp nên không trả OU cha. `-LLL` giúp output LDIF gọn hơn.

Để xác nhận một entry theo DN:

```bash
ldapsearch -x -LLL -H ldap://127.0.0.1:1389 \
  -D "cn=admin,dc=example,dc=org" -W \
  -b "uid=alice,ou=people,dc=example,dc=org" \
  -s base "(objectClass=*)" uid cn sn mail
```

Kết quả có thể được directory chuẩn hóa về cách biểu diễn nhất định. Test nên kiểm tra **giá trị và tập entry cần thiết**, không phụ thuộc thứ tự xuất hiện của các thuộc tính trong response LDIF.

## 8. Cấu hình Spring Boot trỏ tới directory test

Ví dụ cấu hình **profile `test`** khi directory được khởi tạo trước lúc chạy kiểm thử:

```yaml
spring:
  ldap:
    urls: ${LDAP_TEST_URL:ldap://127.0.0.1:1389}
    base: dc=example,dc=org
    username: ${LDAP_TEST_BIND_DN:cn=admin,dc=example,dc=org}
    password: ${LDAP_TEST_BIND_PASSWORD}
```

Lưu trong `src/test/resources/application-test.yml` của **dự án ví dụ** và cấu hình biến môi trường trong test runner. URL/DN/password ở trên chỉ là **thông tin cho directory test**, không để ứng dụng vô tình kết nối tới production. Với directory test thực tế nên ưu tiên tài khoản có quyền tối thiểu: dùng account chỉ đọc cho test truy vấn và account test riêng cho case ghi.

Vì `spring.ldap.base` đã là `dc=example,dc=org`, base tìm kiếm truyền cho `LdapTemplate` thường là:

```java
query().base("ou=people")
```

Không truyền lặp `ou=people,dc=example,dc=org` vào code đã có `ContextSource` với base trên nếu API mong DN tương đối.

### Cấu hình embedded khác với OpenLDAP `cn=config`

Một số phiên bản Spring Boot hỗ trợ embedded LDAP và cơ chế cấu hình LDIF, ví dụ property nhóm `spring.ldap.embedded.*`. Cần kiểm tra phiên bản Spring Boot, embedded provider và đường dẫn fixture tương ứng. **Không giả định** một provider embedded có thể đọc trực tiếp LDIF `olcSchemaConfig` của OpenLDAP, vì định dạng cấu hình schema và cách bootstrap có thể khác nhau.

Nếu yêu cầu bài test chỉ là repository, filter và ODM trên schema chuẩn, embedded LDAP có thể đủ. Nếu cần xác minh cú pháp schema, ACL hoặc ordering/matching rule của **OpenLDAP**, hãy dùng OpenLDAP test instance tương ứng.

## 9. Entity ODM và repository đọc fixture

Để kiểm tra ánh xạ entry, ví dụ entity `PersonEntry.java`:

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
public class PersonEntry {
    @Id
    private Name dn;

    @Attribute(name = "uid")
    private String uid;

    @Attribute(name = "cn")
    private String commonName;

    @Attribute(name = "sn")
    private String surname;

    @Attribute(name = "mail")
    private String email;

    protected PersonEntry() {
        // Constructor dành cho cơ chế ODM.
    }

    public Name getDn() { return dn; }
    public String getUid() { return uid; }
    public String getCommonName() { return commonName; }
    public String getSurname() { return surname; }
    public String getEmail() { return email; }
}
```

Repository `PersonRepository.java`:

```java
package com.example.directory;

import java.util.List;
import java.util.Optional;
import org.springframework.data.ldap.repository.LdapRepository;

public interface PersonRepository extends LdapRepository<PersonEntry> {
    Optional<PersonEntry> findByUid(String uid);
    List<PersonEntry> findByEmailIsNotNull();
}
```

Trong ví dụ, tên property Java `email` ánh xạ sang thuộc tính LDAP `mail` qua `@Attribute(name="mail")`. Các method truy vấn phát sinh từ **tên property Java**, không phải từ tên thuộc tính LDAP nếu hai tên khác nhau.

## 10. Kiểm thử tích hợp với JUnit 5

Ví dụ dưới đây giả định server test đã được reset và nạp **đúng fixture chuẩn** `01/02/03` trước khi khởi động test, và ứng dụng đã cấu hình component/repository scanning phù hợp. Nó không tự tạo container; phần quản lý vòng đời server nên nằm ở setup của suite hoặc pipeline.

```java
package com.example.directory;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;

import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.SearchScope;
import org.springframework.test.context.ActiveProfiles;

import static org.springframework.ldap.query.LdapQueryBuilder.query;

@SpringBootTest
@ActiveProfiles("test")
class SeededDirectoryIT {
    @Autowired PersonRepository repository;
    @Autowired LdapTemplate ldapTemplate;

    @Test
    void repositoryMapsSeededEntries() {
        PersonEntry alice = repository.findByUid("alice").orElseThrow();
        PersonEntry bob = repository.findByUid("bob").orElseThrow();

        assertEquals("Alice Nguyen", alice.getCommonName());
        assertEquals("Nguyen", alice.getSurname());
        assertEquals("alice@example.org", alice.getEmail());
        assertNull(bob.getEmail()); // Trong fixture Bob không có mail.
    }

    @Test
    void presenceFilterFindsOnlyAlice() {
        Set<String> withMail = repository.findByEmailIsNotNull()
                .stream()
                .map(PersonEntry::getUid)
                .collect(Collectors.toSet());
        assertEquals(Set.of("alice"), withMail);
    }

    @Test
    void oneLevelSearchFindsExactlyTwoPeople() {
        var q = query()
                .base("ou=people")
                .searchScope(SearchScope.ONELEVEL)
                .attributes("uid")
                .where("objectClass").is("inetOrgPerson");

        List<String> ids = ldapTemplate.search(q,
                (AttributesMapper<String>) attrs ->
                        String.valueOf(attrs.get("uid").get()));

        assertEquals(2, ids.size());
        assertEquals(Set.of("alice", "bob"), Set.copyOf(ids));
    }
}
```

Các assertion được chọn để xác minh **dữ liệu thực tế đã nạp**:

- `repository.findByUid("alice")` kiểm tra phương thức truy vấn derived và ánh xạ ODM.
- `findByEmailIsNotNull()` kiểm tra ý nghĩa presence filter: Alice có `mail`, Bob không có.
- `LdapTemplate` với `ONELEVEL` và thuộc tính trả về `uid` xác minh cả nhánh, scope và projection.

LDAP không bảo đảm thứ tự kết quả mặc định. Vì thế ví dụ kiểm tra **tập UID**, đồng thời so sánh kích thước để phát hiện kết quả thừa. Nếu fixture thay đổi, cần cập nhật **hợp đồng test** có chủ đích, tránh để dữ liệu mới vô tình làm test mất tính xác định.

## 11. Kiểm thử schema và lỗi dự kiến

Ngoài happy path, nên có những case **âm tính** kiểm chứng server thi hành schema.

| Tình huống | Dữ liệu/việc thử | Kết quả mong đợi |
| --- | --- | --- |
| Thiếu thuộc tính `MUST` | Entry `inetOrgPerson` không có `sn`. | Server từ chối vì vi phạm object class/schema. |
| Thiếu parent | Thử thêm `uid=unknown,ou=missing,...` khi `ou=missing` không tồn tại. | Server trả lỗi thiếu đối tượng cha. |
| DN trùng | Thêm lại Alice trên một directory chưa reset. | Server từ chối `entryAlreadyExists`. |
| Thuộc tính không được schema cho phép | Thêm `employeeCode` khi chưa có schema/class phù hợp. | Server từ chối hoặc báo attribute type không được nhận diện. |
| Thiếu `MUST` trong schema tùy chỉnh | Entry có `trainingAux` nhưng không có `employeeCode`. | Server từ chối sau khi schema tùy chỉnh đã được bật. |
| Thiếu thuộc tính `MAY` | Bob không có `mail`. | Entry hợp lệ nếu không có chính sách server khác bắt buộc mail. |
| Không đủ quyền | Tài khoản chỉ đọc gọi `bind` tạo entry. | Server từ chối theo ACL. |

Ví dụ kiểm thử tạo entry cố ý thiếu `sn`:

```java
import javax.naming.Name;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.BasicAttributes;
import org.springframework.ldap.support.LdapNameBuilder;

Name invalidDn = LdapNameBuilder.newInstance()
        .add("ou", "people")
        .add("uid", "missing-sn-case")
        .build();

BasicAttributes invalidAttrs = new BasicAttributes(true);
BasicAttribute classes = new BasicAttribute("objectClass");
classes.add("top");
classes.add("person");
classes.add("organizationalPerson");
classes.add("inetOrgPerson");
invalidAttrs.put(classes);
invalidAttrs.put("uid", "missing-sn-case");
invalidAttrs.put("cn", "Missing Surname");
// Cố tình KHÔNG thêm sn: kiểm tra schema phía directory.

// Trong một test âm tính, xác nhận bind bị từ chối bởi schema,
// đồng thời kiểm tra invalidDn không được tạo trong directory.
ldapTemplate.bind(invalidDn, null, invalidAttrs);
```

Đoạn code cuối **không phải happy-path và không nên chạy như một method độc lập**: lời gọi `bind` được chủ động thiết kế để thất bại. Trong JUnit, bọc thao tác trong `assertThrows(...)` với loại exception Spring LDAP phù hợp phiên bản; đồng thời xác minh entry không tồn tại và dọn dữ liệu nếu cần. Không viết test chỉ bắt mọi `RuntimeException` rồi coi mọi lỗi kết nối/ACL là bằng chứng schema đúng.

**Quan trọng:** một test dùng validator Java chặn thiếu `sn` từ trước không kiểm chứng server. Với test schema, phải gửi payload thật tới **directory test** để nhận phản hồi từ server.

## 12. Bảo đảm chạy lại được và cô lập môi trường

Fixture “xác định trước” không chỉ là dùng một tệp LDIF có tên cố định. Nó đòi hỏi kiểm soát **vòng đời server, thứ tự nạp, dữ liệu cũ và các test khác**.

Một quy trình đề xuất:

```text
1. Khởi tạo directory test mới, phiên bản/policy cố định
2. Xác nhận naming context và schema chuẩn đã có
3. Nạp schema tùy chỉnh (chỉ trong suite cần mở rộng)
4. Tạo/nạp root nếu chưa được server tạo
5. Nạp entry cha, ví dụ ou=people
6. Nạp đúng một bộ fixture người dùng
7. Chạy kiểm tra nhanh bằng ldapsearch, sau đó JUnit tests
8. Dừng và hủy directory test, không để trạng thái rò rỉ sang suite khác
```

Nếu suite cần **thêm/sửa/xóa** entry, có hai lựa chọn phổ biến:

- **Khởi tạo lại directory** trước mỗi nhóm test cần dữ liệu sạch; phù hợp khi có container/embedded server tự động.
- **Dùng nhánh test riêng hoặc UID ngẫu nhiên có kiểm soát**, dọn đúng các entry test tạo trong `finally`/`@AfterEach`; đừng xóa cả nhánh dùng chung một cách thiếu kiểm soát.

Không chạy nhiều test ghi đồng thời trên **cùng một bộ fixture có tên cố định** nếu chúng cùng sửa hoặc xóa Alice/Bob. Các test chỉ đọc có thể chia sẻ fixture bất biến, nhưng test ghi cần dữ liệu hoặc directory riêng để tránh phụ thuộc thứ tự.

### Cố định phiên bản và nguồn đầu vào

- Ghi rõ phiên bản LDAP image/embedded provider; không dựa vào thẻ `latest` nếu cần tính lặp lại.
- Version-control fixture LDIF và định nghĩa schema mẫu cùng code test; thay đổi fixture phải được review như thay đổi API.
- Đảm bảo test pipeline thực sự import các tệp; đừng chỉ lưu LDIF trong `src/test/resources` rồi cho rằng Spring tự nạp vào mọi LDAP server.
- Không dùng một đường kết nối production làm fallback khi biến môi trường test bị thiếu. Cấu hình nên **fail fast** nếu không có directory test.
- Dùng địa chỉ localhost hoặc mạng test riêng, TLS khi cần và tài khoản quyền tối thiểu.

## 13. Chẩn đoán khi nạp LDIF hoặc chạy test thất bại

| Triệu chứng | Nguyên nhân khả dĩ | Hướng giải quyết |
| --- | --- | --- |
| `entryAlreadyExists` khi nạp root | Server/container đã tạo `dc=example,dc=org`. | Bỏ qua fixture root hoặc dùng directory sạch, không import đè. |
| `noSuchObject` khi thêm Alice | `ou=people` hoặc suffix chưa tồn tại. | Nạp entry cha trước; kiểm tra DN và naming context. |
| `objectClassViolation` khi thêm `inetOrgPerson` | Thiếu `cn`/`sn` hoặc cấu trúc objectClass không đúng. | Kiểm tra `MUST` được kế thừa và payload thực tế. |
| `undefinedAttributeType` hoặc unknown object class | Chưa nạp schema tùy chỉnh hoặc sai định nghĩa. | Nạp schema trước; xác minh đúng config database và schema server. |
| `insufficientAccessRights` | Tài khoản nạp fixture không được ghi nhánh đích. | Cấp quyền test phù hợp hoặc dùng admin test; không nới ACL production. |
| Fixture có Alice nhưng `findByUid` không ra kết quả | `spring.ldap.base`, `@Entry(base)`, DN hoặc objectClass không khớp. | So sánh DN đầy đủ trên server với base tương đối trong ứng dụng. |
| Test hiện diện email trả cả Bob | Dữ liệu Bob vô tình có `mail`, hoặc directory chưa reset. | Kiểm tra `ldapsearch` và trạng thái fixture, không chỉ debug repository. |
| Dữ liệu tiếng Việt đọc sai | File không dùng UTF-8 hoặc được mã hóa LDIF không đúng. | Đảm bảo Unicode hợp lệ, cân nhắc `::` base64 cho giá trị cần thiết. |
| Chạy test lần đầu pass, lần hai fail | Dữ liệu cũ chưa dọn, fixture bị import hai lần. | Tạo directory sạch cho mỗi run hoặc reset xác định trước. |
| Test phụ thuộc thứ tự | Nhiều test cùng sửa Alice/Bob hay kỳ vọng LDAP trả kết quả có thứ tự. | Cô lập test ghi, so sánh theo tập DN/UID. |
| Nạp schema OpenLDAP vào embedded server thất bại | Provider không dùng định dạng `olcSchemaConfig`. | Chọn cú pháp bootstrap schema phù hợp với provider. |

### Checklist debug ngắn

1. **Server đã chạy chưa?** Kiểm tra kết nối đúng URL/port và tài khoản test.
2. **Schema đã có chưa?** Kiểm tra object class, attribute type và matching rule trên directory đó.
3. **Naming context và entry cha đúng chưa?** So sánh DN đầy đủ với base cấu hình.
4. **Import có lỗi từ bản ghi nào?** Đọc mã lỗi và dòng LDIF liên quan.
5. **Directory đang chứa chính xác dữ liệu nào?** Dùng `ldapsearch` trước khi kết luận repository sai.
6. **Các test có làm biến đổi fixture không?** Tắt song song hoặc cấp naming context riêng cho nhóm test ghi.

## 14. Bài thực hành

**Bài 1.** Tệp `03-persons.ldif` có Alice/Bob dưới `ou=people,dc=example,dc=org`, nhưng directory chưa tồn tại `ou=people`. Nạp người dùng trước có thành công không? Thứ tự sửa?

**Đáp án:** Thường không thành công vì thiếu entry cha. Tạo suffix/root (nếu server chưa có), thêm `ou=people`, rồi mới nạp Alice/Bob.

**Bài 2.** Một container đã tự tạo `dc=example,dc=org`. Vì sao nạp thêm `01-base.ldif` gây lỗi và xử lý thế nào?

**Đáp án:** Hai entry trùng DN nên server từ chối `entryAlreadyExists`. Bỏ bước nạp root, chỉ seed các nhánh con hoặc dùng cơ chế bootstrap nhất quán.

**Bài 3.** Alice có `mail`, Bob không có. Viết truy vấn repository xác minh chỉ Alice có email.

**Đáp án:** Ánh xạ `@Attribute(name="mail") private String email;` và method `findByEmailIsNotNull()`. Assert tập `uid` trả về bằng `{"alice"}` sau khi fixture được nạp vào directory sạch.

**Bài 4.** Vì sao một fixture dùng `employeeCode` bị OpenLDAP từ chối dù cú pháp LDIF đúng?

**Đáp án:** Server có thể chưa biết attribute type đó hoặc entry chưa mang object class cho phép nó. Nạp schema custom vào `cn=config` theo cơ chế OpenLDAP trước, dùng `trainingAux`/`employeeCode` trong entry và kiểm tra schema.

**Bài 5.** Một test dùng mock `LdapTemplate` xác nhận `bind(...)` được gọi. Nó đã chứng minh `sn` là bắt buộc theo schema chưa?

**Đáp án:** Chưa. Mock không thực thi schema. Cần thử tạo entry `inetOrgPerson` thiếu `sn` trên directory test có schema thật và xác minh server từ chối.

**Bài 6.** Một test thay đổi Alice rồi để lại dữ liệu cho test tiếp theo. Vì sao khó gọi đây là fixture xác định trước?

**Đáp án:** Kết quả test phụ thuộc thứ tự/chạy song song và trạng thái còn lại. Nên có directory mới, fixture reset cho mỗi run hoặc tách dữ liệu ghi và dọn đúng các entry test tạo.

## 15. Ghi nhớ

- **Schema quyết định entry hợp lệ**, **LDIF quyết định dữ liệu ban đầu**, và **directory test** thực thi quy tắc LDAP thật mà mock không thể thay thế.
- Với schema chuẩn đã có, thường chỉ cần nạp fixture LDIF; với thuộc tính/object class tùy chỉnh, **nạp schema trước dữ liệu sử dụng nó**.
- **Parent trước child:** suffix/root (nếu chưa tồn tại) → OU cha → entry con. DN và `objectClass` phải hợp lệ.
- Giữ fixture **cố định, UTF-8, không trùng DN** và có mục đích rõ cho mỗi entry, ví dụ Alice có `mail` còn Bob không có.
- Xác minh bằng `ldapsearch`, rồi kiểm thử `LdapRepository`, `LdapTemplate`, ánh xạ ODM và ràng buộc schema bằng assertions trên tập entry.
- Cô lập, reset và quản lý vòng đời directory test; **không dùng production** để seed dữ liệu hoặc chạy kiểm thử ghi/xóa.
