# Kiểm thử TLS, timeout, referral và lỗi mạng

Một ứng dụng **SPRING_LDAP** có thể truy vấn DN, schema và filter chính xác nhưng vẫn gặp lỗi khi kết nối **LDAPS/StartTLS**, chờ phản hồi quá lâu, nhận referral đến thư mục khác hoặc mất mạng giữa thao tác ghi. Các lỗi này không chỉ ảnh hưởng độ sẵn sàng: nếu ứng dụng coi “không thể đọc LDAP” như “không có người dùng” hoặc mặc định kết quả tìm kiếm chưa đầy đủ là đầy đủ, hệ thống có thể đưa ra quyết định đồng bộ và phân quyền sai.

Bài thuộc chương **Testing** của module Spring LDAP, tập trung vào **thiết kế kiểm thử thực tế** cho `ContextSource`, `LdapTemplate`, `LdapClient` và tầng ODM/repository. Mục tiêu không chỉ là làm cho code chạy qua các nhánh `catch`, mà còn xác minh các bảo đảm quan trọng: **credential được bảo vệ, timeout có giới hạn, referral không lộ dữ liệu, lỗi mạng không bị ngụy trang thành kết quả rỗng, và thao tác ghi không bị lặp không kiểm soát**.

Các ví dụ sử dụng Java và JUnit 5. Một số thử nghiệm cần LDAP server, chứng chỉ và proxy kiểm thử có khả năng tạo sự cố. **Không chạy fault injection lên LDAP production**, không dùng tài khoản thật và không ghi password vào mã nguồn, log hoặc báo cáo test.

## 1. Chuẩn đầu ra của bài kiểm thử

Sau bài học, người học có thể:

1. Thiết kế **test matrix** bao phủ kết nối thành công và thất bại tại từng lớp DNS → TCP → TLS → LDAP bind → Search/Modify → response.
2. Viết unit test phân biệt `CommunicationException`, `PartialResultException`, `TimeLimitExceededException`, `NameNotFoundException` và kết quả tìm kiếm hợp lệ nhưng rỗng.
3. Kiểm thử TLS với CA tin cậy, CA không tin cậy, hostname mismatch, certificate hết hạn và yêu cầu StartTLS, **không dùng trust-all**.
4. Kiểm thử riêng **connect timeout**, **read timeout**, **search time limit** và **deadline tổng**; tránh test phụ thuộc thời gian tuyệt đối không ổn định.
5. Kiểm thử referral ở các chế độ `ignore`, `follow`, `throw`; đánh giá tính đầy đủ kết quả và an toàn của referral target.
6. Mô phỏng mất kết nối trước/sau khi gửi Add/Modify/Delete, bảo đảm không retry thao tác ghi khi trạng thái chưa rõ.
7. Tổ chức môi trường tích hợp/CI lặp lại được, tách bí mật, thu thập chứng cứ chẩn đoán và xác định tiêu chí PASS/FAIL.

## 2. Phân lớp kiểm thử: test nào chứng minh điều gì?

Không có một loại test đơn lẻ đủ để kiểm chứng toàn bộ chuỗi LDAP.

| Mức kiểm thử | Thành phần thực | Có thể chứng minh | Không nên khẳng định |
| --- | --- | --- | --- |
| **Unit test** | Service/repository + mock `LdapTemplate` | Logic phân loại exception, mapping lỗi, retry policy, xử lý dữ liệu rỗng | TLS handshake, mã LDAP thật, độ trễ socket, schema và ACL thật |
| **Integration test với LDAP nhúng** | `LdapTemplate` + `ContextSource` + LDAP test server | DN, filter, search, CRUD, schema và một số lỗi LDAP theo khả năng server | Mọi hành vi Active Directory, referral xuyên domain, sự cố proxy/TLS production |
| **Integration test TLS** | LDAP server có certificate kiểm soát được + JSSE truststore | Trust chain, hostname verification, yêu cầu mã hóa và lỗi handshake | Tự động chứng minh an toàn cho mọi server ngoài môi trường test |
| **Integration test referral** | Hai naming context/server test + cấu hình referral | `ignore`/`follow`/`throw`, coverage của nhiều nguồn, failure giữa chừng | Mọi chi tiết referral của các directory vendor |
| **Network fault-injection test** | Ứng dụng + proxy có thể chặn/trễ/reset TCP | Connect/read timeout, stale connection, failover, retry storm, write outcome unknown | Độ trễ chính xác đến từng mili giây trên mọi CI runner |
| **Acceptance/contract test** | Service/HTTP + phụ thuộc thử nghiệm | Không trả `404`/`[]` cho outage, không cấp quyền từ dữ liệu partial, API có correlation ID | Tính đầy đủ toàn forest nếu mới kiểm thử một domain |

Spring LDAP có thư viện `spring-ldap-test` hỗ trợ LDAP nhúng dựa trên **UnboundID** hoặc ApacheDS. Tài liệu phiên bản hiện hành nêu hạn chế tương thích đối với ApacheDS nhúng; dự án nên chọn bản tương thích với Spring LDAP đang dùng. **LDAP nhúng phù hợp cho CRUD/query, nhưng muốn kiểm thử TLS, referral hoặc fault injection phải kiểm tra server test có hỗ trợ đúng tính năng cần đo.**

### 2.1. Phân chia test suite

```text
                 JUnit 5 / build pipeline
                           │
             ┌─────────────┼─────────────┐
             ▼             ▼             ▼
          Unit          LDAP IT       Fault / TLS IT
         (mock)        (embedded)      (server + proxy)
             │             │             │
       milliseconds     real LDAP      slower, isolated
             └─────────────┼─────────────┘
                           ▼
              Báo cáo: correctness + safety
```

Đánh dấu integration/fault tests bằng tag hoặc nhóm build riêng, vì chúng phụ thuộc socket, certificate, proxy và môi trường. Tuy nhiên, chúng vẫn cần chạy thường xuyên trong pipeline dành cho thay đổi liên quan cấu hình LDAP/network; không chỉ chạy thủ công trước ngày phát hành.

## 3. Xây “hợp đồng đúng” trước khi viết test

Trước tiên phải biết cách một hệ thống **nên** ứng xử khi LDAP lỗi.

