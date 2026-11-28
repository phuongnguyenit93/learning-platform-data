# Thao tác thành phần RDN thay vì nối chuỗi thủ công

Trong **Spring Data LDAP**, một entry không được định danh chỉ bằng `uid`, `cn` hay một khóa số như trong nhiều bảng SQL. Entry được xác định bởi **Distinguished Name (DN)**, một tên phân cấp được ghép từ các **Relative Distinguished Name (RDN)**. Ứng dụng Java thường phải tạo DN để gọi `LdapTemplate.lookup`, thêm entry mới, truy cập repository hoặc đổi tên/di chuyển một entry.

Sai lầm dễ gặp là ghép DN bằng chuỗi:

```java
// KHÔNG NÊN: uid nhận từ bên ngoài có thể chứa dấu phẩy, dấu cộng,
// dấu bằng, dấu gạch chéo ngược hoặc khoảng trắng cần escape.
String dn = "uid=" + userSuppliedUid + ",ou=people,dc=example,dc=org";
```

Nếu `userSuppliedUid = "lan,qa"`, đoạn mã tạo ra `uid=lan,qa,ou=people,...`, không phải một DN hợp lệ thể hiện giá trị UID chứa dấu phẩy. Cách đúng là **thao tác trên thành phần tên** với `javax.naming.ldap.LdapName`, `javax.naming.ldap.Rdn` và **`org.springframework.ldap.support.LdapNameBuilder`**. Những API này xử lý cú pháp/escape DN và hạn chế nhầm lẫn giữa RDN, parent và search base.

Sau bài học, bạn có thể:

- Đọc cấu trúc DN và phân biệt RDN cụ thể nhất với các RDN của tổ tiên.
- Dựng DN từ giá trị người dùng bằng `LdapNameBuilder.add(type, value)`, không dùng nối chuỗi.
- Tách RDN, tách parent, thay RDN bằng `LdapName`/`Rdn` mà không cắt chuỗi.
- Xử lý giá trị RDN có dấu phẩy, dấu cộng, dấu bằng, dấu `#`, khoảng trắng và dấu `\`.
- Phân biệt **escape DN** với **escape LDAP search filter**.
- Sử dụng DN tương đối đúng base trong `LdapTemplate` và hiểu hậu quả khi đổi RDN/Modify DN.
- Kiểm thử các edge case và kiểm soát rủi ro truy cập sai nhánh trong directory.

## 1. Phân biệt DN, RDN và attribute

Giả sử LDAP server có cây thư mục:

```text
dc=example,dc=org
├── ou=people
│   ├── uid=lan
│   └── uid=minh
├── ou=staff
└── ou=groups
    └── cn=backend
```

DN đầy đủ của Lan:

```text
uid=lan,ou=people,dc=example,dc=org
^^^^^^^ ^^^^^^^^^ ^^^^^^^^^^ ^^^^^^
  RDN      RDN       RDN      RDN
 của entry  của OU    domain   domain
```

Trong ví dụ:

| Khái niệm | Giá trị | Ý nghĩa |
| --- | --- | --- |
| **Full DN** | `uid=lan,ou=people,dc=example,dc=org` | Tên phân cấp xác định entry trong directory |
| **Leaf RDN** (RDN cụ thể nhất) | `uid=lan` | Tên của entry tương đối với parent |
| **Parent DN** | `ou=people,dc=example,dc=org` | Entry/container trực tiếp chứa Lan |
| **Base DN** ứng dụng | `dc=example,dc=org` | Gốc được cấu hình trên `ContextSource` trong ví dụ |
| **Relative DN** so với base | `uid=lan,ou=people` | Tên mà nhiều lời gọi `LdapTemplate` có thể nhận khi base đã đặt |
| **Attribute `uid`** | `lan` | Giá trị thuộc tính trên entry; không phải toàn bộ DN |

**DN là một chuỗi RDN có cấu trúc, không phải chuỗi bất kỳ có dấu phẩy.** Dấu phẩy giữa các thành phần trong DN có ý nghĩa phân cấp. Dấu phẩy **nằm trong giá trị RDN** phải được escape, nếu không parser có thể hiểu thành ranh giới tên.

DN có thể thay đổi khi entry được đổi tên hoặc di chuyển. Vì vậy, với ứng dụng cần ID bền vững qua thời gian, không mặc định DN là mã định danh bất biến; một số directory có thuộc tính định danh riêng như `entryUUID` (tùy server) hoặc `objectGUID` (Active Directory), cần kiểm tra khả năng hỗ trợ và quyền đọc tương ứng.

## 2. Vì sao nối chuỗi thủ công dễ sai?

Giả sử ta muốn tạo DN dưới `ou=people,dc=example,dc=org`:

| Giá trị RDN người dùng mong muốn | Ghép chuỗi thô | Rủi ro |
| --- | --- | --- |
| `lan` | `uid=lan,...` | Có thể chạy trong case đơn giản, nhưng không bao quát dữ liệu thật |
| `lan,qa` | `uid=lan,qa,...` | Dấu phẩy bị hiểu nhầm thành dấu phân cách RDN |
| `lan+admin` | `uid=lan+admin,...` | Dấu cộng có nghĩa đặc biệt trong RDN đa trị |
| `lan=dev` | `uid=lan=dev,...` | Dấu bằng không được xử lý đúng theo cú pháp giá trị |
| `#lan` | `uid=#lan,...` | Dấu `#` đứng đầu có ý nghĩa đặc biệt |
| ` lan ` | `uid= lan ,...` | Khoảng trắng đầu/cuối phải được xử lý chính xác |
| `lan\dev` | `uid=lan\dev,...` | Dấu gạch chéo ngược là ký tự escape trong DN |

