# Grant, deny, thứ tự ACE và chính sách kiểm tra quyền trong Spring Security ACL

## 1. Bài toán: ai được phép làm gì trên **đúng đối tượng nào**?

Trong Spring Security, `hasRole('EDITOR')` hay `hasAuthority('document:read')` thường trả lời câu hỏi người dùng có một vai trò hoặc authority hay không. Nhưng hai người cùng có quyền đọc tài liệu chưa chắc được phép đọc **cùng một tài liệu**. Ví dụ:

- Alice sở hữu tài liệu 42 và có thể đọc, sửa tài liệu đó.
- Bob được chia sẻ quyền **đọc** tài liệu 42, nhưng không có quyền sửa.
- Nhóm `ROLE_AUDITOR` có quyền xem một số báo cáo, không có quyền sửa.
- Tài liệu 57 thuộc tenant khác nên Alice không được đọc, kể cả khi một quy tắc role chung cho phép đọc tài liệu.

**Access Control List (ACL)** bổ sung một danh sách các mục quyền cho từng domain object cụ thể. Mỗi mục gọi là **Access Control Entry (ACE)**, nêu một security identity (SID), một permission và cờ **grant** hoặc **deny**.

Chủ đề này không chỉ là “`grant = true`, `deny = false`”. Với Spring Security ACL, kết quả còn phụ thuộc:

1. **Thứ tự các ACE** trong ACL.
2. **Thứ tự danh sách permission được yêu cầu**.
3. **Thứ tự các SID** mà người gọi có.
4. **PermissionGrantingStrategy** thực sự được cấu hình.
5. **ACL cha và cờ kế thừa ACE**.
6. Cách ứng dụng xử lý trạng thái **không tìm thấy ACE nào phù hợp**.

Điểm quan trọng nhất: **không mặc định rằng deny luôn thắng mọi grant, cũng không coi việc không có ACE là đã có một ACE deny tường minh**.

## 2. Các thành phần ACL cần nắm

| Thành phần | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `ObjectIdentity` | Danh tính duy nhất của một domain object | `Document.class` + `42L` |
| `Acl` | Danh sách quyền áp dụng cho một object identity | ACL của Document 42 |
| `Sid` | Người hoặc authority nhận quyền | `PrincipalSid("alice")`, `GrantedAuthoritySid("ROLE_AUDITOR")` |
| `Permission` | Hành động/bit mask được kiểm tra | `BasePermission.READ` |
| `AccessControlEntry` | Mục kết hợp ACL + SID + permission + granting | Alice, READ, grant |
| `AclService` | Đọc ACL từ nguồn dữ liệu | `readAclById(...)` |
| `MutableAclService` | Tạo, cập nhật, xóa ACL | `createAcl`, `updateAcl` |
| `PermissionGrantingStrategy` | Đánh giá các ACE và xác định allow/deny | `DefaultPermissionGrantingStrategy` |
| `AclPermissionEvaluator` | Kết nối ACL với biểu thức `hasPermission(...)` | Dùng trong `@PreAuthorize` |

Trong schema JDBC thông dụng của Spring Security ACL:

- `ACL_CLASS` xác định các lớp domain.
- `ACL_SID` lưu principal/authority làm SID.
- `ACL_OBJECT_IDENTITY` lưu từng đối tượng, ACL parent, owner và `entries_inheriting`.
- `ACL_ENTRY` lưu từng ACE, gồm `acl_object_identity`, `ace_order`, `sid`, `mask`, `granting` và cờ audit.

**`ace_order` có ý nghĩa**: các ACE không chỉ là một tập quyền không có thứ tự. Tuy nhiên `ace_order` không phải yếu tố duy nhất quyết định thứ tự đánh giá, vì danh sách permissions và SIDs đầu vào cũng có thứ tự.

## 3. Grant và deny có nghĩa chính xác gì?

Một ACE gồm những thông tin khái niệm:

```text
Object: Document #42
SID:    PrincipalSid("alice")
Mask:   READ (1)
Grant:  true
```

Nó có nghĩa một ACE **cấp** quyền READ cho Alice trên Document 42.

ACE khác:

```text
Object: Document #42
SID:    PrincipalSid("bob")
Mask:   WRITE (2)
Grant:  false
```

Nó là một mục **từ chối tường minh** quyền WRITE của Bob đối với đối tượng đó.

Trong Java, một ACE có thể được xem qua interface `AccessControlEntry`:

```java
Sid recipient = ace.getSid();
Permission permission = ace.getPermission();
boolean granting = ace.isGranting();
```

Đoạn này là **fragment** đọc từ một `AccessControlEntry` đã có; nó không tạo ACL hay tải database.

### Đừng nhầm ba trạng thái

| Trạng thái | Điều thực sự xảy ra | Ý nghĩa thực tế |
| --- | --- | --- |
| Một ACE phù hợp có `granting=true` | Có quyết định cấp quyền | `isGranted(...)` có thể trả `true` |
| Một ACE phù hợp có `granting=false` | Có quyết định từ chối tường minh | `isGranted(...)` có thể trả `false` |
| Không có ACE phù hợp trong phạm vi tìm kiếm | Chưa có quyết định đủ căn cứ | Có thể thử parent ACL, sau đó `NotFoundException` |

