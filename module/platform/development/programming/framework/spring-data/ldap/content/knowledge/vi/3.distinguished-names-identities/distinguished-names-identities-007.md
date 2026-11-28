# Ký tự đặc biệt, Unicode và quy tắc escape của DN

## Mục tiêu học tập

Sau bài học này, bạn có thể:

1. Giải thích vì sao **Distinguished Name (DN)** có cú pháp riêng, và vì sao một ký tự trong **giá trị RDN** có thể bị hiểu nhầm thành ký hiệu phân tách cấu trúc.
2. Nhận diện các ký tự phải escape theo **RFC 4514**: dấu phẩy, dấu cộng, dấu gạch chéo ngược, các ký tự đặc biệt khác, dấu cách ở đầu/cuối, dấu `#` ở đầu và byte NUL.
3. Phân biệt cách biểu diễn ký tự Unicode trực tiếp bằng **UTF-8** với cách escape theo từng octet `\HH`; hiểu lý do không nên escape ký tự Unicode theo mã code point một cách tùy ý.
4. Sử dụng `javax.naming.ldap.LdapName`, `Rdn` và Spring LDAP `LdapNameBuilder` để xây DN từ dữ liệu người dùng thay vì nối chuỗi.
5. Hiểu thứ tự component trong JNDI, RDN đơn trị/đa trị, DN đầy đủ/DN tương đối và những giới hạn của so sánh chuỗi thuần.
6. Phân biệt **DN escaping** (RFC 4514), **LDAP filter escaping** (RFC 4515), **Java string escaping**, **YAML quoting** và **LDIF encoding** (RFC 2849).
7. Viết kiểm thử JUnit cho username có dấu phẩy, dấu cộng, khoảng trắng, dấu gạch chéo ngược và Unicode; xác minh lookup trên directory thử nghiệm.

Bài thuộc chương **DN và định danh** của module `SPRING_DATA_LDAP`. Khi Spring Data LDAP ánh xạ entry LDAP phân cấp thành Java object qua repository và `LdapTemplate`, việc xây DN đúng giúp tránh trỏ nhầm entry khi CRUD, rename/move hoặc bind; đồng thời phải tôn trọng `objectClass`, schema, bộ lọc truy vấn an toàn, TLS, quyền truy cập và kiểm thử với directory.

## 1. DN là một cấu trúc, không phải một chuỗi tùy ý

LDAP tổ chức entry theo cây **Directory Information Tree (DIT)**. Tên của mỗi entry là **DN**, gồm nhiều **Relative Distinguished Name (RDN)** nối bằng dấu phẩy trong cách biểu diễn văn bản thông dụng.

Ví dụ:

```text
uid=an.nguyen,ou=people,dc=example,dc=org
```

Phân tích:

| Thành phần | Vai trò |
| --- | --- |
| `uid=an.nguyen` | RDN cụ thể nhất, đặt tên entry người dùng |
| `ou=people` | RDN của nhánh cha |
| `dc=example` | RDN của domain component |
| `dc=org` | RDN ở gần gốc nhất trong ví dụ |
| Toàn bộ chuỗi | DN xác định vị trí của entry tại thời điểm hiện tại |

Giữa các RDN, dấu phẩy `,` mang **nghĩa cấu trúc**. Trong một RDN, dấu bằng `=` phân tách **attribute type** và **attribute value**.

Vì vậy, hai khái niệm khác nhau:

```text
DN gồm 4 RDN:
uid=an.nguyen,ou=people,dc=example,dc=org

Giá trị RDN chứa dấu phẩy:
cn=Nguyễn\, An,ou=people,dc=example,dc=org
          ^^
          Dấu phẩy ở trong giá trị, không chia thành RDN khác
```

Trong dòng thứ hai, dấu `\` trước `,` cho biết dấu phẩy là **dữ liệu của `cn`**, không phải ranh giới giữa hai RDN.

> **Nguyên tắc:** Cần phân biệt **cú pháp biểu diễn DN** với **giá trị thuộc tính thật**. Khi đã parse DN thành cấu trúc, thư viện có thể trả về giá trị `Nguyễn, An` mà không kèm backslash escape.

### 1.1. Một RDN có thể chứa nhiều cặp type/value

RDN thông thường có một cặp:

```text
uid=an.nguyen
```

Nhưng một RDN có thể đa trị (*multi-valued RDN*):

```text
cn=Nguyễn\, An+uid=an.nguyen
```

Dấu `+` không escape trong ví dụ phân tách **hai attribute-value assertion của cùng một RDN**. Nó **không** tạo ra RDN mới.

Ngược lại, nếu dấu cộng là dữ liệu của `cn`:

```text
cn=R\+D,ou=teams,dc=example,dc=org
```

thì giá trị là `R+D`, không phải một RDN đa trị. Đây là lý do phải dùng parser/builder thay vì đếm hoặc tách chuỗi DN bằng dấu phẩy/dấu cộng một cách thủ công.

## 2. Quy tắc escaping của RFC 4514

**RFC 4514 — LDAP: String Representation of Distinguished Names** mô tả cách chuyển giữa DN có cấu trúc và dạng chuỗi văn bản.

Với cú pháp DN kiểu RFC 4514, một số ký tự trong **giá trị RDN** phải escape để không bị hiểu là cú pháp phân tách hoặc có ý nghĩa đặc biệt.

### 2.1. Những ký tự đặc biệt phải escape trong giá trị RDN

| Ký tự trong giá trị | Cách biểu diễn minh họa | Vì sao cần escape? |
| --- | --- | --- |
| Dấu phẩy `,` | `cn=Nguyễn\, An` | `,` là dấu phân tách các RDN |
| Dấu cộng `+` | `cn=R\+D` | `+` phân tách các assertion cùng RDN |
| Dấu nháy kép `"` | `cn=An\"QA` | Có vai trò đặc biệt trong cú pháp DN |
| Gạch chéo ngược `\` | `cn=C:\\Logs` | `\` mở đầu một escape sequence |
| Dấu chấm phẩy `;` | `cn=Sales\;APAC` | Nằm trong nhóm ký tự phải escape |
| Dấu nhỏ hơn `<` | `cn=A\<B` | Nằm trong nhóm ký tự phải escape |
| Dấu lớn hơn `>` | `cn=A\>B` | Nằm trong nhóm ký tự phải escape |
| Dấu bằng `=` trong value | `cn=key\=value` | `=` có vai trò phân chia type/value |
| Dấu cách **đầu** value | `cn=\ An` | Phải biểu diễn là dữ liệu, không phải whitespace cú pháp |
| Dấu cách **cuối** value | `cn=An\ ` | Phải được giữ là một phần của giá trị |
| Dấu `#` ở **đầu** value | `cn=\#team` | `#` ở đầu có ý nghĩa đặc biệt |
| Byte NUL | `cn=A\00B` | Octet `00` phải escape theo dạng hex |

Bảng trên áp dụng cho **giá trị** của một RDN. Dấu `=` giữa type/value và dấu `,` giữa các RDN là **cú pháp hợp lệ**, không được escape nếu bạn thực sự muốn chúng đóng vai trò phân tách.

### 2.2. Quy tắc phụ thuộc vị trí: khoảng trắng và dấu #

