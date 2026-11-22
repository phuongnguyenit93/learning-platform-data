# Kiểm thử conversion, binding và lỗi kiểu

Khi dùng SpEL trong ứng dụng, expression có thể parse thành công nhưng vẫn thất bại lúc đánh giá vì giá trị thực tế không đúng kiểu, không chuyển đổi được hoặc property đích không thể ghi. Vì vậy, kiểm thử SpEL cần xác nhận cả kết quả đúng lẫn cách hệ thống phản ứng với dữ liệu sai.

Ba phạm vi cần phân biệt là conversion của giá trị kết quả, conversion đối số khi gọi method và conversion khi gán property bằng setValue. Mỗi thao tác đi qua TypeConverter và EvaluationContext, nhưng đường thực thi và lỗi có thể khác nhau. Một bộ test tốt kiểm tra từng ranh giới riêng, sau đó mới kiểm tra cách chúng phối hợp trong cấu hình Spring thực tế.

## 1. Những gì cần kiểm thử

Một expression thường trải qua các bước:

1. Parse chuỗi expression.
2. Đánh giá property, biến, method hoặc collection operation.
3. Chuyển đổi đối số nếu method yêu cầu kiểu khác.
4. Gọi method hoặc đọc giá trị.
5. Chuyển đổi kết quả nếu caller yêu cầu kiểu đích.
6. Ghi property nếu dùng setValue.

Các test nên bao phủ:

- Cú pháp hợp lệ và cú pháp sai.
- Giá trị runtime có kiểu đúng.
- Chuyển đổi từ kiểu nguồn sang kiểu đích.
- Custom converter của ứng dụng.
- Binding vào JavaBean property.
- Binding vào property lồng nhau, Map hoặc List.
- Property chỉ đọc và object trung gian null.
- Giá trị không hợp lệ, null và primitive.
- Exception khi method hoặc setter từ chối dữ liệu.

Không nên chỉ kiểm tra expression trả về một giá trị trong trường hợp lý tưởng. Các lỗi kiểu thường chỉ xuất hiện khi dữ liệu thực tế khác dữ liệu test thông thường.

## 2. Tạo parser và EvaluationContext trong unit test

Với unit test thuần, có thể tạo SpelExpressionParser và EvaluationContext trực tiếp:

~~~java
class SpelBindingTest {

    private final ExpressionParser parser =
            new SpelExpressionParser();

    private final EvaluationContext context =
            SimpleEvaluationContext.forReadWriteDataBinding()
                    .build();
}
~~~

SimpleEvaluationContext.forReadWriteDataBinding() phù hợp khi test cần đọc và ghi JavaBean property theo data binding. Nếu test cần function, type reference, bean reference hoặc các tính năng khác của StandardEvaluationContext, hãy tạo context tương ứng và cấu hình rõ các resolver cần thiết.

Giữ parser và context trong phạm vi test hoặc fixture có lifecycle rõ ràng. Tránh chia sẻ một EvaluationContext mutable giữa các test chạy song song nếu root object và variables bị thay đổi.

## 3. Kiểm thử parse thành công và parse thất bại

Parse test xác nhận chuỗi có đúng cú pháp SpEL và parser tạo được Expression.

~~~java
@Test
void parsesValidExpression() {
    Expression expression =
            parser.parseExpression("age >= 18");

    assertNotNull(expression);
}
~~~

Có thể kiểm tra lỗi cú pháp:

~~~java
@Test
void rejectsInvalidExpression() {
    assertThrows(
            ParseException.class,
            () -> parser.parseExpression("age >")
    );
}
~~~

ParseException thuộc hệ exception của Spring Expression; SpelParseException là dạng cụ thể cho lỗi parse SpEL. Test này chỉ kiểm tra cú pháp, không chứng minh property age tồn tại hoặc có thể chuyển đổi khi đánh giá.

Hãy giữ parse test riêng với evaluation test để biết lỗi xảy ra ở giai đoạn nào.

## 4. Kiểm thử kiểu kết quả với typed getValue

Expression.getValue(context, TargetType.class) yêu cầu SpEL trả về giá trị tương thích với kiểu đích và sử dụng TypeConverter khi cần chuyển đổi.

Ví dụ:

~~~java
@Test
void convertsEvaluatedStringToInteger() {
    StandardEvaluationContext context =
            new StandardEvaluationContext();

    context.setVariable("raw", "42");

    Expression expression =
            parser.parseExpression("#raw");

    Integer result = expression.getValue(
            context,
            Integer.class
    );

    assertEquals(42, result);
}
~~~

Test này xác nhận chuỗi "42" có thể được chuyển thành Integer trong context đang dùng.

Cần kiểm tra cả kiểu và giá trị. Nếu chỉ so sánh chuỗi biểu diễn, test có thể bỏ qua trường hợp kết quả thực tế là một kiểu khác nhưng có cùng nội dung khi gọi toString().

Với giá trị null, hãy kiểm tra hành vi theo kiểu đích. Kiểu tham chiếu có thể biểu diễn null; primitive như int hoặc boolean thì không. Nếu expression trả null nhưng caller yêu cầu primitive, việc lấy kết quả có thể thất bại.

## 5. Kiểm thử conversion thành công và thất bại

Một conversion test nên có ít nhất một dữ liệu hợp lệ và một dữ liệu sai định dạng:

~~~java
@Test
void convertsValidNumber() {
    StandardEvaluationContext context =
            new StandardEvaluationContext();

    context.setVariable("raw", "125");

    Integer result = parser.parseExpression("#raw")
            .getValue(context, Integer.class);

    assertEquals(125, result);
}

@Test
void rejectsInvalidNumber() {
    StandardEvaluationContext context =
            new StandardEvaluationContext();

    context.setVariable("raw", "twelve");

    Expression expression = parser.parseExpression("#raw");

    assertThrows(
            EvaluationException.class,
            () -> expression.getValue(context, Integer.class)
    );
}
~~~

Không nên phụ thuộc vào một message text cụ thể nếu ứng dụng không có hợp đồng với nội dung message. Hãy xác nhận exception thuộc nhóm phù hợp và, khi cần, kiểm tra cause hoặc mã lỗi cụ thể theo phiên bản Spring đang dùng.

Nếu ứng dụng cấu hình custom TypeConverter, hãy tạo test bằng đúng converter đó. Test với converter mặc định không chứng minh converter production đang hoạt động.

## 6. Kiểm thử binding một JavaBean property

Để kiểm thử setValue, tạo object có getter và setter:

~~~java
public class Profile {

    private String displayName;
    private Integer age;

    public String getDisplayName() {
        return displayName;
    }

    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }

    public Integer getAge() {
        return age;
    }

    public void setAge(Integer age) {
        this.age = age;
    }
}
~~~

Test cập nhật property:

~~~java
@Test
void writesBeanProperty() {
    Profile profile = new Profile();

    EvaluationContext context =
            SimpleEvaluationContext.forReadWriteDataBinding()
                    .build();

    Expression expression =
            parser.parseExpression("displayName");

    expression.setValue(context, profile, "Lan");

    assertEquals("Lan", profile.getDisplayName());
}
~~~

Test này xác nhận property accessor có thể tìm và ghi property displayName trên root object.

Hãy kiểm tra trạng thái object sau setValue, thay vì chỉ xác nhận lời gọi không ném exception. Một thao tác ghi không có exception chưa đủ để chứng minh đúng property đã được cập nhật.

## 7. Kiểm thử conversion khi ghi property

Property đích có thể là Integer trong khi giá trị truyền vào setValue là String:

~~~java
@Test
void convertsValueWhenWritingProperty() {
    Profile profile = new Profile();

    EvaluationContext context =
            SimpleEvaluationContext.forReadWriteDataBinding()
                    .build();

    Expression age = parser.parseExpression("age");

    age.setValue(context, profile, "30");

    assertEquals(Integer.valueOf(30), profile.getAge());
}
~~~

Test này kiểm tra conversion xảy ra trên đường ghi property.

Cũng cần kiểm tra dữ liệu không hợp lệ:

~~~java
@Test
void rejectsInvalidValueWhenWritingProperty() {
    Profile profile = new Profile();

    EvaluationContext context =
            SimpleEvaluationContext.forReadWriteDataBinding()
                    .build();

    Expression age = parser.parseExpression("age");

    assertThrows(
            EvaluationException.class,
            () -> age.setValue(context, profile, "thirty")
    );
}
~~~

