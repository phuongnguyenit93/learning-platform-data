# Phân biệt giao dịch bù trừ với giao dịch ACID ở cơ sở dữ liệu quan hệ

## 1. Vấn đề: nhiều thao tác LDAP cùng phục vụ một nghiệp vụ

Trong **Spring Data LDAP**, một repository hoặc `LdapTemplate` có thể đọc, tạo, sửa và xóa các entry trong directory, chẳng hạn nhân viên, nhóm và quyền truy cập. Dữ liệu được nhận diện bằng **DN** (*distinguished name*), tổ chức thành cây và phải tuân theo schema, `objectClass` cùng quyền truy cập của LDAP server.

Giả sử hệ thống cần cấp quyền truy cập cho nhân viên mới:

1. Tạo entry `uid=linh,ou=people,dc=example,dc=org`.
2. Thêm DN đó vào thuộc tính nhiều giá trị `member` của nhóm `cn=developers,ou=groups,dc=example,dc=org`.
3. Ghi nhận nhân viên đã được cấp quyền trong một bảng nghiệp vụ của cơ sở dữ liệu quan hệ.

Nếu bước 1 và 2 thành công nhưng bước 3 thất bại, thư mục LDAP có thể giữ lại người dùng và tư cách thành viên không mong muốn. Trong SQL, ta quen với `BEGIN → các câu lệnh → COMMIT/ROLLBACK`. Với LDAP, **không được mặc định xem nhiều request thêm/sửa/xóa entry như một transaction ACID thống nhất**.

Ở đây xuất hiện mô hình **giao dịch bù trừ** (*compensating transaction*): khi công việc đã được thực hiện một phần, hệ thống chạy **các thao tác mới nhằm đảo ngược tác động nghiệp vụ** của các bước đã hoàn thành. Bù trừ là cơ chế khôi phục có điều kiện, không phải phép quay ngược thời gian hay bảo đảm rollback nguyên tử.

Sau bài học, bạn sẽ phân biệt được:

- Các bảo đảm **Atomicity, Consistency, Isolation, Durability (ACID)** của transaction cơ sở dữ liệu quan hệ.
- Tính nguyên tử của **một thao tác LDAP** và giới hạn khi ghép **nhiều thao tác LDAP**.
- Bù trừ ở tầng Spring LDAP, Spring Data LDAP và workflow ứng dụng.
- Vai trò thật sự của `@Transactional`, transaction manager, retry và kiểm thử lỗi.
- Các giới hạn của việc hoàn tác entry, DN, `objectClass`, membership và dữ liệu đồng thời.

## 2. Nhắc lại ACID trong cơ sở dữ liệu quan hệ

Transaction SQL gói nhiều câu lệnh vào một đơn vị công việc. Ví dụ:

```sql
BEGIN;

INSERT INTO employees(employee_id, full_name)
VALUES (101, 'Linh Nguyen');

INSERT INTO group_members(group_id, employee_id)
VALUES (7, 101);

COMMIT;
-- Nếu gặp lỗi trước COMMIT, ứng dụng có thể ROLLBACK.
```

Các bảo đảm ACID được hiểu như sau:

| Thuộc tính | Ý nghĩa trong hệ quản trị cơ sở dữ liệu quan hệ | Điều không nên suy diễn |
| --- | --- | --- |
| **Atomicity** (nguyên tử) | Transaction cam kết tất cả thay đổi của nó hoặc không cam kết thay đổi nào khi rollback thành công. | Không có nghĩa mọi tác động ngoài DB như email, LDAP, HTTP cũng bị rollback. |
| **Consistency** (nhất quán) | Transaction phải đưa DB từ trạng thái thỏa những ràng buộc được áp dụng sang trạng thái hợp lệ tiếp theo. | DB không tự hiểu mọi quy tắc nghiệp vụ nếu chúng chưa được thiết kế/thực thi. |
| **Isolation** (cô lập) | Các transaction đồng thời có mức tách biệt theo isolation level đã chọn. | Không phải mọi mức cô lập đều cho kết quả tương đương `SERIALIZABLE`. |
| **Durability** (bền vững) | Thay đổi đã commit được lưu giữ theo các bảo đảm về lưu trữ/phục hồi của hệ DB. | Không bảo đảm dịch vụ bên ngoài đã thực hiện một lệnh liên quan. |

Trên một database với transaction manager phù hợp, khi câu lệnh thứ hai gặp lỗi trước commit, rollback có thể đưa cả hai thay đổi chưa commit trở về trạng thái trước transaction. Cơ sở dữ liệu quản lý log, cơ chế đồng thời và phục hồi cho việc này; lập trình viên thường không phải viết một câu `DELETE` đối nghịch cho từng `INSERT`.

**Điều kiện quan trọng:** bảo đảm đó chỉ áp dụng cho những tài nguyên thực sự tham gia cùng transaction. Chỉ vì một phương thức Java được gắn `@Transactional` không có nghĩa một LDAP server, một SQL database và một HTTP API sẽ cùng rollback.

## 3. LDAP có những mức nguyên tử nào?

