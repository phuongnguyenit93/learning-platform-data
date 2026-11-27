# UnboundID hoặc server test tương thích LDAP

Khi phát triển với **Spring LDAP**, các bài kiểm thử `AttributesMapper` hoặc mock `ContextSource` giúp kiểm tra logic Java nhanh, nhưng chúng không xác minh được server thật có chấp nhận DN, schema, filter, thao tác tìm kiếm và cập nhật entry hay không. Để kiểm tra đường đi qua `LdapTemplate`, `LdapClient` hoặc ODM, cần một **LDAP server dành riêng cho kiểm thử**. Hai hướng phổ biến là chạy **UnboundID In-Memory Directory Server** ngay trong JVM hoặc chạy một server LDAP tương thích, chẳng hạn OpenLDAP, trong container/môi trường test.

Bài học thuộc chương **Testing** của module **SPRING_LDAP**. Trọng tâm là cách **lựa chọn server test phù hợp**, cấu hình một phép kiểm thử tích hợp bằng Java 17+, Spring LDAP và JUnit 5, kiểm soát dữ liệu/schema và hiểu chính xác giới hạn của kết quả kiểm thử. Các yêu cầu nâng cao về xác thực, TLS, pooling, phân quyền và xử lý lỗi phải được gắn với loại server thực tế đang vận hành.

## 1. Chọn server kiểm thử theo điều muốn chứng minh

Một phép kiểm thử tích hợp LDAP thường cần đi qua các lớp sau:

```text
JUnit 5
   │
   ▼
Repository / service của ứng dụng
   │
   ▼
LdapTemplate / LdapClient / ODM
   │
   ▼
LdapContextSource (JNDI)
   │
   ▼
TCP + LDAP protocol
   │
   ▼
Server test + schema + dữ liệu fixture
   │
   ▼
Kết quả, lỗi LDAP hoặc thay đổi entry
```

Phần quan trọng nhất không phải tên của thư viện server, mà là **hành vi test phải tương đồng đến mức nào với môi trường đích**.

| Phương án | Điểm mạnh | Giới hạn chính | Phù hợp với |
| --- | --- | --- | --- |
| **UnboundID In-Memory Directory Server** | Khởi động và dừng ngay trong JVM; cổng động; tạo entry bằng Java hoặc LDIF; chạy nhanh trên CI | Không mô phỏng đầy đủ đặc thù của Active Directory, OpenLDAP overlay hay quyền truy cập thực tế | Integration test cho DN, filter, search scope, bind, mapping, CRUD cơ bản |
| **Apache Directory Server (ApacheDS)** | LDAP server dựa trên Java, có thể chạy như tiến trình/server test; có schema và cách thực thi riêng | Thiết lập và quản trị test thường phức tạp hơn một server in-memory nhỏ | Kiểm tra với một LDAP implementation khác; tính tương thích giao thức |
| **OpenLDAP qua container** | Dùng implementation OpenLDAP thực; có thể cấu hình schema, ACL, overlay tương tự môi trường đích | Cần container runtime; image, khởi động và import dữ liệu phải kiểm soát | Ứng dụng triển khai với OpenLDAP |
| **389 Directory Server / OpenDJ / server LDAP tương ứng qua container hoặc VM** | Kiểm tra hành vi đặc thù của đúng loại server | Chi phí môi trường, cấu hình và bảo trì cao hơn | Ứng dụng phụ thuộc cơ chế riêng của server |
| **Active Directory trong test domain cô lập** | Kiểm chứng thực tế schema, bind, group membership và hành vi đặc thù AD | Không phải embedded server; cần hạ tầng riêng và quy trình reset dữ liệu | Ứng dụng triển khai với Active Directory |
| **Mock `ContextSource` hoặc `LdapOperations`** | Rất nhanh; test nhánh xử lý và lỗi có kiểm soát | Không thực thi LDAP protocol hay server-side filter | Unit test, không thay thế integration test |

**Nguyên tắc chọn:** dùng UnboundID làm lớp kiểm thử tích hợp nhanh nếu ứng dụng chỉ dựa trên khả năng LDAP thông dụng; bổ sung server cùng loại với production khi có ràng buộc về schema, ACL, matching rule, LDAP control, referral, TLS hoặc thông số kết nối đặc thù.

