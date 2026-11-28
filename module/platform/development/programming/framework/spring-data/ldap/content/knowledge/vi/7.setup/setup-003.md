# Khởi tạo máy chủ LDAP phát triển bằng container

Khi học **Spring Data LDAP**, chỉ đọc ví dụ Java là chưa đủ: các thao tác Bind, Search, CRUD, ánh xạ `@Entry` và kiểm tra `objectClass` cần một directory thực để xác minh. Ta có thể chạy một **OpenLDAP server trong Docker container**, chuẩn bị entry bằng LDIF và kết nối ứng dụng Spring Boot tới nó. Môi trường này giúp làm bài lab lặp lại được mà không phải chỉnh cấu hình LDAP hệ thống.

Bài học thuộc chương **Khởi tạo** của mô-đun `SPRING_DATA_LDAP`. Kết quả mong muốn là một máy chủ LDAP phát triển có DN gốc xác định, dữ liệu người dùng và nhóm, tài khoản thử nghiệm để Search, cùng cấu hình Spring Data LDAP để truy vấn các entry phân cấp.

> **Phạm vi:** cấu hình bên dưới chỉ phục vụ phát triển trên máy cá nhân. Nó cố ý công bố cổng LDAP qua `127.0.0.1` và tắt TLS để đơn giản hóa những bước đầu. **Không dùng nguyên cấu hình này cho môi trường chia sẻ hoặc production.** Phần cuối trình bày các yêu cầu khi chuyển sang LDAPS/StartTLS, ACL và quản lý secret.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích directory LDAP khác cơ sở dữ liệu quan hệ thế nào: entry, DN, RDN, `objectClass` và schema.
2. Tạo và khởi động một container OpenLDAP bằng Docker Compose, ánh xạ port localhost và lưu dữ liệu qua volume.
3. Nạp LDIF mẫu để có `ou=people`, `ou=groups` và hai entry `inetOrgPerson`.
4. Dùng `ldapwhoami` và `ldapsearch` kiểm tra Bind, Search, search base, scope và filter.
5. Cấu hình `spring.ldap.*`, tạo entity/repository hoặc dùng `LdapTemplate` để đọc entry.
6. Chẩn đoán lỗi phổ biến như sai Base DN, sai mật khẩu, thiếu schema, trùng entry hoặc thiếu quyền.
7. Phân biệt việc dừng container, xóa container và xóa dữ liệu volume; biết các bước tăng cường an toàn kết nối.

## 2. Sơ đồ môi trường

~~~mermaid
flowchart LR
    A["Spring Boot chạy trên máy phát triển"] -->|"ldap://localhost:1389"| B["Docker: host port 1389"]
    B -->|"container port 389"| C["Container OpenLDAP"]
    C --> D["DIT: dc=example,dc=org"]
    D --> E["ou=people"]
    D --> F["ou=groups"]
    C --> G["Docker volumes: dữ liệu + cấu hình"]
    H["ldapadd / ldapsearch"] --> C
~~~

| Thành phần | Vai trò trong bài lab |
| --- | --- |
| OpenLDAP server | Lưu entry, kiểm tra schema, tiếp nhận Bind/Search/Modify. |
| Docker Compose | Khai báo container, môi trường, cổng và volume. |
| Docker volume | Giữ database/config LDAP sau khi container khởi động lại. |
| LDIF | Mô tả entry cần nạp vào directory. |
| `ldapadd` / `ldapsearch` / `ldapwhoami` | Kiểm tra dữ liệu và xác thực trực tiếp, độc lập với ứng dụng Java. |
| Spring Data LDAP | Ánh xạ entry sang Java, truy vấn qua repository/`LdapTemplate`. |

**Phân biệt host và container:** nếu Spring Boot chạy **trên máy host**, kết nối qua `ldap://localhost:1389`. Nếu Spring Boot là **một service trong cùng Compose network**, nó gọi `ldap://ldap:389`, với `ldap` là tên service Docker; `localhost` bên trong app container là chính app container.

## 3. Chuẩn bị công cụ

Cần có:

- Docker Engine hoặc Docker Desktop đang chạy, kèm Docker Compose plugin (lệnh `docker compose`).
- Terminal hỗ trợ các lệnh Docker; trên Windows có thể dùng PowerShell hoặc terminal trong IDE.
- JDK tương thích với Spring Boot đang học (ví dụ Java 17 trở lên với Spring Boot 3), Maven hoặc Gradle để thử ứng dụng Java.
- Một cổng TCP **1389** rảnh trên host. Cổng bên trong container là **389**.

Kiểm tra công cụ:

~~~bash
docker --version
docker compose version
docker info
~~~

Lệnh `docker info` sẽ báo lỗi nếu Docker daemon chưa hoạt động hoặc phiên người dùng không có quyền truy cập Docker. Xử lý lỗi Docker trước khi thử LDAP, vì LDAP container chưa thể khởi động nếu runtime không chạy.

### Chọn image cho bài lab