LDAP là giao thức để truy cập dịch vụ thư mục. Nó có các request như `Add`, `Modify`, `Delete`, `Modify DN` và `Search`. Đừng đánh đồng một LDAP request với chuỗi nhiều request.

### 3.1. Một LDAP Modify có thể là thao tác nguyên tử

Theo LDAPv3 (RFC 4511), **danh sách các sửa đổi trong một `ModifyRequest` được thực hiện như một thao tác nguyên tử và theo thứ tự**. Ví dụ, cập nhật `mail` và `telephoneNumber` của **cùng một entry** trong một `ModifyRequest`:

```java
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;
import org.springframework.ldap.core.LdapTemplate;

void updateContact(LdapTemplate ldapTemplate) {
    ModificationItem[] changes = {
        new ModificationItem(
            DirContext.REPLACE_ATTRIBUTE,
            new BasicAttribute("mail", "linh@example.org")
        ),
        new ModificationItem(
            DirContext.REPLACE_ATTRIBUTE,
            new BasicAttribute("telephoneNumber", "+84-28-5555-0101")
        )
    };

    ldapTemplate.modifyAttributes(
        "uid=linh,ou=people",
        changes
    );
}
```

Giả định `ContextSource` đã đặt base DN `dc=example,dc=org`, hai thay đổi cùng nhắm đến entry `uid=linh,ou=people,dc=example,dc=org`. Nếu server tuân theo LDAPv3 và trả lỗi do một thay đổi vi phạm schema, toàn bộ danh sách `Modify` phải được xử lý theo tính nguyên tử của request.

**Phạm vi bảo đảm chỉ là request này.** Một lần gọi `ldapTemplate.modifyAttributes(...)` không tạo ra transaction bao trùm các request LDAP khác hoặc các câu SQL trước/sau đó.

### 3.2. Nhiều request LDAP không mặc nhiên là một transaction ACID

Xét chuỗi:

```text
T1  LDAP Add       uid=linh,ou=people              -> success
T2  LDAP Modify    cn=developers,ou=groups         -> success
T3  SQL Insert     employee_permission_audit      -> failure

Kết quả tức thời:
  LDAP: người dùng tồn tại, nhóm đã có member
  SQL:  bản ghi audit chưa được ghi
```

LDAP server xử lý từng request theo ngữ nghĩa riêng. Khi request `T3` đến SQL thất bại, một LDAP server thông thường không biết cần tự động đảo ngược `T1` và `T2`. Transaction manager của SQL cũng không thể tự phát hành `LDAP Delete` hay `LDAP Modify` thay bạn.

LDAP có đặc tả **LDAP Transactions** (RFC 5805) dưới dạng mở rộng tùy chọn, nhưng khả năng hỗ trợ phụ thuộc vào directory server, client và cấu hình cụ thể. Không được giả định mọi LDAP server hoặc mọi cấu hình Spring LDAP đều triển khai chuẩn này. Bài này tập trung vào **compensating transaction**, một chiến lược khác với transaction nguyên tử do server cung cấp.

## 4. Giao dịch bù trừ hoạt động như thế nào?

Bù trừ chia một nghiệp vụ lớn thành các bước có thể quan sát:

- **Forward action:** thao tác tiến làm thay đổi trạng thái, ví dụ thêm entry, cập nhật thuộc tính, thêm membership.
- **Compensating action:** thao tác hoàn tác tương ứng ở mức nghiệp vụ, ví dụ xóa entry vừa tạo hoặc phục hồi giá trị thuộc tính cũ.
- **Recovery:** khi lỗi, thực hiện các compensating action theo thứ tự phù hợp, thường ngược thứ tự các bước đã xác nhận thành công.
- **Reconciliation:** kiểm tra trạng thái thực tế và sửa sai lệch nếu bù trừ thất bại hoặc không xác định được request trước đó đã hoàn tất hay chưa.

Minh họa:

```text
                        LUỒNG THÀNH CÔNG
  [A] Tạo user ----> [B] Thêm member ----> [C] Ghi DB ----> Hoàn tất
       LDAP                LDAP                SQL

                        LUỒNG GẶP LỖI
  [A] Tạo user ----> [B] Thêm member ----> [C] Ghi DB lỗi
        |                   |
        v                   v
  [A'] Xóa user <---- [B'] Gỡ member

  Nếu B' hoặc A' lỗi: lưu trạng thái phục hồi, thử lại có kiểm soát,
  kiểm tra trạng thái directory và chuyển xử lý thủ công khi cần.
```

Điểm phân biệt quan trọng: `A'` không làm `A` biến mất khỏi lịch sử. Ví dụ, một hệ khác có thể đã đọc được entry trước khi bù trừ, server có thể đã ghi audit log, hoặc thông báo đã được gửi. Bù trừ chỉ cố gắng đưa **trạng thái hiện tại** trở về trạng thái phù hợp với quy tắc nghiệp vụ.

### 4.1. Bảng ánh xạ thao tác LDAP và bù trừ

