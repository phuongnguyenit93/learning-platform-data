# Kiểm thử LDAP/Active Directory với directory thử nghiệm và dữ liệu tổ chức có kiểm soát

## 1. Vì sao cần directory thử nghiệm?

Trong module **Spring Security – authentication**, LDAP và Microsoft Active Directory (AD) thường lưu thông tin định danh trong một cấu trúc phân cấp: người dùng, đơn vị tổ chức (OU), nhóm và các thuộc tính tài khoản. Một lần đăng nhập thành công mới kiểm chứng được một phần nhỏ của tích hợp. Ứng dụng còn phải tìm đúng user, bind với mật khẩu hợp lệ, chuyển membership thành authority, từ chối danh tính không hợp lệ và xử lý lỗi directory mà không cấp quyền quá mức.

Đề bài này tập trung vào **cách kiểm thử có thể tái lập và an toàn**, gồm hai cấp:
1. **Kiểm thử tích hợp LDAP tự động**: chạy một directory in-memory riêng cho bài test; nạp một bộ dữ liệu LDIF giả lập, gọi đúng lớp xác thực LDAP của Spring Security và kiểm tra kết quả.
2. **Kiểm thử tương thích AD có kiểm soát**: chạy ở domain/forest thử nghiệm riêng vì một LDAP server thông dụng **không tái hiện đầy đủ** quy tắc AD như `userPrincipalName`, `sAMAccountName`, trust, nested groups, account lockout, Group Policy hay các quy tắc LDAP signing/channel binding.

Mục tiêu sau bài:
- Phân biệt **authentication** (user có thể bind), **authority mapping** (user có những role nào) và **authorization** (role ấy được phép thực hiện hành động nào).
- Thiết kế cây directory, LDIF fixture, tên nhóm và kịch bản dương/âm một cách có chủ đích.
- Chạy kiểm thử Java 17+ độc lập bằng JUnit 5, UnboundID LDAP SDK và `LdapBindAuthenticationManagerFactory`.
- Biết giới hạn của mô phỏng LDAP và cách tiến hành thử nghiệm AD mà không sử dụng tùy tiện tài khoản/dữ liệu của doanh nghiệp.

## 2. Bốn loại kiểm thử và ranh giới tin cậy

| Loại | Thành phần thực | Kiểm tra được | Chưa chứng minh |
| --- | --- | --- | --- |
| Unit test | Mock `AuthenticationManager`, mapper, policy | Logic chuyển role, thông báo lỗi và quyết định quyền | LDAP search, bind, schema hay kết nối thật |
| Integration test LDAP | LDAP in-memory hoặc OpenLDAP container và Spring Security LDAP | DN/base, bind, tìm group, fixture, xử lý credential không hợp lệ | Hành vi đặc thù của AD, TLS/PKI thực tế, domain controller |
| Integration test AD | AD DS trong domain/forest lab riêng | UPN, `sAMAccountName`, membership, policy, lỗi tài khoản, cấu hình TLS/LDAP theo lab | Chính sách doanh nghiệp trong production nếu lab không đồng nhất |
| Pre-production acceptance | Directory staging do quản trị viên cấp, tài khoản test tách biệt | Cấu hình endpoint, chứng chỉ, ACL, timeout, phối hợp với chính sách môi trường | Quyền tự ý sử dụng production; không phải bảo đảm cho mọi tài khoản thật |

**Nguyên tắc:** test càng gần thực tế càng có chi phí và giới hạn quyền cao hơn. Nhiều bài test LDAP nên tự chạy trên CI với dữ liệu giả; các phép thử AD cần môi trường và lịch vận hành riêng.

Ví dụ một cây directory để kiểm thử:

~~~text
dc=lab,dc=example
├── ou=people
│   ├── uid=alice   (thuộc nhóm readers)
│   └── uid=bob     (không thuộc nhóm readers)
└── ou=groups
    └── cn=readers  (member: DN của alice)
