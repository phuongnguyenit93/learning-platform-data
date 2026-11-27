# Đối chiếu schema LDAP với mô hình Java

Trong chương **Attribute và schema** của module **SPRING_LDAP**, người học cần chuyển dữ liệu dạng *entry* của thư mục LDAP thành các lớp, DTO và thao tác Java mà vẫn tôn trọng quy tắc của máy chủ. Công việc này không chỉ là đổi `cn` thành trường `commonName` hay đổi `mail` thành `String`: **schema LDAP xác định entry nào hợp lệ, thuộc tính nào được phép và cách diễn giải giá trị**. Mô hình Java phải phản ánh những ràng buộc ấy mà không làm mất dữ liệu khi đọc hoặc ghi.

Spring LDAP cung cấp nhiều cách làm việc với directory: `LdapTemplate` để truy cập entry và sửa thuộc tính trực tiếp, `LdapClient` với API fluent trong các phiên bản có hỗ trợ, và ODM (*Object-Directory Mapping*) với `@Entry`, `@Id`, `@Attribute`. Cả ba đều đi qua `ContextSource` tới LDAP server; server vẫn là bên kiểm tra schema và quyền truy cập.

**Kết quả học tập**

Sau bài này, bạn có thể:

1. Đọc một entry và xác định các quy tắc schema ảnh hưởng đến mô hình Java.
2. Phân biệt `objectClass`, `MUST`/`MAY`, `SINGLE-VALUE`, syntax và matching rule.
3. Chọn kiểu Java phù hợp cho DN, thuộc tính tùy chọn, giá trị đơn/đa trị và dữ liệu nhị phân.
4. Ánh xạ entry bằng `AttributesMapper` và hiểu vai trò của Spring LDAP ODM.
5. Thiết kế thao tác thêm, sửa, xóa giá trị an toàn với schema và trạng thái đồng thời.
6. Lập bộ kiểm thử xác minh cả dữ liệu Java lẫn tính hợp lệ của LDAP server.

## 1. Vì sao cần đối chiếu hai mô hình?

LDAP và Java mô tả dữ liệu theo hai cách khác nhau:

| Góc nhìn | LDAP directory | Ứng dụng Java |
| --- | --- | --- |
| Đối tượng | Entry xác định bởi Distinguished Name (DN) | Instance của lớp, record hoặc DTO |
| Kiểu của entry | Một hoặc nhiều `objectClass` theo schema | Một class Java, interface hoặc hierarchy do ứng dụng thiết kế |
| Trường dữ liệu | Attribute type và các giá trị | Field, property hoặc thành phần record |
| Bắt buộc/tùy chọn | Quy định `MUST`/`MAY` của object class | Validation, constructor, nullability, quy tắc nghiệp vụ |
| Một/nhiều giá trị | Cờ `SINGLE-VALUE` của attribute type | `String`, `List<String>`, `Set<String>` hoặc kiểu tương ứng |
| Cú pháp giá trị | LDAP syntax, matching rule | `String`, `byte[]`, `Name`, kiểu miền, converter |
| Danh tính/vị trí | DN và RDN của entry | Trường `dn`, khóa ứng dụng, ID ổn định nếu có |
| Quan hệ | DN tham chiếu trong `member`, `manager`... | Tên tham chiếu, ID, liên kết đối tượng được tải có chủ đích |
| Thay đổi | LDAP Add/Modify/Modify DN/Delete | Create/update/delete, mapper và dịch vụ nghiệp vụ |

**Không có phép tương đương một-một mặc định.** Một Java class không nhất thiết tương ứng một LDAP object class; entry có thể mang structural class, các lớp tổ tiên và auxiliary class. Ngược lại, một object class không tự sinh ra đầy đủ validation, quan hệ và kiểu mạnh trong Java.

Ví dụ, ứng dụng nhân sự thường muốn một `Employee` có một email chính, nhưng thuộc tính LDAP `mail` có thể cho phép nhiều giá trị. Nếu tự khai báo:

```java
class Employee {
    String email;
}
```

thì ứng dụng đã **đưa ra quy tắc riêng**: chỉ chọn một địa chỉ email. Quy tắc này không nhất thiết phản ánh toàn bộ các giá trị có trong directory; nếu ghi ngược một cách bất cẩn, những email còn lại có thể bị mất.

## 2. Entry mẫu và các quy tắc liên quan

Giả sử directory có nhánh `dc=example,dc=org` và entry nhân viên:

```ldif
dn: uid=lan,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: lan
cn: Nguyen Thi Lan
cn: Lan Nguyen
sn: Nguyen
employeeNumber: E-1042
mail: lan@example.org
mail: lan.nguyen@example.org
telephoneNumber: +84 24 3555 0101
telephoneNumber: +84 28 3555 0102
```

Các giá trị `cn`, `mail` và `telephoneNumber` có thể nhiều hơn một theo schema thông dụng. `employeeNumber` là ví dụ quen thuộc về attribute có `SINGLE-VALUE` trong schema `inetOrgPerson`. Những quy tắc cụ thể còn phải kiểm tra trên directory đích vì có thể có schema tùy biến hoặc chính sách bổ sung.

Entry này tạo ra các câu hỏi khi thiết kế Java:

- Lớp `Employee` có phải kế thừa bốn lớp Java cho bốn giá trị `objectClass` không?
- `cn` là `String` hay `List<String>`?
- `employeeNumber` có bắt buộc tồn tại không, và nó được phép có bao nhiêu giá trị?
- Nếu không có `telephoneNumber` thì mô hình nhận `null` hay danh sách rỗng?
- `uid` có phải là ID bất biến không, hay DN có thể đổi khi chuyển OU?
- Ứng dụng có quyền ghi tất cả các attribute đọc được không?

Để trả lời, phải phân tích schema thay vì chỉ quan sát một bản LDIF.

## 3. `objectClass` không tương đương trực tiếp với kế thừa Java

Mỗi LDAP entry có thuộc tính `objectClass`, thường chứa nhiều giá trị. Các object class có quan hệ kế thừa được khai báo qua `SUP` trong schema.

