# Đối chiếu hành vi trên máy chủ giống production

Một bài kiểm thử LDAP có thể chạy xanh trên embedded server nhưng vẫn thất bại khi triển khai lên directory thật. Nguyên nhân thường nằm ở khác biệt giữa hai máy chủ: schema, matching rule, ACL, TLS, referral, giới hạn Search, password policy, overlay hoặc replication topology.

Với Spring Data LDAP, repository và LdapTemplate gửi LDAP operation qua JNDI/Spring LDAP. Ứng dụng nhìn thấy kết quả do server xử lý và do Bind identity được cấp quyền. Vì vậy, kiểm thử có giá trị cao cần chạy trên máy chủ cùng họ sản phẩm, phiên bản, schema và policy gần với môi trường production. Embedded LDAP vẫn hữu ích cho unit test và kiểm tra mapping cơ bản, nhưng không thể đại diện cho mọi semantics của OpenLDAP, Active Directory hay directory service thương mại.

Bài thuộc chương **Kiểm thử** của mô-đun **SPRING_DATA_LDAP**. Chúng ta sẽ xác định mức độ tương đồng cần có, dựng directory test có thể tái tạo, cấu hình Spring Boot kết nối endpoint động, kiểm thử schema/ACL/TLS/referral/limits, đánh giá khác biệt giữa OpenLDAP và Active Directory, mô phỏng replication và tổ chức pipeline an toàn.

> **Nguyên tắc:** “giống production” có nghĩa là tái tạo những đặc tính có thể làm thay đổi hành vi ứng dụng. Dùng dữ liệu synthetic và directory cô lập; không chạy test ghi/xóa trên production thật.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vì sao embedded LDAP test chưa đủ để chứng minh tương thích production.
2. Xây dựng ma trận parity cho server version, schema, ACL, TLS, referral và server limits.
3. Chọn đúng loại test: unit, embedded, container integration, staging acceptance và read-only smoke test.
4. Dựng LDAP test server từ image/build đã pin version và cấu hình.
5. Nạp schema, naming context, service account, ACL và fixture theo thứ tự có kiểm soát.
6. Cấu hình Spring Boot bằng endpoint/port động qua `@DynamicPropertySource`.
7. Kiểm thử repository, LdapTemplate, DN, objectClass và attribute mapping trên server mục tiêu.
8. Phát hiện khác biệt về case matching, uniqueness, group schema và filter behavior.
9. Kiểm thử Bind identity và quyền Read/Add/Modify/Delete thực tế.
10. Kiểm tra LDAPS/StartTLS, certificate chain, hostname verification và truststore.
11. Kiểm thử referral, paging, sorting, size/time limit và partial result.
12. Phân biệt kiểm thử một node với kiểm thử replication topology.
13. Quản lý fixture, test isolation, cleanup và parallel execution.
14. Thiết kế test pipeline tái tạo được mà không phụ thuộc production data hoặc credential thật.

## 2. Vì sao cần máy chủ giống production?

LDAP protocol chuẩn hóa request/response, nhưng mỗi directory server có schema, matching rule, ACL model, extension, overlay và cấu hình vận hành riêng. Cùng một SearchRequest có thể trả kết quả khác nhau khi:
- Attribute có matching rule khác.
- Schema cho phép hoặc từ chối một entry.
- Bind identity được cấp quyền khác.
- Server có size/time limit khác.
- Referral được trả về hoặc tự động theo đuổi.
- Paging/sort/assertion control không được hỗ trợ hoặc bị giới hạn.
- Password policy áp dụng quy tắc riêng.
- Một thao tác Modify bị overlay/plugin tác động.
- Client đọc từ replica chưa nhận thay đổi mới.

Một test chỉ xác minh code gọi đúng method không chứng minh server thật chấp nhận operation.

### 2.1. Embedded test và production-like test trả lời câu hỏi khác nhau

| Loại môi trường | Phù hợp để kiểm tra | Không chứng minh được |
| --- | --- | --- |
| Mock repository/LdapTemplate | Nhánh logic, xử lý exception, mapping ở mức unit | LDAP protocol, schema, ACL và server behavior |
| Embedded LDAP | DN cơ bản, Bind/Search/Add/Modify/Delete, ODM mapping nhanh | Hành vi đúng của sản phẩm/version production |
| Container cùng server family | Schema, ACL, controls, TLS và behavior của build được đóng gói | Replication/topology hoặc policy hạ tầng chưa được dựng |
| Dedicated integration environment | Kết nối, network, certificate, service account, referral, replica | Không tự động chứng minh mọi trạng thái production |
| Staging acceptance | Deployment config, secret injection, routing, policy gần production | Không tự động chứng minh mọi trạng thái production |
| Production smoke test chỉ đọc | DNS/TLS/Bind/Search tối thiểu theo phê duyệt | Không được dùng để test destructive write hoặc fault injection |

Embedded server vẫn rất hữu ích: khởi động nhanh, test cô lập và phản hồi sớm. Hãy dùng nó ở tầng test phù hợp, rồi bổ sung contract/integration test trên server thực tế.

### 2.2. Chọn mức parity theo rủi ro

Không phải test nào cũng cần toàn bộ production topology. Ví dụ:
- Test mapping `@Entry`/`@Attribute` có thể chạy embedded.
- Test ACL cần server có ACL model và rule tương ứng production.
- Test password policy cần đúng directory product/config.
- Test referral cần ít nhất hai naming context/server và routing.
- Test replication cần topology nhiều node.
- Test TLS cần certificate chain và hostname verification thật.
- Test paging cần control và server policy tương ứng.

Đặt yêu cầu parity trước khi viết test để tránh một bộ test chạy xanh nhưng không bao phủ rủi ro quan trọng.

## 3. Lập ma trận parity với production

Bắt đầu bằng cách ghi lại các thuộc tính ảnh hưởng đến hành vi ứng dụng. Thông tin này cần được đội vận hành/LDAP administrator xác nhận; không suy đoán từ URL hoặc tên server.

