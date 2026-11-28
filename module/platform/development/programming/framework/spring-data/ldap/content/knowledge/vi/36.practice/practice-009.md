# Viết kiểm thử tích hợp và mô phỏng lỗi kết nối

Trong **SPRING_DATA_LDAP**, ứng dụng Java dùng Spring Data LDAP repository, Spring LDAP ODM và `LdapTemplate` để truy cập directory theo DN (*Distinguished Name*), `objectClass` và schema. Unit test có thể xác nhận mapper hoặc service xử lý đúng một object giả lập, nhưng chưa chứng minh ứng dụng thực sự Bind, gửi LDAP Search, ánh xạ attribute hay xử lý lỗi từ directory server.

Ở bài thực hành này, bạn sẽ dựng một LDAP server nhúng trong tiến trình test, nạp dữ liệu giả, kết nối bằng `LdapContextSource` và viết integration test với `LdapTemplate`. Sau khi kiểm tra luồng bình thường, bạn chủ động dừng server để mô phỏng mất kết nối và xác minh Spring LDAP chuyển lỗi JNDI thành `CommunicationException`. Một tình huống dùng sai mật khẩu giúp phân biệt lỗi mạng với lỗi xác thực.

**Kết quả cần đạt:** có bộ test tự chạy, không phụ thuộc LDAP server bên ngoài, bao phủ search, CRUD, filter an toàn, Bind sai thông tin và server ngừng hoạt động.

## 1. Bối cảnh và yêu cầu thực hành

Bạn đang xây dựng dịch vụ tra cứu nhân viên. Directory test có base DN:

```text
dc=example,dc=org
└── ou=people
    ├── uid=lan
    │   ├── objectClass: inetOrgPerson
    │   ├── cn: Lan Nguyen
    │   ├── sn: Nguyen
    │   └── mail: lan@example.org
    └── uid=binh
        ├── objectClass: inetOrgPerson
        ├── cn: Binh Tran
        ├── sn: Tran
        └── mail: binh@example.org
```

Service cần tìm nhân viên theo `uid`, tạo entry mới, thay đổi `mail`, xóa entry và báo lỗi rõ khi directory không thể truy cập.

Hãy chia test thành các nhóm:

| Nhóm | Điều cần chứng minh |
|---|---|
| Search | Filter và base DN trả đúng entry |
| Mapping | Attribute LDAP được ánh xạ sang Java object |
| CRUD | Tạo, đọc, cập nhật và xóa entry hoạt động qua LDAP |
| Filter safety | Giá trị đầu vào đặc biệt không thể biến thành một filter khác |
| Authentication | Bind sai password tạo lỗi xác thực |
| Connectivity | Server dừng tạo lỗi giao tiếp, không bị coi là kết quả rỗng |
| Cleanup | Mỗi test có fixture riêng và không ảnh hưởng test kế tiếp |

## 2. Chuẩn bị dependency kiểm thử

Ví dụ dùng Gradle và JUnit 5:

```kotlin
dependencies {
    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("com.unboundid:unboundid-ldapsdk:7.0.6")
}
```

Nếu dự án không dùng Spring Boot, thay `spring-boot-starter-test` bằng các dependency test JUnit Jupiter và AssertJ mà dự án đang quản lý. Spring LDAP core và Spring Data LDAP đã có trong dependency chính của module; không thêm một phiên bản Spring LDAP khác chỉ để chạy test.

UnboundID LDAP SDK cung cấp `InMemoryDirectoryServer`, một LDAP server nhúng hỗ trợ các thao tác LDAP phổ biến. Server có thể được tạo, nạp dữ liệu, mở listener trên cổng tự chọn và dừng ngay trong test. Cách này cho phép kiểm tra client LDAP qua kết nối mạng loopback thực tế mà không cần cài một directory server riêng.

Không cần dùng cổng cố định như `389` hoặc `1389`. Hãy để server chọn cổng trống tự động, sau đó đọc cổng thực tế qua `getListenPort()`.

