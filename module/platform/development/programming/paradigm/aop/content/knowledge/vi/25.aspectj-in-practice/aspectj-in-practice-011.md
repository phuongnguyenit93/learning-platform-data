# Phân biệt đặc tính riêng của AspectJ với khái niệm AOP tổng quát

## 1. Hai tầng kiến thức cần tách bạch

**Aspect-Oriented Programming (AOP)** là tư duy mô-đun hóa những **mối quan tâm cắt ngang** (cross-cutting concerns): một quy tắc như logging, kiểm soát truy cập, tracing, metrics hoặc kiểm tra điều kiện có thể áp dụng tại nhiều vị trí trong chương trình mà không phải lặp lại từng dòng trong mọi phương thức nghiệp vụ.

**AspectJ** là một công nghệ cụ thể trong hệ sinh thái Java để hiện thực tư duy ấy. Nó có ngôn ngữ pointcut, mô hình join point, cú pháp advice, công cụ biên dịch/weaving, các khai báo thay đổi cấu trúc kiểu và các quy tắc xác định thứ tự advice.

Hai phát biểu sau rất khác nhau:

- “AOP cho phép mô tả logic cắt ngang bằng aspect rồi áp dụng tại những join point phù hợp” — **khái niệm tổng quát**.
- “Một pointcut viết bằng execution(* Account.transfer(..)) và biên dịch cùng tệp .aj bằng ajc” — **mô tả một hiện thực AspectJ**.

Đừng lấy một cú pháp của AspectJ làm định nghĩa bắt buộc cho mọi hệ AOP. Ngược lại, cũng đừng phủ nhận khả năng có thật của AspectJ chỉ vì một mô hình AOP khác không hỗ trợ khả năng đó.

### Mục tiêu

Sau bài này, bạn sẽ:

1. Phân biệt aspect, join point, pointcut, advice và weaving ở mức trừu tượng.
2. Nhận biết các điểm cụ thể mà AspectJ hỗ trợ như method call, method execution, field get/set và cflow.
3. Hiểu vì sao execution và call có vị trí áp dụng khác nhau.
4. Phân biệt bản chất before/after/around với cú pháp và semantics của proceed trong AspectJ.
5. Hiểu compile-time, binary và load-time weaving không phải ba bước bắt buộc của mọi AOP.
6. Nhận diện inter-type declarations, declare parents, declare error/warning và declare precedence là các năng lực riêng của AspectJ.
7. Biên dịch một chương trình Java 17 và tệp AspectJ .aj, giải thích chính xác stdout.
8. Chuyển kiến thức sang một cơ chế AOP khác mà không áp đặt quy tắc của AspectJ lên nó.

## 2. Từ vựng AOP tổng quát và hiện thực AspectJ

| Thuật ngữ | Tầng khái niệm AOP | Biểu hiện trong AspectJ |
| --- | --- | --- |
| Concern | Mục tiêu/chính sách xuyên qua nhiều module | Logging, metrics, authorization được mô tả bằng aspect |
| Aspect | Đơn vị mô-đun hóa concern | Aspect code-style hoặc annotation-style được công cụ AspectJ hỗ trợ |
| Join point | Điểm chạy mà hệ AOP có thể quan sát/can thiệp | Tập điểm định nghĩa cụ thể: call, execution, get/set và những loại khác |
| Pointcut | Quy tắc lựa chọn join point | Ngôn ngữ execution(...), call(...), args(...), within(...), cflow(...) |
| Advice | Logic thực thi khi điểm phù hợp | before, after, after returning, after throwing, around |
| Continuation | Phần thực thi bên trong có thể được gọi từ around | Từ khóa proceed(...) trong code-style AspectJ |
| Weaving | Cách kết hợp aspect với chương trình | Công cụ ajc, dệt source/bytecode hoặc dệt khi load class |
| Context binding | Cách lấy tham số/kết quả/ngoại lệ/ngữ cảnh | args, this, target, thisJoinPoint, returning và throwing binding |
| Introduction | Bổ sung thành viên/quan hệ kiểu nếu mô hình cho phép | Inter-type declarations và declare parents |
| Precedence | Thứ tự các advice/aspect khi cùng khớp | Quy tắc precedence của AspectJ và declare precedence |
| Coverage | Những nơi concern thật sự chạy | Phụ thuộc pointcut, mã được woven và điều kiện runtime |

Khái niệm AOP không bắt buộc mọi thư viện hỗ trợ tất cả khả năng trong cột phải. Một thư viện chỉ chặn method call vẫn có thể áp dụng ý tưởng tách concern, dù nó không hỗ trợ get/set pointcut hay giới thiệu method mới.

## 3. Mối quan tâm cắt ngang là khái niệm, không phải cú pháp

Ví dụ một hệ nghiệp vụ Java:

~~~java
// Fragment Java minh họa, không phải chương trình độc lập.
Order placeOrder(Request request);
PaymentResult charge(Payment payment);
Inventory reserve(String sku, int quantity);
~~~

Cả ba operation đều có thể cần:

- Xác thực và phân quyền.
- Đo thời gian và ghi metric.
- Ghi trace/correlation ID.
- Logging ở điểm bắt đầu, kết thúc và lỗi.
- Giới hạn số lần retry hoặc quản lý timeout.

Nếu mã concern lặp lại trong từng method, chúng có thể làm khó bảo trì. AOP đề xuất mô tả concern ở một nơi và áp dụng theo quy tắc selection.