Với ví dụ `inetOrgPerson` thông dụng:

```text
top
 └── person
      └── organizationalPerson
           └── inetOrgPerson
```

Một entry thuộc `inetOrgPerson` cũng đáp ứng các lớp tổ tiên liên quan. Mỗi object class có thể đóng góp quy tắc về các attribute bắt buộc và được phép. Ngoài các class trong chuỗi, một entry có thể mang **auxiliary object class** nếu schema và máy chủ cho phép.

| Loại object class | Vai trò chính | Liên hệ khi ánh xạ Java |
| --- | --- | --- |
| `STRUCTURAL` | Xác định loại cấu trúc của entry trong directory. | Thường là căn cứ lựa chọn loại đối tượng Java đại diện. |
| `ABSTRACT` | Cung cấp các quy tắc dùng chung, chẳng hạn `top`. | Không buộc tạo lớp Java trừu tượng tương ứng. |
| `AUXILIARY` | Bổ sung bộ thuộc tính và quy tắc cho entry. | Có thể ánh xạ thành field bổ sung, thành phần riêng hoặc capability. |

**Một Java class hoàn toàn có thể đại diện cho cả chuỗi object class LDAP.** Việc tách các lớp Java dựa trên cấu trúc miền, cách tái sử dụng và nghiệp vụ; không cần nhân bản hierarchy LDAP thành hierarchy Java.

Khi dùng Spring LDAP ODM, annotation `@Entry` khai báo base và các object class áp dụng cho đối tượng, nhưng **annotation không tạo schema trên máy chủ**. Người phát triển vẫn phải bảo đảm object class phù hợp với DN, loại entry và những thuộc tính sẽ ghi.

## 4. `MUST`, `MAY` và `SINGLE-VALUE` giải quyết ba vấn đề khác nhau

### 4.1. `MUST`: attribute bắt buộc tồn tại

Trong schema LDAP, object class có thể khai báo các thuộc tính bắt buộc bằng `MUST`. Với `person` theo schema thông dụng, `cn` và `sn` là những thuộc tính bắt buộc.

Nếu một entry `inetOrgPerson` kế thừa từ `person`, việc bỏ hoàn toàn `sn` hoặc `cn` có thể khiến entry không còn hợp lệ. Một field Java có `@NotNull` giúp kiểm tra ở ứng dụng, nhưng **không tự động mô phỏng hết validation schema của LDAP**.

### 4.2. `MAY`: attribute được phép có mặt

`MAY` cho biết attribute có thể xuất hiện trên entry của loại tương ứng, kể cả thông qua các object class được kế thừa hoặc auxiliary class. Nó không có nghĩa attribute luôn được trả về khi tìm kiếm.

Ví dụ `employeeNumber` là thuộc tính có thể xuất hiện ở `inetOrgPerson` nhưng không mặc nhiên bắt buộc ở mọi entry. Thiếu giá trị có thể là trường hợp hợp lệ.

### 4.3. `SINGLE-VALUE`: cardinality của attribute type

`SINGLE-VALUE` thuộc **định nghĩa attribute type**, không phải thuộc định nghĩa `MUST`/`MAY`. Nó giới hạn một entry chứa tối đa **một giá trị** cho attribute đó.

| Trạng thái | Ý nghĩa theo schema | Kiểu Java gợi ý |
| --- | --- | --- |
| Bắt buộc và đơn trị | Phải có một giá trị hợp lệ. | `String`/value object, được validate khi ghi. |
| Tùy chọn và đơn trị | Không có hoặc có một giá trị. | `String` nullable, hoặc `Optional` ở ranh giới API. |
| Bắt buộc và đa trị | Phải có ít nhất một giá trị; có thể nhiều hơn. | `Set<T>`/`List<T>` kèm kiểm tra không rỗng khi ghi. |
| Tùy chọn và đa trị | Có thể không có hoặc có nhiều giá trị. | Collection; thường trả danh sách rỗng khi đọc DTO. |

**Lưu ý:** bảng là nguyên tắc thiết kế, không phải công thức tạo schema. Trong thực tế, yêu cầu MUST/MAY chịu ảnh hưởng của các object class đang áp dụng, subtype và các ràng buộc riêng. Một thuộc tính cho phép đa trị nhưng chỉ đang có một giá trị **không biến nó thành đơn trị**.

## 5. Syntax và matching rule: cùng `String` nhưng chưa chắc cùng nghĩa

Cách đơn giản nhất để lưu LDAP attribute trong Java là `String`, nhưng không phải mọi attribute đều có cùng syntax hoặc cách so sánh.

| Attribute mẫu | Ý nghĩa dữ liệu | Kiểu Java ở ranh giới LDAP | Điều cần cân nhắc |
| --- | --- | --- | --- |
| `cn` | Tên hiển thị hoặc tên chung | `List<String>`/`Set<String>` | Có thể đa trị; không có "giá trị đầu tiên" được bảo đảm. |
| `sn` | Họ/tên gia đình | Collection chuỗi nếu cần bảo toàn mọi giá trị | Được object class `person` yêu cầu; không nên tự giả định chỉ một giá trị theo schema. |
| `employeeNumber` | Mã nhân sự | `String` hoặc `EmployeeCode` | Thường đơn trị; có thể vắng mặt; tính duy nhất toàn thư mục là ràng buộc khác. |
| `mail` | Địa chỉ email | `Set<String>` hoặc `List<String>` | Có thể đa trị; địa chỉ chính là quy tắc nghiệp vụ riêng. |
| `telephoneNumber` | Số điện thoại | Collection chuỗi | Thường đa trị; matching không đơn giản là so chuỗi thô. |
| `member` | Các DN thành viên nhóm | `List<Name>` sau chuyển đổi, hoặc `List<String>` giữ nguyên | Phải phân tích DN; không suy thành quan hệ Java được tải tự động. |
| `jpegPhoto` | Ảnh nhị phân | `byte[]` hoặc collection nhị phân tùy cardinality | Không cast sang `String`; cân nhắc kích thước, sao chép mảng và quyền riêng tư. |
| `createTimestamp` | Thời gian tạo do server quản lý | Chuỗi gốc hoặc kiểu thời gian sau parse rõ ràng | Thường là operational attribute, không nên cho ứng dụng tùy tiện sửa. |

