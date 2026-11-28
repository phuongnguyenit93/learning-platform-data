# Kiểm tra điều kiện trước khi ghi và giới hạn race condition

Trong **SPRING_DATA_LDAP**, ứng dụng Java thao tác với dịch vụ thư mục LDAP qua Spring Data LDAP repository, entity ODM và `LdapTemplate`. Mỗi entry có DN (*Distinguished Name*), các `objectClass` và thuộc tính chịu ràng buộc schema. Khi nhiều request hoặc nhiều instance cùng sửa một entry người dùng, nhóm hay cấu hình, câu hỏi quan trọng không chỉ là **ghi dữ liệu thế nào**, mà còn là **làm sao bảo đảm trạng thái kiểm tra vẫn đúng vào thời điểm ghi**.

Một luồng có vẻ hợp lý như “đọc entry → kiểm tra phiên bản/quyền/giá trị → ghi thay đổi” vẫn có thể gặp **race condition**. Trong khoảng thời gian giữa bước đọc và bước ghi, một luồng khác có thể cập nhật hoặc xóa entry. Spring Data LDAP không tự biến chuỗi thao tác này thành một giao dịch cách ly như các transaction của cơ sở dữ liệu quan hệ.

Bài học này phân biệt **kiểm tra trước ghi phục vụ nghiệp vụ** với **điều kiện được server kiểm tra cùng thao tác ghi**; giải thích LDAP Modify atomic trong phạm vi một entry, hai cách hạn chế lost update, xử lý xung đột, giới hạn giữa nhiều entry và cách kiểm thử thực tế.

## 1. Race condition xảy ra ở đâu?

Giả sử entry người dùng Lan đang có email cũ:

```ldif
dn: uid=lan,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: lan
cn: Lan Nguyen
sn: Nguyen
mail: lan@example.org
```

Hai người quản trị cùng đọc entry này rồi thay đổi email:

```text
Thời điểm    Admin A                       Admin B
---------    ---------------------------   ----------------------------
t0           Đọc mail=lan@example.org
t1                                         Đọc mail=lan@example.org
t2           Kiểm tra mail vẫn là cũ
t3                                         Kiểm tra mail vẫn là cũ
t4           Ghi mail=lan.a@example.org
t5                                         Ghi mail=lan.b@example.org
t6           Hiển thị "đã lưu"
t7                                         Hiển thị "đã lưu"
Kết quả      Giá trị của A bị ghi đè mà A không biết.
```

Đây là **lost update**: hai người cùng dựa vào một trạng thái đã đọc nhưng bản ghi sau ghi đè bản ghi trước. LDAP Modify có thể bảo đảm **mỗi request sửa một entry được áp dụng nguyên tử**, nhưng không tự bảo đảm request sau phải từ chối vì người viết đã đọc dữ liệu cũ.

Một biến thể khác là **TOCTOU** (*time-of-check to time-of-use*):

```text
Thread A:   lookup(DN) -> entry đang tồn tại
Thread B:                             delete(DN)
Thread A:                                         modify(DN) -> noSuchObject
```

Hoặc:

```text
Thread A:   search("(uid=lan)") -> chưa có người dùng
Thread B:                             add(uid=lan,...)
Thread A:                                         add(uid=lan,...) -> entryAlreadyExists
```

Một lần kiểm tra kết quả đúng ở `t0` **không chứng minh** điều kiện vẫn đúng ở `t1`. Cần xác định điều kiện nào chỉ để tạo thông báo sớm và điều kiện nào phải được **LDAP server cưỡng chế ngay khi ghi**.

## 2. Phân loại các điều kiện trước khi ghi

Không phải kiểm tra nào cũng giải quyết cùng một vấn đề:

| Điều kiện | Ví dụ | Kiểm tra ở đâu? | Có ngăn race condition một mình không? |
|---|---|---|---|
| Cú pháp dữ liệu | Email đúng định dạng; tên tài khoản không rỗng | Java service/validation | **Không** |
| DN hợp lệ | Tạo DN bằng `LdapNameBuilder` thay vì nối chuỗi | Client; server cũng kiểm tra LDAP DN | **Không** |
| Schema | `objectClass` cho phép thuộc tính, `sn` bắt buộc | LDAP server; có thể validate sớm ở client | Server cưỡng chế schema, nhưng **không** tự ngăn lost update |
| ACL / quyền ghi | Tài khoản bind có quyền sửa `mail` | LDAP server lúc xử lý yêu cầu | Quyền được kiểm tra khi ghi; không thay thế điều kiện phiên bản |
| Entry/parent tồn tại | DN đích hoặc DN cha hợp lệ | Tra cứu sớm và LDAP result code của thao tác ghi | Check riêng lẻ **không** |
| Giá trị đang là bản cũ | `appRevision = r7` trước khi sửa | Phải kiểm tra **cùng thao tác ghi** | **Có thể**, nếu dùng cơ chế conditional update đúng |
| Tính duy nhất | Không có hai entry cùng DN; một `uid` là duy nhất trong tenant | Server bảo đảm DN duy nhất; uniqueness của `uid` cần cơ chế riêng | Search trước ghi **không** |
| Quy tắc nhiều entry | Không xóa user khi vẫn còn ở nhóm quan trọng | Nghiệp vụ; cơ chế server/điều phối nhiều entry | Không bảo đảm toàn hệ thống bằng hai LDAP request độc lập |

