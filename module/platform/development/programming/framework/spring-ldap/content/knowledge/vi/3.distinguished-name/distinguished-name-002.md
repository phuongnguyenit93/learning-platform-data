# Escaping ký tự đặc biệt trong DN

Trong LDAP, **Distinguished Name (DN)** biểu diễn vị trí của một entry trong cây thư mục (Directory Information Tree, DIT). DN có cú pháp riêng: dấu phẩy phân tách các thành phần tên, dấu cộng có thể nối nhiều cặp thuộc tính–giá trị trong một RDN, còn dấu bằng ngăn cách tên thuộc tính với giá trị. Vì vậy, khi **giá trị thuộc tính chứa chính các ký tự có ý nghĩa cú pháp**, ta phải *escape* để LDAP hiểu đó là **dữ liệu** thay vì dấu phân tách.

Bài thuộc chương **DN và Name** của mô-đun **SPRING_LDAP**. Đây là kiến thức nền để đọc và ghi entry, xác định search base, tìm kiếm, xác thực và thao tác với `LdapTemplate`, `LdapClient` hoặc Object-Directory Mapping (ODM) trong Spring LDAP. Một DN viết sai có thể gây lỗi “No Such Object”, tìm sai entry hoặc tạo rủi ro chèn cú pháp DN khi ứng dụng nối chuỗi từ dữ liệu đầu vào.

**Mục tiêu:** sau bài này, bạn có thể:

- Nhận ra các ký tự đặc biệt theo RFC 4514 và escape đúng vị trí.
- Phân biệt giá trị gốc, RDN, DN, Java string và cú pháp LDIF.
- Dựng DN an toàn bằng `LdapNameBuilder` hoặc `Rdn` thay vì tự nối chuỗi.
- Phân biệt **DN escaping** (RFC 4514) với **LDAP filter escaping** (RFC 4515).
- Tìm nguyên nhân lỗi khi DN có dấu phẩy, dấu cộng, dấu gạch chéo ngược, ký tự Unicode hoặc khoảng trắng đầu/cuối.

## 1. DN chứa cấu trúc, RDN chứa giá trị

Xét một entry dưới nhánh `ou=People,dc=example,dc=com`:

```text
cn=Lan Nguyen,ou=People,dc=example,dc=com
└── RDN     └─ các RDN của entry cha ─────┘
```

- `cn=Lan Nguyen` là **Relative Distinguished Name (RDN)** của entry.
- Dấu `=` thứ nhất phân tách **loại thuộc tính** (`cn`) và **giá trị** (`Lan Nguyen`).
- Các dấu `,` chưa escape ngăn cách những RDN trong DN.
- Dấu `+` chưa escape có thể ngăn cách hai cặp thuộc tính–giá trị **trong cùng một RDN**.

Nếu tên hiển thị là **`Doe, Jane`**, không thể viết DN theo kiểu:

```text
cn=Doe, Jane,ou=People,dc=example,dc=com
```

LDAP có thể hiểu dấu phẩy sau `Doe` là điểm kết thúc RDN và bắt đầu phân tích ` Jane` như một RDN khác, khiến DN không hợp lệ. Cách viết đúng là:

```text
cn=Doe\, Jane,ou=People,dc=example,dc=com
```

Ký tự `\` ngay trước dấu phẩy báo rằng **dấu phẩy này thuộc giá trị `cn`**. Những dấu phẩy phân tách RDN vẫn giữ nguyên.

> **Quy tắc cốt lõi:** chỉ escape ký tự đặc biệt **bên trong giá trị của RDN** khi cần biểu diễn chúng như dữ liệu. Không escape nhầm các dấu phân tách `=`, `,`, `+` được dùng có chủ đích để tạo cấu trúc DN.

## 2. Những ký tự cần escape theo RFC 4514

Theo [RFC 4514, mục 2.4](https://www.rfc-editor.org/rfc/rfc4514.html#section-2.4), trong biểu diễn chuỗi DN phổ biến, các ký tự sau phải được escape khi chúng xuất hiện trong **giá trị** theo vị trí tương ứng.

| Giá trị chứa | Quy tắc | Ví dụ giá trị gốc | Phần RDN đã escape |
| --- | --- | --- | --- |
| Dấu phẩy `,` | Escape | `Doe, Jane` | `cn=Doe\, Jane` |
| Dấu cộng `+` | Escape | `Ops+Dev` | `cn=Ops\+Dev` |
| Dấu ngoặc kép `"` | Escape | `"Sales"` | `cn=\"Sales\"` |
| Dấu chấm phẩy `;` | Escape | `East;West` | `cn=East\;West` |
| Dấu nhỏ hơn `<` và lớn hơn `>` | Escape | `A<B>` | `cn=A\<B\>` |
| Dấu bằng `=` | Escape khi nằm trong giá trị | `Tier=1` | `cn=Tier\=1` |
| Dấu gạch chéo ngược `\` | Escape chính nó | `C:\Data` | `cn=C:\\Data` |
| Dấu `#` ở **đầu giá trị** | Escape | `#Archive` | `cn=\#Archive` |
| Dấu cách ở **đầu giá trị** | Escape | ` Team` | `cn=\ Team` |
| Dấu cách ở **cuối giá trị** | Escape | `Team ` | `cn=Team\ ` |
| Ký tự NUL (U+0000) | Escape bằng byte hex | `A` + NUL + `B` | `cn=A\00B` |