| Forward action | Bù trừ có thể triển khai | Hạn chế cần phân tích |
| --- | --- | --- |
| `Add` entry mới | `Delete` entry vừa tạo. | Phải chắc chắn đúng entry do giao dịch tạo; có thể đã phát sinh tham chiếu từ nơi khác. |
| `Modify` một hoặc nhiều attribute | Phục hồi **snapshot** giá trị cũ hoặc áp dụng thay đổi nghịch. | Cập nhật đồng thời có thể khiến restore ghi đè dữ liệu mới của người khác. |
| Thêm DN vào `member` của nhóm | Xóa đúng giá trị `member` vừa thêm. | Group có thể đổi tên, bị xóa hoặc có consumer đã quan sát membership. |
| `Delete` entry | Khôi phục entry từ snapshot hoặc đổi tên tạm trước khi hoàn tất xóa. | Không phải mọi thuộc tính operational và trạng thái ngoài entry đều khôi phục được. |
| `Modify DN` (rename/move) | Đổi DN về giá trị trước đó. | DN cũ có thể bị chiếm, entry con/quan hệ tham chiếu có thể đã thay đổi. |
| Ghi SQL cùng với sửa LDAP | Bù trừ ở hệ đã hoàn tất, hoặc tiếp tục công việc còn thiếu. | Cần kế hoạch phối hợp và xử lý crash xuyên hệ thống. |

Trong LDAP, DN là định danh có cấu trúc và `objectClass` ràng buộc entry hợp lệ. Vì vậy, “phục hồi từ snapshot” không đơn giản chỉ là chép lại object Java: schema có thể thay đổi, thuộc tính chỉ đọc có thể không được ghi lại, RDN/parent DN có thể biến mất và ACL có thể từ chối thao tác.

### 4.2. Bù trừ phải xem xét trước khi chạy bước tiến

Trước mỗi bước, cần biết:

1. Trạng thái nào được coi là **đã thành công** và có thể kiểm tra lại?
2. Muốn hoàn tác, cần lưu giá trị cũ hoặc DN nào?
3. Nếu yêu cầu gửi thành công đến server nhưng phản hồi bị mất, xác định kết quả bằng cách nào?
4. Nếu cùng lúc có request khác sửa entry, khi nào việc bù trừ còn an toàn?
5. Nếu bù trừ thất bại, hệ thống lưu tiến độ ở đâu để khôi phục sau khi process khởi động lại?

Những câu hỏi này thường quan trọng hơn một lệnh `try/catch` đơn giản.

## 5. So sánh ACID và bù trừ theo các thuộc tính cốt lõi

| Tiêu chí | Transaction ACID trong DB quan hệ | Giao dịch bù trừ cho LDAP/workflow |
| --- | --- | --- |
| Đơn vị kiểm soát | Transaction do DB engine quản lý trên tài nguyên tham gia. | Chuỗi các bước độc lập, do client/framework/workflow điều phối. |
| Atomicity | Mọi thay đổi trong transaction cùng commit hoặc rollback theo bảo đảm của DB. | Không có atomicity tổng thể: có thể tồn tại trạng thái trung gian trước bù trừ. |
| Consistency | Ràng buộc DB cùng logic nghiệp vụ được thực thi trong transaction. | Phải thiết kế invariant, điều kiện hoàn tác và reconciliation ở cấp ứng dụng. |
| Isolation | DB cung cấp isolation level và cơ chế đồng thời. | Các thao tác LDAP khác có thể quan sát/cập nhật trạng thái trung gian. |
| Durability | Sau commit, thay đổi bền vững theo bảo đảm của DB. | Mỗi bước đã thành công có thể tồn tại bền vững; việc bù trừ là thao tác mới có thể lỗi. |
| Cơ chế rollback | Database khôi phục trạng thái trước transaction theo transaction log/MVCC. | Client chạy thao tác ngược hoặc hành động sửa sai; có thể chỉ phục hồi một phần. |
| Khi tiến trình ứng dụng crash | DB tự xử lý transaction chưa hoàn tất theo cơ chế của nó. | Cần lưu log/checkpoint workflow để khôi phục những bước chưa xử lý. |
| Phạm vi | Những bảng/tài nguyên nằm trong transaction do DB quản lý. | Có thể điều phối LDAP, DB và dịch vụ khác nhưng không bảo đảm một commit nguyên tử chung. |
| Xung đột đồng thời | DB cung cấp lock/MVCC/isolation theo cấu hình. | Cần tự kiểm soát xung đột, xác minh trạng thái và tránh rollback đè thay đổi mới. |
| Thời gian lộ trạng thái trung gian | Phụ thuộc isolation; giao dịch chưa commit thường không hiển thị như dữ liệu đã commit. | Các bước LDAP thành công có thể hiển thị ngay trước khi bù trừ. |
| Cách xác nhận hoàn tất | `COMMIT` thành công theo contract của DB. | Tất cả bước được xác nhận; trạng thái khôi phục phải được theo dõi riêng nếu lỗi. |

Điểm cần nhớ là **giao dịch bù trừ thường hướng tới tính nhất quán cuối cùng** (*eventual consistency*) của workflow; không tạo lại ACID chỉ bằng việc đặt cùng tên “transaction”.

