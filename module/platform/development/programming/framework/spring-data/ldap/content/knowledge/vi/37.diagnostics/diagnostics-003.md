# DN bị lặp base, sai RDN hoặc escape không đúng

## 1. Mục tiêu và tình huống chẩn đoán

Trong **Spring Data LDAP**, một entry được xác định bằng **distinguished name (DN)**, không phải khóa số tự tăng như nhiều bảng quan hệ. DN biểu diễn đường đi trong cây LDAP; mỗi thành phần **relative distinguished name (RDN)** mô tả một cấp của đường đi. Các lớp Spring LDAP như `ContextSource`, `LdapTemplate`, Object-Directory Mapping (ODM) và `LdapRepository` giúp giảm mã JNDI, nhưng không thể tự đoán một DN được tạo sai.

Ba nhóm lỗi dễ gặp là:

1. **Lặp base DN**: cấu hình kết nối đã có `dc=example,dc=org` nhưng code lại truyền thêm đầy đủ base đó, khiến hệ thống tìm sai nhánh.
2. **Sai RDN**: thiếu `uid=...`, đảo vị trí các thành phần, dùng nhầm `cn` thay vì `uid` hoặc đặt chỉ số `@DnAttribute` sai.
3. **Escape sai**: tự ghép DN bằng chuỗi chứa dấu phẩy, dấu cộng, dấu gạch chéo ngược, khoảng trắng đặc biệt; đôi khi còn nhầm cách escape DN với LDAP search filter.

Một lỗi có thể hiển thị thành `NameNotFoundException`, `InvalidNameException`, `NameAlreadyBoundException`, lỗi schema hoặc chỉ đơn giản là trả về danh sách rỗng. Cần phân biệt **vị trí đang truy cập**, **cú pháp DN** và **điều kiện tìm kiếm** trước khi chỉnh code.

### Dữ liệu mẫu xuyên suốt

```text
dc=example,dc=org                            (base DN)
└── ou=people                                (nhánh chứa người dùng)
    ├── uid=linh                             (entry người dùng)
    ├── uid=an
    └── uid=nguyen.tran

DN đầy đủ của Linh:
uid=linh,ou=people,dc=example,dc=org

DN tương đối với base dc=example,dc=org:
uid=linh,ou=people

RDN của chính entry Linh:
uid=linh
```

Entry `uid=linh` có thể sử dụng các `objectClass` `top`, `person`, `organizationalPerson` và `inetOrgPerson`, cùng những thuộc tính như `uid`, `cn`, `sn` và `mail`. RDN và thuộc tính phải phù hợp với schema của directory; thao tác thành công còn phụ thuộc vào quyền bind, ACL và việc entry thực sự tồn tại.

## 2. Hiểu cấu trúc DN trước khi sửa lỗi

DN LDAP có cú pháp phân cấp; khi viết thành chuỗi, **entry cụ thể nhất nằm bên trái** và phần gốc nằm bên phải:

```text
uid=linh,ou=people,dc=example,dc=org
└──────┘ └───────┘ └────────────────┘
  RDN     cha gần      base/root
  entry   nhất
```

| Thuật ngữ | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| DN đầy đủ (*full DN*) | `uid=linh,ou=people,dc=example,dc=org` | Tên entry khi tham chiếu từ gốc directory. |
| Base DN của kết nối | `dc=example,dc=org` | Gốc dùng cho các thao tác tương đối trong `ContextSource`. |
| DN tương đối (*relative DN*) | `uid=linh,ou=people` | Phần đường dẫn còn lại khi đã có base của kết nối. |
| RDN entry | `uid=linh` | Thành phần định danh gần entry nhất. |
| Parent DN | `ou=people,dc=example,dc=org` | Entry cha trực tiếp. |
| Search base | `ou=people` | Vùng bắt đầu tìm kiếm, thường tương đối với base của `ContextSource`. |
| LDAP filter | `(uid=linh)` | Điều kiện tìm; **không phải DN**. |

Đừng cắt DN theo dấu phẩy bằng `split(",")`. Một giá trị RDN hợp lệ có thể chứa dấu phẩy được escape, ví dụ `cn=Doe\, Jane,ou=people,dc=example,dc=org`; chia chuỗi thô sẽ làm vỡ một RDN thành hai phần sai.

### 2.1. Thứ tự RDN trong JNDI

`javax.naming.ldap.LdapName` biểu diễn DN như một `Name` với thứ tự index bên trong từ thành phần ít cụ thể nhất đến cụ thể nhất. Với:

```text
uid=linh,ou=people,dc=example,dc=org
```

thì `getRdn(0)` là `dc=org`, còn `getRdn(name.size() - 1)` là `uid=linh`. Đừng suy đoán rằng RDN đầu tiên xuất hiện ở bên trái chuỗi luôn tương ứng với `getRdn(0)` trong JNDI.

```java
import javax.naming.ldap.LdapName;
import javax.naming.ldap.Rdn;

LdapName name = new LdapName(
    "uid=linh,ou=people,dc=example,dc=org"
);

Rdn rootMost = name.getRdn(0);                 // dc=org
Rdn leafMost = name.getRdn(name.size() - 1);  // uid=linh
System.out.println(leafMost.getType());       // uid
System.out.println(leafMost.getValue());      // linh
```

Đối với DN có RDN nhiều thuộc tính như `cn=Linh+uid=linh,...`, một `Rdn` có thể chứa **nhiều attribute type/value**; không được coi dấu `+` chưa escape luôn là một phần giá trị của `cn`.

