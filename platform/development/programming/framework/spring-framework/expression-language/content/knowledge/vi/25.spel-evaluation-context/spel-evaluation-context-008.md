# Tái sử dụng context và nguy cơ state bị giữ lại

## Mục tiêu

Trong SpEL, đối tượng **Expression** lưu biểu thức đã được parse, còn **EvaluationContext** cung cấp dữ liệu và cấu hình cần thiết để đánh giá biểu thức đó. Hai đối tượng này có vòng đời và vai trò khác nhau. Có thể tái sử dụng một Expression đã parse cho nhiều lần đánh giá, nhưng việc dùng lại một EvaluationContext mutable giữa các request cần được kiểm soát cẩn thận.

EvaluationContext có thể giữ root object, biến, function và các thành phần cấu hình như PropertyAccessor, MethodResolver, TypeConverter, TypeLocator hoặc BeanResolver. Nếu ứng dụng thay root object hoặc biến theo từng request nhưng quên cập nhật đầy đủ, dữ liệu của lần đánh giá trước có thể ảnh hưởng tới lần sau. Nếu nhiều luồng cùng thay đổi một context, các lần đánh giá còn có thể nhìn thấy state không thuộc request của mình.

Sau bài này, bạn có thể:

- Phân biệt việc tái sử dụng Expression với tái sử dụng EvaluationContext.
- Nhận diện state được giữ trong root object, biến và cấu hình context.
- Tránh dùng nhầm dữ liệu của request trước trong lần đánh giá tiếp theo.
- Hiểu rủi ro khi nhiều luồng cùng cập nhật một context.
- Tạo EvaluationContext riêng theo request hoặc lần đánh giá.
- Tái sử dụng cấu hình chung mà không chia sẻ state mutable của request.
- Viết kiểm thử phát hiện stale state, rò rỉ dữ liệu và lỗi đồng thời.

## 1. Expression và EvaluationContext có vai trò khác nhau

Một Expression là kết quả của quá trình parse chuỗi SpEL. Nó đại diện cho cú pháp và cấu trúc biểu thức cần đánh giá.

EvaluationContext cung cấp môi trường để expression chạy, bao gồm:

- Root object mặc định.
- Các biến được đăng ký bằng setVariable().
- Function được đăng ký trong context.
- PropertyAccessor và MethodResolver.
- ConstructorResolver và BeanResolver nếu được cấu hình.
- TypeLocator, TypeConverter và OperatorOverloader.
- Những thành phần khác quyết định cách expression truy cập hoặc chuyển đổi dữ liệu.

Ví dụ:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression =
    parser.parseExpression("#root.total >= #minimumTotal");
~~~

Expression ở trên có thể được giữ lại và dùng cho nhiều lần đánh giá. Mỗi lần đánh giá có thể cung cấp root object và context phù hợp:

~~~java
StandardEvaluationContext context =
    new StandardEvaluationContext(order);

context.setVariable("minimumTotal", new BigDecimal("100"));

Boolean accepted =
    expression.getValue(context, Boolean.class);
~~~

Điểm cần nhớ: Expression mô tả điều cần tính; EvaluationContext cung cấp dữ liệu và quy tắc để tính. Tái sử dụng Expression không bắt buộc phải tái sử dụng cùng một EvaluationContext.

## 2. State nào có thể được giữ lại trong context?

EvaluationContext không chỉ là một tham số tạm thời. Nó có thể giữ các giá trị và cấu hình qua nhiều lần gọi getValue().

### Root object

Khi tạo StandardEvaluationContext với root object:

~~~java
StandardEvaluationContext context =
    new StandardEvaluationContext(order);
~~~

context giữ tham chiếu tới object đó làm root mặc định. Nếu ứng dụng dùng lại context mà không thay root object, expression tiếp theo vẫn có thể đọc object cũ.

Nếu root object là mutable và một phần khác của ứng dụng thay đổi nó, expression sẽ quan sát state mới của chính object đó. Việc tái sử dụng context không tạo bản sao độc lập của root object.

### Biến

Biến được đăng ký bằng setVariable():

~~~java
context.setVariable("minimumTotal", new BigDecimal("100"));
context.setVariable("region", "VN");
~~~

