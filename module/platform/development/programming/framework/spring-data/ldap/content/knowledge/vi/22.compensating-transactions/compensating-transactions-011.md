# Kiểm chứng cấu hình pool, xác thực và giao dịch cùng hoạt động

Trong chương **Giao dịch bù trừ** của **SPRING_DATA_LDAP**, một ứng dụng thường cần kết hợp ba cơ chế: **xác thực LDAP**, **connection pool** và **giao dịch bù trừ**. Mỗi cơ chế giải quyết một vấn đề riêng. Xác thực xác định danh tính đang thao tác; pool tái sử dụng các kết nối LDAP đã được mở và Bind; transaction manager theo dõi các thay đổi để cố gắng khôi phục trạng thái ban đầu khi một luồng nghiệp vụ thất bại.

Hãy xét luồng cấp tài khoản nhân viên. Ứng dụng tạo entry nhân viên, thêm DN của nhân viên vào group, rồi cập nhật một thuộc tính trạng thái. Nếu thao tác cuối thất bại, ứng dụng muốn hoàn tác các thay đổi LDAP trước đó. Trong khi đó, các thao tác phải chạy bằng service account có quyền phù hợp, connection phải được tái sử dụng an toàn và context chỉ được trả về pool sau khi transaction kết thúc.

Một cấu hình sai có thể khiến repository dùng ContextSource không được transaction manager quản lý; thao tác ghi thoát khỏi transaction; context bị đóng hoặc trả về pool quá sớm; hoặc connection đã Bind bằng service account bị dùng như danh tính của user khác. Bài học này kiểm chứng toàn bộ đường đi từ bean cấu hình đến operation, rollback và việc trả context về pool.

**Mục tiêu:** hiểu giới hạn của Spring LDAP compensating transaction; ghép đúng `ContextSource`, `PooledContextSource`, `TransactionAwareContextSourceProxy`, `LdapTemplate` và `ContextSourceTransactionManager`; giữ service Bind ổn định trong pool; tách user Bind khỏi service connection; dùng `@Transactional` ở service boundary; kiểm tra quyền cho cả thao tác chính và thao tác bù; và xây dựng integration test chứng minh commit, rollback, pool return, identity isolation cùng cách xử lý lỗi.

## 1. Ba cơ chế phải phối hợp

| Cơ chế | Câu hỏi nó trả lời | Thành phần Spring LDAP |
| --- | --- | --- |
| **Authentication** | Connection đang thao tác dưới danh tính nào? | `LdapContextSource`, Bind credentials, `ContextSource.getContext(principal, credentials)` |
| **Connection pooling** | Có thể tái sử dụng context/connection nào? | `PooledContextSource` hoặc `PoolingContextSource` |
| **Compensating transaction** | Nếu một chuỗi thay đổi thất bại, có thể thực hiện thao tác bù nào? | `ContextSourceTransactionManager`, `TransactionAwareContextSourceProxy` |

Trong một ứng dụng thông thường, repository và `LdapTemplate` dùng một service account có quyền tối thiểu. Service account được cấu hình trên ContextSource đích và các read/write context của nó được pool. Khi một service method bắt đầu transaction, transaction manager gắn một `DirContext` vào transaction. Proxy giữ context đó mở trong suốt các operation, ghi nhận các thay đổi cần bù, rồi mới cho context đóng và trở về pool khi transaction hoàn tất.

User Bind có mục đích khác. Khi một nhân viên đăng nhập, ứng dụng kiểm tra credential của nhân viên bằng Bind với DN và password do người đó cung cấp. Kết quả Bind này không làm thay đổi service identity mà repository đang dùng.

## 2. Giao dịch LDAP có giới hạn gì?

### 2.1. Một LDAP update operation và một transaction nhiều operation

LDAP core protocol xử lý các operation như Add, Delete, Modify và ModifyDN theo từng operation. Một operation cập nhật một entry có semantics riêng; điều đó không có nghĩa một chuỗi nhiều operation trên nhiều entry tự động trở thành một transaction ACID.

RFC 5805 mô tả LDAP Transactions Extension với Start Transaction, Transaction Specification Control và End Transaction. RFC này được công bố ở trạng thái **Experimental**, không phải một tính năng bắt buộc của mọi LDAP server. Client chỉ có thể dùng extension đó khi server đích thực sự triển khai và công bố hỗ trợ.

Spring LDAP `ContextSourceTransactionManager` thực hiện một cơ chế khác: **client-side compensating transaction**. Server không nhận một transaction ID để gom nhiều operation thành một commit nguyên tử. Spring ghi lại trạng thái cần thiết trước mỗi thay đổi và thực hiện các operation bù nếu Spring transaction bị rollback.

### 2.2. Spring LDAP compensating transaction không phải ACID transaction phía server

Spring LDAP có thể giúp nhóm các thao tác ghi trong một service method và khôi phục nhiều thay đổi thông thường. Tuy nhiên, cơ chế này không cung cấp đầy đủ các bảo đảm của database transaction:

- **Không có isolation:** client khác vẫn có thể sửa cùng entry trong lúc transaction của ứng dụng đang chạy.
- **Không có server-side atomic commit:** LDAP server không biết toàn bộ chuỗi thao tác thuộc một transaction duy nhất.
- **Rollback cần kết nối hoạt động:** nếu mạng bị ngắt hoặc server không còn truy cập được khi cần thực hiện operation bù, Spring không thể bảo đảm khôi phục.
- **Operation bù cũng có thể thất bại:** ACL, schema, naming context, temporary DN hoặc trạng thái dữ liệu có thể khiến thao tác khôi phục bị từ chối.
- **Có overhead:** framework cần đọc/ghi thêm dữ liệu để ghi nhận trạng thái và thực hiện bù.

Vì vậy, hãy gọi đây là compensating transaction và kiểm thử khả năng khôi phục theo từng loại operation. Không quảng bá nó như một giao dịch LDAP ACID.

### 2.3. Khi nào nên dùng?

Hữu ích khi một use case cần nhiều LDAP write liên quan với nhau, ví dụ:

- Tạo user rồi thêm user vào group.
- Đổi DN rồi cập nhật các tham chiếu trong cùng directory.
- Cập nhật nhiều attribute và entry có quan hệ.
- Xóa hoặc thay thế entry trong một quy trình provisioning.

Nếu một request chỉ thực hiện một `modifyAttributes` độc lập, transaction manager thường không mang lại nhiều lợi ích. Hãy cân nhắc chi phí ghi nhận và rollback so với số operation thực tế.

## 3. Spring LDAP ghi nhận và bù từng operation như thế nào?

