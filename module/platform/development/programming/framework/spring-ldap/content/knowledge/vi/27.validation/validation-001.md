# Kiểm tra DN và attribute trước khi gọi server

Khi ứng dụng dùng **Spring LDAP** để tạo, sửa, tìm kiếm hoặc xóa entry, dữ liệu đầu vào thường đi qua nhiều lớp: HTTP request, mã nghiệp vụ, `LdapTemplate`/`LdapClient`, rồi mới tới LDAP server. Nếu ứng dụng gửi thẳng chuỗi DN (Distinguished Name) hay tập attribute chưa kiểm tra, lỗi nhập liệu sẽ trở thành lỗi LDAP khó chẩn đoán; nguy hiểm hơn, cách nối chuỗi sai có thể làm thao tác hướng tới entry ngoài phạm vi dự kiến.

Bài này thuộc chủ đề **Validation** và tập trung vào câu hỏi: **cần kiểm tra những gì ở phía ứng dụng, trước khi có bất kỳ lời gọi nào đến server?** Ví dụ sử dụng Java 17+, Spring LDAP và cây thư mục giả định có base DN `dc=example,dc=org`. Mọi quy tắc về tên, độ dài hoặc attribute được minh họa đều là **chính sách của ứng dụng mẫu**; khi triển khai thực tế phải đối chiếu với schema và chính sách của directory đang sử dụng.

## 1. Phân biệt kiểm tra đầu vào với kiểm tra của LDAP server

Giả sử ứng dụng cung cấp API tạo người dùng với dữ liệu:

```json
{
  "uid": "alice",
  "cn": "Alice Nguyen",
  "sn": "Nguyen"
}
```

Ứng dụng muốn tạo entry tương ứng với DN đầy đủ `uid=alice,ou=people,dc=example,dc=org`, sử dụng object class `inetOrgPerson`.

Có ba nhóm vấn đề cần tách biệt:

| Lớp kiểm tra | Câu hỏi cần trả lời | Ví dụ |
| --- | --- | --- |
| **Giá trị đầu vào** | Có thiếu trường, vượt giới hạn, chứa ký tự không được chính sách ứng dụng cho phép không? | `uid` rỗng, `cn` quá dài, ký tự điều khiển trong `sn` |
| **DN và phạm vi thao tác** | DN có cấu trúc hợp lệ, RDN mong đợi và nằm trong nhánh được phép không? | Chỉ tạo người dùng dưới `ou=people`, không cho chọn `ou=admins` |
| **Attribute và schema dự kiến** | Tên attribute có được phép, giá trị có đúng kiểu/số lượng và có đủ attribute bắt buộc không? | `inetOrgPerson` cần `cn`, `sn`; không chấp nhận client tự gửi `objectClass` |

Phía ứng dụng chỉ **kiểm tra sớm** những ràng buộc đã biết. LDAP server vẫn là nơi quyết định cuối cùng về schema, quyền truy cập (ACL), sự tồn tại của parent entry, tính duy nhất khi có cạnh tranh đồng thời và các quy tắc đặc thù của hệ thống. Vì thế, một đầu vào vượt qua validation cục bộ **không bảo đảm** thao tác LDAP sẽ thành công.

## 2. Kiểm tra DN: cấu trúc, escape và ranh giới nhánh

### 2.1. DN không phải chuỗi đường dẫn thông thường

DN được tạo từ các **Relative Distinguished Name (RDN)**, chẳng hạn:

```text
uid=alice,ou=people,dc=example,dc=org
└─ RDN người dùng ┘ └─ nhánh tổ chức ┘ └─ base DN ┘
```

Trong ví dụ này:

- `uid=alice` là RDN của entry người dùng.
- `ou=people` là nhánh cha nơi ứng dụng được phép quản lý người dùng.
- `dc=example,dc=org` là base DN của thư mục.