Không phải mọi khoảng trắng hoặc dấu `#` ở mọi nơi đều bắt buộc escape.

```text
cn=An Nguyen,ou=people,dc=example,dc=org
   ^^
   Khoảng trắng ở giữa value: có thể viết trực tiếp

cn=\ An,ou=people,dc=example,dc=org
   ^^
   Khoảng trắng ở đầu value: phải escape

cn=An\ ,ou=people,dc=example,dc=org
     ^^
     Khoảng trắng ở cuối value: phải escape

cn=\#ops,ou=teams,dc=example,dc=org
   ^^
   Dấu # đứng đầu value: phải escape

cn=team#1,ou=teams,dc=example,dc=org
       ^
       # không ở đầu value: không bắt buộc escape vì vị trí
```

Hãy đặc biệt thận trọng với dữ liệu nhập từ giao diện: **`" An"` và `"An"` là hai chuỗi đầu vào khác nhau**. Việc tự `trim()` có thể làm thay đổi dữ liệu trước khi tạo DN. Nếu nghiệp vụ muốn bỏ khoảng trắng đầu/cuối, hãy quy định và thực hiện bước chuẩn hóa **trước khi xây RDN**, không coi đó là tác dụng của escaping.

### 2.3. Hai cách escape được RFC 4514 hỗ trợ

Một ký tự thuộc nhóm đặc biệt có thể được escape bằng backslash ngay trước ký tự, ví dụ:

```text
cn=Nguyễn\, An
```

Một cách khác là biểu diễn **octet UTF-8** qua backslash và **hai chữ số hex**:

```text
cn=An\2CQA
```

Ở đây `2C` là byte hex của dấu phẩy `,` trong UTF-8/ASCII. Cả `cn=An\,QA` và `cn=An\2CQA` biểu diễn giá trị **`An,QA`** theo quy tắc DN.

**Đừng hiểu `\2C` là một dấu phẩy phân tách RDN.** Nó là byte đã được escape nằm bên trong giá trị attribute.

Các chữ số hex trong escape biểu diễn **octet**, không phải một số Unicode code point ở mọi trường hợp.

### 2.4. Dấu backslash có thêm một lớp nghĩa khi viết code Java

Cần phân biệt **DN text thực tế** với **chuỗi literal trong Java source**:

```text
DN text khi gửi tới LDAP parser:
cn=Nguyễn\, An,ou=people,dc=example,dc=org
```

```java
// Java source: dùng \\ để tạo một ký tự backslash thực.
String dnText =
    "cn=Nguyễn\\, An,ou=people,dc=example,dc=org";
```

Nếu viết `"\,"` trực tiếp trong Java source, chương trình sẽ gặp **illegal escape character**, vì Java không hỗ trợ `\,` như một escape của chính ngôn ngữ Java.

Đây là **hai tầng encoding khác nhau**:

1. `\\` trong Java string literal tạo **một ký tự backslash** trong đối tượng `String`.
2. `\,` trong DN text dùng **một ký tự backslash** đó để escape dấu phẩy theo RFC 4514.

Số lượng backslash khi xem *source code*, *debugger*, *JSON response* và *LDIF* có thể khác nhau vì mỗi lớp có cú pháp escaping riêng.

## 3. Unicode và DN: UTF-8, ký tự tiếng Việt và ký tự tổ hợp

LDAP DN không bị giới hạn ở ASCII. Giá trị RDN có thể chứa chữ có dấu và nhiều ký tự Unicode khác, ví dụ:

```text
cn=Nguyễn Ánh,ou=people,dc=example,dc=org
cn=Đặng Minh,ou=people,dc=example,dc=org
cn=Chloé Martin,ou=people,dc=example,dc=org
```

Trong cách biểu diễn DN dạng Unicode, ký tự hợp lệ không thuộc nhóm đặc biệt **không bắt buộc phải escape** chỉ vì nó khác ASCII. Khi truyền qua LDAP protocol, các ký tự được mã hóa theo **UTF-8** phù hợp cú pháp và quy tắc giao thức.

**Hai việc khác nhau:**

- Viết chữ `é` trực tiếp trong DN text.
- Viết các **byte UTF-8** tạo thành `é` dưới dạng hex escape.

### 3.1. Ví dụ Unicode dạng ký tự trực tiếp và hex octet

Chữ `é` có Unicode code point `U+00E9` và mã hóa UTF-8 gồm **hai byte**:

```text
Ký tự:      é
Code point: U+00E9
UTF-8:      C3 A9 (hex)

DN text Unicode:
cn=José,ou=people,dc=example,dc=org

DN text với UTF-8 octet escape:
cn=Jos\C3\A9,ou=people,dc=example,dc=org
```

Theo RFC 4514, các octet `\C3\A9` được giải mã thành chuỗi byte UTF-8 tương ứng với ký tự `é`. **Không được dùng `\E9` để biểu diễn trực tiếp code point U+00E9 theo suy đoán**, vì `E9` một mình **không phải một chuỗi UTF-8 hợp lệ cho ký tự này**.

Với nhiều ký tự Unicode khác, mỗi ký tự có thể chiếm 2, 3 hoặc 4 byte UTF-8. Nếu phải escape ở mức octet, hãy escape **từng byte của UTF-8**, không tự chuyển code point thành `\HH` theo giá trị số của nó.

### 3.2. Ví dụ người dùng tiếng Việt có dấu phẩy

Giá trị của attribute `cn` là:

```text
Nguyễn, An
```

DN text có thể viết:

```text
cn=Nguyễn\, An,ou=people,dc=example,dc=org
```

Ở đây:

- **`Nguyễn`** giữ nguyên Unicode.
- Dấu phẩy **trong `cn`** được escape bằng `\,`.
- Dấu phẩy **giữa các RDN** vẫn là ký hiệu phân tách như bình thường.

Không vì xuất hiện chữ có dấu mà tự escape cả dấu cách hoặc mọi byte Unicode. Chỉ cần biểu diễn đúng quy tắc, hoặc để API DN builder xử lý toàn bộ.

### 3.3. Unicode tổ hợp và normalization

Một ký tự hiển thị giống nhau có thể có nhiều cách biểu diễn Unicode. Ví dụ chữ `é`:

```text
NFC (composed):
é = U+00E9

Decomposed:
e + dấu sắc tổ hợp = U+0065 U+0301
```

Trong Java:

```java
import java.text.Normalizer;

String composed = "José";
String decomposed = "Jose\u0301";

System.out.println(composed.equals(decomposed));  // false

String nfc =
    Normalizer.normalize(decomposed, Normalizer.Form.NFC);

System.out.println(composed.equals(nfc));         // true
```

**Không đồng nhất Java `String.equals(...)` với LDAP DN equality.** Việc so khớp giá trị trong directory phụ thuộc LDAP attribute syntax, matching rule, normalization và implementation server. Một số tình huống Unicode có thể được xem là tương đương bởi matching rule, nhưng **không có quy tắc ứng dụng phổ quát** “mọi chuỗi nhìn giống nhau là cùng entry”.

Gợi ý thiết kế:

1. Với **DN do LDAP server trả về**, giữ và sử dụng giá trị thật của nó; không thay đổi Unicode theo phỏng đoán.
2. Với **tên mới do ứng dụng tạo**, nếu có chính sách chuẩn hóa Unicode (ví dụ NFC), áp dụng nhất quán **trước** khi tạo RDN và trước khi kiểm tra uniqueness.
3. Với **login ID**, không tự đổi NFC/NFKC, chữ hoa/thường hoặc bỏ dấu nếu chưa có quy tắc xác thực được directory và ứng dụng thống nhất.
4. Tránh dùng phép so sánh chuỗi hiển thị để kết luận hai DN chỉ tới cùng entry; khi cần danh tính bền vững, xem xét ID do directory thực sự bảo đảm.

### 3.4. Unicode có thể hợp lệ về cú pháp nhưng không hợp lệ theo nghiệp vụ

Một DN parse được có thể chứa:

- Dấu cách đặc biệt hoặc **non-breaking space**.
- Ký tự điều khiển hay ký tự vô hình.
- Ký tự có hình dạng gần giống chữ Latin (*confusable characters*).
- Dấu tổ hợp Unicode tạo chuỗi khó đọc.
- Emoji hoặc ký tự không thuộc tập đặt tên được tổ chức cho phép.

Đây **không tự động là LDAP injection**. Tuy nhiên, chúng có thể gây nhầm lẫn, giả mạo tên hiển thị, va chạm theo chính sách hoặc lỗi tích hợp. **Escaping chỉ bảo vệ cấu trúc DN**; còn quy tắc ký tự cho phép, độ dài, chuẩn hóa Unicode và quyền tạo entry là trách nhiệm riêng.

## 4. Parse DN bằng javax.naming.ldap.LdapName

JDK có interface `javax.naming.Name`, implementation `javax.naming.ldap.LdapName` và class `javax.naming.ldap.Rdn`.

Ví dụ đọc một DN chứa dấu phẩy được escape:

```java
import javax.naming.ldap.LdapName;
import javax.naming.ldap.Rdn;

public final class LdapNameReader {

    public static void main(String[] args) throws Exception {
        LdapName dn = new LdapName(
            "cn=Nguyễn\\, An,ou=people,dc=example,dc=org"
        );

        System.out.println(dn.size()); // 4

        Rdn leaf = dn.getRdn(dn.size() - 1);

        System.out.println(leaf.getType());  // cn
        System.out.println(leaf.getValue()); // Nguyễn, An
    }
}
```

Parser diễn giải `\,` là **một dấu phẩy trong value**, vì thế RDN cụ thể nhất có giá trị `Nguyễn, An`.

### 4.1. Thứ tự JNDI ngược chiều hiển thị văn bản

DN thường được viết từ **entry cụ thể nhất bên trái** tới phần gần gốc bên phải:

```text
cn=Nguyễn\, An,ou=people,dc=example,dc=org
^ leaf                                 ^ root-side
```

Nhưng `LdapName.get(0)` trả **component gần gốc nhất**:

```java
LdapName dn = new LdapName(
    "cn=Nguyễn\\, An,ou=people,dc=example,dc=org"
);

System.out.println(dn.get(0)); // dc=org
System.out.println(dn.get(1)); // dc=example
System.out.println(dn.get(2)); // ou=people

// Component cụ thể nhất nằm ở chỉ số n - 1.
System.out.println(dn.get(3)); // cn=Nguyễn\, An
```

**Không dùng `dn.get(0)` để lấy RDN của user.** Dùng `dn.getRdn(dn.size() - 1)` hoặc `dn.get(dn.size() - 1)` nếu cần RDN leaf.

### 4.2. LdapName parse đúng cú pháp không chứng minh entry tồn tại

`new LdapName(text)` chỉ xác minh tên có thể được diễn giải theo cú pháp LDAP DN của JNDI. Nó **không**:

- Mở kết nối và tìm entry trên server.
- Kiểm tra `objectClass` hay các attribute bắt buộc.
- Xác minh giá trị `uid` có thuộc naming rule được directory cho phép.
- Kiểm tra bind principal có quyền đọc/ghi.
- Bảo đảm DN nằm trong nhánh được ứng dụng cấp quyền.
- Bảo đảm không trùng với entry hiện tại.

Ví dụ một DN `uid=unknown,ou=people,dc=example,dc=org` vẫn parse được dù server chưa hề có entry nào như vậy.

## 5. Xây RDN an toàn bằng javax.naming.ldap.Rdn

Để xây DN từ dữ liệu động, hãy sử dụng **cấu trúc type/value**, không coi input là một đoạn cú pháp DN.

### 5.1. Đừng nối chuỗi từ giá trị RDN

Ví dụ input người dùng:

```text
qa,ou=admins
```

Không nên làm:

```java
String loginId = "qa,ou=admins";

String dnText =
    "uid=" + loginId + ",ou=people,dc=example,dc=org";
```

Kết quả sẽ có dạng:

```text
uid=qa,ou=admins,ou=people,dc=example,dc=org
```

Ở đây ký tự `,` và `=` của input bị hiểu thành **RDN mới `ou=admins`**, khiến **cấu trúc DN khác ý định**. Đây là một biến thể của lỗi **DN construction/injection**.

Đúng hơn, hãy coi toàn bộ `qa,ou=admins` là **giá trị của attribute `uid`**:

```java
import javax.naming.ldap.Rdn;

String loginId = "qa,ou=admins";

Rdn userRdn = new Rdn("uid", loginId);

System.out.println(userRdn);
// uid=qa\,ou\=admins
```

Ký tự `,` và `=` giờ được biểu diễn như **dữ liệu trong giá trị**, không phải là ranh giới tên.

**Lưu ý:** Việc một username chứa dấu phẩy/dấu bằng được **escape đúng cú pháp** không có nghĩa hệ thống nên cho phép username đó. Quy tắc đặt tên nghiệp vụ cần kiểm tra riêng.

### 5.2. Tạo DN đầy đủ từ danh sách Rdn

```java
import java.util.List;

import javax.naming.ldap.LdapName;
import javax.naming.ldap.Rdn;

public final class FullDnFactory {

    public static LdapName userDn(String loginId)
            throws Exception {

        return new LdapName(List.of(
            new Rdn("dc", "org"),
            new Rdn("dc", "example"),
            new Rdn("ou", "people"),
            new Rdn("uid", loginId)
        ));
    }
}
```

Khi `loginId = "qa,ou=admins"`, `Rdn` sẽ mã hóa ký tự đặc biệt trong **giá trị `uid`**, bảo toàn cấu trúc gồm 4 RDN.

**Cẩn thận thứ tự:** Constructor `new LdapName(List<Rdn>)` nhận danh sách theo thứ tự **gần gốc tới leaf**. Vì vậy `dc=org` đứng đầu danh sách và `uid=...` đứng cuối. Trong chuỗi DN được xuất ra, thứ tự đọc lại là `uid=...,ou=people,dc=example,dc=org`.

### 5.3. Rdn.escapeValue và Rdn.unescapeValue

Java còn cung cấp các helper:

```java
import javax.naming.ldap.Rdn;

String raw = "Nguyễn, An + QA";
String encoded = Rdn.escapeValue(raw);
Object decoded = Rdn.unescapeValue(encoded);

System.out.println(encoded);
// Có các escape cần thiết cho dấu phẩy và dấu cộng.

System.out.println(decoded);
// Nguyễn, An + QA
```