| Tình huống | Hành vi đúng nên được test |
| --- | --- |
| `lookup` DN không tồn tại | Có thể trả `Optional.empty()` nếu hợp đồng của API cho phép |
| `search` base hợp lệ, filter không khớp | Có thể trả `List.of()`; không xem là lỗi mạng |
| DNS/TCP/TLS không kết nối được | Báo lỗi hạ tầng; **không** trả “người dùng không tồn tại” |
| Bind bằng tài khoản dịch vụ thất bại | Báo sự cố cấu hình/credential nội bộ; không quy cho người dùng cuối sai mật khẩu |
| Bind kiểm tra mật khẩu người dùng thất bại | Kết quả xác thực bị từ chối, thông điệp bên ngoài trung tính |
| LDAP search vượt time/size limit | Thể hiện lỗi hoặc kết quả có giới hạn theo hợp đồng; không khẳng định đầy đủ |
| `PartialResultException` do referral chưa xử lý | Không coi tập kết quả đã nhận là toàn bộ phạm vi |
| Referral trỏ tới đích không được tin cậy | Không tự truyền credential hoặc truy vấn nhạy cảm tới đích đó |
| Mất phản hồi sau Add/Modify/Delete | Không gửi lại thao tác ghi vô điều kiện; kiểm tra outcome/idempotency |
| Nhiều request gặp outage cùng lúc | Retry có hạn mức; không tạo bão retry lên LDAP |

Phân biệt **tính đúng đắn** và **khả năng sử dụng**: một dashboard chỉ hiển thị dữ liệu cục bộ có thể chấp nhận kết quả partial kèm cảnh báo; một tiến trình xóa tài khoản dựa trên “entry không xuất hiện trong search” thường không được chấp nhận dữ liệu thiếu.

## 4. Môi trường kiểm thử cô lập và dữ liệu mẫu

Một topology tối thiểu hữu ích:

```text
Test application ──── network proxy ──── LDAP-A (dc=example,dc=test)
       │                    │                 │
       │                    ├─ latency/reset  └─ ou=people, ou=groups
       │                    └─ packet drop
       │
       └──────── referral test ───────── LDAP-B (dc=branch,dc=test)

LDAP-A/B: chỉ dữ liệu giả, tài khoản quyền tối thiểu
TLS test: CA + server certificates riêng cho môi trường test
```

**Nguyên tắc chuẩn bị:**

- Dùng namespace test như `dc=example,dc=test`, entry giả và tài khoản bind có quyền tối thiểu.
- Khởi tạo LDIF/schema bằng fixture kiểm soát được; mỗi test được reset hoặc dùng container/server riêng để tránh phụ thuộc thứ tự chạy.
- Cổng server/proxy nên được cấp động hoặc khóa độc quyền; tránh cố định cổng dễ va chạm khi CI chạy song song.
- Tách **tài khoản service** (dùng search/modify) khỏi **người dùng** (dùng thử xác thực), không dùng bind admin cho mọi kịch bản.
- CA, certificate, truststore và credential trong test phải được tạo riêng; password từ secret CI hoặc fixture test không nhạy cảm, không đưa vào log.
- Chạy TLS truststore khác nhau ở **JVM/process riêng** nếu cấu hình bằng system properties `javax.net.ssl.*`; thay đổi global properties giữa các test song song có thể gây nhiễu và kết quả giả.
- Với referral, chỉ dùng host nằm trong mạng test được cho phép; không để server test trỏ tùy ý ra Internet hoặc LDAP nội bộ thật.

### 4.1. Phụ thuộc kiểm thử

Ví dụ Gradle Kotlin DSL (version do BOM/dependency management của dự án quyết định):

```kotlin
dependencies {
    testImplementation("org.junit.jupiter:junit-jupiter")
    testImplementation("org.mockito:mockito-junit-jupiter")
    testImplementation("org.springframework.ldap:spring-ldap-test")
    // Chọn runtime LDAP nhúng (ví dụ UnboundID) phù hợp với
    // phiên bản spring-ldap-test đang sử dụng.
}

tasks.test {
    useJUnitPlatform()
}
```

Đây là minh họa, không phải yêu cầu thêm mọi dependency cho một test unit. Xem tài liệu Spring LDAP Testing để lựa chọn `EmbeddedLdapServer` hoặc `TestContextSourceFactoryBean` và dependency cần thiết ở **đúng phiên bản**. Test mTLS, AD referral, reset TCP và DNS nên dùng server/proxy test chuyên biệt; **không tự giả định LDAP nhúng hỗ trợ hết**.

### 4.2. Dữ liệu cố định để đối chiếu

Ví dụ LDIF cho test search:

```ldif
dn: dc=example,dc=test
objectClass: top
objectClass: domain
dc: example

dn: ou=people,dc=example,dc=test
objectClass: top
objectClass: organizationalUnit
ou: people

dn: uid=an,ou=people,dc=example,dc=test
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: an
cn: An Test
sn: Test
```

Đối với test “không có kết quả”, search `(uid=absent)` dưới `ou=people` đã tồn tại. Đối với test “search base không tồn tại”, search dưới `ou=missing`. Hai trường hợp có ý nghĩa khác nhau và phải được viết thành hai assertion riêng.

## 5. Cấu hình `ContextSource` cho môi trường kiểm thử

Ví dụ dùng `LdapContextSource` với cấu hình từ test environment. `ldapUrl` có thể là `ldaps://ldap.test.internal:1636` hoặc endpoint LDAP được bật StartTLS theo harness tương ứng.

```java
import java.util.HashMap;
import java.util.Map;

import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.core.support.LdapContextSource;

public final class TestDirectoryClients {
    private TestDirectoryClients() {}

    public static LdapTemplate strictTemplate(
            String ldapUrl,
            String baseDn,
            String serviceDn,
            String servicePassword) throws Exception {

        LdapContextSource source = new LdapContextSource();
        source.setUrl(ldapUrl);
        source.setBase(baseDn);
        source.setUserDn(serviceDn);
        source.setPassword(servicePassword);
        source.setReferral("ignore");

        Map<String, Object> environment = new HashMap<>();
        // Dành cho JNDI LDAP provider của Oracle/OpenJDK:
        environment.put("com.sun.jndi.ldap.connect.timeout", "800");
        environment.put("com.sun.jndi.ldap.read.timeout", "1200");
        source.setBaseEnvironmentProperties(environment);

        // Khi tự tạo thay vì để Spring IoC quản lý:
        source.afterPropertiesSet();

        LdapTemplate template = new LdapTemplate(source);
        template.setIgnorePartialResultException(false);
        template.setIgnoreNameNotFoundException(false);
        template.setIgnoreSizeLimitExceededException(false);
        return template;
    }
}
```

Lưu ý:

1. `com.sun.jndi.ldap.connect.timeout` và `com.sun.jndi.ldap.read.timeout` là **các property đặc thù của JNDI LDAP provider**, đơn vị mili giây; không phải timeout chung của toàn bộ HTTP request.
2. Nếu ứng dụng sử dụng provider khác, custom socket factory, StartTLS hoặc cơ chế pooling riêng, cần xác minh cách áp dụng property thực tế.
3. `setIgnorePartialResultException(false)` là mặc định hiện hành của `LdapTemplate`, giúp exception khi tìm kiếm được báo thay vì bỏ qua.
4. `setIgnoreSizeLimitExceededException(false)` là thay đổi có chủ đích: mặc định Spring LDAP cho phép **bỏ qua** `SizeLimitExceededException`. Test cần phát hiện sự khác nhau giữa lấy một danh sách giới hạn có chủ đích và yêu cầu phải lấy đủ.
5. Dùng cấu hình này cho **test client**, không sao chép nguyên timeout ngắn vào production; giá trị cần dựa trên SLA, vị trí mạng và đặc tính server thật.
6. Với base `dc=example,dc=test`, các DN truyền cho `LdapTemplate` thường tương đối với base, ví dụ `uid=an,ou=people`.

## 6. Kiểm thử TLS/LDAPS và StartTLS

Một bộ TLS test tối thiểu phải có cả **positive test** và **negative test**. Chỉ thấy cổng `636` mở hoặc LDAP bind thành công **không tự chứng minh** hostname và chứng chỉ được kiểm tra đúng.

### 6.1. Ma trận chứng chỉ và kết nối

| Test | Cấu hình | Kết quả mong đợi |
| --- | --- | --- |
| TLS-01 | Server dùng certificate hợp lệ do CA test mà client tin cậy cấp; hostname đúng SAN | TLS handshake và LDAP bind thành công |
| TLS-02 | Cùng server, client không tin CA đó | Handshake thất bại; **không** tự bypass truststore |
| TLS-03 | CA được tin nhưng client dùng hostname **không trùng SAN** | Không được coi là kết nối hợp lệ nếu hostname verification bật đúng |
| TLS-04 | Certificate hết hạn hoặc chưa có hiệu lực | Kết nối bị từ chối theo chính sách validation |
| TLS-05 | Thiếu intermediate certificate trong chain (khi client không dựng được chain) | TLS validation thất bại |
| TLS-06 | Server chỉ cho phép TLS/cipher mà client đã cấm | Handshake thất bại; báo lỗi cấu hình/chính sách |
| TLS-07 | Tài khoản bind sai nhưng TLS hợp lệ | **Authentication failure**, không nhầm với handshake failure |
| TLS-08 | Mở LDAP thường khi chính sách bắt buộc TLS trước bind | Không gửi credential bằng simple bind qua kênh chưa được bảo vệ |
| TLS-09 | StartTLS upgrade thất bại | Không tiếp tục simple bind bằng credential trên kênh chưa mã hóa |
| TLS-10 | LDAP proxy/server đóng socket giữa handshake | Báo lỗi kết nối/TLS, không trả “entry không tồn tại” |

**Hostname verification** có thể phụ thuộc JDK/provider và cách thiết lập StartTLS; test phải xác minh trên client/configuration **thực sự dùng trong ứng dụng**, thay vì giả định một API gọi `ldaps://` là đã an toàn. Không dùng `TrustManager` chấp nhận mọi certificate, tắt endpoint identification hoặc đặt cờ tương đương để làm test pass.

### 6.2. Kiểm thử bằng hai truststore tách biệt

Test harness cần tạo:

```text
test-ca.pem
server-valid.crt + server-valid.key
server-wrong-host.crt + server-wrong-host.key
client-trust-valid.p12   (chứa CA test)
client-trust-empty.p12   (không tin CA test)
```

**Các tệp trên là mô tả fixture**, không phải tệp đã được tạo trong project. Đừng commit private key thật hoặc gửi truststore chứa bí mật qua log/artifact công khai. Khi test bằng `javax.net.ssl.trustStore`, truyền cấu hình khi khởi động JVM test hoặc qua cấu hình SSL context chuyên dụng được provider hỗ trợ; không thay đổi global JSSE properties giữa các test chạy song song.

Ví dụ thiết lập test JVM riêng:

```text
-Djavax.net.ssl.trustStore=/path/to/client-trust-valid.p12
-Djavax.net.ssl.trustStoreType=PKCS12
-Djavax.net.ssl.trustStorePassword=<test-secret-from-CI>
```

Đây là **ví dụ cấu hình**, không nên ghi password trong lệnh shell được CI log lại. Có thể chuyển bí mật qua cơ chế bảo mật của runner, keystore credential provider hoặc một tiến trình test chuyên biệt.

Các assertion cần kiểm tra: **với truststore hợp lệ**, một LDAP read nhỏ thành công; **với truststore không tin cậy hoặc hostname sai**, thao tác không thành công và exception giữ được nguyên nhân TLS/SSL để chẩn đoán. Không phụ thuộc vào chính xác chuỗi thông báo Java `SSLHandshakeException` vì khác JDK/provider/ngôn ngữ runtime.

### 6.3. Test riêng StartTLS

StartTLS **bắt đầu qua kết nối LDAP thường rồi nâng cấp lên TLS trước khi truyền credential nhạy cảm**. Test phải kiểm chứng đúng thứ tự:

```text
Open TCP/LDAP connection
    │
    ▼
StartTLS extended operation
    │
    ├── Upgrade thành công → xác thực, search, modify
    └── Upgrade thất bại    → dừng / đóng connection, không simple bind
```

Đừng dùng test LDAPS làm bằng chứng đã kiểm thử StartTLS: chúng có vòng đời và cơ chế cấu hình khác nhau. Nếu production không dùng StartTLS, có thể bỏ nhóm test này; nếu dùng, cần bao phủ handshake fail, close/reopen, reuse context và chính sách pooling tương ứng.

## 7. Phân biệt bốn loại timeout bằng test

### 7.1. Bốn loại giới hạn

| Giới hạn | Cấu hình/nguồn | Mô phỏng | Điều phải chứng minh |
| --- | --- | --- | --- |
| **Connect timeout** | `com.sun.jndi.ldap.connect.timeout` | Chặn hoàn toàn kết nối tới IP/port test theo cách khiến connect không hoàn tất | Client ngừng chờ trong ngân sách hợp lý và không coi là sai mật khẩu |
| **Read timeout** | `com.sun.jndi.ldap.read.timeout` | Cho thiết lập TCP, nhận request nhưng trì hoãn/không gửi LDAP response | Client báo lỗi chờ phản hồi, phân biệt với connect failure |
| **Search time limit** | `SearchControls.setTimeLimit` hoặc `LdapTemplate.setDefaultTimeLimit`; server limit | Chạy một query bị giới hạn thời gian | Có thể nhận `TimeLimitExceededException`/LDAP `3`; không nhầm với socket timeout |
| **Deadline tổng** | Service/gateway/test harness | Nhiều bước kết nối/search/retry cùng kéo dài | Toàn bộ request dừng đúng ngân sách, không chỉ mỗi socket operation |

Các thuộc tính JNDI là đặc thù provider. **Connect timeout không tương đương TLS handshake timeout** và **read timeout không thay thế deadline tổng**. Đối với môi trường có nhiều URL/failover, thời gian chờ có thể cộng dồn qua các endpoint.