Ví dụ dùng `osixia/openldap:1.5.0`, một image OpenLDAP có sẵn cơ chế cấu hình domain, mật khẩu quản trị và tài khoản đọc đơn giản. **Đây là phiên bản ví dụ dùng trong lab, không phải đề xuất image được duy trì hoặc an toàn cho production năm hiện tại.** Khi đưa vào hệ thống thật, cần kiểm tra tình trạng duy trì của image, CVE, chính sách cập nhật, hỗ trợ TLS và quy trình quản trị.

Image được ghi **tag cố định** để cấu hình và tài liệu có cùng điểm xuất phát. Để tái tạo tuyệt đối giữa các máy, dự án có thể pin image bằng digest sau khi chọn và kiểm tra bản phát hành phù hợp.

## 4. Tạo cấu trúc thư mục lab

Tạo các file theo cấu trúc sau trong một thư mục làm việc riêng:

~~~text
ldap-lab/
├── compose.yaml
├── .env
└── ldif/
    └── people.ldif
~~~

`compose.yaml` khai báo máy chủ và volume. `.env` chỉ chứa secret dành cho Compose trên máy thử nghiệm; không commit file này lên Git. `people.ldif` chứa dữ liệu mẫu không nhạy cảm.

Trong `.gitignore` của dự án lab, nên thêm:

~~~gitignore
.env
.env.*
!.env.example
~~~

Có thể đặt tên file mẫu `.env.example` (chỉ chứa tên biến và placeholder) trong tài liệu hướng dẫn chia sẻ. **Không đưa mật khẩu LDAP thật vào ví dụ, test fixture hoặc commit.**

## 5. Viết Docker Compose cho OpenLDAP

Nội dung `compose.yaml`:

~~~yaml
services:
  ldap:
    image: osixia/openldap:1.5.0
    environment:
      LDAP_ORGANISATION: "Example Organization"
      LDAP_DOMAIN: "example.org"
      LDAP_ADMIN_PASSWORD: "${LDAP_ADMIN_PASSWORD:?Set LDAP_ADMIN_PASSWORD}"
      LDAP_READONLY_USER: "true"
      LDAP_READONLY_USER_USERNAME: "readonly"
      LDAP_READONLY_USER_PASSWORD: "${LDAP_READONLY_USER_PASSWORD:?Set LDAP_READONLY_USER_PASSWORD}"
      LDAP_TLS: "false" # Chỉ dành cho lab localhost
    ports:
      - "127.0.0.1:1389:389"
    volumes:
      - ldap_data:/var/lib/ldap
      - ldap_config:/etc/ldap/slapd.d
      - ./ldif/people.ldif:/work/people.ldif:ro

volumes:
  ldap_data:
  ldap_config:
~~~

Giải thích các dòng quan trọng:

| Cấu hình | Ý nghĩa |
| --- | --- |
| `LDAP_DOMAIN: "example.org"` | Tạo naming context `dc=example,dc=org` khi khởi tạo volume mới. |
| `LDAP_ADMIN_PASSWORD` | Mật khẩu tài khoản quản trị được tạo cho domain. |
| `LDAP_READONLY_USER: "true"` | Yêu cầu image tạo tài khoản đọc phục vụ tìm kiếm theo cấu hình image. |
| `LDAP_READONLY_USER_USERNAME` | Tên tài khoản đọc ở ví dụ là `readonly`. |
| `LDAP_TLS: "false"` | Tắt TLS chỉ để học LDAP qua loopback trong bước đầu. |
| `127.0.0.1:1389:389` | Chỉ publish container port 389 ra IPv4 loopback port 1389 của host. |
| `ldap_data` | Giữ dữ liệu entry. |
| `ldap_config` | Giữ cấu hình OpenLDAP, trong đó có schema/ACL. |
| `people.ldif:/work/people.ldif:ro` | Mount fixture ở chế độ chỉ đọc vào container để chạy `ldapadd` thủ công. |

Với image ví dụ, DN quản trị là `cn=admin,dc=example,dc=org`; tài khoản đọc được cấu hình với tên `readonly` thường có DN `cn=readonly,dc=example,dc=org`. **Hãy xác minh Bind thực tế bằng `ldapwhoami` ở mục kiểm tra**, vì các image khác nhau có thể tạo tài khoản và ACL khác nhau.

**Lưu ý khởi tạo một lần:** nhiều biến môi trường của image có hiệu lực khi **volume LDAP còn trống**. Nếu đổi `LDAP_DOMAIN` hoặc mật khẩu rồi chỉ chạy lại container với volume cũ, dữ liệu/config đã tồn tại có thể giữ nguyên. Đừng suy luận container khởi động lại sẽ tự di chuyển DN hoặc thay đổi mật khẩu trong database.

### File .env cho Compose

Tạo `.env` cùng thư mục `compose.yaml`:

~~~dotenv
LDAP_ADMIN_PASSWORD=replace-with-strong-local-admin-password
LDAP_READONLY_USER_PASSWORD=replace-with-strong-local-read-password
~~~

Từng dòng phải có giá trị thực dành riêng cho máy lab. Compose thay biến `${LDAP_ADMIN_PASSWORD:?Set LDAP_ADMIN_PASSWORD}` và `${LDAP_READONLY_USER_PASSWORD:?Set LDAP_READONLY_USER_PASSWORD}` trong `compose.yaml` bằng giá trị lấy từ môi trường hoặc file `.env`. Nếu thiếu biến, Compose dừng sớm bằng thông báo yêu cầu cấu hình.