**Nguyên tắc:** validate sớm để người dùng nhận lỗi rõ ràng, nhưng với điều kiện quan trọng cho tính đúng đắn, hãy để **server xác nhận tại điểm commit của thao tác LDAP**. Nếu không có cơ chế cưỡng chế tương ứng, hãy coi khả năng race còn tồn tại và thiết kế cách phát hiện/khắc phục.

## 3. Những bảo đảm thật sự của một LDAP Modify

LDAPv3 có các thao tác riêng như Add, Delete, Modify, ModifyDN và Compare. Theo RFC 4511, các thay đổi nằm trong **một `ModifyRequest`** cho **một entry** được xử lý theo thứ tự và như **một thao tác nguyên tử**: khi một thay đổi thất bại, request đó không được áp dụng một phần.

Ví dụ sửa hai thuộc tính cùng một entry:

```text
ModifyRequest: uid=lan,ou=people,dc=example,dc=org
  replace mail        = lan.new@example.org
  replace description = Updated by profile service

=> Server chấp nhận cả hai thay đổi hoặc từ chối request.
```

Với Spring LDAP, `LdapTemplate.modifyAttributes(...)` có thể gửi các `ModificationItem` trong cùng một thao tác:

```java
import javax.naming.Name;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;
import org.springframework.ldap.core.LdapTemplate;

void changeContact(LdapTemplate ldapTemplate, Name relativeDn,
                   String newEmail, String description) {
    ModificationItem[] changes = {
        new ModificationItem(
                DirContext.REPLACE_ATTRIBUTE,
                new BasicAttribute("mail", newEmail)),
        new ModificationItem(
                DirContext.REPLACE_ATTRIBUTE,
                new BasicAttribute("description", description))
    };
    ldapTemplate.modifyAttributes(relativeDn, changes);
}
```

Ở đây, `relativeDn` tương đối với `LdapContextSource.base`. Ví dụ base kết nối là `dc=example,dc=org` thì tên cần truyền là `uid=lan,ou=people`; không tự gắn lặp suffix.

**Những điều LDAP Modify không tự bảo đảm:**

- Không tự từ chối request B chỉ vì B đã đọc một snapshot trước khi A ghi.
- Không tạo transaction ACID chung cho nhiều entry (ví dụ user và hai group).
- Không tự bảo đảm phiên bản vừa ghi đã nhìn thấy ngay khi đọc từ **replica khác**.
- Không tự hiểu quy tắc “chỉ sửa khi giá trị email vẫn chưa đổi” nếu request không có điều kiện đó.

Đừng nhầm tính **atomic của từng ModifyRequest** với tính **cách ly giữa nhiều thao tác** hoặc tính nhất quán xuyên replica.

## 4. Khi nào kiểm tra riêng lẻ là đủ?

Có những kiểm tra hữu ích nhưng không cần biến thành cơ chế compare-and-swap:

1. **Cú pháp/định dạng:** từ chối email rỗng hoặc DN chứa input không hợp lệ trước khi gửi LDAP request.
2. **Thông báo nghiệp vụ:** kiểm tra nhóm tồn tại để hiển thị lời giải thích thân thiện; vẫn xử lý `noSuchObject` nếu entry bị xóa sau lần kiểm tra.
3. **Thêm một giá trị riêng lẻ:** một `ModifyRequest` với `ADD_ATTRIBUTE` có thể thêm một member vào nhóm mà không phải đọc toàn bộ danh sách `member` rồi ghi đè.
4. **Tạo entry theo DN cố định:** gửi LDAP `AddRequest` để server thực thi tính duy nhất của **DN**, thay vì `lookup` trước rồi mới `add`.

Ví dụ thêm đúng một DN vào `groupOfNames.member`:

```java
import javax.naming.Name;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;
import org.springframework.ldap.core.LdapTemplate;

void addMember(LdapTemplate ldapTemplate, Name groupRelativeDn,
               Name userFullDn) {
    ModificationItem item = new ModificationItem(
            DirContext.ADD_ATTRIBUTE,
            new BasicAttribute("member", userFullDn.toString()));
    ldapTemplate.modifyAttributes(
            groupRelativeDn, new ModificationItem[] {item});
}
```

LDAP server sẽ kiểm tra schema/ACL và quy tắc xử lý giá trị đã tồn tại. Khi giá trị `member` đã có, server có thể trả `attributeOrValueExists`; khi group bị xóa, có thể trả `noSuchObject`. **Đừng đọc toàn bộ member, thêm vào `List` trong Java rồi `REPLACE_ATTRIBUTE` cả danh sách**, vì thao tác đó dễ ghi đè thay đổi của người khác.

Điều kiện “không có entry nào cùng DN” được LDAP Add cưỡng chế tại server. Nhưng yêu cầu **`uid` duy nhất trên tất cả container/tenant** không được bảo đảm chỉ bằng việc Add dưới một DN: hai DN khác nhau vẫn có thể mang cùng `uid`. Trường hợp này cần quy tắc đặt tên, cơ chế uniqueness của server hoặc dịch vụ cấp phát định danh chung.

## 5. Optimistic concurrency: lưu và kiểm tra phiên bản của entry

