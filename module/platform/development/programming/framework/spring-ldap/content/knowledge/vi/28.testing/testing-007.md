# Kiểm thử bind, modify, rename và delete

Trong **Spring LDAP**, các thao tác tạo, cập nhật, đổi tên và xóa entry làm thay đổi dữ liệu thư mục. Chỉ kiểm tra mapper hoặc mock `LdapTemplate` chưa đủ để biết ứng dụng tạo entry đúng schema, thay đổi đúng thuộc tính, xử lý DN mới sau khi rename hay xóa đúng entry. Cần một **integration test với LDAP server thật dành cho kiểm thử**, sử dụng dữ liệu giả, naming context riêng và quy trình dọn dẹp xác định.

Bài học trong chương **Testing** của module **SPRING_LDAP** hướng dẫn kiểm thử bốn thao tác `LdapTemplate.bind(...)`, `modifyAttributes(...)`, `rename(...)` và `unbind(...)` với UnboundID In-Memory Directory Server và JUnit 5. Các nguyên tắc cũng áp dụng khi ứng dụng sử dụng `LdapClient` hoặc ODM để thao tác entry. Ví dụ kiểm tra đường dữ liệu qua `LdapContextSource` và LDAP protocol; xác thực người dùng, TLS, pooling, ACL và chính sách riêng của server production cần được kiểm thử thêm trong môi trường phù hợp.

## 1. Hiểu đúng bốn thao tác và thuật ngữ LDAP

Tên phương thức trong Spring LDAP có thể dễ nhầm với những khái niệm khác. Đặc biệt, **`LdapTemplate.bind(...)` dùng để *tạo entry***; nó không phải thao tác đăng nhập hoặc xác thực tài khoản (*LDAP authentication bind*). Còn **`unbind(...)` là xóa entry**, không phải đăng xuất khỏi phiên kết nối.

| Thao tác Spring LDAP | Hành vi trên thư mục | Điều cần kiểm chứng |
| --- | --- | --- |
| `bind(dn, null, attributes)` | Tạo entry mới tại DN | Entry tồn tại, objectClass và thuộc tính đúng; DN trùng bị từ chối |
| `modifyAttributes(dn, modifications)` | Thay đổi thuộc tính của entry có sẵn | Giá trị sau khi thay đổi đúng; thuộc tính khác được giữ nguyên |
| `rename(oldDn, newDn)` | Đổi DN/RDN, tương ứng thao tác Modify DN của LDAP | DN mới tra cứu được, DN cũ không còn, dữ liệu cần giữ vẫn có mặt |
| `unbind(dn)` | Xóa entry tại DN | Entry không còn; thao tác xóa con/cha đúng theo chính sách server |

Khi một ứng dụng gọi `LdapTemplate`, đường đi khái quát là:

```text
JUnit 5 → Repository/service → LdapTemplate
                                  │
                                  ▼
                         LdapContextSource
                                  │
                                  ▼
                            JNDI DirContext
                                  │
                                  ▼
                       LDAP server dành cho test
                                  │
                         ┌────────┴────────┐
                         ▼                 ▼
                    Trạng thái DIT      LDAP result/error
                         │                 │
                         └────────┬────────┘
                                  ▼
                    Lookup/search xác minh hậu điều kiện
```

**DIT** (Directory Information Tree) là cây entry trong thư mục; **DN** là tên phân biệt duy nhất của mỗi entry. Trong ví dụ, `dc=example,dc=org` là suffix của thư mục test, còn `uid=an,ou=people` là DN tương đối với suffix đó. Nạp fixture trực tiếp vào server phải dùng DN đầy đủ; gọi `LdapTemplate` với `ContextSource` đã cấu hình base thường dùng DN tương đối.

## 2. Chuẩn bị dữ liệu và xác định hợp đồng kiểm thử

Giả sử ứng dụng quản lý người dùng dạng `inetOrgPerson`:

```text
dc=example,dc=org
└── ou=people
    ├── uid=an
    ├── uid=binh
    └── uid=temp-user  ← entry do từng test tạo riêng
```

Mỗi người dùng có các thuộc tính:

| Thuộc tính | Vai trò | Quy tắc dữ liệu test |
| --- | --- | --- |
| `objectClass` | Khai báo kiểu entry và schema | `top`, `person`, `organizationalPerson`, `inetOrgPerson` |
| `uid` | Mã người dùng, dùng làm RDN | Không trống; duy nhất trong cùng nhánh cha |
| `cn` | Tên hiển thị | Bắt buộc theo objectClass `person` |
| `sn` | Họ | Bắt buộc theo objectClass `person` |
| `mail` | Email | Tùy chọn; dùng để test thêm, sửa, xóa thuộc tính |

**Hợp đồng cần kiểm tra** nên viết trước khi code test:

- Tạo entry: tra cứu được DN vừa tạo; giá trị `uid`, `cn`, `sn` chính xác.
- Tạo trùng DN: server từ chối, entry gốc không bị ghi đè.
- Sửa entry: `ADD`, `REPLACE`, `REMOVE` thay đổi đúng thuộc tính; những trường không liên quan không đổi.
- Đổi DN: DN mới truy cập được, DN cũ không còn; `cn` vẫn giữ nguyên sau khi rename.
- Xóa entry: tìm kiếm không còn trả entry vừa xóa; dữ liệu ở nhánh khác không bị ảnh hưởng.
- Xử lý lỗi: entry không tồn tại, DN trùng, vi phạm schema hoặc xóa một nhánh đang có con phải được phát hiện rõ ràng.

Chỉ dùng dữ liệu giả và tài khoản quản trị test. Không để integration test truy cập hoặc sửa LDAP server vận hành.

## 3. Thiết lập JUnit 5, Spring LDAP và UnboundID

Ví dụ chạy với Java 17+, Spring LDAP Core, JUnit Jupiter và UnboundID LDAP SDK. Nếu dự án đã quản lý phiên bản qua BOM hoặc cấu hình build, Gradle có thể khai báo:

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

Nếu không có dependency management, hãy khai báo các phiên bản tương thích. Các API `javax.naming.directory.*` thuộc JNDI của JDK, không phải thư viện mock riêng.

Để test độc lập, tạo một UnboundID server mới trong `@BeforeEach` và dừng trong `@AfterEach`:

```text
@BeforeEach
   ├─ Khởi tạo server trên loopback và cổng động
   ├─ Tạo dc=example,dc=org và ou=people
   └─ Tạo LdapContextSource + LdapTemplate thật
        │
        ▼
@Test
   ├─ Thực hiện bind / modify / rename / unbind
   └─ Lookup/search để kiểm tra trạng thái thực tế
        │
        ▼
@AfterEach
   └─ Dừng server và loại bỏ toàn bộ trạng thái test
```

Cách này tốn thời gian hơn tái sử dụng server cho toàn bộ suite, nhưng phù hợp để dạy hành vi ghi/xóa vì mỗi test bắt đầu từ cùng một DIT sạch. Cổng `0` để hệ điều hành chọn cổng trống; địa chỉ `127.0.0.1` tránh mở listener ra mạng ngoài.

## 4. Mã tích hợp đầy đủ: bind, modify, rename và delete

Tạo `src/test/java/com/example/ldap/EntryLifecycleIntegrationTest.java`. Đây là **một lớp JUnit 5 độc lập**; không cần Spring Boot ApplicationContext, mock JNDI hay LDAP server ngoài JVM. Tất cả lời gọi `ldap.*` được thực hiện qua giao thức LDAP thật.