Dấu phẩy, dấu cộng, dấu bằng và một số ký tự khác có ý nghĩa cú pháp trong DN. **Không nối giá trị do người dùng nhập vào DN bằng phép cộng chuỗi.**

```java
// Tránh: giá trị uid đang trở thành một phần của cú pháp DN.
String dn = "uid=" + uidFromRequest + ",ou=people";
```

Ví dụ, nếu `uidFromRequest` là `alice,ou=admins`, phép nối chuỗi làm thay đổi số lượng RDN. Đừng cố giải quyết bằng cách tự `replace(",", "\\,")`: cú pháp escape của DN có nhiều trường hợp, bao gồm dấu cộng, khoảng trắng ở đầu/cuối và các ký tự đặc biệt khác.

Hãy dùng API xây dựng tên của Spring LDAP:

```java
import javax.naming.ldap.LdapName;
import org.springframework.ldap.support.LdapNameBuilder;

LdapName relativeDn = LdapNameBuilder.newInstance()
        .add("ou", "people")
        .add("uid", uidFromRequest)
        .build();
```

`LdapNameBuilder` xử lý giá trị của từng RDN theo cú pháp DN; nếu có dấu phẩy trong *giá trị* `uid`, dấu phẩy đó được biểu diễn như dữ liệu của cùng một RDN, không thành ranh giới của RDN mới. **Escape đúng** vẫn khác với **được phép theo nghiệp vụ**: ứng dụng hoàn toàn có thể cấm dấu phẩy trong `uid` bằng quy tắc riêng.

> **Lưu ý về base DN:** Nếu `ContextSource` đã cấu hình `base=dc=example,dc=org`, DN truyền cho các thao tác thông thường của `LdapTemplate` là DN **tương đối với base** như `uid=alice,ou=people`. Không tự thêm `dc=example,dc=org` lần nữa, vì có thể khiến đường dẫn bị lặp hoặc sai phạm vi.

### 2.2. Khi nhận DN đầy đủ: parse rồi xác minh nhánh

Có API cho phép người quản trị cung cấp một DN đầy đủ. Trường hợp này phải kiểm tra cả cú pháp lẫn phạm vi. Ví dụ, ứng dụng chỉ cho phép thao tác trên entry có **một RDN `uid` ngay dưới** `ou=people,dc=example,dc=org`:

```java
import javax.naming.InvalidNameException;
import javax.naming.ldap.LdapName;
import javax.naming.ldap.Rdn;
import java.util.regex.Pattern;

public final class DnPolicy {
    private static final Pattern UID =
            Pattern.compile("[A-Za-z0-9._-]{1,64}");

    public static LdapName requirePersonDn(String rawDn)
            throws InvalidNameException {
        if (rawDn == null || rawDn.isBlank()) {
            throw new IllegalArgumentException("DN không được rỗng");
        }

        LdapName dn = new LdapName(rawDn); // Kiểm tra cú pháp DN.
        LdapName branch =
                new LdapName("ou=people,dc=example,dc=org");

        // Với LdapName, startsWith so khớp các RDN ở phía gốc DN.
        if (!dn.startsWith(branch) || dn.size() != branch.size() + 1) {
            throw new IllegalArgumentException(
                    "DN phải là người dùng nằm trực tiếp dưới ou=people");
        }

        Rdn leaf = dn.getRdn(dn.size() - 1);
        if (leaf.size() != 1
                || !leaf.getType().equalsIgnoreCase("uid")
                || !(leaf.getValue() instanceof String uid)
                || !UID.matcher(uid).matches()) {
            throw new IllegalArgumentException("RDN uid không hợp lệ");
        }

        return dn;
    }
}
```

Phép kiểm tra `startsWith(branch)` sử dụng **các thành phần DN đã parse**, không phải `String.startsWith`. Kiểm tra thêm `size()` là cần thiết khi chỉ chấp nhận entry con trực tiếp: DN ở nhánh sâu hơn vẫn nằm trong cùng subtree nhưng không đáp ứng quy tắc này. `leaf.size() == 1` loại trường hợp RDN đa giá trị nếu API không hỗ trợ loại RDN đó.

