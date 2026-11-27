# Kiểm thử search scope, filter và DN

Trong **Spring LDAP**, tìm kiếm một entry phụ thuộc đồng thời vào ba yếu tố: **search base (DN bắt đầu)**, **search scope (phạm vi duyệt cây)** và **LDAP filter (điều kiện lọc)**. Chỉ cần sai một yếu tố, ứng dụng có thể không tìm thấy tài khoản hợp lệ, trả dư người dùng thuộc nhánh khác hoặc diễn giải sai dữ liệu nhập vào. Kiểm thử ba yếu tố này là một phần thiết yếu của chương **Testing** trong module **SPRING_LDAP**.

Bài học xây dựng một cây thư mục LDAP cố định, chạy các yêu cầu tìm kiếm bằng `LdapTemplate` thật với UnboundID In-Memory Directory Server, sau đó kiểm chứng kết quả ở từng scope, sự an toàn của filter và việc sử dụng DN. Các nguyên tắc cũng áp dụng cho `LdapClient` hoặc ODM khi truy cập thư mục bằng Spring LDAP. Phần xác thực, TLS, pooling và phân quyền vẫn cần các phép kiểm thử tương ứng; một truy vấn chạy đúng trên server test chưa chứng minh cấu hình môi trường vận hành an toàn.

## 1. Hiểu ba thành phần của phép tìm kiếm LDAP

Một yêu cầu tìm kiếm thông thường có thể xem là bộ ba:

```text
                   SEARCH REQUEST
    ┌────────────────────────────────────┐
    │ Base DN  : ou=people,...           │
    │ Scope    : BASE / ONELEVEL / SUBTREE│
    │ Filter   : (uid=an)                 │
    └────────────────────────────────────┘
                      │
                      ▼
                 LDAP server
                      │
                      ▼
              Các entry phù hợp
                      │
                      ▼
          AttributesMapper / DTO
```

| Thành phần | Quyết định điều gì? | Lỗi phổ biến |
| --- | --- | --- |
| **Base DN** | Entry nào là gốc của vùng tìm kiếm | Thiếu hoặc gắn lặp suffix; tìm nhầm OU |
| **Search scope** | Tìm ngay tại base, chỉ các con trực tiếp hay toàn bộ cây con | `ONELEVEL_SCOPE` bị thay nhầm bằng `SUBTREE_SCOPE` |
| **LDAP filter** | Entry nào trong phạm vi được chọn thỏa điều kiện | Ghép chuỗi từ input không escape; nhầm dấu `*` với ký tự thông thường |
| **Mapping** | Trường nào của entry được đưa vào Java object | Đọc nhầm attribute, hiểu sai thuộc tính nhiều giá trị hoặc DN |

Với Spring LDAP, `LdapQueryBuilder` giúp khai báo rõ base, scope và filter; `LdapTemplate.search(...)` gửi lệnh qua `ContextSource`. Để kết luận phép tìm kiếm đúng, cần kiểm tra **kết quả do LDAP server thực sự xử lý**, ngoài việc xác nhận mapper được gọi.

## 2. Thiết kế DIT khiến lỗi scope dễ bị phát hiện

**DIT** (*Directory Information Tree*) là cây các entry LDAP. Trong ví dụ, naming context là `dc=example,dc=org`:

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

Các DN đầy đủ:

| Entry | DN |
| --- | --- |
| Nhánh người dùng | `ou=people,dc=example,dc=org` |
| Người dùng An | `uid=an,ou=people,dc=example,dc=org` |
| Người dùng Bình | `uid=binh,ou=people,dc=example,dc=org` |
| Nhánh cộng tác viên | `ou=contractors,ou=people,dc=example,dc=org` |
| Người dùng ngoài | `uid=external,ou=contractors,ou=people,dc=example,dc=org` |
| Nhóm developers | `cn=developers,ou=groups,dc=example,dc=org` |

Chính entry `uid=external` nằm **sâu thêm một tầng** là chìa khóa để phân biệt tìm kiếm một cấp và toàn bộ cây. Nếu fixture chỉ có `an` và `binh` ở ngay dưới `ou=people`, hai loại scope rất dễ cho kết quả giống nhau, khiến test không bắt được lỗi.

