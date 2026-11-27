# URL server, base DN và base package khi cấu hình Spring LDAP

## 1. Ba giá trị dễ bị nhầm vì cùng nói về “vị trí”

Khi tích hợp ứng dụng Spring với dịch vụ thư mục LDAP, lập trình viên cần biết **máy chủ nào sẽ nhận yêu cầu**, **nhánh dữ liệu nào được dùng làm gốc truy cập** và **mã Java nào được Spring quản lý**. Ba câu hỏi tương ứng với **server URL**, **base DN** và **base package**:

| Khái niệm | Ví dụ | Xác định điều gì? | Thuộc hệ thống nào? |
| --- | --- | --- | --- |
| **Server URL** | `ldaps://ldap.example.org:636` | Địa chỉ, giao thức và cổng của dịch vụ LDAP | Kết nối mạng/LDAP |
| **Base DN** | `dc=example,dc=org` | Hậu tố DN dùng làm gốc cho các thao tác LDAP tương đối | Cây thư mục LDAP |
| **Base package** | `com.example.identity.directory` | Vùng package Java được Spring quét để tìm component/repository theo cấu hình | Mã nguồn và Spring container |

**Base DN và base package là hai khái niệm hoàn toàn khác nhau.** Base DN là một tên LDAP gồm các RDN, phân tách bằng dấu phẩy. Base package là tên namespace Java gồm các phần phân tách bằng dấu chấm. Spring không thể suy ra `dc=example,dc=org` từ `com.example.identity.directory`, cũng không thể biết package Java cần quét dựa vào URL máy chủ LDAP.

Bài học thuộc chương **Cấu hình ContextSource**. Trọng tâm là cấu hình chính xác URL và base DN cho `LdapContextSource`, đồng thời xác định đúng base package khi dùng component scanning hoặc Spring Data LDAP repositories. Các ví dụ còn cho thấy mối liên hệ với filter, tìm kiếm, ODM, xác thực, TLS, pooling, xử lý lỗi và kiểm thử LDAP an toàn.

### Mục tiêu học tập

Sau bài này, bạn có thể giải thích sự khác nhau giữa ba loại “base”, cấu hình chúng ở đúng vị trí, đọc được DN hiệu lực của một truy vấn Spring LDAP, chẩn đoán lỗi “không tìm thấy entry” và lỗi “không tìm thấy repository bean”, cũng như kiểm tra kết nối qua TLS bằng quyền tối thiểu.

## 2. Server URL: địa chỉ để mở kết nối LDAP

### 2.1. URL xác định giao thức, máy chủ và cổng

Hai dạng endpoint thường gặp là:

```text
ldap://ldap.example.org:389
ldaps://ldap.example.org:636
```

Ở đây:

- `ldap://` chỉ kết nối LDAP thông thường ở thời điểm thiết lập; **không có nghĩa kết nối đã được mã hóa**.
- `ldaps://` yêu cầu thiết lập TLS ngay từ đầu kết nối.
- `ldap.example.org` là tên máy chủ; cổng `389` và `636` là giá trị phổ biến, có thể thay đổi theo hạ tầng.
- URL không quyết định DN người dùng, search scope, filter hoặc quyền đọc/ghi.

Nếu hạ tầng dùng **StartTLS**, ứng dụng có thể bắt đầu bằng `ldap://` rồi nâng cấp kết nối lên TLS **trước khi gửi mật khẩu hoặc dữ liệu nhạy cảm**. Việc dùng `ldap://` trong cấu hình không tự động bật StartTLS. Cách triển khai StartTLS phải được hỗ trợ bởi thư viện/JNDI provider và cần kiểm tra vòng đời context, chứng chỉ, hostname và khả năng pooling.

Trong ví dụ tiếp theo, ứng dụng sử dụng LDAPS để làm rõ việc tách URL khỏi DN. Máy chủ giả định đã có chứng chỉ đúng tên và ứng dụng tin cậy chuỗi chứng chỉ đó.

### 2.2. Không nhầm URL với DN

Hai thành phần sau trả lời hai câu hỏi khác nhau:

```text
URL:     ldaps://ldap.example.org:636
Base DN: dc=example,dc=org
```

URL trả lời “**kết nối đến đâu?**”, còn DN trả lời “**tìm kiếm trong vùng nào của thư mục?**”. Cùng một LDAP server có thể quản lý nhiều naming context hoặc nhiều OU; ngược lại, một vùng dữ liệu có thể được phục vụ qua nhiều endpoint thuộc hạ tầng nhân bản.

Một số dạng LDAP URL trong tiêu chuẩn có thể chứa thêm phần DN và truy vấn. Trong cấu hình Spring LDAP minh họa ở bài này, nên giữ `url` ở dạng **scheme + host + port**, rồi đặt DN vào thuộc tính `base` riêng. Tránh thêm `dc=example,dc=org` trong URL và lặp lại hậu tố đó ở `base` mà không kiểm tra cách provider xử lý, vì có thể gây nhầm lẫn DN hiệu lực.

### 2.3. Nhiều server URL không đồng nghĩa tự động nhất quán dữ liệu

`LdapContextSource` ở những phiên bản Spring LDAP hỗ trợ cấu hình danh sách URL để provider lựa chọn endpoint. Điều đó không bảo đảm mọi server có dữ liệu đồng bộ tức thời, mọi server đều có quyền ghi hoặc một thao tác đã gửi được retry an toàn. Cần xác định rõ hạ tầng replication/failover, phương thức bind, timeout và hành vi khi kết nối mất giữa thao tác. Nếu máy chủ đã nhận một lần tạo entry rồi client mất response, không nên mù quáng gửi lại lệnh tạo mà chưa kiểm tra trạng thái.

## 3. Base DN: gốc logic của các thao tác thư mục

### 3.1. DN và cấu trúc cây LDAP

**Distinguished Name (DN)** định vị một entry duy nhất trong cây LDAP theo ngữ cảnh tên của server. Các thành phần **Relative Distinguished Name (RDN)** thường đi từ entry hiện tại lên các entry cha, chẳng hạn:

```text
uid=alice,ou=people,dc=example,dc=org
```

Trong đó `uid=alice` là RDN của người dùng, `ou=people` là OU chứa người dùng, còn `dc=example,dc=org` là hậu tố của nhánh thư mục trong ví dụ.

```text
dc=example,dc=org                       <-- naming-context root
|
+-- ou=people                           <-- base tìm người dùng
|   |
|   +-- uid=alice
|   +-- ou=engineering
|       +-- uid=bob
|
+-- ou=groups                           <-- base tìm nhóm
    +-- cn=developers
```

Khi đặt `base = dc=example,dc=org` trong `LdapContextSource`, các DN tương đối mà ứng dụng truyền cho `LdapTemplate` được giải quyết dưới hậu tố đó. Ví dụ:

```text
ContextSource base: dc=example,dc=org
Query base:         ou=people
DN trên server:     ou=people,dc=example,dc=org
```

Với một lệnh lookup entry, DN tương đối `uid=alice,ou=people` tương ứng với `uid=alice,ou=people,dc=example,dc=org` trên server. Không thêm `dc=example,dc=org` lần nữa vào DN tương đối nếu `ContextSource` đã có base này.

### 3.2. Base DN không nhất thiết bằng naming-context root

Server LDAP có thể công bố `namingContexts: dc=example,dc=org` trong **Root DSE** (entry đặc biệt có DN rỗng). Đó là một vùng tên server cung cấp. Ứng dụng tìm người dùng có thể chọn base hẹp hơn, chẳng hạn `ou=people,dc=example,dc=org`, nếu chỉ cần truy cập nhánh người dùng. Khi đó truy vấn `ou=groups` không còn là DN tương đối nằm trong base được chọn theo cách dùng template thông thường.

| Vị trí | Vai trò |
| --- | --- |
| `""` | DN rỗng của Root DSE, dùng khám phá metadata server |
| `dc=example,dc=org` | Ví dụ naming-context root được server công bố |
| `ou=people,dc=example,dc=org` | Ví dụ base DN phù hợp cho nghiệp vụ tìm người dùng |
| `uid=alice,ou=people,dc=example,dc=org` | DN của một entry cụ thể |

