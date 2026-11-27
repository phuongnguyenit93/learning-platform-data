# Kiểm tra object class và attribute bắt buộc

Khi ghi dữ liệu vào LDAP bằng **Spring LDAP**, một entry không chỉ là một tập cặp tên–giá trị tùy ý. LDAP schema quy định entry thuộc những **object class** nào, phải có những **attribute bắt buộc** nào và có thể sử dụng thêm những attribute nào. Nếu không kiểm tra trước, ứng dụng có thể gửi một entry thiếu `sn`, tự ý chọn object class không phù hợp hoặc cập nhật attribute trái schema; LDAP server sẽ trả lỗi và logic nghiệp vụ phải xử lý muộn.

Bài học thuộc chương **Validation**, tập trung vào việc xác định **object class hợp lệ và tập thuộc tính bắt buộc trước khi gọi `LdapTemplate`, `LdapClient` hay ghi qua ODM**. Các ví dụ dùng Java 17+, Spring LDAP và cây thư mục giả định có base DN `dc=example,dc=org`. Chúng mô tả một **hợp đồng ứng dụng mẫu**; các directory khác nhau có thể có schema mở rộng, DIT content rule, hạn chế ACL hoặc chính sách riêng. **LDAP server vẫn là nơi kiểm tra schema cuối cùng.**

## 1. Object class đóng vai trò gì trong một LDAP entry?

Một entry điển hình:

```ldif
dn: uid=alice,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: alice
cn: Alice Nguyen
sn: Nguyen
mail: alice@example.org
```

`objectClass` là một attribute chứa một hoặc nhiều giá trị mô tả kiểu của entry. Mỗi object class có thể khai báo:

| Thành phần schema | Vai trò | Ý nghĩa khi kiểm tra |
| --- | --- | --- |
| `SUP` | Object class cha | Kế thừa các ràng buộc của cha và tổ tiên |
| `MUST` | Attribute bắt buộc | Entry phải có attribute phù hợp khi kiểm tra schema |
| `MAY` | Attribute được phép | Có thể xuất hiện nhưng không bắt buộc chỉ vì schema cho phép |
| `STRUCTURAL` | Lớp mô tả loại entry chính | Các structural class của entry phải tuân theo cùng một chuỗi kế thừa phù hợp |
| `AUXILIARY` | Bổ sung khả năng/attribute cho entry | Chỉ dùng khi schema và các quy tắc nội dung của server cho phép |
| `ABSTRACT` | Lớp cơ sở, không trực tiếp đại diện entry cụ thể | Thường xuất hiện trong chuỗi kế thừa, ví dụ `top` |

**Điểm quan trọng:** các giá trị `objectClass` không phải danh sách nhãn tự do. Một entry `inetOrgPerson` là một nhánh kế thừa structural class, còn việc thêm một structural class không liên quan chỉ để “có thêm attribute” thường dẫn đến vi phạm schema.

### 1.1. Kế thừa MUST/MAY

Với schema chuẩn thường dùng, chuỗi người dùng là:

```text
top                         [ABSTRACT]
 └── person                  [STRUCTURAL]  MUST: cn, sn
      └── organizationalPerson [STRUCTURAL]  kế thừa cn, sn
           └── inetOrgPerson  [STRUCTURAL]  kế thừa cn, sn
```

Khi một entry dùng `inetOrgPerson`, ứng dụng phải tính cả các attribute bắt buộc **kế thừa từ `person`**. Không thể chỉ đọc riêng phần `MUST` khai báo tại `inetOrgPerson` rồi kết luận entry không có trường bắt buộc.

Một số ví dụ đối chiếu:

| Kiểu entry / chuỗi class | Attribute bắt buộc theo schema thường dùng | Lưu ý |
| --- | --- | --- |
| `top` → `person` | `cn`, `sn` | `person` là structural class |
| `top` → `person` → `organizationalPerson` → `inetOrgPerson` | `cn`, `sn` (kế thừa) | `uid`, `mail` là các attribute thường được phép, không phải MUST của `inetOrgPerson` |
| `top` → `organizationalUnit` | `ou` | Dùng cho một đơn vị tổ chức |
| `top` → `groupOfNames` | `cn`, `member` | `member` là tập DN thành viên; nhóm chuẩn này cần ít nhất một giá trị `member` |