~~~text
                   Aspect: logging/tracing
                     |      |      |
                     v      v      v
placeOrder()       charge()     reserve()
       \              |           /
        \-------- business -------/
~~~

Tư duy này tồn tại độc lập với tệp .aj. Một giải pháp dùng decorator, interceptor, weaving hay code generation có thể cùng phục vụ việc tách concern, nhưng không mặc nhiên có tập join point hoặc semantics giống AspectJ.

**Giới hạn của AOP:** không phải logic nào cũng là concern cắt ngang. Tính giá bán, chuyển trạng thái đơn hàng hoặc duy trì bất biến của aggregate thường có vị trí tự nhiên trong domain model. Chuyển những việc đó thành advice chỉ vì công cụ làm được có thể tăng coupling ẩn và khiến luồng điều khiển khó đọc.

## 4. Join point: ý tưởng tổng quát, tập điểm do công nghệ quy định

**Join point** là một vị trí có thể nhận advice trong mô hình đang dùng. AOP tổng quát không quy định cố định “mọi join point đều là method execution” hay “mọi field write đều có thể bị chặn”.

AspectJ có mô hình join point giàu khả năng, bao gồm:

- Method execution: thực thi thân phương thức.
- Method call: điểm phát sinh lời gọi phương thức.
- Constructor call/execution và một số điểm khởi tạo.
- Field get và field set.
- Static initialization và một số join point liên quan khởi tạo đối tượng.
- Exception handler và một số điểm thực thi advice.

Những loại này thuộc **mô hình join point AspectJ**, không phải một danh sách bắt buộc cho tất cả hệ AOP.

### 4.1. Method execution khác method call

Hai pattern AspectJ:

~~~java
// Biểu thức pointcut, không phải mã Java độc lập.
execution(* AccountService.transfer(..))
call(* AccountService.transfer(..))
~~~

Execution nhắm tới **việc thực thi thân method transfer**. Call nhắm tới **vị trí phát lời gọi** đến method đó.

~~~text
CallerA ------ call site A -------+
                                 |
CallerB ------ call site B ------> AccountService.transfer()
                                 ^ method execution join point
~~~

Hệ quả quan trọng:

1. Execution advice cần phần thân method đích được weaving phù hợp.
2. Call advice cần những call site liên quan được weaving phù hợp.
3. Nếu có caller bên ngoài vùng weaving, call advice không nhất thiết quan sát caller đó, dù phần thân method đích đã được woven.
4. Một lời gọi nội bộ cùng object vẫn có thể kích hoạt execution advice được woven vào method, trong khi cơ chế chỉ intercept lời gọi qua một proxy có thể bỏ qua self-invocation.
5. Nếu gắn cả call advice và execution advice để đếm operation, có thể đếm hai lần một đường gọi nếu không định nghĩa đơn vị metric rõ.

Không thể chỉ nhìn tên method và kết luận hai pointcut tương đương. **Vị trí join point, phạm vi weaving, điều kiện động** cùng quyết định hành vi.

### 4.2. Field get/set không phổ quát

AspectJ cho phép lựa chọn field access:

~~~java
// Biểu thức pointcut AspectJ, không biên dịch độc lập bằng javac.
get(int Account.balance)
set(int Account.balance)
~~~

Một cơ chế AOP chỉ chặn method invocation không nhất thiết quan sát được field read/write. Vì vậy câu nói “AOP luôn chặn được thao tác đọc và ghi field” là sai.

Ngay cả khi AspectJ hỗ trợ get/set, một policy bảo mật không nên chỉ dựa vào giả định mọi cách truy cập dữ liệu đều đi qua field pointcut; vẫn phải kiểm tra weaving coverage, reflection và các ranh giới bên ngoài ứng dụng.

## 5. Pointcut: điều kiện chọn chung, biểu thức chọn là đặc thù

Ở tầng trừu tượng, pointcut là **một vị từ**: join point nào thỏa điều kiện sẽ nhận advice. Điều kiện có thể liên quan method signature, đối tượng, tham số, vị trí mã, annotation hoặc dynamic control flow, tùy cơ chế AOP.

AspectJ dùng một **ngôn ngữ pointcut cụ thể**. Chẳng hạn:

~~~java
// Code-style AspectJ trong tệp .aj.
pointcut moneyMovement():
    execution(* AccountService.transfer(..));

before(): moneyMovement() {
    System.out.println("Entering transfer");
}
~~~

Ký hiệu execution, dấu ba chấm, phép ghép &&, || và ! theo quy tắc của AspectJ. Không sao chép cú pháp này sang một bộ interceptor khác rồi tin rằng ý nghĩa giữ nguyên.

### 5.1. Các pointcut designator tiêu biểu

| Designator | Ý nghĩa minh họa | Đặc tính cần lưu ý |
| --- | --- | --- |
| execution(signature) | Method/constructor execution | Quan sát ở phía thực thi |
| call(signature) | Method/constructor call site | Quan sát ở phía caller |
| get(fieldPattern), set(fieldPattern) | Field read/write | Không phải mọi AOP đều hỗ trợ |
| within(typePattern) | Vùng mã được khai báo trong type phù hợp | Ràng buộc vị trí lexical |
| withincode(methodPattern) | Điểm nằm trong mã của method/constructor phù hợp | Khác với dynamic control flow |
| this, target | Đối tượng gắn với join point | Cần hiểu nghĩa riêng theo loại join point |
| args | Điều kiện/binding đối số | Liên quan runtime argument và kiểu |
| cflow, cflowbelow | Dynamic control flow của một pointcut khác | Không phải tính năng bắt buộc của mọi AOP |
| if | Điều kiện động theo ngữ cảnh | Có chi phí và hạn chế về cách sử dụng |
| @annotation, @within, @target | Lựa chọn theo annotation | Phụ thuộc target metadata và ranh giới tương ứng |