Các biến này vẫn thuộc context cho tới khi được thay đổi hoặc context không còn được sử dụng. Nếu lần đánh giá tiếp theo không cung cấp một giá trị mới cho biến, giá trị cũ có thể tiếp tục được đọc.

Ví dụ, request thứ nhất đặt minimumTotal là 100. Request thứ hai chỉ cập nhật region nhưng quên cập nhật minimumTotal. Expression vẫn có thể dùng ngưỡng 100 từ request trước, dù request thứ hai không có ý định đó.

### Function và cấu hình

Function đăng ký trong context, cùng các accessor, resolver và converter được cấu hình, cũng là một phần môi trường đánh giá. Đây thường là cấu hình dùng chung ổn định, nhưng nếu ứng dụng thay đổi chúng trong lúc đánh giá đang diễn ra, hành vi có thể khó dự đoán.

Phân biệt rõ:

- Cấu hình cố định của ứng dụng có thể được thiết lập một lần rồi giữ ổn định.
- Root object, biến và các tham chiếu dữ liệu theo request cần được cô lập theo lần đánh giá.
- Object mutable được lưu bên trong biến vẫn có thể thay đổi dù context không bị sửa.

## 3. Phân biệt tái sử dụng Expression và tái sử dụng context

| Thành phần | Có thể tái sử dụng? | Điều cần kiểm soát |
|---|---|---|
| Expression đã parse | Thường có thể dùng lại cho nhiều lần đánh giá | Cùng cú pháp, parser/compiler configuration phù hợp |
| EvaluationContext | Có thể dùng lại trong một luồng xử lý có state ổn định | Root object, biến và mọi thay đổi trong context |
| Root object | Có thể giữ nguyên nếu các lần đánh giá cùng làm việc trên một object | Mutable state, quyền truy cập và vòng đời object |
| Biến context | Có thể giữ nếu giá trị thực sự dùng chung | Không để giá trị request trước tồn tại ngoài ý muốn |
| Accessor/resolver/converter | Có thể dùng như cấu hình ổn định | Không thay đổi cấu hình trong khi đang đánh giá |
| Object được tham chiếu từ biến | Phụ thuộc object đó | Mutable state và việc chia sẻ giữa các request |

Một thiết kế phổ biến là cache Expression theo chuỗi biểu thức hoặc ID rule, rồi tạo EvaluationContext mới cho mỗi request. Cách này giữ lợi ích parse một lần mà vẫn tách dữ liệu đánh giá.

Không nên cache một context chứa root object và biến của request rồi dùng nó như thể đó là một Expression bất biến.

## 4. Ví dụ stale state khi tái sử dụng context

Giả sử expression kiểm tra tổng đơn hàng:

~~~text
#root.total >= #minimumTotal
~~~

Ứng dụng tạo context một lần:

~~~java
StandardEvaluationContext context =
    new StandardEvaluationContext();

Expression expression = parser.parseExpression(
    "#root.total >= #minimumTotal");
~~~

Request đầu tiên:

~~~java
context.setRootObject(orderA);
context.setVariable("minimumTotal", new BigDecimal("100"));

Boolean first =
    expression.getValue(context, Boolean.class);
~~~

Request tiếp theo:

~~~java
context.setRootObject(orderB);
// Quên cập nhật minimumTotal.

Boolean second =
    expression.getValue(context, Boolean.class);
~~~

Lần đánh giá thứ hai có thể tiếp tục dùng minimumTotal bằng 100 từ request đầu tiên. Kết quả có vẻ hợp lệ về mặt kiểu dữ liệu nhưng sai theo chính sách của request thứ hai.

Đây là dạng lỗi khó phát hiện vì expression không nhất thiết ném exception. Nó chỉ sử dụng một giá trị cũ vẫn còn trong context.

Cách xử lý là tạo context mới hoặc bảo đảm mọi biến bắt buộc được đặt lại rõ ràng trước mỗi lần đánh giá. Tạo context mới thường đơn giản và ít rủi ro hơn.

## 5. Rủi ro chia sẻ context giữa nhiều luồng

Giả sử hai request cùng dùng một StandardEvaluationContext:

- Request A đặt root object là order A.
- Request B đặt root object là order B.
- Request A bắt đầu đánh giá expression.
- Request B cập nhật biến hoặc root object trước khi A hoàn tất.