Exception cụ thể phụ thuộc converter và accessor. Test nên xác nhận thao tác không thành công và object không bị đưa vào trạng thái sai. Nếu setter có thể thay đổi trạng thái trước khi ném lỗi, hãy kiểm tra invariant của object hoặc dùng setter có tính nguyên tử phù hợp.

## 8. Kiểm thử property chỉ đọc

Một property chỉ có getter có thể đọc được nhưng không thể cập nhật bằng JavaBean data binding thông thường.

~~~java
public class ImmutableProfile {

    private final String name;

    public ImmutableProfile(String name) {
        this.name = name;
    }

    public String getName() {
        return name;
    }
}
~~~

Test ghi thất bại:

~~~java
@Test
void cannotWriteReadOnlyProperty() {
    ImmutableProfile profile =
            new ImmutableProfile("Lan");

    EvaluationContext context =
            SimpleEvaluationContext.forReadWriteDataBinding()
                    .build();

    Expression name = parser.parseExpression("name");

    assertThrows(
            EvaluationException.class,
            () -> name.setValue(context, profile, "Minh")
    );

    assertEquals("Lan", profile.getName());
}
~~~

Test này giúp phân biệt property có thể đọc với property có thể ghi. Với object bất biến, hãy tạo instance mới bằng constructor hoặc factory thay vì dùng setValue.

## 9. Kiểm thử property lồng nhau

Property path có thể đi qua nhiều object:

~~~java
public class Address {

    private String city;

    public String getCity() {
        return city;
    }

    public void setCity(String city) {
        this.city = city;
    }
}

public class CustomerProfile {

    private Address address;

    public Address getAddress() {
        return address;
    }

    public void setAddress(Address address) {
        this.address = address;
    }
}
~~~

Test cập nhật property con:

~~~java
@Test
void writesNestedProperty() {
    CustomerProfile profile = new CustomerProfile();
    profile.setAddress(new Address());

    EvaluationContext context =
            SimpleEvaluationContext.forReadWriteDataBinding()
                    .build();

    Expression city =
            parser.parseExpression("address.city");

    city.setValue(context, profile, "Da Nang");

    assertEquals(
            "Da Nang",
            profile.getAddress().getCity()
    );
}
~~~

Object trung gian phải tồn tại và có thể truy cập. Không nên mặc định SpEL sẽ tự tạo Address khi profile.address là null. Hãy có một test riêng cho null intermediate object và xác nhận lỗi hoặc hành vi auto-grow đúng với cấu hình thực tế của ứng dụng.

## 10. Kiểm thử Map và List binding

Indexer có thể cập nhật Map entry hoặc phần tử collection nếu đích mutable và accessor hỗ trợ.

Ví dụ Map:

~~~java
@Test
void writesMapEntry() {
    Map<String, Object> settings = new HashMap<>();
    settings.put("theme", "light");

    StandardEvaluationContext context =
            new StandardEvaluationContext();

    context.setVariable("settings", settings);

    Expression theme =
            parser.parseExpression("#settings['theme']");

    theme.setValue(context, "dark");

    assertEquals("dark", settings.get("theme"));
}
~~~

Ví dụ List chứa object:

~~~java
@Test
void writesPropertyOfListElement() {
    List<Profile> profiles = new ArrayList<>();
    profiles.add(new Profile());

    StandardEvaluationContext context =
            new StandardEvaluationContext();

    context.setVariable("profiles", profiles);

    Expression name =
            parser.parseExpression("#profiles[0].displayName");

    name.setValue(context, "Minh");

    assertEquals("Minh", profiles.get(0).getDisplayName());
}
~~~

Test thêm trường hợp index ngoài phạm vi, Map không mutable hoặc key sai kiểu nếu các tình huống đó có thể xuất hiện trong ứng dụng. Không dùng collection bất biến trong test được kỳ vọng phải ghi thành công.

## 11. Kiểm thử custom Converter

Nếu ứng dụng có kiểu domain riêng, hãy xác nhận converter đã đăng ký được sử dụng bởi EvaluationContext.

Ví dụ kiểu AccountCode:

~~~java
public record AccountCode(String value) {
}
~~~

Tạo ConversionService và context:

~~~java
DefaultConversionService conversionService =
        new DefaultConversionService();

conversionService.addConverter(
        String.class,
        AccountCode.class,
        AccountCode::new
);

EvaluationContext context =
        SimpleEvaluationContext.forReadOnlyDataBinding()
                .withTypeConverter(
                        new StandardTypeConverter(conversionService)
                )
                .build();
~~~

Test:

~~~java
@Test
void usesCustomConverterForTypedResult() {
    StandardEvaluationContext context =
            new StandardEvaluationContext();

    DefaultConversionService conversionService =
            new DefaultConversionService();

    conversionService.addConverter(
            String.class,
            AccountCode.class,
            AccountCode::new
    );

    context.setTypeConverter(
            new StandardTypeConverter(conversionService)
    );

    context.setVariable("rawCode", "AC-100");

    AccountCode result = parser.parseExpression("#rawCode")
            .getValue(context, AccountCode.class);

    assertEquals(new AccountCode("AC-100"), result);
}
~~~

Trong test thực tế, hãy dùng đúng loại context mà use case yêu cầu. Ví dụ trên dùng StandardEvaluationContext để minh họa cấu hình TypeConverter trực tiếp; với data binding hạn chế, có thể cấu hình converter qua builder của SimpleEvaluationContext.

Ngoài trường hợp hợp lệ, kiểm tra converter từ chối chuỗi rỗng hoặc định dạng sai nếu domain type có quy tắc định dạng. Converter không nên âm thầm tạo object không hợp lệ.

## 12. Kiểm thử conversion của đối số method

SpEL có thể chuyển đổi đối số trước khi gọi method nếu TypeConverter hỗ trợ.

~~~java
public class NumberOperations {

    public Integer doubleValue(Integer value) {
        return value * 2;
    }
}
~~~

Test:

~~~java
@Test
void convertsArgumentBeforeMethodInvocation() {
    NumberOperations operations = new NumberOperations();

    StandardEvaluationContext context =
            new StandardEvaluationContext(operations);

    Expression expression =
            parser.parseExpression("doubleValue('21')");

    Integer result = expression.getValue(
            context,
            Integer.class
    );

    assertEquals(42, result);
}
~~~

Test này kiểm tra cả method resolution lẫn conversion đối số. Nếu thất bại, hãy xác định lỗi thuộc method không được tìm thấy hay conversion không thực hiện được.

Khi method có nhiều tham số cùng kiểu, test cần xác nhận thứ tự đối số. Một lời gọi có thể chạy mà không có lỗi kiểu nhưng vẫn truyền nhầm ý nghĩa giữa các tham số.

## 13. Kiểm thử null và primitive

Null là trường hợp quan trọng vì kiểu tham chiếu có thể chứa null còn primitive thì không.

Các tình huống nên kiểm tra:

- Expression trả null và caller yêu cầu String.
- Expression trả null và caller yêu cầu Integer.
- Expression trả null nhưng caller yêu cầu int.
- Property wrapper là null rồi được dùng trong phép toán.
- Setter nhận null và có chấp nhận hay không.

Ví dụ kiểm tra typed result:

~~~java
@Test
void preservesNullForReferenceType() {
    StandardEvaluationContext context =
            new StandardEvaluationContext();

    context.setVariable("value", null);

    String result = parser.parseExpression("#value")
            .getValue(context, String.class);

    assertNull(result);
}
~~~

Nếu primitive không thể biểu diễn kết quả null, test nên xác nhận lỗi phù hợp với phiên bản framework. Không nên chuyển null thành 0 hoặc false một cách ngầm định nếu nghiệp vụ không quy định default đó.

## 14. Phân biệt lỗi parse với lỗi conversion/binding

Một expression sai cú pháp thất bại trước khi có EvaluationContext:

~~~java
assertThrows(
        ParseException.class,
        () -> parser.parseExpression("age >")
);
~~~

Một expression hợp lệ nhưng có giá trị không chuyển đổi được sẽ thất bại khi evaluate:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("raw", "not-a-number");

Expression expression = parser.parseExpression("#raw");

assertThrows(
        EvaluationException.class,
        () -> expression.getValue(context, Integer.class)
);
~~~

Binding cũng có thể thất bại trong lúc evaluate nếu property không ghi được hoặc conversion không thành công.

