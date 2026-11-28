# Phối hợp pool với StartTLS và giao dịch bù trừ

Một ứng dụng Spring Boot kết nối tới LDAP bằng StartTLS. Mỗi request tạo một DirContext, nâng cấp kết nối lên TLS, bind bằng service account rồi thực hiện một vài thao tác. Cách này bảo vệ dữ liệu trên đường truyền nhưng tốn thời gian vì mỗi kết nối mới đều phải thực hiện TLS handshake. Nhóm phát triển bật connection pooling có sẵn của JNDI để giảm độ trễ, sau đó phát hiện một số request nhận lại context có trạng thái TLS không như mong đợi.

Một luồng nghiệp vụ khác cần tạo entry nhân viên rồi thêm DN của nhân viên vào nhóm. Nếu thao tác thứ hai thất bại, ứng dụng muốn hoàn tác thao tác đầu tiên. LDAP không cung cấp transaction ACID tổng quát cho chuỗi thao tác này; Spring LDAP hỗ trợ **compensating transaction** ở phía client bằng cách ghi nhận trạng thái và thực hiện thao tác bù khi rollback.

Trong chương **Pool kết nối** của module **SPRING_DATA_LDAP**, bài này kết hợp ba thành phần: StartTLS để bảo vệ kết nối, Spring LDAP pool để tái sử dụng các context đã được bảo vệ, và ContextSourceTransactionManager để quản lý các thao tác bù trừ. Bạn sẽ hiểu vòng đời của một context, cách cấu hình pool, cách giữ cùng context trong một giao dịch, giới hạn của rollback và cách kiểm thử cả ba thành phần.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Mô tả vòng đời LDAP connection khi dùng StartTLS.
2. Giải thích vì sao JNDI native connection pooling không phù hợp với context có trạng thái StartTLS.
3. Cấu hình LdapContextSource với DefaultTlsDirContextAuthenticationStrategy.
4. Dùng PooledContextSource của Spring LDAP để tái sử dụng context đã được nâng cấp TLS.
5. Chọn giới hạn pool, validation, timeout và eviction phù hợp.
6. Kết hợp pool với TransactionAwareContextSourceProxy và ContextSourceTransactionManager.
7. Viết service dùng @Transactional để gom nhiều thao tác LDAP và kích hoạt compensation khi lỗi.
8. Giải thích những tình huống compensation không thể khôi phục dữ liệu.
9. Kiểm thử TLS handshake, pool reuse, pool exhaustion, rollback và lỗi kết nối.

## 2. StartTLS thay đổi trạng thái của một kết nối LDAP

StartTLS là LDAP Extended Operation cho phép nâng cấp một kết nối LDAP đang dùng sang TLS mà không cần mở một socket LDAP-over-SSL riêng. Khác với LDAPS, StartTLS bắt đầu bằng URL ldap:// và yêu cầu client thực hiện TLS handshake trước khi gửi thông tin xác thực hoặc dữ liệu nhạy cảm.

Vòng đời thông thường:

~~~mermaid
sequenceDiagram
    participant App as Spring application
    participant CS as ContextSource
    participant LDAP as LDAP server
    App->>CS: getReadWriteContext()
    CS->>LDAP: TCP connect + LDAP connection
    CS->>LDAP: StartTLS ExtendedRequest
    LDAP-->>CS: StartTLS ExtendedResponse
    CS->>LDAP: TLS handshake + certificate validation
    CS->>LDAP: Bind SIMPLE trên TLS
    LDAP-->>CS: Bind success
    App->>LDAP: Search / Modify / Rename
    LDAP-->>App: LDAP result
    App->>CS: close DirContext
~~~

Điểm quan trọng là **bind SIMPLE phải diễn ra sau khi TLS handshake thành công**. Nếu TLS handshake thất bại, ứng dụng phải dừng thao tác và đóng context; không tự động tiếp tục bind qua kết nối LDAP plaintext.

### 2.1. StartTLS và LDAPS khác nhau ở thời điểm nâng cấp

| Đặc điểm | StartTLS | LDAPS |
| --- | --- | --- |
| URL | ldap://host:389 | ldaps://host:636 |
| Bắt đầu kết nối | LDAP connection thường, sau đó gửi StartTLS Extended Operation. | TLS handshake ngay khi mở socket. |
| Thời điểm bind | Sau khi StartTLS handshake thành công. | Sau khi TLS handshake thành công. |
| Trạng thái kết nối | Cùng một LDAP association được nâng cấp. | LDAP chạy bên trong TLS từ đầu. |
| Pooling | Phải giữ và tái sử dụng đúng context đã được nâng cấp. | Cũng cần pool hỗ trợ TLS; không dùng JNDI native pooling theo cách không theo dõi trạng thái TLS. |

StartTLS không phải là một thao tác chỉ kiểm tra certificate rồi kết thúc. TLS session tiếp tục bảo vệ các LDAP operation trên chính connection đó cho đến khi TLS được đóng hoặc connection bị đóng.

### 2.2. Không đóng TLS layer khi context còn được tái sử dụng

JNDI StartTlsResponse.close() đóng TLS layer và quay lại LDAP connection bên dưới. Sau lệnh này, các LDAP operation tiếp theo trên context có thể không còn được mã hóa. Vì vậy, khi Spring LDAP đang quản lý StartTLS và pool, không tự lấy StartTlsResponse rồi gọi close() ở cuối từng request.

Hãy để DirContextAuthenticationStrategy của Spring LDAP quản lý StartTLS và vòng đời context. Khi context được trả về pool, connection cần tiếp tục ở trạng thái bảo vệ TLS để lần mượn tiếp theo không sử dụng nhầm một kết nối plaintext.

## 3. Vì sao JNDI native pooling không phù hợp với StartTLS?

JNDI LDAP provider có cơ chế pooling tích hợp, thường bật bằng thuộc tính com.sun.jndi.ldap.connect.pool. Cơ chế này tái sử dụng connection nhưng không theo dõi mọi thay đổi trạng thái được thực hiện sau khi context đã được tạo.