Các dòng bảng chỉ giới thiệu **nhóm cấu trúc**, không phải mọi tổ hợp đều hợp lệ trong mọi context. Khi dùng thật, tham khảo cú pháp và version AspectJ đang cài, nhất là cách binding tham số và áp dụng annotation.

### 5.2. Static matching và dynamic matching

Một pointcut có thể được phân tích một phần ở thời điểm weaving: tên kiểu, tên phương thức, chữ ký. Những điều kiện dựa trên đối tượng, đối số hoặc control flow có thể phải kiểm tra khi chạy.

Điều này ảnh hưởng hiệu năng và phạm vi:

- Điểm được chọn theo signature không có nghĩa mọi lần chạy đều thỏa điều kiện runtime.
- Dynamic test có thể làm advice không chạy ở một lần cụ thể dù bytecode đã woven.
- Đo lường overhead nên tách thời gian kiểm tra pointcut với logic trong advice khi phân tích hiệu năng.
- Khi kiểm thử quyền, cần biết có điểm enforcement chắc chắn cho mọi tình huống nhạy cảm; một điều kiện động sai có thể thành đường bypass.

## 6. Aspect là module khái niệm; cú pháp aspect của AspectJ là một lựa chọn

Ở mức AOP tổng quát, **aspect** là mô-đun chứa hành vi cắt ngang và các quy tắc áp dụng.

AspectJ code-style cho phép tệp .aj và khai báo:

~~~java
// Trace.aj: đoạn AspectJ code-style, chưa phải chương trình độc lập.
public aspect Trace {
    before(): execution(void Work.start()) {
        System.out.println("Before start");
    }
}
~~~

Từ khóa aspect và khai báo before với dấu hai chấm là cú pháp cụ thể, **không phải Java thuần** được javac biên dịch riêng như một class thông thường.

AspectJ còn có phong cách dùng annotation trong mã Java. Annotation-style vẫn cần cơ chế xử lý/weaving phù hợp; chỉ thêm một annotation lên class không có nghĩa JVM tự hiểu và chèn advice vào bytecode.

Ở mức khái niệm:

- Concern cần được mô-đun hóa.
- Điểm áp dụng concern phải được mô tả rõ.
- Phần thực thi phải có cơ chế nối vào join point.

Ở mức công nghệ: tệp .aj, ajc, những annotation của AspectJ, compiler/runtime jar và cấu hình weaving là những chi tiết **phải học cho AspectJ**.

## 7. Advice: before, after và around ở hai tầng

Trong AOP tổng quát, advice trả lời câu hỏi **logic cắt ngang chạy khi nào so với join point**. Nhưng mỗi ngôn ngữ AOP có kiểu advice, quy tắc tương tác với exception và cách binding dữ liệu khác nhau.

AspectJ code-style có:

~~~java
// Các mảnh advice AspectJ độc lập, không phải một chương trình đầy đủ.
before(): execution(void Work.open()) {
    System.out.println("Before");
}

after(): execution(void Work.close()) {
    System.out.println("After finally");
}

after() returning(int result): execution(int Work.count()) {
    System.out.println("Returned: " + result);
}

after() throwing(IllegalArgumentException error):
        execution(void Work.fail()) {
    System.out.println("Threw: " + error.getMessage());
}

String around(): execution(String Work.label(String)) {
    return proceed();
}
~~~

**Before** chạy trước phần join point tương ứng. Nếu advice itself ném exception, target có thể không được chạy; không được coi before là quan sát không có khả năng ảnh hưởng kết quả.

**After kiểu finally** chạy khi join point kết thúc theo đường bình thường hoặc do throw, trong phạm vi advice tương ứng. Nó không đồng nghĩa “nghiệp vụ thành công”.

**After returning** chạy khi join point trả về bình thường và có thể bind return value. Nếu target trả CompletableFuture pending, chỉ biết target đã trả đối tượng future bình thường; chưa biết tác vụ bên trong thành công.

**After throwing** chạy khi ngoại lệ thoát khỏi join point phù hợp với kiểu binding. Binding IllegalArgumentException không có nghĩa observer nhận mọi throwable.

**Around** có thể thực thi trước và sau phần bên trong, thay đổi kết quả, không tiếp tục phần bên trong hoặc tiếp tục nhiều lần có chủ đích.

Điểm tổng quát là **mẫu thời điểm thực thi**. Các cú pháp returning(...), throwing(...), kiểu của pointcut và quy tắc kết hợp là đặc thù AspectJ.

### Bảng chọn advice theo mục tiêu

| Mục tiêu | Advice/điểm can thiệp thường thích hợp | Lưu ý |
| --- | --- | --- |
| Ghi trước lúc chạy | Before | Logging lỗi có thể chặn target |
| Ghi khi kết thúc bất kể outcome | After/finally | Không mặc định log success |
| Đọc giá trị trả về đồng bộ | After returning | Return future không phải completion future |
| Ghi exception đồng bộ | After throwing | Throwable binding phải phù hợp |
| Cache và short-circuit | Around | Có thể bỏ qua phần thực thi bên trong |
| Retry có điều kiện | Around | Nguy cơ gọi target nhiều lần |
| Biến đổi argument/return | Around | Là thay đổi hợp đồng nghiệp vụ |
| Ghi trạng thái tác vụ async | Completion callback/hook của mô hình async | Không đủ chỉ dùng after returning của lời gọi tạo future |