Trong Spring Security ACL, `NotFoundException` từ `Acl.isGranted(...)` **không có nghĩa đối tượng business chắc chắn không tồn tại**. Nó cũng có thể nghĩa không có thông tin ACL/SID/permission đủ để quyết định. Ứng dụng phải quyết định cách xử lý, thông thường **không cấp quyền** khi thiếu bằng chứng cho phép.

Đối với hệ thống bảo mật, **fail closed** là lựa chọn cơ bản: khi không thể xác minh quyền, không cho đọc/sửa dữ liệu. Nhưng không nuốt toàn bộ lỗi cơ sở dữ liệu thành “không có ACE”: outage là lỗi hạ tầng, cần được log/giám sát và trả phản hồi phù hợp.

## 4. Permission và bit mask

`BasePermission` của Spring ACL cung cấp các permission phổ biến:

| Permission | Bit | Giá trị mask |
| --- | ---: | ---: |
| `BasePermission.READ` | 0 | 1 |
| `BasePermission.WRITE` | 1 | 2 |
| `BasePermission.CREATE` | 2 | 4 |
| `BasePermission.DELETE` | 3 | 8 |
| `BasePermission.ADMINISTRATION` | 4 | 16 |

Bit mask cho phép kết hợp quyền. Ví dụ mask `3` chứa READ (1) và WRITE (2). Tuy nhiên cách một mask kết hợp được **so với ACE** là trách nhiệm của `PermissionGrantingStrategy`, không nên chỉ dựa vào toán tử bit Java rồi suy ra toàn bộ chính sách.

Theo Javadoc của `DefaultPermissionGrantingStrategy`, kiểm tra từng ACE có chi tiết đáng lưu ý:

- Với **ACE grant** và permission được hỏi có mask khác 0, chiến lược mặc định xem ACE là phù hợp nếu `(aceMask & requestedMask) != 0`.
- Với **ACE deny**, chiến lược mặc định dùng **so khớp mask chính xác** `aceMask == requestedMask`.
- Khi dùng một chiến lược tùy biến, hoặc thay `Permission` và cách cấu tạo mask, ngữ nghĩa này có thể thay đổi.

Ví dụ theo chiến lược mặc định:

```text
ACE grant, mask = 3 (READ | WRITE)
Hỏi READ, mask = 1  -> (3 & 1) != 0 -> match
Hỏi WRITE, mask = 2 -> (3 & 2) != 0 -> match

ACE deny, mask = 3 (READ | WRITE)
Hỏi READ, mask = 1 -> 3 != 1 -> không match theo rule deny mặc định
Hỏi mask = 3       -> 3 == 3 -> match
```

**Cảnh báo:** chính sách với nhiều bit có thể gây kết quả bất ngờ, đặc biệt khi điều kiện “có đủ hai quyền” bị biểu diễn bằng phép OR/bit-overlap. Nếu muốn yêu cầu cả READ và WRITE, nên thiết kế kiểm tra hai permission một cách rõ ràng và test; không mặc định mask `3` nghĩa “bắt buộc cả hai bit” trong mọi API kiểm tra.

## 5. Ba thứ tự cần phân biệt

Nói “ACE đầu tiên quyết định quyền” là **mô tả chưa đủ**. Với `DefaultPermissionGrantingStrategy`, Javadoc mô tả thứ tự tìm kiếm gần đúng:

```text
for each requested Permission, theo thứ tự danh sách:
    for each SID, theo thứ tự danh sách:
        tìm ACE phù hợp đầu tiên với permission + SID
        nếu ACE grant:
            cho phép
        nếu ACE deny:
            ghi nhận từ chối, chuyển sang permission tiếp theo

nếu tất cả permission đã thử đều bị deny:
    từ chối

nếu không có ACE nào phù hợp:
    thử ACL cha nếu cho phép kế thừa
    nếu vẫn không có: NotFoundException
```

Sơ đồ này chỉ biểu đạt **nguyên tắc của chiến lược mặc định**; nó bỏ qua các chi tiết nội bộ như audit, bitmask, lỗi SID chưa tải và cách xử lý parent. Khi thay strategy, không tự áp dụng sơ đồ.

### 5.1. Thứ tự các ACE: first matching entry

Giả sử chỉ có **một** SID là Alice, chỉ kiểm tra READ. Các ACE nằm theo thứ tự:

| `ace_order` | SID | Permission | Granting |
| ---: | --- | --- | --- |
| 0 | Alice | READ | false |
| 1 | Alice | READ | true |

ACE phù hợp đầu tiên với cặp `READ + Alice` là ACE 0: **deny**. ACE ở index 1 không phải “bản sửa” tự động ghi đè index 0.

Nếu đảo thứ tự:

| `ace_order` | SID | Permission | Granting |
| ---: | --- | --- | --- |
| 0 | Alice | READ | true |
| 1 | Alice | READ | false |

ACE grant đứng đầu được tìm thấy trước và READ được cho phép. Đây là lý do thêm một ACE ở đầu hay cuối danh sách có thể thay đổi quyết định.

**Nhớ:** “đứng đầu” là đứng đầu **trong các ACE phù hợp với permission/SID đang xét**, không phải toàn bộ hàng `ACL_ENTRY` của tất cả đối tượng.

### 5.2. Thứ tự các permission được yêu cầu

