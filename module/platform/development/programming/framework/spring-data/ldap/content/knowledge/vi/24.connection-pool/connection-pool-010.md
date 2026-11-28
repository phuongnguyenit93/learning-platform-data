# Nhận diện cạn pool, rò rỉ context và yêu cầu giữ kết nối lâu

## 1. Khi nào cần nghi ngờ pool kết nối LDAP?

Ứng dụng **Spring Data LDAP** thường thực hiện nhiều thao tác directory trong cùng một khoảng thời gian: repository tìm người dùng, `LdapTemplate` đọc nhóm, service kiểm tra quyền, job đồng bộ duyệt hàng nghìn entry. Mỗi thao tác cần một `DirContext` để giao tiếp với LDAP server. Nếu ứng dụng tạo kết nối mới cho mọi thao tác, chi phí bind, TLS handshake và thiết lập socket có thể lớn. Pool giúp tái sử dụng các context đã được tạo.

Tuy nhiên, pool có số lượng context hữu hạn. Khi mọi context đều đang được mượn, request tiếp theo phải chờ context được trả lại hoặc bị từ chối sau thời gian chờ. Tình trạng này gọi là **pool exhaustion** (cạn pool).

Ví dụ pool cho phép tối đa 8 context đọc:

~~~text
Thời điểm T0:
  active = 8
  idle   = 0
  waiters = 0

Thời điểm T1:
  8 request đang giữ context
  5 request mới cần context
  waiters = 5

Thời điểm T2:
  request mới phải chờ context được trả lại
  latency tăng, thread ứng dụng bị giữ
~~~

Pool cạn không tự chứng minh có memory leak hoặc connection leak. Nó có thể do tải đồng thời tăng, LDAP server phản hồi chậm, truy vấn giữ context lâu, callback thực hiện công việc downstream hoặc ứng dụng quên đóng `DirContext`.

Bài học này hướng dẫn phân biệt các nguyên nhân, đọc chỉ số pool, kiểm tra vòng đời context và cấu hình pool có giới hạn chờ phù hợp.

Sau bài này, người học có thể:

1. Giải thích vai trò của `ContextSource`, `DirContext` và pool trong Spring LDAP.
2. Nhận biết dấu hiệu pool exhaustion qua active, idle, waiter và thời gian chờ.
3. Phân biệt connection leak với context được giữ lâu do truy vấn hoặc xử lý chậm.
4. Đóng `DirContext` và `NamingEnumeration` đúng cách khi dùng JNDI trực tiếp.
5. Hiểu cách `LdapTemplate` tự quản lý vòng đời context.
6. Cấu hình pool với giới hạn active, max wait và validation.
7. Theo dõi pool read/write và điều chỉnh kích thước dựa trên số liệu.
8. Xử lý các trường hợp paging, callback, authentication và shutdown an toàn.

> **Nguyên tắc:** Một context được mượn phải được trả lại sớm nhất có thể sau khi thao tác LDAP kết thúc. Tăng kích thước pool chỉ giúp khi tải đồng thời thực sự cần thêm kết nối và LDAP server còn đủ khả năng phục vụ.

## 2. Các thành phần trong vòng đời kết nối

### 2.1. `ContextSource` và `DirContext`

Trong Spring LDAP, `ContextSource` là abstraction tạo context để ứng dụng truy cập directory:

- `getReadOnlyContext()` cấp context cho các thao tác đọc.
- `getReadWriteContext()` cấp context cho các thao tác ghi.
- `getContext(principal, credentials)` tạo context với thông tin xác thực được chỉ định, thường dùng trong luồng bind/authentication.

`DirContext` là đối tượng JNDI thực hiện các thao tác như Search, Lookup, Add, Modify và Delete.

Khi không có pool, `ContextSource` thường tạo context mới theo yêu cầu rồi đóng context sau thao tác. Khi có pool, context được bọc bởi một đối tượng quản lý pool. `close()` trên context được mượn sẽ trả nó về pool để tái sử dụng nếu context còn hợp lệ.

~~~mermaid
flowchart TD
    A["Ứng dụng gọi LdapTemplate"] --> B["ContextSource"]
    B --> C{"Có context idle?"}
    C -->|Có| D["Mượn context từ pool"]
    C -->|Không| E{"Còn capacity?"}
    E -->|Có| F["Tạo context mới"]
    E -->|Không| G["Chờ hoặc báo pool exhausted"]
    D --> H["Thực hiện LDAP operation"]
    F --> H
    H --> I["Đóng context wrapper"]
    I --> J["Trả context về pool hoặc loại bỏ nếu hỏng"]
    J --> K["Sẵn sàng cho lần mượn tiếp theo"]
~~~

Một context đang active là context đã được cấp cho caller và chưa được trả về. Context idle đang nằm trong pool, sẵn sàng được mượn.

### 2.2. Pool giữ context, không giữ request nghiệp vụ

Pool không nên bị giữ trong suốt vòng đời của HTTP request nếu request chỉ thực hiện một thao tác LDAP ngắn. Thông thường, một lần gọi `LdapTemplate` mượn context, thực hiện thao tác, đóng context rồi trả kết quả Java cho service.

Nếu service gọi ba thao tác LDAP tuần tự, mỗi thao tác có thể mượn và trả context riêng. Một số cơ chế như giữ một context xuyên nhiều thao tác hoặc paging cần cùng connection sẽ có vòng đời dài hơn; khi đó phải giới hạn phạm vi giữ context.

Không nên lưu `DirContext` trong:

- Field của singleton service.
- Static variable.
- Cache ứng dụng.
- Session HTTP.
- Message hoặc job được xử lý bất đồng bộ.
- `ThreadLocal` không có cơ chế cleanup chắc chắn.

Một context được mượn thuộc về một lần sử dụng cụ thể. Không chia sẻ đồng thời cùng `DirContext` cho nhiều thread.

### 2.3. `close()` có ý nghĩa gì khi dùng pool?

Với context lấy từ pooled `ContextSource`, gọi `close()` thường trả wrapper về pool. Nó không nhất thiết đóng socket vật lý ngay lập tức. Pool quyết định giữ context idle để tái sử dụng hay loại bỏ context không hợp lệ.

Nếu không gọi `close()`, pool không biết caller đã dùng xong context. Slot vẫn bị tính là active, kể cả khi thread đã kết thúc hoặc không còn thực hiện LDAP operation.

Đây là nguyên nhân phổ biến của connection leak.

## 3. Nhận diện ba tình trạng dễ nhầm

### 3.1. Pool exhaustion do tải đồng thời thật sự

Dấu hiệu thường gặp:

- `active` chạm giới hạn trong giờ cao điểm.
- `idle` thường xuyên bằng 0.
- Số waiter tăng khi tải tăng.
- Khi tải giảm, active giảm và waiter được giải phóng.
- Không có một context nào bị giữ vô thời hạn.
- Thời gian thực hiện LDAP operation tăng theo tải hoặc theo độ phức tạp truy vấn.

