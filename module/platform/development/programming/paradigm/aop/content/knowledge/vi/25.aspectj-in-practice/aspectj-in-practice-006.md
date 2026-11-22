# Advice before, after, around và lời gọi proceed: minh họa AOP bằng AspectJ

## 1. Mục tiêu học tập

Trong lập trình hướng khía cạnh (Aspect-Oriented Programming, AOP), một mối quan tâm cắt ngang như ghi log, đo thời gian, kiểm soát quyền hoặc thu thập metric thường xuất hiện ở nhiều vị trí khác nhau trong mã nghiệp vụ. **Advice** là hành vi mà aspect đưa vào những **join point** được chọn bởi một **pointcut**.

Bốn kiểu advice thường gặp là:

- **Before:** chạy trước join point được chọn.
- **After:** chạy sau join point; trong AspectJ cần phân biệt after kiểu finally, after returning và after throwing.
- **Around:** bao quanh join point, có thể thực thi trước và sau, quan sát hoặc thay đổi kết quả, thậm chí quyết định có tiếp tục join point hay không.
- **Proceed:** cơ chế riêng trong around advice để tiếp tục phần thực thi nằm phía trong advice theo chuỗi được dệt.

Mục tiêu của bài không chỉ là nhớ cú pháp, mà còn hiểu **điều gì được đảm bảo, điều gì có thể thay đổi, khi nào phải gọi proceed và vì sao việc bỏ qua/nhân đôi proceed có thể phá hợp đồng nghiệp vụ**.

Các ví dụ sử dụng **AspectJ** như một cách minh họa cụ thể cho AOP cơ bản và nâng cao. Những khái niệm advice, join point và pointcut có ý nghĩa chung trong AOP, nhưng cú pháp và tập join point phụ thuộc cơ chế triển khai.

## 2. Ba thành phần cần hiểu trước khi đọc code

**Join point** là một điểm xác định trong quá trình thực thi mà cơ chế AOP nhận biết được: ví dụ thực thi phương thức, lời gọi phương thức, tạo đối tượng, truy cập trường hoặc xử lý ngoại lệ (tùy khả năng của công nghệ AOP).

**Pointcut** là điều kiện chọn những join point cần áp dụng advice. Một pointcut đơn giản của AspectJ:

~~~java
// Ví dụ một biểu thức pointcut, không phải chương trình Java độc lập.
execution(String Work.transform(String))
~~~

Biểu thức trên nhắm tới **lần thực thi** phương thức Work.transform nhận String và trả String. Đây không phải một lệnh Java thông thường; nó là ngôn ngữ pointcut của AspectJ. Cùng một phương thức có thể được gọi từ nhiều nơi, trong khi join point execution thuộc về việc thực thi thân phương thức.

**Advice** là logic được dệt vào những điểm phù hợp. Trong AspectJ kiểu code-style, aspect được khai báo trong tệp nguồn có cú pháp riêng, chẳng hạn:

~~~java
// Đây là đoạn cú pháp AspectJ trong tệp .aj, không biên dịch độc lập bằng javac.
public aspect TraceAspect {
    before(): execution(void Work.open()) {
        System.out.println("BEFORE open");
    }
}
~~~

**Weaving** là quá trình tích hợp aspect vào chương trình để khi join point diễn ra, advice được gọi đúng cách. AspectJ có thể dệt ở thời điểm biên dịch, sau khi đã biên dịch hoặc trong lúc nạp lớp, tùy cấu hình. Ở ví dụ chính, ta sử dụng **compile-time weaving với trình biên dịch ajc**.

### Phân biệt execution với call

Hai pointcut dễ bị nhầm:

~~~java
// Cú pháp pointcut AspectJ, không phải Java độc lập.
execution(* Work.transform(..))
call(* Work.transform(..))
~~~

- execution nhắm vào việc **thực thi thân phương thức**, nên có thể bao quát những người gọi khác nhau khi code đã được dệt phù hợp.
- call nhắm vào **vị trí phát sinh lời gọi**, tức các call site; phạm vi phụ thuộc các call site có được dệt không.
- Một lời gọi từ mã không được dệt có thể không kích hoạt call advice; điều đó không có nghĩa execution advice trên phần thân đã được dệt cũng bị bỏ qua.
- Một lớp chỉ đơn thuần tham chiếu hoặc nhận Method object chưa chắc tạo ra một join point call hay execution tương ứng.

Khi đánh giá advice có bao phủ hành vi cần kiểm soát hay không, phải xác định rõ **loại join point và phạm vi weaving**.

## 3. Before advice: chạy trước, nhưng không tự xử lý kết quả sau đó

Before advice thực thi trước phần join point mà nó bao quanh theo thứ tự advice đang có hiệu lực:

~~~java
// Cú pháp AspectJ trong tệp .aj.
before(): execution(void Work.open()) {
    System.out.println("BEFORE open");
}
~~~

Nếu Work.open bắt đầu bằng việc in “WORK open”, ta nhận được “BEFORE open” trước “WORK open”, giả sử không có advice khác can thiệp thứ tự.

Công dụng thích hợp:

- Ghi một event bắt đầu, lấy timestamp đầu vào.
- Kiểm tra điều kiện truy cập trước khi thao tác nhạy cảm xảy ra.
- Khởi tạo ngữ cảnh hoặc kiểm tra argument theo chính sách.
- Đếm số lần join point được đi vào.

Giới hạn:

