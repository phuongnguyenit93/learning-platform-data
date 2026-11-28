# Tạo DN an toàn bằng LdapNameBuilder

Trong **SPRING_DATA_LDAP**, ứng dụng Java truy cập dịch vụ thư mục LDAP bằng Spring Data LDAP repository, mô hình ánh xạ đối tượng (ODM) và `LdapTemplate`. Mỗi entry trong directory được định danh bởi một **DN** (*Distinguished Name*), có `objectClass`, thuộc tính và các ràng buộc schema. Khi cần tra cứu, tạo, đổi tên hoặc xóa entry, ứng dụng thường phải dựng DN từ một phần cố định như `ou=people,dc=example,dc=org` và một giá trị động như tên đăng nhập.

Ví dụ cần tạo DN cho người dùng có `uid` là `lan`:

```text
uid=lan,ou=people,dc=example,dc=org
```

Vấn đề xuất hiện khi giá trị do người dùng nhập **chứa dấu phẩy, dấu cộng, dấu bằng, dấu gạch chéo ngược hoặc khoảng trắng đặc biệt**. Nếu chỉ nối chuỗi `"uid=" + uid + ",ou=people,..."`, dữ liệu có thể bị hiểu thành cú pháp DN, dẫn đến tên sai hoặc chèn một thành phần tên ngoài ý muốn. `org.springframework.ldap.support.LdapNameBuilder` giúp xây dựng DN theo cấu trúc, escape **giá trị RDN** đúng cách và tránh tự ghép chuỗi thiếu an toàn.

Sau bài này, bạn sẽ:

- Hiểu DN, RDN, thứ tự các thành phần và mối quan hệ với base DN của `ContextSource`.
- Sử dụng đúng `LdapNameBuilder.newInstance(...)`, `add(String, Object)`, `add(String)` và `build()`.
- Xây DN từ dữ liệu động mà không diễn giải dữ liệu đó thành cú pháp DN.
- Phân biệt DN escaping với LDAP filter escaping, LDAP URL encoding và việc validate dữ liệu.
- Dùng DN đã xây trong `LdapTemplate`, ODM và kiểm thử JUnit/LDAP test directory.

## 1. DN và RDN: hiểu tên trước khi tạo

LDAP tổ chức dữ liệu thành cây thông tin thư mục (*Directory Information Tree*, DIT):

```text
dc=org
└── dc=example
    ├── ou=people
    │   ├── uid=lan
    │   └── uid=binh
    └── ou=groups
        └── cn=developers
```

DN của entry Lan là:

```text
uid=lan,ou=people,dc=example,dc=org
```

Các phần `uid=lan`, `ou=people`, `dc=example` và `dc=org` là **RDN** (*Relative Distinguished Name*), viết từ cụ thể nhất ở **bên trái** đến ancestor ở **bên phải** trong dạng chuỗi RFC 4514.

| Khái niệm | Ví dụ | Ý nghĩa |
|---|---|---|
| DN đầy đủ | `uid=lan,ou=people,dc=example,dc=org` | Tên entry trong LDAP namespace đã xác định |
| RDN của entry | `uid=lan` | Tên tương đối của Lan so với entry cha |
| DN của parent | `ou=people,dc=example,dc=org` | Container chứa Lan |
| DN tương đối với base `dc=example,dc=org` | `uid=lan,ou=people` | Tên dùng trong nhiều lời gọi Spring LDAP nếu base đã cấu hình |
| Giá trị thuộc tính `uid` | `lan` | Dữ liệu thuộc tính, không tự là một DN |

DN có cú pháp riêng: dấu phẩy `,` phân cách RDN; dấu cộng `+` có thể nối nhiều cặp thuộc tính/giá trị trong **cùng một RDN**. Một số RDN có thể đa trị, chẳng hạn `cn=Lan+uid=lan`. Vì vậy, không nên parse DN bằng `split(",")` hoặc `split("=")`; dữ liệu của RDN có thể chứa dấu phẩy hoặc dấu bằng đã escape.

Ví dụ LDIF cho entry:

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

**DN không phải** một thuộc tính có tên `dn` mà `AttributesMapper` luôn nhận được; trong LDAP protocol, tên entry được truyền ở trường riêng. `uid` có thể được chọn làm RDN theo quy ước của tổ chức, nhưng cũng có directory dùng `cn` hoặc một định danh khác làm RDN. `LdapNameBuilder` không tự biết entry tồn tại ở đâu: nó chỉ **xây một tên hợp lệ về cú pháp**.

## 2. Tại sao nối chuỗi DN là nguy hiểm?

Xét code:

```java
String uid = userInput;
String dn = "uid=" + uid + ",ou=people,dc=example,dc=org";
```

Với `uid="lan"`, chuỗi tình cờ đúng. Nhưng nếu `userInput` là `"lan,ou=admins"`:

```text
DN dự định: uid=[giá trị nguyên vẹn của input],ou=people,dc=example,dc=org

DN ghép chuỗi:
uid=lan,ou=admins,ou=people,dc=example,dc=org

DN được hiểu:
uid=lan
  nằm trong ou=admins
    nằm trong ou=people
      nằm trong dc=example,dc=org
```

