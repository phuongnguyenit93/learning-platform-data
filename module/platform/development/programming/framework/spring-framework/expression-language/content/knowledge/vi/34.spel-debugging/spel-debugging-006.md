# Phân tích lỗi do resolver hoặc converter trong SpEL

Khi Spring Expression Language (SpEL) đánh giá một expression, nhiều thành phần của EvaluationContext phối hợp để tìm property, method, constructor, bean và chuyển đổi kiểu dữ liệu. Nếu một thành phần không xử lý được yêu cầu, expression có thể parse thành công nhưng thất bại lúc runtime.

Để chẩn đoán đúng, cần xác định **bước nào đang thất bại** và **thành phần nào chịu trách nhiệm**. Lỗi không tìm thấy property thường liên quan PropertyAccessor; lỗi gọi method có thể liên quan MethodResolver hoặc kiểu đối số; lỗi chuyển kiểu liên quan TypeConverter. Chỉ nhìn dòng expression hoặc thông báo lỗi ngoài cùng thường chưa đủ để xác định nguyên nhân.

## 1. Phân biệt lỗi parse và lỗi evaluation

SpEL có hai giai đoạn chính:

    ExpressionParser parser = new SpelExpressionParser();

    Expression expression =
            parser.parseExpression("#order.total");

    Object value = expression.getValue(context);

`parseExpression(...)` phân tích cú pháp và tạo Expression. Lỗi cú pháp thường xuất hiện dưới dạng `SpelParseException`. Khi gọi `getValue(...)`, SpEL mới resolve property, variable, bean, method và converter trong EvaluationContext. Lỗi lúc này thường được biểu diễn bằng `SpelEvaluationException` hoặc một exception evaluation liên quan, có thể giữ nguyên nguyên nhân gốc ở bên dưới.

Ví dụ:

    Expression expression =
            parser.parseExpression("#order.customer.address.city");

Expression có thể parse thành công dù variable `order` chưa được đăng ký, hoặc `customer` đang null. Những vấn đề này chỉ xuất hiện khi đánh giá trong context thực tế.

Khi debug, hãy ghi nhận rõ lỗi xảy ra ở parse hay evaluate. Đừng thay đổi resolver hoặc converter nếu expression chưa qua được bước parse.

## 2. Nhận diện thành phần chịu trách nhiệm

EvaluationContext cung cấp các cơ chế khác nhau cho từng loại truy cập:

| Thành phần | Công việc | Dấu hiệu lỗi thường gặp |
|---|---|---|
| PropertyAccessor | Đọc hoặc ghi property | Không tìm thấy property, property không đọc/ghi được |
| MethodResolver | Tìm method phù hợp | Không tìm thấy method hoặc không phân giải được overload |
| ConstructorResolver | Tìm constructor | Không tìm thấy constructor phù hợp |
| BeanResolver | Resolve `@beanName` | Không tìm thấy bean hoặc resolver từ chối tên |
| TypeLocator | Resolve class trong `T(...)` hoặc `new` | Không tìm thấy class |
| TypeConverter | Chuyển giá trị sang kiểu đích | Không có converter hoặc giá trị không chuyển đổi được |

Không phải mọi lỗi đều do resolver. Một property có thể tồn tại nhưng target là null; một method có thể tồn tại nhưng đối số không tương thích; một converter có thể hỗ trợ cặp kiểu nhưng dữ liệu cụ thể vẫn sai định dạng.

Hãy bắt đầu từ thao tác đang được expression thực hiện, sau đó kiểm tra đúng thành phần của context.

## 3. Phân tích lỗi PropertyAccessor

PropertyAccessor chịu trách nhiệm đọc và ghi property trên target object. Khi SpEL truy cập:

    #order.customer.name

nó lần lượt đọc `customer` trên order rồi đọc `name` trên customer. Mỗi bước có thể cần accessor phù hợp với kiểu target tại bước đó.

Các nguyên nhân phổ biến:

- Target object không đúng kiểu mà accessor hỗ trợ.
- Tên property sai hoặc getter không theo quy ước JavaBean mà accessor nhận diện.
- Property trung gian trả về null.
- Accessor không hỗ trợ đọc hoặc ghi property.
- Nhiều accessor cùng hỗ trợ một target và thứ tự tìm kiếm khiến accessor khác được dùng trước.
- Custom accessor ném AccessException trong `read` hoặc `write`.