## 8. Proceed: tính năng điều khiển mạnh nhưng không phổ quát về cú pháp

Trong AOP, around advice có thể **ủy quyền phần thực thi tiếp theo** cho chuỗi nội bộ. AspectJ code-style sử dụng proceed.

~~~java
// Mảnh code-style AspectJ, Work.decorate đã tồn tại.
String around(String input):
        execution(String Work.decorate(String)) && args(input) {
    System.out.println("around entry");
    String value = proceed(input);
    System.out.println("around exit");
    return value;
}
~~~

Proceed không nhất thiết gọi trực tiếp target và bỏ qua mọi advice khác. Nó đi tiếp **qua phần chuỗi bên trong** theo thứ tự precedence đã được xác lập.

### 8.1. Không gọi proceed

~~~java
// Mảnh AspectJ minh họa short-circuit.
String around(): execution(String Work.decorate(String)) {
    return "CACHE_VALUE";
}
~~~

Nếu advice được chạy mà không gọi proceed, phần phía trong không thực thi theo nhánh đó. Có thể hữu ích với cache hay deny, nhưng không phù hợp cho tracing thuần túy nếu target bắt buộc phải chạy.

### 8.2. Gọi proceed nhiều lần

~~~java
// Mảnh AspectJ minh họa retry;
// TransientFailure là một exception giả định do ứng dụng định nghĩa.
String around(): execution(String Work.decorate(String)) {
    try {
        return proceed();
    } catch (TransientFailure ex) {
        return proceed();
    }
}
~~~

Một lần proceed có thể gây side effect rồi throw. Proceed lần nữa có thể nhân đôi side effect; policy retry cần số attempt, ngân sách thời gian, idempotency và khả năng phân biệt kết quả không chắc chắn.

### 8.3. Truyền tham số mới

~~~java
// Mảnh AspectJ, thay thế around khác cho cùng Work.decorate.
String around(String input):
        execution(String Work.decorate(String)) && args(input) {
    String normalized = input.trim();
    return proceed(normalized);
}
~~~

Đây là khả năng thay đổi đầu vào. Nó không phải logging best effort và có thể ảnh hưởng xác thực, cache key, chữ ký, nullability hoặc hành vi domain. Cú pháp truyền đối số vào proceed thuộc về AspectJ code-style; một mô hình AOP khác có thể có invocation object, argument array hoặc callback khác.

**Phân biệt nguyên lý và cú pháp:** “around có thể tiếp tục” là ý tưởng rộng; proceed(...) với quy tắc binding chính xác là hiện thực cụ thể.

## 9. Weaving: concept chung, giai đoạn và công cụ cụ thể

Weaving là việc kết hợp định nghĩa aspect với các join point trong chương trình. Trong thực tế AOP có nhiều cơ chế chèn hành vi: compile-time transformation, load-time bytecode instrumentation, runtime interception, proxy hay decorator.

AspectJ cung cấp những hình thức phổ biến:

1. **Compile-time weaving:** ajc biên dịch nguồn và aspect rồi tạo bytecode được woven.
2. **Post-compile/binary weaving:** dệt vào class/jar đã biên dịch.
3. **Load-time weaving:** dùng cấu hình/agent và class loader thích hợp để dệt khi class được nạp.

Ba mục trên là **lựa chọn của AspectJ**, không phải ba giai đoạn bắt buộc mà mọi ứng dụng AOP phải trải qua.

~~~text
Source Java + AspectJ source
              |
              +--> ajc compile-time weaving
              |
Class/JAR ----+--> post-compile weaving
              |
Class loading +--> load-time weaving
              |
              v
Bytecode thực thi có advice tại join point phù hợp
~~~

Một tệp aspect tồn tại ở source tree **không chứng minh** advice đã được weave hay sẽ được kích hoạt. Cần xác nhận compiler/weaver, classpath/module path, cấu hình class loading, class/call site được instrument và pointcut match.

### Vì sao tự gọi nội bộ không có một đáp án chung?

Với AspectJ execution weaving vào thân method, một self-call phù hợp vẫn có thể chạy advice khi method đó được thực thi. Với một dạng interception chỉ chặn invocation đi qua object đại diện, self-call có thể không đi qua interceptor.

Do đó phát biểu “mọi AOP đều bỏ qua self-invocation” là sai; phát biểu “mọi AOP đều bắt self-invocation” cũng sai. Câu hỏi đúng là **đang chặn loại join point nào và mã nào được instrument**.

## 10. Inter-type declarations: điều nổi bật nhưng không phải bản chất bắt buộc của AOP

Tách concern bằng advice khác với bổ sung cấu trúc kiểu. AspectJ có **inter-type declaration (ITD)** cho phép đưa một số method/field hoặc quan hệ kiểu vào type được chọn theo những quy tắc của compiler/weaving.

Ví dụ hai fragment:

~~~java
// Customer.java — Java thuần
class Customer {
}
~~~

~~~java
// CustomerExtension.aj — AspectJ code-style
public aspect CustomerExtension {
    public String Customer.displayName() {
        return "anonymous";
    }
}
~~~