Các helper này **dành cho giá trị RDN**, không phải để escape toàn bộ DN hoàn chỉnh hoặc LDAP filter.

Một vài cảnh báo:

- `escapeValue(...)` có thể xuất một cách biểu diễn hợp lệ mà **khác chính tả escape** bạn tự dự đoán. Không nên viết test chỉ so sánh chuỗi với một kiểu formatting quá cụ thể khi ngữ nghĩa mới là điều quan trọng.
- `unescapeValue(...)` trả về `Object`. Trong trường hợp cú pháp thể hiện dữ liệu nhị phân, giá trị có thể là dạng khác `String`; đừng luôn ép kiểu.
- Với DN hoàn chỉnh, dùng `LdapName`; với giá trị RDN riêng lẻ, dùng `Rdn`/helper tương ứng.

## 6. LdapNameBuilder trong Spring LDAP

Spring LDAP cung cấp `org.springframework.ldap.support.LdapNameBuilder` để tạo DN từ các thành phần an toàn hơn và ít nhầm thứ tự.

### 6.1. Tạo DN tương đối với một base DN

Giả sử `ContextSource` có base:

```text
dc=example,dc=org
```

Lúc này nhiều API `LdapTemplate` nhận DN **tương đối với base**.

```java
import javax.naming.Name;

import org.springframework.ldap.support.LdapNameBuilder;

public final class RelativeDnFactory {

    public static Name userRelativeDn(String loginId) {
        return LdapNameBuilder
            .newInstance("ou=people")
            .add("uid", loginId)
            .build();
    }
}
```

Nếu `loginId = "an,qa"`, DN tương đối biểu diễn:

```text
uid=an\,qa,ou=people
```

Dấu phẩy trong `loginId` không tạo thêm RDN. `LdapNameBuilder.add("uid", loginId)` nhận một **attribute type cố định** và **giá trị**; builder chịu trách nhiệm biểu diễn giá trị đúng cú pháp DN.

### 6.2. Tạo DN đầy đủ có Unicode và dấu cộng

```java
Name fullDn = LdapNameBuilder
    .newInstance("dc=example,dc=org")
    .add("ou", "people")
    .add("cn", "Nguyễn, An + QA")
    .build();

System.out.println(fullDn);
// cn=Nguyễn\, An \+ QA,ou=people,dc=example,dc=org
```

Về ngữ nghĩa, `cn` chứa đúng giá trị `Nguyễn, An + QA`. Dù thư viện chọn cách escape bằng ký tự hoặc octet hex, việc parse lại DN phải giữ nguyên cấu trúc và giá trị.

### 6.3. Tại sao builder không thay thế kiểm tra input?

Builder bảo vệ **cấu trúc DN**. Ứng dụng vẫn phải kiểm tra:

- `loginId` có rỗng, quá dài hoặc chứa ký tự bị chính sách cấm không?
- Attribute type có thuộc **allowlist** không (ví dụ `uid` hoặc `cn`)?
- Entry dự định tạo có nằm đúng OU được caller phép quản lý không?
- DN mới có trùng với entry khác không?
- Server có cho phép RDN và `objectClass` đó không?
- Người gọi có quyền create/rename/bind theo nghiệp vụ không?

Không nhận cả một chuỗi DN hoàn chỉnh do client gửi rồi giả định chỉ vì `new LdapName(...)` parse được thì giá trị đã “được escape an toàn”.

## 7. RDN đa trị và ký tự dấu cộng

Một RDN đa trị chứa **nhiều attribute-value assertion** trong **một component**, phân tách bằng dấu cộng `+`.

Ví dụ:

```text
cn=Nguyễn\, An+uid=an.nguyen,ou=people,dc=example,dc=org
```

RDN đầu tiên có hai cặp type/value, nhưng DN vẫn có **4 RDN**.

### 7.1. Tạo RDN đa trị có dữ liệu đặc biệt

```java
import java.util.List;

import javax.naming.directory.Attributes;
import javax.naming.directory.BasicAttributes;
import javax.naming.ldap.LdapName;
import javax.naming.ldap.Rdn;

public final class MultiValuedRdnExample {

    public static LdapName build() throws Exception {
        Attributes attributes = new BasicAttributes(true);

        attributes.put("cn", "Nguyễn, An");
        attributes.put("uid", "an+qa");

        Rdn namingRdn = new Rdn(attributes);

        return new LdapName(List.of(
            new Rdn("dc", "org"),
            new Rdn("dc", "example"),
            new Rdn("ou", "people"),
            namingRdn
        ));
    }
}
```

`Rdn(attributes)` tạo **một RDN chứa hai cặp**; nó không biến dấu `+` nằm trong giá trị `an+qa` thành dấu phân tách, vì đã nhận giá trị qua cấu trúc JNDI.

Đọc một RDN đa trị:

```java
LdapName dn = MultiValuedRdnExample.build();

Rdn leaf = dn.getRdn(dn.size() - 1);

System.out.println(leaf.size());        // 2
System.out.println(leaf.toAttributes()); // cn và uid
```

**Không dựa vào thứ tự in ra của các assertion** trong RDN đa trị để xác định danh tính. Nếu cần kiểm tra từng type/value, dùng `leaf.toAttributes()` thay vì chỉ nhìn vào `leaf.getType()`/`getValue()` rồi giả định RDN chỉ có một cặp.

### 7.2. Không nên dùng regex tách dấu +

Dòng:

```text
cn=R\+D+uid=an\+qa,ou=people,dc=example,dc=org
```

có hai dấu cộng được escape (nằm trong value) và một dấu cộng không escape (phân tách assertion). Một phép `split("\\+")` bằng regex Java trên văn bản DN sẽ không đủ vì còn phụ thuộc số backslash, escaping hex và các cú pháp hợp lệ khác.

**Dùng `LdapName` và `Rdn` để phân tích**, không tự xây parser bằng `split(",")`, `split("+")` hoặc regex đơn giản.

## 8. DN escaping khác LDAP search filter escaping

Đây là một trong những nhầm lẫn bảo mật quan trọng nhất khi dùng Spring Data LDAP.

**DN** chỉ định **tên/vị trí** của entry. **LDAP filter** là biểu thức **điều kiện truy vấn**. Hai chuỗi dùng hai quy tắc escaping khác nhau:

| Mục đích | Chuẩn | Ví dụ API |
| --- | --- | --- |
| Xây DN/RDN | **RFC 4514** | `Rdn`, `LdapName`, `LdapNameBuilder` |
| Xây LDAP search filter | **RFC 4515** | `LdapQueryBuilder.where("uid").is(value)` |
| Đặt DN trong Java source | Java language escaping | `"cn=An\\, QA,..."` |
| Ghi DN vào LDIF | **RFC 2849** cộng quy tắc DN | `dn:` hoặc `dn::` |
| Ghi DN trong YAML | YAML quoting cộng quy tắc DN | Single quotes hoặc escape đúng double quotes |

### 8.1. Cùng một input phải đi qua đúng API của ngữ cảnh

Giả sử username nhập là:

```text
an*(qa)
```