**Cần phân biệt:** file `.env` của Docker Compose **không tự động trở thành biến môi trường của tiến trình Spring Boot chạy trực tiếp trong IDE**. Muốn Spring Boot dùng mật khẩu đó, bạn phải thiết lập biến tương ứng trong cấu hình Run/Debug hoặc shell khởi động Java. Đừng giả định một công cụ khác tự nạp file Compose.

## 6. Đưa dữ liệu thử nghiệm vào LDIF

Trước khi khởi động Compose, ghi `ldif/people.ldif`:

~~~ldif
dn: ou=people,dc=example,dc=org
objectClass: top
objectClass: organizationalUnit
ou: people

dn: ou=groups,dc=example,dc=org
objectClass: top
objectClass: organizationalUnit
ou: groups

dn: uid=lan,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: lan
cn: Nguyen Thi Lan
sn: Nguyen
givenName: Lan
mail: lan@example.org
title: Backend Developer

dn: uid=minh,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: minh
cn: Tran Van Minh
sn: Tran
givenName: Minh
mail: minh@example.org
title: QA Engineer

dn: cn=engineering,ou=groups,dc=example,dc=org
objectClass: top
objectClass: groupOfNames
cn: engineering
member: uid=lan,ou=people,dc=example,dc=org
member: uid=minh,ou=people,dc=example,dc=org
~~~

### Cách đọc LDIF

Một đoạn `dn: ...` mở đầu **entry**. Các dòng `objectClass` chỉ định cấu trúc. Mỗi entry trong ví dụ nằm dưới naming context `dc=example,dc=org`, nhưng `ou=people`/`ou=groups` phải tồn tại trước khi thêm các entry con.

- `person` là structural object class yêu cầu `cn` và `sn`.
- `organizationalPerson` kế thừa `person`, bổ sung thuộc tính tổ chức.
- `inetOrgPerson` kế thừa `organizationalPerson`, thường dùng cho người dùng có `uid`, `mail`, `givenName`.
- `groupOfNames` là structural class cho nhóm, yêu cầu `cn` và ít nhất một `member`; `member` chứa **DN của entry thành viên**.
- `uid=lan` là **RDN**; `uid=lan,ou=people,dc=example,dc=org` là **DN đầy đủ**.

Các entry `uid=lan` và `uid=minh` được tạo để **tìm kiếm danh bạ**, chưa chứa `userPassword` để làm bài tập xác thực người dùng. Không suy ra một entry `inetOrgPerson` mặc định có thể đăng nhập. Nếu muốn thực hành Bind bằng tài khoản người dùng, cần thiết kế riêng việc thiết lập mật khẩu, chính sách password và kênh TLS; ở bài này Bind sử dụng tài khoản dịch vụ hoặc admin của lab.

**Lưu ý về schema:** schema của OpenLDAP phải có `inetOrgPerson`, `organizationalUnit` và `groupOfNames`. Image minh họa thường cung cấp schema tương ứng. Nếu server khác báo `objectClassViolation`, hãy kiểm tra schema thay vì thêm thuộc tính ngẫu nhiên.

## 7. Khởi động container và kiểm tra kết nối

Từ thư mục chứa `compose.yaml`, chạy:

~~~bash
docker compose up -d
docker compose ps
docker compose logs --tail=80 ldap
~~~

Lần đầu Docker có thể cần kéo image về máy. Đợi dịch vụ khởi tạo xong trước khi gọi LDAP; trạng thái container “running” không tự chứng minh directory đã sẵn sàng nhận Bind.

### Xác nhận naming context

Thử dùng LDAP CLI ngay trong container:

~~~bash
docker compose exec ldap ldapsearch -LLL -x \
  -H ldap://127.0.0.1:389 \
  -D "cn=admin,dc=example,dc=org" -W \
  -b "dc=example,dc=org" -s base \
  "(objectClass=*)" dn objectClass
~~~

Nhập mật khẩu admin từ `.env` khi công cụ hỏi. `-W` tránh truyền mật khẩu trực tiếp vào dòng lệnh, nơi mật khẩu có thể lộ trong shell history/process list. Kỳ vọng thấy entry gốc:

~~~text
dn: dc=example,dc=org
objectClass: top
objectClass: dcObject
objectClass: organization
~~~

Tập `objectClass` chính xác của entry gốc phụ thuộc image; điều cốt lõi là base `dc=example,dc=org` tồn tại.

### Phân biệt các loại DN khi gọi LDAP

| Tên | Ví dụ | Vai trò |
| --- | --- | --- |
| Naming context / base DN gốc | `dc=example,dc=org` | Gốc của dữ liệu directory bài lab. |
| DN Bind quản trị | `cn=admin,dc=example,dc=org` | Danh tính dùng khi thêm fixture. |
| DN người dùng | `uid=lan,ou=people,dc=example,dc=org` | Entry danh bạ được lưu. |
| Search base | `ou=people,dc=example,dc=org` | Nhánh giới hạn tìm kiếm nhân viên. |
| RDN người dùng | `uid=lan` | Thành phần định danh trực tiếp dưới `ou=people`. |

