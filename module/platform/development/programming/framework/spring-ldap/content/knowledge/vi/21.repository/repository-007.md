# Transaction boundary trong repository operation của Spring LDAP

Khi dùng Spring Data LDAP Repository, các thao tác như `save`, `delete`, `saveAll` và `findById` được gọi tương tự Spring Data JPA. Sự giống nhau về API dễ dẫn đến một giả định nguy hiểm: đặt `@Transactional` lên service sẽ biến mọi lần ghi LDAP thành một giao dịch cơ sở dữ liệu có khả năng **commit/rollback nguyên tử**. Trên thực tế, **LDAPv3 cốt lõi không cung cấp giao dịch ACID bao trùm nhiều operation như cơ sở dữ liệu quan hệ**. Spring LDAP chỉ có thể hỗ trợ **compensating transaction**: ghi nhận trạng thái trước khi sửa để *cố gắng* thực hiện thao tác bù trừ nếu luồng nghiệp vụ thất bại.

Trong chương **Repository**, *transaction boundary* là ranh giới bắt đầu và kết thúc phần công việc mà ứng dụng muốn xử lý như một đơn vị nghiệp vụ. Ví dụ, “cập nhật thông tin của hai nhân viên hoặc khôi phục nếu bước thứ hai lỗi” là một boundary có **hai repository call**; một lần `repository.save(person)` riêng lẻ không bao quát toàn bộ quy trình đó.

Sau bài này, bạn có thể:

- Xác định transaction boundary phù hợp ở **service** thay vì nhầm mỗi repository method với một transaction toàn hệ thống.
- Phân biệt **LDAP operation**, **compensating transaction của Spring LDAP** và **transaction JDBC/JPA**.
- Cấu hình `ContextSourceTransactionManager` với `TransactionAwareContextSourceProxy` và gọi `@Transactional` đúng transaction manager.
- Giải thích rollback **best-effort**, giới hạn isolation/replication/mất kết nối và cách kiểm thử luồng lỗi.

## 1. Ba cấp độ “giao dịch” cần phân biệt

| Phạm vi | Ví dụ | Bảo đảm thực tế |
| --- | --- | --- |
| **Một LDAP operation** | `modifyAttributes(dn, items)` trên một entry | Server thực hiện operation theo quy tắc LDAP của nó; không đồng nghĩa bao trùm các operation khác |
| **Nhiều repository operation trong service** | `save(A)` rồi `save(B)` | Mặc định không có cơ chế rollback chung mà ứng dụng có thể tự động kỳ vọng |
| **Spring LDAP compensating transaction** | `@Transactional` với `ContextSourceTransactionManager` và context proxy đã cấu hình | Spring ghi nhận thao tác để **cố gắng đảo ngược** nếu transaction rollback; không có ACID/isolation phía server |

Hãy hình dung luồng sau:

~~~text
Service: chuyển hai nhân viên sang trạng thái mới

  repository.save(employeeA)    ---> LDAP đã thay đổi entry A
  repository.save(employeeB)    ---> lỗi LDAP

Nếu KHÔNG có compensating transaction:
  A có thể đã đổi, B chưa đổi.

Nếu CÓ Spring LDAP compensating transaction được cấu hình đúng:
  Spring cố gắng khôi phục A về trạng thái trước bước ghi.
  Nếu mất kết nối hoặc có ghi đồng thời, khôi phục có thể thất bại.
~~~

Đây là khác biệt quan trọng giữa **ý định all-or-nothing ở tầng ứng dụng** và **khả năng bảo đảm của hạ tầng LDAP**. Với hệ thống quản trị tài khoản, cấp quyền hoặc đồng bộ nhân sự, phải thiết kế cả tình huống trạng thái chỉ được cập nhật một phần.

## 2. Repository operation không tự thiết lập boundary nghiệp vụ

Spring LDAP hỗ trợ repository qua Spring Data LDAP. Một repository điển hình:

~~~java
import org.springframework.data.ldap.repository.LdapRepository;

