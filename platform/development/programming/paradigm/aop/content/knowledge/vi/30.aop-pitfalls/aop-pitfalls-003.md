# Advice làm thay đổi kết quả hoặc nuốt lỗi ngoài dự kiến

## 1. Vấn đề: kết quả nghiệp vụ bị thay đổi khi đi qua aspect

Trong lập trình hướng khía cạnh (Aspect-Oriented Programming, AOP), **advice** là hành vi chạy tại hoặc xung quanh một **join point** đã được chọn bằng **pointcut**. Advice thường phục vụ logging, đo thời gian, kiểm tra quyền, audit, retry hoặc chuẩn hóa lỗi. Những mối quan tâm đó có thể ảnh hưởng rất lớn đến lời gọi nghiệp vụ dù mã của phương thức đích không thay đổi.

Một sai lầm khó phát hiện là advice **vô tình làm đổi giá trị trả về** hoặc **bắt lỗi rồi trả kết quả thành công giả**. Chẳng hạn:

- Phương thức đích trả mã xác nhận CONFIRMED:A-1, nhưng advice around luôn trả OK.
- Phương thức đích ném IllegalArgumentException vì thiếu đầu vào, nhưng advice catch rồi trả OK; caller tưởng thao tác thành công.
- Advice trả null trong khi caller mong đợi một kiểu nguyên thủy hoặc một giá trị bắt buộc khác null.
- Advice chuyển ngoại lệ thành một ngoại lệ chung và làm mất cause, khiến hệ thống phía ngoài không còn phân biệt được lỗi kiểm tra dữ liệu, lỗi tạm thời và lỗi nghiêm trọng.
- Advice ném lỗi trong phần ghi log hoặc cleanup, làm che mất exception gốc của target.

**Mục tiêu bài học:** nhận diện chính xác nơi hợp đồng bị thay đổi, hiểu cách advice điều khiển continuation, tái hiện lỗi bằng Java 17+, thiết kế chính sách xử lý lỗi có chủ đích, và viết kiểm thử bảo vệ cả giá trị lẫn ngoại lệ, tác dụng phụ, số lần gọi.

**Phạm vi:** các nguyên lý AOP cơ bản và nâng cao áp dụng cho nhiều mô hình proxy hoặc weaving. Ví dụ dùng JDK dynamic proxy để nhìn thấy rõ đường điều khiển; không đồng nhất nó với mọi công cụ AOP.

## 2. Hợp đồng quan sát được của một lời gọi

Khi đánh giá advice đúng hay sai, đừng chỉ hỏi “chương trình có chạy được không?”. Trước tiên phải định nghĩa **hợp đồng của join point** từ góc nhìn caller:

1. **Điều kiện đầu vào:** kiểu dữ liệu, giá trị được chấp nhận, kiểm tra quyền và trạng thái ban đầu.
2. **Giá trị trả về:** kiểu và ngữ nghĩa của kết quả, nullability, danh tính đối tượng và dữ liệu bắt buộc.
3. **Ngoại lệ:** loại lỗi được công bố, thông điệp/cause cần giữ, trường hợp nào caller phải nhìn thấy lỗi.
4. **Tác dụng phụ:** ghi dữ liệu, gửi thông báo, tiêu thụ hàng đợi, thực hiện một lần hay có thể lặp.
5. **Điều khiển luồng:** phương thức đích chạy bao nhiêu lần; advice có được bỏ qua hoặc gọi lại target không?
6. **Đặc tính phi chức năng:** tracing, thời gian, audit và yêu cầu nhất quán khi có nhiều lời gọi song song.

Một advice **trong suốt về nghiệp vụ** (business-transparent) phải bảo toàn các mục mà chính sách của nó không được phép đổi: giá trị thành công, ngoại lệ, số lần thực thi và tác dụng phụ. Advice logging điển hình nên quan sát rồi truyền tiếp kết quả hoặc lỗi. Ngược lại, một aspect *cố ý* retry, cache, authorization, fallback hoặc chuyển đổi exception có thể làm thay đổi hành vi; nhưng thay đổi đó phải được mô tả thành hợp đồng, không được xảy ra ngầm.

| Kết quả của target | Advice được thiết kế chỉ để ghi log | Triệu chứng advice sai |
| --- | --- | --- |
| Trả object X | Ghi sự kiện rồi trả đúng X | Trả giá trị khác, mất metadata hoặc đổi identity |
| Trả null hợp lệ | Giữ nguyên null | Thay null bằng đối tượng giả hoặc ném lỗi ngoài quy định |
| Ném ngoại lệ E | Ghi lỗi rồi ném lại E | Nuốt E và trả OK |
| Ném E có cause | Giữ E/cause, hoặc wrap đúng chính sách | Tạo lỗi mới không kèm cause |
| Tạo đúng một side effect | Không tự ý kích hoạt target thêm lần nữa | Gọi proceed hai lần dẫn đến ghi dữ liệu trùng |

Một số hệ AOP có advice loại after-returning hoặc around cho phép tác động đến kết quả với mức độ khác nhau. Khả năng thực tế phụ thuộc công cụ. **Đừng suy diễn rằng mọi advice có cùng quyền đổi return hoặc exception**; khi cần thay kết quả, phải kiểm tra semantics của kiểu advice và engine đang dùng.

## 3. Vì sao around advice dễ làm thay đổi hợp đồng nhất?

Với around advice, phần tiếp tục thực thi thường được biểu diễn bằng một hành động như proceed/continuation. Mô hình khái niệm:

~~~text
caller
  |
  v
around advice
  |-- mã trước proceed
  |-- proceed() --------> advice bên trong / target
  |                         |
  |                         +--> value hoặc Throwable
  |-- mã sau proceed / catch / finally
  |
  +--> return hoặc throw ------------> caller