| Chiều parity | Cần đối chiếu | Vì sao ảnh hưởng |
| --- | --- | --- |
| Server family | OpenLDAP, Active Directory, 389 Directory Server hoặc sản phẩm đang dùng | Schema, ACL, extension và semantics khác nhau |
| Server version/build | Major/minor/patch, vendor build, hotfix | Bug fix và default có thể thay đổi |
| Schema | Core schema, custom schema, objectClass, attribute syntax | Entry có thể Add/Modify thành công ở test nhưng bị production từ chối |
| Naming context | Base DN, OU, naming context | Search base và DN resolution |
| Matching rules | Case ignore/exact, substring, ordering, equality | Filter có thể khớp nhiều/ít entry khác nhau |
| ACL | Bind identity, quyền trên entry/attribute/subtree | Search có thể thiếu attribute hoặc write bị từ chối |
| Authentication | Simple Bind, SASL, Kerberos, service account policy | Cách xác thực và credential lifecycle |
| TLS | LDAPS/StartTLS, CA, SAN, protocol/cipher policy | Kết nối test plaintext không phát hiện lỗi trust |
| Referral | Referral URL, chase policy, credentials forwarding | Search có thể trả partial result hoặc đi sang server khác |
| Search controls | Paging, sort, assertion, ManageDsaIT nếu dùng | Server có thể không hỗ trợ hoặc giới hạn control |
| Limits | Size/time/admin limit, connection limit | Result có thể partial hoặc operation bị từ chối |
| Password policy | Complexity, expiry, lockout, password modify extension | Password test có thể pass ở local nhưng fail production |
| Overlay/plugin | Referential integrity, memberOf, uniqueness, audit | Side effect server-side thay đổi dữ liệu |
| Replication | Single node, multi-master, provider/consumer, read routing | Read-after-write có thể trễ hoặc khác node |
| Network | DNS, firewall, proxy, latency, MTU | Timeout và referral behavior |
| Pooling | Pool size, validation, idle timeout | Connection stale và giới hạn concurrency |

### 3.1. Ghi nhận phiên bản cụ thể

Tránh ghi chung “OpenLDAP” hoặc “AD”. Hãy ghi:
- Product và exact version/build đã được administrator xác nhận.
- Image digest hoặc package build dùng cho integration test.
- Schema bundle/version.
- ACL/config bundle commit.
- TLS CA/certificate profile.
- Server control/limit configuration.
- Test fixture version.

Nếu production đang chạy nhiều version do rolling upgrade, kiểm thử cả hai version trong thời gian chuyển đổi hoặc xác định version nào là compatibility floor.

### 3.2. Không sao chép production data để tạo parity

Parity là parity của server/configuration, không phải sao chép dữ liệu người thật. Dùng UID/email/name synthetic, DN trong naming context test riêng, password test tạo tại runtime, group và membership giả, custom attribute không chứa dữ liệu cá nhân và snapshot cấu hình đã được review, loại bỏ secret.

Không đưa LDIF dump production vào Git hoặc test artifact. Nếu cần dữ liệu đại diện, tạo synthetic dataset có cùng kiểu dữ liệu, cardinality và quan hệ.

## 4. Thiết kế test pyramid cho Spring Data LDAP

Một pipeline thực tế nên có nhiều tầng:

~~~mermaid
flowchart TD
    A["Unit tests: query/service logic"] --> B["Embedded LDAP: ODM and basic operations"]
    B --> C["Same-family container: schema, ACL, controls"]
    C --> D["Dedicated integration: TLS, network, referral, topology"]
    D --> E["Staging acceptance: deployed config and identity"]
    E --> F["Approved read-only production smoke"]
~~~

### 4.1. Unit test

Kiểm tra service chọn đúng base/scope/filter, input validation, mapping DTO, exception translation và logic saga/journal. Mock không nên giả lập server semantics quá sâu. Nếu mock trả đúng kết quả bạn mong muốn, test có thể che lỗi server thật.

### 4.2. Embedded LDAP

Kiểm tra nhanh:
- `@Entry`, `@Id`, `@Attribute`.
- DN build/parse.
- Basic Bind/Search.
- Add/Modify/Delete.
- Filter escaping ở các case cơ bản.

Embedded server phải được coi là một implementation riêng. Không dùng test pass ở embedded để kết luận ACL, TLS, referral, matching rule hoặc password policy production đã đúng.

### 4.3. Container cùng server family

Đây là tầng chính cho contract/integration:
- Dùng cùng family và version/build mục tiêu.
- Nạp schema/configuration đã version hóa.
- Dựng Bind identity và ACL gần production.
- Dùng LDIF fixture synthetic.
- Chạy test repository và LdapTemplate bằng đúng application identity.
- Dừng container sau test.

Với Active Directory, một container OpenLDAP không thể thay thế domain controller. Có thể cần dedicated AD test domain hoặc môi trường lab được quản lý bởi đội IAM.

### 4.4. Dedicated integration/staging

Dùng khi cần kiểm tra TLS certificate và hostname trên network thực, DNS/firewall/routing, referral giữa naming context, replication và read-after-write behavior, connection pool dưới latency thực, password policy và secret manager/workload identity.

Staging cần dữ liệu synthetic và access policy tương tự production. Không cho test harness tự động trỏ sang production khi biến endpoint bị thiếu.

## 5. Dựng LDAP test server có thể tái tạo

Một production-like test environment phải được tạo từ source-of-truth có version:
- Server image/package version.
- Schema files.
- Server configuration.
- ACL.
- TLS certificates test.
- Naming context.
- Service accounts.
- Fixture LDIF.
- Readiness check.

Cấu trúc thư mục minh họa:

~~~text
src/test/
├── java/
│   └── com/example/directory/
│       ├── DirectoryRepositoryIT.java
│       ├── DirectoryAclIT.java
│       └── DirectoryTlsIT.java
└── resources/
    └── ldap/
        ├── openldap/
        │   ├── schema/
        │   ├── config/
        │   ├── acl/
        │   └── bootstrap/
        ├── fixtures/
        │   ├── 00-base.ldif
        │   ├── 10-service-accounts.ldif
        │   ├── 20-people.ldif
        │   └── 30-groups.ldif
        └── test-ca/
~~~

Nếu production là AD, tạo bộ test riêng với schema/OU/ACL của AD. Không cố dùng chung LDIF OpenLDAP rồi thêm điều kiện runtime để che khác biệt.

### 5.1. Pin image hoặc package

Không dùng tag `latest`. Dùng version cụ thể, tốt hơn là digest bất biến do pipeline quản lý.

Ví dụ Docker Compose minh họa:

~~~yaml
services:
  ldap-it:
    image: registry.example.test/directory/openldap:2.6.8-build3
    ports:
      - "127.0.0.1:1389:389"
      - "127.0.0.1:1636:636"
    volumes:
      - ./ldap/config:/etc/ldap-test/config:ro
      - ./ldap/schema:/etc/ldap-test/schema:ro
      - ./ldap/bootstrap:/etc/ldap-test/bootstrap:ro
      - ./ldap/test-ca:/etc/ldap-test/tls:ro
    healthcheck:
      test: ["CMD", "/opt/ldap-test/bin/healthcheck"]
      interval: 5s
      timeout: 3s
      retries: 20