public interface EmployeeRepository extends LdapRepository<EmployeeEntry> {
}
~~~

`EmployeeEntry` là ODM entity có `@Entry` và `@Id` kiểu `javax.naming.Name`. Spring Data LDAP dùng `@EnableLdapRepositories` để tìm repository, và theo mặc định tìm bean `LdapTemplate` tên `ldapTemplate`. Các phương thức như `save` hoặc `deleteById` có thể dẫn tới LDAP `bind`, `modifyAttributes` hoặc `unbind` thông qua tầng ODM.

Một số nhầm lẫn cần tránh:

1. `saveAll(List.of(a, b))` biểu thị thao tác lưu nhiều entity, **không tự mang ý nghĩa một LDAP server transaction nguyên tử**.
2. `@Transactional` chỉ có tác dụng khi **transaction interceptor của Spring được kích hoạt** và **transaction manager được chọn phù hợp**. Không thể suy ra bảo đảm từ tên annotation.
3. Một repository chỉ biết operation của nó; quy trình “thêm account + cập nhật nhóm + gửi thông báo” thuộc **service nghiệp vụ**, vượt quá phạm vi một repository.
4. LDAP repository không hỗ trợ paging/sorting theo cách các repository database thường hỗ trợ; đừng lấy đặc điểm giao dịch hay truy vấn của JPA làm mặc định cho LDAP.

### Chọn ranh giới tại service

~~~mermaid
flowchart TD
    A["Controller gọi public service method qua Spring proxy"] --> B["Bắt đầu logical transaction"]
    B --> C["repository.save(A)"]
    C --> D["repository.save(B)"]
    D --> E{"Có lỗi?"}
    E -->|Không| F["Kết thúc transaction / commit bước bù trừ nếu có"]
    E -->|Có| G["Transaction manager cố gắng rollback bằng compensation"]
    G --> H["Kiểm tra kết quả, phát hiện trạng thái chưa khôi phục"]
~~~

Đặt annotation tại **public service method** gọi nhiều repository operation giúp boundary trùng với mục đích nghiệp vụ. Trong mô hình Spring proxy phổ biến, **self-invocation** (method của cùng object gọi trực tiếp method khác cũng có `@Transactional`) không đi qua proxy nên không tự tạo boundary mong đợi. Tránh khởi tạo service bằng `new` nếu cần transaction interception.

## 3. Spring LDAP compensating transaction hoạt động thế nào?

Spring LDAP cung cấp `ContextSourceTransactionManager`, triển khai `PlatformTransactionManager`, và `TransactionAwareContextSourceProxy` để bao bọc `ContextSource`. Proxy can thiệp các thao tác ghi đi qua `DirContext` trong một transaction, ghi lại thông tin cần cho bước bù trừ.

| LDAP operation | Cách chuẩn bị/ghi nhận | Bước bù trừ khi rollback (khái quát) |
| --- | --- | --- |
| `bind` (tạo entry) | Ghi nhớ DN, thực hiện bind | `unbind` entry vừa tạo |
| `rename` | Ghi DN cũ và mới, thực hiện rename | Rename về DN cũ |
| `modifyAttributes` | Ghi các giá trị/thay đổi cần đảo | Gửi những modification đảo ngược |
| `unbind` (xóa entry) | Có thể **đổi DN tạm** để giữ nguyên entry trước commit | Đổi entry từ DN tạm trở về DN cũ |
| `rebind` | Có thể dùng DN tạm và thao tác thay thế | Khôi phục entry cũ bằng bước bù trừ phù hợp |

Với `unbind` và `rebind`, việc đổi tên tạm có thể đòi hỏi chiến lược `TempEntryRenamingStrategy` phù hợp cho cây có entry con hoặc ràng buộc naming/schema. **Không coi delete đã hoàn tất ngay khi service gọi `delete`** nếu một transaction bù trừ đang trì hoãn việc xóa thực tế đến thời điểm commit.

