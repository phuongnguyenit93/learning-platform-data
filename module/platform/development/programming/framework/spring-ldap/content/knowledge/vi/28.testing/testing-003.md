# Embedded LDAP server cho integration test

Trong **Spring LDAP**, kiểm thử đơn vị có thể gọi trực tiếp `AttributesMapper` hoặc giả lập `ContextSource` để kiểm tra cách `LdapTemplate` thực hiện lời gọi JNDI. Tuy nhiên, những phép thử này không cho biết một **LDAP server** có thực sự hiểu filter, phân giải DN, áp dụng scope tìm kiếm, kiểm tra schema và xử lý các thao tác entry hay không. Để kiểm tra đường đi từ mã Java đến thư mục, ta cần **integration test** với một server LDAP hoạt động thật.

Một giải pháp phù hợp trong môi trường phát triển là **embedded LDAP server**: máy chủ LDAP chạy ngay trong tiến trình hoặc vòng đời của bộ kiểm thử, khởi tạo dữ liệu từ fixture, lắng nghe trên cổng tạm và dừng sau khi chạy xong. Bài này sử dụng **UnboundID In-Memory Directory Server** với Spring Boot và JUnit 5 để minh họa cách kiểm thử `LdapTemplate`, tìm kiếm, DN, filter và ghi entry. Đây là một phần của kỹ năng kiểm thử truy cập thư mục an toàn trong module **SPRING_LDAP**, bên cạnh cấu hình `ContextSource`, xác thực, TLS, pooling, xử lý lỗi, `LdapClient` và ODM.

## 1. Embedded LDAP khác gì so với mock?

```text
                    Unit test với mock                 Integration test với embedded LDAP

  Repository / service thật                      Repository / service thật
             │                                              │
             ▼                                              ▼
       LdapTemplate thật                               LdapTemplate thật
             │                                              │
             ▼                                              ▼
   ContextSource / DirContext mock                   LdapContextSource thật
             │                                              │
             ▼                                              ▼
      SearchResult giả                              TCP loopback: cổng ngẫu nhiên
                                                            │
                                                            ▼
                                                In-memory LDAP server thật
                                                            │
                                                            ▼
                                               Entry và schema theo fixture
```

Mock hữu ích để kiểm tra **tham số được gửi** và nhánh xử lý của ứng dụng. Embedded LDAP kiểm tra thêm rằng các thành phần thực sự có thể kết nối, bind, tìm kiếm, đọc/ghi dữ liệu và chuyển kết quả từ JNDI sang đối tượng Java.

| Phạm vi | Mock `ContextSource`/`DirContext` | Embedded LDAP |
| --- | --- | --- |
| Mapping `AttributesMapper` | Có | Có |
| Lệnh `LdapTemplate` tạo đúng base/filter/scope | Kiểm tra lời gọi | Kiểm tra kết quả thực thi |
| Server phân tích filter và thực thi tìm kiếm | Không | Có |
| Truy cập entry theo DN, objectClass và thuộc tính | Giả lập | Có |
| Thao tác `bind`, `modify`, `unbind` | Giả lập lời gọi | Có thể kiểm thử end-to-end |
| Xác thực bằng tài khoản test | Không kiểm chứng bind thật | Có thể kiểm thử |
| Tương thích Active Directory, ACL thực tế, TLS/pooling production | Không | **Không được bảo đảm** |

UnboundID in-memory server là một implementation LDAP tiện dụng cho integration test. Nó không phải bản sao đầy đủ của mọi LDAP server sản xuất; đặc biệt không được suy ra rằng các chính sách Active Directory, overlay OpenLDAP, ACL, referral, matching rule riêng hoặc TLS ở môi trường thực sẽ giống hệt.

## 2. Chuẩn bị dependency và cấu hình test

