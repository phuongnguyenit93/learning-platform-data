# Cấu hình ContextSourceTransactionManager

Khi một chức năng nghiệp vụ cần thay đổi **nhiều entry LDAP**, lỗi ở thao tác sau có thể để lại directory ở trạng thái cập nhật dở dang. Ví dụ: ứng dụng tạo entry nhân viên, sửa một thuộc tính rồi gặp ngoại lệ. Spring LDAP cung cấp `ContextSourceTransactionManager` để **thử hoàn tác** các thay đổi đã thực hiện bằng những thao tác LDAP ngược lại, hay còn gọi là **compensating transactions** (giao dịch bù trừ).

Bài học thuộc chương **Giao dịch bù trừ** của mô-đun `SPRING_DATA_LDAP`. Nội dung tập trung vào cấu hình đúng `ContextSourceTransactionManager`, `TransactionAwareContextSourceProxy` và `LdapTemplate`; sử dụng `@Transactional` ở tầng service; quan sát commit/rollback; kết nối với repository, schema, DN, filter an toàn và kiểm thử trên directory thật.

**Giới hạn quan trọng:** đây là cơ chế **phía ứng dụng**, không phải giao dịch ACID hoặc khóa/rollback nguyên tử do LDAP server cung cấp. Nó không đảm bảo rollback khi mất kết nối, gặp lỗi quyền truy cập hay có thay đổi đồng thời. LDAPv3 cơ bản không có cơ chế transaction nhiều thao tác phổ quát; RFC 5805 mô tả một *LDAP Transactions Extension* tùy chọn, nhưng `ContextSourceTransactionManager` **không dựa vào extension đó**.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích ý nghĩa **compensation** và phân biệt nó với transaction của cơ sở dữ liệu quan hệ.
2. Hiểu cách Spring LDAP ghi nhận thao tác và tạo thao tác ngược để rollback.
3. Cấu hình đúng ba thành phần: **ContextSource gốc**, **TransactionAwareContextSourceProxy** và **ContextSourceTransactionManager**.
4. Dùng `@Transactional(transactionManager = "ldapTransactionManager")` để xác định ranh giới giao dịch ở tầng service.
5. Nêu khác biệt API cấu hình giữa Spring LDAP 3.x và phiên bản mới hơn, tránh dùng ví dụ constructor không tương thích.
6. Thiết kế kiểm thử tích hợp cho commit, rollback, ngoại lệ, thay đổi đồng thời, mất kết nối và quyền LDAP.
7. Chọn khi nào cần cơ chế bù trừ, khi nào cần idempotency, trạng thái chờ và đối soát bổ sung.

## 2. Tình huống cần giao dịch bù trừ

Giả sử một ứng dụng quản lý nhân viên có cây LDAP:

~~~text
dc=example,dc=org
├── ou=people
│   ├── uid=lan
│   └── uid=minh
└── ou=groups
    └── cn=engineering
~~~

Để đăng ký nhân viên, nghiệp vụ muốn:

1. Tạo `uid=an,ou=people,dc=example,dc=org` với object class `inetOrgPerson`.
2. Ghi nhận `description` hoặc cập nhật một entry liên quan.
3. Chỉ xác nhận thành công khi toàn bộ những bước bắt buộc kết thúc.

Nếu bước 2 thất bại sau khi bước 1 đã ghi xuống LDAP, chỉ dựa vào xử lý ngoại lệ trong Java sẽ không tự xóa entry vừa tạo. Với `ContextSourceTransactionManager`, Spring có thể ghi nhận **bước 1 tạo entry** rồi cố thực hiện **bước xóa entry** khi rollback.

Ví dụ kết quả mong đợi trong trường hợp bù trừ thành công:

| Mốc | Trạng thái directory |
| --- | --- |
| Trước khi gọi service | Chưa có `uid=an`. |
| Sau LDAP `bind` tạo entry | `uid=an` đã tồn tại. |
| Bước sau phát sinh ngoại lệ | Spring bắt đầu rollback logic. |
| Bù trừ thành công | Entry vừa tạo bị xóa; trạng thái quay về gần trạng thái trước yêu cầu. |
| Bù trừ thất bại | Có thể còn entry dở dang; cần đối soát và xử lý thủ công hoặc tự động. |

**Phân biệt hai từ dễ nhầm:** Trong `LdapTemplate`, `bind(dn, obj, attrs)` là thao tác **tạo entry**, còn `unbind(dn)` là thao tác **xóa entry**. Chúng **khác** với LDAP *BindRequest* dùng để xác thực kết nối và *UnbindRequest* dùng để kết thúc kết nối.

## 3. ContextSourceTransactionManager hoạt động thế nào?

`ContextSourceTransactionManager` triển khai `PlatformTransactionManager` của Spring. Khi gọi một phương thức service được quản lý bằng transaction, nó phối hợp với `TransactionAwareContextSourceProxy` để ghi nhận các thao tác LDAP có thay đổi dữ liệu, từ đó chuẩn bị thao tác hoàn tác tương ứng.

~~~mermaid
sequenceDiagram
    autonumber
    participant Caller as Controller / Scheduler
    participant Tx as Spring @Transactional
    participant Proxy as TransactionAwareContextSourceProxy
    participant Dir as LDAP Directory
    Caller->>Tx: Gọi service nghiệp vụ
    Tx->>Proxy: Bắt đầu ngữ cảnh giao dịch
    Proxy->>Dir: LDAP Modify / Add / Delete / Rename
    Dir-->>Proxy: Kết quả từng thao tác
    Note over Proxy: Ghi nhận thông tin để hoàn tác
    alt Toàn bộ logic thành công
        Tx->>Proxy: Commit logic
        Note over Proxy: Hoàn tất thao tác còn chờ / dọn dữ liệu tạm
    else Ngoại lệ kích hoạt rollback
        Tx->>Proxy: Rollback logic
        Proxy->>Dir: Thao tác LDAP bù trừ
        Dir-->>Proxy: Thành công hoặc thất bại bù trừ
    end
    Tx-->>Caller: Trả kết quả / ném ngoại lệ