**Không phải mọi dấu cách hoặc dấu `#` đều cần escape.** Ví dụ `cn=Sales Team` hợp lệ vì dấu cách nằm **giữa** giá trị; `cn=Ref#12` hợp lệ vì `#` không nằm đầu giá trị. Dấu sao `*` cũng **không phải ký tự bắt buộc escape trong DN**, dù nó mang ý nghĩa riêng trong *LDAP search filter*.

### 2.1. Escaping bằng dấu gạch chéo ngược

Cách thường gặp là đặt `\` trước ký tự cần escape:

```text
Giá trị gốc:    Smith, John
RDN:            cn=Smith\, John
DN đầy đủ:      cn=Smith\, John,ou=People,dc=example,dc=com
```

Nếu giá trị chứa dấu gạch chéo ngược thật, escape chính nó:

```text
Giá trị gốc:    C:\Data
RDN:            cn=C:\\Data
```

Ở ví dụ thứ hai, `\\` trong **chuỗi DN** biểu diễn **một** dấu gạch chéo ngược trong giá trị gốc.

### 2.2. Escaping bằng cặp byte hex

RFC 4514 còn cho phép dùng `\HH`, trong đó `HH` là hai chữ số hexa biểu diễn **một byte**. Chẳng hạn:

```text
cn=Doe\, Jane       # escape dấu phẩy bằng ký tự
cn=Doe\2C Jane      # cùng giá trị, escape byte 0x2C
```

Hai cách trên cùng biểu diễn giá trị `Doe, Jane`. Dạng hex đặc biệt hữu ích cho các byte điều khiển, ví dụ NUL phải viết `\00`.

Với Unicode, chuỗi DN có thể hiển thị ký tự Unicode trực tiếp nếu được mã hóa và truyền đúng. Nếu dùng dạng hex cho ký tự không thuộc ASCII, phải escape **từng byte UTF-8**, không dùng điểm mã Unicode như một byte đơn:

```text
Giá trị:         Müller
DN thông thường: cn=Müller,ou=People,dc=example,dc=com
Dạng UTF-8 hex:  cn=M\C3\BCller,ou=People,dc=example,dc=com
```

Chữ `ü` được mã hóa UTF-8 thành hai byte `C3 BC` nên cần `\C3\BC`. Đừng lấy mã điểm Unicode `U+00FC` rồi ghi thành `\00FC` trong DN: `\00` biểu diễn NUL, không phải chữ `ü`.

### 2.3. Khoảng trắng đầu và cuối có ý nghĩa

So sánh ba giá trị (dấu ngoặc kép chỉ dùng để làm rõ vị trí khoảng trắng):

| Giá trị thực | RDN tương ứng |
| --- | --- |
| `"Team"` | `cn=Team` |
| `" Team"` — có dấu cách ở đầu | `cn=\20Team` |
| `"Team "` — có dấu cách ở cuối | `cn=Team\20` |

Dấu cách đầu/cuối cũng có thể được escape bằng **dấu `\` đặt ngay trước dấu cách** (như `cn=\ Team` hoặc `cn=Team\ `). Tuy nhiên, cú pháp `\20` biểu diễn một byte space rõ ràng hơn trong tài liệu vì trình soạn thảo có thể cắt khoảng trắng ở cuối dòng.

Lưu ý: dấu cách *giữa* hai từ như `cn=Sales Team` không cần escape. Khi cần giữ chính xác dữ liệu, không tự ý `trim()` đầu vào chỉ để tránh phải escape: cắt khoảng trắng có thể biến giá trị cần lưu thành giá trị khác.

### 2.4. Dấu `#` đầu giá trị và RDN nhiều thuộc tính

