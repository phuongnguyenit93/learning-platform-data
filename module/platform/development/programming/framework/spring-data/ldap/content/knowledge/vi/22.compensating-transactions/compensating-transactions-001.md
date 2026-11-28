# Giao dịch bù trừ phía client trong Spring LDAP là gì?

## Mục tiêu

Khi viết ứng dụng Java truy cập directory bằng **Spring Data LDAP**, ta thường dùng repository để ánh xạ entry LDAP thành đối tượng Java hoặc dùng **LdapTemplate** để thao tác trực tiếp với DN, thuộc tính và bộ lọc. Các thao tác này có thể liên quan đến nhiều entry: tạo tài khoản, bổ sung thành viên vào nhóm, rồi cập nhật trạng thái của tài khoản. Nếu bước giữa chừng thất bại, ứng dụng cần biết những thay đổi nào đã thực hiện và làm thế nào khôi phục trạng thái trước đó.

Sau bài này, người học có thể:

- Giải thích được **client-side compensating transaction** (giao dịch bù trừ phía client) trong Spring LDAP và vì sao nó khác transaction ACID của cơ sở dữ liệu.
- Mô tả cách Spring ghi nhận thông tin để hoàn tác các thao tác **bind, unbind, rebind, rename, modifyAttributes**.
- Cấu hình **ContextSourceTransactionManager** và **TransactionAwareContextSourceProxy** cho **LdapTemplate**.
- Dùng **@Transactional** đúng transaction manager, hiểu cách Spring quyết định rollback và các bẫy thường gặp.
- Nhận diện giới hạn khi mất kết nối, ứng dụng sập, thao tác đồng thời và khi phối hợp LDAP với SQL hoặc dịch vụ bên ngoài.
- Thiết kế và kiểm thử quy trình bù trừ với LDAP directory có DN, objectClass, schema, ACL và kết nối an toàn.

## 1. Vấn đề: LDAP không có transaction như JDBC

Xét quy trình tạo nhân viên trong nhánh LDAP **ou=people,dc=example,dc=org**:

1. Tạo entry **uid=linh,ou=people** có các objectClass hợp lệ.
2. Thêm DN của Linh vào thuộc tính **member** của nhóm **cn=engineering,ou=groups**.
3. Cập nhật một thuộc tính hồ sơ, chẳng hạn **description**, rồi trả kết quả cho ứng dụng.

Mỗi lời gọi LDAP có thể thành công hoặc thất bại riêng. Giả sử bước 1 tạo entry thành công nhưng bước 2 bị từ chối do ACL hoặc nhóm không tồn tại: entry nhân viên đã xuất hiện dù toàn bộ quy trình chưa hoàn tất. Một lệnh **@Transactional** dùng cho JDBC không tự động biến nhiều thao tác LDAP thành một transaction do LDAP server quản lý.

**Giao dịch bù trừ phía client** là cơ chế do **Spring LDAP** cung cấp: phía ứng dụng theo dõi các thay đổi LDAP trong một phạm vi transaction, ghi nhận thông tin cần để đảo ngược chúng, và khi rollback sẽ **gửi những thao tác LDAP bổ sung** nhằm đưa directory về trạng thái trước đó.

Ví dụ:

~~~text
Trước transaction
    uid=linh chưa tồn tại

Thao tác 1
    bind(uid=linh,...)              -> thành công

Thao tác 2
    modifyAttributes(group,...)    -> thất bại

Spring LDAP cố gắng rollback
    unbind(uid=linh,...)            -> xóa entry vừa tạo

Sau rollback, nếu thao tác bù trừ thành công
    uid=linh không còn tồn tại
~~~

Từ khóa ở đây là **cố gắng**. LDAP server nhìn thấy từng yêu cầu đọc/ghi độc lập; nó không nắm một transaction bao trùm các yêu cầu này. Đặc biệt, nếu mất kết nối giữa quy trình, server vẫn có thể giữ một phần thay đổi, còn client có thể không hoàn tác được.

## 2. Phân biệt ba khái niệm dễ nhầm