Ví dụ: 20 request đồng thời, mỗi request thực hiện một Search mất 200 ms, nhưng pool chỉ cho phép 8 context. Những request còn lại phải chờ.

Hướng xử lý:

1. Đo tốc độ request và thời gian giữ context.
2. Kiểm tra LDAP server có chịu được concurrency cao hơn không.
3. Tối ưu filter, base DN, scope và index.
4. Cân nhắc tăng pool có giới hạn nếu server còn capacity.
5. Giới hạn concurrency ở ứng dụng để không tạo hàng đợi quá lớn.

### 3.2. Context leak (không trả context)

Dấu hiệu thường gặp:

- `active` tăng dần theo thời gian và không giảm sau khi tải đã kết thúc.
- `idle` về 0, waiter tăng dù số request đang chạy thấp.
- Một số luồng đã kết thúc nhưng context vẫn được pool xem là đang mượn.
- Restart ứng dụng làm tình trạng biến mất tạm thời.
- Pool lại cạn sau khi ứng dụng chạy đủ lâu.

Hướng xử lý:

1. Tìm nơi gọi trực tiếp `ContextSource.getReadOnlyContext()` hoặc `getReadWriteContext()`.
2. Kiểm tra mọi nhánh `return`, `break` và exception có đi qua cleanup không.
3. Kiểm tra `NamingEnumeration` có được đóng không.
4. Tìm context bị lưu vào field, ThreadLocal hoặc chuyển sang async worker.
5. Dùng thread dump, log và instrumentation để xác định vị trí mượn context.

### 3.3. Context bị giữ lâu (long hold)

Context có thể được đóng đúng cách nhưng vẫn giữ pool slot trong thời gian quá dài.

Ví dụ:

~~~text
Search LDAP:              100 ms
Map một entry:             10 ms
Ghi database batch:       900 ms
Gọi HTTP service:        1.500 ms
Đợi queue có chỗ:        2.000 ms
Tổng thời gian giữ context: 4.510 ms
~~~

Nếu callback thực hiện tất cả công việc trên trong khi `LdapTemplate.search` đang duyệt kết quả, context LDAP vẫn được giữ trong toàn bộ thời gian callback chạy.

Hướng xử lý:

- Giảm công việc không liên quan LDAP bên trong callback.
- Chỉ map dữ liệu cần thiết thành DTO độc lập.
- Đưa dữ liệu sang bounded queue hoặc staging store có giới hạn.
- Không chờ HTTP, message broker hoặc database lâu trong lúc giữ context nếu có thể tách bước.
- Nếu cần cùng connection cho paging, giữ context trong đúng phạm vi vòng lặp paging rồi trả ngay sau đó.

### 3.4. Bảng phân biệt nhanh

| Quan sát | Tải đồng thời cao | Context leak | Context giữ lâu |
| --- | --- | --- | --- |
| Active | Tăng theo tải, sau đó giảm | Tăng dần và khó giảm | Cao trong thời gian thao tác kéo dài |
| Idle | Thấp trong peak | Thường bằng 0 | Thấp trong thời gian xử lý |
| Waiters | Tăng khi có burst | Tăng theo thời gian | Tăng trong lúc các operation giữ context |
| Thời gian giữ context | Phù hợp với thời gian LDAP operation | Bất thường hoặc không kết thúc | Lớn hơn thời gian LDAP cần thiết |
| Sau khi tải giảm | Pool hồi phục | Có thể vẫn cạn | Hồi phục khi thao tác dài kết thúc |
| Ưu tiên điều tra | Capacity và concurrency | Cleanup/lifecycle | Callback, paging, downstream và transaction scope |

Không kết luận leak chỉ từ một ảnh chụp `active=max`. Hãy quan sát xu hướng qua nhiều chu kỳ tải và đối chiếu với số operation đang thực sự chạy.

## 4. Cấu hình pool trong Spring LDAP

Spring LDAP cung cấp pooling dựa trên Apache Commons Pool. Có hai nhánh API cần phân biệt:

- `PoolingContextSource` trong package `org.springframework.ldap.pool.factory` dùng Commons Pool 1.x.
- `PooledContextSource` trong package `org.springframework.ldap.pool2.factory` dùng Commons Pool 2.x.

Không trộn các class, validator hoặc cấu hình của hai package. Ví dụ dưới đây sử dụng nhánh Pool 2.

### 4.1. Cấu hình `PooledContextSource`

~~~java
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

    @Bean
    ContextSource contextSource() throws Exception {
        LdapContextSource target = new LdapContextSource();
        target.setUrl("ldaps://ldap.example.org:636");
        target.setBase("dc=example,dc=org");
        target.setUserDn(
            "uid=app-reader,ou=service-accounts,dc=example,dc=org"
        );
        target.setPassword(System.getenv("LDAP_BIND_PASSWORD"));
        target.afterPropertiesSet();

        PoolConfig config = new PoolConfig();

        // Giới hạn tổng số context và số context cho mỗi loại.
        config.setMaxTotalPerKey(12);
        config.setMaxTotal(24);

        // Chờ tối đa 1,5 giây khi pool hết context.
        config.setBlockWhenExhausted(true);
        config.setMaxWaitMillis(1_500);

        // Kiểm tra context trước khi cấp và khi đang idle.
        config.setTestOnBorrow(true);
        config.setTestWhileIdle(true);
        config.setTimeBetweenEvictionRunsMillis(30_000);

        PooledContextSource pool = new PooledContextSource(config);
        pool.setContextSource(target);
        pool.setDirContextValidator(
            new DefaultDirContextValidator()
        );

        return pool;
    }

    @Bean
    LdapTemplate ldapTemplate(ContextSource contextSource) {
        return new LdapTemplate(contextSource);
    }
}
~~~

Đây là cấu hình minh họa cho Spring LDAP có package `pool2`. Hãy dùng đúng dependency và version đang được ứng dụng quản lý. Trong môi trường thật, URL, base DN và bind credential nên được inject từ cấu hình bảo mật; certificate và hostname của LDAPS phải được xác minh.

`PooledContextSource` là một Spring bean quản lý vòng đời pool và triển khai `DisposableBean`. Để Spring quản lý bean này tới shutdown; không gọi `destroy()` sau mỗi request.

### 4.2. Ý nghĩa các giới hạn