~~~

Trong LDAP, **DN (Distinguished Name)** chỉ vị trí duy nhất của entry trong cây; **base DN** giới hạn vùng tìm kiếm. `ou` là organizational unit; `uid`, `cn` là những thuộc tính được chọn cho fixture này. Cây này chỉ là dữ liệu giả, không đại diện cho cấu trúc OU hay schema bắt buộc của AD thật.

## 3. Tạo fixture tổ chức có kiểm soát

### 3.1. Chọn dữ liệu có mục đích kiểm thử

Một fixture tốt phải có **ít nhất một trường hợp được cấp quyền và một trường hợp bị từ chối quyền**. Ví dụ:

| Entry | Thuộc tính quan trọng | Điều cần kiểm chứng |
| --- | --- | --- |
| `uid=alice,ou=people,...` | `uid=alice`, `userPassword` là mật khẩu test | Bind đúng thành công; thuộc `readers` |
| `uid=bob,ou=people,...` | `uid=bob`, mật khẩu khác Alice | Bind đúng thành công nhưng không tự có `ROLE_READERS` |
| `cn=readers,ou=groups,...` | `objectClass=groupOfNames`, `member=<DN Alice>` | Spring Security ánh xạ membership thành authority |
| Không có `uid=ghost` | Không có entry | Authentication phải thất bại |
| Sai password của Alice | Entry có thật nhưng credential sai | Authentication phải thất bại |

Không sử dụng tên, email, số nhân viên, danh sách nhóm hoặc mật khẩu thật. Với dữ liệu cần đại diện cho cơ cấu tổ chức, **tạo các entry hoàn toàn tổng hợp** và chỉ giữ các quan hệ cần thiết: một user thuộc nhóm A, user khác không thuộc A, user nằm ngoài vùng tìm kiếm, v.v. Khử tên riêng nhưng vẫn giữ email, DN, SID hay log gốc có thể chưa đủ ẩn danh.

### 3.2. LDIF đầy đủ và có thể nạp lại

Tạo file `src/test/resources/fixtures/directory.ldif` như sau. LDIF biểu diễn mỗi entry bằng một khối thuộc tính, các entry cách nhau bởi dòng trống; thứ tự từ base đến OU, user, group giúp việc import rõ ràng.

~~~ldif
dn: dc=lab,dc=example
objectClass: top
objectClass: domain
dc: lab

dn: ou=people,dc=lab,dc=example
objectClass: top
objectClass: organizationalUnit
ou: people

dn: ou=groups,dc=lab,dc=example
objectClass: top
objectClass: organizationalUnit
ou: groups

dn: uid=alice,ou=people,dc=lab,dc=example
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
cn: Alice Demo
sn: Demo
uid: alice
userPassword: alice-test-pass

dn: uid=bob,ou=people,dc=lab,dc=example
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
cn: Bob Demo
sn: Demo
uid: bob
userPassword: bob-test-pass

dn: cn=readers,ou=groups,dc=lab,dc=example
objectClass: top
objectClass: groupOfNames
cn: readers
member: uid=alice,ou=people,dc=lab,dc=example
~~~

**Giải thích các điểm dễ nhầm:**
- `objectClass: inetOrgPerson` dùng cho user LDAP chuẩn; nhóm `groupOfNames` dùng thuộc tính `member` chứa **DN của user**, chứ không phải chuỗi `alice`.
- `userPassword` trong fixture được để dạng rõ chỉ vì directory chỉ chạy cục bộ, dùng tên và mật khẩu giả. Không dùng mẫu này để thiết kế lưu mật khẩu thật; cơ chế mật khẩu production phụ thuộc server và chính sách bảo mật.
- `ou=people` và `ou=groups` là hai vùng phân biệt. Nếu cấu hình search base sai, user hoặc group có thể không tìm thấy dù entry tồn tại.
- Thay đổi một fixture phải đi kèm sửa kỳ vọng test; test không được tự chấp nhận mọi membership mới để “xanh” bằng mọi giá.