Dấu `#` ở **đầu giá trị** phải escape; nếu không, nó có thể được hiểu là điểm bắt đầu của biểu diễn dạng hex (`BER-encoded value`) theo cú pháp DN:

```text
cn=\#Finance,ou=Groups,dc=example,dc=com
```

Dấu cộng có thể là ký tự **cú pháp** tạo *multi-valued RDN*:

```text
cn=Jane+uid=42,ou=People,dc=example,dc=com
```

Ở đây RDN có **hai cặp thuộc tính–giá trị** là `cn=Jane` và `uid=42`. Nhưng nếu toàn bộ `Jane+uid=42` là **giá trị của `cn`**, phải escape cả dấu cộng và dấu bằng xuất hiện trong giá trị:

```text
cn=Jane\+uid\=42,ou=People,dc=example,dc=com
```

Hai DN trên khác nghĩa; escape không đơn thuần là làm đẹp chuỗi.

## 3. Phân biệt giá trị gốc, DN string, Java string và LDIF

Dễ nhầm vì mỗi môi trường lại có **một tầng cú pháp** riêng.

Giả sử entry có giá trị `cn` thực tế là `Doe, Jane`, nằm dưới `ou=People`.

| Ngữ cảnh | Cách biểu diễn | Lý do |
| --- | --- | --- |
| Giá trị attribute trong LDAP | `Doe, Jane` | Bản thân dữ liệu không chứa ký tự escape thêm vào |
| RDN dưới dạng chuỗi LDAP | `cn=Doe\, Jane` | Escape dấu phẩy thuộc giá trị |
| DN dưới dạng chuỗi LDAP | `cn=Doe\, Jane,ou=People,dc=example,dc=com` | Dấu phẩy giữa các RDN là cú pháp |
| Java string literal chứa DN | `"cn=Doe\\, Jane,ou=People,dc=example,dc=com"` | Java cần `\\` để biểu diễn một `\` |
| LDIF: dòng `dn:` | `dn: cn=Doe\, Jane,ou=People,dc=example,dc=com` | DN sử dụng cú pháp RFC 4514 |
| LDIF: giá trị `cn:` | `cn: Doe, Jane` | Attribute value thực là `Doe, Jane` |

Ví dụ LDIF nhất quán:

```ldif
dn: cn=Doe\, Jane,ou=People,dc=example,dc=com
objectClass: top
objectClass: organizationalRole
cn: Doe, Jane
```

Dấu `\` trong dòng `dn:` **không phải** một phần của giá trị `cn` lưu trong LDAP; nó chỉ phục vụ cú pháp DN dạng chuỗi. Trong LDIF, các giá trị có ký tự không an toàn theo quy tắc LDIF (ví dụ nhiều trường hợp chứa ký tự ngoài ASCII) cần được biểu diễn qua `::` và Base64 theo RFC 2849. Quy tắc Base64 của LDIF là **một tầng khác** với DN escaping.

### 3.1. Java cần thêm tầng escaping cho dấu `\`

Để tạo một `String` trong mã nguồn Java chứa ký tự `\`, phải viết `\\` trong *string literal*:

```java
String ldapDn = "cn=Doe\\, Jane,ou=People,dc=example,dc=com";
System.out.println(ldapDn);
// In ra: cn=Doe\, Jane,ou=People,dc=example,dc=com
```

Nếu nhập `"cn=Doe\, Jane"` trong mã nguồn Java, chương trình **không biên dịch** vì `\,` không phải escape sequence hợp lệ của Java.

Ngược lại, nếu DN được nhận từ API, biến môi trường hay cấu hình ở runtime, **đừng tự động nhân đôi mọi dấu `\`**. Việc có cần viết `\\` hay không là vấn đề **cú pháp string literal của ngôn ngữ lập trình**, không phải quy tắc sửa DN ở runtime.

## 4. Cách dựng DN an toàn trong Spring LDAP

Khi một tên người dùng, tên nhóm hoặc mã đối tượng đến từ form/API, **không nối trực tiếp giá trị đó vào chuỗi DN**:

```java
// Không an toàn: input có dấu phẩy, dấu cộng, dấu bằng... làm đổi cú pháp DN.
String dn = "cn=" + commonName + ",ou=People,dc=example,dc=com";
```

Ví dụ `commonName = "Doe, Jane"` sẽ gây DN sai vì dấu phẩy trong tên bị hiểu như ký tự phân tách. Thay vào đó, dựng DN theo từng cặp **loại thuộc tính / giá trị** để thư viện escape đúng khi chuyển sang chuỗi.

### 4.1. Dùng `LdapNameBuilder`

`LdapNameBuilder` là tiện ích của Spring LDAP để ghép DN và xử lý escaping cho **giá trị**. Ví dụ:

```java
import javax.naming.Name;
import org.springframework.ldap.support.LdapNameBuilder;