## 3. Dựng LDAP server cho mỗi test

Tạo class `PersonDirectoryIntegrationTest`. Mỗi test sẽ có một server mới và dữ liệu cố định. Cách này ngăn test dừng server làm hỏng những test khác.

### 3.1. Tạo fixture

```java
import com.unboundid.ldap.listener.InMemoryDirectoryServer;
import com.unboundid.ldap.listener.InMemoryDirectoryServerConfig;

import javax.naming.directory.BasicAttribute;
import javax.naming.directory.BasicAttributes;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.springframework.ldap.query.LdapQueryBuilder.query;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import org.springframework.ldap.AuthenticationException;
import org.springframework.ldap.CommunicationException;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.core.support.LdapContextSource;

class PersonDirectoryIntegrationTest {

    private static final String BASE_DN = "dc=example,dc=org";
    private static final String ADMIN_DN = "cn=test-admin,dc=example,dc=org";
    private static final String ADMIN_PASSWORD = "test-only-password";

    private InMemoryDirectoryServer server;
    private LdapContextSource contextSource;
    private LdapTemplate ldapTemplate;

    @BeforeEach
    void startDirectory() throws Exception {
        InMemoryDirectoryServerConfig config =
                new InMemoryDirectoryServerConfig(BASE_DN);
        config.addAdditionalBindCredentials(ADMIN_DN, ADMIN_PASSWORD);

        server = new InMemoryDirectoryServer(config);

        server.add(
                "dn: dc=example,dc=org",
                "objectClass: top",
                "objectClass: domain",
                "dc: example");

        server.add(
                "dn: ou=people,dc=example,dc=org",
                "objectClass: top",
                "objectClass: organizationalUnit",
                "ou: people");

        server.add(
                "dn: uid=lan,ou=people,dc=example,dc=org",
                "objectClass: top",
                "objectClass: person",
                "objectClass: organizationalPerson",
                "objectClass: inetOrgPerson",
                "uid: lan",
                "cn: Lan Nguyen",
                "sn: Nguyen",
                "mail: lan@example.org");

        server.add(
                "dn: uid=binh,ou=people,dc=example,dc=org",
                "objectClass: top",
                "objectClass: person",
                "objectClass: organizationalPerson",
                "objectClass: inetOrgPerson",
                "uid: binh",
                "cn: Binh Tran",
                "sn: Tran",
                "mail: binh@example.org");

        server.startListening();

        contextSource = new LdapContextSource();
        contextSource.setUrl(
                "ldap://127.0.0.1:" + server.getListenPort());
        contextSource.setBase(BASE_DN);
        contextSource.setUserDn(ADMIN_DN);
        contextSource.setPassword(ADMIN_PASSWORD);
        contextSource.setPooled(false);
        contextSource.afterPropertiesSet();

        ldapTemplate = new LdapTemplate(contextSource);
    }

    @AfterEach
    void stopDirectory() {
        if (server != null) {
            server.shutDown(true);
        }
    }
}
```

Các method test ở những phần tiếp theo được thêm vào bên trong `PersonDirectoryIntegrationTest` này; chúng dùng chung fixture và các static assertion import ở đầu class.

Các chi tiết quan trọng:

- `InMemoryDirectoryServerConfig` khai báo naming context gốc.
- `addAdditionalBindCredentials` thêm một cặp DN/password dành riêng cho test.
- `server.add(...)` nạp từng entry bằng LDIF.
- `startListening()` mở LDAP listener; `getListenPort()` trả về cổng đã chọn.
- `LdapContextSource` trỏ đến loopback và dùng đúng base DN.
- `setPooled(false)` giúp test lỗi dừng server không vô tình tái sử dụng một kết nối đã mở từ trước.
- `@AfterEach` dừng server để giải phóng listener sau từng test.

Password trong ví dụ chỉ là credential giả của directory nhúng. Không dùng password production trong test, log hoặc file fixture.

### 3.2. Vì sao phải dùng server thật trong tiến trình test?

