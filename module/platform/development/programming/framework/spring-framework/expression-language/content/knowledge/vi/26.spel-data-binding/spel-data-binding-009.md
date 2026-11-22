# Kiểm thử binding với dữ liệu thiếu, null và sai kiểu trong SpEL

## 1. Mục tiêu của kiểm thử data binding

Data binding đưa dữ liệu đầu vào vào các property của object. Trong ứng dụng Spring, dữ liệu có thể đến từ request, cấu hình, form hoặc một object trung gian. Các tình huống cần được kiểm tra không chỉ là dữ liệu hợp lệ, mà còn gồm field không được gửi, giá trị null, chuỗi rỗng và giá trị không thể chuyển đổi sang kiểu đích.

SpEL có thể ghi property thông qua expression và EvaluationContext. Khi expression gán giá trị vào property có kiểu khác với giá trị đầu vào, SpEL sử dụng TypeConverter của context để chuyển đổi nếu có thể.

Ví dụ, expression ghi String vào property Integer:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression = parser.parseExpression("quantity");
expression.setValue(context, target, "12");
~~~

Một bài test binding nên xác nhận ba điều:

- Object đích nhận đúng giá trị khi dữ liệu hợp lệ.
- Object giữ trạng thái phù hợp khi dữ liệu không được gửi hoặc giá trị là null.
- Dữ liệu sai kiểu được báo lỗi theo đúng contract, không âm thầm tạo ra giá trị nghiệp vụ sai.

Cần phân biệt SpEL property binding với Spring DataBinder. SpEL đánh giá một expression cụ thể và thực hiện thao tác được expression mô tả. DataBinder bind một tập property values vào object và cung cấp BindingResult để báo lỗi binding. Hai cơ chế có thể cùng dùng Spring conversion infrastructure, nhưng cách quan sát lỗi và phạm vi thao tác khác nhau.

## 2. Chuẩn bị object đích cho test

Fixture nên nhỏ, có property getter/setter rõ ràng và chứa những kiểu dữ liệu cần kiểm tra. Dùng wrapper như Integer hoặc Boolean khi property có thể nhận null; kiểu primitive như int và boolean không thể lưu null.

~~~java
public class BindingTarget {
    private String name = "Existing";
    private Integer quantity = 5;
    private Boolean enabled = true;
    private int retryCount = 2;

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public Integer getQuantity() {
        return quantity;
    }

    public void setQuantity(Integer quantity) {
        this.quantity = quantity;
    }

    public Boolean getEnabled() {
        return enabled;
    }

    public void setEnabled(Boolean enabled) {
        this.enabled = enabled;
    }

    public int getRetryCount() {
        return retryCount;
    }

    public void setRetryCount(int retryCount) {
        this.retryCount = retryCount;
    }
}
~~~

Các giá trị ban đầu có chủ đích:

- name đã có giá trị để xác nhận field không được gửi sẽ giữ nguyên.
- quantity là Integer để có thể kiểm tra cả số hợp lệ, null và chuỗi không phải số.
- enabled là Boolean wrapper để phân biệt false với null.
- retryCount là primitive int để minh họa giới hạn khi dữ liệu null được gán vào primitive.

Không nên dùng một object quá lớn cho mọi test. Fixture nhỏ làm rõ property nào đang được bind và trạng thái nào cần được xác nhận.

## 3. Tạo SimpleEvaluationContext cho data binding

Khi expression chỉ cần đọc hoặc ghi property, SimpleEvaluationContext là lựa chọn giới hạn hơn StandardEvaluationContext. Builder data binding cấu hình property accessor phù hợp:

~~~java
SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadWriteDataBinding().build();
~~~

Đối với test chỉ đọc property:

~~~java
SimpleEvaluationContext readOnlyContext =
        SimpleEvaluationContext.forReadOnlyDataBinding().build();
~~~

SimpleEvaluationContext không bật toàn bộ khả năng SpEL như type references hoặc method resolution rộng theo mặc định. Đây là lựa chọn phù hợp khi mục tiêu là data binding vào property và muốn giới hạn khả năng của expression.

Nếu test cần custom ConversionService, có thể gắn service vào builder:

~~~java
SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadWriteDataBinding()
                .withConversionService(conversionService)
                .build();
~~~

Hãy tạo context theo đúng quyền mà expression cần. Nếu chỉ kiểm tra property binding, không cần cấp thêm type access hoặc method execution.

