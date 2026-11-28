# Thuộc tính chuỗi, nhị phân, thời gian và giá trị định danh

Trong **SPRING_DATA_LDAP**, ứng dụng Java (các ví dụ dùng Java 17+) truy cập dịch vụ thư mục LDAP bằng Spring Data LDAP repository, Spring LDAP ODM và `LdapTemplate`. Directory lưu các entry theo DN (*Distinguished Name*), `objectClass` và schema. Mỗi thuộc tính LDAP có **syntax** quy định cấu trúc/định dạng giá trị; schema còn khai báo matching rule, số lượng giá trị, quyền sửa và các ràng buộc liên quan.

Khi ánh xạ entry sang Java, không thể mặc định mọi giá trị đều là `String`. Một thuộc tính có thể là chuỗi UTF-8, dữ liệu nhị phân, thời gian theo Generalized Time, DN, số nguyên, boolean hoặc UUID. Cùng một ý nghĩa nghiệp vụ còn có thể có cách biểu diễn khác nhau giữa các LDAP server. Ví dụ `entryUUID` theo RFC 4530 là giá trị UUID dạng chuỗi chuẩn LDAP, trong khi `objectGUID` của Active Directory được truyền như một chuỗi octet nhị phân 16 byte.

Bài học này giúp bạn đọc schema, lựa chọn kiểu Java, cấu hình `@Attribute`/ODM, chuyển đổi Generalized Time, xử lý binary và nhận diện định danh ổn định. Mục tiêu là **giữ đúng dữ liệu và ngữ nghĩa**, tránh lỗi chuyển mã, sai múi giờ, UUID đảo byte hoặc dùng DN có thể thay đổi làm khóa bền vững.

Sau bài này, bạn có thể:

- Phân biệt LDAP syntax với Java runtime type và matching rule.
- Nhận biết các syntax phổ biến: Directory String, Octet String, Generalized Time, DN, Integer, Boolean, JPEG và UUID.
- Hiểu JNDI thường trả giá trị thuộc tính dưới dạng `String` hoặc `byte[]` tùy syntax/provider.
- Ánh xạ binary bằng `@Attribute(type = Attribute.Type.BINARY)` và cấu hình binary attributes khi dùng JNDI.
- Chuyển Generalized Time sang `Instant` bằng converter có quy tắc múi giờ rõ ràng.
- Phân biệt `entryUUID`, `objectGUID`, `uid` và DN.
- Kiểm thử giá trị đơn trị/đa trị, binary, thời gian và định danh trên LDAP test directory.

## 1. Syntax của LDAP không phải kiểu Java

Trong LDAP, một attribute type được schema mô tả bằng tên/OID, syntax và các matching rule. **Syntax** nói giá trị có dạng gì; **matching rule** nói server so sánh hai giá trị như thế nào.

Ví dụ:

```text
Attribute type:  mail
Syntax:          Directory String
Matching rule:   caseIgnoreMatch
Java mapping:    String

Attribute type:  jpegPhoto
Syntax:          JPEG
Matching rule:   phụ thuộc schema/server
Java mapping:    byte[]

Attribute type:  modifyTimestamp
Syntax:          Generalized Time
Matching rule:   generalizedTimeMatch / generalizedTimeOrderingMatch
Java mapping:    Instant (qua converter)
```

Một giá trị Directory String có thể được truyền bằng UTF-8, nhưng JNDI không trả về một kiểu Java riêng cho `DirectoryString`; thông thường nó trả `String`. Một giá trị Octet String có thể là bất kỳ byte nào và JNDI trả `byte[]` khi provider nhận biết thuộc tính đó là binary. Giá trị Generalized Time vẫn thường đến Java dưới dạng chuỗi; ứng dụng phải chuyển đổi sang `Instant` hoặc kiểu thời gian phù hợp.

### 1.1. Các syntax thường gặp

| Syntax | OID | Ý nghĩa | Java mapping thường dùng |
|---|---|---|---|
| Directory String | `1.3.6.1.4.1.1466.115.121.1.15` | Chuỗi Unicode theo encoding LDAP UTF-8 | `String` |
| Octet String | `1.3.6.1.4.1.1466.115.121.1.40` | Dãy byte tùy ý, không nhất thiết đọc được như văn bản | `byte[]` |
| Generalized Time | `1.3.6.1.4.1.1466.115.121.1.24` | Ngày/giờ có timezone | `String` ở JNDI; `Instant` qua converter |
| DN | `1.3.6.1.4.1.1466.115.121.1.12` | Tên phân biệt của một entry | `javax.naming.Name` hoặc `String` theo mục đích |
| Integer | `1.3.6.1.4.1.1466.115.121.1.27` | Số nguyên LDAP | `String` ở JNDI; `BigInteger`/kiểu số qua converter |
| Boolean | `1.3.6.1.4.1.1466.115.121.1.7` | Giá trị TRUE/FALSE | `String` ở JNDI; `Boolean` qua converter |
| JPEG | `1.3.6.1.4.1.1466.115.121.1.28` | Nội dung ảnh JPEG | `byte[]` |
| UUID (RFC 4530) | `1.3.6.1.1.16.1` | UUID 128-bit; LDAP encoding là chuỗi ASCII canonical | `String` rồi parse `UUID` |

Các OID trên là syntax được chuẩn hóa, nhưng **không có nghĩa mọi server đều triển khai mọi syntax hoặc mọi attribute type**. Schema thực tế của directory quyết định attribute nào được phép, matching rule nào áp dụng và attribute có operational/read-only hay không.

### 1.2. Syntax và matching rule là hai thứ khác nhau

RFC 4517 xác định syntax và matching rule riêng. Cùng một kiểu dữ liệu có thể có quy tắc so sánh khác nhau:

| Matching rule | Ý nghĩa minh họa |
|---|---|
| `caseIgnoreMatch` | So sánh chuỗi không phân biệt hoa/thường |
| `caseExactMatch` | So sánh chuỗi có phân biệt hoa/thường |
| `octetStringMatch` | So sánh dãy byte |
| `generalizedTimeMatch` | So sánh thời điểm theo Generalized Time |
| `generalizedTimeOrderingMatch` | So sánh thứ tự thời gian |
| `distinguishedNameMatch` | So sánh DN theo semantics của directory |
| `uuidMatch` | So sánh UUID theo syntax UUID |

