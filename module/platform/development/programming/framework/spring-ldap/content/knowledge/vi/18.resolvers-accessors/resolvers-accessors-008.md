# Phân biệt accessor của Spring LDAP với accessor của SpEL

## Mục tiêu học tập

Trong hệ sinh thái Spring, từ **accessor** thường chỉ một cơ chế **đọc hoặc ghi dữ liệu**, nhưng ý nghĩa cụ thể phụ thuộc lớp đang xử lý. Với **Spring LDAP**, ứng dụng truy cập các thuộc tính của **LDAP entry** thông qua `DirContextOperations`, `DirContextAdapter`, `AttributesMapper` hoặc `ContextMapper`. Với **Spring Expression Language (SpEL)**, `PropertyAccessor` là một điểm mở rộng dùng để giải quyết cách đọc/ghi **property trong biểu thức**.

Bài học thuộc chương **Resolver và accessor**, giúp bạn:

1. Phân biệt **LDAP attribute** với **Java object property** và vị trí của từng accessor trong luồng xử lý.
2. Đọc thuộc tính LDAP bằng `LdapTemplate.lookupContext(...)` và `getStringAttribute(...)`; hiểu giới hạn khi attribute có nhiều giá trị.
3. Đọc property JavaBean bằng SpEL, sử dụng `PropertyAccessor`/`EvaluationContext` đúng mục đích.
4. Ánh xạ dữ liệu LDAP thành DTO rồi sử dụng SpEL khi thực sự cần, tránh cho biểu thức truy cập LDAP ngoài ý muốn.
5. Nhận diện sự khác nhau về lỗi, kiểu dữ liệu, phân quyền và bảo mật giữa hai cơ chế.

Các ví dụ dựa trên **Spring LDAP**, kết hợp `ContextSource`, DN, schema và `LdapTemplate`. Điều tương tự cũng áp dụng khi lớp truy cập thư mục dùng `LdapClient` hoặc ODM: tầng truy cập LDAP và tầng đánh giá biểu thức là hai trách nhiệm riêng.

## 1. Cùng gọi là accessor, nhưng truy cập những gì?

Giả sử directory có một entry:

~~~ldif
dn: uid=lan,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: lan
cn: Lan Tran
sn: Tran
mail: lan@example.org
telephoneNumber: +84 28 3822 0000
telephoneNumber: +84 90 111 2222
~~~

Ứng dụng có thể cần lấy `cn` để hiển thị tên, `mail` để gửi thông báo, hoặc đọc nhiều số `telephoneNumber`. **Accessor của Spring LDAP** hoạt động trên dữ liệu attribute mà LDAP server đã trả về.

Sau khi ánh xạ, ứng dụng có thể sở hữu một đối tượng Java:

~~~java
public final class PersonView {
    private final String displayName;
    private final String email;

    public PersonView(String displayName, String email) {
        this.displayName = displayName;
        this.email = email;
    }

    public String getDisplayName() {
        return displayName;
    }

    public String getEmail() {
        return email;
    }
}
~~~

Khi một biểu thức SpEL đọc property `displayName` của đối tượng đó, **accessor của SpEL** sẽ giải quyết biểu thức dựa trên đối tượng và các quy tắc truy cập property của `EvaluationContext`.

Hai lời gọi sau nhìn tương tự nhưng có ý nghĩa khác nhau:

~~~java
// 1. LDAP: tìm attribute có tên "cn" trong dữ liệu của entry.
String cn = entry.getStringAttribute("cn");

// 2. SpEL: đánh giá property "displayName" của một Java object.
String name = expression.getValue(
    evaluationContext, personView, String.class
);
~~~

Ở ví dụ 2, `expression` là biểu thức đã parse từ `"displayName"`. SpEL có thể gọi getter `getDisplayName()` của JavaBean; nó **không tự truy vấn LDAP** để tìm `cn`.

### Bảng so sánh