**LDAP syntax** xác định dạng giá trị và quy tắc mã hóa/giải mã. **Matching rule** xác định cách máy chủ so sánh các giá trị trong filter và khi kiểm tra giá trị tương đương. Chẳng hạn một phép equality theo quy tắc không phân biệt chữ hoa/thường không giống phép so sánh byte hoặc `String.equals()` trong Java.

Hệ quả khi thiết kế mô hình:

1. Chọn kiểu Java dựa trên schema **và** mục tiêu nghiệp vụ.
2. Không dùng `Set<String>` rồi mặc nhiên tin rằng `String.equals()` của Java thể hiện đúng matching rule của LDAP. Set trong Java xử lý trùng lặp theo quy tắc của Java; server có thể có quy tắc tương đương khác.
3. Với dữ liệu nhị phân, đọc về đúng kiểu; nếu xuất ra JSON hoặc lưu trong cơ sở dữ liệu khác, phải định nghĩa chuyển đổi và bảo vệ dữ liệu.
4. Với thuộc tính thời gian, xác định syntax, múi giờ, độ chính xác và cách parse trước khi đổi sang `Instant`.
5. Nếu dùng domain type như `EmployeeCode`, tạo adapter/converter để đổi có kiểm soát tại ranh giới LDAP thay vì giả định ODM tự hiểu mọi kiểu tự định nghĩa.

## 6. Dữ liệu đa trị là tập giá trị, không phải danh sách có thứ tự

Các giá trị của một LDAP attribute đa trị không có thứ tự ổn định được giao thức bảo đảm. Ví dụ:

```ldif
mail: lan@example.org
mail: lan.nguyen@example.org
```

Không thể kết luận địa chỉ xuất hiện đầu tiên là email chính. Nếu business logic muốn có `primaryEmail`, ứng dụng phải có quy tắc xác định rõ ràng, ví dụ lấy từ một attribute chuyên biệt, cấu hình riêng hoặc nguồn dữ liệu có thẩm quyền.

Đây là lựa chọn kiểu Java thường gặp:

| Kiểu Java | Ưu điểm | Rủi ro hoặc giới hạn |
| --- | --- | --- |
| `String` | Đơn giản cho thuộc tính thật sự đơn trị. | Làm mất các giá trị còn lại nếu áp vào thuộc tính đa trị. |
| `List<String>` | Giữ đủ các giá trị trả về, dễ chuyển thành DTO/JSON. | Thứ tự trong list không có ngữ nghĩa LDAP mặc định. |
| `Set<String>` | Thể hiện ý định không lưu trùng theo quy tắc Java. | Quy tắc bằng nhau của Set có thể khác matching rule LDAP. |
| `byte[]` | Phù hợp cho một giá trị nhị phân. | Mảng có thể bị sửa, so sánh bằng reference, không bảo đảm đa trị. |
| `List<byte[]>` | Có thể giữ nhiều giá trị nhị phân. | Cần sao chép dữ liệu nếu muốn bất biến; `equals()` của mảng không so nội dung. |

**Đơn trị/tùy chọn** cũng cần phân biệt với **không có attribute**. Trong entry LDAP, một attribute tùy chọn không có giá trị thường được biểu diễn bằng việc attribute **vắng mặt**, thay vì tồn tại với collection rỗng. Trên DTO đọc, ứng dụng có thể chuyển vắng mặt thành `List.of()` để thuận tiện, nhưng cần biết mình đã chọn một biểu diễn mới.

## 7. DN và RDN: vị trí entry khác định danh nghiệp vụ

Entry `uid=lan,ou=people,dc=example,dc=org` có DN gồm nhiều thành phần. DN xác định vị trí trong Directory Information Tree; `uid` là một attribute thường được sử dụng làm RDN. Mô hình Java nên phân biệt:

- `Name dn` hoặc `LdapName dn`: vị trí entry trong LDAP.
- `String uid`: một giá trị thuộc tính dùng cho nghiệp vụ hoặc tìm kiếm.
- Một **ID ổn định** (nếu server cung cấp và ứng dụng cần): định danh không phụ thuộc đổi tên/chuyển OU.

Đổi `uid` trong DN hoặc di chuyển entry sang OU khác có thể làm thay đổi DN. Java object chứa một `String id = "uid=lan,ou=people,..."` sẽ phải xử lý những lần đổi tên này. Không nên mặc định DN là khóa bất biến cho mọi hệ thống tích hợp.

Với Spring LDAP có cấu hình base DN:

```yaml
spring:
  ldap:
    urls: ${LDAP_URL:ldaps://ldap.example.org:636}
    base: dc=example,dc=org
    username: ${LDAP_BIND_DN}
    password: ${LDAP_BIND_PASSWORD}
```

`LdapTemplate` thường sử dụng **DN tương đối với base** được cấu hình. Để truy cập người dùng Lan:

```java
import javax.naming.Name;
import org.springframework.ldap.support.LdapNameBuilder;

Name relativeDn = LdapNameBuilder.newInstance("ou=people")
        .add("uid", "lan")
        .build();

// uid=lan,ou=people
```

Không ghép các thành phần của DN trực tiếp từ chuỗi đầu vào. `LdapNameBuilder` xử lý việc escape các ký tự đặc biệt ở giá trị RDN; điều này khác với escape giá trị trong **LDAP search filter**.

## 8. Ánh xạ rõ ràng bằng `LdapTemplate` và `AttributesMapper`

Ánh xạ thủ công giúp kiểm soát chính xác attribute nào được đọc, attribute nào có thể thiếu và cách biểu diễn đa trị. Với entry người dùng mẫu, ta có thể chọn DTO chỉ đọc:

```java
import java.util.List;

public record PersonSnapshot(
        String employeeNumber,
        List<String> commonNames,
        List<String> surnames,
        List<String> emails
) {}
```