Nếu hai writer cùng thay đổi một thuộc tính hoặc một nhóm thuộc tính, ta cần biết **snapshot mà request đang dựa vào** còn là bản mới nhất hay không. Một giải pháp phổ biến là dùng *optimistic concurrency control*.

Mô hình:

```text
Entry ban đầu:
  mail        = lan@example.org
  appRevision = 7

Admin A đọc revision=7
Admin B đọc revision=7
           |
Admin A: conditional write expected=7 -> mail mới, revision=8
           |
Admin B: conditional write expected=7 -> CONFLICT (revision hiện tại != 7)
```

`appRevision` là **thuộc tính ví dụ do ứng dụng tự quản lý**, **không phải** thuộc tính mặc định của `inetOrgPerson`. Trước khi dùng trong production, cần mở rộng schema/objectClass thích hợp, xác định syntax và single-value, cấp ACL đúng; mọi writer liên quan phải tuân thủ protocol đổi revision.

Có thể dùng một token revision duy nhất cho mỗi lần cập nhật, chẳng hạn UUID mới, thay vì số nguyên, để giảm nguy cơ **ABA** (trạng thái đổi đi rồi quay lại cùng token). Định danh ổn định như `entryUUID`/`objectGUID` thường giúp biết **entry nào**, nhưng không tự thay thế token biểu thị **lần cập nhật nào**.

### 5.1. Đọc snapshot cần để tạo điều kiện

Ví dụ Java 17 với `LdapTemplate`:

**`PersonSnapshot.java`**

```java
package com.example.ldap;

public record PersonSnapshot(
        String revision,
        String email
) {}
```

**`PersonEmailStore.java` — phần đọc**

```java
package com.example.ldap;

import javax.naming.Name;
import javax.naming.NamingException;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;

public class PersonEmailStore {
    private final LdapTemplate ldapTemplate;

    public PersonEmailStore(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public PersonSnapshot load(Name relativeDn) {
        AttributesMapper<PersonSnapshot> mapper = attrs ->
                new PersonSnapshot(
                        required(attrs, "appRevision"),
                        optional(attrs, "mail"));

        return ldapTemplate.lookup(relativeDn, mapper);
    }

    private static String required(Attributes attrs, String name)
            throws NamingException {
        Attribute attr = attrs.get(name);
        if (attr == null || attr.size() == 0) {
            throw new IllegalStateException(
                    "Không thể đọc revision/thuộc tính: " + name);
        }
        return (String) attr.get();
    }

    private static String optional(Attributes attrs, String name)
            throws NamingException {
        Attribute attr = attrs.get(name);
        return attr == null || attr.size() == 0
                ? null : (String) attr.get();
    }
}
```

Để gọi:

```java
import javax.naming.Name;
import org.springframework.ldap.support.LdapNameBuilder;

Name relativeDn = LdapNameBuilder.newInstance("ou=people")
        .add("uid", "lan")
        .build();
PersonSnapshot snapshot = store.load(relativeDn);

// UI/API mang snapshot.revision() như version/ETag của lần đọc.
// Không được coi việc load() tự tạo khóa bảo vệ khỏi ghi đè.
```

**Quan trọng:** `load()` chỉ lấy bản đọc. Nếu sau đó gọi `modifyAttributes` bằng `REPLACE_ATTRIBUTE` thông thường, race condition **vẫn còn**. Cần một trong các cơ chế **conditional update ngay tại server** sau đây.

## 6. Cách 1: dùng LDAP Assertion Control (RFC 4528)

LDAP Assertion Control cho phép client gắn một **điều kiện filter** vào thao tác LDAP như Modify, Delete hoặc ModifyDN (khi server hỗ trợ). Server phải đánh giá điều kiện trên entry đích **như một phần của thao tác**, không phải một `CompareRequest` riêng rồi mới ghi.

Ví dụ ý tưởng:

```text
ModifyRequest:
  object: uid=lan,ou=people,dc=example,dc=org
  controls:
    Assertion Control
      OID        = 1.3.6.1.1.12
      critical   = true
      condition  = (appRevision=7)
  changes:
    replace mail        -> lan.new@example.org
    replace appRevision -> 8
```

Nếu entry còn `appRevision=7`, server có thể chấp nhận request và đổi cả email/revision. Nếu điều kiện không còn đúng, server trả lỗi **`assertionFailed (122)`** và **không áp dụng** thay đổi. Nếu server không hiểu **critical control**, nó phải từ chối theo cơ chế LDAP (ví dụ `unavailableCriticalExtension (12)`) thay vì âm thầm bỏ qua điều kiện.

### 6.1. Lưu ý khi tích hợp Java/Spring LDAP

Với JNDI, interface `javax.naming.ldap.LdapContext` hỗ trợ `setRequestControls(...)` và `BasicControl` có thể chứa control OID, criticality và giá trị BER. Tuy nhiên, giá trị của Assertion Control là **LDAP Filter được mã hóa BER theo RFC 4528**, **không phải** mảng byte UTF-8 của chuỗi `"(appRevision=7)"`.

Đoạn **pseudocode** sau diễn tả thứ tự thao tác, cố ý không phải mã biên dịch hoàn chỉnh:

```java
// PSEUDOCODE: encodeFilterBer(...) cần ASN.1/BER encoder đúng RFC 4511.
// Dùng LdapContext cho phép gắn request control trước một ModifyRequest.
byte[] assertionBer = encodeFilterBer("(appRevision=7)");
Control assertion = new BasicControl(
        "1.3.6.1.1.12", true, assertionBer);

ldapContext.setRequestControls(new Control[] { assertion });
try {
    ldapContext.modifyAttributes(relativeDn, changes);
} finally {
    ldapContext.setRequestControls(null);
    ldapContext.close();
}
```

Không copy pseudocode này trực tiếp vào dự án nếu chưa có thư viện encode LDAP Filter BER, chưa kiểm chứng server hỗ trợ control và chưa chuẩn hóa đường đóng/trả context. Với Spring LDAP, `LdapTemplate` có các điểm mở rộng cho context/DirContext processing ở một số API, nhưng **không mặc định mọi `repository.save()` đều gửi Assertion Control**. Hãy kiểm tra tính tương thích API, pooling và control lifecycle của phiên bản được sử dụng.

Chọn **`critical=true`** với điều kiện bắt buộc để tránh trường hợp server bỏ qua kiểm tra mà vẫn ghi dữ liệu. Kiểm thử cả kịch bản server không hỗ trợ control trước khi triển khai.

**Cẩn trọng khi dùng metadata làm revision:** `modifyTimestamp` là operational attribute thường được server duy trì, nhưng độ phân giải, thời điểm ghi, quyền đọc và behavior khi replication khác nhau; hai lần thay đổi nhanh có thể làm nó không đủ làm token duy nhất. `uSNChanged` trên Active Directory cũng không phải version toàn cục độc lập với replica. Nếu dùng chúng làm tiền điều kiện, phải chứng minh semantics của backend, không coi chúng là CAS token phổ quát.

## 7. Cách 2: một ModifyRequest kiểm tra phiên bản bằng xóa giá trị cũ

Khi backend không hỗ trợ Assertion Control, một phương án hữu ích cho **thuộc tính revision ứng dụng tự quản lý** là đưa cả việc **xóa revision cũ**, **thêm revision mới** và **thay đổi dữ liệu** vào **cùng một `ModifyRequest`**.

Theo LDAP Modify, nếu một yêu cầu **xóa giá trị cụ thể** của thuộc tính nhưng giá trị đó không tồn tại, server phải trả lỗi; và vì mọi thay đổi trong request được áp dụng nguyên tử, các thay đổi khác trong request **không được commit**. Do đó, request tiếp theo mang expected revision đã cũ sẽ bị từ chối.

Ví dụ:

```text
Entry hiện tại: appRevision = r7

ModifyRequest A:
  delete appRevision: r7
  add    appRevision: r8
  replace mail: lan.a@example.org
  => SUCCESS

ModifyRequest B (vẫn nghĩ revision là r7):
  delete appRevision: r7   <-- giá trị r7 không còn
  add    appRevision: r9
  replace mail: lan.b@example.org
  => FAIL; tất cả thay đổi của B không được áp dụng
```

Phương án này yêu cầu **server tuân thủ semantics Modify của LDAP**, revision có giá trị **single-valued** với schema cho phép thao tác xóa/thêm, và **mọi writer** phải duy trì quy tắc đổi revision. Trong schema có ràng buộc khiến việc xóa một thuộc tính bắt buộc bị từ chối ngay cả khi request thêm lại, cần kiểm thử hoặc chọn Assertion Control thay vì giả định thao tác luôn được chấp nhận.

**`PersonEmailStore.java` — phương thức cập nhật có điều kiện** (thêm vào class ở mục 5):

```java
import java.util.UUID;
import javax.naming.Name;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;

public String updateEmailIfRevisionMatches(
        Name relativeDn, String expectedRevision, String newEmail) {

    if (expectedRevision == null || expectedRevision.isBlank()) {
        throw new IllegalArgumentException("Thiếu expectedRevision");
    }
    if (newEmail == null || newEmail.isBlank()) {
        throw new IllegalArgumentException("Email không được rỗng");
    }

    String newRevision = UUID.randomUUID().toString();

    ModificationItem[] changes = {
        new ModificationItem(
                DirContext.REMOVE_ATTRIBUTE,
                new BasicAttribute("appRevision", expectedRevision)),
        new ModificationItem(
                DirContext.ADD_ATTRIBUTE,
                new BasicAttribute("appRevision", newRevision)),
        new ModificationItem(
                DirContext.REPLACE_ATTRIBUTE,
                new BasicAttribute("mail", newEmail))
    };

    // Một thao tác LDAP Modify; không tách thành ba lời gọi.
    ldapTemplate.modifyAttributes(relativeDn, changes);
    return newRevision;
}
```

Đây là mã minh họa **logic ghi** có thể gắn vào `PersonEmailStore`; `appRevision` phải tồn tại trong entry và được schema cho phép. Method không tự chuyển lỗi thành HTTP status, vì Spring LDAP/JNDI có nhiều lớp exception tùy nguyên nhân.

Khi một writer gửi `expectedRevision` không còn tồn tại, server có thể trả result code **`noSuchAttribute (16)`** cho bước xóa revision; Spring LDAP sẽ chuyển đổi ngoại lệ theo lớp `NamingException`/`DataAccessException` phù hợp phiên bản. **Đừng tự động gán mọi `noSuchAttribute` là “409 conflict”** khi request còn thao tác khác hoặc server có schema/ACL không như mong đợi. Lớp service cần phân loại lỗi trong ngữ cảnh operation và có thể đọc lại entry để xác định revision thực.