Việc Bind bằng DN quản trị không biến DN đó thành search base. **Danh tính xác thực**, **phạm vi tìm kiếm** và **entry mục tiêu** là các khái niệm khác nhau.

## 8. Nạp fixture vào server bằng ldapadd

Sau khi server sẵn sàng, chạy:

~~~bash
docker compose exec ldap ldapadd -x \
  -H ldap://127.0.0.1:389 \
  -D "cn=admin,dc=example,dc=org" -W \
  -f /work/people.ldif
~~~

Lệnh nạp theo thứ tự các entry: tạo `ou=people` và `ou=groups` trước, sau đó đến nhân viên và nhóm. Thành công thường có các dòng `adding new entry ...`.

- `-x`: dùng Simple authentication, không tự động chọn SASL.
- `-H`: URI LDAP trong container. Đây là kết nối **nội bộ container** vì CLI đang chạy trong server container.
- `-D`: DN được dùng để Bind trước khi gửi yêu cầu Add.
- `-W`: nhập mật khẩu tại lời nhắc.
- `-f`: đường dẫn LDIF đã mount ở chế độ chỉ đọc.

**Chỉ chạy `ldapadd` khi dữ liệu chưa được nạp.** Nếu chạy lại, server trả `Already exists (68)` cho những DN có sẵn. Đây không phải lỗi Compose: volume đã giữ dữ liệu từ lần trước. Nếu cần cập nhật entry có sẵn, dùng `ldapmodify` hoặc CRUD trong Spring LDAP; nếu cần reset hoàn toàn, xem mục cuối.

## 9. Kiểm tra Bind và truy vấn Search

### 9.1. Kiểm tra danh tính đã Bind

Đăng nhập thử bằng tài khoản đọc:

~~~bash
docker compose exec ldap ldapwhoami -x \
  -H ldap://127.0.0.1:389 \
  -D "cn=readonly,dc=example,dc=org" -W
~~~

Kỳ vọng trả về danh tính tương ứng (thường có tiền tố `dn:`). Nếu báo `Invalid credentials (49)`, kiểm tra giá trị `LDAP_READONLY_USER`, DN, mật khẩu và việc volume đã được khởi tạo trước khi thêm cấu hình tài khoản đọc.

Việc `ldapwhoami` thành công xác nhận **Bind**, còn quyền Search/Modify là chuyện khác và phải kiểm tra riêng theo ACL của server.

### 9.2. Search một entry theo uid

~~~bash
docker compose exec ldap ldapsearch -LLL -x \
  -H ldap://127.0.0.1:389 \
  -D "cn=readonly,dc=example,dc=org" -W \
  -b "ou=people,dc=example,dc=org" -s one \
  "(&(objectClass=inetOrgPerson)(uid=lan))" \
  dn uid cn sn mail title
~~~

Dự kiến có một entry:

~~~text
dn: uid=lan,ou=people,dc=example,dc=org
uid: lan
cn: Nguyen Thi Lan
sn: Nguyen
mail: lan@example.org
title: Backend Developer
~~~

Bốn phần quan trọng của truy vấn:

| Thành phần | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Bind DN | `cn=readonly,dc=example,dc=org` | Danh tính có quyền truy cập. |
| Search base | `ou=people,dc=example,dc=org` | Chỉ tìm từ nhánh người dùng. |
| Scope | `-s one` | Chỉ entry con trực tiếp của base, không đi sâu các OU con. |
| Filter | `(&(objectClass=inetOrgPerson)(uid=lan))` | Lọc class người dùng và uid bằng `lan`. |

Thử tìm toàn bộ người dùng có email:

~~~bash
docker compose exec ldap ldapsearch -LLL -x \
  -H ldap://127.0.0.1:389 \
  -D "cn=readonly,dc=example,dc=org" -W \
  -b "ou=people,dc=example,dc=org" -s one \
  "(&(objectClass=inetOrgPerson)(mail=*))" \
  dn uid cn mail
~~~

Dự kiến tìm thấy `lan` và `minh`. Filter presence `(mail=*)` yêu cầu thuộc tính tồn tại, khác với `(mail=)`. Đừng ghép filter bằng dữ liệu trực tiếp từ HTTP request; với Spring LDAP, dùng `LdapQueryBuilder` hoặc các lớp filter để escape giá trị.

### 9.3. Kiểm tra nhóm

~~~bash
docker compose exec ldap ldapsearch -LLL -x \
  -H ldap://127.0.0.1:389 \
  -D "cn=readonly,dc=example,dc=org" -W \
  -b "ou=groups,dc=example,dc=org" -s one \
  "(cn=engineering)" dn cn member
~~~

Kỳ vọng `member` có hai DN dưới `ou=people`. Đây là quan hệ tham chiếu bằng **DN**, không tự động là quan hệ khóa ngoại như trong database quan hệ; việc đổi DN người dùng có thể cần cập nhật tham chiếu nhóm tùy cấu hình directory.

## 10. Kết nối Spring Boot với container LDAP

Thêm các dependency phù hợp với phiên bản Spring Boot của dự án:

~~~xml
<!-- Đặt bên trong <dependencies> của pom.xml. -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-ldap</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
~~~