**Giới hạn cốt lõi**: cơ chế này là **client-side**. LDAP server không giữ một bản transaction để rollback theo yêu cầu. Nếu mất kết nối lúc cần khôi phục, nếu bên thứ ba sửa cùng entry, nếu quyền/schema thay đổi hoặc server gặp sự cố, bù trừ có thể thất bại. Không có **transaction isolation** giữa các client LDAP chỉ nhờ cấu hình này.

## 4. Cấu hình transaction manager và context proxy

Muốn các repository operation tham gia cùng transaction, **đường kết nối LDAP đi qua repository** phải sử dụng `LdapTemplate` với `TransactionAwareContextSourceProxy`, trong khi `ContextSourceTransactionManager` phải quản lý **ContextSource gốc**.

Sơ đồ bean:

~~~text
                        +-----------------------------+
LdapContextSource ------>| ContextSourceTransactionManager |
  (target)              +-----------------------------+
      |
      v
TransactionAwareContextSourceProxy
      |
      v
LdapTemplate (bean "ldapTemplate")
      |
      v
EmployeeRepository ---> EmployeeService
                            @Transactional("ldapTransactionManager")
~~~

### 4.1. Ví dụ JavaConfig (Spring LDAP 4.1+)

Đoạn dưới minh họa cách bố trí bean và tránh hard-code bind password. Trong môi trường thực, cấu hình TLS/LDAPS, truststore, pooling và credential phải phù hợp với quy trình bảo mật của tổ chức.

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;
import org.springframework.data.ldap.repository.config.EnableLdapRepositories;
import org.springframework.ldap.core.ContextSource;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.core.support.LdapContextSource;
import org.springframework.ldap.transaction.compensating.manager.ContextSourceTransactionManager;
import org.springframework.ldap.transaction.compensating.manager.TransactionAwareContextSourceProxy;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@Configuration
@EnableTransactionManagement
@EnableLdapRepositories(
    basePackages = "com.example.directory.repository",
    ldapTemplateRef = "ldapTemplate"
)
public class LdapTxConfig {

    @Bean("ldapTargetContextSource")
    public LdapContextSource ldapTargetContextSource(Environment env) {
        LdapContextSource target = new LdapContextSource();
        target.setUrl(env.getRequiredProperty("directory.ldap-url"));
        target.setBase(env.getRequiredProperty("directory.base-dn"));
        target.setUserDn(env.getRequiredProperty("directory.bind-dn"));
        target.setPassword(env.getRequiredProperty("directory.bind-password"));
        return target;
    }

    @Bean("transactionAwareContextSource")
    public ContextSource transactionAwareContextSource(
            @Qualifier("ldapTargetContextSource") LdapContextSource target) {
        return new TransactionAwareContextSourceProxy(target);
    }

    @Bean("ldapTemplate")
    public LdapTemplate ldapTemplate(
            @Qualifier("transactionAwareContextSource") ContextSource source) {
        return new LdapTemplate(source);
    }

    @Bean("ldapTransactionManager")
    public PlatformTransactionManager ldapTransactionManager(
            @Qualifier("ldapTargetContextSource") ContextSource target) {
        return new ContextSourceTransactionManager(target);
    }
}
~~~

Các property cần khai báo an toàn, ví dụ:

~~~properties
directory.ldap-url=ldaps://ldap.example.org:636
directory.base-dn=dc=example,dc=org
# directory.bind-dn và directory.bind-password được lấy từ secret store/env.
~~~

**Tại sao phải có hai ContextSource?** `ContextSourceTransactionManager` cần biết target để quản lý tài nguyên, còn `LdapTemplate` phải nhận proxy nhằm ghi nhận các operation cần đảo ngược. Nếu repository vô tình dùng một `LdapTemplate` khác trỏ thẳng vào target, những lần ghi đó có thể **đi ngoài** cơ chế bù trừ.