```java
package com.example.ldap;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.ldap.query.LdapQueryBuilder.query;

import com.unboundid.ldap.listener.InMemoryDirectoryServer;
import com.unboundid.ldap.listener.InMemoryDirectoryServerConfig;
import com.unboundid.ldap.listener.InMemoryListenerConfig;
import com.unboundid.ldap.sdk.Attribute;
import com.unboundid.ldap.sdk.Entry;
import java.net.InetAddress;
import java.util.List;
import javax.naming.directory.Attributes;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.BasicAttributes;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;
import javax.naming.directory.SearchControls;
import javax.naming.ldap.LdapName;
import javax.naming.ldap.Rdn;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.core.support.LdapContextSource;

class EntryLifecycleIntegrationTest {

    private static final String BASE = "dc=example,dc=org";
    private static final String PEOPLE = "ou=people," + BASE;
    private static final String ADMIN = "cn=Directory Manager";
    private static final String PASSWORD = "test-password-only";

    private InMemoryDirectoryServer server;
    private LdapTemplate ldap;

    @BeforeEach
    void setUp() throws Exception {
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
        config.addAdditionalBindCredentials(ADMIN, PASSWORD);

        server = new InMemoryDirectoryServer(config);
        try {
            server.startListening();

            // Fixture nền: entry cha được tạo trước entry con.
            server.addEntries(
                    new Entry(BASE,
                            new Attribute("objectClass", "top", "domain"),
                            new Attribute("dc", "example")),
                    new Entry(PEOPLE,
                            new Attribute("objectClass", "top",
                                    "organizationalUnit"),
                            new Attribute("ou", "people"))
            );

            LdapContextSource source = new LdapContextSource();
            source.setUrl(
                    "ldap://127.0.0.1:" + server.getListenPort());
            source.setBase(BASE);
            source.setUserDn(ADMIN);
            source.setPassword(PASSWORD);
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

    private static LdapName dnFor(String uid) throws Exception {
        // Escape RDN theo cú pháp DN, kể cả khi uid chứa dấu phẩy.
        return new LdapName(
                "uid=" + Rdn.escapeValue(uid) + ",ou=people");
    }

    private static Attributes personAttributes(String uid) {
        BasicAttributes attrs = new BasicAttributes(true);

        BasicAttribute classes = new BasicAttribute("objectClass");
        classes.add("top");
        classes.add("person");
        classes.add("organizationalPerson");
        classes.add("inetOrgPerson");
        attrs.put(classes);

        attrs.put("uid", uid);
        attrs.put("cn", "Member " + uid);
        attrs.put("sn", "Member");
        return attrs;
    }

    private void createUser(String uid) throws Exception {
        ldap.bind(dnFor(uid), null, personAttributes(uid));
    }

    private String readString(LdapName dn, String attributeName) {
        return ldap.lookup(
                dn,
                (AttributesMapper<String>) attrs -> {
                    javax.naming.directory.Attribute value =
                            attrs.get(attributeName);
                    return value == null
                            ? null
                            : (String) value.get();
                }
        );
    }

    private boolean userExists(String uid) {
        List<String> ids = ldap.search(
                query()
                        .base("ou=people")
                        .searchScope(SearchControls.ONELEVEL_SCOPE)
                        .where("uid").is(uid),
                (AttributesMapper<String>) attrs ->
                        (String) attrs.get("uid").get()
        );
        return !ids.isEmpty();
    }

    @Test
    void bindCreatesEntryThatCanBeLookedUp() throws Exception {
        LdapName dn = dnFor("an");

        ldap.bind(dn, null, personAttributes("an"));

        assertTrue(userExists("an"));
        assertEquals("an", readString(dn, "uid"));
        assertEquals("Member an", readString(dn, "cn"));
        assertEquals("Member", readString(dn, "sn"));
    }

    @Test
    void duplicateBindFailsWithoutReplacingEntry() throws Exception {
        LdapName dn = dnFor("an");
        createUser("an");

        assertThrows(
                org.springframework.ldap.NameAlreadyBoundException.class,
                () -> ldap.bind(
                        dn, null, personAttributes("an"))
        );

        // Giá trị của entry ban đầu vẫn còn.
        assertEquals("Member an", readString(dn, "cn"));
    }

    @Test
    void modifyCanAddReplaceAndRemoveAnAttribute()
            throws Exception {
        LdapName dn = dnFor("binh");
        createUser("binh");

        ldap.modifyAttributes(dn, new ModificationItem[] {
                new ModificationItem(
                        DirContext.ADD_ATTRIBUTE,
                        new BasicAttribute("mail", "old@example.org"))
        });
        assertEquals("old@example.org", readString(dn, "mail"));

        ldap.modifyAttributes(dn, new ModificationItem[] {
                new ModificationItem(
                        DirContext.REPLACE_ATTRIBUTE,
                        new BasicAttribute("mail", "new@example.org"))
        });
        assertEquals("new@example.org", readString(dn, "mail"));

        ldap.modifyAttributes(dn, new ModificationItem[] {
                new ModificationItem(
                        DirContext.REMOVE_ATTRIBUTE,
                        new BasicAttribute("mail"))
        });
        assertNull(readString(dn, "mail"));

        // Những thuộc tính khác vẫn còn.
        assertEquals("Member binh", readString(dn, "cn"));
        assertEquals("Member", readString(dn, "sn"));
    }

    @Test
    void renameChangesDnAndPreservesOtherAttributes()
            throws Exception {
        LdapName oldDn = dnFor("before");
        LdapName newDn = dnFor("after");

        createUser("before");
        ldap.rename(oldDn, newDn);

        assertEquals("Member before", readString(newDn, "cn"));
        assertThrows(
                org.springframework.ldap.NameNotFoundException.class,
                () -> ldap.lookup(oldDn)
        );
    }

    @Test
    void deleteRemovesOnlyTheRequestedEntry() throws Exception {
        LdapName toDelete = dnFor("temp");
        LdapName toKeep = dnFor("keep");

        createUser("temp");
        createUser("keep");

        ldap.unbind(toDelete);

        assertFalse(userExists("temp"));
        assertTrue(userExists("keep"));
        assertEquals("Member keep", readString(toKeep, "cn"));
    }

    @Test
    void renamingMissingEntryReturnsAnError() throws Exception {
        LdapName missing = dnFor("missing");
        LdapName target = dnFor("target");

        assertThrows(
                org.springframework.ldap.NameNotFoundException.class,
                () -> ldap.rename(missing, target)
        );
        assertFalse(userExists("target"));
    }
}
```