Nếu xây DN theo naming convention `uid=<loginId>`, hãy dùng:

```java
Name relativeDn = LdapNameBuilder
    .newInstance("ou=people")
    .add("uid", loginId)
    .build();
```

Nếu tìm người dùng theo attribute `uid`, hãy dùng:

```java
import java.util.List;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;

import static org.springframework.ldap.query.LdapQueryBuilder.query;

public final class UserSearchExample {

    private final LdapTemplate ldapTemplate;

    public UserSearchExample(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<String> findCommonNames(String loginId) {
        return ldapTemplate.search(
            query()
                .base("ou=people")
                .attributes("cn")
                .where("uid").is(loginId),
            (AttributesMapper<String>) attributes ->
                (String) attributes.get("cn").get()
        );
    }
}
```

`where("uid").is(loginId)` xử lý giá trị như **filter assertion value**. Đừng viết:

```java
// KHÔNG NÊN: có thể tạo filter khác ý định hoặc LDAP injection.
String filter = "(uid=" + loginId + ")";
```

Ví dụ ký tự `*` trong filter biểu thị wildcard/trường hợp presence khi không được escape, trong khi nó không phải dấu phân tách RDN theo cách giống dấu phẩy. Vì vậy:

- Đúng cú pháp DN **không đồng nghĩa** đúng cú pháp filter.
- Escape bằng `Rdn.escapeValue(loginId)` rồi đưa vào filter **không phải cách an toàn được khuyến nghị**.
- Escape bằng hàm filter rồi dùng nó làm giá trị RDN **cũng sai lớp cú pháp**.

### 8.2. Tìm group theo member là một bài toán hai tầng

Với `groupOfNames`, attribute `member` lưu **full DN** của user:

```text
member: uid=an\,qa,ou=people,dc=example,dc=org
```

Để tìm group trực tiếp chứa user đó:

```java
import javax.naming.Name;
import org.springframework.ldap.query.LdapQuery;

import static org.springframework.ldap.query.LdapQueryBuilder.query;

public final class GroupFilterFactory {

    public static LdapQuery byMember(Name userFullDn) {
        return query()
            .base("ou=groups")
            .where("objectClass").is("groupOfNames")
            .and("member").is(userFullDn.toString());
    }
}
```

Ở đây có **hai bước tách biệt**:

1. `userFullDn` được xây hoặc lấy như một **LDAP DN hợp lệ** (RFC 4514).
2. `where("member").is(...)` đặt DN vào **giá trị của filter**, được filter builder xử lý theo RFC 4515.

Không nội suy `userFullDn` vào `"(member=" + dn + ")"`; DN có thể chứa dấu gạch chéo ngược và những ký tự khiến filter phải escape khác với DN.

## 9. DN có Unicode trong LDIF và application.yml

### 9.1. LDIF có một lớp encoding riêng

LDIF là định dạng văn bản biểu diễn entry và các thay đổi LDAP (RFC 2849). Cú pháp DN phải đúng **RFC 4514**, nhưng việc ghi dòng vào **LDIF** còn phải tuân thủ quy tắc biểu diễn giá trị.

Ví dụ DN ASCII với dấu phẩy nằm trong giá trị RDN:

```ldif
dn: cn=An\, QA,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
cn: An, QA
sn: QA
```

Trong LDIF, hai dấu phẩy ở dòng DN có vai trò khác nhau:

- `\,` là dấu phẩy trong **giá trị RDN**.
- `,ou=people` và `,dc=...` phân tách các RDN.

**Với Unicode non-ASCII**, theo yêu cầu biểu diễn LDIF chuẩn, giá trị chứa octet không an toàn cần được xuất **base64** bằng `::` thay vì luôn ghi ký tự Unicode thẳng sau `dn:`:

```text
dn:: <base64 của UTF-8 DN text>
```

Dòng `dn::` phía trên chỉ là mô tả cú pháp, **không phải một entry LDIF có thể import ngay**. Để tạo giá trị base64 chính xác bằng Java:

```java
import java.nio.charset.StandardCharsets;
import java.util.Base64;

String dnText =
    "cn=Nguyễn\\, An,ou=people,dc=example,dc=org";

String encoded = Base64.getEncoder().encodeToString(
    dnText.getBytes(StandardCharsets.UTF_8)
);

System.out.println("dn:: " + encoded);
```

**Cần phân biệt hai loại mã hóa:**

- `\` trong DN text bảo vệ **cấu trúc DN** (ví dụ dấu phẩy là một phần giá trị).
- Base64 trong LDIF bảo vệ **biểu diễn dòng chứa octet không an toàn**.

Base64 **không thay thế** DN escaping. Nếu DN text đã sai cấu trúc, đem nó đi base64 chỉ bảo toàn một **DN sai**.

### 9.2. YAML và dấu backslash

Khi đặt DN có backslash escape trong `application.yml`, cần nhớ **YAML double-quoted string có quy tắc escape riêng**. Ví dụ đơn giản, có thể dùng **single quotes** để giữ nguyên backslash DN:

```yaml
app:
  ldap:
    example-user-dn: 'cn=An\, QA,ou=people,dc=example,dc=org'
```

Giá trị sau khi YAML parser đọc vẫn chứa ký tự `\` đứng trước dấu phẩy.

Tránh viết `"cn=An\, QA,..."` trong YAML double quotes một cách tùy tiện, bởi `\,` **không phải YAML double-quoted escape hợp lệ** trong nhiều parser. Nếu bắt buộc dùng double quotes, phải encode backslash theo đúng quy tắc YAML.

**Đừng nhầm namespace cấu hình:** `app.ldap.example-user-dn` chỉ là property minh họa do ứng dụng tự định nghĩa; Spring Boot dùng nhóm property kết nối tiêu chuẩn `spring.ldap.*` cho URL, base DN, bind DN và password.

### 9.3. JSON, URL và shell còn có quy tắc riêng

Nếu DN xuất hiện trong JSON, URL hoặc lệnh shell:

- JSON string escape backslash theo cú pháp JSON; DN escaping không tự xử lý lớp này.
- URL có percent-encoding; đừng dùng percent-encoding thay cho escape RDN.
- Shell có quoting/expansion; đừng ghép DN raw vào shell command từ input.
- LDIF dòng `dn::` không phải ký pháp DNS hay phần của `javax.naming.Name`.

Một tên có thể trải qua nhiều lớp encoding, nhưng **mỗi lớp cần được xử lý tại đúng ranh giới**, chỉ một lần và bằng đúng bộ mã hóa của lớp đó.

## 10. DN đầy đủ, DN tương đối và kiểm tra nhánh bằng Name

Giả sử:

```text
ContextSource base:
dc=example,dc=org

DN đầy đủ:
cn=Nguyễn\, An,ou=people,dc=example,dc=org

DN tương đối với base:
cn=Nguyễn\, An,ou=people
```

Spring LDAP `LdapTemplate` thường nhận **relative DN** với cấu hình `ContextSource`. Ngược lại, attribute `groupOfNames.member` thường lưu **full DN** của user.

### 10.1. Tách DN tương đối an toàn

```java
import javax.naming.Name;
import javax.naming.ldap.LdapName;

public final class RelativeDnConverter {