`employeeNumber` là `String` vì giả sử schema máy chủ xác nhận thuộc tính này đơn trị. `cn`, `sn` và `mail` được lưu bằng `List<String>` vì DTO muốn giữ **tất cả giá trị**, kể cả khi nghiệp vụ chỉ hiển thị một tên trên giao diện.

### Đọc entry và chuyển đổi giá trị

```java
import java.util.ArrayList;
import java.util.List;

import javax.naming.Name;
import javax.naming.NamingEnumeration;
import javax.naming.NamingException;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;

import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

public final class PersonDirectoryReader {

    private final LdapTemplate ldapTemplate;

    public PersonDirectoryReader(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public PersonSnapshot find(String uid) {
        Name dn = LdapNameBuilder.newInstance("ou=people")
                .add("uid", uid)
                .build();

        return ldapTemplate.lookup(
                dn,
                (AttributesMapper<PersonSnapshot>) attrs ->
                        new PersonSnapshot(
                                optionalSingleString(attrs, "employeeNumber"),
                                allStrings(attrs, "cn"),
                                allStrings(attrs, "sn"),
                                allStrings(attrs, "mail")));
    }

    private static String optionalSingleString(Attributes attrs, String key)
            throws NamingException {
        Attribute attribute = attrs.get(key);

        if (attribute == null) {
            return null; // Attribute tùy chọn vắng mặt.
        }
        if (attribute.size() != 1) {
            throw new IllegalStateException(
                    key + " không có đúng một giá trị như schema mong đợi");
        }

        Object value = attribute.get();
        if (!(value instanceof String text)) {
            throw new IllegalStateException(key + " không phải kiểu chuỗi");
        }
        return text;
    }

    private static List<String> allStrings(Attributes attrs, String key)
            throws NamingException {
        Attribute attribute = attrs.get(key);
        if (attribute == null) {
            return List.of();
        }

        List<String> result = new ArrayList<>();
        NamingEnumeration<?> values = attribute.getAll();

        try {
            while (values.hasMore()) {
                Object value = values.next();
                if (!(value instanceof String text)) {
                    throw new IllegalStateException(
                            key + " chứa giá trị không phải chuỗi");
                }
                result.add(text);
            }
        } finally {
            values.close();
        }
        return List.copyOf(result);
    }
}
```

**Những lựa chọn cố ý trong ví dụ:**

- `optionalSingleString()` trả `null` nếu attribute tùy chọn không có mặt, nhưng **báo lỗi** nếu đọc được nhiều giá trị ở thuộc tính mà schema yêu cầu đơn trị; tránh âm thầm lấy giá trị đầu tiên.
- `allStrings()` duyệt toàn bộ `NamingEnumeration`, đóng enumeration và trả collection bất biến ở tầng DTO.
- DTO giữ `cn`/`sn`/`mail` dưới dạng collection để tránh làm mất giá trị hợp lệ.
- Hàm chỉ xử lý thuộc tính dạng chuỗi; đối với syntax nhị phân cần mapper riêng.
- `lookup` dùng DN tương đối với base DN của `ContextSource`. Một DN không tồn tại cần được dịch sang kết quả hoặc lỗi nghiệp vụ phù hợp, chẳng hạn HTTP 404 ở tầng API.
- Thứ tự phần tử của `List` **không được dùng để xác định giá trị ưu tiên**; nếu cần hiển thị ổn định, ứng dụng có thể sắp xếp một bản sao theo quy tắc cụ thể.

Khi ứng dụng chỉ cần một vài field, có thể chỉ yêu cầu những attribute cần thiết từ máy chủ thông qua API search/lookup có hỗ trợ chỉ định danh sách thuộc tính. Tránh truy xuất cả dữ liệu nhạy cảm và operational attribute không phục vụ nghiệp vụ.

## 9. ODM: gắn annotation Java với schema LDAP

Spring LDAP ODM cho phép khai báo cách một class Java ánh xạ vào entry bằng annotation. Ví dụ hình dạng mô hình:

```java
import java.util.Set;
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

    @Attribute(name = "employeeNumber")
    private String employeeNumber;

    @Attribute(name = "cn")
    private Set<String> commonNames;

    @Attribute(name = "sn")
    private Set<String> surnames;

    @Attribute(name = "mail")
    private Set<String> emails;

    public PersonEntry() {
    }

    // Getter/setter hoặc các phương thức truy cập theo framework sử dụng.
}
```

Ở cấp mô hình, lựa chọn trên diễn tả:

| Annotation/field | Ý nghĩa |
| --- | --- |
| `@Entry(base = "ou=people", …)` | Mô tả entry trong nhánh LDAP cụ thể và các object class. |
| `@Id Name dn` | Lưu DN theo cơ chế ODM, không cần coi mọi phần của DN là chuỗi tự ghép. |
| `@Attribute(name = "employeeNumber") String` | Thuộc tính đơn trị và tùy chọn theo giả định schema mẫu. |
| `@Attribute(name = "cn") Set<String>` | Một thuộc tính có thể có nhiều tên; không ép chỉ lấy một. |
| `@Attribute(name = "sn") Set<String>` | Thuộc tính được yêu cầu bởi `person` nhưng vẫn cần kiểm tra số lượng khi ghi. |
| `@Attribute(name = "mail") Set<String>` | Lưu nhiều email; không áp thứ tự chính/phụ. |

Đây là **mẫu biểu diễn**, cần hoàn thiện accessors, quy tắc gán DN, constructor và tương thích converter/collection theo phiên bản Spring LDAP được sử dụng. Không phải bất kỳ Java type nào cũng được ODM tự chuyển đổi thành LDAP syntax tương ứng. Với kiểu miền tùy biến, dữ liệu binary hoặc object class đặc thù, có thể cần converter hay mapper riêng.

**Giới hạn quan trọng của ODM:**