| Tiêu chí | Accessor kiểu Spring LDAP | Accessor của SpEL |
| --- | --- | --- |
| Dữ liệu đầu vào | LDAP entry, `Attributes`, `DirContextOperations` | Root object/biến trong `EvaluationContext` |
| Đơn vị truy cập | LDAP **attribute** theo tên, có thể nhiều giá trị | JavaBean/Map/object **property** trong biểu thức |
| API điển hình | `getStringAttribute("cn")`, `getStringAttributes("mail")` | `Expression.getValue(...)`, SPI `PropertyAccessor` |
| Nơi quyết định dữ liệu có tồn tại | LDAP server, DN, filter, schema và ACL | Đối tượng Java, accessor được cấu hình, expression |
| Giao tiếp mạng | Có thể xảy ra khi `LdapTemplate` thực hiện lookup/search | Đánh giá property thông thường không tự tạo LDAP request |
| Quy tắc kiểu dữ liệu | LDAP syntax và mapper Java | Kiểu Java, converter và evaluator |
| Ghi dữ liệu | `setAttributeValue(...)` rồi `modifyAttributes(...)`, hoặc modify trực tiếp | Có thể dùng `setValue(...)` nếu context/accessor cho ghi |
| Lỗi điển hình | Không có DN, quyền, schema, kết nối, mapper | Sai property, biểu thức sai, không có quyền truy cập property |
| Mục đích chính | Làm việc với directory | Đánh giá biểu thức trên object/context |

**Điểm mấu chốt:** Cùng tên *accessor* không có nghĩa hai API dùng chung cơ chế hay tự ánh xạ tên thuộc tính qua lại.

## 2. Accessor ở phía Spring LDAP

Spring LDAP cung cấp các phương thức truy cập attribute qua `DirContextOperations`, thường là kết quả từ `LdapTemplate.lookupContext(...)`. Dữ liệu này có thể được triển khai bởi `DirContextAdapter`, lớp thích ứng với JNDI và duy trì trạng thái attribute khi cần cập nhật.

Một số thao tác thường dùng:

| Phương thức | Mục đích |
| --- | --- |
| `getStringAttribute("cn")` | Lấy giá trị chuỗi đơn của attribute, khi phù hợp |
| `getStringAttributes("telephoneNumber")` | Lấy nhiều giá trị chuỗi |
| `getObjectAttribute("jpegPhoto")` | Truy cập giá trị ở dạng object, cần kiểm tra kiểu thực tế |
| `setAttributeValue("description", value)` | Đặt giá trị mới trên đối tượng context |
| `setAttributeValues("telephoneNumber", values)` | Đặt toàn bộ danh sách giá trị trên context |
| `ldapTemplate.modifyAttributes(context)` | Gửi các thay đổi của context trở lại LDAP server |

Các phương thức getter chỉ đọc dữ liệu **đã được LDAP trả về** trong đối tượng context. Chúng không tự cấp thêm quyền, không bỏ qua ACL và không chuyển `cn` thành property JavaBean tên `displayName`.

### 2.1. Đọc một entry theo DN

Giả sử `ContextSource` đã cấu hình base DN `dc=example,dc=org`. Đoạn mã sau dùng DN tương đối `uid=lan,ou=people`.

~~~java
import javax.naming.Name;

import org.springframework.ldap.core.DirContextOperations;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

Name dn = LdapNameBuilder.newInstance()
    .add("ou", "people")
    .add("uid", "lan")
    .build();

DirContextOperations entry = ldapTemplate.lookupContext(dn);

String cn = entry.getStringAttribute("cn");
String mail = entry.getStringAttribute("mail");
String[] phones = entry.getStringAttributes("telephoneNumber");
~~~

Ở đây:

- `LdapTemplate.lookupContext(dn)` dùng kết nối LDAP từ `ContextSource` để tra cứu entry.
- `DirContextOperations` đóng vai trò **đại diện cho một entry và các attribute đã nhận**.
- `getStringAttribute(...)` và `getStringAttributes(...)` đọc dữ liệu từ đại diện đó.
- Nếu DN không tồn tại, lỗi xuất hiện tại lookup (ví dụ `org.springframework.ldap.NameNotFoundException`), trước khi đọc attribute.
- Nếu entry tồn tại nhưng thiếu `mail`, getter có thể trả `null`; đây là tình huống khác với việc **DN không tồn tại**.