Transaction-aware proxy chặn các thao tác sửa đổi được hỗ trợ và ghi lại dữ liệu cần thiết trước khi thực hiện.

| LDAP operation | Chuẩn bị/commit | Thao tác bù khi rollback |
| --- | --- | --- |
| `bind` | Ghi nhận DN rồi tạo entry | `unbind` entry vừa tạo |
| `rename` | Ghi nhận DN cũ và DN mới rồi đổi tên | Rename entry về DN ban đầu |
| `unbind` | Ghi nhận DN cũ, chuyển entry sang DN tạm thời; khi commit mới xóa entry tạm | Rename entry từ DN tạm về DN cũ |
| `rebind` | Ghi nhận DN và attributes mới, chuyển entry cũ sang DN tạm; commit tạo entry mới và xóa bản tạm | Đưa entry cũ từ DN tạm về DN ban đầu |
| `modifyAttributes` | Ghi nhận DN và tạo các ModificationItem ngược | Thực hiện các modification ngược để phục hồi attribute |

Hai điểm có ảnh hưởng trực tiếp đến cấu hình:

1. Operation bù phải chạy được bằng **cùng service identity** mà transaction đang sử dụng.
2. Một số operation cần rename entry tạm thời. ACL phải cho phép thao tác rename và temporary DN phải hợp lệ trong schema/topology.

### 3.1. Temporary DN và quyền ACL

`DefaultTempEntryRenamingStrategy` thường thêm hậu tố vào RDN hiện tại. Ví dụ:

~~~text
DN ban đầu:
    uid=lan,ou=people,dc=example,dc=org

DN tạm:
    uid=lan_temp,ou=people,dc=example,dc=org
~~~

Ứng dụng cần bảo đảm:

- DN tạm không xung đột với entry khác.
- Schema cho phép giá trị RDN tạm.
- Service account có quyền rename vào DN tạm và rename trở lại.
- ACL cho phép các thao tác ghi/đọc phụ trợ mà recorder và executor cần.

Nếu xóa cây entry có nhiều cấp, chiến lược mặc định có thể không phù hợp. Không thể rename một entry cha khi nó vẫn còn children; với recursive delete, cần xem xét `DifferentSubtreeTempEntryRenamingStrategy` và chuẩn bị sẵn subtree tạm theo tài liệu Spring LDAP.

### 3.2. Quyền của thao tác chính chưa đủ

Ví dụ service account được phép xóa một entry nhưng không được rename entry đó. Operation `unbind` trong compensating transaction có thể cần rename sang DN tạm trước khi commit. Khi đó thao tác chính mà ứng dụng mong muốn có thể không hoàn tất theo cơ chế bù.

Hãy kiểm thử cả hai chiều:

- Operation nghiệp vụ có được phép không?
- Operation bù tương ứng có được phép không?

Không chỉ kiểm tra ACL bằng một lần gọi `delete` hoặc `modify` đơn lẻ.

## 4. Đường đi đúng của ContextSource, pool và transaction proxy

Một cấu hình có thể biểu diễn như sau:

~~~mermaid
flowchart TD
    BASE["LdapContextSource\nTLS + service DN/password"]
    POOL["PooledContextSource\npool read/write contexts"]
    PROXY["TransactionAwareContextSourceProxy"]
    TEMPLATE["LdapTemplate"]
    REPOS["Spring Data LDAP repositories"]
    TX["ContextSourceTransactionManager"]
    SERVICE["Transactional service"]
    AUTH["User Bind verifier"]

    BASE --> POOL
    POOL --> PROXY
    PROXY --> TEMPLATE
    TEMPLATE --> REPOS
    SERVICE --> REPOS
    SERVICE --> TEMPLATE
    TX --> POOL
    AUTH --> BASE
~~~

Thứ tự này là phần quan trọng nhất:

1. `LdapContextSource` tạo context với TLS và service credentials ổn định.
2. `PooledContextSource` bọc ContextSource đích để quản lý read-only/read-write contexts.
3. `TransactionAwareContextSourceProxy` bọc **chính instance pool đó**.
4. `LdapTemplate` dùng proxy transaction-aware.
5. Spring Data LDAP repositories dùng `LdapTemplate` này.
6. `ContextSourceTransactionManager` nhận **pool đích**, không nhận proxy transaction-aware.

Transaction manager và proxy phải cùng tham chiếu một ContextSource đích. Nếu chúng trỏ tới hai pool hoặc hai ContextSource khác nhau, transaction manager có thể giữ một context trong khi repository lại thao tác trên context khác.

### 4.1. Tại sao LdapTemplate phải dùng TransactionAwareContextSourceProxy?

Proxy này làm cho `DirContext` nhận được từ ContextSource biết transaction hiện tại:

- Trong transaction, context không bị đóng sau từng operation.
- Các modifying operations được ghi nhận để có thể thực hiện operation bù.
- Các lần gọi tiếp theo trong cùng transaction sử dụng context đã gắn với transaction.
- Khi transaction hoàn tất, context mới được đóng hoặc trả về pool.

Nếu `LdapTemplate` dùng thẳng `LdapContextSource` hoặc `PooledContextSource`, operation có thể chạy ngoài cơ chế ghi nhận compensating transaction.

### 4.2. Tại sao transaction manager nhận pool đích?

`ContextSourceTransactionManager` cần biết ContextSource thực tế mà transaction đang sử dụng. API của Spring LDAP yêu cầu `ContextSource` đưa vào manager là **target** của `TransactionAwareContextSourceProxy`. Khi dùng pool, target đó chính là `PooledContextSource`.

Không truyền proxy vào manager chỉ vì proxy là ContextSource mà LdapTemplate nhìn thấy. Dùng cùng target object làm khóa đồng bộ để manager và proxy tìm được cùng transaction-bound context.

## 5. Cấu hình Spring LDAP 4.x bằng Java

Ví dụ dưới đây dùng Spring LDAP pool2 (`PooledContextSource`) và một service account ổn định. Thay URL, base DN, secret, package scan và pool size theo môi trường thực tế.

### 5.1. Tạo ContextSource service

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ldap.core.support.LdapContextSource;

@Configuration
public class DirectoryTargetConfiguration {

    @Bean
    LdapContextSource serviceLdapContextSource() {
        LdapContextSource source = new LdapContextSource();
        source.setUrl("ldaps://directory.example.org:636");
        source.setBase("dc=example,dc=org");
        source.setUserDn(
            "uid=app-service,ou=services,dc=example,dc=org"
        );
        source.setPassword(loadServicePassword());

        // Pool Spring LDAP sẽ quản lý context.
        // Không bật native JNDI pooling ở ContextSource đích.
        source.setPooled(false);
        return source;
    }

