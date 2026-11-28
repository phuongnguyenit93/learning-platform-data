# Xử lý thuộc tính vắng mặt, giá trị rỗng và giá trị không đúng kiểu

> **Chương:** Ánh xạ kết quả  
> **Module:** SPRING_DATA_LDAP — truy cập dịch vụ thư mục LDAP từ Java thông qua `LdapRepository`, `LdapTemplate` và mô hình ánh xạ entry phân cấp.

Kết quả trả về từ LDAP không phải lúc nào cũng chứa đầy đủ các thuộc tính mà mã Java mong đợi. Một entry có thể không khai báo `mail`, tài khoản bind không được phép đọc một trường, truy vấn chỉ yêu cầu một vài thuộc tính, hoặc dữ liệu từ directory có kiểu biểu diễn khác với giả định của chương trình. Chỉ một phép ép kiểu như `(String) attrs.get("mail").get()` cũng có thể gây `NullPointerException`, `ClassCastException` hoặc lỗi khi attribute không có phần tử.

Trong Spring Data LDAP, xử lý tốt dữ liệu đầu vào cần bắt đầu từ ba câu hỏi:

1. **Thuộc tính có được trả về không?** Không tìm thấy trong `Attributes` chưa đủ để khẳng định entry không lưu thuộc tính đó.
2. **Giá trị có hợp lệ với hợp đồng nghiệp vụ không?** `""`, `"   "`, một phần tử hoặc nhiều phần tử có thể mang ý nghĩa khác nhau.
3. **Kiểu dữ liệu Java có phù hợp không?** JNDI có thể cung cấp `String` hoặc `byte[]`; giá trị LDAP có cú pháp số, ngày hoặc DN không mặc nhiên trở thành `Integer`, `Instant` hay `Name`.

Bài này hướng dẫn phân loại trường hợp, viết `AttributesMapper` an toàn, kiểm thử bằng JNDI giả lập và directory thật, đồng thời xác định ranh giới giữa dữ liệu truy vấn và dữ liệu được phép ghi trở lại LDAP.

## 1. Bối cảnh: một entry có nhiều loại thuộc tính

Giả sử hệ thống nhân sự lưu entry theo schema `inetOrgPerson`:

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
telephoneNumber: +84 28 1234 5678
telephoneNumber: +84 90 111 2222
~~~

Trong một entry thuộc `inetOrgPerson`, `cn` và `sn` là những thuộc tính bắt buộc kế thừa từ `person`. Ngược lại, `mail` và `telephoneNumber` là ví dụ những thuộc tính tùy chọn được schema tương ứng cho phép. Một người dùng có thể không có email hoặc có nhiều số điện thoại.

Khi kết quả được chuyển sang Java, ứng dụng cần xác định:

| Thuộc tính | Hợp đồng Java ví dụ | Cách xử lý đề xuất |
|---|---|---|
| `uid` | Một chuỗi không rỗng, dùng làm khóa tìm kiếm trong nghiệp vụ | Kiểm tra có mặt, kiểu chuỗi và cardinality theo hợp đồng |
| `cn` | Một tên hiển thị trong DTO này | Kiểm tra dữ liệu hợp lệ; chú ý LDAP có thể cho nhiều giá trị |
| `sn` | Bắt buộc theo schema của entry | Khi ánh xạ entity đầy đủ, cần kiểm tra hoặc để server xác thực schema |
| `mail` | Có thể không được trả về | Biểu diễn trạng thái tùy chọn, không tự suy ra giá trị |
| `telephoneNumber` | Có thể có nhiều giá trị | Đọc tất cả phần tử, không chỉ `get()` |
| `jpegPhoto` | Nhị phân (nếu entry/schema chứa thuộc tính này) | Giữ dạng byte, không ép thành `String` |

**Chú ý:** lựa chọn “chỉ một `cn`” hoặc “chỉ một `uid`” trong DTO là **quy tắc của ứng dụng minh họa**, không phải khẳng định mọi directory đều định nghĩa chúng là single-valued. Nếu directory có nhiều giá trị được schema cho phép, ứng dụng phải thiết kế policy rõ ràng thay vì lấy phần tử đầu theo thứ tự bất kỳ.

## 2. Năm trạng thái không được đánh đồng

Tại tầng ứng dụng, có ít nhất năm trạng thái cần xét:

| Trạng thái | Ví dụ khi đọc bằng JNDI | Có thể kết luận gì? |
|---|---|---|
| **Không có attribute trong kết quả** | `attrs.get("mail") == null` | Không có trong phần dữ liệu trả về; chưa chắc entry không lưu |
| **Attribute tồn tại nhưng không có phần tử** | `attrs.get("mail").size() == 0` | Có thể gặp trong đối tượng `BasicAttributes` do test dựng; không mặc định đại diện cho entry hợp lệ ở server |
| **Có chuỗi độ dài 0** | `attr.get()` trả `""` | Một giá trị rỗng ở tầng Java; tính hợp lệ trong LDAP phụ thuộc syntax/schema/server |
| **Có chuỗi chỉ chứa khoảng trắng** | `"   "` | Không rỗng về độ dài, nhưng có thể vô nghĩa đối với trường nghiệp vụ |
| **Có giá trị sai kiểu** | Trả `byte[]` trong khi mapper ép `String` | Cần nhận diện binary hoặc báo lỗi kiểu thay vì ép tùy tiện |

Một trường hợp khác rất quan trọng: **attribute không được yêu cầu trong phép tìm kiếm**. Nếu truy vấn giới hạn `attributes("uid", "cn")`, thì `mail` không xuất hiện là điều dự kiến, ngay cả khi server lưu email và tài khoản bind có quyền đọc.

Đối với thuộc tính bị ACL che, kết quả cũng có thể thiếu trường đó. Vì vậy:

> **“Không có trong kết quả” khác “chắc chắn không tồn tại trên entry”.** Chỉ khi đã kiểm soát projection, quyền truy cập và hợp đồng tìm kiếm, mapper mới có đủ ngữ cảnh để quyết định cách xử lý trường vắng mặt.

### Phân biệt LDAP và Java