**Base DN không quyết định search scope.** Dù gốc là `ou=people`, một truy vấn có thể chỉ xét entry tại base, con trực tiếp hoặc toàn bộ subtree, tùy `SearchScope`/`SearchControls` của lời gọi. Bộ lọc `(uid=alice)` lại quyết định entry nào trong phạm vi được lựa chọn sẽ được trả về.

### 3.3. Base DN cần dựa trên thư mục thực tế

Không nên suy base DN từ email domain hoặc tên hostname. Các thư mục có thể dùng hậu tố `o=example`, `dc=corp,dc=example,dc=org`, `dc=ad,dc=example,dc=org` hoặc những partition khác. Đặc biệt với Active Directory, có thể tồn tại nhiều naming context cho domain, Configuration, Schema và các application partition. Root DSE có thể hỗ trợ khám phá, nhưng tài khoản bind, vị trí entry và chính sách ACL mới xác định nhánh nghiệp vụ phù hợp.

## 4. Base package: nơi Spring tìm các lớp Java

Trong mã Java, **package** là namespace, ví dụ:

```text
com.example.identity
├── IdentityApplication.java
├── config
│   └── LdapConfiguration.java
├── service
│   └── DirectoryService.java
└── directory
    ├── model
    │   └── Person.java
    └── repository
        └── PersonRepository.java
```

Ở đây, `com.example.identity` là package gốc thuận tiện cho **component scanning**. `com.example.identity.directory.repository` là package chứa repository interface. Cả hai nằm trong code Java; chúng **không phải** DN, OU hay vị trí có thể tìm trên LDAP server.

### 4.1. Component scanning với Spring Boot

Một ứng dụng Spring Boot điển hình đặt class `@SpringBootApplication` ở package cha để Spring tự phát hiện các bean có annotation phù hợp ở các package con:

```java
package com.example.identity;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class IdentityApplication {
    public static void main(String[] args) {
        SpringApplication.run(IdentityApplication.class, args);
    }
}
```

Nếu `LdapConfiguration` hoặc `DirectoryService` nằm ngoài vùng package được Spring quét, bean mong đợi có thể không được đăng ký, dẫn tới lỗi như “No qualifying bean of type ...”. Trường hợp đó liên quan **component scanning**. Thay đổi LDAP `base` hoặc sửa search filter sẽ không chữa được lỗi bean chưa được phát hiện.

Khi cấu trúc dự án yêu cầu quét nhiều package khác nhau, có thể chỉ định rõ:

```java
@SpringBootApplication(scanBasePackages = {
    "com.example.identity",
    "com.example.shared.directory"
})
public class IdentityApplication { /* ... */ }
```

Đây là minh họa cách cấu hình component scan; mã thực tế cần có import và phương thức `main` như ví dụ trước. `scanBasePackages` điều khiển **component scanning**, không tự thay thế mọi cơ chế quét Spring Data repository/entity của các mô-đun dữ liệu.

### 4.2. Spring Data LDAP repository có vùng quét riêng

Nếu ứng dụng sử dụng **Spring Data LDAP**, có thể bật phát hiện LDAP repository bằng `@EnableLdapRepositories` và chỉ rõ `basePackages`:

```java
package com.example.identity.config;

import org.springframework.context.annotation.Configuration;
import org.springframework.data.ldap.repository.config.EnableLdapRepositories;

@Configuration
@EnableLdapRepositories(
    basePackages = "com.example.identity.directory.repository"
)
public class LdapRepositoryConfiguration {
}
```

Để dùng annotation này, dự án cần dependency **Spring Data LDAP** tương ứng với phiên bản Spring đang chạy; `LdapTemplate` thuộc Spring LDAP không đồng nghĩa dự án đã có Spring Data LDAP repositories. Annotation trên yêu cầu Spring tìm các repository interface trong **package Java được chỉ định**, chẳng hạn:

```java
package com.example.identity.directory.repository;

import org.springframework.data.ldap.repository.LdapRepository;
import com.example.identity.directory.model.Person;

public interface PersonRepository extends LdapRepository<Person> {
}
```

Ví dụ giả định `Person` là lớp ODM đã ánh xạ hợp lệ theo schema và có trường DN định danh, và dự án có các dependency Spring Data LDAP cần thiết. Base package ở `@EnableLdapRepositories` chỉ ảnh hưởng **việc phát hiện repository interface**, không biến package đó thành `ou=people` hoặc gốc LDAP. Cách cấu hình repository tự động của Spring Boot phụ thuộc phiên bản và dependency; không nên bật cùng lúc nhiều cấu hình tạo trùng repository bean.

### 4.3. ODM và base package liên quan thế nào?

Một lớp ODM có thể dùng `@Entry(base = "ou=people", objectClasses = ...)` để mô tả loại entry và nhánh LDAP mà lớp ánh xạ đến:

```java
package com.example.identity.directory.model;

import javax.naming.Name;
import org.springframework.ldap.odm.annotations.Attribute;
import org.springframework.ldap.odm.annotations.Entry;
import org.springframework.ldap.odm.annotations.Id;

@Entry(base = "ou=people", objectClasses = {
    "top", "person", "organizationalPerson", "inetOrgPerson"
})
public class Person {
    @Id
    private Name dn;

    @Attribute(name = "cn")
    private String commonName;

    @Attribute(name = "sn")
    private String surname;

    // Getter/setter hoặc cách truy cập thuộc tính phù hợp với mapper.
}
```

Đoạn `@Entry(base = "ou=people")` ở đây mô tả **base DN tương đối cho ánh xạ LDAP**, khác với `@EnableLdapRepositories(basePackages = "...")` mô tả **vị trí package Java**. Cả hai có từ *base* nhưng phục vụ những chức năng khác nhau. Domain class không phải repository interface; Spring Data tìm repository qua vùng quét repository, sau đó sử dụng thông tin ánh xạ của domain class liên quan. Cách ánh xạ, yêu cầu constructor và API repository phụ thuộc phiên bản dự án.

## 5. Cấu hình `LdapContextSource` bằng Java Config

Ví dụ sau cấu hình kết nối LDAP và `LdapTemplate` trong Spring Framework. Các giá trị được đọc từ cấu hình môi trường để việc triển khai ở local, test và production không cần sửa mã:

```java
package com.example.identity.config;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.core.support.LdapContextSource;

@Configuration
public class LdapConfiguration {

    @Bean
    public LdapContextSource ldapContextSource(
            @Value("${app.ldap.url}") String url,
            @Value("${app.ldap.base}") String base,
            @Value("${app.ldap.bind-dn}") String bindDn,
            @Value("${app.ldap.bind-password}") String password) {

        LdapContextSource contextSource = new LdapContextSource();
        contextSource.setUrl(url);
        contextSource.setBase(base);
        contextSource.setUserDn(bindDn);
        contextSource.setPassword(password);
        return contextSource;
    }

    @Bean
    public LdapTemplate ldapTemplate(LdapContextSource ldapContextSource) {
        return new LdapTemplate(ldapContextSource);
    }
}
```

```yaml
# application.yml
app:
  ldap:
    url: ${LDAP_URL:ldaps://ldap.example.org:636}
    base: dc=example,dc=org
    bind-dn: ${LDAP_BIND_DN}
    bind-password: ${LDAP_BIND_PASSWORD}
```

Spring quản lý vòng đời bean `LdapContextSource` và khởi tạo các tài nguyên cần thiết theo hợp đồng của implementation. Khi dùng template, ứng dụng không tự tạo/đóng `DirContext` cho từng thao tác thông thường. Các thư viện phía dưới vẫn là JNDI/LDAP, nên thao tác trên server có thể thất bại vì TLS, bind, schema hoặc quyền truy cập.

Các giá trị cấu hình có ý nghĩa độc lập:

```text
app.ldap.url       -> server nào, giao thức và cổng nào?
app.ldap.base      -> gốc LDAP nào cho DN tương đối?
app.ldap.bind-dn   -> kết nối dưới danh tính nào?
app.ldap.bind-password -> bí mật của danh tính bind là gì?
basePackages       -> lớp Java/repository nào được Spring phát hiện?
```

Tài khoản bind nên chỉ có quyền cần thiết; ví dụ service chỉ tìm người dùng không cần quyền xóa hay sửa schema. Tài khoản dịch vụ không đồng nghĩa với tài khoản người dùng được xác thực trong quy trình đăng nhập.

### 5.1. Cấu hình bằng Spring Boot properties

Với Spring Boot và dependency LDAP starter thích hợp, có thể dùng cơ chế cấu hình LDAP của Boot thay cho bean thủ công, ví dụ:

```yaml
spring:
  ldap:
    urls: ${LDAP_URL:ldaps://ldap.example.org:636}
    base: dc=example,dc=org
    username: ${LDAP_BIND_DN}
    password: ${LDAP_BIND_PASSWORD}
```

`spring.ldap.urls` và `spring.ldap.base` thuộc nhóm cấu hình kết nối Boot, không phải `scanBasePackages`. Việc Boot có tạo bean `ContextSource`/`LdapTemplate` như mong đợi phụ thuộc dependency, auto-configuration, các bean người dùng đã khai báo và phiên bản. Khi dùng Java Config ở phần trước, các tên `app.ldap.*` là property **do ứng dụng tự định nghĩa**; chúng không tự động là property chuẩn của Spring Boot.

Không trộn nhiều cách cấu hình mà không biết bean nào được tiêm vào repository. Nếu hệ thống có nhiều LDAP server hoặc nhiều base DN, nên đặt tên bean/`@Qualifier` rõ ràng để một repository không vô tình truy vấn nhầm thư mục.

## 6. Từ cấu hình đến một truy vấn thực tế

Giả sử có các entry:

```ldif
dn: uid=alice,ou=people,dc=example,dc=org
objectClass: inetOrgPerson
uid: alice
cn: Alice Nguyen
sn: Nguyen
mail: alice@example.org
```

Ứng dụng cần tìm người dùng theo `uid`. Với `LdapTemplate`, ta có thể tạo truy vấn từ DN tương đối và filter builder:

```java
package com.example.identity.directory;

import java.util.List;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.SearchScope;
import org.springframework.stereotype.Repository;
import static org.springframework.ldap.query.LdapQueryBuilder.query;

@Repository
public class DirectoryUserLookup {
    private final LdapTemplate ldapTemplate;

    public DirectoryUserLookup(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<String> findNamesByUid(String uid) {
        if (uid == null || uid.isBlank()) {
            throw new IllegalArgumentException("uid must not be blank");
        }

        LdapQuery ldapQuery = query()
                .base("ou=people")
                .searchScope(SearchScope.SUBTREE)
                .attributes("cn")
                .where("uid").is(uid);

        return ldapTemplate.search(ldapQuery,
                (AttributesMapper<String>) attributes -> {
                    if (attributes.get("cn") == null) {
                        return "";
                    }
                    return String.valueOf(attributes.get("cn").get());
                });
    }
}
```

Với `ContextSource.base = dc=example,dc=org`, code trên tìm trong `ou=people,dc=example,dc=org`. `SearchScope.SUBTREE` duyệt chính OU và các nhánh con; filter `.where("uid").is(uid)` chọn những entry có giá trị `uid` phù hợp. Query builder xử lý escaping **giá trị filter**; nó không tự xác nhận quyền truy cập, schema hay tính duy nhất toàn cục của `uid`.

Khi không có kết quả, thường nhận danh sách rỗng. Khi base DN không tồn tại, bind bị từ chối hoặc mất kết nối/TLS lỗi, có thể nhận ngoại lệ Spring LDAP. Không nên nuốt mọi ngoại lệ và trả rỗng vì như vậy sẽ che giấu lỗi vận hành.

Nếu dùng Spring Data LDAP repository hoặc ODM, base package chỉ quyết định lớp/đối tượng nào được ứng dụng phát hiện; khi thực hiện tìm kiếm thực tế, vẫn phải chọn base DN, scope và filter như với `LdapTemplate`.