Nếu context mutable được cập nhật đồng thời, một lần đánh giá có thể quan sát state không đồng nhất hoặc state thuộc request khác. Điều này có thể dẫn tới kết quả sai, lỗi không tái hiện ổn định hoặc lộ dữ liệu giữa các request.

Không dựa vào việc một số thao tác nội bộ có thể an toàn luồng để kết luận toàn bộ quá trình cập nhật root object, biến và đánh giá expression là một giao dịch nguyên tử. Việc đọc và ghi nhiều giá trị context cần được phối hợp nếu cùng chia sẻ một instance.

Nguyên tắc an toàn:

- Không dùng cùng một context mutable cho nhiều request nếu mỗi request thay root object hoặc biến.
- Không thay biến trong khi một lần đánh giá khác có thể đang đọc biến đó.
- Không thay root object trên context đang được dùng đồng thời.
- Nếu cần chia sẻ context, chỉ chia sẻ cấu hình ổn định và không sửa nó trong thời gian đánh giá.
- Ưu tiên tạo context riêng theo request hoặc theo lần đánh giá.

## 6. Tạo context riêng cho mỗi lần đánh giá

Cách đơn giản nhất là tạo context mới với root object và biến của request hiện tại.

~~~java
public Boolean evaluateOrder(
        Expression expression,
        Order order,
        BigDecimal minimumTotal) {

    StandardEvaluationContext context =
        new StandardEvaluationContext(order);

    context.setVariable("minimumTotal", minimumTotal);

    return expression.getValue(context, Boolean.class);
}
~~~

Expression có thể được parse và lưu bên ngoài method, còn context được tạo mới mỗi lần gọi.

Ưu điểm:

- Root object luôn thuộc request hiện tại.
- Biến của request trước không tồn tại trong context mới.
- Không cần đồng bộ việc thay root object hoặc biến giữa nhiều luồng.
- Test dễ tạo dữ liệu độc lập cho từng lần đánh giá.
- Lỗi do state cũ dễ được loại trừ.

Chi phí tạo context thường nhỏ hơn chi phí chẩn đoán một lỗi rò rỉ state khó tái hiện. Nếu có yêu cầu tối ưu hiệu năng, hãy đo bằng workload thực tế trước khi chọn cơ chế pooling hoặc chia sẻ mutable context.

## 7. Dùng factory để giữ cấu hình chung

Tạo context mới không có nghĩa phải đăng ký lại cấu hình theo cách rời rạc ở nhiều nơi. Có thể dùng factory để áp dụng cùng một bộ accessor, resolver, converter và function cho mỗi context.

Ví dụ:

~~~java
public class SpelContextFactory {

    private final ConversionService conversionService;

    public SpelContextFactory(ConversionService conversionService) {
        this.conversionService = conversionService;
    }

    public StandardEvaluationContext create(
            Object rootObject,
            BigDecimal minimumTotal) {

        StandardEvaluationContext context =
            new StandardEvaluationContext(rootObject);

        context.setVariable("minimumTotal", minimumTotal);
        context.setTypeConverter(
            new StandardTypeConverter(conversionService)
        );

        return context;
    }
}
~~~

Ứng dụng gọi factory cho mỗi lần đánh giá:

~~~java
StandardEvaluationContext context =
    contextFactory.create(order, minimumTotal);

Boolean accepted =
    expression.getValue(context, Boolean.class);
~~~

Factory giúp tập trung cấu hình, nhưng mỗi lần gọi vẫn tạo context riêng. Nếu cần đăng ký function hoặc PropertyAccessor, hãy thêm chúng trong factory để tất cả context có cấu hình nhất quán.

Các dependency dùng làm cấu hình chung nên được quản lý theo vòng đời phù hợp của Spring. Không đặt dữ liệu request hoặc object mutable dùng riêng cho một request vào field dùng chung của factory.

## 8. Khi nào có thể tái sử dụng cùng EvaluationContext?

Có thể tái sử dụng một context khi các lần đánh giá thực sự thuộc cùng một phạm vi dữ liệu và state không thay đổi ngoài ý muốn.

Ví dụ:

- Một batch xử lý nhiều expression trên cùng một root object bất biến.
- Một tập rule cùng dùng các biến cấu hình cố định.
- Context đã được cấu hình hoàn chỉnh và không có thread nào sửa root object hoặc biến.
- Một test đánh giá nhiều expression trên cùng fixture có chủ đích.

