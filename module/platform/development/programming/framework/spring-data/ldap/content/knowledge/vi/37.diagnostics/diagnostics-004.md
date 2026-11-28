# ODM ánh xạ thiếu thuộc tính hoặc không đọc được dữ liệu nhị phân

## 1. Tình huống: entry tồn tại nhưng đối tượng Java bị thiếu dữ liệu

Trong **Spring Data LDAP**, repository và `LdapTemplate` giúp ứng dụng Java tìm kiếm, đọc, sửa và ánh xạ entry của dịch vụ thư mục thành đối tượng Java. Một entry được xác định bằng **DN** (*Distinguished Name*), mang các thuộc tính theo `objectClass` và schema của LDAP server. Khi áp dụng **Object-Directory Mapping (ODM)** của Spring LDAP, lỗi không phải lúc nào cũng là “không tìm được entry”: có trường hợp entry đã được tìm thấy nhưng **một số trường trong object nhận `null`**, hoặc dữ liệu như ảnh `jpegPhoto` và chứng chỉ `userCertificate` không đọc được dưới dạng `byte[]`.

Ví dụ directory có entry:

~~~text
dn: uid=alice,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: alice
cn: Alice Nguyen
sn: Nguyen
mail: alice@example.org
jpegPhoto:: <dữ liệu Base64 của ảnh JPEG thử nghiệm>
~~~

Nhưng service Java lại nhận:

~~~text
dn       = uid=alice,ou=people
uid      = alice
fullName = null
email    = null
photo    = null
~~~

Không thể kết luận ngay rằng Spring LDAP có bug, ảnh bị hỏng hay dữ liệu đã bị xóa. Ta phải xác định **dữ liệu biến mất ở tầng nào**:

1. **LDAP server:** entry/thuộc tính có thực sự tồn tại, phù hợp schema, và tài khoản bind có được phép đọc không?
2. **Request LDAP:** base DN, scope, filter và danh sách thuộc tính yêu cầu có đúng không?
3. **JNDI LDAP provider:** giá trị được trả thành `String`, `byte[]` hay kiểu khác?
4. **Spring LDAP ODM:** annotation, tên trường, kiểu Java và conversion service có ánh xạ được giá trị không?
5. **Tầng ứng dụng:** DTO, JSON serializer, quyền hiển thị hoặc logic xử lý có vô tình bỏ trường không?

Bài học tập trung vào **chẩn đoán có bằng chứng** và sửa đúng tầng, tránh tắt TLS, mở rộng ACL hoặc thay đổi schema một cách mù quáng.

## 2. Phân biệt “không có entry”, “thiếu thuộc tính” và “sai kiểu”

| Triệu chứng | Bằng chứng khả dĩ | Ý nghĩa ban đầu |
| --- | --- | --- |
| `findByDn` không đọc được entry | DN sai hoặc lỗi `noSuchObject`/ACL/kết nối | Trước tiên kiểm tra DN và quyền đọc, chưa phải lỗi ánh xạ thuộc tính |
| Search trả danh sách rỗng | Filter/scope/base không khớp, server không cho search | Có thể không có entry khớp; chưa chứng minh thuộc tính bị thiếu |
| Raw LDAP trả entry nhưng không trả `mail` | Thuộc tính không tồn tại, không được yêu cầu hoặc bị ACL ẩn | Cần phân biệt ba nguyên nhân bằng request và quyền phù hợp |
| Raw LDAP có `cn`, object Java `fullName == null` | Tên ánh xạ `@Attribute`, conversion, projection | Nghi ngờ tầng ODM hoặc mapping |
| Raw LDAP có `jpegPhoto`, Java nhận `String` | JNDI coi thuộc tính là chuỗi, hoặc giá trị đã chuyển kiểu | Kiểm tra khai báo binary và LDAP provider |
| Raw LDAP có `byte[]`, entity `photo == null`/ném lỗi | Kiểu field không tương thích, `@Attribute` sai, converter thiếu | Kiểm tra mapping ODM |
| Entity có `byte[]`, response REST không có ảnh | DTO/serializer không đưa field ra, API cố ý ẩn dữ liệu | Lỗi ở tầng ứng dụng, không phải LDAP |
| Một server đọc được nhưng server khác không | Schema, ACL, replication, directory vendor hoặc connection khác | So sánh từng endpoint và bind identity |

**Quy tắc:** Khi cùng một thuộc tính không đọc được, đối chiếu **cùng DN, cùng server, cùng tài khoản bind, cùng thời điểm và cùng danh sách thuộc tính** ở từng tầng. So sánh kết quả từ tài khoản admin với ứng dụng read-only chỉ để phát hiện **khác biệt ACL**, không lấy quyền admin làm chuẩn hoạt động cho production.

## 3. Preflight: khóa chặt DN, base, schema và account

Giả sử Spring Boot cấu hình:

~~~yaml
spring:
  ldap:
    urls: "ldaps://ldap.example.org:636"
    base: "dc=example,dc=org"
    username: "${LDAP_BIND_DN}"
    password: "${LDAP_BIND_PASSWORD}"
~~~

Với cấu hình này, ứng dụng thường truyền DN **tương đối** cho `LdapTemplate`:

~~~text
uid=alice,ou=people
~~~

DN đầy đủ trên server là:

~~~text
uid=alice,ou=people,dc=example,dc=org
~~~

Đọc entry sai DN, hoặc đưa DN đầy đủ vào API đã tự cộng base, có thể dẫn tới tìm sai nơi hoặc lỗi `NameNotFoundException`. Nếu tập kết quả thiếu người dùng, kiểm tra:

- **Base DN:** ứng dụng có đang nhìn vào `ou=people` hay một OU khác?
- **Search scope:** `ONELEVEL` chỉ gồm con trực tiếp; `SUBTREE` gồm mọi cấp dưới.
- **Filter:** `(&(objectClass=inetOrgPerson)(uid=alice))` có khớp entry thực tế không?
- **`objectClass`:** entry có đủ lớp mà `@Entry` của ODM yêu cầu không? Có lớp vendor bổ sung không?
- **Schema:** thuộc tính `mail`, `jpegPhoto`, `userCertificate` có được định nghĩa và cho phép trên loại entry đó không?
- **ACL:** service account có được phép *search*, *read* và đọc chính thuộc tính đang cần không?
- **Replica:** sau khi ghi, ứng dụng có đang đọc một replica chưa đồng bộ không?

Nếu lỗi chỉ xảy ra với một trường mà các trường khác của cùng entry vẫn đúng, ưu tiên kiểm tra **thuộc tính được trả về và mapping**, thay vì đổi connection pool hay sửa DN trên diện rộng.

## 4. Tầng 1: chứng minh LDAP server đang trả gì

### 4.1. `ldapsearch` với đúng DN và account

Dùng công cụ có thể gửi LDAP Search thực tế, chẳng hạn OpenLDAP `ldapsearch`:

~~~bash
ldapsearch -LLL -x \
  -H ldaps://ldap.example.org:636 \
  -D "uid=app-reader,ou=service-accounts,dc=example,dc=org" -W \
  -b "uid=alice,ou=people,dc=example,dc=org" \
  -s base "(objectClass=*)" \
  dn objectClass uid cn sn mail jpegPhoto userCertificate
~~~

Lệnh trên dùng `-W` để nhập mật khẩu qua prompt và **LDAPS** với chứng chỉ server phải được xác minh. Đừng đưa mật khẩu trực tiếp vào `-w` hoặc lệnh được lưu trong CI log. Output của `ldapsearch` có thể chứa dữ liệu cá nhân và ảnh/chứng chỉ; chỉ chạy với danh tính kiểm thử được cấp phép, và không đăng nguyên output lên hệ thống issue công khai.

Cần phân biệt:

- Có entry và có `mail: alice@example.org`: server trả giá trị text.
- Có `jpegPhoto:: /9j/...`: LDIF biểu diễn dữ liệu nhị phân bằng **Base64**, dấu `::` là cú pháp LDIF; chưa phải chuỗi JPEG của Java.
- Không thấy `jpegPhoto`: có thể entry không lưu ảnh, ACL không trả, tên attribute không khớp hoặc yêu cầu không được đáp ứng.
- Server trả lỗi: ghi nhận **result code** và thông tin kết nối/bind để tiếp tục chẩn đoán, không coi đó là “không có ảnh”.

**Nhắc lại:** phần `jpegPhoto:: ...` là cách *hiển thị* bytes trong LDIF, không chứng minh JNDI đã chuyển bytes thành `String`.

### 4.2. `*`, `+` và danh sách thuộc tính cụ thể

LDAP Search có thể yêu cầu các thuộc tính theo những cách khác nhau:

| Yêu cầu | Ý nghĩa thực tế |
| --- | --- |
| `cn mail jpegPhoto` | Xin trả chính xác các thuộc tính này, nếu có và ACL cho phép |
| `*` | Xin các thuộc tính **user attributes** thông thường |
| `+` | Xin các **operational attributes** (LDAPv3) như `modifyTimestamp`, tùy server |
| `1.1` | **Không yêu cầu thuộc tính nào**; thường dùng để chỉ kiểm tra có entry khớp |
| `dn` trong công cụ `ldapsearch` | Hiển thị DN của entry; DN nằm ngoài tập thuộc tính được ánh xạ thông thường |

Nếu gọi Search bằng `setReturningAttributes(new String[]{"uid","cn"})`, server **không được yêu cầu trả `mail` hoặc `jpegPhoto`**. Entity lấy từ kết quả chỉ có dữ liệu mà thao tác Search đã cấp cho mapper; đừng kết luận các thuộc tính chưa được yêu cầu là “LDAP server đã làm mất dữ liệu”.

Thuộc tính vận hành như `modifyTimestamp` thường không tự xuất hiện trong kết quả mặc định, và có thể được cấu hình là chỉ đọc. Khi cần nó để chẩn đoán, yêu cầu rõ ràng và kiểm tra ACL; không coi timestamp luôn sẵn có hay là phiên bản có thể khóa lạc quan trên mọi server.

### 4.3. Kiểm chứng bằng nhiều tài khoản mà không phá nguyên tắc quyền tối thiểu

Khi service account không đọc được `jpegPhoto` nhưng tài khoản quản trị đọc được:

1. Ghi lại DN, endpoint và filter giống nhau.
2. Thử `ldapsearch` bằng hai danh tính trong **môi trường được phép**; tránh hiển thị raw binary.
3. Đối chiếu ACL trên **thuộc tính cần đọc**, không chỉ quyền search trên OU.
4. Nếu nghiệp vụ thật sự cần ảnh, đề xuất cấp quyền đọc **tối thiểu** cho đúng nhánh/thuộc tính.
5. Không đổi ứng dụng sang bind bằng admin chỉ để “sửa” trường `null`.

Ngược lại, nếu cả admin cũng không thấy attribute, phải xác minh **giá trị có tồn tại**, có được nhập vào đúng entry, có bị replication trễ và schema của server có cho phép không.

## 5. Tầng 2: kiểm tra kiểu dữ liệu JNDI nhận được

Spring LDAP dựa trên **JNDI LDAP provider**. Ở tầng này, các giá trị của `javax.naming.directory.Attributes` có thể là `String` hoặc `byte[]`, tùy **schema/encoding và cách provider phân loại attribute**.

Điều này đặc biệt quan trọng với:

- `jpegPhoto`: thường là byte JPEG.
- `userCertificate` hoặc `userCertificate;binary`: dữ liệu certificate dạng DER, cách biểu diễn và option phụ thuộc schema/server/provider.
- Thuộc tính binary tùy biến (`customBinaryData`, `employeeBlob`, ...) theo schema nội bộ.
- Thuộc tính đa trị chứa nhiều dữ liệu binary, không thể mặc định mỗi attribute chỉ có một giá trị.

### 5.1. Đọc raw entry bằng `LdapTemplate.lookup`

Ví dụ Java 17+, dùng `LdapTemplate` đã có `ContextSource` với base `dc=example,dc=org`:

~~~java
import javax.naming.Name;
import javax.naming.directory.Attribute;
import javax.naming.ldap.LdapName;

import org.springframework.ldap.core.LdapTemplate;

public final class RawAttributeDiagnostics {

    private final LdapTemplate ldapTemplate;

    public RawAttributeDiagnostics(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public record Snapshot(
        boolean mailReturned,
        boolean photoReturned,
        String rawType,
        Integer photoBytes
    ) {}

    public Snapshot inspectAlice() throws Exception {
        Name dn = new LdapName("uid=alice,ou=people");

        return ldapTemplate.lookup(
            dn,
            new String[] {"objectClass", "cn", "mail", "jpegPhoto"},
            attrs -> {
                Attribute mail = attrs.get("mail");
                Attribute photo = attrs.get("jpegPhoto");

                if (photo == null || photo.size() == 0) {
                    return new Snapshot(mail != null, false, null, null);
                }

                Object raw = photo.get();
                String type = raw == null
                    ? "null"
                    : raw.getClass().getName();

                Integer length = raw instanceof byte[] bytes
                    ? bytes.length
                    : null;

                // Chỉ trả metadata: không log ảnh, DN nhạy cảm, Base64.
                return new Snapshot(
                    mail != null, true, type, length
                );
            }
        );
    }
}
~~~

Ví dụ quan sát (không phải kết quả cố định):

~~~text
Snapshot[mailReturned=true, photoReturned=true,
         rawType=[B, photoBytes=18422]
~~~

`[B` là tên lớp runtime của **`byte[]`** trong Java. Nếu `rawType=java.lang.String`, cần kiểm tra xem provider đã nhận attribute dưới dạng chuỗi hay cấu hình/cách trả response khác mong đợi.

**Không gọi** `(byte[]) photo.get()` trước khi kiểm tra kiểu vì có thể ném `ClassCastException`. Đồng thời, `photo == null` chỉ có nghĩa **attribute không có trong kết quả lookup này**; không đủ để chứng minh attribute không tồn tại ở server.

`AttributesMapper` giúp kiểm tra kiểu raw mà **chưa qua ODM**. Nếu raw đã đúng `byte[]`, lỗi chuyển đổi tiếp theo nhiều khả năng nằm ở annotation, Java field hoặc bộ converter. Nếu raw là `String`, cần kiểm tra tầng JNDI/provider trước.

### 5.2. Cách kiểm tra thuộc tính đa trị

Với attribute có thể chứa nhiều giá trị, `attribute.get()` chỉ lấy **một** giá trị. Để kiểm tra số phần tử:

~~~java
Attribute value = attrs.get("customBinaryData");
if (value != null) {
    int count = value.size();
    for (int i = 0; i < count; i++) {
        Object item = value.get(i);
        // Ghi metadata count và item.getClass(), không ghi nội dung.
    }
}
~~~

Đoạn mã là minh họa **bên trong một `AttributesMapper`**, nơi biến `attrs` đang được cung cấp. Không chọn `String`/`byte[]` field đơn trị nếu schema thực sự trả nhiều giá trị mà nghiệp vụ phải giữ nguyên; có thể cần collection và converter phù hợp.

## 6. Tầng 3: sửa mapping Spring LDAP ODM

### 6.1. Annotation đúng package và tên LDAP attribute

Spring LDAP ODM dùng annotation thuộc package `org.springframework.ldap.odm.annotations`:

- `@Entry`: khai báo `objectClass` và base cho entity.
- `@Id`: trỏ tới DN, trường phải có kiểu `javax.naming.Name` hoặc kiểu triển khai.
- `@Attribute`: ánh xạ field Java tới LDAP attribute.
- `@DnAttribute`: lấy giá trị thành phần DN, không có nghĩa bỏ ánh xạ thuộc tính.
- `@Transient`: bỏ qua field khi ODM map/persist.

**Chú ý:** Import `org.springframework.ldap.odm.annotations.Id`, **không phải** `org.springframework.data.annotation.Id` hoặc `jakarta.persistence.Id` cho entity ODM.

Mặc định, field Java không đánh dấu `@Transient` có thể được ODM ánh xạ theo **chính tên field**. Vì vậy `private String fullName;` sẽ không tự biết nó phải đọc từ LDAP `cn`. Muốn ánh xạ khác tên, dùng:

~~~java
@Attribute(name = "cn")
private String fullName;
~~~

`@Entry(objectClasses=...)` cần khớp các lớp thuộc entry và các thuộc tính được quản lý. Với `inetOrgPerson`, nên kiểm tra chuỗi lớp `top`, `person`, `organizationalPerson`, `inetOrgPerson` của entry thực; nếu server dùng thêm lớp vendor/auxiliary class, kiểm tra tác động lên ODM và schema thay vì giảm filter một cách mù quáng.

### 6.2. Entity có attribute text và binary

~~~java
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

    @Attribute(name = "mail")
    private String email;

    @Attribute(
        name = "jpegPhoto",
        type = Attribute.Type.BINARY
    )
    private byte[] photo;

    @Attribute(name = "modifyTimestamp", readonly = true)
    private String modifyTimestamp;

    @Transient
    private String displayLabel;

    public PersonEntry() {}

    public Name getDn() { return dn; }
    public void setDn(Name value) { dn = value; }

    public String getUid() { return uid; }
    public void setUid(String value) { uid = value; }

    public String getFullName() { return fullName; }
    public void setFullName(String value) { fullName = value; }

    public String getEmail() { return email; }
    public void setEmail(String value) { email = value; }

    public byte[] getPhoto() { return photo; }
    public void setPhoto(byte[] value) { photo = value; }

    public String getModifyTimestamp() { return modifyTimestamp; }
    public void setModifyTimestamp(String value) {
        modifyTimestamp = value;
    }
}
~~~

Những chi tiết cần ghi nhớ:

- `@Attribute(name = "jpegPhoto", type = Attribute.Type.BINARY)` cho ODM biết trường phải được coi là **binary**. `Attribute.Type.BINARY` nói tới giá trị JNDI `byte[]`, không phải chuỗi Base64.
- `private byte[] photo` giữ dữ liệu raw. **Không** khai báo `String photo` chỉ vì `ldapsearch` hiển thị `jpegPhoto:: ...`.
- `@Attribute(name = "modifyTimestamp", readonly = true)` giúp tránh ghi trả một thuộc tính chỉ đọc khi update entity; bản thân annotation không cấp thêm quyền đọc hoặc buộc server trả timestamp.
- `@Transient` ngăn một field ứng dụng không có trong directory bị ODM coi như LDAP attribute.
- Field `sn` không có trong ví dụ vì bài chỉ tập trung đọc; **khi tạo mới** `inetOrgPerson`, schema thông thường vẫn yêu cầu `sn` và `cn`, do đó phải bổ sung dữ liệu bắt buộc nếu dùng entity này để tạo mới.
- Nếu ứng dụng dùng repository `save`/`update`, hãy xem xét đầy đủ các field được ánh xạ để không vô ý xóa hoặc ghi đè dữ liệu từ một entity chỉ được load một phần.

**Để đọc binary**, không cần tạo một entity riêng cho từng giá trị ảnh; nhưng nếu mỗi người có nhiều ảnh (nếu schema cho phép) hoặc attribute dùng loại dữ liệu tùy biến, cần mapping và conversion tương thích với **cấu trúc đa trị**.

### 6.3. Đối chiếu hai cách đọc trên cùng DN

Ví dụ với `LdapTemplate`:

~~~java
import javax.naming.Name;
import javax.naming.ldap.LdapName;
import org.springframework.ldap.core.LdapTemplate;

public class PersonOdmDiagnostics {

