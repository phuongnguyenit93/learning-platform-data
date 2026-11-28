# Thuộc tính một giá trị và nhiều giá trị

## 1. Vì sao cần hiểu số lượng giá trị của LDAP attribute?

Trong **Spring Data LDAP**, ứng dụng Java quản lý người dùng, nhóm và các đối tượng trong **directory** thông qua `LdapRepository`, Object-Directory Mapping (ODM) hoặc `LdapTemplate`. Mỗi entry có **DN** (*distinguished name*), các `objectClass` và những attribute tuân theo LDAP schema. Khác với cách hình dung một cột của bảng quan hệ thường chứa một giá trị, **một LDAP attribute có thể chứa nhiều giá trị**.

Ví dụ một nhân viên có hai tên thường dùng và hai số điện thoại:

```ldif
dn: uid=linh,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: linh
cn: Linh Nguyen
cn: Nguyen Thu Linh
sn: Nguyen
telephoneNumber: +84 28 5555 0101
telephoneNumber: +84 90 123 4567
mail: linh@example.org
```

Những dòng lặp `cn:` và `telephoneNumber:` trong LDIF là **các giá trị của cùng một attribute**, không phải hai entry và cũng không phải hai cột trùng tên. Ngược lại, một attribute được schema định nghĩa **`SINGLE-VALUE`** không được chứa hai giá trị, dù Java khai báo field dưới dạng `List`.

Nếu hiểu sai, ứng dụng dễ:

- Đọc `getStringAttribute("cn")` rồi âm thầm bỏ mất các tên khác.
- Dùng `REPLACE_ATTRIBUTE` khi chỉ muốn thêm một số điện thoại, làm mất các số cũ.
- Gửi hai giá trị vào attribute đơn trị và bị server từ chối.
- Nhầm `MUST` trong `objectClass` với `SINGLE-VALUE` trong `attributeTypes`.
- Dùng danh sách có thứ tự cho dữ liệu LDAP vốn thường được đối xử như **tập giá trị không có thứ tự**.
- Vô tình xóa thành viên khác khi cập nhật thuộc tính `member` của nhóm.

### Mục tiêu học tập

Sau bài này, bạn có thể phân biệt attribute đơn trị/đa trị theo schema, tìm và đọc định nghĩa `SINGLE-VALUE` trên server, giải thích ý nghĩa `MUST`/`MAY`, ánh xạ sang Java đúng kiểu dữ liệu, dùng `ADD_ATTRIBUTE`/`REPLACE_ATTRIBUTE`/`REMOVE_ATTRIBUTE` an toàn, đọc đủ giá trị bằng Spring LDAP, viết truy vấn và kiểm thử những trường hợp vi phạm schema.

## 2. Hai khái niệm quan trọng: attribute type và attribute values

Một **attribute type** định nghĩa đặc tính của thuộc tính: tên hoặc OID, syntax, matching rules, tính đơn trị/đa trị và các ràng buộc khác. Một **attribute instance** trong entry là giá trị cụ thể của loại thuộc tính ấy.

```text
SCHEMA
  attributeTypes
    cn                 -> cho phép nhiều giá trị
    telephoneNumber    -> cho phép nhiều giá trị
    createTimestamp    -> SINGLE-VALUE, operational
             |
             v
ENTRY: uid=linh,ou=people,dc=example,dc=org
  cn                  = { "Linh Nguyen", "Nguyen Thu Linh" }
  telephoneNumber     = { "+84 28 ...", "+84 90 ..." }
  createTimestamp     = "20261126091000Z" (nếu server công bố)
```

Theo **RFC 4512**, mặc định một loại thuộc tính **có thể đa trị**; nếu định nghĩa attribute type khai báo `SINGLE-VALUE` thì một instance của attribute đó trong entry bị giới hạn **tối đa một giá trị**.

### 2.1. Đơn trị nghĩa là gì?

Thuộc tính **đơn trị** (*single-valued*) có **tối đa một giá trị** trong một entry:

```text
entry:
  someSingleValue = A            -> hợp lệ, nếu schema cho phép attribute
  someSingleValue = { A, B }     -> không hợp lệ vì vượt cardinality
  someSingleValue vắng mặt       -> có thể hợp lệ nếu objectClass không bắt buộc
```

`SINGLE-VALUE` **không có nghĩa attribute luôn phải xuất hiện**. Muốn biết có bắt buộc hay không, phải xem `MUST`/`MAY` của `objectClass` và các quy tắc schema liên quan.

### 2.2. Đa trị nghĩa là gì?

Thuộc tính **đa trị** (*multi-valued*) có thể chứa nhiều giá trị trong cùng một entry:

```text
telephoneNumber = {
  "+84 28 5555 0101",
  "+84 90 123 4567"
}
```

Một thuộc tính **được phép đa trị** vẫn có thể có **chỉ một giá trị** hoặc không xuất hiện nếu schema cho phép. Điều đáng chú ý là: loại thuộc tính đó có khả năng chứa hơn một giá trị, không phải bắt buộc phải có ít nhất hai.

Các giá trị của một LDAP attribute thông thường được đối xử như **một tập**, không có thứ tự nghiệp vụ được bảo đảm. Vì vậy, hai kết quả có cùng tập giá trị nhưng thứ tự trả về khác nhau nên được coi tương đương ở tầng nghiệp vụ.

### 2.3. Các giá trị trùng nhau

Một LDAP attribute không phải danh sách cho phép thêm bản sao tùy ý. Server đánh giá việc hai giá trị có tương đương hay không bằng **equality matching rule** được schema khai báo, khi có quy tắc này. Ví dụ, một thuộc tính dùng `caseIgnoreMatch` có thể coi `"Linh Nguyen"` và `"LINH NGUYEN"` là tương đương sau quy tắc chuẩn hóa.

Do đó:

- Không dùng `String.equals` của Java làm bằng chứng chắc chắn hai giá trị LDAP khác nhau.
- `ADD_ATTRIBUTE` một giá trị tương đương với giá trị đang có có thể bị từ chối với `attributeOrValueExists`.
- Khi schema không định nghĩa equality matching rule, những thao tác/truy vấn phụ thuộc vào so khớp giá trị có giới hạn đặc biệt theo RFC 4512; không giả định có thể xóa riêng một giá trị bằng mọi loại attribute.
- Đừng dựa vào thứ tự từ `NamingEnumeration` hay `List` để xác định “giá trị chính” nếu schema/nghiệp vụ chưa định nghĩa quy tắc chọn.

## 3. Ví dụ thuộc tính đơn trị và đa trị

Danh sách dưới đây minh họa các định nghĩa chuẩn phổ biến. **Directory cụ thể có thể có schema mở rộng, subtype hoặc chính sách riêng**; cần kiểm tra định nghĩa thực tế trước khi ghi.