Oracle JNDI cảnh báo không dùng native pooling cho context mà ứng dụng sẽ thay đổi trạng thái connection, ví dụ:

- Gọi StartTLS Extended Operation trên context.
- Thay đổi java.naming.security.principal.
- Thay đổi java.naming.security.protocol.

Provider không quản lý các thay đổi trạng thái đó như một phần của pool key/lifecycle. Một connection đã được nâng cấp TLS hoặc thay đổi security properties có thể bị tái sử dụng trong trạng thái ngoài dự kiến.

Với Spring LDAP:

- Giữ native-pooling tắt (setPooled(false) trong Java configuration).
- Dùng pool do Spring LDAP quản lý, tức PooledContextSource hoặc cấu hình namespace pooling tương ứng.
- Đặt StartTLS authentication strategy ở LdapContextSource nền; pool lấy context đã được strategy xử lý.

Spring LDAP khuyến nghị dùng pool riêng của framework khi dùng TLS authentication strategy. Pool này biết context được tạo bởi ContextSource nào, hỗ trợ validation và quản lý thời điểm trả context về pool.

## 4. Vai trò của từng thành phần

~~~text
LdapTemplate
    |
    v
TransactionAwareContextSourceProxy
    |
    v
PooledContextSource
    |
    v
LdapContextSource
    |
    +-- URL ldap://...
    +-- StartTLS authentication strategy
    +-- Bind service account sau TLS handshake
~~~

| Thành phần | Trách nhiệm |
| --- | --- |
| LdapContextSource | Tạo DirContext/LdapContext, mở kết nối LDAP và áp dụng authentication strategy. |
| DefaultTlsDirContextAuthenticationStrategy | Gửi StartTLS, thương lượng TLS, kiểm tra certificate/hostname và bind SIMPLE trên kênh TLS. |
| PooledContextSource | Giữ các DirContext đã được tạo, cho mượn và nhận lại context, kiểm tra context cũ và loại bỏ context hỏng. |
| TransactionAwareContextSourceProxy | Giữ context được mượn trong suốt transaction và ghi nhận các thao tác sửa đổi để có thể bù trừ. |
| ContextSourceTransactionManager | Điều phối transaction phía client, commit hoặc thực hiện compensation khi rollback. |
| LdapTemplate | Thực hiện LDAP operation thông qua context source đã được cấu hình. |

Thứ tự bọc có ý nghĩa:

1. Cấu hình LdapContextSource với StartTLS.
2. Bọc context source đó bằng PooledContextSource.
3. Đưa pooled context source thật vào ContextSourceTransactionManager.
4. Bọc pool bằng TransactionAwareContextSourceProxy.
5. Cấu hình LdapTemplate dùng proxy transaction-aware.

Transaction manager cần biết context source đích thực để quản lý transaction. LdapTemplate cần dùng proxy để các lần lấy/đóng context được nhận biết trong transaction.

## 5. Cấu hình StartTLS và Spring LDAP pool

Ví dụ sau dùng API của Spring LDAP 4.1.x với Commons Pool 2. Tên package của pool2 là org.springframework.ldap.pool2.

Đảm bảo Commons Pool 2 có trên classpath. Spring Boot LDAP starter/BOM có thể quản lý dependency theo phiên bản; nếu dùng Spring LDAP standalone, kiểm tra dependency graph và khai báo Commons Pool 2 phù hợp với phiên bản Spring LDAP đang dùng.

### 5.1. Tạo context source có StartTLS

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ldap.core.support.DefaultTlsDirContextAuthenticationStrategy;
import org.springframework.ldap.core.support.LdapContextSource;

@Configuration
public class LdapConnectionConfiguration {

    @Bean
    DefaultTlsDirContextAuthenticationStrategy startTlsStrategy() {
        DefaultTlsDirContextAuthenticationStrategy strategy =
                new DefaultTlsDirContextAuthenticationStrategy();

        // Mặc định là false. Chỉ đổi khi LDAP server yêu cầu
        // TLS shutdown graceful và đã kiểm thử vòng đời với pool.
        strategy.setShutdownTlsGracefully(false);

        return strategy;
    }

    @Bean
    LdapContextSource ldapTargetContextSource(
            DefaultTlsDirContextAuthenticationStrategy startTlsStrategy,
            DirectoryProperties properties) {

        LdapContextSource source = new LdapContextSource();
        source.setUrl(properties.url()); // ldap://ldap01.example.com:389
        source.setBase(properties.baseDn());
        source.setUserDn(properties.bindDn());
        source.setPassword(properties.bindPassword());

        // Không dùng JNDI native pooling với StartTLS.
        source.setPooled(false);

        // StartTLS handshake diễn ra trước SIMPLE bind.
        source.setAuthenticationStrategy(startTlsStrategy);

        return source;
    }
}
~~~

DirectoryProperties là kiểu cấu hình do ứng dụng định nghĩa. Lấy bind password từ secret manager hoặc biến môi trường; không hard-code secret trong source code. Spring gọi lifecycle initialization của LdapContextSource khi quản lý bean.

DefaultTlsDirContextAuthenticationStrategy dùng SIMPLE authentication sau khi thương lượng TLS. Nếu server yêu cầu SASL EXTERNAL với client certificate, xem ExternalTlsDirContextAuthenticationStrategy và cấu hình keystore/client certificate tương ứng.

Theo mặc định, strategy dùng SSL socket factory của JSSE và hostname verification mặc định. Cấu hình CA tin cậy trong truststore của đúng JVM/container đang chạy ứng dụng; không dùng HostnameVerifier luôn trả true để bỏ qua SAN mismatch.

### 5.2. Tạo pool với giới hạn và validation

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ldap.core.support.LdapContextSource;
import org.springframework.ldap.pool2.factory.PoolConfig;
import org.springframework.ldap.pool2.factory.PooledContextSource;
import org.springframework.ldap.pool2.validation.DefaultDirContextValidator;

@Configuration
public class LdapPoolConfiguration {

