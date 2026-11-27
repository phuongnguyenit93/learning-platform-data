# Đổi tên và di chuyển entry an toàn

Trong **Spring LDAP**, đổi tên một entry hoặc chuyển nó sang đơn vị tổ chức (OU) khác không đơn thuần là sửa một chuỗi DN. DN là địa chỉ của entry trong **Directory Information Tree (DIT)**; thay đổi DN có thể tác động đến đăng nhập, tìm kiếm theo base/scope, tham chiếu thành viên nhóm, cache, phân quyền và các hệ thống phụ thuộc. Nếu chỉ gọi `LdapTemplate.rename(...)` rồi trả thông báo thành công, ứng dụng có nguy cơ để lại **tham chiếu cũ** hoặc không phát hiện một thao tác đã hoàn tất một phần.

Bài **thực hành tổng hợp** của module **SPRING_LDAP** hướng dẫn xây dựng một quy trình có kiểm soát để **đổi RDN** trong cùng OU và **di chuyển entry** giữa các OU, kết hợp `LdapTemplate`, `LdapContextSource`, DN/RDN, schema, filter, kiểm tra quyền, xử lý lỗi và integration test. Ví dụ dùng **Java 17+, Spring LDAP Core, JUnit 5 và UnboundID In-Memory Directory Server**. Những kiểm thử về TLS, pooling, ACL hoặc hành vi riêng của LDAP server sản xuất cần môi trường tương thích riêng.

## 1. Bối cảnh và yêu cầu bài thực hành

Một tổ chức có người dùng `uid=an` trong nhánh nhân sự đang hoạt động:

```text
dc=example,dc=org
├── ou=people
│   └── uid=an
├── ou=alumni
└── ou=groups
    └── cn=reviewers
        member: uid=an,ou=people,dc=example,dc=org
```

Hệ thống phải hỗ trợ hai nghiệp vụ:

1. **Đổi tên định danh:** từ `uid=an,ou=people,...` thành `uid=an-new,ou=people,...`.
2. **Di chuyển người dùng:** từ `uid=an,ou=people,...` sang `uid=an,ou=alumni,...` khi người dùng rời nhóm nhân sự đang hoạt động.

Ở cả hai nghiệp vụ, cần bảo toàn dữ liệu hợp lệ như `cn`, `sn`, `mail`, xử lý DN đích đã tồn tại, và nhận biết tham chiếu nhóm `member` dùng **DN đầy đủ** có thể cần cập nhật.

**Hợp đồng an toàn:**

- Không tự ý di chuyển entry tới OU bất kỳ do client cung cấp.
- Kiểm tra DN nguồn, OU đích, quyền truy cập và va chạm trước khi thực hiện.
- Dựng DN bằng parser/builder để escape RDN đúng chuẩn.
- Không ghi đè entry đích nếu DN đã tồn tại.
- Sau khi đổi DN, kiểm tra entry dưới DN mới và xác nhận DN cũ không còn.
- Xem xét tất cả tham chiếu trỏ vào DN cũ; không giả định server sẽ cập nhật chúng.
- Xử lý được tình huống rename thành công nhưng một bước cập nhật tham chiếu thất bại.
- Có audit trail và kế hoạch đối soát/khôi phục theo mức độ rủi ro của hệ thống.

## 2. Phân biệt rename, move và modify attribute

Trong LDAP, thao tác **Modify DN** cho phép thay đổi RDN và, nếu server hỗ trợ, thay đổi parent DN (*newSuperior*). Với Spring LDAP/JNDI, API thường dùng là:

```java
ldapTemplate.rename(oldRelativeDn, newRelativeDn);
```

| Nghiệp vụ | DN trước | DN sau | Ý nghĩa |
| --- | --- | --- | --- |
| Đổi RDN | `uid=an,ou=people,...` | `uid=an-new,ou=people,...` | Thay RDN, giữ nguyên parent |
| Di chuyển OU | `uid=an,ou=people,...` | `uid=an,ou=alumni,...` | Giữ RDN, đổi parent |
| Đổi RDN và di chuyển | `uid=an,ou=people,...` | `uid=an-new,ou=alumni,...` | Thay cả RDN và parent |
| Đổi tên hiển thị | `cn=An Nguyen` thành `cn=An N.` | DN không đổi nếu RDN là `uid` | Sử dụng `modifyAttributes(...)`, không cần Modify DN |

