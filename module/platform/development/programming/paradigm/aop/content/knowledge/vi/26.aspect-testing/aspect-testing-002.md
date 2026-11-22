# Kiểm thử pointcut khớp đúng trường hợp mong muốn trong AOP

## 1. Vì sao pointcut phải được kiểm thử?

Trong **Aspect-Oriented Programming (AOP)**, pointcut quyết định **những join point nào sẽ được áp dụng advice**. Một pointcut sai có thể làm advice **bỏ sót** nơi cần chạy (*false negative*) hoặc **can thiệp nhầm** nơi không được chạy (*false positive*).

Đây không chỉ là lỗi ghi log:

- Bỏ sót kiểm tra quyền ở một phương thức quan trọng có thể tạo lỗ hổng.
- Áp transaction lên phương thức không liên quan có thể thay đổi chi phí, locking và semantics.
- Áp retry vào thao tác ghi không idempotent có thể nhân đôi side effect.
- Một aspect quan sát quá rộng có thể ghi dữ liệu nhạy cảm hoặc tạo recursion.
- Một pointcut theo tên quá hẹp có thể mất hiệu lực khi refactor, overload hoặc thêm implementation mới.

**Mục tiêu kiểm thử pointcut** là chứng minh tập join point được chọn **trùng với tập mong muốn theo hợp đồng**, bao gồm cả trường hợp **phải match** và **không được match**. Chỉ kiểm thử việc một phương thức mẫu “đã in log” là chưa đủ: phải kiểm tra **độ chính xác của tập chọn, kiểu join point, thứ tự advice và hành vi thực tế sau weaving/interception**.

Bài này nói về **AOP tổng quát**, từ phân tích pointcut tới kiểm thử nâng cao. Các ví dụ dùng cú pháp AspectJ và compiler `ajc` như một cách hiện thực AOP có weaving. Cơ chế proxy, decorator và weaving có thể hỗ trợ tập join point khác nhau; khi chuyển một bài test giữa các công cụ phải điều chỉnh kỳ vọng theo cơ chế thực tế.

## 2. Những khái niệm cần xác định trước

| Khái niệm | Vai trò trong kiểm thử | Câu hỏi |
| --- | --- | --- |
| **Join point** | Một điểm thực thi/gọi hợp lệ trong mô hình AOP | Có những loại điểm nào: execution, call, constructor, field? |
| **Pointcut** | Biểu thức chọn một tập join point | Biểu thức này có chọn đúng tập được định nghĩa không? |
| **Advice** | Hành vi tại join point đã chọn | Advice chạy mấy lần, lúc nào, có giữ nguyên return/throw? |
| **Weaving / interception** | Cơ chế kết nối advice vào chương trình | Class/call site nào thực sự được xử lý? |
| **Shadow** | Vị trí có thể trở thành join point khi chương trình chạy trong AOP tĩnh/bytecode | Weaver có nhìn thấy và xử lý vị trí đó không? |
| **Positive case** | Một join point phải match | Có đúng một sự kiện advice tương ứng không? |
| **Negative case** | Một join point không được match | Advice không chạy tại vị trí này? |
| **Boundary case** | Trường hợp sát ranh giới biểu thức | Overload, subclass, generic, visibility, package khác xử lý sao? |

**Pointcut là một điều kiện trên join point, không chỉ là một bộ lọc tên method.** Ví dụ, `execution(public void TaskService.save(String))` mô tả việc **thực thi** một method có chữ ký tương ứng; còn `call(void TaskService.save(String))` chọn vị trí **gọi** tương ứng. Nơi phải weave và số lần match có thể khác nhau.

Trong AOP, có hai hợp đồng cần kiểm thử riêng:

1. **Selection contract:** tập join point nào được chọn hoặc loại trừ.
2. **Advice behavior contract:** khi đã được chọn, advice có giữ nguyên semantics nghiệp vụ và thực hiện policy đúng không.

Một phép kiểm thử có thể chứng minh “advice in một dòng” nhưng chưa chứng minh phương thức gốc được gọi đúng một lần, không bị đổi exception hoặc thiếu nhánh cleanup. Do đó hai hợp đồng phải được đo độc lập rồi kiểm thử tích hợp.

## 3. Đặc tả tập match trước khi viết biểu thức

Trước khi viết `execution(...)` hoặc chọn annotation, hãy lập bảng **quyết định** từ yêu cầu.

Giả sử policy là: **quan sát mọi lần thực thi công khai của `TaskService.save(String)`**, bao gồm khi được gọi từ bên trong cùng đối tượng; không quan sát overload nhận `int`, phương thức `cancel()`, phương thức `selfCall()` và phương thức cùng tên ở class khác.

| Tình huống | Kỳ vọng | Lý do |
| --- | --- | --- |
| `new TaskService().save("A")` | **MATCH** | Đúng class, tên, kiểu tham số và method execution |
| `new TaskService().save(7)` | **NO MATCH** | Overload khác kiểu tham số |
| `new TaskService().cancel()` | **NO MATCH** | Method khác |
| `new TaskService().selfCall()` | **NO MATCH** tại execution của `selfCall` | Nó không phải `save(String)` |
| `selfCall()` gọi nội bộ `save("self")` | **MATCH** tại execution của `save(String)` | Weaving tại method execution, không phụ thuộc caller |
| `new OtherService().save("A")` | **NO MATCH** | Class khác dù cùng tên/signature |
| Một join point nằm ngoài class được weave | Phụ thuộc phạm vi weaving | Không thể yêu cầu advice xuất hiện nếu vị trí cần weave không được xử lý |

