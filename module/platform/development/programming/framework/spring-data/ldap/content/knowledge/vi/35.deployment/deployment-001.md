# Tách cấu hình phát triển, kiểm thử và production

> **Chương:** Triển khai  
> **Phạm vi:** Spring Data LDAP — ứng dụng Java ánh xạ LDAP entry thành entity, truy vấn bằng repository hoặc `LdapTemplate`, thực hiện CRUD trên cây thư mục và bảo vệ kết nối tới directory server.

Khi viết một ứng dụng Spring Data LDAP, cùng một mã Java thường chạy ở ba môi trường khác nhau: **development (dev)**, **test** và **production (prod)**. Các môi trường dùng những directory server, tài khoản bind, cây DN, dữ liệu và chính sách bảo mật khác nhau. Nếu mã nguồn chứa cố định `ldap://localhost:389`, tài khoản quản trị hoặc `dc=example,dc=org`, việc chuyển môi trường sẽ dễ dẫn đến lỗi kết nối, ghi nhầm dữ liệu và lộ thông tin xác thực.

Giải pháp là giữ **logic repository/entity dùng chung** và tách **cấu hình kết nối, phạm vi thư mục, thông tin xác thực và chính sách vận hành** theo môi trường. Với ứng dụng dựa trên Spring Boot, cấu hình theo profile, biến môi trường và hệ thống quản lý bí mật giúp triển khai cùng một phiên bản ứng dụng mà không cần sửa rồi biên dịch lại mã nguồn.

Bài này trình bày một cấu trúc triển khai mẫu có thể điều chỉnh cho OpenLDAP, Active Directory hoặc directory server khác. Các ví dụ dùng Spring Boot với Spring Data LDAP/Spring LDAP; khi thay phiên bản Spring hoặc nhà cung cấp LDAP, cần kiểm tra lại khả năng hỗ trợ và hành vi của server.

## 1. Vì sao LDAP cần tách cấu hình theo môi trường?

LDAP khác một dịch vụ HTTP thông thường ở chỗ một thao tác `save(...)` hoặc `rename(...)` có thể trực tiếp thay đổi **entry trong cây thư mục dùng để xác thực, phân quyền hoặc quản lý danh tính**. Một URL kết nối đúng nhưng base DN sai vẫn có thể hướng thao tác tới tập entry không mong muốn.

| Thành phần | Dev | Test | Production |
|---|---|---|---|
| Directory server | Máy local/container thử nghiệm | Directory độc lập, thường tạo mới cho mỗi lần chạy kiểm thử | Directory được quản lý, có giám sát và sao lưu |
| URL/port | Ví dụ `ldap://127.0.0.1:1389` | URL/port được test harness cấp động | Ví dụ `ldaps://directory.corp.example:636` |
| Base DN | `dc=dev,dc=example` | `dc=test,dc=example` | DN do quản trị viên cấp |
| Bind account | Tài khoản thử nghiệm có phạm vi nhỏ | Tài khoản riêng của test, có thể tạo và dọn fixture | Service account với quyền tối thiểu |
| Dữ liệu | Dữ liệu giả, có thể đặt lại | Dữ liệu kiểm thử xác định trước, cô lập | Dữ liệu thật, cần bảo vệ |
| TLS và chứng chỉ | Có thể dùng LDAP thường trên loopback khi chỉ thử nghiệm | Có thể kiểm thử cả kết nối không mã hóa và TLS | Cần bảo vệ đường truyền, xác minh chứng chỉ |
| Mục tiêu | Phát triển nhanh, gỡ lỗi | Kết quả lặp lại được, không phụ thuộc prod | An toàn, ổn định, quan sát được, dễ khôi phục |

**Nguyên tắc:** test và dev tuyệt đối không sử dụng tài khoản hoặc endpoint production để thực hiện các ca CRUD, xóa, đổi DN hay thay đổi schema. Tài khoản, DNS, network policy và quyền truy cập phải giúp ngăn kết nối nhầm ngay cả khi ai đó chọn sai profile.

## 2. Phân biệt cấu hình ứng dụng và dữ liệu LDAP

Trong Spring Data LDAP, một entity có thể khai báo ánh xạ:

~~~java
import javax.naming.Name;
import org.springframework.ldap.odm.annotations.Attribute;
import org.springframework.ldap.odm.annotations.Entry;
import org.springframework.ldap.odm.annotations.Id;

@Entry(
    base = "ou=people",
    objectClasses = {
        "top", "person", "organizationalPerson", "inetOrgPerson"
    }
)
public class DirectoryPerson {
    @Id
    private Name dn;

    @Attribute(name = "uid")
    private String uid;

    @Attribute(name = "cn")
    private String commonName;