Cần phân biệt **`LdapTemplate.rename(...)`** với **`modifyAttributes(...)`**. Sửa thuộc tính `cn` không có nghĩa entry sẽ tự chuyển DN. Ngược lại, đổi RDN `uid` có thể làm thay đổi giá trị attribute `uid` theo quy tắc *deleteOldRDN* và hành vi implementation. Hãy kiểm tra sau thao tác; không mặc định mọi server xử lý RDN attribute giống nhau.

**Giới hạn của server:** di chuyển giữa các OU trong cùng naming context thường khả thi khi server và ACL cho phép, nhưng di chuyển giữa các naming context hoặc qua referral/DSA khác có thể không được hỗ trợ. Không suy ra rằng việc `rename` hoạt động trên UnboundID có nghĩa Active Directory hoặc OpenLDAP đã được cấu hình hỗ trợ mọi kiểu move.

## 3. DN tương đối, DN đầy đủ và quy tắc escape

Giả sử `ContextSource` có cấu hình:

```java
LdapContextSource source = new LdapContextSource();
source.setBase("dc=example,dc=org");
```

Khi đó:

| Mục đích | DN |
| --- | --- |
| Nạp entry trực tiếp vào UnboundID hoặc LDIF | `uid=an,ou=people,dc=example,dc=org` |
| Truy vấn hoặc rename qua `LdapTemplate` với base trên | `uid=an,ou=people` |
| DN đích khi di chuyển tới alumni | `uid=an,ou=alumni` |
| Tham chiếu nhóm `member` trong dữ liệu LDAP | `uid=an,ou=people,dc=example,dc=org` (DN đầy đủ) |

Nếu truyền **DN đầy đủ** vào API đã làm việc tương đối với base của `ContextSource`, suffix có nguy cơ bị gắn lặp, tạo đường dẫn không tồn tại. Ngược lại, giá trị thuộc tính `member` của nhóm thường lưu **DN đầy đủ**, không phải tên tương đối của `LdapTemplate`.

### Dựng DN bằng LdapNameBuilder

Không ghép input trực tiếp:

```java
// Không an toàn: uid có thể chứa dấu phẩy, dấu cộng hoặc ký tự DN.
String dn = "uid=" + uidFromRequest + ",ou=people";
```

Dùng builder để escape giá trị RDN:

```java
import javax.naming.Name;
import org.springframework.ldap.support.LdapNameBuilder;

Name oldDn = LdapNameBuilder.newInstance("ou=people")
        .add("uid", "doe, jane")
        .build();

// DN tương đối hợp lệ, RDN chứa dấu phẩy đã được escape.
Name newDn = LdapNameBuilder.newInstance("ou=alumni")
        .add("uid", "doe, jane")
        .build();
```

Builder giải quyết **cú pháp DN**. Nó không tự kiểm tra rằng người gọi được quyền chọn OU nào. Cần giữ danh sách OU đích cho phép ở **tầng nghiệp vụ**, áp dụng authorization và kiểm soát giá trị đầu vào độc lập với thao tác escape.

Đừng dùng escape filter LDAP (ví dụ `\2a`) để escape DN; cú pháp filter và cú pháp DN là hai chuẩn khác nhau. Nếu cần tìm các nhóm chứa DN cũ, tạo filter bằng `LdapQueryBuilder.where("member").is(oldFullDn)` để xử lý filter value an toàn.

## 4. Thiết kế quy trình an toàn trước, trong và sau khi move

Một workflow đủ dùng cho bài thực hành:

```text
Yêu cầu đổi DN
      │
      ▼
Xác thực người gọi + kiểm tra quyền nghiệp vụ
      │
      ▼
Tính oldDn / newDn bằng DN builder, kiểm tra OU đích
      │
      ▼
Preflight: nguồn còn tồn tại? parent đích tồn tại?
           đích đã chiếm? schema/ACL có cho phép?
      │
      ▼
Ghi nhận snapshot tối thiểu của entry + tham chiếu liên quan
      │
      ▼
LDAP Modify DN: LdapTemplate.rename(oldDn, newDn)
      │
      ├── Lỗi → phân loại nguyên nhân, đọc lại trạng thái khi cần
      │
      ▼
Kiểm tra entry mới + absence của entry cũ
      │
      ▼
Cập nhật các tham chiếu chứa DN cũ (group member, metadata...)
      │
      ├── Lỗi → ghi nhận trạng thái chưa đồng bộ, đối soát / bù trừ
      │
      ▼
Xác minh search, mapping, group membership và quyền sau di chuyển
      │
      ▼
Audit thay đổi + kết quả
```

