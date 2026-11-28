# Độ trễ replication và đọc lại sau khi ghi

> **Chương:** Đồng thời và nhất quán  
> **Module:** SPRING_DATA_LDAP — truy cập LDAP bằng Spring Data LDAP, ánh xạ entry phân cấp thành đối tượng Java, truy vấn qua `LdapRepository` và thao tác với `LdapTemplate`.

Một ứng dụng có thể gọi `LdapTemplate.modifyAttributes(...)` thành công nhưng ngay sau đó đọc thấy **giá trị cũ**. Một nguyên nhân quan trọng là hệ thống LDAP có nhiều server: thao tác ghi được chấp nhận tại node A, trong khi một request đọc khác được chuyển tới node B chưa nhận hoặc chưa áp dụng bản cập nhật qua **replication**.

Ví dụ:

~~~text
12:00:00.000  LDAP A nhận Modify mail=lan.new@example.org → success
12:00:00.020  API đọc từ LDAP B → mail=lan.old@example.org
12:00:00.180  LDAP B áp dụng thay đổi từ A
12:00:00.220  API đọc từ LDAP B → mail=lan.new@example.org
~~~

Mốc thời gian là **giả định để minh họa**, không phải bảo đảm LDAP replication hoàn thành trong 220 ms. Thời gian thực tế phụ thuộc topology, công nghệ directory, mạng, tải, trạng thái replication, failover và xung đột ghi. Bài học này tập trung vào cách thiết kế **read-after-write** cho ứng dụng Spring Data LDAP, cách phân biệt **replica chậm** với lỗi DN/schema/ACL/cache, cách kiểm thử và vận hành.

## 1. Các khái niệm nền tảng

| Khái niệm | Ý nghĩa | Không được suy ra |
|---|---|---|
| **Write acknowledgement** | LDAP server nhận thao tác đã trả kết quả thành công | Mọi replica đều có dữ liệu mới |
| **Replication** | Cơ chế chuyển/đồng bộ dữ liệu giữa các directory server | Mọi server đều cập nhật tức thời |
| **Replication lag** | Khoảng trễ giữa một thay đổi và việc replica quan sát/áp dụng thay đổi | Có một thời gian chờ cố định cho mọi hệ thống |
| **Stale read** | Phép đọc trả trạng thái cũ hơn thay đổi đã biết | Chắc chắn do replication; có thể do cache hoặc truy vấn sai |
| **Read-after-write** | Đọc được thực hiện sau một lần ghi | Tự nhiên nhận giá trị mới trên bất kỳ node nào |
| **Read-your-writes** | Một phiên làm việc nhìn thấy các thay đổi do chính nó thực hiện | `LdapTemplate` tự bảo đảm xuyên mọi replica |
| **Monotonic reads** | Sau khi đã thấy trạng thái mới, phiên đọc không quay lại trạng thái cũ hơn | Load balancing ngẫu nhiên tự đáp ứng |
| **Eventual consistency** | Các bản sao có thể hội tụ khi hệ thống ổn định và quá trình đồng bộ thành công | Hội tụ trong một SLA cụ thể ngay cả khi replication bị lỗi |

LDAP định nghĩa giao thức Search, Add, Modify, Delete và ModifyDN. **Mô hình replication giữa nhiều server là phần phụ thuộc sản phẩm và cấu hình triển khai**. OpenLDAP, Active Directory và các directory khác không nhất thiết có cùng topology, metadata, conflict resolution hoặc bảo đảm về thứ tự thay đổi.

Trong bài, **writer** nghĩa là endpoint chấp nhận thao tác ghi đang xét; **replica/reader** nghĩa là endpoint có thể chưa quan sát thay đổi đó. Không mặc định mọi directory có mô hình một writer duy nhất: một số hệ thống cho phép nhiều server cùng ghi.

## 2. Một tình huống điển hình với Spring Data LDAP

Entry ban đầu:

~~~ldif
dn: uid=lan,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: lan
cn: Tran Thi Lan
sn: Tran
mail: lan.old@example.org
~~~

API cập nhật email và trả HTTP `204 No Content` sau khi LDAP A trả success. Browser gửi GET ngay sau PUT; backend chọn LDAP B để đọc, và B còn dữ liệu cũ:

~~~mermaid
sequenceDiagram
    autonumber
    participant C as Client
    participant API as Spring Boot API
    participant A as LDAP A / writer
    participant B as LDAP B / replica

    C->>API: PUT /people/lan, email mới
    API->>A: LDAP Modify mail=lan.new@example.org
    A-->>API: success
    API-->>C: 204 No Content
    C->>API: GET /people/lan
    API->>B: LDAP Search / Lookup
    B-->>API: mail=lan.old@example.org
    API-->>C: 200, email cũ
    A-->>B: Replication diễn ra
    C->>API: GET /people/lan sau đó
    API->>B: LDAP Search / Lookup
    B-->>API: mail=lan.new@example.org
    API-->>C: 200, email mới
~~~

**Không có mâu thuẫn bắt buộc giữa hai response:** thao tác Modify đã thành công ở node nhận ghi, còn một node khác chưa có trạng thái mới.

Tuy nhiên, nếu dữ liệu cũ xuất hiện, chưa nên kết luận ngay rằng replication chậm. Có thể request ghi/đọc khác DN, dùng filter sai, projection bỏ trường `mail`, service account không có quyền đọc, hoặc màn hình đang lấy dữ liệu từ application cache.

## 3. Topology quyết định nhiều về độ trễ

Một số mô hình directory phổ biến:

| Topology | Ghi vào đâu? | Đọc từ đâu? | Vấn đề cần chú ý |
|---|---|---|---|
| **Một node** | Một backend | Cùng backend | Không có lag giữa các replica, nhưng vẫn có cache và ghi đồng thời |
| **Một writer, nhiều readers** | A | B/C hoặc A | Stale read trên B/C |
| **Multi-writer** | A hoặc B | A/B/C | Có thể vừa lag vừa có ghi xung đột |
| **LDAP proxy/load balancer** | Qua router | Qua router | Cùng hostname không chứng minh cùng backend |
| **Nhiều site / WAN** | Node theo site | Local node mỗi site | Replication lag, partition, referral và failover phức tạp |