- Before advice **không nắm được giá trị trả về** hay ngoại lệ sẽ phát sinh sau khi target chạy.
- Before không tự quyết định chạy tiếp hay không như around với proceed. Tuy nhiên, nếu chính before advice ném ngoại lệ, luồng thực thi có thể bị ngắt **trước target**, nên advice không được coi là không có tác dụng điều khiển.
- Nếu logger trong before ném exception, một lời gọi vốn hợp lệ có thể bị chặn. Với logging best effort, cần cô lập lỗi logging; với kiểm soát truy cập, từ chối có chủ đích là hành vi theo chính sách.
- Nếu có nhiều aspect, thứ tự giữa các before advice cần hiểu theo quy tắc precedence, không dựa vào thứ tự hiển thị trong file bất kỳ.

Một before advice rất phù hợp để xác thực quyền **trước** khi gọi target, nhưng chỉ khi pointcut thật sự bao phủ mọi đường đi cần bảo vệ.

## 4. After advice: ba biến thể khác ngữ nghĩa

Trong AspectJ, từ “after” không chỉ là một loại duy nhất. Cần nắm ba trường hợp.

### 4.1. after() — ngữ nghĩa finally

~~~java
// Cú pháp AspectJ.
after(): execution(void Work.finish()) {
    System.out.println("AFTER finally");
}
~~~

After kiểu này chạy khi join point kết thúc theo đường bình thường **hoặc** ném ngoại lệ, khi control flow đã đi tới advice tương ứng. Nó tương tự vùng finally quanh phần join point.

Ứng dụng: giải phóng scope hoặc ghi nhận rằng lời gọi đã kết thúc, bất kể thành công hay thất bại. Hạn chế: chính advice cũng có thể ném lỗi và che kết quả/ngoại lệ nghiệp vụ; cleanup cần được thiết kế an toàn và phải bảo toàn chính sách lỗi.

Không nên tự động viết “operation succeeded” trong after kiểu finally: target có thể kết thúc bằng ngoại lệ.

### 4.2. after() returning — chỉ khi hoàn tất bình thường

~~~java
// Cú pháp AspectJ.
after() returning(int value): execution(int Work.count()) {
    System.out.println("AFTER returning: " + value);
}
~~~

Biến thể này chỉ chạy khi join point kết thúc **bình thường**. Có thể bind giá trị trả về để ghi nhận, đo đạc hoặc kiểm tra theo yêu cầu.

Một số lưu ý:

- Giá trị trả về của target được quan sát qua biến binding, không nên suy luận advice này có quyền tùy ý thay kết quả target giống around.
- Với phương thức void, after returning vẫn có thể dùng mà không bind giá trị trả về.
- Nếu phương thức trả về CompletableFuture đang pending, đó vẫn là một **lần trả về bình thường của phương thức**, không đồng nghĩa operation bất đồng bộ đã hoàn thành thành công.
- Chính after returning advice có thể ném exception và làm thay đổi những gì caller nhận được. Bảo toàn ngữ nghĩa là trách nhiệm của aspect.

### 4.3. after() throwing — chỉ khi join point ném ngoại lệ

~~~java
// Cú pháp AspectJ.
after() throwing(IllegalArgumentException error):
        execution(void Work.fail()) {
    System.out.println("AFTER throwing: " + error.getMessage());
}
~~~

Biến thể này được chọn khi join point kết thúc bằng ngoại lệ tương thích với kiểu binding, ở đây là IllegalArgumentException. Nếu target ném ngoại lệ loại khác không phù hợp, advice với binding này không chạy. Có thể dùng kiểu Throwable để nhận phạm vi rộng hơn nhưng phải xử lý đúng lỗi nghiệp vụ và lỗi nghiêm trọng.

Ứng dụng: ghi nguyên nhân thất bại đồng bộ, thống kê lỗi theo loại hoặc gắn thêm ngữ cảnh vận hành. Nếu chỉ cần quan sát, tốt nhất **không thay ngoại lệ gốc**. Nếu chính logger trong after throwing ném ngoại lệ khác, caller có thể mất nguyên nhân ban đầu.

**After throwing tại method execution không tự bắt lỗi phát sinh muộn trong callback hoặc future.** Lỗi đó cần hook hoặc pointcut tại ranh giới tương ứng.

### Bảng so sánh ngắn

| Kiểu advice | Điều kiện chạy | Có thể biết gì tại thời điểm đó? | Lỗi thường gặp |
| --- | --- | --- | --- |
| before | Trước phần join point tương ứng | Tham số và ngữ cảnh đầu vào | Logger lỗi làm chặn target |
| after() | Join point kết thúc, dù normal/exceptional | Đã rời khỏi lời gọi đồng bộ | Ghi nhãn success dù vừa thất bại |
| after() returning | Join point trả về bình thường | Có thể bind return value | Nhầm trả future với thành công nghiệp vụ |
| after() throwing | Join point thoát ra bằng ngoại lệ phù hợp | Có thể bind throwable | Logger che ngoại lệ gốc |
| around | Bao quanh phần tiếp tục khi advice chạy | Có thể quan sát trước/sau, return, throw | Không proceed, proceed nhiều lần, thay contract |

## 5. Around advice và proceed: công cụ mạnh nhất, cũng dễ gây sai nhất

Around advice thay một đoạn luồng điều khiển bằng mã do aspect định nghĩa. Nó thường có mẫu:

~~~java
// Fragment cú pháp AspectJ, không phải Java độc lập.
String around(): execution(String Work.transform(String)) {
    System.out.println("AROUND enter");
    String result = proceed();
    System.out.println("AROUND exit");
    return result;
}
~~~

Khi join point Work.transform thực thi:

1. Around advice được vào.
2. Dòng “AROUND enter” được in.
3. **proceed()** tiếp tục phần thực thi bên trong advice: thường dẫn đến target, nhưng có thể đi qua những advice có precedence thấp hơn.
4. Sau khi phần thực thi đó trả về, advice in “AROUND exit”.
5. Advice trả giá trị cho caller.

Phân biệt quan trọng: **proceed không có nghĩa “gọi trực tiếp target và bỏ qua mọi advice khác”**. Nó đi tiếp qua chuỗi thực thi được dệt, theo thứ tự precedence. Nếu một around advice nằm bên trong trả kết quả mà không gọi proceed, target có thể không được chạy.

### 5.1. Bỏ qua proceed

~~~java
// Fragment minh họa; chỉ hợp lệ khi chính sách cho phép short-circuit.
String around(): execution(String Work.transform(String)) {
    return "CACHED"; // Không gọi proceed().
}
~~~

Cơ chế này cho phép caching, từ chối thực thi, fallback hoặc trả response tổng hợp. Nhưng nếu target có side effect, việc bỏ qua nó có thể là thay đổi nghiệp vụ nghiêm trọng.

Các câu hỏi cần trả lời trước khi short-circuit:

- Target có phải chạy ít nhất một lần theo contract không?
- Trạng thái cache có đúng với context/người dùng hiện tại không?
- Các advice bên trong có còn được chạy khi proceed bị bỏ qua không?
- Có cần audit bắt buộc trước khi trả kết quả thay thế không?
- Với security advice, bỏ qua proceed là deny có chủ đích hay vô tình?
- Giá trị trả về có hợp lệ về kiểu, nullability và ngữ nghĩa không?

### 5.2. Gọi proceed đúng một lần

Nếu mục tiêu chỉ là quan sát, một around advice thông thường nên gọi proceed **chính xác một lần**, giữ nguyên return/exception, và không tạo side effect khác ảnh hưởng caller:

~~~java
// Fragment cú pháp AspectJ minh họa; recordStart/recordEnd giả định đã có.
String around(): execution(String Work.transform(String)) {
    recordStart();
    try {
        return proceed();
    } finally {
        recordEnd();
    }
}
~~~

Cần bảo đảm recordStart/recordEnd không ném lỗi ngoài chính sách; nếu recordEnd ném lỗi trong finally, nó có thể che giá trị trả về hoặc exception của target. Đây là lý do “gọi proceed đúng một lần” chỉ là **một phần** của tính minh bạch.

### 5.3. Gọi proceed nhiều lần

~~~java
// Fragment minh họa cơ chế retry; có thể nguy hiểm với side effect.
String around(): execution(String Work.transform(String)) {
    try {
        return proceed();
    } catch (TransientFailure failure) {
        return proceed();
    }
}
~~~

Trong đoạn trên, TransientFailure là một kiểu exception minh họa do ứng dụng định nghĩa. Nếu lần gọi đầu đã ghi dữ liệu rồi ném lỗi, lần thứ hai có thể ghi lại. Retry cần giới hạn attempt, thời gian, điều kiện lỗi, idempotency, và chính sách xử lý interruption/cancellation.

Một aspect dùng cho tracing thuần túy không nên vô tình gọi proceed hai lần. Không nên giả định proceed được chạy một lần mặc định: **chỉ khi code thực sự gọi nó**, dòng thực thi phía trong mới tiếp tục.

### 5.4. Proceed ném ngoại lệ

Nếu phần tiếp tục ném ngoại lệ, các dòng sau proceed trong cùng khối try thông thường không chạy:

~~~java
// Fragment minh họa, operation được định nghĩa trong ứng dụng.
Object around(): execution(* Work.risky(..)) {
    System.out.println("before proceed");
    try {
        return proceed();
    } finally {
        System.out.println("after proceed, even on throw");
    }
}
~~~

Phần finally chạy khi proceed trả về hoặc ném exception thông thường. Tuy nhiên, nếu dùng logging có thể ném trong finally, lỗi mới vẫn có thể che lỗi target. Với exception transformation, làm rõ đây là chính sách nghiệp vụ chứ không phải tác dụng phụ của logging.

## 6. Ví dụ hoàn chỉnh Java 17+ với AspectJ

Ví dụ sau tách mỗi dạng advice sang một method khác nhau, giúp **thứ tự stdout xác định** mà không phải suy đoán precedence của nhiều advice cùng khớp một join point.

Có hai tệp: Main.java là Java thuần, TraceAspect.aj chứa mã AspectJ. Phải dùng **trình biên dịch AspectJ ajc** để dệt aspect; chạy javac riêng trên Main.java sẽ không thực hiện weaving.

### 6.1. Tệp Main.java

~~~java
import java.util.Locale;

class Work {
    void open() {
        System.out.println("WORK open");
    }

    void finish() {
        System.out.println("WORK finish");
    }

    int count() {
        System.out.println("WORK count");
        return 3;
    }

    String transform(String input) {
        System.out.println("WORK transform");
        return input.toUpperCase(Locale.ROOT);
    }

    void fail() {
        System.out.println("WORK fail");
        throw new IllegalArgumentException("denied");
    }
}

public class Main {
    public static void main(String[] args) {
        Work work = new Work();

        work.open();
        work.finish();

        System.out.println("CALLER count=" + work.count());
        System.out.println("CALLER transform=" + work.transform("aspect"));

        try {
            work.fail();
        } catch (IllegalArgumentException error) {
            System.out.println("CALLER caught: " + error.getMessage());
        }
    }
}
~~~

### 6.2. Tệp TraceAspect.aj