~~~

Thư viện cung cấp các `CompensatingTransactionOperationRecorder` và `CompensatingTransactionOperationExecutor` để quản lý thông tin trước khi ghi, việc thực hiện thao tác chính và việc commit/rollback. **Server LDAP không biết rằng nhiều request này nằm trong một transaction logic của Spring**.

### Các loại thay đổi và phương án bù trừ

| Thao tác ở Spring LDAP | Ví dụ thao tác ngược | Điểm cần kiểm chứng |
| --- | --- | --- |
| `LdapTemplate.bind(...)` (tạo entry) | `unbind` entry đã tạo. | Phải đủ quyền xóa entry; entry có thể đã bị tham chiếu hoặc sửa từ nơi khác. |
| `modifyAttributes(...)` | Phục hồi giá trị thuộc tính cũ đã ghi nhận. | Có thể thất bại khi thiếu quyền đọc giá trị cũ hoặc có thay đổi đồng thời. |
| `rename(oldDn, newDn)` | Rename ngược về `oldDn`. | DN cũ phải còn khả dụng; cần quyền tại nhánh liên quan. |
| `unbind(dn)` (xóa entry) | Có thể tạm **rename** entry để rollback bằng cách rename ngược. | Tên tạm, ACL và cấu trúc cây cần tương thích. |
| `rebind(dn, ...)` (thay entry) | Có thể dùng entry gốc được đổi tên tạm để phục hồi. | Tên tạm có thể bị trùng; thay đổi liên quan của client khác không được cô lập. |

Với `unbind`/`rebind`, việc lưu mọi thuộc tính cũ để xóa rồi tạo lại **không phải lúc nào khả thi**. Vì vậy bộ quản lý bù trừ có thể **đổi DN cũ sang một DN tạm**, và chỉ xóa hẳn khi commit; khi rollback thì rename ngược. Đây là lý do cần hiểu `TempEntryRenamingStrategy` ở phần sau.

### Không có ACID thực sự

- **Atomicity:** mọi thao tác LDAP thành phần vẫn có thể đã được server chấp nhận trước lỗi; bù trừ chỉ là một **nỗ lực** phục hồi.
- **Consistency:** schema và ACL của directory vẫn được kiểm tra cho từng thao tác; chúng không tự đảm bảo toàn bộ quy tắc nghiệp vụ.
- **Isolation:** transaction khác có thể thấy trạng thái trung gian hoặc đổi cùng entry.
- **Durability:** các thao tác đã được chấp nhận là dữ liệu thực trên server; rollback chỉ thành công nếu các request bù trừ tiếp theo thực thi được.

Do đó `@Transactional` trên một service LDAP **không tương đương** `@Transactional` với `DataSourceTransactionManager` hoặc `JpaTransactionManager`.

## 4. Kiến trúc cấu hình đúng

Có ba đối tượng giữ vai trò riêng:

~~~mermaid
flowchart TD
    A["LdapContextSource (gốc)"] --> B["TransactionAwareContextSourceProxy"]
    B --> C["LdapTemplate dùng để đọc/ghi"]
    C --> D["Spring Data LDAP Repository hoặc Service"]
    A --> E["ContextSourceTransactionManager"]
    F["@Transactional trên Service"] --> E
    F --> D
~~~

**Quy tắc quan trọng nhất:**

- `ContextSourceTransactionManager` nhận **ContextSource gốc** (target).
- `LdapTemplate` nhận **TransactionAwareContextSourceProxy** bao quanh target.
- Mọi thao tác cần bù trừ phải đi qua `LdapTemplate`/repository thực sự dùng **proxy đó**, trong cùng ranh giới giao dịch.
- Khi có nhiều transaction manager, `@Transactional` phải chỉ rõ manager dành cho LDAP.

Nếu `LdapTemplate` dùng thẳng target, các thao tác có thể bỏ qua cơ chế ghi nhận bù trừ; nếu toàn bộ ứng dụng vô tình dùng một context source khác, cấu hình transaction manager tồn tại nhưng không có hiệu quả mong muốn.

## 5. Dependency và cấu hình kết nối

Ví dụ giả định Java 17+, Spring Boot 3.x, Spring LDAP 3.x và Spring Data LDAP cùng một bộ phiên bản tương thích. Dependency cần có:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-ldap</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
~~~

Đây là các phần tử nằm trong `<dependencies>` của `pom.xml` hiện có. Spring Boot quản lý các phiên bản thư viện theo BOM; không tự ghép Spring LDAP Core và Spring Transaction từ các nhánh phiên bản khác nhau.

Ví dụ `application.yml`:

~~~yaml
spring:
  ldap:
    urls: ldaps://ldap.example.org:636
    base: dc=example,dc=org
    username: cn=svc-writer,ou=service,dc=example,dc=org
    password: "${LDAP_BIND_PASSWORD}"
~~~