Test nên xác nhận đúng giai đoạn và loại lỗi. Đừng dùng một assertion chung cho mọi exception nếu ứng dụng cần phân biệt lỗi cấu hình với lỗi dữ liệu.

## 15. Kiểm thử validation riêng với conversion

Conversion thành công không có nghĩa giá trị hợp lệ theo nghiệp vụ. Ví dụ chuỗi "-5" có thể chuyển thành Integer -5, nhưng quantity có thể phải lớn hơn 0.

~~~java
public class QuantityForm {

    private Integer quantity;

    public Integer getQuantity() {
        return quantity;
    }

    public void setQuantity(Integer quantity) {
        this.quantity = quantity;
    }
}
~~~

Sau khi binding:

~~~java
quantityExpression.setValue(context, form, "5");
~~~

ứng dụng vẫn cần validation:

~~~java
assertTrue(form.getQuantity() > 0);
~~~

Trong dự án thật, nên dùng Jakarta Bean Validation hoặc validator domain thích hợp. Test conversion tập trung vào kiểu nguồn/đích; test validation tập trung vào invariant nghiệp vụ.

Không gộp hai trách nhiệm vào custom converter. Converter nên chuyển dữ liệu; validator quyết định dữ liệu đó có được phép trong domain hay không.

## 16. Kiểm thử Spring integration cho @Value và bean binding

Unit test trực tiếp Expression không kiểm tra được toàn bộ cơ chế Spring inject @Value hoặc khởi tạo bean. Với cấu hình có annotation, hãy tạo ApplicationContext test với bộ property riêng.

Ví dụ cấu hình:

~~~java
@Component
public class LimitSettings {

    private final int limit;

    public LimitSettings(
            @Value("${app.limit:10}") int limit) {
        this.limit = limit;
    }

    public int getLimit() {
        return limit;
    }
}
~~~

Có thể dùng Spring test context hoặc ApplicationContextRunner trong Spring Boot để xác nhận:

- Property được resolve đúng.
- Default được áp dụng khi thiếu property.
- Conversion sang kiểu field/constructor đúng.
- Giá trị sai định dạng khiến context khởi tạo thất bại theo mong đợi.
- Bean điều kiện có hoặc không được đăng ký theo property.

Unit test SpEL và integration test Spring bổ sung cho nhau. Không cần khởi tạo toàn bộ ứng dụng cho mọi trường hợp conversion đơn giản; dùng context test khi cần xác nhận wiring, placeholder hoặc annotation processing.

## 17. Dùng parameterized test cho nhiều giá trị

Nếu một converter hoặc expression cần xử lý nhiều input, JUnit 5 parameterized test giúp tránh lặp code.

Ví dụ:

~~~java
@ParameterizedTest
@CsvSource({
        "10, 10",
        "25, 25",
        "100, 100"
})
void convertsValidIntegers(String raw, Integer expected) {
    StandardEvaluationContext context =
            new StandardEvaluationContext();

    context.setVariable("raw", raw);

    Integer actual = parser.parseExpression("#raw")
            .getValue(context, Integer.class);

    assertEquals(expected, actual);
}
~~~

Có thể dùng @MethodSource cho các input phức tạp hoặc object domain. Với dữ liệu sai, viết parameterized test riêng để xác nhận từng giá trị bị từ chối.

Đặt tên test mô tả hành vi, chẳng hạn convertsValidInteger hoặc rejectsMalformedAccountCode. Tên rõ giúp báo cáo test cho biết hợp đồng nào bị vi phạm.

## 18. Kiểm tra object sau khi thao tác thất bại

Khi setValue hoặc setter ném exception, cần xác nhận object còn ở trạng thái hợp lệ.

Ví dụ, nếu setter kiểm tra giá trị trước khi gán:

~~~java
public void setAge(Integer age) {
    if (age != null && age < 0) {
        throw new IllegalArgumentException("Age must be non-negative");
    }
    this.age = age;
}
~~~

Test nên kiểm tra:

- Exception được truyền ra hoặc được bọc theo hợp đồng dự kiến.
- Giá trị cũ vẫn được giữ nếu thao tác bị từ chối.
- Các property liên quan không bị cập nhật dở dang.
- Không có side effect không mong muốn.