    @Attribute(name = "sn")
    private String surname;
}
~~~

Entity mô tả cách một entry được ánh xạ sang đối tượng Java; còn thuộc tính kết nối của `ContextSource` xác định **directory server** và **base DN** mà ứng dụng truy cập.

Ví dụ với cấu hình `spring.ldap.base=dc=dev,dc=example`, phần `@Entry(base="ou=people")` được hiểu trong phạm vi base của context. Ở prod, cùng một mapping có thể áp dụng dưới base DN khác, miễn cấu trúc OU, object class và attribute type thực sự tương thích.

Có ba nhóm cấu hình cần phân biệt:

1. **Kết nối:** URL, port, bind DN, mật khẩu, TLS, chứng chỉ, timeout.
2. **Mô hình thư mục:** base DN, OU chứa người dùng/nhóm, objectClass, schema, quy tắc DN và phạm vi tìm kiếm.
3. **Chính sách vận hành:** quyền bind, giới hạn truy vấn, log, giám sát, retry, quá trình cấp phát và thu hồi bí mật.

Không nên xem mọi thay đổi môi trường là một thao tác “thay URL”: nếu schema hoặc cây DN khác nhau, ứng dụng có thể kết nối thành công nhưng lỗi khi chạy truy vấn hoặc ghi entry.

## 3. Tổ chức cấu hình bằng Spring Boot profiles

Một cấu trúc quen thuộc:

~~~text
src/main/resources/
├── application.yml
├── application-dev.yml
├── application-test.yml
└── application-prod.yml

src/test/java/
└── .../DirectoryRepositoryIntegrationTest.java
~~~

Spring Boot tải `application.yml` dùng chung và áp dụng các giá trị từ file của profile đang hoạt động. Thông thường, cấu hình môi trường cụ thể sẽ ghi đè giá trị cùng khóa của cấu hình chung; biến môi trường, tham số dòng lệnh và nguồn thuộc tính khác cũng có thứ tự ưu tiên riêng.

**File chung — `application.yml`**

~~~yaml
spring:
  application:
    name: ldap-directory-service

app:
  directory:
    people-ou: ou=people
    groups-ou: ou=groups
~~~

File này chỉ chứa cấu hình thực sự dùng chung và không chứa tài khoản/mật khẩu. Các `app.directory.*` là khóa do ứng dụng tự định nghĩa; Spring Boot không tự dùng chúng để cấu hình `LdapTemplate`. Nếu triển khai service có đọc các khóa này, hãy ánh xạ chúng bằng `@ConfigurationProperties` hoặc cơ chế đọc cấu hình tương đương.

**File dev — `application-dev.yml`**