~~~mermaid
flowchart TD
    APP["Spring Boot / Spring Data LDAP"]
    W["LDAP Writer A"]
    LB["Read load balancer"]
    B["LDAP Replica B"]
    C["LDAP Replica C"]

    APP -->|"Modify / Add / Delete"| W
    APP -->|"Search / Lookup"| LB
    W -->|"Replication"| B
    W -->|"Replication"| C
    LB --> B
    LB --> C
~~~

Trong topology này, ngay cả khi Spring Boot có **một** bean `LdapTemplate`, các phép đọc khác nhau cũng có thể tới node khác nhau nếu `ContextSource` dùng nhiều URL hoặc kết nối tới proxy. Pool có thể giữ kết nối với một backend nhưng không tự biến mọi request sau đó thành một session có read-your-writes.

**Những điều phải xác minh trên môi trường triển khai:** server nào cho phép ghi, URL nào đi tới backend nào, có proxy/DNS load balancing hay không, failover hoạt động ra sao và replication path thực sự đi qua những node nào.

## 4. Phân biệt độ trễ replication với các lớp cache

Một request GET có thể đi qua nhiều nơi:

~~~text
HTTP client
  -> Application service / cache
  -> Repository hoặc LdapTemplate
  -> ContextSource / connection pool
  -> DNS / proxy / LDAP endpoint
  -> Directory backend / replication state / ACL
~~~

Các hiện tượng tương tự nhau ở bề mặt API nhưng nguyên nhân khác nhau:

- **Replica lag:** writer đã có dữ liệu mới, reader trực tiếp tại B chưa có.
- **Cache ở ứng dụng:** cả A và B đã mới nhưng API vẫn trả bản cache cũ.
- **Pool hoặc routing:** instance 1 kết nối A, instance 2 kết nối B; một số request vẫn đọc cũ.
- **Search base hoặc scope sai:** entry đã chuyển xuống OU con, còn truy vấn `ONELEVEL` chỉ tìm dưới OU cha.
- **Projection/ACL:** LDAP kết quả không có `mail` dù entry lưu giá trị đó.
- **Concurrent write:** tác nhân khác đã sửa lại `mail` sau thao tác của bạn.
- **Referral và naming context:** request thực tế được thực hiện bởi backend ngoài dự tính.

Để chẩn đoán, cần ghi nhận **DN, thuộc tính, endpoint thật, bind identity, search base, scope, thời điểm và correlation ID** một cách có kiểm soát, tránh log credential hoặc thông tin nhạy cảm.

## 5. LDAP Modify thành công bảo đảm điều gì?

Ví dụ ghi một thuộc tính trên entry:

~~~java
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;

ldapTemplate.modifyAttributes(
        personDn,
        new ModificationItem[] {
            new ModificationItem(
                    DirContext.REPLACE_ATTRIBUTE,
                    new BasicAttribute(
                            "mail", "lan.new@example.org"))
        });
~~~

`personDn` là `Name` tương đối với base của `ContextSource` trong ví dụ này.

Nếu LDAP server trả success và Spring LDAP không ném exception, ta có thể kết luận **node nhận thao tác đã xử lý yêu cầu theo hợp đồng LDAP của nó**. Không nên mặc định kết luận:

1. Mọi replica đã apply Modify.
2. Mọi search qua load balancer có thể thấy giá trị mới.
3. Các cache ứng dụng/Spring Security đã được vô hiệu.
4. Các service account đều có quyền đọc giá trị mới.
5. Không có thao tác ghi khác xảy ra sau đó.
6. Các hệ thống downstream hay group membership đã hội tụ.
7. Kết quả đọc sau này không bao giờ quay lại dữ liệu cũ.

Một LDAP Modify trên **một entry** có tính nguyên tử đối với tập thay đổi trong thao tác theo giao thức, nhưng điều này khác với **replication đồng bộ trên nhiều node**. LDAP không tự cung cấp một transaction chuẩn bao trùm mọi entry, mọi replica và các ứng dụng khác chỉ vì thao tác Modify thành công.

## 6. Chọn consistency contract trước khi viết API

Không phải chức năng nào cũng cần cùng mức nhất quán:

| Nghiệp vụ | Yêu cầu hợp lý | Hướng thiết kế |
|---|---|---|
| Màn hình sửa hồ sơ cá nhân | Sau khi lưu, hiển thị dữ liệu vừa lưu | Read-back tại nguồn ghi hoặc cơ chế read-your-writes được kiểm chứng |
| Báo cáo danh sách nhân viên | Có thể chấp nhận trễ đã thỏa thuận | Đọc replica và quan sát lag |
| Tạo tài khoản rồi cấp quyền | Thường yêu cầu xác minh dữ liệu mới trước bước tiếp | Chọn writer/luồng điều phối và xác nhận rõ |
| Thu hồi quyền khỏi nhóm | Trễ quyền có thể gây rủi ro bảo mật | Chính sách nhất quán và invalidation phù hợp |
| Di chuyển DN/RDN | Các consumer cần thấy vị trí mới đúng lúc | Migration nhiều bước, xử lý tham chiếu, monitoring |
| Đồng bộ dữ liệu nền | Chấp nhận eventual với deadline và reconciliation | Queue/job, bounded polling, retry có chính sách |

Ba khái niệm cần tách biệt:

**Read-your-writes:** sau khi client A sửa dữ liệu, các GET trong cùng flow nhìn thấy thay đổi của A. Có thể đạt được khi đọc từ **writer endpoint đã được kiểm chứng**, nhưng không tự bảo đảm trong multi-writer hay khi có proxy.

**Monotonic reads:** nếu client đã thấy một phiên bản mới, GET tiếp theo không được quay về phiên bản cũ. Truy cập luân phiên qua B và C đang lag khác nhau có thể vi phạm điều này. Muốn bảo đảm cần pin endpoint/source đủ mới hoặc dùng metadata/phiên đọc được thiết kế đúng.

**Eventual reads:** client có thể thấy dữ liệu cũ một thời gian, và ứng dụng công bố rõ hành vi đó. Không hứa thời gian tối đa khi chưa có SLA server và số đo thực tế.