| Khái niệm | Cơ chế | Mức đảm bảo |
| --- | --- | --- |
| **Transaction JDBC/ACID** | Database quản lý commit/rollback trên dữ liệu thuộc transaction | Có tính nguyên tử, cách ly theo mức cấu hình và đảm bảo của database |
| **Spring LDAP client-side compensating transaction** | Client ghi nhận thao tác và phát sinh thao tác ngược trong rollback | **Best effort**: phụ thuộc kết nối, trạng thái directory, ACL, schema và thao tác đồng thời |
| **Bù trừ nghiệp vụ/Saga** | Ứng dụng định nghĩa hành động khắc phục cho các bước giữa nhiều dịch vụ, có thể retry hoặc điều phối lâu dài | Phụ thuộc thiết kế trạng thái, idempotency và điều phối; không phải rollback XA |

Một transaction bù trừ của Spring LDAP **không đồng nghĩa với Saga**. Spring quản lý các thao tác LDAP trong phạm vi giao dịch của process; một Saga có thể gồm database, LDAP, REST API, hàng đợi và các bước kéo dài qua nhiều lần chạy. Có thể dùng Spring LDAP transaction bên trong một bước Saga, nhưng không nên coi nó là bộ điều phối Saga bền vững.

## 3. Cơ chế hoạt động bên trong Spring LDAP

Spring LDAP có **ContextSourceTransactionManager**, một implementation của **PlatformTransactionManager**. Cơ chế này liên kết một giao dịch với **ContextSource** và sử dụng **TransactionAwareContextSourceProxy** để chặn các thao tác LDAP thay đổi dữ liệu thông qua **DirContext**. Spring giữ thông tin trước khi thay đổi, thực hiện thao tác, rồi khi hoàn tất sẽ commit hoặc thử khôi phục bằng thao tác bù trừ.

Trong một transaction, cùng một **DirContext** được sử dụng xuyên suốt phạm vi liên quan và chỉ đóng khi transaction kết thúc; đây là quản lý tài nguyên phía client, **không phải lock hay isolation do server cung cấp**.

~~~mermaid
flowchart TD
    A["Service gọi phương thức @Transactional"] --> B["ContextSourceTransactionManager bắt đầu transaction"]
    B --> C["LdapTemplate dùng TransactionAwareContextSourceProxy"]
    C --> D["Ghi nhận trạng thái và thao tác đảo ngược"]
    D --> E["Gửi thao tác LDAP cho directory"]
    E --> F{"Toàn bộ quy trình thành công?"}
    F -->|Có| G["Commit: hoàn tất các bước còn chờ"]
    F -->|Không| H["Rollback: thử chạy thao tác bù trừ"]
    H --> I{"Khôi phục thành công?"}
    I -->|Có| J["Trạng thái gần tương ứng với trước transaction"]
    I -->|Không| K["Có thể còn thay đổi dở dang: cần đối soát"]
~~~

Để hỗ trợ cả thao tác khó khôi phục như xóa entry, Spring LDAP phân tách một thay đổi thành các phần:

1. **Recording:** ghi thông tin cần thiết trước khi thay đổi, chẳng hạn DN hoặc giá trị thuộc tính cũ.
2. **Preparation:** thực hiện thay đổi ban đầu hoặc chuẩn bị thay đổi bằng entry tạm.
3. **Commit:** hoàn tất những bước chỉ được tiến hành khi transaction thành công.
4. **Rollback:** sử dụng thông tin đã ghi để gửi thao tác bù trừ khi transaction thất bại.

Không phải mọi lệnh đều cần thao tác cụ thể ở cả bốn phần. Chẳng hạn **bind** có thể hoàn tất ngay ở preparation và không cần làm thêm lúc commit.

### 3.1. Spring bù trừ từng thao tác LDAP như thế nào?

