# Kiểm thử authentication và quyền truy cập

Trong **Spring LDAP**, một kết nối LDAP thành công không đồng nghĩa với việc ứng dụng đã **xác thực đúng người dùng** hoặc **kiểm soát đúng quyền truy cập**. Một tài khoản có thể đăng nhập hợp lệ nhưng không được phép đọc thuộc tính nhạy cảm hay sửa entry. Ngược lại, một phép tìm kiếm trả kết quả qua tài khoản dịch vụ chưa chứng minh mật khẩu người dùng vừa nhập là đúng. Kiểm thử hai hành vi này cần xác định rõ **danh tính được dùng ở mỗi bước**, **thao tác nào được gửi đến server**, và **chính sách truy cập nào được cấu hình**.

Bài thuộc chương **Testing** của module **SPRING_LDAP**. Người học sẽ thực hành với `LdapContextSource`, `LdapTemplate.authenticate(...)` và JUnit 5; sau đó thiết kế bài kiểm thử quyền đọc/ghi trên một LDAP server có ACL. Những khái niệm này liên quan trực tiếp đến tìm kiếm bằng DN/filter, cấu hình `ContextSource`, TLS, pooling, xử lý lỗi và các thao tác entry bằng `LdapTemplate`, `LdapClient` hoặc ODM.

## 1. Phân biệt authentication và authorization

**Authentication (xác thực)** trả lời câu hỏi: *Danh tính này có thể chứng minh mình là ai không?* Với LDAP đơn giản, một client có thể thực hiện **LDAP simple bind** bằng DN và mật khẩu. Nếu server chấp nhận credentials, việc xác thực thành công theo cơ chế bind đó.

**Authorization (phân quyền)** trả lời câu hỏi: *Danh tính đã xác thực được phép thao tác gì trên entry hoặc thuộc tính nào?* Chính sách này thường nằm ở **ACL (Access Control List)** hoặc cơ chế tương đương của LDAP server. Nó có thể phụ thuộc DN người dùng, nhóm, OU, loại thao tác, thuộc tính và quy tắc riêng của server.

```text
Ứng dụng nhận uid + password
              │
              ▼
    [1] Tìm DN của người dùng
         bằng service account
              │
              ▼
    [2] Thử bind bằng DN + password
              │
        ┌─────┴─────┐
        │           │
      Sai         Đúng
        │           │
        ▼           ▼
   Từ chối      Đã xác thực
                    │
                    ▼
    [3] Kiểm tra quyền cho thao tác
           (search/read/modify/delete)
                    │
              ┌─────┴─────┐
              │           │
          Không đủ       Đủ quyền
              │           │
              ▼           ▼
           Từ chối     Cho phép
```

Bước [1] có thể do tài khoản dịch vụ thực hiện; bước [2] xác minh mật khẩu của người dùng; bước [3] sử dụng **danh tính thực sự được server dùng cho thao tác**. Nếu ứng dụng tiếp tục đọc/ghi bằng kết nối của **service account có quyền rộng**, quyền LDAP áp dụng là quyền của service account, không tự động là quyền của người dùng vừa đăng nhập. Ứng dụng cần có cơ chế phân quyền ở tầng nghiệp vụ hoặc thực hiện thao tác bằng context mang danh tính người dùng theo thiết kế bảo mật đã chọn.

| Mục tiêu | Hành vi cần kiểm thử | Kết luận hợp lệ |
| --- | --- | --- |
| Xác thực đúng mật khẩu | Bind DN người dùng với password đúng | Server chấp nhận credentials của DN đó |
| Từ chối mật khẩu sai | Bind với password khác | Server từ chối xác thực |
| Tài khoản không tồn tại | Tìm theo UID không có kết quả | Luồng đăng nhập thất bại an toàn |
| Input filter bất thường | UID chứa dấu sao, dấu ngoặc và ký tự escape | Input vẫn là giá trị của filter, không biến thành biểu thức khác |
| Quyền đọc | Thực hiện search/lookup với **tài khoản bị giới hạn** | Nhìn thấy đúng entry/thuộc tính policy cho phép |
| Quyền ghi | Thử modify/delete bằng tài khoản không có quyền | Server từ chối; dữ liệu không đổi |
| Tài khoản dịch vụ | Bind và tìm người dùng bằng service account | Chỉ chứng minh quyền của service account |

