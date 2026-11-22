# Aspect bằng cú pháp chuyên biệt và bằng annotation trong AspectJ

## 1. Tổng quan và mục tiêu

**Aspect-Oriented Programming (AOP)** cho phép mô tả những hành vi cắt ngang nhiều module, chẳng hạn quan sát lời gọi, ghi audit, áp chính sách và đo thời gian, bằng **aspect**, **pointcut** và **advice**. **AspectJ** mở rộng khả năng diễn đạt AOP của Java và cung cấp compiler/weaver để gắn các hành vi này vào các vị trí chương trình phù hợp.

Một kiến thức quan trọng khi học AspectJ là **cùng một aspect có thể được biểu diễn theo hai phong cách**:

1. **Code-style**: cú pháp ngôn ngữ AspectJ chuyên biệt dùng `aspect`, `pointcut`, `before`, `after`, `around` và `declare`. File thường mang đuôi `.aj`, phải được công cụ hiểu cú pháp AspectJ xử lý.
2. **Annotation-style (@AspectJ)**: aspect là một lớp Java gắn `@Aspect`; khai báo điểm chặn bằng `@Pointcut`; advice bằng `@Before`, `@AfterReturning`, `@AfterThrowing`, `@After`, `@Around`. Java compiler có thể biên dịch class annotation phù hợp, nhưng advice chỉ có hiệu lực khi AspectJ **weave** bytecode.

Bài này tập trung vào **AOP nói chung với AspectJ**, bao gồm kiến thức cơ bản và cơ chế nâng cao. Sau khi học, bạn có thể:

- Đối chiếu chính xác phần tử của hai cú pháp.
- Hiểu `execution`, `call`, bind `args`, nhận return value và phân biệt các loại advice.
- Chạy hai phiên bản aspect có cùng join point/advice trên Java 17.
- Giải thích vì sao chỉ có `@Aspect` và chạy `javac` chưa đủ để bật advice.
- Chọn đúng thời điểm weaving: compile-time, binary/post-compile và load-time.
- Biết khi nào code-style có khả năng biểu đạt tốt hơn đối với inter-type declaration, `declare` và privileged aspects.
- Tránh các lỗi về signature, binding tên tham số, overloading, thứ tự advice, aspect scope và concurrency.

**Điều cần nhớ từ đầu:** lựa chọn code-style hay annotation-style là lựa chọn **cách khai báo source**. Nó độc lập với việc dùng compile-time hay load-time weaving và không tự xác định tập join point nào sẽ hoạt động.

## 2. Những thành phần AOP được biểu diễn

| Thuật ngữ | Ý nghĩa | Ví dụ |
|---|---|---|
| **Join point** | Một điểm/sự kiện thực thi mà AspectJ có thể quan sát | Execution của `TaskService.perform` |
| **Pointcut** | Quy tắc chọn join point và, nếu cần, bind ngữ cảnh | `execution(String TaskService.perform(String))` |
| **Advice** | Hành vi chạy tại join point đã chọn | In `enter` trước method |
| **Aspect** | Đơn vị đóng gói pointcut, advice, state và khai báo liên quan | `NativeTrace` hoặc `AnnotationTrace` |
| **Weaving** | Tích hợp hành vi advice vào bytecode mục tiêu | `ajc` compile và weave `TaskService` |
| **Target** | Lớp/phương thức thực thi nghiệp vụ | `TaskService.perform` |
| **Static crosscutting** | Tác động tới cấu trúc kiểu hoặc báo lỗi kiến trúc | Inter-type method, `declare warning` |

Một lời gọi sau weaving có thể được xem là:

```text
App.main()
  |
  +--> TaskService.perform("A-7")
         |-- before advice: enter:A-7
         |-- method body: return "done:A-7"
         |-- after returning advice: exit:done:A-7
       App in result: done:A-7
```

Aspect không chỉ là “wrapper gọi hàm”. Với bytecode weaving, AspectJ có thể nhận diện nhiều loại join point, bao gồm execution, call và một số thao tác khác trong phạm vi mà weaver kiểm soát. Không giả định mọi công cụ AOP đều hỗ trợ tất cả loại join point này.

## 3. Cú pháp code-style: ngôn ngữ AspectJ

Một tệp `.aj` có thể chứa khai báo:

```java
// Đây là cú pháp AspectJ, không phải Java thuần cho javac.
public aspect ExampleAspect {
    pointcut selected():
        execution(* demo.Service.execute(..));

    before(): selected() {
        System.out.println("before");
    }

    after() returning: selected() {
        System.out.println("success");
    }
}
```

