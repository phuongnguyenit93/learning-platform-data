# Định danh bằng `Name` và hợp đồng của phương thức CRUD trong LDAP Repository

## 1. Vì sao ID của LDAP khác ID của cơ sở dữ liệu quan hệ?

Trong **Spring Data LDAP**, mỗi entry trong dịch vụ thư mục có một **Distinguished Name (DN)** xác định vị trí của nó trong cây. Entry đồng thời có tập thuộc tính như `uid`, `cn`, `sn`, `mail`, `member`, cùng các `objectClass` quy định cấu trúc và schema. Repository giúp truy cập các entry dưới dạng đối tượng Java, nhưng khác với bảng quan hệ có khóa chính `Long` hay UUID, **định danh chuẩn của một entry là DN**.

Xét cây directory:

```text
dc=example,dc=org
├── ou=people
│   ├── uid=alice
│   │   ├── objectClass: inetOrgPerson
│   │   ├── uid: alice
│   │   ├── cn: Alice Nguyen
│   │   └── sn: Nguyen
│   └── uid=bob
│       ├── uid: bob
│       ├── cn: Bob Tran
│       └── sn: Tran
└── ou=groups
    └── cn=reviewers
```

DN đầy đủ của Alice là:

```text
uid=alice,ou=people,dc=example,dc=org
```

Ở đây `uid=alice` là **Relative Distinguished Name (RDN)** của entry so với entry cha `ou=people,...`. Chỉ có thuộc tính `uid=alice` chưa chắc đủ xác định duy nhất entry trên toàn directory: một entry khác có thể có `uid=alice` ở `ou=contractors`. Vì vậy, khi gọi `findById`, `deleteById` hoặc nhận `@Id` trong mô hình Spring Data LDAP, **ID là DN**, không phải giá trị của một thuộc tính đơn lẻ.

| Khái niệm | Ví dụ | Vai trò |
| --- | --- | --- |
| Thuộc tính nghiệp vụ | `uid=alice`, `mail=alice@example.org` | Phục vụ tìm kiếm/lọc và nghiệp vụ; không nhất thiết duy nhất trong toàn directory |
| RDN | `uid=alice` | Xác định entry tương đối với entry cha |
| DN đầy đủ | `uid=alice,ou=people,dc=example,dc=org` | Định danh vị trí entry trong directory |
| `javax.naming.Name` | `new LdapName("uid=alice,ou=people")` | Kiểu Java thể hiện DN phục vụ repository/ODM |
| ID repository | `Name`, qua thuộc tính `@Id` | Khóa nhận dạng cho hợp đồng CRUD |

**Mục tiêu:** hiểu vì sao Spring Data LDAP dùng `javax.naming.Name`, cách ánh xạ DN sang entity, hợp đồng CRUD thực tế và cách tránh lỗi khi tạo, cập nhật, xóa hoặc đổi DN.

## 2. `javax.naming.Name`, `LdapName` và DN tương đối

### 2.1. Các kiểu Java quan trọng

`javax.naming.Name` là interface biểu diễn tên phân cấp trong JNDI. `javax.naming.ldap.LdapName` là implementation phù hợp với cú pháp LDAP DN; `LdapNameBuilder` của Spring LDAP hỗ trợ xây dựng DN theo từng thành phần và escape giá trị.

```java
import javax.naming.Name;
import javax.naming.ldap.LdapName;
import org.springframework.ldap.support.LdapNameBuilder;

Name aliceDn = new LdapName("uid=alice,ou=people");

// Dùng builder với giá trị nhận từ người dùng:
String inputUid = "alice";
Name safeDn = LdapNameBuilder
        .newInstance("ou=people")
        .add("uid", inputUid)
        .build();
```

Hai biến đại diện cho DN tương đối `uid=alice,ou=people`. Builder cho phép truyền giá trị RDN có ký tự đặc biệt như dấu phẩy hoặc ký tự escape mà không tự lắp ghép DN sai cú pháp. Vẫn phải kiểm tra **quy tắc nghiệp vụ** của `uid` (độ dài, tập ký tự, phạm vi OU được phép); escape chỉ bảo đảm cú pháp.

Không xây dựng DN trực tiếp bằng:

```java
// Không dùng với input chưa tin cậy:
String dn = "uid=" + inputUid + ",ou=people";
```

Với giá trị chứa dấu phẩy, dấu `=`, dấu `+`, ký tự đặc biệt hoặc ký tự phân tách, nối chuỗi có thể làm DN sai hoặc khiến dữ liệu bị hiểu thành thành phần tên khác.

### 2.2. Base DN của `ContextSource` ảnh hưởng thế nào?

Giả sử `LdapContextSource` cấu hình:

```yaml
spring:
  ldap:
    urls: "ldaps://ldap.example.org:636"
    base: "dc=example,dc=org"
    username: "${LDAP_BIND_DN}"
    password: "${LDAP_BIND_PASSWORD}"
```

Các DN thường được truyền vào `LdapTemplate`/LDAP repository là **tương đối với base `dc=example,dc=org`**, ví dụ:

```text
uid=alice,ou=people
```

Trong khi DN thực tế trên server là:

```text
uid=alice,ou=people,dc=example,dc=org
```

Các API có thể sử dụng quy ước DN tương đối theo `ContextSource`; đừng nối thêm `dc=example,dc=org` khi base đã được cấu hình, vì sẽ dễ tạo đường dẫn sai. Khi đổi `ContextSource.base` hoặc cấu hình nhiều directory, cần kiểm tra lại toàn bộ DN đầu vào. Một chuỗi DN dùng được với ứng dụng A chưa chắc có ý nghĩa giống hệt trong ứng dụng B.

**DN không phải ID bất biến:** chuyển Alice từ `ou=people` sang `ou=contractors` sẽ đổi DN. Từ góc nhìn repository, đó là **thay đổi tên/vị trí entry**, không chỉ sửa một trường văn bản.

## 3. ODM: đánh dấu DN bằng `@Id`

Spring Data LDAP sử dụng Object-Directory Mapping (**ODM**) của Spring LDAP. Entity cần có `@Entry` và một trường `@Id` kiểu `javax.naming.Name` hoặc kiểu triển khai của nó.

Chú ý import chính xác:

```java
import org.springframework.ldap.odm.annotations.Entry;
import org.springframework.ldap.odm.annotations.Id;
import org.springframework.ldap.odm.annotations.Attribute;
import org.springframework.ldap.odm.annotations.DnAttribute;
```

**Không dùng** `org.springframework.data.annotation.Id` hoặc `jakarta.persistence.Id` cho entity LDAP ODM. Chúng thuộc cơ chế mapping khác và không thay thế được `org.springframework.ldap.odm.annotations.Id`.

### 3.1. Entity minh họa

Giả sử entry người dùng được lưu trực tiếp dưới `ou=people`. Để tạo entry mới khi chưa có DN, trường `uid` có thể dùng `@DnAttribute(index = 0)` tạo RDN ở cấp trực tiếp dưới base `@Entry`.

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
public class PersonEntry {

    @Id
    private Name dn;

    @Attribute(name = "uid")
    @DnAttribute(value = "uid", index = 0)
    private String uid;

    @Attribute(name = "cn")
    private String commonName;

    @Attribute(name = "sn")
    private String surname;

    @Attribute(name = "mail")
    private String email;

    public PersonEntry() {}

    public Name getDn() { return dn; }
    public void setDn(Name dn) { this.dn = dn; }

    public String getUid() { return uid; }
    public void setUid(String uid) { this.uid = uid; }

    public String getCommonName() { return commonName; }
    public void setCommonName(String value) { this.commonName = value; }

    public String getSurname() { return surname; }
    public void setSurname(String value) { this.surname = value; }

    public String getEmail() { return email; }
    public void setEmail(String value) { this.email = value; }
}
```

Giải thích:

- **`@Entry`** khai báo nhánh chứa entry và các `objectClass` cần ánh xạ/tạo mới. Danh sách lớp cần phù hợp schema và thừa kế của server thật.
- **`@Id Name dn`** giữ DN để đọc, sửa và xóa đúng entry. DN không tự biến thành `Long` hoặc UUID.
- **`@DnAttribute(..., index = 0)`** khai báo một thành phần RDN để ODM có thể tính DN khi tạo entry mới với `dn == null`. Trong ví dụ một cấp, `uid` tạo RDN ở dưới `ou=people`.
- **`@Attribute(name = "uid")`** cho biết `uid` đồng thời phải được lưu như thuộc tính LDAP. `@DnAttribute` tự nó không miễn trừ mapping thuộc tính; schema phải chấp nhận cách ánh xạ được chọn.
- **`cn` và `sn`** là những thuộc tính bắt buộc theo schema thường dùng của `person`/`inetOrgPerson`. Không nên cố `save` khi thiếu chúng.
- **`mail`** là thuộc tính tùy chọn trong nhiều schema; entity/mapper cần xử lý trường hợp không có giá trị.

Ví dụ có thể cần điều chỉnh `@DnAttribute` nếu entry nằm sâu trong nhiều OU, nếu RDN không phải `uid`, hoặc nếu directory sử dụng schema riêng. Nếu cấu hình ID không đầy đủ, ODM có thể không suy ra được DN để tạo entry và báo lỗi; đừng tự cho rằng `save` sẽ phát sinh DN ngẫu nhiên như cơ chế sinh khóa của cơ sở dữ liệu.

### 3.2. `@DnAttribute` có thể ảnh hưởng danh tính

Trường `uid` trong ví dụ vừa là thuộc tính LDAP vừa tham gia tính DN. Nếu sửa `person.setUid("alice2")` rồi cập nhật, đường dẫn được tính từ `@DnAttribute` có thể khác DN gốc. Một số đường cập nhật ODM có thể thực hiện thao tác di chuyển/tạo lại entry theo cấu hình; đây không nên được xem là thao tác sửa thuộc tính thông thường.

Với nghiệp vụ chỉ muốn sửa `mail`, không đổi `uid`. Với nghiệp vụ đổi RDN hoặc chuyển OU, hãy xây dựng quy trình đổi DN riêng bằng thao tác **ModifyDN/rename**, kiểm tra ảnh hưởng tới thành viên nhóm và các tham chiếu DN ở entry khác.

## 4. Khai báo `LdapRepository<T>` và hợp đồng CRUD

Khi entity có ODM mapping phù hợp, một repository có thể được khai báo:

```java
import org.springframework.data.ldap.repository.LdapRepository;