Nếu dùng Gradle, thêm các dependency tương ứng và để Spring Boot quản lý phiên bản thư viện. Với ví dụ này, không cần thêm riêng bản Spring LDAP không tương thích với BOM của Boot.

Cấu hình `application-local.yml` cho **Spring Boot chạy trên host**:

~~~yaml
spring:
  ldap:
    urls: ldap://localhost:1389
    base: dc=example,dc=org
    username: cn=readonly,dc=example,dc=org
    password: "${LDAP_READONLY_USER_PASSWORD}"
~~~

Đặt biến môi trường `LDAP_READONLY_USER_PASSWORD` trong shell chạy Java hoặc Run Configuration của IDE. Nếu dùng profile `local`, kích hoạt bằng cấu hình IDE hoặc `--spring.profiles.active=local`.

**Không nhầm:** Spring Boot đọc biến môi trường của **chính tiến trình Java**. File `.env` dùng để thay biến của Compose, vì vậy cần truyền cùng secret vào Java riêng. Trong môi trường production, thay cách truyền này bằng secret manager hoặc hệ thống cấp secret được phê duyệt.

Nếu ứng dụng được container hóa trong cùng Compose project, URL thành `ldap://ldap:389`, không phải `ldap://localhost:1389`. Trong mọi trường hợp, ứng dụng phải dùng **search base tương ứng với naming context thực**; ở đây `ou=people` nằm dưới `dc=example,dc=org`.

## 11. Ánh xạ entry bằng Spring Data LDAP

Có thể biểu diễn entry `inetOrgPerson` thành một Java entity có DN và các thuộc tính hồ sơ.

`DirectoryPerson.java`:

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

    @Attribute(name = "mail")
    private String email;

    public Name getDn() { return dn; }
    public void setDn(Name dn) { this.dn = dn; }

    public String getUid() { return uid; }
    public void setUid(String uid) { this.uid = uid; }

    public String getCommonName() { return commonName; }
    public void setCommonName(String commonName) {
        this.commonName = commonName;
    }

    public String getSurname() { return surname; }
    public void setSurname(String surname) {
        this.surname = surname;
    }

    public String getEmail() { return email; }
    public void setEmail(String email) { this.email = email; }
}
~~~

Trong Spring LDAP ODM:

- `@Entry` ánh xạ class Java với tập object class và vị trí trong directory.
- `@Id` giữ **DN**, không phải khóa tự tăng kiểu SQL.
- `@Attribute` gắn tên thuộc tính Java vào attribute LDAP.
- `@Entry(base = "ou=people")` là nhánh tương đối với `spring.ldap.base` trong cấu hình đang dùng.

Ví dụ chỉ ánh xạ một giá trị cho `cn`/`mail`. Một số thuộc tính LDAP có thể đa giá trị; nếu dữ liệu thực sự có nhiều giá trị, hãy dùng kiểu collection và kiểm thử mapping.

Repository đọc entry theo `uid`:

~~~java
import java.util.Optional;

import org.springframework.data.ldap.repository.LdapRepository;

public interface DirectoryPersonRepository
        extends LdapRepository<DirectoryPerson> {

    Optional<DirectoryPerson> findByUid(String uid);
}
~~~

Trong bài lab, cả hai `uid` khác nhau và mỗi `uid` tìm ra tối đa một entry. Tuy nhiên schema LDAP không tự bảo đảm mọi giá trị `uid` là duy nhất giữa các DN khác nhau; điều này phải được quản lý bằng quy tắc dữ liệu và ràng buộc tương ứng.

### Cần quyền ghi khi thử CRUD

Tài khoản `readonly` chỉ phù hợp để đọc/search. Nếu thử `repository.save(...)` hoặc thao tác Modify/Delete bằng tài khoản này, LDAP có thể trả `Insufficient access (50)`. Điều đó là **đúng theo chính sách**; đừng cấp quyền admin cho một API chỉ cần tra cứu.

Để học CRUD, có thể tạo một service account có quyền ghi **giới hạn trong nhánh lab** hoặc dùng admin **chỉ trong lệnh nhập dữ liệu thử nghiệm**, rồi kiểm tra từng quyền ACL. Không dùng tài khoản admin chung cho API của hệ thống thật.

## 12. Truy vấn bằng LdapTemplate, trả về dữ liệu tối thiểu

`LdapTemplate` giúp xác định rõ scope, base và filter. Ví dụ service tra cứu tên theo `uid`:

~~~java
import java.util.List;

import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;
import org.springframework.ldap.query.SearchScope;
import org.springframework.stereotype.Service;

@Service
public class PeopleLookupService {

    private final LdapTemplate ldapTemplate;

    public PeopleLookupService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<String> findNamesByUid(String uid) {
        if (uid == null || !uid.matches("[a-z][a-z0-9._-]{1,31}")) {
            throw new IllegalArgumentException("Invalid uid");
        }

        LdapQuery query = LdapQueryBuilder.query()
                .base("ou=people")
                .searchScope(SearchScope.ONELEVEL)
                .countLimit(20)
                .where("objectClass").is("inetOrgPerson")
                .and("uid").is(uid);

        return ldapTemplate.search(
                query,
                (AttributesMapper<String>) attrs ->
                        (String) attrs.get("cn").get()
        );
    }
}
~~~

