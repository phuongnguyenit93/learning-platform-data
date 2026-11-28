# Chuyển đổi thời gian và kiểu dữ liệu theo schema khi ánh xạ kết quả LDAP

## 1. Vì sao cùng một giá trị LDAP có thể cần nhiều kiểu Java?

Trong **Spring Data LDAP**, repository và `LdapTemplate` giúp ứng dụng Java đọc, tìm kiếm và sửa entry của một directory. Mỗi entry có **Distinguished Name (DN)**, các `objectClass` và một tập thuộc tính được định nghĩa bởi **schema LDAP**. Khi Spring LDAP ánh xạ kết quả tìm kiếm sang object Java, ứng dụng phải hiểu **cú pháp thuộc tính (attribute syntax)** chứ không chỉ nhìn nội dung hiển thị từ `ldapsearch`.

Ví dụ một entry có:

~~~text
dn: uid=alice,ou=people,dc=example,dc=org
uid: alice
cn: Alice Nguyen
employeeNumber: 000812
modifyTimestamp: 20261126153045Z
jpegPhoto:: <BASE64_CUA_ANH_MAU>
~~~

Các trường trong Java không nhất thiết cùng kiểu:

| Dữ liệu LDAP | Kiểu nhận ở tầng JNDI thường gặp | Kiểu Java nghiệp vụ có thể phù hợp |
| --- | --- | --- |
| `uid`, `cn` | `String` | `String` |
| `employeeNumber` | `String` | **`String`**, vì giữ số 0 đầu có ý nghĩa |
| `modifyTimestamp` | `String` | `Instant` sau khi parse đúng cú pháp LDAP |
| Thuộc tính integer theo schema | Thường `String` | `long`/`BigInteger` sau khi xác thực phạm vi |
| Thuộc tính boolean theo schema | Thường `String` | `boolean`/`Boolean`, parse **TRUE/FALSE** chặt chẽ |
| `jpegPhoto` | `byte[]` nếu provider nhận biết binary | `byte[]`, không phải text Base64 |
| Thuộc tính kiểu DN | Thường `String` | `javax.naming.Name`/`LdapName` nếu nghiệp vụ cần |
| Thuộc tính đa trị | `Attribute` với nhiều giá trị | `List<T>` hoặc collection tương ứng |

Một lỗi rất thường gặp là coi mọi giá trị giống chữ số đều là `long`, mọi ngày giờ đều là `LocalDateTime`, hoặc mọi trường được hiển thị bằng Base64 đều phải được lưu thành `String`. **Schema và ý nghĩa nghiệp vụ quyết định phép chuyển kiểu đúng.**

Bài này hướng dẫn người học phân biệt **raw LDAP → JNDI `Attributes` → Spring LDAP ODM/Repository → kiểu Java nghiệp vụ**; viết converter thời gian chuẩn, xử lý dữ liệu nhị phân, số, boolean và DN; đồng thời thiết kế test để phát hiện sai múi giờ, mất độ chính xác và mất giá trị đa trị.

## 2. Bản đồ các tầng ánh xạ kết quả

~~~mermaid
flowchart LR
    A["LDAP server: DN, schema, attribute values"] --> B["Search/Lookup qua JNDI"]
    B --> C["Attributes / Attribute"]
    C --> D{"Cách ánh xạ?"}
    D --> E["AttributesMapper hoặc ContextMapper"]
    D --> F["ODM: @Entry, @Attribute, @Id"]
    E --> G["Value Object / DTO Java"]
    F --> G
    G --> H["Ứng dụng: nghiệp vụ, API, kiểm thử"]
~~~

Mỗi tầng có trách nhiệm riêng:

1. **LDAP server** lưu và trả giá trị theo attribute syntax, matching rules, ACL, schema, các `objectClass`.
2. **JNDI LDAP provider** biểu diễn thuộc tính qua `javax.naming.directory.Attributes`; một giá trị thường là `String` hoặc `byte[]`, chưa nhất thiết là `Instant` hay `BigInteger`.
3. **`LdapTemplate` + `AttributesMapper`** cho phép ứng dụng đọc giá trị thô rồi chuyển kiểu theo logic riêng.
4. **Spring LDAP ODM** ánh xạ attribute vào field của entity; `ConversionService`/`Converter` có thể được cấu hình để chuyển qua kiểu Java nghiệp vụ.
5. **Service/API** xác định dữ liệu nào được công khai, giá trị thiếu được hiểu ra sao, múi giờ hiển thị và các quy tắc đặc thù.

> **Điểm quan trọng:** `@Attribute(name="modifyTimestamp")` xác định tên LDAP attribute; bản thân annotation **không** làm mọi chuỗi ngày giờ trở thành `Instant`. Để bảo đảm đúng kiểu, cần có conversion phù hợp hoặc chuyển đổi rõ ràng trong tầng service.

## 3. LDAP schema: tên thuộc tính chưa đủ để hiểu kiểu

Một định nghĩa **attribute type** trong schema LDAP có thể mô tả:

- **OID** và tên của thuộc tính, chẳng hạn `cn`, `uid`, `modifyTimestamp`.
- **SYNTAX OID**: quy tắc biểu diễn/giá trị hợp lệ, ví dụ Boolean, Integer, Generalized Time.
- **EQUALITY**, **ORDERING**, **SUBSTR** matching rules: cách server so sánh các giá trị trong filter.
- Thuộc tính **đơn trị/đa trị**, trạng thái user/operational, có thể sửa hay do server quản lý.
- Những `objectClass` nào cho phép hoặc yêu cầu thuộc tính đó.

Các cú pháp LDAP thông dụng theo RFC 4517:

| LDAP syntax | OID của syntax | Ví dụ thuộc tính/giá trị | Cách đọc trong Java |
| --- | --- | --- | --- |
| Directory String | `1.3.6.1.4.1.1466.115.121.1.15` | `cn: Alice Nguyen` | `String` |
| IA5 String | `1.3.6.1.4.1.1466.115.121.1.26` | Một số thuộc tính văn bản ASCII | `String`, kiểm tra schema/encoding |
| Boolean | `1.3.6.1.4.1.1466.115.121.1.7` | `TRUE`, `FALSE` | Parse có xác thực |
| Integer | `1.3.6.1.4.1.1466.115.121.1.27` | `42`, `-12` | `BigInteger` hoặc số có kiểm tra overflow |
| Generalized Time | `1.3.6.1.4.1.1466.115.121.1.24` | `20261126153045Z` | `Instant` sau khi parse |
| Distinguished Name | `1.3.6.1.4.1.1466.115.121.1.12` | `uid=alice,ou=people,...` | `Name`/`LdapName` |
| Octet String | `1.3.6.1.4.1.1466.115.121.1.40` | Dữ liệu byte | `byte[]` |

