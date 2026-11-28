# Ngăn LDAP injection trong bộ lọc và DN

Trong **Spring Data LDAP**, ứng dụng thường nhận dữ liệu từ form đăng nhập, màn hình tìm người dùng hoặc API quản trị rồi chuyển dữ liệu đó thành truy vấn LDAP hoặc **Distinguished Name (DN)** để đọc, tạo, sửa entry. Nếu ghép trực tiếp dữ liệu không đáng tin vào cú pháp LDAP, người dùng có thể vô tình hoặc cố ý làm thay đổi ý nghĩa truy vấn, chọn sai entry hoặc hướng thao tác tới nhánh thư mục ngoài dự kiến. Đây là nhóm lỗi **LDAP injection**.

Hai nơi thường xảy ra sai sót là **giá trị trong LDAP search filter** và **giá trị nằm trong DN/RDN**. Mỗi nơi có quy tắc escape riêng; xử lý đúng một loại không tự động bảo vệ loại còn lại. Bài học tập trung vào cách xây bộ lọc và DN an toàn khi dùng `LdapTemplate`, query builder và mô hình repository của Spring Data LDAP.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Chỉ ra vị trí dữ liệu đầu vào có thể thay đổi cú pháp hoặc phạm vi tìm kiếm LDAP.
- Phân biệt cách escape giá trị **filter theo RFC 4515** với cách escape **DN theo RFC 4514**.
- Dùng `LdapQueryBuilder` và `EqualsFilter` để truyền giá trị tìm kiếm như dữ liệu.
- Dùng `LdapNameBuilder` và `LdapName` để xử lý DN thay vì ghép chuỗi.
- Giới hạn thuộc tính được phép tìm, base DN và quyền thao tác; viết kiểm thử cho đầu vào có ký tự đặc biệt.

## 2. Nhận diện hai bề mặt của LDAP injection

LDAP tổ chức entry thành cây. Một ví dụ:

```text
dc=example,dc=com
├── ou=people
│   ├── uid=alice
│   └── uid=bob
└── ou=admins
    └── uid=operator
```

Với dữ liệu mẫu này, ứng dụng có thể:

1. **Tìm entry** dưới `ou=people` bằng filter `(uid=alice)`.
2. **Truy cập entry theo tên** bằng DN tương đối `uid=alice,ou=people`.

Nếu phần `alice` được lấy từ request, ứng dụng phải xem nó là **giá trị**, không phải một đoạn cú pháp LDAP hoàn chỉnh.

| Ngữ cảnh | Cú pháp bao quanh giá trị | Ký tự dễ gây nhầm | API nên dùng |
| --- | --- | --- | --- |
| Search filter | `(uid=<giá trị>)` | `*`, `(`, `)`, `\`, NUL | `LdapQueryBuilder`, `EqualsFilter` |
| DN/RDN | `uid=<giá trị>,ou=people` | `,`, `+`, `=`, `\`, khoảng trắng đặc biệt, `#` đầu giá trị | `LdapNameBuilder`, `LdapName` |

Hai kiểu injection có tác động khác nhau. **Filter injection** có thể làm truy vấn trả nhiều entry hơn, đổi điều kiện logic hoặc khiến kết quả được sử dụng sai trong kiểm tra tài khoản/quyền. **DN injection** có thể làm chuỗi tên bị phân tích thành nhiều RDN, dẫn tới chọn sai vị trí trong cây hoặc sai mục tiêu của thao tác ghi. Tác động thực tế vẫn phụ thuộc vào quyền của tài khoản kết nối, cấu hình directory và cách ứng dụng xử lý kết quả.

## 3. Filter injection: dấu `*` có thể thay đổi truy vấn

Bộ lọc LDAP dùng cú pháp theo RFC 4515. Một bộ lọc so sánh bằng đơn giản:

```ldap
(uid=alice)
```

Nếu xây filter như sau, giá trị ngoài ứng dụng trở thành một phần của **cú pháp**:

```java
// Ví dụ KHÔNG AN TOÀN: không sử dụng trong ứng dụng thực tế.
String filter = "(uid=" + uidFromRequest + ")";

List<String> results = ldapTemplate.search(
        "ou=people",
        filter,
        (AttributesMapper<String>) attrs ->
                attrs.get("uid").get().toString()
);
```