| Thao tác ban đầu | Cách ghi nhận và thực hiện | Hành động khi rollback |
| --- | --- | --- |
| **bind(dn, ...)** | Ghi DN rồi tạo entry mới | **unbind(dn)** để xóa entry mới |
| **rename(oldDn, newDn)** | Ghi cả DN cũ và mới rồi đổi tên/di chuyển | Đổi từ **newDn** về **oldDn** |
| **modifyAttributes(dn, changes)** | Ghi giá trị thuộc tính cần khôi phục, tính các **ModificationItem** bù trừ rồi cập nhật | Gửi **modifyAttributes** đảo ngược |
| **unbind(dn)** | Đổi DN của entry sang một **DN tạm**, chưa xóa hẳn | Đổi entry từ DN tạm về DN ban đầu |
| **rebind(dn, ...)** | Giữ entry cũ dưới DN tạm trước khi thay bằng dữ liệu mới | Đưa entry cũ từ DN tạm trở lại |

Hai chi tiết đặc biệt quan trọng:

**Xóa bằng unbind:** chỉ đọc lại Attributes rồi tạo lại entry có thể không khôi phục đủ dữ liệu, do một số thuộc tính bị ẩn, chỉ đọc hoặc do server quản lý. Vì vậy Spring có thể **đổi tên entry sang DN tạm**, sau đó xóa hẳn entry tạm lúc commit; nếu rollback, nó đổi tên entry tạm trở lại. Trong lúc chờ commit, tên gốc có thể chưa truy cập được như trước.

**Thay thế bằng rebind:** Spring cũng dùng entry tạm để bảo toàn entry cũ trong thời gian chờ kết quả. Do đó, quyền **rename**, quy tắc RDN, schema và vị trí nhánh tạm ảnh hưởng trực tiếp đến khả năng bù trừ.

Những thao tác trên chỉ là các hành động LDAP thông thường; mỗi hành động có thể thất bại và bị quan sát bởi client khác.

## 4. Cấu hình Spring LDAP để áp dụng transaction bù trừ

Giả sử dự án Spring Boot đã có **ContextSource** kết nối LDAP và dùng Spring Data LDAP repository/LdapTemplate. Nếu muốn LdapTemplate tham gia cơ chế bù trừ, cần nối đúng ba thành phần:

1. **ContextSource thực** để tạo kết nối và cung cấp cho transaction manager.
2. **TransactionAwareContextSourceProxy** bọc ContextSource thực cho **LdapTemplate**.
3. **ContextSourceTransactionManager** cùng ContextSource thực, cộng với Spring transaction interceptor cho **@Transactional**.

Ví dụ cấu hình Java phù hợp với API có constructor **ContextSourceTransactionManager(ContextSource)**:

~~~java
package org.example.directory;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ldap.core.ContextSource;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.transaction.compensating.manager.ContextSourceTransactionManager;
import org.springframework.ldap.transaction.compensating.manager.TransactionAwareContextSourceProxy;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@Configuration(proxyBeanMethods = false)
@EnableTransactionManagement
public class LdapCompensationConfiguration {

    // ContextSource do Spring Boot hoặc cấu hình khác cung cấp.
    @Bean("ldapTxManager")
    ContextSourceTransactionManager ldapTxManager(ContextSource contextSource) {
        return new ContextSourceTransactionManager(contextSource);
    }

    // LdapTemplate phải đi qua proxy nhận biết transaction.
    @Bean
    LdapTemplate ldapTemplate(ContextSource contextSource) {
        return new LdapTemplate(
                new TransactionAwareContextSourceProxy(contextSource));
    }
}
~~~

Đối với phiên bản Spring LDAP cũ hơn, API cấu hình transaction manager có thể dùng **setContextSource(...)** thay cho constructor; hãy đối chiếu Javadoc theo phiên bản thư viện đang sử dụng. Các dependency cần có Spring LDAP, Spring transaction và những dependency hỗ trợ của phiên bản tương ứng; **Spring Data LDAP repository không mặc nhiên biến các lời gọi thành transaction bù trừ**.

Ví dụ kết nối khi chạy trong môi trường có LDAP server riêng:

~~~yaml
spring:
  ldap:
    urls: ldaps://ldap.example.org:636
    base: dc=example,dc=org
    username: uid=svc-ldap,ou=service-accounts,dc=example,dc=org
    password: ${LDAP_BIND_PASSWORD}
~~~