~~~

Điểm quan trọng: **giá trị đi ra ngoài advice là giá trị advice return**, không tự động là giá trị target return. Ngoại lệ target sẽ không đến caller nếu advice catch rồi kết thúc bình thường. Có bốn lựa chọn điều khiển căn bản:

- **Không gọi proceed:** target không thực thi; có thể hợp lệ cho authorization từ chối hoặc cache hit.
- **Gọi proceed một lần:** thông thường phù hợp logging/timing; nhưng vẫn có thể thay đổi return hoặc exception.
- **Gọi proceed nhiều lần:** thực hiện lại phần còn lại của chain; có thể phù hợp retry nhưng rủi ro tác dụng phụ trùng.
- **Gọi proceed rồi tạo giá trị/ngoại lệ khác:** hoàn toàn có thể là chủ đích (fallback/translation), nhưng phá tính trong suốt nếu không nằm trong hợp đồng.

### 3.1. Ba lỗi chỉ khác một vài dòng

Ví dụ rút gọn theo ký hiệu quanh continuation; đây là **đoạn minh họa**, không phải chương trình độc lập:

~~~java
// Sai: bỏ kết quả thật rồi thay bằng một hằng số.
Object rewrite(Proceed next) throws Throwable {
    next.call();
    return "OK";
}

// Sai: che lỗi kiểm tra dữ liệu bằng kết quả thành công giả.
Object swallow(Proceed next) throws Throwable {
    try {
        return next.call();
    } catch (IllegalArgumentException failure) {
        return "OK";
    }
}

// Đúng với chính sách quan sát: bảo toàn kết quả/lỗi.
Object transparent(Proceed next) throws Throwable {
    try {
        Object result = next.call();
        logSuccess();
        return result;
    } catch (Throwable failure) {
        logFailure(failure);
        throw failure;
    }
}
~~~

Trong đoạn cuối, logSuccess/logFailure chỉ là **hàm giả định**, chưa có định nghĩa. Dù logic xử lý kết quả đã đúng hướng, mã thực tế vẫn phải xem xét lỗi của chính hệ logging, nếu không một lỗi ghi log có thể thay lỗi nghiệp vụ. Chương trình hoàn chỉnh ở mục 5 dùng System.out để minh họa và có lệnh chạy cụ thể.

### 3.2. Return trong finally có thể ghi đè cả return và throw

Java cho phép return trong finally, nhưng đây thường là bẫy nghiêm trọng:

~~~java
Object dangerous(Proceed next) throws Throwable {
    try {
        return next.call();
    } finally {
        return "OK"; // Ghi đè kết quả hoặc cả ngoại lệ đang truyền ra.
    }
}
~~~

Đây là đoạn minh họa sử dụng interface Proceed ở mục 5. Dù next.call() trả bất kỳ giá trị nào hoặc ném ngoại lệ, finally có return sẽ khiến phương thức kết thúc bằng "OK" (trừ tình huống đặc biệt như JVM dừng bất thường). Một trường hợp tương tự là **ném ngoại lệ mới trong finally**, làm che kết quả/lỗi đang xảy ra.

Việc cố viết một advice “luôn trả kết quả tốt” thường tạo **thành công giả**: thao tác nghiệp vụ thực sự thất bại nhưng caller không còn thông tin để rollback, báo lỗi hoặc thử lại đúng cách.

## 4. Các kịch bản đổi giá trị trả về sai

### 4.1. Bỏ kết quả của proceed

Sai sót rõ nhất là gọi proceed để target chạy nhưng bỏ giá trị trả về rồi return một giá trị mặc định. Khi caller dùng String, lỗi có thể khó nhận ra vì cả "OK" và "CONFIRMED:A-1" đều hợp lệ về kiểu. Khi caller dùng Boolean hay mã trạng thái, kết quả sai có thể làm thay đổi quyết định nghiệp vụ.

**Dấu hiệu:** log bên trong target ghi đúng return nhưng caller nhận dữ liệu khác; debugger dừng tại target cho thấy giá trị khác giá trị cuối cùng.

**Cách tìm:** log hoặc assert giá trị ngay trước return của target, sau proceed của từng advice và ngay tại caller; đừng chỉ đọc một đầu của đường gọi.

### 4.2. Ép kiểu và null không hợp đồng

Advice có thể trả một đối tượng không tương thích với kiểu phương thức. Với proxy hoặc mã generated, caller có thể gặp ClassCastException khi kết quả được cast, hoặc NullPointerException khi unboxing null thành kiểu nguyên thủy. **Vị trí stack trace** có thể nằm ở lớp proxy/caller, nhưng nguyên nhân là advice đã trả giá trị không phù hợp.

Ví dụ minh họa không độc lập:

~~~java
// Giả sử join point thật công bố trả về int.
Object wrongResult(Proceed next) {
    return null; // Rủi ro unboxing null hoặc vi phạm hợp đồng non-null.
}
~~~

Không nên “khắc phục” bằng cách bọc mọi return thành String. Hãy bảo toàn kiểu và ngữ nghĩa của phương thức đích. Nếu thật sự đổi kiểu public API, đó là thay đổi hợp đồng ở cấp API, không phải một chính sách advice bí mật.

### 4.3. Thay đổi đối tượng trả về

Advice có thể clone, wrap, cache hoặc chỉnh sửa đối tượng được trả về. Caller có thể phụ thuộc vào identity, tính bất biến, version field hoặc metadata mà việc thay đối tượng làm mất. Ngay cả khi toString() cho kết quả giống nhau, phép so sánh identity hay vòng đời resource có thể đã khác.