Ví dụ gọi `findNamesByUid("lan")` dự kiến trả danh sách chứa `Nguyen Thi Lan`.

**Vì sao không ghép filter?** Mã như `"(uid=" + uid + ")"` tạo nguy cơ LDAP filter injection. `LdapQueryBuilder` xử lý escaping của giá trị so sánh; validation của ứng dụng vẫn cần thiết. Với DN, dùng API `LdapNameBuilder` thay vì ghép chuỗi từ input. Escape filter (RFC 4515) và escape DN (RFC 4514) là hai quy tắc khác nhau.

Ngoài ra:

- Với danh bạ lớn, giới hạn `countLimit` và Search scope để tránh đọc quá nhiều entry.
- Không cung cấp nguyên `DirectoryPerson` làm JSON nếu chứa DN hoặc thông tin nội bộ; nên chuyển sang DTO phản hồi.
- Kết quả Search phụ thuộc ACL và schema server. Một thuộc tính không được trả về có thể là do quyền truy cập hoặc danh sách thuộc tính yêu cầu, không nhất thiết vì entry không có nó.
- Nếu tích hợp REST API, xác thực người gọi HTTP **riêng**; việc ứng dụng Bind LDAP bằng tài khoản đọc không xác thực người đang gọi API.

## 13. Test nhanh luồng từ container đến ứng dụng

Khi đã chạy LDAP và nạp LDIF, bạn có thể thực hiện các bước sau:

1. Kiểm tra `docker compose ps` cho thấy container đang chạy.
2. `ldapwhoami` với tài khoản `readonly` thành công.
3. `ldapsearch` theo `uid=lan` trả entry hợp lệ.
4. Khởi động Spring Boot với profile `local` và mật khẩu đúng.
5. Gọi `findNamesByUid("lan")` bằng unit/integration test hoặc endpoint thử nghiệm; kỳ vọng có `Nguyen Thi Lan`.
6. Gọi `findNamesByUid("unknown")`; kỳ vọng danh sách rỗng.
7. Gọi `findNamesByUid("lan*)(uid=*)")`; validation phải từ chối, không làm thay đổi cấu trúc filter.
8. Thử dùng sai mật khẩu đọc, xác nhận ứng dụng phân biệt lỗi kết nối/Bind với kết quả Search rỗng.

Có thể xây thêm endpoint chỉ đọc để xem kết quả trong bài lab:

~~~java
import java.util.List;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/people")
public class PeopleController {

    private final PeopleLookupService peopleLookupService;

    public PeopleController(PeopleLookupService peopleLookupService) {
        this.peopleLookupService = peopleLookupService;
    }

    @GetMapping
    public List<String> lookup(@RequestParam String uid) {
        return peopleLookupService.findNamesByUid(uid);
    }
}
~~~

Dùng trên máy phát triển:

~~~bash
curl --get "http://localhost:8080/api/people" \
  --data-urlencode "uid=lan"
~~~

Kỳ vọng JSON:

~~~json
["Nguyen Thi Lan"]
~~~

Endpoint này là minh họa để thử kết nối; trước khi expose ra mạng, cần HTTP authentication/authorization, xử lý lỗi thống nhất, rate limiting và bảo vệ dữ liệu cá nhân.

## 14. Các lỗi hay gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra |
| --- | --- | --- |
| Docker không khởi động | Daemon chưa chạy, thiếu quyền hoặc port 1389 đã bị chiếm. | Kiểm tra `docker info`, `docker compose ps` và port host. |
| `Can't contact LDAP server (-1)` | Container chưa sẵn sàng, sai host/port hoặc bị chặn. | Thử `ldapsearch` trong container, so sánh `localhost:1389` với `ldap:389`. |
| `Invalid credentials (49)` | Sai Bind DN/mật khẩu; volume cũ dùng secret khác. | Kiểm tra DN, secret và thời điểm khởi tạo volume. |
| `No such object (32)` | Base DN hoặc OU chưa tồn tại. | Kiểm tra naming context, `ou=people` và thứ tự nạp LDIF. |
| `Already exists (68)` khi `ldapadd` | Đã nạp cùng DN vào volume. | Search entry rồi quyết định dùng Modify hay reset lab. |
| `Object class violation (65)` | Thiếu `cn`/`sn`, schema thiếu hoặc thuộc tính sai. | Kiểm tra object classes và schema server. |
| `Insufficient access (50)` | Tài khoản readonly không có quyền Add/Modify hoặc đọc một số thuộc tính. | Xem ACL; dùng tài khoản ghi giới hạn riêng cho CRUD. |
| Spring Boot chạy trên host mà không kết nối | Dùng `ldap://ldap:389`, vốn chỉ phân giải trong Compose network. | Đổi thành `ldap://localhost:1389`. |
| App trong container không kết nối | Dùng `localhost:1389` bên trong container app. | Đổi URI thành `ldap://ldap:389` trong cùng Compose network. |
| Search trả rỗng dù có entry | Sai search base, scope, filter, quyền hoặc matching rule. | So sánh cùng Bind DN và filter bằng `ldapsearch`. |
| Cấu hình biến đổi mà không hiệu lực | Volume LDAP giữ database/config đã khởi tạo. | Kiểm tra config, thay đúng cách hoặc reset riêng lab. |
| TLS handshake lỗi khi chuyển LDAPS | Chưa tin cậy CA, hostname trên chứng chỉ không khớp. | Kiểm tra certificate chain, SAN/hostname, truststore và server TLS. |