| Thuộc tính | Ý nghĩa |
| --- | --- |
| `maxTotalPerKey` | Số context tối đa cho mỗi key/loại context trong pool |
| `maxTotal` | Tổng số context tối đa trên tất cả key |
| `maxWaitMillis` | Thời gian tối đa chờ mượn context |
| `blockWhenExhausted` | Có chờ khi pool hết context hay từ chối ngay |
| `maxIdlePerKey` | Số context idle tối đa giữ lại cho mỗi key |
| `minIdlePerKey` | Số context idle tối thiểu muốn duy trì |
| `testOnBorrow` | Kiểm tra context trước khi cấp cho caller |
| `testOnReturn` | Kiểm tra context khi caller trả lại |
| `testWhileIdle` | Kiểm tra các context đang nằm idle |
| `timeBetweenEvictionRunsMillis` | Khoảng thời gian giữa các lần kiểm tra/eviction idle |

Với pool2, mặc định thường gặp là `maxTotalPerKey=8`, `maxTotal=-1` và `maxWaitMillis=-1`. `-1` cho max wait có nghĩa là chờ vô hạn. Không nên giữ mặc định chờ vô hạn cho một service API có SLA rõ ràng.

Pool cũ `PoolingContextSource` có các thuộc tính tương tự nhưng tên API khác, ví dụ `maxActive`, `maxTotal` và `maxWait`. Hãy tra tài liệu đúng package thay vì copy cấu hình pool2 sang pool1.

### 4.3. Không nhầm `maxIdle` với `maxActive`

- `maxActive` hoặc `maxTotalPerKey` giới hạn số context có thể được mượn đồng thời cho key đó.
- `maxIdle` hoặc `maxIdlePerKey` giới hạn số context được giữ lại khi đã trả về pool.
- `minIdle` hoặc `minIdlePerKey` đặt mức idle mong muốn, không phải giới hạn concurrency.
- `maxTotal` giới hạn tổng pool khi có nhiều key.

Tăng `maxIdle` không giải quyết tình trạng active đạt trần. Tăng `maxActive` cũng không có nghĩa cần giữ tất cả kết nối idle sau giờ cao điểm.

### 4.4. Chính sách khi pool cạn

Với Pool2, `blockWhenExhausted` quyết định pool chờ hay từ chối ngay:

| Chính sách | Hành vi | Khi phù hợp |
| --- | --- | --- |
| Block có giới hạn | Chờ context trả lại tới `maxWaitMillis` | API có thể chịu một khoảng chờ ngắn |
| Không block | Từ chối nhanh khi không còn capacity | Cần fail-fast và có retry/backpressure ở tầng gọi |
| Chờ vô hạn | Thread có thể chờ không giới hạn | Thường không phù hợp với request xử lý đồng bộ |
| Grow (một số cấu hình Pool 1 cũ) | Tạo thêm context ngoài mức giới hạn active | Có nguy cơ vượt connection limit của LDAP server; Pool2 không dùng lựa chọn này |

Với service đồng bộ, thường nên chọn block có giới hạn hoặc fail-fast. Nếu pool chờ vô hạn, thread HTTP có thể bị chiếm hết trong khi đợi context, kéo theo thread pool của web server cũng cạn.

Không dùng chính sách grow để che giấu leak hoặc truy vấn chậm. Khi không còn giới hạn rõ ràng, một đợt traffic tăng có thể mở quá nhiều LDAP connection và làm server quá tải.

Khi pool hết và thời gian chờ đã hết, Commons Pool có thể phát sinh `NoSuchElementException`. Spring LDAP có thể bọc lỗi lấy context thành `DataAccessResourceFailureException`; hãy xem cause chain để phân biệt lỗi pool với lỗi LDAP bind hoặc lỗi Search.

## 5. Validation và loại bỏ context hỏng

### 5.1. Vì sao cần validation?

Một context idle có thể không còn sử dụng được do:

- LDAP server đóng connection sau thời gian idle.
- Firewall hoặc load balancer loại bỏ TCP connection.
- Server failover hoặc restart.
- TLS session hoặc network path gặp lỗi.
- Password/bind identity bị thay đổi.
- Connection đã lỗi trong lần sử dụng trước.

Nếu pool cấp context hỏng cho caller, request sẽ thất bại ngay trong thao tác LDAP.

Spring LDAP cung cấp `DirContextValidator` để kiểm tra context khi borrow, return hoặc trong lúc idle.

### 5.2. `DefaultDirContextValidator`

Validator mặc định thực hiện một Search nhỏ:

- Base rỗng.
- Filter `objectclass=*`.
- Giới hạn một kết quả.
- Chỉ lấy attribute `objectclass`.
- Time limit 500 ms.
- Search scope mặc định là `OBJECT_SCOPE`.

Nếu Search trả kết quả, context được xem là hợp lệ. Nếu không có kết quả hoặc có exception, validation thất bại và pool loại context đó.

Validator có thể được cấu hình base/filter/search controls riêng nếu directory không cho phép kiểm tra ở base mặc định. Hãy chọn một entry/base mà bind identity có quyền đọc và bảo đảm validation query không quá tốn tài nguyên.

### 5.3. `testOnBorrow` và `testWhileIdle`

Hai lựa chọn này giải quyết các thời điểm khác nhau:

- `testOnBorrow=true`: kiểm tra trước khi cấp context. Tăng độ tin cậy khi có nhiều connection idle lâu, nhưng thêm chi phí validation vào thời gian borrow.
- `testWhileIdle=true`: kiểm tra các context đang idle theo chu kỳ eviction. Có thể loại connection chết trước khi request cần dùng.
- `testOnReturn=true`: kiểm tra khi trả context. Có thể hữu ích với một số hệ thống nhưng làm tăng chi phí mỗi lần return.

Không bật tất cả validation option một cách máy móc. Bắt đầu từ lỗi stale connection đã quan sát, bật validation phù hợp và đo thời gian borrow/latency sau thay đổi.

### 5.4. Context gặp `CommunicationException`

Spring LDAP mặc định xem `javax.naming.CommunicationException` là lỗi không tạm thời đối với context đang được pool quản lý. Context lỗi được đánh dấu để loại bỏ thay vì tái sử dụng như một kết nối khỏe.

Điều này giúp tránh đưa một socket đã mất kết nối trở lại pool. Tuy nhiên, validation không thay thế timeout, retry policy hoặc xử lý lỗi nghiệp vụ. Request hiện tại vẫn có thể thất bại và cần được xử lý ở tầng service.

## 6. Vòng đời context với `LdapTemplate`

### 6.1. `LdapTemplate` tự đóng context

Một lợi ích lớn của `LdapTemplate` là quản lý phần plumbing của JNDI:

- Lấy context từ `ContextSource`.
- Thực hiện thao tác LDAP.
- Chuyển đổi `NamingException` sang exception hierarchy của Spring LDAP.
- Đóng context trong `finally`.

Ví dụ:

~~~java
PersonEntry person = ldapTemplate.findByDn(
    dn,
    PersonEntry.class
);
~~~

Caller chỉ nhận object Java. Không cần tự gọi `close()` cho context nội bộ mà `LdapTemplate` đã mượn.