Việc chỉ gọi `String.replace(",", "\\,")` là **không đủ**, vì còn các ký tự và quy tắc escape khác. Tự “xóa ký tự lạ” cũng có thể **thay đổi định danh nghiệp vụ** (ví dụ `lan,qa` bị biến thành `lanqa`), làm nhầm entry.

Giải pháp là **lưu dữ liệu đầu vào dưới dạng giá trị** và để API cấu trúc tạo representation:

```java
import javax.naming.Name;
import org.springframework.ldap.support.LdapNameBuilder;

String uid = "lan,qa";
Name dn = LdapNameBuilder.newInstance("ou=people,dc=example,dc=org")
        .add("uid", uid)
        .build();

System.out.println(dn);
// uid=lan\,qa,ou=people,dc=example,dc=org
```

Ở đây `.add("uid", uid)` hiểu `uid` là **attribute type của một RDN** và `uid` thứ hai là **giá trị**; Spring LDAP/JNDI escape giá trị. Không đưa input tùy ý vào overload `add(String name)`, bởi overload đó **phân tích string như một tên LDAP đã có cú pháp**, không phải một giá trị RDN thô.

## 3. Dựng DN đúng bằng `LdapNameBuilder`

`LdapNameBuilder` thuộc `org.springframework.ldap.support` và trả về một `javax.naming.ldap.LdapName` khi gọi `build()`. Một số phương thức thường dùng:

| Phương thức | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| `newInstance()` | Bắt đầu từ tên rỗng | Tự thêm các RDN từ gốc đến leaf |
| `newInstance(String name)` | Bắt đầu bằng tên có cú pháp LDAP | Chỉ dùng tên có cấu trúc đã xác định/được kiểm soát |
| `newInstance(Name name)` | Bắt đầu từ bản sao của tên hiện có | Tránh sửa object gốc ngoài dự kiến |
| `add(String type, Object value)` | Thêm **một RDN** từ tên attribute + giá trị | Ưu tiên cho input động |
| `add(String name)` | Thêm **một đoạn tên LDAP** đã biểu diễn bằng chuỗi | Không dùng trực tiếp với input thô của người dùng |
| `add(Name name)` | Thêm một tên đã parse | Phù hợp khi đã có object `Name` |
| `build()` | Tạo `LdapName` | Có thể truyền cho nhiều API LDAP |

### 3.1. Thêm từ base tới leaf

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

**Điểm dễ nhầm:** khi nhìn DN dưới dạng chuỗi, RDN của entry xuất hiện **bên trái**; nhưng khi xây từ base, ta gọi `add("ou", ...)` trước, `add("uid", ...)` sau. Builder thêm thành phần cụ thể hơn vào phía trái trong cách hiển thị tên.

Ví dụ tạo từ tên rỗng:

```java
LdapName dn = LdapNameBuilder.newInstance()
        .add("dc", "org")
        .add("dc", "example")
        .add("ou", "people")
        .add("uid", "lan")
        .build();

// uid=lan,ou=people,dc=example,dc=org
```

Không đảo thứ tự thành `.add("uid", "lan").add("ou", "people")...` nếu đang xây từ tên rỗng, vì tên kết quả sẽ có quan hệ phân cấp sai.

### 3.2. Tạo DN tương đối cho `LdapTemplate`

Giả sử cấu hình:

```java
import org.springframework.ldap.core.support.LdapContextSource;

LdapContextSource contextSource = new LdapContextSource();
contextSource.setUrl("ldaps://directory.example.org:636");
contextSource.setBase("dc=example,dc=org");
// Cần thêm bind DN/password qua secret và TLS truststore phù hợp.
```

Với một `ContextSource` đã có base `dc=example,dc=org`, nhiều API của Spring LDAP **nhận DN tương đối với base**:

```java
import javax.naming.Name;
import org.springframework.ldap.support.LdapNameBuilder;

Name relativeDn = LdapNameBuilder.newInstance("ou=people")
        .add("uid", "lan")
        .build();

// uid=lan,ou=people
```

Truyền `relativeDn` cho `LdapTemplate.lookup` hay `rename`, tùy API, sẽ thao tác với entry trong vùng base đã cấu hình. **Không tự động gắn lại `dc=example,dc=org` vào mọi DN** nếu `ContextSource` đã thực hiện phần đó; nếu thêm lặp, tên có thể thành `...,dc=example,dc=org,dc=example,dc=org` hoặc không trỏ entry mong muốn.

DN tương đối với `ContextSource` **khác** với RDN: `uid=lan,ou=people` có **hai RDN**, còn leaf RDN chỉ là `uid=lan`.

### 3.3. Tách rõ “phần tin cậy” và “giá trị động”

Một thiết kế an toàn cho phép ứng dụng xác định base/OU, chỉ cho user cung cấp **giá trị UID**:

```java
import javax.naming.Name;
import org.springframework.ldap.support.LdapNameBuilder;

public Name personDn(String userUid) {
    if (userUid == null || userUid.isBlank()) {
        throw new IllegalArgumentException("UID must not be blank");
    }
    return LdapNameBuilder.newInstance("ou=people")
            .add("uid", userUid)
            .build();
}
```

Đây là **xây DN an toàn về cú pháp**; vẫn cần kiểm tra chính sách tên, độ dài, Unicode normalization và quyền truy cập. Nếu tổ chức chỉ cho phép UID dạng `[a-z0-9._-]`, quy tắc nghiệp vụ đó phải được thực thi riêng. Escape không thay thế validation/authorization.

## 4. Đọc từng RDN bằng `LdapName` và `Rdn`

Đối tượng `javax.naming.ldap.LdapName` cho phép truy cập các RDN **đã được phân tích**, không cần `split(",")`.