~~~java
public aspect TraceAspect {
    before(): execution(void Work.open()) {
        System.out.println("BEFORE open");
    }

    after(): execution(void Work.finish()) {
        System.out.println("AFTER finally");
    }

    after() returning(int value): execution(int Work.count()) {
        System.out.println("AFTER returning: " + value);
    }

    after() throwing(IllegalArgumentException error):
            execution(void Work.fail()) {
        System.out.println("AFTER throwing: " + error.getMessage());
    }

    String around(): execution(String Work.transform(String)) {
        System.out.println("AROUND enter");
        String result = proceed();
        System.out.println("AROUND exit");
        return result;
    }
}
~~~

**Kiểm tra kiểu:** Around advice trả String vì join point Work.transform trả String. Nếu advice chọn một join point void, cú pháp trả giá trị sẽ khác; nếu advice chọn nhiều phương thức với kiểu trả về không đồng nhất, cần một thiết kế binding/return type phù hợp. Không dùng một kiểu return ngẫu nhiên chỉ vì compiler cho phép chuyển đổi.

### 6.3. Biên dịch với ajc và chạy

Cần JDK 17, một bản AspectJ compiler hỗ trợ Java 17, và thư viện runtime aspectjrt.jar tương ứng. Giả sử biến môi trường ASPECTJ_HOME trỏ tới bộ cài có thư mục lib chứa aspectjrt.jar, lệnh trên hệ Unix:

~~~bash
mkdir -p out
ajc -source 17 -target 17 -classpath "$ASPECTJ_HOME/lib/aspectjrt.jar" -d out Main.java TraceAspect.aj
java -cp "out:$ASPECTJ_HOME/lib/aspectjrt.jar" Main
~~~

Với Windows PowerShell, dấu phân cách classpath là dấu chấm phẩy:

~~~powershell
New-Item -ItemType Directory -Force -Path out | Out-Null
ajc -source 17 -target 17 -classpath "$env:ASPECTJ_HOME\lib\aspectjrt.jar" -d out Main.java TraceAspect.aj
java -cp "out;$env:ASPECTJ_HOME\lib\aspectjrt.jar" Main
~~~

Lưu ý: một số cách đóng gói AspectJ đặt compiler/runtime ở đường dẫn khác; điều kiện cần là lệnh ajc hoạt động và classpath tìm được thư viện runtime tương ứng. Dùng cùng thế hệ phiên bản compiler/runtime, tránh mismatch. Đây là lệnh minh họa chạy local khi bộ công cụ đã được cài đặt, không phải lệnh javac độc lập.

### 6.4. Stdout dự kiến

~~~text
BEFORE open
WORK open
WORK finish
AFTER finally
WORK count
AFTER returning: 3
CALLER count=3
AROUND enter
WORK transform
AROUND exit
CALLER transform=ASPECT
WORK fail
AFTER throwing: denied
CALLER caught: denied
~~~

**Giải thích từng cụm:**

1. Work.open: before advice được gọi trước khi method in “WORK open”.
2. Work.finish: thân method in “WORK finish”, sau đó after kiểu finally được chạy.
3. Work.count: method trả số 3; after returning nhận chính giá trị đó và ghi log trước khi caller in “CALLER count=3”.
4. Work.transform: around in dòng vào, gọi proceed để thân method in “WORK transform” và trả “ASPECT”, rồi around in dòng thoát và trả giá trị cho caller.
5. Work.fail: method in “WORK fail” rồi ném IllegalArgumentException; after throwing bind lỗi và in “denied”; caller bắt lại cùng nhánh lỗi theo hợp đồng.

Ví dụ chỉ đặt một advice áp dụng vào mỗi method nên không phát sinh câu hỏi sắp thứ tự nhiều advice cho cùng join point. Trong chương trình thực, nếu có nhiều advice cùng khớp, kết quả sẽ phụ thuộc precedence và loại advice.

### 6.5. Một thử nghiệm để tự quan sát proceed

Ở TraceAspect.aj, thay nội dung của around cho Work.transform bằng:

~~~java
// Đoạn thay thế trong aspect, không biên dịch song song
// với advice around cũ trên cùng join point.
String around(): execution(String Work.transform(String)) {
    System.out.println("AROUND bypass");
    return "OVERRIDE";
}
~~~

Khi biên dịch lại, thân Work.transform không chạy cho join point đó, vì advice không gọi proceed. Caller sẽ nhận “OVERRIDE”. Đây là thay đổi có chủ đích về luồng điều khiển. Không dùng bản này nếu mục tiêu là tracing thuần túy hay method cần tạo side effect.

## 7. Điều gì xảy ra khi nhiều advice cùng khớp?

Trong ví dụ đơn giản, mỗi method có một advice riêng. Trên ứng dụng lớn, một join point có thể được nhiều aspect chọn, ví dụ kiểm tra quyền, transaction policy, retry, metrics và logging.

Hình dung:

~~~text
caller
  -> around A (pre)
      -> before B
          -> around C (pre)
              -> target
          <- around C (post)
      <- after D
  <- around A (post)
~~~

Sơ đồ chỉ mô tả **một thứ tự khả dĩ**, không phải quy tắc precedence cố định cho mọi aspect. AspectJ có cơ chế xác định precedence giữa aspect và quy tắc thứ tự advice bên trong aspect; có thể dùng khai báo precedence tường minh khi thiết kế cần thứ tự chắc chắn.

Những câu hỏi quan trọng:

- Access control có bắt buộc chạy trước operation nhạy cảm không?
- Retry phải bao quanh logging, hay logging bao quanh mỗi attempt?
- Metrics đo **mỗi attempt** hay **toàn bộ operation**?
- Một around advice không proceed có ngăn các advice nằm sâu hơn chạy không?
- Exception của logging trong finally có che lỗi của target không?
- Một advice trả fallback có vô tình biến lỗi nghiệp vụ thành success không?