Khi được parse theo RFC 4514, dấu phẩy do người dùng nhập đã trở thành **dấu phân cách RDN**, không còn là một phần của giá trị `uid`. Đây là một dạng **DN injection/nhầm lẫn cấu trúc tên**. Tùy DN có tồn tại và quyền của tài khoản bind, lỗi có thể dẫn đến tra cứu nhầm entry, thao tác sai mục tiêu hoặc thất bại khó chẩn đoán.

Ví dụ khác:

| Giá trị người dùng nhập | Rủi ro nếu nối chuỗi |
|---|---|
| `lan,team` | Dấu phẩy bị hiểu là ngăn cách RDN |
| `Lan+Admin` | Dấu cộng có thể bị hiểu là một phần RDN đa trị |
| `\` | Dấu escape của DN có thể khiến phần sau được phân tích khác |
| `#lan` | Dấu `#` ở đầu giá trị cần xử lý theo quy tắc RFC 4514 |
| ` Lan ` | Khoảng trắng đầu/cuối mang ý nghĩa đặc biệt trong biểu diễn DN |
| `lan=prod` | Một số parser/chế độ hiển thị có quy tắc riêng với dấu `=` |

**Không giải quyết bằng cách tự `replace(",", "\\,")` rồi nối chuỗi**. Cần tính cả ký tự đặc biệt khác, giá trị Unicode, các vị trí cần escape và trường hợp đầu vào chứa sẵn dấu `\`. Hãy để thư viện tạo **RDN từ giá trị**, sau đó thư viện mới chuyển tên thành chuỗi DN theo quy tắc.

## 3. Dựng DN bằng LdapNameBuilder

API hiện tại của Spring LDAP:

```java
import javax.naming.ldap.LdapName;
import org.springframework.ldap.support.LdapNameBuilder;

LdapName dn = LdapNameBuilder.newInstance("dc=example,dc=org")
        .add("ou", "people")
        .add("uid", "lan")
        .build();

System.out.println(dn);
// uid=lan,ou=people,dc=example,dc=org
```

**Cách đọc thứ tự:** `newInstance("dc=example,dc=org")` bắt đầu ở tên cha đã biết; `.add("ou", "people")` thêm RDN gần entry hơn; `.add("uid", "lan")` thêm RDN của entry. Mỗi lệnh `add(...)` đặt thành phần mới **về đầu chuỗi DN** khi xuất `toString()`.

```text
Builder ban đầu:    dc=example,dc=org
Thêm ou=people:     ou=people,dc=example,dc=org
Thêm uid=lan:       uid=lan,ou=people,dc=example,dc=org
```

`build()` trả về một `javax.naming.ldap.LdapName`, là một triển khai của `javax.naming.Name`. Nhiều API `LdapTemplate` nhận trực tiếp `Name` nên không cần chuyển qua `String` rồi parse lại.

### 3.1. Các overload cần phân biệt

| Phương thức | Đầu vào được hiểu là gì? | Khi nào dùng |
|---|---|---|
| `newInstance()` | Bắt đầu từ tên rỗng | Dựng từng thành phần theo thứ tự |
| `newInstance(String name)` | **Parse toàn bộ chuỗi theo cú pháp DN** | Base DN cố định, được quản lý và kiểm chứng |
| `newInstance(Name name)` | Bắt đầu từ bản sao `Name` | Từ một `LdapName` đã có cấu trúc |
| `add(String key, Object value)` | **Thêm một RDN** với attribute type và giá trị | Dùng cho giá trị động: `uid`, `cn`, `ou` |
| `add(String name)` | **Parse chuỗi name như một DN** rồi thêm | Chỉ với đoạn DN đã biết/được xác minh |
| `add(Name name)` | Ghép thêm thành phần của một `Name` đã parse | Tái sử dụng một đoạn tên có cấu trúc |
| `build()` | Hoàn tất và trả `LdapName` | Truyền vào `LdapTemplate`, so sánh/kiểm tra tên |

**Điểm an toàn trọng tâm:** `add("uid", userInput)` khác căn bản với `add("uid=" + userInput)`. Cách thứ nhất truyền dữ liệu dưới dạng **giá trị RDN**; cách thứ hai truyền một **chuỗi DN hoàn chỉnh để parser diễn giải**.

Ví dụ:

```java
String userInput = "lan,ou=admins";

LdapName safe = LdapNameBuilder.newInstance("ou=people")
        .add("uid", userInput)
        .build();

// Giá trị uid vẫn là nguyên vẹn "lan,ou=admins".
// Dấu phẩy ở giữa input được escape khi biểu diễn thành chuỗi.

LdapName unsafe = LdapNameBuilder.newInstance("ou=people")
        .add("uid=" + userInput)
        .build();

// Chuỗi add(String) bị parse như cấu trúc DN:
// có thể chèn thêm RDN "ou=admins" ngoài dự định.
```

Tên biến `unsafe` ở đây chỉ minh họa **mẫu API không nên dùng với đầu vào không tin cậy**. `add(String)` tự nó không sai nếu chuỗi truyền vào là cấu trúc DN đã được tin cậy và xác minh.

### 3.2. Xây DN hoàn toàn từ các RDN

Trong trường hợp không có sẵn chuỗi base DN:

```java
LdapName dn = LdapNameBuilder.newInstance()
        .add("dc", "org")
        .add("dc", "example")
        .add("ou", "people")
        .add("uid", "lan")
        .build();

