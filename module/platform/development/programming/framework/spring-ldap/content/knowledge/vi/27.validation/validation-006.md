# Kiểm tra giá trị multi-valued và giới hạn kích thước

Trong LDAP, một attribute không nhất thiết chỉ chứa một chuỗi. Thuộc tính `member` của nhóm có thể chứa hàng trăm Distinguished Name (DN), `objectClass` thường mang nhiều giá trị, còn một số attribute khác chỉ được phép có **một** giá trị theo schema. Nếu ứng dụng dùng **Spring LDAP** không kiểm tra số lượng, từng giá trị và kích thước dữ liệu trước khi gọi server, thao tác tạo/sửa entry dễ gặp lỗi schema, dữ liệu trùng hoặc yêu cầu quá lớn.

Bài thuộc chương **Validation** của module **SPRING_LDAP**, tập trung vào **kiểm tra giá trị multi-valued và giới hạn kích thước** khi sử dụng `LdapTemplate`, `LdapClient` hoặc ODM. Chúng ta sẽ phân biệt giới hạn schema với giới hạn nghiệp vụ, chuẩn bị `Attributes` và `ModificationItem` an toàn, kiểm thử việc chặn đầu vào trước I/O, rồi xác định những điều LDAP server vẫn phải kiểm tra. Ví dụ dùng Java 17+, một directory giả định có base DN `dc=example,dc=org` và nhóm `groupOfNames`.

## 1. Hiểu đúng multi-valued attribute

Một LDAP entry có nhiều attribute. Mỗi attribute có thể mang một hoặc nhiều giá trị, tùy định nghĩa schema và trạng thái entry.

```ldif
dn: cn=developers,ou=groups,dc=example,dc=org
objectClass: top
objectClass: groupOfNames
cn: developers
member: uid=alice,ou=people,dc=example,dc=org
member: uid=bob,ou=people,dc=example,dc=org
member: uid=carol,ou=people,dc=example,dc=org
```

Ở đây:

- `objectClass` có hai giá trị, thể hiện loại entry.
- `member` có ba giá trị, mỗi giá trị là một DN.
- `cn` hiện chỉ có một giá trị. Điều đó không tự chứng minh schema của `cn` là `SINGLE-VALUE`; ứng dụng có thể chủ động chỉ cho một giá trị.

Với `groupOfNames` theo schema phổ biến, `cn` và `member` là những thuộc tính bắt buộc (`MUST`). Nhóm mới phải có ít nhất một giá trị `member`. Nếu cần nhóm rỗng, phải chọn mô hình/schema hoặc quy trình nghiệp vụ tương ứng mà directory hỗ trợ, thay vì bỏ qua kiểm tra.

### 1.1. Attribute multi-valued mang ngữ nghĩa tập giá trị

Trong LDAP, nhiều giá trị của cùng một attribute nhìn chung có **ngữ nghĩa tập hợp**, không phải mảng đã được sắp thứ tự. Ví dụ trên không có nghĩa Alice luôn là thành viên “đầu tiên”. Không nên dựa vào thứ tự server trả về, chỉ số `get(0)` hoặc thứ tự thêm vào `BasicAttribute` để suy ra mức độ ưu tiên.

Việc xác định **hai giá trị có được coi là trùng** phụ thuộc cú pháp và matching rule của attribute, cũng như cách directory thực thi. Với `member`, hai cách viết DN có thể được server so khớp theo quy tắc DN, trong khi phép so sánh chuỗi Java không nhất thiết cho cùng kết quả. Cũng không nên tự chuyển toàn bộ DN thành chữ thường rồi xem như quy tắc chuẩn hóa tổng quát.

`BasicAttribute` của JNDI hỗ trợ nhiều giá trị qua `add(...)`. Đối tượng này hữu ích để chuẩn bị dữ liệu phía Java; **nó không phải một bộ kiểm tra schema LDAP đầy đủ**.