Do đó, không nên giả định Java `String.equals()` có cùng semantics với LDAP equality filter. Ví dụ server có thể dùng `caseIgnoreMatch` cho `uid`, trong khi ứng dụng Java so sánh hai chuỗi phân biệt hoa/thường. Với ngày giờ có offset khác nhau, so sánh chuỗi theo thứ tự từ điển cũng không thay thế `generalizedTimeOrderingMatch`.

## 2. Chuỗi: Directory String, IA5 String và dữ liệu Unicode

Directory String là syntax phổ biến cho `cn`, `sn`, `description` và nhiều thuộc tính người dùng. Theo RFC 4517, giá trị Directory String được mã hóa UTF-8 trong LDAP. JNDI LDAP provider thường đưa giá trị này thành `String`.

Ví dụ:

```ldif
dn: uid=lan,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: lan
cn: Lan Nguyen
sn: Nguyen
description: Nhân viên hỗ trợ khách hàng
mail: lan@example.org
```

Ánh xạ cơ bản:

```java
String uid = (String) attributes.get("uid").get();
String cn = (String) attributes.get("cn").get();
String description =
        (String) attributes.get("description").get();
```

Không tự chuyển mọi chuỗi LDAP qua ASCII. Directory String cho phép các code point Unicode; nếu dùng charset không phù hợp, tên có dấu tiếng Việt có thể bị hỏng.

### 2.1. IA5 String không phải Directory String

IA5 String giới hạn ký tự trong bộ ký tự IA5/ASCII. Một số schema dùng IA5 String cho địa chỉ email, URL hoặc dữ liệu cần giới hạn ASCII. **Không được giả định** tất cả attribute có vẻ giống văn bản đều là Directory String.

Schema và matching rule mới quyết định dữ liệu được phép. Nếu ứng dụng chấp nhận email có ký tự Unicode hoặc internationalized domain, phải xác định rõ quy tắc ở tầng nghiệp vụ và server; không tự nới schema hoặc ép mọi giá trị thành ASCII.

### 2.2. Đọc giá trị đơn trị và đa trị

LDAP attribute có thể chứa một hoặc nhiều giá trị. `Attribute.get()` chỉ lấy **một giá trị**; nếu attribute không ordered và có nhiều giá trị, giá trị được trả có thể là bất kỳ giá trị nào. Khi cần toàn bộ membership, certificate hay nhiều email, hãy duyệt `getAll()`:

```java
import java.util.ArrayList;
import java.util.List;
import javax.naming.NamingEnumeration;
import javax.naming.directory.Attribute;
import javax.naming.NamingException;

static List<String> readAllStrings(
        Attribute attribute) throws NamingException {
    List<String> values = new ArrayList<>();
    if (attribute == null) {
        return values;
    }

    NamingEnumeration<?> all = attribute.getAll();
    try {
        while (all.hasMore()) {
            Object value = all.next();
            if (!(value instanceof String text)) {
                throw new IllegalStateException(
                        "Attribute không phải chuỗi: "
                                + attribute.getID());
            }
            values.add(text);
        }
    } finally {
        all.close();
    }
    return List.copyOf(values);
}
```

Không dùng `get(0)` để đại diện cho một tập giá trị unordered. Schema có `SINGLE-VALUE` hay không và matching rule quyết định semantics; đừng dựa vào thứ tự ngẫu nhiên của server.

## 3. Binary: Octet String, ảnh và certificate

Binary attribute có thể chứa:

- Ảnh đại diện như `jpegPhoto` hoặc `thumbnailPhoto`.
- Chứng chỉ X.509 như `userCertificate`, `cACertificate`.
- GUID, SID hoặc dữ liệu đặc thù của nhà cung cấp.
- Các blob nhị phân do ứng dụng tự định nghĩa theo schema.

Không chuyển các giá trị này thành chuỗi bằng charset mặc định. Một byte sequence có thể chứa byte NUL, byte ngoài UTF-8 hoặc cấu trúc ASN.1; nếu giải mã như văn bản, dữ liệu sẽ bị hỏng.

### 3.1. JNDI trả binary dưới dạng byte[]

JNDI LDAP provider thường trả attribute value dưới dạng `String` hoặc `byte[]`. Danh sách binary mặc định phụ thuộc provider. Thuộc tính có option `;binary` thường được xử lý như binary; provider còn có thể có danh sách built-in như `jpegPhoto`, `userCertificate` và các thuộc tính liên quan.

Với thuộc tính binary riêng, JNDI provider của Oracle hỗ trợ environment property:

```java
import java.util.Hashtable;

Hashtable<String, Object> environment = new Hashtable<>();
environment.put(
        "java.naming.ldap.attributes.binary",
        "objectGUID myBinaryKey");
```

Giá trị là danh sách tên attribute cách nhau bằng dấu cách. Đây là **JNDI provider property**, không phải LDAP schema OID và không phải quy tắc chung cho mọi LDAP client library.

Một thuộc tính trả về:

```java
Object raw = attributes.get("jpegPhoto").get();
if (raw instanceof byte[] bytes) {
    // Dữ liệu nhị phân; giữ nguyên bytes.
} else {
    throw new IllegalStateException(
            "Provider không trả jpegPhoto dưới dạng byte[]");
}
```

### 3.2. Option ;binary không đồng nghĩa với syntax

LDAP attribute description có thể có option:

```text
userCertificate;binary
```

Option `;binary` là **transfer option** yêu cầu truyền giá trị ở dạng binary trong trường hợp phù hợp, ví dụ dữ liệu ASN.1 được mã hóa. Nó không thay đổi schema attribute type và không có nghĩa mọi attribute có syntax Octet String đều phải thêm option này. Hãy theo đúng yêu cầu của server và schema.

### 3.3. Spring LDAP ODM ánh xạ binary

Trong Spring LDAP ODM, `@Attribute` có trường `type` để báo cho JNDI provider rằng giá trị phải được trả dưới dạng chuỗi hay binary:

```java
import javax.naming.Name;
import org.springframework.ldap.odm.annotations.Attribute;
import org.springframework.ldap.odm.annotations.Entry;
import org.springframework.ldap.odm.annotations.Id;

@Entry(
        objectClasses = {
                "top", "person", "organizationalPerson", "inetOrgPerson"
        },
        base = "ou=people"
)
public class PersonEntry {

    @Id
    private Name dn;

    @Attribute(name = "uid")
    private String uid;

    @Attribute(
            name = "jpegPhoto",
            type = Attribute.Type.BINARY,
            syntax = "1.3.6.1.4.1.1466.115.121.1.28"
    )
    private byte[] photo;

    public Name getDn() { return dn; }
    public void setDn(Name dn) { this.dn = dn; }
    public String getUid() { return uid; }
    public void setUid(String uid) { this.uid = uid; }
    public byte[] getPhoto() {
        return photo == null ? null : photo.clone();
    }
    public void setPhoto(byte[] photo) {
        this.photo = photo == null ? null : photo.clone();
    }
}
```

`Attribute.Type.BINARY` hướng dẫn mapping/provider dùng `byte[]`; `syntax` khai báo syntax OID để converter có thêm ngữ cảnh. Đây là hai thông tin liên quan nhưng khác nhau: **binary/string representation** không thay thế schema syntax.

Trong ví dụ, `jpegPhoto` được khai báo là JPEG syntax. Nếu schema của server hoặc attribute thực tế khác, phải thay đúng OID và kiểu; không gán syntax JPEG cho mọi blob.

### 3.4. Giới hạn kích thước và bảo vệ binary

Binary thường lớn hơn thuộc tính text. Khi tìm danh bạ, không nên tải ảnh hoặc certificate nếu màn hình không cần chúng. Hãy chọn projection chỉ chứa các attribute cần dùng bằng `LdapQueryBuilder.attributes(...)` hoặc `SearchControls.setReturningAttributes(...)` phù hợp với API đang dùng.

Nếu cần đọc ảnh:

```java
byte[] photo = entry.getPhoto();
if (photo != null && photo.length > 2_000_000) {
    throw new IllegalArgumentException("Ảnh vượt giới hạn ứng dụng");
}
```

Giới hạn 2 MB ở đây chỉ là ví dụ nghiệp vụ. Hãy kiểm tra cả kích thước upload trước khi gửi LDAP, kích thước response, số entry đồng thời và áp lực heap. Không log nội dung binary hoặc Base64 certificate; không trả private key/secret attribute ra API.

## 4. Thời gian: Generalized Time

LDAP Generalized Time biểu diễn ngày và giờ, có timezone. Syntax OID:

```text
1.3.6.1.4.1.1466.115.121.1.24
```

Ví dụ:

```text
20261126143000Z
20261126143000+0700
20261126073000-0700
```

Các ví dụ biểu diễn dạng thời điểm theo UTC hoặc offset. Theo RFC 4517, timezone là thành phần bắt buộc của Generalized Time; dạng `Z` được khuyến nghị ưu tiên. Format đầy đủ thường gặp là:

```text
YYYYMMDDHH[MM[SS[.fraction]]](Z|+hh[mm]|-hh[mm])
```

Fraction có thể biểu diễn phần của giờ, phút hoặc giây tùy độ chính xác đã xuất hiện. Một ứng dụng nên xác định **profile format được chấp nhận** thay vì viết parser quá đơn giản rồi tuyên bố hỗ trợ toàn bộ Generalized Time.

### 4.1. Không ánh xạ thời gian bằng chuỗi tự do

Nếu giữ thời gian dưới `String`:

```java
String modified = (String) attrs.get("modifyTimestamp").get();
```

thì mỗi nơi sử dụng có thể tự parse theo một cách khác nhau, dễ gây:

- Nhầm timezone của JVM với timezone của LDAP value.
- So sánh chuỗi có offset khác nhau như thể cùng định dạng UTC.
- Mất phần mili giây hoặc phần giây thập phân.
- Lưu thời gian local mà không có offset.

Với timestamp của nghiệp vụ, `Instant` thường là lựa chọn tốt vì biểu diễn một điểm trên timeline UTC. Với lịch địa phương có quy tắc múi giờ, có thể cần `OffsetDateTime` hoặc `ZonedDateTime`, nhưng phải lưu/diễn giải zone theo hợp đồng rõ.

### 4.2. Converter cho profile UTC đầy đủ giây

Ví dụ sau cố ý hỗ trợ **một profile hẹp**: `yyyyMMddHHmmssZ`, tức đủ giây và UTC. Đây là profile ứng dụng chọn cho trường `modifyTimestamp` trong môi trường đã kiểm soát; parser không tuyên bố chấp nhận mọi biến thể hợp lệ của RFC 4517.

**`GeneralizedTimeToInstantConverter.java`**

```java
package com.example.ldap.convert;

import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.time.format.ResolverStyle;
import java.util.Locale;

import org.springframework.core.convert.converter.Converter;
import org.springframework.stereotype.Component;

@Component
public class GeneralizedTimeToInstantConverter
        implements Converter<String, Instant> {

    private static final DateTimeFormatter FORMAT =
            DateTimeFormatter.ofPattern(
                    "uuuuMMddHHmmss'Z'", Locale.ROOT)
                    .withResolverStyle(ResolverStyle.STRICT);

    @Override
    public Instant convert(String source) {
        if (source == null) {
            return null;
        }
        try {
            LocalDateTime utc = LocalDateTime.parse(source, FORMAT);
            return utc.toInstant(ZoneOffset.UTC);
        } catch (DateTimeParseException ex) {
            throw new IllegalArgumentException(
                    "Generalized Time không đúng profile UTC giây đầy đủ",
                    ex);
        }
    }
}
```

**`InstantToGeneralizedTimeConverter.java`**

```java
package com.example.ldap.convert;

import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

import org.springframework.core.convert.converter.Converter;
import org.springframework.stereotype.Component;

@Component
public class InstantToGeneralizedTimeConverter
        implements Converter<Instant, String> {

    private static final DateTimeFormatter FORMAT =
            DateTimeFormatter.ofPattern(
                    "uuuuMMddHHmmss'Z'", Locale.ROOT);

    @Override
    public String convert(Instant source) {
        if (source == null) {
            return null;
        }
        LocalDateTime utc = LocalDateTime.ofInstant(
                source, ZoneOffset.UTC);
        return FORMAT.format(utc);
    }
}
```

Hai converter được đăng ký dưới dạng Spring converter bean. Spring LDAP ODM hiện hành sử dụng `ConversionService` để chuyển giữa kiểu Java và giá trị LDAP; khi dùng Spring Boot, các converter bean có thể được ODM configuration nhận. Nếu tự cấu hình `ObjectDirectoryMapper`/`ConversionService` ngoài Boot, cần kết nối converter vào đúng conversion service mà mapper sử dụng.

