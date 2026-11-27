# PropertyAccessor trong quá trình mapping hoặc evaluation

Khi làm việc với Spring LDAP, dữ liệu ban đầu thường là các thuộc tính của một entry LDAP, chẳng hạn `uid`, `cn`, `mail`. Ứng dụng có thể chuyển các thuộc tính đó thành đối tượng Java hoặc đánh giá một quy tắc trên chúng. `PropertyAccessor` giúp Spring Expression Language (SpEL) hiểu cú pháp truy cập thuộc tính trong **bước đánh giá biểu thức**. Nó không tự tìm kiếm LDAP và cũng không thay thế cơ chế ánh xạ entry của Spring LDAP.

Sau bài này, bạn có thể phân biệt các loại accessor thường gặp trong Spring, giải thích cách SpEL chọn accessor, tự xây dựng accessor chỉ đọc cho `Attributes`, và quyết định khi nào nên dùng `AttributesMapper`, `ContextMapper`, ODM hoặc `PropertyAccessor`.

## 1. PropertyAccessor nằm ở đâu trong luồng xử lý?

Xét entry giả định:

```ldif
dn: uid=linh,ou=people,dc=example,dc=org
objectClass: inetOrgPerson
uid: linh
cn: Linh Nguyen
sn: Nguyen
mail: linh@example.org
```

Một luồng xử lý điển hình:

```text
LDAP server
    │  LDAP search / lookup: base DN, scope, filter
    ▼
LdapTemplate
    │  Trả về Attributes hoặc DirContext qua callback
    ▼
AttributesMapper / ContextMapper / ODM
    │  Tạo đối tượng nghiệp vụ Java (khi cần)
    ▼
Đối tượng Java hoặc cấu trúc thuộc tính đã lấy từ LDAP
    │  Expression + EvaluationContext
    ▼
SpEL PropertyAccessor
    │  Đọc một thuộc tính để đánh giá quy tắc / tính giá trị
    ▼
Kết quả: String, Boolean, giá trị tính toán, ...
```

Phân biệt rõ trách nhiệm của từng API:

| Thành phần | Nhiệm vụ | Ví dụ |
| --- | --- | --- |
| `LdapTemplate` / `LdapOperations` | Thực hiện thao tác LDAP, quản lý truy cập thư mục | `search(query, mapper)` |
| `AttributesMapper<T>` | Biến `javax.naming.directory.Attributes` của từng entry thành `T` | Đọc `cn` rồi tạo `DirectoryPerson` |
| `ContextMapper<T>` | Ánh xạ ngữ cảnh LDAP, hữu ích khi cần DN hoặc thông tin của `DirContextAdapter` | Lấy `getDn()` và tên hiển thị |
| ODM (`@Entry`, `@Id`, `@Attribute`) | Ánh xạ entry và trường của lớp Java bằng metadata | `ldapTemplate.find(query, Person.class)` |
| `org.springframework.expression.PropertyAccessor` | Cho **SpEL** biết có thể đọc/ghi thuộc tính tên `x` từ một đối tượng hay không | Diễn giải biểu thức `mail != null` |

`PropertyAccessor` thuộc Spring Framework, không phải một kiểu mapper riêng của Spring LDAP. Các phương thức ODM của `LdapTemplate` sử dụng `ObjectDirectoryMapper`; đăng ký một SpEL accessor **không** tự làm thay đổi cách ODM đọc/ghi thuộc tính LDAP. Nếu chỉ cần ánh xạ cố định một vài thuộc tính, dùng `AttributesMapper` hoặc ODM thường đơn giản hơn. Accessor tùy biến phát huy tác dụng khi ứng dụng thật sự dùng SpEL để đọc dữ liệu từ cấu trúc đặc biệt hoặc thực hiện các phép đánh giá cấu hình sẵn.

> **Dễ nhầm tên:** `org.springframework.expression.PropertyAccessor` là giao diện phục vụ SpEL (`canRead`, `read`, `canWrite`, `write`). `org.springframework.beans.PropertyAccessor` là giao diện khác, dùng cho truy cập thuộc tính bean (`getPropertyValue`, `setPropertyValue`), với các triển khai như `BeanWrapper`. Khi nói về `EvaluationContext` trong bài này, ta dùng **giao diện thứ nhất**.

## 2. Hợp đồng của SpEL PropertyAccessor

Các phương thức cốt lõi của `org.springframework.expression.PropertyAccessor` là:

| Phương thức | Ý nghĩa |
| --- | --- |
| `getSpecificTargetClasses()` | Khai báo những kiểu đối tượng đích mà accessor hỗ trợ; `null` nghĩa là có thể được xem xét cho mọi kiểu |
| `canRead(context, target, name)` | Cho biết accessor có thể đọc thuộc tính `name` của `target` hay không |
| `read(context, target, name)` | Đọc thuộc tính và trả về `TypedValue` (chứa giá trị và thông tin kiểu) |
| `canWrite(context, target, name)` | Cho biết thuộc tính có hỗ trợ ghi hay không |
| `write(context, target, name, newValue)` | Ghi giá trị; accessor chỉ đọc nên từ chối thao tác này |

Trong một `EvaluationContext`, SpEL thử các accessor phù hợp để giải quyết phép truy cập như `person.mail`. Các accessor nhắm vào kiểu đích cụ thể được ưu tiên khi phù hợp; SpEL còn có thể cache accessor đã chọn cho một nút biểu thức. Vì vậy `canRead` và `read` phải nhất quán với cùng kiểu đích/tên thuộc tính. `canRead` không nên có tác dụng phụ và `read` không nên bất ngờ sửa LDAP.

Với đối tượng JavaBean thông thường, Spring đã có `ReflectivePropertyAccessor` hoặc `DataBindingPropertyAccessor`. Khi dữ liệu là `Attributes` (một tập thuộc tính LDAP, không phải JavaBean), một accessor chuyên biệt có thể cho phép viết `mail` trong biểu thức thay vì tự gọi `attributes.get("mail").get()` ở mỗi nơi.

## 3. Ví dụ: tạo accessor chỉ đọc cho thuộc tính LDAP

Để đánh giá tên thuộc tính LDAP trực tiếp bằng SpEL, ta giới hạn những thuộc tính có thể đọc (`uid`, `cn`, `mail`) và quy ước ví dụ này chỉ chấp nhận giá trị kiểu `String` có **một** phần tử. Đây là một quy tắc nghiệp vụ của ví dụ, không phải giới hạn của LDAP: LDAP có thể có thuộc tính nhiều giá trị hoặc giá trị nhị phân.

```java
import java.util.Set;
import javax.naming.NamingException;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;

import org.springframework.expression.AccessException;
import org.springframework.expression.EvaluationContext;
import org.springframework.expression.PropertyAccessor;
import org.springframework.expression.TypedValue;

public final class LdapAttributeAccessor implements PropertyAccessor {
    private static final Set<String> ALLOWED = Set.of("uid", "cn", "mail");

    @Override
    public Class<?>[] getSpecificTargetClasses() {
        return new Class<?>[] { Attributes.class };
    }

    @Override
    public boolean canRead(EvaluationContext context, Object target, String name) {
        return target instanceof Attributes && ALLOWED.contains(name);
    }

    @Override
    public TypedValue read(EvaluationContext context, Object target, String name)
            throws AccessException {
        if (!canRead(context, target, name)) {
            throw new AccessException("Thuộc tính không được phép đọc: " + name);
        }

        try {
            Attribute attribute = ((Attributes) target).get(name);
            if (attribute == null || attribute.size() == 0) {
                return new TypedValue(null); // Thuộc tính hợp lệ nhưng không có giá trị
            }
            if (attribute.size() != 1) {
                throw new AccessException("Thuộc tính có nhiều giá trị: " + name);
            }

            Object value = attribute.get();
            if (!(value instanceof String)) {
                throw new AccessException("Thuộc tính không phải chuỗi: " + name);
            }
            return new TypedValue(value);
        } catch (NamingException ex) {
            throw new AccessException("Không đọc được thuộc tính LDAP: " + name, ex);
        }
    }

    @Override
    public boolean canWrite(EvaluationContext context, Object target, String name) {
        return false;
    }

    @Override
    public void write(EvaluationContext context, Object target, String name,
                      Object newValue) throws AccessException {
        throw new AccessException("Accessor LDAP này chỉ cho phép đọc");
    }
}
```

Các quyết định quan trọng trong thiết kế:

1. `getSpecificTargetClasses()` giới hạn đối tượng đích là `Attributes`. Accessor không nhận nhầm một JavaBean hay một loại dữ liệu khác.
2. `ALLOWED` giới hạn tên thuộc tính có thể truy cập. Một thuộc tính được phép nhưng vắng mặt trả về `null`, để có thể dùng biểu thức như `mail != null`.
3. Thuộc tính nhiều giá trị hoặc nhị phân không được tự ý ép thành `String`. Khi thực tế cần `memberOf` hay `jpegPhoto`, hãy thiết kế kiểu trả về/logic chuyển đổi tương ứng.
4. `canWrite() == false` và `write()` từ chối ghi. Việc chỉnh sửa LDAP phải được thực hiện qua API cập nhật LDAP với kiểm tra quyền và dữ liệu thích hợp.