    public static Name belowBase(Name fullDn, Name base) {
        if (fullDn == null || base == null
                || !fullDn.startsWith(base)) {
            throw new IllegalArgumentException(
                "DN is not below configured base"
            );
        }

        return fullDn.getSuffix(base.size());
    }

    public static void main(String[] args) throws Exception {
        Name base = new LdapName("dc=example,dc=org");
        Name full = new LdapName(
            "cn=Nguyễn\\, An,ou=people,dc=example,dc=org"
        );

        System.out.println(belowBase(full, base));
        // cn=Nguyễn\, An,ou=people
    }
}
```

`Name.startsWith(base)` kiểm tra **component gần gốc** theo thứ tự JNDI (root-first); nó không phải phép `String.startsWith(...)` trên chuỗi DN. Với tên có cấu trúc, `getSuffix(base.size())` trả phần còn lại cụ thể hơn.

**Không dùng `String.endsWith("dc=example,dc=org")` để làm authorization check**: chuỗi có thể có escape/case/biểu diễn tương đương khác nhau và không phản ánh chính xác ranh giới component. Việc DN nằm dưới base là **một điều kiện cần**, không thay thế quyền của caller đối với entry đó.

### 10.2. Lookup một entry có dấu phẩy trong RDN

```java
import javax.naming.Name;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

public final class LdapLookupExample {

    private final LdapTemplate ldapTemplate;

    public LdapLookupExample(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public String lookupName(String commonName) {
        Name relative = LdapNameBuilder
            .newInstance("ou=people")
            .add("cn", commonName)
            .build();

        return ldapTemplate.lookup(
            relative,
            (AttributesMapper<String>) attributes ->
                (String) attributes.get("cn").get()
        );
    }
}
```

Gọi `lookupName("Nguyễn, An")` sẽ tạo DN có **một RDN leaf `cn`**, với dấu phẩy được escape đúng.

Tuy nhiên, **chỉ nên lookup bằng DN suy ra** khi naming convention được bảo đảm. Nếu thực thể có RDN `uid` nhưng attribute `cn` vẫn là `Nguyễn, An`, phải **search theo `cn` để tìm DN thật**, không dựng DN `cn=...` rồi giả định entry tồn tại.

## 11. So sánh DN và định danh trong Spring Data LDAP

Một entity LDAP có thể ánh xạ:

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
    private String loginId;

    @Attribute(name = "cn")
    private String commonName;

    @Attribute(name = "sn")
    private String surname;

    public PersonEntry() {}

    public Name getDn() { return dn; }
    public String getLoginId() { return loginId; }
    public String getCommonName() { return commonName; }
}
```

Repository:

```java
import java.util.List;

import org.springframework.data.ldap.repository.LdapRepository;

public interface PersonRepository
        extends LdapRepository<PersonEntry> {

    List<PersonEntry> findByLoginId(String loginId);
}
```

Phân biệt:

- `@Id Name dn`: **DN của entry**, không phải một cột primary key số hay ID LDAP bất biến suốt vòng đời.
- `@Attribute(name = "uid")`: ánh xạ attribute LDAP `uid` sang property Java `loginId`.
- `@Entry(base = "ou=people")`: vùng entry so với base của `ContextSource`.
- `findByLoginId(...)`: tìm theo property Java, sau đó ánh xạ thành LDAP filter theo `uid`; **không phải** parse chuỗi input thành DN.

Nếu user được rename/move, `dn` có thể đổi dù ID người dùng nghiệp vụ không đổi. Ngược lại, `uid` có thể đổi do rename account. Khi cần key ổn định, dùng ID do directory/ứng dụng bảo đảm thật sự (ví dụ `entryUUID` hoặc `objectGUID` theo server), không lấy DN text chỉ vì nó có vẻ duy nhất.

### 11.1. Cú pháp được escape đúng không chứng minh schema cho phép

Một tên có dạng:

```text
uid=an\,qa,ou=people,dc=example,dc=org
```

có thể parse đúng, nhưng LDAP server vẫn có quyền từ chối:

- Username không hợp quy tắc đặt tên của tổ chức.
- `uid` không được schema của loại entry cho phép làm RDN trong ngữ cảnh đó.
- Parent `ou=people` không tồn tại.
- Entry đã tồn tại hoặc account thiếu quyền Add/ModifyDN.
- `objectClass` yêu cầu những attribute khác (ví dụ `cn` và `sn` với `inetOrgPerson`).
- ACL không cho đọc hoặc bind vào entry.

**Escape đúng DN không đồng nghĩa CRUD thành công.** Cần kiểm thử trên directory thật với schema/ACL tương ứng.

## 12. Những lỗi thường gặp khi escape DN và Unicode

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| `InvalidNameException` khi tên có dấu phẩy | Nối raw input vào DN, dấu phẩy thành separator | Dùng `Rdn`/`LdapNameBuilder` với type/value |
| DN có thêm OU ngoài dự kiến | Input `an,ou=admins` bị diễn giải là đoạn DN | Không nối chuỗi; dùng builder và kiểm tra nhánh |
| Mất dấu `+` trong tên | Dấu cộng chưa escape thành phân tách RDN đa trị | Dùng `new Rdn("cn", value)` |
| Tên có khoảng trắng đầu/cuối bị đổi | Ứng dụng `trim()` hoặc DN text không escape vị trí | Quy định chính sách chuẩn hóa; builder bảo toàn cấu trúc |
| Giá trị bắt đầu bằng `#` parse sai | Không escape ký tự ở đầu value | Dùng `Rdn`; ví dụ `cn=\#team` |
| Tên chứa backslash parse sai | Một lớp escape bị mất ở Java/YAML/JSON | Kiểm tra từng ranh giới; viết test round-trip |
| Unicode bị lỗi dấu hoặc ký tự thay thế | Dùng encoding khác UTF-8 hoặc xử lý octet sai | Dùng UTF-8, không đoán `\HH` từ code point |
| Hai tên nhìn giống nhau nhưng không khớp | Unicode normalization, case/matching rule khác | Kiểm tra dữ liệu gốc và matching rule của server |
| Parse DN thành công nhưng lookup không thấy | Schema, base/OU, ACL hoặc entry không tồn tại | Đọc DN thực, kiểm tra server thay vì sửa escape tùy tiện |
| `cn=...` lookup sai user | RDN thật dùng `uid` hoặc user đã move | Search theo attribute, lấy DN trả về |
| DN trong filter gây LDAP injection | Dùng DN escaping cho filter hoặc nối raw filter | Dùng `LdapQueryBuilder.where(...).is(value)` |
| YAML không load do `\,` | Dùng backslash DN trong YAML double quotes | Dùng single quotes hoặc escape theo YAML |
| LDIF với DN Unicode bị từ chối | Không tuân thủ encoding/base64 trong LDIF | Dùng `dn::` đúng UTF-8 base64 theo RFC 2849 |
| Group `member` không khớp sau rename | Full DN của user đã thay đổi | Đối soát DN-valued references và cache |
| Dùng `split(",")` ra sai số RDN | Dấu phẩy escaped là dữ liệu | Dùng `LdapName` và `getRdns()` |

## 13. Kiểm thử đơn vị cho ký tự đặc biệt và Unicode

JDK DN parser/builder có thể được kiểm tra bằng **unit test** mà không cần kết nối LDAP.

### 13.1. Bộ kiểm thử JUnit 5

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import javax.naming.Name;
import javax.naming.ldap.LdapName;
import javax.naming.ldap.Rdn;

import org.junit.jupiter.api.Test;
import org.springframework.ldap.support.LdapNameBuilder;

class DistinguishedNameEscapingTest {