Mock `LdapTemplate` có thể kiểm tra service phản ứng ra sao khi một method ném exception. Nhưng mock không kiểm tra được:

- JNDI có kết nối được đến LDAP endpoint hay không.
- Bind DN/password có được server chấp nhận không.
- Filter có đúng cú pháp LDAP không.
- Attribute có được trả và mapper có đọc được không.
- Server dừng giữa môi trường test thì client nhận exception nào.

Embedded server xử lý các request LDAP thật qua socket loopback. Nó phù hợp cho integration test nhanh, có dữ liệu kiểm soát và dễ lặp lại.

## 4. Viết integration test cho Search và mapping

Định nghĩa một kiểu dữ liệu chỉ giữ các thuộc tính service cần:

```java
record PersonView(String uid, String cn, String mail) {}
```

Thêm test tìm `uid=lan`:

```java
@Test
void findsPersonByUid() {
    AttributesMapper<PersonView> mapper = attrs ->
            new PersonView(
                    (String) attrs.get("uid").get(),
                    (String) attrs.get("cn").get(),
                    (String) attrs.get("mail").get());

    var people = ldapTemplate.search(
            "ou=people",
            "(&(objectClass=inetOrgPerson)(uid=lan))",
            mapper);

    assertThat(people).containsExactly(
            new PersonView("lan", "Lan Nguyen", "lan@example.org"));
}
```

Test này đi qua toàn bộ đường đi:

1. `LdapTemplate` lấy một LDAP context từ `LdapContextSource`.
2. Client gửi SearchRequest với base `ou=people` và filter đã khai báo.
3. Server đánh giá filter và trả `SearchResultEntry`.
4. `AttributesMapper` chuyển các attribute sang `PersonView`.
5. AssertJ kiểm tra object nhận được.

Tiếp theo, kiểm tra một filter hợp lệ nhưng không match entry:

```java
@Test
void returnsEmptyListWhenNoEntryMatches() {
    var people = ldapTemplate.search(
            "ou=people",
            "(uid=missing)",
            attrs -> (String) attrs.get("uid").get());

    assertThat(people).isEmpty();
}
```

Kết quả rỗng trong test này là hành vi bình thường: base DN tồn tại, filter hợp lệ và không có entry nào match. Hãy giữ trường hợp này tách biệt với lỗi không thể kết nối LDAP.

## 5. Kiểm thử CRUD qua LdapTemplate

Tạo một entry mới trong OU `people`, đọc lại, cập nhật `mail`, rồi xóa entry.

```java
@Test
void createsUpdatesAndDeletesPerson() {
    BasicAttributes attributes = new BasicAttributes(true);

    BasicAttribute objectClasses = new BasicAttribute("objectClass");
    objectClasses.add("top");
    objectClasses.add("person");
    objectClasses.add("organizationalPerson");
    objectClasses.add("inetOrgPerson");

    attributes.put(objectClasses);
    attributes.put("uid", "minh");
    attributes.put("cn", "Minh Tran");
    attributes.put("sn", "Tran");

    String relativeDn = "uid=minh,ou=people";

    // Create
    ldapTemplate.bind(relativeDn, null, attributes);

    var created = ldapTemplate.search(
            "ou=people",
            "(uid=minh)",
            attrs -> (String) attrs.get("cn").get());

    assertThat(created).containsExactly("Minh Tran");

    // Update
    ModificationItem replaceMail = new ModificationItem(
            DirContext.REPLACE_ATTRIBUTE,
            new BasicAttribute("mail", "minh@example.org"));

    ldapTemplate.modifyAttributes(
            relativeDn,
            new ModificationItem[]{replaceMail});

    var updated = ldapTemplate.search(
            "ou=people",
            "(uid=minh)",
            attrs -> (String) attrs.get("mail").get());

    assertThat(updated).containsExactly("minh@example.org");

    // Delete
    ldapTemplate.unbind(relativeDn);

    var deleted = ldapTemplate.search(
            "ou=people",
            "(uid=minh)",
            attrs -> (String) attrs.get("uid").get());

    assertThat(deleted).isEmpty();
}
```