Nếu setter cập nhật nhiều field trước khi thất bại, cần thiết kế lại thao tác để validate trước khi mutate hoặc thực hiện cập nhật nguyên tử ở tầng domain.

SpEL không cung cấp transaction cho việc gán nhiều property. Nếu cần cập nhật nhiều field như một đơn vị nghiệp vụ, hãy dùng method domain/service có kiểm soát transaction thay vì nhiều setValue độc lập.

## 19. Test helper để giảm lặp

Có thể tạo helper nhỏ trong test để tạo context hoặc đánh giá expression:

~~~java
private EvaluationContext readWriteContext() {
    return SimpleEvaluationContext
            .forReadWriteDataBinding()
            .build();
}

private <T> T evaluate(
        String source,
        Object root,
        Class<T> targetType) {

    Expression expression = parser.parseExpression(source);

    return expression.getValue(
            readWriteContext(),
            root,
            targetType
    );
}
~~~

Helper chỉ nên loại bỏ boilerplate. Không nên giấu exception hoặc tự động trả default khiến test không còn xác nhận đúng hành vi.

Với test cần custom TypeConverter, MethodResolver hoặc variables, hãy tạo context riêng trong test đó để cấu hình thể hiện rõ mục tiêu.

## 20. Ma trận kiểm thử conversion và binding

Một ma trận ngắn giúp kiểm tra đủ đường đi dữ liệu:

| Thao tác | Input hợp lệ | Input không hợp lệ |
|---|---|---|
| Typed getValue | String chuyển sang Integer | Chuỗi không phải số |
| Method argument | Đối số chuyển được sang kiểu tham số | Không có converter phù hợp |
| setValue property | Ghi được vào setter và conversion thành công | Property read-only hoặc conversion lỗi |
| Nested property | Object trung gian tồn tại | Object trung gian null |
| Map/List indexer | Key/index hợp lệ, collection mutable | Key thiếu, index ngoài phạm vi hoặc collection immutable |
| Custom converter | Input đúng định dạng domain | Input sai định dạng |
| Null | Kiểu tham chiếu chấp nhận null | Primitive hoặc logic không chấp nhận null |

Không phải mọi ứng dụng cần mọi hàng trong ma trận. Chọn các trường hợp tương ứng với object, converter và expression thực sự được sử dụng.

## 21. Lỗi kiểm thử thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Test parse pass nhưng runtime fail | Chưa evaluate với root object và context thực tế | Bổ sung evaluation test |
| Test conversion dùng context khác production | Converter không được cấu hình giống nhau | Dùng fixture tạo context production-like |
| Assertion chỉ kiểm tra toString() | Không xác nhận kiểu runtime | Assert kiểu đích và giá trị |
| Binding test không phát hiện property read-only | Chỉ test getter | Thêm test setValue |
| Test nested property không ổn định | Object trung gian chưa được khởi tạo rõ | Tạo fixture đầy đủ |
| Test lỗi phụ thuộc message text | Message thay đổi theo phiên bản | Assert exception type, cause hoặc message code |
| Test bỏ qua trạng thái sau lỗi | Setter có thể mutate trước khi ném exception | Assert object vẫn giữ invariant |
| Test unit pass nhưng @Value lỗi | Chưa kiểm tra Spring placeholder/annotation processing | Thêm integration test ApplicationContext |

## 22. Ghi nhớ

Kiểm thử SpEL cần tách parse, evaluate, conversion và binding. Typed getValue kiểm tra chuyển đổi kết quả; method invocation kiểm tra conversion đối số; setValue kiểm tra property accessor, setter và conversion vào kiểu đích. Custom TypeConverter hoặc ConversionService phải được cấu hình giống use case thực tế.

Hãy kiểm tra cả dữ liệu hợp lệ, sai định dạng, null, property chỉ đọc, object lồng nhau null, index không hợp lệ và collection không mutable. Sau thao tác ghi, xác nhận trạng thái object; sau thao tác thất bại, xác nhận invariant vẫn được giữ.

Dùng unit test cho expression và converter, parameterized test cho nhiều input, và Spring integration test cho @Value hoặc bean configuration. Conversion không thay validation; test kiểu dữ liệu và test quy tắc nghiệp vụ cần có mục tiêu riêng.