# Kiểm thử integration bằng LDAP server cô lập

## 1. Đề bài và kết quả cần đạt

Trong một ứng dụng **SPRING_LDAP**, mã `LdapTemplate` hoặc `LdapClient` có thể vượt qua unit test giả lập nhưng vẫn thất bại khi kết nối một directory thực: DN được ghép sai, filter không escape dữ liệu, `SearchControls` chọn sai scope, schema từ chối thuộc tính, bind dùng DN không tồn tại, hoặc thay đổi entry vi phạm quyền. Vì vậy, trước khi triển khai cần **integration test chạy với một LDAP server riêng biệt, có dữ liệu xác định và được hủy sau khi thử nghiệm**.

Đây là bài **Thực hành tổng hợp** kết nối nhiều kỹ năng trong Spring LDAP: cấu hình `ContextSource`, DN và schema, tìm kiếm theo filter, bind, thao tác entry, TLS, pooling, timeout, xử lý lỗi và kiểm tra quyền tối thiểu.

**Nhiệm vụ:** xây dựng một bộ kiểm thử integration tự động cho service tra cứu và chỉnh sửa thông tin thư mục, kết nối tới **OpenLDAP chạy trong Testcontainers**, không dùng LDAP production, không dùng máy chủ chia sẻ giữa nhiều người và không để dữ liệu test tồn tại sau phiên chạy.

Sau khi hoàn thành, người học phải chứng minh được:

1. Spring Boot khởi tạo `ContextSource`/`LdapTemplate` với URL và credential được cung cấp từ **container do test quản lý**.
2. Test thiết lập fixture LDAP có DN, objectClass và thuộc tính hợp lệ; tìm đúng một entry, phân biệt không tìm thấy với lỗi mạng.
3. Filter được dựng bằng API encode phù hợp, chống LDAP filter injection ở giá trị đầu vào.
4. Một user bind hợp lệ thành công, credential sai bị từ chối và lỗi không bị chuyển thành kết quả tìm kiếm rỗng.
5. Thao tác modify lên **entry test** được xác minh bằng cách đọc lại, không tác động dữ liệu thật.
6. Kiểm thử là độc lập với môi trường của lập trình viên, chạy được trong CI có Docker và thu hồi server/dữ liệu khi hoàn tất.
7. Người học biết **giới hạn** của bộ test LDAP thuần, đồng thời bổ sung kiểm thử riêng cho LDAPS/StartTLS, ACL, pooling và fault injection.

### 1.1. Bối cảnh nghiệp vụ giả định

Một ứng dụng quản lý danh bạ có các chức năng:

- `findCommonName(uid)`: tìm thuộc tính `cn` của người dùng trong `ou=people`.
- `replaceDescription(uid, description)`: cập nhật thuộc tính `description` của một entry cho phép chỉnh sửa.
- `bind(userDn, password)`: xác minh credential của một người dùng trên directory.

Các giá trị DN, user/password và endpoint ở đây đều là **fixture giả**. Môi trường test dùng kết nối LDAP thuần tới container cô lập để đơn giản hóa bước đầu; **production phải dùng LDAPS hoặc StartTLS bắt buộc, có kiểm tra chứng chỉ và hostname**. Bài thực hành có phần mở rộng TLS riêng, không đánh đồng việc test LDAP thuần thành chứng minh kết nối TLS an toàn.

## 2. Chọn mức kiểm thử: mock, embedded hay container?

| Loại test | Điều đang được kiểm tra | Ưu điểm | Giới hạn |
| --- | --- | --- | --- |
| Unit test dùng mock `LdapOperations` | Nhánh logic và cách xử lý exception trong service | Rất nhanh, không cần server | Không kiểm tra protocol, schema, bind, filter thật |
| LDAP **in-memory** như UnboundID | Kết nối LDAP thật trong tiến trình test, thao tác và một phần schema | Khởi động nhanh, không cần Docker | Không đại diện mặc định cho ACL/TLS/replication của OpenLDAP/AD |
| **Testcontainers OpenLDAP** | Tương tác qua network, server LDAP thực, bind, search, modify, schema | Gần hệ thống thật hơn, có vòng đời cô lập | Tốn tài nguyên Docker, image/config khác production |
| Staging directory chuyên dụng | TLS, ACL, topology, referral, policy của loại server đang dùng | Gần production nhất | Phức tạp, dễ bị dùng chung/ô nhiễm nếu thiếu cô lập |

**Lựa chọn chính của bài:** Testcontainers + OpenLDAP cho integration test tự động. Nếu production chạy Microsoft Active Directory, 389 Directory Server hoặc directory đặc thù, cần thêm test tương thích với chính sản phẩm đó; OpenLDAP không bảo đảm hành vi giống nhau về schema, paging, control, password policy, referral và ACL.

Một server “cô lập” phải thỏa **cả ba yếu tố**:

- **Cách ly kết nối:** test lấy địa chỉ từ container, không tái sử dụng `ldap://production-host` hay một `spring.ldap.urls` được người khác cấu hình thủ công.
- **Cách ly dữ liệu:** fixture chỉ tồn tại trong container của test; không dùng dữ liệu nhân viên, nhóm hay mật khẩu thật.
- **Cách ly vòng đời:** test khởi động server riêng, tạo dữ liệu dự đoán được, hủy container sau khi chạy; không dùng chung dữ liệu có thể bị test khác sửa.

## 3. Kiến trúc kiểm thử và luồng dữ liệu

~~~mermaid
flowchart TD
    A["JUnit 5 + Spring Boot Test"] --> B["Testcontainers quản lý OpenLDAP"]
    B --> C["Docker container: LDAP port 389 (lab only)"]
    A --> D["DynamicPropertySource: URL, base, bind credential"]
    D --> E["Spring Boot LDAP AutoConfiguration"]
    E --> F["ContextSource + LdapTemplate"]
    A --> G["Fixture: OU, user entries"]
    G --> F
    A --> H["Assertions: search, injection, bind, modify"]
    H --> I["DirectoryService"]
    I --> F
    F --> C
    A --> J["Kết thúc test → hủy container/fixture"]