**Tại sao `REPLACE_ATTRIBUTE("appRevision", next)` đơn lẻ không đủ?** Vì `REPLACE_ATTRIBUTE` không đòi giá trị cũ khớp `expectedRevision`. Hai luồng đều có thể ghi đè mà không phát hiện xung đột. Tính nguyên tử của từng request không đồng nghĩa với tính điều kiện của request.

## 8. Xây API để trả conflict thay vì lặng lẽ ghi đè

Trong một API chỉnh sửa thông tin, nên trả kèm **revision** khi đọc:

```json
{
  "dn": "uid=lan,ou=people,dc=example,dc=org",
  "displayName": "Lan Nguyen",
  "email": "lan@example.org",
  "revision": "9e19ad6e-87db-49d1-b5dd-8d451b29e5cd"
}
```

Client gửi bản sửa kèm revision đã đọc. Backend thực hiện một conditional write theo một trong hai cách ở trên.

```text
GET /people/lan
  -> email cũ, revision=r7
          |
          v
PUT /people/lan
  body: email mới; expectedRevision=r7
          |
          v
Conditional LDAP Modify
  |
  +-- Thỏa điều kiện   -> ghi; trả revision mới
  |
  +-- Không còn khớp  -> CONFLICT; trả trạng thái mới có kiểm soát
  |
  +-- Lỗi ACL/schema/network -> lỗi tương ứng; không báo là conflict
```

Nếu xây REST API, có thể dùng `ETag`/`If-Match` và trả `412 Precondition Failed` khi version của tài nguyên đã thay đổi (hoặc `409 Conflict` theo contract ứng dụng). Quan trọng hơn mã HTTP cụ thể là **không trả 200 thành công khi thao tác đã bị từ chối** và **không tự retry bằng cách ghi đè snapshot mới nhất** khi người dùng chưa giải quyết xung đột.

Khi gặp conflict:

1. Thông báo bản đang sửa đã lỗi thời.
2. Đọc lại **từ nguồn ghi phù hợp** để có revision và nội dung mới nhất theo semantics backend.
3. Cho người dùng xem khác biệt hoặc tính lại thay đổi nghiệp vụ.
4. Gửi request có revision mới khi người dùng đồng ý; không tự đổi `expectedRevision` mà giữ nguyên dữ liệu cũ rồi ghi lại.

Với thao tác có thể retry sau lỗi mạng, cần phân biệt **“server chưa ghi”** với **“server đã ghi nhưng client không nhận response”**. Tra cứu lại revision/giá trị hoặc dùng operation ID/idempotency design thích hợp trước khi lặp lại một thao tác không idempotent.

## 9. Những điều kiểm tra trước ghi **không** thể bảo đảm

### 9.1. `exists()` rồi `bind()` không bảo vệ tính duy nhất

Mẫu không an toàn:

```java
// Giữa hai lời gọi có thể có request khác tạo entry.
if (!ldapTemplate.nameExists(relativeDn)) {
    // Gọi bind/create theo API phù hợp...
}
```

Ngay cả khi `nameExists` trả false, entry có thể được tạo ngay sau đó. Nếu cần tạo entry tại DN chưa tồn tại, **gửi LDAP Add** và để server phát hiện DN trùng (result code `entryAlreadyExists (68)`). Khi nhiều container có thể chứa cùng `uid`, DN trùng và `uid` trùng là hai vấn đề khác nhau.

### 9.2. LDAP Compare rồi Modify vẫn có TOCTOU

`CompareRequest` là một thao tác giao thức riêng, có thể xác nhận `(appRevision=r7)` vào lúc so sánh. Nhưng trình tự:

```text
Compare(appRevision=r7) -> true
                  [writer khác sửa entry]
Modify(mail=...)    -> vẫn có thể ghi đè
```

vẫn có race. Để chặn lost update, phải gắn điều kiện vào **cùng** operation ghi hoặc dùng server-side mechanism tương đương.

### 9.3. Thêm thành viên vào nhóm và xóa user là hai entry

Ví dụ:

```text
Thread A: kiểm tra uid=lan tồn tại
Thread B: xóa uid=lan
Thread A: thêm DN của Lan vào group.member
```

Kết quả có thể là nhóm chứa **tham chiếu DN đã không còn entry**. Cả request xóa user lẫn request sửa group đều có thể thành công theo LDAP server; mỗi request chỉ bảo đảm quy tắc của entry mình thao tác.

Một số backend cung cấp referential integrity plugin, overlay hoặc transaction extension. **Không mặc định** mọi server có chức năng đó. Khi cần nhất quán nhiều entry, cân nhắc:

- Server-side referential integrity / uniqueness constraint được hỗ trợ và bật đúng.
- LDAP Transactions extension (RFC 5805) **nếu** server/client thực sự hỗ trợ và đã kiểm thử.
- Điều phối theo một writer/queue có kiểm soát, phiên bản hóa và reconciliation job để sửa liên kết sai.
- Thiết kế hệ thống chịu **eventual consistency** ở những quan hệ cho phép, nhưng không dùng dữ liệu chưa xác minh để ra quyết định cấp quyền quan trọng.