    private static LdapName build(String cn) throws Exception {
        Name name = LdapNameBuilder
            .newInstance("dc=example,dc=org")
            .add("ou", "people")
            .add("cn", cn)
            .build();

        return new LdapName(name.toString());
    }

    @Test
    void commaAndPlusStayInsideTheLeafValue() throws Exception {
        String raw = "Nguyễn, An + QA";

        LdapName dn = build(raw);

        assertEquals(4, dn.size());
        assertEquals(
            raw,
            dn.getRdn(dn.size() - 1).getValue()
        );
    }

    @Test
    void leadingAndTrailingSpacesRoundTrip() throws Exception {
        String raw = " An ";

        LdapName dn = build(raw);

        assertEquals(
            raw,
            dn.getRdn(dn.size() - 1).getValue()
        );
    }

    @Test
    void hashAndBackslashArePreserved() throws Exception {
        String raw = "#ops\\qa";

        LdapName dn = build(raw);

        assertEquals(
            raw,
            dn.getRdn(dn.size() - 1).getValue()
        );
    }

    @Test
    void hexEscapedUtf8CanBeDecoded() throws Exception {
        LdapName dn = new LdapName(
            "cn=Jos\\C3\\A9,ou=people,dc=example,dc=org"
        );

        assertEquals(
            "José",
            dn.getRdn(dn.size() - 1).getValue()
        );
    }