`Acl.isGranted(List<Permission> permissions, List<Sid> sids, ...)` nhận một **danh sách** permission. Một danh sách có nhiều permission thể hiện các **lựa chọn có thể cho phép**, không mặc định là “phải có đủ tất cả”.

Ví dụ với Alice:

| ACE | SID | Permission | Granting |
| --- | --- | --- | --- |
| 0 | Alice | READ | false |
| 1 | Alice | WRITE | true |

Gọi:

```java
acl.isGranted(
    List.of(BasePermission.READ, BasePermission.WRITE),
    List.of(new PrincipalSid("alice")),
    false
);
```

Ở chiến lược mặc định, READ gặp deny; sau đó WRITE được thử và có grant → kết quả **true**. Như vậy không có một quy tắc toàn cục “hễ có deny thì mọi kiểm tra đều bị từ chối”.

Điểm cần nhấn mạnh: nếu nghiệp vụ đòi **READ VÀ WRITE**, không truyền cả hai vào một lần `isGranted` rồi tưởng đó là AND. Phải biểu diễn yêu cầu “cả hai” rõ ràng, ví dụ kiểm tra riêng từng quyền và kết hợp bằng AND trong policy đã được kiểm soát, đồng thời xử lý exception.

Thứ tự các permission còn quan trọng cho **ưu tiên tìm kiếm, ACE nào được xem trước và dấu vết audit**. Nếu có nhiều lựa chọn, nên chọn một thứ tự có ý nghĩa nghiệp vụ và test kết quả khi có deny/grant xen kẽ.

### 5.3. Thứ tự các SID

Một Authentication có thể được ánh xạ thành:

- `PrincipalSid("alice")`: SID cá nhân.
- `GrantedAuthoritySid("ROLE_EDITOR")`: SID nhóm/authority.
- `GrantedAuthoritySid("ROLE_AUDITOR")`: SID khác.

Giả sử Alice thuộc nhóm EDITOR. Với một permission READ duy nhất:

| ACE | SID | Permission | Granting |
| --- | --- | --- | --- |
| 0 | `ROLE_EDITOR` | READ | true |
| 1 | Alice | READ | false |

Nếu danh sách SID đầu vào kiểm tra Alice trước, deny cá nhân có thể được chọn trước nhánh grant nhóm. Nếu danh sách SID được xếp nhóm trước Alice, grant nhóm có thể thắng.

`DefaultPermissionGrantingStrategy` nhấn mạnh **thứ tự danh sách SID là quan trọng**; không dựa vào thứ tự tình cờ của collection, tên bảng hoặc cách token được serialize. `SidRetrievalStrategyImpl` thường tạo SID người dùng và các `GrantedAuthoritySid` từ `Authentication`; hãy xác minh cách hệ thống build danh sách và thứ tự thực trong phiên bản đang dùng.

Trong hệ thống có yêu cầu đặc biệt “user deny phải luôn thắng group grant”, hãy **chính thức hóa quy tắc đó** qua thứ tự SID được kiểm soát và/hoặc `PermissionGrantingStrategy` tùy biến có test chặt, thay vì hy vọng database tự sắp xếp đúng.

## 6. “Deny luôn ưu tiên” là một giả định sai

Cụm “deny-overrides” có thể là chính sách hợp lệ của một hệ thống khác, nhưng **không nên mặc định đó là ngữ nghĩa tổng quát của Spring Security ACL**.

Phân biệt:

- **ACE deny**: một cờ `granting=false` gắn với đúng permission và SID của đối tượng.
- **Deny-overrides toàn cục**: nếu bất cứ ACE deny nào áp dụng thì kết quả cuối đều deny, bất kể grant khác. Đây **không phải** kết luận có thể suy ra chỉ từ việc xuất hiện cờ deny.
- **First applicable**: xử lý theo ACE/SID/permission phù hợp đầu tiên, có tính đến thứ tự và quy tắc duyệt.
- **Any permission granted**: danh sách permission thay thế có thể cho phép nếu một permission khác được grant.

Ví dụ khi kiểm tra `List.of(READ, WRITE)`, explicit deny READ không ngăn một explicit grant WRITE đáp ứng điều kiện của lời gọi đó. Đó là ý nghĩa khác với yêu cầu nghiệp vụ “người dùng bị cấm READ tuyệt đối dù có WRITE”.

Để xây dựng deny-overrides thật sự, cần mô tả rõ: một deny cá nhân có chặn mọi group grant không? Deny theo mask có chặn quyền khác không? Parent ACL có được override không? Sau đó tùy biến `PermissionGrantingStrategy` hoặc xây policy ngoài ACL, kèm test integration.

**Đừng dùng một câu “deny thắng grant” làm tiêu chí kiểm thử** nếu chưa ghi rõ loại SID, permission, ACE, thứ tự và chiến lược cụ thể.

## 7. Kế thừa từ ACL cha: khi nào parent được xét?

Mỗi `Acl` có thể có `getParentAcl()` và cờ `isEntriesInheriting()`. Có quan hệ parent **chưa đủ** để ACE từ parent áp dụng: cần bật kế thừa.

Với chiến lược mặc định, khi không tìm được ACE phù hợp để ra quyết định trên ACL hiện tại, hệ thống có thể tiếp tục tìm trong parent ACL nếu:

1. `getParentAcl()` không null.
2. `isEntriesInheriting()` là `true`.
3. Danh sách SID và permission cho phép tiếp tục tìm theo chiến lược đang dùng.

```text
Document 42 ACL
  ACEs hiện tại có phù hợp?
      |
      +-- Có grant/deny có hiệu lực -> quyết định tại ACL hiện tại
      |
      +-- Không có ACE phù hợp
             |
             +-- entriesInheriting = false -> không dùng parent
             |
             +-- entriesInheriting = true + parent tồn tại
                        |
                        v
                 đánh giá parent ACL
```

**Không kết luận** “một ACE deny local sẽ bị một grant từ parent ghi đè” — explicit deny có thể chặn đường kế thừa cho permission được hỏi. Ngược lại, **không có ACE local** chưa phải deny: parent có thể cung cấp grant, hoặc cuối cùng hệ thống ném `NotFoundException` nếu không đủ thông tin.

Đặc biệt cẩn trọng với ACL phân cấp theo tổ chức, folder hoặc tenant. Một grant từ ACL cha có thể mở rộng quyền tới hàng loạt đối tượng con. Nếu có dữ liệu đa tenant, việc tham chiếu parent phải tôn trọng ranh giới tenant; ACL inheritance không thay thế điều kiện bảo vệ dữ liệu nền.

## 8. Không tìm được ACE không phải là một deny ACE

`Acl.isGranted(...)` là API quyết định, không phải getter trả default false trong mọi trường hợp. Theo Javadoc:

- `true`: có bằng chứng grant theo policy.
- `false`: có quyết định explicit deny theo strategy.
- `NotFoundException`: chiến lược không tìm ra cơ sở quyết định quyền.
- `UnloadedSidException`: ACL chỉ được tải cho một số SID, nhưng caller kiểm tra một SID chưa được tải.

Hệ quả:

```java
boolean allowed;
try {
    allowed = acl.isGranted(
        List.of(BasePermission.READ),
        sids,
        false
    );
} catch (NotFoundException ex) {
    allowed = false; // fail closed: thiếu thông tin ACL để grant
}
```

Đây là **fragment** minh họa xử lý no-match; cần tạo `acl` và `sids` từ nguồn tin cậy. Không bắt tất cả exception rồi return `true`. Nếu gặp `UnloadedSidException`, cần điều tra/đọc lại ACL với danh sách SID đầy đủ hoặc bảo đảm deny an toàn và ghi nhận lỗi cấu hình; đừng hiểu đó là explicit deny của một ACE.

`NotFoundException` khi đọc `AclService.readAclById(...)` còn có nghĩa **không có ACL cho ObjectIdentity đó**, khác với “ACL có tồn tại nhưng không có ACE phù hợp”. Hai tình huống cần được phân biệt trong audit/diagnostics, nhưng thường cùng dẫn tới **không cho phép** theo policy fail closed.

Không biến mất kết nối database, lỗi schema hay lỗi cache thành `NotFoundException` giả để ứng dụng hoạt động như không có ACL. Những lỗi hạ tầng cần xử lý riêng và không được làm lộ dữ liệu.

## 9. Thêm ACE: index, grant flag và cập nhật lưu trữ

Spring ACL cung cấp `MutableAcl.insertAce(int atIndexLocation, Permission permission, Sid sid, boolean granting)`. Tham số `atIndexLocation` là **vị trí trong danh sách ACE**, không phải ID bản ghi database. Có thể chèn đầu danh sách hoặc thêm cuối; việc chọn vị trí là một quyết định chính sách.

Ví dụ **thành phần trong ứng dụng Spring**, giả định đã có `MutableAclService` được cấu hình, `Document` là domain class thật và người gọi được cấp quyền quản trị ACL:

```java
import java.io.Serializable;
import org.springframework.security.acls.domain.ObjectIdentityImpl;
import org.springframework.security.acls.domain.PrincipalSid;
import org.springframework.security.acls.domain.BasePermission;
import org.springframework.security.acls.model.MutableAcl;
import org.springframework.security.acls.model.MutableAclService;
import org.springframework.security.acls.model.ObjectIdentity;
import org.springframework.security.acls.model.Sid;
import org.springframework.security.acls.model.NotFoundException;

public class DocumentAclAdmin {
    private final MutableAclService aclService;

    public DocumentAclAdmin(MutableAclService aclService) {
        this.aclService = aclService;
    }

    public void addReadRule(Serializable documentId,
                            String username,
                            boolean granting) {
        ObjectIdentity identity =
            new ObjectIdentityImpl(Document.class, documentId);
        Sid sid = new PrincipalSid(username);

        MutableAcl acl;
        try {
            acl = (MutableAcl) aclService.readAclById(identity);
        } catch (NotFoundException missing) {
            acl = aclService.createAcl(identity);
        }

        // Chèn lên đầu: thứ tự có thể ảnh hưởng quyết định.
        acl.insertAce(0, BasePermission.READ, sid, granting);
        aclService.updateAcl(acl);
    }
}
```

**Giải thích và giới hạn:**