Ví dụ dùng **Java 17+**, Spring LDAP thông qua Spring Boot, JUnit Jupiter và UnboundID LDAP SDK. Mã đặt trong package `com.example.ldap`. Với dự án có Spring Boot dependency management, Gradle có thể khai báo:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-ldap'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'com.unboundid:unboundid-ldapsdk'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Nếu dự án dùng Maven, các dependency tương ứng là `spring-boot-starter-data-ldap`, `spring-boot-starter-test` (scope `test`) và `com.unboundid:unboundid-ldapsdk` (scope `test`). Phiên bản cần tương thích với Spring Boot BOM hoặc dependency management của dự án.

Spring Boot có các phiên bản hỗ trợ tự động khởi tạo embedded LDAP khi có thư viện UnboundID và nhóm cấu hình `spring.ldap.embedded.*`. Ví dụ sau giả định đang sử dụng phiên bản có cơ chế cấu hình này; nếu dùng Spring LDAP thuần hoặc phiên bản Boot không còn hỗ trợ cơ chế tương ứng, ta có thể tự tạo `InMemoryDirectoryServer` trong vòng đời JUnit (phần 7).

### Cấu hình profile riêng cho integration test

Tạo `src/test/resources/application-test.yml`:

```yaml
spring:
  ldap:
    base: dc=example,dc=org
    username: cn=Directory Manager
    password: test-admin-password
    embedded:
      base-dn: dc=example,dc=org
      ldif: classpath:ldap/people.ldif
      port: 0
      credential:
        username: cn=Directory Manager
        password: test-admin-password
```

Ý nghĩa của từng phần:

- `embedded.base-dn` khai báo naming context của server test: `dc=example,dc=org`.
- `embedded.ldif` trỏ đến dữ liệu mẫu nạp khi server khởi động.
- `embedded.port: 0` yêu cầu sử dụng **cổng động**, tránh va chạm giữa các lần chạy và trong CI.
- `ldap.base` là base của các DN truyền cho `LdapTemplate`. Vì vậy `ou=people` trong truy vấn được hiểu dưới `dc=example,dc=org`.
- Các trường `credential` tạo tài khoản bind test trong embedded server; `ldap.username/password` cho `LdapContextSource` sử dụng thông tin đó. Đây là **credential giả chỉ dành cho test**, không dùng lại trong môi trường chạy thật.

Không đặt `spring.ldap.urls` trỏ đến server công ty trong profile test này. Cấu hình kết nối production không được ghi đè cấu hình nhúng. Khi dùng `@ActiveProfiles("test")`, tài nguyên và thông tin kết nối phải được giải quyết theo profile test.

> **Lưu ý về phiên bản:** các khóa cấu hình embedded là tiện ích do Spring Boot cung cấp, không phải một API của riêng `spring-ldap-core`. Khi thay đổi phiên bản Boot, cần kiểm tra tài liệu cấu hình tương ứng và xác minh test thực sự khởi động server nhúng trước khi tin tưởng kết quả.

## 3. Khai báo dữ liệu LDAP từ LDIF

LDIF (**LDAP Data Interchange Format**) mô tả các entry thông qua DN và thuộc tính. Tạo `src/test/resources/ldap/people.ldif`:

```ldif
dn: dc=example,dc=org
objectClass: top
objectClass: domain
dc: example

dn: ou=people,dc=example,dc=org
objectClass: top
objectClass: organizationalUnit
ou: people

dn: uid=an,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: an
cn: An Nguyen
sn: Nguyen
mail: an@example.org
userPassword: test-user-secret

dn: uid=binh,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: binh
cn: Binh Tran
sn: Tran
mail: binh@example.org
userPassword: another-test-secret

dn: ou=contractors,ou=people,dc=example,dc=org
objectClass: top
objectClass: organizationalUnit
ou: contractors

dn: uid=external,ou=contractors,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: external
cn: External User
sn: User
mail: external@example.org
```

Cấu trúc entry sau khi nạp:

```text
dc=example,dc=org
└── ou=people
    ├── uid=an
    ├── uid=binh
    └── ou=contractors
        └── uid=external
```