// uid=lan,ou=people,dc=example,dc=org
```

Cần bắt đầu từ **ancestor ngoài cùng** và lần lượt tiến đến entry. Nếu làm ngược thứ tự, kết quả sẽ là một DN khác. Với base cố định trong cấu hình, `newInstance("dc=example,dc=org")` thường dễ đọc hơn; với thành phần động, dùng `add(attributeType, value)`.

## 4. Escape RDN: dữ liệu giữ nguyên, cú pháp thay đổi

Theo RFC 4514, các ký tự phải được escape khi biểu diễn thành chuỗi DN bao gồm dấu `\`, dấu ngoặc kép, dấu cộng, dấu phẩy, dấu chấm phẩy, dấu `<`/`>`, NUL; ngoài ra có quy tắc đặc biệt cho `#` và khoảng trắng ở **đầu/cuối giá trị**. Những ký tự đặc biệt được biểu diễn với dấu `\` hoặc dạng mã hex phù hợp.

Ví dụ:

```text
Giá trị uid thực tế:  lan,team
Chuỗi DN hiển thị:   uid=lan\,team,ou=people,dc=example,dc=org

Giá trị cn thực tế:   Lan+Ops
Chuỗi DN hiển thị:   cn=Lan\+Ops,ou=people,dc=example,dc=org

Giá trị cn thực tế:   #Lan
Chuỗi DN hiển thị:   cn=\#Lan,ou=people,dc=example,dc=org
```

Cách hiển thị cụ thể do `LdapName`/`Rdn` quyết định; có thể tồn tại nhiều biểu diễn escape hợp lệ. **Đừng viết test chỉ đúng khi `toString()` dùng một dạng escape chính xác** nếu mục tiêu là kiểm tra dữ liệu không đổi. Hãy parse lại và so sánh **giá trị RDN**.

```java
import javax.naming.ldap.LdapName;
import javax.naming.ldap.Rdn;
import org.springframework.ldap.support.LdapNameBuilder;

String rawUid = "lan,team";
LdapName dn = LdapNameBuilder.newInstance("ou=people")
        .add("uid", rawUid)
        .build();

Rdn leaf = dn.getRdn(dn.size() - 1);
System.out.println(leaf.getType());  // uid
System.out.println(leaf.getValue()); // lan,team
```

Trong `LdapName`, `getRdn(size - 1)` lấy thành phần **cụ thể nhất**. Thứ tự **index** của `LdapName` bắt đầu từ thành phần ít cụ thể nhất, dù chuỗi DN lại hiển thị thành phần cụ thể nhất bên trái. Đây là nguyên nhân thường gặp khiến code kiểm thử hoặc xử lý RDN lấy sai phần.

### 4.1. Không escape sẵn rồi đưa vào builder lần nữa

Sai:

```java
String alreadyEscaped = "lan\\,team";
Name wrong = LdapNameBuilder.newInstance("ou=people")
        .add("uid", alreadyEscaped)
        .build();
```

Trong Java, biến `alreadyEscaped` chứa **ký tự backslash thật** trước dấu phẩy. `add("uid", ...)` coi cả chuỗi đó là **dữ liệu literal**, nên có thể escape thêm dấu backslash. Kết quả mô tả giá trị có dấu `\` chứ không còn giá trị `lan,team` ban đầu.

Đúng:

```java
String rawUid = "lan,team";
Name right = LdapNameBuilder.newInstance("ou=people")
        .add("uid", rawUid)
        .build();
```

Quy tắc thực hành: **đầu vào thô → API có cấu trúc → đối tượng `LdapName`**. Chỉ chuyển sang chuỗi ở biên thực sự cần log, xuất LDIF, ghi cấu hình hoặc giao tiếp với API nhận String.

### 4.2. Escape không thay thế kiểm tra dữ liệu

`LdapNameBuilder` có nhiệm vụ biểu diễn **một giá trị RDN an toàn về cú pháp**, không xác minh nghiệp vụ rằng `uid` hợp lệ. Ví dụ:

- Tên đăng nhập rỗng hoặc dài bất thường.
- Ký tự điều khiển hoặc ký tự không được quy tắc đăng nhập cho phép.
- Giá trị chứa Unicode khác chuẩn hóa nhưng trông giống nhau.
- Attribute type không hợp lệ hoặc không có trong schema LDAP của server.
- DN được tạo ra nhưng entry cha không tồn tại hoặc người dùng bind không được ghi.

Vì vậy vẫn cần validate đầu vào **trước khi tạo DN**, rồi để LDAP server kiểm tra schema/ACL khi thực hiện thao tác.

## 5. Tách rõ DN tương đối với base và DN đầy đủ

Spring LDAP thường đặt một **base DN** trong `ContextSource`. Ví dụ cấu hình:

```yaml
spring:
  ldap:
    urls: ldaps://ldap.example.org:636
    base: dc=example,dc=org
    username: cn=reader,ou=service,dc=example,dc=org
    password: ${LDAP_BIND_PASSWORD}
```

Trong ví dụ này:

- `urls` là endpoint directory, **không phải DN**.
- `base` là DN đầy đủ mà ứng dụng dùng làm mốc.
- `username` là bind DN của service account trong ví dụ.
- Password được cấp qua biến môi trường hoặc secret manager, không ghi giá trị thật vào source code.

Nếu muốn đọc entry `uid=lan,ou=people,dc=example,dc=org` bằng `LdapTemplate`, hãy xây **DN tương đối với base đã cấu hình**:

```java
import javax.naming.Name;
import org.springframework.ldap.support.LdapNameBuilder;