Mật khẩu đến từ biến môi trường `LDAP_BIND_PASSWORD` của **tiến trình Java**. Với LDAPS, JVM phải tin cậy chứng chỉ và xác minh tên máy chủ; nếu sử dụng StartTLS thì thương lượng TLS **thành công trước Simple Bind**. Không nên chạy giao dịch gồm nhiều thao tác ghi bằng một tài khoản chỉ có quyền Search.

**Điểm thực tiễn:** `spring.ldap.*` giúp Spring Boot khởi tạo `LdapContextSource` trong các cấu hình thông thường. Nhưng để kiểm soát **target + proxy + manager** của bài học, phần sau khai báo tường minh các bean. Cần tránh tạo hai bộ `LdapTemplate`/`ContextSource` song song rồi gọi nhầm bộ không có transaction.

## 6. Cấu hình Java cho Spring LDAP 3.x

Tệp minh họa `config/LdapCompensationConfig.java`:

~~~java
package com.example.directory.config;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;
import org.springframework.ldap.core.ContextSource;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.core.support.LdapContextSource;
import org.springframework.ldap.transaction.compensating.manager.ContextSourceTransactionManager;
import org.springframework.ldap.transaction.compensating.manager.TransactionAwareContextSourceProxy;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@Configuration
@EnableTransactionManagement
public class LdapCompensationConfig {

    // ContextSource gốc: tạo các DirContext vật lý.
    @Bean("ldapTargetContextSource")
    public LdapContextSource ldapTargetContextSource(
            @Value("${spring.ldap.urls}") String ldapUrl,
            @Value("${spring.ldap.base}") String baseDn,
            @Value("${spring.ldap.username}") String bindDn,
            @Value("${spring.ldap.password}") String password) {

        LdapContextSource target = new LdapContextSource();
        target.setUrl(ldapUrl);
        target.setBase(baseDn);
        target.setUserDn(bindDn);
        target.setPassword(password);
        // Spring gọi afterPropertiesSet khi khởi tạo bean.
        return target;
    }

    // ContextSource cho mọi LdapTemplate/repository cần bù trừ.
    @Bean("contextSource")
    @Primary
    public ContextSource contextSource(
            @Qualifier("ldapTargetContextSource") ContextSource target) {
        return new TransactionAwareContextSourceProxy(target);
    }

    @Bean("ldapTemplate")
    public LdapTemplate ldapTemplate(
            @Qualifier("contextSource") ContextSource contextSource) {
        return new LdapTemplate(contextSource);
    }

    // Spring LDAP 3.x: setter-based configuration.
    @Bean("ldapTransactionManager")
    public PlatformTransactionManager ldapTransactionManager(
            @Qualifier("ldapTargetContextSource") ContextSource target) {
        ContextSourceTransactionManager manager =
                new ContextSourceTransactionManager();
        manager.setContextSource(target);
        return manager;
    }
}
~~~

Ở đây tên bean và `@Qualifier` **có ý nghĩa**:

| Bean | Đối tượng thực tế | Được dùng bởi |
| --- | --- | --- |
| `ldapTargetContextSource` | `LdapContextSource` gốc | `ContextSourceTransactionManager`; target của proxy |
| `contextSource` | `TransactionAwareContextSourceProxy` | `LdapTemplate` và các thao tác LDAP cần bù trừ |
| `ldapTemplate` | `LdapTemplate(proxy)` | Service và repository khi đã nối đúng |
| `ldapTransactionManager` | `ContextSourceTransactionManager(target)` | `@Transactional(transactionManager = "ldapTransactionManager")` |

`@Primary` trên proxy giúp tránh trường hợp có hai bean `ContextSource` mà một thành phần tự động inject nhầm target. Trong dự án thật, kiểm tra **bean nào được Spring Data LDAP repository sử dụng**; cấu hình custom có thể cần chỉnh cách repository nhận `LdapTemplate`. Nếu chưa kiểm chứng wiring, nên thử giao dịch bằng `LdapTemplate` tường minh trước khi chuyển sang repository.

### 6.1. Khác biệt khi dùng Spring LDAP 4.1+

Ở các bản API mới hơn, constructor nhận `ContextSource` được khuyến nghị; constructor không tham số và `setContextSource(...)` được đánh dấu deprecated. Khi dự án đang dùng phiên bản có constructor mới, **thay riêng phương thức tạo transaction manager** bằng:

~~~java
@Bean("ldapTransactionManager")
public PlatformTransactionManager ldapTransactionManager(
        @Qualifier("ldapTargetContextSource") ContextSource target) {
    return new ContextSourceTransactionManager(target);
}
~~~

Giữ nguyên target/proxy/template trong cấu hình trước đó. **Đừng ghép hai cách tạo bean cùng lúc.** Nếu dùng Spring LDAP 3.x mà chưa có constructor nhận `ContextSource`, giữ cách setter tương ứng. Kiểm tra API đúng phiên bản `spring-ldap-core` mà dự án biên dịch.

### 6.2. Vì sao không cần tự đóng context trong mỗi thao tác của LdapTemplate?

`LdapTemplate` tự quản lý lấy và giải phóng `DirContext`. `TransactionAwareContextSourceProxy` đảm bảo context gắn với transaction không bị đóng giữa chừng và theo dõi các thao tác có thay đổi. Tự lấy `DirContext` từ target rồi đóng nó giữa service có thể **vượt qua** proxy bù trừ.

Nếu dùng JNDI trực tiếp, phải bảo đảm các thao tác được thực hiện qua context do proxy cung cấp và xử lý vòng đời chính xác. Với các thao tác thông dụng, ưu tiên `LdapTemplate`.

## 7. Sử dụng @Transactional ở tầng service