## 6. Tình huống cụ thể: tạo người dùng và cấp membership

Giả sử có:

```text
Base DN  : dc=example,dc=org
User DN  : uid=linh,ou=people,dc=example,dc=org
Group DN : cn=developers,ou=groups,dc=example,dc=org

User: objectClass=inetOrgPerson, uid=linh, cn=Linh Nguyen, sn=Nguyen
Group: objectClass=groupOfNames, member=<DN người dùng>
```

Với `groupOfNames`, thuộc tính `member` chứa DN đầy đủ, không phải nickname hay chỉ `uid`. Schema/ACL và cách xác định group thực tế khác nhau theo sản phẩm LDAP; hệ thống này giả định OU, group và các quyền phù hợp đã được cấu hình.

### 6.1. Phác thảo giao dịch nếu cả hai bảng là SQL

Nếu cùng một relational database lưu `employees` và `memberships`:

```java
@Transactional(transactionManager = "jdbcTransactionManager")
public void createEmployeeInDatabase(Employee employee) {
    employeeRepository.insert(employee);
    membershipRepository.add(employee.id(), "developers");
    // Nếu lời gọi thứ hai ném exception trước commit,
    // transaction manager có thể rollback cả hai thao tác SQL.
}
```

Đoạn trên là **mã minh họa**, giả định hai repository dùng chung tài nguyên transaction của SQL và loại lỗi được cấu hình để kích hoạt rollback. `@Transactional` là cơ chế khai báo ranh giới transaction của Spring; bản thân annotation không quyết định mọi hệ thống bên ngoài sẽ tham gia.

### 6.2. Ví dụ Spring LDAP tự bù trừ ở mức tối thiểu

Sau đây là ví dụ **minh họa cơ chế**, dùng `LdapTemplate` và chỉ bù trừ bước tạo user khi bước thêm vào nhóm thất bại:

```java
package com.example.identity;

import javax.naming.Name;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.BasicAttributes;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;
import org.springframework.stereotype.Service;

@Service
public class DirectoryEnrollmentService {

    private final LdapTemplate ldap;

    public DirectoryEnrollmentService(LdapTemplate ldap) {
        this.ldap = ldap;
    }

    public void enroll(String uid, String commonName, String surname) {
        Name relativeUserDn = LdapNameBuilder.newInstance("ou=people")
            .add("uid", uid)
            .build();
        Name groupDn = LdapNameBuilder.newInstance("ou=groups")
            .add("cn", "developers")
            .build();
        String fullUserDn = LdapNameBuilder
            .newInstance("dc=example,dc=org")
            .add("ou", "people")
            .add("uid", uid)
            .build()
            .toString();

        Attributes attributes = new BasicAttributes(true);
        Attribute classes = new BasicAttribute("objectClass");
        classes.add("top");
        classes.add("person");
        classes.add("organizationalPerson");
        classes.add("inetOrgPerson");
        attributes.put(classes);
        attributes.put("uid", uid);
        attributes.put("cn", commonName);
        attributes.put("sn", surname);

        boolean createAcknowledged = false;
        try {
            // Bước A: tạo người dùng.
            ldap.bind(relativeUserDn, null, attributes);
            createAcknowledged = true;

            // Bước B: thêm DN đầy đủ vào attribute member của nhóm.
            ModificationItem addMember = new ModificationItem(
                DirContext.ADD_ATTRIBUTE,
                new BasicAttribute("member", fullUserDn)
            );
            ldap.modifyAttributes(groupDn, new ModificationItem[] {addMember});

        } catch (RuntimeException originalError) {
            if (createAcknowledged) {
                try {
                    // Bù trừ A nếu B báo lỗi.
                    ldap.unbind(relativeUserDn);
                } catch (RuntimeException compensationError) {
                    originalError.addSuppressed(compensationError);
                }
            }
            throw originalError;
        }
    }
}
```

Ví dụ này chỉ để **hiểu nguyên tắc và giới hạn**. Nó cố ý giữ mã gọn, **chưa đủ tiêu chuẩn production**:

- `createAcknowledged` chỉ được đặt sau khi client nhận phản hồi thành công. Nếu server đã tạo entry nhưng kết nối đứt trước phản hồi, giá trị vẫn là `false`; hệ thống cần kiểm tra trạng thái thực tế trước khi quyết định bù trừ.
- `ldap.modifyAttributes` có thể **đã thực hiện thành công ở server** nhưng client chỉ nhận exception do mất phản hồi. Khi đó, xóa user có thể để lại giá trị `member` tham chiếu đến DN đã xóa. Muốn phục hồi đúng, cần kiểm tra membership và bù trừ nó nếu đã được áp dụng.
- Nếu nhiều request cùng dùng `uid`, không được xóa nhầm entry do người khác tạo trong một cuộc đua đồng thời. Cần cơ chế nhận dạng/correlation và chính sách duy nhất phù hợp.
- Nếu `ldap.unbind` thất bại, exception được gắn `suppressed` để điều tra; hệ thống thực tế phải ghi nhận **công việc bù trừ còn dang dở** trong nơi lưu bền vững và có quy trình retry/reconciliation.
- Không nên chuyển toàn bộ lỗi thành `Optional.empty()` hoặc âm thầm trả thành công. Cần phân biệt xung đột DN, lỗi schema, xác thực, ACL và kết nối.

