# Cấu trúc DN nhiều thành phần và thứ tự RDN

Trong chương **DN và Name** của **SPRING_LDAP**, Distinguished Name (DN) là kiến thức nền tảng để ứng dụng Spring LDAP định vị entry trong dịch vụ thư mục. Khi gọi `LdapTemplate.lookup()`, xây search base, tạo entry bằng `bind()` hay đổi tên bằng `rename()`, ứng dụng phải chỉ đúng vị trí entry trong cây. Muốn làm được điều đó, cần hiểu **DN gồm nhiều Relative Distinguished Name (RDN) như thế nào, chúng được sắp xếp theo thứ tự nào và Java/Spring LDAP biểu diễn thứ tự đó ra sao**.

Bài học tập trung vào cấu trúc tên. Những chủ đề khác của module như schema, filter, xác thực, TLS, pooling, xử lý lỗi và kiểm thử sẽ xuất hiện ở mức cần thiết để cho thấy tác động thực tế của việc xây DN chính xác.

**Mục tiêu học tập**

Sau bài học, bạn có thể:

1. Phân tích một DN thành các RDN, xác định entry, entry cha và gốc cây.
2. Đọc đúng thứ tự RDN trong dạng chuỗi LDAP; phân biệt RDN đơn trị với RDN đa trị.
3. Phân biệt DN đầy đủ và DN tương đối với base DN khi dùng `ContextSource`, `LdapTemplate` và ODM.
4. Tạo và phân tích DN bằng `LdapName`, `Rdn`, `LdapNameBuilder` thay vì ghép chuỗi từ dữ liệu đầu vào.
5. Nhận biết các lỗi thứ tự, dấu phân cách và escaping dễ gây truy cập sai entry.

## 1. Vì sao DN cần nhiều thành phần?

LDAP tổ chức entry trong **Directory Information Tree (DIT)**: mỗi entry nằm ở một vị trí trong cây. Một tên đơn giản như `uid=lan` có thể nhận diện entry **trong phạm vi entry cha**, nhưng chưa nói rõ entry nằm dưới nhánh nào. DN bổ sung các thành phần tổ tiên để mô tả đường đi đầy đủ đến entry đó.

Xét cây thư mục mẫu:

```text
dc=org
└── dc=example
    ├── ou=people
    │   ├── uid=lan
    │   └── uid=minh
    └── ou=groups
        └── cn=developers
```

DN đầy đủ của người dùng Lan:

```text
uid=lan,ou=people,dc=example,dc=org
```

Đọc theo chuỗi, ta gặp **entry cụ thể nhất ở bên trái**, sau đó lần lượt đến các tổ tiên và **thành phần gốc ở bên phải**. Bốn RDN tạo thành một DN gồm bốn thành phần:

| Vị trí khi đọc từ trái sang phải | RDN | Vai trò trong ví dụ |
| --- | --- | --- |
| 1 | `uid=lan` | RDN của entry cần định vị (entry lá). |
| 2 | `ou=people` | RDN của entry cha trực tiếp. |
| 3 | `dc=example` | RDN của một nhánh tổ tiên cao hơn. |
| 4 | `dc=org` | RDN của nhánh gốc đang hiển thị trong ví dụ. |

Dạng khái quát:

```text
RDN_của_entry,RDN_của_cha,RDN_của_ông_bà,...,RDN_của_gốc
```

Một DN không nhất thiết phải có `dc` hoặc `ou`: cách đặt tên thực tế phụ thuộc cấu trúc cây và schema của máy chủ LDAP. Ví dụ, `cn=...` cũng có thể là RDN của entry, và một cây có thể được tổ chức theo nhánh `o=...` hoặc những naming context khác.

## 2. Phân biệt RDN, DN, attribute và naming context

**RDN (Relative Distinguished Name)** phân biệt một entry với các entry cùng cấp dưới một entry cha. RDN phổ biến gồm một *attribute type* và một *attribute value*:

```text
uid=lan
└┬┘ └┬┘
type value
```

**DN (Distinguished Name)** là chuỗi các RDN dẫn tới vị trí entry trong DIT, ví dụ:

```text
uid=lan,ou=people,dc=example,dc=org
```

**Attribute** là dữ liệu được lưu trong entry, chẳng hạn `uid`, `cn`, `sn`, `mail`. RDN dùng một hoặc nhiều cặp type/value để đặt tên entry; tuy nhiên không nên coi DN và tập attribute của entry là cùng một thứ. DN thể hiện vị trí; attribute còn được dùng để tìm kiếm, mô tả đối tượng và áp dụng schema.