    private final LdapTemplate ldapTemplate;

    public PersonOdmDiagnostics(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public PersonEntry loadAlice() throws Exception {
        Name dn = new LdapName("uid=alice,ou=people");
        return ldapTemplate.findByDn(dn, PersonEntry.class);
    }
}
~~~

So sánh trạng thái:

| Kết quả `lookup` raw | Kết quả `findByDn` ODM | Vùng cần điều tra |
| --- | --- | --- |
| Có `mail`, có `cn` | `email` và `fullName` có giá trị | Mapping text hoạt động |
| Có `cn` | `fullName == null` | Tên field, `@Attribute(name="cn")`, converter, entity class |
| Có `jpegPhoto` kiểu `byte[]` | `photo == null` | `@Attribute(type=BINARY)`, tên attribute, field type, converter |
| Có `jpegPhoto` kiểu `String` | `photo` lỗi hoặc `null` | JNDI phân loại binary, attribute option, schema |
| Không có `jpegPhoto` raw | ODM không có `photo` | Chưa thể quy lỗi cho ODM; quay lại request/server/ACL |
| Raw đọc đúng server A, ODM truy vấn server B | Kết quả khác nhau | Endpoint, replica, bind account, base DN phải thống nhất |

Không bắt toàn bộ lỗi rồi trả `null`: `ClassCastException`, lỗi converter, `NameNotFoundException`, từ chối quyền và lỗi TLS có ý nghĩa khác nhau.

## 7. Vì sao `Attribute.Type.BINARY` chưa đủ trong mọi trường hợp?

Theo Spring LDAP, `@Attribute(type = BINARY)` xác định trường được xem là binary khi mapping. Tuy nhiên, **JNDI LDAP provider phải nhận biết thuộc tính là binary** để trả `byte[]`. Với một số thuộc tính chuẩn, provider thường biết trước; với attribute tùy biến, việc phân loại có thể cần cấu hình bổ sung.

JNDI LDAP provider của JDK hỗ trợ environment property:

~~~text
java.naming.ldap.attributes.binary
~~~

Giá trị là danh sách tên attribute mà provider phải coi là binary. Cách áp dụng phụ thuộc vào **provider và cấu hình `ContextSource` thực tế**.

Ví dụ phác thảo tại nơi ứng dụng **tự cấu hình** `LdapContextSource`:

~~~java
import java.util.HashMap;
import java.util.Map;

import org.springframework.ldap.core.support.LdapContextSource;

// Chỉ là phần cấu hình binary của một ContextSource đang được xây dựng.
// url/base/bind DN/password và lifecycle bean phải được thiết lập riêng.
LdapContextSource contextSource = new LdapContextSource();

Map<String, Object> jndiProperties = new HashMap<>();
jndiProperties.put(
    "java.naming.ldap.attributes.binary",
    "customBinaryData"
);

contextSource.setBaseEnvironmentProperties(jndiProperties);
~~~

**Lưu ý:** Đây là đoạn cấu hình **minh họa**, không phải bean hoàn chỉnh. Nếu Spring Boot đã auto-configure `ContextSource`, việc tạo một instance khác trong test không làm thay đổi bean ứng dụng đang dùng. Hãy áp dụng property tại đúng `ContextSource` và kiểm tra sau khi khởi tạo, với dependency/version thực tế. Tránh ghi đè các environment properties khác có sẵn.

Trong một số directory, tên attribute trả về có **option** như `userCertificate;binary`. Việc server có trả về tên kèm option và JNDI có nhận biết nó hay không phụ thuộc schema/provider. Khi raw `attrs.get("userCertificate")` trả `null`, hãy **kiểm tra các attribute IDs thực tế** được trả về, không mặc định thêm `;binary` cho mọi thuộc tính:

~~~java
import javax.naming.NamingEnumeration;
import javax.naming.directory.Attribute;

NamingEnumeration<? extends Attribute> all = attrs.getAll();
while (all.hasMore()) {
    Attribute attribute = all.next();
    String id = attribute.getID();
    // Chỉ ghi tên thuộc tính và loại dữ liệu, không ghi nội dung.
}
~~~

Đoạn này chạy bên trong `AttributesMapper` hoặc logic có sẵn `Attributes attrs`. Nếu muốn map certificate DER, cần bảo đảm tên LDAP attribute, option, cú pháp và field Java `byte[]` hoặc converter đã được thử trực tiếp với server.

**Không sửa schema** hoặc đổi dữ liệu nhị phân thành text chỉ vì một client không hiểu cách trả giá trị. Hãy xác định **kiểu dữ liệu thực sự** và chuẩn LDAP tương ứng.

## 8. Khi nào cần conversion service tùy chỉnh?

Không phải attribute nào cũng là `String` hoặc `byte[]` đơn giản trong mô hình nghiệp vụ. Ví dụ:

- Một attribute DER muốn chuyển sang `X509Certificate`.
- Một attribute binary chứa payload chuyên biệt của doanh nghiệp cần giải mã thành cấu trúc Java.
- Một tập giá trị binary có thể cần `List<byte[]>` hoặc tập đối tượng tùy chỉnh.

Spring LDAP ODM có khả năng sử dụng `ConversionService` với các `Converter` do ứng dụng cung cấp (cách đăng ký phụ thuộc Spring Boot/Spring LDAP version). Trước khi viết converter, **chứng minh raw type** và kiểm tra annotation/field type; nếu raw đã là `byte[]` và field cũng là `byte[]` thì thường không cần thêm conversion tầng nghiệp vụ.

Ví dụ chuyển **DER certificate bytes** thành đối tượng X.509 trong lớp service, **không** tự động thực hiện trong mọi mapping LDAP:

~~~java
import java.io.ByteArrayInputStream;
import java.security.cert.CertificateFactory;
import java.security.cert.X509Certificate;

public final class CertificateParser {

