# So sánh chuỗi, số và các kiểu có thể chuyển đổi trong SpEL

## 1. Tổng quan về phép so sánh

Spring Expression Language (SpEL) hỗ trợ các toán tử quan hệ để so sánh hai giá trị và trả về kết quả Boolean:

| Toán tử | Tên | Ví dụ | Kết quả |
|---|---|---|---|
| `==` | Bằng | `2 == 2` | `true` |
| `!=` | Khác | `2 != 3` | `true` |
| `<` | Nhỏ hơn | `2 < 5` | `true` |
| `>` | Lớn hơn | `8 > 5` | `true` |
| `<=` | Nhỏ hơn hoặc bằng | `5 <= 5` | `true` |
| `>=` | Lớn hơn hoặc bằng | `8 >= 9` | `false` |

Các toán tử quan hệ hoạt động với giá trị thuộc kiểu `Number` và các kiểu triển khai `Comparable`. Vì vậy, có thể so sánh số, chuỗi và các object có thứ tự tự nhiên được định nghĩa bởi `compareTo`.

Ví dụ dùng parser:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Boolean numberCheck =
        parser.parseExpression("10 > 5").getValue(Boolean.class);

Boolean stringCheck =
        parser.parseExpression("'black' < 'block'").getValue(Boolean.class);

System.out.println(numberCheck); // true
System.out.println(stringCheck); // true
~~~

Kết quả của biểu thức so sánh là `Boolean`. Có thể đánh giá biểu thức trên literal trực tiếp, trên root object hoặc trên variables trong `EvaluationContext`.

## 2. So sánh các giá trị số

Với hai toán hạng là số, SpEL thực hiện so sánh theo giá trị số học. Các biểu thức có thể dùng số nguyên, số thập phân và những kiểu số khác nhau:

~~~java
Boolean first = parser.parseExpression("10 > 5").getValue(Boolean.class);
Boolean second = parser.parseExpression("2 < 10.0").getValue(Boolean.class);
Boolean third = parser.parseExpression("2 == 2.0").getValue(Boolean.class);

System.out.println(first);  // true
System.out.println(second); // true
System.out.println(third);  // true
~~~

Phép so sánh số không phải phép so sánh chuỗi biểu diễn của số. Giá trị số nguyên `2` và giá trị số thập phân `2.0` có cùng giá trị số học, vì vậy có thể được xem là bằng nhau trong so sánh số.

Có thể dùng các biến thay cho literal:

~~~java
StandardEvaluationContext context = new StandardEvaluationContext();
context.setVariable("minimum", 100);
context.setVariable("actual", 125.5);

Expression expression =
        parser.parseExpression("#actual >= #minimum");

Boolean accepted = expression.getValue(context, Boolean.class);
System.out.println(accepted); // true
~~~

Cách này hữu ích khi ngưỡng và dữ liệu đến từ cấu hình hoặc object runtime. Expression vẫn giữ nguyên trong khi giá trị variables có thể thay đổi.

## 3. So sánh chuỗi theo thứ tự từ điển

Trong SpEL, `String` triển khai `Comparable`, do đó các toán tử `<`, `>`, `<=`, `>=` có thể so sánh chuỗi theo thứ tự từ điển (lexicographic order) của `String.compareTo` trong Java.

~~~java
Boolean result = parser.parseExpression("'black' < 'block'")
        .getValue(Boolean.class);

System.out.println(result); // true
~~~

Việc so sánh đi từ ký tự đầu tiên. Khi gặp cặp ký tự khác nhau đầu tiên, thứ tự của cặp ký tự đó quyết định kết quả. Nếu một chuỗi là tiền tố của chuỗi còn lại, chuỗi ngắn hơn đứng trước.

Ví dụ:

~~~java
Boolean a = parser.parseExpression("'ant' < 'bat'").getValue(Boolean.class);
Boolean b = parser.parseExpression("'app' < 'apple'").getValue(Boolean.class);
Boolean c = parser.parseExpression("'zebra' > 'apple'").getValue(Boolean.class);

System.out.println(a); // true
System.out.println(b); // true
System.out.println(c); // true
~~~

So sánh chuỗi mặc định có phân biệt chữ hoa và chữ thường. Nó không tự áp dụng quy tắc sắp xếp theo ngôn ngữ tự nhiên, locale hoặc quy tắc collation của cơ sở dữ liệu. Vì vậy, không nên dùng `<` hoặc `>` để thay thế việc sắp xếp tên người, địa chỉ hoặc nội dung đa ngôn ngữ theo locale.