Các overload Search của `LdapTemplate` cũng quản lý vòng lặp `NamingEnumeration` và việc đóng context. Nếu mapper hoặc callback ném exception, cleanup vẫn được thực hiện theo vòng đời của lời gọi.

### 6.2. `executeReadOnly` và `executeReadWrite`

Khi cần thực hiện một hoặc vài thao tác JNDI trên cùng context, có thể dùng:

~~~java
String commonName = ldapTemplate.executeReadOnly(context -> {
    var attributes = context.getAttributes(
        dn,
        new String[] {"cn"}
    );

    var cn = attributes.get("cn");
    return cn == null ? null : String.valueOf(cn.get());
});
~~~

`executeReadOnly` quản lý việc mượn context, chuyển exception và đóng context sau khi callback hoàn tất. `executeReadWrite` làm tương tự với context ghi.

Không dùng `executeReadOnly` như một API Search thay thế. Với Search, dùng các overload `LdapTemplate.search(...)` để framework quản lý `NamingEnumeration` và callback đúng cách.

### 6.3. Tìm kiếm bằng callback vẫn giữ context tới khi callback kết thúc

Ví dụ:

~~~java
ldapTemplate.search(
    "ou=people",
    "(objectClass=inetOrgPerson)",
    controls,
    pair -> {
        // Đọc và map SearchResult.
        // Callback chạy đồng bộ trong quá trình Search.
        processEntry(pair);
    }
);
~~~

Context được giữ trong suốt quá trình Search và callback. Nếu `processEntry` ghi database chậm, gọi HTTP hoặc chờ queue, thời gian giữ context cũng tăng theo.

Với callback xử lý hàng nghìn entry, nên:

1. Chỉ đọc các attribute cần thiết.
2. Map sang DTO độc lập.
3. Ghi batch nhỏ hoặc đưa DTO vào bounded queue.
4. Không truyền `DirContext`, `SearchResult` hoặc `NamingEnumeration` sang thread khác.
5. Theo dõi thời gian Search và thời gian callback riêng biệt.

Nếu queue đầy và callback block để chờ worker, context vẫn đang được giữ. Backpressure bảo vệ bộ nhớ nhưng có thể làm tăng thời gian giữ connection; cần đo và chọn capacity phù hợp.

## 7. Đóng context đúng cách khi dùng JNDI trực tiếp

### 7.1. Mẫu dễ gây leak

~~~java
DirContext context = contextSource.getReadOnlyContext();

Attributes attributes = context.getAttributes(dn);

// Nếu code ném exception hoặc return sớm,
// context có thể không bao giờ được trả về pool.
return attributes;
~~~

Không có cleanup nên context vẫn active. Nếu lặp lại nhiều lần, pool sẽ dần cạn.

### 7.2. Dùng `try/finally`

~~~java
import javax.naming.NamingException;
import javax.naming.directory.DirContext;
import javax.naming.directory.Attributes;

import org.springframework.ldap.core.ContextSource;

public Attributes readAttributes(
        ContextSource contextSource,
        String dn) throws NamingException {

    DirContext context = contextSource.getReadOnlyContext();

    try {
        return context.getAttributes(
            dn,
            new String[] {"cn", "mail"}
        );
    } finally {
        context.close();
    }
}
~~~

Trong môi trường dùng pooled context, `context.close()` trả wrapper về pool. Nếu context được tạo trực tiếp bởi provider, close sẽ đóng context theo semantics của provider.

Spring LDAP cũng có `LdapUtils.closeContext(context)` để đóng context theo cách tiện dụng, đặc biệt khi cần xử lý cleanup nhất quán.

### 7.3. Phải đóng cả `NamingEnumeration`

Một Search JNDI trực tiếp trả về `NamingEnumeration`. Đóng context là cần thiết, nhưng nên đóng enumeration trước:

~~~java
import javax.naming.NamingEnumeration;
import javax.naming.directory.SearchResult;
import javax.naming.directory.SearchControls;
import javax.naming.directory.DirContext;

import org.springframework.ldap.core.ContextSource;
import org.springframework.ldap.support.LdapUtils;

public void rawSearch(ContextSource contextSource)
        throws Exception {

    DirContext context = contextSource.getReadOnlyContext();
    NamingEnumeration<SearchResult> results = null;

    try {
        SearchControls controls = new SearchControls();
        controls.setSearchScope(SearchControls.SUBTREE_SCOPE);
        controls.setReturningAttributes(
            new String[] {"uid", "cn"}
        );

        results = context.search(
            "ou=people",
            "(objectClass=inetOrgPerson)",
            controls
        );

        while (results.hasMore()) {
            SearchResult result = results.next();
            processResult(result);
        }
    } finally {
        try {
            if (results != null) {
                results.close();
            }
        } finally {
            LdapUtils.closeContext(context);
        }
    }
}
~~~

Cấu trúc `finally` lồng nhau bảo đảm context vẫn được đóng nếu việc đóng enumeration gặp lỗi.

Không giữ `NamingEnumeration` để xử lý sau khi method kết thúc. Nó gắn với operation/context đã tạo ra nó.

### 7.4. Không đóng context hai lần theo hai tầng sở hữu

Nếu `LdapTemplate` đã mượn và quản lý context, caller không có trách nhiệm đóng context đó. Nếu caller tự gọi `ContextSource.getReadOnlyContext()`, caller chịu trách nhiệm đóng nó.

Xác định rõ **ai sở hữu context** trước khi thêm cleanup. Đóng context đã được trả về pool hoặc chia sẻ bởi một tầng khác có thể làm thao tác của caller khác thất bại.

## 8. Những mẫu giữ context lâu thường gặp

### 8.1. Gọi dịch vụ ngoài khi đang giữ context

Mẫu nên tránh:

~~~java
ldapTemplate.executeReadOnly(context -> {
    Attributes attrs = context.getAttributes(dn);

    // HTTP request có thể mất vài giây.
    externalApi.send(attrs);

    return null;
});
~~~

Context vẫn active trong lúc chờ HTTP. Nếu nhiều request làm tương tự, pool sẽ cạn dù LDAP server phản hồi rất nhanh.

Tách thành hai bước:

~~~java
PersonSnapshot snapshot = ldapTemplate.lookup(
    dn,
    new String[] {"uid", "cn", "mail"},
    attributes -> mapSnapshot(attributes)
);

// LDAP context đã được đóng trước khi gọi HTTP.
externalApi.send(snapshot);
~~~

DTO/snapshot phải chứa dữ liệu độc lập, không giữ object JNDI.

### 8.2. Ghi database trong callback Search

Nếu callback ghi từng entry vào database, mỗi lần commit có thể giữ context lâu. Có thể gom batch nhỏ hoặc đưa DTO vào bounded queue.

Không dùng queue không giới hạn. Khi downstream chậm, queue sẽ tích lũy dữ liệu và có thể gây OOM; khi queue bounded nhưng đầy, callback block và context vẫn được giữ. Cần cân bằng throughput, memory và thời gian mượn context.