public interface PersonRepository extends LdapRepository<PersonEntry> {
    // Có thể bổ sung phương thức tìm kiếm theo thuộc tính tại đây.
}
```

`LdapRepository<PersonEntry>` tự quy định kiểu ID là **`javax.naming.Name`**. Với phiên bản Spring Data LDAP hiện hành, nó kế thừa `ListCrudRepository<PersonEntry, Name>` và các phương thức CRUD từ `CrudRepository`.

Cách khai báo cơ bản khác là:

```java
import javax.naming.Name;
import org.springframework.data.repository.CrudRepository;

public interface BasicPersonRepository
        extends CrudRepository<PersonEntry, Name> {
}
```

Nếu muốn sử dụng phương thức đặc thù nhận `LdapQuery`, ưu tiên `LdapRepository<T>` thay cho `CrudRepository<T, Name>`. **Sai kiểu ID** như `CrudRepository<PersonEntry, Long>` là không phù hợp với LDAP ODM.

Có thể kích hoạt scanning repository qua `@EnableLdapRepositories` nếu ứng dụng chưa có cơ chế tự cấu hình phù hợp. Cấu hình `LdapTemplate`/`ContextSource` và địa chỉ LDAP cần hoàn tất trước khi chạy ví dụ; tránh ghi mật khẩu bind trong source code.

### Hợp đồng của từng phương thức

| API | Kiểu/kết quả tiêu biểu | Điều cần hiểu trong LDAP |
| --- | --- | --- |
| `save(entity)` | Trả về entity đã lưu | Chọn đường tạo hoặc cập nhật theo trạng thái entity/ID; không mặc định là UPSERT |
| `saveAll(entities)` | `List<T>` ở các phiên bản `LdapRepository` hiện hành | Nhiều thao tác, không tạo một transaction LDAP nguyên tử cho mọi entry |
| `findById(Name dn)` | `Optional<T>` | Tìm entity với **DN**, không phải `uid` hay `mail` |
| `existsById(Name dn)` | `boolean` | Kiểm tra tồn tại tại thời điểm truy vấn; không khóa entry chống sửa/xóa đồng thời |
| `findAll()` | `List<T>` | Duyệt các entry của loại entity theo mapping/base, có thể tốn tài nguyên |
| `findAllById(Iterable<Name>)` | `List<T>` | Có thể thiếu entry không tìm thấy; thứ tự trả về không được bảo đảm |
| `count()` | `long` | Đếm entry của loại entity mà repository tìm được, không phải số hàng trong bảng SQL |
| `deleteById(Name dn)` | `void` | Xóa theo DN; cần quyền xóa và tuân thủ ràng buộc của directory |
| `delete(entity)` | `void` | Dùng định danh của entity được ánh xạ để xóa |
| `deleteAll()` | `void` | Có thể ảnh hưởng toàn bộ tập entry mà repository quản lý; phải có biện pháp bảo vệ |
| `findOne(LdapQuery)` | `Optional<T>` | Tìm theo filter, có thể lỗi nếu có hơn một entry khớp |
| `findAll(LdapQuery)` | `List<T>` | Tìm theo filter, base và scope đã xác định |

Các phương thức CRUD kế thừa quy tắc tổng quát của **Spring Data Commons**: tham số ID/entity không được `null` nếu API không cho phép, `findById` trả `Optional.empty()` khi không tìm thấy, `findAllById` có thể trả ít phần tử hơn danh sách ID đầu vào, và giá trị trả về của `save` nên được giữ lại để dùng tiếp. Các lỗi kết nối, schema, quyền hoặc thao tác LDAP vẫn có thể được chuyển thành các Spring `DataAccessException` phù hợp; không phải mọi trường hợp thất bại đều trở thành danh sách rỗng hoặc `false`.

> **Lưu ý về `deleteById`:** hợp đồng `CrudRepository` hiện hành cho phép bỏ qua ID không tồn tại. Tuy nhiên, ứng dụng vẫn phải xử lý các lỗi khác như mất kết nối, thiếu quyền hoặc vi phạm chính sách directory; không dùng nó làm cơ chế khẳng định mọi thao tác xóa đều thành công.

### Các bảo đảm không được suy ra từ chữ “CRUD”

`CrudRepository` là **giao diện lập trình**, không biến LDAP thành cơ sở dữ liệu quan hệ. Không được ngầm giả định:

- `save` của LDAP là SQL `INSERT ... ON CONFLICT UPDATE`.
- Tất cả phần tử của `saveAll` cùng commit/rollback như một transaction database.
- Có `@GeneratedValue`, sequence tự tăng hoặc khóa chính số nguyên.
- Một lần đọc rồi cập nhật được cô lập với mọi client khác.
- `findAll()` có sắp xếp/pagination theo `Pageable` như JPA. Tài liệu Spring Data LDAP lưu ý repository LDAP không hỗ trợ paging và sorting theo cách chung của các repository khác; với nhu cầu lớn/đặc thù dùng `LdapTemplate` và control của LDAP server.

## 5. Thao tác CRUD trên một người dùng

Ví dụ service dùng `PersonRepository`, giả định:

- `ContextSource.base = dc=example,dc=org`.
- Parent `ou=people,dc=example,dc=org` đã tồn tại.
- Server chấp nhận schema `inetOrgPerson` với các thuộc tính được ánh xạ.
- Tài khoản bind được cấp đúng quyền đọc/thêm/sửa/xóa.
- Môi trường dùng LDAPS hoặc StartTLS đã được thiết lập và xác minh chứng chỉ server.

### 5.1. Create: tạo entry mới với DN được ODM tính

```java
import org.springframework.stereotype.Service;
import javax.naming.Name;
import javax.naming.ldap.LdapName;
import java.util.Optional;