Testcontainers chỉ là công cụ **quản lý vòng đời container**, không phải LDAP server. Khi dùng Testcontainers, cần chọn image của một server cụ thể và biết cách cấu hình, nạp dữ liệu, kiểm tra readiness của image đó.

## 2. UnboundID In-Memory Directory Server là gì?

Thư viện `com.unboundid:unboundid-ldapsdk` có các lớp `InMemoryDirectoryServerConfig`, `InMemoryListenerConfig` và `InMemoryDirectoryServer`. Server chạy trong JVM, tiếp nhận client LDAP qua cổng TCP như một server thực, và xử lý các thao tác LDAP trên dữ liệu trong bộ nhớ.

Những API thường dùng:

| API | Vai trò |
| --- | --- |
| `InMemoryDirectoryServerConfig(baseDn)` | Khai báo một hoặc nhiều naming context |
| `config.setListenerConfigs(...)` | Chọn địa chỉ và cổng TCP để lắng nghe |
| `config.addAdditionalBindCredentials(dn, password)` | Tạo credential dùng để bind trong test |
| `new InMemoryDirectoryServer(config)` | Tạo một instance LDAP server |
| `server.startListening()` | Khởi động listener |
| `server.getListenPort()` | Lấy cổng TCP thực tế nếu dùng cổng động |
| `server.add(...)` / `server.addEntries(...)` | Nạp dữ liệu fixture |
| `server.importFromLDIF(...)` | Nhập dữ liệu từ LDIF |
| `server.shutDown(true)` | Dừng listener và đóng kết nối hiện có |

**Dùng cổng 0** để hệ điều hành chọn cổng trống, giúp test chạy lại hoặc chạy song song ổn định hơn. Nếu mã cần giới hạn listener vào máy cục bộ, hãy chỉ định `127.0.0.1` trong cấu hình thay vì chỉ dựa vào mặc định có thể lắng nghe trên mọi network interface.

UnboundID phù hợp với phép kiểm thử tương tác LDAP trong một JVM; song kết quả “test xanh” chỉ khẳng định ứng dụng tương tác đúng với **server và fixture đang dùng**. Ví dụ, việc `bind` bằng một tài khoản test không tự chứng minh tài khoản production có quyền sửa entry trên OpenLDAP hay Active Directory.

## 3. Chuẩn bị một dự án kiểm thử tối thiểu

Ví dụ bên dưới dùng Spring LDAP Core trực tiếp, không cần Spring Boot hay `@SpringBootTest`. Cần Java 17+, JUnit Jupiter và UnboundID LDAP SDK.

Với Gradle và dependency management đã có trong dự án:

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

Nếu dự án không quản lý phiên bản tự động, hãy khai báo các phiên bản tương thích và cố định chúng trong build. Các gói `javax.naming.*` là **JNDI có sẵn trong JDK**; ngay cả khi ứng dụng dùng Spring Framework phiên bản Jakarta, API JNDI trong mã mẫu vẫn thuộc `javax.naming`.

Ta sẽ dựng cây dữ liệu sau:

```text
dc=example,dc=org
└── ou=people
    ├── uid=an
    └── ou=contractors
        └── uid=external
```

Entry lồng trong `ou=contractors` giúp kiểm tra sự khác biệt giữa `ONELEVEL_SCOPE` và `SUBTREE_SCOPE`. Mỗi người dùng có `objectClass=inetOrgPerson` và thuộc tính cơ bản như `uid`, `cn`, `sn`.

## 4. Ví dụ JUnit 5 với server UnboundID và LdapTemplate thật

Tạo file `src/test/java/com/example/ldap/UnboundIdLdapIntegrationTest.java`. Đoạn mã sau tạo server trong `@BeforeAll`, khởi tạo `LdapContextSource` thật, nạp fixture và đóng server trong `@AfterAll`. Mọi thao tác `LdapTemplate` đều đi qua LDAP protocol.