Ngay cả trong các trường hợp này, cần xác định rõ context thuộc về ai và khi nào nó hết hiệu lực.

Không tái sử dụng context chỉ vì muốn tránh gọi new. Nếu mỗi request có root object, tenant, người dùng, ngưỡng hoặc quyền truy cập khác nhau, context riêng thường là lựa chọn đúng.

Nếu context cần được dùng lại trong một luồng tuần tự, hãy có bước chuẩn bị đầy đủ trước mỗi lần đánh giá:

1. Đặt đúng root object.
2. Gán tất cả biến bắt buộc.
3. Xử lý biến tùy chọn theo quy tắc rõ ràng.
4. Xác nhận cấu hình accessor/resolver/converter.
5. Đánh giá expression.
6. Không để lần đánh giá kế tiếp kế thừa dữ liệu ngoài ý muốn.

Không dựa vào việc “biến nào không set thì tự mất”. Hãy coi context đã dùng là state còn tồn tại cho đến khi được thay thế hoặc loại bỏ.

## 9. State có thể nằm bên trong object được truyền vào

Tạo EvaluationContext mới không tự động làm mọi dữ liệu trở nên độc lập. Root object hoặc biến có thể tham chiếu tới một object mutable đang được chia sẻ ở nơi khác.

Ví dụ:

~~~java
context.setVariable("policy", sharedPolicy);
~~~

Nếu sharedPolicy được một thread khác thay đổi, expression có thể nhìn thấy giá trị mới dù context không thay đổi.

Tương tự, root object có thể giữ collection mutable, entity đang được cập nhật hoặc một proxy truy cập dữ liệu động.

Vì vậy, cần xem xét cả object graph được truyền vào:

- Object có bất biến trong suốt lần đánh giá không?
- Collection bên trong có thể bị sửa đồng thời không?
- Biến có trỏ tới object dùng chung giữa nhiều tenant hoặc request không?
- Property getter có trả về dữ liệu mutable hoặc tải dữ liệu động không?
- Expression có gọi method làm thay đổi state không?

Nếu expression cần một snapshot ổn định, có thể tạo DTO chỉ đọc hoặc bản sao dữ liệu cần thiết trước khi đánh giá. Đừng truyền một object có quyền rộng khi chỉ cần vài giá trị.

## 10. Rủi ro dữ liệu cũ và rò rỉ giữa request

Stale state không chỉ gây sai phép tính. Nếu context giữ root object hoặc biến của request trước, expression sau có thể đọc dữ liệu thuộc người dùng hoặc tenant khác.

Các ví dụ rủi ro:

- Biến currentUser vẫn trỏ tới người dùng trước.
- Biến tenantId chưa được cập nhật và rule dùng tenant cũ.
- Root object vẫn là entity của request trước.
- Một biến tùy chọn không được đặt lại nên giữ giá trị cũ.
- Function hoặc accessor dùng một field mutable toàn cục để lưu dữ liệu request.

Đây là lỗi cách ly dữ liệu. Cần xử lý như một vấn đề về ranh giới request và quyền truy cập, không chỉ là lỗi logic expression.

Biện pháp giảm rủi ro:

- Tạo context riêng cho request.
- Chỉ đưa dữ liệu cần thiết vào context.
- Đặt root object và biến từ dữ liệu đã xác thực.
- Tránh lưu request-specific state trong singleton hoặc static field.
- Không chia sẻ context mutable qua tenant hoặc người dùng.
- Kiểm thử hai request liên tiếp có dữ liệu khác nhau.
- Kiểm thử các request chạy đồng thời với root object và biến riêng.

## 11. Expression caching và context lifecycle

Có thể cache Expression để tránh parse cùng một chuỗi nhiều lần. Cache nên lưu expression theo key ổn định như ID rule cộng phiên bản hoặc nội dung expression đã chuẩn hóa.

Ví dụ khái quát:

~~~java
Expression expression = expressionCache.get(ruleId);
~~~

Sau đó, mỗi lần đánh giá tạo context mới:

~~~java
StandardEvaluationContext context =
    new StandardEvaluationContext(currentOrder);

context.setVariable("minimumTotal", currentMinimum);

Boolean result = expression.getValue(context, Boolean.class);
~~~