Ý nghĩa các phần:

- `public aspect ExampleAspect` khai báo một **aspect type**. Theo mặc định, nó theo mô hình instance singleton, trừ khi có per-clause khác.
- `pointcut selected(): ...;` đặt tên một quy tắc. Dấu `:` ngăn formal part với pointcut expression.
- `execution(* demo.Service.execute(..))` match việc thực thi method `execute` của type được chỉ định; `*` là return type bất kỳ và `..` trong danh sách đối số thể hiện số lượng/kiểu tham số bất kỳ.
- `before(): selected() { ... }` chạy trước join point.
- `after() returning: selected() { ... }` chạy khi join point kết thúc bình thường. Nếu có exception, advice kiểu `returning` không phải nhánh ghi lỗi.
- Nếu cần nắm kết quả trả về, có thể khai báo biến binding trong `returning(...)`.

Đây là **phần mở rộng ngôn ngữ Java**, nên `javac` không biên dịch được file chứa `aspect` hoặc cú pháp advice chuyên biệt. Sử dụng `ajc` để biên dịch các nguồn này và weave những lớp đích cần thiết.

## 4. Cú pháp annotation-style: Java class có metadata AspectJ

Một ví dụ tương ứng:

```java
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;
import org.aspectj.lang.annotation.Pointcut;

@Aspect
public class ExampleAnnotationAspect {
    @Pointcut("execution(* demo.Service.execute(..))")
    public void selected() {}

    @Before("selected()")
    public void beforeSelected() {
        System.out.println("before");
    }
}
```

Đặc điểm:

- `@Aspect` thuộc namespace `org.aspectj.lang.annotation` và đánh dấu một lớp Java là aspect để AspectJ weaver xử lý.
- `@Pointcut` được khai báo trên Java method, có **thân rỗng**. Đây là một tên pointcut, không phải method nghiệp vụ phải gọi để kích hoạt advice.
- `@Before` nhận một pointcut expression trong chuỗi; `"selected()"` tham chiếu pointcut đã đặt tên.
- Các advice khác được biểu diễn bởi annotation riêng; phần thân advice là Java method.
- Class này có thể compile bằng `javac` nếu đã có AspectJ runtime API trên classpath và code không dùng cú pháp ngôn ngữ mở rộng.
- **Compilation và weaving là hai công việc khác nhau**: biên dịch ra class với annotation chưa tự sửa bytecode của target.

Hai phong cách có thể tạo cùng semantics khi được weaver xử lý đúng. Annotation-style hữu ích nếu muốn dùng các công cụ biên tập Java thông thường và tách giai đoạn compile source khỏi weave các class đã biên dịch.

## 5. Đối chiếu cấu trúc giữa hai phong cách

| Nhiệm vụ | Code-style | Annotation-style |
|---|---|---|
| Aspect | `public aspect X { }` | `@Aspect public class X { }` |
| Pointcut có tên | `pointcut work(): expression;` | `@Pointcut("expression") void work() {}` |
| Trước join point | `before(): work() { }` | `@Before("work()") void before() { }` |
| Sau thành công | `after() returning: work() { }` | `@AfterReturning("work()") void after() { }` |
| Sau khi lỗi | `after() throwing: work() { }` | `@AfterThrowing("work()") void afterError() { }` |
| Sau join point nói chung | `after(): work() { }` | `@After("work()") void after() { }` |
| Around | `T around(...): work(...) { return proceed(...); }` | `@Around("work(...)") Object around(ProceedingJoinPoint p) throws Throwable` |
| Join point hiện tại | `thisJoinPoint` | Tham số `JoinPoint` / `ProceedingJoinPoint` |
| Bind đối số | Formal trong `pointcut`/advice và `args(...)` | Formal Java method trong `@Pointcut`/advice |
| Thêm inter-type method | Cú pháp khai báo trực tiếp được hỗ trợ | Không viết trực tiếp cùng cú pháp bằng Java thuần; có cơ chế annotation hỗ trợ một số dạng |
| Quy tắc kiến trúc | Các `declare` của AspectJ | Một số `@Declare...`, tùy loại và phiên bản |
| Compile source | Cần compiler hiểu cú pháp AspectJ | Có thể compile bằng `javac` với phụ thuộc phù hợp |
| Kích hoạt advice | Weaving | **Vẫn phải weaving** |