## 3. Lỗi 1: base DN bị lặp

### 3.1. Cách lỗi hình thành

Spring Boot cấu hình:

```yaml
spring:
  ldap:
    urls: ldaps://ldap.example.org:636
    base: dc=example,dc=org
    username: ${LDAP_BIND_DN}
    password: ${LDAP_BIND_PASSWORD}
```

Khi `ContextSource` đã có `base=dc=example,dc=org`, những DN trong các thao tác thông thường của `LdapTemplate` sẽ được hiểu **tương đối với base này**. Ví dụ đúng:

```java
import javax.naming.Name;
import org.springframework.ldap.support.LdapNameBuilder;

Name relativeDn = LdapNameBuilder.newInstance("ou=people")
    .add("uid", "linh")
    .build();

ldapTemplate.lookupContext(relativeDn);
```

DN này biểu diễn `uid=linh,ou=people`; kết hợp với base của `ContextSource` để trỏ đến entry đầy đủ `uid=linh,ou=people,dc=example,dc=org`.

Đoạn code sau thường gây lỗi:

```java
// SAI nếu ldapTemplate dùng ContextSource có base=dc=example,dc=org:
ldapTemplate.lookupContext(
    "uid=linh,ou=people,dc=example,dc=org"
);
```

Khi base bị cộng thêm một lần nữa, server có thể nhận yêu cầu ở vị trí tương đương:

```text
uid=linh,ou=people,dc=example,dc=org,dc=example,dc=org
                                     ^^^^^^^^^^^^^^^^^^
                                     base bị lặp
```

Do entry không ở nhánh này, kết quả thường là `NameNotFoundException` hoặc tìm kiếm rỗng, tùy thao tác và cách provider xử lý. **Không nên sửa bằng cách tự tạo nhánh trùng**; cần xác định thao tác nào đã thêm base.

### 3.2. Ba nơi thường vô tình thêm base

| Nơi cấu hình/viết code | Ví dụ gây lỗi | Cách dùng khi base kết nối đã là `dc=example,dc=org` |
| --- | --- | --- |
| `spring.ldap.base` | Đúng là `dc=example,dc=org`, nhưng caller lại truyền full DN. | Caller truyền `uid=linh,ou=people`. |
| `@Entry(base = ...)` trong ODM | `@Entry(base="ou=people,dc=example,dc=org")`. | `@Entry(base="ou=people")`. |
| `LdapQueryBuilder.base(...)` | `query().base("ou=people,dc=example,dc=org")`. | `query().base("ou=people")`. |
| `LdapNameBuilder` trong service | `newInstance("dc=example,dc=org").add("ou","people")...` rồi truyền thẳng vào `LdapTemplate`. | `newInstance("ou=people").add("uid", uid)`. |

Tài liệu Spring LDAP có những ví dụ xây **full DN** bằng `LdapNameBuilder.newInstance(BASE_DN)`. Những ví dụ đó đúng khi ứng dụng **cần giá trị DN đầy đủ** (chẳng hạn thuộc tính `member` của một nhóm), hoặc khi `ContextSource` chưa thiết lập base tương ứng. Không nên bê nguyên DN đầy đủ vào lời gọi `LdapTemplate` trong một ứng dụng đã cấu hình base DN.

### 3.3. Khi nào phải dùng full DN?

Một số thuộc tính LDAP chứa **DN làm dữ liệu**, chẳng hạn `member` của `groupOfNames`. Trong trường hợp đó, giá trị thuộc tính phải là DN đầy đủ theo schema/khả năng directory:

```java
import javax.naming.Name;
import org.springframework.ldap.support.LdapNameBuilder;

// Dùng cho thao tác lookup (tương đối với ContextSource base):
Name lookupDn = LdapNameBuilder.newInstance("ou=people")
    .add("uid", "linh")
    .build();

// Dùng làm GIÁ TRỊ thuộc tính member (full DN):
Name memberDn = LdapNameBuilder.newInstance("dc=example,dc=org")
    .add("ou", "people")
    .add("uid", "linh")
    .build();
```

Phân biệt rõ **DN làm đối số vị trí thao tác** và **DN làm giá trị một attribute**. Cách chọn phụ thuộc loại API và contract mà server/attribute yêu cầu.

### 3.4. Chuyển full DN thành relative DN một cách có kiểm tra

Nếu nhận từ một hệ thống khác DN đầy đủ, hãy parse và kiểm tra gốc trước khi loại bỏ phần base:

```java
import javax.naming.InvalidNameException;
import javax.naming.Name;
import javax.naming.ldap.LdapName;

public final class LdapDnNormalizer {
    private LdapDnNormalizer() {}

    public static Name relativeTo(String fullDn, String baseDn)
            throws InvalidNameException {
        LdapName full = new LdapName(fullDn);
        LdapName base = new LdapName(baseDn);

        // LdapName đánh số thành phần từ root (bên phải chuỗi).
        if (!full.startsWith(base)) {
            throw new IllegalArgumentException(
                "DN nằm ngoài base được cấu hình");
        }
        return full.getSuffix(base.size());
    }
}
```

Ví dụ:

```text
fullDn = uid=linh,ou=people,dc=example,dc=org
baseDn = dc=example,dc=org
result = uid=linh,ou=people
```

Giải pháp này tránh xóa đoạn chuỗi theo cách `fullDn.replace(baseDn, "")`, vốn có thể xóa nhầm, làm rơi dấu phẩy hoặc xử lý sai dấu escape. **Quan trọng:** từ chối DN nằm ngoài base cho phép; không tự lấy phần đuôi mơ hồ rồi gửi đến directory.