Có thể kiểm tra accessor trực tiếp:

    EvaluationContext context =
            new StandardEvaluationContext(order);

    for (PropertyAccessor accessor :
            context.getPropertyAccessors()) {
        boolean supported =
                accessor.canRead(context, order, "customer");

        System.out.println(
                accessor.getClass().getName() + ": " + supported
        );
    }

Đoạn code minh họa việc kiểm tra khả năng đọc trên target và property cụ thể. Nếu cần debug nested path, lặp lại kiểm tra với object trung gian thực tế và tên property ở cấp tiếp theo.

Với assignment, kiểm tra `canWrite(...)` và xác nhận setter hoặc cơ chế ghi của accessor thực sự hoạt động. `canWrite` trả true chỉ thể hiện khả năng kỹ thuật; policy ứng dụng vẫn phải quyết định có cho phép cập nhật hay không.

## 4. Phân tích lỗi MethodResolver

MethodResolver tìm method phù hợp với target object, tên method và kiểu đối số. Ví dụ:

    #pricingService.calculate(#amount, #customer.level)

Nếu expression báo không tìm thấy method, hãy kiểm tra:

1. Bean hoặc variable target đã được resolve chưa?
2. Target có null không?
3. Tên method có đúng chữ hoa/thường không?
4. Số lượng đối số có khớp không?
5. Kiểu runtime của từng đối số là gì?
6. Có overload nào nhận các kiểu đó không?
7. TypeConverter có hỗ trợ chuyển đổi cần thiết không?
8. Method có thể truy cập theo resolver hiện tại không?

Một method có thể tồn tại trong Java nhưng vẫn không được chọn nếu chữ ký không tương thích với các đối số runtime. Với overload, một chuỗi có thể phù hợp với method nhận String nhưng không phù hợp với method nhận Integer nếu không có converter tương ứng.

StandardEvaluationContext mặc định sử dụng reflective method resolution. Nếu ứng dụng thay resolver mặc định bằng custom MethodResolver, hãy kiểm tra danh sách resolver thực tế và logic trả về của từng resolver. Resolver tùy chỉnh có thể trả về executor khi tìm được method, trả null để cho resolver tiếp theo thử, hoặc ném AccessException khi gặp lỗi truy cập theo hợp đồng API.

## 5. Phân tích lỗi ConstructorResolver và TypeLocator

Với expression tạo object:

    new com.example.Customer('Lan', 25)

SpEL cần tìm class trước, rồi mới chọn constructor.

- **TypeLocator** tìm class theo tên.
- **ConstructorResolver** tìm constructor phù hợp với số lượng và kiểu đối số.
- **TypeConverter** có thể hỗ trợ chuyển đổi đối số sang kiểu constructor yêu cầu.

Nếu lỗi nói không tìm thấy type, kiểm tra tên package, classpath, classloader và TypeLocator. Nếu type đã được tìm thấy nhưng không có constructor phù hợp, kiểm tra constructor visibility, số lượng đối số, overload và khả năng chuyển đổi.

StandardTypeLocator mặc định nhận diện package `java.lang`. Với class khác, dùng tên đầy đủ hoặc đăng ký import prefix phù hợp:

    StandardTypeLocator locator =
            new StandardTypeLocator();

    locator.registerImport("com.example.domain");

    StandardEvaluationContext context =
            new StandardEvaluationContext();

    context.setTypeLocator(locator);

Nếu ứng dụng dùng custom TypeLocator hoặc ConstructorResolver, kiểm tra cấu hình của đúng EvaluationContext đang evaluate. Đừng nhầm lỗi không resolve được class với lỗi không gọi được constructor.

## 6. Phân tích lỗi BeanResolver

Cú pháp `@beanName` cần BeanResolver:

    @pricingService.defaultCurrency

Một StandardEvaluationContext tự tạo không tự động biết ApplicationContext. Nếu expression báo không resolve được bean, kiểm tra:

- Context đã được gọi `setBeanResolver(...)` chưa?
- Bean name có đúng tên hoặc alias trong BeanFactory không?
- Resolver có allowlist tên bean không?
- Bean có thuộc scope đang hoạt động không?
- Việc khởi tạo bean có thất bại do dependency hoặc cấu hình không?
- Expression đang chạy trong đúng ApplicationContext hay một context test khác?

Ví dụ cấu hình phổ biến:

    context.setBeanResolver(
            new BeanFactoryResolver(beanFactory)
    );

Nếu dùng custom BeanResolver, hãy kiểm tra tên bean đầu vào và kết quả tra cứu. Một resolver có thể cố ý từ chối bean ngoài allowlist; đó là hành vi policy, không nhất thiết là lỗi cấu hình.

