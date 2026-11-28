# Tổ chức cấu hình theo môi trường và quản lý dữ liệu mẫu

Ứng dụng Spring Data LDAP thường chạy ở máy lập trình, môi trường integration test, staging và production. Mỗi môi trường có LDAP endpoint, base DN, Bind account, TLS trust, schema và dữ liệu khác nhau. Nếu các giá trị này nằm rải rác trong Java code hoặc dùng chung một file cấu hình, ứng dụng có thể kết nối nhầm directory, sử dụng sai quyền hoặc vô tình nạp dữ liệu demo vào production.

Spring Boot cung cấp **externalized configuration** và **profiles** để tách cấu hình theo môi trường. Spring LDAP sử dụng các thuộc tính như `spring.ldap.urls`, `spring.ldap.base`, `spring.ldap.username` và `spring.ldap.password` để tạo kết nối. Dữ liệu mẫu nên được quản lý riêng bằng LDIF hoặc fixture loader có giới hạn rõ ràng, có thể tái tạo trong directory phát triển/kiểm thử và không chứa dữ liệu cá nhân hay mật khẩu thật.

Bài thuộc chương **Khởi tạo** của mô-đun `SPRING_DATA_LDAP`. Ta sẽ xây cấu hình dùng chung, profile `local`/`test`/`prod`, bind properties có validation, đưa secret từ môi trường triển khai, chuẩn bị LDIF cho `inetOrgPerson` và `groupOfNames`, nạp fixture an toàn, xác minh dữ liệu và giữ production tách biệt.

> **Nguyên tắc:** profile chọn cấu hình; secret store cung cấp credential; LDAP server và ACL quyết định quyền thật; fixture chỉ được nạp vào directory đã xác định rõ là môi trường phát triển hoặc kiểm thử.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vì sao endpoint, base DN và Bind credential phải khác nhau theo môi trường.
2. Dùng `application.yml` và `application-{profile}.yml` để tổ chức cấu hình Spring Boot.
3. Kích hoạt profile qua `SPRING_PROFILES_ACTIVE` hoặc tham số chạy.
4. Hiểu thứ tự ưu tiên của các nguồn cấu hình và cách biến môi trường ghi đè YAML.
5. Cấu hình Spring LDAP qua `spring.ldap.*` mà không hardcode password.
6. Bind cấu hình nghiệp vụ bằng `@ConfigurationProperties` và kiểm tra giá trị bắt buộc.
7. Tách cấu hình local/test/prod và kiểm soát cờ nạp dữ liệu mẫu.
8. Tạo LDIF fixture có đúng DN, `objectClass`, thuộc tính bắt buộc và tham chiếu group.
9. Nạp dữ liệu mẫu bằng `ldapadd` hoặc fixture loader có kiểm soát.
10. Thiết kế seed có thể chạy lặp an toàn, không ghi đè entry không thuộc fixture.
11. Dọn dữ liệu test theo thứ tự và giới hạn subtree.
12. Kiểm thử bằng directory riêng, xác minh cấu hình TLS/ACL và tránh kết nối nhầm production.

## 2. Những gì thay đổi giữa các môi trường?

Giả sử cùng một ứng dụng danh bạ cần kết nối các directory sau:

| Thuộc tính | Local | Test | Production |
| --- | --- | --- | --- |
| LDAP URL | `ldap://localhost:1389` | URL của LDAP test container/service | `ldaps://ldap.corp.example:636` hoặc endpoint được phê duyệt |
| Base DN | `dc=example,dc=org` | Suffix riêng của test | Naming context thật của tổ chức |
| Bind DN | Tài khoản dev giới hạn | Tài khoản test | Service account do IAM quản lý |
| Password | Secret local không commit | Secret CI/test | Secret manager hoặc workload identity nếu được hỗ trợ |
| TLS trust | CA test riêng | CA của test service | CA nội bộ/chứng chỉ production được xác minh |
| Dữ liệu | Tài khoản giả, nhóm giả | Fixture tái tạo được | Dữ liệu thật, không seed demo |
| ACL | Quyền đủ cho bài thực hành | Quyền giới hạn cho test | Least privilege theo chức năng |
| Fixture seeding | Có thể bật có điều kiện | Bật trong bước setup test | **Luôn tắt** |

Không chỉ URL thay đổi. Nếu local dùng `groupOfNames` nhưng production dùng schema group riêng của Active Directory, code và fixture cần phản ánh khác biệt schema; không thể giải quyết bằng đổi mỗi hostname.

### Ba lớp cấu hình cần tách

- **Cấu hình kết nối:** URL, base DN, Bind DN, timeout, referral, TLS.
- **Cấu hình nghiệp vụ:** people base, groups base, policy tìm kiếm, giới hạn thao tác.
- **Dữ liệu mẫu:** entry test, nhóm test, quan hệ member và dữ liệu cần cleanup.

Không lưu dữ liệu mẫu như một phần của file cấu hình kết nối. Không để một cờ fixture có thể biến production thành môi trường demo.

## 3. Spring Boot profiles và externalized configuration

Spring Boot có thể nạp file cấu hình chung và file riêng cho profile đang hoạt động:

~~~text
src/main/resources/
├── application.yml
├── application-local.yml
├── application-test.yml
└── application-prod.yml
~~~

- `application.yml` chứa giá trị chung, timeout mặc định và placeholder lấy secret từ môi trường.
- `application-local.yml` ghi đè endpoint và base của directory local.
- `application-test.yml` trỏ tới LDAP test được tạo riêng cho integration test.
- `application-prod.yml` chỉ chứa tên biến secret/endpoint được cấp từ hạ tầng production.

Khi kích hoạt profile `local`, Spring Boot nạp cấu hình chung rồi áp dụng cấu hình profile tương ứng. Có thể kích hoạt bằng:

~~~bash
SPRING_PROFILES_ACTIVE=local
~~~

Hoặc:

~~~bash
java -jar learning-platform.jar --spring.profiles.active=local
~~~

Trong PowerShell:

~~~powershell
$env:SPRING_PROFILES_ACTIVE = "local"
java -jar .\learning-platform.jar
~~~

Deployment nên chọn profile theo môi trường triển khai. Không để một profile local tự trở thành mặc định trong artifact production.

### 3.1. Cấu hình chung

`src/main/resources/application.yml`:

~~~yaml
spring:
  application:
    name: ldap-learning-platform

  ldap:
    urls: "${LDAP_URLS}"
    base: "${LDAP_BASE}"
    username: "${LDAP_BIND_DN}"
    password: "${LDAP_BIND_PASSWORD}"
    base-environment:
      "[com.sun.jndi.ldap.connect.timeout]": "2000"
      "[com.sun.jndi.ldap.read.timeout]": "5000"

app:
  directory:
    people-base: "${DIRECTORY_PEOPLE_BASE:ou=people}"
    groups-base: "${DIRECTORY_GROUPS_BASE:ou=groups}"
    fixtures-enabled: false
    allow-fixture-reset: false
~~~

Các placeholder `LDAP_URLS`, `LDAP_BASE`, `LDAP_BIND_DN` và `LDAP_BIND_PASSWORD` được cấp từ môi trường triển khai. Ở profile local/test, file riêng có thể ghi đè giá trị kết nối chung. Nếu không có profile override và thiếu biến bắt buộc, ứng dụng nên fail khi khởi động thay vì tự kết nối một directory mặc định không rõ ràng.

`base-environment` là JNDI environment của Spring LDAP. Bracket notation giữ nguyên các dấu chấm trong key `com.sun.jndi.ldap.*` khi Spring Boot bind map.

### 3.2. Cấu hình local

`src/main/resources/application-local.yml`:

~~~yaml
spring:
  ldap:
    urls: ldap://localhost:1389
    base: dc=example,dc=org
    username: cn=svc-dev,ou=service,dc=example,dc=org
    password: "${LDAP_LOCAL_BIND_PASSWORD}"

app:
  directory:
    people-base: ou=people
    groups-base: ou=groups
    fixtures-enabled: true
    allow-fixture-reset: false
~~~

`LDAP_LOCAL_BIND_PASSWORD` phải được cấp qua secret local hoặc environment variable. Không đặt password thật trong YAML được commit. Dùng directory local dùng một lần với tài khoản test riêng; không tái sử dụng credential production trên máy cá nhân.

### 3.3. Cấu hình test

`src/test/resources/application-test.yml`:

~~~yaml
spring:
  ldap:
    urls: "${LDAP_TEST_URL}"
    base: "${LDAP_TEST_BASE:dc=example,dc=org}"
    username: "${LDAP_TEST_BIND_DN}"
    password: "${LDAP_TEST_BIND_PASSWORD}"

app:
  directory:
    people-base: ou=people
    groups-base: ou=groups
    fixtures-enabled: false
    allow-fixture-reset: false
~~~

Với test container có port ngẫu nhiên, cung cấp `spring.ldap.urls` qua `@DynamicPropertySource` thay vì hardcode port. Fixture nên được import trong bước setup test sau khi directory sẵn sàng. Tắt application seeder nếu test harness đã quản lý dữ liệu riêng.

### 3.4. Cấu hình production

`src/main/resources/application-prod.yml`:

~~~yaml
spring:
  ldap:
    urls: "${LDAP_PROD_URLS}"
    base: "${LDAP_PROD_BASE}"
    username: "${LDAP_PROD_BIND_DN}"
    password: "${LDAP_PROD_BIND_PASSWORD}"

app:
  directory:
    people-base: "${LDAP_PROD_PEOPLE_BASE}"
    groups-base: "${LDAP_PROD_GROUPS_BASE}"
    fixtures-enabled: false
    allow-fixture-reset: false
~~~

Production không được chứa fixture demo hoặc password mẫu. Nếu secret không được cấp, deployment nên fail fast. Không thêm default như `admin`/`password` để ứng dụng “vẫn chạy được”.

### 3.5. Multi-document YAML

Spring Boot cũng hỗ trợ nhiều document trong cùng file và kích hoạt document bằng `spring.config.activate.on-profile`:

~~~yaml
spring:
  ldap:
    urls: ldap://localhost:1389
---
spring:
  config:
    activate:
      on-profile: local
  ldap:
    base: dc=example,dc=org
~~~

Chọn một chiến lược dễ đọc. Các file `application-local.yml`/`application-test.yml`/`application-prod.yml` thường đơn giản khi mỗi môi trường có nhiều thuộc tính khác nhau. Không đặt `spring.profiles.active` hoặc `spring.profiles.include` trong một document chỉ được kích hoạt theo profile; thuộc tính điều khiển profile phải nằm ở nguồn cấu hình không phải profile-specific.

## 4. Thứ tự ưu tiên cấu hình và biến môi trường

Spring Boot có nhiều nguồn cấu hình. Ở mức thực hành:

- Tham số dòng lệnh như `--spring.ldap.base=...` có độ ưu tiên cao.
- Java system properties và OS environment variables có thể ghi đè Config Data.
- Cấu hình profile-specific ghi đè cấu hình chung.
- Giá trị mặc định trong code hoặc placeholder default có độ ưu tiên thấp hơn nguồn cấu hình thực tế.

Thứ tự đầy đủ còn có các nguồn khác như `SPRING_APPLICATION_JSON`, test properties, command-line args, JNDI và Config Data; hãy xem tài liệu Spring Boot đúng phiên bản để xác định chính xác.

Ví dụ:

~~~bash
export SPRING_PROFILES_ACTIVE=local
export LDAP_LOCAL_BIND_PASSWORD='secret-from-local-vault'
~~~