### 8.3. Giữ context trong transaction hoặc workflow dài

Một số luồng cần nhiều thao tác LDAP dùng cùng context, ví dụ paging hoặc một đoạn xử lý cần nhất quán connection. Các helper như `SingleContextSource.doWithSingleContext(...)` có thể giữ context trong phạm vi closure.

Chỉ đặt những thao tác LDAP cần thiết bên trong closure. Không thực hiện các việc sau khi context đang được giữ:

- Chờ người dùng hoặc chờ phê duyệt.
- Gọi HTTP service chậm.
- Sleep/backoff nhiều giây.
- Chờ queue hoặc future không có deadline.
- Chạy xử lý CPU nặng.
- Truyền context sang thread khác.

Một context được giữ qua nhiều page có thể là chủ đích để duy trì paging cookie trên cùng connection. Tuy nhiên, hãy kết thúc vòng lặp paging ngay khi đủ dữ liệu và trả context về pool; đừng giữ context giữa các lần scheduler chạy.

### 8.4. Không giữ context qua `CompletableFuture`

Mẫu rủi ro:

~~~java
DirContext context = contextSource.getReadOnlyContext();

return CompletableFuture.supplyAsync(() -> {
    // Context bị giữ bởi task async.
    return context.getAttributes(dn);
});
~~~

Nếu task bị kẹt hoặc bị hủy mà không cleanup, context có thể không được trả lại. Ngoài ra, context JNDI không nên được chia sẻ giữa các thread.

Hãy hoàn tất thao tác LDAP đồng bộ trong scope có cleanup, chuyển dữ liệu cần thiết sang DTO rồi mới gửi DTO sang executor:

~~~java
PersonSnapshot snapshot = loadSnapshotWithLdapTemplate(dn);

return CompletableFuture.supplyAsync(
    () -> enrichSnapshot(snapshot)
);
~~~

## 9. Tính kích thước pool có cơ sở

### 9.1. Không chọn pool size chỉ theo số thread

Pool cần đủ cho concurrency LDAP thực tế, nhưng không nên lớn hơn khả năng phục vụ của directory. Số thread HTTP hoặc số CPU không trực tiếp cho biết cần bao nhiêu LDAP connection.

Một phép ước lượng ban đầu dựa trên định luật Little:

\[
L = \lambda \times W
\]

Trong đó:

- \(L\): số context active trung bình.
- \(\lambda\): tốc độ thao tác LDAP mỗi giây.
- \(W\): thời gian giữ context trung bình, tính bằng giây.

Ví dụ ứng dụng thực hiện 30 thao tác LDAP/giây và mỗi thao tác giữ context trung bình 150 ms:

\[
L = 30 \times 0.15 = 4.5
\]

Tức khoảng 4,5 context active trung bình. Đây chỉ là mức trung bình, chưa tính burst traffic, p95 latency, retry, paging và read/write distribution. Cần đo peak và thử tải để chọn giới hạn có headroom.

### 9.2. Tính cả số instance ứng dụng

Nếu một instance cho phép tối đa 12 read context và có 5 replica:

~~~text
Tổng khả năng cấp read context = 12 x 5 = 60
~~~

Nếu có thêm pool write, pool theo principal hoặc nhiều directory endpoint, tổng kết nối thực tế có thể cao hơn. So sánh tổng này với giới hạn connection của LDAP server, load balancer và các ứng dụng khác đang dùng directory.

`maxTotal` trong một pool instance không tự giới hạn tổng connection của toàn cụm ứng dụng. Cần tính số replica và mọi pool độc lập.

### 9.3. Tăng pool có thể làm LDAP server chậm hơn

Nhiều connection hơn có thể làm tăng:

- Số bind và TLS session.
- Số Search đồng thời.
- CPU server và tải database backend.
- Lock contention hoặc chi phí index.
- Áp lực lên network và load balancer.

Nếu Search đã chậm do filter không được index hoặc scope quá rộng, tăng pool có thể khiến nhiều Search nặng chạy đồng thời hơn và làm hệ thống tệ hơn.

Hãy tối ưu query và đo server trước khi tăng concurrency.

### 9.4. Phân bổ read và write

Tùy cấu hình, pool có thể quản lý context đọc và ghi theo key riêng. Theo dõi riêng:

- Active read.
- Idle read.
- Active write.
- Idle write.
- Tổng waiter.

Nếu read pool cạn nhưng write pool còn idle, nguyên nhân có thể là read traffic burst hoặc Search dài. Nếu write pool cạn, kiểm tra các thao tác Add/Modify/Delete, retry và transaction scope.

Không cộng các chỉ số read/write một cách tùy tiện nếu API pool đã báo tổng; hãy hiểu key và giới hạn của đúng implementation.

## 10. Timeout: bốn loại thời gian khác nhau

Một hệ thống ổn định cần phân biệt timeout của pool với timeout của network và LDAP operation.

| Timeout | Điều khiển | Khi hết hạn |
| --- | --- | --- |
| Pool borrow timeout (`maxWaitMillis`) | Chờ context được trả lại pool | Không có context được cấp đúng hạn |
| LDAP connect timeout | Thời gian thiết lập TCP/LDAP connection | Kết nối mới thất bại |
| LDAP read/socket timeout | Thời gian chờ dữ liệu từ server | Operation có thể thất bại do server/network chậm |
| LDAP Search time limit | Thời gian server xử lý Search theo SearchControls | Search bị giới hạn thời gian |

`maxWaitMillis=1500` không có nghĩa LDAP Search chỉ chạy tối đa 1,5 giây. Nó chỉ giới hạn thời gian chờ **mượn context** khi pool hết.

JNDI LDAP provider có các environment property như:

~~~text
com.sun.jndi.ldap.connect.timeout
com.sun.jndi.ldap.read.timeout
~~~

Các giá trị này thường được cấu hình bằng millisecond trong environment của LDAP context. Hãy cấu hình theo provider/JDK đang dùng và kiểm tra bằng integration test. Search time limit có thể được đặt qua `SearchControls.setTimeLimit(...)`.

Timeout nên phối hợp với SLA của HTTP request, retry policy và thời gian xử lý của downstream. Không để thread HTTP chờ pool vô hạn rồi lại chờ LDAP socket vô hạn.

## 11. Theo dõi pool bằng metric

### 11.1. Các chỉ số quan trọng

Với `PooledContextSource` dùng Commons Pool 2, API cung cấp các số liệu như:

| Method | Ý nghĩa |
| --- | --- |
| `getNumActive()` | Tổng context đang được mượn |
| `getNumActiveRead()` | Context đọc đang active |
| `getNumActiveWrite()` | Context ghi đang active |
| `getNumIdle()` | Tổng context idle |
| `getNumIdleRead()` | Context đọc idle |
| `getNumIdleWrite()` | Context ghi idle |
| `getNumWaiters()` | Số thread đang chờ mượn context |