Không xem bảng là một bản dịch “thay từ khóa bằng annotation” cho mọi tính năng. Code-style có những khả năng tĩnh mà Java annotation không thể mô tả hoàn toàn, trong khi việc cấu hình metadata và bind formal của annotation-style có những yêu cầu riêng.

## 6. Ví dụ chạy được: cùng thao tác, hai cách viết

Để so sánh công bằng, hãy dùng **cùng hai file nghiệp vụ** và compile **hai aspect vào hai output directory tách biệt**. Như vậy không có chuyện hai aspect đồng thời in log khiến ta tưởng một aspect chạy hai lần.

Tạo các file sau trong cùng thư mục làm việc.

### TaskService.java

```java
public class TaskService {
    public String perform(String id) {
        return "done:" + id;
    }
}
```

`TaskService.perform("A-7")` trả chuỗi `done:A-7` và không tự ghi log. Không cần sửa mã nghiệp vụ để thêm advice.

### App.java

```java
public class App {
    public static void main(String[] args) {
        System.out.println(new TaskService().perform("A-7"));
    }
}
```

Khi chạy `App` với `TaskService` chưa được weave, stdout chỉ gồm:

```text
done:A-7
```

### NativeTrace.aj — Code-style

```java
public aspect NativeTrace {
    pointcut operation(String id):
        execution(String TaskService.perform(String)) && args(id);

    before(String id): operation(id) {
        System.out.println("enter:" + id);
    }

    after(String id) returning(String result): operation(id) {
        System.out.println("exit:" + result);
    }
}
```

Phân tích:

1. `pointcut operation(String id)` có formal `id` kiểu `String`.
2. `execution(String TaskService.perform(String))` match chính xác việc thực thi method nhận một `String` và trả `String`.
3. `args(id)` bind đối số runtime vào formal của pointcut.
4. `before(String id): operation(id)` nhận giá trị đã bind và in `enter:A-7`.
5. `after(String id) returning(String result): operation(id)` chạy sau khi method thành công; bind kết quả vào `result`.
6. Phần mã nghiệp vụ trả lại `done:A-7` cho `App`, rồi `App` in dòng cuối.

Nếu body ném ngoại lệ, `after returning` không thực thi; muốn ghi lỗi thì dùng `after throwing` hoặc around advice theo hợp đồng.

### AnnotationTrace.java — Annotation-style

```java
import org.aspectj.lang.annotation.AfterReturning;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;
import org.aspectj.lang.annotation.Pointcut;

@Aspect
public class AnnotationTrace {
    @Pointcut("execution(String TaskService.perform(String)) && args(id)")
    public void operation(String id) {}

    @Before("operation(id)")
    public void before(String id) {
        System.out.println("enter:" + id);
    }

    @AfterReturning(pointcut = "operation(id)", returning = "result")
    public void after(String id, String result) {
        System.out.println("exit:" + result);
    }
}
```

Cấu trúc tương ứng:

- `@Pointcut("... && args(id)")` khai báo điểm chặn và tên formal được bind.
- `@Before("operation(id)")` chọn cùng tập execution join point.
- `@AfterReturning(pointcut = "operation(id)", returning = "result")` lấy return value vào tham số method tên `result`.
- Method advice là method Java bình thường về cú pháp, nhưng để nó được tự động gọi tại join point thì **weaver** phải nhận ra annotation và xử lý class đích.
- Tên `result` trong annotation cần khớp với tên formal; thiếu metadata tên tham số ở một số quy trình compile riêng rẽ có thể khiến binding thất bại.

Đây là một trường hợp hai phong cách có **ngữ nghĩa quan sát giống nhau**.

## 7. Cài đặt công cụ và cách chạy trên Java 17

Các ví dụ ở trên đã được kiểm tra bằng **AspectJ 1.9.24** với `-17`, và chạy trên JVM có hỗ trợ Java 17 trở lên. Cần có `aspectjtools` (chứa compiler `ajc`) và `aspectjrt` ở giai đoạn thích hợp.

Có thể tải hai dependency bằng Maven:

```bash
mvn -B dependency:get -Dartifact=org.aspectj:aspectjtools:1.9.24 -Dtransitive=false
mvn -B dependency:get -Dartifact=org.aspectj:aspectjrt:1.9.24 -Dtransitive=false
```

Lệnh được viết để sử dụng local Maven repository mặc định. Nếu cấu hình của môi trường dùng repository khác, hãy điều chỉnh đường dẫn jar tương ứng.

