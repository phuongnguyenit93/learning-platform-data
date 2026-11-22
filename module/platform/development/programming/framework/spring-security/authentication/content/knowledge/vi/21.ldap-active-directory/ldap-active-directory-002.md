# Kết nối LDAP, base DN và tài khoản dùng để tìm kiếm

Trong ứng dụng Spring Security sử dụng LDAP hoặc Active Directory (AD), việc xác thực chỉ hoạt động đúng khi ứng dụng biết **kết nối đến máy chủ nào**, **bắt đầu tìm người dùng từ nhánh nào** và **dùng danh tính nào để thực hiện thao tác tìm kiếm**. Ba cấu hình này liên quan với nhau nhưng có vai trò khác nhau; nhầm chúng có thể khiến ứng dụng kết nối thành công mà vẫn không tìm thấy tài khoản.

Bài học tập trung vào kết nối LDAP, `base DN` và tài khoản tìm kiếm (*service/bind account*) trong luồng đăng nhập bằng mật khẩu. Ví dụ Java dùng Spring Boot 3.x, Spring Security 6.x và Java 17+; tên máy chủ, DN và tài khoản đều là dữ liệu minh họa.

## 1. Nhận diện cấu trúc LDAP

LDAP (Lightweight Directory Access Protocol) cung cấp cách truy vấn và thao tác với các mục (*entry*) trong một dịch vụ thư mục. AD là dịch vụ thư mục của Microsoft có hỗ trợ giao thức LDAP, đồng thời có các quy ước tài khoản và thuộc tính riêng.

Mỗi mục được nhận diện bằng **distinguished name (DN)**, là đường dẫn đầy đủ trong cây thư mục. Ví dụ:

~~~text
dc=example,dc=org
├── ou=people
│   ├── uid=linh
│   └── uid=nam
├── ou=groups
└── ou=service
    └── cn=svc-ldap-reader
~~~

Trong sơ đồ, một mục người dùng có DN đầy đủ:

~~~text
uid=linh,ou=people,dc=example,dc=org
~~~

Các thành phần cần phân biệt:

| Thành phần | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `dc` (*domain component*) | Thành phần của tên miền trong cây LDAP | `dc=example,dc=org` |
| `ou` (*organizational unit*) | Nhánh tổ chức để chứa người dùng, nhóm hoặc tài nguyên | `ou=people` |
| `uid`, `cn` | Thuộc tính có thể xuất hiện trong tên mục; lựa chọn tùy schema | `uid=linh`, `cn=svc-ldap-reader` |
| RDN (*relative distinguished name*) | Thành phần tên tương đối của mục so với cha | `uid=linh` |
| DN | Tên đầy đủ của mục, gồm RDN và các nhánh cha | `uid=linh,ou=people,dc=example,dc=org` |
| Base DN | Gốc ngữ cảnh mà client dùng làm điểm xuất phát cho các thao tác tương đối | `dc=example,dc=org` |

LDAP không buộc mọi tổ chức đều dùng `ou=people` hoặc thuộc tính `uid`. Trong AD, tên người dùng thường được tìm bằng `sAMAccountName` hoặc `userPrincipalName` và DN có thể có dạng `CN=Linh Nguyen,OU=Employees,DC=corp,DC=example,DC=com`.

### Base DN, search base và DN của tài khoản tìm kiếm

Giả sử ứng dụng có các giá trị sau:

~~~properties
LDAP_URL=ldaps://directory.example.org:636
LDAP_BASE_DN=dc=example,dc=org
LDAP_USER_SEARCH_BASE=ou=people
LDAP_USER_SEARCH_FILTER=(uid={0})
LDAP_BIND_DN=cn=svc-ldap-reader,ou=service,dc=example,dc=org
~~~

Ý nghĩa:

1. **LDAP URL** xác định máy chủ và giao thức truyền tải. `ldaps://` biểu thị LDAP qua TLS ngay từ lúc bắt đầu kết nối.
2. **Base DN** là gốc dùng cho các DN tương đối trong `ContextSource`. Ở đây là `dc=example,dc=org`.
3. **User search base** thu hẹp phạm vi tìm người dùng dưới base DN. Ở đây `ou=people` là đường dẫn **tương đối**, nên phạm vi tìm kiếm hiệu lực là `ou=people,dc=example,dc=org`.
4. **User search filter** chọn mục phù hợp trong phạm vi đó. Với tên đăng nhập `linh`, `(uid={0})` trở thành điều kiện tìm `uid=linh`.
5. **Bind DN** chỉ danh tính mà ứng dụng sử dụng để đọc/tìm trong thư mục. DN này là **DN đầy đủ** (tùy máy chủ cũng có thể hỗ trợ dạng principal khác); không ghép thêm base DN vào nó. Mật khẩu của tài khoản này được cấu hình riêng.

**Điểm dễ nhầm:** `LDAP_BIND_DN` không phải DN của người dùng cuối đang đăng nhập. Nó là tài khoản kỹ thuật được cấp quyền tra cứu. DN tìm được, chẳng hạn `uid=linh,ou=people,dc=example,dc=org`, mới là danh tính được thử bind với mật khẩu người dùng trong cơ chế xác thực LDAP bind.

Nếu đặt `userSearchBase=""`, việc tìm kiếm bắt đầu từ chính base DN. Nếu dùng DN đầy đủ ở nơi API yêu cầu DN tương đối, có thể vô tình ghép trùng `dc=example,dc=org` và nhận lỗi không tìm thấy nhánh. Cũng không nên vừa gắn suffix vào URL LDAP vừa đặt lại chính suffix đó ở `spring.ldap.base`.

## 2. Một lần đăng nhập sử dụng những kết nối nào?

Với chiến lược **tìm người dùng rồi bind** (*search-then-bind*), luồng thông thường gồm:

1. Ứng dụng thiết lập kết nối LDAP an toàn và dùng bind DN + mật khẩu của tài khoản tra cứu để thực hiện thao tác tìm kiếm.
2. Ứng dụng tìm một mục người dùng trong `base DN + user search base` theo filter, ví dụ `(uid=linh)`. Kết quả phải xác định đúng một danh tính mong muốn.
3. Ứng dụng lấy DN đầy đủ của mục tìm được.
4. Spring Security thử **bind bằng DN của chính người dùng và mật khẩu họ vừa nhập**. Máy chủ LDAP kiểm tra mật khẩu; ứng dụng không cần đọc thuộc tính mật khẩu từ thư mục.
5. Nếu bind thành công, Spring Security tạo đối tượng xác thực. Việc tìm nhóm/quyền (nếu có) là bước cấu hình bổ sung, tách biệt khỏi việc tìm DN người dùng.

~~~text
Người dùng -- username/password --> Ứng dụng
Ứng dụng -- bind service account --> LDAP
Ứng dụng -- search username ------> LDAP
LDAP      -- user DN -------------> Ứng dụng
Ứng dụng -- bind user DN/password -> LDAP
LDAP      -- success/failure -----> Ứng dụng
~~~

Hai bí mật có vai trò khác nhau: **mật khẩu service account** cho phép ứng dụng tra cứu; **mật khẩu người dùng** dùng để chứng minh danh tính người đang đăng nhập. Không sử dụng tài khoản tra cứu có quyền quản trị domain chỉ để đọc người dùng.

Có một phương án khác là `userDnPatterns("uid={0},ou=people")`: khi vị trí DN dự đoán được từ username, Spring Security có thể thử bind trực tiếp và không cần tìm DN trước. Phương án này khó áp dụng nếu người dùng nằm ở nhiều OU, DN thay đổi hoặc tên đăng nhập không suy ra DN. Với các hệ thống như vậy, search-then-bind linh hoạt hơn.

## 3. Chuẩn bị máy chủ và tài khoản tìm kiếm

Trước khi viết cấu hình Spring, cần có thông tin từ nhóm quản trị thư mục:

| Thông tin | Cần xác nhận |
| --- | --- |
| Host / cổng | FQDN của LDAP server hoặc domain controller, cổng TLS, cấu hình DNS và kết nối mạng |
| TLS | Chứng chỉ máy chủ hợp lệ, CA nội bộ nếu có, tên host khớp chứng chỉ |
| Base DN | Naming context thực tế, ví dụ `dc=example,dc=org` |
| Vị trí user | Các OU chứa user; có user nằm ngoài nhánh dự kiến không |
| Thuộc tính login | `uid`, `sAMAccountName` hay `userPrincipalName`; giá trị có duy nhất trong phạm vi tìm kiếm không |
| Tài khoản tra cứu | DN/UPN được máy chủ chấp nhận, mật khẩu, quyền đọc tối thiểu và chính sách xoay vòng |
| Chính sách directory | Có cho anonymous search không, giới hạn kết quả, referral, khóa tài khoản và chính sách LDAP signing/TLS |

