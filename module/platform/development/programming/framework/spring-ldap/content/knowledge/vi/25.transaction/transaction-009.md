# Kiểm thử lỗi giữa chuỗi bind, modify và delete trong Spring LDAP

Một quy trình làm việc với thư mục LDAP đôi khi gồm nhiều thao tác liên tiếp: tạo một entry, cập nhật thuộc tính, rồi xóa entry hoặc tài nguyên tạm. Nếu một thao tác ở giữa thất bại, liệu các thay đổi trước đó có tự quay về trạng thái ban đầu? Trong **Spring LDAP**, câu trả lời mặc định là **không**. Mỗi yêu cầu LDAP có kết quả riêng; một chuỗi lời gọi `LdapTemplate` thông thường không tự trở thành transaction nguyên tử trên toàn bộ chuỗi.

Ví dụ, ứng dụng thử tạo tài khoản tạm `uid=tx-demo-01`, đổi `description` từ `created` sang `updated` rồi xóa tài khoản. Nếu bước xóa bị từ chối do ACL, entry có thể **vẫn tồn tại với giá trị đã cập nhật**. Nếu đường truyền đứt sau khi server xử lý lệnh xóa nhưng trước khi client nhận phản hồi, ứng dụng thậm chí không biết chắc thao tác đã được áp dụng chưa.

Bài học thuộc chương **Transaction** của module **SPRING_LDAP**. Chúng ta sẽ xây một chuỗi thao tác có thể kiểm thử, chèn lỗi có kiểm soát, đối chiếu trạng thái thực trong directory sau từng lỗi và xác định khi nào cần xử lý bù, idempotency hoặc cơ chế transaction do server hỗ trợ.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt `bind` để **tạo entry** trong `LdapTemplate` với **LDAP Bind** để xác thực kết nối.
2. Xác định ranh giới nguyên tử của một yêu cầu LDAP và giới hạn của chuỗi `bind → modify → delete`.
3. Lập bảng trạng thái mong đợi khi lỗi xảy ra trước, trong hoặc sau từng thao tác.
4. Viết bài kiểm thử tích hợp với LDAP thử nghiệm, JUnit và cách chèn lỗi có kiểm soát.
5. Phân biệt lỗi thực sự được server trả về với tình huống **timeout/mất phản hồi** không rõ trạng thái.
6. Đánh giá khi nào có thể thử **compensating transaction**, xác minh điều kiện rollback và thiết kế retry an toàn.
7. Áp dụng nguyên tắc quyền tối thiểu, LDAPS/StartTLS, dữ liệu test riêng và cleanup có kiểm soát.

## 2. Làm rõ từ “bind” trước khi kiểm thử

Trong Spring LDAP, hai thao tác mang chữ **bind** nhưng ý nghĩa hoàn toàn khác nhau:

| API hoặc thao tác | Ý nghĩa | Có làm thay đổi entry? |
|---|---|---|
| `LdapTemplate.bind(dn, object, attributes)` | **Tạo/bind một entry mới** vào LDAP tree theo DN | Có, tạo entry nếu server chấp nhận |
| LDAP **Bind Request** / `ContextSource.getContext(principal, password)` | Xác thực danh tính trên kết nối LDAP | Không phải thao tác tạo entry |
| `LdapTemplate.modifyAttributes(...)` | Cập nhật thuộc tính entry | Có |
| `LdapTemplate.unbind(dn)` | **Xóa entry** theo DN | Có, xóa entry nếu server chấp nhận |

Trong chuỗi **bind → modify → delete** thuộc chương Transaction, `bind` thường được hiểu là **tạo entry bằng `LdapTemplate.bind(...)`**, còn `delete` tương ứng với `LdapTemplate.unbind(...)`. Bài sẽ sử dụng nghĩa này cho thao tác dữ liệu.

Một ứng dụng có thể phải **LDAP Bind để xác thực** trước khi được phép thực hiện chuỗi ba thao tác nói trên. LDAP Bind xác thực chỉ quyết định danh tính của context và quyền ACL; nó **không tự nằm trong transaction tạo/sửa/xóa entry**. Mật khẩu dùng để bind dịch vụ là credential nhạy cảm và phải được bảo vệ bằng TLS.

## 3. Tính nguyên tử ở mức LDAP khác transaction nhiều bước