    @Bean
    PooledContextSource pooledContextSource(
            LdapContextSource ldapTargetContextSource) {

        PoolConfig poolConfig = new PoolConfig();
        poolConfig.setMaxTotal(32);
        poolConfig.setMaxTotalPerKey(16);
        poolConfig.setMaxIdlePerKey(8);
        poolConfig.setMaxWaitMillis(2_000);
        poolConfig.setTestOnBorrow(true);
        poolConfig.setTestWhileIdle(true);
        poolConfig.setTimeBetweenEvictionRunsMillis(60_000);

        PooledContextSource pool =
                new PooledContextSource(ldapTargetContextSource, poolConfig);

        // Cần validator khi bật testOnBorrow/testWhileIdle.
        pool.setDirContextValidator(new DefaultDirContextValidator());

        return pool;
    }
}
~~~

Đây là cấu hình khởi đầu để minh họa, không phải kích thước tối ưu cho mọi hệ thống. Các giá trị cần điều chỉnh theo giới hạn connection của directory server, số request đồng thời, thời lượng transaction và số instance ứng dụng.

DefaultDirContextValidator thực hiện một search nhỏ với filter objectclass=*, giới hạn một kết quả và timeout mặc định ngắn. Nếu server không cho phép đọc objectClass ở base DN mặc định, hãy cấu hình validator riêng với base/filter mà bind account được phép dùng. Không tắt validation chỉ để làm test pass mà chưa xác định lý do context bị từ chối.

### 5.3. Ý nghĩa các tham số pool

| Tham số | Ý nghĩa | Cách chọn |
| --- | --- | --- |
| maxTotal | Tổng số context tối đa trong pool. | Giới hạn tổng connection đọc và ghi. |
| maxTotalPerKey | Số context tối đa cho mỗi loại key. | Read-only và read-write có pool key riêng. |
| maxIdlePerKey | Số context nhàn rỗi tối đa mỗi key. | Tránh giữ quá nhiều connection không dùng. |
| maxWaitMillis | Thời gian chờ context khi pool hết chỗ. | Chọn timeout hữu hạn để request không treo vô thời hạn. |
| testOnBorrow | Kiểm tra context trước khi giao cho caller. | Hữu ích khi server đóng connection nhàn rỗi. |
| testWhileIdle | Kiểm tra context đang nhàn rỗi. | Cần kết hợp eviction run interval. |
| timeBetweenEvictionRunsMillis | Chu kỳ kiểm tra context nhàn rỗi. | Điều chỉnh theo idle timeout phía server. |

Trong pool2, maxTotalPerKey giới hạn số object theo từng loại context; maxTotal giới hạn tổng object. Ví dụ maxTotal=32 và maxTotalPerKey=16 cho phép tối đa 16 context read-only và 16 context read-write nếu cả hai loại đều được dùng.

Khi pool cạn, maxWaitMillis quyết định caller chờ bao lâu trước khi nhận lỗi mượn connection. Hãy đồng bộ timeout này với request timeout và transaction timeout. Không đặt maxWaitMillis quá dài nếu request HTTP có deadline ngắn.

### 5.4. Validation không thay thế TLS certificate validation

testOnBorrow xác minh context có thể thực hiện một LDAP search. Nó không thay thế:

- Certificate chain validation.
- Hostname/SAN verification.
- TLS protocol/cipher policy.
- Kiểm tra StartTLS handshake đã hoàn tất trước bind.

Certificate phải được xác minh ngay trong TLS handshake khi context được tạo. Validator chỉ kiểm tra context đã được tạo có còn sử dụng được hay không.

## 6. Giữ TLS state an toàn trong pool

StartTLS là trạng thái của connection, không phải một cờ cấu hình chỉ tồn tại trong LdapTemplate. Khi PooledContextSource tạo context mới, StartTLS strategy được chạy. Khi caller đóng wrapper context, pool nhận lại context để tái sử dụng; connection vẫn cần ở trạng thái TLS đã thương lượng.

### 6.1. Không gọi StartTLS hai lần trên context đang được pool quản lý

Nếu LdapContextSource đã dùng DefaultTlsDirContextAuthenticationStrategy, ứng dụng không cần gọi thêm:

~~~java
// Không tự làm điều này trên context do PooledContextSource cấp:
StartTlsResponse response =
        (StartTlsResponse) ldapContext.extendedOperation(new StartTlsRequest());
response.negotiate();
~~~

Gọi StartTLS lần nữa có thể gây lỗi protocol hoặc tạo trạng thái mà pool không biết cách quản lý. Hãy để strategy của Spring thực hiện handshake đúng một lần khi tạo context vật lý.

### 6.2. Không tự đóng TLS layer ở cuối request

StartTlsResponse.close() quay về LDAP association không mã hóa. Nếu ứng dụng gọi nó rồi trả context về pool, connection có thể bị tái sử dụng trong trạng thái không bảo vệ.

Đối với context được quản lý bởi Spring LDAP:

- Chỉ gọi DirContext.close() theo vòng đời do Spring cung cấp; khi dùng pool, thao tác này trả context về pool.
- Không giữ DirContext sau khi method kết thúc.
- Không lưu StartTlsResponse vào field hoặc cache.
- Không thay đổi security properties của context đã được tạo.
- Để pool loại bỏ connection khi context hỏng hoặc hết tuổi thọ.

### 6.3. shutdownTlsGracefully

AbstractTlsDirContextAuthenticationStrategy có thuộc tính shutdownTlsGracefully, mặc định là false. Một số directory server yêu cầu đóng TLS layer một cách graceful trước khi đóng context; một số server khác không hỗ trợ hoặc phản hồi không đúng khi client yêu cầu shutdown này.

Khi dùng pool, việc trả context về pool và việc hủy connection vật lý là hai thời điểm khác nhau. Hãy chọn giá trị theo server, kiểm thử cả việc trả context và lúc pool destroy/evict context. Không bật graceful shutdown chỉ dựa trên suy đoán; phải xác minh rằng connection được tái sử dụng vẫn ở trạng thái TLS và khi bị hủy server xử lý đúng.