```java
import javax.naming.directory.Attribute;
import javax.naming.directory.BasicAttribute;

Attribute members = new BasicAttribute("member");
members.add("uid=alice,ou=people,dc=example,dc=org");
members.add("uid=bob,ou=people,dc=example,dc=org");

int numberOfValues = members.size(); // 2 giá trị đã chuẩn bị ở Java.
```

### 1.2. Phân biệt `SINGLE-VALUE`, `MUST` và chính sách ứng dụng

| Quy tắc | Câu hỏi trả lời | Ví dụ |
| --- | --- | --- |
| `MUST` trong object class | Entry bắt buộc có **attribute này** hay không? | `groupOfNames` yêu cầu `member` |
| `MAY` trong object class | Schema cho phép attribute này xuất hiện không? | `description` có thể được cho phép |
| `SINGLE-VALUE` trong attribute type | Attribute có bị giới hạn tối đa một giá trị không? | Một số attribute định danh/trạng thái |
| Ràng buộc nghiệp vụ | API yêu cầu tối thiểu/tối đa bao nhiêu giá trị? | Nhóm có từ 1 đến 200 thành viên theo quy định ứng dụng |
| Ràng buộc hạ tầng | Server có giới hạn số giá trị/độ lớn entry/request không? | Các giới hạn do sản phẩm LDAP và cấu hình triển khai quyết định |

**`MUST` không đồng nghĩa `SINGLE-VALUE`.** Một attribute bắt buộc vẫn có thể có nhiều giá trị; một attribute tùy chọn vẫn có thể bị giới hạn một giá trị. Phải đọc đúng cả định nghĩa `objectClasses` và `attributeTypes` khi cần thực hiện schema validation.

## 2. Những giới hạn kích thước cần kiểm tra

“Kích thước attribute” có nhiều nghĩa. Chỉ kiểm tra `list.size()` hoặc `String.length()` là chưa đủ.

| Giới hạn | Cách đo hoặc câu hỏi | Ví dụ chính sách ứng dụng |
| --- | --- | --- |
| Số giá trị của một attribute | `member` có bao nhiêu giá trị? | 1–200 thành viên mỗi nhóm |
| Kích thước của **mỗi giá trị** | DN/chuỗi sau khi chuẩn bị chiếm bao nhiêu byte? | Tối đa 1.024 byte UTF-8 mỗi DN |
| Tổng kích thước các giá trị | Tổng dung lượng `member` cộng lại | Tối đa 64 KiB dữ liệu DN |
| Số ký tự logic | Giá trị tên có quá giới hạn mã Unicode/code point? | `cn` tối đa 64 ký tự ASCII theo ví dụ |
| Kích thước entry/request | Toàn bộ attributes, DN và overhead của giao thức | Theo directory và giới hạn API/gateway |
| Số entry trả về trong search | Kết quả truy vấn có quá nhiều entry? | Search size limit riêng, **khác** số value trong một attribute |

Các con số 200, 1.024 byte và 64 KiB ở đây là **giới hạn minh họa của ứng dụng**, không phải chuẩn chung của LDAP hay mặc định của Spring LDAP. Cần đo đạc, đối chiếu với directory thật và điều chỉnh theo nhu cầu.

### 2.1. `String.length()` không đo byte UTF-8

Java `String.length()` đếm **code unit UTF-16**. Một ký tự ngoài BMP có thể chiếm hai code unit, trong khi độ dài byte UTF-8 lại khác. Nếu một ràng buộc cụ thể được định nghĩa bằng byte, phải đo byte với charset xác định.

```java
import java.nio.charset.StandardCharsets;

String value = "Đặng";

int utf16Units = value.length();
int unicodeCodePoints = value.codePointCount(0, value.length());
int utf8Bytes = value.getBytes(StandardCharsets.UTF_8).length;
```

Không có một phép đo phù hợp cho mọi attribute:

- Với **ID theo mẫu ASCII** cố định, giới hạn `String.length()` thường dễ diễn giải vì mỗi ký tự hợp lệ là một code unit.
- Với **trường hiển thị Unicode**, cần định nghĩa rõ “ký tự” theo code point hay grapheme cluster, tránh nhầm ký tự có dấu với độ dài byte.
- Với **giới hạn byte do ứng dụng đặt**, đo sau khi chọn representation sẽ gửi; đồng thời cân nhắc overhead của LDAP encoding và request.
- Với **LDAP schema**, một khai báo syntax có ràng buộc độ dài như `{n}` phải được diễn giải theo loại syntax/schema và cách server áp dụng; không tự giả định mọi `{n}` đều là cùng một đơn vị byte hoặc ký tự.

### 2.2. Đặt giới hạn cả cho đầu vào trước khi parse

Đầu vào rất dài có thể tiêu tốn CPU và bộ nhớ ngay cả khi sau này bị từ chối. Với danh sách DN, hãy kiểm tra `null`, số phần tử và độ dài thô **trước** khi gọi `new LdapName(...)`. Sau parse, kiểm tra cấu trúc DN, nhánh được phép, rồi đo giới hạn cho giá trị biểu diễn sẽ gửi.

Nếu API đưa dữ liệu qua HTTP JSON, gateway và framework có thể có giới hạn request body riêng; kiểm tra ở tầng LDAP service vẫn cần thiết cho những caller khác như batch job hoặc message consumer.

## 3. Quy trình validation cho tập giá trị `member`

Giả sử API tạo nhóm nhận:

```json
{
  "cn": "developers",
  "memberDns": [
    "uid=alice,ou=people,dc=example,dc=org",
    "uid=bob,ou=people,dc=example,dc=org"
  ]
}
```

Quy tắc của ứng dụng mẫu:

1. `cn` gồm 1–64 ký tự ASCII được phép; ứng dụng dựng DN nhóm dưới `ou=groups`.
2. Danh sách `memberDns` có từ **1 đến 200** phần tử, không chứa `null` hoặc chuỗi rỗng.
3. Mỗi DN là DN đầy đủ có cú pháp hợp lệ, nằm **ngay dưới** `ou=people,dc=example,dc=org` và có RDN lá `uid=...`.
4. Mỗi DN có kích thước không quá **1.024 byte UTF-8** theo biểu diễn đã chuẩn bị.
5. Tổng byte UTF-8 của các DN không vượt **64 KiB**; không có DN bị lặp theo cách so sánh phía Java.
6. Service tự chọn `objectClass: top` và `groupOfNames`; không nhận tên attribute hoặc object class tùy ý từ request.

Kiểm tra DN trong danh sách **không xác thực** rằng member tồn tại, có đúng loại người dùng hay caller có quyền truy cập thành viên đó. Những điều này có thể yêu cầu bước nghiệp vụ riêng và vẫn chịu tác động của trạng thái directory.

### 3.1. Ví dụ Spring LDAP: chuẩn bị nhiều giá trị trước `bind`