Trong hệ thống quản lý tài khoản, ứng dụng thường **bổ sung ràng buộc nghiệp vụ** rằng `uid` là bắt buộc và dùng làm RDN, dù schema của `inetOrgPerson` không đánh dấu `uid` là MUST. Vì vậy cần phân biệt rõ:

- **Schema MUST:** bắt buộc do object class và schema của directory.
- **Application required:** bắt buộc do thiết kế API, định danh, bảo mật hoặc quy trình nghiệp vụ.
- **Schema MAY:** attribute được phép; không đồng nghĩa API cho client tự do sửa.

## 2. Xác định đúng tập object class cho từng loại entry

Một API tạo người dùng có thể nhận `uid`, `cn`, `sn`, `mail`, nhưng **không nhận trực tiếp `objectClass` từ request**. Tầng service chọn bộ class chuẩn, ví dụ:

```text
PERSON_CLASS_SET = [top, person, organizationalPerson, inetOrgPerson]
```

Một API tạo nhóm sử dụng bộ class khác, ví dụ `top` và `groupOfNames`. Không dùng bộ class của người dùng để tạo group và cũng không trộn `inetOrgPerson` với `groupOfNames` như hai structural class độc lập.

Quy trình xác định hợp đồng cho một kiểu entry:

1. **Chọn structural class** theo ý nghĩa entry, ví dụ `inetOrgPerson`.
2. **Truy vết `SUP`** để biết các class tổ tiên và các ràng buộc được kế thừa.
3. **Xem xét auxiliary class** nếu nghiệp vụ cần, đồng thời xác minh directory có cho phép kết hợp đó không.
4. **Hợp nhất MUST/MAY** của class đang dùng cùng các class kế thừa; đối chiếu các quy tắc schema khác của server.
5. **Bổ sung chính sách ứng dụng**, như `uid` bắt buộc, giới hạn độ dài tên, hay cấm client sửa `userPassword`.
6. **Đóng gói thành profile riêng** cho từng loại entry; tạo `objectClass` và danh sách attribute cho phép từ profile đó.

Ví dụ với `inetOrgPerson`:

```text
Schema MUST (kế thừa):         cn, sn
Ứng dụng yêu cầu thêm:          uid
Ứng dụng cho phép thêm:         mail
Object classes do app thiết lập: top, person, organizationalPerson, inetOrgPerson
```

Ví dụ với `groupOfNames`:

```ldif
dn: cn=developers,ou=groups,dc=example,dc=org
objectClass: top
objectClass: groupOfNames
cn: developers
member: uid=alice,ou=people,dc=example,dc=org
```

Với `groupOfNames`, tạo một entry **không có `member`** thường bị server từ chối do thiếu attribute bắt buộc. Nếu sản phẩm cần nhóm rỗng, hãy chọn mô hình/schema được directory hỗ trợ (ví dụ loại nhóm thích hợp hoặc quy trình riêng), thay vì lén thêm giá trị giả mà không tính đến hệ quả nghiệp vụ.

## 3. Kiểm tra attribute: không dừng ở việc tên trường có tồn tại

Để validation có ý nghĩa, ứng dụng cần kiểm tra cả tính hiện diện, số lượng giá trị và giới hạn theo schema:

| Kiểm tra | Trường hợp cần phát hiện | Cách xử lý |
| --- | --- | --- |
| Attribute bắt buộc vắng mặt | `inetOrgPerson` không có `sn` | Từ chối trước thao tác ghi |
| Attribute bắt buộc rỗng | `sn` không có giá trị; chuỗi trắng bị cấm theo chính sách | Trả lỗi ở request/service |
| Attribute ngoài profile | Client muốn thêm `employeeNumber` dù API không hỗ trợ | Từ chối hoặc dành cho API có thẩm quyền riêng |
| Giá trị sai kiểu/cú pháp | `member` không phải DN hợp lệ; `uid` vi phạm quy tắc định danh | Kiểm tra bằng bộ xử lý theo loại attribute |
| Sai số lượng giá trị | API chỉ hỗ trợ một `cn` nhưng nhận nhiều giá trị; attribute schema SINGLE-VALUE lại có nhiều giá trị | Kiểm tra theo schema và hợp đồng API |
| RDN không khớp attribute | DN là `uid=alice,...` nhưng giá trị `uid` của entry lại là `bob` | Dùng cùng giá trị đã validation để xây DN và entry |
| Object class không nhất quán | Chỉ có `inetOrgPerson` nhưng ứng dụng kỳ vọng profile class cố định; hoặc trộn nhiều structural chain không hợp lệ | Chuẩn hóa theo profile, rồi để server kiểm chứng schema thực |

Một số chi tiết quan trọng:

- Tên attribute của LDAP về cơ bản **không phân biệt chữ hoa/thường**. `BasicAttributes(true)` của JNDI giúp xử lý tên không phân biệt hoa/thường trong bộ nhớ. Schema còn có thể định danh attribute bằng OID hoặc alias; muốn kiểm tra tổng quát phải chuẩn hóa theo schema thực, không chỉ chuyển sang lowercase.
- Attribute LDAP có thể **đa giá trị**. `member` của `groupOfNames` thường chứa nhiều DN; không được mặc định mọi attribute chỉ có một chuỗi. Ngược lại, những attribute khai báo `SINGLE-VALUE` phải tuân thủ ràng buộc đó.
- `objectClass` chính nó là attribute bắt buộc của entry, và giá trị class không phân biệt hoa/thường. Một object class có thể kéo theo attribute bắt buộc từ tổ tiên.
- `MAY` không cấp quyền ghi. Các attribute được schema cho phép vẫn có thể bị ACL hoặc chính sách ứng dụng chặn.
- Attribute do server quản lý như `entryUUID`, `createTimestamp` và các attribute liên quan trạng thái thư mục không nên được client tự cấp giá trị.

## 4. Ví dụ Spring LDAP: chuẩn bị entry theo profile trước `bind`

Ví dụ dưới đây dùng DTO có kiểu rõ ràng, cho phép tạo entry `inetOrgPerson`. Quy tắc của ứng dụng mẫu là: `uid` gồm 1–64 ký tự ASCII phù hợp, `cn` và `sn` bắt buộc, `mail` tùy chọn, và API chỉ ghi **một giá trị cho mỗi trường dữ liệu**. Giới hạn này chặt hơn một số khả năng đa giá trị của LDAP schema; nó phản ánh hợp đồng API chứ không phải quy tắc phổ quát.