Bảng này là **nguồn sự thật của bài test**. Không suy luận expected result từ pointcut đang viết: nếu pointcut sai và test cũng copy cùng giả định, cả hai có thể sai mà test vẫn xanh.

### 3.1. Chia kiểm thử thành ba lớp

- **Selection test:** dùng một aspect probe có hành vi rất nhỏ và xác định, ghi lại từng hit để so với bảng expected.
- **Advice contract test:** kiểm tra advice với target giả: số lần gọi, kết quả, lỗi, thứ tự và cleanup.
- **Integration/weaving test:** chạy artifact thật sau weaving/interception, chứng minh các join point được đánh dấu ở đúng class, class loader và đường gọi.

Khi sửa một pointcut bảo mật, phải coi đây là thay đổi về **phạm vi bảo vệ**. Một kiểm thử unit riêng cho hàm kiểm tra quyền không chứng minh pointcut đã bao phủ mọi đường vào.

## 4. Cách nhận biết false positive và false negative

### 4.1. False negative: thiếu một nơi cần chạy advice

Ví dụ một chính sách đòi đo mọi thao tác ghi, nhưng pointcut chỉ match `save(String)`; sau đó người khác thêm `save(Request)` hoặc `persist(Request)` mà không cập nhật scope. Test của method cũ vẫn xanh nhưng thao tác mới không được đo.

Các nguyên nhân thường gặp:

- Chữ ký hoặc kiểu tham số thay đổi.
- Pointcut chỉ chọn một class cụ thể, trong khi implementation mới nằm ở class khác.
- Phạm vi weave thiếu một thư viện, package hoặc module.
- Lời gọi đi qua đường nội bộ không kích hoạt proxy interception dù người viết tưởng có.
- Dùng `call(...)` nhưng caller code không được weave.
- Annotation không xuất hiện hoặc không được đọc ở vị trí mong muốn.
- Method trả asynchronous handle, advice chạy ở thời điểm return nhưng không quan sát completion.

### 4.2. False positive: bắt nhầm một nơi không thuộc chính sách

Ví dụ `execution(* *.save(..))` có thể chọn nhiều method `save` với nghĩa khác nhau: lưu tài liệu public, ghi cấu hình nội bộ, cập nhật token hoặc phương thức của telemetry sink. Một advice ghi full arguments khi đó có thể làm lộ dữ liệu.

Các nguyên nhân:

- Wildcard kiểu trả về, package hoặc tham số quá rộng.
- Chọn mọi class con của một base type trong khi một số subclass có nghĩa nghiệp vụ khác.
- Dùng `within(...)`/`withincode(...)` mà không hiểu phạm vi lexical.
- Nhiều aspect cùng pointcut gây đếm trùng hoặc advice lồng nhau.
- Áp `cflow(...)` khi không phân biệt lời gọi trực tiếp, nested call và recursive call.
- Annotation được đặt ở method khác với method thực sự được weave.

**Negative tests quan trọng ngang positive tests.** Chúng bảo vệ khỏi một kiểu regression rất dễ bỏ qua: chương trình vẫn chạy thành công nhưng advice âm thầm ảnh hưởng thêm các nơi ngoài ý định.

## 5. Test theo ma trận chữ ký và loại join point

### 5.1. Signature matching

Kiểm thử các chiều:

| Chiều | Trường hợp cần có | Rủi ro |
| --- | --- | --- |
| Tên method | `save`, `saveAll`, `persist` | Wildcard match cả tên không mong muốn |
| Kiểu tham số | `save(String)`, `save(int)`, `save(Object)` | `(..)` rộng quá, overload bị chọn nhầm |
| Số lượng tham số | 0, 1, varargs | Quy tắc `*` và `..` bị hiểu sai |
| Return type | `void`, `String`, `CompletionStage<?>` | Đổi return type làm pointcut mất match |
| Visibility | public/protected/package/private | Pointcut và cơ chế chặn có phạm vi khác nhau |
| Static/instance | method static và method instance | Một số cơ chế proxy không áp lên static |
| Interface/class | Interface method, concrete method | Signature ở interface khác execution tại implementation |
| Inheritance/override | Class cha, subclass, override | Target method được thực thi không như tên tĩnh |
| Generic/bridge | Generic method sau type erasure, bridge method | Có thể có bytecode bổ sung, cần kiểm tra weave info |
| Annotation | Trên interface, class, method hoặc override | Không mặc định annotation được kế thừa mọi nơi |
| Package | Class đúng module, class cùng tên ở package khác | Pattern quá rộng hoặc quá hẹp |

Không cần mọi dự án kiểm thử tích Descartes của toàn bộ các chiều. Hãy chọn những **ranh giới dễ làm đổi phạm vi chính sách**, và cố định bằng contract test khi thêm method hoặc nâng compiler.

### 5.2. Phân biệt `execution`, `call` và `within`

Trong mô hình AspectJ:

- `execution(...)` mô tả **method execution**. Với code method được weave, một self-call đến method ấy vẫn đi vào execution join point.
- `call(...)` mô tả **call site**. Code chứa lời gọi phải được weave; không đủ nếu chỉ class đích đã weave.
- `within(TypePattern)` giới hạn về **vị trí lexical** của code chứa join point, không có nghĩa tự động chọn mọi lần method được gọi bởi class đó.
- `withincode(SignaturePattern)` chọn join point **nằm trong thân** method/constructor phù hợp, không tự có nghĩa chọn execution của chính method đó.
- `this(...)` và `target(...)` có semantics khác nhau ở những loại join point khác nhau; phải kiểm tra trường hợp static hoặc join point không có target.
- `args(...)` quan sát kiểu/giá trị đối số runtime theo ngữ nghĩa pointcut, khác với signature pattern chỉ kiểm tra khai báo tĩnh.

Ví dụ trong môi trường có weaving:

~~~java
// Giả mã cú pháp pointcut: các class phải tồn tại trong dự án.
// execution: method được thực thi.
execution(void TaskService.save(String))

// call: vị trí gọi method.
call(void TaskService.save(String))

// Chọn execution nằm trong một package cụ thể.
execution(public * sample.app..*(..))
~~~

Đây là **các biểu thức minh họa**, không phải file Java chạy độc lập. `execution` và `call` không thể thay thế máy móc cho nhau trong mọi tình huống.

### 5.3. Tính động của pointcut

Một số pointcut có phần điều kiện chỉ xác định được khi chạy: `args(...)` với runtime type, `this(...)`, `target(...)`, `cflow(...)` hoặc `if(...)`. Với chúng, test phải thay **giá trị runtime, type của object và đường control flow**, không chỉ liệt kê method name.

Nếu policy phụ thuộc `actorId` hoặc trạng thái đơn hàng, hãy phân biệt **pointcut chọn nơi chạy advice** với **business predicate quyết định allow/deny**. Việc method đã match không chứng minh actor được phép thực hiện thao tác. Chia hai test: test selection và test policy.

## 6. Ví dụ Java 17+ và AspectJ: test đầy đủ cả match lẫn exclusion

Bốn file dưới đây tạo thành chương trình tự kiểm tra thứ tự sự kiện. Pointcut chọn chính xác `execution(public void TaskService.save(String))`; test ghi lại event thay vì chỉ trông vào log bằng mắt.

Dùng compiler `ajc` của AspectJ tương thích Java 17 và `aspectjrt.jar` cùng phiên bản. Đây là **ví dụ AOP weaving tổng quát**, không sử dụng framework web hay container ứng dụng.

### 6.1. Mã nghiệp vụ `TaskService.java`

~~~java
public class TaskService {
    public void save(String id) {
        PointcutContractTest.record("business:save(String):" + id);
    }

    public void save(int id) {
        PointcutContractTest.record("business:save(int):" + id);
    }

    public void cancel() {
        PointcutContractTest.record("business:cancel");
    }

    public void selfCall() {
        PointcutContractTest.record("business:selfCall");
        save("self");
    }
}
~~~

`TaskService` không biết aspect. Có hai overload để kiểm tra chữ ký, và `selfCall()` để chứng minh execution join point của `save(String)` vẫn được weave khi gọi từ trong cùng object.

### 6.2. Class ngoài phạm vi `OtherService.java`

~~~java
public class OtherService {
    public void save(String id) {
        PointcutContractTest.record("other:save(String):" + id);
    }
}
~~~

Dù tên `save` và kiểu tham số giống nhau, class khác phải **không khớp** pointcut đã mô tả cho `TaskService`.

### 6.3. Aspect `TaskPointcut.aj`

~~~java
public aspect TaskPointcut {
    pointcut selectedSave():
        execution(public void TaskService.save(String));

    before(): selectedSave() {
        PointcutContractTest.record("advice:before");
    }

    after() returning: selectedSave() {
        PointcutContractTest.record("advice:after");
    }
}
~~~

Aspect chỉ quan sát hai mốc: trước khi method được chạy và sau khi nó **trả bình thường**. Nếu method ném exception, `after() returning` sẽ không chạy. Khi cần kiểm tra đường lỗi, thêm test/advice thích hợp, không “chữa” bằng cách nuốt lỗi nghiệp vụ.

### 6.4. Bộ kiểm thử `PointcutContractTest.java`

~~~java
import java.util.ArrayList;
import java.util.List;

public class PointcutContractTest {
    private static final List<String> EVENTS = new ArrayList<>();

    public static void record(String event) {
        EVENTS.add(event);
    }

    public static void main(String[] args) {
        TaskService task = new TaskService();
        OtherService other = new OtherService();

        task.save("A");       // MATCH.
        task.save(7);         // NO MATCH: overload.
        task.cancel();        // NO MATCH: method khác.
        task.selfCall();      // selfCall KHÔNG match,
                              // nhưng save("self") ở bên trong MATCH.
        other.save("A");      // NO MATCH: class khác.

        List<String> expected = List.of(
            "advice:before",
            "business:save(String):A",
            "advice:after",
            "business:save(int):7",
            "business:cancel",
            "business:selfCall",
            "advice:before",
            "business:save(String):self",
            "advice:after",
            "other:save(String):A"
        );

        if (!EVENTS.equals(expected)) {
            throw new AssertionError(
                "Pointcut mismatch: expected=" + expected
                + " actual=" + EVENTS
            );
        }
        System.out.println("PASS: 2 matches; 4 other executions not advised");
    }
}
~~~