**base DN** là tiền tố cây thư mục để LDAP template tính DN tương đối; **username** ở đây là DN đầy đủ của tài khoản kỹ thuật dùng để bind. Cần dùng TLS với xác minh chứng chỉ, giữ mật khẩu trong secret manager/biến môi trường và cấu hình ACL theo nguyên tắc quyền tối thiểu.

Nếu ứng dụng có nhiều **PlatformTransactionManager** (ví dụ một manager JDBC và một manager LDAP), phải chỉ rõ **transactionManager = "ldapTxManager"** tại nơi muốn bù trừ LDAP. Một tên transaction manager sai hoặc LdapTemplate nối vào ContextSource không qua proxy có thể khiến nghiệp vụ trông như có transaction nhưng các thao tác LDAP không được ghi nhận để rollback.

### 4.1. Ví dụ service thay đổi hai thuộc tính và mô phỏng lỗi

Giả định một entry **inetOrgPerson** đã tồn tại ở **uid=linh,ou=people,dc=example,dc=org**, schema cho phép các thuộc tính **description** và **telephoneNumber**, tài khoản kết nối có quyền sửa.

~~~java
package org.example.directory;

import javax.naming.Name;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;

import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class EmployeeDirectoryService {
    private final LdapTemplate ldapTemplate;

    public EmployeeDirectoryService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    @Transactional(transactionManager = "ldapTxManager")
    public void updateContact(
            String uid, String description, String phone,
            boolean simulateFailure) {
        if (uid == null || !uid.matches("[a-zA-Z0-9._-]{1,64}")) {
            throw new IllegalArgumentException("uid không hợp lệ");
        }

        // DN tương đối với base dc=example,dc=org.
        Name dn = LdapNameBuilder.newInstance("ou=people")
                .add("uid", uid)
                .build();

        ldapTemplate.modifyAttributes(
                dn,
                new ModificationItem[] {
                    new ModificationItem(
                        DirContext.REPLACE_ATTRIBUTE,
                        new BasicAttribute("description", description))
                });

        ldapTemplate.modifyAttributes(
                dn,
                new ModificationItem[] {
                    new ModificationItem(
                        DirContext.REPLACE_ATTRIBUTE,
                        new BasicAttribute("telephoneNumber", phone))
                });

        if (simulateFailure) {
            // Chỉ dùng để quan sát rollback trong môi trường test.
            throw new IllegalStateException("Lỗi nghiệp vụ mô phỏng");
        }
    }
}
~~~

Trong lời gọi:

~~~java
employeeDirectoryService.updateContact(
        "linh", "Onboarding", "+84-28-1234-5678", true);
~~~

Hai yêu cầu **modifyAttributes** có thể đã được server thực thi trước khi exception xuất hiện. Nếu transaction manager và proxy được nối đúng, Spring cố gắng khôi phục **description** và **telephoneNumber** về giá trị trước lúc gọi. Khi tham số **simulateFailure = false**, thay đổi được giữ lại nếu không xảy ra lỗi khác.

Ví dụ cần chạy thông qua **Spring-managed bean** để interceptor của **@Transactional** hoạt động. Gọi phương thức qua **this.updateContact(...)** trong cùng instance thường bỏ qua proxy transaction. Theo mặc định Spring rollback khi gặp **RuntimeException** hoặc **Error**; với checked exception, cân nhắc **rollbackFor** theo yêu cầu nghiệp vụ. Exception bị bắt rồi nuốt bên trong phương thức có thể khiến transaction vẫn commit.

Đây là ví dụ cơ chế ở **một tài nguyên LDAP**; nó không giả định rằng **@Transactional** đang điều phối cả database SQL.

## 5. Giới hạn quan trọng: rollback không được bảo đảm