```java
import java.nio.charset.StandardCharsets;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;
import java.util.regex.Pattern;

import javax.naming.InvalidNameException;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.BasicAttributes;
import javax.naming.ldap.LdapName;
import javax.naming.ldap.Rdn;

import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

public final class GroupDirectoryService {
    private static final int MAX_MEMBERS = 200;
    private static final int MAX_RAW_DN_CHARS = 2_048;
    private static final int MAX_DN_UTF8_BYTES = 1_024;
    private static final long MAX_TOTAL_UTF8_BYTES = 64L * 1_024;

    private static final Pattern GROUP_CN =
            Pattern.compile("[A-Za-z0-9][A-Za-z0-9._-]{0,63}");
    private static final Pattern UID =
            Pattern.compile("[A-Za-z0-9._-]{1,64}");

    private static final LdapName PEOPLE_BRANCH =
            parseTrustedDn("ou=people,dc=example,dc=org");

    private final LdapTemplate ldapTemplate;

    public GroupDirectoryService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public record NewGroup(String cn, List<String> memberDns) {}
    private record Prepared(LdapName relativeDn, Attributes attrs) {}

    public void create(NewGroup input) {
        Prepared group = prepare(input); // Chỉ validation; chưa gọi server.
        ldapTemplate.bind(group.relativeDn(), null, group.attrs());
    }

    private static Prepared prepare(NewGroup input) {
        if (input == null
                || input.cn() == null
                || !GROUP_CN.matcher(input.cn()).matches()) {
            throw new IllegalArgumentException("cn của nhóm không hợp lệ");
        }

        List<String> source = input.memberDns();
        if (source == null || source.isEmpty()
                || source.size() > MAX_MEMBERS) {
            throw new IllegalArgumentException(
                    "Nhóm phải có từ 1 đến 200 thành viên");
        }

        Set<LdapName> uniqueMembers = new LinkedHashSet<>();
        long totalBytes = 0;
        for (String rawDn : source) {
            LdapName personDn = requireMemberDn(rawDn);
            if (!uniqueMembers.add(personDn)) {
                throw new IllegalArgumentException(
                        "DN thành viên bị lặp trong request");
            }

            int bytes = personDn.toString()
                    .getBytes(StandardCharsets.UTF_8).length;
            if (bytes > MAX_DN_UTF8_BYTES) {
                throw new IllegalArgumentException(
                        "Một DN thành viên vượt 1024 byte UTF-8");
            }
            totalBytes += bytes;
            if (totalBytes > MAX_TOTAL_UTF8_BYTES) {
                throw new IllegalArgumentException(
                        "Tổng kích thước member vượt 64 KiB");
            }
        }

        Attributes attrs = new BasicAttributes(true);
        Attribute classes = new BasicAttribute("objectClass");
        classes.add("top");
        classes.add("groupOfNames");
        attrs.put(classes);
        attrs.put("cn", input.cn());

        Attribute members = new BasicAttribute("member");
        for (LdapName name : uniqueMembers) {
            members.add(name.toString());
        }
        attrs.put(members);

        // LdapTemplate dùng DN tương đối khi ContextSource đã có base.
        LdapName groupDn = LdapNameBuilder.newInstance()
                .add("ou", "groups")
                .add("cn", input.cn())
                .build();
        return new Prepared(groupDn, attrs);
    }

    private static LdapName requireMemberDn(String raw) {
        if (raw == null || raw.isBlank()
                || raw.length() > MAX_RAW_DN_CHARS
                || !raw.equals(raw.strip())
                || raw.codePoints().anyMatch(Character::isISOControl)) {
            throw new IllegalArgumentException(
                    "DN thành viên rỗng, quá dài hoặc chứa ký tự cấm");
        }

        try {
            LdapName dn = new LdapName(raw);
            if (!dn.startsWith(PEOPLE_BRANCH)
                    || dn.size() != PEOPLE_BRANCH.size() + 1) {
                throw new IllegalArgumentException(
                        "Thành viên phải nằm trực tiếp dưới ou=people");
            }

            Rdn leaf = dn.getRdn(dn.size() - 1);
            if (leaf.size() != 1
                    || !leaf.getType().equalsIgnoreCase("uid")
                    || !(leaf.getValue() instanceof String uid)
                    || !UID.matcher(uid).matches()) {
                throw new IllegalArgumentException(
                        "RDN uid của thành viên không hợp lệ");
            }
            return dn;
        } catch (InvalidNameException ex) {
            throw new IllegalArgumentException(
                    "DN thành viên sai cú pháp", ex);
        }
    }

    private static LdapName parseTrustedDn(String value) {
        try {
            return new LdapName(value);
        } catch (InvalidNameException ex) {
            throw new IllegalStateException(
                    "Nhánh LDAP cấu hình sai", ex);
        }
    }
}
```

Ví dụ gọi service:

```java
service.create(new GroupDirectoryService.NewGroup(
        "developers",
        List.of(
                "uid=alice,ou=people,dc=example,dc=org",
                "uid=bob,ou=people,dc=example,dc=org"
        )
));
```