**Câu hỏi chẩn đoán:** advice chỉ quan sát kết quả hay có nhiệm vụ biến đổi dữ liệu? Nếu không có yêu cầu biến đổi, tránh mutate và trả lại chính object từ proceed.

### 4.4. Giá trị trả về của lời gọi bất đồng bộ

Một phương thức trả CompletionStage, Future hoặc một đối tượng biểu diễn kết quả trì hoãn có hai thời điểm riêng: **trả handle** và **hoàn tất phép xử lý bên trong**. Advice around chỉ bao quanh thời điểm trả handle có thể chưa biết thành công/thất bại cuối cùng.

Nếu advice catch quanh proceed nhưng lỗi xuất hiện sau đó khi future hoàn tất, catch này không bắt được lỗi đó. Tương tự, biến một CompletionStage thành một String trả trực tiếp có thể phá kiểu và semantics. Muốn chuyển đổi lỗi async phải làm theo hợp đồng của abstraction và bảo toàn cancellation, completion, propagation và ngữ cảnh thực thi.

## 5. MRE Java 17+: đối chiếu advice sai và advice bảo toàn hợp đồng

Đây là chương trình độc lập, chạy không cần thư viện ngoài JDK. Nó tách target CheckoutImpl, hợp đồng advice, lớp proxy và hàm quan sát để thấy **giá trị thật, giá trị bị thay và ngoại lệ bị nuốt**.

**Lưu mã nguyên vẹn trong tệp AdviceOutcomeDemo.java:**

~~~java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Proxy;

public class AdviceOutcomeDemo {
    interface Checkout { String confirm(String id); }

    static final class CheckoutImpl implements Checkout {
        @Override public String confirm(String id) {
            if (id.isBlank()) throw new IllegalArgumentException("missing id");
            return "CONFIRMED:" + id;
        }
    }
    @FunctionalInterface interface Proceed { Object call() throws Throwable; }
    @FunctionalInterface interface Advice { Object around(Proceed next) throws Throwable; }
    static Checkout wrap(Checkout target, Advice advice) {
        return (Checkout) Proxy.newProxyInstance(
            Checkout.class.getClassLoader(), new Class<?>[] {Checkout.class},
            (proxy, method, args) -> advice.around(() -> {
                try { return method.invoke(target, args); }
                catch (InvocationTargetException wrapper) { throw wrapper.getCause(); }
            }));
    }
    static void observe(String label, Checkout service, String id) {
        try { System.out.println(label + " -> " + service.confirm(id)); }
        catch (IllegalArgumentException failure) {
            System.out.println(label + " -> ERROR:" + failure.getMessage());
        }
    }
    public static void main(String[] args) {
        Advice rewrite = next -> { next.call(); return "OK"; };
        Advice swallow = next -> {
            try { return next.call(); }
            catch (IllegalArgumentException failure) { return "OK"; }
        };
        Advice transparent = next -> {
            try {
                Object value = next.call();
                System.out.println("AUDIT success");
                return value;
            } catch (Throwable failure) {
                System.out.println("AUDIT error=" +
                        failure.getClass().getSimpleName());
                throw failure;
            }
        };
        observe("plain-valid", new CheckoutImpl(), "A-1");
        observe("rewrite-valid", wrap(new CheckoutImpl(), rewrite), "A-1");
        observe("plain-invalid", new CheckoutImpl(), "");
        observe("swallow-invalid", wrap(new CheckoutImpl(), swallow), "");
        observe("safe-valid", wrap(new CheckoutImpl(), transparent), "A-1");
        observe("safe-invalid", wrap(new CheckoutImpl(), transparent), "");
    }
}
~~~

Lệnh chạy bằng JDK 17 trở lên, trong thư mục chứa file:

~~~bash
javac AdviceOutcomeDemo.java
java AdviceOutcomeDemo
~~~

**Stdout đã kiểm chứng bằng cách biên dịch/chạy trên JDK 21:**

~~~text
plain-valid -> CONFIRMED:A-1
rewrite-valid -> OK
plain-invalid -> ERROR:missing id
swallow-invalid -> OK
AUDIT success
safe-valid -> CONFIRMED:A-1
AUDIT error=IllegalArgumentException
safe-invalid -> ERROR:missing id
~~~

**Giải thích từng quan sát:**

- Với **plain-valid**, target trả dữ liệu đúng: CONFIRMED:A-1.
- Với **rewrite-valid**, target vẫn có thể thực thi bình thường, nhưng advice gọi next.call() rồi vứt kết quả và return OK. Caller không hề biết kết quả xác nhận gốc.
- Với **plain-invalid**, id rỗng tạo IllegalArgumentException("missing id"); caller nhận đúng lỗi.
- Với **swallow-invalid**, advice bắt IllegalArgumentException rồi return OK. Từ phía caller, tình trạng thất bại đã biến thành thành công giả.
- Với **safe-valid**, advice ghi audit rồi return đúng value của target.
- Với **safe-invalid**, advice ghi loại lỗi và ném lại chính Throwable; caller vẫn thấy thông điệp missing id.

Phần **wrap** tạo JDK dynamic proxy cho interface Checkout, dùng reflection để gọi target. Method.invoke gói lỗi do target ném trong InvocationTargetException, vì thế bộ chặn phải lấy wrapper.getCause() nếu muốn advice nhìn thấy ngoại lệ gốc. Điều này đặc trưng cho đường gọi reflection trong ví dụ, không phải một quy tắc về exception wrapper của mọi engine AOP.