Với DN đến từ client, sau khi xác minh thành công, ứng dụng vẫn phải chọn đúng cách chuyển thành DN tương đối với `ContextSource` trước khi gọi `LdapTemplate`; **không trộn DN tuyệt đối và tương đối**. Trong API tạo người dùng thông thường, cách đơn giản và an toàn hơn là **không nhận DN tùy ý**, chỉ nhận `uid` rồi xây DN từ một nhánh cố định.

### 2.3. Không lẫn escape DN với escape LDAP filter

DN và search filter có cú pháp khác nhau:

| Ngữ cảnh | Ví dụ | Cách xử lý |
| --- | --- | --- |
| DN/RDN | `uid=<giá trị>,ou=people` | Dùng `LdapNameBuilder` hoặc `Rdn` |
| Search filter | `(uid=<giá trị>)` | Dùng `LdapQueryBuilder` hoặc bộ xây filter có escape giá trị |
| Tên attribute/filter field | `uid`, `mail` | Chọn từ danh sách cho phép; không nhận tên trường tùy ý |

Ví dụ tìm kiếm bằng Spring LDAP:

```java
import static org.springframework.ldap.query.LdapQueryBuilder.query;
import org.springframework.ldap.core.AttributesMapper;
import java.util.List;

List<String> names = ldapTemplate.search(
        query().base("ou=people").where("uid").is(uidFromRequest),
        (AttributesMapper<String>) attrs ->
                (String) attrs.get("cn").get()
);
```

Ở đây `ou=people` và `uid` là phần cấu trúc do ứng dụng kiểm soát; `uidFromRequest` được đưa vào như **giá trị** cho bộ xây filter. Đừng ghép `"(uid=" + uidFromRequest + ")"` rồi gửi nguyên chuỗi đi. Một giá trị cần escape trong filter **không thể** dùng cách escape của DN để thay thế.

## 3. Kiểm tra attribute trước khi ghi entry

### 3.1. Phân biệt attribute do server/schema quyết định với dữ liệu nghiệp vụ

Trong LDAP, entry mang một hoặc nhiều `objectClass`; schema liên kết các object class với những attribute **bắt buộc** (MUST) và **được phép** (MAY). Ví dụ thông dụng với `inetOrgPerson`:

```ldif
dn: uid=alice,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: alice
cn: Alice Nguyen
sn: Nguyen
```

Với chuỗi object class trên, `cn` và `sn` là những attribute bắt buộc được kế thừa từ `person`. `uid` không phải MUST của `inetOrgPerson`, nhưng **ứng dụng mẫu chủ động yêu cầu `uid`** để định danh entry theo RDN. Những directory thực tế có thể bổ sung schema, giới hạn độ dài, các attribute khác hoặc quy tắc kiểm tra riêng.

Trước khi tạo entry, nên kiểm tra:

1. **Danh sách cho phép:** Chỉ nhận những attribute mà API được thiết kế để sửa (ví dụ `cn`, `sn`, `mail`); không nhận trực tiếp một `Map<String, Object>` rồi biến toàn bộ thành LDAP attributes.
2. **Thuộc tính bắt buộc:** `cn` và `sn` có giá trị; `uid` hợp lệ với quy tắc đặt tên của hệ thống.
3. **Định dạng và độ dài:** Chặn `null`, chuỗi rỗng, dữ liệu vượt giới hạn đã định và ký tự điều khiển không phù hợp. Với `mail`, dùng kiểm tra email riêng nếu API yêu cầu.
4. **Số lượng giá trị:** Tôn trọng thuộc tính đơn giá trị/đa giá trị theo schema cụ thể; không tùy tiện nối nhiều giá trị vào một chuỗi.
5. **Quan hệ DN–attribute:** Giá trị `uid` dùng để xây RDN phải nhất quán với `uid` lưu trong entry.
6. **Attribute nhạy cảm hoặc do server quản lý:** Không cho request tự ghi `objectClass`, `userPassword`, `entryUUID`, `createTimestamp`, `memberOf` khi API không có mục đích và quy trình rõ ràng cho chúng.