### 7.2. Thiết kế test connect timeout

Để kiểm tra đúng **timeout** (thay vì “connection refused” tức thì), proxy test cần nhận route nhưng **không hoàn tất connect** ở tầng thích hợp, hoặc môi trường được cấu hình làm TCP handshake không có phản hồi. Nếu proxy chỉ trả RST, client thường nhận `ConnectException` rất nhanh; test đó kiểm tra lỗi kết nối, **không chứng minh connect timeout**.

Ví dụ test:

```text
Given: connect timeout của JNDI provider = 800 ms
And:   đích được mô phỏng không hoàn tất TCP connect
When:  tạo LDAP context / thực hiện một lookup
Then:  nhận lỗi kết nối trong ngân sách test hợp lý
And:   không tiếp tục xác thực hay search
And:   không biến exception thành Optional.empty()/false
```

Trong CI, dùng khoảng chấp nhận rộng hợp lý (ví dụ “không treo quá deadline được test harness áp đặt”), **không viết assertion chính xác 800 ms ±1 ms**. Scheduling, DNS, khởi tạo JVM, TLS và việc chọn endpoint có thể tạo biến thiên.

### 7.3. Thiết kế test read timeout

Một proxy hoặc server giả cần **chấp nhận TCP connection** nhưng trì hoãn phản hồi LDAP vượt read timeout:

```text
Given: LDAP TCP connection established
And:   provider read timeout = 1200 ms
And:   backend giữ request không phản hồi trong hơn 1200 ms
When:  client thực hiện LDAP operation
Then:  operation thất bại có giới hạn thời gian
And:   lỗi được báo ở nhóm communication/timeout phù hợp
And:   service KHÔNG trả danh sách rỗng như một search thành công
```

Khối `assert` nên kiểm tra **hành vi quan sát được** và loại/nhóm lỗi; `SocketTimeoutException` có thể nằm sâu trong chuỗi `cause` hoặc provider có thể dùng wrapper khác. Không phụ thuộc vào một stack trace cố định cho mọi JDK.

### 7.4. Search time limit không phải read timeout

`LdapTemplate.setDefaultTimeLimit(int)` cấu hình giới hạn tìm kiếm mặc định, đơn vị **mili giây**, cho những search không chỉ định giới hạn riêng. Với API JNDI, `SearchControls.setTimeLimit(int)` cũng nhận mili giây:

```java
import javax.naming.directory.SearchControls;

SearchControls controls = new SearchControls();
controls.setSearchScope(SearchControls.SUBTREE_SCOPE);
controls.setTimeLimit(1500); // search time limit, ms
controls.setCountLimit(100);
```

Test phải ghi rõ có **server trả `timeLimitExceeded (3)`**, hay socket chờ quá lâu và **client nhận read timeout**. Nếu server trả giới hạn ngay trước lúc socket timeout thì test có thể ném một loại khác so với khi server bị treo; không thể dùng cùng assertion để kết luận cả hai cơ chế hoạt động.

Một query nhỏ trên LDAP nhúng có thể chạy quá nhanh để tạo `timeLimitExceeded`. Khi cần kiểm thử đường xử lý exception, unit test có thể **mô phỏng `TimeLimitExceededException`**, còn integration test nên dùng server/fault harness có thể điều khiển giới hạn trả về. Không tạo dữ liệu khổng lồ hoặc query quá nặng trên LDAP production chỉ để ép timeout.

## 8. Unit test: service phải phân loại lỗi rõ ràng

Giả sử ứng dụng có một service tra cứu entry theo DN. Ta định nghĩa hợp đồng:

- DN không tồn tại → `Optional.empty()`.
- Lỗi mạng/LDAP unavailable → exception miền `DirectoryUnavailableException`.
- Referral chưa xử lý hết → exception miền `IncompleteDirectoryResultException`.
- Hết search time limit → exception miền `DirectoryTimeoutException`.

Ví dụ:

```java
import java.util.Optional;
import javax.naming.Name;
import javax.naming.directory.Attribute;

import org.springframework.ldap.CommunicationException;
import org.springframework.ldap.NameNotFoundException;
import org.springframework.ldap.PartialResultException;
import org.springframework.ldap.ServiceUnavailableException;
import org.springframework.ldap.TimeLimitExceededException;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

public final class SafeDirectoryReader {
    private final LdapTemplate ldapTemplate;

    public SafeDirectoryReader(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public Optional<String> findCnByUid(String uid) {
        if (uid == null || uid.isBlank()) {
            throw new IllegalArgumentException("uid không được rỗng");
        }

        Name dn = LdapNameBuilder.newInstance("ou=people")
                .add("uid", uid)
                .build();

        try {
            String cn = ldapTemplate.lookup(
                    dn,
                    (AttributesMapper<String>) attrs -> {
                        Attribute attribute = attrs.get("cn");
                        if (attribute == null || attribute.size() == 0) {
                            throw new IllegalStateException(
                                    "Entry tồn tại nhưng thiếu cn");
                        }
                        return attribute.get().toString();
                    });
            return Optional.ofNullable(cn);
        } catch (NameNotFoundException ex) {
            return Optional.empty();
        } catch (PartialResultException ex) {
            throw new IncompleteDirectoryResultException(ex);
        } catch (TimeLimitExceededException ex) {
            throw new DirectoryTimeoutException(ex);
        } catch (CommunicationException | ServiceUnavailableException ex) {
            throw new DirectoryUnavailableException(ex);
        }
    }

    public static final class DirectoryUnavailableException
            extends RuntimeException {
        public DirectoryUnavailableException(Throwable cause) {
            super("LDAP không khả dụng", cause);
        }
    }

    public static final class DirectoryTimeoutException
            extends RuntimeException {
        public DirectoryTimeoutException(Throwable cause) {
            super("LDAP search vượt giới hạn thời gian", cause);
        }
    }

    public static final class IncompleteDirectoryResultException
            extends RuntimeException {
        public IncompleteDirectoryResultException(Throwable cause) {
            super("LDAP không thể xác nhận kết quả đầy đủ", cause);
        }
    }
}
```

Trong thực tế, `PartialResultException` thường xuất hiện ở **search có referral**, còn `lookup` thường không có luồng enumeration nhiều entry tương tự. Ví dụ service trên gom chính sách exception vào một vị trí để dễ test, **không khẳng định `lookup` luôn ném mọi loại exception này**. Để kiểm thử referral có ý nghĩa, dùng thêm **search** ở phần tiếp theo.

### 8.1. JUnit 5 + Mockito: mạng lỗi không phải not found

