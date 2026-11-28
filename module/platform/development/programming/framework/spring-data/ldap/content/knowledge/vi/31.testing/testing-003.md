# Chuẩn bị máy chủ LDAP nhúng hoặc container kiểm thử

## 1. Vì sao Spring Data LDAP cần directory thật khi kiểm thử?

**Spring Data LDAP** cho phép truy cập LDAP bằng repository và `LdapTemplate`, ánh xạ entry phân cấp sang đối tượng Java thông qua DN, `objectClass` và các thuộc tính được schema cho phép. Nhưng việc kiểm thử một repository LDAP không chỉ là kiểm tra phương thức Java: ứng dụng còn phụ thuộc vào cách **LDAP server** xử lý DN, filter, scope, bind, CRUD, schema và quyền truy cập.

Ví dụ, một mock `LdapTemplate` có thể được cấu hình để trả về entry Alice khi gọi `findByUid("alice")`, nhưng mock đó không tự chứng minh rằng:

- Filter đã được escape đúng khi `uid` có ký tự đặc biệt.
- Entry `inetOrgPerson` được tạo đủ `cn`, `sn` và các `objectClass` bắt buộc.
- DN `uid=alice,ou=people,dc=example,dc=org` được hiểu đúng với base DN của `ContextSource`.
- Server trả lỗi gì khi tạo trùng DN, xóa entry không tồn tại hoặc tài khoản bind thiếu quyền.
- Repository và `LdapTemplate` xử lý đúng dữ liệu đa trị như `uniqueMember`.

Vì vậy, ngoài unit test cho logic thuần Java, nên có **integration test kết nối đến một directory độc lập**. Có hai cách phổ biến:

1. **Máy chủ LDAP nhúng (embedded/in-memory)**, thường dùng UnboundID trong Spring Boot: khởi động nhanh, không cần Docker, thích hợp kiểm thử mapping, filter và CRUD cơ bản.
2. **Máy chủ LDAP chạy trong container**, thường do Testcontainers quản lý: chạy một triển khai directory gần với môi trường thực hơn, thích hợp kiểm thử schema, ACL, TLS và các khác biệt của server.

Bài học hướng dẫn cả hai cách, từ chuẩn bị dữ liệu LDIF đến thực thi kiểm thử với Spring Data LDAP, xác định điều gì được và chưa được chứng minh bởi mỗi môi trường.

## 2. Chọn embedded LDAP hay container?

| Tiêu chí | Embedded UnboundID | Container LDAP qua Testcontainers |
| --- | --- | --- |
| Chạy cùng JVM kiểm thử | Có, server in-memory | Không, chạy một tiến trình server trong container |
| Phụ thuộc Docker/container runtime | Không | Có |
| Thời gian khởi tạo | Thường ngắn | Thường cao hơn vì khởi tạo image và server |
| Cấu hình từ Spring Boot | Có auto-configuration cho embedded LDAP | Có thể tích hợp bằng `@DynamicPropertySource` |
| Dữ liệu mẫu | LDIF, lập trình trực tiếp | LDIF bootstrap, lệnh import hoặc `LdapTemplate` |
| Tương thích schema/ACL với production | Giới hạn theo khả năng mô phỏng của UnboundID | Tốt hơn nếu container dùng đúng loại server và cấu hình gần production |
| TLS, StartTLS, referral, paging, controls | Cần kiểm tra hỗ trợ cụ thể; không giả định giống production | Có thể kiểm thử theo khả năng của image/server đã chọn |
| Tính độc lập giữa test | Dễ tạo context/instance mới | Cần chiến lược vòng đời container và reset fixture |
| Phù hợp nhất | Kiểm thử repository, DN, search/filter, CRUD thường xuyên | Kiểm thử tích hợp gần production và hành vi đặc thù LDAP server |

Không có lựa chọn nào tự thay thế mọi môi trường còn lại. Một hướng triển khai thực tế là dùng **embedded** cho nhiều integration test chạy nhanh, thêm **container** cho những hành vi phụ thuộc loại LDAP server đang vận hành, và giữ một số kiểm thử trên môi trường staging có schema/TLS/ACL tương đương production.

**Không kết nối test vào LDAP production.** Tác vụ CRUD hoặc dọn dữ liệu thử có thể tác động trực tiếp đến tài khoản, nhóm và quyền truy cập thật.

## 3. Chuẩn bị cấu trúc dữ liệu thử nghiệm và file LDIF

### 3.1. Cây thư mục mẫu

Để thống nhất ví dụ, dùng base DN:

```text
dc=example,dc=org
├── ou=people
│   ├── uid=alice
│   └── uid=bob
└── ou=groups
    └── cn=reviewers
```

Trong đó:

- `uid=alice` và `uid=bob` dùng `objectClass=inetOrgPerson`.
- `cn=reviewers` dùng `objectClass=groupOfUniqueNames`.
- Thuộc tính `uniqueMember` của nhóm chứa **DN đầy đủ** của Alice.
- `ContextSource` phía ứng dụng được cấu hình base là `dc=example,dc=org`, nên `LdapTemplate` thường nhận DN tương đối như `uid=alice,ou=people`.

### 3.2. File `src/test/resources/ldap/fixtures.ldif`

LDIF (*LDAP Data Interchange Format*) mô tả từng entry bằng `dn:`, thuộc tính và các dòng trống phân cách entry. Ví dụ dưới đây dùng các `objectClass` phổ biến:

```ldif
dn: dc=example,dc=org
objectClass: top
objectClass: domain
dc: example

dn: ou=people,dc=example,dc=org
objectClass: top
objectClass: organizationalUnit
ou: people

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
mail: bob@example.org

dn: ou=groups,dc=example,dc=org
objectClass: top
objectClass: organizationalUnit
ou: groups

dn: cn=reviewers,ou=groups,dc=example,dc=org
objectClass: top
objectClass: groupOfUniqueNames
cn: reviewers
uniqueMember: uid=alice,ou=people,dc=example,dc=org
```

Điều cần kiểm tra trước khi import:

- **DN cha trước DN con**: thêm `dc=example,...`, rồi `ou=people`, sau đó `uid=alice`. Nếu công cụ đã khởi tạo entry gốc, tránh import trùng entry gốc.
- **Schema đúng**: `person` cần `cn`, `sn`; `inetOrgPerson` kế thừa các lớp phù hợp; `groupOfUniqueNames` cần ít nhất một `uniqueMember` trong schema thông thường.
- **Không chứa dữ liệu thật**: không chép LDIF của nhân viên, mật khẩu hoặc DN production vào source kiểm thử. Dữ liệu phải là dữ liệu giả.
- **UTF-8**: khi có ký tự tiếng Việt hoặc giá trị đặc biệt, tuân thủ cách mã hóa LDIF (RFC 2849); công cụ import phải đọc đúng encoding.
- **Cấu trúc bất biến**: lưu fixture trong `src/test/resources`, có version control và review. Nếu cần nhiều kịch bản, chia fixture theo tên mô tả thay vì liên tục sửa một file dùng chung.

> LDIF trên là mẫu cho thử nghiệm; một directory vendor khác có thể có schema hoặc cơ chế bootstrap riêng. Phải xác minh import hoàn tất và đọc lại entry đã tạo trước khi coi fixture hợp lệ.

## 4. Phương án A: embedded LDAP bằng UnboundID và Spring Boot

Spring Boot hỗ trợ auto-configuration một **UnboundID in-memory LDAP server** phục vụ kiểm thử. Tính năng này được bật khi dependency UnboundID có mặt và cấu hình embedded LDAP phù hợp. Spring LDAP cũng cung cấp thư viện `spring-ldap-test` để khởi tạo embedded server trực tiếp khi không dùng cách tự cấu hình của Spring Boot.

### 4.1. Dependency chỉ dành cho test

Ví dụ Gradle Kotlin DSL; phiên bản thực tế do Spring Boot BOM hoặc dependency management của dự án quản lý:

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-ldap")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("com.unboundid:unboundid-ldapsdk")
}
```

Thêm thư viện `unboundid-ldapsdk` ở **test scope** để không đóng gói directory thử vào runtime production. Nếu ứng dụng đã có starter LDAP và JUnit, chỉ cần bổ sung dependency còn thiếu.

Với Maven, ý tưởng tương ứng là dependency UnboundID mang `<scope>test</scope>`. Không tự lấy phiên bản ngẫu nhiên khi dự án đang dùng dependency management.

### 4.2. Cấu hình profile `ldap-embedded`

Tạo file mẫu `src/test/resources/application-ldap-embedded.yml`:

```yaml
spring:
  ldap:
    base: "dc=example,dc=org"
    embedded:
      base-dn: "dc=example,dc=org"
      ldif: "classpath:ldap/fixtures.ldif"
      validation:
        enabled: true