~~~

### 3.1. Quy ước DIT trong lab

Chọn base DN `dc=example,dc=org` và một OU dành riêng cho người dùng:

~~~text
dc=example,dc=org
└── ou=people
    ├── uid=alice
    │   ├── cn: Alice Example
    │   ├── sn: Example
    │   ├── uid: alice
    │   └── userPassword: <test-only secret>
    └── uid=bob
        ├── cn: Bob Example
        ├── sn: Example
        ├── uid: bob
        └── description: initial
~~~

DN đầy đủ của Alice là `uid=alice,ou=people,dc=example,dc=org`. Trong Spring LDAP, khi `ContextSource.setBase("dc=example,dc=org")` được cấu hình, các DN truyền vào `LdapTemplate` có thể là **DN tương đối**, chẳng hạn `uid=alice,ou=people`. Việc dùng DN đầy đủ để bind một người dùng khác `ContextSource.getContext(userDn, password)` cần được xét theo đúng API của context source đang dùng.

### 3.2. Tiêu chí một fixture hợp lệ

- Entry gốc có `objectClass: domain` và `dc: example`.
- OU có `objectClass: organizationalUnit` và `ou: people`.
- Entry người dùng có `objectClass: inetOrgPerson`, kèm các lớp cha phù hợp với schema, `cn`, `sn` và `uid`.
- `userPassword` chỉ là giá trị giả dùng ở môi trường test; không được dùng lại trong production.
- Test dùng **một entry cho tra cứu** và **một entry riêng cho modify** để tránh phụ thuộc thứ tự chạy.
- Chạy cùng bộ test nhiều lần phải có kết quả giống nhau; fixture không bị tích lũy qua các lần chạy.

## 4. Phụ thuộc và cấu hình chạy test

### 4.1. Maven với Spring Boot 3.x

Trong một dự án Spring Boot đã quản lý phiên bản bằng BOM phù hợp, bổ sung các dependency cần thiết:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-ldap</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>

    <dependency>
        <groupId>org.testcontainers</groupId>
        <artifactId>junit-jupiter</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Các ví dụ giả định Java 17+, Spring Boot 3.x, Spring LDAP, JUnit Jupiter và Testcontainers tương thích. Cần cấu hình Docker Engine hoặc môi trường container tương thích cho CI. Không để test bị **skip im lặng** khi CI không có Docker nếu integration test là tiêu chí bắt buộc của pipeline.

**Về image:** ví dụ dùng `osixia/openldap:1.5.0` để thể hiện cách cấu hình server LDAP trong lab. Đây là một image minh họa thuộc dòng phát hành cũ, **không phải khuyến nghị bảo mật cho môi trường chạy thật**. Trước khi áp dụng trong CI tổ chức, hãy thay bằng image LDAP đã được kiểm duyệt, kiểm tra nguồn gốc và khóa phiên bản bằng digest để tránh thay đổi ngoài ý muốn. Biến môi trường khởi tạo và cơ chế seed khác nhau giữa các image: cần điều chỉnh đoạn test tương ứng.

### 4.2. Vì sao không ghi URL và credential test cố định trong application.yml?

Nếu một dự án có property `spring.ldap.urls` trỏ đến directory staging hoặc production, việc chạy nhầm integration test có thể sửa dữ liệu thật. Thay vì ghi URL trong YAML chung, test sẽ **tự đăng ký property từ container đã khởi động** bằng `@DynamicPropertySource`.

Property được dùng trong ví dụ:

| Property Spring Boot | Giá trị lấy từ | Mục đích |
| --- | --- | --- |
| `spring.ldap.urls` | Host + port được Testcontainers ánh xạ | Bắt buộc kết nối container |
| `spring.ldap.base` | `dc=example,dc=org` | Base DN của lab |
| `spring.ldap.username` | `cn=admin,dc=example,dc=org` | Account để seed fixture; **không dùng làm service account production** |
| `spring.ldap.password` | Secret giả cài khi tạo container | Chỉ sử dụng trong lab |
| `spring.ldap.base-environment.*` (tùy phiên bản/cách cấu hình) | Timeout JNDI nếu được hỗ trợ | Tránh test kẹt vô hạn |

Trong code mẫu, chúng ta tạo một test application context riêng. Khi chuyển sang dự án hiện hữu, có thể dùng `@SpringBootTest` với cấu hình ứng dụng thật, nhưng **phải** bảo đảm property test ghi đè mọi LDAP endpoint ngoài lab và các bean `ContextSource` custom không bỏ qua `spring.ldap.urls`.

## 5. Mã thực hành: service dùng LdapTemplate

Service dưới đây không chứa bất kỳ địa chỉ LDAP nào. Nó nhận `LdapTemplate` do Spring tạo, dùng `EqualsFilter` để encode input và `LdapNameBuilder` để tạo DN an toàn.

~~~java
import java.util.List;
import java.util.Optional;
import javax.naming.Name;
import javax.naming.directory.Attribute;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;
import javax.naming.directory.SearchControls;

import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.filter.EqualsFilter;
import org.springframework.ldap.support.LdapNameBuilder;

public class DirectoryService {
    private final LdapTemplate ldapTemplate;

    public DirectoryService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public Optional<String> findCommonName(String uid) {
        if (uid == null || uid.isBlank()) {
            throw new IllegalArgumentException("uid is required");
        }

        SearchControls controls = new SearchControls();
        controls.setSearchScope(SearchControls.ONELEVEL_SCOPE);
        controls.setReturningAttributes(new String[] {"cn"});
        controls.setCountLimit(2);
        controls.setTimeLimit(1200);  // ms, chỉ giới hạn search

        String filter = new EqualsFilter("uid", uid).encode();

        List<String> names = ldapTemplate.search(
                "ou=people",
                filter,
                controls,
                (AttributesMapper<String>) attrs -> {
                    Attribute cn = attrs.get("cn");
                    if (cn == null) {
                        throw new IllegalStateException(
                                "cn attribute unavailable");
                    }
                    return String.valueOf(cn.get());
                });

        if (names.size() > 1) {
            throw new IllegalStateException("uid not unique");
        }
        return names.stream().findFirst();
    }

