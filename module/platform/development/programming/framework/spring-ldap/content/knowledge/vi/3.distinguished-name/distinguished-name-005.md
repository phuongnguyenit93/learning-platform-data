# LdapName và Rdn trong Java

Trong LDAP, một entry được xác định bằng **Distinguished Name (DN)**, chẳng hạn `uid=lan.nguyen,ou=people,dc=example,dc=org`. Khi làm việc với Spring LDAP, ứng dụng Java cần tạo, phân tích, so sánh và thay đổi các DN này. Ghép chuỗi thủ công dễ dẫn đến DN sai cú pháp, đặc biệt nếu giá trị chứa dấu phẩy, dấu cộng, dấu gạch chéo ngược hoặc khoảng trắng đặc biệt.

Java cung cấp hai lớp thuộc JNDI là **`javax.naming.ldap.LdapName`** và **`javax.naming.ldap.Rdn`** để xử lý cấu trúc tên LDAP. Spring LDAP bổ sung **`LdapNameBuilder`** để xây dựng DN thuận tiện và sử dụng kết quả với `LdapTemplate`. Đây là những công cụ về *tên và cú pháp*, không thay thế schema, xác thực, phân quyền hoặc kết nối bảo mật của máy chủ LDAP.

Sau bài này, bạn có thể:

- Phân biệt DN, RDN và các thành phần của DN trong Java.
- Tạo và phân tích `LdapName`, `Rdn` mà không phải tự xử lý ký tự phân cách.
- Hiểu thứ tự đánh chỉ số RDN trong `LdapName`, cách lấy RDN cuối (lá), tên cha và kiểm tra tên con.
- Xử lý giá trị cần escape, RDN nhiều cặp thuộc tính–giá trị và lỗi `InvalidNameException`.
- Truyền `Name` tương đối đúng cách cho `LdapTemplate` và `LdapNameBuilder`.

## 1. Nhắc lại DN và RDN

Xem một DN đầy đủ:

```text
uid=lan.nguyen,ou=people,dc=example,dc=org
│               │         │          │
│               │         │          └─ miền cấp cao
│               │         └──────────── thành phần miền
│               └────────────────────── đơn vị tổ chức
└────────────────────────────────────── entry người dùng
```

Mỗi đoạn ngăn cách bằng dấu phẩy **không bị escape** là một **Relative Distinguished Name (RDN)**. Một RDN thường có dạng `attributeType=value`:

| Thành phần | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| DN (*Distinguished Name*) | `uid=lan.nguyen,ou=people,dc=example,dc=org` | Tên đầy đủ định vị một entry trong cây thư mục |
| RDN (*Relative Distinguished Name*) | `uid=lan.nguyen` | Tên của entry tương đối với entry cha |
| Attribute type | `uid`, `ou`, `dc`, `cn` | Tên loại thuộc tính dùng để đặt tên |
| Attribute value | `lan.nguyen`, `people`, `example` | Giá trị thuộc tính trong RDN |
| Base DN | `dc=example,dc=org` | Gốc tìm kiếm hoặc ngữ cảnh thường cấu hình cho kết nối Spring LDAP |

Ví dụ trên có bốn RDN. RDN ngoài cùng bên trái là **RDN của entry đích** (`uid=lan.nguyen`), còn phần bên phải là DN của entry cha (`ou=people,dc=example,dc=org`). Trong LDAP, RDN có thể chứa **nhiều cặp thuộc tính–giá trị** nối bằng dấu `+`, nên không thể mặc định một RDN luôn chỉ có một thuộc tính.

**Lưu ý:** Dòng `dn: ...` trong LDIF diễn tả tên của entry; `dn` không phải một thuộc tính dữ liệu thông thường có thể gán giống `cn` hoặc `mail`.

## 2. Hai lớp JNDI: `LdapName` và `Rdn`

Cả hai lớp đều có sẵn trong Java SE qua package `javax.naming.ldap`:

| Lớp | Vai trò | API thường dùng |
| --- | --- | --- |
| `LdapName` | Biểu diễn cả DN gồm nhiều RDN; triển khai interface `javax.naming.Name` | `size()`, `getRdn(int)`, `getRdns()`, `add(...)`, `remove(int)`, `getPrefix(int)`, `startsWith(...)` |
| `Rdn` | Biểu diễn **một** RDN, có thể chứa một hoặc nhiều cặp thuộc tính–giá trị | `getType()`, `getValue()`, `size()`, `toAttributes()`, `escapeValue(...)`, `unescapeValue(...)` |