Nếu aspect A bao ngoài B, thứ tự thường quan sát là **A pre → B pre → target → B post → A post** khi cả hai đều gọi proceed đúng một lần và không ném lỗi. Nhưng nếu advice có nhánh short-circuit hoặc exception, chuỗi đó có thể khác.

Khi bảo toàn contract quan trọng, nên thiết kế test cụ thể với nhiều advice và output/counter thay vì dựa vào suy luận từ một ví dụ một aspect.

## 8. Return value và kiểu dữ liệu trong around

Around advice có khả năng tạo ra giá trị mà caller nhìn thấy. Những ràng buộc cần xét:

- **Kiểu trả về tương thích:** around cho một join point trả String không được tự ý trả Integer. Compiler có thể kiểm tra nhiều vi phạm kiểu trước khi weaving.
- **Giá trị null:** nếu method cho phép null, advice không nên giả định mọi kết quả khác null. Nếu contract cấm null, fallback null có thể gây lỗi ở caller.
- **Giữ exception gốc:** nếu mục tiêu quan sát, ném lại đúng ngoại lệ; không tạo exception mới do logger hỏng.
- **Hợp đồng side effect:** bỏ qua proceed nghĩa là thân join point có thể không chạy; proceed hai lần có thể thực hiện side effect hai lần.
- **Return wrapper:** nếu target trả CompletionStage hoặc một đối tượng có identity quan trọng, thay bằng wrapper/stage khác có thể đổi semantics.
- **Checked exception:** một around advice cần tuân theo quy tắc khai báo ngoại lệ, binding và type checking của AspectJ cho join point nó chọn.

Một example ngắn về biến đổi kết quả có chủ đích:

~~~java
// Cú pháp AspectJ; giả sử Work.transform đã được dệt.
String around(): execution(String Work.transform(String)) {
    String original = proceed();
    return "[" + original + "]";
}
~~~

Nếu input là “aspect”, caller nhận “[ASPECT]”. Đây là một **thay đổi nghiệp vụ** hoặc chính sách trình bày; không nên thực hiện trong logging aspect chỉ để ghi nhận.

## 9. Binding tham số và dùng proceed với dữ liệu đã thay đổi

Around có thể bind đối số từ join point bằng args và chuyển đối số mới cho proceed khi cơ chế ngôn ngữ cho phép. Ví dụ code-style AspectJ:

~~~java
// Fragment cú pháp AspectJ, không phải đoạn Java độc lập.
// Nếu chạy cùng ví dụ đầy đủ, phải bỏ/thay around
// đã chọn cùng Work.transform để tránh trùng chính sách.
String around(String input):
        execution(String Work.transform(String)) && args(input) {
    String normalized = input.trim();
    return proceed(normalized);
}
~~~

Trong trường hợp này, advice chọn Work.transform và bind tham số String vào input. Nó tạo giá trị đã trim rồi truyền làm đối số khi proceed. Bản này minh họa khả năng can thiệp; **không dùng để logging thuần túy**, vì nó thay đổi dữ liệu mà target nhận.

Đừng nhầm proceed trong AspectJ code-style với mọi API proxy có tên tương tự; cú pháp truyền đối số và quy tắc binding có thể khác. Với nhiều binding (this, target, args, annotation), quy tắc truyền giá trị cho proceed phải khớp thứ tự và loại binding theo AspectJ.

Nếu normalizing input là hợp đồng nghiệp vụ, cần kiểm thử:

1. Input có ký tự Unicode hoặc khoảng trắng đặc biệt.
2. Null input: input.trim() có thể ném NullPointerException.
3. Chuẩn hóa có làm thay đổi quyền, chữ ký số hoặc cache key không?
4. Có những advice khác phụ thuộc original input hay không?
5. Target có side effect hoặc kiểm tra dữ liệu gốc trước khi thay đổi không?

Khi chỉ muốn đo lường, tốt hơn là đọc arguments để ghi log theo chính sách, không tự sửa chúng.

## 10. After throwing khác với catch quanh proceed

After throwing giúp ghi nhận một ngoại lệ đã thoát khỏi join point được chọn; nó không mặc định phục hồi bằng cách trả fallback.

Around advice có thể bắt ngoại lệ của phần tiếp tục:

~~~java
// Fragment minh họa; Work.risky được định nghĩa trong ứng dụng.
String around(): execution(String Work.risky()) {
    try {
        return proceed();
    } catch (IllegalStateException failure) {
        recordFailure(failure);
        throw failure;
    }
}
~~~

Ở đây recordFailure là hàm giả định. Mục đích là **giữ nguyên đối tượng ngoại lệ**. Nếu recordFailure ném lỗi, ngoại lệ ghi nhận có thể che lỗi gốc; thiết kế logger an toàn là một phần của chính sách.

Around cũng có thể trả fallback thay vì throw, nhưng đó là quyết định rõ ràng về hợp đồng của operation. Hãy phân biệt:

- Quan sát lỗi, rồi ném lại.
- Chuyển lỗi thành ngoại lệ khác được định nghĩa.
- Cung cấp fallback.
- Retry có giới hạn sau một nhóm lỗi đã phân loại.

Nếu một after throwing advice chỉ bắt RuntimeException còn target ném checked exception, đừng giả định advice đó sẽ thấy mọi failure. Phải chọn kiểu throwable/binding theo yêu cầu kiểm thử.