1. Annotation không bảo đảm máy chủ đã có object class hoặc attribute type đó.
2. Java field có `null`/collection rỗng không thay thế validation `MUST` khi lưu.
3. Ánh xạ `Set<String>` không tự áp dụng matching rule của server khi kiểm tra trùng.
4. Một entry thực tế có thể chứa attribute ngoài các field đã ánh xạ. Cần hiểu rõ cơ chế save/update của API trước khi dùng một đối tượng thiếu field để ghi ngược toàn bộ dữ liệu.
5. Entry và class có thể thay đổi độc lập theo phiên bản schema hoặc ứng dụng. Vì vậy ánh xạ phải được kiểm thử bằng directory thật hoặc môi trường test có schema tương đương.

Khi schema quá linh hoạt hoặc có nhiều custom attribute, `LdapTemplate` với mapper tường minh đôi khi dễ kiểm soát hơn ODM. ODM hữu ích khi mô hình entry ổn định và nhu cầu thao tác đối tượng rõ ràng.

## 10. Khi ghi dữ liệu, phải hiểu phép biến đổi trên LDAP

Java thường cập nhật một field bằng phép gán:

```java
person.setEmails(Set.of("new@example.org"));
```

Nhưng ở LDAP, hành động này có thể mang ý nghĩa **thay toàn bộ** tập giá trị `mail`. Với attribute đa trị, cần xác định rõ nghiệp vụ muốn **thêm**, **xóa một giá trị** hay **thay tất cả**.

JNDI cung cấp `ModificationItem` và ba kiểu sửa:

| Kiểu sửa | Ý nghĩa | Trường hợp thích hợp |
| --- | --- | --- |
| `DirContext.ADD_ATTRIBUTE` | Bổ sung attribute hoặc giá trị cụ thể. | Thêm một email/số điện thoại/thành viên nhóm, giữ các giá trị cũ. |
| `DirContext.REPLACE_ATTRIBUTE` | Thay tập giá trị đang lưu. | Hệ thống chủ sở hữu muốn cập nhật toàn bộ danh sách hoặc đổi một giá trị đơn trị. |
| `DirContext.REMOVE_ATTRIBUTE` | Xóa attribute hoặc giá trị được chỉ định. | Gỡ một thành viên/số điện thoại mà không xóa các giá trị còn lại. |

Ví dụ sửa có chủ đích bằng `LdapTemplate`:

```java
import javax.naming.Name;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;

import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

public final class PersonDirectoryWriter {

    private final LdapTemplate ldapTemplate;

    public PersonDirectoryWriter(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    private Name dnFor(String uid) {
        return LdapNameBuilder.newInstance("ou=people")
                .add("uid", uid)
                .build();
    }

    // Bổ sung email; các email cũ vẫn được giữ lại.
    public void addEmail(String uid, String email) {
        ModificationItem change = new ModificationItem(
                DirContext.ADD_ATTRIBUTE,
                new BasicAttribute("mail", email));

        ldapTemplate.modifyAttributes(
                dnFor(uid), new ModificationItem[] {change});
    }

    // Thay mã nhân viên (thuộc tính đơn trị theo schema mẫu).
    public void replaceEmployeeNumber(String uid, String number) {
        ModificationItem change = new ModificationItem(
                DirContext.REPLACE_ATTRIBUTE,
                new BasicAttribute("employeeNumber", number));

        ldapTemplate.modifyAttributes(
                dnFor(uid), new ModificationItem[] {change});
    }

    // Xóa đúng một email, không xóa toàn bộ attribute mail.
    public void removeEmail(String uid, String email) {
        ModificationItem change = new ModificationItem(
                DirContext.REMOVE_ATTRIBUTE,
                new BasicAttribute("mail", email));

        ldapTemplate.modifyAttributes(
                dnFor(uid), new ModificationItem[] {change});
    }
}
```

Nếu gửi `ADD_ATTRIBUTE` với giá trị `employeeNumber` thứ hai trong khi nó đã có một giá trị, máy chủ có thể trả lỗi vì `SINGLE-VALUE`. Nếu gỡ giá trị cuối cùng của `cn` hoặc `sn`, máy chủ có thể từ chối vì vi phạm `MUST` của `person`.

**Không nên đọc tập email, thêm một phần tử rồi `REPLACE_ATTRIBUTE` toàn bộ chỉ để thực hiện thao tác thêm.** Cách đọc–sửa–ghi có thể làm mất thay đổi từ một tiến trình khác giữa hai bước. Thao tác add/remove theo giá trị cụ thể thường phù hợp hơn; khi bắt buộc replace toàn bộ, cần giải quyết xung đột theo khả năng máy chủ và yêu cầu nghiệp vụ.

### Cập nhật qua `DirContextOperations`

`LdapTemplate.lookupContext(dn)` trả về đối tượng `DirContextOperations` có thể được thay đổi rồi truyền cho `modifyAttributes()`. API như `setAttributeValue()` và `setAttributeValues()` hữu ích nhưng người lập trình phải biết tác động lên **toàn bộ tập giá trị** của attribute. Với thuộc tính đa trị không thuộc quyền sở hữu của ứng dụng, chỉ đặt một giá trị rồi lưu có thể làm mất dữ liệu.

Đối với `LdapClient` hoặc ODM, cú pháp lưu khác nhau theo phiên bản, nhưng server vẫn thực hiện các thao tác LDAP và áp dụng cùng những quy tắc schema, ACL, matching rule.

## 11. Đối chiếu validation Java và validation server

Schema của máy chủ là **nguồn xác định cuối cùng** xem entry được phép ghi hay không. Validation ở Java cần bổ sung các quy tắc nghiệp vụ, nâng chất lượng lỗi và giảm request sai, nhưng không thể thay thế kiểm tra phía LDAP.