## 4. Lỗi 2: RDN sai kiểu hoặc sai thứ tự

### 4.1. RDN là thành phần định danh, không phải nhãn tùy ý

Giả sử entry thật có DN:

```text
uid=linh,ou=people,dc=example,dc=org
```

Các DN dưới đây có thể **đúng cú pháp** nhưng trỏ đến **entry khác**:

| DN được xây | Vấn đề |
| --- | --- |
| `cn=Linh Nguyen,ou=people,dc=example,dc=org` | Dùng `cn` làm RDN trong khi entry hiện có được đặt tên bằng `uid`. |
| `ou=people,uid=linh,dc=example,dc=org` | Đảo thứ tự cha và con; cấu trúc nhánh khác. |
| `uid=linh,ou=groups,dc=example,dc=org` | Đúng RDN nhưng sai nhánh. |
| `uid=linh,dc=example,dc=org` | Thiếu OU chứa entry. |
| `uid=LINH,ou=people,dc=example,dc=org` | Có thể được coi tương đương hay khác tùy matching rule của attribute/server; không tùy tiện suy luận. |

Không thể sửa mọi lỗi này bằng cách “escape thêm” vì về mặt cú pháp nhiều DN trong bảng đã hợp lệ. Cần kiểm tra **DN entry thật, schema và quy tắc định danh**.

### 4.2. Xây RDN bằng API có cấu trúc

`LdapNameBuilder` của Spring LDAP thêm thành phần mới vào **bên trái chuỗi hiển thị**:

```java
import javax.naming.Name;
import org.springframework.ldap.support.LdapNameBuilder;

Name dn = LdapNameBuilder.newInstance("dc=example,dc=org")
    .add("ou", "people")
    .add("uid", "linh")
    .build();

// uid=linh,ou=people,dc=example,dc=org
System.out.println(dn);
```

Nếu viết ngược:

```java
// SAI về vị trí OU/UID trong ví dụ người dùng:
Name wrong = LdapNameBuilder.newInstance("dc=example,dc=org")
    .add("uid", "linh")
    .add("ou", "people")
    .build();
// Kết quả: ou=people,uid=linh,dc=example,dc=org
```

Vì vậy, hãy bắt đầu từ gốc, thêm từng OU theo thứ tự từ ngoài vào trong, rồi thêm RDN entry cuối cùng. Khi gọi `LdapTemplate` với base có sẵn, bắt đầu từ OU tương đối và thêm leaf RDN, không lặp lại `dc=...`.

### 4.3. Tên RDN phải khớp với schema và dữ liệu

Một entry người dùng với các object class `person` và `inetOrgPerson` có thể chứa `uid`, `cn`, `sn`, `mail`. Tuy nhiên:

- `cn` là tên hiển thị, **không tự động** là RDN; nếu entry được tạo dưới `uid=...` thì lookup bằng `cn=...` không trỏ đến cùng entry.
- Thuộc tính xuất hiện trong RDN cần nhất quán với entry, cú pháp và schema; server có thể trả lỗi `namingViolation`, `constraintViolation` hoặc lỗi khác nếu tên không hợp lệ.
- Không đổi UID như một field thường nếu UID là một phần DN. Đổi RDN cần thao tác **Modify DN / rename**, có thể ảnh hưởng các DN được nhóm hoặc hệ thống khác tham chiếu.
- Không tự động đổi `cn` thành `uid` khi thấy lookup thất bại: phải kiểm tra quy ước đặt tên của directory thực tế.

### 4.4. Sai index trong ODM @DnAttribute

Spring LDAP ODM có thể dùng `@Entry` và `@DnAttribute` để tính DN từ field của entity:

```java
import javax.naming.Name;
import org.springframework.ldap.odm.annotations.Attribute;
import org.springframework.ldap.odm.annotations.DnAttribute;
import org.springframework.ldap.odm.annotations.Entry;
import org.springframework.ldap.odm.annotations.Id;

@Entry(
    base = "ou=people",
    objectClasses = {"top", "person", "organizationalPerson", "inetOrgPerson"}
)
public class DirectoryPerson {
    @Id
    private Name dn;

    @DnAttribute(value = "uid", index = 0)
    @Attribute(name = "uid")
    private String uid;

    @Attribute(name = "cn")
    private String commonName;

    @Attribute(name = "sn")
    private String surname;

    public DirectoryPerson() {}
    // Getters/setters cho các field cần được bổ sung trong dự án thực tế.
}
```

Khi `@Entry(base="ou=people")` và chỉ có một thành phần RDN động `uid=...`, `index=0` là vị trí thích hợp trong DN tính từ các field `@DnAttribute`.

Với DN phức tạp hơn:

```text
uid=linh,ou=engineering,dc=example,dc=org
```

thứ tự `@DnAttribute(index=...)` của **các thành phần được tính** cần theo thứ tự gốc đến lá. Theo ví dụ ODM của Spring LDAP, `ou` ở `index=0` và `uid` ở `index=1`:

```java
@DnAttribute(value = "ou", index = 0)
private String department;

@DnAttribute(value = "uid", index = 1)
private String uid;
```

Đây là **minh họa khác** với entity `@Entry(base="ou=people")` ở trên: để `department` là thành phần động, base của entity sẽ không chứa sẵn `ou=engineering`. Đừng vừa đưa OU vào `@Entry.base` vừa tính lại cùng OU qua `@DnAttribute`.