### 4.1. Chỉ số RDN trong JNDI đi từ phải sang trái

```java
import javax.naming.ldap.LdapName;

LdapName dn =
        new LdapName("uid=lan,ou=people,dc=example,dc=org");

System.out.println(dn.size());       // 4
System.out.println(dn.getRdn(0));     // dc=org
System.out.println(dn.getRdn(1));     // dc=example
System.out.println(dn.getRdn(2));     // ou=people
System.out.println(dn.getRdn(3));     // uid=lan
```

**Quy ước JNDI quan trọng:** RDN bên phải nhất (**ít cụ thể nhất**) có index `0`; RDN bên trái nhất (**cụ thể nhất**) có index `size() - 1`. Không gọi `getRdn(0)` rồi cho rằng đó là tên người dùng ở đầu chuỗi.

### 4.2. Đọc RDN của entry

```java
import javax.naming.ldap.LdapName;
import javax.naming.ldap.Rdn;

LdapName dn =
        new LdapName("uid=lan,ou=people,dc=example,dc=org");

Rdn leaf = dn.getRdn(dn.size() - 1);

System.out.println(leaf.getType());    // uid
System.out.println(leaf.getValue());   // lan
```

Các phương thức `getType()`/`getValue()` có cách dùng trực quan nhất khi RDN gồm **một** cặp type–value. Với **RDN đa trị** như `uid=lan+cn=Nguyen Thi Lan`, phải truy cập toàn bộ thành phần (AVA) thay vì giả định chỉ có một giá trị; xem phần 6.

### 4.3. Lấy parent mà không cắt dấu phẩy

Không nên:

```java
// Sai với dấu phẩy được escape trong giá trị RDN.
String parent = dn.toString().substring(dn.toString().indexOf(',') + 1);
```

Vì nếu `uid` là `lan,qa`, tên hợp lệ có dạng `uid=lan\,qa,ou=people,...`. Dấu phẩy đầu tiên trong chuỗi là **một phần giá trị**, không phải ranh giới parent.

Thay vào đó:

```java
import javax.naming.Name;
import javax.naming.ldap.LdapName;

LdapName dn =
        new LdapName("uid=lan\\,qa,ou=people,dc=example,dc=org");

Name parent = dn.getPrefix(dn.size() - 1);

System.out.println(dn);
// uid=lan\,qa,ou=people,dc=example,dc=org
System.out.println(parent);
// ou=people,dc=example,dc=org
```

`getPrefix(size - 1)` lấy các RDN từ index `0` đến trước index của leaf, tức **DN parent** theo thứ tự cấu trúc JNDI. Không nhầm phương thức `getPrefix` trong API `Name` với việc lấy “một đoạn bên trái” trong chuỗi hiển thị.

Một DN gốc có một thành phần vẫn có `getPrefix(0)` là tên rỗng; tên rỗng không đồng nghĩa một entry parent tồn tại để thao tác. Cần kiểm tra naming context trước khi làm nghiệp vụ dựa trên parent.

### 4.4. So sánh thành phần thay vì so sánh chuỗi

Hai cách viết tên có thể khác nhau về case hoặc escape nhưng chỉ tới cùng cấu trúc tên:

```java
import javax.naming.ldap.LdapName;

LdapName a = new LdapName(
        "CN=Nguyen\\, Lan,OU=People,DC=example,DC=org");
LdapName b = new LdapName(
        "cn=Nguyen\\, Lan,ou=People,dc=example,dc=org");

System.out.println(a.equals(b)); // true theo so sánh cấu trúc LdapName
```

**Chú ý ngữ nghĩa:** `LdapName.equals` so sánh tên theo quy tắc của lớp JNDI, **không** hỏi LDAP server rằng hai entry có tồn tại hay được coi như một theo schema/matching rule/ACL của directory. Không dùng so sánh chuỗi `equalsIgnoreCase` hay normalization tùy ý làm cơ sở **duy nhất** cho quyết định bảo mật hoặc cấp quyền.

## 5. Đổi RDN bằng object thay vì sửa chuỗi

Giả sử ứng dụng cần đổi `uid=lan` thành `uid=lan.nguyen` nhưng giữ nguyên parent. Ta có thể tạo **DN đích** bằng cách sao chép DN cũ, bỏ RDN cụ thể nhất và thêm RDN mới:

```java
import javax.naming.InvalidNameException;
import javax.naming.ldap.LdapName;
import javax.naming.ldap.Rdn;

public static LdapName withNewUid(
        LdapName original, String newUid) throws InvalidNameException {

    if (original.isEmpty()) {
        throw new IllegalArgumentException("Cannot rename empty DN");
    }

    LdapName updated = (LdapName) original.clone();
    updated.remove(updated.size() - 1);  // Bỏ RDN cụ thể nhất (uid cũ)
    updated.add(new Rdn("uid", newUid));  // Thêm RDN mới, escape tự động
    return updated;
}

LdapName oldDn =
        new LdapName("uid=lan,ou=people,dc=example,dc=org");
LdapName newDn = withNewUid(oldDn, "lan.nguyen");

System.out.println(oldDn);
// uid=lan,ou=people,dc=example,dc=org
System.out.println(newDn);
// uid=lan.nguyen,ou=people,dc=example,dc=org
```

Điểm mạnh của cách này:

- Không phụ thuộc dấu phẩy, dấu cộng hoặc ký tự escape trong tên cũ.
- Giữ nguyên các RDN của parent.
- Tránh chỉnh sửa `original` vì làm việc trên `clone()`.
- Dùng `new Rdn("uid", newUid)` để tạo thành phần mới theo cú pháp đúng.