    public void replaceDescription(String uid, String description) {
        // Đây là chính sách cho mã định danh của use case ví dụ;
        // không cho phép caller cung cấp DN hoặc tên thuộc tính tùy ý.
        if (uid == null || !uid.matches("[a-z0-9_-]{1,32}")) {
            throw new IllegalArgumentException("invalid uid");
        }
        if (description == null || description.length() > 128) {
            throw new IllegalArgumentException("invalid description");
        }

        Name dn = LdapNameBuilder.newInstance("ou=people")
                .add("uid", uid)
                .build();

        ModificationItem item = new ModificationItem(
                DirContext.REPLACE_ATTRIBUTE,
                new BasicAttribute("description", description));

        ldapTemplate.modifyAttributes(dn, new ModificationItem[] {item});
    }
}
~~~

**Điểm kỹ thuật cần hiểu:**

- `SearchControls.ONELEVEL_SCOPE` chỉ xét entry con trực tiếp của `ou=people`. Nó không tìm trong mọi OU lồng nhau; nếu DIT thực tế khác, thiết kế query phải thay đổi có chủ đích.
- `EqualsFilter` escape dữ liệu đầu vào theo cú pháp LDAP filter, không nối `"(uid=" + uid + ")"` trực tiếp.
- `setCountLimit(2)` cho phép phát hiện các kết quả trùng `uid` không hợp lệ theo yêu cầu nghiệp vụ; không nên âm thầm lấy phần tử đầu khi dữ liệu bất nhất.
- `setTimeLimit(1200)` là giới hạn tìm kiếm từ JNDI/server, **không phải deadline tuyệt đối** bao gồm DNS, TCP, bind và mapping.
- `LdapNameBuilder` xây DN bằng RDN, tránh nối các phần tử của DN bằng chuỗi nhận từ người dùng.
- `replaceDescription` chỉ cho phép sửa thuộc tính được viết cố định trong code. Quyền thật vẫn do ACL trên directory quyết định; kiểm tra input không thay thế kiểm tra quyền.
- Lỗi LDAP không bị chuyển thành `Optional.empty()`. Kết quả trống của tìm kiếm hợp lệ và exception do LDAP unavailable là hai tình huống khác nhau.

## 6. Bộ integration test dùng Testcontainers và JUnit 5

Ví dụ sau trình bày **một test class tự chứa**. Nó tạo LDAP container, đăng ký các property cho Spring Boot, seed fixture sau khi Spring context sẵn sàng, chạy các assertions rồi để Testcontainers hủy container.

Khai báo một lớp test ở `src/test/java/.../DirectoryIntegrationTest.java`; thay package và imports cho phù hợp dự án.

~~~java
import java.util.List;
import java.util.Optional;

import javax.naming.Name;
import javax.naming.directory.Attributes;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.BasicAttributes;
import javax.naming.directory.DirContext;

import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.TestInstance;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.ldap.AuthenticationException;
import org.springframework.ldap.core.ContextSource;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;
import org.springframework.ldap.support.LdapUtils;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.containers.wait.strategy.Wait;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.junit.jupiter.api.Assertions.*;

@Testcontainers
@SpringBootTest(classes = DirectoryIntegrationTest.TestApplication.class)
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
class DirectoryIntegrationTest {

    // Chỉ dùng cho container giả lập, không tái sử dụng ở môi trường khác.
    private static final String LAB_ADMIN_PASSWORD =
            "lab-only-admin-password";
    private static final String LAB_USER_PASSWORD =
            "lab-only-user-password";

    private static final String USER_DN =
            "uid=alice,ou=people,dc=example,dc=org";

    @Container
    static final GenericContainer<?> LDAP =
            new GenericContainer<>("osixia/openldap:1.5.0")
                    .withEnv("LDAP_ORGANISATION", "Example Lab")
                    .withEnv("LDAP_DOMAIN", "example.org")
                    .withEnv("LDAP_ADMIN_PASSWORD", LAB_ADMIN_PASSWORD)
                    .withEnv("LDAP_TLS", "false") // Chỉ dành cho lab cô lập!
                    .withExposedPorts(389)
                    .waitingFor(Wait.forListeningPort());