### Kiểm tra đánh giá không cần LDAP server

```java
import javax.naming.directory.Attributes;
import javax.naming.directory.BasicAttributes;

import org.springframework.expression.Expression;
import org.springframework.expression.ExpressionParser;
import org.springframework.expression.spel.standard.SpelExpressionParser;
import org.springframework.expression.spel.support.SimpleEvaluationContext;

Attributes attributes = new BasicAttributes(true); // Tên thuộc tính không phân biệt hoa/thường
attributes.put("uid", "linh");
attributes.put("cn", "Linh Nguyen");
attributes.put("mail", "linh@example.org");

SimpleEvaluationContext context = SimpleEvaluationContext
        .forPropertyAccessors(new LdapAttributeAccessor())
        .withAssignmentDisabled()
        .build();

ExpressionParser parser = new SpelExpressionParser();
Expression emailExpression = parser.parseExpression("mail");
Expression hasEmailExpression = parser.parseExpression("mail != null");

String email = emailExpression.getValue(context, attributes, String.class);
Boolean hasEmail = hasEmailExpression.getValue(context, attributes, Boolean.class);

// email == "linh@example.org"
// Boolean.TRUE.equals(hasEmail) == true
```

`SimpleEvaluationContext` chỉ cung cấp một tập con chức năng SpEL, phù hợp với tác vụ đọc thuộc tính. `withAssignmentDisabled()` vô hiệu các phép gán trong biểu thức. Việc cấu hình accessor trong context này **chỉ ảnh hưởng các biểu thức đánh giá với context đó**; không tự đăng ký accessor cho tất cả `LdapTemplate` hoặc cho LDAP server.

## 4. Tích hợp vào quá trình mapping của LdapTemplate

Ví dụ sau đưa accessor vào callback `AttributesMapper` để chuyển từng entry tìm được thành đối tượng Java. Đây là cách tích hợp **tường minh**: callback nhận `Attributes`, chủ động gọi SpEL rồi tạo đối tượng. Giả định `ldapTemplate` đã được cấu hình `ContextSource` và `ou=people` là base tương đối với base DN của kết nối.

```java
import java.util.List;

import org.springframework.expression.Expression;
import org.springframework.expression.ExpressionParser;
import org.springframework.expression.spel.standard.SpelExpressionParser;
import org.springframework.expression.spel.support.SimpleEvaluationContext;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;

import static org.springframework.ldap.query.LdapQueryBuilder.query;

record DirectoryPerson(String uid, String commonName, String email) {}

public final class DirectoryReader {
    private final LdapTemplate ldapTemplate;
    private final SimpleEvaluationContext readContext = SimpleEvaluationContext
            .forPropertyAccessors(new LdapAttributeAccessor())
            .withAssignmentDisabled()
            .build();

    private final ExpressionParser parser = new SpelExpressionParser();
    private final Expression uidExpression = parser.parseExpression("uid");
    private final Expression nameExpression = parser.parseExpression("cn");
    private final Expression mailExpression = parser.parseExpression("mail");

    public DirectoryReader(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<DirectoryPerson> findPeople() {
        AttributesMapper<DirectoryPerson> mapper = attrs -> new DirectoryPerson(
                uidExpression.getValue(readContext, attrs, String.class),
                nameExpression.getValue(readContext, attrs, String.class),
                mailExpression.getValue(readContext, attrs, String.class)
        );

        return ldapTemplate.search(
                query().base("ou=people").where("objectClass").is("inetOrgPerson"),
                mapper
        );
    }
}
```

Ở đây, phần `query()` quyết định **entry nào được truy vấn trên LDAP server**. `AttributesMapper` xử lý **từng entry đã được trả về**. `PropertyAccessor` được gọi khi biểu thức SpEL `uid`, `cn` hoặc `mail` được đánh giá trên `Attributes` đó. Việc chuyển thành `DirectoryPerson` chỉ diễn ra trong Java; ví dụ không ghi ngược entry xuống LDAP.

Trong tình huống ánh xạ cố định như trên, có thể bỏ SpEL và viết `AttributesMapper` đọc `attrs.get("uid")`, `attrs.get("cn")`, `attrs.get("mail")` trực tiếp. Tùy biến `PropertyAccessor` hữu ích hơn khi nhiều quy tắc hoặc các biểu thức *được ứng dụng kiểm soát* cần dùng chung một cách truy cập dữ liệu LDAP, ví dụ tính trường xuất báo cáo từ những thuộc tính đã truy vấn.

### Khi dữ liệu đã được map thành Java object

Với một DTO/JavaBean thông thường, không cần `LdapAttributeAccessor`. Bạn có thể dùng accessor data binding có sẵn:

```java
SimpleEvaluationContext beanContext = SimpleEvaluationContext
        .forReadOnlyDataBinding()
        .build();

class PersonBean {
    public String getEmail() { return "linh@example.org"; }
}
PersonBean personBean = new PersonBean();

String email = new SpelExpressionParser()
        .parseExpression("email")
        .getValue(beanContext, personBean, String.class);
```

Nếu dùng ODM, `@Entry`, `@Id`, `@Attribute` và bộ chuyển kiểu của `ObjectDirectoryMapper` mới là cơ chế kiểm soát mapping LDAP ↔ Java. Sau khi có đối tượng, SpEL có thể đọc giá trị từ getter/thuộc tính Java, nhưng không vì thế mà tự thay đổi metadata ODM.

## 5. Những vấn đề thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| SpEL báo không đọc được `mail` | Accessor chưa được đăng ký vào đúng `EvaluationContext`, hoặc target không phải `Attributes` | Kiểm tra `forPropertyAccessors(...)`, đối tượng gốc và tên thuộc tính |
| Thuộc tính đã được cho phép nhưng kết quả `null` | LDAP entry không có attribute đó hoặc server không trả về do phân quyền/điều kiện truy vấn | Xem tập thuộc tính được trả về và quyền của tài khoản bind; xử lý giá trị thiếu rõ ràng |
| Lỗi khi đọc `memberOf` | Attribute có nhiều giá trị; accessor ví dụ chỉ nhận một chuỗi | Xử lý `Attribute.getAll()` và một kiểu tập hợp phù hợp |
| Kỳ vọng biểu thức làm thay đổi entry trên server | SpEL chỉ hoạt động trên đối tượng Java được cung cấp để đánh giá | Dùng `LdapTemplate`/`LdapOperations` để sửa LDAP theo luồng nghiệp vụ |
| Kết quả khác khi tái sử dụng biểu thức | Context/accessor hoặc kiểu target thay đổi, trong khi SpEL có cache phân giải | Cấu hình context ổn định và không dùng chung expression giữa các context có mức quyền khác nhau |

Về hiệu năng, hãy tạo `ExpressionParser`, các `Expression` cố định và `EvaluationContext` phù hợp một lần rồi tái sử dụng; đừng parse cùng một biểu thức cho từng entry trong một danh sách lớn. Với phép ánh xạ cố định có ít trường, việc đọc trực tiếp bằng mapper thường dễ hiểu và tiết kiệm chi phí đánh giá biểu thức hơn.

Về an toàn, **không lấy chuỗi SpEL tùy ý do người dùng gửi rồi đem đánh giá**, kể cả với `SimpleEvaluationContext`: accessor hoặc getter có thể gây tác dụng phụ và khả năng truy cập phụ thuộc đối tượng được cung cấp. Chỉ sử dụng biểu thức đáng tin cậy, giới hạn các thuộc tính lộ ra, giới hạn quyền của tài khoản LDAP và tránh ghi log dữ liệu cá nhân. Đặc biệt, lọc dữ liệu bằng SpEL sau khi tìm kiếm **không thay thế** LDAP search filter ở server; vẫn cần filter, scope, phân quyền và giới hạn kết quả phù hợp.

## 6. Tự kiểm tra kiến thức

1. Khi đã dùng `ldapTemplate.find(query, Person.class)`, có cần thêm SpEL `PropertyAccessor` để ánh xạ `@Attribute("mail")` không? **Không**; ODM đảm nhiệm ánh xạ. Accessor chỉ cần khi có bước đánh giá biểu thức riêng.
2. `canRead()` trả `true` với thuộc tính `mail` nhưng entry không có `mail`, kết quả nên là gì? **Theo quy ước ví dụ:** `read()` trả `TypedValue(null)`; biểu thức `mail != null` trả `false`.
3. Vì sao không dùng SpEL để thay LDAP filter? Vì LDAP filter chạy **trên server trước khi trả entry**, còn biểu thức SpEL ở ví dụ chỉ chạy **trên dữ liệu đã tải về**.
4. Khi nào ưu tiên `DataBindingPropertyAccessor`? Khi cần đọc/ghi thuộc tính của JavaBean trong giới hạn hỗ trợ của SpEL, thay vì một cấu trúc đặc thù như `Attributes`.

## Tài liệu tham khảo

- [Spring Framework — EvaluationContext và PropertyAccessor](https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html).
- [Spring Framework — API `PropertyAccessor`](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/PropertyAccessor.html).
- [Spring LDAP — Object-Directory Mapping](https://docs.spring.io/spring-ldap/reference/odm.html).
- [Spring LDAP — API `AttributesMapper`](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/AttributesMapper.html).