@Service
public class PeopleService {
    private final PersonRepository repository;

    public PeopleService(PersonRepository repository) {
        this.repository = repository;
    }

    public PersonEntry create(
            String uid, String commonName,
            String surname, String email) {

        PersonEntry person = new PersonEntry();
        person.setUid(uid);
        person.setCommonName(commonName);
        person.setSurname(surname);
        person.setEmail(email);

        // dn == null. @DnAttribute(index = 0) sẽ dùng uid
        // để xác định DN của entry mới dưới ou=people.
        PersonEntry saved = repository.save(person);
        return saved;
    }

    public Optional<PersonEntry> getAlice() throws Exception {
        Name id = new LdapName("uid=alice,ou=people");
        return repository.findById(id);
    }
}
```

Trong ví dụ, `create("alice", "Alice Nguyen", "Nguyen", "alice@example.org")` dự kiến tạo entry có DN đầy đủ `uid=alice,ou=people,dc=example,dc=org`. Nếu entry này đã tồn tại, lệnh tạo mới có thể báo **entryAlreadyExists**; nếu parent chưa tồn tại có thể báo **noSuchObject**; nếu thiếu `sn`, schema có thể từ chối.

**Quan trọng:** đường tạo mới của `save` phụ thuộc cơ chế xác định *new entity*. Với entity thông thường, ID DN `null` là chỉ báo thường dùng để coi entity là mới. Nếu bạn tự gán `dn` khác `null` cho một instance chưa từng được lưu, repository có thể coi đó là entity đã tồn tại và đi theo đường cập nhật. Vì vậy không nên hiểu `save` là “nếu chưa có thì thêm, nếu có rồi thì sửa” trong mọi trường hợp.

Nếu ứng dụng **phải** tạo entry tại một DN được chỉ định rõ, hãy thiết kế đường tạo qua `LdapTemplate.create(...)` cùng ODM phù hợp, hoặc sử dụng một cơ chế xác định trạng thái mới có chủ đích. Đừng chữa lỗi bằng cách gọi `existsById()` rồi quyết định `save`: giữa hai request vẫn có thể có client khác tạo entry trùng DN.

### 5.2. Read: đọc đúng DN và xử lý `Optional`

```java
import org.springframework.ldap.support.LdapNameBuilder;