Không được chỉ dựa vào **tên** để suy rằng một thuộc tính luôn có cùng syntax trên mọi directory. Active Directory, OpenLDAP và directory vendor khác có thể định nghĩa kiểu và thuộc tính mở rộng riêng. Đặc biệt, các thuộc tính có chữ `time`, `date`, `expire` trong tên **không nhất thiết dùng Generalized Time**.

### 3.1. Kiểm tra schema và raw response

Khi có quyền, có thể hỏi LDAP server về `subschemaSubentry`, rồi đọc các định nghĩa `attributeTypes` hoặc tra tài liệu schema chính thức của vendor. Khả năng đọc subschema phụ thuộc ACL/server.

Ví dụ để **quan sát giá trị thuộc tính** tại một DN đã biết:

~~~bash
ldapsearch -LLL -x \
  -H ldaps://ldap.example.org:636 \
  -D "uid=app-reader,ou=service-accounts,dc=example,dc=org" -W \
  -b "uid=alice,ou=people,dc=example,dc=org" -s base \
  "(objectClass=*)" dn uid cn employeeNumber modifyTimestamp
~~~

`-W` yêu cầu nhập mật khẩu, tránh lộ trực tiếp ở command line. LDAP server phải được xác minh TLS/CA/hostname trước khi tin cậy kết quả. Dữ liệu trả về có thể bị giới hạn bởi ACL hoặc attribute selection.

**`modifyTimestamp` là thuộc tính operational** thường được server quản lý và không nhất thiết xuất hiện khi client chỉ yêu cầu `*`. Với OpenLDAP client có thể xin `+` hoặc nêu rõ tên operational attribute. Nếu giá trị không được trả về, không thể kết luận ngay “entry chưa từng được sửa”.

## 4. Chuyển `GeneralizedTime` thành `Instant`

### 4.1. Phân biệt thời điểm với giờ địa phương

Theo RFC 4517, cú pháp LDAP **Generalized Time** có thể chứa thành phần giờ, phút, giây, phần thập phân và timezone. Các biểu diễn thường gặp:

~~~text
20261126153045Z           -> 2026-11-26 15:30:45 UTC
20261126153045.125Z       -> 2026-11-26 15:30:45.125 UTC
20261126223045+0700       -> 2026-11-26 22:30:45 UTC+07:00
~~~

Cả dòng thứ nhất và thứ ba biểu diễn **cùng một thời điểm**.

`java.time.Instant` là lựa chọn tốt cho:

- Thời điểm entry được tạo hoặc sửa (`createTimestamp`, `modifyTimestamp`).
- Thời điểm diễn ra sự kiện, khi thông số LDAP thực sự lưu **một timestamp**.
- So sánh thời điểm tuyệt đối giữa các server ở các múi giờ khác nhau.

`LocalDateTime` **không mang thông tin timezone/offset**, nên không phải lựa chọn thích hợp làm kiểu chuẩn cho một timestamp LDAP có timezone. Nếu người dùng cần xem giờ Việt Nam, chuyển **lúc hiển thị**:

~~~java
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZonedDateTime;

Instant modifiedAt = Instant.parse("2026-11-26T15:30:45Z");

ZonedDateTime localDisplay =
    modifiedAt.atZone(ZoneId.of("Asia/Ho_Chi_Minh"));

// Hiển thị: 2026-11-26T22:30:45+07:00[Asia/Ho_Chi_Minh]
~~~

Không dùng múi giờ mặc định của máy chủ để đoán timezone khi dữ liệu LDAP đã chứa `Z` hoặc `+0700`. Một lần triển khai ở vùng khác không được làm thay đổi **Instant** đại diện cho cùng timestamp.

### 4.2. Vì sao không gọi trực tiếp `Instant.parse`?

`Instant.parse` xử lý các định dạng ISO-8601 như `2026-11-26T15:30:45Z`, **không** xử lý trực tiếp dạng LDAP thông dụng `20261126153045Z`.

Sai:

~~~java
// Không phải định dạng mà Instant.parse nhận trực tiếp.
Instant instant = Instant.parse("20261126153045Z");
~~~

Cách đúng là parse bằng `DateTimeFormatter` theo cú pháp nguồn, rồi đổi sang `Instant`.

### 4.3. Bộ chuyển đổi Java cho dạng Generalized Time thường gặp

Ví dụ sau nhận các giá trị có **đủ giờ-phút-giây**, timezone `Z` hoặc offset `+HHMM`/`-HHMM`, và phần thập phân của **giây** dùng dấu chấm. Đây là một **tập con được xác định rõ** của RFC 4517, phù hợp với nhiều directory thông thường.

~~~java
import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeFormatterBuilder;
import java.time.format.ResolverStyle;
import java.time.temporal.ChronoField;
import java.util.Locale;

public final class LdapGeneralizedTime {

    private LdapGeneralizedTime() {}

    private static final DateTimeFormatter INPUT =
        new DateTimeFormatterBuilder()
            .appendPattern("uuuuMMddHHmmss")
            .optionalStart()
            .appendFraction(ChronoField.NANO_OF_SECOND, 1, 9, true)
            .optionalEnd()
            .appendOffset("+HHMM", "Z")
            .toFormatter(Locale.ROOT)
            .withResolverStyle(ResolverStyle.STRICT);

    private static final DateTimeFormatter OUTPUT =
        new DateTimeFormatterBuilder()
            .appendPattern("uuuuMMddHHmmss")
            .appendFraction(ChronoField.NANO_OF_SECOND, 0, 9, true)
            .appendLiteral('Z')
            .toFormatter(Locale.ROOT)
            .withZone(ZoneOffset.UTC);

    public static Instant parseCommon(String ldapValue) {
        if (ldapValue == null || ldapValue.isBlank()) {
            throw new IllegalArgumentException("Thiếu GeneralizedTime");
        }

        return OffsetDateTime.parse(ldapValue, INPUT).toInstant();
    }

