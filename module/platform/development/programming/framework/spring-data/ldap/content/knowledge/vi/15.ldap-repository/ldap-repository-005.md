# Ngữ nghĩa save khi tạo mới hoặc cập nhật entry

Trong Spring Data LDAP, lời gọi `personRepository.save(person)` trông quen thuộc với lập trình viên từng dùng Spring Data JPA. Nhưng LDAP không có bảng, khóa chính tự tăng hay câu lệnh `INSERT ... ON CONFLICT DO UPDATE`. Mỗi đối tượng được lưu tương ứng với một **entry có Distinguished Name (DN)** trong cây thư mục, còn việc **tạo mới** và **cập nhật** là hai thao tác có điều kiện, ràng buộc và lỗi khác nhau.

Một sai lầm điển hình là tạo đối tượng `PersonEntry` mới, gán sẵn `dn=uid=lan,ou=people` rồi gọi `save`, kỳ vọng repository tự kiểm tra và tạo entry nếu chưa có. Trong cách triển khai repository Spring Data LDAP thông dụng, **DN/`@Id` có giá trị khiến đối tượng thường được xem là đã tồn tại**, nên `save` có thể chọn nhánh cập nhật. Nếu DN chưa tồn tại trên server, thao tác cập nhật sẽ thất bại chứ không tự chuyển thành tạo mới.

Bài **LDAP Repository** này giải thích ngữ nghĩa `save`, metadata ODM (`@Entry`, `@Id`, `@DnAttribute`, `@Attribute`), quá trình tạo/cập nhật entry, tác động của thay đổi DN, và cách kiểm chứng qua `LdapTemplate` cùng directory thực tế. Các ví dụ thuộc module **SPRING_DATA_LDAP**: ánh xạ entry phân cấp sang Java, truy vấn repository/`LdapTemplate`, CRUD, filter an toàn, schema/`objectClass`, bảo mật kết nối và kiểm thử.

## 1. Mục tiêu

Sau bài này, bạn có thể:

1. Giải thích tại sao `save(entity)` **không đồng nghĩa với upsert dựa trên việc entry tồn tại**.
2. Nhận biết cách repository phân loại entity **mới** và **đã có**, thường dựa trên DN `@Id` hoặc `Persistable.isNew()` nếu được hỗ trợ/cấu hình.
3. Tạo entry mới bằng metadata `@DnAttribute` cho phép tính DN khi `@Id` chưa được gán.
4. Đọc entry hiện có, thay đổi attribute và gọi `save` để cập nhật đúng DN.
5. Chọn `LdapTemplate.create/update/modifyAttributes` khi cần diễn đạt ý định create/update hoặc sửa một thuộc tính một cách tường minh.
6. Nhận diện lỗi DN đã tồn tại, DN không tồn tại, schema, ACL, thay đổi RDN, update mất dữ liệu và retry ghi không an toàn.
7. Thiết kế kiểm thử để phân biệt **create**, **update**, **rename** và lỗi sau khi phản hồi LDAP bị mất.

## 2. Nhắc lại: LDAP entry có DN, không có ID tự tăng như bảng

Directory thử nghiệm:

~~~text
dc=example,dc=org
├── ou=people
│   ├── uid=lan
│   └── uid=minh
├── ou=groups
│   └── cn=developers
└── ou=services
    └── cn=app-directory-writer
~~~

Ví dụ entry người dùng:

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
description: Ky su phan mem
~~~

Những thành phần quan trọng:

| Khái niệm | Trong ví dụ | Vai trò đối với `save` |
| --- | --- | --- |
| **DN đầy đủ** | `uid=lan,ou=people,dc=example,dc=org` | Tên duy nhất của entry trong directory. |
| **RDN** | `uid=lan` | Thành phần định danh entry so với cha; có thể đổi khi rename. |
| **Base DN của ContextSource** | `dc=example,dc=org` | Gốc để Spring LDAP diễn giải DN tương đối. |
| **`@Entry.base`** | `ou=people` | Nhánh entity quản lý trong directory. |
| **`@Id`** | Field Java kiểu `javax.naming.Name` | DN của object LDAP, **không phải** ID sequence database. |
| **`@DnAttribute`** | Field `uid` dùng làm RDN | Cho phép ODM suy DN theo cấu trúc đã khai báo. |
| **`objectClass` / schema** | `inetOrgPerson` và lớp kế thừa | Quyết định thuộc tính bắt buộc và hợp lệ khi tạo/sửa. |

Ví dụ `cn` và `sn` thường là thuộc tính bắt buộc theo lớp `person`. Directory có thể từ chối tạo entry nếu thiếu chúng, ngay cả khi Java entity hợp lệ về kiểu dữ liệu.

**DN có thể thay đổi:** khi entry được đổi tên hoặc chuyển sang OU khác, DN mới không giống DN cũ. Vì vậy đừng dùng DN như định danh nhân sự bất biến trong database nghiệp vụ lâu dài nếu cần đồng bộ tài khoản giữa các hệ thống; dùng một định danh ổn định do nguồn phù hợp cung cấp và bảng ánh xạ khi có yêu cầu đó.

## 3. Trọng tâm: `save` quyết định tạo hay cập nhật như thế nào?

Trong một repository Spring Data LDAP thông dụng (ví dụ `SimpleLdapRepository`), `save` dựa trên việc entity được xem là **mới** hay **đã tồn tại**. Theo hành vi mặc định phổ biến:

- Entity **không triển khai `Persistable`**: DN khai báo qua `@Id` bằng `null` thường được hiểu là entity mới; `@Id` đã có DN thường được hiểu là entity hiện có.
- Entity **triển khai `Persistable`**: cơ chế phân loại có thể dựa vào `isNew()` của chính entity, thay vì chỉ nhìn DN. Phải quản lý trạng thái `isNew` chính xác trong vòng đời tạo, đọc và cập nhật.
- Repository chọn luồng ODM **create** hoặc **update** tương ứng. Đây không phải một truy vấn bảo đảm `existsById` được thực hiện trước mọi lần `save`.

Sơ đồ quyết định khái niệm:

~~~mermaid
flowchart TD
    A["repository.save(entity)"] --> B{"Entity được xem là mới?"}
    B -- "Có" --> C["ODM create"]
    B -- "Không" --> D["ODM update"]
    C --> E{"DN đích đã tồn tại?"}
    E -- "Có" --> F["Lỗi: entry đã tồn tại"]
    E -- "Không" --> G["Server kiểm tra cha, ACL, schema"]
    D --> H{"Entry đích có tồn tại?"}
    H -- "Không" --> I["Lỗi: không tìm thấy entry"]
    H -- "Có" --> J["Đọc/so sánh dữ liệu và cập nhật"]
    G --> K["Tạo entry nếu hợp lệ"]
    J --> L["Ghi các thay đổi nếu hợp lệ"]
~~~

Sơ đồ này minh họa **nhánh tạo/cập nhật**, không cam kết mọi phiên bản thư viện đều dùng cùng các lớp nội bộ hoặc cùng thứ tự lời gọi. Khi dự án nâng cấp Spring Data LDAP/Spring LDAP, hãy xác nhận API và hành vi bằng integration test.

### Bảng các tình huống dễ nhầm

| Đối tượng Java | Entry trên server | Nhánh thường được chọn | Kết quả thường gặp |
| --- | --- | --- | --- |
| `@Id == null`, có đủ `@DnAttribute` để suy DN | Chưa tồn tại | **Create** | Tạo entry; ODM có thể gán DN mới vào object. |
| `@Id == null`, DN tính ra trùng entry cũ | Đã tồn tại | **Create** | Server từ chối tạo trùng DN; không tự merge. |
| `@Id != null`, DN đó tồn tại | Đã tồn tại | **Update** | Cập nhật entry theo metadata ODM và ACL. |
| `@Id != null`, DN đó chưa tồn tại | Không tồn tại | **Update** | Lỗi không tìm thấy DN; không tự tạo mới. |
| `@Id == null`, không thể tính DN | Không liên quan | **Create** nhưng thiếu tên đích | Lỗi xác định DN trước/ở bước tạo. |
| Entity tự khai báo `Persistable.isNew()` | Tùy trạng thái do code quản lý | Theo cờ new/existing | Phải kiểm thử cờ và đảm bảo nó được cập nhật sau khi tạo/đọc. |

**Kết luận quan trọng:** `save` là API lưu entity theo trạng thái mới/cũ mà repository nhận biết; không có cam kết tự động “nếu DN chưa có thì insert, nếu đã có thì update” theo cách upsert tại database.

## 4. Cấu hình môi trường Spring Boot

Dependency Gradle Kotlin DSL:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-ldap")
}
~~~

`application.yml`:

~~~yaml
spring:
  ldap:
    urls: ${LDAP_URL:ldaps://ldap.example.org:636}
    base: ${LDAP_BASE_DN:dc=example,dc=org}
    username: ${LDAP_BIND_DN}
    password: ${LDAP_BIND_PASSWORD}
~~~

Ví dụ danh tính bind trong **directory thử nghiệm** là `cn=app-directory-writer,ou=services,dc=example,dc=org`. Tài khoản này cần quyền phù hợp để tạo hoặc cập nhật entry trong `ou=people`. Để triển khai an toàn, phân tách tài khoản chỉ đọc và tài khoản ghi khi có thể; không dùng tài khoản quản trị directory cho mọi request.

Với `spring.ldap.base=dc=example,dc=org`, DN tương đối của Lan là `uid=lan,ou=people`. Tránh tạo DN thành `uid=lan,ou=people,dc=example,dc=org` rồi lại ghép thêm context base bằng cách thủ công.

Spring Boot có thể tự cấu hình `LdapContextSource`, `LdapTemplate` và cơ sở cho repository khi starter/cấu hình phù hợp. Nếu ứng dụng có nhiều `ContextSource` hoặc custom bean, cần wiring và repository scanning đúng nguồn, không suy rằng mọi repository đều tự dùng tài khoản mong muốn.

## 5. Xây entity ODM đủ thông tin để tính DN

Một cách tự nhiên để tạo entry bằng `repository.save` là **để `@Id` chưa có giá trị**, nhưng khai báo cách tính DN từ các thuộc tính cấu thành tên.

~~~java
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

    @Attribute(name = "description")
    private String description;

    public PersonEntry() {}

    public PersonEntry(
            String uid, String commonName, String surname, String email) {
        this.uid = uid;
        this.commonName = commonName;
        this.surname = surname;
        this.email = email;
    }

    public Name getDn() { return dn; }
    public void setDn(Name dn) { this.dn = dn; }
    public String getUid() { return uid; }
    public void setUid(String uid) { this.uid = uid; }
    public String getCommonName() { return commonName; }
    public void setCommonName(String name) { this.commonName = name; }
    public String getSurname() { return surname; }
    public void setSurname(String name) { this.surname = name; }
    public String getEmail() { return email; }
    public void setEmail(String email) { this.email = email; }
    public String getDescription() { return description; }
    public void setDescription(String description) {
        this.description = description;
    }
}
~~~