Đoạn code này dùng base DN của `ContextSource` là `dc=example,dc=org`; vì vậy DN của `bind`/`modifyAttributes`/`unbind` là **DN tương đối**, còn `member` là **giá trị DN đầy đủ** theo schema nhóm.

### 6.3. Mở rộng khi có bước SQL

Nếu bước thứ ba ghi SQL, việc tạo user và thêm membership đã hoàn tất trước đó. Khi SQL thất bại, bù trừ cần chạy **gỡ membership rồi xóa user**; chỉ xóa user là chưa đủ để bảo đảm toàn bộ trạng thái mong muốn.

Một orchestration phù hợp có thể mô tả bằng bảng trạng thái:

| Bước | Hành động tiến | Hành động bù trừ | Trạng thái cần ghi |
| --- | --- | --- | --- |
| A | Tạo LDAP user. | Xóa đúng user do workflow tạo. | `USER_CREATED`. |
| B | Thêm member vào nhóm. | Gỡ đúng DN khỏi nhóm. | `GROUP_UPDATED`. |
| C | Ghi SQL audit/record. | Xóa/đánh dấu đảo nghiệp vụ theo chính sách SQL. | `DB_WRITTEN`. |

Workflow phải lưu được bước nào **đã xác nhận**, bước nào **không rõ kết quả** và bước nào **đã bù trừ**. Khi ứng dụng crash giữa A và B, một cờ Boolean chỉ nằm trong bộ nhớ sẽ không giúp khôi phục.

## 7. Vai trò của Spring @Transactional và transaction manager LDAP

### 7.1. @Transactional không tự biến LDAP thành ACID

Spring hỗ trợ khai báo transaction trên method bằng `@Transactional`, nhưng việc thực thi tùy thuộc **`PlatformTransactionManager` đang được chọn**, những tài nguyên nó quản lý và cách các thao tác truy cập dữ liệu đi qua những abstraction được hỗ trợ.

Nếu ứng dụng chỉ cấu hình transaction manager JDBC/JPA:

```java
@Transactional(transactionManager = "jdbcTransactionManager")
public void register(Registration registration) {
    jdbcRepository.insert(registration);
    ldapRepository.save(registration.toDirectoryPerson());
}
```

Rollback của JDBC có thể đảo các thao tác SQL trong transaction, **không tự động đảo `ldapRepository.save(...)`**. Điều này đúng cả khi cả hai lệnh nằm trong một phương thức Java.

### 7.2. Spring LDAP có hỗ trợ giao dịch bù trừ ở phía client

Spring LDAP có cơ chế **client-side compensating transaction**, được giới thiệu qua các thành phần như `ContextSourceTransactionManager` trong những phiên bản hỗ trợ. Cơ chế này có thể theo dõi một số thao tác LDAP qua hạ tầng `ContextSource` liên quan và chuẩn bị hành động bù trừ khi rollback.

Khi sử dụng, cần kiểm tra tài liệu đúng **phiên bản Spring LDAP của ứng dụng** để xác minh:

- Transaction manager nào đang được khai báo, được `@Transactional` chọn theo tên nào?
- `ContextSource`/`LdapTemplate` và repository có đi qua đúng hạ tầng được transaction manager quản lý không?
- Những loại thao tác LDAP nào được hỗ trợ bù trừ (ví dụ bind/unbind, modify, rename) và có giới hạn gì?
- Bù trừ xóa entry được triển khai thế nào, có dùng tên tạm hoặc snapshot và có thể phục hồi mọi attribute không?
- Khi đồng thời có JDBC/JPA, các bước được điều phối theo thứ tự nào và lỗi ở giai đoạn commit/rollback được báo như thế nào?

Các triển khai/gói API thay đổi theo phiên bản. Không nên sao chép một cấu hình transaction manager của tài liệu cũ rồi giả định nó hỗ trợ mọi phiên bản Spring Data LDAP hiện tại. Dù bật được cơ chế bù trừ của Spring LDAP, **nó vẫn không cung cấp cùng bảo đảm ACID với transaction engine của relational database**.

### 7.3. @Transactional: ngoại lệ và rollback rule

Với Spring transaction thông thường, mặc định các exception kiểu `RuntimeException` và `Error` kích hoạt rollback; checked exception không tự động kích hoạt nếu không cấu hình `rollbackFor`. Tuy nhiên, **quy tắc kích hoạt rollback không nói lên chất lượng bù trừ**.

```java
@Transactional(
    transactionManager = "ldapTransactionManager",
    rollbackFor = Exception.class
)
public void updateDirectory() throws Exception {
    // Chỉ có tác dụng như mong đợi nếu một LDAP transaction manager
    // phù hợp đã được cấu hình và các LDAP operations được quản lý.
}
```

Ở đây `ldapTransactionManager` là **tên bean giả định**, không phải bean Spring Boot luôn tự cung cấp. Không nên đưa chú thích `@Transactional` vào LDAP service rồi kết luận hệ thống đã rollback được mọi entry khi lỗi.