| Thuộc tính | Cardinality thường gặp | Ý nghĩa | Lưu ý |
| --- | --- | --- | --- |
| `cn` (*commonName*) | **Đa trị** theo RFC 4519 | Một hoặc nhiều tên của đối tượng. | Dù `person` yêu cầu `cn`, attribute vẫn có thể có nhiều giá trị. |
| `sn` (*surname*) | **Đa trị** theo RFC 4519 | Một hoặc nhiều họ/tên họ. | `MUST sn` không đồng nghĩa đơn trị. |
| `telephoneNumber` | **Đa trị** theo RFC 4519 | Các số liên hệ. | Chỉ thêm một số bằng ADD, không thay toàn bộ nếu muốn giữ số cũ. |
| `description` | **Đa trị** theo RFC 4519 | Nhiều mô tả/ghi chú. | Có thể được ứng dụng tự giới hạn một giá trị. |
| `member` của `groupOfNames` | **Đa trị** | Các DN thành viên của nhóm. | `member` là attribute bắt buộc của objectClass này. |
| `objectClass` | **Đa trị** | Các object class mà entry thuộc về. | Một entry thường có nhiều class theo cây kế thừa. |
| `c` (*countryName*) | **SINGLE-VALUE** theo RFC 4519 | Mã quốc gia hai chữ cái. | Chỉ được dùng nếu schema/objectClass cho phép trên entry. |
| `createTimestamp` | **SINGLE-VALUE**, operational | Thời điểm tạo entry. | Do server quản lý, không phải field để ứng dụng tùy ý ghi. |
| `modifyTimestamp` | **SINGLE-VALUE**, operational | Thời điểm sửa gần nhất. | Thường chỉ đọc; cần yêu cầu operational attribute rõ ràng. |
| `structuralObjectClass` | **SINGLE-VALUE**, operational | Structural class của entry. | Khác với attribute `objectClass` đa trị. |
| `uidNumber` trong `posixAccount` | Thường **SINGLE-VALUE** theo schema RFC 2307 | ID số trong môi trường POSIX. | Cần schema POSIX thực tế, không mặc định mọi LDAP có attribute này. |

**Điểm dễ nhầm:** trong nhiều ứng dụng, người dùng có **một** email chính và **một** UID để đăng nhập. Đó có thể chỉ là **quy tắc nghiệp vụ**. Không nên suy ra `mail` hoặc `uid` chắc chắn có `SINGLE-VALUE` trong schema của mọi directory chỉ từ việc project Java dùng `String`.

## 4. Phân biệt MUST/MAY với SINGLE-VALUE

LDAP schema có **hai trục độc lập**:

1. **Tính bắt buộc:** `MUST` hay `MAY` được khai báo trong **object class**.
2. **Số lượng giá trị tối đa:** `SINGLE-VALUE` hay cho phép nhiều giá trị, được khai báo ở **attribute type**.

### 4.1. Ma trận 2 × 2

| Attribute trong objectClass | Attribute type | Số giá trị hợp lệ trong trường hợp thông thường |
| --- | --- | --- |
| `MUST` | `SINGLE-VALUE` | **Đúng 1**; không thể thiếu hoặc có 2 giá trị. |
| `MUST` | Đa trị | **Ít nhất 1**; có thể có nhiều giá trị. |
| `MAY` | `SINGLE-VALUE` | **0 hoặc 1** giá trị. |
| `MAY` | Đa trị | **0, 1 hoặc nhiều** giá trị. |

Ma trận giả định không có ràng buộc phụ khác do subtype, DIT content rules, matching rule hoặc triển khai server. Nó mô tả **ngữ nghĩa cơ bản**, không bảo đảm mọi tập giá trị sẽ vượt qua mọi policy.

### 4.2. Ví dụ objectClass person

Theo RFC 4519, `person` là structural object class và có các thuộc tính bắt buộc `cn` và `sn`:

```text
objectClass: person
MUST: ( sn $ cn )
MAY:  ( userPassword $ telephoneNumber $ seeAlso $ description )
```

Điều này có nghĩa:

- Entry phải có **ít nhất một** giá trị `cn` và **ít nhất một** giá trị `sn`.
- `cn` và `sn` vẫn có thể chứa **nhiều** giá trị vì định nghĩa attribute type của chúng cho phép đa trị.
- `telephoneNumber` không bắt buộc theo `person`, nhưng nếu có thì có thể chứa nhiều giá trị.
- Không thể xóa **giá trị cuối cùng** của `cn` hoặc `sn` rồi để entry `person` không hợp lệ.

### 4.3. Ví dụ groupOfNames

`groupOfNames` yêu cầu `cn` và `member`. `member` thường chứa nhiều DN:

```ldif
dn: cn=developers,ou=groups,dc=example,dc=org
objectClass: top
objectClass: groupOfNames
cn: developers
member: uid=linh,ou=people,dc=example,dc=org
member: uid=an,ou=people,dc=example,dc=org
```

Lệnh gỡ riêng An có thể hợp lệ vì nhóm vẫn còn Linh. Nhưng gỡ giá trị `member` cuối cùng sẽ khiến entry thiếu một attribute `MUST`, nên directory tuân schema có thể từ chối. Nếu nghiệp vụ cần nhóm rỗng, phải kiểm tra **loại nhóm và schema** hỗ trợ điều đó; không tự đổi chính sách của mọi group.

### 4.4. Object class không tự tạo cardinality

Chỉ vì `inetOrgPerson` cho phép `mail` không có nghĩa `mail` đã tự thành `SINGLE-VALUE`. Khi object class khai báo `MAY mail`, quy tắc cardinality vẫn đến từ định nghĩa attribute type `mail` và các ràng buộc liên quan. Tương tự, `MUST cn` chỉ buộc `cn` hiện diện; nó không chuyển `cn` thành một trường đơn trị.

## 5. Định nghĩa SINGLE-VALUE trong schema

Theo RFC 4512, một attribute type có thể có mô tả dạng:

```text
( OID
  NAME 'attributeName'
  DESC 'Mô tả'
  EQUALITY matchingRule
  SYNTAX syntaxOid
  SINGLE-VALUE )
```

`SINGLE-VALUE` là từ khóa **có hoặc không** trong định nghĩa attribute type; không có cú pháp `SINGLE-VALUE FALSE` theo format tiêu chuẩn này. Khi thiếu `SINGLE-VALUE`, loại attribute thường được phép đa trị.

### 5.1. Hai định nghĩa minh họa

Các OID dưới đây là **giả lập để đọc cú pháp**. Khi thiết kế schema thật, tổ chức phải dùng nhánh OID được cấp hợp lệ; không lấy nguyên OID ví dụ này để triển khai.

```text
# Mã nhân viên: đơn trị
attributetype ( 1.3.6.1.4.1.55555.1.1
  NAME 'appEmployeeCode'
  DESC 'Business employee code'
  EQUALITY caseExactMatch
  SYNTAX 1.3.6.1.4.1.1466.115.121.1.15
  SINGLE-VALUE )

# Nhãn nghiệp vụ: đa trị (không có SINGLE-VALUE)
attributetype ( 1.3.6.1.4.1.55555.1.2
  NAME 'appLabel'
  DESC 'Labels associated with an entry'
  EQUALITY caseIgnoreMatch
  SYNTAX 1.3.6.1.4.1.1466.115.121.1.15 )
```

Giải thích:

| Thành phần | Ý nghĩa |
| --- | --- |
| OID | Định danh loại attribute trong schema. |
| `NAME` | Tên thuận tiện để biểu diễn attribute. |
| `EQUALITY` | Quy tắc so sánh bằng nhau, ảnh hưởng duplicate và filter. |
| `SYNTAX` | Kiểu giá trị; OID `1.3.6.1.4.1.1466.115.121.1.15` là Directory String. |
| `SINGLE-VALUE` | Giới hạn attribute trong entry tối đa một giá trị. |

Một định nghĩa attribute type **không tự cấp quyền** sử dụng nó trên entry. Muốn đưa `appEmployeeCode` và `appLabel` vào entry, phải có object class hoặc schema rules cho phép, ví dụ một auxiliary class được quản trị viên cấp phát đúng cách.

### 5.2. Kết hợp với objectClass minh họa