Một số attribute có tên không phân biệt chữ hoa/chữ thường; ngoài ra LDAP hỗ trợ mô tả attribute bằng tên hoặc OID và có thể có option. Vì vậy, regex kiểm tra *cú pháp tên* chưa đủ để phân quyền ghi. Với đầu vào từ client, **allowlist theo ý nghĩa nghiệp vụ** hiệu quả hơn. `BasicAttributes(true)` giúp tra cứu tên attribute không phân biệt chữ hoa/chữ thường ở cấu trúc phía Java, nhưng không thay thế schema validation của LDAP server.

### 3.2. Chuẩn bị DN và Attributes một lần trước lời gọi LDAP

Ví dụ sau tạo entry người dùng. `NewPerson` là kiểu dữ liệu đầu vào; các field được kiểm tra và chuyển thành **một tập dữ liệu đã chuẩn bị** trước khi thực thi `bind`.

```java
import java.util.regex.Pattern;
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

    private final LdapTemplate ldapTemplate;

    public PersonDirectoryService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public record NewPerson(String uid, String cn, String sn) {}

    private record PreparedPerson(LdapName dn, Attributes attributes) {}

    public void create(NewPerson input) {
        PreparedPerson prepared = prepare(input); // Chưa gọi LDAP.
        ldapTemplate.bind(
                prepared.dn(), null, prepared.attributes()); // Một lời gọi LDAP.
    }

    private static PreparedPerson prepare(NewPerson input) {
        if (input == null) {
            throw new IllegalArgumentException("Thiếu thông tin người dùng");
        }
        if (input.uid() == null || !UID.matcher(input.uid()).matches()) {
            throw new IllegalArgumentException(
                    "uid phải dài 1-64 ký tự và chỉ gồm A-Z, a-z, 0-9, . _ -");
        }
        requireText(input.cn(), "cn", 128);
        requireText(input.sn(), "sn", 128);

        // Nhánh cố định, DN tương đối với base của ContextSource.
        LdapName dn = LdapNameBuilder.newInstance()
                .add("ou", "people")
                .add("uid", input.uid())
                .build();

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
        return new PreparedPerson(dn, attrs);
    }

    private static void requireText(String value, String name, int maxLength) {
        if (value == null || value.isBlank() || value.length() > maxLength) {
            throw new IllegalArgumentException(name + " trống hoặc quá dài");
        }
        if (value.codePoints().anyMatch(Character::isISOControl)) {
            throw new IllegalArgumentException(
                    name + " chứa ký tự điều khiển");
        }
    }
}
```

Những điểm đáng chú ý trong thiết kế:

- `prepare` không thực hiện I/O; nếu kiểm tra thất bại, `ldapTemplate.bind` **không được gọi**.
- `uid` chỉ được dùng làm **giá trị** của RDN; `ou=people` là nhánh được định nghĩa trong code. Kiểm tra regex là chính sách tên cho ứng dụng mẫu, không phải yêu cầu chung của LDAP.
- Các thuộc tính được tạo từ những field có kiểu cụ thể; client không thể đưa thêm tên attribute hay object class ngoài dự kiến.
- `cn` và `sn` được truyền dưới dạng **giá trị attribute**. Không cần escape chúng theo cú pháp DN hay search filter, vì ở đây không nhúng chúng vào DN/filter.
- `objectClass` được gán bởi ứng dụng theo kiểu entry đã chọn. Schema server vẫn có thể từ chối entry nếu cấu trúc hoặc nội dung không đáp ứng yêu cầu thực tế.