## 4. Kiểm thử binding với dữ liệu hợp lệ

Bắt đầu bằng trường hợp dữ liệu hợp lệ để xác nhận expression có thể ghi property và chuyển đổi giá trị nếu cần:

~~~java
@Test
void bindsStringValueToIntegerProperty() {
    BindingTarget target = new BindingTarget();

    SimpleEvaluationContext context =
            SimpleEvaluationContext.forReadWriteDataBinding().build();

    Expression expression =
            new SpelExpressionParser().parseExpression("quantity");

    expression.setValue(context, target, "12");

    assertEquals(Integer.valueOf(12), target.getQuantity());
}
~~~

Expression target là property quantity có kiểu Integer. Giá trị đầu vào là String "12"; conversion service mặc định có thể chuyển String thành Integer.

Có thể kiểm tra property String không cần chuyển đổi:

~~~java
@Test
void bindsStringProperty() {
    BindingTarget target = new BindingTarget();

    SimpleEvaluationContext context =
            SimpleEvaluationContext.forReadWriteDataBinding().build();

    new SpelExpressionParser()
            .parseExpression("name")
            .setValue(context, target, "Lan");

    assertEquals("Lan", target.getName());
}
~~~

Các test này xác nhận đường đi cơ bản trước khi kiểm tra dữ liệu thiếu, null hoặc sai kiểu.

## 5. Dữ liệu thiếu khác với giá trị null

Dữ liệu thiếu nghĩa là đầu vào không chứa property đó. Nếu không có thao tác bind vào property, giá trị hiện tại của object đích thường được giữ nguyên.

Giá trị null nghĩa là đầu vào có property nhưng giá trị của nó là null. Nếu binder thực hiện thao tác gán null và property đích cho phép null, giá trị cũ có thể bị thay bằng null.

Hai trường hợp này không nên được gộp thành một:

| Đầu vào | Hành vi binding dự kiến |
|---|---|
| Không có key name | Không có thao tác gán name; giữ giá trị hiện tại |
| Có key name với giá trị null | Thực hiện gán null nếu binder/target cho phép |
| Có key name với chuỗi rỗng | Gán chuỗi rỗng hoặc áp dụng quy tắc empty-value riêng |
| Có key name với chuỗi hợp lệ | Chuyển đổi và gán giá trị tương ứng |

Trong test, hãy tạo input không chứa property để mô phỏng field bị bỏ qua. Đừng thay dữ liệu thiếu bằng null trong fixture, vì điều đó kiểm tra một tình huống khác.

## 6. Kiểm thử property bị thiếu với Spring DataBinder

DataBinder nhận property values và bind chúng vào target object. Nếu một property không xuất hiện trong MutablePropertyValues, binder không có giá trị nào để gán cho property đó.

~~~java
@Test
void missingPropertyKeepsExistingValue() {
    BindingTarget target = new BindingTarget();
    DataBinder binder = new DataBinder(target);

    MutablePropertyValues values = new MutablePropertyValues();
    values.add("enabled", "false");

    binder.bind(values);

    assertEquals("Existing", target.getName());
    assertEquals(Boolean.FALSE, target.getEnabled());
    assertFalse(binder.getBindingResult().hasFieldErrors("name"));
}
~~~

Test này chỉ gửi enabled. Property name không xuất hiện trong input nên giá trị ban đầu "Existing" được giữ nguyên.

Đây là hành vi thường mong muốn với partial update: client chỉ gửi những field muốn thay đổi. Nếu ứng dụng cần phân biệt field không có trong request với field có mặt nhưng null, hãy giữ nguyên thông tin presence từ request mapping hoặc binding layer thay vì chỉ kiểm tra giá trị sau khi bind.

## 7. Kiểm thử null với property wrapper

Property dùng wrapper như Integer, Boolean hoặc một reference type có thể nhận null nếu setter và quy tắc nghiệp vụ cho phép.

Với DataBinder:

~~~java
@Test
void explicitNullClearsNullableProperty() {
    BindingTarget target = new BindingTarget();
    DataBinder binder = new DataBinder(target);

    MutablePropertyValues values = new MutablePropertyValues();
    values.add("quantity", null);

    binder.bind(values);

    assertNull(target.getQuantity());
    assertFalse(binder.getBindingResult().hasFieldErrors("quantity"));
}
~~~