~~~

`registry.example.test` và đường dẫn trong container là placeholder của image nội bộ. Mỗi LDAP image có cách mount config, import schema, tạo suffix và healthcheck riêng; hãy thay bằng quy ước của image đã được chọn. Điều quan trọng là image phải pin version và được build từ cùng server family/build mà production dùng.

Không publish LDAP port ra mọi network interface của máy CI nếu test chỉ cần loopback. Nếu CI dùng Docker network nội bộ, không cần publish port ra host.

### 5.2. Thứ tự bootstrap

Một quy trình bootstrap điển hình:

1. Khởi động server.
2. Chờ LDAP protocol readiness, không chỉ chờ container process running.
3. Load schema cần thiết.
4. Tạo naming context/base DN.
5. Tạo OU phục vụ service account và fixture.
6. Tạo reader/writer test account.
7. Áp ACL.
8. Nạp people/group fixture.
9. Kiểm tra Bind bằng từng identity.
10. Chạy test suite.

Nếu schema load sau khi import entry, các objectClass/attribute tùy chỉnh có thể bị từ chối. Nếu ACL áp trước khi tạo service account, bootstrap có thể cần một administrator bootstrap riêng; credential này chỉ tồn tại trong test harness và không dùng bởi application.

### 5.3. Readiness không chỉ là cổng TCP mở

Port 389/636 mở chưa chứng minh server đã load schema, naming context đã sẵn sàng, Bind identity đã được tạo, ACL đã được áp, TLS certificate đã được load hoặc fixture import hoàn tất.

Healthcheck nên thực hiện Bind/Search nhẹ bằng account test hoặc một readiness probe được giới hạn. Test không nên bắt đầu chỉ vì container có trạng thái `running`.

## 6. Cấu hình Spring Boot với endpoint động

Không hardcode port container. Test harness có thể cấp host/port thực tế sau khi container khởi động.

Ví dụ dùng Testcontainers `GenericContainer` làm wrapper cho một image đã được cấu hình sẵn. Image cụ thể và bootstrap script là theo server đã chọn:

~~~java
@Testcontainers
@SpringBootTest
@ActiveProfiles("it")
class DirectoryRepositoryIT {

    private static final String LDAP_IMAGE =
            System.getProperty("ldap.it.image");

    @Container
    static final GenericContainer<?> ldap =
            new GenericContainer<>(
                    DockerImageName.parse(LDAP_IMAGE))
                    .withExposedPorts(389)
                    .waitingFor(Wait.forListeningPort());

    @DynamicPropertySource
    static void ldapProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.ldap.urls", () ->
                "ldap://" + ldap.getHost() + ":"
                        + ldap.getMappedPort(389));
        registry.add("spring.ldap.base", () ->
                "dc=example,dc=org");
        registry.add("spring.ldap.username", () ->
                "cn=svc-app,ou=service,dc=example,dc=org");
        registry.add("spring.ldap.password", () ->
                "it-only-bind-secret");
    }

    @Autowired
    DirectoryPersonRepository repository;

    // Tests dùng fixture được image/bootstrap tạo trước khi context chạy.
}
~~~

Các import cần thiết thuộc JUnit 5, Testcontainers, Spring Boot Test và Spring Data LDAP. `LDAP_IMAGE` phải được cung cấp bởi build pipeline với version/digest đã pin. `GenericContainer` chỉ chờ cổng mở; trong dự án thực, nên dùng WaitStrategy/readiness probe kiểm tra LDAP Bind/Search và đảm bảo bootstrap đã hoàn tất trước khi Spring context sử dụng directory.

Ví dụ giả định bootstrap đã tạo `dc=example,dc=org`, service account `cn=svc-app,...`, ACL và fixture. Password trong snippet là secret giả dành riêng cho test. Không dùng nó trong staging/production.

### 6.1. TLS test cần cấu hình riêng

Không đổi `ldaps://` thành `ldap://` chỉ để test chạy dễ hơn nếu production bắt buộc TLS. Với LDAPS:
- Expose port TLS của server test.
- Cấp CA test cho JVM truststore.
- Certificate SAN phải khớp hostname client sử dụng.
- Giữ hostname verification bật.
- Test cả certificate hết hạn/CA không tin cậy trong test âm.
- Không dùng TrustAllStrategy hoặc tắt validation.

Với StartTLS, kiểm thử đúng thứ tự StartTLS handshake rồi Bind. Một kết nối LDAP plaintext trước khi StartTLS thành công có thể làm lộ credential nếu client tiếp tục Bind.

### 6.2. Không đưa secret vào test report

Không log password LDAP, Bind credential, private key/truststore password, full environment dump hoặc LDIF chứa secret.

Có thể assert endpoint/profile và Bind thành công mà không in password. Secret test nên được tạo riêng cho job và hết hạn sau pipeline.

## 7. Fixture và isolation

Fixture phải phản ánh schema thật nhưng không mang dữ liệu production.

Ví dụ naming context test:

~~~text
dc=example,dc=org
├── ou=people
│   ├── uid=lan
│   ├── uid=minh
│   └── ou=engineering
│       └── uid=mai
├── ou=groups
│   └── cn=engineering
└── ou=service
    ├── cn=svc-app
    ├── cn=svc-reader
    └── cn=svc-writer
~~~

### 7.1. Fixture cần kiểm tra gì?

- Parent entry tồn tại trước child.
- `objectClass` đúng schema.
- Attribute bắt buộc đầy đủ.
- DN được encode/parse đúng.
- Group membership tham chiếu DN tồn tại nếu schema/policy yêu cầu.
- Attribute có matching rule như production.
- Marker test không thể nhầm với dữ liệu thật.
- Service account có ACL đúng sau bootstrap.

Nếu schema production dùng custom objectClass, fixture phải load cùng schema version hoặc một compatibility schema được administrator phê duyệt.

### 7.2. Dùng namespace riêng cho mỗi test

Có thể tạo OU riêng theo test run:

~~~text
ou=run-20261126-8f2a,ou=tests,dc=example,dc=org
├── ou=people
└── ou=groups
~~~

UID trong mỗi run có thể lặp lại vì base DN khác nhau. Nếu server không cho tạo OU test riêng, dùng prefix UID duy nhất và cleanup đúng các DN đã tạo.

Không cho hai test chạy song song cùng Add/Modify một DN. Nếu cần test concurrency, đó phải là test chủ động phối hợp hai actor trên cùng fixture, không phải race ngẫu nhiên giữa test case độc lập.

