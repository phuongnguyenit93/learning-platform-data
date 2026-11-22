# LDAP nhúng cho kiểm thử và giới hạn so với hệ thống thật

## 1. Vì sao cần LDAP nhúng trong kiểm thử Spring Boot?

Nhiều ứng dụng Spring Boot lấy thông tin người dùng, đơn vị tổ chức hoặc nhóm quyền từ **LDAP (Lightweight Directory Access Protocol)**. Một flow tích hợp có thể tìm tài khoản theo mã nhân viên, xác thực thông tin đăng nhập, đọc nhóm để quyết định quyền truy cập rồi đồng bộ dữ liệu về database hoặc cache. Trong môi trường thật, LDAP thường là máy chủ dùng chung, có chính sách truy cập, nhiều vùng dữ liệu, TLS, tài khoản dịch vụ và các quy tắc vận hành riêng.

Nếu tất cả bài kiểm thử đều kết nối trực tiếp thư mục doanh nghiệp, chúng dễ bị ảnh hưởng bởi mạng, dữ liệu thay đổi, quyền hạn, lịch bảo trì hoặc nguy cơ ghi nhầm dữ liệu thật. **LDAP nhúng (embedded LDAP)** cung cấp một máy chủ LDAP chạy cùng quá trình kiểm thử hoặc được khởi tạo cho test, nạp một tập dữ liệu **LDIF** có thể tái lập.

LDAP nhúng giúp kiểm tra những gì ứng dụng thực sự gửi lên giao thức LDAP: DN, search base, scope, filter, thuộc tính trả về, phép bind, ánh xạ kết quả và cách Spring xử lý lỗi. Nó có giá trị hơn việc mock toàn bộ **LdapTemplate** khi cần xác nhận truy vấn và cấu trúc dữ liệu.

Tuy nhiên, một bài test xanh với LDAP nhúng **không chứng minh** ứng dụng tương thích hoàn toàn với Microsoft Active Directory (AD), OpenLDAP hoặc dịch vụ thư mục được tổ chức vận hành. Các hệ thống này có thể khác về schema, quyền đọc, group membership, referral, TLS, pagination, password policy và hành vi khi nhiều node cùng phục vụ.

Trong module **SPRING_BOOT_INTEGRATION**, chủ đề này liên hệ trực tiếp với quản lý cấu hình tích hợp, hợp đồng dữ liệu, lỗi mạng/xác thực, cache, transaction, kiểm thử và quan sát các flow làm việc với hệ thống bên ngoài.

### Kết quả mong muốn sau bài học

1. Phân biệt **unit test**, **integration test với embedded LDAP**, **integration/contract test với server thực**.
2. Dựng dữ liệu LDIF nhỏ nhưng đại diện, chạy LDAP nhúng riêng cho kiểm thử Spring Boot.
3. Kiểm tra search, bind, mapping, group lookup và các tình huống lỗi cơ bản.
4. Nhận diện rõ phần nào embedded LDAP chưa mô phỏng được, từ đó thiết kế lớp kiểm thử bổ sung.
5. Tránh đưa cấu hình và dữ liệu đăng nhập của môi trường test vào production.

## 2. Những khái niệm LDAP cần hiểu trước khi tạo fixture

LDAP tổ chức thông tin thành các **entry**, mỗi entry có **Distinguished Name (DN)** duy nhất trong cây thư mục. Entry mang các thuộc tính và **objectClass** xác định cấu trúc hợp lệ theo schema.

Ví dụ:

~~~text
dc=example,dc=org
├── ou=people
│   ├── uid=alice
│   └── uid=bob
└── ou=groups
    └── cn=order-operators
~~~

DN đầy đủ của Alice:

~~~text
uid=alice,ou=people,dc=example,dc=org
~~~