### 6.4. Không trộn credential người dùng tùy biến vào một pool service account chung

PooledContextSource giả định các context read-only cùng loại và các context read-write cùng loại có cùng environment xác thực. Nếu mỗi request thay đổi DN/password theo người dùng qua AuthenticationSource, pool có thể trả context được tạo bằng credential của người khác.

Với ứng dụng dùng service account cố định, pool theo từng loại context thường phù hợp. Nếu cần user-specific bind, hãy thiết kế pool/key tách biệt theo principal hoặc không dùng chung pool cho các credential khác nhau. Không để một context đã bind user A được trả cho request của user B.

## 7. Kết hợp pool với compensating transaction

LDAP không cung cấp transaction ACID tổng quát cho chuỗi thao tác mà Spring LDAP quản lý. ContextSourceTransactionManager thực hiện compensation ở phía client:

1. Ghi nhận trạng thái cần thiết trước thao tác thay đổi.
2. Thực hiện thao tác LDAP.
3. Khi transaction commit, hoàn tất các bước phụ trợ.
4. Khi rollback, thực hiện thao tác bù để cố gắng khôi phục trạng thái trước đó.

Spring LDAP cũng giữ **cùng một DirContext trong suốt transaction**. Context không được trả về pool ngay sau mỗi method của LdapTemplate; nó chỉ được giải phóng khi transaction hoàn tất.

### 7.1. Cấu hình proxy và transaction manager

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.pool2.factory.PooledContextSource;
import org.springframework.ldap.transaction.compensating.manager.ContextSourceTransactionManager;
import org.springframework.ldap.transaction.compensating.manager.TransactionAwareContextSourceProxy;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@Configuration
@EnableTransactionManagement
public class LdapTransactionConfiguration {

    @Bean
    TransactionAwareContextSourceProxy transactionAwareContextSource(
            PooledContextSource pooledContextSource) {

        return new TransactionAwareContextSourceProxy(pooledContextSource);
    }

    @Bean
    LdapTemplate ldapTemplate(
            TransactionAwareContextSourceProxy transactionAwareContextSource) {

        return new LdapTemplate(transactionAwareContextSource);
    }

    @Bean
    ContextSourceTransactionManager ldapTransactionManager(
            PooledContextSource pooledContextSource) {

        // Truyền ContextSource thật, chưa bọc proxy.
        return new ContextSourceTransactionManager(pooledContextSource);
    }
}
~~~

Hai đường dùng context phải được cấu hình đúng:

- ContextSourceTransactionManager nhận PooledContextSource thật.
- LdapTemplate nhận TransactionAwareContextSourceProxy bọc quanh pool.

Proxy giúp LdapTemplate không đóng context đang được transaction sử dụng. Transaction manager dùng pool thật để quản lý context và ghi nhận các operation cần compensation.

### 7.2. Gắn transaction ở service layer

Nên đặt transaction ở service method bao trọn một nghiệp vụ, thay vì chỉ đặt trên từng repository call:

~~~java
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.BasicAttributes;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class EmployeeProvisioningService {

    private final LdapTemplate ldapTemplate;

    public EmployeeProvisioningService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    @Transactional(transactionManager = "ldapTransactionManager")
    public void createEmployeeAndAddToGroup(
            String uid,
            String commonName,
            String surname) {

        BasicAttributes employee = new BasicAttributes(true);
        BasicAttribute objectClass = new BasicAttribute("objectClass");
        objectClass.add("top");
        objectClass.add("person");
        objectClass.add("organizationalPerson");
        objectClass.add("inetOrgPerson");

        employee.put(objectClass);
        employee.put("uid", uid);
        employee.put("cn", commonName);
        employee.put("sn", surname);

        String employeeDn = LdapNameBuilder.newInstance()
                .add("ou", "people")
                .add("uid", uid)
                .build()
                .toString();
        String groupDn = "cn=employees,ou=groups";
        String employeeFullDn = LdapNameBuilder.newInstance("dc=example,dc=com")
                .add("ou", "people")
                .add("uid", uid)
                .build()
                .toString();

        // Operation 1: tạo entry nhân viên.
        ldapTemplate.bind(employeeDn, null, employee);

        // Operation 2: thêm DN nhân viên vào thuộc tính member của nhóm.
        ModificationItem addMember = new ModificationItem(
                DirContext.ADD_ATTRIBUTE,
                new BasicAttribute("member", employeeFullDn));

        ldapTemplate.modifyAttributes(
                groupDn,
                new ModificationItem[] { addMember });
    }
}
~~~

Ví dụ giả định ContextSource có base DN là dc=example,dc=com, các OU ou=people và ou=groups đã tồn tại, và schema cho phép các object class/attribute trên. DN truyền vào LdapTemplate là relative DN theo base đã cấu hình; giá trị member là full DN của entry được tham chiếu.

LdapNameBuilder tạo RDN có escape giá trị đúng quy tắc DN. Không ghép chuỗi DN từ dữ liệu người dùng bằng toán tử + vì uid có thể chứa dấu phẩy, dấu cộng hoặc ký tự cần escape. Trong production, cần xác thực uid theo quy tắc định danh của hệ thống trước khi tạo entry.

Nếu bước thêm member thất bại, exception thoát khỏi method làm transaction rollback. Spring LDAP có thể bù trừ thao tác bind trước đó bằng unbind entry vừa tạo.

Để @Transactional có hiệu lực, method phải được gọi qua Spring proxy (ví dụ từ bean/service khác); gọi nội bộ bằng this.method() không kích hoạt transaction interceptor theo proxy mode mặc định. Các thao tác phải đi qua LdapTemplate được cấu hình bằng transaction-aware context source.

Ví dụ trên phát sinh DataAccessException (runtime exception) khi LDAP operation thất bại, nên rollback theo mặc định của Spring. Nếu service ném checked exception và muốn rollback, khai báo rollbackFor phù hợp trong @Transactional.

## 8. Spring LDAP bù trừ các thao tác như thế nào?

Spring LDAP ghi nhận thông tin trước khi thực hiện các thao tác sửa đổi được hỗ trợ: bind, unbind, rebind, modifyAttributes và rename.