**Cẩn thận với tên phương thức:** `LdapTemplate.bind(dn, null, attributes)` trong Spring LDAP được dùng để **tạo entry**; nó không phải lời gọi xác thực người dùng. Để kiểm thử thông tin đăng nhập, dùng `LdapTemplate.authenticate(...)` hoặc tạo `DirContext` có DN/password và để server thực hiện bind.

## 2. Chọn server test theo loại bảo mật cần xác minh

Với một phần lớn quy trình đăng nhập, có thể dùng **UnboundID In-Memory Directory Server**. Server này hoạt động trong JVM và nhận kết nối LDAP qua TCP cục bộ, vì vậy nó thích hợp để kiểm tra việc tìm DN và thử bind bằng credential giả.

Tuy nhiên, test với UnboundID không mặc nhiên chứng minh hành vi **ACL của OpenLDAP, Active Directory hay LDAP server sản xuất**. Một số cơ chế truy cập và chính sách password phụ thuộc hoàn toàn vào implementation và cấu hình.

| Kịch bản | UnboundID in-memory | LDAP test server cùng loại production |
| --- | --- | --- |
| Xác thực user DN + password thông thường | Phù hợp | Nên xác minh thêm khi có yêu cầu riêng |
| Tìm DN bằng UID/filter an toàn | Phù hợp | Phù hợp |
| Mật khẩu sai, UID không tồn tại | Phù hợp | Phù hợp |
| DN, schema, tên thuộc tính cơ bản | Phù hợp nếu fixture tương ứng | Cần khi có schema riêng |
| ACL đọc/ghi theo DN/OU/attribute | **Không được suy ra từ kiểm thử bind** | Cần cấu hình chính sách thật để kiểm chứng |
| Chính sách lockout, expiration, password history | Không đại diện đầy đủ | Dùng server có chính sách tương ứng |
| Active Directory: UPN, trạng thái account, LDAP controls | Không phải bản sao AD | Test domain Active Directory cô lập |
| TLS certificate, StartTLS/LDAPS, pooling, referral | Cần hạ tầng test riêng phù hợp | Cần kiểm thử tương thích triển khai |

Trong bài, ta triển khai **bộ test xác thực với UnboundID** trước, rồi trình bày **hợp đồng và ví dụ kiểm thử ACL trên server khác**. Điều này giúp báo cáo kết quả không đánh đồng xác thực thành công với quyền truy cập đã được kiểm chứng.

## 3. Dữ liệu kiểm thử và thiết kế kịch bản đăng nhập

Giả sử naming context của LDAP test là `dc=example,dc=org`:

```text
dc=example,dc=org
└── ou=people
    ├── uid=an
    │   ├── cn: An Nguyen
    │   └── userPassword: <mật khẩu giả>
    └── uid=binh
        ├── cn: Binh Tran
        └── userPassword: <mật khẩu giả khác>
```

**Entry người dùng cần có `userPassword` và các thuộc tính hợp lệ theo schema** để server có thể thực hiện bind bằng DN của entry. Nếu userPassword ở production dùng cơ chế hash hoặc plugin riêng, phải chọn fixture và server tương thích; không lấy plaintext password của người thật làm dữ liệu test.

Các ca test tối thiểu:

| Ca kiểm thử | Đầu vào | Kỳ vọng |
| --- | --- | --- |
| Đúng mật khẩu | `an` + password của An | Xác thực thành công |
| Sai mật khẩu | `an` + password khác | Xác thực thất bại |
| Không tồn tại | `ghost` + password bất kỳ | Xác thực thất bại |
| Nhầm mật khẩu giữa user | `an` + password của Bình | Xác thực thất bại |
| Input có ký tự filter | UID `an*)(uid=*` | Không được biến thành query tìm người khác |
| Direct bind thành công | DN đầy đủ của An + password của An | Tạo được authenticated context |
| Direct bind sai password | DN đầy đủ của An + password sai | Server từ chối context |
| Hết quyền sửa entry | Reader DN + lệnh modify | Từ chối trên server có ACL thật; giá trị vẫn nguyên |