Sau khi cấu hình, service có thể khai báo một **ranh giới giao dịch logic** cho nhiều thay đổi LDAP. Ví dụ tạo `inetOrgPerson` và cập nhật thuộc tính `description` của entry đó.

`service/PeopleProvisioningService.java`:

~~~java
package com.example.directory.service;

import java.util.regex.Pattern;
import javax.naming.Name;
import javax.naming.directory.Attributes;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.BasicAttributes;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;

import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PeopleProvisioningService {

    private static final Pattern UID =
            Pattern.compile("[a-z][a-z0-9._-]{2,31}");

    private final LdapTemplate ldapTemplate;

    public PeopleProvisioningService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    @Transactional(transactionManager = "ldapTransactionManager")
    public void createThenTag(String uid, boolean failAfterWriting) {
        if (uid == null || !UID.matcher(uid).matches()) {
            throw new IllegalArgumentException("Invalid uid");
        }

        // DN tương đối với spring.ldap.base=dc=example,dc=org.
        Name dn = LdapNameBuilder.newInstance("ou=people")
                .add("uid", uid)
                .build();

        Attributes attributes = new BasicAttributes(true);
        BasicAttribute objectClasses = new BasicAttribute("objectClass");
        objectClasses.add("top");
        objectClasses.add("person");
        objectClasses.add("organizationalPerson");
        objectClasses.add("inetOrgPerson");

        attributes.put(objectClasses);
        attributes.put("uid", uid);
        attributes.put("cn", "Demo " + uid);
        attributes.put("sn", "Demo");

        // LDAP bind theo nghĩa tạo entry, không phải đăng nhập.
        ldapTemplate.bind(dn, null, attributes);

        // Thao tác LDAP thứ hai trong cùng transaction logic.
        ModificationItem[] changes = {
            new ModificationItem(
                DirContext.REPLACE_ATTRIBUTE,
                new BasicAttribute("description", "created by lab"))
        };
        ldapTemplate.modifyAttributes(dn, changes);

        if (failAfterWriting) {
            throw new IllegalStateException("Simulated failure for rollback");
        }
    }
}
~~~

### Luồng commit

Khi `failAfterWriting=false`:

1. Spring mở transaction logic và giữ context liên quan.
2. `bind(...)` tạo entry người dùng có `cn`, `sn` và chuỗi `objectClass` hợp lệ.
3. `modifyAttributes(...)` gán `description`.
4. Method kết thúc bình thường; transaction manager thực hiện commit logic.
5. Entry vẫn tồn tại với `description: created by lab`.

### Luồng rollback

Khi `failAfterWriting=true`:

1. Hai thao tác có thể đã được LDAP server chấp nhận.
2. `IllegalStateException` là **unchecked exception** nên mặc định Spring đánh dấu rollback.
3. Transaction manager dùng các thông tin đã ghi để **cố** đảo ngược `modifyAttributes`, sau đó **cố** xóa entry được tạo bởi `bind`.
4. Nếu bù trừ thành công, search theo `uid` không còn trả entry mới.
5. Nếu bù trừ gặp lỗi, dữ liệu có thể không ở trạng thái ban đầu; cần thông báo/đối soát.

Phạm vi demo là **một entry** để dễ quan sát. Trong nghiệp vụ thật, một method có thể tạo người dùng và cập nhật nhóm; với các thao tác đó cần xem xét tham chiếu DN, quyền sửa nhóm và tác động của user khác đang đọc dữ liệu trung gian.

**Không coi ví dụ là bảo đảm “all-or-nothing”:** việc lệnh Java ném ngoại lệ không có nghĩa server LDAP chắc chắn đã xóa mọi dấu vết của các thao tác trước đó.

## 8. Các quy tắc khi dùng @Transactional

### 8.1. Chỉ rõ transaction manager

Trong một ứng dụng có cả JDBC/JPA và LDAP, thường xuất hiện nhiều bean quản lý transaction. Dùng:

~~~java
@Transactional(transactionManager = "ldapTransactionManager")
public void updateDirectory() {
    // Các thay đổi LDAP đi qua template/proxy đã cấu hình.
}
~~~

Nếu dùng `@Transactional` không ghi tên manager, Spring có thể chọn một manager mặc định dành cho database hoặc báo lỗi không xác định được bean. Khi đó các thay đổi LDAP không được quản lý như bạn kỳ vọng.

### 8.2. Spring AOP và self-invocation

Ví dụ sau dễ khiến annotation không được áp dụng:

~~~java
@Service
public class WrongExample {
    public void outer() {
        inner(); // Gọi trực tiếp cùng đối tượng, thường bỏ qua proxy.
    }

    @Transactional(transactionManager = "ldapTransactionManager")
    public void inner() {
        // Ghi LDAP ở đây có thể không nằm trong transaction.
    }
}
~~~

Hãy đặt `@Transactional` lên public method được gọi **qua Spring bean proxy**, thường là method service được controller hoặc service khác gọi. Một method tự gọi method khác của chính đối tượng có thể bỏ qua transaction advice trong chế độ proxy mặc định.

### 8.3. Quy tắc rollback theo loại ngoại lệ

Theo cấu hình Spring thông dụng, `RuntimeException` và `Error` kích hoạt rollback, còn **checked exception** không tự động kích hoạt theo mặc định. Nếu nghiệp vụ cần rollback khi checked exception được ném:

~~~java
@Transactional(
    transactionManager = "ldapTransactionManager",
    rollbackFor = Exception.class
)
public void provision() throws Exception {
    // ...
}
~~~

