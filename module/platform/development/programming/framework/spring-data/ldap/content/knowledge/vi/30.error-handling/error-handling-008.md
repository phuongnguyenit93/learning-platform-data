# Timeout sau khi gửi thao tác ghi và trạng thái không chắc chắn

Một ứng dụng Spring Data LDAP gửi yêu cầu tạo người dùng, cập nhật thuộc tính, xóa entry hoặc đổi DN. LDAP server có thể đã thực hiện thay đổi, nhưng kết nối bị ngắt trước khi client nhận được response. Ứng dụng nhìn thấy timeout và thường muốn thử lại ngay. Đây là một trong những tình huống nguy hiểm nhất khi ghi dữ liệu vào directory: **client không biết thao tác đã được áp dụng hay chưa**.

Theo RFC 4511, khi transport connection bị đóng, server có thể hủy operation chưa hoàn tất nếu có thể, hoặc hoàn tất operation nhưng không gửi response. Client **không được giả định update operation đã thành công hoặc thất bại** chỉ vì kết nối bị đóng. Với LDAP Modify, RFC còn quy định danh sách thay đổi trong một ModifyRequest được áp dụng nguyên tử; nếu nhận response lỗi thì không thay đổi nào được áp dụng, nếu nhận success thì toàn bộ thay đổi đã áp dụng. Nhưng nếu không nhận response, trạng thái vẫn không xác định. [RFC 4511](https://www.rfc-editor.org/rfc/rfc4511.html)

Bài thuộc chương **Xử lý lỗi** của mô-đun `SPRING_DATA_LDAP`. Ta sẽ phân biệt timeout kết nối với timeout chờ response, mô hình hóa trạng thái ghi, đối soát sau timeout theo từng loại thao tác, thiết kế retry an toàn, sử dụng `LdapTemplate`/JNDI, kiểm soát đồng thời và kiểm thử lỗi mạng.

> **Nguyên tắc cốt lõi:** timeout sau khi gửi write request không chứng minh server đã rollback. Đánh dấu operation là **UNKNOWN**, đối soát trạng thái directory bằng định danh ổn định và chỉ retry khi đã chứng minh được hành động tiếp theo an toàn.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vì sao client có thể mất response sau khi LDAP server đã thực hiện Add, Modify, Delete hoặc ModifyDN.
2. Phân biệt `connect timeout`, `read timeout`, LDAP result code và HTTP request timeout.
3. Phân biệt ba kết quả `CONFIRMED_APPLIED`, `CONFIRMED_REJECTED` và `UNKNOWN`.
4. Hiểu tính nguyên tử của một LDAP ModifyRequest và giới hạn của một workflow gồm nhiều LDAP request.
5. Chọn cách đối soát riêng cho Add, Modify, Delete, Rename/Move và đổi mật khẩu.
6. Dùng DN và định danh bất biến để xác minh entry sau khi mất response.
7. Thiết kế idempotency key, operation journal và quy trình reconciliation.
8. Hiểu khi nào `replace` có thể được gửi lại, vì sao `add`/`delete` theo giá trị không phải lúc nào cũng an toàn.
9. Dùng Assertion Control để bảo vệ cập nhật có điều kiện khi server hỗ trợ.
10. Cấu hình JNDI connect/read timeout và hiểu giới hạn của việc hủy request.
11. Tránh retry mù qua `@Retryable` hoặc HTTP client.
12. Viết integration test mô phỏng proxy chuyển request tới LDAP nhưng làm rơi response.

## 2. Kịch bản: write đã tới server, response bị mất

Giả sử ứng dụng cần tạo entry nhân viên Lan:

~~~text
DN:
uid=lan,ou=people,dc=example,dc=org

Thuộc tính:
objectClass = inetOrgPerson
uid         = lan
cn          = Nguyen Thi Lan
sn          = Nguyen
mail        = lan@example.org
~~~

Luồng mạng có thể xảy ra:

~~~mermaid
sequenceDiagram
    participant App as Spring application
    participant Net as Network / proxy
    participant LDAP as LDAP server
    App->>Net: AddRequest(uid=lan,...)
    Net->>LDAP: Chuyển AddRequest
    LDAP->>LDAP: Kiểm tra schema và ghi entry
    LDAP-->>Net: AddResponse(success)
    Note over Net: Response bị mất trên đường về
    Net--xApp: Không nhận được response
    Note over App: Read timeout / CommunicationException
~~~

Ứng dụng chỉ quan sát được một lỗi truyền thông. Có ít nhất hai khả năng:

- **Khả năng A:** server chưa thực hiện write, hoặc operation bị hủy trước khi commit.
- **Khả năng B:** server đã commit write nhưng response bị mất.

Một khả năng khác là operation vẫn đang được server xử lý khi client hết thời gian chờ. Vì vậy, ngay cả việc đọc lại ngay lập tức cũng cần được thực hiện có kiểm soát.

### Điều gì sai khi retry ngay?

~~~text
Lần 1: Add uid=lan
Server: đã tạo entry
Client: timeout, không nhận response

Lần 2: Add uid=lan
Server: entry đã tồn tại
Client: nhận entryAlreadyExists (68)
~~~

Nếu ứng dụng coi lần hai là thất bại, người dùng có thể nhận thông báo sai dù entry đã được tạo. Nếu ứng dụng dùng `rebind` để “thử lại”, entry hiện có có thể bị xóa và tạo lại với dữ liệu khác.

**Retry không phải là rollback.** Nó là một operation mới có thể gặp một trạng thái directory đã thay đổi.

## 3. Mô hình trạng thái của một write operation

Không nên biểu diễn một write chỉ bằng boolean `success`/`failed`. Hãy phân biệt kết quả đã được xác nhận với kết quả chưa biết.

| Trạng thái | Ý nghĩa | Hành động tiếp theo |
| --- | --- | --- |
| `PREPARED` | Đã ghi nhận ý định, chưa bắt đầu gửi LDAP request. | Có thể dispatch theo policy. |
| `DISPATCHING` | Ứng dụng đã bắt đầu gửi request; chưa lưu response cuối. | Nếu process chết, xem như cần reconciliation. |
| `CONFIRMED_APPLIED` | Đã nhận LDAP success response. | Ghi nhận hoàn tất. |
| `CONFIRMED_REJECTED` | Đã nhận LDAP error response xác định operation thất bại. | Xử lý lỗi nghiệp vụ hoặc sửa request. |
| `UNKNOWN` | Request có thể đã được áp dụng nhưng client không có response xác nhận. | Đối soát; không retry mù. |
| `RECONCILED_APPLIED` | Đã xác minh trạng thái mong muốn hiện diện. | Hoàn tất operation theo policy. |
| `RECONCILED_NOT_APPLIED` | Đã xác minh operation chưa được áp dụng và không còn đang xử lý. | Có thể lập kế hoạch retry mới. |
| `CONFLICT` | Trạng thái thực tế khác cả trạng thái trước và trạng thái mong muốn. | Dừng tự động, xử lý xung đột. |

~~~mermaid
stateDiagram-v2
    [*] --> PREPARED
    PREPARED --> DISPATCHING
    DISPATCHING --> CONFIRMED_APPLIED: LDAP success response
    DISPATCHING --> CONFIRMED_REJECTED: LDAP error response
    DISPATCHING --> UNKNOWN: response lost / timeout
    UNKNOWN --> RECONCILED_APPLIED: desired state verified
    UNKNOWN --> RECONCILED_NOT_APPLIED: old state verified after operation settled
    UNKNOWN --> CONFLICT: unexpected state / identity mismatch
    RECONCILED_NOT_APPLIED --> PREPARED: explicit retry decision
    CONFIRMED_APPLIED --> [*]
    CONFIRMED_REJECTED --> [*]
    RECONCILED_APPLIED --> [*]
    CONFLICT --> [*]
~~~

`UNKNOWN` không phải lỗi để bỏ qua. Đây là một kết quả nghiệp vụ riêng, cần được lưu lại để hệ thống biết phải đối soát.

### Ba khái niệm không nên đánh đồng

- **LDAP response success:** server đã xác nhận operation thành công.
- **Client timeout:** client không nhận response đúng hạn.
- **Operation failed:** có bằng chứng operation không được áp dụng.

Timeout chỉ chứng minh client không nhận được response trong khoảng thời gian đã cấu hình. Nó không chứng minh operation failed.

## 4. Phân biệt connect timeout và read timeout

Hai timeout quan trọng của JNDI LDAP provider:

| Cấu hình | Thời điểm | Ý nghĩa |
| --- | --- | --- |
| `com.sun.jndi.ldap.connect.timeout` | Khi tạo kết nối TCP tới LDAP endpoint | Giới hạn thời gian chờ thiết lập kết nối. |
| `com.sun.jndi.ldap.read.timeout` | Sau khi kết nối đã được thiết lập, khi chờ LDAP response | Giới hạn thời gian chờ server trả response cho operation. |

Oracle JNDI mô tả `read.timeout` tính bằng **mili giây**. Nếu provider không nhận được LDAP response trong thời gian đó, nó hủy lần đọc phía client. Nếu không cấu hình, mặc định provider có thể chờ cho tới khi nhận response hoặc TCP timeout. [Oracle JNDI read timeout](https://docs.oracle.com/javase/tutorial/jndi/newstuff/readtimeout.html)

### 4.1. Connect timeout

Nếu client không thiết lập được kết nối tới server, request write chưa thể được gửi qua kết nối đó. Đây thường là trường hợp có thể kết luận operation chưa được gửi **trên lần kết nối thất bại đó**.

Tuy nhiên, cần xét toàn bộ kiến trúc:

- ContextSource có nhiều LDAP URL và thử endpoint khác nhau.
- Một request có thể đã được gửi qua connection trước đó trong workflow.
- Lỗi xảy ra khi Bind, không nhất thiết ở bước TCP connect.
- Client có thể retry nội bộ hoặc qua proxy.

Chỉ đánh dấu `NOT_SENT` khi ứng dụng biết chắc chưa gửi write request.

### 4.2. Read timeout sau khi gửi request

Khi TCP connection đã hoạt động và client chờ response, server có thể đã nhận request. Nếu `read.timeout` hết hạn, client ngừng chờ; operation có thể đã hoàn thành hoặc chưa.

Ví dụ:

~~~yaml
spring:
  ldap:
    urls: ldaps://ldap.example.org:636
    base: dc=example,dc=org
    base-environment:
      "[com.sun.jndi.ldap.connect.timeout]": "2000"
      "[com.sun.jndi.ldap.read.timeout]": "5000"
~~~

Đây là cấu hình JNDI environment cho Spring Boot LDAP auto-configuration. Nếu ứng dụng tự tạo `LdapContextSource` bằng JavaConfig, phải bảo đảm các environment property được đặt trên đúng bean thực tế. Không giả định cấu hình `spring.ldap` sẽ tự áp dụng cho một ContextSource tùy chỉnh không sử dụng auto-configuration.

Tùy JNDI provider và cách Spring LDAP dịch lỗi, timeout có thể xuất hiện dưới dạng `javax.naming.CommunicationException`/`org.springframework.ldap.CommunicationException` hoặc một exception khác có root cause là socket timeout. Không chỉ dựa vào tên lớp bên ngoài; giữ cause chain và nếu không xác định chắc chắn server đã từ chối request, hãy để operation ở `UNKNOWN`.

### 4.3. Search time limit không phải write timeout

`LdapQueryBuilder.timeLimit(...)` và `SearchControls.setTimeLimit(...)` kiểm soát Search. Chúng không phải deadline tổng cho Add, Modify, Delete hay ModifyDN.

`com.sun.jndi.ldap.read.timeout` là timeout đọc response ở JNDI provider, nên có thể tác động tới nhiều loại LDAP operation, bao gồm write. Vẫn cần giới hạn tổng thời gian của workflow ở application layer.

### 4.4. Timeout không hủy chắc chắn operation phía server

Một HTTP request hết hạn, thread Java bị interrupt hoặc future bị cancel không đồng nghĩa LDAP server đã rollback write.

LDAP có `AbandonRequest` để client yêu cầu server bỏ một operation, nhưng Abandon không có response xác nhận hoàn tất; client vẫn không có bằng chứng chắc chắn rằng operation chưa được áp dụng. Việc đóng transport cũng không bảo đảm mọi server có thể dừng operation đúng lúc. [RFC 4511](https://www.rfc-editor.org/rfc/rfc4511.html)

## 5. LDAP response cho biết điều gì?

Một operation LDAP thường có response mang result code. Nếu client nhận được response cuối, nó có thể phân loại kết quả theo ngữ nghĩa của operation.

| Response nhận được | Trạng thái có thể ghi nhận |
| --- | --- |
| `success (0)` | `CONFIRMED_APPLIED`. |
| `entryAlreadyExists (68)` cho Add | `CONFIRMED_REJECTED` cho lần Add này; cần đối soát nếu đây là retry của một operation trước đó. |
| `noSuchObject (32)` cho Delete/Modify | `CONFIRMED_REJECTED` cho request hiện tại, theo response server. |
| `insufficientAccessRights (50)` | `CONFIRMED_REJECTED` do quyền. |
| `constraintViolation (19)` / `objectClassViolation (65)` | `CONFIRMED_REJECTED` do dữ liệu/schema/policy. |
| Không nhận LDAP response cuối | `UNKNOWN` nếu request có thể đã được gửi. |

Với ModifyRequest, RFC 4511 Section 4.6 yêu cầu danh sách các modification trong **một request** được áp dụng nguyên tử. Nếu nhận error response thì không modification nào được áp dụng; nếu nhận success response thì tất cả đã được áp dụng. Nếu không nhận response, client không thể xác định trạng thái. [RFC 4511, Section 4.6](https://www.rfc-editor.org/rfc/rfc4511.html#section-4.6)

### Result code không thay thế operation journal

`LDAP messageID` chỉ dùng tương quan request/response trong một LDAP session. Nó không phải idempotency key bền vững của ứng dụng và không thể dùng để tra cứu kết quả sau khi process hoặc connection đã mất.

Ứng dụng cần một `operationId` riêng để theo dõi write qua nhiều request, restart và reconciliation.

## 6. Quy tắc chung khi gặp UNKNOWN

Khi nhận timeout hoặc lỗi truyền thông sau khi write có thể đã được gửi:

1. Ghi trạng thái `UNKNOWN` cùng `operationId`.
2. Không tự retry ngay.
3. Xác định đúng LDAP server/DC đã nhận request nếu có thể.
4. Kết nối lại và đọc trạng thái bằng cùng endpoint có thẩm quyền.
5. So sánh entry với **định danh ổn định** và trạng thái mong muốn.
6. Nếu trạng thái khớp, ghi `RECONCILED_APPLIED`.
7. Nếu trạng thái cũ vẫn còn sau khi operation đã ổn định và không còn xử lý, có thể đánh dấu `RECONCILED_NOT_APPLIED`.
8. Nếu trạng thái khác dự kiến, ghi `CONFLICT` và yêu cầu xử lý.
9. Nếu chưa đủ bằng chứng, tiếp tục giữ `UNKNOWN`.

~~~mermaid
flowchart TD
    A["Write request đã gửi"] --> B{"Nhận LDAP response cuối?"}
    B -->|Success| C["CONFIRMED_APPLIED"]
    B -->|LDAP error| D["CONFIRMED_REJECTED"]
    B -->|Không / timeout| E["UNKNOWN"]
    E --> F["Đối soát cùng LDAP server/DC"]
    F --> G{"Trạng thái thực tế"}
    G -->|Khớp trạng thái mong muốn| H["RECONCILED_APPLIED"]
    G -->|Khớp trạng thái cũ, operation đã settle| I["RECONCILED_NOT_APPLIED"]
    G -->|Khác / có xung đột| J["CONFLICT"]
    G -->|Chưa đủ bằng chứng| E
~~~

### Vì sao cần đọc lại cùng server?

Trong môi trường nhiều LDAP server hoặc Active Directory domain controller:

- Write có thể được gửi tới DC A.
- Read-after-timeout có thể được load balancer chuyển tới DC B.
- Replication giữa A và B có thể chưa hoàn tất.
- DC B chưa thấy thay đổi không chứng minh DC A chưa áp dụng.

Đối soát nên dùng endpoint đã thực hiện write hoặc một nguồn có tính nhất quán phù hợp. Không kết luận `RECONCILED_NOT_APPLIED` chỉ vì một replica chưa nhìn thấy entry.

## 7. Xây operation journal trước khi ghi LDAP

Một workflow quan trọng nên lưu một bản ghi bền vững về ý định write trước khi gửi request.

Ví dụ các trường:

| Trường | Mục đích |
| --- | --- |
| `operationId` | UUID duy nhất cho lần yêu cầu nghiệp vụ. |
| `operationType` | ADD, MODIFY, DELETE, MODIFY_DN, PASSWORD_MODIFY. |
| `targetKey` | UID hoặc định danh ổn định, không chỉ DN có thể thay đổi. |
| `targetDn` | DN mục tiêu đã được service xác minh. |
| `payloadHash` | Hash của dữ liệu mong muốn, không lưu password. |
| `status` | PREPARED, DISPATCHING, UNKNOWN, APPLIED, REJECTED, CONFLICT. |
| `ldapEndpoint` | Server/DC đã gửi write, nếu hệ thống có thể xác định. |
| `createdAt` / `updatedAt` | Thời điểm tạo và cập nhật. |
| `attemptCount` | Số lần dispatch/reconcile. |
| `lastErrorType` | Loại lỗi kỹ thuật, không chứa secret. |

### Thứ tự lưu trạng thái

~~~text
1. Commit operation journal = PREPARED
2. Cập nhật journal = DISPATCHING
3. Gửi LDAP write
4a. Nhận success -> journal = CONFIRMED_APPLIED
4b. Nhận response lỗi -> journal = CONFIRMED_REJECTED
4c. Mất response -> journal = UNKNOWN
~~~

Nếu process chết sau bước 2 nhưng trước khi gửi request, journal còn `DISPATCHING`. Recovery worker phải coi đây là **chưa rõ đã gửi hay chưa**, trừ khi kiến trúc dispatch có bằng chứng đáng tin rằng request chưa rời process.

Không lưu mật khẩu LDAP hoặc password mới vào operation journal. `payloadHash` cũng không nên là hash dễ dò của password; password operation cần metadata riêng không chứa credential.

### Idempotency key từ HTTP client

Với endpoint nhận header `Idempotency-Key`, service có thể ánh xạ key đó vào operation journal:

~~~http
POST /api/v1/people
Idempotency-Key: 5e51b0a7-6a4c-4e4d-8a0f-8c7c7b3e25b1
Content-Type: application/json
~~~

Nếu client gửi lại cùng key:

- Trả trạng thái của operation cũ.
- Không dispatch write mới khi operation cũ đang `UNKNOWN`.
- Từ chối nếu key đã được dùng với payload khác.
- Chỉ tạo operation mới khi key mới hoặc policy cho phép sau reconciliation.

LDAP protocol không tự cung cấp idempotency key tổng quát cho Add/Modify/Delete. Header HTTP chỉ có tác dụng nếu ứng dụng lưu và thực thi policy đó một cách bền vững.

## 8. Đối soát sau timeout theo từng loại thao tác

Không có một cách đọc lại duy nhất phù hợp với mọi LDAP write.

| Operation | Trạng thái cần kiểm tra | Rủi ro khi retry |
| --- | --- | --- |
| Add | DN đã tồn tại chưa? Entry có đúng immutable ID và payload dự kiến không? | Duplicate DN hoặc ghi đè sai đối tượng. |
| Modify | Attribute hiện tại có khớp desired state không? Version có đổi không? | Ghi đè thay đổi đồng thời hoặc add/delete value bị lặp. |
| Delete | Entry còn tồn tại không? Nếu có, có đúng object ban đầu không? | Xóa nhầm entry mới được tạo lại cùng DN. |
| ModifyDN | Entry nằm ở DN cũ hay DN mới? Stable ID có trùng không? | Rename lần hai, conflict DN hoặc move nhầm object. |
| Password Modify | Có thể xác minh bằng Bind theo chính sách an toàn không? | Đổi lặp, lockout hoặc không biết credential hiện tại. |

### Trạng thái mong muốn khác với lịch sử thao tác

Nếu một entry đã không còn tồn tại sau Delete timeout, ứng dụng có thể kết luận **trạng thái mong muốn “entry vắng mặt” đã đạt**. Nhưng không phải lúc nào cũng chứng minh được chính request vừa gửi là nguyên nhân: entry có thể đã bị xóa trước đó hoặc bởi actor khác.

Nếu audit cần biết chính xác actor nào xóa, phải kết hợp operation journal, server audit log hoặc metadata có thể đối chiếu. Chỉ nhìn thấy DN vắng mặt không đủ để chứng minh quan hệ nhân quả.

## 9. Add: dùng DN ổn định và so sánh entry

Ví dụ tạo người dùng:

~~~java
Name dn = LdapNameBuilder.newInstance("ou=people")
        .add("uid", validatedUid)
        .build();

Attributes attrs = new BasicAttributes(true);
Attribute objectClass = new BasicAttribute("objectClass");
objectClass.add("top");
objectClass.add("person");
objectClass.add("organizationalPerson");
objectClass.add("inetOrgPerson");

attrs.put(objectClass);
attrs.put("uid", validatedUid);
attrs.put("cn", displayName);
attrs.put("sn", surname);
attrs.put("mail", email);

ldapTemplate.bind(dn, null, attrs);
~~~

Nếu response bị mất, đối soát bằng DN đó:

1. Lookup DN trên cùng LDAP endpoint/DC.
2. Đọc `uid` và một định danh nghiệp vụ bất biến đã được schema chấp nhận, ví dụ `employeeNumber` hoặc custom immutable ID.
3. So sánh với dữ liệu mong muốn của operation.
4. Nếu entry khớp định danh và payload theo policy, ghi `RECONCILED_APPLIED`.
5. Nếu DN đã có nhưng định danh khác, ghi `CONFLICT`; không rebind.
6. Nếu entry chưa thấy, kiểm tra lại có giới hạn và xác định operation cũ đã settle trước khi dispatch Add mới.

### DN ổn định giúp gì?

Nếu mỗi lần retry tạo DN ngẫu nhiên mới, ứng dụng có thể tạo hai entry cho cùng một nhân viên. DN deterministic theo một UID duy nhất giúp server từ chối Add trùng và cho phép đối soát một mục tiêu cố định.

Tuy nhiên, `entryAlreadyExists` sau một lần retry không tự chứng minh entry đó được tạo bởi operation ban đầu. Phải đọc và so sánh stable ID/payload.

### Không dùng rebind để retry Add

`LdapTemplate.rebind` về cơ bản là remove rồi create lại entry. Dùng nó sau timeout có thể thay thế entry đã được tạo thành công, làm mất thuộc tính hoặc ảnh hưởng các tham chiếu. Với thao tác create, dùng `bind` và reconciliation rõ ràng.

## 10. Modify: atomic trong một request, không atomic với workflow

Spring LDAP có thể gửi nhiều thay đổi thuộc tính trong một ModifyRequest:

~~~java
ModificationItem[] changes = {
    new ModificationItem(
        DirContext.REPLACE_ATTRIBUTE,
        new BasicAttribute("title", "Senior Developer")),
    new ModificationItem(
        DirContext.REPLACE_ATTRIBUTE,
        new BasicAttribute("mail", "lan@example.org"))
};

ldapTemplate.modifyAttributes(dn, changes);
~~~

Theo RFC 4511 Section 4.6, danh sách modification trong một ModifyRequest được áp dụng nguyên tử. Nếu nhận error response, không modification nào trong request được áp dụng; nếu nhận success, toàn bộ được áp dụng. Nhưng khi mất response, client vẫn không biết request đã hoàn tất hay chưa.

### 10.1. Replace thường dễ retry hơn Add/Delete value

| LDAP modification | Tính chất khi gửi lại | Cần lưu ý |
| --- | --- | --- |
| `REPLACE_ATTRIBUTE` với một giá trị tuyệt đối | Thường idempotent về desired state | Có thể ghi đè thay đổi mới của actor khác. |
| `ADD_ATTRIBUTE` với một giá trị | Có thể lỗi `attributeOrValueExists` khi giá trị đã được thêm | Phải đối soát membership/value trước. |
| `REMOVE_ATTRIBUTE` với một giá trị | Có thể lỗi `noSuchAttribute` nếu giá trị đã bị xóa | Không tự coi lỗi lần hai là lỗi nghiệp vụ mới. |
| `REMOVE_ATTRIBUTE` toàn attribute | Có thể đạt trạng thái absent sau lần đầu | Phải kiểm tra schema/required attribute. |

`Replace` không tự giải quyết race condition. Ví dụ một request khác vừa thay `title` thành `Principal Engineer`; retry Replace của operation cũ có thể ghi đè giá trị mới thành `Senior Developer`.

### 10.2. Đối soát Modify

Sau timeout:

- Đọc các attribute liên quan.
- So sánh với desired state của operation.
- Nếu tất cả khớp và không có xung đột theo policy, ghi `RECONCILED_APPLIED`.
- Nếu vẫn là trạng thái cũ, chỉ retry sau khi operation cũ đã settle và điều kiện concurrency vẫn hợp lệ.
- Nếu giá trị khác cả cũ và mới, ghi `CONFLICT` và không ghi đè tự động.

### 10.3. Assertion Control cho cập nhật có điều kiện

LDAP Assertion Control (RFC 4528) cho phép gắn một filter điều kiện vào update operation. Server chỉ thực hiện operation nếu điều kiện trên entry đích vẫn đúng; nếu filter false hoặc undefined, server trả `assertionFailed (122)` và không thực hiện operation. Control có thể hỗ trợ thao tác kiểu test-and-set/test-and-clear. [RFC 4528](https://www.rfc-editor.org/rfc/rfc4528.html)

Ví dụ ý tưởng:

~~~text
Target DN:
uid=lan,ou=people,dc=example,dc=org

Assertion:
(modifyTimestamp=20261126123000Z)

Modify:
REPLACE title = Senior Developer
~~~

Đây là sơ đồ khái niệm, không phải cú pháp filter/attribute phù hợp với mọi server. `modifyTimestamp` có format và semantics theo schema/server; cần chọn version token đáng tin cậy, kiểm tra server hỗ trợ Assertion Control và gửi control qua API JNDI/Spring LDAP phù hợp.

Assertion Control bảo vệ cập nhật khỏi ghi đè trạng thái đã thay đổi. Nó **không** tự cho biết operation trước đó có thành công hay không khi response bị mất; vẫn phải reconciliation.

## 11. Delete: kiểm tra absence nhưng không xóa nhầm object mới

Ví dụ:

~~~java
ldapTemplate.unbind(dn);
~~~

Sau timeout, lookup DN có thể cho ba kết quả:

| Kết quả đọc lại | Cách hiểu |
| --- | --- |
| DN không còn tồn tại | Desired state “entry vắng mặt” có thể đã đạt; kiểm tra audit/precondition nếu cần biết chính xác ai xóa. |
| DN còn tồn tại, stable ID vẫn giống entry cũ | Delete có thể chưa được áp dụng hoặc operation chưa settle; tiếp tục đối soát. |
| DN còn tồn tại nhưng stable ID khác | Có object mới được tạo lại tại DN đó; không retry Delete lên object mới. |

Không chỉ kiểm tra `NameNotFoundException` rồi kết luận request ban đầu chắc chắn đã xóa entry. Một actor khác có thể đã xóa trước hoặc trong cùng thời gian.

### Delete theo trạng thái mong muốn

Nếu hợp đồng nghiệp vụ chỉ yêu cầu “đảm bảo entry này không còn”, Delete có thể được thiết kế idempotent:

- Entry vắng mặt: trạng thái mong muốn đã đạt.
- Entry còn đúng stable ID: sau khi operation trước đã settle, có thể quyết định retry.
- DN được tái sử dụng cho object khác: conflict; không xóa.

Với dữ liệu có giá trị, dùng stable ID như `entryUUID` (nếu server cung cấp) hoặc `objectGUID` (Active Directory), không dựa duy nhất vào DN có thể đổi hoặc được tái sử dụng.

## 12. ModifyDN: đối soát cả DN cũ và DN mới

Spring LDAP có method:

~~~java
ldapTemplate.rename(oldDn, newDn);
~~~

Nếu timeout sau khi gửi ModifyDNRequest, cần kiểm tra cả hai DN.

~~~text
Trước:
uid=lan,ou=people,dc=example,dc=org

Sau:
uid=lan.nguyen,ou=people,dc=example,dc=org
~~~

| DN cũ | DN mới | Cách xử lý |
| --- | --- | --- |
| Không có | Có, stable ID khớp | Có bằng chứng entry đã chuyển tới DN mới. |
| Có, stable ID khớp | Không có | Có thể chưa áp dụng; chờ operation settle và kiểm tra lại trước retry. |
| Có | Có | Có thể là hai object khác nhau hoặc trạng thái xung đột; dừng tự động. |
| Không có | Không có | Chưa xác định; kiểm tra server/DC, parent DN và replication. |

Nếu rename đồng thời thay RDN, server có thể thay đổi giá trị attribute tương ứng theo semantics của ModifyDN và cờ `deleteOldRDN`. Khi đối soát, không chỉ so DN; phải so stable object ID và các thuộc tính được mong đợi.

Nếu move entry sang OU khác, kiểm tra ACL và quyền ở cả vùng nguồn/đích. Không retry rename vào một DN mới đã được một object khác chiếm.

## 13. Đổi mật khẩu: không thể đọc lại secret để xác nhận

Đổi mật khẩu LDAP có thể dùng Password Modify Extended Operation (RFC 3062) nếu server hỗ trợ. RFC này định nghĩa request chứa user identity, old password và new password; server chỉ trả success khi thay đổi mật khẩu thành công. Operation yêu cầu bảo vệ confidentiality/integrity như TLS và không được dùng anonymous. [RFC 3062](https://www.rfc-editor.org/rfc/rfc3062.html)

Nếu client mất response:

- Không thể đọc password hash/secret để so sánh như một attribute thông thường.
- Không retry mù với mật khẩu cũ/mới.
- Có thể xác minh bằng Bind thử với mật khẩu mới nếu policy cho phép, nhưng phải kiểm soát lockout, rate limit và việc xác minh có tạo thêm side effect hay không.
- Nếu Bind mới thành công, đó là bằng chứng credential mới hoạt động tại thời điểm kiểm tra; vẫn cần xét replication và password policy.
- Nếu Bind mới thất bại, không chắc password chưa đổi: endpoint có thể là replica chưa nhận replication, hoặc account bị lock/credential bị đổi tiếp.

Với Active Directory, đổi password có quy tắc riêng về `unicodePwd`, quyền và TLS; không sao chép cách ghi `userPassword` của OpenLDAP sang AD. Cần dùng API/thư viện hỗ trợ đúng server và kiểm thử theo chính sách mật khẩu thực tế.

## 14. Ví dụ service ghi có operation journal

Ví dụ sau minh họa một luồng Add có trạng thái rõ ràng. `OperationJournal` là adapter lưu bền vững (ví dụ database); đây là interface ứng dụng, không phải API Spring LDAP.

~~~java
package com.example.directory.service;

import java.util.UUID;
import java.util.Base64;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;

import javax.naming.Name;
import javax.naming.directory.Attributes;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.BasicAttributes;

import org.springframework.ldap.CommunicationException;
import org.springframework.ldap.NameAlreadyBoundException;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;
import org.springframework.stereotype.Service;

@Service
public class PersonProvisioningService {

    private final LdapTemplate writer;
    private final OperationJournal journal;

    public PersonProvisioningService(
            LdapTemplate writer,
            OperationJournal journal) {
        this.writer = writer;
        this.journal = journal;
    }

    public UUID create(UUID operationId, PersonCommand command) {
        validate(command);
        if (operationId == null) {
            throw new IllegalArgumentException("operationId is required");
        }
        Name dn = LdapNameBuilder.newInstance("ou=people")
                .add("uid", command.uid())
                .build();

        Attributes attrs = new BasicAttributes(true);
        BasicAttribute objectClass = new BasicAttribute("objectClass");
        objectClass.add("top");
        objectClass.add("person");
        objectClass.add("organizationalPerson");
        objectClass.add("inetOrgPerson");

        attrs.put(objectClass);
        attrs.put("uid", command.uid());
        attrs.put("cn", command.commonName());
        attrs.put("sn", command.surname());
        attrs.put("employeeNumber", command.employeeNumber());

        // operationId được tạo/tra cứu ở HTTP boundary từ Idempotency-Key.
        // Commit journal trước khi dispatch LDAP write.
        journal.prepare(
                operationId,
                "ADD_PERSON",
                command.employeeNumber(),
                dn.toString(),
                fingerprint(command));

        // Claim bằng compare-and-set: chỉ một request được dispatch.
        // Nếu key đã ở DISPATCHING/UNKNOWN/terminal, caller đọc status cũ.
        if (!journal.claimDispatchIfPrepared(operationId)) {
            return operationId;
        }

        try {
            writer.bind(dn, null, attrs);
            journal.markConfirmedApplied(operationId);
            return operationId;

        } catch (CommunicationException timeoutOrDisconnect) {
            // Không suy ra server đã rollback.
            journal.markUnknown(operationId, "COMMUNICATION_FAILURE");
            throw new WriteOutcomeUnknownException(
                    operationId, timeoutOrDisconnect);

        } catch (NameAlreadyBoundException duplicate) {
            // Response LDAP xác định DN đã tồn tại cho lần Add này.
            // Nếu đây là lần dispatch lại, reconciliation phải xác minh
            // stable ID trước khi kết luận operation trước đã hoàn tất.
            journal.markConfirmedRejected(
                    operationId, "ENTRY_ALREADY_EXISTS");
            throw new PersonAlreadyExistsException(
                    command.uid(), duplicate);
        }
    }

    private static void validate(PersonCommand command) {
        if (command == null
                || command.uid() == null
                || !command.uid().matches("[a-z][a-z0-9._-]{2,31}")
                || command.employeeNumber() == null
                || command.employeeNumber().isBlank()
                || command.commonName() == null
                || command.commonName().isBlank()
                || command.surname() == null
                || command.surname().isBlank()) {
            throw new IllegalArgumentException("Invalid person command");
        }
    }

    private static String fingerprint(PersonCommand command) {
        // Canonicalize theo length-prefix để tránh nhập nhằng dấu phân cách.
        // Chỉ hash dữ liệu nghiệp vụ; tuyệt đối không đưa password/secret vào.
        String canonical = field(command.uid())
                + field(command.employeeNumber())
                + field(command.commonName())
                + field(command.surname());
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256")
                    .digest(canonical.getBytes(StandardCharsets.UTF_8));
            return Base64.getUrlEncoder().withoutPadding()
                    .encodeToString(digest);
        } catch (NoSuchAlgorithmException impossible) {
            throw new IllegalStateException("SHA-256 is unavailable", impossible);
        }
    }

    private static String field(String value) {
        return value == null ? "-1:" : value.length() + ":" + value;
    }
}
~~~

Các kiểu `PersonCommand`, `OperationJournal`, `WriteOutcomeUnknownException` và `PersonAlreadyExistsException` là kiểu của ứng dụng, cần triển khai theo dự án. Fingerprint trong ví dụ chỉ minh họa; production nên dùng hash chuẩn trên canonical serialization và bảo vệ dữ liệu cá nhân.

### Lưu ý khi triển khai journal

- `prepare` phải có unique constraint trên `operationId`/idempotency key. Cùng key và cùng fingerprint thì trả bản ghi cũ; cùng key nhưng payload khác thì trả conflict.
- `claimDispatchIfPrepared` phải là compare-and-set nguyên tử từ `PREPARED` sang `DISPATCHING`, để hai HTTP request đồng thời không cùng gửi một write.
- Nếu `journal.markUnknown` cũng lỗi, bản ghi vẫn ở `DISPATCHING`; recovery worker phải coi nó là chưa rõ kết quả.
- Không đánh dấu `CONFIRMED_REJECTED` cho mọi runtime exception. Chỉ đánh dấu rejected khi có response/exception xác định request bị từ chối; lỗi transport hoặc exception không phân loại được vẫn có thể là UNKNOWN.
- Không giữ transaction database mở trong lúc chờ LDAP lâu hơn cần thiết.
- Không giả định transaction database và LDAP cùng commit/rollback.
- Không dùng UUID của operation thay cho định danh ổn định của entry.

## 15. Reconciliation worker: xác minh trước khi retry

Một worker nền có thể xử lý các operation `UNKNOWN`:

~~~java
public ReconciliationResult reconcileAdd(
        PendingOperation operation,
        LdapTemplate reader) {

    try {
        Name targetDn = LdapNameBuilder
                .newInstance(operation.targetDn())
                .build();
        PersonSnapshot actual = reader.lookup(
                targetDn,
                attrs -> new PersonSnapshot(
                        (String) attrs.get("uid").get(),
                        (String) attrs.get("employeeNumber").get(),
                        (String) attrs.get("cn").get()
                )
        );

        if (actual.employeeNumber().equals(operation.stableKey())
                && actual.uid().equals(operation.expectedUid())
                && matchesFingerprint(actual, operation)) {
            return ReconciliationResult.applied();
        }

        return ReconciliationResult.conflict(
                "DN exists but identifies a different or unexpected entry");

    } catch (org.springframework.ldap.NameNotFoundException missing) {
        // Một lần đọc không tìm thấy chưa luôn chứng minh operation
        // không còn đang xử lý hoặc replica đã đồng bộ.
        return ReconciliationResult.stillUnknown(
                "Entry not visible yet; verify endpoint and operation settlement");
    }
}
~~~

Đây là code khung; các record và hàm so sánh cần triển khai. Không nên chuyển kết quả `NameNotFoundException` ngay thành `RECONCILED_NOT_APPLIED` nếu chưa xác nhận:

1. Reader đang truy vấn cùng DC/endpoint đã nhận write.
2. Operation cũ đã settle hoặc không còn khả năng tiếp tục áp dụng.
3. Directory không có replication delay làm kết quả đọc bị cũ.
4. Không có một workflow khác đang tạo cùng entry.

### Backoff có giới hạn

Nếu cần chờ server hoàn tất, có thể thử đọc lại theo lịch backoff có jitter, ví dụ:

~~~text
200 ms -> 500 ms -> 1 s -> 2 s -> 4 s
~~~

Đây chỉ là ví dụ policy. Giới hạn tổng thời gian và số lượt đọc; sau đó giữ `UNKNOWN` để xử lý tiếp thay vì tạo vòng lặp vô hạn.

## 16. Retry: operation nào có thể gửi lại?

Retry nên được quyết định dựa trên **desired state**, tính idempotent và bằng chứng về operation trước.

| Operation/pattern | Có thể retry trực tiếp? | Điều kiện |
| --- | --- | --- |
| Add cùng DN deterministic | Không tự động | Reconcile entry, stable ID và payload trước. |
| Replace attribute bằng giá trị tuyệt đối | Có thể trong một số trường hợp | Đảm bảo không ghi đè thay đổi đồng thời; dùng assertion/version nếu cần. |
| Add value vào multi-valued attribute | Không mù | Kiểm tra value đã có chưa; xử lý duplicate và concurrent writer. |
| Remove một value | Không mù | Kiểm tra value còn tồn tại và policy nếu đã vắng mặt. |
| Delete DN | Có điều kiện | Xác minh object identity; xử lý absence theo desired-state policy. |
| Rename/Move | Không mù | Kiểm tra cả DN cũ và mới bằng stable identity. |
| Password Modify | Không mù | Xác minh credential theo policy an toàn hoặc yêu cầu can thiệp. |
| Gửi lại toàn bộ workflow nhiều request | Không | Reconcile từng bước, dùng saga/compensation. |

### 16.1. Không dùng @Retryable quá rộng

Anti-pattern:

~~~java
@Retryable(
    retryFor = org.springframework.ldap.NamingException.class,
    maxAttempts = 3
)
public void createPerson(...) {
    ldapTemplate.bind(...);
}
~~~

Cách này có thể gửi lại Add sau khi server đã tạo entry nhưng response bị mất. Nó cũng retry lỗi schema, ACL hoặc dữ liệu không hợp lệ vốn không tự hết.

Nếu dùng Spring Retry, chỉ retry các lỗi đã được phân loại là tạm thời và chỉ với operation có cơ chế idempotency/reconciliation. Đối với write có kết quả UNKNOWN, retry phải là một bước riêng sau reconciliation.

### 16.2. Retry và HTTP client cũng cần cùng policy

Nếu API trả timeout và frontend tự gửi lại POST, server có thể nhận hai yêu cầu. Hãy dùng idempotency key ở HTTP boundary và lưu trạng thái operation. Không yêu cầu người dùng nhấn nút lần nữa để giải quyết một trạng thái directory chưa rõ.

## 17. Assertion Control và version check

Với dữ liệu hay được cập nhật đồng thời, đọc rồi ghi vẫn có race:

~~~text
Client A đọc title = Developer
Client B đổi title = Architect
Client A gửi Replace title = Senior Developer
~~~

Nếu không có điều kiện, A có thể ghi đè thay đổi mới của B.

Assertion Control (RFC 4528) cho phép update chỉ thực hiện khi filter condition trên entry vẫn đúng. Nếu điều kiện sai/undefined, server trả `assertionFailed (122)` và không thực hiện operation.

Các ứng dụng có thể kiểm tra:
- Version attribute do ứng dụng quản lý.
- `entryCSN` hoặc `modifyTimestamp` nếu directory cung cấp và semantics phù hợp.
- Stable identity và trạng thái nghiệp vụ.

Không giả định mọi server hỗ trợ control hoặc cùng một operational attribute. Hãy kiểm tra capability, cấu hình provider/control và test với server thực tế.

**Assertion Control giải quyết concurrent update; nó không phải idempotency key và không thay thế reconciliation sau mất response.**

## 18. Workflow nhiều bước: dùng saga và đối soát

Giả sử onboarding người dùng gồm:

1. Add entry trong `ou=people`.
2. Add DN vào `groupOfNames.member`.
3. Ghi audit trong database.
4. Gửi sự kiện cho hệ thống khác.

Đây là nhiều hệ thống/operation. Nếu bước 2 timeout, không thể suy ra bước 1 chưa thành công.

~~~mermaid
flowchart TD
    A["Prepare operation journal"] --> B["Add person"]
    B --> C{"Add confirmed?"}
    C -->|Yes| D["Add group membership"]
    C -->|Unknown| U["Reconcile person entry"]
    U -->|Applied| D
    U -->|Not applied| R["Controlled retry / stop"]
    U -->|Conflict| X["Manual reconciliation"]
    D --> E{"Membership confirmed?"}
    E -->|Yes| F["Commit business completion"]
    E -->|Unknown| G["Reconcile group member"]
    G -->|Applied| F
    G -->|Not applied| H["Retry only after safe decision"]
    G -->|Conflict| X
    F --> I["Outbox event / downstream delivery"]
~~~

### Compensating action

Nếu nghiệp vụ quyết định phải hoàn tác khi Add membership thất bại, có thể xóa entry vừa tạo. Nhưng compensation cũng là một LDAP Delete có thể timeout và có trạng thái UNKNOWN riêng.

Không gọi compensation ngay khi một operation đang UNKNOWN. Trước hết phải xác minh trạng thái operation trước, rồi mới quyết định hành động bù.

### Transaction LDAP không mặc định được hỗ trợ

LDAP có các extension/implementation riêng cho transaction, nhưng không nên giả định mọi directory và Spring LDAP deployment đều hỗ trợ transaction đa operation. Với workflow liên quan database, LDAP và hệ thống khác, thiết kế operation journal, saga, outbox và reconciliation thường dễ kiểm soát hơn việc giả định một transaction phân tán tự động.

## 19. HTTP API nên biểu diễn UNKNOWN thế nào?

Nếu request HTTP chờ LDAP quá deadline, API không nên trả thông báo “ghi thất bại” khi chưa biết trạng thái.

Một response ví dụ:

~~~http
HTTP/1.1 202 Accepted
Location: /api/v1/operations/4f13d8c8-4d55-4c88-a4bc-5c1e6d14e2b7
Content-Type: application/json
~~~

~~~json
{
  "operationId": "4f13d8c8-4d55-4c88-a4bc-5c1e6d14e2b7",
  "status": "UNKNOWN",
  "message": "Directory chưa xác nhận kết quả. Hệ thống đang đối soát."
}
~~~

`202 Accepted` phù hợp nếu ứng dụng đã lưu operation journal và có endpoint theo dõi trạng thái. Nếu API đồng bộ chọn trả `504 Gateway Timeout`, response vẫn phải nói rõ kết quả ghi **chưa xác định**; client không nên tự gửi một operation mới bằng key khác.

Endpoint theo dõi:

~~~http
GET /api/v1/operations/4f13d8c8-4d55-4c88-a4bc-5c1e6d14e2b7
~~~

Kết quả sau reconciliation:

~~~json
{
  "operationId": "4f13d8c8-4d55-4c88-a4bc-5c1e6d14e2b7",
  "status": "RECONCILED_APPLIED",
  "resource": "/api/v1/people/lan"
}
~~~

Không trả LDAP Bind DN, raw DN ngoài phạm vi người gọi được phép, credential, stack trace hoặc diagnostic message.

## 20. Kiểm thử timeout sau khi request đã tới LDAP

Unit test mock `LdapTemplate` ném `CommunicationException` chỉ kiểm tra service xử lý exception. Nó **không chứng minh** tình huống quan trọng nhất: server đã áp dụng write nhưng response bị mất.

Cần integration test có fault injection ở tầng network.

### 20.1. Kịch bản proxy

~~~text
Spring application
        |
        v
Fault-injection TCP proxy
        |
        v
LDAP test server
~~~

Proxy có thể:
- Chuyển Add/Modify/Delete tới LDAP server.
- Đợi server trả LDAP success response.
- Cố ý bỏ response, đóng connection phía client.
- Hoặc đóng connection ngay sau khi nhận request nhưng trước khi chuyển tới server.

Hai kịch bản này tạo hai trạng thái khác nhau để kiểm tra reconciliation.

### 20.2. Ma trận test

| Kịch bản | Hành vi proxy/server | Kỳ vọng ứng dụng |
| --- | --- | --- |
| Connect timeout trước khi gửi | Không thiết lập được TCP connection | Có thể ghi NOT_SENT nếu có bằng chứng request chưa gửi. |
| Read timeout trước response | Request đã tới server, response bị trì hoãn | UNKNOWN. |
| Add đã áp dụng, response bị drop | Server có entry, client timeout | Reconcile thành APPLIED nếu stable ID/payload khớp. |
| Add chưa tới server | Proxy drop request trước khi forward | UNKNOWN trước reconciliation; sau đó mới quyết định not applied. |
| Add retry tạo duplicate | Entry đã tồn tại | Đối chiếu stable ID, không rebind. |
| Modify đã áp dụng, response bị drop | Attribute đạt desired state | Reconcile APPLIED. |
| Modify chưa áp dụng | Attribute còn trạng thái cũ | Chỉ retry khi operation đã settle và version/precondition còn đúng. |
| Modify có concurrent writer | Attribute khác desired state | CONFLICT, không ghi đè. |
| Delete đã áp dụng, response bị drop | DN không còn trên cùng DC | Reconcile desired state absent; kiểm tra identity/audit theo policy. |
| Delete DN đã được tái sử dụng | DN hiện có stable ID khác | CONFLICT, không xóa object mới. |
| Rename đã áp dụng | DN cũ vắng, DN mới có cùng stable ID | Reconcile APPLIED. |
| Rename có DN đích bị chiếm | DN cũ và DN mới phản ánh hai object | CONFLICT. |
| Password Modify response bị drop | Không đọc lại được secret | UNKNOWN; xác minh Bind theo policy an toàn. |
| LDAP server restart | Connection bị đóng khi write đang chạy | UNKNOWN nếu request có thể đã tới server. |
| Replica chưa nhận replication | Read từ DC khác không thấy write | Không kết luận NOT_APPLIED. |
| Process chết sau DISPATCHING | Không biết request đã rời process chưa | Recovery worker xử lý UNKNOWN. |
| Journal update thất bại | LDAP write có thể đã thành công | Bản ghi DISPATCHING phải được recovery như UNKNOWN. |
| Client HTTP retry cùng idempotency key | Cùng operationId | Trả trạng thái cũ; không dispatch duplicate. |

### 20.3. Test đơn vị cho state machine

Các test cần xác nhận:
- Success response -> `CONFIRMED_APPLIED`.
- LDAP error response đã phân loại -> `CONFIRMED_REJECTED`.
- `CommunicationException` sau dispatch -> `UNKNOWN`.
- UNKNOWN không được tự chuyển thành retry.
- Reconciliation matching desired state -> `RECONCILED_APPLIED`.
- Reconciliation thấy object khác stable ID -> `CONFLICT`.
- Journal không thể ghi UNKNOWN -> trạng thái DISPATCHING vẫn được recovery xem là UNKNOWN.

### 20.4. Test timeout thật không nên phụ thuộc timing mong manh

Không dùng một sleep cố định 1 ms rồi mong request chắc chắn đã đến server. Proxy nên có tín hiệu xác nhận:
- Request LDAP đã được nhận.
- Request đã được forward.
- Server đã áp dụng operation (có thể xác minh bằng một read trên server test).
- Response đã bị drop.

Nhờ đó test phân biệt được “request chưa gửi” với “server đã ghi nhưng response mất”.

## 21. Observability và audit

Khi write có kết quả UNKNOWN, log và metric nên đủ để điều tra nhưng không chứa bí mật.

### Nên ghi

- `operationId`.
- Loại operation: ADD/MODIFY/DELETE/MODIFY_DN/PASSWORD_MODIFY.
- Resource key đã được chuẩn hóa hoặc token nội bộ.
- LDAP endpoint/DC đã sử dụng nếu được phép.
- Thời điểm dispatch và timeout.
- Exception class/root cause class.
- Trạng thái hiện tại và số lần reconciliation.
- Thời gian từ UNKNOWN tới khi được giải quyết.
- Kết quả APPLIED/NOT_APPLIED/CONFLICT/UNKNOWN.

### Không nên ghi

- Mật khẩu Bind hoặc mật khẩu mới.
- Toàn bộ `Attributes`/LDIF có dữ liệu cá nhân.
- Raw LDAP diagnostic trả về client.
- Token HTTP hoặc secret trong JNDI environment.
- DN nhạy cảm trong log không kiểm soát.

### Metrics gợi ý

| Metric | Mục đích |
| --- | --- |
| `ldap.write.timeout.count` | Số write timeout. |
| `ldap.write.unknown.count` | Số operation chưa xác định. |
| `ldap.write.reconcile.duration` | Thời gian giải quyết UNKNOWN. |
| `ldap.write.reconcile.conflict.count` | Xung đột sau timeout. |
| `ldap.write.retry.count` | Số retry đã được policy cho phép. |
| `ldap.write.pending.age` | Tuổi của operation chưa được giải quyết. |

Alert khi operation UNKNOWN tồn tại quá lâu, tăng đột biến hoặc có conflict lặp lại. Không gắn UID/email làm metric tag vì cardinality và quyền riêng tư.

## 22. Bảo mật và quyền truy cập trong quy trình reconciliation

Reconciliation cũng là một chức năng truy cập dữ liệu, phải được bảo vệ như write service:

- Dùng Bind DN reader chỉ có quyền đọc các attribute cần so sánh.
- Không tự chuyển sang account admin khi reader không đọc được entry.
- Chỉ reconciliation worker có quyền cập nhật operation journal.
- Không cho HTTP caller tùy ý yêu cầu reconcile DN ngoài scope của họ.
- Bảo vệ endpoint operation status bằng authorization.
- Dùng LDAPS hoặc StartTLS có xác minh certificate/hostname.
- Đặt timeout và giới hạn số lần đọc lại.
- Không để worker lặp vô hạn khi server unavailable.
- Với password operation, không lưu secret trong journal hoặc log.
- Khi có referral, chỉ theo referral tới endpoint được allowlist; không chuyển credential tùy tiện.

Một kết quả “không tìm thấy” chỉ đáng tin khi reader có quyền Search/Read phù hợp. ACL che entry hoặc attribute có thể làm reconciliation đưa ra kết luận sai.

## 23. Lỗi thường gặp

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Coi timeout là write failed | Retry có thể tạo duplicate hoặc ghi đè. | Ghi UNKNOWN, reconciliation. |
| Coi timeout là write success | Báo thành công dù server chưa áp dụng. | Chỉ xác nhận khi nhận success hoặc reconcile. |
| Retry mọi `CommunicationException` | Gửi lặp operation không idempotent. | Retry theo loại operation và desired state. |
| Dùng `@Retryable` trên toàn service write | Lặp Add/Modify/Delete/Password không kiểm soát. | Retry ở lớp điều phối sau reconciliation. |
| Dùng `rebind` để retry Add | Có thể xóa và tạo lại entry. | Dùng bind và kiểm tra stable identity. |
| Dùng DN làm định danh bất biến | Rename/move hoặc DN tái sử dụng gây đối soát nhầm. | Dùng `entryUUID`/`objectGUID` hoặc business ID ổn định. |
| Chỉ đọc một replica sau timeout | Replication lag bị hiểu nhầm là write thất bại. | Đối soát cùng authoritative DC/endpoint. |
| Dùng Replace không kiểm tra version | Ghi đè cập nhật mới của actor khác. | Assertion Control hoặc optimistic concurrency. |
| Coi HTTP cancellation là LDAP rollback | Server vẫn có thể hoàn tất write. | Dùng operation journal và UNKNOWN state. |
| Dùng Search timeLimit làm write timeout | Write không được giới hạn như mong muốn. | Cấu hình JNDI read timeout và application deadline. |
| Bắt exception rồi trả 500 “failed” | Caller có thể retry sai. | Trả trạng thái outcome unknown. |
| Lưu password trong journal | Rò rỉ credential. | Chỉ lưu metadata/fingerprint không chứa secret. |
| Đánh dấu journal complete trước LDAP response | Mất khả năng phát hiện write chưa xác nhận. | Journal PREPARED/DISPATCHING trước dispatch. |
| Dùng transaction DB để rollback LDAP | Hai hệ thống không tự atomic. | Saga, compensation và reconciliation. |
| Retry Delete khi DN hiện có object khác | Xóa nhầm object mới. | So stable ID trước mọi retry. |
| Xem Add duplicate là chứng minh lần trước thành công | DN có thể thuộc object được tạo trước bởi actor khác. | So stable ID và expected payload. |
| Không kiểm thử response loss | Unit test exception không bao phủ tình huống server đã ghi. | Fault-injection proxy integration test. |

## 24. Checklist triển khai

| Hạng mục | Tiêu chí đạt |
| --- | --- |
| Timeout | Connect và read timeout được cấu hình riêng, có application deadline. |
| State model | Có CONFIRMED_APPLIED, CONFIRMED_REJECTED, UNKNOWN và CONFLICT. |
| Journal | Ghi operationId và DISPATCHING bền vững trước write. |
| Stable identity | Có định danh không đổi khi DN rename/move. |
| Add | Sau timeout kiểm tra DN, stable ID và payload; không rebind. |
| Modify | Xác minh desired state, tránh ghi đè concurrent update. |
| Delete | Kiểm tra identity trước retry; xử lý absence theo policy. |
| ModifyDN | Đọc cả DN cũ và mới, so stable identity. |
| Password | Không lưu secret; có quy trình xác minh riêng. |
| Retry | Không retry mù; có backoff, giới hạn và idempotency key. |
| Reconciliation | Đọc đúng DC/endpoint, xử lý replication lag và ACL. |
| HTTP | API biểu diễn outcome unknown và cung cấp operation status. |
| Transactions | Không giả định transaction database tự rollback LDAP. |
| Audit | Có operation ID, actor, resource key, trạng thái và thời điểm. |
| Security | TLS, least privilege, không log credential/LDIF nhạy cảm. |
| Tests | Có proxy drop response sau khi server đã áp dụng write. |

## 25. Bài tập thực hành

**Bài 1 — Mô phỏng Add response bị mất.** Tạo một entry bằng `LdapTemplate.bind` qua proxy. Cho proxy forward request tới LDAP server, chờ entry xuất hiện rồi drop response. Xác minh ứng dụng ghi UNKNOWN, sau đó reconciliation nhận ra entry có stable ID khớp và chuyển sang RECONCILED_APPLIED.

**Bài 2 — Add chưa tới server.** Cho proxy drop request trước khi forward. Xác minh client vẫn có thể thấy timeout/UNKNOWN nếu không có bằng chứng dispatch, nhưng worker chỉ chuyển sang RECONCILED_NOT_APPLIED sau khi xác minh cùng endpoint và operation đã settle.

**Bài 3 — Modify atomicity.** Gửi một ModifyRequest gồm hai thay đổi attribute. Thử một request bị server từ chối và một request được áp dụng nhưng response bị drop. So sánh error response với trường hợp không có response theo RFC 4511 Section 4.6.

**Bài 4 — Replace và Add value.** Cập nhật một attribute bằng REPLACE, sau đó thử ADD một giá trị vào multi-valued attribute. Gửi lại request và quan sát khác biệt về idempotency/result code.

**Bài 5 — Assertion Control.** Dùng Assertion Control nếu server test hỗ trợ. Đọc version token, thay đổi entry từ một client khác rồi gửi Modify với assertion cũ. Xác minh operation bị từ chối và không ghi đè thay đổi mới.

**Bài 6 — Delete và DN tái sử dụng.** Xóa một entry qua proxy drop response. Tạo một object khác ở DN cũ trong test. Reconciliation phải phát hiện stable ID khác và không gửi Delete lần hai.

**Bài 7 — ModifyDN.** Rename một entry, drop response rồi kiểm tra DN cũ/mới. Thêm trường hợp DN đích đã tồn tại và xử lý conflict.

**Bài 8 — Password Modify.** Dùng server test hỗ trợ RFC 3062. Drop response sau khi server đổi password. Thiết kế xác minh bằng Bind theo chính sách lockout và không lưu secret trong operation journal.

**Bài 9 — HTTP idempotency.** Gửi hai POST cùng `Idempotency-Key` khi operation đầu đang UNKNOWN. Xác minh chỉ có một LDAP dispatch và cả hai caller nhận cùng operation status.

**Bài 10 — Recovery sau process crash.** Dừng application sau khi journal ở DISPATCHING. Khởi động lại worker, tìm operation cũ và thực hiện reconciliation trước mọi retry.

## 26. Câu hỏi tự đánh giá

1. Vì sao LDAP server có thể đã ghi dữ liệu dù client nhận timeout?
2. RFC 4511 nói gì về update operation khi transport connection đóng?
3. Connect timeout khác read timeout như thế nào?
4. Vì sao `com.sun.jndi.ldap.read.timeout` không phải bằng chứng operation bị hủy?
5. `CONFIRMED_REJECTED` khác `UNKNOWN` ở điểm nào?
6. Vì sao một ModifyRequest có nhiều ModificationItem vẫn được áp dụng nguyên tử?
7. Nếu ModifyResponse không được nhận, client có thể suy ra điều gì?
8. Vì sao `LDAP messageID` không phải idempotency key bền vững?
9. Add bị timeout rồi retry gặp `entryAlreadyExists` có chứng minh operation đầu đã thành công không?
10. Vì sao không dùng `rebind` để retry Add?
11. Khi nào Replace attribute có thể retry an toàn hơn Add/Delete value?
12. Assertion Control giúp giải quyết loại race condition nào?
13. Assertion Control có thay thế reconciliation sau response loss không?
14. Khi Delete timeout, tại sao phải kiểm tra stable identity thay vì chỉ kiểm tra DN?
15. Rename/Move cần kiểm tra những DN nào sau timeout?
16. Vì sao password operation khó đối soát bằng cách đọc lại dữ liệu?
17. HTTP request bị cancel có rollback LDAP write không?
18. Vì sao đọc từ replica khác có thể dẫn tới kết luận sai?
19. Operation journal cần ghi trạng thái nào trước khi dispatch LDAP?
20. Khi nào một workflow nên chuyển sang saga/compensation?
21. Vì sao không thể dùng transaction database để rollback LDAP một cách tự động?
22. Cần mô phỏng tình huống nào để chứng minh server đã ghi nhưng response bị mất?

**Ghi nhớ:** khi write request đã có thể được gửi tới LDAP server nhưng client không nhận được response, trạng thái đúng là **UNKNOWN**. Đối soát bằng stable identity và desired state trên endpoint có thẩm quyền; chỉ retry sau khi biết operation trước đã settle và retry an toàn. Timeout, HTTP cancellation và Abandon không phải rollback. Hãy dùng operation journal, idempotency key, assertion/version check, reconciliation và integration test có fault injection để tránh ghi trùng, ghi đè hoặc xóa nhầm dữ liệu.

### Tài liệu tham khảo

- [RFC 4511 — LDAP: The Protocol, Section 3.1](https://www.rfc-editor.org/rfc/rfc4511.html#section-3.1): khi transport connection đóng, client không được giả định update operation chưa hoàn tất đã thành công hay thất bại.
- [RFC 4511 — Modify Operation, Section 4.6](https://www.rfc-editor.org/rfc/rfc4511.html#section-4.6): tính nguyên tử của danh sách thay đổi trong một ModifyRequest và trạng thái không xác định khi không nhận response.
- [RFC 4511 — Add/Delete/Modify DN Operations, Sections 4.7–4.9](https://www.rfc-editor.org/rfc/rfc4511.html): ngữ nghĩa các operation ghi.
- [RFC 4511 — Abandon Operation, Section 4.11](https://www.rfc-editor.org/rfc/rfc4511.html#section-4.11): Abandon không có response xác nhận.
- [RFC 4528 — LDAP Assertion Control](https://www.rfc-editor.org/rfc/rfc4528.html): conditional update, test-and-set và assertionFailed.
- [RFC 3062 — LDAP Password Modify Extended Operation](https://www.rfc-editor.org/rfc/rfc3062.html): Password Modify request/response và yêu cầu bảo vệ confidentiality/integrity.
- [Oracle Java Tutorial — Setting Timeout for LDAP Operations](https://docs.oracle.com/javase/tutorial/jndi/newstuff/readtimeout.html): `com.sun.jndi.ldap.read.timeout`, đơn vị mili giây và khác biệt với connect timeout.
- [Oracle JNDI LDAP Provider Documentation](https://docs.oracle.com/javase/8/docs/technotes/guides/jndi/jndi-ldap.html): environment property của LDAP provider, connection và read timeout.
- [Spring LDAP — LdapTemplate API](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/LdapTemplate.html): bind, modifyAttributes, rename và các thao tác write.
- [Spring LDAP — Basic Usage](https://docs.spring.io/spring-ldap/reference/spring-ldap-basic-usage.html): modifyAttributes, rebind và các cách cập nhật entry.
- [Spring LDAP — LdapClient API](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/LdapClient.html): API fluent cho bind, modify, rename và unbind.
- [Spring Framework — Retry](https://docs.spring.io/spring-retry/reference/index.html): retry policy; cần kết hợp với idempotency và reconciliation cho write operation.