| Bước | Kiểm tra bắt buộc | Vì sao |
| --- | --- | --- |
| Authorization | Người gọi được đổi danh tính/OU đó không? | Tránh vượt quyền chỉ vì service account có quyền LDAP rộng |
| Đích cho phép | Parent DN nằm trong OU được phê duyệt | Ngăn di chuyển vào nhánh hệ thống hoặc nơi khác |
| Nguồn hợp lệ | Entry tồn tại, objectClass phù hợp | Tránh rename nhầm nhóm, máy hoặc OU |
| Parent đích | OU tồn tại và server cho phép move | Tránh lỗi `noSuchObject` |
| DN đích | Chưa tồn tại trong lần kiểm tra hiện tại | Giảm khả năng va chạm; bước này không loại bỏ race |
| Tham chiếu | Nhóm hoặc hệ thống nào dùng DN cũ? | Không tự giả định server cập nhật `member` |
| Hậu điều kiện | DN mới đọc được, DN cũ không còn | Phân biệt thành công thực tế với lời gọi vừa gửi |
| Đồng bộ | Tham chiếu đã trỏ đến DN mới và chính sách mới áp dụng | Rename có thể chỉ là một phần nghiệp vụ |

**Lưu ý cạnh tranh:** preflight “đích chưa tồn tại” và lệnh rename không phải một transaction duy nhất. Một tác nhân khác có thể tạo entry đích ở giữa hai bước (*time-of-check/time-of-use*). Phải **xử lý lỗi của chính lệnh rename** và đọc lại trạng thái khi cần, không chỉ dựa vào kiểm tra trước.

### Transaction và rollback có giới hạn

Modify DN là **một thao tác LDAP**, nhưng cập nhật group, cache hoặc hệ thống bên ngoài thường là **những thao tác riêng**. Không có lý do để giả định chúng nằm trong cùng một transaction phân tán. Nếu rename thành công, cập nhật `member` thất bại thì entry đã có DN mới nhưng tham chiếu có thể vẫn trỏ DN cũ.

Các lựa chọn xử lý lỗi:

- Đánh dấu trạng thái **cần đồng bộ** và có tác vụ retry/đối soát idempotent.
- Với phạm vi hẹp và điều kiện an toàn, thực hiện **compensating rename** về DN cũ; trước đó phải xác minh DN cũ chưa bị chiếm và entry đích vẫn là entry dự kiến.
- Nếu có hệ thống quản trị danh tính khác là nguồn dữ liệu chuẩn, thực hiện lại quy trình theo snapshot/version đã ghi nhận, không tự ý ghi đè dữ liệu mới.
- Ghi audit đủ để xác định thao tác nào đã thành công và thao tác nào chưa, tránh retry toàn bộ một cách mù quáng.

**Không khẳng định rollback tự động:** `LdapTemplate.rename(...)` không tự rollback cập nhật group thuộc một LDAP Modify riêng hay thao tác ở ứng dụng khác.

## 5. Viết lớp nghiệp vụ giới hạn đích và xây DN an toàn

Tạo `src/main/java/com/example/ldap/EntryRelocationService.java`. Ví dụ này chỉ cho phép hai thao tác được định nghĩa rõ, không nhận tùy ý một chuỗi DN đích do client gửi. Quyền nghiệp vụ phải được kiểm tra ở lớp gọi dịch vụ này hoặc qua cơ chế authorization riêng của ứng dụng.

```java
package com.example.ldap;

import javax.naming.Name;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

public final class EntryRelocationService {

    private final LdapTemplate ldap;

    public EntryRelocationService(LdapTemplate ldap) {
        this.ldap = ldap;
    }

    private static Name userDn(String ou, String uid) {
        if (uid == null || uid.isBlank()) {
            throw new IllegalArgumentException("uid must not be blank");
        }
        return LdapNameBuilder.newInstance(ou)
                .add("uid", uid)
                .build();
    }

    // Đổi uid, nhưng không đổi OU.
    public void renameWithinPeople(String oldUid, String newUid) {
        Name oldDn = userDn("ou=people", oldUid);
        Name newDn = userDn("ou=people", newUid);
        ldap.rename(oldDn, newDn);
    }

    // Chỉ cho phép chuyển từ people sang alumni.
    public void moveToAlumni(String uid) {
        Name oldDn = userDn("ou=people", uid);
        Name newDn = userDn("ou=alumni", uid);
        ldap.rename(oldDn, newDn);
    }
}
```

