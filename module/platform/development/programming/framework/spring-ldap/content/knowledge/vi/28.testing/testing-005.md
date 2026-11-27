# Seed DIT và dữ liệu test theo từng kịch bản

Trong **Spring LDAP**, một bài integration test chỉ đáng tin cậy nếu thư mục kiểm thử có dữ liệu **được kiểm soát, đúng cấu trúc và tái tạo được**. Cùng một câu truy vấn `LdapTemplate.search(...)` có thể trả kết quả khác nhau khi DN gốc thay đổi, entry nằm ở cấp con khác, thiếu `objectClass`, hoặc còn dữ liệu từ bài test trước. Vì vậy, **seed DIT** (Directory Information Tree) là công việc thiết kế đầu vào của phép kiểm thử chứ không chỉ thêm vài entry cho đủ số lượng.

Bài học trong chương **Testing** của module **SPRING_LDAP** trình bày cách xây dựng cây thư mục mẫu, chia dữ liệu theo kịch bản, nạp bằng Java hoặc LDIF, kiểm tra với `LdapTemplate` thật, và giữ mỗi test độc lập. Các nguyên tắc này áp dụng khi ứng dụng dùng `LdapTemplate`, `LdapClient` hoặc ODM để tìm kiếm, xác thực và thao tác entry. Riêng TLS, pooling, quyền truy cập và đặc tính server sản xuất cần được kiểm tra bằng các môi trường chuyên biệt tương ứng.

## 1. DIT là gì và tại sao dữ liệu seed phải phản ánh cấu trúc thư mục?

**DIT** là cây các entry LDAP. Mỗi entry được định danh bằng **DN** (Distinguished Name); mỗi thành phần trên đường đi là một **RDN** (Relative Distinguished Name). Ví dụ:

```text
dc=example,dc=org
├── ou=people
│   ├── uid=an
│   ├── uid=binh
│   └── ou=contractors
│       └── uid=external
└── ou=groups
    └── cn=developers
```

DN đầy đủ của người dùng `an` là:

```text
uid=an,ou=people,dc=example,dc=org
```

Còn `uid=an,ou=people` là DN **tương đối với** `dc=example,dc=org`. Với `LdapContextSource.setBase("dc=example,dc=org")`, nhiều API của `LdapTemplate` nhận DN tương đối này; khi nạp entry bằng UnboundID SDK, phải cung cấp DN đầy đủ.

Một fixture cần bảo đảm:

- Entry cha tồn tại trước entry con. Ví dụ, chỉ thêm `uid=an,ou=people,...` sau khi tạo `ou=people,...`.
- DN duy nhất và đúng cú pháp; ký tự đặc biệt trong giá trị RDN phải được escape theo quy tắc DN.
- Thuộc tính phù hợp với schema: `person` yêu cầu `cn` và `sn`; `inetOrgPerson` thường dùng thêm `uid` và `mail`.
- Chỉ đặt những giá trị mà test thực sự cần, nhưng vẫn đủ các `objectClass` và thuộc tính bắt buộc.
- Có các nhánh ở **độ sâu khác nhau** để test phát hiện nhầm lẫn giữa `ONELEVEL_SCOPE` và `SUBTREE_SCOPE`.
- Dữ liệu giả không chứa thông tin định danh cá nhân, mật khẩu thật hoặc bản sao thư mục sản xuất.

**Vì sao cần phân nhánh?** Nếu tất cả entry nằm ngay dưới `ou=people` thì truy vấn với `ONELEVEL_SCOPE` có thể tình cờ cho kết quả giống `SUBTREE_SCOPE`. Một entry `uid=external` ở sâu thêm một cấp biến khác biệt đó thành điều có thể kiểm thử.

## 2. Thiết kế seed theo từng kịch bản, không theo một “database mẫu” khổng lồ

Nên bắt đầu từ **kết quả mong đợi** của test, sau đó xây dựng DIT tối thiểu đủ chứng minh kết quả ấy. Có hai lớp dữ liệu:

1. **Base fixture bất biến:** naming context, các OU nền, objectClass và cấu trúc bắt buộc.
2. **Scenario fixture:** người dùng, nhóm và giá trị thuộc tính chỉ dành cho một ca kiểm thử.

| Kịch bản | Entry cần seed thêm | Assertion có ý nghĩa |
| --- | --- | --- |
| Tìm `uid` hợp lệ | Một người dùng có `uid`, `cn`, `sn` | Tìm đúng một DTO với giá trị mong đợi |
| Không tìm thấy | Không thêm entry có `uid` cần tìm | Trả danh sách rỗng |
| Thuộc tính tùy chọn vắng mặt | Entry không có `mail` | Mapper trả `null` hoặc giá trị mặc định theo contract |
| Tìm kiếm theo cấp | Một người nằm trong `ou=contractors,ou=people` | `ONELEVEL_SCOPE` không thấy; `SUBTREE_SCOPE` thấy |
| Nhóm người dùng | Một `groupOfNames` có `member` trỏ tới DN người dùng | Đọc đúng giá trị thành viên; không suy luận nhóm tự động |
| Tên DN trùng | Thêm một entry rồi thử thêm lại cùng DN | Server từ chối entry trùng |
| Cập nhật/xóa | Entry có DN riêng của test | Đọc được giá trị mới, xóa xong không tìm thấy |
| Lỗi schema | Entry thiếu thuộc tính bắt buộc hoặc có `objectClass` sai | Server trả lỗi khi chế độ kiểm tra schema phù hợp được bật |
| Filter chứa ký tự đặc biệt | `uid` chứa hoặc được truy vấn với `*`, `(`, `)` | Builder escape giá trị; không mở rộng kết quả ngoài ý muốn |
| Phân quyền/xác thực | Account test với quyền riêng, dùng server có ACL tương ứng | Cho phép/từ chối đúng theo policy thực sự được cấu hình |

Một test càng dùng ít entry liên quan thì càng dễ hiểu nguyên nhân thất bại. Không nên tạo sẵn hàng trăm người dùng trong mọi test rồi khẳng định kết quả dựa vào thứ tự may rủi của LDAP search.

## 3. Chuẩn bị UnboundID và Spring LDAP cho test độc lập

Ví dụ sử dụng **Java 17+**, JUnit Jupiter (JUnit 5), `org.springframework.ldap:spring-ldap-core` và `com.unboundid:unboundid-ldapsdk`. Dùng phiên bản tương thích với dependency management của dự án. Nếu dùng Gradle:

```groovy
dependencies {
    implementation 'org.springframework.ldap:spring-ldap-core'
    testImplementation 'org.junit.jupiter:junit-jupiter'
    testImplementation 'com.unboundid:unboundid-ldapsdk'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

UnboundID In-Memory Directory Server chạy LDAP protocol thật qua TCP, nhưng dữ liệu nằm trong JVM. Trong ví dụ này, mỗi test tạo server mới ở `@BeforeEach` và dừng ở `@AfterEach`. Cách này tốn thời gian khởi tạo hơn chia sẻ một server cho cả lớp, đổi lại fixture của các ca kiểm thử không ảnh hưởng nhau.

```text
@BeforeEach
   │
   ├── Tạo server trên 127.0.0.1:cổng-động
   ├── Seed dc=example,dc=org
   ├── Seed ou=people và ou=groups
   └── Tạo LdapContextSource + LdapTemplate
   │
   ▼
@Test
   │
   ├── Seed entry riêng cho kịch bản
   ├── Gọi LdapTemplate thật
   └── Assert dữ liệu được server trả về
   │
   ▼
@AfterEach
   └── Dừng server, giải phóng tài nguyên