| Thành phần | Vai trò | Lỗi thường thấy |
| --- | --- | --- |
| **Base DN** | Gốc tìm kiếm, ví dụ **dc=example,dc=org**. | Trỏ nhầm nhánh, tìm thấy 0 entry dù dữ liệu tồn tại. |
| **DN và RDN** | Định danh đường dẫn entry; RDN như **uid=alice**. | Ghép DN bằng chuỗi thiếu escaping hoặc giả định UID là DN. |
| **objectClass/schema** | Quy định thuộc tính được phép/bắt buộc. | Fixture quá dễ dãi, production từ chối add/modify. |
| **Bind** | Xác thực/thiết lập danh tính kết nối, thường bằng DN và mật khẩu trong simple bind. | Nhầm việc service account tìm thấy user với việc user đăng nhập thành công. |
| **Search filter** | Điều kiện như **(uid=alice)**. | Ghép input người dùng vào filter dẫn đến LDAP injection. |
| **Search scope** | **OBJECT**, **ONELEVEL**, **SUBTREE** tùy API. | Tìm thiếu entry nằm trong OU con hoặc tìm quá rộng. |
| **Attribute** | **cn**, **sn**, **mail**, **member**... | Giả định thuộc tính luôn tồn tại, chỉ có một giá trị hoặc ai cũng được đọc. |
| **Group membership** | Quan hệ qua **member**, **uniqueMember**, **memberUid** hay thuộc tính theo server. | Giả định mọi server đều có **memberOf** hoặc hỗ trợ nhóm lồng nhau giống nhau. |

**LDIF (LDAP Data Interchange Format)** là định dạng văn bản biểu diễn entry và thuộc tính. Một LDIF test tốt mô tả những entry và quan hệ mà code thật cần, không chỉ một tài khoản hoàn hảo không có trường hợp biên.

## 3. Phân biệt các cấp kiểm thử