## 7. Ba kiểu đọc lại sau khi ghi

| Cách đọc | Có thể kết luận | Không thể kết luận |
|---|---|---|
| **Đọc từ chính writer A** | A hiện trả giá trị mong đợi | B/C đã hội tụ |
| **Đọc qua URL load-balanced** | Backend được chọn lần đó trả giá trị mong đợi | Toàn bộ readers đồng nhất |
| **Đọc trực tiếp B, C lần lượt** | Các node đã kiểm tra nhìn thấy giá trị tại thời điểm probe | Các node khác hoặc những lần sau luôn giống vậy |

Có một chi tiết quan trọng: **cùng `LdapTemplate` không đồng nghĩa cùng backend**. Nếu URL chỉ tới proxy, `LdapContextSource` có nhiều URL hoặc cơ chế pool/failover thay connection, phép ghi và đọc có thể đi những đường khác nhau.

Khi hệ thống cần read-your-writes, phải dùng **đường đọc được route có chủ đích** tới nguồn đáp ứng yêu cầu. Một hostname tên `ldap-primary.example.org` cũng không đủ bằng chứng nếu thực tế nó là proxy chuyển traffic.

## 8. Cấu hình hai LdapTemplate cho hai vai trò đọc và ghi

Một thiết kế dễ hiểu là cấu hình **hai `ContextSource` tường minh**: writer và replica. Đây không phải cấu hình bắt buộc cho mọi ứng dụng Spring Data LDAP, nhưng làm rõ vai trò của endpoint.

Ví dụ `application.yml`:

~~~yaml
app:
  ldap:
    writer-url: ${LDAP_WRITER_URL}
    replica-url: ${LDAP_REPLICA_URL}
    base: ${LDAP_BASE_DN}
    bind-dn: ${LDAP_BIND_DN}
    bind-password: ${LDAP_BIND_PASSWORD}
~~~

`app.ldap.*` là **khóa riêng do ứng dụng định nghĩa**, không phải thuộc tính Spring Boot tự động tạo hai LDAP template.

~~~java
package org.example.directory;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.core.support.LdapContextSource;

@Configuration(proxyBeanMethods = false)
public class DirectoryTopologyConfig {

    @Bean("writerContextSource")
    public LdapContextSource writerContextSource(
            @Value("${app.ldap.writer-url}") String url,
            @Value("${app.ldap.base}") String base,
            @Value("${app.ldap.bind-dn}") String dn,
            @Value("${app.ldap.bind-password}") String password) {
        return source(url, base, dn, password);
    }

    @Bean("replicaContextSource")
    public LdapContextSource replicaContextSource(
            @Value("${app.ldap.replica-url}") String url,
            @Value("${app.ldap.base}") String base,
            @Value("${app.ldap.bind-dn}") String dn,
            @Value("${app.ldap.bind-password}") String password) {
        return source(url, base, dn, password);
    }

    @Bean("writerLdapTemplate")
    public LdapTemplate writerLdapTemplate(
            @Qualifier("writerContextSource")
            LdapContextSource source) {
        return new LdapTemplate(source);
    }

    @Bean("replicaLdapTemplate")
    public LdapTemplate replicaLdapTemplate(
            @Qualifier("replicaContextSource")
            LdapContextSource source) {
        return new LdapTemplate(source);
    }

    private static LdapContextSource source(
            String url, String base, String dn, String password) {
        LdapContextSource source = new LdapContextSource();
        source.setUrl(url);
        source.setBase(base);
        source.setUserDn(dn);
        source.setPassword(password);
        source.setPooled(false);
        // @Bean lifecycle gọi afterPropertiesSet() cho bean trả về.
        return source;
    }
}
~~~

Điều kiện áp dụng:

- Mỗi URL phải thực sự định vị **node có vai trò phù hợp**; tên thuộc tính không ép LDAP server chấp nhận read/write như mong muốn.
- `source.setPooled(false)` trong ví dụ tắt native JNDI pooling, không phải mọi loại Spring LDAP pooling. Pooling có thể cấu hình riêng; **pool không đảm bảo consistency**.
- Khi có nhiều `ContextSource`, Spring Boot/repository autoconfiguration có thể cần cấu hình bean/repository tường minh, vì chọn bean mặc định có thể trở nên mơ hồ.
- Nếu có nhiều replica cần kiểm tra, phải định nghĩa nhiều endpoint hoặc cơ chế khám phá node chứ không chỉ dùng một `replicaLdapTemplate`.
- LDAP URL production phải dùng LDAPS/StartTLS với kiểm tra chứng chỉ; secret được inject an toàn.
- Nếu reader chỉ cần Search/Read, nên đánh giá **tài khoản dịch vụ ít quyền hơn** thay vì tái sử dụng account writer có quyền sửa dữ liệu.
- Phải kiểm tra rằng proxy, referral hoặc failover không khiến hai source thực tế đi tới cùng hoặc sai backend.

Ví dụ dùng Java 17 và API Spring LDAP tương ứng; việc lựa chọn phiên bản dependencies phải khớp Spring Boot BOM của dự án.

## 9. Service ghi và đọc lại có chủ đích

Ví dụ service thay email nhân viên ở nhánh `ou=people` và cung cấp **hai phép đọc riêng**:

~~~java
package org.example.directory;

import javax.naming.Name;
import javax.naming.directory.Attribute;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;
import org.springframework.stereotype.Service;

@Service
public class PersonMailDirectoryService {

    private final LdapTemplate writer;
    private final LdapTemplate replica;

    public PersonMailDirectoryService(
            @Qualifier("writerLdapTemplate") LdapTemplate writer,
            @Qualifier("replicaLdapTemplate") LdapTemplate replica) {
        this.writer = writer;
        this.replica = replica;
    }

    public void changeMail(String uid, String newMail) {
        if (newMail == null || newMail.isBlank()) {
            throw new IllegalArgumentException("Invalid email");
        }

        writer.modifyAttributes(
                personDn(uid),
                new ModificationItem[] {
                    new ModificationItem(
                            DirContext.REPLACE_ATTRIBUTE,
                            new BasicAttribute("mail", newMail))
                });
    }