Các điểm thiết kế:

1. `@Entry` khai báo nhánh entity và các lớp schema cần thiết; nó **không tạo schema trên server**.
2. `@Id Name dn` biểu diễn DN. Với entity mới, trường này được để `null` để repository nhận diện nhánh tạo theo hành vi mặc định.
3. `@DnAttribute(value = "uid", index = 0)` chỉ ra thành phần DN từ `uid`. Với một RDN động trước `@Entry.base="ou=people"`, index `0` là thành phần duy nhất cần suy; **index trở nên quan trọng khi có nhiều RDN động**.
4. `@Attribute(name = "uid")` bảo đảm field `uid` cũng được ánh xạ thành thuộc tính LDAP, không chỉ là dữ liệu dùng đặt tên.
5. `cn` và `sn` có mặt vì schema `person` cần các thuộc tính đó. Các field khác phải phù hợp schema thật, không tự giả định mọi directory sử dụng cùng objectClass.

**Về `@DnAttribute`:** annotation có thể đọc thành phần tên từ DN. Khi muốn ODM **tự tính DN** cho create/update, cần cấu hình `index` đầy đủ và đúng thứ tự đối với các thành phần DN động. Không suy ra DN tự được tính chỉ vì entity có `@Attribute(name="uid")`.

## 6. Repository và luồng tạo entry mới

Khai báo repository:

~~~java
import java.util.Optional;
import org.springframework.data.ldap.repository.LdapRepository;

public interface PersonRepository extends LdapRepository<PersonEntry> {
    Optional<PersonEntry> findByUid(String uid);
}
~~~

Service tạo entry:

~~~java
import org.springframework.stereotype.Service;

@Service
public class PersonRegistrationService {
    private final PersonRepository repository;

    public PersonRegistrationService(PersonRepository repository) {
        this.repository = repository;
    }

    public PersonEntry createPerson(
            String uid, String commonName, String surname, String email) {
        if (uid == null || !uid.matches("[a-zA-Z0-9._-]{1,64}")) {
            throw new IllegalArgumentException("uid khong hop le");
        }
        if (commonName == null || commonName.isBlank()
                || surname == null || surname.isBlank()) {
            throw new IllegalArgumentException(
                    "cn va sn la truong bat buoc");
        }

        PersonEntry person = new PersonEntry(
                uid, commonName, surname, email);

        // person.getDn() == null: repository xem entity là mới.
        // @DnAttribute(index=0) + @Entry(base="ou=people")
        // cung cấp thông tin để ODM tính DN cần tạo.
        return repository.save(person);
    }
}
~~~

Với `uid=mai` và context base `dc=example,dc=org`, DN mong đợi sau khi tạo là:

~~~text
uid=mai,ou=people,dc=example,dc=org
~~~

**Điều kiện để tạo thành công:**

- Entry cha `ou=people,dc=example,dc=org` đã tồn tại.
- DN `uid=mai,...` **chưa có** trong directory.
- Entity thỏa các `objectClass` và thuộc tính bắt buộc theo schema.
- Tài khoản kết nối có ACL cho **add** entry trong nhánh đó.
- Kết nối TLS và bind hợp lệ; thao tác không gặp lỗi mạng/server.

Sau khi `save` thành công, ODM có thể gán DN tính được vào trường `@Id` của đối tượng. Đừng suy rằng server sinh ra một số thứ tự như database; tên entry được hình thành từ quy tắc DN/ODM.

### Nếu `uid=mai` đã tồn tại thì sao?

Ở luồng **create**, server có thể trả LDAP result code **68** (`entryAlreadyExists`). `save` không có nhiệm vụ tìm entry Mai rồi hợp nhất mọi trường từ object mới. Đây là tình huống cần xử lý theo nghiệp vụ:

- Nếu “đăng ký mới”, trả lỗi trùng định danh và yêu cầu người dùng chọn tên khác.
- Nếu “cập nhật người dùng đã có”, tìm entry thật rồi đi qua luồng **update** có phân quyền.
- Nếu API có yêu cầu “create or update”, xây chính sách upsert rõ ràng và xử lý race; đừng dùng một lời gọi `save` mù quáng để thay thế quyết định đó.

**Không coi `existsById` trước khi tạo là khóa chống trùng tuyệt đối:** giữa hai request kiểm tra và tạo, worker khác có thể đã tạo cùng DN. Directory vẫn cần từ chối duplicate, và application phải xử lý lỗi này.

## 7. Luồng cập nhật: đọc entry đang tồn tại rồi save

Để thay đổi mô tả của Lan:

~~~java
import org.springframework.stereotype.Service;

@Service
public class PersonProfileService {
    private final PersonRepository repository;

    public PersonProfileService(PersonRepository repository) {
        this.repository = repository;
    }

    public PersonEntry changeDescription(String uid, String description) {
        PersonEntry person = repository.findByUid(uid)
                .orElseThrow(() ->
                        new IllegalArgumentException(
                                "Khong tim thay tai khoan"));

        // Entity vừa đọc có DN qua @Id nên đi theo luồng update.
        person.setDescription(description);
        return repository.save(person);
    }
}
~~~

Luồng ý nghĩa:

~~~mermaid
sequenceDiagram
    participant API as Service
    participant Repo as LdapRepository
    participant ODM as Spring LDAP ODM
    participant Dir as LDAP server
    API->>Repo: findByUid("lan")
    Repo->>Dir: Search theo uid + base/schema
    Dir-->>Repo: DN + attributes
    Repo-->>API: PersonEntry có @Id
    API->>API: setDescription(newValue)
    API->>Repo: save(person)
    Repo->>ODM: update(entity hiện có)
    ODM->>Dir: Đọc trạng thái / tính thay đổi
    ODM->>Dir: Modify những attribute phù hợp
    Dir-->>API: Hoàn thành hoặc báo lỗi
~~~

Các lời gọi cụ thể có thể khác theo phiên bản Spring LDAP và ODM; sơ đồ nhấn mạnh **phân loại entity đã có DN** và **cập nhật dữ liệu trên cùng entry**.

### Không nên tạo “partial entity” rồi save để sửa một trường

Đây là lỗi nguy hiểm:

~~~java
// KHÔNG KHUYẾN NGHỊ: cố cập nhật bằng entity chỉ có DN và description.
PersonEntry partial = new PersonEntry();
partial.setDn(existingDn);
partial.setDescription("Da chuyen bo phan");
repository.save(partial);
~~~

Vì ODM ánh xạ **các field của entity** và có thể tính chênh lệch với entry thực, những field còn `null`/rỗng có thể bị diễn giải là xóa hoặc thay thế thuộc tính đang có tùy mapping/phiên bản. Rủi ro là mất `cn`, `sn`, `mail`, vi phạm schema hoặc thay đổi ngoài mong muốn.

**Cách an toàn hơn:** đọc entity có đủ các thuộc tính được quản lý, sửa trường cần thiết rồi lưu. Với yêu cầu chỉ thay đổi đúng **một** thuộc tính theo DN, dùng `LdapTemplate.modifyAttributes` (mục 10), nhất là khi entity có trường nhạy cảm hoặc nhiều attribute không được phép sửa.

Không đánh đồng việc đọc rồi lưu với **optimistic locking bảo đảm**: người khác có thể sửa entry giữa hai lần đọc/ghi.

## 8. Đã gán `@Id` nhưng entry chưa tồn tại: tại sao save thất bại?

Xét đoạn code:

~~~java
import javax.naming.Name;
import org.springframework.ldap.support.LdapNameBuilder;

PersonEntry person = new PersonEntry(
        "mai", "Mai Le", "Le", "mai@example.org");

Name dn = LdapNameBuilder.newInstance("ou=people")
        .add("uid", "mai")
        .build();
person.setDn(dn);

// Với repository mặc định, có @Id trước khi save
// thường khiến entity được phân loại là đã tồn tại.
repository.save(person);
~~~

Nếu DN `uid=mai,ou=people` **chưa tồn tại**, repository có thể chọn nhánh **update** và gặp lỗi `noSuchObject` (thường là LDAP result code **32**). Không được chữa bằng cách “đặt DN thành chuỗi khác ngẫu nhiên” hoặc coi `save` luôn tạo mới.

### Muốn tạo entry có DN biết trước

Khi nghiệp vụ đã tính DN và muốn **nói rõ đây là thao tác create**, có thể dùng ODM trực tiếp:

~~~java
import javax.naming.Name;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

public PersonEntry createWithExplicitDn(
        LdapTemplate ldapTemplate) {
    PersonEntry person = new PersonEntry(
            "mai", "Mai Le", "Le", "mai@example.org");

    Name dn = LdapNameBuilder.newInstance("ou=people")
            .add("uid", "mai")
            .build();
    person.setDn(dn);

    // Diễn đạt rõ CREATE, không dựa vào suy luận new/existing của save.
    ldapTemplate.create(person);
    return person;
}
~~~

`LdapTemplate.create(Object)` sử dụng metadata ODM, cố tạo entry theo DN, và không phải một upsert. Nếu entry đã tồn tại, server từ chối trùng. Đối với **update tường minh**, Spring LDAP cũng cung cấp `ldapTemplate.update(person)` để cập nhật entry có thật.

### Nâng cao: `Persistable` để điều khiển trạng thái mới

Spring Data cung cấp interface `org.springframework.data.domain.Persistable<ID>` với `getId()` và `isNew()`. Một entity có thể dùng cơ chế này khi DN được gán trước nhưng vẫn cần repository coi nó là **mới**:

~~~java
// Ý tưởng, không phải một entity hoàn chỉnh để copy thẳng vào production:
// implements Persistable<Name>:
//
// @Override public Name getId() { return dn; }
// @Override public boolean isNew() { return newEntry; }
//
// @Transient (annotation LDAP ODM) private boolean newEntry;
~~~

Cần đánh dấu `newEntry=false` **đúng thời điểm sau khi create thành công và khi entity được đọc lại**, nếu không một entity đã tồn tại có thể vẫn bị xem là mới và `save` cố tạo trùng. Không dùng `isNew()` luôn trả `true` làm mẹo vượt qua lỗi DN. Nếu thiết kế yêu cầu lifecycle phức tạp, cân nhắc ưu tiên gọi `create`/`update` tường minh ở tầng service để giảm trạng thái ẩn.

## 9. Thay đổi `uid`, RDN hay OU không đơn giản là cập nhật thuộc tính

Vì `uid` trong entity minh họa có `@DnAttribute(index = 0)`, nó tham gia **tính DN**. Giả sử Lan đổi username từ `lan` sang `lan.nguyen`.

