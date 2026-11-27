# Attribute alias, display name và định danh chuẩn trong LDAP

Trong LDAP, thuộc tính như `cn`, `uid`, `mail` hoặc `displayName` xuất hiện trong entry, bộ lọc tìm kiếm và code Spring LDAP. Tuy nhiên, **tên thuộc tính nhìn thấy trong ứng dụng chưa chắc là định danh nền tảng của thuộc tính đó**. Schema LDAP định nghĩa mỗi **attribute type** bằng một **Object Identifier (OID)**, có thể gắn thêm một hoặc nhiều tên dễ đọc (descriptor). Người dùng giao diện còn có thể thấy một nhãn khác, chẳng hạn “Tên hiển thị”, không nhất thiết trùng với tên trong schema.

Bài học thuộc chương **Attribute và schema**, tập trung phân biệt ba lớp thông tin:

1. **Định danh chuẩn của attribute type:** OID trong schema.
2. **Tên và alias của attribute type:** các descriptor được khai báo trong trường `NAME` của schema.
3. **Display name:** có thể là **nhãn trên giao diện** hoặc là thuộc tính LDAP có tên thật là `displayName`. Hai ý nghĩa này hoàn toàn khác nhau.

Nắm vững các khái niệm trên giúp đọc schema chính xác, thiết kế ánh xạ dữ liệu ổn định và sử dụng `LdapTemplate`, `LdapClient` hoặc ODM trong Spring LDAP mà không nhầm giữa tên kỹ thuật với tên hiển thị.

## 1. Định danh attribute type: OID và descriptor

LDAP schema định nghĩa các loại thuộc tính. Một loại thuộc tính có **OID** là chuỗi số phân cấp, chẳng hạn:

```text
2.5.4.3
```

OID này định danh attribute type chuẩn **Common Name**, thường được gọi bằng descriptor `cn`. Định nghĩa schema có thể được biểu diễn gần như sau (rút gọn):

```text
( 2.5.4.3 NAME 'cn' SUP name )
```

Trong đó:

| Thành phần | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `2.5.4.3` | OID định danh attribute type | OID của `cn` |
| `NAME 'cn'` | Descriptor dễ đọc để tham chiếu attribute type | `cn` |
| `SUP name` | Kế thừa thuộc tính cha theo schema | Loại thuộc tính `name` |
| `DESC '...'`, nếu có | Lời mô tả dành cho người đọc schema | Một câu giải thích ý nghĩa thuộc tính |

**OID là định danh ổn định của loại thuộc tính**, còn descriptor là tên tiện dụng để viết bộ lọc, truy xuất attribute và cấu hình ứng dụng. Trên một server, descriptor phải được định nghĩa và không được mơ hồ giữa các loại thuộc tính; hai tên cùng trỏ về một OID chỉ khi schema khai báo chúng là tên của cùng attribute type.

Một số định danh quen thuộc:

| Attribute type | OID tiêu chuẩn | Vai trò thường gặp |
| --- | --- | --- |
| `cn` | `2.5.4.3` | Common name |
| `sn` | `2.5.4.4` | Surname |
| `uid` | `0.9.2342.19200300.100.1.1` | User identifier |
| `mail` | `0.9.2342.19200300.100.1.3` | Địa chỉ email |
| `displayName` | `2.16.840.1.113730.3.1.241` | Tên hiển thị, khi schema hỗ trợ |

Danh sách là các định danh trong schema chuẩn phổ biến; **một server có thể không nạp hoặc không cho phép dùng tất cả loại thuộc tính này**. Khi tích hợp hệ thống thật, phải đối chiếu với schema và các object class server đang áp dụng.

## 2. Attribute alias là gì?

Một attribute type có thể được khai báo với **nhiều descriptor** trong cùng mục `NAME`:

```text
( 1.3.6.1.4.1.99999.1.17
  NAME ( 'personCode' 'staffCode' )
  DESC 'Demo: internal person identifier'
  EQUALITY caseIgnoreMatch
  SYNTAX 1.3.6.1.4.1.1466.115.121.1.15
  SINGLE-VALUE )
```

> Đây là định nghĩa **giả định dùng để học**, bao gồm một OID minh họa. Không sử dụng OID này để triển khai schema thật. Khi tạo attribute type riêng cho doanh nghiệp, cần dùng nhánh OID được cấp hoặc được quản lý hợp lệ.

