# Thay đổi kiểu runtime ảnh hưởng compiled expression

## Mục tiêu

SpEL có thể đánh giá expression bằng interpreter hoặc biên dịch expression thành bytecode để tăng tốc. Compiler thu thập thông tin kiểu từ những lần đánh giá interpreted trước đó rồi dùng thông tin này để sinh mã. Vì vậy, một compiled expression thường hoạt động tốt nhất khi các kiểu dữ liệu mà nó quan sát được ổn định qua các lần đánh giá.

Nếu cùng một expression được dùng với nhiều root object, property hoặc giá trị có kiểu runtime khác nhau, giả định kiểu đã dùng khi biên dịch có thể không còn đúng. Khi đó compiled expression có thể thất bại dù expression vẫn có thể được interpreter đánh giá thành công với dữ liệu mới.

Sau bài này, bạn có thể:

- Hiểu vì sao SpEL compiler dựa vào thông tin kiểu thu thập từ interpreted evaluation.
- Nhận diện những thay đổi kiểu runtime có thể làm compiled expression thất bại.
- Phân biệt hành vi của OFF, IMMEDIATE và MIXED compiler mode.
- Chọn mode phù hợp với tính ổn định của dữ liệu và side effect của expression.
- Cấu hình compiler qua SpelParserConfiguration.
- Kiểm tra class loader và giới hạn của compiler.
- Thiết kế test với nhiều kiểu dữ liệu runtime và theo dõi fallback.

## 1. Interpreter và compiler trong SpEL

Theo mặc định, SpEL đánh giá expression bằng interpreter. Interpreter thực hiện các node trong expression tree khi ứng dụng gọi getValue() hoặc setValue(). Cách này linh hoạt vì SpEL có thể xử lý nhiều kiểu object và quyết định truy cập property, method hoặc toán tử trong lúc chạy.

SpEL compiler có thể tạo một Java class chứa logic của expression dưới dạng bytecode. Sau khi expression được biên dịch, các lần đánh giá tiếp theo có thể chạy nhanh hơn do không phải diễn giải toàn bộ expression tree theo cùng cách.

Compiler không biết trước mọi kiểu runtime chỉ từ chuỗi expression. Ví dụ, expression có property reference có thể nhận object với kiểu thực tế khác nhau. SpEL dùng các lần interpreted evaluation để quan sát kiểu của các phần tử expression rồi mới sinh bytecode dựa trên thông tin đã thu thập.

Điều này tạo ra một giả định quan trọng: kiểu dữ liệu trong các lần đánh giá sau sẽ tương thích với kiểu đã quan sát lúc biên dịch. Nếu giả định đó không đúng, compiled expression có thể không còn phù hợp với dữ liệu mới.

## 2. Vì sao thay đổi kiểu runtime gây lỗi?

Một expression có thể được đánh giá với nhiều root object hoặc nhiều giá trị đầu vào. Nếu property, method result hoặc phần tử dữ liệu thay đổi kiểu giữa các lần gọi, interpreter có thể phân giải lại thao tác theo kiểu mới, trong khi bytecode đã biên dịch có thể đang dựa trên kiểu cũ.

Các nguồn thay đổi thường gặp:

- Cùng expression được dùng cho nhiều class triển khai chung một interface nhưng trả về kiểu property khác nhau.
- Một property khai báo kiểu rộng như Object hoặc Number nhưng giá trị thực tế thay đổi giữa các lần đánh giá.
- Method trả về các implementation hoặc kiểu con khác nhau tùy dữ liệu.
- Biến trong EvaluationContext nhận giá trị thuộc kiểu khác qua từng request.
- Root object thay đổi giữa các message hoặc loại sự kiện.
- Dữ liệu collection chứa phần tử không đồng nhất.
- Một giá trị ban đầu null rồi các lần sau có kiểu runtime cụ thể, hoặc ngược lại.

Ví dụ, expression đọc property payload:

~~~text
payload
~~~

Lần đầu payload có thể chứa String. Lần sau cùng expression được đánh giá với một object khác và payload lại chứa một kiểu khác. Interpreter có thể trả về giá trị theo object hiện tại, nhưng compiled form có thể đã được tạo với giả định kiểu từ lần đầu.

Ví dụ với biểu thức số:

~~~text
#root.value + 1
~~~