LDAP server xử lý từng thao tác như Add, Modify và Delete riêng biệt. Trong một **Modify Request**, danh sách sửa đổi thuộc tính phải được server áp dụng như một đơn vị nguyên tử theo giao thức LDAP: nếu một thay đổi trong request không hợp lệ, server không được để request đó chỉ áp dụng một phần. Nhưng **tính nguyên tử của một Modify Request không kéo dài tới Add hoặc Delete ở các request khác**.

~~~mermaid
sequenceDiagram
    participant App as Ứng dụng Spring LDAP
    participant Dir as LDAP server
    App->>Dir: Add entry (LdapTemplate.bind)
    Dir-->>App: Success
    App->>Dir: Modify entry (modifyAttributes)
    Dir-->>App: Success
    App->>Dir: Delete entry (LdapTemplate.unbind)
    Dir-->>App: insufficientAccessRights
    Note over App,Dir: Không có transaction chung mặc định
    App->>Dir: Read entry để xác minh hậu trạng thái
    Dir-->>App: Entry vẫn tồn tại và đã được modify
~~~

Nếu không cấu hình cơ chế transaction/bù nào khác, chuỗi này có thể đi qua các trạng thái:

| Mốc xử lý | Trạng thái entry `uid=tx-demo-01` |
|---|---|
| Trước khi chạy | Chưa tồn tại |
| Sau `LdapTemplate.bind(...)` thành công | Tồn tại với `description=created` |
| Sau `modifyAttributes(...)` thành công | Tồn tại với `description=updated` |
| Sau `LdapTemplate.unbind(...)` thành công | Không còn tồn tại |
| Delete thất bại sau hai bước đầu thành công | **Vẫn tồn tại**, thường với `description=updated` |

**Không nên gọi toàn bộ ba bước là atomic chỉ vì Java chạy chúng trong một method.** Dùng `@Transactional` cũng không tự bảo đảm các thao tác LDAP được rollback nếu không có transaction manager và cấu hình phù hợp cho LDAP.

## 4. Ma trận lỗi theo từng vị trí trong chuỗi

Trước khi viết test, cần thống nhất **trạng thái hậu điều kiện** cho mỗi điểm lỗi. Bảng sau mô tả hành vi thường thấy khi **không có cơ chế transaction/compensation cho chuỗi**.

| Điểm xảy ra lỗi | Các thao tác chắc chắn đã thành công | Hậu trạng thái cần kiểm tra | Loại lỗi minh họa |
|---|---|---|---|
| Không tạo được connection hoặc service bind xác thực thất bại | Chưa có | Không có entry mới | TLS, DNS, credential service |
| `bind` tạo entry bị từ chối | Chưa có | Entry mới không được tạo | Thiếu quyền Add, DN trùng |
| Lỗi được chèn **sau Add** và trước Modify | Add | Entry tồn tại, còn `description=created` | Exception kiểm thử |
| Modify bị server từ chối | Add | Entry thường vẫn tồn tại với giá trị trước Modify | Thiếu quyền Modify, schema invalid |
| Lỗi được chèn **sau Modify** và trước Delete | Add, Modify | Entry tồn tại với `description=updated` | Exception kiểm thử |
| Delete bị server từ chối | Add, Modify | Entry vẫn tồn tại với giá trị đã cập nhật | ACL Delete, entry có child |
| Delete thành công và phản hồi đến client | Add, Modify, Delete | Entry không còn tồn tại | Không lỗi |
| Mất kết nối/timeout khi chờ phản hồi Delete | Add và Modify đã được xác nhận; Delete chưa rõ | **Phải đọc lại/đối soát**, không đoán | Read timeout, network reset |
| Lỗi lúc chạy thao tác bù | Một số bước đã xảy ra | Có thể tồn tại trạng thái **bù dở dang** | Mất kết nối, ACL hoặc xung đột dữ liệu |

Với lỗi trả về rõ ràng từ server, có thể dựa vào kết quả thao tác đó để xác định thất bại. Với timeout hoặc mất phản hồi, **client không luôn biết server đã xử lý yêu cầu hay chưa**. Retry mù quáng đặc biệt nguy hiểm nếu thao tác không idempotent hoặc có tiến trình khác cùng sửa entry.

## 5. Chuẩn bị môi trường test đúng ranh giới an toàn

### 5.1. Cây LDAP và quyền cho tài khoản thử nghiệm

Môi trường tích hợp nên dùng LDAP container/embedded directory hoặc máy chủ staging được phép thao tác. Ví dụ:

~~~text
dc=example,dc=org
├── ou=tx-tests
│   └── uid=tx-demo-01           # entry do test tạo, ban đầu chưa tồn tại
└── ou=system
    └── cn=svc-tx-test          # service account dành riêng cho test