Ví dụ dùng constructor `new ContextSourceTransactionManager(target)` theo API Spring LDAP 4.1+. Với các phiên bản cũ, cách khởi tạo transaction manager có thể khác; đối chiếu tài liệu API của phiên bản đang chạy. Không thiết lập nhiều `PlatformTransactionManager` rồi để Spring tự chọn một cách mơ hồ: hãy ghi rõ tên `transactionManager` trong `@Transactional`.

### 4.2. Những thứ cấu hình trên không tự bảo đảm

- Không tự tích hợp LDAP và JDBC thành một **XA / two-phase commit**. Tài liệu Spring LDAP ghi nhận chức năng tích hợp JDBC–LDAP transaction manager trước đây đã **bị loại bỏ từ Spring LDAP 4.0**.
- Không giữ snapshot của LDAP; client khác vẫn có thể ghi và quan sát dữ liệu.
- Không tự giải quyết cập nhật đồng thời, vòng lặp retry, referral, replication lag hoặc failover.
- Không bảo đảm mọi kiểu move/delete nguyên subtree đều được chiến lược rename tạm mặc định hỗ trợ.

## 5. Ví dụ service có hai repository operation

Giả sử ODM entity đã ánh xạ các trường `uid`, `cn`, `sn` và `description` như sau:

~~~java
import javax.naming.Name;

import org.springframework.ldap.odm.annotations.Attribute;
import org.springframework.ldap.odm.annotations.Entry;
import org.springframework.ldap.odm.annotations.Id;

@Entry(
    base = "ou=people",
    objectClasses = {"top", "person", "organizationalPerson", "inetOrgPerson"}
)
public class EmployeeEntry {

    @Id
    private Name dn;

    @Attribute(name = "uid")
    private String uid;

    @Attribute(name = "cn")
    private String cn;

    @Attribute(name = "sn")
    private String sn;

    @Attribute(name = "description")
    private String description;

    public EmployeeEntry() {}

    public Name getDn() { return dn; }
    public void setDn(Name dn) { this.dn = dn; }

    public String getUid() { return uid; }
    public void setUid(String uid) { this.uid = uid; }

    public String getCn() { return cn; }
    public void setCn(String cn) { this.cn = cn; }

    public String getSn() { return sn; }
    public void setSn(String sn) { this.sn = sn; }

    public String getDescription() { return description; }
    public void setDescription(String description) {
        this.description = description;
    }
}
~~~

Repository tiếp tục dùng giao diện `LdapRepository`:

~~~java
package com.example.directory.repository;

import org.springframework.data.ldap.repository.LdapRepository;
import com.example.directory.model.EmployeeEntry;

public interface EmployeeRepository extends LdapRepository<EmployeeEntry> {
}
~~~

Service xác định boundary:

~~~java
import javax.naming.Name;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class EmployeeDirectoryService {

    private final EmployeeRepository repository;

    public EmployeeDirectoryService(EmployeeRepository repository) {
        this.repository = repository;
    }

    @Transactional(transactionManager = "ldapTransactionManager")
    public void updateTwoDescriptions(
            Name firstDn, String firstDescription,
            Name secondDn, String secondDescription) {

        if (firstDn.equals(secondDn)) {
            throw new IllegalArgumentException("Hai DN phải khác nhau");
        }

        EmployeeEntry first = repository.findById(firstDn)
            .orElseThrow(() -> new IllegalArgumentException("Thiếu DN thứ nhất"));
        first.setDescription(firstDescription);
        repository.save(first);

        // Nếu lookup/save thứ hai thất bại, transaction manager sẽ cố gắng
        // thực hiện compensation cho lần save thứ nhất.
        EmployeeEntry second = repository.findById(secondDn)
            .orElseThrow(() -> new IllegalArgumentException("Thiếu DN thứ hai"));
        second.setDescription(secondDescription);
        repository.save(second);
    }
}
~~~

Ở đây, **một lời gọi public service method** là logical transaction boundary gồm hai lần repository `save`. Theo mặc định của Spring transaction interceptor, `RuntimeException` và `Error` dẫn đến rollback, còn **checked exception** không tự kích hoạt rollback nếu không cấu hình `rollbackFor` hoặc điều kiện tương đương. Cần quyết định rule phù hợp với loại lỗi nghiệp vụ.