Name relativeDn = LdapNameBuilder.newInstance("ou=people")
        .add("uid", "lan")
        .build();

// uid=lan,ou=people
```

Khi kết hợp với `ContextSource.base = dc=example,dc=org`, nó hướng tới entry đầy đủ:

```text
uid=lan,ou=people  +  dc=example,dc=org
           |
           v
uid=lan,ou=people,dc=example,dc=org
```

Nếu thay vào đó dùng:

```java
Name fullDn = LdapNameBuilder
        .newInstance("dc=example,dc=org")
        .add("ou", "people")
        .add("uid", "lan")
        .build();

// uid=lan,ou=people,dc=example,dc=org
```

thì đây là **DN đầy đủ**. Truyền nó vào một API đang mặc định diễn giải tên là **tương đối với base** có thể ghép suffix hai lần:

```text
uid=lan,ou=people,dc=example,dc=org,dc=example,dc=org
```

Không có một quy ước tương đối/đầy đủ áp dụng cho mọi thư viện, API và tầng hệ thống. Với Spring LDAP, hãy xem hợp đồng `LdapTemplate` và `ContextSource` của phiên bản đang dùng; với ODM, xem cách `@Entry(base=...)`, `@Id` và `@DnAttribute` được phối hợp.

### 5.1. Tạo helper có hợp đồng tên rõ ràng

Thay vì để mọi service tự ghép DN, xây một lớp factory tập trung:

**`PersonDnFactory.java`**

```java
package com.example.ldap;

import javax.naming.Name;
import javax.naming.ldap.LdapName;
import org.springframework.ldap.support.LdapNameBuilder;

public final class PersonDnFactory {

    private static final String DIRECTORY_BASE = "dc=example,dc=org";
    private static final String PEOPLE_OU = "ou=people";

    private PersonDnFactory() {}

    // Trả DN tương đối với ContextSource.base = dc=example,dc=org.
    public static LdapName relativeToContextBase(String uid) {
        validateUid(uid);
        return LdapNameBuilder.newInstance(PEOPLE_OU)
                .add("uid", uid)
                .build();
    }

    // Chỉ dùng khi API đích đòi một DN đầy đủ.
    public static LdapName fullDn(String uid) {
        validateUid(uid);
        return LdapNameBuilder.newInstance(DIRECTORY_BASE)
                .add("ou", "people")
                .add("uid", uid)
                .build();
    }

    private static void validateUid(String uid) {
        if (uid == null || uid.isBlank()) {
            throw new IllegalArgumentException("uid không được rỗng");
        }
        if (uid.length() > 128) {
            throw new IllegalArgumentException("uid quá dài");
        }
    }
}
```

Giới hạn 128 ký tự ở đây là **quy tắc minh họa của ứng dụng**, không phải giới hạn chung của LDAP. Với hệ thống thật cần thêm chính sách hợp lệ của login name, Unicode, tenant và schema. Nếu `uid` hợp lệ của bạn có thể chứa dấu phẩy, `LdapNameBuilder` vẫn escape đúng; đừng cấm mọi dấu câu chỉ vì chưa biết cách encode DN.

Lớp factory giảm rủi ro nhiều nơi dùng khác nhau:

```java
Name relative = PersonDnFactory.relativeToContextBase("lan");
Name absolute = PersonDnFactory.fullDn("lan");

// Hai Name có mục đích khác nhau; không hoán đổi tùy tiện.
```

## 6. Dùng DN đã tạo với LdapTemplate

Với `ContextSource.base = dc=example,dc=org` và directory có entry Lan:

**`PersonDirectoryReader.java`**

```java
package com.example.ldap;