```

Cần phân biệt **seed trực tiếp qua UnboundID SDK** và **thao tác nghiệp vụ qua Spring LDAP**. API `server.add(...)` là công cụ quản trị fixture của test; nó không đi qua credential hoặc đường xử lý `LdapTemplate` của ứng dụng. Khi muốn kiểm tra quyền ghi/bind của ứng dụng, phải thực hiện thao tác đó bằng client LDAP với credential test tương ứng.

## 4. Ví dụ đầy đủ: seed base DIT và mở rộng theo scenario

Tạo `src/test/java/com/example/ldap/ScenarioSeedIntegrationTest.java`. Mã dưới đây tạo thư mục hoàn toàn mới cho từng test, seed hai OU nền, sau đó thêm người dùng hoặc nhóm ngay trong phương thức kiểm thử. Các DN truyền vào UnboundID SDK là DN đầy đủ; base của Spring LDAP được cấu hình bằng `dc=example,dc=org`.

```java
package com.example.ldap;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.ldap.query.LdapQueryBuilder.query;

import com.unboundid.ldap.listener.InMemoryDirectoryServer;
import com.unboundid.ldap.listener.InMemoryDirectoryServerConfig;
import com.unboundid.ldap.listener.InMemoryListenerConfig;
import com.unboundid.ldap.sdk.Attribute;
import com.unboundid.ldap.sdk.Entry;
import com.unboundid.ldap.sdk.LDAPException;
import com.unboundid.ldap.sdk.ResultCode;
import java.net.InetAddress;
import java.util.List;
import javax.naming.NamingException;
import javax.naming.directory.Attributes;
import javax.naming.directory.SearchControls;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.core.support.LdapContextSource;

class ScenarioSeedIntegrationTest {

    private static final String BASE = "dc=example,dc=org";
    private static final String PEOPLE = "ou=people," + BASE;
    private static final String GROUPS = "ou=groups," + BASE;

    private InMemoryDirectoryServer server;
    private LdapTemplate ldap;

    record User(String uid, String cn, String mail) {}

    @BeforeEach
    void setUp() throws Exception {
        InMemoryDirectoryServerConfig config =
                new InMemoryDirectoryServerConfig(BASE);

        // Không mở listener trên interface mạng bên ngoài.
        config.setListenerConfigs(
                InMemoryListenerConfig.createLDAPConfig(
                        "test-ldap",
                        InetAddress.getByName("127.0.0.1"),
                        0,
                        null
                )
        );
        config.addAdditionalBindCredentials(
                "cn=Directory Manager", "test-password");

        server = new InMemoryDirectoryServer(config);

        try {
            server.startListening();

            // Base fixture: tạo cha trước rồi mới tạo OU con.
            server.addEntries(
                    new Entry(BASE,
                            new Attribute("objectClass", "top", "domain"),
                            new Attribute("dc", "example")),

                    new Entry(PEOPLE,
                            new Attribute("objectClass", "top",
                                    "organizationalUnit"),
                            new Attribute("ou", "people")),

                    new Entry(GROUPS,
                            new Attribute("objectClass", "top",
                                    "organizationalUnit"),
                            new Attribute("ou", "groups"))
            );

            LdapContextSource source = new LdapContextSource();
            source.setUrl(
                    "ldap://127.0.0.1:" + server.getListenPort());
            source.setBase(BASE);
            source.setUserDn("cn=Directory Manager");
            source.setPassword("test-password");
            source.setPooled(false);
            source.afterPropertiesSet();

            ldap = new LdapTemplate(source);
        } catch (Exception e) {
            server.shutDown(true);
            throw e;
        }
    }

    @AfterEach
    void tearDown() {
        if (server != null) {
            server.shutDown(true);
        }
    }

    // Dữ liệu đầu vào kiểm soát trong test, không phải DN từ người dùng.
    private static Entry person(
            String uid, String cn, String sn, String mail,
            String parentDn) {

        Entry entry = new Entry(
                "uid=" + uid + "," + parentDn,
                new Attribute("objectClass", "top", "person",
                        "organizationalPerson", "inetOrgPerson"),
                new Attribute("uid", uid),
                new Attribute("cn", cn),
                new Attribute("sn", sn)
        );

        if (mail != null) {
            entry.addAttribute("mail", mail);
        }
        return entry;
    }