- `addReadRule(..., true)` tạo một ACE **grant READ**; `false` tạo ACE **deny READ**.
- `insertAce(0, ...)` đứng trước các ACE cũ. `insertAce(acl.getEntries().size(), ...)` thêm ở cuối.
- `updateAcl(acl)` lưu thay đổi. Spring Security **không tự động tạo/cập nhật ACL** chỉ vì repository lưu Document.
- Phải phân quyền **ai được phép sửa ACL**; quản trị ACL là hành động bảo mật nhạy cảm, không cho người dùng tự chọn SID và granting tùy ý.
- Đừng chèn thêm ACE trùng nhau vô hạn; quản lý idempotency, version/concurrency, lịch sử thay đổi và thứ tự có chủ đích.
- Cấu hình transaction/ACL cache phải bảo đảm việc thay đổi quyền có hiệu lực đúng thời điểm. Khi có cache, kiểm tra invalidation và hành vi trong nhiều instance.

Ví dụ trên không phải file độc lập: phải có model `Document`, hạ tầng JDBC ACL, schema, datasource, ACL authorization strategy và transaction/config của ứng dụng.

### Có nên đặt deny trước toàn bộ grant?

Đó có thể là một **quy ước** để giảm xung đột cho cùng permission/SID, nhưng không nên coi là một định luật của Spring Security ACL. Vì evaluator còn xét thứ tự requested permissions/SIDs, một grant thuộc permission hoặc SID khác vẫn có thể làm kết quả thay đổi tùy trường hợp.

Quy ước tốt hơn là xác định xung đột ngay khi **ghi quyền**: không cho hai ACE có cùng `ObjectIdentity + Sid + Permission` nhưng opposite granting mà không có quy tắc priority rõ. Nếu business cho phép ghi đè, phải lưu/duy trì thứ tự và test hành vi khi cập nhật.

## 10. Đánh giá bằng Acl.isGranted thay vì tự duyệt getEntries

Một nhầm lẫn phổ biến là tự làm:

```java
// KHÔNG DÙNG làm policy chung.
boolean canRead = acl.getEntries().stream()
    .anyMatch(ace -> ace.isGranting()
        && ace.getPermission().equals(BasePermission.READ));
```

Code này sai vì **không kiểm tra SID của caller**, không xét deny ưu tiên, mask, parent ACL, unloaded SIDs hay permission strategy. Nó có thể cho Alice quyền chỉ vì có ACE grant READ cho Bob.

API để đánh giá là:

```java
boolean granted = acl.isGranted(
    List.of(BasePermission.READ),
    List.of(new PrincipalSid("alice")),
    false
);
```

Trong ứng dụng thật, danh sách SID nên được xây từ `Authentication` đã xác thực qua `SidRetrievalStrategy` hoặc policy phù hợp, không lấy username từ request tùy ý. `false` ở tham số thứ ba là **`administrativeMode`**, liên quan đến audit, **không phải** “bỏ qua quyền quản trị” hoặc “ép deny”. Nếu `administrativeMode=true`, theo contract, thao tác kiểm tra được coi là hoạt động quản trị và có thể không ghi audit.

Đừng đưa `List.of(BasePermission.READ, BasePermission.WRITE)` nếu nghiệp vụ yêu cầu **cả READ và WRITE**; list ở đây dùng như các permission có thể cho phép một quyết định. Đặt AND ở policy Java hoặc hai kiểm tra có xử lý exception minh bạch.

## 11. Tích hợp với PermissionEvaluator và @PreAuthorize

