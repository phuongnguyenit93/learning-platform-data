# Kiểu dữ liệu, cú pháp thuộc tính và matching rule

> **Chương:** Schema  
> **Module:** SPRING_DATA_LDAP — truy cập dịch vụ thư mục LDAP qua Spring Data LDAP, ánh xạ entry phân cấp sang Java entity và thao tác với `LdapRepository` hoặc `LdapTemplate`.

Một LDAP entry chứa các cặp *thuộc tính – giá trị*, nhưng directory server không xem tất cả giá trị là những chuỗi ký tự có thể so sánh tùy ý. Mỗi **attribute type** được schema mô tả bằng tên/OID, **syntax** (cú pháp giá trị), các **matching rule** (quy tắc so khớp), giới hạn số giá trị và một số quy tắc khác. Những thông tin này quyết định server chấp nhận gì khi Add/Modify và diễn giải filter ra sao khi Search.

Ví dụ, giá trị `uidNumber: 42` có cú pháp số nguyên; dùng phép so sánh chuỗi để kết luận `"10" > "2"` sẽ sai nếu yêu cầu là so sánh số. Giá trị `createTimestamp: 20261126120000Z` biểu diễn thời điểm, không phải một chuỗi tự do. Một thuộc tính lưu DN thành viên nhóm phải áp dụng quy tắc so khớp DN thay vì so sánh văn bản thô. Và dữ liệu `jpegPhoto` là các octet, không phải `String` UTF-8 bất kỳ.

Khi lập trình Spring Data LDAP, hiểu syntax và matching rule giúp bạn **thiết kế entity đúng kiểu**, **xây filter an toàn**, **giải thích kết quả tìm kiếm** và **xử lý lỗi schema** thay vì cố sửa mã Java theo suy đoán.

## 1. Mục tiêu của bài học

Sau bài học, người học có thể:

1. Phân biệt **attribute type**, **LDAP syntax**, **matching rule**, **objectClass** và **giá trị Java**.
2. Đọc các thành phần `SYNTAX`, `EQUALITY`, `ORDERING`, `SUBSTR` và `SINGLE-VALUE` trong định nghĩa attribute type.
3. Hiểu một số syntax phổ biến: Directory String, Integer, Boolean, Generalized Time, Distinguished Name và Octet String.
4. Giải thích vì sao `caseIgnoreMatch`, `integerMatch` hoặc `distinguishedNameMatch` cho kết quả khác nhau.
5. Xây LDAP filter bằng API Spring LDAP mà không ghép trực tiếp dữ liệu đầu vào.
6. Chuyển các giá trị JNDI thành kiểu Java thích hợp, kiểm tra trường bắt buộc và dữ liệu nhiều giá trị.
7. Thiết kế kiểm thử xác nhận matching semantics trên directory server thật, không chỉ dựa vào unit test Java.

## 2. Năm tầng định nghĩa dữ liệu cần phân biệt

| Tầng | Quyết định điều gì? | Ví dụ |
|---|---|---|
| **Attribute type** | Thuộc tính có tên/OID nào; được so khớp và giới hạn giá trị ra sao | `cn`, `uidNumber`, `member` |
| **LDAP syntax** | Kiểu giá trị hợp lệ và cách diễn giải giá trị ở phía directory | Directory String, Integer, Distinguished Name |
| **Matching rule** | Cách server xác định bằng nhau, thứ tự hoặc substring | `caseIgnoreMatch`, `integerMatch` |
| **Object class** | Attribute nào bắt buộc (MUST) hoặc được phép (MAY) trên entry | `person` yêu cầu `cn` và `sn` |
| **Java mapping** | Đối tượng JNDI/ODM thể hiện và chuyển giá trị trong ứng dụng | `String`, `byte[]`, `List<String>` |

Xét entry minh họa:

~~~ldif
dn: uid=lan,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: lan
cn: Tran Thi Lan
sn: Tran
mail: lan@example.org
~~~

- `inetOrgPerson` là một **object class**, thuộc chuỗi kế thừa structural `top → person → organizationalPerson → inetOrgPerson`.
- `uid`, `cn`, `sn` và `mail` là **attribute type**.
- Các thuộc tính đó có những **syntax/matching rule** được schema định nghĩa, không do kiểu field Java quyết định.
- `@Attribute(name = "mail") private String email;` là **ánh xạ ODM** trong Spring Data LDAP; khai báo này không tự thay đổi schema directory.

**Kết luận:** thêm một field Java hoặc đặt `@Attribute` không khiến server tự hiểu một attribute type mới. Mọi thao tác ghi vẫn phải thỏa schema đang được directory thực thi.

## 3. Đọc định nghĩa attribute type trong LDAP schema

Một định nghĩa attribute type thường có các thành phần như:

~~~text
( 1.3.6.1.4.1.99999.1.1
  NAME 'appStaffLevel'
  DESC 'Example-only employee level'
  EQUALITY integerMatch
  ORDERING integerOrderingMatch
  SYNTAX 1.3.6.1.4.1.1466.115.121.1.27
  SINGLE-VALUE )
~~~

**Đây là ví dụ thiết kế, không phải schema chuẩn hay OID đã được cấp phát để đưa vào production.** Nếu thực sự tạo schema extension, tổ chức phải sử dụng OID thuộc nhánh đã được cấp cho mình và kiểm tra cú pháp của server đích.

| Thành phần | Ý nghĩa | Trong ví dụ |
|---|---|---|
| OID đầu tiên | Định danh duy nhất cho attribute type | `1.3.6.1.4.1.99999.1.1` (giả định) |
| `NAME` | Tên tiện dùng trong LDIF/filter/API | `appStaffLevel` |
| `DESC` | Mô tả ngắn | Employee level |
| `SUP` | Attribute type cha, nếu có kế thừa từ một attribute type khác | Không khai báo trong ví dụ |
| `EQUALITY` | Matching rule cho phép so bằng | `integerMatch` |
| `ORDERING` | Matching rule cho so thứ tự | `integerOrderingMatch` |
| `SUBSTR` | Matching rule cho substring | Không định nghĩa |
| `SYNTAX` | Syntax OID và giới hạn dạng giá trị | OID của Integer |
| `SINGLE-VALUE` | Giới hạn thuộc tính tối đa một giá trị | Có |
| `NO-USER-MODIFICATION` | Thuộc tính không được sửa bằng thao tác người dùng thông thường | Không có ở ví dụ |

Những từ khóa `EQUALITY`, `ORDERING` và `SUBSTR` mô tả ba cách so khớp khác nhau. Một attribute **không bắt buộc có đủ cả ba**: `appStaffLevel` là số nguyên nên định nghĩa ở trên hỗ trợ equality và ordering nhưng không định nghĩa substring.