```

Hai thuộc tính `base` dễ bị nhầm:

| Thuộc tính | Ý nghĩa |
| --- | --- |
| `spring.ldap.base` | Base DN trên **client** (`LdapContextSource`): các DN Java thường được hiểu tương đối với nó |
| `spring.ldap.embedded.base-dn` | Naming context/base của **server in-memory** |
| `spring.ldap.embedded.ldif` | File fixture được server tải khi khởi động |
| `spring.ldap.embedded.validation.enabled` | Bật kiểm tra schema cho dữ liệu LDIF trong embedded server |

Khi không đặt `spring.ldap.embedded.port`, Spring Boot có thể chọn **cổng ngẫu nhiên**, giảm xung đột nếu nhiều bộ test chạy trên cùng máy. Với cấu hình embedded, Boot thiết lập thông tin kết nối tới server nội bộ; không cần cố định `spring.ldap.urls` của production.

Theo Spring Boot hiện hành, các thuộc tính `spring.ldap.embedded.*` quyết định endpoint và credential của server nhúng. Những thông tin kết nối ứng dụng nhận qua auto-configuration sẽ lấy từ server embedded; **đừng giả định** `spring.ldap.urls`, `spring.ldap.username` hoặc `spring.ldap.password` của môi trường production vẫn được áp dụng trong profile embedded. Nếu đã tự khai báo `LdapContextSource`/`ContextSource`, cần xem lại auto-configuration trước khi dùng mẫu này.

### 4.3. Kiểm thử tìm kiếm thật bằng `LdapTemplate`

Giả sử code ứng dụng đã có cấu hình Spring Boot và `LdapTemplate` được tạo bởi auto-configuration. Đây là một integration test gọi **LDAP server thật trong JVM**, không mock phương thức search:

```java
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.test.context.ActiveProfiles;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@ActiveProfiles("ldap-embedded")
class EmbeddedLdapSearchIT {

    @Autowired
    LdapTemplate ldapTemplate;

    @Test
    void findsAliceUnderPeopleOu() {
        List<String> uids = ldapTemplate.search(
            "ou=people",
            "(&(objectClass=inetOrgPerson)(uid=alice))",
            attrs -> (String) attrs.get("uid").get()
        );

        assertThat(uids).containsExactly("alice");
    }

    @Test
    void doesNotMatchUnknownUid() {
        List<String> uids = ldapTemplate.search(
            "ou=people",
            "(&(objectClass=inetOrgPerson)(uid=unknown))",
            attrs -> (String) attrs.get("uid").get()
        );

        assertThat(uids).isEmpty();
    }
}
```

Trong đoạn mã trên, base `ou=people` là DN tương đối với `spring.ldap.base=dc=example,dc=org`; kết quả được ánh xạ từ thuộc tính `uid`. Nếu điều kiện filter không khớp, Search trả danh sách rỗng trong điều kiện base tồn tại và server cho phép truy cập.

Các assertion không kiểm chứng được ACL/TLS của production, vì fixture embedded có thể dùng mặc định đơn giản hơn. Nhưng chúng **thực sự chạy JNDI/LDAP search và schema** thay vì chỉ xác nhận một giá trị đã được stub.

### 4.4. Kiểm thử repository và ánh xạ entry

Với entity Spring LDAP ODM:

```java
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

    public PersonEntry() { }

    public Name getDn() { return dn; }
    public void setDn(Name dn) { this.dn = dn; }

    public String getUid() { return uid; }
    public void setUid(String uid) { this.uid = uid; }

    public String getCommonName() { return commonName; }
    public void setCommonName(String commonName) {
        this.commonName = commonName;
    }

    public String getSurname() { return surname; }
    public void setSurname(String surname) {
        this.surname = surname;
    }
}
```

Repository tương ứng:

```java
import org.springframework.data.ldap.repository.LdapRepository;

public interface PersonRepository extends LdapRepository<PersonEntry> {
}
```

Kiểm tra lookup theo DN:

```java
import javax.naming.Name;
import javax.naming.ldap.LdapName;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@ActiveProfiles("ldap-embedded")
class PersonRepositoryIT {

    @Autowired
    PersonRepository repository;