Đừng bắt và nuốt mọi ngoại lệ ngay trong transactional method rồi trả `false`: nếu phương thức kết thúc bình thường, transaction có thể được commit. Khi muốn kết thúc thất bại, hãy ném ngoại lệ có ý nghĩa hoặc đánh dấu rollback bằng cơ chế Spring phù hợp.

## 9. TempEntryRenamingStrategy khi xóa và thay thế entry

Spring LDAP có `TempEntryRenamingStrategy` phục vụ các thao tác như `unbind` và `rebind`. Chiến lược mặc định `DefaultTempEntryRenamingStrategy` thêm hậu tố vào phần tên gần entry nhất; ví dụ tên tạm có thể là:

~~~text
Gốc:     uid=lan,ou=people,dc=example,dc=org
Tạm:     uid=lan_temp,ou=people,dc=example,dc=org
~~~

Khi thao tác xóa xảy ra trong transaction logic:

~~~mermaid
sequenceDiagram
    participant S as Service
    participant Tx as Spring LDAP bù trừ
    participant LDAP as Directory
    S->>Tx: unbind(uid=lan)
    Tx->>LDAP: Rename uid=lan → uid=lan_temp
    alt Commit thành công
        Tx->>LDAP: Xóa entry tạm
    else Rollback thành công
        Tx->>LDAP: Rename uid=lan_temp → uid=lan
    end
~~~

### Cảnh báo khi dùng tên tạm

- Entry ở DN tạm **có thể xuất hiện trong Search** trước commit, khiến ứng dụng khác nhìn thấy dữ liệu trung gian.
- Các phép rename/xóa có thể yêu cầu quyền ACL ở cả DN cũ và mới.
- Tên tạm có thể trùng entry có sẵn hoặc vi phạm ràng buộc tên của schema.
- Với cây có **entry con**, rename/xóa cả subtree phức tạp hơn; không áp dụng mặc định cho xóa một nhánh lớn khi chưa kiểm thử.
- `DifferentSubtreeTempEntryRenamingStrategy` cho phép đặt tên tạm trong subtree khác theo cấu hình, nhưng phải tạo sẵn nhánh tạm, quản lý ACL và kiểm thử khả năng chuyển entry/subtree của server.

Có thể điều chỉnh renaming strategy bằng `manager.setRenamingStrategy(strategy)`. Chỉ thay đổi khi có lý do nghiệp vụ và đã thử đầy đủ các ca commit/rollback tương ứng; thay hậu tố không khắc phục sự thiếu isolation của cơ chế.

## 10. Phối hợp với Spring Data LDAP repository và ODM

`SPRING_DATA_LDAP` thường ánh xạ entry qua `@Entry`, `@Id`, `@Attribute` và truy cập bằng `LdapRepository`. Một entity người dùng có thể như sau:

~~~java
import javax.naming.Name;
import org.springframework.ldap.odm.annotations.Attribute;
import org.springframework.ldap.odm.annotations.Entry;
import org.springframework.ldap.odm.annotations.Id;

@Entry(
    base = "ou=people",
    objectClasses = {"top", "person", "organizationalPerson", "inetOrgPerson"}
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

    // Getter/setter tương ứng trong entity thật.
}
~~~

Repository:

~~~java
import org.springframework.data.ldap.repository.LdapRepository;

public interface DirectoryPersonRepository
        extends LdapRepository<DirectoryPerson> {
}
~~~

Nếu repository được cấu hình dùng **`LdapTemplate` gắn `TransactionAwareContextSourceProxy`** và service có ranh giới `@Transactional` đúng, các thay đổi đi qua lớp LDAP được proxy quản lý có thể tham gia cơ chế bù trừ. Hãy xác nhận bằng **integration test**, vì việc chỉ khai báo `@Transactional` trên một repository không chứng minh bộ bean đang sử dụng đúng context source.

Khi cần cập nhật vài thuộc tính cụ thể, `LdapTemplate.modifyAttributes(...)` giúp bạn kiểm soát những thay đổi được ghi nhận. Đặc biệt khi entity chứa thuộc tính đa giá trị hoặc thuộc tính được ứng dụng khác quản lý, tránh tải toàn bộ entity rồi lưu lại mà không hiểu cách ODM so sánh/ghi thuộc tính.

Với các thao tác Delete/Rename hoặc thay thế entry thông qua repository, hãy đối chiếu đường gọi thực tế với các thao tác LDAP được Spring LDAP proxy ghi nhận. Một phương thức repository có thể thực hiện nhiều lệnh LDAP nội bộ, nên kết quả bù trừ phải được xác minh trên directory.

## 11. Kiểm thử tích hợp commit và rollback

Để kiểm chứng transaction, cần một directory kiểm thử có schema `inetOrgPerson`, nhánh `ou=people,dc=example,dc=org`, tài khoản ghi giới hạn và TLS hợp lệ. Có thể dùng OpenLDAP container hoặc directory test tương đương; không dùng dữ liệu nhân sự thật.

Ví dụ JUnit 5 sử dụng Spring Boot Test:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;

@SpringBootTest
class LdapCompensationIntegrationTest {

    @Autowired
    private PeopleProvisioningService service;

    @Autowired
    private LdapTemplate ldapTemplate;

    private List<String> findByUid(String uid) {
        LdapQuery query = LdapQueryBuilder.query()
                .base("ou=people")
                .where("uid").is(uid);

        return ldapTemplate.search(
                query,
                (AttributesMapper<String>)
                    attrs -> (String) attrs.get("uid").get()
        );
    }