Tuy nhiên, **một DN đích mới tồn tại trong bộ nhớ Java không tự đổi tên entry trên LDAP server**. Muốn thực hiện thật, gọi một thao tác **Modify DN** được directory hỗ trợ, ví dụ `LdapTemplate.rename(oldDn, newDn)`; phần 8 trình bày cách thực hiện an toàn.

### 5.1. Giữ leaf RDN, chuyển sang parent khác

Giả sử chuyển Lan từ `ou=people` sang `ou=staff` nhưng giữ `uid=lan`:

```java
import javax.naming.ldap.LdapName;
import javax.naming.ldap.Rdn;

LdapName oldDn =
        new LdapName("uid=lan,ou=people,dc=example,dc=org");
Rdn leaf = oldDn.getRdn(oldDn.size() - 1);

LdapName newParent =
        new LdapName("ou=staff,dc=example,dc=org");
LdapName movedDn = (LdapName) newParent.clone();
movedDn.add(leaf);

System.out.println(movedDn);
// uid=lan,ou=staff,dc=example,dc=org
```

Không cần lấy chuỗi `"uid=lan"` bằng `split(",")` rồi ghép lại. Việc thêm trực tiếp `Rdn` bảo toàn cách biểu diễn giá trị đã được parse.

**Quan trọng:** parent đích phải nằm trong vùng server quản lý, tồn tại và có quyền di chuyển phù hợp. Di chuyển xuyên naming context hoặc xuyên server LDAP có thể không được hỗ trợ bằng một Modify DN. **Tạo tên đúng cú pháp không bảo đảm server chấp nhận thao tác.**

## 6. RDN nhiều cặp type–value

Đa số ví dụ người dùng dùng **RDN đơn trị**, như `uid=lan`. Nhưng LDAP cho phép **multi-valued RDN**, chẳng hạn:

```text
cn=Nguyen Thi Lan+uid=lan,ou=people,dc=example,dc=org
```

Trong RDN đó, dấu `+` **phân tách hai Attribute Value Assertion (AVA)**: `cn=Nguyen Thi Lan` và `uid=lan`. Ngược lại, một dấu cộng thuộc **giá trị** phải được escape:

```text
uid=lan\+qa,ou=people,dc=example,dc=org
```

Hai chuỗi trên thể hiện hai cấu trúc khác nhau.

### 6.1. Đọc đủ thành phần của multi-valued RDN

```java
import javax.naming.directory.Attributes;
import javax.naming.ldap.LdapName;
import javax.naming.ldap.Rdn;

LdapName dn = new LdapName(
        "cn=Nguyen Thi Lan+uid=lan,ou=people,dc=example,dc=org");
Rdn leaf = dn.getRdn(dn.size() - 1);

System.out.println(leaf.size()); // 2

Attributes avas = leaf.toAttributes();
Object uidValue = avas.get("uid").get();
Object cnValue = avas.get("cn").get();

System.out.println(uidValue); // lan
System.out.println(cnValue);  // Nguyen Thi Lan
```

Không dựa vào thứ tự chuỗi `cn=...+uid=...` khi so sánh RDN đa trị: thứ tự AVA bên trong một RDN không mang ý nghĩa phân cấp. `Rdn.toAttributes()` cho phép truy cập theo tên attribute.

### 6.2. Không giả định RDN luôn là `uid`

Trong một hệ thống thực tế có thể có các kiểu tên:

```text
uid=lan,ou=people,dc=example,dc=org
cn=backend,ou=groups,dc=example,dc=org
ou=people,dc=example,dc=org
cn=Nguyen Thi Lan+uid=lan,ou=people,dc=example,dc=org
```

Hàm `withNewUid` ở phần 5 được thiết kế cho entry user đặt tên bằng `uid`; nó **không** phải thuật toán rename tổng quát áp dụng cho mọi entry. Trước khi bỏ leaf RDN, kiểm tra loại entry và quy tắc đặt tên; với multi-valued RDN, phải có chính sách rõ về việc thêm/bỏ các AVA.

## 7. Escape đúng: DN và LDAP filter là hai cú pháp khác nhau

**Dựng DN** và **tìm entry bằng filter** là hai công việc khác nhau.

| Mục tiêu | Ví dụ | API nên dùng |
| --- | --- | --- |
| Tạo DN từ `uid=lan,qa` | `uid=lan\,qa,ou=people` | `LdapNameBuilder.add("uid", rawUid)` hoặc `new Rdn("uid", rawUid)` |
| Tra cứu uid **bằng giá trị chính xác** | `(uid=lan,qa)` (giá trị được escape khi cần) | `LdapQueryBuilder.where("uid").is(rawUid)` |
| Tìm bằng filter substring | `(cn=Lan*)` | Builder/filter API với wildcard do ứng dụng quyết định |
| Đổi tên entry | Old DN → New DN | `LdapTemplate.rename(Name, Name)` |
| So sánh RDN | `getRdn(index)` | `LdapName`/`Rdn` |

### 7.1. Tạo DN dùng cú pháp RFC 4514

Với giá trị RDN động, **ưu tiên API tạo thành phần**:

```java
String rawUid = "lan,qa";
LdapName dn = LdapNameBuilder.newInstance("ou=people")
        .add("uid", rawUid)
        .build();
// uid=lan\,qa,ou=people
```

Nếu bắt buộc phải tạo representation thủ công để tích hợp một API chỉ nhận chuỗi, JNDI có `Rdn.escapeValue(Object)`:

```java
import javax.naming.ldap.Rdn;

String value = "Lan, QA";
String escapedValue = Rdn.escapeValue(value);
String dnAsString = "cn=" + escapedValue + ",ou=people,dc=example,dc=org";

// cn=Lan\, QA,ou=people,dc=example,dc=org
```