    @Test
    void readsEntryByDn() throws Exception {
        Name id = new LdapName("uid=alice,ou=people");

        assertThat(repository.findById(id))
            .isPresent()
            .get()
            .extracting(PersonEntry::getUid)
            .isEqualTo("alice");
    }
}
```

`PersonEntry` và `PersonRepository` phải nằm trong phạm vi scan của ứng dụng, hoặc được đăng ký bằng cấu hình `@EntityScan` / `@EnableLdapRepositories`. Ở đây `@Id` là `org.springframework.ldap.odm.annotations.Id`, **không phải `jakarta.persistence.Id`**. Kiểm thử này chứng minh mapping DN/thuộc tính khớp directory mẫu.

Để kiểm thử **Create/Update/Delete**, dùng một DN dành riêng cho test như `uid=test-create-123,ou=people` và xác minh kết quả bằng lookup độc lập. Không sửa/xóa Alice nếu các test khác còn cần fixture đó.

## 5. Phương án B: LDAP server trong container với Testcontainers

Container hữu ích khi muốn thử với cùng loại directory như production, ví dụ **OpenLDAP**, cùng schema và ACL tương tự. Testcontainers quản lý việc khởi động, ánh xạ cổng động và dọn tài nguyên kiểm thử; cần máy có Docker hoặc container runtime tương thích.

Có các module container chuyên dụng (ví dụ module LLDAP trong hệ sinh thái Testcontainers), nhưng **LLDAP không đồng nghĩa OpenLDAP/Active Directory**. Muốn xác minh hành vi riêng của OpenLDAP, hãy dùng image OpenLDAP phù hợp, ví dụ qua `GenericContainer`.

### 5.1. Dependency Testcontainers

Ví dụ Gradle:

```kotlin
dependencies {
    testImplementation("org.springframework.boot:spring-boot-starter-test")

    testImplementation("org.testcontainers:testcontainers")
    testImplementation("org.testcontainers:junit-jupiter")
}
```

Đặt phiên bản Testcontainers tương thích với BOM của dự án. Không cần `unboundid-ldapsdk` cho phương án container nếu không chạy embedded LDAP trong cùng tập kiểm thử.

### 5.2. Một `GenericContainer` OpenLDAP và cấu hình động

Ví dụ dùng **image OpenLDAP đã ghim tag**. `osixia/openldap:1.5.0` ở đây minh họa cấu hình của nhánh image 1.x (cổng LDAP nội bộ 389, biến `LDAP_DOMAIN`, `LDAP_ADMIN_PASSWORD`); trước khi dùng trong CI, hãy kiểm tra image còn được duy trì/phân phối và ghim digest đã phê duyệt. Khi chọn image/version khác, các biến môi trường và cổng có thể **khác hoàn toàn**.

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.containers.wait.strategy.Wait;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

import java.time.Duration;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@Testcontainers
class OpenLdapContainerIT {

    @Container
    static final GenericContainer<?> LDAP =
        new GenericContainer<>(
            DockerImageName.parse("osixia/openldap:1.5.0"))
            .withEnv("LDAP_ORGANISATION", "Example Org")
            .withEnv("LDAP_DOMAIN", "example.org")
            .withEnv("LDAP_ADMIN_PASSWORD", "test-password-only")
            .withEnv("LDAP_TLS", "false")
            .withExposedPorts(389)
            .waitingFor(
                Wait.forListeningPort()
                    .withStartupTimeout(Duration.ofMinutes(2))
            );

    @DynamicPropertySource
    static void ldapProperties(DynamicPropertyRegistry properties) {
        properties.add(
            "spring.ldap.urls",
            () -> "ldap://" + LDAP.getHost()
                + ":" + LDAP.getMappedPort(389)
        );
        properties.add("spring.ldap.base",
            () -> "dc=example,dc=org");
        properties.add("spring.ldap.username",
            () -> "cn=admin,dc=example,dc=org");
        properties.add("spring.ldap.password",
            () -> "test-password-only");
    }

    @Autowired
    LdapTemplate ldapTemplate;

    @Test
    void canReadBaseEntry() {
        String dc = ldapTemplate.lookup(
            "",
            new String[] { "dc" },
            attrs -> String.valueOf(attrs.get("dc").get())
        );

        assertThat(dc).isEqualTo("example");
    }
}
```

Điểm cần hiểu:

- `@Container` và `@Testcontainers` để JUnit extension khởi động/dừng container theo vòng đời test.
- `withExposedPorts(389)` yêu cầu cổng container **389**, nhưng cổng trên host được cấp động; luôn đọc `LDAP.getMappedPort(389)`, không gắn cứng `localhost:389`.
- `@DynamicPropertySource` cấp URL, bind DN, mật khẩu **chỉ dùng cho test** vào Spring context trước khi ứng dụng khởi tạo `LdapTemplate`.
- `spring.ldap.base` là base trên client; ở đây root được image tạo qua `LDAP_DOMAIN=example.org`.
- Test smoke đọc thuộc tính `dc` tại root tương đối `""`, qua cùng `LdapTemplate` mà ứng dụng sẽ dùng.
- Image này được minh họa với **LDAP không mã hóa trong một container thử nghiệm riêng**. Để kiểm thử TLS, cần cấu hình image với chứng chỉ và truststore hợp lệ. Không chuyển cấu hình `LDAP_TLS=false` sang môi trường thật.

Cần giữ profile container **không bật** `spring.ldap.embedded.base-dn`, nếu không auto-configuration embedded có thể tranh quyền thiết lập `ContextSource`. Nếu bộ test dùng nhiều profile, tách rõ `ldap-embedded` và `ldap-container`.