Ví dụ tìm `appStaffLevel >= 5` chỉ có ý nghĩa khi entry được phép chứa attribute này và server có matching rule thích hợp. **Chỉ thêm `attributeTypes` chưa đủ để entry có thể dùng attribute**: còn cần object class hoặc quy tắc schema cho phép thuộc tính đó.

### Kế thừa của attribute type khác kế thừa object class

LDAP cho phép attribute type có `SUP` để kế thừa đặc điểm từ một attribute type cha; đây là quan hệ **riêng** với việc `inetOrgPerson SUP organizationalPerson`. Không nhầm hai cơ chế:

- Kế thừa **object class** xác định tập thuộc tính MUST/MAY được phép trên entry.
- Kế thừa **attribute type** liên quan tới định nghĩa và thuộc tính của một loại giá trị; mỗi attribute type vẫn có định danh riêng.

Nếu attribute type đang được định nghĩa bởi nhánh schema cụ thể, cần đọc các ràng buộc đã được kế thừa và quy tắc đăng ký của directory. Không được suy rằng mỗi attribute type trong directory đều có một lớp cha.

## 4. LDAP syntax: server chấp nhận những loại giá trị nào?

LDAP syntax mô tả cách diễn giải giá trị của attribute. Bảng dưới liệt kê **các syntax phổ biến**, không phải toàn bộ syntax được LDAP hỗ trợ:

| Syntax | OID syntax LDAP | Ví dụ attribute | Kiểu thường thấy qua JNDI |
|---|---|---|---|
| Directory String | `1.3.6.1.4.1.1466.115.121.1.15` | `cn`, `sn`, `mail` (theo định nghĩa thuộc tính thực tế) | `String` |
| Integer | `1.3.6.1.4.1.1466.115.121.1.27` | `uidNumber` trong schema POSIX | Thường `String`; ứng dụng tự parse |
| Boolean | `1.3.6.1.4.1.1466.115.121.1.7` | Một số attribute logic trong schema hỗ trợ | Thường `String` |
| Generalized Time | `1.3.6.1.4.1.1466.115.121.1.24` | `createTimestamp`, `modifyTimestamp` | Thường `String` |
| Distinguished Name | `1.3.6.1.4.1.1466.115.121.1.12` | `member` của `groupOfNames` | Thường chuỗi DN |
| Octet String | `1.3.6.1.4.1.1466.115.121.1.40` | `jpegPhoto` và thuộc tính nhị phân phù hợp | `byte[]` khi provider nhận diện binary |

Các OID này **xác định syntax**, không phải OID của attribute type. Ví dụ một attribute tùy chỉnh có thể tham chiếu syntax Integer OID; điều đó **không** làm nó trở thành `uidNumber`.

**Đặc biệt:** syntax LDAP và kiểu Java do JNDI trả về là hai lớp khác nhau. Một giá trị biểu diễn số nguyên trong LDAP có thể vẫn được trả về dưới dạng `String`; việc chuyển thành `int` hay `long` là chính sách của mapper Java.

### 4.1. Directory String

Directory String biểu diễn văn bản Unicode theo cú pháp LDAP. Một attribute type dùng Directory String có thể lựa chọn quy tắc so khớp bỏ qua hoa/thường hoặc phân biệt hoa/thường.

Ví dụ:

~~~ldif
cn: Tran Thi Lan
description: Nhan vien phong ky thuat
~~~

Không có quy tắc “mọi Directory String đều so sánh không phân biệt hoa/thường”: hành vi phụ thuộc `EQUALITY` và `SUBSTR` được định nghĩa cho **attribute type cụ thể**.

### 4.2. Integer

Integer biểu diễn giá trị số nguyên theo syntax LDAP, nhưng **không tự tương ứng với Java `Integer`**.

Ví dụ trong một schema POSIX có `uidNumber`:

~~~ldif
uidNumber: 10042
~~~

Khi map, nên parse có kiểm tra giới hạn, không ép trực tiếp đối tượng JNDI thành `Integer`. So thứ tự số phải dựa vào matching rule của LDAP, không dùng `String.compareTo(...)`.

### 4.3. Boolean

Giá trị Boolean theo LDAP có dạng ký tự được chuẩn hóa bởi syntax và matching rule (điển hình `TRUE`/`FALSE`). Không tự giả định server chấp nhận mọi cách viết mà Java có thể parse.

~~~text
TRUE
FALSE
~~~

Một phép thử trên directory thực tế sẽ cho biết những biến thể nào được syntax validator của server chấp nhận. Không dùng `Boolean.parseBoolean(...)` một cách âm thầm nếu ứng dụng cần phát hiện giá trị bất hợp lệ, vì phương thức đó trả `false` cho nhiều chuỗi không phải `true`.

### 4.4. Generalized Time

Syntax này biểu diễn mốc thời gian; một dạng thường gặp:

~~~text
20261126143000Z
~~~

LDAP Generalized Time có quy tắc cú pháp và diễn giải offset/độ chính xác riêng. Một giá trị thời gian không phải chuỗi `yyyy-MM-dd` thông thường, cũng không tự động được JNDI chuyển thành `java.time.Instant`. Thuộc tính `createTimestamp` thường là **operational attribute** do directory server quản lý, không phải trường để client tự ghi.

### 4.5. Distinguished Name

Một giá trị DN mô tả danh tính/vị trí entry trong Directory Information Tree:

~~~ldif
member: uid=lan,ou=people,dc=example,dc=org
~~~

Server dùng syntax và matching rule DN để diễn giải thành phần tên phù hợp với schema. Không thể coi giá trị này tương đương một chuỗi ký tự bất kỳ; trong Java, khi cần thao tác DN, dùng `LdapName` hoặc `LdapNameBuilder` thay vì cắt chuỗi theo dấu phẩy.

### 4.6. Octet String và binary

Một giá trị `jpegPhoto` thường chứa bytes của ảnh, không phải văn bản. Khi đọc qua JNDI, provider có thể trả `byte[]`; nếu provider không tự nhận diện một attribute tùy chỉnh là binary, cần cấu hình xử lý kiểu theo tài liệu JNDI/server.

Không sử dụng `toString()` để đổi `byte[]` thành ảnh hoặc text. Với LDIF, dữ liệu không thể in trực tiếp thường được biểu diễn qua Base64 với cú pháp `::`; điều đó là **cách biểu diễn trong LDIF**, không phải một matching rule của LDAP.

## 5. Matching rule là gì?