**Phạm vi chứng minh:** ví dụ có một advice cho mỗi proxy, một lời gọi tuần tự, không side effect bền vững và lỗi được tạo xác định. Nó chứng minh tính chất điều khiển return/exception của around advice qua continuation. Nó chưa chứng minh về pointcut, thứ tự nhiều aspect, weaving, retry đa luồng hoặc quyền truy cập thực tế.

## 6. Advice nuốt lỗi: vì sao nguy hiểm hơn một log sai?

“Nuốt lỗi” xảy ra khi một ngoại lệ hoặc trạng thái thất bại đáng lẽ phải tới caller nhưng advice **chặn đường truyền lỗi và kết thúc bình thường**. Việc catch exception để ghi log tự nó không sai; sai ở quyết định tiếp theo khi advice được kỳ vọng trong suốt.

Xét đường truyền sau:

~~~text
caller
  |
  v
Advice.around
  |
  +---- proceed() --> Target
                      |
                      +---- throws IllegalArgumentException
  |
  +---- catch IllegalArgumentException
          |
          +---- return "OK" --> caller thấy thành công
~~~

Hậu quả có thể gồm:

- **Sai giao thức nghiệp vụ:** caller đánh dấu thao tác thành công dù target không cập nhật dữ liệu.
- **Mất quyết định xử lý lỗi:** tầng ngoài không thể trả mã lỗi phù hợp, cảnh báo người dùng hoặc retry theo quy tắc.
- **Sai giám sát:** tỷ lệ thành công giả tăng, error-rate giảm dù lỗi thật vẫn phát sinh.
- **Sai điều khiển giao dịch/tác dụng phụ:** code phía ngoài tiếp tục một nhánh thành công có thể gây thao tác không nên thực hiện.
- **Khó điều tra:** log ở target có lỗi, nhưng response/return ở caller cho biết thành công.

Có trường hợp **cố ý** biến lỗi thành giá trị fallback như cache miss hoặc xử lý một lỗi cụ thể thuộc hợp đồng. Khi đó cần quy định rõ **được phép bắt loại lỗi nào**, giá trị fallback có nghĩa gì, liệu có được xem là thành công không, và có cần ghi metric riêng. Không đánh đồng fallback được thiết kế với nuốt lỗi vô tình.

### 6.1. Catch quá rộng

Advice kiểu “catch Throwable rồi return null” thường che cả nhiều loại lỗi không được phép phục hồi. Catch Exception cũng có thể bao trùm lỗi lập trình không thuộc lỗi nghiệp vụ dự kiến. Ngay cả catch đúng loại vẫn có thể sai nếu đó là lỗi mà caller bắt buộc phải nhìn thấy.

**Nguyên tắc:** chỉ xử lý được khi có một hợp đồng phục hồi cụ thể; còn lại **ném tiếp**. Đừng chuyển mọi ngoại lệ thành trạng thái OK chỉ để tránh hiển thị stack trace.

### 6.2. Catch đúng nhưng ném sai

Ví dụ dưới đây là **đoạn mã minh họa** dùng kiểu Proceed của mục 5:

~~~java
Object loseCause(Proceed next) throws Throwable {
    try {
        return next.call();
    } catch (IllegalArgumentException original) {
        throw new IllegalStateException("failed"); // Mất liên kết cause.
    }
}
~~~

Nếu phải chuyển loại lỗi theo một hợp đồng rõ ràng, giữ cause:

~~~java
Object translate(Proceed next) throws Throwable {
    try {
        return next.call();
    } catch (IllegalArgumentException original) {
        throw new IllegalStateException("invalid request", original);
    }
}
~~~

Ở biến thể thứ hai, caller nhận IllegalStateException thay vì IllegalArgumentException: **đây vẫn là một thay đổi hành vi**, chỉ hợp lệ nếu API hoặc chính sách chuyển đổi lỗi cho phép. Giữ cause giúp truy vết nhưng không tự biến đổi thay đổi đó thành “trong suốt”.

### 6.3. Không nhận ra lỗi phụ sinh ra trong cleanup/logging

Nếu target ném lỗi E1 rồi nhánh finally của advice ném lỗi E2, E2 có thể trở thành lỗi được truyền ra và che E1. Do đó, code dọn tài nguyên hoặc ghi audit cần chính sách riêng cho lỗi phụ.

Trong code tự quản lý nhiều lỗi, có thể gắn lỗi phụ bằng Throwable.addSuppressed nếu thích hợp và nếu còn giữ được lỗi chính. Tuy nhiên, không tùy tiện gọi addSuppressed trên Throwable từ thư viện hoặc các đối tượng được chia sẻ; phải hiểu quy tắc sở hữu và không tạo chu kỳ nguyên nhân. Cơ chế try-with-resources của Java cũng có quy tắc suppressed để bảo tồn lỗi chính khi đóng resource gặp lỗi.

### 6.4. Ngoại lệ checked, unchecked và proxy

Một JDK dynamic proxy có thể gói **checked exception không được khai báo trong chữ ký interface** bằng UndeclaredThrowableException nếu InvocationHandler cho ngoại lệ đó thoát ra. Đây là một lớp wrapper về mặt hợp đồng proxy, không tự đồng nghĩa advice đã “nuốt” lỗi. Cần đọc cả cause của wrapper và chữ ký phương thức. Với phương thức ném unchecked exception như chương trình ở mục 5, lỗi gốc có thể đi thẳng đến caller.

## 7. Phân tích chính xác return, throw, proceed và finally

Một cách chẩn đoán hiệu quả là gắn mỗi advice với bốn điểm quan sát:

- **ENTER:** advice vừa bắt đầu.
- **PROCEED-RESULT:** next.proceed() trở về bình thường với giá trị R.
- **PROCEED-THROW:** next.proceed() ném ngoại lệ E.
- **ADVICE-OUTCOME:** lời gọi advice cuối cùng return giá trị nào hoặc throw ngoại lệ nào?