Không khắc phục lỗi bằng cách expose toàn bộ ApplicationContext hoặc BeanFactory cho mọi expression. Chỉ cung cấp bean hoặc facade mà use case cần.

## 7. Phân tích lỗi TypeConverter

TypeConverter được dùng khi SpEL cần chuyển một giá trị sang kiểu đích, chẳng hạn lúc gán property, truyền đối số cho method/constructor hoặc lấy kết quả theo kiểu yêu cầu.

Hai thao tác chính:

    TypeConverter converter = context.getTypeConverter();

    boolean canConvert = converter.canConvert(
            TypeDescriptor.valueOf(String.class),
            TypeDescriptor.valueOf(Integer.class)
    );

    Object converted = converter.convertValue(
            "42",
            TypeDescriptor.valueOf(String.class),
            TypeDescriptor.valueOf(Integer.class)
    );

`canConvert` cho biết converter có hỗ trợ cặp kiểu được mô tả hay không. Nó không bảo đảm mọi giá trị cụ thể đều hợp lệ. Ví dụ chuỗi `"42"` có thể chuyển thành Integer, còn `"forty-two"` có thể thất bại dù cùng cặp kiểu String sang Integer.

Khi conversion thất bại, hãy kiểm tra:

- Kiểu nguồn thực tế, không chỉ kiểu bạn nghĩ biến đang có.
- Kiểu đích của property, tham số method hoặc constructor.
- Converter được đăng ký trong ConversionService.
- Giá trị cụ thể, định dạng, miền số và null.
- Metadata TypeDescriptor nếu conversion phụ thuộc generic collection hoặc annotation.

Các exception có thể xuất hiện ở nhiều lớp, ví dụ lỗi conversion của Spring hoặc exception được SpEL bọc trong lỗi evaluation. Hãy xem cause chain để tìm converter hoặc giá trị nguồn gây lỗi.

## 8. Phân biệt lỗi chọn method với lỗi chuyển đổi đối số

Hai loại lỗi này thường dễ nhầm. Method resolution quyết định method nào có thể nhận lời gọi; conversion hỗ trợ chuyển đối số sang kiểu tham số tương ứng.

Ví dụ Java:

    public String format(Integer value) {
        return "number=" + value;
    }

    public String format(String value) {
        return "text=" + value;
    }

Expression:

    #formatter.format(#input)

Nếu `input` là String, overload nhận String có thể được chọn trực tiếp. Nếu chỉ có method nhận Integer, SpEL cần converter phù hợp để chuyển String sang Integer. Nếu giá trị không chuyển đổi được, lỗi có thể xảy ra khi chuẩn bị lời gọi method.

Để tách nguyên nhân:

1. In kiểu runtime của từng đối số.
2. Xem chữ ký method đang có trên target.
3. Kiểm tra converter cho cặp kiểu nguồn/đích.
4. Thử chuyển đổi giá trị riêng bằng TypeConverter.
5. Thử gọi method bằng đối số đã chuẩn hóa kiểu trong Java.

Nếu method chạy được khi truyền Integer trực tiếp nhưng lỗi với String, vấn đề có thể nằm ở conversion hoặc overload resolution, không phải ở việc method không tồn tại.

## 9. Đăng ký và thứ tự resolver tùy chỉnh

StandardEvaluationContext cho phép thêm hoặc thay thế các resolver và accessor. Khi có nhiều implementation, thứ tự trong danh sách có thể ảnh hưởng thành phần được thử trước.

Ví dụ thêm một PropertyAccessor:

    context.addPropertyAccessor(
            new CustomerPropertyAccessor()
    );

Ví dụ thay danh sách MethodResolver cần được thực hiện có chủ đích:

    context.setMethodResolvers(
            List.of(customMethodResolver)
    );

Khi dùng `setMethodResolvers`, danh sách được cung cấp trở thành danh sách resolver của context. Nếu cần giữ reflective fallback, hãy đưa resolver đó vào danh sách theo thứ tự mà ứng dụng mong muốn. Tương tự, khi thay property accessors, đừng vô tình bỏ accessor mặc định mà các expression khác đang cần.

Để debug, ghi lại class của từng accessor/resolver và thứ tự chúng được đăng ký trong context. Kiểm tra cả implementation tùy chỉnh lẫn resolver mặc định. Không thêm nhiều resolver rộng quyền chỉ để làm mất lỗi; điều đó có thể che nguyên nhân và mở phạm vi truy cập ngoài dự kiến.