Trong build được weave phù hợp, phương thức displayName có thể được thêm vào Customer theo quy tắc của AspectJ. Điều này không có nghĩa một class Java viết riêng như trên đã tự có method nếu chỉ chạy javac.

Phân biệt rõ:

- **Advice:** áp dụng hành vi tại join point trong runtime.
- **ITD/introduction:** bổ sung thành viên hoặc quan hệ kiểu.
- **Decorator:** cung cấp một đối tượng bao quanh với interface được thiết kế, không nhất thiết thay type gốc.
- **Inheritance/composition:** kỹ thuật hướng đối tượng bình thường.

ITD có thể hữu ích khi muốn cung cấp một khả năng ngang nhiều kiểu, nhưng làm tăng coupling ẩn và khiến người đọc source class khó thấy toàn bộ API thực tế. Cần quản lý đụng tên method, binary compatibility, vòng đời phiên bản và khả năng debug.

### Declare parents

AspectJ cũng hỗ trợ những khai báo liên quan đến hierarchy, như declare parents, với điều kiện theo hệ kiểu và compiler. Đây là năng lực đặc thù AspectJ; một hệ AOP không có introductions vẫn có thể thực hiện đúng việc quan sát/intercept concern theo mục tiêu của nó.

## 11. Declare precedence, declare warning và declare error

Một khía cạnh riêng của AspectJ là nhóm **declare constructs** phục vụ quy tắc cấu trúc/kiến trúc và thứ tự aspect.

Ví dụ fragment minh họa:

~~~java
// Cú pháp AspectJ trong .aj, giả sử các aspect đã được định nghĩa.
declare precedence: SecurityPolicy, TracingPolicy, *;
~~~

Đây là cách biểu diễn một thứ tự aspect mong muốn. Vấn đề **thứ tự bảo mật trước telemetry** là quan tâm thiết kế tổng quát; câu lệnh declare precedence là ngôn ngữ AspectJ.

Một ví dụ khác:

~~~java
// Fragment trong AspectJ .aj, không phải Java thuần.
declare warning:
    call(* java.lang.System.exit(..)) :
    "Process termination calls should be reviewed";
~~~

Kiểu khai báo này có thể phát cảnh báo từ compiler/weaver cho những join point phù hợp nhằm kiểm tra quy tắc kiến trúc. Khả năng này **không phải** điều kiện để một thư viện được gọi là AOP.

- Declare warning/error giúp phát hiện loại vi phạm có thể mô tả bằng pointcut.
- Nó không thay thế toàn bộ static analyzer, linter hay kiểm thử bảo mật.
- Kết quả phụ thuộc những class/call site được phân tích và phiên bản công cụ.
- Nếu quy tắc về quyền phải được enforce ở runtime, chỉ tạo cảnh báo khi build không tự thay thế điểm chặn bắt buộc.

## 12. Ví dụ Java 17 + AspectJ chạy được để phân biệt hai tầng

Chương trình gồm **hai tệp**:

- Demo.java: Java 17 thông thường với các phương thức nghiệp vụ.
- SampleAspect.aj: tệp code-style của AspectJ dệt advice lên những method phù hợp.

Để thứ tự stdout minh bạch, chỉ một dạng around chọn method decorate, còn before/after chọn prepare, after returning chọn amount và after throwing chọn broken.

### 12.1. Tệp Demo.java

~~~java
import java.util.Locale;

final class Service {
    void prepare() {
        System.out.println("TARGET prepare");
    }

    int amount() {
        System.out.println("TARGET amount");
        return 12;
    }

    String decorate(String input) {
        System.out.println("TARGET decorate");
        return input.toUpperCase(Locale.ROOT);
    }

    void broken() {
        System.out.println("TARGET broken");
        throw new IllegalArgumentException("invalid");
    }
}

public class Demo {
    public static void main(String[] args) {
        Service service = new Service();
        service.prepare();
        System.out.println("CALLER amount=" + service.amount());
        System.out.println("CALLER decorate=" + service.decorate("aop"));

        try {
            service.broken();
        } catch (IllegalArgumentException error) {
            System.out.println("CALLER error=" + error.getMessage());
        }
    }
}
~~~

Tệp trên **chạy được bằng Java thuần**; nó không có khai báo aspect hay advice trong source.

### 12.2. Tệp SampleAspect.aj

~~~java
public aspect SampleAspect {
    before(): execution(void Service.prepare()) {
        System.out.println("BEFORE prepare");
    }

    after(): execution(void Service.prepare()) {
        System.out.println("AFTER prepare");
    }

    after() returning(int value): execution(int Service.amount()) {
        System.out.println("AFTER returning=" + value);
    }

    after() throwing(IllegalArgumentException error):
            execution(void Service.broken()) {
        System.out.println("AFTER throwing=" + error.getMessage());
    }

    String around(String input):
            execution(String Service.decorate(String)) && args(input) {
        System.out.println("AROUND enter=" + input);
        String result = proceed(input);
        System.out.println("AROUND exit=" + result);
        return result;
    }
}
~~~

Ở đây:

1. aspect và cú pháp .aj là ngôn ngữ code-style AspectJ.
2. execution(...) là pointcut designator của AspectJ.
3. before/after/around cụ thể hóa các mẫu advice chung.
4. returning và throwing binding là quy tắc liên kết dữ liệu của AspectJ.
5. proceed(input) đi tiếp qua phần thực thi bên trong around.
6. Method Service.decorate không chứa dòng nào về logging; output AROUND đến từ mã được weaving.