### Những điều thực sự được kiểm chứng

| Test | Hành động được thực thi trên server | Hậu điều kiện |
| --- | --- | --- |
| `bindCreatesEntryThatCanBeLookedUp` | LDAP Add Entry | Entry mới tồn tại và các thuộc tính bắt buộc đọc đúng |
| `duplicateBindFailsWithoutReplacingEntry` | Thử Add Entry trùng DN | Có lỗi `NameAlreadyBoundException`; entry gốc không bị thay thế |
| `modifyCanAddReplaceAndRemoveAnAttribute` | LDAP Modify với ba kiểu thao tác | `mail` được thêm → thay giá trị → xóa; `cn` và `sn` không đổi |
| `renameChangesDnAndPreservesOtherAttributes` | LDAP Modify DN | Có thể lookup DN mới; DN cũ không còn; `cn` giữ nguyên |
| `deleteRemovesOnlyTheRequestedEntry` | LDAP Delete | Entry đích không còn; entry khác vẫn có |
| `renamingMissingEntryReturnsAnError` | Modify DN với DN nguồn không tồn tại | Báo `NameNotFoundException`; không tự tạo entry mới |

Điểm mạnh của kiểm thử này là **không lập trình sẵn kết quả trả về bằng Mockito**. Trạng thái sau thao tác được đọc lại từ server test qua `LdapTemplate`. Nếu thao tác không thành công, dữ liệu thiếu hoặc code dùng sai DN, assertion sẽ thất bại.

## 5. Kiểm thử bind: objectClass, DN và lỗi tạo trùng

Phương thức thường gặp:

```java
ldapTemplate.bind(dn, null, attributes);
```

Trong đó:

- `dn` chỉ ra vị trí của entry mới; nếu `ContextSource` đã đặt base suffix thì thường truyền DN tương đối.
- `null` là đối tượng Java không được dùng trong cách tạo entry chỉ dựa trên attributes.
- `attributes` chứa `objectClass` và các trường cần thiết cho schema.

Với `inetOrgPerson`, các objectClass kế thừa và các thuộc tính bắt buộc phải phù hợp. Không nên để test tự “qua” bằng cách tắt schema validation rồi dùng entry không hợp lệ: điều đó có thể che lỗi sẽ xuất hiện trên server production.

**Tạo trùng DN** phải thất bại theo hành vi LDAP Add Entry. Nếu nghiệp vụ muốn “tạo hoặc cập nhật”, cần thiết kế thao tác đó tường minh và kiểm thử cả hai nhánh. Không thay `bind` bằng `rebind` một cách vô thức; ghi đè entry hiện hữu có thể làm mất thuộc tính hoặc thay đổi schema.

