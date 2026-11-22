# ParserConfiguration và compiler mode trong Spring Expression Language

Spring Expression Language (SpEL) có thể chạy một biểu thức theo cách diễn giải (interpreted) hoặc biên dịch biểu thức thành bytecode để tăng tốc những trường hợp được đánh giá lặp lại. Ngoài ra, parser có thể được cấu hình để tự mở rộng một số property null hoặc collection khi biểu thức truy cập chúng.

Các tùy chọn này được cấu hình bằng lớp \`SpelParserConfiguration\` và truyền vào \`SpelExpressionParser\`. Trong tài liệu hoặc trao đổi, chủ đề này đôi khi được gọi ngắn là parser configuration; tên API cụ thể của Spring là \`SpelParserConfiguration\`.

Cần phân biệt hai nhóm cấu hình:

- **Parser configuration:** quyết định cách parser xử lý biểu thức, ví dụ auto-grow và compiler mode.
- **EvaluationContext:** cung cấp root object, variables, property accessors, method resolvers, type converter và các dịch vụ lúc đánh giá.

Compiler mode không thay thế EvaluationContext. Nó chỉ thay đổi cách thực thi expression sau khi parser tạo ra đối tượng Expression.

## 1. SpelParserConfiguration là gì?

\`SpelParserConfiguration\` thuộc package \`org.springframework.expression.spel\`. Lớp này gom các tùy chọn ảnh hưởng đến parser và cách biểu thức được chuẩn bị để đánh giá.

Một parser có thể được tạo với cấu hình mặc định:

~~~java
ExpressionParser parser =
    new SpelExpressionParser();
~~~

Hoặc nhận một cấu hình tường minh:

~~~java
SpelParserConfiguration configuration =
    new SpelParserConfiguration();

ExpressionParser parser =
    new SpelExpressionParser(configuration);
~~~

Khi cần compiler mode hoặc auto-grow, hãy tạo \`SpelParserConfiguration\` phù hợp rồi truyền vào constructor của \`SpelExpressionParser\`.

Parser configuration được chọn khi tạo parser. Nếu hai nhóm biểu thức cần chính sách khác nhau, có thể tạo parser riêng cho từng nhóm để hành vi dễ hiểu và kiểm soát.

## 2. Parser configuration khác EvaluationContext

Hai thành phần tham gia ở những giai đoạn khác nhau:

| Thành phần | Trách nhiệm | Ví dụ |
|---|---|---|
| SpelParserConfiguration | Cấu hình cách parser chuẩn bị và xử lý expression | Compiler mode, auto-grow |
| ExpressionParser | Phân tích chuỗi SpEL thành Expression | parseExpression("price * 2") |
| EvaluationContext | Cung cấp dữ liệu và dịch vụ lúc đánh giá | Root object, variables, resolver |
| Expression | Đại diện cho biểu thức đã parse | getValue(context) |

Ví dụ:

~~~java
SpelParserConfiguration parserConfiguration =
    new SpelParserConfiguration();

ExpressionParser parser =
    new SpelExpressionParser(parserConfiguration);

Expression expression =
    parser.parseExpression("price * #quantity");

StandardEvaluationContext context =
    new StandardEvaluationContext(product);

context.setVariable("quantity", 2);

BigDecimal total =
    expression.getValue(context, BigDecimal.class);
~~~

Parser configuration không chứa product hoặc quantity. Root object và biến được cung cấp qua EvaluationContext khi gọi getValue.

## 3. Các nhóm tùy chọn chính

Những tùy chọn thường gặp trong SpelParserConfiguration gồm:

- **Auto-grow null references:** cho phép SpEL khởi tạo một số tham chiếu null trên đường dẫn property khi cần truy cập sâu hơn.
- **Auto-grow collections:** cho phép mở rộng collection khi expression truy cập một index vượt kích thước hiện tại, trong phạm vi cấu hình.
- **Maximum auto-grow size:** giới hạn kích thước tối đa khi tự mở rộng collection.
- **Compiler mode:** chọn cách expression được thực thi bằng interpreted mode hoặc compiler.
- **Compiler classloader:** chỉ định classloader được dùng cho lớp bytecode do SpEL compiler tạo.

Không phải ứng dụng nào cũng cần bật tất cả. Hãy chọn từng tùy chọn dựa trên cấu trúc dữ liệu và đặc điểm expression thực tế.

## 4. Auto-grow null references

Khi một biểu thức truy cập property lồng nhau, object trung gian có thể đang là null.

Ví dụ:

~~~spel
customer.address.city
~~~

Nếu customer tồn tại nhưng address là null, việc đọc city thông thường không thể tiếp tục. Khi bật auto-grow null references, SpEL có thể khởi tạo object trung gian null nếu kiểu đó có thể được tạo theo cơ chế mà framework hỗ trợ.

Cấu hình:

~~~java
SpelParserConfiguration configuration =
    new SpelParserConfiguration(
        true,   // autoGrowNullReferences
        false   // autoGrowCollections
    );

ExpressionParser parser =
    new SpelExpressionParser(configuration);
~~~

Hai tham số Boolean lần lượt bật auto-grow null references và auto-grow collections.

Auto-grow không có nghĩa SpEL có thể tạo mọi kiểu object. Kiểu trung gian cần đáp ứng điều kiện khởi tạo phù hợp, chẳng hạn có constructor hoặc cơ chế instantiation mà SpEL có thể sử dụng. Nếu không thể tạo object, evaluation vẫn có thể thất bại.

### Auto-grow không thay thế kiểm tra mô hình dữ liệu

Tự khởi tạo object có thể hữu ích cho data binding, nhưng cũng có thể làm thay đổi trạng thái object chỉ vì một biểu thức truy cập property sâu.

Ví dụ, một biểu thức được kỳ vọng chỉ đọc có thể khiến object trung gian được tạo ra nếu auto-grow được bật và đường dẫn được truy cập theo cách kích hoạt tính năng này.

Vì vậy, hãy cân nhắc bật tính năng này khi mục tiêu là binding hoặc cập nhật dữ liệu. Với expression chỉ đọc, mặc định không auto-grow thường dễ dự đoán hơn.

## 5. Auto-grow collections

Auto-grow collections cho phép SpEL mở rộng collection khi biểu thức truy cập một index lớn hơn index hiện có, trong phạm vi giới hạn.

Ví dụ, với một list đang rỗng:

~~~java
public class FormData {
    private List<String> labels = new ArrayList<>();

    public List<String> getLabels() {
        return labels;
    }

    public void setLabels(List<String> labels) {
        this.labels = labels;
    }
}
~~~

Có thể cấu hình:

~~~java
SpelParserConfiguration configuration =
    new SpelParserConfiguration(
        false,
        true,
        100
    );

ExpressionParser parser =
    new SpelExpressionParser(configuration);
~~~

Trong ví dụ, auto-grow null references bị tắt, auto-grow collections được bật và maximum auto-grow size là 100.

Nếu expression ghi vào một index vượt kích thước hiện tại, SpEL có thể mở rộng list đến vị trí cần thiết. Giá trị được tạo cho các vị trí mới phụ thuộc vào kiểu phần tử và khả năng khởi tạo/chuyển đổi tương ứng.

### Maximum auto-grow size

Giới hạn kích thước ngăn một biểu thức yêu cầu mở rộng collection đến số lượng phần tử quá lớn.

Ví dụ, nếu maximum auto-grow size là 100, không nên giả định expression có thể tự mở rộng collection đến hàng nghìn phần tử. Yêu cầu vượt giới hạn có thể khiến evaluation thất bại.

Giới hạn này đặc biệt quan trọng khi index đến từ dữ liệu runtime. Không nên cho phép một giá trị index không được kiểm soát gây ra việc cấp phát bộ nhớ lớn.

Auto-grow collections không làm cho index bất kỳ trở nên hợp lệ. Nó chỉ hỗ trợ mở rộng theo quy tắc và giới hạn được cấu hình.

## 6. Kết hợp auto-grow null references và collections

Có thể bật cả hai tùy chọn:

~~~java
SpelParserConfiguration configuration =
    new SpelParserConfiguration(
        true,
        true,
        100
    );

ExpressionParser parser =
    new SpelExpressionParser(configuration);
~~~

Cấu hình này hữu ích trong một số luồng data binding có object lồng nhau và collection cần được tạo/mở rộng khi người dùng nhập dữ liệu.

Ví dụ đường dẫn:

~~~spel
customer.addresses[2].city
~~~

Tùy trạng thái object và kiểu dữ liệu, SpEL có thể cần:

1. Khởi tạo address hoặc collection trung gian đang null nếu auto-grow null references được bật.
2. Mở rộng collection để index 2 tồn tại nếu auto-grow collections được bật.
3. Khởi tạo phần tử mới nếu kiểu phần tử hỗ trợ.
4. Gán hoặc đọc property city theo biểu thức.

Không phải mọi đường dẫn đều có thể tự động hoàn tất. Kiểu không thể khởi tạo, property không writable, collection không hỗ trợ sửa đổi hoặc index vượt giới hạn vẫn có thể gây lỗi.

## 7. Compiler mode là gì?

SpEL thường đánh giá expression theo interpreted mode. Khi expression được đánh giá lặp lại, việc biên dịch expression thành bytecode có thể giảm chi phí thực thi.

Compiler mode được điều khiển bởi enum \`SpelCompilerMode\`:

- \`OFF\`: không dùng compiler.
- \`IMMEDIATE\`: yêu cầu biên dịch expression sớm khi có thể.
- \`MIXED\`: kết hợp interpreted và compiled execution, có khả năng quay lại interpreted mode khi compiled execution không còn phù hợp.

Compiler không làm thay đổi ý nghĩa logic mà expression mô tả. Mục tiêu là cải thiện hiệu năng thực thi cho những expression có thể biên dịch và có đặc điểm runtime phù hợp.

Compiler mode được đặt trong SpelParserConfiguration khi tạo parser.

## 8. Chế độ OFF

\`SpelCompilerMode.OFF\` tắt SpEL compiler. Expression được đánh giá theo cơ chế diễn giải.

Ví dụ:

~~~java
SpelParserConfiguration configuration =
    new SpelParserConfiguration(
        SpelCompilerMode.OFF
    );

ExpressionParser parser =
    new SpelExpressionParser(configuration);

Expression expression =
    parser.parseExpression("price * #quantity");
~~~

Đây là chế độ mặc định khi không yêu cầu compiler.

OFF phù hợp khi:

- Expression chỉ được đánh giá thỉnh thoảng.
- Tính linh hoạt của kiểu runtime quan trọng hơn tối ưu compile.
- Expression dùng các cấu trúc không được compiler hỗ trợ.
- Ứng dụng muốn hành vi interpreted ổn định và dễ chẩn đoán.

Tắt compiler không có nghĩa expression không được parse hoặc không được tối ưu ở các lớp khác của ứng dụng. Nó chỉ có nghĩa SpEL không biên dịch expression thành bytecode bằng compiler mode.

## 9. Chế độ IMMEDIATE

\`SpelCompilerMode.IMMEDIATE\` yêu cầu SpEL biên dịch expression sớm nhất có thể khi có đủ thông tin cần thiết.

Ví dụ:

~~~java
SpelParserConfiguration configuration =
    new SpelParserConfiguration(
        SpelCompilerMode.IMMEDIATE,
        MyService.class.getClassLoader()
    );

ExpressionParser parser =
    new SpelExpressionParser(configuration);
~~~

Trong chế độ này, nếu expression không thể biên dịch hoặc compiled execution gặp vấn đề, lỗi có thể được thể hiện trực tiếp thay vì âm thầm dựa vào interpreted fallback như chế độ MIXED.

IMMEDIATE phù hợp khi:

- Expression được đánh giá lặp lại với cấu trúc và kiểu dữ liệu ổn định.
- Ứng dụng biết rõ những expression cần biên dịch.
- Kiểu của root object và các giá trị quan trọng tương đối ổn định.
- Có thể kiểm soát lỗi compile và kiểm thử trước khi đưa vào môi trường chạy.

Không nên bật IMMEDIATE một cách đại trà cho expression động hoặc có kiểu runtime thay đổi mạnh. Một expression hợp lệ ở interpreted mode chưa chắc đã thuộc tập cú pháp mà compiler có thể xử lý.

## 10. Chế độ MIXED

\`SpelCompilerMode.MIXED\` cho phép expression được đánh giá bằng interpreted mode trước, sau đó chuyển sang compiled execution khi compiler có đủ thông tin và điều kiện phù hợp.

Nếu compiled execution gặp vấn đề do đặc điểm runtime thay đổi, chế độ MIXED có thể quay lại interpreted mode để tiếp tục đánh giá.

Ví dụ cấu hình:

~~~java
SpelParserConfiguration configuration =
    new SpelParserConfiguration(
        SpelCompilerMode.MIXED,
        MyService.class.getClassLoader()
    );

ExpressionParser parser =
    new SpelExpressionParser(configuration);
~~~

MIXED thường phù hợp khi:

- Expression được tái sử dụng nhiều lần.
- Kiểu runtime nhìn chung ổn định nhưng có thể thay đổi ở một số lần đánh giá.
- Ứng dụng muốn tận dụng compiler nhưng vẫn cần khả năng quay lại interpreted execution.
- Expression được cung cấp bởi cấu hình hoặc rule engine và không phải mọi trường hợp đều có thể biên dịch.

Fallback không có nghĩa mọi lỗi logic đều được tự động sửa. Nếu expression sai dữ liệu, gọi method không tồn tại hoặc thực hiện phép toán không hợp lệ, interpreted execution vẫn có thể phát sinh lỗi tương ứng.

## 11. So sánh ba compiler mode

| Mode | Hành vi | Khi phù hợp |
|---|---|---|
| OFF | Luôn interpreted, không biên dịch bằng SpEL compiler | Expression ít dùng hoặc cần tính linh hoạt |
| IMMEDIATE | Biên dịch sớm khi có thể; lỗi compile/runtime không được xử lý theo cơ chế fallback của MIXED | Expression ổn định, có thể kiểm soát và kiểm thử |
| MIXED | Bắt đầu interpreted, có thể chuyển sang compiled; có thể quay lại interpreted nếu compiled execution không phù hợp | Expression dùng lặp lại nhưng có biến thiên runtime |

Không có mode nào luôn nhanh nhất trong mọi tình huống. Hiệu năng phụ thuộc độ phức tạp expression, số lần đánh giá, kiểu dữ liệu, khả năng biên dịch và chi phí khởi động.

Đối với một expression chỉ chạy một lần, chi phí chuẩn bị compile có thể không mang lại lợi ích. Với expression được đánh giá hàng nghìn lần trên dữ liệu có kiểu ổn định, compiler có thể tạo khác biệt đáng kể.

## 12. Compiler classloader

SpEL compiler tạo bytecode cho expression. Classloader dùng để định nghĩa hoặc truy cập lớp được biên dịch cần nhìn thấy những kiểu mà expression sử dụng.

Có thể chỉ định compiler classloader khi tạo SpelParserConfiguration:

~~~java
ClassLoader compilerClassLoader =
    MyService.class.getClassLoader();

SpelParserConfiguration configuration =
    new SpelParserConfiguration(
        SpelCompilerMode.MIXED,
        compilerClassLoader
    );

ExpressionParser parser =
    new SpelExpressionParser(configuration);
~~~

Việc chọn classloader phù hợp đặc biệt quan trọng trong ứng dụng có:

- Nhiều module hoặc classloader.
- Plugin được nạp động.
- Application server hoặc container.
- Kiểu domain nằm trong classloader riêng.
- Các lớp proxy hoặc generated class.

Nếu compiler classloader không nhìn thấy kiểu cần thiết, việc biên dịch hoặc tải lớp expression đã biên dịch có thể thất bại.

Hãy chọn classloader có thể truy cập các kiểu mà root object, property và method của expression sử dụng. Không nên mặc định thread context classloader luôn là lựa chọn đúng cho mọi ứng dụng.

## 13. Compiler cần thông tin kiểu runtime

Compiled expression hoạt động tốt hơn khi SpEL có thể xác định kiểu của các giá trị trong expression.

Ví dụ:

~~~java
public class Product {
    private BigDecimal price;

    public BigDecimal getPrice() {
        return price;
    }
}
~~~

Expression:

~~~spel
price * 2
~~~

có thể được tối ưu khi kiểu của root object và property price ổn định.

Nếu cùng một expression được đánh giá với nhiều root object có kiểu khác nhau hoặc property trả về kiểu không ổn định, compiler có thể không tạo được một đường thực thi phù hợp cho mọi trường hợp.

Điều này giải thích vì sao một expression chạy tốt ở interpreted mode nhưng không nhất thiết có thể biên dịch hoặc chạy compiled ổn định.

Khi dùng compiler mode, hãy giữ hợp đồng kiểu của root object, variables và property nhất quán nếu có thể.

## 14. Không phải mọi expression đều có thể biên dịch

SpEL compiler chỉ hỗ trợ một tập cấu trúc expression nhất định. Khả năng biên dịch phụ thuộc phiên bản Spring và nội dung expression.

Những yếu tố có thể ảnh hưởng:

- Cấu trúc expression có được compiler hỗ trợ không.
- Kiểu runtime của property và method có xác định được không.
- Có sử dụng custom PropertyAccessor hoặc cơ chế truy cập động không.
- Có dùng những thao tác có kiểu hoặc hành vi không thể biểu diễn trong compiled form không.
- Kiểu tham số và giá trị trả về có ổn định giữa các lần đánh giá không.

Vì vậy, không nên kết luận một expression chắc chắn biên dịch được chỉ vì nó parse và evaluate thành công ở interpreted mode.

Nếu compiler không hỗ trợ expression, OFF vẫn hoạt động theo interpreted mode. Với MIXED, framework có thể tiếp tục bằng interpreted execution khi không thể dùng compiled form. Với IMMEDIATE, cần kiểm thử sớm để phát hiện expression không phù hợp với chế độ đã chọn.

## 15. Parser configuration cho auto-grow và compiler mode là hai nhóm độc lập

Một parser có thể cần auto-grow cho data binding nhưng không cần compiler. Parser khác có thể cần compiler cho expression tính toán lặp lại nhưng không cần auto-grow.

Ví dụ chỉ bật auto-grow:

~~~java
SpelParserConfiguration configuration =
    new SpelParserConfiguration(
        true,
        true,
        100
    );

ExpressionParser parser =
    new SpelExpressionParser(configuration);
~~~

Ví dụ chỉ chọn compiler mode:

~~~java
SpelParserConfiguration configuration =
    new SpelParserConfiguration(
        SpelCompilerMode.MIXED
    );

ExpressionParser parser =
    new SpelExpressionParser(configuration);
~~~

Hãy chọn constructor phù hợp với nhóm tùy chọn cần dùng và phiên bản Spring của dự án. Không bật auto-grow chỉ vì đang dùng compiler; hai tính năng không phụ thuộc bắt buộc vào nhau.

## 16. Parse một lần và tái sử dụng Expression

Compiler mode có ý nghĩa rõ hơn khi expression được tái sử dụng. Ứng dụng thường nên parse expression một lần rồi đánh giá nhiều lần thay vì liên tục tạo parser và parse lại cùng một chuỗi.

~~~java
SpelParserConfiguration configuration =
    new SpelParserConfiguration(
        SpelCompilerMode.MIXED
    );

ExpressionParser parser =
    new SpelExpressionParser(configuration);

Expression expression =
    parser.parseExpression("price * #quantity");

for (Product product : products) {
    StandardEvaluationContext context =
        new StandardEvaluationContext(product);

    context.setVariable("quantity", 2);

    BigDecimal total =
        expression.getValue(context, BigDecimal.class);

    // Sử dụng total.
}
~~~

Expression giữ cấu trúc đã parse. Mỗi lần đánh giá, context cung cấp root object và biến tương ứng.

Nếu expression cần được đánh giá đồng thời, hãy xem xét việc tái sử dụng Expression và quản lý EvaluationContext riêng cho từng công việc. Tránh thay đổi biến trên một context dùng chung giữa nhiều luồng nếu không có cơ chế đồng bộ phù hợp.

## 17. Đo hiệu năng trước khi chọn compiler mode

Compiler mode là một lựa chọn tối ưu hóa, không phải bảo đảm mọi expression sẽ nhanh hơn.

Khi đo, nên phân biệt:

- **Parsing cost:** chi phí tạo Expression từ chuỗi.
- **Warm-up cost:** các lần interpreted evaluation và quá trình compiler chuẩn bị.
- **Steady-state cost:** thời gian khi expression đã đạt trạng thái chạy ổn định.
- **Fallback cost:** chi phí nếu compiled execution không còn phù hợp và phải quay lại interpreted mode.

Một benchmark có ý nghĩa cần:

1. Dùng cùng expression và dữ liệu đại diện cho production.
2. Đo riêng thời gian parse và thời gian evaluate.
3. Chạy đủ số vòng để quan sát warm-up.
4. So sánh OFF, IMMEDIATE và MIXED.
5. Dùng nhiều kiểu dữ liệu thực tế nếu ứng dụng có biến thiên.
6. Kiểm tra kết quả tính toán có giống nhau giữa các mode.
7. Đo cả throughput và latency trong điều kiện tải gần thực tế.

Không nên bật compiler chỉ vì một microbenchmark đơn giản cho thấy một trường hợp nhanh hơn. Hãy đo với expression và dữ liệu thực sự của ứng dụng.

## 18. Chẩn đoán lỗi liên quan parser configuration và compiler

Một số nhóm lỗi thường gặp:

### Parser không hiểu cấu hình hoặc constructor

Kiểm tra phiên bản Spring Framework và API SpelParserConfiguration có trong dependency thực tế. Một constructor hoặc tùy chọn có thể khác giữa các phiên bản.

### Auto-grow không tạo được object

Kiểm tra kiểu property trung gian, constructor, setter, collection implementation và maximum auto-grow size. Auto-grow không thể khởi tạo mọi kiểu hoặc sửa một property không writable.

### Compiler không thể biên dịch expression

Kiểm tra compiler mode, kiểu runtime, cấu trúc expression và compiler classloader. Expression có thể hợp lệ ở interpreted mode nhưng không thuộc tập được compiler hỗ trợ.

### Compiled execution gặp lỗi khi kiểu runtime thay đổi

Kiểm tra các lần đánh giá có dùng root object hoặc property với kiểu khác nhau không. Nếu expression cần linh hoạt, MIXED có thể phù hợp hơn IMMEDIATE.

### Classloader không nhìn thấy kiểu

Kiểm tra compiler classloader có thể truy cập class domain, proxy và dependency được expression dùng hay không.

Khi điều tra, hãy phân biệt lỗi parsing, lỗi evaluation ở interpreted mode và lỗi trong quá trình compile hoặc thực thi compiled expression.

## 19. Ví dụ hoàn chỉnh: cấu hình MIXED và tái sử dụng expression

Giả sử ứng dụng cần tính giá trị đơn hàng nhiều lần:

~~~java
public class Product {
    private final BigDecimal price;

    public Product(BigDecimal price) {
        this.price = price;
    }

    public BigDecimal getPrice() {
        return price;
    }
}
~~~

Tạo parser ở chế độ MIXED:

~~~java
SpelParserConfiguration configuration =
    new SpelParserConfiguration(
        SpelCompilerMode.MIXED,
        Product.class.getClassLoader()
    );

ExpressionParser parser =
    new SpelExpressionParser(configuration);

Expression expression =
    parser.parseExpression("price * #quantity");
~~~

Đánh giá với từng product:

~~~java
Product first =
    new Product(new BigDecimal("250000"));

Product second =
    new Product(new BigDecimal("400000"));

StandardEvaluationContext firstContext =
    new StandardEvaluationContext(first);

firstContext.setVariable("quantity", 2);

StandardEvaluationContext secondContext =
    new StandardEvaluationContext(second);

secondContext.setVariable("quantity", 3);

BigDecimal firstTotal =
    expression.getValue(firstContext, BigDecimal.class);

BigDecimal secondTotal =
    expression.getValue(secondContext, BigDecimal.class);
~~~

Kết quả:

~~~text
firstTotal = 500000
secondTotal = 1200000
~~~

Ví dụ minh họa việc dùng cùng một Expression đã parse với nhiều EvaluationContext. Compiler mode có thể tối ưu quá trình đánh giá khi expression và kiểu runtime phù hợp; kết quả nghiệp vụ vẫn phải giữ nguyên giữa interpreted và compiled execution.

## 20. Những nhầm lẫn thường gặp

**Nhầm lẫn 1: ParserConfiguration là EvaluationContext.**  
SpelParserConfiguration thiết lập hành vi parser và compiler. EvaluationContext cung cấp root object, variables và dịch vụ lúc đánh giá.

**Nhầm lẫn 2: IMMEDIATE và MIXED giống nhau.**  
IMMEDIATE yêu cầu compiled execution sớm và không có cơ chế fallback như MIXED. MIXED có thể quay lại interpreted mode nếu compiled execution không còn phù hợp.

**Nhầm lẫn 3: Bật compiler làm mọi expression nhanh hơn.**  
Chỉ expression phù hợp và được đánh giá đủ nhiều mới có thể hưởng lợi. Parsing, warm-up và compilation cũng có chi phí.

**Nhầm lẫn 4: Expression parse được thì chắc chắn compile được.**  
Compiler chỉ hỗ trợ một tập cấu trúc nhất định và cần thông tin kiểu runtime phù hợp.

**Nhầm lẫn 5: Auto-grow chỉ là tối ưu hiệu năng.**  
Auto-grow có thể khởi tạo object hoặc thay đổi kích thước collection. Đây là hành vi ảnh hưởng dữ liệu, không phải compiler optimization.

**Nhầm lẫn 6: Compiler classloader không quan trọng.**  
Compiler cần truy cập các kiểu được dùng trong expression. Classloader không phù hợp có thể làm compile hoặc tải compiled class thất bại.

**Nhầm lẫn 7: Bật auto-grow và compiler phải đi cùng nhau.**  
Đây là hai nhóm tùy chọn độc lập. Chỉ bật tính năng mà ứng dụng cần.

## 21. Ghi nhớ

- API cấu hình parser của SpEL là \`SpelParserConfiguration\`, được truyền vào \`SpelExpressionParser\`.
- Parser configuration khác EvaluationContext: một bên cấu hình parser, bên kia cung cấp dữ liệu và dịch vụ khi evaluate.
- Auto-grow null references có thể khởi tạo object trung gian null nếu kiểu hỗ trợ.
- Auto-grow collections có thể mở rộng collection khi index cần thiết, trong giới hạn maximum auto-grow size.
- Auto-grow có thể làm thay đổi object và collection; cần bật có chủ đích, nhất là với expression chỉ đọc.
- SpelCompilerMode có ba chế độ OFF, IMMEDIATE và MIXED.
- OFF dùng interpreted execution; IMMEDIATE yêu cầu compile sớm; MIXED có thể chuyển đổi giữa compiled và interpreted execution.
- Compiler cần thông tin kiểu runtime phù hợp và chỉ hỗ trợ một tập expression nhất định.
- Compiler classloader phải nhìn thấy các kiểu mà expression sử dụng.
- Nên parse một lần, tái sử dụng Expression và quản lý EvaluationContext theo từng đơn vị công việc.
- Đo warm-up và steady-state trên workload thực tế trước khi chọn compiler mode.

Khi cấu hình SpEL, hãy tách yêu cầu data binding khỏi yêu cầu tối ưu thực thi. Chọn auto-grow theo mô hình dữ liệu và giới hạn kích thước phù hợp; chọn compiler mode theo tính ổn định của kiểu và số lần đánh giá; sau đó kiểm thử expression trên đúng phiên bản Spring và classloader của ứng dụng.