## 7. Kiểm chứng URL và base DN bằng `ldapsearch`

Trước khi chạy code Spring, nên thử endpoint và nhánh thư mục với công cụ dòng lệnh. Với tài khoản chỉ đọc và máy chủ thử nghiệm:

```bash
ldapsearch -LLL -x \
  -H "ldaps://ldap.example.org:636" \
  -D "cn=directory-reader,ou=system,dc=example,dc=org" -W \
  -b "ou=people,dc=example,dc=org" -s sub \
  "(&(objectClass=inetOrgPerson)(uid=alice))" \
  dn cn uid
```

`-H` dùng URL đầy đủ, `-D` là bind DN, `-b` là **base DN đầy đủ** của lệnh `ldapsearch`, `-s sub` là subtree search. `-W` yêu cầu nhập mật khẩu tương tác, tránh ghi mật khẩu trên dòng lệnh. Kết quả nên có DN của entry `alice` nếu dữ liệu, quyền và filter phù hợp.

Chú ý khác biệt giữa hai cách biểu diễn base:

```text
ldapsearch -b "ou=people,dc=example,dc=org"    # DN đầy đủ
LdapTemplate .base("ou=people")                  # DN tương đối nếu ContextSource.base là dc=example,dc=org
```

Nếu `ldapsearch` thành công nhưng Spring không tìm thấy entry, đối chiếu **base được cấu hình trong bean đang thực sự được tiêm**, DN tương đối truyền cho template, filter, tài khoản bind và scope. Sự khác biệt có thể nằm ở cấu hình hoặc quyền, không nhất thiết nằm ở network.

### 7.1. Dùng Root DSE để khám phá naming context

Khi chưa biết hậu tố DN, có thể hỏi Root DSE bằng DN rỗng và scope `base`:

```bash
ldapsearch -LLL -x \
  -H "ldaps://ldap.example.org:636" \
  -b "" -s base \
  "(objectClass=*)" namingContexts
```

Ví dụ có thể trả `namingContexts: dc=example,dc=org`. Máy chủ có thể giới hạn thuộc tính hiển thị ẩn danh; khi cần, dùng tài khoản được cấp quyền và `-W`. Đừng mặc định naming context đầu tiên là nhánh người dùng chính, nhất là với thư mục có schema/configuration partitions hoặc nhiều miền.

Một điểm khác biệt quan trọng: `ldapTemplate.lookup("")` trên template đã cấu hình `base = dc=example,dc=org` thông thường tra cứu **entry tại base của context**, không phải Root DSE. Muốn đọc Root DSE tuyệt đối, có thể cấu hình một `ContextSource` riêng không đặt base hoặc dùng cách truy cập được provider hỗ trợ để tham chiếu DN rỗng ở gốc máy chủ.

## 8. Kiểm chứng base package mà không cần truy cập LDAP

Khi ứng dụng không tạo bean repository hoặc service, hãy kiểm tra **cấu trúc package và cấu hình quét** trước. Ví dụ class chạy ứng dụng đặt tại:

```text
com.example.identity.IdentityApplication
```

Trong trường hợp mặc định, Spring component scanning theo phạm vi của package này và các package con. Một `@Repository` nằm ở `com.example.identity.directory` sẽ được thấy; một `@Repository` nằm ở `com.other.directory` có thể không được thấy nếu không cấu hình quét thêm.

Nếu sử dụng Spring Data LDAP, `@EnableLdapRepositories(basePackages = "com.example.identity.directory.repository")` yêu cầu tìm repository interface trong package đó và các package con. Nếu tên package sai hoặc interface nằm ngoài vùng quét, bean repository có thể không được tạo. **Đây là lỗi wiring của Spring container**, khác với LDAP `noSuchObject` khi server không tìm thấy DN.

### Bảng chẩn đoán ba loại cấu hình