Nếu bỏ annotation hoặc chọn nhầm transaction manager JDBC, việc save A thành công trước khi save B thất bại **không được bảo vệ** bởi compensating transaction LDAP đúng nghĩa. Ngay cả khi cấu hình đúng, đừng ghi trong tài liệu nghiệp vụ rằng “cả hai entry sẽ chắc chắn cùng thành công hoặc cùng rollback”.

## 6. Phạm vi của một transaction boundary

Tùy mục đích, một boundary có thể bao gồm:

| Workflow | Boundary nên đặt ở đâu? | Cảnh báo |
| --- | --- | --- |
| Chỉ cập nhật một attribute của một entry | Một service method ngắn hoặc gọi `modifyAttributes` trực tiếp | Compensation có thể không đem lại lợi ích lớn so với một operation đơn |
| Lưu hai entity qua hai lần `save` | Service method điều phối hai repository call | Rollback best-effort, không có isolation |
| Tạo user và thêm DN vào group | Service method cho cả tạo và cập nhật nhóm | Nếu bước sau lỗi, cần biết user đã tồn tại, group đã đổi hay chưa |
| Xóa user và xóa tham chiếu nhóm | Workflow có kế hoạch bù trừ và kiểm chứng | Phụ thuộc temp renaming, ACL, thứ tự xóa, dữ liệu liên kết |
| Ghi JDBC rồi gọi LDAP | Boundary ứng dụng/hệ tích hợp; có thể cần saga/outbox | Không có XA LDAP + JDBC trong Spring LDAP 4.x |
| Gọi HTTP API/email sau sửa LDAP | Workflow ngoài transaction LDAP, có idempotency | Không thể rollback email/API call bằng LDAP transaction |

Đặt boundary quá rộng làm tăng thời gian giữ context, số thao tác bù trừ và nguy cơ va chạm. **Không để transaction mở trong lúc đợi người dùng nhập liệu hoặc gọi hệ thống mạng chậm**. Với nhiều thao tác có thể thất bại độc lập, thiết kế workflow idempotent, audit trail và bước đối soát thường đáng tin cậy hơn dựa hoàn toàn vào compensation.

### Khi transaction manager chỉ quản lý một ContextSource

Một `ContextSourceTransactionManager` được gắn với một `ContextSource`. Nếu ứng dụng có nhiều LDAP directory/server, không nên suy rằng một annotation sẽ tự gom các context khác nhau thành một transaction. Điều phối nhiều nguồn và dữ liệu có thể yêu cầu bước bù trừ được ứng dụng xác định cụ thể.

Trong môi trường có LDAP replica, hãy xác định endpoint ghi và endpoint đọc. Một rollback hoặc phép kiểm tra sau ghi đi qua node khác có thể thấy trạng thái chưa được replicate; điều đó khác với việc transaction hoàn tất ở phía client.

## 7. Isolation và các trường hợp rollback có thể thất bại

Compensation dựa vào trạng thái đã ghi nhận nên có giới hạn quan trọng khi directory còn được sửa bởi client khác:

~~~text
T0: LDAP có description(A) = "Old".
T1: Service 1 bắt đầu transaction, đổi A thành "New".
T2: Service 2 cập nhật A thành "Other".
T3: Service 1 gặp lỗi ở entry B và cố rollback A về "Old".
~~~

Nếu không có kiểm soát đồng thời, rollback của service 1 **có thể ghi đè giá trị "Other" vừa được service 2 cập nhật**. Spring LDAP transaction manager không cung cấp isolation như database.

Những tình huống cần được giám sát:

- **Mất kết nối/TLS timeout khi rollback:** client không gửi được thao tác bù trừ hoặc không biết server đã xử lý đến đâu.
- **ACL/schema thay đổi:** thao tác đảo có thể bị từ chối dù thao tác gốc thành công.
- **Thao tác xóa/chuyển DN với entry con:** strategy rename tạm có thể không hợp lệ trên server/backend cụ thể.
- **Ghi đồng thời:** rollback có thể khôi phục giá trị cũ sai với kỳ vọng của client khác.
- **Lỗi tại commit/cleanup:** không thể coi một service không trả lỗi nghiệp vụ là bằng chứng toàn bộ tài nguyên đã ở trạng thái mong muốn nếu có sự cố trên đường mạng.

Nếu nghiệp vụ yêu cầu chống mất cập nhật, cần kiểm soát phiên bản/điều kiện ghi theo tính năng server, chẳng hạn LDAP assertion control nếu cả server và client hỗ trợ, hoặc cơ chế điều phối ở ứng dụng. `@Transactional` không thay thế các kỹ thuật đó.

## 8. Tại sao không nên xem @Transactional là phép màu?

### 8.1. Proxy, phương thức và rollback rule

Một đoạn mã có vẻ có transaction nhưng thực tế không qua interceptor:

~~~java
@Service
public class WrongExample {

    public void outer() {
        inner(); // Self-invocation: không đi qua Spring AOP proxy.
    }

    @Transactional(transactionManager = "ldapTransactionManager")
    public void inner() {
        // repository.save(...);
    }
}
~~~

Hãy gọi method giao dịch **qua một Spring-managed bean/proxy khác**. Trường hợp nhiều transaction manager, phải chỉ rõ `transactionManager = "ldapTransactionManager"`. Khi bắt exception rồi không ném lại, transaction interceptor có thể không nhận ra cần rollback; nếu cần nuốt lỗi, phải chủ động định nghĩa trạng thái transaction, không chỉ dựa vào catch.

### 8.2. Annotation không đồng nghĩa server rollback

So sánh:

| Kỳ vọng sai | Cách hiểu đúng |
| --- | --- |
| “`saveAll` chạy một lệnh nguyên tử trên LDAP” | Có thể phát sinh nhiều operation; phải kiểm tra triển khai và boundary |
| “Có `@Transactional` là LDAP server giữ snapshot” | Spring thực hiện compensation phía client, không có isolation server |
| “Bất kỳ lỗi nào cũng rollback” | Spring có rule rollback; checked exception cần cấu hình |
| “Kết nối hỏng sẽ rollback chắc chắn” | Mất kết nối có thể khiến compensation bất khả thi |
| “Commit JDBC là LDAP cũng commit đồng bộ” | Không có XA LDAP/JDBC trong Spring LDAP 4.x |
| “Rollback nghĩa là ứng dụng không cần kiểm tra lại” | Cần readback/audit và quy trình xử lý bất nhất |

## 9. Kiểm thử transaction boundary

Nên kiểm thử trên LDAP test server có schema và ACL giống môi trường đích. Không dùng production làm nơi thử các lỗi rollback, rename tạm hoặc xóa entry.

### 9.1. Ma trận kiểm thử

| Ca thử | Thiết lập | Kỳ vọng quan sát |
| --- | --- | --- |
| Hai lần save đều thành công | Cả hai DN tồn tại, tài khoản có quyền | Hai description mới được đọc lại đúng |
| Lỗi runtime **sau** save A | DN B cố ý không tồn tại hoặc lỗi có kiểm soát | Spring **thử compensation** cho A; kiểm tra A về giá trị trước đó |
| Không cấu hình proxy/manager | Dùng bản test riêng không bật compensation | Save A có thể còn tồn tại dù bước B lỗi |
| Lỗi checked exception | Service ném checked exception, không cấu hình `rollbackFor` | So sánh với rule mặc định; không giả định có rollback |
| Rollback khi bị ACL từ chối | Test account không có quyền đảo thao tác | Ghi nhận rollback thất bại, kiểm tra trạng thái thực tế |
| Có cập nhật đồng thời | Client khác sửa A giữa save và compensation | Quan sát nguy cơ ghi đè/vi phạm isolation |
| Delete trong transaction | Xóa entry thử nghiệm rồi gây lỗi | Kiểm tra hành vi đổi tên tạm/khôi phục, nhất là entry có con |
| LDAP + JDBC | Có hai data source và hai manager riêng | Không giả định một annotation tạo XA transaction |