Kịch bản mật khẩu rỗng cần được thiết kế **riêng** và kiểm tra hành vi thư viện/server: trong LDAP, simple bind với mật khẩu rỗng có các quy tắc đặc biệt cho anonymous/unauthenticated bind. Ứng dụng đăng nhập thường nên **từ chối chuỗi rỗng trước khi gửi bind**, thay vì chấp nhận việc tạo được một context làm bằng chứng xác thực người dùng.

## 4. Dependency và quy trình test bằng JUnit 5

Ví dụ dùng Java 17+, Spring LDAP Core, JUnit Jupiter và UnboundID LDAP SDK. Nếu dự án đang dùng dependency management qua BOM:

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

Nếu chưa có BOM, hãy cố định phiên bản tương thích trong build. JNDI nằm trong Java qua `javax.naming.*` nên không cần thư viện JNDI riêng.

Chúng ta sẽ dùng server **mới cho mỗi phương thức JUnit**, với listener chỉ mở trên `127.0.0.1` và cổng động. Tài khoản `cn=Directory Manager` chỉ dùng để seed và thực hiện bước tìm kiếm trước khi authentication; password test là giá trị giả.

```text
@BeforeEach
    │
    ├─ Tạo UnboundID server, bind listener trên 127.0.0.1:0
    ├─ Seed dc=example,dc=org / ou=people
    ├─ Seed uid=an / uid=binh và userPassword
    └─ Khởi tạo LdapTemplate với service DN
    │
    ▼
@Test
    ├─ Tìm user DN từ uid
    ├─ Xác thực password bằng LDAP bind
    └─ Kiểm tra đúng/sai với assertions
    │
    ▼
@AfterEach
    └─ Dừng server, xóa trạng thái test
```

## 5. Ví dụ đầy đủ: xác thực với LdapTemplate và direct bind

Tạo file `src/test/java/com/example/ldap/LdapAuthenticationIntegrationTest.java`. Đoạn mã là **một lớp JUnit 5 tự chứa**, dùng `LdapTemplate` và `LdapContextSource` thật, không mock kết quả authentication.