## 4. Kiểm thử tích hợp chạy được bằng Java 17+ và JUnit 5

Ví dụ dưới đây là một **project Gradle chỉ phục vụ kiểm thử**, không yêu cầu Spring Boot Web server hay hệ thống AD thật. `LdapBindAuthenticationManagerFactory` và `DefaultLdapAuthoritiesPopulator` là lớp Spring Security được dùng trực tiếp. UnboundID cung cấp LDAP listener ephemeral trong cùng tiến trình test.

Các file:
~~~text
ldap-directory-lab/
├── settings.gradle
├── build.gradle
└── src/test/
    ├── java/demo/LdapDirectoryIntegrationTest.java
    └── resources/fixtures/directory.ldif
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'ldap-directory-lab'
~~~

`build.gradle` (Java 17, các version thư viện đồng bộ bởi Spring Boot BOM 3.3.12):

~~~groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    testImplementation platform('org.springframework.boot:spring-boot-dependencies:3.3.12')
    testImplementation 'org.springframework.security:spring-security-config'
    testImplementation 'org.springframework.security:spring-security-ldap'
    testImplementation 'com.unboundid:unboundid-ldapsdk'
    testImplementation 'org.junit.jupiter:junit-jupiter'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

`src/test/java/demo/LdapDirectoryIntegrationTest.java`:

~~~java
package demo;

import java.net.InetAddress;
import java.nio.file.Path;
import java.util.Set;
import java.util.stream.Collectors;

import com.unboundid.ldap.listener.InMemoryDirectoryServer;
import com.unboundid.ldap.listener.InMemoryDirectoryServerConfig;
import com.unboundid.ldap.listener.InMemoryListenerConfig;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.config.ldap.LdapBindAuthenticationManagerFactory;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.ldap.DefaultSpringSecurityContextSource;
import org.springframework.security.ldap.userdetails.DefaultLdapAuthoritiesPopulator;

import static org.junit.jupiter.api.Assertions.*;

class LdapDirectoryIntegrationTest {

    private static InMemoryDirectoryServer directory;
    private static AuthenticationManager manager;

    @BeforeAll
    static void startDirectory() throws Exception {
        var config = new InMemoryDirectoryServerConfig("dc=lab,dc=example");

        // Chỉ lắng nghe loopback và dùng port 0 để tự chọn cổng trống.
        config.setListenerConfigs(InMemoryListenerConfig.createLDAPConfig(
                "test-ldap",
                InetAddress.getByName("127.0.0.1"),
                0,
                null));

        // Account đặc biệt chỉ tồn tại trong server test, không nằm trong LDIF.
        config.addAdditionalBindCredentials(
                "cn=fixture-reader,dc=lab,dc=example", "lookup-test-only");

        directory = new InMemoryDirectoryServer(config);
        directory.importFromLDIF(
                true,
                Path.of("src/test/resources/fixtures/directory.ldif").toFile());
        directory.startListening();

        // URL gồm địa chỉ listener và base DN; không kết nối directory thật.
        var context = new DefaultSpringSecurityContextSource(
                "ldap://127.0.0.1:" + directory.getListenPort()
                        + "/dc=lab,dc=example");
        context.setUserDn("cn=fixture-reader,dc=lab,dc=example");
        context.setPassword("lookup-test-only");
        context.afterPropertiesSet();

        // Tìm groupOfNames dưới ou=groups theo DN của user.
        var authorities = new DefaultLdapAuthoritiesPopulator(
                context, "ou=groups");
        authorities.setGroupSearchFilter("(member={0})");
        authorities.setGroupRoleAttribute("cn");
        authorities.setRolePrefix("ROLE_");
        authorities.setConvertToUpperCase(true);

        // Bind dưới ou=people: uid=alice,... hoặc uid=bob,...
        var factory = new LdapBindAuthenticationManagerFactory(context);
        factory.setUserDnPatterns("uid={0},ou=people");
        factory.setLdapAuthoritiesPopulator(authorities);
        manager = factory.createAuthenticationManager();
    }