```text
# Chỉ minh họa ý tưởng; cú pháp cài đặt phụ thuộc directory.
objectclass ( 1.3.6.1.4.1.55555.2.1
  NAME 'appEmployeeAux'
  SUP top
  AUXILIARY
  MAY ( appEmployeeCode $ appLabel ) )
```

Khi entry được phép dùng `appEmployeeAux`, việc `appEmployeeCode` vắng mặt có thể hợp lệ (`MAY`), nhưng nếu xuất hiện thì nó chỉ được có **một** giá trị (`SINGLE-VALUE`). `appLabel` cũng là `MAY`, nhưng nếu xuất hiện có thể có nhiều giá trị.

**Không tự sửa schema production từ ứng dụng Spring Boot.** Thay đổi schema có thể tác động toàn directory, replication, chính sách ACL và hệ thống tích hợp. Hãy thử nghiệm/cấp OID/kiểm tra compatibility dưới quy trình quản trị server.

## 6. Làm sao kiểm tra cardinality thật trên LDAP server?

**Nguồn sự thật cuối cùng là schema của server** đang lưu entry. Spring annotation hay kiểu field Java không thay thế định nghĩa này.

### 6.1. Tìm subschemaSubentry

Nhiều LDAP server cung cấp attribute vận hành `subschemaSubentry`, trỏ tới entry chứa mô tả schema. Tùy server, có thể truy vấn entry hoặc Root DSE:

```bash
# Kiểm tra subschemaSubentry cho một entry cụ thể:
ldapsearch -LLL -x \
  -H "ldaps://ldap.example.org:636" \
  -D "uid=svc-reader,ou=service-accounts,dc=example,dc=org" -W \
  -b "uid=linh,ou=people,dc=example,dc=org" -s base \
  "(objectClass=*)" subschemaSubentry
```

Kỳ vọng một giá trị như `subschemaSubentry: cn=Subschema`, nhưng **DN thật phải lấy từ response**, không hard-code. Một số directory hạn chế đọc metadata hoặc có nhiều schema subentry, vì vậy không nhận response không có nghĩa LDAP không áp dụng schema.

### 6.2. Đọc attributeTypes và objectClasses

Sau khi biết DN subschema thực:

```bash
ldapsearch -LLL -x \
  -H "ldaps://ldap.example.org:636" \
  -D "uid=svc-schema-reader,ou=service-accounts,dc=example,dc=org" -W \
  -b "cn=Subschema" -s base \
  "(objectClass=subschema)" attributeTypes objectClasses
```

Thay `cn=Subschema` bằng **DN do server trả ở bước trước**, nếu khác. `attributeTypes` và `objectClasses` thường có số lượng rất lớn; khi chẩn đoán, lọc nội dung đã lấy để tìm định nghĩa `cn`, `telephoneNumber`, `member` hoặc attribute tùy chỉnh.

Khi đọc mô tả attribute type:

1. Tìm `NAME`/OID của attribute.
2. Tìm `SINGLE-VALUE` trong chính định nghĩa đó hoặc kiểm tra inheritance khi attribute kế thừa subtype.
3. Xác nhận `SYNTAX` và `EQUALITY`, vì loại giá trị và so khớp có thể khác Java.
4. Tra `objectClasses` để biết entry được phép có attribute (`MAY`) hoặc bắt buộc có (`MUST`).
5. Đối chiếu ACL của bind account; thiếu quyền đọc schema không phải bằng chứng schema không tồn tại.

### 6.3. So sánh với dữ liệu đang có

```bash
ldapsearch -LLL -x \
  -H "ldaps://ldap.example.org:636" \
  -D "uid=svc-reader,ou=service-accounts,dc=example,dc=org" -W \
  -b "uid=linh,ou=people,dc=example,dc=org" -s base \
  "(objectClass=*)" dn cn sn telephoneNumber mail
```

Ví dụ trả nhiều dòng `telephoneNumber:` cho cùng entry chứng tỏ entry đó đang có nhiều giá trị. Nhưng nếu kết quả chỉ có một dòng, bạn **không thể kết luận** attribute là đơn trị; cần xem schema. LDAP server cũng có thể ẩn một số giá trị do ACL.

## 7. Đọc dữ liệu đa trị bằng JNDI

`javax.naming.directory.Attributes` ánh xạ tên attribute tới `Attribute`. `Attribute.get()` chỉ lấy một giá trị, còn `Attribute.getAll()` dùng để đọc **toàn bộ**.

### 7.1. Cách đọc đầy đủ

```java
import java.util.LinkedHashSet;
import java.util.Set;
import javax.naming.NamingEnumeration;
import javax.naming.NamingException;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;

public final class LdapAttributeValues {
    private LdapAttributeValues() {}

    public static Set<String> strings(Attributes attrs, String name)
            throws NamingException {
        Attribute attribute = attrs.get(name);
        if (attribute == null) {
            return Set.of();
        }

        Set<String> result = new LinkedHashSet<>();
        NamingEnumeration<?> values = attribute.getAll();
        try {
            while (values.hasMore()) {
                Object value = values.next();
                if (!(value instanceof String text)) {
                    throw new IllegalArgumentException(
                        "Attribute không chứa String: " + name
                    );
                }
                result.add(text);
            }
        } finally {
            values.close();
        }
        return result;
    }
}
```

`LinkedHashSet` giúp code Java giữ thứ tự **nhận được trong lần đọc**, nhưng **LDAP không bảo đảm thứ tự đó là cố định**. Nếu API cần hiển thị nhất quán, hãy sắp xếp sau khi đọc, theo quy tắc nghiệp vụ riêng.

Với attribute binary như `jpegPhoto` hoặc `objectGUID` ở một số directory, kiểu dữ liệu có thể là `byte[]`, không phải `String`. Không ép mọi attribute vào `Set<String>` mà không xét schema.

### 7.2. Tránh dùng get() khi cần nhiều giá trị

```java
// Chỉ lấy một giá trị, không phù hợp nếu cần mọi số điện thoại.
String onePhone =
    (String) attrs.get("telephoneNumber").get();

// Đọc đầy đủ, có kiểm tra attribute vắng mặt:
Set<String> allPhones =
    LdapAttributeValues.strings(attrs, "telephoneNumber");
```

Nếu dùng `get()` cho một attribute đa trị, giá trị được trả không được diễn giải tự động là “primary phone”. LDAP schema không định nghĩa “giá trị đầu tiên” là giá trị chính.

### 7.3. BasicAttribute có hỗ trợ nhiều giá trị

```java
import javax.naming.directory.Attribute;
import javax.naming.directory.BasicAttribute;

Attribute phones = new BasicAttribute("telephoneNumber");
phones.add("+84 28 5555 0101");
phones.add("+84 90 123 4567");
```

Đây mới là **đối tượng Java**, chưa ghi vào directory. Đặc biệt, constructor `new BasicAttribute("telephoneNumber", true)` có boolean diễn đạt **thứ tự của tập Java**, **không phải** tùy chọn bật `SINGLE-VALUE` trong schema. Cardinality ở LDAP server vẫn do schema quyết định.

## 8. Đọc đa trị với Spring LDAP LdapTemplate

Với Spring Boot có `spring-boot-starter-data-ldap`, ví dụ cấu hình:

```yaml
spring:
  ldap:
    urls: ${LDAP_URL:ldaps://ldap.example.org:636}
    base: dc=example,dc=org
    username: ${LDAP_BIND_DN}
    password: ${LDAP_BIND_PASSWORD}
```