```java
package com.example.ldap;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.ldap.query.LdapQueryBuilder.query;

import com.unboundid.ldap.listener.InMemoryDirectoryServer;
import com.unboundid.ldap.listener.InMemoryDirectoryServerConfig;
import com.unboundid.ldap.listener.InMemoryListenerConfig;
import com.unboundid.ldap.sdk.Attribute;
import com.unboundid.ldap.sdk.Entry;
import java.net.InetAddress;
import javax.naming.directory.Attributes;
import javax.naming.directory.DirContext;
import javax.naming.ldap.LdapName;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.core.support.LdapContextSource;

class LdapAuthenticationIntegrationTest {

    private static final String BASE = "dc=example,dc=org";
    private static final String PEOPLE = "ou=people," + BASE;
    private static final String ADMIN_DN = "cn=Directory Manager";
    private static final String ADMIN_PASSWORD = "test-admin-only";
    private static final String AN_DN = "uid=an," + PEOPLE;
    private static final String AN_PASSWORD = "an-test-password";
    private static final String BINH_PASSWORD = "binh-test-password";

    private InMemoryDirectoryServer server;
    private LdapTemplate ldap;
    private String ldapUrl;

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

        // Credential quản trị giả, dùng trong riêng server test.
        config.addAdditionalBindCredentials(ADMIN_DN, ADMIN_PASSWORD);

        server = new InMemoryDirectoryServer(config);
        try {
            server.startListening();

            server.addEntries(
                    new Entry(BASE,
                            new Attribute("objectClass", "top", "domain"),
                            new Attribute("dc", "example")),

                    new Entry(PEOPLE,
                            new Attribute("objectClass", "top",
                                    "organizationalUnit"),
                            new Attribute("ou", "people")),

                    new Entry(AN_DN,
                            new Attribute("objectClass", "top",
                                    "person", "organizationalPerson",
                                    "inetOrgPerson"),
                            new Attribute("uid", "an"),
                            new Attribute("cn", "An Nguyen"),
                            new Attribute("sn", "Nguyen"),
                            new Attribute("mail", "an@example.org"),
                            new Attribute("userPassword", AN_PASSWORD)),

                    new Entry("uid=binh," + PEOPLE,
                            new Attribute("objectClass", "top",
                                    "person", "organizationalPerson",
                                    "inetOrgPerson"),
                            new Attribute("uid", "binh"),
                            new Attribute("cn", "Binh Tran"),
                            new Attribute("sn", "Tran"),
                            new Attribute(
                                    "userPassword", BINH_PASSWORD))
            );

            ldapUrl = "ldap://127.0.0.1:" + server.getListenPort();

            // Tài khoản dịch vụ chỉ để tìm DN và khởi động luồng.
            LdapContextSource serviceContext =
                    contextSource(ADMIN_DN, ADMIN_PASSWORD);
            ldap = new LdapTemplate(serviceContext);
        } catch (Exception e) {
            server.shutDown(true);
            throw e;
        }
    }

    private LdapContextSource contextSource(
            String bindDn, String password) {

        LdapContextSource source = new LdapContextSource();
        source.setUrl(ldapUrl);
        source.setBase(BASE);
        source.setUserDn(bindDn);
        source.setPassword(password);
        source.setPooled(false);
        source.afterPropertiesSet();

        return source;
    }

    private boolean authenticate(String uid, String password) {
        return ldap.authenticate(
                query()
                        .base("ou=people")
                        .where("uid").is(uid),
                password
        );
    }

    @AfterEach
    void tearDown() {
        if (server != null) {
            server.shutDown(true);
        }
    }

    @Test
    void acceptsCorrectPasswordForExistingUser() {
        assertTrue(authenticate("an", AN_PASSWORD));
        assertTrue(authenticate("binh", BINH_PASSWORD));
    }

    @Test
    void rejectsWrongPassword() {
        assertFalse(authenticate("an", "incorrect-password"));
    }

    @Test
    void rejectsAnotherUsersPassword() {
        assertFalse(authenticate("an", BINH_PASSWORD));
    }

    @Test
    void rejectsUnknownUser() {
        assertFalse(authenticate("ghost", "any-test-password"));
    }

    @Test
    void escapesUserNameUsedInSearchFilter() {
        // Không cho ký tự filter biến input thành điều kiện khác.
        assertFalse(authenticate("an*)(uid=*", AN_PASSWORD));
        assertFalse(authenticate("*", AN_PASSWORD));
    }

    @Test
    void directBindAsUserSucceedsWithCorrectCredentials()
            throws Exception {

        LdapContextSource userSource =
                contextSource(AN_DN, AN_PASSWORD);

        DirContext context = userSource.getReadOnlyContext();
        try {
            Attributes attributes = context.getAttributes(
                    new LdapName("uid=an,ou=people")
            );

            assertEquals("An Nguyen",
                    attributes.get("cn").get());
        } finally {
            context.close();
        }
    }

    @Test
    void directBindRejectsIncorrectCredentials() {
        LdapContextSource userSource =
                contextSource(AN_DN, "incorrect-password");

        assertThrows(
                org.springframework.ldap.AuthenticationException.class,
                userSource::getReadOnlyContext
        );
    }
}
```

### Kiểm thử này chứng minh điều gì?

- `authenticate("an", AN_PASSWORD)`: Spring LDAP dùng query tìm DN của entry `an` và xác minh mật khẩu bằng thao tác LDAP authentication phù hợp. Khi credentials đúng, kết quả là `true`.
- Mật khẩu sai hoặc UID không tồn tại: luồng trả về `false` cho các ca thông thường, thay vì cho phép đăng nhập.
- `authenticate("an*)(uid=*", ...)`: truy vấn được tạo bởi `LdapQueryBuilder` coi input là **giá trị**, tránh chuyển nó thành cú pháp filter tìm nhiều người dùng.
- Direct bind: `LdapContextSource` được tạo bằng DN của An và mật khẩu đúng; `getReadOnlyContext()` phải kết nối và bind thành công trước khi đọc entry. Context được đóng trong `finally`.
- Direct bind sai password: server từ chối việc tạo context có danh tính đó và Spring LDAP báo `AuthenticationException`.