| Biểu hiện | Cấu hình cần kiểm tra trước | Vì sao? |
| --- | --- | --- |
| `UnknownHostException`, connection refused hoặc TLS handshake lỗi | URL/hostname/port/chứng chỉ/truststore | Chưa truy cập server LDAP đúng cách |
| LDAP result `32` / `noSuchObject` | Base DN, DN tương đối, entry cha và quyền | Server không tìm được DN được yêu cầu hoặc không thể hiển thị nó |
| Search trả rỗng dù server hoạt động | Base DN, scope, filter, ACL và dữ liệu thực tế | Có thể truy vấn sai nhánh hoặc không có entry phù hợp |
| `NoSuchBeanDefinitionException` cho `LdapTemplate` | Dependency, auto-configuration, `@Configuration` và component scan | Chưa đăng ký bean vào Spring container |
| `No qualifying bean` cho Spring Data LDAP repository | `@EnableLdapRepositories`, basePackages và dependency | Repository interface chưa được phát hiện/khởi tạo |
| Có nhiều bean `ContextSource` không rõ bean nào được chọn | Bean name/`@Qualifier`, auto-configuration | Có thể truy cập nhầm server hoặc base DN |
| LDAP result `50` / `insufficientAccessRights` | Bind DN và ACL | Kết nối thành công nhưng danh tính không có quyền thao tác |

Những nhóm lỗi này có thể xuất hiện đồng thời. Ví dụ, sau khi sửa base package để Spring tạo được repository, truy vấn vẫn có thể thất bại vì base DN sai. Mỗi lần sửa cần kiểm tra đúng tầng để tránh thay đổi các tham số không liên quan.

## 9. Bảo mật và cấu hình môi trường

### 9.1. TLS và chứng chỉ

Khi dùng `ldaps://`, máy khách phải xác minh chuỗi chứng chỉ và tên máy chủ. Nếu truststore thiếu CA hoặc hostname không khớp, nên sửa chứng chỉ, endpoint hoặc truststore. Không vô hiệu hóa TLS hostname verification để làm cho ví dụ chạy bằng mọi giá. Khi dùng StartTLS, cần đảm bảo nâng cấp trước thao tác gửi mật khẩu simple bind và đánh giá tương tác với tái sử dụng connection.

### 9.2. Mật khẩu và quyền tối thiểu

Đừng lưu mật khẩu LDAP trong repository Git hoặc log. Dùng biến môi trường, secret manager hoặc cơ chế cấp bí mật được quản trị. Tài khoản chỉ tra cứu người dùng không cần quyền thay đổi entry hay schema. Nếu có chức năng cập nhật, quyền ghi nên giới hạn theo OU và thuộc tính cần thiết. Base DN chỉ là phạm vi logic thuận tiện; **phân quyền vẫn do ACL của LDAP server quyết định**.

### 9.3. Timeout, pooling và hiệu năng

Một URL đúng không bảo đảm truy vấn nhanh. Cần cấu hình timeout kết nối/đọc phù hợp với JNDI provider, giới hạn phạm vi tìm kiếm và số lượng kết quả; có thể dùng paging khi server hỗ trợ. Pooling có thể giảm chi phí tạo context trong workload phù hợp, nhưng cần kiểm tra tương tác với TLS/StartTLS và các danh tính bind. Không chia sẻ context đã bind với người dùng này cho request của người dùng khác.

Không nên dùng pooling để che giấu một truy vấn với base quá rộng hoặc filter không được index. Nếu hệ thống dùng nhiều LDAP URL để failover, cần xác định chính sách retry, replication và xử lý trường hợp không biết thao tác ghi đã thành công hay chưa.

## 10. Bài thực hành: cấu hình và xác minh ba “vị trí”

**Bối cảnh:** Một ứng dụng Spring Boot cần tìm `uid` của người dùng trong nhánh `ou=people` của thư mục LDAP thử nghiệm. Mã Java đặt ở `com.example.identity`; LDAP server cung cấp naming context `dc=example,dc=org`.