| Rủi ro | Vì sao cơ chế bù trừ có thể thất bại? | Biện pháp thực tế |
| --- | --- | --- |
| **Mất mạng / server không sẵn sàng** | Client không thể gửi lệnh hoàn tác, hoặc không biết chắc lệnh trước đã được áp dụng chưa | Ghi nhận kết quả chưa xác định, kiểm tra lại trạng thái khi kết nối phục hồi |
| **Ứng dụng bị kill / process sập** | Thông tin bù trừ gắn với transaction trong process không phải nhật ký transaction bền vững trên LDAP server | Dùng bản ghi nghiệp vụ/đối soát ngoài transaction khi cần phục hồi sau restart |
| **Hai client cùng sửa entry** | LDAP transaction của Spring không cung cấp isolation; giá trị khác có thể đã được ghi trong lúc rollback | Thiết kế kiểm soát đồng thời, giảm tranh chấp, cân nhắc chính sách version hoặc assertion control nếu server hỗ trợ |
| **Không đủ ACL** | Tài khoản có thể sửa một phần nhưng không được rename, xóa hay sửa lại | Kiểm tra quyền cho cả thao tác chính và thao tác bù trừ |
| **Schema, RDN, entry có con** | DN tạm hoặc lệnh rename có thể bị server từ chối; objectClass/thuộc tính có ràng buộc | Kiểm thử trên schema thật, thiết kế nhánh tạm và quy trình với subtree |
| **Dữ liệu ngoài phạm vi LDAP** | Thay đổi DB, message hoặc HTTP call không nằm trong cơ chế undo của LDAP | Dùng quy trình liên hệ liên tài nguyên có trạng thái, retry và bù trừ nghiệp vụ |

Không được suy luận rằng việc phương thức ném exception nghĩa là directory đã trở lại trạng thái cũ. Nếu **rollback** cũng thất bại, ứng dụng phải giữ thông tin để điều tra/đối soát. Tương tự, nhãn **transaction committed** phía Spring chỉ nói về chu trình điều phối phía client, không bổ sung tính chất nguyên tử server-side cho LDAP.

### 5.1. DN tạm và chiến lược đổi tên

Khi **unbind** hoặc **rebind** tham gia giao dịch, Spring cần bảo quản entry cũ dưới một DN tạm. **DefaultTempEntryRenamingStrategy** thường thêm hậu tố vào thành phần RDN, ví dụ đổi **uid=linh,ou=people** thành một DN tạm trong cùng nhánh. Một số quy trình như xóa đệ quy/subtree cần chiến lược chuyển entry sang nhánh khác, chẳng hạn **DifferentSubtreeTempEntryRenamingStrategy**, và nhánh tạm phải có sẵn.

Chọn chiến lược phụ thuộc tính năng rename/move mà server hỗ trợ, chính sách ACL, RDN, tham chiếu giữa entry và khả năng xử lý entry có con. Không nên giả định đổi tên subtree luôn khả thi trên mọi directory. Cần kiểm thử trường hợp rollback thực sự, không chỉ đường đi thành công.

## 6. Có nên ghép giao dịch LDAP với JDBC hay dịch vụ khác?

Một nghiệp vụ phổ biến là vừa ghi **employees** trong database SQL vừa tạo tài khoản LDAP. Gọi **@Transactional** với một **DataSourceTransactionManager** chỉ bảo vệ thay đổi JDBC; gọi với **ContextSourceTransactionManager** chỉ kích hoạt cơ chế bù trừ LDAP. **Hai transaction manager riêng không tạo thành distributed transaction**.

Trong một số phiên bản Spring LDAP có **ContextSourceAndDataSourceTransactionManager** để điều phối logic hai phía. Tuy nhiên class này đã được đánh dấu **@Deprecated** trong Javadoc các phiên bản Spring LDAP 3.3.x; bản thân cách gộp đó không dùng **XA/two-phase commit**, nên vẫn có trạng thái commit lệch. Không nên chọn nó như giải pháp bảo đảm atomicity giữa SQL và LDAP.

Với quy trình nhiều hệ thống, mô hình nghiệp vụ có thể như sau:

~~~mermaid
flowchart TD
    A["DB lưu yêu cầu tạo nhân viên: PENDING"] --> B["Worker nhận yêu cầu"]
    B --> C["Tạo/cập nhật entry LDAP"]
    C --> D{"LDAP thành công?"}
    D -->|Có| E["Đối chiếu DN và đánh dấu ACTIVE"]
    D -->|Không hoặc không rõ| F["Đánh dấu RETRY / NEEDS_REVIEW"]
    F --> G["Retry có kiểm tra trạng thái hiện tại"]
    G --> C