Đây vẫn là phương án dự phòng: dễ chọn sai type, parent hoặc phạm vi; dùng `LdapNameBuilder` khi có thể. `Rdn.escapeValue` escape **giá trị của một RDN**; không dùng nó để escape **cả DN hoàn chỉnh** vì sẽ làm mất các dấu phân cấp có chủ đích.

### 7.2. LDAP filter dùng RFC 4515

Ví dụ tìm theo UID:

```java
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;

String rawUid = "lan*ops";
LdapQuery query = LdapQueryBuilder.query()
        .base("ou=people")
        .where("objectClass").is("inetOrgPerson")
        .and("uid").is(rawUid);
```

`.is(rawUid)` biểu diễn **equality match với giá trị literal**, không coi dấu `*` do người dùng nhập là wildcard. Nếu ghép chuỗi:

```java
// KHÔNG AN TOÀN: ký tự '*' trong input có thể biến đổi ý nghĩa filter.
String unsafeFilter = "(uid=" + rawUid + ")";
```

thì nguy cơ không chỉ là sai cú pháp mà còn là **LDAP filter injection**. Escape cho DN (**RFC 4514**) và escape cho filter (**RFC 4515**) không thể thay thế cho nhau. Không chuyển `LdapName.toString()` thành filter bằng nối chuỗi tùy tiện; khi cần tra cứu attribute chứa DN, hãy dùng builder với giá trị DN như một **giá trị**.

## 8. Liên hệ với `LdapTemplate` và Modify DN

### 8.1. Lookup một entry theo DN tương đối

Ví dụ trích xuất `cn`:

```java
import javax.naming.Name;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

public String displayName(LdapTemplate ldapTemplate, String uid) {
    Name relativeDn = LdapNameBuilder.newInstance("ou=people")
            .add("uid", uid)
            .build();

    return ldapTemplate.lookup(
            relativeDn,
            new String[] {"cn"},
            (AttributesMapper<String>) attrs ->
                    (String) attrs.get("cn").get());
}
```

Giả sử `ContextSource` base là `dc=example,dc=org`. Code này chỉ hoạt động đúng khi entry thực sự đặt tên `uid=...` và nằm trực tiếp dưới `ou=people`. Nếu một user có thể ở nhiều OU hoặc RDN đặt theo `cn`, phải **search để xác định DN thật** thay vì đoán DN từ username.

Ngoài ra, cần kiểm tra quyền đọc `cn` và xử lý khi `attrs.get("cn")` bị thiếu/ẩn. Việc ánh xạ DN an toàn về cú pháp **không** thay thế kiểm soát ACL.

### 8.2. Đổi leaf RDN bằng `LdapTemplate.rename`

```java
import javax.naming.Name;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

public void renameUser(LdapTemplate ldapTemplate,
                       String oldUid, String newUid) {
    Name oldDn = LdapNameBuilder.newInstance("ou=people")
            .add("uid", oldUid)
            .build();

    Name newDn = LdapNameBuilder.newInstance("ou=people")
            .add("uid", newUid)
            .build();

    ldapTemplate.rename(oldDn, newDn);
}
```

Ở ví dụ này, hai DN đều **tương đối với cùng base**. `rename` yêu cầu server thực hiện **Modify DN**, không phải thay chuỗi trong bộ nhớ Java. Trước khi gọi, cần xác minh:

1. Entry nguồn tồn tại và đúng chủ thể.
2. DN đích chưa bị một entry khác chiếm.
3. New RDN phù hợp naming rule/schema và không vi phạm tính đơn trị, giá trị bắt buộc.
4. Tài khoản bind có quyền đổi tên tại source/parent theo chính sách server.
5. Các hệ thống giữ DN trong `member`, `manager` hoặc cache được đồng bộ sau rename.

Theo giao thức LDAP, `ModifyDNRequest` có `newrdn`, `deleteoldrdn` và `newSuperior` (khi chuyển parent). Việc `deleteoldrdn` là `true` hay `false` ảnh hưởng giá trị thuộc tính RDN cũ; API `LdapTemplate.rename(Name, Name)` không phơi bày mọi trường của giao thức thành tham số riêng. Hãy kiểm tra JNDI provider/server và đọc lại entry sau đổi tên nếu nghiệp vụ phụ thuộc vào việc giữ/xóa giá trị cũ.

### 8.3. Di chuyển parent bằng `rename`

```java
import javax.naming.Name;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

Name oldDn = LdapNameBuilder.newInstance("ou=people")
        .add("uid", "lan")
        .build();

Name newDn = LdapNameBuilder.newInstance("ou=staff")
        .add("uid", "lan")
        .build();

ldapTemplate.rename(oldDn, newDn);
```

Lúc này leaf RDN không đổi nhưng **parent DN thay đổi**. Chỉ sửa thuộc tính `ou` trong entry sẽ không di chuyển nó trong DIT. LDAP server có thể từ chối di chuyển nếu parent đích không tồn tại, DN đích trùng, ACL không đủ, schema không cho phép hoặc việc di chuyển vượt naming context/DSA mà server quản lý.

## 9. Kiểm tra DN có nằm dưới nhánh được phép không?

Một tính năng tự phục vụ chỉ được sửa entry dưới `ou=people,dc=example,dc=org`. Không nên kiểm tra bằng:

```java
// Không nên dùng so sánh hậu tố chuỗi để ra quyết định cấu trúc.
boolean allowed = userSuppliedDn.endsWith(
        "ou=people,dc=example,dc=org");
```

Kỹ thuật chuỗi dễ bỏ sót khác biệt escape, case hoặc các chuỗi được dựng sai. Có thể **parse DN và so sánh các thành phần**:

```java
import javax.naming.ldap.LdapName;

LdapName fullDn = new LdapName(
        "uid=lan,ou=people,dc=example,dc=org");
LdapName allowedBase = new LdapName(
        "ou=people,dc=example,dc=org");

// Trong API Name của JNDI, index 0 là RDN phải nhất,
// nên cấu trúc suffix của chuỗi hiển thị là prefix của LdapName.
boolean inside = fullDn.startsWith(allowedBase)
        && fullDn.size() > allowedBase.size();

System.out.println(inside); // true
```

Trong mô hình JNDI, `startsWith(allowedBase)` so khớp các thành phần từ **RDN index 0** (gốc về phía phải trong chuỗi hiển thị). Điều kiện `fullDn.size() > allowedBase.size()` loại trừ chính entry OU nếu chỉ muốn cho phép **hậu duệ** của nó.

**Đây chỉ là kiểm tra phạm vi cấu trúc ở ứng dụng**, không phải cơ chế authorization hoàn chỉnh:

- Tài khoản bind vẫn phải bị hạn chế bằng ACL của server LDAP.
- Ứng dụng phải biết naming context nào được phục vụ và có referral/alias hay không.
- Nếu dùng kết quả parse để quyết định bảo mật, cần thống nhất schema/matching semantics và policy server; `LdapName.equals` không thay thế việc hỏi server xác minh định danh.
- Không tin client tự gửi full DN rồi dùng nó làm căn cứ duy nhất để cấp quyền truy cập entry.
- Nếu thao tác viết có thể thay đổi parent/RDN, phải kiểm tra **cả DN nguồn và DN đích**.

### 9.1. Vì sao so sánh chỉ leaf RDN không đủ?

Hai entry:

```text
uid=lan,ou=people,dc=example,dc=org
uid=lan,ou=contractors,dc=example,dc=org
```

có cùng `Rdn("uid", "lan")`, nhưng **DN khác nhau**. Dựa vào `getRdn(size - 1)` để xác thực “đó chính là Lan” có thể chọn sai đối tượng. Danh tính LDAP phải xét **đúng DN và ngữ cảnh**, hoặc định danh bền vững riêng được directory cung cấp.

## 10. Spring Data LDAP ODM: RDN và `@Id`

Một entity ODM có thể ánh xạ DN bằng `@Id` và thuộc tính RDN qua `@DnAttribute`:

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
public class Person {
    @Id
    private Name dn;

    @DnAttribute(value = "uid")
    private String uid;

    @Attribute(name = "cn")
    private String fullName;

    @Attribute(name = "sn")
    private String surname;

    public Person() {}
    // Getter/setter và mapping còn lại theo quy ước dự án.
}
```

Trong ví dụ:

- `@Id Name dn` biểu diễn **DN**, không phải chỉ giá trị `uid`.
- `@DnAttribute` tham gia ánh xạ một giá trị vào RDN; với DN nhiều thành phần, việc định vị RDN bằng `index`/base phải được thiết kế theo tài liệu của phiên bản Spring LDAP.
- `@Entry(base = "ou=people")` xác định nơi entity dự kiến nằm dưới base `ContextSource`, không tự tạo OU đó.
- `@Attribute` ánh xạ thuộc tính thông thường; server vẫn kiểm tra `objectClass` và schema.

**Đừng coi thay field `uid` trong object rồi gọi `repository.save(person)` là phép đổi RDN bảo đảm nguyên tử.** Spring LDAP ODM có các đường cập nhật có thể xóa entry cũ rồi tạo entry mới khi DN thay đổi, tùy API/phiên bản/cấu hình; hành vi đó khác một Modify DN tường minh và có rủi ro đối với tham chiếu DN, hậu duệ hoặc lỗi giữa chừng. Khi nghiệp vụ cần **rename/move**, cân nhắc `LdapTemplate.rename(...)` với DN nguồn/đích được dựng bằng RDN đúng cách, sau đó tải lại entity.

Nếu một người được chuyển từ `ou=people` sang `ou=staff`, repository có `@Entry(base = "ou=people")` có thể không còn tìm thấy entry ở OU mới. Việc đổi DN cần xem xét cả kiến trúc ánh xạ và dữ liệu tham chiếu.

## 11. Các lỗi phổ biến và cách chẩn đoán

| Hiện tượng | Nguyên nhân có thể | Cách khắc phục |
| --- | --- | --- |
| `InvalidNameException` khi UID chứa dấu phẩy | Nối chuỗi `"uid=" + uid` | Dùng `LdapNameBuilder.add("uid", uid)` |
| Một UID chứa `+` được hiểu thành hai AVA | Không escape dấu cộng | Tạo `Rdn` từ type/value |
| `getRdn(0)` ra `dc=org` thay vì `uid=lan` | Nhầm thứ tự index JNDI | Leaf là `getRdn(size - 1)` |
| Tách parent sai khi tên chứa `\,` | `split(",")` hoặc `indexOf(',')` | Dùng `getPrefix(size - 1)` |
| Query ghép DN lặp `dc=example,dc=org` | Dùng full DN trong API yêu cầu relative DN | Xác nhận `ContextSource` base và contract API |
| `lookup` báo không tìm thấy dù UID đúng | User ở OU khác hoặc RDN là `cn` | Search để lấy DN thật trước |
| Đổi field `ou` nhưng entry không chuyển OU | Sửa attribute không phải Modify DN | Dùng `LdapTemplate.rename` khi server cho phép |
| Rename báo `entryAlreadyExists` | DN đích đã có | Kiểm tra xung đột và quy tắc duy nhất dưới parent |
| Rename báo `namingViolation` | RDN/parent mới vi phạm schema hoặc naming rule | Kiểm tra schema, objectClass, DN đích |
| Rename báo `insufficientAccessRights` | Principal thiếu quyền trên source/đích | Xác minh ACL, không cấp quyền rộng tùy tiện |
| DN so sánh bằng chuỗi trả false dù cùng cấu trúc | Khác case/escape/representation | Parse thành `LdapName`, xét semantics server |
| RDN đa trị chỉ đọc một field | Giả định mỗi RDN chỉ có một AVA | Dùng `Rdn.toAttributes()` |
| Filter theo `uid` chứa `*` trả quá nhiều entry | Escape DN bị nhầm với escape filter | Dùng `LdapQueryBuilder.where(...).is(...)` |
| Rename thành công nhưng group mất thành viên | `member`/`uniqueMember` còn lưu DN cũ | Kiểm tra chức năng cập nhật tham chiếu và đồng bộ group |

### 11.1. Các mã lỗi LDAP liên quan

| LDAP result code | Ý nghĩa thường gặp |
| --- | --- |
| `noSuchObject (32)` | DN nguồn hoặc parent đích không tồn tại / không tìm thấy |
| `entryAlreadyExists (68)` | DN đích trùng entry đang có |
| `namingViolation (64)` | RDN hoặc cấu trúc tên không hợp lệ theo directory |
| `objectClassViolation (65)` | Schema/objectClass không cho phép thay đổi |
| `insufficientAccessRights (50)` | Principal thiếu quyền rename/move |
| `affectsMultipleDSAs (71)` | Thao tác vượt khả năng xử lý trên nhiều DSA |
| `unwillingToPerform (53)` | Server từ chối vì policy/giới hạn cụ thể |

Mã lỗi là **đầu mối chẩn đoán**, không phải một kết luận duy nhất cho mọi vendor. Ghi loại thao tác, base DN đã được phân loại, thời gian và mã lỗi; tránh đưa full DN người dùng, filter hoặc credential nhạy cảm vào log/tracing tùy tiện.

## 12. Bài thực hành: tạo, phân tích, đổi và so sánh RDN

### Bước 1. Dựng DN cho giá trị có dấu phẩy

```java
LdapName dn = LdapNameBuilder.newInstance("ou=people,dc=example,dc=org")
        .add("uid", "lan,qa")
        .build();