```java
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import javax.naming.Name;
import org.junit.jupiter.api.Test;
import org.springframework.ldap.CommunicationException;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;

class SafeDirectoryReaderTest {
    @Test
    @SuppressWarnings("unchecked")
    void communicationFailureMustNotBecomeEmptyResult() {
        LdapTemplate template = mock(LdapTemplate.class);

        when(template.lookup(
                any(Name.class), any(AttributesMapper.class)))
                .thenThrow(new CommunicationException(
                        new javax.naming.CommunicationException(
                                "Simulated connection drop")));

        SafeDirectoryReader reader = new SafeDirectoryReader(template);

        assertThrows(
                SafeDirectoryReader.DirectoryUnavailableException.class,
                () -> reader.findCnByUid("an"));
    }
}
```

Unit test này chứng minh **nhánh xử lý**: không đánh đồng exception giao tiếp với `Optional.empty()`. Nó **không đo** read timeout thật và không kiểm tra certificate của server; các mục tiêu đó cần integration/fault test.

### 8.2. Thử nghiệm phân loại theo bảng

Bộ unit test nên mô phỏng lần lượt các exception được Spring LDAP chuyển từ JNDI:

| Mock ném ra | Kỳ vọng service |
| --- | --- |
| `org.springframework.ldap.NameNotFoundException` | `Optional.empty()` cho `lookup` một DN |
| `org.springframework.ldap.CommunicationException` | `DirectoryUnavailableException` |
| `org.springframework.ldap.ServiceUnavailableException` | `DirectoryUnavailableException` |
| `org.springframework.ldap.TimeLimitExceededException` | `DirectoryTimeoutException` |
| `org.springframework.ldap.PartialResultException` | `IncompleteDirectoryResultException` |
| `org.springframework.ldap.NoPermissionException` | Không bị chuyển thành “không thấy entry”; xử lý phân quyền riêng |
| `org.springframework.ldap.AuthenticationException` | Không bị chuyển thành sai password của người dùng khi đang dùng service account |

**Bắt đúng package:** dùng `org.springframework.ldap.*` quanh `LdapTemplate`; JNDI ném các exception checked `javax.naming.*` mà Spring LDAP thường đã chuyển đổi. Không dùng `catch (Exception)` để tạo kết quả rỗng cho mọi lỗi.

## 9. Kiểm thử referral và kết quả không đầy đủ

LDAP referral xuất hiện khi server chỉ nơi có dữ liệu ở naming context khác. Một search có thể nhận một số entry ở server A và `SearchResultReference` hướng đến server B. Nếu client không theo được reference, JNDI/Spring LDAP có thể báo `PartialResultException`.

### 9.1. Ma trận referral

| Case | `ContextSource` referral mode | Cấu hình | Kết quả cần kiểm tra |
| --- | --- | --- | --- |
| REF-01 | `ignore` | Search cục bộ không có referral | Trả danh sách đúng trong scope được hỏi |
| REF-02 | `ignore` | Có continuation reference đến B; B không được xử lý | Có thể ném `PartialResultException`; không khẳng định coverage toàn hệ thống |
| REF-03 | `follow` | B hợp lệ, reachable, được phép truy cập | Client cố theo referral; xác minh entry từ nguồn mong đợi và bảo mật |
| REF-04 | `follow` | B không reachable | Có timeout/lỗi, không được coi dữ liệu A là kết quả toàn bộ |
| REF-05 | `follow` | Referral đến host ngoài allowlist | Không gửi credential/dữ liệu nhạy cảm đến host lạ |
| REF-06 | `throw` | Server gửi referral | JNDI có thể ném `ReferralException` cho xử lý thủ công; test ở tầng phù hợp |
| REF-07 | `ignore` + Spring ignorePartialResultException=true | Referral bị bỏ qua | Search có thể trả dữ liệu cục bộ; caller phải biết **có thể thiếu** |
| REF-08 | B trả size/time limit | Tổng hợp kết quả A+B | Không báo `complete=true` nếu nguồn B chưa được xử lý đủ |

**Lưu ý:** chế độ `ignore` có thể khiến JNDI gửi **ManageDsaIT control** trong LDAPv3; cách server hỗ trợ control/referral quyết định liệu `PartialResultException` xuất hiện. **Không đặt assertion “ignore phải luôn ném exception”** trên mọi server. Hãy ghi rõ topology và hành vi mong đợi của provider đang kiểm thử.

### 9.2. Unit test riêng cho search

Sử dụng query builder để không ghép filter bằng chuỗi từ input:

```java
import java.util.List;
import org.springframework.ldap.PartialResultException;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import static org.springframework.ldap.query.LdapQueryBuilder.query;

public final class StrictPeopleSearch {
    private final LdapTemplate ldapTemplate;

    public StrictPeopleSearch(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<String> searchByUid(String uid) {
        try {
            return ldapTemplate.search(
                    query().base("ou=people").where("uid").is(uid),
                    (AttributesMapper<String>) attrs ->
                            String.valueOf(attrs.get("uid").get()));
        } catch (PartialResultException ex) {
            throw new IllegalStateException(
                    "Không thể xác nhận search LDAP đã đủ kết quả", ex);
        }
    }
}
```

Kiểm thử mock:

```java
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import org.junit.jupiter.api.Test;
import org.springframework.ldap.PartialResultException;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;

class StrictPeopleSearchTest {
    @Test
    @SuppressWarnings("unchecked")
    void partialResultMustNotBeTreatedAsComplete() {
        LdapTemplate template = mock(LdapTemplate.class);

        when(template.search(
                any(LdapQuery.class), any(AttributesMapper.class)))
                .thenThrow(new PartialResultException(
                        new javax.naming.PartialResultException(
                                "Simulated continuation reference failure")));

        StrictPeopleSearch service = new StrictPeopleSearch(template);

        assertThrows(IllegalStateException.class,
                () -> service.searchByUid("an"));
    }
}
```

**Giới hạn của test:** khi `LdapTemplate.setIgnorePartialResultException(true)`, exception được bỏ qua **bên trong template** nên service **không có cờ nào tự động cho biết bị bỏ qua**. Với API yêu cầu kết quả đầy đủ, nên cấu hình strict policy và kiểm soát phạm vi nguồn từ đầu; mock service không chứng minh đã tìm đủ mọi domain.

### 9.3. Kiểm thử “không đủ dữ liệu” thực sự

Với môi trường A/B, tạo:

```text
LDAP-A: uid=an,ou=people,dc=example,dc=test
LDAP-B: uid=binh,ou=people,dc=branch,dc=test
```

Cho một truy vấn nghiệp vụ yêu cầu **hai domain** và kiểm tra:

- Cả A/B được truy vấn thành công → có An và Bình, `complete=true` chỉ khi điều kiện completeness đã được xác minh.
- A thành công, B timeout/referral không xử lý được → **không** công bố kết quả “toàn bộ nhân viên” chỉ có An.
- Nếu API chủ ý “chỉ domain A”, kết quả có An là đúng **trong scope A**, không nói gì về B.
- Referral tới server B không có TLS hợp lệ → từ chối kết nối, không gửi password sang B trên kênh không đáng tin.
- Các nguồn trả cùng đối tượng theo nhiều đường → định nghĩa quy tắc de-duplicate; tránh đếm đôi hoặc ghép nhầm identity.

Tính đầy đủ phải được định nghĩa theo **phạm vi nghiệp vụ**, không chỉ bằng việc `LdapTemplate.search(...)` đã trả về `List` không rỗng.

## 10. Fault injection cho lỗi mạng

Tạo các sự cố có kiểm soát bằng proxy mạng test hoặc một server giả. Những công cụ như Toxiproxy, proxy TCP tùy chỉnh hoặc test harness của hệ thống có thể đặt độ trễ, ngắt kết nối và chặn phản hồi. **Không phụ thuộc vào tên sản phẩm**: điều quan trọng là tạo đúng giai đoạn lỗi.

### 10.1. Ma trận lỗi mạng

| Case | Fault được tạo | Điều cần xác nhận |
| --- | --- | --- |
| NET-01 | Hostname không phân giải | Root cause có thể liên quan DNS; không retry vô hạn |
| NET-02 | TCP port bị từ chối (RST/refused) | Báo lỗi kết nối nhanh; không gọi là connect timeout nếu không chờ |
| NET-03 | SYN không có phản hồi / kết nối không hoàn tất | Connect timeout có giới hạn |
| NET-04 | TCP kết nối được nhưng không nhận LDAP response | Read timeout có giới hạn; không trả kết quả rỗng |
| NET-05 | TCP reset trong lúc search | Lỗi availability; không coi danh sách đã đọc là toàn bộ |
| NET-06 | TLS handshake bị treo hoặc đóng giữa chừng | Không gửi simple-bind credential sau handshake thất bại |
| NET-07 | Idle connection trong pool bị server/load balancer đóng | Không tái sử dụng vô hạn connection hỏng; xử lý loại bỏ hoặc tạo lại |
| NET-08 | Server A mất, server B còn | Failover theo policy, TLS/ACL/replication được kiểm chứng |
| NET-09 | Nhiều request đồng thời cùng timeout | Không tạo retry storm; tôn trọng concurrency/deadline |
| NET-10 | Phản hồi Add/Modify/Delete bị mất **sau khi server xử lý** | Trạng thái ghi chưa rõ; không tự retry write |

Nếu test giả chỉ ném một exception trước khi gọi LDAP, nó không thể chứng minh hành vi của client khi socket mất giữa chừng. Vì vậy cần **ít nhất một integration/fault test thật** cho việc “request đã gửi, response bị mất”, bằng server/proxy test có thể điều khiển đúng thời điểm.

### 10.2. Test retry: đo số lần thực hiện, không chỉ kết quả cuối

Một chiến lược retry đúng cần:

- Phân loại **lỗi có thể tạm thời** so với lỗi cấu hình cố định (DNS sai, truststore sai, bind credential sai, ACL thiếu).
- Giới hạn số lần thử và **deadline tổng**, không đơn thuần đợi `read.timeout` mỗi lần.
- Backoff và jitter; giới hạn đồng thời/circuit breaker để tránh dồn tải lên LDAP đang yếu.
- Phân biệt thao tác **đọc** với **ghi có tác dụng phụ**; không bật retry mù quáng cho `bind`/`modifyAttributes`/`unbind`.

Trong unit test, dùng mock/spy để đo số lần method `lookup`/`search` được gọi. Trong fault test, ghi nhận request **thực tế đến server**; số lần code cố gọi không nhất thiết bằng số request server đã nhận khi có lỗi kết nối.

### 10.3. Mất phản hồi sau khi ghi: trạng thái không xác định

```text
Client                     Network proxy                     LDAP
  │                             │                             │
  ├───────────── Add ───────────>│───────────── Add ───────────>│
  │                             │                             ├─ Entry đã tạo
  │                             X<──── response success ──────┤
  │
  ├─ timeout / CommunicationException
  │
  └─ KHÔNG tự Add lại
      └─ Đối soát entry / idempotency / source đã nhận request
```

Tiêu chí PASS của test write-outcome-unknown là:

1. Server test **đã tạo entry** trong trường hợp fault được dựng.
2. Client vẫn nhận timeout hoặc lỗi giao tiếp vì phản hồi bị chặn.
3. Logic ứng dụng **không tự phát lại Add** chỉ vì nhận `CommunicationException`.
4. Khi cần, service báo trạng thái chưa xác định/đối soát hoặc đọc lại trạng thái an toàn.
5. Nếu có retry có chủ đích, nó phải dựa trên hợp đồng idempotent và kiểm chứng dữ liệu, không chỉ coi `NameAlreadyBoundException` là bằng chứng request trước đã thành công.

Với LDAP replication, đọc ngay trên replica khác có thể chưa thấy entry vừa tạo. Test failover phải tính đến giới hạn consistency đó.

## 11. Unit test ngăn retry ghi không kiểm soát

Ví dụ service có hợp đồng tạo entry một lần. Khi mất phản hồi, nó **không tự gửi lại** trong cùng lời gọi:

```java
import javax.naming.Name;
import javax.naming.directory.Attributes;

import org.springframework.ldap.CommunicationException;
import org.springframework.ldap.core.LdapTemplate;

public final class OneShotEntryWriter {
    private final LdapTemplate ldapTemplate;

    public OneShotEntryWriter(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public void add(Name relativeDn, Attributes attributes) {
        try {
            ldapTemplate.bind(relativeDn, null, attributes);
        } catch (CommunicationException ex) {
            // Không kết luận server chưa tạo entry.
            throw new WriteOutcomeUnknownException(ex);
        }
    }

    public static final class WriteOutcomeUnknownException
            extends RuntimeException {
        public WriteOutcomeUnknownException(Throwable cause) {
            super("Không xác định được kết quả ghi LDAP", cause);
        }
    }
}
```

Unit test bằng Mockito:

```java
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.isNull;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;

import javax.naming.Name;
import javax.naming.directory.Attributes;
import javax.naming.directory.BasicAttributes;
import javax.naming.ldap.LdapName;

import org.junit.jupiter.api.Test;
import org.springframework.ldap.CommunicationException;
import org.springframework.ldap.core.LdapTemplate;

class OneShotEntryWriterTest {
    @Test
    void lostResponseMustNotTriggerAnAutomaticSecondAdd() throws Exception {
        LdapTemplate template = mock(LdapTemplate.class);
        doThrow(new CommunicationException(
                new javax.naming.CommunicationException(
                        "Response lost after Add")))
                .when(template)
                .bind(any(Name.class), isNull(), any(Attributes.class));

        OneShotEntryWriter writer = new OneShotEntryWriter(template);
        Name dn = new LdapName("uid=an,ou=people");
        Attributes attrs = new BasicAttributes(true);

        assertThrows(
                OneShotEntryWriter.WriteOutcomeUnknownException.class,
                () -> writer.add(dn, attrs));

        verify(template, times(1)).bind(dn, null, attrs);
    }
}
```