### 12.3. Biên dịch và chạy

Cần một JDK 17 và trình biên dịch AspectJ ajc phiên bản hỗ trợ Java 17, cùng runtime jar tương ứng. Giả sử ASPECTJ_HOME trỏ vào bộ cài có lib/aspectjrt.jar và lệnh ajc có trong PATH.

Trên Unix:

~~~bash
mkdir -p out
ajc -source 17 -target 17 -classpath "$ASPECTJ_HOME/lib/aspectjrt.jar" -d out Demo.java SampleAspect.aj
java -cp "out:$ASPECTJ_HOME/lib/aspectjrt.jar" Demo
~~~

Trên Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force -Path out | Out-Null
ajc -source 17 -target 17 -classpath "$env:ASPECTJ_HOME\lib\aspectjrt.jar" -d out Demo.java SampleAspect.aj
java -cp "out;$env:ASPECTJ_HOME\lib\aspectjrt.jar" Demo
~~~

Bộ cài khác nhau có thể đặt compiler/runtime jar ở vị trí khác hoặc gọi ajc thông qua một launcher khác. Điều kiện thực chất là bộ công cụ hỗ trợ Java 17 và classpath hợp lệ. Mã .aj không được javac biên dịch trực tiếp; ajc thực hiện compile-time weaving ở ví dụ này.

### 12.4. Stdout dự kiến khi weave thành công

~~~text
BEFORE prepare
TARGET prepare
AFTER prepare
TARGET amount
AFTER returning=12
CALLER amount=12
AROUND enter=aop
TARGET decorate
AROUND exit=AOP
CALLER decorate=AOP
TARGET broken
AFTER throwing=invalid
CALLER error=invalid
~~~

Giải thích:

- prepare: before chạy trước thân method; after kiểu finally chạy sau khi thân method trả bình thường.
- amount: method in rồi trả 12; after returning nhận 12 trước khi biểu thức println ở caller sử dụng giá trị trả về.
- decorate: around in khi vào, gọi proceed, method gốc in rồi trả AOP, around in khi thoát và caller nhận AOP.
- broken: thân method in rồi ném IllegalArgumentException; after throwing nhận lỗi tương thích, rồi caller bắt lỗi.

Dù có một before và một after ở prepare, thứ tự trước/thân/sau vẫn dễ xác định; ví dụ không có nhiều around cạnh tranh trên cùng join point.

### 12.5. Chạy Java thuần để đối chiếu

Biên dịch riêng Demo.java vào một thư mục khác, không dùng aspect:

~~~bash
mkdir -p plain
javac -d plain Demo.java
java -cp plain Demo
~~~

Stdout nếu không có cơ chế weaving nào khác:

~~~text
TARGET prepare
TARGET amount
CALLER amount=12
TARGET decorate
CALLER decorate=AOP
TARGET broken
CALLER error=invalid
~~~

So với bản ajc:

- Các dòng TARGET/CALLER do Java code tạo ra.
- Các dòng BEFORE/AFTER/AROUND do aspect tạo ra qua weaving.
- Không có weaving thì cùng code Java chạy không có advice.
- AOP là ý tưởng tổ chức concern; **AspectJ cung cấp cơ chế cụ thể biến ý tưởng thành hành vi**.

## 13. Vì sao ví dụ này không chứng minh mọi tính năng AOP trên thế giới?

Ví dụ minh họa một tập pointcut và advice cụ thể do AspectJ hỗ trợ. Nó **không chứng minh**:

- Mọi cơ chế AOP đều có join point field access.
- Mọi cơ chế đều chặn self-invocation giống nhau.
- Mọi cơ chế dùng compiler ajc hoặc tệp .aj.
- Mọi hệ đều cho phép sửa hệ thống kiểu bằng ITD.
- Mọi advice trong mọi công nghệ sẽ sắp theo cùng một quy tắc precedence.
- Một method trả future là đã hoàn tất tác vụ bên trong.
- Một aspect có mặt trong source tree luôn được kích hoạt.

Muốn đánh giá một công nghệ AOP khác, hãy giữ cách đặt câu hỏi theo concern/join point/pointcut/advice/continuation/ordering và xác minh khả năng thực tế của nó.

## 14. Một thí nghiệm phân biệt call với execution

Khi đã chạy ví dụ chính, hãy thử tạo aspect riêng quan sát một method theo hai điểm:

~~~java
// Hai mảnh pointcut/advice của AspectJ; chưa phải chương trình độc lập.
before(): call(String Service.decorate(String)) {
    System.out.println("AT CALL SITE");
}

before(): execution(String Service.decorate(String)) {
    System.out.println("AT METHOD EXECUTION");
}
~~~

Trong trường hợp caller chứa call site và thân method đều đã được woven, một lời gọi có thể đi qua cả hai dạng advice. Nhưng số lượng event còn tùy phạm vi instrumentation và số caller. Không kết luận “mọi lời gọi đều in hai dòng” khi chưa xác định đầy đủ build và loader.

**Đây là cách kiểm chứng một đặc tính của AspectJ:** call-side với execution-side có thể khác nhau. **Đây không phải yêu cầu của mọi hiện thực AOP.**

### Self-invocation

~~~java
// Fragment Java, chưa phải ví dụ biên dịch độc lập.
class Task {
    void run() {
        sensitive();
    }

    void sensitive() {
        updateData();
    }
}
~~~