System.out.println(dn);
// uid=lan\,qa,ou=people,dc=example,dc=org
```

Đảm bảo đây là **một** leaf RDN `uid=lan,qa` chứ không tách thành hai RDN.

### Bước 2. Trích xuất leaf RDN và parent

```java
Rdn leaf = dn.getRdn(dn.size() - 1);
Name parent = dn.getPrefix(dn.size() - 1);

System.out.println(leaf.getType());   // uid
System.out.println(leaf.getValue());  // lan,qa
System.out.println(parent);           // ou=people,dc=example,dc=org
```

### Bước 3. Thay RDN mà không thay parent

```java
LdapName renamed = withNewUid(dn, "lan+qa");

System.out.println(renamed);
// uid=lan\+qa,ou=people,dc=example,dc=org
```

Hàm `withNewUid` được định nghĩa ở phần 5; dấu `+` trong UID là **ký tự literal**, không phải cú pháp multi-valued RDN.

### Bước 4. Di chuyển sang parent khác

```java
LdapName newParent =
        new LdapName("ou=staff,dc=example,dc=org");
LdapName moved = (LdapName) newParent.clone();
moved.add(renamed.getRdn(renamed.size() - 1));

System.out.println(moved);
// uid=lan\+qa,ou=staff,dc=example,dc=org
```

Đây mới chỉ là thao tác Java **tạo DN đích**. Muốn thay đổi entry trên server, dùng `LdapTemplate.rename` với DN đúng base và kiểm tra ACL/schema.

### Bước 5. Kiểm tra cấu trúc bằng unit test

```java
import javax.naming.ldap.LdapName;
import org.springframework.ldap.support.LdapNameBuilder;

String rawUid = "lan,qa";
LdapName dn = LdapNameBuilder.newInstance("ou=people,dc=example,dc=org")
        .add("uid", rawUid)
        .build();

if (!rawUid.equals(dn.getRdn(dn.size() - 1).getValue())) {
    throw new AssertionError("UID changed during DN encoding");
}

LdapName expected = new LdapName(
        "uid=lan\\,qa,ou=people,dc=example,dc=org");
if (!expected.equals(dn)) {
    throw new AssertionError("Incorrect DN structure");
}

LdapName parent = (LdapName) dn.getPrefix(dn.size() - 1);
if (!parent.equals(new LdapName("ou=people,dc=example,dc=org"))) {
    throw new AssertionError("Incorrect parent DN");
}
```

Unit test so sánh **giá trị leaf RDN đã parse** và **cấu trúc DN**, thay vì chỉ kiểm tra một chuỗi được in ra. Trong integration test với server thực/nhúng, kiểm tra thêm:

1. `uid` có dấu phẩy, dấu cộng, dấu bằng, dấu gạch chéo ngược, dấu `#` đầu và khoảng trắng đầu/cuối.
2. Giá trị Unicode và cách directory thực thi normalization/matching rule.
3. DN tương đối có tìm đúng entry theo base `ContextSource` không.
4. DN ngoài nhánh `ou=people` có bị ứng dụng và ACL chặn đúng không.
5. Rename cùng parent, move sang `ou=staff`, DN đích trùng và parent không tồn tại.
6. Giá trị attribute tạo nên RDN cũ được giữ/xóa theo chính sách server khi Modify DN.
7. Group/manager references, repository base và cache sau khi DN thay đổi.
8. Nếu request timeout sau rename, đọc lại **DN cũ và DN mới** trước khi retry, vì server có thể đã thực hiện thành công.