Nếu value thay đổi giữa Integer, Long, BigDecimal hoặc một kiểu số khác, cách xử lý số và kiểu kết quả có thể thay đổi. Compiled form được sinh dựa trên kiểu đã quan sát trước đó có thể không xử lý được mọi biến thể.

Không phải mọi thay đổi kiểu đều chắc chắn làm lỗi. Vấn đề xuất hiện khi kiểu mới không còn tương thích với các giả định hoặc bytecode mà compiler đã tạo. Cần kiểm thử với tập kiểu runtime thực tế của ứng dụng.

## 3. Compiler học kiểu từ interpreted evaluation

Quá trình điển hình:

1. Ứng dụng parse expression thành một Expression.
2. Một lần đánh giá interpreted chạy và các node thu thập thông tin kiểu runtime.
3. Khi compiler mode cho phép và expression đủ điều kiện, SpEL thử biên dịch expression.
4. Bytecode được tạo dựa trên cấu trúc expression và thông tin kiểu đã quan sát.
5. Các lần đánh giá tiếp theo có thể dùng compiled form.
6. Nếu kiểu runtime thay đổi và không tương thích, compiled evaluation có thể thất bại.

Điểm quan trọng là compiler không suy luận đầy đủ mọi kiểu dữ liệu có thể xuất hiện trong tương lai. Nó tối ưu cho những kiểu đã quan sát trong quá trình đánh giá.

Vì vậy, compiled expression phù hợp hơn với luồng dữ liệu có schema và kiểu ổn định. Với rule engine nhận nhiều loại object, message không đồng nhất hoặc biến có kiểu thay đổi thường xuyên, interpreted mode có thể là lựa chọn an toàn và dễ dự đoán hơn.

## 4. Ba compiler mode

SpEL định nghĩa ba mode trong enum SpelCompilerMode:

| Mode | Hành vi |
|---|---|
| OFF | Tắt compiler; mọi expression được đánh giá bằng interpreter. Đây là mặc định. |
| IMMEDIATE | Biên dịch sớm nhất có thể, thường sau lần interpreted evaluation đầu tiên. Lỗi từ compiled evaluation được trả về cho caller. |
| MIXED | Chuyển đổi giữa interpreted và compiled theo thời gian. Nếu compiled evaluation thất bại, lỗi được xử lý nội bộ và expression quay lại interpreted mode. |

### OFF

OFF phù hợp khi kiểu dữ liệu thay đổi thường xuyên, expression không nằm trên đường hiệu năng quan trọng hoặc ứng dụng ưu tiên tính linh hoạt.

Không có compiled form nên không có lỗi do giả định kiểu của bytecode. Interpreter vẫn có thể phát sinh lỗi nghiệp vụ hoặc lỗi truy cập property bình thường; OFF không làm expression miễn nhiễm với lỗi dữ liệu.

### IMMEDIATE

IMMEDIATE yêu cầu SpEL biên dịch expression sớm nhất có thể, thường sau lần đánh giá interpreted đầu tiên.

Nếu compiled expression thất bại, ví dụ vì kiểu runtime thay đổi, exception được trả về cho caller. Ứng dụng có thể phát hiện lỗi ngay tại lần đánh giá đó và quyết định xử lý theo chính sách riêng.

Chọn IMMEDIATE khi:

- Kiểu runtime ổn định và đã được kiểm soát.
- Muốn lỗi compiled evaluation hiển thị rõ cho caller.
- Expression không nên được tự động chạy lại ở một chế độ khác sau lỗi.
- Cần tránh việc fallback âm thầm đối với expression có side effect.

IMMEDIATE không tự sửa hoặc làm cho kiểu dữ liệu ổn định. Nó chỉ quyết định cách lỗi compiled evaluation được truyền ra ngoài.

### MIXED

MIXED cho phép SpEL chuyển giữa interpreted và compiled trong thời gian chạy. Sau một số lần interpreted evaluation thành công, expression có thể được biên dịch. Nếu compiled form thất bại, lỗi được bắt nội bộ và expression quay lại interpreted mode. Sau đó compiler có thể thử tạo compiled form khác.

Chu kỳ này có thể tiếp tục cho tới khi SpEL xác định không nên thử biên dịch nữa, chẳng hạn sau khi đạt ngưỡng thất bại. Khi đó expression sẽ tiếp tục ở interpreted mode.

MIXED hữu ích khi muốn tận dụng compilation nhưng vẫn có khả năng quay lại interpreter nếu kiểu runtime thay đổi. Tuy nhiên, fallback không phải lúc nào cũng an toàn đối với expression có side effect.