    private String loadServicePassword() {
        // Đọc từ secret manager hoặc configuration binding của ứng dụng.
        return System.getenv("LDAP_SERVICE_BIND_PASSWORD");
    }
}
~~~

`loadServicePassword()` chỉ minh họa nguồn secret. Trong production, hãy dùng cơ chế quản lý secret của hệ thống và tránh log hoặc lưu password vào repository.

Nếu dùng StartTLS thay vì LDAPS, cấu hình `DirContextAuthenticationStrategy` phù hợp trên ContextSource đích. Dùng Spring LDAP pool để quản lý context; không bật native JNDI pooling cho context có StartTLS state.

### 5.2. Tạo pool2 và validator

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ldap.core.support.LdapContextSource;
import org.springframework.ldap.pool2.factory.PoolConfig;
import org.springframework.ldap.pool2.factory.PooledContextSource;
import org.springframework.ldap.pool2.validation.DefaultDirContextValidator;

@Configuration
public class DirectoryPoolConfiguration {

    @Bean
    PooledContextSource pooledContextSource(
            LdapContextSource serviceLdapContextSource) {

        PoolConfig config = new PoolConfig();
        config.setMaxTotal(24);
        config.setMaxTotalPerKey(12);
        config.setMaxIdlePerKey(8);
        config.setMinIdlePerKey(1);
        config.setMaxWaitMillis(2_000);
        config.setBlockWhenExhausted(true);
        config.setTestOnBorrow(true);
        config.setTestWhileIdle(true);
        config.setTimeBetweenEvictionRunsMillis(30_000);

        PooledContextSource pool = new PooledContextSource(config);
        pool.setContextSource(serviceLdapContextSource);
        pool.setDirContextValidator(new DefaultDirContextValidator());
        return pool;
    }
}
~~~

Các giá trị pool trong ví dụ là điểm bắt đầu để kiểm thử, không phải con số tối ưu cho mọi tải:

- `maxTotal` giới hạn tổng số context của pool.
- `maxTotalPerKey` giới hạn context theo pool key, thường tách read-only và read-write.
- `maxIdlePerKey` và `minIdlePerKey` điều khiển số context chờ.
- `maxWaitMillis` giới hạn thời gian request đợi context khi pool cạn.
- `testOnBorrow` xác minh context trước khi giao cho caller.
- `testWhileIdle` kiểm tra context đang idle theo chu kỳ eviction.

`DefaultDirContextValidator` thực hiện một Search kiểm tra nhỏ, mặc định với base rỗng, filter `objectclass=*`, giới hạn một kết quả và timeout ngắn. Nếu ACL của directory không cho phép Search ở base mặc định, hãy cấu hình validator/base/filter phù hợp với server đích. Validation thành công chỉ chứng minh context trả lời được phép kiểm tra đó; nó không chứng minh service account có đủ quyền cho mọi operation nghiệp vụ hoặc operation bù.

### 5.3. Tạo transaction-aware proxy, LdapTemplate và transaction manager

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.pool2.factory.PooledContextSource;
import org.springframework.ldap.transaction.compensating.manager.ContextSourceTransactionManager;
import org.springframework.ldap.transaction.compensating.manager.TransactionAwareContextSourceProxy;

@Configuration
public class DirectoryTransactionConfiguration {

    @Bean
    TransactionAwareContextSourceProxy transactionAwareContextSource(
            PooledContextSource pooledContextSource) {
        return new TransactionAwareContextSourceProxy(pooledContextSource);
    }

    @Bean
    LdapTemplate transactionalLdapTemplate(
            TransactionAwareContextSourceProxy transactionAwareContextSource) {
        return new LdapTemplate(transactionAwareContextSource);
    }

    @Bean
    ContextSourceTransactionManager ldapTransactionManager(
            PooledContextSource pooledContextSource) {
        return new ContextSourceTransactionManager(pooledContextSource);
    }
}
~~~

Hãy kiểm tra rằng:

- `transactionAwareContextSource` bọc bean `pooledContextSource`.
- `ldapTransactionManager` nhận đúng bean `pooledContextSource` đó.
- `transactionalLdapTemplate` dùng proxy transaction-aware.
- Không tạo một `PooledContextSource` mới riêng cho transaction manager.
- Không để một repository tự tạo `LdapTemplate` bằng ContextSource khác.

Constructor nhận `ContextSource` của `ContextSourceTransactionManager` là API hiện hành; constructor rỗng và setter cũ đã bị deprecated trong Spring LDAP 4.1 trở đi.

### 5.4. Cho Spring Data repositories dùng đúng LdapTemplate

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.ldap.repository.config.EnableLdapRepositories;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@Configuration
@EnableTransactionManagement
@EnableLdapRepositories(
    basePackages = "com.example.directory.repository",
    ldapTemplateRef = "transactionalLdapTemplate"
)
public class DirectoryRepositoryConfiguration {
}
~~~

Spring Data LDAP repositories mặc định tìm bean `ldapTemplate`. Khi template có tên khác, chỉ định `ldapTemplateRef` để repository dùng đúng template transaction-aware. Đừng để repository mặc định tự động lấy một `LdapTemplate` khác đang trỏ thẳng vào ContextSource đích.

Nếu ứng dụng chỉ có một `LdapTemplate`, có thể đặt tên bean là `ldapTemplate`; điều quan trọng vẫn là template đó phải được tạo từ `TransactionAwareContextSourceProxy`.

## 6. Dùng transaction ở service boundary

Transaction nên bao quanh một use case nghiệp vụ, thường ở service layer. Repository tiếp tục thực hiện một operation nhỏ; service quyết định nhiều operation nào cần được bù cùng nhau.

Ví dụ:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.ldap.core.LdapTemplate;
import javax.naming.directory.ModificationItem;

@Service
public class DirectoryProvisioningService {

    private final PersonRepository personRepository;
    private final LdapTemplate transactionalLdapTemplate;

    public DirectoryProvisioningService(
            PersonRepository personRepository,
            LdapTemplate transactionalLdapTemplate) {
        this.personRepository = personRepository;
        this.transactionalLdapTemplate = transactionalLdapTemplate;
    }

    @Transactional(transactionManager = "ldapTransactionManager")
    public void provision(PersonEntry person,
                          String groupDn,
                          ModificationItem[] membershipChanges) {

        personRepository.save(person);
        transactionalLdapTemplate.modifyAttributes(
            groupDn, membershipChanges
        );
    }
}
~~~