**Ghi log an toàn:** có thể tăng mức log/trace có chọn lọc cho Spring LDAP/JNDI khi cần chẩn đoán, nhưng không ghi mật khẩu, thông tin xác thực hoặc nội dung entry nhạy cảm ra console/CI log. Tránh gửi nguyên file `.env` khi báo lỗi.

## 15. Dừng, chạy lại và reset môi trường

Sau khi học xong:

~~~bash
docker compose stop
~~~

Lệnh trên dừng container nhưng giữ container/volume. Chạy lại:

~~~bash
docker compose start
~~~

Nếu muốn dừng và gỡ container/network do Compose tạo, **vẫn giữ named volumes**:

~~~bash
docker compose down
~~~

Lần sau `docker compose up -d` có thể gắn lại `ldap_data` và `ldap_config` chứa dữ liệu cũ.

**Chỉ khi muốn xóa sạch toàn bộ dữ liệu lab**, dùng:

~~~bash
docker compose down -v
~~~

`-v` xóa các named volumes do Compose quản lý trong project này. Thao tác này **mất toàn bộ entry và cấu hình LDAP trong volume**, không phục hồi bằng lệnh start; lần chạy sau image sẽ khởi tạo lại từ đầu. Cần kiểm tra đúng thư mục Compose/project trước khi xóa, nhất là khi dùng Docker volume phục vụ các bài thực hành khác.

Nếu cần lặp lại bài tập mà giữ dữ liệu, hãy chỉnh dữ liệu bằng `ldapmodify` hoặc dùng LDIF có cơ chế thay đổi cụ thể, thay vì reset mọi lần.

## 16. Từ lab localhost sang môi trường phát triển chia sẻ

Cấu hình chạy LDAP plaintext trên loopback giúp người học nhìn rõ kết nối, DN, Bind và Search. Khi chuyển sang máy chủ dùng chung, phải thay đổi thiết kế bảo mật:

### 16.1. TLS và chứng chỉ

- Chọn **LDAPS** hoặc **StartTLS** cho kết nối từ Spring đến LDAP.
- Với LDAPS, thông thường sử dụng URI `ldaps://hostname:636` và bảo đảm server hỗ trợ cổng đó.
- Với StartTLS, thiết lập TLS **thành công trước khi gửi Simple Bind có mật khẩu**.
- Cấp chứng chỉ có SAN khớp hostname ứng dụng sử dụng; cấu hình truststore của JVM tin cậy CA phát hành.
- Không bỏ kiểm tra chứng chỉ/hostname bằng TrustManager “chấp nhận tất cả”.
- Với container image, xem hướng dẫn cụ thể về đường dẫn mount private key, certificate, CA và quyền file. Tùy image, thông số TLS và cách khởi động khác nhau.

### 16.2. Danh tính, quyền và mạng

- Dùng tài khoản đọc riêng cho API danh bạ; dùng tài khoản ghi với ACL tối thiểu khi học thao tác CRUD.
- Hạn chế quyền đọc các thuộc tính nhạy cảm; đừng giả định mọi entry `inetOrgPerson` đều được công khai.
- Chỉ mở cổng cho ứng dụng cần kết nối; tránh publish LDAP plaintext trên địa chỉ mạng công cộng.
- Quản lý secret qua cơ chế cấp secret phù hợp, xoay vòng mật khẩu và tách tài khoản test/production.
- Kiểm thử ACL bằng **chính DN mà ứng dụng sử dụng để Bind**, vì kết quả Search của admin có thể khác tài khoản chỉ đọc.
- Xác thực và phân quyền **HTTP** độc lập với việc ứng dụng đã Bind LDAP bằng tài khoản dịch vụ.

### 16.3. Độ tin cậy, dữ liệu và kiểm thử

- Có health check thực sự kiểm tra LDAP sẵn sàng Bind/Search, không chỉ dựa vào trạng thái container.
- Thiết lập timeout kết nối/đọc, giới hạn Search và quan sát mức sử dụng tài nguyên.
- Tạo fixture dữ liệu giả cho test, không đưa hồ sơ nhân viên hoặc mật khẩu thật vào LDIF.
- Kiểm thử tích hợp schema, DN, filter, ACL và TLS trên đúng loại directory sẽ dùng.
- Nâng cấp image được kiểm soát, có backup và quy trình migration khi cấu trúc/schema thay đổi.

## 17. Bài tập củng cố

**Bài 1 — Hiểu DN và phạm vi Search.** Cho biết sự khác biệt giữa DN `uid=lan,ou=people,dc=example,dc=org`, search base `ou=people,dc=example,dc=org` và Bind DN `cn=readonly,dc=example,dc=org`. Thử đổi `-s one` sang `-s sub` để xem hành vi khi có OU con.