**Vì sao dịch vụ có ít tham số?** Người gọi chỉ định `uid`, còn đích hợp lệ được chọn từ phương thức nghiệp vụ. Cách này tránh nhận `newDn` hoàn toàn do client điều khiển. Nếu ứng dụng phải hỗ trợ nhiều OU, nên ánh xạ một enum/định danh đã được phê duyệt sang DN cấu hình cố định và kiểm tra authorization tương ứng.

**Giới hạn cố ý của ví dụ:** đây là lõi gọi Modify DN, chưa gồm preflight, audit, tham chiếu và bù trừ. Trong hệ thống thật, hãy bọc nó trong một workflow ứng dụng tuân thủ mục 4. Việc dùng service account có quyền sửa toàn bộ cây không thay thế authorization ở tầng nghiệp vụ.

## 6. Chuẩn bị môi trường thực hành UnboundID + JUnit 5

Bài tích hợp dùng **server LDAP nhúng hoạt động qua TCP thật**, không mock `ContextSource`. Dữ liệu khởi tạo:

```text
dc=example,dc=org
├── ou=people
│   └── uid=an                       cn=An Nguyen
├── ou=alumni
│   └── uid=taken                    cn=Existing User
└── ou=groups
    └── cn=reviewers                 member=uid=an,ou=people,dc=example,dc=org
```

Entry `uid=taken` là đích đã tồn tại để kiểm thử va chạm. Nhóm `cn=reviewers` chỉ có **một member**, giúp minh họa việc cập nhật giá trị bằng `REPLACE_ATTRIBUTE` mà không làm mất thành viên khác.

Dependency gợi ý cho dự án Gradle đã có BOM/dependency management:

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

Nếu chưa quản lý version, cần khai báo phiên bản tương thích. Các lớp `javax.naming.*` là API JNDI của JDK. Dùng Java 17+ và JUnit Jupiter; đặt test tại `src/test/java/com/example/ldap/EntryRelocationIntegrationTest.java`.

### Bộ kiểm thử tích hợp đầy đủ