Trong Java, `null` là trạng thái của tham chiếu đối tượng. LDAP không coi một `null` Java là giá trị thuộc tính. Một attribute của LDAP về mặt dữ liệu có các giá trị theo syntax tương ứng; cách công cụ hoặc JNDI trình bày “không có giá trị” không đồng nghĩa với việc server lưu một giá trị `null`.

Ngoài ra, thuộc tính LDAP thường là một **tập các giá trị**, không nên dựa vào thứ tự liệt kê của một attribute đa giá trị để xác định “giá trị chính” nếu không có quy ước nghiệp vụ hoặc cấu trúc khác.

## 3. Luồng dữ liệu từ LDAP search đến đối tượng Java

~~~mermaid
flowchart TD
    A["LdapTemplate.search(...)"] --> B["LDAP SearchRequest<br/>base, scope, filter, attributes"]
    B --> C["Directory server<br/>schema, ACL, kết quả"]
    C --> D["JNDI Attributes"]
    D --> E{"Kiểm tra thuộc tính và giá trị"}
    E -->|Bắt buộc nhưng thiếu| F["Báo lỗi mapping / dữ liệu"]
    E -->|Tùy chọn vắng mặt| G["Optional.empty / chính sách mặc định"]
    E -->|Sai kiểu / sai cardinality| H["Báo lỗi rõ ràng"]
    E -->|Hợp lệ| I["DTO hoặc entity Java"]
    G --> I
~~~

Có hai lựa chọn ánh xạ thường gặp:

- **`AttributesMapper<T>`:** nhận một `javax.naming.directory.Attributes`, phù hợp để tạo DTO từ tập thuộc tính được yêu cầu.
- **ODM với `@Entry`:** Spring LDAP chuyển entry thành Java entity theo annotation; phù hợp với repository và thao tác CRUD nhưng vẫn chịu ràng buộc schema/kiểu dữ liệu thực tế.

Đối với bài toán xử lý null, blank và type mismatch một cách tường minh, `AttributesMapper` cho phép áp dụng chính sách cụ thể cho từng field mà không buộc mọi truy vấn phải tải và ánh xạ toàn bộ entity.

## 4. API JNDI cần biết: Attributes và Attribute

Spring LDAP dùng các kiểu JNDI trong Java:

~~~java
import javax.naming.NamingEnumeration;
import javax.naming.NamingException;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;
~~~

Những phương thức quan trọng:

| API | Công dụng | Rủi ro cần tránh |
|---|---|---|
| `attrs.get("mail")` | Lấy attribute theo tên | Có thể trả `null` |
| `attr.size()` | Đếm số phần tử được chứa | `0` không cho phép gọi `get()` an toàn |
| `attr.get()` | Lấy một giá trị | Không thay thế việc đọc mọi giá trị và có thể ném lỗi |
| `attr.getAll()` | Truy cập mọi giá trị | Phải duyệt và đóng `NamingEnumeration` |
| `attr.getID()` | Tên attribute JNDI trả về | Không dùng tên này để đoán kiểu Java |
| `attrs.getAll()` | Duyệt các attribute của kết quả | Dùng khi cần xử lý tập thuộc tính động |

Ví dụ code **dễ lỗi**:

~~~java
String mail = (String) attrs.get("mail").get();
~~~

Tình huống lỗi có thể xảy ra ngay cả khi LDAP server hoạt động tốt:

1. `attrs.get("mail")` trả `null` → gọi `get()` ném `NullPointerException`.
2. Mapper được test bằng `BasicAttribute` không có phần tử → gọi `get()` thất bại.
3. Giá trị trả là `byte[]` → ép trực tiếp sang `String` gây `ClassCastException`.
4. Thuộc tính có nhiều giá trị → `get()` chỉ chọn một phần tử; có thể làm mất dữ liệu.

Để tránh những lỗi đó, mapper nên phân nhánh rõ ràng **vắng mặt → cardinality → kiểu → giá trị nghiệp vụ**.

## 5. Thiết kế hợp đồng ánh xạ trước khi viết code

Giả sử chức năng tìm người dùng chỉ cần bốn trường:

~~~java
import java.util.List;
import java.util.Optional;

public record PersonSummary(
        String uid,
        String commonName,
        Optional<String> email,
        List<String> telephoneNumbers) {
}
~~~

Đây là DTO **chỉ đọc**. Hợp đồng của ví dụ:

- `uid` và `commonName` bắt buộc có đúng **một giá trị chuỗi không blank** trong dữ liệu được trả về.
- `email` là `Optional<String>`; khi attribute vắng mặt, biểu diễn bằng `Optional.empty()`.
- `telephoneNumbers` là danh sách; nếu không có attribute, trả danh sách rỗng, còn nếu có thì kiểm tra từng giá trị.
- Nếu một thuộc tính có kiểu sai hoặc cardinality trái hợp đồng, mapper **báo lỗi** thay vì âm thầm sửa.

Sử dụng `Optional` trong DTO giúp caller phải nhìn thấy trạng thái thiếu dữ liệu; không nhất thiết dùng `Optional` làm field trong mọi entity ODM hoặc làm kiểu trả về của mọi getter Java. Quyết định đó phụ thuộc framework mapping và mô hình ứng dụng.

**Điều cần thống nhất với nghiệp vụ:** liệu `email` có chuỗi `""` hoặc `"   "` có được xem là “không cung cấp” hay phải báo lỗi? Bài này chọn cách **chuẩn hóa blank thành `Optional.empty()` cho trường email tùy chọn**. Với `uid` và `commonName` bắt buộc, blank bị từ chối. Đây là chính sách ví dụ, không phải quy tắc chung cho tất cả thuộc tính LDAP.

## 6. Viết AttributesMapper kiểm tra dữ liệu tường minh

Lớp mapper dưới đây không cần truy cập directory để được kiểm thử đơn vị; nó chỉ nhận một đối tượng `Attributes` do JNDI cung cấp.

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;

import javax.naming.NamingEnumeration;
import javax.naming.NamingException;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;

import org.springframework.ldap.core.AttributesMapper;