Một test tốt phải thiết kế dữ liệu để **mỗi sai sót làm thay đổi kết quả quan sát được**. Không nên tạo một fixture lớn không liên quan rồi chỉ khẳng định “danh sách không rỗng”.

## 3. Search scope: BASE, ONELEVEL và SUBTREE

Trong JNDI, `SearchControls` định nghĩa ba hằng:

| JNDI / Spring LDAP | Ý nghĩa | Với base `ou=people` và filter `(objectClass=inetOrgPerson)` |
| --- | --- | --- |
| `SearchControls.OBJECT_SCOPE` | Chỉ xét chính entry base (*LDAP base scope*) | Không có user, vì base là `organizationalUnit` |
| `SearchControls.ONELEVEL_SCOPE` | Xét **con trực tiếp**, không xét base hoặc cháu | `an`, `binh` |
| `SearchControls.SUBTREE_SCOPE` | Xét base và **toàn bộ** entry bên dưới | `an`, `binh`, `external` |

Đổi base thành `uid=an,ou=people` với filter `(uid=an)` thì `OBJECT_SCOPE` trả về chính entry `an`. Vì vậy, không thể nói một scope luôn trả rỗng hay luôn trả kết quả: **base và filter** cũng tham gia quyết định.

Để kiểm thử scope, tối thiểu phải có cả entry con trực tiếp và entry cháu, đồng thời so sánh **chính xác tập DN hoặc UID trả về**. Tránh kiểm tra duy nhất `assertFalse(results.isEmpty())`.

### So sánh kết quả không phụ thuộc thứ tự LDAP

LDAP thông thường không cam kết thứ tự entry được server trả về khi không yêu cầu sắp xếp. Một assertion như `assertEquals(List.of("an", "binh"), actual)` có thể thất bại ngẫu nhiên dù tập kết quả đúng. Hãy kiểm tra kích thước và so sánh tập hợp:

```java
assertEquals(2, actual.size());
assertEquals(Set.of("an", "binh"), Set.copyOf(actual));
```

Kiểm tra kích thước riêng giúp phát hiện cả trường hợp có kết quả trùng mà phép chuyển sang `Set` có thể che mất.

## 4. Dựng integration test với UnboundID và LdapTemplate

Ví dụ dùng **Java 17+**, Spring LDAP Core, UnboundID LDAP SDK và JUnit Jupiter. Dữ liệu LDAP được tạo trong bộ nhớ nhưng giao tiếp diễn ra qua **LDAP protocol và TCP loopback thật**; không mock `DirContext`.

Với Gradle, khi dự án đã quản lý phiên bản dependency:

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

Nếu không có BOM/dependency management, khai báo phiên bản tương thích cho các dependency trên. Các lớp `javax.naming.*` là JNDI của JDK; không cần thêm dependency riêng.

Tạo file `src/test/java/com/example/ldap/SearchScopeFilterDnTest.java`. Mỗi test có server riêng, vì vậy việc tạo DN mới trong một test không ảnh hưởng test khác. Đoạn mã sau là **một lớp kiểm thử hoàn chỉnh**:

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
import javax.naming.directory.SearchControls;
import javax.naming.ldap.LdapName;
import javax.naming.ldap.Rdn;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.core.support.LdapContextSource;

class SearchScopeFilterDnTest {

    private static final String BASE = "dc=example,dc=org";
    private static final String PEOPLE = "ou=people," + BASE;
    private static final String ADMIN_DN = "cn=Directory Manager";
    private static final String PASSWORD = "local-test-only";

    private InMemoryDirectoryServer server;
    private LdapTemplate ldap;