```java
package com.example.ldap;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import com.unboundid.ldap.listener.InMemoryDirectoryServer;
import com.unboundid.ldap.listener.InMemoryDirectoryServerConfig;
import com.unboundid.ldap.listener.InMemoryListenerConfig;
import com.unboundid.ldap.sdk.Attribute;
import com.unboundid.ldap.sdk.Entry;
import java.net.InetAddress;
import javax.naming.Name;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.core.support.LdapContextSource;
import org.springframework.ldap.support.LdapNameBuilder;

class EntryRelocationIntegrationTest {

    private static final String BASE = "dc=example,dc=org";
    private static final String ADMIN_DN = "cn=Directory Manager";
    private static final String PASSWORD = "only-for-local-test";

    private static final String OLD_MEMBER_DN =
            "uid=an,ou=people," + BASE;
    private static final String MOVED_MEMBER_DN =
            "uid=an,ou=alumni," + BASE;

    private InMemoryDirectoryServer server;
    private LdapTemplate ldap;
    private EntryRelocationService service;

    private static Name userDn(String ou, String uid) {
        return LdapNameBuilder.newInstance(ou)
                .add("uid", uid)
                .build();
    }

    private static Entry person(
            String fullDn, String uid, String cn, String sn) {
        return new Entry(
                fullDn,
                new Attribute("objectClass", "top", "person",
                        "organizationalPerson", "inetOrgPerson"),
                new Attribute("uid", uid),
                new Attribute("cn", cn),
                new Attribute("sn", sn)
        );
    }

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
        config.addAdditionalBindCredentials(ADMIN_DN, PASSWORD);

        server = new InMemoryDirectoryServer(config);
        try {
            server.startListening();

            // Nạp cha trước con; mọi DN của UnboundID đều đầy đủ.
            server.addEntries(
                    new Entry(BASE,
                            new Attribute("objectClass", "top", "domain"),
                            new Attribute("dc", "example")),

                    new Entry("ou=people," + BASE,
                            new Attribute("objectClass", "top",
                                    "organizationalUnit"),
                            new Attribute("ou", "people")),

                    new Entry("ou=alumni," + BASE,
                            new Attribute("objectClass", "top",
                                    "organizationalUnit"),
                            new Attribute("ou", "alumni")),

                    new Entry("ou=groups," + BASE,
                            new Attribute("objectClass", "top",
                                    "organizationalUnit"),
                            new Attribute("ou", "groups")),

                    person(OLD_MEMBER_DN, "an", "An Nguyen", "Nguyen"),

                    person("uid=taken,ou=alumni," + BASE,
                            "taken", "Existing User", "User"),

                    new Entry("cn=reviewers,ou=groups," + BASE,
                            new Attribute("objectClass", "top",
                                    "groupOfNames"),
                            new Attribute("cn", "reviewers"),
                            new Attribute("member", OLD_MEMBER_DN))
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
            service = new EntryRelocationService(ldap);
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

    private String cnAt(Name relativeDn) {
        return ldap.lookup(
                relativeDn,
                (AttributesMapper<String>) attrs ->
                        (String) attrs.get("cn").get()
        );
    }

    private String groupMember() {
        Name groupDn = LdapNameBuilder.newInstance("ou=groups")
                .add("cn", "reviewers")
                .build();

        return ldap.lookup(
                groupDn,
                (AttributesMapper<String>) attrs ->
                        (String) attrs.get("member").get()
        );
    }

    @Test
    void renamesRdnWithinSameOu() {
        Name oldDn = userDn("ou=people", "an");
        Name newDn = userDn("ou=people", "an-new");

        service.renameWithinPeople("an", "an-new");

        assertEquals("An Nguyen", cnAt(newDn));
        assertThrows(
                org.springframework.ldap.NameNotFoundException.class,
                () -> ldap.lookup(oldDn)
        );
    }

    @Test
    void movesToAlumniButReferencesNeedSeparateUpdate() {
        Name oldDn = userDn("ou=people", "an");
        Name newDn = userDn("ou=alumni", "an");

        service.moveToAlumni("an");

        assertEquals("An Nguyen", cnAt(newDn));
        assertThrows(
                org.springframework.ldap.NameNotFoundException.class,
                () -> ldap.lookup(oldDn)
        );

        // Move không tự cam kết cập nhật member ở entry khác.
        assertEquals(OLD_MEMBER_DN, groupMember());

        Name groupDn = LdapNameBuilder.newInstance("ou=groups")
                .add("cn", "reviewers")
                .build();

        // Fixture này có đúng một member. Với nhiều member,
        // không thay cả attribute bằng một giá trị đơn.
        ldap.modifyAttributes(groupDn, new ModificationItem[] {
                new ModificationItem(
                        DirContext.REPLACE_ATTRIBUTE,
                        new BasicAttribute("member", MOVED_MEMBER_DN))
        });

        assertEquals(MOVED_MEMBER_DN, groupMember());
        assertEquals("An Nguyen", cnAt(newDn));
    }

    @Test
    void rejectsCollisionWithoutOverwritingTarget() {
        Name source = userDn("ou=people", "an");
        Name occupied = userDn("ou=alumni", "taken");

        assertThrows(
                org.springframework.ldap.NameAlreadyBoundException.class,
                () -> ldap.rename(source, occupied)
        );

        assertEquals("An Nguyen", cnAt(source));
        assertEquals("Existing User", cnAt(occupied));
    }

    @Test
    void escapesSpecialCharactersInRdn() throws Exception {
        String uid = "doe, jane";

        Name oldDn = userDn("ou=people", uid);
        Name newDn = userDn("ou=alumni", uid);

        // Thêm fixture với DN đầy đủ được dựng từ RDN đã escape.
        server.add(person(
                oldDn + "," + BASE, uid, "Jane Doe", "Doe"));

        service.moveToAlumni(uid);

        assertEquals("Jane Doe", cnAt(newDn));
        assertThrows(
                org.springframework.ldap.NameNotFoundException.class,
                () -> ldap.lookup(oldDn)
        );
    }

    @Test
    void rejectsMoveWhenSourceDoesNotExist() {
        Name missing = userDn("ou=people", "ghost");
        Name target = userDn("ou=alumni", "ghost");

        assertThrows(
                org.springframework.ldap.NameNotFoundException.class,
                () -> ldap.rename(missing, target)
        );

        assertThrows(
                org.springframework.ldap.NameNotFoundException.class,
                () -> ldap.lookup(target)
        );
    }
}
```