Trong ví dụ, `personCode` và `staffCode` là **hai tên của cùng một attribute type**, không phải hai trường khác nhau. Chúng có chung OID, syntax, matching rule và ràng buộc `SINGLE-VALUE`.

```text
             OID: 1.3.6.1.4.1.99999.1.17
                           │
              Một attribute type
                  ┌────────┴────────┐
                  │                 │
          NAME personCode     NAME staffCode
          (descriptor)        (alias descriptor)
```

Nếu server nạp schema trên, những điều kiện sau tham chiếu cùng **loại thuộc tính**:

```ldap
(personCode=HR-042)
```

```ldap
(staffCode=HR-042)
```

Theo giao thức LDAP, có thể tham chiếu loại thuộc tính bằng OID tương ứng:

```ldap
(1.3.6.1.4.1.99999.1.17=HR-042)
```

Ba cách biểu đạt dùng cùng loại thuộc tính nếu server hỗ trợ đúng schema. Quy tắc so khớp giá trị vẫn do **matching rule** quyết định.

Điểm cần ghi nhớ:

- **Alias không tạo thêm attribute hoặc giá trị.** Với ví dụ `SINGLE-VALUE`, không thể có một giá trị `personCode` và một giá trị `staffCode` khác nhau để lách giới hạn một giá trị.
- **Alias phải được đăng ký trong schema.** Không thể tự đặt tên khác trong code Spring LDAP rồi mong LDAP server hiểu tên mới.
- **Descriptor không nhất thiết là tên “đầy đủ”.** Các tên dạng `commonName` hoặc `surname` không tự động là alias chỉ vì giống cách diễn đạt bằng tiếng Anh; phải kiểm tra định nghĩa `NAME` của server.
- **Tên ưu tiên trong tài liệu và code cần nhất quán.** Dùng một descriptor phổ biến, đã xác nhận có trong schema. Việc server trả về tên nào trong kết quả có thể phụ thuộc implementation và tham số yêu cầu thuộc tính.
- **Không nhầm với LDAP alias entry.** Object class `alias` và attribute `aliasedObjectName` dùng cho cơ chế entry alias/định hướng tên khác; chúng không phải “attribute alias” được khai báo bằng nhiều descriptor trong `NAME`.

## 3. Display name có hai nghĩa thường gặp

### 3.1. Display name là nhãn giao diện

Trong màn hình quản trị tài khoản, ứng dụng có thể hiển thị:

| Nhãn người dùng nhìn thấy | Attribute kỹ thuật ứng dụng đọc | Định danh schema |
| --- | --- | --- |
| “Mã đăng nhập” | `uid` | `0.9.2342.19200300.100.1.1` |
| “Họ” | `sn` | `2.5.4.4` |
| “Email công việc” | `mail` | `0.9.2342.19200300.100.1.3` |
| “Tên hiển thị” | `displayName` *hoặc quy tắc ứng dụng* | Tùy nguồn dữ liệu |

Các nhãn như “Mã đăng nhập” hoặc “Email công việc” là **UI labels**, do ứng dụng quyết định để phù hợp ngôn ngữ và nghiệp vụ. Đổi nhãn “Email công việc” thành “Work email” **không đổi** tên attribute `mail`, OID hay dữ liệu LDAP.

Trong định nghĩa schema, trường `DESC` cũng là mô tả con người đọc được; nó **không có vai trò** tạo alias hoặc đặt nhãn mặc định bắt buộc cho mọi giao diện.

### 3.2. `displayName` là một attribute type cụ thể

LDAP cũng có attribute type chuẩn mang tên **`displayName`** (OID `2.16.840.1.113730.3.1.241`). Với schema hỗ trợ `inetOrgPerson`, thuộc tính này thường được dùng cho tên mà người dùng muốn nhìn thấy.