Khi kiểm tra ODM, đối chiếu `@Entry.base`, mọi `@DnAttribute`, giá trị field tại thời điểm `save()`, DN ở `@Id` và cấu trúc entry thực tế. Chỉ sửa annotation khi đã xác định đúng tầng gây lỗi.

## 5. Lỗi 3: không escape hoặc escape sai trong DN

### 5.1. Cú pháp escape DN theo RFC 4514

Giá trị RDN có thể chứa ký tự mang ý nghĩa cú pháp trong chuỗi DN. Ví dụ tên hiển thị `Doe, Jane` có dấu phẩy, nên chuỗi DN sau **không đúng với một RDN `cn` duy nhất**:

```text
cn=Doe, Jane,ou=people,dc=example,dc=org
```

Nó có thể bị parse thành các thành phần không hợp lệ. Chuỗi DN đúng có thể là:

```text
cn=Doe\, Jane,ou=people,dc=example,dc=org
```

Những ký tự cần chú ý trong giá trị RDN theo RFC 4514:

| Đầu vào | Ý nghĩa/điều kiện | Cách biểu diễn minh họa |
| --- | --- | --- |
| Dấu phẩy `,` | Phân tách các RDN. | `cn=Doe\, Jane` |
| Dấu cộng `+` | Phân tách nhiều attribute trong một RDN. | `cn=R\+D` |
| Dấu gạch chéo ngược `\` | Ký tự escape. | `cn=A\\B` |
| Dấu ngoặc kép `"` | Ký tự cần escape trong giá trị. | `cn=He said \"Hi\"` |
| Dấu chấm phẩy `;`, `<`, `>` | Ký tự cú pháp cần escape. | `cn=A\;B` |
| Dấu cách **đầu** giá trị | Phải escape. | `cn=\ Linh` |
| Dấu cách **cuối** giá trị | Phải escape. | `cn=Linh\ ` |
| Dấu `#` ở **đầu** giá trị | Phải escape để tránh hiểu là dạng hexstring. | `cn=\#Admin` |
| Ký tự NUL | Phải biểu diễn an toàn bằng escape hex. | `\00` |

Không phải mọi ký tự trong bảng đều phải escape ở **mọi vị trí**: ví dụ dấu `#` ở giữa giá trị thường không bắt buộc escape. Ký tự `=` bên trong giá trị có thể được escape; dùng thư viện dựng DN sẽ giúp tránh phải tự nhớ các quy tắc chi tiết.

### 5.2. Phân biệt escape của DN và escape của Java String

Trong **chuỗi DN thực tế**, một dấu gạch chéo ngược `\` đứng trước dấu phẩy biểu diễn dấu phẩy thuộc giá trị. Nhưng trong **Java source code**, dấu `\` cũng là ký tự escape của chuỗi Java, nên phải viết hai dấu:

```java
import javax.naming.ldap.LdapName;

// Java source chứa hai dấu \\ để tạo một dấu \ trong chuỗi DN.
LdapName dn = new LdapName(
    "cn=Doe\\, Jane,ou=people,dc=example,dc=org"
);

System.out.println(dn.getRdn(dn.size() - 1).getValue());
// Doe, Jane
```

Truyền `"cn=Doe\, Jane,..."` trực tiếp vào Java String sẽ không hợp lệ vì `\,` không phải escape sequence hợp lệ trong Java. Ngược lại, đưa sẵn dấu backslash vào **giá trị thô** rồi tiếp tục chạy một hàm escape DN sẽ có nguy cơ **double escaping** và làm giá trị thực bị đổi.

### 5.3. Dùng LdapNameBuilder thay vì tự nối chuỗi

`LdapNameBuilder.add(String, Object)` nhận **tên attribute và giá trị thô**; builder sẽ biểu diễn RDN hợp lệ:

```java
import javax.naming.Name;
import org.springframework.ldap.support.LdapNameBuilder;

String rawCn = "Doe, Jane";
Name safe = LdapNameBuilder.newInstance("ou=people")
    .add("cn", rawCn)
    .build();

System.out.println(safe);
// cn=Doe\, Jane,ou=people
```

Ví dụ cần kiểm chứng thêm:

```java
String rawUid = "a+b";
Name safeUid = LdapNameBuilder.newInstance("ou=people")
    .add("uid", rawUid)
    .build();

// RDN có một attribute uid mang giá trị "a+b",
// không phải RDN có hai attribute ghép bằng dấu +.
```

Không nên biến `rawCn` thành `"Doe\\, Jane"` **trước khi** đưa vào `add("cn", rawCn)`. Đối số `value` phải là giá trị thật chưa escape; builder chịu trách nhiệm encoding.

### 5.4. Khi nào dùng LdapName, Rdn.escapeValue?

Nếu đã nhận **một chuỗi DN hợp lệ, có cấu trúc đầy đủ** từ nguồn tin cậy, `new LdapName(dnText)` dùng để parse và xác minh cú pháp. Nếu đang có **giá trị field thô** như UID/tên người dùng, dùng `LdapNameBuilder.add("uid", value)` để tạo thành phần đúng.

JNDI còn có `javax.naming.ldap.Rdn.escapeValue(Object value)` khi cần escape đúng **một giá trị RDN**. Nhưng **không** dùng nó để escape **toàn bộ DN**, bởi thao tác đó sẽ escape luôn dấu phẩy phân tách RDN và tạo nghĩa khác.

```java
import javax.naming.ldap.Rdn;