Đây là bài test **fail-fast**: thiếu advice ở self-call, bắt nhầm overload hoặc bắt nhầm class khác đều khiến danh sách không khớp. `List.of(...)` thuộc Java 9+ và hoạt động trong Java 17.

### 6.5. Build và chạy thực tế với `ajc`

Đặt 4 file cùng thư mục. Chuẩn bị hai artifact cùng phiên bản AspectJ: `aspectjtools.jar` (compiler) và `aspectjrt.jar` (runtime). Các lệnh dưới đây **đặt tên ngắn cho JAR** và có thể thay đường dẫn bằng vị trí file thực tế của bạn.

Trên Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force woven | Out-Null
java -cp "lib\aspectjtools.jar" org.aspectj.tools.ajc.Main -17 -classpath "lib\aspectjrt.jar" -d woven TaskService.java OtherService.java PointcutContractTest.java TaskPointcut.aj
java -cp "woven;lib\aspectjrt.jar" PointcutContractTest
~~~

Trên macOS/Linux:

~~~bash
mkdir -p woven
java -cp "lib/aspectjtools.jar" org.aspectj.tools.ajc.Main -17 -classpath "lib/aspectjrt.jar" -d woven TaskService.java OtherService.java PointcutContractTest.java TaskPointcut.aj
java -cp "woven:lib/aspectjrt.jar" PointcutContractTest
~~~

**Stdout của bài test khi tất cả match/exclusion đúng:**

~~~text
PASS: 2 matches; 4 other executions not advised
~~~

Sự hiện diện của dòng `PASS` có nghĩa **mọi phần tử của event list đã được so sánh đúng từng vị trí**; nó không chỉ đơn thuần đếm hai lần advice chạy. Nếu chạy các class chưa weave bằng `javac` rồi `java`, test sẽ thất bại vì các event `advice:before`/`advice:after` không xuất hiện. Đó là hành vi mong đợi: bài test cũng phát hiện **cấu hình weaving bị thiếu**.

### 6.6. Những điều ví dụ đã và chưa chứng minh

Đã chứng minh:

1. Hai execution của `TaskService.save(String)` match, bao gồm self-call.
2. `TaskService.save(int)` không match.
3. `TaskService.cancel()` và `TaskService.selfCall()` không bị advice này chặn tại execution của chúng.
4. `OtherService.save(String)` không match dù cùng tên và tham số.
5. `before`/`after returning` đi đúng thứ tự trên đường thành công.
6. Weaving thực sự được bật trong chương trình đang chạy.

Chưa chứng minh: behavior của inherited method, interface method, abstract class, overload với generic bridge, dynamic pointcut, annotation, class loader khác, exception từ `save(String)`, concurrency, async hay tình huống nhiều advice có precedence. Những phần này cần test riêng trong dự án có các cấu trúc tương ứng.

Vì `EVENTS` là danh sách static không thread-safe, demo chủ ý **chạy tuần tự**; trong kiểm thử nhiều thread, dùng collector an toàn đồng thời và điều khiển thứ tự mà không dựa vào scheduler ngẫu nhiên.

## 7. Đối chiếu contract với sự kiện nhận được

Một lỗi kiểm thử phổ biến là kiểm tra theo kiểu:

~~~java
// MINH HỌA: cách assert còn quá yếu, không phải chương trình độc lập.
if (events.contains("advice:before")) {
    // Cho rằng pointcut đã đúng.
}
~~~

Check trên chỉ chứng minh advice đã chạy **ít nhất một lần**. Nó không phát hiện:

- Bị match thêm một method không mong muốn.
- Bị match hai lần do hai aspect chồng lấn.
- Thiếu match khi self-call.
- Advice chạy đúng method nhưng sai thời điểm hoặc thiếu cleanup.
- Runtime đang load class chưa weave ở một nhánh khác.

Cách kiểm chứng mạnh hơn là tạo **tập kỳ vọng** hoặc **chuỗi sự kiện kỳ vọng** trước, bao gồm giá trị **không được xuất hiện**. Các điểm cần xác minh:

- **Membership:** join point mong đợi đều được chọn, loại trừ đều không xuất hiện.
- **Multiplicity:** mỗi join point có đúng số lần advice mong đợi.
- **Ordering:** `before -> target -> after`, hoặc các lớp around theo order đã công bố.
- **Preservation:** method vẫn được gọi số lần đúng, trả cùng giá trị, truyền đúng exception.
- **Scope:** chỉ artifact/class loader/đường gọi trong phạm vi weaving nhận instrumentation.
- **Stability:** khi refactor, test giúp nhận biết sự thay đổi selection thay vì im lặng.

Khi thứ tự event không ổn định do concurrency, không so sánh một chuỗi global tuyến tính nếu hợp đồng không yêu cầu thứ tự ấy. Dùng correlation ID theo invocation, tập multiset, partial order hoặc rào đồng bộ để xác nhận **quan hệ thứ tự có ý nghĩa**.

## 8. Positive, negative và boundary tests nên viết thế nào?

### 8.1. Positive tests

Mỗi thao tác được policy bao phủ phải có ít nhất một test rõ:

- Thực thi thành công.
- Thực thi ném exception nếu policy bao gồm lỗi.
- Gọi trực tiếp, gọi qua method khác hoặc qua interface nếu hợp đồng yêu cầu.
- Loại concrete class/implementation được áp dụng.
- Thao tác mới được thêm vào API cần được lựa chọn.
- Nếu có điều kiện runtime, cả trường hợp giá trị hợp lệ khiến pointcut match.

Tuy nhiên, không dùng “mọi method đều match” như tiêu chí bao phủ tốt. Pointcut an toàn là **đúng danh sách**, không phải danh sách dài nhất.

### 8.2. Negative tests

Các loại trừ nên được coi là một phần **hợp đồng không can thiệp**:

- Method chỉ có tên gần giống hoặc overload khác.
- Package phụ trợ/telemetry sink, để ngăn recursion.
- Internal helper không mang policy.
- Getter của entity hoặc method dùng trong đường đo lường.
- Các loại giao dịch/thao tác mà retry/cache/audit không được áp dụng.
- Method thuộc class cùng tên ở module/package khác.
- Những join point không thuộc control flow dự định (với `cflow`).
- Trường hợp annotation absent hoặc annotation đặt sai scope.

Một negative test đặc biệt quan trọng với bảo mật và dữ liệu: **không có log sensitive arguments** tại những method không thuộc chính sách.

### 8.3. Boundary tests

Chọn những ranh giới liên quan thật tới expression:

- `save(String)` vs `save(CharSequence)` vs `save(Object)`.
- `process()` vs `process(int)` vs `process(int...)`.
- Class cha định nghĩa method vs subclass override.
- Interface method vs implementation, annotation trên interface hay trên method implementation.
- Package `foo.app` vs subpackage `foo.app.internal`.
- Public vs package-private/private, static vs instance.
- Giá trị runtime `null`, subclass instance, proxy object hoặc đối số bất đồng bộ.
- Một method gọi nhiều lần trong recursion/nested call.

Không giả định các trường hợp trên match thế nào nếu chưa xác định **designator**, **pointcut language** và **cơ chế interception** đang sử dụng.

## 9. Annotation pointcut: vị trí khai báo và retention

Pointcut dựa vào annotation thường giúp biểu đạt contract rõ ràng hơn so với quy tắc tên method, ví dụ đánh dấu thao tác cần audit. Nhưng annotation có nhiều nơi xuất hiện:

- Annotation trên interface method.
- Annotation trên implementation method.
- Annotation trên class/base class.
- Annotation trên method override trong subclass.
- Annotation được giữ tới class file nhưng không có runtime retention.
- Annotation chỉ đặt ở parameter/type use khác với method.

Một ví dụ cú pháp AspectJ mang tính minh họa:

~~~java
// Cần khai báo annotation Audited trong dự án thực.
// Đây là biểu thức pointcut minh họa, không phải chương trình độc lập.
pointcut marked():
    execution(@Audited * *(..));
~~~

Ý nghĩa chính xác của pattern và nơi annotation được chọn cần được xác nhận bằng tài liệu của ngôn ngữ AOP đang dùng. Đừng mặc định annotation trên interface tự hiện diện ở method override hoặc annotation method được kế thừa như annotation class trong mọi cơ chế.

**Chiến lược test:** tạo fixture gồm một method annotated đúng, một method không annotated, một method override, một interface implementation; định nghĩa rõ từng expected match. Nếu đổi retention hoặc vị trí annotation, kiểm thử phải phát hiện.

## 10. Inheritance, overrides, interface và generic bridge

### 10.1. Kế thừa và override

Một pointcut sử dụng kiểu base có thể chọn hoặc không chọn method thực thi ở subclass, tùy **type pattern**, chữ ký được chọn và cơ chế AOP. Với `execution`, chú ý **method body thực sự chạy** và nơi body đó được weave; với `call`, chú ý kiểu/đích ở vị trí gọi.

Test gợi ý:

1. Gọi method kế thừa không override.
2. Gọi method đã override ở subclass.
3. Gọi qua biến có kiểu interface hoặc superclass.
4. Gọi `super.method()` trong implementation.
5. Gọi từ self-call trong class con.
6. Gọi method cùng tên nhưng không nằm trong hierarchy mong muốn.

Không chỉ test một method bằng reflection để suy ra mọi dispatch path.

### 10.2. Generics và synthetic bridge methods

Java dùng **type erasure**. Compiler có thể phát sinh **bridge method** để giữ đa hình khi override generic method. Đối với code AOP/weaving làm việc với bytecode, những method synthetic/bridge có thể ảnh hưởng số join point thực sự được nhìn thấy hoặc loại chữ ký được báo cáo.

Không nên đoán “một method trong source chắc chắn tương ứng một execution shadow duy nhất trong mọi compiler”. Hãy dùng test thực tế, báo cáo weave info và kiểm tra số advice hit trên invocation cụ thể khi policy phụ thuộc đúng một lần.

Nếu đổi compiler/JDK hoặc refactor generic hierarchy, chạy lại test pointcut regression. Nếu project có code generation hoặc annotation processing, kiểm thử trên **artifact cuối cùng** thay vì chỉ source fixture đơn giản.

## 11. Pointcut có điều kiện runtime và control flow

Một biểu thức chọn kiểu động có thể nhận kết quả khác nhau dù cùng static signature.