Ví dụ một entry:

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
displayName: Lan N. (Engineering)
```

Ở đây:

- `cn` và `displayName` là **hai attribute type khác nhau**, mỗi loại có OID và quy tắc schema riêng.
- `displayName: Lan N. (Engineering)` là **giá trị LDAP thật**, khác với việc ứng dụng tự gán nhãn “Tên hiển thị” cho `cn`.
- `uid=lan` trong DN dùng để định danh entry trong nhánh `ou=people`; sửa `displayName` **không tự động đổi DN**.
- Ứng dụng có thể chọn lấy `displayName` để hiển thị, rồi fallback sang `cn` nếu thuộc tính đó không có. Đây là **quy tắc của ứng dụng**, không phải hành vi tự động của LDAP.

Một bảng so sánh:

| Khái niệm | Là thuộc tính lưu trong LDAP? | Có OID attribute type? | Có thể đổi độc lập? |
| --- | --- | --- | --- |
| Nhãn UI “Tên hiển thị” | Không bắt buộc | Không | Có, bằng cấu hình giao diện |
| `displayName` | Có, nếu schema/object class cho phép | Có | Có thể sửa theo ACL và schema |
| Descriptor alias `staffCode` | Là tên tham chiếu một attribute type | Dùng chung OID của loại đó | Thay schema có thể ảnh hưởng client |
| DN `uid=lan,ou=people,...` | Định danh vị trí entry | Không phải attribute type đơn lẻ | Đổi bằng thao tác rename/move phù hợp |

## 4. Trường `NAME`, `DESC`, `OID` và `SINGLE-VALUE` không thay thế nhau

Khi đọc định nghĩa schema, hãy tách rõ vai trò:

```text
( 1.3.6.1.4.1.99999.1.17
  NAME ( 'personCode' 'staffCode' )
  DESC 'Demo: internal person identifier'
  EQUALITY caseIgnoreMatch
  SYNTAX 1.3.6.1.4.1.1466.115.121.1.15
  SINGLE-VALUE )
```

| Thành phần | Quy định điều gì? | Không nên hiểu thành |
| --- | --- | --- |
| OID | Định danh attribute type | Giá trị thuộc tính của một người |
| `NAME` | Một hay nhiều descriptor, gồm tên thay thế | Danh sách các giá trị thuộc tính |
| `DESC` | Mô tả schema cho người đọc | Alias hay tên UI bắt buộc |
| `SYNTAX` | Dạng dữ liệu được chấp nhận | Nhãn của trường |
| `EQUALITY` | Quy tắc so sánh khi kiểm tra bằng nhau | Ràng buộc số lượng giá trị |
| `SINGLE-VALUE` | Giới hạn tối đa một giá trị cho attribute type | Giới hạn số descriptor trong `NAME` |

**Object class** là ràng buộc khác: một loại entry có được sử dụng attribute type này hay không phụ thuộc các danh sách `MUST`/`MAY` trong object class hiệu lực. Dù tên descriptor và OID hợp lệ, việc thêm attribute vẫn có thể bị từ chối vì schema entry không cho phép, thiếu quyền hoặc vi phạm syntax.

**Attribute option không phải alias.** Ví dụ `cn;lang-vi` là một *attribute description* có option ngôn ngữ; `cn` vẫn là attribute type. Các option được server hỗ trợ theo schema và khả năng triển khai. Đừng dùng phần sau dấu chấm phẩy như tên thay thế tùy ý.

## 5. Kiểm tra định danh và alias trên LDAP server

Không nên suy đoán alias từ tên tài liệu, cách hiển thị của LDAP browser hoặc cách API trả key. Cách đáng tin là **đọc subschema** mà server công bố, khi server cho phép.

Quy trình phổ biến:

1. Đọc operational attribute `subschemaSubentry` từ một entry (hoặc Root DSE nếu server công bố) để biết DN của subschema áp dụng.
2. Tra cứu entry subschema đó và yêu cầu operational attribute `attributeTypes`.
3. Tìm định nghĩa theo OID hoặc descriptor, đọc danh sách `NAME`, `DESC`, `SYNTAX`, `EQUALITY` và `SINGLE-VALUE`.
4. Kiểm tra object class tương ứng xem thuộc tính thuộc `MUST` hay `MAY`, rồi thử đọc với bind account đủ quyền.

Ví dụ minh họa bằng `ldapsearch` (thay hostname, DN và subschema DN theo môi trường):

```bash
# Hỏi Root DSE về vị trí subschema nếu server có công bố.
ldapsearch -x -H ldaps://ldap.example.org:636 \
  -D "cn=readonly,ou=system,dc=example,dc=org" -W \
  -b "" -s base subschemaSubentry

# Đọc định nghĩa attribute type trên subschema DN trả về.
ldapsearch -x -H ldaps://ldap.example.org:636 \
  -D "cn=readonly,ou=system,dc=example,dc=org" -W \
  -b "cn=subschema" -s base attributeTypes