    @AfterAll
    static void stopDirectory() {
        if (directory != null) {
            directory.shutDown(true);
        }
    }

    private static Authentication authenticate(String uid, String password) {
        return manager.authenticate(
                new UsernamePasswordAuthenticationToken(uid, password));
    }

    private static Set<String> authorities(Authentication authentication) {
        return authentication.getAuthorities().stream()
                .map(a -> a.getAuthority())
                .collect(Collectors.toSet());
    }

    @Test
    void validCredentialsAuthenticate() {
        Authentication alice = authenticate("alice", "alice-test-pass");
        assertTrue(alice.isAuthenticated());
    }

    @Test
    void membershipBecomesRoleOnlyForMember() {
        Set<String> aliceRoles =
                authorities(authenticate("alice", "alice-test-pass"));
        Set<String> bobRoles =
                authorities(authenticate("bob", "bob-test-pass"));

        assertTrue(aliceRoles.contains("ROLE_READERS"));
        assertFalse(bobRoles.contains("ROLE_READERS"));
    }

    @Test
    void incorrectPasswordFails() {
        assertThrows(AuthenticationException.class,
                () -> authenticate("alice", "incorrect-password"));
    }

    @Test
    void unknownUserFails() {
        assertThrows(AuthenticationException.class,
                () -> authenticate("ghost", "any-password"));
    }

    @Test
    void anotherUserCannotReuseAlicePassword() {
        assertThrows(AuthenticationException.class,
                () -> authenticate("bob", "alice-test-pass"));
    }
}
~~~

**Chạy:** trong thư mục project, với Gradle đã cài hoặc Gradle Wrapper đã tạo:

~~~bash
gradle test
# Hoặc nếu project có Gradle Wrapper:
./gradlew test
~~~

Trên Windows dùng `gradlew.bat test` khi có wrapper. Kỳ vọng là **5 test đều pass**; Gradle trả exit code 0. Không khẳng định một chuỗi stdout cố định vì Gradle hiển thị log khác nhau theo version, cache và mức logging.

**Giải thích tại sao phép thử có ý nghĩa:**
1. Directory được nạp lại từ LDIF có kiểm soát; không gọi đến LDAP server trên mạng doanh nghiệp.
2. Bind với password đúng/sai được server LDAP thực hiện, không bị stub hay hardcode một kết quả `true`.
3. Spring Security lấy membership bằng `(member={0})`, trong đó `{0}` được thay bằng DN user đã xác thực. Từ `cn=readers`, ví dụ ánh xạ ra `ROLE_READERS`.
4. Cùng một user có thể **đăng nhập được** mà **không có authority** theo nhóm đang xét: Bob không có `ROLE_READERS`. Đó là khác biệt giữa xác thực và phân quyền.
5. Directory lắng nghe ở `127.0.0.1`, port ngẫu nhiên, và bị dừng ở `@AfterAll`. Đây là giao thức LDAP không mã hóa chỉ dùng giữa test process và loopback; kết nối đến LDAP/AD thật phải bảo vệ kênh và xác minh chứng chỉ.

**Giới hạn quan trọng:** project này kiểm thử `AuthenticationManager` và LDAP authority resolution, **không kiểm thử `SecurityFilterChain`, HTTP 401/403 hay các annotation `@PreAuthorize`**. Khi tích hợp trong ứng dụng Spring MVC, bổ sung `MockMvc` hoặc request thật để kiểm tra chính sách URL/method, phiên đăng nhập và việc mapping authority tại lớp web. Với WebFlux, dùng `WebTestClient` cùng cơ chế xác thực mà ứng dụng reactive thực sự cấu hình; không dùng test servlet để kết luận hành vi reactive.

## 5. Bộ tình huống bắt buộc trước khi tin một tích hợp LDAP