Ví dụ mục tiêu policy là can thiệp lời gọi trong **control flow** của một operation quan trọng. Khi đó `cflow(...)` có thể giúp mô tả phạm vi, nhưng test cần hai đường:

~~~text
entryImportant()
  -> helper()
      -> work()      => nằm trong cflow mong muốn

entryOrdinary()
  -> helper()
      -> work()      => không nằm trong cflow mong muốn
~~~

Test không chỉ gọi `work()` một mình: phải kích hoạt **cả hai cây lời gọi**. Với recursion, xem policy muốn một advice trên mỗi tầng hay chỉ một lần theo logical operation; điều này khác nhau và cần hợp đồng tường minh.

Với `args(SomeSubtype)`, test cả object là subclass, object không đúng kiểu, `null` và những lời gọi generic/reflection có khả năng xuất hiện trong hệ thống thực. Dynamic matching có thể tốn chi phí vì phải đánh giá khi chạy; đo overhead trên hot path nếu pointcut rộng.

Với pointcut có condition phụ thuộc external state, test phải kiểm soát state, clock và phiên bản policy để không bị flaky. Tối ưu hơn là giữ pointcut mô tả **nơi cần policy chạy**, còn phép kiểm tra actor/resource cụ thể được chuyển vào policy evaluator có unit test riêng.

## 12. Scope của weaving và proxy là một phần của kiểm thử

### 12.1. Aspect không hoạt động không có nghĩa expression sai

Nếu pointcut mô tả đúng `execution(...)` nhưng bytecode class đích chưa weave, advice vẫn không chạy. Tương tự, với `call(...)`, nếu caller không nằm trong phạm vi weave thì call join point không có advice. Với proxy, lời gọi không đi qua proxy có thể bỏ qua interception.

Do đó bài test phải có hai lớp:

1. **Kiểm tra pointcut/selection** với fixture chắc chắn nằm trong phạm vi công cụ.
2. **Kiểm tra pipeline/build/runtime** chứng minh class thật được chặn đúng lúc chạy.

Một bản test chạy trong IDE bằng một classpath khác với artifact đóng gói có thể cho kết quả khác. Kết quả chạy phải xác nhận classpath, phiên bản aspect, output sau weave và môi trường load class.

### 12.2. Compile-time, binary và load-time weaving

- **Compile-time weaving (CTW):** compiler/weaver kết hợp mã aspect trong quá trình build nguồn. Test chạy trên bytecode đã weave.
- **Post-compile / binary weaving:** weave file `.class`/JAR có sẵn; test cần đọc **output artifact**, không chỉ thư mục class gốc.
- **Load-time weaving (LTW):** weaver can thiệp khi class được định nghĩa; test startup phải có agent/config phù hợp và class chưa load quá sớm.

Trong LTW, **class loader delegation** có thể ảnh hưởng lớp nào được weaver thấy. Chỉ kiểm tra unit bằng compiler trong module riêng chưa chứng minh application server tải class theo cùng đường.

Bật thông tin weaving của công cụ (chẳng hạn tùy chọn `-showWeaveInfo` với `ajc`) giúp xác định join point được weave, nhưng **weave-info không thay thế behavior assertion**. Một join point có thể được weave mà advice vẫn chạy sai số lần hoặc làm hỏng semantics.

### 12.3. Self-invocation không có quy tắc chung cho mọi công cụ

Đừng viết assertion “self-call luôn bị chặn” hoặc “self-call luôn bypass” nếu chưa nói cơ chế:

- **Execution-based weaving:** nếu thân method đích được weave, self-call dẫn tới execution ấy vẫn kích hoạt advice.
- **Call-based weaving:** vị trí gọi trong caller phải được weave.
- **Proxy/decorator:** lời gọi trực tiếp bằng `this` bên trong target có thể bỏ qua wrapper/proxy bên ngoài.

Một test tốt ghi rõ **loại join point và cơ chế**, không áp một kết luận cho toàn bộ AOP.

## 13. Kiểm tra advice độc lập với điểm match

Ngay cả khi pointcut match đúng, advice vẫn có thể sai. Thiết kế fake target để kiểm tra:

| Thuộc tính | Điều cần xác minh |
| --- | --- |
| `proceed` | Được gọi đúng một lần trừ khi hợp đồng công khai cho phép retry/skip |
| Args | Đầu vào gốc không bị sửa nếu policy chỉ quan sát |
| Return | Kết quả đúng như target trả khi không có transformation hợp lệ |
| Exception | Exception gốc được truyền hoặc mapping theo contract |
| Cleanup | `finally`/after advice chạy đúng trên các đường cần thiết |
| Side effect | Không bị lặp vì around advice sai |
| Metrics | Số hit/advice count không bị nhầm với số logical operation |
| Thread safety | State của advice không rò giữa invocation đồng thời |
| Async | Terminal outcome được đo ở completion, không chỉ khi trả future |
| Recursion | Advice không tự gọi lại join point vô hạn |

Đặc biệt, `after returning` không chạy khi method ném exception. Để ghi lỗi, test `after throwing`; để cleanup, cân nhắc `after` hoặc around `finally`. Nếu test chỉ chạy đường thành công, thiếu trường hợp lỗi là một false confidence.

## 14. Test được thứ tự của nhiều aspect

Một join point có thể khớp cả tracing, authorization và metrics. Dù mỗi pointcut đúng độc lập, thứ tự có thể tạo semantics khác:

~~~text
Metrics -> Authorization -> Domain
         deny: metrics vẫn đếm request bị từ chối

Authorization -> Metrics -> Domain
         deny: metrics bên trong không chạy
~~~

Với caching:

~~~text
Authorization -> Cache -> Domain
         cache hit vẫn qua authorization

Cache -> Authorization -> Domain
         cache hit có thể bypass authorization
~~~

Với retry:

~~~text
Retry -> Transaction -> Domain
         mỗi attempt có thể có transaction riêng

Transaction -> Retry -> Domain
         nhiều attempt có thể nằm trong một transaction
~~~

**Kiểm thử composition** bằng event collector có thể xác nhận chain trước/sau, cùng số lần target thực thi, exception và side effect. Nếu aspect ordering/precedence được cấu hình, cần test trên cấu hình thật. Không mặc định thứ tự khai báo class, tên file hay thời gian load sẽ là thứ tự advice đã mong muốn.

Một bài pointcut selection test có thể cố định đúng tập match nhưng **không chứng minh hệ thống an toàn nếu một cache bên ngoài trả sớm trước kiểm tra quyền**. Đây là lý do cần integration test cho pipeline đầy đủ.

## 15. Mutation testing cho pointcut

Một cách đo sức mạnh của bộ test là **cố tình làm pointcut sai**:

- Đổi `save(String)` thành `save(..)`, test negative overload phải đỏ.
- Đổi `TaskService.save` thành `*Service.save` hoặc pattern rộng, test class khác phải đỏ nếu bị bắt.
- Đổi `execution` thành `call` trong fixture có self-call/caller chưa weave, test tương ứng phải phát hiện chênh lệch.
- Loại trừ sai một package, test positive phải đỏ.
- Tắt weaving, test integration phải đỏ.
- Đổi `after returning` sang advice khác, test success/error phải phát hiện thay đổi.
- Tăng lời gọi `proceed()` từ một lên hai, test side effect phải đỏ.

Đây là các **mutation có chủ đích trong môi trường kiểm thử**, không phải thay đổi production. Nếu bỏ/đổi pointcut mà mọi test vẫn xanh, tập expected có thể quá ít hoặc chỉ đang test code advice thay vì thực sự test selection.

Mutation testing cho pointcut đặc biệt hữu ích với một policy được áp rộng bằng wildcard: tạo nhiều loại mutation để phát hiện cả overmatching lẫn undermatching.

## 16. Tránh flaky test và dữ liệu kiểm thử không đáng tin

### 16.1. Đồng thời và bất đồng bộ

Khi nhiều luồng được chặn, event từ các invocation có thể xen kẽ. Một assertion `List.of(beforeA, afterA, beforeB, afterB)` có thể sai nếu execution hợp lệ thực sự đan xen:

~~~text
before A
before B
after B
after A
~~~

Dùng correlation ID theo invocation và khẳng định **happens-before** cần thiết, thay vì đòi thứ tự global vốn không có trong contract. Với callback async, `after returning` trên method trả `CompletionStage` không tự chứng minh nghiệp vụ hoàn tất. Test cần chờ completion có kiểm soát, phân biệt terminal event với return-handle event và đảm bảo không double close.

### 16.2. Recorder và fake

Trong fixture tuần tự, một `ArrayList` là đủ để kiểm chứng chuỗi event. Trong test song song, collector cần thread-safe hoặc đồng bộ đúng. Không dùng log bên ngoài có sampling, async batching hoặc rate limiter làm nguồn khẳng định duy nhất số hit của pointcut; nó có thể cố ý bỏ dữ liệu.

Nên có một **probe đơn giản, không lọc/sampling**, được gọi từ advice ở môi trường test; sử dụng assert trên probe. Đừng áp cùng pointcut vào code recorder, tránh instrumentation recursion.

### 16.3. Kiểm soát classpath và trạng thái chung

- Chạy trên artifact được weave thực, không lẫn class gốc cùng tên trên classpath.
- Reset/khởi tạo event collector trước test; không để static state từ case trước lọt sang case sau.
- Xác minh compiler/JDK, class loader và phiên bản AOP tool dùng trong CI.
- Tránh phụ thuộc thứ tự test của framework.
- Không dựa vào `Thread.sleep` để hy vọng một callback đúng lúc.
- Với aspect có state per-target/per-flow, kiểm tra cleanup để tránh ảnh hưởng giữa test.

## 17. Quy trình CI kiểm chứng pointcut

Một pipeline bảo đảm tốt nên gồm:

1. **Compile code + aspect** hoặc cấu hình weaving runtime theo cách sản phẩm thực sẽ dùng.
2. **Bật diagnostics về weaving** ở môi trường CI phù hợp; lưu danh sách join point/weaver warnings để so sánh khi đổi build.
3. **Run positive/negative/boundary selection tests** trên class được weave.
4. **Run advice behavior tests** kiểm tra proceed, return, throw, cleanup và số lần gọi.
5. **Run composition tests** với cache, security, retry, transaction, tracing nếu có.
6. **Run bypass tests** qua self-call, direct access, proxy boundary, async và các đường gọi tin cậy khác.
7. **Run regression tests** khi đổi package, signature, annotation, compiler hoặc dependency.
8. **Benchmark overhead** nếu pointcut mới chọn nhiều method hơn; quan sát impact của logging/metrics trên hot path.
9. **Review kết quả diff coverage:** join point mới được chọn có được yêu cầu chấp thuận không? Join point cũ mất đi có được phép không?
10. **Kiểm thử artifact cuối** đóng gói/deploy thay vì chỉ một bản class dùng trong test.