    public String mailFromWriter(String uid) {
        return readMail(writer, uid);
    }

    public String mailFromReplica(String uid) {
        return readMail(replica, uid);
    }

    private static String readMail(LdapTemplate template, String uid) {
        return template.lookup(
                personDn(uid),
                (AttributesMapper<String>) attrs -> {
                    Attribute attr = attrs.get("mail");
                    if (attr == null || attr.size() == 0) {
                        return null;
                    }
                    if (attr.size() != 1) {
                        throw new IllegalStateException(
                                "Ambiguous LDAP mail values");
                    }
                    Object value = attr.get();
                    if (!(value instanceof String text)) {
                        throw new IllegalStateException(
                                "Expected LDAP String for mail");
                    }
                    return text;
                });
    }

    private static Name personDn(String uid) {
        if (uid == null
                || !uid.matches("[A-Za-z0-9._-]{1,64}")) {
            throw new IllegalArgumentException("Invalid uid");
        }
        return LdapNameBuilder.newInstance("ou=people")
                .add("uid", uid)
                .build();
    }
}
~~~

Với `spring.ldap.base` hoặc `app.ldap.base=dc=example,dc=org`, `personDn("lan")` là DN **tương đối** `uid=lan,ou=people`. Đừng gửi full DN có cả hậu tố base vào một `LdapTemplate` đang yêu cầu tên tương đối với base.

`mail` là thuộc tính tùy chọn theo schema `inetOrgPerson`. Mapper trả `null` nếu thuộc tính vắng mặt trong kết quả, nhưng **null không chứng minh replication chậm**: còn có ACL/projection hoặc entry chưa từng có email. Code ví dụ giới hạn một giá trị `mail` theo hợp đồng API; với thuộc tính đa trị cần dùng `getAll()`.

Thử luồng:

~~~java
service.changeMail("lan", "lan.new@example.org");

String writerValue = service.mailFromWriter("lan");
String replicaValue = service.mailFromReplica("lan");

// Writer có thể đã mới; replica có thể vẫn cũ.
// Nếu replication rất nhanh, cả hai có thể cùng là giá trị mới.
~~~

Không nên tạo một bài test **bắt buộc** quan sát được stale read trong lần thử đầu tiên. Nếu muốn mô phỏng nhánh stale để kiểm thử thuật toán retry, dùng fake service hoặc môi trường có thể điều khiển replication lag.

## 10. Đọc lại từ writer: khi nào đủ, khi nào chưa?

Đọc lại từ **endpoint thực sự đã nhận ghi** có thể hỗ trợ UX “lưu xong hiển thị thông tin mới”:

~~~mermaid
sequenceDiagram
    participant UI as UI
    participant API as API
    participant W as LDAP Writer
    participant R as LDAP Reader

    UI->>API: PUT email mới
    API->>W: Modify
    W-->>API: success
    API->>W: Lookup cùng DN
    W-->>API: email mới
    API-->>UI: Trả dữ liệu đã kiểm chứng trên writer
    Note over R: Replica có thể chưa đồng bộ
~~~

Nó **không** chứng minh reader B đã thấy dữ liệu mới. Cũng không ngăn client khác thay đổi entry ngay sau khi writer trả success. Nếu API đọc lại thấy giá trị khác, có thể đã có concurrent write, không thể tự kết luận thao tác Modify trước đó bị rollback.

Nếu writer không thể được truy cập sau khi Modify thành công, hệ thống có thể rơi vào **unknown outcome cho bước readback**. Cần tách lỗi xác minh khỏi lỗi thực hiện ghi; không báo sai “ghi thất bại” rồi để client tự động thực hiện lại thao tác có side effect.

## 11. Chờ replica hội tụ bằng bounded polling

Nếu một workflow cần xác nhận một replica cụ thể đã nhìn thấy giá trị mới, có thể dùng **đọc lặp với thời gian chờ hữu hạn**. Đoạn sau minh họa cho integration test hoặc job điều phối, không phù hợp để chặn request HTTP dài trên tải lớn:

~~~java
import java.time.Duration;

public final class ReplicaConvergenceProbe {

    private ReplicaConvergenceProbe() {
    }

    public static void awaitMail(
            PersonMailDirectoryService service,
            String uid,
            String expected,
            Duration timeout) throws InterruptedException {

        long deadline = System.nanoTime() + timeout.toNanos();

        while (true) {
            String actual = service.mailFromReplica(uid);

            if (expected.equals(actual)) {
                return;
            }

            if (System.nanoTime() >= deadline) {
                throw new AssertionError(
                        "Replica did not show expected value in time");
            }

            Thread.sleep(100L);
        }
    }
}
~~~

Sử dụng trong một test đã chuẩn bị sẵn entry:

~~~java
service.changeMail("lan-test", "lan.test2@example.org");
ReplicaConvergenceProbe.awaitMail(
        service, "lan-test", "lan.test2@example.org",
        Duration.ofSeconds(10));
~~~

**`10 giây` chỉ là tham số minh họa, không phải một SLA của LDAP.** Cần đo thực tế theo directory server và môi trường triển khai để chọn deadline, đồng thời thiết lập connection/read timeout riêng.

Giới hạn của code:

1. Đợi tới khi **quan sát** đúng giá trị. Nếu request khác đã thay email lần nữa, probe có thể không nhìn thấy giá trị trung gian; cần chiến lược version hoặc coordination riêng.
2. Lỗi network, ACL, TLS hoặc sai base DN vẫn ném exception, **không bị coi là replication lag**.
3. Trong ví dụ Modify của một entry vốn đã có, kết quả không tìm thấy DN có thể do lỗi truy vấn/di chuyển entry hoặc replication rất bất thường; cần phân loại, không tự bỏ qua.
4. `Thread.sleep` chiếm thread. Trong production có nhiều client, nên dùng background job, scheduler hoặc cơ chế async có deadline.
5. Poll quá dày gây tải LDAP; dùng **backoff và jitter** nếu hoạt động trên quy mô lớn.

Timeout chỉ nghĩa là **chưa quan sát dữ liệu mong muốn trước deadline**, không đủ để kết luận write thất bại hoặc replication sẽ không bao giờ hoàn thành.