**Quyền tối thiểu của service account:** tài khoản chỉ cần bind và đọc những thuộc tính dùng cho tìm kiếm/ánh xạ người dùng (và nhóm nếu bài toán yêu cầu). Không cần quyền tạo, sửa, xóa user hoặc quyền Domain Admin. Đừng lưu mật khẩu trong source code, commit, file cấu hình công khai hay nhật ký ứng dụng. Nên đưa qua biến môi trường hoặc secret manager, đặt cơ chế thay đổi/thu hồi và giám sát sự cố.

**Kết nối bảo mật:**

- `ldap://host:389` tự nó không mã hóa lưu lượng; chỉ sử dụng với StartTLS được bật và xác minh đúng. Tùy môi trường, kết nối LDAP không TLS có thể bị từ chối.
- `ldaps://host:636` thiết lập TLS ngay từ đầu; phù hợp cho ví dụ kết nối đơn giản.
- Cần tin cậy CA cấp chứng chỉ trên JVM chạy ứng dụng (truststore phù hợp), xác minh tên host và không tắt kiểm tra chứng chỉ để “cho chạy được”. Công cụ `ldapsearch` có thể sử dụng kho CA khác JVM.
- Cấu hình timeout kết nối/đọc, failover và theo dõi lỗi; không tạo kết nối vô hạn hoặc retry mật khẩu sai liên tục làm khóa tài khoản.

### Kiểm tra độc lập trước khi chạy Spring

Ví dụ dùng bộ công cụ OpenLDAP trên máy có quyền truy cập directory. `-W` yêu cầu nhập mật khẩu tương tác, tránh đưa password vào lịch sử shell:

~~~bash
ldapwhoami -x \
  -H ldaps://directory.example.org:636 \
  -D "cn=svc-ldap-reader,ou=service,dc=example,dc=org" \
  -W
~~~

Nếu bind tài khoản tra cứu thành công, thử tìm đúng user trong phạm vi đã chọn:

~~~bash
ldapsearch -LLL -x \
  -H ldaps://directory.example.org:636 \
  -D "cn=svc-ldap-reader,ou=service,dc=example,dc=org" \
  -W \
  -b "ou=people,dc=example,dc=org" \
  -s sub "(uid=linh)" dn uid cn
~~~

Ở đây `-b` nhận **base DN đầy đủ của lệnh tìm kiếm**; khác với `setUserSearchBase("ou=people")` vốn là đường dẫn tương đối với `spring.ldap.base`. Kết quả mong đợi là một entry đúng người dùng và thuộc tính `dn` hợp lệ; dữ liệu thực tế phụ thuộc directory nên không có stdout cố định. Nếu kết quả bằng 0, xác minh tên thuộc tính, giá trị username, OU và quyền đọc trước khi điều chỉnh ứng dụng.

Nếu máy chủ sử dụng StartTLS trên cổng 389, một cách kiểm tra tương ứng là dùng `-H ldap://directory.example.org:389 -ZZ` (chế độ yêu cầu nâng cấp TLS thành công). Không thay `ldaps://` bằng `ldap://` rồi mặc định cho rằng lưu lượng đã được mã hóa.

## 4. Ví dụ Spring Boot và Spring Security: tìm user trước khi bind

Dưới đây là cấu hình **ứng dụng servlet Spring Boot 3.x có sẵn cấu hình build/Java 17+**. Nó dùng chính tài khoản tra cứu để tìm DN rồi bind bằng mật khẩu đăng nhập. Các đoạn dưới là những phần cần thêm vào một project Spring Boot, không phải một `build.gradle` hoàn chỉnh tự chứa.

### 4.1. Dependencies

Trong `build.gradle` (Groovy DSL) của ứng dụng web đã có Spring Boot plugin:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-data-ldap'
    implementation 'org.springframework.security:spring-security-ldap'
}
~~~