### 7.3. Cleanup theo ownership

Mỗi test ghi lại DN mà nó tạo. Cleanup:
- Xóa child trước parent.
- Xóa group membership/entry phụ thuộc theo đúng schema.
- Chỉ xóa entry có marker/namespace của test run.
- Không dùng recursive delete trên naming context dùng chung.
- Báo lỗi nếu cleanup bị ACL từ chối.
- Nếu container disposable, ưu tiên hủy toàn bộ container sau suite.

Không swallow cleanup error. Directory còn fixture sót lại có thể khiến test sau pass giả hoặc fail không ổn định.

## 8. Kiểm thử ODM và repository trên server mục tiêu

Test repository cần chạy với đúng ContextSource, LdapTemplate, Bind identity và schema của server test.

### 8.1. Entity mẫu

~~~java
@Entry(objectClasses = {
        "top",
        "person",
        "organizationalPerson",
        "inetOrgPerson"
})
public class DirectoryPerson {

    @Id
    private Name dn;

    @Attribute(name = "uid")
    private String uid;

    @Attribute(name = "cn")
    private String commonName;

    @Attribute(name = "sn")
    private String surname;

    @Attribute(name = "mail")
    private String email;

    // Constructors and accessors omitted.
}
~~~

### 8.2. Test round-trip Add/Lookup/Delete

~~~java
@SpringBootTest
class DirectoryPersonRoundTripIT {

    @Autowired
    DirectoryPersonRepository repository;

    @Test
    void addThenLookupMapsEntryOnTargetServer() {
        DirectoryPerson person = new DirectoryPerson();
        person.setDn(LdapNameBuilder.newInstance("ou=people")
                .add("uid", "it-lan-001").build());
        person.setUid("it-lan-001");
        person.setCommonName("Integration Test Lan");
        person.setSurname("Test");
        person.setEmail("it-lan-001@example.test");

        repository.save(person);

        Optional<DirectoryPerson> found =
                repository.findById(person.getDn());

        assertTrue(found.isPresent());
        assertEquals("it-lan-001", found.get().getUid());
        assertEquals("Integration Test Lan",
                found.get().getCommonName());

        repository.deleteById(person.getDn());
    }
}
~~~

Đây là skeleton minh họa; entity cần constructor/accessor và ID generation đúng với mô hình repository của dự án. Test phải chạy bằng Bind identity ứng dụng. Không dùng admin Bind cho test round-trip nếu production application chỉ có quyền writer hạn chế. Nên đặt cleanup trong `@AfterEach` hoặc test fixture manager để entry được dọn cả khi assertion thất bại.

### 8.3. Test schema rejection

Tạo một entry thiếu attribute MUST hoặc chứa objectClass không được server hỗ trợ. Kỳ vọng:
- LDAP server từ chối Add/Modify.
- Exception được translate thành lỗi phù hợp.
- Journal ghi confirmed rejection nếu server trả LDAP error response.
- Không biến lỗi schema thành kết quả Search rỗng.

Không hardcode mã lỗi schema chung cho mọi server nếu test suite hỗ trợ nhiều sản phẩm. Assert error category/diagnostic theo adapter của server và ghi lại product/version.

## 9. Kiểm thử matching rule và filter semantics

Một filter có thể chạy khác nhau giữa server nếu attribute syntax hoặc matching rule khác.

Các ca nên có:
- So sánh UID phân biệt/không phân biệt hoa thường.
- Equality trên email.
- Substring/wildcard.
- Ordering `>=`/`<=` trên attribute có matching rule phù hợp.
- Attribute không tồn tại.
- Multi-valued attribute.
- Unicode/diacritics nếu ứng dụng hỗ trợ tên quốc tế.
- Escape các ký tự filter đặc biệt.
- Attribute có caseIgnoreMatch so với caseExactMatch.

Ví dụ test theo kỳ vọng đã được xác nhận từ schema:

~~~java
@Test
void equalitySearchUsesProductionMatchingRule() {
    LdapQuery query = query()
            .base("ou=people")
            .searchScope(SearchScope.SUBTREE)
            .where("uid").is("LAN");

    List<DirectoryPerson> result =
            repository.findAll(query);

    // Kỳ vọng phải được xác định từ schema/matching rule của target.
    assertEquals(expectedCaseMatchCount, result.size());
}
~~~

`expectedCaseMatchCount` là fixture expectation theo server profile, không phải biến có sẵn. Không viết test mong case-insensitive nếu schema production định nghĩa exact matching hoặc ngược lại.

### 9.1. Test LDAP injection

Dùng input có ký tự `*`, `(`, `)`, dấu gạch chéo ngược và NUL. So sánh query builder/parameterized filter với việc nối chuỗi thô. Test phải chứng minh input được xử lý như một assertion value, không thể thay đổi cấu trúc filter.

### 9.2. Test attribute syntax

Một attribute có thể là Directory String, Integer, DN, Generalized Time hoặc binary. Test string đơn giản có thể che việc schema production yêu cầu syntax khác.

Fixture nên có giá trị hợp lệ, giá trị biên, giá trị sai syntax, multi-value nếu schema cho phép và DN reference có escaped comma/plus khi phù hợp.

## 10. Kiểm thử ACL bằng đúng Bind identity

ACL test cần nhiều identity tách biệt:
- Reader.
- Writer.
- Compensator/admin automation nếu workflow yêu cầu.
- Bootstrap administrator chỉ dùng để dựng môi trường test.

Không dùng Bind DN quản trị để chạy toàn bộ integration suite; điều đó khiến ứng dụng có thể pass dù ACL production sẽ từ chối.

### 10.1. Ma trận quyền

| Test actor | Search/Read | Add | Modify | Delete |
| --- | --- | --- | --- | --- |
| Application reader | Có trong subtree cần thiết | Không | Không | Không |
| Application writer | Có các field cần thiết | Có trong OU được cấp | Có attribute được cấp | Không mặc định |
| Compensator | Read snapshot/ownership | Chỉ khi restore được duyệt | Chỉ attribute cần bù | Chỉ subtree/entry thuộc operation |
| Bootstrap admin | Chỉ trong setup | Setup | Setup | Setup |

Ma trận là ví dụ; policy thực tế phải khớp quyền production đã được phê duyệt.

### 10.2. Test positive và negative