Không dùng `getStringAttribute(...)` để suy ra thứ tự hoặc lựa chọn chuẩn của một attribute **nhiều giá trị**. Đối với `telephoneNumber`, hãy dùng `getStringAttributes(...)` và xử lý các giá trị như một tập, trừ khi schema/nghiệp vụ xác định rõ khác đi.

### 2.2. Đọc dữ liệu qua mapper

Trong truy vấn nhiều entry, Spring LDAP thường ánh xạ từng kết quả tìm kiếm thành một object ứng dụng. Hai giao diện phổ biến:

- **`AttributesMapper<T>`:** ánh xạ `javax.naming.directory.Attributes` của một entry.
- **`ContextMapper<T>`:** ánh xạ context kết quả, cho phép truy cập `DirContextOperations` khi adapter thích hợp được dùng.

Ví dụ lấy những tên hiển thị, dùng `AttributesMapper`:

~~~java
import java.util.List;

import javax.naming.directory.Attribute;

import org.springframework.ldap.core.AttributesMapper;

// ldapTemplate là bean đã cấu hình.
List<String> displayNames = ldapTemplate.search(
    "ou=people",
    "(objectClass=inetOrgPerson)",
    (AttributesMapper<String>) attrs -> {
        Attribute cn = attrs.get("cn");
        return cn == null ? null : (String) cn.get();
    }
);
~~~

Ví dụ ánh xạ entry sang DTO bằng `ContextMapper`:

~~~java
import java.util.List;

import org.springframework.ldap.core.ContextMapper;
import org.springframework.ldap.core.DirContextOperations;

List<PersonView> people = ldapTemplate.search(
    "ou=people",
    "(objectClass=inetOrgPerson)",
    (ContextMapper<PersonView>) ctx -> {
        DirContextOperations entry = (DirContextOperations) ctx;
        return new PersonView(
            entry.getStringAttribute("cn"),
            entry.getStringAttribute("mail")
        );
    }
);
~~~

`PersonView` là JavaBean ở phần trước. Việc ánh xạ từ LDAP `cn` sang property `displayName` là **quyết định của lập trình viên**; Spring không tự đặt hai tên này tương đương.

Nên dùng `AttributesMapper` khi chỉ cần các attribute trả về; dùng `ContextMapper` khi cần thông tin context hoặc các thao tác mà `DirContextOperations` cung cấp.

### 2.3. Ghi attribute không giống ghi property trong SpEL

Ví dụ cập nhật `description`:

~~~java
DirContextOperations entry = ldapTemplate.lookupContext(dn);
entry.setAttributeValue("description", "Active employee");

// Gửi thay đổi cho LDAP server.
ldapTemplate.modifyAttributes(entry);
~~~

`setAttributeValue(...)` thay đổi dữ liệu mà adapter quản lý; nó **không có nghĩa LDAP server đã được cập nhật ngay lập tức**. Lệnh `modifyAttributes(...)` thực hiện phần ghi vào directory, chịu kiểm tra schema, ACL và tình trạng kết nối.

Với SpEL, gọi setter trên JavaBean có thể chỉ thay đổi trạng thái **object Java trong bộ nhớ**. Ngay cả khi object này được tạo từ LDAP, một lệnh SpEL `setValue(...)` không tự động gọi `LdapTemplate.modifyAttributes(...)`.

## 3. Accessor ở phía SpEL

**SpEL** là ngôn ngữ biểu thức của Spring Framework. Ví dụ biểu thức:

~~~text
displayName
email
address.city
contacts[0]
['cn']
~~~

Ý nghĩa của chúng phụ thuộc **root object** và các accessor/indexer được cấu hình trong `EvaluationContext`. Trong SpEL, **`org.springframework.expression.PropertyAccessor`** là SPI (giao diện mở rộng) cho phép bộ máy biểu thức biết một property có thể đọc/ghi hay không và cách thực hiện.

Một `PropertyAccessor` có các trách nhiệm như:

- `canRead(context, target, name)`: xác định có thể đọc property hay không.
- `read(context, target, name)`: đọc và trả `TypedValue`.
- `canWrite(context, target, name)`: xác định có thể ghi hay không.
- `write(context, target, name, newValue)`: thực hiện ghi nếu được phép.
- `getSpecificTargetClasses()`: có thể giới hạn loại đối tượng mà accessor hỗ trợ.