    @BeforeEach
    void startServer() throws Exception {
        InMemoryDirectoryServerConfig config =
                new InMemoryDirectoryServerConfig(BASE);

        config.setListenerConfigs(
                InMemoryListenerConfig.createLDAPConfig(
                        "test-ldap",
                        InetAddress.getByName("127.0.0.1"),
                        0,
                        null
                )
        );
        config.addAdditionalBindCredentials(ADMIN_DN, PASSWORD);

        server = new InMemoryDirectoryServer(config);
        try {
            server.startListening();

            // Tạo entry cha trước khi tạo entry con.
            server.addEntries(
                    new Entry(BASE,
                            new Attribute("objectClass", "top", "domain"),
                            new Attribute("dc", "example")),

                    new Entry(PEOPLE,
                            new Attribute("objectClass", "top",
                                    "organizationalUnit"),
                            new Attribute("ou", "people")),

                    person("uid=an," + PEOPLE, "an", "Nguyễn An", "Nguyễn"),
                    person("uid=binh," + PEOPLE, "binh",
                            "Bình Trần", "Trần"),

                    new Entry("ou=contractors," + PEOPLE,
                            new Attribute("objectClass", "top",
                                    "organizationalUnit"),
                            new Attribute("ou", "contractors")),

                    person("uid=external,ou=contractors," + PEOPLE,
                            "external", "External User", "User"),

                    new Entry("ou=groups," + BASE,
                            new Attribute("objectClass", "top",
                                    "organizationalUnit"),
                            new Attribute("ou", "groups")),

                    new Entry("cn=developers,ou=groups," + BASE,
                            new Attribute("objectClass", "top",
                                    "groupOfNames"),
                            new Attribute("cn", "developers"),
                            new Attribute("member", "uid=an," + PEOPLE))
            );

            LdapContextSource source = new LdapContextSource();
            source.setUrl(
                    "ldap://127.0.0.1:" + server.getListenPort());
            source.setBase(BASE);
            source.setUserDn(ADMIN_DN);
            source.setPassword(PASSWORD);
            source.setPooled(false);
            source.afterPropertiesSet();

            ldap = new LdapTemplate(source);
        } catch (Exception e) {
            server.shutDown(true);
            throw e;
        }
    }

    private static Entry person(String dn, String uid, String cn, String sn) {
        return new Entry(
                dn,
                new Attribute("objectClass", "top", "person",
                        "organizationalPerson", "inetOrgPerson"),
                new Attribute("uid", uid),
                new Attribute("cn", cn),
                new Attribute("sn", sn)
        );
    }

    @AfterEach
    void stopServer() {
        if (server != null) {
            server.shutDown(true);
        }
    }

    private List<String> searchUserIds(String base, int scope) {
        return ldap.search(
                query()
                        .base(base)
                        .searchScope(scope)
                        .where("objectClass").is("inetOrgPerson"),
                (AttributesMapper<String>) attributes ->
                        (String) attributes.get("uid").get()
        );
    }

    private List<String> searchByUid(String uid) {
        return ldap.search(
                query()
                        .base("ou=people")
                        .searchScope(SearchControls.SUBTREE_SCOPE)
                        .where("uid").is(uid),
                (AttributesMapper<String>) attributes ->
                        (String) attributes.get("uid").get()
        );
    }

    @Test
    void baseScopeSearchesOnlyTheBaseEntry() {
        List<String> ous = ldap.search(
                query()
                        .base("ou=people")
                        .searchScope(SearchControls.OBJECT_SCOPE)
                        .where("objectClass").is("organizationalUnit"),
                (AttributesMapper<String>) attributes ->
                        (String) attributes.get("ou").get()
        );

        assertEquals(List.of("people"), ous);

        // Cũng dùng BASE scope, nhưng base là entry của user.
        List<String> user = ldap.search(
                query()
                        .base("uid=an,ou=people")
                        .searchScope(SearchControls.OBJECT_SCOPE)
                        .where("uid").is("an"),
                (AttributesMapper<String>) attributes ->
                        (String) attributes.get("uid").get()
        );

        assertEquals(List.of("an"), user);
    }

    @Test
    void oneLevelExcludesGrandchildrenAndOtherBranches() {
        List<String> actual = searchUserIds(
                "ou=people", SearchControls.ONELEVEL_SCOPE);

        assertEquals(2, actual.size());
        assertEquals(Set.of("an", "binh"), Set.copyOf(actual));
    }

    @Test
    void subtreeIncludesGrandchildren() {
        List<String> actual = searchUserIds(
                "ou=people", SearchControls.SUBTREE_SCOPE);

        assertEquals(3, actual.size());
        assertEquals(Set.of("an", "binh", "external"),
                Set.copyOf(actual));
    }