## 13. Câu hỏi tự kiểm tra

**Câu 1.** Người dùng nhập `uid=lan,qa`. Vì sao `"uid=" + uid + ",ou=people"` là sai và nên thay thế bằng gì?

*Gợi ý:* Dấu phẩy trong giá trị chưa được escape có thể bị hiểu như ranh giới RDN. Dùng `LdapNameBuilder.newInstance("ou=people").add("uid", uid).build()`.

**Câu 2.** Với `uid=lan,ou=people,dc=example,dc=org`, `getRdn(0)` trả gì?

*Gợi ý:* `dc=org`; leaf RDN là `getRdn(size() - 1)`.

**Câu 3.** Tại sao không thể dùng `split(",")` để lấy parent của `uid=lan\,qa,ou=people,...`?

*Gợi ý:* Dấu phẩy đầu thuộc giá trị đã escape. Dùng `getPrefix(size - 1)` để tách theo thành phần.

**Câu 4.** Khi một RDN là `cn=Lan+uid=lan`, có thể coi dấu `+` là ký tự trong giá trị `cn` không?

*Gợi ý:* Không. Dấu `+` phân tách AVA của **multi-valued RDN**; muốn giá trị chứa dấu cộng thì phải escape nó (hoặc tạo RDN bằng API type/value).

**Câu 5.** Vì sao `new Rdn("uid", "lan,qa")` an toàn hơn `new Rdn("uid=lan,qa")`?

*Gợi ý:* Constructor type/value xem dấu phẩy như **dữ liệu giá trị** và escape đúng; constructor chuỗi phải parse một biểu thức RDN đã có cú pháp và sẽ không thể tự suy ra ý định từ input thô sai định dạng.

**Câu 6.** `LdapTemplate.rename(oldDn, newDn)` thành công có tự cập nhật mọi giá trị `member` ở các nhóm không?

*Gợi ý:* Không bảo đảm. Một số directory có chức năng cập nhật tham chiếu; cần kiểm tra thực tế và quy trình đồng bộ.

**Câu 7.** Khi `ContextSource` có base `dc=example,dc=org`, vì sao DN truyền cho `LdapTemplate.lookup` thường chỉ cần `uid=lan,ou=people`?

*Gợi ý:* API xử lý DN tương đối theo base của `ContextSource`; tự thêm suffix có thể làm lặp base hoặc sai entry.

**Câu 8.** Parse DN và kiểm tra `startsWith(allowedBase)` đã đủ để cấp quyền xóa entry chưa?

*Gợi ý:* Chưa. Đó chỉ là điều kiện phạm vi cấu trúc. Còn cần xác thực chủ thể, kiểm tra ACL của server và chính sách nghiệp vụ cho DN nguồn/đích.

## 14. Ghi nhớ

- **DN được cấu thành từ RDN**, không nên thao tác bằng `split`, `substring` hoặc ghép chuỗi tự phát.
- Dùng **`LdapNameBuilder.add(type, value)`** hoặc **`new Rdn(type, value)`** với dữ liệu động để xử lý escape đúng cú pháp.
- Trong `LdapName` của JNDI, **index 0 là RDN bên phải nhất**; leaf RDN ở **`size() - 1`**. Dùng `getPrefix(size - 1)` để lấy parent.
- Một RDN có thể **đa trị**, dấu `+` phân cách AVA; dùng `Rdn.toAttributes()` thay vì giả định luôn có một type/value.
- **Escape DN và escape LDAP filter là hai bài toán riêng** (RFC 4514 và RFC 4515). Dùng `LdapQueryBuilder` khi tạo search filter.
- `LdapTemplate.rename` mới thực hiện **Modify DN trên server**; đổi chuỗi hoặc field ODM chỉ tạo dữ liệu trong Java và có thể không tương đương rename nguyên tử.
- Đúng cú pháp **chưa đủ**: schema, naming context, base DN, ACL và quy tắc đồng bộ tham chiếu vẫn quyết định thao tác có hợp lệ và an toàn không.

**Tài liệu tham khảo chính thức:**

- [Spring LDAP — LdapNameBuilder API](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/support/LdapNameBuilder.html): tạo DN theo từng RDN và thứ tự thành phần.
- [Spring LDAP — Basic Usage](https://docs.spring.io/spring-ldap/reference/spring-ldap-basic-usage.html): ví dụ tạo/trích xuất DN bằng `LdapNameBuilder` và `LdapUtils`.
- [Oracle JNDI — Manipulating LdapName](https://docs.oracle.com/javase/tutorial/jndi/newstuff/ldapname.html): `getRdn`, thứ tự index, thêm/xóa RDN.
- [Java API — LdapName](https://docs.oracle.com/en/java/javase/21/docs/api/java.naming/javax/naming/ldap/LdapName.html): so sánh, `getPrefix`, `getRdns`, `clone`.
- [Java API — Rdn](https://docs.oracle.com/en/java/javase/21/docs/api/java.naming/javax/naming/ldap/Rdn.html): RDN đa trị, `getType`, `getValue`, `escapeValue`, `toAttributes`.
- [RFC 4514 — String Representation of Distinguished Names](https://www.rfc-editor.org/rfc/rfc4514): cú pháp DN/RDN và escape.
- [RFC 4515 — String Representation of Search Filters](https://www.rfc-editor.org/rfc/rfc4515): cú pháp filter và escape giá trị truy vấn.
- [RFC 4511 — LDAP Protocol](https://www.rfc-editor.org/rfc/rfc4511): Modify DN, result code và thao tác LDAP.
- [Spring Data LDAP — Reference](https://docs.spring.io/spring-data/ldap/reference/): repository và entity ODM.