Sau validation, entry được chuẩn bị có:

```text
DN tương đối: cn=developers,ou=groups
objectClass: top, groupOfNames
cn: developers
member: uid=alice,ou=people,dc=example,dc=org
member: uid=bob,ou=people,dc=example,dc=org
```

Điểm cần hiểu về ví dụ:

- Mọi giới hạn số lượng/kích thước đều được kiểm tra **trước** `ldapTemplate.bind(...)`. Nếu có lỗi, service không gửi yêu cầu tạo entry.
- `LinkedHashSet<LdapName>` chỉ loại trùng theo phép so sánh DN mà Java/JNDI áp dụng; **không khẳng định** phát hiện toàn bộ cặp giá trị mà matching rule phía LDAP server coi là tương đương. Directory vẫn có thể từ chối trùng giá trị sau chuẩn hóa.
- Danh sách đã được kiểm tra chỉ được dùng để tạo `member`; không có chuyển đổi một `Map<String,Object>` tùy ý thành LDAP attributes.
- Giá trị `member` là **DN đầy đủ** tham chiếu đến người dùng, trong khi DN của nhóm gửi tới `LdapTemplate` là DN **tương đối với base của `ContextSource`**. Hai ngữ cảnh không được lẫn lộn.
- Giới hạn tổng UTF-8 đo **các giá trị được chuẩn bị**, chưa cộng overhead của ASN.1/LDAP encoding, tên attribute, DN entry hay toàn bộ request. Server có thể từ chối một request dù cả ba giới hạn ứng dụng đều đạt.

## 4. Cập nhật multi-valued attribute: thêm, xóa hay thay toàn bộ?

LDAP hỗ trợ nhiều kiểu sửa attribute. Trong JNDI và Spring LDAP, có thể biểu diễn bằng `ModificationItem`:

| Loại sửa | Ý nghĩa | Ví dụ với `member` | Rủi ro cần kiểm soát |
| --- | --- | --- | --- |
| `ADD_ATTRIBUTE` | Thêm một hoặc nhiều giá trị | Thêm `uid=carol,...` vào nhóm | Giá trị đã tồn tại có thể gây lỗi; có thể vượt giới hạn số member |
| `REMOVE_ATTRIBUTE` | Xóa attribute hoặc những giá trị được chỉ định | Xóa đúng DN Bob | Xóa **giá trị cuối** của một `MUST` có thể vi phạm schema |
| `REPLACE_ATTRIBUTE` | Thay các giá trị hiện có bằng tập mới | Thay danh sách thành viên | Có thể ghi đè thay đổi đồng thời; danh sách mới vẫn phải hợp lệ |

**Cảnh báo quan trọng:** Xóa toàn bộ `member` khỏi một entry `groupOfNames` thường vi phạm ràng buộc `MUST`. Nếu nghiệp vụ cần nhóm rỗng, hãy thiết kế mô hình tương ứng; không giả định gửi một `member` rỗng sẽ được server chấp nhận.

### 4.1. Thêm một giá trị bằng `ModificationItem`

Sau khi kiểm tra DN thành viên và quyền nghiệp vụ, có thể gửi một thay đổi tăng dần thay vì đọc toàn bộ danh sách rồi ghi đè:

```java
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;
import javax.naming.ldap.LdapName;

import org.springframework.ldap.support.LdapNameBuilder;

LdapName relativeGroupDn = LdapNameBuilder.newInstance()
        .add("ou", "groups")
        .add("cn", "developers")
        .build();

String checkedMemberDn =
        "uid=carol,ou=people,dc=example,dc=org";

ModificationItem addMember = new ModificationItem(
        DirContext.ADD_ATTRIBUTE,
        new BasicAttribute("member", checkedMemberDn)
);

ldapTemplate.modifyAttributes(
        relativeGroupDn, new ModificationItem[] { addMember });
```

Đây là **minh họa cách gọi API**: trong hệ thống thực, `checkedMemberDn` phải đi qua validator DN, giới hạn byte, kiểm tra quyền và các quy tắc của nhóm trước khi gọi `modifyAttributes`. Không để caller gửi `ModificationItem` tùy ý.