public PersonEntry requirePerson(String uid) {
    Name relativeDn = LdapNameBuilder.newInstance("ou=people")
            .add("uid", uid)
            .build();

    return repository.findById(relativeDn)
            .orElseThrow(() ->
                new IllegalArgumentException("Không tìm thấy người dùng"));
}
```

`uid` nhập vào được đưa vào **giá trị RDN**, không được nối thẳng thành chuỗi LDAP filter hoặc DN. Phương thức trên kiểm tra một DN cụ thể; nó không phải truy vấn tìm kiếm `(uid=<input>)` trong mọi OU.

`findById` trả `Optional.empty()` khi không có entry phù hợp. Tuy nhiên, nếu server không thể kết nối, chứng chỉ TLS không hợp lệ hoặc tài khoản bind thiếu quyền, phải nhận diện exception tương ứng chứ không được gộp tất cả thành HTTP 404.

Nếu nghiệp vụ chỉ biết `uid` nhưng người dùng có thể nằm ở nhiều nhánh, hãy dùng truy vấn theo thuộc tính với base DN, scope, filter **an toàn** rồi xử lý trường hợp nhiều DN cùng có một `uid`.

### 5.3. Update: giữ nguyên DN, thay đổi thuộc tính

```java
public PersonEntry changeEmail(String uid, String newEmail) {
    PersonEntry person = requirePerson(uid);

    // Không đổi uid vì uid góp phần tạo RDN.
    person.setEmail(newEmail);

    // Entity đã có DN từ lần đọc; cập nhật entry hiện có.
    return repository.save(person);
}
```

Hành vi này gắn với **DN của entity đã đọc**. Nếu entry bị xóa trước khi `save`, cập nhật có thể lỗi thay vì tự tạo lại. Nếu người khác đã sửa cùng thuộc tính trong khoảng giữa `findById` và `save`, có thể xuất hiện *lost update*. Repository CRUD cơ bản không tự đảm bảo khóa lạc quan chuẩn JPA trên mọi LDAP server.

`save` có thể đồng bộ **những thuộc tính đã ánh xạ** của object với dữ liệu server. Đừng dùng một DTO chỉ có `mail` và DN nhưng các thuộc tính bắt buộc/khác đều `null` làm entity đầy đủ để save, vì cách mapping/update có thể gây ra sửa đổi thuộc tính ngoài ý muốn. Cách an toàn là đọc entity hiện tại, thay các thuộc tính mong muốn, xác minh schema và thực hiện cập nhật; khi cần thay **một** giá trị của thuộc tính đa trị, `LdapTemplate.modifyAttributes(...)` với `ADD_ATTRIBUTE`/`REMOVE_ATTRIBUTE` có thể phù hợp hơn.

### 5.4. Delete: xóa entry theo DN

```java
public void removePerson(String uid) {
    Name relativeDn = LdapNameBuilder.newInstance("ou=people")
            .add("uid", uid)
            .build();

    repository.deleteById(relativeDn);
}
```

Xóa một entry LDAP không đồng nghĩa “cascade xóa” mọi nhóm đang tham chiếu DN đó. Với `groupOfNames`, `groupOfUniqueNames` và các schema tương tự, ứng dụng có thể cần quy trình riêng để cập nhật `member`/`uniqueMember` ở **các entry khác**. LDAP server cũng có thể từ chối xóa entry đang có con hoặc bị hạn chế bởi chính sách.

Do đó nên:

1. Xác thực quyền của người yêu cầu xóa và bảo đảm DN thuộc nhánh được phép.
2. Kiểm tra các tham chiếu nhóm và quy tắc nghiệp vụ; không tự cho rằng được phép xóa tùy ý.
3. Chỉ gọi `deleteById` với DN đã xác thực.
4. Đọc/đối soát kết quả khi cần; ghi audit theo chính sách.

Không dùng `deleteAll()` trong tác vụ xử lý một người dùng vì API này có phạm vi rất rộng.

## 6. Đổi `uid`, rename và move là thay đổi danh tính

Giả sử Alice chuyển từ:

```text
uid=alice,ou=people,dc=example,dc=org
```

sang:

```text
uid=alice,ou=contractors,dc=example,dc=org
```

Đây là thay đổi **DN**. Nếu nhóm `cn=reviewers,ou=groups,...` chứa thuộc tính `uniqueMember` với DN cũ, các tham chiếu đó cũng cần được kiểm tra/điều chỉnh theo chính sách server. Một `repository.save(person)` không được mặc định giải quyết trọn vẹn việc cập nhật mọi entry liên quan.

LDAPv3 có thao tác **ModifyDN** để đổi RDN hoặc di chuyển trong cây khi server cho phép. Spring LDAP cung cấp API rename thích hợp:

```java
import javax.naming.Name;
import javax.naming.ldap.LdapName;
import org.springframework.ldap.core.LdapTemplate;