| LDAP operation | Thao tác chuẩn bị | Compensation khi rollback |
| --- | --- | --- |
| bind | Ghi lại DN, sau đó tạo entry. | unbind entry vừa tạo. |
| rename | Ghi lại DN cũ và DN mới, sau đó rename. | Rename về DN ban đầu. |
| unbind | Ghi DN gốc và tính temporary DN; rename entry tới vị trí tạm. | Rename entry từ vị trí tạm về DN ban đầu. |
| rebind | Ghi DN gốc và attributes mới; di chuyển entry cũ tới DN tạm, sau đó bind entry mới. | Khôi phục entry cũ từ vị trí tạm. |
| modifyAttributes | Ghi lại DN và tạo các modification ngược. | Thực hiện modification ngược để khôi phục giá trị cũ. |

Một số operation cần temporary DN vì LDAP không phải lúc nào cũng cho đọc lại toàn bộ attribute của entry. Ví dụ khi unbind, Spring LDAP có thể rename entry sang vị trí tạm trước; đến commit mới xóa entry tạm. Nếu rollback, entry được rename về DN ban đầu.

### 8.1. Temporary DN và subtree

DefaultTempEntryRenamingStrategy thêm suffix vào RDN cuối để tạo DN tạm. Cách này phù hợp với nhiều thao tác đơn giản.

Tuy nhiên, không thể rename một entry cha khi nó vẫn còn child entry. Nếu cần xóa đệ quy một subtree trong transaction, chiến lược mặc định có thể thất bại. Spring LDAP cung cấp DifferentSubtreeTempEntryRenamingStrategy để di chuyển entry tạm sang một subtree khác. Subtree tạm đó phải tồn tại trước khi transaction chạy.

Ví dụ cấu trúc:

~~~text
dc=example,dc=com
├── ou=people
├── ou=groups
└── ou=tempEntries
~~~

Nếu nghiệp vụ có thao tác subtree, cấu hình renaming strategy phù hợp với topology và kiểm thử cả rollback lẫn commit. Không tạo ou=tempEntries tùy tiện trong cùng transaction đang cần dùng nó để bù trừ.

### 8.2. Compensation không phải rollback nguyên tử

Spring LDAP transaction manager là cơ chế **client-side**, không phải transaction server-side:

- LDAP server không biết transaction ID hay ranh giới commit/rollback của Spring.
- Không có transaction isolation; client khác có thể đọc hoặc sửa entry giữa các bước.
- Nếu network connection bị mất, client có thể không thực hiện được compensation.
- Compensation có thể thất bại do ACL, schema constraint, uniqueness, entry đã bị client khác thay đổi hoặc server không còn sẵn sàng.
- Một lỗi khi rollback có thể khiến trạng thái directory cần được kiểm tra và khôi phục thủ công.

Vì vậy, không nên mô tả @Transactional LDAP như ACID database transaction. Đây là nỗ lực khôi phục trạng thái cũ bằng các operation ngược, với giới hạn của giao thức và trạng thái directory.

## 9. Pool hoạt động ra sao trong một transaction?

Giả sử pool read-write có maxTotalPerKey=16. Một transaction bắt đầu và gọi ldapTemplate.bind(...); context read-write được mượn từ pool. Transaction tiếp tục gọi modifyAttributes(...), rồi có thể rename(...). Spring transaction-aware proxy giữ cùng context trong toàn bộ transaction.

~~~mermaid
sequenceDiagram
    participant Service
    participant Tx as ContextSourceTransactionManager
    participant Proxy as TransactionAwareContextSourceProxy
    participant Pool as PooledContextSource
    participant LDAP as LDAP server
    Service->>Tx: Begin transaction
    Service->>Proxy: bind(...)
    Proxy->>Pool: Borrow read-write context
    Pool->>LDAP: Reuse StartTLS context (or create + handshake)
    LDAP-->>Pool: Bind/context ready
    Pool-->>Proxy: DirContext
    Proxy->>LDAP: bind employee
    Service->>Proxy: modifyAttributes(...)
    Proxy->>LDAP: add member DN
    Service->>Tx: Commit
    Tx->>Proxy: Complete transaction
    Proxy->>Pool: Return context
~~~

Trong transaction, context được mượn vẫn chiếm một slot của pool. Nó không được trả về sau mỗi operation. Khi transaction kết thúc, proxy mới cho phép đóng context; với pooled context, việc đóng này trả context về pool để request khác có thể dùng.

### 9.1. Ảnh hưởng đến sizing

Pool phải đủ lớn cho số transaction đồng thời, không chỉ số query đơn lẻ. Ví dụ:

- 12 transaction ghi đồng thời có thể giữ 12 read-write context cho tới khi hoàn tất.
- Một transaction kéo dài 10 giây sẽ giữ slot lâu hơn transaction chỉ chạy 100 ms.
- Nếu pool chỉ có 8 read-write context, các transaction tiếp theo phải chờ hoặc nhận lỗi khi hết maxWaitMillis.

Giữ transaction ngắn. Không thực hiện HTTP call, gửi email, chờ người dùng, xử lý file lớn hoặc tính toán kéo dài khi đang giữ context LDAP trong transaction.

### 9.2. Tránh deadlock do pool cạn

Một luồng có thể giữ context trong transaction rồi gọi một service khác khiến service đó mượn thêm context từ cùng pool. Nếu mọi slot đều bị giữ bởi các transaction đang chờ slot thứ hai, ứng dụng có thể bị kẹt tới khi maxWaitMillis hết hạn.

Giảm rủi ro bằng cách:

- Không mở transaction lồng nhau nếu không cần.
- Tránh gọi service có thể mượn context thứ hai bên trong transaction đang giữ context.
- Giữ thứ tự truy cập resource nhất quán.
- Đặt timeout hữu hạn cho pool và LDAP operation.
- Theo dõi số context active và số thread đang chờ.

## 10. Kết hợp LDAP với database hoặc message broker