### Bind thao tác entry khác với bind để xác thực

Một LDAP authentication bind xác nhận DN/password đối với server, thường đi qua việc tạo context hoặc API authenticate phù hợp. Nó khác `ldapTemplate.bind(dn, null, attributes)` dùng để tạo entry. Vì vậy test `bindCreatesEntryThatCanBeLookedUp` **không chứng minh xác thực người dùng thành công**. Muốn test xác thực, cần test riêng với account không có quyền quản trị và mật khẩu, kèm kịch bản sai mật khẩu hoặc tài khoản bị khóa nếu server hỗ trợ.

## 6. Kiểm thử modify: ADD, REPLACE và REMOVE

LDAP cho phép sửa thuộc tính của một entry mà không tạo entry mới. JNDI thể hiện thay đổi bằng `ModificationItem`:

| Kiểu | Ví dụ | Kết quả cần xét |
| --- | --- | --- |
| `DirContext.ADD_ATTRIBUTE` | Thêm `mail=old@example.org` | Giá trị/thuộc tính mới được thêm theo schema |
| `DirContext.REPLACE_ATTRIBUTE` | Thay `mail` thành `new@example.org` | Giá trị cũ bị thay bằng giá trị mới |
| `DirContext.REMOVE_ATTRIBUTE` | Xóa `mail` | Thuộc tính biến mất hoặc giá trị được chỉ định bị xóa |
 
Ví dụ thay email:

```java
ModificationItem replaceMail = new ModificationItem(
        DirContext.REPLACE_ATTRIBUTE,
        new BasicAttribute("mail", "new@example.org")
);

ldapTemplate.modifyAttributes(relativeDn, new ModificationItem[] {
        replaceMail
});
```

Để kiểm thử tốt:

1. **Đọc trước** giá trị gốc để có baseline.
2. Thực hiện thao tác modify.
3. **Đọc lại từ server** để xác nhận giá trị mong đợi.
4. Kiểm tra thêm một thuộc tính không liên quan để phát hiện thay đổi ngoài ý muốn.
5. Nếu thuộc tính có nhiều giá trị, so sánh theo tập hợp khi thứ tự không có ý nghĩa.

Đối với thuộc tính nhiều giá trị, `ADD_ATTRIBUTE` có thể thêm giá trị vào tập đang có, nhưng thêm một giá trị đã tồn tại có thể bị server từ chối. `REMOVE_ATTRIBUTE` với `BasicAttribute("member", "dn...")` thường xóa đúng giá trị đó; `REMOVE_ATTRIBUTE` chỉ có tên thuộc tính thường yêu cầu xóa toàn bộ thuộc tính. Cần xác minh chính xác trên schema và LDAP implementation dùng trong ứng dụng.

Không xóa `cn` hoặc `sn` ở entry `person` nếu schema yêu cầu chúng, trừ khi chủ đích của test là kiểm tra server từ chối vi phạm schema. Khi kiểm thử dữ liệu lỗi, hãy assert exception đúng thay vì sửa fixture chính cho invalid.

## 7. Kiểm thử rename: từ DN cũ sang DN mới

`ldapTemplate.rename(oldDn, newDn)` thực hiện đổi tên entry, tương ứng thao tác **Modify DN** của giao thức LDAP. Ví dụ:

```text
Trước:
uid=before,ou=people,dc=example,dc=org

Sau:
uid=after,ou=people,dc=example,dc=org
```

Trong mã JUnit ở phần 4, hai DN đều tương đối với `dc=example,dc=org` đã cấu hình trên `LdapContextSource`. Vì thế việc nối suffix vào cả `oldDn` và `newDn` ở tầng repository có thể tạo đường dẫn sai.

Sau khi rename, cần xác minh **cả hai phía**:

- **DN mới:** tra cứu được entry, những thuộc tính không phải RDN vẫn giữ nguyên.
- **DN cũ:** lookup thất bại (hoặc search theo vị trí cũ không còn kết quả).

