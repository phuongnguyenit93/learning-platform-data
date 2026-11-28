# Kiểm tra kết nối khi lấy, trả hoặc trong lúc nhàn rỗi

Trong **SPRING_DATA_LDAP**, ứng dụng Java sử dụng Spring Data LDAP repository hoặc `LdapTemplate` để truy cập LDAP directory, ánh xạ các entry theo DN (*Distinguished Name*), `objectClass` và thuộc tính sang đối tượng Java. Mỗi lần tìm kiếm, đọc hoặc sửa entry đều cần một `DirContext` do `ContextSource` cấp. Nếu phải tạo và xác thực kết nối mới cho mọi thao tác, chi phí TCP/TLS, LDAP Bind và cấp phát tài nguyên có thể trở thành nút thắt. Vì vậy ứng dụng có thể dùng **pool** để tái sử dụng context.

Tuy nhiên, context nằm trong pool không phải lúc nào cũng còn tốt. Trong khi nó đang rảnh, firewall có thể đóng socket, LDAP server có thể restart, kết nối TLS có thể bị ngắt hoặc tài khoản bind có thể thay đổi trạng thái. Nếu lấy context đã chết ra dùng, thao tác đầu tiên sẽ gặp lỗi; nếu kiểm tra quá nhiều, ứng dụng lại phải trả giá bằng **thêm LDAP request, độ trễ và tải server**.

Spring LDAP có ba chế độ kiểm tra hữu ích khi dùng pool dựa trên Apache Commons Pool 2: **`testOnBorrow`**, **`testOnReturn`** và **`testWhileIdle`**. Bài học này làm rõ thời điểm từng chế độ chạy, cách hoạt động của `DefaultDirContextValidator`, cấu hình `PooledContextSource`, các giới hạn của validation, cách theo dõi chi phí và kiểm thử tình huống LDAP server bị ngắt.

## 1. Vì sao context đã tạo vẫn có thể hỏng?

Giả sử dịch vụ cần tra cứu:

```text
uid=lan,ou=people,dc=example,dc=org
```

Ứng dụng gọi `LdapTemplate.lookup(...)`, nhận `DirContext` từ pool, thực hiện thao tác và trả context về pool. Trong thời gian không có request:

```text
12:00:00  LDAP Bind thành công, context A trở thành idle.
12:05:00  Firewall đóng TCP connection đã nhàn rỗi.
12:06:00  User request đến; pool còn context A.
12:06:01  Nếu không kiểm tra, lookup bằng A có thể báo CommunicationException.
```

Những nguyên nhân thường gặp:

| Tình huống | Điều gì xảy ra | Validation có thể giúp gì? |
|---|---|---|
| LDAP server restart | Session/socket cũ mất hiệu lực | Loại bỏ context không còn phản hồi |
| Firewall/NAT idle timeout | Kết nối nhàn rỗi bị cắt | Phát hiện khi kiểm tra hoặc khi thao tác |
| Server failover | Địa chỉ mới có thể nhận kết nối, context cũ vẫn gắn node cũ | Hủy context cũ và tạo context mới theo endpoint cấu hình |
| Kết nối mạng chập chờn | Search hoặc Bind bị timeout | Phân loại lỗi, invalidate context hỏng |
| TLS session bị đóng | Lần dùng lại có thể lỗi giao tiếp | Phát hiện context không sử dụng được; tạo TLS connection mới |
| LDAP server quá tải | Probe cũng chậm hoặc timeout | Thấy lỗi nhưng không sửa được nguyên nhân server quá tải |
| ACL/bind identity thay đổi | Context có thể không còn quyền như trước | Probe có thể thành công nhưng thao tác nghiệp vụ vẫn bị từ chối |

Một `DirContext` là đối tượng JNDI đại diện cho một ngữ cảnh LDAP. Số context đang rảnh **không phải** bằng chứng mọi socket phía dưới đều còn sống. Ngược lại, một lần validation thành công chỉ cho thấy context phản hồi được **tại thời điểm kiểm tra**; kết nối vẫn có thể hỏng ngay sau đó.

## 2. Vòng đời một pooled DirContext

Với `PooledContextSource`, một luồng sử dụng cơ bản:

```text
                     POOL
                 +------------+
                 | IDLE       | <--- context được trả lại
                 +------------+
                       |
             request mượn context
                       |
                testOnBorrow?
                  /         \
                 có         không
                 |            |
          validate bằng       |
          LDAP search         |
           /       \          |
         PASS      FAIL       |
          |         |         |
          |   loại context    |
          |   thử context mới |
          +---------+---------+
                    |
                    v
           ACTIVE / đang mượn
                    |
             LdapTemplate dùng
                    |
                 close()
                    |
               testOnReturn?
                 /       \
               có       không
               |          |
         validate         |
           /   \          |
         PASS  FAIL       |
           |     |        |
           |   hủy       |
           +-----+--------+
                 |
                 v
                IDLE
                 |
           idle evictor chạy?
                 |
           testWhileIdle?
                 |
         validation/eviction
```

Trong thực tế, Commons Pool 2 còn có các trạng thái tạo mới, invalidation, giới hạn theo key và chờ mượn. Sơ đồ trên chỉ nhằm chỉ ra **ba điểm kiểm tra khác nhau**, không phải sơ đồ mọi trạng thái nội bộ của thư viện.

**Cực kỳ quan trọng:** với context được quản lý bởi `PooledContextSource`, gọi `close()` trên wrapper thường có nghĩa **trả đối tượng về pool**, không nhất thiết đóng TCP socket ngay. Nếu dùng JNDI trực tiếp và bỏ qua `close()`, context có thể tiếp tục bị coi là active, dẫn đến pool cạn dù không còn request.

## 3. So sánh testOnBorrow, testOnReturn và testWhileIdle