    @Test
    void aNarrowerBaseChangesTheCandidateSet() {
        List<String> actual = searchUserIds(
                "ou=contractors,ou=people",
                SearchControls.ONELEVEL_SCOPE);

        assertEquals(List.of("external"), actual);
    }

    @Test
    void escapedFilterValuesCannotBecomeWildcards() {
        assertEquals(List.of("an"), searchByUid("an"));

        // Nếu ghép (uid=*) bằng chuỗi, dấu * trở thành wildcard.
        // Query builder .is("*") phải coi nó là giá trị literal.
        assertTrue(searchByUid("*").isEmpty());

        // Chuỗi nhập vào chứa cú pháp filter vẫn chỉ là giá trị uid.
        assertTrue(searchByUid("an*)(uid=*").isEmpty());
    }

    @Test
    void dnEscapingAndFilterEscapingAreDifferent() throws Exception {
        String uid = "doe, jane";

        // Dấu phẩy là ký tự cần escape trong RDN.
        String relativeDnText = "uid="
                + Rdn.escapeValue(uid) + ",ou=people";
        LdapName relativeDn = new LdapName(relativeDnText);

        server.add(person(
                relativeDn + "," + BASE, uid, "Jane Doe", "Doe"));

        String viaDn = ldap.lookup(
                relativeDn,
                (AttributesMapper<String>) attributes ->
                        (String) attributes.get("uid").get()
        );

        assertEquals(uid, viaDn);

        // Với filter, dấu phẩy không đóng vai trò dấu phân tách DN.
        assertEquals(List.of(uid), searchByUid(uid));
    }