    public static String formatUtc(Instant instant) {
        if (instant == null) {
            throw new IllegalArgumentException("Thiếu Instant");
        }
        return OUTPUT.format(instant);
    }
}
~~~

Ví dụ:

~~~java
Instant a = LdapGeneralizedTime.parseCommon("20261126153045Z");
Instant b = LdapGeneralizedTime.parseCommon("20261126223045+0700");

assert a.equals(b);
assert "20261126153045Z".equals(
    LdapGeneralizedTime.formatUtc(a)
);
~~~

**Giới hạn cố ý của parser:**

- RFC 4517 cho phép một số biến thể như **không có giây**, có phần thập phân áp dụng cho đơn vị thời gian cuối, dấu phẩy làm dấu thập phân, offset chỉ giờ và leap second. Parser trên **không tuyên bố hỗ trợ tất cả**.
- Bộ kiểm thử production phải kiểm kê các giá trị thực từ directory đang dùng. Nếu server trả biến thể khác, mở rộng parser theo **đặc tả/schema**, không tự thêm `replace` mơ hồ.
- Với thời điểm có **leap second `60`**, API `java.time` cần chính sách xử lý riêng; không silently thay `60` thành `59`.
- Khi dữ liệu có độ chính xác lớn hơn nanosecond, phải xác định quy tắc giữ/truncate/round; ví dụ trên nhận tối đa 9 chữ số sau dấu chấm.
- Nên dùng UTC cho **giá trị ghi ra** khi schema cho phép; thời điểm hiển thị địa phương là trách nhiệm của UI.

### 4.4. Thuộc tính operational: không được tự ghi

`createTimestamp` và `modifyTimestamp` thuộc nhóm thuộc tính **do server quản lý** trong nhiều directory. Chúng thường được đọc để hiển thị/audit hoặc chẩn đoán, **không** phải trường mà ứng dụng tùy ý `save` lại.

Nếu một entry không trả `modifyTimestamp`, các khả năng gồm: không yêu cầu operational attribute, ACL không cho đọc, directory không hỗ trợ, hoặc cách mô hình hóa khác. Đừng tự sinh giá trị rồi ghi vào LDAP chỉ để object Java không còn `null`.

## 5. Đọc dữ liệu thô bằng `LdapTemplate` trước khi ánh xạ

Khi một thời gian hoặc kiểu số bị sai, cách nhanh nhất để khoanh vùng là dùng `AttributesMapper` lấy raw value, không đi qua ODM.

Giả sử `ContextSource.base = dc=example,dc=org`:

~~~java
import javax.naming.Name;
import javax.naming.directory.Attribute;
import javax.naming.ldap.LdapName;

import org.springframework.ldap.core.LdapTemplate;

public final class EntryTypeInspector {

    private final LdapTemplate ldapTemplate;