### Phân tích kết quả kỳ vọng

| Test | Điều được chứng minh | Tại sao quan trọng |
| --- | --- | --- |
| `renamesRdnWithinSameOu` | DN mới đọc được, DN cũ không còn, `cn` giữ nguyên | Đổi RDN khác với cập nhật tên hiển thị |
| `movesToAlumniButReferencesNeedSeparateUpdate` | Move thành công, `member` vẫn mang DN cũ cho đến khi sửa riêng | Không có giao dịch tự động bao gồm tất cả tham chiếu |
| `rejectsCollisionWithoutOverwritingTarget` | Đích đã tồn tại → server từ chối và cả hai entry vẫn còn | Tránh mất dữ liệu khi va chạm DN |
| `escapesSpecialCharactersInRdn` | UID chứa dấu phẩy vẫn tạo được DN và di chuyển đúng | Không phân tách DN bằng chuỗi |
| `rejectsMoveWhenSourceDoesNotExist` | Move lỗi, không tạo ra entry mới | Phát hiện thiếu nguồn thay vì báo thành công giả |

Bài test dùng UnboundID nên kết quả phản ánh server này. Với Active Directory, OpenLDAP có ACL, referral hoặc schema tùy chỉnh, cần xác minh cả thao tác move và chính sách trên **LDAP server tương thích với môi trường đích**. Bài tập không chạy thử trên thư mục dùng chung.

## 7. Tham chiếu nhóm và tính nhất quán sau khi đổi DN

Một entry nhóm có thể lưu:

```ldif
dn: cn=reviewers,ou=groups,dc=example,dc=org
objectClass: top
objectClass: groupOfNames
cn: reviewers
member: uid=an,ou=people,dc=example,dc=org
```

Nếu `uid=an` chuyển sang `ou=alumni`, giá trị `member` có thể vẫn chứa DN cũ. Việc server có tự cập nhật hay không phụ thuộc tính năng tham chiếu/refint, overlay/plugin, cấu hình và cơ chế nhóm. Không coi `memberOf` là thuộc tính luôn được tính sẵn hay tự sửa trong mọi server.

### Với nhóm có nhiều thành viên

**Không dùng `REPLACE_ATTRIBUTE` với một giá trị** nếu nhóm đang có nhiều `member`; làm vậy có thể xóa các thành viên khác. Thay vào đó, cần tìm mọi nhóm có member bằng DN cũ, rồi cập nhật từng nhóm một cách có kiểm soát.

Ví dụ một LDAP Modify request để thêm DN mới và loại bỏ DN cũ trên một nhóm đã xác định:

```java
ModificationItem[] changes = {
    new ModificationItem(
            DirContext.ADD_ATTRIBUTE,
            new BasicAttribute("member", newFullDn)),
    new ModificationItem(
            DirContext.REMOVE_ATTRIBUTE,
            new BasicAttribute("member", oldFullDn))
};

ldapTemplate.modifyAttributes(relativeGroupDn, changes);
```

Với LDAP server tuân thủ thao tác Modify, các modification của **một request trên một entry** được áp dụng nguyên khối hoặc bị từ chối theo điều kiện của server. Nhưng đó **không** tạo transaction chung với thao tác rename đã xảy ra trước đó, cũng không bảo đảm cập nhật hàng loạt nhiều nhóm là atomic.

Khi nhóm đã chứa sẵn DN mới, ADD có thể bị từ chối vì giá trị trùng; khi nhóm không còn DN cũ, REMOVE có thể thất bại. Workflow đối soát nên đọc trạng thái hiện tại và chỉ thực hiện thay đổi còn thiếu, rồi xác minh lại. Với ACL hạn chế, phải bảo đảm danh tính được dùng có quyền đọc/ghi member của đúng nhóm, không tự chuyển sang quyền quản trị cao hơn.

### Những nguồn tham chiếu khác

Bên cạnh `groupOfNames.member`, có thể có:

- Nhóm hoặc role lưu DN dưới tên thuộc tính khác theo schema.
- Ứng dụng lưu DN trong database, cache hoặc token/claim.
- Mapping ODM tham chiếu DN trong đối tượng Java.
- Danh sách kiểm soát truy cập, rule hoặc provisioning workflow phụ thuộc OU.
- Dịch vụ dùng `memberOf` hoặc quan hệ nhóm do server tự duy trì.