**Chú ý độ chính xác:** profile trên ghi timestamp đến giây; phần nano giây trong `Instant` bị bỏ khi serialize. Nếu nghiệp vụ cần phần giây thập phân, hãy định nghĩa profile có fraction, parse và ghi chính xác, đồng thời kiểm thử server matching rule. Nếu directory trả offset `+0700` hoặc `-0500`, converter này phải từ chối; hãy dùng parser có hỗ trợ offset thay vì âm thầm diễn giải thành UTC.

### 4.3. Dùng converter trong ODM

Ví dụ một thuộc tính operational do server quản lý:

```java
import java.time.Instant;
import javax.naming.Name;
import org.springframework.ldap.odm.annotations.Attribute;
import org.springframework.ldap.odm.annotations.Entry;
import org.springframework.ldap.odm.annotations.Id;

@Entry(
        objectClasses = {"top", "person", "organizationalPerson", "inetOrgPerson"},
        base = "ou=people"
)
public class TimestampedPerson {

    @Id
    private Name dn;

    @Attribute(name = "uid")
    private String uid;

    @Attribute(
            name = "modifyTimestamp",
            syntax = "1.3.6.1.4.1.1466.115.121.1.24",
            readonly = true
    )
    private Instant modifyTimestamp;

    // getters/setters
}
```

`modifyTimestamp` thường là operational attribute được server quản lý. `readonly=true` giúp ODM biết không nên ghi trường đó như một thuộc tính thông thường. Tên/khả năng trả về operational attribute và ACL phụ thuộc directory server; khi search thủ công, cần **yêu cầu rõ** attribute cần đọc. Không cố tự set `modifyTimestamp` để giả lập thời điểm cập nhật.

### 4.4. Ngày giờ không phải lúc nào cũng Generalized Time

Các directory có thể dùng:

- `Generalized Time` cho timestamp chuẩn LDAP.
- `UTC Time` trong schema cũ hoặc một số thuộc tính chuyên biệt.
- Integer epoch seconds/milliseconds cho schema ứng dụng tự thiết kế.
- Chuỗi local date theo format do tổ chức định nghĩa.

Không đoán kiểu chỉ từ tên thuộc tính có chữ `Date` hoặc `Time`. Kiểm tra schema, tài liệu server và dữ liệu thực trước khi chọn converter.

## 5. Giá trị định danh: uid, DN, entryUUID và objectGUID

Định danh là phần dễ gây lỗi dữ liệu nhất khi đồng bộ giữa LDAP và hệ thống khác. Bốn loại sau có ý nghĩa khác nhau:

| Giá trị | Ví dụ | Đặc tính |
|---|---|---|
| `uid` | `lan` | Thuộc tính tên đăng nhập; uniqueness phụ thuộc schema/chính sách và phạm vi |
| DN | `uid=lan,ou=people,dc=example,dc=org` | Địa chỉ entry trong cây LDAP; thay đổi khi rename/move |
| `entryUUID` | `597ae2f6-16a6-1027-98f4-d28b5365dc14` | Operational UUID server gán theo RFC 4530 nếu server hỗ trợ |
| `objectGUID` | UUID hiển thị dạng chuẩn | GUID 128-bit riêng của Active Directory, được truyền dưới dạng 16 byte |

### 5.1. DN là địa chỉ, không phải khóa bền vững

DN xác định vị trí entry trong namespace hiện tại. Khi entry chuyển OU hoặc đổi RDN, DN thay đổi:

```text
Trước:
  uid=lan,ou=employees,dc=example,dc=org

Sau khi move:
  uid=lan,ou=contractors,dc=example,dc=org
```

Nếu hệ thống ngoài LDAP lưu DN làm khóa liên kết dài hạn, rename/move có thể làm tham chiếu lỗi thời. DN vẫn rất quan trọng để gọi `lookup`/`modifyAttributes` tại directory, nhưng không phải định danh bất biến trong mọi workflow.

### 5.2. entryUUID theo RFC 4530

RFC 4530 định nghĩa `entryUUID` là operational attribute chứa UUID do server gán cho entry. Syntax UUID có OID `1.3.6.1.1.16.1`; attribute type `entryUUID` có OID `1.3.6.1.1.16.4`. Giá trị UUID trên LDAP được mã hóa dưới dạng **chuỗi ASCII theo định dạng UUID canonical**, ví dụ:

```text
597ae2f6-16a6-1027-98f4-d28b5365dc14
```

Không nhầm syntax UUID này với một thuộc tính GUID nhị phân bất kỳ.

Ví dụ đọc:

```java
import java.util.UUID;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;

static UUID readEntryUuid(Attributes attrs) throws Exception {
    Attribute attribute = attrs.get("entryUUID");
    if (attribute == null || attribute.size() != 1) {
        throw new IllegalStateException(
                "entryUUID không có hoặc không đơn trị");
    }
    Object value = attribute.get();
    if (!(value instanceof String text)) {
        throw new IllegalStateException(
                "entryUUID phải được truyền dưới dạng UUID string");
    }
    return UUID.fromString(text);
}
```

`entryUUID` là operational attribute; không phải server nào cũng hỗ trợ RFC 4530. Khi tìm kiếm, client thường cần **yêu cầu rõ attribute** thay vì mặc định nhận mọi operational attribute. Quyền đọc cũng phụ thuộc ACL. Đừng gắn `entryUUID` vào schema của mọi server mà chưa xác nhận hỗ trợ.

### 5.3. objectGUID của Active Directory

Active Directory có `objectGUID`, một GUID 128-bit được server gán cho object. Microsoft mô tả GUID này duy trì khi object được rename/move, trong khi DN thay đổi. Giá trị được lưu/trả ở dạng **octet string 16 byte**, không phải chuỗi UUID ASCII của RFC 4530.

Đọc qua JNDI:

```java
Object raw = attributes.get("objectGUID").get();
if (!(raw instanceof byte[] guidBytes) || guidBytes.length != 16) {
    throw new IllegalStateException("objectGUID phải có 16 byte");
}
```

Trong JNDI, cần bảo đảm provider nhận diện `objectGUID` là binary; có thể cấu hình `java.naming.ldap.attributes.binary` hoặc dùng `@Attribute(type = Attribute.Type.BINARY)` trong Spring LDAP ODM.