    @Test
    void otherOrganizationalUnitIsOutsidePeopleBase() {
        List<String> actual = searchUserIds(
                "ou=people", SearchControls.SUBTREE_SCOPE);

        // Entry nhóm có objectClass=groupOfNames và khác nhánh.
        assertEquals(3, actual.size());
        assertTrue(!actual.contains("developers"));
    }
}
```

**Đọc đúng ranh giới của fixture:** `server.addEntries(...)` nhận DN **đầy đủ** như `uid=an,ou=people,dc=example,dc=org`. Ngược lại, `LdapContextSource.setBase(BASE)` đã đặt suffix `dc=example,dc=org`, nên trong `query().base("ou=people")` và `ldap.lookup(new LdapName("uid=an,ou=people"), ...)` dùng **DN tương đối**. Đưa DN đầy đủ vào search base trong trường hợp này có thể làm gắn lặp suffix và dẫn tới lỗi `NameNotFoundException`.

**Đọc đúng phạm vi của kết quả:** test `oneLevelExcludesGrandchildrenAndOtherBranches` chỉ trả `an`, `binh` vì `external` là cháu, còn `developers` là entry của nhánh khác và thuộc objectClass khác. Test `subtreeIncludesGrandchildren` phải trả thêm `external`. Test chỉ nhìn số lượng mà không kiểm tra tập UID có thể bỏ sót trường hợp trả sai người dùng.

## 5. Kiểm thử filter: giá trị literal, wildcard và điều kiện kết hợp

LDAP filter có cú pháp riêng, được quy định trong RFC 4515. Một số ví dụ:

| Filter | Ý nghĩa |
| --- | --- |
| `(uid=an)` | So khớp giá trị `uid` bằng `an` theo matching rule |
| `(uid=*)` | Kiểm tra thuộc tính `uid` có mặt |
| `(uid=an*)` | So khớp giá trị bắt đầu bằng `an` theo substring matching |
| `(&(objectClass=inetOrgPerson)(uid=an))` | AND: hai điều kiện cùng đúng |
| `(|(uid=an)(uid=binh))` | OR: ít nhất một điều kiện đúng |
| `(!(uid=an))` | NOT: phủ định điều kiện |
| `(uid=\2a)` | Tìm **dấu sao literal** trong giá trị `uid`, không phải wildcard |

Vì `*` có thể đại diện wildcard, hai biểu thức `(uid=*)` và `(uid=\2a)` có ý nghĩa hoàn toàn khác. Đây là lý do test phải dùng cả giá trị bình thường và chuỗi chứa ký tự đặc biệt.

### Tạo filter an toàn với LdapQueryBuilder

Dữ liệu nhập từ HTTP request, form hoặc message queue **phải được coi là giá trị**, không được ghép trực tiếp vào cú pháp LDAP filter.

Không nên làm:

```java
// Input của người dùng có thể chứa *, (, ) hoặc dấu gạch chéo ngược.
String unsafeFilter = "(uid=" + userInput + ")";
```

Thay bằng:

```java
ldapTemplate.search(
        query()
                .base("ou=people")
                .searchScope(SearchControls.SUBTREE_SCOPE)
                .where("uid").is(userInput),
        (AttributesMapper<String>) attributes ->
                (String) attributes.get("cn").get()
);
```

`LdapQueryBuilder` xử lý escape filter value trước khi gửi đến LDAP server. Đối với **LDAP filter string** theo RFC 4515, các ký tự đặc biệt thường được escape như sau:

| Ký tự trong giá trị | Dạng escape trong filter |
| --- | --- |
| `*` | `\2a` |
| `(` | `\28` |
| `)` | `\29` |
| `\` | `\5c` |
| Byte NUL | `\00` |

Khi giá trị đầu vào thực sự là dấu `*`, `.is("*")` có ý nghĩa so khớp một chuỗi chứa dấu sao; nó không đồng nghĩa với điều kiện `(uid=*)`. Trong mã kiểm thử, `searchByUid("*")` phải trả rỗng vì fixture không có tài khoản nào mang UID bằng dấu sao.

Nếu nghiệp vụ thực sự cần tìm theo tiền tố hoặc ký tự đại diện, hãy thiết kế **chức năng substring search riêng**, giới hạn giá trị và tạo filter theo API hỗ trợ escape phù hợp. Không biến một phương thức “tìm UID chính xác” thành wildcard search bằng cách cho phép người dùng nhập một filter tùy ý.

### Kiểm thử filter bằng kết quả server và bằng quan sát lời gọi

Có hai cấp độ kiểm chứng bổ sung cho nhau:

- **Unit test repository với Mockito:** dùng `ArgumentCaptor` để bắt filter gửi đến `DirContext.search(...)`, xác minh base, scope và chuỗi filter cụ thể. Không cần LDAP server.
- **Integration test với embedded LDAP:** đặt fixture có kết quả phân biệt rõ literal và wildcard, gọi `LdapTemplate` thật, rồi so sánh kết quả server trả về. Đây là cách test trên dùng để xác minh ý nghĩa filter.

Filter đúng cú pháp chưa chắc có kết quả đúng trên server production: quy tắc so khớp giá trị và kiểu thuộc tính phụ thuộc **LDAP schema/matching rule**. Với thuộc tính đặc thù Active Directory hoặc OpenLDAP, cần test bổ sung trên server tương thích.

## 6. Kiểm thử DN và RDN: base tương đối, escaping và phân tích cấu trúc

**DN** gồm một hoặc nhiều **RDN**. Ví dụ:

```text
uid=an,ou=people,dc=example,dc=org
└─RDN ┘└─RDN─┘└──── base suffix ──┘
```

Vấn đề cần kiểm thử không chỉ là chuỗi DN trông có vẻ đúng. DN có cú pháp escape và thứ tự thành phần, trong khi `LdapContextSource` có thể tự bổ sung base suffix.

### DN đầy đủ và DN tương đối

Giả sử:

```java
LdapContextSource source = new LdapContextSource();
source.setBase("dc=example,dc=org");
```

Khi đó:

| Trường hợp | Giá trị |
| --- | --- |
| DN đầy đủ trong LDIF/UnboundID SDK | `uid=an,ou=people,dc=example,dc=org` |
| DN tương đối cho `LdapTemplate.lookup(...)` | `uid=an,ou=people` |
| Search base tương đối cho toàn bộ người dùng | `ou=people` |
| Search base tương đối cho cộng tác viên | `ou=contractors,ou=people` |

Không nên đoán cách gắn suffix từ chuỗi đường dẫn. Cần nhìn **cấu hình `ContextSource`**, dùng DN có cú pháp chuẩn và kiểm chứng trên server test. Khi thay đổi `ContextSource.setBase(...)`, các test về DN nên thất bại nếu code repository vẫn sử dụng base cũ.

### Escape DN khác escape filter

Một dấu phẩy trong **giá trị RDN** là ký tự cần escape, vì dấu phẩy không escape trong DN phân tách các RDN:

```text
uid=doe\, jane,ou=people,dc=example,dc=org
```

Đây là DN của **một** entry có `uid` bằng `doe, jane`. Nếu tách bằng `String.split(",")`, ứng dụng có thể chia sai tên người dùng thành nhiều RDN. Java/JNDI có `LdapName` và `Rdn.escapeValue(...)`, còn Spring LDAP cung cấp `LdapNameBuilder` để dựng DN có cấu trúc.

```java
String uid = "doe, jane";
LdapName safeRelativeDn = new LdapName(
        "uid=" + Rdn.escapeValue(uid) + ",ou=people");