| Quy tắc | Kiểm tra Java có thể làm | Máy chủ LDAP vẫn quyết định |
| --- | --- | --- |
| `cn`/`sn` bắt buộc | Không cho lưu DTO tạo mới nếu trống. | Object class có yêu cầu MUST và dữ liệu đúng schema không. |
| `employeeNumber` đơn trị | DTO chọn một `String`; từ chối collection nhiều giá trị. | Attribute type có `SINGLE-VALUE` và giá trị mới hợp lệ không. |
| Email hợp lệ | Kiểm tra độ dài/định dạng theo sản phẩm. | Syntax, matching rules và chính sách server. |
| `mail` đa trị | Giữ toàn bộ collection, loại trùng theo quy tắc ứng dụng. | Trùng/tương đương theo LDAP, quyền được thêm/sửa. |
| DN đúng cấu trúc | Xây bằng `LdapNameBuilder`, kiểm tra OU cho phép. | Entry cha tồn tại, naming rules và ACL có cho phép không. |
| Mã nhân viên duy nhất trên toàn thư mục | Kiểm tra nghiệp vụ và xử lý race condition. | Chỉ được bảo đảm nếu server có ràng buộc hoặc quy trình đủ mạnh. |
| Attribute do server quản lý | Đánh dấu read-only trong DTO cập nhật. | Server quyết định thuộc tính có sửa được không. |

Ví dụ **một attribute đơn trị không đồng nghĩa với duy nhất trên toàn directory**: hai entry có thể cùng `employeeNumber=E-1042` nếu không có ràng buộc uniqueness bổ sung. `SINGLE-VALUE` chỉ giới hạn **số giá trị của attribute đó trong mỗi entry**.

Bean Validation như `@NotBlank`, `@Size` hoặc custom validator là lớp kiểm tra hữu ích tại API; nó không tự biết sự kế thừa `objectClass`, các custom attribute, quyền bind, subtype hoặc ràng buộc schema mới triển khai trên server.

## 12. Schema thực tế có thể khác tài liệu mẫu

Khi tích hợp vào OpenLDAP, Active Directory hoặc máy chủ LDAP khác, không nên xem entry mẫu là mô hình phổ quát.

Một số điểm khác biệt cần khảo sát:

- **Object class:** một số tổ chức có custom structural/auxiliary object class hoặc attribute bắt buộc riêng.
- **Tên attribute:** có alias, subtype hoặc tên phù hợp với từng hệ thống, ví dụ cách biểu diễn tài khoản, nhóm và mã định danh.
- **Syntax và matching:** cùng nội dung hiển thị nhưng quy tắc mã hóa/so khớp có thể khác.
- **Cardinality:** những thuộc tính custom có thể dùng `SINGLE-VALUE` trong khi thuộc tính gần nghĩa ở nơi khác cho phép đa trị.
- **Operational attribute:** thông tin như thời điểm tạo, thay đổi, DN đặc biệt hoặc ID nội bộ có thể do máy chủ quản lý, không hiện trong kết quả tìm kiếm mặc định.
- **Phân quyền:** schema cho phép ghi chưa chắc ACL cho tài khoản ứng dụng ghi.
- **Hỗ trợ API/protocol:** phân trang, StartTLS, cơ chế authentication bind và khả năng rename/move có khác biệt.

### Quy trình kiểm tra schema thực tế

1. **Xác định naming context và loại entry cần tích hợp.** Đọc `objectClass` của entry mẫu bằng tài khoản chỉ đọc.
2. **Tìm thông tin schema có hiệu lực.** Máy chủ có thể công bố `subschemaSubentry` và định nghĩa `attributeTypes`/`objectClasses` ở schema entry; khả năng truy cập tùy quyền và triển khai.
3. **Ghi nhận ràng buộc cho từng attribute:** MUST/MAY, syntax, SINGLE-VALUE, matching rules, tính operational/readonly và giá trị mặc định nếu có chính sách riêng.
4. **Đối chiếu Java model:** type, collection, nullability, converter, field được ghi và field chỉ đọc.
5. **Kiểm thử trên LDAP test có schema tương ứng.** Không xác nhận tính đúng đắn chỉ bằng một unit test mapper với dữ liệu giả.

Nếu server không cho phép đọc toàn bộ schema, cần lấy mô tả schema từ quản trị viên hoặc bộ cấu hình triển khai chính thức. Không tự suy từ vài entry đang tồn tại rằng một attribute chắc chắn là đơn trị hoặc luôn bắt buộc.

## 13. Thiết kế lớp Java theo nhu cầu: DTO đọc và lệnh ghi

Một mô hình dễ bảo trì là tách **hình dạng dữ liệu đọc từ LDAP** khỏi **các lệnh thay đổi LDAP**:

```java
import java.util.List;

// Dữ liệu ứng dụng đã đọc, không tự ghi ngược lên LDAP.
public record PersonView(
        String uid,
        List<String> commonNames,
        List<String> emails,
        String employeeNumber
) {}
```

```java
// Các lệnh mô tả rõ ý định cập nhật.
public record AddPersonEmail(String uid, String email) {}
public record ReplaceEmployeeNumber(String uid, String newNumber) {}
```

*Các khai báo `public` trên được đặt trong những tệp Java riêng nếu biên dịch dưới dạng mã nguồn thực.*

Tách read model và write command giúp tránh một vấn đề thường gặp: HTTP request chỉ gửi `employeeNumber` nhưng framework lại biến những field không gửi thành `null` hoặc collection rỗng, rồi ghi ngược gây xóa thông tin trên LDAP.

Đối với mô hình lưu trong ODM, có thể dùng một aggregate phù hợp, nhưng vẫn nên xác định ranh giới nào cho phép cập nhật toàn bộ và ranh giới nào chỉ thực hiện `ADD_ATTRIBUTE`/`REMOVE_ATTRIBUTE` trên một giá trị. Việc dùng DTO không thay thế ACL, xác thực hoặc kiểm tra ownership của attribute.

### Khi thiết kế API, hãy hỏi bốn câu

1. **Ứng dụng sở hữu attribute nào?** Ví dụ HR quản lý `employeeNumber`; hệ thống danh bạ có thể quản lý `telephoneNumber`; IAM quản lý quyền nhóm.
2. **Thao tác này là thêm, thay hay xóa?** Không dùng replace cho nghiệp vụ chỉ muốn thêm một giá trị.
3. **Nếu thiếu field trong request, có nghĩa là không đổi hay xóa?** Cần quy ước rõ giữa omitted, null, empty collection và yêu cầu xóa chủ động.
4. **Nếu hai tác nhân cùng cập nhật, kết quả mong muốn là gì?** Đặc biệt quan trọng với attribute đa trị và dữ liệu có nhiều nguồn đồng bộ.

