# Cấu hình kết nối động cho Spring Boot test với Spring Data LDAP

## 1. Bài toán: địa chỉ LDAP thay đổi sau khi môi trường kiểm thử khởi động

Trong ứng dụng **Spring Data LDAP**, repository và `LdapTemplate` truy cập directory thông qua `ContextSource` do Spring LDAP/JNDI quản lý. Directory lưu entry theo **Distinguished Name (DN)**, `objectClass` và schema; truy vấn cần đúng base DN, LDAP filter, quyền bind và địa chỉ máy chủ.

Khi chạy kiểm thử tích hợp, LDAP server có thể được tạo ngay lúc chạy test:

- **Embedded LDAP** nằm trong tiến trình test, có cổng được cấp tự động.
- **LDAP container** chạy qua Testcontainers, có cổng 389/636 *bên trong container* nhưng **host và cổng bên ngoài thay đổi** theo máy chạy hoặc job CI.
- **Directory dùng riêng cho một job** được tạo bằng hạ tầng test, cung cấp URL và tài khoản bind khi khởi tạo xong.

Nếu ghi cố định `spring.ldap.urls=ldap://localhost:389` trong `application-test.yml`, test có thể hoạt động trên laptop nhưng thất bại trong CI vì port host không phải 389, Docker daemon chạy qua môi trường khác hoặc server chưa sẵn sàng. Tệ hơn, cấu hình test bị lẫn với profile production có thể khiến thao tác `save`/`delete` nhắm sai directory.

**Cấu hình kết nối động** là kỹ thuật chuyển thông tin LDAP *đã biết khi môi trường test được tạo* thành các property Spring **trước khi `ApplicationContext` khởi tạo các bean kết nối**.

Mục tiêu bài học:

1. Phân biệt cấu hình tĩnh và cấu hình động của Spring Boot test.
2. Áp dụng `@DynamicPropertySource` với `DynamicPropertyRegistry` để inject URL, base DN, bind DN và password của LDAP Testcontainers.
3. Kiểm tra `ContextSource`/`LdapTemplate` thực sự trỏ vào directory thử nghiệm bằng smoke test.
4. Phân biệt mô hình container với Spring Boot embedded LDAP.
5. Xử lý lifecycle, cache `ApplicationContext`, quyền truy cập, TLS, dữ liệu fixture và các lỗi thường gặp.

> **Nguyên tắc an toàn:** Test phải hướng đến một directory riêng, có thể xóa hoặc tái tạo; không bao giờ thử CRUD bằng cấu hình kết nối LDAP production.

## 2. Bốn property xác định kết nối LDAP phía ứng dụng

Trong một dự án Spring Boot dùng cơ chế tự cấu hình Spring LDAP:

| Property | Giá trị minh họa | Vai trò |
| --- | --- | --- |
| `spring.ldap.urls` | `ldap://127.0.0.1:49173` | Một hoặc nhiều endpoint của LDAP server |
| `spring.ldap.base` | `dc=example,dc=org` | Base DN được client dùng khi phân giải DN tương đối |
| `spring.ldap.username` | `cn=admin,dc=example,dc=org` | Bind DN/tài khoản kết nối |
| `spring.ldap.password` | Secret của môi trường test | Credential dùng với bind identity |

Cần tách biệt:

- **Endpoint** xác định kết nối mạng: host, port và `ldap://`/`ldaps://`.
- **Server naming context** (ví dụ `dc=example,dc=org`) phải **tồn tại tại server**. Property `spring.ldap.base` không tạo entry hay suffix.
- **Base DN của client** quyết định ý nghĩa của `ldapTemplate.search("ou=people", ...)` và DN `uid=alice,ou=people` khi `ContextSource` có base `dc=example,dc=org`.
- **Bind identity** có thể xác thực thành công nhưng vẫn không có quyền search/read/modify, tùy ACL.

Ví dụ cây dữ liệu của server test:

~~~text
dc=example,dc=org
├── ou=people
│   └── uid=alice
│       ├── objectClass: inetOrgPerson
│       ├── uid: alice
│       ├── cn: Alice Nguyen
│       └── sn: Nguyen
└── ou=groups
    └── cn=reviewers
~~~

Mỗi property cần được áp dụng **trước khi `LdapContextSource` hoặc bean repository sử dụng nó**. Đổi giá trị property sau khi bean đã tạo không tự cập nhật các kết nối/pool đang mở.

## 3. Vì sao `@DynamicPropertySource` phù hợp với Testcontainers?