| Kịch bản | Input/điều kiện | Kết quả cần kiểm chứng |
| --- | --- | --- |
| Bind thành công | User có thật, mật khẩu đúng | `Authentication.isAuthenticated() == true` |
| Bind thất bại | Sai mật khẩu hoặc user không tồn tại | Phát sinh lỗi xác thực, không cấp session/authority hợp lệ |
| Role đúng | Alice có `member` trong `readers` | Có `ROLE_READERS` |
| Không leo quyền | Bob không là member | Bob không có `ROLE_READERS` dù login thành công |
| Search base giới hạn | User chỉ ở OU khác với `userDnPatterns`/search base | Không được âm thầm tìm sang OU ngoài chính sách |
| Group rename/remove | Đổi `cn`/membership trong fixture test riêng | Authority phản ánh quy tắc mapping và cache đã chủ đích |
| Tên có Unicode/dấu | User/group với thuộc tính được mã hóa LDIF đúng | Chuỗi được đọc/so sánh đúng; không hỏng UTF-8 |
| Ký tự đặc biệt trong input | `(`, `*`, `\` và ký tự cần escape | Không tạo LDAP filter injection; chỉ user mong muốn được tìm |
| Lỗi LDAP | Directory dừng, timeout, sai base, sai bind account | Fail closed; không tự cho phép đăng nhập |
| Cạn kết nối/retry | Directory chậm hoặc mất kết nối ngắn hạn | Timeout và retry có giới hạn; không khóa tài nguyên hay lặp vô hạn |

Không nên dùng một user thật để thử nhiều mật khẩu sai: **AD có thể khóa account** theo chính sách domain. Trong test tự động, chỉ sử dụng tài khoản giả và directory cô lập. Những tình huống làm thay đổi fixture nên khởi động directory riêng hoặc reset toàn bộ dữ liệu sau mỗi test để tránh phụ thuộc thứ tự chạy.

### Filter injection và escaping

LDAP filter là ngôn ngữ biểu thức, không phải chuỗi có thể nối tùy ý. Ví dụ **không an toàn** khi tạo filter từ input:

~~~java
// Chỉ minh họa lỗi, không dùng ở production.
String filter = "(uid=" + suppliedUsername + ")";
~~~

Các ký tự đặc biệt có thể làm thay đổi ý nghĩa filter. Khi cần tìm user bằng thuộc tính thay vì DN pattern, sử dụng API Spring Security chuẩn:

~~~java
// Đoạn cấu hình bổ sung, không phải một chương trình Java độc lập.
factory.setUserSearchBase("ou=people");
factory.setUserSearchFilter("(uid={0})");
~~~

Cơ chế bind/search của Spring Security thay tham số bằng API phù hợp. Tránh tự xây filter hoặc DN bằng nối chuỗi không kiểm soát; khi tự dùng Spring LDAP, dùng `LdapQueryBuilder`/tham số API và quy tắc escape DN/filter tương ứng. Test các input đặc biệt bằng fixture riêng để bảo đảm không mở rộng tập kết quả tìm kiếm.

## 6. Dữ liệu tổ chức có kiểm soát nghĩa là gì?

**Dữ liệu tổng hợp (synthetic):** tạo mới hoàn toàn DN, OU, UPN, group, membership theo kịch bản; không xuất phát từ thông tin của nhân viên. Đây là lựa chọn mặc định cho CI.

**Dữ liệu đã được cấp phép cho staging:** chỉ dùng khi cần kiểm tra cấu trúc/schema đặc thù và có môi trường do quản trị directory quản lý. Xác định trước phạm vi các attribute cần có, quyền truy cập, thời hạn lưu, nơi đặt log và cách xóa sau test. Dùng test account riêng; ưu tiên bản sao sơ đồ quan hệ đã loại dữ liệu định danh thay vì snapshot directory production.

Một quy trình thực tế:

1. **Xác định case trước:** ví dụ “employee thuộc group A phải có quyền đọc, contractor không được có quyền sửa”. Từ yêu cầu đó mới tạo user/group tương ứng.
2. **Định nghĩa schema và fixture:** duy trì LDIF hoặc script IaC trong thư mục test có review; ghi rõ base DN, expected membership, expected authority.
3. **Tách môi trường:** domain test, network/VLAN hoặc container riêng; cấu hình `ldap.url` và credential theo profile `test`; cấm profile test trỏ đến endpoint production.
4. **Giới hạn quyền:** bind/search account chỉ đọc, chỉ các OU/attribute cần thiết; không dùng domain admin, không thay đổi object thuộc tổ chức thật.
5. **Bảo vệ bí mật:** secret staging qua secret manager/biến môi trường; không commit mật khẩu thật, token, certificate private key hoặc bản dump chứa PII.
6. **Quản lý log:** test report ghi username giả, loại lỗi và assertion; không in mật khẩu, toàn bộ DN người thật, credential, ticket, token hay nội dung `userPassword`.
7. **Dọn dẹp và tái lập:** khởi tạo mới cho mỗi job hoặc reset fixture; hủy directory/container, xoá credential tạm, thu hồi quyền, áp dụng retention cho artifact.
8. **Kiểm chứng fail closed:** nếu directory không khả dụng, user không thể được cấp quyền “mặc định”; phân biệt lỗi hệ thống với sai credential ở log nội bộ mà không rò chi tiết tài khoản trong thông báo công khai.

### Một cấu trúc fixture có thể review

~~~text
src/test/resources/fixtures/
├── directory.ldif          # user/group giả đã xác nhận
├── expected-membership.md  # alice -> readers; bob -> none
└── cases.md                # bảng case, quyền kỳ vọng và giới hạn test
~~~

Mỗi fixture nên có owner, lý do tồn tại, phiên bản schema, dữ liệu tối thiểu và cách reset. Không cần lưu “bản sao đầy đủ” hệ thống nhân sự để kiểm tra một phép ánh xạ nhóm.

## 7. Khi cần thử AD thật: giới hạn của giả lập LDAP

AD hỗ trợ LDAP nhưng không đồng nhất với máy chủ LDAP chuẩn. Không kết luận rằng vì fixture `inetOrgPerson`/`groupOfNames` pass thì cấu hình AD chắc chắn đúng.

| Yếu tố AD | Vì sao fixture LDAP thường chưa đủ | Kiểm thử trong AD lab |
| --- | --- | --- |
| Tên đăng nhập | AD có `userPrincipalName`, `sAMAccountName`, domain suffix, đôi khi nhiều dạng login | Đăng nhập bằng dạng tên mà ứng dụng chính thức chấp nhận |
| Provider | `ActiveDirectoryLdapAuthenticationProvider` có quy tắc bind và tìm user riêng | Dùng chính provider/config ứng dụng sẽ triển khai |
| Group | AD dùng `member`/`memberOf`, có nhóm lồng nhau, phạm vi và trust | Test direct/nested membership, group ngoài domain, quy tắc ánh xạ role |
| Account state | Disabled, expired, locked, password expired, logon restriction | Test bằng tài khoản lab và chính sách lockout riêng; xác minh lỗi không cấp quyền |
| Network/TLS | Domain controller, DNS, chứng chỉ, LDAP signing, channel binding | Kiểm tra cấu hình thực của lab, TLS và certificate trust, timeout/failover |
| Replication | Nhiều DC có độ trễ đồng bộ | Kiểm tra việc đổi group/password rồi xác thực trên các DC trong lab |
| ACL | Anonymous search/service account có thể không được đọc mọi attribute | Kiểm chứng service principal quyền đọc tối thiểu |

Spring Security cung cấp `ActiveDirectoryLdapAuthenticationProvider` cho quy ước AD. Mẫu cấu hình **minh họa, không chạy một mình**:

~~~java
// Mẫu cấu hình trong Spring app; cần AD lab và xác thực TLS riêng.
ActiveDirectoryLdapAuthenticationProvider provider =
        new ActiveDirectoryLdapAuthenticationProvider(
                "lab.example", "ldaps://dc1.lab.example:636/");
~~~

Bổ sung search base/filter, chính sách authority và truststore theo mô hình tổ chức; không sao chép URL minh họa thành endpoint thật. Với AD, một số mã lỗi phụ (sub-error) có thể biểu thị locked/disabled/expired; không phụ thuộc việc tất cả server hay cấu hình đều trả một mã cụ thể. Log chi tiết chỉ ở hệ thống nội bộ có kiểm soát, tránh giúp đối tượng bên ngoài dò tài khoản.

**TLS cần được phân biệt:** LDAP đơn thuần trên cổng 389 không tự mã hóa. LDAPS (thường 636) hoặc StartTLS giúp bảo vệ đường truyền nếu xác minh chuỗi chứng chỉ và hostname đúng. LDAP signing chỉ bảo vệ tính toàn vẹn cho một số phiên SASL, không thay TLS để bảo mật simple bind; channel binding có vai trò riêng khi dùng SASL qua TLS. Không vô hiệu hóa certificate validation để “cho test qua”.

## 8. Đưa test vào CI mà vẫn kiểm soát được tổ chức

- **CI mỗi commit/pull request:** unit test + tích hợp UnboundID in-memory; không cần secret và không truy cập directory thật.
- **Môi trường integration riêng:** OpenLDAP container hoặc AD lab với account/credential test được cấp; truy cập qua network riêng, chỉ chạy khi có job và quyền phù hợp.
- **Acceptance trước phát hành:** cùng cấu hình authentication/authority mapping gần production, nhưng endpoint và account phải là staging/test; rà soát TLS, ACL, policy và timeout.
- **Điều kiện chặn release:** không cho chạy tiếp nếu sai credential vẫn đăng nhập được, Bob có quyền nhóm của Alice, lookup vượt OU dự kiến, lỗi directory khiến request được cho phép, hoặc test thật nhắm nhầm endpoint production.

Với CI không hỗ trợ mạng/container, test UnboundID trong ví dụ ở trên vẫn chạy được; không mở port cố định hoặc yêu cầu Docker. Khi dùng Docker, khóa phiên bản image, tạo volume/fixture tạm, hạn chế network và reset trạng thái giữa runs. Đừng để suite đọc một LDAP fixture “sống” được nhiều job tự ý chỉnh sửa.

### Cách đọc lỗi thường gặp

| Triệu chứng | Kiểm tra trước | Hướng xử lý |
| --- | --- | --- |
| User tồn tại nhưng không đăng nhập | DN pattern, `userSearchBase`, bind account, password | Sửa cách tìm user; xác nhận đúng server và OU |
| Bind thành công nhưng thiếu role | `groupSearchBase`, `groupSearchFilter`, `member` chứa full DN, role prefix/case | Kiểm tra mapping và fixture membership |
| Bob bất ngờ có `ROLE_READERS` | Group filter quá rộng, test state rò giữa tests, cache role | Thu hẹp filter, reset fixture, kiểm tra group entry |
| Máy local pass nhưng CI fail | Port cố định, fixture không nằm classpath, version khác, file encoding | Port 0, đường dẫn nhất quán, cố định dependency, UTF-8 |
| Directory lab trả timeout | DNS/route/TLS/truststore, timeout LDAP/JNDI, service account | Phân biệt availability và credential; không fallback allow |
| AD trả lỗi policy | Account disabled/locked, password expired, bind type/signing, TLS | Kiểm thử theo policy của AD lab; không tự thay đổi GPO production |

Không gộp tất cả lỗi thành “mật khẩu sai” trong log nội bộ, vì như vậy khó phát hiện lỗi truststore, tài khoản dịch vụ bị chặn hoặc cấu hình OU sai. Tuy nhiên thông điệp trả cho client nên hạn chế lộ danh tính/chi tiết policy.

## 9. Kiểm tra kết quả và câu hỏi tự luyện

**Case 1.** Alice dùng đúng mật khẩu, Bob dùng đúng mật khẩu. Cả hai `isAuthenticated()` là `true`, nhưng chỉ Alice có `ROLE_READERS`. Có mâu thuẫn không? **Không**: xác thực thành công không đồng nghĩa được cấp quyền nhóm.

**Case 2.** Bob đột nhiên có `ROLE_READERS` sau khi thêm `member: uid=bob,...` vào group trong một fixture khác. Test bị “flaky” nếu suite không reset dữ liệu. Khắc phục bằng directory mới cho từng test/suite hoặc reset trạng thái có kiểm chứng; nếu ứng dụng có role cache, kiểm tra thời điểm invalidation riêng.

**Case 3.** Một test LDAP in-memory pass với `uid`, nhưng user thật đăng nhập AD bằng `user@company.example` lại thất bại. Điều này không chứng minh AD sai: cần test `ActiveDirectoryLdapAuthenticationProvider` và thuộc tính UPN/domain suffix trong AD lab.

**Case 4.** Để kiểm tra account lockout, một job CI dùng account nhân viên thật và lặp 20 mật khẩu sai. Cách này không phù hợp: có thể khóa tài khoản và ghi nhận hành vi xác thực bất thường. Tạo tài khoản chuyên dụng trong AD lab với policy và quyền được duyệt.

**Checklist đạt:**
- [ ] Fixture hoàn toàn giả, có base DN/OU/user/group xác định và quyền kỳ vọng được review.
- [ ] Test có both success/failure; xác thực, authority và authorization được phân biệt.
- [ ] Sai mật khẩu, user không tồn tại và user không thuộc group đều có assertion rõ ràng.
- [ ] Test không kết nối production; cổng/ngữ cảnh được cách ly và teardown sạch.
- [ ] Không sử dụng credential thật hay PII trong source, log, artifact.
- [ ] Test AD riêng cho UPN/`sAMAccountName`, nested group, policy, TLS, replication khi có trong yêu cầu.
- [ ] Mọi lỗi directory đều không cấp quyền vượt quá chính sách.

## 10. Tài liệu tham khảo

- [Spring Security 6.5 – LDAP Authentication](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/ldap.html): bind auth, DN/search filter, authority populator và AD provider.
- [Spring Security API – ActiveDirectoryLdapAuthenticationProvider](https://www.springframework.org/spring-security/reference/6.5/api/java/org/springframework/security/ldap/authentication/ad/ActiveDirectoryLdapAuthenticationProvider.html): cách provider xử lý tên đăng nhập và đặc thù AD.
- [UnboundID – In-Memory Directory Server](https://docs.ldap.com/ldap-sdk/docs/in-memory-directory-server.html): cấu hình server thử nghiệm và import LDIF.
- [UnboundID API – InMemoryDirectoryServer](https://docs.ldap.com/ldap-sdk/docs/javadoc/com/unboundid/ldap/listener/InMemoryDirectoryServer.html): vòng đời và `importFromLDIF`.
- [Microsoft Learn – LDAP signing](https://learn.microsoft.com/en-us/windows-server/identity/ad-ds/ldap-signing) và [LDAP channel binding](https://learn.microsoft.com/en-us/windows-server/identity/ad-ds/ldap-channel-binding): bảo vệ giao tiếp directory trong AD.

**Ghi nhớ:** Một kiểm thử LDAP có giá trị là kiểm thử dựa trên fixture **tối thiểu, có thể tái lập và có quyền kỳ vọng rõ ràng**; khi cần xác nhận hành vi AD riêng, dùng một directory AD thử nghiệm được quản trị và dữ liệu tổ chức có kiểm soát.