Với đổi RDN từ `uid=before` thành `uid=after`, server có thể cập nhật giá trị thuộc tính `uid` theo quy tắc Modify DN và thiết lập `deleteOldRDN`. Điều quan trọng là kiểm tra thuộc tính RDN theo contract của ứng dụng và hành vi server mục tiêu; không mặc định mọi implementation sẽ giữ hay xóa giá trị RDN cũ giống nhau trong mọi cấu hình.

### Rename khác với modify thuộc tính hiển thị

Thay `cn` (tên hiển thị) qua `modifyAttributes(...)` không tự động đổi một DN có RDN `uid=...`. Ngược lại, đổi DN không có nghĩa tự động sửa email, tên hiển thị hay mọi thuộc tính phụ thuộc của ứng dụng.

Di chuyển entry sang OU khác cũng có thể được thực hiện thông qua Modify DN trong một số server, nhưng khả năng chuyển giữa các superior/naming context và cách xử lý con cháu phụ thuộc LDAP implementation. Với bài kiểm thử cơ bản, hãy bắt đầu bằng **rename trong cùng một OU** rồi bổ sung test di chuyển khi môi trường đích hỗ trợ rõ ràng.

### Tạo DN an toàn

Nếu RDN được tạo từ input, không ghép chuỗi trực tiếp khi giá trị chứa dấu phẩy hoặc dấu cộng:

```java
String uid = "doe, jane";
LdapName relativeDn = new LdapName(
        "uid=" + Rdn.escapeValue(uid) + ",ou=people"
);
```

Hãy dùng `LdapName`, `Rdn.escapeValue(...)` hoặc `LdapNameBuilder` cho DN; dùng `LdapQueryBuilder` cho **filter**. Escape DN và escape filter là hai cú pháp khác nhau. Ngoài kiểm tra cú pháp, ứng dụng cần giới hạn OU mà một tài khoản được phép sửa.

## 8. Kiểm thử delete: xóa đúng entry và không xóa nhầm nhánh

`LdapTemplate.unbind(dn)` tương ứng thao tác LDAP Delete. Khi xóa thành công:

- DN đã xóa không thể lookup.
- Search phù hợp không còn trả entry đó.
- Các entry khác trong cùng OU vẫn tồn tại.

Đó là lý do test `deleteRemovesOnlyTheRequestedEntry` tạo cả `temp` và `keep`. Nếu chỉ khẳng định search của `temp` trả rỗng, test chưa chứng minh thao tác không vô tình xóa những entry khác.

**Xóa một entry cha đang có entry con** thường bị server từ chối với lỗi non-leaf, vì LDAP Delete thông thường chỉ xóa một entry. Spring LDAP có các biến thể hỗ trợ xóa đệ quy tùy API/phiên bản, nhưng không nên sử dụng chúng trong test CRUD thông thường: xóa cả nhánh có thể làm mất dữ liệu fixture của test khác hoặc tác động đến server dùng chung.

Một test bổ sung nên tạo:

```text
ou=temporary,ou=people,dc=example,dc=org
└── uid=child,ou=temporary,ou=people,dc=example,dc=org
```

Sau đó thử `unbind("ou=temporary,ou=people")` bằng context tương đối và xác minh server từ chối vì còn entry con; xóa entry con trước rồi mới xóa OU. Đừng thử kịch bản xóa cây trên môi trường LDAP chia sẻ.

### Dọn dữ liệu bằng try/finally

Nếu dùng **server mới cho mỗi test** như ví dụ, `@AfterEach` dừng toàn bộ server và loại bỏ trạng thái. Nếu dùng một server chung cho nhiều test, cần cleanup ở cấp entry:

```java
LdapName dn = new LdapName("uid=temp,ou=people");

ldapTemplate.bind(dn, null, personAttributes("temp"));
try {
    // Assertions và các thao tác đang kiểm thử.
} finally {
    ldapTemplate.unbind(dn);
}
```

Đoạn này phù hợp khi entry vẫn tồn tại lúc đi vào `finally`. Nếu chính test đã xóa/rename entry hoặc thao tác thất bại giữa chừng, cleanup phải kiểm tra trạng thái và dùng **DN hiện tại**; tránh để exception lúc cleanup che lỗi kiểm thử ban đầu. Có thể chọn DN riêng bằng UUID và/hoặc đặt mỗi test trong OU riêng.