**Matching rule** là một quy tắc server dùng để kiểm tra quan hệ giữa *assertion value* trong filter và giá trị thực của attribute. Nó còn có thể quy định các bước chuẩn hóa để hai biểu diễn khác nhau được xem là khớp.

Ba loại phổ biến trong định nghĩa attribute type:

| Rule tại attribute type | Phép tìm kiếm thường gắn với nó | Ví dụ |
|---|---|---|
| `EQUALITY` | Filter equality `(uid=lan)` | So khớp hai giá trị theo nghĩa bằng nhau |
| `ORDERING` | Filter `(uidNumber>=1000)`, `(uidNumber<=2000)` | Xác định thứ tự theo syntax/rule |
| `SUBSTR` | Filter `(cn=*Lan*)` | So khớp một phần chuỗi nếu được hỗ trợ |

Còn có **approximate matching** `~=` và **extensible matching** `:=`; hành vi và mức hỗ trợ có thể phụ thuộc vào server/matching rule cụ thể. Không coi approximate search là chức năng bảo đảm có sẵn hoặc giống nhau giữa OpenLDAP, Active Directory và các directory khác.

Một syntax có thể có nhiều matching rule phù hợp. Ví dụ Directory String có thể được so với `caseIgnoreMatch` hoặc `caseExactMatch`; chỉ nhìn thấy syntax Directory String **không đủ** để biết filter equality sẽ phân biệt chữ hoa hay không.

### Matching rule áp dụng ở đâu?

~~~mermaid
flowchart TD
    A["Attribute type trong schema"] --> B["SYNTAX: giá trị hợp lệ"]
    A --> C["EQUALITY: so bằng"]
    A --> D["ORDERING: so thứ tự"]
    A --> E["SUBSTR: so chuỗi con"]
    F["SearchRequest: base + scope + filter"] --> G["Directory server"]
    B --> G
    C --> G
    D --> G
    E --> G
    G --> H["Các entry khớp và được ACL cho phép"]
~~~

Matching rule là **một phần của schema và khả năng server**. Spring Data LDAP không thể đổi ngữ nghĩa so khớp của `cn` chỉ bằng cách khai báo `String` hay `StringPath` trong Java.

## 6. Các matching rule phổ biến và cách đọc đúng

| Rule | Ngữ nghĩa chính | Ứng dụng điển hình |
|---|---|---|
| `caseIgnoreMatch` | So chuỗi không phân biệt hoa/thường theo chuẩn hóa của rule | Nhiều thuộc tính tên |
| `caseExactMatch` | So chuỗi có phân biệt hoa/thường theo rule | Một số mã định danh cần phân biệt chữ hoa |
| `caseIgnoreSubstringsMatch` | Substring không phân biệt hoa/thường theo rule | Tìm tên chứa từ khóa |
| `caseExactSubstringsMatch` | Substring với phân biệt hoa/thường theo rule | Trường cần phân biệt chữ hoa |
| `integerMatch` | So bằng theo giá trị số nguyên | Attribute syntax Integer |
| `integerOrderingMatch` | So thứ tự số nguyên | Ngưỡng số, cấp bậc, số thứ tự |
| `booleanMatch` | So Boolean | Attribute cú pháp Boolean |
| `generalizedTimeMatch` | So thời điểm theo cú pháp Generalized Time | Thuộc tính thời gian |
| `generalizedTimeOrderingMatch` | So thứ tự thời gian | Tìm trước/sau thời điểm |
| `distinguishedNameMatch` | So DN theo cú pháp và matching rules DN | Tham chiếu thành viên nhóm |
| `octetStringMatch` | So chuỗi byte | Một số thuộc tính binary |

Đây là các quy tắc được định nghĩa trong bộ chuẩn LDAP; **không phải mọi attribute type đều dùng mọi rule**. Phải đọc `attributeTypes` của directory để biết một trường cụ thể hỗ trợ cách so nào.

### 6.1. caseIgnoreMatch không đồng nghĩa String.equalsIgnoreCase

Ví dụ một server có `cn` được định nghĩa với equality rule `caseIgnoreMatch`:

~~~ldif
cn: Tran Thi Lan
~~~

Filter:

~~~text
(cn=tran thi lan)
~~~

có thể khớp với entry dù cách viết chữ hoa khác nhau, tùy schema và cách server thực hiện rule. Tuy nhiên, không mô phỏng hành vi LDAP bằng `String.equalsIgnoreCase` rồi kỳ vọng luôn tương đương. Matching rule LDAP còn có các quy tắc chuẩn hóa ký tự và khoảng trắng theo chuẩn; cách xử lý Unicode và giá trị được server triển khai có thể khác phép so sánh Java đơn giản.

**Không suy từ “case insensitive” rằng mọi dấu câu, dấu tiếng Việt hoặc khoảng trắng đều bị bỏ qua.** Những thay đổi đó phải được kiểm thử dựa trên rule và server cụ thể.

### 6.2. caseExactMatch

Nếu một attribute dùng `caseExactMatch`, các biến thể khác hoa/thường có thể không khớp. Điều này hữu ích với một số mã định danh, nhưng không biến giá trị thành khoá có tính duy nhất tuyệt đối trên toàn DIT. Quy tắc unique constraint và ranh giới DN là chuyện khác.

### 6.3. integerMatch và integerOrderingMatch

Với một attribute số:

~~~text
uidNumber: 10042
~~~

Filter `(uidNumber>=1000)` dựa trên **ordering matching rule**, không so sánh lexicographic như chuỗi Java. Nếu attribute type không có ordering rule thích hợp hoặc server không hỗ trợ phép so đó, filter có thể không cho kết quả mong muốn và cần kiểm tra diagnostic result từ server.

### 6.4. distinguishedNameMatch

Với nhóm:

~~~ldif
dn: cn=developers,ou=groups,dc=example,dc=org
objectClass: top
objectClass: groupOfNames
cn: developers
member: uid=lan,ou=people,dc=example,dc=org
~~~

Thuộc tính `member` tham chiếu DN. Phép lọc bằng DN không đơn giản là so hai chuỗi byte: server áp dụng syntax và matching rule DN. Khi ứng dụng dựng DN phải escape RDN hợp lệ; khi người dùng đổi DN, directory không mặc nhiên cập nhật mọi thuộc tính `member` trừ khi có cơ chế quản lý tham chiếu được cấu hình.

### 6.5. generalizedTimeOrderingMatch

Phép so khoảng thời gian chỉ chính xác khi server hỗ trợ matching rule phù hợp và giá trị assertion hợp lệ với syntax. Nếu `createTimestamp` được trả về dưới dạng chuỗi, hãy parse nó thành thời điểm thực trong Java khi cần tính toán; không chỉ so `String.compareTo(...)` trên hai biểu diễn có timezone khác nhau.