## 8. Khi nào bù trừ có thể thất bại hoặc gây tác dụng phụ?

### 8.1. Không có isolation giống transaction SQL

Giả sử hai workflow cùng sửa `mail` của một entry:

```text
Ban đầu       mail=old@example.org

Workflow A    đọc old; ghi mail=a@example.org
Workflow B    đọc a;   ghi mail=b@example.org
Workflow A    lỗi bước khác; bù trừ bằng mail=old@example.org

Kết quả: B bị mất thay đổi dù B không có lỗi.
```

Nếu A phục hồi snapshot cũ mà không kiểm tra thay đổi mới của B, bù trừ gây **lost update**. Cách hạn chế gồm tuần tự hóa các workflow cùng DN, sử dụng cơ chế kiểm tra phiên bản/điều kiện nếu LDAP server hỗ trợ, hoặc kiểm tra trạng thái hiện tại trước khi restore. Không nên giả định LDAP tự cung cấp isolation ngang với DB transaction.

### 8.2. Mất phản hồi không đồng nghĩa request thất bại

Hai trường hợp có thể tạo cùng loại exception ở client:

1. Network đứt **trước** khi server nhận `Add`: entry chưa được tạo.
2. Network đứt **sau** khi server thực hiện `Add` nhưng **trước** khi client nhận xác nhận: entry đã tồn tại.

Nếu chỉ dựa vào exception để chạy lại `Add`, trường hợp 2 có thể gặp lỗi trùng DN. Nếu mặc định rollback đã làm xong, hệ thống có thể bỏ lại dữ liệu. Vì thế cần thao tác kiểm tra trạng thái sau lỗi với quyền đọc phù hợp, kèm cơ chế lưu workflow ID và tiêu chí nhận dạng dữ liệu đã tạo.

### 8.3. Hoàn tác Delete không chắc tái tạo được entry cũ

Khôi phục entry đã xóa có thể gặp các vấn đề:

- Một số thuộc tính **operational** do server quản lý, không thể ghi lại theo giá trị cũ.
- DN cha đã bị xóa hoặc RDN cũ bị tái sử dụng.
- Schema/ACL thay đổi giữa thời điểm xóa và khôi phục.
- Entry có liên kết với nhóm, hệ thống khác hoặc audit log đã thấy sự kiện xóa.
- Nếu có entry con, thao tác xóa và khôi phục toàn nhánh cần kế hoạch riêng.

Do đó, trong một số quy trình nên ưu tiên **đánh dấu trạng thái vô hiệu hóa**, **di chuyển entry sang vùng tạm** hoặc quy trình chờ xác nhận trước khi xóa cuối cùng, khi schema và yêu cầu bảo mật cho phép. Những cách đó cũng có đánh đổi; không có một chiến lược áp dụng được cho mọi server.

### 8.4. Bù trừ không thể thu hồi mọi tác động đã được quan sát

Một tài khoản được tạo trong directory có thể đã được dịch vụ khác đọc, dùng để đăng nhập, đồng bộ hoặc gửi thông báo. Sau khi xóa tài khoản, các sự kiện và cache đó không tự biến mất. Hệ thống phải định nghĩa rõ **invariant nghiệp vụ** (ví dụ “người dùng thất bại khi đăng ký không còn quyền truy cập”) và kiểm chứng cả các hệ tiêu thụ dữ liệu.

## 9. Thiết kế phục hồi an toàn và có thể vận hành

Một quy trình bù trừ đáng tin cậy cần nhiều hơn `try/catch`:

1. **Định danh workflow duy nhất:** lưu `workflowId`, actor, DN đích và loại thao tác. Hạn chế lưu thuộc tính nhạy cảm không cần thiết.
2. **Ghi trạng thái bền vững:** phân biệt `PENDING`, `APPLIED`, `COMPENSATING`, `COMPENSATED`, `UNKNOWN`, `NEEDS_REVIEW`; mọi chuyển trạng thái cần có dấu thời gian.
3. **Lưu dữ liệu đủ cho compensation:** snapshot có chọn lọc, các DN trước/sau và giá trị attribute sẽ thay đổi; không lưu bind password.
4. **Thiết kế thao tác lặp lại an toàn:** trước khi tạo/xóa/sửa, kiểm tra trạng thái thực tế. Với timeout hoặc mất kết nối, đừng giả định thao tác chưa được thực hiện.
5. **Retry có giới hạn:** backoff và timeout chỉ dành cho lỗi có khả năng tạm thời như giao tiếp hoặc dịch vụ không sẵn sàng; không retry vô hạn với lỗi schema/ACL/credentials.
6. **Reconciliation định kỳ:** so sánh trạng thái workflow với LDAP/SQL; sửa sai lệch hoặc chuyển người vận hành xử lý nếu không thể tự xác định.
7. **Quan sát và cảnh báo:** đếm số bù trừ thất bại, số workflow ở trạng thái `UNKNOWN` và độ trễ phục hồi; ghi log an toàn theo `workflowId`.