Với relaxed binding, property `spring.ldap.username` có thể được ánh xạ từ environment variable `SPRING_LDAP_USERNAME`. Các tên custom như `app.directory.people-base` có thể được cấp bằng `APP_DIRECTORY_PEOPLE_BASE`.

**Không in environment variables ra log** khi debug. Chúng có thể chứa credential hoặc secret khác ngoài LDAP.

### 4.1. Secret từ environment

Environment variable có thể dùng trong container/CI, nhưng cần lưu ý:

- Hạn chế quyền đọc environment của process.
- Không đưa giá trị vào log hoặc diagnostic dump.
- Không truyền password trong command line vì có thể xuất hiện trong process list/history.
- Không commit file `.env` có secret.
- Không dùng cùng một password giữa local, test và production.
- Xoay vòng credential và có quy trình cập nhật ứng dụng.

### 4.2. Secret từ mounted config tree

Spring Boot hỗ trợ config tree để nạp secret từ file được mount bởi runtime/secret manager:

~~~yaml
spring:
  config:
    import: "optional:configtree:/run/secrets/"
~~~

Trong config tree, tên file được ánh xạ thành property key và nội dung file thành giá trị. Ví dụ, file secret được mount với tên phù hợp cho property `spring.ldap.password` có thể cung cấp password mà không lưu nó trong YAML. Kiểm tra cách mount và tên file của nền tảng triển khai.

`optional:` chỉ có nghĩa import có thể vắng mặt; nếu password là bắt buộc, validation/placeholder vẫn phải khiến ứng dụng fail khi không có credential.

## 5. Bind cấu hình nghiệp vụ bằng ConfigurationProperties

Không nên rải `@Value` cho mọi thuộc tính ở nhiều service. Dùng `@ConfigurationProperties` để gom cấu hình directory của ứng dụng vào một kiểu có validation.

`DirectoryProperties.java`:

~~~java
package com.example.directory.config;

import jakarta.validation.constraints.NotBlank;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.directory")
public record DirectoryProperties(
        @NotBlank String peopleBase,
        @NotBlank String groupsBase,
        boolean fixturesEnabled,
        boolean allowFixtureReset) {
}
~~~

Đăng ký scan trong application:

~~~java
@SpringBootApplication
@ConfigurationPropertiesScan
public class DirectoryApplication {
    public static void main(String[] args) {
        SpringApplication.run(DirectoryApplication.class, args);
    }
}
~~~

Validation dùng `spring-boot-starter-validation` và Jakarta Validation tương ứng phiên bản Spring Boot. Nếu dự án không có validation starter, annotation `@NotBlank` không tự chạy.

### 5.1. Vì sao base DN là dữ liệu quan trọng?

`peopleBase` và `groupsBase` là DN tương đối với `ContextSource.base` trong ví dụ:

~~~text
ContextSource.base = dc=example,dc=org
peopleBase         = ou=people
groupsBase         = ou=groups
~~~

Khi ghép DN, ứng dụng phải giữ rõ quy ước relative/full DN. Không cấu hình `peopleBase` là DN đầy đủ rồi lại ghép với ContextSource base một lần nữa.

### 5.2. Không bind secret vào business properties

`DirectoryProperties` chỉ giữ các base và cờ fixture. Credential kết nối do Spring Boot LDAP auto-configuration quản lý qua `spring.ldap.*`. Điều này giảm nơi lưu trữ/hiển thị secret và tránh vô tình log toàn bộ business properties có chứa password.

Nếu ứng dụng tự tạo nhiều `LdapContextSource`, hãy dùng kiểu cấu hình riêng cho từng nguồn, áp dụng secret injection tương ứng và đặt `@Qualifier` rõ ràng cho từng template/repository.

## 6. Spring LDAP auto-configuration và ContextSource

Khi dùng Spring Boot starter phù hợp, Boot có thể tạo `ContextSource` và `LdapTemplate` dựa trên `spring.ldap.*` nếu ứng dụng chưa tự khai báo bean thay thế.

Ví dụ inject template:

~~~java
@Service
public class PersonDirectoryReader {

    private final LdapTemplate ldapTemplate;