SpEL có cơ chế truy cập phản chiếu đối với JavaBean qua `ReflectivePropertyAccessor` trong `StandardEvaluationContext`. Đây là **property accessor ở tầng biểu thức**, khác với phương thức đọc LDAP attribute của `DirContextOperations`.

### 3.1. Đọc property của JavaBean

Ví dụ sau dùng class `PersonView` đã tạo ở mục 1:

~~~java
import org.springframework.expression.Expression;
import org.springframework.expression.ExpressionParser;
import org.springframework.expression.spel.standard.SpelExpressionParser;
import org.springframework.expression.spel.support.SimpleEvaluationContext;

PersonView person = new PersonView(
    "Lan Tran", "lan@example.org"
);

ExpressionParser parser = new SpelExpressionParser();
Expression expression = parser.parseExpression("displayName");

// Chỉ cho phép đọc property theo cơ chế data binding.
SimpleEvaluationContext context =
    SimpleEvaluationContext.forReadOnlyDataBinding().build();

String result = expression.getValue(
    context,
    person,
    String.class
);

// Kết quả: "Lan Tran"
~~~

Trong trường hợp này, biểu thức `displayName` được giải quyết thông qua getter `getDisplayName()` của `PersonView`. **Không có yêu cầu LDAP mới** phát sinh khi chỉ thực hiện `expression.getValue(...)` trên JavaBean này.

### 3.2. Đọc dữ liệu từ Map trong SpEL

Một số ứng dụng đưa dữ liệu đã chọn vào `Map`:

~~~java
import java.util.LinkedHashMap;
import java.util.Map;

Map<String, String> safeAttributes = new LinkedHashMap<>();
safeAttributes.put("cn", "Lan Tran");
safeAttributes.put("mail", "lan@example.org");

String cn = new SpelExpressionParser()
    .parseExpression("['cn']")
    .getValue(
        SimpleEvaluationContext.forReadOnlyDataBinding().build(),
        safeAttributes,
        String.class
    );
~~~

Dấu `['cn']` là **truy cập key trong Map bằng SpEL indexer**; nó không đọc attribute từ LDAP server. Giá trị Map phải được lấy hoặc ánh xạ từ directory ở bước riêng. Không đưa toàn bộ attributes hoặc thông tin nhạy cảm vào biểu thức nếu chỉ cần vài trường.

### 3.3. PropertyAccessor và MethodResolver

Trong SpEL, hai giao diện liên quan nhưng không giống nhau:

| Thành phần | Trách nhiệm | Ví dụ |
| --- | --- | --- |
| `PropertyAccessor` | Đọc/ghi property trong biểu thức | `displayName` |
| `MethodResolver` | Tìm phương thức phù hợp khi biểu thức gọi method | `formatName()` |
| `ConstructorResolver` | Xử lý việc tạo object trong biểu thức khi được cho phép | `new ...` |
| `TypeLocator` | Phân giải tên type cho biểu thức | `T(java.lang.Math)` |
| `TypeConverter` | Chuyển đổi kiểu theo cấu hình context | Kết quả string sang kiểu khác |

Các khả năng này còn phụ thuộc loại `EvaluationContext`. `StandardEvaluationContext` hỗ trợ nhiều tính năng mạnh; `SimpleEvaluationContext` cho phép cấu hình một tập tính năng giới hạn hơn, phù hợp khi chỉ cần đọc property để hiển thị.

**Không gọi mọi phần mở rộng SpEL là “LDAP resolver”.** Resolver/Accessor của SpEL xử lý cú pháp và object trong biểu thức; resolver/mapper ở tầng Spring LDAP làm việc với DN, context và LDAP attributes.

## 4. Hai accessor phối hợp như thế nào?

Một ứng dụng có thể dùng cả hai theo trình tự rõ ràng:

~~~mermaid
flowchart LR
    A["LDAP server"] --> B["ContextSource / LdapTemplate"]
    B --> C["LDAP entry / DirContextOperations"]
    C --> D["ContextMapper hoặc code ứng dụng"]
    D --> E["PersonView (JavaBean/DTO)"]
    E --> F["SpEL EvaluationContext"]
    F --> G["PropertyAccessor"]
    G --> H["Giá trị để hiển thị"]