```java
import java.util.HashSet;
import java.util.Locale;
import java.util.Set;
import java.util.regex.Pattern;
import javax.naming.NamingEnumeration;
import javax.naming.NamingException;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.BasicAttributes;
import javax.naming.ldap.LdapName;

import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

public final class PersonDirectoryService {
    private static final Pattern UID =
            Pattern.compile("[A-Za-z0-9._-]{1,64}");

    // Chuỗi object class chuẩn cho loại entry này.
    private static final Set<String> PERSON_CLASSES = Set.of(
            "top", "person", "organizationalperson", "inetorgperson");
    private static final Set<String> ALLOWED_ATTRIBUTES = Set.of(
            "objectclass", "uid", "cn", "sn", "mail");

    private final LdapTemplate ldapTemplate;

    public PersonDirectoryService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public record NewPerson(String uid, String cn, String sn, String mail) {}
    private record Prepared(LdapName relativeDn, Attributes attributes) {}

    public void create(NewPerson input) {
        Prepared entry = prepare(input); // Validation hoàn toàn ở client.
        ldapTemplate.bind(entry.relativeDn(), null, entry.attributes());
    }

    private static Prepared prepare(NewPerson input) {
        if (input == null || input.uid() == null
                || !UID.matcher(input.uid()).matches()) {
            throw new IllegalArgumentException("uid không hợp lệ");
        }
        requireText("cn", input.cn(), 128);
        requireText("sn", input.sn(), 128);
        if (input.mail() != null) {
            requireText("mail", input.mail(), 254);
        }

        // Chọn class tại service, không nhận từ HTTP request.
        Attributes attrs = new BasicAttributes(true);
        Attribute classes = new BasicAttribute("objectClass");
        classes.add("top");
        classes.add("person");
        classes.add("organizationalPerson");
        classes.add("inetOrgPerson");
        attrs.put(classes);

        attrs.put("uid", input.uid());
        attrs.put("cn", input.cn());
        attrs.put("sn", input.sn());
        if (input.mail() != null) {
            attrs.put("mail", input.mail());
        }

        validatePersonProfile(attrs);

        // DN tương đối khi ContextSource đã có base=dc=example,dc=org.
        LdapName dn = LdapNameBuilder.newInstance()
                .add("ou", "people")
                .add("uid", input.uid())
                .build();
        return new Prepared(dn, attrs);
    }

    static void validatePersonProfile(Attributes attrs) {
        if (attrs == null) {
            throw new IllegalArgumentException("Thiếu attributes");
        }
        try {
            Attribute classes = attrs.get("objectClass");
            if (classes == null || classes.size() == 0) {
                throw new IllegalArgumentException("Thiếu objectClass");
            }
            Set<String> actualClasses = new HashSet<>();
            for (int i = 0; i < classes.size(); i++) {
                Object value = classes.get(i);
                if (!(value instanceof String className)) {
                    throw new IllegalArgumentException(
                            "Giá trị objectClass không hợp lệ");
                }
                actualClasses.add(className.toLowerCase(Locale.ROOT));
            }
            if (!actualClasses.equals(PERSON_CLASSES)) {
                throw new IllegalArgumentException(
                        "Object classes không thuộc profile người dùng");
            }

            // cn, sn là schema MUST; uid là yêu cầu bổ sung của app.
            for (String required : Set.of("cn", "sn", "uid")) {
                Attribute value = attrs.get(required);
                if (value == null || value.size() != 1
                        || !(value.get() instanceof String text)
                        || text.isBlank()) {
                    throw new IllegalArgumentException(
                            "Thiếu hoặc sai giá trị bắt buộc: " + required);
                }
            }

            NamingEnumeration<? extends Attribute> all = attrs.getAll();
            try {
                while (all.hasMore()) {
                    Attribute attribute = all.next();
                    String id = attribute.getID().toLowerCase(Locale.ROOT);
                    if (!ALLOWED_ATTRIBUTES.contains(id)) {
                        throw new IllegalArgumentException(
                                "Attribute không được phép: " + id);
                    }
                    // Hợp đồng API mẫu: mỗi field dữ liệu có một giá trị.
                    if (!id.equals("objectclass")) {
                        if (attribute.size() != 1
                                || !(attribute.get() instanceof String text)
                                || text.isBlank()) {
                            throw new IllegalArgumentException(
                                    "Attribute rỗng hoặc sai số lượng: " + id);
                        }
                    }
                }
            } finally {
                all.close();
            }
        } catch (NamingException ex) {
            throw new IllegalArgumentException(
                    "Không thể đọc thuộc tính LDAP", ex);
        }
    }

    private static void requireText(String name, String value, int maxLength) {
        if (value == null || value.isBlank() || value.length() > maxLength
                || value.codePoints().anyMatch(Character::isISOControl)) {
            throw new IllegalArgumentException(name + " không hợp lệ");
        }
    }
}
```

Cách sử dụng trong service:

```java
service.create(new PersonDirectoryService.NewPerson(
        "alice", "Alice Nguyen", "Nguyen", "alice@example.org"));
```

Trước lời gọi `bind`, code đã:

1. Loại input thiếu `uid`, `cn` hoặc `sn` và giá trị vi phạm chính sách ứng dụng.
2. Tạo bộ `objectClass` cố định từ loại entry đã chọn.
3. Kiểm tra bộ class đúng **profile**, có các attribute bắt buộc, không có attribute ngoài allowlist, và số lượng giá trị phù hợp với API.
4. Tạo DN bằng `LdapNameBuilder` để giá trị `uid` không làm thay đổi cú pháp RDN.