Nếu API dùng **`LdapClient`** thay vì `LdapTemplate`, những bước `prepare` không thay đổi: validation thuộc biên ứng dụng, trước khi đưa DN và attribute vào lời gọi của client. Chỉ adapter thực hiện thao tác LDAP cần thay đổi.

## 4. Quy tắc cần kiểm tra tùy theo thao tác

| Thao tác | Kiểm tra trước khi gửi LDAP | Phần vẫn phải xác minh bằng server |
| --- | --- | --- |
| **Tạo entry** | DN thuộc nhánh cho phép; RDN đúng loại; trường bắt buộc có giá trị; object class và attribute theo mẫu được phép | Parent entry tồn tại; tên chưa trùng; schema, ACL và ràng buộc của server |
| **Sửa attribute** | DN đích hợp lệ; chỉ cập nhật attribute trong allowlist; định dạng và số lượng giá trị hợp lệ; không sửa các trường đặc biệt ngoài luồng nghiệp vụ | Entry tồn tại; quyền ghi; schema và kiểm tra đồng thời |
| **Đổi tên/di chuyển DN** | RDN mới được xây từ các thành phần; kiểm tra nhánh nguồn/đích; kiểm tra chính sách đổi tên, hậu quả với thuộc tính đặt tên | Quyền `modDN`, parent đích, xung đột tên và hành vi `deleteOldRdn` |
| **Tìm kiếm** | Base tìm kiếm cố định hoặc nằm trong allowlist; filter được xây bằng API escape; giới hạn phạm vi truy vấn, số lượng và thời gian | Quyền đọc, giới hạn truy vấn, kết quả và các alias/referral thực tế |
| **Xóa entry** | DN đúng subtree và loại entry cho phép; yêu cầu xác nhận nghiệp vụ nếu cần | Quyền xóa, entry tồn tại, ràng buộc xóa trên server |

Chú ý: một DN **đúng cú pháp** không có nghĩa là một DN **được phép**. Ví dụ `uid=bob,ou=admins,dc=example,dc=org` có thể hợp lệ với LDAP nhưng phải bị từ chối nếu API chỉ được phép thao tác dưới `ou=people`.

## 5. Xử lý lỗi và kiểm thử trước kết nối

### 5.1. Hai nhóm lỗi cần tách rõ

**Lỗi validation cục bộ** có thể trả về thông báo cụ thể ngay tại biên API:

- `uid` rỗng hoặc chứa ký tự nằm ngoài chính sách.
- `cn`/`sn` thiếu, quá dài hoặc chứa ký tự điều khiển.
- DN đã parse nhưng nằm ngoài subtree ứng dụng được quyền sử dụng.
- Request yêu cầu ghi attribute không được API hỗ trợ.

**Lỗi phát sinh từ LDAP server** vẫn có thể xảy ra sau bước validation: entry đã tồn tại, schema violation, quyền không đủ, parent DN không tồn tại, kết nối thất bại hoặc một thay đổi đồng thời khác. Không nên biến mọi lỗi server thành thông báo “đầu vào không hợp lệ”. Ở tầng API, phân loại lỗi nghiệp vụ có thể xử lý được, ghi log kèm mã lỗi và correlation ID; tránh log mật khẩu, secret hoặc toàn bộ thông tin cá nhân.

### 5.2. Unit test phải xác minh không có lời gọi mạng khi input sai

Với JUnit 5 và Mockito, có thể kiểm tra tính chất quan trọng nhất: **validation phải dừng trước I/O**.