DN truyền vào `LdapTemplate` ở ví dụ là DN tương đối so với base đã cấu hình trong `LdapContextSource`. DN đầy đủ của entry là `uid=minh,ou=people,dc=example,dc=org`.

`bind` tạo entry mới và sẽ lỗi nếu DN đã tồn tại. `modifyAttributes` chỉ thay đổi attribute được chỉ định. `unbind` xóa entry lá. Hãy giữ các thao tác trong cùng test fixture để kết quả không phụ thuộc thứ tự chạy test.

## 6. Kiểm thử filter an toàn với giá trị đầu vào đặc biệt

Không nối chuỗi trực tiếp từ input bên ngoài vào LDAP filter:

```java
String filter = "(uid=" + userInput + ")";
ldapTemplate.search("ou=people", filter, mapper);
```

Nếu `userInput` chứa ký tự filter đặc biệt như `*`, `(`, `)`, dấu gạch chéo ngược hoặc NUL, filter có thể thay đổi ý nghĩa.

Hãy dùng `LdapQueryBuilder` để giá trị assertion được encode:

```java
@Test
void treatsInputAsAnAssertionValue() {
    var ldapQuery = query()
            .base("ou=people")
            .where("uid").is("*)(uid=*)");

    var results = ldapTemplate.search(
            ldapQuery,
            attrs -> (String) attrs.get("uid").get());

    assertThat(results).isEmpty();
}
```

Test này xác nhận chuỗi đặc biệt được coi là giá trị tìm kiếm. Nó không được biến thành filter mới có thể match tất cả nhân viên. Nếu service có nhiều loại query, hãy viết test tương tự cho từng input được đưa vào assertion value.

## 7. Mô phỏng lỗi kết nối bằng cách dừng LDAP server

Đây là phần trọng tâm của bài thực hành.

Một test có thể nhận list rỗng khi filter không match. Nhưng khi TCP connection không thể được thiết lập, JNDI ném `CommunicationException`; Spring LDAP chuyển exception này thành runtime exception `org.springframework.ldap.CommunicationException`.

Thêm test:

```java
@Test
void reportsCommunicationFailureWhenServerStops() {
    server.shutDown(true);

    assertThatThrownBy(() -> ldapTemplate.search(
            "ou=people",
            "(uid=lan)",
            attrs -> (String) attrs.get("uid").get()))
            .isInstanceOf(CommunicationException.class);
}
```

`shutDown(true)` dừng listener và đóng các kết nối đang mở. Lời gọi `search` sau đó phải thiết lập kết nối mới; vì server không còn lắng nghe, thao tác thất bại ở tầng giao tiếp.

Test dùng `setPooled(false)` và không tạo request thành công trước khi dừng server. Điều đó tránh tình huống client tái sử dụng connection có sẵn rồi làm test không còn mô phỏng được kết nối mới.

Trong `@AfterEach`, gọi `shutDown(true)` thêm lần nữa là an toàn: server đã dừng sẽ không có listener đang hoạt động để dừng tiếp.

### 7.1. Phân biệt lỗi mạng với lỗi xác thực

Sai mật khẩu vẫn có thể kết nối được đến server. TCP và LDAP protocol hoạt động, nhưng Bind bị từ chối. Đây là lỗi khác với server không thể truy cập.

Tạo một `LdapContextSource` riêng với password sai:

```java
@Test
void reportsAuthenticationFailureForWrongPassword() throws Exception {
    LdapContextSource badContextSource = new LdapContextSource();
    badContextSource.setUrl(
            "ldap://127.0.0.1:" + server.getListenPort());
    badContextSource.setBase(BASE_DN);
    badContextSource.setUserDn(ADMIN_DN);
    badContextSource.setPassword("incorrect-password");
    badContextSource.setPooled(false);
    badContextSource.afterPropertiesSet();

    LdapTemplate badTemplate = new LdapTemplate(badContextSource);

    assertThatThrownBy(() -> badTemplate.search(
            "ou=people",
            "(uid=lan)",
            attrs -> (String) attrs.get("uid").get()))
            .isInstanceOf(AuthenticationException.class);
}
```