`@DynamicPropertySource` là annotation thuộc **Spring TestContext Framework**. Nó đánh dấu một phương thức **`static`** nhận tham số `DynamicPropertyRegistry`. Phương thức này đăng ký các `Supplier` cung cấp property cho `Environment` của `ApplicationContext` dùng trong test.

~~~java
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

@DynamicPropertySource
static void registerProperties(DynamicPropertyRegistry registry) {
    registry.add("spring.ldap.urls", () -> "ldap://localhost:1389");
}
~~~

Giá trị ở đây chỉ minh họa cú pháp. Với Testcontainers, `Supplier` sẽ **đọc host và mapped port từ container đang chạy**, không dùng số cổng cố định.

Đặc điểm cần nhớ:

- `@DynamicPropertySource` được Spring TestContext xử lý **trước khi tạo các bean cần property**.
- Supplier thường được gọi khi property được **resolve**, không phải “chạy một lần để chép tĩnh tất cả biến” lúc compile test.
- Các property đăng ký từ `@DynamicPropertySource` có **độ ưu tiên cao** trong TestContext, kể cả so với nhiều property đến từ `@TestPropertySource`, environment variables và file cấu hình. Nếu một giá trị “không đổi được” dù đã sửa YAML, hãy kiểm tra dynamic override.
- Đăng ký ở lớp test hoặc lớp test base dùng chung; không thiết kế nó như một lời gọi setter diễn ra tùy ý trong mỗi phương thức `@Test`.
- `DynamicPropertyRegistry.add(...)` nhận supplier; **không** sử dụng nó như một phương tiện thay đổi kết nối của bean đã khởi tạo sau khi test bắt đầu.

### Luồng khởi tạo

~~~mermaid
sequenceDiagram
    participant JUnit as JUnit 5 / Testcontainers
    participant Container as LDAP container
    participant Spring as Spring TestContext
    participant Props as DynamicPropertyRegistry
    participant App as LdapContextSource / LdapTemplate
    JUnit->>Container: Start LDAP container
    Container-->>JUnit: Host + mapped port
    Spring->>Props: @DynamicPropertySource register suppliers
    Spring->>Props: Resolve spring.ldap.urls/credentials
    Props-->>Spring: Values from running container
    Spring->>App: Create ContextSource and repository beans
    App->>Container: Bind + Search/Lookup
    Container-->>App: LDAP response
    App-->>JUnit: Test assertions
~~~

Đây là sơ đồ trình tự logic, không phải cam kết từng callback có thứ tự y hệt ở mọi phiên bản framework. Điểm bất biến là **container phải sẵn sàng cho đến khi supplier được sử dụng**, và các thuộc tính phải được đăng ký trước lúc Spring dựng kết nối.

## 4. Dependency cho integration test với LDAP container

Ví dụ Gradle Kotlin DSL, giả sử dự án dùng Spring Boot và Java 17+:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-ldap")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.testcontainers:testcontainers")
    testImplementation("org.testcontainers:junit-jupiter")
}
~~~

Những dependency này có các vai trò khác nhau:

- `spring-boot-starter-data-ldap`: Spring LDAP, Spring Data LDAP và auto-configuration tương thích.
- `spring-boot-starter-test`: Spring TestContext, JUnit Jupiter, AssertJ.
- `testcontainers`: tạo/quản lý container test bằng Java.
- `junit-jupiter` của Testcontainers: tích hợp `@Testcontainers`/`@Container` với vòng đời JUnit 5.

Để tránh xung đột dependency, quản lý phiên bản Spring Boot, Spring Data LDAP và Testcontainers bằng BOM/dependency management tương thích của dự án. Tên dependency và API phải được đối chiếu với **phiên bản đang sử dụng**, không copy một version bất kỳ từ bài viết cũ.

Không đóng gói Testcontainers hoặc server test vào artifact ứng dụng production. Nếu dùng image LDAP từ registry bên ngoài, ghim **tag/digest đã được phê duyệt** và tuân thủ chính sách image vulnerability scanning của tổ chức.

## 5. Ví dụ hoàn chỉnh: `GenericContainer` + `@DynamicPropertySource`

### 5.1. Khởi động server LDAP với host/port động

Trong ví dụ này dùng image `osixia/openldap:1.5.0` để minh họa API Testcontainers. Image thuộc một nhánh cũ, vì vậy khi triển khai thực tế cần kiểm tra tình trạng bảo trì và thay bằng **image OpenLDAP được tổ chức phê duyệt**, có thông số bootstrap tương ứng.

Một số giả định dành riêng cho image minh họa:

- `LDAP_DOMAIN=example.org` tạo base `dc=example,dc=org`.
- Bind admin minh họa: `cn=admin,dc=example,dc=org`.
- Cổng LDAP nội bộ là `389`.
- `LDAP_TLS=false` **chỉ dành cho mạng test cô lập** để tập trung vào cơ chế inject URL. Không sao chép cấu hình plaintext này vào production.

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.test.context.ActiveProfiles;
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
@ActiveProfiles("ldap-container")
class DynamicLdapConnectionIT {

    private static final int LDAP_PORT = 389;

    // Chỉ là credential của container throwaway.
    private static final String TEST_PASSWORD = "test-password-only";

    @Container
    static final GenericContainer<?> LDAP =
        new GenericContainer<>(
            DockerImageName.parse("osixia/openldap:1.5.0")
        )
        .withEnv("LDAP_ORGANISATION", "Example Test")
        .withEnv("LDAP_DOMAIN", "example.org")
        .withEnv("LDAP_ADMIN_PASSWORD", TEST_PASSWORD)
        .withEnv("LDAP_TLS", "false")
        .withExposedPorts(LDAP_PORT)
        .waitingFor(
            Wait.forListeningPort()
                .withStartupTimeout(Duration.ofMinutes(2))
        );

    @DynamicPropertySource
    static void ldapProperties(DynamicPropertyRegistry registry) {
        registry.add(
            "spring.ldap.urls",
            () -> "ldap://" + LDAP.getHost()
                + ":" + LDAP.getMappedPort(LDAP_PORT)
        );
        registry.add(
            "spring.ldap.base",
            () -> "dc=example,dc=org"
        );
        registry.add(
            "spring.ldap.username",
            () -> "cn=admin,dc=example,dc=org"
        );
        registry.add(
            "spring.ldap.password",
            () -> TEST_PASSWORD
        );
    }

    @Autowired
    LdapTemplate ldapTemplate;

    @Test
    void readsRootEntryThroughDynamicConnection() {
        String rootDc = ldapTemplate.lookup(
            "",
            new String[] {"dc"},
            attrs -> String.valueOf(attrs.get("dc").get())
        );

        assertThat(rootDc).isEqualTo("example");
    }

    @Test
    void usesMappedPortNotContainerPort() {
        assertThat(LDAP.getMappedPort(LDAP_PORT)).isPositive();
        assertThat(LDAP.getHost()).isNotBlank();
    }
}
~~~

Đoạn test đọc attribute `dc` của **entry gốc** thông qua `LdapTemplate`; nó không chỉ kiểm tra port đã mở. Với `spring.ldap.base=dc=example,dc=org`, lookup với DN rỗng `""` nhắm tới chính entry base trong quy ước của `ContextSource`.

**Giải thích các điểm kết nối động:**

1. `withExposedPorts(389)` khai báo cổng **bên trong** container; host port được Testcontainers phân bổ ngẫu nhiên.
2. `LDAP.getHost()` cho biết hostname mà JVM test cần dùng. Không giả định trong CI luôn là `localhost`.
3. `LDAP.getMappedPort(389)` lấy cổng **host** tương ứng. Không dùng trực tiếp `389` hoặc một số cổng hardcode ở máy host.
4. `@DynamicPropertySource` trả các giá trị động cho Spring Boot khi khởi tạo kết nối LDAP.
5. `@Container static` có vòng đời thường là **một container cho mỗi test class** với JUnit extension, không phải một container mới cho mỗi phương thức.
6. Phép lookup cuối cùng chứng minh URL, base DN, bind DN, mật khẩu, đường mạng và một thao tác LDAP cơ bản phối hợp thành công.

**Lưu ý readiness:** `Wait.forListeningPort()` chỉ xác nhận listener đã mở; chưa chắc quá trình bootstrap schema/entry đã xong. Nếu image mất thời gian import LDIF hoặc thiết lập tài khoản, bổ sung wait strategy phù hợp với image và kiểm thử bind/lookup có **retry giới hạn** để phân biệt server chưa sẵn sàng với lỗi cấu hình.

### 5.2. Tại sao không gọi `LDAP.start()` trong `@DynamicPropertySource`?

Trong ví dụ đã có `@Container` và `@Testcontainers`, JUnit extension chịu trách nhiệm start/stop. Đặt `LDAP.start()` tùy tiện bên trong supplier gây tác dụng phụ khi Spring resolve property, làm khó kiểm soát vòng đời và lặp lại lỗi.

Nếu chủ động quản lý container bằng `static { LDAP.start(); }`, cần thiết kế cleanup, lifecycle và context cache riêng; **không đồng thời dựa vào hai cơ chế quản lý vòng đời** mà không hiểu hậu quả.

Cũng không nên khởi tạo container trong mỗi lần gọi `registry.add`: lúc đó URL và port có thể thuộc một container khác với container mà test sẽ truy vấn.