Để xóa **một giá trị cụ thể**, `REMOVE_ATTRIBUTE` cần kèm đúng giá trị cần xóa; một lệnh xóa attribute mà không chỉ rõ giá trị có thể mang nghĩa xóa toàn bộ attribute. Với `groupOfNames`, việc xóa thành viên cuối cùng thường bị server từ chối do thiếu `member`.

### 4.2. Giới hạn 200 thành viên có được bảo đảm khi cập nhật đồng thời?

**Không**, nếu ứng dụng chỉ thực hiện chuỗi đơn giản “đọc số lượng hiện tại → so với 200 → gửi ADD”. Hai request có thể đồng thời quan sát 199 thành viên, đều qua validation rồi cùng thêm một người, khiến kết quả vượt 200 nếu directory không thực thi giới hạn đó.

Các hướng giải quyết tùy yêu cầu:

1. Đặt ràng buộc phía directory nếu sản phẩm LDAP hỗ trợ giới hạn tương ứng và có thể cấu hình được.
2. Dùng cơ chế thay đổi có điều kiện/kiểm soát phiên bản mà server thực sự hỗ trợ, hoặc điều phối ghi theo một writer đáng tin cậy.
3. Thiết kế chiến lược retry và xử lý xung đột theo trạng thái mới, không giả định một lần đọc trước đó tạo transaction LDAP xuyên nhiều thao tác.

`ADD_ATTRIBUTE` thường giúp tránh ghi đè toàn bộ danh sách như `REPLACE_ATTRIBUTE`, nhưng **không tự tạo ra giới hạn tổng số thành viên mang tính nguyên tử**. Kiểm tra cục bộ giúp giảm request sai; ràng buộc cần đúng dưới cạnh tranh phải được bảo đảm ở tầng có quyền kiểm soát trạng thái ghi.

## 5. Các lỗi LDAP liên quan đến nhiều giá trị và kích thước

Vượt giới hạn cục bộ nên được trả về dưới dạng lỗi input/business validation trước I/O. Khi đã gửi đến server, lỗi phụ thuộc schema, ACL và các ràng buộc thực tế:

| Hiện tượng | Kết quả có thể gặp | Diễn giải |
| --- | --- | --- |
| Ghi nhiều giá trị vào attribute schema `SINGLE-VALUE` | `constraintViolation` hoặc lỗi schema tùy server | Số lượng không hợp lệ |
| Tạo `groupOfNames` thiếu `member` | `objectClassViolation` | Vi phạm `MUST` |
| Thêm lại một giá trị mà server coi là đã tồn tại | `attributeOrValueExists` | Trùng sau quy tắc so khớp của server |
| Xóa giá trị không tồn tại | `noSuchAttribute` hoặc phản hồi phụ thuộc thao tác/server | Không thể áp dụng đúng thay đổi đã yêu cầu |
| Giá trị vượt ràng buộc schema/plugin | `constraintViolation` hoặc lỗi phù hợp khác | Cần xem ràng buộc thực của directory |
| Không có quyền sửa `member` | `insufficientAccessRights` | Lỗi ACL/danh tính LDAP |
| Server giới hạn kích thước request hoặc tài nguyên | Lỗi quản trị/tài nguyên, có khi đóng kết nối tùy server | Không tự suy ra là cùng lỗi “số lượng member” |

Một số mã số LDAP để nhận diện: `constraintViolation=19`, `attributeOrValueExists=20`, `noSuchAttribute=16`, `objectClassViolation=65`, `insufficientAccessRights=50`. Không nên ánh xạ máy móc tất cả thành HTTP `400`: lỗi schema profile, lỗi ACL tài khoản dịch vụ và lỗi hạ tầng có trách nhiệm xử lý khác nhau.