public final class PersonSummaryMapper
        implements AttributesMapper<PersonSummary> {

    @Override
    public PersonSummary mapFromAttributes(Attributes attrs)
            throws NamingException {

        String uid = requiredOneText(attrs, "uid");
        String cn = requiredOneText(attrs, "cn");
        Optional<String> email = optionalOneText(attrs, "mail");
        List<String> phones = allTexts(attrs, "telephoneNumber");

        return new PersonSummary(uid, cn, email, phones);
    }

    private static String requiredOneText(
            Attributes attrs, String name) throws NamingException {

        Attribute attribute = attrs.get(name);
        if (attribute == null || attribute.size() == 0) {
            throw new IllegalStateException(
                    "Missing required LDAP attribute: " + name);
        }
        if (attribute.size() != 1) {
            throw new IllegalStateException(
                    "Expected exactly one LDAP value for: " + name);
        }

        String value = asString(attribute.get(), name);
        if (value.isBlank()) {
            throw new IllegalStateException(
                    "Blank required LDAP attribute: " + name);
        }
        return value;
    }

    private static Optional<String> optionalOneText(
            Attributes attrs, String name) throws NamingException {

        Attribute attribute = attrs.get(name);
        if (attribute == null || attribute.size() == 0) {
            return Optional.empty();
        }
        if (attribute.size() != 1) {
            throw new IllegalStateException(
                    "Expected at most one LDAP value for: " + name);
        }

        String value = asString(attribute.get(), name);
        return value.isBlank()
                ? Optional.empty()
                : Optional.of(value);
    }

    private static List<String> allTexts(
            Attributes attrs, String name) throws NamingException {

        Attribute attribute = attrs.get(name);
        if (attribute == null || attribute.size() == 0) {
            return List.of();
        }

        List<String> result = new ArrayList<>();
        NamingEnumeration<?> values = attribute.getAll();

        try {
            while (values.hasMore()) {
                String value = asString(values.next(), name);
                if (value.isBlank()) {
                    throw new IllegalStateException(
                            "Blank value in LDAP attribute: " + name);
                }
                result.add(value);
            }
        } finally {
            values.close();
        }

        return List.copyOf(result);
    }

    private static String asString(Object raw, String name) {
        if (raw instanceof String text) {
            return text;
        }
        String actualType = raw == null
                ? "null"
                : raw.getClass().getSimpleName();

        throw new IllegalStateException(
                "Expected LDAP String for " + name
                        + ", got " + actualType);
    }
}
~~~

### Vì sao mapper xử lý theo thứ tự đó?

**Bước 1 — kiểm tra attribute:** `attrs.get(name) == null` có thể là một thuộc tính không có trong projection; không thể gọi `get()`.

**Bước 2 — kiểm tra số giá trị:** một attribute có nhiều giá trị cần mô hình `List`/`Set` hoặc policy rõ ràng. Dùng `get()` mà không kiểm tra có thể làm mất dữ liệu, đặc biệt khi LDAP không bảo đảm thứ tự.

**Bước 3 — kiểm tra kiểu:** mapper không dùng `raw.toString()` như cách “chữa” sai kiểu, vì `byte[].toString()` chỉ cho tên kiểu và định danh object, không phải nội dung nhị phân.

**Bước 4 — áp dụng quy tắc blank:** `String.isBlank()` nhận diện cả chuỗi rỗng và chuỗi chỉ gồm khoảng trắng theo Unicode. Đối với giá trị mà khoảng trắng có ý nghĩa hợp lệ, không áp dụng quy tắc này máy móc.

**Bước 5 — trả DTO bất biến:** `List.copyOf(...)` giữ tập kết quả không bị caller chỉnh sửa vô tình. Nếu ứng dụng cần thứ tự, phải hiểu directory có bảo đảm thứ tự giá trị hay không; không suy thứ tự nghiệp vụ từ kết quả LDAP đa trị.

**Giới hạn của ví dụ:** code dùng cú pháp `record`, pattern matching với `instanceof` và `String.isBlank()` trên Java hiện đại (phù hợp Java 17+). Nếu dự án dùng Java cũ hơn, thay bằng class DTO và các phép kiểm tra tương thích.

## 7. Kết nối mapper với LdapTemplate.search

Một truy vấn Spring LDAP có thể chỉ yêu cầu các thuộc tính thật sự dùng cho DTO:

~~~java
import java.util.List;

import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.SearchScope;

import static org.springframework.ldap.query.LdapQueryBuilder.query;

public final class PersonLookupService {

    private final LdapTemplate ldapTemplate;

    public PersonLookupService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<PersonSummary> findByUid(String uid) {
        LdapQuery ldapQuery = query()
                .base("ou=people")
                .searchScope(SearchScope.SUBTREE)
                .attributes("uid", "cn", "mail", "telephoneNumber")
                .where("objectClass").is("inetOrgPerson")
                .and("uid").is(uid);

        return ldapTemplate.search(
                ldapQuery,
                new PersonSummaryMapper());
    }
}
~~~

Trong ví dụ này:

- `.base("ou=people")` là search base **tương đối** khi `ContextSource` đã cấu hình base DN, ví dụ `dc=example,dc=org`.
- `.attributes(...)` là projection có chủ đích. Vì mapper sử dụng bốn trường, truy vấn yêu cầu đủ bốn trường.
- `.where(...).and(...).is(uid)` xây dựng filter qua API, tránh nối chuỗi filter từ input tùy ý.
- `PersonSummaryMapper` chỉ xử lý entry đã khớp filter; mapper không tự kiểm soát search base, ACL hoặc schema.

Nếu hệ thống chuyển sang chỉ yêu cầu `attributes("uid", "cn")` nhưng vẫn giữ mapper cũ, `email=Optional.empty()` sẽ xuất hiện do **projection** chứ không có nghĩa người dùng không có email. Khi cần kết luận sự vắng mặt là dữ liệu thực, ứng dụng phải kiểm soát projection và quyền đọc hoặc thiết kế cơ chế chỉ báo “không có dữ liệu/không được cung cấp” rõ hơn.

**Một đặc điểm quan trọng:** `AttributesMapper` nhận các attribute, không mặc nhiên mang DN của entry để đưa vào DTO. Khi cần biết DN để lưu hoặc kiểm tra danh tính, sử dụng `ContextMapper<T>`/`DirContextOperations` hoặc cơ chế mapping ODM phù hợp, thay vì tự suy DN từ `uid`.