## 5. Vì sao MIXED có thể chạy expression nhiều lần?

Tài liệu Spring cảnh báo rằng MIXED có thể gây vấn đề với expression có side effect. Nếu compiled expression đã thực hiện một phần thao tác rồi mới thất bại, SpEL có thể quay lại interpreted mode và đánh giá lại expression.

Ví dụ không nên đặt thao tác gửi thông báo hoặc cập nhật trạng thái vào một expression có thể chạy trong MIXED:

~~~text
#service.sendNotification(#root)
~~~

Nếu lần compiled evaluation thực hiện được một phần side effect trước khi lỗi, việc fallback và chạy lại có thể khiến thao tác được thực hiện lần thứ hai.

Vì vậy:

- Ưu tiên expression thuần, chỉ đọc dữ liệu và tính toán.
- Không đặt thao tác ghi dữ liệu, gửi message, thanh toán hoặc gọi API có side effect vào expression được đánh giá lặp lại.
- Nếu không thể loại bỏ side effect, không dựa vào MIXED để tự động fallback.
- Đưa hành động có side effect vào Java service với cơ chế idempotency, transaction và xử lý lỗi phù hợp.

IMMEDIATE giúp exception được trả về thay vì tự động chuyển về interpreted mode, nhưng không thể hoàn tác side effect đã xảy ra trước thời điểm compiled evaluation thất bại. Thiết kế tốt nhất vẫn là tách tính toán expression khỏi hành động thay đổi trạng thái.

## 6. Cấu hình compiler qua SpelParserConfiguration

Compiler được tắt mặc định. Có thể cấu hình mode khi tạo parser bằng SpelParserConfiguration.

Ví dụ với IMMEDIATE:

~~~java
SpelParserConfiguration configuration =
    SpelParserConfiguration.builder()
        .compilerMode(SpelCompilerMode.IMMEDIATE)
        .compilerClassLoader(getClass().getClassLoader())
        .build();

SpelExpressionParser parser =
    new SpelExpressionParser(configuration);

Expression expression = parser.parseExpression("payload");
~~~

Ví dụ dùng MIXED:

~~~java
SpelParserConfiguration configuration =
    SpelParserConfiguration.builder()
        .compilerMode(SpelCompilerMode.MIXED)
        .build();

SpelExpressionParser parser =
    new SpelExpressionParser(configuration);
~~~

Với OFF, có thể để mặc định hoặc cấu hình rõ:

~~~java
SpelParserConfiguration configuration =
    SpelParserConfiguration.builder()
        .compilerMode(SpelCompilerMode.OFF)
        .build();
~~~

API builder có thể khác giữa các phiên bản Spring. Hãy đối chiếu Javadoc của phiên bản đang dùng nếu dự án sử dụng constructor hoặc builder API khác.

Ngoài cấu hình parser, khi SpEL được nhúng trong một component khác và không thể cấu hình parser trực tiếp, có thể đặt property JVM hoặc SpringProperties:

~~~text
spring.expression.compiler.mode=off
spring.expression.compiler.mode=immediate
spring.expression.compiler.mode=mixed
~~~

Tên property nhận một trong ba giá trị tương ứng. Hãy xác định nguồn cấu hình thực tế của ứng dụng và tránh đặt mode khác nhau ở nhiều nơi mà không có quy ước.

## 7. ClassLoader của compiled expression

Compiled expression được định nghĩa trong một child ClassLoader. SpelParserConfiguration cho phép chỉ định compilerClassLoader làm class loader cha cho quá trình này.

ClassLoader được cung cấp cần nhìn thấy tất cả kiểu dữ liệu tham gia vào expression evaluation, bao gồm:

- Kiểu của root object.
- Kiểu property hoặc method result.
- Kiểu đối số và kết quả của method.
- Các class nghiệp vụ được expression tham chiếu.
- Các kiểu được load bởi module, plugin hoặc application class loader.

Nếu class loader không nhìn thấy một kiểu, quá trình tạo hoặc chạy compiled expression có thể thất bại dù interpreter có thể truy cập kiểu đó thông qua cấu hình khác.

Khi không chỉ định class loader, Spring sử dụng class loader mặc định, thường là context class loader của thread đang đánh giá expression.

Trong ứng dụng dùng plugin, application server, module layer hoặc nhiều class loader, cần kiểm tra class visibility kỹ hơn. Không nên chọn class loader chỉ vì nó có thể load SpelExpressionParser; nó cần nhìn thấy toàn bộ kiểu liên quan tới expression.