    @DynamicPropertySource
    static void ldapProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.ldap.urls",
                () -> "ldap://" + LDAP.getHost() +
                        ":" + LDAP.getMappedPort(389));
        registry.add("spring.ldap.base",
                () -> "dc=example,dc=org");
        registry.add("spring.ldap.username",
                () -> "cn=admin,dc=example,dc=org");
        registry.add("spring.ldap.password",
                () -> LAB_ADMIN_PASSWORD);
    }

    @Autowired LdapTemplate ldapTemplate;
    @Autowired ContextSource contextSource;
    @Autowired DirectoryService directoryService;

    @BeforeAll
    void seedDirectory() {
        // Image test tạo sẵn dc=example,dc=org từ LDAP_DOMAIN.
        ldapTemplate.bind(
                LdapNameBuilder.newInstance("ou=people").build(),
                null,
                organizationalUnit("people"));

        ldapTemplate.bind(
                LdapNameBuilder.newInstance("uid=alice,ou=people").build(),
                null,
                person("alice", "Alice Example", LAB_USER_PASSWORD));

        ldapTemplate.bind(
                LdapNameBuilder.newInstance("uid=bob,ou=people").build(),
                null,
                person("bob", "Bob Example", LAB_USER_PASSWORD));
    }

    @Test
    void findsUserByUid() {
        assertEquals(
                Optional.of("Alice Example"),
                directoryService.findCommonName("alice"));
    }

    @Test
    void returnsEmptyWhenSearchHasNoMatches() {
        assertEquals(
                Optional.empty(),
                directoryService.findCommonName("unknown"));
    }

    @Test
    void escapesFilterInjectionPayload() {
        // Giá trị được coi là một uid literal, không thành OR/AND filter.
        assertEquals(
                Optional.empty(),
                directoryService.findCommonName("alice)(uid=*)"));
        assertEquals(
                Optional.of("Alice Example"),
                directoryService.findCommonName("alice"));
    }

    @Test
    void rejectsWrongBindPassword() {
        assertThrows(AuthenticationException.class, () -> {
            DirContext context = contextSource.getContext(
                    USER_DN, "wrong-lab-password");
            try {
                fail("A wrong password must not bind successfully");
            } finally {
                LdapUtils.closeContext(context);
            }
        });
    }

    @Test
    void allowsCorrectUserBind() {
        DirContext context = contextSource.getContext(
                USER_DN, LAB_USER_PASSWORD);
        try {
            assertNotNull(context);
        } finally {
            LdapUtils.closeContext(context);
        }
    }

    @Test
    void modifiesOnlyTheTestEntryAndReadsItBack() {
        directoryService.replaceDescription("bob", "updated by test");

        Name dn = LdapNameBuilder
                .newInstance("uid=bob,ou=people").build();
        String description = ldapTemplate.lookup(
                dn,
                (org.springframework.ldap.core.AttributesMapper<String>)
                        attrs -> (String) attrs.get("description").get());

        assertEquals("updated by test", description);
    }

    private static Attributes organizationalUnit(String ou) {
        BasicAttributes attributes = new BasicAttributes(true);
        BasicAttribute classes = new BasicAttribute("objectClass");
        classes.add("top");
        classes.add("organizationalUnit");
        attributes.put(classes);
        attributes.put("ou", ou);
        return attributes;
    }

    private static Attributes person(
            String uid, String cn, String password) {
        BasicAttributes attributes = new BasicAttributes(true);
        BasicAttribute classes = new BasicAttribute("objectClass");
        classes.add("top");
        classes.add("person");
        classes.add("organizationalPerson");
        classes.add("inetOrgPerson");
        attributes.put(classes);
        attributes.put("uid", uid);
        attributes.put("cn", cn);
        attributes.put("sn", "Example");
        attributes.put("userPassword", password);
        return attributes;
    }

    @SpringBootConfiguration
    @EnableAutoConfiguration
    @Import(DirectoryService.class)
    static class TestApplication {}
}
~~~

**Lưu ý khi áp dụng:** đoạn code `DirectoryService` ở mục trước phải nằm trong source path mà test truy cập được; `@Import(DirectoryService.class)` đăng ký nó cho test application context. `@SpringBootTest` nạp cấu hình LDAP auto-configuration nhờ các dependency và `spring.ldap.*`. Nếu ứng dụng đã tự khai báo `LdapContextSource` hoặc `LdapTemplate`, hãy kiểm tra thực tế bean nào được inject: **custom bean có thể không sử dụng các property động của test**.

### 6.1. Điều kiện đúng và hạn chế của mẫu code

- Docker cần được khởi động trước khi test. `@Container` quản lý vòng đời LDAP container trong phạm vi test class.
- `@DynamicPropertySource` lấy host và port đã được Testcontainers cấp, tránh xung đột cổng 389 trên máy chạy test.
- `@BeforeAll` với `@TestInstance(PER_CLASS)` cho phép seed fixture bằng `LdapTemplate` được Spring inject.
- Image OpenLDAP mẫu sẽ tạo base suffix từ `LDAP_DOMAIN`. Nếu chọn image khác, phải xác nhận suffix và cấu hình admin account thực tế.
- Test modify chỉ sửa entry `bob`; các test còn lại không phụ thuộc thuộc tính `description` của Bob. Khi thêm test khác, cần tránh fixture dùng chung bị thay đổi theo thứ tự chạy.
- `Wait.forListeningPort()` chỉ xác minh TCP listener, không chứng minh LDAP server đã **sẵn sàng bind**. Trong CI nghiêm ngặt, nên dùng readiness check bằng **LDAP bind/search có timeout hữu hạn** hoặc wait strategy phù hợp image để tránh flakiness khi server còn khởi tạo.
- Đoạn test dùng admin DN để seed và thao tác ví dụ. Điều này chỉ phù hợp cho **lab**; test ACL phải sử dụng một tài khoản read-only/least-privilege khác, không lấy thành công dưới admin làm bằng chứng phân quyền đúng.
- Không chạy class này song song với class khác dùng chung state nếu chuyển sang chiến lược tái sử dụng container; bài mẫu mặc định tạo một server riêng cho class.

### 6.2. Kết quả kiểm thử mong đợi

| Ca | Input/kịch bản | Kết quả cần khẳng định |
| --- | --- | --- |
| I1 | `uid=alice` | Tìm đúng `cn=Alice Example` |
| I2 | `uid=unknown` | Trả `Optional.empty()`, không ném lỗi |
| I3 | `uid=alice)(uid=*)` | Không tìm thấy; không làm filter bị biến nghĩa |
| I4 | Bind Alice bằng password sai | LDAP từ chối, test bắt exception xác thực |
| I5 | Bind Alice bằng password giả hợp lệ | Context được tạo thành công và được đóng |
| I6 | Modify `description` của Bob | Giá trị đọc lại khớp dữ liệu mới |
| I7 | Gọi method với `uid` rỗng | Validation từ chối sớm, không gửi LDAP request |
| I8 | Gửi giá trị `uid` chứa dấu phân cách DN cho modify | Validation từ chối, không sửa entry khác |
| I9 | Test chạy lại từ đầu | Fixture mới và kết quả giống nhau |
| I10 | Test kết thúc | Container và dữ liệu test được thu hồi |

Ở mức integration, nên bổ sung assertion có ý nghĩa theo nghiệp vụ và mã lỗi, thay vì chỉ kiểm tra “không có exception”. Khi bắt exception, không kiểm tra text message nguyên vẹn vì nội dung message có thể khác theo JNDI provider/LDAP server và chứa dữ liệu cần tránh log.

## 7. Phân biệt positive test, negative test và test an toàn

### 7.1. Search và LDAP filter injection

Hai kiểm thử tối thiểu cho search phải có:

1. **Positive:** một giá trị `uid` hợp lệ trả đúng entry duy nhất.
2. **Negative:** một giá trị chứa các ký tự điều khiển filter như `*`, `(`, `)` hoặc `\` được encode thành **giá trị dữ liệu literal**, không chuyển thành một phần cấu trúc filter mới.

Không kiểm tra an toàn chỉ bằng cách tìm trong log xem filter có ký tự escape; phải thực hiện query trên server và **khẳng định không trả dữ liệu ngoài ý muốn**. Đặt fixture khác `alice` giúp phát hiện một filter độc hại vô tình chuyển thành wildcard hoặc OR query.

Ví dụ nguy hiểm cần tránh:

~~~java
// Sai: ghép thẳng giá trị do người dùng nhập vào cú pháp filter.
String unsafe = "(uid=" + untrustedUid + ")";

// Đúng: builder sẽ encode ký tự đặc biệt của giá trị.
String safe = new org.springframework.ldap.filter.EqualsFilter(
        "uid", untrustedUid).encode();
~~~

**Phân biệt filter với DN:** `EqualsFilter` giải quyết việc escape **giá trị filter**, không dùng để xây DN. Nếu code nhận RDN từ input, dùng `LdapNameBuilder`/`LdapName` và kiểm tra scope nghiệp vụ; không ghép raw DN bằng dấu phẩy.

### 7.2. Bind và xác thực

Một lần bind là kiểm chứng credential đối với danh tính trên directory. Đối với credential sai, Spring LDAP có thể ánh xạ `javax.naming.AuthenticationException` thành `org.springframework.ldap.AuthenticationException`; test cần kiểm tra đúng lớp exception thực tế của stack đang dùng hoặc nhóm lỗi đã chuẩn hóa tại adapter.

Không retry credential sai trong test hoặc production: retry có thể kích hoạt account lockout, tạo tải và che giấu lỗi nhập liệu. Khi test bind, **không ghi password hoặc DN thực** vào metric label, trace hoặc log. Các hằng số trong code mẫu là secret giả chỉ dành cho container.

### 7.3. Modify và trạng thái không chắc chắn

Test modify thành công phải:

1. Chỉ tác động entry giả đã seed trong container.
2. Gửi thay đổi tới đúng DN dự kiến.
3. Đọc lại thuộc tính bằng một truy vấn khác và so sánh.
4. Không tự động retry nếu xảy ra timeout sau khi đã gửi modify: server có thể đã commit nhưng client mất response.

Nếu muốn kiểm tra idempotency hoặc optimistic concurrency, cần bổ sung cơ chế/version phù hợp server và schema. Test thành công dưới admin **không** chứng minh một tài khoản dịch vụ có quyền tối thiểu cũng được phép modify.

## 8. Kiểm tra phân quyền tối thiểu: cần cấu hình ACL riêng

OpenLDAP container chạy bằng admin DN cho phép tạo fixture thuận tiện, nhưng **không thể dùng admin để khẳng định ACL của ứng dụng**. Một test quyền tối thiểu phải tạo ít nhất:

- **Service reader:** có thể search/lookup những thuộc tính cần thiết dưới `ou=people`.
- **Service writer:** chỉ được modify một thuộc tính trên subtree/entry test được duyệt.
- **Unauthorized identity:** không được đọc thuộc tính nhạy cảm hoặc sửa entry vượt quyền.

Có thể dùng LDIF/ACL config được cung cấp cho **LDAP server test** khi khởi tạo container. Cách khai báo ACL phụ thuộc image và server, nên không tự giả định một image mặc định đã có chính sách này.

| Test ACL | Bind identity | Operation | Kỳ vọng |
| --- | --- | --- | --- |
| A1 | Reader | Search `uid` trong `ou=people` | Thành công |
| A2 | Reader | Modify `description` | Bị từ chối quyền |
| A3 | Writer giới hạn | Modify `description` của entry test được phép | Thành công |
| A4 | Writer giới hạn | Modify `userPassword` hoặc entry ngoài phạm vi | Bị từ chối quyền |
| A5 | Anonymous | Search thuộc tính nhạy cảm | Bị chặn theo ACL test |
| A6 | Sai password | Bind | Authentication failure |

**Lưu ý LDAP ACL:** một số directory có thể che entry/attribute bị cấm bằng cách trả “không tìm thấy” hoặc thuộc tính bị bỏ qua, thay vì ném luôn lỗi `insufficientAccessRights`. Vì vậy, assertion phải dựa vào **chính sách đã cấu hình và trạng thái dữ liệu quan sát được**, không chỉ mong đợi một exception code 50 ở mọi tình huống.

### 8.1. Cách nâng cấp bộ test ACL

1. Tạo LDIF test với account reader/writer dưới OU service riêng.
2. Cấu hình ACL của test server cho các mục tiêu và thuộc tính cụ thể.
3. Tạo `ContextSource`/`LdapTemplate` riêng cho reader hoặc writer, dùng bind DN/password của chúng.
4. Thử các phép đọc/ghi được phép và bị cấm; đọc lại dữ liệu bằng identity kiểm chứng có thẩm quyền.
5. Nếu test thay đổi ACL, chạy trên container mới hoặc reset cấu hình, không phụ thuộc test khác.

Không cho account thử nghiệm reader/writer quyền admin chỉ để test “xanh”. Nếu ACL production chạy trên Active Directory hoặc sản phẩm khác, cần thêm môi trường test cùng loại để kiểm chứng semantics thật.

## 9. Kiểm thử LDAPS/StartTLS: cô lập vẫn phải xác minh TLS

Bài mẫu dùng `ldap://...:389` trong container lab, **chưa kiểm chứng TLS**. Để kiểm thử bảo mật kết nối, cần tạo một **test suite riêng** với directory được cấu hình TLS hợp lệ.

### 9.1. Các thành phần cần chuẩn bị