## 8. Thuộc tính vắng mặt: thiếu trên entry, không được đọc hay không được yêu cầu?

Ba nguyên nhân thường tạo cùng hiện tượng `attrs.get("mail") == null`:

~~~text
A. Entry thực sự không có mail.
B. Entry có mail nhưng SearchRequest không yêu cầu mail.
C. Entry có mail nhưng tài khoản bind không được phép đọc mail.
~~~

Tầng mapper chỉ quan sát được **kết quả được trả về**. Nó không thể tự biết nguyên nhân A/B/C nếu không nhận thêm ngữ cảnh.

### Mô hình xử lý theo mục đích sử dụng

| Chức năng | Cách xử lý thuộc tính vắng mặt |
|---|---|
| Danh sách nhân viên không hiển thị email | Không cần yêu cầu `mail` và không cần map field đó |
| Hồ sơ chi tiết cho phép email tùy chọn | Yêu cầu `mail`, dùng `Optional` hoặc nullable DTO theo hợp đồng |
| Đồng bộ dữ liệu cần phân biệt không có và không được đọc | Dùng service account/quyền phù hợp; ghi nhận projection và nguồn dữ liệu |
| Tính toán bắt buộc có mã định danh | Báo lỗi khi `uid` vắng mặt trong kết quả cần thiết |
| Cập nhật một phần entry | Không xem attribute thiếu trong DTO đọc là lệnh xóa thuộc tính trên server |

Nếu một nghiệp vụ bắt buộc phải có `mail`, có thể chuyển policy sang `requiredOneText(attrs, "mail")` sau khi xác minh schema và quyền. Tuy nhiên, không phải mọi `inetOrgPerson` đều bắt buộc có email, nên chính sách đó là **ràng buộc của nghiệp vụ**, không phải yêu cầu MUST của object class.

### Trạng thái “không biết” có thể cần biểu diễn riêng

Đối với hệ thống audit hoặc đồng bộ, `Optional.empty()` không đủ phân biệt “đã xác nhận không có” và “không được trả về”. Khi đó có thể dùng một kết quả ba trạng thái, chẳng hạn `Present(value)`, `AbsentConfirmed` và `UnknownNotFetched`, nhưng chỉ gán `AbsentConfirmed` khi đã có ngữ cảnh đáng tin cậy: projection có yêu cầu trường, account được cấp quyền, và chính sách server đủ rõ.

Đây là mô hình nghiệp vụ đề xuất; JNDI không tự phân biệt cả ba trạng thái chỉ bằng `attrs.get(name)`.

## 9. Chuỗi rỗng và khoảng trắng: chính sách không thể dùng chung cho mọi trường

Trong Java:

~~~java
"".isEmpty();       // true
"".isBlank();       // true
"   ".isEmpty();    // false
"   ".isBlank();    // true
"Lan".isBlank();    // false
~~~

Một giá trị `""` khác với “không có attribute trong kết quả”. Ở LDAP, attribute và giá trị phải tuân thủ syntax và ràng buộc schema; không phải mọi attribute type đều cho phép chuỗi có độ dài bằng 0. Một số directory có thể từ chối thao tác Add/Modify nếu giá trị rỗng không hợp lệ. `BasicAttributes` trong unit test có thể giữ giá trị mà server production sẽ không chấp nhận.

Ví dụ quy tắc xử lý phù hợp theo mục đích:

| Thuộc tính / dữ liệu | Khi gặp blank | Lý do |
|---|---|---|
| `uid` dùng làm identifier nghiệp vụ | Báo lỗi | Không dùng identifier vô nghĩa để truy vấn hoặc cập nhật |
| `cn` bắt buộc hiển thị | Báo lỗi hoặc chuyển sang chính sách fallback đã phê duyệt | Tránh hiển thị “tên” rỗng như dữ liệu hợp lệ |
| `mail` tùy chọn trong DTO hiển thị | Có thể chuyển thành không được cung cấp | Tránh hiển thị email chỉ có khoảng trắng |
| `telephoneNumber` | Tùy nghiệp vụ: báo lỗi hoặc loại qua quy trình làm sạch có audit | Không âm thầm làm mất dữ liệu khi đồng bộ |
| `description` | Có thể coi blank là nội dung do người dùng nhập | Khoảng trắng có thể liên quan trải nghiệm, cần policy riêng |
| Thuộc tính nhị phân | **Không áp dụng `isBlank()`** | Binary có quy tắc kích thước/định dạng khác |

Việc gọi `trim()`/`strip()` lên mọi dữ liệu cũng không phải chính sách an toàn mặc định. Với identifier, DN, password hoặc giá trị cần giữ nguyên byte, tự động chuẩn hóa có thể làm thay đổi ý nghĩa và phá khớp dữ liệu. Chỉ chuẩn hóa khi hợp đồng định nghĩa rõ.

## 10. Giá trị sai kiểu: String, byte[] và kiểu nghiệp vụ

LDAP mô tả giá trị theo **attribute syntax**. Ở lớp JNDI Java, dạng object trả về thường gặp là `String` hoặc `byte[]` tùy loại thuộc tính, cấu hình provider và cách dữ liệu được mã hóa.

Các suy đoán nguy hiểm:

~~~java
String photo = (String) attrs.get("jpegPhoto").get(); // Có thể sai kiểu
Integer number = (Integer) attrs.get("uidNumber").get(); // Thường sai
String value = attrs.get("jpegPhoto").get().toString();  // Không decode bytes
~~~

Thực tế cần phân biệt:

- `jpegPhoto` thường là dữ liệu nhị phân và nên xử lý bằng `byte[]`.
- `uidNumber` ở schema POSIX có ý nghĩa số nhưng JNDI LDAP thường đưa về **chuỗi ký tự**, không phải `Integer`. Hơn nữa, `uidNumber` không mặc nhiên thuộc `inetOrgPerson`; directory phải có schema/objectClass thích hợp.
- Thuộc tính thời gian như `createTimestamp` thường được trả theo biểu diễn **Generalized Time** của LDAP, không phải `java.time.Instant`. Đây có thể là operational attribute cần được yêu cầu tường minh và phụ thuộc quyền đọc.
- Thuộc tính chứa DN có thể được trả thành chuỗi biểu diễn DN; để xử lý cấu trúc DN, dùng API parser `LdapName` theo chính sách hợp lệ.