## 8. Giới hạn của SpEL compiler

Không phải expression nào cũng có thể biên dịch. Compiler tập trung vào những cấu trúc phổ biến có khả năng đem lại lợi ích hiệu năng.

Theo tài liệu Spring, các nhóm expression sau không được hỗ trợ compilation:

- Expression có phép gán.
- Expression phụ thuộc ConversionService.
- Expression dùng custom resolver.
- Expression dùng overloaded operator.
- Expression dùng Optional cùng null-safe operator hoặc Elvis operator.
- Expression dùng cú pháp tạo array.
- Expression dùng selection hoặc projection.
- Expression dùng bean reference.

Nếu expression không thể biên dịch, SpEL tiếp tục dùng interpreter theo cơ chế của mode và phiên bản framework. Không nên giả định rằng bật compiler mode nghĩa là mọi expression đều được chuyển thành bytecode.

Khi đánh giá hiệu năng, hãy xác nhận expression thực tế có thể compile. Nếu không, tối ưu compiler mode sẽ không mang lại lợi ích cho expression đó.

## 9. Thiết kế expression ổn định về kiểu

Để compiled expression hoạt động ổn định:

- Dùng một kiểu root object nhất quán cho expression.
- Giữ kiểu property và kiểu trả về của method ổn định qua các lần đánh giá.
- Chuẩn hóa dữ liệu đầu vào trước khi đưa vào EvaluationContext.
- Tránh cùng một property lúc trả String, lúc trả Number hoặc object không liên quan.
- Không trộn nhiều implementation có contract runtime không tương thích nếu expression cần compilation.
- Tách expression theo nhóm kiểu dữ liệu khi các nhóm input khác nhau rõ rệt.
- Dùng DTO có kiểu cụ thể thay cho Map hoặc Object nếu schema đã biết.
- Kiểm tra null và kiểu đầu vào trước khi đánh giá khi nghiệp vụ yêu cầu.

Ví dụ, nếu expression luôn cần số tiền, hãy chuẩn hóa amount thành BigDecimal trước khi đặt vào root object hoặc biến. Không để cùng một biến amount lần thì String, lần thì Double, lần thì BigDecimal rồi kỳ vọng compiled expression xử lý mọi trường hợp giống interpreter.

Nếu ứng dụng cần xử lý nhiều loại message, có thể dùng một expression riêng cho từng loại message hoặc chuẩn hóa message thành một model chung có kiểu rõ ràng trước khi đánh giá.

## 10. Phân biệt lỗi do type change với lỗi nghiệp vụ

Một compiled expression thất bại không nhất thiết có nghĩa dữ liệu nghiệp vụ sai. Có thể expression vẫn hợp lệ nhưng kiểu runtime hiện tại khác kiểu mà compiler đã dùng khi tạo bytecode.

Khi điều tra, kiểm tra:

1. Expression đã được parse bằng compiler mode nào?
2. Expression đã được compile hay vẫn đang interpreted?
3. Kiểu runtime ở lần đánh giá đầu và lần đánh giá gây lỗi có khác nhau không?
4. Root object, property hoặc method result nào thay đổi kiểu?
5. Lỗi là ClassCastException, lỗi method/property access hay exception compile/evaluation?
6. Expression có nằm trong danh sách cấu trúc không hỗ trợ compilation không?
7. ClassLoader có nhìn thấy kiểu mới không?

Không nên xử lý mọi lỗi bằng cách tắt compiler ngay lập tức. Trước tiên xác định liệu expression có cần compiler hay không, và liệu kiểu runtime có thể được chuẩn hóa.

Nếu dữ liệu vốn đa hình và cần xử lý linh hoạt, OFF hoặc MIXED có thể phù hợp hơn IMMEDIATE. Nếu kiểu thay đổi là dấu hiệu vi phạm contract dữ liệu, nên sửa ở tầng model hoặc validation.

## 11. Kiểm thử khi kiểu runtime thay đổi

Một test chỉ dùng một kiểu dữ liệu không đủ để phát hiện giả định kiểu bị giữ lại. Hãy kiểm tra cùng expression với nhiều root object và kiểu property khác nhau.

Ví dụ model có property khai báo rộng:

~~~java
public class PayloadMessage {
    private final Object payload;

    public PayloadMessage(Object payload) {
        this.payload = payload;
    }