| Cấp kiểm thử | Hạ tầng | Xác minh tốt nhất | Giới hạn |
| --- | --- | --- | --- |
| **Unit test** | Mock **LdapOperations**/**LdapTemplate**, fake directory gateway. | Logic mapping, nhánh lỗi, quy tắc quyền, cache, retry mà không cần LDAP server. | Không kiểm chứng cú pháp filter, DN, bind hay server behavior. |
| **Embedded LDAP integration test** | LDAP server nhúng, LDIF tĩnh, thường trong JVM/test context. | Spring wiring, search/bind thật, query builder, mapping, dữ liệu OU/group, lỗi LDAP phổ biến. | Không tái hiện đầy đủ schema/ACL/TLS/replication/AD-specific behavior. |
| **Server compatibility test** | OpenLDAP/389 DS/AD hoặc môi trường tương đương được quản lý; có thể dùng container khi phù hợp. | Schema, auth, TLS, access policy, indexing, paging, referrals và cách server mục tiêu xử lý truy vấn. | Cần chuẩn bị dữ liệu, quản lý version và cấu hình phức tạp hơn. |
| **Staging/sandbox end-to-end** | Gần production, tài khoản thử và các hệ thống tích hợp liên quan. | Flow xuyên HTTP/database/cache/broker/LDAP, quyền thực tế, timeout, failover, đồng bộ và quan sát. | Chậm, dễ phụ thuộc hạ tầng, không thích hợp thay thế mọi test nhanh. |

Các lớp kiểm thử bổ sung cho nhau. **Embedded LDAP phù hợp để bắt lỗi tích hợp LDAP thường ngày một cách nhanh và ổn định**. Hành vi đặc thù của server đích cần được kiểm chứng với hệ thống đó.

## 4. Dựng embedded LDAP cho Spring Boot test

Một cách phổ biến trong các phiên bản Spring Boot có hỗ trợ embedded LDAP là dùng **UnboundID LDAP SDK** và cấu hình **spring.ldap.embedded** trong profile kiểm thử. Cần kiểm tra starter và tên property theo **phiên bản Spring Boot thực tế** của dự án; ví dụ sau minh họa cấu hình điển hình, không phải cách mô phỏng đầy đủ production directory.

### 4.1. Phụ thuộc thư viện

Ví dụ với Maven, các dependency chính:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-ldap</artifactId>
    </dependency>

    <dependency>
        <groupId>com.unboundid</groupId>
        <artifactId>unboundid-ldapsdk</artifactId>
        <scope>test</scope>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Đoạn này giả định project đã dùng Spring Boot dependency management. **unboundid-ldapsdk** chỉ cần trong scope test nếu ứng dụng production kết nối server thư mục ngoài. Không thêm LDAP server nhúng vào artifact chạy production khi không có lý do riêng.

### 4.2. Tách cấu hình test khỏi production

Ví dụ **src/test/resources/application-test.yml**:

~~~yaml
spring:
  ldap:
    base: dc=example,dc=org
    embedded:
      base-dn: dc=example,dc=org
      ldif: classpath:ldap/test-directory.ldif
      port: 0
~~~

Trong cấu hình này, **port: 0** yêu cầu chọn cổng khả dụng khi cơ chế embedded của phiên bản đang dùng hỗ trợ; cách này giúp giảm xung đột khi chạy test song song. **spring.ldap.base** xác định search base của LDAP client, còn **embedded.base-dn** là naming context của server thử nghiệm. Hai giá trị được đặt nhất quán để truy vấn tương đối như **ou=people** hoạt động như mong đợi.

Chỉ kích hoạt profile **test** trong kiểm thử. Ở production, client phải dùng URL, cơ chế TLS, credentials, base DN và timeout do môi trường thật cấp. Nếu dự án cấu hình **LdapContextSource** thủ công hoặc có nhiều LDAP server, hãy xác minh auto-configuration không bị thay thế và test thực sự đang kết nối embedded server thay vì LDAP bên ngoài.

**Không dùng một cổng cố định** trừ khi có nhu cầu và đã kiểm soát chạy đồng thời. Nếu cần chạy LDAP test song song trong cùng JVM, còn phải kiểm tra cách Spring cache **ApplicationContext** và cách từng test chia sẻ/sửa dữ liệu.

### 4.3. Tạo tập dữ liệu LDIF có chủ đích

Ví dụ **src/test/resources/ldap/test-directory.ldif**:

~~~ldif
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

dn: uid=alice,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: alice
cn: Alice Example
sn: Example
givenName: Alice
mail: alice@example.org
userPassword: alice-test-secret

dn: uid=bob,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: bob
cn: Bob Example
sn: Example
givenName: Bob
userPassword: bob-test-secret

dn: cn=order-operators,ou=groups,dc=example,dc=org
objectClass: top
objectClass: groupOfNames
cn: order-operators
member: uid=alice,ou=people,dc=example,dc=org
~~~

Fixture có một tài khoản có email (**alice**), một tài khoản thiếu thuộc tính tùy chọn (**bob**), và một nhóm chứa Alice. Nó cho phép kiểm tra mapping trường thiếu, xác thực mật khẩu, tìm kiếm thành viên nhóm và việc một user không mặc nhiên thuộc nhóm.

**Mật khẩu LDIF chỉ là dữ liệu giả dùng riêng trong test.** Một server thật có thể lưu password theo hash, chính sách bảo mật hoặc thuộc tính đặc thù; việc đơn giản hóa này có chủ đích. Tuyệt đối không tái sử dụng mật khẩu, DN đặc quyền hoặc bản xuất dữ liệu người dùng thật.

LDIF cần tuân thủ encoding/line folding theo chuẩn khi chứa giá trị Unicode hoặc ký tự đặc biệt. Với entry thay đổi thực tế, nên dùng dữ liệu tối thiểu đã được tổng hợp hoặc tạo nhân tạo; không đưa dữ liệu cá nhân từ production vào test repository.

## 5. Viết integration test thực sự gọi LDAP

Ví dụ dùng Spring Boot test context, **LdapTemplate** và AssertJ. Cấu hình application-test.yml và fixture bên trên phải được nạp thành công.

~~~java
import java.util.List;
import javax.naming.directory.Attributes;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.test.context.ActiveProfiles;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.ldap.query.LdapQueryBuilder.query;

@SpringBootTest
@ActiveProfiles("test")
class DirectoryLdapIntegrationTest {

    @Autowired
    LdapTemplate ldapTemplate;

    @Test
    void findsUserByUidAndMapsCommonName() {
        List<String> names = ldapTemplate.search(
                query().base("ou=people").where("uid").is("alice"),
                (AttributesMapper<String>) attrs ->
                        (String) attrs.get("cn").get());

        assertThat(names).containsExactly("Alice Example");
    }

    @Test
    void authenticatesKnownUserAndRejectsWrongPassword() {
        var alice = query().base("ou=people")
                .where("uid").is("alice");

        assertThat(ldapTemplate.authenticate(
                alice, "alice-test-secret")).isTrue();
        assertThat(ldapTemplate.authenticate(
                alice, "wrong-password")).isFalse();
    }

    @Test
    void findsGroupByMemberDn() {
        String aliceDn =
                "uid=alice,ou=people,dc=example,dc=org";

        List<String> groups = ldapTemplate.search(
                query().base("ou=groups")
                        .where("member").is(aliceDn),
                (AttributesMapper<String>) attrs ->
                        (String) attrs.get("cn").get());

        assertThat(groups).containsExactly("order-operators");
    }

    @Test
    void unknownUserReturnsNoEntry() {
        List<String> names = ldapTemplate.search(
                query().base("ou=people").where("uid").is("nobody"),
                (AttributesMapper<String>) attrs ->
                        (String) attrs.get("cn").get());

        assertThat(names).isEmpty();
    }
}
~~~

Mục đích là xác minh **truy vấn được thực thi bởi LDAP server**, không chỉ kiểm tra hàm Java trả về đúng theo mock. Lưu ý:

- Đoạn search dùng **base tương đối** vì ứng dụng đã đặt **spring.ldap.base**. Nếu **ContextSource** không có base, phải dùng DN đầy đủ hoặc cấu hình base tương ứng.
- **AttributesMapper** nhận thuộc tính có thể vắng mặt; đoạn test chỉ đọc **cn** của các fixture có **cn**. Code production phải xử lý thuộc tính tùy chọn và đa giá trị.
- Ví dụ **authenticate** kiểm tra simple bind theo thiết lập thử nghiệm. Nó không thay thế kiểm thử đăng nhập production có TLS, tài khoản khóa, MFA, SASL/Kerberos hoặc chính sách mật khẩu.
- Không nên chạy trực tiếp các test cùng sửa hoặc xóa entry trên **cùng một instance embedded** mà không reset fixture; kết quả có thể phụ thuộc thứ tự chạy.

### Kiểm tra trường thiếu và giá trị đa trị

Với Bob không có **mail**, mapper cần biểu đạt trạng thái **không có giá trị** thay vì ném **NullPointerException**:

~~~java
List<String> mails = ldapTemplate.search(
        query().base("ou=people").where("uid").is("bob"),
        (AttributesMapper<String>) attrs -> {
            var mail = attrs.get("mail");
            return mail == null ? null : (String) mail.get();
        });
~~~

Đây chỉ là minh họa việc kiểm tra **null**; trong code nghiệp vụ nên dùng DTO/Optional hoặc một kiểu biểu diễn rõ ràng. Vì API mapping có thể trả về giá trị null, cách assert và xử lý collection nên được thiết kế minh bạch. Với thuộc tính đa trị như **member**, không chỉ gọi **get()** một lần rồi xem đó là toàn bộ danh sách; cần đọc tất cả giá trị thuộc tính.

## 6. Bảo vệ truy vấn LDAP trước dữ liệu đầu vào không đáng tin

Khi tích hợp HTTP API nhận tham số **uid**, việc nối chuỗi thủ công tạo nguy cơ **LDAP filter injection**:

~~~java
// Không dùng cách ghép filter bằng input bên ngoài:
String filter = "(uid=" + userInput + ")";
~~~

Các ký tự như **\***, **(**, **)**, dấu gạch chéo ngược và byte NUL có ý nghĩa đặc biệt trong cú pháp LDAP filter. Một input tùy ý có thể làm filter sai hoặc mở rộng tập kết quả. Nên dùng API xây dựng filter có xử lý escaping:

~~~java
var ldapQuery = query()
        .base("ou=people")
        .where("uid").is(userInput);

var users = ldapTemplate.search(
        ldapQuery,
        (AttributesMapper<String>) attrs ->
                (String) attrs.get("cn").get());
~~~

**Filter escaping** và **DN escaping** là hai việc khác nhau. Nếu phải tạo DN từ user input, dùng API dựng DN như **LdapNameBuilder**, không ghép **"uid=" + input + ",ou=people,..."**. Ngoài escaping, áp dụng validation theo hợp đồng dữ liệu: giới hạn độ dài UID, loại ký tự cho phép khi phù hợp, base/scope cố định và số lượng kết quả tối đa.

Test các chuỗi đặc biệt và input dài để chắc chắn truy vấn không trả thêm người dùng ngoài ý muốn. Embedded server giúp bắt lỗi filter ở mức LDAP protocol nhưng **không thay thế** việc kiểm tra schema và chính sách ACL của môi trường thật.

## 7. Giới hạn của embedded LDAP so với directory production

### 7.1. Schema và thuộc tính chuyên biệt

Trong fixture trên, **inetOrgPerson** và **groupOfNames** đủ cho bài toán cơ bản. Hệ thống thật có thể có objectClass tùy biến, attribute bắt buộc, matching rule riêng, DN syntax và cơ chế chuẩn hóa khác.

Đặc biệt, **Active Directory** có những thuộc tính và quy ước riêng như **sAMAccountName**, **userPrincipalName**, **objectGUID**, **userAccountControl** và cách biểu diễn nhóm, tài khoản bị khóa hoặc hết hạn. Những thuộc tính tính toán hoặc virtual như **memberOf** không mặc nhiên xuất hiện giống nhau trên embedded LDAP.

Một test xanh với **(uid=alice)** chỉ chứng minh fixture có uid; nó không chứng minh production cho phép tìm user theo UID hoặc mọi domain đều dùng cùng naming attribute. Mapping group/role cần được xây dựng theo schema và contract của server mục tiêu.

### 7.2. Authentication và password policy

Embedded LDAP có thể xác nhận bind hợp lệ/sai mật khẩu trong fixture. Nó thường không mô phỏng đầy đủ:

- Khóa tài khoản sau nhiều lần sai mật khẩu, password expired, account disabled.
- Quy tắc thay đổi mật khẩu, lịch sử mật khẩu, min length, complexity.
- Cơ chế AD/Kerberos/SASL, bind qua TLS hoặc chính sách chặn simple bind không mã hóa.
- Cơ chế đồng bộ domain, trạng thái replication và lỗi khi một domain controller không còn sẵn sàng.

**Không dùng mật khẩu rỗng để kiểm thử thành công xác thực**: tùy server và cơ chế bind, anonymous hoặc unauthenticated bind có semantics khác login người dùng. Dịch vụ phải kiểm tra username/password hợp lệ trước khi gọi LDAP và từ chối trường hợp null/rỗng.

### 7.3. Authorization, ACL và quyền dữ liệu

Một embedded LDAP thường chạy với cấu hình quyền đơn giản; nhiều thao tác có thể được phép mặc định trong bài test. Production thường tách service bind account, admin account, người dùng cuối và quyền đọc/ghi theo OU/attribute.

Một search trả về **mail** trong test không chứng minh tài khoản dịch vụ production được đọc thuộc tính này. Tương tự, một phép modify thành công trên embedded server không chứng minh service account có quyền ghi attribute hoặc di chuyển entry ở production.

Test với server tương đương thật cần dùng **least privilege account** và xác minh cả trường hợp **insufficientAccessRights**, không chạy mọi test với quyền quản trị khiến lỗi cấu hình bị che giấu.

### 7.4. TLS, certificate và cơ chế mạng

Embedded LDAP tại **localhost** có thể dùng kết nối không mã hóa để giúp test nhanh. Môi trường thật cần đánh giá **LDAPS/StartTLS**, certificate chain, hostname verification, truststore, protocol và thời gian timeout.

Các kiểm thử cần bổ sung gồm: chứng chỉ hết hạn, CA không tin cậy, tên máy không khớp, server không hỗ trợ cơ chế TLS đã chọn, kết nối bị đóng giữa search/bind và trường hợp chỉ một endpoint trong danh sách failover còn hoạt động.

Không tắt kiểm tra certificate hay dùng trust-all manager trong code production chỉ để giống test embedded. Kết nối test thành công qua **ldap://localhost** không nói gì về an toàn transport của môi trường thật.

### 7.5. Search behavior, paging và referral

Server production có thể giới hạn số entry trả về, thời gian tìm kiếm, loại filter, chỉ mục và tốc độ truy vấn. Thư mục lớn cần **paged results** hoặc phân trang theo khả năng server, và phải quản lý cookie/continuation một cách đúng đắn.

**Referral** có thể chuyển client sang naming context hoặc server khác. Embedded server một cây nhỏ thường không đại diện cho nhiều domain/forest, referral chain và các vấn đề xác thực qua server được giới thiệu.

Test với một vài người dùng không bộc lộ lỗi query không có index hoặc code giả định **search luôn trả hết kết quả trong một lần**. Cần kiểm thử volume, giới hạn search và truy vấn phân trang với server đích hoặc container tương tự production.

### 7.6. HA, replication, dữ liệu đồng bộ chậm

Production có thể gồm nhiều LDAP server/domain controller, dữ liệu được replication theo thời gian, DNS/load balancer và kết nối được pooling. Một lần ghi vào node A chưa chắc hiện ngay khi đọc node B.

Embedded LDAP một node không mô phỏng đầy đủ replication lag, split-brain, sự khác biệt read-after-write giữa node, connection failover hoặc hành vi khi hết connection pool. Thiết kế client cần timeout, retry có giới hạn và cách xác định **stale data** phù hợp với nghiệp vụ.

### Bảng so sánh tóm tắt

| Khả năng | Embedded LDAP | Server thật hoặc môi trường gần production |
| --- | --- | --- |
| Load LDIF, tìm DN/filter, bind cơ bản | Phù hợp để kiểm thử | Có, theo schema/quyền thực tế |
| Schema/attribute tùy biến | Có thể cấu hình một phần tùy implementation | Là nguồn sự thật của contract |
| ACL, service account, account lock | Thường bị đơn giản hóa | Cần kiểm tra trực tiếp |
| AD-specific attributes và nested group | Không giả định có đầy đủ | Phải thử trên AD khi ứng dụng phụ thuộc AD |
| TLS/certificate/StartTLS | Có thể thử một phần, không đủ đại diện | Cần kiểm tra toàn bộ đường kết nối |
| Paging, referral, size/time limit | Có thể thử cơ bản, khác production | Phải xác minh theo server mục tiêu |
| Hiệu năng, index, nhiều triệu entry | Fixture thường rất nhỏ | Cần load/performance test thực tế |
| Replication/failover/HA | Thường một instance | Phải thử vận hành có nhiều node |

## 8. Thiết kế fixture có giá trị: kiểm thử cả trường hợp lỗi

Chỉ một tài khoản **alice** với đủ thuộc tính tạo ra bài test dễ xanh nhưng ít phát hiện lỗi. Nên thiết kế dữ liệu đáp ứng những tình huống thật sự xuất hiện trong contract:

| Kịch bản fixture | Câu hỏi kiểm chứng |
| --- | --- |
| Người dùng hợp lệ, đúng OU | Search và mapping trả về duy nhất entry mong đợi? |
| Người dùng không tồn tại | Code biểu diễn “not found” rõ ràng, không nhầm với lỗi kết nối? |
| Mật khẩu sai, rỗng hoặc tài khoản không cho bind | Không xác thực thành công nhầm; không log password? |
| Thuộc tính tùy chọn bị thiếu | Mapper/DTO xử lý null và fallback đúng? |
| Thuộc tính đa trị hoặc nhóm có nhiều member | Có đọc đủ giá trị và kiểm tra quyền chính xác? |
| UID có ký tự đặc biệt, input dài | Filter/DN có escaping, validation và giới hạn phạm vi đúng? |
| Hai entry có cùng giá trị một thuộc tính không unique | Code xử lý trường hợp search trả nhiều kết quả mà không chọn nhầm ngẫu nhiên? |
| Người dùng nằm ở OU con | Scope SUBTREE và base DN đúng? |
| Nhóm lồng nhau hoặc nhiều loại group schema | Contract có thật sự hỗ trợ, hay chỉ đang giả định **memberOf**? |
| Search bị timeout hoặc LDAP unavailable | Service phân biệt retryable error với not found/invalid credentials? |

**Không cố ép embedded server giả lập lỗi mà nó không hỗ trợ trung thực.** Với network timeout, TLS, referral và AD lockout, hãy dùng fake có fault injection ở lớp phù hợp và bổ sung bài test trên server/container đại diện. Quan trọng là chỉ rõ giới hạn của từng bài kiểm thử.

### Tách dữ liệu và tránh test phụ thuộc nhau

- Ưu tiên **read-only tests** với fixture cố định. Nếu test add/modify/delete entry, phục hồi dữ liệu sau test hoặc dùng LDAP instance/context riêng.
- Dùng **port động** hoặc quản lý port độc quyền khi chạy CI song song.
- Không dùng dữ liệu người dùng thật hoặc thông tin đăng nhập thật. Test account/password là mẫu giả và chỉ xuất hiện trong test resources.
- Đảm bảo test đóng server/socket và Spring context phù hợp. Cẩn thận với state được cache trong context giữa hai test.
- Không kỳ vọng **@Transactional** của database test tự rollback thay đổi thực hiện trong LDAP. LDAP directory nằm ngoài transaction JDBC/JPA thông thường.

## 9. Tích hợp LDAP với database, cache, HTTP và luồng đồng bộ

Trong ứng dụng thực tế, LDAP thường chỉ là một nguồn của nhiều nguồn dữ liệu. Chẳng hạn, API HTTP nhận **employeeId**, truy vấn LDAP lấy tên/nhóm, cache kết quả để giảm tải và ghi bản snapshot vào database phục vụ tìm kiếm nhanh.

~~~mermaid
flowchart LR
    A[HTTP API / scheduled sync] --> B[Spring Boot service]
    B --> C{Cache còn hợp lệ?}
    C -->|Có| D[Trả dữ liệu đã lưu]
    C -->|Không| E[LDAP adapter]
    E --> F[(Directory server)]
    E --> G[(Cache / database snapshot)]
    G --> D
~~~

Các lỗi cần tính trước:

**LDAP unavailable:** Không trả **“user not found”** khi thực chất không liên lạc được directory. Phân biệt trạng thái “không có entry” với lỗi mạng, timeout, bind credentials sai và thiếu quyền đọc. Retry nên có timeout/backoff/jitter và giới hạn; không retry mù quáng lỗi xác thực hoặc dữ liệu sai.

**Cache stale:** Group membership hoặc tài khoản bị vô hiệu hóa có thể thay đổi sau khi cache được tạo. Thiết kế TTL/invalidation theo mức nhạy cảm; với quyết định phân quyền quan trọng, không dùng snapshot quá hạn như nguồn bảo đảm tuyệt đối.

**Directory/database không có transaction chung:** Nếu đã ghi snapshot vào database nhưng cập nhật LDAP thất bại hoặc ngược lại, **@Transactional** trên JPA/JDBC không rollback thao tác LDAP. Cần thứ tự thao tác rõ ràng, khả năng chạy lại an toàn và đối soát theo khóa nghiệp vụ. Nhiều hệ thống xem LDAP là nguồn đọc chỉ quyền, đồng bộ sang database theo cơ chế eventual consistency.

**Contract thay đổi:** Một attribute bị đổi tên, bị cắt quyền đọc hoặc chuyển sang multi-valued có thể khiến adapter sai mà embedded fixture vẫn xanh. Nên quản lý version của mapping/filter và kiểm tra contract với directory mục tiêu khi thay đổi tích hợp.

**Không đồng nhất identity key:** DN có thể đổi khi user được chuyển OU hoặc đổi tên RDN. Nếu dùng DN làm khóa bền vững trong database, việc di chuyển entry có thể tạo bản ghi trùng. Cần chọn khóa ổn định phù hợp hệ thống đích, ví dụ một immutable identifier do directory cấp, và kiểm tra hành vi rename/move.

## 10. Kiểm thử lỗi, quan sát và bảo vệ thông tin

### Phân loại lỗi trong adapter

| Nhóm lỗi | Ví dụ | Cách xử lý |
| --- | --- | --- |
| **Không tìm thấy entry** | Search hợp lệ trả 0 kết quả. | Trả trạng thái not-found theo contract; không tự retry liên tục. |
| **Invalid credentials** | Simple bind với mật khẩu sai. | Từ chối đăng nhập; tránh tiết lộ user tồn tại hay không; không retry cùng password vô hạn. |
| **Access denied** | Service account không đọc được attribute/OU. | Báo lỗi vận hành/quyền; không biến thành tập kết quả rỗng giả tạo. |
| **Server unavailable/timeout** | DNS, TLS, network, server bận. | Retry có giới hạn, circuit breaker nếu phù hợp, fallback đã được thiết kế. |
| **Invalid DN/filter/schema** | DN không hợp lệ, vi phạm objectClass. | Sửa mapping/config/input; retry thường không giúp. |
| **Too many results/partial results** | Size limit, time limit, referral hoặc paging chưa xử lý. | Phân trang và điều chỉnh search base/filter, không kết luận dữ liệu đã đầy đủ. |

Các LDAP result code thường gặp gồm **32 (noSuchObject)**, **49 (invalidCredentials)**, **50 (insufficientAccessRights)** và **52 (unavailable)**. Spring LDAP có thể ánh xạ chúng thành các exception chuyên biệt; test nên dựa trên hợp đồng lỗi của tầng adapter, không phụ thuộc toàn bộ business logic vào chuỗi thông báo của server.

### Điều nên quan sát

- **Thời gian search/bind**, tỷ lệ timeout, kết quả không tìm thấy và lỗi xác thực.
- **Search base/filter template** đã được redacted, số entry trả về, cảnh báo bị giới hạn kết quả.
- **Server endpoint** được chọn, số kết nối đang sử dụng, sự kiện failover và lỗi TLS.
- **Cache hit/miss**, tuổi dữ liệu cache, độ trễ đồng bộ LDAP → database.
- **Correlation ID/traceId**, operation name, lỗi retry và giới hạn tốc độ.

Không đưa **password, bind secret, access token** hay bản chụp toàn bộ attributes nhạy cảm vào log/trace. DN cũng có thể chứa thông tin cá nhân; khi log cần tuân thủ chính sách bảo vệ dữ liệu và giới hạn mức chi tiết.

## 11. Checklist quyết định nơi chạy từng bài kiểm thử

1. **Unit test:** kiểm tra logic mapping, fallback và retry; dùng mock/fake để điều khiển lỗi.
2. **Embedded LDAP:** kiểm tra khởi tạo Spring LDAP, LDIF, search/filter, DN, bind, group cơ bản và mapping trường thiếu/đa trị.
3. **Container hoặc LDAP server tương đương:** kiểm tra schema/ACL thực tế, TLS, search limits, paging, referral và dữ liệu lớn.
4. **AD/staging sandbox (nếu dùng AD):** kiểm tra userPrincipalName/sAMAccountName, nested group, trạng thái tài khoản, password policy và quyền service account.
5. **End-to-end:** kiểm tra LDAP kết hợp HTTP/database/cache/broker, retry, dữ liệu đồng bộ chậm và kết quả nghiệp vụ.
6. **CI:** chạy embedded tests thường xuyên; chạy contract/staging tests theo lịch hoặc tại thay đổi liên quan schema/config; cô lập dữ liệu và tài khoản test.

Một kiểm tra quan trọng khi chạy CI là xác minh **test thật sự dùng embedded endpoint** và không lặng lẽ kết nối LDAP ngoài do biến môi trường hoặc profile khác ghi đè. Đừng để kết quả test phụ thuộc một directory production mà người chạy không biết.

## 12. Các ngộ nhận thường gặp

**“LDAP nhúng chạy xanh tức là sẽ kết nối AD thành công.”** Không. LDAP protocol là phần chung, còn AD có schema, auth, group và policy khác.

**“Bind thành công với tài khoản service chứng minh mật khẩu user đúng.”** Không. Bind với service account chỉ xác thực service account; xác thực người dùng cần thao tác và chiến lược xác minh riêng.

**“Có memberOf trong fixture nghĩa là mọi thư mục hỗ trợ giống nhau.”** Không. Thuộc tính tính toán hoặc plugin server có thể có semantics khác; có hệ thống chỉ lưu **member** ở group.

**“@Transactional sẽ hủy thay đổi LDAP nếu database rollback.”** Không. Giao dịch database thường không bao gồm thao tác LDAP.

**“Có cache LDAP thì quyền người dùng luôn đúng.”** Không. Cache có TTL và có thể giữ quyền cũ sau khi group membership thay đổi.

**“Test localhost không cần quan tâm security.”** Trong test cô lập có thể dùng đơn giản hóa, nhưng code production vẫn phải validate/escape input, dùng quyền tối thiểu, bảo vệ secret và xác thực certificate.

**“Chỉ cần một test tìm thấy Alice.”** Test đó chưa kiểm tra dữ liệu thiếu, truy vấn trả nhiều kết quả, nhóm phức tạp, không có quyền hoặc server unavailable.

## 13. Ghi nhớ

**Embedded LDAP là công cụ kiểm thử tích hợp LDAP nhanh, kiểm soát được dữ liệu và có thể tái lập**, thích hợp để xác minh Spring wiring, search filter, DN, bind và mapping. Chất lượng kiểm thử phụ thuộc vào fixture LDIF có đại diện cho hợp đồng dữ liệu hay không, cách cô lập trạng thái và các negative test được thiết kế ra sao.

Khi chuyển sang thư mục doanh nghiệp thật, phải kiểm chứng thêm **schema, ACL, kiểu xác thực, TLS, paging, referral, hiệu năng, replication và failover**. Với các flow Spring Boot còn liên quan HTTP, database, cache và broker, cũng phải kiểm tra transaction boundary, lỗi hệ thống ngoài và độ mới của dữ liệu. Một bộ kiểm thử đáng tin cậy kết hợp **unit test + embedded LDAP + kiểm thử server đích**, đồng thời ghi rõ giới hạn của từng lớp.