String safeValue = Rdn.escapeValue("Doe, Jane");
// Có thể dùng để tạo MỘT thành phần RDN; ví dụ này
// minh họa ý nghĩa, còn LdapNameBuilder phù hợp hơn.
System.out.println("cn=" + safeValue);
```

### 5.5. Tránh double escape

Đối chiếu:

```text
Giá trị đầu vào thực sự:     Doe, Jane
Chuỗi DN biểu diễn đúng:     cn=Doe\, Jane
Giá trị đầu vào đã escape:   Doe\, Jane
Nếu builder escape lần nữa:  cn=Doe\\\, Jane  (giá trị khác)
```

Thông điệp chính: **dữ liệu thô đi vào builder**, còn **chuỗi DN đã encode đi vào parser**. Đừng luân phiên encode/decode bằng các phép `replace()` thủ công.

## 6. Phân biệt DN escaping với LDAP filter escaping

DN dùng quy tắc **RFC 4514**, còn filter tìm kiếm dùng **RFC 4515**. Đây là hai ngữ pháp khác nhau.

| Tình huống | Dùng API | Ví dụ |
| --- | --- | --- |
| Xây tên entry cần `lookup`/`bind` | `LdapNameBuilder` hoặc `LdapName`. | `uid=linh,ou=people` |
| Tìm entry thỏa điều kiện | `LdapQueryBuilder` hoặc parameterized filter. | `(uid=linh)` |
| Gán DN vào `member` của group | Full DN đúng schema của group. | `uid=linh,ou=people,dc=example,dc=org` |

Ví dụ input `a*b`:

- Trong **DN**, dấu `*` không mang cùng ý nghĩa ký tự đại diện như filter và có thể được biểu diễn như giá trị RDN thông thường.
- Trong **LDAP filter**, `*` có ý nghĩa wildcard khi nằm ngoài escape; để tìm đúng giá trị `a*b`, nó phải được mã hóa theo quy tắc filter, ví dụ `(uid=a\2ab)`.

Ví dụ với Spring LDAP:

```java
import static org.springframework.ldap.query.LdapQueryBuilder.query;

import javax.naming.Name;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

// DN dùng để lookup (giá trị thô):
Name dn = LdapNameBuilder.newInstance("ou=people")
    .add("uid", userInput)
    .build();

// Filter dùng để search (giá trị thô):
var ldapQuery = query()
    .base("ou=people")
    .where("uid").is(userInput);
```

`LdapQueryBuilder` xử lý escaping tham số của filter. Không viết:

```java
// Không an toàn: ký tự *, (, ), \ trong input có thể đổi nghĩa filter.
String unsafeFilter = "(uid=" + userInput + ")";

// Cũng sai mục đích: đưa toàn bộ DN hoặc filter qua cùng một
// hàm replace("\\", "\\\\") tự chế.
```

Đặc biệt, `@Query` của Spring Data LDAP và những biểu thức truy vấn động cần sử dụng cơ chế binding/escaping được framework hỗ trợ. Không đưa dữ liệu chưa tin cậy vào phần cú pháp filter, tên attribute hoặc `search base`.

## 7. Chẩn đoán theo triệu chứng

| Triệu chứng | Khả năng thường gặp | Cách xác minh |
| --- | --- | --- |
| `NameNotFoundException` khi `lookup` DN đã biết | Base trùng, OU sai, DN không tồn tại hoặc entry đã đổi DN. | So sánh DN tương đối của lời gọi với full DN kiểm tra bằng `ldapsearch`. |
| `NameNotFoundException` khi `search` | Search base thực tế không tồn tại. | Kiểm tra `spring.ldap.base` và `LdapQueryBuilder.base(...)`. |
| `InvalidNameException` | DN sai cú pháp, escape lỗi hoặc RDN không đúng cấu trúc. | Parse bằng `new LdapName(...)` hoặc kiểm tra `LdapNameBuilder`. |
| `NameAlreadyBoundException` khi tạo | DN mục tiêu đã tồn tại. | Lookup đúng DN; phân biệt trùng thật với tình huống đọc nhầm base. |
| `SchemaViolationException` / `InvalidAttributeValueException` | RDN/attribute thiếu hoặc `objectClass`/schema không phù hợp. | So sánh `uid`, `cn`, `sn` với entry và schema thực. |
| `NoPermissionException` | Account bind không được đọc/ghi đúng nhánh. | Kiểm tra ACL; không mặc định là DN sai. |
| Search trả `[]` nhưng lookup thất bại | Filter không khớp, search base khác, hoặc lookup tới DN không tồn tại. | Dùng cùng thông tin DN và một phép `ldapsearch` đối chứng. |
| Đổi UID nhưng entry “biến mất” | UID nằm trong RDN và DN cũ không còn đúng. | Kiểm tra thao tác rename/Modify DN và DN sau cập nhật. |
| Bản ghi có `cn` nhưng lookup theo `uid` không thấy | Entry đặt RDN theo `cn` hoặc thiếu nhánh trong DN. | Truy vấn entry thật để lấy DN từ server. |
| DN chứa dấu phẩy trong tên dẫn đến lỗi | Tự nối chuỗi thiếu escape. | Dùng builder, so sánh giá trị `getRdn(...).getValue()`. |

Lưu ý sự khác biệt:

```text
lookup("uid=missing,ou=people")             -> có thể NameNotFoundException
search(base="ou=people", filter="(uid=x)")   -> có thể là danh sách rỗng
search(base="ou=missing", filter="(uid=x)")  -> có thể NameNotFoundException
```

`LdapTemplate` mặc định thường coi **search base không tồn tại** là lỗi. Việc tùy chỉnh bỏ qua `NameNotFoundException` khi search có thể che giấu cấu hình DN sai; không nên bật chỉ để làm bảng kết quả trông có vẻ hợp lệ.

## 8. Quy trình kiểm tra từ server đến application

Khi DN sai, mục tiêu là xác định **tên thật mà server đang có** rồi so sánh với **tên mà application đang hỏi**.

### Bước 1 — Xác nhận entry có thật

Trên LDAP server thử nghiệm hoặc bằng tài khoản được phép đọc, sử dụng `ldapsearch`:

```bash
ldapsearch -x \
  -H "ldaps://ldap.example.org:636" \
  -D "cn=service-reader,ou=system,dc=example,dc=org" -W \
  -b "dc=example,dc=org" \
  "(uid=linh)" dn uid cn sn objectClass