Spring LDAP 4.0 đã loại bỏ JDBC transaction integration cũ. ContextSourceTransactionManager quản lý compensation cho LDAP; nó không tạo XA transaction với database hoặc message broker.

Ví dụ một nghiệp vụ cần:

1. Tạo LDAP entry.
2. Ghi user ID vào bảng SQL.
3. Gửi event EmployeeCreated.

Không nên giả định một annotation @Transactional sẽ làm cả ba resource commit/rollback nguyên tử. Một hướng thiết kế thường dùng là Saga/outbox:

- Ghi trạng thái nghiệp vụ và outbox event trong SQL transaction.
- Thực hiện LDAP provisioning theo một bước độc lập, có idempotency key.
- Đánh dấu outbox/job thành công sau khi LDAP operation xác nhận.
- Nếu LDAP thất bại, retry có giới hạn hoặc chạy compensation nghiệp vụ.
- Có job reconciliation để phát hiện SQL/LDAP không đồng bộ.

Nếu LDAP operation nằm trong một ContextSourceTransactionManager riêng, dùng rõ transaction manager đó trong @Transactional. Không đặt tên transaction manager mặc định chung rồi mong Spring tự suy ra resource.

## 11. Xử lý lỗi và trạng thái không chắc chắn

| Lỗi | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| TLS handshake failure | CA không tin cậy, certificate hết hạn, hostname không khớp hoặc server không hỗ trợ cấu hình TLS. | Kiểm tra truststore, SAN, protocol/cipher và server log; không fallback plaintext. |
| Bind failure sau StartTLS | DN/password sai hoặc server policy từ chối. | Kiểm tra bind identity và quyền; xác nhận server log cho thấy TLS handshake thành công trước bind. |
| CommunicationException | Connection bị ngắt, server restart hoặc network lỗi. | Loại context hỏng khỏi pool; kiểm tra non-transient exception handling và retry policy. |
| Pool exhausted / DataAccessResourceFailureException (có thể bọc NoSuchElementException) | Tất cả slot đang được mượn hoặc maxWaitMillis hết hạn. | Kiểm tra transaction duration, concurrency, pool sizing và context leak. |
| Validation failure | Context idle bị server đóng hoặc validator search không có quyền. | Xác minh ACL/base/filter của validator và idle timeout; không bỏ validation một cách mù quáng. |
| Compensation failure | Network mất, ACL/constraint thay đổi hoặc dữ liệu đã bị client khác sửa. | Ghi nhận rollback failure, đưa operation vào hàng chờ reconciliation và kiểm tra directory. |
| NameAlreadyBoundException khi compensation | Một client khác đã tạo entry tại DN cần khôi phục. | Xác minh trạng thái hiện tại trước khi sửa; không ghi đè tự động. |
| NoPermissionException khi rollback | Bind identity không đủ quyền thực hiện thao tác ngược. | Cấp quyền cần thiết theo least privilege hoặc thiết kế compensation bằng service identity chuyên biệt. |

### 11.1. Không retry mù quáng khi kết quả transaction không rõ

Nếu kết nối bị ngắt đúng lúc client gửi operation hoặc đang rollback, client có thể không biết server đã áp dụng operation hay chưa. Không gửi lại toàn bộ transaction mà không xác minh trạng thái:

1. Ghi nhận operation ID/correlation ID và trạng thái UNKNOWN.
2. Đọc lại DN/attribute liên quan bằng một connection mới đã qua StartTLS.
3. So sánh trạng thái thực tế với trạng thái mong đợi.
4. Chỉ thực hiện bước còn thiếu nếu operation idempotent hoặc đã có điều kiện kiểm tra trước.
5. Nếu không thể xác định, đưa vào reconciliation/manual review.

Một operation như bind không idempotent nếu DN đã tồn tại; một operation ADD_ATTRIBUTE có thể lỗi nếu giá trị đã được thêm. Thiết kế service cần kiểm tra trạng thái hoặc dùng giá trị/identifier giúp nhận biết thao tác đã chạy.

## 12. Quan sát pool và transaction

Nên theo dõi ít nhất:

| Chỉ số | Ý nghĩa |
| --- | --- |
| ldap.pool.active.read | Số context read-only đang được mượn. |
| ldap.pool.active.write | Số context read-write đang được mượn. |
| ldap.pool.idle | Số context nhàn rỗi trong pool. |
| ldap.pool.waiters | Số thread đang chờ mượn context. |
| ldap.pool.borrow.duration | Thời gian mượn context, bao gồm chờ và validation. |
| ldap.pool.validation.failure | Số context không vượt qua validation. |
| ldap.starttls.handshake.failure | Số lần StartTLS handshake thất bại khi tạo context. |
| ldap.transaction.duration | Thời lượng transaction LDAP. |
| ldap.transaction.rollback | Số lần transaction cần compensation. |
| ldap.transaction.compensation.failure | Số lần thao tác bù thất bại. |

PooledContextSource cung cấp các số liệu như active/idle/waiters qua API; có thể đưa chúng vào Micrometer gauge. Không dùng DN, username, password hoặc filter làm metric label vì cardinality và dữ liệu nhạy cảm.

Log cần có correlation ID, operation type, directory alias, result category và transaction outcome. Không ghi bind password, raw TLS session, toàn bộ LDAP attribute hoặc payload nhạy cảm.

## 13. Kiểm thử tích hợp

Mock LdapTemplate có thể kiểm tra service gọi đúng method, nhưng không chứng minh StartTLS, pool reuse hoặc compensation hoạt động. Cần LDAP server test tương thích với StartTLS và cấu hình pool.

### 13.1. Ma trận kiểm thử