~~~

Tài khoản `cn=svc-tx-test,ou=system,dc=example,dc=org` chỉ nên có quyền đọc, tạo, sửa, xóa entry **trong `ou=tx-tests`**, không có quyền đối với OU sản xuất hay thuộc tính mật khẩu của người dùng thực.

Các nguyên tắc dựng test:

1. Mỗi test tạo DN mới với định danh ngẫu nhiên hoặc namespace riêng, tránh đụng dữ liệu của test chạy song song.
2. Test có quyền delete **chỉ entry do test tạo**, và có cleanup trong `finally`/`@AfterEach` để không để lại dữ liệu.
3. Với ca lỗi ACL, dùng tài khoản test có quyền khác biệt trên **nhánh thử nghiệm**, không chỉnh ACL production.
4. Kết nối LDAP qua **LDAPS hoặc StartTLS** và xác minh CA/hostname, kể cả khi kiểm thử trên staging.
5. Log ID ca thử, DN thử nghiệm, tên bước và mã lỗi vừa đủ; **không log mật khẩu**, thông tin xác thực hoặc giá trị nhạy cảm.
6. Nếu dùng server embedded, xác nhận nó mô phỏng được ACL, schema, timeout và cách xử lý thực tế cần kiểm chứng; không suy từ test in-memory rằng production cũng có hành vi giống vậy.

### 5.2. Cấu hình Spring Boot minh họa

Giả định ứng dụng dùng Spring LDAP, `LdapTemplate` được inject qua auto-configuration:

~~~yaml
# application-ldap-it.yml — chỉ dùng cho integration test có quyền ghi
spring:
  ldap:
    urls: ${LDAP_TEST_URL:ldaps://ldap-test.example.org:636}
    base: dc=example,dc=org
    username: ${LDAP_TEST_BIND_DN}
    password: ${LDAP_TEST_BIND_PASSWORD}
~~~

Các biến môi trường ví dụ trỏ tới LDAP test:

~~~text
LDAP_TEST_URL=ldaps://ldap-test.example.org:636
LDAP_TEST_BIND_DN=cn=svc-tx-test,ou=system,dc=example,dc=org
LDAP_TEST_BIND_PASSWORD=(cấp từ secret manager)
~~~

Đây là **cấu hình thử nghiệm**, không phải cấu hình chạy trên LDAP thật. Dùng truststore phù hợp, giới hạn network access, timeout và số lượng kết nối; không hạ cấp sang kết nối không mã hóa để làm test vượt qua lỗi TLS.

## 6. Tạo chuỗi thao tác với `LdapTemplate`

Ví dụ dưới đây dùng **một entry test** để trạng thái sau từng bước dễ quan sát. Chuỗi tạo → sửa → xóa cùng một entry là **bài tập kiểm thử tính nguyên tử và lỗi**, không phải một workflow nghiệp vụ tối ưu; trong thực tế các bước có thể tác động đến nhiều DN khác nhau.

### 6.1. Lớp thực hành có điểm chèn lỗi xác định

~~~java
import javax.naming.Name;
import javax.naming.directory.Attributes;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.BasicAttributes;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;

import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

// Chỉ dùng trong test fixture để nghiên cứu trạng thái từng bước.
public class LdapChainExercise {

    public enum StopAfter {
        NONE, AFTER_CREATE, AFTER_MODIFY
    }

    public static class InjectedFailure extends RuntimeException {
        public InjectedFailure(String step) {
            super("Injected failure after " + step);
        }
    }

    private final LdapTemplate ldapTemplate;

    public LdapChainExercise(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public Name dnFor(String uid) {
        return LdapNameBuilder.newInstance()
                .add("ou", "tx-tests")
                .add("uid", uid)
                .build();
    }

    public void run(String uid, StopAfter stopAfter) {
        Name dn = dnFor(uid);
        Attributes attributes = new BasicAttributes(true);

        BasicAttribute classes = new BasicAttribute("objectClass");
        classes.add("top");
        classes.add("person");
        classes.add("organizationalPerson");
        classes.add("inetOrgPerson");

        attributes.put(classes);
        attributes.put("uid", uid);
        attributes.put("cn", "Transaction Demo");
        attributes.put("sn", "Demo");
        attributes.put("description", "created");

        // Bước 1 — tạo entry (bind ở đây KHÔNG phải login).
        ldapTemplate.bind(dn, null, attributes);
        if (stopAfter == StopAfter.AFTER_CREATE) {
            throw new InjectedFailure("create");
        }

        // Bước 2 — cập nhật thuộc tính của cùng entry.
        ldapTemplate.modifyAttributes(dn, new ModificationItem[] {
            new ModificationItem(
                DirContext.REPLACE_ATTRIBUTE,
                new BasicAttribute("description", "updated")
            )
        });
        if (stopAfter == StopAfter.AFTER_MODIFY) {
            throw new InjectedFailure("modify");
        }

        // Bước 3 — xóa entry test.
        ldapTemplate.unbind(dn);
    }
}
~~~

**Giải thích kỹ thuật:**

- `dnFor` dựng DN tương đối với base `spring.ldap.base`: `uid=<uid>,ou=tx-tests,dc=example,dc=org`. Dùng `LdapNameBuilder` để escape thành phần DN đúng cú pháp, không nối giá trị user vào DN bằng chuỗi.
- `LdapTemplate.bind(...)` tạo entry với object class và thuộc tính cần thiết. `inetOrgPerson` có các yêu cầu schema như `cn` và `sn`; dữ liệu test phải tuân thủ schema của server.
- `modifyAttributes(...)` thực hiện một LDAP Modify Request, ở đây thay `description` bằng `updated`.
- `unbind(...)` xóa entry; test không bao giờ gọi nó với DN ngoài OU `tx-tests`.
- `StopAfter` tạo lỗi **ngay sau khi server đã trả thành công** ở bước chỉ định. Đây là một cách thử có tính quyết định trạng thái, không giả vờ là đã mô phỏng đúng mọi kiểu network failure.

> **Phân biệt cách chèn lỗi:** `AFTER_MODIFY` mô phỏng sự gián đoạn *trước khi gửi Delete*, vì vậy test xác nhận trạng thái “Add và Modify đã thành công, Delete chưa chạy”. Để kiểm thử **Delete bị server từ chối thật**, cần dùng ACL/schema/entry con trong directory thử nghiệm hoặc một adapter có khả năng trả lỗi tại chính lời gọi Delete.

### 6.2. Luồng thành công

Khi gọi:

~~~java
LdapChainExercise exercise = new LdapChainExercise(ldapTemplate);
exercise.run("tx-demo-01", LdapChainExercise.StopAfter.NONE);
~~~

Kết quả cuối cùng: entry `uid=tx-demo-01,ou=tx-tests,dc=example,dc=org` **không còn tồn tại**. Tuy nhiên, đã có ba thao tác ghi được gửi đến server. Không nên dùng “không còn entry” để suy luận rằng không có thay đổi trung gian hoặc không có request ghi nào được thực hiện.

## 7. Kiểm thử tích hợp bằng JUnit: chứng minh trạng thái dở dang

Một bài test tích hợp dùng LDAP server thật trong môi trường test sẽ giúp phát hiện hành vi kết nối, schema và lỗi directory mà mock `LdapTemplate` không mô phỏng hết.

### 7.1. Test kết thúc sau Modify

Giả định Spring Boot test profile `ldap-it` đã cấu hình `LdapTemplate` trỏ tới directory test và chỉ chạy trên môi trường được phép:

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.util.UUID;
import javax.naming.Name;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.ldap.NameNotFoundException;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest
@ActiveProfiles("ldap-it")
@EnabledIfEnvironmentVariable(
        named = "RUN_LDAP_WRITE_IT", matches = "true")
class LdapChainIntegrationTest {

    @Autowired
    private LdapTemplate ldapTemplate;

    @Test
    void updatedEntryRemainsWhenDeleteIsNeverReached() {
        LdapChainExercise exercise =
                new LdapChainExercise(ldapTemplate);
        String uid = "tx-" + UUID.randomUUID();
        Name dn = exercise.dnFor(uid);

        try {
            assertThatThrownBy(() -> exercise.run(
                    uid, LdapChainExercise.StopAfter.AFTER_MODIFY))
                .isInstanceOf(LdapChainExercise.InjectedFailure.class);

            String description = ldapTemplate.lookup(
                dn,
                (AttributesMapper<String>) attrs ->
                    attrs.get("description").get().toString()
            );

            assertThat(description).isEqualTo("updated");
        } finally {
            // Cleanup chỉ nhắm tới DN vừa tạo cho test này.
            try {
                ldapTemplate.unbind(dn);
            } catch (NameNotFoundException ignored) {
                // Nếu bước tạo đã thất bại, không có gì để dọn.
            }
        }
    }
}
~~~

Kết quả mong đợi: test ném `InjectedFailure`, nhưng lookup sau đó vẫn đọc được `description=updated`. Điều này chứng minh **một exception Java không tự rollback các LDAP request đã được server chấp nhận**.

Không chạy test này với tài khoản có quyền ghi directory production. Nếu quyền LDAP test không cho xóa hoặc dữ liệu có child, cleanup phải dùng cơ chế/fixture dành riêng và báo rõ dữ liệu còn lại thay vì dùng quyền admin rộng để ép xóa.

### 7.2. Những test cần bổ sung

Không nhất thiết sao chép cả lớp JUnit cho từng trường hợp; có thể tái sử dụng fixture trên để kiểm tra:

| Ca kiểm thử | Cách tạo tình huống | Assertion quan trọng |
|---|---|---|
| **Happy path** | `StopAfter.NONE` | Entry bị xóa sau cùng; không còn trong directory |
| Lỗi sau Create | `StopAfter.AFTER_CREATE` | Entry tồn tại với `description=created`; chưa chạy Modify/Delete |
| Lỗi sau Modify | `StopAfter.AFTER_MODIFY` | Entry tồn tại với `description=updated`; chưa chạy Delete |
| Create bị từ chối | Bind DN không có quyền Add hoặc DN trùng | Không ghi đè entry cũ; lỗi được phân loại |
| Modify bị từ chối | Service account chỉ có quyền Add, không có quyền Modify | Entry đã tạo vẫn tồn tại, chưa bị thay thuộc tính |
| Delete bị từ chối | ACL deny Delete cho entry do test tạo | Entry vẫn tồn tại với giá trị đã cập nhật |
| Delete của entry có child | Dựng child entry hợp lệ, gọi Delete parent theo policy server | Lỗi `notAllowedOnNonLeaf` nếu server không cho xóa non-leaf |
| Server timeout sau gửi Delete | Proxy test làm mất phản hồi theo kịch bản kiểm soát | Đọc lại entry để xác định hậu trạng thái; không đoán |
| Schema invalid ở Modify | Sửa thuộc tính vi phạm schema trong test directory | Modify Request không được áp dụng dở dang |
| Lỗi ở cleanup | Chặn Delete trong nhánh cleanup có kiểm soát | Test báo rõ DN và trạng thái tồn dư, không che lỗi gốc |

**Test không chỉ assert exception.** Với chuỗi thao tác có side effect, phải **đọc lại directory** qua lookup/search để khẳng định postcondition. Nếu chỉ kiểm tra một exception đã xuất hiện, test vẫn có thể PASS dù entry đang ở trạng thái sai hoặc có dữ liệu tồn dư.

## 8. Gây lỗi thật ở Modify/Delete bằng ACL và schema

Fault injection tại boundary rất hữu ích, nhưng chỉ nó chưa đủ để kiểm chứng server từ chối request. Hãy bổ sung test có **directory thật hoặc mô phỏng tương thích**, áp dụng quyền trong phạm vi test:

### 8.1. Modify thất bại do thiếu quyền

1. Dùng một service account được phép **Add** entry trong `ou=tx-tests` nhưng không có quyền **Modify** thuộc tính mục tiêu.
2. Tạo entry với `description=created`.
3. Gửi `modifyAttributes(...)` thay `description=updated`.
4. Xác nhận LDAP trả lỗi quyền phù hợp (ví dụ `insufficientAccessRights`, tùy server/ACL).
5. Đọc lại entry bằng tài khoản kiểm thử có quyền phù hợp; khẳng định `description` chưa bị đổi.
6. Dọn entry bằng tài khoản cleanup được ủy quyền.

### 8.2. Delete thất bại do ACL

1. Dùng danh tính có quyền Add/Modify nhưng bị chặn Delete đối với entry test.
2. Tạo và cập nhật entry thành công.
3. Thử `LdapTemplate.unbind(dn)`.
4. Xác nhận Delete bị server từ chối.
5. Đọc lại `description=updated`, khẳng định hai bước trước vẫn hiện hữu.
6. Dọn bằng cơ chế cleanup tách biệt, không vô tình cấp cho workflow production quyền xóa quá rộng.

Nếu server tự ẩn entry hoặc trả một mã khác vì chính sách ACL, test cần ghi rõ **mã LDAP, danh tính bind, OU và kết quả đọc lại** thay vì cố chuẩn hóa mọi lỗi thành một exception duy nhất.

### 8.3. Modify chứa nhiều thay đổi trong một request

Để kiểm tra tính nguyên tử **bên trong một Modify Request**, tạo một request có ít nhất hai thay đổi: một hợp lệ và một vi phạm schema. Kết quả cần là request **không áp dụng nửa chừng**. Sau đó xác minh bằng cách đọc lại **cả hai thuộc tính**.

Đừng nhầm với bài test chuỗi ba request: server có thể áp dụng một Modify Request nguyên tử nhưng vẫn để nguyên kết quả của Add từ trước khi Modify thất bại.

## 9. Transaction trong Spring LDAP: những giới hạn phải hiểu

### 9.1. “Gọi `@Transactional` là mọi bước đều rollback” — sai

`@Transactional` chỉ có ý nghĩa khi thao tác được thực thi dưới **transaction manager thích hợp** và loại tài nguyên có cơ chế transaction tương ứng. Dùng `DataSourceTransactionManager` cho cơ sở dữ liệu quan hệ không tự làm Add/Modify/Delete trong LDAP rollback.

Với LDAP, cần phân biệt ba tình huống:

| Cơ chế | Bản chất | Điều không nên giả định |
|---|---|---|
| Các lời gọi `LdapTemplate` thông thường | Mỗi request LDAP hoạt động riêng | Không có rollback toàn chuỗi mặc định |
| **Compensating transaction** của Spring LDAP (nếu phiên bản/cấu hình hỗ trợ) | Ghi nhận trạng thái và gọi thao tác **bù ngược** khi rollback | Không phải transaction nguyên tử của LDAP server; compensation có thể thất bại |
| **LDAP Transactions Extended Operation** (RFC 5805) | Extension transaction phía server **nếu server triển khai và cho phép** | Không phải tính năng mặc định của mọi LDAP server hoặc tự động được mọi cấu hình Spring LDAP sử dụng |

Trong Spring LDAP, tài liệu về **compensating transaction support** mô tả cơ chế thực hiện các thay đổi bù tương ứng; các lớp/API cụ thể phải đối chiếu phiên bản đang sử dụng. Một transaction bù có thể thử xóa entry vừa tạo hoặc khôi phục thuộc tính đã sửa, nhưng còn phụ thuộc vào ACL, dữ liệu cũ, kết nối, thứ tự thao tác và các thay đổi đồng thời.

**Không được tuyên bố “rollback thành công” chỉ vì framework gọi một callback rollback.** Phải xác minh trạng thái thật của directory và giám sát trường hợp thao tác bù thất bại.

### 9.2. Bù ngược khi một bước thất bại

Ví dụ workflow nghiệp vụ thật có thể là **tạo một entry A → sửa entry B → xóa một entry C**. Nếu bước cuối thất bại, ứng dụng có thể cần:

1. Khôi phục **đúng trạng thái trước đó của B**, dựa trên snapshot có kiểm soát phiên bản.
2. Xóa entry A nếu A thực sự do workflow đó tạo và chưa bị tiến trình khác thay đổi.
3. Chỉ thử khôi phục C nếu C thực sự đã bị xóa và ứng dụng có dữ liệu đầy đủ, quyền phù hợp để phục hồi.
4. Ghi nhận những thao tác bù không thành công để xử lý thủ công hoặc bằng job đối soát.

Đây là dạng **saga/compensation** theo nghiệp vụ. Cần định nghĩa sự phụ thuộc và dữ liệu nào được phép đảo ngược; việc “đổi thuộc tính về giá trị cũ” có thể ghi đè cập nhật của tiến trình khác nếu không kiểm tra trạng thái.

Trong bài tập tạo → sửa → xóa **cùng một entry**, trạng thái mong đợi sau thành công là “không tồn tại”. Nếu Delete bị từ chối mà nghiệp vụ muốn hoàn tác toàn bộ, một hành động bù có thể là xóa entry do chính workflow vừa tạo **nhưng yêu cầu Delete đang bị từ chối**, nên bù kiểu này cũng có thể thất bại. Vì thế phải thiết kế **đối soát và phục hồi sau lỗi**, thay vì giả định luôn có bước đảo ngược khả thi.

### 9.3. Timeout và yêu cầu chưa rõ kết quả

Một lỗi quan trọng:

~~~text
Ứng dụng            LDAP server
   |  Delete request    |
   |------------------->|
   |                    | Entry đã được xóa
   |   (mất response)   X
   |       TIMEOUT      |
~~~

Nếu ứng dụng retry Delete, server có thể báo `noSuchObject` vì entry đã bị xóa ở lần trước. Trong trường hợp đó, thông báo lỗi mới **không tự chứng minh lần Delete ban đầu thất bại**.

Chiến lược xử lý phụ thuộc hậu điều kiện nghiệp vụ: nếu mục tiêu là “entry không còn tồn tại”, một lookup có quyền phù hợp xác nhận không có entry có thể hoàn thành bước đối soát. Tuy nhiên phải chắc chắn rằng **DN đúng, quyền search đủ và không có tiến trình khác tái tạo entry với DN đó**; lý tưởng là dùng định danh bất biến/marker của workflow.

## 10. Retry, idempotency và xử lý cạnh tranh

| Thao tác | Retry mù quáng có thể gặp | Cách thiết kế an toàn hơn |
|---|---|---|
| **Create (`bind`)** | Entry đã tồn tại, hoặc entry cùng DN đã được tiến trình khác tạo | Kiểm tra owner/marker, khóa nghiệp vụ hoặc idempotency key; không ghi đè tùy tiện |
| **Modify** | Thao tác lặp thay giá trị; có thể ghi đè cập nhật đồng thời | Đọc trạng thái/phiên bản, so sánh điều kiện hoặc dùng cơ chế đồng bộ phù hợp server |
| **Delete (`unbind`)** | `noSuchObject` sau khi Delete trước đã thành công | Đối soát hậu điều kiện và identity trước khi coi là thành công |
| **Compensation** | Xóa/khôi phục sai entry hoặc sai phiên bản | Gắn operation ID, xác minh snapshot và kiểm soát đồng thời |

Một giải pháp tổng quát là gán **operation ID** riêng cho workflow và lưu trạng thái xử lý trong một nguồn tin cậy (có thể là database nghiệp vụ). Khi retry:

1. Đọc trạng thái của operation trước.
2. Đối soát trạng thái LDAP hiện tại với hậu điều kiện đã biết.
3. Chỉ tiếp tục hoặc bù những bước còn cần thực hiện.
4. Ghi nhận bước hoàn thành bằng cơ chế idempotency phù hợp.
5. Cảnh báo nếu trạng thái mâu thuẫn hoặc không thể xác minh chắc chắn.

Nếu ứng dụng vừa ghi cơ sở dữ liệu vừa sửa LDAP, **transaction của JDBC/JPA không tự bao trùm LDAP**. Cần xem xét mô hình outbox, sự kiện đáng tin cậy, saga hoặc reconciler theo yêu cầu nhất quán của nghiệp vụ.

## 11. Tiêu chí kiểm thử bảo mật và vận hành

Các kiểm thử lỗi còn phải kiểm tra tính an toàn của hệ thống:

- **Authentication:** service bind và user bind là thao tác xác thực kết nối, không được nhầm với `LdapTemplate.bind` tạo entry.
- **Authorization:** service account chỉ có quyền trên OU test, không thể Add/Modify/Delete entry thật ngoài vùng này.
- **TLS:** LDAPS hoặc StartTLS được xác minh certificate/hostname; lỗi TLS phải dừng quy trình trước khi gửi credential.
- **Pooling:** context LDAP có danh tính đúng, không lẫn kết nối đã bind của user vào pool service account.
- **Logging:** không ghi mật khẩu, hash, secret; có operation ID, DN test, bước thất bại, loại exception và correlation ID đủ cho đối soát.
- **Timeout:** phải có giới hạn thời gian hợp lý và phân biệt lỗi không chắc hậu trạng thái với lỗi server từ chối dứt khoát.
- **Cleanup:** test dọn dữ liệu trong phạm vi được cấp; lỗi cleanup được báo cáo để xử lý, không che mất lỗi kiểm thử chính.
- **Không có quyền mặc định rộng:** không chạy integration test ghi trên production hoặc bằng tài khoản admin toàn thư mục.

### 11.1. Bảng nghiệm thu dành cho bài kiểm thử

| Tiêu chí | Bằng chứng cần thu | PASS khi |
|---|---|---|
| Happy path | Log ba bước và lookup cuối | Entry không còn tồn tại |
| Lỗi sau Create | Exception và lookup thuộc tính | Entry còn với giá trị ban đầu |
| Lỗi sau Modify | Exception và lookup thuộc tính | Entry còn với giá trị đã sửa |
| Modify bị từ chối thật | Mã lỗi LDAP + lookup | Trạng thái Create vẫn còn, Modify không được áp dụng |
| Delete bị từ chối thật | Mã lỗi LDAP + lookup | Entry còn tồn tại sau Modify |
| Mất phản hồi Delete | Log proxy test và đối soát | Không retry mù; kết quả được kiểm chứng |
| Compensation được bật | Log thao tác bù và readback | Trạng thái được phục hồi theo chính sách hoặc ghi rõ phần thất bại |
| Quyền và TLS | Kiểm thử ACL, chứng chỉ, hostname | Không vượt OU test, không gửi mật khẩu plaintext |
| Cleanup | Danh sách DN do test tạo | Không còn entry rác hoặc có báo cáo tồn dư cụ thể |

## 12. Câu hỏi và bài tập tự kiểm tra

### Bài tập

1. Tạo một OU `ou=tx-tests` trên directory thử nghiệm; cấp quyền Add/Modify/Delete riêng cho tài khoản test.
2. Chạy `LdapChainExercise` với `StopAfter.NONE`; xác nhận entry không còn tồn tại.
3. Chạy với `AFTER_CREATE` và `AFTER_MODIFY`; sau từng lỗi đọc lại entry để ghi trạng thái.
4. Tạo một danh tính thử nghiệm được phép Add/Modify nhưng **không** được Delete; chứng minh Delete bị từ chối thật và entry đã sửa vẫn còn.
5. Dùng fault proxy tại staging để cắt phản hồi Delete; quan sát trạng thái không xác định và xây bước đối soát.
6. Thiết kế một operation ID và mô tả hành vi retry nếu lần Delete trước đã thành công nhưng response bị mất.

### Câu hỏi

1. `LdapTemplate.bind(...)` khác LDAP Bind Request xác thực ở điểm nào?
2. Nếu Add thành công, Modify bị từ chối, liệu entry vừa tạo có tự biến mất không?
3. Tính nguyên tử của một LDAP Modify Request có bảo đảm nguyên tử cho cả Add và Delete trước/sau nó không?
4. Vì sao `@Transactional` với JDBC transaction manager không tự rollback thao tác LDAP?
5. Sau timeout khi gọi Delete, có thể kết luận entry chắc chắn vẫn tồn tại không?
6. Vì sao test chèn lỗi sau Modify chưa phải bằng chứng rằng LDAP server từ chối Delete?
7. Khi làm compensating transaction, tại sao chỉ ghi log “rollback attempted” chưa đủ để xác nhận dữ liệu đã phục hồi?

**Gợi ý trả lời:** (1) API `bind` của `LdapTemplate` tạo entry; LDAP Bind Request xác thực kết nối. (2) Không, Add đã được server chấp nhận; cần đối soát hoặc cơ chế bù. (3) Không, mỗi request có ranh giới riêng. (4) LDAP là tài nguyên khác và cần cơ chế transaction thích hợp. (5) Không; có thể server đã xóa nhưng response bị mất. (6) Test đó chỉ chứng minh Delete chưa được gọi, cần test server trả lỗi Delete thật. (7) Cần readback hậu trạng thái và xử lý lỗi khi thao tác bù không thành công.

## Tài liệu tham khảo

- [RFC 4511 — Lightweight Directory Access Protocol (LDAP)](https://www.rfc-editor.org/rfc/rfc4511): Add, Modify, Delete, Bind và quy tắc xử lý từng thao tác.
- [RFC 5805 — Lightweight Directory Access Protocol (LDAP) Transactions](https://www.rfc-editor.org/rfc/rfc5805): LDAP Transactions Extended Operation tùy chọn phía server.
- [Spring LDAP Reference](https://docs.spring.io/spring-ldap/reference/): `LdapTemplate`, `ContextSource` và hỗ trợ transaction/compensation theo phiên bản.
- [Spring Framework — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html): `@Transactional`, `PlatformTransactionManager` và phạm vi quản lý transaction.

## Kết luận

Kiểm thử lỗi giữa **`LdapTemplate.bind → modifyAttributes → unbind`** phải tập trung vào **trạng thái thật của directory sau mỗi bước**, vì chuỗi LDAP thông thường không có rollback nguyên tử mặc định. Hãy phân biệt bind tạo entry với bind xác thực, chèn lỗi có kiểm soát để kiểm chứng từng boundary, bổ sung ca server từ chối Modify/Delete và ca timeout mất phản hồi. Nếu nghiệp vụ yêu cầu nhất quán nhiều bước, cần thiết kế compensating transaction hoặc cơ chế transaction phù hợp với server, kết hợp idempotency, đối soát và kiểm thử việc phục hồi thực tế.