```java
package com.example.ldap;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.ldap.query.LdapQueryBuilder.query;

import com.unboundid.ldap.listener.InMemoryDirectoryServer;
import com.unboundid.ldap.listener.InMemoryDirectoryServerConfig;
import com.unboundid.ldap.listener.InMemoryListenerConfig;
import com.unboundid.ldap.sdk.Attribute;
import com.unboundid.ldap.sdk.Entry;
import java.net.InetAddress;
import java.util.List;
import java.util.Set;
import java.util.HashSet;
import java.util.UUID;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.BasicAttributes;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;
import javax.naming.directory.SearchControls;
import javax.naming.ldap.LdapName;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.core.support.LdapContextSource;

class UnboundIdLdapIntegrationTest {

    private static final String BASE_DN = "dc=example,dc=org";
    private static final String ADMIN_DN = "cn=Directory Manager";
    private static final String ADMIN_PASSWORD = "only-for-tests";

    private static InMemoryDirectoryServer server;
    private static LdapTemplate ldap;

    @BeforeAll
    static void startServer() throws Exception {
        InMemoryDirectoryServerConfig config =
                new InMemoryDirectoryServerConfig(BASE_DN);

        config.setListenerConfigs(
                InMemoryListenerConfig.createLDAPConfig(
                        "test-ldap",
                        InetAddress.getByName("127.0.0.1"),
                        0,
                        null
                )
        );
        config.addAdditionalBindCredentials(ADMIN_DN, ADMIN_PASSWORD);

        server = new InMemoryDirectoryServer(config);
        try {
            // Nạp entry cha trước, rồi tới các entry con.
            server.addEntries(
                    new Entry(BASE_DN,
                            new Attribute("objectClass", "top", "domain"),
                            new Attribute("dc", "example")),

                    new Entry("ou=people," + BASE_DN,
                            new Attribute("objectClass", "top",
                                    "organizationalUnit"),
                            new Attribute("ou", "people")),

                    new Entry("uid=an,ou=people," + BASE_DN,
                            new Attribute("objectClass", "top", "person",
                                    "organizationalPerson", "inetOrgPerson"),
                            new Attribute("uid", "an"),
                            new Attribute("cn", "An Nguyen"),
                            new Attribute("sn", "Nguyen"),
                            new Attribute("mail", "an@example.org")),

                    new Entry("ou=contractors,ou=people," + BASE_DN,
                            new Attribute("objectClass", "top",
                                    "organizationalUnit"),
                            new Attribute("ou", "contractors")),

                    new Entry("uid=external,ou=contractors,ou=people,"
                                    + BASE_DN,
                            new Attribute("objectClass", "top", "person",
                                    "organizationalPerson", "inetOrgPerson"),
                            new Attribute("uid", "external"),
                            new Attribute("cn", "External User"),
                            new Attribute("sn", "User"))
            );

            server.startListening();

            LdapContextSource contextSource = new LdapContextSource();
            contextSource.setUrl(
                    "ldap://127.0.0.1:" + server.getListenPort());
            contextSource.setBase(BASE_DN);
            contextSource.setUserDn(ADMIN_DN);
            contextSource.setPassword(ADMIN_PASSWORD);
            contextSource.setPooled(false);
            contextSource.afterPropertiesSet();

            ldap = new LdapTemplate(contextSource);
        } catch (Exception e) {
            server.shutDown(true);
            throw e;
        }
    }

    @AfterAll
    static void stopServer() {
        if (server != null) {
            server.shutDown(true);
        }
    }

    @Test
    void searchesByUidUsingRealLdapProtocol() {
        List<String> names = ldap.search(
                query()
                        .base("ou=people")
                        .searchScope(SearchControls.SUBTREE_SCOPE)
                        .where("uid").is("an"),
                (AttributesMapper<String>) attributes ->
                        (String) attributes.get("cn").get()
        );

        assertEquals(List.of("An Nguyen"), names);
    }

    @Test
    void oneLevelAndSubtreeReturnDifferentResults() {
        List<String> directChildren = ldap.search(
                query()
                        .base("ou=people")
                        .searchScope(SearchControls.ONELEVEL_SCOPE)
                        .where("uid").is("external"),
                (AttributesMapper<String>) attributes ->
                        (String) attributes.get("uid").get()
        );

        List<String> entireSubtree = ldap.search(
                query()
                        .base("ou=people")
                        .searchScope(SearchControls.SUBTREE_SCOPE)
                        .where("uid").is("external"),
                (AttributesMapper<String>) attributes ->
                        (String) attributes.get("uid").get()
        );

        assertTrue(directChildren.isEmpty());
        assertEquals(Set.of("external"), new HashSet<>(entireSubtree));
    }

    @Test
    void filterBuilderEscapesSpecialCharacters() {
        List<String> results = ldap.search(
                query()
                        .base("ou=people")
                        .where("uid").is("an*)(uid=*"),
                (AttributesMapper<String>) attributes ->
                        (String) attributes.get("uid").get()
        );

        assertTrue(results.isEmpty());
    }

    @Test
    void createsModifiesReadsAndDeletesEntry() throws Exception {
        String uid = "it" + UUID.randomUUID().toString()
                .replace("-", "");
        LdapName dn = new LdapName("uid=" + uid + ",ou=people");

        BasicAttributes attributes = new BasicAttributes(true);
        BasicAttribute objectClasses = new BasicAttribute("objectClass");
        objectClasses.add("top");
        objectClasses.add("person");
        objectClasses.add("organizationalPerson");
        objectClasses.add("inetOrgPerson");

        attributes.put(objectClasses);
        attributes.put("uid", uid);
        attributes.put("cn", "Test Person");
        attributes.put("sn", "Person");

        ldap.bind(dn, null, attributes);
        try {
            ldap.modifyAttributes(dn, new ModificationItem[] {
                    new ModificationItem(
                            DirContext.ADD_ATTRIBUTE,
                            new BasicAttribute("mail", "it@example.org"))
            });

            String storedEmail = ldap.lookup(
                    dn,
                    (AttributesMapper<String>) attrs ->
                            (String) attrs.get("mail").get()
            );

            assertEquals("it@example.org", storedEmail);
        } finally {
            ldap.unbind(dn);
        }

        List<String> afterDelete = ldap.search(
                query()
                        .base("ou=people")
                        .where("uid").is(uid),
                (AttributesMapper<String>) attrs ->
                        (String) attrs.get("uid").get()
        );
        assertTrue(afterDelete.isEmpty());
    }
}
```