### Ví dụ đọc thuộc tính nhị phân

~~~java
import javax.naming.NamingException;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;

public final class BinaryAttributes {

    public static byte[] optionalPhoto(Attributes attrs)
            throws NamingException {

        Attribute attribute = attrs.get("jpegPhoto");
        if (attribute == null || attribute.size() == 0) {
            return null;
        }
        if (attribute.size() != 1) {
            throw new IllegalStateException(
                    "Unexpected jpegPhoto value count");
        }

        Object raw = attribute.get();
        if (!(raw instanceof byte[] bytes)) {
            throw new IllegalStateException(
                    "jpegPhoto must be returned as byte[]");
        }

        // Trả một bản sao để không giữ mutable array của provider.
        return bytes.clone();
    }
}
~~~

Nếu provider đưa thuộc tính dưới dạng không phải `byte[]`, cần kiểm tra cấu hình JNDI và cách chỉ định binary attributes của provider, thay vì gọi `toString()`. Chỉ giải mã bytes thành văn bản khi schema/encoding thực sự quy định dữ liệu là chuỗi.

Trong DTO production, có thể chọn kiểu `Optional<byte[]>` hoặc wrapper bất biến cho ảnh, nhưng cần lưu ý `byte[]` bản thân có thể bị sửa đổi; nên sao chép khi trao đổi dữ liệu ra ngoài.

### Ví dụ chuyển chuỗi LDAP sang kiểu số

Nếu một entry hợp lệ có `uidNumber` theo schema POSIX, ứng dụng có thể chuyển một giá trị chuỗi thành số:

~~~java
import javax.naming.NamingException;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;

public static int requiredUidNumber(Attributes attrs)
        throws NamingException {

    Attribute attribute = attrs.get("uidNumber");
    if (attribute == null || attribute.size() != 1) {
        throw new IllegalStateException(
                "uidNumber must have one value");
    }

    Object raw = attribute.get();
    if (!(raw instanceof String text)) {
        throw new IllegalStateException(
                "uidNumber must be returned as String");
    }

    try {
        return Integer.parseInt(text);
    } catch (NumberFormatException ex) {
        throw new IllegalStateException(
                "Invalid uidNumber syntax", ex);
    }
}
~~~

Đây là **phương thức minh họa** đặt trong một class utility của ứng dụng, không phải một file Java hoàn chỉnh với class bao ngoài. Khi triển khai, cần xác định giới hạn số và kiểu `int`/`long` phù hợp với dữ liệu thực tế; không giả định mọi giá trị LDAP số đều nằm trong phạm vi của `int`.

## 11. Dữ liệu nhiều giá trị: không gọi get() rồi bỏ qua phần còn lại

LDAP có những attribute có nhiều giá trị như `telephoneNumber`, `member` hoặc `objectClass`. Đoạn code:

~~~java
String phone = (String) attrs.get("telephoneNumber").get();
~~~

chỉ lấy **một** giá trị. Với hai số điện thoại trong LDIF ví dụ, ứng dụng có thể làm mất số còn lại nếu chuyển DTO sang một trường `String`.

Nên sử dụng `getAll()`, kiểm tra từng phần tử, rồi chọn collection phù hợp:

- `List<String>` nếu cần trình bày một danh sách nhưng **không được dựa vào thứ tự server trả về** như thứ tự ưu tiên.
- `Set<String>` nếu hợp đồng coi các giá trị là một tập hợp không thứ tự và cần tránh trùng ở tầng Java.
- Một object có thêm metadata nếu nghiệp vụ thực sự có số “chính”, “phụ”; metadata đó phải đến từ mô hình dữ liệu khác hoặc quy ước rõ ràng, không dựa vào vị trí `get()`.

`member` của `groupOfNames` chứa DN thành viên, có thể có nhiều giá trị. Mỗi giá trị cần parse/xác minh nếu ứng dụng xử lý DN, và phải tính đến trường hợp entry thành viên đã bị đổi tên/di chuyển.

### Giá trị trống trong collection

Nếu JNDI trả về một phần tử `""` trong attribute đa trị, hãy quyết định rõ: báo lỗi, bỏ qua có audit hay giữ nguyên. Mapper ở mục 6 chọn **báo lỗi** với `telephoneNumber` để tránh bỏ dữ liệu âm thầm.

Nếu `Attribute.size() == 0`, mapper trả danh sách rỗng. Đây là một nhánh xử lý phòng vệ ở tầng Java, không phải khẳng định server LDAP cho phép lưu mọi attribute với zero values.

## 12. Ánh xạ bằng @Entry và repository: chú ý dữ liệu chưa được tải

Spring Data LDAP hỗ trợ object-directory mapping với các annotation:

~~~java
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
public class DirectoryPerson {

    @Id
    private Name dn;

    @Attribute(name = "uid")
    private String uid;

    @Attribute(name = "cn")
    private String commonName;

    @Attribute(name = "sn")
    private String surname;

    @Attribute(name = "mail")
    private String mail;

    // Constructor và getter/setter tùy mô hình ứng dụng.
}
~~~

Repository có thể tìm theo thuộc tính Java:

~~~java
import java.util.List;
import org.springframework.data.ldap.repository.LdapRepository;

public interface DirectoryPersonRepository
        extends LdapRepository<DirectoryPerson> {

    List<DirectoryPerson> findByUid(String uid);
}
~~~

Những điều cần nhớ:

1. `@Attribute(name = "mail")` ánh xạ field Java tới thuộc tính LDAP; nó **không** đảm bảo thuộc tính đó hiện diện hoặc người dùng bind được phép đọc.
2. Một field Java `String` không thích hợp cho mọi attribute: binary, đa trị và kiểu được chuyển đổi có thể cần dạng Java khác.
3. Việc entity có `@Entry` và Java compile thành công **không** chứng minh schema server chấp nhận mọi attribute hay object class.
4. Nếu thư viện không chuyển được giá trị theo kiểu field, thao tác ánh xạ có thể ném ngoại lệ. Nên thiết kế kiểu field phù hợp và kiểm thử với entry thật.
5. Đối tượng entity phục vụ **ghi trở lại LDAP** phải được xử lý thận trọng khi một số trường không được tải. Không suy rằng field Java đang `null` là yêu cầu xóa attribute trên server.