Ví dụ `'Spring'` và `'spring'` khác nhau khi so sánh chính xác:

~~~java
Boolean sameCase = parser.parseExpression("'Spring' == 'Spring'")
        .getValue(Boolean.class);

Boolean differentCase = parser.parseExpression("'Spring' == 'spring'")
        .getValue(Boolean.class);

System.out.println(sameCase);      // true
System.out.println(differentCase); // false
~~~

Nếu nghiệp vụ cần so sánh không phân biệt hoa thường, hãy chuẩn hóa dữ liệu bằng một quy tắc rõ ràng, ví dụ gọi `toLowerCase()` trên cả hai phía hoặc dùng method Java chuyên biệt. Với ngôn ngữ cần xử lý locale, hãy dùng `Collator` hoặc cơ chế so sánh phù hợp thay vì giả định `String.compareTo` là so sánh ngôn ngữ tự nhiên.

## 4. So sánh bằng và khác

Toán tử `==` kiểm tra hai giá trị có bằng nhau theo ngữ nghĩa của SpEL; `!=` là phép phủ định tương ứng.

~~~java
Boolean sameNumber =
        parser.parseExpression("100 == 100").getValue(Boolean.class);

Boolean differentNumber =
        parser.parseExpression("100 != 99").getValue(Boolean.class);

Boolean sameText =
        parser.parseExpression("'paid' == 'paid'").getValue(Boolean.class);

System.out.println(sameNumber);     // true
System.out.println(differentNumber); // true
System.out.println(sameText);       // true
~~~

Với chuỗi, phép bằng phân biệt hoa thường và so sánh nội dung. Với số, SpEL so sánh theo giá trị số học; không nên nhầm với việc so sánh cách viết của literal.

Nếu cần kiểm tra cùng một object instance, hãy phân biệt phép bằng với phép đồng nhất tham chiếu. Trong Java, `equals()` và `==` có thể có ý nghĩa khác nhau đối với object; khi nghiệp vụ cần kiểm tra identity, có thể gọi method Java phù hợp hoặc thiết kế một biểu thức rõ ràng. Không nên suy luận rằng hai object bằng nhau về nội dung thì nhất thiết là cùng một instance.

## 5. So sánh các object triển khai Comparable

Ngoài `Number` và `String`, SpEL có thể so sánh các object triển khai `java.lang.Comparable`. Kết quả phụ thuộc vào quy tắc `compareTo` do kiểu đó định nghĩa.

Ví dụ, một kiểu phiên bản có thể so sánh theo số phiên bản:

~~~java
public final class Version implements Comparable<Version> {
    private final int major;

    public Version(int major) {
        this.major = major;
    }

    @Override
    public int compareTo(Version other) {
        return Integer.compare(this.major, other.major);
    }
}
~~~

Nếu root object chứa hai giá trị `Version`, biểu thức có thể so sánh chúng bằng toán tử quan hệ:

~~~java
Expression expression = parser.parseExpression("currentVersion < requiredVersion");

Boolean needsUpgrade =
        expression.getValue(versionInfo, Boolean.class);
~~~

Ví dụ này yêu cầu `versionInfo` có các property `currentVersion` và `requiredVersion`, đồng thời hai giá trị có kiểu có thể so sánh tương thích. Hãy thiết kế `compareTo` sao cho thứ tự nhất quán với ý nghĩa nghiệp vụ; SpEL sử dụng thứ tự do kiểu Java cung cấp chứ không tự suy ra quy tắc so sánh cho object tùy chỉnh.

Nếu hai object không thể so sánh với nhau, hoặc `compareTo` từ chối kiểu đầu vào, việc đánh giá có thể phát sinh lỗi. Không nên giả định mọi object đều có thứ tự tự nhiên.

## 6. So sánh chuỗi với số: chuyển đổi tường minh

Một chuỗi chứa chữ số vẫn là `String`, không tự động trở thành một giá trị số chỉ vì nội dung trông giống số.

Ví dụ, `'10'` và `'2'` là hai string literal. So sánh chúng theo thứ tự chuỗi sẽ cho kết quả khác với so sánh hai số:

~~~java
Boolean lexical = parser.parseExpression("'10' < '2'")
        .getValue(Boolean.class);

Boolean numeric = parser.parseExpression("10 < 2")
        .getValue(Boolean.class);

System.out.println(lexical); // true
System.out.println(numeric); // false
~~~

Trong so sánh chuỗi, ký tự đầu tiên `'1'` đứng trước `'2'`, nên `'10' < '2'` là true. Trong so sánh số, mười lớn hơn hai, nên `10 < 2` là false.