## 14. Bảo mật và xử lý lỗi khi ánh xạ

Vì dữ liệu LDAP thường chứa thông tin tài khoản và nhận dạng cá nhân, một mapper đúng về kiểu nhưng làm lộ dữ liệu vẫn là một thiết kế không đạt yêu cầu.

**Bảo mật:**

- Dùng LDAPS hoặc StartTLS với xác minh chứng chỉ; không coi việc cài đặt `ContextSource` là bảo đảm TLS đã hoạt động đúng.
- Sử dụng tài khoản bind có quyền tối thiểu. Đọc `mail` không có nghĩa được sửa `member` hoặc các thuộc tính bảo mật.
- Không đưa password/hash, token, secret hoặc ảnh nhạy cảm vào log và DTO trả ra khi không cần thiết.
- Xây DN bằng API xử lý RDN, xây filter bằng builder/escaping phù hợp; escaping DN và escaping filter là hai quy tắc khác nhau.
- Nếu có pooling, kiểm tra cấu hình xác thực và vòng đời kết nối để tránh tái sử dụng không đúng ngữ cảnh bảo mật.

**Xử lý lỗi:**

| Hiện tượng | Khả năng liên quan đến schema/mapping | Phản ứng cần thiết |
| --- | --- | --- |
| `objectClassViolation` (mã LDAP 65) | Thiếu MUST, ghi attribute không được phép hoặc object class không phù hợp. | Kiểm tra định nghĩa object class và các giá trị đang gửi. |
| `constraintViolation` (mã 19) | Vi phạm ràng buộc của attribute hoặc chính sách server. | Kiểm tra cardinality, syntax, schema tùy biến. |
| `attributeOrValueExists` (mã 20) | Thêm giá trị bị coi là trùng. | Xác minh matching rule và trạng thái trước khi xử lý idempotent. |
| `noSuchAttribute` (mã 16) | Xóa attribute/giá trị không có. | Kiểm tra ý định xóa và dữ liệu thực tế. |
| `undefinedAttributeType` (mã 17) | Attribute type chưa được server định nghĩa. | Không tự thêm field lạ; phối hợp người quản trị schema. |
| `insufficientAccessRights` (mã 50) | Tài khoản bind không có quyền sửa/đọc. | Kiểm tra ACL và scope của service account. |
| `invalidAttributeSyntax` (mã 21) | Giá trị không phù hợp syntax được khai báo. | Kiểm tra converter, mã hóa và validation. |
| Lỗi cast/serialization trong Java | DTO/ODM giả định sai kiểu hoặc số lượng giá trị. | Sửa mapper, không ép mất dữ liệu để che lỗi. |

Spring LDAP ánh xạ lỗi của JNDI/LDAP sang hệ exception phù hợp; không nên dựa vào một tên exception duy nhất cho mọi máy chủ mà không kiểm tra kết quả thực tế. Với lỗi ghi, log nên đủ ngữ cảnh kỹ thuật để chẩn đoán nhưng không tiết lộ secret hoặc giá trị riêng tư.

## 15. Kiểm thử ánh xạ và các thay đổi schema

Unit test có thể xác nhận mapper chuyển một `Attributes` giả thành DTO đúng. Nhưng **kiểm thử tích hợp** với LDAP server có schema tương ứng mới cho thấy các ràng buộc thực tế được áp dụng.

Bảng kiểm thử gợi ý:

| Ca kiểm thử | Dữ liệu/Thao tác | Kết quả mong đợi |
| --- | --- | --- |
| Bắt buộc hợp lệ | Tạo `inetOrgPerson` có `cn` và `sn`, cùng object class đúng. | Entry được chấp nhận nếu đủ các ràng buộc khác. |
| Thiếu thuộc tính MUST | Tạo entry không có `sn`. | Máy chủ từ chối theo schema đang áp dụng. |
| Đơn trị hợp lệ | Thêm một `employeeNumber`. | Thành công nếu quyền và giá trị hợp lệ. |
| Đơn trị bị vi phạm | Dùng ADD để bổ sung `employeeNumber` thứ hai. | Máy chủ từ chối. |
| Đa trị đầy đủ | Entry có hai `mail`; đọc qua mapper. | DTO giữ cả hai giá trị. |
| Đa trị thiếu | Entry không có `telephoneNumber`. | DTO đọc collection rỗng hoặc biểu diễn thiếu đã chọn. |
| Thêm giá trị | Thêm email thứ ba bằng ADD. | Hai email cũ vẫn tồn tại. |
| Xóa một giá trị | REMOVE một email chỉ định. | Các email khác còn nguyên. |
| Trùng theo matching rule | Thử ADD một giá trị được server coi tương đương. | Server áp dụng đúng luật trùng lặp. |
| Không đủ quyền | Tài khoản chỉ đọc thử sửa `mail`. | Thao tác bị từ chối. |
| Truy cập nhầm DN | Dùng DN chứa ký tự cần escape hoặc DN ở OU khác. | Builder tạo đúng DN và truy vấn không vượt nhánh cho phép. |
| Schema thay đổi | Bổ sung/đổi một attribute custom trong môi trường test. | Mapper và lệnh ghi nhận diện dữ liệu thiếu hoặc quy tắc mới. |

Dữ liệu thử nên nằm trong OU dành riêng, dùng tài khoản quyền hạn hẹp và tránh trùng với entry thật. Khi kiểm thử tìm kiếm, giới hạn search base/scope, kích thước và thời gian; nếu dữ liệu lớn, cân nhắc LDAP paged results theo khả năng server. Sau thao tác ghi, **đọc lại** bằng một kết nối phù hợp để xác nhận trạng thái và không làm mất các giá trị khác.

### Khi schema thay đổi theo thời gian