### 7.1. Windows PowerShell: compile và chạy code-style

```powershell
$repo = Join-Path $HOME ".m2/repository/org/aspectj"
$tools = Join-Path $repo "aspectjtools/1.9.24/aspectjtools-1.9.24.jar"
$rt = Join-Path $repo "aspectjrt/1.9.24/aspectjrt-1.9.24.jar"

New-Item -ItemType Directory -Force out-native | Out-Null
java -cp $tools org.aspectj.tools.ajc.Main -17 -classpath $rt -d out-native App.java TaskService.java NativeTrace.aj
java -cp "out-native;$rt" App
```

### 7.2. Windows PowerShell: compile và chạy annotation-style

```powershell
New-Item -ItemType Directory -Force out-annotation | Out-Null
java -cp $tools org.aspectj.tools.ajc.Main -17 -classpath $rt -d out-annotation App.java TaskService.java AnnotationTrace.java
java -cp "out-annotation;$rt" App
```

**Kết quả stdout đã kiểm tra của cả hai cách:**

```text
enter:A-7
exit:done:A-7
done:A-7
```

Các tùy chọn:

- `-17`: chọn mức ngôn ngữ Java 17 cho `ajc`.
- `-classpath $rt`: cung cấp AspectJ runtime API khi compile/weave.
- `-d out-native` hoặc `-d out-annotation`: giữ output riêng để **không weave chồng hai aspect tương đương**.
- `java -cp "out-native;$rt" App`: chạy class đã weave và có runtime API trên classpath.

Trên Linux/macOS, classpath dùng dấu `:` thay cho `;`. Ví dụ Bash:

```bash
REPO="$HOME/.m2/repository/org/aspectj"
TOOLS="$REPO/aspectjtools/1.9.24/aspectjtools-1.9.24.jar"
RT="$REPO/aspectjrt/1.9.24/aspectjrt-1.9.24.jar"

mkdir -p out-native out-annotation
java -cp "$TOOLS" org.aspectj.tools.ajc.Main -17 -classpath "$RT" -d out-native App.java TaskService.java NativeTrace.aj
java -cp "out-native:$RT" App

java -cp "$TOOLS" org.aspectj.tools.ajc.Main -17 -classpath "$RT" -d out-annotation App.java TaskService.java AnnotationTrace.java
java -cp "out-annotation:$RT" App
```

Các lệnh cần chạy tại thư mục chứa bốn file source, nhưng **mỗi lần compile chỉ đưa vào ba file cần thiết**.

## 8. Biên dịch annotation bằng javac chưa có nghĩa là đã weave

Để thấy khác biệt này, có thể biên dịch cả ba file Java bằng `javac` trước, rồi chạy ứng dụng:

```powershell
New-Item -ItemType Directory -Force out-javac, out-woven | Out-Null
javac --release 17 -g -parameters -cp $rt -d out-javac App.java TaskService.java AnnotationTrace.java
java -cp "out-javac;$rt" App
```

Stdout là:

```text
done:A-7
```

Không thấy `enter` và `exit` vì các class mới chỉ **được biên dịch Java**, chưa được weave. Sau đó dùng `ajc` để weave bytecode:

```powershell
java -cp $tools org.aspectj.tools.ajc.Main -17 -classpath "out-javac;$rt" -inpath out-javac -aspectpath out-javac -d out-woven
java -cp "out-woven;$rt" App
```

Kết quả sau weaving:

```text
enter:A-7
exit:done:A-7
done:A-7
```

Trong quy trình này:

- `-inpath out-javac` chỉ định các class đầu vào cần weave.
- `-aspectpath out-javac` giúp tìm compiled aspects để áp dụng.
- `-d out-woven` ghi kết quả ra thư mục mới, dễ phân biệt class gốc và class đã weave.
- `-g -parameters` giữ metadata hữu ích cho việc bind tên formal của pointcut/advice. Đã kiểm tra rằng bỏ metadata này trong quy trình demo có thể gây lỗi binding lúc weave.

Đừng nhầm `-aspectpath` với mọi dependency của ứng dụng; vẫn phải quản lý classpath cần thiết. Với build có nhiều module, tập class target và tập aspect có thể nằm ở các output riêng.

## 9. Ba thời điểm weaving và cách chúng liên quan cú pháp