~~~text
Trước:
uid=lan,ou=people,dc=example,dc=org

Sau:
uid=lan.nguyen,ou=people,dc=example,dc=org
~~~

Đây là **thay đổi DN/RDN**, không chỉ là một phép `REPLACE_ATTRIBUTE` trên `uid`. Spring LDAP ODM có cơ chế xử lý DN được tính từ các trường `@DnAttribute`, và trong một số đường cập nhật có thể thực hiện thao tác di chuyển/tạo lại entry khi DN tính mới khác DN cũ. Hành vi chính xác cần được kiểm thử theo phiên bản, không nên coi mọi lần `save` thay `uid` là một LDAP Modify DN nguyên tử.

Rủi ro khi đổi DN:

- Nhóm dùng `member`/`uniqueMember` có thể lưu **DN thành viên cũ** và cần cơ chế cập nhật tham chiếu.
- Directory có thể hạn chế rename/move hoặc cấp ACL khác nhau theo nhánh đích.
- Entry có operational attributes/ID nội tại cần được giữ ổn định; thao tác xóa/tạo lại có thể thay đổi danh tính entry.
- Ứng dụng khác có thể cache DN hoặc ánh xạ dữ liệu nghiệp vụ theo DN.
- Một luồng cập nhật có thể gặp lỗi giữa chừng và không có transaction đa entry.

**Khuyến nghị:** nếu sản phẩm cần rename/move, thiết kế thành chức năng riêng, dùng API như `LdapTemplate.rename(oldDn, newDn)` khi thích hợp và xác minh hành vi của directory, schema, ACL và các liên kết nhóm. Không cho HTTP client tự sửa `@DnAttribute` qua một DTO cập nhật hồ sơ thông thường.

## 10. `save` so với các thao tác tường minh của `LdapTemplate`

| Nhu cầu | API | Đặc tính |
| --- | --- | --- |
| Entity mới, DN có thể tính tự động theo ODM. | `repository.save(newEntity)` | Phụ thuộc quy tắc new/existing. |
| Entity đã đọc, sửa một số field ánh xạ. | `repository.save(existingEntity)` | Dùng ODM và metadata entity để cập nhật. |
| Bắt buộc thao tác tạo, DN đã xác định. | `ldapTemplate.create(entry)` | Nói rõ ý định tạo; server từ chối nếu trùng. |
| Bắt buộc thao tác update entity. | `ldapTemplate.update(entry)` | Nói rõ ý định cập nhật; entry phải tồn tại. |
| Chỉ thay một thuộc tính theo DN. | `ldapTemplate.modifyAttributes(dn, changes)` | Nêu rõ ADD/REPLACE/REMOVE. |
| Đổi RDN hoặc di chuyển entry. | `ldapTemplate.rename(oldDn, newDn)` | Đổi tên thay vì coi DN là một field tùy ý. |

Ví dụ cập nhật **chỉ `description`**:

~~~java
import javax.naming.Name;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;
import org.springframework.ldap.core.LdapTemplate;

public void updateDescriptionAtDn(
        LdapTemplate ldapTemplate, Name relativeDn, String newValue) {
    ModificationItem change = new ModificationItem(
            DirContext.REPLACE_ATTRIBUTE,
            new BasicAttribute("description", newValue));

    ldapTemplate.modifyAttributes(
            relativeDn, new ModificationItem[] {change});
}
~~~

Trong thực tế, service phải validate `newValue`, xác minh người gọi được phép sửa và bảo đảm `relativeDn` được xác định từ nguồn đáng tin cậy, không nhận DN tùy ý để sửa entry ngoài vùng quản lý.

**Với attribute nhiều giá trị:** `REPLACE_ATTRIBUTE` có thể thay toàn bộ tập giá trị. Nếu chỉ thêm/xóa một số điện thoại hoặc một DN thành viên nhóm, dùng `ADD_ATTRIBUTE`/`REMOVE_ATTRIBUTE` với giá trị cụ thể, đồng thời kiểm tra schema và lỗi giá trị đã có/chưa có.

## 11. Không nhầm save với transaction, merge và optimistic locking

### 11.1. Một request LDAP không tương đương transaction database

LDAP Modify trên **một entry** có ngữ nghĩa áp dụng các thay đổi trong request theo thứ tự và nguyên tử. Tuy nhiên, một quy trình tạo `PersonEntry`, thêm thành viên vào nhóm và ghi audit vào PostgreSQL có thể chứa **nhiều request và nhiều hệ thống**.

~~~text
1. repository.save(person)         -> ghi entry người dùng vào LDAP
2. ldapTemplate.modifyAttributes() -> thêm thành viên vào nhóm LDAP
3. auditRepository.save(...)       -> ghi audit vào RDBMS
~~~

Không mặc định `@Transactional` trên một service sẽ rollback cả ba thao tác khi bước 3 thất bại. Cần cơ chế transaction/compensation/outbox/saga hoặc đối soát tùy tính năng directory và thiết kế hệ thống. `saveAll` cũng **không nên được xem là một transaction LDAP đa entry nguyên tử**.

### 11.2. Đọc rồi ghi có khoảng đua

Hai admin cùng đọc entry Lan với `description=A`. Admin 1 cập nhật B, sau đó admin 2 cập nhật C từ bản đọc cũ. Nếu không có điều kiện đồng thời, cập nhật sau có thể ghi đè cập nhật trước.