    public static X509Certificate fromDer(byte[] der) throws Exception {
        if (der == null || der.length == 0) {
            throw new IllegalArgumentException("Thiếu dữ liệu certificate");
        }

        CertificateFactory factory = CertificateFactory.getInstance("X.509");
        return (X509Certificate) factory.generateCertificate(
            new ByteArrayInputStream(der)
        );
    }
}
~~~

Lưu ý phân biệt:

- **Certificate trong thuộc tính `userCertificate`** là dữ liệu directory mà ứng dụng được phép đọc.
- **Truststore của JVM dùng xác minh TLS với LDAP server** là một cấu hình bảo mật khác. Đọc được một `userCertificate` **không** có nghĩa Java tự tin cậy certificate đó.
- Một giá trị DER parse được chưa chứng minh nó đáng tin cậy; xác thực PKIX/CA/hostname là quy trình riêng khi certificate được dùng làm chứng cứ bảo mật.

Với ảnh JPEG, `byte[]` là dữ liệu gốc; nếu ứng dụng cần kiểm tra định dạng, có thể dùng thư viện đọc ảnh ở tầng service nhưng phải giới hạn **kích thước, định dạng, thời gian xử lý và bộ nhớ**. Không hiển thị trực tiếp dữ liệu nhận từ directory thành HTML không kiểm soát.

## 9. Những lỗi mapping khác có thể làm trường thành `null`

### 9.1. Field Java và LDAP attribute có tên khác nhau

~~~java
// Sai khi directory chỉ có thuộc tính cn:
private String fullName;

// Đúng mapping:
@Attribute(name = "cn")
private String fullName;
~~~

Tên attribute LDAP thường không phân biệt hoa/thường theo quy tắc schema; **tên field Java vẫn phải được ánh xạ đúng**. Không suy đoán `displayName`, `fullName`, `commonName` là alias của `cn` khi schema không quy định.

### 9.2. `@Entry.objectClasses` hoặc `base` không phù hợp

Nếu entry có `inetOrgPerson`, `organizationalPerson`, `person`, `top`, trong khi `@Entry` khai báo lớp không đúng hoặc ánh xạ một lớp thuộc tính không tương ứng, ODM có thể không tìm được entry/mapping như kỳ vọng. Đối chiếu **`objectClass` raw của entry**, không chỉ nhìn tên class Java.

Nếu base trên entity đã là `ou=people` và `ContextSource` có base `dc=example,dc=org`, kiểm tra cách library kết hợp chúng. Không đưa `dc=example,dc=org` lặp lại vào các API mong DN tương đối.

### 9.3. `@DnAttribute`, `@Transient` và ID

`@DnAttribute` có thể lấy dữ liệu từ RDN, ví dụ `uid=alice`, ngay cả khi cách đọc attribute thông thường khác. Nó **không tự loại field khỏi ánh xạ LDAP attribute**. Nếu muốn một field chỉ là thành phần tính toán hoặc không persistent, cân nhắc `@Transient` đúng mục đích.

`@Id` phải giữ DN kiểu `javax.naming.Name` và dùng annotation Spring LDAP ODM. Nếu nhầm với `@Id` của JPA hoặc Spring Data Commons, entity LDAP có thể không map đúng danh tính.

### 9.4. Tập kết quả bị cắt do projection/attribute selection

Khi dùng API `lookup(..., String[] attrs, mapper)` hay `SearchControls.setReturningAttributes(...)`, một mapper chỉ thấy **các trường được server trả cho request đó**. Nếu danh sách chỉ là `uid`, `cn`, việc thiếu `jpegPhoto` trong object không chứng minh ODM hỏng.

Với truy vấn repository/ODM, hãy kiểm tra khả năng attribute projection của đường truy vấn đang dùng và so sánh với `LdapTemplate.lookup` raw. Tránh dùng một entity **chưa load đầy đủ** để `save/update` khi có nguy cơ ghi đè những thuộc tính không được tải.

### 9.5. Dữ liệu đa trị, các loại số/ngày và converter

Không mặc định một giá trị LDAP có thể cast sang mọi kiểu Java tương ứng. Ví dụ, server có thể trả `String` cho một giá trị timestamp dạng Generalized Time; cần converter trước khi gán vào `Instant`. Với thuộc tính đa trị như `member`/`uniqueMember`, dùng collection tương ứng, không lấy phần tử đầu tiên rồi cho rằng đó là toàn bộ dữ liệu.

## 10. Quy trình chẩn đoán có thể lặp lại

Có thể áp dụng quy trình sau cho **bất cứ field nào bị null hoặc bị sai kiểu**:

~~~mermaid
flowchart TD
    A["Lỗi: field ODM null / binary đọc sai"] --> B["Khóa DN, server, bind identity"]
    B --> C["ldapsearch tại đúng DN và attribute"]
    C --> D{"Raw LDAP có attribute?"}
    D -->|Không| E["Kiểm tra entry, schema, ACL, replication, search attrs"]
    D -->|Có| F["LdapTemplate.lookup nhận giá trị và raw type"]
    F --> G{"Raw JNDI là byte[] như kỳ vọng?"}
    G -->|Không| H["Kiểm tra JNDI binary config, attribute option, provider"]
    G -->|Có| I["Đọc qua ODM findByDn / repository"]
    I --> J{"Entity có dữ liệu?"}
    J -->|Không| K["Kiểm tra @Entry, @Attribute, @Id, field type, converter"]
    J -->|Có| L["Kiểm tra DTO, serializer, phân quyền hiển thị"]
~~~

### Checklist chẩn đoán

1. Ghi lại **tên lỗi, môi trường, phiên bản Spring LDAP/JDK, endpoint LDAP**, không ghi secret.
2. Xác minh **DN đầy đủ**, base cấu hình và đúng `objectClass`.
3. Dùng `ldapsearch -s base` với **cùng bind identity** để đọc đúng attribute.
4. Kiểm tra **attribute selection**; `*` cho user attrs, `+` cho operational attrs; lưu ý quyền của server.
5. Dùng `LdapTemplate.lookup` raw để đo **presence, runtime class, byte length**.
6. Nếu binary raw sai kiểu, kiểm tra `Attribute.Type.BINARY`, tùy chỉnh JNDI binary property khi cần, và tên attribute có option.
7. Nếu raw đúng nhưng ODM sai, sửa `@Entry`, `@Attribute`, `@Id`, `@Transient`, field type và converter.
8. Nếu ODM đúng nhưng API sai, kiểm tra DTO mapping, JSON serializer, response policy và nơi che dữ liệu nhạy cảm.
9. Kiểm thử lại trên **directory test có schema và ACL tương ứng**.
10. Chỉ deploy thay đổi sau khi đã chứng minh sửa đúng nguyên nhân; theo dõi regression của các thuộc tính khác.

### Bảng lỗi và hướng xử lý nhanh

| Dấu hiệu | Nguyên nhân có thể | Bước kiểm tra đúng |
| --- | --- | --- |
| `mail == null` nhưng `uid` đúng | Không có `mail`, ACL, thiếu `@Attribute` hoặc request không xin `mail` | Đọc `mail` bằng raw `ldapsearch` và `lookup` |
| `fullName == null` trong khi raw có `cn` | Field khác tên LDAP attribute | `@Attribute(name="cn")` |
| `ClassCastException: String cannot be cast to byte[]` | JNDI trả text hoặc cast sai | Log raw class, kiểm tra `Type.BINARY` và cấu hình provider |
| Conversion exception | Converter không hỗ trợ raw Java type → field | Kiểm tra `raw.getClass()`, `ConversionService`, field type |
| `jpegPhoto` có trong LDIF nhưng không ở LDAP | Import lỗi, schema từ chối hoặc đang đọc server khác | Kiểm tra kết quả import và truy vấn tại đúng DN/endpoint |
| Đọc raw được bằng admin nhưng service không đọc được | ACL thuộc tính/entry | Kiểm tra quyền tối thiểu và bind identity |
| Không thấy `modifyTimestamp` | Operational attribute không được yêu cầu/ACL | Yêu cầu `+` hoặc tên attribute cụ thể |
| `userCertificate` raw null, có `userCertificate;binary` | Attribute option khác | Liệt kê attribute IDs thực trả về |
| Entity có `byte[]`, REST trả không có ảnh | Field bị ẩn trong DTO/serializer | Kiểm tra tầng API, không sửa LDAP |
| Mapping được trên embedded, lỗi trên production | Khác schema, ACL, provider hoặc attribute options | Test trên container/ directory tương đương production |
| Photo quá lớn gây chậm/OOM | Tải nhị phân trong truy vấn danh sách | Tách truy vấn ảnh theo DN; giới hạn kích thước |
| Sau ghi không thấy dữ liệu mới | Replication delay/đọc replica khác | Đọc cùng server ghi, kiểm tra độ trễ và topology |

## 11. Kiểm thử hồi quy trước khi chốt sửa lỗi

Một test có ý nghĩa phải chứng minh **raw LDAP** và **ODM** nhất quán. Dùng LDAP embedded hoặc container được chuẩn bị với schema và quyền gần giống hệ thống thật.

### 11.1. Seed ảnh thử và certificate thử đúng định dạng

Với LDIF, dữ liệu binary được mã hóa Base64:

~~~ldif
dn: uid=alice,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: alice
cn: Alice Nguyen
sn: Nguyen
jpegPhoto:: <BASE64_CUA_ANH_JPEG_GIA_DUNG_TRONG_TEST>
~~~

Đoạn trên là **minh họa cú pháp**, không phải fixture LDIF có thể import nguyên văn: thay placeholder bằng Base64 được tạo từ một file JPEG **hợp lệ dùng cho test** và tuân thủ cách xuống dòng/folding của RFC 2849. Không đưa ảnh người dùng thật vào source kiểm thử.

Ví dụ tạo Base64 trong Java:

~~~java
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Base64;

byte[] jpegBytes = Files.readAllBytes(Path.of("src/test/resources/sample.jpg"));
String base64 = Base64.getEncoder().encodeToString(jpegBytes);

// Khi tạo LDIF thật, cần fold dòng theo cú pháp RFC 2849.
String attributeLine = "jpegPhoto:: " + base64;
~~~

Đây là code minh họa chạy **trong dự án ví dụ của người học**, không phải lệnh tạo file trong workspace đang biên soạn. Test với ảnh hợp lệ, kích thước nhỏ và không nhạy cảm. Tránh chèn certificate/private key thật vào LDIF fixture.

### 11.2. Test raw trước, ODM sau

~~~java
import java.util.List;
import javax.naming.ldap.LdapName;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.ldap.core.LdapTemplate;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class BinaryOdmIntegrationTest {

    @Autowired
    LdapTemplate ldapTemplate;

    @Test
    void rawAndOdmHaveSamePhotoBytes() throws Exception {
        LdapName dn = new LdapName("uid=alice,ou=people");

        byte[] fromRaw = ldapTemplate.lookup(
            dn,
            new String[] {"jpegPhoto"},
            attrs -> {
                var photo = attrs.get("jpegPhoto");
                assertThat(photo).isNotNull();
                Object value = photo.get();
                assertThat(value).isInstanceOf(byte[].class);
                return (byte[]) value;
            }
        );

        PersonEntry entity = ldapTemplate.findByDn(dn, PersonEntry.class);

        assertThat(entity).isNotNull();
        assertThat(entity.getPhoto()).isNotNull();
        assertThat(entity.getPhoto()).isEqualTo(fromRaw);
        assertThat(entity.getPhoto()).hasSize(fromRaw.length);
    }

    @Test
    void absentOptionalPhotoDoesNotBreakTextFields() throws Exception {
        LdapName dn = new LdapName("uid=bob,ou=people");
        PersonEntry entity = ldapTemplate.findByDn(dn, PersonEntry.class);

        assertThat(entity).isNotNull();
        assertThat(entity.getUid()).isEqualTo("bob");
        assertThat(entity.getPhoto()).isNull();
    }
}
~~~

Trước khi chạy, fixture cần có `uid=alice` với `jpegPhoto` hợp lệ, `uid=bob` **không có ảnh**, và `ContextSource.base=dc=example,dc=org`. Các test phải chạy với quyền LDAP cho phép đọc ảnh. Nếu schema/vendor không dùng `jpegPhoto`, điều chỉnh fixture và mapping đúng thuộc tính được cấp phép.

Với dữ liệu ảnh lớn, không load tất cả photos trong `findAll()` nếu chỉ cần danh sách người dùng. Ưu tiên truy vấn các trường text, rồi đọc ảnh theo **DN được phép** khi thực sự có yêu cầu.

### 11.3. Các case nên có trong CI

| Ca kiểm thử | Kỳ vọng |
| --- | --- |
| Entry có đủ text + ảnh | Đọc được `cn`, `mail` và `byte[]` giống raw |
| Entry không có `mail`/`jpegPhoto` | Mapper không ném NPE; trường tùy chọn vắng mặt xử lý hợp lý |
| User bind thiếu quyền đọc ảnh | Ảnh không bị lộ; ứng dụng tuân thủ ACL và không giả dữ liệu |
| Thuộc tính đa trị | Không mất phần tử, converter/collection xử lý đúng |
| `userCertificate;binary` khi server hỗ trợ | Kiểm tra tên attribute + bytes DER trả về |
| Entity được đọc bằng `findByDn` và `repository.findById` | Quy ước DN và ODM mapping nhất quán |
| Sai `objectClass` / schema | Test báo lỗi/không match rõ ràng |
| Tài khoản test ghi cập nhật `mail` | Không vô tình ghi đè hoặc xóa `jpegPhoto` |
| Chuyển server/JDK khác | Mapping binary không phụ thuộc giả định riêng môi trường |
| TLS không tin CA hoặc hostname sai | Bị từ chối, không tắt xác thực để test xanh |

**Không** chỉ mock `LdapTemplate` rồi assert field có giá trị: mock không chứng minh được JNDI binary classification, cách server trả attribute, ACL hay schema.

## 12. Bảo mật, khả năng vận hành và tối ưu

- **Bảo vệ dữ liệu:** `jpegPhoto`, certificate và các thuộc tính cá nhân có thể nhạy cảm. Không log raw bytes, Base64, toàn bộ `Attributes` hoặc private key. Chỉ ghi presence, runtime class, kích thước và mã lỗi cần thiết trong môi trường có quyền kiểm tra.
- **Bảo đảm TLS:** dùng LDAPS hoặc StartTLS, xác minh certificate và hostname, không bật `TrustManager` chấp nhận tất cả chỉ để đọc ảnh.
- **Giới hạn truy vấn:** Search theo base DN/scope nhỏ, giới hạn count/time và thuộc tính trả về. Không yêu cầu `jpegPhoto` trong trang danh sách nếu không hiển thị ảnh.
- **Không thay đổi schema vội vàng:** mismatch giữa field Java và attribute phải xử lý ở mapper/provider nếu schema đúng; thêm objectClass/attribute vào production cần được phê duyệt.
- **Không bỏ qua ACL:** nếu tài khoản ứng dụng không được phép đọc ảnh thì kết quả không có ảnh có thể là **đúng chính sách**; không dùng admin account thay thế.
- **Cẩn thận khi `save` entity thiếu dữ liệu:** ánh xạ một phần không phải phép cập nhật một field an toàn mặc định. Đọc đủ entry hoặc dùng `LdapTemplate.modifyAttributes` với `ModificationItem` nhắm đúng thuộc tính cần sửa.
- **Theo dõi hiệu năng:** đo latency và dung lượng khi truy vấn binary; với tập dữ liệu lớn, tách endpoint lấy ảnh/certificate theo DN và giới hạn quyền, kích thước, caching theo chính sách.
- **Không suy luận thất bại từ `null` duy nhất:** bao gồm DN, endpoint, code LDAP, loại thao tác và ACL trong chẩn đoán để tránh sửa sai tầng.

## 13. Câu hỏi tự kiểm tra

1. Một entry đã được `findByDn`, `uid` đúng nhưng `fullName == null`. Vì sao nên đọc raw `cn` trước khi sửa Java class?
2. `@Attribute(name="cn")` và `@DnAttribute("uid")` giải quyết hai nhu cầu khác nhau như thế nào?
3. Vì sao `ldapsearch` in `jpegPhoto:: <Base64>` không có nghĩa nên khai báo `String photo`?
4. Với raw `attrs.get("jpegPhoto").get()` trả `java.lang.String`, cần xem xét những nguyên nhân nào trước khi cast sang `byte[]`?
5. `@Attribute(type = Attribute.Type.BINARY)` dùng cho mục đích gì? Khi nào cần thêm `java.naming.ldap.attributes.binary` ở JNDI provider?
6. Làm thế nào phân biệt **không có attribute** với **attribute không được trả** do projection hoặc ACL?
7. Vì sao cần xem các ID thực tế trong `Attributes` khi xử lý `userCertificate;binary`?
8. Khi raw JNDI đã trả `byte[]` đúng nhưng entity ODM còn `null`, đâu là các vị trí nên kiểm tra?
9. Vì sao `@Attribute(readonly = true)` không tự cấp quyền đọc `modifyTimestamp`?
10. Nếu entity có ảnh nhưng REST API trả JSON không có trường ảnh, tại sao không nên sửa LDAP server?
11. Vì sao không nên dùng `save(...)` ngay trên entity chỉ được load hai thuộc tính khi entry có nhiều thuộc tính khác?
12. Hãy mô tả một integration test giúp phát hiện lỗi dữ liệu binary bị đổi kiểu khi nâng JDK hoặc đổi LDAP server.

## 14. Tổng kết

Khi **ODM ánh xạ thiếu thuộc tính hoặc không đọc được dữ liệu nhị phân**, cách xử lý đáng tin cậy nhất là **đối chiếu từng tầng**: directory có trả thuộc tính hay không → request có yêu cầu đúng attribute không → JNDI trả `String` hay `byte[]` → ODM có dùng đúng annotation, tên field và converter không → tầng ứng dụng có giữ dữ liệu không.

Với text field, `@Attribute(name=...)` và `@Entry` thường là điểm cần kiểm tra; với dữ liệu binary như `jpegPhoto`, sử dụng `@Attribute(type=Attribute.Type.BINARY)` và trường `byte[]`, đồng thời xác minh JNDI provider đã nhận biết binary attribute. Không dùng Base64 xuất từ `ldapsearch` làm kiểu Java mặc định và không mở rộng ACL khi chưa có nhu cầu nghiệp vụ được phê duyệt.

Hãy xác nhận bằng **integration test raw-vs-ODM trên một LDAP server có schema/ACL tương ứng**, sau đó mới triển khai thay đổi. Cách tiếp cận này giúp chẩn đoán đúng nguyên nhân, giảm mất dữ liệu và giữ an toàn cho truy vấn repository, `LdapTemplate` và các chức năng CRUD trong Spring Data LDAP.

### Tài liệu tham khảo

- [Spring LDAP Reference — Object-Directory Mapping (ODM)](https://docs.spring.io/spring-ldap/reference/odm.html).
- [Spring LDAP API — `@Attribute` và `Attribute.Type.BINARY`](https://docs.spring.io/spring-ldap/reference/4.2-SNAPSHOT/api/java/org/springframework/ldap/odm/annotations/Attribute.html).
- [Spring LDAP API — `LdapTemplate`](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/LdapTemplate.html).
- [Oracle JNDI/LDAP Service Provider — `java.naming.ldap.attributes.binary`](https://docs.oracle.com/javase/7/docs/technotes/guides/jndi/jndi-ldap.html).
- [RFC 4511 — Lightweight Directory Access Protocol (LDAP): The Protocol](https://www.rfc-editor.org/rfc/rfc4511).
- [RFC 4512 — LDAP Directory Information Models](https://www.rfc-editor.org/rfc/rfc4512).
- [RFC 2849 — LDAP Data Interchange Format (LDIF)](https://www.rfc-editor.org/rfc/rfc2849).