## 7. Syntax khác kiểu Java và khác định dạng hiển thị

Cần nhìn qua ba tầng:

~~~text
LDAP trên mạng: giá trị theo ASN.1/BER và cú pháp LDAP
      ↓
JNDI provider: String, byte[] hoặc kiểu mà provider cung cấp
      ↓
Ứng dụng Java: String / Integer / Instant / LdapName / DTO
~~~

Ví dụ mapper đơn giản đọc chuỗi LDAP và chuyển sang số:

~~~java
import javax.naming.NamingException;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;

public final class LdapValueReaders {

    private LdapValueReaders() {
    }

    public static int requiredInteger(
            Attributes attrs, String attributeId)
            throws NamingException {

        Attribute attr = attrs.get(attributeId);
        if (attr == null || attr.size() != 1) {
            throw new IllegalStateException(
                    "Expected exactly one value: " + attributeId);
        }

        Object raw = attr.get();
        if (!(raw instanceof String text)) {
            throw new IllegalStateException(
                    "Expected LDAP text form for " + attributeId);
        }

        try {
            return Integer.parseInt(text);
        } catch (NumberFormatException ex) {
            throw new IllegalStateException(
                    "Invalid integer or out of Java int range: "
                            + attributeId, ex);
        }
    }
}
~~~

Ví dụ yêu cầu `Integer`-like syntax nhưng vẫn kiểm tra `String` vì đó là kiểu JNDI provider thường trả. Nếu dữ liệu có giá trị vượt phạm vi `int`, cân nhắc `long` hoặc `BigInteger` theo yêu cầu nghiệp vụ.

### Chuyển Generalized Time sang Instant

Với một định dạng cụ thể `yyyyMMddHHmmssZ` (trong đó `Z` là ký hiệu UTC trong LDAP), có thể parse bằng formatter được định nghĩa rõ:

~~~java
import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.format.DateTimeFormatter;

public final class LdapTimeReaders {

    private static final DateTimeFormatter UTC_SECONDS =
            DateTimeFormatter.ofPattern("uuuuMMddHHmmssX");

    private LdapTimeReaders() {
    }

    public static Instant parseUtcSeconds(String raw) {
        return OffsetDateTime.parse(raw, UTC_SECONDS)
                .toInstant();
    }
}
~~~

Đây là parser cho **một dạng Generalized Time hẹp** với giây và timezone ký hiệu `Z`. LDAP Generalized Time cho phép các dạng khác (ví dụ offset và phần giây) theo quy chuẩn; parser production phải lựa chọn hoặc hỗ trợ rõ những dạng mà directory trả về. Tránh giả vờ rằng mọi giá trị `Generalized Time` đều có thể parse bằng formatter trên.

### Chuyển DN sang đối tượng tên LDAP

~~~java
import javax.naming.InvalidNameException;
import javax.naming.ldap.LdapName;

public static LdapName parseMemberDn(String ldapValue)
        throws InvalidNameException {
    return new LdapName(ldapValue);
}
~~~

Đoạn trên là một phương thức minh họa, cần đặt vào class utility trong dự án. `LdapName` hỗ trợ thao tác với các thành phần DN thay vì xử lý bằng `split(",")`, vốn dễ sai khi RDN chứa dấu phẩy đã escape hoặc tên nhiều thành phần.

**Cẩn trọng:** parse DN đúng cú pháp **không** xác nhận DN đó nằm trong OU được phép, entry tồn tại hay người gọi được quyền truy cập. Đó là các kiểm tra riêng.

## 8. Attribute đơn trị và đa trị

Một attribute type có thể có `SINGLE-VALUE`. Khi được khai báo, server kỳ vọng entry có tối đa một giá trị cho attribute đó. Nếu không có `SINGLE-VALUE`, attribute có thể có nhiều giá trị, nhưng object class/schema/policy khác vẫn có thể đặt thêm giới hạn.

Ví dụ LDAP nhiều giá trị:

~~~ldif
telephoneNumber: +84 28 1234 5678
telephoneNumber: +84 90 111 2222
~~~

Trong JNDI:

~~~java
Attribute phones = attrs.get("telephoneNumber");
if (phones != null) {
    NamingEnumeration<?> values = phones.getAll();
    try {
        while (values.hasMore()) {
            Object value = values.next();
            // Kiểm tra kiểu và xử lý từng giá trị.
        }
    } finally {
        values.close();
    }
}
~~~

Đoạn minh họa giả định `attrs` là một đối tượng `Attributes` đã được khai báo và import `Attribute`/`NamingEnumeration`. Không dùng `attr.get()` rồi coi đó là “giá trị đầu tiên” có thứ tự nghiệp vụ; giá trị thuộc tính đa trị của LDAP thông thường là **tập giá trị không thứ tự**.

**Syntax và cardinality là hai yêu cầu khác nhau:** hai số điện thoại có thể dùng cùng syntax Directory String/Telephone Number nhưng số phần tử của attribute được quyết định bởi định nghĩa attribute type và các ràng buộc khác.

## 9. LDAP filter: dùng matching rule đúng ý nghĩa

LDAP filter có một số dạng cơ bản:

| Filter | Ý nghĩa | Điều kiện thực sự |
|---|---|---|
| `(uid=lan)` | Equality | Dùng equality matching rule của `uid` |
| `(uid=*)` | Presence | Kiểm tra attribute hiện diện, không tìm chuỗi ký tự `*` |
| `(cn=*Lan*)` | Substring | Cần substring matching rule phù hợp |
| `(uidNumber>=1000)` | Greater-or-equal | Cần ordering matching rule |
| `(uidNumber<=2000)` | Less-or-equal | Cần ordering matching rule |
| `(cn~=Lan)` | Approximate match | Phụ thuộc rule/server; không bảo đảm tương đương substring |
| `(&(objectClass=inetOrgPerson)(uid=lan))` | AND | Cả hai điều kiện phải khớp |
| `(|(uid=lan)(uid=binh))` | OR | Một trong hai điều kiện khớp |
| `(!(uid=lan))` | NOT | Phủ định theo ngữ nghĩa filter LDAP |

Dấu `*` trong `(cn=*Lan*)` là **ký tự điều khiển filter substring**, không phải ký tự phải xuất hiện trong giá trị `cn`. Nếu cần tìm dấu sao theo nghĩa literal, phải escape nó theo cú pháp LDAP filter, hoặc để framework xử lý giá trị assertion.

### LDAP filter escaping khác DN escaping

Theo RFC 4515, các ký tự trong **giá trị filter** cần escape khi dùng biểu diễn filter chuỗi:

~~~text
*       -> \2a
(       -> \28
)       -> \29
\       -> \5c
NUL     -> \00
~~~

Ví dụ muốn tìm UID có dấu sao literal:

~~~text
(uid=lan\2a)
~~~

Filter trên khác với `(uid=lan*)` (substring). Đồng thời, dấu phẩy và dấu bằng trong DN phải được escape theo **cú pháp DN** (RFC 4514), chứ không áp dụng nguyên quy tắc escaping filter.

Không tự nối:

~~~java
String unsafeFilter = "(uid=" + userInput + ")";
~~~

Nếu user nhập `*`, ngoặc hoặc dấu backslash, filter có thể bị thay đổi ý nghĩa hoặc trở nên không hợp lệ. Hãy dùng API Spring LDAP xây filter từ giá trị do người dùng cung cấp.

### Extensible matching

LDAP còn có filter dạng extensible match:

~~~text
(attribute:matchingRuleOID:=assertionValue)
~~~

Một số dạng có thể dùng tên/OID matching rule và cờ `:dn` để xem xét thành phần DN theo ngữ nghĩa filter tương ứng. Việc có thể sử dụng extensible matching cụ thể còn phụ thuộc schema và khả năng server; **không đưa một matching rule OID bất kỳ vào filter rồi giả định mọi server đều hỗ trợ**.

Trong Spring Data LDAP, nếu không có yêu cầu thực sự, hãy dùng filter equality, substring, presence và ordering được schema hỗ trợ qua builder thay vì tự xây extensible filter phức tạp.

## 10. Spring LDAP: tạo filter an toàn bằng LdapQueryBuilder

Ví dụ tìm user có `uid` khớp chính xác theo matching rule của attribute:

~~~java
import java.util.List;

import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.SearchScope;

import static org.springframework.ldap.query.LdapQueryBuilder.query;

public final class PersonDirectorySearch {

    private final LdapTemplate ldapTemplate;