**Bài 2 — Chỉnh dữ liệu.** Thêm nhân viên `uid=an` bằng LDIF hợp lệ; bắt buộc có `cn` và `sn`. Nạp bằng admin, rồi Search bằng readonly. Dự đoán lỗi nếu cố tạo entry chỉ có `uid` và `mail` mà thiếu `sn`.

**Bài 3 — Tìm theo filter an toàn.** Thêm phương thức `findByEmail(String email)` với `LdapQueryBuilder`. Giới hạn base `ou=people` và dùng equality thay vì ghép `"(mail=" + email + ")"`.

**Bài 4 — Kiểm thử quyền.** Thử thay `title` bằng tài khoản readonly và xác minh directory từ chối. Sau đó giải thích vì sao không nên sửa ACL cấp toàn quyền chỉ để một test CRUD “pass”.

**Bài 5 — Lưu trữ.** Khởi động lại container rồi `ldapsearch`, chứng minh entry vẫn tồn tại. Giải thích kết quả khác biệt giữa `docker compose down` và `docker compose down -v`.

### Ma trận nghiệm thu

| Trường hợp kiểm thử | Kết quả mong đợi |
| --- | --- |
| Compose khởi động với volume trống | Có naming context `dc=example,dc=org`. |
| Bind admin bằng mật khẩu đúng | Thành công; truy vấn được root entry. |
| Bind readonly bằng mật khẩu đúng | Thành công; truy vấn được entry được ACL cho phép. |
| Bind với mật khẩu sai | Thất bại có kiểm soát, không tự xem là authenticated. |
| Nạp LDIF mẫu lần đầu | Tạo được OU, hai `inetOrgPerson` và một `groupOfNames`. |
| Nạp lại LDIF không chỉnh sửa | Báo entry trùng; không tạo bản sao DN. |
| Search `uid=lan` trong `ou=people` | Tìm đúng một entry của Lan. |
| Search `(mail=*)` trong `ou=people` | Tìm hai entry có email theo fixture. |
| Spring Data LDAP dùng base đúng | Có thể đọc `uid=lan` bằng repository hoặc `LdapTemplate`. |
| Dùng giá trị filter có ký tự đặc biệt | Input được validate/escape; không thay cấu trúc filter. |
| Thử sửa bằng readonly | Directory từ chối theo ACL, không tự tăng quyền. |
| Dừng và chạy lại container | Dữ liệu trên named volumes vẫn còn. |
| Xóa volumes của riêng project lab | Dữ liệu được tạo lại từ trạng thái khởi tạo khi khởi động mới. |

## 18. Câu hỏi tự ôn tập

1. Vì sao LDAP dùng DN, RDN và `objectClass` thay cho mô hình bảng/khóa chính quen thuộc của SQL?
2. `LDAP_DOMAIN=example.org` dẫn đến naming context nào trong ví dụ image?
3. Khi Spring Boot chạy trên host, vì sao `ldap://localhost:1389` khác `ldap://ldap:389`?
4. Vì sao `docker compose restart` không tự áp dụng một `LDAP_DOMAIN` mới khi volume đã có dữ liệu?
5. Tại sao phải nạp `ou=people` trước `uid=lan,ou=people,...`?
6. `ldapwhoami` thành công có chứng minh tài khoản có quyền thêm entry không?
7. Vì sao `inetOrgPerson` phải có `cn` và `sn`?
8. `repository.save(...)` bằng readonly thất bại có phải lỗi ứng dụng không?
9. Vì sao dùng `LdapQueryBuilder` khi filter chứa giá trị đến từ HTTP client?
10. Cần thay đổi những gì trước khi dùng LDAP server container trong môi trường chia sẻ?

**Ghi nhớ:** một OpenLDAP container giúp tạo directory thử nghiệm có thể khởi động lại, nhưng quá trình học hiệu quả nhất khi kiểm tra từng lớp: **container hoạt động → naming context đúng → Bind được → LDIF hợp schema → Search ra entry → Spring Data LDAP ánh xạ/truy vấn đúng**. Từ đó mới mở rộng sang CRUD, bảo mật TLS, ACL và kiểm thử tích hợp.

### Tài liệu tham khảo

- [Docker Compose Documentation](https://docs.docker.com/compose/): cấu hình services, ports và volumes.
- [osixia/docker-openldap](https://github.com/osixia/docker-openldap): tài liệu image dùng cho bài lab và các biến môi trường của image.
- [OpenLDAP Administrator's Guide](https://openldap.org/doc/admin26/): slapd, schema, ACL, TLS và vận hành directory.
- [RFC 4511 — Lightweight Directory Access Protocol (LDAP): The Protocol](https://www.rfc-editor.org/rfc/rfc4511): Bind, Search và các thao tác LDAP.
- [RFC 4512 — LDAP: Directory Information Models](https://www.rfc-editor.org/rfc/rfc4512): entry, DN, schema và object class.
- [RFC 2798 — Definition of the inetOrgPerson LDAP Object Class](https://www.rfc-editor.org/rfc/rfc2798): class `inetOrgPerson`.
- [Spring Data LDAP Reference](https://docs.spring.io/spring-data/ldap/reference/): repository và ánh xạ entry.
- [Spring LDAP Reference](https://docs.spring.io/spring-ldap/reference/): `LdapTemplate`, truy vấn và quản lý context.