`Wait.forListeningPort()` chỉ cho biết cổng đã có listener, có thể **sớm hơn** thời điểm bootstrap LDIF/schema hoàn tất. Với image cần khởi tạo lâu, thêm wait strategy phù hợp với image và một phép LDAP bind/lookup smoke có retry giới hạn để đánh giá readiness thực tế.

### 5.3. Đưa fixture vào container

Có ba hướng:

1. **Bootstrap LDIF từ image**: copy `fixtures.ldif` tới thư mục bootstrap do image công bố; chú ý root entry thường đã được image tạo tự động, nên tách các entry con ra khỏi root.
2. **Import qua `ldapadd`** sau khi container sẵn sàng: thao tác dưới tài khoản thử, dùng `-f` trỏ tới file LDIF, kiểm tra mã thoát và đọc lại.
3. **Seed qua `LdapTemplate`/JNDI** ở bước setup: tạo OU, người dùng và nhóm bằng `bind`/`create`; phù hợp khi cần biến thể dữ liệu theo từng test.

Ví dụ lệnh import cho một OpenLDAP container đã có `ldapadd`, với file **chỉ chứa các entry chưa tồn tại**:

```bash
ldapadd -x \
  -H ldap://localhost:389 \
  -D "cn=admin,dc=example,dc=org" -W \
  -f test-entries-only.ldif
```

Lệnh trên giả định chạy **trong môi trường nhìn thấy cổng 389 của server** (ví dụ bên trong container). Nếu chạy từ host, cần dùng **cổng host đã được ánh xạ** thay vì mặc định 389. Không gắn bind password thật vào tham số `-w`; `-W` yêu cầu nhập mật khẩu tương tác.

Với Testcontainers, có thể gọi `container.execInContainer(...)` để import sau bootstrap, hoặc copy fixture bằng `MountableFile.forClasspathResource(...)` tới đúng đường dẫn mà image hỗ trợ. Đường dẫn bootstrap và thứ tự xử lý LDIF phụ thuộc image/version; không có một đường dẫn chung cho mọi server LDAP.

**Quan trọng:** Fixture nhập vào embedded server và fixture nhập vào container có thể cần khác nhau ở **entry gốc** hoặc thuộc tính đặc thù. Mục tiêu là tạo ra **cùng cấu trúc logic** để chạy các assertion tương đương, không phải ép hai server dùng cùng một file khi cơ chế bootstrap của chúng khác nhau.

## 6. Phân biệt kiểm thử cấu hình, schema và quyền

Dù chọn embedded hay container, dữ liệu fixture phải đủ để test các đặc tính riêng của LDAP:

| Đặc tính | Ví dụ cần kiểm tra | Lưu ý |
| --- | --- | --- |
| **Base DN** | `dc=example,dc=org` | `spring.ldap.base` và DN tương đối không được ghép đôi/sai |
| **DN và RDN** | `uid=alice,ou=people` | Dùng `LdapName`/`LdapNameBuilder`, kiểm tra ký tự đặc biệt |
| **`objectClass`** | `inetOrgPerson` cần `cn`, `sn` | Kiểm tra schema thực thay vì tắt validation |
| **Search scope** | `ONELEVEL` vs `SUBTREE` | Tạo thêm OU lồng nhau để phân biệt |
| **Filter escaping** | Giá trị `uid` có `*`, `(`, `)` | Dùng `LdapQueryBuilder`, tránh nối chuỗi |
| **Thuộc tính đa trị** | `uniqueMember` có nhiều DN | Kiểm tra thêm/xóa một giá trị không ghi đè cả danh sách |
| **CRUD** | Tạo mới, cập nhật, tạo trùng DN, xóa | Đọc lại trạng thái sau thao tác; trường hợp lỗi phải xác minh |
| **ACL** | Tài khoản chỉ có quyền đọc | Admin bind trong fixture không chứng minh ACL của production |
| **TLS** | LDAPS/StartTLS và hostname verification | Embedded đơn giản có thể không tái hiện đúng chain/cert config |
| **Controls** | Paging, server-side sort, assertion | Hỏi `supportedControl` và kiểm thử trên server thật |
| **Referral/replication** | Entry nằm ở partition khác | Một container đơn lẻ không tự tạo topology nhiều node |

Nếu production dùng **Active Directory**, test với OpenLDAP có ích để kiểm tra các phần LDAP chuẩn, nhưng không tự chứng minh các hành vi AD-specific như chính sách account, thuộc tính vendor, referral hoặc security descriptor. Nếu các đặc tính đó quan trọng, cần môi trường kiểm thử tương thích với AD.

## 7. Cô lập dữ liệu và đảm bảo test chạy lặp lại

### 7.1. Một test không được làm hỏng test khác