`save` của LDAP repository không tự mang cùng optimistic locking semantics như một entity JPA có `@Version` trong RDBMS. Nếu cần kiểm soát tranh chấp, phải thiết kế một cơ chế phù hợp với server/provider, ví dụ **LDAP Assertion Control (RFC 4528)** hoặc một luồng cập nhật có điều kiện được triển khai/kiểm thử rõ ràng. Kiểm tra trước ở client rồi ghi riêng **không loại bỏ hoàn toàn race condition**.

### 11.3. Mất phản hồi sau khi server ghi

Nếu socket ngắt sau khi gửi create, server có thể đã tạo entry nhưng client nhận lỗi timeout. Retry `save(newEntity)` có thể gặp duplicate DN. Tương tự, sau update, một request gửi lại có thể ghi đè dữ liệu vừa được người khác sửa.

Khi kết quả ghi **không xác định**, đọc lại trạng thái trên nguồn có thẩm quyền theo DN hoặc stable ID phù hợp, đối chiếu các attribute cần thiết rồi quyết định có retry hay không. Với nhiều LDAP endpoint, cân nhắc độ trễ replication trước khi kết luận entry chưa tồn tại.

### 11.4. Upsert thực sự là yêu cầu nghiệp vụ riêng

Nếu API có `createOrUpdate(uid, data)`, quy trình cần tự định nghĩa:

1. Xác định **định danh đáng tin cậy** và phạm vi tìm kiếm, không chỉ tìm trùng email.
2. Quyết định caller được phép **create**, **update** hay cả hai.
3. Nếu entry tồn tại, đọc phiên bản hiện tại và áp dụng những field được phép cập nhật.
4. Nếu chưa tồn tại, tạo mới với DN/schema hợp lệ.
5. Xử lý tranh chấp create giữa nhiều worker, lỗi kết nối và tình huống DN đổi giữa search và write.

Đây không phải cam kết tự động của `repository.save`; LDAP server vẫn là nơi quyết định entry có tồn tại, ACL và schema có cho phép thao tác hay không.

## 12. Bảo mật khi tạo hoặc cập nhật entry

### 12.1. Kiểm tra quyền ở hai lớp

~~~mermaid
flowchart LR
    A["HTTP caller"] --> B["Spring Security<br/>authentication + authorization"]
    B --> C["Service<br/>allowlist thuộc tính + validation"]
    C --> D["LdapRepository / LdapTemplate"]
    D --> E["LdapContextSource<br/>bind account"]
    E --> F["LDAP server<br/>ACL + schema"]
~~~

Việc repository có phương thức `save` **không cấp quyền ghi cho người dùng HTTP**. Cần Spring Security hoặc cơ chế tương đương để xác nhận caller được phép tạo/sửa entry cụ thể, đồng thời directory phải cấp ACL phù hợp cho bind account.

Những nguyên tắc tối thiểu:

- Dùng **LDAPS hoặc StartTLS** được cấu hình chính xác, xác minh hostname/CA. Không truyền credential trên LDAP không mã hóa.
- Giữ bind password trong secret manager/biến môi trường; không commit secret hoặc log mật khẩu.
- Giới hạn **write ACL** theo OU/attribute; tách tài khoản đọc/ghi nếu phù hợp.
- Dùng allowlist DTO để client không tùy ý sửa `objectClass`, attribute nhóm, mật khẩu hoặc operational attributes như `entryUUID`.
- Dùng `LdapQueryBuilder` để escape giá trị search filter; `LdapNameBuilder` để xử lý RDN/DN động. Escape DN và escape filter là **hai quy tắc khác nhau**.
- Không mặc định một username hay email là duy nhất trong mọi directory; kiểm tra search base/schema/nguồn định danh.
- Ghi audit cho hoạt động quản trị, nhưng không log toàn bộ thông tin cá nhân hoặc các thuộc tính bảo mật.

### 12.2. Không trao quyền tạo và sửa tùy ý qua một endpoint

Ví dụ endpoint cập nhật hồ sơ chỉ cho phép sửa `description`; hãy gọi `modifyAttributes` với tên attribute cố định. Không deserialize JSON trực tiếp vào toàn bộ `PersonEntry` rồi `save` mà không kiểm tra các field được phép thay đổi; điều này có thể cho phép caller sửa `uid`, DN, objectClass hoặc các attribute không được dự kiến.

Trong nghiệp vụ có khả năng thay đổi nhóm hoặc trạng thái tài khoản, tách chức năng có đặc quyền cao, dùng quyền riêng và cơ chế phê duyệt/audit thích hợp.

## 13. Kiểm thử ngữ nghĩa create/update với directory thật

Để biết code dùng đúng nhánh `save`, cần kiểm chứng với directory thử nghiệm có ACL ghi và schema đúng. Unit test mock repository chỉ xác nhận service gọi `save`; nó **không chứng minh server đã thực hiện LDAP Add hay Modify**.

### 13.1. Kiểm tra entry trước/sau

Truy vấn một entry trong môi trường thử nghiệm bằng `ldapsearch`:

~~~bash
ldapsearch -LLL -x \
  -H "ldaps://ldap.example.org:636" \
  -D "cn=app-directory-writer,ou=services,dc=example,dc=org" -W \
  -b "ou=people,dc=example,dc=org" -s sub \
  "(uid=mai)" dn uid cn sn mail description
~~~