~~~yaml
spring:
  ldap:
    urls: ${LDAP_DEV_URL:ldap://127.0.0.1:1389}
    base: ${LDAP_DEV_BASE_DN:dc=dev,dc=example}
    username: ${LDAP_DEV_BIND_DN:cn=admin,dc=dev,dc=example}
    password: ${LDAP_DEV_BIND_PASSWORD}
~~~

Trong môi trường local:

- URL mặc định chỉ hướng tới `127.0.0.1`, dùng cho một directory test trên máy phát triển.
- Base DN và bind DN là dữ liệu **giả định**; phải cấu hình directory tương ứng trước.
- Mật khẩu **không có giá trị mặc định**: lập trình viên cấp bằng biến môi trường hoặc cơ chế secrets cục bộ.
- `ldap://` trong ví dụ chỉ phù hợp với thử nghiệm trên loopback có kiểm soát; không dùng mặc định này để truyền thông tin nhạy cảm qua mạng.

**File test — `application-test.yml`**

~~~yaml
spring:
  ldap:
    urls: ${LDAP_TEST_URL}
    base: ${LDAP_TEST_BASE_DN:dc=test,dc=example}
    username: ${LDAP_TEST_BIND_DN}
    password: ${LDAP_TEST_BIND_PASSWORD}
~~~

Test profile không có URL hoặc thông tin xác thực mặc định: bộ kiểm thử cấp chúng từ một LDAP instance riêng, thường là container chạy tạm thời hoặc test directory có dữ liệu fixture. Nếu thiếu các giá trị bắt buộc, cấu hình phải khiến quá trình khởi tạo test thất bại thay vì tự động kết nối một LDAP server khác.

**File prod — `application-prod.yml`**

~~~yaml
spring:
  ldap:
    urls: ${LDAP_PROD_URL}
    base: ${LDAP_PROD_BASE_DN}
    username: ${LDAP_PROD_BIND_DN}
    password: ${LDAP_PROD_BIND_PASSWORD}
~~~

Các giá trị prod được inject lúc khởi chạy, ví dụ qua secret manager hoặc cấu hình triển khai. Không thêm URL, bind DN hoặc mật khẩu production thực vào repository Git. Các ví dụ sử dụng tên biến môi trường riêng từng profile để tránh vô tình dùng chung endpoint; đây là quy ước của dự án, không phải tên biến bắt buộc do Spring đặt ra.

### Chọn profile khi chạy

Spring Boot nhận profile qua `spring.profiles.active`. Chẳng hạn:

~~~bash
# Chạy local; mật khẩu được cấp qua secret/env trước khi chạy.
SPRING_PROFILES_ACTIVE=dev java -jar app.jar
~~~

Hoặc cung cấp tham số:

~~~bash
java -jar app.jar --spring.profiles.active=prod
~~~

Khi chạy bằng Docker, Kubernetes, IDE hay CI, dùng cơ chế khai báo biến môi trường tương ứng. Trong production, hệ thống triển khai phải **chọn profile rõ ràng** và xác thực đầu vào; không phụ thuộc vào việc máy tình cờ có hay không có biến môi trường nào đó.

**Lưu ý về tên biến:** `SPRING_PROFILES_ACTIVE` là tên biến chuẩn mà Spring Boot ánh xạ sang `spring.profiles.active`. Những biến như `LDAP_PROD_URL` hoặc `LDAP_TEST_BIND_DN` là tên do ví dụ này tự chọn và được tham chiếu qua cú pháp `${...}` trong YAML.

## 4. Cách cấu hình được áp dụng lúc khởi động

~~~mermaid
flowchart TD
    A["Khởi chạy ứng dụng"] --> B["Xác định active profile"]
    B --> C["Nạp application.yml"]
    C --> D["Nạp application-{profile}.yml"]
    D --> E["Áp dụng biến môi trường và nguồn cấu hình có ưu tiên cao hơn"]
    E --> F["Spring Boot bind spring.ldap.*"]
    F --> G["Tạo ContextSource / LdapTemplate"]
    G --> H{"Kết nối và bind hợp lệ?"}
    H -->|Có| I["Repository, query và CRUD dùng directory tương ứng"]
    H -->|Không| J["Báo lỗi khởi tạo hoặc ở lần truy cập LDAP đầu tiên"]
~~~

Cần phân biệt **nạp cấu hình thành công** với **kết nối LDAP đã được xác minh**. Một số thành phần LDAP có thể kết nối lười (khi thực hiện thao tác đầu tiên), nên ứng dụng khởi động bình thường không chứng minh rằng DNS, port, chứng chỉ, mật khẩu và quyền truy cập đều đúng.

Cú pháp `${NAME}` trong file YAML yêu cầu Spring giải quyết biến/thuộc tính `NAME`; `${NAME:default}` cung cấp giá trị dự phòng. **Chỉ nên có default ở những giá trị dev không nhạy cảm và thực sự an toàn.** Nếu một biến bí mật hoặc URL prod không tồn tại, nên để hệ thống fail fast hoặc có bước validation bắt buộc.

Một số nguồn cấu hình có độ ưu tiên cao hơn file YAML (như tham số dòng lệnh hoặc biến môi trường), vì vậy cần kiểm soát cả quyền thay đổi biến chạy ứng dụng. Việc khóa file YAML nhưng để người vận hành tùy ý ghi đè `spring.ldap.urls` không đủ để ngăn kết nối sai nơi.

## 5. Giữ secret ngoài source code và build artifact

Tài khoản bind LDAP thường xuất hiện trong:

~~~yaml
spring:
  ldap:
    username: ${LDAP_PROD_BIND_DN}
    password: ${LDAP_PROD_BIND_PASSWORD}
~~~

Những giá trị cần bảo vệ gồm:

- **Mật khẩu bind**, token hoặc credential liên quan.
- **Khóa riêng TLS** và mật khẩu mở keystore/truststore nếu ứng dụng dùng.
- **Thông tin cá nhân trong entry**, log truy vấn và dữ liệu trả về khi gỡ lỗi.
- **Đường dẫn, quyền và chính sách** của directory trong phạm vi cần hạn chế.

Có thể cấp secret từ hệ thống quản lý bí mật hoặc cơ chế secret injection của nền tảng triển khai. Hạn chế truyền mật khẩu trực tiếp trên command line vì có thể xuất hiện trong lịch sử shell hoặc thông tin tiến trình. Phân quyền truy cập secret theo ứng dụng, môi trường và dịch vụ; tránh cấp mọi tài khoản CI quyền đọc secret prod.

### Ví dụ manifest triển khai dạng minh họa

Đây là phần biến môi trường cho container production; những giá trị bí mật được lấy từ Secret do nền tảng cấp trước:

~~~yaml
env:
  - name: SPRING_PROFILES_ACTIVE
    value: prod
  - name: LDAP_PROD_URL
    value: ldaps://directory.corp.example:636
  - name: LDAP_PROD_BASE_DN
    value: dc=corp,dc=example
  - name: LDAP_PROD_BIND_DN
    valueFrom:
      secretKeyRef:
        name: ldap-bind-credentials
        key: bind-dn
  - name: LDAP_PROD_BIND_PASSWORD
    valueFrom:
      secretKeyRef:
        name: ldap-bind-credentials
        key: password
~~~

Đoạn YAML này là **một phần `env` của Kubernetes container spec**, không phải manifest Deployment hoàn chỉnh. Tên miền và DN chỉ là ví dụ. Secret cần được tạo và phân quyền theo quy trình của nền tảng; không đưa đối tượng Secret chứa mật khẩu bản rõ vào Git.

Sau khi xoay vòng credential, cách ứng dụng nhận giá trị mới phụ thuộc cơ chế cấp secret và connection pool: giá trị inject qua biến môi trường thường đòi hỏi restart/rollout để tiến trình dùng credential mới. Phải có quy trình kiểm tra bind sau rotation.

## 6. Bảo vệ kết nối LDAP ở production

Bảo mật LDAP không thể chỉ là “mật khẩu nằm trong biến môi trường”. Một kết nối LDAP không mã hóa có thể làm lộ credential bind hoặc nội dung entry trên đường truyền.

| Nội dung | Dev | Test | Prod |
|---|---|---|---|
| Giao thức | `ldap://` trên loopback thử nghiệm hoặc TLS | Có bài kiểm thử cho TLS và chứng chỉ | Ưu tiên LDAPS hoặc StartTLS được cấu hình đúng |
| Xác minh server | Có thể dùng CA thử nghiệm riêng | Kiểm thử đúng và sai chứng chỉ | Xác minh chain và tên máy chủ |
| Credential | Tài khoản riêng cho local | Tài khoản riêng cho test | Service account đặc quyền tối thiểu |
| Giới hạn mạng | Không expose LDAP container ra Internet | Mạng test cô lập | Chỉ mở luồng từ ứng dụng tới directory |
| Ghi log | Có thể nhiều log hơn nhưng vẫn che dữ liệu nhạy cảm | Che thông tin fixture nếu cần | Không log mật khẩu, raw entry, secret |

**LDAPS:** URL bắt đầu bằng `ldaps://`, thường dùng cổng `636` và TLS từ đầu kết nối. Java cần tin cậy CA/chứng chỉ server thông qua truststore phù hợp và kiểm tra danh tính máy chủ. Không sửa lỗi chứng chỉ bằng cách bỏ qua xác minh TLS trong production.

**StartTLS:** kết nối ban đầu dùng `ldap://`, sau đó thực hiện thao tác nâng cấp TLS trước khi bind/truyền dữ liệu nhạy cảm. Việc chỉ điền URL `ldap://...` trong `spring.ldap.urls` **không tự động có nghĩa StartTLS đã được thực hiện**. Nếu chọn StartTLS, cấu hình `ContextSource`/JNDI cần hỗ trợ và bảo đảm thứ tự nâng cấp bảo mật; phải kiểm thử chống fallback về kết nối không mã hóa.

**Truststore:** có thể dùng CA được JVM tin cậy hoặc cấu hình truststore riêng của ứng dụng. Cần triển khai CA đúng cách, dự trù gia hạn chứng chỉ và không hardcode mật khẩu bảo vệ khóa trong repository. Tham số cấu hình TLS có thể khác nhau theo môi trường JVM và nhà cung cấp directory, nên hãy kiểm thử bắt tay TLS trên đúng runtime sẽ dùng ở prod.

**Đặc quyền tối thiểu:** nếu service chỉ tìm kiếm người dùng, tài khoản bind không cần quyền xóa hoặc di chuyển entry. Nếu service có CRUD, nên giới hạn thao tác vào một OU cụ thể và phân tách dịch vụ quản trị khỏi dịch vụ đọc nếu phù hợp kiến trúc.

## 7. Cấu hình base DN, schema và repository theo môi trường

Một trường hợp dễ gặp: dev dùng cây `dc=dev,dc=example`, prod dùng `dc=corp,dc=example`, nhưng cả hai có nhánh `ou=people`. Khi `spring.ldap.base` thay đổi, cùng repository có thể tiếp tục tìm kiếm trong nhánh tương đối `ou=people`.

~~~java
import java.util.List;
import org.springframework.data.ldap.repository.LdapRepository;

public interface DirectoryPersonRepository
        extends LdapRepository<DirectoryPerson> {

    List<DirectoryPerson> findByUid(String uid);
}
~~~

Ví dụ Spring LDAP dùng filter builder để an toàn với giá trị đầu vào:

~~~java
import java.util.List;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;

import static org.springframework.ldap.query.LdapQueryBuilder.query;

public class PersonLookupService {
    private final LdapTemplate ldapTemplate;

    public PersonLookupService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<String> findCommonNames(String userInput) {
        LdapQuery ldapQuery = query()
                .base("ou=people")
                .where("objectClass").is("inetOrgPerson")
                .and("uid").is(userInput);

        return ldapTemplate.search(
                ldapQuery,
                (AttributesMapper<String>) attrs ->
                        (String) attrs.get("cn").get()
        );
    }
}
~~~

Dùng API query/filter thay vì nối chuỗi filter từ dữ liệu người dùng để tránh LDAP injection. Khi dùng `@Entry(base = "ou=people")` hoặc `query().base("ou=people")`, hãy thống nhất **DN tương đối** với base cấu hình trong `ContextSource`; nếu tự thêm base DN lần nữa, truy vấn có thể đi đến vị trí sai hoặc không tồn tại.

**Không phải sự khác biệt nào cũng giải quyết bằng profile:**

- Nếu dev và prod dùng khác `objectClass`, thuộc tính bắt buộc hoặc naming rule, phải thiết kế mapping/schema phù hợp.
- Nếu một môi trường dùng `uid` làm RDN, môi trường khác dùng `cn`, thao tác tạo và đổi tên DN cần được xem xét riêng.
- Nếu `@Entry` hardcode `ou=people` nhưng prod dùng `ou=employees`, thay `spring.ldap.base` **không tự động thay `ou=people`**. Cần đồng nhất cây thư mục hoặc thiết kế cách chọn branch/config cho ứng dụng.
- Nếu tài khoản prod không đọc được `mail` hoặc `member` do ACL, repository có thể trả thiếu thuộc tính dù entry hợp lệ.

Tách cấu hình thành công đòi hỏi cả **hợp đồng mô hình dữ liệu LDAP** phù hợp giữa các môi trường, không chỉ tránh hardcode URL.

## 8. Kiểm thử: profile test phải thực sự tách biệt

Có ba cấp kiểm thử hữu ích:

| Loại kiểm thử | Kết nối LDAP thật? | Mục tiêu |
|---|---|---|
| Unit test cho service | Không bắt buộc; mock repository/`LdapTemplate` | Luồng nghiệp vụ, kiểm tra đầu vào, xử lý ngoại lệ |
| Integration test | Có, directory phục vụ test | Schema, DN, filter, bind, CRUD, repository và mapping |
| Pre-production smoke test | Có, directory staging/prod theo quyền và phạm vi đã duyệt | DNS, TLS, credential, base DN, quyền đọc và tính sẵn sàng |

**Integration test phải chạy với test profile** và một server có thể tạo dữ liệu fixture rồi xóa/đặt lại:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.test.context.ActiveProfiles;

import static org.junit.jupiter.api.Assertions.assertNotNull;

@SpringBootTest
@ActiveProfiles("test")
class DirectoryRepositoryIntegrationTest {

    @Autowired
    private LdapTemplate ldapTemplate;

    @Test
    void ldapTemplateIsConfigured() {
        assertNotNull(ldapTemplate);
    }
}
~~~

Kiểm tra trên **chỉ xác minh Spring context tạo được bean**, chưa chứng minh kết nối directory hay hành vi CRUD hoạt động. Một bài kiểm thử tích hợp có giá trị cần thực sự gọi LDAP, kiểm tra entry ở DN xác định và làm sạch dữ liệu thử nghiệm.

Với Testcontainers hoặc test directory nhúng, có thể cấp `LDAP_TEST_URL` theo host/port cấp động. Nếu dùng `@DynamicPropertySource`, đăng ký trực tiếp các khóa `spring.ldap.urls`, `spring.ldap.base`, `spring.ldap.username` và `spring.ldap.password` để test harness ghi đè cấu hình file khi context được khởi tạo. Dù dùng cơ chế nào, vẫn phải xác nhận **test không thể trỏ tới production**, kể cả khi biến môi trường trên máy CI bị cấu hình sai.

### Checklist cho integration test LDAP

1. Khởi tạo directory test riêng với đúng base DN và các OU cần thiết, ví dụ `ou=people`, `ou=groups`.
2. Nạp schema phù hợp: `inetOrgPerson`, `groupOfNames` hoặc object class tùy biến mà ứng dụng dùng.
3. Nạp fixture có DN, `objectClass`, `cn`, `sn`, `uid` nhất quán.
4. Kiểm tra repository/`LdapTemplate` tìm đúng entry và trả về giá trị ánh xạ như mong đợi.
5. Kiểm tra Create, Update, Delete, rename/move theo quyền và khả năng của server test.
6. Kiểm tra LDAP filter có ký tự đặc biệt, trường hợp thiếu thuộc tính bắt buộc và các kết quả lỗi từ server.
7. Dọn dữ liệu, dừng directory test và bảo đảm các lần chạy không dùng chung trạng thái.

Với trường hợp cần khẳng định TLS, phân quyền, chính sách mật khẩu hoặc schema đặc thù của Active Directory, directory nhúng đơn giản có thể không mô phỏng được. Hãy bổ sung test ở môi trường gần production với quyền và phạm vi phù hợp.

## 9. Quy trình triển khai từ CI tới production

Một luồng triển khai có thể được tổ chức như sau:

~~~mermaid
flowchart TD
    A["Build ứng dụng một lần"] --> B["Unit test"]
    B --> C["Integration test với LDAP riêng"]
    C --> D{"Pass?"}
    D -->|Không| E["Dừng pipeline và xem lỗi"]
    D -->|Có| F["Tạo artifact bất biến"]
    F --> G["Deploy staging với secret riêng"]
    G --> H["Kiểm tra TLS, bind, base DN, ACL"]
    H --> I{"Đạt điều kiện phát hành?"}
    I -->|Không| E
    I -->|Có| J["Deploy production cùng artifact"]
    J --> K["Read-only smoke test và giám sát"]
~~~

Để tránh “chạy được ở máy cá nhân nhưng lỗi ở production”, hãy kiểm tra từng bước:

**Trước khi đóng gói:** dependency Spring Data LDAP/Spring LDAP và phiên bản Spring Boot phù hợp, không commit `.env` chứa secret, không nhúng thông tin LDAP production trong image và không tạo test có khả năng xóa dữ liệu thật.

**Khi cấp cấu hình:** endpoint, port, base DN, bind DN, secret, truststore, chính sách TLS và OU phải được cấp từ đúng môi trường. Đảm bảo network policy cho phép service kết nối đúng directory.

**Khi startup:** ứng dụng nhận active profile mong muốn; biến cấu hình bắt buộc đã tồn tại; kiểm tra giá trị URL/hostname theo chính sách deployment. Nếu yêu cầu TLS, phát hiện và từ chối cấu hình `ldap://` chưa được nâng cấp StartTLS.

**Sau khi triển khai:** dùng phép đọc an toàn trên entry/nhánh kiểm tra đã thống nhất để xác nhận bind, quyền đọc và mapping; giám sát kết nối/timeout, lỗi `noSuchObject`, lỗi ACL, lỗi chứng chỉ. Chỉ chạy phép ghi khi có nhu cầu và phạm vi kiểm thử được cấp phép.

### Lệnh kiểm tra kết nối LDAP

Một ví dụ read-only dùng công cụ `ldapsearch` (giả sử server hỗ trợ bind đơn giản qua LDAPS, base entry tồn tại và quyền đọc cho phép):

~~~bash
ldapsearch -LLL -x \
  -H ldaps://directory.corp.example:636 \
  -D "uid=svc-app,ou=services,dc=corp,dc=example" \
  -W \
  -b "dc=corp,dc=example" \
  -s base "(objectClass=*)" dn
~~~

`-W` yêu cầu nhập mật khẩu tương tác, tránh đặt mật khẩu trong câu lệnh. CA phải được công cụ LDAP tin cậy. Đây là lệnh thao tác thủ công để chẩn đoán, không phải cách lưu mật khẩu cho ứng dụng. Một số directory chặn đọc root/base hoặc có cơ chế bind khác; cần điều chỉnh đối tượng kiểm tra cho đúng chính sách.

## 10. Timeout, tính sẵn sàng và giám sát

Phân tách profile không đủ nếu ứng dụng có thể treo vô hạn khi directory gặp sự cố. Khi đưa vào production, cần xác định:

- **Connect timeout**: giới hạn thời gian thiết lập kết nối mạng tới LDAP server.
- **Read/operation timeout**: giới hạn chờ phản hồi truy vấn hoặc thao tác.
- **Connection pooling**: lựa chọn chiến lược sử dụng lại kết nối và kiểm tra tương thích với TLS/StartTLS, chính sách xác thực và nhà cung cấp LDAP.
- **Retry có giới hạn**: chỉ retry lỗi tạm thời theo ngữ cảnh; không tự động lặp vô hạn lệnh Add/Delete/ModifyDN, vì thao tác có thể đã thành công dù client mất phản hồi.
- **Health/readiness**: ứng dụng có thể sống (liveness) nhưng chưa sẵn sàng (readiness) nếu không kết nối được directory phục vụ nghiệp vụ thiết yếu.
- **Quan sát lỗi**: đo tỉ lệ thất bại, timeout và thời gian truy vấn; che hoặc băm định danh nhạy cảm khi log.

Timeout với Spring LDAP thường được thiết lập thông qua thuộc tính JNDI/provider (ví dụ `com.sun.jndi.ldap.connect.timeout` và `com.sun.jndi.ldap.read.timeout`, giá trị tính bằng mili giây với JNDI LDAP provider thông dụng). **Không nên tự đặt các khóa Spring Boot tưởng tượng** như `spring.ldap.connect-timeout` nếu phiên bản đang dùng không định nghĩa; hãy cấu hình `ContextSource` theo API thực tế của thư viện hoặc cơ chế JNDI được hỗ trợ.

Chính sách timeout và retry của dev, test, prod có thể khác nhau, nhưng điểm chung là phải tránh trả lỗi trống và không làm lộ credential trong thông điệp lỗi/metrics. Nếu muốn health check ghi dữ liệu để thử quyền ghi, chỉ dùng entry kiểm thử riêng được cấp phép và dọn sạch sau đó.

## 11. Các tình huống lỗi cấu hình thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Dev chạy được, prod không connect | URL/port hoặc network policy khác nhau | DNS, kết nối TCP, firewall, endpoint |
| Prod lỗi bắt tay TLS | CA/truststore, chứng chỉ hết hạn hoặc hostname không khớp | Chuỗi chứng chỉ, tên DNS, cấu hình JVM TLS |
| Bind thất bại | Secret sai/hết hạn, DN bind sai, tài khoản bị khóa | Kiểm tra nguồn secret và trạng thái account |
| Query trả rỗng ở prod | Base DN, OU, filter, scope hoặc quyền đọc khác dev | Truy vấn đúng nhánh bằng tài khoản service |
| Create lỗi `objectClassViolation` | Schema hoặc các thuộc tính MUST khác | Đọc schema thực tế, kiểm tra `objectClass` và field |
| Một số thuộc tính không trả về | ACL che giá trị, schema hoặc mapping khác | Quyền đọc từng thuộc tính, `@Attribute` |
| Test truy cập sai directory | Profile hoặc biến môi trường bị ghi đè | In thông tin **không nhạy cảm** về active profile/host, kiểm tra cách cấp env |
| Thay mật khẩu nhưng app vẫn bind lỗi | Credential cũ đang dùng ở process/connection pool | Kiểm tra rollout, pool, secret injection và rotation |
| App start thành công nhưng request đầu lỗi | Kết nối LDAP chỉ diễn ra khi truy vấn đầu tiên | Read-only smoke test hoặc readiness check |
| `rename` thành công nhưng repository không thấy entry | DN đã chuyển khỏi base tìm kiếm hiện tại | Kiểm tra DN mới, `@Entry(base)` và search base |

### Những lỗi thiết kế cần tránh

**Gộp cả ba môi trường trong một file với điều kiện tự viết bằng Java.** Spring Boot profile và nguồn cấu hình đã có cơ chế quản lý thứ tự nạp. Chỉ tự viết logic chọn cấu hình nếu có yêu cầu nghiệp vụ rõ ràng, và cần kiểm tra chặt tính hợp lệ của dữ liệu đầu vào.

**Đặt mặc định production trong file dev hoặc ngược lại.** Khi thiếu env, ứng dụng có thể vô tình trỏ vào directory không mong muốn. URL/mật khẩu production nên bắt buộc phải cấp và được validation.

**Dùng dữ liệu người dùng thật trong test.** Test có các thao tác `save`, `delete` và `rename` phải dùng directory/fixture riêng; việc vô tình khởi chạy test bằng profile prod có thể phá hỏng dữ liệu.

**Tắt kiểm tra TLS để ứng dụng “chạy được”.** Đúng cách là cài CA/truststore và xác minh hostname; bypass chứng chỉ che giấu cấu hình sai và tạo nguy cơ bị giả mạo server.

**Cho rằng repository hoạt động giống nhau chỉ vì cùng Java entity.** Object class, attribute type, naming rule, ACL và dữ liệu của directory thực tế mới quyết định phép CRUD có thành công hay không.

## 12. Mẫu checklist phát hành

Dưới đây là checklist có thể dùng khi review một lần deploy:

| Hạng mục | Câu hỏi cần xác nhận |
|---|---|
| **Profile** | `SPRING_PROFILES_ACTIVE=prod` được cấp chính xác? |
| **Endpoint** | LDAP URL, port và DNS trỏ tới đúng hệ thống production? |
| **Base DN** | Base và các OU khớp với directory prod? |
| **Credential** | Secret đến từ nguồn quản lý bí mật, đúng quyền hạn và còn hiệu lực? |
| **TLS** | Kết nối đã được mã hóa và xác minh server bằng CA/hostname hợp lệ? |
| **Schema** | Các objectClass, attribute type và thuộc tính MUST/MAY ứng dụng dùng có sẵn? |
| **ACL** | Service account chỉ có các quyền đọc/ghi cần thiết? |
| **Test** | Integration test chạy với LDAP riêng, không truy cập prod? |
| **Network** | Firewall/network policy chỉ mở các luồng cần thiết? |
| **Observability** | Có đo lỗi/timeout, nhưng log không chứa secret hoặc toàn bộ thông tin cá nhân? |
| **Recovery** | Có phương án xử lý khi endpoint lỗi, secret rotation lỗi hoặc deployment cần rollback? |
| **Verification** | Đã chạy kiểm tra kết nối và phép đọc không phá dữ liệu sau deploy? |

Có thể chuyển checklist thành bước kiểm tra tự động trong CI/CD, nhưng không xuất secret hoặc DN chứa thông tin cá nhân ra build log.

## 13. Bài tập thực hành

**Bối cảnh:** một ứng dụng quản lý nhân viên đọc và cập nhật entry `inetOrgPerson` qua `LdapRepository`. Nhóm có một LDAP container trên laptop, một LDAP container riêng trên CI và một directory quản lý ở production.

Hãy thực hiện:

1. Tạo cấu trúc `application.yml`, `application-dev.yml`, `application-test.yml`, `application-prod.yml` tương ứng các ví dụ.
2. Cấu hình `@Entry(base = "ou=people")` và `spring.ldap.base` sao cho repository truy vấn đúng nhánh trong từng môi trường.
3. Chạy ứng dụng với `dev` và một LDAP container có dữ liệu giả; xác nhận đọc entry thành công.
4. Chạy integration test với `@ActiveProfiles("test")`, tạo entry thử nghiệm, tìm lại qua repository rồi xóa entry test.
5. Thử cố ý bỏ biến `LDAP_TEST_URL`: bảo đảm test thất bại rõ ràng, không tự chuyển sang dev hoặc prod.
6. Định nghĩa yêu cầu production: URL TLS, CA đáng tin cậy, service account ít quyền, secret injection, timeout và phép đọc smoke test.
7. Giả lập một trường hợp sai base DN và một trường hợp chứng chỉ không đáng tin cậy; ghi lại lỗi quan sát được và cách sửa bằng cấu hình phù hợp.

**Tiêu chí hoàn thành:** cùng một artifact ứng dụng chạy được với ba bộ cấu hình khác nhau; không có credential production trong code/repository; test thực sự dùng directory độc lập; các thao tác CRUD chỉ diễn ra ở nhánh được phép.

## 14. Tổng kết và tham khảo

Tách cấu hình dev, test và production giúp cùng một ứng dụng Spring Data LDAP kết nối đúng directory, sử dụng đúng base DN, bind account và chính sách TLS cho từng môi trường. Profile là cơ chế chọn bộ cấu hình, còn secret manager, ACL, network policy, kiểm thử tích hợp và quan sát vận hành là các lớp bảo vệ và xác minh bổ sung.

**Nhớ ba ý cốt lõi:**

- **Dev:** dùng dữ liệu giả, môi trường dễ đặt lại, không chứa secret production.
- **Test:** sử dụng LDAP độc lập, kiểm tra schema, filter, mapping, CRUD và điều kiện lỗi thực tế.
- **Prod:** cấp cấu hình/secret từ môi trường triển khai, kiểm tra TLS và quyền tối thiểu, giám sát kết nối và có quy trình khôi phục.

Tài liệu tham khảo để tra cứu chi tiết theo phiên bản đang sử dụng:

- [Spring Boot Reference — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html): nguồn cấu hình, placeholders và thứ tự ưu tiên.
- [Spring Boot Reference — Profiles](https://docs.spring.io/spring-boot/reference/features/profiles.html): kích hoạt profile và tài liệu cấu hình theo môi trường.
- [Spring Boot Reference — LDAP](https://docs.spring.io/spring-boot/reference/data/nosql.html#data.nosql.ldap): cấu hình LDAP qua Spring Boot.
- [Spring LDAP Reference](https://docs.spring.io/spring-ldap/reference/): `ContextSource`, `LdapTemplate`, DN và bảo mật kết nối.
- [Spring Data LDAP Reference](https://docs.spring.io/spring-data/ldap/reference/): mapping entity và repository LDAP.
- [RFC 4511 — Lightweight Directory Access Protocol](https://www.rfc-editor.org/rfc/rfc4511): các thao tác LDAP và ngữ nghĩa kết nối/trao đổi.