| Cơ chế | Hoạt động | Lưu ý |
|---|---|---|
| **Compile-time weaving (CTW)** | `ajc` đọc source Java/AspectJ, compile và weave thành class | Cần đưa đủ target/aspect source vào build |
| **Binary/post-compile weaving** | `ajc` đọc `.class`/jar đã compile, chèn advice và xuất class mới | Tránh trộn class woven với class chưa woven hoặc weave trùng |
| **Load-time weaving (LTW)** | Weaver can thiệp khi JVM nạp class | Cần agent/config/classloader phù hợp; chỉ có runtime jar là chưa đủ |

`aspectjweaver` là thành phần phổ biến cho LTW; cấu hình triển khai thường dùng `-javaagent` và tệp cấu hình aspect, ví dụ `META-INF/aop.xml`. Đây là cơ chế riêng với `javac`/`ajc` compile ở build time.

Sơ đồ:

```text
Code-style .aj + Java target --ajc--> woven classes --> JVM

Annotation .java + Java target --ajc--> woven classes --> JVM

Annotation .java --javac--> plain classes --ajc(binary weave)--> woven classes --> JVM

Java/Aspect classes --> classloader + AspectJ weaving agent --> loaded woven classes
```

**Cả code-style lẫn annotation-style có thể được xử lý qua weaving phù hợp.** Không kết luận code-style bắt buộc dùng compile-time hay annotation-style bắt buộc dùng load-time.

## 10. Pointcut: cú pháp chung, ngữ nghĩa join point

Cả hai phong cách dùng **cùng ý tưởng về biểu thức pointcut**. Những designator tiêu biểu:

| Designator | Chọn theo |
|---|---|
| `execution(...)` | Execution của method thỏa chữ ký |
| `call(...)` | Vị trí gọi method; cần weave bytecode phía caller |
| `args(x)` | Tham số runtime và bind giá trị |
| `this(x)` | Ngữ cảnh đối tượng `this` theo join point |
| `target(x)` | Đối tượng đích theo join point |
| `within(TypePattern)` | Lexical type scope |
| `withincode(Signature)` | Lexical code body chứa join point |
| `@annotation(a)` | Annotation liên quan join point và có thể bind |
| `cflow(p)` / `cflowbelow(p)` | Ngữ cảnh luồng điều khiển theo ngữ nghĩa AspectJ |

**`execution` khác `call`**: advice ở phần thực thi của method không đồng nghĩa advice tại mọi call site. Một class caller chưa được weave có thể không có `call` advice, trong khi class target đã weave có thể có `execution` advice.

Giữa các kiểu join point, `this` và `target` có thể khác nhau. Không dùng interchangeably khi kiểm tra quyền hay trích principal/target. Với pointcut phụ thuộc annotation, phải biết annotation đặt ở interface, implementation, method override hay class; không được suy rằng Java tự kế thừa annotation method trên mọi nhánh override.

`args(id)` trong ví dụ nhận dữ liệu để advice in `enter:A-7`. Đối số thật có thể là token hoặc nội dung nhạy cảm; chỉ render allowlisted fields và giới hạn kích thước trước khi log.

## 11. Bind đối số, kết quả và lỗi

Ở code-style:

```java
// Snippet AspectJ; phụ thuộc pointcut/workspace phù hợp.
after(String id) returning(String value): operation(id) {
    System.out.println(value);
}
```

Ở annotation-style:

```java
// Snippet bên trong class @Aspect với pointcut operation(String).
@org.aspectj.lang.annotation.AfterReturning(
    pointcut = "operation(id)", returning = "value")
public void onSuccess(String id, String value) {
    System.out.println(value);
}
```

Cần chú ý tên `value` trong phần `returning` và tên tham số advice. Nếu pointcut biểu diễn một phương thức `void` thì không thể coi return value như một `String` không tồn tại. Trong một số môi trường, tên argument trong annotation có thể cần `argNames` hoặc debug/parameter metadata. Test đúng toolchain đã dùng, thay vì trông cậy IDE sẽ đoán chính xác.

Những đường kết thúc:

- **Before:** chạy trước join point.
- **After returning:** chỉ chạy khi kết thúc bình thường, có thể nhận result.
- **After throwing:** chạy khi ném exception, có thể nhận Throwable phù hợp.
- **After:** thực thi sau join point theo ngữ nghĩa cleanup/finally.
- **Around:** bao cả lời gọi, có quyền thực hiện `proceed`, đo thời gian, wrap hoặc thay return nếu hợp đồng cho phép.