Để LDIF nạp ổn định:

1. Entry cha phải xuất hiện trước entry con; DN phải duy nhất.
2. Thuộc tính bắt buộc phải hợp lệ với `objectClass`: `person` yêu cầu `cn` và `sn`.
3. Mỗi entry cách nhau bằng một dòng trống; tránh thừa khoảng trắng trong tên thuộc tính.
4. Trong LDIF chuẩn, giá trị chứa ký tự Unicode ngoài ASCII hoặc một số ký tự đặc biệt cần biểu diễn **Base64** theo cú pháp `cn:: <base64-utf8>`. Ví dụ trên dùng tên ASCII để fixture không phụ thuộc bộ mã khi import.
5. Chỉ dùng dữ liệu giả. Không đưa tài khoản, email hoặc mật khẩu thật vào fixture test.

Fixture này cố ý có một entry nằm sâu hai cấp bên dưới `ou=people` để thấy được khác biệt giữa `ONELEVEL_SCOPE` và `SUBTREE_SCOPE`. Việc thêm entry nested là quan trọng: nếu tất cả người dùng ở ngay dưới `ou=people` thì một test scope có thể thành công dù code đổi sai phạm vi tìm kiếm.

## 4. Kiểm thử tìm kiếm bằng LdapTemplate và server thật

Với ứng dụng Spring Boot đã bật LDAP auto-configuration, `LdapTemplate` có thể được inject vào lớp kiểm thử như một bean thật. Ta dùng `@SpringBootTest` để khởi động context, `@ActiveProfiles("test")` để tải LDIF và kết nối đến embedded server.

Tạo `src/test/java/com/example/ldap/EmbeddedLdapIntegrationTest.java`:

```java
package com.example.ldap;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.ldap.query.LdapQueryBuilder.query;

import java.util.List;
import javax.naming.directory.Attributes;
import javax.naming.directory.SearchControls;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest
@ActiveProfiles("test")
class EmbeddedLdapIntegrationTest {

    @Autowired
    private LdapTemplate ldapTemplate;

    record Person(String uid, String fullName, String email) {}

    private static Person mapPerson(Attributes attributes)
            throws javax.naming.NamingException {
        return new Person(
                (String) attributes.get("uid").get(),
                (String) attributes.get("cn").get(),
                (String) attributes.get("mail").get()
        );
    }

    @Test
    void findsUserByUidAndMapsAttributes() {
        List<Person> found = ldapTemplate.search(
                query()
                        .base("ou=people")
                        .searchScope(SearchControls.SUBTREE_SCOPE)
                        .where("uid").is("an"),
                (AttributesMapper<Person>)
                        EmbeddedLdapIntegrationTest::mapPerson
        );

        assertEquals(
                List.of(new Person("an", "An Nguyen", "an@example.org")),
                found
        );
    }

    @Test
    void returnsEmptyListForUnknownUid() {
        List<String> found = ldapTemplate.search(
                query()
                        .base("ou=people")
                        .where("uid").is("unknown"),
                (AttributesMapper<String>) attributes ->
                        (String) attributes.get("uid").get()
        );

        assertTrue(found.isEmpty());
    }

    @Test
    void distinguishesOneLevelFromSubtreeSearch() {
        List<String> oneLevel = ldapTemplate.search(
                query()
                        .base("ou=people")
                        .searchScope(SearchControls.ONELEVEL_SCOPE)
                        .where("uid").is("external"),
                (AttributesMapper<String>) attributes ->
                        (String) attributes.get("uid").get()
        );

        List<String> subtree = ldapTemplate.search(
                query()
                        .base("ou=people")
                        .searchScope(SearchControls.SUBTREE_SCOPE)
                        .where("uid").is("external"),
                (AttributesMapper<String>) attributes ->
                        (String) attributes.get("uid").get()
        );

        assertTrue(oneLevel.isEmpty());
        assertEquals(List.of("external"), subtree);
    }

    @Test
    void treatsFilterCharactersAsAValueNotAsFilterSyntax() {
        List<String> found = ldapTemplate.search(
                query()
                        .base("ou=people")
                        .where("uid").is("an*)(uid=*"),
                (AttributesMapper<String>) attributes ->
                        (String) attributes.get("uid").get()
        );

        assertTrue(found.isEmpty());
    }
}
```