Nếu phần thân sensitive được woven với execution pointcut tương ứng, việc gọi từ run trên cùng object vẫn có thể được advice quan sát. Nếu chỉ có proxy-based call interception tại một ranh giới bên ngoài, self-call có thể không đi qua proxy. Không áp một nhận xét từ cơ chế này lên tất cả cơ chế khác.

## 15. Độ ưu tiên giữa nhiều aspect là một vấn đề thiết kế thực

Giả sử authentication, authorization, retry, transaction và metrics cùng áp dụng một operation.

~~~text
Authorization
  -> Retry
      -> Metrics
          -> Business logic
      <- Metrics
  <- Retry
<- Authorization
~~~

Sơ đồ chỉ là thứ tự giả định phục vụ phân tích:

- Metrics bên trong retry đo từng attempt.
- Metrics bên ngoài retry đo toàn operation.
- Authorization nằm ngoài retry có thể được đánh giá một lần; bên trong retry có thể được đánh giá lại theo mỗi attempt.
- Một around không gọi proceed có thể khiến advice phía trong không được thực thi.
- Ghi audit trong after finally có thể phát sinh cả khi target thất bại; thứ tự và failure policy quan trọng.

**Precedence/ordering là câu hỏi tổng quát.** Declare precedence và quy tắc advice của AspectJ là cách một công nghệ cụ thể giải quyết câu hỏi ấy. Khi correctness phụ thuộc thứ tự, phải kiểm tra/thiết kế thứ tự tường minh thay vì tin rằng thứ tự các file được biên dịch quyết định hành vi.

## 16. Lỗi instrumentation và ngoại lệ: nguyên tắc chung cho mọi AOP

Nếu một before advice ghi log mà logger ném exception, target có thể không chạy. Nếu after finally ghi log lỗi, caller có thể nhìn thấy lỗi logging thay cho return hay exception nghiệp vụ. Around có thể vô tình gọi proceed hai lần hoặc bỏ qua proceed.

Ví dụ anti-pattern:

~~~java
// Fragment AspectJ, giả sử logger và Work.process tồn tại.
after(): execution(* Work.process(..)) {
    logger.write("finished");
}
~~~

Nếu logger ném lỗi, hành vi nghiệp vụ có thể bị thay đổi. Cách xử lý tùy **chính sách**:

- Telemetry/logging best effort nên cô lập lỗi có thể xử lý.
- Audit bắt buộc phải được thiết kế ở ranh giới cam kết/bền vững phù hợp, không để một lỗi sau commit biến operation thành thất bại giả.
- Authorization từ chối sớm là thay đổi control flow có chủ đích, cần kiểm thử.
- Retry chỉ hợp lệ khi có số attempt/timeout/idempotency.
- Cancellation của future không bảo đảm task đã dừng; after returning của method không đồng nghĩa success end-to-end.

Tất cả đều là các nguyên tắc lập trình đúng đắn vượt quá cú pháp .aj.

## 17. Bất đồng bộ: join point đồng bộ không tự thấy completion

Giả sử một method Java trả CompletableFuture đang pending:

~~~java
// Fragment Java; pending được cung cấp từ ngữ cảnh xung quanh.
CompletableFuture<String> loadAsync() {
    return pending;
}
~~~

After returning trên execution của loadAsync chạy lúc method trả đối tượng future. Nó không tự chờ kết quả được tính sau đó. After throwing trên method cũng không tự nhận lỗi xảy ra trong worker lúc khác.

Để quan sát completion, có thể dùng API của mô hình bất đồng bộ:

~~~java
// Fragment Java, stage và recordOutcome đã được định nghĩa.
CompletionStage<String> monitored = stage.whenComplete(
        (value, failure) -> recordOutcome(value, failure));
~~~

Lưu ý:

1. whenComplete tạo dependent stage; callback observer ném lỗi có thể làm dependent stage thất bại khi source thành công.
2. Completion callback có thể chạy ngay khi gắn nếu source đã hoàn tất hoặc chạy trên luồng làm source hoàn tất.
3. Context theo ThreadLocal không tự động truyền qua mọi callback/executor.
4. Timeout của future không chứng minh tác vụ đã bị dừng; side effect có thể tới muộn.
5. Muốn logging best effort, callback observer phải cô lập lỗi logging theo policy.

AOP có thể giúp gắn concern vào chỗ phù hợp, nhưng **ngữ nghĩa vòng đời async thuộc mô hình thực thi**, không thể suy ra chỉ từ nhãn advice after.

## 18. Checklist chuyển kiến thức sang một hệ AOP khác

Trước khi áp dụng một điều học từ AspectJ cho một công nghệ khác, hãy kiểm tra:

1. Concern cần tách là gì? Nó thật sự cross-cutting hay là domain invariant?
2. Join point được hỗ trợ: method call, method execution, constructor, field, callback hay tập khác?
3. Pointcut/selection được diễn đạt bằng cú pháp, annotation, interceptor registration hay code generation?
4. Advice có before, after finally, returning, throwing, around không; semantics riêng là gì?
5. Cơ chế continuation là proceed, invocation object hay callback?
6. Có thể short-circuit hoặc gọi phần bên trong nhiều lần không? Hợp đồng return/exception ra sao?
7. Advice được gắn ở compile-time, load-time hay runtime? Mã nào thực sự được instrument?
8. Self-invocation, direct call, reflection, overload và class loader mới ảnh hưởng coverage thế nào?
9. Thứ tự nhiều advice được quyết định ra sao?
10. Có introductions/ITD hoặc thay đổi cấu trúc type không? Có thật sự cần dùng?
11. Lỗi do logging/metrics có thể che lỗi nghiệp vụ không?
12. Method trả future có cần hook completion riêng để quan sát outcome không?
13. Cần những integration test nào để chứng minh pointcut match và target chạy đúng số lần?