Sự khác biệt này là ngữ nghĩa AOP, không thay đổi chỉ vì code được viết bằng `@AfterReturning` hay `after() returning`.

## 12. Around advice trong hai phong cách

Code-style dùng phép `proceed` đặc biệt:

```java
// Snippet .aj; chỉ dùng riêng nếu có TaskService được weave.
public aspect AroundNative {
    pointcut selected(): execution(String TaskService.perform(String));

    String around(): selected() {
        long start = System.nanoTime();
        try {
            return proceed();
        } finally {
            System.out.println("elapsed_ns=" + (System.nanoTime() - start));
        }
    }
}
```

Annotation-style dùng đối tượng `ProceedingJoinPoint`:

```java
// Snippet là method bên trong một class có @Aspect.
@org.aspectj.lang.annotation.Around(
    "execution(String TaskService.perform(String))")
public Object around(org.aspectj.lang.ProceedingJoinPoint joinPoint)
        throws Throwable {
    long start = System.nanoTime();
    try {
        return joinPoint.proceed();
    } finally {
        System.out.println("elapsed_ns=" + (System.nanoTime() - start));
    }
}
```

**Các snippet này là minh họa bổ sung**, không thuộc hai chương trình đã test tại mục 6. Giá trị `elapsed_ns` biến đổi từng lần chạy, nên không có stdout cố định.

Quy tắc:

1. Nếu around advice không gọi `proceed`, phần thân target có thể không chạy; đó có thể là hành vi cố ý (từ chối quyền, cache hit) nhưng phải có hợp đồng rõ.
2. Một số chính sách retry có thể gọi `proceed` nhiều lần khi công cụ hỗ trợ; điều đó đòi hỏi thao tác an toàn khi lặp và input có thể replay.
3. Return type và exception phải phù hợp join point; sai kiểu, nuốt lỗi hoặc wrap không kiểm soát có thể làm sai nghiệp vụ.
4. `finally` quanh một method trả future chỉ bao thời gian **tạo/trả handle**, không tự đo toàn bộ thời gian completion.
5. Việc bind args và truyền args mới vào `proceed(..)` có quy tắc của AspectJ; không đổi dữ liệu nghiệp vụ chỉ để phục vụ telemetry.

## 13. Cấu trúc nâng cao và giới hạn annotation-style

Code-style có thể dùng các cấu trúc **static crosscutting** mà Java không thể viết trực tiếp bằng cú pháp thông thường.

Ví dụ khai báo inter-type method và warning kiến trúc:

```java
// Snippet cú pháp .aj; cần các type bên dưới tồn tại trong build.
public aspect AddCapabilities {
    public String TaskService.auditCategory() {
        return "task";
    }

    declare warning:
        call(* java.lang.System.exit(..)):
        "Do not terminate an application from business code";
}
```

**Inter-type declaration (ITD)** có thể thêm method, field hoặc constructor vào type đích khi được weave. `declare parents` thay đổi quan hệ supertype/interface theo loại khai báo được hỗ trợ. `declare warning` và `declare error` áp các ràng buộc kiến trúc. `declare precedence` xác định thứ tự aspect.

Annotation-style có những công cụ như `@DeclareParents`, `@DeclareMixin`, `@DeclareWarning`, `@DeclareError` và `@DeclarePrecedence`. **Điều này không có nghĩa toàn bộ cú pháp code-style được dịch 1:1 sang annotation**:

- Trong Java class có `@Aspect`, bạn không thể viết trực tiếp cú pháp `public String TaskService.auditCategory()` của code-style.
- Annotation-style không có khai báo `privileged aspect` tương đương đầy đủ.
- Một số cấu trúc như `declare soft`, `declare parents extends` hoặc khai báo bổ sung annotation có hạn chế theo phiên bản/trình biên dịch; cần đối chiếu tài liệu của bản AspectJ đang dùng.
- Mọi khai báo inter-type vẫn cần quyền weave bytecode của target. Không phải cứ viết annotation là có thể thay đổi bất kỳ class nào, nhất là class đã load hoặc class thư viện không nằm trong phạm vi weaver.

Vì vậy, khi cần khả năng **thay đổi cấu trúc type** hoặc diễn đạt quy tắc tĩnh rất đặc biệt, code-style thường trực tiếp hơn. Khi chỉ cần pointcut/advice, annotation-style là một cách biểu đạt rõ ràng và thân thiện với môi trường Java.

## 14. Aspect instance và state