    public PersonDirectoryReader(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    // Các thao tác search/lookup được triển khai ở service.
}
~~~

Không khai báo một `LdapContextSource` tùy chỉnh rồi giả định mọi thuộc tính auto-config sẽ tự áp dụng lên bean đó. Nếu tự tạo bean, chính cấu hình Java phải thiết lập URL, base, Bind DN, password, timeout, TLS và referral policy.

### 6.1. Khi nào cần nhiều ContextSource?

Ứng dụng có thể tách:
- `directoryReaderContextSource` cho Search/Lookup.
- `directoryWriterContextSource` cho Add/Modify/Delete.
- `directoryAuthContextSource` cho xác thực bằng danh tính người dùng.

Mỗi nguồn cần credential và ACL riêng. Đừng đổi `userDn`/`password` trên singleton theo từng HTTP request. Dùng `@Qualifier` cho từng `LdapTemplate` và cấu hình repository đúng template nếu có nhiều directory context.

### 6.2. TLS và trust

Với LDAPS hoặc StartTLS:
- Dùng endpoint TLS đã được phê duyệt.
- Xác minh certificate chain và hostname/SAN.
- Cấp truststore/CA qua cấu hình runtime phù hợp.
- Không tắt certificate validation để vượt lỗi kết nối.
- Không tự fallback từ LDAPS sang LDAP plaintext.
- Test certificate trong CI/staging tương tự production.

Profile chỉ chọn endpoint và trust configuration. Nó không làm kết nối tự an toàn.

## 7. Cấu trúc quản lý dữ liệu mẫu

Tách fixture khỏi cấu hình ứng dụng:

~~~text
src/
├── main/
│   └── resources/
│       └── application.yml
└── test/
    └── resources/
        ├── application-test.yml
        └── ldap/
            └── fixtures/
                ├── 00-people-and-groups-ou.ldif
                └── 10-sample-directory.ldif
~~~

Có thể đặt fixture phát triển trong thư mục riêng nếu nhóm muốn dùng chung, nhưng phải đánh dấu rõ đây là dữ liệu giả và chỉ nạp vào directory local/dev. Không đặt fixture có dữ liệu nhân viên thật trong source control.

### Quy tắc fixture

- Dùng UID, email, tên và DN giả có thể nhận biết.
- Không dùng dữ liệu production đã ẩn một phần nếu chưa có phê duyệt dữ liệu.
- Không lưu password thật trong LDIF.
- Có base DN rõ ràng, tách khỏi production naming context.
- Tạo parent entry trước child entry.
- Dùng objectClass/attribute đúng schema server.
- Định nghĩa rõ entry nào thuộc fixture để cleanup không xóa dữ liệu ngoài fixture.
- Version hóa fixture cùng code và review khi schema thay đổi.
- Không phụ thuộc thứ tự trả entry từ Search để xác định seed đã hoàn tất.

## 8. Tạo fixture LDIF cho OpenLDAP-style schema

Ví dụ dùng schema có `inetOrgPerson` và `groupOfNames`. Đây là fixture minh họa cho OpenLDAP hoặc directory có các schema tương ứng.

Hai file LDIF dưới đây giả định naming context `dc=example,dc=org` **đã được tạo khi khởi động LDAP test server**. Chúng chỉ tạo hai OU và các entry bên dưới; nếu test server chưa có suffix này, hãy provision suffix trước theo cách cấu hình của server. DN của `svc-fixture-loader` cũng phải được tạo và cấp ACL ngoài fixture người dùng, không tự giả định account đó đã tồn tại.

`00-people-and-groups-ou.ldif`:

~~~ldif
dn: ou=people,dc=example,dc=org
objectClass: top
objectClass: organizationalUnit
ou: people

dn: ou=groups,dc=example,dc=org
objectClass: top
objectClass: organizationalUnit
ou: groups
~~~

`10-sample-directory.ldif`:

~~~ldif
dn: uid=lan,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: lan
cn: Nguyen Thi Lan
sn: Nguyen
mail: lan@example.org
employeeNumber: TEST-1001

dn: uid=minh,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: minh
cn: Tran Quang Minh
sn: Tran
mail: minh@example.org
employeeNumber: TEST-1002

dn: cn=engineering,ou=groups,dc=example,dc=org
objectClass: top
objectClass: groupOfNames
cn: engineering
member: uid=lan,ou=people,dc=example,dc=org
member: uid=minh,ou=people,dc=example,dc=org
~~~

`inetOrgPerson` kế thừa các thuộc tính bắt buộc của `person` như `cn` và `sn`. `groupOfNames` yêu cầu ít nhất một `member` theo schema chuẩn; fixture group có hai DN người dùng đã tồn tại.

### 8.1. Không áp fixture này nguyên xi cho Active Directory

Active Directory dùng schema group riêng, phổ biến là `objectClass=group` và thuộc tính `member`. Không giả định AD mặc định chấp nhận entry `groupOfNames` giống OpenLDAP.

Fixture AD cần:
- DN theo naming context của AD.
- `objectClass` phù hợp schema AD.
- Thuộc tính bắt buộc theo loại group và policy domain.
- Tài khoản test có quyền tạo entry và sửa membership.
- Quy tắc về group scope/type nếu tạo group bằng AD schema.

Nếu cần hỗ trợ nhiều loại server, nên có bộ fixture riêng theo directory family và integration test tương ứng.

## 9. Nạp fixture bằng ldapadd

Trong directory local/test dùng một lần, có thể import LDIF bằng OpenLDAP command-line tools.

Ví dụ shell POSIX:

~~~bash
ldapadd -x -H ldap://localhost:1389 -D "cn=svc-fixture-loader,ou=service,dc=example,dc=org" -W -f src/test/resources/ldap/fixtures/00-people-and-groups-ou.ldif

ldapadd -x -H ldap://localhost:1389 -D "cn=svc-fixture-loader,ou=service,dc=example,dc=org" -W -f src/test/resources/ldap/fixtures/10-sample-directory.ldif
~~~

`-W` yêu cầu nhập password qua prompt. Không đưa password vào command line. Account fixture loader chỉ được cấp quyền trên base test, không dùng rootdn/domain admin production.

Trước khi import:
1. Khởi động đúng LDAP test instance.
2. Xác nhận endpoint và base DN.
3. Xác nhận schema hỗ trợ objectClass/attribute trong LDIF.
4. Xác nhận Bind DN có quyền Add trong nhánh test.
5. Import parent OU trước rồi mới import user/group.

`ldapadd` là Add operation. Chạy lại cùng fixture trên directory đã có entry thường trả `entryAlreadyExists`; nó không tự đồng bộ hoặc bỏ qua dữ liệu đã có.

### 9.1. Kiểm tra sau import

~~~bash
ldapsearch -LLL -x -H ldap://localhost:1389 -D "cn=svc-directory-reader,ou=service,dc=example,dc=org" -W -b "ou=people,dc=example,dc=org" "(objectClass=inetOrgPerson)" dn uid cn sn mail employeeNumber
~~~

Kiểm tra group:

~~~bash
ldapsearch -LLL -x -H ldap://localhost:1389 -D "cn=svc-directory-reader,ou=service,dc=example,dc=org" -W -b "cn=engineering,ou=groups,dc=example,dc=org" -s base "(objectClass=groupOfNames)" dn cn member
~~~

Đọc kết quả bằng đúng Bind DN mà ứng dụng sử dụng. Nếu fixture loader có quyền admin nhưng reader không đọc được thuộc tính, test sẽ không phản ánh hành vi thật của ứng dụng.

## 10. Nạp fixture bằng Spring LDAP trong local profile

Một lựa chọn khác là viết fixture loader nhỏ. Nó chỉ được kích hoạt ở profile local và khi cờ cấu hình bật.

`LocalDirectoryFixtureLoader.java`:

~~~java
package com.example.directory.fixture;

import javax.naming.Name;
import javax.naming.NamingException;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.BasicAttributes;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Profile;
import org.springframework.ldap.NameAlreadyBoundException;
import org.springframework.ldap.NameNotFoundException;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;
import org.springframework.stereotype.Component;

@Component
@Profile("local")
@ConditionalOnProperty(
    prefix = "app.directory",
    name = "fixtures-enabled",
    havingValue = "true"
)
public class LocalDirectoryFixtureLoader implements ApplicationRunner {