| Kịch bản | Cách kiểm thử | Kết quả mong đợi |
| --- | --- | --- |
| StartTLS handshake thành công | Dùng test server có certificate được trust. | Context được tạo, bind chỉ xảy ra sau handshake. |
| CA không tin cậy | Dùng truststore không chứa CA của server. | Context creation thất bại; không bind plaintext. |
| Hostname mismatch | URL dùng hostname không khớp SAN. | TLS negotiation thất bại. |
| Native pooling bị tắt | Kiểm tra setPooled(false)/native-pooling=false. | Context StartTLS không đi qua JNDI native pool. |
| Spring pool tái sử dụng context | Mượn context, thực hiện search, đóng, mượn lại; quan sát connection ID phía server. | Context/connection đã TLS được tái sử dụng theo pool. |
| Context idle bị server đóng | Để context idle vượt idle timeout, bật validation. | Context lỗi bị loại và pool tạo context mới. |
| Pool hết slot | Giữ đủ context đồng thời rồi mượn thêm. | Caller chờ tới maxWaitMillis rồi nhận lỗi có kiểm soát. |
| Transaction giữ một context | Gọi nhiều LdapTemplate operation trong một transaction và quan sát pool. | Một context được giữ tới khi transaction hoàn tất. |
| Rollback sau bind | Bind entry rồi cố tình ném runtime exception. | Compensation unbind entry vừa tạo. |
| Rollback sau modify | Thay attribute rồi gây lỗi. | Compensation khôi phục giá trị cũ nếu điều kiện directory cho phép. |
| Concurrent update | Hai client cùng sửa entry trong lúc transaction đang chạy. | Test thể hiện không có transaction isolation; không giả định kết quả serializable. |
| Mất mạng khi rollback | Ngắt kết nối sau operation và trước compensation. | Rollback failure được ghi nhận; reconciliation cần xử lý. |
| Temporary DN cho subtree | Xóa đệ quy fixture có child entries. | Dùng renaming strategy phù hợp và temporary subtree đã tồn tại. |
| TLS shutdown behavior | Chạy với shutdownTlsGracefully theo từng server. | Context trả về pool và context bị destroy đều giữ đúng lifecycle bảo mật. |

### 13.2. Kiểm tra không có bind trước TLS

Đây là kiểm thử bảo mật quan trọng:

1. Bật LDAP server test có log StartTLS request và Bind request.
2. Tạo context mới qua LdapContextSource có DefaultTlsDirContextAuthenticationStrategy.
3. Xác minh log cho thấy StartTLS handshake thành công trước Bind.
4. Dùng certificate không hợp lệ và lặp lại.
5. Xác minh handshake thất bại và server không nhận SIMPLE bind trên kết nối plaintext.
6. Không bật packet/debug trace chứa password trong môi trường chia sẻ.

### 13.3. Kiểm tra pool reuse không làm mất TLS

1. Mượn context từ PooledContextSource.
2. Thực hiện LDAP search thành công qua TLS.
3. Đóng context để trả về pool.
4. Mượn context tiếp theo cùng loại.
5. Thực hiện operation và xác minh server vẫn ghi nhận kết nối TLS.
6. Lặp lại sau khi connection idle và sau khi server đóng connection.

Nếu lần mượn lại sử dụng LDAP plaintext, dừng kiểm thử và kiểm tra lifecycle StartTLS, native pooling, việc gọi StartTlsResponse.close() và cách trả context về pool.

### 13.4. Kiểm tra compensation

Chuẩn bị một OU test riêng và hai operation có thể quan sát:

1. Service bind một employee entry.
2. Service thêm DN employee vào member của group.
3. Test làm operation thứ hai thất bại hoặc ném exception sau operation thứ nhất.
4. Transaction manager thực hiện rollback.
5. Search lại directory để xác minh entry employee đã được gỡ và group không còn member vừa thêm.

Chạy thêm một test ngắt network trong lúc rollback. Kỳ vọng hệ thống báo compensation failure/UNKNOWN và tạo tín hiệu reconciliation, không giả định trạng thái đã được khôi phục.

## 14. Checklist trước khi phát hành

- [ ] LdapContextSource dùng DefaultTlsDirContextAuthenticationStrategy hoặc strategy TLS phù hợp.
- [ ] Certificate chain và hostname/SAN được xác minh.
- [ ] Bind chỉ diễn ra sau khi StartTLS handshake thành công.
- [ ] JNDI native pooling được tắt.
- [ ] PooledContextSource của Spring LDAP được dùng cho context StartTLS.
- [ ] Pool có maxTotal, maxTotalPerKey và maxWaitMillis hữu hạn, phù hợp tải.
- [ ] Validator có quyền search trên base/filter được cấu hình.
- [ ] testOnBorrow/testWhileIdle được chọn theo idle timeout của directory.
- [ ] Pool không trộn context của nhiều user credential khác nhau.
- [ ] ContextSourceTransactionManager dùng pooled context source thật.
- [ ] LdapTemplate dùng TransactionAwareContextSourceProxy.
- [ ] Transaction được đặt ở service layer và method được gọi qua Spring proxy.
- [ ] Subtree delete/rebind đã chọn temporary DN strategy phù hợp.
- [ ] Rollback failure và network uncertainty có quy trình reconciliation.
- [ ] Không giả định LDAP compensation là ACID/XA hoặc có isolation.
- [ ] Integration test xác minh TLS, pool reuse, pool exhaustion và compensation.

## 15. Bài tập tình huống

Một ứng dụng nhân sự kết nối tới OpenLDAP bằng StartTLS. Mỗi request tạo context mới và thực hiện hai thao tác: tạo entry nhân viên, sau đó thêm DN nhân viên vào group cn=employees. Nhóm muốn tăng hiệu năng bằng connection pooling và muốn tự động hoàn tác nếu bước cập nhật group thất bại.

Một developer bật com.sun.jndi.ldap.connect.pool=true, tự gọi StartTLS trên context, sau đó gọi StartTlsResponse.close() ở cuối request. Developer cũng thêm @Transactional nhưng LdapTemplate vẫn dùng LdapContextSource trực tiếp, không qua transaction-aware proxy.

**Yêu cầu:**