Ví dụ bản ghi khái niệm:

```json
{
  "workflowId": "enroll-1042",
  "userDn": "uid=linh,ou=people,dc=example,dc=org",
  "step": "ADD_GROUP_MEMBER",
  "status": "UNKNOWN",
  "nextAction": "VERIFY_LDAP_MEMBERSHIP"
}
```

Khi server báo lỗi kết nối sau bước thêm member, trạng thái `UNKNOWN` là trung thực hơn `FAILED` nếu chưa biết server có hoàn thành thao tác hay chưa. Bộ phục hồi có thể đọc group, xác định DN đã xuất hiện trong `member` hay chưa, rồi thực hiện bước kế tiếp hoặc bù trừ theo quyết định nghiệp vụ.

Đối với luồng giao dịch trải qua LDAP và SQL, có thể triển khai **saga orchestration** để điều phối các bước/compensation. Khi cần phát thông báo từ DB, **transactional outbox** có thể giúp phát sự kiện đáng tin cậy sau commit SQL; outbox tự nó không biến thao tác LDAP thành phần của transaction SQL, nên vẫn cần đối soát.

## 10. Chọn phương án theo yêu cầu thực tế

| Yêu cầu | Cách tiếp cận phù hợp | Vì sao |
| --- | --- | --- |
| Cập nhật nhiều attribute của **cùng một entry** | Một LDAP `ModifyRequest` với nhiều `ModificationItem`. | Tận dụng tính nguyên tử của một Modify theo LDAPv3, giảm bước bù trừ. |
| Chỉ đọc/ghi một entry không kèm hệ thống khác | `LdapTemplate` hoặc Spring Data LDAP repository theo thao tác bình thường. | Không nhất thiết cần workflow bù trừ nhiều bước. |
| Tạo entry và thêm thành viên nhóm | Thiết kế forward/compensation, kiểm tra trạng thái thực tế sau lỗi. | Hai LDAP request không mặc nhiên được commit cùng nhau. |
| Xử lý LDAP và SQL trong một nghiệp vụ | Orchestration bù trừ, workflow lưu bền vững, hoặc thiết kế giảm phụ thuộc đồng thời. | JDBC transaction manager không tự điều khiển rollback LDAP. |
| Muốn dùng cơ chế bù trừ của Spring LDAP | Xác minh transaction manager, phiên bản, operation support và thử lỗi thực. | Tự động hóa compensation chỉ nằm trong phạm vi framework hỗ trợ. |
| Cần yêu cầu atomicity chặt chẽ xuyên nhiều entry | Đánh giá hỗ trợ giao dịch server cụ thể, hoặc thay đổi thiết kế/phân ranh tài nguyên. | Compensation không thể tự cung cấp isolation và atomic commit. |
| Môi trường có cập nhật đồng thời cao | Cơ chế phát hiện xung đột/serialization, kiểm tra trước restore. | Ngăn bù trừ đè thay đổi hợp lệ của workflow khác. |

Quy tắc thiết kế hữu ích là **giảm số bước cần đồng thời thành công**. Ví dụ, nếu schema cho phép, gom nhiều thay đổi thuộc tính của một entry vào một LDAP Modify; tránh tách thành hai request chỉ để thay hai attribute của cùng DN.

## 11. Kiểm thử: chứng minh được cả lỗi và phục hồi

Kiểm thử một bài transaction bù trừ phải tập trung vào **trạng thái còn lại sau các điểm lỗi**, không chỉ việc method có ném exception hay không.

| Ca kiểm thử | Cách tạo tình huống | Điều cần xác nhận |
| --- | --- | --- |
| Luồng thành công | LDAP test có OU/group hợp lệ, DB test sẵn sàng. | User có trong directory, group chứa DN, DB ở trạng thái hoàn tất. |
| Lỗi trước `Add` | Không gửi request đầu tiên. | Không xuất hiện user mới hoặc membership mới. |
| Lỗi khi `Add` bị từ chối | Tạo UID trùng hoặc schema không hợp lệ trong directory test. | Không chạy bước cấp membership; không xóa nhầm entry cũ. |
| Lỗi khi `Modify` group | Bind account thiếu quyền sửa group. | User do workflow tạo được bù trừ hoặc có trạng thái cần phục hồi rõ ràng. |
| Lỗi SQL sau khi đã sửa LDAP | Cho bước ghi DB bị lỗi có chủ đích. | Gỡ membership, xóa user hoặc ghi nhận công việc bù trừ còn dang dở. |
| Mất kết nối sau server đã commit | Fault injection sau thao tác, trước khi trả response. | Workflow kiểm tra trạng thái thực tế trước khi retry/bù trừ. |
| Bù trừ cũng lỗi | Tạm chặn ACL hoặc LDAP server trong bước undo. | Lỗi không bị nuốt; trạng thái `NEEDS_REVIEW`/`UNKNOWN` còn lại để khôi phục. |
| Hai workflow cùng sửa attribute | Chạy A/B xen kẽ, kích hoạt A rollback muộn. | Không ghi đè update hợp lệ của B; phát hiện xung đột. |
| Process crash giữa các bước | Dừng ứng dụng sau khi một bước thành công. | Sau khởi động lại, journal/recovery có thể tiếp tục hoặc bù trừ. |