Không đưa EvaluationContext của request vào cache dùng chung. Context chứa state và tham chiếu object, nên cache nó có thể kéo dài vòng đời dữ liệu, giữ object không còn cần thiết và tạo nguy cơ rò rỉ giữa request.

Cũng cần quản lý cache Expression khi rule thay đổi. Nếu expression được cập nhật, cache cần được vô hiệu hóa hoặc version hóa để không tiếp tục đánh giá nội dung cũ.

Expression caching và context creation là hai quyết định độc lập:

- Cache Expression để giảm chi phí parse.
- Tạo EvaluationContext mới để cô lập dữ liệu và state.
- Chỉ chia sẻ cấu hình bất biến khi đã xác định rõ vòng đời và tính đồng thời.

## 12. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Kết quả dùng ngưỡng của request trước | Biến context chưa được cập nhật | Tạo context mới hoặc đặt lại mọi biến bắt buộc |
| Expression đọc nhầm entity | Root object cũ vẫn còn trong context | Khởi tạo context với root hiện tại |
| Kết quả thay đổi không ổn định | Nhiều luồng cùng sửa context | Cô lập context theo request |
| Dữ liệu giữa tenant bị lẫn | Context hoặc object biến được chia sẻ sai phạm vi | Tách context và object theo tenant/request |
| Biến tùy chọn có giá trị bất ngờ | State cũ chưa được xóa hoặc thay thế | Xác định rõ chính sách null/thiếu biến |
| Test chạy riêng nhưng lỗi khi chạy song song | Shared mutable context hoặc fixture | Tạo context và fixture riêng cho mỗi test |
| Bộ nhớ giữ object request lâu hơn dự kiến | Context bị cache hoặc giữ trong field singleton | Không cache context; giới hạn vòng đời tham chiếu |
| Cấu hình function/accessor không nhất quán | Mỗi nơi tự tạo context theo cách khác nhau | Dùng một context factory |
| Expression mới vẫn chạy logic cũ | Cache expression không được version hóa hoặc invalidated | Quản lý cache theo rule version |

Khi điều tra, ghi nhận ID expression, ID request, loại context và danh sách tên biến đã cung cấp. Không log giá trị nhạy cảm. So sánh root type và kiểu dữ liệu biến giữa các lần đánh giá để xác định state nào bị giữ lại.

## 13. Kiểm thử stale state và isolation

Một test quan trọng là đánh giá hai lần liên tiếp với dữ liệu khác nhau và xác nhận kết quả thứ hai không phụ thuộc giá trị của lần đầu.

Ví dụ dùng context riêng:

~~~java
@Test
void createsIsolatedContextForEachEvaluation() {
    ExpressionParser parser = new SpelExpressionParser();
    Expression expression =
        parser.parseExpression("#root.total >= #minimumTotal");

    Order firstOrder = new Order(new BigDecimal("150"));
    Order secondOrder = new Order(new BigDecimal("150"));

    StandardEvaluationContext firstContext =
        new StandardEvaluationContext(firstOrder);
    firstContext.setVariable("minimumTotal", new BigDecimal("100"));

    StandardEvaluationContext secondContext =
        new StandardEvaluationContext(secondOrder);
    secondContext.setVariable("minimumTotal", new BigDecimal("200"));

    assertEquals(Boolean.TRUE,
        expression.getValue(firstContext, Boolean.class));

    assertEquals(Boolean.FALSE,
        expression.getValue(secondContext, Boolean.class));
}
~~~

Test này dùng cùng Expression nhưng hai context độc lập. Kết quả khác nhau do dữ liệu của từng lần đánh giá, không do state bị giữ lại.

Các trường hợp nên có:

- Hai request tuần tự với root object khác nhau.
- Hai request có giá trị biến khác nhau.
- Request thứ hai không cung cấp một biến tùy chọn mà request đầu có.
- Một lần đánh giá ném exception rồi lần tiếp theo vẫn dùng context sạch.
- Nhiều request chạy đồng thời với context riêng.
- Root object hoặc biến tham chiếu tới collection mutable.
- Function/accessor được đăng ký nhất quán qua factory.
- Expression cache được cập nhật khi rule đổi phiên bản.
- Không có object request bị giữ lại trong singleton hoặc cache context.