### Vì sao DTO đọc và entity ghi nên tách khi cần?

Một màn hình tìm kiếm có thể chỉ nhận `uid` và `cn`. Nếu ánh xạ kết quả thiếu `mail` vào entity đầy đủ, rồi sửa tên và gọi `repository.save(...)`, chương trình có nguy cơ diễn giải dữ liệu **chưa được tải** như dữ liệu **cần xóa** hoặc ghi đè, tùy cơ chế update và mapping của phiên bản thư viện.

Không nên dựa vào giả định “field null sẽ luôn được bỏ qua” hay “field null sẽ luôn xóa attribute” mà chưa xác minh API thực tế. Với cập nhật một phần:

- Nên lấy entry đầy đủ theo phạm vi được phép rồi sửa rõ thuộc tính nghiệp vụ, hoặc
- Dùng `LdapTemplate.modifyAttributes(...)` với yêu cầu thay đổi có chủ đích,
- Và kiểm thử rõ **thuộc tính không được đề cập sẽ giữ nguyên**.

Phân biệt ba ý nghĩa trong API ghi: **không thay đổi**, **xóa attribute**, **gán giá trị mới**. Một DTO chỉ có `null` thường không diễn đạt đủ ba trạng thái này.

## 13. Bộ kiểm thử đơn vị với BasicAttributes

JNDI cung cấp `BasicAttributes` và `BasicAttribute` để dựng dữ liệu cho mapper mà không cần LDAP server. Điều này giúp kiểm tra các nhánh null, blank, sai kiểu và nhiều giá trị.

~~~java
import java.util.List;
import java.util.Optional;

import javax.naming.NamingException;
import javax.naming.directory.Attributes;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.BasicAttributes;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class PersonSummaryMapperTest {

    private final PersonSummaryMapper mapper =
            new PersonSummaryMapper();

    private Attributes validAttributes() {
        Attributes attrs = new BasicAttributes(true);
        attrs.put("uid", "lan");
        attrs.put("cn", "Tran Thi Lan");
        return attrs;
    }

    @Test
    void missingOptionalMailBecomesEmptyOptional()
            throws NamingException {

        PersonSummary person = mapper.mapFromAttributes(
                validAttributes());

        assertEquals(Optional.empty(), person.email());
        assertEquals(List.of(), person.telephoneNumbers());
    }

    @Test
    void blankOptionalMailFollowsDeclaredPolicy()
            throws NamingException {

        Attributes attrs = validAttributes();
        attrs.put("mail", "   ");

        assertEquals(
                Optional.empty(),
                mapper.mapFromAttributes(attrs).email());
    }

    @Test
    void missingRequiredUidIsRejected() {
        Attributes attrs = validAttributes();
        attrs.remove("uid");

        assertThrows(
                IllegalStateException.class,
                () -> mapper.mapFromAttributes(attrs));
    }

    @Test
    void wrongJavaTypeIsRejected() {
        Attributes attrs = validAttributes();
        attrs.put("cn", new byte[] { 1, 2, 3 });

        assertThrows(
                IllegalStateException.class,
                () -> mapper.mapFromAttributes(attrs));
    }

    @Test
    void allTelephoneNumbersArePreserved()
            throws NamingException {

        Attributes attrs = validAttributes();
        BasicAttribute phones =
                new BasicAttribute("telephoneNumber");
        phones.add("+84 28 1234 5678");
        phones.add("+84 90 111 2222");
        attrs.put(phones);

        PersonSummary person = mapper.mapFromAttributes(attrs);

        assertEquals(
                2,
                person.telephoneNumbers().size());
    }

    @Test
    void multipleValuesForSingleValueContractAreRejected() {
        Attributes attrs = validAttributes();
        BasicAttribute ids = new BasicAttribute("uid");
        ids.add("lan");
        ids.add("lan2");
        attrs.put(ids);

        assertThrows(
                IllegalStateException.class,
                () -> mapper.mapFromAttributes(attrs));
    }
}
~~~

`BasicAttributes(true)` tạo tập thuộc tính với tên không phân biệt chữ hoa/chữ thường, phù hợp để mô phỏng cách truy cập attribute ID của nhiều directory. Đây là kiểm thử logic Java; nó **không** chứng minh server chấp nhận entry, thực thi schema hay trả đúng kiểu trong mọi provider.

Một test nữa nên thêm là attribute tồn tại nhưng `size() == 0`:

~~~java
Attributes attrs = new BasicAttributes(true);
attrs.put("uid", "lan");
attrs.put("cn", "Tran Thi Lan");
attrs.put(new BasicAttribute("mail")); // Không có phần tử.

PersonSummary person = new PersonSummaryMapper()
        .mapFromAttributes(attrs);
// email: Optional.empty() theo policy của mapper.
~~~

Trường hợp này giúp kiểm tra mapper phòng vệ trước đối tượng Java do test dựng. Không suy ra rằng đây là cách server LDAP sẽ lưu thuộc tính `mail` khi không có giá trị.

## 14. Kiểm thử tích hợp với directory và schema thật

Unit test chỉ kiểm tra phương thức ánh xạ. Muốn xác minh dữ liệu thực tế phải dùng một **LDAP directory phục vụ test**, có schema, ACL và cấu trúc OU tương đương môi trường triển khai.

### Các kịch bản quan trọng