Chỉ sau khi trả lời những câu hỏi này mới có thể dịch một ví dụ AspectJ sang công nghệ khác mà không sai ngữ nghĩa.

## 19. Những ngộ nhận thường gặp

**“AOP chính là AspectJ.”** Sai: AspectJ là một hiện thực của tư duy AOP.

**“Có từ khóa execution là có AOP.”** Sai: đây là cú pháp selection cụ thể của AspectJ, không phải chuẩn chung.

**“Mọi AOP chặn được get/set field.”** Sai: tập join point khác nhau.

**“AspectJ chỉ quan sát method call.”** Sai: có method execution và nhiều loại khác.

**“Bất cứ code Java nào cũng tự kích hoạt .aj.”** Sai: cần compile/weaving/runtime phù hợp.

**“Proceed luôn gọi target đúng một lần.”** Sai: around kiểm soát việc có proceed và số lần gọi; có thể đi qua advice khác.

**“AOP bắt buộc compile-time weaving.”** Sai: cả ý tưởng AOP lẫn công nghệ AspectJ đều không bị giới hạn chỉ một thời điểm dệt.

**“Mọi framework AOP đều có inter-type declarations.”** Sai: ITD là khả năng không phổ quát.

**“After returning chứng minh tác vụ async đã hoàn tất.”** Sai: chỉ method trả về bình thường.

**“Nếu advice không chạy thì chắc vì pointcut sai.”** Chưa đủ: còn có khả năng bytecode/call site không được woven hoặc class loader không dùng đúng artifact.

**“Nếu advice chạy thì contract nghiệp vụ không thể bị đổi.”** Sai: around, lỗi logger, exception transformation và retry đều có thể đổi kết quả.

## 20. Bài tập tự đánh giá

**Câu 1.** AOP là tư duy hay một tệp mã nguồn cụ thể?

**Đáp án:** AOP là tư duy/mô hình hóa concern cắt ngang tại join point. Tệp .aj là một cách hiện thực bằng AspectJ.

**Câu 2.** Vì sao call và execution trong AspectJ không nên bị hiểu là cùng một join point?

**Đáp án:** Call quan sát call site; execution quan sát phần thân method được thực thi. Phạm vi weaving và nhiều caller có thể tạo coverage khác nhau.

**Câu 3.** Nếu một thư viện AOP chỉ hỗ trợ interceptor quanh method, nó có phải “không phải AOP” vì thiếu get/set không?

**Đáp án:** Không. Một mô hình có tập join point hẹp hơn vẫn có thể mô-đun hóa concern xuyên suốt.

**Câu 4.** Around advice không gọi proceed sẽ có tác dụng gì?

**Đáp án:** Nó có thể short-circuit phần thực thi bên trong và trả kết quả thay thế. Đó là hành vi cần được chính sách cho phép, nhất là khi target có side effect.

**Câu 5.** Inter-type declaration có phải đặc điểm bắt buộc của mọi AOP không?

**Đáp án:** Không. Đây là một khả năng mở rộng kiểu mà AspectJ hỗ trợ; không phải mọi hệ AOP có.

**Câu 6.** Một aspect tồn tại nhưng không có log. Kiểm tra những gì?

**Đáp án:** Compiler/weaver có chạy, class/call site đã woven chưa, pointcut có match không, điều kiện runtime có thỏa không, class loader và phiên bản runtime có đúng không.

**Câu 7.** Vì sao after returning của một method trả CompletableFuture chưa cho biết operation thành công?

**Đáp án:** Future có thể chưa hoàn tất hoặc hoàn tất exceptional ở thời điểm khác; phải quan sát completion channel.

**Câu 8.** Declare precedence là điều gì?

**Đáp án:** Một cách của AspectJ để mô tả ưu tiên giữa các aspect. Bài toán thứ tự advice là tổng quát, nhưng cú pháp đó không phổ quát.

**Câu 9.** Làm sao minh họa rõ sự khác nhau giữa Java thuần và AspectJ weaving?

**Đáp án:** Biên dịch Demo.java bằng javac để quan sát dòng TARGET/CALLER, rồi dệt thêm SampleAspect.aj bằng ajc để quan sát các dòng BEFORE/AFTER/AROUND tương ứng.

**Câu 10.** Điều gì nên mang theo khi học một công nghệ AOP khác?

**Đáp án:** Concern, join point, selection/pointcut, advice semantics, continuation, weaving/interception, precedence, coverage, error/side-effect policy và phương pháp kiểm thử; cú pháp cụ thể phải học lại theo công nghệ đó.

## Kết luận

**AOP cung cấp bộ khái niệm để tổ chức logic cắt ngang; AspectJ cung cấp một mô hình và bộ công cụ Java cụ thể để triển khai những khái niệm đó.** Method call/execution, get/set, cflow, tệp .aj, compiler ajc, inter-type declaration và declare constructs là những tính năng quan trọng khi học AspectJ nhưng không thể coi là luật chung của mọi AOP. Điều nên giữ lại khi chuyển công nghệ là tư duy xác định concern, điểm can thiệp, thứ tự thực thi, phạm vi bao phủ, kết quả/ngoại lệ và các kiểm thử xác nhận hành vi thực tế.