    public Object getPayload() {
        return this.payload;
    }
}
~~~

Expression đơn giản đọc payload:

~~~java
Expression expression = parser.parseExpression("payload");
~~~

Đánh giá lần lượt với nhiều giá trị:

~~~java
Object first = expression.getValue(
    new PayloadMessage("hello"));

Object second = expression.getValue(
    new PayloadMessage(42));
~~~

Ở interpreted mode, expression đọc property từ từng root object theo dữ liệu hiện tại. Khi compiler được bật, cần kiểm thử lại cùng chuỗi kiểu và xác nhận hành vi khi kiểu khác với kiểu đã quan sát trong giai đoạn đầu.

Với expression có toán tử hoặc method call, hãy chọn các kiểu runtime có thể xuất hiện thật trong production và kiểm tra cả trường hợp thành công lẫn thất bại. Không chỉ kiểm thử hai kiểu tương thích; hãy bao phủ cả kiểu không tương thích và null nếu chúng được phép theo contract.

Các trường hợp nên có:

- Cùng một kiểu runtime qua mọi lần đánh giá.
- Hai kiểu con khác nhau của cùng interface.
- Property có kiểu khai báo Object nhưng runtime value thay đổi.
- Method result thay đổi kiểu theo input.
- Giá trị null trước và sau một giá trị có kiểu cụ thể.
- Thay đổi kiểu sau khi expression đã compile.
- Class được load từ class loader khác.
- Expression không hỗ trợ compilation.
- Compiled evaluation thất bại trong IMMEDIATE.
- Fallback về interpreted mode trong MIXED.
- Expression có side effect để xác nhận không bị thực thi lặp ngoài ý muốn.

## 12. Chẩn đoán và quan sát compiler behavior

Khi một expression chỉ lỗi sau nhiều lần đánh giá, hãy ghi nhận dữ liệu đủ để so sánh các lần gọi:

- ID hoặc nội dung đã version hóa của expression.
- Compiler mode đang dùng.
- Kiểu của root object.
- Kiểu runtime của property và method result quan trọng.
- Loại exception và cause chain.
- ClassLoader được cấu hình.
- Expression có hỗ trợ compilation hay không.

Có thể bật logging phù hợp cho package SpEL để quan sát việc compile trong môi trường kiểm thử. Tránh bật log quá chi tiết trong production nếu nó làm lộ dữ liệu expression hoặc tạo lượng log lớn.

Đừng suy luận rằng expression đang chạy compiled chỉ vì compiler mode khác OFF. Expression có thể không thuộc tập cấu trúc được hỗ trợ hoặc compiler chưa đủ thông tin để tạo bytecode.

Để đo hiệu năng, benchmark cùng dữ liệu, cùng context setup và cùng số lần đánh giá. So sánh OFF với mode cần dùng; đồng thời tính cả chi phí tạo context, conversion và truy cập dữ liệu bên ngoài nếu chúng nằm trên đường chạy thực tế.

## 13. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Compiled expression lỗi sau lần chạy đầu | Kiểu runtime khác với kiểu được dùng khi compile | Chuẩn hóa kiểu, tách expression hoặc chọn mode phù hợp |
| IMMEDIATE trả exception | Compiled evaluation thất bại và exception được chuyển cho caller | Kiểm tra type change, class visibility và expression |
| MIXED chuyển về interpreter | Compiled evaluation thất bại | Kiểm tra kiểu dữ liệu và theo dõi các lần thử compile tiếp theo |
| Expression không được compile | Cấu trúc nằm ngoài giới hạn compiler hoặc thiếu thông tin kiểu | Dùng interpreter hoặc viết lại expression nếu hợp lý |
| Lỗi ClassCastException | Bytecode dùng giả định kiểu không còn đúng | So sánh runtime type trước và sau compile |
| Lỗi chỉ xảy ra trong plugin/runtime container | Compiler class loader không thấy kiểu liên quan | Cấu hình class loader phù hợp |
| Side effect xuất hiện hai lần | MIXED fallback sau khi compiled form đã thực hiện một phần thao tác | Loại side effect khỏi expression và xử lý trong Java |
| Hiệu năng không cải thiện | Expression không compile hoặc chi phí khác chiếm phần lớn | Đo lại và kiểm tra compiler eligibility |
| Expression chạy được ở OFF nhưng không ở IMMEDIATE | Kiểu runtime thay đổi hoặc bytecode assumption không phù hợp | Giữ OFF/MIXED hoặc chuẩn hóa input theo contract |