Ví dụ:
1. Reader Search được `ou=people`.
2. Reader không thể Modify `mail`.
3. Writer Add được user trong `ou=people`.
4. Writer không thể Add vào `ou=service`.
5. Writer Modify được `title` nhưng không được sửa `userPassword`.
6. Writer không thể Delete user nếu policy không cấp.
7. Compensator chỉ xóa entry có provisioning marker đúng.
8. Mọi identity bị từ chối ở subtree ngoài phạm vi.

Không chỉ assert thao tác được phép thành công. Negative authorization test quan trọng ngang positive test.

### 10.3. Phân biệt API authorization và LDAP ACL

API có thể cho phép một operator yêu cầu reset user, nhưng LDAP Bind identity vẫn cần quyền cụ thể để thực hiện. Ngược lại, Bind identity có quyền Delete không có nghĩa mọi HTTP caller được phép kích hoạt Delete.

Kiểm thử cả hai lớp:
- Application authorization: ai được gọi use case.
- LDAP ACL: service identity được thao tác gì trên directory.

## 11. Kiểm thử TLS và authentication

Production-like TLS test cần xác minh handshake thực, không chỉ cấu hình property.

### 11.1. LDAPS

Kiểm thử:
- Server certificate còn hiệu lực.
- Certificate chain tới CA test tin cậy.
- SAN khớp hostname client sử dụng.
- JVM truststore có CA đúng.
- Hostname verification không bị tắt.
- Bind chỉ diễn ra sau TLS handshake.
- CA sai hoặc hostname sai làm connection thất bại.

Không dùng trust-all manager trong test integration. Nếu test luôn chấp nhận mọi certificate, nó không phát hiện lỗi cấu hình TLS production.

### 11.2. StartTLS

Nếu production dùng StartTLS:
1. Kết nối LDAP.
2. Thực hiện StartTLS extended operation.
3. Xác minh certificate.
4. Chỉ sau khi TLS thành công mới Bind.
5. Nếu StartTLS thất bại, đóng connection; không fallback plaintext trừ khi policy production cho phép tường minh.

Test cả trường hợp server không hỗ trợ StartTLS và CA không tin cậy.

### 11.3. Authentication policy

Với SASL/Kerberos hoặc cơ chế xác thực khác Simple Bind:
- Dùng dedicated test realm/domain.
- Kiểm tra ticket/keytab được cấp đúng.
- Kiểm tra clock skew.
- Kiểm tra service principal/SPN.
- Không copy keytab production.
- Test credential rotation và expiry trong môi trường riêng.

Nếu ứng dụng chỉ dùng Simple Bind qua LDAPS, đừng kết luận test SASL đã được bao phủ.

## 12. Kiểm thử referral và nhiều naming context

Một LDAP server có thể trả referral khi Search chạm tới naming context khác. Cấu hình referral của JNDI/Spring LDAP ảnh hưởng việc client chase referral, bỏ qua hay ném partial result.

Test cần xác định:
- Referral URL được trả về ở base/scope nào.
- Client có chase referral không.
- Credential có được gửi sang referred server không.
- TLS trust có đúng cho server đích không.
- Vòng lặp referral có được ngăn không.
- Referral có làm kết quả partial không.
- Ứng dụng có phân biệt partial result với empty result không.

~~~mermaid
flowchart LR
    A["Application"] --> B["LDAP server A"]
    B -->|Search base in A| C["Search result"]
    B -->|Referral to naming context B| D["Referral policy"]
    D -->|Chase enabled| E["LDAP server B"]
    D -->|Ignore/throw| F["Partial or referral outcome"]
    E --> G["Combined result or error"]
~~~

### 12.1. Không giả định credential forwarding an toàn

Chase referral có thể tạo kết nối tới endpoint khác. Cần kiểm tra hostname/port nằm trong allowlist, TLS certificate của referred server được xác minh, Bind credential có được forward hay không, referral server có cùng trust boundary không và network policy có cho phép kết nối đó không.

Không bật referral chasing rộng chỉ để Search test pass. Chỉ chase các referral cần thiết và được quản lý.

### 12.2. Test nhiều naming context

Dựng ít nhất hai server/context trong test topology hoặc môi trường integration được kiểm soát. Tạo referral thật và xác minh ứng dụng xử lý kết quả theo policy. Mock referral URL trong unit test không thay thế integration test.

## 13. Kiểm thử limits, paging và controls

Production server có thể áp limit thấp hơn test embedded server.

### 13.1. Size và time limit

Test:
- Search trả ít hơn size limit.
- Search vượt size limit.
- Search chậm vượt time limit.
- Client count limit thấp hơn server limit.
- Bind identity có policy limit riêng.
- Partial result có bị framework bỏ qua hoặc chuyển thành exception không.

Không coi danh sách partial là đầy đủ. API tầng trên nên phân biệt complete result, explicit empty result, limit exceeded/partial result và directory unavailable.

### 13.2. Paged Results Control

Nếu ứng dụng dùng RFC 2696:
- Kiểm tra server hỗ trợ paged results.
- Kiểm tra page size tối đa.
- Kiểm tra cookie được giữ giữa các request.
- Không tái sử dụng cookie sau khi search context đã hết hiệu lực.
- Kiểm tra cookie gắn với cùng Bind identity/query.
- Đóng paging sequence đúng cách nếu client/server yêu cầu.
- Xác minh tổng số entry qua nhiều page.

Một test server không bật paged results không thể chứng minh paging production hoạt động.

### 13.3. Server-side sorting và assertion

Nếu dùng server-side sort hoặc Assertion Control, kiểm thử OID control được server hỗ trợ, control critical/non-critical được xử lý như mong muốn, ACL có cho phép operation không, unsupported critical control trả lỗi đúng, assertion false không sửa entry và sort key có matching rule phù hợp.

Không giả định tất cả LDAP server hỗ trợ cùng controls hoặc cùng policy.

## 14. Kiểm thử password policy và account lifecycle

Password là phần thường khác nhau rõ nhất giữa server.

Các khác biệt:
- Password syntax/complexity.
- Minimum age/history.
- Expiration.
- Lockout threshold/duration.
- Password reset vs user change.
- Must-change-at-next-login.
- Password Modify Extended Operation.
- Account disabled/locked/expired.
- Quyền admin reset khác quyền user đổi password.

### 14.1. Dùng test account riêng

Không dùng password người thật. Tạo account disposable và password ngẫu nhiên tại runtime. Đảm bảo password không xuất hiện trong log, LDIF, test report hoặc exception message.

### 14.2. Test negative policy

Thử password yếu, password reuse, expired password hoặc account locked theo policy của test server. Kỳ vọng exception/error code có thể khác theo product; map thành domain error ở adapter thay vì để business layer phụ thuộc mã lỗi riêng của server.