Một distributed lock ở tầng ứng dụng có thể giảm tranh chấp giữa các instance tham gia, nhưng **không chặn writer ngoài hệ thống**, không tự tạo transaction trên LDAP server và có thể thất bại khi lease hết hạn hoặc network partition.

### 9.4. Rename/move không chỉ là sửa một thuộc tính

`ModifyDN` đổi tên hoặc chuyển entry sang container khác theo khả năng server. Kiểm tra “DN đích chưa tồn tại” trước khi rename vẫn là TOCTOU. Phải xử lý lỗi đích trùng, không đủ quyền và thay đổi tham chiếu `member` ở group.

Nếu entry mang thuộc tính revision, cần xét rõ khi rename: DN cũ có thể mất hiệu lực dù token vẫn giữ nguyên, hoặc đối tượng được chuyển qua naming context/replica khác. Đừng chỉ dựa vào `uid` như khóa bất biến; xác định đúng identity của entry và thao tác cần bảo vệ.

## 10. Repository `save` và optimistic locking có tự hoạt động không?

Trong nhiều công nghệ Spring Data khác, người học thường thấy `@Version` và suy ra `repository.save(entity)` luôn từ chối update khi có writer khác. **Không nên mang giả định đó sang Spring Data LDAP.**

Ví dụ:

```java
public interface PersonRepository
        extends org.springframework.data.ldap.repository.LdapRepository<PersonEntry> {
}
```

`LdapRepository<T>` dùng entity ODM có `@Entry` và `@Id Name`; `save` thực hiện các thao tác tương ứng qua tầng LDAP. Nó **không tự động biến mọi cập nhật thành CAS** chỉ vì ứng dụng đã đọc entity trước đó. Khi cần bảo vệ lost update, phải xác nhận rõ phiên bản Spring Data LDAP và cơ chế conditional write được dùng trong đường ghi thực tế.

Một phương án kiến trúc là:

```text
PersonRepository   -> đọc entity, truy vấn thông thường
PersonWriteService -> kiểm tra yêu cầu + conditional LdapTemplate Modify
                            |
                            v
                       LDAP server
```

Khi cập nhật chỉ một thuộc tính đã xác minh, `LdapTemplate.modifyAttributes` với `ModificationItem` mô tả thay đổi cụ thể thường dễ kiểm soát hơn chu trình “đọc toàn entity → sửa một field → save lại cả entity”.

**Cũng không phải** mọi thay đổi đều cần optimistic lock. Cập nhật độc lập một giá trị đa trị bằng Add/Delete hoặc thao tác idempotent có thể phù hợp hơn, miễn là nghiệp vụ chấp nhận semantics của server và có chính sách retry.

## 11. Replica, topology và read-after-write

Một ứng dụng LDAP có thể đọc từ replica A nhưng ghi qua writable server B:

```text
                 Application
                  /        \
                 v          v
            Read replica   Write server
                 A             B
                 |             |
                 +-- replication --+
                       (có độ trễ)
```

Nếu A chưa nhận dữ liệu mới từ B, lần đọc sau khi ghi có thể trả **revision cũ**. Điều này không chứng minh conditional write trên B thất bại; chỉ là khả năng **replication lag**. Ngược lại, writer gửi conditional update đến hai writable server khác nhau trước khi replica hội tụ có thể gặp hành vi xung đột/giải quyết replication phụ thuộc backend.

Đối với luồng cần đọc–sửa–ghi nhất quán, phải xác định rõ:

1. Nơi nhận **write** là server/naming context nào.
2. Nguồn **read** được phép cung cấp revision cho CAS.
3. Có đảm bảo **read-your-writes** hoặc đọc trên cùng writable authority không.
4. Khi referral/failover xảy ra, operation có thể được định tuyến sang server nào.
5. Khi dữ liệu đa vùng chưa hội tụ, API báo lỗi hoặc hiển thị trạng thái gì.

LDAP Modify atomic ở một server **không tự cung cấp global serializability** trên topology có replication. Kiểm thử trên cấu hình production tương đương nếu consistency là yêu cầu quan trọng.

## 12. Bảo mật và tính đúng đắn cùng phải được kiểm soát

Trước thao tác ghi người dùng/nhóm:

| Bước | Điều cần thực hiện |
|---|---|
| Xác thực | Xác định caller, bind/service identity và tenant hợp lệ |
| Phân quyền | Kiểm tra quyền nghiệp vụ ở app; LDAP server vẫn phải cưỡng chế ACL tại thời điểm ghi |
| Xác định target | Tra đúng DN/entry identity, tránh tự ghép DN từ input chưa xác minh |
| Validate dữ liệu | Schema, format, giới hạn độ dài, thuộc tính được phép sửa |
| Điều kiện trạng thái | Revision/giá trị cũ được server kiểm tra trong cùng Modify nếu nghiệp vụ cần |
| Giới hạn tác động | Chỉ sửa các thuộc tính liên quan, không ghi đè vô ý danh sách đa trị |
| Audit | Ghi action, outcome, revision đã làm sạch, request ID; không ghi password/bind secret |

`LdapQueryBuilder` và `LdapNameBuilder` hỗ trợ escape dữ liệu ở các **cú pháp khác nhau**: filter khác DN. Đối với Assertion Control, còn phải mã hóa filter theo **BER**, không thể coi mọi chuỗi filter đã escape là control value hợp lệ.