**Naming context** là một nhánh mà máy chủ LDAP quản lý và có thể công bố làm điểm bắt đầu của cây dữ liệu. Trong hệ thống minh họa, `dc=example,dc=org` có thể là naming context hoặc base DN ứng dụng đã cấu hình. Bản thân `dc=org` chỉ là một thành phần trong DN; không nên suy từ chuỗi rằng nó là gốc toàn bộ máy chủ.

Hai DN sau **khác nhau** dù có cùng RDN lá `uid=lan`:

```text
uid=lan,ou=people,dc=example,dc=org
uid=lan,ou=contractors,dc=example,dc=org
```

Vì vậy:

- Không dùng riêng `uid=lan` như một địa chỉ toàn cục nếu hệ thống không có quy tắc định danh bảo đảm tính duy nhất trên toàn phạm vi.
- Cùng một giá trị thuộc tính có thể xuất hiện ở nhiều entry; DN dùng cấu trúc cây để phân biệt vị trí.
- DN có thể thay đổi khi entry được đổi RDN hoặc chuyển sang nhánh cha khác. Nếu nghiệp vụ cần một định danh bất biến, phải xem xét thuộc tính định danh ổn định do directory server cung cấp.

## 3. Quy tắc thứ tự RDN: từ entry về gốc

Quy tắc quan trọng nhất khi **viết và đọc chuỗi DN theo RFC 4514** là:

> **RDN ở bên trái là RDN của entry được định vị; các RDN bên phải lần lượt mô tả entry cha, ông bà và những tổ tiên cao hơn.**

Ví dụ:

```text
cn=api-admin,ou=teams,ou=engineering,dc=example,dc=org
   │            │          │              │         │
   │            │          │              └─────────┴── nhánh domain
   │            │          └─────────────────────────── nhánh engineering
   │            └────────────────────────────────────── nhánh teams
   └─────────────────────────────────────────────────── entry api-admin
```

Khi bỏ **RDN ở đầu chuỗi** khỏi một DN nhiều thành phần, ta thu được DN của cha trực tiếp:

| Entry | DN |
| --- | --- |
| Entry cần định vị | `cn=api-admin,ou=teams,ou=engineering,dc=example,dc=org` |
| Cha | `ou=teams,ou=engineering,dc=example,dc=org` |
| Ông/bà | `ou=engineering,dc=example,dc=org` |
| Nhánh cao hơn | `dc=example,dc=org` |

Nếu đổi thứ tự các RDN, ý nghĩa đường dẫn thay đổi. Ví dụ:

```text
# Có thể đúng nếu cây có OU teams nằm dưới engineering:
cn=api-admin,ou=teams,ou=engineering,dc=example,dc=org

# Mô tả một vị trí khác: engineering nằm dưới teams:
cn=api-admin,ou=engineering,ou=teams,dc=example,dc=org
```

Hai DN trên **không hoán đổi được**. Việc một chuỗi DN có cú pháp hợp lệ cũng không bảo đảm entry tương ứng tồn tại trên máy chủ.

Để đọc một DN nhiều cấp chính xác, hãy xác định RDN đầu tiên, rồi từng RDN cha theo thứ tự. Đây cũng là cách kiểm tra nhanh lỗi khi `lookup()` báo không tìm thấy entry dù tên người dùng có vẻ đúng.

## 4. Các ký hiệu trong cú pháp DN

Ở dạng chuỗi thông dụng, DN có các dấu phân cách với vai trò khác nhau:

| Ký hiệu | Ý nghĩa khi không được escape | Ví dụ |
| --- | --- | --- |
| `=` | Phân tách attribute type và attribute value trong một cặp type/value. | `uid=lan` |
| `,` | Phân tách hai RDN liên tiếp trong một DN. | `uid=lan,ou=people` |
| `+` | Phân tách nhiều cặp type/value cùng thuộc **một RDN**. | `cn=Lan+uid=lan` |
| `\` | Bắt đầu cách biểu diễn escape trong chuỗi DN. | `cn=Tran\, Lan` |

Các dấu `,`, `+` hoặc `=` xuất hiện trong **giá trị** phải được biểu diễn theo đúng quy tắc escaping nếu có thể bị hiểu là ký hiệu cú pháp.

Ví dụ, tên hiển thị thực tế là **Tran, Lan**:

```text
cn=Tran\, Lan,ou=people,dc=example,dc=org
```

Ở đây, `\,` là dấu phẩy thuộc giá trị `cn`, còn hai dấu phẩy còn lại phân tách các RDN. Nếu dùng `String.split(",")` để phân tích DN, chuỗi trên sẽ bị cắt sai. Tương tự, tên có dấu cộng cần phân biệt **dấu cộng thuộc giá trị** với dấu cộng ngăn các thành phần của RDN đa trị.

Các quy tắc escaping khác cũng có thể áp dụng cho dấu `\`, dấu `"`, dấu `<`, `>`, `;`, dấu `#` ở đầu giá trị, khoảng trắng đầu/cuối giá trị và những biểu diễn byte. Khi làm việc với DN thực tế, **dùng bộ parser/builder chuẩn** thay vì tự viết thuật toán tách, ghép hoặc escape.

## 5. RDN đơn trị và RDN đa trị

Một **RDN đơn trị** chứa một cặp attribute type/value:

```text
uid=lan
```

Một **RDN đa trị** (multi-valued RDN) chứa từ hai cặp trở lên và dùng dấu cộng để nối các cặp đó:

```text
cn=Lan+uid=lan
```

Cả chuỗi `cn=Lan+uid=lan` là **một RDN duy nhất**, không phải hai tầng trong cây thư mục. Ví dụ DN:

```text
cn=Lan+uid=lan,ou=people,dc=example,dc=org
```

DN này có **bốn RDN**, trong đó RDN đầu có hai cặp type/value. So sánh:

```text
# Một RDN đa trị ở vị trí entry lá:
cn=Lan+uid=lan,ou=people,dc=example,dc=org

# Hai RDN đơn trị ở hai tầng khác nhau:
cn=Lan,uid=lan,ou=people,dc=example,dc=org
```

Dòng thứ hai có **năm RDN** và mô tả một entry `cn=Lan` nằm dưới entry cha `uid=lan`. Hai cách viết có ý nghĩa khác nhau hoàn toàn.

### Thứ tự các cặp trong một RDN đa trị

Trong một RDN đa trị, các cặp thuộc tính–giá trị tạo thành một tập trong cùng RDN; việc đổi chỗ các cặp khi viết ra **không làm đổi ý nghĩa thứ bậc của DN**:

```text
cn=Lan+uid=lan,ou=people,dc=example,dc=org
uid=lan+cn=Lan,ou=people,dc=example,dc=org
```

Đây là hai cách biểu diễn cùng một RDN đa trị theo mô hình tên LDAP. Tuy nhiên, khi ứng dụng so sánh DN hoặc tên thuộc tính trong dữ liệu thực, cần dùng cách phân tích/so sánh phù hợp với LDAP và matching rules của máy chủ; không dùng so sánh chuỗi thô như một phép kiểm tra tương đương DN đáng tin cậy.

**Phân biệt hai loại thứ tự:**

- **Thứ tự giữa các RDN:** Có ý nghĩa quyết định đường đi trong cây; đổi chỗ thường tạo DN khác.
- **Thứ tự các cặp type/value bên trong cùng RDN đa trị:** Không biểu diễn cấp cha/con và không làm thay đổi vị trí thứ bậc.

## 6. DN được lưu và hiển thị như thế nào trong Java JNDI?

Spring LDAP sử dụng các kiểu tên từ JNDI, đặc biệt là `javax.naming.Name`, `javax.naming.ldap.LdapName` và `javax.naming.ldap.Rdn`. Điểm dễ gây nhầm lẫn là **chuỗi DN và thứ tự index của JNDI không cùng chiều đọc**.

Xét đoạn Java sau:

```java
import javax.naming.InvalidNameException;
import javax.naming.ldap.LdapName;

public class DnOrderDemo {

    public static void main(String[] args) throws InvalidNameException {
        LdapName dn =
                new LdapName("uid=lan,ou=people,dc=example,dc=org");

        System.out.println(dn.toString());
        // uid=lan,ou=people,dc=example,dc=org

        System.out.println(dn.size());
        // 4

        System.out.println(dn.getRdn(0));
        // dc=org

        System.out.println(dn.getRdn(1));
        // dc=example

        System.out.println(dn.getRdn(2));
        // ou=people

        System.out.println(dn.getRdn(3));
        // uid=lan

        System.out.println(dn.getRdns());
        // [dc=org, dc=example, ou=people, uid=lan]
    }
}
```