| Chế độ | Khi nào kiểm tra? | Mục đích | Chi phí/đánh đổi |
|---|---|---|---|
| **`testOnBorrow`** | Trước khi giao context cho caller | Giảm khả năng request nhận context đã chết | Có thể thêm round-trip vào thời gian mượn context |
| **`testOnReturn`** | Khi caller `close()`/trả context | Không giữ lại context hỏng trong nhóm idle | Tăng thời gian trả context, gây thêm probe sau thao tác |
| **`testWhileIdle`** | Khi background idle-evictor chọn một context rảnh | Dọn dần context hỏng trong thời gian chưa có request | Probe định kỳ, tăng lưu lượng nền; không bảo đảm quét hết tức thì |
| `testOnCreate` | Sau khi pool tạo đối tượng mới | Kiểm tra context vừa tạo có dùng được không | Thêm validation vào chi phí tạo mới; không thay ba chế độ trên |

Trong Spring LDAP Commons Pool 2, các cờ trên thuộc **`org.springframework.ldap.pool2.factory.PoolConfig`**. Giá trị mặc định của phần lớn cờ validation là **`false`**; đừng nghĩ việc tạo `PooledContextSource` tự động bật cả ba.

### 3.1. testOnBorrow

```text
Borrow context
   |
   +-- Có idle -> validate -> PASS -> giao cho request
   |                    |
   |                    +-> FAIL -> loại; thử đối tượng khác/tạo mới
   |
   +-- Không có idle -> có thể tạo mới, chịu giới hạn pool
```

Ưu điểm là phát hiện context hỏng gần với thời điểm dùng nhất. Nhược điểm là một LDAP query validation có thể xuất hiện ngay trên đường request; nếu directory chậm, **acquire latency** tăng và có thể kéo dài thời gian chờ của các request khác.

Đừng gọi kết quả đo quanh `getReadOnlyContext()` là “thời gian xếp hàng” thuần túy: nó có thể bao gồm **chờ pool, validation và tạo kết nối mới**. `testOnBorrow` cũng không bảo đảm thao tác `search` tiếp theo không lỗi nếu kết nối chết sau probe.

### 3.2. testOnReturn

```text
Request xử lý xong
    |
    v
context.close()
    |
    v
Validate?
   |                   |
  PASS                FAIL
   |                   |
 Trả idle           Loại context
```

Kiểm tra ở thời điểm trả giúp pool tránh lưu giữ đối tượng không còn sử dụng được. Nhưng nó **không bảo vệ request vừa hoàn tất**, và nếu pool đã tự invalidate context vì `CommunicationException` nghiêm trọng thì thêm một probe khi trả có thể dư thừa.

Khi thao tác LDAP đã thành công rồi caller gọi `close()`, validation lúc return có thể tăng chi phí đường đi của request nếu request chỉ kết thúc sau khi trả context. Vì vậy không nên bật `testOnReturn=true` chỉ với giả định “bật càng nhiều càng tốt”.

### 3.3. testWhileIdle

Idle validation cần **hai điều kiện**:

1. `testWhileIdle=true`.
2. **Idle object evictor thật sự chạy định kỳ** qua `timeBetweenEvictionRunsMillis` hoặc API tương ứng của phiên bản Commons Pool 2.

Nếu chỉ bật `testWhileIdle` nhưng khoảng chạy của evictor ở trạng thái tắt, **không có lần quét định kỳ** chỉ vì cờ được bật.

```text
Pool idle: [A] [B] [C] [D] [E]
                      |
       Evictor chạy mỗi 60 giây
                      |
             Chọn một số context
                      |
          Validate + kiểm tra tuổi idle
            /                   \
          hợp lệ               lỗi/expired
            |                       |
         giữ lại               hủy context
```

Evictor chỉ kiểm tra **các context đang rảnh**. Nó không buộc kiểm tra hoặc hủy một context đang được request giữ lâu. Số phần tử được xét ở mỗi vòng do `numTestsPerEvictionRun` và cấu hình liên quan quyết định.

**Đừng đồng nhất idle validation với TCP keepalive.** Một LDAP search định kỳ có thể tạo traffic trên một số connection rảnh, nhưng mục tiêu của evictor là **xác minh/dọn pool**, không phải bảo đảm network không bao giờ cắt socket. Probe quá thường xuyên có thể tăng tải directory và làm che khuất sự cố thực.

## 4. DefaultDirContextValidator kiểm tra điều gì?

Spring LDAP cung cấp `org.springframework.ldap.pool2.validation.DefaultDirContextValidator`, một implementation của `DirContextValidator`. Đây là thành phần quan trọng: **bật cờ test thôi chưa đủ**, phải cung cấp validator cho `PooledContextSource`.

Validator mặc định thực hiện một LDAP search nhẹ:

```text
Search base             = "" (tên rỗng tương đối với context)
Search filter           = objectclass=*
Search scope            = OBJECT_SCOPE
Count limit             = 1
Returning attributes    = objectclass
Search time limit       = 500 ms
```

Nếu query nhận được kết quả hợp lệ, validation trả `true`; nếu không có kết quả hoặc có ngoại lệ, validator trả `false`. Các giá trị có thể được chỉnh qua `setBase(String)`, `setFilter(String)` và `setSearchControls(SearchControls)`. Xem Javadoc chính thức trong phần tham khảo.

### 4.1. Ví dụ tùy chỉnh validation query

Nếu `ContextSource.base=dc=example,dc=org` thì search base `""` thường tương ứng **ngay tại entry base** trong context đó. Với directory có ACL không cho tài khoản đọc thuộc tính `objectClass` của base, validation mặc định có thể **thất bại giả** dù query nghiệp vụ tới `ou=people` vẫn được phép.

Ví dụ sửa điểm kiểm tra:

```java
import javax.naming.directory.SearchControls;
import org.springframework.ldap.pool2.validation.DefaultDirContextValidator;

DefaultDirContextValidator validator = new DefaultDirContextValidator();
validator.setBase("ou=health");  // Entry đã tồn tại, đọc được, dưới ContextSource.base.
validator.setFilter("(objectClass=*)");

SearchControls controls = new SearchControls();
controls.setSearchScope(SearchControls.OBJECT_SCOPE);
controls.setCountLimit(1);
controls.setReturningAttributes(new String[] {"objectClass"});
controls.setTimeLimit(500);
validator.setSearchControls(controls);
```