Ở đây quantity có mặt trong input và giá trị của nó là null. Binder thực hiện binding vào property wrapper, nên giá trị trước đó được xóa nếu không có constraint hoặc setter logic từ chối null.

Có thể kiểm tra null trực tiếp qua SpEL:

~~~java
@Test
void spelCanSetNullablePropertyToNull() {
    BindingTarget target = new BindingTarget();

    SimpleEvaluationContext context =
            SimpleEvaluationContext.forReadWriteDataBinding().build();

    Expression expression =
            new SpelExpressionParser().parseExpression("quantity");

    expression.setValue(context, target, null);

    assertNull(target.getQuantity());
}
~~~

Test này xác nhận expression có thể ghi null vào property reference type. Nếu ứng dụng không cho phép null, hãy kiểm tra validation hoặc setter contract riêng. Khả năng gán null ở tầng binding không đồng nghĩa giá trị đó hợp lệ về nghiệp vụ.

## 8. Kiểm thử null với primitive property

Primitive như int và boolean không thể biểu diễn null. Nếu input có key nhưng giá trị null, việc chuyển đổi/gán vào primitive có thể thất bại hoặc cần chính sách xử lý rõ ràng của binding layer.

Không nên giả định primitive tự động trở thành zero hoặc false mà không kiểm tra hành vi của API đang dùng. Viết test trên đúng Spring version và cấu hình thực tế:

~~~java
@Test
void reportsNullForPrimitivePropertyAccordingToBindingPolicy() {
    BindingTarget target = new BindingTarget();
    DataBinder binder = new DataBinder(target);

    MutablePropertyValues values = new MutablePropertyValues();
    values.add("retryCount", null);

    binder.bind(values);

    // Xác nhận BindingResult và giá trị target theo policy của ứng dụng.
    // Nếu null không được phép, yêu cầu có field error hoặc validation error.
}
~~~

Với request model cần phân biệt không gửi và gửi null, wrapper thường phù hợp hơn primitive. Ví dụ Integer cho phép biểu diễn cả “chưa có giá trị” và số 0. Sau đó validation hoặc business logic quyết định null có được chấp nhận hay không.

Nếu ứng dụng cần default 0 khi thiếu field, hãy áp dụng default ở tầng DTO, binding hoặc service theo quy tắc rõ ràng. Đừng để default của primitive vô tình che mất việc client đã gửi null.

## 9. Kiểm thử chuỗi rỗng và whitespace

Chuỗi rỗng không giống null. Với property String, chuỗi rỗng thường được bind thành chính chuỗi rỗng. Với property số, Boolean hoặc kiểu miền nghiệp vụ, chuỗi rỗng có thể được xử lý theo conversion service, property editor hoặc binder configuration.

Ví dụ với String:

~~~java
@Test
void bindsEmptyStringAsEmptyString() {
    BindingTarget target = new BindingTarget();
    DataBinder binder = new DataBinder(target);

    MutablePropertyValues values = new MutablePropertyValues();
    values.add("name", "");

    binder.bind(values);

    assertEquals("", target.getName());
}
~~~

Whitespace cũng cần được kiểm tra riêng nếu ứng dụng trim dữ liệu:

~~~java
MutablePropertyValues values = new MutablePropertyValues();
values.add("name", "   ");

DataBinder binder = new DataBinder(new BindingTarget());
binder.bind(values);
~~~

DataBinder không nên được giả định là tự trim mọi String. Nếu yêu cầu nghiệp vụ là loại bỏ khoảng trắng, cấu hình StringTrimmerEditor hoặc xử lý normalization có chủ đích, rồi kiểm thử kết quả sau binding.

Ví dụ đăng ký editor cho String:

~~~java
binder.registerCustomEditor(
        String.class,
        new StringTrimmerEditor(true));
~~~

Tham số true yêu cầu chuỗi rỗng sau trim được chuyển thành null. Vì vậy, kết quả của whitespace có thể khác với chuỗi rỗng khi không đăng ký editor. Hãy ghi rõ chính sách này trong test.

## 10. Kiểm thử dữ liệu sai kiểu với SpEL

Khi expression gán String không thể chuyển đổi sang kiểu property đích, SpEL có thể phát sinh EvaluationException, thường là một SpelEvaluationException chứa thông tin lỗi chuyển đổi.

Ví dụ, quantity là Integer nhưng input không phải số:

~~~java
@Test
void rejectsInvalidNumberInSpelBinding() {
    BindingTarget target = new BindingTarget();

    SimpleEvaluationContext context =
            SimpleEvaluationContext.forReadWriteDataBinding().build();

    Expression expression =
            new SpelExpressionParser().parseExpression("quantity");

    assertThrows(
            EvaluationException.class,
            () -> expression.setValue(context, target, "twelve"));

    assertEquals(Integer.valueOf(5), target.getQuantity());
}
~~~

Test xác nhận dữ liệu không hợp lệ không được ghi thành giá trị mới. Giá trị cũ được giữ nguyên nếu quá trình chuyển đổi thất bại trước khi setter được gọi.

Trong code xử lý lỗi, có thể kiểm tra exception cụ thể hơn nếu ứng dụng phụ thuộc vào mã lỗi SpEL. Tránh phụ thuộc vào toàn bộ message text vì nội dung message có thể thay đổi giữa phiên bản hoặc locale.

## 11. Kiểm thử sai kiểu với DataBinder và BindingResult

DataBinder thường thu thập lỗi chuyển đổi vào BindingResult thay vì yêu cầu test phải bắt exception trực tiếp. Khi một String không thể chuyển thành Integer, field error thường có code typeMismatch.

~~~java
@Test
void recordsTypeMismatchForInvalidInteger() {
    BindingTarget target = new BindingTarget();
    DataBinder binder = new DataBinder(target);

    MutablePropertyValues values = new MutablePropertyValues();
    values.add("quantity", "twelve");

    binder.bind(values);

    BindingResult result = binder.getBindingResult();

    assertTrue(result.hasFieldErrors("quantity"));
    assertEquals("typeMismatch", result.getFieldError("quantity").getCode());
    assertEquals(Integer.valueOf(5), target.getQuantity());
}
~~~

Kết quả quan trọng cần kiểm tra:

- BindingResult có field error tại quantity.
- Mã lỗi thể hiện type mismatch.
- Property không bị thay bằng một giá trị sai.
- Giá trị cũ vẫn được giữ nếu conversion thất bại trước khi gán.

DataBinder cho phép ứng dụng hiển thị lỗi theo field và trả lại form/request validation phù hợp. Với SpEL setValue trực tiếp, lỗi thường xuất hiện như exception trong quá trình evaluate. Vì vậy, không dùng cùng một assertion cho hai API.

## 12. Kết hợp ConversionService trong test binding

Khi ứng dụng đăng ký custom converter, test nên dùng đúng ConversionService mà cấu hình production sẽ cung cấp:

~~~java
DefaultConversionService conversionService =
        new DefaultConversionService();

conversionService.addConverter(new StringToMoneyConverter());
~~~

Với SpEL:

~~~java
SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadWriteDataBinding()
                .withConversionService(conversionService)
                .build();

Expression expression =
        new SpelExpressionParser().parseExpression("amount");

expression.setValue(context, invoice, "125.50");
~~~

Với DataBinder:

~~~java
DataBinder binder = new DataBinder(invoice);
binder.setConversionService(conversionService);

MutablePropertyValues values = new MutablePropertyValues();
values.add("amount", "125.50");

binder.bind(values);
~~~

Dùng cùng ConversionService giúp hai luồng có chung quy tắc chuyển đổi, nhưng vẫn cần test riêng từng API. Test SpEL xác nhận TypeConverter của EvaluationContext sử dụng service; test DataBinder xác nhận binder được cấu hình với service đó và báo lỗi qua BindingResult.

## 13. Kiểm thử validation sau binding

Binding và validation là hai bước khác nhau. Binding chuyển dữ liệu vào object; validation kiểm tra object có đáp ứng các quy tắc nghiệp vụ hay không.

Ví dụ property quantity có thể bind thành Integer hợp lệ về kiểu nhưng không hợp lệ về miền giá trị:

~~~java
public class QuantityForm {
    @Min(1)
    private Integer quantity;

    public Integer getQuantity() {
        return quantity;
    }

    public void setQuantity(Integer quantity) {
        this.quantity = quantity;
    }
}
~~~

Test có thể bind giá trị 0 rồi chạy validator:

~~~java
@Test
void validatesBoundValueAfterConversion() {
    QuantityForm form = new QuantityForm();
    DataBinder binder = new DataBinder(form);

    MutablePropertyValues values = new MutablePropertyValues();
    values.add("quantity", "0");

    binder.bind(values);
    binder.validate();

    assertEquals(Integer.valueOf(0), form.getQuantity());
    assertTrue(binder.getBindingResult().hasFieldErrors("quantity"));
}
~~~