Aspect mặc định theo mô hình singleton, nhưng AspectJ còn hỗ trợ các mô hình instance gắn theo đối tượng hoặc luồng điều khiển, chẳng hạn `perthis`, `pertarget`, `percflow` và `percflowbelow` theo ràng buộc của weaver.

Code-style minh họa:

```java
// Snippet AspectJ cần demo.Service tồn tại.
public aspect PerObjectTrace
    perthis(execution(* demo.Service.perform(..))) {
}
```

Annotation-style có thể mô tả một số per-clause qua thuộc tính `@Aspect`:

```java
// Snippet Java annotation phụ thuộc demo.Service.
@org.aspectj.lang.annotation.Aspect(
    "perthis(execution(* demo.Service.perform(..)))")
public class PerObjectTrace {
}
```

**Không đặt dữ liệu request vào field mutable của singleton aspect** mà không có cơ chế scope/đồng bộ, bởi nhiều thread có thể chạy advice đồng thời. `percflow` liên quan luồng điều khiển; không giả định context tự truyền sang task được đưa vào executor khác. Với asynchronous context, phải có chính sách capture/install/restore riêng.

Một cơ chế per-clause không thể tạo mọi aspect instance nếu target bytecode cần thiết không nằm trong phạm vi weaver được phép xử lý.

## 15. Thứ tự advice và phối hợp nhiều aspect

Khi nhiều aspect cùng match một join point, thứ tự ảnh hưởng kết quả:

```text
Authorization -> Transaction -> Retry -> Business
```

Khác với:

```text
Retry -> Transaction -> Authorization -> Business
```

Cần xác định ai chạy trước, ai đo thời gian cho một logical operation, retry có lặp toàn transaction hay không, và bao nhiêu lần audit được phát ra. AspectJ có cơ chế khai báo precedence thích hợp; code-style có `declare precedence`, annotation-style có `@DeclarePrecedence` trong phạm vi được hỗ trợ.

**Không đoán thứ tự** dựa trên tên file, thứ tự import hay vị trí annotation. Thiết lập thứ tự minh bạch khi thứ tự có ý nghĩa, rồi xác minh bằng integration test. Nếu compile hai ví dụ `NativeTrace` và `AnnotationTrace` vào cùng một output và cả hai được weave, cùng một lời gọi có thể in log thừa; đó không phải bằng chứng một phong cách bị “gọi hai lần” tự nhiên.

## 16. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách khắc phục |
|---|---|---|
| Có `@Aspect` nhưng log không chạy | Chỉ compile Java mà chưa weave | Kiểm tra bước `ajc`/agent và class đã weave |
| `ajc` báo thiếu formal binding | Thiếu tên tham số/debug metadata khi dùng `javac` trước | Biên dịch với `-g -parameters` hoặc cấu hình binding hỗ trợ và test |
| `javac` báo lỗi với `aspect` | Tệp `.aj` dùng cú pháp ngôn ngữ mở rộng | Dùng `ajc` |
| Log bị lặp | Hai aspect cùng match hoặc weave trùng | Tách output và kiểm tra cấu hình aspect |
| Advice không match | Sai `execution`/`call`, type hoặc overload | Kiểm tra join point và class được weave |
| Đổi tên method làm mất advice | Pointcut dùng exact tên/chữ ký cũ | Kiểm tra lại pointcut contract khi refactor |
| Method trên interface không nhận annotation đúng | Khác vị trí annotation ở interface/implementation | Xác minh lookup/weaver semantics |
| Advice không ghi lỗi | Dùng `after returning` cho đường ném exception | Dùng `after throwing` theo hợp đồng |
| Around gây lỗi kiểu trả về | `proceed`/return không phù hợp signature | Bảo toàn return và Throwable |
| LTW không hoạt động | Có runtime jar nhưng thiếu agent/config | Cấu hình weaving đúng deployment |
| Thời gian đo quá ngắn | Method chỉ trả future chưa hoàn tất | Đo đến completion nếu đó là hợp đồng observation |
| Concurrency lỗi | Aspect singleton lưu state của từng request | Tách state theo scope hoặc dùng đồng bộ đúng |

Đặc biệt, **pointcut expression dạng chuỗi** trong annotation-style có thể vẫn chứa tên/signature cũ dù IDE đã refactor method Java. Code-style cũng cần test phạm vi match, nhưng nhiều khai báo chuyên biệt được `ajc` kiểm tra cùng build. Không có phong cách nào tự bảo đảm đúng tập join point sau mọi lần refactor.