    @Test
    void rollbackTriesToRemoveCreatedEntry() {
        String uid = "txrollbackdemo";
        assertTrue(findByUid(uid).isEmpty());

        assertThrows(
            IllegalStateException.class,
            () -> service.createThenTag(uid, true)
        );

        assertTrue(findByUid(uid).isEmpty());
    }

    @Test
    void commitLeavesEntryInDirectory() {
        String uid = "txcommitdemo";
        assertTrue(findByUid(uid).isEmpty());

        service.createThenTag(uid, false);

        assertEquals(List.of(uid), findByUid(uid));
        // Dọn entry trong môi trường test sau khi kiểm chứng.
    }
}
~~~

**Điều kiện của ví dụ:** fixture phải bảo đảm hai `uid` chưa tồn tại trước test, tài khoản có quyền Add/Modify/Delete cần thiết và test có bước dọn dữ liệu. Test thành công với directory thử nghiệm **không chứng minh** mọi tình huống lỗi mạng hay ghi đồng thời đều được phục hồi.

### Kiểm tra theo chuỗi thao tác

Nên quan sát log/traces của test server (đã che dữ liệu nhạy cảm) hoặc dùng `ldapsearch` đọc entry sau mỗi ca:

~~~bash
ldapsearch -x \
  -H ldaps://ldap.example.org:636 \
  -D "cn=svc-writer,ou=service,dc=example,dc=org" -W \
  -b "ou=people,dc=example,dc=org" \
  "(&(objectClass=inetOrgPerson)(uid=txrollbackdemo))" \
  dn uid cn sn description
~~~

Bộ lọc trên tìm entry theo `uid`; muốn điều tra tình huống rollback thất bại, còn cần kiểm tra entry tạm có hậu tố `_temp` hoặc thay đổi thuộc tính đang dở dang khi thao tác có rename.

### Ma trận kiểm thử cần có

| Trường hợp | Kết quả/kỳ vọng cần kiểm chứng |
| --- | --- |
| Hai bước tạo/sửa thành công | Commit logic, entry tồn tại với thuộc tính mới. |
| Ngoại lệ runtime sau khi ghi | Manager cố rollback; entry trở lại trạng thái ban đầu nếu các lệnh bù trừ thành công. |
| Checked exception mặc định | Có thể vẫn commit nếu không cấu hình `rollbackFor`. |
| Checked exception với `rollbackFor` | Kích hoạt nỗ lực bù trừ. |
| Gọi `@Transactional` từ cùng class | Có thể bypass AOP proxy, không kích hoạt transaction. |
| `LdapTemplate` dùng target thay proxy | Thao tác không được recorder theo dõi như kỳ vọng. |
| Sai transaction manager | LDAP không được quản lý bởi manager đã cấu hình. |
| Không có quyền Delete/Rename | Bù trừ có thể thất bại dù thao tác chính trước đó thành công. |
| Xóa entry có con | Kiểm tra hạn chế subtree và renaming strategy, không giả định xóa nhiều cấp an toàn. |
| Gặp xung đột với DN tạm | Thao tác rename có thể thất bại; cần phương án xử lý. |
| Mất kết nối sau ghi | Không bảo đảm phục hồi vì không thể gửi thao tác bù trừ. |
| Hai client cùng sửa một entry | Không có isolation; kết quả rollback có thể xung đột/thất bại hoặc ghi đè thay đổi khác. |
| Thay đổi đồng thời LDAP + SQL | Không có XA/two-phase commit nhờ manager LDAP này; cần thiết kế tính nhất quán riêng. |

## 12. Vì sao bù trừ có thể thất bại?

### 12.1. Mất kết nối hoặc LDAP server không sẵn sàng

Nếu request đầu tiên đã sửa directory, sau đó mạng đứt, transaction manager không thể chắc chắn server đã xử lý request cuối đến đâu và không gửi được thao tác ngược. Bù trừ **không thay thế** retry có kiểm soát, audit hoặc cơ chế đối soát dữ liệu.

### 12.2. Thay đổi đồng thời và không có isolation

Client A sửa `mail`, client B sửa cùng entry, rồi A rollback. Nếu thao tác bù trừ của A ghi lại giá trị cũ, nó có thể ghi đè thay đổi hợp lệ của B. LDAP server không tự khóa các entry theo ranh giới `@Transactional` của ứng dụng.

### 12.3. Quyền truy cập và schema

Một tài khoản có quyền tạo entry chưa chắc có quyền xóa, rename hoặc sửa lại thuộc tính cũ. Ngoài ra, thay đổi `objectClass` hoặc chính sách schema có thể làm thao tác ngược không còn hợp lệ. Luôn kiểm thử **quyền của chính Bind DN ứng dụng**, không chỉ bằng admin account.

### 12.4. Rename tạm và tham chiếu nhóm

Khi directory đổi DN tạm, entry nhóm `groupOfNames` có thể còn `member` trỏ đến DN cũ. Directory khác nhau có thể có hoặc không có tính năng cập nhật tham chiếu tự động. Các client khác cũng có thể đọc thấy trạng thái trung gian.

### 12.5. Đọc không đầy đủ dữ liệu cũ

Cơ chế bù trừ cần biết thông tin cũ để phục hồi. ACL có thể che thuộc tính hoặc server hạn chế thuộc tính vận hành, khiến trạng thái đã ghi nhận không đầy đủ. Đặc biệt phải tránh thao tác lặp lại trên thuộc tính mật khẩu hoặc dữ liệu nhạy cảm nếu thư viện/ACL không đủ điều kiện khôi phục đúng.

## 13. Thiết kế nghiệp vụ an toàn hơn khi bù trừ không đủ

Một số quy trình cần kiểm soát ở mức cao hơn:

- **Idempotency:** mỗi yêu cầu nghiệp vụ có ID ổn định, retry không tạo người dùng hoặc nhóm trùng.
- **Trạng thái chờ/đối soát:** lưu dấu nghiệp vụ “đang tạo”, “đã tạo” hoặc “cần sửa lỗi” trong hệ thống có độ tin cậy phù hợp; sau lỗi có thể so sánh trạng thái LDAP thực tế để tiếp tục.
- **Giới hạn phạm vi ghi:** cập nhật từng tập thuộc tính cần thiết, tránh xóa/thay thế toàn entry nếu không bắt buộc.
- **Điều phối theo DN:** giảm xung đột ghi đồng thời lên cùng entry; dùng quy tắc duy nhất và kiểm tra kết quả từ server.
- **Thông báo lỗi rõ ràng:** tách lỗi thao tác chính khỏi lỗi rollback/compensation; không báo “đã hoàn tác thành công” khi chưa có bằng chứng.
- **Audit và cảnh báo:** ghi request ID, loại thao tác, DN đã được chuẩn hóa/phù hợp chính sách log, thời điểm và trạng thái; không ghi mật khẩu hay dữ liệu cá nhân không cần thiết.
- **Khả năng phục hồi:** có quy trình kiểm tra entry tạm, tham chiếu nhóm, trạng thái không nhất quán và sửa chữa có kiểm soát.

Nếu luồng nghiệp vụ phối hợp giữa LDAP và cơ sở dữ liệu SQL, một `ContextSourceTransactionManager` **không tạo transaction phân tán ACID**. Một số phiên bản Spring LDAP từng cung cấp `ContextSourceAndDataSourceTransactionManager` để điều phối ở mức client, nhưng nó cũng không triển khai XA/two-phase commit và API có thể đã deprecated theo phiên bản. Cần đánh giá khả năng lỗi từng bước, cơ chế lưu trạng thái/đối soát và tài liệu phiên bản trước khi chọn.

## 14. Bảo mật kết nối, filter và schema trong giao dịch

Dù đã có `@Transactional`, các thao tác LDAP vẫn phải đáp ứng yêu cầu bảo mật:

- Dùng **LDAPS** hoặc **StartTLS thiết lập thành công trước Bind**, xác minh certificate chain và hostname.
- Lưu mật khẩu service account trong secret manager/biến môi trường, không đưa vào source control, trace hay exception message.
- Tách service account có quyền ghi giới hạn từ tài khoản chỉ đọc. Quyền để **bù trừ** phải được kiểm thử, gồm Delete/Rename/Modify khi cần.
- Không nhận DN hoặc `objectClass` từ payload HTTP. Ứng dụng phải xây DN bằng `LdapNameBuilder`, không ghép chuỗi.
- Khi Search tìm entry trước cập nhật, dùng `LdapQueryBuilder` và filter escaping theo RFC 4515, giới hạn base DN/scope/kết quả.
- Tuân thủ schema: entry `inetOrgPerson` cần `cn` và `sn` (kế thừa từ `person`); sự thất bại do `objectClassViolation` có thể làm kích hoạt bù trừ nếu đã có thao tác trước đó.
- Không chạy thao tác thử lỗi/rollback trên tài khoản hoặc nhóm thật; ưu tiên directory test có fixture riêng.

Ví dụ filter tìm người trước khi bắt đầu thao tác ghi:

~~~java
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;

LdapQuery query = LdapQueryBuilder.query()
    .base("ou=people")
    .where("objectClass").is("inetOrgPerson")
    .and("uid").is(uid);
~~~

Cách này giúp không để dữ liệu `uid` làm biến dạng filter. Nhưng **tìm thấy entry không đảm bảo quyền Modify hoặc khả năng bù trừ**. Hãy kiểm tra ACL và các lỗi server thật.

## 15. Các lỗi cấu hình thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| `@Transactional` không có tác dụng | Quên `@EnableTransactionManagement` hoặc gọi nội bộ cùng class. | Dùng service bean qua Spring proxy; kiểm tra transaction advice. |
| Rollback không xóa entry vừa tạo | `LdapTemplate` dùng ContextSource gốc hoặc manager sai. | Kiểm tra target/proxy wiring và tên `ldapTransactionManager`. |
| Có hai `LdapTemplate` | Auto-configuration và cấu hình riêng tạo bean song song. | Kiểm tra bean graph; inject đúng template trỏ vào proxy. |
| Biên dịch lỗi constructor `ContextSourceTransactionManager(ContextSource)` | Spring LDAP 3.x chưa có constructor mới. | Dùng no-arg + setter tương ứng phiên bản. |
| Cảnh báo deprecated constructor/setter | Dự án dùng Spring LDAP 4.1+ có constructor mới. | Chuyển sang constructor nhận `ContextSource` nếu API hỗ trợ. |
| Commit thành công nhưng entry vẫn tên `_temp` | Commit dọn dữ liệu tạm thất bại hoặc thao tác rename chưa hoàn tất. | Kiểm tra server/log; đối soát entry tạm và quyền Delete. |
| Rollback thất bại với `Insufficient Access Rights` | Thiếu quyền Delete/Rename/Modify ở nhánh liên quan. | Thiết kế ACL đủ cho chính sách bù trừ và giới hạn vào phạm vi nghiệp vụ. |
| Lỗi khi dùng JDBC + LDAP | Nhầm manager hoặc kỳ vọng XA. | Tách ranh giới transaction, thiết kế bù trừ và đối soát liên hệ thống. |
| Dữ liệu giữa các bước bị client khác nhìn thấy | Không có isolation. | Giới hạn thao tác, phối hợp theo DN hoặc thay đổi quy trình nghiệp vụ. |
| Timeout khi rollback | Network/server chậm hoặc mất kết nối. | Không giả định đã phục hồi; ghi nhận trạng thái cần đối soát. |