~~~

**Tầng LDAP** chịu trách nhiệm truy vấn dữ liệu thật, kiểm soát DN, filter, schema, ACL và kết nối. **Tầng mapping** chuyển attribute sang cấu trúc dữ liệu nghiệp vụ. **Tầng SpEL** chỉ đọc các property đã được công khai cho biểu thức.

Đoạn service hoàn chỉnh sau minh họa cách kết hợp:

~~~java
import javax.naming.Name;

import org.springframework.expression.Expression;
import org.springframework.expression.spel.standard.SpelExpressionParser;
import org.springframework.expression.spel.support.SimpleEvaluationContext;
import org.springframework.ldap.core.DirContextOperations;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;
import org.springframework.stereotype.Service;

@Service
public class DirectoryDisplayService {

    private final LdapTemplate ldapTemplate;
    private final Expression displayNameExpression =
        new SpelExpressionParser().parseExpression("displayName");
    private final SimpleEvaluationContext readOnlyContext =
        SimpleEvaluationContext.forReadOnlyDataBinding().build();

    public DirectoryDisplayService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public String displayNameOf(String uid) {
        Name dn = LdapNameBuilder.newInstance()
            .add("ou", "people")
            .add("uid", uid)
            .build();

        // Bước 1: truy cập LDAP.
        DirContextOperations entry = ldapTemplate.lookupContext(dn);

        // Bước 2: ánh xạ sang DTO chỉ chứa dữ liệu cần thiết.
        PersonView view = new PersonView(
            entry.getStringAttribute("cn"),
            entry.getStringAttribute("mail")
        );

        // Bước 3: SpEL đọc property của DTO.
        return displayNameExpression.getValue(
            readOnlyContext,
            view,
            String.class
        );
    }
}
~~~

Service trên giả định `ContextSource` có base DN `dc=example,dc=org` và caller chỉ gửi `uid` được phép theo chính sách nghiệp vụ. `LdapNameBuilder` giúp dựng DN đúng quy tắc escape; nó không thay thế kiểm tra quyền đọc LDAP hoặc authorization của API.

### Dữ liệu đi qua từng bước

| Bước | Đầu vào | Đầu ra | Chủ thể quyết định |
| --- | --- | --- | --- |
| LDAP lookup | DN `uid=lan,ou=people` | `DirContextOperations` | LDAP server và `LdapTemplate` |
| Accessor LDAP | `getStringAttribute("cn")` | `"Lan Tran"` | Dữ liệu của entry/mapper |
| DTO mapping | `cn`, `mail` | `PersonView` | Logic ứng dụng |
| SpEL property access | `displayName` trên `PersonView` | `"Lan Tran"` | `EvaluationContext` và property accessor |

Nếu thay đổi `cn` trong LDAP, cần thực hiện lookup mới (hoặc refresh dữ liệu phù hợp) để DTO có giá trị cập nhật. SpEL **không tự làm mới** dữ liệu từ directory.

## 5. Vì sao SpEL không tự hiểu tên LDAP attribute?

Giả sử có `DirContextOperations entry` và biểu thức:

~~~text
cn
~~~

SpEL sẽ cố giải quyết `cn` như **property của object gốc**. Nó không có quy tắc mặc định rằng `cn` phải được chuyển thành `entry.getStringAttribute("cn")`. Nếu object không có property tương ứng, biểu thức có thể thất bại với lỗi đánh giá property.

Để dùng tên LDAP attribute trong biểu thức, có ba phương án:

1. **Ưu tiên:** ánh xạ LDAP sang DTO với property rõ ràng, ví dụ `cn → displayName`, `mail → email`; SpEL chỉ đọc DTO.
2. **Map đã lọc:** đưa một số attribute cần thiết vào Map, truy cập qua indexer `['cn']`.
3. **Custom `PropertyAccessor`:** viết adapter cho các target kiểu `DirContextOperations` nếu thực sự cần cú pháp `cn` trực tiếp. Phương án này có chi phí về bảo mật, khả năng bảo trì và kiểm thử.

### Thiết kế custom PropertyAccessor khi thật sự cần