**Điều kiện tiên quyết:** `ou=health,dc=example,dc=org` phải thực sự tồn tại và được **mọi identity của context pool cần validate** phép đọc tương ứng. Không tạo một subtree riêng chỉ để phục vụ probe trong production nếu chính sách directory không cho phép; có thể chọn một entry metadata sẵn có đã được cấp quyền.

Nếu LDAP ACL chặn search ở đường dẫn kiểm tra, tình huống dễ xảy ra:

```text
Lookup uid=lan ở ou=people  -> có thể thành công
Validation tại ou=health     -> không có quyền -> FAIL
Pool hủy context hợp lệ     -> tạo lại -> FAIL tiếp
```

Kết quả là **connection churn** do cấu hình validator sai, không phải LDAP server thật sự mất kết nối. Cần kiểm thử query validation bằng đúng bind identity của context read-only/read-write.

### 4.2. Những gì validation không chứng minh

- Một search thành công **không xác nhận** caller được sửa entry; validator mặc định **không thử ghi** vào directory.
- Một search thành công **không bảo đảm** kết nối tiếp tục sống sau thời điểm probe.
- Một search thành công **không chứng minh** đúng tenant, đúng role hoặc mọi ACL của nghiệp vụ.
- Nếu server có referral/alias/special schema, filter/base kiểm tra phải tương thích; không coi `PartialResultException` mặc nhiên là lỗi “server down”.
- Validation không thay cho kiểm tra **TLS certificate/hostname**, bind authentication, authorization, schema hoặc query timeout.
- Validation không sửa được connection đã bị firewall đóng; nó giúp pool **nhận ra để thay** context, tùy thời điểm phát hiện.

`DirContextValidator.validateDirContext(DirContextType, DirContext)` nhận loại context (read-only/read-write) và đối tượng thực tế. Một validator tùy biến có thể dùng loại này để chọn phép kiểm tra phù hợp, nhưng phải tránh query gây side effect hoặc yêu cầu quyền rộng.

## 5. Native JNDI pooling khác Spring LDAP Pool2

Không phải tất cả ứng dụng gọi `ContextSource` đều có Spring pool:

| Kiểu | Cơ chế | Các tùy chọn validation trên bài có áp dụng? |
|---|---|---|
| Không pool | Tạo context theo vòng đời request/provider | Không có object pool để bật ba cờ |
| **Native JNDI LDAP pooling** | `LdapContextSource.setPooled(true)` và cấu hình JDK LDAP provider | **Không** có trực tiếp `PoolConfig.testOnBorrow`/`testOnReturn`/`testWhileIdle` của Spring |
| **Spring LDAP Pool2** | `org.springframework.ldap.pool2.factory.PooledContextSource` + Commons Pool 2 | **Có**, cấu hình `PoolConfig` và `DirContextValidator` |
| Spring LDAP pool đời cũ | `org.springframework.ldap.pool.factory.PoolingContextSource` | Có tên setter/kiểu pool **khác**; không copy API Pool2 nguyên xi |

Pool2 cho phép điều chỉnh giới hạn active/idle, validation và evictor. Trong bài, chỉ dùng **`PooledContextSource` thuộc `pool2`**; tránh lẫn với `PoolingContextSource` ở package `pool.factory`.

**Không bật cả native JNDI pooling lẫn Spring Pool2 một cách vô thức.** Nếu đặt hai tầng pool, một context của Spring có thể dùng connection do provider quản lý bên dưới, làm số liệu active/idle và vòng đời khó giải thích. Với ví dụ dưới đây, `LdapContextSource.setPooled(false)`.

## 6. Cấu hình Spring Boot / Spring LDAP Pool2 có validation

Ví dụ ứng dụng Java 17+ dùng Spring LDAP, Apache Commons Pool 2 và một LDAP service account có quyền đọc `dc=example,dc=org`.

**`LdapPoolConfiguration.java`**

```java
package com.example.ldap;

import java.util.Map;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ldap.core.ContextSource;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.core.support.LdapContextSource;
import org.springframework.ldap.pool2.factory.PoolConfig;
import org.springframework.ldap.pool2.factory.PooledContextSource;
import org.springframework.ldap.pool2.validation.DefaultDirContextValidator;

@Configuration
public class LdapPoolConfiguration {

    @Bean("rawLdapContextSource")
    LdapContextSource rawLdapContextSource(
            @Value("${app.ldap.url}") String url,
            @Value("${app.ldap.base}") String base,
            @Value("${app.ldap.bind-dn}") String bindDn,
            @Value("${app.ldap.bind-password}") String password) {

        LdapContextSource source = new LdapContextSource();
        source.setUrl(url);
        source.setBase(base);
        source.setUserDn(bindDn);
        source.setPassword(password);
        source.setPooled(false); // Không bật thêm JNDI native pooling.

        source.setBaseEnvironmentProperties(Map.of(
                "com.sun.jndi.ldap.connect.timeout", "2000",
                "com.sun.jndi.ldap.read.timeout", "4000"));
        return source;
    }

    @Bean("ldapPool")
    PooledContextSource ldapPool(
            @Qualifier("rawLdapContextSource")
            LdapContextSource rawSource) {

        PoolConfig settings = new PoolConfig();

        // Các giới hạn chỉ là giá trị minh họa: điều chỉnh theo tải thật.
        settings.setMaxTotal(16);
        settings.setMaxTotalPerKey(8);
        settings.setMaxIdlePerKey(6);
        settings.setMinIdlePerKey(0);
        settings.setBlockWhenExhausted(true);
        settings.setMaxWaitMillis(700);

        settings.setTestOnBorrow(true);
        settings.setTestOnReturn(false);
        settings.setTestWhileIdle(true);
        settings.setTestOnCreate(false);

        // Cho phép idle evictor chạy và kiểm tra một số đối tượng mỗi vòng.
        settings.setTimeBetweenEvictionRunsMillis(60_000);
        settings.setNumTestsPerEvictionRun(3);
        settings.setMinEvictableIdleTimeMillis(10 * 60_000L);
        settings.setJmxEnabled(true);
        settings.setJmxNamePrefix("ldapDirectory");

        DefaultDirContextValidator validator =
                new DefaultDirContextValidator();
        // Validator mặc định: OBJECT_SCOPE, filter objectclass=*,
        // trả objectClass, countLimit=1, timeLimit=500 ms.

        PooledContextSource pooled = new PooledContextSource(settings);
        pooled.setContextSource(rawSource);
        pooled.setDirContextValidator(validator); // BẮT BUỘC khi bật test.
        return pooled;
    }

    @Bean("ldapTemplate")
    LdapTemplate ldapTemplate(@Qualifier("ldapPool") ContextSource source) {
        return new LdapTemplate(source);
    }
}
```