`LdapName` có thể thay đổi sau khi khởi tạo. Ngược lại, `Rdn` biểu diễn một thành phần tên độc lập và không có API để thay đổi thuộc tính/giá trị sau khi tạo. Vì `LdapName` có thể thay đổi, trong ứng dụng nhiều luồng nên tạo bản tên cho từng thao tác hoặc truyền một bản sao nếu cần sửa DN.

### Đọc một DN bằng Java

```java
import javax.naming.InvalidNameException;
import javax.naming.ldap.LdapName;
import javax.naming.ldap.Rdn;

public class ParseDnExample {
    public static void main(String[] args) throws InvalidNameException {
        LdapName dn = new LdapName(
                "uid=lan.nguyen,ou=people,dc=example,dc=org");

        System.out.println("DN: " + dn);
        System.out.println("Số RDN: " + dn.size());

        for (int i = 0; i < dn.size(); i++) {
            Rdn rdn = dn.getRdn(i);
            System.out.printf("RDN[%d] = %s%n", i, rdn);
        }
    }
}
```

Kết quả:

```text
DN: uid=lan.nguyen,ou=people,dc=example,dc=org
Số RDN: 4
RDN[0] = dc=org
RDN[1] = dc=example
RDN[2] = ou=people
RDN[3] = uid=lan.nguyen
```

**Điểm dễ nhầm nhất:** Chuỗi DN được viết từ **entry lá sang gốc** (trái sang phải), còn `getRdn(0)` bắt đầu từ **RDN ít đặc thù nhất**, tức gốc ở bên phải chuỗi. Vì thế:

- `dn.getRdn(0)` trả về `dc=org`, **không** phải `uid=lan.nguyen`.
- `dn.getRdn(dn.size() - 1)` trả về RDN của entry lá: `uid=lan.nguyen`.
- `dn.getRdns()` cũng trả các RDN từ gốc đến lá, theo cùng thứ tự chỉ số.

Không nên dùng `dn.toString().split(",")` để lấy thành phần: dấu phẩy có thể nằm **bên trong giá trị đã escape**, không phải dấu phân cách.

### Lấy loại thuộc tính và giá trị từ một RDN đơn

```java
LdapName dn = new LdapName(
        "uid=lan.nguyen,ou=people,dc=example,dc=org");

Rdn leaf = dn.getRdn(dn.size() - 1);

System.out.println(leaf.getType());  // uid
System.out.println(leaf.getValue()); // lan.nguyen (kiểu Object)
```

`getValue()` trả `Object` vì giá trị RDN có thể được biểu diễn ở nhiều dạng, chẳng hạn `String` hoặc `byte[]`. Với RDN chứa **một** cặp thuộc tính–giá trị, `getType()` và `getValue()` là cách đọc tiện lợi. Với RDN có nhiều cặp, xem mục 5 để tránh bỏ sót giá trị.

## 3. Tạo DN an toàn bằng `Rdn` và `LdapName`

Giả sử tên hiển thị nhập từ người dùng là `Lan, Nguyen`. Dấu phẩy thuộc **giá trị** `cn`, không phải dấu phân cách hai RDN.

**Cách nên dùng:** Tạo `Rdn` trực tiếp từ attribute type và **giá trị thô**, rồi thêm nó vào `LdapName`:

```java
import javax.naming.ldap.LdapName;
import javax.naming.ldap.Rdn;

String displayName = "Lan, Nguyen"; // giá trị thô do người dùng nhập

LdapName dn = new LdapName("ou=people,dc=example,dc=org");
dn.add(new Rdn("cn", displayName));

System.out.println(dn);
// cn=Lan\, Nguyen,ou=people,dc=example,dc=org
```

`Rdn` sẽ escape dấu phẩy khi chuyển thành chuỗi DN. Nếu tự ghép chuỗi như sau thì DN có thể bị phân tích sai hoặc bị từ chối:

```java
// Không nên: dữ liệu đầu vào trở thành một phần cú pháp DN.
String unsafeDn = "cn=" + displayName
        + ",ou=people,dc=example,dc=org";
```

Ở ví dụ này, dấu phẩy sau `Lan` sẽ bị hiểu là dấu phân cách RDN. Sử dụng `new Rdn("cn", displayName)` giúp Java tự mã hóa giá trị đúng ngữ cảnh DN.

### `Rdn.escapeValue(...)` và `Rdn.unescapeValue(...)`

Khi cần làm việc với biểu diễn chuỗi của **giá trị RDN**, có thể dùng hai phương thức tĩnh:

```java
import javax.naming.ldap.Rdn;

String rawValue = "Lan, Nguyen";

String escapedValue = Rdn.escapeValue(rawValue);
System.out.println(escapedValue); // Lan\, Nguyen

Object decodedValue = Rdn.unescapeValue(escapedValue);
System.out.println(decodedValue); // Lan, Nguyen
```

`escapeValue` nhận **giá trị**, không nhận cả chuỗi `cn=...` hoặc một DN đầy đủ. Tương tự, `unescapeValue` dùng với **phần giá trị đã escape**, không phải để giải mã toàn bộ DN.

Nếu đã dùng `new Rdn("cn", rawValue)`, **không escape `rawValue` thêm lần nữa** trước khi truyền vào constructor. Escape lặp có thể khiến dấu gạch chéo ngược trở thành dữ liệu thật và làm sai tên entry.