Các lỗi ngẫu nhiên thường xuất hiện khi nhiều test dùng cùng một entry và thứ tự thực thi thay đổi:

- Test A xóa `uid=alice`, làm test B tìm Alice thất bại.
- Test C đổi `cn=reviewers` hoặc `uniqueMember` nhưng không hoàn nguyên.
- Hai test chạy song song cố tạo cùng DN dẫn đến `entryAlreadyExists`.
- Một test thất bại giữa chừng khiến fixture còn dữ liệu dở dang.

Nên dùng một trong các chiến lược:

- **Khởi tạo server/container mới cho mỗi lớp** khi chi phí chấp nhận được; test class khác có trạng thái riêng.
- **Reset dữ liệu về fixture gốc trước mỗi test**; thứ tự xóa entry từ lá lên cha và kiểm tra entry thuộc nhánh test.
- **Tạo DN riêng theo test**, ví dụ `uid=case-01,ou=people`, rồi chỉ xóa các entry do chính test tạo.
- Với thao tác phá hủy, tách suite hoặc vô hiệu hóa chạy song song trên một directory chia sẻ.
- Không dựa vào `@Transactional` để ngầm rollback toàn bộ thay đổi LDAP. Cơ chế bù trừ của Spring LDAP không tương đương transaction nhiều entry phía server.

Chỉ chạy cleanup dưới **nhánh test được phép**. Không dùng script xóa `dc=example,dc=org` tùy tiện nếu server đó có thể được chia sẻ bởi nhiều suite.

### 7.2. Khởi tạo lại context khác với xóa dữ liệu directory

`@DirtiesContext` khiến Spring Test tải lại `ApplicationContext` khi thích hợp, nhưng **không bảo đảm dữ liệu LDAP container bên ngoài được reset**. Với embedded server do chính context sở hữu, đóng/mở context có thể tái tạo server và nạp lại LDIF; cần kiểm chứng vòng đời bean của phiên bản đang dùng.

Với Testcontainers, vòng đời container do JUnit/thiết kế suite quản lý; Spring context được tạo lại không nhất thiết khởi động container mới. Vì vậy muốn đảm bảo dữ liệu sạch, phải dùng **reset fixture hoặc container mới** một cách tường minh.

### 7.3. Một nguồn fixture, nhiều kịch bản

Có thể chuẩn hóa fixture theo tầng:

```text
src/test/resources/ldap/
├── fixtures.ldif              # Người dùng và nhóm hợp lệ
├── nested-ou.ldif             # OU lồng nhau cho ONELEVEL/SUBTREE
├── invalid-schema.ldif        # Dữ liệu dùng để kiểm thử lỗi import
└── tls/                       # Chứng chỉ self-signed chỉ dùng cho test
```

Các đường dẫn là ví dụ minh họa, không phải yêu cầu phải tạo tất cả. Mỗi test biết rõ dữ liệu đầu vào, trạng thái ban đầu và trạng thái đích. Đối với lỗi schema, không nhất thiết import `invalid-schema.ldif` lúc khởi tạo toàn bộ suite; có thể gửi thao tác tạo sai trong một test riêng để kiểm tra server từ chối.

## 8. Kiểm thử tích hợp thực tế: nên assert điều gì?

Một bài kiểm thử LDAP có giá trị phải quan sát **trạng thái server sau thao tác**, không chỉ kiểm tra phương thức Java đã được gọi.

### 8.1. Search và filter

```java
import static org.springframework.ldap.query.LdapQueryBuilder.query;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.SearchScope;

LdapQuery ldapQuery = query()
    .base("ou=people")
    .searchScope(SearchScope.SUBTREE)
    .attributes("uid", "cn")
    .where("objectClass").is("inetOrgPerson")
    .and("uid").is("alice");

List<String> found = ldapTemplate.search(
    ldapQuery,
    attrs -> (String) attrs.get("uid").get()
);
```

Khẳng định Alice xuất hiện và Bob không xuất hiện trong kết quả của filter. Khi kiểm tra **LDAP injection**, truyền giá trị chứa ký tự `*`, `(` và `)` qua query builder rồi chứng minh filter không bị mở rộng bất ngờ. Thư viện sẽ escape giá trị; không ghép filter bằng nối chuỗi với input chưa tin cậy.

### 8.2. CRUD, schema và trạng thái thật

Các test nên bao gồm:

1. Tạo entry hợp lệ với `uid`, `cn`, `sn` và `objectClass` đúng; đọc lại bằng DN.
2. Gửi yêu cầu tạo **trùng DN**; kiểm tra server từ chối và entry gốc không bị ghi đè.
3. Gửi dữ liệu **thiếu thuộc tính bắt buộc**; kiểm tra schema từ chối khi validation bật.
4. Sửa `mail` trên entry vừa tạo, đọc lại để xác minh giá trị mới.
5. Thêm một `uniqueMember` vào nhóm; xác minh thành viên cũ vẫn còn.
6. Xóa entry của test; xác minh entry không còn tồn tại và các tham chiếu được xử lý theo yêu cầu nghiệp vụ.
7. Thử thao tác bằng tài khoản **chỉ đọc** khi container có ACL tương ứng; kiểm tra lỗi quyền.

Không giả định `saveAll` hay chuỗi `LdapTemplate.modifyAttributes(...)` trên hai DN khác nhau có tính nguyên tử chung. Nếu test kiểm tra phục hồi sau lỗi, cần mô phỏng thất bại ở thao tác thứ hai và xác minh trạng thái dở dang/đối soát.

### 8.3. Với `@SpringBootTest`, chỉ dùng logic mã cần thiết

Unit test tính chuỗi giao diện, kiểm tra tham số hoặc chuyển đổi DTO không nhất thiết cần LDAP thật. Integration test với directory nên dành cho các ranh giới thực tế: schema, DN, filter, mapping, CRUD, ACL và TLS. Điều này giúp suite chạy nhanh nhưng vẫn phát hiện lỗi mà mock không thể tái hiện.

## 9. Chạy trên CI/CD

Trước khi đưa test vào pipeline:

- **Kiểm tra runtime:** embedded cần JDK tương thích; Testcontainers cần quyền truy cập container runtime và khả năng kéo image đã phê duyệt.
- **Ghim phiên bản/digest:** nếu dùng image LDAP, quản lý digest/tag để tránh pipeline cho kết quả khác nhau theo ngày.
- **Không dùng tài khoản production:** bind DN/password và CA của suite là dữ liệu test. Đừng ghi thông tin xác thực vào log.
- **Dùng port động:** embedded và Testcontainers tránh cổng cố định nếu có thể, đặc biệt khi build chạy song song.
- **Đợi readiness thực sự:** port mở chưa chắc import LDIF đã xong; thực hiện LDAP bind và lookup smoke trước khi vào test.
- **Giới hạn tài nguyên:** đặt timeout cho setup, Search và toàn test; thu thập log server khi thất bại, nhưng lọc thông tin nhạy cảm.
- **Dọn tài nguyên:** để Testcontainers/JUnit dừng container đúng vòng đời; đừng cố giữ container dùng chung mà không có chiến lược reset dữ liệu.
- **Tách test nhanh và chậm:** có thể dùng tag JUnit (`@Tag("ldap-integration")`) để chạy embedded thường xuyên và container ở bước integration phù hợp.
- **Báo lỗi rõ nguyên nhân:** phân biệt không có Docker, không kéo được image, không bind được, lỗi LDIF/schema và assertion nghiệp vụ sai.

Ví dụ JUnit tag:

```java
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

@Tag("ldap-integration")
class DirectoryIntegrationSuite {

    @Test
    void sample() {
        // Thay bằng phép kiểm thử LDAP thực tế.
    }
}
```

Không nên để test mặc định bỏ qua khi thiếu Docker rồi báo pipeline xanh mà không biết suite container chưa hề chạy. Nếu tổ chức cho phép tách stage tùy chọn, cần hiển thị trạng thái **skipped** và lý do rõ ràng.

## 10. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| `NameNotFoundException`/`noSuchObject` | Base DN, OU cha hoặc DN tương đối sai | Đối chiếu cây fixture, `spring.ldap.base`, DN đầy đủ |
| `objectClassViolation` | Thiếu `cn`/`sn`, sai tổ hợp `objectClass` | Kiểm tra schema; bật validation và sửa LDIF |
| `entryAlreadyExists` | Fixture root đã được bootstrap hoặc test dùng lại DN | Không import trùng; reset dataset hoặc dùng DN test riêng |
| `InvalidCredentialsException`/result code `49` | Sai bind DN/password | Kiểm tra cấu hình credential của embedded/container |
| `CommunicationException` | Server chưa sẵn sàng, host/port mapping sai, network lỗi | Dùng readiness check và `getMappedPort(...)` |
| Spring Test kết nối nhầm production | Profile sai, embedded không bật hoặc config động chưa áp dụng | Xác minh profile, bean `ContextSource` và URL thực tế |
| Test tìm đúng nhưng CRUD lỗi | Quyền ghi, schema hoặc mapping thiếu | Kiểm tra quyền bind identity và trường `@Id`/`@Entry` |
| Dữ liệu test lúc đúng lúc sai | Chia sẻ entry giữa test, teardown thiếu, chạy song song | Reset fixture, tạo DN riêng, cô lập vòng đời container |
| Kết quả container khác embedded | Khác schema, ACL, matching rules, server controls | Điều chỉnh fixture và test theo đúng mục tiêu tương thích |
| Lỗi TLS ở môi trường gần production | Truststore, certificate SAN, thời hạn hoặc CA chain | Test handshake với đúng hostname và truststore |
| Test dựa vào `@DirtiesContext` nhưng dữ liệu còn | Container có vòng đời ngoài ApplicationContext | Reset data hoặc khởi động container mới |