### 14.3. Account disable không có semantics chung

Active Directory có `userAccountControl`; OpenLDAP có thể dựa vào overlay/password policy hoặc schema/policy khác. Test phải xác minh khả năng đăng nhập thật bị từ chối, không chỉ kiểm tra attribute đã thay đổi.

Nếu production dùng SSO hoặc authentication gateway, cần test toàn bộ authentication path hoặc adapter thực tế. LDAP entry attribute đơn lẻ không chứng minh user không thể đăng nhập.

## 15. Kiểm thử overlay, plugin và uniqueness

Server-side extension có thể thay đổi kết quả operation:
- Referential integrity overlay cập nhật DN reference khi entry bị Rename/Delete.
- `memberOf` overlay duy trì group backlink.
- Uniqueness overlay từ chối duplicate attribute.
- Audit overlay ghi event.
- Password policy module áp dụng lockout/expiry.
- Custom plugin thay đổi default hoặc validate attribute.

### 15.1. Test overlay như một phần cấu hình

Ghi version/config của overlay cùng server image. Test:
- Add user rồi Add group member.
- Rename user và xác minh reference theo policy.
- Delete user và xác minh group member có bị cleanup không.
- Add duplicate email/UID và xác minh uniqueness.
- Password policy reject và lockout.
- Audit record xuất hiện sau write.

Không giả định overlay production luôn được bật trong test chỉ vì image cùng family.

### 15.2. Không để overlay che lỗi ứng dụng

Nếu overlay tự xóa membership khi Delete user, test ứng dụng vẫn nên xác minh trạng thái group sau compensation. Server-side behavior có thể khác theo naming context hoặc ACL.

## 16. Kiểm thử replication và consistency

Một container đơn không mô phỏng replication. Nếu production có multi-master hoặc provider/consumer replication, cần topology riêng.

Các tình huống:
- Write vào node A, read ngay từ node A.
- Write vào node A, read từ replica B.
- Replication lag.
- Replica unavailable.
- Conflict do concurrent write trên hai node.
- Failover giữa request.
- Referral/traffic routing sang node khác.
- Operational attribute/version khác nhau.

### 16.1. Read-after-write phải biết endpoint

Nếu Add thành công ở node A nhưng Search được route sang replica B chưa đồng bộ, test có thể thấy entry chưa tồn tại. Đây không nhất thiết chứng minh Add thất bại.

Journal cần ghi endpoint/node đã gửi write nếu hạ tầng cho phép nhận diện. Reconciliation nên đọc từ authoritative node hoặc endpoint có consistency guarantee phù hợp. Không retry Add mù chỉ vì replica chưa nhìn thấy entry.

### 16.2. Test eventual consistency

Đo thời gian từ write commit tới khi replica đọc thấy entry, thời gian membership đồng bộ, behavior khi replica lag vượt SLA, behavior khi replica mất kết nối và cách ứng dụng phản hồi trạng thái pending.

Không hardcode một thời gian ngắn tùy ý rồi coi mọi replication lag là lỗi. Dùng SLA/contract đã thống nhất với đội directory.

### 16.3. Test concurrent updates

Hai writer cập nhật cùng entry có thể tạo last-writer-wins hoặc conflict tùy operation/server. Dùng Assertion Control/version/precondition nếu nghiệp vụ cần bảo vệ. Kiểm thử bằng hai connection độc lập, không chỉ hai thread dùng chung một object Java.

## 17. Test connection pool và lỗi mạng

Production-like network cần mô phỏng:
- Connect timeout.
- Read timeout.
- Server restart.
- Stale pooled connection.
- TLS handshake failure.
- DNS resolution delay/failure.
- Referral endpoint unavailable.
- Connection limit reached.
- Network interruption sau khi server áp dụng write nhưng trước response.

Test write response loss đặc biệt quan trọng: client có thể không biết LDAP đã áp dụng operation chưa. Khi đó trạng thái phải là UNKNOWN và recovery phải đối soát.

Không biến mọi CommunicationException thành “operation failed chắc chắn”. Giữ cause chain, phân loại outcome và kiểm tra trạng thái thực tế trước retry/compensation.

## 18. So sánh OpenLDAP và Active Directory trong test

Một bộ contract test có thể chạy trên nhiều server profile, nhưng expectation cần có phần chung và phần đặc thù.

| Chủ đề | OpenLDAP thường gặp | Active Directory thường gặp |
| --- | --- | --- |
| Person object | `inetOrgPerson` phổ biến nếu schema được load | `user` theo AD schema |
| Group object | `groupOfNames`, `groupOfUniqueNames` hoặc schema riêng | `group` |
| Login attribute | `uid` thường dùng | `sAMAccountName`/UPN |
| Account enable | Password policy/overlay hoặc custom schema | `userAccountControl` |
| ACL | `olcAccess`/ACL configuration | AD security descriptors/ACL |
| Membership | `member` tùy group schema | `member`, linked attribute semantics |
| Password policy | Overlay/policy module và server config | Domain password policy/fine-grained policy |
| Naming context | Suffix cấu hình của directory | Domain/Configuration/Schema naming contexts |
| Referral | Referral configuration | Referral và domain/forest topology |
| Controls/extensions | Phụ thuộc version/module | Phụ thuộc AD DS version/policy |

Đây là định hướng so sánh, không phải khẳng định mọi deployment đều dùng cấu hình mặc định. Hãy xác minh schema và policy thực tế của tổ chức.

### 18.1. Chia contract chung và adapter riêng

Contract chung có thể kiểm tra Bind thành công bằng service identity, Search trong base được phép, ODM map stable attributes, filter input được escape, Add/Modify/Delete trong subtree test và lỗi được translate thành domain outcome.

Adapter-specific test kiểm tra objectClass/attribute riêng, account disable/password policy, ACL syntax/semantics, referral và controls, group membership behavior.

Không ép một test fixture giống hệt chạy trên mọi directory nếu schema khác nhau. Mục tiêu là cùng một business contract, với adapter và fixture phù hợp từng server.

## 19. Pipeline CI/CD cho production-like LDAP test

Một pipeline gợi ý:

~~~mermaid
flowchart TD
    A["Compile and unit tests"] --> B["Embedded LDAP tests"]
    B --> C["Start pinned LDAP container"]
    C --> D["Bootstrap schema, base, ACL and fixtures"]
    D --> E["Wait for Bind/Search readiness"]
    E --> F["Repository and LdapTemplate integration tests"]
    F --> G["TLS, ACL, controls and failure tests"]
    G --> H["Destroy disposable environment"]
    H --> I["Dedicated staging acceptance"]
    I --> J["Approved read-only production smoke"]