| Thành phần | Chức năng |
| --- | --- |
| Test CA / root certificate | Ký server certificate của LDAP lab |
| Server certificate | Có SAN/hostname phù hợp endpoint mà client dùng |
| Server private key | Nằm trong container/server test, không đưa vào ứng dụng |
| JVM truststore hoặc SSL context test | Chỉ tin CA lab đã chuẩn bị |
| LDAPS endpoint hoặc StartTLS listener | Buộc tạo kênh TLS trước khi bind |
| Client config | Không cho phép fallback sang bind không mã hóa |

Testcontainers thường ánh xạ cổng và hostname khác DNS gốc. Nếu certificate chỉ có SAN `ldap.example.org` nhưng JVM thực sự kết nối tới `localhost` hoặc tên host khác, hostname verification có thể thất bại. **Không sửa bằng cách tắt hostname verification.** Thay vào đó, cấu hình test hostname/SAN và đường kết nối sao cho khớp, hoặc dùng một mạng/alias DNS dành cho lab với certificate hợp lệ.

### 9.2. Ma trận test TLS

| Ca | Điều kiện | Kỳ vọng |
| --- | --- | --- |
| T1 | CA test được JVM tin, SAN khớp | LDAPS handshake + bind/search thành công |
| T2 | CA không được tin | TLS handshake bị từ chối |
| T3 | Chứng chỉ hết hạn/chưa hiệu lực | Kết nối mới bị từ chối theo cơ chế validation |
| T4 | SAN không khớp hostname | Hostname verification không chấp nhận |
| T5 | StartTLS thành công | TLS upgrade hoàn tất **trước** khi gửi credential |
| T6 | StartTLS không được hỗ trợ hoặc handshake lỗi | Fail closed; không thực hiện simple bind không mã hóa |
| T7 | TLS connection cũ còn trong pool sau cert rotation | Probe tạo **kết nối mới** phát hiện chính xác trust/certificate mới |

**Một khác biệt quan trọng:** đổi `spring.ldap.urls` thành `ldaps://...` không tự cung cấp CA hoặc truststore đúng. Với StartTLS, cách cấu hình/khởi tạo của Spring LDAP phụ thuộc vào chiến lược authentication/context và server; không mặc định rằng URL `ldap://` tự kích hoạt StartTLS. Test phải xác minh thực tế handshake và không có credential gửi trước TLS.

## 10. Timeout, pooling và lỗi mạng: mở rộng integration test

Một server cô lập cho phép mô phỏng lỗi một cách an toàn mà không làm ảnh hưởng directory thật. Tuy nhiên, bài test thường quy chỉ nên kiểm tra nghiệp vụ chính; những test fault injection và performance có thể chạy ở suite riêng, có timeout tổng thể và cleanup chắc chắn.

### 10.1. Timeout theo tầng

| Tầng | Biện pháp thường dùng | Chú ý |
| --- | --- | --- |
| TCP connect | JNDI `com.sun.jndi.ldap.connect.timeout`, mili giây | Không phải deadline toàn request |
| LDAP response/read | JNDI `com.sun.jndi.ldap.read.timeout`, mili giây | Một search nhiều response có thể kéo dài hơn một read timeout |
| Search | `SearchControls.setTimeLimit(ms)` | Search limit không gồm toàn bộ setup/conversion |
| Pool borrow | Timeout của pool đang dùng | Không được kiểm soát chỉ bằng JNDI read timeout |
| Test method | JUnit `@Timeout` hoặc timeout của build/CI | Có thể không hủy được mọi blocking I/O bên dưới ngay lập tức |

Ví dụ cấu hình JNDI ở `LdapContextSource` cho một môi trường test tùy chỉnh:

~~~java
LdapContextSource source = new LdapContextSource();
source.setUrl(containerLdapUrl);
source.setBase("dc=example,dc=org");
source.setUserDn("cn=admin,dc=example,dc=org");
source.setPassword(testOnlyPassword);
source.setPooled(false);
source.setBaseEnvironmentProperties(java.util.Map.of(
        "com.sun.jndi.ldap.connect.timeout", "700",
        "com.sun.jndi.ldap.read.timeout", "1200"));
source.afterPropertiesSet();

LdapTemplate ldapTemplate = new LdapTemplate(source);
~~~

`containerLdapUrl` và `testOnlyPassword` là các biến do test lấy từ môi trường container/fixture; **không đặt endpoint production vào đây**. Mẫu cấu hình này dùng trực tiếp `LdapContextSource` khi không có Spring container quản lý lifecycle; nếu trong `@SpringBootTest` đã có bean tương ứng, nên dùng cấu hình bean test thay vì tạo context source trùng mà không rõ instance nào đang dùng.

### 10.2. Các bài thử lỗi mạng có điều kiện

- **Container bị ngắt trước connect:** xác minh lỗi kết nối được phân loại là network failure và test không chờ vô hạn.
- **Proxy giữ socket nhưng trì hoãn response:** xác minh read timeout thực sự được kích hoạt theo provider đang dùng.
- **Pool trả connection cũ sau idle:** thử cơ chế validation, eviction và reconnect của đúng pool.
- **Search theo filter thiếu index trong dữ liệu giả:** ghi nhận latency và giới hạn tìm kiếm, nhưng không đoán năng lực production server từ số liệu lab.
- **Read-only retry:** dùng backoff, jitter, max attempts và deadline; mỗi attempt phải qua giới hạn tải.
- **Modify khi mất response:** **không tự động gửi lại**; kiểm tra trạng thái entry theo phương án rõ ràng.

Có thể đặt proxy lỗi mạng như Toxiproxy trước container trong một suite nâng cao, nhưng không cần đưa mọi fault injection vào class kiểm thử smoke ở mục 6. **Không dùng cổng thật hoặc firewall production** để tạo điều kiện lỗi.

### 10.3. Kiểm thử pooling

Test `setPooled(true)` của JNDI và `PoolingContextSource` là hai trường hợp khác nhau. Với pool có API đo được, khẳng định giới hạn active/idle, borrow timeout và hành vi loại connection stale. Không suy ra rằng tìm kiếm thành công nhiều lần đồng nghĩa pool đã tái sử dụng context.

Một test pool tốt phải có:

1. Capacity và borrow wait có giới hạn;
2. Nhiều client tasks cùng mượn connection;
3. Lỗi do connection chết hoặc bị server đóng;
4. Assertion connection được trả/loại bỏ đúng cách và không vượt số lượng đã cấu hình;
5. Timeout test hữu hạn, cleanup executor và container sau khi chạy.

Không tăng số threads vô hạn để “kiểm tra tải”. Với StartTLS, cần kiểm chứng riêng khả năng tương thích của cơ chế pool và vòng đời TLS.

## 11. Phân lớp kiểm thử để tránh flakiness

Một bộ test integration chất lượng thường có nhiều cấp:

| Nhóm | Mục đích | Khi nào chạy |
| --- | --- | --- |
| **Fast unit** | Validation, filter builder, mapping lỗi, policy retry | Mọi commit |
| **Container smoke** | ContextSource, schema, bind, search, modify với OpenLDAP | PR/merge, CI có Docker |
| **Security/TLS/ACL** | LDAPS/StartTLS, chứng chỉ, quyền tối thiểu, negative tests | PR nhạy cảm, CI bảo mật hoặc trước release |
| **Failure/pool** | Timeout, retry, idle reconnect, connection churn | Pipeline định kỳ hoặc trước release |
| **Staging compatibility** | Kiểm chứng server/vendor và topology gần production | Trước nâng version, rotation, thay schema |
| **Performance/soak** | Saturation, p95/p99, pool utilization | Kế hoạch kiểm thử có kiểm soát |

**Không nhầm tính ổn định với việc bỏ assertion.** Test có thể flaky vì server chưa sẵn sàng, port chưa mở, fixture dùng chung, timeout quá gắt hoặc container không đủ tài nguyên. Hãy khắc phục tại ranh giới tương ứng thay vì thêm `Thread.sleep(10000)` tùy tiện vào mọi test.

### 11.1. Chiến lược fixture

- Seed fixture theo test class/container và không chia sẻ dữ liệu mutable giữa các class.
- Nếu nhiều test thay đổi cùng một entry, dùng **entry riêng theo từng ca** hoặc reset trạng thái trước mỗi ca.
- Gắn ID fixture bằng tên cố định trong container mới, không dùng `uid` của người dùng thật.
- Cleanup qua vòng đời Testcontainers; khi CI mất kết nối Docker hoặc tiến trình bị kill, cần cơ chế dọn container của runner và chính sách tài nguyên phù hợp.
- Khi cần debug thất bại, có thể giữ log và dump đã làm sạch thông tin nhạy cảm; **không xuất raw LDAP entry, password hoặc JNDI BER trace**.

### 11.2. Anti-pattern cần tránh

| Anti-pattern | Hậu quả | Cách thay |
| --- | --- | --- |
| Test dùng LDAP staging hoặc production | Thao tác ghi gây hỏng dữ liệu thật | Testcontainers và endpoint động |
| Test chỉ mock `LdapTemplate` rồi gọi là integration | Không xác minh schema/bind/network | Thêm ít nhất một real LDAP server test |
| Test đặt URL cứng ở `application.yml` chung | Có thể kết nối sai môi trường | `@DynamicPropertySource` hoặc profile test cách ly |
| Dùng admin để khẳng định ACL tối thiểu | Kết quả “xanh” sai ý nghĩa | Tài khoản thử riêng với policy ACL rõ |
| Bỏ xác minh TLS vì certificate test tự ký | Che lỗi cấu hình chứng chỉ | Test CA/SAN/truststore đúng |
| Bắt mọi `Exception` rồi trả danh sách rỗng | Che lỗi mạng và auth | Phân loại lỗi; kết quả rỗng chỉ khi search hợp lệ |
| Retry mọi LDAP write sau timeout | Có thể thực thi thay đổi hai lần | Xác minh trạng thái/thiết kế idempotency |
| Chạy Testcontainers theo một Docker image `latest` | Kết quả CI thay đổi khó kiểm soát | Chốt image digest và cập nhật chủ động |
| Bật `com.sun.jndi.ldap.trace.ber` trong CI log mặc định | Có thể lộ credential và dữ liệu entry | Log loại thao tác và nhóm lỗi an toàn |
| Dùng `Thread.sleep` cố định để chờ LDAP | Flaky, tăng thời gian pipeline | Readiness probe thực và timeout hữu hạn |

## 12. Chạy trong CI và thu thập bằng chứng

### 12.1. Lệnh chạy kiểm thử

Với dự án Maven có Docker Engine sẵn sàng và dependency đã khai báo:

~~~bash
# Chạy riêng test class, không chạy thử trên directory thật.
mvn -Dtest=DirectoryIntegrationTest test

# Chạy toàn bộ test suite đã cấu hình.
mvn test
~~~

Các lệnh trên là hướng dẫn cho môi trường dự án của người học; **bài viết không thực thi những lệnh này trên workspace được giao**. Nếu dùng Gradle, cấu hình JUnit Platform và dependency tương đương rồi chạy task test của dự án.

Trong CI, runner phải có quyền Docker hoặc một Testcontainers environment được tổ chức cho phép. Không tự bật privileged container nếu chính sách CI không chấp nhận. Kiểm tra giới hạn CPU/RAM, thời gian pull image, nguồn image đáng tin cậy, chế độ dọn tài nguyên và chính sách network egress.

### 12.2. Giới hạn bảo mật cho container test

- Không mount credential production hoặc host directory vào LDAP test container.
- Không expose cổng LDAP lab ra mạng công cộng; chỉ dùng cổng được ánh xạ cho runner có quyền.
- Không mở anonymous write hoặc TLS insecure trong bất kỳ môi trường ngoài lab.
- Không ghi secret giả và fixture nhạy cảm vào console nếu log sẽ lưu lâu dài.
- Nếu cần chạy test trong một môi trường nhiều tenant, sử dụng Docker daemon/runner được cách ly phù hợp và policy image scan.
- Một Docker container được quản lý không đồng nghĩa cấu hình directory luôn an toàn; vẫn phải quản lý lifecycle, ACL và dữ liệu giả.

### 12.3. Bằng chứng cần nộp