Không lấy toàn bộ `Attributes` rồi ghi log để điều tra conflict: entry có thể chứa thông tin nhạy cảm như email, số điện thoại, nhóm quyền hoặc thuộc tính xác thực. Chỉ log những trường metadata đủ để điều tra mà không tăng bề mặt lộ dữ liệu.

Trong hệ thống phân quyền, “đọc thấy user chưa thuộc nhóm” rồi quyết định cấp quyền không đủ để loại trừ thay đổi đồng thời. Phải phân biệt việc **cấp quyền thành công** với **trạng thái quyền hiện tại** sau khi backend đã áp dụng mọi quy tắc nhóm lồng nhau, ACL và replication.

## 13. Thiết kế kiểm thử race condition có thể lặp lại

Unit test kiểm tra việc xây danh sách `ModificationItem` là hữu ích nhưng **không chứng minh** tính atomic của LDAP server. Cần integration test với directory có schema chứa `appRevision` hoặc backend thực sự hỗ trợ Assertion Control.

### 13.1. Kịch bản hai writer cùng expected revision

Fixture:

```text
DN          = uid=lan,ou=people,dc=example,dc=org
mail        = lan@example.org
appRevision = r7
```

Dùng hai thread, cho chúng cùng đọc `r7`, sau đó mở `CountDownLatch` để gửi hai conditional write gần như đồng thời:

```text
Thread A: update(expected=r7, mail=a@example.org, next=r8)
Thread B: update(expected=r7, mail=b@example.org, next=r9)
                         |
                         v
Kết quả mong đợi:
  Số request SUCCESS = 1
  Số request conflict do revision cũ = 1
  Email/revision cuối cùng = cặp giá trị của writer thành công
```

Ví dụ **khung kiểm thử JUnit 5** cho một store đã chuẩn hóa ngoại lệ stale revision thành `RevisionConflictException` (lớp này do ứng dụng định nghĩa):

```java
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

@Test
void oneWriterWinsWhenBothUseSameRevision() throws Exception {
    String oldRevision = store.load(userRelativeDn).revision();

    CountDownLatch start = new CountDownLatch(1);
    ExecutorService executor = Executors.newFixedThreadPool(2);
    try {
        Future<String> a = executor.submit(() -> {
            start.await();
            return store.updateEmailIfRevisionMatches(
                    userRelativeDn, oldRevision, "a@example.org");
        });
        Future<String> b = executor.submit(() -> {
            start.await();
            return store.updateEmailIfRevisionMatches(
                    userRelativeDn, oldRevision, "b@example.org");
        });
        start.countDown();

        // Khung kiểm thử: thu outcome từng Future, phân loại exception
        // thành SUCCESS / RevisionConflictException / lỗi khác.
        // Assert 1 SUCCESS + 1 CONFLICT và đọc lại email/revision.
    } finally {
        executor.shutdownNow();
    }
}
```

Đoạn khung thể hiện cách gây tranh chấp; để có **test hoàn chỉnh**, cần triển khai bộ phân loại lỗi và các assertion outcome, không được coi bất kỳ exception nào cũng là conflict. Hãy dọn lại fixture trước/sau mỗi test để tránh test khác tác động song song. Trong test thực, có thể dùng `CountDownLatch` bổ sung để bảo đảm cả hai thread **đã sẵn sàng trước khi phát lệnh**, thay vì chỉ dựa vào timing/sleep.

### 13.2. Ma trận tình huống nên kiểm tra

| Trường hợp | Điều cần xác nhận |
|---|---|
| Một writer với revision hợp lệ | Ghi thành công; email và revision cùng đổi |
| Hai writer có cùng revision | Chỉ một thành công; writer còn lại bị từ chối rõ ràng |
| Revision không tồn tại | Không sửa email; lỗi được phân loại đúng |
| Entry bị xóa sau khi đọc | Thao tác ghi thất bại với trạng thái entry đã biến mất, không tạo lại nhầm |
| Caller không có quyền sửa email/revision | Server từ chối; không có thay đổi một phần |
| Schema không cho phép `appRevision` | Báo lỗi cấu hình/schema, **không** trả là conflict |
| Assertion Control không được hỗ trợ | Với critical control, request bị từ chối thay vì bỏ qua điều kiện |
| Hai thay đổi trong một `ModifyRequest`, thay đổi thứ hai lỗi | Không có thay đổi thứ nhất được commit |
| Reader đọc qua replica đang trễ | Không nhầm snapshot replica cũ với phiên bản authoritative |
| Rename/move xảy ra đồng thời | Phân biệt DN cũ không còn tồn tại, đích trùng hoặc lỗi ACL |
| Thêm member cùng lúc từ hai request | Không làm mất các thành viên khác; xử lý duplicate value |
| Lỗi mạng sau khi gửi Modify | Kiểm tra outcome qua revision/readback trước khi retry không an toàn |

Không nên chạy test tranh chấp trên directory production hoặc bằng tài khoản có quyền sửa nhóm quản trị. Dùng LDAP test directory, naming context riêng và ACL tối thiểu. Với hai writer qua **hai replica writable khác nhau**, cần thêm kiểm thử topology riêng; test trên một server không chứng minh nhất quán toàn hệ thống.

## 14. Những lỗi thiết kế thường gặp