Bảng kiểm tra:

| Kết quả proceed | Kết quả advice | Diễn giải |
| --- | --- | --- |
| return R | return chính R | Trong suốt về return trong ca thử này |
| return R | return S khác R | Có thay đổi return, cần chứng minh chính sách cho phép |
| return R | throw E | Advice tạo lỗi mới hoặc làm lỗi ghi log/cleanup che kết quả |
| throw E | throw chính E | Đường truyền lỗi được bảo toàn |
| throw E | throw F có E là cause | Có chuyển đổi lỗi có truy vết; phải đúng hợp đồng |
| throw E | return R | Ngoại lệ bị xử lý/fallback; phải chứng minh đây là chủ đích |
| Không gọi proceed | return/throw | Chặn trước target; chỉ hợp lệ trong policy cho phép |
| Gọi proceed nhiều lần | return/throw | Retry/replay; cần xem idempotency và tác dụng phụ |

**Phân biệt reference và equality:** với giá trị immutable như String, có thể so sánh nội dung; nhưng với object result, chính sách trong suốt thường cần trả lại **chính reference** target đưa ra. Khi không thể bảo toàn identity vì phải wrap/copy theo chính sách, cần ghi rõ loại đối tượng mới và thuộc tính bắt buộc phải giữ.

**Cẩn thận với finally:** finally chạy cả khi return và khi throw. Đặt return/throw trong finally dễ thay kết quả đang trên đường ra. Nên dùng finally để cleanup không đổi outcome, đồng thời xử lý được lỗi cleanup theo chính sách rõ.

## 8. Tương tác nhiều aspect: lỗi do thứ tự, không chỉ do từng advice

Một lời gọi có thể đi qua chuỗi **TRACE → RETRY → VALIDATE → TARGET**. Các mối quan tâm tưởng như độc lập nhưng kết quả tùy thuộc vào thứ tự:

~~~text
Trường hợp A: RETRY nằm ngoài TRANSLATE
RETRY
  TRANSLATE
    TARGET -> IllegalArgumentException
  TRANSLATE -> IllegalStateException
RETRY kiểm tra IllegalArgumentException: không khớp, không thử lại

Trường hợp B: TRANSLATE nằm ngoài RETRY
TRANSLATE
  RETRY
    TARGET -> IllegalArgumentException
    RETRY có thể bắt lỗi gốc để cân nhắc thử lại
  RETRY trả thành công hoặc lỗi cuối
TRANSLATE chỉ xử lý outcome cuối
~~~

Đây là mô hình minh họa. Loại ngoại lệ nào thực sự có thể retry và nên retry phải được định nghĩa theo nghiệp vụ, **không** tự động coi IllegalArgumentException là lỗi tạm thời. Nếu retry lặp một thao tác không idempotent, có thể ghi hai lần dù advice cuối cùng trả thành công.

Khi nhiều aspect cùng có catch/return, phải biết:
- Advice nào nằm ngoài, advice nào nằm trong?
- Exception có bị wrap/translate trước khi tới interceptor quyết định retry không?
- Một failure ở attempt đầu đã được xử lý hay cần đi tới caller?
- Advice logging đang tính **mỗi attempt** hay **mỗi yêu cầu logic**?
- Có advice nào tự bắt lại lời gọi của nó thông qua pointcut, dẫn đến reentrancy không?

**Không suy luận precedence từ tên class hoặc vị trí trong file**. Tập join point, precedence và cách đan advice do engine AOP cụ thể quyết định. Xác minh bằng cấu hình và trace quan sát thực tế; nếu hai aspect đổi thứ tự làm lỗi biến mất, ghi đó là bằng chứng về tương tác, không tự động kết luận từng aspect đều đúng.

## 9. Cách tái hiện lỗi và xác định advice gây ra

### Bước 1 — Ghi hợp đồng trước khi thay code

Viết một câu định lượng: với đầu vào X, target phải trả R; với đầu vào Y, target phải ném E; side effect S thực hiện N lần. Đặt tiêu chí PASS/FAIL ở **caller**, vì caller là nơi thấy outcome cuối.

Ví dụ ở mục 5:
- id="A-1" phải trả "CONFIRMED:A-1".
- id="" phải ném IllegalArgumentException với message "missing id".
- Advice audit không được biến hai outcome thành "OK".

### Bước 2 — Thu hẹp thành MRE

Giữ một target, một phương thức, một advice và một lời gọi xác định. Loại bỏ mạng, cơ sở dữ liệu, queue, lịch trình và thời gian thực nếu chúng không liên quan. Lưu stack trace, loại exception và số lần target/proceed. Khi đã cô lập được một advice, mới thêm advice thứ hai để tìm lỗi tương tác.

### Bước 3 — So sánh năm đường đi

1. Target trực tiếp với đầu vào hợp lệ.
2. Target có advice với đầu vào hợp lệ.
3. Target trực tiếp với đầu vào lỗi.
4. Target có advice với đầu vào lỗi.
5. Cùng điều kiện sau khi sửa advice.

Ma trận này cho phép xác định **sai lệch do advice** thay vì nhầm với logic target đã sai sẵn. Với nhiều aspect, thêm các ca chỉ A, chỉ B, A ngoài B và B ngoài A.

### Bước 4 — Đặt log tại các ranh giới

Đừng chỉ log ở catch. Ghi:
- Giá trị và loại đối tượng target thực sự return, hoặc exception nó ném.
- Outcome ngay sau mỗi lần proceed.
- Outcome cuối cùng của mỗi advice.
- Outcome được caller quan sát.
- Số lần proceed và target được gọi; mã nhận dạng logical request/attempt nếu có retry.