```

Kết quả cần đọc đầu tiên là `dn: ...` do directory trả về. Nếu không có entry, kiểm tra filter, scope, ACL và dữ liệu seed; đừng vội kết luận code đang nhân đôi base.

Để kiểm tra chính một DN đã biết:

```bash
ldapsearch -x \
  -H "ldaps://ldap.example.org:636" \
  -D "cn=service-reader,ou=system,dc=example,dc=org" -W \
  -b "uid=linh,ou=people,dc=example,dc=org" -s base \
  "(objectClass=*)" dn uid cn sn
```

Lệnh dùng **full DN** vì `ldapsearch -b` đặt search base trực tiếp trên LDAP server; nó **khác** `LdapTemplate.lookup` đã có base của `ContextSource`. Dùng `-W` để nhập password an toàn hơn việc ghi mật khẩu trực tiếp trong command line.

### Bước 2 — Kiểm tra cấu hình base đang có hiệu lực

Phân biệt những nơi cấu hình:

```yaml
# Cấu hình đúng cho ví dụ:
spring:
  ldap:
    urls: ldaps://ldap.example.org:636
    base: dc=example,dc=org
```

Cũng cần kiểm tra profile/biến môi trường có thể override `spring.ldap.base`, cấu hình `ContextSource` tự tạo, hoặc môi trường có **nhiều directory** và `LdapTemplate` khác nhau. Nếu kết nối dùng base rỗng hoặc root khác, DN cần truyền cũng thay đổi tương ứng.

### Bước 3 — Viết ra 3 giá trị DN

Trước khi sửa code, ghi lại:

```text
1. ContextSource base:       dc=example,dc=org
2. DN truyền cho LdapTemplate: uid=linh,ou=people
3. DN đầy đủ cần có:         uid=linh,ou=people,dc=example,dc=org
```

Nếu giá trị (2) chứa thêm `dc=example,dc=org`, bạn đã tìm thấy một ứng viên lỗi lặp base. Nếu (2) thành `cn=...` thay vì `uid=...`, hãy kiểm tra RDN. Nếu giá trị (2) có dấu phẩy bên trong raw value, hãy kiểm tra escaping.

### Bước 4 — So sánh DN bằng parser thay vì văn bản

```java
import javax.naming.ldap.LdapName;

LdapName expected = new LdapName(
    "uid=linh,ou=people,dc=example,dc=org"
);
LdapName actual = new LdapName(
    actualFullDnFromTrustedDiagnostics
);

if (!expected.equals(actual)) {
    // Kiểm tra các RDN có cấu trúc sau khi parse.
    // Không log PII hoặc DN đầy đủ ở log công khai.
}
```

`LdapName.equals` so sánh theo contract của JNDI và các quy tắc của tên, tránh nhầm việc khác nhau do cách biểu diễn escape. Tuy nhiên, LDAP server có thể áp dụng matching rule hoặc alias đặc thù; so sánh ở Java **không thay thế** lookup trên directory thật.

### Bước 5 — Kiểm tra lỗi cụ thể của Spring LDAP và JNDI

Spring LDAP thường chuyển các `javax.naming.NamingException` checked của JNDI thành ngoại lệ runtime thuộc `org.springframework.ldap`. Ví dụ:

```java
try {
    ldapTemplate.lookupContext(relativeDn);
} catch (org.springframework.ldap.NameNotFoundException ex) {
    // Kiểm tra DN tương đối/base và sự tồn tại của entry.
    throw ex;
} catch (org.springframework.ldap.InvalidNameException ex) {
    // Kiểm tra cú pháp, RDN và escaping.
    throw ex;
}
```

Không import nhầm `javax.naming.NameNotFoundException` khi đang catch quanh `LdapTemplate`. Dựa vào `cause` để nhận diện exception sâu bên dưới; với lỗi schema, kiểm tra `objectClass` và các thuộc tính bắt buộc. Không biến lỗi search base không tồn tại thành “user không tồn tại” nếu đó là lỗi cấu hình.

### Bước 6 — Xác nhận lại bằng thao tác nhỏ nhất

Sau khi sửa:

1. Thử lookup một DN **đã tồn tại**, chỉ đọc một vài thuộc tính không nhạy cảm.
2. Thử tìm kiếm đúng OU với filter an toàn, xác nhận có kết quả.
3. Nếu có quyền ghi, thử `bind`/`save` một entry **thử nghiệm** với UID riêng và kiểm tra DN sinh ra.
4. Chỉ kiểm thử `rename`/`delete` trên directory test, vì thay đổi DN có thể ảnh hưởng thành viên nhóm hoặc hệ thống đồng bộ.

## 9. Ví dụ service Spring LDAP an toàn với DN tương đối

Giả sử base kết nối đã là `dc=example,dc=org`:

```java
package com.example.identity;