## 14. Quy trình chọn compiler mode

1. **Xác định độ ổn định kiểu.** Kiểm tra root object, property và method result qua các lần đánh giá.
2. **Kiểm tra compiler eligibility.** Xác nhận expression không dùng cấu trúc bị giới hạn.
3. **Đo hiệu năng trước.** Xác định expression có thực sự nằm trên đường hiệu năng quan trọng.
4. **Chọn OFF nếu cần linh hoạt.** Dùng interpreter khi kiểu thay đổi thường xuyên hoặc compilation không đem lại lợi ích rõ.
5. **Chọn IMMEDIATE khi kiểu ổn định.** Dùng khi muốn lỗi compiled evaluation được trả trực tiếp cho caller.
6. **Chọn MIXED khi chấp nhận fallback.** Chỉ dùng khi expression không có side effect hoặc việc đánh giá lại được kiểm soát.
7. **Kiểm tra ClassLoader.** Bảo đảm generated class có thể nhìn thấy tất cả kiểu tham gia.
8. **Kiểm thử type changes.** Chạy nhiều lần với các kiểu thực tế, bao gồm kiểu mới xuất hiện sau khi compile.
9. **Theo dõi production.** Ghi nhận exception, mode và runtime type mà không log dữ liệu nhạy cảm.

## 15. Thực hành tốt

- Chỉ bật compiler khi benchmark cho thấy lợi ích đáng kể.
- Giữ kiểu runtime ổn định nếu dùng compiled expression.
- Chuẩn hóa dữ liệu và dùng model có kiểu cụ thể.
- Dùng OFF khi expression cần tính linh hoạt với nhiều kiểu.
- Dùng IMMEDIATE khi muốn lỗi compiled evaluation hiển thị cho caller.
- Dùng MIXED khi fallback an toàn và expression không có side effect.
- Không đặt thao tác ghi hoặc gọi dịch vụ có side effect trong expression có thể được MIXED đánh giá lại.
- Cấu hình compiler qua SpelParserConfiguration và chọn ClassLoader có thể thấy các kiểu liên quan.
- Kiểm tra compiler limitations trước khi tối ưu expression.
- Kiểm thử cùng expression với nhiều root object và kiểu runtime.
- Theo dõi type changes và exception sau khi triển khai.
- Tách logic nghiệp vụ có side effect sang Java service.

## 16. Checklist review

Trước khi bật SpEL compiler, hãy kiểm tra:

- [ ] Đã xác định kiểu runtime của root object và các property quan trọng.
- [ ] Kiểu property và method result ổn định qua các lần đánh giá.
- [ ] Input được chuẩn hóa theo contract dữ liệu.
- [ ] Expression thuộc nhóm compiler hỗ trợ.
- [ ] Compiler mode được chọn rõ ràng.
- [ ] OFF, IMMEDIATE và MIXED có hành vi phù hợp với yêu cầu lỗi.
- [ ] MIXED không thể vô tình chạy lại side effect.
- [ ] ClassLoader có thể nhìn thấy tất cả kiểu liên quan.
- [ ] Có test cho kiểu ổn định và kiểu thay đổi sau compile.
- [ ] Có test cho null và nhiều implementation nếu được phép.
- [ ] Hiệu năng đã được đo với workload thực tế.
- [ ] Có logging/diagnostic đủ để nhận biết lỗi type change.

## Kết luận

SpEL compiler tạo bytecode dựa trên thông tin kiểu thu thập từ interpreted evaluation. Nếu kiểu runtime của root object, property hoặc method result thay đổi sau khi expression được compile, bytecode có thể không còn phù hợp. OFF luôn dùng interpreter; IMMEDIATE trả lỗi compiled evaluation cho caller; MIXED có thể quay lại interpreter và thử compile lại sau đó. Vì MIXED có thể đánh giá lại expression sau lỗi, không đặt side effect vào expression được xử lý theo mode này. Hãy chỉ bật compiler khi kiểu dữ liệu ổn định, expression được hỗ trợ, class loader phù hợp và benchmark xác nhận lợi ích.

## Tài liệu tham khảo

- Spring Framework Reference — SpEL Evaluation and Compilation: https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html
- Spring Framework API — SpelCompilerMode: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/SpelCompilerMode.html
- Spring Framework API — SpelParserConfiguration: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/standard/SpelParserConfiguration.html