`spring-boot-starter-data-ldap` mang vào Spring LDAP và khả năng tạo `LdapContextSource` từ thuộc tính `spring.ldap.*`; `spring-security-ldap` cung cấp chiến lược xác thực LDAP cho Spring Security. Quản lý version qua dependency management của project Spring Boot, tránh trộn các version không tương thích.

### 4.2. Thuộc tính kết nối

Trong `src/main/resources/application.properties`:

~~~properties
spring.ldap.urls=ldaps://directory.example.org:636
spring.ldap.base=dc=example,dc=org
spring.ldap.username=${LDAP_BIND_DN}
spring.ldap.password=${LDAP_BIND_PASSWORD}
~~~

Ở môi trường chạy, thiết lập `LDAP_BIND_DN` thành DN đầy đủ của service account, ví dụ `cn=svc-ldap-reader,ou=service,dc=example,dc=org`; đưa `LDAP_BIND_PASSWORD` qua secret manager/biến môi trường. `spring.ldap.username` và `spring.ldap.password` ở đây là **thông tin kết nối để tra cứu**, không phải thông tin đăng nhập của mọi user.

Khi dùng auto-configuration này, ứng dụng nhận `LdapContextSource` mà `BaseLdapPathContextSource` có thể tham chiếu. Việc ghi `spring.ldap.base` nghĩa là các phép tìm kiếm nhận base tương đối; đừng lặp lại suffix trong `userSearchBase`.

### 4.3. Cấu hình Java

Tệp `src/main/java/example/ldap/DirectoryDemoApplication.java` (một public class, các class phụ cùng tệp/package):

~~~java
package example.ldap;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ldap.core.support.BaseLdapPathContextSource;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.ldap.LdapBindAuthenticationManagerFactory;
import org.springframework.security.core.Authentication;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class DirectoryDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DirectoryDemoApplication.class, args);
    }
}

@Configuration(proxyBeanMethods = false)
class DirectorySecurityConfiguration {
    @Bean
    AuthenticationManager authenticationManager(
            BaseLdapPathContextSource contextSource) {
        LdapBindAuthenticationManagerFactory factory =
                new LdapBindAuthenticationManagerFactory(contextSource);
        factory.setUserSearchBase("ou=people");
        factory.setUserSearchFilter("(uid={0})");
        return factory.createAuthenticationManager();
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http, AuthenticationManager authenticationManager)
            throws Exception {
        http.authenticationManager(authenticationManager);
        http.authorizeHttpRequests(auth -> auth.anyRequest().authenticated());
        http.httpBasic(Customizer.withDefaults());
        return http.build();
    }
}

@RestController
class WhoAmIController {
    @GetMapping("/whoami")
    String whoami(Authentication authentication) {
        return authentication.getName();
    }
}
~~~

Giải thích các dòng quan trọng:

- `BaseLdapPathContextSource` biểu diễn nguồn kết nối, chứa URL, base DN và credential của service account do Spring Boot cấu hình.
- `LdapBindAuthenticationManagerFactory` tạo `AuthenticationManager` dùng LDAP bind. Nó **không** xác thực người dùng bằng cách đọc mật khẩu LDAP vào `UserDetailsService`.
- `setUserSearchBase("ou=people")` tìm trong `ou=people,dc=example,dc=org`.
- `setUserSearchFilter("(uid={0})")` so khớp login theo `uid`; `{0}` là tham số do Spring Security thay/escape thích hợp. Không tự nối trực tiếp chuỗi input người dùng vào biểu thức LDAP filter.
- `http.authenticationManager(...)` gắn bộ xác thực LDAP cho HTTP Security Filter Chain. `httpBasic()` chỉ dùng làm cách thử đăng nhập dễ quan sát; trong hệ thống thật chọn cơ chế xác thực và bảo vệ HTTP phù hợp.
- Endpoint `/whoami` trả lại tên principal sau khi xác thực; không lộ password hay thông tin nhạy cảm của directory.

Chạy ứng dụng sau khi cấu hình credential, kết nối mạng và truststore hợp lệ:

~~~bash
./gradlew bootRun
curl -i -u linh http://localhost:8080/whoami
~~~