    public PersonDirectorySearch(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<String> findCommonNames(String uid) {
        LdapQuery ldapQuery = query()
                .base("ou=people")
                .searchScope(SearchScope.SUBTREE)
                .attributes("cn")
                .where("objectClass").is("inetOrgPerson")
                .and("uid").is(uid);

        return ldapTemplate.search(
                ldapQuery,
                (AttributesMapper<String>) attrs ->
                        (String) attrs.get("cn").get()
        );
    }
}
~~~

Trong ví dụ:

- `base("ou=people")` là search base tương đối khi `ContextSource` đã cấu hình `spring.ldap.base=dc=example,dc=org`.
- `searchScope(SearchScope.SUBTREE)` cho phép tìm người dùng trong OU con nếu mô hình dữ liệu yêu cầu.
- `attributes("cn")` yêu cầu trả thuộc tính cần dùng, tránh lấy không cần thiết.
- `.and("uid").is(uid)` dùng API builder thay vì nối chuỗi giá trị của client.
- Equality semantics của `uid` vẫn do **matching rule trên LDAP server** quyết định.

Mapper trên cố ý ngắn gọn để tập trung vào filter; một ứng dụng production phải kiểm tra `attrs.get("cn")` có thể `null`, số giá trị và kiểu trả về. `cn` có thể bị ẩn bởi ACL hoặc không xuất hiện trong projection của truy vấn khác.

### Querydsl hoặc repository có thay matching rule không?

Không. Ví dụ:

~~~java
public interface DirectoryPersonRepository
        extends LdapRepository<DirectoryPerson> {

    List<DirectoryPerson> findByUid(String uid);
}
~~~

Phương thức `findByUid(...)` tạo điều kiện dựa trên mapping Java và LDAP. Nó không biến `uid` thành một attribute so sánh bằng `String.equals` trên client. Spring Data LDAP vẫn gửi truy vấn tương ứng để **server** áp dụng schema, matching rule và ACL.

Tương tự, nếu dùng Querydsl, Q-type giúp kiểm tra tên/kiểu thuộc tính tại compile-time, không xác định matching semantics của LDAP attribute. Không mặc nhiên áp dụng mọi phép toán Querydsl của JPA/SQL cho LDAP; cần xác nhận tập thao tác mà Spring Data LDAP hỗ trợ.

## 11. Khi thiếu matching rule hoặc dùng phép so không phù hợp

Không phải attribute type nào cũng khai báo `ORDERING` và `SUBSTR`. Nếu một attribute chỉ có `EQUALITY`, ứng dụng không được kỳ vọng filter `>=` hoặc substring luôn có ngữ nghĩa hữu ích.

Ví dụ schema giả định:

~~~text
( 1.3.6.1.4.1.99999.1.2
  NAME 'appOpaqueToken'
  EQUALITY octetStringMatch
  SYNTAX 1.3.6.1.4.1.1466.115.121.1.40
  SINGLE-VALUE )
~~~

Tính năng trong ví dụ:

- `EQUALITY octetStringMatch`: server có cách so bằng bytes phù hợp.
- Không có `ORDERING`: không tự dùng `(appOpaqueToken>=...)`.
- Không có `SUBSTR`: không xem substring search là được hỗ trợ.
- Attribute là nhị phân: không ép tùy tiện thành `String` rồi tạo filter.

Khi phép so không được định nghĩa hoặc assertion không phù hợp, server có thể trả **kết quả không khớp** theo logic đánh giá filter hoặc lỗi như `inappropriateMatching (18)`, tùy loại thao tác và cách triển khai. Không coi kết quả rỗng tự động là “attribute không tồn tại”.

### Không dùng matching rule để kiểm tra duy nhất

`caseIgnoreMatch` xác định cách so bằng, nhưng không tự tạo một unique index hoặc quy tắc “mọi UID là duy nhất toàn cây”. Hai entry dưới các OU khác nhau vẫn có thể có `uid=lan`. Việc xác định ranh giới duy nhất thuộc DN, DIT, chính sách directory hoặc nghiệp vụ.

## 12. Đọc schema thực tế từ subschemaSubentry

Để biết thuộc tính đang dùng có syntax và matching rule nào, hãy đọc **schema directory đang chạy**, không chỉ suy từ tên field.

Quy trình:

1. Kết nối tới directory qua LDAPS/StartTLS với tài khoản có quyền đọc schema theo chính sách.
2. Chọn entry thuộc vùng dữ liệu cần nghiên cứu và đọc `subschemaSubentry` của nó.
3. Lấy DN được trả về rồi truy vấn subschema entry đó với scope `base`.
4. Đọc `attributeTypes` và `objectClasses`; tra định nghĩa cho các attribute/entry đang dùng.
5. Ghi lại OID syntax, EQUALITY, ORDERING, SUBSTR, SINGLE-VALUE, các lớp cho phép dùng thuộc tính và sự khác biệt theo server.

Ví dụ lệnh LDAP read-only:

~~~bash
ldapsearch -LLL -x \
  -H ldaps://directory.example.org:636 \
  -D "uid=svc-reader,ou=services,dc=example,dc=org" \
  -W \
  -b "uid=lan,ou=people,dc=example,dc=org" \
  -s base "(objectClass=*)" subschemaSubentry
~~~

Sau khi nhận DN của subschema entry, ví dụ server trả `cn=schema`:

~~~bash
ldapsearch -LLL -x \
  -H ldaps://directory.example.org:636 \
  -D "uid=svc-reader,ou=services,dc=example,dc=org" \
  -W \
  -b "cn=schema" \
  -s base "(objectClass=*)" attributeTypes objectClasses
~~~

**`cn=schema` chỉ là ví dụ.** Cần thay bằng DN thực nhận từ `subschemaSubentry`. Một directory có thể giới hạn quyền đọc schema, có nhiều subschema hoặc sử dụng cách quản trị schema khác. Không sửa schema production trực tiếp từ ứng dụng để làm filter “chạy được”.

### Giải thích một dòng attributeTypes

Giả sử một bản ghi định nghĩa thuộc tính có dạng:

~~~text
( 1.3.6.1.4.1.99999.1.1
  NAME 'appStaffLevel'
  EQUALITY integerMatch
  ORDERING integerOrderingMatch
  SYNTAX 1.3.6.1.4.1.1466.115.121.1.27
  SINGLE-VALUE )
~~~

Ứng dụng có thể suy ra:

- Giá trị phải hợp cú pháp Integer của server.
- Filter equality có ngữ nghĩa so số bằng nhau.
- Filter `>=` và `<=` có ordering rule phù hợp.
- Không nên viết substring filter vì không có SUBSTR.
- DTO Java phải tính đến trường hợp attribute không hiện diện và lỗi chuyển đổi, dù `SINGLE-VALUE` ngăn có nhiều giá trị tại server.

Đây là điểm xuất phát để thiết kế mapping, không thay thế kiểm thử thực tế với server.

## 13. Khi nào cần định nghĩa attribute type tùy chỉnh?

Trong đa số bài toán nhân sự, nên ưu tiên attribute type và object class tiêu chuẩn có sẵn. Chỉ định nghĩa schema extension khi dữ liệu nghiệp vụ không có cách biểu diễn phù hợp, và tổ chức có quy trình quản trị OID/schema rõ ràng.

Ví dụ thuộc tính `appStaffLevel` và auxiliary class **minh họa**:

~~~text
( 1.3.6.1.4.1.99999.1.1
  NAME 'appStaffLevel'
  DESC 'Illustrative numeric staff level'
  EQUALITY integerMatch
  ORDERING integerOrderingMatch
  SYNTAX 1.3.6.1.4.1.1466.115.121.1.27
  SINGLE-VALUE )

( 1.3.6.1.4.1.99999.2.1
  NAME 'appStaffMetadata'
  SUP top
  AUXILIARY
  MAY ( appStaffLevel ) )
~~~

Để sử dụng thật:

1. Đăng ký và quản lý OID thuộc quyền của tổ chức; **không dùng nhánh OID giả định này** trên production.
2. Đưa định nghĩa attribute type và object class vào quy trình thay đổi schema phù hợp directory server.
3. Xác minh auxiliary class được phép áp dụng cho structural class người dùng theo schema/DIT content rule của server.
4. Bổ sung `objectClass: appStaffMetadata` cho entry phù hợp và gán giá trị `appStaffLevel` theo quy tắc.
5. Kiểm thử Add/Modify/Search và ordering; chuẩn bị migration/rollback trước khi thay đổi dữ liệu thật.

Entry minh họa **chỉ hợp lệ nếu schema extension đã được cài đặt và được server cho phép**:

~~~ldif
dn: uid=lan,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
objectClass: appStaffMetadata
uid: lan
cn: Tran Thi Lan
sn: Tran
appStaffLevel: 5
~~~

Không cố thêm field `@Attribute(name = "appStaffLevel")` trong Java rồi kỳ vọng server tự chấp nhận một attribute type chưa được khai báo.

## 14. Lỗi thường gặp do syntax và matching rule

| Mã LDAP / hiện tượng | Ý nghĩa có thể | Cách chẩn đoán |
|---|---|---|
| `undefinedAttributeType (17)` | Server không biết attribute type được dùng | Tra `attributeTypes`, tên/OID và schema |
| `invalidAttributeSyntax (21)` | Giá trị không phù hợp cú pháp attribute | Kiểm tra syntax và assertion/value |
| `inappropriateMatching (18)` | Matching rule không phù hợp cho thao tác/thuộc tính | Kiểm tra EQUALITY/ORDERING/SUBSTR và rule server hỗ trợ |
| `constraintViolation (19)` | Vi phạm ràng buộc như cardinality hoặc policy khác | Kiểm tra SINGLE-VALUE, kích thước và constraint |
| `objectClassViolation (65)` | Thuộc tính không được object class cho phép hoặc thiếu MUST | Tra chuỗi objectClass và MUST/MAY |
| `invalidDNSyntax (34)` | DN/RDN không hợp cú pháp | Dùng parser/builder DN đúng chuẩn |
| Filter trả rỗng bất ngờ | Base/scope sai, attribute bị ACL ẩn, rule khác dự kiến | Xem search base, quyền và schema |
| Filter substring rất chậm | Truy vấn rộng, index không phù hợp, biểu thức tốn tài nguyên | Thu hẹp base, tối ưu filter/index |
| `ClassCastException` trong Java | Mapper giả định `String` với binary `byte[]` | Kiểm tra kiểu JNDI và syntax |
| `NumberFormatException` | Parse sai kiểu/range số | Chuyển đổi có kiểm tra theo định dạng server trả |

Không giả định **mỗi lỗi luôn có một mã duy nhất** trên mọi LDAP server. Chẩn đoán phụ thuộc tính năng, thao tác cụ thể và cách server thực thi schema.

### Ví dụ sai kiểu dù Java compile thành công

~~~java
// Không đảm bảo đúng: JNDI LDAP không bắt buộc trả Integer.
Integer number = (Integer) attrs.get("uidNumber").get();
~~~

Sửa theo hướng:

~~~java
Object raw = attrs.get("uidNumber").get();
if (!(raw instanceof String text)) {
    throw new IllegalStateException("Unexpected LDAP value type");
}
int number = Integer.parseInt(text);
~~~

Trước hai đoạn trên, phải bảo đảm `attrs.get("uidNumber")` khác null và có số giá trị hợp lệ. Nếu provider trả `byte[]` do cấu hình, cần nhánh xử lý riêng thay vì ép mù.

### Ví dụ lọc bằng Java sau khi tải dữ liệu quá rộng

Một sai lầm khác là tải tất cả entry dưới `dc=example,dc=org` rồi dùng `String.toLowerCase()` và so sánh trong Java. Cách này vừa có thể làm sai LDAP matching semantics, vừa tăng truyền dữ liệu, vượt ranh giới tenant/OU và tạo nguy cơ lộ thông tin. Nên để **directory server** thực hiện filter được xây an toàn, trong search base và ACL phù hợp.

## 15. Hiệu năng: matching rule, index và phạm vi tìm kiếm

Matching rule xác định cách so khớp; **index** quyết định server có thể thực hiện phép tìm kiếm hiệu quả đến mức nào. Hai yếu tố liên quan nhưng không đồng nhất.

Ví dụ:

~~~text
(uid=lan)
(cn=*Lan*)
(uidNumber>=1000)
~~~

- Equality filter theo `uid` có thể được hưởng lợi từ equality index nếu server hỗ trợ và cấu hình phù hợp.
- Substring filter có wildcard đầu hoặc giữa thường đắt hơn và phụ thuộc substring index.
- Ordering filter trên attribute có rule phù hợp vẫn có thể tốn tài nguyên nếu không có index hữu ích hoặc base quá rộng.

Một số thực hành:

1. Chọn **search base nhỏ nhất** vẫn bao phủ kết quả hợp lệ; không tìm xuyên nhiều OU/tenant không liên quan.
2. Đặt `SearchScope.ONELEVEL` hoặc `SUBTREE` theo cấu trúc DIT thật.
3. Kết hợp filter objectClass và các thuộc tính cần thiết; escape giá trị từ client.
4. Chỉ yêu cầu thuộc tính cần trả bằng `attributes(...)` trong `LdapQueryBuilder`.
5. Đặt count/time limit thích hợp, theo dõi latency và lỗi LDAP server.
6. Phối hợp với quản trị directory để kiểm tra index và log search thực tế; không dựa trên suy đoán kiểu SQL.
7. Với truy vấn trả kết quả lớn, nghiên cứu phân trang LDAP theo khả năng server và Spring LDAP; count limit không phải cơ chế tự động tải hết dữ liệu.

Cùng một filter có thể cho hiệu năng và tập kết quả khác nhau khi chạy với tài khoản bind có ACL khác nhau hoặc trên server có cấu hình/schema khác nhau.

## 16. Kiểm thử xác minh syntax và matching rule

Unit test Java có thể xác minh mapper, parser hoặc code xây filter, nhưng **không chứng minh được directory server áp dụng đúng matching rule**. Cần integration test với một LDAP directory độc lập, schema đủ và dữ liệu fixture phù hợp.

### Ma trận kiểm thử gợi ý

| Kiểm thử | Cách bố trí | Điều cần xác nhận |
|---|---|---|
| Equality không phân biệt hoa/thường | Entry có `cn: Tran Thi Lan` | Filter case variant khớp theo rule của `cn` |
| Equality phân biệt hoa/thường | Attribute test có `caseExactMatch` | Khác chữ hoa cho kết quả theo đúng schema |
| Integer ordering | Attribute tùy chỉnh Integer hoặc `uidNumber` theo schema POSIX | `>=`/`<=` dựa trên giá trị số, không phải thứ tự chuỗi |
| Syntax sai | Thử Add/Modify Integer bằng chuỗi không hợp lệ | Server từ chối với lỗi schema/syntax phù hợp |
| Single-value | Thử ghi hai giá trị vào attribute `SINGLE-VALUE` | Server từ chối theo chính sách/schema |
| Substring | Attribute có SUBSTR rule | Filter `*Lan*` hoạt động theo rule |
| Không có SUBSTR | Attribute test chỉ có EQUALITY | Không giả định substring trả kết quả |
| DN matching | Nhóm có `member` | So khớp DN phù hợp; kiểm tra cách server chuẩn hóa |
| Generalized Time | Attribute thời gian hợp lệ | Ordering theo thời điểm khi được schema hỗ trợ |
| Binary | Entry có attribute nhị phân | Mapper giữ `byte[]` và không biến thành text |
| Filter escaping | Client gửi ký tự `*` hoặc dấu ngoặc | Không làm thay đổi cấu trúc filter ngoài ý định |
| ACL và projection | Cùng entry với hai tài khoản/quyền khác nhau | Không nhầm thuộc tính không thấy với không tồn tại |

### Integration test qua LdapTemplate

Một ví dụ kiểm thử truy vấn equality trực tiếp qua Spring LDAP:

~~~java
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.test.context.ActiveProfiles;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.springframework.ldap.query.LdapQueryBuilder.query;

@SpringBootTest
@ActiveProfiles("test")
class LdapMatchingRuleIntegrationTest {