Một `PropertyAccessor` tùy chỉnh cho `DirContextOperations` cần:

- Giới hạn `getSpecificTargetClasses()` cho kiểu target dự định hỗ trợ.
- Chỉ chấp nhận **danh sách attribute cho phép** như `cn`, `mail`; không cho đọc tùy ý `userPassword` hoặc các operational attributes nhạy cảm.
- Trong `read(...)`, chuyển property name đã kiểm tra thành `getStringAttribute(name)` và trả `TypedValue`.
- Định nghĩa `canWrite(...)` là `false` nếu mục đích chỉ đọc; không cài đặt `write(...)` để tùy ý sửa LDAP.
- Dùng `SimpleEvaluationContext.forPropertyAccessors(...)` hoặc cơ chế context tương thích, kiểm thử cả trường hợp thiếu attribute, đa giá trị và lỗi kiểu dữ liệu.

**Không làm cho custom accessor tự truy vấn LDAP trong mỗi lần SpEL đọc property**. Cách đó có thể gây kết nối mạng ngầm, truy vấn lặp (kiểu N+1) và khó kiểm soát lỗi; tốt hơn hết là tìm một entry/batch có chủ đích trước khi đánh giá biểu thức.

## 6. Khác biệt về kiểu dữ liệu, giá trị thiếu và attribute nhiều giá trị

| Tình huống | Spring LDAP | SpEL trên DTO/Map |
| --- | --- | --- |
| Entry không tồn tại | `lookupContext` có thể ném `NameNotFoundException` | Không phải lỗi LDAP nếu object đã tồn tại |
| Attribute không tồn tại | Getter có thể trả `null` | Property vẫn có thể tồn tại và mang `null` |
| Property không tồn tại | Không phải khái niệm getter LDAP | Có thể phát sinh lỗi SpEL evaluation |
| Attribute nhiều giá trị | Dùng `getStringAttributes(...)`, `getObjectAttributes(...)` tùy kiểu | Truy cập collection/array của DTO qua indexer |
| Attribute binary | Cần đọc object/byte array phù hợp schema | SpEL chỉ thấy kiểu Java sau mapping |
| Kiểu dữ liệu cần chuyển đổi | Mapper có trách nhiệm diễn giải dữ liệu LDAP | `TypeConverter`/converter xử lý kiểu trong expression khi được phép |
| Giá trị đã sửa | Phải gửi `modifyAttributes(...)` để ghi server | Setter trên bean thường chỉ thay đổi object trong bộ nhớ |

Ví dụ với thuộc tính nhiều số điện thoại:

~~~java
String[] phones = entry.getStringAttributes("telephoneNumber");

// Không suy đoán phần tử [0] là "số chính" nếu LDAP/schema
// không định nghĩa thứ tự hoặc thuộc tính ưu tiên.
~~~

Nếu cần đánh giá SpEL trên danh sách điện thoại, hãy ánh xạ thành một DTO có `List<String>` và quy tắc nghiệp vụ rõ ràng. Đừng để biểu thức tự chọn phần tử đầu chỉ vì thuận tiện.

Cũng cần phân biệt khác biệt về **tên**: LDAP `mail` là tên attribute theo schema, trong khi JavaBean có thể dùng property `email`. Ánh xạ giữa hai tên là trách nhiệm của code mapper.

## 7. Bảo mật: tránh nhầm giữa LDAP filter injection và SpEL injection

Hai tầng có rủi ro khác nhau.

**Ở tầng LDAP:**

- Dựng DN bằng `LdapNameBuilder` để escape giá trị RDN.
- Dựng filter bằng `EqualsFilter`, `AndFilter` hoặc bộ dựng filter phù hợp; không ghép trực tiếp input người dùng vào cú pháp filter.
- Xác minh quyền đọc/ghi của tài khoản bind, kết nối qua LDAPS hoặc StartTLS với chứng chỉ hợp lệ.
- Chỉ trả các thuộc tính cần thiết, tránh đưa credential hoặc thông tin nhạy cảm vào DTO/Map.

**Ở tầng SpEL:**