## 11. After finally và lỗi trong advice

Một giả định thường thấy: vì after kiểu finally luôn chạy sau target, nó an toàn để ghi log trong mọi trường hợp. Đây là suy luận sai.

~~~java
// Fragment minh họa, sink được khai báo ở nơi khác.
after(): execution(* Work.process(..)) {
    sink.write("operation finished"); // Có thể ném lỗi.
}
~~~

Nếu target đã thành công và sink.write ném lỗi, caller có thể nhìn thấy lỗi logger thay cho kết quả thật. Nếu target đã ném ngoại lệ nghiệp vụ và sink.write lại ném lỗi, kết quả quan sát được cũng có thể bị thay đổi.

Hãy xác định chính sách:

- **Best effort diagnostics:** cô lập lỗi logging ở chính helper hoặc advice; không làm sai outcome nghiệp vụ.
- **Audit bắt buộc:** nếu nghiệp vụ chỉ được phép diễn ra khi audit bền vững, phải thiết kế ranh giới transaction/cam kết phù hợp hoặc từ chối trước khi tạo side effect. Không “tự nhiên” phát lỗi audit sau khi side effect đã commit rồi để caller retry.
- **Cleanup bắt buộc:** nếu việc giải phóng tài nguyên bị lỗi, cần quy tắc xử lý/ghi nhận cụ thể; không tự nuốt mọi lỗi với lý do đó là after advice.
- **Error và fatal condition:** bắt RuntimeException khác với nuốt mọi Throwable; không hứa an toàn tuyệt đối khi JVM hết bộ nhớ hoặc mất khả năng hoạt động.

AOP không làm lỗi của instrumentation trở nên vô hại. Mọi advice đều là code thật, có thể ném ngoại lệ và sử dụng tài nguyên.

## 12. Advice và bất đồng bộ: “after returning” của phương thức không phải “after completion”

Một method có thể trả ngay một CompletableFuture đang pending:

~~~java
// Fragment Java trong một class; không độc lập.
CompletableFuture<String> fetchAsync() {
    return pendingTask;
}
~~~

Nếu after returning advice gắn vào execution của fetchAsync, nó chạy khi **phương thức trả về đối tượng future**, chứ không tự chờ task hoàn tất. Tác vụ có thể tiếp tục, thành công, thất bại hoặc bị hủy sau đó.

Nếu cần log kết quả cuối, có thể thêm completion observer:

~~~java
// Fragment Java dùng CompletionStage; recordOutcome phải có
// chính sách không ném lỗi quan sát ngoài ý muốn.
CompletionStage<String> observed = stage.whenComplete((value, error) -> {
    recordOutcome(value, error);
});
~~~

Kết quả của whenComplete là một dependent stage. Nếu observer ném lỗi khi stage nguồn thành công, dependent stage có thể thất bại. Và cancellation của dependent stage không luôn tương đương cancellation upstream. Do đó, một around advice thay stage trả về cần hiểu rõ semantics, không chỉ đơn giản attach callback.

**Lỗi muộn trong callback không tự đi vào after throwing của lời gọi tạo future.** Để quan sát nó, phải chọn join point/hook thật sự liên quan tới callback hoặc completion.

## 13. Trường hợp self-invocation và phương thức được gọi từ nhiều nơi

Trong ví dụ main, Work là một class được ajc dệt tại **method execution**, nên các advice execution được nhắm trực tiếp vào thân method được dệt. Đây khác với cơ chế chỉ can thiệp khi caller đi qua một đối tượng proxy.

Giả sử Work.open được gọi từ một phương thức khác trong chính Work. Với execution weaving phù hợp, advice có thể vẫn áp dụng khi Work.open thực thi. Nếu chuyển sang cơ chế call interception giới hạn ở proxy, internal call có thể không kích hoạt advice.

Một kiểm thử coverage nghiêm túc cần:

- Xác nhận code target thật sự đã được woven.
- Gọi join point từ đường thông thường, từ đường nội bộ và từ đường callback nếu chúng tồn tại.
- Phân biệt execution với call pointcut.
- Kiểm tra overload và các method signature có match pointcut hay không.
- Kiểm tra việc thêm class mới hoặc tải class động có được weaving không.
- Không suy từ stdout của một ví dụ compile-time weaving rằng mọi lời gọi ở mọi runtime đều có coverage giống nhau.

Nếu advice dùng để kiểm soát quyền, phải bảo đảm mọi đường đến thao tác nhạy cảm đi qua một điểm cưỡng chế có thẩm quyền; không dựa vào tên “aspect” để suy ra an toàn.

## 14. Thứ tự thực thi khi có exception

Để hiểu thời điểm callback:

~~~text
Đường bình thường (một around bao ngoài phần tiếp tục):
around pre
  -> proceed
      -> target
      <- normal result
around post
<- caller nhận result

Đường ném lỗi:
around pre
  -> proceed
      -> target throws E
      <- E truyền ra
around catch/finally (nếu có)
<- caller thấy E hoặc kết quả đã được chính sách chuyển đổi
~~~

Nếu around viết:

~~~java
// Fragment minh họa: after-proceed chỉ chạy khi proceed trả bình thường.
Object around(): execution(* Work.risky(..)) {
    System.out.println("enter");
    Object result = proceed();
    System.out.println("normal exit");
    return result;
}
~~~

Khi proceed ném lỗi, dòng “normal exit” bị bỏ qua. Nếu muốn ghi sự kiện kết thúc trong cả hai nhánh, dùng finally (và cô lập lỗi logger theo chính sách). Nếu muốn phân biệt success và failure, dùng catch có chủ đích hoặc after returning/after throwing đúng nghĩa.