Với `PoolingContextSource` dùng Commons Pool 1, các method phổ biến gồm `getNumActive()` và `getNumIdle()`. Không giả định mọi method của pool2 có mặt trong pool1.

### 11.2. Metric nên xuất ra monitoring

Có thể xuất các metric:

- `ldap_pool_active_read`
- `ldap_pool_active_write`
- `ldap_pool_idle_read`
- `ldap_pool_idle_write`
- `ldap_pool_waiters`
- `ldap_pool_borrow_wait_seconds`
- `ldap_context_hold_seconds`
- `ldap_search_duration_seconds`
- `ldap_pool_exhausted_total`
- `ldap_context_validation_failure_total`

Một số metric cần tự instrument ở wrapper/service; không phải tất cả đều có sẵn từ `PooledContextSource`.

Đo cả **borrow wait** và **context hold duration**. Borrow wait tăng cho biết request phải chờ pool; hold duration tăng giúp tìm operation đang giữ context lâu.

### 11.3. Đọc một số mẫu metric

| Active | Idle | Waiters | Diễn giải ban đầu |
| ---: | ---: | ---: | --- |
| 2 | 6 | 0 | Pool còn nhiều context rảnh |
| 8 | 0 | 0 | Pool đang sử dụng hết nhưng chưa có hàng chờ |
| 8 | 0 | 12 | Pool cạn và có 12 thread đang đợi |
| 8 | 0 | 12 kéo dài | Điều tra leak, query chậm hoặc downstream block |
| 3 | 5 | 0 nhưng Search latency cao | Có thể bottleneck ở server/network/query, không phải pool |
| 8 | 0 | 0 sau khi traffic giảm | Kiểm tra active có giảm theo thời gian hay không |

Chụp metric theo thời gian và đối chiếu với request rate, LDAP operation count, thread count và server latency. Một ảnh chụp đơn lẻ không đủ xác định nguyên nhân.

## 12. Quy trình điều tra pool exhaustion

### 12.1. Bước 1: Xác nhận đúng pool và đúng key

Kiểm tra:

- Ứng dụng đang dùng `PoolingContextSource` hay `PooledContextSource`.
- Pool có tách read/write không.
- Có nhiều `ContextSource` hoặc directory endpoint không.
- Có pool riêng theo principal/credential không.
- `maxTotal`, `maxTotalPerKey`, `maxActive` và `maxWait` đang có giá trị nào.
- Số replica ứng dụng và tổng giới hạn connection toàn cụm.

Đừng xem metric của một pool rồi kết luận pool khác cũng đang cạn.

### 12.2. Bước 2: Đo active, idle và waiter

Ghi nhận ít nhất:

~~~text
timestamp
activeRead
activeWrite
idleRead
idleWrite
waiters
borrowWaitMs
ldapOperationDurationMs
requestRate
~~~

Nếu active luôn chạm max, hãy kiểm tra context hold time. Nếu active thấp nhưng request vẫn chậm, điều tra DNS, TLS, network, LDAP server hoặc database backend.

### 12.3. Bước 3: Kiểm tra thread dump

Khi hệ thống đang chậm, lấy thread dump và tìm các thread:

- Đang chờ object từ Commons Pool.
- Đang ở JNDI `DirContext.search`, `lookup` hoặc `modifyAttributes`.
- Đang chạy callback Search.
- Đang block khi ghi database hoặc gọi HTTP.
- Đang chờ queue, semaphore hoặc future.
- Đang chờ lock trong service.

Thread dump giúp phân biệt thread đang chờ **mượn context** với thread đã mượn context nhưng đang giữ nó trong operation chậm.

### 12.4. Bước 4: Tìm code mượn context thủ công

Tìm các lời gọi:

~~~text
getReadOnlyContext()
getReadWriteContext()
getContext(principal, credentials)
~~~

Với mỗi nơi, xác minh:

- Có `try/finally` đóng context không?
- Có đóng `NamingEnumeration` không?
- Có nhánh `return` sớm không?
- Có lưu context vào field hoặc ThreadLocal không?
- Có truyền context qua async boundary không?
- Có gọi external service trong khi đang giữ context không?

Các lời gọi `LdapTemplate` thông thường đã tự quản lý context. Ưu tiên dùng API đó nếu không cần truy cập JNDI cấp thấp.

### 12.5. Bước 5: Tách thời gian LDAP khỏi thời gian downstream

Instrument từng đoạn:

~~~text
pool borrow:        25 ms
LDAP Search:        80 ms
map result:         15 ms
database write:    700 ms
HTTP callback:    1.200 ms
total hold:       2.020 ms
~~~

Trong ví dụ, LDAP chỉ mất 80 ms nhưng context bị giữ hơn 2 giây do công việc downstream. Tối ưu pool size không giải quyết gốc vấn đề; cần rút ngắn thời gian giữ context.

### 12.6. Bước 6: Kiểm tra server và network

Nếu LDAP operation tự nó chậm:

- Kiểm tra CPU, memory, thread và connection count ở LDAP server.
- Kiểm tra Search filter có index phù hợp.
- Thu hẹp base DN và search scope.
- Kiểm tra DNS, TLS handshake và packet retransmission.
- Kiểm tra connection idle bị firewall/load balancer đóng.
- Kiểm tra replication/failover và referral.
- Đối chiếu server-side operation log với client latency.

Đừng tăng pool trong khi server đã quá tải.

## 13. Authentication và giới hạn của connection pooling

### 13.1. Pool phù hợp với credential ổn định

Một pool thông thường giả định các context thuộc cùng loại được tạo với cùng môi trường xác thực. Đây là mô hình phù hợp với service account cố định:

~~~text
app-directory-reader
  ├── read context 1
  ├── read context 2
  └── read context 3
~~~

Pool có thể tái sử dụng các context đã bind bằng cùng identity.

### 13.2. Cẩn thận với `AuthenticationSource` theo user hiện tại

Nếu `ContextSource` lấy principal/credentials từ người dùng hiện tại trong từng request, việc bọc nó bằng pool thông thường có thể không hoạt động như mong muốn.

Pool có thể giữ lại context được tạo bằng credential của request đầu tiên rồi cấp lại cho request khác cùng loại. Khi đó context không còn đại diện cho user hiện tại.

Không dùng chung pool service-account cho các context xác thực cá nhân. Nếu nghiệp vụ cần bind theo từng user, hãy dùng luồng authentication phù hợp và xác định rõ cách quản lý/đóng context riêng; hoặc thiết kế pool phân vùng theo danh tính với kiểm soát bảo mật chặt chẽ.

`ContextSource.getContext(principal, credentials)` là API xác thực theo credential truyền vào; tài liệu Spring LDAP cũng lưu ý luồng này không sử dụng native Java LDAP pooling để thay đổi password có hiệu lực ngay. Không giả định mọi loại context đều được quản lý giống nhau bởi một pool.