Trong ví dụ, repository và template phải dùng cùng `transactionalLdapTemplate`. Khi hai operation cùng nằm trong một transaction, proxy ghi nhận các thay đổi và transaction manager điều phối commit/rollback.

### 6.1. Spring AOP phải thực sự tạo transaction

`@Transactional` hoạt động thông qua proxy của Spring. Các điều kiện cần kiểm tra:

- Service là Spring bean được container quản lý.
- Method transaction được gọi từ bean khác qua proxy Spring.
- Method không phải private/final theo cách proxy đang sử dụng.
- Không gọi method transaction bằng self-invocation trong cùng object rồi kỳ vọng AOP tự mở transaction.
- Transaction manager được chỉ định đúng bằng `transactionManager = "ldapTransactionManager"` khi ứng dụng có nhiều manager.

Mặc định, Spring rollback với unchecked exception (`RuntimeException`) và `Error`. Nếu use case cần rollback với checked exception, khai báo `rollbackFor` phù hợp:

~~~java
@Transactional(
    transactionManager = "ldapTransactionManager",
    rollbackFor = Exception.class
)
public void provisionWithCheckedFailure(...) throws Exception {
    // Nhiều LDAP writes trong cùng transaction.
}
~~~

Không bắt exception rồi nuốt nó bên trong method nếu nghiệp vụ mong muốn Spring đánh dấu transaction rollback. Nếu cần chuyển lỗi, hãy ném exception phù hợp sau khi ghi nhận nguyên nhân.

### 6.2. Kiểm tra thao tác nào đi qua proxy

Các modifying operations được Spring LDAP compensating transaction hỗ trợ gồm:

- `bind`
- `unbind`
- `rebind`
- `rename`
- `modifyAttributes`

Nếu code gọi JNDI trực tiếp bằng một `DirContext` được tạo từ ContextSource khác, gọi một `LdapTemplate` không transaction-aware, hoặc gọi API ghi ngoài proxy, manager không tự động ghi nhận operation đó.

Đừng suy ra mọi side effect trong một method có `@Transactional` đều được hoàn tác. Chỉ những LDAP modifications đi qua đường truy cập được transaction-aware proxy quản lý mới tham gia cơ chế bù.

## 7. Authentication phải giữ đúng identity

### 7.1. Service Bind dùng cho repository và pool

Service account thường có identity ổn định:

~~~text
uid=app-service,ou=services,dc=example,dc=org
~~~

Các context được lấy qua `getReadOnlyContext()` và `getReadWriteContext()` từ pool đều dùng service identity này. Service account cần quyền đọc/ghi phù hợp với use case và các thao tác bù.

Đừng thay đổi Bind identity của một context đang nằm trong pool. Connection được trả lại pool có thể được request khác mượn; identity không được phép thay đổi ngoài lifecycle do ContextSource/pool quản lý.

### 7.2. User Bind dùng credential người dùng

Khi xác thực một nhân viên, ứng dụng dùng DN và password của nhân viên để tạo context xác thực riêng:

~~~java
import javax.naming.directory.DirContext;
import org.springframework.ldap.AuthenticationException;
import org.springframework.ldap.core.support.LdapContextSource;
import org.springframework.ldap.support.LdapUtils;

public final class DirectoryUserAuthenticator {

    private final LdapContextSource authenticationContextSource;

    public DirectoryUserAuthenticator(
            LdapContextSource authenticationContextSource) {
        this.authenticationContextSource = authenticationContextSource;
    }

    public boolean verify(String userDn, String suppliedPassword) {
        DirContext userContext = null;
        try {
            userContext = authenticationContextSource.getContext(
                userDn, suppliedPassword
            );
            return true;
        } catch (AuthenticationException ex) {
            return false;
        } finally {
            LdapUtils.closeContext(userContext);
        }
    }
}
~~~

Ví dụ này chỉ minh họa Bind verification. Trong ứng dụng thực tế, phân loại authentication rejection riêng với lỗi TLS, timeout, server unavailable và lỗi cấu hình; không biến mọi exception thành “sai password”.

User Bind không cần đọc `userPassword` hoặc tự so sánh hash. Directory xác minh credential qua Bind. Context xác thực phải được đóng sau khi dùng và không được chia sẻ giữa request.

### 7.3. User Bind không được mượn nhầm service pool

`PooledContextSource` pool các context lấy qua `getReadOnlyContext()` và `getReadWriteContext()` với giả định environment/identity ổn định theo pool key. Spring LDAP cảnh báo rằng dùng `AuthenticationSource` thay đổi credential theo thread/user với một pool như vậy không hoạt động như nhiều người mong đợi: pool có thể được tạo bằng credential của user đầu tiên và tái sử dụng cho request tiếp theo.

Vì vậy:

- Pool service account có identity ổn định.
- User authentication dùng `getContext(userDn, password)` theo đường riêng.
- Đóng user context sau khi Bind verification hoàn tất.
- Không lưu password người dùng trong pool/cache.
- Không rebind service pool context thành user identity.

Phương thức `getContext(principal, credentials)` là đường lấy context theo credential cụ thể, khác với hai pool path read-only/read-write. Hãy kiểm tra hành vi của phiên bản Spring LDAP đang dùng; không mặc định các user context được pool như service context.

### 7.4. Authentication không nên nằm trong transaction provisioning

Xác thực credential là một bước riêng. Không nên mở một compensating transaction cho các thao tác provisioning rồi đổi Bind identity của context đang được transaction giữ. Transaction provisioning cần dùng một service identity ổn định xuyên suốt từ đầu đến khi commit/rollback.

Một luồng điển hình:

1. Resolve DN của user theo filter an toàn.
2. User Bind để xác minh credential.
3. Tạo authenticated principal.
4. Kiểm tra authorization và policy.
5. Nếu cần provisioning, gọi service method riêng có transaction LDAP bằng service account.

### 7.5. Anonymous read-only có giới hạn với compensating transaction

Spring LDAP không hỗ trợ cấu hình `anonymous-read-only="true"` cùng compensating transaction support. Cấu hình này bị từ chối vì transaction cần context nhất quán để ghi nhận và thực hiện thao tác bù. Nếu ứng dụng cần anonymous read cho một use case công khai, hãy thiết kế ContextSource/read path riêng, ngoài luồng compensating transaction.

## 8. Pool và transaction cùng quản lý vòng đời context

### 8.1. Trong transaction, context được giữ đến khi hoàn tất

Với request không transaction, một operation thông thường lấy context, thực hiện Search/Modify rồi đóng context. Nếu ContextSource là pooled source, `close()` trả context về pool.

Trong compensating transaction:

1. Transaction manager lấy context từ ContextSource đích.
2. Context được gắn với transaction hiện tại.
3. `LdapTemplate` lấy context qua transaction-aware proxy.
4. Các operation trong cùng transaction dùng lại context đã gắn.
5. `close()` do template gọi không làm context bị trả về pool giữa transaction.
6. Khi transaction commit/rollback và cleanup hoàn tất, context được đóng.
7. Pooled context trả về pool hoặc bị loại nếu connection không còn hợp lệ.

### 8.2. Vì sao transaction dài có thể làm pool cạn?

Một transaction giữ context trong suốt thời gian chạy. Nếu service method vừa thực hiện LDAP writes, vừa gọi HTTP API, chờ message broker hoặc xử lý file lâu, context vẫn bị giữ và không thể phục vụ request khác.

Hãy:

- Giữ transaction ngắn và chỉ bao gồm các operation LDAP cần phối hợp.
- Không gọi dịch vụ ngoài hoặc chờ người dùng bên trong transaction.
- Đặt `maxWaitMillis` hữu hạn để request không chờ vô hạn khi pool cạn.
- Sizing pool theo số transaction đồng thời và traffic ngoài transaction.
- Theo dõi số context active, idle và số waiter.

### 8.3. Ước lượng dung lượng pool

~~~text
Pool capacity
    >= concurrent LDAP transactions
     + concurrent non-transaction LDAP operations
     + operational headroom
~~~

Đây là cách ước lượng tài nguyên, không phải công thức chính xác cho mọi pool. Pool2 có thể tách read-only và read-write context theo key; hãy kiểm tra `maxTotal`, `maxTotalPerKey`, loại context mà transaction manager mượn và tổng số application instances.

Ví dụ, nếu mỗi instance có tối đa 10 transaction đồng thời và 6 request đọc ngoài transaction, không nên cấu hình pool chỉ đủ 10 context. Cần tính cả các request ngoài transaction, hoạt động nền, validation và headroom cho biến động tải.

## 9. Những lỗi cấu hình khiến các lớp không phối hợp

| Cấu hình/lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| Transaction manager nhận `TransactionAwareContextSourceProxy` thay vì target | Transaction manager và proxy có thể không đồng bộ cùng ContextSource | Manager nhận đúng target pool |
| LdapTemplate dùng ContextSource thô | Modifying operations không được proxy ghi nhận | Tạo template từ transaction-aware proxy |
| Repository dùng template khác | Repository write thoát khỏi transaction | Đặt `ldapTemplateRef` rõ ràng |
| Tạo hai PooledContextSource riêng | Manager và repository dùng hai pool/context khác nhau | Dùng cùng một bean pool |
| Pool dùng credential thay đổi theo thread | Context của user này có thể được cấp cho user khác | Pool service identity ổn định; user Bind riêng |
| Chia sẻ `DirContext` giữa thread | Context không thread-safe và có state Bind | Để ContextSource/template quản lý borrow/return |
| Bật native JNDI pooling cùng Spring pool | Khó kiểm soát validation/lifecycle, pool chồng lớp | Tắt native pooling, dùng một Spring pool |
| Bắt exception rồi nuốt trong `@Transactional` | Spring có thể commit dù nghiệp vụ đã lỗi | Ném exception hoặc đánh dấu rollback rõ ràng |
| Gọi transactional method qua self-invocation | AOP proxy không mở transaction như mong đợi | Gọi qua Spring bean proxy |
| Service account không có quyền rename tạm | Rollback `unbind`/`rebind` có thể thất bại | Cấp ACL cần thiết và test operation bù |
| Pool không validate connection stale | Request mượn connection đã bị server/network đóng | Bật validator và eviction hợp lý |
| Pool wait vô hạn | Request có thể treo khi pool cạn | Đặt max wait và application deadline |
| anonymous-read-only cùng compensating tx | Cấu hình không được hỗ trợ | Tách anonymous read path |
| Transaction quá dài | Giữ context lâu, làm pool cạn | Giới hạn phạm vi và thời lượng transaction |

## 10. Kiểm chứng bằng integration test

Unit test mock `LdapTemplate` không chứng minh pool, proxy, transaction manager và LDAP server thật phối hợp. Cần integration test tạo Spring context với các bean thật và một LDAP test server có schema phù hợp. Với ACL, password policy, rename subtree hoặc behavior đặc thù, hãy kiểm thử thêm trên đúng loại directory server triển khai.

### 10.1. Bộ dữ liệu và danh tính test

Tạo các entry riêng:

~~~text
Service account:
    uid=app-service,ou=services,dc=example,dc=org
    Quyền đọc/ghi nhánh people và group theo use case.

User account Lan:
    uid=lan,ou=people,dc=example,dc=org
    Password test hợp lệ.

Group:
    cn=engineering,ou=groups,dc=example,dc=org
    Attribute member chứa DN user.

Temporary subtree:
    ou=tempEntries,dc=example,dc=org
    Chỉ cần nếu dùng DifferentSubtreeTempEntryRenamingStrategy.
~~~

Không dùng credential production trong integration test. Service account test cần đủ quyền cho cả operation nghiệp vụ và operation bù.

### 10.2. Ma trận kiểm thử