## 12. Backoff, timeout và retry có kỷ luật

Khi có hàng nghìn request vừa ghi, việc cùng poll mỗi 100 ms có thể tăng tải reader và làm hệ thống tệ hơn. Một lịch kiểm tra tham khảo:

~~~text
Lần 1: sau khoảng 100 ms
Lần 2: sau khoảng 200 ms
Lần 3: sau khoảng 400 ms
Lần 4: sau khoảng 800 ms
... trần và tổng deadline do ứng dụng quyết định
~~~

Thêm jitter để nhiều client không cùng thực hiện request một thời điểm. Đừng dùng các con số đó làm quy tắc áp dụng cứng; tính năng delay thực tế cần đo lag, tải và yêu cầu người dùng.

**Retry đọc** nhằm quan sát convergence khác với **retry ghi**. Khi Modify mất kết nối sau khi gửi, ta có thể không biết server đã thực hiện hay chưa. Nếu tự động retry thao tác ghi:

- Với `REPLACE_ATTRIBUTE` cùng giá trị và không có tác nhân khác, hiệu quả có thể gần idempotent.
- Với `ADD_ATTRIBUTE` một giá trị đã tồn tại, server có thể trả `attributeOrValueExists (20)`.
- Với `REMOVE_ATTRIBUTE` một giá trị đã bị xóa, server có thể trả `noSuchAttribute (16)`.
- Với `Add` entry mới, retry có thể gặp `entryAlreadyExists (68)`.
- Với `ModifyDN`, nguồn/đích có thể thay đổi giữa hai lần thử.

Do đó, phải đối soát trạng thái hiện tại và xác định semantics nghiệp vụ trước khi retry ghi. **Đọc từ replica còn lag không phải nơi đáng tin cậy để quyết định một thao tác ghi trước đó đã thành công hay chưa**.

## 13. Add, Modify, Delete, Rename: mỗi thao tác có kiểu stale khác nhau

| Thao tác | Replica chậm có thể trả | Hậu quả |
|---|---|---|
| **Add entry** | DN mới chưa tồn tại | Client tưởng chưa tạo, thử Add lần nữa |
| **Modify attribute** | Giá trị cũ | UI hoặc workflow dùng dữ liệu cũ |
| **Delete entry** | Entry vừa xóa vẫn xuất hiện | UI tưởng xóa thất bại; quyền cũ có thể bị quan sát |
| **ModifyDN/rename** | DN cũ còn, DN mới chưa có | Lookup sai và tham chiếu DN chưa cập nhật |
| **Thêm `member` vào group** | Nhóm chưa có member mới | Quyền chưa được thấy trong group search |
| **Xóa `member` khỏi group** | Member cũ còn tồn tại trong kết quả | Có thể ảnh hưởng thu hồi quyền |
| **Đổi password** | Xác thực qua node khác có thể khác trạng thái | Rủi ro đăng nhập trong lúc replication |

Với việc thay đổi mật khẩu hoặc thuộc tính bảo mật, **không kiểm tra bằng cách đọc `userPassword`**, vì có thể bị ẩn/mã hóa và gây rò rỉ credential. Kiểm thử xác thực phải dùng tài khoản test, cơ chế TLS và giới hạn số lần thử để tránh khóa tài khoản.

Đối với `groupOfNames.member`, LDAP có thể dùng DN của user làm giá trị; nếu user đồng thời được rename sang OU mới, replication lag và tham chiếu DN còn cũ là **hai vấn đề riêng**. Không giả định directory tự cập nhật mọi DN tham chiếu sau ModifyDN.

## 14. Ghi đồng thời khác với replication lag

Hai client cùng cập nhật một thuộc tính:

~~~text
T0: Client A đọc mail=old@example.org
T1: Client B đọc mail=old@example.org
T2: Client A Modify mail=a@example.org -> success
T3: Client B Modify mail=b@example.org -> success
T4: Client A đọc lại writer -> mail=b@example.org
~~~

Ở T4, kết quả khác mong đợi có thể do **một lần ghi mới hơn**, không phải do A bị từ chối hay replica chậm. Readback giúp **phát hiện khác biệt**, không **ngăn** mất cập nhật (*lost update*).

Các giải pháp tùy yêu cầu:

- Dùng `ModificationItem` sửa đúng thuộc tính, tránh `repository.save(...)` trên entity chỉ tải một phần làm mất thuộc tính khác.
- Nếu cần optimistic concurrency thật, xem xét LDAP **Assertion Control** (RFC 4528) hoặc cơ chế compare-and-swap do server hỗ trợ. Phải áp điều kiện **trong cùng thao tác ghi**.
- Nếu nhiều writer cùng sửa một entry, có thể cần điều phối theo identity hoặc conflict resolution phù hợp.
- Một chuỗi “đọc version → so trong Java → Modify” không nguyên tử vì có khoảng trống giữa phép đọc và phép ghi.

Operational attributes như `modifyTimestamp`, `entryCSN` hoặc metadata USN có thể hữu ích, nhưng không mặc nhiên là **version token toàn cục** dùng được cho mọi server/replica. Cần xác minh ngữ nghĩa, phạm vi, độ phân giải và khả năng dùng cho điều kiện ghi tại server.

## 15. Spring Data LDAP Repository có tự bảo đảm read-your-writes không?

Một repository:

~~~java
import java.util.List;
import org.springframework.data.ldap.repository.LdapRepository;

public interface DirectoryPersonRepository
        extends LdapRepository<DirectoryPerson> {

    List<DirectoryPerson> findByUid(String uid);
}
~~~

có thể tạo/đọc entity theo mapping ODM `@Entry`. Nhưng sau:

~~~java
repository.save(person);
List<DirectoryPerson> found = repository.findByUid(uid);
~~~

không thể kết luận result chắc chắn mới nhất trên mọi replica. Repository vẫn dùng **`ContextSource` và LDAP endpoint được cấu hình**. Nếu traffic được chuyển qua proxy/replicas, nguyên tắc read-after-write không tự thay đổi.