import javax.naming.Name;
import org.springframework.ldap.core.DirContextOperations;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;
import org.springframework.stereotype.Service;

@Service
public class DirectoryLookupService {
    private final LdapTemplate ldapTemplate;

    public DirectoryLookupService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public String commonName(String uid) {
        Name dn = LdapNameBuilder.newInstance("ou=people")
            .add("uid", uid)
            .build();

        DirContextOperations entry = ldapTemplate.lookupContext(dn);
        return entry.getStringAttribute("cn");
    }
}
```

Đoạn code không nối chuỗi `"uid=" + uid`, nên xử lý được ký tự đặc biệt của RDN theo ngữ nghĩa dữ liệu. Phương thức này là **lookup theo DN**; nếu entry không tồn tại sẽ không trả danh sách rỗng mà thường ném `NameNotFoundException`. Với ứng dụng cần tìm nhiều người theo `sn` hoặc `mail`, dùng `LdapQueryBuilder` hoặc derived repository query thay cho đoán DN.

### Tương đương với Spring Data LDAP repository

```java
import java.util.Optional;
import org.springframework.data.ldap.repository.LdapRepository;

public interface DirectoryPersonRepository
        extends LdapRepository<DirectoryPerson> {
    Optional<DirectoryPerson> findByUid(String uid);
}
```

Ở đây `DirectoryPerson` cần là entity ODM hợp lệ như ví dụ `@Entry` ở mục 4. `findByUid` là tìm theo **attribute** `uid`; không giống `findById(Name dn)` vốn nhận một DN. Khi điều tra việc `findByUid` trả rỗng, kiểm tra `@Entry.base`, `objectClass` và mapping attribute; không chỉ nhìn vào RDN.

## 10. Integration test: nhận diện base và escape sai

Unit test parse DN giúp phát hiện lỗi trước khi kết nối server; integration test phải có LDAP directory thử nghiệm thực sự để xác minh mapping và lookup.

### 10.1. Unit test Java 17 — kiểm tra DN

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import javax.naming.Name;
import javax.naming.ldap.LdapName;
import org.junit.jupiter.api.Test;
import org.springframework.ldap.support.LdapNameBuilder;

class LdapDnTest {

    @Test
    void buildsCorrectRelativeDn() throws Exception {
        Name built = LdapNameBuilder.newInstance("ou=people")
            .add("uid", "linh")
            .build();

        assertEquals(new LdapName("uid=linh,ou=people"), built);
    }

    @Test
    void escapesCommaAsPartOfRdnValue() throws Exception {
        Name built = LdapNameBuilder.newInstance("ou=people")
            .add("cn", "Doe, Jane")
            .build();

        assertEquals(
            new LdapName("cn=Doe\\, Jane,ou=people"), built
        );
        assertEquals(
            "Doe, Jane",
            ((LdapName) built).getRdn(built.size() - 1).getValue()
        );
    }

    @Test
    void recognizesBaseAndExtractsRelativeDn() throws Exception {
        Name relative = LdapDnNormalizer.relativeTo(
            "uid=linh,ou=people,dc=example,dc=org",
            "dc=example,dc=org"
        );
        assertEquals(new LdapName("uid=linh,ou=people"), relative);
    }

    @Test
    void recognizesDuplicatedBaseAsDifferentName() throws Exception {
        LdapName expected = new LdapName(
            "uid=linh,ou=people,dc=example,dc=org"
        );
        LdapName duplicate = new LdapName(
            "uid=linh,ou=people,dc=example,dc=org,dc=example,dc=org"
        );
        assertTrue(!expected.equals(duplicate));
    }
}
```

Đây là mã minh họa cho project chứa JUnit 5 và Spring LDAP. `LdapDnNormalizer` là class ở mục 3.4. Các test này **không chứng minh LDAP server có entry**, nhưng giúp xác nhận builder, cấu trúc và escape hoạt động đúng trước khi gửi request.

### 10.2. Ma trận test trên LDAP server