Vì vậy, cần **kiểm kê tham chiếu** trước khi quyết định rằng chỉ cập nhật một nhóm là đủ. Không log toàn bộ dữ liệu người dùng khi đối soát; sử dụng request ID, DN được bảo vệ theo chính sách và trạng thái từng bước.

## 8. Lỗi thường gặp khi rename và move

| Biểu hiện | Nguyên nhân có thể | Hành động chẩn đoán |
| --- | --- | --- |
| `NameNotFoundException` | Nguồn/parent đích không tồn tại, DN bị gắn lặp suffix | So sánh DN tương đối với `ContextSource.setBase(...)`; xác nhận OU |
| `NameAlreadyBoundException` | DN đích đã tồn tại | Không ghi đè; xác định collision/race và xử lý theo nghiệp vụ |
| `InvalidNameException` | RDN chưa escape hoặc DN sai cấu trúc | Dùng `LdapNameBuilder`/`LdapName` thay vì ghép chuỗi |
| `NoPermissionException` | Account bind không được rename hoặc di chuyển giữa OU | Kiểm tra ACL nguồn, đích và quyền Modify DN trên server đích |
| Rename thành công nhưng user không nằm trong group | `member` vẫn trỏ DN cũ, hoặc server không bật refint | Tìm tham chiếu theo DN cũ và cập nhật có kiểm soát |
| Rename xong mà ứng dụng vẫn tìm theo OU cũ | Repository search base/scope hoặc cache chưa cập nhật | Kiểm tra query base, scope, cache invalidation |
| RDN attribute có kết quả khác kỳ vọng | Chính sách *deleteOldRDN*, schema hoặc implementation | Đọc lại `uid` sau rename; đặt contract rõ ràng |
| Di chuyển giữa subtree thất bại | Server không hỗ trợ cross-naming-context move/referral | Kiểm tra phạm vi DSA và tài liệu server mục tiêu |
| Rename trả timeout/mất kết nối | Chưa rõ server đã hoàn tất thao tác hay chưa | Đọc lại DN nguồn/đích trước khi quyết định retry |
| Test chạy riêng đạt nhưng chạy suite lỗi | Entry/nhóm còn sót hoặc DN trùng giữa test | Server/namespace riêng, cleanup và seed lại fixture |

### Retry không mù quáng

Một lệnh Modify DN có thể đã được server xử lý trước khi client mất kết nối. Nếu retry ngay `rename(oldDn,newDn)`, DN nguồn có thể đã biến mất và nhận lỗi `noSuchObject`. Hãy truy vấn lại **cả DN cũ lẫn DN mới** bằng một kết nối mới, đối chiếu danh tính/thuộc tính hoặc ID ổn định, rồi quyết định khôi phục, tiếp tục cập nhật tham chiếu hay đưa vào hàng đợi xử lý thủ công. Tình huống “old không thấy, new thấy” không đủ nếu new có thể do tác nhân khác tạo; cần xác minh đúng entry theo dấu định danh tin cậy.

### Đặc biệt thận trọng khi move một OU

Di chuyển một OU có nhiều entry con có thể ảnh hưởng **toàn bộ DN của hậu duệ** và lượng lớn tham chiếu. Bài thực hành này cố ý dùng **một entry lá** để giảm rủi ro. Với move subtree, cần công cụ kiểm kê, kiểm tra ACL/referral/schema, kế hoạch downtime hoặc đồng bộ, giám sát và rollback được phê duyệt. Không sao chép đoạn code bài tập để chạy trên OU production.

## 9. Bảo mật và kiểm thử ngoài UnboundID

Các test trong bài dùng `ldap://127.0.0.1` và credential giả. Chúng kiểm chứng luồng cơ bản của giao thức LDAP với UnboundID, nhưng không chứng minh:

- **LDAPS/StartTLS:** chứng chỉ hợp lệ, hostname verification, truststore, lỗi handshake.
- **ACL production:** tài khoản thực tế có đủ quyền rename ở OU cũ và OU đích hoặc sửa nhóm.
- **Pooling:** context được tái sử dụng đúng danh tính, tài nguyên được đóng/trả về pool.
- **Server-specific behavior:** referential integrity overlay, group membership, password policy, matching rule, referral.
- **Business authorization:** user A có được phép tự di chuyển entry của user B hay không.