    public EntryTypeInspector(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public record RawInfo(
        String modifiedValue,
        String numberValue,
        String photoJavaType
    ) {}

    public RawInfo inspectAlice() throws Exception {
        Name dn = new LdapName("uid=alice,ou=people");

        return ldapTemplate.lookup(
            dn,
            new String[] {
                "modifyTimestamp", "employeeNumber", "jpegPhoto"
            },
            attrs -> {
                String modified = readText(attrs.get("modifyTimestamp"));
                String number = readText(attrs.get("employeeNumber"));

                Attribute photo = attrs.get("jpegPhoto");
                Object photoValue =
                    photo == null || photo.size() == 0
                        ? null
                        : photo.get();

                String photoType =
                    photoValue == null ? null
                        : photoValue.getClass().getName();

                return new RawInfo(modified, number, photoType);
            }
        );
    }

    private static String readText(Attribute attribute)
            throws javax.naming.NamingException {

        if (attribute == null || attribute.size() == 0) {
            return null;
        }

        Object value = attribute.get();
        if (!(value instanceof String stringValue)) {
            throw new IllegalStateException(
                "Thuộc tính không phải String: "
                + value.getClass().getName()
            );
        }
        return stringValue;
    }
}
~~~

Kết quả minh họa:

~~~text
RawInfo[
  modifiedValue=20261126153045Z,
  numberValue=000812,
  photoJavaType=[B
]
~~~

Tên Java runtime `[B` nghĩa là `byte[]`. Không đọc/log bytes ảnh hay token bí mật khi chỉ muốn kiểm tra type.

**Điều cần chú ý:** `attrs.get("modifyTimestamp")==null` chỉ cho biết thuộc tính **không có trong phản hồi này**; không đủ để khẳng định entry không có thời gian sửa. Nếu raw value đã đúng mà entity ODM sai, chuyển sang kiểm tra annotation và converter.

### 5.1. Khi cần ngữ cảnh DN của từng SearchResult

`AttributesMapper` tập trung vào attribute; nếu cần **DN của entry** để chuyển đổi, đối soát hoặc hiển thị, dùng `ContextMapper` phù hợp hoặc `DirContextAdapter` do Spring LDAP cung cấp.

DN không phải `Attribute` như `uid` hay `cn`; đừng tìm `attrs.get("dn")` rồi coi `null` là lỗi schema. Với `@Id` của ODM, DN được ánh xạ sang trường kiểu **`javax.naming.Name`**, không phải trường text bất kỳ.

## 6. ODM và `ConversionService`: map từ raw LDAP sang entity

### 6.1. Một entity ánh xạ kiểu thô an toàn

Trong Spring LDAP ODM, entity cần `@Entry` và `@Id` của package `org.springframework.ldap.odm.annotations`.

~~~java
import java.time.Instant;
import javax.naming.Name;

import org.springframework.ldap.odm.annotations.Attribute;
import org.springframework.ldap.odm.annotations.Entry;
import org.springframework.ldap.odm.annotations.Id;
import org.springframework.ldap.odm.annotations.Transient;

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
    private String fullName;

    // Có thể chứa số 0 đầu, nên giữ dạng String.
    @Attribute(name = "employeeNumber")
    private String employeeNumber;

    // Operational attribute thường được server quản lý.
    @Attribute(name = "modifyTimestamp", readonly = true)
    private String modifiedAtRaw;

    @Attribute(name = "jpegPhoto", type = Attribute.Type.BINARY)
    private byte[] photo;

    @Transient
    private String displayLabel;

    public PersonEntry() {}

    public Name getDn() { return dn; }
    public void setDn(Name value) { dn = value; }

    public String getUid() { return uid; }
    public void setUid(String value) { uid = value; }

    public String getFullName() { return fullName; }
    public void setFullName(String value) { fullName = value; }

    public String getEmployeeNumber() { return employeeNumber; }
    public void setEmployeeNumber(String value) {
        employeeNumber = value;
    }

    public String getModifiedAtRaw() { return modifiedAtRaw; }
    public void setModifiedAtRaw(String value) {
        modifiedAtRaw = value;
    }

    public byte[] getPhoto() { return photo; }
    public void setPhoto(byte[] value) { photo = value; }

    public Instant getModifiedAtForDisplay() {
        return modifiedAtRaw == null
            ? null
            : LdapGeneralizedTime.parseCommon(modifiedAtRaw);
    }
}
~~~

Trong ví dụ, `getModifiedAtForDisplay()` tính `Instant` từ chuỗi raw khi đọc; nó không có field ODM riêng phải ghi vào directory.

Ý nghĩa:

- `@Entry` ánh xạ entry theo `objectClass` và base.
- `@Id Name dn` chứa DN (thường tương đối với base đã cấu hình).
- `@Attribute(name="cn")` ánh xạ property Java `fullName` từ `cn` của LDAP.
- `@Attribute(name="modifyTimestamp", readonly=true)` nêu rõ field không nên được ghi trả trong update ODM.
- `@Attribute(type=Attribute.Type.BINARY)` cho biết `jpegPhoto` là binary, không phải `String`.
- `@Transient` bỏ qua field `displayLabel` dành riêng cho giao diện, không ghi nó trở lại directory.

**Không nên thiết kế `modifiedAtForDisplay` là một field ODM được ghi** vì việc hiển thị theo múi giờ địa phương không phải thuộc tính mới trong directory.

**Cảnh báo:** Các thuộc tính operational có thể không được trả về trong một số đường query ODM, ngay cả khi `@Attribute` đúng. Khi cần timestamp để đối soát, chủ động yêu cầu `modifyTimestamp` bằng `LdapTemplate.lookup` hoặc `SearchControls` và kiểm tra ACL.

### 6.2. Converter để ánh xạ trực tiếp `String` sang `Instant`

Spring LDAP ODM hỗ trợ **Spring `ConversionService`**. Trong các phiên bản Spring Boot có tích hợp `ObjectDirectoryMapper`, các bean `Converter` được công bố trong ApplicationContext có thể được sử dụng để chuyển kiểu khi mapping.

Ví dụ một converter cho các field mà schema thực sự dùng **GeneralizedTime dạng thường gặp**:

~~~java
import java.time.Instant;

import org.springframework.core.convert.converter.Converter;
import org.springframework.stereotype.Component;

@Component
public final class GeneralizedTimeToInstant
        implements Converter<String, Instant> {

    @Override
    public Instant convert(String source) {
        return LdapGeneralizedTime.parseCommon(source);
    }
}
~~~

Entity có thể khai báo:

~~~java
@Attribute(name = "whenCreated", readonly = true)
private Instant createdAt;
~~~

**Điều kiện sử dụng đúng:**

1. Đã xác minh `whenCreated` có **GeneralizedTime** theo schema directory (hoặc tương đương vendor).
2. `ObjectDirectoryMapper` đang sử dụng `ConversionService` có converter này; cấu hình Spring Boot/custom `LdapTemplate` phải được kiểm tra bằng integration test.
3. Query thực sự **yêu cầu/trả về** attribute; converter không thể tạo giá trị cho một attribute bị ACL ẩn.
4. `Converter<String, Instant>` thường tác động đến mọi mapping `String → Instant` trong cùng conversion service. Nếu cùng ứng dụng có attribute `accountExpires` của Active Directory ở dạng FILETIME, **không thể dùng chung** parser này cho cả hai.

Đối với chương trình cần ghi một thuộc tính GeneralizedTime do **ứng dụng sở hữu** (không phải operational timestamp), có thể cần converter ngược:

~~~java
import java.time.Instant;

import org.springframework.core.convert.converter.Converter;

public final class InstantToGeneralizedTime
        implements Converter<Instant, String> {

    @Override
    public String convert(Instant source) {
        return LdapGeneralizedTime.formatUtc(source);
    }
}
~~~

Chỉ đăng ký chiều ghi khi nghiệp vụ và schema cho phép update thuộc tính đó. Việc vô tình đăng ký converter không có nghĩa `modifyTimestamp` trở thành thuộc tính có thể sửa.

### 6.3. Nếu không dùng Spring Boot auto-configuration

Có thể cấu hình một `ObjectDirectoryMapper` được tích hợp conversion service và gắn nó vào `LdapTemplate` bằng `setObjectDirectoryMapper(...)`. Spring LDAP cung cấp cấu hình liên quan như `ObjectDirectoryMapperConfiguration`; chi tiết bean phụ thuộc phiên bản.

Điểm cần tránh: chỉ tạo một `ConversionService` bean **không đảm bảo** một `LdapTemplate` **tự xây dựng** bằng `new LdapTemplate(contextSource)` đã sử dụng nó. Phải kết nối đúng mapper và test bằng một entry có attribute thực.

**Lựa chọn đơn giản hơn:** lưu giá trị raw thành `String` trong entity và chuyển sang `Instant` ở service. Cách này ít rủi ro khi cùng directory có **nhiều định dạng thời gian khác nhau** hoặc một phần giá trị là vendor-specific.

## 7. Integer, Boolean và string mang chữ số: không chuyển kiểu theo cảm tính

### 7.1. Phân biệt số nguyên thật với mã nghiệp vụ

Giả sử:

~~~text
employeeNumber: 000812
loginFailureCount: 12
~~~

- `employeeNumber` có thể là **mã nhân viên**. Chuyển sang `int` sẽ làm mất các số 0 đầu và có thể phá định danh.
- `loginFailureCount` nếu schema xác định là Integer, có thể chuyển thành kiểu số, nhưng còn phải xét giới hạn và ý nghĩa của `null`/`0`.

Chuyển một LDAP integer raw string:

~~~java
import java.math.BigInteger;

public final class LdapNumbers {
    public static BigInteger integerValue(String raw) {
        if (raw == null || !raw.matches("-?(0|[1-9][0-9]*)")) {
            throw new IllegalArgumentException("Không phải LDAP integer hợp lệ");
        }
        return new BigInteger(raw);
    }