Khi dữ liệu số đến từ form, file cấu hình hoặc JSON dưới dạng chuỗi, hãy chuyển đổi nó sang kiểu số trước khi so sánh. Có thể chuyển đổi trong Java:

~~~java
String rawValue = "42";
Integer value = Integer.valueOf(rawValue);

StandardEvaluationContext context = new StandardEvaluationContext();
context.setVariable("value", value);

Boolean result = parser.parseExpression("#value >= 40")
        .getValue(context, Boolean.class);
~~~

Hoặc thực hiện chuyển đổi tường minh ngay trong expression bằng type reference và method phù hợp:

~~~java
StandardEvaluationContext context = new StandardEvaluationContext();
context.setVariable("rawValue", "42");

Expression expression =
        parser.parseExpression("T(java.lang.Integer).valueOf(#rawValue) >= 40");

Boolean result = expression.getValue(context, Boolean.class);
System.out.println(result); // true
~~~

Cách này cho thấy rõ dữ liệu chuỗi được phân tích thành Integer trước khi toán tử `>=` thực hiện so sánh. Nếu nội dung không phải số hợp lệ, chẳng hạn `"42x"`, việc chuyển đổi sẽ thất bại và phát sinh lỗi evaluation. Hãy xác thực đầu vào hoặc xử lý lỗi chuyển đổi ở tầng phù hợp.

## 7. ConversionService và kiểu kết quả của expression

SpEL tích hợp hệ thống chuyển đổi kiểu của Spring Core. Mặc định, SpEL sử dụng conversion service để chuyển đổi giá trị trong các tình huống cần một kiểu đích, ví dụ khi lấy kết quả với kiểu mong muốn hoặc khi gán giá trị cho property có kiểu cụ thể.

Ví dụ, biểu thức trả về string literal nhưng ứng dụng yêu cầu Integer:

~~~java
Expression expression = parser.parseExpression("'42'");

Integer value = expression.getValue(Integer.class);
System.out.println(value); // 42
~~~

Overload `getValue(Integer.class)` yêu cầu kết quả có kiểu `Integer`. Nếu giá trị biểu thức không phải Integer nhưng có thể chuyển đổi bằng `TypeConverter` đang đăng ký, SpEL có thể thực hiện chuyển đổi. Nếu không thể chuyển đổi, lời gọi sẽ phát sinh `EvaluationException`.

Cần phân biệt hai việc:

- **Chuyển đổi kiểu kết quả:** biểu thức đã được đánh giá, sau đó kết quả được chuyển sang kiểu mà `getValue(TargetType.class)` yêu cầu.
- **So sánh hai toán hạng:** toán tử quan hệ cần các giá trị có thể so sánh theo quy tắc của `Number` hoặc `Comparable`. Không nên mặc định rằng mọi cặp kiểu khác nhau đều tự động được chuyển đổi trước khi so sánh.

Vì vậy, việc `getValue(Integer.class)` có thể chuyển `'42'` thành `42` không có nghĩa rằng mọi biểu thức như `'42' > 10` đều tự động được hiểu là phép so sánh số. Khi so sánh dữ liệu khác kiểu, hãy chuyển đổi rõ ràng trước.

## 8. Chuyển đổi khi gán property có kiểu

ConversionService cũng hữu ích khi SpEL ghi giá trị vào một property có kiểu đích. Ví dụ, bean có property Boolean:

~~~java
public class Preferences {
    private Boolean enabled;

    public Boolean getEnabled() {
        return enabled;
    }

    public void setEnabled(Boolean enabled) {
        this.enabled = enabled;
    }
}
~~~

Có thể dùng evaluation context hỗ trợ data binding để gán giá trị chuỗi vào property Boolean:

~~~java
Preferences preferences = new Preferences();

EvaluationContext context =
        SimpleEvaluationContext.forReadWriteDataBinding().build();

parser.parseExpression("enabled")
        .setValue(context, preferences, "true");

System.out.println(preferences.getEnabled()); // true
~~~

SpEL biết kiểu đích của property `enabled` là `Boolean`, nên conversion service có thể chuyển chuỗi `"true"` thành giá trị Boolean trước khi gán.

Việc chuyển đổi còn có thể áp dụng cho collection có generic type. Chẳng hạn, khi gán vào `List<Boolean>`, Spring có thể chuyển từng phần tử sang Boolean để giữ đúng kiểu phần tử. Đây là một điểm quan trọng của conversion service: nó không chỉ chuyển đổi giá trị đơn mà còn có thể duy trì ràng buộc kiểu generic khi làm việc với property.