Mỗi test dùng một server mới; không có credential hoặc entry do test khác để lại. Các giá trị password nằm trong class test chỉ là dữ liệu giả. Khi dùng container hoặc server ngoài JVM, phải thay bằng secret test do môi trường cấp và bảo đảm không ghi password vào log.

**Giới hạn quan trọng:** sau khi direct bind thành công, việc đọc được `cn` trong ví dụ phản ánh quyền mặc định của **server UnboundID đang chạy**. Không được kết luận rằng một tài khoản thông thường trên LDAP sản xuất cũng sẽ đọc được mọi entry hay thuộc tính. Muốn kiểm tra quyền thực tế, phải dùng LDAP server với **ACL được cấu hình tương ứng**, như phần tiếp theo.

## 6. Thiết kế integration test cho quyền truy cập thực tế

Giả sử hệ thống cần chính sách:

- Tài khoản `reader` được phép tìm và đọc `uid`, `cn`, `mail` trong `ou=people`.
- Tài khoản `reader` không được sửa `mail`, xóa entry hoặc đổi DN.
- Tài khoản `editor` chỉ được sửa `mail` trong một nhánh được cấp quyền.
- Thuộc tính `userPassword` không được tiết lộ dưới dạng dữ liệu đọc cho `reader`.
- Tài khoản quản trị test dùng để seed fixture và kiểm tra trạng thái trước/sau thao tác; không dùng làm danh tính cho assertions về quyền của `reader`.

Để chứng minh các quy tắc này, cần dựng **OpenLDAP/LDAP server test có ACL đúng với chính sách trên**, hoặc test domain tương thích nếu production là Active Directory. Không thể chỉ thêm `groupOfNames` với `member` rồi suy ra server đã thực thi quyền truy cập.

### Ma trận quyền cần bao phủ

| Danh tính | Search dưới `ou=people` | Đọc `cn` | Đọc `userPassword` | Modify `mail` | Delete |
| --- | --- | --- | --- | --- | --- |
| `reader` | Cho phép | Cho phép | Không cho phép | Từ chối | Từ chối |
| `editor` | Theo ACL | Theo ACL | Không cho phép | Cho phép trong phạm vi được cấp | Từ chối |
| Admin test | Theo cấu hình quản trị test | Có | Theo chính sách server | Có | Có |

Ma trận là **hợp đồng mong muốn**, không phải mặc định của LDAP. Quyền cuối cùng do ACL/configuration của server quyết định. Để test có ý nghĩa, cần có fixture ACL mà người kiểm thử biết rõ và đã được áp dụng trước khi chạy assertions.

### Ví dụ test quyền ghi trên server có ACL

Ví dụ dưới đây minh họa **phần assertion** của một suite sử dụng hai `LdapTemplate` đã được cấu hình kết nối đến **LDAP test server có ACL**: `readerLdap` bind bằng account read-only, `adminLdap` bind bằng account test có quyền đọc dữ liệu gốc. Cần tạo fixture và ACL trước khi chạy; đây là đoạn chèn vào lớp test có cấu hình tương ứng, **không chạy với UnboundID mặc định ở phần 5**.

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import javax.naming.directory.BasicAttribute;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;
import javax.naming.ldap.LdapName;
import org.junit.jupiter.api.Test;
import org.springframework.ldap.NoPermissionException;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;

// readerLdap và adminLdap đã được tạo bằng hai ContextSource
// dùng credential khác nhau trên LDAP server có ACL test.
// Fixture có uid=an,ou=people,dc=example,dc=org
// với mail=an@example.org.