Trong Spring Security, `AclPermissionEvaluator` là lớp hỗ trợ nối ACL với các biểu thức `hasPermission(...)`. Ở ứng dụng Servlet có method security, có thể công bố:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.acls.AclPermissionEvaluator;
import org.springframework.security.acls.model.AclService;
import org.springframework.security.access.expression.method.DefaultMethodSecurityExpressionHandler;
import org.springframework.security.access.expression.method.MethodSecurityExpressionHandler;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class AclMethodSecurityConfig {

    @Bean
    static AclPermissionEvaluator aclPermissionEvaluator(
            AclService aclService) {
        return new AclPermissionEvaluator(aclService);
    }

    @Bean
    static MethodSecurityExpressionHandler expressionHandler(
            AclPermissionEvaluator evaluator) {
        DefaultMethodSecurityExpressionHandler handler =
            new DefaultMethodSecurityExpressionHandler();
        handler.setPermissionEvaluator(evaluator);
        return handler;
    }
}
```

Đây là **cấu hình thành phần**, cần các bean `AclService` và JDBC ACL/caching phù hợp. Nó không tự tạo bảng ACL hoặc ACE cho tài liệu mới; quá trình provisioning phải do ứng dụng quản lý.

Một service có thể dùng:

```java
import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class DocumentService {
    private final DocumentRepository documents;

    public DocumentService(DocumentRepository documents) {
        this.documents = documents;
    }

    @PreAuthorize(
        "hasAuthority('document:read') and " +
        "hasPermission(#id, 'com.example.documents.Document', 'READ')"
    )
    public Document readDocument(@P("id") Long id) {
        return documents.findById(id).orElseThrow();
    }
}
```

**Quan trọng:** chuỗi target type phải phù hợp với `ObjectIdentity` được sử dụng trong ACL thực. Nếu ACL lưu class `com.example.documents.Document`, truyền `"Document"` khi implementation yêu cầu tên class đầy đủ có thể làm không tìm thấy ACL.

Code minh họa trên chỉ là skeleton:

- Cần `DocumentRepository`, model và dữ liệu ACL thật của dự án.
- Việc gọi phải qua **Spring proxy** để `@PreAuthorize` được thực thi; self-invocation `this.readDocument(...)` có thể bypass.
- `hasPermission` được dùng cho ACL, nhưng **không thay thế tenant boundary**, business ownership constraints hoặc dữ liệu truy vấn có scope.
- Nếu `AclPermissionEvaluator` trả false, method security từ chối; phản hồi HTTP 403/404 phụ thuộc cấu hình, **không** do ACE tự tạo mã HTTP.
- Với quyền ghi, kiểm tra trước khi có side effect và truy vấn/transaction bảo vệ against TOCTOU. Một `@PostAuthorize` từ chối sau khi write đã commit không tự rollback giao dịch hoàn tất.

### Chính sách kết hợp tenant, trạng thái và ACL

Thường nên gắn nhiều điều kiện:

```java
@PreAuthorize(
    "hasAuthority('document:read') and " +
    "@tenantPolicy.canAccess(authentication, #id) and " +
    "hasPermission(#id, 'com.example.documents.Document', 'READ')"
)
```

`tenantPolicy` phải xác minh tenant thực qua server/database, không chỉ so sánh `X-Tenant-Id` với giá trị tự khai. Nếu tài liệu đã soft-deleted, archived, classified hoặc account đã suspended, các điều kiện đó có thể cần thực thi **ngoài ACL**. ACL là lớp cấp quyền trên object; nó không định nghĩa mọi quy tắc nghiệp vụ.

## 12. Java 17 chạy độc lập: cùng ACE, đổi thứ tự là đổi kết quả

Chương trình sau mô phỏng **một phần ngữ nghĩa của DefaultPermissionGrantingStrategy** với permission một bit, mask khớp chính xác, và không có ACL parent, caching, audit hoặc database. Nó không import Spring Security. Mục tiêu là thấy ba yếu tố: thứ tự ACE, thứ tự SID và danh sách permission thay thế.

Tạo file `AceOrderDemo.java`:

```java
import java.util.List;

public class AceOrderDemo {

    record Ace(String sid, String permission, boolean granting) {}

    enum Outcome {
        GRANT, DENY, NO_MATCH
    }

    static Outcome check(
            List<Ace> entries,
            List<String> requestedPermissions,
            List<String> sids) {

        boolean foundDeny = false;

        for (String permission : requestedPermissions) {
            boolean deniedThisPermission = false;

            for (String sid : sids) {
                for (Ace ace : entries) {
                    if (!ace.sid().equals(sid)
                            || !ace.permission().equals(permission)) {
                        continue;
                    }

                    if (ace.granting()) {
                        return Outcome.GRANT;
                    }

                    foundDeny = true;
                    deniedThisPermission = true;
                    break; // First matching ACE for this SID/permission.
                }

                if (deniedThisPermission) {
                    break; // Try the next requested permission.
                }
            }
        }

        return foundDeny ? Outcome.DENY : Outcome.NO_MATCH;
    }