### Những gì bốn test này thực sự chứng minh

- **Kết quả và mapping:** Spring LDAP kết nối đến server, thực hiện search dưới base DN, nhận `Attributes` và tạo đối tượng `Person`. Nếu sai DN, sai filter, thiếu thuộc tính hoặc mapping sai, test sẽ thất bại.
- **Không có kết quả:** server trả tập rỗng và `LdapTemplate` trả danh sách rỗng cho `uid` không tồn tại.
- **Scope:** với `ONELEVEL_SCOPE`, server chỉ tìm các entry con trực tiếp của `ou=people`; với `SUBTREE_SCOPE`, server duyệt cả `ou=contractors` và tìm được `uid=external`.
- **Escape filter:** chuỗi đầu vào có các ký tự `*`, `(` và `)` được coi là giá trị của `uid` khi dùng `LdapQueryBuilder`. Nó không được diễn giải thành biểu thức LDAP Filter mới.

Điểm khác với test giả lập là các assertion trên dựa vào **kết quả do server LDAP thực tế tính toán**, không phải danh sách cố định mà Mockito được lập trình để trả về. Dù vậy, test vẫn chỉ phản ánh **implementation và schema của embedded server** đang dùng.

## 5. Kiểm thử vòng đời entry: tạo, đọc, xóa

Integration test cũng nên kiểm tra ít nhất một thao tác ghi. Dùng DN riêng cho mỗi lần chạy giúp tránh va chạm giữa các test. Test phải dọn dẹp dữ liệu ngay cả khi assertion thất bại.

Bổ sung các import vào cùng lớp `EmbeddedLdapIntegrationTest`:

```java
import java.util.UUID;
import javax.naming.ldap.LdapName;
import javax.naming.directory.Attribute;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.BasicAttributes;
```

Sau đó thêm method dưới đây vào lớp:

```java
@Test
void createsFindsAndDeletesEntry() throws Exception {
    String uid = "it-" + UUID.randomUUID();
    LdapName dn = new LdapName("uid=" + uid + ",ou=people");

    BasicAttributes attributes = new BasicAttributes(true);
    Attribute objectClasses = new BasicAttribute("objectClass");
    objectClasses.add("top");
    objectClasses.add("person");
    objectClasses.add("organizationalPerson");
    objectClasses.add("inetOrgPerson");

    attributes.put(objectClasses);
    attributes.put("uid", uid);
    attributes.put("cn", "Integration Test");
    attributes.put("sn", "Test");

    ldapTemplate.bind(dn, null, attributes);

    try {
        List<String> found = ldapTemplate.search(
                query()
                        .base("ou=people")
                        .where("uid").is(uid),
                (AttributesMapper<String>) attrs ->
                        (String) attrs.get("uid").get()
        );

        assertEquals(List.of(uid), found);
    } finally {
        ldapTemplate.unbind(dn);
    }

    List<String> afterDelete = ldapTemplate.search(
            query()
                    .base("ou=people")
                    .where("uid").is(uid),
            (AttributesMapper<String>) attrs ->
                    (String) attrs.get("uid").get()
    );

    assertTrue(afterDelete.isEmpty());
}
```

Trong JNDI, `bind(Name, Object, Attributes)` tạo một entry với DN và các thuộc tính đã khai báo. Sau đó truy vấn tìm thấy `uid` mới, `unbind(Name)` xóa entry, và lần tìm kiếm cuối không còn kết quả. Sử dụng DN ngẫu nhiên giúp việc chạy lặp hoặc chạy song song ít đụng nhau hơn; `finally` giúp giảm khả năng để lại dữ liệu bẩn.