### Những gì ví dụ chứng minh

1. `LdapContextSource` kết nối vào một LDAP listener thật qua TCP loopback, dùng DN và mật khẩu test để bind.
2. `LdapTemplate.search(...)` gửi yêu cầu tìm kiếm đến server, nhận `Attributes` và dùng mapper tạo kết quả.
3. Scope tìm kiếm do **server** áp dụng: `ONELEVEL_SCOPE` không đi vào nhánh `ou=contractors`, còn `SUBTREE_SCOPE` có.
4. Query builder giữ input chứa ký tự đặc biệt ở vai trò **giá trị** thay vì cho phép trở thành cú pháp filter.
5. `bind`, `modifyAttributes`, `lookup` và `unbind` đi qua JNDI tới server và tác động lên cùng một entry.

Các lệnh `ldap.lookup(...)` hoặc `ldap.search(...)` trong mã ví dụ dùng DN **tương đối** với base `dc=example,dc=org` đã đặt trên `LdapContextSource`. Trong khi đó, fixture `Entry` nạp trực tiếp vào UnboundID phải dùng **DN đầy đủ**. Đây là một lỗi thường gặp: gắn suffix hai lần sẽ tạo DN sai.

Test ghi dùng `UUID` để không tranh chấp DN với test khác. Khối `finally` bảo đảm xóa entry ngay cả khi assertion bên trong thất bại. Với test có thể xóa cả entry cha, hãy dùng fixture riêng hoặc server riêng, tránh gây lỗi dây chuyền trong suite.

> **Phạm vi:** bốn test này là integration test thực sự ở mức LDAP protocol, nhưng vẫn không kiểm chứng ACL, TLS hoặc matching rule đặc thù của server production. Không nên suy từ một phép bind bằng credential test rằng quyền của tài khoản vận hành đã đúng.

## 5. LDIF: cách quản lý dữ liệu fixture có thể bảo trì