Trên Windows có thể dùng `gradlew.bat bootRun`. `curl -u linh` sẽ hỏi mật khẩu. Khi DN được tìm và mật khẩu người dùng đúng, request nhận HTTP 200 và danh tính đã xác thực; khi thiếu hoặc sai mật khẩu thường nhận HTTP 401. Đây là ví dụ kiểm thử, không khẳng định một stdout cố định khi chưa có server LDAP thực tế.

**Nếu DN biết trước:** thay hai lệnh `setUserSearch...` bằng `factory.setUserDnPatterns("uid={0},ou=people")` *khi chắc chắn mọi user có DN theo khuôn đó*. Pattern cũng tương đối với base DN. Trường hợp này có thể không cần service account để tìm user; chính sách directory và việc đọc thuộc tính nhóm vẫn quyết định có cần credential đọc khác hay không.

## 5. Áp dụng cho Active Directory

AD nói LDAP nhưng cách đặt tên và đăng nhập thường khác OpenLDAP. Ví dụ domain `corp.example.com` có naming context `DC=corp,DC=example,DC=com`. Người dùng có thể nằm ở nhiều OU:

~~~text
CN=Linh Nguyen,OU=Engineering,DC=corp,DC=example,DC=com
CN=Nam Tran,OU=Operations,DC=corp,DC=example,DC=com
~~~

Tên đăng nhập `linh` có thể được lưu trong `sAMAccountName`, trong khi UPN có thể là `linh@corp.example.com`. Không suy đoán DN từ username khi tổ chức có nhiều OU, vì DN còn phụ thuộc vị trí và tên hiển thị.

Với chiến lược search-then-bind đã trình bày:

- Đổi `spring.ldap.base` thành `dc=corp,dc=example,dc=com` theo naming context được quản trị viên xác nhận.
- Nếu user nằm rải rác khắp domain, dùng `factory.setUserSearchBase("")` để tìm từ domain base; nếu chỉ một nhánh cần thiết, thu hẹp về OU thích hợp.
- Đổi filter thành `factory.setUserSearchFilter("(sAMAccountName={0})")` khi login là tên ngắn, hoặc `(userPrincipalName={0})` khi ứng dụng nhận UPN đầy đủ. Kiểm tra tính duy nhất và chính sách đăng nhập thực tế.
- Service account có thể được AD chấp nhận ở dạng UPN như `svc-ldap@corp.example.com` hoặc DN; xác minh với AD thay vì giả định mọi server dùng cùng cú pháp.
- AD có `RootDSE` với thuộc tính `defaultNamingContext` để xác định base của domain hiện tại. Không coi `RootDSE` là một OU chứa người dùng.

Spring Security cũng có `ActiveDirectoryLdapAuthenticationProvider` dành cho kiểu đăng nhập AD với `username@domain`. Đây là một lựa chọn xác thực riêng: kiểm tra cách provider thực hiện bind/tìm kiếm và cấu hình domain, search filter trước khi thay thế luồng `LdapBindAuthenticationManagerFactory` ở ví dụ. Không kết hợp tùy tiện hai provider với cùng một credential nếu chưa xác định rõ cơ chế.

## 6. Lỗi phổ biến và cách khoanh vùng

| Triệu chứng | Nguyên nhân thường gặp | Bước kiểm tra |
| --- | --- | --- |
| Không mở được kết nối / timeout | DNS, firewall, port, server không sẵn sàng | Xác minh FQDN, cổng, kết nối mạng, timeout; thử `ldapwhoami` từ cùng môi trường chạy |
| Lỗi TLS/certificate | CA chưa được JVM tin cậy, certificate hết hạn hoặc sai hostname | Kiểm tra chain chứng chỉ, truststore JVM, FQDN; không tắt xác minh TLS |
| Service bind bị từ chối | Sai DN/UPN, mật khẩu hết hạn, tài khoản bị khóa, chính sách TLS | Thử bind service account độc lập, kiểm tra chính sách server, xoay secret đúng cách |
| Kết nối được nhưng không tìm thấy user | Sai base DN, OU, filter hoặc thuộc tính login | Dùng `ldapsearch -b` với full DN; kiểm tra kết quả trong đúng phạm vi |
| Tìm được user nhưng đăng nhập 401 | Sai mật khẩu user, bind user bị chặn, trạng thái account | Phân biệt bước search với bước bind người dùng; không tiết lộ chi tiết cho client |
| Search báo thiếu quyền | Service account không được đọc OU/thuộc tính cần thiết | Kiểm tra ACL đọc, bổ sung quyền tối thiểu đúng phạm vi |
| Trả nhiều kết quả | Filter quá rộng, tên đăng nhập trùng trong phạm vi | Thu hẹp search base/filter; yêu cầu tiêu chí định danh duy nhất |
| Có user đăng nhập nhưng không có role | Chưa cấu hình truy vấn/ánh xạ nhóm, hoặc service account không đọc được nhóm | Kiểm tra `groupSearchBase`, group filter và ánh xạ authority ở bài quyền riêng |

