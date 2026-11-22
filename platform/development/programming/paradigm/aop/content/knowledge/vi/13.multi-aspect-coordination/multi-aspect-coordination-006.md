# Thiết kế thứ tự tường minh thay vì dựa vào chi tiết triển khai

## 1. Vấn đề: khi nhiều aspect cùng can thiệp vào một điểm

Trong **Aspect-Oriented Programming (AOP)**, một **join point** được pointcut chọn có thể đồng thời phù hợp với nhiều aspect. Chẳng hạn một lời gọi xử lý đơn hàng có thể cần tracing, đo latency, retry lỗi tạm thời, caching, audit, kiểm tra quyền và quản lý tài nguyên. Không phải chỉ cần từng advice **đúng khi chạy riêng** là cả hệ thống sẽ đúng khi ghép chúng lại: **thứ tự phối hợp** có thể thay đổi những điều mà mỗi advice quan sát, thời điểm nó chạy, số lần target được thực thi và kết quả cuối cùng.

Giả sử hai advice đều hoạt động khi dùng riêng:

- `Retry` có thể tiếp tục vào target nhiều lần khi gặp một loại lỗi tạm thời.
- `Metrics` đếm các lần gọi và đo khoảng thời gian.

Nếu Metrics nằm **bên ngoài** Retry, nó có thể đo một **logical operation** gồm tất cả attempts và backoff. Nếu Metrics nằm **bên trong** Retry, nó có thể chạy **mỗi attempt**. Cả hai thiết kế đều có thể hợp lý, nhưng mang **nghĩa khác nhau**.

Bởi vậy, trọng tâm bài học là:

> **Định nghĩa quan hệ thứ tự bằng yêu cầu ngữ nghĩa có thể kiểm chứng, khai báo quan hệ ấy rõ ràng, và thất bại sớm nếu nhiều advice không thể được sắp thành một chuỗi nhất quán. Không dựa vào tên class, thứ tự khai báo, thứ tự quét package, cấu trúc collection hay tình cờ của classloader.**

### Mục tiêu

Sau bài này, bạn có thể:

1. Phân biệt **thứ tự advice**, **thứ tự aspect instance được tạo**, **thứ tự đăng ký**, **thứ tự weaving** và **thứ tự sự kiện runtime**.
2. Hiểu cách nhiều around advice **lồng nhau** và vì sao hành vi trước, sau, lỗi và `finally` có thứ tự khác nhau.
3. Xây **quan hệ ràng buộc tường minh** như `Trace bao ngoài Retry`, `Retry bao ngoài MetricAttempt` theo mục tiêu đo.
4. Thiết kế precedence bằng **priority**, **partial order/đồ thị phụ thuộc**, **nhóm concern** và chính sách xử lý tie/cycle.
5. Phân tích tình huống phức tạp: retry, cache, authorization, transaction, audit, short-circuit, error handling, async completion và nested calls.
6. Tránh các lỗi như dựa vào thứ tự reflection, load class, tên file hay trật tự các phần tử trong `HashMap`.
7. Chạy chương trình **Java 17** hoàn chỉnh, tự sắp chuỗi interceptors với priority rõ ràng và cho thấy metric “mỗi attempt” khác metric “mỗi logical call”.
8. Kiểm thử cấu hình thứ tự theo cả **success, failure, skip, retry, concurrency và bất đồng bộ**.

Phạm vi là **AOP cơ bản và nâng cao nói chung**. Cú pháp đặt precedence, quy tắc mặc định và ý nghĩa priority cụ thể **không giống nhau giữa mọi AOP engine**. Các ví dụ thứ tự trong bài sử dụng **chính sách được định nghĩa tường minh**, không áp nó như một chuẩn của mọi công cụ.

## 2. Những loại thứ tự không được đánh đồng

Một rule đặt **aspect A ở ngoài B** không đồng nghĩa mọi dòng log của A phải xuất hiện trước B. Để thiết kế một thứ tự **tường minh**, trước tiên tách các cấp sau:

| Thứ tự | Dữ liệu đang nói tới | Có thể dùng làm hợp đồng precedence? |
| --- | --- | --- |
| **Source/khởi tạo** | Thứ tự file, class declaration, tạo instance | Không tự bảo đảm thứ tự advice |
| **Đăng ký** | Interceptor được thêm vào registry theo thứ tự nào | Chỉ khi API công bố quy tắc sắp xếp |
| **Build/weaving** | Trình biên dịch/bộ dệt xử lý các input theo thứ tự nào | Có thể ảnh hưởng artifact, không mặc định quyết định runtime nesting |
| **Aspect precedence / advice order** | Quan hệ bắt buộc giữa những lớp advice được chọn | Là đối tượng cần đặc tả theo engine, kể cả advice khác loại |
| **Runtime events** | Trình tự enter, return, throw, finally, short-circuit và retry | Hệ quả của thứ tự kết hợp **cùng** luồng điều khiển |
| **Business effects** | Quyền, giao dịch, ghi dữ liệu, commit, phát sự kiện | Không được suy từ vị trí một log đơn lẻ |

**Coverage khác order.** Dù precedence được mô tả chính xác, advice vẫn không chạy nếu pointcut không khớp, join point ngoài weaving scope, caller bỏ qua proxy, điều kiện runtime sai hoặc một advice ở ngoài không gọi continuation. Sửa thứ tự không chữa được việc chọn sai tập điểm hay sai đường gọi.

Tương tự, với before, after-returning, after-throwing, finally và around, ý nghĩa của “trước” hoặc “sau” gắn với **ranh giới cụ thể**. Cần kiểm thử trên cả normal return, exception và short-circuit; không xem thứ tự từng xuất hiện trong một lần chạy là cam kết của công cụ AOP.

## 3. Mô hình nền tảng: thứ tự bao ngoài và bao trong

Giả sử có hai around advice A và B. Ta tuyên bố **A bao ngoài B**:

~~~text
caller
  |
  v
A.before
  |
  +--> A.proceed()
          |
          v
       B.before
          |
          +--> B.proceed()
                  |
                  v
                 target
          |
       B.after
  |
A.after
  |
caller
~~~

Nếu target trả bình thường, cả A và B gọi `proceed` đúng một lần, thứ tự quan sát:

~~~text
A before
B before
TARGET
B after
A after
~~~

**Nhận xét cốt lõi:** *Before ở tầng ngoài chạy trước before tầng trong, nhưng after ở tầng ngoài chạy sau after tầng trong.* Vì vậy một rule “aspect A ưu tiên trước B” cần làm rõ nó nói về **nesting/precedence** chứ không phải mọi dòng log của A đều đứng trước mọi dòng log của B.

### 3.1. Trên đường lỗi

Nếu target ném `E` và cả hai advice chỉ ghi nhận rồi ném lại:

~~~text
A before
B before
TARGET throws E
B catch E
B finally
A catch E
A finally
CALLER receives E
~~~

Nếu B **bắt E rồi trả fallback**, A có thể chỉ thấy **normal return**. Nếu B biến đổi E thành lỗi E2, A thấy E2. **Lỗi quan sát ở advice ngoài có thể đã được advice trong chuyển đổi.** Do đó thứ tự là một phần của hợp đồng error semantics.