    public static long longValueExact(String raw) {
        return integerValue(raw).longValueExact();
    }
}
~~~

Dùng `longValueExact()` để ném lỗi khi giá trị vượt phạm vi `long`, không dùng `longValue()` mà không kiểm tra vì có thể **overflow/truncate**.

**Lưu ý:** Matcher trên cố ý chấp nhận biểu diễn số nguyên thập phân có dạng canonical đơn giản. Nếu directory/vendor hỗ trợ biến thể cú pháp khác, cần kiểm tra theo schema của thuộc tính. `BigInteger` chỉ giúp chứa giá trị lớn, không chứng minh giá trị có ý nghĩa nghiệp vụ.

### 7.2. Parse boolean theo cú pháp LDAP

LDAP Boolean thông thường dùng biểu diễn chữ **`TRUE`** hoặc **`FALSE`** (theo schema/matching rules). Không nên dùng `Boolean.parseBoolean(raw)` khi cần phát hiện dữ liệu không hợp lệ, vì Java sẽ trả `false` cho nhiều chuỗi không nhận ra, làm mất phân biệt giữa **FALSE** và **đọc lỗi**.

~~~java
public static boolean ldapBoolean(String raw) {
    if ("TRUE".equals(raw)) {
        return true;
    }
    if ("FALSE".equals(raw)) {
        return false;
    }
    throw new IllegalArgumentException(
        "Giá trị LDAP Boolean không hợp lệ: " + raw
    );
}
~~~

Nếu một vendor biểu diễn trạng thái bằng `0/1`, bitmask hoặc thuộc tính riêng, **đó không phải tự động là LDAP Boolean syntax**. Phải đọc định nghĩa thuộc tính cụ thể trước khi viết converter.

### 7.3. Giá trị thiếu không đồng nghĩa giá trị mặc định

Khi `attrs.get("loginFailureCount") == null`, ứng dụng không nên mặc định trả `0` nếu ý nghĩa nghiệp vụ phân biệt **không được cấp quyền đọc**, **không tồn tại** và **giá trị bằng 0**.

Tùy API, có thể dùng:

~~~java
import java.math.BigInteger;
import java.util.Optional;

public static Optional<BigInteger> optionalInteger(String raw) {
    return raw == null
        ? Optional.empty()
        : Optional.of(LdapNumbers.integerValue(raw));
}
~~~

Nếu giá trị không được trả về vì ACL, `Optional.empty()` chỉ mô tả **vắng mặt trong dữ liệu đã nhận**, không khẳng định thuộc tính không tồn tại ở server.

## 8. Kiểu DN và dữ liệu đa trị

### 8.1. DN là kiểu phân cấp, không phải một chuỗi bất kỳ

Thuộc tính như `member` hoặc `uniqueMember` trong một nhóm có thể chứa DN đầy đủ:

~~~ldif
dn: cn=reviewers,ou=groups,dc=example,dc=org
objectClass: top
objectClass: groupOfUniqueNames
cn: reviewers
uniqueMember: uid=alice,ou=people,dc=example,dc=org
uniqueMember: uid=bob,ou=people,dc=example,dc=org
~~~

Khi cần thao tác cấu trúc DN, parse bằng `LdapName`:

~~~java
import javax.naming.InvalidNameException;
import javax.naming.Name;
import javax.naming.ldap.LdapName;

public static Name parseDn(String raw)
        throws InvalidNameException {

    return new LdapName(raw);
}
~~~

DN có nhiều ký tự đặc biệt và quy tắc escape theo RFC 4514. Không dùng `split(",")` để lấy thành phần DN hoặc so sánh hai DN như chuỗi chưa chuẩn hóa.

**Phân biệt** DN dùng trong thuộc tính `uniqueMember` với `@Id Name dn` của entry nhóm. `@Id` xác định **entry đang đọc**, còn `uniqueMember` là một **thuộc tính chứa DN tham chiếu**.

### 8.2. Thuộc tính đa trị phải đọc đủ các giá trị

JNDI `Attribute.get()` thường chỉ trả **một** giá trị. Nếu attribute có nhiều giá trị, cần lặp:

~~~java
import java.util.ArrayList;
import java.util.List;
import javax.naming.directory.Attribute;
import javax.naming.ldap.LdapName;
import javax.naming.Name;

public static List<Name> readMemberDns(Attribute attr)
        throws Exception {

    List<Name> result = new ArrayList<>();
    if (attr == null) {
        return result;
    }

    for (int i = 0; i < attr.size(); i++) {
        Object raw = attr.get(i);
        if (!(raw instanceof String dn)) {
            throw new IllegalStateException("Member DN không phải String");
        }
        result.add(new LdapName(dn));
    }
    return result;
}
~~~

LDAP không bảo đảm thứ tự của giá trị **thuộc tính đa trị** như một danh sách có thứ tự nghiệp vụ. Nếu ứng dụng cần hiển thị theo tên, nên sắp xếp rõ trong tầng service/UI. Đừng coi `attr.get(0)` là “thành viên đầu tiên có ưu tiên cao nhất”.

Nếu schema định nghĩa thuộc tính **đơn trị**, không nên map nó thành một tập tùy ý rồi ghi nhiều giá trị; server có thể từ chối với lỗi schema.

## 9. Dữ liệu nhị phân và thuộc tính tùy biến

Một số thuộc tính, ví dụ `jpegPhoto`, `userCertificate`, hoặc thuộc tính doanh nghiệp chứa blob, không phải text. `ldapsearch` thường hiển thị giá trị nhị phân theo LDIF Base64, ký hiệu `::`:

~~~ldif
jpegPhoto:: <BASE64_DU_LIEU_ANH_GIA_TRONG_TEST>
~~~

Đó là **cách biểu diễn văn bản của LDIF**, không có nghĩa giá trị JNDI nên là `String` chứa Base64.

Trong Spring LDAP ODM có thể dùng:

~~~java
@Attribute(
    name = "jpegPhoto",
    type = Attribute.Type.BINARY
)
private byte[] photo;
~~~

JNDI LDAP provider có cấu hình attribute binary riêng nếu nó không tự nhận biết một thuộc tính tùy biến:

~~~text
java.naming.ldap.attributes.binary
~~~

Tùy `ContextSource` và version JDK/Spring LDAP, cần đưa thuộc tính đó vào environment property của provider, rồi kiểm tra `attrs.get("...").get().getClass()` trả `byte[]`.

Một số server trả tên thuộc tính kèm **option** như `userCertificate;binary`. Nếu `attrs.get("userCertificate")` là `null`, hãy liệt kê attribute IDs thực trả về trước khi kết luận mất dữ liệu.

**Không tự decode dữ liệu DER/certificate thành `String` với UTF-8**. Nếu nghiệp vụ cần `X509Certificate`, dùng API X.509 phù hợp sau khi lấy raw `byte[]`; việc parse được certificate **không chứng minh** certificate đáng tin cậy.

## 10. Active Directory: `accountExpires` không phải GeneralizedTime

Đây là một trong những bẫy chuyển đổi phổ biến nhất khi cùng một ứng dụng tích hợp nhiều directory.

Với **Microsoft Active Directory**, thuộc tính `accountExpires` thường là một giá trị số 64-bit kiểu Windows FILETIME: **số khoảng 100 nanosecond kể từ `1601-01-01T00:00:00Z`**, không phải chuỗi `yyyyMMddHHmmssZ`.

Theo Microsoft, hai giá trị **không hết hạn** của `accountExpires` có thể là:

~~~text
0
9223372036854775807
~~~

Nếu gọi `LdapGeneralizedTime.parseCommon(...)` cho các giá trị này, kết quả sai định dạng. Nếu mặc định xem `0` là `Instant.EPOCH`, ứng dụng có thể nhầm tài khoản “không hết hạn” thành đã hết hạn từ 1970.

### 10.1. Converter có xử lý sentinel

~~~java
import java.math.BigInteger;
import java.time.Instant;
import java.util.Optional;

public final class ActiveDirectoryTimes {