**Điểm mấu chốt:** `toString()` hiển thị DN với RDN lá ở bên trái, trong khi `getRdn(0)` và phần tử đầu của `getRdns()` là RDN **xa entry nhất**, ở phía gốc. Trong JNDI, index tăng từ thành phần gốc về entry cụ thể.

| Tình huống | Thứ tự hiển thị |
| --- | --- |
| `dn.toString()` | `uid=lan,ou=people,dc=example,dc=org` |
| `dn.getRdns()` | `[dc=org, dc=example, ou=people, uid=lan]` |
| `dn.getRdn(0)` | `dc=org` |
| `dn.getRdn(dn.size() - 1)` | `uid=lan` |

Do đó, nếu cần lấy RDN của entry lá từ `LdapName`, hãy truy cập index `size() - 1`; không mặc định index `0` là RDN đầu tiên nhìn thấy trong chuỗi.

Trong `LdapName`, những thao tác như `add()`, `getPrefix()`, `getSuffix()` tuân theo quy ước chỉ số của JNDI. Khi xử lý cây bằng code, cần kiểm tra quy ước này để tránh vô tình xây nhầm nhánh cha/con.

## 7. Tạo DN bằng `LdapNameBuilder` trong Spring LDAP

Việc nối chuỗi để tạo DN từ UID hoặc tên người dùng dễ dẫn tới lỗi escape hoặc lỗi thứ tự. Spring LDAP cung cấp `LdapNameBuilder` để xây tên từng thành phần.

Ví dụ tạo **DN đầy đủ**:

```java
import javax.naming.Name;
import org.springframework.ldap.support.LdapNameBuilder;

public class DnBuilderDemo {

    public static Name fullPersonDn(String uid) {
        return LdapNameBuilder
                .newInstance("dc=example,dc=org")
                .add("ou", "people")
                .add("uid", uid)
                .build();
    }

    public static void main(String[] args) {
        System.out.println(fullPersonDn("lan"));
        // uid=lan,ou=people,dc=example,dc=org

        System.out.println(fullPersonDn("lan,dev"));
        // uid=lan\,dev,ou=people,dc=example,dc=org
    }
}
```

Ở đây, các lệnh `add()` đưa RDN cụ thể hơn vào trước các RDN đã có khi chuyển thành chuỗi. Bắt đầu từ `dc=example,dc=org`, thêm `ou=people`, sau đó thêm `uid=lan` sẽ thu được đúng thứ tự hiển thị **entry → cha → gốc**.

Giá trị truyền cho `add("uid", uid)` được xử lý như **giá trị của RDN**, nên dấu phẩy trong UID là dữ liệu và sẽ được escape đúng cách. Đừng tự escape rồi truyền tiếp cho builder, vì có thể tạo escaping hai lần.

Với `javax.naming.ldap.LdapName` và `Rdn`, ta cũng có thể tạo hoặc đọc các thành phần của DN:

```java
import javax.naming.ldap.LdapName;
import javax.naming.ldap.Rdn;

public class DnParseDemo {

    public static void main(String[] args) throws Exception {
        String enteredName = "Tran, Lan";

        // Escape khi tự lắp chuỗi từ giá trị của một RDN:
        String safeValue = Rdn.escapeValue(enteredName);

        LdapName dn = new LdapName(
                "cn=" + safeValue + ",ou=people,dc=example,dc=org");

        System.out.println(dn);
        // cn=Tran\, Lan,ou=people,dc=example,dc=org

        Rdn leaf = dn.getRdn(dn.size() - 1);
        System.out.println(leaf.getType());  // cn
        System.out.println(leaf.getValue()); // Tran, Lan
    }
}
```

Ví dụ trên dùng `Rdn.escapeValue()` có chủ đích để minh họa escaped value. Trong ứng dụng Spring LDAP, ưu tiên builder nhận trực tiếp từng type/value; cách đó giúp giảm việc tự quản lý cú pháp khi ghép nhiều RDN.

## 8. DN đầy đủ và DN tương đối khi cấu hình `ContextSource`

Một nguồn gây lỗi phổ biến là **nhầm giữa DN tương đối với base DN đã cấu hình và DN đầy đủ**.