**Phạm vi của validator này:** nó cố ý kiểm tra **một profile `inetOrgPerson` có chủ đích**, không phải engine đọc và xác thực toàn bộ LDAP schema. Việc so khớp chính xác tập `objectClass` là quy định của ứng dụng mẫu; trên server thực tế có thể có alias/OID hoặc các class mở rộng hợp lệ. Nếu cần hỗ trợ thêm class, phải cập nhật profile và kiểm chứng lại với schema server. Việc kiểm tra cú pháp email, Unicode normalization hoặc ràng buộc phân biệt tên vẫn có thể được bổ sung tùy yêu cầu sản phẩm.

## 5. Kiểm thử bắt lỗi trước khi gửi LDAP

### 5.1. Unit test cho dữ liệu không hợp lệ

Test nên chứng minh rằng **khi thiếu attribute bắt buộc, không có lời gọi LDAP nào được thực hiện**:

```java
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verifyNoInteractions;

import org.junit.jupiter.api.Test;
import org.springframework.ldap.core.LdapTemplate;

class PersonDirectoryServiceTest {
    @Test
    void missingSurnameStopsBeforeBind() {
        LdapTemplate template = mock(LdapTemplate.class);
        var service = new PersonDirectoryService(template);

        assertThrows(IllegalArgumentException.class, () ->
                service.create(new PersonDirectoryService.NewPerson(
                        "alice", "Alice Nguyen", "", null)));

        verifyNoInteractions(template);
    }
}
```

Muốn kiểm tra trực tiếp guard của profile:

```java
import javax.naming.directory.Attributes;
import javax.naming.directory.BasicAttributes;
import static org.junit.jupiter.api.Assertions.assertThrows;

// Ví dụ này nằm trong cùng package với PersonDirectoryService.
Attributes attrs = new BasicAttributes(true);
attrs.put("objectClass", "extensibleObject");
attrs.put("uid", "alice");
attrs.put("cn", "Alice Nguyen");
attrs.put("sn", "Nguyen");

assertThrows(IllegalArgumentException.class,
        () -> PersonDirectoryService.validatePersonProfile(attrs));
```

Bộ kiểm thử hợp lý gồm:

| Trường hợp | Kỳ vọng |
| --- | --- |
| Đầy đủ `top/person/organizationalPerson/inetOrgPerson`, `uid/cn/sn` | Qua validation cục bộ và có thể gửi `bind` |
| Thiếu `cn` hoặc `sn` | Chặn trước I/O |
| `objectClass` thiếu hoặc chứa class ngoài profile | Chặn trước I/O |
| Client cố thêm attribute không trong allowlist | Chặn trước I/O |
| `mail` vắng mặt | Chấp nhận, vì đây là tùy chọn trong profile |
| `cn` có hai giá trị | Từ chối theo **hợp đồng API mẫu**, dù schema có thể cho phép đa giá trị |
| Dữ liệu qua local validation nhưng server có schema bổ sung | Server có thể từ chối; integration test phát hiện |
| Hai request cùng tạo một DN | Local validation có thể đều qua; server giải quyết xung đột tồn tại |

### 5.2. Integration test với directory kiểm thử

Unit test phát hiện lỗi validation do ứng dụng quy định. Muốn xác minh **schema thực tế**, cần chạy bài kiểm thử tích hợp với LDAP server dành riêng cho test:

- Tạo một `inetOrgPerson` hợp lệ; đọc lại `objectClass`, `cn`, `sn`, `uid` để xác nhận dữ liệu.
- Thử gửi entry thiếu `sn` bằng fixture kiểm thử trực tiếp và xác minh server từ chối theo schema hiện dùng.
- Thử một object class không hỗ trợ và một attribute không được schema cho phép.
- Thử tạo `groupOfNames` không có `member` nếu schema server yêu cầu; xác minh phản hồi.
- Kiểm tra ACL của tài khoản dịch vụ; schema hợp lệ không có nghĩa tài khoản có quyền ghi.