## 16. Bài tập thực hành

**Bài 1 — Vẽ lại wiring.** Cho bốn bean `ldapTargetContextSource`, `contextSource`, `ldapTemplate` và `ldapTransactionManager`. Vẽ mũi tên phụ thuộc và giải thích vì sao manager phải nhận target, còn template nhận proxy.

**Bài 2 — Commit và rollback.** Chạy `createThenTag("txlab01", false)` trên directory test, xác nhận entry tồn tại. Chạy `createThenTag("txlab02", true)` và kiểm tra entry mới biến mất **nếu bù trừ thành công**. Thử ngắt kết nối trong test có kiểm soát và ghi nhận giới hạn của rollback.

**Bài 3 — Kiểm tra hai loại lỗi.** Thử ném `RuntimeException` và checked `Exception`. So sánh hành vi mặc định rồi bật `rollbackFor = Exception.class`. Cần chạy phương thức qua Spring bean proxy, không gọi trực tiếp đối tượng `new`.

**Bài 4 — Kiểm tra quyền bù trừ.** Cấu hình account trong môi trường test có quyền Add nhưng không có quyền Delete. Cho thao tác ghi trước đó thành công rồi kích hoạt rollback. Quan sát lỗi bù trừ và trạng thái thực tế; đề xuất chính sách ACL tối thiểu phù hợp.

**Bài 5 — Rename tạm.** Tạo entry test có thể xóa, thực hiện `LdapTemplate.unbind(...)` trong transaction rồi cố ý ném ngoại lệ. Quan sát tên tạm `_temp` nếu server cho phép; giải thích vì sao Search của client khác có thể thấy trạng thái trung gian.

**Bài 6 — Repository.** Chuyển thao tác tạo/sửa sang `DirectoryPersonRepository` và viết kiểm thử chứng minh repository đang thực sự dùng `LdapTemplate` trỏ tới `TransactionAwareContextSourceProxy`. Nếu test rollback khác với `LdapTemplate` trực tiếp, kiểm tra bean wiring trước.

## 17. Câu hỏi tự ôn tập

1. `ContextSourceTransactionManager` thực hiện rollback bằng cơ chế gì, và vì sao không có đảm bảo ACID?
2. Vì sao phải đưa **target ContextSource** vào manager nhưng đưa **proxy** vào `LdapTemplate`?
3. `LdapTemplate.bind(...)` khác LDAP BindRequest ở mức giao thức thế nào?
4. Hai thao tác LDAP đã thành công; service ném `IllegalStateException`. Những điều kiện nào khiến rollback vẫn có thể thất bại?
5. `@Transactional` có chạy khi một method của cùng service tự gọi một method khác có annotation không?
6. Một checked exception có mặc định kích hoạt rollback theo cấu hình Spring thông dụng không?
7. `DefaultTempEntryRenamingStrategy` có tác dụng gì đối với `unbind` và `rebind`?
8. Vì sao cùng một entry có thể bị người dùng khác nhìn thấy ở trạng thái trung gian dù service có `@Transactional`?
9. Khi ứng dụng có cả `JpaTransactionManager` và `ContextSourceTransactionManager`, cần làm gì ở annotation?
10. Cần những kiểm thử nào để khẳng định cả thao tác chính lẫn thao tác bù trừ có đủ quyền LDAP?
11. Có nên đưa trường `userPassword` vào thao tác bù trừ hồ sơ nhân viên thông thường không? Vì sao?
12. Vì sao một integration test rollback thành công chưa đủ để cam kết phục hồi trong mọi tình huống production?

**Ghi nhớ:** muốn cấu hình `ContextSourceTransactionManager` đúng, hãy nối **target ContextSource → transaction manager**, đồng thời nối **target → TransactionAwareContextSourceProxy → LdapTemplate/repository**. Đặt `@Transactional` ở ranh giới service thực sự đi qua Spring proxy, kiểm thử bằng directory thật và luôn thiết kế phương án đối soát khi bù trừ không thành công.

### Tài liệu tham khảo

- [Spring LDAP — ContextSourceTransactionManager API](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/transaction/compensating/manager/ContextSourceTransactionManager.html): cơ chế bù trừ, constructor và yêu cầu wiring.
- [Spring LDAP — TransactionAwareContextSourceProxy API](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/transaction/compensating/manager/TransactionAwareContextSourceProxy.html): context theo giao dịch và recorder.
- [Spring LDAP — LdapTemplate API](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/LdapTemplate.html): `bind`, `unbind`, `modifyAttributes`, `rename`.
- [Spring LDAP Reference](https://docs.spring.io/spring-ldap/reference/): thiết lập ContextSource, Spring LDAP transaction và thao tác directory.
- [Spring Framework — Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html): `@Transactional`, proxy và rollback rules.
- [RFC 4511 — LDAP: The Protocol](https://www.rfc-editor.org/rfc/rfc4511): thao tác LDAP và Search/Modify.
- [RFC 4512 — LDAP: Directory Information Models](https://www.rfc-editor.org/rfc/rfc4512): DN, schema và objectClass.
- [RFC 5805 — LDAP Transactions](https://www.rfc-editor.org/rfc/rfc5805): mở rộng giao dịch LDAP tùy chọn, khác cơ chế bù trừ của Spring.