Nếu dùng weaving ở startup, test chỉ chạy với `ajc` compile-time là chưa đủ để chứng minh agent/class loader trong production hoạt động. Hãy có ít nhất một integration test cùng mô hình startup thích hợp.

### 17.1. Một phép kiểm kê đơn giản

Mỗi pointcut quan trọng có thể đi kèm bảng như:

| Mã | Phạm vi mong đợi | Exclusions | Loại test |
| --- | --- | --- | --- |
| PC-1 | Public execution của method theo policy | Overload không thuộc policy, helper | Selection test |
| PC-2 | Method có annotation audit đúng vị trí | Method không annotated, override không phù hợp | Annotation fixture |
| PC-3 | Join point trong control flow của operation | Cùng method ngoài flow | Dynamic/cflow fixture |
| PC-4 | Chính sách kiểm tra quyền tại API boundary | Bypass qua cache/proxy/self-call | Integration/security test |
| PC-5 | Span đo hoàn tất thao tác async | Chỉ trả handle không tính terminal success | Completion lifecycle test |

Bảng kiểm kê không thay thế tests; nó giúp review **phạm vi mong đợi** trước khi viết một expression rất rộng và khó diễn giải.

## 18. Các sai lầm thường gặp

| Sai lầm | Hệ quả | Cách khắc phục |
| --- | --- | --- |
| Chỉ test một method đúng tên | Không phát hiện overload/subclass bị chọn nhầm | Bảng match và no-match rõ |
| Chỉ assert advice chạy `>=1` lần | Không phát hiện advice chạy thừa/thiếu | Assert tập và multiplicity |
| Test pointcut trên code không weave | False failure hoặc nhầm tưởng advice hỏng | Xác nhận artifact/classpath/weaving |
| Dùng `call` nhưng chỉ weave target method | Không chặn call site trong caller | Weave caller hoặc chọn `execution` theo contract |
| Giả định self-call giống nhau ở mọi AOP | Test sai cơ chế interception | Xác định join point + proxy/weaving |
| Wildcard package quá rộng | Chặn helper, telemetry, method nhạy cảm | Scope có contract/exclusion + negative tests |
| Chỉ kiểm tra thành công | Không biết after throwing/finally đúng không | Test lỗi, return và cleanup |
| Sao chép pointcut vào logic tính expected | Test và implementation sai giống nhau | Viết matrix độc lập từ yêu cầu |
| Bỏ qua static/bridge/generic edge cases | Double hit hoặc miss khó giải thích | Test artifact cuối và weave diagnostics |
| Dựa vào log đã sampling | Đếm sai advice hits | Test probe không bị drop |
| So event global của nhiều thread | Flaky vì scheduler | Correlation ID, partial order |
| Chỉ unit-test policy, không test scope | Chính sách đúng nhưng không bao phủ đường vào | Selection + integration/bypass |
| Không test sau refactor signature/package | Silent break của pointcut | Regression tests trong CI |

## 19. Checklist thực hành

Trước khi coi một pointcut “đúng”, xác minh:

1. **Yêu cầu:** danh sách join point *phải match* và *không được match* được định nghĩa độc lập với expression chưa?
2. **Loại điểm:** method `execution`, `call`, constructor, field hay event khác? Có chọn đúng loại không?
3. **Chữ ký:** return, parameter types/count, visibility, static/instance, overload đã được tính đến chưa?
4. **Hierarchy:** interface/override/inheritance/generics/bridge có làm thay đổi kết quả không?
5. **Annotation:** annotation được đặt và giữ ở nơi nào? Có được match theo rule thật không?
6. **Dynamic conditions:** `args`, `this`, `target`, `cflow` và value runtime đã có cả positive/negative path chưa?
7. **Weaving:** class hoặc call site thật có được weave? Cấu hình loader/startup có bao phủ không?
8. **Số lần chạy:** advice chạy đúng multiplicity, đúng thứ tự và không bị đếm trùng?
9. **Behavior:** target gọi bao nhiêu lần, có bị đổi args/return/exception/cleanup ngoài hợp đồng?
10. **Composition:** cache hit, authorization deny, retry, transaction, fallback và async completion có làm skip advice sai không?
11. **CI:** đổi signature, thêm method, nâng compiler hoặc chỉnh pointcut có kích hoạt regression test đáng tin?
12. **Bảo mật/hiệu năng:** không chọn nhầm sensitive method, không gây recursion, không bùng nổ overhead trên hot path?

**Kết luận:** kiểm thử pointcut đúng nghĩa là kiểm thử **tập join point và các đường loại trừ** ở artifact thực tế. Điểm mạnh của AOP là một biểu thức có thể áp chính sách nhất quán ở nhiều nơi; điểm rủi ro cũng chính là khả năng ấy. Vì vậy, đừng chỉ chứng minh advice **có chạy** — hãy chứng minh nó **chạy đúng nơi, không chạy sai nơi, chạy đúng số lần và không làm thay đổi hợp đồng nghiệp vụ ngoài ý muốn**.