Không sử dụng tài khoản quản trị hoặc LDAP production cho các thử nghiệm phá vỡ schema. Nếu thao tác không thành công, phân biệt lỗi `objectClassViolation`, `constraintViolation`, thiếu quyền, entry đã tồn tại và lỗi kết nối; nội dung và mã kết quả cụ thể phụ thuộc server.

## 6. Khi schema không cố định: kiểm tra dựa trên directory

Nếu ứng dụng hỗ trợ nhiều LDAP server, nhiều loại entry hoặc schema mở rộng, hard-code profile có thể không đủ. Một hướng triển khai nâng cao:

1. Truy vấn thông tin **subschema** mà server công bố (thường thông qua thuộc tính vận hành `subschemaSubentry`).
2. Đọc các định nghĩa `objectClasses`, `attributeTypes` và những ràng buộc được server hỗ trợ.
3. Phân tích `SUP`, loại class, `MUST`, `MAY`, alias/OID và các tính chất như `SINGLE-VALUE`.
4. Tạo bản mô tả ràng buộc theo schema tương ứng; bổ sung allowlist và ràng buộc nghiệp vụ riêng.
5. Cache có kiểm soát và làm mới khi schema thay đổi; xử lý trường hợp tài khoản dịch vụ không có quyền đọc schema.

Không phải server nào cũng cung cấp đầy đủ cùng một tập metadata hoặc triển khai các quy tắc giống nhau. Vì vậy, schema discovery cần xử lý sai khác và lỗi truy cập. Ngay cả khi có schema động, **không bỏ qua validation phía server**: quyền, các ràng buộc nội dung, quy tắc tên, xung đột thời điểm ghi và plugin tùy biến vẫn được đánh giá lúc thực thi.

Spring LDAP giúp đọc và thao tác entry qua `ContextSource`, `LdapTemplate`, `LdapClient` hoặc ODM, nhưng các API này không tự suy ra toàn bộ hợp đồng nghiệp vụ từ DTO. Với ODM, annotation mapping chỉ mô tả ánh xạ Java–LDAP; vẫn cần xem xét object classes, field bắt buộc và phản hồi schema của server trong integration test.

## 7. Checklist khi chuẩn bị entry

- [ ] Xác định structural object class theo loại entry và chuỗi `SUP` liên quan.
- [ ] Tính đầy đủ `MUST` kế thừa; xem xét `MAY`, auxiliary class và các quy tắc của directory.
- [ ] Phân biệt **schema MUST** với attribute bắt buộc do ứng dụng, như `uid` trong ví dụ.
- [ ] Chọn `objectClass` từ profile đáng tin cậy; không để request tùy ý cung cấp hoặc mở rộng class.
- [ ] Xác minh attribute bắt buộc **có giá trị sử dụng được**, đúng số lượng, kiểu và cú pháp theo hợp đồng.
- [ ] Chỉ ghi attribute được API cho phép; không tự cấp giá trị cho attribute do server quản lý.
- [ ] Dùng nhất quán các giá trị RDN trong DN và entry; xây DN bằng API LDAP chuyên dụng.
- [ ] Bảo đảm thao tác tạo/sửa/đổi tên không làm mất attribute bắt buộc sau khi cập nhật.
- [ ] Có unit test kiểm tra dừng trước I/O và integration test xác nhận schema, ACL trên directory thử nghiệm.
- [ ] Xử lý lỗi validation cục bộ và lỗi schema/quyền từ server theo hai đường rõ ràng.

**Kết luận:** Kiểm tra object class hiệu quả bắt đầu bằng việc chọn đúng kiểu entry và hiểu chuỗi kế thừa schema; kiểm tra attribute bắt buộc phải hợp nhất `MUST` của schema với yêu cầu riêng của ứng dụng. Chuẩn bị entry hợp lệ trước lời gọi Spring LDAP giúp phát hiện lỗi sớm, còn LDAP server bảo đảm ràng buộc cuối cùng đối với dữ liệu trong thư mục.