~~~

### 19.1. Fast feedback

Unit/embedded tests chạy mỗi commit để phát hiện lỗi nhanh. Same-family container tests chạy trong CI hoặc pull request theo thời gian pipeline cho phép. Staging acceptance chạy trước release hoặc theo cadence được định nghĩa.

### 19.2. Pin và cache image an toàn

- Pin image digest/version.
- Quét image theo quy trình supply chain.
- Không dùng tag mutable `latest`.
- Cache image theo digest.
- Ghi lại digest trong test report.
- Update image có review khi production nâng version.

### 19.3. Lưu artifact test

Có thể lưu server version/build, image digest, schema/config revision, test result và correlation ID, LDAP result code đã redact, metrics latency/limit và container log đã lọc secret/PII.

Không lưu Bind password, private key, LDIF chứa dữ liệu thật hoặc full directory dump.

### 19.4. Dọn môi trường kể cả khi test fail

Dùng lifecycle hook của Testcontainers/CI để hủy container, network và volume test. Với dedicated shared server, dùng test namespace riêng và cleanup job có ownership guard.

Không để test fail giữa chừng tạo entry vĩnh viễn trong directory dùng chung.

## 20. Production smoke test an toàn

Production smoke test chỉ thực hiện thao tác đã được phê duyệt, thường gồm:
- DNS resolve endpoint.
- TLS handshake và certificate validation.
- Bind bằng health-check identity quyền thấp.
- Base Search trên một health entry đã định nghĩa.
- Kiểm tra response time và availability.
- Kiểm tra naming context/rootDSE nếu policy cho phép.

Không:
- Add/Delete user test vào production.
- Thử password yếu để kích hoạt lockout.
- Thay đổi group membership.
- Chạy fault injection/proxy drop response.
- Đọc hàng loạt attribute nhạy cảm.
- Dùng Domain Admin/rootdn làm health check.

Health-check account chỉ cần quyền tối thiểu trên một entry hoặc subtree probe. Rate limit và timeout phải thấp, không tạo tải đáng kể.

## 21. Test report và bằng chứng parity

Mỗi lần chạy integration test nên lưu một manifest:

~~~yaml
testEnvironment:
  serverFamily: openldap
  serverVersion: "2.6.8"
  imageDigest: "sha256:..."
  schemaRevision: "directory-schema-17"
  aclRevision: "ldap-acl-9"
  fixtureRevision: "fixture-12"
  tlsProfile: "test-ca-v3"
  topology: single-node
  testRunId: "it-20261126-8f2a"
~~~

Các giá trị trên chỉ minh họa. CI cần ghi dữ liệu thật từ image/config được khởi chạy. Nếu server version hoặc schema revision không khớp compatibility matrix, report phải đánh dấu môi trường không tương thích thay vì chỉ ghi test pass.

### 21.1. Phân loại kết quả

- **PASS:** test chạy trên parity profile được chấp thuận.
- **FAIL:** hành vi khác expectation.
- **SKIPPED:** feature không nằm trong profile này.
- **NOT_APPLICABLE:** server không hỗ trợ feature và ứng dụng không yêu cầu.
- **ENVIRONMENT_MISMATCH:** server/schema/ACL/TLS không đúng cấu hình đã khai báo.
- **INCONCLUSIVE:** server unavailable, partial result hoặc test harness không xác định được outcome.

Không gộp SKIPPED/INCONCLUSIVE thành PASS.

## 22. Lỗi thường gặp khi đối chiếu production

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Chỉ test embedded LDAP | Bỏ sót schema/ACL/server semantics | Bổ sung same-family integration test |
| Dùng `latest` image | Test thay đổi không kiểm soát | Pin version/digest |
| Dùng OpenLDAP thay AD | Test sai schema/ACL/password behavior | Dùng AD test domain cho AD production |
| Chỉ so sánh product name | Bỏ sót patch, overlay và config | Ghi version/build/config revision |
| Dùng admin Bind cho test | Che lỗi quyền ứng dụng | Test bằng reader/writer identity thực tế |
| Dùng plaintext LDAP trong test | Không phát hiện TLS/trust failure | Test LDAPS/StartTLS đúng production |
| Bỏ qua referral | Partial result hoặc credential forwarding ngoài ý muốn | Dựng referral topology và test policy |
| Không mô phỏng server limits | Search partial bị coi là đầy đủ | Test size/time limit và error handling |
| Dùng một node cho test replication | Không phát hiện read-after-write lag | Dựng topology nhiều node |
| Reuse DN giữa test song song | Race, duplicate và cleanup sai | Namespace riêng/test run ID |
| Import fixture trước schema | Entry bị từ chối hoặc mapping khác | Bootstrap schema trước fixture |
| Cleanup bằng recursive delete | Xóa entry ngoài test | Cleanup theo ownership và DN cụ thể |
| Chỉ test positive ACL | Không phát hiện quyền thừa | Thêm negative authorization tests |
| Tắt hostname verification | Test TLS xanh giả | Kiểm tra SAN/hostname thật |
| Log environment dump | Lộ secret | Redact và chỉ log metadata |
| Chạy destructive test trên production | Thay đổi dữ liệu thật | Chỉ test trên disposable/staging |
| Coi replica chưa thấy entry là Add thất bại | Retry trùng hoặc compensation sai | Đối soát authoritative node |
| Gộp partial result thành empty list | Che lỗi server | Phân biệt empty/partial/error |
| Không ghi image/schema revision | Không tái tạo được failure | Lưu parity manifest |

## 23. Checklist trước khi phát hành

| Hạng mục | Tiêu chí |
| --- | --- |
| Server family/version | Khớp compatibility target |
| Schema | Core/custom schema đúng revision |
| Naming context | Base DN và OU tương ứng |
| ACL | Reader/writer/compensator được test riêng |
| TLS | CA, chain, SAN, hostname verification |
| Authentication | Cơ chế Bind tương ứng production |
| Referral | Chase/ignore/error policy đã test |
| Matching rules | Equality/substring/order đã xác minh |
| Search limits | Size/time/partial result được test |
| Controls | Paging/sort/assertion được xác minh nếu ứng dụng dùng |
| Password policy | Negative/expiry/lockout được test nếu ứng dụng quản lý password |
| Overlay/plugin | Được bật và revision ghi trong manifest |
| Replication | Topology/lag/failover được test nếu production có replica |
| Pool/network | Timeout, stale connection, restart và response loss |
| Fixtures | Synthetic, schema-valid, isolated |
| Cleanup | Ownership guard, không recursive delete tùy tiện |
| CI evidence | Image digest, schema/ACL revision, report |
| Production smoke | Read-only, least privilege, approved |

