# Vai trò của bản ghi trạng thái và các thao tác khôi phục

## Mục tiêu bài học

Trong **SPRING_DATA_LDAP**, ứng dụng Java có thể sử dụng **Spring Data LDAP repository** hoặc **LdapTemplate** để tìm kiếm, tạo, đổi tên, chỉnh sửa và xóa entry. Mỗi entry được xác định bằng **distinguished name (DN)**, tuân theo **objectClass**, schema và quyền LDAP. Khi một nghiệp vụ thực hiện **nhiều thao tác LDAP liên tiếp**, điều gì xảy ra nếu thao tác thứ ba thất bại trong khi hai thao tác đầu đã thay đổi directory?

Đó là bài toán **giao dịch bù trừ**. Spring LDAP hỗ trợ **client-side compensating transactions**: ghi nhận thông tin trước khi sửa, theo dõi thao tác và cố thực hiện hành động ngược nếu transaction cần rollback. Tuy nhiên, rollback ấy **không phải một transaction ACID đa thao tác được LDAP server quản lý**. Nếu kết nối đứt, tiến trình chết, quyền thay đổi hoặc có client khác can thiệp, trạng thái ban đầu có thể không khôi phục được.

Bài học trong chương **Giao dịch bù trừ** tập trung vào **vai trò của bản ghi trạng thái và các thao tác khôi phục**, bao gồm cả thông tin rollback được Spring LDAP theo dõi trong bộ nhớ và **nhật ký workflow bền vững** mà một ứng dụng có thể xây dựng cho việc phục hồi sau sự cố.

Sau bài học, bạn có thể:

- Phân biệt **before-image**, bộ **operation recorder** của Spring LDAP, **durable workflow journal** và **audit log**.
- Mô tả các bước **record → prepare → commit/rollback** cho **bind, unbind, rebind, rename, modifyAttributes**.
- Giải thích tại sao **temporary DN** được dùng khi xóa hoặc thay thế entry.
- Cấu hình **ContextSourceTransactionManager** và **TransactionAwareContextSourceProxy** cho một chuỗi LDAP operations.
- Xây dựng trạng thái **PREPARED**, **LDAP_APPLYING**, **OUTCOME_UNKNOWN**, **COMPENSATING**, **COMPENSATED**, **NEEDS_RECONCILIATION**.
- Chọn một thao tác khôi phục có điều kiện, xử lý thay đổi đồng thời và kết quả ghi chưa chắc chắn.
- Lập kế hoạch kiểm thử lỗi mạng, rollback, khôi phục sau restart và bảo vệ dữ liệu nhạy cảm trong journal.

## 1. Tình huống: tạo người dùng rồi thêm vào nhóm

Directory ví dụ:

~~~text
dc=example,dc=org
├── ou=people
│   ├── uid=an
│   └── uid=binh
└── ou=groups
    └── cn=backend
~~~

Một service nhận yêu cầu “tạo người dùng Chi và đưa vào nhóm backend”:

1. **LDAP Add** entry **uid=chi,ou=people,dc=example,dc=org**.
2. **LDAP Modify** thêm DN của Chi vào thuộc tính **member** của **cn=backend,ou=groups,dc=example,dc=org**.
3. Xác nhận toàn bộ nghiệp vụ thành công.

Nếu bước 1 thành công nhưng bước 2 thất bại vì **group không tồn tại** hoặc **service account không có quyền sửa member**, directory đã có người dùng Chi nhưng chưa có membership. Một chính sách có thể yêu cầu **xóa lại người dùng Chi** để bù trừ; chính sách khác có thể giữ Chi ở trạng thái chờ quản trị. Sự lựa chọn phụ thuộc **hợp đồng nghiệp vụ**, không phải được LDAP tự quyết định.

~~~mermaid
flowchart TD
    A["Nhận yêu cầu tạo Chi"] --> B["LDAP Add user"]
    B --> C{"Thành công?"}
    C -->|Không| X["Phân loại lỗi, không xóa entry có sẵn"]
    C -->|Có| D["LDAP Modify group"]
    D -->|Có| E["COMPLETED"]
    D -->|Không| F["COMPENSATION_PENDING"]
    F --> G["Kiểm tra entry có đúng do workflow tạo"]
    G --> H{"Có thể hoàn tác an toàn?"}
    H -->|Có| I["LDAP Delete user"]
    I --> J{"Đã xác minh xóa?"}
    J -->|Có| K["COMPENSATED"]
    J -->|Không| L["NEEDS_RECONCILIATION"]
    H -->|Không| L
~~~

**Lưu ý về kết quả ghi:** LDAP có thể đã xử lý Add/Modify nhưng client mất kết nối trước khi nhận response. Vì vậy một exception giao tiếp **không chứng minh** server chưa thay đổi dữ liệu.

## 2. Bản ghi trạng thái có vai trò gì?

Để đảo ngược một operation, trước hết cần biết **DN**, **loại thao tác** và **trạng thái trước khi thay đổi**:

~~~text
Before:
  DN: uid=an,ou=people,dc=example,dc=org
  telephoneNumber: 111

Forward:
  REPLACE telephoneNumber = 222

Compensation:
  REPLACE telephoneNumber = 111
~~~

Nếu không ghi giá trị **111**, ứng dụng không thể tự suy ra trạng thái cần khôi phục. Đối với **rename**, cần nhớ cả old DN và new DN; đối với **bind**, cần nhớ DN entry mới tạo; đối với **member** đa giá trị, phải biết chính xác giá trị nào đã được thêm hoặc xóa.

### 2.1. Ba loại bản ghi không tương đương

| Loại | Ai quản lý | Mục đích | Có tự khôi phục được sau khi Java process chết? |
| --- | --- | --- | --- |
| **Operation recorder của Spring LDAP** | Transaction manager/interceptor trong JVM | Tạo thao tác bù trừ cho transaction đang thực thi | **Không**, đây không phải durable journal |
| **Durable workflow journal** | Ứng dụng tự xây dựng và lưu trong database bền vững | Theo dõi intent, bước, kết quả và recovery sau crash | **Có thể**, nếu có cơ chế kiểm tra và tiếp tục an toàn |
| **Audit log** | Hệ thống giám sát/tuân thủ | Truy dấu ai làm gì, khi nào | Không mặc nhiên có đủ trước/sau trạng thái để khôi phục |

**Audit log không thay thế rollback journal.** Log “đã đổi email của An” không đủ để phục hồi khi không có giá trị trước đó, phiên bản, bằng chứng thao tác đã áp dụng và chính sách xung đột. Đồng thời, một rollback journal có thể giữ dữ liệu nhạy cảm hơn audit log; không nên xuất toàn bộ journal ra monitoring không kiểm soát.

**Nhật ký bền vững là kiến trúc bổ sung của ứng dụng.** Spring LDAP không tự tạo bảng database để lưu trạng thái transaction và không hứa resume rollback sau restart.

## 3. Cơ chế transaction bù trừ của Spring LDAP

**ContextSourceTransactionManager** triển khai **PlatformTransactionManager** để quản lý một transaction logic của LDAP ở client. **TransactionAwareContextSourceProxy** bọc **ContextSource** và giúp các thao tác sửa LDAP được theo dõi. Hạ tầng dùng các đối tượng **CompensatingTransactionOperationRecorder** để ghi dữ liệu và **CompensatingTransactionOperationExecutor** để thực hiện thao tác thuận/ngược.

Theo tài liệu Spring LDAP, mỗi operation sửa dữ liệu có thể được phân tích thành:

1. **Recording:** lưu thông tin cần thiết để bù trừ.
2. **Preparation:** thực hiện thao tác LDAP hoặc chuyển entry đến một temporary DN.
3. **Commit:** hoàn tất những việc còn lại khi transaction logic thành công.
4. **Rollback:** cố thực hiện thao tác ngược nếu transaction logic thất bại.

### 3.1. Bảng thao tác khôi phục

| LDAP operation | Ghi nhận | Prepare | Commit | Rollback dự kiến |
| --- | --- | --- | --- | --- |
| **bind / Add** | DN của entry mới | Tạo entry | Không cần thêm việc | Xóa entry vừa tạo |
| **rename / Modify DN** | Old DN, new DN | Đổi sang DN mới | Không cần thêm việc | Đổi về old DN |
| **modifyAttributes / Modify** | DN, before-state và các modification ngược | Gửi LDAP Modify | Không cần thêm việc | Gửi các **ModificationItem** đảo ngược |
| **unbind / Delete** | Original DN, temporary DN | Rename entry sang DN tạm | Xóa entry tạm | Đổi DN tạm về original DN |
| **rebind / Replace entry** | Original DN, new attributes, temporary DN | Rename entry cũ sang DN tạm | Bind dữ liệu mới tại DN cũ, xóa entry cũ tạm | Trả entry gốc từ DN tạm về vị trí cũ |

Đây là **cơ chế của Spring LDAP compensating transactions**, không phải yêu cầu mọi LDAP server phải triển khai transaction theo bảng trên. **Một LDAP Modify request trên một entry** có quy tắc xử lý nguyên tử của operation theo giao thức; nhưng **nhiều Modify/Add/Delete trên nhiều entry không tự biến thành một transaction nguyên tử nhiều bước**.

### 3.2. Rollback không cung cấp isolation

~~~text
T1: Service A đổi description của An thành "Pending".
T2: Service B đọc thấy "Pending".
T3: Service A thất bại ở thao tác kế tiếp.
T4: Service A thực hiện compensation -> description ban đầu.
~~~

Service B đã thấy trạng thái trung gian ở T2. Một LDAP client khác còn có thể thay đổi entry trước T4; nếu compensation dùng snapshot cũ một cách mù quáng, nó có thể ghi đè cập nhật hợp lệ mới hơn.

Spring LDAP không biến directory thành một database với **transaction isolation đa-entry**. Bảo vệ trước xung đột phải do chính sách nghiệp vụ/server hỗ trợ và kiểm tra dữ liệu thực tế cung cấp.

## 4. Những thông tin nên có trong bản ghi trạng thái

Một workflow có khả năng phục hồi cần đủ dữ liệu để **biết đã định làm gì**, **xác minh đã làm chưa** và **quyết định có nên đảo ngược**.

| Thông tin | Ví dụ | Vai trò |
| --- | --- | --- |
| **operationId** | UUID | Định danh một lần xử lý |
| **idempotencyKey** | request key duy nhất | Nhận diện request gửi lặp |
| **operationType** | ADD_ENTRY, MODIFY_ATTR, ADD_MEMBER | Chọn logic khôi phục |
| **directoryAlias** | people-primary | Chọn endpoint từ allowlist cấu hình |
| **targetDnRef** | Tham chiếu tới DN | Định vị entry cần kiểm tra |
| **beforeStateRef** | Tham chiếu tới snapshot được bảo vệ | Biết dữ liệu trước khi sửa |
| **desiredStateRef** | Tham chiếu/expected-state | Đối soát sau khi mất response |
| **step / status** | LDAP_APPLYING | Theo dõi bước đã xác nhận |
| **attemptCount / nextRetryAt** | 2 / thời điểm | Retry có giới hạn |
| **leaseOwner / leaseUntil** | worker-2 / thời điểm | Chống hai worker cùng xử lý |
| **version / updatedAt** | 7 / timestamp | Kiểm tra cập nhật trạng thái cạnh tranh |
| **lastErrorCategory** | NETWORK_UNKNOWN, ACL_DENIED | Hỗ trợ vận hành |

Một bản ghi minh họa:

~~~json
{
  "operationId": "967ca78e-9d8b-4bd1-8428-0297198ba3b3",
  "idempotencyKey": "req-2026-01183",
  "kind": "UPDATE_PHONE",
  "directoryAlias": "people-primary",
  "targetDnRef": "protected-ref-42",
  "beforeStateRef": "encrypted-snapshot-42",
  "desiredStateRef": "encrypted-desired-42",
  "step": "REPLACE_PHONE",
  "status": "LDAP_APPLYING",
  "attemptCount": 1,
  "version": 3,
  "lastErrorCategory": null
}
~~~

Đây là **format minh họa do ứng dụng thiết kế**, không phải file hoặc object mà Spring LDAP tự xuất ra. Nếu snapshot chứa email, số điện thoại, DN hoặc thông tin tổ chức, vẫn phải tuân thủ chính sách bảo vệ dữ liệu. **Không lưu userPassword/unicodePwd, private key, token hoặc mật khẩu bind ở dạng plaintext trong journal** chỉ để tiện rollback.

### 4.1. Journal không tự chứng minh LDAP đã áp dụng thao tác

Giả sử service chuyển status sang **LDAP_APPLYING**, gửi LDAP Modify rồi mất TCP connection. Bản ghi chỉ chứng minh **yêu cầu đã được dự định và có thể đã gửi**. Không đủ bằng chứng để chuyển nó sang **FAILED** hay **LDAP_APPLIED**. Trạng thái đúng là **OUTCOME_UNKNOWN** hoặc giữ trạng thái đang xử lý để recovery đối soát.

## 5. State machine cho workflow có phục hồi

| Trạng thái | Ý nghĩa | Hành động tiếp theo |
| --- | --- | --- |
| **RECEIVED** | Đã nhận request và kiểm tra đầu vào | Chuẩn bị before/desired |
| **PREPARED** | Đã lưu kế hoạch/before-state bền vững | Bắt đầu thao tác |
| **LDAP_APPLYING** | Đã chuyển sang gửi LDAP, chưa chắc outcome | Chờ response hoặc đối soát |
| **LDAP_APPLIED** | Đã xác minh LDAP operation thành công | Sang bước kế hoặc hoàn thành |
| **COMPLETED** | Toàn bộ điều kiện nghiệp vụ đã đạt | Kết thúc workflow |
| **COMPENSATION_PENDING** | Có bước cần được đảo ngược | Kiểm tra precondition |
| **COMPENSATING** | Đang khôi phục | Xác minh hậu điều kiện |
| **COMPENSATED** | Đã xác minh trạng thái được bù trừ | Kết thúc workflow đã hoàn tác |
| **OUTCOME_UNKNOWN** | Không biết server đã áp dụng request chưa | Đọc actual state rồi đối soát |
| **NEEDS_RECONCILIATION** | Tự động phục hồi không còn an toàn | Operator/recovery có kiểm soát |

~~~mermaid
stateDiagram-v2
    [*] --> RECEIVED
    RECEIVED --> PREPARED
    PREPARED --> LDAP_APPLYING
    LDAP_APPLYING --> LDAP_APPLIED: success xác nhận
    LDAP_APPLYING --> OUTCOME_UNKNOWN: mất response
    LDAP_APPLYING --> COMPENSATION_PENDING: lỗi xác định
    LDAP_APPLIED --> COMPLETED: xong các bước
    LDAP_APPLIED --> COMPENSATION_PENDING: bước sau thất bại
    OUTCOME_UNKNOWN --> LDAP_APPLIED: actual khớp desired
    OUTCOME_UNKNOWN --> PREPARED: xác minh chắc chưa áp dụng
    OUTCOME_UNKNOWN --> NEEDS_RECONCILIATION: dữ liệu mâu thuẫn
    COMPENSATION_PENDING --> COMPENSATING
    COMPENSATING --> COMPENSATED: khôi phục được xác minh
    COMPENSATING --> NEEDS_RECONCILIATION: xung đột/lỗi
    COMPLETED --> [*]
    COMPENSATED --> [*]