@Test
void readerCannotModifyMail() throws Exception {
    LdapName dn = new LdapName("uid=an,ou=people");

    assertThrows(NoPermissionException.class, () ->
            readerLdap.modifyAttributes(dn,
                    new ModificationItem[] {
                        new ModificationItem(
                                DirContext.REPLACE_ATTRIBUTE,
                                new BasicAttribute(
                                        "mail", "changed@example.org"))
                    })
    );

    // Đọc lại bằng account được phép: lỗi phải không làm đổi dữ liệu.
    String current = adminLdap.lookup(
            dn,
            (AttributesMapper<String>) attributes ->
                    (String) attributes.get("mail").get());

    assertEquals("an@example.org", current);
}
```

Ví dụ này giả định ACL trả lỗi LDAP `insufficientAccessRights` cho lệnh modify, được Spring LDAP dịch thành `NoPermissionException`. Một số chính sách **che giấu sự tồn tại** của entry/attribute đối với account không được đọc; trong tình huống đó search/lookup có thể trả rỗng hoặc báo lỗi khác. Test phải dùng **kỳ vọng theo chính sách và implementation đích**, không cố ép mọi lỗi quyền thành một exception duy nhất.

**Hai assertion là cần thiết:** xác nhận lệnh bị từ chối và xác nhận dữ liệu không bị sửa. Chỉ kiểm tra exception chưa chứng minh entry không thay đổi do thao tác trước đó hoặc một bước cleanup lỗi.

### Kiểm thử quyền đọc và thuộc tính ẩn

Đọc entry có ACL không nhất thiết ném exception:

- Server có thể trả **entry nhưng lọc bỏ** thuộc tính không được phép đọc.
- Server có thể **không trả entry** nếu account không được phép search.
- Server có thể từ chối thao tác bằng mã lỗi quyền.

Vì vậy, với chính sách `reader` được đọc `cn` nhưng không được đọc `userPassword`, nên viết hai phép kiểm tra riêng: đọc `cn` thành công và yêu cầu rõ danh sách thuộc tính cần đọc để xác minh `userPassword` không xuất hiện, hoặc server từ chối theo chính sách cụ thể. Không đưa giá trị mật khẩu nhận được vào test log, kể cả trong tình huống lỗi.

Đặc biệt, **khả năng đọc `userPassword` không phải điều kiện bắt buộc để xác thực bằng LDAP bind**: server có thể đối chiếu mật khẩu nội bộ trong khi không cho phép account dịch vụ đọc thuộc tính mật khẩu.

## 7. Tránh nhầm quyền của service account với quyền người dùng

Một lỗi thiết kế rất phổ biến:

```text
User A đăng nhập thành công
       │
       ▼
Ứng dụng lưu userId = A
       │
       ▼
LdapTemplate vẫn dùng ContextSource của admin
       │
       ▼
Modify entry trên LDAP
       │
       ▼