~~~

Đây là một **thiết kế minh họa**, không phải chức năng tự động của Spring LDAP. Tùy nghiệp vụ có thể dùng **transactional outbox** ở DB, job retry có backoff, idempotency key, bản ghi operation ID, trạng thái **PENDING/ACTIVE/FAILED**, và nhiệm vụ đối soát định kỳ giữa DB với LDAP.

Ví dụ, nếu yêu cầu tạo account gặp timeout, không được lập tức tạo tiếp một DN khác. Trước tiên hãy kiểm tra DN mục tiêu có tồn tại không, các thuộc tính và objectClass có đúng không, sau đó mới quyết định hoàn tất, sửa chênh lệch hoặc báo xử lý thủ công. Với bước không thể tự động hoàn tác (chẳng hạn email đã gửi hoặc API của bên thứ ba đã thực hiện), phải định nghĩa hành động bù trừ nghiệp vụ riêng.

## 7. Thực hành kiểm thử trên LDAP directory

Cần directory kiểm thử độc lập, ví dụ OpenLDAP hoặc máy chủ LDAP nhúng có schema phù hợp; trước khi thử phải có gốc **dc=example,dc=org**, nhánh **ou=people**, account test có **uid=linh** và quyền đọc/ghi hợp lệ. Khác biệt ACL, schema và hỗ trợ rename của server có thể ảnh hưởng trực tiếp đến kết quả.

### 7.1. Kiểm tra trước và sau rollback

1. Dùng **LdapTemplate.lookup** hoặc LDAP client đọc trước các giá trị **description**, **telephoneNumber** của **uid=linh**; ghi lại giá trị và thời điểm theo dõi.
2. Gọi **updateContact("linh", ..., true)** **thông qua service bean**; kỳ vọng nhận **IllegalStateException**.
3. Đọc lại entry bằng một lời gọi LDAP độc lập ngoài transaction. Nếu rollback thành công, hai thuộc tính giống trạng thái trước.
4. Gọi lại với **simulateFailure=false**; kiểm tra giá trị mới tồn tại sau khi phương thức hoàn thành.
5. Tắt cấu hình proxy hoặc transaction manager trong một bài test có chủ đích, rồi so sánh: exception sau khi ghi có thể để lại các giá trị mới trên directory.

**Không dùng Java `assert` thuần làm cơ chế kiểm thử chính**, vì assertions có thể bị tắt ở runtime. Nên dùng JUnit và những assertion độc lập; bảo đảm setup/cleanup để mỗi ca có DN riêng và không đụng tài khoản thật.

### 7.2. Ma trận kiểm thử lỗi

| Ca | Kích hoạt | Kết quả mong đợi / điều cần kiểm chứng |
| --- | --- | --- |
| Commit bình thường | Hai sửa đổi đều thành công | Cả hai thuộc tính nhận giá trị mới |
| Rollback trong ứng dụng | Ném RuntimeException sau hai sửa đổi | Spring cố hoàn tác theo giá trị trước; đọc lại để xác nhận |
| Tạo entry rồi lỗi | **bind** thành công, bước kế tiếp lỗi | Entry vừa tạo bị **unbind** nếu rollback thực thi thành công |
| Xóa rồi lỗi | **unbind** trong transaction, rồi ném lỗi | Entry đã chuyển tạm được đưa về DN gốc nếu rollback thành công |
| Sai ACL | Tài khoản thiếu quyền rename hoặc modify | Ghi nhận lỗi thật từ directory; kiểm tra có để lại entry tạm hay không |
| Lỗi kết nối | Làm gián đoạn kết nối khi đang xử lý | Không mặc định rollback thành công; kiểm tra trạng thái thực tế và cơ chế đối soát |
| Hai client cùng ghi | Concurrent update lên cùng entry | Không kỳ vọng isolation; phân tích xung đột và giá trị cuối |
| Phối hợp SQL và LDAP | Commit DB thành công, LDAP timeout | Có khả năng chênh trạng thái; xác nhận retry/đối soát xử lý được |