- Không đánh giá biểu thức SpEL **tùy ý do người dùng gửi** trong context có quyền truy cập bean, type, method hoặc service nhạy cảm.
- Dùng biểu thức cố định/được kiểm soát và `SimpleEvaluationContext` ở chế độ đọc nếu chỉ cần hiển thị property.
- Không đặt `LdapTemplate`, `ContextSource` hoặc đối tượng có thể thực hiện thao tác LDAP vào root object/variables của một evaluator không đáng tin cậy.
- Tránh cho SpEL gọi method sửa dữ liệu hoặc kích hoạt truy vấn mạng dưới tên “đọc property”.
- Kiểm soát null, kiểu dữ liệu và thông tin lỗi, không gửi stack trace hay DN chứa thông tin cá nhân ra giao diện.

Ví dụ anti-pattern:

~~~java
// Không đánh giá chuỗi SpEL do người dùng tùy ý gửi
// với một StandardEvaluationContext có quyền truy cập service:
String userProvidedExpression = request.getExpression();
Object value = parser.parseExpression(userProvidedExpression)
    .getValue(privilegedEvaluationContext);
~~~

Nếu nghiệp vụ yêu cầu người dùng tự chọn trường, hãy đưa ra một **whitelist tên trường** (ví dụ `displayName`, `email`) và đọc getter trực tiếp hoặc map tới biểu thức đã định nghĩa. Đây thường là thiết kế đơn giản và dễ kiểm soát hơn việc chấp nhận toàn bộ cú pháp SpEL.

## 8. Lỗi thường gặp khi dùng hai loại accessor

| Dấu hiệu | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `getStringAttribute("cn")` là `null` | Attribute bị thiếu, không được trả về hoặc bị hạn chế bởi ACL | Kiểm tra dữ liệu, search/lookup và quyền |
| `lookupContext(dn)` báo `NameNotFoundException` | DN/base sai hoặc entry vắng mặt | Kiểm tra DN và `ContextSource`; xử lý nghiệp vụ phù hợp |
| SpEL báo không đọc được property `cn` | Object gốc không có Java property `cn` | Ánh xạ sang DTO hoặc dùng Map/custom accessor có kiểm soát |
| SpEL đọc `email` nhưng dữ liệu LDAP là `mail` | Hai hệ đặt tên khác nhau | Định nghĩa mapping `mail → email` rõ ràng |
| Gọi SpEL `setValue(...)` xong mà LDAP không đổi | SpEL chỉ sửa object Java, chưa gọi LDAP update | Ghi lại qua `LdapTemplate.modifyAttributes(...)` khi nghiệp vụ cho phép |
| Dữ liệu phone hiển thị lộn thứ tự | Attribute LDAP nhiều giá trị không có thứ tự ưu tiên | Tạo quy tắc chọn/sort ở tầng nghiệp vụ |
| Có lỗi parse/evaluation từ SpEL | Biểu thức sai hoặc không có accessor tương ứng | Sửa expression, context và loại target |
| Tài khoản LDAP thiếu quyền | ACL hoặc chính sách directory từ chối | Xử lý lỗi LDAP; không che bằng lỗi SpEL |
| Gọi một biểu thức lại tạo hàng loạt LDAP request | Custom accessor gọi server mỗi lần read | Tra cứu theo batch, ánh xạ trước khi đánh giá |
| Dùng `StandardEvaluationContext` cho input không đáng tin | Bề mặt truy cập method/type/bean rộng | Chỉ cho phép biểu thức cố định và context hạn chế |

## 9. Kiểm thử có ý nghĩa

Hãy tạo LDAP test server với base `dc=example,dc=org`, OU `ou=people` và vài entry `inetOrgPerson` hợp lệ. Những ca sau kiểm tra cả **accessor LDAP** lẫn **accessor SpEL**:

| Ca thử | Dữ liệu/điều kiện | Kỳ vọng |
| --- | --- | --- |
| Đọc LDAP `cn` | Entry tồn tại và ACL cho đọc | `getStringAttribute("cn")` trả tên đúng |
| Đọc attribute thiếu | Entry không có `description` | Không nhầm với DN vắng mặt |
| Đọc attribute nhiều giá trị | Có hai `telephoneNumber` | Nhận đúng các giá trị, không phụ thuộc thứ tự |
| Lookup DN vắng mặt | `uid=missing` không tồn tại | Nhận lỗi LDAP và xử lý tại repository/service |
| Mapper `mail → email` | Entry có `mail` | DTO mang property `email` |
| Đọc SpEL property | DTO có getter `getDisplayName()` | Biểu thức `displayName` cho giá trị đúng |
| Đọc SpEL sai property | DTO không có `cn` | Không tự động tra LDAP `cn` |
| Ghi bằng adapter | `setAttributeValue` rồi `modifyAttributes` | Readback LDAP xác nhận thay đổi |
| Chỉ sửa DTO Java | Đặt property Java mà không LDAP update | Dữ liệu server không tự thay đổi |
| Evaluator đọc hạn chế | Dùng `SimpleEvaluationContext` | Chỉ thao tác được những property đã cho phép |
| Thiếu quyền LDAP | Account không đọc được một thuộc tính | Không biến lỗi/thiếu dữ liệu thành lỗi SpEL tùy tiện |

Bài kiểm thử đơn vị có thể kiểm tra mapping/SpEL trên DTO thuần Java. Để chứng minh hoạt động của `LdapTemplate` và hành vi ACL/schema, cần kiểm thử tích hợp trên LDAP server phù hợp. Mock object không xác nhận được quyền truy cập thực tế hoặc việc đọc nhiều giá trị từ directory.

### Bài tập tự đánh giá

1. Vì sao `getStringAttribute("cn")` và biểu thức SpEL `cn` có thể trả kết quả khác nhau trên cùng một đối tượng ứng dụng?
2. `PropertyAccessor` của SpEL nhận những đầu vào nào và có vai trò gì trong `EvaluationContext`?
3. Khi ánh xạ LDAP `mail` thành JavaBean property `email`, tầng nào nên chịu trách nhiệm?
4. Tại sao `setAttributeValue("description", ...)` chưa chắc đã làm LDAP server thay đổi ngay?
5. Nếu muốn biểu thức chỉ đọc tên người dùng, nên dùng `SimpleEvaluationContext` hay đưa toàn bộ `LdapTemplate` vào `StandardEvaluationContext`?
6. Khi `telephoneNumber` có nhiều giá trị, vì sao không nên tự mặc định phần tử đầu là số ưu tiên?
7. Một custom `PropertyAccessor` có thể tự gọi LDAP; điểm nào khiến giải pháp này dễ gặp rủi ro hiệu năng và bảo mật?

## 10. Ghi nhớ

**Accessor của Spring LDAP** truy cập dữ liệu **LDAP attribute** qua `DirContextOperations`/`AttributesMapper`/`ContextMapper`, trong bối cảnh DN, schema, quyền truy cập và kết nối directory. **Accessor của SpEL** truy cập **property trong biểu thức** thông qua `EvaluationContext` và SPI `PropertyAccessor`; nó không mặc định hiểu rằng tên property Java là tên LDAP attribute.

Cách phối hợp đáng tin cậy là **truy vấn LDAP → ánh xạ sang DTO/Map đã lọc → đánh giá biểu thức được kiểm soát nếu cần**. Sự phân tầng này giúp quản lý rõ kiểu dữ liệu, lỗi, việc ghi lại server và phạm vi quyền truy cập; đồng thời tránh đánh giá SpEL với tài nguyên LDAP có đặc quyền.

## Tài liệu tham khảo

- [Spring LDAP Reference](https://docs.spring.io/spring-ldap/reference/): tổng quan `LdapTemplate`, `ContextSource`, tìm kiếm và mapping.
- [Spring LDAP — DirContextOperations API](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/core/DirContextOperations.html): các phương thức đọc/ghi attribute trên context.
- [Spring LDAP — LdapTemplate API](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/core/LdapTemplate.html): `lookupContext(...)`, `search(...)` và `modifyAttributes(...)`.
- [Spring Framework — Spring Expression Language](https://docs.spring.io/spring-framework/reference/core/expressions.html): khái niệm SpEL và `EvaluationContext`.
- [Spring Framework — Type Evaluation](https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html): đánh giá biểu thức, context và xử lý property.
- [Spring Framework — PropertyAccessor API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/PropertyAccessor.html): giao diện SPI cho accessor của SpEL.