Cần kết hợp:

1. **Unit test:** validator, danh sách OU cho phép, quyền nghiệp vụ, quyết định retry/compensation.
2. **Integration test UnboundID:** DN, schema cơ bản, rename/move, collision, hậu điều kiện, thao tác modify nhóm.
3. **Integration test với LDAP cùng loại production:** ACL, TLS, refint, move giữa các nhánh thực tế, failure modes.
4. **Operational rehearsal:** audit, quan sát, đối soát dữ liệu và kế hoạch bù trừ trên môi trường test cô lập.

Chỉ dùng tài khoản test với quyền tối thiểu tương ứng từng kịch bản. Không thử move trên thư mục công ty khi chưa có môi trường và quyền cho phép. Không tắt kiểm tra certificate để làm test TLS thành công; không dùng log chứa mật khẩu hoặc thuộc tính nhạy cảm.

## 10. Bài tập mở rộng theo mức độ khó

1. **Đổi RDN:** tạo `uid=binh` trong `ou=people`, đổi thành `uid=binh-2`; kiểm tra DN mới, DN cũ, `cn`, `sn` và thuộc tính `uid` sau rename.
2. **Di chuyển có giới hạn:** bổ sung `ou=contractors` và whitelist các đích được phép. Viết unit test từ chối OU không có trong whitelist trước khi gọi LDAP.
3. **RDN đặc biệt:** dùng UID chứa dấu phẩy, dấu cộng và khoảng trắng theo quy tắc DN; xác minh `LdapNameBuilder` dựng DN hợp lệ và move thành công.
4. **Đích đã tồn tại:** cố di chuyển một entry vào DN đang có dữ liệu; khẳng định không entry nào bị ghi đè.
5. **Tham chiếu nhiều giá trị:** nhóm có ba `member`; đổi một người sang OU khác rồi cập nhật đúng một giá trị, bảo toàn hai thành viên còn lại.
6. **Thất bại sau rename:** giả lập một exception ở bước cập nhật nhóm, thiết kế trạng thái `PENDING_REFERENCE_UPDATE` và một tác vụ đối soát idempotent.
7. **Quyền ACL:** chạy cùng thao tác với tài khoản chỉ đọc và tài khoản có quyền Modify DN trên server có ACL thật; xác nhận lỗi và dữ liệu sau thao tác.
8. **Audit:** thiết kế event gồm ID yêu cầu, actor, DN cũ/mới, bước đã hoàn tất, kết quả và mã lỗi đã được che dữ liệu nhạy cảm.
9. **Khả năng phục hồi:** mô phỏng mất kết nối sau khi gửi rename; viết logic đọc lại nguồn/đích và xác minh ID ổn định trước khi retry.

### Checklist nghiệm thu

- [ ] Tính đúng DN nguồn/đích từ base của `ContextSource`; không gắn lặp suffix.
- [ ] Escape RDN bằng builder, không ghép giá trị chưa tin cậy.
- [ ] OU đích được giới hạn và actor đã được kiểm tra quyền nghiệp vụ.
- [ ] Nguồn/parent đích hợp lệ và collision được xử lý.
- [ ] Lệnh Modify DN chạy trên LDAP server test, DN mới tra cứu được.
- [ ] DN cũ không còn; các thuộc tính được giữ theo contract.
- [ ] Tham chiếu nhóm và các hệ thống phụ thuộc được rà soát/cập nhật.
- [ ] Có cách ghi nhận tình trạng cập nhật dở dang và đối soát/compensation.
- [ ] Test độc lập, dữ liệu giả, cleanup và logging an toàn.
- [ ] Những hành vi phụ thuộc ACL/TLS/referral/overlay được kiểm chứng trên server phù hợp.

**Tiêu chí hoàn thành:** người học giải thích được khác biệt giữa đổi RDN, di chuyển entry và sửa thuộc tính; triển khai được `LdapTemplate.rename(...)` với DN tương đối xây an toàn; xác minh trạng thái trước/sau trên LDAP test server; xử lý DN đích đã tồn tại, tham chiếu nhóm và lỗi cập nhật dở dang; đồng thời biết ranh giới giữa integration test UnboundID và các yêu cầu phải kiểm tra trên LDAP server của môi trường vận hành.