Nên có test cho **DN có ký tự đặc biệt**, tuy ví dụ sử dụng **LdapNameBuilder** để ghép RDN an toàn; mọi điều kiện tìm kiếm theo người dùng phải dùng **LdapQueryBuilder/Filter** để escape giá trị. Việc rollback không khắc phục được lỗi LDAP injection hoặc lỗi phân quyền ứng dụng. Tài khoản LDAP phải có quyền tối thiểu cần thiết, và kết nối **LDAPS/StartTLS** phải kiểm tra chứng chỉ server.

## 8. Những hiểu lầm thường gặp

**“Chỉ cần @Transactional là LDAP sẽ rollback”**: chưa đủ. Phải chọn đúng **ContextSourceTransactionManager**, dùng **TransactionAwareContextSourceProxy** với **LdapTemplate**, và gọi qua transaction proxy. Các lệnh LDAP nằm ngoài đường đi này có thể không được theo dõi.

**“Rollback luôn phục hồi trạng thái chính xác”**: sai. Client phải thực thi thêm các lệnh LDAP; mất kết nối, concurrent updates, ACL và server policy có thể làm hoàn tác thất bại.

**“Xóa entry rồi rollback chỉ cần bind lại”**: không đáng tin cậy; có thuộc tính LDAP không đọc được hoặc thuộc quyền quản lý của server. Spring dùng DN tạm cho những thao tác như **unbind/rebind** nhằm bảo vệ entry ban đầu.

**“Một @Transactional bao luôn SQL, LDAP và REST”**: sai. Chọn transaction manager chỉ xác định phạm vi mà manager đó điều khiển. Khi nghiệp vụ đòi hỏi thống nhất nhiều tài nguyên, cần có cơ chế điều phối và đối soát riêng.

**“Repository và LdapTemplate giống transaction JDBC”**: repository Spring Data LDAP giúp ánh xạ entry và truy vấn; việc hỗ trợ transaction vẫn phụ thuộc cấu hình Spring LDAP và các thao tác đi qua lớp proxy thích hợp.

## 9. Tổng kết và câu hỏi tự luyện

Giao dịch bù trừ phía client trong Spring LDAP là **cơ chế phục hồi best effort do ứng dụng thực hiện**. Framework ghi nhận thông tin trước các thao tác LDAP rồi gửi thao tác bù trừ nếu có yêu cầu rollback. **ContextSourceTransactionManager** cung cấp tích hợp với Spring transaction; **TransactionAwareContextSourceProxy** bảo đảm các thao tác thay đổi LDAP được ghi nhận. Cơ chế hữu ích khi một service thực hiện nhiều thay đổi LDAP liên tiếp, nhưng không thay thế transaction ACID, không bảo vệ được mọi trường hợp lỗi mạng hoặc concurrency, và không tự giải quyết tính nhất quán với SQL/dịch vụ khác.

Hãy tự trả lời:

1. Nếu **bind** thành công rồi **modifyAttributes** thất bại, Spring có thể dùng thao tác LDAP nào để bù trừ? Điều kiện nào khiến thao tác đó cũng thất bại?
2. Vì sao Spring không đơn thuần đọc toàn bộ thuộc tính rồi **bind lại** sau khi xóa một entry?
3. **@Transactional(transactionManager="ldapTxManager")** có tự động rollback transaction JDBC không? Vì sao?
4. Nếu client bị ngắt mạng sau khi server đã xử lý một bước, hệ thống phải làm gì để xác định trạng thái cuối cùng?
5. Khi muốn xóa cả một subtree, chiến lược DN tạm và ràng buộc nào của directory phải được kiểm tra?

### Tài liệu tham khảo

- [Spring LDAP Reference — Transaction Support](https://docs.spring.io/spring-ldap/docs/3.1.4/reference/) (chương **12**, gồm cấu hình, JDBC integration và giải thích các thao tác bù trừ).
- [ContextSourceTransactionManager — Spring LDAP Javadoc](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/transaction/compensating/manager/ContextSourceTransactionManager.html).
- [TransactionAwareContextSourceProxy — Spring LDAP Javadoc](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/transaction/compensating/manager/TransactionAwareContextSourceProxy.html).