Các ví dụ dùng DN **tương đối với** `ContextSource.base=dc=example,dc=org`. Không lặp lại phần `dc=example,dc=org` trong đối số của `LdapTemplate` khi base đã cấu hình.

### 8.1. Tìm theo UID, trả về toàn bộ số điện thoại

```java
package com.example.directory;

import static org.springframework.ldap.query.LdapQueryBuilder.query;

import java.util.List;
import java.util.Set;
import javax.naming.directory.Attributes;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.stereotype.Service;

@Service
public class PersonPhonesQuery {
    private final LdapTemplate ldap;

    public PersonPhonesQuery(LdapTemplate ldap) {
        this.ldap = ldap;
    }

    public List<PersonPhones> findByUid(String uid) {
        return ldap.search(
            query()
                .base("ou=people")
                .attributes("uid", "telephoneNumber")
                .where("uid").is(uid),
            (AttributesMapper<PersonPhones>) attrs ->
                new PersonPhones(
                    value(attrs, "uid"),
                    LdapAttributeValues.strings(
                        attrs, "telephoneNumber")
                )
        );
    }

    private static String value(Attributes attrs, String name)
            throws javax.naming.NamingException {
        var attribute = attrs.get(name);
        return attribute == null ? null : (String) attribute.get();
    }

    public record PersonPhones(String uid, Set<String> phoneNumbers) {}
}
```

Giải thích:

- `.base("ou=people")` và `.where("uid").is(uid)` tạo query có phạm vi rõ ràng, escaping giá trị filter đúng API Spring LDAP.
- `.attributes(...)` là projection, giúp tránh tải các thuộc tính không cần thiết.
- Mapper gọi `getAll()` gián tiếp, không làm mất các giá trị `telephoneNumber` còn lại.
- `Set<String>` biểu diễn hợp lý tập giá trị; có thể sắp xếp để trả về DTO ổn định.
- Nếu thiếu quyền đọc một attribute, LDAP có thể không trả nó; `Set.of()` trong mapper lúc này biểu diễn **các giá trị quan sát được**, không chứng minh server thật sự không có attribute.

**Phân biệt kết quả:** tìm không khớp UID có thể trả danh sách rỗng, trong khi một entry phù hợp nhưng không có số điện thoại có thể cho `phoneNumbers` rỗng. Không biến lỗi kết nối hoặc lỗi ACL thành “không có số điện thoại”.

### 8.2. DirContextOperations giúp truy cập nhanh nhưng có bẫy

`LdapTemplate.lookupContext(Name)` trả `DirContextOperations`. Spring LDAP hỗ trợ:

```java
import javax.naming.Name;
import org.springframework.ldap.core.DirContextOperations;
import org.springframework.ldap.support.LdapNameBuilder;

Name dn = LdapNameBuilder.newInstance("ou=people")
    .add("uid", "linh")
    .build();

DirContextOperations entry = ldapTemplate.lookupContext(dn);

// Chỉ một giá trị; không coi là giá trị "chính".
String first = entry.getStringAttribute("telephoneNumber");

// Tất cả giá trị string được directory trả.
String[] everyPhone =
    entry.getStringAttributes("telephoneNumber");
```

`getStringAttribute` có thể trả một giá trị trong tập đa trị, còn `getStringAttributes` lấy các giá trị String. Khi attribute vắng mặt, kiểm tra `null`/empty theo API được dùng trước khi xử lý.

## 9. Ghi dữ liệu: ADD, REPLACE và REMOVE không tương đương

Ở mức JNDI, LDAP Modify dùng `ModificationItem` với ba hằng:

- `DirContext.ADD_ATTRIBUTE`: thêm giá trị, giữ các giá trị hiện tại.
- `DirContext.REPLACE_ATTRIBUTE`: thay **toàn bộ** tập giá trị của attribute.
- `DirContext.REMOVE_ATTRIBUTE`: xóa một số giá trị được liệt kê, hoặc xóa toàn attribute khi không liệt kê giá trị.

Giả sử `telephoneNumber = {A, B}`:

| Thao tác | Kết quả kỳ vọng |
| --- | --- |
| `ADD_ATTRIBUTE` thêm C | `{A, B, C}` |
| `REPLACE_ATTRIBUTE` bằng C | `{C}` |
| `REMOVE_ATTRIBUTE` giá trị B | `{A}` |
| `REMOVE_ATTRIBUTE` không chỉ định giá trị | Attribute không còn tồn tại |
| `REPLACE_ATTRIBUTE` bằng tập rỗng | Attribute không còn tồn tại theo LDAP Modify |

Lưu ý: với attribute `MUST` như `cn` hoặc `sn` trong entry `person`, xóa giá trị **cuối cùng** làm vi phạm schema và có thể bị server từ chối.

### 9.1. Ví dụ service cập nhật chính xác

```java
package com.example.directory;

import java.util.Collection;
import java.util.Objects;
import javax.naming.Name;
import javax.naming.directory.Attribute;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;
import org.springframework.stereotype.Service;

@Service
public class PersonPhonesWriter {
    private final LdapTemplate ldap;

    public PersonPhonesWriter(LdapTemplate ldap) {
        this.ldap = ldap;
    }

    public void addPhone(String uid, String phone) {
        modify(userDn(uid), DirContext.ADD_ATTRIBUTE,
            new BasicAttribute("telephoneNumber",
                Objects.requireNonNull(phone)));
    }

    public void removeOnePhone(String uid, String phone) {
        modify(userDn(uid), DirContext.REMOVE_ATTRIBUTE,
            new BasicAttribute("telephoneNumber",
                Objects.requireNonNull(phone)));
    }

    public void replaceAllPhones(
            String uid, Collection<String> phones) {
        Objects.requireNonNull(phones);
        Attribute replacement = new BasicAttribute("telephoneNumber");
        for (String phone : phones) {
            replacement.add(Objects.requireNonNull(phone));
        }
        modify(userDn(uid), DirContext.REPLACE_ATTRIBUTE, replacement);
    }

    private Name userDn(String uid) {
        return LdapNameBuilder.newInstance("ou=people")
            .add("uid", Objects.requireNonNull(uid))
            .build();
    }

    private void modify(Name dn, int operation, Attribute values) {
        ModificationItem item =
            new ModificationItem(operation, values);
        ldap.modifyAttributes(dn, new ModificationItem[] {item});
    }
}
```

Code minh họa chưa có Bean Validation và policy quyền. Khi triển khai API, phải kiểm tra định dạng số điện thoại, quyền người gọi, giới hạn số lượng, và tuyệt đối không cho HTTP client tùy ý chỉ định attribute/mã Modify. Không ghi vào LDAP production trong bài thực hành.

### 9.2. Bẫy khi thay toàn bộ tập

```text
Ban đầu telephoneNumber = {A, B}

Yêu cầu nghiệp vụ: thêm C

ĐÚNG:  ADD_ATTRIBUTE     C   => {A, B, C}
SAI:   REPLACE_ATTRIBUTE C   => {C}
                                 mất A và B
```

Với `member` của group, sai lầm tương tự có thể làm mất quyền truy cập của các thành viên cũ, gây ảnh hưởng lớn hơn một số điện thoại. Khi chỉ thêm một giá trị, không đọc cả tập rồi ghi REPLACE nếu không có nhu cầu thay toàn bộ.

### 9.3. Thao tác không phải luôn idempotent