| ID | Kịch bản | Kết quả cần xác minh |
| --- | --- | --- |
| CFG01 | ContextSource đích dùng service DN/secret hợp lệ | Service Bind thành công |
| CFG02 | Pool bọc đúng ContextSource đích | Read/write context được lấy từ pool |
| CFG03 | Transaction manager nhận cùng pool bean | Transaction bắt đầu trên đúng ContextSource |
| CFG04 | Transaction-aware proxy bọc cùng pool | Context trong transaction được giữ lại |
| CFG05 | Repository dùng transactional LdapTemplate | Repository writes được ghi nhận |
| CFG06 | LdapTemplate thô được dùng nhầm | Test chứng minh operation không tham gia transaction; sửa wiring |
| AUTH01 | User Bind bằng password đúng | Bind thành công |
| AUTH02 | User Bind bằng password sai | Authentication bị từ chối |
| AUTH03 | Service Bind đúng, user Bind sai | Không tạo authenticated principal |
| AUTH04 | User Bind đúng, service account thiếu quyền Search | Authentication và service authorization được phân biệt |
| AUTH05 | User Bind rồi đóng context | Không làm thay đổi service identity trong pool |
| AUTH06 | AuthenticationSource trả credential khác theo thread | Không dùng chung pool service cho dynamic user credentials |
| AUTH07 | Anonymous read-only cùng compensating tx | Cấu hình bị từ chối hoặc test xác nhận không bật kết hợp này |
| POOL01 | Borrow context và đóng ngoài transaction | Context trở về pool |
| POOL02 | Nhiều LDAP operations trong một transaction | Dùng context transaction-bound cho toàn bộ chuỗi |
| POOL03 | Commit transaction | Thay đổi LDAP được lưu và context trở về pool |
| POOL04 | Rollback sau bind | Entry mới được unbind |
| POOL05 | Rollback sau rename | Entry được rename về DN cũ |
| POOL06 | Rollback sau modifyAttributes | Attribute được khôi phục |
| POOL07 | Rollback sau unbind | Entry được rename từ DN tạm về DN ban đầu |
| POOL08 | Rollback sau rebind | Entry cũ được phục hồi theo recorder |
| POOL09 | Service method ném RuntimeException | Spring thực hiện rollback |
| POOL10 | Service method ném checked exception | Rollback theo rollbackFor đã cấu hình |
| POOL11 | Exception bị catch và nuốt | Test chứng minh commit có thể xảy ra; sửa error handling |
| POOL12 | Gọi method transaction bằng self-invocation | Test xác nhận transaction proxy không được kích hoạt như lời gọi qua bean khác |
| POOL13 | Context bị đóng trong transaction | Context không bị trả về pool trước transaction completion |
| POOL14 | Transaction commit/rollback xong | Active count trở về baseline dự kiến |
| POOL15 | Pool max active đạt giới hạn | Request chờ tối đa maxWait rồi xử lý lỗi exhaustion |
| POOL16 | Server đóng connection idle | Validation loại connection stale |
| POOL17 | Validator không có quyền Search base | Validation failure được phân loại; cấu hình validator/ACL được sửa |
| TX01 | Hai transaction sửa cùng entry đồng thời | Xác nhận không có isolation; xử lý conflict theo nghiệp vụ |
| TX02 | Mạng bị ngắt sau operation ghi | Không giả định rollback chắc chắn thành công |
| TX03 | Operation bù bị ACL từ chối | Ghi nhận rollback failure và tạo quy trình reconciliation |
| TX04 | Rebind trong subtree có children | Chọn renaming strategy phù hợp |
| TX05 | Recursive delete | Temporary subtree và quyền rename được kiểm tra |
| TX06 | Repository và LdapTemplate cùng service method | Cả hai đi qua cùng transaction-aware template |
| TX07 | Hai application instances cùng chạy test | Không giả định pool là cluster-wide; mỗi instance có pool riêng |
| TX08 | Shutdown application | Pool destroy và connection được giải phóng |

### 10.3. Test commit

Một test commit nên:

1. Gọi service method qua Spring bean proxy.
2. Thực hiện `repository.save(person)`.
3. Thực hiện `modifyAttributes` trên group bằng cùng `LdapTemplate`.
4. Để method kết thúc bình thường.
5. Search lại LDAP bằng context mới.
6. Xác nhận entry và membership đều tồn tại.
7. Kiểm tra context đã được trả về pool.

Không chỉ assert giá trị trả về từ repository trong cùng transaction; cần đọc lại từ một operation ngoài transaction để chứng minh commit đã hoàn tất.

### 10.4. Test rollback có chủ đích

Một test rollback nên:

1. Seed trạng thái ban đầu.
2. Gọi service method transaction-aware.
3. Thực hiện ít nhất hai modifying operations.
4. Ném `RuntimeException` sau operation thứ hai để kích hoạt rollback.
5. Bắt exception ở test boundary.
6. Dùng Search ngoài transaction để đọc lại trạng thái.
7. Xác nhận tất cả thay đổi được bù trong trường hợp test.
8. Xác nhận context được trả về pool sau cleanup.

Ví dụ pseudocode:

~~~text
service.provisionAndFail(person, groupDn)

    transaction begins
    repository.save(person)
    ldapTemplate.modifyAttributes(groupDn, addMember)
    throw IllegalStateException

transaction manager performs compensation
transaction cleanup closes transaction-bound context
pool receives the context or discards it if invalid

assert person entry does not exist
assert group membership is unchanged
assert pool active count returned to baseline
~~~

Test này chỉ chứng minh rollback hoạt động trong điều kiện test. Nó không chứng minh rollback luôn thành công khi network hoặc LDAP server bị lỗi.

### 10.5. Kiểm tra pool active/idle và context leak

`PooledContextSource` pool2 cung cấp các số liệu như:

- `getNumActive()`
- `getNumActiveRead()`
- `getNumActiveWrite()`
- `getNumIdle()`
- `getNumIdleRead()`
- `getNumIdleWrite()`
- `getNumWaiters()`

Trong integration test tuần tự:

1. Ghi baseline active/idle.
2. Bắt đầu transaction và thực hiện LDAP operation.
3. Quan sát active context tăng trong lúc transaction đang giữ context.
4. Kết thúc transaction.
5. Chờ cleanup đồng bộ hoàn tất.
6. Xác nhận active count quay về baseline và idle count phù hợp.

Không assert con số tuyệt đối khi test chạy song song với các test khác. Dùng test cô lập hoặc kiểm tra delta/baseline.

## 11. Xử lý lỗi và reconciliation

### 11.1. Phân biệt lỗi operation và lỗi compensation

Một transaction có thể thất bại ở hai giai đoạn:

- **Original operation failure:** operation nghiệp vụ bị từ chối, timeout hoặc lỗi schema/ACL.
- **Compensation failure:** operation bù không thể phục hồi trạng thái ban đầu.

Nếu compensation thất bại, đừng chỉ log exception ban đầu rồi trả một lỗi chung. Cần giữ cả nguyên nhân ban đầu và lỗi rollback, correlation ID, loại operation và trạng thái đã biết của entry.

### 11.2. Mất kết nối khi rollback

Ví dụ:

1. Server đã áp dụng `modifyAttributes`.
2. Client mất kết nối trước khi nhận response.
3. Spring không biết chắc operation đã được áp dụng hay chưa.
4. Context không còn hoạt động để gửi modification ngược.

Trong tình huống này, transaction manager không thể bảo đảm phục hồi. Hãy đưa use case vào trạng thái cần đối soát, đọc lại trạng thái từ directory khi kết nối phục hồi và chạy reconciliation có kiểm soát.

### 11.3. Không có isolation

Giả sử transaction A đọc `departmentNumber=D01`, transaction B đổi thành `D02`, rồi A rollback bằng modification ngược dựa trên giá trị trước đó. Vì không có isolation, operation bù có thể ghi đè thay đổi hợp lệ của B.

Giảm rủi ro bằng:

- Giữ transaction ngắn.
- Hạn chế nhiều transaction cùng sửa một entry.
- Dùng assertion control/version attribute khi server và client hỗ trợ.
- Kiểm tra trạng thái trước khi chạy compensation.
- Có audit và reconciliation cho conflict.

Compensating transaction không thay thế locking/versioning của nghiệp vụ.

### 11.4. Pool hết context không phải authentication failure

Khi pool cạn, request có thể chờ `maxWaitMillis` rồi nhận lỗi resource acquisition/exhaustion. Không chuyển lỗi này thành “sai password” hoặc “không tìm thấy user”.

Phân loại riêng:

| Nhóm lỗi | Ví dụ | Cách xử lý |
| --- | --- | --- |
| Authentication | User Bind bị từ chối | Trả kết quả đăng nhập thất bại theo policy |
| Service Bind | Service secret sai/expired | Cảnh báo dependency/configuration |
| Pool exhaustion | Không có context rảnh trước max wait | Backpressure, sizing, tìm transaction dài/leak |
| Validation | Connection stale hoặc Search validation thất bại | Loại connection, kiểm tra ACL/validator |
| LDAP operation | Schema, ACL, duplicate DN | Xử lý theo operation và directory state |
| Compensation | Rename/modify ngược bị từ chối | Báo rollback failure và reconciliation |
| Transport | TLS/timeout/network | Xử lý dependency; không giả định rollback thành công |

## 12. Kết hợp LDAP với SQL hoặc dịch vụ khác

Một service method có thể thay đổi cả LDAP và SQL. Tuy nhiên, Spring LDAP 4.0 đã loại bỏ hỗ trợ JDBC transaction integration cũ. Không lấy ví dụ `ContextSourceAndDataSourceTransactionManager` từ tài liệu phiên bản cũ rồi áp vào Spring LDAP 4.x.

Compensating transaction của LDAP cũng không phải XA/2PC. Nếu một use case thay đổi LDAP và database:

- Thiết kế trạng thái nghiệp vụ và bước bù cho từng resource.
- Dùng outbox/saga hoặc workflow có thể tiếp tục sau lỗi.
- Làm operation idempotent để có thể retry/reconcile.
- Ghi correlation ID và trạng thái từng bước.
- Không tuyên bố hai resource được commit nguyên tử nếu không có distributed transaction protocol thực sự.

RFC 5805 LDAP Transactions Extension cũng không tự biến Spring LDAP compensating transaction thành XA. Đây là một extension LDAP riêng, trạng thái Experimental, và phải được hỗ trợ ở server/client tương ứng.

## 13. Observability cho pool, authentication và transaction

Theo dõi ba nhóm số liệu riêng:

| Metric/log | Câu hỏi cần trả lời |
| --- | --- |
| Pool active read/write | Bao nhiêu context đang được mượn? |
| Pool idle read/write | Bao nhiêu context sẵn sàng tái sử dụng? |
| Pool waiters và borrow latency | Request có phải chờ pool? |
| Pool validation failures | Bao nhiêu connection stale/không hợp lệ bị loại? |
| Service Bind failures | Service credentials có vấn đề không? |
| User Bind failures | Authentication rejection tăng bất thường không? |
| Transaction duration | Transaction nào giữ context quá lâu? |
| Commit/rollback count | Bao nhiêu transaction thành công hoặc bị rollback? |
| Compensation failures | Có thao tác bù nào thất bại? |
| Reconciliation backlog | Bao nhiêu use case cần đối soát thủ công/tự động? |

Không gắn password, raw Bind credentials hoặc full DN có thông tin nhạy cảm vào metric labels. Dùng operation type, directory alias, pool key và error category có cardinality thấp.

### 13.1. Audit transaction

Một audit event có thể ghi:

~~~text
transactionId
correlationId
serviceIdentityAlias
operationTypes
startedAt
completedAt
outcome = COMMITTED | ROLLED_BACK | COMPENSATION_FAILED
compensationCount
failureCategory
reconciliationRequired
~~~

Đây là schema minh họa do ứng dụng định nghĩa. Không lưu password hoặc credential vào audit.

## 14. Các anti-pattern cần tránh

| Anti-pattern | Vì sao nguy hiểm? | Thiết kế đúng |
| --- | --- | --- |
| Dùng transaction manager với một pool, repository với pool khác | Hai bên không chia sẻ transaction-bound context | Dùng một target pool bean |
| LdapTemplate không dùng transaction-aware proxy | Modifications không được recorder theo dõi | Tạo template từ proxy |
| Repository tự dùng template mặc định khác | Repository writes có thể thoát transaction | Khai báo `ldapTemplateRef` |
| Dùng dynamic user credentials trong service pool | Có nguy cơ mượn context sai identity | Pool một service identity ổn định |
| Đổi Bind identity giữa transaction | Transaction không còn security context nhất quán | Giữ service Bind cố định |
| Dùng user Bind context cho service pool | Rò identity/ACL giữa người dùng | User Bind riêng và đóng context |
| Nghĩ rollback là server-side atomic | Mất mạng có thể làm mất khả năng bù | Thiết kế reconciliation |
| Nghĩ rollback có isolation | Client khác vẫn sửa cùng entry | Version/assertion/conflict handling |
| Không cấp quyền rename tạm | Unbind/rebind compensation có thể thất bại | Test ACL cho thao tác bù |
| Dùng default rename strategy cho recursive delete | Entry cha có children không thể rename theo cách đó | Dùng chiến lược subtree phù hợp |
| Transaction bao gồm HTTP call lâu | Context bị giữ, pool cạn | Giữ transaction ngắn |
| Pool wait vô hạn | Request treo khi pool exhausted | Đặt max wait và deadline |
| Nuốt exception bên trong transaction | Spring có thể commit | Ném lỗi hoặc mark rollback |
| Gọi method transaction bằng self-invocation | Transaction proxy không được kích hoạt | Gọi qua Spring bean |
| Coi pool exhaustion là sai password | Sai phân loại và che sự cố tải | Phân loại pool/resource failure |
| Dùng API transaction JDBC cũ trên Spring LDAP 4.x | Tích hợp đã bị loại bỏ | Dùng saga/outbox cho cross-resource workflow |

## 15. Checklist triển khai