    private final LdapTemplate ldapTemplate;

    public LocalDirectoryFixtureLoader(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    @Override
    public void run(ApplicationArguments args) {
        ensureLanFixture();
    }

    private void ensureLanFixture() {
        Name dn = LdapNameBuilder.newInstance("ou=people")
                .add("uid", "lan")
                .build();

        try {
            Attributes existing = ldapTemplate.lookup(
                    dn, attrs -> attrs);
            verifyExistingFixture(existing);
            return;
        } catch (NameNotFoundException missing) {
            // Entry chưa tồn tại: có thể tạo fixture.
        }

        try {
            ldapTemplate.bind(dn, null, lanAttributes());
        } catch (NameAlreadyBoundException concurrentCreate) {
            Attributes actual = ldapTemplate.lookup(
                    dn, attrs -> attrs);
            verifyExistingFixture(actual);
        }
    }

    private static Attributes lanAttributes() {
        Attributes attrs = new BasicAttributes(true);
        Attribute objectClass = new BasicAttribute("objectClass");
        objectClass.add("top");
        objectClass.add("person");
        objectClass.add("organizationalPerson");
        objectClass.add("inetOrgPerson");

        attrs.put(objectClass);
        attrs.put("uid", "lan");
        attrs.put("cn", "Nguyen Thi Lan");
        attrs.put("sn", "Nguyen");
        attrs.put("mail", "lan@example.org");
        attrs.put("employeeNumber", "TEST-1001");
        return attrs;
    }

    private static void verifyExistingFixture(Attributes attrs) {
        try {
            String uid = (String) attrs.get("uid").get();
            String employeeNumber =
                    (String) attrs.get("employeeNumber").get();

            if (!"lan".equals(uid)
                    || !"TEST-1001".equals(employeeNumber)) {
                throw new IllegalStateException(
                        "Existing entry conflicts with local fixture");
            }
        } catch (NamingException ex) {
            throw new IllegalStateException(
                    "Cannot verify local fixture", ex);
        }
    }
}
~~~

Loader minh họa chỉ tạo một user. Trong ứng dụng thực tế, có thể tách mỗi fixture thành một phương thức hoặc dùng LDIF import để quản lý nhiều entry.

### 10.1. Tại sao loader không dùng rebind?

`rebind` có thể thay thế entry hiện có. Nếu fixture DN vô tình trùng với entry do developer tạo thủ công, seeder có thể ghi đè dữ liệu. Ví dụ dùng:
- Lookup trước.
- Nếu có entry, xác minh stable fixture marker như `employeeNumber=TEST-1001`.
- Nếu không có, Add bằng `bind`.
- Nếu gặp race `NameAlreadyBoundException`, đọc lại và xác minh.
- Nếu dữ liệu hiện có không khớp, dừng với conflict; không tự ghi đè.

### 10.2. Giới hạn của seeder

Đây là ví dụ phục vụ local, không phải hệ thống migration tổng quát:
- `@Profile("local")` là một lớp bảo vệ; cờ `fixtures-enabled` là lớp thứ hai.
- Chỉ dùng DN cố định trong OU local được phê duyệt.
- Không có method reset/xóa subtree.
- Không seed password hoặc account đặc quyền.
- Nếu có nhiều instance cùng khởi động, xử lý duplicate bằng read-after-add nhưng vẫn cần thiết kế concurrency phù hợp.
- Nếu fixture nhiều entry có quan hệ phụ thuộc, nạp theo thứ tự parent → user → group.
- Test nên dùng directory disposable và reset ở test harness, không dựa vào seeder ứng dụng.

## 11. Idempotency và vòng đời fixture

Fixture loader cần xác định hành vi khi chạy lần đầu và khi chạy lại.

| Trạng thái directory | Hành vi mong muốn |
| --- | --- |
| DN chưa tồn tại | Add fixture. |
| DN đã tồn tại và marker/identity khớp | Bỏ qua, coi fixture đã có. |
| DN đã tồn tại nhưng marker khác | Báo conflict, không ghi đè. |
| DN đã tồn tại nhưng thiếu attribute fixture | Báo mismatch hoặc chạy migration fixture có version riêng; không tự rebind. |
| Group fixture chưa tồn tại | Add sau khi các user member đã có. |
| Group đã tồn tại nhưng member khác | So sánh và báo conflict; không thay toàn bộ member âm thầm. |
| LDAP timeout sau Add | Trạng thái không chắc chắn; lookup cùng directory trước khi thử lại. |
| LDAP ACL từ chối | Dừng và sửa quyền fixture loader, không đổi sang admin toàn quyền. |

### 11.1. Fixture marker

Có thể dùng thuộc tính nghiệp vụ được schema cho phép để nhận biết entry test, ví dụ:
- `employeeNumber=TEST-1001`.
- `description=Managed test fixture`.
- Một custom attribute theo schema nội bộ.

Không tự thêm attribute không tồn tại trong schema. Marker không được dùng để cấp quyền hoặc phân biệt người dùng thật trong production.

### 11.2. Fixture không phải production migration

Fixture tạo dữ liệu phục vụ test; migration schema/production data là quy trình khác. Không đặt các bước Add user mẫu vào startup production để “đảm bảo dữ liệu ban đầu”. Với dữ liệu khởi tạo production, dùng quy trình provisioning có phê duyệt, audit, backup và idempotency riêng.

## 12. Dọn dữ liệu mẫu an toàn

Dữ liệu test cần được dọn trong phạm vi fixture. Với ví dụ group và users:

1. Xóa group fixture trước.
2. Xóa các user fixture sau.
3. Chỉ xóa OU fixture nếu chắc chắn OU không chứa dữ liệu khác.
4. Không xóa base naming context.
5. Không dùng recursive delete trên OU dùng chung.

Ví dụ:

~~~bash
ldapdelete -x -H ldap://localhost:1389 -D "cn=svc-fixture-loader,ou=service,dc=example,dc=org" -W "cn=engineering,ou=groups,dc=example,dc=org"

ldapdelete -x -H ldap://localhost:1389 -D "cn=svc-fixture-loader,ou=service,dc=example,dc=org" -W "uid=lan,ou=people,dc=example,dc=org"

ldapdelete -x -H ldap://localhost:1389 -D "cn=svc-fixture-loader,ou=service,dc=example,dc=org" -W "uid=minh,ou=people,dc=example,dc=org"
~~~

Các lệnh dùng DN fixture cụ thể. Không thêm `-r` để xóa đệ quy một subtree không kiểm soát.

### 12.1. Cleanup trong test

Mỗi test cần:
- Dùng UID/DN riêng hoặc reset directory trước test suite.
- Không chạy song song hai test cùng ghi một DN nếu không cô lập namespace.
- Cleanup trong `@AfterEach` hoặc test fixture manager.
- Nếu cleanup thất bại, fail test và báo rõ directory còn dữ liệu.
- Không swallow `NameNotFoundException` nếu nó làm test không còn xác minh được trạng thái mong muốn.

Với test container disposable, có thể hủy toàn bộ container sau test thay vì chạy hàng loạt Delete trên directory dùng chung. Đây thường là cách cô lập đơn giản hơn.

## 13. Kiểm thử cấu hình theo profile

Cấu hình theo môi trường cũng là một phần hành vi ứng dụng, cần được kiểm thử.

### 13.1. Kiểm tra profile và binding

~~~java
@SpringBootTest
@ActiveProfiles("test")
class DirectoryPropertiesTest {