## 17. Cách kiểm thử aspect có hiệu lực

Nên dùng ít nhất ba loại kiểm tra:

1. **Compile/check metadata:** biểu thức pointcut hợp lệ, annotation nằm đúng chỗ, output chứa aspect mong muốn, version runtime/weaver tương thích.
2. **Weaving verification:** target code được đưa vào đúng `-inpath`/source compile hoặc được LTW biến đổi ở thời điểm nạp; không chạy nhầm class chưa weave trên classpath.
3. **Behavior test:** gọi thật qua entrypoint của ứng dụng, assert `before`, success/error advice, side effect và result chính xác.

Với demo, kiểm thử dương là cả hai phiên bản đều in:

```text
enter:A-7
exit:done:A-7
done:A-7
```

Kiểm thử âm là Java class chưa weave chỉ in:

```text
done:A-7
```

Các kiểm thử nâng cao nên bao gồm:

- Method ném exception: `after returning` không chạy, `after throwing` xử lý đúng đường lỗi.
- Thay `perform(String)` thành một overload hoặc đổi tên: pointcut có bỏ sót/chặn nhầm không?
- Class caller chưa weave khi pointcut dùng `call`.
- Aspect trên interface vs implementation; override, generic bridge method, method synthetic, varargs.
- Nhiều aspect cùng target: precedence và khả năng ghi nhận trùng.
- Actor/context trên nhiều thread hoặc future trả sớm: thời điểm observation chính xác.
- Build/deploy khác môi trường lập trình: phiên bản Java/AspectJ và agent/classloader tương thích.

**Có class aspect trong jar chưa đủ chứng minh advice đã chạy.** Cần ít nhất một test gọi vào phương thức đích qua đường thực thi thật và kiểm chứng effect.

## 18. Chọn phong cách phù hợp

Chọn **code-style** khi:

- Muốn sử dụng đầy đủ các cú pháp AspectJ đặc thù như inter-type method/field, những `declare` nâng cao.
- Build đã tích hợp `ajc` và nhóm muốn khai báo crosscutting tập trung bằng ngôn ngữ AspectJ.
- Cần trực tiếp mô tả các thay đổi cấu trúc type mà Java annotation không biểu đạt nguyên xi.

Chọn **annotation-style** khi:

- Phần lớn concern là pointcut và advice, cùng các loại `@Declare...` được hỗ trợ.
- Muốn viết Java class/method thông thường, dùng IDE Java, unit test helper và chuyển source qua `javac` trước khi weave nếu cần.
- Toolchain có bước weaving được định nghĩa và kiểm tra rõ.

Dù chọn cách nào:

- Pointcut phải bám theo **ranh giới nghiệp vụ** hoặc contract được review, tránh wildcard quá rộng.
- Không log tham số nhạy cảm, không gọi `proceed` ngoài hợp đồng và không dùng retry trên side effect chưa an toàn.
- Quản lý precedence, concurrency và vòng đời asynchronous observation.
- Pin phiên bản compiler/runtime/weaver và kiểm tra build reproducibility.
- Test **tập join point được chọn và hành vi thực sự xảy ra** thay vì chỉ nhìn syntax.

## 19. Ghi nhớ

**Cú pháp chuyên biệt và cú pháp annotation của AspectJ là hai cách diễn đạt AOP**, không phải hai mô hình độc lập. `aspect`/`pointcut`/`before` trong `.aj` tương ứng với `@Aspect`/`@Pointcut`/`@Before` trong Java ở nhiều trường hợp, và chúng có thể tạo kết quả như nhau khi weave đúng. Cần phân biệt riêng **cú pháp khai báo, thời điểm weaving, khả năng static crosscutting và metadata binding**. Một Java class chứa `@Aspect` mới chỉ là phần mô tả; muốn advice chạy phải chắc rằng target đã được weave.

### Tài liệu kỹ thuật

- [AspectJ — An Annotation Based Development Style](https://eclipse.dev/aspectj/doc/latest/adk15notebook/ataspectj.html): cú pháp annotation, tương ứng với code-style và giới hạn.
- [AspectJ Programming Guide](https://eclipse.dev/aspectj/doc/latest/progguide/progguide.html): join point, pointcut, advice, aspect instantiation và static crosscutting.
- [AspectJ ajc compiler/weaver](https://eclipse.dev/aspectj/doc/latest/devguide/ajc.html): compiler options, binary weaving, `-inpath` và `-aspectpath`.