1. **Service identity ổn định:** repository và transaction dùng cùng service account.
2. **TLS đúng:** LDAPS hoặc StartTLS được cấu hình trên ContextSource đích; không fallback plaintext.
3. **Một pool:** chỉ có một `PooledContextSource` target cho đường transaction.
4. **Native pooling tắt:** không chồng JNDI native pooling lên Spring pool.
5. **Pool validation:** bật validator phù hợp với ACL và server.
6. **Proxy đúng:** `TransactionAwareContextSourceProxy` bọc pool target.
7. **Manager đúng target:** `ContextSourceTransactionManager` nhận đúng pool target, không nhận proxy.
8. **Template đúng:** `LdapTemplate` dùng transaction-aware proxy.
9. **Repository đúng:** `@EnableLdapRepositories` tham chiếu transactional template.
10. **Transaction ở service:** đặt `@Transactional` quanh use case nhiều operation.
11. **AOP hoạt động:** gọi method qua Spring proxy; không dựa vào self-invocation.
12. **Rollback policy:** kiểm tra RuntimeException/checked exception và `rollbackFor`.
13. **ACL đủ cho operation bù:** kiểm tra rename, temporary DN, modify ngược và delete.
14. **Authentication riêng:** user Bind dùng DN/password người dùng; không trộn vào service pool.
15. **Pool sizing:** tính cả transaction đồng thời và request ngoài transaction.
16. **Transaction ngắn:** không chờ HTTP, message broker hoặc user input trong khi giữ context.
17. **Test commit:** đọc lại bằng context ngoài transaction.
18. **Test rollback:** kiểm tra state directory sau exception.
19. **Test pool return:** active count trở về baseline sau commit/rollback.
20. **Test compensation failure:** có audit và reconciliation path.
21. **Test concurrency:** hiểu và xử lý việc không có isolation.
22. **Cross-resource workflow:** không giả định XA/2PC; dùng saga/outbox khi cần.

## 16. Câu hỏi tự kiểm tra

1. **Spring LDAP compensating transaction là gì?** Cơ chế client-side ghi nhận trạng thái trước khi sửa và thực hiện operation bù khi rollback.
2. **Nó có phải transaction ACID phía LDAP server không?** Không; server không biết transaction của Spring và không cung cấp isolation.
3. **ContextSourceTransactionManager phải nhận ContextSource nào?** ContextSource đích thực tế, tức target của TransactionAwareContextSourceProxy.
4. **LdapTemplate phải dùng ContextSource nào?** TransactionAwareContextSourceProxy bọc đúng target mà transaction manager sử dụng.
5. **Tại sao manager và proxy phải dùng cùng pool instance?** Để cùng nhận diện và chia sẻ context được gắn với transaction.
6. **Spring LDAP intercept những modifying operations nào?** bind, unbind, rebind, rename và modifyAttributes.
7. **Tại sao unbind/rebind cần temporary DN?** Để giữ entry gốc có thể phục hồi khi rollback, kể cả khi không thể đọc đủ mọi attribute để tạo lại entry.
8. **Tại sao service account cần quyền rename?** Một số operation bù phải chuyển entry đến DN tạm rồi đưa trở lại.
9. **Khi transaction đang chạy, context có được trả pool sau từng operation không?** Không; transaction-aware proxy giữ context đến khi transaction kết thúc.
10. **Điều gì xảy ra nếu transaction kéo dài?** Context bị giữ lâu và pool có thể cạn.
11. **Repository có tự tham gia transaction nếu dùng LdapTemplate khác không?** Không; repository phải dùng transactional template.
12. **User Bind có dùng service identity trong pool không?** Không; user Bind xác minh credential riêng và context phải được đóng.
13. **Có nên dùng AuthenticationSource động theo thread với service pool không?** Không; pool giả định environment ổn định theo read-only/read-write key.
14. **Pool validation chứng minh điều gì?** Context trả lời được operation kiểm tra; không chứng minh mọi ACL hay operation bù đều thành công.
15. **Rollback có luôn thành công khi network bị ngắt không?** Không; connection failure có thể làm mất khả năng thực hiện compensation.
16. **Spring compensating transaction có isolation không?** Không; client khác có thể sửa cùng entry trong thời gian transaction chạy.
17. **Vì sao recursive delete có thể cần DifferentSubtreeTempEntryRenamingStrategy?** Entry cha có children không thể được rename theo cách thêm suffix trong cùng subtree.
18. **Nếu exception bị catch và nuốt trong method transaction thì sao?** Spring có thể không rollback theo mặc định; phải ném exception hoặc đánh dấu rollback.
19. **Có thể dùng transaction JDBC integration cũ trong Spring LDAP 4.x không?** Không; hỗ trợ đó đã bị loại bỏ từ Spring LDAP 4.0.
20. **Khi nào cần reconciliation?** Khi compensation thất bại hoặc outcome không xác định, ví dụ mất kết nối sau khi server có thể đã áp dụng write.

## Tài liệu tham khảo

- [Spring LDAP 4.2 — Transaction Support](https://docs.spring.io/spring-ldap/reference/transaction-support.html)
- [Spring LDAP — ContextSourceTransactionManager API](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/transaction/compensating/manager/ContextSourceTransactionManager.html)
- [Spring LDAP — TransactionAwareContextSourceProxy API](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/transaction/compensating/manager/TransactionAwareContextSourceProxy.html)
- [Spring LDAP — Pooling Support](https://docs.spring.io/spring-ldap/reference/pooling.html)
- [Spring LDAP — PooledContextSource API](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/pool2/factory/PooledContextSource.html)
- [Spring LDAP — PoolConfig API](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/pool2/factory/PoolConfig.html)
- [Spring Data LDAP — Configuration](https://docs.spring.io/spring-data/ldap/reference/ldap/configuration.html)
- [RFC 4511 — Lightweight Directory Access Protocol: The Protocol](https://www.rfc-editor.org/rfc/rfc4511.html)
- [RFC 5805 — Lightweight Directory Access Protocol Transactions (Experimental)](https://www.rfc-editor.org/rfc/rfc5805.html)

**Ghi nhớ:** Muốn pool, authentication và compensating transaction phối hợp đúng, hãy giữ service Bind ổn định, pool đúng một ContextSource đích, bọc pool bằng TransactionAwareContextSourceProxy, cho cả LdapTemplate và Spring Data repositories dùng proxy đó, rồi truyền chính pool target vào ContextSourceTransactionManager. User Bind phải đi theo đường xác thực riêng và context phải được đóng sau khi kiểm tra credential. Transaction giữ một context đến khi commit/rollback rồi mới trả về pool; vì vậy cần pool sizing, validation, timeout và transaction duration phù hợp. Spring LDAP rollback bằng operation bù phía client, không có isolation và không thể bảo đảm khôi phục khi kết nối mất hoặc operation bù bị từ chối. Hãy kiểm thử commit, rollback, ACL cho temporary DN, identity isolation, pool return và reconciliation trên đúng directory server triển khai.