~~~

**Không chuyển trạng thái chỉ bằng suy đoán**. Ví dụ **OUTCOME_UNKNOWN → PREPARED** chỉ hợp lệ nếu có đủ bằng chứng việc ghi chưa được áp dụng và các điều kiện retry vẫn đúng. Nếu actual entry khác cả before và desired, ưu tiên **NEEDS_RECONCILIATION**, không ghi đè.

Với workflow nhiều bước, nên có **checkpoint riêng cho từng bước**. Một cờ boolean **rollbackSuccess** không cho biết rollback bước 1 đã xong nhưng bước 2 còn dở hay không.

## 6. Cách khôi phục theo từng LDAP operation

### 6.1. Bind: bù trừ bằng unbind

~~~text
Forward: ADD uid=chi,ou=people,dc=example,dc=org
Undo:    DELETE uid=chi,ou=people,dc=example,dc=org
~~~

**Chỉ xóa** nếu có bằng chứng entry được tạo bởi workflow đang phục hồi. Nếu Add bị timeout và DN đang tồn tại, entry ấy có thể đã có từ trước hoặc do worker khác tạo. Khi người dùng Chi đã được thêm vào nhóm khác hoặc có client cập nhật profile, xóa có thể gây thiệt hại lớn hơn giữ trạng thái chờ.

### 6.2. Modify: tính thao tác đảo ngược

~~~text
Before:   telephoneNumber = 111
Forward:  REPLACE telephoneNumber = 222
Undo:     REPLACE telephoneNumber = 111
~~~

Nếu trước đó thuộc tính không tồn tại, thao tác bù trừ tương ứng có thể là **REMOVE_ATTRIBUTE**, không phải set một chuỗi rỗng. Nếu **member** là đa giá trị, undo của một lệnh **ADD một DN** thường là **REMOVE chính DN đó**, chứ không xóa toàn bộ thuộc tính.

Trước khi tự động undo, kiểm tra giá trị hiện tại có còn đúng **expected value 222** không. Nếu một client khác đổi tiếp thành **333**, thao tác **222 → 111** sẽ vô tình hủy thay đổi của người khác. Có thể dùng version/metadata, quy tắc optimistic concurrency hoặc **LDAP Assertion Control** nếu directory đích hỗ trợ; nếu không thể xác minh, chuyển sang reconciliation.

### 6.3. Rename: đảo lại DN

~~~text
Forward:
  uid=an,ou=people,dc=example,dc=org
    -> uid=an,ou=alumni,dc=example,dc=org

Undo:
  uid=an,ou=alumni,dc=example,dc=org
    -> uid=an,ou=people,dc=example,dc=org
~~~

Rollback cần old DN chưa bị chiếm và entry tại new DN đúng là entry đã đổi trước đó. Ràng buộc schema, ACL, parent DN và quan hệ tham chiếu trong group có thể khiến việc đổi lại thất bại.

### 6.4. Unbind: tạm đổi tên để giữ nguyên entry cũ

Do client không chắc đọc được mọi thuộc tính LDAP (nhất là operational hoặc thuộc tính hạn chế), **đọc Attributes rồi bind lại** không bảo đảm phục hồi nguyên vẹn. Spring LDAP có thể thực hiện:

~~~text
Original: uid=an,ou=people,dc=example,dc=org
Prepare:  uid=an_temp,ou=people,dc=example,dc=org
Commit:   Xóa entry tại temporary DN
Rollback: Rename temporary DN về original DN
~~~

Đổi tên tạm là **LDAP operation thật**, client khác có thể nhìn thấy entry tạm trong lúc transaction logic chạy. Sau crash, temporary entry có thể còn sót và cần đối chiếu.

### 6.5. Rebind: bảo toàn bản cũ qua temporary DN

**rebind** thay nội dung entry ở DN có sẵn. Spring LDAP giữ entry cũ tại temporary DN trong giai đoạn chuẩn bị; khi commit, nó đưa nội dung mới về DN gốc và xóa bản cũ ở tạm. Khi rollback, framework cố trả bản cũ về vị trí ban đầu.

Các vấn đề có thể xuất hiện: thiếu quyền move, trùng temporary DN, schema mới không hợp lệ hoặc một tác nhân khác chiếm DN gốc. Không coi **rebind** có tính an toàn tương đương một **Modify** chỉ thay một thuộc tính.

## 7. TempEntryRenamingStrategy: vùng tạm cũng là trạng thái cần quản lý

| Chiến lược | Cách hoạt động | Nguy cơ |
| --- | --- | --- |
| **DefaultTempEntryRenamingStrategy** | Thêm hậu tố, thường **_temp**, vào RDN | Entry tạm vẫn ở cùng nhánh; search có thể thấy; recursive delete không phù hợp |
| **DifferentSubtreeTempEntryRenamingStrategy** | Move entry tới subtree riêng | Phải có subtree đích, ACL và khả năng rename/move phù hợp |

Ví dụ:

~~~text
Original: uid=an,ou=people,dc=example,dc=org
Default:  uid=an_temp,ou=people,dc=example,dc=org
Separate: uid=an,ou=tx-temp,dc=example,dc=org
~~~

Với thao tác **xóa cây đệ quy**, cách đổi RDN nhưng vẫn để entry ở trong cùng subtree có thể khiến xóa không đúng logic. Tài liệu Spring LDAP khuyến nghị **DifferentSubtreeTempEntryRenamingStrategy** cho các trường hợp cần thực sự chuyển entry ra ngoài nhánh đang xử lý.

Trước khi cấu hình vùng tạm, cần bảo đảm **ou=tx-temp** tồn tại, tài khoản có quyền rename vào/ra, tên không xung đột, schema phù hợp và directory cho phép move giữa các nhánh. Không tự động xóa mọi entry có suffix **_temp** mà không chứng minh nó thuộc về workflow cần dọn.

## 8. Cấu hình Spring LDAP compensating transactions

Ví dụ JavaConfig dưới đây theo API **Spring LDAP 4.1+**, trong đó **ContextSourceTransactionManager** có constructor nhận **ContextSource**. Với phiên bản cũ hơn, cách khởi tạo manager có thể khác; cần đối chiếu Javadoc đúng dependency.

### 8.1. Cấu hình kết nối

~~~yaml
app:
  ldap:
    url: ldaps://ldap.example.org:636
    base: dc=example,dc=org
    bind-dn: ${LDAP_BIND_DN}
    password: ${LDAP_BIND_PASSWORD}
~~~

Đây là cấu hình ứng dụng sở hữu để tránh phụ thuộc vào việc Spring Boot auto-configuration chọn bean nào khi có nhiều ContextSource. LDAP server phải được xác minh **CA và hostname SAN** qua LDAPS; tuyệt đối không tắt TLS verification để rollback thành công bằng mọi giá.

### 8.2. ContextSource thật, proxy và transaction manager