LDAP server kiểm tra quyền của ADMIN, không tự biết A
```

Đây không phải hành vi sai của LDAP; đó là **danh tính kết nối** mà ứng dụng đang dùng. Nếu nghiệp vụ yêu cầu User A chỉ sửa dữ liệu của chính mình, hệ thống phải kiểm tra quyền ở lớp nghiệp vụ trước khi dùng service account để ghi, hoặc tạo thao tác bằng context mang danh tính được giới hạn phù hợp. Phải có test riêng xác minh quy tắc này ở cấp service và/hoặc server.

Một chuỗi test hữu ích gồm:

1. **Authentication test:** mật khẩu của A đúng, của B sai khi dùng cho DN của A.
2. **Service authorization test:** dù đã xác thực A, service từ chối sửa entry của B.
3. **Server ACL test:** tài khoản read-only không thể modify/delete trên LDAP test server.
4. **Audit/exception test:** khi bị từ chối, ứng dụng trả lỗi nghiệp vụ phù hợp và không tiết lộ mật khẩu hoặc chi tiết nhạy cảm.

Không nên xem kết quả `ldapTemplate.authenticate(...) == true` là bằng chứng rằng người dùng đã được cấp toàn bộ quyền đọc/ghi.

## 8. Kiểm thử input và xử lý lỗi xác thực

### DN, filter và giới hạn vùng tìm kiếm

Nếu người dùng đăng nhập bằng `uid`, ứng dụng có thể tìm DN của người đó bằng filter. Hãy dùng `LdapQueryBuilder.where("uid").is(uid)` để escape ký tự đặc biệt. Ví dụ, UID `an*)(uid=*` phải là **một giá trị UID**, không phải cú pháp thêm điều kiện vào filter.

Cần giới hạn **base DN** của truy vấn về OU được phép, chẳng hạn `ou=people`; không tự nhận DN đầy đủ từ client rồi bind hoặc modify ở bất kỳ vùng nào. Nếu hệ thống phải chấp nhận DN từ ngoài, parse bằng `LdapName` và kiểm tra nó thuộc subtree được cho phép theo cấu trúc DN, không dùng `String.endsWith(...)` đơn thuần.

### Mật khẩu rỗng và anonymous/unauthenticated bind

Theo đặc tả LDAP, một simple bind với tên không rỗng nhưng mật khẩu rỗng có thể được diễn giải là **unauthenticated authentication** trên một số server. Vì vậy, khi người dùng đăng nhập, nên đặt điều kiện đầu vào rõ ràng:

```java
public boolean login(String uid, String password) {
    if (uid == null || uid.isBlank()
            || password == null || password.isEmpty()) {
        return false;
    }

    return ldapTemplate.authenticate(
            query()
                    .base("ou=people")
                    .where("uid").is(uid),
            password
    );
}
```

Không gọi một mật khẩu rỗng là hợp lệ chỉ vì kết nối LDAP có thể tạo được. Cũng cần quyết định chính sách đối với whitespace trong mật khẩu: không tùy tiện `trim()` vì khoảng trắng có thể là một phần của mật khẩu thực.

### Phân loại lỗi

| Tình huống | Hành vi test nên xác nhận | Lưu ý |
| --- | --- | --- |
| UID không có entry | Từ chối đăng nhập | Không tiết lộ thông tin tồn tại tài khoản qua thông báo công khai |
| Mật khẩu sai | Từ chối đăng nhập | Có thể áp dụng giới hạn tần suất tại ứng dụng/hạ tầng |
| Mật khẩu trống | Bị chặn trước khi bind | Tránh unauthenticated bind |
| Service account sai credential | Phát sinh lỗi cấu hình/vận hành | Không coi là user nhập sai password |
| LDAP server không kết nối được | Lỗi phụ thuộc dịch vụ | Không chuyển mọi lỗi thành “sai tài khoản” |
| Context đóng không đúng | Rò rỉ tài nguyên/kết nối | Đảm bảo đóng trong `finally` hoặc try-with-resources khi API hỗ trợ |
| User có password đúng nhưng bị khóa/expired | Kỳ vọng theo chính sách server | Cần LDAP server có cơ chế tương ứng |
| ACL từ chối thao tác | Exception/lỗi theo server và policy | Phải xác minh hậu điều kiện dữ liệu không đổi |

Phân biệt **authentication failure** (credentials không đúng) với **LDAP infrastructure failure** (server không sẵn sàng, certificate lỗi, DNS, timeout) giúp ứng dụng phản hồi an toàn và vận hành dễ chẩn đoán. Unit test service có thể mock lỗi mạng có kiểm soát; còn kết nối, TLS và pooling thực tế phải được xác minh trong integration environment.

## 9. TLS, pooling và thực hành bảo mật khi kiểm thử

Ví dụ xác thực ở phần 5 dùng `ldap://127.0.0.1` để tránh phụ thuộc hạ tầng ngoài. Nó **không chứng minh** rằng ứng dụng production bảo vệ mật khẩu trên đường truyền. LDAP simple bind qua kết nối không mã hóa có thể để lộ credentials nếu truyền trên mạng; cần dùng **LDAPS hoặc StartTLS** với xác minh certificate phù hợp khi triển khai.

Các yêu cầu nên có test tách biệt:

| Yêu cầu | Kiểm thử phù hợp |
| --- | --- |
| LDAPS/StartTLS | Kết nối đến server test hỗ trợ TLS, dùng truststore và certificate test |
| Certificate tin cậy | Xác thực kết nối thành công với chứng chỉ hợp lệ |
| Certificate sai hoặc hostname không khớp | Kết nối bị từ chối |
| Pooling/context reuse | Dùng cấu hình pool test, kiểm tra danh tính và ranh giới giao dịch |
| Credential isolation | Không để context đã bind bằng user A được dùng cho thao tác của B |
| Timeout/mất kết nối | Fault injection và xử lý exception; kiểm tra tài nguyên được đóng |
| Rate limiting/account lockout | Test tại tầng ứng dụng hoặc server hỗ trợ chính sách tương ứng |

Không tắt xác minh chứng chỉ bằng trust-all manager trong một test nhằm chứng minh TLS an toàn. Không dùng password, email hoặc DN thực tế từ production trong dữ liệu seed. Khi test trên server dùng chung, phải có **naming context riêng, tài khoản riêng và quyền hạn giới hạn** để tránh thay đổi dữ liệu ngoài phạm vi.

Đối với connection pooling, cần xác minh chính sách sử dụng kết nối theo danh tính: không giả định một pool phục vụ service account sẽ an toàn để tái sử dụng cho các thao tác dưới danh tính người dùng khác. Kiểm thử xác thực bằng `LdapTemplate.authenticate` có cơ chế tạo context phù hợp khác với việc tự giữ lâu một `DirContext` của user.

## 10. Lựa chọn lớp kiểm thử để không bỏ sót lỗi

| Mục tiêu | Unit test | UnboundID integration | LDAP server có ACL/TLS thực |
| --- | --- | --- | --- |
| Validate uid/password rỗng | Có | Có thể bổ sung | Không cần cho kiểm tra đơn giản |
| Tạo filter từ UID an toàn | Có thể bắt tham số | Có, bằng kết quả bind/search | Có khi schema riêng |
| Xác thực DN/password | Mock không chứng minh bind | Có | Có, cần nếu chính sách đặc thù |
| Phân quyền nghiệp vụ “A không sửa B” | Có, với mock repository | Có thể chạy flow thật | Có nếu quyền còn phụ thuộc ACL |
| Server ACL read/modify/delete | Không | Không mặc nhiên | **Bắt buộc** |
| Lockout, expiration, password policy | Không | Phụ thuộc khả năng server test | **Cần server tương ứng** |
| Kết nối LDAPS/StartTLS và pooling | Mock không đủ | Cấu hình bổ sung riêng | **Cần môi trường tương ứng** |
| ODM hoặc `LdapClient` với danh tính giới hạn | Test logic độc lập | Kiểm thử tích hợp API | Kiểm thử lại trên server đích |

Điểm quan trọng là mọi test phải nói rõ **danh tính bind**, **quyền mong đợi**, **server áp dụng chính sách nào**, và **hậu điều kiện**. “Đăng nhập được” hoặc “truy vấn có kết quả” là bằng chứng quá hẹp để kết luận phân quyền an toàn.

## 11. Bài tập thực hành

1. Thêm tài khoản `uid=lan` vào fixture UnboundID với mật khẩu giả riêng. Viết test xác nhận đúng mật khẩu thành công, sai mật khẩu và mật khẩu của user khác đều thất bại.
2. Tạo service method `login(uid, password)` từ ví dụ phần 8. Viết unit test đảm bảo `null`, chuỗi rỗng và UID toàn khoảng trắng bị từ chối trước khi gọi LDAP.
3. Bổ sung input UID có `*`, `(`, `)` và dấu gạch chéo ngược. Xác nhận `LdapQueryBuilder` giữ chúng trong vai trò giá trị của filter.
4. Tạo hai context: service account và user account. Đọc cùng một entry bằng cả hai, giải thích vì sao quyền thực tế phải được kiểm tra theo danh tính kết nối.
5. Cấu hình một LDAP test server có ACL `reader` chỉ đọc, không sửa. Dùng ví dụ phần 6 để kiểm tra server từ chối modify và giá trị `mail` được giữ nguyên.
6. Thêm test quyền đọc thuộc tính `cn` và kiểm chứng `userPassword` không được tiết lộ cho `reader` theo ACL cụ thể.
7. Lập kế hoạch test với TLS thật: chứng chỉ hợp lệ, chứng chỉ không tin cậy, hostname không khớp và kết nối mất giữa chừng.
8. Kiểm tra ứng dụng hiện tại có đang dùng service account để sửa entry sau khi xác thực user không. Nếu có, bổ sung bài test quy tắc phân quyền nghiệp vụ trước khi ghi.

**Tiêu chí hoàn thành:** người học phân biệt authentication với authorization; viết được JUnit 5 kiểm tra DN/password đúng và sai bằng Spring LDAP trên server UnboundID; nhận diện ranh giới giữa quyền của service account và quyền của user; thiết kế ma trận ACL, test quyền đọc/ghi và hậu điều kiện trên server phù hợp; xử lý an toàn filter, password rỗng, TLS, pooling và lỗi kết nối mà không suy diễn quá mức từ một phép bind thành công.