    private static User mapUser(Attributes attributes)
            throws NamingException {
        javax.naming.directory.Attribute mail =
                attributes.get("mail");

        return new User(
                (String) attributes.get("uid").get(),
                (String) attributes.get("cn").get(),
                mail == null ? null : (String) mail.get()
        );
    }

    private List<User> findUsers(String uid, int scope) {
        return ldap.search(
                query()
                        .base("ou=people")
                        .searchScope(scope)
                        .where("uid").is(uid),
                (AttributesMapper<User>)
                        ScenarioSeedIntegrationTest::mapUser
        );
    }

    @Test
    void findsSeededUser() throws Exception {
        server.add(person(
                "an", "Nguyễn An", "Nguyễn",
                "an@example.org", PEOPLE));

        assertEquals(
                List.of(new User(
                        "an", "Nguyễn An", "an@example.org")),
                findUsers("an", SearchControls.SUBTREE_SCOPE)
        );
    }

    @Test
    void mapsMissingOptionalMailToNull() throws Exception {
        server.add(person(
                "binh", "Bình Trần", "Trần", null, PEOPLE));

        assertEquals(
                List.of(new User("binh", "Bình Trần", null)),
                findUsers("binh", SearchControls.SUBTREE_SCOPE)
        );
    }

    @Test
    void startsWithNoPersonEntriesInEveryTest() {
        List<User> users = ldap.search(
                query()
                        .base("ou=people")
                        .where("objectClass").is("inetOrgPerson"),
                (AttributesMapper<User>)
                        ScenarioSeedIntegrationTest::mapUser
        );

        assertTrue(users.isEmpty());
    }

    @Test
    void distinguishesOneLevelAndSubtree() throws Exception {
        String contractors = "ou=contractors," + PEOPLE;

        server.add(new Entry(contractors,
                new Attribute("objectClass", "top",
                        "organizationalUnit"),
                new Attribute("ou", "contractors")));

        server.add(person(
                "external", "External User", "User",
                null, contractors));

        assertTrue(findUsers(
                "external", SearchControls.ONELEVEL_SCOPE).isEmpty());

        assertEquals(
                List.of(new User("external", "External User", null)),
                findUsers("external", SearchControls.SUBTREE_SCOPE)
        );
    }

    @Test
    void groupFixtureReferencesAnExistingUserDn()
            throws Exception {

        server.add(person(
                "an", "Nguyễn An", "Nguyễn", null, PEOPLE));

        String memberDn = "uid=an," + PEOPLE;
        server.add(new Entry(
                "cn=developers," + GROUPS,
                new Attribute("objectClass", "top", "groupOfNames"),
                new Attribute("cn", "developers"),
                new Attribute("member", memberDn)
        ));

        List<String> members = ldap.search(
                query()
                        .base("ou=groups")
                        .where("cn").is("developers"),
                (AttributesMapper<String>) attributes ->
                        (String) attributes.get("member").get()
        );

        assertEquals(List.of(memberDn), members);
    }

    @Test
    void duplicateDnIsRejectedByServer() throws Exception {
        Entry original = person(
                "an", "Nguyễn An", "Nguyễn", null, PEOPLE);

        server.add(original);

        LDAPException error = assertThrows(
                LDAPException.class,
                () -> server.add(original)
        );

        assertEquals(
                ResultCode.ENTRY_ALREADY_EXISTS,
                error.getResultCode()
        );
    }