Nếu ứng dụng cố ý tái sử dụng một context tuần tự, hãy có test xác nhận toàn bộ state được thay thế trước mỗi lần đánh giá. Test isolation riêng vẫn nên được giữ để chứng minh dữ liệu giữa các request không lẫn nhau.

## 14. Quy trình thiết kế vòng đời context

Khi triển khai SpEL trong ứng dụng:

1. **Parse và quản lý Expression riêng.** Cache expression theo ID hoặc version rule nếu cần.
2. **Xác định dữ liệu theo lần đánh giá.** Liệt kê root object, biến và object được tham chiếu.
3. **Tạo context riêng.** Dùng factory để khởi tạo context với root object và biến của request hiện tại.
4. **Áp dụng cấu hình chung.** Đăng ký accessor, resolver, converter và function cần thiết.
5. **Không chia sẻ mutable state.** Tránh cập nhật context hoặc object đầu vào khi một lần đánh giá đang chạy.
6. **Đánh giá và lấy kết quả.** Không giữ context trong cache sau khi hoàn tất nếu không có lý do rõ ràng.
7. **Kiểm thử isolation.** Chạy liên tiếp và song song với dữ liệu khác nhau.
8. **Theo dõi vòng đời cache.** Version hóa Expression và loại bỏ entry cũ khi rule thay đổi.

Nếu hiệu năng là mối quan tâm, đo riêng thời gian parse, tạo context và evaluate. Đừng tối ưu bằng cách chia sẻ context trước khi có số đo và test chứng minh state được cách ly đúng.

## 15. Thực hành tốt

- Tái sử dụng Expression đã parse; quản lý EvaluationContext theo vòng đời dữ liệu.
- Tạo context riêng cho mỗi request hoặc lần đánh giá có state khác nhau.
- Khởi tạo root object từ dữ liệu hiện tại, không giữ root của request trước.
- Đăng ký đầy đủ biến bắt buộc trước mỗi lần evaluate.
- Không giả định biến cũ tự biến mất khi không được set lại.
- Không sửa root object hoặc biến trong khi context đang được dùng đồng thời.
- Dùng context factory để cấu hình accessor, resolver, converter và function nhất quán.
- Chỉ chia sẻ cấu hình ổn định; không chia sẻ state mutable của request.
- Kiểm tra cả object mutable được tham chiếu từ root hoặc biến.
- Không cache EvaluationContext chứa dữ liệu request.
- Version hóa hoặc invalidate Expression cache khi rule thay đổi.
- Kiểm thử stale state, request isolation và đánh giá đồng thời.
- Không log giá trị nhạy cảm chỉ để chẩn đoán context state.

## 16. Checklist review

Trước khi chấp nhận thiết kế tái sử dụng SpEL, hãy kiểm tra:

- [ ] Expression và EvaluationContext có vòng đời riêng biệt.
- [ ] Expression cache không giữ EvaluationContext của request.
- [ ] Root object thuộc đúng request hoặc batch đang xử lý.
- [ ] Mọi biến bắt buộc được đăng ký trước khi đánh giá.
- [ ] Biến tùy chọn có chính sách null/thiếu rõ ràng.
- [ ] State cũ không thể ảnh hưởng tới lần đánh giá sau.
- [ ] Không có nhiều luồng cùng sửa một context mutable.
- [ ] Object mutable bên trong root/biến được kiểm soát.
- [ ] Function và accessor không lưu state request trong field dùng chung.
- [ ] Cấu hình chung được áp dụng qua một context factory.
- [ ] Cache Expression được version hóa và invalidated đúng lúc.
- [ ] Có test tuần tự, song song và kiểm tra rò rỉ giữa request.

## Kết luận

Expression đã parse có thể được tái sử dụng cho nhiều lần đánh giá, trong khi EvaluationContext có thể giữ root object, biến và cấu hình qua các lần gọi. Nếu dùng lại context mà không thay thế đầy đủ state, expression có thể đọc dữ liệu cũ; nếu nhiều luồng cùng cập nhật context, dữ liệu giữa các request có thể bị lẫn. Thiết kế an toàn thường cache Expression riêng, tạo EvaluationContext mới cho từng request hoặc lần đánh giá, và dùng factory để áp dụng cấu hình chung. Hãy kiểm thử stale state, object mutable và đánh giá đồng thời trước khi tối ưu vòng đời context.