Khi fixture lớn hơn vài entry, viết từng `new Entry(...)` sẽ khó đọc. Hãy lưu dữ liệu dưới dạng **LDIF** và nạp vào server test. Ví dụ `src/test/resources/ldap/people.ldif`:

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
```

Có thể nạp file bằng API `importFromLDIF`. Với đường dẫn file thực tế có thể đọc được, ví dụ:

```java
server.importFromLDIF(true, ldifFilePath);
```

Tham số `true` yêu cầu xóa dữ liệu hiện tại trước khi import, nên chỉ dùng khi **được phép reset toàn bộ server test**. Đây là thao tác không phù hợp với môi trường LDAP dùng chung. Trong dự án có nhiều môi trường build, nên lấy dữ liệu từ classpath và sử dụng overload nhận `LDIFReader` để tránh phụ thuộc current working directory.

Fixture tốt cần thỏa các điểm sau:

- Entry cha xuất hiện trước entry con; DN duy nhất và đúng cú pháp.
- Chọn `objectClass` theo schema; ví dụ `person` thường yêu cầu cả `cn` và `sn`.
- Phân biệt thuộc tính một giá trị và nhiều giá trị; không giả định thứ tự của tập nhiều giá trị.
- Chuỗi ngoài ASCII hoặc các trường hợp cần escape phải được mã hóa theo quy tắc LDIF, chẳng hạn giá trị `cn:: ...` ở dạng Base64 UTF-8.
- Có tình huống dữ liệu thiếu thuộc tính tùy chọn, entry sâu nhiều cấp, ký tự đặc biệt và trường hợp không tìm thấy.
- Mọi tài khoản, địa chỉ email và mật khẩu trong fixture đều là dữ liệu giả.
- Không nạp dump LDAP sản xuất vào môi trường CI không phù hợp với chính sách dữ liệu.

Các **quy tắc schema** của UnboundID có thể khác server đích. Nếu cần kiểm thử schema tùy chỉnh, phải đưa schema tương ứng vào server test và kiểm tra test báo lỗi khi dữ liệu không hợp lệ, thay vì tắt kiểm tra schema chỉ để dễ import.

## 6. Khi nào nên chọn OpenLDAP hoặc server khác?

Nếu production sử dụng **OpenLDAP**, test trên OpenLDAP thường đáng tin cậy hơn đối với các phần phụ thuộc cấu hình:

- Cấu trúc naming context, schema bổ sung và attribute/objectClass riêng.
- ACL, nhóm quyền và chính sách bind theo cấu hình test.
- Overlay hoặc cơ chế xử lý dữ liệu đặc thù, chẳng hạn memberOf.
- Referral, LDAP controls, paging và matching rule cụ thể.
- Cơ chế StartTLS/LDAPS, cấu hình trust và chứng chỉ tương thích môi trường vận hành.

Với **Active Directory**, một test domain cô lập phù hợp hơn khi cần kiểm chứng `sAMAccountName`, `userPrincipalName`, group membership, thuộc tính hệ thống, cách xác thực hoặc các LDAP controls đặc thù AD. UnboundID không thể được coi là mô phỏng đầy đủ AD.

### Quy trình với container LDAP tương thích

Một container test nên được coi là tài nguyên tạm, do test suite quản lý:

```text
Bắt đầu suite
    │
    ├─ Khởi tạo container từ image đã được cố định phiên bản
    ├─ Cấu hình domain / schema / credential chỉ dành cho test
    ├─ Đợi server sẵn sàng bằng LDAP bind hoặc search thử
    ├─ Import LDIF theo đúng schema
    ├─ Lấy mapped host + mapped port
    ├─ Tạo LdapContextSource theo host + port đó
    │
    ▼
Chạy các integration test
    │
    ├─ Search / filter / scope
    ├─ Bind / authentication
    ├─ Modify / delete / mapper / ODM
    └─ Trường hợp lỗi và kiểm tra quyền
    │
    ▼