public final class DnFactory {
    public static Name personDn(String commonName) {
        return LdapNameBuilder.newInstance()
            .add("dc", "com")
            .add("dc", "example")
            .add("ou", "People")
            .add("cn", commonName)
            .build();
    }
}
```

Với `commonName = "Doe, Jane"`, `personDn(commonName).toString()` trả về DN tương ứng:

```text
cn=Doe\, Jane,ou=People,dc=example,dc=com
```

Nhờ API nhận riêng `"cn"` và `commonName`, dấu phẩy trong **giá trị** sẽ được escape khi tuần tự hóa tên. Cũng cần phân biệt với đoạn `.add("cn=Doe, Jane")`: khi API nhận *cả chuỗi RDN*, nó sẽ phân tích chuỗi theo cú pháp RDN, không thể tự đoán dấu phẩy nào là dữ liệu chưa escape. Ưu tiên overload nhận **loại thuộc tính và giá trị riêng**.

**Quan trọng về thứ tự:** Các lệnh `.add(...)` ở ví dụ này xây đường dẫn từ gốc (`dc=com`) đến nút con (`cn=...`). Chuỗi DN kết quả hiển thị theo thứ tự ngược, từ RDN của entry ở bên trái đến RDN cấp cha ở bên phải.

### 4.2. Dùng `javax.naming.ldap.Rdn` nếu làm việc ở tầng JNDI

Java chuẩn cung cấp `Rdn` để biểu diễn một RDN. Bạn có thể truyền tên thuộc tính và **giá trị gốc**:

```java
import javax.naming.ldap.Rdn;

String commonName = "Doe, Jane";
Rdn rdn = new Rdn("cn", commonName);
System.out.println(rdn.toString()); // cn=Doe\, Jane
```

Nếu cần thao tác một DN gồm nhiều RDN, `javax.naming.ldap.LdapName` cung cấp mô hình đối tượng cho tên LDAP. Hãy dùng API thay vì viết hàm replace thủ công như `value.replace(",", "\\,")`, vì còn nhiều ký tự và trường hợp khác phải xử lý đúng.

### 4.3. Chú ý DN tương đối khi cấu hình `ContextSource.base`

Một cấu hình Spring LDAP thường đặt base DN:

```java
contextSource.setBase("dc=example,dc=com");
```

Khi đó, `LdapTemplate` thường nhận **DN tương đối với base này** cho các thao tác entry và search. Ví dụ, nếu lookup người có `cn = "Doe, Jane"` dưới `ou=People`, chỉ dựng phần tương đối:

```java
import javax.naming.Name;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

public class PersonRepository {
    private final LdapTemplate ldapTemplate;