### 13.3. Xoay vòng credential

Context đã được tạo có thể vẫn giữ phiên bind cũ. Khi đổi password service account:

1. Cập nhật secret/configuration.
2. Tạo hoặc chuyển sang `ContextSource`/pool mới theo kế hoạch.
3. Ngừng cấp context mới từ pool cũ.
4. Chờ context đang active trả về hoặc áp dụng thời hạn drain.
5. Hủy pool cũ khi không còn borrower.
6. Xác minh pool mới bind thành công.

Không log credential hoặc dump environment của context khi điều tra.

## 14. Native Java pooling và Spring LDAP pooling

JDK LDAP provider có native pooling thông qua environment property và cấu hình hệ thống. Spring LDAP cũng có pool riêng dựa trên Commons Pool.

Spring LDAP khuyến nghị pool của mình khi cần cấu hình chi tiết, validation và quản lý idle context. Native pooling có ít tùy chọn hơn và cấu hình chủ yếu qua system properties.

Không bật đồng thời native pooling và Spring pooling mà không hiểu rõ hai tầng đang quản lý connection nào. Double pooling làm việc quan sát, timeout, validation và giới hạn connection khó dự đoán hơn.

Nếu dùng Spring pool, hãy để `ContextSource` nền tạo context và để pool Spring quản lý vòng đời tái sử dụng.

## 15. Kiểm thử và tái hiện lỗi

### 15.1. Kiểm thử pool có giới hạn

Có thể viết integration test với pool nhỏ, ví dụ hai context. Một thread mượn context và giữ trong thời gian ngắn; thread thứ ba cố mượn sẽ phải chờ hoặc timeout theo cấu hình.

Kỳ vọng:

- Active không vượt giới hạn.
- Waiter tăng khi pool hết.
- Khi context được đóng, waiter có thể tiếp tục.
- Nếu hết `maxWaitMillis`, thao tác borrow thất bại.
- Sau khi mọi context được trả, idle count tăng và active giảm.

Không chạy test cố tình giữ context vô hạn trên LDAP production.

### 15.2. Test đảm bảo context được trả khi exception

Dùng một đoạn code gây lỗi sau khi mượn context:

~~~java
DirContext context = contextSource.getReadOnlyContext();

try {
    throw new IllegalStateException("simulated failure");
} finally {
    context.close();
}
~~~

Sau khi exception được truyền ra, xác minh active count trở về giá trị ban đầu. Trong test thực tế, dùng `try/finally` của production code và assert metric pool thay vì chỉ kiểm tra exception.

### 15.3. Test `LdapTemplate` cleanup

Gọi một thao tác `LdapTemplate` thành công và một thao tác có mapper ném exception. Sau mỗi lời gọi, xác minh context được trả về pool. Điều này giúp phát hiện custom callback hoặc wrapper làm gián đoạn cleanup.

### 15.4. Test context stale

Có thể:

1. Mượn context.
2. Làm connection mất hiệu lực bằng test proxy hoặc restart LDAP test server.
3. Trả context về pool.
4. Mượn lại với validation phù hợp.
5. Xác minh context hỏng bị loại và context mới được tạo.

Kịch bản cần được kiểm soát trong môi trường test. Không tắt network hoặc restart directory dùng chung.

### 15.5. Test callback giữ context lâu

Tạo một callback có delay nhân tạo để mô phỏng downstream chậm. Đo:

- Active count trong lúc callback chạy.
- Waiter count khi có nhiều Search đồng thời.
- Context hold duration.
- Thời gian giải phóng sau khi callback hoàn tất.

Sau đó so sánh với cách callback chỉ map DTO và ghi batch nhanh. Mục tiêu là xác định chi phí thời gian giữ context.

## 16. Runbook xử lý sự cố

Khi ứng dụng báo không mượn được LDAP context:

1. **Xác nhận pool:** loại pool, key, giới hạn active và max wait.
2. **Đọc metric:** active, idle, waiters, borrow wait và context hold duration.
3. **Kiểm tra tải:** request rate, concurrency, retry và số replica.
4. **Lấy thread dump:** phân biệt thread chờ pool với thread đang giữ context.
5. **Kiểm tra lifecycle:** các lời gọi `getReadOnlyContext`/`getReadWriteContext` có cleanup không.
6. **Kiểm tra operation dài:** Search callback, paging, database, HTTP và queue.
7. **Kiểm tra LDAP server:** latency, connection limit, CPU và Search index.
8. **Khôi phục tải:** giảm concurrency hoặc pause job không khẩn cấp nếu server đang quá tải.
9. **Điều chỉnh có kiểm soát:** sửa leak/hold time trước, sau đó mới thử tăng capacity nếu cần.
10. **Theo dõi sau thay đổi:** xác minh active/idle/waiter, latency và server connection count trở về mức ổn định.

Không restart ứng dụng như biện pháp sửa lỗi thường xuyên. Restart chỉ giải phóng các context đang bị giữ trong process; nếu code vẫn leak, pool sẽ cạn lại.

## 17. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách đúng |
| --- | --- | --- |
| Tăng pool ngay khi thấy timeout | LDAP server có thể bị quá tải hơn | Đo active, waiter và hold time trước |
| Không đóng context lấy trực tiếp từ `ContextSource` | Context luôn active và pool cạn dần | Dùng `try/finally` |
| Không đóng `NamingEnumeration` | Giữ tài nguyên Search không cần thiết | Đóng enumeration trước context |
| Giữ `DirContext` trong singleton/ThreadLocal | Context sống lâu và khó thu hồi | Giới hạn scope theo thao tác |
| Chia sẻ context giữa nhiều thread | Hành vi JNDI không an toàn, khó cleanup | Mỗi borrower sở hữu context riêng |
| Gọi HTTP/database trong Search callback | Context bị giữ lâu | Map DTO và tách downstream |
| Dùng queue không giới hạn | Bộ nhớ tăng khi downstream chậm | Bounded queue và backpressure |
| Dùng `maxWait=-1` cho API đồng bộ | Thread có thể chờ vô hạn | Đặt max wait hữu hạn |
| Coi maxIdle là maxActive | Cấu hình không giới hạn concurrency như mong muốn | Hiểu đúng từng thuộc tính |
| Dùng `GROW` để tránh pool exhaustion | Vượt connection budget của server | Giới hạn pool và điều tiết tải |
| Bật validation mọi lúc mà không đo | Tăng chi phí borrow/return | Chọn validation theo lỗi và đo latency |
| Bỏ validation dù server đóng idle connection | Borrow có thể nhận context stale | Dùng testWhileIdle/testOnBorrow phù hợp |
| Dùng pool service account cho user-specific bind | Context có thể mang sai identity | Tách authentication flow |
| Nhầm maxWait với LDAP read timeout | Operation vẫn có thể treo ở tầng socket | Cấu hình từng timeout riêng |
| Coi restart là fix leak | Lỗi quay lại sau khi chạy đủ lâu | Tìm và sửa nơi không trả context |
| Dùng native pool và Spring pool đồng thời không chủ đích | Khó kiểm soát lifecycle và giới hạn | Chọn một chiến lược rõ ràng |