`ADD_ATTRIBUTE` một giá trị đã tồn tại có thể trả `attributeOrValueExists`, và `REMOVE_ATTRIBUTE` một giá trị không tồn tại có thể trả `noSuchAttribute`. Sau lỗi mạng, client có thể không biết server đã áp dụng Modify hay chưa; hãy đọc lại trạng thái và quyết định retry theo **kết quả nghiệp vụ mong muốn**, không lặp thao tác vô hạn.

## 10. Cập nhật đa trị bằng DirContextOperations

Spring LDAP hỗ trợ xử lý delta trên một entry đã được đọc:

```java
import javax.naming.Name;
import org.springframework.ldap.core.DirContextOperations;

DirContextOperations entry = ldapTemplate.lookupContext(userDn);

// Bổ sung một giá trị vào tập:
entry.addAttributeValue("telephoneNumber", "+84 90 123 4567");

// Hoặc bỏ riêng một giá trị:
// entry.removeAttributeValue("telephoneNumber", "+84 28 5555 0101");

ldapTemplate.modifyAttributes(entry);
```

`DirContextOperations.addAttributeValue`/`removeAttributeValue` điều chỉnh dữ liệu ở object context và `modifyAttributes(entry)` phát sinh yêu cầu cập nhật. Khi dùng `addAttributeValue`, Spring LDAP có cơ chế tránh thêm bản sao giống hệt trong context; nhưng server vẫn quyết định equality/schema cuối cùng.

### 10.1. setAttributeValue và setAttributeValues

```java
DirContextOperations entry = ldapTemplate.lookupContext(userDn);

// Đặt thuộc tính với một giá trị (không phải "thêm"):
entry.setAttributeValue("telephoneNumber", "+84 90 123 4567");

// Đặt toàn bộ tập giá trị, thứ tự không có ý nghĩa mặc định:
entry.setAttributeValues("telephoneNumber", new String[] {
    "+84 28 5555 0101",
    "+84 90 123 4567"
});

ldapTemplate.modifyAttributes(entry);
```

Theo Spring LDAP API, `setAttributeValues(name, values)` bỏ qua thứ tự giá trị mặc định khi tính thay đổi. Nếu truyền mảng rỗng hoặc `null`, API này có thể **loại bỏ attribute**, chứ không tạo một attribute chứa danh sách rỗng. Đừng dùng nó với `cn`/`sn` bắt buộc nếu kết quả sẽ khiến entry thiếu thuộc tính.

**Lưu ý trong ví dụ:** hai lời gọi `setAttributeValue` và `setAttributeValues` chỉ minh họa lựa chọn API; lời gọi thứ hai quyết định tập giá trị cuối cùng. Trong code thực tế, chọn **một** ý định nghiệp vụ rõ ràng thay vì thực hiện cả hai liên tiếp.

### 10.2. So sánh cách điều chỉnh tập

| Ý định | Cách dùng `DirContextOperations` |
| --- | --- |
| Lấy một giá trị quan sát được | `getStringAttribute(name)` |
| Đọc toàn bộ String values | `getStringAttributes(name)` |
| Thêm một giá trị | `addAttributeValue(name, value)` |
| Gỡ một giá trị | `removeAttributeValue(name, value)` |
| Thay toàn bộ tập | `setAttributeValues(name, values)` |
| Gán một giá trị duy nhất | `setAttributeValue(name, value)` |

Đối với các tình huống đồng thời, việc đọc context rồi cập nhật có thể làm phát sinh race condition; nếu yêu cầu chỉ ADD/REMOVE một giá trị, `ModificationItem[]` gửi trực tiếp đôi khi dễ kiểm soát hơn việc ghi lại cả snapshot cũ.

## 11. LDAP Repository và ODM: chọn String hay Collection?

Spring LDAP ODM ánh xạ attribute vào field Java qua `@Attribute`, và Spring Data LDAP repository quản lý entity qua `LdapRepository`. Khi attribute đa trị, mapping nên **giữ được tất cả giá trị** cần thiết.

### 11.1. Người dùng với nhiều số điện thoại

Mẫu mô hình:

```java
import java.util.Set;
import javax.naming.Name;
import org.springframework.ldap.odm.annotations.Attribute;
import org.springframework.ldap.odm.annotations.DnAttribute;
import org.springframework.ldap.odm.annotations.Entry;
import org.springframework.ldap.odm.annotations.Id;

@Entry(
    base = "ou=people",
    objectClasses = {
        "top", "person", "organizationalPerson", "inetOrgPerson"
    }
)
public class DirectoryPerson {
    @Id
    private Name dn;

    @DnAttribute(value = "uid", index = 0)
    @Attribute(name = "uid")
    private String uid;

    @Attribute(name = "cn")
    private Set<String> commonNames;

    @Attribute(name = "sn")
    private Set<String> surnames;

    @Attribute(name = "telephoneNumber")
    private Set<String> phoneNumbers;

    public DirectoryPerson() {}
    // Các getter/setter thích hợp được bổ sung trong project.
}
```

`Set<String>` phù hợp ngữ nghĩa tập không thứ tự của `cn`/`sn`/`telephoneNumber`. ODM phiên bản thực tế cần hỗ trợ kiểu collection đã chọn; nên kiểm tra tài liệu và integration test mapping, nhất là với attribute có kiểu binary hoặc subtype đặc biệt.

**Không ép buộc mô hình nghiệp vụ** phải hiển thị hai tên hoặc hai số điện thoại. Nếu sản phẩm muốn một `displayName` hoặc `primaryPhone`, hãy chọn giá trị theo quy tắc nghiệp vụ riêng và lưu mapping/thuộc tính bổ sung khi cần, chứ không tùy tiện chọn “phần tử đầu tiên” từ LDAP.

### 11.2. Nhóm có nhiều DN

Một ví dụ được Spring LDAP ODM hỗ trợ là collection của `javax.naming.Name`:

```java
import java.util.Set;
import javax.naming.Name;
import org.springframework.ldap.odm.annotations.Attribute;
import org.springframework.ldap.odm.annotations.DnAttribute;
import org.springframework.ldap.odm.annotations.Entry;
import org.springframework.ldap.odm.annotations.Id;

@Entry(
    base = "ou=groups",
    objectClasses = {"top", "groupOfUniqueNames"}
)
public class DirectoryGroup {
    @Id
    private Name dn;

    @DnAttribute(value = "cn", index = 0)
    @Attribute(name = "cn")
    private String name;

    @Attribute(name = "uniqueMember")
    private Set<Name> members;

    public DirectoryGroup() {}

    public Name getDn() { return dn; }
    public void setDn(Name dn) { this.dn = dn; }
    public String getName() { return name; }
    public void setName(String name) { this.name = name; }
    public Set<Name> getMembers() { return members; }
    public void setMembers(Set<Name> members) {
        this.members = members;
    }
}
```

`groupOfUniqueNames` và `uniqueMember` khác với `groupOfNames` và `member`, nhưng cùng giúp minh họa DN-valued multi-valued attribute. Spring LDAP ODM có hỗ trợ so sánh các giá trị kiểu `Name` theo ngữ nghĩa DN khi tính thay đổi; điều đó giúp tránh so sánh đơn giản dựa trên cách escape/viết hoa của chuỗi DN.

Không coi `@Id` là khóa số. Kiểu DN trong ODM là `javax.naming.Name`; `@DnAttribute` giúp tính thành phần RDN, nhưng không quyết định cardinality của một attribute độc lập.

### 11.3. Repository không thay thế schema

```java
import org.springframework.data.ldap.repository.LdapRepository;

public interface PersonRepository
        extends LdapRepository<DirectoryPerson> {
}
```