### 5.3. Nếu muốn test bằng repository

Giả sử dự án có entity:

~~~java
import javax.naming.Name;
import org.springframework.ldap.odm.annotations.Attribute;
import org.springframework.ldap.odm.annotations.Entry;
import org.springframework.ldap.odm.annotations.Id;

@Entry(
    base = "ou=people",
    objectClasses = {"top", "person", "organizationalPerson", "inetOrgPerson"}
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

    public PersonEntry() {}

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
~~~

Repository:

~~~java
import org.springframework.data.ldap.repository.LdapRepository;

public interface PersonRepository extends LdapRepository<PersonEntry> {
}
~~~

Một test có thể gọi:

~~~java
import javax.naming.ldap.LdapName;

var alice = repository.findById(
    new LdapName("uid=alice,ou=people")
);
assertThat(alice).isPresent();
~~~

Đây là **đoạn sử dụng bên trong test method**, với `repository` là bean `PersonRepository` đã được inject. Nó **chỉ đúng khi** fixture đã khởi tạo `ou=people` và Alice trên container, đồng thời class/repository nằm trong phạm vi component scanning. Image OpenLDAP bootstrap chỉ từ `LDAP_DOMAIN` **không mặc định chứa Alice**. Không coi phép assert ở trên là một phần của smoke test tối thiểu nếu chưa seed dữ liệu.

## 6. Seed dữ liệu thử nghiệm sau khi kết nối đã đúng

### 6.1. Mẫu LDIF cho entry con

Giả sử OpenLDAP image đã tạo `dc=example,dc=org`. Một file LDIF chỉ cần tạo **OU và các entry con**:

~~~ldif
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
~~~

Không import lại root `dc=example,dc=org` nếu image đã tạo entry đó, vì server thường trả `entryAlreadyExists`.

Có thể chọn một trong các cơ chế:

- Copy LDIF vào **đường dẫn bootstrap do image tài liệu hóa**, trước khi container khởi động.
- Gọi `ldapadd` trên container sau khi sẵn sàng, với DN/password chỉ dành cho test.
- Seed qua `LdapTemplate.bind(...)` hoặc API phù hợp trong một bước setup riêng.

**Đừng giả định mọi image LDAP dùng cùng thư mục bootstrap.** Khi đổi image từ OpenLDAP sang LLDAP hoặc server khác, đường dẫn, biến môi trường và schema có thể thay đổi.

### 6.2. Một phép round-trip nhỏ với `LdapTemplate`

Nếu muốn xác minh ứng dụng có thể tạo/read/delete entry trong directory **throwaway** của test, có thể dùng `LdapTemplate` trực tiếp. Ví dụ sau tạo **một OU test riêng** với tên ngẫu nhiên, rồi dọn trong `finally`:

~~~java
import java.util.UUID;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.BasicAttributes;

@Test
void createsAndReadsAnEntryInThrowawayDirectory() {
    String suffix = UUID.randomUUID().toString().replace("-", "");
    String rdn = "ou=it-" + suffix;

    BasicAttributes attributes = new BasicAttributes(true);
    BasicAttribute objectClass = new BasicAttribute("objectClass");
    objectClass.add("top");
    objectClass.add("organizationalUnit");
    attributes.put(objectClass);
    attributes.put("ou", "it-" + suffix);

    // Dùng LDAP test account có quyền add và delete.
    ldapTemplate.bind(rdn, null, attributes);

    try {
        String ou = ldapTemplate.lookup(
            rdn,
            new String[] {"ou"},
            attrs -> String.valueOf(attrs.get("ou").get())
        );
        assertThat(ou).isEqualTo("it-" + suffix);
    } finally {
        ldapTemplate.unbind(rdn);
    }
}
~~~

Đây là ví dụ cần đặt **trong test class có trường `ldapTemplate` được inject**. Nó kiểm tra `ContextSource` dùng đúng directory và thao tác write. Chỉ thực hiện trong môi trường **cho phép xóa test entry**, không dùng trên directory dùng chung. Phải kiểm tra dữ liệu server sau cleanup nếu test thất bại giữa chừng; một `finally` cũng có thể gặp lỗi mạng trong lúc dọn.

Không lạm dụng `@Transactional` để giả định toàn bộ CRUD LDAP tự rollback như database. Các thao tác LDAP trên nhiều entry không có bảo đảm transaction chung nếu server/cơ chế transaction không hỗ trợ.

## 7. Embedded LDAP: khi nào không cần `@DynamicPropertySource`?

Spring Boot có hỗ trợ một **embedded UnboundID LDAP server** cho kiểm thử, khi dependency và các property `spring.ldap.embedded.*` được cấu hình đúng. Trong phương án này, Spring Boot tự thiết lập URL/port cho `ContextSource` nội bộ; **thường không cần tự inject mapped port** bằng `@DynamicPropertySource` như khi dùng Testcontainers.

Ví dụ test dependency:

~~~kotlin
dependencies {
    testImplementation("com.unboundid:unboundid-ldapsdk")
}
~~~

Ví dụ `application-ldap-embedded.yml`:

~~~yaml
spring:
  ldap:
    base: "dc=example,dc=org"
    embedded:
      base-dn: "dc=example,dc=org"
      ldif: "classpath:ldap/test-users.ldif"
      validation:
        enabled: true
~~~

Cần phân biệt:

| Property | Bên nào sử dụng? |
| --- | --- |
| `spring.ldap.embedded.base-dn` | Định nghĩa base/naming context của embedded server |
| `spring.ldap.base` | Base DN của client kết nối tới embedded server |
| `spring.ldap.embedded.ldif` | LDIF để seed dữ liệu kiểm thử |
| `spring.ldap.embedded.port` | Chỉ định port server nhúng nếu có yêu cầu; có thể để framework chọn |
| `spring.ldap.urls` | URL LDAP cho client bên ngoài; trong embedded test tránh ghi đè URL do Boot tự thiết lập |

Nếu đặt một profile `ldap-embedded` và một profile `ldap-container`, **không bật cả hai cơ chế cùng lúc** trong một test nếu không hiểu cơ chế auto-configuration. Ví dụ, `spring.ldap.embedded.base-dn` còn sót từ config khác có thể làm Boot dựng server nhúng và ứng dụng trỏ nhầm endpoint dù `@DynamicPropertySource` cũng đã đăng ký URL.

Một lợi ích của embedded là test mapping DN, schema và filter nhanh mà không cần Docker. Nhưng embedded directory **không chứng minh** toàn bộ hành vi TLS, ACL hoặc controls của LDAP server production; những phần đó cần môi trường tương đương.

## 8. Property precedence và cách tránh ghi đè cấu hình không mong muốn

Trong test Spring Boot, property có thể đến từ nhiều nguồn:

- `application.yml` và file theo profile như `application-ldap-container.yml`.
- Environment variables, JVM system properties và command-line arguments.
- `@TestPropertySource`, `@SpringBootTest(properties=...)`.
- `@DynamicPropertySource` / cơ chế đăng ký property động được Spring Test hỗ trợ.

Với LDAP container test, nên:

1. Để **property động** (`spring.ldap.urls`, và credential được tạo khi provision nếu có) ở **một nơi duy nhất**.
2. Để **property cố định theo test** (`base DN`, một số timeout không phụ thuộc container) ở profile hoặc dynamic registry theo hợp đồng.
3. Không để profile test kế thừa giá trị LDAP production khi chưa có cơ chế bảo vệ.
4. Kiểm tra trường hợp property dynamic bị ghi đè: `@DynamicPropertySource` có precedence cao, nên một giá trị YAML sửa sau đó có thể không tác dụng.
5. Nếu có nhiều `ContextSource` hoặc bean tự tạo, xác minh bean thực sự đọc `spring.ldap.*`, thay vì các property custom khác.

Ví dụ profile:

~~~yaml
# application-ldap-container.yml:
spring:
  ldap:
    base: "dc=example,dc=org"
# urls/username/password được cấp bởi @DynamicPropertySource.
~~~

Không cần tạo giá trị giả `spring.ldap.urls=ldap://localhost:389` trong profile nếu các test luôn dùng registry động. Cấu hình giả đôi khi che giấu việc `@DynamicPropertySource` không được tìm thấy.

### Đừng lẫn `@DynamicPropertySource` với thay đổi bằng `System.setProperty`

~~~java
// Không nên dùng cách này để cấu hình test container.
System.setProperty("spring.ldap.urls", dynamicUrl);
~~~

System properties là trạng thái **toàn tiến trình JVM**. Nếu nhiều test chạy song song hoặc context đã được tạo, chúng có thể dùng sai giá trị hoặc ảnh hưởng test khác. `@DynamicPropertySource` gắn property vào **Spring TestContext của bài test**, dễ kiểm soát hơn.

### `@ServiceConnection` có thay thế được không?

Spring Boot có cơ chế `@ServiceConnection` cho **những service/container type được tích hợp ConnectionDetails tương ứng**. Tuy nhiên, **không mặc định** rằng một `GenericContainer` LDAP sẽ được Spring Boot nhận dạng và tự tạo LDAP connection details. Cần kiểm tra module, phiên bản và cơ chế factory thực tế.

Với một LDAP image tùy chọn, `@DynamicPropertySource` vẫn là cách biểu diễn rõ nhất: ghi tường minh **URL, base DN, bind identity và password** mà ứng dụng mong muốn.

## 9. Vòng đời test và bộ nhớ đệm `ApplicationContext`

### 9.1. Container `static` và test context

Một `@Container static` thường khởi động trước các test method và dừng sau test class. Spring TestContext có thể **cache `ApplicationContext`** để tái sử dụng giữa các lớp test có cấu hình tương đương.

Hai vòng đời này **không đồng nhất**:

~~~text
Class A
  LDAP container A -> hostPort 49173
  Spring ApplicationContext -> ContextSource kết nối port 49173

Class B
  LDAP container B -> hostPort 49184
  Nếu reuse ApplicationContext từ A không phù hợp:
  ContextSource có thể vẫn nhắm port 49173 (container A đã dừng).
~~~

Vì vậy, nếu nhiều lớp test cùng dùng static container khác nhau nhưng được Spring xem là cùng cấu hình context, có thể xảy ra lỗi ngẫu nhiên: class đầu chạy xanh, class sau nhận `Connection refused` hoặc đọc nhầm directory.

Cách xử lý:

- **Chia sẻ một container trong vòng đời toàn bộ nhóm test có cùng cấu hình**, nếu đã có chiến lược seed/reset và quản lý lifecycle đáng tin cậy.
- **Phân tách context rõ ràng** giữa các nhóm test dùng endpoint khác nhau.
- Dùng `@DirtiesContext` khi test context cần được bỏ khỏi cache và tạo lại với property mới. Đây là biện pháp có chi phí khởi động lại; không dùng cho mọi test theo thói quen.
- Không đặt các value động phụ thuộc container từng lớp vào một base class được kế thừa nếu Spring có thể cache context qua các lớp nhưng container đó đã thay đổi.

Tài liệu Spring TestContext cảnh báo riêng: các `@DynamicPropertySource` được kế thừa từ base class nhưng **giá trị động thay đổi giữa các subclass** có thể cần `@DirtiesContext` để bảo đảm mỗi subclass nhận đúng cấu hình.

### 9.2. `@DynamicPropertySource` không phải công cụ đổi URL sau mỗi test

Nếu muốn một test method trỏ vào server A, method khác trỏ server B bằng cách sửa biến toàn cục giữa chừng, các bean đang hoạt động có thể giữ kết nối cũ. Một `LdapContextSource` thường được khởi tạo với property đã resolve; việc đọc supplier về sau không tự cập nhật bean.

Giải pháp là thiết kế hai **ApplicationContext độc lập** hoặc hai `ContextSource` được khai báo/cấu hình rõ ràng khi nghiệp vụ thật sự cần hai directory. Không tự sửa trường `urls` của bean đang được repository sử dụng đồng thời.

### 9.3. Chạy song song

Khi CI chạy nhiều JVM hoặc nhiều test class:

- Cổng host phải **động** (Testcontainers quản lý).
- Fixture/DN của test nên **riêng biệt** hoặc được reset.
- Container nên có **vòng đời rõ ràng**, tránh tái sử dụng không kiểm soát.
- Property không được ghi ở mức JVM chung để tránh ảnh hưởng chéo.
- Nếu các lớp cùng ghi một directory, phải có chiến lược namespace/OU và đồng bộ, hoặc tắt parallelism cho nhóm test đó.

## 10. Bảo mật khi chạy test LDAP

Ví dụ Testcontainers dùng `ldap://` và mật khẩu giả để tập trung vào cơ chế động. **Đó không phải cấu hình production.**

Đối với test LDAPS/StartTLS, cần bổ sung:

- LDAP server hỗ trợ TLS, certificate có SAN phù hợp với hostname mà client kết nối.
- JVM tin cậy **CA kiểm thử đã xác minh**; không dùng `TrustManager` “trust-all”.
- Nếu dùng `ldaps://`, mapped port phải tương ứng với **cổng LDAPS thực** của image (thường 636) chứ không phải vẫn map 389.
- Nếu dùng StartTLS, phải có cơ chế thực hiện StartTLS trước khi bind; `ldap://` không tự nâng cấp TLS.
- Đọc secret từ secret store của môi trường test nếu đó là credential thật của shared test directory. **Không commit mật khẩu production**.

Khi dùng certificate tự ký trong môi trường test, có thể tạo CA riêng cho test rồi cấp server certificate có SAN phù hợp. Không tự tắt hostname verification chỉ vì Testcontainers cấp host động; hãy thiết kế certificate hoặc endpoint cho phù hợp.

Một tài khoản LDAP dùng cho kiểm thử **đọc** nên không có quyền xóa; nếu test cần CRUD, chỉ cấp quyền trên **nhánh test cô lập**. Không chạy `deleteAll()` từ repository vào một directory dùng chung.

## 11. Chẩn đoán lỗi kết nối động

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra/sửa |
| --- | --- | --- |
| `Connection refused` trên `localhost:389` | URL bị hardcode, không dùng mapped port | Kiểm tra `spring.ldap.urls`, dynamic registry và `getMappedPort(389)` |
| `Connection refused` trên mapped port cũ | Container đã dừng nhưng Spring context cache còn dùng kết nối cũ | Xem vòng đời container, `@DirtiesContext` hoặc tổ chức shared container |
| DNS/host lỗi trong CI | Giả định `localhost` thay vì host Testcontainers trả về | Dùng `container.getHost()` |
| Container port mở nhưng bind fail | Bootstrap chưa hoàn tất, wrong credential, server chưa ready | Thêm LDAP-level readiness, kiểm tra log khởi tạo |
| `Invalid credentials` (LDAP code 49) | Sai admin DN/password hoặc account chưa được tạo | So sánh image env, `spring.ldap.username/password`; không thay bằng admin production |
| `noSuchObject` | `spring.ldap.base` sai, root/OU chưa có hoặc DN truyền sai | Đọc naming context, đối chiếu DN tương đối |
| Lấy dữ liệu từ môi trường không mong muốn | Profile test không hoạt động hoặc custom `ContextSource` bỏ qua dynamic properties | Xác nhận profile và bean được inject |
| Test thay YAML nhưng URL không đổi | `@DynamicPropertySource` có precedence cao | Kiểm tra dynamic property đã đăng ký |
| Đọc root được nhưng `findById` rỗng | Fixture user chưa seed hoặc `@Entry`/DN sai | Tách smoke kết nối khỏi test dữ liệu |
| LDAP schema lỗi khi tạo entry | Thiếu `objectClass`, `cn`, `sn`, OU parent | Dùng LDIF/schema đúng và tạo parent trước child |
| TLS/PKIX lỗi | Sai truststore, CA chain, SAN hoặc cổng/protocol | Kiểm tra certificate và truststore thật của JVM |
| Test xanh trên embedded nhưng fail trên container | Khác schema/ACL/vendor controls | Test theo cùng mục tiêu, ghi nhận khác biệt server |

### Chiến lược debug theo thứ tự

1. Xác nhận container thật sự được start và `getMappedPort(...)` có giá trị hợp lệ.
2. Xác nhận cấu hình active profile; bảo đảm không có profile embedded đang kích hoạt ngoài ý muốn.
3. Kiểm tra bean `LdapContextSource` đang dùng URL từ dynamic registry (chỉ ghi URL test và metadata, không ghi password).
4. Thử root lookup bằng `LdapTemplate`, **chưa** dùng entity ODM/repository để loại trừ lỗi mapping.
5. Nếu root lookup thành công, kiểm tra fixture DN/OU/schema rồi thử repository.
6. Nếu chỉ lớp test thứ hai thất bại, điều tra cache `ApplicationContext` và vòng đời `@Container static`.
7. Khi lỗi kết nối xuất hiện trên CI mà không có ở local, kiểm tra Docker/runtime/network, readiness và cách lấy host/mapped port.

## 12. Ma trận kiểm thử nên có trong CI

| Kịch bản | Thiết lập | Kỳ vọng |
| --- | --- | --- |
| Port host ngẫu nhiên | `@Container` + `getMappedPort(389)` | Không phụ thuộc `localhost:389` |
| Host không cố định | `getHost()` | Chạy trên runner tương thích Testcontainers |
| Base DN đúng | Client `dc=example,dc=org`, root hiện diện | Lookup root thành công |
| Base DN sai | Thử với suffix không tồn tại trong môi trường cô lập | Báo lỗi DN, không tự đọc dữ liệu ngoài phạm vi |
| Credential sai | Mật khẩu test không đúng | Bind bị từ chối với lỗi xác thực |
| Directory chưa sẵn sàng | Bootstrap có độ trễ | Readiness có retry giới hạn và fail rõ ràng |
| Fixture user có sẵn | Seed LDIF với Alice | Repository hoặc `LdapTemplate` đọc được UID |
| Tạo/sửa/xóa entry test | Tài khoản có quyền trên OU test | Đọc lại state, cleanup đúng |
| Hai test class với container khác nhau | Tách context/cache | Không còn dùng mapped port cũ |
| Chạy song song | Mỗi class có container và dữ liệu riêng | Không tranh chấp DN/cổng |
| TLS test | CA/cert dành cho test | Bắt tay thành công với cert hợp lệ, fail với CA sai |
| Profile production bị lẫn | Test không nhận secret/URL production | Có guardrail, không tác động production |

Nên dùng `@Tag("ldap-integration")` cho nhóm integration test cần container để CI biết rõ suite nào đã chạy. Nếu Docker không khả dụng, không nên âm thầm bỏ qua suite rồi báo kết quả “toàn bộ test đạt” mà không ghi nhận **skipped/infrastructure failure**.

## 13. Câu hỏi tự kiểm tra

1. Vì sao `spring.ldap.urls=ldap://localhost:389` không đáng tin cậy khi dùng Testcontainers trong CI?
2. `withExposedPorts(389)` khác `getMappedPort(389)` ở điểm nào?
3. `@DynamicPropertySource` cần phương thức có chữ ký thế nào? Tại sao nên dùng `Supplier`?
4. Khi property có trong `application.yml` và `@DynamicPropertySource`, cấu hình nào thường có precedence cao hơn?
5. Vì sao một test root lookup được là bằng chứng về kết nối tốt hơn chỉ assert `container.isRunning()`?
6. `spring.ldap.base` có tự tạo suffix `dc=example,dc=org` trên LDAP server không?
7. Nếu chỉ test `findById("uid=alice,ou=people")` thất bại còn root lookup thành công, cần kiểm tra những gì?
8. Khi dùng Spring Boot embedded UnboundID, có nhất thiết phải tự inject mapped port bằng `@DynamicPropertySource` không?
9. Một test class chạy xanh, test class sau bị `Connection refused` trên port cũ. Hai vòng đời nào cần điều tra?
10. Vì sao thay `System.setProperty` bằng `@DynamicPropertySource` có thể cải thiện cô lập test?
11. `@ServiceConnection` có tự cấu hình `GenericContainer<?>` LDAP bất kỳ không? Bạn cần xác minh điều gì?
12. Khi test LDAPS với mapped port động, cần xử lý SAN/truststore ra sao?
13. Nếu test có quyền ghi, vì sao cần tạo DN/OU riêng và cleanup có kiểm soát?
14. Hãy đề xuất một smoke test phân biệt **kết nối sai endpoint** với **repository entity mapping sai**.

## 14. Tổng kết

**Cấu hình kết nối động** giúp Spring Boot test giao tiếp đúng LDAP server được tạo tại runtime, đặc biệt khi Testcontainers cấp **host và mapped port không cố định**. Với `@DynamicPropertySource`, Spring TestContext đăng ký các property `spring.ldap.*` từ container đang chạy **trước khi** khởi tạo `LdapContextSource`, `LdapTemplate` và repository. Test phải xác nhận kết nối thật bằng bind/lookup, không chỉ kiểm tra container đã start.

Khi dùng embedded UnboundID, Spring Boot thường tự cấp địa chỉ kết nối và không cần inject port thủ công; khi dùng container, phải phân biệt lifecycle Testcontainers với cache `ApplicationContext`. Hãy tách rõ **endpoint**, **base DN**, **bind credential**, **fixture** và **schema/ACL**, bảo vệ secret, kiểm tra TLS nếu cần, và cô lập test khỏi production.

Nhờ các nguyên tắc này, bộ kiểm thử Spring Data LDAP vừa có thể chạy lặp lại trên laptop/CI vừa phát hiện đúng lỗi ở tầng network, bind, DN, filter, repository mapping hoặc hành vi directory.

### Tài liệu tham khảo

- [Spring Framework Reference — `@DynamicPropertySource` và dynamic property registration](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/dynamic-property-sources.html).
- [Spring Framework Javadoc — `DynamicPropertySource`](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/test/context/DynamicPropertySource.html).
- [Spring Boot Reference — LDAP và embedded LDAP](https://docs.spring.io/spring-boot/reference/data/nosql.html).
- [Spring Boot Reference — Testcontainers](https://docs.spring.io/spring-boot/reference/testing/testcontainers.html).
- [Testcontainers for Java — GenericContainer và host/mapped ports](https://java.testcontainers.org/features/networking/).
- [Testcontainers for Java — JUnit Jupiter integration](https://java.testcontainers.org/test_framework_integration/junit_5/).
- [Spring LDAP Reference — Basic Usage](https://docs.spring.io/spring-ldap/reference/basic-usage.html).
- [RFC 4511 — LDAPv3 Protocol](https://www.rfc-editor.org/rfc/rfc4511).