Cũng cần lưu ý `save(...)` là thao tác theo semantics ODM cụ thể; việc field Java `null` hoặc collection chưa tải có làm thay đổi dữ liệu server hay không phải được kiểm thử riêng. Một kết quả cũ có thể do replication, nhưng cũng có thể do entity mapping, projection, schema hoặc cache.

Trong dự án nhiều `ContextSource`, không để repository chọn mặc định một source không như dự kiến; cần cấu hình rõ bean/template theo khả năng của phiên bản Spring Data LDAP.

## 16. Cache quyền và Spring Security LDAP

Cập nhật group trên LDAP writer có thể **chưa xuất hiện ngay** trong tìm kiếm nhóm qua reader:

~~~text
Admin xóa member=uid=lan,... khỏi cn=developers ở writer
        ↓
Replica B vẫn có member cũ
        ↓
Spring Security LDAP đọc nhóm từ B
        ↓
Người dùng có thể còn được gán quyền theo group cũ
~~~

Còn một lớp khác: session/JWT/authorization cache của ứng dụng có thể giữ authorities trước khi group được cập nhật, dù LDAP replicas đã hội tụ.

Đối với **cấp quyền**, lag tạo cảm giác quyền chưa có hiệu lực. Đối với **thu hồi quyền**, nó có thể là vấn đề bảo mật nghiêm trọng, vì quyền cũ còn được sử dụng một thời gian.

Cần định nghĩa:

1. Nguồn sự thật về quyền và cách tính authorities.
2. Chính sách xác minh cập nhật nhóm, có thể đọc writer khi cần.
3. Cơ chế refresh/invalidation cho session, token hoặc authorization cache.
4. Giới hạn thời gian thu hồi quyền mà nghiệp vụ cho phép.
5. Cách kiểm thử với cả LDAP group state và HTTP access control.

Không coi “replication đã xong” đồng nghĩa “mọi phiên đăng nhập đã được cập nhật quyền”.

## 17. Chẩn đoán: lag, ACL, base DN hay cache?

| Triệu chứng | Giả thuyết | Phép kiểm tra phù hợp |
|---|---|---|
| Writer mới, replica B cũ | Replication lag | Đọc trực tiếp từng endpoint; xem replication status |
| Writer và B đều cũ sau success | Sai entry/attribute hoặc có write khác | Đối chiếu DN, log thao tác, concurrency |
| `mail` không được trả | ACL hoặc projection | Yêu cầu rõ attribute; kiểm tra bind identity |
| GET từ một pod cũ, pod khác mới | Cache/pool/config URL khác | Kiểm tra từng instance, revision, connection routing |
| B đã mới nhưng browser vẫn cũ | Application/UI cache | Kiểm tra TTL, cache invalidation, client cache |
| DN cũ vẫn có trên B sau rename | Replication chưa áp dụng ModifyDN | Đọc writer và B; kiểm tra DN mới/cũ |
| Query `ONELEVEL` không thấy OU con | Scope sai | Xác minh `ONELEVEL`/`SUBTREE`, base |
| Một replica không nhận update lâu | Replication backlog/partition | Kiểm tra monitor server/network |
| `insufficientAccessRights (50)` | ACL thiếu | Điều tra quyền, không retry như lag |
| `invalidCredentials (49)` | Secret hoặc bind sai | Kiểm tra rotation/credential, không thử ồ ạt |
| `unavailable (52)` / timeout | Server/network không khả dụng | Timeout/failover/recovery riêng |
| Đọc mới rồi lại đọc cũ | Routing giữa replicas khác lag | Pin nguồn đọc/định nghĩa monotonic read policy |

Một phép so sánh đáng tin cậy phải dùng **cùng bind identity, base, scope, filter và projection**, chỉ thay endpoint cần khảo sát. Nếu thay đổi tài khoản hoặc quyền đọc, kết quả không còn so sánh trực tiếp được.

## 18. Giám sát replication lag bằng chỉ số quan sát

Ứng dụng có thể định nghĩa:

~~~text
t_write_ack    = thời điểm LDAP writer trả success
t_replica_seen = lần đầu probe B thấy giá trị/version kỳ vọng

observed_visibility_delay = t_replica_seen - t_write_ack
~~~

Chỉ số này là **độ trễ hiển thị quan sát được**, không nhất thiết là thời điểm server đã apply replication: nếu poll mỗi 500 ms, dữ liệu có thể đã được cập nhật trước khi probe thấy. Kết quả còn chịu ảnh hưởng network, scheduling, cache và định tuyến.

Các chỉ số nên theo dõi:

| Tín hiệu | Ý nghĩa |
|---|---|
| Write success/error của từng node | Xác nhận nguồn ghi và trạng thái thao tác |
| Visibility delay theo replica | Thời gian thấy kết quả mới tại endpoint cụ thể |
| Số probe vượt deadline | Phát hiện lag kéo dài |
| Search/Modify latency, timeout | Phân biệt query chậm với replication |
| Connection pool active/idle/wait | Phát hiện nghẽn tài nguyên |
| Replication backlog/queue/errors | Kiểm tra ở phía directory server |
| Số lần trả stale result | Tần suất chưa hội tụ theo phép đo |
| Số conflict trong multi-writer | Bất đồng do các ghi cạnh tranh |
| Lỗi ACL, bind, schema và cache | Phân biệt nguyên nhân với replication lag |

Tên metric do ứng dụng tự đặt; **đừng giả định Spring LDAP tự cung cấp tất cả metrics này**.

Một số directory có operational metadata như `entryCSN`/`contextCSN` của OpenLDAP hoặc USN theo domain controller trong Active Directory. **Không so sánh mù các giá trị metadata khác hệ thống hoặc coi `modifyTimestamp` là global version.** Cần tra tài liệu của server, cách nó ghi nhận replication và ACL cho operational attributes.

## 19. Kiểm thử có ý nghĩa cho replication

Unit test Java không chứng minh được thời gian replication thật. Nên có ba lớp:

| Nhóm test | Mục tiêu | Hạ tầng |
|---|---|---|
| **Unit test** | Retry/backoff/deadline, phân loại lỗi, chọn endpoint | Fake service/mock writer/reader |
| **Single-directory integration test** | Modify đúng DN, schema, ACL và mapper | Một LDAP server test |
| **Replication integration test** | Read-after-write khác node, hội tụ và timeout | **Ít nhất hai LDAP endpoints có replication thực** |