**Chú ý endian:** cấu trúc byte của GUID trong Active Directory dùng thứ tự little-endian cho ba trường đầu (`Data1`, `Data2`, `Data3`), còn tám byte cuối giữ thứ tự byte. Vì vậy không thể luôn dùng `ByteBuffer.getLong()` trực tiếp trên 16 byte rồi coi kết quả là `UUID` canonical.

Hàm chuyển đổi ví dụ:

```java
import java.util.UUID;

static UUID fromActiveDirectoryObjectGuid(byte[] bytes) {
    if (bytes == null || bytes.length != 16) {
        throw new IllegalArgumentException(
                "objectGUID phải có đúng 16 byte");
    }

    long mostSignificantBits =
            ((long) (bytes[3] & 0xff) << 56)
          | ((long) (bytes[2] & 0xff) << 48)
          | ((long) (bytes[1] & 0xff) << 40)
          | ((long) (bytes[0] & 0xff) << 32)
          | ((long) (bytes[5] & 0xff) << 24)
          | ((long) (bytes[4] & 0xff) << 16)
          | ((long) (bytes[7] & 0xff) << 8)
          |  (long) (bytes[6] & 0xff);

    long leastSignificantBits = 0L;
    for (int i = 8; i < 16; i++) {
        leastSignificantBits =
                (leastSignificantBits << 8) | (bytes[i] & 0xffL);
    }

    return new UUID(mostSignificantBits, leastSignificantBits);
}
```

Ví dụ kiểm tra byte order:

```java
byte[] adBytes = new byte[] {
        0x33, 0x22, 0x11, 0x00,
        0x55, 0x44,
        0x77, 0x66,
        (byte) 0x88, (byte) 0x99, (byte) 0xaa, (byte) 0xbb,
        (byte) 0xcc, (byte) 0xdd, (byte) 0xee, (byte) 0xff
};

UUID id = fromActiveDirectoryObjectGuid(adBytes);
// 00112233-4455-6677-8899-aabbccddeeff
```

Đây là cách chuyển đổi **đặc thù AD**. Không áp dụng nó cho mọi binary UUID attribute. Với RFC 4530, LDAP wire representation là chuỗi UUID canonical và có thể dùng `UUID.fromString` trực tiếp. Với vendor khác, phải theo tài liệu của schema/backend.

### 5.4. Chọn định danh nào để lưu ở hệ thống ngoài?

| Mục đích | Lựa chọn phù hợp |
|---|---|
| Hiển thị login | `uid` hoặc `userPrincipalName` theo chính sách |
| Thực hiện LDAP operation hiện tại | DN đã xác minh trong đúng directory/base |
| Liên kết lâu dài với entry OpenLDAP có RFC 4530 | `entryUUID` nếu server hỗ trợ |
| Liên kết lâu dài với object AD | `objectGUID` |
| Hợp nhất nhiều directory/tenant | Cặp `directoryId + stableEntryId` |

Không mặc định `uid` là duy nhất toàn forest hoặc giữa các tenant. Cũng không dùng một UUID để xác định endpoint LDAP; cùng một giá trị có thể tồn tại ở hai directory độc lập nếu không có ranh giới source.

## 6. ODM: ánh xạ String, binary, time và identity

Spring LDAP Object-Directory Mapping (ODM) cung cấp:

- `@Entry`: khai báo objectClass của entity.
- `@Id`: giữ DN dưới dạng `javax.naming.Name`.
- `@Attribute`: ánh xạ property Java với LDAP attribute, có thể khai báo tên, syntax, type và readonly.
- `@Transient`: bỏ qua property không được lưu vào LDAP.
- `@DnAttribute`: ánh xạ thành phần RDN vào property String.

Ví dụ entity:

**`EmployeeEntry.java`**

```java
package com.example.ldap;

import java.time.Instant;
import javax.naming.Name;
import org.springframework.ldap.odm.annotations.Attribute;
import org.springframework.ldap.odm.annotations.Entry;
import org.springframework.ldap.odm.annotations.Id;

@Entry(
        base = "ou=employees",
        objectClasses = {
                "top",
                "person",
                "organizationalPerson",
                "inetOrgPerson"
        }
)
public class EmployeeEntry {

    @Id
    private Name dn;

    @Attribute(name = "uid")
    private String uid;

    @Attribute(name = "cn")
    private String displayName;

    @Attribute(name = "modifyTimestamp", readonly = true,
            syntax = "1.3.6.1.4.1.1466.115.121.1.24")
    private Instant modifyTimestamp;

    @Attribute(name = "jpegPhoto",
            type = Attribute.Type.BINARY,
            syntax = "1.3.6.1.4.1.1466.115.121.1.28")
    private byte[] photo;

    // Nếu directory có hỗ trợ RFC 4530:
    @Attribute(name = "entryUUID", readonly = true,
            syntax = "1.3.6.1.1.16.1")
    private String entryUuid;

    public Name getDn() { return dn; }
    public void setDn(Name dn) { this.dn = dn; }
    public String getUid() { return uid; }
    public void setUid(String uid) { this.uid = uid; }
    public String getDisplayName() { return displayName; }
    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }
    public Instant getModifyTimestamp() { return modifyTimestamp; }
    public void setModifyTimestamp(Instant modifyTimestamp) {
        this.modifyTimestamp = modifyTimestamp;
    }
    public byte[] getPhoto() {
        return photo == null ? null : photo.clone();
    }
    public void setPhoto(byte[] photo) {
        this.photo = photo == null ? null : photo.clone();
    }
    public String getEntryUuid() { return entryUuid; }
    public void setEntryUuid(String entryUuid) {
        this.entryUuid = entryUuid;
    }
}
```

Các trường `modifyTimestamp` và `entryUUID` là ví dụ về attribute do directory quản lý; khả năng tồn tại và quyền đọc phụ thuộc server. `jpegPhoto` chỉ hợp lệ nếu objectClass/schema của directory cho phép thuộc tính này. Khi ODM tạo entry mới, các objectClass khai báo trong `@Entry` và schema server phải tương thích.

### 6.1. Converter là một phần của hợp đồng mapping

ODM dùng converter/conversion service để chuyển từ kiểu dữ liệu LDAP sang property Java. Khi không có converter phù hợp, mapping sang `Instant`/kiểu tùy chỉnh có thể thất bại.