**Phân biệt rõ với search size limit:** LDAP result code `sizeLimitExceeded=4` thường nói về **giới hạn số entry trong kết quả tìm kiếm**, không phải “attribute `member` chứa quá nhiều giá trị”. Giới hạn `member` phải xem schema, chính sách server và cách API chuẩn bị dữ liệu.

## 6. Kiểm thử validation và thao tác thực tế

### 6.1. Unit test: danh sách rỗng hoặc sai DN phải dừng trước I/O

```java
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verifyNoInteractions;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.ldap.core.LdapTemplate;

class GroupDirectoryServiceTest {
    @Test
    void emptyMembersNeverCallLdap() {
        LdapTemplate template = mock(LdapTemplate.class);
        var service = new GroupDirectoryService(template);

        assertThrows(IllegalArgumentException.class, () ->
                service.create(
                        new GroupDirectoryService.NewGroup(
                                "developers", List.of())));

        verifyNoInteractions(template);
    }

    @Test
    void memberOutsideAllowedBranchNeverCallsLdap() {
        LdapTemplate template = mock(LdapTemplate.class);
        var service = new GroupDirectoryService(template);

        assertThrows(IllegalArgumentException.class, () ->
                service.create(
                        new GroupDirectoryService.NewGroup(
                                "developers",
                                List.of("uid=alice,ou=admins,dc=example,dc=org"))));

        verifyNoInteractions(template);
    }
}
```

### 6.2. Unit test: entry hợp lệ có đúng số giá trị `member`

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.ArgumentMatchers.isNull;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;

import java.util.List;
import javax.naming.Name;
import javax.naming.directory.Attributes;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.ldap.core.LdapTemplate;