**Phân biệt unit test và integration test:** unit test với mock có thể kiểm tra **thứ tự gọi** và **quyết định bù trừ**, nhưng không chứng minh LDAP server bảo đảm atomic Modify, chuyển mã lỗi, áp schema/ACL hay xử lý rename đúng như mong muốn. Cần LDAP server thử nghiệm (embedded hoặc container) và DB test để xác minh trạng thái sau các kịch bản.

Kiểm thử chỉ được chạy trên dữ liệu giả định và environment tách biệt. Không thực hiện kịch bản phá kết nối, xóa entry hay thay đổi quyền trên directory sản xuất.

## 12. Những nhầm lẫn thường gặp

| Nhận định sai | Cách hiểu đúng |
| --- | --- |
| “LDAP không có atomicity.” | Một LDAP ModifyRequest theo LDAPv3 có tính nguyên tử; giới hạn là **không có atomicity mặc định giữa nhiều request**. |
| “Có `@Transactional` thì LDAP rollback giống SQL.” | Annotation chỉ hoạt động trong phạm vi transaction manager và tài nguyên được quản lý. |
| “Bù trừ chính là rollback của DB.” | Bù trừ phát thao tác mới, có thể thất bại, bị quan sát và đụng dữ liệu đồng thời. |
| “Lỗi timeout nghĩa là thao tác chưa thực hiện.” | Server có thể đã hoàn thành request trước khi mất phản hồi. |
| “Delete rồi tạo lại entry sẽ chắc chắn giống hệt.” | Schema, DN, thuộc tính operational, ACL và hệ thống phụ thuộc có thể thay đổi. |
| “Chạy lại `Add` luôn an toàn.” | Có thể gặp DN trùng hoặc tạo xung đột; phải kiểm tra trạng thái trước retry. |
| “Nếu bù trừ thất bại, chỉ cần bỏ qua.” | Cần trạng thái phục hồi bền vững, cảnh báo và reconciliation. |
| “SQL và LDAP ở cùng một method là cùng một transaction.” | Hai hệ cần cơ chế phối hợp rõ ràng; transaction manager SQL không tự bao phủ LDAP. |
| “Khôi phục snapshot luôn an toàn.” | Có thể ghi đè thay đổi mới do request khác thực hiện sau snapshot. |

## 13. Bài tập tự luyện

1. Đặt cạnh nhau chuỗi SQL `BEGIN → INSERT A → INSERT B → ROLLBACK` và chuỗi LDAP `Add A → Modify B → bù trừ`. Chỉ ra thời điểm dữ liệu trung gian có thể được client khác quan sát.
2. Với việc cấp quyền nhóm cho người dùng, lập bảng **forward action**, **compensating action**, dữ liệu cần lưu và trạng thái `UNKNOWN` cần kiểm tra lại.
3. Dựa vào RFC 4511, giải thích vì sao một `ModifyRequest` có hai thay đổi trên cùng entry khác với hai lời gọi `modifyAttributes` riêng biệt.
4. Một `ldapTemplate.bind(...)` ném `CommunicationException`; sau đó tra cứu thấy entry đã tồn tại. Có đủ dữ kiện để xóa entry không? Cần xác minh điều gì trước?
5. Workflow A đổi `mail` từ `old` sang `a`; workflow B đổi từ `a` sang `b`; A thất bại. Đề xuất chiến lược tránh A rollback đè lên B.
6. Thiết kế một integration test gây lỗi ở bước SQL sau khi LDAP đã cấp membership. Viết tiêu chí xác nhận directory đã được bù trừ hoặc workflow đã ghi nhận yêu cầu reconciliation.
7. Một ứng dụng chỉ cấu hình `DataSourceTransactionManager` và gọi repository LDAP trong `@Transactional`. Giải thích phần dữ liệu nào được đảm bảo rollback và phần nào không.

## 14. Tài liệu tham khảo

- [Spring LDAP Reference Documentation](https://docs.spring.io/spring-ldap/reference/): `LdapTemplate`, `ContextSource`, thao tác directory và phần transaction support theo phiên bản.
- [Spring Data LDAP Reference Documentation](https://docs.spring.io/spring-data/ldap/reference/): repository, ODM, CRUD và truy vấn LDAP.
- [Spring Framework — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html): `@Transactional`, transaction manager, rollback rule và phạm vi tài nguyên.
- [RFC 4511 — Lightweight Directory Access Protocol (LDAP): The Protocol](https://www.rfc-editor.org/rfc/rfc4511): thao tác LDAP và tính nguyên tử của ModifyRequest.
- [RFC 5805 — Lightweight Directory Access Protocol (LDAP) Transactions](https://www.rfc-editor.org/rfc/rfc5805): mở rộng LDAP Transactions tùy chọn; không đồng nhất với giao dịch bù trừ.
- [RFC 4512 — LDAP Directory Information Models](https://www.rfc-editor.org/rfc/rfc4512): mô hình entry, DN, attribute và schema.