Với Spring Boot, đăng ký converter như bean theo cơ chế Spring ConversionService mà ODM sử dụng. Nếu không dùng Boot auto-configuration, cấu hình `ObjectDirectoryMapper`/`ObjectDirectoryMapperConfiguration` và `ConversionService` rõ ràng, rồi gắn mapper vào `LdapTemplate`.

Không tạo một `Converter<String, Instant>` chỉ vì thấy timestamp đang là chuỗi rồi mong mọi bean trong ứng dụng tự dùng converter đó. Cần xác minh **ObjectDirectoryMapper thực sự nhận converter**, và test cả chiều đọc lẫn ghi.

### 6.2. Operational attribute cần đánh dấu readonly

Một số attribute như `entryUUID`, `createTimestamp`, `modifyTimestamp` được server quản lý. Nếu ODM cố ghi chúng trong `update`, server có thể từ chối vì `NO-USER-MODIFICATION` hoặc ACL.

Khi ánh xạ, cân nhắc `@Attribute(readonly = true)`. Với thao tác đọc thủ công, chỉ yêu cầu attribute khi cần; operational attributes không nhất thiết được trả cùng user attributes mặc định. Không coi việc property Java có giá trị là quyền ghi vào directory.

## 7. JNDI: đọc kiểu runtime và xử lý giá trị đúng

`Attributes` là tập attribute; mỗi `Attribute` chứa một hay nhiều giá trị kiểu `Object`. Oracle JNDI LDAP provider thường trả `String` hoặc `byte[]`; không tự tạo `Instant`/`UUID`.

Một hàm đọc một giá trị chuỗi có kiểm tra:

```java
import javax.naming.NamingException;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;

static String requiredString(Attributes attrs, String name)
        throws NamingException {
    Attribute attr = attrs.get(name);
    if (attr == null || attr.size() != 1) {
        throw new IllegalStateException(
                name + " phải tồn tại và đơn trị");
    }
    Object value = attr.get();
    if (!(value instanceof String text)) {
        throw new IllegalStateException(
                name + " không được provider trả về dạng String");
    }
    return text;
}
```

Hàm này phù hợp với thuộc tính nghiệp vụ đã được schema quy định single-valued. Nếu attribute hợp lệ là multi-valued, hãy dùng một hàm đọc danh sách như mục 2.2.

### 7.1. Parse integer và boolean nghiêm ngặt

LDAP Integer syntax biểu diễn số nguyên; JNDI thường đưa về `String`. Nên dùng `BigInteger` nếu schema không giới hạn miền giá trị:

```java
import java.math.BigInteger;

BigInteger employeeNumber =
        new BigInteger(requiredString(attrs, "employeeNumber"));
```

Boolean:

```java
static boolean parseLdapBoolean(String value) {
    if ("TRUE".equalsIgnoreCase(value)) {
        return true;
    }
    if ("FALSE".equalsIgnoreCase(value)) {
        return false;
    }
    throw new IllegalArgumentException(
            "Boolean LDAP không hợp lệ: " + value);
}
```

Không dùng `Boolean.parseBoolean(value)` nếu cần phát hiện dữ liệu sai: phương thức đó trả `false` cho mọi chuỗi không phải `true`, có thể biến dữ liệu lỗi thành giá trị hợp lệ một cách âm thầm.

### 7.2. Đọc byte[] mà không làm mất dữ liệu

```java
static byte[] requiredBinary(Attributes attrs, String name)
        throws Exception {
    Attribute attr = attrs.get(name);
    if (attr == null || attr.size() != 1) {
        throw new IllegalStateException(
                name + " phải tồn tại và đơn trị");
    }
    Object value = attr.get();
    if (!(value instanceof byte[] bytes)) {
        throw new IllegalStateException(
                name + " không được provider trả về byte[]");
    }
    return bytes.clone();
}
```

Không viết:

```java
String corrupted = new String(binaryValue);
```

vì constructor không chỉ định charset dùng charset mặc định và có thể làm mất byte. Nếu schema thực sự là text nhưng provider trả byte[], hãy chọn charset theo syntax/hợp đồng của attribute và kiểm thử encoding. Nếu schema là Octet String/Certificate/JPEG/GUID, giữ nguyên byte sequence và parse theo định dạng tương ứng.

## 8. Kiểm tra schema trước khi ánh xạ

Trước khi thiết kế entity, cần xác nhận:

- Attribute type có tồn tại trong schema không?
- Syntax OID là gì?
- Matching rule equality/ordering/substring là gì?
- Attribute single-valued hay multi-valued?
- Attribute là user attribute hay operational attribute?
- Có `NO-USER-MODIFICATION`/read-only không?
- ObjectClass nào cho phép attribute?
- Tài khoản bind có quyền đọc/ghi không?
- Directory có yêu cầu option `;binary` hay binary provider property không?

Một lệnh kiểm tra schema trên OpenLDAP-compatible server:

```bash
ldapsearch -LLL -H ldaps://ldap.example.org:636 \
  -D "cn=schema-reader,ou=service,dc=example,dc=org" -W \
  -b "" -s base subschemaSubentry
```

Sau đó dùng DN schema được trả về để đọc các định nghĩa `attributeTypes`/`objectClasses` nếu tài khoản được phép:

```bash
ldapsearch -LLL -H ldaps://ldap.example.org:636 \
  -D "cn=schema-reader,ou=service,dc=example,dc=org" -W \
  -b "<DN-do-subSchemaSubentry-tra-ve>" -s base attributeTypes objectClasses
```

`<DN-do-subSchemaSubentry-tra-ve>` là placeholder cần thay bằng giá trị `subschemaSubentry` ở lệnh trước; `cn=Subschema` chỉ là tên thường gặp ở một số directory, không phải DN schema cố định của mọi server. Cú pháp tra cứu schema, quyền truy cập và việc server có công bố schema cho client khác nhau theo sản phẩm.

**Không suy đoán OID từ tên thuộc tính.** Ví dụ `objectGUID` là thuộc tính Active Directory; `entryUUID` theo RFC 4530 có syntax riêng. Hai tên đều liên quan định danh nhưng schema và wire representation khác nhau.

## 9. LDIF cho chuỗi, thời gian và binary

Ví dụ entry text:

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

Một custom schema có thể khai báo thuộc tính thời gian nghiệp vụ `employeeStartTime` với Generalized Time syntax. Ví dụ giá trị:

```ldif
employeeStartTime: 20250308143000Z
```

Attribute custom chỉ hợp lệ sau khi schema server đã khai báo và objectClass cho phép nó. Không thêm một thuộc tính tùy ý vào entry production rồi mong directory tự hiểu syntax.

Binary value trong LDIF dùng dạng Base64 với dấu hai chấm kép:

```text
jpegPhoto:: /9j/4AAQSkZJRgABAQ...
```

Chuỗi Base64 ở đây chỉ minh họa cách biểu diễn; muốn import phải thay bằng toàn bộ Base64 của một file JPEG hợp lệ. Không cắt chuỗi và không coi Base64 là nội dung LDAP thực sau khi import: server lưu byte sequence đã giải mã.

Các operational attributes như `createTimestamp`, `modifyTimestamp` hoặc `entryUUID` thường do server quản lý. Không cố nạp chúng từ LDIF user thông thường nếu server cấm sửa.

## 10. Kiểm thử converter và mapping

### 10.1. Unit test Generalized Time

**`GeneralizedTimeToInstantConverterTest.java`**

```java
package com.example.ldap.convert;

import java.time.Instant;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class GeneralizedTimeToInstantConverterTest {

    private final GeneralizedTimeToInstantConverter converter =
            new GeneralizedTimeToInstantConverter();

    @Test
    void parsesUtcFullSeconds() {
        Instant result = converter.convert("20261126143000Z");
        assertEquals(
                Instant.parse("2026-11-26T14:30:00Z"),
                result);
    }

    @Test
    void rejectsOffsetWhenOnlyUtcProfileIsConfigured() {
        assertThrows(IllegalArgumentException.class,
                () -> converter.convert("20261126143000+0700"));
    }

    @Test
    void rejectsInvalidCalendarDate() {
        assertThrows(IllegalArgumentException.class,
                () -> converter.convert("20260230143000Z"));
    }
}
```

Test này kiểm tra **profile UTC full seconds** của ví dụ. Nếu yêu cầu nhận mọi dạng Generalized Time theo RFC, cần mở rộng converter và bổ sung test cho offset, fraction, leap second và các độ chính xác khác.

### 10.2. Unit test chuyển đổi AD objectGUID

```java
import java.util.UUID;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class ActiveDirectoryGuidTest {
    @Test
    void convertsMixedEndianGuidBytes() {
        byte[] bytes = {
                0x33, 0x22, 0x11, 0x00,
                0x55, 0x44, 0x77, 0x66,
                (byte) 0x88, (byte) 0x99,
                (byte) 0xaa, (byte) 0xbb,
                (byte) 0xcc, (byte) 0xdd,
                (byte) 0xee, (byte) 0xff
        };

        assertEquals(
                UUID.fromString("00112233-4455-6677-8899-aabbccddeeff"),
                fromActiveDirectoryObjectGuid(bytes));
    }
}
```

Test dùng một GUID đã biết để phát hiện lỗi đảo byte. Không thay test này bằng việc chỉ kiểm tra độ dài `byte[]` là 16; độ dài đúng không chứng minh thứ tự byte đúng.

### 10.3. Integration test trên LDAP directory

Chuẩn bị LDAP test directory có schema thật và một entry chứa:

- `uid`/`cn` dạng Directory String.
- `modifyTimestamp` do server tạo, nếu server hỗ trợ và cho phép đọc.
- `jpegPhoto` có payload JPEG nhỏ, hợp lệ.
- `entryUUID` nếu server triển khai RFC 4530; hoặc `objectGUID` nếu chạy Active Directory test.

Các assertion nên bao gồm:

| Test | Kỳ vọng |
|---|---|
| Đọc `cn` có tiếng Việt | Không mất ký tự Unicode |
| Đọc `jpegPhoto` | JNDI/ODM trả `byte[]`, byte length hợp lệ |
| Ghi/đọc lại ảnh | Byte sequence khớp; schema/server chấp nhận JPEG |
| Đọc `modifyTimestamp` | Converter trả đúng `Instant` theo UTC |
| Timestamp có offset không hỗ trợ | Converter báo lỗi rõ, không âm thầm lệch giờ |
| Đọc `entryUUID` | Chuỗi parse thành UUID canonical khi server hỗ trợ |
| Đọc `objectGUID` | 16 byte được chuyển đúng theo AD layout |
| Yêu cầu operational attr không có quyền | Test nhận lỗi/quyền phù hợp, không coi là giá trị null hợp lệ |
| Attribute multi-valued | Tất cả giá trị được đọc, không chỉ một giá trị tùy ý |
| ODM update entity | Không ghi ngược operational attribute readonly |

Integration test phải chạy trên server tương thích với schema/ACL của môi trường mục tiêu. Một embedded LDAP server tối giản có thể không triển khai `entryUUID`, `objectGUID`, custom schema, Generalized Time matching rule hoặc binary behavior giống production.

## 11. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Ép `(String) attr.get()` gây ClassCastException | Provider trả `byte[]` cho binary syntax | Kiểm tra schema và `Attribute.Type.BINARY`/JNDI binary property |
| Ảnh/certificate bị hỏng | Giải mã byte bằng charset hoặc Base64 sai | Giữ nguyên bytes; chỉ Base64 ở ranh giới text/LDIF/API |
| ODM không map `byte[]` đúng | `@Attribute` để mặc định STRING | Đặt `type=Attribute.Type.BINARY` và syntax đúng |
| Timestamp lệch múi giờ | Parse thành local time hoặc dùng timezone mặc định JVM | Parse offset rõ ràng, chuẩn hóa `Instant`/UTC |
| Timestamp bị từ chối | Converter chỉ hỗ trợ UTC full seconds nhưng server trả offset/fraction | Mở rộng parser theo profile thật, không bỏ timezone |
| So sánh timestamp bằng chuỗi sai | Offset hoặc độ chính xác khác nhau | Dùng matching rule LDAP và kiểu thời gian chuẩn |
| `UUID.fromString` báo lỗi | Giá trị không phải UUID canonical string | Kiểm tra syntax/wire format và server |
| AD objectGUID ra UUID khác | Sai endian hoặc coi byte như RFC 4530 UUID | Dùng conversion AD riêng và test byte order |
| Không thấy `entryUUID` | Server không hỗ trợ, ACL hoặc chưa request operational attr | Kiểm tra RFC 4530 support, projection và quyền đọc |
| Update entity bị từ chối | Cố ghi operational attribute | Dùng `readonly=true` hoặc tách read model/write model |
| `Attribute.get()` trả giá trị không mong đợi | Attribute multi-valued, không ordered | Duyệt `getAll()` và xử lý collection |
| Filter equality không giống Java equals | LDAP matching rule khác | Kiểm tra schema/matching rule; không tự suy luận từ Java |
| Binary response quá lớn | Projection rộng hoặc không giới hạn payload | Chỉ request thuộc tính cần thiết, giới hạn kích thước |