### 9.2. Khung JUnit 5 integration test

Giả sử test fixture đã seed entry A với description `Old` và bảo đảm entry B **không tồn tại**. Bài kiểm thử dưới đây chỉ có ý nghĩa khi đã bật `LdapTxConfig` đúng cách và có service bean thực sự được proxy:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import javax.naming.Name;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.ldap.support.LdapNameBuilder;

@SpringBootTest
class EmployeeDirectoryServiceTransactionTest {

    @Autowired
    EmployeeDirectoryService service;

    @Autowired
    EmployeeRepository repository;

    @Test
    void failureOnSecondOperationAttemptsToRestoreFirst() {
        Name first = dn("an");
        Name absentSecond = dn("missing-test-user");

        EmployeeEntry before = repository.findById(first).orElseThrow();
        String previous = before.getDescription();

        assertThrows(IllegalArgumentException.class, () ->
            service.updateTwoDescriptions(
                first, "Temporary change",
                absentSecond, "Must not be written"
            )
        );

        EmployeeEntry after = repository.findById(first).orElseThrow();
        assertEquals(previous, after.getDescription());
    }

    private static Name dn(String uid) {
        return LdapNameBuilder.newInstance()
            .add("ou", "people")
            .add("uid", uid)
            .build();
    }
}
~~~

Đây là **khung kiểm thử tích hợp**, không phải phép chứng minh mọi rollback đều thành công. Phải cấu hình `SpringBootTest`, test LDAP endpoint, schema, dữ liệu seed và làm sạch fixture. Một test đạt trong tình huống bình thường chỉ chứng minh compensation hoạt động trong **điều kiện thử đó**; còn phải thử lỗi mạng, thay đổi quyền, rename/move và cập nhật đồng thời nếu hệ thống cần độ tin cậy cao.

Để phân biệt không có compensation với compensation đúng cách, nên xem audit log của LDAP test server hoặc cơ chế logging được phép, đồng thời **đọc lại trạng thái** từng entry. Không log mật khẩu, token, toàn bộ DN nhạy cảm hoặc các attribute bảo mật.

## 10. Thiết kế phục hồi khi không thể rollback

Với nghiệp vụ cần độ tin cậy cao, nên thiết kế rõ **trạng thái quy trình** thay vì chỉ trông cậy vào annotation:

1. Gán **operation ID** để phân biệt một yêu cầu nghiệp vụ, đặc biệt khi retry sau timeout.
2. Ghi trạng thái dự kiến và trạng thái đã áp dụng cho từng bước trong hệ thống quản lý workflow phù hợp; tránh dùng LDAP như một journal giao dịch không được hỗ trợ.
3. Phân biệt lỗi “server chắc chắn từ chối” với lỗi “không biết server đã áp dụng chưa” do mạng.
4. Sau sự cố, **đọc lại từng DN/attribute liên quan** qua điểm đọc được kiểm soát và so với trạng thái nghiệp vụ mong muốn.
5. Thực hiện bước sửa lỗi/bù trừ **idempotent** và kiểm soát quyền; không retry lệnh tạo/xóa một cách mù quáng.
6. Cảnh báo hoặc chuyển cho người vận hành xử lý khi không thể tự phục hồi, đặc biệt với thay đổi nhóm quyền hoặc account.

Ví dụ thêm user vào LDAP và lưu profile trong database cần hiểu rằng nếu profile insert thành công nhưng LDAP bind thất bại (hoặc ngược lại), không có một XA transaction Spring LDAP 4.x mặc định khôi phục cả hai. Một thiết kế saga/outbox hoặc luồng đồng bộ lại theo trạng thái nghiệp vụ thường phù hợp hơn lời hứa rollback chắc chắn.

## 11. Bài tập vận dụng