Test này chạy khi server vẫn hoạt động. Server nhận Bind request nhưng từ chối credential. Vì vậy, Spring LDAP ánh xạ lỗi sang `AuthenticationException`.

### 7.2. Bảng phân loại kết quả

| Tình huống | Kết quả ở tầng Spring LDAP | Ý nghĩa |
|---|---|---|
| Filter hợp lệ, không có entry match | List rỗng | Search hoàn tất, không có kết quả phù hợp |
| LDAP server dừng hoặc endpoint từ chối kết nối | `CommunicationException` | Không thể giao tiếp với directory |
| Bind DN/password không hợp lệ | `AuthenticationException` | Kết nối đến server được, nhưng xác thực thất bại |
| Base DN không tồn tại và không bỏ qua lỗi | `NameNotFoundException` | Search base không tìm thấy |
| Referral/continuation không được xử lý | Có thể là `PartialResultException` | Search có thể chỉ hoàn thành một phần |

Đừng bắt tất cả exception rồi trả `Collections.emptyList()`. Cách làm đó biến lỗi mạng, sai credential hoặc partial result thành một kết quả nghiệp vụ có vẻ hợp lệ.

## 8. Áp dụng với Spring Boot và Spring Data LDAP Repository

Nếu ứng dụng dùng Spring Boot, `@DataLdapTest` là test slice dành cho LDAP. Khi có embedded LDAP phù hợp trên test classpath, Spring Boot có thể cấu hình directory nhúng, `LdapTemplate`, quét các class `@Entry` và cấu hình Spring Data LDAP repositories.

Ví dụ khung repository test:

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.ldap.DataLdapTest;

@DataLdapTest
class PersonRepositoryIntegrationTest {

    @Autowired
    private PersonRepository repository;