~~~java
package org.example.directory.config;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ldap.core.ContextSource;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.core.support.LdapContextSource;
import org.springframework.ldap.transaction.compensating.manager.ContextSourceTransactionManager;
import org.springframework.ldap.transaction.compensating.manager.TransactionAwareContextSourceProxy;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@Configuration(proxyBeanMethods = false)
@EnableTransactionManagement
public class LdapCompensatingConfig {

    @Bean("rawLdapContextSource")
    LdapContextSource rawLdapContextSource(
            @Value("${app.ldap.url}") String url,
            @Value("${app.ldap.base}") String base,
            @Value("${app.ldap.bind-dn}") String bindDn,
            @Value("${app.ldap.password}") String password) {
        LdapContextSource source = new LdapContextSource();
        source.setUrl(url);
        source.setBase(base);
        source.setUserDn(bindDn);
        source.setPassword(password);
        return source;
    }

    @Bean("txAwareLdapContextSource")
    ContextSource transactionAwareContextSource(
            @Qualifier("rawLdapContextSource") ContextSource target) {
        return new TransactionAwareContextSourceProxy(target);
    }

    @Bean("transactionalLdapTemplate")
    LdapTemplate transactionalLdapTemplate(
            @Qualifier("txAwareLdapContextSource") ContextSource proxy) {
        return new LdapTemplate(proxy);
    }

    @Bean("ldapTransactionManager")
    ContextSourceTransactionManager ldapTransactionManager(
            @Qualifier("rawLdapContextSource") ContextSource target) {
        // Manager dùng ContextSource thật, không phải proxy.
        return new ContextSourceTransactionManager(target);
    }
}
~~~

**Điều kiện quan trọng:** template cần **TransactionAwareContextSourceProxy** để các LDAP Modify/Add/Delete được recorder theo dõi, còn manager gắn với **target ContextSource gốc**. Dùng template đi thẳng vào một ContextSource không có proxy sẽ làm mất đường interceptor bù trừ, dù service có **@Transactional**.

Nếu ứng dụng có JDBC/JPA transaction manager, luôn chỉ rõ **transactionManager** cho phương thức LDAP. Việc Spring có hai transaction manager **không tạo ra một distributed transaction giữa LDAP và database**.

### 8.3. Service gồm hai thao tác LDAP

~~~java
package org.example.directory.service;