## 9. Kiểm thử lỗi và mức độ phù hợp của server

Không phải lỗi nào cũng kiểm thử được chỉ bằng fixture hợp lệ.

| Lỗi hoặc trường hợp | Cách gây lỗi trong test | Kết quả nên khẳng định |
| --- | --- | --- |
| Tạo entry trùng | `bind` hai lần với cùng DN | `NameAlreadyBoundException` hoặc lỗi LDAP tương ứng |
| Sửa entry không tồn tại | `modifyAttributes` với DN giả | `NameNotFoundException` hoặc exception được mapping phù hợp |
| Rename nguồn không tồn tại | `rename(missing, target)` | Không tạo entry đích; báo lỗi không tìm thấy |
| Rename tới DN đã dùng | Tạo hai entry rồi đổi DN đầu sang DN thứ hai | Server từ chối và hai entry không bị mất |
| Thiếu thuộc tính bắt buộc | Tạo `person` thiếu `sn` khi schema validation bật | Server từ chối thao tác Add Entry |
| Xóa entry cha còn con | Tạo OU + entry con, rồi xóa OU trước | Server trả lỗi non-leaf/context not empty |
| Không có quyền ghi | Dùng tài khoản ít quyền trên LDAP server có ACL | LDAP từ chối, dữ liệu không đổi |
| Mất kết nối khi modify | Test fault injection hoặc server integration có điều khiển | Ứng dụng xử lý lỗi; xác định trạng thái thực tế trước khi retry |

Khi kiểm thử bằng UnboundID, các lỗi cơ bản của giao thức và schema có thể được kiểm tra ở mức integration, nhưng quyền ACL, chính sách password, group membership và hành vi Active Directory/OpenLDAP có thể khác production. Nếu logic nghiệp vụ phụ thuộc ACL hoặc thuộc tính riêng, bổ sung test trên **server tương thích môi trường triển khai**.

### Tại sao retry thao tác ghi cần cẩn trọng?

Các lệnh ghi LDAP không phải lúc nào cũng **idempotent**:

- Thử lại `bind` sau khi server đã tạo entry có thể nhận lỗi DN trùng.
- Thử lại `ADD_ATTRIBUTE` có thể gặp lỗi giá trị đã tồn tại.
- Thử lại `rename` có thể gặp lỗi DN nguồn không còn.
- Thử lại `unbind` có thể gặp lỗi entry đã bị xóa.

Khi client mất kết nối sau lúc gửi lệnh, không được giả định server chưa thực hiện thay đổi. Một kịch bản integration nâng cao nên mô phỏng timeout/mất kết nối, đọc lại trạng thái bằng một context mới, rồi quyết định có nên retry. Không tự động lặp mọi lệnh ghi chỉ vì exception là lỗi mạng.

## 10. Phân biệt unit test, integration test và kiểm thử vận hành

| Mục tiêu | Phương pháp kiểm thử | Có cần LDAP server? |
| --- | --- | --- |
| Mapper đọc `Attributes` thành DTO | Dùng `BasicAttributes` trực tiếp | Không |
| Service gọi đúng thao tác `bind/modify/rename/unbind` | Mock `LdapOperations` hoặc repository | Không |
| Entry thật được tạo/sửa/đổi DN/xóa | `LdapTemplate` thật + UnboundID embedded | Có, loại nhúng |
| ODM ghi/đọc entry theo annotations | Integration test với LDAP schema thích hợp | Có |
| Phân quyền theo ACL sản xuất, account không có quyền | Server test cấu hình ACL tương thích | Có |
| LDAPS/StartTLS, certificate, timeout, pooling | Môi trường integration/staging được cấu hình tương ứng | Có |

Với `LdapClient`, vẫn cần xác minh trước/sau trên server thay vì chỉ assert rằng fluent API được gọi. Với ODM, phải kiểm tra annotation như `@Entry`, `@Attribute` và `@Id` thực sự tạo ra entry theo schema và DN dự kiến, kể cả khi rename hoặc delete.