Ví dụ `application.yml`:

```yaml
app:
  ldap:
    url: ldaps://ldap.example.org:636
    base: dc=example,dc=org
    bind-dn: cn=reader,ou=service,dc=example,dc=org
    bind-password: ${LDAP_BIND_PASSWORD}
```

Đường dẫn, hostname và tất cả giới hạn ở trên là **giả định để học**, không phải khuyến nghị production chung. Cần bảo vệ bind password bằng secret manager/biến môi trường và xác minh certificate/hostname của LDAPS. Cấu hình certificate trust của JVM độc lập với tùy chọn pool validation.

Giải thích các thuộc tính:

| Thiết lập | Chức năng |
|---|---|
| `maxTotal=16` | Giới hạn tổng context trong pool |
| `maxTotalPerKey=8` | Giới hạn context theo loại khóa, ví dụ read-only/read-write |
| `maxIdlePerKey=6` | Không giữ quá nhiều đối tượng idle theo key |
| `maxWaitMillis=700` | Giới hạn thời gian chờ mượn context khi pool cạn |
| `testOnBorrow=true` | Kiểm tra context trước khi cấp cho request |
| `testOnReturn=false` | Không query lại chỉ vì context vừa được trả |
| `testWhileIdle=true` | Cho phép evictor validate context idle |
| `timeBetweenEvictionRunsMillis=60_000` | Evictor có cơ hội chạy mỗi 60 giây |
| `numTestsPerEvictionRun=3` | Giới hạn số đối tượng được xem xét mỗi lượt chạy |
| `setDirContextValidator(...)` | Cung cấp cách kiểm tra thực tế cho các cờ test |

**Lưu ý về bean:** `rawLdapContextSource` và `ldapPool` đều có thể dùng như `ContextSource`. Khi có repository hoặc `LdapTemplate` khác được Spring Boot auto-configure, hãy kiểm tra **nó dùng đúng bean pool**, không đi thẳng qua raw source. Trong hệ thống có nhiều directory, dùng qualifier và cấu hình repository rõ ràng theo từng mục tiêu.

Khi Spring quản lý bean `PooledContextSource`, vòng đời hủy pool có thể gọi `destroy()` lúc shutdown. Nếu tự tạo pool ngoài container, cần đóng/hủy nó đúng cách khi ứng dụng dừng để không giữ connection và idle-evictor thread.

## 7. Chọn chế độ kiểm tra theo SLO và workload

Không có cấu hình “bật hết cả ba” luôn đúng. Có thể bắt đầu từ chiến lược sau rồi kiểm thử:

| Workload | Cấu hình cân nhắc | Lý do |
|---|---|---|
| LDAP server ổn định, request thường xuyên | `testOnBorrow=true`, `testOnReturn=false` | Giảm trả context chết cho request, không probe lúc trả |
| Firewall cắt idle connection thường xuyên | `testOnBorrow=true` + `testWhileIdle=true` | Chủ động dọn context hỏng khi rảnh |
| Ứng dụng có latency budget chặt | Cân nhắc idle validation và giám sát acquire p95 trước khi bật borrow cho mọi request | Probe trên đường request có thể tăng latency |
| Workload rất lớn, server có quota request thấp | Hạn chế số lần probe bằng eviction interval và đối chiếu lỗi thật | Tránh tạo thêm LDAP QPS chỉ để kiểm tra |
| Nghi ngờ context bị lỗi nhưng không được invalidate | Xem exception policy, kiểm thử `testOnReturn` có kiểm soát | Return validation không nên thay cơ chế invalidate theo lỗi |
| Server hay restart/failover | Borrow validation + phát hiện CommunicationException + retry có điều kiện | Phát hiện connection cũ, tạo mới nhưng không đảm bảo mọi request thành công |

Ví dụ ước tính **chi phí lý thuyết**:

```text
Ứng dụng: 150 request đọc LDAP mỗi giây.
Mỗi request mượn 1 context.
testOnBorrow=true -> có thể tạo tới khoảng 150 validation search/giây
                     ngoài 150 business search/giây.
```

Đây là mô hình đơn giản, không phải số liệu đo trên Spring LDAP cụ thể: việc tái sử dụng context, tạo mới, validation options và hành vi pool ảnh hưởng số probe thực tế. Nếu lượng traffic rất cao, probe ở mỗi borrow có thể ảnh hưởng đáng kể LDAP server. `testWhileIdle` định kỳ có overhead khác: phụ thuộc số idle object được kiểm tra mỗi vòng, không tỉ lệ trực tiếp với QPS.

Tránh chỉ tối ưu tốc độ bằng cách tắt validation mà không đo số request thất bại do stale context. Quyết định cần dựa trên **độ trễ, tỷ lệ lỗi và tải máy chủ đồng thời**.

## 8. Đừng nhầm các loại timeout

Trong một lời gọi `repository.findByUid(...)`, lỗi chờ có thể xuất hiện ở các tầng khác nhau:

```text
Service request
     |
     +-- Mượn context từ pool
     |       maxWaitMillis
     |       testOnBorrow (LDAP search validation)
     |
     +-- Nếu cần context mới
     |       TCP connect timeout
     |       TLS handshake + Bind
     |
     +-- LDAP search/lookup
     |       JNDI read timeout
     |       LDAP SearchControls time limit
     |
     +-- Mapping + xử lý kết quả
```

| Timeout | Điều khiển gì? | Không điều khiển gì? |
|---|---|---|
| `PoolConfig.setMaxWaitMillis(700)` | Chờ mượn context khi pool hết | Không giới hạn toàn bộ LDAP search |
| `com.sun.jndi.ldap.connect.timeout` | Kết nối tới LDAP endpoint mới | Không bảo đảm context idle còn hợp lệ |
| `com.sun.jndi.ldap.read.timeout` | Chờ LDAP response theo JNDI provider | Không thay server search size limit |
| `SearchControls.setTimeLimit(500)` trong validator | Giới hạn thời gian tìm kiếm của validation theo SearchControls/provider | Không phải một deadline end-to-end tuyệt đối |
| Deadline HTTP/job | Toàn bộ yêu cầu ứng dụng | Không tự hủy mọi LDAP task đang chạy nếu không có cancellation phù hợp |

Một validator `timeLimit=500ms` không bảo đảm *toàn bộ* `getReadOnlyContext()` sẽ hoàn thành dưới 500 ms: có thể có chờ pool, kết nối mới, TLS/Bind và các bước khác. Nếu exception là `CommunicationException` do mạng, cần xem connection/read timeout và logs server, không chỉ tăng `maxWaitMillis`.

## 9. Pool tự xử lý những lỗi nào?

Ngoài ba cờ test, Spring LDAP `PooledContextSource` hỗ trợ **eager invalidation** với các exception được coi là **non-transient**. Tài liệu nêu `javax.naming.CommunicationException` là ví dụ điển hình; khi gặp lỗi này trên context, pool có thể tự loại đối tượng thay vì cần thêm một lần `testOnReturn`.

```text
Pooled context ACTIVE
     |
     +-- LDAP operation -> SUCCESS -> close() -> pool
     |
     +-- LDAP operation -> CommunicationException
                              |
                              v
                     Invalidate context
                              |
                              v
                        Tạo context mới sau đó
```

Phân biệt:

- **`CommunicationException`:** dấu hiệu kết nối/transport có vấn đề, thường cần loại context.
- **`AuthenticationException`:** credential sai/hết hiệu lực; tạo lại cùng credential có thể tiếp tục thất bại. Cần kiểm tra identity, secret rotation và server auth policy.
- **`NoPermissionException`:** ACL từ chối; không giải quyết bằng cách loại context rồi thử vô hạn.
- **`NameNotFoundException`:** DN không tồn tại; không phải bằng chứng kết nối chết.
- **`SizeLimitExceededException`/`TimeLimitExceededException`:** truy vấn vi phạm giới hạn; cần xét filter/scope/index, không tự quy thành “pool hỏng”.

Không thêm mọi `NamingException` vào danh sách non-transient một cách vô điều kiện. Nếu invalidate context khi có lỗi nghiệp vụ, ứng dụng sẽ gây **kết nối mới liên tục** mà không khắc phục nguyên nhân.

Với `PooledContextSource`, API `setNonTransientExceptions(...)` cho phép cấu hình nhóm ngoại lệ; chỉ dùng sau khi đã kiểm tra behavior của provider và thử nghiệm.

## 10. Quan sát validation mà không làm lộ dữ liệu

Những gauge quan trọng của `PooledContextSource`:

| API | Ý nghĩa |
|---|---|
| `getNumActive()` | Số context đang được mượn |
| `getNumIdle()` | Số context rảnh trong pool |
| `getNumWaiters()` | Số thread đang chờ mượn |
| `getNumActiveRead()` / `getNumActiveWrite()` | Context đang mượn theo loại read/write |
| `getNumIdleRead()` / `getNumIdleWrite()` | Context rảnh theo loại read/write |

Micrometer có thể đo các số này bằng gauge tùy chỉnh:

**`LdapPoolMetrics.java`**

```java
package com.example.ldap;

import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.binder.MeterBinder;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ldap.pool2.factory.PooledContextSource;

@Configuration
public class LdapPoolMetrics {

    @Bean
    MeterBinder ldapPoolMeterBinder(
            @Qualifier("ldapPool") PooledContextSource pool) {
        return registry -> {
            Gauge.builder("ldap.pool.active", pool,
                    PooledContextSource::getNumActive)
                    .tag("pool", "main")
                    .register(registry);
            Gauge.builder("ldap.pool.idle", pool,
                    PooledContextSource::getNumIdle)
                    .tag("pool", "main")
                    .register(registry);
            Gauge.builder("ldap.pool.waiters", pool,
                    PooledContextSource::getNumWaiters)
                    .tag("pool", "main")
                    .register(registry);
        };
    }
}
```

Các metric `ldap.pool.*` ở ví dụ **do ứng dụng đăng ký**, không phải mặc định mọi Spring Boot Actuator tự cung cấp. Muốn thấy trên Prometheus/Grafana phải cấu hình registry/exporter và endpoint phù hợp.

Riêng validation cần kết hợp thêm các phép đo ở tầng instrumentation:

1. **Context acquire latency** p50/p95/p99 (bao gồm validation nếu bật `testOnBorrow`).
2. **Tỷ lệ lỗi borrow/context creation**, số lần phải tạo context mới hoặc invalidate.
3. **Độ trễ LDAP operation** và tỷ lệ `CommunicationException`.
4. **Validation attempt/failure** và duration nếu bổ sung instrumentation cho validator; `PooledContextSource` không tự công bố tất cả chỉ số này dưới dạng các getter bên trên.
5. **LDAP server search QPS**, số connection và CPU để thấy overhead probe.
6. **TLS handshake/Bind latency**, đặc biệt khi context bị hủy hàng loạt sau restart server.