## 9. Đăng ký converter tùy chỉnh

Spring Core cho phép mở rộng conversion service bằng converter riêng khi ứng dụng có kiểu dữ liệu đặc thù. Sau khi đăng ký converter, có thể cấu hình `StandardTypeConverter` của evaluation context sử dụng conversion service đó.

~~~java
ConversionService conversionService = new DefaultConversionService();

// Đăng ký Converter<String, CustomCode> phù hợp với domain của ứng dụng.
conversionService.addConverter(new StringToCustomCodeConverter());

StandardEvaluationContext context = new StandardEvaluationContext();
context.setTypeConverter(new StandardTypeConverter(conversionService));
~~~

`StringToCustomCodeConverter` ở đây là converter do ứng dụng định nghĩa và triển khai `Converter<String, CustomCode>`. Converter cần xác thực nội dung chuỗi và tạo object domain hợp lệ; không nên chuyển đổi tùy tiện dữ liệu không hợp lệ thành một giá trị mặc định khiến lỗi bị che giấu.

Converter tùy chỉnh đặc biệt hữu ích khi:

- Property đích dùng một kiểu value object riêng.
- Giá trị đầu vào đến từ cấu hình hoặc data binding dưới dạng chuỗi.
- Ứng dụng có quy tắc chuẩn hóa hoặc xác thực riêng khi chuyển đổi.
- Nhiều expression hoặc thành phần Spring cần dùng chung một quy tắc chuyển đổi.

Đăng ký converter không có nghĩa mọi phép so sánh tự động sử dụng converter để biến đổi hai toán hạng. Hãy xác định rõ vị trí cần chuyển đổi: trước khi so sánh, khi lấy kiểu kết quả hay khi ghi property.

## 10. So sánh với null

Trong SpEL, `null` được xem là “không có giá trị”, không phải số 0. Với toán tử nhỏ hơn và lớn hơn, quy tắc so sánh với null có hành vi riêng:

- `X > null` là true khi X khác null.
- `X < null` là false khi X khác null.
- Không nên dùng phép so sánh với null để thay thế phép so sánh số với 0.

Ví dụ:

~~~java
Boolean greater = parser.parseExpression("10 > null")
        .getValue(Boolean.class);

Boolean less = parser.parseExpression("10 < null")
        .getValue(Boolean.class);

System.out.println(greater); // true
System.out.println(less);    // false
~~~

Nếu mục đích là kiểm tra giá trị số dương hoặc âm, hãy so sánh với 0:

~~~java
Boolean positive = parser.parseExpression("#amount > 0")
        .getValue(context, Boolean.class);
~~~

Nếu mục đích là kiểm tra dữ liệu có tồn tại hay không, hãy dùng điều kiện null rõ ràng, ví dụ `#value != null`. Khi truy cập property có thể null, cần xử lý null trước khi gọi method hoặc truy cập sâu vào object graph.

## 11. Các toán tử dạng chữ và toán tử mở rộng

Trong một số định dạng cấu hình, ký tự `<` hoặc `>` có ý nghĩa đặc biệt, chẳng hạn XML. SpEL hỗ trợ các từ tương đương cho toán tử quan hệ:

| Toán tử ký hiệu | Từ tương đương |
|---|---|
| `<` | `lt` |
| `>` | `gt` |
| `<=` | `le` |
| `>=` | `ge` |
| `==` | `eq` |
| `!=` | `ne` |

Các từ này không phân biệt chữ hoa và chữ thường.

~~~java
Boolean result = parser.parseExpression("10 gt 5")
        .getValue(Boolean.class);
~~~

SpEL còn hỗ trợ các toán tử liên quan đến so sánh:

**between**

~~~java
Boolean inRange = parser.parseExpression("5 between {1, 10}")
        .getValue(Boolean.class);
~~~

`between` là cách viết gọn cho điều kiện giá trị nằm trong khoảng, bao gồm cả hai đầu mút: giá trị lớn hơn hoặc bằng đầu dưới và nhỏ hơn hoặc bằng đầu trên. Nếu đảo ngược hai đầu mút, biểu thức không tự sắp xếp lại khoảng.

**instanceof**

~~~java
Boolean isInteger = parser.parseExpression("123 instanceof T(Integer)")
        .getValue(Boolean.class);
~~~

Toán tử này kiểm tra kiểu runtime. Literal số nguyên trong SpEL được đóng hộp thành `Integer`; vì vậy cần phân biệt kiểu wrapper như `Integer` với kiểu primitive như `int`.

**matches**