Bài test dùng admin credential chỉ chứng minh thao tác thành công dưới quyền quản trị test; nó không thay thế phép thử xác thực tài khoản ứng dụng hoặc quyền ghi thực tế. Tương tự, UnboundID server chạy qua `ldap://127.0.0.1` trong ví dụ chưa xác minh TLS, truststore, pooling hay behavior khi có referral.

## 11. Các lỗi thường gặp khi chạy integration test

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `NameNotFoundException` ở `bind` | Thiếu OU cha hoặc base DN sai | Seed cha trước; so sánh DN tương đối với base của `ContextSource` |
| `NameAlreadyBoundException` | DN đã tồn tại từ test trước hoặc bind lặp | Server riêng, DN riêng, cleanup rõ ràng |
| Vi phạm `objectClass` | Thiếu `cn`/`sn` hoặc thuộc tính không được schema cho phép | Sửa fixture theo schema, không tắt validation một cách vô thức |
| Modify không có hiệu lực như mong đợi | Dùng `ADD` thay vì `REPLACE`; sai tên attribute | Kiểm tra `ModificationItem` và đọc lại từ server |
| Rename xong không tìm thấy entry | Sử dụng DN mới sai base/suffix hoặc RDN chưa escape | Dùng `LdapName`, xem lại `ContextSource.setBase(...)` |
| Delete thất bại vì còn entry con | Xóa OU trước khi xóa các entry con | Xóa con trước, kiểm tra phạm vi xóa |
| Test chạy riêng đạt nhưng chạy suite thất bại | Cùng DN hoặc cùng server bị các test khác sửa | Tách server/namespace hoặc reset fixture |
| Test khác kết quả giữa UnboundID và production | Schema/ACL/matching rule/implementation khác nhau | Test thêm trên LDAP server tương thích |
| Thông tin xác thực hiện trong log | Ghi credential test vào exception/log hoặc dùng account thật | Dùng credential giả, bảo vệ secret khi dùng server ngoài |

Khi lỗi xảy ra, phải phân biệt **thất bại ở bước seed**, **LDAP operation bị từ chối**, **mapper đọc sai dữ liệu**, và **cleanup không hoàn tất**. Đừng làm cho test xanh bằng cách mock luôn server trong một phép kiểm thử có mục tiêu chứng minh tương tác LDAP thực tế.

## 12. Bài tập thực hành

1. Thêm thuộc tính `telephoneNumber` vào một entry; test đủ ba biến thể `ADD_ATTRIBUTE`, `REPLACE_ATTRIBUTE` và `REMOVE_ATTRIBUTE` với dữ liệu hợp lệ theo schema.
2. Tạo hai entry có DN khác nhau. Thử rename entry thứ nhất sang DN của entry thứ hai và xác minh cả hai entry vẫn không bị ghi đè sau lỗi.
3. Thêm một OU tạm chứa người dùng. Viết test server từ chối xóa OU chưa rỗng; sau đó xóa người dùng rồi mới xóa OU.
4. Tạo một UID chứa dấu phẩy. Dùng `Rdn.escapeValue(...)`, `LdapName` rồi chạy chu trình create → lookup → rename → delete.
5. Thay một `uid` RDN và xác minh chính xác hành vi thuộc tính RDN trên LDAP implementation được sử dụng.
6. Chạy bộ test nhiều lần và theo thứ tự khác nhau. Chứng minh mỗi test có DIT ban đầu độc lập và không phụ thuộc trạng thái còn sót.
7. Nếu hệ thống có LDAP server đích, bổ sung một integration test dùng tài khoản quyền thấp để chứng minh thao tác modify/delete bị từ chối đúng theo ACL.

**Tiêu chí hoàn thành:** người học phân biệt được tạo entry với xác thực LDAP; có thể viết JUnit 5 cho `LdapTemplate.bind`, `modifyAttributes`, `rename` và `unbind` với server UnboundID thật; kiểm tra hậu điều kiện của từng thao tác bằng lookup/search; xử lý DN tương đối, schema và các lỗi phổ biến; đồng thời giữ dữ liệu test cô lập và nhận biết trường hợp phải kiểm tra thêm trên server production-compatible.