    @Test
    void dangerousLookingInputDoesNotCreateExtraRdn()
            throws Exception {

        String raw = "qa,ou=admins";

        LdapName dn = build(raw);

        assertEquals(4, dn.size());
        assertEquals(
            raw,
            dn.getRdn(dn.size() - 1).getValue()
        );

        assertTrue(dn.startsWith(
            new LdapName("dc=example,dc=org")
        ));
    }
}
```

Vì test kiểm tra **giá trị parse lại**, nó không phụ thuộc cứng vào việc implementation in dấu phẩy theo `\,` hay một dạng hex escape tương đương.

### 13.2. Test Java string escaping và ký tự literal

Có thể bổ sung test phân biệt:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import javax.naming.ldap.LdapName;
import org.junit.jupiter.api.Test;

class DnLiteralTest {

    @Test
    void javaLiteralNeedsDoubleBackslash() throws Exception {
        String dnText =
            "cn=An\\, QA,ou=people,dc=example,dc=org";

        LdapName dn = new LdapName(dnText);

        assertEquals(
            "An, QA",
            dn.getRdn(dn.size() - 1).getValue()
        );
    }
}
```

Những test này xác minh **parser/builder trong JVM**. Chúng **không** kiểm tra permission, tính tồn tại entry, schema hay cách LDAP server xử lý Unicode matching. Các điều đó cần integration test.

## 14. Kiểm thử tích hợp trên directory

Dựng một LDAP server test có base `dc=example,dc=org` và OU `ou=people`. Seed bằng dữ liệu giả, TLS/ACL phù hợp, không thao tác trên production.

### 14.1. Kiểm thử những gì?

| Tình huống | Kết quả cần xác minh |
| --- | --- |
| Tạo entry với `cn` chứa dấu phẩy | DN leaf có **một RDN**, lookup theo DN tạo bởi builder thành công |
| Dấu cộng trong `cn` | Không bị biến thành RDN đa trị ngoài ý định |
| Giá trị có dấu `\` hoặc `"` | Round-trip đúng giá trị; không lỗi cú pháp |
| Leading/trailing space | Giá trị bảo toàn hoặc bị chính sách nghiệp vụ từ chối **có chủ đích** |
| `#` đầu value | Được escape; không bị diễn giải sai |
| Chữ tiếng Việt có dấu | UTF-8 đọc/ghi đúng, không bị mojibake |
| Unicode composed/decomposed | Ghi nhận matching behavior thực tế của server, không suy từ Java equals |
| Username chứa dấu phẩy và dấu bằng | Builder không cho phép chèn OU/RDN ngoài ý định |
| LDIF có Unicode | Export/import bằng `dn::` đúng theo RFC 2849 khi cần |
| Filter tìm theo `cn` và `uid` | Dùng escaping của RFC 4515, tìm đúng entry |
| `member` trỏ tới DN Unicode | Group lookup theo DN thực khớp |
| Rename/move entry có ký tự đặc biệt | DN cũ/mới đúng; refs/group được đối soát |
| Account thiếu quyền Add/Read | Server từ chối thích hợp; không coi là lỗi escaping |
| Server có schema hạn chế ký tự | Phân biệt lỗi naming policy/schema với parser DN |

### 14.2. Ví dụ tạo một entry có dấu phẩy trong DN

Dùng `LdapTemplate` và builder để tạo DN tương đối. **Trước khi chạy phải có `ou=people`**, account được quyền Add và đúng object classes/attributes:

```java
import javax.naming.Name;
import javax.naming.directory.Attributes;
import javax.naming.directory.BasicAttributes;

import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

public final class SeedSpecialDnEntry {

    private final LdapTemplate ldapTemplate;

    public SeedSpecialDnEntry(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public Name createSample() {
        Name relativeDn = LdapNameBuilder
            .newInstance("ou=people")
            .add("cn", "Nguyễn, An")
            .build();

        Attributes attrs = new BasicAttributes(true);

        attrs.put("objectClass", "top");
        attrs.get("objectClass").add("person");
        attrs.get("objectClass").add("organizationalPerson");
        attrs.get("objectClass").add("inetOrgPerson");

        attrs.put("cn", "Nguyễn, An");
        attrs.put("sn", "Nguyễn");
        attrs.put("uid", "an.nguyen");

        ldapTemplate.bind(relativeDn, null, attrs);

        return relativeDn;
    }
}
```

Ví dụ cố ý dùng `BasicAttributes(true)` để tên attribute không phụ thuộc hoa/thường trong JNDI. Đây là một entry thử nghiệm minh họa; kiểm tra naming rules, objectClass chain và schema cụ thể trước khi seed.

**Phải đọc lại entry theo `relativeDn`**, xác minh giá trị `cn`, `sn` và không tạo nhầm OU. Không dùng dữ liệu người thật hay quyền admin production để thực hành.

### 14.3. Đối chiếu với client ldapsearch

Trong môi trường test, có thể tìm theo attribute `cn` bằng LDAP filter:

```bash
ldapsearch -LLL -x \
  -H "ldaps://ldap.example.org:636" \
  -D "uid=ldap-reader,ou=service,dc=example,dc=org" -W \
  -b "ou=people,dc=example,dc=org" \
  "(cn=Nguyễn, An)" dn cn sn
```

**Dấu phẩy trong filter value không phải dấu phân tách RDN**, vì filter có cú pháp riêng. Khi dùng filter trên các giá trị có `*`, `(`, `)` hoặc backslash, phải dùng filter escaping đúng; không tự suy từ cách viết DN.

Chữ Unicode trong tham số shell yêu cầu terminal/locale và client hỗ trợ UTF-8 đúng. Nếu CLI và Java có kết quả khác, kiểm tra mã hóa đầu vào, bind principal, base, ACL và cú pháp filter ở từng client.

### 14.4. Đối chiếu kết quả trong Spring Data LDAP

Khi tích hợp repository/ODM:

1. Dùng `LdapTemplate` hoặc repository tìm user theo attribute `cn` hoặc `uid`.
2. Lấy `@Id Name dn` được mapper trả về.
3. Parse `Name` (nếu cần) và kiểm tra `Rdn.getValue()` giữ đúng Unicode/dấu phẩy.
4. Kiểm tra đường dẫn DN tương đối so với `ContextSource.base`.
5. Thử lookup lại entry bằng **DN thực**, không tự ghép từ tên hiển thị.
6. Với rename/move, xác minh entry mới có ở DN đích và tham chiếu DN trong các nhóm được cập nhật theo khả năng server.

Đối với username có dấu đặc biệt, kiểm thử **cả phía xây DN và phía xây filter**: pass ở một lớp không bảo đảm lớp còn lại đúng.

## 15. Bài tập tự kiểm tra

Giả sử `ContextSource` có base DN `dc=example,dc=org`.

**Câu A.** Người dùng có `cn` là `"Nguyễn, An"`. Hãy viết DN đầy đủ theo cú pháp RFC 4514 khi entry ở `ou=people`.

**Câu B.** Giá trị `cn` là `"R+D"`. Nếu không escape `+` thì parser có thể hiểu sai điều gì?

**Câu C.** Chuỗi Java nào tạo DN text thực tế `cn=An\, QA,ou=people,dc=example,dc=org`?

**Câu D.** Chữ `é` là U+00E9, UTF-8 là `C3 A9`. Vì sao `\C3\A9` là đúng còn `\E9` không phải biểu diễn UTF-8 đầy đủ của chữ này?

**Câu E.** Vì sao `"cn= An "` không nên được coi là tương đương chắc chắn với `"cn=An"`?

**Câu F.** Tên user được nhập là `"qa,ou=admins"`. Cách nào an toàn hơn: nối chuỗi vào `uid=...` hay dùng `new Rdn("uid", loginId)`?

**Câu G.** Khi muốn search theo `uid`, có thể dùng `Rdn.escapeValue(loginId)` rồi nối vào `"(uid=" + ... + ")"` không?

**Câu H.** Khi ghi DN chứa chữ tiếng Việt vào LDIF chuẩn, vì sao có thể cần `dn::` dù DN text đã escape dấu phẩy đúng?

**Câu I.** Trong JNDI `LdapName`, `get(0)` của `cn=An\, QA,ou=people,dc=example,dc=org` là gì?

### Gợi ý đáp án

- **A:** `cn=Nguyễn\, An,ou=people,dc=example,dc=org`.
- **B:** `+` không escape phân tách các assertion của **một RDN đa trị**, thay vì là dấu cộng trong `cn`. Dùng `cn=R\+D`.
- **C:** Java literal `"cn=An\\, QA,ou=people,dc=example,dc=org"` có hai backslash ở source để tạo một backslash trong DN text.
- **D:** `\HH` escape từng **octet UTF-8**. `é` cần hai octet `C3 A9`; một byte `E9` không đủ.
- **E:** Khoảng trắng đầu/cuối có ý nghĩa dữ liệu; nếu muốn loại bỏ, đó là chính sách chuẩn hóa riêng. Không mặc định `trim()` là một bước escaping.
- **F:** `new Rdn("uid", loginId)` hoặc `LdapNameBuilder.add("uid", loginId)`, vì toàn bộ input là **giá trị**, không thể tự tạo OU mới.
- **G:** Không. DN escaping và filter escaping khác nhau; dùng `LdapQueryBuilder.where("uid").is(loginId)`.
- **H:** `RFC 2849` yêu cầu mã hóa an toàn các octet không ASCII trong LDIF; base64 là lớp biểu diễn LDIF, còn dấu `\` là lớp DN.
- **I:** `get(0)` là `dc=org` (component gần gốc), không phải leaf `cn`.

## 16. Ghi nhớ cốt lõi

- **RFC 4514** quy định cách biểu diễn DN: dấu phẩy, dấu cộng, dấu backslash, ký tự đặc biệt khác và các trường hợp **leading/trailing space, leading #, NUL** cần escape phù hợp.
- **Unicode hợp lệ có thể xuất hiện trực tiếp trong DN text**; khi escape theo hex, phải dùng **từng octet UTF-8** chứ không đoán từ code point.
- **`javax.naming.ldap.Rdn`, `LdapName` và `LdapNameBuilder`** giúp thao tác DN có cấu trúc, tránh sai do nối chuỗi/split text.
- **DN escaping ≠ LDAP filter escaping**. Với search, dùng `LdapQueryBuilder` hoặc cơ chế binding filter tương ứng.
- **Java, YAML, JSON và LDIF** còn có lớp biểu diễn riêng; hãy encode/escape ở đúng ranh giới, tránh double-escaping hoặc thiếu escaping.
- **Parse thành công chưa đủ**: LDAP server vẫn kiểm tra schema, ACL, naming rule, DN tồn tại và matching rule Unicode.
- Với Spring Data LDAP, phân biệt **DN đầy đủ**, **DN tương đối**, **`@Id Name`** và **attribute Java được ánh xạ**; kiểm thử cả builder/parser lẫn thao tác directory thực.

## Tài liệu tham khảo

1. [RFC 4514 — LDAP: String Representation of Distinguished Names](https://www.rfc-editor.org/rfc/rfc4514.html) — cú pháp DN, escaping ký tự và octet UTF-8.
2. [RFC 4512 — LDAP: Directory Information Models](https://www.rfc-editor.org/rfc/rfc4512.html) — DN/RDN, entry và mô hình thuộc tính.
3. [RFC 4517 — LDAP: Syntaxes and Matching Rules](https://www.rfc-editor.org/rfc/rfc4517.html) — matching rules và ngữ nghĩa so sánh.
4. [RFC 4515 — LDAP: String Representation of Search Filters](https://www.rfc-editor.org/rfc/rfc4515.html) — escaping filter, khác DN escaping.
5. [RFC 2849 — LDAP Data Interchange Format (LDIF)](https://www.rfc-editor.org/rfc/rfc2849.html) — encoding và `dn::` base64.
6. [Java SE — javax.naming.ldap.LdapName](https://docs.oracle.com/en/java/javase/21/docs/api/java.naming/javax/naming/ldap/LdapName.html).
7. [Java SE — javax.naming.ldap.Rdn](https://docs.oracle.com/en/java/javase/21/docs/api/java.naming/javax/naming/ldap/Rdn.html).
8. [Java SE — java.text.Normalizer](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/Normalizer.html).
9. [Spring LDAP — LdapNameBuilder API](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/support/LdapNameBuilder.html).
10. [Spring LDAP Reference](https://docs.spring.io/spring-ldap/reference/) và [Spring Data LDAP Reference](https://docs.spring.io/spring-data/ldap/reference/).