Unit test xác nhận service không gọi lệnh tạo lần hai **trong một lần xử lý**. Nó không bảo đảm infrastructure retry tự động ở HTTP client, message broker hoặc proxy đã bị tắt; cần test hệ thống ở lớp ngoài và quan sát số Add thực sự đến LDAP server.

## 12. Kiểm thử pooling, failover và thay đổi danh tính

Với pooling, lỗi mạng có thể chỉ xuất hiện **sau thời gian idle**:

```text
Context được lấy từ pool
    ├── Connection còn sống → Search thành công
    └── Connection stale     → reset / timeout
                                  │
                                  ▼
                     Pool bỏ / tạo lại context phù hợp
```

Những ca quan trọng:

1. Server test đóng connection sau khi idle, pool vẫn còn reference → client phát hiện connection lỗi, không lặp lại mãi với cùng connection hỏng.
2. Pool đạt max connections → request phải tuân thủ deadline chờ, không treo vô hạn.
3. Pool bị đóng/recreate khi ứng dụng shutdown/restart → không rò thread/socket/context.
4. Bind theo người dùng A và B trong hai request riêng → không tái sử dụng trạng thái A cho B; không lẫn quyền giữa các identity.
5. Failover từ A sang B → xác minh B có TLS hợp lệ, ACL phù hợp và dữ liệu đủ nhất quán cho query.

Không bật pooling tùy tiện cho mọi context được tạo trong quá trình xác thực người dùng, đặc biệt với StartTLS; kiểm tra khả năng hỗ trợ và hướng dẫn của provider. Nếu ứng dụng dùng `PoolingContextSource` hay JNDI pooling, các lựa chọn kiểm tra stale connection có thể khác nhau theo phiên bản; test phải khớp cấu hình đang sử dụng.

## 13. Tính bảo mật của kết quả test

LDAP test thường xử lý credential, DN, membership và attribute nhạy cảm. Một pipeline chạy được nhưng **ghi lộ password ra build log** vẫn là thất bại về bảo mật.

### 13.1. Không dùng những mẹo làm test TLS “xanh” giả

- Không có `TrustManager` tin tất cả certificate.
- Không tắt hostname verification hoặc chấp nhận certificate hết hạn.
- Không hạ từ `ldaps://` sang `ldap://` khi test thất bại, trừ khi đó là kịch bản StartTLS được bảo vệ đúng.
- Không bỏ qua `SSLHandshakeException` để thử simple bind gửi password qua plaintext.
- Không gửi credential đến referral host ngoài allowlist.
- Không ghi truststore password, private key hay bind secret vào assertion message/log.

### 13.2. Giữ log có ích mà không rò dữ liệu

Ví dụ bản ghi được làm sạch:

```json
{
  "event": "ldap_operation_failed",
  "case": "NET-04",
  "operation": "search",
  "directoryAlias": "test-ldap-a",
  "exception": "org.springframework.ldap.CommunicationException",
  "rootCauseType": "java.net.SocketTimeoutException",
  "timeoutCategory": "read",
  "attempt": 1,
  "requestId": "test-2f91"
}
```

Các tên và mã là **dữ liệu minh họa**, không phải kết quả đo thật. Ghi loại thao tác, endpoint alias, thời gian, số lần thử, root-cause *type*, correlation ID, tình trạng completeness. Tránh log full DN, password, token, filter chứa PII, diagnostic message thô hoặc referral URL chưa được kiểm tra.

### 13.3. Không dùng dữ liệu partial cho quyết định quyền

Nếu search membership được dùng để quyết định quyền truy cập:

- Không biến `PartialResultException` thành `List.of()` rồi suy ra “không có group” như một kết quả đã được xác minh.
- Nếu không thể xác minh quyền, áp dụng chính sách truy cập an toàn của ứng dụng (thường không cấp quyền mới từ dữ liệu thiếu) **và báo lỗi kiểm tra quyền**, không phát hành kết luận giả.
- Test nên có tình huống membership chỉ tồn tại ở domain B trong khi B unreachable, để chắc chắn dịch vụ **không cấp quyền sai** và không khẳng định đã truy vấn đủ.

## 14. Tính ổn định trong CI và tiêu chí PASS/FAIL

Fault tests có nhiều nguy cơ flaky hơn unit tests. Để kết quả có giá trị:

| Rủi ro trong CI | Cách kiểm soát |
| --- | --- |
| Cổng trùng khi chạy song song | Cấp dynamic port, cô lập test network/container |
| DNS cache của JVM | Dùng topology/hostname rõ ràng và môi trường tách biệt; không dựa vào thời điểm cache hết hạn |
| Timing phụ thuộc scheduler | Assert hành vi theo deadline đủ rộng, không chính xác từng mili giây |
| Proxy chưa sẵn sàng | Health-check test server/proxy trước khi gây lỗi |
| Server test còn dữ liệu từ suite trước | Fixture/reset/isolated container cho từng suite |
| Truststore global giữa test song song | Tách JVM/process hoặc SSL context theo client |
| Sự cố chưa đúng giai đoạn | Ghi nhận server có nhận request hay chưa; phân biệt refused/connect timeout/read timeout |
| Referral bị bỏ qua âm thầm | Kiểm tra cấu hình `ignorePartialResultException` và coverage thực tế |
| Retry từ tầng ngoài bị bỏ sót | Quan sát cả ứng dụng, HTTP client, message broker và request đích LDAP |
| Chỉ chạy test thành công | Luôn có negative cases cho TLS, ACL, timeout, referral và network |

Một test **PASS** không chỉ vì “không bị treo” hoặc “exception được ném”; phải chứng minh kết quả đáp ứng hợp đồng:

- Không leak credential.
- Không coi lỗi mạng là “entry không tồn tại”.
- Không coi dữ liệu partial là đầy đủ khi nghiệp vụ yêu cầu completeness.
- Không gửi lại thao tác ghi khi không biết server đã áp dụng hay chưa.
- Không retry vượt ngân sách hoặc tạo tải không kiểm soát.
- Không có tác dụng phụ tồn đọng làm ảnh hưởng test tiếp theo.

## 15. Bài thực hành theo từng bước

### Bài 1 — Test TLS âm tính

Chuẩn bị một LDAP test server có certificate do CA test cấp. Chạy cùng một lệnh `lookup` trong hai JVM với truststore **tin** và **không tin** CA đó.