```

`cn=subschema` chỉ là **giá trị ví dụ**: phải dùng DN thật do server cung cấp. `attributeTypes` có thể trả nhiều định nghĩa lớn; một số server triển khai cơ chế khám phá schema khác, chẳng hạn thông qua vùng schema riêng và quyền đặc biệt. Khi thiếu quyền truy cập schema, cần trao đổi với người quản trị thay vì đoán tên hoặc OID.

Trong môi trường production, nên dùng LDAPS hoặc StartTLS được kiểm chứng chứng chỉ, không đưa mật khẩu vào dòng lệnh; `-W` cho phép nhập mật khẩu khi được yêu cầu.

## 6. Sử dụng định danh đã xác nhận trong Spring LDAP

Giả sử `ContextSource` đã có base DN `dc=example,dc=org`, và entry người dùng nằm dưới `ou=people`. Một cách phổ biến là dùng **descriptor ổn định được server hỗ trợ** trong query và mapping.

Ví dụ Java 17+ với `LdapTemplate`:

```java
import java.util.Arrays;
import java.util.List;

import org.springframework.ldap.core.ContextMapper;
import org.springframework.ldap.core.DirContextOperations;
import org.springframework.ldap.core.LdapTemplate;

import static org.springframework.ldap.query.LdapQueryBuilder.query;

record DirectoryUser(String uid, List<String> commonNames, String displayName) {}

public class UserDirectory {
    private final LdapTemplate ldapTemplate;