Tránh giải quyết lỗi schema bằng cách **tắt validation vĩnh viễn**. Có thể tạm vô hiệu hóa trong một phép thử đặc biệt để cô lập nguyên nhân, nhưng suite chính cần giữ validation gần với directory sẽ triển khai.

## 11. Bài tập thực hành và câu hỏi tự kiểm tra

1. Tạo profile `ldap-embedded`, nạp `fixtures.ldif` và viết test tìm `uid=alice` bằng `LdapTemplate`. Kết quả nào xác nhận fixture đã được load?
2. Vì sao `spring.ldap.base` và `spring.ldap.embedded.base-dn` cùng là DN nhưng phục vụ hai tầng khác nhau?
3. Vì sao nên dùng cổng ngẫu nhiên thay vì cố định `8389` khi CI chạy nhiều job?
4. Hãy thử import một `inetOrgPerson` thiếu `sn`. Server phải phản hồi thế nào nếu schema validation đang bật?
5. Viết test repository `findById(new LdapName("uid=bob,ou=people"))` và giải thích tại sao truyền `"bob"` là không đủ.
6. Một test xóa Alice khiến test tìm nhóm `reviewers` không ổn định. Bạn sẽ cô lập dữ liệu theo cách nào?
7. Khi dùng `GenericContainer`, tại sao không viết cố định `ldap://localhost:389` trong cấu hình ứng dụng?
8. Vì sao container OpenLDAP thường kiểm tra ACL, schema và behavior production tốt hơn embedded UnboundID, nhưng chưa đủ để chứng minh tính tương thích Active Directory?
9. Nếu Testcontainers báo port đã mở nhưng LDAP bind vẫn lỗi, cơ chế readiness nào nên bổ sung?
10. Nếu pipeline không có Docker, cần phản ánh tình trạng chạy suite container ra sao để không tạo cảm giác kiểm thử đầy đủ?
11. Để kiểm thử LDAPS, bạn phải bổ sung gì ngoài việc đổi URL từ `ldap://` thành `ldaps://`?
12. Đề xuất test chứng minh một LDAP filter được escape đúng khi input chứa dấu ngoặc và dấu `*`.

## 12. Kết luận

Chuẩn bị LDAP server thử nghiệm là bước thiết yếu để kiểm tra **Spring Data LDAP repository, `LdapTemplate`, DN, schema, filter và CRUD** trong điều kiện gần thực tế. **Embedded UnboundID** phù hợp với bộ kiểm thử nhanh, không cần Docker; **LDAP container** phù hợp khi cần server triển khai cụ thể, ACL/TLS hoặc hành vi vendor. Cả hai cần dữ liệu LDIF có thể tái lập, base DN thống nhất, credential riêng cho test và một cơ chế cô lập/cleanup rõ ràng.

Khi đánh giá kết quả, hãy chỉ kết luận trong phạm vi môi trường đã chạy: một test xanh trên embedded không chứng minh LDAP production có cùng schema, ACL hoặc TLS. Giá trị của kiểm thử tích hợp nằm ở khả năng **phát hiện sai khác về hành vi directory trước khi deploy**.

### Tài liệu tham khảo

- [Spring Boot Reference — Working with NoSQL Technologies: LDAP và Embedded In-memory LDAP Server](https://docs.spring.io/spring-boot/reference/data/nosql.html).
- [Spring LDAP Reference — Testing: Embedded Server, ApacheDS và UnboundID](https://docs.spring.io/spring-ldap/reference/testing.html).
- [Spring Boot Guide — Authenticating a User with LDAP (embedded LDAP và LDIF)](https://spring.io/guides/gs/authenticating-ldap).
- [Testcontainers for Java — Getting Started và GenericContainer](https://java.testcontainers.org/).
- [Testcontainers for Java — LDAP module (LLDAP)](https://java.testcontainers.org/modules/ldap/).
- [Testcontainers — Container lifecycle và wait strategies](https://testcontainers.com/getting-started/).
- [RFC 2849 — The LDAP Data Interchange Format (LDIF)](https://www.rfc-editor.org/rfc/rfc2849).
- [RFC 4511 — Lightweight Directory Access Protocol (LDAP): The Protocol](https://www.rfc-editor.org/rfc/rfc4511).