Chỉ cần `uidFromRequest = "*"`, filter được tạo sẽ là `(uid=*)`. Theo cú pháp LDAP, đây là **kiểm tra thuộc tính uid tồn tại**, không còn là phép tìm người dùng có giá trị `uid` đúng bằng ký tự `*`. Nếu code tiếp tục lấy bản ghi đầu tiên để xác định danh tính, lỗi có thể trở nên nghiêm trọng.

Một filter còn có cấu trúc logic như `(&(...)(...))`, `(|(...)(...))` và `(!( ... ))`. Vì thế ghép chuỗi đầu vào vào filter có thể làm thay đổi số lượng điều kiện hoặc quan hệ AND/OR khi có ký tự đặc biệt. Việc kiểm tra chỉ một ví dụ đầu vào bình thường như `alice` sẽ không phát hiện lỗi.

### 3.1. Escape giá trị filter theo RFC 4515

Trong **giá trị của một filter assertion**, các ký tự sau phải được biểu diễn bằng mã hex với dấu gạch chéo ngược:

| Ký tự gốc | Cách biểu diễn trong filter | Lý do |
| --- | --- | --- |
| `*` | `\2a` | Dấu `*` thô có ý nghĩa wildcard/presence. |
| `(` | `\28` | Bắt đầu cấu trúc nhóm filter. |
| `)` | `\29` | Kết thúc cấu trúc nhóm filter. |
| `\` | `\5c` | Ký tự mở đầu escape. |
| NUL (`U+0000`) | `\00` | Byte NUL phải được escape. |

Ví dụ giá trị tìm kiếm `alice*` cần được truyền thành giá trị literal:

```text
Giá trị người dùng:         alice*
Filter sai khi ghép chuỗi:  (uid=alice*)
Filter với literal '*':     (uid=alice\2a)
```

Trong cách biểu diễn cuối, server tìm **giá trị có dấu sao thật**, thay vì thực hiện phép so khớp tiền tố. Các ký tự Unicode khác cũng phải được biểu diễn hợp lệ theo UTF-8; nếu cần xử lý byte hoặc tên ở mức thấp, hãy dùng thư viện tuân thủ RFC thay vì tự viết bộ escape.

**Không dùng duy nhất một hàm escape cho cả filter và DN.** Ví dụ dấu phẩy có ý nghĩa phân tách RDN trong DN, nhưng dấu phẩy thông thường không phải ký tự phân tách trong giá trị filter. Ngược lại dấu `*` là ký tự có ý nghĩa trong filter, nhưng không phải dấu phân tách RDN trong DN.

## 4. Cách tìm kiếm an toàn với Spring LDAP

### 4.1. Dùng `LdapQueryBuilder` để xử lý giá trị như dữ liệu

API query builder của Spring LDAP xây cấu trúc filter từ các thành phần có kiểu thay vì yêu cầu ứng dụng tự nối chuỗi:

```java
import java.util.List;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;

import static org.springframework.ldap.query.LdapQueryBuilder.query;

public class DirectorySearch {
    private final LdapTemplate ldapTemplate;