Không hứa một thứ tự cố định nếu nhiều around/before/after cùng áp dụng và precedence chưa được định nghĩa; test cùng runtime, cùng aspect set để xác định thứ tự thật.

## 15. Những lỗi thường gặp với proceed và cách tránh

### Lỗi 1: không gọi proceed trong advice chỉ dùng để đo đạc

Nếu around trả giá trị mặc định mà không proceed, business method không chạy. Cần kiểm thử target invocation count bằng 1 khi mục đích chỉ là observability.

### Lỗi 2: proceed nhiều lần vô tình

Một vòng retry vô hạn có thể tạo side effect lặp lại. Chỉ retry khi có ngân sách, điều kiện lỗi đã xác định và hành vi idempotent hoặc reconcile.

### Lỗi 3: tin rằng proceed luôn gọi thẳng target

Proceed tiếp tục chain bên trong; một advice khác có thể short-circuit hoặc ném lỗi. Không nhầm thứ tự logic với call trực tiếp.

### Lỗi 4: after returning là “operation đã thành công”

Nếu method trả future, chỉ có lời gọi **trả về bình thường**. Phải quan sát completion nếu cần outcome cuối.

### Lỗi 5: after() kiểu finally chỉ chạy khi thành công

Sai. Nó áp dụng cả đường ném lỗi trong phạm vi đã dệt; không ghi “success” một cách vô điều kiện.

### Lỗi 6: after throwing luôn thấy mọi loại lỗi

Binding kiểu cụ thể có thể chỉ khớp những exception tương thích. Ngoài ra, các lỗi xảy ra sau khi join point trả về không nằm trong phạm vi lời gọi đồng bộ đó.

### Lỗi 7: logger trong advice không thể làm thay đổi outcome

Sai. Một exception do logger ném có thể che return hoặc exception nghiệp vụ. Giảm side effect và cô lập lỗi quan sát theo chính sách.

### Lỗi 8: lạm dụng around cho mọi trường hợp

Nếu chỉ cần ghi log trước, before đơn giản hơn. Nếu chỉ cần quan sát return, after returning diễn đạt ý định rõ hơn. Around phù hợp khi cần điều khiển phần tiếp tục, biến đổi dữ liệu hoặc kết hợp quan sát hai phía có giữ trạng thái.

### Lỗi 9: dùng javac để biên dịch trực tiếp tệp .aj

Mã code-style AspectJ cần compiler/weaver phù hợp; javac thuần không hiểu khai báo aspect hoặc advice trong tệp .aj.

### Lỗi 10: giả định thứ tự giữa nhiều aspect là thứ tự trong file bất kỳ

Precedence là vấn đề ngữ nghĩa của AOP. Khi cần chính xác, khai báo precedence và kiểm thử, nhất là với authorization, transaction policy, retry và telemetry.

## 16. Checklist kiểm thử advice đúng hợp đồng

Với một join point mẫu, nên có các tình huống sau:

| Test | Điều phải xác minh |
| --- | --- |
| Before trên method bình thường | Advice chạy trước target; target đúng một lần |
| Before ném lỗi có chủ đích | Target không chạy, caller nhận lỗi từ chối đúng contract |
| After finally khi target trả bình thường | Advice được chạy sau thân method |
| After finally khi target ném | Advice vẫn được chạy, không che lỗi gốc nếu policy yêu cầu |
| After returning có giá trị | Advice nhận đúng giá trị trả về của join point |
| After returning khi target throw | Advice không chạy |
| After throwing với exception phù hợp | Advice nhận đúng loại và thông điệp lỗi |
| After throwing với exception không phù hợp | Advice không khớp binding đó |
| Around proceed một lần | Thân target chạy một lần; return và exception được bảo toàn |
| Around không proceed | Target bị bỏ qua có chủ đích; giá trị thay thế hợp lệ |
| Around retry | Số lần target chạy đúng attempt, không sinh side effect trái policy |
| Around trên async return | Advice return đúng lúc; completion được theo dõi riêng |
| Nhiều advice cùng khớp | Precedence và log order đúng cấu hình |
| Logger tự throw | Không thay đổi kết quả nghiệp vụ ngoài policy |
| Direct/internal call | Coverage phù hợp loại pointcut và weaving |
| Refactor signature | Pointcut vẫn match hoặc regression test phát hiện |

Những bài test này giúp phân biệt **đúng cú pháp** với **đúng hành vi thực thi**. Một chương trình compile được vẫn có thể sai logic nếu bỏ proceed hoặc vô tình nuốt ngoại lệ.

## 17. Cách lựa chọn advice theo mục đích

| Mục tiêu | Kiểu advice thích hợp | Lý do |
| --- | --- | --- |
| Kiểm tra quyền trước khi vào target | Before hoặc around | Có thể từ chối trước khi side effect diễn ra |
| Đo thời gian nhập phương thức | Before + hook kết thúc, hoặc around | Cần timestamp bắt đầu và kết thúc |
| Log mỗi lần target trả về bình thường | After returning | Phân biệt rõ với đường lỗi |
| Ghi nhận exception đồng bộ | After throwing | Có thể bind throwable |
| Cleanup sau cả success và failure | After finally hoặc finally trong around | Nhìn cả hai đường rời join point |
| Cache với short-circuit | Around | Có thể trả kết quả mà không proceed |
| Retry có giới hạn | Around | Có quyền gọi proceed nhiều lần theo chính sách |
| Biến đổi argument hoặc return | Around | Có thể can thiệp trước/sau proceed |
| Tracing của kết quả bất đồng bộ | Hook completion kết hợp advice ở invocation | Return future chưa có nghĩa complete |
| Quan sát mà không đổi hợp đồng | Advice đơn giản nhất, thêm error isolation | Giảm bề mặt thay đổi control flow |