Giả sử ứng dụng Spring Boot cấu hình:

```yaml
spring:
  ldap:
    urls: ldaps://ldap.example.org:636
    base: dc=example,dc=org
    username: cn=app-reader,ou=service-accounts,dc=example,dc=org
    password: "configured-via-secret-store"
```

Cấu hình chỉ mang tính minh họa; khi triển khai thật, mật khẩu phải được nạp từ cơ chế quản lý bí mật thay vì ghi vào mã nguồn. TLS cần xác minh được chứng chỉ của máy chủ.

Với base `dc=example,dc=org`, các thao tác `LdapTemplate` thường dùng **DN tương đối với base**:

```text
uid=lan,ou=people
```

Máy chủ sẽ nhận diện entry đầy đủ:

```text
uid=lan,ou=people,dc=example,dc=org
```

Ví dụ Spring LDAP:

```java
import javax.naming.Name;
import javax.naming.NamingException;

import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

public class PersonDirectory {
    private final LdapTemplate ldapTemplate;

    public PersonDirectory(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public String lookupCommonName(String uid) {
        Name relativeDn = LdapNameBuilder.newInstance("ou=people")
                .add("uid", uid)
                .build();

        return ldapTemplate.lookup(
                relativeDn,
                (AttributesMapper<String>) attrs ->
                        (String) attrs.get("cn").get());
    }
}
```

Ở ví dụ này, builder trả `uid=lan,ou=people` nếu `uid` là `lan`. Khi ứng dụng làm việc thông qua `ContextSource` đã đặt base, không đưa thêm `dc=example,dc=org` vào một DN mà API đang xử lý theo quy ước **tương đối**; nếu không, ứng dụng có thể tìm sai đường dẫn vì phần base bị lặp.

Cần phân biệt ba khái niệm:

| Khái niệm | Ví dụ | Công dụng |
| --- | --- | --- |
| DN đầy đủ | `uid=lan,ou=people,dc=example,dc=org` | Đường dẫn hoàn chỉnh trong DIT. |
| Base DN của ứng dụng | `dc=example,dc=org` | Gốc logic cho các DN tương đối và truy vấn của `ContextSource`. |
| DN tương đối với base | `uid=lan,ou=people` | Đầu vào phù hợp cho các thao tác `LdapTemplate` trong cấu hình minh họa. |

DN tài khoản bind cấu hình trong `username` là một khái niệm khác: đó là DN của danh tính dùng để kết nối/xác thực tới server. Trong ví dụ, DN này nằm dưới `ou=service-accounts`; nó không phải DN của entry người dùng mà `lookup()` đang đọc.

### DN trong tìm kiếm

Khi dùng `LdapTemplate.search()` hoặc `LdapQueryBuilder`, **search base** lại là một nhánh làm điểm bắt đầu tìm kiếm, ví dụ `ou=people`. Filter như `(uid=lan)` chỉ chọn các entry theo thuộc tính; filter **không phải là DN** và không tự xác định nhánh cha của kết quả.

```text
ContextSource base: dc=example,dc=org
Search base:        ou=people
Filter:             (uid=lan)
Entry DN trả về:    uid=lan,ou=people,dc=example,dc=org
```

Trong thực tế, cách API trả về tên tuyệt đối hay tương đối có thể khác tùy overload, mapper và cấu hình. Hãy đọc hợp đồng API đang dùng trước khi lưu hoặc nối thêm base vào DN kết quả.

## 9. Thứ tự RDN ảnh hưởng gì đến việc thêm, đổi tên và di chuyển entry?

Với Spring LDAP, thứ tự DN tác động trực tiếp lên đích của các thao tác ghi:

| Thao tác | API thường dùng | Yêu cầu về tên |
| --- | --- | --- |
| Đọc entry đã biết | `lookup(dn, …)` | DN đúng vị trí, đúng base. |
| Tạo entry | `bind(…)` | DN mới xác định entry cha, RDN mới và schema hợp lệ. |
| Sửa thuộc tính | `modifyAttributes(dn, …)` | DN trỏ đúng entry sẽ được cập nhật. |
| Đổi RDN hoặc vị trí | `rename(oldDn, newDn)` | DN trước và sau biểu thị hai vị trí mong muốn. |
| Xóa entry | `unbind(dn)` | DN trỏ tới đúng entry; cần quyền và tuân thủ quy tắc xóa. |