import javax.naming.Name;
import javax.naming.directory.Attribute;
import javax.naming.directory.InvalidAttributeValueException;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class PersonDirectoryReader {
    private final LdapTemplate ldapTemplate;

    public PersonDirectoryReader(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public String findDisplayNameByUid(String uid) {
        Name relativeDn = PersonDnFactory.relativeToContextBase(uid);

        AttributesMapper<String> mapper = attrs -> {
            Attribute cn = attrs.get("cn");
            if (cn == null || cn.size() == 0) {
                throw new InvalidAttributeValueException("Entry thiếu cn");
            }
            return (String) cn.get();
        };

        return ldapTemplate.lookup(relativeDn, mapper);
    }
}
```

`ldapTemplate.lookup(relativeDn, mapper)` dùng DN để truy cập **một entry đã biết tên**, không phải tìm mọi entry có `uid` tương ứng. Nếu entry không tồn tại, server trả lỗi tên không tồn tại; Spring LDAP chuyển đổi ngoại lệ JNDI theo hợp đồng của nó. Không được biến lỗi DNS/ACL/schema thành `"không tìm thấy"` nếu chưa phân loại.

Các thao tác `bind`, `unbind`, `rename` và `modifyAttributes` cũng dùng DN phù hợp với phương thức tương ứng. Tuy nhiên:

- **DN hợp lệ không bảo đảm entry tồn tại.**
- **DN hợp lệ không bảo đảm RDN được schema cho phép.**
- **DN hợp lệ không chứng minh người dùng hiện có quyền thao tác.**
- **Đúng DN không loại bỏ race condition** giữa lúc đọc và lúc ghi.

Ví dụ, để đổi thuộc tính `mail` của một DN, không cần tự ghép chuỗi từ uid:

```java
import javax.naming.Name;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;

Name target = PersonDnFactory.relativeToContextBase("lan");

ModificationItem updateMail = new ModificationItem(
        DirContext.REPLACE_ATTRIBUTE,
        new BasicAttribute("mail", "lan.new@example.org"));

ldapTemplate.modifyAttributes(
        target, new ModificationItem[]{updateMail});
```

Đoạn code gửi một thay đổi theo DN. Nó **không** tự bảo vệ khỏi lost update khi hai writer ghi `mail` cùng lúc; nếu cần kiểm tra trạng thái cũ, hãy dùng conditional update được LDAP server cưỡng chế (ví dụ Assertion Control, nếu hỗ trợ). Ngoài ra, việc ghi phải dùng service account có ACL phù hợp, tránh dùng thông tin bind của người dùng cuối không được kiểm soát.

## 7. Khi nào nên tìm kiếm thay vì đoán DN?

Không phải directory nào cũng tổ chức người dùng ở `uid=<login>,ou=people`. Giả sử có dữ liệu:

```text
cn=Lan Nguyen,ou=employees,dc=example,dc=org
uid=lan,ou=contractors,dc=example,dc=org
uid=lan,ou=partners,dc=example,dc=net
```

Ở trường hợp này:

- `LdapNameBuilder.newInstance("ou=people").add("uid", "lan")` tạo **DN có cú pháp hợp lệ** nhưng có thể không trỏ tới entry thực.
- Tên đăng nhập `lan` có thể không duy nhất toàn bộ nhiều naming context.
- Dựng DN từ tên đăng nhập phải dựa trên **quy ước đặt tên đã được chứng minh**, không dựa vào một suy đoán.

Nếu chỉ biết thuộc tính `uid` mà chưa biết DN thực, hãy **search theo thuộc tính** với base/scope đã xác định, rồi lấy DN của entry phù hợp:

```java
import java.util.List;
import org.springframework.ldap.core.ContextMapper;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.SearchScope;
import static org.springframework.ldap.query.LdapQueryBuilder.query;

LdapQuery queryByUid = query()
        .base("ou=people")
        .searchScope(SearchScope.SUBTREE)
        .attributes("uid", "cn")
        .where("objectClass").is("inetOrgPerson")
        .and("uid").is(userInput);

ContextMapper<String> mapper = ctx -> ctx.getDn().toString();
List<String> matchingDns = ldapTemplate.search(queryByUid, mapper);
```

`ctx.getDn()` biểu diễn DN theo ngữ cảnh `ContextMapper`/`ContextSource`, **không mặc định là DN đầy đủ toàn directory**. Trước khi dùng kết quả làm identity cho API khác, hãy xác định base và endpoint liên quan.

**Tìm kiếm và dựng tên giải quyết hai việc khác nhau:**

| Đã biết gì? | Dùng gì? | Kết quả |
|---|---|---|
| Biết chắc vị trí entry, RDN có quy ước cố định | `LdapNameBuilder` + `lookup` | Một DN mục tiêu xác định |
| Chỉ biết `uid`, email hoặc tên hiển thị | `LdapQueryBuilder` + `search` | 0, 1 hoặc nhiều entry khớp |
| Muốn tạo entry theo quy tắc mới | `LdapNameBuilder` + thao tác Add | DN dự kiến; server kiểm tra tồn tại/schema/ACL |
| Muốn đổi tên/chuyển nhánh entry | Parse DN cũ + dựng DN đích có cấu trúc | Hai DN cần kiểm tra điều kiện thao tác |

Khi tìm theo giá trị từ người dùng, sử dụng `LdapQueryBuilder.where("uid").is(userInput)` để **escape LDAP filter**, không đặt giá trị đó vào một chuỗi filter nối thủ công.

## 8. DN escaping khác LDAP filter escaping

Đây là ranh giới bảo mật đặc biệt quan trọng.

| Cú pháp | Ví dụ | Ý nghĩa |
|---|---|---|
| DN | `uid=lan\,team,ou=people` | Dấu phẩy thuộc **giá trị RDN** |
| LDAP filter | `(uid=lan\2ateam)` | Dấu sao là **giá trị literal** trong filter |
| LDAP URL | `ldap://ldap.example.org/ou=people,dc=example,dc=org??sub?%28uid%3Dlan%29` | URI chứa endpoint, DN, scope và filter |

Ví dụ input `"lan*team"`:

```java
String userInput = "lan*team";

// Xây DN: '*' là một phần giá trị RDN.
Name dn = LdapNameBuilder.newInstance("ou=people")
        .add("uid", userInput)
        .build();

// Xây filter: '*' phải là dữ liệu literal, không phải wildcard.
LdapQuery filterQuery = query()
        .base("ou=people")
        .where("uid").is(userInput);
```

`LdapNameBuilder` không phải filter encoder; `LdapQueryBuilder` không phải DN encoder. Nếu lấy `dn.toString()` rồi đưa vào filter bằng phép nối `"(member=" + dn + ")"`, bạn vẫn phải xử lý **lớp filter syntax** đúng cách. Hãy tạo điều kiện bằng `where("member").is(dn.toString())` khi tìm nhóm có thành viên dạng DN và để server áp dụng matching rule thích hợp.

**Không nhầm LDAP URL với DN.** `LdapNameBuilder` không tạo URL, không chọn host, không thiết lập TLS/port hay cơ chế referral. URL phải được xử lý ở tầng kết nối hoặc công cụ LDAP URL phù hợp, gồm cả URI encoding và chính sách endpoint.

### 8.1. Không cho người dùng điều khiển tên thuộc tính hoặc base tự do

`add(String key, Object value)` bảo vệ **giá trị**, nhưng không có nghĩa bạn được tin tưởng một `key` hoặc `base DN` do client tự nhập.

Ví dụ nên tránh:

```java
// Không nên cho client tùy ý chọn attribute type và cây đích.
Name dn = LdapNameBuilder.newInstance(untrustedBaseDn)
        .add(untrustedAttributeType, userInput)
        .build();
```

Để bảo vệ namespace:

1. Cố định `attribute type` theo nghiệp vụ: `uid` cho tài khoản, `cn` cho nhóm, v.v.
2. Cố định hoặc **allowlist** các base/container mà caller được phép thao tác.
3. Gắn tenant hoặc directory identity đáng tin từ phiên đăng nhập/quyền phía server, không chỉ từ tham số client.
4. Validate giới hạn độ dài, kiểu ký tự và các quy tắc đăng nhập theo domain.
5. Để LDAP server cưỡng chế ACL và schema; không xem DN escaping là một cơ chế phân quyền.

**DN injection** và **authorization bypass** là hai vấn đề liên quan nhưng không đồng nhất. `LdapNameBuilder` giải quyết việc coi một giá trị động là **một RDN value**, còn kiểm soát ai được truy cập container/entry nào phải được thực hiện riêng.

## 9. RDN đa trị và các trường hợp phức tạp

Một RDN có thể gồm nhiều cặp thuộc tính/giá trị:

```text
cn=Lan Nguyen+uid=lan,ou=people,dc=example,dc=org
```

Lưu ý:

```java
LdapName different = LdapNameBuilder.newInstance("ou=people")
        .add("cn", "Lan Nguyen")
        .add("uid", "lan")
        .build();

// uid=lan,cn=Lan Nguyen,ou=people
// Đây là HAI RDN liên tiếp, KHÔNG phải một RDN đa trị.
```

Nếu schema/naming convention bắt buộc một **RDN đa trị**, cần tạo một `Rdn` có nhiều cặp thuộc tính/giá trị bằng API JNDI thích hợp, hoặc parse một tên đa trị đã được xác minh, rồi thêm dưới dạng `Name`. Không ghép `"+"` với giá trị động rồi hy vọng builder sẽ xử lý đúng mọi trường hợp.

Ví dụ minh họa một RDN đa trị có giá trị **cố định/đáng tin**:

```java
LdapName dn = LdapNameBuilder.newInstance(
                "ou=people,dc=example,dc=org")
        .add("cn=Lan Nguyen+uid=lan")
        .build();
```

**Chỉ dùng `add(String)` như trên khi chuỗi DN được quản lý và tin cậy.** Với dữ liệu động, tạo `Rdn` bằng cách dùng `Attributes`/API JNDI với giá trị thành phần rõ ràng, rồi kiểm tra khi serialize; không biến tên tùy ý của client thành cú pháp.

Một số server hỗ trợ DN có thuộc tính binary hoặc syntax đặc thù; `LdapNameBuilder` làm đúng nhiệm vụ tạo tên theo JNDI nhưng **không thể thay thế** việc hiểu schema, matching rule, normalization và cách server so sánh DN.

## 10. Sử dụng với Spring Data LDAP ODM

Spring Data LDAP dùng `@Entry` và `@Id` để ánh xạ entry LDAP sang Java entity. Ví dụ:

```java
import javax.naming.Name;
import org.springframework.ldap.odm.annotations.Attribute;
import org.springframework.ldap.odm.annotations.Entry;
import org.springframework.ldap.odm.annotations.Id;

@Entry(
        base = "ou=people",
        objectClasses = {
                "top", "person", "organizationalPerson", "inetOrgPerson"
        }
)
public class PersonEntry {

    @Id
    private Name dn;

    @Attribute(name = "uid")
    private String uid;

    @Attribute(name = "cn")
    private String displayName;

    @Attribute(name = "sn")
    private String surname;

    public PersonEntry() {}
    // Getter/setter phù hợp với ứng dụng.
}
```

Nếu code tạo entity mới với tên theo một quy ước nhất định, `LdapNameBuilder` giúp tạo giá trị `Name` cho trường định danh; tuy nhiên **cần tuân thủ quy ước DN của ODM và `ContextSource.base`** ở phiên bản Spring LDAP đang dùng. Đừng tự gắn toàn bộ suffix và base của `@Entry` hai lần.

Một số entity ODM dùng `@DnAttribute` để xây/tách các thành phần RDN từ thuộc tính entity. Khi kết hợp cơ chế đó với `@Id` được gán thủ công, cần kiểm tra quy tắc đồng bộ giữa tên và trường dữ liệu; không để `uid` trong attribute khác `uid` của RDN nếu schema/naming convention yêu cầu chúng khớp nhau.

**`repository.save(entity)` không phải một bộ kiểm tra quyền hay schema thay cho server**, cũng không tự ngăn lost update nếu nhiều writer chỉnh sửa cùng entry. Tạo DN an toàn chỉ là một lớp của quy trình ghi an toàn.

## 11. Kiểm thử LdapNameBuilder bằng JUnit 5

Có thể kiểm chứng phần **dựng DN và escape dữ liệu** hoàn toàn bằng unit test; không cần LDAP server để kiểm tra `LdapName` có bao nhiêu RDN hoặc giá trị RDN cuối cùng. Ví dụ:

**`PersonDnFactoryTest.java`**

```java
package com.example.ldap;

import javax.naming.ldap.LdapName;
import javax.naming.ldap.Rdn;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class PersonDnFactoryTest {

    @Test
    void createsRelativeDnWithinTrustedPeopleBranch() throws Exception {
        LdapName dn = PersonDnFactory.relativeToContextBase("lan");

        assertEquals(2, dn.size());
        assertEquals("uid=lan,ou=people", dn.toString());
        assertEquals("uid", dn.getRdn(dn.size() - 1).getType());
        assertEquals("lan", dn.getRdn(dn.size() - 1).getValue());
    }

    @Test
    void commaCannotCreateExtraRdn() throws Exception {
        String untrustedUid = "lan,ou=admins";
        LdapName dn = PersonDnFactory.relativeToContextBase(untrustedUid);

        // Chỉ 2 RDN: uid=<toàn bộ input> và ou=people.
        assertEquals(2, dn.size());
        Rdn leaf = dn.getRdn(dn.size() - 1);
        assertEquals("uid", leaf.getType());
        assertEquals(untrustedUid, leaf.getValue());
    }

    @Test
    void plusAndBackslashRemainData() throws Exception {
        String untrustedUid = "lan+ops\\test";
        LdapName dn = PersonDnFactory.relativeToContextBase(untrustedUid);

        assertEquals(2, dn.size());
        assertEquals(untrustedUid,
                dn.getRdn(dn.size() - 1).getValue());
    }

    @Test
    void fullDnHasFourRdns() throws Exception {
        LdapName dn = PersonDnFactory.fullDn("lan");
        assertEquals(4, dn.size());
        assertEquals("uid=lan,ou=people,dc=example,dc=org",
                dn.toString());
    }

    @Test
    void rejectsBlankInput() {
        assertThrows(IllegalArgumentException.class,
                () -> PersonDnFactory.relativeToContextBase(" "));
    }
}
```

Test kiểm tra **số RDN** và **giá trị RDN sau khi parse** quan trọng hơn so sánh một chuỗi escape cố định. Nếu thư viện thay đổi cách hiển thị escape nhưng DN có cùng cấu trúc và giá trị, test không nên báo lỗi giả. Với các DN chỉ chứa chữ/số đơn giản, assert `toString()` chính xác như ví dụ vẫn hữu ích để kiểm chứng thứ tự.

### 11.1. Bảng test case bổ sung

| Input động | Điều cần xác nhận |
|---|---|
| `lan` | Tạo đúng `uid=lan` ở nhánh `ou=people` |
| `lan,team` | Dấu phẩy thuộc giá trị, không phát sinh RDN thứ ba |
| `lan+ops` | Dấu cộng không làm thành RDN đa trị |
| `lan\ops` | Dấu backslash không làm parser đổi giá trị |
| `#lan` | Giá trị bắt đầu `#` được giữ nguyên sau parse/serialize |
| ` lan ` | Khoảng trắng đầu/cuối được giữ đúng hoặc bị validation nghiệp vụ từ chối |
| `Nguyễn Lan` | Unicode được giữ nguyên ở giá trị RDN |
| Chuỗi rỗng/blank | Helper từ chối trước khi tạo DN |
| Giá trị vượt giới hạn policy | Helper từ chối với lỗi rõ ràng |
| Đã escape sẵn `lan\,team` | Thể hiện rõ đó là giá trị có dấu `\`, không dùng như raw UID |
| Base DN khác | Helper chỉ tạo tên đúng với contract base đã định nghĩa |

### 11.2. Kiểm thử tích hợp trên LDAP directory mẫu

Unit test không chứng minh entry tồn tại hoặc quy tắc naming được server chấp nhận. Cần thêm integration test với LDAP test directory:

1. Tạo base `dc=example,dc=org` và container `ou=people`, nạp entry mẫu `uid=lan,ou=people,dc=example,dc=org`.
2. Cấu hình `LdapContextSource.base = dc=example,dc=org`.
3. Dùng `PersonDnFactory.relativeToContextBase("lan")` và `LdapTemplate.lookup(...)` để đọc `cn`; xác nhận đúng entry Lan.
4. Nếu schema và policy thử nghiệm cho phép, tạo entry có giá trị `uid` chứa dấu phẩy/dấu cộng; dùng builder để tạo DN và kiểm tra không truy cập nhầm một nhánh khác.
5. Dùng một DN không tồn tại để xác nhận lỗi được phân loại, không tự tạo entry ngoài ý muốn.
6. Thử tài khoản bind chỉ đọc và tài khoản có quyền ghi hạn chế; xác nhận DN hợp lệ **không vượt được ACL**.
7. Khi đổi `ContextSource.base` thành `ou=people,dc=example,dc=org`, dùng tên tương đối `uid=lan` thay vì giữ `uid=lan,ou=people`.

Không nên chạy kiểm thử tạo/xóa entry trên directory production. Cần naming context test riêng, dữ liệu giả, TLS/certificate phù hợp và quyền tối thiểu.

## 12. Những lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Cách sửa |
|---|---|---|
| `InvalidNameException` khi input có dấu phẩy | Nối chuỗi DN hoặc truyền input trực tiếp vào `add(String)` | Dùng `add("uid", rawValue)` |
| Tên trỏ sang nhánh khác sau input có `,ou=...` | Dữ liệu bị parse thành RDN mới | Coi input là giá trị, không phải cú pháp |
| DN có dấu `\\` nhiều hơn dự kiến | Đã escape trước khi đưa giá trị vào builder | Truyền raw value, để builder escape một lần |
| `lookup` báo không tìm thấy dù DN trông đúng | Truyền DN đầy đủ khi `ContextSource.base` đã gắn suffix hoặc entry thực tế nằm ở nơi khác | Kiểm tra base và DN tương đối |
| `add("uid",uid)` tạo DN nhưng server báo schema violation | Schema không cho phép RDN/thuộc tính hoặc thiếu thuộc tính bắt buộc | Đối chiếu objectClass và schema |
| Đổi `uid` nhưng `member` nhóm còn DN cũ | Rename/move không được cập nhật referential integrity | Kiểm tra server plugin/overlay, cập nhật theo nghiệp vụ |
| Không tìm được user dù có cùng login | Cấu trúc tên thực khác quy tắc builder | Search theo thuộc tính và lấy DN thực |
| Test `toString()` thất bại do dạng escape khác nhau | Kiểm tra literal thay vì cấu trúc DN | So sánh RDN type/value và số RDN |
| User được truy cập DN ngoài tenant | Base/container do client điều khiển, thiếu authorization | Allowlist base, xác định tenant phía server, LDAP ACL |
| Tìm kiếm filter bị mở rộng khi input chứa `*` | Dùng DN escaping thay filter escaping | Dùng `LdapQueryBuilder.where(...).is(value)` |

**Đừng coi mọi `NameNotFoundException` là tên sai cú pháp.** DN có thể hoàn toàn hợp lệ nhưng entry chưa tồn tại, người dùng không có quyền nhìn thấy, hoặc bạn đang kết nối đến naming context khác. Ngược lại, `InvalidNameException` báo vấn đề phân tích tên ở tầng client/provider. Cần đọc đúng exception và trạng thái server để điều tra.

## 13. Câu hỏi tự đánh giá

1. DN và RDN khác nhau thế nào? Với `uid=lan,ou=people,dc=example,dc=org`, đâu là RDN của entry?
2. Vì sao `LdapNameBuilder.add("uid", input)` an toàn hơn `.add("uid=" + input)` khi `input` đến từ người dùng?
3. Kết quả của `newInstance("dc=example,dc=org").add("ou","people").add("uid","lan")` được sắp theo thứ tự nào?
4. Vì sao `LdapName.getRdn(size-1)` thường là thành phần cụ thể nhất của DN?
5. Escape DN với dấu phẩy, dấu cộng hoặc backslash khác LDAP filter escaping ra sao?
6. Nếu `ContextSource.base` đã là `dc=example,dc=org`, cần truyền DN nào vào `LdapTemplate.lookup` để lấy Lan?
7. Vì sao một DN được builder tạo hợp lệ chưa chứng minh entry tồn tại hoặc caller có quyền?
8. Nếu user có login `lan` nhưng DN là `cn=Lan Nguyen,ou=employees,...`, tại sao không thể dùng một factory cố định `uid=<login>` để lookup?
9. Khi nào có thể dùng `add(String name)`, khi nào phải dùng `add(String key, Object value)`?
10. Để unit test chống DN injection, nên assert những tính chất nào ngoài chuỗi `toString()`?

**Ghi nhớ:** `LdapNameBuilder` xây **tên LDAP có cấu trúc**. Với dữ liệu động, dùng **`add(attributeType, rawValue)`**, không chèn chuỗi động vào **`add(String)`** hoặc `newInstance(String)` như thể đó là một DN đã được kiểm chứng. Luôn phân biệt DN tương đối với base và DN đầy đủ; kiểm soát attribute type, container/tenant, schema, ACL và quyền ghi. Escape DN đúng cách giúp giữ dữ liệu thành **giá trị RDN**, nhưng không thay thế filter escaping, authorization hay kiểm tra entry thực sự tồn tại.

### Tài liệu tham khảo

- Spring LDAP API — [`LdapNameBuilder`](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/support/LdapNameBuilder.html): `newInstance`, `add(String, Object)`, `add(String)`, `add(Name)` và `build()`.
- Spring LDAP Reference — [Basic Usage](https://docs.spring.io/spring-ldap/reference/spring-ldap-basic-usage.html): cách xây `LdapName` động và sử dụng với `LdapTemplate`.
- IETF [RFC 4514 — String Representation of Distinguished Names](https://www.rfc-editor.org/rfc/rfc4514): thứ tự RDN và escape DN.
- IETF [RFC 4512 — LDAP Directory Information Models](https://www.rfc-editor.org/rfc/rfc4512): khái niệm entry, DN, RDN và DIT.
- IETF [RFC 4515 — LDAP Search Filter String Representation](https://www.rfc-editor.org/rfc/rfc4515): quy tắc escape của filter, khác DN.
- Oracle Java SE — [`LdapName`](https://docs.oracle.com/en/java/javase/17/docs/api/java.naming/javax/naming/ldap/LdapName.html), [`Rdn`](https://docs.oracle.com/en/java/javase/17/docs/api/java.naming/javax/naming/ldap/Rdn.html).