## 10. Tạo một test nhỏ tái hiện lỗi

Khi lỗi xảy ra trong một luồng lớn, hãy rút gọn thành test chỉ có expression, target, context và dependency cần thiết.

Ví dụ kiểm tra conversion độc lập:

    @Test
    void convertsStringToInteger() {
        StandardEvaluationContext context =
                new StandardEvaluationContext();

        Integer value = new SpelExpressionParser()
                .parseExpression("'42'")
                .getValue(context, Integer.class);

        assertEquals(42, value);
    }

Ví dụ kiểm tra property:

    @Test
    void readsNestedProperty() {
        StandardEvaluationContext context =
                new StandardEvaluationContext(order);

        String city = new SpelExpressionParser()
                .parseExpression("customer.address.city")
                .getValue(context, String.class);

        assertEquals("Da Nang", city);
    }

Sau khi test nhỏ tái hiện được lỗi, thêm lại từng thành phần: custom accessor, method resolver, bean resolver hoặc converter. Cách này giúp xác định thành phần nào làm thay đổi hành vi.

Nếu lỗi chỉ xuất hiện trong annotation, hãy kiểm thử qua đúng framework infrastructure và Spring-managed bean. Context tự tạo trong unit test có thể không giống context mà annotation handler cung cấp.

## 11. Ghi log đủ để chẩn đoán, không làm lộ dữ liệu

Thông tin hữu ích khi log lỗi gồm:

- Expression hoặc mã định danh expression đã được kiểm soát.
- Giai đoạn parse hay evaluate.
- Loại annotation hoặc use case đang xử lý.
- Loại target object và tên property/method liên quan.
- Kiểu nguồn và kiểu đích khi conversion thất bại.
- Loại resolver/accessor/converter đang được sử dụng.
- Exception gốc và cause chain.

Tránh ghi toàn bộ object, giá trị bí mật, token, thông tin cá nhân hoặc expression chứa dữ liệu nhạy cảm. Nếu expression do người dùng cấu hình, cân nhắc log ID của expression và phiên bản cấu hình thay vì toàn bộ chuỗi.

Không bắt exception rồi trả null hoặc giá trị mặc định một cách im lặng. Cách đó có thể biến lỗi cấu hình hoặc lỗi conversion thành kết quả nghiệp vụ sai. Hãy phân loại lỗi, giữ nguyên nguyên nhân gốc và xử lý theo chính sách fail-closed phù hợp với use case.

## 12. Checklist chẩn đoán nhanh

Khi một expression thất bại, đi theo thứ tự:

1. Parse có thành công không? Nếu không, kiểm tra cú pháp và vị trí lỗi.
2. EvaluationContext nào đang được dùng? Xác nhận root, variables và resolver.
3. Target ở bước lỗi có null hoặc sai kiểu không?
4. PropertyAccessor có hỗ trợ đọc/ghi target và property không?
5. MethodResolver có tìm được method theo tên, số lượng và kiểu đối số không?
6. BeanResolver có resolve được bean name không?
7. TypeLocator có tìm được class không?
8. ConstructorResolver có tìm được constructor phù hợp không?
9. TypeConverter có hỗ trợ cặp kiểu và giá trị cụ thể không?
10. Custom resolver/accessor/converter có ném exception hoặc che lỗi của implementation khác không?

Sau khi xác định nguyên nhân, sửa cấu hình hoặc dữ liệu tại đúng thành phần. Tránh thêm fallback rộng, expose thêm bean hoặc bật quyền ghi chỉ để expression không còn ném lỗi.

## 13. Ghi nhớ

Resolver và converter xử lý các phần khác nhau trong quá trình evaluate SpEL. PropertyAccessor đọc/ghi property; MethodResolver và ConstructorResolver tìm executable phù hợp; BeanResolver tìm bean; TypeLocator tìm class; TypeConverter chuyển đổi giá trị. Hãy phân biệt lỗi parse với lỗi evaluation, kiểm tra target và kiểu runtime, xem cause chain và xác nhận danh sách resolver thực tế của EvaluationContext. `canConvert` chỉ kiểm tra khả năng theo cặp kiểu, không xác nhận giá trị cụ thể hợp lệ. Giữ lỗi rõ ràng, tạo test tái hiện nhỏ và chỉ sửa đúng thành phần gây lỗi; không mở rộng quyền truy cập hoặc nuốt exception để che vấn đề.