Một cách debug hiệu quả là tách ba câu hỏi: **(1) kết nối và service bind có thành công không? (2) search có trả đúng một DN không? (3) bind với DN người dùng có thành công không?** Khi ba bước được kiểm chứng riêng, lỗi cấu hình sẽ dễ xác định hơn nhiều so với việc chỉ nhìn HTTP 401.

Không ghi log mật khẩu, header Authorization hoặc toàn bộ thuộc tính directory. Với lỗi AD có mã phụ trong thông báo LDAP, chỉ dùng thông tin chẩn đoán trong log nội bộ được kiểm soát; không phân biệt “tài khoản tồn tại” và “mật khẩu sai” trong phản hồi công khai để tránh lộ thông tin.

## 7. Checklist hoàn thành cấu hình

- [ ] `LDAP_URL` trỏ đúng máy chủ; TLS được xác minh và truststore JVM hoạt động.
- [ ] `base DN` khớp naming context thật, không bị ghép suffix hai lần.
- [ ] `userSearchBase` có ý nghĩa **tương đối** với base DN và bao phủ đúng người dùng.
- [ ] `userSearchFilter` dùng đúng thuộc tính login; input được tham số hóa, không nối thẳng chuỗi.
- [ ] Service account bind được, chỉ có quyền đọc cần thiết và secret không nằm trong source code.
- [ ] Search cho người dùng hợp lệ trả đúng DN; user bind với password đúng thành công và password sai thất bại.
- [ ] Đã kiểm tra trường hợp sai OU, user không tồn tại, tài khoản khóa, hết hạn secret và lỗi kết nối.
- [ ] Nếu cần phân quyền, nhóm/authority được cấu hình và kiểm thử **riêng** với luồng tìm kiếm user.

### Tự kiểm tra kiến thức

1. Nếu `spring.ldap.base=dc=example,dc=org` và `userSearchBase=ou=people`, search thực sự bắt đầu ở DN nào?
2. Vì sao DN của service account cần đầy đủ, còn search base trong factory thường là DN tương đối?
3. Khi tài khoản nằm ở nhiều OU, vì sao `userDnPatterns` có thể thất bại dù username/mật khẩu đúng?
4. Khi `ldapwhoami` bằng service account thành công nhưng `ldapsearch` không tìm thấy user, nên kiểm tra những tham số nào trước?
5. Tại sao không thể dùng mật khẩu service account để thay cho bước bind bằng mật khẩu người dùng?

**Đáp án định hướng:** (1) `ou=people,dc=example,dc=org`; (2) tài khoản bind là principal đầy đủ của kết nối, còn search base được nối tương đối vào base của context; (3) DN không suy ra được từ username nếu vị trí OU thay đổi; (4) base/search base, filter, thuộc tính login, ACL đọc; (5) service account chỉ chứng thực quyền tra cứu, không chứng thực danh tính người dùng cuối.

## Tài liệu tham khảo

- [Spring Security: LDAP Authentication (6.5)](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/ldap.html)
- [Spring Boot: Connecting to an LDAP Server](https://docs.spring.io/spring-boot/3.3/reference/data/nosql.html)
- [Spring LDAP: ContextSource Configuration](https://docs.spring.io/spring-ldap/reference/configuration.html)
- [Microsoft Learn: RootDSE và defaultNamingContext](https://learn.microsoft.com/en-us/windows/win32/adsi/rootdse)
- [RFC 4514: LDAP Distinguished Names](https://www.rfc-editor.org/rfc/rfc4514)
- [RFC 4515: LDAP Search Filter Syntax](https://www.rfc-editor.org/rfc/rfc4515)