    @Autowired
    DirectoryProperties properties;

    @Test
    void bindsDirectoryBasesFromTestConfiguration() {
        assertEquals("ou=people", properties.peopleBase());
        assertEquals("ou=groups", properties.groupsBase());
        assertFalse(properties.fixturesEnabled());
        assertFalse(properties.allowFixtureReset());
    }
}
~~~

Test giả định `application-test.yml` được nạp và có các property tương ứng. Không cần gọi LDAP server chỉ để kiểm tra bind configuration.

### 13.2. Test auto-configuration

Nếu ứng dụng dùng Boot auto-configuration, kiểm tra:
- `ContextSource` được tạo với đúng URL/base/Bind DN.
- `LdapTemplate` được tạo và dùng đúng source.
- Profile test không trỏ tới URL local/prod.
- Secret test được cấp từ environment/test properties.
- Timeout được bind vào JNDI environment đúng bean.

Không assert password bằng cách in nó ra log hoặc snapshot test. Có thể kiểm tra bean/environment trong test nội bộ nhưng không ghi giá trị secret vào output.

### 13.3. Test bằng DynamicPropertySource

Với LDAP test server có URL/port động:

~~~java
@SpringBootTest
@ActiveProfiles("test")
class DirectoryIntegrationTest {

    @DynamicPropertySource
    static void ldapProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.ldap.urls", TestDirectory::url);
        registry.add("spring.ldap.base", () -> "dc=example,dc=org");
        registry.add("spring.ldap.username", TestDirectory::bindDn);
        registry.add("spring.ldap.password", TestDirectory::password);
    }