Người học có thể trình bày một báo cáo ngắn gồm:

| Hạng mục | Bằng chứng |
| --- | --- |
| Server cô lập | Testcontainers container ID tạm hoặc log khởi tạo đã làm sạch |
| Config động | URL test được lấy từ mapped port; không có production host |
| Fixture | Sơ đồ DIT và các objectClass/attribute cần thiết |
| Search | Kết quả Alice và zero-result case |
| Filter injection | Test case với dấu ngoặc và wildcard vẫn không trả entry trái ý |
| Bind | Positive/negative test, không ghi password |
| Modify | Entry Bob thay đổi, đọc lại chính xác |
| Security extensions | Ma trận TLS/ACL, trạng thái các ca đã chạy hoặc chưa chạy |
| Pipeline | Kết quả test pass/fail, thời gian và cách cleanup |
| Điều tra lỗi | Nguyên nhân, fix, test tái hiện (nếu có) |

**Không ghi nhận PASS cho TLS/ACL chỉ vì các test mục 6 chạy thành công**: class đó cố ý dùng LDAP thuần và admin để tập trung vào logic integration cơ bản. Báo cáo phải phân biệt rõ **đã kiểm chứng** với **bài thử mở rộng được đề xuất**.

## 13. Bài tập nâng cao

### 13.1. Chuyển sang LdapClient hoặc ODM

Giữ nguyên LDAP container và fixture, thay adapter truy cập:

- Dùng `LdapClient` để xây query với API builder an toàn.
- Dùng ODM để ánh xạ entry `inetOrgPerson` thành object và kiểm tra mapping attribute, DN và objectClass.
- Giữ nguyên những assertion cấp nghiệp vụ: tìm đúng uid, không tìm thấy, chống injection, cập nhật đúng entry, phân loại lỗi.

**Không viết lại cả fixture chỉ để đổi API** nếu hành vi directory mong muốn không đổi. Bằng cách giữ chung kịch bản và chuyển adapter, có thể so sánh API mới với `LdapTemplate` một cách khách quan.

### 13.2. Thêm kiểm thử thay đổi schema và objectClass

Tạo một ca cố ghi entry thiếu thuộc tính bắt buộc như `sn` đối với `person/inetOrgPerson`, sau đó khẳng định OpenLDAP từ chối theo schema. Dùng negative assertion trên server test thực tế và xác minh không có entry bị thêm dở dang.

Một ca khác có thể cố modify một attribute bị giới hạn theo schema hoặc ACL. Phân biệt rõ **schema violation** với **access denied**; hai loại lỗi yêu cầu hành động xử lý khác nhau.

### 13.3. Tạo test time budget

Một API danh bạ có ngân sách 3 giây. Thiết kế test fault proxy tạo độ trễ ở một LDAP search:

- `connect.timeout` ví dụ 700 ms;
- `read.timeout` ví dụ 1200 ms;
- `SearchControls.setTimeLimit` ví dụ 900 ms;
- retry tối đa 2 lần cho phép đọc, với backoff có jitter;
- xác nhận phương thức không bắt đầu attempt mới khi không đủ ngân sách.

**Không coi các timeout này là đảm bảo tổng thời gian chính xác**: một attempt có thể gồm nhiều giai đoạn hoặc response. Cần đo end-to-end bằng clock đơn điệu và phân biệt timeout do LDAP provider với deadline của request/test.

### 13.4. So sánh container với directory thật

Sau khi bộ test OpenLDAP ổn định, tổ chức có thể duy trì một **staging directory riêng cùng sản phẩm với production**, có chứng chỉ, ACL, index, replication và referral tương tự. Chạy những kịch bản đã chuẩn hóa ở môi trường đó nhưng **không ghi vào dữ liệu sản xuất**. Điều này phát hiện khác biệt server/vendor mà OpenLDAP container đơn giản không mô phỏng.

## 14. Checklist hoàn thành

- [ ] Có LDAP server **cô lập**, vòng đời được Testcontainers quản lý.
- [ ] `spring.ldap.urls` và credential lấy từ container/test fixture; không trỏ tới server thật.
- [ ] Base DN, OU, objectClass, `cn`, `sn`, `uid` và credential test hợp lệ.
- [ ] `LdapTemplate` được tạo với `ContextSource` thực và thực hiện search qua network.
- [ ] Search theo uid có positive, no-result và filter injection negative tests.
- [ ] Bind có cả credential đúng và sai, context được đóng sau khi dùng.
- [ ] Modify chỉ sửa entry lab cho phép và **đọc lại** để kiểm chứng.
- [ ] Test không phụ thuộc thứ tự thực thi, dữ liệu mutable không bị dùng chung sai cách.
- [ ] Đã kiểm tra readiness bằng LDAP operation hữu hạn nếu startup listener chưa đủ ổn định.
- [ ] Không dùng admin để kết luận ACL tối thiểu đã đúng; có suite ACL riêng nếu cần.
- [ ] Không coi LDAP thuần trong container là bằng chứng LDAPS/StartTLS an toàn; có test TLS riêng.
- [ ] Với pool, timeout hoặc retry, có suite riêng để kiểm thử lỗi mạng và quản lý tài nguyên.
- [ ] CI dùng image và phiên bản được kiểm duyệt, container được dọn sau test.
- [ ] Log, metric và trace không chứa user DN, LDAP filter thực, password hoặc entry attributes nhạy cảm.
- [ ] Báo cáo PASS/FAIL ghi rõ ca đã chạy, ca chưa triển khai và giới hạn của môi trường giả lập.

**Kết luận:** integration test có giá trị khi nó thực sự đi qua **Spring LDAP → network → LDAP server độc lập → dữ liệu fixture → assertions**. Testcontainers đem lại môi trường tái tạo được cho search, bind và modify; các bước mở rộng về TLS, ACL, pooling và lỗi mạng giúp hoàn thiện bằng chứng an toàn. Nhờ tách biệt dữ liệu và vòng đời, người học có thể thử cả tình huống thành công lẫn thất bại mà không tác động directory của tổ chức.