Khi test concurrency, dùng correlation id và đồng bộ có kiểm soát. Không nối stack trace của các thread thành một call stack đồng bộ duy nhất.

### Bước 5 — Xem cơ chế áp dụng thật

Nếu dùng proxy, bảo đảm caller nhận proxy chứ không giữ trực tiếp target. Nếu dùng compile-time hoặc load-time weaving, kiểm tra bytecode đã biến đổi, phiên bản weaver, classloader và join point đúng. Một MRE JDK proxy có thể chứng minh lỗi ở logic around, nhưng không đủ để chứng minh một cấu hình weaving đã chọn đúng phương thức.

### Bước 6 — Sửa một biến, chạy lại các ca

Đổi một nhánh return hoặc catch, rồi chạy lại toàn bộ ma trận. Tránh vừa sửa pointcut, vừa đổi precedence, vừa thay logic để rồi không biết yếu tố nào giải quyết vấn đề.

## 10. Viết kiểm thử bảo vệ hợp đồng

**Không chỉ assert “không ném exception”.** Đó là một assertion nguy hiểm cho ca nuốt lỗi: advice sai ở ví dụ thậm chí sẽ làm assertion này thành công.

| Ca thử | Đầu vào | Mong đợi |
| --- | --- | --- |
| Success transparency | Dữ liệu hợp lệ | Return đúng nội dung và kiểu; reference giữ nguyên nếu hợp đồng yêu cầu |
| Failure transparency | Dữ liệu không hợp lệ | Caller nhận lỗi đúng class/cause theo hợp đồng |
| Advice logging failure | Sink ghi log lỗi | Outcome theo chính sách logging; không âm thầm đổi lỗi nghiệp vụ |
| Null return | Target trả null hợp lệ | Advice không tự đổi null nếu không có chính sách |
| Primitive return | Target trả int/boolean | Không null-unboxing, sai kiểu hoặc đổi giá trị |
| Multiple proceed | Advice retry với target giả | Số attempt đúng, side effect chỉ lặp khi được phép |
| Nested advice | A bao B hoặc B bao A | Return/throw, số log và thứ tự sự kiện đúng |
| Concurrent calls | Hai request có context khác nhau | Không lẫn result/exception/correlation giữa các request |

### 10.1. Test đơn vị bằng continuation giả

Có thể kiểm tra advice riêng mà không cần engine:

~~~java
// Đoạn kiểm thử minh họa đặt cùng phạm vi có các kiểu Advice, Proceed.
Advice transparent = next -> next.call();
Object marker = new Object();
Object result = transparent.around(() -> marker);
if (result != marker) {
    throw new AssertionError("result identity changed");
}
~~~

Đoạn này không có main/khai báo lớp độc lập; mục đích là giải thích điều kiện test. Một test khác dùng continuation ném sẵn một exception E rồi khẳng định advice ném lại **chính E** khi chính sách yêu cầu bảo toàn identity.

Trong hệ thống thật, không phải mọi advice đều phải bảo toàn Throwable identity; một advice chuyển đổi ngoại lệ có chủ đích được kiểm thử theo hợp đồng **loại lỗi mới và cause**.

### 10.2. Test lỗi bị nuốt không cần mock phức tạp

Dùng target ném IllegalArgumentException("missing id"), gọi qua advice, và viết assertion rằng caller **phải nhận ngoại lệ**. Test thất bại nếu advice trả "OK". Với phương thức có side effect, dùng counter/in-memory store để chắc rằng việc nuốt lỗi không làm caller đánh dấu thành công rồi ghi dữ liệu ngoài ý muốn.

### 10.3. Test thất bại của chính advice

Trường hợp ít được kiểm tra: log sink, formatter hoặc metadata extractor của advice ném lỗi, trong khi target đã thành công hoặc đã ném exception E. Hãy dựng fake sink ném exception cố định; xác định policy của aspect là:

- **Fail closed:** lỗi của cơ chế kiểm soát bắt buộc phải khiến lời gọi thất bại.
- **Fail open có kiểm soát:** một công cụ quan sát không bắt buộc có thể ghi nhận qua kênh khác và không làm đổi outcome nghiệp vụ.
- **Truyền lỗi:** nếu error policy yêu cầu caller biết lỗi của advice.

Không áp dụng một chính sách chung cho mọi loại aspect. Với kiểm soát truy cập và audit bắt buộc, việc “cứ trả OK” thường gây hại nghiêm trọng.

## 11. Khi nào chuyển đổi return hoặc exception là hợp lệ?

Không phải mọi biến đổi do advice đều là bug. AOP cho phép thể hiện chính sách xuyên suốt, nhưng chính sách phải **cụ thể, có phạm vi và có test**.

### Authorization

Advice có thể **không gọi proceed** khi quyền không hợp lệ. Outcome hợp lệ thường là từ chối hoặc ném lỗi rõ ràng theo hợp đồng. Trả một chuỗi "OK" khi không được phép là sai hiển nhiên.

### Cache

Advice có thể trả kết quả từ cache mà không chạy target. Điều đó hợp lệ khi cache được phép theo hợp đồng dữ liệu, khóa cache đúng, không trả dữ liệu sai scope, và xử lý invalidation phù hợp. Cache hit không được che lỗi từ thao tác bắt buộc phải thực hiện mỗi lần.

### Retry

Advice có thể gọi proceed nhiều lần với điều kiện retry rõ. Phải kiểm tra idempotency, số attempt, backoff và ngoại lệ cuối. Không tự ý retry mọi exception; tuyệt đối không gộp “đã thử lại” với “đã thành công”.