Một quy trình test:

1. Dựng LDAP test có writer A và replica B, kiểm tra chúng thật sự là hai backend.
2. Nạp một entry `inetOrgPerson` đủ `cn`, `sn` dưới `ou=people`.
3. Chờ fixture ban đầu đã nhìn thấy ở B trước khi test sửa thuộc tính.
4. Gọi Modify ở A với `mail` mới **độc nhất cho test run**.
5. Đọc từ A, kiểm tra đã thấy dữ liệu kỳ vọng.
6. Đọc ngay từ B, ghi nhận giá trị cũ **hoặc** mới đều có thể xảy ra.
7. Dùng bounded polling để xác minh B hội tụ trong deadline của test.
8. Đánh giá trường hợp B bị partition hoặc replication bị dừng có kiểm soát; probe phải timeout có chủ đích.
9. Kiểm tra Create/Delete/ModifyDN và group membership nếu nghiệp vụ sử dụng.
10. Dọn fixture và kiểm tra test lặp lại độc lập.

Ví dụ integration test dựa trên service mục 9:

~~~java
import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest
@ActiveProfiles("test")
class ReplicaVisibilityIntegrationTest {

    @Autowired
    private PersonMailDirectoryService service;

    @Test
    void mailEventuallyAppearsOnReplica()
            throws InterruptedException {

        String uid = "replica-fixture";
        String email = "replica-v2@example.org";

        // Tiền điều kiện: fixture tồn tại ở A và B,
        // replication đã cấu hình và ổn định.
        service.changeMail(uid, email);

        assertEquals(email, service.mailFromWriter(uid));

        ReplicaConvergenceProbe.awaitMail(
                service, uid, email, Duration.ofSeconds(10));

        assertEquals(email, service.mailFromReplica(uid));
    }
}
~~~

Đây là test minh họa: phải có environment/credential test, fixture và hai endpoint thực tế. `Duration.ofSeconds(10)` không phải SLA. Nếu LDAP server đồng bộ tức thì trong tình huống thử, test vẫn hợp lệ: nó kiểm tra **eventual visibility**, không bắt buộc phải quan sát một stale read.

Muốn kiểm tra nhánh “hai lần cũ rồi một lần mới” một cách xác định, tạo fake reader có kết quả lập trình sẵn ở unit test. Muốn đo replication lag thật, dùng multi-node test environment.

## 20. Kiểm tra thủ công từng endpoint bằng ldapsearch

Dùng cùng bind DN và DN entry để đối chiếu:

~~~bash
ldapsearch -LLL -x \
  -H ldaps://ldap-writer.example.org:636 \
  -D "uid=svc-directory,ou=services,dc=example,dc=org" \
  -W \
  -b "uid=lan,ou=people,dc=example,dc=org" \
  -s base "(objectClass=*)" dn mail modifyTimestamp
~~~

Tại replica B:

~~~bash
ldapsearch -LLL -x \
  -H ldaps://ldap-reader-b.example.org:636 \
  -D "uid=svc-directory,ou=services,dc=example,dc=org" \
  -W \
  -b "uid=lan,ou=people,dc=example,dc=org" \
  -s base "(objectClass=*)" dn mail modifyTimestamp
~~~

`-W` yêu cầu nhập password, tránh để mật khẩu xuất hiện trong command line hoặc lịch sử shell. `modifyTimestamp` có thể là operational attribute không được trả mặc định hoặc bị ACL che. Hai lệnh phải kết nối **đúng hai backend**; nếu cùng qua một load balancer, kết quả so sánh có thể không có ý nghĩa.

Nếu cả A và B đều trả khác dữ liệu trong ứng dụng, kiểm tra application cache, credential, base DN và projection trước khi kết luận có vấn đề với replica. Nếu kết quả giữa A/B khác nhau, tiếp tục xem trạng thái replication trên server.

## 21. Runbook khi hệ thống trả dữ liệu cũ

**Trước rollout đọc qua replica:**

- Kiểm kê writer, reader, proxy, connection pool, schema và replication path.
- Xác định nghiệp vụ nào cần read-your-writes, nghiệp vụ nào chấp nhận eventual.
- Kiểm tra reader ACL, search base, scope và tính nhất quán schema.
- Đo baseline visibility delay bằng entry test, không dùng dữ liệu nhạy cảm production.
- Định nghĩa timeout, backoff, chính sách failover và ngưỡng dừng traffic reader.
- Kiểm tra ảnh hưởng tới Spring Security LDAP và authorization/session cache.

**Khi nhận báo cáo GET trả cũ sau PUT:**

1. Xác nhận thao tác ghi thực sự trả success hay kết quả chưa biết do timeout.
2. Đọc từ writer endpoint và ghi nhận trạng thái hiện tại.
3. Đọc trực tiếp reader nghi vấn bằng cùng bind identity và filter.
4. Kiểm tra cache, pool, cấu hình từng instance và load balancer.
5. Kiểm tra DN, base, scope, schema, ACL và các ghi cạnh tranh.
6. Kiểm tra replication queue, network và lỗi server.
7. Nếu chưa hội tụ và đang trong deadline đã thỏa thuận, thử đọc có giới hạn.
8. Nếu lag vượt ngưỡng, tạm ngừng đường đọc bị ảnh hưởng hoặc chuyển read cần nhất quán về writer nếu được phép.
9. Không tự retry thao tác ghi có side effect khi chưa xác định kết quả.
10. Nếu ảnh hưởng tới thu hồi quyền, kích hoạt quy trình bảo mật và refresh quyền ngoài replication.

**Khi replica bị partition kéo dài:** không chờ vô hạn hoặc tăng polling vô tội vạ. Ưu tiên bảo vệ directory writer khỏi bị quá tải, hạn chế reader không khỏe và thông báo đúng mức độ nhất quán của dữ liệu trả về.

## 22. Những lỗi tư duy phổ biến