class GroupAttributesTest {
    @Test
    void createsGroupWithTwoMemberValues() {
        LdapTemplate template = mock(LdapTemplate.class);
        var service = new GroupDirectoryService(template);
        service.create(new GroupDirectoryService.NewGroup(
                "developers",
                List.of(
                        "uid=alice,ou=people,dc=example,dc=org",
                        "uid=bob,ou=people,dc=example,dc=org"
                )));

        ArgumentCaptor<Name> dnCaptor =
                ArgumentCaptor.forClass(Name.class);
        ArgumentCaptor<Attributes> attrsCaptor =
                ArgumentCaptor.forClass(Attributes.class);

        verify(template).bind(
                dnCaptor.capture(), isNull(), attrsCaptor.capture());

        assertEquals("cn=developers,ou=groups",
                dnCaptor.getValue().toString());
        assertEquals(2, attrsCaptor.getValue().get("member").size());
    }
}
```

Test kiểm tra số lượng giá trị được **chuẩn bị**. Nó chưa xác nhận LDAP schema, ACL hoặc giới hạn kích thước của server mục tiêu; những điều đó cần integration test.

### 6.3. Bảng test case cần có

| Tình huống | Kỳ vọng |
| --- | --- |
| Một nhóm có hai member DN hợp lệ | `bind` nhận `member` với hai giá trị |
| `memberDns=null` hoặc danh sách rỗng | Từ chối trước I/O |
| Danh sách trên 200 giá trị | Từ chối trước I/O, không parse toàn bộ DN |
| Một DN dài vượt 1.024 byte UTF-8 | Từ chối trước I/O |
| Tổng kích thước member vượt 64 KiB | Từ chối trước I/O |
| DN có cú pháp sai hoặc nằm ngoài `ou=people` | Từ chối trước I/O |
| Hai DN tương đương theo `LdapName.equals` | Từ chối trùng ở client |
| Hai DN được server coi là trùng nhưng client không nhận diện | LDAP server có thể từ chối; xử lý lỗi trùng |
| Ghi 2 giá trị vào attribute `SINGLE-VALUE` theo schema test | LDAP server từ chối, mapper báo đúng lỗi |
| Xóa member cuối cùng khỏi `groupOfNames` | Server từ chối nếu vi phạm `MUST` |
| Hai request đồng thời thêm member khi gần giới hạn 200 | Phát hiện giới hạn không nguyên tử nếu chỉ kiểm tra trước; kiểm thử cơ chế bảo đảm được chọn |
| Server chấp nhận entry nhưng giới hạn tải/size ở API khác nhau | Theo dõi và cân chỉnh ngưỡng ứng dụng |

## 7. Kiểm tra khi sử dụng `LdapClient` hoặc ODM

Cùng một chính sách phải được áp dụng bất kể adapter nào thực hiện I/O:

- **`LdapTemplate`**: xây `Attributes` và `ModificationItem` sau validation; tránh truyền cấu trúc do client tạo trực tiếp.
- **`LdapClient`**: vẫn phải kiểm tra danh sách, giá trị và giới hạn kích thước trước khi thực thi thao tác. API fluent không tự hiểu giới hạn nghiệp vụ “tối đa 200 member”.
- **ODM**: field Java như `List<String>` hoặc `Set<String>` có thể ánh xạ tới attribute đa giá trị, nhưng mapping không tự giải quyết thứ tự, trùng theo LDAP matching rule, `SINGLE-VALUE` của schema hay xung đột khi nhiều writer cùng sửa.

Khi đọc entry qua mapper, không mặc định chỉ gọi `attribute.get()` cho mọi thuộc tính. Với attribute multi-valued, cần duyệt toàn bộ giá trị theo API tương ứng và kiểm tra kiểu; đồng thời không dựa vào thứ tự để diễn giải quyền hoặc vai trò. Một số attribute có thể không xuất hiện do ACL, mặc dù server lưu dữ liệu.

Với dữ liệu cá nhân hoặc thông tin định danh, tránh log toàn bộ danh sách member. Nên ghi tên thao tác, loại entry, số lượng giá trị, kích thước đã làm sạch và correlation ID, thay vì toàn bộ DN hay các attribute chứa thông tin nhạy cảm.

## 8. Checklist trước khi gọi LDAP

- [ ] Xác định attribute nào là **multi-valued**, attribute nào có `SINGLE-VALUE` theo schema thật.
- [ ] Phân biệt `MUST/MAY` với ràng buộc số lượng và chính sách nghiệp vụ.
- [ ] Đặt số lượng giá trị tối thiểu/tối đa và kiểm tra `null`, phần tử rỗng, kiểu dữ liệu.
- [ ] Định nghĩa rõ đơn vị giới hạn: code point, UTF-16 unit, UTF-8 byte hoặc ràng buộc syntax/schema cụ thể.
- [ ] Kiểm tra **mỗi giá trị**, **tổng các giá trị** và giới hạn request/entry tại các tầng phù hợp.
- [ ] Với DN, parse bằng `LdapName`, kiểm tra subtree/RDN, rồi mới đưa vào attribute.
- [ ] Phát hiện giá trị trùng trong request; vẫn xử lý matching rule và lỗi trùng từ server.
- [ ] Không phụ thuộc thứ tự của các giá trị LDAP để suy ra ưu tiên hay ý nghĩa nghiệp vụ.
- [ ] Chọn `ADD`/`REMOVE`/`REPLACE` phù hợp; kiểm tra trạng thái entry **sau sửa**, nhất là khi xóa giá trị `MUST`.
- [ ] Không giả định kiểm tra số lượng trước modify bảo đảm giới hạn khi nhiều request ghi đồng thời.
- [ ] Phân biệt giới hạn số giá trị attribute với **search size limit**.
- [ ] Test chặn input trước I/O và test tích hợp trên directory có schema/ACL tương ứng.

**Điểm cần nhớ:** Validation multi-valued cần xét cả **số lượng, cấu trúc từng giá trị, trùng lặp và tổng kích thước**, trong khi schema LDAP quyết định kiểu attribute và những ràng buộc thật sự được thực thi. Chuẩn bị dữ liệu đúng trước `LdapTemplate`/`LdapClient` giúp loại bỏ lỗi sớm; LDAP server tiếp tục chịu trách nhiệm về matching rule, quyền và trạng thái entry lúc ghi.