~~~java
Boolean validAmount = parser.parseExpression(
        "'125.50' matches '^-?\\d+(\\.\\d{2})?$'")
        .getValue(Boolean.class);
~~~

`matches` kiểm tra chuỗi có khớp biểu thức chính quy hay không. Đây là kiểm tra định dạng chuỗi, không phải phép so sánh số học; chuỗi khớp regex vẫn cần được chuyển đổi và kiểm tra miền giá trị nếu nghiệp vụ yêu cầu một số hợp lệ.

## 12. Lỗi thường gặp

- **So sánh chuỗi như số:** `'10' < '2'` là so sánh từ điển và có kết quả true. Chuyển hai giá trị sang kiểu số trước khi so sánh số học.
- **Giả định mọi kiểu đều chuyển đổi được:** conversion service chỉ thực hiện những chuyển đổi có converter phù hợp. Chuỗi không hợp lệ hoặc kiểu không được hỗ trợ sẽ gây lỗi.
- **Nhầm chuyển đổi kết quả với chuyển đổi toán hạng:** `getValue(Integer.class)` chuyển kết quả sang Integer nếu có thể; điều đó không chứng minh các toán hạng khác kiểu trong một phép so sánh được tự động chuyển đổi.
- **So sánh chuỗi không phân biệt hoa thường:** `'PAID'` và `'paid'` khác nhau. Chuẩn hóa theo quy tắc nghiệp vụ nếu cần.
- **Dùng thứ tự chuỗi cho ngôn ngữ tự nhiên:** `String.compareTo` không thay thế collation theo locale.
- **Coi null như số 0:** `null` có quy tắc riêng. Hãy kiểm tra null hoặc so sánh với 0 tùy mục đích.
- **So sánh object không tương thích:** kiểu tùy chỉnh cần triển khai `Comparable` với quy tắc rõ ràng, hoặc chuyển đổi dữ liệu sang kiểu có thể so sánh.
- **Bỏ qua lỗi chuyển đổi:** dữ liệu đầu vào nên được xác thực trước hoặc lỗi evaluation cần được xử lý tại ranh giới phù hợp.

## 13. Chọn cách so sánh phù hợp

Có thể chọn theo kiểu dữ liệu và ý nghĩa nghiệp vụ:

1. **Số với số:** dùng trực tiếp các toán tử quan hệ. Chọn kiểu số phù hợp với độ chính xác cần thiết.
2. **Chuỗi với chuỗi:** dùng `==` để so sánh nội dung hoặc `<`/`>` cho thứ tự từ điển. Chuẩn hóa nếu cần không phân biệt hoa thường.
3. **Object có thứ tự:** triển khai `Comparable` với quy tắc nhất quán rồi dùng toán tử quan hệ.
4. **Chuỗi biểu diễn số với số:** chuyển chuỗi sang kiểu số một cách tường minh trước khi so sánh.
5. **Kết quả expression cần kiểu khác:** dùng overload `getValue(TargetType.class)` và bảo đảm conversion service có converter phù hợp.
6. **Gán dữ liệu vào property có kiểu:** dùng evaluation context phù hợp với data binding; Spring conversion service có thể chuyển giá trị trước khi gán.
7. **Kiểu domain tùy chỉnh:** đăng ký converter riêng khi cần và xác thực dữ liệu ở converter.

## 14. Ghi nhớ

- Toán tử quan hệ trong SpEL hỗ trợ `Number` và các kiểu triển khai `Comparable`.
- Số được so sánh theo giá trị số học; chuỗi được so sánh theo thứ tự từ điển và phân biệt hoa thường.
- So sánh chuỗi biểu diễn số khác với so sánh giá trị số: `'10' < '2'` là true theo thứ tự chuỗi.
- Không mặc định mọi cặp kiểu khác nhau đều được chuyển đổi trước khi so sánh.
- Dùng chuyển đổi tường minh hoặc chuẩn hóa dữ liệu trước phép so sánh khi kiểu đầu vào khác kiểu đích.
- ConversionService hỗ trợ chuyển đổi kiểu kết quả và data binding; có thể mở rộng bằng converter tùy chỉnh.
- `null` không phải số 0; kiểm tra null và so sánh số theo đúng mục đích.
- Các từ `lt`, `gt`, `le`, `ge`, `eq`, `ne` là dạng chữ của toán tử quan hệ.
- Dùng `between`, `instanceof` và `matches` cho các nhu cầu kiểm tra khoảng, kiểu runtime và định dạng chuỗi.
- Giữ quy tắc so sánh ngắn, rõ và phù hợp với kiểu dữ liệu thực tế.