    @Test
    void savesAndReadsPerson() {
        Person person = new Person();
        person.setUid("lan");
        person.setCn("Lan Nguyen");
        person.setSn("Nguyen");
        person.setMail("lan@example.org");

        Person saved = repository.save(person);

        assertThat(repository.findById(saved.getId()))
                .isPresent()
                .get()
                .extracting(Person::getUid)
                .isEqualTo("lan");
    }
}
```

Ví dụ giả định dự án đã có `Person` được ánh xạ bằng `@Entry` và `PersonRepository` kế thừa `LdapRepository<Person>`. Hãy dùng đúng constructor/getter/setter và kiểu ID của entity trong module đang học.

`@DataLdapTest` phù hợp để kiểm tra repository và mapping. Test mô phỏng server ngừng hoạt động ở phần trước cần một test context riêng, vì test slice tự động cấu hình embedded server và không phải nơi thích hợp để dừng server dùng chung của Spring context.

Nếu muốn chạy `@DataLdapTest` với LDAP server thật, loại embedded LDAP auto-configuration bằng `EmbeddedLdapAutoConfiguration` và cung cấp cấu hình kết nối test riêng. Không để test vô tình kết nối tới directory production.

## 9. Mở rộng bài thực hành

Sau khi các test cơ bản chạy thành công, hoàn thành các nhiệm vụ sau:

### Nhiệm vụ A — Tách service khỏi test fixture

Tạo `PersonDirectoryService` nhận `LdapTemplate` qua constructor. Di chuyển logic search vào service và để test gọi service thay vì gọi template trực tiếp. Giữ `LdapContextSource` và embedded server trong test configuration.

### Nhiệm vụ B — Kiểm tra DN không tồn tại

Search một base DN không có trong fixture. Xác minh exception khi `ignoreNameNotFoundException` được cấu hình `false`. Sau đó thử cấu hình bỏ qua exception và ghi lại khác biệt với trường hợp filter hợp lệ nhưng không match.

### Nhiệm vụ C — Kiểm tra timeout

Tạo một test profile riêng có server hoặc network proxy điều khiển được độ trễ. Đặt timeout phù hợp và xác minh exception/root cause của provider. Không dùng `Thread.sleep()` để tạo timing race; một timeout test phải có điều kiện tái lập và giới hạn thời gian tổng thể.

### Nhiệm vụ D — Kiểm tra lỗi TLS

Nếu service dùng LDAPS hoặc StartTLS, dựng server test với certificate riêng. Kiểm tra cả trường hợp truststore đúng và certificate không được trust. Không tắt certificate verification để làm test pass.

### Nhiệm vụ E — Kiểm tra retry có giới hạn

Viết policy retry chỉ cho lỗi giao tiếp tạm thời, có số lần thử và backoff tối đa. Không retry vô hạn; không retry `AuthenticationException` hoặc lỗi filter/schema như thể chúng là lỗi mạng.

### Nhiệm vụ F — Kiểm tra service không che lỗi

Viết test xác nhận service không chuyển `CommunicationException`, `AuthenticationException` hoặc `PartialResultException` thành danh sách rỗng. Nếu service chuyển exception thành exception nghiệp vụ riêng, hãy giữ cause gốc để log và điều tra.

## 10. Ma trận test cần hoàn thành

| ID | Tình huống | Kỳ vọng |
|---|---|---|
| INT-01 | Search theo UID có tồn tại | Trả đúng một `PersonView` |
| INT-02 | Filter hợp lệ nhưng không match | List rỗng |
| INT-03 | Search có attribute mapper | Giá trị UID/CN/mail đúng |
| INT-04 | Tạo entry mới | Search thấy entry vừa tạo |
| INT-05 | Thay đổi mail | Search trả mail mới |
| INT-06 | Xóa entry | Search không còn entry |
| INT-07 | Assertion value có ký tự filter đặc biệt | Không mở rộng filter |
| ERR-01 | Server dừng trước Search | `CommunicationException` |
| ERR-02 | Bind password sai | `AuthenticationException` |
| ERR-03 | Base DN sai | `NameNotFoundException` hoặc hành vi ignore đã cấu hình |
| ERR-04 | Referral chưa xử lý | Lỗi/partial result được nhận biết |
| ERR-05 | TLS certificate không tin cậy | Kết nối bảo mật thất bại |
| ERR-06 | Lỗi giao tiếp tạm thời | Retry có giới hạn nếu policy cho phép |

## 11. Các lỗi thường gặp khi viết integration test

| Cách làm | Vấn đề | Cách sửa |
|---|---|---|
| Dùng cổng LDAP cố định | Test xung đột giữa tiến trình hoặc CI | Dùng cổng tự chọn và đọc bằng `getListenPort()` |
| Dùng directory dùng chung cho nhiều test | Dữ liệu test ảnh hưởng lẫn nhau | Dựng server/fixture riêng mỗi test hoặc reset rõ ràng |
| Không dừng server sau test | Rò rỉ listener và port | Dùng `@AfterEach`/`@AfterAll` để shutdown |
| Dùng mock để khẳng định TCP đã hoạt động | Mock không tạo kết nối mạng | Dùng embedded LDAP server cho integration test |
| Dùng `setPooled(true)` rồi dừng server | Client có thể dùng connection đã mở | Tắt pool trong test mô phỏng server unavailable |
| Bắt mọi exception và trả list rỗng | Che lỗi hạ tầng và dữ liệu không đầy đủ | Phân loại exception và giữ cause |
| Dùng password production trong fixture | Rò rỉ credential | Chỉ dùng credential giả |
| Dùng filter nối chuỗi từ input | Có nguy cơ filter injection | Dùng `LdapQueryBuilder` hoặc encode assertion value |
| Dùng `Thread.sleep()` để ép lỗi timeout | Test chập chờn | Dùng server/proxy có khả năng điều khiển delay |
| Không test referral target | Không phát hiện lỗi DNS/TLS/Bind | Dùng topology nhiều server nếu referral thuộc scope |
| Chỉ kiểm tra repository save | Không chứng minh entry có thể được đọc lại | Save rồi find/search và assert attribute |

## 12. Tiêu chí hoàn thành

Bài thực hành được xem là hoàn thành khi:

- [ ] Test server nhúng tự chọn cổng và nạp đúng base DN/OU/entry.
- [ ] Search theo UID trả đúng object đã map.
- [ ] Search không match trả list rỗng.
- [ ] Test CRUD tạo, cập nhật và xóa entry thành công.
- [ ] Filter builder xử lý assertion value có ký tự đặc biệt.
- [ ] Dừng server làm phát sinh `CommunicationException`.
- [ ] Bind sai password làm phát sinh `AuthenticationException`.
- [ ] Cleanup dừng server sau từng test.
- [ ] Service không biến lỗi kết nối hoặc partial result thành empty list.
- [ ] Không dùng endpoint, credential hoặc dữ liệu production.

## 13. Câu hỏi tự đánh giá

1. Vì sao unit test dùng mock `LdapTemplate` không đủ để chứng minh client có thể kết nối LDAP?
2. `InMemoryDirectoryServer` giúp tạo integration test như thế nào?
3. Vì sao nên để server chọn cổng động?
4. `LdapContextSource.setPooled(false)` có ý nghĩa gì trong test mô phỏng server dừng?
5. `CommunicationException` khác `AuthenticationException` ở đâu?
6. Vì sao một filter hợp lệ không match phải trả list rỗng?
7. Vì sao không nên chuyển mọi exception thành empty list?
8. `bind`, `modifyAttributes` và `unbind` tương ứng với thao tác CRUD nào?
9. Vì sao cần test filter assertion value có ký tự đặc biệt?
10. `@DataLdapTest` giúp kiểm tra repository và ODM như thế nào?
11. Vì sao test mô phỏng network outage nên có context/server riêng?
12. Những lỗi nào có thể retry và những lỗi nào cần xử lý cấu hình/dữ liệu?

**Ghi nhớ:** integration test LDAP cần một directory server có thể kiểm soát và dữ liệu xác định. Hãy kiểm tra cả đường đi thành công lẫn lỗi Bind/kết nối. Server dừng phải tạo lỗi giao tiếp; sai mật khẩu phải tạo lỗi xác thực; filter không match mới là list rỗng. Giữ các trạng thái này riêng biệt để service không che giấu sự cố directory.

### Tài liệu tham khảo

- Spring LDAP Reference — [Testing](https://docs.spring.io/spring-ldap/reference/testing.html): embedded LDAP server và UnboundID test support.
- Spring Boot Reference — [Auto-configured Data LDAP Tests](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html#testing.spring-boot-applications.autoconfigured-data-ldap-tests): `@DataLdapTest`, `LdapTemplate`, `@Entry`, repository và embedded LDAP.
- UnboundID LDAP SDK — [In-Memory Directory Server](https://docs.ldap.com/ldap-sdk/docs/in-memory-directory-server.html): tạo, nạp dữ liệu, mở listener, lấy cổng và dừng server trong Java test.
- UnboundID LDAP SDK — [InMemoryDirectoryServer API](https://docs.ldap.com/ldap-sdk/docs/javadoc/com/unboundid/ldap/listener/InMemoryDirectoryServer.html): `add`, `getListenPort`, `startListening` và `shutDown`.
- Spring LDAP API — [CommunicationException](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/CommunicationException.html): runtime exception tương ứng JNDI CommunicationException.
- Spring LDAP API — [AbstractContextSource](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/support/AbstractContextSource.html): cấu hình URL, Bind identity, base DN và tùy chọn pooling.
- Spring LDAP API — [LdapTemplate](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/LdapTemplate.html): search, bind, modifyAttributes, unbind và exception translation.
- Spring LDAP API — [LdapQueryBuilder](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/query/LdapQueryBuilder.html): xây dựng LDAP filter và encode assertion values an toàn.