Một ứng dụng sử dụng `EmployeeRepository` với hai account `uid=an` và `uid=binh`:

1. Đặt `@Transactional` trên `repository.save` có chắc chắn bao trùm cả bước cập nhật nhóm ở một repository khác không? Boundary hợp lý hơn nằm ở đâu?
2. Vì sao phải dùng `TransactionAwareContextSourceProxy` ở đường kết nối của `LdapTemplate` mà repository sử dụng?
3. `save(A)` thành công, `save(B)` ném `IllegalArgumentException`. Với compensating transaction cấu hình đúng, Spring LDAP cố gắng làm gì?
4. Nếu kết nối LDAP mất sau lỗi thứ hai, có thể cam kết A trở về trạng thái ban đầu không?
5. Vì sao `delete` entry trong transaction có thể liên quan tới `TempEntryRenamingStrategy`?
6. Nếu một service có cả JDBC và LDAP, trong Spring LDAP 4.x có tự tạo XA transaction bằng `ContextSourceAndDataSourceTransactionManager` cũ không?
7. Khi service A gọi method `@Transactional` của **chính object A** bằng `this.method()`, transaction interceptor của Spring proxy có nhất thiết chạy không?

**Gợi ý:** (1) không, nên đặt tại service điều phối; (2) proxy ghi nhận operation và dữ liệu cần cho compensation; (3) cố đảo ngược lần ghi A; (4) không, vì rollback client-side cần kết nối và điều kiện server phù hợp; (5) server có thể không cho phục hồi đủ thuộc tính khi xóa nên Spring dùng đổi tên tạm; (6) không, hỗ trợ tích hợp cũ đã bị loại bỏ; (7) không, self-invocation thường bỏ qua proxy.

## 12. Ghi nhớ

- **Transaction boundary** là phạm vi nghiệp vụ do service quyết định; repository API không tự bảo đảm nhiều LDAP operation là nguyên tử.
- `ContextSourceTransactionManager` + `TransactionAwareContextSourceProxy` cung cấp **compensating transaction phía client**, không phải ACID transaction của LDAP server.
- Cấu hình `@Transactional(transactionManager = "ldapTransactionManager")` trên public service method, bảo đảm invocation đi qua Spring proxy và repository dùng đúng `LdapTemplate` đã gắn context proxy.
- Rollback chỉ là **cố gắng bù trừ**: mất kết nối, ACL/schema, rename tạm hoặc ghi đồng thời có thể khiến trạng thái LDAP không khôi phục như mong đợi.
- **JDBC/LDAP XA** không được cung cấp bởi cơ chế này; hỗ trợ kết hợp manager cũ đã bị loại bỏ trong Spring LDAP 4.0.
- Luôn kiểm thử đường lỗi, theo dõi trạng thái từng entry, thiết kế retry/bù trừ idempotent và có kế hoạch đối soát dữ liệu sau sự cố.

### Tài liệu tham khảo

- [Spring LDAP — Transaction Support, Compensating Transactions](https://docs.spring.io/spring-ldap/reference/transaction-support.html)
- [Spring LDAP — ContextSourceTransactionManager API](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/transaction/compensating/manager/ContextSourceTransactionManager.html)
- [Spring LDAP — TransactionAwareContextSourceProxy API](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/transaction/compensating/manager/TransactionAwareContextSourceProxy.html)
- [Spring LDAP — Spring LDAP Repositories](https://docs.spring.io/spring-ldap/reference/repositories.html)
- [Spring Data LDAP — Configuration & EnableLdapRepositories](https://docs.spring.io/spring-data/ldap/reference/ldap/configuration.html)
- [Spring Data LDAP — SimpleLdapRepository API](https://docs.spring.io/spring-data/ldap/reference/api/java/org/springframework/data/ldap/repository/support/SimpleLdapRepository.html)
- [Spring Framework — Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html)
- [RFC 4511 — LDAP Modify Operation](https://www.rfc-editor.org/rfc/rfc4511.html#section-4.6)