public void moveToContractors(LdapTemplate ldapTemplate) throws Exception {
    Name oldDn = new LdapName("uid=alice,ou=people");
    Name newDn = new LdapName("uid=alice,ou=contractors");

    ldapTemplate.rename(oldDn, newDn);
}
```

Các DN trong ví dụ là tương đối với base `dc=example,dc=org`. Trước khi gọi, cần xác minh OU đích tồn tại, quyền ModifyDN, ràng buộc schema, ảnh hưởng đến các entry tham chiếu và hành vi cụ thể của LDAP server. Với một số cấu hình ODM, việc sửa trường `@DnAttribute` có thể kích hoạt di chuyển/đổi tên trong bước cập nhật, nhưng không nên dựa vào cơ chế đó khi chưa kiểm thử với server/version thực tế.

Không đổi `@Id dn` của entity rồi cho rằng LDAP server sẽ tự hiểu đó là một thao tác rename an toàn. Cần lựa chọn **API rename**, chính sách chuyển nhóm và xử lý lỗi riêng cho nghiệp vụ đổi tên.

## 7. Những điểm dễ nhầm trong hợp đồng CRUD

### 7.1. Có DN chưa chắc có entry

Một object `Name` chỉ là tên hợp lệ; điều đó không chứng minh entry tồn tại. Với `save`, sự khác biệt giữa *new entity* và *existing entity* quyết định đường thực hiện; với `findById`, `existsById`, `deleteById`, kết quả vẫn do server trả về theo tình trạng hiện tại và ACL.

```text
Name id được tạo hợp lệ
       |
       +--> findById(id)      -> Optional<PersonEntry>
       +--> existsById(id)    -> boolean
       +--> deleteById(id)    -> yêu cầu xóa tại DN
       +--> save(entity)      -> nhánh tạo/cập nhật theo trạng thái entity