`-W` yêu cầu nhập password tương tác, không đặt secret trực tiếp vào command-line. Nếu chưa có entry Mai, chạy `createPerson(...)` rồi lặp lại truy vấn. Sau khi tạo thành công, sửa `description` bằng `changeDescription(...)` và đối chiếu **DN vẫn đúng**, thuộc tính vừa sửa thay đổi, các thuộc tính khác không bị mất.

### 13.2. Ma trận test trọng tâm

| Kịch bản | Bước kiểm thử | Kỳ vọng |
| --- | --- | --- |
| Entity mới, `@Id=null`, `@DnAttribute` hợp lệ. | `repository.save(newEntity)`. | Tạo entry; DN được suy và xác minh trên server. |
| Tạo khi DN đã tồn tại. | Lặp create sau khi entry đã có. | Có lỗi duplicate (thường code 68); không âm thầm update. |
| Gán `@Id` thủ công cho DN chưa có. | `repository.save(entityWithDn)`. | Luồng update có thể trả noSuchObject (thường code 32). |
| Đọc entry rồi sửa `description`. | `findByUid` → mutate → `save`. | Entry hiện có được cập nhật, DN giữ nguyên. |
| Đối tượng partial chỉ có DN/description. | Thử **chỉ trên dữ liệu thử nghiệm**. | Phát hiện nguy cơ làm mất thuộc tính hoặc lỗi schema; không dùng production. |
| Thiếu `cn`/`sn` khi tạo. | Tạo entry không đủ thuộc tính bắt buộc. | Server từ chối theo schema. |
| Ghi bằng tài khoản read-only. | Gọi create/update. | Server từ chối theo ACL (thường code 50). |
| Đổi `uid` làm thay đổi RDN. | Thay giá trị `@DnAttribute` trên entry test. | Quan sát đúng DN mới, tác động tham chiếu; không coi là update field đơn thuần. |
| Hai worker cùng tạo một DN. | Chạy create cạnh tranh trên test data. | Không được có hai entry cùng DN; xử lý duplicate/race. |
| Timeout sau khi gửi write. | Mô phỏng ngắt mạng có kiểm soát. | Phải đối soát trước retry; không giả định chưa ghi. |
| `saveAll` có một entry lỗi. | Thực thi batch trên directory test. | Không mặc định các entry đã ghi trước đó được rollback. |

### 13.3. Xác minh qua LDIF

Một entry vừa tạo có thể trông như:

~~~ldif
dn: uid=mai,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: mai
cn: Mai Le
sn: Le
mail: mai@example.org
~~~

Một phép sửa mô tả tường minh có thể biểu diễn bằng LDIF:

~~~ldif
dn: uid=mai,ou=people,dc=example,dc=org
changetype: modify
replace: description
description: Phu trach tich hop
~~~

Đây là các mẫu để hiểu **dữ liệu directory** và **thao tác LDAP**, không phải lệnh được `repository.save` ghi ra nguyên văn. Khi kiểm thử, chỉ thao tác trên OU dữ liệu test và có quy trình làm sạch/khôi phục phù hợp.

## 14. Bảng chẩn đoán lỗi thường gặp

| Hiện tượng | Nguyên nhân cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| Code **32** (`noSuchObject`) khi gọi `save` lần đầu. | Entity có `@Id` nên đi nhánh update nhưng DN chưa tồn tại; hoặc DN/base sai. | Kiểm tra newness, `@Id`, `@DnAttribute` và context base. |
| Code **68** (`entryAlreadyExists`) khi `save`. | Luồng create được chọn cho DN đã tồn tại. | Xử lý duplicate theo nghiệp vụ; không tự hợp nhất. |
| Code **65** (`objectClassViolation`). | Thiếu `cn`/`sn`, objectClass/attribute không khớp schema. | Kiểm tra annotation và schema directory. |
| Code **50** (`insufficientAccessRights`). | Bind account thiếu quyền create/update trên nhánh/thuộc tính. | Sửa ACL theo nguyên tắc ít quyền, không dùng tài khoản admin tùy tiện. |
| Code **19** (`constraintViolation`). | Giá trị/kiểu hoặc ràng buộc của attribute không phù hợp. | Kiểm tra matching rule và schema cụ thể. |
| DN sau save không như dự kiến. | `@DnAttribute.index`, `@Entry.base` hoặc `spring.ldap.base` sai. | Đối chiếu DN tương đối với DN đầy đủ, viết test DN. |
| `uid` đổi làm entry biến mất ở DN cũ. | RDN/DN thay đổi; có thể đã di chuyển/tạo lại. | Thiết kế rename riêng, kiểm tra ổn định identity và tham chiếu nhóm. |
| Field khác bị mất sau update. | Sử dụng partial entity, mapping null hoặc mapper/ODM không đúng schema. | Read–modify–save đúng cách hoặc `modifyAttributes` theo attribute. |
| `SSLHandshakeException` / timeout. | TLS, truststore, mạng hoặc lỗi khi đang ghi. | Xác minh CA/hostname, phân biệt lỗi trước và sau khi gửi write. |
| `save` thành công nhưng HTTP 403. | Lớp Spring Security đang từ chối request khác hoặc log/service bị gọi sai luồng. | Phân tách xác thực/phân quyền HTTP với LDAP ACL và kiểm tra đường gọi. |

Mã lỗi LDAP có thể được Spring dịch thành những `DataAccessException` khác nhau tùy ngữ cảnh/phiên bản. Không lộ raw DN nội bộ, credential hoặc stack trace cho HTTP client; log thông tin chẩn đoán có giới hạn và kiểm soát PII.