Repository có thể `save(entity)`, `findById(Name)` và `delete(entity)`. Nhưng `save` không được phép ghi hai giá trị vào attribute `SINGLE-VALUE` chỉ vì Java field là `Set`; server có thể từ chối.

Với yêu cầu **chỉ thêm/gỡ một member** trong group, hãy xem xét `LdapTemplate.modifyAttributes` và những thao tác delta rõ ràng thay vì mặc định ghi lại toàn bộ collection khi có nhiều actor cùng sửa nhóm.

## 12. Truy vấn theo một giá trị trong attribute đa trị

LDAP filter theo equality có thể khớp một entry nếu **ít nhất một giá trị** của attribute thỏa điều kiện, khi attribute có equality matching rule phù hợp.

Ví dụ:

```ldif
dn: uid=linh,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: linh
cn: Linh Nguyen
cn: Nguyen Thu Linh
sn: Nguyen
telephoneNumber: +84 28 5555 0101
telephoneNumber: +84 90 123 4567
```

Tìm theo một tên:

```text
(cn=Linh Nguyen)
```

Entry có thể được trả về vì **một** giá trị `cn` khớp, dù attribute chứa thêm giá trị khác. Filter presence `(telephoneNumber=*)` kiểm tra sự hiện diện của attribute, **không** có nghĩa attribute chỉ chứa một giá trị.

Với nhiều điều kiện:

```text
(&(cn=Linh Nguyen)(cn=Nguyen Thu Linh))
```

Theo semantics của AND filter, từng phép so khớp có thể được thỏa bởi **những giá trị khác nhau** trong cùng multi-valued attribute. Không hiểu điều kiện này như một giá trị phải đồng thời bằng hai chuỗi khác nhau.

### 12.1. Spring LDAP query an toàn

```java
import static org.springframework.ldap.query.LdapQueryBuilder.query;

var ldapQuery = query()
    .base("ou=people")
    .where("telephoneNumber").is(phoneInput);

var users = ldapTemplate.search(
    ldapQuery,
    (org.springframework.ldap.core.AttributesMapper<String>) attrs ->
        (String) attrs.get("uid").get()
);
```

`LdapQueryBuilder` mã hóa giá trị của filter theo quy tắc LDAP. Không nối input người dùng thành `"(telephoneNumber=" + phoneInput + ")"`, bởi các ký tự `*`, `(`, `)` và dấu gạch chéo ngược có thể thay đổi ý nghĩa filter.

**Filter escaping không giống DN escaping.** Nếu cần biến giá trị UID thành RDN, dùng `LdapNameBuilder.add("uid", uid)`; nếu cần tìm theo attribute, dùng query builder.

### 12.2. Không nên đoán thứ tự kết quả và thuộc tính

Ngay cả khi search trả entry theo một thứ tự nào đó, các giá trị trong `telephoneNumber` cũng không tự có thứ tự “công việc trước, di động sau”. Nếu ứng dụng cần phân biệt số chính/phụ, nên thiết kế kiểu thông tin bổ sung hoặc thuộc tính riêng được schema và nghiệp vụ hỗ trợ.

## 13. Phân biệt attribute đa trị với RDN đa thành phần

**DN** là đường dẫn định danh entry, gồm các **RDN**. Một RDN có thể chứa **nhiều attribute-value assertions** (*multi-valued RDN*), ví dụ:

```text
cn=Linh Nguyen+uid=linh,ou=people,dc=example,dc=org
^^^^^^^^^^^^^^^^^^^^^^^
    cùng MỘT RDN với hai AVA
```

Đây **không phải** ví dụ của một attribute `cn` có hai giá trị. Multi-valued RDN nói rằng **một thành phần tên** được cấu tạo bởi hai cặp attribute/value; multi-valued attribute nói rằng **một loại thuộc tính trong entry** chứa nhiều giá trị.

Ngược lại:

```ldif
dn: uid=linh,ou=people,dc=example,dc=org
cn: Linh Nguyen
cn: Nguyen Thu Linh
```

cho thấy attribute `cn` đa trị nhưng RDN của entry chỉ là `uid=linh`.

Để thao tác với DN chứa dấu phẩy, dấu cộng hoặc các ký tự cần escape, dùng `LdapNameBuilder` hoặc `javax.naming.ldap.LdapName`; không dùng `String.split(",")`. Khi đổi giá trị tham gia RDN, có thể cần thao tác **Modify DN/rename**, không chỉ `REPLACE_ATTRIBUTE` tùy ý.

## 14. Lỗi schema hay gặp khi cập nhật cardinality

LDAP server là nơi xác nhận thay đổi cuối cùng. Một request hợp lệ về Java vẫn có thể bị từ chối bởi schema hoặc ACL.

| Trường hợp | LDAP result code thường gặp | Nguyên nhân |
| --- | --- | --- |
| Thêm giá trị thứ hai vào attribute `SINGLE-VALUE` | `19 — constraintViolation` hoặc lỗi schema tùy server | Vượt giới hạn cardinality. |
| `ADD_ATTRIBUTE` giá trị đã tồn tại/tương đương | `20 — attributeOrValueExists` | Tập giá trị không chấp nhận duplicate theo equality rule. |
| `REMOVE_ATTRIBUTE` một giá trị không có | `16 — noSuchAttribute` | Yêu cầu xóa dữ liệu không tồn tại. |
| Xóa giá trị cuối của `MUST cn` hoặc `MUST sn` | `65 — objectClassViolation` | Entry không còn thỏa ràng buộc bắt buộc. |
| Attribute không có trong schema | `17 — undefinedAttributeType` | Không biết loại thuộc tính. |
| Attribute không được object class cho phép | `65 — objectClassViolation` | Đưa attribute ngoài tập cho phép. |
| Giá trị sai syntax | `21 — invalidAttributeSyntax` | Dữ liệu không đúng định dạng được schema khai báo. |
| Bind account không đủ quyền ghi | `50 — insufficientAccessRights` | ACL chặn Modify. |
| DN entry không tồn tại hoặc sai base | `32 — noSuchObject` | Đích ghi sai/đã đổi DN hoặc bị xóa. |
| Lỗi kết nối/TLS | Có thể không có LDAP result code | Network/certificate hoặc server không sẵn sàng. |

Đừng xử lý lỗi cardinality bằng cách đổi sang tài khoản admin hoặc tắt schema validation. Hãy kiểm tra attribute type, `objectClass`, số giá trị hiện có, loại Modify và quyền server.

### 14.1. Java kiểu String không làm LDAP trở thành SINGLE-VALUE

```java
@Attribute(name = "telephoneNumber")
private String telephoneNumber;
```

Một field `String` trong ODM cho thấy **ứng dụng chỉ lưu một giá trị trong model**, không sửa schema của directory. Khi LDAP có nhiều số điện thoại, mapping này có thể gây mất thông tin hoặc chọn một giá trị không có bảo đảm thứ tự. Nếu nghiệp vụ yêu cầu bảo toàn mọi số, dùng collection phù hợp và integration test.

### 14.2. Java kiểu Set không biến attribute đơn trị thành đa trị

```java
@Attribute(name = "appEmployeeCode")
private Set<String> employeeCodes;
```

Nếu schema của `appEmployeeCode` là `SINGLE-VALUE`, server vẫn từ chối hai mã khác nhau. Đúng cách là sửa model cho phù hợp schema hoặc điều chỉnh **thiết kế schema qua quy trình quản trị**, không tự bỏ qua lỗi.

## 15. Atomicity, đồng thời và rủi ro mất dữ liệu

### 15.1. Một LDAP ModifyRequest là nguyên tử