1. Vì sao JNDI native pooling không phù hợp với context có StartTLS?
2. StartTLS khác LDAPS ở thời điểm TLS handshake như thế nào?
3. Vì sao không được gọi StartTlsResponse.close() trước khi trả context về pool?
4. Spring LDAP cần dùng class pool nào để tái sử dụng context StartTLS?
5. DefaultTlsDirContextAuthenticationStrategy thực hiện bước nào trước SIMPLE bind?
6. Vì sao cần giữ native-pooling=false khi dùng TLS strategy?
7. testOnBorrow và testWhileIdle giúp xử lý vấn đề nào?
8. maxTotalPerKey khác maxTotal như thế nào?
9. Vì sao transaction dài làm pool nhanh cạn?
10. ContextSourceTransactionManager và TransactionAwareContextSourceProxy có vai trò gì?
11. Nếu operation tạo entry thành công nhưng operation thêm group member thất bại, Spring LDAP có thể bù trừ thế nào?
12. Vì sao compensation không thể bảo đảm khôi phục nếu network mất trong lúc rollback?
13. Vì sao transaction manager phải nhận pooled context source thật, còn LdapTemplate dùng proxy?
14. Nếu cần xóa một subtree có nhiều child entries, vì sao DefaultTempEntryRenamingStrategy có thể không phù hợp?
15. Hãy đề xuất test chứng minh connection được trả về pool vẫn ở trạng thái TLS.

**Gợi ý đáp án:**

- JNDI native pool không theo dõi trạng thái connection thay đổi sau khi context được tạo, trong đó có StartTLS.
- StartTLS mở LDAP connection thường rồi nâng cấp bằng Extended Operation; LDAPS dùng TLS ngay từ đầu socket.
- StartTlsResponse.close() đóng TLS layer và quay về LDAP plaintext.
- Dùng PooledContextSource/Spring LDAP pooling, không dùng native JNDI pooling.
- TLS strategy gửi StartTLS, thương lượng TLS và sau đó mới áp dụng SIMPLE authentication.
- Pool giữ connection đã nâng cấp TLS; native pooling không quản lý trạng thái đó.
- Validation giúp loại context bị server đóng hoặc không còn hoạt động.
- maxTotal giới hạn toàn pool; maxTotalPerKey giới hạn từng loại context như read-only/read-write.
- Transaction giữ cùng context cho tới khi hoàn tất, do đó slot không được trả sớm.
- Transaction manager điều phối compensation; proxy giúp LdapTemplate giữ context và ghi nhận operation trong transaction.
- Bind có thể được bù bằng unbind; modifyAttributes có thể được bù bằng các modification ngược.
- Network mất làm client không thể gửi thao tác bù tới directory; trạng thái cần reconciliation.
- Manager cần context source thật để điều phối; template cần proxy để các thao tác được intercept.
- Không thể rename entry cha khi còn child; chiến lược chuyển sang subtree tạm có thể phù hợp hơn.
- Mượn, thao tác, trả context, mượn lại và xác minh server vẫn ghi nhận kết nối TLS; lặp lại với certificate không hợp lệ và xác minh không bind plaintext.

## 16. Ghi nhớ

**StartTLS thay đổi trạng thái của connection, vì vậy không dùng JNDI native pooling cho context StartTLS.** Spring LDAP cung cấp DefaultTlsDirContextAuthenticationStrategy để nâng cấp connection và bind sau TLS handshake; PooledContextSource của Spring LDAP giúp tái sử dụng context đã được bảo vệ, đồng thời hỗ trợ validation và eviction.

Để dùng compensation, ContextSourceTransactionManager phải quản lý pooled context source thật, còn LdapTemplate dùng TransactionAwareContextSourceProxy. Transaction giữ cùng DirContext đến khi hoàn tất; vì vậy thời lượng transaction ảnh hưởng trực tiếp tới số slot pool đang bị chiếm. Spring LDAP chỉ cung cấp compensating transaction phía client, không có isolation và không thể bảo đảm rollback khi network bị đứt. Hãy kiểm thử TLS lifecycle, pool reuse, pool exhaustion, rollback và reconciliation với đúng directory server/version trước khi phát hành.

### Tài liệu tham khảo

- [Spring LDAP 4.1 — Pooling Support](https://docs.spring.io/spring-ldap/reference/4.1/pooling.html)
- [Spring LDAP 4.1 — Configuration and TLS Authentication](https://docs.spring.io/spring-ldap/reference/4.1/configuration.html)
- [Spring LDAP 4.1 — Transaction Support](https://docs.spring.io/spring-ldap/reference/4.1/transaction-support.html)
- [Spring LDAP API — PooledContextSource](https://docs.spring.io/spring-ldap/reference/4.1/api/java/org/springframework/ldap/pool2/factory/PooledContextSource.html)
- [Spring LDAP API — PoolConfig](https://docs.spring.io/spring-ldap/reference/4.1/api/java/org/springframework/ldap/pool2/factory/PoolConfig.html)
- [Spring LDAP API — DefaultTlsDirContextAuthenticationStrategy](https://docs.spring.io/spring-ldap/reference/4.1/api/java/org/springframework/ldap/core/support/DefaultTlsDirContextAuthenticationStrategy.html)
- [Spring LDAP API — ContextSourceTransactionManager](https://docs.spring.io/spring-ldap/reference/4.1/api/java/org/springframework/ldap/transaction/compensating/manager/ContextSourceTransactionManager.html)
- [Spring LDAP API — TransactionAwareContextSourceProxy](https://docs.spring.io/spring-ldap/reference/4.1/api/java/org/springframework/ldap/transaction/compensating/manager/TransactionAwareContextSourceProxy.html)
- [Spring LDAP API — LdapNameBuilder](https://docs.spring.io/spring-ldap/reference/4.1/api/java/org/springframework/ldap/support/LdapNameBuilder.html)
- [Oracle JNDI Tutorial — Pooling](https://docs.oracle.com/javase/jndi/tutorial/ldap/pool.html)
- [Oracle JNDI Tutorial — The Start TLS Extension](https://docs.oracle.com/javase/jndi/tutorial/ldap/ext/starttls.html)
- [Java SE — StartTlsResponse](https://docs.oracle.com/en/java/javase/21/docs/api/java.naming/javax/naming/ldap/StartTlsResponse.html)