    // TestDirectory là test harness của dự án:
    // khởi động directory disposable, nạp fixture và đóng sau suite.
}
~~~

`TestDirectory` là abstraction của test harness, không phải class có sẵn của Spring Boot. Có thể triển khai bằng Testcontainers hoặc embedded LDAP server. Mục tiêu là URL/credential được cấp từ server test thực tế thay vì port hardcode.

## 14. Profile không phải ranh giới bảo mật

`@Profile("local")` và `SPRING_PROFILES_ACTIVE` là cơ chế chọn bean/cấu hình. Chúng không ngăn một người có quyền sửa environment variables kích hoạt profile khác.

Các lớp bảo vệ cần có:
- Deployment pipeline kiểm soát profile được phép.
- Secret manager chỉ cấp secret đúng môi trường.
- Network policy giới hạn ứng dụng kết nối LDAP endpoint.
- LDAP ACL giới hạn Bind DN theo chức năng và subtree.
- Application authorization bảo vệ API.
- Production fixture seeder bị loại khỏi deployment hoặc bị tắt bằng policy.
- Alert khi production process cố kết nối localhost/test LDAP hoặc dùng test Bind DN.

Không dựa vào một dòng `fixtures-enabled: false` làm hàng rào duy nhất. Với dữ liệu nhạy cảm, nên không đóng gói seeder/fixture loader production vào artifact hoặc bảo đảm bean không được tạo ở profile production.

## 15. Bảo vệ secret và dữ liệu mẫu

### 15.1. Secret

Không commit:
- LDAP Bind password.
- Password người dùng mẫu.
- Private key, truststore password.
- Access token của secret manager.
- File dump directory thật.

Không đưa credential vào LDIF fixture, Docker image layer, Git history, CI log, exception message hoặc startup banner.

Dùng credential riêng cho local/test/staging/prod. Xoay vòng và thu hồi credential theo policy. Dùng LDAPS/StartTLS với xác minh certificate; không tắt TLS validation để xử lý lỗi trust.

### 15.2. Dữ liệu mẫu

Dữ liệu fixture nên:
- Là synthetic data, không phải bản sao production.
- Có tên/email/UID dễ nhận biết là test.
- Không mang quyền quản trị thật.
- Không dùng mật khẩu mặc định chung giữa các môi trường.
- Được giới hạn trong OU/base riêng.
- Được cleanup hoặc reset cùng lifecycle test environment.

Nếu cần test authentication, tạo password test bằng quy trình của test server và giữ nó trong secret test runtime; không đưa plaintext password vào LDIF commit.

## 16. Phân biệt cấu hình với dữ liệu directory

| Thành phần | Lưu ở đâu | Ví dụ |
| --- | --- | --- |
| LDAP URL | Environment/config | `ldaps://ldap.example.org:636` |
| Base DN | Environment/config | `dc=example,dc=org` |
| Bind DN | Secret/config được bảo vệ | `cn=svc-reader,ou=service,...` |
| Bind password | Secret manager/config tree | Giá trị bí mật runtime |
| People/group base | Business configuration | `ou=people`, `ou=groups` |
| Schema | LDAP server/schema management | `inetOrgPerson`, `groupOfNames` |
| Entry người dùng mẫu | LDIF/test fixture | `uid=lan,ou=people,...` |
| Membership mẫu | Group entry fixture | `member: uid=lan,...` |
| Trạng thái đã seed | Fixture journal/version nếu cần | Version fixture hoặc marker |
| Quyền đọc/ghi | LDAP ACL + application authorization | Reader/writer Bind DN và API authority |

Đừng lưu danh sách user/group mẫu trong `application.yml` rồi coi đó là directory database. YAML cấu hình kết nối; LDAP server mới lưu entry và quan hệ.

## 17. Xử lý khác biệt schema giữa các directory

Cùng một bài thực hành có thể dùng OpenLDAP local và Active Directory production. Cần có fixture/mapping phù hợp:

| Khái niệm | OpenLDAP-style fixture | Active Directory |
| --- | --- | --- |
| Person | `inetOrgPerson` | `user` cùng schema AD |
| Group | `groupOfNames` | `group` |
| Membership | `member` chứa DN | `member` chứa DN |
| Username/login | `uid` thường dùng | Có thể dùng `sAMAccountName`/UPN |
| DN suffix | `dc=example,dc=org` | Domain naming context thực tế |
| Group constraints | `groupOfNames` yêu cầu member | Group type/scope và schema AD |
| Password | `userPassword` theo schema/server | Quy tắc riêng của AD, thường dùng password operation phù hợp |
| Membership visibility | ACL/schema/overlay | ACL, nested group và thuộc tính linked |

Đừng viết code nghiệp vụ phụ thuộc trực tiếp vào một thuộc tính chỉ có ở một server mà không có adapter. Ví dụ, đăng nhập theo `uid` không thể mặc định dùng cho AD nếu directory thực tế định danh user bằng `sAMAccountName` hoặc UPN.

### 17.1. Cấu hình naming attribute

Có thể cấu hình tên thuộc tính đăng nhập theo environment:

~~~yaml
app:
  directory:
    username-attribute: uid
~~~

Trong AD profile:

~~~yaml
app:
  directory:
    username-attribute: sAMAccountName
~~~

Filter phải được xây bằng API escape filter an toàn; không nối raw username vào LDAP filter string. Tên attribute là cấu hình tin cậy được validate/allowlist, còn giá trị người dùng nhập phải được escape.

## 18. Lỗi thường gặp

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Hardcode LDAP URL trong Java | Không chuyển môi trường an toàn. | Externalized configuration. |
| Commit Bind password trong YAML | Lộ credential qua Git/history. | Environment/secret manager/config tree. |
| Dùng cùng credential local và prod | Rủi ro lan giữa môi trường. | Credential riêng, least privilege. |
| Cho local profile mặc định khi deploy | Có thể kết nối nhầm directory. | Deployment chọn profile rõ ràng. |
| Nghĩ profile là security boundary | Có thể đổi profile qua environment. | Network policy, secret policy và LDAP ACL. |
| Dùng fixture production data | Rò rỉ thông tin cá nhân. | Synthetic data. |
| Dùng ldapadd lặp lại và mong tự bỏ qua | Duplicate DN làm import thất bại. | Reset disposable server hoặc loader có reconciliation. |
| Dùng rebind cho seeding | Ghi đè entry hiện có. | Bind + verify stable marker; conflict thì dừng. |
| Import child trước parent | Add thất bại vì parent chưa tồn tại. | Nạp LDIF theo thứ tự cây. |
| Dùng groupOfNames trên AD mặc định | Schema không phù hợp. | Fixture/schema theo directory family. |
| Bật seeder bằng một cờ duy nhất | Có thể nạp fixture nhầm môi trường. | Profile local + condition + deployment guard. |
| Dùng recursive delete để cleanup base dùng chung | Xóa dữ liệu ngoài test. | Cleanup DN fixture cụ thể hoặc hủy test container. |
| Bỏ qua ACL reader khi test | App production không đọc được dữ liệu. | Test bằng đúng Bind DN và ACL ứng dụng. |
| Lưu password mẫu trong LDIF | Secret bị commit. | Provision credential riêng ở runtime. |
| Test dùng chung DN khi chạy song song | Test tranh chấp và không ổn định. | Namespace riêng hoặc directory disposable. |
| Dùng một fixture cho mọi LDAP server | Khác biệt schema gây lỗi. | Fixture riêng theo directory family. |

## 19. Bài tập thực hành

**Bài 1 — Tách profile.** Tạo `application.yml` và ba file `application-local.yml`, `application-test.yml`, `application-prod.yml`. Kích hoạt từng profile và xác minh URL/base/Bind DN được chọn đúng. Không in password ra console.

**Bài 2 — External secret.** Cấp `LDAP_LOCAL_BIND_PASSWORD` từ environment hoặc secret store. Thử khởi động khi thiếu secret và xác minh ứng dụng fail fast thay vì kết nối anonymous ngoài ý muốn.

**Bài 3 — ConfigurationProperties.** Tạo `DirectoryProperties` với `@NotBlank` cho people/group base. Viết test xác minh cấu hình thiếu bị báo lỗi lúc startup.

**Bài 4 — Nạp LDIF.** Tạo OU people/groups, hai `inetOrgPerson` và một `groupOfNames`. Import theo thứ tự, sau đó Search và xác minh member DN.

**Bài 5 — Seeder an toàn.** Viết loader chỉ chạy ở local và khi `fixtures-enabled=true`. Chạy hai lần; lần hai không tạo duplicate, dữ liệu không khớp marker phải báo conflict và không rebind.

**Bài 6 — Cleanup.** Viết cleanup xóa group fixture rồi xóa user fixture. Xác minh không xóa OU hoặc entry ngoài fixture.

**Bài 7 — Test directory động.** Khởi động LDAP disposable với port động, cấp URL qua `@DynamicPropertySource` và nạp LDIF trong test setup. Không phụ thuộc LDAP server dùng chung của developer.

**Bài 8 — Schema khác nhau.** So sánh fixture `groupOfNames` của OpenLDAP với `group` của AD. Viết adapter/fixture riêng và xác minh mapping repository đúng.

**Bài 9 — ACL.** Tạo reader và fixture loader account. Reader chỉ đọc, loader được Add trong OU test. Xác minh không dùng admin toàn quyền cho ứng dụng.

**Bài 10 — Production guard.** Viết test/context assertion chứng minh profile prod không tạo fixture loader và `fixtures-enabled` luôn false. Kiểm tra deployment policy không cho profile local trong production.

## 20. Câu hỏi tự đánh giá

1. Vì sao cần tách LDAP URL, base DN và Bind credential theo môi trường?
2. `application.yml` và `application-local.yml` được Spring Boot nạp như thế nào?
3. Làm thế nào kích hoạt profile bằng environment variable?
4. OS environment variable có thể ghi đè giá trị YAML không?
5. Vì sao không nên đặt password thật trong `application-prod.yml`?
6. `spring.ldap.username` khác `app.directory.people-base` ở vai trò nào?
7. `@ConfigurationProperties` có lợi ích gì so với rải nhiều `@Value`?
8. Vì sao `@NotBlank` cần validation starter tương ứng?
9. Vì sao profile không phải ranh giới bảo mật?
10. LDIF fixture cần tạo parent OU trước hay sau user/group?
11. `inetOrgPerson` yêu cầu các thuộc tính nào được kế thừa từ `person`?
12. Vì sao `groupOfNames` cần ít nhất một `member` theo schema?
13. Tại sao không áp fixture OpenLDAP nguyên xi cho AD?
14. `ldapadd` có tự idempotent khi chạy lại không?
15. Vì sao seeder nên dùng Bind và verify thay vì rebind?
16. Khi DN đã tồn tại nhưng fixture marker khác, nên làm gì?
17. Vì sao fixture loader phải bị giới hạn trong local/test?
18. Cleanup group trước hay user trước, và vì sao?
19. Làm thế nào cấp port LDAP test động cho Spring Boot?
20. Vì sao integration test cần dùng đúng Bind DN/ACL của ứng dụng?
21. Có nên lưu password người dùng mẫu trong LDIF không?
22. Nếu production thiếu secret, ứng dụng nên fail fast hay dùng default demo?
23. Vì sao cần fixture riêng theo schema/capability của directory?
24. Cần những hàng rào nào ngoài `fixtures-enabled=false` để bảo vệ production?

**Ghi nhớ:** cấu hình kết nối phải được externalize và chọn theo profile; credential phải đến từ secret runtime; dữ liệu mẫu phải được quản lý riêng, synthetic, có schema phù hợp và có cleanup giới hạn. Seeder chỉ chạy trong local/test có kiểm soát, dùng Add + verify để tránh ghi đè; production không nạp fixture demo. Profile không thay thế LDAP ACL, TLS, network policy hoặc secret management.

### Tài liệu tham khảo

- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html): property sources, precedence, environment variables và Config Data.
- [Spring Boot — Profiles](https://docs.spring.io/spring-boot/reference/features/profiles.html): profile-specific files, activation và profile groups.
- [Spring Boot — Type-safe Configuration Properties](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties): `@ConfigurationProperties`, binding và validation.
- [Spring Boot — LDAP](https://docs.spring.io/spring-boot/reference/data/nosql.html#data.nosql.ldap): LDAP auto-configuration và thuộc tính `spring.ldap.*`.
- [Spring LDAP — Basic Usage](https://docs.spring.io/spring-ldap/reference/spring-ldap-basic-usage.html): ContextSource, LdapTemplate, Bind và thao tác entry.
- [Spring LDAP — Testing](https://docs.spring.io/spring-ldap/reference/testing.html): test support và embedded LDAP.
- [Spring LDAP — LdapTestUtils API](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/test/LdapTestUtils.html): tiện ích setup/cleanup dữ liệu test nếu có trong phiên bản sử dụng.
- [RFC 2849 — The LDAP Data Interchange Format (LDIF)](https://www.rfc-editor.org/rfc/rfc2849): định dạng LDIF và change records.
- [RFC 4512 — LDAP Directory Information Models](https://www.rfc-editor.org/rfc/rfc4512): directory entry, DN, attribute và schema.
- [RFC 4519 — LDAP Schema for User Applications](https://www.rfc-editor.org/rfc/rfc4519): person, groupOfNames và các thuộc tính schema liên quan.
- [OpenLDAP Administrator's Guide](https://www.openldap.org/doc/admin26/): schema, LDIF, ACL và quản trị directory.
- [Microsoft Learn — Active Directory Schema](https://learn.microsoft.com/en-us/windows/win32/adschema/active-directory-schema): schema và thuộc tính dành riêng cho Active Directory.