Ví dụ hệ thống bổ sung một attribute `employeeType` hoặc một auxiliary object class riêng:

1. Xác minh schema mới đã được áp dụng ở môi trường đích.
2. Cập nhật mapper và cách xử lý entry cũ chưa có attribute đó.
3. Tách dữ liệu có thể thiếu khỏi dữ liệu mới bắt buộc; tránh biến một thay đổi schema thành lỗi đọc hàng loạt entry cũ.
4. Nếu cập nhật qua ODM, kiểm tra cơ chế save tránh ghi đè các attribute chưa được mô hình Java biết đến.
5. Chạy kiểm thử tích hợp trên entry cũ, mới và trường hợp ràng buộc bị vi phạm.

## 16. Bài tập ứng dụng: từ schema đến Java

Giả sử bạn phát triển dịch vụ danh bạ nhân viên trên LDAP có schema `inetOrgPerson` thông dụng, được xác nhận:

- `cn` và `sn` được yêu cầu qua `person` và có thể chứa nhiều giá trị.
- `employeeNumber` được phép có mặt nhưng là attribute đơn trị.
- `mail` được phép có mặt và có thể đa trị.
- `telephoneNumber` là thuộc tính tùy chọn và có thể đa trị.
- `uid` được dùng làm RDN trong OU nhân viên; ứng dụng có quy tắc riêng để bảo đảm UID không trùng trong nhánh đó.

### Bài tập 1 — Thiết kế DTO

Thiết kế `PersonView` sao cho có thể giữ trọn các giá trị `cn`, `sn`, `mail`, `telephoneNumber` và một `employeeNumber`. Chỉ ra những field nào có thể vắng mặt và cách biểu diễn vắng mặt ở tầng DTO.

### Bài tập 2 — Phân biệt schema và nghiệp vụ

Trả lời:

1. Nếu hai entry cùng `employeeNumber=E-1042`, có chắc đã vi phạm `SINGLE-VALUE` không?
2. Nếu `mail` của một entry hiện chỉ có một giá trị, đã đủ cơ sở khai báo `String email` làm bản sao chính xác chưa?
3. Nếu `cn` thuộc `MUST`, có bắt buộc là attribute đơn trị không?
4. Nếu entry có `objectClass: inetOrgPerson`, ứng dụng có cần bốn Java class tương ứng bốn lớp trong LDAP không?

### Bài tập 3 — Chọn thao tác LDAP

Entry chứa:

```ldif
mail: lan@example.org
mail: lan.nguyen@example.org
```

Hãy chọn thao tác phù hợp cho ba yêu cầu:

1. Thêm `lan.work@example.org` mà giữ hai email trước.
2. Xóa riêng `lan.nguyen@example.org`.
3. Thay toàn bộ tập email bằng đúng `lan.work@example.org` khi ứng dụng có quyền sở hữu danh sách.

Giải thích kết quả nếu dùng `REPLACE_ATTRIBUTE` để xử lý yêu cầu số 1.

### Bài tập 4 — Sửa mô hình bị mất dữ liệu

Một lớp Java có trường `String mail` và mapper chỉ lấy `attrs.get("mail").get()`. Hãy chỉ ra vấn đề; viết lại kiểu dữ liệu và thuật toán đọc để không bỏ sót email.

### Đáp án tham khảo

1. **Bài 1:** `List<String>` hoặc `Set<String>` cho `cn`, `sn`, `mail` và `telephoneNumber`; `String` nullable cho `employeeNumber`. `cn`/`sn` là bắt buộc ở server nên phải kiểm tra không rỗng khi ghi. Collection tùy chọn có thể trả `List.of()` khi đọc; điều này là quy ước DTO.
2. **Bài 2:** (1) Không: `SINGLE-VALUE` là ràng buộc **trong một entry**, không phải uniqueness toàn directory. (2) Không: schema có thể cho phép nhiều email. (3) Không: `MUST` chỉ yêu cầu attribute hiện diện. (4) Không: một Java class có thể đại diện cho chuỗi object class.
3. **Bài 3:** (1) `ADD_ATTRIBUTE` với email mới. (2) `REMOVE_ATTRIBUTE` kèm giá trị cần gỡ. (3) `REPLACE_ATTRIBUTE` với tập chứa một email mới. Dùng replace cho (1) sẽ xóa mất hai email cũ.
4. **Bài 4:** Mapper chỉ lấy một giá trị nên có thể mất dữ liệu; dùng collection và `Attribute.getAll()`, duyệt đủ giá trị, kiểm tra kiểu và đóng `NamingEnumeration`.

## 17. Tổng kết

Đối chiếu **schema LDAP với mô hình Java** cần làm rõ bốn nhóm thông tin trước khi viết code: **loại entry và object class**, **thuộc tính bắt buộc/được phép**, **kiểu và số lượng giá trị**, **ý định đọc/ghi cùng quyền truy cập**. Một Java class và một LDAP entry có thể cùng mô tả một nhân viên nhưng không cùng ngữ nghĩa ở mọi thuộc tính.

Khi dùng **Spring LDAP**, hãy lựa chọn `LdapTemplate`/`AttributesMapper` nếu cần kiểm soát tường minh hoặc dùng ODM khi schema và mô hình đủ ổn định. Luôn giữ dữ liệu đa trị, hiểu DN, chọn add/replace/remove phù hợp, xác thực kết nối qua TLS, giới hạn quyền của tài khoản bind và kiểm thử trên schema thật. Việc ánh xạ đúng là cơ sở để tìm kiếm, xác thực, cập nhật entry và tích hợp dữ liệu thư mục an toàn.

**Nguồn để tự tra cứu:** RFC 4512 (*LDAP: Directory Information Models*), RFC 4517 (*LDAP: Syntaxes and Matching Rules*), RFC 4519 (*LDAP: Schema for User Applications*), RFC 2798 (*Definition of the inetOrgPerson LDAP Object Class*) và tài liệu Spring LDAP về `LdapTemplate`, `LdapClient`, `LdapQueryBuilder`, `DirContextOperations` và ODM.