**Mục tiêu:** kết nối hợp lệ thành công; trường hợp CA không tin cậy thất bại trước khi thực hiện thao tác LDAP; cả hai test không tắt certificate validation.

### Bài 2 — Phân biệt refused với read timeout

Tạo hai fault:

1. Port đóng trả TCP RST nhanh.
2. Proxy nhận TCP nhưng giữ LDAP response trong thời gian dài hơn read timeout.

**Mục tiêu:** cả hai được xử lý như lỗi hạ tầng, nhưng **loại nguyên nhân và thời điểm** được ghi nhận khác nhau; không dùng cùng một câu “connect timeout” cho cả hai.

### Bài 3 — Referral và completeness

Chuẩn bị hai nguồn A/B, mỗi nguồn có một user. Định nghĩa API yêu cầu kết quả từ **cả hai**. Làm B unavailable.

**Mục tiêu:** API không trả danh sách chỉ chứa A như thể là toàn bộ hệ thống. Nếu có chế độ dữ liệu cục bộ, API phải diễn đạt scope và khả năng incomplete.

### Bài 4 — Timeout sau Add

Proxy chuyển Add tới LDAP server, cho server xử lý, nhưng cố ý chặn phản hồi. Kiểm tra entry thật sau test.

**Mục tiêu:** client nhìn thấy lỗi chưa xác định; hệ thống không phát lại Add vô điều kiện; cơ chế đối soát hoặc idempotency xử lý trường hợp lần đầu đã thành công.

### Bài 5 — Retry storm

Mô phỏng nhiều request đọc đồng thời khi server phản hồi chậm. Đếm số request thực tế tới LDAP và độ trễ toàn bộ API.

**Mục tiêu:** mỗi request có retry hữu hạn và deadline, tổng lượng request không phình vượt ngưỡng cấu hình, circuit breaker/concurrency limit hoạt động nếu hệ thống sử dụng.

## 16. Câu hỏi tự đánh giá

**Câu 1.** Unit test mô phỏng `CommunicationException` có chứng minh cấu hình `read.timeout` của JNDI hoạt động không?

**Đáp án:** Không. Nó chỉ kiểm tra policy xử lý exception. Cần network fault-injection/integration test để đánh giá socket timeout thật.

**Câu 2.** Vì sao một test “TCP refused” không đủ để xác nhận connect timeout?

**Đáp án:** Refused có thể trả lỗi tức thì. Connect timeout cần tình huống không hoàn tất giai đoạn mở kết nối trong thời hạn.

**Câu 3.** Test LDAPS thành công có chứng minh StartTLS an toàn không?

**Đáp án:** Không. Đây là hai đường khởi tạo TLS khác nhau; StartTLS cần kiểm tra upgrade trước bind và từ chối khi upgrade thất bại.

**Câu 4.** `LdapTemplate.setIgnorePartialResultException(true)` có làm cho tìm kiếm xuyên nhiều domain đầy đủ không?

**Đáp án:** Không. Nó bỏ qua exception trong những đường search liên quan; caller có thể mất tín hiệu về referral chưa xử lý.

**Câu 5.** Trong test lỗi mạng sau Add, server đã tạo entry nhưng client timeout. Có nên tự động Add lại?

**Đáp án:** Không. Cần xác minh trạng thái/idempotency hoặc báo outcome unknown; Add lại có thể nhận `NameAlreadyBoundException` hoặc tạo tác dụng phụ ngoài dự kiến.

**Câu 6.** Khi referral trỏ đến một host không tin cậy, test cần chứng minh điều gì?

**Đáp án:** Client không tự gửi credential hoặc dữ liệu nhạy cảm tới host đó; có chính sách kiểm soát target, TLS và giới hạn referral rõ ràng.

**Câu 7.** Vì sao LDAP nhúng không đủ để kiểm tra mọi lỗi Active Directory?

**Đáp án:** Schema, referral/forest, Global Catalog, certificate policy và hành vi lỗi mạng của vendor có thể khác; cần môi trường test đúng tính năng muốn xác minh.

**Câu 8.** Khi test timeout, nên assert chính xác `elapsed == 1200ms` không?

**Đáp án:** Không. Đo độ trễ trong ngân sách và biên đủ rộng, kết hợp bằng chứng fault đúng giai đoạn; tránh test flaky do JVM, scheduler hoặc nhiều endpoint.

## 17. Tài liệu tham khảo

- [Spring LDAP — Testing](https://docs.spring.io/spring-ldap/reference/testing.html): `spring-ldap-test`, embedded LDAP dựa trên UnboundID/ApacheDS và cấu hình fixture.
- [Spring LDAP — Configuration](https://docs.spring.io/spring-ldap/reference/configuration.html): `ContextSource`, referral và các tùy chọn của `LdapTemplate`.
- [Spring LDAP API — `LdapTemplate`](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/core/LdapTemplate.html): `setIgnorePartialResultException`, `setIgnoreSizeLimitExceededException`, search time limit và thao tác LDAP.
- [Spring LDAP API — `LdapContextSource`](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/core/support/LdapContextSource.html): cấu hình và lifecycle context.
- [Java SE — JNDI `java.naming` module](https://docs.oracle.com/en/java/javase/26/docs/api/java.naming/module-summary.html): `com.sun.jndi.ldap.connect.timeout` và `read.timeout` của JDK LDAP provider.
- [Oracle JNDI — Setting Timeout for LDAP Operations](https://docs.oracle.com/javase/tutorial/jndi/newstuff/readtimeout.html): hành vi `read.timeout`.
- [Oracle JNDI — Referrals in the JNDI](https://docs.oracle.com/javase/jndi/tutorial/ldap/referral/jndi.html): `ignore`/`follow`/`throw` và ManageDsaIT.
- [RFC 4511 — LDAP Protocol](https://www.rfc-editor.org/rfc/rfc4511): Search, referral, time/size limit và các mã kết quả.
- [RFC 4513 — LDAP Authentication and Security](https://www.rfc-editor.org/rfc/rfc4513): xác thực LDAP và bảo vệ thông tin xác thực.
- [RFC 2696 — LDAP Simple Paged Results](https://www.rfc-editor.org/rfc/rfc2696): cookie paging khi cần lấy nhiều trang kết quả.

**Ghi nhớ:** Một bộ kiểm thử Spring LDAP đáng tin phải chứng minh **đúng hành vi khi phụ thuộc không khỏe**, không chỉ khi mọi thứ thành công. Tách kiểm thử TLS, connect/read/search timeout, referral completeness và network fault theo từng lớp; kiểm tra loại exception đúng package; không bỏ qua lỗi để trả kết quả rỗng; giữ credential an toàn và kiểm soát mọi retry, nhất là sau thao tác ghi có trạng thái chưa xác định.