Nếu yêu cầu chỉ là ghi nhật ký “bắt đầu”, không cần around. Nếu cần chuyển đổi return value, before/after returning thường không phải lựa chọn để sửa kết quả; dùng around với hợp đồng rõ ràng.

## 18. Bài tập tự đánh giá

**Câu 1.** Một before advice in “start”, target ném ngoại lệ. Before có tự in “failed” sau khi target ném không?

**Đáp án:** Không. Before chạy trước join point và không có nhánh sau target. Dùng after throwing hoặc around catch khi cần ghi lỗi.

**Câu 2.** After() kiểu finally khác after returning như thế nào?

**Đáp án:** After finally chạy khi join point kết thúc theo cả đường bình thường lẫn ngoại lệ (trong phạm vi advice áp dụng). After returning chỉ chạy khi join point trả về bình thường và có thể bind return value.

**Câu 3.** Around không gọi proceed có làm thân method chạy không?

**Đáp án:** Không, đối với phần join point nằm phía trong advice đó. Around có thể short-circuit hợp lệ theo chính sách, nhưng nếu lỡ quên proceed thì mất hành vi nghiệp vụ.

**Câu 4.** Gọi proceed hai lần có vô hại với một phương thức tạo đơn hàng không?

**Đáp án:** Không. Thao tác có thể tạo hai đơn hàng hoặc thực hiện side effect hai lần. Retry phải có điều kiện rõ, giới hạn attempt và idempotency.

**Câu 5.** Một method trả CompletableFuture pending. After returning chạy. Nghiệp vụ đã thành công chưa?

**Đáp án:** Chưa thể kết luận. Chỉ phương thức đã trả future bình thường. Cần completion hook để biết future hoàn tất thành công, thất bại hay bị hủy.

**Câu 6.** Nếu một after throwing advice bind IllegalArgumentException mà target ném IOException, advice đó có nhất thiết chạy không?

**Đáp án:** Không. Binding throwable phải tương thích kiểu exception được ném. Nếu cần quan sát phổ rộng, thiết kế binding thích hợp và xử lý nhiều loại lỗi.

**Câu 7.** Trong around, proceed có luôn gọi trực tiếp thân method không qua advice nào khác?

**Đáp án:** Không. Proceed đi tiếp qua chain bên trong theo precedence; nó có thể gặp advice khác trước khi đến target.

**Câu 8.** Một after finally advice ghi log bị lỗi khi target đã ném lỗi nghiệp vụ. Caller có thể thấy lỗi gì?

**Đáp án:** Nếu logging throw không được cô lập, lỗi logger có thể che lỗi nghiệp vụ. Với policy quan sát best effort, phải giữ nguyên lỗi target.

**Câu 9.** Tại sao không thể chỉ dùng javac để biên dịch TraceAspect.aj?

**Đáp án:** Tệp .aj sử dụng cú pháp riêng của AspectJ, cần ajc hoặc cơ chế weaving tương thích. Java compiler thuần không nhận khai báo code-style aspect.

**Câu 10.** Trong ví dụ, Work.transform được gọi từ nhiều caller. execution advice có nhất thiết giống call advice trên mọi caller không?

**Đáp án:** Không. Execution advice được dệt vào thực thi method; call advice bắt call site thuộc phạm vi weaving. Phạm vi khác nhau nên cần test phù hợp.

## 19. Tự thực hành theo ba thí nghiệm

**Thí nghiệm A — Không proceed:** đổi around trong TraceAspect.aj sang trả một String cố định. Sau khi biên dịch lại, kiểm tra “WORK transform” biến mất và caller nhận chuỗi thay thế. Giải thích vì sao điều này nguy hiểm với method có side effect.

**Thí nghiệm B — Proceed một lần với finally:** thay around bằng mẫu try/finally; sửa Work.transform để ném IllegalArgumentException khi input null. Quan sát phần finally vẫn chạy khi proceed throw, còn dòng sau proceed ngoài finally sẽ bị bỏ qua.

**Thí nghiệm C — Hai advice cùng join point:** tạo một around đo thời gian và một before logging cùng chọn Work.transform. Định nghĩa precedence, dự đoán thứ tự trước khi chạy rồi kiểm chứng stdout. Thử short-circuit trong around và ghi lại advice nào không còn chạy. Chú ý không suy ngược quy luật precedence từ một quan sát tình cờ.

Khi hoàn thành, cần giải thích được không chỉ **dòng nào in trước**, mà cả **target thực thi bao nhiêu lần, caller nhận kết quả gì và những mối quan tâm cắt ngang nào còn được thực hiện**.

## Kết luận

Before phù hợp với xử lý trước join point. After finally, after returning và after throwing đại diện cho **những điều kiện kết thúc khác nhau**. Around là dạng có quyền điều khiển mạnh: nó có thể đi tiếp qua proceed, thay đổi dữ liệu, short-circuit hoặc retry. Sức mạnh đó đòi hỏi kỷ luật về kiểu dữ liệu, return value, ngoại lệ, side effect và thứ tự advice. AspectJ giúp thấy cơ chế này bằng các pointcut execution và mã .aj được weaving, nhưng nguyên tắc vẫn thuộc AOP nói chung: **chọn advice theo mục đích, hiểu rõ phần thực thi được bao quanh, và chỉ thay đổi hành vi nghiệp vụ khi chính sách thật sự yêu cầu**.