    public static void main(String[] args) {
        List<Ace> denyFirst = List.of(
            new Ace("alice", "READ", false),
            new Ace("alice", "READ", true)
        );
        List<Ace> grantFirst = List.of(
            new Ace("alice", "READ", true),
            new Ace("alice", "READ", false)
        );

        List<Ace> alternatives = List.of(
            new Ace("alice", "READ", false),
            new Ace("alice", "WRITE", true)
        );

        List<Ace> principalAndGroup = List.of(
            new Ace("team", "READ", true),
            new Ace("alice", "READ", false)
        );

        System.out.println("Deny ACE first: " + check(
            denyFirst, List.of("READ"), List.of("alice")));

        System.out.println("Grant ACE first: " + check(
            grantFirst, List.of("READ"), List.of("alice")));

        System.out.println("READ or WRITE: " + check(
            alternatives, List.of("READ", "WRITE"), List.of("alice")));

        System.out.println("Principal SID first: " + check(
            principalAndGroup, List.of("READ"),
            List.of("alice", "team")));

        System.out.println("Group SID first: " + check(
            principalAndGroup, List.of("READ"),
            List.of("team", "alice")));

        System.out.println("No matching ACE: " + check(
            denyFirst, List.of("DELETE"), List.of("alice")));
    }
}
```

Chạy với JDK 17 trở lên:

```bash
javac AceOrderDemo.java
java AceOrderDemo
```

Stdout chính xác:

```text
Deny ACE first: DENY
Grant ACE first: GRANT
READ or WRITE: GRANT
Principal SID first: DENY
Group SID first: GRANT
No matching ACE: NO_MATCH
```

Giải thích:

- **Dòng 1–2:** hai ACE cùng SID/permission, đổi thứ tự làm đổi kết quả.
- **Dòng 3:** READ bị deny, nhưng WRITE là một permission thay thế được grant → kết quả grant.
- **Dòng 4–5:** cùng danh sách ACE nhưng đổi thứ tự SID được xét làm đổi kết quả.
- **Dòng 6:** không ACE nào khớp DELETE → trạng thái không đủ thông tin, **không đồng nghĩa explicit deny**.

**Giới hạn mô phỏng:** code dùng tên permission bằng chuỗi, không mô phỏng match bit mask grant/deny bất đối xứng, audit, UnloadedSidException, ACL cha hoặc tất cả chi tiết sản phẩm. Để xác nhận policy thực, bắt buộc viết test dùng `DefaultPermissionGrantingStrategy`/`AclImpl` và persistence ACL của Spring Security trong phiên bản đang triển khai.

## 13. Khi nào cần custom PermissionGrantingStrategy?

`DefaultPermissionGrantingStrategy` là lựa chọn chuẩn có luật duyệt rõ. Tuy nhiên một số tổ chức có chính sách khác:

- Deny từ principal **luôn** thắng grant của mọi group.
- Một deny ở child ACL **không** được parent override trong mọi trường hợp.
- Permission ADMINISTRATION có thể bao hàm một tập hành động theo quy ước riêng.
- Mọi yêu cầu phải thỏa cả hai permission (AND), không phải OR.
- Muốn áp dụng priority giữa principal, role và department một cách bất biến dù thứ tự SIDs được truyền vào thay đổi.

Nếu chọn chính sách như trên, hãy mô tả đầy đủ và cài đặt ở một thành phần tập trung như `PermissionGrantingStrategy` tùy biến hoặc policy domain riêng, thay vì lặp điều kiện `if` rải rác trên từng service.

Các câu hỏi nên trả lời trước khi viết custom strategy:

1. **Grant có được phép override explicit deny không?** Nếu có, khi nào?
2. **Deny thuộc một group có chặn grant cá nhân không?**
3. **Thứ tự SIDs có phải một phần của hợp đồng không?**
4. **Deny theo mask kết hợp có chặn từng permission con không?**
5. **Kế thừa parent có xử lý deny/missing thế nào?**
6. **Có giữ được hành vi audit và lỗi `NotFoundException`/`UnloadedSidException` không?**
7. **Các rule hiện tại có thay đổi khi nâng Spring Security version không?**

Chỉ thay chiến lược sau khi có **test bảng quyết định** cho những tình huống tranh chấp grant/deny. Với policy đơn giản như owner và tenant, đôi khi truy vấn database có điều kiện hoặc bean authorization Java phù hợp hơn một ACL framework tùy biến sâu.

## 14. Checklist kiểm thử ACL grant/deny/order

| Tình huống | Điều cần xác minh |
| --- | --- |
| Chỉ có ACE grant READ cho Alice | Alice đọc được, người khác không tự được cấp |
| Chỉ có ACE deny READ cho Alice | Alice bị từ chối, không có grant mặc định |
| Deny rồi grant cho cùng SID/permission | Order quyết định theo strategy; test cả thứ tự đảo |
| Grant rồi deny cho cùng SID/permission | Kết quả có thể đổi khi đảo ACE |
| Grant nhóm, deny cá nhân | Kết quả phụ thuộc SID order/strategy; không mặc định deny toàn cục |
| `List.of(READ, WRITE)` với READ deny, WRITE grant | Hiểu đây là permission thay thế, không phải AND |
| ACL child không có ACE match, inheritance on | Parent có thể được đánh giá |
| ACL child có explicit deny, parent grant | Deny local và inheritance tuân strategy; test |
| Inheritance off | Parent không được sử dụng để grant |
| No matching ACE cả child và parent | `NotFoundException`/xử lý fail closed |
| SID chưa tải | `UnloadedSidException` hoặc cơ chế kiểm tra tải SID |
| Mask grant nhiều bit, mask deny nhiều bit | Kiểm chứng quy tắc so khớp không giống nhau |
| ACL update thay đổi thứ tự | Quyết định thay đổi đúng, cache được làm mới |
| Object thuộc tenant khác | ACL không được vượt qua tenant boundary |
| DB lỗi khi tải ACL | Không cấp quyền, lỗi hạ tầng được ghi nhận đúng |
| Lời gọi qua Spring proxy | Annotation `hasPermission` được thực thi thật |
| Gọi nội bộ `this.method()` | Nhận diện nguy cơ bypass proxy |
| Người dùng sửa ACE qua API | Chỉ người được ủy quyền mới có thể sửa ACL |

### Các loại test nên có

**Unit test:** tạo ACL với ACE/SID/permission có thứ tự kiểm soát rồi gọi `isGranted(...)`; assert grant/deny/missing và các nhánh của custom strategy.

**Integration test:** dùng schema JDBC ACL, repository, transaction, cache và `@EnableMethodSecurity`. Bảo đảm các bản ghi `ace_order` được lưu và load theo đúng thứ tự, cập nhật ACL không để dữ liệu cache cũ, quyền bị thu hồi có hiệu lực.

**Security/negative test:** thử user khác tenant, không thuộc group, SID thiếu, quyền bị deny, token/role sai, tài liệu không có ACL; xác minh không có dữ liệu hoặc side effect trái phép.

**Audit test:** kiểm tra lý do được ghi nội bộ ở mức cần thiết, không log token/secret, không trả thông tin ACL chi tiết cho caller trái quyền. `administrativeMode` phải được dùng đúng mục đích, không nhầm với quyền ADMINISTRATION.

## 15. Các lỗi thực tế và cách khắc phục

| Lỗi | Vì sao sai | Cách sửa |
| --- | --- | --- |
| “Deny luôn thắng mọi grant” | Strategy duyệt permission, SID và ACE theo thứ tự; grant ở nhánh khác có thể thắng | Xác định chính sách thật, đọc Javadoc và test nhiều nhánh |
| Coi `ACL_ENTRY` là tập hợp không thứ tự | Có `ace_order` và vị trí `insertAce` | Quản lý thứ tự tường minh, test sau khi load |
| Dùng `isGranted(List.of(READ, WRITE), ...)` để yêu cầu cả hai quyền | Danh sách permission có thể cho phép một trong các lựa chọn | Viết yêu cầu AND tường minh |
| Coi thiếu ACE như explicit deny đã được lưu | No match có thể ném `NotFoundException` | Fail closed nhưng phân biệt trong logs/tests |
| Coi `NotFoundException` nghĩa business entity chắc chắn không tồn tại | Có thể thiếu ACL/ACE phù hợp | Kiểm tra dữ liệu domain và ACL riêng |
| Không xét `UnloadedSidException` | ACL được tải thiếu SID cho quyết định | Đọc ACL đúng các SID hoặc xử lý an toàn |
| Tự duyệt `getEntries()` và bỏ SID | Có thể lấy grant của người khác | Dùng `Acl.isGranted(...)` |
| Coi bit mask grant/deny đối xứng trong mọi trường hợp | Strategy mặc định có khác biệt giữa grant/deny | Test mask, không suy đoán chỉ từ bitwise |
| Quên `entriesInheriting` khi có ACL cha | Parent có thể áp dụng hoặc không | Xác minh cờ kế thừa và test child/parent |
| Tự cho ACL owner mọi quyền | ACL owner và quyền trên domain object không mặc nhiên giống nhau | Tách quyền sửa ACL với quyền đọc/ghi domain |
| Cho phép client chọn granting/index/SID | Người dùng có thể cấp quyền cho mình | Bảo vệ chặt endpoint cập nhật ACL, audit thay đổi |
| Kiểm tra ACL rồi query/write không scope | Race hoặc truy cập cross-tenant | Ràng buộc truy vấn theo tenant/owner và transaction |
| ACL thay đổi nhưng cache không làm mới | Thu hồi quyền không có hiệu lực ngay | Invalidate cache và test nhiều instance |
| Chỉ viết unit test mô phỏng | Không chứng minh framework chạy theo mô phỏng | Integration test với API thật và DB ACL |

## 16. Quy trình review một ACL có xung đột

Khi gặp bug “người dùng vẫn xem được dù có deny”, đừng đổi ACE một cách cảm tính. Hãy điều tra theo thứ tự:

1. Xác định **object identity** chính xác: class + ID, và domain object có thuộc đúng tenant không.
2. Xác định **permission** đang hỏi: READ, WRITE, một mask kết hợp hay danh sách thay thế; ghi nguyên thứ tự.
3. Xác định **SID list** lấy từ Authentication: principal và GrantedAuthority SIDs; ghi nguyên thứ tự.
4. Đọc **các ACE của ACL hiện tại theo ace_order**, kiểm tra grant/deny và mask.
5. Xác định **PermissionGrantingStrategy** thật đang dùng (default hay custom).
6. Kiểm tra **ACL parent**, cờ `entriesInheriting` và những ACE inherited có thể được xét.
7. Phân biệt kết quả **grant**, **explicit deny**, **no match** và **unloaded SID**, không trộn lỗi hạ tầng.
8. Kiểm tra **cache**, version và transaction sau lần thay đổi ACL.
9. Chạy test tái hiện với cùng permission/SID/ACE order và một test đảo thứ tự.
10. Sửa chính sách ở nguồn tập trung, bảo vệ API quản trị ACL và thêm regression test.

**Tóm tắt:** Trong Spring Security ACL, `granting=true/false` của một ACE chỉ là một thành phần quyết định. Để biết quyền cuối cùng, phải xét **permission order → SID order → ACE order**, ngữ nghĩa mask, parent inheritance và `PermissionGrantingStrategy`. `Acl.isGranted(...)` là điểm kiểm tra được hỗ trợ; đừng thay bằng tự tìm bất kỳ ACE grant trong database.

## Tài liệu chính thức

- [Spring Security — Domain Object Security (ACLs)](https://docs.spring.io/spring-security/reference/servlet/authorization/acls.html): mô hình ACL, ACE, permission bit mask, bảng lưu trữ và `insertAce`.
- [Spring Security API — DefaultPermissionGrantingStrategy](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/acls/domain/DefaultPermissionGrantingStrategy.html): thứ tự permission/SID, first matching ACE, grant/deny, `NotFoundException` và so khớp mask.
- [Spring Security API — Acl và isGranted](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/acls/model/Acl.html): hợp đồng kiểm tra quyền, kế thừa và SID được tải.
- [Spring Security API — AclImpl](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/acls/domain/AclImpl.html): `getEntries`, `insertAce`, `isEntriesInheriting`, `getParentAcl`.
- [Spring Security API — AclPermissionEvaluator](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/acls/AclPermissionEvaluator.html): tích hợp ACL với `hasPermission`.
- [Spring Security — ACL database schema](https://docs.spring.io/spring-security/reference/servlet/appendix/database-schema.html): cấu trúc `acl_entry`, `ace_order` và các bảng ACL.