## 15. Bài tập tình huống

Directory thử nghiệm có base `dc=company,dc=internal`, nhánh `ou=employees` và entry:

~~~ldif
dn: uid=mai,ou=employees,dc=company,dc=internal
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: mai
cn: Mai Le
sn: Le
mail: mai@company.internal
description: Nhan vien
~~~

Trong Java có `@Entry(base="ou=employees", objectClasses={...})`, `@Id Name dn` và `@DnAttribute(value="uid",index=0)` trên field `uid`.

**Yêu cầu:**

1. Một object mới `uid=an` có `dn=null`, đủ `cn`/`sn`. `repository.save` thường chọn nhánh nào? DN dự kiến là gì?
2. Object `uid=an` đã được gán DN `uid=an,ou=employees` nhưng entry chưa có. Vì sao `save` có thể báo lỗi thay vì tạo?
3. Có thể dùng API nào để nói rõ “tạo entry với DN đã xác định”, không dựa vào newness của repository?
4. Để đổi `description` của Mai mà không thay đổi field khác, hãy trình bày hai cách: **read–modify–save** và **`modifyAttributes`**.
5. Nếu tạo object mới chỉ có `dn` và `description` rồi gọi `save`, nguy cơ của việc ánh xạ các trường còn `null` là gì?
6. Giải thích cách thay đổi `uid` có thể làm thay đổi DN/RDN, và vì sao không nên coi đó là sửa một chuỗi thông thường.
7. Nếu hai worker cùng tạo entry `uid=an`, kiểm tra tồn tại trước bằng `existsById` có đủ ngăn race không?
8. Vì sao không thể coi `saveAll` là transaction đa entry và không được retry mù quáng sau timeout?
9. Nếu người gọi HTTP không có quyền `DIRECTORY_WRITE` nhưng bind account có ACL ghi, API phải làm gì?

**Gợi ý đáp án:**

- (1) Nhánh create, DN đầy đủ dự kiến `uid=an,ou=employees,dc=company,dc=internal` khi mapping, parent và schema hợp lệ.
- (2) `@Id` khác null thường khiến repository coi entity đã tồn tại, đi nhánh update; server trả `noSuchObject` nếu DN không có.
- (3) `ldapTemplate.create(person)` với DN rõ ràng; hoặc thiết kế trạng thái mới `Persistable` thật chính xác nếu cần dùng repository.
- (4) Cách A: `repository.findByUid("mai")` → `setDescription(...)` → `repository.save(...)`. Cách B: `ldapTemplate.modifyAttributes(dn, new ModificationItem[] { ...REPLACE_ATTRIBUTE... })`.
- (5) ODM có thể sửa/xóa các attribute ánh xạ không được thiết lập; nên tránh partial entity.
- (6) `uid` là `@DnAttribute`, có thể thay RDN; ảnh hưởng nhóm, ACL và tham chiếu DN; cần chiến lược rename/move riêng.
- (7) Không: có khoảng đua giữa check và create; server vẫn quyết định tính duy nhất DN.
- (8) Không có transaction đa entry mặc định; phản hồi timeout không chứng minh server chưa ghi, cần đối soát.
- (9) Từ chối tại authorization của ứng dụng dù service account có quyền LDAP.

## 16. Ghi nhớ

**`repository.save` trong Spring Data LDAP không phải upsert LDAP vô điều kiện.** Trong cách triển khai thường gặp, entity mới với `@Id=null` đi theo nhánh **create**, entity có DN đi theo nhánh **update**; `Persistable.isNew()` có thể thay đổi cơ chế phân loại khi được dùng đúng cách. `@DnAttribute` giúp ODM suy DN khi tạo entry, còn `@Entry` và `@Attribute` xác định mapping/schema tương ứng.

Để tạo mới, đảm bảo **DN chưa tồn tại**, entry cha có thật, schema hợp lệ và ACL cho phép. Để cập nhật, ưu tiên **đọc entity rồi sửa và save**, hoặc dùng `LdapTemplate.modifyAttributes` để thay đúng attribute cần thiết. Đừng gán DN sẵn rồi mặc định `save` sẽ insert; đừng dùng partial entity để update; và đừng coi rename, retry ghi hay `saveAll` là transaction đơn giản. Hãy xác minh tất cả với directory thử nghiệm trước khi quản lý dữ liệu thật.

### Tài liệu tham khảo

- [Spring Data LDAP — Repository Configuration](https://docs.spring.io/spring-data/ldap/reference/ldap/configuration.html)
- [Spring Data LDAP — LdapRepository API](https://docs.spring.io/spring-data/ldap/docs/current/api/org/springframework/data/ldap/repository/LdapRepository.html)
- [Spring Data LDAP — SimpleLdapRepository API](https://docs.spring.io/spring-data/ldap/docs/current/api/org/springframework/data/ldap/repository/support/SimpleLdapRepository.html)
- [Spring LDAP — Object-Directory Mapping](https://docs.spring.io/spring-ldap/reference/odm.html)
- [Spring LDAP — LdapTemplate API](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/LdapTemplate.html)
- [Spring LDAP — Updating Attributes via DirContextAdapter](https://docs.spring.io/spring-ldap/reference/dirobjectfactory.html)
- [RFC 4511 — LDAPv3 Add, Modify and Modify DN](https://www.rfc-editor.org/rfc/rfc4511)
- [RFC 4528 — LDAP Assertion Control](https://www.rfc-editor.org/rfc/rfc4528)