import javax.naming.Name;
import javax.naming.directory.Attributes;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.BasicAttributes;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class UserProvisioningService {
    private final LdapTemplate ldapTemplate;

    public UserProvisioningService(
            @Qualifier("transactionalLdapTemplate")
            LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    @Transactional(transactionManager = "ldapTransactionManager")
    public void createAndAssign(String uid, String cn, String sn) {
        if (uid == null || !uid.matches("[A-Za-z0-9._-]{1,64}")) {
            throw new IllegalArgumentException("uid không hợp lệ");
        }
        if (cn == null || cn.isBlank()
                || sn == null || sn.isBlank()) {
            throw new IllegalArgumentException("cn/sn bắt buộc");
        }

        Name userDn = LdapNameBuilder.newInstance("ou=people")
                .add("uid", uid).build();
        Name fullUserDn = LdapNameBuilder
                .newInstance("dc=example,dc=org")
                .add("ou", "people")
                .add("uid", uid).build();
        Name groupDn = LdapNameBuilder.newInstance("ou=groups")
                .add("cn", "backend").build();

        Attributes attributes = new BasicAttributes(true);
        BasicAttribute objectClasses = new BasicAttribute("objectClass");
        objectClasses.add("top");
        objectClasses.add("person");
        objectClasses.add("organizationalPerson");
        objectClasses.add("inetOrgPerson");
        attributes.put(objectClasses);
        attributes.put("uid", uid);
        attributes.put("cn", cn);
        attributes.put("sn", sn);

        // 1. Add entry; framework ghi DN để phục vụ compensation.
        ldapTemplate.bind(userDn, null, attributes);

        // 2. Add member; attribute chứa DN đầy đủ, không phải DN tương đối.
        ModificationItem addMember = new ModificationItem(
                DirContext.ADD_ATTRIBUTE,
                new BasicAttribute("member", fullUserDn.toString()));
        ldapTemplate.modifyAttributes(
                groupDn, new ModificationItem[]{addMember});
    }
}
~~~

Nếu **bind** thành công nhưng **modifyAttributes** ném runtime exception, Spring transaction interceptor sẽ cố rollback các thao tác đã ghi nhận. Nhưng **rollback có thể thất bại** nếu directory không còn kết nối hoặc không cho phép Undo. Không nên báo **đã khôi phục** trước khi xác minh actual state.

Tiền đề của ví dụ:

- Entry cha **ou=people**, **ou=groups** đã tồn tại; **cn=backend** là nhóm **groupOfNames** có thuộc tính **member**.
- ContextSource base là **dc=example,dc=org**. **userDn/groupDn** là DN tương đối; **fullUserDn** là DN tham chiếu lưu trong member.
- Account được cấp quyền phù hợp, TLS hợp lệ; cần bổ sung kiểm tra uniqueness, membership trùng, retry và validation theo môi trường thật.
- Phương thức public **@Transactional** được gọi **qua Spring proxy**, không tự gọi trong cùng class rồi kỳ vọng transaction interceptor chạy.

### 8.4. Hạn chế phiên bản và JDBC

Tài liệu Spring LDAP 4.0 nêu rõ hỗ trợ **JDBC Transaction Integration** của một số phiên bản cũ **đã bị loại bỏ**. Không sao chép cấu hình **ContextSourceAndDataSourceTransactionManager** từ tài liệu cũ rồi mặc định Spring LDAP 4.x còn hỗ trợ. Ngay cả khi có manager bao ngoài nhiều nguồn dữ liệu ở một phiên bản khác, không suy ra **LDAP và JDBC được commit nguyên tử theo kiểu XA**.

Operation recorder của Spring LDAP phục vụ **transaction hiện tại trong tiến trình**; nó **không tự lưu durable journal** và không hứa tiếp tục rollback sau khi JVM restart.

## 9. Durable journal: lớp bảo đảm bổ sung cho workflow dài

Với quy trình chỉ có vài thao tác LDAP ngắn, một transaction bù trừ trong JVM có thể đủ cho nhiều trường hợp. Nhưng nếu quy trình bao gồm thêm database, API khác, hàng đợi hoặc phải tồn tại qua restart, cần **bản ghi trạng thái bền vững** do ứng dụng quản lý.

Một bảng dữ liệu minh họa:

~~~sql
CREATE TABLE directory_workflow (
    operation_id       UUID PRIMARY KEY,
    idempotency_key    VARCHAR(128) UNIQUE NOT NULL,
    directory_alias    VARCHAR(64) NOT NULL,
    operation_type     VARCHAR(64) NOT NULL,
    target_dn_ref      VARCHAR(256) NOT NULL,
    before_state_ref   VARCHAR(256),
    desired_state_ref  VARCHAR(256),
    current_step       VARCHAR(64) NOT NULL,
    status             VARCHAR(40) NOT NULL,
    attempt_count      INTEGER NOT NULL DEFAULT 0,
    next_retry_at      TIMESTAMP WITH TIME ZONE,
    lease_owner        VARCHAR(128),
    lease_until        TIMESTAMP WITH TIME ZONE,
    last_error_code    VARCHAR(80),
    version            BIGINT NOT NULL DEFAULT 0,
    updated_at         TIMESTAMP WITH TIME ZONE NOT NULL
);
~~~

SQL trên mang tính thiết kế, phù hợp DBMS có **UUID** và **TIMESTAMP WITH TIME ZONE**; điều chỉnh theo hệ quản trị thực tế. **target_dn_ref** có thể là định danh mã hóa/HMAC thay vì DN plaintext. Các **before_state_ref/desired_state_ref** nên tham chiếu đến snapshot được bảo vệ với quyền đọc hạn chế. Không lưu những thuộc tính như **userPassword**, **unicodePwd** hay private key để “dễ rollback”.

**Đây không phải một database schema do Spring LDAP cung cấp.** Transaction của việc ghi row trong database là độc lập với LDAP operation. Cần phối hợp qua **state transitions, outbox/saga, reconciliation**, không tuyên bố commit hai hệ thống là nguyên tử.

### 9.1. Write-ahead: lưu intent trước khi gửi LDAP

Một quy trình có thể theo trình tự:

1. Nhận request, kiểm tra **idempotencyKey** và quyền của caller.
2. Đọc **before-state** tại DN được phép, tính **desired-state** và chọn compensation được chấp thuận.
3. **Commit journal PREPARED** trong một database transaction trước khi gửi LDAP.
4. Chuyển trạng thái sang **LDAP_APPLYING** bằng cập nhật có điều kiện (**compare-and-set**).
5. Gửi LDAP operation qua LdapTemplate có cấu hình bảo mật.
6. Nếu nhận response thành công, ghi **LDAP_APPLIED** và đi tiếp.
7. Nếu gặp lỗi chắc chắn từ chối, ghi loại lỗi và quyết định compensation; nếu mất response, ghi **OUTCOME_UNKNOWN** khi có thể.
8. Một **recovery worker** đọc những operation chưa kết thúc, claim lease, truy vấn actual LDAP state và quyết định tiếp tục/rollback/reconciliation.
9. Chỉ đặt **COMPLETED** hoặc **COMPENSATED** khi đã xác minh điều kiện cuối.

~~~mermaid
sequenceDiagram
    participant API as Spring API
    participant DB as Durable journal
    participant LDAP as LDAP server
    participant Recovery as Recovery worker
    API->>DB: INSERT PREPARED + beforeRef + operationId
    DB-->>API: Commit
    API->>DB: CAS PREPARED -> LDAP_APPLYING
    API->>LDAP: LDAP Add/Modify
    alt Phản hồi thành công
        LDAP-->>API: success
        API->>DB: UPDATE LDAP_APPLIED
    else Mất phản hồi
        LDAP--xAPI: socket closed
        API->>DB: OUTCOME_UNKNOWN nếu còn sống
        Recovery->>DB: Claim lease
        Recovery->>LDAP: Read actual state
        LDAP-->>Recovery: Actual attributes / DN
        Recovery->>DB: Reconcile / COMPENSATION_PENDING
    end
~~~

**CAS** có thể triển khai bằng SQL update **WHERE operation_id = ? AND version = ? AND status = 'PREPARED'** rồi kiểm tra số row bị thay đổi. **Lease** tránh nhiều worker cùng xử lý một request. Tuy nhiên **CAS/lease trên journal không tạo exactly-once effect trên LDAP**: worker có thể chết ngay sau khi server đã thực hiện operation, và một worker khác vẫn phải kiểm tra actual state.

### 9.2. Interface Java minh họa cho journal

~~~java
package org.example.directory.workflow;

public enum WorkflowState {
    PREPARED,
    LDAP_APPLYING,
    LDAP_APPLIED,
    COMPLETED,
    OUTCOME_UNKNOWN,
    COMPENSATION_PENDING,
    COMPENSATING,
    COMPENSATED,
    NEEDS_RECONCILIATION
}
~~~

~~~java
package org.example.directory.workflow;

import java.time.Instant;
import java.util.UUID;

public record WorkflowRecord(
        UUID operationId,
        String idempotencyKey,
        String directoryAlias,
        String targetDnRef,
        String beforeStateRef,
        String desiredStateRef,
        WorkflowState state,
        long version,
        Instant updatedAt) {
}
~~~

~~~java
package org.example.directory.workflow;

import java.time.Instant;
import java.util.List;
import java.util.UUID;

public interface WorkflowJournal {
    // Phải commit bền vững trước khi gửi LDAP;
    // idempotencyKey cần constraint unique.
    void createPrepared(WorkflowRecord record);

    // Chỉ một actor được chuyển trạng thái với version khớp.
    boolean transition(
            UUID operationId,
            long expectedVersion,
            WorkflowState expectedState,
            WorkflowState nextState);

    // Triển khai phải có lease/fencing để xử lý song song.
    List<WorkflowRecord> claimRecoverable(
            Instant now, int limit);
}
~~~

Đây là **contract ứng dụng để minh họa**, chưa phải JdbcRepository đầy đủ. Một triển khai thực phải kiểm tra affected rows, isolation, thời gian lease, version và lỗi ghi DB. Nếu **transition** trả **false**, worker phải dừng thao tác đang định gửi, vì có thể một worker khác đã chiếm quyền điều phối.

### 9.3. Đừng bao hai hệ thống trong một @Transactional rồi suy ra atomicity

Ví dụ tư duy sai:

~~~java
@Transactional
public void updateBoth() {
    jdbcTemplate.update("UPDATE app_user SET status = ? WHERE id = ?",
            "ACTIVE", userId);
    ldapTemplate.modifyAttributes(userDn, modifications);
    // Không có bảo đảm commit/rollback nguyên tử cho cả JDBC và LDAP.
}
~~~

Nếu Spring chọn JDBC manager, transaction đó bảo vệ những thao tác database thuộc manager ấy; LDAP không tự tham gia. Nếu Spring chọn **ContextSourceTransactionManager**, thao tác JDBC cũng không tự được quản lý như một thành phần trong LDAP compensation. Để điều phối, dùng **transactional outbox** hoặc workflow có journal, kiểm tra idempotency và quá trình đối soát.

## 10. Recovery worker: quyết định dựa trên actual state

Một recovery worker **không nên cứ thấy LDAP_APPLYING thì gửi Modify lần nữa**. Quy trình an toàn là:

1. **Claim lease** bằng operationId/version, và đảm bảo thao tác không bị worker khác xử lý song song.
2. Xác minh **directoryAlias** từ allowlist trong cấu hình ứng dụng, không kết nối URL tùy ý lưu trong journal.
3. Đọc entry tại đúng DN và endpoint, theo base DN, scope, schema và quyền phù hợp.
4. So sánh **actual state** với **before** và **desired** theo matching rule của thuộc tính LDAP.
5. Nếu actual đã đạt desired, đánh dấu **LDAP_APPLIED** mà không gửi operation lần nữa.
6. Nếu actual còn before, có thể retry **chỉ khi xác minh không có thay đổi ngoài workflow** và còn ngân sách retry.
7. Nếu actual mâu thuẫn với cả before/desired, không ghi đè: đặt **NEEDS_RECONCILIATION**.
8. Nếu cần undo, kiểm tra precondition của compensation, thực hiện và đọc lại để xác minh.
9. Ghi kết quả/correlationId có chọn lọc, cập nhật checkpoint và giải phóng lease.

### 10.1. Bảng đối soát một thuộc tính

Giả sử journal lưu:

~~~text
Before:  department = Engineering
Desired: department = Platform
~~~

| Actual từ LDAP | Diễn giải khả dĩ | Hành động |
| --- | --- | --- |
| **Platform** | Modify có thể đã được áp dụng | Xác nhận theo operationId/precondition và đánh dấu APPLIED |
| **Engineering** | Có thể chưa áp dụng hoặc đã được người khác hoàn tác | Xem version và bằng chứng trước khi retry |
| **Security** | Có thay đổi khác ngoài workflow | NEEDS_RECONCILIATION |
| Entry không còn | Đã bị xóa/rename hoặc DN sai | Xác minh naming, không tạo mới mù |
| Không đọc được do mạng/ACL | Chưa biết actual state | Backoff, giữ UNKNOWN và alert |

Đối với thuộc tính đa giá trị **member**, thứ tự giá trị không mang ý nghĩa. Đối với giá trị DN, cần so sánh theo cú pháp/matching rule LDAP, không dựa hoàn toàn vào **String.equals**. Với password, không tạo before-state từ một mật khẩu không thể/không nên đọc.

### 10.2. Vì sao timeout khi ghi là tình huống nguy hiểm?

~~~mermaid
sequenceDiagram
    participant Client as Client
    participant Server as LDAP server
    Client->>Server: Add uid=chi
    Server->>Server: Thực hiện Add thành công
    Server--xClient: Đứt mạng trước response
    Note over Client: CommunicationException
    Note over Server: Entry có thể đã tồn tại
~~~

Nếu gửi lại Add, LDAP có thể trả **entryAlreadyExists (68)**. Mã 68 không chứng minh entry được tạo bởi request hiện tại: một client khác cũng có thể đã tạo DN đó. Hãy đọc entry, kiểm tra dấu hiệu sở hữu/operationId hoặc điều kiện idempotency do ứng dụng thiết kế, rồi mới quyết định.

## 11. Chọn compensation theo mức độ an toàn

| Thao tác đảo ngược | Điều kiện trước khi tự động thực hiện | Khi nào cần con người? |
| --- | --- | --- |
| **Delete entry vừa Add** | Có bằng chứng entry do operation tạo, chưa được sửa hoặc sử dụng ngoài workflow | Entry có thay đổi mới, liên kết mới, không rõ chủ sở hữu |
| **Restore thuộc tính cũ** | Actual vẫn đúng expected forward state; snapshot đầy đủ | Client khác đã sửa, snapshot không còn hợp lệ |
| **Remove member vừa thêm** | Xác minh membership đó do workflow bổ sung | Thành viên đã có trước hoặc được tái thêm |
| **Add member vừa xóa** | Có snapshot xác nhận member tồn tại trước operation | Nhóm bị xóa, schema/ACL thay đổi |
| **Rename về old DN** | Old DN trống, new DN đúng entry, parent hợp lệ | DN cũ bị chiếm, thiếu quyền rename |
| **Move entry tạm về chỗ cũ** | Temporary DN liên kết với operationId, không xung đột | Không xác minh được entry tạm thuộc workflow |
| **Retry LDAP search** | Filter/scope có giới hạn, chỉ lỗi tạm | Quá ngân sách, vi phạm ACL |
| **Retry LDAP write** | Đã xác minh chưa áp dụng và retry an toàn | Outcome unknown hoặc dữ liệu mâu thuẫn |

Chính sách **idempotent** không phải “bắt mọi exception rồi trả success”. Ví dụ **ADD member** trả **attributeOrValueExists (20)** có thể có nghĩa thành viên đã tồn tại từ trước; ứng dụng phải xác minh rằng việc giữ membership là trạng thái được nghiệp vụ cho phép.

## 12. Workflow nhiều bước và thứ tự đảo ngược

Giả sử:

~~~text
S1: Add user Chi
S2: Add Chi vào nhóm backend
S3: Set description theo yêu cầu đồng bộ
~~~

Nếu S3 thất bại sau khi S1 và S2 thành công, kế hoạch bù trừ thường được suy ra theo thứ tự ngược:

~~~text
Undo S2: Remove membership của Chi khỏi backend
Undo S1: Delete entry Chi
~~~

Thứ tự này giảm khả năng để lại nhóm tham chiếu tới user đã xóa. Nhưng mỗi bước phải có **bản ghi trạng thái và guard**:

- S2 có chắc đã **thêm mới** membership không, hay membership có sẵn từ trước?
- Entry Chi có chắc do S1 tạo và chưa được actor khác chỉnh sửa không?
- Nếu Undo S2 thành công nhưng Undo S1 thất bại, journal phải giữ **partial compensation** và tiếp tục từ bước còn thiếu.
- Nếu LDAP trả lỗi sau một thao tác undo mà outcome chưa rõ, cũng phải chuyển **OUTCOME_UNKNOWN** cho compensation, không tự đánh dấu thất bại tuyệt đối.

**Một bước không thể đảo ngược hoàn toàn:** gửi email thông báo, phát event ra hệ thống khác, reset password hoặc cấp quyền đã được hệ thống khác sử dụng. Rollback LDAP không thể “lấy lại” email đã gửi hoặc xóa tác dụng phụ người khác đã quan sát. Hãy phân biệt **reversible**, **compensable có tác dụng phụ** và **irreversible** trong thiết kế workflow.

## 13. Giới hạn và rủi ro khi phục hồi

### 13.1. Mất kết nối hoặc process chết

Nếu rollback cần gửi LDAP operation mà connection đã hỏng, Spring LDAP **không thể bắt LDAP server tự khôi phục chuỗi thao tác thay mình**. Durable journal giúp khôi phục sau này nhưng không bảo đảm kết quả tức thì. Nếu process chết khi temporary DN đang tồn tại, có thể cần runbook để xử lý.

### 13.2. Concurrency và isolation

Spring LDAP không cung cấp isolation giữa nhiều client LDAP. Một snapshot có thể trở nên lỗi thời trước khi compensation. Hãy dùng precondition và đối soát, không phục hồi bằng cách **thay cả entry** khi chỉ cần sửa một trường.

### 13.3. Schema/ACL thay đổi

LDAP server kiểm tra schema và ACL ngay cả đối với operation Undo. Tài khoản có quyền thêm entry nhưng không có quyền xóa, hoặc parent bị đổi tên, có thể khiến rollback thất bại. **objectClassViolation (65)** và **insufficientAccessRights (50)** là dấu hiệu cần phân tích, không phải lý do để tắt kiểm soát.

### 13.4. Temporary DN bị bỏ lại

Entry tạm có thể còn sau crash. Không dọn bằng wildcard **uid=*_temp**, vì một entry có hậu tố giống vậy không nhất thiết thuộc transaction hiện tại. Cần xác định nguồn qua **operationId, thời điểm, chủ sở hữu, journal, DN và trạng thái thực tế**.

### 13.5. Replication và độ mới của dữ liệu

Nếu directory có nhiều replica hoặc Active Directory domain controllers, đọc từ máy khác có thể thấy giá trị cũ. Không được kết luận LDAP Modify chưa xảy ra chỉ từ một replica đang trễ. Recovery nên biết endpoint nào vừa xử lý ghi, mức nhất quán cần thiết và thời gian replication hợp lý.

## 14. An toàn và bảo mật journal

Workflow journal chứa thông tin kỹ thuật nhạy cảm như DN, mapping, before-state và desired-state. Một thiết kế đúng phải:

- Dùng **LDAPS/StartTLS** với CA và hostname hợp lệ; không tắt TLS verification để thử rollback.
- Giới hạn quyền LDAP của writer/compensator theo từng OU và thuộc tính; không dùng quyền quản trị toàn domain khi không cần.
- Chỉ kết nối **directoryAlias đã được quản trị**, không chuyển raw URL từ request hoặc journal thành ContextSource.
- Mã hóa snapshot có PII, phân quyền đọc journal, dùng retention/expiration và có quy trình xóa đúng chính sách.
- Không lưu **userPassword/unicodePwd**, mật khẩu bind, key hoặc token trong log/JSON.
- Xây DN bằng **LdapNameBuilder**, filter bằng **LdapQueryBuilder** để tránh injection.
- Giới hạn retry count, timeout, rate/concurrency của recovery workers; không tạo thác truy vấn khi directory đang yếu.
- Audit thay đổi trạng thái workflow (ai, lúc nào, vì sao) nhưng che DN/PII khi cần.
- Bảo vệ thao tác operator như “force retry”, “force compensate”, “delete temporary entry” bằng quyền và xác nhận phù hợp.

## 15. Kiểm thử rollback và recovery

Phân biệt hai nhóm test:

1. **Compensating transaction test:** xác minh Spring LDAP có ghi và bù trừ các operation trong một @Transactional khi phát sinh exception.
2. **Durable recovery test:** xác minh journal vẫn tồn tại sau restart; worker xử lý unknown outcome, lease cạnh tranh và các trạng thái mâu thuẫn mà không ghi đè dữ liệu.

### 15.1. LDAP test fixture

~~~ldif
dn: dc=example,dc=org
objectClass: top
objectClass: domain
dc: example

dn: ou=people,dc=example,dc=org
objectClass: top
objectClass: organizationalUnit
ou: people

dn: ou=groups,dc=example,dc=org
objectClass: top
objectClass: organizationalUnit
ou: groups

dn: uid=an,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: an
cn: An Tran
sn: Tran

dn: cn=backend,ou=groups,dc=example,dc=org
objectClass: top
objectClass: groupOfNames
cn: backend
member: uid=an,ou=people,dc=example,dc=org
~~~

**groupOfNames** yêu cầu **member** tối thiểu một giá trị. Với test xóa member cuối, server có thể trả schema violation. Suffix/parent được tạo trước; không import trùng những entry đã tồn tại trên server.

### 15.2. Ma trận test

| Ca | Thiết lập/điểm gây lỗi | Kỳ vọng |
| --- | --- | --- |
| Add user + member thành công | Đủ ACL/schema | User và membership được xác minh |
| Bước 2 thất bại | Dùng nhóm không có/quyền bị từ chối | Compensation cố xóa user, đọc lại actual state |
| Add trùng DN | Tạo sẵn user | Không được xóa entry có sẵn khi bù trừ |
| Modify rồi rollback | Đổi telephoneNumber và chủ động ném runtime exception | Trả đúng before-state khi không có concurrency |
| Rename rồi rollback | Rename user trên OU test, gây lỗi sau đó | Entry quay về DN gốc nếu không xung đột |
| Unbind rồi rollback | Unbind trong transaction rồi ném lỗi | Entry từ temporary DN trở về original DN |
| Commit unbind | Không gây lỗi | Temporary entry được xóa |
| Recursive delete | Dùng test subtree và renaming strategy phù hợp | Không để entry tạm trong subtree đang xóa |
| Mất response sau Add | Fault injection network trên test | Journal UNKNOWN, recovery không Add lại mù |
| App chết sau PREPARED | Kill test process trước LDAP | Worker đánh giá chưa áp dụng trước khi resume |
| App chết sau LDAP success | Kill process trước khi ghi APPLIED | Đọc actual LDAP, đánh dấu APPLIED |
| Concurrent modification | Client khác sửa attribute sau snapshot | Không overwrite; NEEDS_RECONCILIATION |
| Thiếu quyền Undo | Thu hồi ACL delete/rename trên test | Ghi nhận rollback failure, không báo COMPENSATED |
| Replica trễ | Đọc từ replica khác hoặc giả lập lag | Recovery có chính sách chờ/đọc đúng endpoint |
| Hai worker cùng recover | Cùng claim một operationId | Lease/CAS chỉ cho một worker điều phối |

Chỉ gây lỗi mạng, kill process, recursive delete trên directory **test cô lập được cấp phép**. Không sử dụng LDAP production để “thử độ bền rollback”.

### 15.3. Ví dụ integration test trong Spring

Ví dụ sau sử dụng **UserProvisioningService** đã khai báo ở phần 8 và yêu cầu fixture có **nhóm không tồn tại**, để thao tác thứ hai thất bại. Phương thức được gọi qua Spring proxy, không gọi nội bộ:

~~~java
package org.example.directory;

import javax.naming.Name;
import org.example.directory.service.UserProvisioningService;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest
class CompensationIntegrationTest {
    @Autowired UserProvisioningService provisioningService;

    @Autowired
    @Qualifier("transactionalLdapTemplate")
    LdapTemplate template;

    @Test
    void reversesAddWhenSubsequentModifyFails() {
        String uid = "test-compensate-42";

        // Fixture phải khiến bước Add member bị từ chối.
        // Phải xác nhận uid này chưa tồn tại trước test.
        assertThrows(RuntimeException.class,
                () -> provisioningService.createAndAssign(
                        uid, "Test Compensation", "Compensation"));

        Name personDn = LdapNameBuilder.newInstance("ou=people")
                .add("uid", uid).build();

        // Khi rollback có thể hoàn tất, entry test không còn.
        assertThrows(org.springframework.ldap.NameNotFoundException.class,
                () -> template.lookup(
                        personDn,
                        (AttributesMapper<String>) attrs ->
                                (String) attrs.get("uid").get()));
    }
}
~~~

**Test chỉ có ý nghĩa khi fixture thực sự khiến bước thứ hai thất bại** và quyền tài khoản đủ để rollback. Không giả định LDAP test luôn đáp ứng điều đó. Phải dọn entry test còn sót theo quy trình an toàn sau khi test; cũng nên dùng template chỉ đọc độc lập khi xác minh trạng thái sau rollback.

### 15.4. Test journal bằng state machine

Nhiều quy tắc recovery có thể unit test mà không cần LDAP server:

~~~text
PREPARED -> LDAP_APPLYING            : CAS chỉ một worker được chuyển
LDAP_APPLYING -> OUTCOME_UNKNOWN     : nếu mất response
OUTCOME_UNKNOWN -> LDAP_APPLIED      : actual khớp desired
OUTCOME_UNKNOWN -> PREPARED          : chỉ khi chắc chưa áp dụng
OUTCOME_UNKNOWN -> NEEDS_RECONCILIATION: actual mâu thuẫn
COMPENSATING -> COMPENSATED          : xác minh khôi phục thành công
COMPENSATING -> NEEDS_RECONCILIATION : thiếu quyền/xung đột
COMPLETED -> COMPENSATING            : từ chối nếu không có workflow mới
~~~

Test này kiểm tra **logic điều phối**, còn integration test kiểm tra **LDAP server thật** có cho phép các operation, rename và ACL hay không.

## 16. Bảng chẩn đoán và runbook vận hành

| Dấu hiệu | Nguyên nhân có thể | Bước xử lý |
| --- | --- | --- |
| User vẫn tồn tại sau exception trong @Transactional | LdapTemplate không đi qua transaction-aware proxy hoặc rollback thất bại | Kiểm tra manager/proxy, root cause và actual LDAP |
| Temporary DN còn sau crash | Commit hoặc rollback chưa hoàn tất | Đối chiếu journal/operationId, không xóa theo tên |
| Rollback Modify không thành công | ACL, schema hoặc concurrent change | Đọc trạng thái, chuyển RECONCILIATION |
| Rename về old DN bị lỗi **68** | Old DN bị chiếm | Không overwrite, điều tra xung đột |
| **noSuchObject (32)** khi Undo | DN, parent, entry tạm không còn hoặc base sai | Kiểm tra DN đầy đủ/tương đối, replication |
| **insufficientAccessRights (50)** | Writer thiếu quyền bù trừ | Xem ACL, dùng operator có quyền được phê duyệt |
| **objectClassViolation (65)** | Phục hồi vi phạm schema hiện tại | Kiểm tra objectClass, MUST/MAY và snapshot |
| **CommunicationException** sau ghi | Outcome chưa chắc | Đọc lại và đối soát, không retry/xóa mù |
| Journal COMPLETED nhưng LDAP khác | Replication lag, client khác thay đổi, bug journal | Reconciliation theo operationId |
| Hai recovery workers cùng gửi Modify | Thiếu lease/fencing hoặc timeout lease | Cập nhật CAS/ownership và idempotency |

**Runbook** cho ca không khôi phục tự động:

1. Xác định operationId, directoryAlias, status, lease, thời điểm và các bước thành công đã ghi.
2. Đọc **actual LDAP state** tại endpoint phù hợp, bảo vệ dữ liệu nhận được.
3. Đối chiếu before/desired, điều kiện ghi trước và mọi thay đổi từ client khác.
4. Đánh giá schema, ACL, referential integrity, replication và các hệ thống phụ trợ đã nhận event.
5. Quyết định retry, compensation, tiếp tục nghiệp vụ hoặc kết thúc với manual decision.
6. Chỉ đổi trạng thái khi có bằng chứng; mọi can thiệp phải được audit, không sửa DB row tùy tiện.
7. Nếu còn temporary DN, xử lý theo journal gắn operationId, không chạy một job xóa wildcard.

## 17. Những hiểu nhầm thường gặp

**“@Transactional biến nhiều LDAP operations thành ACID transaction.”** Không. Spring LDAP cung cấp client-side compensation, không có isolation hoặc atomic commit đa-entry như database transaction.

**“Spring LDAP tự lưu rollback log vào database.”** Không. Recorder phục vụ transaction trong tiến trình; durable journal do ứng dụng tự thiết kế.

**“Có exception nghĩa là LDAP chưa sửa gì.”** Không. Có thể server đã thực thi request rồi mất response.

**“Rollback luôn trả LDAP về đúng trạng thái trước đó.”** Không. Mạng, ACL, schema, concurrency và những client khác có thể làm undo thất bại.

**“Đọc Attributes trước unbind rồi bind lại là đủ.”** Không. Client có thể không đọc được operational/hidden attributes; một chiến lược là giữ entry gốc qua temporary rename.

**“Commit nghĩa là không ai nhìn thấy trạng thái trung gian.”** Sai. Cơ chế client-side không có isolation đa operation.

**“OUTCOME_UNKNOWN có thể coi là FAILED và retry ngay.”** Không. Phải đọc lại directory trước khi retry một thao tác ghi.

**“Bản ghi audit là rollback journal.”** Không. Audit thường không đủ snapshot và dữ liệu để quyết định bù trừ.

**“Có thể xóa mọi entry kết thúc bằng _temp sau một ngày.”** Không. Phải kiểm tra nó thuộc workflow nào và trạng thái gốc ra sao.

**“JDBC @Transactional sẽ rollback LDAP.”** Không. Cả hai phụ thuộc hai cơ chế transaction khác nhau; Spring LDAP 4.0 đã loại bỏ hỗ trợ JDBC integration kiểu cũ.

## 18. Tổng kết và bài tập tự luyện

**Bản ghi trạng thái** là nền tảng để biết một workflow **đã định làm gì, đã thực hiện bước nào, trạng thái trước đó thế nào và có thể bù trừ ra sao**. Spring LDAP dùng **ContextSourceTransactionManager** cùng **TransactionAwareContextSourceProxy** để theo dõi các thao tác **bind, unbind, rebind, rename, modifyAttributes** và cố thực hiện thao tác khôi phục khi rollback.

Tuy nhiên, đây **không phải server-side transaction nhiều entry**. Với workflow quan trọng, cần bổ sung **durable journal, idempotency key, trạng thái OUTCOME_UNKNOWN, lease/CAS, kiểm tra actual LDAP và reconciliation**. Compensation cần tuân thủ **DN, objectClass, schema, LDAP ACL, TLS**, cùng các thay đổi đồng thời của hệ thống khác.

**Bài tập:**

1. Với **REPLACE telephoneNumber từ 111 sang 222**, cần ghi thông tin gì để bù trừ? Điều gì xảy ra nếu client khác đã sửa thành 333?
2. Vì sao compensation của **unbind** dùng temporary DN thay vì chỉ đọc Attributes rồi bind lại? Trình bày giới hạn.
3. Lập bảng **record / prepare / commit / rollback** cho **bind, rename, modifyAttributes**.
4. Thiết kế state machine cho **tạo user + thêm vào nhóm**. Nếu group không tồn tại, bù trừ bước nào trước?
5. Service gặp CommunicationException sau Add; lần thử lại trả entryAlreadyExists (68). Cần bằng chứng gì để kết luận?
6. Vì sao **LdapTemplate** dùng transaction-aware proxy, còn transaction manager dùng ContextSource gốc?
7. So sánh operation recorder trong RAM, durable workflow journal và audit log khi JVM chết sau LDAP Modify.
8. Những điều kiện về parent, schema, ACL và uniqueness cần kiểm tra khi dùng **DifferentSubtreeTempEntryRenamingStrategy**?
9. Thiết kế test gây rollback thất bại do thiếu quyền xóa user. Journal phải ghi trạng thái nào?
10. Giải thích vì sao **JDBC @Transactional** không chứng minh được LDAP và database được commit nguyên tử.

### Tài liệu tham khảo

- [Spring LDAP — Transaction Support](https://docs.spring.io/spring-ldap/reference/transaction-support.html) — client-side compensating transactions, bảng record/prepare/commit/rollback và renaming strategies.
- [Spring LDAP — ContextSourceTransactionManager Javadoc](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/transaction/compensating/manager/ContextSourceTransactionManager.html) — cơ chế manager, hạn chế khi network failure và concurrency.
- [Spring LDAP — TransactionAwareContextSourceProxy Javadoc](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/transaction/compensating/manager/TransactionAwareContextSourceProxy.html) — chặn thao tác sửa để ghi lại các rollback operations.
- [Spring LDAP — DefaultTempEntryRenamingStrategy Javadoc](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/transaction/compensating/support/DefaultTempEntryRenamingStrategy.html) — xử lý temporary DN theo suffix.
- [Spring LDAP — DifferentSubtreeTempEntryRenamingStrategy Javadoc](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/transaction/compensating/support/DifferentSubtreeTempEntryRenamingStrategy.html) — vùng tạm riêng khi unbind/rebind.
- [Spring LDAP Reference](https://docs.spring.io/spring-ldap/reference/) và [Spring Data LDAP Reference](https://docs.spring.io/spring-data/ldap/reference/) — ContextSource, LdapTemplate, repository và ODM.
- [RFC 4511 — LDAP: The Protocol](https://www.rfc-editor.org/rfc/rfc4511) — LDAP Modify/Add/Delete/Modify DN và result codes.
- [RFC 5805 — LDAP Transactions](https://www.rfc-editor.org/rfc/rfc5805) — phần mở rộng giao thức tùy chọn; không được mặc định server hỗ trợ hoặc nhầm với Spring LDAP compensation.