    @Autowired
    private LdapTemplate ldapTemplate;

    @Test
    void matchesCommonNameAccordingToDirectorySchema() {
        LdapQuery ldapQuery = query()
                .base("ou=people")
                .attributes("uid")
                .where("cn").is("tran thi lan");

        List<String> uids = ldapTemplate.search(
                ldapQuery,
                (AttributesMapper<String>) attrs ->
                        (String) attrs.get("uid").get());

        assertEquals(List.of("lan"), uids);
    }
}
~~~

Test giả định fixture `cn: Tran Thi Lan`, `uid: lan`, `ContextSource` có base DN đúng và directory dùng matching rule với semantics phù hợp cho `cn`. Đây là **test tích hợp thật**, không phải unit test: kết quả còn phụ thuộc server, ACL, schema và dữ liệu đã nạp. Không chạy thử Add/Modify cố tình sai syntax trên production directory.

### Truy vấn chẩn đoán bằng ldapsearch

~~~bash
ldapsearch -LLL -x \
  -H ldaps://directory.example.org:636 \
  -D "uid=svc-reader,ou=services,dc=example,dc=org" \
  -W \
  -b "ou=people,dc=example,dc=org" \
  -s sub "(cn=tran thi lan)" dn cn
~~~

Lệnh này giúp so sánh trực tiếp server search với truy vấn Spring LDAP. `-W` hỏi mật khẩu tương tác, tránh để password trong shell history. LDAP URL, DN và tổ chức OU ở ví dụ là giả định, cần điều chỉnh cho directory test. Khi so kết quả, bảo đảm dùng **cùng bind identity, base, scope và filter**.

## 17. Những hiểu lầm thường gặp

- **“LDAP attribute nào cũng là String.”** Không. Syntax có số, boolean, thời gian, DN và dữ liệu nhị phân; JNDI mapping cũng cần kiểm tra kiểu thực tế.
- **“JNDI trả `String` nghĩa là syntax của attribute là Directory String.”** Không. Nhiều giá trị Integer và Generalized Time cũng có thể được provider trả dưới dạng chuỗi.
- **“Directory String luôn bỏ qua hoa/thường.”** Không. Equality rule của attribute quyết định.
- **“`caseIgnoreMatch` giống hệt `String.equalsIgnoreCase()`.”** Không. LDAP có cách chuẩn hóa và xử lý ký tự riêng.
- **“Có `SYNTAX Integer` là filter `>=` chắc chắn hoạt động.”** Không. Phải có ordering rule tương thích và server hỗ trợ.
- **“SUBSTR là thao tác Java `contains()`.”** Không. Server thực thi substring theo matching rule/normalization.
- **“`SINGLE-VALUE` là cùng khái niệm `MUST`.”** Không. SINGLE-VALUE giới hạn số phần tử; MUST yêu cầu thuộc tính hiện diện theo object class.
- **“Matching rule quyết định quyền truy cập.”** Không. ACL là lớp riêng.
- **“Escape DN bằng quy tắc filter.”** Không. RFC 4514 và RFC 4515 có cú pháp khác nhau.
- **“`findByUid` trong repository bảo đảm UID duy nhất toàn directory.”** Không. DN/search base và chính sách duy nhất cần được thiết kế.
- **“Gắn `@Attribute` trong Java là tạo attribute type mới.”** Không. Schema do directory quản lý.
- **“Unit test dùng BasicAttributes thay thế được schema test.”** Không. `BasicAttributes` là đối tượng Java; nó không thực thi matching rule/schema của LDAP server.

## 18. Bài tập thực hành

**Bối cảnh:** ứng dụng Spring Data LDAP lưu người dùng dưới `ou=people,dc=example,dc=org`. Nhóm cần tìm người dùng theo `cn`, thống kê theo `uidNumber` nếu có schema POSIX, và nghiên cứu một thuộc tính tùy chỉnh `appStaffLevel`.

Thực hiện:

1. Từ `subschemaSubentry`, tìm định nghĩa `cn`, `uid`, `member` và một attribute số đang có trên server. Ghi OID, SYNTAX, EQUALITY, ORDERING, SUBSTR.
2. So sánh kết quả `(cn=Tran Thi Lan)`, `(cn=tran thi lan)` và `(cn=*Lan*)` trên directory test, giải thích từng matching rule.
3. Tạo một entry `inetOrgPerson` hợp lệ với `cn`, `sn`, `uid`; thêm một thuộc tính optional chỉ khi schema cho phép.
4. Nếu server có schema POSIX, tạo fixture `uidNumber` hợp lệ và thử filter ordering; so sánh với kết quả so sánh chuỗi Java để thấy sự khác biệt.
5. Viết mapper kiểm tra kiểu JNDI trước khi parse số hoặc DN.
6. Kiểm tra `member` của một group và parse DN bằng `LdapName` thay vì `split(",")`.
7. Thử query có UID chứa ký tự dấu sao literal; dùng builder và so sánh với việc ghép filter thô.
8. Nếu có môi trường schema test do quản trị viên cấp, thử định nghĩa `appStaffLevel` như ví dụ với **OID hợp lệ thuộc tổ chức** và auxiliary class cho phép, rồi chạy truy vấn ordering.
9. Thử thêm hai giá trị vào một attribute SINGLE-VALUE ở directory test và ghi nhận phản hồi.
10. Viết integration test Spring LDAP xác minh equality và ordering, cùng kiểm thử ACL/search base cho những thuộc tính nhạy cảm.
11. Giải thích vì sao `@Entry` và `@Attribute` không thay thế schema checking hay matching rule trên server.

**Tiêu chí hoàn thành:** người học phân biệt đúng các tầng schema, đọc được định nghĩa attribute type, chọn phép so phù hợp với matching rule, xử lý đúng kiểu Java và kiểm chứng bằng LDAP server thật.

## 19. Tổng kết và tài liệu tham khảo

Đối với mỗi LDAP attribute, cần trả lời ba câu hỏi riêng: **giá trị có syntax nào; server so khớp bằng matching rule nào; entry có được phép mang thuộc tính đó không?** Syntax ảnh hưởng tới dữ liệu hợp lệ, matching rule quyết định semantics tìm kiếm, object class và các ràng buộc schema quyết định tập thuộc tính; ACL quyết định quyền đọc/ghi.

Trong Spring Data LDAP, `LdapRepository`, `LdapTemplate` và ODM ánh xạ dữ liệu sang Java nhưng **không thay thế** syntax/matching rule của directory. Hãy xem `attributeTypes` thực tế khi có nghi ngờ; dựng filter qua API an toàn, parse giá trị JNDI có kiểm tra, giữ ranh giới DN và thử bằng directory test độc lập.

Nguồn tham khảo:

- [RFC 4512 — LDAP: Directory Information Models](https://www.rfc-editor.org/rfc/rfc4512): `attributeTypes`, `SYNTAX`, `EQUALITY`, `ORDERING`, `SUBSTR`, `SINGLE-VALUE` và `subschemaSubentry`.
- [RFC 4517 — LDAP: Syntaxes and Matching Rules](https://www.rfc-editor.org/rfc/rfc4517): Directory String, Integer, Generalized Time, Distinguished Name, các matching rule tiêu chuẩn.
- [RFC 4515 — LDAP: String Representation of Search Filters](https://www.rfc-editor.org/rfc/rfc4515): cú pháp filter, presence, substring, extensible matching và escaping.
- [RFC 4519 — LDAP: Schema for User Applications](https://www.rfc-editor.org/rfc/rfc4519): attribute types thông dụng như `cn`, `sn`, `uid`, `member`.
- [RFC 2798 — inetOrgPerson](https://www.rfc-editor.org/rfc/rfc2798): object class người dùng và các thuộc tính mở rộng.
- [Spring Data LDAP Reference](https://docs.spring.io/spring-data/ldap/reference/): ánh xạ ODM, repository và giới hạn thao tác truy vấn.
- [Spring LDAP Reference](https://docs.spring.io/spring-ldap/reference/): `LdapTemplate`, `LdapQueryBuilder`, mapping JNDI và truy vấn an toàn.
- [Java SE — javax.naming.directory.Attributes](https://docs.oracle.com/en/java/javase/17/docs/api/java.naming/javax/naming/directory/Attributes.html): API đọc attribute JNDI.