## 12. Bảo mật và vận hành

Các thuộc tính nhị phân/thời gian/định danh có thể chứa dữ liệu nhạy cảm:

1. **Không log binary** hoặc certificate content; log kích thước/loại và correlation ID nếu cần.
2. Không trả `userCertificate`, `jpegPhoto` hoặc GUID/SID nội bộ cho API công khai nếu không có nhu cầu.
3. Áp dụng ACL tối thiểu cho operational attributes; không phải mọi tài khoản bind đều cần đọc `entryUUID`/`objectGUID`.
4. Không coi UUID là secret hoặc credential; nó là định danh, vẫn có thể là dữ liệu nhạy cảm khi liên kết hồ sơ.
5. Giới hạn kích thước binary khi upload/download để tránh memory exhaustion.
6. Không dùng timezone mặc định JVM làm timezone LDAP; lưu timestamp chuẩn UTC hoặc offset rõ ràng.
7. Khi đồng bộ định danh, lưu source/directory ID cùng stable ID để tránh collision giữa các directory độc lập.
8. Khi DN thay đổi, cập nhật locator hiện tại nhưng giữ stable ID theo backend nếu nghiệp vụ cần liên kết lâu dài.
9. Không tự sửa schema hoặc converter production chỉ để bỏ qua lỗi mapping; thay đổi schema cần quy trình versioning và compatibility.

**Đừng nhầm stable ID với quyền truy cập.** Biết `entryUUID` hay `objectGUID` không có nghĩa người dùng có quyền đọc hoặc sửa entry. LDAP server vẫn áp dụng authentication, ACL và schema validation cho từng thao tác.

## 13. Câu hỏi tự đánh giá

1. LDAP syntax và matching rule khác nhau ở điểm nào?
2. Vì sao JNDI thường trả `String` hoặc `byte[]` thay vì tự trả `Instant`/`UUID`?
3. Directory String được mã hóa thế nào trên LDAP? Vì sao không ép mọi text sang ASCII?
4. Octet String khác `;binary` option như thế nào?
5. Khi nào cần `@Attribute(type = Attribute.Type.BINARY)`?
6. Generalized Time có timezone ra sao? Vì sao nên chuẩn hóa thời gian thành `Instant`?
7. Converter UTC full seconds trong bài từ chối giá trị `+0700` vì lý do gì?
8. Vì sao `Attribute.get()` không đủ cho attribute đa trị unordered?
9. `entryUUID` theo RFC 4530 được truyền dưới dạng gì và operational attribute có ý nghĩa gì?
10. Vì sao `objectGUID` của Active Directory cần xử lý endian riêng?
11. DN, `uid`, `entryUUID` và `objectGUID` khác nhau thế nào về tính ổn định?
12. Vì sao phải yêu cầu operational attributes rõ ràng và kiểm tra ACL?
13. `@Attribute(readonly=true)` có tác dụng gì khi ánh xạ timestamp/UUID do server quản lý?
14. Một UUID giống nhau ở hai directory độc lập có đủ để làm khóa toàn hệ thống không?
15. Những test nào cần chạy trước khi đổi converter hoặc schema production?

**Ghi nhớ:** schema LDAP quyết định **syntax, matching rule và cardinality**; Java mapping phải tôn trọng hợp đồng đó. Chuỗi thường là `String`, binary là `byte[]`, Generalized Time cần converter có timezone/precision rõ ràng, UUID phải phân biệt **RFC 4530 entryUUID dạng chuỗi** với **AD objectGUID dạng 16 byte**. DN là locator có thể đổi; stable ID chỉ có ý nghĩa trong directory/backend hỗ trợ nó. Hãy khai báo `@Attribute` đúng type/syntax/readonly, đọc đầy đủ giá trị đa trị, giới hạn binary payload và kiểm thử trên LDAP server thực trước khi phát hành.

### Tài liệu tham khảo

- IETF [RFC 4517 — LDAP: Syntaxes and Matching Rules](https://www.rfc-editor.org/rfc/rfc4517): Directory String, Octet String, Generalized Time, syntax OID và matching rules.
- IETF [RFC 4530 — LDAP entryUUID Operational Attribute](https://www.rfc-editor.org/rfc/rfc4530): UUID syntax, `entryUUID`, `uuidMatch` và định danh sau rename.
- IETF [RFC 4512 — LDAP: Directory Information Models](https://www.rfc-editor.org/rfc/rfc4512): schema, attribute types, object classes và operational attributes.
- Spring LDAP Reference — [Object-Directory Mapping](https://docs.spring.io/spring-ldap/reference/odm.html): `@Entry`, `@Id`, `@Attribute`, binary type và custom converters.
- Spring LDAP API — [`Attribute`](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/odm/annotations/Attribute.html) và [`Attribute.Type`](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/odm/annotations/Attribute.Type.html): STRING/BINARY, syntax và readonly.
- Oracle Java — [`javax.naming.directory.Attribute`](https://docs.oracle.com/en/java/javase/17/docs/api/java.naming/javax/naming/directory/Attribute.html): giá trị đơn/đa trị, syntax và schema.
- Oracle JNDI Tutorial — [Attributes](https://docs.oracle.com/javase/jndi/tutorial/ldap/misc/attrs.html): binary attributes, `;binary` và `java.naming.ldap.attributes.binary`.
- Microsoft Learn — [Object Names and Identities](https://learn.microsoft.com/en-us/windows/win32/ad/object-names-and-identities): DN có thể đổi khi rename/move, `objectGUID` ổn định trong vòng đời object.
- Microsoft Learn — [Reading an Object's objectGUID](https://learn.microsoft.com/en-us/windows/win32/ad/reading-an-objectampaposs-objectguid-and-creating-a-string-representation-of-the-guid): `objectGUID` được lưu như octet string và cách tạo biểu diễn GUID.