    public UserDirectory(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<DirectoryUser> findByUid(String uid) {
        return ldapTemplate.search(
            query().base("ou=people")
                .attributes("uid", "cn", "displayName")
                .where("uid").is(uid),
            (ContextMapper<DirectoryUser>) context -> {
                DirContextOperations entry = (DirContextOperations) context;

                String[] cnValues = entry.getStringAttributes("cn");
                List<String> names = cnValues == null
                    ? List.of()
                    : Arrays.asList(cnValues);

                return new DirectoryUser(
                    entry.getStringAttribute("uid"),
                    names,
                    entry.getStringAttribute("displayName")
                );
            }
        );
    }
}
```

Giải thích từng lựa chọn:

- `where("uid").is(uid)` xây điều kiện lọc theo thuộc tính `uid`. Dùng query builder xử lý giá trị đầu vào thay vì nối filter trực tiếp.
- `attributes("uid", "cn", "displayName")` yêu cầu các thuộc tính ứng dụng cần, theo các descriptor đã xác nhận trong schema.
- `getStringAttributes("cn")` giữ **tất cả** giá trị của `cn`; LDAP không cam kết thứ tự value trong một multi-valued attribute.
- `getStringAttribute("displayName")` đọc riêng attribute `displayName`; nó **không tự lấy** giá trị `cn` và cũng không biến thành nhãn UI.
- Nếu `displayName` không có trong entry, giá trị có thể là `null`. Ứng dụng cần quyết định fallback và trường hợp thiếu dữ liệu theo nghiệp vụ.

Ví dụ trên giả định server có schema `inetOrgPerson` hỗ trợ `displayName`, dữ liệu là chuỗi và tài khoản kết nối có quyền đọc. Nếu server không hỗ trợ attribute type, phải sửa projection và mapping theo schema thực tế, thay vì tạo alias trong code.

### 6.1. Hiển thị tên cho người dùng

Một quy tắc hiển thị đơn giản ở tầng ứng dụng có thể là:

```java
public static String labelFor(DirectoryUser user) {
    if (user.displayName() != null && !user.displayName().isBlank()) {
        return user.displayName();
    }
    if (!user.commonNames().isEmpty()) {
        // Ví dụ chọn giá trị đầu tiên chỉ khi ứng dụng chấp nhận quy tắc này.
        return user.commonNames().get(0);
    }
    return user.uid();
}
```

**Chú ý:** `cn` có thể có nhiều giá trị và không có thứ tự ưu tiên được LDAP bảo đảm. Nếu cần một tên chính thức, phải có quy tắc dữ liệu riêng (chẳng hạn luôn cung cấp `displayName`), không coi phần tử đầu tiên của `cn` là “tên chính” theo đặc tả LDAP.

### 6.2. Điều gì xảy ra khi dùng alias trong truy vấn?

Trong schema giả định tại phần 2, server hiểu `personCode` và `staffCode` là hai descriptor cùng type. Truy vấn:

```java
ldapTemplate.search(
    query().base("ou=people").where("staffCode").is("HR-042"),
    (ContextMapper<String>) context ->
        ((DirContextOperations) context).getStringAttribute("uid")
);
```

về mặt schema tham chiếu cùng thuộc tính như filter viết bằng `personCode`. Nhưng **không nên giả định** key trong đối tượng kết quả luôn được server/JNDI trả về dưới đúng alias bạn nhập. Một số server trả descriptor khác hoặc OID; các thư viện client có thể xử lý tên thay thế khác nhau. Với hệ thống ổn định, hãy chọn descriptor chuẩn hóa tại ranh giới truy vấn/ánh xạ và kiểm thử với LDAP server thực tế.

### 6.3. Khi nào dùng OID thay cho tên?

OID hữu ích khi đọc schema, so sánh định nghĩa giữa server và kiểm tra hai descriptor có cùng attribute type hay không. LDAP cho phép dùng OID làm định danh attribute type trong bộ lọc khi type đã được server nhận biết.

Tuy nhiên, **OID không vượt qua ràng buộc schema hay quyền truy cập**. Nếu client dùng một OID chưa được server định nghĩa, thao tác vẫn có thể thất bại. Với các thuộc tính phổ biến trong Spring LDAP, dùng descriptor được xác nhận thường dễ đọc và bảo trì hơn; với thuộc tính tùy biến, cần lưu giữ tài liệu ánh xạ descriptor ↔ OID và kiểm thử tương thích khi thay schema.

## 7. Thiết kế ứng dụng và thay đổi schema an toàn

Giả sử ban đầu một hệ thống dùng `personCode`, sau đó đội vận hành muốn đổi cách gọi thành `staffCode`. Nếu hai descriptor cùng được khai báo cho một OID, hai hệ thống có thể tham chiếu cùng loại thuộc tính. Tuy vậy, có một số điều kiện:

| Việc thay đổi | Có làm đổi attribute type? | Điều cần kiểm tra |
| --- | --- | --- |
| Đổi nhãn giao diện “Mã nhân sự” → “Mã nhân viên” | Không | Giao diện, nội dung và bản dịch |
| Dùng descriptor alias khác đã có trong schema | Không | Server có đăng ký alias và client có hỗ trợ |
| Thêm descriptor alias vào `NAME` của schema hiện tại | Không đổi OID, nhưng **thay schema** | Quyền quản trị, khả năng triển khai, client cũ |
| Đổi `displayName` của một entry | Không đổi OID hay DN do thao tác này | ACL, syntax, dữ liệu và quy tắc hiển thị |
| Tạo attribute type mới với OID khác | Có | Schema, object class, dữ liệu, migration và truy vấn |
| Xóa alias cũ khỏi schema | Không tự thay dữ liệu, nhưng có thể làm hỏng client | Tìm mọi filter, mapping và tích hợp đang dùng tên cũ |

Một cách tổ chức code dễ bảo trì là tập trung các tên LDAP ở lớp truy cập thư mục, thay vì sao chép literal `"displayName"`, `"uid"` và các descriptor tùy biến khắp ứng dụng. Cần ưu tiên mô tả rõ tại lớp đó tên nào là **attribute LDAP**, tên nào là **trường DTO**, và tên nào là **nhãn hiển thị**.

Khi cập nhật schema trên directory server, hãy kiểm tra tác động lên entry hiện hữu, matching rule, object class, dữ liệu nhị phân, quyền ACL và các hệ thống tiêu thụ trước khi triển khai. Việc bổ sung alias không thay thế quy trình quản lý schema.

## 8. Các nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| “Tên dài tiếng Anh” của attribute luôn là alias hợp lệ | Chỉ những descriptor nằm trong `NAME` của schema mới là tên được định nghĩa |
| `NAME ( 'personCode' 'staffCode' )` tạo hai cột dữ liệu | Đó là hai tên của **một** attribute type |
| `DESC` là display name bắt buộc trên giao diện | `DESC` chỉ mô tả schema; giao diện có quyền đặt nhãn riêng |
| `displayName` chỉ là nhãn của `cn` | `displayName` là attribute type độc lập, có OID riêng |
| Sửa `displayName` sẽ đổi DN của người dùng | DN được xác định bởi RDN/đường dẫn entry; muốn đổi tên entry cần thao tác phù hợp |
| Dùng OID luôn giải quyết được lỗi “unknown attribute” | Server vẫn phải nhận biết OID trong schema |
| Alias cho phép vượt qua `SINGLE-VALUE` | Ràng buộc cardinality áp dụng cho **attribute type**, bất kể descriptor nào được dùng |
| Spring LDAP tự hiểu tên trường DTO là alias schema | Ánh xạ Java và schema LDAP là hai hệ thống đặt tên riêng, phải cấu hình rõ ràng |

## 9. Bài thực hành tự kiểm tra

Cho định nghĩa schema giả định:

```text
( 1.3.6.1.4.1.99999.1.17
  NAME ( 'personCode' 'staffCode' )
  DESC 'Demo: internal person identifier'
  EQUALITY caseIgnoreMatch
  SYNTAX 1.3.6.1.4.1.1466.115.121.1.15
  SINGLE-VALUE )
```

Và entry giả định:

```ldif
dn: uid=lan,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: lan
cn: Lan Nguyen
sn: Nguyen
displayName: Lan N. (Engineering)
personCode: HR-042
```

*Giả sử object class của entry đã được mở rộng hợp lệ để cho phép `personCode`, và schema này được nạp trên server.*

1. Định danh chuẩn của `personCode` là gì? `staffCode` có phải một attribute type khác không?
2. Tìm theo `(staffCode=HR-042)` có thể khớp entry không?
3. Có thể thêm `staffCode: HR-999` như “một trường thứ hai” bên cạnh `personCode: HR-042` không?
4. Nếu giao diện đổi nhãn “Mã nhân viên” thành “Employee code”, định nghĩa LDAP có cần sửa không?
5. Nếu ứng dụng đổi `displayName` thành `Lan Nguyen`, DN của entry có tự đổi không?
6. Vì sao nên đọc thuộc tính `attributeTypes` của subschema thay vì đoán rằng `commonName` luôn là alias của `cn`?

**Đáp án và giải thích:**

1. OID `1.3.6.1.4.1.99999.1.17` trong **ví dụ học tập**. `staffCode` là một descriptor alias, cùng OID với `personCode`.
2. Có thể, khi server hỗ trợ schema giả định, entry cho phép loại thuộc tính này và quyền truy vấn phù hợp.
3. Không theo mô hình hai trường độc lập: cả hai descriptor chỉ một attribute type có `SINGLE-VALUE`; ghi thêm giá trị khác sẽ vi phạm ràng buộc.
4. Không. Đây là thay đổi nhãn UI, không phải thay attribute type.
5. Không. Đổi giá trị `displayName` không đồng nghĩa đổi RDN/đường dẫn entry.
6. Tên alias phải được chứng minh bởi danh sách `NAME` server đang dùng; một cách gọi quen thuộc trong tài liệu không bảo đảm được server đăng ký.

## 10. Tổng kết và tài liệu tham khảo

Trong LDAP, **OID** định danh attribute type; các descriptor trong `NAME` là tên được schema công nhận, có thể gồm nhiều alias. **Nhãn UI** là cách ứng dụng trình bày dữ liệu và không có vai trò định danh schema. Riêng **`displayName`** là tên của một attribute type thực sự, độc lập với `cn` và với nhãn “Tên hiển thị”.

Khi làm việc với Spring LDAP, hãy xác nhận schema trên server, thống nhất descriptor trong truy vấn và ánh xạ, xử lý attribute tùy chọn và multi-valued đúng cách, đồng thời phân biệt việc **đổi nhãn giao diện**, **đổi descriptor schema** và **đổi giá trị attribute**. Những phân biệt này giúp tránh lỗi tìm kiếm, mapping và triển khai schema trong hệ thống LDAP thực tế.

Tham khảo thêm:

- [RFC 4512 — LDAP: Directory Information Models](https://www.rfc-editor.org/rfc/rfc4512): attribute type, OID, descriptor, subschema và định nghĩa schema.
- [RFC 4519 — LDAP: Schema for User Applications](https://www.rfc-editor.org/rfc/rfc4519): các thuộc tính chuẩn như `cn`, `sn` và `uid`.
- [RFC 2798 — Definition of the inetOrgPerson LDAP Object Class](https://www.rfc-editor.org/rfc/rfc2798): định nghĩa `displayName` và `inetOrgPerson`.
- [Spring LDAP Reference Documentation](https://docs.spring.io/spring-ldap/reference/): sử dụng `ContextSource`, `LdapTemplate`, query API và ánh xạ attribute.