## 24. Bài tập thực hành

**Bài 1 — Parity matrix.** Lập bảng so sánh production và integration server về product/version, schema, base DN, ACL, TLS, referral, controls và replication. Đánh dấu chiều nào chưa được tái tạo.

**Bài 2 — Container reproducible.** Dựng LDAP container cùng family/version production. Pin image digest, bootstrap schema/base/service account/ACL và fixture synthetic. Chạy test hai lần trên môi trường sạch để xác minh kết quả ổn định.

**Bài 3 — Repository contract.** Chạy cùng test findOne, findAll, Add, Modify, Rename và Delete trên embedded và same-family server. Ghi lại khác biệt thay vì điều chỉnh expectation để test pass giả.

**Bài 4 — ACL matrix.** Dùng reader/writer/compensator identity. Kiểm tra cả operation được phép và operation phải bị từ chối.

**Bài 5 — TLS.** Bật LDAPS với test CA. Chạy test CA đúng, CA sai, hostname sai và certificate hết hạn. Không tắt hostname verification.

**Bài 6 — Matching rule.** Tạo UID/email khác chữ hoa thường và kiểm tra equality/substring theo schema production.

**Bài 7 — Referral.** Dựng hai naming context/server, tạo referral và kiểm tra chase policy, TLS, credential forwarding và partial result.

**Bài 8 — Limits.** Cấu hình size/time limit thấp. Xác minh ứng dụng không coi partial list là đầy đủ và API trả lỗi phù hợp.

**Bài 9 — Replication lag.** Dựng hai node hoặc dùng integration lab. Write vào node A, đọc node B trước/sau replication; xác minh recovery không retry Add mù.

**Bài 10 — Password policy.** Tạo test account disposable, thử password không đạt policy, expiry và lockout. Không dùng credential production.

**Bài 11 — Network failure.** Drop response sau khi server áp dụng write. Xác minh journal chuyển UNKNOWN và reconciliation đọc đúng authoritative node.

**Bài 12 — Pipeline evidence.** Xuất parity manifest gồm server version, image digest, schema/ACL/fixture revision, TLS profile, topology và test run ID.

## 25. Câu hỏi tự đánh giá

1. Vì sao embedded LDAP không đủ để chứng minh production compatibility?
2. Những chiều parity nào có thể làm thay đổi Search result?
3. Vì sao server version/build cần được pin?
4. Schema và ACL ảnh hưởng Add/Modify như thế nào?
5. Vì sao test phải chạy bằng application Bind identity?
6. Tại sao test reader cần negative Modify/Delete assertions?
7. Vì sao TLS test phải xác minh hostname?
8. StartTLS phải diễn ra trước hay sau Bind?
9. Referral chasing có thể làm credential đi tới server nào?
10. Size limit có thể tạo partial result ra sao?
11. Count limit có phải paging không?
12. Vì sao một node không kiểm thử được replication?
13. Khi replica chưa thấy Add, vì sao không retry ngay?
14. Overlay uniqueness có thể làm test khác embedded server thế nào?
15. Vì sao OpenLDAP fixture không thể dùng nguyên xi trên AD?
16. Làm thế nào kiểm tra group membership và last-member constraint?
17. Vì sao password policy cần server thật hoặc server cùng product?
18. Testcontainer readiness cần kiểm tra gì ngoài TCP port?
19. Vì sao fixture phải synthetic và namespace riêng?
20. Cleanup recursive có rủi ro gì?
21. Khi nào cần staging acceptance thay vì container test?
22. Production smoke test nên được giới hạn ra sao?
23. Parity manifest cần lưu những revision nào?
24. Vì sao INCONCLUSIVE không được báo thành PASS?

**Ghi nhớ:** kiểm thử production-like phải tái tạo đúng server family/version, schema, ACL, TLS, referral, controls, limits và topology có ảnh hưởng đến ứng dụng. Embedded LDAP giúp phản hồi nhanh, còn same-family container và dedicated integration mới kiểm chứng semantics của server mục tiêu. Dùng fixture synthetic, Bind identity least privilege, namespace riêng và cleanup có ownership; chỉ chạy smoke test production ở chế độ read-only được phê duyệt.

### Tài liệu tham khảo

- [Spring LDAP — Testing](https://docs.spring.io/spring-ldap/reference/testing.html): test support, embedded LDAP và cách tổ chức kiểm thử Spring LDAP.
- [Spring LDAP — Configuration](https://docs.spring.io/spring-ldap/reference/configuration.html): ContextSource, pooling và cấu hình kết nối.
- [Spring Data LDAP — Reference](https://docs.spring.io/spring-data/ldap/reference/): repository và ODM.
- [Testcontainers for Java](https://java.testcontainers.org/): quản lý container disposable trong integration test.
- [Testcontainers — JUnit 5 integration](https://java.testcontainers.org/test_framework_integration/junit_5/): lifecycle container với JUnit Jupiter.
- [RFC 4511 — LDAP: The Protocol](https://www.rfc-editor.org/rfc/rfc4511.html): Bind, Search, Modify, referral và LDAP result codes.
- [RFC 4512 — LDAP Directory Information Models](https://www.rfc-editor.org/rfc/rfc4512.html): schema, DN, entry và attribute.
- [RFC 4513 — LDAP Authentication Methods and Security Mechanisms](https://www.rfc-editor.org/rfc/rfc4513.html): authentication và transport security.
- [RFC 4515 — LDAP Search Filters](https://www.rfc-editor.org/rfc/rfc4515.html): filter syntax và escaping.
- [RFC 2696 — LDAP Control Extension for Simple Paged Results Manipulation](https://www.rfc-editor.org/rfc/rfc2696.html): paged results control.
- [RFC 4528 — LDAP Assertion Control](https://www.rfc-editor.org/rfc/rfc4528.html): conditional update.
- [RFC 3062 — LDAP Password Modify Extended Operation](https://www.rfc-editor.org/rfc/rfc3062.html): password modify operation.
- [OpenLDAP Administrator's Guide](https://www.openldap.org/doc/admin26/): schema, ACL, overlays, replication và quản trị.
- [Microsoft Learn — Active Directory Domain Services](https://learn.microsoft.com/en-us/windows-server/identity/ad-ds/active-directory-domain-services): AD DS schema, directory partitions, security and replication.