1. **Xác định URL:** cấu hình `ldaps://ldap.example.org:636`, kiểm tra DNS, cổng, chứng chỉ và truststore. Không gửi mật khẩu khi kết nối chưa được bảo vệ.
2. **Xác định base DN:** đọc Root DSE hoặc tài liệu quản trị; chọn `dc=example,dc=org` cho `ContextSource` và `ou=people` làm search base tương đối. Viết ra DN đầy đủ của truy vấn để kiểm tra.
3. **Đặt cấu hình:** dùng `app.ldap.url`, `app.ldap.base`, `app.ldap.bind-dn`, `app.ldap.bind-password` với bean Java Config, hoặc nhóm `spring.ldap.*` theo cấu hình Boot tương ứng; không tạo trùng bean vô ý.
4. **Chạy truy vấn:** tạo `LdapTemplate` từ `ContextSource`, dùng `query().base("ou=people").where("uid").is("alice")` và so sánh với lệnh `ldapsearch -b "ou=people,dc=example,dc=org"`.
5. **Kiểm tra base package:** đặt class `DirectoryUserLookup` trong package con của application class. Xác nhận Spring tạo bean và tiêm `LdapTemplate` thành công.
6. **Kiểm tra repository scanning:** nếu dùng Spring Data LDAP, đặt repository interface vào `com.example.identity.directory.repository` và cấu hình `@EnableLdapRepositories` tương ứng. Cố ý cấu hình sai tên package trong môi trường test để quan sát lỗi bean không tồn tại; khôi phục cấu hình đúng.
7. **Phân biệt lỗi:** thử base LDAP không tồn tại, thử URL không truy cập được và thử base package không chứa repository. Ghi lại biểu hiện và khẳng định chúng thuộc ba tầng khác nhau.
8. **Kiểm tra quyền:** chạy truy vấn bằng tài khoản chỉ đọc và thử một thao tác ghi vào entry thử nghiệm theo quy trình cho phép; xác định cách LDAP server phản hồi ACL.
9. **Kiểm thử môi trường:** chạy cùng cấu hình code với các giá trị URL/base/credentials riêng cho test, không sử dụng dữ liệu tài khoản thật; bảo đảm log không chứa mật khẩu và thông tin nhạy cảm.

### Câu hỏi tự kiểm tra

1. Vì sao `ldaps://ldap.example.org:636` không cho biết phải tìm người dùng dưới OU nào?
2. Khi `ContextSource.base = dc=example,dc=org`, `.base("ou=people")` tương ứng với DN đầy đủ nào?
3. Vì sao `@EnableLdapRepositories(basePackages = "com.example.identity.directory.repository")` không thay thế `ContextSource.setBase("dc=example,dc=org")`?
4. Nếu Spring báo không tìm thấy `PersonRepository` bean nhưng `ldapsearch` vẫn chạy tốt, nên kiểm tra yếu tố gì trước?
5. Vì sao `ldapTemplate.lookup("")` trên context đã đặt base có thể không đọc Root DSE?
6. Một server URL có TLS hợp lệ đã đủ khẳng định ứng dụng có quyền đọc và ghi mọi entry chưa? Vì sao?
7. Khi dùng hai `ContextSource` trỏ hai máy chủ khác nhau, cần làm gì để repository luôn nhận đúng bean?

## 11. Ghi nhớ

**Server URL** xác định địa chỉ và phương thức kết nối với LDAP; **base DN** xác định gốc logic cho các DN tương đối trong truy vấn; **base package** xác định vùng mã Java mà Spring quét để đăng ký component hoặc repository. Cả ba cần được cấu hình đúng, nhưng chúng thuộc **những tầng độc lập**. `LdapContextSource` kết nối URL, base DN và danh tính bind để cung cấp context; `LdapTemplate`, `LdapClient` hoặc ODM sử dụng context đó cho các thao tác LDAP. Khi kết nối và tìm kiếm thất bại, hãy chẩn đoán chính xác tầng mạng/TLS, cây DN/filter/ACL hay cơ chế quét bean/repository. Kết hợp kiểm thử bằng `ldapsearch`, xác minh bean Spring, cấu hình bí mật an toàn và phân quyền tối thiểu giúp triển khai Spring LDAP rõ ràng, dễ bảo trì và đáng tin cậy.