Ví dụ một entry được đổi UID trong cùng `ou=people`:

```text
Trước:
uid=lan,ou=people,dc=example,dc=org

Sau:
uid=lan.nguyen,ou=people,dc=example,dc=org
```

Chỉ RDN đầu thay đổi; entry vẫn cùng cha. Nếu chuyển từ `ou=people` sang `ou=contractors`:

```text
Trước:
uid=lan,ou=people,dc=example,dc=org

Sau:
uid=lan,ou=contractors,dc=example,dc=org
```

RDN của entry vẫn là `uid=lan`, nhưng RDN cha khác nên DN cũng khác. Máy chủ LDAP có thể giới hạn thao tác move hoặc rename theo chính sách, quyền và hỗ trợ giao thức. Khi đổi DN, các tham chiếu chứa DN ở entry khác, chẳng hạn thành viên nhóm, cũng cần được kiểm tra.

Một ví dụ sử dụng DN tương đối với base đã cấu hình:

```java
import javax.naming.Name;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

public class DirectoryRenamer {
    private final LdapTemplate ldapTemplate;

    public DirectoryRenamer(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public void renameUid(String oldUid, String newUid) {
        Name oldDn = LdapNameBuilder.newInstance("ou=people")
                .add("uid", oldUid)
                .build();
        Name newDn = LdapNameBuilder.newInstance("ou=people")
                .add("uid", newUid)
                .build();

        ldapTemplate.rename(oldDn, newDn);
    }
}
```

Đây là thao tác **đổi tên entry trên LDAP server**, không đơn thuần đổi chuỗi trong bộ nhớ. Entry phải tồn tại, đích phải được chấp nhận và tài khoản kết nối phải có quyền cần thiết.

## 10. Những lỗi thường gặp khi đọc và tạo DN

| Lỗi | Ví dụ hoặc triệu chứng | Cách khắc phục |
| --- | --- | --- |
| Đọc ngược cấp cha/con | Hiểu `uid=lan,ou=people` là “OU people ở dưới UID lan”. | Nhớ thành phần **bên trái là entry cụ thể hơn**, bên phải là cha. |
| Đảo RDN khi ghép tên | `uid=lan,dc=example,ou=people,dc=org`. | Xác nhận đúng cây trước khi tạo DN; dùng `LdapNameBuilder`. |
| Tách chuỗi bằng dấu phẩy | `cn=Tran\, Lan,ou=people` bị tách thành nhiều phần sai. | Dùng `LdapName`/`Rdn` để phân tích. |
| Nhầm dấu cộng với cấp cây | `cn=Lan+uid=lan` bị hiểu là hai RDN. | `+` nối cặp trong **cùng một RDN**, `,` mới tách các RDN. |
| Nhầm chiều index trong JNDI | `getRdn(0)` được hiểu là `uid=lan`. | Chỉ số `0` là thành phần xa entry nhất, gần gốc nhất. |
| Gắn lặp base DN | Gửi `uid=lan,ou=people,dc=example,dc=org` vào thao tác đã có base `dc=example,dc=org` và bị gắn thêm lần nữa. | Dùng DN tương đối phù hợp với `ContextSource`. |
| Dùng UID làm địa chỉ toàn cục | `uid=lan` được giả định chỉ có một entry trong toàn cây. | Xác định nhánh cha hoặc ràng buộc duy nhất ở phạm vi nghiệp vụ. |
| Nối đầu vào chưa escape | UID chứa dấu phẩy hoặc dấu cộng làm DN bị phân tích sai. | Truyền giá trị trực tiếp cho builder; tránh ghép DN thủ công. |
| So sánh DN bằng chuỗi | Hai cách hiển thị cùng RDN đa trị bị xem là hoàn toàn khác. | Phân tích tên và dựa trên quy tắc tương đương thích hợp, không so chuỗi thô. |
| Xem DN là định danh bất biến | Đổi OU làm liên kết tham chiếu DN cũ không còn đúng. | Thiết kế quy trình rename/move và cập nhật hoặc kiểm tra tham chiếu. |

Ngoài lỗi cú pháp, `NameNotFoundException` có thể xuất hiện khi DN hợp lệ nhưng entry không tồn tại, gốc tìm kiếm không đúng hoặc tài khoản không nhìn thấy nhánh mong muốn. Lỗi quyền truy cập, schema hoặc kết nối TLS cũng cần được xử lý theo đặc tính máy chủ. Đừng kết luận mọi trường hợp “không tìm thấy” đều do thứ tự RDN.

