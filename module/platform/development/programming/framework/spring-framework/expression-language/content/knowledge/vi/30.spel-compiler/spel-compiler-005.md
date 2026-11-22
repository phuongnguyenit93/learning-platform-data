# Expression không hỗ trợ compiler và cơ chế fallback

Spring Expression Language (SpEL) có hai cách thực thi expression: **interpreted mode** (diễn giải) và **compiled mode** (biên dịch). Interpreted mode linh hoạt vì mỗi lần đánh giá, SpEL xử lý cấu trúc expression bằng interpreter. Compiled mode tạo bytecode Java cho expression để giảm chi phí xử lý khi expression được đánh giá thường xuyên.

Không phải expression nào cũng có thể biên dịch. Một số cú pháp và khả năng mở rộng phụ thuộc vào runtime context nên compiler không thể tạo bytecode tương ứng. Trong trường hợp đó, expression vẫn có thể chạy bằng interpreter. Vì vậy, **không biên dịch được không đồng nghĩa expression không hợp lệ hoặc không thể đánh giá**.

Ngoài ra, khi expression đã được biên dịch nhưng thất bại trong lúc chạy, cách xử lý phụ thuộc vào **SpelCompilerMode**:

- **OFF:** luôn diễn giải.
- **IMMEDIATE:** dùng compiled expression khi có thể; lỗi từ compiled evaluation được trả về cho caller.
- **MIXED:** tự chuyển qua lại giữa interpreted và compiled; nếu compiled evaluation thất bại, SpEL bắt lỗi nội bộ và quay về interpreter.

Hiểu rõ giới hạn và chế độ này giúp chọn cách thực thi phù hợp, tránh kỳ vọng rằng bật compiler sẽ làm mọi expression tự động chạy nhanh hơn hoặc luôn fallback an toàn.

## 1. Interpreted mode và compiled mode

### 1.1. Interpreted mode

Ở interpreted mode, SpEL phân tích expression thành cấu trúc nội bộ rồi interpreter đánh giá cấu trúc đó khi gọi getValue() hoặc setValue().

Ví dụ:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression =
        parser.parseExpression("customer.address.city");

String city = expression.getValue(order, String.class);
~~~

Interpreter đọc property customer, tiếp tục đọc address rồi lấy city. Các thao tác truy cập và kiểu dữ liệu được xử lý trong quá trình đánh giá.

Interpreted mode phù hợp khi:

- Expression chỉ được đánh giá thỉnh thoảng.
- Kiểu dữ liệu đầu vào có thể thay đổi giữa các lần gọi.
- Expression dùng các tính năng chưa được compiler hỗ trợ.
- Ứng dụng cần sự linh hoạt của custom resolver hoặc conversion service.
- Tính đúng đắn và khả năng tương thích quan trọng hơn chi phí đánh giá nhỏ.

### 1.2. Compiled mode

SpEL compiler có thể tạo một Java class đại diện cho hành vi của expression trong runtime. Khi đã có compiled form, những lần đánh giá sau có thể chạy nhanh hơn vì không phải thực hiện toàn bộ quá trình diễn giải.

Ví dụ expression có chuỗi truy cập property và phép toán số học:

~~~text
#order.items[0].price * #quantity
~~~

Nếu expression và kiểu dữ liệu liên quan phù hợp với compiler, SpEL có thể tạo bytecode để thực hiện các thao tác đó.

Compiler cần biết kiểu của những phần tử trong expression. Một số kiểu chỉ có thể được suy ra sau các lần interpreted evaluation. Vì vậy, compiled expression thường dựa trên thông tin kiểu đã quan sát được khi chạy interpreter.

Đây cũng là giới hạn quan trọng: nếu kiểu dữ liệu thay đổi giữa các lần evaluate, compiled form có thể không còn phù hợp.

### 1.3. Compiler không phải là một parser khác

Cả hai chế độ đều dùng cùng cú pháp và mô hình expression của SpEL. Compiler chỉ thay đổi cách thực thi expression sau khi parse.

Một expression có thể:

- Parse thành công và chạy bằng interpreter.
- Parse thành công, nhưng không thể biên dịch.
- Parse và biên dịch được, nhưng compiled evaluation thất bại với một bộ dữ liệu khác.
- Chạy ổn định ở cả hai chế độ.

Do đó, cần tách ba giai đoạn: parse expression, xác định khả năng compile và evaluate expression với dữ liệu thực tế.

## 2. Những loại expression không hỗ trợ compiler

Tài liệu Spring hiện hành liệt kê các nhóm expression sau là không thể biên dịch. Danh sách có thể thay đổi theo phiên bản Spring Framework, nên hãy đối chiếu tài liệu của đúng phiên bản ứng dụng đang sử dụng.

| Nhóm expression | Ví dụ hoặc dấu hiệu | Vì sao cần interpreter |
| --- | --- | --- |
| Assignment | name = 'Linh' | Có thao tác ghi giá trị vào property hoặc variable |
| Dựa vào ConversionService | Chuyển String sang kiểu domain qua converter | Phụ thuộc cơ chế chuyển đổi runtime của context |
| Custom resolver | Dùng resolver do ứng dụng cung cấp | Hành vi không được compiler mặc định sinh bytecode |
| Overloaded operators | Toán tử được xử lý qua operator overloader | Cách thực thi phụ thuộc resolver tùy chỉnh |
| Optional với null-safe hoặc Elvis | #value?.name hoặc #value ?: 'default' khi value là Optional | Một số thao tác Optional này chưa được compiler hỗ trợ |
| Array construction | new int[] {1, 2, 3} | Tạo array theo cú pháp constructor đặc biệt |
| Selection hoặc projection | #orders.?[total > 100], #orders.![id] | Duyệt và biến đổi collection bằng các operator chuyên biệt |
| Bean reference | @priceService.calculate(#order) | Cần BeanResolver để tìm bean trong context |

Lưu ý một số điểm dễ nhầm:

- **Array construction** không đồng nghĩa mọi thao tác với array đều không compile được. Truy cập phần tử như #scores[0] là một thao tác khác với tạo array bằng new int[] {...}.
- **Selection và projection** là hai operator khác nhau, nhưng cả hai đều nằm trong nhóm không được compiler hỗ trợ.
- **Bean reference** có thể hoạt động bình thường ở interpreted mode nếu EvaluationContext có BeanResolver. Giới hạn ở đây là compiler không biên dịch được expression đó.
- **ConversionService** là cơ chế chuyển đổi kiểu của context. Một expression cần conversion service có thể vẫn chạy đúng khi được diễn giải.
- **Custom resolver** là khả năng mở rộng của EvaluationContext; không nên kỳ vọng compiler hiểu được hành vi riêng do ứng dụng định nghĩa.

Nếu expression chứa một trong các tính năng này, hãy để interpreter xử lý hoặc tách phần cần biên dịch thành một expression đơn giản hơn nếu điều đó phù hợp với thiết kế.

## 3. Vì sao kiểu dữ liệu thay đổi có thể làm compiled expression thất bại?

SpEL không thể biết mọi kiểu runtime chỉ bằng cách đọc chuỗi expression. Ví dụ:

~~~text
#payload.amount
~~~

Trong lần evaluate đầu tiên, payload có thể là Invoice. Compiler ghi nhận amount có kiểu BigDecimal và tạo bytecode dựa trên thông tin đó.

Nếu một lần evaluate sau truyền payload là một object khác, chẳng hạn Quote có amount là String, compiled expression có thể không còn thực hiện được thao tác đã sinh ra.

Tình huống tương tự xảy ra khi:

- Một property trả về kiểu khác theo trạng thái hoặc implementation.
- Collection thay đổi kiểu phần tử giữa các lần evaluate.
- Root object được truyền vào không cùng cấu trúc hoặc kiểu với những lần trước.
- Custom conversion hoặc resolver thay đổi hành vi theo request.
- Class được tải qua classloader khác với classloader dùng khi biên dịch.

Compiled mode phù hợp nhất với expression có cấu trúc và kiểu dữ liệu ổn định qua nhiều lần đánh giá. Nếu một expression được dùng với nhiều loại root object, hãy cân nhắc giữ interpreted mode hoặc tạo expression/parser riêng theo từng kiểu dữ liệu.

## 4. Cấu hình chế độ compiler

Compiler không được bật mặc định. Chế độ được điều khiển bằng enum **SpelCompilerMode** trong package org.springframework.expression.spel.

Có ba chế độ:

| Mode | Hành vi |
| --- | --- |
| OFF | Tắt compiler; mọi expression được đánh giá bằng interpreter. Đây là mặc định. |
| IMMEDIATE | Compiler thử biên dịch expression sớm, thường sau lần interpreted evaluation đầu tiên. Nếu compiled evaluation thất bại, exception được trả về cho caller. |
| MIXED | Sau một số lần interpreted evaluation thành công, expression có thể được biên dịch. Nếu compiled evaluation thất bại, SpEL bắt lỗi nội bộ và quay lại interpreter. |

### 4.1. Cấu hình bằng SpelParserConfiguration

Có thể truyền compiler mode và classloader vào SpelParserConfiguration khi tạo parser:

~~~java
SpelParserConfiguration configuration =
        SpelParserConfiguration.builder()
                .compilerMode(SpelCompilerMode.MIXED)
                .compilerClassLoader(getClass().getClassLoader())
                .build();

ExpressionParser parser =
        new SpelExpressionParser(configuration);

Expression expression =
        parser.parseExpression("payload.amount * 1.08");
~~~

Ở đây parser dùng MIXED mode. Classloader được cung cấp làm parent cho classloader tạo compiled expression.

Nếu không cần chỉ định classloader riêng, có thể bỏ compilerClassLoader và dùng classloader mặc định mà Spring lựa chọn.

Với các phiên bản Spring cũ hơn chưa có builder API, hãy dùng constructor SpelParserConfiguration được cung cấp trong phiên bản đó. Luôn kiểm tra Javadoc của dependency thực tế thay vì sao chép API từ một phiên bản khác.

### 4.2. Cấu hình qua system property

Khi SpEL được sử dụng bên trong một module hoặc integration point mà ứng dụng không trực tiếp tạo parser, có thể cấu hình compiler mode bằng property:

~~~text
spring.expression.compiler.mode
~~~

Property nhận một trong các giá trị:

~~~text
off
immediate
mixed
~~~

Có thể đặt qua JVM system property hoặc cơ chế SpringProperties. Đây là cách cấu hình ở phạm vi rộng hơn, nên cần cân nhắc ảnh hưởng tới các expression khác trong cùng ứng dụng.

Nếu ứng dụng tự quản lý parser, cấu hình trực tiếp bằng SpelParserConfiguration thường giúp giới hạn mode cho parser đó.

## 5. Cơ chế fallback trong từng mode

Cần phân biệt hai tình huống:

1. Expression không nằm trong tập tính năng compiler hỗ trợ nên không thể tạo compiled form.
2. Expression đã được biên dịch nhưng một lần chạy compiled form thất bại, chẳng hạn do kiểu runtime thay đổi.

Fallback chủ yếu nói về tình huống thứ hai. Một expression không hỗ trợ compile vẫn có thể chạy bằng interpreter; đó không phải là lỗi runtime cần MIXED mode khôi phục.

### 5.1. OFF: luôn dùng interpreter

Với OFF, compiler bị tắt:

~~~java
SpelParserConfiguration configuration =
        SpelParserConfiguration.builder()
                .compilerMode(SpelCompilerMode.OFF)
                .build();
~~~

Mọi lần evaluate đều dùng interpreter. Không có compiled form nên cũng không có fallback từ compiled sang interpreted.

Chọn OFF khi expression dùng selection, projection, bean reference, assignment hoặc tính năng khác chưa hỗ trợ compile; khi kiểu dữ liệu thay đổi thường xuyên; hoặc khi muốn hành vi thực thi dễ dự đoán.

### 5.2. IMMEDIATE: lỗi compiled evaluation được trả về

Trong IMMEDIATE mode, SpEL thử biên dịch expression sớm, thường sau lần diễn giải đầu tiên để thu thập thông tin kiểu.

Nếu compiled expression chạy thất bại, caller nhận exception. SpEL không tự âm thầm chạy lại expression bằng interpreter như MIXED mode.

Ví dụ:

~~~java
SpelParserConfiguration configuration =
        SpelParserConfiguration.builder()
                .compilerMode(SpelCompilerMode.IMMEDIATE)
                .build();

SpelExpressionParser parser =
        new SpelExpressionParser(configuration);
~~~

IMMEDIATE phù hợp khi kiểu dữ liệu ổn định và ứng dụng muốn nhận lỗi rõ ràng nếu compiled form không còn phù hợp.

Không nên chọn IMMEDIATE chỉ vì muốn tốc độ cao. Trước tiên cần xác nhận expression nằm trong phạm vi compiler hỗ trợ và dữ liệu có kiểu ổn định.

### 5.3. MIXED: tự quay về interpreter

MIXED mode cho phép expression chuyển đổi giữa interpreted và compiled trong quá trình sử dụng:

1. Expression được đánh giá bằng interpreter trong những lần đầu.
2. Sau một số lần chạy thành công, compiler có thể tạo compiled form.
3. Các lần tiếp theo có thể dùng compiled form.
4. Nếu compiled evaluation thất bại, lỗi được bắt nội bộ và expression quay về interpreter.
5. Sau đó compiler có thể thử tạo compiled form mới.
6. Nếu việc compile tiếp tục thất bại đủ nhiều lần, SpEL có thể ngừng thử và giữ expression ở interpreted mode.

Cơ chế này giúp ứng dụng tiếp tục chạy khi thông tin kiểu đã suy ra không còn phù hợp. Tuy nhiên, fallback không có nghĩa mọi lỗi nghiệp vụ đều được bỏ qua. Lỗi do dữ liệu không hợp lệ, null không được xử lý hoặc method ném exception vẫn cần được xử lý theo đúng ngữ nghĩa expression.

### 5.4. MIXED có thể chạy lại một phần expression

MIXED mode có một rủi ro quan trọng với expression có side effect.

Nếu compiled expression thực hiện được một phần hành động rồi thất bại, SpEL có thể quay về interpreter và đánh giá lại expression. Phần đã chạy trước khi lỗi có thể bị thực hiện lần thứ hai.

Ví dụ không nên dùng trong MIXED:

~~~text
@paymentService.charge(#account, #amount)
~~~

Nếu thao tác charge đã tạo giao dịch trước khi một node khác thất bại, lần interpreted retry có thể tạo thêm giao dịch.

Vì vậy:

- Ưu tiên expression thuần, chỉ đọc dữ liệu hoặc tính toán.
- Không đặt thanh toán, gửi email, ghi dữ liệu hay thay đổi trạng thái trong expression có thể được tự động chạy lại.
- Nếu expression có side effect và cần compiled mode, cân nhắc IMMEDIATE để lỗi được trả về caller, đồng thời thiết kế thao tác có tính idempotent và xử lý lỗi rõ ràng.
- Nếu không cần compiler, OFF là lựa chọn dễ dự đoán nhất.

## 6. ClassLoader và compiled expression

Compiled expression được tạo thành class Java trong một child ClassLoader. Nếu ứng dụng chỉ định classloader cho compiler, classloader đó phải nhìn thấy tất cả kiểu tham gia vào quá trình đánh giá expression.

Ví dụ:

~~~java
ClassLoader expressionClassLoader =
        MyApplication.class.getClassLoader();

SpelParserConfiguration configuration =
        SpelParserConfiguration.builder()
                .compilerMode(SpelCompilerMode.MIXED)
                .compilerClassLoader(expressionClassLoader)
                .build();
~~~

Lỗi class visibility có thể xuất hiện trong ứng dụng có plugin, module loader, application server hoặc classloader riêng cho từng thành phần.

Khi gặp lỗi chỉ xuất hiện ở compiled mode, hãy kiểm tra:

- Root object và các kiểu property mà expression truy cập.
- Kiểu đối số và kiểu trả về của method được gọi.
- Classloader có thể nhìn thấy các class liên quan không.
- Class có được nạp từ nhiều classloader khác nhau không.
- Kiểu runtime có ổn định qua các lần evaluate không.

Nếu không có lý do đặc biệt để chỉ định classloader, có thể để Spring dùng classloader mặc định. Với ứng dụng modular, hãy cấu hình classloader có thể truy cập toàn bộ kiểu liên quan tới expression.

## 7. Kiểm tra expression có compile được không

Nếu cần kiểm tra khả năng biên dịch trong test hoặc công cụ chẩn đoán, SpEL cung cấp API trên **SpelExpression**.

Có thể evaluate expression trước để thu thập thông tin kiểu, sau đó yêu cầu compile:

~~~java
SpelExpressionParser parser =
        new SpelExpressionParser();

SpelExpression expression = (SpelExpression)
        parser.parseExpression("payload.amount * 1.08");

Object firstResult = expression.getValue(message);

boolean compiled = expression.compileExpression();
~~~

compileExpression() trả về true nếu expression được biên dịch thành công và false nếu chưa thể biên dịch. Việc compile chỉ thành công khi các node đã có đủ thông tin kiểu cần thiết.

API này hữu ích trong kiểm thử hoặc chẩn đoán. Với ứng dụng thông thường, cấu hình SpelCompilerMode trên parser thường là cách quản lý compiler phù hợp hơn.

Nếu expression đã dùng compiled form và cần quay lại interpreter một cách tường minh, SpelExpression có method revertToInterpreted():

~~~java
expression.revertToInterpreted();
~~~

Thao tác này loại bỏ compiled form hiện tại và đưa expression về interpreted mode. Tùy compiler mode, SpEL có thể thử biên dịch lại sau đó.

Không nên dùng compileExpression() như một bước bắt buộc trước mọi lần getValue(). Compiler cần đủ thông tin runtime và một số expression vốn không thể biên dịch.

## 8. Tách expression để tránh giới hạn compiler

Nếu một expression lớn chứa cả phần có thể compile và phần không thể compile, có thể cân nhắc tách logic thành các bước nhỏ hơn.

Ví dụ ban đầu:

~~~text
#orders.?[total >= #minimumTotal].![total * #taxRate]
~~~

Expression này dùng selection và projection nên compiler không hỗ trợ.

Nếu kiến trúc cho phép, có thể thực hiện việc lọc collection trong Java rồi dùng một expression đơn giản để tính giá trị trên từng Order:

~~~text
total * #taxRate
~~~

Một lựa chọn khác là chuyển toàn bộ việc lọc và mapping sang Java Stream:

~~~java
List<BigDecimal> totals = orders.stream()
        .filter(order -> order.getTotal().compareTo(minimumTotal) >= 0)
        .map(order -> order.getTotal().multiply(taxRate))
        .toList();
~~~

Không nên tách expression chỉ để ép compiler hoạt động nếu kết quả làm logic khó đọc hoặc tạo thêm chi phí chuyển đổi dữ liệu. Hãy giữ SpEL cho phần biểu thức cấu hình ngắn và dùng Java cho logic collection phức tạp hoặc cần kiểm soát kiểu chặt chẽ.

## 9. Chẩn đoán khi expression không được compile hoặc fallback

Khi thấy hiệu năng không như mong đợi hoặc compiled evaluation phát sinh lỗi, hãy xác định trường hợp cụ thể.

### 9.1. Expression vẫn chạy nhưng không được biên dịch

Dấu hiệu:

- Expression evaluate thành công.
- Không có lỗi cú pháp hoặc lỗi runtime.
- Compiler không tạo được compiled form hoặc expression thuộc nhóm chưa hỗ trợ.

Cách xử lý:

1. Đối chiếu expression với danh sách giới hạn theo phiên bản Spring đang dùng.
2. Kiểm tra có assignment, selection, projection, bean reference, custom resolver hoặc conversion service không.
3. Chấp nhận interpreted mode nếu expression chỉ chạy thỉnh thoảng.
4. Nếu cần hiệu năng, chuyển phần xử lý không hỗ trợ sang Java hoặc viết lại thành expression đơn giản hơn khi phù hợp.

Đây không phải lỗi parse và cũng không phải lý do để thay đổi dữ liệu đầu vào.

### 9.2. Compiled expression thất bại trong IMMEDIATE

Dấu hiệu:

- Expression đã chạy ở interpreted mode.
- Sau khi compile, một lần evaluate với dữ liệu khác ném exception.
- Lỗi có thể liên quan tới kiểu property, method argument, class visibility hoặc runtime structure.

Cách xử lý:

1. Kiểm tra kiểu của root object và các property ở lần chạy thành công đầu tiên.
2. So sánh với kiểu ở lần chạy bị lỗi.
3. Kiểm tra classloader và các kiểu method liên quan.
4. Nếu kiểu thực sự thay đổi, dùng OFF hoặc MIXED tùy yêu cầu về side effect và lỗi.
5. Nếu kiểu cần ổn định, chuẩn hóa dữ liệu trước khi evaluate.

IMMEDIATE không tự chuyển sang interpreter khi compiled evaluation thất bại.

### 9.3. MIXED quay về interpreter

Dấu hiệu:

- Expression chạy được dù compiled evaluation từng thất bại.
- Hiệu năng có thể thay đổi giữa các lần evaluate.
- Expression có thể được compile lại sau đó hoặc cuối cùng ở lại interpreted mode.

Cách xử lý:

1. Xác định vì sao kiểu runtime thay đổi.
2. Kiểm tra expression có side effect hay không.
3. Nếu có side effect, đánh giá nguy cơ một phần expression bị chạy lại.
4. Nếu kiểu thay đổi là bình thường, cân nhắc OFF để tránh compile thất bại lặp lại.
5. Nếu kiểu đáng lẽ phải ổn định, sửa nguồn dữ liệu hoặc tách expression theo kiểu.

Không nên xem MIXED như một cơ chế bỏ qua exception tổng quát. Nó xử lý lỗi của compiled form bằng cách quay về interpreter; các lỗi nghiệp vụ khi diễn giải vẫn có thể được trả về.

## 10. Chọn mode theo đặc điểm expression

| Tình huống | Mode nên cân nhắc | Lý do |
| --- | --- | --- |
| Expression dùng selection/projection hoặc bean reference | OFF | Các dạng này không hỗ trợ compiler trong tài liệu hiện hành |
| Expression cần custom resolver hoặc ConversionService | OFF | Compiler không biên dịch được hành vi mở rộng đó |
| Expression có kiểu ổn định, không có side effect và cần hiệu năng | IMMEDIATE hoặc MIXED | Có thể hưởng lợi từ compiled form |
| Kiểu dữ liệu có thể thay đổi giữa các lần evaluate | OFF hoặc MIXED | OFF tránh compiled form; MIXED có cơ chế quay lại interpreter |
| Compiled failure phải được caller nhìn thấy | IMMEDIATE | Lỗi compiled evaluation được trả về trực tiếp |
| Expression có side effect và không thể chạy lại | OFF hoặc IMMEDIATE | Tránh tự động retry ngầm của MIXED |
| Expression chỉ được chạy vài lần | OFF | Chi phí compile có thể không mang lại lợi ích đáng kể |

Đây là định hướng lựa chọn, không phải quy tắc cứng. Hãy đo hiệu năng trên workload thực tế và kiểm tra đúng kiểu dữ liệu mà ứng dụng sử dụng.

## 11. Kiểm thử interpreted, compiled và fallback

Nên có test riêng cho các tình huống sau:

- Expression chạy ở OFF.
- Expression ổn định có thể compile.
- Expression thuộc nhóm không hỗ trợ compile nhưng vẫn chạy bằng interpreter.
- Kiểu runtime thay đổi sau khi compile.
- MIXED chuyển lại interpreter khi compiled form thất bại.
- IMMEDIATE trả lỗi khi compiled evaluation thất bại.
- Expression có side effect không bị chạy lại ngoài ý muốn.

Ví dụ kiểm tra expression thuộc nhóm selection:

~~~java
SpelExpressionParser parser =
        new SpelExpressionParser();

SpelExpression expression = (SpelExpression)
        parser.parseExpression("#orders.?[total > 100]");

StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("orders", orders);

Object result = expression.getValue(context);

// Selection được hỗ trợ ở interpreted mode.
// Trong Spring Framework hiện hành, selection không được compiler hỗ trợ.
boolean compiled = expression.compileExpression();
~~~

Trong test gắn với một phiên bản Spring cụ thể, có thể xác nhận compileExpression() trả false cho expression selection. Khi nâng phiên bản Spring, hãy kiểm tra lại giới hạn vì compiler có thể hỗ trợ thêm cú pháp mới.

Với expression có thể compile, nên chạy test bằng các object có kiểu ổn định và cả trường hợp kiểu thay đổi. Không chỉ kiểm tra một lần evaluate rồi kết luận compiled form an toàn cho toàn bộ vòng đời ứng dụng.

## 12. Lưu ý về hiệu năng

Compiler có thể cải thiện tốc độ của expression được đánh giá lặp lại nhiều lần, nhưng không phải lúc nào cũng nhanh hơn tổng thể.

Hãy cân nhắc:

1. **Tần suất evaluate:** expression chỉ chạy một lần có thể không đáng để compile.
2. **Chi phí compile:** compiler cần tạo class và thu thập thông tin kiểu.
3. **Tính ổn định của kiểu:** compiled form dựa trên kiểu đã quan sát được.
4. **Giới hạn cú pháp:** expression không hỗ trợ vẫn chạy bằng interpreter.
5. **Chi phí bên trong method:** nếu expression gọi một service hoặc truy vấn database, thời gian đó có thể lớn hơn chi phí interpreter.
6. **Classloader và bộ nhớ:** compiled expression tạo class trong child ClassLoader.
7. **Side effect:** MIXED có thể quay lại interpreter sau khi compiled expression đã chạy một phần.

Đo benchmark với cùng dữ liệu, số lần evaluate và EvaluationContext tương tự môi trường thật. Không nên bật compiler toàn cục chỉ dựa trên một microbenchmark đơn lẻ.

## 13. Ghi nhớ nhanh

- SpEL có interpreted mode và compiled mode.
- Compiler không bật mặc định; mode mặc định là OFF.
- Expression không hỗ trợ compile vẫn có thể chạy bình thường bằng interpreter.
- Các giới hạn hiện hành gồm assignment, ConversionService, custom resolvers, overloaded operators, một số thao tác Optional, array construction, selection/projection và bean references.
- Compiler suy luận kiểu từ các lần interpreted evaluation; kiểu thay đổi có thể làm compiled form thất bại.
- OFF luôn dùng interpreter.
- IMMEDIATE trả exception cho caller nếu compiled evaluation thất bại.
- MIXED bắt lỗi compiled evaluation và quay về interpreter; có thể thử compile lại sau đó.
- MIXED có nguy cơ thực hiện lại side effect nếu compiled expression đã chạy một phần trước khi thất bại.
- Cấu hình parser bằng SpelParserConfiguration hoặc property spring.expression.compiler.mode khi parser được quản lý bởi integration point khác.
- Classloader dùng cho compiler phải nhìn thấy mọi kiểu tham gia vào expression.
- Dùng compileExpression() để kiểm tra khả năng compile khi cần chẩn đoán; dùng revertToInterpreted() để bỏ compiled form.
- Đo hiệu năng thực tế trước khi chọn mode cho production.

## 14. Tài liệu tham khảo chính thức

- [Spring Framework — SpEL Compilation and Compiler Limitations](https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html)
- [SpelCompilerMode Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/SpelCompilerMode.html)
- [SpelParserConfiguration Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/SpelParserConfiguration.html)
- [SpelExpression Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/standard/SpelExpression.html)