    public DirectorySearch(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<String> findUserIds(String uidFromRequest) {
        if (uidFromRequest == null || uidFromRequest.isBlank()) {
            throw new IllegalArgumentException("uid không được rỗng");
        }

        LdapQuery ldapQuery = query()
                .base("ou=people")              // Cố định theo nghiệp vụ
                .where("uid").is(uidFromRequest); // Giá trị được encode

        return ldapTemplate.search(
                ldapQuery,
                (AttributesMapper<String>) attrs ->
                        attrs.get("uid").get().toString()
        );
    }
}
```

Khi `uidFromRequest` chứa `*`, `(` hoặc `\`, điều kiện `is(...)` mã hóa giá trị theo quy tắc filter. Nó không biến đầu vào thành toán tử wildcard hay nhóm AND/OR mới. Trong ví dụ, `base` và tên thuộc tính `uid` do lập trình viên quyết định; chúng không lấy trực tiếp từ người dùng.

Nếu cần nhiều điều kiện, để builder ghép các điều kiện cố định:

```java
LdapQuery ldapQuery = query()
        .base("ou=people")
        .where("objectClass").is("inetOrgPerson")
        .and("uid").is(uidFromRequest);
```

Đừng tạo toàn bộ filter bằng nối chuỗi rồi đưa vào `.filter(rawFilter)` với dữ liệu không đáng tin. Một số API cố ý cho phép truyền **filter dạng thô** để viết biểu thức phức tạp; dùng chúng chỉ khi toàn bộ cú pháp do code đáng tin cậy tạo ra và các giá trị động đã được encode đúng ngữ cảnh.

### 4.2. Dùng `EqualsFilter` khi cần một đối tượng filter

Spring LDAP cũng có thư viện xây bộ lọc:

```java
import org.springframework.ldap.filter.EqualsFilter;
import org.springframework.ldap.filter.AndFilter;

AndFilter filter = new AndFilter();
filter.and(new EqualsFilter("objectClass", "inetOrgPerson"));
filter.and(new EqualsFilter("uid", uidFromRequest));

String encodedFilter = filter.encode();

List<String> results = ldapTemplate.search(
        "ou=people",
        encodedFilter,
        (AttributesMapper<String>) attrs ->
                attrs.get("uid").get().toString()
);
```

`EqualsFilter` encode **giá trị so sánh**; `AndFilter` tạo cấu trúc logic AND. Dù vậy, lập trình viên vẫn phải kiểm soát **tên thuộc tính**, **base tìm kiếm**, phạm vi tìm kiếm và các toán tử được sử dụng. Không tự đưa tên thuộc tính hoặc filter template do client cung cấp vào API.

### 4.3. Nếu người dùng được chọn trường tìm kiếm, dùng whitelist

Giả sử UI cho phép tìm theo mã tài khoản hoặc tên hiển thị. Đừng cho client gửi trực tiếp chuỗi thuộc tính LDAP tùy ý như `userPassword`. Hãy ánh xạ lựa chọn nghiệp vụ sang một tập tên thuộc tính được phép:

```java
String ldapAttribute = switch (searchFieldFromRequest) {
    case "userId" -> "uid";
    case "displayName" -> "cn";
    default -> throw new IllegalArgumentException("Trường tìm kiếm không được phép");
};

LdapQuery ldapQuery = query()
        .base("ou=people")
        .where(ldapAttribute).is(searchTermFromRequest);
```

Đây là **allowlist** cho cấu trúc truy vấn; query builder lo encode **giá trị**. Hai lớp kiểm soát giải quyết hai rủi ro khác nhau.

## 5. DN injection: dấu phẩy có thể làm thay đổi cây

DN trong LDAP dùng cú pháp chuỗi theo RFC 4514. Một DN như:

```text
uid=alice,ou=people,dc=example,dc=com
```

được tạo từ các **RDN** ngăn bởi dấu phẩy. Phần trái nhất là RDN của entry (`uid=alice`); các phần bên phải lần lượt là ancestor của entry.

Đoạn code sau nguy hiểm vì ghép giá trị `uid` vào một tên có cấu trúc:

```java
// Ví dụ KHÔNG AN TOÀN.
String relativeDn = "uid=" + uidFromRequest + ",ou=people";
ldapTemplate.lookup(relativeDn, (AttributesMapper<String>) attrs ->
        attrs.get("cn").get().toString());
```

Khi đầu vào chứa dấu phẩy và cặp `thuộc_tính=giá_trị`, cú pháp tên có thể có thêm một RDN ngoài dự kiến. Kết quả là thao tác có thể truy cập hoặc ghi vào entry khác với định danh mà chương trình dự định. Với các lệnh ghi như `bind`, `modifyAttributes` hay `rename`, kiểm soát DN càng quan trọng.

### 5.1. Escape DN không giống escape filter

Trong giá trị RDN, RFC 4514 yêu cầu escape các ký tự cú pháp như `,`, `+`, `"`, `\`, `<`, `>`, `;`, `=`, NUL; thêm vào đó là khoảng trắng ở đầu/cuối và dấu `#` ở đầu giá trị. Có thể dùng dấu gạch chéo ngược trước ký tự hoặc biểu diễn hex phù hợp.

| Giá trị RDN mong muốn | Cách biểu diễn trong DN | Điều cần hiểu |
| --- | --- | --- |
| `Doe, Jane` | `cn=Doe\, Jane` | Dấu phẩy thuộc giá trị, không tách RDN. |
| `R&D+Ops` | `cn=R&D\+Ops` | Dấu `+` thuộc giá trị, không tạo RDN đa giá trị. |
| `#team` | `cn=\#team` | `#` ở đầu giá trị cần escape. |
| `Alice=1` | `cn=Alice\=1` | Dấu bằng là dữ liệu trong giá trị. |

Chẳng hạn DN `cn=Doe\, Jane,ou=people,dc=example,dc=com` vẫn có ba RDN. Không được tách DN bằng `split(",")` vì dấu phẩy được escape vẫn thuộc giá trị.

### 5.2. Dùng `LdapNameBuilder` thay vì nối chuỗi

Với Spring LDAP, xây DN từ từng **loại thuộc tính** và **giá trị**:

```java
import javax.naming.Name;
import org.springframework.ldap.support.LdapNameBuilder;

Name relativeDn = LdapNameBuilder.newInstance()
        .add("ou", "people")
        .add("uid", uidFromRequest)
        .build();

// Ví dụ: uidFromRequest = "alice,ou=admins"
// Dấu phẩy và dấu bằng nằm bên trong giá trị uid,
// không được hiểu là RDN khác.
```

Builder xử lý biểu diễn RDN cần escape và thứ tự các thành phần DN. Trong ví dụ này, `ou=people` là nhánh đáng tin cậy được quyết định bởi ứng dụng. **Không đưa nguyên chuỗi DN người dùng nhập vào builder như một đoạn tên tin cậy**; làm vậy có thể tái nhập cấu trúc không được phép.

Giả sử `spring.ldap.base` được cấu hình là `dc=example,dc=com`. DN tương đối do đoạn code trên tạo là `uid=<giá trị>,ou=people`. Thông thường `LdapTemplate` sẽ áp dụng base từ `ContextSource` khi thực hiện thao tác; đừng nối thêm `dc=example,dc=com` lần nữa.

Ví dụ dùng DN đã xây để đọc đúng một entry:

```java
String commonName = ldapTemplate.lookup(
        relativeDn,
        (AttributesMapper<String>) attrs ->
                attrs.get("cn").get().toString()
);
```

Nếu cần tạo entry bằng `LdapTemplate.bind(...)`, có thể sử dụng chính `relativeDn` đó với một tập `Attributes` hợp lệ theo schema và `objectClass` của directory. Tạo DN an toàn giúp bảo vệ **cấu trúc tên**; nó không tự kiểm tra quyền tạo entry hoặc các thuộc tính có được phép ghi hay không.

### 5.3. Đầu vào là DN đầy đủ: phải phân tích và kiểm tra phạm vi

Một số API quản trị nhận một **DN hoàn chỉnh** để chọn entry. Lúc này escape toàn bộ chuỗi như một giá trị RDN sẽ làm sai mục đích. Cần phân tích nó thành cấu trúc tên, kiểm tra cú pháp, phạm vi và quyền trước khi thao tác.

```java
import javax.naming.InvalidNameException;
import javax.naming.ldap.LdapName;

public static LdapName parseAllowedPersonDn(String suppliedDn)
        throws InvalidNameException {

    LdapName dn = new LdapName(suppliedDn);
    LdapName allowedParent =
            new LdapName("ou=people,dc=example,dc=com");

    // JNDI LdapName đánh chỉ số từ thành phần phía phải của chuỗi DN.
    // startsWith ở đây so theo các thành phần gốc của Name.
    if (!dn.startsWith(allowedParent)
            || dn.size() != allowedParent.size() + 1) {
        throw new IllegalArgumentException(
                "DN phải là entry con trực tiếp của ou=people");
    }

    if (!"uid".equalsIgnoreCase(dn.getRdn(dn.size() - 1).getType())) {
        throw new IllegalArgumentException("Entry phải dùng RDN uid");
    }

    return dn;
}
```

`LdapName` cho phép so sánh thành phần có cấu trúc, tránh lỗi dùng `String.endsWith(...)` hoặc `contains(...)` với chuỗi DN có escape hay cách biểu diễn khác nhau. Ví dụ trên chỉ chấp nhận **con trực tiếp** dưới một parent cố định; nếu ứng dụng cho phép nhánh con nhiều cấp, cần đặc tả chính sách khác và kiểm tra rõ từng nhánh.

Việc parse/giới hạn DN là một **kiểm tra đầu vào**, không thay thế kiểm soát quyền. Ứng dụng vẫn phải xác định người gọi có quyền đối với entry đích, đồng thời tài khoản LDAP phải được server cấp ACL phù hợp. Trong API xử lý người dùng thông thường, cách an toàn hơn là nhận **uid** làm dữ liệu và tự dựng DN dưới nhánh cố định, thay vì nhận DN tùy ý.

## 6. Không nhầm escape, validation và authorization

Ba cơ chế này bổ sung cho nhau:

| Cơ chế | Trả lời câu hỏi | Ví dụ |
| --- | --- | --- |
| **Escape/encode theo ngữ cảnh** | Ký tự đầu vào có bị hiểu thành cú pháp LDAP không? | `where("uid").is(uid)`; `LdapNameBuilder.add("uid", uid)`. |
| **Validation nghiệp vụ** | Giá trị này có nằm trong định dạng, độ dài, loại dữ liệu được chấp nhận không? | Quy tắc `uid` dài 1–64 ký tự, chỉ chứa chữ/số/`._-`. |
| **Authorization/ACL** | Người gọi và tài khoản kết nối có được đọc/ghi entry này không? | Chỉ quản trị viên được xem nhánh `ou=admins`; service account bị giới hạn nhánh. |

Một mã `uid` không chứa ký tự đặc biệt vẫn có thể thuộc về người dùng mà caller không được phép xem. Ngược lại, một giá trị hợp lệ về nghiệp vụ vẫn cần encode nếu dùng trong filter hoặc DN. Không nên dùng regex validation như phương án thay thế cho escaping.

Ví dụ kiểm tra định dạng mã tài khoản của một hệ thống **chỉ cho phép ASCII**:

```java
import java.util.regex.Pattern;

private static final Pattern UID_PATTERN =
        Pattern.compile("[A-Za-z0-9._-]{1,64}");

static String validateUid(String uid) {
    if (uid == null || !UID_PATTERN.matcher(uid).matches()) {
        throw new IllegalArgumentException("uid không hợp lệ");
    }
    return uid;
}
```

Đây là **quy tắc nghiệp vụ minh họa**, không phải yêu cầu chung của LDAP. Những hệ thống cần Unicode hoặc định danh có ký tự đặc biệt phải thiết kế quy tắc phù hợp, đồng thời vẫn dùng builder cho mọi giá trị động.

## 7. Những điểm cần kiểm soát ngoài hàm escape

**Tên thuộc tính và toán tử:** đặt sẵn hoặc cho chọn qua allowlist. Không nhận cả đoạn `(uid=...)`, tên thuộc tính, toán tử hay chuỗi `(|...)` từ client như một filter đã hoàn thiện.

**Base DN và phạm vi tìm kiếm:** chọn nhánh đã biết từ cấu hình và nghiệp vụ. Escape giá trị trong `where(...)` không ngăn việc ứng dụng cho client tùy ý đổi `base` sang nhánh khác. Sử dụng phạm vi tìm kiếm vừa đủ (entry, một cấp, subtree) và giới hạn kết quả khi phù hợp.

**Dữ liệu cho repository:** phương thức dạng `findByUid(String uid)` của Spring Data LDAP thể hiện tiêu chí theo thuộc tính; cần giữ cách truyền dữ liệu như **tham số** của cơ chế truy vấn thay vì tự tạo raw LDAP filter từ input. Khi viết phương thức tùy biến bằng `LdapTemplate`, vẫn tuân thủ cách xây filter và DN tương ứng.

**Ràng buộc schema:** `objectClass` và thuộc tính LDAP quyết định entry hợp lệ khi tạo/sửa. Ngăn injection không có nghĩa là mọi entry từ request đều được phép ghi. Không trao quyền chọn `objectClass` hoặc thuộc tính nhạy cảm tùy ý.

**Kết nối và quyền:** dùng TLS cho LDAP khi truyền thông tin xác thực và dữ liệu nhạy cảm; kiểm tra chứng chỉ máy chủ; lưu bí mật ngoài mã nguồn; đặt ACL theo nguyên tắc quyền tối thiểu. Lỗ hổng trong filter không được phép biến tài khoản dịch vụ thành quyền quản trị toàn bộ directory.

**Giới hạn tài nguyên:** truy vấn có wildcard chủ động, phạm vi lớn hoặc điều kiện tốn kém có thể tiêu tốn tài nguyên dù không có injection. Áp dụng size/time limit của LDAP, pagination và giới hạn truy vấn phù hợp.

**Thông điệp lỗi và log:** không log mật khẩu hoặc dữ liệu nhạy cảm; tránh trả nguyên filter, DN nội bộ và chi tiết directory cho người dùng cuối. Có thể ghi mã tương quan và thông tin kỹ thuật cần thiết vào log bảo vệ phù hợp.

## 8. Kiểm thử escaping và hành vi tìm kiếm

Kiểm thử nên tách thành hai tầng: kiểm tra **cách builder mã hóa giá trị** và kiểm tra **kết quả thực tế với directory**. Một unit test chỉ xác nhận chuỗi đã escape chưa đủ chứng minh base, quyền và schema ở môi trường chạy.

### 8.1. Kiểm thử filter không diễn giải `*` thành wildcard

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;
import org.springframework.ldap.filter.EqualsFilter;

class SafeFilterTest {
    @Test
    void escapesAsteriskAsLiteralValue() {
        String filter = new EqualsFilter("uid", "alice*").encode();
        assertEquals("(uid=alice\\2a)", filter);
    }
}
```

Trong Java string literal `"\\2a"` biểu diễn đúng một dấu gạch chéo ngược rồi tới ký tự `2a` trong filter. Kết quả có thể được viết bằng chữ hoa hoặc chữ thường cho mã hex tùy encoder; điều quan trọng là `*` trong giá trị đã được escape.

### 8.2. Kiểm thử DN giữ dấu phẩy trong RDN

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import javax.naming.ldap.LdapName;
import org.junit.jupiter.api.Test;
import org.springframework.ldap.support.LdapNameBuilder;

class SafeDnTest {
    @Test
    void keepsCommaInsideRdnValue() {
        LdapName dn = LdapNameBuilder.newInstance()
                .add("ou", "people")
                .add("cn", "Doe, Jane")
                .build();

        assertEquals(2, dn.size());
        assertEquals("Doe, Jane",
                dn.getRdn(dn.size() - 1).getValue());
    }
}
```

Test kiểm tra **cấu trúc Name** thay vì chỉ so chuỗi DN, bởi một số ký tự có thể được biểu diễn bằng nhiều cách escape hợp lệ.

### 8.3. Bộ trường hợp nên đưa vào kiểm thử

| Đầu vào | Kỳ vọng với filter tìm bằng | Kỳ vọng với DN builder |
| --- | --- | --- |
| `alice` | Tìm chính xác `alice`. | Một RDN `uid=alice`. |
| `*` | Ký tự `*` được xem là dữ liệu, không thành presence/wildcard. | Một giá trị RDN chứa `*`, không thêm RDN. |
| `a(b)` | Dấu ngoặc được encode, không thay đổi cấu trúc filter. | Dấu ngoặc là dữ liệu của RDN. |
| `Doe, Jane` | Dấu phẩy là dữ liệu trong filter. | Dấu phẩy được escape, không chia thành hai RDN. |
| `Dev+Ops` | Dấu cộng là dữ liệu trong filter. | Dấu cộng không tạo RDN đa giá trị. |
| `a\b` | Dấu gạch chéo ngược được encode đúng. | Dấu gạch chéo ngược được escape đúng. |
| Giá trị có khoảng trắng đầu/cuối | So khớp giá trị literal theo quy tắc directory. | Escape khoảng trắng ở vị trí bắt buộc theo RFC 4514. |
| `#tag` | `#` là dữ liệu trong filter. | `#` ở đầu giá trị RDN được escape. |

Ở tầng integration test, nên có sẵn fixture phân biệt rõ hai giá trị như `alice` và `alice*`, sau đó kiểm tra rằng tìm theo giá trị literal `alice*` không trả tất cả người dùng bắt đầu bằng `alice`. Đồng thời xác minh lookup hoặc ghi entry với dấu phẩy trong RDN vẫn nằm đúng nhánh dự kiến. Chạy trên directory **dành riêng cho test**, với tài khoản và ACL như cấu hình thực tế.

## 9. Sai lầm thường gặp

| Sai lầm | Vì sao nguy hiểm | Cách làm đúng |
| --- | --- | --- |
| Ghép `"(uid=" + uid + ")"` | Giá trị có thể tạo wildcard hoặc thay đổi cấu trúc filter. | `query().where("uid").is(uid)` hoặc `EqualsFilter`. |
| Ghép `"uid=" + uid + ",ou=people"` | Dấu phẩy, dấu cộng, dấu bằng có thể đổi cấu trúc DN. | `LdapNameBuilder.add("uid", uid)`. |
| Dùng một hàm escape chung cho filter và DN | Hai cú pháp có tập ký tự đặc biệt khác nhau. | Chọn encoder theo **đích sử dụng**. |
| Chỉ kiểm tra `uid` bằng regex | Regex không chứng minh mã hóa đúng hoặc quyền truy cập. | Kết hợp validation, builder và authorization. |
| Đưa cả filter hoặc tên thuộc tính từ request vào query | Client có thể kiểm soát cấu trúc tìm kiếm. | Giữ cấu trúc cố định, allowlist tên thuộc tính. |
| So sánh DN bằng `String.endsWith(...)` | So sánh ký tự không hiểu RDN và cách escape hợp lệ. | Parse `LdapName`, kiểm tra từng thành phần và quyền. |
| Tin rằng filter đã escape thì có thể đọc cả directory | Escape chỉ giữ nguyên ý nghĩa dữ liệu, không cấp quyền. | Cố định base/scope, giới hạn kết quả và dùng ACL. |

## 10. Bài thực hành có đáp án

**Bài 1.** Một ứng dụng tạo filter bằng `"(uid=" + requestUid + ")"`. Người dùng nhập `*`. Vì sao có thể trả về nhiều entry và cách sửa là gì?

**Đáp án:** Filter `(uid=*)` kiểm tra thuộc tính `uid` có tồn tại. Dùng `query().base("ou=people").where("uid").is(requestUid)` để dấu `*` được escape thành giá trị literal. Đồng thời xử lý kết quả không mặc định bản ghi đầu tiên là danh tính cần tìm.

**Bài 2.** Với đầu vào `cn = "Doe, Jane"`, tên `"cn=" + cn + ",ou=people"` có vấn đề gì?

**Đáp án:** Dấu phẩy trong giá trị bị hiểu thành ranh giới RDN khi không được escape. Dùng `LdapNameBuilder.newInstance().add("ou", "people").add("cn", cn).build()` để có DN hợp lệ với dấu phẩy nằm trong giá trị.

**Bài 3.** Đã dùng `EqualsFilter("uid", input)` nhưng ứng dụng cho client tự chọn `base` là `ou=admins`. Đã ngăn đủ mọi nguy cơ chưa?

**Đáp án:** Chưa. `EqualsFilter` encode giá trị tìm kiếm, nhưng không kiểm soát phạm vi. Base/scope phải được quyết định bởi nghiệp vụ và quyền; directory phải có ACL ngăn truy cập trái phép.

**Bài 4.** Một API nhận nguyên DN từ request. Tại sao kiểm tra `suppliedDn.endsWith("dc=example,dc=com")` không phù hợp?

**Đáp án:** Đây là so sánh chuỗi, không phân tích RDN hoặc xác định nhánh được phép. Cần parse bằng `LdapName`, kiểm tra DN có nằm dưới parent phù hợp bằng so sánh thành phần, kiểm tra cấp con được phép và thực thi authorization.

## 11. Ghi nhớ

- **LDAP filter** và **DN** có cú pháp escape khác nhau: filter theo RFC 4515, DN theo RFC 4514.
- Với filter, hãy dùng `LdapQueryBuilder`/`EqualsFilter`; với DN, hãy dùng `LdapNameBuilder`/`LdapName`.
- Cố định hoặc allowlist **thuộc tính, toán tử, base và phạm vi tìm kiếm**; không biến request thành cả một filter hoặc DN tùy ý.
- **Escape giữ nguyên ý nghĩa dữ liệu**; validation kiểm tra định dạng, còn authorization/ACL quyết định ai được truy cập entry nào.
- Kiểm thử các ký tự đặc biệt, xác minh kết quả trên directory và duy trì kết nối LDAP bảo mật cùng quyền tối thiểu.