    @Test
    void filterValueDoesNotChangeFilterStructure()
            throws Exception {

        server.add(person(
                "an", "Nguyễn An", "Nguyễn", null, PEOPLE));

        // Chuỗi này là giá trị uid, không phải cú pháp LDAP filter.
        assertTrue(findUsers(
                "an*)(uid=*", SearchControls.SUBTREE_SCOPE).isEmpty());
    }
}
```

### Đọc kết quả kiểm thử theo đúng mục tiêu seed

- **`findsSeededUser`** chứng minh entry có DN và các thuộc tính hợp lệ được server trả về, mapper nhận đúng Unicode và email.
- **`mapsMissingOptionalMailToNull`** khẳng định việc không có `mail` khác với việc có `mail` là chuỗi rỗng. Quy tắc của mapper ở đây là trả `null` khi thiếu.
- **`startsWithNoPersonEntriesInEveryTest`** chứng minh mỗi test chỉ có base fixture, không chứa người dùng được test khác thêm.
- **`distinguishesOneLevelAndSubtree`** xác minh cấu trúc DIT đủ phân biệt scope tìm kiếm.
- **`groupFixtureReferencesAnExistingUserDn`** khẳng định một entry nhóm có giá trị `member` trỏ đến DN người dùng đã seed; test này **không** chứng minh cơ chế tự động quản lý thuộc tính `memberOf`.
- **`duplicateDnIsRejectedByServer`** xác minh phép thêm entry trùng DN thất bại trên server.
- **`filterValueDoesNotChangeFilterStructure`** chứng minh giá trị đầu vào chứa các ký tự filter không làm truy vấn tìm thêm entry ngoài ý muốn khi dùng query builder.

Các test này có server riêng và tắt server sau mỗi phương thức, nên không dựa vào thứ tự thực thi của JUnit. Nếu muốn dùng một server chung để tăng tốc, cần cơ chế **reset fixture giữa các test** tương đương về mặt dữ liệu.

## 5. Dùng LDIF cho fixture lớn và phân nhóm theo kịch bản

Khi có nhiều entry, dùng **LDIF** dễ đọc và review hơn lặp lại hàng chục lời gọi `new Entry(...)`. Nên phân chia nguồn dữ liệu theo mục đích:

```text
src/test/resources/ldap/
├── base.ldif
└── scenarios/
    ├── search-users.ldif
    ├── nested-users.ldif
    ├── group-membership.ldif
    └── invalid-schema.ldif
```

Đây là **quy ước tổ chức file trong dự án**, không phải cú pháp `include` của LDIF. Server cần được nạp bằng code theo đúng thứ tự, hoặc nhận một snapshot LDIF đã được ghép hợp lệ; bản thân LDIF không tự import các file khác.

Ví dụ `base.ldif`:

```ldif
dn: dc=example,dc=org
objectClass: top
objectClass: domain
dc: example

dn: ou=people,dc=example,dc=org
objectClass: top
objectClass: organizationalUnit
ou: people

dn: ou=groups,dc=example,dc=org
objectClass: top
objectClass: organizationalUnit
ou: groups
```

Ví dụ `scenarios/search-users.ldif`:

```ldif
dn: uid=an,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: an
cn: An Nguyen
sn: Nguyen
mail: an@example.org

dn: uid=binh,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: binh
cn: Binh Tran
sn: Tran
```

Ví dụ `scenarios/group-membership.ldif`:

```ldif
dn: uid=an,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: an
cn: An Nguyen
sn: Nguyen