### Fallback

Advice có thể trả giá trị dự phòng khi một lỗi **được liệt kê rõ là có thể phục hồi** xảy ra. Giá trị dự phòng phải là một kết quả có ngữ nghĩa hợp lệ, caller biết trạng thái degraded nếu cần, và có metric. Một fallback thành công giả cho thao tác ghi hoặc thanh toán là nguy hiểm.

### Exception translation

Advice có thể chuyển lỗi tầng thấp sang lỗi API có ý nghĩa hơn, với cause đầy đủ và mapping chính xác. Ví dụ, lỗi truy cập tài nguyên có thể trở thành lỗi dịch vụ; nhưng chuyển mọi lỗi sang IllegalStateException không phân biệt sẽ làm mất khả năng xử lý có chủ đích.

### Result normalization

Advice có thể chuẩn hóa output nếu **hợp đồng của join point đã tuyên bố điều đó**, chẳng hạn chuẩn hóa text. Tuy nhiên, làm biến đổi object có identity hoặc semantics đặc biệt có thể phá invariants. Đừng tự ý thay return khi nhiệm vụ ban đầu chỉ là tracing/timing.

**Tiêu chuẩn chung:** người gọi và người sở hữu nghiệp vụ đã chấp nhận thay đổi; scope join point được giới hạn; thay đổi về return, exception và side effect được kiểm thử.

## 12. Các trường hợp nâng cao dễ bỏ sót

### 12.1. Sai vị trí return sau nhiều proceed

Một advice có thể gọi proceed hai lần, lấy R1 rồi R2 nhưng lại return R1, hoặc return một hằng số. Khi target không idempotent, side effect có thể xảy ra hai lần trong khi caller chỉ thấy một kết quả. Ghi mỗi attempt riêng, xác định outcome nào là outcome cuối theo chính sách retry.

### 12.2. Xử lý lỗi trong advice cuối cùng làm mất cause

Lớp proxy, reflection và mã woven có thể thay hình thức stack trace. Nếu advice tạo Throwable mới mà không giữ cause, việc điều tra sẽ khó hơn. Đọc trace đầy đủ gồm cause, suppressed; phân biệt **nơi lỗi được tạo** và **nơi lỗi được chuyển đổi**. Một frame ở adapter/proxy chưa đủ chứng minh adapter gây ra lỗi nghiệp vụ.

### 12.3. Bắt Throwable có thể bao gồm những lỗi không thể phục hồi

Lệnh catch Throwable có phạm vi rộng hơn catch Exception. Trong advice quan sát, bắt rồi **ném lại** có thể giúp ghi dấu vết; nhưng làm việc quá nhiều trong catch, ghi log có thể ném lỗi hoặc trả fallback chung là nguy hiểm. Không cố phục hồi mọi lỗi thuộc nhóm Error. Thiết kế failure policy cho từng loại tình huống.

### 12.4. Lỗi nằm trong lời gọi bất đồng bộ

Với API bất đồng bộ, “return thành công” có thể chỉ là trả một future chưa hoàn tất. Một advice ghi “success” ngay sau proceed có thể chỉ chứng minh future đã được tạo. Cần phân biệt lỗi ném **đồng bộ trước khi trả future** với lỗi **hoàn tất future trong trạng thái thất bại**. Việc gắn handler xử lý completion phải bảo toàn completion/cancellation và không làm rò context.

### 12.5. Mutable shared state giữa các request

Nếu advice giữ lastResult hoặc lastError trong field dùng chung, hai luồng có thể đổi dữ liệu của nhau. Khi đó caller nhận outcome sai dù mỗi target riêng lẻ đều đúng. Dùng trạng thái theo invocation, không chia sẻ mutable result giữa request nếu không có thiết kế đồng bộ rõ; thử đồng thời với input khác nhau để phát hiện.

### 12.6. Pointcut quá rộng làm advice tác động sai phương thức

Một advice fallback chỉ dành cho read-only query nhưng pointcut chọn cả thao tác ghi có thể khiến lỗi ghi bị nuốt. Luôn thử cả **join point phải match** và **join point không được match**. Tập join point hỗ trợ khác nhau theo engine; phải xác minh thực tế thay vì đoán từ tên method.

## 13. Quy trình review code advice trước khi triển khai

Khi review một aspect có around advice, đi theo đường xử lý cho từng nhánh:

1. **Input/selection:** pointcut nào kích hoạt advice? Có phương thức nào không phù hợp bị chọn?
2. **Enter:** advice có kiểm tra trước và ném lỗi đúng chính sách hay không?
3. **Continuation:** proceed được gọi 0, 1 hay nhiều lần; có điều kiện giới hạn và guard reentrancy không?
4. **Success:** sau proceed, có return lại đúng giá trị, kiểu, nullability, identity hoặc contract biến đổi được duyệt không?
5. **Failure:** catch ngoại lệ nào? Có ném lại, wrap giữ cause, hoặc fallback đúng điều kiện không?
6. **Finally/cleanup:** code cleanup có thể return/throw làm che outcome hay không? Lỗi phụ được xử lý thế nào?
7. **Composition:** advice nằm ngoài hay trong các aspect khác? Exception có bị translate trước khi đến retry/audit không?
8. **Runtime:** proxy/weaving áp dụng vào đúng lời gọi chưa? Các trường hợp gọi nội bộ, async và classloader đã được xét chưa?
9. **Evidence:** kiểm thử qua caller, đầu ra/ngoại lệ thật, side effect, số lần gọi và log sự kiện có chứng minh hợp đồng không?