| Kịch bản | Chuẩn bị | Kỳ vọng |
| --- | --- | --- |
| Lookup DN tương đối đúng | `ContextSource.base=dc=example,dc=org`, có `uid=linh`. | Đọc được `cn` theo DN `uid=linh,ou=people`. |
| Truyền full DN vào context có base | Cố ý truyền thêm `dc=example,dc=org`. | Thất bại hoặc truy cập nhầm vị trí; không được coi là DN hợp lệ cho thao tác tương đối. |
| Sai loại RDN | Lookup `cn=Linh Nguyen,ou=people` thay vì `uid=linh,...`. | Không trỏ đến entry `uid=linh`. |
| Thứ tự RDN sai | Truyền `ou=people,uid=linh`. | Không truy cập cùng DN với entry chuẩn. |
| Giá trị chứa dấu phẩy | Tạo/test entry bằng builder từ `"Doe, Jane"`. | Đọc lại nguyên giá trị `Doe, Jane`, không tách RDN. |
| Giá trị có dấu `+` hoặc `\` | Dùng builder với giá trị thô. | Không biến `+` thành dấu phân tách AVA; dữ liệu được giữ đúng. |
| Filter chứa `*` | Tìm bằng `LdapQueryBuilder`. | Dấu sao được xử lý theo giá trị cần tìm, không âm thầm mở rộng wildcard. |
| Base search không tồn tại | Query dưới OU không tồn tại. | Nhận biết lỗi base, không biến thành danh sách rỗng. |
| ODM `@Entry.base` chứa base lặp | Dùng cấu hình lỗi trong project test cô lập. | Phát hiện DN bất thường, sửa mapping rồi kiểm thử lại. |
| Tài khoản thiếu quyền | Bind user chỉ đọc hoặc không có ACL truy cập nhánh. | Phân biệt lỗi quyền với lỗi cú pháp DN. |

Không chạy các kịch bản tạo/xóa/rename trên directory production. Nên dùng LDAP server test có sẵn OU, schema và ACL phù hợp; kiểm tra bằng `ldapsearch` để đối chiếu DN thật sau mỗi thao tác.

## 11. Checklist chẩn đoán nhanh

Trước khi thay đổi code, trả lời theo thứ tự:

- [ ] `spring.ldap.base` hoặc `ContextSource.setBase` thực sự đang là gì?
- [ ] DN truyền cho `LdapTemplate` đang **relative** hay **full**?
- [ ] `@Entry.base` có bao gồm lặp phần gốc của `ContextSource` không?
- [ ] `LdapQueryBuilder.base(...)` hoặc search base đang nhắm đúng OU không?
- [ ] DN thật do `ldapsearch` trả về có RDN `uid`, `cn` hay loại khác?
- [ ] Các lệnh `LdapNameBuilder.add(...)` đã đúng thứ tự root → leaf chưa?
- [ ] Nếu dùng ODM, `@DnAttribute(index=...)` có đúng với các thành phần động và `@Id` có kiểu `Name` không?
- [ ] Đầu vào được đưa **thô** vào builder hay đã bị escape trước một lần?
- [ ] Có đang dùng escape **DN** cho filter hoặc escape **filter** cho DN không?
- [ ] Có đang nhầm “lookup DN không có” với “search có 0 kết quả” không?
- [ ] Thông báo lỗi thuộc `org.springframework.ldap`, JNDI hay schema/ACL của server?
- [ ] Có integration test chứng minh DN/attribute thực tế trên directory chưa?

## 12. Bài tập thực hành

1. Với base `dc=example,dc=org`, hãy chỉ rõ DN tương đối và DN đầy đủ để lookup `uid=an` dưới `ou=people`. Viết đoạn `LdapNameBuilder` cho cả hai mục đích.
2. Một service truyền `uid=an,ou=people,dc=example,dc=org` vào `ldapTemplate.lookupContext(...)`, trong khi `ContextSource` đã có base `dc=example,dc=org`. Tìm nguyên nhân và viết lại lệnh đúng.
3. Cho DN `cn=Doe\, Jane,ou=people,dc=example,dc=org`. Phân tích số RDN, tên/giá trị RDN leaf và lý do `split(",")` là sai.
4. Hãy so sánh `uid=a+b` là **giá trị thô** với chuỗi DN `uid=a\+b,ou=people`. Vì sao chuỗi `uid=a+b,ou=people` có nghĩa khác?
5. Mô tả khác biệt giữa `(uid=a*b)` và `(uid=a\2ab)` trong LDAP filter; dùng `LdapQueryBuilder` để tìm đúng ký tự `*` trong dữ liệu.
6. Xây entity ODM cho DN dạng `uid=linh,ou=engineering,dc=example,dc=org` với `ou` và `uid` là hai thành phần động. Chỉ ra thứ tự index của `@DnAttribute` và cách chọn `@Entry.base`.
7. Viết integration test đọc cùng entry qua `LdapRepository.findByUid` và `LdapTemplate.lookupContext`. Nếu một cách trả kết quả còn cách kia thất bại, bạn kiểm tra những tham số nào trước?
8. Một hệ thống dùng thuộc tính `member` của group để chứa DN của user. Giải thích vì sao attribute `member` cần full DN nhưng đối số của `LdapTemplate.lookupContext` thường cần relative DN.

## 13. Tài liệu tham khảo

- [Spring LDAP — Configuration](https://docs.spring.io/spring-ldap/reference/configuration.html): `ContextSource`, base LDAP path và cách dùng relative DN.
- [Spring LDAP — Basic Usage](https://docs.spring.io/spring-ldap/reference/spring-ldap-basic-usage.html): xây DN bằng `LdapNameBuilder`, tìm kiếm, lookup và escaping.
- [Spring LDAP — Object-Directory Mapping](https://docs.spring.io/spring-ldap/reference/odm.html): `@Entry`, `@Id`, `@DnAttribute` và tính DN khi tạo/cập nhật entity.
- [Spring LDAP API — LdapNameBuilder](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/support/LdapNameBuilder.html): cách thêm RDN, thứ tự và kiểu giá trị.
- [Spring LDAP API — LdapTemplate](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/core/LdapTemplate.html): `lookup`, `search` và cách xử lý `NameNotFoundException`.
- [Java SE 17 — LdapName](https://docs.oracle.com/en/java/javase/17/docs/api/java.naming/javax/naming/ldap/LdapName.html) và [Rdn](https://docs.oracle.com/en/java/javase/17/docs/api/java.naming/javax/naming/ldap/Rdn.html): biểu diễn DN/RDN và API parse/escape.
- [RFC 4514 — String Representation of Distinguished Names](https://www.rfc-editor.org/rfc/rfc4514): cú pháp DN và escape theo giao thức LDAP.
- [RFC 4515 — String Representation of Search Filters](https://www.rfc-editor.org/rfc/rfc4515): quy tắc escape của LDAP search filter.
- [RFC 4511 — LDAP Protocol](https://www.rfc-editor.org/rfc/rfc4511): thao tác Search, Add, Modify DN, result code và tên LDAP.