```

Không dùng kết quả `existsById()` từ vài giây trước như khóa giao dịch. Với cạnh tranh ghi, hai client cùng thấy `false`, cùng tạo DN và một trong hai có thể bị từ chối do trùng DN.

### 7.2. Không đánh đồng `Name` với `String`, UID hay UUID

| Lỗi lập trình | Hậu quả | Cách sửa |
| --- | --- | --- |
| Repository khai báo ID là `Long`/`UUID` | Không khớp định danh ODM của LDAP | Dùng `LdapRepository<T>` hoặc `CrudRepository<T, Name>` |
| Gọi `findById("alice")` | Sai kiểu tham số và sai nghĩa DN | Xây dựng `Name` như `uid=alice,ou=people` |
| Lắp DN bằng nối chuỗi từ input | Sai cú pháp/escape DN hoặc chọn nhánh không mong muốn | Dùng `LdapNameBuilder`/`LdapName` và xác thực OU được phép |
| Dùng `@Id` của Spring Data/JPA | ODM không nhận đúng metadata LDAP | Import `org.springframework.ldap.odm.annotations.Id` |
| Cho `uid` là định danh toàn cục | Trùng UID ở các OU và định danh mơ hồ | Phân biệt search theo thuộc tính với lookup theo DN |
| Đổi `uid` mà không xem xét DN | Có thể làm DN tính được khác DN cũ, tác động đến tham chiếu | Thiết kế rename/move với kiểm thử |
| Đưa DN đầy đủ vào API đang dùng base tương đối | Có thể ghép base hai lần hoặc tìm sai vị trí | Thống nhất quy ước DN theo `ContextSource` |
| Xem `saveAll` là một transaction | Có thể dở dang sau khi một số entry đã được ghi | Thiết kế retry/bù trừ/đối soát theo trạng thái |
| Gọi `findAll` trên cây rất lớn | Tốn bộ nhớ, vượt server size/time limit | Search theo filter/scope, giới hạn kết quả và paging bằng control phù hợp |

### 7.3. `Name` và các giá trị DN tham chiếu trong thuộc tính

Một DN có thể là **giá trị thuộc tính** của entry khác:

```text
dn: cn=reviewers,ou=groups,dc=example,dc=org
objectClass: groupOfUniqueNames
uniqueMember: uid=alice,ou=people,dc=example,dc=org
```

Ở trường hợp này, `Name` của entry nhóm là `cn=reviewers,ou=groups` (nếu base `dc=example,dc=org`); `uniqueMember` là **thuộc tính đa trị chứa DN của thành viên**. Hai khái niệm khác nhau:

- **`@Id Name dn`:** định danh của **chính entry nhóm**.
- **`Set<Name> members` ánh xạ `uniqueMember`:** các DN **tham chiếu** tới entry khác.

Không tự cho rằng xóa/đổi tên Alice sẽ tự cập nhật `uniqueMember` trên mọi server. Một số directory có cơ chế referential integrity riêng, nhưng đó là cấu hình vendor/server, không phải bảo đảm chung từ `CrudRepository`.

## 8. Giới hạn về giao dịch, concurrency và bảo mật

### 8.1. Một thao tác LDAP không tạo transaction nhiều entry

Một request LDAP `Modify` có thể cập nhật nhiều thuộc tính trên **cùng entry** theo quy tắc nguyên tử của giao thức, nhưng `saveAll` hoặc quy trình “sửa người dùng rồi sửa nhóm” gồm nhiều request. Nếu request thứ hai thất bại, request thứ nhất có thể đã được ghi.

Tương tự, thêm mới bằng `save`, rồi thêm DN vào nhóm bằng `modifyAttributes`, là hai thay đổi entry khác nhau. Khi nghiệp vụ yêu cầu nhất quán, phải xác định trạng thái đích, xử lý trạng thái dở dang, kiểm tra lại sau lỗi và dùng cơ chế giao dịch do server thực sự hỗ trợ nếu có.

### 8.2. Ghi đè đồng thời

Với quy trình `findById` → thay đổi `email` → `save`, client khác có thể sửa entry trong khoảng giữa hai bước. Việc chỉ có đúng DN không cung cấp *optimistic locking*. Có thể cần LDAP Assertion Control (RFC 4528), quy tắc phiên bản riêng và chiến lược retry nếu server/client hỗ trợ. Tránh ghi đè thuộc tính đa trị bằng snapshot cũ khi chỉ muốn thêm/xóa một giá trị; cân nhắc `LdapTemplate.modifyAttributes(...)`.

### 8.3. Quyền truy cập và kiểm soát DN

- Kết nối qua **LDAPS hoặc StartTLS** đã xác minh chứng chỉ. Không đưa mật khẩu bind vào source code.
- Chỉ cấp tài khoản bind quyền đọc/ghi cần thiết trên OU tương ứng. ACL có thể cho phép đọc nhưng từ chối sửa/xóa.
- Không cho người dùng nhập DN tùy ý rồi chạy `deleteById` trên toàn directory. Giới hạn nhánh hợp lệ và kiểm tra quyền nghiệp vụ.
- Khi truy vấn theo `uid`, `mail` hay tên, dùng builder/filter escaping của Spring LDAP (`LdapQueryBuilder`, `EqualsFilter`); **escape LDAP filter khác escape DN**.
- Không log toàn bộ entity/thuộc tính nhạy cảm. Cần audit DN, loại thao tác và kết quả theo chính sách bảo mật.
- Nếu directory có nhiều replica, một lần ghi thành công trên node A không đồng nghĩa tìm ngay trên node B sẽ thấy kết quả mới.

## 9. Kiểm thử hợp đồng CRUD với directory thử nghiệm

Kiểm thử bằng LDAP server có schema, quyền và base DN gần giống môi trường thật; không chỉ mock repository.

| Kịch bản | Dữ liệu chuẩn bị | Kỳ vọng cần xác minh |
| --- | --- | --- |
| Tạo mới với `dn == null` | `uid`, `cn`, `sn` hợp lệ, parent OU tồn tại | Entry mới đúng DN; `@Id` được cập nhật nếu ODM tính DN |
| Tạo DN trùng | Đã có `uid=alice,ou=people` | Thao tác tạo được báo lỗi, không sinh entry thứ hai |
| Đọc ID đúng | Gọi `findById(Name)` với DN tương đối | Lấy đúng entity và thuộc tính |
| Đọc ID không tồn tại | DN hợp lệ nhưng không có entry | `Optional.empty()` theo hợp đồng repository |
| Đọc cùng UID tại hai OU | Hai entry khác DN nhưng cùng `uid` | `findById` phân biệt được DN; search có thể trả nhiều entry |
| Sửa `mail` | Đọc entity, thay mail, save | DN giữ nguyên, thuộc tính cập nhật |
| Đổi `@DnAttribute` | Thay giá trị tham gia DN | Quan sát hành vi ODM/LDAP, không giả định chỉ sửa thuộc tính |
| Xóa theo DN | Entry tồn tại với quyền xóa | Entry bị xóa; kiểm tra tham chiếu nhóm |
| Xóa entry thiếu quyền | ACL từ chối xóa | Exception phù hợp, không hiểu là xóa thành công |
| `saveAll` với một entry gây lỗi | Danh sách nhiều entity, lỗi schema/ACL ở phần tử giữa | Không giả định rollback các entry đã xử lý |
| Hai client cập nhật cùng entry | Chạy xen kẽ đọc/sửa/ghi | Phát hiện và xác định chính sách xử lý lost update |
| Base DN sai | Truyền DN đầy đủ vào ContextSource đã có base | Xác minh lỗi và sửa quy ước DN |

Nên kiểm tra **trạng thái thật trong directory sau mỗi thao tác** bằng lookup độc lập hoặc công cụ LDAP (`ldapsearch -s base`) với cùng tài khoản quyền tương ứng. Một test chỉ xác minh `save(...)` không ném exception mà không đọc lại DN/thuộc tính có thể bỏ sót lỗi mapping.

### Bài tập thực hành

Hãy tạo entity `PersonEntry` cho OU `ou=people` và repository `PersonRepository`. Thực hiện lần lượt:

1. Tạo Alice với `dn == null`, `uid=alice`, `cn=Alice Nguyen`, `sn=Nguyen`; quan sát DN sau `save`.
2. Đọc Alice bằng `findById(new LdapName("uid=alice,ou=people"))`.
3. Đổi `mail`, gọi lại `save`, đọc lại để xác nhận **DN không đổi**.
4. Thử tìm DN `uid=alice,ou=contractors`; giải thích vì sao kết quả khác lookup theo `uid` trên nhiều OU.
5. Thử `deleteById` với DN được tạo an toàn; đọc lại để xác minh.
6. Thảo luận điều gì xảy ra nếu Alice đang là thành viên một nhóm mà `uniqueMember` lưu DN cũ.

## 10. Câu hỏi tự kiểm tra

1. Vì sao `uid=alice` không phải lúc nào cũng là định danh duy nhất trong LDAP directory?
2. Vì sao kiểu ID repository phải là `javax.naming.Name`, và loại `@Id` nào phải import?
3. `@Id` và `@DnAttribute` khác nhau thế nào? Trường hợp nào `@DnAttribute(index = 0)` giúp tạo DN?
4. Khi entity mới đã được gán `dn` trước lúc `save`, vì sao không nên mặc định nó sẽ được tạo mới?
5. `findById(Name)` khác phương thức tìm kiếm theo filter `(uid=alice)` như thế nào?
6. Vì sao `saveAll(...)` không có bảo đảm nguyên tử nhiều entry?
7. Khi `uid` góp phần tạo RDN, việc đổi `uid` có thể ảnh hưởng những entry khác ra sao?
8. Vì sao `existsById` không đủ để chống hai client tạo cùng DN một cách đồng thời?
9. Muốn di chuyển một người dùng giữa hai OU, thao tác LDAP nào phù hợp và cần kiểm tra điều gì?
10. Tại sao repository LDAP không tự có hỗ trợ `Pageable`/`Sort` giống một số repository database?

## 11. Tổng kết

**DN là định danh của LDAP entry**, nên **`Name` là kiểu ID của Spring Data LDAP repository**. Khai báo entity bằng `@Entry`, `@Id` của Spring LDAP ODM và các thuộc tính/schema phù hợp; dùng `@DnAttribute` khi cần cấu thành RDN. CRUD repository giúp làm việc với đối tượng Java nhưng vẫn tuân thủ quy tắc LDAP: `save` phụ thuộc trạng thái entity, `findById` và `deleteById` nhận DN, thay đổi DN là rename/move, và nhiều request không tự trở thành một transaction.

Trong triển khai thực tế, hãy thống nhất base DN, xây dựng DN an toàn, kiểm soát quyền, xác minh trạng thái sau thao tác và kiểm thử với directory thật. Những điều này bảo đảm mô hình repository phản ánh đúng **cấu trúc cây LDAP** thay vì vô tình mang giả định của JPA/SQL sang hệ thống thư mục.

### Tài liệu tham khảo

- [Spring Data LDAP Reference — Configuration](https://docs.spring.io/spring-data/ldap/reference/ldap/configuration.html).
- [Spring Data LDAP API — `LdapRepository<T>`](https://docs.spring.io/spring-data/ldap/docs/current/api/org/springframework/data/ldap/repository/LdapRepository.html).
- [Spring Data LDAP API — `SimpleLdapRepository<T>`](https://docs.spring.io/spring-data/ldap/docs/current/api/org/springframework/data/ldap/repository/support/SimpleLdapRepository.html).
- [Spring LDAP Reference — Object-Directory Mapping](https://docs.spring.io/spring-ldap/reference/odm.html).
- [Spring LDAP API — `LdapOperations`](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/core/LdapOperations.html).
- [Spring Data Commons API — `CrudRepository<T, ID>`](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/repository/CrudRepository.html).
- [RFC 4511 — LDAPv3 Protocol](https://www.rfc-editor.org/rfc/rfc4511).