Giá trị "0" chuyển đổi thành Integer thành công, nhưng vi phạm @Min(1). Đây là validation error, khác với type mismatch khi chuỗi không thể chuyển thành Integer.

Nếu dùng JSR-303/Bean Validation, ứng dụng cần validator tương ứng trên classpath và được cấu hình trong binder. Trong test tích hợp, hãy dùng cùng validator configuration với ứng dụng thật.

## 14. Lập ma trận test cho missing, null và sai kiểu

Một ma trận ngắn giúp tránh bỏ sót các trường hợp quan trọng:

| Trường hợp | Input | Kết quả cần xác nhận |
|---|---|---|
| Missing | Không có property | Giá trị hiện tại giữ nguyên |
| Explicit null | Property có mặt, value null | Wrapper property nhận null nếu được phép |
| Empty String | Property có mặt, value là chuỗi rỗng | Theo property type và editor/converter |
| Whitespace | Property có mặt, chỉ có khoảng trắng | Theo chính sách trim/normalization |
| Valid type text | Ví dụ "12" cho Integer | Chuyển đổi thành công |
| Invalid type text | Ví dụ "twelve" cho Integer | EvaluationException với SpEL hoặc field error với DataBinder |
| Valid but rejected by validation | Ví dụ 0 cho @Min(1) | Binding thành công, validation error |
| Null to primitive | Null cho int/boolean | Theo binding policy; xác nhận lỗi hoặc default được cấu hình rõ |

Không phải mọi property đều cần mọi test case. Chọn ma trận theo kiểu dữ liệu, contract của DTO và chính sách binding thực tế. Với property nullable, kiểm tra null; với property số, kiểm tra chuỗi hợp lệ và không hợp lệ; với String, kiểm tra empty và whitespace nếu có normalization.

## 15. Kiểm thử không làm lẫn dữ liệu thiếu với null

Một lỗi phổ biến là dựng request fixture bằng cách khởi tạo tất cả key với giá trị null. Điều đó mô phỏng “có key và value null”, không phải “key bị thiếu”.

Ví dụ:

~~~java
Map<String, Object> input = new HashMap<>();
input.put("name", null);
~~~

Map trên có key name. Nếu muốn mô phỏng missing field, không thêm key:

~~~java
Map<String, Object> input = new HashMap<>();
input.put("quantity", "12");
~~~

Khi chuyển Map thành MutablePropertyValues, chỉ những property có trong map mới được gửi cho binder. Nếu request parser hoặc framework tạo DTO trước khi binding, hãy kiểm tra cách nó giữ thông tin field presence; một DTO đã khởi tạo với null có thể không đủ để phân biệt missing và explicit null.

Đối với PATCH API, sự khác biệt này đặc biệt quan trọng. Missing thường có nghĩa “không thay đổi”; explicit null có thể có nghĩa “xóa giá trị”. Hãy kiểm thử ở đúng tầng nhận request để xác nhận semantics đó không bị mất trước khi binder chạy.

## 16. Giới hạn property được phép bind

Data binding có thể thay đổi trạng thái object. Không nên cho phép client bind tùy ý mọi property của domain object, đặc biệt các field nhạy cảm như role, owner, internal status hoặc audit metadata.

DataBinder hỗ trợ giới hạn property bằng allowed fields:

~~~java
DataBinder binder = new DataBinder(target);

binder.setAllowedFields("name", "quantity", "enabled");
~~~

Sau đó chỉ những property nằm trong danh sách cho phép mới được bind. Hãy kiểm thử cả field hợp lệ và field bị loại khỏi phạm vi binding theo policy ứng dụng.

Với SpEL, giới hạn expression và EvaluationContext theo đúng mục đích. Dùng SimpleEvaluationContext với property access phù hợp khi chỉ cần data binding; không đánh giá expression không tin cậy bằng context có quyền rộng hơn mức cần thiết.

## 17. Ví dụ tổng hợp với JUnit 5

Ví dụ sau kiểm tra missing field, explicit null và type mismatch bằng DataBinder:

~~~java
class BindingInputTest {