### 3.2. Nếu advice ngoài không gọi `proceed`

~~~text
A around:
    if cacheHit:
        return cachedValue
    return proceed()
~~~

Khi `cacheHit=true`, B và target có thể **không chạy**. Không có nghĩa B sai priority; B đơn giản chưa nhận occurrence ở nhánh này.

Nếu B là kiểm tra quyền **bắt buộc** và nằm trong một cache có thể return sớm, đó có thể là lỗi kiến trúc nghiêm trọng. Cần thiết kế sao cho policy bắt buộc không thể bị bỏ qua hoặc được bảo vệ ở trusted boundary độc lập.

### 3.3. Nếu advice gọi tiếp nhiều lần

~~~text
A around retry:
    for attempt in attempts:
        try:
            return proceed()
        catch transientError:
            maybeRetry()
~~~

Nếu B nằm trong A, **B có thể chạy theo mỗi attempt**. Nếu B nằm ngoài A, B có thể chỉ chạy **một lần cho logical operation**. Ngữ nghĩa này cũng phụ thuộc engine có cho phép gọi continuation nhiều lần hay không và việc inner advice được tái chạy như thế nào. Không tự áp dụng pseudocode retry cho mọi engine.

## 4. Viết mục tiêu ngữ nghĩa trước khi đặt priority

Một thiết kế tốt không bắt đầu bằng “cho aspect X priority 1, Y priority 2” khi chưa biết **vì sao**.

Thay vào đó, viết requirement có thể test:

- “Trace tổng đo từ lúc caller đi vào boundary tới khi retry kết thúc.”
- “Metric `attempts` tăng một lần cho mỗi lần target được thử.”
- “Authorization phải được kiểm tra trước khi bất kỳ đường nào tạo side effect nhạy cảm.”
- “Audit thành công chỉ được ghi sau khi điều kiện xác nhận thành công được thỏa, không chỉ khi target return tạm thời.”
- “Cache hit có được tính là một request logic hay một target invocation?”
- “Cleanup span xảy ra cả success và failure; với async phải theo task completion nếu span được định nghĩa end-to-end.”
- “Lỗi của telemetry không được che lỗi nghiệp vụ nếu telemetry được công bố là best effort.”

Sau đó mới dịch thành quan hệ:

~~~text
TraceTotal OUTER_THAN Retry
Retry OUTER_THAN MetricPerAttempt
Authorization OUTER_THAN CacheWithEarlyReturn
~~~

Đây là **cú pháp biểu diễn quan hệ**, không phải cú pháp cấu hình của bất kỳ công cụ nào. Trong một hệ thống thật, vài ràng buộc có thể được giải quyết bằng ordering, còn vài ràng buộc liên quan bảo mật/commit phải được thực hiện tại boundary tường minh hơn.

### 4.1. Tách “bắt buộc chạy” khỏi “chạy theo thứ tự”

Nếu requirement là “authorization không bao giờ bị bỏ qua”, chỉ đặt Authorization ngoài Cache **chưa chứng minh** toàn bộ ứng dụng được bảo vệ: direct target call, self-invocation qua một proxy hoặc một entry point khác có thể bypass cả hai. Cần bảo vệ ở biên tin cậy và có negative tests.

Nếu requirement là “audit ghi sau commit”, chỉ đặt Audit vào sau body của method chưa đủ nếu commit có thể xảy ra muộn hơn hoặc future mới báo hoàn tất về sau. Thứ tự advice phải kết hợp với **định nghĩa đúng của sự kiện hoàn thành**.

### 4.2. Cần đặt tên metric theo phạm vi

Hai cái tên rõ nghĩa:
- `logical_operation_duration`: bao retry, backoff và sự kiện hoàn thành đã xác định.
- `attempt_duration`: đo mỗi lượt target attempt.

Nếu đều đặt `duration`, khi đổi thứ tự retry và metric mà dashboard không đổi tên, những số liệu trước/sau không còn so sánh đúng về semantics.

## 5. Các cách khai báo precedence tường minh

### 5.1. Thứ tự tổng bằng một danh sách đã sắp

Nếu chỉ có vài interceptors tại một boundary, có thể khai báo:

~~~text
outermost -> [TraceTotal, Authorization, Retry, MetricPerAttempt] -> target
~~~

Ưu điểm: dễ review và tạo test. Đánh đổi: khi có nhiều aspect độc lập và module mở rộng, danh sách toàn cục dài, dễ có phụ thuộc không mong muốn.

**Chú ý:** thứ tự danh sách chỉ có ý nghĩa nếu **composition API thật sự quy định** “phần tử đầu là ngoài cùng” hoặc “phần tử đầu chạy trước”. Tài liệu hóa quy tắc và test, không phó mặc cho helper constructor.

### 5.2. Priority bằng số hoặc thứ hạng

Một chính sách nội bộ có thể quy định:

~~~text
priority thấp hơn = lớp ngoài hơn
TraceTotal:        10
Authorization:     20
Retry:             30
MetricPerAttempt:  40
~~~

Đây là **chính sách tùy định nghĩa trong bài học**. Một engine khác có thể hiểu số lớn hơn là ưu tiên cao hơn hoặc sắp thứ tự before và after khác nhau.

Cần xác định:
1. Độ ưu tiên nhỏ/lớn tương ứng **outer/inner** hay chỉ “được xem xét trước”?
2. Cấu hình priority trùng nhau có bị từ chối không?
3. Nếu chỉ một aspect khớp join point, priority có tạo side effect nào không?
4. Nếu một advice ngoài short-circuit, những advice trong có chạy không?
5. Khi lỗi/return, thứ tự unwind được engine quy định thế nào?

**Khuyến nghị thiết kế:** Với những cặp advice có quan hệ ngữ nghĩa bắt buộc, nên **fail fast** khi priority trùng/không xác định hơn là silently dựa vào tên class hay đăng ký trước.

### 5.3. Quan hệ thứ tự bộ phận (partial order)

Trong hệ thống lớn, không phải mọi cặp aspect đều cần quan hệ. Có thể ghi:

~~~text
TraceTotal      -> Retry
Retry           -> MetricPerAttempt
Authorization   -> Cache
~~~

Dấu `A -> B` nghĩa là **A phải nằm ngoài B** trong ví dụ. Đây là đồ thị có hướng các ràng buộc, không nhất thiết tạo một thứ tự duy nhất cho các node không có quan hệ.

Nếu cần chuyển sang chuỗi tuyến tính, có thể dùng **topological sort**. Nhưng cần phân biệt:
- Một **partial order hợp lệ** chỉ nêu những cặp bắt buộc.
- Một **total order triển khai** phải chọn cách sắp tất cả phần tử được áp dụng.
- Các phần tử **không có ràng buộc** có thể đổi chỗ theo một tie-break được định nghĩa, hoặc hệ thống yêu cầu bổ sung precedence.

Không tự suy rằng topological sort luôn chỉ có **một** kết quả. Với nhiều node không liên hệ, thường có nhiều thứ tự hợp lệ.

### 5.4. Phát hiện cycle thay vì đoán

Ví dụ:

~~~text
A OUTER_THAN B
B OUTER_THAN C
C OUTER_THAN A
~~~

Đây là một chu trình mâu thuẫn, không có một nesting tuyến tính thỏa cả ba. Hệ thống cần báo **configuration error**, không chỉ chọn “last one wins” tình cờ.

Trong CI, nên có một phép kiểm tra graph:
- Các tên aspect/advice có tồn tại?
- Có phụ thuộc bị bỏ lửng?
- Có chu trình?
- Có hai rule mâu thuẫn?
- Có node không được xác định khi policy yêu cầu total order?
- Có thay đổi ordering khi feature flag/tập aspect áp dụng đổi không?

### 5.5. Khi nào dùng nhóm concern?

Có thể quy định các **phase/boundary** thay vì một bảng priority dài:

~~~text
RequestBoundary
  └─ Governance (auth, quota)
      └─ LogicalOperation (trace, retry)
          └─ AttemptBoundary (metric, transient-IO)
              └─ Target
~~~

Cách này hữu ích khi số aspect lớn. Nhưng “nhóm” phải có nghĩa **được hiện thực và kiểm tra**; không chỉ là thư mục source hoặc tên package đẹp.

## 6. Những thứ không nên là căn cứ precedence

### 6.1. Tên file và tên class

Đặt `01Tracing`, `02Retry` hoặc prefix alphabet không bảo đảm mọi engine sắp theo tên. Refactor tên class có thể vô tình làm đổi behavior nếu bạn đã dùng một quy tắc tự chế thiếu tài liệu.

Nếu một application **cố ý** sắp theo tên, đó phải được định nghĩa là hợp đồng thứ tự, có test; vẫn nên cân nhắc dùng priority/constraint có ý nghĩa ngữ nghĩa hơn.

### 6.2. Thứ tự reflection

Java reflection trả về tập method/field qua API có các quy tắc riêng và không cung cấp một **hợp đồng tổng quát về thứ tự khai báo source** để dùng làm precedence. Đừng dựa vào “ở JDK máy tôi method A xuất hiện trước B” để sắp advice.

### 6.3. Thứ tự HashMap/HashSet

Một `HashMap` hoặc `HashSet` không có hợp đồng iteration order cần thiết cho precedence. Ngay cả khi output trông ổn định trong vài lần chạy, nó không nên được dùng như cấu hình thứ tự ngầm định.

### 6.4. Thứ tự classloader hoặc module scan

Cấu hình scanning có thể phụ thuộc classpath, loader, artifact, build tool và incremental changes. Việc class được discover hoặc load trước **không tự mang nghĩa nghiệp vụ** rằng advice phải bao ngoài hoặc bao trong advice khác.

### 6.5. Thứ tự weaving

Một công cụ có thể biến đổi bytecode qua nhiều pass và lắp hook ở những chỗ khác nhau. Dù thứ tự các pass ảnh hưởng output trong một engine, **thứ tự biến đổi** không phải lúc nào cũng bằng **thứ tự runtime nested advice**. Nếu behavior dựa trên ordering của pass, cần tài liệu engine và test bytecode/runtime tương ứng.

### 6.6. “Vừa chạy thử thấy đúng”

Một test chỉ chứng minh behavior với artifact/config/runtime ấy. Nếu ordering không được khai báo và hỗ trợ như hợp đồng, phiên bản mới, module mới, classpath khác hay một refactor có thể làm đổi kết quả. Test là **bằng chứng xác minh hợp đồng**, không thay thế việc định nghĩa hợp đồng.

## 7. Ví dụ Java 17: hai thứ tự hợp lệ, hai phạm vi metric khác nhau

Ví dụ sau không dùng một engine weaving hoặc DSL pointcut cụ thể. Nó tạo một **interceptor chain tường minh** bằng Java 17, rồi sắp theo priority với chính sách:

> **Số priority nhỏ hơn = advice ở ngoài hơn. Priority trùng nhau = configuration error.**

Mỗi lần chạy một `WorkTarget` mới. Target thất bại với `TransientFailure` trong attempt đầu và thành công ở attempt thứ hai. `Retry` cho phép tối đa hai attempts. `Metric` in `begin/end` trong `finally` để quan sát mỗi lần đoạn bên trong nó chạy; đây là marker **phạm vi**, không phải công cụ đo số nano giây.

Chương trình chạy hai trường hợp:

- **Case 1:** Trace( Retry( Metric( Target ))) → Metric xuất hiện **mỗi attempt**.
- **Case 2:** Trace( Metric( Retry( Target ))) → Metric xuất hiện **một lần cho logical call**.

Tạo file **`ExplicitAdviceOrderDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

public class ExplicitAdviceOrderDemo {
    @FunctionalInterface
    interface Work {
        String execute();
    }

    @FunctionalInterface
    interface Next {
        String run();
    }

    @FunctionalInterface
    interface Interceptor {
        String around(Next next);
    }

    record Stage(String name, int priority, Interceptor interceptor) {}

    static final class TransientFailure extends RuntimeException {
        TransientFailure() {
            super("temporary outage");
        }
    }

    static final class WorkTarget implements Work {
        int attempts;

        @Override
        public String execute() {
            attempts++;
            System.out.println("TARGET attempt " + attempts);
            if (attempts == 1) {
                throw new TransientFailure();
            }
            return "OK";
        }
    }

    static Interceptor trace() {
        return next -> {
            System.out.println("TRACE enter");
            try {
                String result = next.run();
                System.out.println("TRACE return " + result);
                return result;
            } catch (RuntimeException error) {
                System.out.println("TRACE throw "
                        + error.getClass().getSimpleName());
                throw error;
            } finally {
                System.out.println("TRACE finally");
            }
        };
    }

    static Interceptor retry() {
        return next -> {
            for (int attempt = 1; attempt <= 2; attempt++) {
                System.out.println("RETRY attempt " + attempt);
                try {
                    return next.run();
                } catch (TransientFailure error) {
                    System.out.println("RETRY observed transient");
                    if (attempt == 2) {
                        throw error;
                    }
                }
            }
            throw new AssertionError("unreachable");
        };
    }

    static Interceptor metric() {
        return next -> {
            System.out.println("METRIC begin");
            try {
                return next.run();
            } finally {
                System.out.println("METRIC end");
            }
        };
    }

    static Work compose(Work target, List<Stage> stages) {
        List<Stage> sorted = new ArrayList<>(stages);
        sorted.sort(Comparator.comparingInt(Stage::priority));

        Set<Integer> priorities = new HashSet<>();
        for (Stage stage : sorted) {
            if (!priorities.add(stage.priority())) {
                throw new IllegalArgumentException(
                        "duplicate priority " + stage.priority());
            }
        }

        Work current = target;
        for (int index = sorted.size() - 1; index >= 0; index--) {
            Interceptor interceptor = sorted.get(index).interceptor();
            Work inner = current;
            current = () -> interceptor.around(inner::execute);
        }
        return current;
    }

    static void demonstrate(String title, List<Stage> stages) {
        System.out.println(title);
        Work work = compose(new WorkTarget(), stages);
        System.out.println("CALLER " + work.execute());
    }

    public static void main(String[] args) {
        demonstrate("CASE 1: per attempt", List.of(
                new Stage("Metric", 30, metric()),
                new Stage("Trace", 10, trace()),
                new Stage("Retry", 20, retry())
        ));

        demonstrate("CASE 2: logical call", List.of(
                new Stage("Retry", 30, retry()),
                new Stage("Metric", 20, metric()),
                new Stage("Trace", 10, trace())
        ));
    }
}
~~~

Biên dịch và chạy bằng JDK 17 hoặc mới hơn:

~~~bash
javac ExplicitAdviceOrderDemo.java
java ExplicitAdviceOrderDemo
~~~

**Stdout kỳ vọng, đúng thứ tự:**

~~~text
CASE 1: per attempt
TRACE enter
RETRY attempt 1
METRIC begin
TARGET attempt 1
METRIC end
RETRY observed transient
RETRY attempt 2
METRIC begin
TARGET attempt 2
METRIC end
TRACE return OK
TRACE finally
CALLER OK
CASE 2: logical call
TRACE enter
METRIC begin
RETRY attempt 1
TARGET attempt 1
RETRY observed transient
RETRY attempt 2
TARGET attempt 2
METRIC end
TRACE return OK
TRACE finally
CALLER OK
~~~

### 7.1. Vì sao danh sách khai báo không quyết định kết quả?

Trong Case 1, `List.of` được viết theo thứ tự `Metric, Trace, Retry`. Nhưng `compose` sắp theo số priority `10, 20, 30`, tạo chuỗi **Trace → Retry → Metric → Target**. Vì vậy output bắt đầu bằng `TRACE enter`, không phải `METRIC begin`.

Đây là cách tránh một phụ thuộc ngầm vào thứ tự khai báo. **Định nghĩa hợp đồng số nhỏ hơn ở ngoài** là phần thiết kế; việc sử dụng `Comparator.comparingInt` hiện thực trực tiếp hợp đồng đó.

### 7.2. Vì sao phải dựng chain từ trong ra ngoài?

Sau khi đã sắp `Trace(10), Retry(20), Metric(30)`, vòng lặp đi **từ cuối danh sách về đầu**:
- Khởi đầu là `Target`.
- Bọc `Metric(Target)`.
- Bọc `Retry(Metric(Target))`.
- Bọc `Trace(Retry(Metric(Target)))`.

Kết quả là lời gọi `work.execute()` đi vào **Trace trước**. Nếu code lắp wrapper từ đầu tới cuối, phần cuối có thể thành lớp ngoài cùng và **đảo ngược ý nghĩa** của priority; phải test builder, không chỉ test comparator.

### 7.3. Vì sao Case 1 ghi Metric hai lần?

`Retry` ở ngoài `Metric`, nên mỗi lần `Retry` gọi `next.run()` đều đi vào `Metric`. Attempt 1 ném `TransientFailure`, `finally` của Metric vẫn in `METRIC end`; Retry bắt exception loại cho phép và thử lại. Attempt 2 thành công, Metric chạy thêm một lần.

Như vậy một logical operation thành công có thể tạo:
- **Hai lần đo attempt**.
- **Một lần return bình thường** ở Trace.
- **Một lần failure nội bộ** đã được Retry xử lý.

Nếu metric “số lỗi nghiệp vụ cuối” được tăng ở Metric theo attempt đầu, dashboard có thể báo một failure attempt dù caller nhận kết quả OK. Điều đó không sai nếu metric đặt tên theo **attempt**, nhưng sai nếu được quảng cáo là failure của logical call.

### 7.4. Vì sao Case 2 chỉ ghi Metric một lần?

Metric ở ngoài Retry. Nó gọi `next.run()` một lần, nhưng continuation đó là **Retry**; Retry tự gọi target hai lần. Vì thế Metric mở một scope trước Retry và đóng scope sau khi Retry đã kết thúc thành công.

Đó là phạm vi một logical call. Nếu đo thời gian thật, nó có thể bao gồm cả backoff, queueing và những đoạn bên trong Retry. Một metric per-attempt được đặt trong Retry có phạm vi khác; cần định nghĩa tên và histogram rõ ràng.

### 7.5. Vì sao `TRACE return OK` chỉ xuất hiện một lần mỗi case?

Trace nằm ngoài cả Metric và Retry. Nó chỉ quan sát kết quả cuối của `next.run()`. Retry đã xử lý lỗi tạm thời của attempt 1 rồi cuối cùng trả OK; Trace không tự biết đã có một failure nội bộ trừ khi có thông tin attempt khác.

Tương tự, nếu Retry hết attempts và ném lại, Trace có thể in `TRACE throw TransientFailure` theo branch trong code. Một advice bên ngoài quan sát **kết cục sau khi advice bên trong đã áp dụng chính sách**.

### 7.6. Vì sao duplicate priority bị từ chối?

`compose` tạo `HashSet<Integer>` để kiểm tra trùng sau khi sort. Nếu hai Stage cùng priority, chương trình ném `IllegalArgumentException` thay vì sử dụng thứ tự phần tử hoặc tính ổn định của sort như một tie-break ngầm.

Không phải mọi hệ thống **bắt buộc** cấm tie. Một thiết kế khác có thể có secondary key tường minh như phase, tên định danh bất biến hoặc quan hệ `before/after`. Nhưng nếu cặp advice có quan hệ nghiệp vụ quan trọng, **từ chối cấu hình thiếu thứ tự** thường an toàn hơn việc vô tình đổi semantics sau một refactor.

### 7.7. Giới hạn có chủ đích của chương trình

- Đây là interceptor chain viết bằng Java thuần, **không dệt bytecode** và không có pointcut DSL.
- Target chỉ có một method; các lớp `Stage` đều áp dụng cho method ấy, không có filtering phức tạp.
- Retry chỉ bắt một exception type cụ thể và chạy hai attempts, không có backoff, timeout hay idempotency key.
- `WorkTarget` được tạo mới cho từng case nên attempt count mỗi case bắt đầu lại từ 1.
- `METRIC begin/end` minh họa phạm vi, không đo duration thực.
- Không có concurrency hoặc async trong ví dụ; phần kiểm thử nâng cao cần bổ sung các trường hợp đó.
- Không suy từ thứ tự trong ví dụ rằng một engine khác có cùng cách hiểu số priority.

## 8. Thiết kế order cho retry, tracing và metrics

### 8.1. Hai cấp quan sát nên được tách tên

Nhiều hệ thống cần **cả hai** loại số liệu:

~~~text
TraceTotal(
    LogicalMetrics(
        Retry(
            AttemptMetrics(
                Target
            )
        )
    )
)
~~~

Ví dụ:
- `LogicalMetrics`: một lần đo cho một logical request, bao cả retry.
- `AttemptMetrics`: một lần đo cho mỗi attempt mà Retry thực hiện.
- `TraceTotal`: trace span của toàn boundary đang định nghĩa.

Một công cụ AOP có thể biểu diễn hai metrics bằng hai advice instances hoặc một hệ thống tracing/metric chuyên dụng. Điều quan trọng không phải số object aspect mà là **phạm vi mỗi sự kiện**.

### 8.2. Trong retry có thể có nhiều tầng advice khác

Nếu Retry bao ngoài `AuditAttempt` hoặc một metric per-attempt, audit/metric có thể chạy nhiều lần. Nếu nó bao ngoài transaction scope, mỗi attempt có thể nhận một transaction riêng, **nếu** cơ chế transaction và retry được thiết kế như vậy.

Đừng mặc định thứ tự nesting tạo ra semantics commit/rollback mong muốn: transaction resource, propagation, isolation và external side effects có hợp đồng độc lập. Test phải chứng minh actual commit và effect count, không chỉ thứ tự advice.

### 8.3. Một retry lỗi tạm thời không nhất thiết an toàn

Ví dụ yêu cầu gửi tiền tới hệ thống ngoài. Attempt 1 có thể đã commit nhưng response bị mất; Retry thực hiện attempt 2 sẽ nhân side effect. Dù advice order hoàn toàn đúng, hệ thống vẫn sai nếu thiếu idempotency key, retry policy và khả năng kiểm tra trạng thái.

**Ordering đúng là cần thiết nhưng không đủ cho correctness.**

## 9. Cache và authorization: thứ tự có thể trở thành ranh giới bảo mật

Giả sử Cache có thể return sớm mà không gọi `proceed()`.

**Thiết kế 1:**

~~~text
Authorization(
    Cache(
        Target
    )
)
~~~

Nếu mọi invocation cần kiểm tra quyền được bảo đảm đi qua wrapper Authorization, quyền được kiểm tra trước cả cache hit. Nhưng điều này vẫn không bảo đảm tất cả đường truy cập ứng dụng đều đi qua wrapper; phải bảo vệ trusted boundary.

**Thiết kế 2:**

~~~text
Cache(
    Authorization(
        Target
    )
)
~~~

Ở nhánh cache hit, Cache có thể return ngay và **bỏ qua Authorization bên trong**. Nếu quyền được xác định theo user/tenant và giá trị cache được chia không đúng, có nguy cơ trả dữ liệu không được phép.

### 9.1. Trường hợp caching có thể đặt ngoài authorization?

Trong một hệ thống được thiết kế chặt chẽ, dữ liệu công khai hoặc cache gắn với một boundary đã được xác thực và khóa cache chứa đúng phân vùng quyền có thể tạo một thiết kế khác. Không khẳng định mọi Cache phải luôn ở trong mọi Auth advice. Câu hỏi đúng là:

- Auth được bảo đảm tại boundary nào?
- Cache có chứa dữ liệu người dùng hoặc tenant không?
- Cache hit có được phép bỏ qua target và inner advice không?
- Có kiểm tra quyền trên mọi đường vào, kể cả direct target/proxy bypass?
- Có thay đổi quyền sau khi cache entry được tạo không?

Thứ tự explicit giúp review, nhưng **policy security bắt buộc phải được chứng minh ở trust boundary**, không chỉ bằng sơ đồ nesting.

### 9.2. Metric cache hit khác metric target execution

~~~text
RequestMetrics(
    Cache(
        TargetMetrics(
            Target
        )
    )
)
~~~

Trong mô hình này:
- `RequestMetrics` đếm cả cache hit và cache miss.
- `TargetMetrics` chỉ chạy khi Cache tiếp tục vào Target.
- Một lần cache hit có thể có 1 request nhưng 0 target executions.

Nếu đảo vị trí hai metric, các dashboard sẽ có ý nghĩa khác. Không đặt cùng một nhãn “requests” cho những phạm vi không tương đương.

## 10. Transaction, audit và thời điểm “thành công”

Transaction và audit là ví dụ cho thấy thứ tự wrapper có thể cần nhưng chưa đủ.

~~~text
Audit(
    Transaction(
        Target
    )
)
~~~

Nếu `Transaction` chỉ return sau khi commit thành công, Audit ở ngoài có thể quan sát outcome sau commit. Nhưng có mô hình transaction mà commit xảy ra ở nơi khác; có async API trả future trước commit; có chuyện audit sink không lưu bền cùng transaction. **Không thể lấy dòng log “after Transaction” làm bằng chứng commit đã hoàn tất** khi chưa xác nhận hợp đồng.

Ngược lại:

~~~text
Transaction(
    Audit(
        Target
    )
)
~~~

Audit ở trong transaction boundary có thể ghi “success” khi Target return, trước khi transaction commit thất bại. Nếu audit được ghi ra hệ thống ngoài giao dịch, kết quả audit và dữ liệu bền vững có thể bất nhất.

### 10.1. Phải đặt tên sự kiện muốn audit

Có nhiều mốc khác nhau:
1. Request được nhận.
2. Authorization được kiểm tra.
3. Target body đã chạy.
4. Transaction chuẩn bị commit.
5. Commit đã hoàn tất theo hệ lưu trữ.
6. Event đã được phát/lưu bền.
7. Caller nhận kết quả.
8. Task bất đồng bộ cuối cùng completed.

Với hệ thống phức tạp, các mốc có thể tách nhau đáng kể. Xác định **audit event** cần nói về mốc nào rồi đặt logic ở điểm có thể chứng minh mốc đó. Đôi khi cần transactional outbox, domain events hoặc transaction callbacks thay vì chỉ đảo priority advice.

### 10.2. Không tạo side effect tại một advice “before” chỉ vì nó đứng đầu

Một advice before có thể chạy trước khi Target bị từ chối bởi một advice trong. Ghi “thanh toán thành công” ở before là sai tên event. Advice before có thể ghi “bắt đầu attempt” hoặc “request được nhận”, nhưng không được tự suy thành kết quả cuối.

### 10.3. Retry và transaction

Một policy cần mỗi attempt có một transaction riêng phải có **retry bao ngoài transaction boundary** theo cấu trúc phù hợp:

~~~text
Retry(
    Transaction(
        Target
    )
)
~~~

Nhưng điều đó chỉ diễn đạt phạm vi wrapper; transaction thật có mở/đóng mỗi attempt hay không phụ thuộc implementation, propagation và database behavior.

Nếu:

~~~text
Transaction(
    Retry(
        Target
    )
)
~~~

thì nhiều attempts có thể diễn ra trong cùng transaction context; điều này có thể ảnh hưởng rollback/lock/isolation. Đừng cho rằng hai cấu trúc tương đương chỉ vì caller cuối cùng cùng nhận OK.

## 11. Xử lý ngoại lệ: advice nào thấy lỗi nào?

Giả sử `A(B(Target))`.

- Target ném `E`.
- B bắt E, rồi **ném lại E** → A có thể thấy E.
- B bắt E, rồi **ném E2** → A thấy E2.
- B bắt E, rồi **trả fallback** → A có thể thấy normal return.
- B `finally` tự ném F → F có thể thay thế E mà A nhìn thấy.
- B không gọi continuation → Target không chạy, kết quả phụ thuộc B.

Như vậy một thứ tự đã được khai báo không chỉ quyết định logging: nó có thể quyết định **exception type/cause** tới caller.

### 11.1. Best-effort telemetry

Nếu logging/metrics chỉ nhằm quan sát, thường cần bảo đảm lỗi telemetry không vô tình làm mất kết quả/exception của nghiệp vụ. Một `finally` ghi metric mà tự ném exception có thể **che lỗi gốc**. Cần có chính sách lỗi rõ cho instrumentation.

Không tự dùng `catch(Throwable)` rồi nuốt mọi lỗi: Java `Throwable` gồm các `Error` nghiêm trọng và có thể phá tính đúng đắn. Việc quan sát rồi ném lại nguyên lỗi khác với thay mọi lỗi bằng fallback.

### 11.2. After-throwing ở tầng ngoài không phải nhật ký mọi lỗi bên trong

Nếu Retry bắt `TransientFailure` ở attempt đầu và thành công attempt hai, Trace ở ngoài Retry thấy normal return. Nếu cần thống kê transient failures, phải ghi ở attempt boundary hoặc trong Retry, không mong after-throwing ở outer ghi những lỗi đã được xử lý.

### 11.3. Đừng đếm cùng lỗi nhiều lần

Một Throwable có thể đi qua ba advice nested; cả ba có thể log “failure”. Dashboard cần phân biệt:
- Failure **ở từng boundary**.
- Failure **của attempt**.
- Failure **của logical operation**.
- Failure **của transaction commit**.

Không thể cộng thẳng tất cả thành tổng số request thất bại.

## 12. Async: thứ tự advice không tự mở rộng thời gian sống

Method Java có thể trả `CompletionStage<T>` trước khi task hoàn tất. Xét:

~~~text
Trace(
    Retry(
        Target.fetchAsync()
    )
)
~~~

Nếu advice Trace đo tới lúc `proceed()` **trả future**, nó chỉ đo invocation/dispatch latency; không tự bao trọn việc future completed. Tương tự, một catch quanh `proceed()` không tự bắt lỗi future hoàn tất exceptionally **sau khi method return bình thường**.

### 12.1. Hai trục độc lập

- **Nesting precedence:** Trace nằm ngoài hay trong Retry?
- **Completion semantics:** thời điểm nào được xem là logical operation completed?

Thay priority không sửa nghĩa “method return stage” so với “task hoàn tất”. Cần hook theo completion/error/cancellation của abstraction phù hợp.

### 12.2. Original stage và dependent stage

Với `CompletionStage`, `whenComplete` tạo một dependent stage. Nếu around advice đính callback rồi trả **stage gốc**, caller vẫn giữ stage gốc; lỗi callback có thể xuất hiện ở dependent stage bị bỏ qua. Nếu advice trả **dependent stage**, lỗi instrumentation trong callback có thể tác động tới outcome caller.

Vì thế thứ tự giữa Trace, Retry và CompletionObserver cần xét cả:
- Stage nào được trả về?
- Completion callback có chạy trước hay sau callback khác?
- Có callback nào thay result/exception không?
- Context/ThreadLocal có được truyền đúng thread không?
- Cancellation/timeout có propagation xuống task thật không?

Không suy rằng source ordering của callback luôn xác định thứ tự callback runtime trên nhiều threads. Dùng scheduler/serialization hoặc explicit coordination nếu một quan hệ happens-before là bắt buộc.

### 12.3. Callback và context lifecycle

Một aspect tracing ngoài retry có thể muốn giữ trace span đến khi logical task completed. Nếu dùng `ThreadLocal` ở caller rồi đóng span trong `finally` khi method trả future, span có thể đóng quá sớm. Nhưng giữ ThreadLocal caller mở mãi tới completion cũng có thể rò context vào request kế tiếp của thread pool.

Cần chuyển **snapshot tối thiểu** theo task và mở/restore scope phù hợp khi callback chạy, không dựa vào ordering của advice để tự động truyền context xuyên async boundary.

## 13. Nhiều join points và lồng lời gọi: thứ tự ở đâu?

Một operation ngoài có thể gọi nhiều methods có aspect riêng:

~~~text
caller -> A.outer()
            |
            +-> B.inner()
            |
            +-> C.helper()
~~~

Ngoài **thứ tự advice trên cùng một join point**, còn có **thứ tự các method executions khác nhau**. Nếu A.outer gọi B.inner trước C.helper, log interleave là do control flow business, không chỉ precedence.

Một advice được chọn ở execution của `outer` có thể bao một call stack chứa nhiều join points. Khi B.inner xảy ra, advice của nó được lồng vào giữa advice outer đang hoạt động. Không nên so log toàn hệ thống rồi tưởng mọi aspect có một total order toàn cục.

### 13.1. Self-invocation và bypass proxy

Trong mô hình delegating proxy, target.outer gọi `this.inner()` có thể không qua proxy handler dành riêng cho inner. Cho dù đã khai precedence rõ `AspectX OUTER_THAN AspectY`, nếu inner handler không được gọi, thứ tự đó không có hiệu lực cho internal invocation.

Cần test call paths: proxy invocation, direct target, self-call, async callback và interface/class dispatch theo công cụ.

### 13.2. Pointcut runtime conditions

Nếu advice B chỉ áp khi argument hợp lệ, có những invocation A chạy mà B không chạy. Bản đồ thứ tự chỉ áp cho **tập advice thực sự được kích hoạt trên occurrence cụ thể**. Nếu aspect ngoài short-circuit, tập bên trong không được kích hoạt.

### 13.3. Nhiều targets và threads

Hai targets có thể chạy ở hai threads. Dù trong mỗi invocation thứ tự `Trace → Retry → Metric` là xác định, các dòng log giữa hai invocations **có thể xen kẽ**. Đừng đòi thứ tự tổng giữa hai request đồng thời trừ khi nghiệp vụ thật sự yêu cầu synchronization.

## 14. Kiểm thử ordering như một hợp đồng

### 14.1. Test sơ đồ thứ tự, không chỉ test “cả hai advice đã chạy”

Một test chỉ assert có log `TRACE` và `METRIC` không phát hiện Metric đã từ per-attempt chuyển thành per-logical. Cần kiểm tra **đúng thứ tự tương đối** và **số lần chạy**.

Ví dụ với target fail một lần rồi success:

| Cấu hình | Trace enter | Retry attempts | Metric begin/end | Kết quả caller |
| --- | --- | --- | --- | --- |
| `Trace(Retry(Metric(Target)))` | 1 lần. | 2 attempts. | 2 cặp. | OK. |
| `Trace(Metric(Retry(Target)))` | 1 lần. | 2 attempts. | 1 cặp. | OK. |

Một output giống nhau ở caller không chứng minh instrumentation đúng phạm vi.

### 14.2. Ma trận QA tối thiểu

| Ca | Điều kiểm tra |
| --- | --- |
| **Single aspect** | Khi chỉ còn một advice, không phụ thuộc thứ tự lớp không liên quan. |
| **Two aspects** | Before đi từ ngoài vào trong, after/finally unwind từ trong ra ngoài. |
| **Three around aspects** | Nesting đúng total/partial order được chọn. |
| **Duplicate priority** | Fail fast hoặc dùng tie-break được công bố, không im lặng. |
| **Cycle precedence** | Báo config error, không tạo ordering bất khả thi. |
| **Target success** | Result/call count chính xác. |
| **Target exception** | Các catch/finally theo chiều unwind, exception contract được giữ. |
| **Inner advice fallback** | Outer thấy normal return, không báo target failure thành final failure. |
| **Outer short-circuit** | Inner/target không chạy theo hợp đồng skip. |
| **Retry two attempts** | Metric per-attempt chạy 2, metric per-logical chạy 1. |
| **Cache hit** | Authorization/policy bắt buộc không bị bỏ qua; request/target metrics tách đúng. |
| **Transaction commit failure** | Audit không ghi success ở thời điểm chưa cam kết. |
| **Async failure** | Method return-handle khác terminal completion; observer nhìn đúng stage. |
| **Nested method calls** | Phân biệt nested join points với precedence trên cùng join point. |
| **Proxy bypass** | Không suy log từ handler khi caller gọi target trực tiếp. |
| **Concurrency** | Ordering trong từng invocation đúng, không giả định global log order. |
| **Upgrade** | Config/tập advisor thay đổi vẫn thỏa quan hệ đã khai. |

### 14.3. Unit test cho sorting algorithm

Nếu có composition builder, test ít nhất:

1. Input stages được viết **không theo thứ tự**; output vẫn theo priority.
2. Một stage ngoài có `try/finally`; lệnh `finally` chạy cuối phạm vi của nó.
3. Priority trùng sinh lỗi đúng nhãn.
4. Danh sách rỗng trả target nguyên semantics.
5. Một stage mới được chèn không làm đảo quan hệ bắt buộc giữa các stage cũ.
6. Vòng lặp wrap từ cuối về đầu đúng ý nghĩa “priority nhỏ = ngoài”.

Với đồ thị quan hệ:
- Test topological sort.
- Test cycle detection.
- Test node không tồn tại.
- Test partial order nhiều thứ tự hợp lệ.
- Nếu yêu cầu deterministic total order, test tie-break rõ ràng.

### 14.4. Integration test với engine thật

Một comparator tùy viết đúng chưa chứng minh engine AOP đã áp dụng thứ tự ấy. Cần chạy test với **đúng engine, runtime version, weaving/proxy config và artifact**; ghi sự kiện tại advice boundaries.

Nếu engine tự có precedence language hoặc annotation, kiểm tra:
- Priority được đọc ở nơi nào?
- Giá trị mặc định là gì?
- Thứ tự across-aspects và within-one-aspect có khác nhau không?
- Matching, classloader và creation có ảnh hưởng không?
- Có advisory warnings khi order mơ hồ không?

Không dùng tài liệu/logic của một engine để khẳng định engine khác giống nó.

## 15. Phát hiện thay đổi thứ tự ngoài ý muốn

### 15.1. Snapshot thứ tự hiệu lực

Trong môi trường có nhiều plugins/config modules, nên có một báo cáo ở startup hoặc build:

~~~text
Join-point group: service-operation
Effective outer-to-inner chain:
  TraceTotal
  Authorization
  Retry
  AttemptMetrics
  Target
~~~

Báo cáo cần bắt nguồn từ **kết quả config thực tế**, không chỉ liệt kê tên aspect tìm thấy trong source. Nếu pointcut là động, mô tả những nhóm join point đại diện và xác minh runtime.

### 15.2. Diff khi thêm một aspect mới

Một aspect mới có thể:
- Nằm ngoài Retry nên chỉ chạy một lần.
- Nằm trong Retry nên chạy mỗi attempt.
- Short-circuit trước Authorization.
- Bắt và chuyển lỗi trước Audit.
- Đóng span trước completion.
- Lấy lock trước một wrapper khác và tạo deadlock.

Do vậy review một aspect mới phải xem **điều kiện matching + precedence + dữ liệu/side effects** chứ không chỉ nội dung advice.

### 15.3. Đảm bảo ổn định qua build/refactor

Các dấu hiệu cần cảnh giác:
- Thêm module khiến classpath scan khác.
- Đổi tên/package aspect.
- Nâng phiên bản compiler/bytecode weaver.
- Thay cách dựng proxy/interceptor chain.
- Chuyển từ một collection có order sang collection không có order.
- Thêm annotation thứ tự mà không xử lý tie.
- Dời method từ component A sang B làm call path đổi.

Một suite test ordering như mục 14 giúp phát hiện thay đổi semantics trước production.

## 16. Sai lầm phổ biến và cách sửa

**“Aspect A được khai báo trước nên advice A luôn chạy trước.”** Không có hợp đồng chung. Dùng precedence tường minh và kiểm chứng.

**“Số priority càng nhỏ thì advice luôn chạy trước ở mọi công cụ.”** Chỉ đúng nếu engine/chính sách bạn chọn có định nghĩa như vậy. Cần đọc contract.

**“A ưu tiên trước B nghĩa là mọi log A đều xuất hiện trước mọi log B.”** Sai với wrapper lồng: `A.before` trước `B.before`, nhưng `A.after` sau `B.after`.

**“Nếu cả hai advice chạy thì thứ tự không quan trọng.”** Sai: cache, retry, auth, metrics và audit có thể khác semantics theo thứ tự.

**“Đảo order giữa Retry và Metrics chỉ đổi số dòng log.”** Không chỉ vậy. Nó đổi đơn vị đo và số lần observer được gọi.

**“Có trace outer nghĩa là mọi exception bên trong đều được trace outer đánh dấu failure.”** Không: retry/fallback có thể xử lý lỗi rồi trả bình thường.

**“Thứ tự wrapper bảo đảm transaction đã commit khi method return.”** Không mặc định; phải xác minh transaction boundary và async/commit lifecycle.

**“Topological sort chỉ tạo một chuỗi duy nhất.”** Không nếu partial order để lại những cặp độc lập.

**“Cycle trong precedence có thể được xử lý bằng chọn aspect khởi tạo trước.”** Không; cycle mâu thuẫn, cần báo lỗi cấu hình.

**“HashMap iteration đang ổn định nên dùng để tạo advice order.”** Không nên vì không có hợp đồng thứ tự phù hợp.

**“Dùng tên class làm tie-break luôn vô hại.”** Không nếu tên class thay đổi qua refactor; cần xác định tie-break có ý nghĩa và được test.

**“Chỉ cần sửa priority để bắt được self-invocation.”** Không nếu internal call bypass proxy/handler.

**“Priority giải quyết quyền truy cập bắt buộc.”** Không thể bảo đảm nếu có đường bypass hoặc short-circuit khác; cần security invariant ở trusted boundary.

**“AOP engine lúc nào cũng hỗ trợ gọi `proceed` nhiều lần để retry.”** Không. Cần xác minh capability và semantics.

**“Một lời gọi async return stage thành công nghĩa là logical task thành công.”** Sai: future có thể fail về sau.

**“Unit test sorting đủ, không cần test engine/runtime thật.”** Chưa đủ; phải test cấu hình thực sự được áp dụng ở join point.

## 17. Bài tập vận dụng

### Bài 1 — Hai quanh advice

`A(B(Target))`, cả hai có before/after, Target trả bình thường. Viết thứ tự bốn lời ghi.

**Đáp án:** `A.before`, `B.before`, `B.after`, `A.after`.

### Bài 2 — Retry và Metrics

Một target thất bại lần 1 và thành công lần 2. `Retry(Metric(Target))` có bao nhiêu lượt Metric nếu Retry gọi tiếp lại đúng hai lần?

**Đáp án:** Hai lượt Metric (mỗi attempt). `Metric(Retry(Target))` thường chỉ có một lượt Metric bao ngoài logical operation.

### Bài 3 — Nhánh cache hit

`Cache(Authorization(Target))`, Cache return ngay khi hit. Authorization bên trong có chạy không?

**Đáp án:** Không ở nhánh cache return sớm không gọi continuation. Nếu việc kiểm tra quyền bắt buộc, cần đổi kiến trúc/boundary để không có đường bỏ qua, không chỉ tin vào thứ tự.

### Bài 4 — Nhiều lỗi trong một request

Retry xử lý hai transient failures rồi success. Trace ngoài chỉ ghi success. Có nghĩa request chưa từng có attempt failure?

**Đáp án:** Không. Trace ngoài ghi final outcome; cần metric/log ở attempt boundary để thấy failures bên trong.

### Bài 5 — Cycle

Có yêu cầu A ngoài B, B ngoài C, C ngoài A. Có thể sắp một chuỗi tuyến tính thỏa cả ba không?

**Đáp án:** Không. Cần sửa ràng buộc và fail fast.

### Bài 6 — Source order

Aspect X đứng đầu trong file; Y đứng sau. Trong runtime thấy Y.before chạy trước X.before. Đây chắc chắn là bug engine?

**Đáp án:** Không thể kết luận. Source declaration order không nhất thiết là precedence contract. Xem cấu hình và tài liệu engine.

### Bài 7 — Transaction và audit

Một advice Audit ở ngoài Transaction, nhưng target trả future chưa hoàn tất còn commit diễn ra sau. Audit thấy method return bình thường có được kết luận đã commit không?

**Đáp án:** Không. Phải xác định commit/completion event thật; ordering của method invocation không tự bao lifecycle async.

### Bài 8 — Concurrent invocations

Hai threads chạy cùng chuỗi `Trace(Retry(Target))`, log xen kẽ. Việc dòng TRACE của request B xuất hiện giữa hai attempts của A có chứng minh precedence sai?

**Đáp án:** Không. Ordering được bảo đảm **trong phạm vi từng invocation**, không mặc nhiên sắp mọi request theo một thứ tự toàn cục.

### Bài 9 — Trùng priority

Hai interceptors cùng số priority 20 và có thứ tự business bắt buộc. Nên làm gì?

**Đáp án:** Định nghĩa secondary precedence tường minh hoặc báo lỗi cấu hình; không dựa vào thứ tự quét/discovery tình cờ.

### Bài 10 — Refactor gọi trực tiếp target

Một test ordering pass khi gọi qua proxy, nhưng một code path mới gọi target thẳng. Sửa priority có khắc phục được không?

**Đáp án:** Không. Phải sửa coverage/wiring hoặc dùng mechanism có hook phù hợp rồi test call path mới.

### Bài 11 — Which metric is which?

`RequestMetric(Cache(TargetMetric(Target)))`. Một cache hit tạo bao nhiêu RequestMetric, TargetMetric nếu mỗi wrapper gọi một lần?

**Đáp án:** RequestMetric một lần, TargetMetric không chạy nếu Cache return mà không gọi continuation.

### Bài 12 — Lỗi callback đo lường

Một advice trả `stage.whenComplete(callback)`, callback đôi lúc ném lỗi. Chỉ đảo priority callback với Trace có giải quyết tính trong suốt không?

**Đáp án:** Không. Phải xét stage nào được trả ra, lỗi callback được xử lý thế nào và contract completion; ordering không thay thế error handling.

## 18. Checklist thiết kế thứ tự advice dùng trong review

1. **Boundary:** Advice áp vào join point nào, qua proxy hay weaving, có bypass không?
2. **Concern:** Advice chỉ quan sát hay có thể skip, retry, mutate result hoặc exception?
3. **Scope đo:** Logical operation, target invocation hay attempt?
4. **Outer/inner:** Đã biểu diễn chính xác lớp ngoài và lớp trong chưa?
5. **Before/after:** Đã hiểu unwind order trên return, throw, finally chưa?
6. **Short-circuit:** Advice nào có thể không gọi `proceed`; chính sách quan trọng nào bị bỏ qua?
7. **Retry:** Ai được gọi nhiều lần; target idempotent và timeout tổng có rõ không?
8. **Cache:** Hit/miss tác động tới Authorization, metrics và target execution thế nào?
9. **Transaction:** Commit/rollback xảy ra ở đâu, có thuộc async lifecycle không?
10. **Audit:** “Success” mang nghĩa method return, commit hay task completion?
11. **Exceptions:** Advice trong có thể catch/transform/swallow lỗi không?
12. **Priorities:** Hướng so sánh số priority có rõ, có collision/cycle không?
13. **Partial order:** Những cặp nào thực sự cần precedence, cặp nào độc lập?
14. **Tie handling:** Có fail-fast hoặc deterministic explicit tie-break không?
15. **Construction:** Builder có đảo wrapper order ngoài ý muốn không?
16. **Runtime:** Engine thật có áp ordering đã khai, kể cả after advice và call paths không?
17. **Async:** Observer nào nhìn terminal completion và stage gốc/phụ thuộc?
18. **Concurrency:** Có yêu cầu ordering trong một call hay across requests? State có thread-safe?
19. **Versioning:** Thêm module/refactor/upgrade có đổi effective chain không?
20. **Evidence:** Có positive/negative tests cùng artifact và báo cáo effective order không?
21. **Security:** Critical invariants có nằm ở trusted boundary đáng tin, không chỉ proxy priority?
22. **Operations:** Có metrics/trace names phản ánh đúng attempt vs logical success/failure?

## Kết luận

Khi nhiều aspect cùng chọn một join point, **thứ tự là một phần của ngữ nghĩa hệ thống**, không phải chi tiết trang trí. Một advice ngoài sẽ thực hiện phần “before” trước advice trong và phần “after/finally” sau advice trong; short-circuit có thể bỏ qua phần bên trong; retry có thể làm advice bên trong chạy nhiều lần; xử lý lỗi của tầng trong có thể thay đổi outcome mà tầng ngoài nhìn thấy.

Thiết kế đáng tin cậy bắt đầu bằng **quy tắc nghiệp vụ và quan sát có thể kiểm chứng**: ai phải nằm ngoài ai, ai được chạy theo attempt, ai phải chạy cho logical operation, policy nào không được skip, và thế nào là completion thật. Chỉ sau đó mới khai precedence bằng **danh sách, priority hoặc đồ thị ràng buộc tường minh**, với chính sách xử lý tie/cycle rõ. Xác nhận bằng test ở cả lớp composition và AOP engine/runtime thực tế; không dựa vào tên class, source order, reflection, classloader hoặc kết quả tình cờ của một lần chạy. Đặc biệt, một ordering đúng không thay thế việc chứng minh **độ phủ interception, idempotency, transaction consistency và async completion semantics**.