dn: cn=developers,ou=groups,dc=example,dc=org
objectClass: top
objectClass: groupOfNames
cn: developers
member: uid=an,ou=people,dc=example,dc=org
```

**Lưu ý quan trọng:** Hai file scenario trên cùng định nghĩa DN `uid=an,ou=people,...`. Chúng là hai **fixture lựa chọn độc lập**, không được import đồng thời vào cùng một server trừ khi thiết kế lại dữ liệu để loại bỏ trùng DN. Lỗi `ENTRY_ALREADY_EXISTS` lúc seed là dấu hiệu fixture mâu thuẫn, không nên bỏ qua.

Với UnboundID, có thể nạp một snapshot LDIF hoàn chỉnh bằng:

```java
server.importFromLDIF(true, absoluteLdIfFilePath);
```

`true` nghĩa là **xóa toàn bộ entry trước khi import**. Nếu lần thứ nhất import `base.ldif` với `true`, rồi lần thứ hai import file scenario cũng với `true` thì base đã bị xóa và dữ liệu scenario có thể không nạp được vì thiếu entry cha. Hai cách an toàn là:

1. Tạo một snapshot hợp lệ chứa **base + đúng một scenario**, rồi import snapshot đó một lần.
2. Import base, sau đó thêm các entry của scenario bằng UnboundID SDK (ví dụ `server.add(...)`/`server.addEntries(...)`) theo thứ tự cha → con, không reset ở giữa.

Không dùng `importFromLDIF(true, ...)` trên server LDAP chia sẻ hoặc server production. Tác vụ xóa toàn bộ entry chỉ phù hợp với một **server test do chính suite sở hữu**.

### Giá trị Unicode và cú pháp LDIF

Với LDIF, giá trị chứa Unicode ngoài ASCII nên mã hóa Base64 theo cú pháp hai dấu hai chấm. Ví dụ một entry hợp lệ có `cn` là `Café` (`Q2Fmw6k=` là Base64 của UTF-8 `Café`):

```ldif
dn: uid=cafe,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: cafe
cn:: Q2Fmw6k=
sn: Cafe
```

Entry này có thể được nạp sau khi `ou=people` đã tồn tại. Trong mã Java ở phần 4, Unicode được truyền trực tiếp qua `new Attribute("cn", "Nguyễn An")` nên không cần tự mã hóa LDIF. Khi viết LDIF, hãy bảo đảm dữ liệu sau `cn::` là Base64 của chuỗi UTF-8 chính xác.

## 6. Dựng dữ liệu âm tính mà vẫn kiểm chứng đúng lỗi

Những ca **negative test** là lý do quan trọng nhất để chia fixture theo từng kịch bản. Tuy nhiên không nên nhầm lỗi seed với lỗi nghiệp vụ.

| Tình huống | Cách seed phù hợp | Kỳ vọng |
| --- | --- | --- |
| Không tìm thấy người dùng | Không tạo entry có `uid` được hỏi | Query trả danh sách rỗng |
| Thiếu thuộc tính tùy chọn | Tạo `inetOrgPerson` không có `mail` | Mapper xử lý theo contract |
| Thiếu thuộc tính bắt buộc `sn` | Tạo entry `person` thiếu `sn` trong fixture riêng | Server từ chối nếu schema check bật |
| Sai objectClass | Thử thêm entry thiếu `objectClass` bắt buộc | Server báo lỗi schema phù hợp |
| DN không hợp lệ | Tạo DN từ input không đúng cú pháp qua parser | Bị từ chối trước hoặc khi gửi LDAP request |
| Entry trùng DN | Thêm lại đúng DN đã tồn tại | `ENTRY_ALREADY_EXISTS` |
| User ở sai nhánh | Đặt user dưới `ou=contractors` | Search base/scope hẹp không thấy |
| Không có quyền sửa | Dùng account không đủ quyền trên server có ACL | LDAP trả lỗi quyền |
| Truy vấn với ký tự đặc biệt | Input chứa `*`, `(`, `)` hoặc dấu gạch chéo ngược | Escape đúng, không đổi logic filter |

Một số lỗi phải được kiểm tra bằng **hai tầng**:

- Với **unit test mapper**, có thể tạo `BasicAttributes` thiếu `cn` hoặc chứa `byte[]` bất thường mà không cần LDAP server. Khi đó kiểm tra chính sách lỗi của Java mapper.
- Với **integration test schema**, dùng server có schema validation đang hoạt động và thử nhập entry không hợp lệ. Nếu server từ chối ở bước seed, hãy assert đó chính là kết quả mong đợi của test schema; không đưa fixture hỏng vào `@BeforeEach` chung làm mọi test đều thất bại.

Mọi test cần ghi rõ **lỗi mong đợi ở giai đoạn nào**: khởi tạo fixture, gửi LDAP request, chuyển đổi kết quả hay xử lý nghiệp vụ. Khi biết ranh giới lỗi, việc chẩn đoán trở nên chính xác hơn.

### Không giả lập ACL bằng dữ liệu nhóm đơn giản

Một entry `groupOfNames` chứa `member` chỉ chứng minh dữ liệu thuộc tính nhóm tồn tại. Nó **không tự cấp quyền** hay bảo đảm server sinh ra `memberOf` cho user. Membership overlay, ACL và chính sách xác thực phụ thuộc implementation và cấu hình server. Khi muốn test quyền đọc/ghi, phải dùng môi trường có ACL thật và một tài khoản quyền hạn thấp, không dựa vào tài khoản seed có quyền quản trị.

## 7. Tái lập và cô lập trạng thái giữa các test

Một lỗi phổ biến là tạo server một lần trong `@BeforeAll`, sau đó cho mọi test sửa cùng các entry. Khi suite chạy với thứ tự khác hoặc chạy song song, một test có thể tìm thấy dữ liệu từ test trước và báo sai kết quả.

Các chiến lược:

| Chiến lược | Đổi lại | Nên dùng khi |
| --- | --- | --- |
| Server mới trong `@BeforeEach`, seed lại base | Chậm hơn nhưng tách biệt tuyệt đối | Suite nhỏ/vừa, test có nhiều ghi/xóa |
| Server chung, mỗi test dùng DN riêng + cleanup | Nhanh hơn nhưng phải kiểm soát trạng thái chia sẻ | Test chỉ thêm entry độc lập |
| Snapshot/restore hoặc tái import LDIF giữa các test | Có chi phí reset và phải chắc server đã sạch | Fixture lớn, muốn môi trường xác định |
| Container/server riêng cho mỗi lớp test | Phản ánh implementation cụ thể, khởi động lâu hơn | Integration test với OpenLDAP hoặc server khác |
| Server test dùng chung từ CI/staging | Có nguy cơ xung đột khi chạy song song | Chỉ khi có namespace/DN, quyền và quy trình dọn dẹp rõ ràng |

Nếu dùng cùng một server cho nhiều test, nên áp dụng:

1. Quy ước **namespace riêng** cho từng test, như một OU hoặc suffix riêng nếu server hỗ trợ.
2. DN riêng cho entry ghi/xóa, tạo bằng ID ổn định của test hoặc `UUID`.
3. `try/finally` để xóa entry kể cả khi assertion thất bại.
4. Không phụ thuộc thứ tự entry do LDAP server trả về; so sánh theo tập hợp trừ khi có sắp xếp rõ ràng.
5. Không để các test sửa cùng một nhóm hoặc cùng tài khoản khi chạy song song.
6. Kiểm tra server đã sẵn sàng, base DN tồn tại và số entry nền như mong đợi **trước khi chạy assertion của kịch bản**.

**Cẩn trọng với `UUID`:** ID ngẫu nhiên giúp tránh xung đột DN nhưng khiến test khó tái hiện nguyên văn khi lỗi. Nên ghi ID không nhạy cảm vào log test hoặc chọn ID cố định khi chạy trên server mới cho mỗi test. Với bài test thuần đọc, fixture cố định thường dễ debug hơn.

## 8. Liên hệ với LdapTemplate, LdapClient và ODM

Đối với **`LdapTemplate`** hoặc **`LdapClient`**, data seed là điều kiện để xác minh truy vấn thực sự trả đúng kết quả theo filter, base và scope. Các API khác nhau có thể dùng lại cùng mô hình DIT nếu mapping và phạm vi truy vấn tương ứng.

Đối với **ODM** (Object Directory Mapping), cần seed entry theo annotation và schema mà entity định nghĩa:

- `@Entry`/objectClasses cần khớp với `objectClass` có trong entry.
- `@Id` và DN phải thống nhất về base và cấu trúc RDN.
- `@Attribute` cần tương ứng với tên thuộc tính LDAP và cách biểu diễn dữ liệu (một hay nhiều giá trị).
- Khi test thao tác update/delete, cần dùng entry riêng để tránh phá dữ liệu của kịch bản khác.

Với xác thực, TLS và pooling, seed DIT chỉ giải quyết **dữ liệu thư mục**. Các bài test xác thực phải có tài khoản và mật khẩu giả phù hợp với server; các test TLS phải có listener, chứng chỉ và truststore test; các test pooling phải kiểm tra cơ chế cấp/đóng context dưới tải và lỗi kết nối thực tế. Không thể kết luận các yếu tố đó đúng chỉ vì tìm thấy một entry seeded.

## 9. Xử lý lỗi fixture thường gặp

| Dấu hiệu | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `NO_SUCH_OBJECT` hoặc `NameNotFoundException` | Entry cha chưa được seed; base DN sai | Tạo cha trước và phân biệt DN đầy đủ với DN tương đối |
| `OBJECT_CLASS_VIOLATION` | Thiếu `sn`/`cn`, objectClass không hợp lệ | Điều chỉnh fixture theo schema |
| `ENTRY_ALREADY_EXISTS` | Hai scenario dùng chung DN | Chọn một scenario hoặc đổi DN |
| User không được tìm thấy dù entry tồn tại | Sai search base, scope, filter hoặc uid | So sánh DIT thực tế với query |
| Test độc lập chạy được, chạy cả suite lại lỗi | Dữ liệu chia sẻ, cleanup thiếu, chạy song song | Tách server/namespace hoặc reset giữa test |
| LDIF import lần thứ hai xóa dữ liệu cũ | Gọi `importFromLDIF(true, ...)` nhiều lần | Import một snapshot đầy đủ hoặc thêm dữ liệu bằng API |
| Group search đúng nhưng quyền vẫn sai | Membership chưa liên kết ACL; server test khác production | Kiểm tra trên server có cấu hình ACL thực |
| Unicode bị sai khi import LDIF | Mã hóa file hoặc Base64 không hợp lệ | Sinh LDIF UTF-8 đúng chuẩn và kiểm tra giá trị sau import |
| CI không kết nối được server | Cổng cố định bị chiếm, listener sai interface, server chưa sẵn sàng | Chọn port 0, loopback, readiness check thích hợp |

Khi phát hiện lỗi, hãy kiểm tra **đường DN đầy đủ của entry đã nạp**, cấu trúc OU, danh sách thuộc tính, cấu hình base của `ContextSource` và filter được gửi tới server. Đừng sửa assertion để khớp dữ liệu tồn dư: phải sửa nguyên nhân gây fixture không xác định.

## 10. Bài tập và tiêu chí hoàn thành

1. Mở rộng DIT bằng `ou=service-accounts`. Tạo một test chỉ tìm dưới `ou=people` và khẳng định tài khoản dịch vụ không xuất hiện.
2. Tạo scenario có `uid=an` ở nhánh `ou=people` và người dùng khác ở `ou=contractors`. Kiểm tra `ONELEVEL_SCOPE` và `SUBTREE_SCOPE` với cùng một filter.
3. Tạo một scenario thiếu `mail`, một scenario có `mail` là chuỗi rỗng (nếu schema cho phép), và phân biệt chúng trong mapper.
4. Seed hai nhóm có thuộc tính `member` nhiều giá trị; viết test xác minh tập DN thành viên mà không dựa vào thứ tự.
5. Đưa fixture base và từng scenario vào LDIF. Kiểm tra việc import nhiều lần không xóa nhầm base hay thêm entry trùng DN.
6. Viết một test update/delete entry do chính test tạo, sử dụng `finally` để dọn dẹp. Chạy cả lớp test nhiều lần với thứ tự khác nhau.
7. Nếu môi trường đích là OpenLDAP hoặc Active Directory, đối chiếu schema, attribute và cơ chế phân quyền mà fixture UnboundID chưa thể mô phỏng chính xác.

**Tiêu chí hoàn thành:** người học giải thích được DIT, DN và RDN; phân biệt base fixture với scenario fixture; seed entry hợp lệ có quan hệ cha–con bằng Java hoặc LDIF; kiểm thử tìm kiếm, scope, thuộc tính tùy chọn, nhóm và lỗi DN/schema; đồng thời bảo đảm dữ liệu của từng integration test Spring LDAP có thể tái tạo, cô lập và dọn dẹp an toàn.