Dọn entry test → Dừng container → Thu hồi tài nguyên
```

Khi dùng **Testcontainers Java**, `GenericContainer` cho phép khởi tạo image LDAP, mở cổng 389 trong container và lấy cổng ngẫu nhiên từ `getMappedPort(389)`. Nhưng **biến môi trường, bind DN quản trị, lệnh import LDIF và readiness check phụ thuộc image**. Không nên sao chép cấu hình của image OpenLDAP sang ApacheDS hoặc 389 Directory Server rồi kỳ vọng chúng hoạt động giống nhau.

Hãy ưu tiên một lệnh kiểm tra readiness thực sự ở mức LDAP (ví dụ bind/search trên root DSE hoặc một entry biết trước) thay vì chỉ kiểm tra TCP port đã mở. Cổng mở chưa chắc schema đã nạp xong hoặc account đã sẵn sàng. Chọn tag/digest image rõ ràng để tránh kết quả thay đổi bất ngờ khi CI tải image mới.

Nếu hạ tầng không cho phép chạy Docker, có thể chạy LDAP server dưới dạng tiến trình riêng trong môi trường test, dùng VM hoặc một test directory tập trung. Cần cô lập namespace/DN, reset fixture và tránh để các suite ghi đè lẫn nhau.

## 7. Những ca kiểm thử nào nên chạy với từng server?

| Tình huống | UnboundID in-memory | Server cùng loại production |
| --- | --- | --- |
| Tìm kiếm theo DN, filter, base và scope | Ưu tiên chạy | Có thể chạy smoke test |
| Mapping kết quả bằng `AttributesMapper` / `ContextMapper` | Ưu tiên chạy | Kiểm tra thêm attribute thực tế |
| `LdapClient`, `LdapTemplate` bind/modify/unbind cơ bản | Ưu tiên chạy | Kiểm tra lại schema và ACL |
| ODM đọc/ghi entry từ annotation | Phù hợp nếu schema đủ | Cần thêm khi có thuộc tính/schema riêng |
| Schema riêng, matching rule, operational attribute | Có thể cần cấu hình thêm; độ trung thực giới hạn | Ưu tiên |
| Quyền tài khoản ứng dụng, group membership đặc thù | Không thể thay thế server đích | Bắt buộc nếu ứng dụng phụ thuộc |
| LDAPS/StartTLS và kiểm tra chứng chỉ | Cấu hình được test TLS nhưng chỉ phản ánh môi trường test | Cần test với cấu hình tương thích production |
| Pooling, retry, timeout, mất kết nối, referral | Chỉ kiểm tra một phần, có thể kết hợp fault injection | Cần test riêng theo hệ thống thực |
| CI chạy nhanh sau mỗi commit | Rất phù hợp | Chạy một tập nhỏ khi cần |
| Kiểm thử trước phát hành đối với phụ thuộc server cụ thể | Chưa đủ | Ưu tiên, có thể là bắt buộc |

Một hướng triển khai thường dùng là: unit test cho mapper và service → integration test nhanh với UnboundID → integration test chọn lọc với OpenLDAP/AD test environment → smoke test triển khai. Phần cuối chỉ dùng tài khoản và thư mục được cấp cho kiểm thử.

## 8. Xác thực, TLS và quyền truy cập trong server test

### Bind và tài khoản test

`config.addAdditionalBindCredentials(...)` cho phép UnboundID chấp nhận một DN/password đã khai báo. Đây là cách tiện lợi để chạy `LdapTemplate` với authenticated context. Nhưng nó **không tự tạo ra mô hình phân quyền tương đương production**.

Nếu cần kiểm thử “người dùng A được đọc nhưng không được sửa nhóm B”, hãy dùng LDAP server có ACL được cấu hình đúng với tình huống cần xác minh. Viết cả hai hướng: một ca thành công với quyền hợp lệ và một ca bị từ chối với quyền không hợp lệ.

### LDAP thường và LDAPS/StartTLS

Ví dụ ở phần 4 chỉ dùng `ldap://127.0.0.1:<port>` trong một test process cục bộ. Test ấy không chứng minh cấu hình TLS đang đúng. Nếu yêu cầu bảo mật có TLS, cần server listener hỗ trợ TLS, chứng chỉ test, truststore phía client và phép kiểm tra kết nối xác minh server identity.

Không tắt xác minh chứng chỉ hoặc dùng trust-all manager để làm cho một bài kiểm thử TLS “xanh” nếu mục tiêu chính là kiểm tra tính an toàn của TLS. Test chứng chỉ không hợp lệ cũng quan trọng như test chứng chỉ hợp lệ.

### Không rò rỉ dữ liệu hoặc credential

Dữ liệu test phải giả lập. Credential test không được sao chép sang cấu hình production. Không in password, token hoặc nội dung nhạy cảm trong log của pipeline. Với test cần kết nối đến một server ngoài JVM, tách credential qua secret của môi trường CI và bảo đảm test không thể xóa những DN nằm ngoài namespace được cấp.

## 9. Giữ integration test ổn định và có thể tái chạy