    private static final BigInteger TICKS_PER_SECOND =
        BigInteger.valueOf(10_000_000L);

    private static final BigInteger UNIX_EPOCH_OFFSET_SECONDS =
        BigInteger.valueOf(11_644_473_600L);

    private static final BigInteger NEVER_EXPIRES =
        BigInteger.valueOf(Long.MAX_VALUE);

    private ActiveDirectoryTimes() {}

    public static Optional<Instant> accountExpires(String raw) {
        BigInteger fileTimeTicks = new BigInteger(raw);

        if (fileTimeTicks.signum() == 0
                || fileTimeTicks.equals(NEVER_EXPIRES)) {
            return Optional.empty(); // Không có ngày hết hạn
        }
        if (fileTimeTicks.signum() < 0) {
            throw new IllegalArgumentException(
                "accountExpires âm, cần kiểm tra directory"
            );
        }

        BigInteger[] split =
            fileTimeTicks.divideAndRemainder(TICKS_PER_SECOND);

        long unixSeconds = split[0]
            .subtract(UNIX_EPOCH_OFFSET_SECONDS)
            .longValueExact();

        long nanos = split[1].longValueExact() * 100L;

        return Optional.of(
            Instant.ofEpochSecond(unixSeconds, nanos)
        );
    }
}
~~~

Giải thích:

- Một giây có **10.000.000** đơn vị 100 ns.
- Khoảng cách từ epoch 1601 tới epoch Unix 1970 là **11.644.473.600 giây**.
- `BigInteger` giữ nguyên độ chính xác của số nguyên lớn khi parse.
- `divideAndRemainder` giữ được phần lẻ giây, tránh làm tròn bằng `double`.
- `Optional.empty()` trong ví dụ mang ý nghĩa **không có thời điểm hết hạn** của thuộc tính này, không phải “đọc dữ liệu lỗi”.

**Không áp dụng máy móc hai sentinel trên cho tất cả thuộc tính thời gian AD.** Ví dụ `pwdLastSet`, `lastLogonTimestamp` hay `lockoutTime` có ý nghĩa nghiệp vụ, cơ chế replication và giá trị đặc biệt **riêng**. Chúng có thể dùng cùng đơn vị FILETIME nhưng quy tắc xử lý trạng thái không giống `accountExpires`.

### 10.2. Cách trình bày trạng thái tài khoản

Với một hệ thống quản lý tài khoản, nên tách rõ:

~~~java
import java.time.Instant;
import java.util.Optional;

public record AccountExpiry(
    boolean neverExpires,
    Optional<Instant> expiresAt
) {}
~~~

Không dùng một giá trị `LocalDateTime.MIN` hoặc `1970-01-01` để đại diện cho “không bao giờ hết hạn” nếu API có thể biểu đạt điều này trực tiếp. Trạng thái *disabled*, *locked*, *expired* là những khái niệm khác nhau và không thể kết luận chỉ từ `accountExpires`.

## 11. Hướng xây dựng lớp chuyển đổi dùng chung mà không nhầm schema

Một thiết kế thường dùng là tách:

~~~text
Directory adapter
  |-- raw LDAP reading: AttributesMapper / ODM entity
  |-- syntax-aware converters:
  |     |-- GeneralizedTime -> Instant
  |     |-- LDAP Integer -> BigInteger
  |     |-- LDAP Boolean -> boolean
  |     |-- DN syntax -> Name
  |     |-- Binary syntax -> byte[]
  |     +-- AD accountExpires -> Optional<Instant>
  +-- application DTO: dữ liệu đã chuẩn hóa, có policy rõ ràng
~~~

Bảng chọn converter:

| Tình huống | Lựa chọn khuyến nghị | Tránh |
| --- | --- | --- |
| `modifyTimestamp` theo LDAP GeneralizedTime | Parse rõ ràng thành `Instant` | `Instant.parse(raw)` trực tiếp; dùng timezone JVM |
| `employeeNumber` | Giữ `String` nếu là mã | Bỏ số 0 đầu bằng `parseInt` |
| LDAP Integer lớn | `BigInteger`, rồi ép phạm vi bằng `longValueExact` | `double` hoặc cast không kiểm tra |
| LDAP Boolean | Parse chặt `TRUE`/`FALSE` | `Boolean.parseBoolean("INVALID")` thành false |
| DN ở `member` | `LdapName` sau khi validate | `split(",")` hoặc tự nối DN |
| `jpegPhoto`/certificate | `byte[]` rồi xử lý chuyên dụng | `new String(bytes)` |
| Giá trị `accountExpires` AD | Converter FILETIME + sentinel cụ thể | Nhầm với GeneralizedTime |
| Thuộc tính đa trị | Lặp toàn bộ `Attribute` values | Chỉ dùng `Attribute.get()` |
| Attribute không có trong response | Ghi nhận vắng mặt/chưa được trả | Tự cho là `false`, `0` hoặc giá trị rỗng |

Nếu nhiều directory có cùng attribute name nhưng **khác schema**, định nghĩa các adapter theo từng loại directory, không dùng một converter toàn cục không nhận biết nguồn dữ liệu.

## 12. Kiểm thử chuyển đổi trên directory và dữ liệu biên

### 12.1. Unit test parser thời gian

Ví dụ JUnit 5 và AssertJ:

~~~java
import java.time.Instant;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class LdapGeneralizedTimeTest {

    @Test
    void parsesUtcAndOffsetToSameInstant() {
        Instant utc =
            LdapGeneralizedTime.parseCommon("20261126153045Z");
        Instant plusSeven =
            LdapGeneralizedTime.parseCommon("20261126223045+0700");

        assertThat(utc).isEqualTo(plusSeven);
        assertThat(utc)
            .isEqualTo(Instant.parse("2026-11-26T15:30:45Z"));
    }

    @Test
    void keepsFractionalSeconds() {
        Instant instant = LdapGeneralizedTime.parseCommon(
            "20261126153045.125Z"
        );

        assertThat(instant)
            .isEqualTo(Instant.parse("2026-11-26T15:30:45.125Z"));
    }

    @Test
    void rejectsInvalidCalendarDate() {
        assertThatThrownBy(
            () -> LdapGeneralizedTime.parseCommon(
                "20260230153045Z"
            )
        ).isInstanceOf(RuntimeException.class);
    }

    @Test
    void formatsUtcWithoutUsingMachineTimezone() {
        Instant at = Instant.parse("2026-11-26T15:30:45Z");

        assertThat(LdapGeneralizedTime.formatUtc(at))
            .isEqualTo("20261126153045Z");
    }
}
~~~

Bộ test cần thêm trường hợp dữ liệu từ directory thực tế có các biến thể RFC 4517 ngoài tập con được hỗ trợ: timezone không đủ phút, phần thập phân không phải giây, dấu phẩy, leap second. **Parser cố ý từ chối format chưa hỗ trợ** tốt hơn là nhận sai thời điểm.

### 12.2. Unit test cho AD FILETIME

~~~java
import java.time.Instant;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class ActiveDirectoryTimesTest {

    @Test
    void recognizesNeverExpires() {
        assertThat(ActiveDirectoryTimes.accountExpires("0"))
            .isEmpty();

        assertThat(ActiveDirectoryTimes.accountExpires(
            "9223372036854775807"
        )).isEmpty();
    }

    @Test
    void convertsFileTimeEpochToUnixEpoch() {
        assertThat(ActiveDirectoryTimes.accountExpires(
            "116444736000000000"
        )).contains(Instant.EPOCH);
    }
}
~~~

Test này kiểm tra **công thức chuyển epoch**, không chứng minh quyền đọc `accountExpires`, trạng thái thực tế của tài khoản hay chính sách AD production.

### 12.3. Integration test raw và mapped entity

Khi thử với LDAP embedded/container có schema phù hợp:

1. Tạo entry `inetOrgPerson` với các thuộc tính hợp lệ.
2. Đọc raw `uid`, `cn`, `employeeNumber`, `modifyTimestamp`, và một attribute binary nếu có.
3. Xác nhận runtime classes của các raw value (`String`, `byte[]`).
4. Đọc qua ODM/repository và so sánh field đã map; nếu dùng converter, kiểm tra `Instant` đúng UTC.
5. Xác minh `employeeNumber="000812"` không mất số 0 đầu.
6. Tạo nhiều giá trị cho một attribute cho phép đa trị rồi kiểm tra không mất phần tử.
7. Thử account không có `mail` hoặc không trả operational attribute; mapper phải xử lý absence.
8. Thử server có ACL hạn chế; phân biệt “không được trả” với “không tồn tại”.
9. Kiểm tra sai định dạng/overflow được báo lỗi, không silently đưa giá trị mặc định.
10. Kiểm tra chỉ những thuộc tính mà nghiệp vụ được quyền **ghi** mới bị thay đổi khi `save`.

Không dùng một LDIF fixture tự điền `modifyTimestamp` tùy ý để giả lập attribute operational trên server có quản lý nó; hãy để server sinh giá trị hoặc dùng thuộc tính thời gian test riêng theo schema.

### 12.4. Ma trận lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| `DateTimeParseException` với `20261126153045Z` | Dùng `Instant.parse` thay vì formatter LDAP | Parse GeneralizedTime đúng định dạng |
| Thời gian lệch đúng 7 giờ | Diễn giải thời gian UTC như giờ local, hoặc ngược lại | Dùng `Instant`, chỉ đổi ZoneId khi hiển thị |
| `modifyTimestamp == null` | Không yêu cầu operational attribute hoặc ACL ẩn | Xin rõ attribute, kiểm tra LDAP response |
| Từ `000812` thành `812` | Ép mã nghiệp vụ sang số | Giữ `String` |
| `Boolean.parseBoolean("foo")` trả false | Parser quá dễ dãi | Chỉ nhận cú pháp schema được duyệt |
| `ClassCastException` ở ảnh/certificate | JNDI trả `String` nhưng code cast `byte[]` hoặc ngược lại | Kiểm tra raw class, `Attribute.Type.BINARY` |
| Tràn số với LDAP integer/FILETIME | Dùng `int`/`long` không kiểm tra | Parse `BigInteger`, dùng `longValueExact` |
| `accountExpires=0` hiển thị năm 1601 | Không xử lý sentinel AD | Kiểm tra `0`, `Long.MAX_VALUE` trước |
| `UniqueMember` chỉ có một DN | Dùng `Attribute.get()` | Duyệt mọi giá trị |
| DN bị tách sai khi có dấu phẩy escaped | `split(",")` | Dùng `LdapName` |
| ODM converter chạy local nhưng không chạy test | Bean/ConversionService chưa gắn đúng mapper | Kiểm tra Spring Boot config và `LdapTemplate` thực tế |
| Một replica trả timestamp khác | Replication/sửa đổi chưa đồng bộ | Kiểm tra node, thời gian, chính sách nhất quán |

## 13. Hiệu năng, bảo mật và tính đúng đắn

- **Chỉ lấy thuộc tính cần thiết.** Nếu chỉ liệt kê người dùng, không fetch `jpegPhoto`, `userCertificate` hoặc toàn bộ dữ liệu binary lớn.
- **Giữ thời điểm ở UTC** bằng `Instant` trong business logic; UI chịu trách nhiệm hiển thị giờ địa phương.
- **Không sửa thuộc tính server-managed** như `modifyTimestamp`. Với một entity ODM chỉ được load một phần, cân nhắc `LdapTemplate.modifyAttributes` nhắm đúng thuộc tính thay vì `save` toàn bộ.
- **Dùng TLS** (LDAPS/StartTLS) với chứng chỉ đã xác minh, bảo vệ bind credentials và dữ liệu người dùng.
- **Truy vấn filter an toàn** bằng `LdapQueryBuilder` hoặc encoder; giá trị kiểu thời gian/chuỗi từ người dùng không được nối thẳng vào filter LDAP.
- **Phân biệt dữ liệu vắng mặt và dữ liệu sai.** Không biến parse error thành `Instant.EPOCH`, `0`, `false` nếu không có policy được duyệt.
- **Giám sát lỗi chuyển đổi** theo attribute name, DN đã được xử lý phù hợp chính sách và mã lỗi; không log toàn bộ binary hoặc thông tin nhạy cảm.
- **Không giả định thuộc tính vận hành là đồng hồ khóa giao dịch.** `modifyTimestamp` hữu ích cho audit/đối soát nhưng không tự cung cấp optimistic locking đáng tin trên mọi replica và mọi directory.
- **Kiểm thử schema thực tế.** Embedded LDAP có thể khác Active Directory/OpenLDAP về operational attributes, INTEGER/FILETIME hoặc cách trả binary; adapter phải được test với server mục tiêu.

## 14. Câu hỏi tự kiểm tra

1. Vì sao `employeeNumber="000812"` thường nên giữ `String` thay vì `int`?
2. LDAP `GeneralizedTime` khác `Instant.parse` ở cú pháp nào?
3. Vì sao hai chuỗi `20261126153045Z` và `20261126223045+0700` chỉ một thời điểm?
4. Khi nào nên dùng `Instant`, `OffsetDateTime`, `LocalDateTime` trong luồng LDAP?
5. `modifyTimestamp` là operational attribute: điều đó ảnh hưởng việc đọc và update như thế nào?
6. Làm sao xác định `jpegPhoto` là `byte[]` ở JNDI trước khi sửa ODM mapping?
7. Khi nào nên đăng ký `Converter<String, Instant>` cho Spring LDAP ODM? Rủi ro nếu có nhiều định dạng thời gian trong cùng directory?
8. Vì sao `Boolean.parseBoolean(raw)` có thể che giấu giá trị LDAP không hợp lệ?
9. Với LDAP Integer lớn hơn phạm vi `long`, nên dùng API nào để tránh mất giá trị?
10. Vì sao không thể dùng `LdapGeneralizedTime` để parse trực tiếp `accountExpires` của Active Directory?
11. Hai giá trị `accountExpires` nào được Microsoft định nghĩa là “không bao giờ hết hạn”?
12. Khi dùng `uniqueMember`, vì sao không được chỉ lấy `attribute.get()`?
13. DN có thành phần escape chứa dấu phẩy phải parse bằng cách nào?
14. Nếu `attrs.get("modifyTimestamp")==null`, có thể kết luận entry chưa từng được sửa không? Vì sao?
15. Thiết kế một test so raw JNDI với entity ODM để phát hiện sai timezone hoặc converter.

## 15. Tổng kết

**Ánh xạ kết quả LDAP đúng không chỉ là đặt `@Attribute` cho đúng tên.** Ứng dụng phải hiểu **schema syntax, matching rules, raw JNDI types, ngữ nghĩa thuộc tính và quy ước múi giờ**. Với timestamp LDAP phổ biến, dùng parser `GeneralizedTime → Instant`, giữ UTC và chỉ chuyển timezone khi hiển thị. Với dữ liệu số, xác định đó là *con số* hay *mã định danh*; với Boolean, DN, binary và đa trị, dùng quy tắc chuyển đổi tương ứng thay vì ép kiểu theo suy đoán.

Spring LDAP hỗ trợ `AttributesMapper` cho chuyển đổi minh bạch ở mức Search/Lookup, và ODM `ConversionService` cho mapping entity khi đã kiểm thử converter. Những thuộc tính đặc thù như **Active Directory FILETIME** cần adapter và sentinel riêng, không được gom vào một parser ngày giờ chung.

Khi gặp lỗi, hãy theo thứ tự **schema/server → LDAP response → JNDI raw type → ODM converter → business DTO**, xác minh bằng test với directory thích hợp. Đây là cách bảo vệ tính toàn vẹn dữ liệu, tránh lệch thời gian và giữ hành vi repository/LdapTemplate ổn định trong ứng dụng Spring Data LDAP.

### Tài liệu tham khảo

- [RFC 4517 — LDAP: Syntaxes and Matching Rules (Generalized Time, Boolean, Integer, DN)](https://www.rfc-editor.org/rfc/rfc4517).
- [RFC 4512 — LDAP Directory Information Models (attribute types, operational attributes)](https://www.rfc-editor.org/rfc/rfc4512).
- [RFC 4514 — String Representation of Distinguished Names](https://www.rfc-editor.org/rfc/rfc4514).
- [RFC 2849 — LDAP Data Interchange Format](https://www.rfc-editor.org/rfc/rfc2849).
- [Spring LDAP Reference — Object-Directory Mapping and Converters](https://docs.spring.io/spring-ldap/reference/odm.html).
- [Spring LDAP Reference — Basic Usage and AttributesMapper](https://docs.spring.io/spring-ldap/reference/basic-usage.html).
- [Microsoft Learn — Account-Expires attribute](https://learn.microsoft.com/en-us/windows/win32/adschema/a-accountexpires).