Theo RFC 4511, các thay đổi nằm trong **một** ModifyRequest phải được áp dụng theo thứ tự và nguyên tử trên entry đích.

```java
ModificationItem[] changes = {
    new ModificationItem(
        DirContext.REPLACE_ATTRIBUTE,
        new BasicAttribute("mail", "linh.new@example.org")
    ),
    new ModificationItem(
        DirContext.ADD_ATTRIBUTE,
        new BasicAttribute("telephoneNumber", "+84 90 123 4567")
    )
};

ldapTemplate.modifyAttributes(userDn, changes);
```

Nếu một thay đổi trong request bị schema từ chối, server không được chỉ ghi một nửa các thay đổi của request đó. Nhưng **hai request Modify riêng biệt không mặc nhiên là một transaction ACID**, kể cả khi `@Transactional` trên service Java.

### 15.2. Lost update khi ghi đè toàn bộ tập

```text
Ban đầu member = {Linh, An}

Client A đọc member = {Linh, An}, muốn bỏ An
Client B thêm Minh bằng ADD_ATTRIBUTE -> {Linh, An, Minh}
Client A REPLACE_ATTRIBUTE {Linh}      -> {Linh}

Kết quả: Minh cũng bị mất, dù A không định xóa Minh.
```

Nếu chỉ muốn xóa An, hãy dùng `REMOVE_ATTRIBUTE("member", DN_An)` thay vì đọc toàn tập rồi REPLACE. Điều này giảm rủi ro ghi đè nhưng không biến LDAP Modify thành transaction có isolation đa entry; các quy tắc đồng thời và controls phụ thuộc server vẫn cần được xem xét.

### 15.3. Chính sách retry khi chưa biết request đã thành công

Sau lỗi timeout, server có thể đã thực thi ADD hoặc REMOVE nhưng client không nhận response. Gửi lại ADD có thể báo giá trị trùng; gửi lại REMOVE có thể báo giá trị không tồn tại. Vì vậy:

1. Xác minh trạng thái thực tế bằng một kết nối tin cậy.
2. So sánh với **trạng thái nghiệp vụ mong muốn**.
3. Chỉ retry khi thực sự cần, có giới hạn và ghi nhận kết quả.
4. Không coi một giá trị bị vắng trong response là bằng chứng server đã xóa: ACL đọc có thể che giá trị.

## 16. Kiểm thử đơn trị/đa trị trên directory thực

Unit test với mock kiểm tra logic Java, nhưng **không chứng minh schema thật**. Cần integration test trên directory thử nghiệm có OU `ou=people`, schema `inetOrgPerson` và tài khoản được phép CRUD. Không thực hiện thử nghiệm ADD/REMOVE/REPLACE lên dữ liệu production.

### 16.1. Ma trận kiểm thử

| Test | Dữ liệu trước | Thao tác | Kỳ vọng |
| --- | --- | --- | --- |
| Tạo attribute đa trị | Không có `telephoneNumber` | ADD A | Có A. |
| Bổ sung giá trị mới | `{A}` | ADD B | Có `{A,B}`. |
| Đọc đầy đủ | `{A,B}` | `getAll()`/`getStringAttributes()` | Có cả A và B, không phụ thuộc thứ tự. |
| ADD trùng | `{A,B}` | ADD A | Server có thể báo duplicate theo schema. |
| REMOVE một giá trị | `{A,B}` | REMOVE B | Chỉ còn A. |
| REPLACE toàn tập | `{A,B}` | REPLACE C | Chỉ còn C. |
| Xóa toàn attribute tùy chọn | `{C}` | REMOVE không value | Không còn attribute. |
| Xóa giá trị cuối của `cn` | `cn={A}` | REMOVE A | Bị schema từ chối. |
| Attribute SINGLE-VALUE tùy chỉnh | `appEmployeeCode={X}` | ADD Y | Bị từ chối do cardinality. |
| Gộp hai changes, một change lỗi | Entry hợp lệ | REPLACE mail và ADD trùng | Toàn request thất bại, mail không đổi. |
| Group membership | `member={Linh,An}` | ADD Minh | Có cả ba DN, không mất người cũ. |
| Nhiều tác nhân cùng sửa | `member={Linh,An}` | A/B sửa song song | Không suy luận mọi REPLACE an toàn; kiểm tra lost update. |

### 16.2. Integration test Java 17 + Spring LDAP

Ví dụ tạo entry thử nghiệm có UID ngẫu nhiên, thêm hai số điện thoại, đọc lại tập và dọn dẹp:

```java
package com.example.directory;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.Set;
import java.util.UUID;
import javax.naming.Name;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.BasicAttributes;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

@SpringBootTest
class MultiValueAttributeIT {

    @Autowired
    private LdapTemplate ldap;

    @Test
    void keepsBothPhoneNumbersAndRemovesOnlyOne() {
        String uid = "lab" + UUID.randomUUID().toString()
            .replace("-", "").substring(0, 10);
        Name dn = LdapNameBuilder.newInstance("ou=people")
            .add("uid", uid)
            .build();

        Attributes attrs = new BasicAttributes(true);
        Attribute classes = new BasicAttribute("objectClass");
        classes.add("top");
        classes.add("person");
        classes.add("organizationalPerson");
        classes.add("inetOrgPerson");
        attrs.put(classes);
        attrs.put("uid", uid);
        attrs.put("cn", "Lab " + uid);
        attrs.put("sn", "Test");

        boolean created = false;
        try {
            ldap.bind(dn, null, attrs);
            created = true;

            modify(dn, DirContext.ADD_ATTRIBUTE,
                new BasicAttribute("telephoneNumber", "+84 28 1111"));
            modify(dn, DirContext.ADD_ATTRIBUTE,
                new BasicAttribute("telephoneNumber", "+84 90 2222"));

            assertThat(readPhones(dn)).containsExactlyInAnyOrder(
                "+84 28 1111", "+84 90 2222"
            );

            modify(dn, DirContext.REMOVE_ATTRIBUTE,
                new BasicAttribute("telephoneNumber", "+84 28 1111"));
            assertThat(readPhones(dn)).containsExactly("+84 90 2222");
        } finally {
            if (created) {
                ldap.unbind(dn);
            }
        }
    }

    private void modify(Name dn, int type, Attribute attribute) {
        ldap.modifyAttributes(dn, new ModificationItem[] {
            new ModificationItem(type, attribute)
        });
    }

    private Set<String> readPhones(Name dn) {
        return ldap.lookup(dn,
            (AttributesMapper<Set<String>>) attrs ->
                LdapAttributeValues.strings(attrs, "telephoneNumber")
        );
    }
}
```

`LdapAttributeValues` là helper ở mục 7; khi đưa vào project thực tế, import đúng package. Test giả định directory cho phép tạo/xóa `inetOrgPerson` và `telephoneNumber` theo schema, tài khoản test có quyền và URL LDAPS/StartTLS được cấu hình đúng. Nếu server mất kết nối trong `finally`, cleanup có thể thất bại: cần dọn fixture trong môi trường test.

### 16.3. Kiểm thử single-value thế nào cho đúng?

Không nên dùng `createTimestamp` làm ví dụ ghi hai giá trị chỉ để chứng minh `SINGLE-VALUE`: đây là operational attribute do server quản lý, nên lỗi có thể là **NO-USER-MODIFICATION**, không phải do cardinality.

Muốn kiểm chứng cardinality một cách cô lập, sử dụng **attribute tùy chỉnh** được schema test khai báo `SINGLE-VALUE` và **cho phép ứng dụng ghi**, như `appEmployeeCode` trong mục 5. Kịch bản:

1. Tạo entry có auxiliary object class hợp lệ và `appEmployeeCode=X`.
2. Gửi Modify ADD `appEmployeeCode=Y`.
3. Xác nhận server từ chối và giá trị X vẫn được giữ.
4. Thử REPLACE thành Y, xác nhận chỉ còn Y.
5. Không thay schema của directory dùng chung chỉ để chạy test.

## 17. Thiết kế API và vận hành an toàn

Một REST API quản lý người dùng nên **định nghĩa rõ chủ đích của mỗi thao tác**:

```text
GET    /users/{uid}/phone-numbers       -> đọc tập số
POST   /users/{uid}/phone-numbers       -> thêm đúng một số
DELETE /users/{uid}/phone-numbers/...   -> gỡ đúng một số
PUT    /users/{uid}/phone-numbers       -> thay toàn bộ tập (nếu được phép)
```

Nếu có PUT thay toàn bộ, phải mô tả rõ semantics và điều kiện cập nhật đồng thời cho client; không triển khai PUT bằng cách “append thêm” khiến API khó dự đoán. Với attribute đơn trị như mã nhân viên, endpoint phải validate rằng giá trị là **một** scalar, không nhận danh sách.

### 17.1. Checklist trước khi ghi

- [ ] Xác nhận DN đúng, base DN của `ContextSource` không bị lặp.
- [ ] Đã xem `attributeTypes` để biết có `SINGLE-VALUE` không.
- [ ] Đã xem `objectClasses` để biết thuộc tính là `MUST` hay `MAY`.
- [ ] Phân biệt “được phép nhiều giá trị” với “đang có nhiều giá trị”.
- [ ] Không giả định thứ tự LDAP values là thứ tự nghiệp vụ.
- [ ] Không làm mất giá trị khác khi chỉ thêm/gỡ một value.
- [ ] Không dùng `getStringAttribute` để xuất toàn bộ attribute đa trị.
- [ ] Xử lý duplicate theo matching rule của LDAP server.
- [ ] Validate dữ liệu, kích thước, số lượng và quyền sửa thuộc tính.
- [ ] Dùng `LdapNameBuilder` để dựng DN, `LdapQueryBuilder` để dựng filter.
- [ ] Có xử lý lỗi schema, ACL, network và retry không chắc trạng thái.
- [ ] Có integration test và quy trình khôi phục trước khi sửa dữ liệu thật.

### 17.2. Bảo mật dữ liệu

Các attribute đa trị có thể chứa **DN thành viên nhóm, email, số liên lạc hoặc thông tin nhạy cảm**. Chỉ trả những field được phép qua DTO, giới hạn quyền bind account theo OU và attribute, dùng LDAPS/StartTLS với xác minh chứng chỉ và không log toàn bộ tập giá trị.

Đặc biệt, quyền `write member` của group có thể liên quan tới cấp quyền trong hệ thống khác; không trao cho API đọc danh bạ quyền cập nhật group chỉ vì đều sử dụng `LdapRepository`.

## 18. Bài tập và câu hỏi tự kiểm tra

1. Giải thích tại sao `MUST cn` của `person` không có nghĩa `cn` là attribute đơn trị. Dự đoán kết quả khi entry có hai tên `cn`.
2. Cho `telephoneNumber={A,B}`. Dự đoán trạng thái sau các thao tác: ADD C, REMOVE B, REPLACE X, rồi REPLACE tập rỗng; giải thích thay đổi từng bước.
3. Một entity Java có `@Attribute(name="telephoneNumber") String phone`. Directory chứa ba số. Hãy chỉ ra nguy cơ và viết lại mapping/API đọc để giữ mọi giá trị.
4. Cho schema `appEmployeeCode SINGLE-VALUE` và `appLabel` đa trị. Thiết kế object class `MAY` cả hai; mỗi attribute được phép có bao nhiêu giá trị?
5. Giải thích tại sao `new BasicAttribute("cn", true)` không có nghĩa `cn` bị ép thành đơn trị. Thuộc tính nào quyết định cardinality phía server?
6. Với `groupOfNames` chứa Linh và An, viết `ModificationItem` để thêm Minh, gỡ An và giải thích rủi ro khi REPLACE toàn `member`.
7. Dùng `ldapsearch` tra `subschemaSubentry`, `attributeTypes` và `objectClasses` của directory test. Tìm một thuộc tính `SINGLE-VALUE` và một thuộc tính đa trị.
8. Một lần ADD số điện thoại trả `attributeOrValueExists` dù hai chuỗi khác nhau về chữ hoa/khoảng trắng. Matching rule của server ảnh hưởng thế nào?
9. So sánh multi-valued attribute `cn` với multi-valued RDN `cn=Linh+uid=linh`. Chúng là cùng một khái niệm không?
10. Viết integration test chứng minh `getAll()` trả đủ hai giá trị, `get()` không bảo đảm trả “giá trị chính”, và việc REMOVE một giá trị giữ nguyên giá trị kia.
11. Khi client A đọc rồi REPLACE toàn bộ `member` trong lúc client B ADD một member mới, dữ liệu có thể mất ra sao? Đề xuất thao tác thay thế an toàn hơn.
12. Vì sao không thể dùng `createTimestamp` làm test ghi hai giá trị để chứng minh lỗi cardinality một cách chính xác?

## 19. Tài liệu tham khảo

- [RFC 4512 — LDAP Directory Information Models](https://www.rfc-editor.org/rfc/rfc4512): attribute type, `SINGLE-VALUE`, schema, operational attributes và ràng buộc.
- [RFC 4519 — LDAP Schema for User Applications](https://www.rfc-editor.org/rfc/rfc4519): `cn`, `sn`, `c`, `telephoneNumber`, `person` và `groupOfNames`.
- [RFC 4511 — LDAP Protocol](https://www.rfc-editor.org/rfc/rfc4511): ModifyRequest add/delete/replace và result codes.
- [RFC 4517 — LDAP Syntaxes and Matching Rules](https://www.rfc-editor.org/rfc/rfc4517): so sánh giá trị và syntax.
- [RFC 2307 — Using LDAP as a Network Information Service](https://www.rfc-editor.org/rfc/rfc2307): các attribute POSIX như `uidNumber`.
- [Spring LDAP — Object-Directory Mapping](https://docs.spring.io/spring-ldap/reference/odm.html): `@Entry`, `@Id`, `@Attribute` và mapping tập `Name`.
- [Spring LDAP API — LdapDataEntry](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/LdapDataEntry.html): `getStringAttributes`, `addAttributeValue`, `removeAttributeValue`, `setAttributeValues`.
- [Spring LDAP — LdapTemplate](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/core/LdapTemplate.html): search, lookup và modify.
- [Spring Data LDAP Reference](https://docs.spring.io/spring-data/ldap/reference/): repository, entity mapping và CRUD.
- [Java SE 17 — Attribute](https://docs.oracle.com/en/java/javase/17/docs/api/java.naming/javax/naming/directory/Attribute.html) và [BasicAttribute](https://docs.oracle.com/en/java/javase/17/docs/api/java.naming/javax/naming/directory/BasicAttribute.html): tập giá trị và hành vi JNDI.
- [RFC 4514 — Distinguished Names](https://www.rfc-editor.org/rfc/rfc4514) và [RFC 4515 — LDAP Filters](https://www.rfc-editor.org/rfc/rfc4515): ngữ nghĩa DN/RDN và escaping filter.