| Kịch bản | Bố trí trong LDAP test | Kỳ vọng |
|---|---|---|
| Thuộc tính tùy chọn vắng mặt | Entry `inetOrgPerson` hợp lệ không có `mail` | Mapper đọc được, email không được cung cấp |
| Thiếu thuộc tính MUST | Thử Add `inetOrgPerson` thiếu `sn` | Server từ chối theo schema nếu schema checking được bật |
| Chỉ đọc projection | Search chỉ yêu cầu `uid` và `cn` | `mail` không xuất hiện dù entry có thể lưu giá trị |
| Quyền đọc bị giới hạn | Bind account không có quyền đọc một thuộc tính | Kết quả phụ thuộc ACL; test không kết luận nhầm “không tồn tại” |
| Attribute đa giá trị | Entry có hai `telephoneNumber` | Mapper thu thập đủ phần tử, không phụ thuộc thứ tự |
| Giá trị binary | Entry có `jpegPhoto` hợp lệ và provider trả bytes | Xử lý bằng `byte[]` thay vì ép chuỗi |
| Syntax không hợp lệ | Thử ghi giá trị không hợp lệ với attribute type | Server từ chối theo luật schema/syntax |
| Kiểu số/thời gian | Entry có attribute theo schema phù hợp | Mapper parse đúng định dạng server trả |
| Cập nhật một phần | Tải DTO projection rồi sửa trường khác bằng quy trình được thiết kế | Không xóa nhầm thuộc tính chưa được tải |
| Đổi quyền bind | Đọc lại cùng entry bằng account quyền khác nhau | Xác nhận sự khác biệt không phải lỗi dữ liệu |

### Quy trình gợi ý

1. Tạo base DN `dc=example,dc=org` và `ou=people` trong test directory.
2. Nạp entry `inetOrgPerson` có `cn`/`sn`; thêm nhiều biến thể có/không có `mail` và hai số điện thoại.
3. Dùng `LdapTemplate.search(...)` với projection như mục 7.
4. Xác nhận mapper trả DTO phù hợp hợp đồng, kiểm tra cả dữ liệu vắng mặt và collection.
5. Thử tìm cùng entry với projection khác, ghi nhận thông tin nào chưa được yêu cầu.
6. Thử bind bằng account bị giới hạn quyền; không sử dụng tài khoản quản trị để suy luận account dịch vụ được đọc những gì.
7. Kiểm tra lỗi schema bằng dữ liệu test, không thử viết sai vào directory production.
8. Với binary và date, đối chiếu kiểu/encoding trả về ở JNDI trên provider thực tế.
9. Dọn fixture, đảm bảo test có thể chạy lại độc lập.

### Kiểm thử bắt đúng lỗi nơi phát sinh

Nếu LDAP server **từ chối Add/Modify** một attribute sai syntax, đó là lỗi đầu vào/schema ở server, chưa chắc mapper đã chạy. Nếu LDAP search thành công nhưng mapper nhận sai kiểu hoặc không đủ số giá trị, đó là lỗi dữ liệu/mapping ở tầng ứng dụng. Hai trường hợp cần phân loại rõ trong log và kiểm thử.

## 15. Lỗi phổ biến và chiến lược xử lý

| Triệu chứng | Khả năng gây ra | Cách giải quyết |
|---|---|---|
| `NullPointerException` khi đọc `mail` | `attrs.get("mail") == null` | Kiểm tra attribute tồn tại trước khi gọi `get()` |
| `ClassCastException` | Ép `byte[]` thành `String` | Kiểm tra kiểu và dùng mapper tương ứng |
| Không thấy email dù có trong directory | Projection không chọn `mail` hoặc ACL che | Xem `attributes(...)` và quyền bind |
| Chỉ có một trong nhiều số điện thoại | Dùng `get()` trên attribute đa trị | Dùng `getAll()` và collection |
| `NoSuchElementException`/lỗi lấy giá trị | Attribute không có phần tử | Kiểm tra `size()` |
| `NumberFormatException` | Giả định LDAP value là số hợp lệ cho kiểu Java đích | Parse có kiểm soát, kiểm tra range/syntax |
| Ngày parse lỗi | `Generalized Time` không phải chuỗi ISO-8601 thông thường | Dùng formatter/parser theo syntax thực |
| `objectClassViolation (65)` khi Add | Thiếu MUST hoặc attribute không được class cho phép | Kiểm tra objectClass, kế thừa schema |
| `invalidAttributeSyntax (21)` | Giá trị không đáp ứng cú pháp attribute | Xem attributeTypes và định dạng hợp lệ |
| Dữ liệu bị mất sau save | Ghi entity thiếu trường chưa tải hoặc diễn giải null sai | Thiết kế patch/update tường minh, test giữ nguyên thuộc tính khác |
| Ẩn lỗi bằng giá trị mặc định | Mapper dùng `""`/`0` thay cho dữ liệu bắt buộc sai | Báo lỗi rõ với thuộc tính required; chỉ default theo hợp đồng |
| Log lộ thông tin cá nhân | In toàn bộ `Attributes`/giá trị binary khi lỗi | Chỉ log tên trường và loại lỗi, giới hạn dữ liệu nhạy cảm |

Không nên “sửa” mọi tình huống bằng `try/catch (Exception) { return null; }`. Cách này xóa dấu vết của lỗi schema, mapping hoặc sai cấu hình, khiến caller không phân biệt được dữ liệu hợp lệ và lỗi hệ thống.

### Chọn chiến lược cho từng loại lỗi

- **Thuộc tính required thiếu hoặc blank:** ném ngoại lệ chuyên biệt để tầng dịch vụ xử lý, hoặc trả kết quả validation chứa tên field và mã lỗi.
- **Thuộc tính optional vắng mặt:** biểu diễn rõ trạng thái optional theo hợp đồng API; không bịa dữ liệu.
- **Kiểu Java không khớp:** dừng mapping hoặc áp dụng converter đã được định nghĩa; không tự ép bằng `toString()`.
- **Sai syntax trên server:** xem schema/encoding, không tắt schema validation để bỏ qua lỗi.
- **Kết quả không có quyền đọc:** kiểm tra ACL và projection; không coi tự động là entry không tồn tại.

## 16. Bảo mật khi ánh xạ kết quả LDAP

Ánh xạ dữ liệu không chỉ là xử lý exception. Một mapper có thể vô tình làm lộ thông tin nếu trả ra các thuộc tính quá rộng hoặc log toàn bộ entry.

Các nguyên tắc nên áp dụng:

1. **Chỉ yêu cầu thuộc tính cần thiết.** Dùng projection `attributes("uid", "cn", ...)` tương ứng với DTO; không yêu cầu `userPassword` hay thuộc tính nhạy cảm khi không dùng.
2. **Giới hạn search base và scope.** Một mapper đúng nhưng truy vấn quá rộng vẫn có thể trả dữ liệu của tenant/OU không được phép.
3. **Sử dụng API filter an toàn.** `LdapQueryBuilder` escape giá trị filter; DN phải được xây qua API xử lý DN thay vì ghép trực tiếp đầu vào.
4. **Áp dụng ACL tại directory.** Việc application không đọc một field trong code không thay cho quyền hạn chế tại server.
5. **Không in raw `Attributes` hoặc `byte[]`.** Khi lỗi chỉ ghi loại lỗi, tên attribute và mã trace thích hợp; tránh email, ảnh, mật khẩu và DN cá nhân không cần thiết.
6. **Giữ kết nối được bảo vệ.** Dùng LDAPS hoặc StartTLS với xác minh chứng chỉ; bảo vệ credential của service account.
7. **Phân biệt dữ liệu ẩn với dữ liệu không tồn tại.** Một giá trị bị che bởi ACL không được dùng để đưa ra quyết định ủy quyền thiếu căn cứ.
8. **Giới hạn kích thước binary và collection.** Nếu xử lý ảnh hoặc chứng chỉ lớn, thiết lập giới hạn nghiệp vụ và tránh cấp phát bộ nhớ không giới hạn từ dữ liệu ngoài.
9. **Cẩn trọng với dữ liệu đưa vào log/UI.** Giá trị LDAP vẫn là dữ liệu đầu vào: phải escape theo ngữ cảnh HTML, JSON, DN hoặc filter nếu đưa sang bề mặt khác.

**Đặc biệt:** không lấy một trường `mail` bị thiếu rồi gán giá trị mặc định như `admin@example.org` để hệ thống tiếp tục cấp quyền. Bản chất của “thiếu dữ liệu” cần được giữ nguyên trong các quyết định bảo mật.

## 17. Bài tập thực hành

**Bối cảnh:** ứng dụng Spring Data LDAP cung cấp API `GET /people?uid=...`. DTO trả `uid`, `cn`, `mail` và các số điện thoại. Directory có entry `inetOrgPerson`; một số nhân viên không có mail, một số có hai số điện thoại.

Hãy thực hiện:

1. Tạo entity/test fixture LDAP với `uid=lan`, `cn=Tran Thi Lan`, `sn=Tran` và hai `telephoneNumber`.
2. Viết `PersonSummary` và `PersonSummaryMapper`, chỉ định field required và optional.
3. Dùng `LdapTemplate.search(...)` với search base `ou=people`, filter `uid` qua builder và projection đủ bốn thuộc tính DTO.
4. Dựng `BasicAttributes` không có `mail`; xác minh `Optional.empty()`.
5. Tạo `BasicAttribute("mail")` không có phần tử, sau đó thêm giá trị `""`/`"   "`; so sánh các nhánh xử lý.
6. Thử bỏ `uid`; xác nhận mapper báo lỗi required.
7. Thay `cn` bằng `byte[]` trong unit test; xác minh lỗi sai kiểu không bị che giấu.
8. Thêm hai giá trị `telephoneNumber`; kiểm tra lấy đủ hai, không phụ thuộc thứ tự.
9. Thử entry nhị phân có `jpegPhoto`; bảo đảm ứng dụng nhận byte, không gọi `toString()` để biến ảnh thành text.
10. Tạo một entry trong LDAP test đúng schema nhưng thiếu `mail`; xác nhận kết quả khác với trường hợp projection cố ý bỏ qua mail.
11. Viết một phép cập nhật `mail` có chủ đích; xác nhận `telephoneNumber` và các thuộc tính không được đề cập vẫn giữ nguyên.
12. Đánh giá trường hợp account bị ACL che `mail`: API sẽ trả “không có email” hay “không được cung cấp” và có cần thay đổi hợp đồng không?

**Tiêu chí hoàn thành:** người học xử lý được thuộc tính thiếu, zero-value trong đối tượng Java, blank, sai kiểu, multi-value và binary; hiểu tại sao projection/ACL ảnh hưởng kết quả, đồng thời không làm mất dữ liệu khi thực hiện cập nhật một phần.

## 18. Ghi nhớ và tài liệu tham khảo

**Trong Spring Data LDAP, kết quả tìm kiếm là tập thuộc tính đã qua chọn lọc của LDAP server.** Không thấy một thuộc tính trong `Attributes` không đủ để kết luận entry không lưu nó. Một `AttributesMapper` tốt phải xác định rõ quy tắc cho thuộc tính bắt buộc, tùy chọn, chuỗi blank, sai kiểu và đa trị; khi dùng entity ODM để ghi lại, cần phân biệt **không được tải**, **không thay đổi** và **xóa**.

Một trình tự kiểm tra hữu ích là:

~~~text
Attribute có được trả về?
  -> Có bao nhiêu giá trị?
     -> Java type có phù hợp?
        -> Giá trị có đạt điều kiện nghiệp vụ?
           -> Trả DTO / báo lỗi rõ ràng
~~~

Nguồn tham khảo:

- [Spring LDAP Reference](https://docs.spring.io/spring-ldap/reference/): `LdapTemplate`, `AttributesMapper`, `ContextMapper`, tìm kiếm và xử lý kết quả.
- [Spring Data LDAP Reference](https://docs.spring.io/spring-data/ldap/reference/): ODM, `@Entry`, `@Attribute` và repository.
- [Java SE — javax.naming.directory.Attributes](https://docs.oracle.com/en/java/javase/17/docs/api/java.naming/javax/naming/directory/Attributes.html): tra cứu và duyệt attribute trong JNDI.
- [Java SE — javax.naming.directory.Attribute](https://docs.oracle.com/en/java/javase/17/docs/api/java.naming/javax/naming/directory/Attribute.html): `size()`, `get()`, `getAll()` và kiểu dữ liệu trả về.
- [RFC 4511 — LDAP: The Protocol](https://www.rfc-editor.org/rfc/rfc4511): SearchRequest, SearchResultEntry và attribute values.
- [RFC 4512 — LDAP: Directory Information Models](https://www.rfc-editor.org/rfc/rfc4512): objectClass, MUST/MAY và attribute type.
- [RFC 4517 — LDAP: Syntaxes and Matching Rules](https://www.rfc-editor.org/rfc/rfc4517): syntax/biểu diễn giá trị thuộc tính.