Một số ký tự đáng chú ý trong DN là dấu phẩy (`,`), dấu cộng (`+`), dấu ngoặc kép (`"`), dấu gạch chéo ngược (`\`), dấu `<`, `>`, dấu chấm phẩy (`;`), ký tự `#` ở đầu và khoảng trắng ở đầu/cuối giá trị. Để xử lý chúng đúng theo cú pháp DN, hãy ưu tiên tạo `Rdn` từ giá trị thô.

## 4. Thao tác cấu trúc DN: lấy tên cha, ghép tên con và kiểm tra nhánh

### Lấy RDN lá và DN cha

Trong `LdapName`, phần tử có chỉ số lớn nhất là RDN của entry lá. DN cha có thể được lấy bằng cách bỏ phần tử này:

```java
import javax.naming.Name;
import javax.naming.ldap.LdapName;
import javax.naming.ldap.Rdn;

LdapName dn = new LdapName(
        "uid=lan.nguyen,ou=people,dc=example,dc=org");

Rdn leaf = dn.getRdn(dn.size() - 1);
Name parent = dn.getPrefix(dn.size() - 1);

System.out.println(leaf);   // uid=lan.nguyen
System.out.println(parent); // ou=people,dc=example,dc=org
```

Trong API `Name` của JNDI, `getPrefix(n)` ở đây lấy **n RDN đầu theo thứ tự từ gốc đến lá**. Vì vậy, `getPrefix(size - 1)` tương ứng DN cha. Điều này có thể khác trực giác nếu chỉ nhìn chuỗi DN từ trái sang phải.

### Thêm RDN mới vào DN cha

```java
LdapName parent = new LdapName("ou=people,dc=example,dc=org");
parent.add(new Rdn("uid", "minh.tran"));

System.out.println(parent);
// uid=minh.tran,ou=people,dc=example,dc=org
```

`add(...)` thay đổi chính đối tượng `parent`. Nếu còn cần giữ DN cũ, hãy tạo đối tượng mới:

```java
LdapName parent = new LdapName("ou=people,dc=example,dc=org");

LdapName child = new LdapName(parent.toString());
child.add(new Rdn("uid", "minh.tran"));

System.out.println(parent); // ou=people,dc=example,dc=org
System.out.println(child);  // uid=minh.tran,ou=people,dc=example,dc=org
```

### Kiểm tra DN có thuộc nhánh nào không

```java
LdapName dn = new LdapName(
        "uid=lan.nguyen,ou=people,dc=example,dc=org");

LdapName base = new LdapName("dc=example,dc=org");
LdapName otherBase = new LdapName("dc=other,dc=org");

System.out.println(dn.startsWith(base));      // true
System.out.println(dn.startsWith(otherBase)); // false
```

`startsWith(base)` kiểm tra thành phần đầu của **chuỗi RDN nội bộ theo thứ tự từ gốc đến lá**. Với `LdapName`, kết quả này có nghĩa DN nằm trong nhánh có hậu tố chữ viết là `dc=example,dc=org`.

Cần phân biệt việc **so sánh cấu trúc tên** và việc **kiểm tra truy cập**: `startsWith` không xác nhận entry có thật trên server, không chứng minh tài khoản được phép đọc nhánh đó, và không thay thế ACL của LDAP.

## 5. RDN nhiều thuộc tính: `cn=Lan Nguyen+uid=lan.nguyen`

Ngoài RDN đơn, LDAP cho phép **RDN nhiều giá trị** (*multi-valued RDN*). Ví dụ:

```text
cn=Lan Nguyen+uid=lan.nguyen,ou=people,dc=example,dc=org
└──────────── cùng một RDN ───────────┘
```

Dấu `+` phân cách hai cặp thuộc tính–giá trị **trong cùng một RDN**, không tạo thêm một cấp trong cây thư mục.

```java
import javax.naming.ldap.LdapName;
import javax.naming.ldap.Rdn;

LdapName dn = new LdapName(
        "cn=Lan Nguyen+uid=lan.nguyen,ou=people,dc=example,dc=org");

Rdn leaf = dn.getRdn(dn.size() - 1);

System.out.println(dn.size());   // 4 RDN
System.out.println(leaf.size()); // 2 cặp thuộc tính–giá trị
```

Khi `leaf.size() > 1`, `getType()` và `getValue()` chỉ cho bạn **một** cặp; chúng không phải API để liệt kê tất cả thành phần. Dùng `Rdn.toAttributes()`:

```java
import javax.naming.NamingEnumeration;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;
import javax.naming.ldap.Rdn;

Rdn rdn = new Rdn("cn=Lan Nguyen+uid=lan.nguyen");
Attributes attributes = rdn.toAttributes();

NamingEnumeration<? extends Attribute> all = attributes.getAll();
try {
    while (all.hasMore()) {
        Attribute attribute = all.next();
        System.out.println(attribute.getID() + " = " + attribute.get());
    }
} finally {
    all.close();
}
```

Thứ tự hiển thị các cặp trong RDN có thể được chuẩn hóa; mã ứng dụng không nên phụ thuộc vào việc `cn` hay `uid` đứng trước trong chuỗi. Cũng cần phân biệt **RDN nhiều thuộc tính** với **một thuộc tính nhiều giá trị** trong entry: đó là hai khái niệm khác nhau.

## 6. Phân tích và so sánh tên: điều Java kiểm tra và điều server kiểm tra

`LdapName` và `Rdn` xử lý **cú pháp và cấu trúc** DN. Chúng không truy cập LDAP server khi parse tên:

```java
import javax.naming.InvalidNameException;
import javax.naming.ldap.LdapName;

try {
    LdapName parsed = new LdapName(
            "uid=lan.nguyen,ou=people,dc=example,dc=org");
    System.out.println("DN đúng cú pháp: " + parsed);
} catch (InvalidNameException ex) {
    System.err.println("DN không phân tích được: " + ex.getMessage());
}
```

Một `LdapName` được khởi tạo thành công **chỉ chứng tỏ chuỗi có thể được phân tích theo cú pháp DN**, không đảm bảo:

- Entry tồn tại trên server.
- Các attribute type (`uid`, `ou`, `dc`...) được schema LDAP của server chấp nhận tại vị trí đó.
- RDN khớp với thuộc tính và giá trị thực của entry khi tạo hoặc đổi tên.
- Người dùng đã được xác thực hoặc có quyền đọc, tạo, sửa, đổi tên entry.
- Kết nối LDAP đang dùng TLS đúng cách và có thể truy cập máy chủ.

Tương tự, `LdapName.equals(...)` là phép so sánh theo các quy tắc của lớp Java, **không phải truy vấn so khớp dựa trên matching rules hay alias resolution của LDAP server**. Tránh so sánh DN bằng `String.equals(...)` hoặc tự chuyển toàn bộ chuỗi thành chữ thường: trường hợp cần so sánh cấu trúc hãy dùng `LdapName`, còn trường hợp cần xác nhận danh tính/entry thực tế phải hỏi server theo cơ chế phù hợp.

**Không nhầm DN escaping với LDAP filter escaping.** `Rdn` và `LdapName` dành cho DN; chúng không phải công cụ escape giá trị trong filter như `(uid=...)`. Với Spring LDAP, hãy dùng filter builder của thư viện cho dữ liệu đầu vào trong câu tìm kiếm, thay vì nối chuỗi filter.

## 7. Sử dụng `LdapNameBuilder` trong Spring LDAP

Trong Spring LDAP, `LdapNameBuilder` cung cấp cách tạo `Name` theo từng thành phần, đặc biệt hữu ích khi đầu vào đến từ form hoặc service.

```java
import javax.naming.Name;
import org.springframework.ldap.support.LdapNameBuilder;

String uid = "lan.nguyen";

Name dn = LdapNameBuilder.newInstance("dc=example,dc=org")
        .add("ou", "people")
        .add("uid", uid)
        .build();

System.out.println(dn);
// uid=lan.nguyen,ou=people,dc=example,dc=org
```

Các lệnh `add("ou", ...)` và `add("uid", ...)` thêm RDN vào phía lá của DN hiện có; builder xử lý cú pháp RDN cho giá trị được truyền vào. Vì thế, hãy đưa **giá trị gốc** của `uid` vào `add` mà không escape trước.

### DN tương đối khi `ContextSource` đã có base DN

Giả sử `ContextSource` được cấu hình với base DN `dc=example,dc=org`. Trong trường hợp này, các thao tác `LdapTemplate` thường nhận **DN tương đối so với base**:

```text
Base DN trong ContextSource:  dc=example,dc=org
DN truyền cho LdapTemplate:  uid=lan.nguyen,ou=people
DN đầy đủ trên server:      uid=lan.nguyen,ou=people,dc=example,dc=org
```

Ví dụ service thêm entry `inetOrgPerson`:

```java
import javax.naming.Name;

import org.springframework.ldap.core.DirContextAdapter;
import org.springframework.ldap.core.DirContextOperations;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

public class DirectoryPersonService {
    private final LdapTemplate ldapTemplate;

    public DirectoryPersonService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public void createPerson(String uid, String cn, String sn) {
        Name relativeDn = LdapNameBuilder.newInstance("ou=people")
                .add("uid", uid)
                .build();

        DirContextAdapter entry = new DirContextAdapter(relativeDn);
        entry.setAttributeValues("objectClass", new String[] {
                "top", "person", "organizationalPerson", "inetOrgPerson"
        });

        // Thuộc tính trong RDN và các thuộc tính MUST của schema.
        entry.setAttributeValue("uid", uid);
        entry.setAttributeValue("cn", cn);
        entry.setAttributeValue("sn", sn);

        ldapTemplate.bind(entry);
    }

    public DirContextOperations findPerson(String uid) {
        Name relativeDn = LdapNameBuilder.newInstance("ou=people")
                .add("uid", uid)
                .build();

        return ldapTemplate.lookupContext(relativeDn);
    }
}
```

Mã giả định rằng:

1. Một `LdapTemplate` đã được cấu hình đúng `ContextSource` và base DN `dc=example,dc=org`.
2. Entry cha `ou=people,dc=example,dc=org` đã tồn tại và tài khoản kết nối có quyền tạo/đọc entry.
3. Máy chủ hỗ trợ các object class đã khai báo, entry có đủ thuộc tính bắt buộc (điển hình `cn` và `sn`), và các giá trị hợp lệ theo schema.
4. Kết nối đến thư mục được bảo vệ phù hợp, ví dụ LDAPS hoặc StartTLS với kiểm tra chứng chỉ.

Nếu base DN đã nằm trong `ContextSource` mà vẫn đưa cả `dc=example,dc=org` vào `relativeDn`, một số thao tác sẽ nhắm sai DN do lặp phần base. Hãy xác định rõ giá trị đưa vào API là DN **tương đối** hay DN **đầy đủ**, dựa trên cấu hình và tài liệu của API đang sử dụng.

### Dùng `Name` khi đổi tên entry

`LdapTemplate` cũng nhận các đối tượng `Name` khi đổi tên:

```java
import javax.naming.Name;
import org.springframework.ldap.support.LdapNameBuilder;

Name oldDn = LdapNameBuilder.newInstance("ou=people")
        .add("uid", "lan.nguyen")
        .build();

Name newDn = LdapNameBuilder.newInstance("ou=people")
        .add("uid", "lan.tran")
        .build();

ldapTemplate.rename(oldDn, newDn);
```

Đoạn trên giả định `ldapTemplate` có sẵn trong service và hai DN là tương đối với cùng base. Việc đổi tên cần quyền phù hợp; các server còn có thể đặt quy tắc riêng về RDN, thuộc tính đặt tên và khả năng chuyển entry trong cây.

### Tìm theo thuộc tính cần filter, không tự xây DN khi chưa biết tên

Nếu chỉ biết `uid` và chưa biết DN của entry (người dùng có thể nằm ở nhiều `ou`), cần **tìm kiếm** thay vì giả định DN:

```java
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;

String uid = "lan.nguyen"; // giá trị nhập từ bên ngoài

LdapQuery query = LdapQueryBuilder.query()
        .base("ou=people")
        .where("uid").is(uid);
```

Sau đó truyền `query` vào một phương thức `ldapTemplate.search(...)` phù hợp với kiểu kết quả mong muốn. `LdapQueryBuilder` xây dựng điều kiện LDAP filter theo ngữ cảnh tìm kiếm. `Rdn.escapeValue(uid)` **không phải** cách chuẩn bị giá trị cho filter: cú pháp filter và cú pháp DN có các quy tắc escape khác nhau.

## 8. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `getRdn(0)` trả `dc=org` thay vì `uid=...` | Nhầm thứ tự RDN trong JNDI với thứ tự khi đọc chuỗi DN | Dùng `getRdn(size - 1)` để lấy RDN lá |
| Giá trị `cn=Lan, Nguyen` bị tách thành hai RDN | Ghép chuỗi DN từ dữ liệu thô chứa dấu phẩy | Dùng `new Rdn("cn", rawValue)` hoặc `LdapNameBuilder.add(...)` |
| DN có thêm dấu `\` hoặc không tìm thấy entry | Escape giá trị hai lần | Truyền **giá trị thô** cho constructor `Rdn` / builder |
| Lấy thông tin từ RDN có `+` nhưng mất một thuộc tính | Dùng `getType()`/`getValue()` như thể RDN chỉ có một cặp | Kiểm tra `size()` và dùng `toAttributes()` |
| `LdapTemplate` truy cập sai vị trí | Lặp base DN đã cấu hình trong `ContextSource` | Dùng tên tương đối phù hợp với base |
| Parse DN thành công nhưng thao tác bind thất bại | Lỗi schema, entry cha không tồn tại hoặc không đủ quyền | Kiểm tra `objectClass`, thuộc tính `MUST`, ACL và lỗi LDAP server |
| Giá trị trong bộ lọc tìm kiếm bị hiểu sai | Dùng escaping của RDN cho LDAP filter | Sử dụng `LdapQueryBuilder` / công cụ xây filter thích hợp |
| Mã Java báo `InvalidNameException` | Chuỗi DN có ký tự đặc biệt chưa escape hoặc cú pháp RDN không hợp lệ | Dùng `Rdn` để xây DN; bắt và xử lý lỗi khi parse chuỗi từ bên ngoài |

Khi ghi log, có thể lưu loại thao tác, vị trí tương đối và mã lỗi để hỗ trợ xử lý, nhưng cần tránh ghi giá trị nhạy cảm như mật khẩu hoặc DN chứa thông tin cá nhân không cần thiết. Ngoài ra, lỗi kết nối, xác thực và quyền truy cập không thể được khắc phục chỉ bằng thay đổi `LdapName`.

## 9. Thực hành: kiểm tra cách Java biểu diễn tên

Đoạn mã Java sau không cần kết nối LDAP server; chỉ dùng JNDI trong Java SE để kiểm tra cú pháp và thứ tự RDN.

```java
import javax.naming.Name;
import javax.naming.ldap.LdapName;
import javax.naming.ldap.Rdn;

public class LdapNamePractice {
    public static void main(String[] args) throws Exception {
        String userInput = "Lan, Nguyen";

        // 1. Tạo tên từ giá trị chứa dấu phẩy.
        LdapName dn = new LdapName("ou=people,dc=example,dc=org");
        dn.add(new Rdn("cn", userInput));

        // 2. In tên và số thành phần.
        System.out.println(dn);
        System.out.println("RDN count = " + dn.size());

        // 3. Đọc RDN lá và lấy DN cha.
        Rdn leaf = dn.getRdn(dn.size() - 1);
        Name parent = dn.getPrefix(dn.size() - 1);
        System.out.println("Leaf attribute = " + leaf.getType());
        System.out.println("Leaf value = " + leaf.getValue());
        System.out.println("Parent = " + parent);

        // 4. Kiểm tra nhánh.
        System.out.println("Under example.org = " + dn.startsWith(
                new LdapName("dc=example,dc=org")));
    }
}
```

Những điều cần quan sát:

- Dấu phẩy trong `Lan, Nguyen` được escape trong chuỗi DN in ra, nhưng `leaf.getValue()` vẫn trả giá trị gốc.
- `dn.size()` là `4`, vì dấu phẩy thuộc dữ liệu không tạo thêm RDN.
- DN cha là `ou=people,dc=example,dc=org`.
- Phép `startsWith` với `dc=example,dc=org` trả `true` theo thứ tự RDN của JNDI.

Nếu muốn thử trường hợp RDN có nhiều thuộc tính, thay câu lệnh thêm RDN bằng:

```java
dn.add(new Rdn("cn=Lan Nguyen+uid=lan.nguyen"));
```

Khi đó `dn.size()` vẫn là `4` nhưng `leaf.size()` sẽ là `2`. Hãy dùng `toAttributes()` để liệt kê đủ hai thành phần.

## 10. Câu hỏi tự kiểm tra

**Câu 1.** Với tên `cn=Hoa,ou=engineering,dc=example,dc=org`, `getRdn(0)` và `getRdn(3)` trả về gì?

**Đáp án:** `getRdn(0)` là `dc=org`; `getRdn(3)` là `cn=Hoa`. JNDI đánh chỉ số từ gốc đến lá.

**Câu 2.** Người dùng nhập `Mai+Lan` làm giá trị `cn`. Vì sao không nên viết `"cn=" + input + ",ou=people,..."`?

**Đáp án:** Dấu `+` là ký tự cú pháp để phân cách các cặp trong một RDN. Nếu ghép trực tiếp, chuỗi có thể bị phân tích sai. Tạo `new Rdn("cn", input)` hoặc dùng builder với giá trị thô để escape đúng.

**Câu 3.** DN `cn=An+uid=an,ou=people,dc=example,dc=org` có bao nhiêu RDN?

**Đáp án:** Bốn RDN. `cn=An+uid=an` là **một** RDN có hai cặp thuộc tính–giá trị.

**Câu 4.** `new LdapName("uid=an,ou=people,dc=example,dc=org")` chạy thành công. Điều đó có chứng minh entry đã tồn tại không?

**Đáp án:** Không. Lớp chỉ phân tích cú pháp DN; muốn biết entry tồn tại cần thao tác trên LDAP server bằng tài khoản có quyền phù hợp.

**Câu 5.** `ContextSource` có base `dc=example,dc=org`. Muốn tra cứu `uid=an,ou=people,dc=example,dc=org` bằng `LdapTemplate` thì nên truyền DN nào?

**Đáp án:** Trong cấu hình thường gặp với base đã đặt, truyền DN tương đối `uid=an,ou=people`.

## Ghi nhớ

**`LdapName` biểu diễn toàn DN, `Rdn` biểu diễn từng thành phần đặt tên.** Chuỗi LDAP viết từ lá đến gốc, nhưng `getRdn(0)` trong Java là RDN gốc. Với dữ liệu đầu vào có ký tự đặc biệt, hãy tạo RDN từ **giá trị thô**, không ghép chuỗi DN. Khi dùng Spring LDAP, `LdapNameBuilder` giúp xây `Name` theo từng thành phần; hãy luôn kết hợp với base DN của `ContextSource` và các quy tắc schema/quyền truy cập của LDAP server.