## 11. Thực hành: tự phân tích và xây DN

Hãy giả định cây sau đã có trên máy chủ LDAP thử nghiệm:

```text
dc=example,dc=org
├── ou=people
│   └── uid=lan
├── ou=engineering
│   └── ou=teams
│       └── cn=platform
└── ou=contractors
```

**Bài tập 1 — Nhận diện thứ tự**

Với DN `cn=platform,ou=teams,ou=engineering,dc=example,dc=org`, hãy trả lời:

- DN có bao nhiêu RDN?
- RDN của entry lá là gì?
- DN của entry cha trực tiếp là gì?
- Nếu đặt `ou=engineering` trước `ou=teams` trong chuỗi thì còn cùng vị trí không?

**Bài tập 2 — Phân biệt dấu phẩy và dấu cộng**

Xác định số RDN trong từng chuỗi:

```text
A. cn=Lan\, Pham,ou=people,dc=example,dc=org
B. cn=Lan+uid=lan,ou=people,dc=example,dc=org
C. cn=Lan,uid=lan,ou=people,dc=example,dc=org
```

Giải thích vì sao A và B đều có cùng số RDN dù dùng các ký hiệu khác nhau.

**Bài tập 3 — Java JNDI**

Dùng `new LdapName("uid=lan,ou=people,dc=example,dc=org")` và dự đoán:

```java
dn.size()
dn.getRdn(0)
dn.getRdn(dn.size() - 1)
dn.toString()
```

Sau đó chạy chương trình ở mục 6 để đối chiếu.

**Bài tập 4 — Spring LDAP**

Với `spring.ldap.base=dc=example,dc=org`, xây một `Name` để `LdapTemplate.lookup()` truy cập entry `uid=lan` trong `ou=people`. Không tự ghép các giá trị đầu vào thành chuỗi DN.

### Đáp án tham khảo

1. Có **5 RDN**; RDN lá là `cn=platform`; DN cha là `ou=teams,ou=engineering,dc=example,dc=org`. Hoán đổi `ou=teams` và `ou=engineering` sẽ chỉ một đường dẫn khác.
2. A có **4 RDN**: dấu phẩy trong `Lan\, Pham` đã được escape nên thuộc giá trị `cn`. B có **4 RDN**: dấu cộng tạo một RDN đa trị. C có **5 RDN** do dấu phẩy tách thành hai RDN khác nhau.
3. `size()` trả `4`; `getRdn(0)` trả `dc=org`; `getRdn(size() - 1)` trả `uid=lan`; `toString()` hiển thị `uid=lan,ou=people,dc=example,dc=org`.
4. Dùng `LdapNameBuilder.newInstance("ou=people").add("uid", "lan").build()`, cho kết quả tương đối `uid=lan,ou=people`. `ContextSource` đã có phần base nên không cần thêm lại.

## 12. Những điểm cần ghi nhớ

- **DN là chuỗi có thứ tự các RDN**, mô tả từ entry cụ thể đến các entry tổ tiên. Đổi thứ tự RDN có thể làm DN chỉ một vị trí hoàn toàn khác.
- **RDN đa trị dùng dấu `+`**, còn dấu `,` không được escape tách các RDN. Dấu phân cách trong giá trị phải được escape.
- **JNDI lập chỉ mục RDN từ gốc về entry**, trái chiều với cách mắt đọc chuỗi DN; `getRdn(0)` không phải thành phần bên trái nhất của chuỗi.
- **Spring LDAP nên xây DN bằng `LdapNameBuilder`** (hoặc các kiểu chuẩn `LdapName`/`Rdn`), đặc biệt khi giá trị đến từ người dùng.
- **DN tương đối phải phù hợp với base DN của `ContextSource`**. Hiểu đúng vị trí entry là điều kiện để các thao tác đọc, tìm kiếm, thêm, sửa, đổi tên và xóa hoạt động chính xác và an toàn.

Tài liệu liên quan để đào sâu cú pháp và API: **RFC 4514 — LDAP: String Representation of Distinguished Names**; **RFC 4512 — LDAP: Directory Information Models**; Javadoc của `javax.naming.ldap.LdapName`, `javax.naming.ldap.Rdn` và `org.springframework.ldap.support.LdapNameBuilder`.