    @Test
    void missingFieldLeavesTargetUnchanged() {
        BindingTarget target = new BindingTarget();
        DataBinder binder = new DataBinder(target);

        MutablePropertyValues values = new MutablePropertyValues();
        values.add("enabled", "false");

        binder.bind(values);

        assertEquals("Existing", target.getName());
        assertEquals(Boolean.FALSE, target.getEnabled());
        assertFalse(binder.getBindingResult().hasFieldErrors());
    }

    @Test
    void explicitNullClearsNullableField() {
        BindingTarget target = new BindingTarget();
        DataBinder binder = new DataBinder(target);

        MutablePropertyValues values = new MutablePropertyValues();
        values.add("quantity", null);

        binder.bind(values);

        assertNull(target.getQuantity());
        assertFalse(binder.getBindingResult().hasFieldErrors());
    }

    @Test
    void invalidNumberProducesFieldError() {
        BindingTarget target = new BindingTarget();
        DataBinder binder = new DataBinder(target);

        MutablePropertyValues values = new MutablePropertyValues();
        values.add("quantity", "twelve");

        binder.bind(values);

        assertEquals(Integer.valueOf(5), target.getQuantity());
        assertTrue(binder.getBindingResult().hasFieldErrors("quantity"));
    }
}
~~~

Ba test dùng cùng fixture nhưng tạo input riêng cho từng trạng thái. Test missing không thêm name; test null thêm quantity với giá trị null; test sai kiểu thêm quantity với chuỗi không thể chuyển đổi.

Đối với SpEL trực tiếp, có thể bổ sung test riêng cho setValue với SimpleEvaluationContext để xác nhận expression dùng đúng property path và conversion service. Không nên suy ra hành vi exception của SpEL từ BindingResult của DataBinder.

## 18. Lỗi thường gặp

**Coi missing và explicit null là một**

Không có key nghĩa là binder không có property value để gán. Có key với null nghĩa là có thao tác bind null. Hãy tạo input riêng cho hai tình huống.

**Dùng primitive cho property cần biểu diễn null**

int và boolean không thể lưu null. Dùng Integer hoặc Boolean khi cần phân biệt null với 0 hoặc false.

**Giả định sai kiểu luôn làm request thất bại ngay**

DataBinder thường ghi lỗi vào BindingResult; SpEL setValue thường phát sinh EvaluationException. Hãy kiểm tra đúng cơ chế đang dùng.

**Chỉ kiểm tra lỗi mà không kiểm tra object đích**

Khi conversion thất bại, xác nhận giá trị cũ không bị ghi thành dữ liệu sai. Khi null được chấp nhận, xác nhận property thực sự được xóa.

**Nhầm conversion error với validation error**

Chuỗi "twelve" không thể chuyển thành Integer là type mismatch. Số 0 chuyển thành Integer thành công nhưng có thể vi phạm @Min(1). Hai trường hợp cần assertion khác nhau.

**Giả định chuỗi rỗng luôn là null**

String rỗng là giá trị riêng. Chỉ khi có converter, property editor hoặc normalization policy thì nó mới được chuyển thành null.

**Không kiểm tra cấu hình ConversionService**

Một context hoặc binder dùng service khác có thể có kết quả chuyển đổi khác. Trong test tích hợp, dùng đúng cấu hình converter mà ứng dụng triển khai.

## 19. Ghi nhớ

- Kiểm thử binding với ít nhất ba trạng thái: property bị thiếu, property có giá trị null và property có giá trị sai kiểu.
- Missing field thường không tạo thao tác gán nên giá trị hiện tại được giữ nguyên.
- Explicit null có thể xóa giá trị của property reference type nếu binding policy cho phép.
- Primitive không thể biểu diễn null; dùng wrapper khi cần trạng thái nullable.
- SpEL ghi property qua Expression.setValue và TypeConverter của EvaluationContext.
- SimpleEvaluationContext.forReadWriteDataBinding phù hợp cho expression chỉ cần property data binding.
- DataBinder bind MutablePropertyValues và báo lỗi chuyển đổi qua BindingResult.
- Với SpEL, kiểm tra exception khi conversion thất bại; với DataBinder, kiểm tra field error và trạng thái object.
- Phân biệt type mismatch với validation error sau khi chuyển đổi thành công.
- Kiểm thử empty String, whitespace và custom ConversionService theo chính sách ứng dụng.
- Giới hạn property được phép bind và không đánh giá expression không tin cậy bằng context có quyền quá rộng.