| Triệu chứng | Nguyên nhân | Cách khắc phục |
|---|---|---|
| Hai admin cùng lưu và người ghi trước bị mất thay đổi | `read -> modify(REPLACE)` không có điều kiện | Dùng Assertion Control hoặc revision guard trong một ModifyRequest |
| Kiểm tra `exists` xong vẫn bị `entryAlreadyExists` | TOCTOU giữa lookup và Add | Xử lý kết quả Add của server; thiết kế uniqueness đúng scope |
| Lỗi `noSuchAttribute` nhưng backend trả 409 cho mọi trường hợp | Phân loại lỗi quá rộng | Chỉ coi lỗi là stale revision khi xác minh đúng thao tác guard |
| `repository.save` được cho là tự có `@Version` | Suy luận từ Spring Data module khác | Kiểm tra support thực; có write service conditional rõ ràng |
| Group mất member của người khác | Đọc cả danh sách rồi ghi `REPLACE_ATTRIBUTE` | Dùng Add/Remove một giá trị hoặc có điều kiện version |
| Xóa user rồi group còn DN cũ | Không có transaction/referential integrity liên entry | Server plugin/reconciliation hoặc điều phối phù hợp |
| Dùng `modifyTimestamp` để CAS nhưng vẫn mất update | Timestamp không phải token version đủ mạnh trong backend đó | Chọn revision được bảo vệ; kiểm tra semantics server |
| API luôn retry khi thấy conflict | Tự ghi đè thay đổi mới với dữ liệu cũ | Đọc lại, merge hoặc yêu cầu người dùng giải quyết |
| Test hai thread chỉ thấy “có exception” | Không phân biệt xung đột với lỗi mạng/schema/ACL | Assert cụ thể error code và trạng thái cuối |
| Đọc lại ngay nhưng vẫn thấy bản cũ | Đọc từ replica có độ trễ | Xác định read-your-writes policy/authoritative server |

## 15. Câu hỏi tự kiểm tra

1. Vì sao kiểm tra `lookup`/`exists` rồi mới `modify` không đủ chống race condition?
2. Tính nguyên tử của **một** `ModifyRequest` khác gì transaction xuyên nhiều entry?
3. Khi nào `REPLACE_ATTRIBUTE` có thể gây lost update, và vì sao chỉ thêm một giá trị qua `ADD_ATTRIBUTE` thường an toàn hơn việc ghi đè cả danh sách?
4. Assertion Control có OID nào, dùng filter thế nào và vì sao `critical=true` quan trọng?
5. Trong phương án xóa `appRevision` cũ rồi thêm revision mới trong một ModifyRequest, tại sao request thứ hai dùng revision cũ phải thất bại?
6. Vì sao không nên dùng `modifyTimestamp` hoặc `entryUUID` làm optimistic-lock version mặc định mà không kiểm chứng semantics?
7. Khi user được đổi DN, điều gì xảy ra với tham chiếu thành viên nhóm dạng DN?
8. Khi nào API nên trả conflict và khi nào phải trả lỗi schema/ACL/network riêng?
9. Tại sao replica lag có thể làm một lần đọc sau ghi trả dữ liệu cũ?
10. Một bài kiểm thử hai writer cần xác nhận trạng thái cuối và loại lỗi như thế nào để chứng minh cơ chế chống lost update?

**Ghi nhớ:** kiểm tra dữ liệu trước ghi giúp phát hiện lỗi sớm nhưng **không tự ngăn TOCTOU**. Để giới hạn race condition, ưu tiên thao tác đơn lẻ mà LDAP server tự cưỡng chế (Add một DN, Modify một giá trị) và dùng **điều kiện được kiểm tra cùng thao tác ghi** khi cần bảo vệ phiên bản. LDAP bảo đảm atomic trong phạm vi một ModifyRequest trên một entry, **không** mặc nhiên bảo đảm transaction nhiều entry hay serializability trên các replica. Hãy thiết kế conflict handling, retry, ACL, monitoring và integration test dựa trên semantics backend thực tế.

### Tài liệu tham khảo

- IETF [RFC 4511 — LDAP: The Protocol](https://www.rfc-editor.org/rfc/rfc4511): Add, Delete, Modify, Compare, ModifyDN và tính nguyên tử của Modify.
- IETF [RFC 4528 — LDAP Assertion Control](https://www.rfc-editor.org/rfc/rfc4528): Assertion Control OID `1.3.6.1.1.12` và result code `assertionFailed`.
- IETF [RFC 5805 — LDAP Transactions](https://www.rfc-editor.org/rfc/rfc5805): transaction extension tùy chọn, không mặc định được hỗ trợ.
- Spring LDAP API — [`LdapTemplate`](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/core/LdapTemplate.html): `modifyAttributes`, `lookup` và các thao tác cơ bản.
- Oracle Java SE — [`ModificationItem`](https://docs.oracle.com/en/java/javase/17/docs/api/java.naming/javax/naming/directory/ModificationItem.html), [`DirContext`](https://docs.oracle.com/en/java/javase/17/docs/api/java.naming/javax/naming/directory/DirContext.html) và [`LdapContext`](https://docs.oracle.com/en/java/javase/17/docs/api/java.naming/javax/naming/ldap/LdapContext.html).
- Spring Data LDAP Reference — [Repositories](https://docs.spring.io/spring-data/ldap/reference/ldap/repositories.html): entity ODM, LDAP repository và các giới hạn so với repository của datastore khác.