    public PersonRepository(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public String readCommonName(String commonName) {
        Name relativeDn = LdapNameBuilder.newInstance()
            .add("ou", "People")
            .add("cn", commonName)
            .build();

        return ldapTemplate.lookup(
            relativeDn,
            (AttributesMapper<String>) attrs ->
                (String) attrs.get("cn").get()
        );
    }
}
```

`relativeDn` lúc này biểu diễn `cn=Doe\, Jane,ou=People`; `ContextSource` xử lý phần base `dc=example,dc=com` trong các thao tác thông thường. Nếu truyền thêm cả `dc=example,dc=com` vào `relativeDn`, ứng dụng có thể nối lặp base, dẫn đến sai DN và lỗi không tìm thấy entry.

**Đừng nhầm hai hành động khác nhau:** tạo DN dùng để *định vị entry* (có thể tương đối với base cấu hình) và lưu một **giá trị attribute dạng DN**, chẳng hạn `member` của nhóm. Giá trị `member` thường cần **DN đầy đủ của thành viên** theo schema; cấu hình base của Spring LDAP không tự động biến các giá trị attribute thành DN đầy đủ.

### 4.4. Đầu vào có vẻ giống cú pháp DN vẫn là một giá trị

Giả sử người dùng nhập tên:

```text
Ops,ou=Admins
```

Với API `.add("cn", input)`, toàn bộ nội dung trên được coi là **giá trị `cn`** và dấu phẩy/dấu bằng trong nó được escape:

```text
cn=Ops\,ou\=Admins,ou=People
```

Dữ liệu người dùng **không tự ý tạo thêm cấp `ou=Admins`**. Escaping giúp giữ đúng cấu trúc tên; thao tác ghi/đọc vẫn phải tuân thủ xác thực, quyền truy cập và schema của LDAP server.

## 5. DN escaping khác LDAP filter escaping

Đây là hai cú pháp riêng, có **bộ ký tự đặc biệt khác nhau**. Việc một giá trị an toàn khi đặt vào DN **không đồng nghĩa** nó đã an toàn khi nhúng vào filter.

| Ngữ cảnh | Chuẩn | Ký tự cần chú ý | Ví dụ |
| --- | --- | --- | --- |
| DN/RDN string | RFC 4514 | `,`, `+`, `"`, `\`, `<`, `>`, `;`, `=`; `#`/space ở đầu; space ở cuối; NUL | `cn=Doe\, Jane` |
| LDAP filter assertion value | RFC 4515 | `*`, `(`, `)`, `\`, NUL (và các byte UTF-8 không hợp lệ) | `(cn=A\2aB)` để tìm giá trị đúng `A*B` |

Ví dụ, dấu phẩy trong giá trị `Doe, Jane` **phải escape trong DN**, nhưng là dữ liệu bình thường khi dùng trong filter:

```text
DN:      cn=Doe\, Jane,ou=People,dc=example,dc=com
Filter:  (cn=Doe, Jane)
```

Ngược lại, dấu sao `*` trong filter là wildcard:

```text
(cn=A*B)       # có thể khớp các tên bắt đầu A, kết thúc B
(cn=A\2aB)     # khớp giá trị chứa dấu * thật: "A*B"
```

Không dùng `\*` để thay thế `\2a` trong cú pháp filter của RFC 4515. Và đừng dùng `\2a` như một “bộ lọc DN” chung: chức năng escaping phụ thuộc ngữ cảnh.

### 5.1. Tìm kiếm qua Spring LDAP: dùng filter builder

Khi tìm entry theo giá trị `cn` được nhập từ người dùng, hãy để bộ dựng query thực hiện escaping filter:

```java
import java.util.List;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;

public List<String> findNames(LdapTemplate ldapTemplate, String input) {
    LdapQuery query = LdapQueryBuilder.query()
        .base("ou=People")
        .where("cn").is(input);

    return ldapTemplate.search(
        query,
        (AttributesMapper<String>) attrs ->
            (String) attrs.get("cn").get()
    );
}
```

Ví dụ này giả sử `ContextSource.base = dc=example,dc=com`. API `.where("cn").is(input)` xử lý **giá trị filter** theo ngữ cảnh của filter. Nếu `input = "A*B"` và bạn muốn tìm giá trị `cn` thực sự chứa ký tự `*`, query builder sẽ escape ký tự đó như dữ liệu.

Khi cần truy cập **đúng một entry đã biết DN**, dựng `Name` bằng `LdapNameBuilder` rồi dùng `lookup`. Khi cần **tìm theo điều kiện**, dùng filter builder và chọn base/scope thích hợp. Hai nghiệp vụ đòi hỏi cách escaping khác nhau.

## 6. Những trường hợp dễ mắc lỗi

### 6.1. Escape toàn bộ DN như một giá trị duy nhất

Sai cách tư duy:

```text
Giá trị nhập vào API: cn=Doe, Jane,ou=People,dc=example,dc=com
```

Nếu mục tiêu là **địa chỉ của entry**, cần phân tích một DN đã hợp lệ (hoặc dựng từng RDN từ các giá trị gốc). Không đưa nguyên **chuỗi DN hoàn chỉnh** vào `.add("cn", value)`: điều đó sẽ tạo một **giá trị `cn` rất dài** chứa dấu bằng và dấu phẩy, không phải đường dẫn đến entry mong muốn.

### 6.2. Escape hai lần (double escaping)

Nếu đã có DN string hợp lệ `cn=Doe\, Jane,ou=People,...` mà lại coi toàn bộ `Doe\, Jane` là **giá trị thô** để đưa vào bộ dựng DN, dấu `\` sẵn có sẽ bị escape thêm. Kết quả biểu diễn một tên khác có **dấu gạch chéo ngược thật** trong giá trị.

Quy ước nên dùng:

- Dữ liệu lấy từ form/API: giữ dạng **giá trị gốc**, đưa vào `add(attribute, value)`.
- DN string nhận từ nguồn đáng tin và đã đúng cú pháp: dùng API phân tích DN/RDN tương ứng.
- Không vừa tự escape dấu phẩy rồi lại nhờ thư viện escape lần nữa.

### 6.3. Tự động xóa khoảng trắng

Đổi giá trị `" Jane"` thành `"Jane"` bằng `trim()` sẽ thay đổi nội dung. Nếu dấu cách ở đầu/cuối thực sự thuộc dữ liệu, giữ nguyên và escape (`cn=\ Jane` hoặc `cn=Jane\ `). Nếu nghiệp vụ quy định bỏ khoảng trắng, hãy chuẩn hóa theo **quy tắc nghiệp vụ có chủ đích**, trước khi dựng DN.

### 6.4. So sánh DN bằng chuỗi văn bản

Cùng một giá trị có thể được biểu diễn khác nhau:

```text
cn=Doe\, Jane,ou=People,dc=example,dc=com
cn=Doe\2C Jane,ou=People,dc=example,dc=com
```

So sánh từng ký tự sẽ báo khác dù hai chuỗi có thể biểu diễn cùng tên. RFC 4514 không quy định một dạng chuỗi DN *canonical* duy nhất. Ưu tiên mô hình `Name`/`LdapName` để phân tích tên; khi cần quyết định hai tên có tham chiếu cùng entry hay không, vẫn phải tôn trọng quy tắc so khớp tên/schema và hành vi của LDAP server.

### 6.5. Nhầm escaping với bảo mật kết nối và phân quyền

Escaping ngăn một giá trị đầu vào bị diễn giải thành cấu trúc DN/filter sai. Nó **không** xác thực người dùng, cấp quyền sửa entry, mã hóa đường truyền hay kiểm tra schema. Trong ứng dụng Spring LDAP thực tế vẫn phải sử dụng bind account với quyền tối thiểu, kết nối TLS (LDAPS hoặc StartTLS, kiểm tra chứng chỉ), kiểm soát dữ liệu đầu vào và xử lý lỗi LDAP theo ngữ cảnh.

## 7. Bảng kiểm khi xử lý DN có ký tự đặc biệt

| Triệu chứng | Khả năng cao | Hướng xử lý |
| --- | --- | --- |
| DN báo lỗi cú pháp khi tên có dấu phẩy | `,` trong giá trị chưa escape | Dùng `LdapNameBuilder.add("cn", rawValue)` |
| Tên `Ops+Dev` bị coi là RDN nhiều thuộc tính | `+` chưa escape | Trong giá trị dùng `\+` |
| Tên bắt đầu bằng `#` gây lỗi parse | `#` ở đầu chưa escape | Dùng `\#` hoặc bộ dựng DN |
| Dấu `\` trong dữ liệu biến mất hoặc bị hiểu sai | Chưa escape `\` trong DN hoặc nhầm Java literal | Phân biệt `\\` ở DN và `\\\\` trong mã nguồn Java |
| Dấu cách đầu/cuối không còn | Dữ liệu bị `trim()` hoặc chưa escape | Kiểm tra giá trị thô và biểu diễn `\20` |
| Search tìm `A*B` trả nhiều kết quả | `*` được hiểu là wildcard filter | Dùng filter builder hoặc escape `\2a` trong filter |
| `No Such Object` dù DN có vẻ đúng | Dựng RDN sai, escape hai lần hoặc nối lặp `ContextSource.base` | In dạng DN đã dựng, phân tích từng RDN và đối chiếu base |
| Cùng entry nhưng hai chuỗi DN trông khác | Khác dạng escape hoặc cách biểu diễn | Parse bằng API tên LDAP; xét quy tắc so khớp của server |

**Mẹo kiểm tra:** ghi log dạng DN **đã dựng** (khi phù hợp với chính sách dữ liệu nhạy cảm), giá trị `ContextSource.base` và search base/scope. Đừng ghi log mật khẩu bind hoặc các giá trị cá nhân không cần thiết.

## 8. Thực hành và tự kiểm tra

Giả sử base DN của `ContextSource` là `dc=example,dc=com` và entry nằm dưới `ou=People`.

**Bài 1.** Viết DN đầy đủ cho một entry có `cn` gốc là `Nguyen, An`.

**Bài 2.** Viết RDN tương ứng cho giá trị `cn` gốc là `#2026`, rồi cho giá trị gốc ` Sales ` (có một dấu cách ở đầu và một dấu cách ở cuối).

**Bài 3.** Hai chuỗi `cn=Ops+uid=42,...` và `cn=Ops\+uid\=42,...` có ý nghĩa giống nhau không? Vì sao?

**Bài 4.** Bạn nhận đầu vào `A*B`. Hãy viết biểu diễn tương ứng để tìm **chính xác** giá trị `cn` qua LDAP filter. Có bắt buộc escape dấu `*` nếu dùng đầu vào này làm RDN `cn` không?

**Bài 5.** Trong Java, hãy chọn cách đúng để dựng DN khi `commonName` đến từ người dùng:

```java
// A
String dnA = "cn=" + commonName + ",ou=People";

// B
Name dnB = LdapNameBuilder.newInstance()
    .add("ou", "People")
    .add("cn", commonName)
    .build();
```

### Đáp án gợi ý

1. `cn=Nguyen\, An,ou=People,dc=example,dc=com`.
2. `cn=\#2026`; và `cn=\ Sales\ ` (hoặc dạng hex `cn=\20Sales\20`).
3. **Không.** Chuỗi thứ nhất dùng `+` làm dấu nối hai cặp thuộc tính–giá trị của một RDN; chuỗi thứ hai có toàn bộ `Ops+uid=42` là giá trị của riêng `cn`.
4. Filter đúng là `(cn=A\2aB)`. Trong **DN**, `cn=A*B` hợp lệ theo RFC 4514 vì `*` không bắt buộc escape.
5. **B**: dùng API nhận riêng loại attribute và giá trị để escape đúng. Kết quả ở đây là DN **tương đối** với `dc=example,dc=com` nếu dùng qua `ContextSource` đã cấu hình base đó.

## 9. Ghi nhớ

- **RFC 4514** quy định cách biểu diễn **DN/RDN**: dấu `,`, `+`, `=` và các ký tự cú pháp khác cần escape nếu nằm trong giá trị; `#` đầu và dấu cách đầu/cuối là trường hợp theo vị trí.
- **RFC 4515** quy định **LDAP filter**: `*`, `(`, `)`, `\`, NUL cần escaping phù hợp khi dùng như ký tự dữ liệu.
- Dùng **`LdapNameBuilder` hoặc `Rdn` để dựng tên**, **query builder để dựng filter**; không ghép chuỗi từ đầu vào chưa được xử lý.
- DN tương đối phải khớp với **`ContextSource.base`** khi truy cập thư mục qua Spring LDAP; escaping đúng vẫn chưa đủ nếu base hoặc quyền truy cập sai.

### Tài liệu tham khảo

- [RFC 4514 — LDAP: String Representation of Distinguished Names](https://www.rfc-editor.org/rfc/rfc4514.html): quy tắc DN/RDN và escaping.
- [RFC 4512 — LDAP: Directory Information Models](https://www.rfc-editor.org/rfc/rfc4512.html): mô hình entry, DN và DIT.
- [RFC 4515 — LDAP: String Representation of Search Filters](https://www.rfc-editor.org/rfc/rfc4515.html): ký tự đặc biệt trong filter.
- [RFC 2849 — LDAP Data Interchange Format (LDIF)](https://www.rfc-editor.org/rfc/rfc2849.html): cách biểu diễn attribute và DN trong LDIF.
- [Spring LDAP Reference](https://docs.spring.io/spring-ldap/reference/): cấu hình ContextSource, tìm kiếm và thao tác LDAP.
- [Spring LDAP Javadoc — LdapNameBuilder](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/support/LdapNameBuilder.html): dựng DN bằng Java.