System.out.println(safeRelativeDn);
// uid=doe\, jane,ou=people
```

Ngược lại, khi tìm theo **filter** `(uid=doe, jane)`, dấu phẩy chỉ là ký tự thông thường trong giá trị thuộc tính và không đóng vai trò phân tách RDN. Vì vậy:

- Dựng **DN/RDN** bằng `LdapName`, `Rdn.escapeValue(...)` hoặc `LdapNameBuilder`.
- Dựng **LDAP filter** bằng `LdapQueryBuilder` hoặc các lớp filter có xử lý escape.
- Không áp dụng escape filter cho DN, hoặc escape DN cho filter; hai cú pháp phục vụ hai mục đích khác nhau.

Khi dùng DN từ bên ngoài, ngoài việc escape RDN còn phải **giới hạn nhánh cha cho phép**. Chỉ kiểm tra DN đúng cú pháp không có nghĩa user được quyền đọc/ghi ở mọi OU.

### Một số ca test DN bổ sung

| Ca test | Input | Kỳ vọng |
| --- | --- | --- |
| Lookup DN tương đối | `uid=an,ou=people` | Tìm đúng entry `an` với `ContextSource` có base suffix |
| Tra cứu theo RDN chứa dấu phẩy | `uid=doe\, jane,ou=people` | Trả về UID `doe, jane` |
| Search sai OU | Base `ou=groups`, filter người dùng | Không trả người dùng dưới `ou=people` |
| Search đúng nhánh con | Base `ou=contractors,ou=people` | Chỉ trả thành viên của nhánh cộng tác viên |
| DN không hợp lệ | Chuỗi DN sai cú pháp | Bị parser hoặc server từ chối, không tự sửa bằng tách chuỗi |
| Entry có ký tự đặc biệt | RDN có `,`, `+`, dấu gạch chéo ngược hoặc khoảng trắng đặc biệt | Dựng/parsing theo cú pháp DN; lookup đúng entry |

Đối với ca DN không hợp lệ, có thể unit test `new LdapName(input)` và kiểm tra `InvalidNameException`. Khi test integration, hãy xác định rõ lỗi được phát hiện ở **bước parse DN** hay do server trả về, thay vì kỳ vọng mọi chuỗi sai đều đi tới LDAP server.

## 7. Test ranh giới tìm kiếm và các lỗi thường gặp

Việc tìm kiếm thất bại có thể xuất phát từ những nguyên nhân khác nhau dù cùng biểu hiện là “không thấy user”.

| Triệu chứng | Nguyên nhân cần kiểm tra | Bằng chứng nên thu thập |
| --- | --- | --- |
| Không tìm thấy entry ở OU con | Dùng `ONELEVEL_SCOPE` thay vì `SUBTREE_SCOPE` | DIT có entry cháu; test scope trả khác nhau |
| Tìm thấy quá nhiều entry | Base quá rộng, filter thành wildcard hoặc thiếu điều kiện | So sánh chính xác UID/DN; test input `*` |
| `NameNotFoundException` | Search base hoặc suffix không tồn tại | Đối chiếu DN đầy đủ với cấu hình `ContextSource` |
| `InvalidNameException` | DN/RDN sai cú pháp, ký tự chưa escape | Parse bằng `LdapName` trước khi gửi |
| Filter không hợp lệ | Ghép chuỗi filter thủ công hoặc escape sai | Dùng query builder; kiểm tra test ký tự đặc biệt |
| Filter đúng nhưng kết quả khác server đích | Matching rule/schema khác nhau | Test lại trên server tương thích môi trường vận hành |
| Test đôi lúc fail theo thứ tự kết quả | Giả định thứ tự entry từ LDAP server | Dùng so sánh tập hợp hoặc sort rõ ràng |
| Lỗi đọc thuộc tính | Mapper giả định attribute luôn tồn tại hoặc là `String` | Seed ca thiếu/tối đa nhiều giá trị và unit test mapper |
| Search trả rỗng dù entry hiện hữu | Tài khoản không có quyền đọc attribute/entry trên server thật | Kiểm thử phân quyền với account được cấu hình ACL |

**Phân biệt kết quả rỗng và lỗi:** một LDAP search hợp lệ không khớp entry có thể trả danh sách rỗng. Base không tồn tại, bind thất bại hoặc lỗi filter thường dẫn đến exception; không nên âm thầm chuyển mọi lỗi kết nối thành danh sách rỗng vì sẽ che dấu sự cố vận hành.

### Mức độ bao phủ của từng loại test

| Mục tiêu | Unit test không có server | Integration test UnboundID | Server test giống production |
| --- | --- | --- | --- |
| Mapper đọc thuộc tính chính xác | Phù hợp | Có | Có |
| Repository dựng base/scope/filter đúng | Mock có thể bắt tham số | Kiểm chứng kết quả thật | Kiểm chứng kết quả thật |
| Search scope theo DIT và filter phổ thông | Không kiểm chứng server | Phù hợp | Có thể kiểm tra thêm |
| Escape ký tự ở giá trị filter | Có thể bắt filter | Phù hợp | Phù hợp |
| Matching rule/schema riêng | Không | Có thể khác | Cần thiết |
| Xác thực/ACL/nhóm đặc thù | Không | Giới hạn | Cần thiết |
| TLS, referral, pooling và lỗi mạng | Mock lỗi ở tầng service | Một phần | Môi trường chuyên dụng |

Khi dùng Spring LDAP, các thao tác `LdapClient` và ODM vẫn phải được kiểm thử với **base DN và dữ liệu thật do server cung cấp** nếu muốn bảo đảm đường tích hợp của framework. Một unit test mapper xanh không đảm bảo rằng server trả đúng attributes khi sử dụng filter hoặc phạm vi khác.

## 8. Bài tập thực hành

1. Thêm một tài khoản `uid=anna` vào `ou=people`. Tạo test phân biệt so khớp UID chính xác với tìm kiếm theo tiền tố `an`, trong đó ký tự wildcard chỉ được đưa vào khi nghiệp vụ cho phép.
2. Chuyển `uid=external` từ `ou=contractors` lên `ou=people`. Chạy lại test `ONELEVEL_SCOPE` và giải thích vì sao tập kết quả thay đổi.
3. Thêm `ou=partners,ou=people` và người dùng bên dưới. Kiểm tra `SUBTREE_SCOPE` nhận đủ các nhánh, `ONELEVEL_SCOPE` chỉ nhận con trực tiếp.
4. Thêm entry có RDN chứa dấu phẩy hoặc dấu cộng. Dùng `Rdn.escapeValue` để dựng DN và `LdapName` để parse, sau đó `lookup` đúng entry.
5. Viết test xác nhận tìm kiếm ở base `ou=groups` không trả về entry dưới `ou=people`, kể cả khi filter UID trùng.
6. Kiểm thử đầu vào `*`, `(`, `)`, dấu gạch chéo ngược và ký tự Unicode qua `LdapQueryBuilder`. Xác nhận đây là **giá trị** cần so khớp.
7. Chạy lại các test với một LDAP server tương thích môi trường triển khai; kiểm tra các khác biệt về schema, matching rule, kết quả phân quyền và TLS.

**Tiêu chí hoàn thành:** người học thiết kế được DIT làm lộ lỗi scope, phân biệt chính xác `OBJECT_SCOPE`, `ONELEVEL_SCOPE` và `SUBTREE_SCOPE`; viết filter an toàn cho giá trị do người dùng nhập; sử dụng đúng DN tương đối/đầy đủ và escape RDN; dùng JUnit 5 cùng `LdapTemplate` thật để xác nhận kết quả trên server LDAP kiểm thử; và chỉ ra những hành vi còn phải xác minh trong môi trường tương thích production.