## 18. Checklist trước production

**Cấu hình pool**

- [ ] Chọn đúng implementation: `PoolingContextSource` hoặc `PooledContextSource`.
- [ ] Xác định `maxActive`/`maxTotalPerKey` và `maxTotal`.
- [ ] Đặt `maxWait` hữu hạn phù hợp SLA.
- [ ] Chọn `maxIdle`/`minIdle` theo traffic thực tế.
- [ ] Đặt validation nếu directory/network có thể đóng idle connection.
- [ ] Cấu hình validator dùng base/filter mà bind identity được phép truy cập.
- [ ] Tính tổng connection trên mọi application replica.

**Vòng đời context**

- [ ] Ưu tiên `LdapTemplate` cho thao tác LDAP thông thường.
- [ ] Context lấy trực tiếp từ `ContextSource` luôn được đóng trong `finally`.
- [ ] `NamingEnumeration` được đóng.
- [ ] Không lưu context vào field, cache, session hoặc ThreadLocal.
- [ ] Không chia sẻ context giữa các thread.
- [ ] Paging/single-context scope có thời lượng giới hạn.

**Timeout và quan sát**

- [ ] Pool borrow timeout được phân biệt với connect/read/Search timeout.
- [ ] Có metric active, idle, waiter và borrow wait.
- [ ] Có metric context hold duration và LDAP operation duration.
- [ ] Có dashboard theo read/write và directory endpoint.
- [ ] Có thread dump/runbook khi pool cạn.
- [ ] Có cảnh báo active đạt max và waiter tăng kéo dài.

**Bảo mật và vận hành**

- [ ] Pool dùng credential phù hợp và không trộn user identity.
- [ ] TLS xác minh certificate/hostname.
- [ ] Credential rotation có kế hoạch drain pool.
- [ ] Spring quản lý shutdown/destroy của pool.
- [ ] Không bật native pooling và Spring pooling cùng lúc nếu chưa có thiết kế rõ.

## 19. Câu hỏi tự kiểm tra

1. `ContextSource` và `DirContext` có vai trò gì?
2. Khi dùng pool, `DirContext.close()` có ý nghĩa gì?
3. Phân biệt context active và idle.
4. Pool exhaustion khác context leak như thế nào?
5. Vì sao `active=max` trong một thời điểm chưa đủ kết luận có leak?
6. Dấu hiệu nào cho thấy callback Search giữ context lâu?
7. `LdapTemplate` tự quản lý những phần nào của context lifecycle?
8. Khi nào nên dùng `executeReadOnly` và vì sao không dùng nó thay Search API?
9. Nếu tự gọi `getReadOnlyContext()`, cần cleanup những đối tượng nào?
10. Vì sao phải đóng `NamingEnumeration` trước context?
11. `maxTotalPerKey` khác `maxTotal` như thế nào?
12. `maxWaitMillis` có phải LDAP socket timeout không?
13. Vì sao chờ vô hạn khi pool cạn có thể làm thread HTTP bị giữ?
14. `testOnBorrow` và `testWhileIdle` kiểm tra ở thời điểm nào?
15. `DefaultDirContextValidator` thực hiện loại Search nào?
16. Vì sao validation query phải phù hợp ACL của bind identity?
17. Little's Law giúp ước lượng active context như thế nào?
18. Vì sao cần nhân pool limit với số replica ứng dụng?
19. Khi nào tăng pool có thể làm LDAP server chậm hơn?
20. Vì sao pool service account không phù hợp với `AuthenticationSource` thay đổi theo user?
21. `CommunicationException` ảnh hưởng thế nào tới context đang được pool quản lý?
22. Làm thế nào phân biệt thread đang chờ borrow với thread đang giữ context?
23. Khi nào `SingleContextSource` có thể giữ connection lâu hơn dự kiến?
24. Vì sao không nên gọi HTTP hoặc ghi database chậm bên trong callback Search?
25. Hãy thiết kế một integration test chứng minh context luôn được trả về pool khi callback ném exception.

## 20. Tổng kết

Pool LDAP giúp tái sử dụng `DirContext` và giảm chi phí tạo kết nối. Khi pool cạn, request phải chờ hoặc thất bại theo chính sách exhausted. Nguyên nhân có thể là concurrency cao, Search chậm, callback giữ context lâu, connection stale hoặc context leak.

Để chẩn đoán đúng, cần đọc đồng thời active, idle, waiter, borrow wait và thời gian giữ context. `LdapTemplate` tự quản lý context cho các thao tác thông thường; khi dùng JNDI trực tiếp, caller phải đóng `NamingEnumeration` và `DirContext` trong mọi nhánh. Callback, paging và workflow giữ cùng connection cần có scope ngắn, không thực hiện công việc downstream chậm trong khi đang mượn context.

Cấu hình pool cần giới hạn số context, đặt max wait hữu hạn, chọn validation phù hợp và tính tổng connection qua mọi replica. Tăng pool chỉ hợp lý sau khi đã xác minh LDAP server còn capacity. Với lifecycle rõ ràng, metric đầy đủ và integration test, ứng dụng có thể nhận diện sớm pool exhaustion, tìm ra leak và tránh để các request chờ kết nối vô thời hạn.

### Tài liệu tham khảo

- [Spring LDAP Reference — Pooling Support](https://docs.spring.io/spring-ldap/reference/pooling.html).
- [Spring LDAP API — `PooledContextSource` (Commons Pool 2)](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/pool2/factory/PooledContextSource.html).
- [Spring LDAP API — `PoolConfig`](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/pool2/factory/PoolConfig.html).
- [Spring LDAP API — `DefaultDirContextValidator`](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/pool2/validation/DefaultDirContextValidator.html).
- [Spring LDAP API — `PoolingContextSource` (Commons Pool 1)](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/pool/factory/PoolingContextSource.html).
- [Spring LDAP API — `LdapTemplate`](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/LdapTemplate.html).
- [Spring LDAP API — `ContextSource`](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/ContextSource.html).
- [Spring LDAP Reference — Configuration and Native Java LDAP Pooling](https://docs.spring.io/spring-ldap/reference/configuration.html).
- [Apache Commons Pool 2 — GenericObjectPool Configuration](https://commons.apache.org/proper/commons-pool/apidocs/org/apache/commons/pool2/impl/GenericObjectPoolConfig.html).
- [Java Naming and Directory Interface — Context](https://docs.oracle.com/en/java/javase/21/docs/api/java.naming/javax/naming/Context.html).