**Giới hạn:** nếu đoạn `bind(...)` không thành công vì schema hoặc bind account thiếu quyền, đó là lỗi cấu hình/đầu vào cần điều tra, không nên mock lại `DirContext` để test “đi qua”. Trong hệ thống thật, nhiều thư mục giới hạn quyền ghi theo ACL; UnboundID in-memory server không phải căn cứ khẳng định ACL production đang đúng.

Với test cập nhật thuộc tính, có thể dùng `ldapTemplate.modifyAttributes(...)` cùng `ModificationItem` từ JNDI; sau đó đọc lại giá trị bằng `search` hoặc `lookup`. Nên khôi phục giá trị ban đầu trong `finally` hoặc tạo một entry riêng hoàn toàn cho ca kiểm thử.

## 6. Cô lập fixture để kết quả ổn định

Embedded LDAP thường được khởi động theo **Spring ApplicationContext**. Spring Test có thể cache context giữa các phương thức hoặc lớp test; dữ liệu đã ghi vào server sẽ tiếp tục tồn tại cho đến khi context bị hủy, server được khởi tạo lại hoặc fixture được reset.

| Tình huống | Cách xử lý |
| --- | --- |
| Test chỉ đọc | Dùng LDIF bất biến, tái sử dụng server được |
| Test tạo entry | Tên DN duy nhất, xóa trong `finally` |
| Test sửa entry có sẵn | Lưu giá trị trước khi sửa; khôi phục sau test, hoặc tạo fixture riêng |
| Test xóa entry gốc | Tái nạp fixture hoặc dùng context/server riêng, tránh phụ thuộc thứ tự |
| Nhiều lớp kiểm thử chạy song song | Cổng động `port: 0`; tránh chia sẻ entry có thể ghi |
| Cần reset toàn bộ trạng thái | Tạo ApplicationContext/server mới hoặc tái import LDIF theo thiết kế test |
| Test thất bại giữa chừng | Cleanup có `finally`, kiểm tra dữ liệu tồn dư và log server |

Không nên dựa vào thứ tự chạy của JUnit để test sau sửa dữ liệu do test trước tạo. Cũng không nên để một test phá cấu trúc nền `dc=example,dc=org` hoặc `ou=people` khiến mọi test còn lại thất bại dây chuyền.

Với trường hợp Spring Test context caching khiến các test ghi xung đột, có thể dùng `@DirtiesContext` ở mức phù hợp để buộc tạo context mới. Tuy nhiên đây là thao tác khá tốn thời gian; trước tiên hãy ưu tiên fixture riêng và cleanup rõ ràng.

## 7. Nếu dùng Spring LDAP thuần, không có Spring Boot

Embedded LDAP không phụ thuộc bắt buộc vào Spring Boot. Dự án chỉ dùng `spring-ldap-core` có thể điều khiển trực tiếp UnboundID server trong JUnit 5. Quy trình:

1. Khởi tạo `InMemoryDirectoryServerConfig` với naming context như `dc=example,dc=org`.
2. Cấu hình listener LDAP trên cổng 0, cùng tài khoản bind chỉ dành cho test.
3. Tạo `InMemoryDirectoryServer`, gọi `startListening()`, rồi nạp fixture LDIF.
4. Tạo `LdapContextSource` với URL `ldap://127.0.0.1:<cổng-thực>`, base DN và tài khoản test; gọi `afterPropertiesSet()`.
5. Tạo `LdapTemplate` từ `LdapContextSource` và chạy các integration test đã trình bày.
6. Dừng server bằng `shutDown(true)` và giải phóng context source khi kết thúc vòng đời kiểm thử.

Ví dụ phần khởi tạo cơ bản, nếu fixture nằm trong `src/test/resources/ldap/people.ldif`:

```java
InMemoryDirectoryServerConfig config =
        new InMemoryDirectoryServerConfig("dc=example,dc=org");

config.addAdditionalBindCredentials(
        "cn=Directory Manager", "test-admin-password");
config.setListenerConfigs(
        InMemoryListenerConfig.createLDAPConfig("test", 0));

InMemoryDirectoryServer server = new InMemoryDirectoryServer(config);
server.startListening();
server.importFromLDIF(true, "src/test/resources/ldap/people.ldif");

LdapContextSource source = new LdapContextSource();
source.setUrl("ldap://127.0.0.1:" + server.getListenPort());
source.setBase("dc=example,dc=org");
source.setUserDn("cn=Directory Manager");
source.setPassword("test-admin-password");
source.afterPropertiesSet();

LdapTemplate ldapTemplate = new LdapTemplate(source);

// ... chạy các test với ldapTemplate ...

source.destroy();
server.shutDown(true);
```

Các import liên quan:

```java
import com.unboundid.ldap.listener.InMemoryDirectoryServer;
import com.unboundid.ldap.listener.InMemoryDirectoryServerConfig;
import com.unboundid.ldap.listener.InMemoryListenerConfig;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.core.support.LdapContextSource;
```

Ở đây, `InMemoryListenerConfig.createLDAPConfig("test", 0)` yêu cầu listener dùng cổng động; sau khi `startListening()`, `getListenPort()` trả về cổng thực tế. Ví dụ trên là khung vòng đời; khi đưa vào test thật, nên chuyển phần khởi tạo sang `@BeforeAll`, dừng server và hủy context source trong `@AfterAll` hoặc một JUnit extension, bảo đảm giải phóng tài nguyên cả khi test thất bại. Đường dẫn `src/test/resources/...` cũng cần được xử lý thành đường dẫn có thể đọc trong môi trường chạy kiểm thử thay vì dựa vào working directory nếu công cụ build có cấu hình khác.

## 8. Kiểm thử an toàn: những gì embedded LDAP chưa đủ để kết luận

Một integration test với embedded LDAP mạnh hơn mock ở khả năng thực thi giao thức và phép tìm kiếm, nhưng **không đại diện hoàn toàn cho môi trường production**.

### Xác thực và quyền truy cập

Có thể thử một tài khoản có `userPassword` trong fixture bằng API xác thực của Spring LDAP, nhưng nếu production dùng Active Directory, SASL, LDAP proxy hoặc chính sách lockout thì phải kiểm thử riêng ở môi trường tương thích. Một `bind` thành công trong in-memory server không chứng minh tài khoản production có đúng quyền đọc hoặc sửa entry.

### TLS, pooling và network

Mẫu bài này dùng LDAP qua `127.0.0.1` để tránh tài nguyên ngoài và không cấu hình TLS. Vì vậy nó **không** xác minh certificate trust, hostname verification, StartTLS/LDAPS, timeout, kết nối qua firewall hay hiệu quả của connection pool. Với các yêu cầu đó, dùng môi trường integration hoặc staging cấu hình TLS và pooling tương tự production, với credential riêng cho test.

### Schema, filter và tương thích server

Cú pháp LDAP filter và các thao tác JNDI có thể kiểm tra bằng embedded server, nhưng matching rule chuyên biệt, attribute operational, extension/LDAP control và hành vi sắp xếp kết quả giữa các server có thể khác nhau. Hãy kiểm tra những trường hợp đặc thù đó trên server mục tiêu. Đặc biệt, không dựa vào thứ tự của một tập kết quả LDAP nếu ứng dụng không yêu cầu sort một cách tường minh.

### Xử lý lỗi và recovery

Không thể dùng một server in-memory đơn giản để xác nhận đầy đủ các nhánh đứt kết nối, hết phiên, lỗi chứng chỉ, referral hoặc giới hạn tài nguyên server. Các nhánh xử lý exception ở cấp service vẫn có thể được kiểm thử bằng mock; còn resilience trước sự cố kết nối nên được kiểm thử bằng môi trường có khả năng gây lỗi kiểm soát.