```java
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verifyNoInteractions;

import org.junit.jupiter.api.Test;
import org.springframework.ldap.core.LdapTemplate;

class PersonDirectoryServiceTest {
    @Test
    void invalidUidNeverCallsLdap() {
        LdapTemplate template = mock(LdapTemplate.class);
        PersonDirectoryService service =
                new PersonDirectoryService(template);

        assertThrows(IllegalArgumentException.class, () ->
                service.create(
                    new PersonDirectoryService.NewPerson(
                        "alice,ou=admins", "Alice", "Nguyen")
                )
        );

        verifyNoInteractions(template);
    }

    @Test
    void missingRequiredAttributeNeverCallsLdap() {
        LdapTemplate template = mock(LdapTemplate.class);
        PersonDirectoryService service =
                new PersonDirectoryService(template);

        assertThrows(IllegalArgumentException.class, () ->
                service.create(
                    new PersonDirectoryService.NewPerson(
                        "alice", "Alice", "")
                )
        );

        verifyNoInteractions(template);
    }
}
```

Bên cạnh unit test, nên có **integration test** trên directory dành riêng cho kiểm thử để xác minh server chấp nhận object classes/attributes thực tế, từ chối vi phạm schema và giới hạn đúng quyền của tài khoản dịch vụ. Dữ liệu kiểm thử phải tách khỏi thư mục production.

### 5.3. Bộ ca kiểm tra tối thiểu

| Đầu vào/tình huống | Kỳ vọng |
| --- | --- |
| `uid=alice`, `cn=Alice Nguyen`, `sn=Nguyen` | Tạo đúng DN tương đối `uid=alice,ou=people` và gửi các attribute dự kiến |
| `uid` rỗng hoặc chứa dấu phẩy | Bị từ chối theo chính sách `uid` của ví dụ, không gọi LDAP |
| `cn` là chuỗi trống hoặc chứa xuống dòng | Bị từ chối trước khi tạo attributes |
| DN đầy đủ nằm dưới `ou=admins` | Không vượt qua kiểm tra subtree |
| DN có thêm cấp `ou=team` dưới `ou=people` | Bị từ chối nếu API chỉ cho entry con trực tiếp |
| Client yêu cầu chỉnh `objectClass` hoặc `entryUUID` | Bị từ chối bởi allowlist của API |
| Hai yêu cầu tạo cùng `uid` chạy đồng thời | Local validation đều có thể qua; server quyết định xung đột và ứng dụng xử lý lỗi |
| Attribute hợp lệ ở phía Java nhưng thiếu schema server yêu cầu | Server từ chối; test tích hợp phát hiện và hỗ trợ hiệu chỉnh chính sách |

## 6. Checklist trước khi gọi `LdapTemplate` hoặc `LdapClient`

- [ ] Đã xác định thao tác nhận **DN hay chỉ nhận các giá trị RDN**; ưu tiên xây DN từ nhánh cố định.
- [ ] DN được xây/parse bằng API LDAP chuyên dụng, không nối chuỗi thủ công.
- [ ] DN nằm trong subtree được phép và đáp ứng độ sâu, loại RDN theo nghiệp vụ.
- [ ] Đã phân biệt **DN đầy đủ** với **DN tương đối với base của `ContextSource`**.
- [ ] Đã kiểm tra field bắt buộc, độ dài, loại dữ liệu và các giới hạn của ứng dụng.
- [ ] Attribute được tạo theo allowlist; request không được tự định nghĩa tên trường, object class hoặc attribute do server quản lý.
- [ ] Giá trị đặt tên trong DN nhất quán với attribute tương ứng.
- [ ] Search filter được xây bằng API có escape giá trị; tên trường và search base do ứng dụng kiểm soát.
- [ ] Lỗi validation được phát hiện **trước** I/O; đã có unit test xác minh.
- [ ] Đã kiểm thử schema, ACL, trùng DN và lỗi đồng thời với LDAP server thử nghiệm.

**Nguyên tắc cốt lõi:** Ứng dụng chịu trách nhiệm kiểm tra hợp đồng đầu vào và phạm vi thao tác; Spring LDAP hỗ trợ xây DN/filter đúng cú pháp; LDAP server thực thi schema, quyền và trạng thái thực tế của thư mục. Kết hợp cả ba lớp sẽ giúp thao tác entry dễ kiểm soát, dễ kiểm thử và giảm nguy cơ thao tác nhầm đối tượng.