- **“Modify thành công nghĩa là tất cả replicas đã cập nhật.”** Không; chỉ có kết quả của node nhận thao tác được xác minh.
- **“Cùng `LdapTemplate` là cùng backend.”** Không nếu `ContextSource`/proxy có nhiều đường đi.
- **“Cùng một URL sẽ luôn vào cùng LDAP server.”** Không nếu URL đứng trước load balancer.
- **“Không tìm thấy attribute nghĩa là replica lag.”** Có thể do projection, ACL hoặc schema.
- **“Đợi một giây là đủ cho mọi replication.”** Không có SLA chung; phải đo và theo dõi.
- **“Đọc writer sau ghi chứng minh replicas đã hội tụ.”** Không.
- **“Đọc lại giải quyết lost update.”** Không; cần conditional write/coordinator riêng.
- **“`modifyTimestamp` là số version dùng ở tất cả directory.”** Không; metadata có giới hạn riêng.
- **“Replica đã cập nhật group thì mọi token đã có quyền mới.”** Không; authorization có thể cache riêng.
- **“Retry ghi sau timeout luôn an toàn.”** Không; kết quả thao tác có thể chưa biết.
- **“Một server LDAP test đủ kiểm thử replication.”** Không; cần nhiều endpoint hoặc mô phỏng lag cho logic retry.
- **“Lag và timeout LDAP là một lỗi.”** Không; timeout network và trạng thái replica chưa hội tụ cần chẩn đoán khác nhau.

## 23. Bài tập thực hành

**Bối cảnh:** ứng dụng Spring Boot dùng SPRING_DATA_LDAP cập nhật `mail` của người dùng dưới `ou=people`. Hệ thống có writer A và replica B. Người dùng đôi khi thấy email cũ sau khi lưu.

Thực hiện trên **directory test độc lập**:

1. Vẽ topology từ API tới writer, reader, proxy, `ContextSource` và pool.
2. Chuẩn bị hai LDAP endpoints có replication, xác minh URL thực sự đi tới các node khác nhau.
3. Tạo entry `inetOrgPerson` hợp lệ, đợi entry ban đầu xuất hiện trên cả A và B.
4. Cấu hình hai `LdapTemplate` tách biệt; sử dụng `@Qualifier` để chọn đúng template.
5. Dùng `modifyAttributes(...)` thay `mail` tại A.
6. Đọc lại từ A và B, ghi nhận giá trị và thời điểm mà không giả định B luôn chậm.
7. Triển khai bounded retry cho B, có deadline và phân biệt lỗi kết nối/ACL với stale value.
8. Thử mô phỏng B chậm hoặc partition; xác nhận thuật toán dừng sau deadline.
9. Dùng fake reader ở unit test trả giá trị cũ rồi mới; kiểm tra backoff không làm lặp vô hạn.
10. Giải thích vì sao có thể xảy ra read-your-writes từ A nhưng không có monotonic reads qua B/C.
11. Mô phỏng hai client thay email cạnh tranh và đề xuất phương án tránh lost update.
12. Thêm/xóa một giá trị `member` của group trong test, theo dõi hiện tượng role chưa đổi do replica hoặc cache.
13. Đề xuất HTTP contract cho màn hình sửa hồ sơ và cho API báo cáo eventual.
14. Định nghĩa metric quan sát lag, tần suất lỗi, timeout và ngưỡng chuyển đọc về writer.
15. Viết runbook cho sự cố “PUT thành công, GET trả dữ liệu cũ” mà không log credential hoặc thông tin cá nhân.

**Tiêu chí hoàn thành:** người học xác định được nơi ghi/nơi đọc, hiểu success không đồng nghĩa replication tức thời, biết cách read-back đúng nguồn và timeout có giới hạn, phân biệt lag với lỗi mapping/ACL/cache và có test đa node.

## 24. Tổng kết và tài liệu tham khảo

**Trong Spring Data LDAP, kết quả ghi thành công trên node A và khả năng đọc được dữ liệu mới từ replica B là hai sự kiện khác nhau.** `LdapRepository` và `LdapTemplate` dùng `ContextSource` do ứng dụng cấu hình; chúng không tự tạo bảo đảm replication đồng bộ.

Một mô hình tư duy đơn giản:

~~~text
WRITE thành công tại LDAP A
        |
        +--> READ A: xác minh giá trị tại nguồn ghi
        |
        +--> READ B: có thể còn dữ liệu cũ
                    |
                    +--> Replication hoàn tất theo topology thực tế
                    |
                    +--> READ B: quan sát dữ liệu mới
~~~

Nếu nghiệp vụ yêu cầu **read-your-writes**, cần đọc từ nguồn đủ mới hoặc sử dụng cơ chế consistency đã được chứng minh. Nếu chấp nhận **eventual consistency**, hãy thiết kế API contract rõ, đo visibility delay, dùng bounded retry có deadline và phân biệt replication lag với ACL/cache/network/concurrent write. Với nhóm và quyền truy cập, phải xét cả replication **và** cache bảo mật.

Tài liệu tham khảo:

- [Spring Data LDAP Reference](https://docs.spring.io/spring-data/ldap/reference/): ODM, repository, LDAP operations.
- [Spring LDAP Reference](https://docs.spring.io/spring-ldap/reference/): `LdapTemplate`, `ContextSource`, lookup/search/modify, pooling và cấu hình.
- [Spring Security — LDAP Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/ldap.html): LDAP bind, group search và authority mapping.
- [RFC 4511 — Lightweight Directory Access Protocol](https://www.rfc-editor.org/rfc/rfc4511): Search, Modify, Add, Delete, ModifyDN và LDAP result codes.
- [RFC 4512 — Directory Information Models](https://www.rfc-editor.org/rfc/rfc4512): DN, DIT, schema, operational attributes.
- [RFC 4528 — LDAP Assertion Control](https://www.rfc-editor.org/rfc/rfc4528): điều kiện server-side nếu server/client hỗ trợ.
- [OpenLDAP Administrator's Guide — Replication](https://openldap.org/doc/admin26/replication.html): mô hình syncrepl và các metadata replication của OpenLDAP.
- [Microsoft Learn — Active Directory Replication Concepts](https://learn.microsoft.com/en-us/windows-server/identity/ad-ds/get-started/replication/active-directory-replication-concepts): replication trong Active Directory.