## 9. Quy trình chạy và chẩn đoán lỗi thường gặp

Chạy riêng test khi hoàn tất dependency, fixture và profile:

```bash
./gradlew test --tests "com.example.ldap.EmbeddedLdapIntegrationTest"
```

Hoặc với Maven:

```bash
./mvnw -Dtest=EmbeddedLdapIntegrationTest test
```

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra |
| --- | --- | --- |
| Không khởi động được ApplicationContext | Embedded auto-configuration không hoạt động, thiếu UnboundID hoặc trùng cấu hình connection | Xem dependency, profile test và các thuộc tính `spring.ldap.embedded.*` |
| `NameNotFoundException` | Thiếu entry cha, sai base DN, dùng DN đầy đủ trong API đang yêu cầu DN tương đối | So sánh `ldap.base`, cây DN trong LDIF và query |
| `InvalidNameException` | DN không hợp lệ hoặc escape sai ký tự | Tạo/so sánh DN qua `LdapName` hay `LdapNameBuilder` |
| `AuthenticationException` | Username/password test và credential của embedded server khác nhau | Kiểm tra cặp cấu hình `ldap.username/password` và `embedded.credential.*` |
| Import LDIF thất bại | Schema không hợp lệ, thiếu `sn` hoặc `cn`, entry cha chưa tạo | Đọc lỗi import và sửa đúng entry |
| Kết quả tìm kiếm không như mong đợi | Sai scope, base DN hoặc filter | Dùng fixture phân biệt `ONELEVEL_SCOPE` và `SUBTREE_SCOPE` |
| Test chạy lặp lại bị lỗi entry đã tồn tại | Test ghi không cleanup, context cache tái sử dụng server | Tạo DN duy nhất và xóa trong `finally` |
| Cổng đã được dùng | Chọn cổng cố định khi nhiều suite chạy | Dùng cổng 0, đọc cổng được cấp thực tế |

Khi kiểm tra lỗi, ưu tiên xem **nguyên nhân gốc** của exception từ Spring LDAP/JNDI, nhất là lỗi schema hoặc DN. Một test chỉ bị đổi sang mock để “xanh” sẽ làm mất mục đích integration test là phát hiện sự không khớp giữa ứng dụng và server.

## 10. Bài tập tự thực hành

1. Tạo fixture cho `ou=teams` và entry có thuộc tính `member` nhiều giá trị. Viết test xác minh tìm kiếm nhóm trả đúng danh sách DN thành viên.
2. Sửa một truy vấn từ `SUBTREE_SCOPE` sang `ONELEVEL_SCOPE` rồi quan sát test với `uid=external` thất bại.
3. Thêm test `modifyAttributes(...)` thay đổi `mail` của entry mới tạo, đọc lại rồi xóa entry trong `finally`.
4. Thêm thuộc tính bắt buộc bị thiếu trong một fixture riêng để quan sát server báo lỗi schema (khi schema validation được bật), thay vì chỉ kiểm tra lỗi mapper.
5. Chạy các test nhiều lần và song song trên CI. Giải quyết nếu có va chạm DN hoặc port.
6. Lập danh sách các điểm phụ thuộc LDAP server thật của ứng dụng: bind, ACL, schema đặc thù, referral, TLS, timeout và pooling; xác định bài kiểm thử nào cần chạy trên môi trường gần production.

**Tiêu chí hoàn thành:** người học khởi động được LDAP server nhúng với LDIF, kết nối bằng `LdapContextSource`/`LdapTemplate` thật, chạy các test tìm kiếm và ghi/xóa có cleanup, phân biệt chính xác DN, base và scope, rồi xác định được các giới hạn cần kiểm chứng thêm trên LDAP server của môi trường vận hành.