Các nguyên nhân gây flakiness phổ biến ở kiểm thử LDAP là dữ liệu tồn dư, cổng cố định, lệ thuộc thứ tự thực thi, kỳ vọng sai về dữ liệu nhiều giá trị, và khởi động server chưa sẵn sàng.

| Rủi ro | Biện pháp |
| --- | --- |
| Cổng bị chiếm | Dùng cổng `0`; lấy cổng thực tế sau khi listener khởi động |
| Server chạy trên mọi interface | Bind vào loopback trong kiểm thử local |
| Fixture bị test trước sửa | Dùng server/fixture riêng hoặc phục hồi trạng thái |
| Hai test tạo cùng DN | Dùng ID ngẫu nhiên và dọn entry trong `finally` |
| Test phụ thuộc thứ tự kết quả LDAP | So sánh theo `Set` hoặc yêu cầu sorting rõ ràng |
| Container chưa import xong | Health check có bind/search thật |
| DN bị lặp base suffix | Phân biệt DN đầy đủ trong LDIF và DN tương đối khi dùng `LdapTemplate` |
| Schema khác production | Chạy thêm test trên đúng server hoặc cấu hình schema phù hợp |
| Test dùng credential production | Thay bằng test secret và test directory cô lập |
| Cấu hình test tự kết nối nhầm LDAP công ty | Dùng profile test tường minh, URL và DN được kiểm soát |

Bản thân `LdapContextSource` không cần một lệnh “đóng server” riêng: các context được `LdapTemplate` tạo và giải phóng theo từng thao tác. Server UnboundID có vòng đời độc lập và phải được dừng bằng `server.shutDown(true)`. Khi có cấu hình pooling hoặc resource quản lý riêng, cần thêm bước hủy tài nguyên tương ứng theo thư viện đang dùng.

Chỉ báo rằng kiểm thử đã chạy khi thực tế có kết quả từ build. Việc đọc một đoạn code JUnit hoặc nhìn thấy bài viết này không thay thế chạy thử với dependency/version thực tế.

## 10. Bài tập thực hành

1. Dựa trên `UnboundIdLdapIntegrationTest`, bổ sung hai entry có thuộc tính `mail` khác nhau và xác minh filter tìm đúng một người.
2. Thêm một entry ở cấp con trực tiếp và một entry ở cấp cháu. Viết test chứng minh sự khác nhau giữa `ONELEVEL_SCOPE` và `SUBTREE_SCOPE`.
3. Thử import một LDIF có thiếu `sn` cho `person`, quan sát phản hồi của server test khi schema validation được bật; sửa fixture cho hợp lệ.
4. Bổ sung test tìm kiếm giá trị `uid` có ký tự `*`, `(`, `)`, dấu gạch chéo ngược để kiểm tra sử dụng filter builder an toàn.
5. Nếu ứng dụng triển khai trên OpenLDAP, chạy cùng phép tìm kiếm trong container OpenLDAP có schema và fixture tương ứng; ghi lại những khác biệt.
6. Liệt kê các tình huống phải kiểm chứng trên server đích: ACL, bind, paging, referral, group membership, TLS/LDAPS và pooling. Xác định test nào chạy mỗi commit và test nào chạy trước phát hành.

**Tiêu chí hoàn thành:** người học lựa chọn được UnboundID hoặc server kiểm thử phù hợp, tạo được LDAP server test có base DN và fixture rõ ràng, kết nối với Spring LDAP qua `LdapContextSource` thật, kiểm tra search/scope/CRUD bằng JUnit 5, giữ dữ liệu test cô lập và nhận diện đúng những hành vi chỉ có thể xác minh với server tương thích production.

## Tài liệu tra cứu

- [UnboundID — InMemoryDirectoryServer API](https://docs.ldap.com/ldap-sdk/docs/javadoc/com/unboundid/ldap/listener/InMemoryDirectoryServer.html)
- [UnboundID — InMemoryListenerConfig API](https://docs.ldap.com/ldap-sdk/docs/javadoc/com/unboundid/ldap/listener/InMemoryListenerConfig.html)
- [Spring LDAP — LdapTemplate API](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/LdapTemplate.html)
- [Spring LDAP — AbstractContextSource API](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/support/AbstractContextSource.html)