Không đưa password, DN đầy đủ, raw LDAP filter chứa thông tin người dùng hoặc địa chỉ email vào metric tags. Nên dùng tag ổn định như tên pool, loại context, environment và kết quả success/failure.

### 10.1. Đọc metric theo cặp

| Quan sát | Giả thuyết ban đầu | Việc cần kiểm tra |
|---|---|---|
| `active` cao, `idle=0`, `waiters>0` | Pool cạn | Giới hạn theo key, thời gian giữ context |
| Acquire p95 tăng, `waiters≈0` | Validation hoặc kết nối mới chậm | Probe latency, TLS/Bind, JNDI read timeout |
| Validation failure tăng sau server restart | Context cũ đã chết | Tỷ lệ tạo mới, server đã hồi phục chưa |
| `idle` cao nhưng lookup lỗi ACL | Context còn hoạt động nhưng không đủ quyền | Bind identity, ACL và schema |
| `testWhileIdle=true` nhưng idle failures không xuất hiện | Evictor chưa chạy/không quét tới context | `timeBetweenEvictionRunsMillis`, số test mỗi lượt |
| QPS LDAP tăng mạnh sau bật `testOnBorrow` | Overhead probe | So sánh hiệu quả giảm lỗi stale context |

Gauge chỉ là ảnh chụp tức thời; `waiters=0` trong một lần scrape **không chứng minh** chưa có đợt đợi giữa hai lần lấy mẫu. Dùng timer/counter để quan sát xu hướng.

## 11. Kiểm thử tích hợp ba chế độ validation

Để chứng minh pool phát hiện context cũ, cần **LDAP test directory** thực hoặc test double điều khiển được trạng thái `DirContext`. Unit test chỉ đọc lại cờ cấu hình chưa chứng minh validator đã chạy.

### 11.1. Smoke test pool trả context đúng vòng đời

**`LdapPoolIT.java`**

```java
package com.example.ldap;

import javax.naming.directory.DirContext;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.ldap.pool2.factory.PooledContextSource;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
class LdapPoolIT {
    @Autowired
    @Qualifier("ldapPool")
    PooledContextSource pool;

    @Test
    void borrowAndCloseReturnsToPool() throws Exception {
        // Test phải chạy trên pool không có request khác dùng đồng thời.
        int before = pool.getNumActiveRead();

        DirContext context = pool.getReadOnlyContext();
        try {
            assertEquals(before + 1, pool.getNumActiveRead());
            assertTrue(pool.getNumActive() > 0);
        } finally {
            context.close();
        }

        assertEquals(before, pool.getNumActiveRead());
    }
}
```

**Điều kiện chạy:** phải có LDAP test directory hợp lệ, bean `ldapPool` cấu hình như ví dụ, base entry đọc được bởi validator và không có test khác cùng lúc mượn context. Nếu pool đang được chia sẻ với ứng dụng thật, assertion count tuyệt đối có thể không ổn định; cần tách pool riêng cho test.

Test này chỉ chứng minh **borrow/return** và pool không bị giữ active do test; nó **không** chứng minh kết nối chết đã bị loại. Cần kiểm thử hỏng kết nối riêng.

### 11.2. Kiểm thử testOnBorrow bằng server outage

Quy trình trên một LDAP server thử nghiệm:

1. Tạo `PooledContextSource` với `maxTotalPerKey=1`, `testOnBorrow=true`, `testOnReturn=false`, `testWhileIdle=false` và validator đọc được một entry.
2. Mượn context, thực hiện lookup thành công rồi `close()` để nó rảnh trong pool.
3. Dừng LDAP server hoặc ngắt connection test theo cơ chế có kiểm soát.
4. Mượn context lần nữa. Validation phải thử kiểm tra; đối tượng không còn dùng được phải bị loại. Khi server còn down, lệnh mượn/tạo mới có thể kết thúc bằng lỗi, **không** được trả về một context giả như thể hoạt động tốt.
5. Khởi động lại server. Lần mượn mới phải tạo hoặc lấy context hợp lệ; kiểm tra được thực hiện theo chính sách pool.
6. Kiểm tra logs/metrics: số lần validation fail, thay context và chi phí acquire.

Không assert rằng lỗi luôn xuất hiện sau **đúng 500ms**: đó là thời gian giới hạn **SearchControls** của validator, chưa bao gồm thời gian network, connect/Bind, scheduler hay việc pool retry tạo context.

### 11.3. Kiểm thử testOnReturn

1. Bật `testOnReturn=true`, tắt borrow/idle để cô lập hành vi.
2. Mượn context hợp lệ.
3. Dùng test double làm cho validator báo `false` lúc gọi `close()`, hoặc gây sự cố LDAP có kiểm soát.
4. Kiểm tra pool **không đưa context đã fail validation trở lại idle**.
5. Đo thời gian trả context và xem việc bật chế độ này có tăng latency nghiệp vụ không.

Nếu chọn lỗi `CommunicationException` từ một LDAP operation để làm context hỏng, pool có thể đã **eager invalidate** trước khi `testOnReturn` chạy. Vì vậy để chứng minh riêng test-on-return, test double kiểm soát được validator rõ ràng hơn.

### 11.4. Kiểm thử testWhileIdle

1. Bật `testWhileIdle=true` và đặt `timeBetweenEvictionRunsMillis` nhỏ **chỉ trong test**, ví dụ 200–500ms; giới hạn `numTestsPerEvictionRun` rõ ràng.
2. Mượn/trả context để tạo một đối tượng idle.
3. Làm validator test trả `false` với context idle đó.
4. Dùng điều kiện chờ có timeout (thay vì `Thread.sleep` cố định) để quan sát `getNumIdleRead()` giảm hoặc context cũ bị thay thế.
5. Xác nhận **context đang active** không bị evictor tự ý kiểm tra/hủy như một idle object.
6. Dọn pool và thread sau test.

Test không nên dựa vào thứ tự chạy tuyệt đối của evictor: nó là background activity, có jitter scheduler, thứ tự chọn object và chính sách eviction.

### 11.5. Ma trận kiểm thử cần có