Trong pull request hay tài liệu thiết kế, phần mô tả thay đổi nên nêu một tình huống **trước–sau**: “Trước đây, khi target ném IllegalArgumentException('missing id'), caller nhận 'OK'. Sau sửa, caller nhận đúng IllegalArgumentException và không có trạng thái thành công giả.” Việc mô tả bằng quan sát của caller giúp người review xác minh mục tiêu chính xác.

## 14. Sai lầm thường gặp khi cố sửa lỗi

| Cách sửa sai | Vì sao chưa đúng | Cách kiểm chứng/sửa |
| --- | --- | --- |
| Xóa catch để hết bị nuốt lỗi | Có thể làm mất logging, cleanup hoặc policy phục hồi thật sự cần thiết | Chỉ ném tiếp những lỗi phải truyền; giữ nhánh phục hồi đã định nghĩa rõ |
| Luôn return giá trị của proceed | Có thể phá chính sách authorization/cache/fallback có chủ đích | So sánh với hợp đồng riêng của loại aspect |
| Catch rồi throw new RuntimeException(e.getMessage()) | Mất cause và type | Giữ cause hoặc ném lại chính E khi hợp đồng yêu cầu |
| Return trong finally để bảo đảm có output | Ghi đè lỗi và return đang truyền ra | Dùng finally cho cleanup; tránh return/throw ngoài policy |
| Đổi thứ tự aspect rồi kết luận đã sửa | Có thể che triệu chứng, lỗi xảy ra ở join point khác | Test ma trận precedence và xác định nguyên nhân |
| Chỉ assert status=200 hoặc “không lỗi” | Nuốt lỗi được coi là thành công | Assert cụ thể giá trị, exception, side effect |
| Chỉ unit-test advice trực tiếp | Không phát hiện cấu hình pointcut/proxy/weaving sai | Thêm integration test qua đường gọi thật |
| Catch mọi Throwable và trả fallback | Che cả lỗi không thể phục hồi | Giới hạn loại lỗi, ngữ cảnh, hợp đồng fallback |
| Log đủ nhiều nhưng không có request id | Khó nối target, advice và caller trong concurrency | Correlate bằng logical-call id và attempt id |
| Kiểm tra giá trị return mà quên gọi lặp | Target có thể thực hiện hai lần dù return cuối đúng | Đếm proceed, target, side effect thực tế |

## 15. Bài tập tự luyện

**Bài tập 1 — Phát hiện lỗi đổi return.** Trong chương trình mục 5, đổi rewrite thành return kết quả của next.call() và chạy lại. Kỳ vọng dòng rewrite-valid trả CONFIRMED:A-1. Giải thích vì sao trước đó chương trình vẫn biên dịch nhưng sai ngữ nghĩa.

**Bài tập 2 — Phát hiện lỗi bị nuốt.** Đổi swallow thành catch rồi throw failure. Kỳ vọng dòng swallow-invalid thể hiện ERROR:missing id. Viết assertion ở caller để sai lầm “return OK” khiến test fail.

**Bài tập 3 — Kiểm thử finally.** Viết một advice có finally chứa return "OK" và bọc một target ném lỗi. Quan sát outcome; sau đó bỏ return trong finally và ném lại lỗi. Nêu nguyên nhân theo quy tắc điều khiển của Java.

**Bài tập 4 — Thử nhiều aspect.** Thêm một advice chuyển đổi IllegalArgumentException thành IllegalStateException có cause; ghép với một advice bắt riêng IllegalArgumentException. Đổi thứ tự, in event trace và giải thích tại sao cùng target có thể dẫn đến kết quả khác nhau. Đừng dùng exception đó làm ví dụ mặc định cho retry sản xuất.

**Bài tập 5 — Fallback có chủ đích.** Đề xuất một API read-only được phép trả kết quả cache khi nguồn dữ liệu tạm lỗi. Ghi rõ những lỗi được fallback, thời hạn dữ liệu, cách báo trạng thái degraded và test rằng các lỗi ngoài danh sách vẫn phải truyền đi.

## 16. Checklist chốt một advice an toàn về kết quả/lỗi

- [ ] Hợp đồng của join point được mô tả bằng đầu vào, return, exception, side effect và tính lặp an toàn.
- [ ] Đã xác định advice là trong suốt hay có quyền chuyển đổi kết quả/lỗi theo chính sách.
- [ ] Với lời gọi thành công, return đúng value/kiểu/nullability/identity cần thiết.
- [ ] Với lỗi, ném lại hoặc chuyển đổi đúng hợp đồng; giữ cause, suppressed khi thích hợp.
- [ ] Không có return hoặc throw ngoài chính sách trong finally/cleanup làm che outcome gốc.
- [ ] Số lần proceed được kiểm soát; retry có giới hạn và cân nhắc idempotency.
- [ ] Pointcut và precedence đúng; không chọn nhầm join point hoặc tự tái nhập.
- [ ] Advice xử lý lỗi của chính logging/audit/fallback theo failure policy đã thiết kế.
- [ ] Test có cả ca thành công, lỗi, null/kiểu đặc biệt, nhiều advice và concurrency khi liên quan.
- [ ] Đã xác minh qua đường gọi AOP thật; log/trace có thể đối chiếu outcome target với caller.

**Kết luận:** advice là một phần của đường thực thi công khai dù nằm ngoài mã nghiệp vụ. Sai lầm phổ biến không nằm ở việc có catch hoặc có return, mà ở **không bảo toàn hợp đồng quan sát được**: thay giá trị mà caller cần hoặc biến thất bại thành thành công không được cho phép. Đọc từng nhánh proceed/return/throw, so sánh target với caller và khóa hành vi bằng kiểm thử hồi quy là cách chắc chắn để phát hiện và sửa lỗi này.