| Kịch bản | Kỳ vọng |
|---|---|
| Context hợp lệ, `testOnBorrow` bật | Có thể mượn, dùng, trả; probe không bị ACL từ chối |
| Context hỏng sau idle, `testOnBorrow` bật | Loại context cũ trước khi cấp thành công cho nghiệp vụ |
| `testOnBorrow` tắt | Không được tuyên bố stale connection đã được ngăn; nghiệp vụ có thể gặp lỗi |
| `testOnReturn` bật, validator fail | Context không trở lại pool idle |
| `testWhileIdle` bật nhưng evictor tắt | Không mong đợi validation nền |
| Idle evictor chạy, validator fail | Context idle hỏng bị hủy sau lần quét phù hợp |
| Base validation không đọc được do ACL | Có validation failure dù business lookup có thể vẫn hoạt động |
| LDAP server down rồi up | Không dùng context cũ không hợp lệ; hồi phục được sau restart |
| `maxTotalPerKey` đạt giới hạn | Caller chờ trong `maxWaitMillis` hoặc fail theo cấu hình |
| Caller quên `close()` | Active không giảm; phát hiện leak và timeout borrow |
| Bind password đổi/hết hiệu lực | Phân biệt authentication error với connection chết |
| Read-only context và read-write context | Theo dõi/validate theo loại context thực tế |
| Network chậm nhưng chưa chết | Đánh giá false negatives của probe và ảnh hưởng latency |
| TLS certificate server thay đổi | Đảm bảo trust/hostname validation vẫn đúng khi tạo kết nối mới |

## 12. Các lỗi phổ biến và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Đã bật `testOnBorrow` nhưng khởi động báo lỗi cấu hình | Chưa `setDirContextValidator(...)` | Cung cấp `DefaultDirContextValidator` hoặc implementation phù hợp |
| Probe luôn thất bại dù LDAP có thể lookup | Base/filter validation sai hoặc ACL không cho đọc entry đó | Chọn entry kiểm tra có quyền đọc; xác minh ContextSource.base |
| `testWhileIdle=true` mà không có probe nền | Evictor chưa bật | Đặt `timeBetweenEvictionRunsMillis` dương và kiểm tra version |
| Mọi request chậm thêm một round-trip | `testOnBorrow` gửi validation search | Đo acquire p95 và directory QPS; hiệu chỉnh chiến lược |
| Connection vẫn hỏng sau probe thành công | Lỗi xảy ra sau khi probe | Xử lý CommunicationException và invalidation; không kỳ vọng “bất tử” |
| `active` không giảm | Caller không trả context hoặc giữ enumeration/kết quả quá lâu | Dùng `LdapTemplate`, đóng resource trong `finally` |
| Tăng pool size không giải quyết timeout | LDAP server chậm hoặc validation quá đắt | Tối ưu query, timeout, validator và concurrency |
| Giữ nhiều context idle nhưng không sử dụng | `minIdlePerKey`/`maxIdlePerKey` quá cao, eviction không hoạt động | Điều chỉnh idle và eviction theo tải |
| Lỗi ACL bị ghi thành “connection dead” | Nhầm `NoPermissionException` với `CommunicationException` | Phân loại lỗi, không invalidate mọi exception |
| StartTLS/mTLS gặp lỗi khi tái sử dụng context | Kết hợp TLS state và pooling không phù hợp | Xem tài liệu Spring LDAP; kiểm thử chuyên biệt, tránh native JNDI pooling tùy tiện |
| Bật test-on-return và vẫn thấy lỗi borrow | Context hỏng **sau** khi đã trả | Xem xét borrow/idle validation |
| Chạy hai tầng pool khiến metric khó hiểu | Vừa `setPooled(true)` vừa `PooledContextSource` | Dùng một chiến lược pool rõ ràng |

**Không chữa mọi lỗi bằng retry vô hạn.** Nếu LDAP server down, retry nhanh từ nhiều replica có thể tạo **retry storm** khiến server hồi phục khó hơn. Cần timeout hữu hạn, backoff/jitter, giới hạn concurrency và phản hồi lỗi rõ ràng.

## 13. Vấn đề bảo mật riêng của context pool

Pool context chứa thông tin **đã xác thực**. Khi tái sử dụng, cần bảo đảm identity và trạng thái request trước không bị rò sang request sau:

- **Service account pool:** có thể phù hợp với thao tác đọc/ghi kỹ thuật dưới một identity cố định, theo ACL tối thiểu.
- **User Bind động:** không gom các context gắn credential của nhiều người dùng vào một pool service một cách tùy tiện. Kiểm tra Spring LDAP API và chiến lược credential để tránh reuse sai identity.
- **StartTLS/LDAP controls:** một số thao tác thay đổi trạng thái `LdapContext` hoặc request controls (paging, sort, authorization control); cần cơ chế context pooling tương thích, tránh để trạng thái request trước ảnh hưởng request sau.
- **TLS:** validation search không thay cho xác minh certificate chain và hostname của LDAP server.
- **Rotation:** đổi bind password/certificate có thể cần tái tạo context mới và drain idle pool; không giả định mọi context sống sẽ tự cập nhật credential.
- **Least privilege:** account dùng validation không cần quyền sửa LDAP; tuyệt đối không dùng write probe trên directory production chỉ để kiểm tra pool.

Khi dùng `PooledContextSource` với workflow có LDAP controls/`LdapContext` mutable, tham khảo `MutablePooledContextSource` và kiểm thử đường trả context. Không coi mọi proxy pool là hỗ trợ tất cả JNDI mutations giống nhau.

## 14. Quy trình chọn cấu hình production

Một quy trình thực dụng:

1. **Chọn pool rõ ràng:** Spring LDAP Pool2 hay native JNDI; nếu cần ba chế độ validation, chọn Pool2.
2. **Cấu hình context nguồn:** endpoint LDAPS/StartTLS đúng, truststore, bind DN/secret, base DN, timeout; native pooling tắt khi dùng Pool2.
3. **Kiểm tra validator mặc định:** base/filter được phép truy cập dưới đúng identity và naming context.
4. **Bật tối thiểu cần thiết:** thường bắt đầu với `testOnBorrow`, cân nhắc `testWhileIdle` nếu kết nối idle dễ bị cắt; `testOnReturn` chỉ bật khi có lý do và số liệu.
5. **Bật evictor đúng cách:** đặt khoảng chạy dương nếu dùng idle validation, số lượng test mỗi vòng và idle eviction threshold phù hợp.
6. **Giới hạn pool:** cấu hình `maxTotal`, `maxTotalPerKey`, `maxWaitMillis` theo concurrency và số replica ứng dụng.
7. **Quan sát trước/sau:** đo acquire p95, validation failure, LDAP QPS, active/idle/waiters, TLS/Bind latency, lỗi nghiệp vụ.
8. **Thử lỗi có kiểm soát:** restart test LDAP, ngắt network, thay secret trong staging; xác nhận hồi phục và không loop vô hạn.
9. **Đảm bảo quyền và trạng thái:** ACL, referrals, tenant, LDAP controls, rotation, cấu hình pool read/write.
10. **Đánh giá định kỳ:** pool cần đổi theo lưu lượng thực và cấu hình firewall/server; không chỉ cấu hình một lần rồi bỏ mặc.

### Khi nào không cần bật cả ba?

Nếu workload có nhiều request ngắn và server tương đối ổn định, `testOnBorrow=true` có thể đủ để giảm lỗi stale context; `testOnReturn` chỉ tăng chi phí mà lợi ích nhỏ. Nếu phần lớn request hiếm nhưng connection thường idle lâu, `testWhileIdle` định kỳ hoặc chính sách eviction phù hợp sẽ hữu ích hơn việc giữ quá nhiều connection lâu dài. Khi server rất nhạy với QPS, cần so sánh overhead của cả hai trước khi bật.

**Mục tiêu không phải “pool luôn có 100% context hợp lệ”** vì mạng và server có thể thay đổi giữa hai lời gọi. Mục tiêu là giảm lỗi, phát hiện nhanh context hỏng, hạn chế tải nền và giữ latency trong SLO của hệ thống.

## 15. Câu hỏi tự kiểm tra

1. Vì sao một `DirContext` đang idle trong pool có thể không còn dùng được dù trước đó Bind thành công?
2. `testOnBorrow`, `testOnReturn` và `testWhileIdle` khác nhau về thời điểm và chi phí?
3. Bật `testWhileIdle=true` nhưng giữ `timeBetweenEvictionRunsMillis` ở chế độ tắt thì chuyện gì xảy ra?
4. `DefaultDirContextValidator` thực hiện loại LDAP operation nào? Base, filter, scope và limit mặc định là gì?
5. Vì sao một validator search thành công **không chứng minh** context có quyền ghi hoặc kết nối sẽ không hỏng ngay sau đó?
6. Tại sao cần `setDirContextValidator(...)` khi bật test mode trong `PooledContextSource`?
7. `maxWaitMillis` khác JNDI `connect.timeout`/`read.timeout` như thế nào?
8. Nếu app bị chậm khi mượn context nhưng `getNumWaiters()` gần 0, bạn sẽ kiểm tra những nguyên nhân nào?
9. Vì sao nên phân biệt `CommunicationException` và `NoPermissionException` trong việc invalidate context?
10. Khi LDAP server restart và context idle cũ mất hiệu lực, test integration nào chứng minh borrow validation thực sự hoạt động?
11. Vì sao không nên dùng một pool service account cho mọi context xác thực của người dùng cuối?
12. Nếu bật `testOnBorrow` làm LDAP QPS tăng mạnh, cần cân bằng những chỉ số nào trước khi thay đổi chiến lược?

**Ghi nhớ:** kiểm tra context ở **lúc lấy** (`testOnBorrow`), **lúc trả** (`testOnReturn`) và **khi nhàn rỗi** (`testWhileIdle`) phục vụ ba thời điểm khác nhau. Với Spring LDAP Pool2, hãy cấu hình **`PoolConfig` + `DirContextValidator`**, bật idle evictor nếu muốn test nền, và quan sát acquire latency cùng lỗi stale context để cân bằng độ tin cậy với overhead. Validation chỉ kiểm tra phản hồi của kết nối tại thời điểm đó; nó **không thay thế** TLS verification, ACL, quản lý credential hay xử lý lỗi LDAP trong nghiệp vụ.

### Tài liệu tham khảo

- Spring LDAP — [Pooling Support](https://docs.spring.io/spring-ldap/reference/pooling.html): validation, thời điểm kiểm tra, `DefaultDirContextValidator` và non-transient exception invalidation.
- Spring LDAP API — [`PooledContextSource`](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/pool2/factory/PooledContextSource.html): cấu hình context/validator, số active/idle/waiters.
- Spring LDAP API — [`PoolConfig`](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/pool2/factory/PoolConfig.html): test-on-borrow/return/while-idle, eviction, giới hạn và JMX.
- Spring LDAP API — [`DefaultDirContextValidator`](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/pool2/validation/DefaultDirContextValidator.html): search validation mặc định, `setBase`, `setFilter`, `setSearchControls`.
- Spring LDAP API — [`DirContextValidator`](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/pool2/validation/DirContextValidator.html): hợp đồng `validateDirContext(DirContextType, DirContext)`.
- Apache Commons Pool 2 — [GenericKeyedObjectPool](https://commons.apache.org/proper/commons-pool/apidocs/org/apache/commons/pool2/impl/GenericKeyedObjectPool.html): vòng đời object, validation và eviction.
- Oracle Java — [`DirContext`](https://docs.oracle.com/en/java/javase/17/docs/api/java.naming/javax/naming/directory/DirContext.html), [`SearchControls`](https://docs.oracle.com/en/java/javase/17/docs/api/java.naming/javax/naming/directory/SearchControls.html): JNDI LDAP query và giới hạn tìm kiếm.
