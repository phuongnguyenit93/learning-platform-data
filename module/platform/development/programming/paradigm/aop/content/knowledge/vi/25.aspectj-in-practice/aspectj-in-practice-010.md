# Cấu hình phạm vi dệt và đọc thông báo của bộ dệt trong AspectJ

## 1. Tổng quan

Trong lập trình hướng khía cạnh (Aspect-Oriented Programming — AOP), viết một `aspect` và một `pointcut` chưa bảo đảm advice có hiệu lực ở những phương thức mong muốn. AspectJ còn cần thực hiện **weaving (dệt)**: kết nối advice với các join point mà bộ máy hỗ trợ. Việc dệt có thể xảy ra khi biên dịch nguồn, xử lý bytecode đã biên dịch, hoặc khi JVM nạp class.

Đối với một lỗi như “advice không chạy”, cần phân biệt ít nhất ba điều:

- **Class đủ điều kiện dệt hay chưa?** Source, file `.class`, JAR hoặc class loader có nằm trong vùng mà weaver xem xét không?
- **Aspect và pointcut có khớp không?** Aspect có được đăng ký và pointcut chọn được join point phù hợp không?
- **Đường thực thi có chạy qua join point không?** Code đã được dệt có thể không chạy vào nhánh đó, hoặc điều kiện runtime của pointcut không đúng.

Thông báo của bộ dệt giúp trả lời hai câu đầu; kiểm thử hành vi mới trả lời được câu thứ ba. Bài học đi sâu vào cấu hình và chẩn đoán **AspectJ nói riêng, AOP tổng quát nói chung**, không phụ thuộc framework ứng dụng.

~~~text
Java / AspectJ source hoặc binary classes
                   |
                   v
           Weaver input scope
                   |
                   v
       Eligible classes / class loader
                   |
                   v
            Available aspects
                   |
                   v
         Pointcut and join points
                   |
                   v
          Advice woven into code
                   |
                   v
        Runtime execution occurs?
                   |
                   v
           Advice is executed
~~~

**Nguyên tắc trung tâm:** “có class trên classpath” khác “class được weave”; “đã weave” khác “advice đã thực thi”; “advice thực thi” khác “mọi đường gọi cần bảo vệ đều được kiểm soát”.

## 2. Các khái niệm quan trọng

| Khái niệm | Ý nghĩa |
| --- | --- |
| **Aspect** | Đơn vị đóng gói pointcut, advice và logic xuyên suốt |
| **Join point** | Điểm có thể được chọn để can thiệp, chẳng hạn method call hoặc execution |
| **Pointcut** | Quy tắc chọn những join point cụ thể |
| **Advice** | Logic trước, sau hoặc quanh join point |
| **Weaver** | Công cụ gắn advice vào chương trình |
| **CTW** | Compile-time weaving: dệt trong quá trình biên dịch source |
| **Binary weaving** | Dệt file `.class` hoặc JAR đã biên dịch |
| **LTW** | Load-time weaving: dệt khi class được nạp/định nghĩa |
| **Weaving scope** | Tập class/type mà bộ dệt có thể xử lý |
| **Aspect selection** | Tập aspects có hiệu lực đối với bộ dệt |
| **Weave info** | Thông báo về việc dệt xảy ra tại class/join point |
| **Lint** | Chẩn đoán các tình huống có thể sai trong crosscutting |

Ví dụ pointcut/advice:

~~~aspectj
before(): execution(void example.WorkService.run()) {
    System.out.println("[advice] before");
}
~~~

Đây là đoạn cú pháp AspectJ minh họa, **không phải file `.aj` độc lập**. Nó nói advice cần đặt ở execution của `WorkService.run()` nếu join point đó được weaver hỗ trợ và class được đưa vào đúng phạm vi. Đoạn code tự nó không chỉ định binary input, class loader hoặc thời điểm dệt.

## 3. Compile-time weaving (CTW)

Trong CTW, compiler `ajc` nhận source Java và AspectJ, biên dịch và gắn advice vào bytecode đầu ra.

~~~text
.java + .aj --> ajc --> .class đã được weave --> JVM
~~~

Một ví dụ lệnh:

~~~bash
ajc -d build/ctw -showWeaveInfo -Xlint:warning \
    example/Main.java example/WorkService.java example/TraceAspect.aj
~~~

Ý nghĩa:

- `-d build/ctw`: nơi tạo output riêng.
- Các file `.java` đưa vào build là source cần compile/weave.
- `.aj` chứa aspect cần compile.
- `-showWeaveInfo` hiển thị những join point được bộ dệt tác động.
- `-Xlint:warning` báo tình huống nghi ngờ.

**Lưu ý:** `ajc` cần được cung cấp các source cần thiết; không tự tìm toàn bộ source trong dự án chỉ vì class tồn tại trong một cây thư mục khác. Nếu class nghiệp vụ chỉ được nhận diện như dependency, body của class đó không mặc nhiên được weave.

CTW phù hợp khi muốn xác định phạm vi ở **thời điểm build**, lưu log compiler trong CI và kiểm soát artifact đã dệt. Nhược điểm là phải cấu hình đúng pipeline build, đặc biệt với source chia nhiều module và JAR bên thứ ba.

## 4. Binary/post-compile weaving: ba đường dẫn rất dễ nhầm

Một lớp đã được biên dịch vẫn có thể trở thành input của bộ dệt. Khi dùng `ajc`, ba nhóm đường dẫn có mục tiêu khác nhau.

| Option | Chức năng chính | Không được hiểu là |
| --- | --- | --- |
| `-inpath <path>` | Đường dẫn file `.class`/JAR đưa vào làm **bytecode input cho weaving** | Dependency thông thường chỉ để resolve type |
| `-aspectpath <path>` | Đường dẫn **binary aspects** đã biên dịch được áp lên input | Danh sách class nghiệp vụ cần weave |
| `-classpath <path>` | Đường dẫn thư viện/class để **resolve dependency và kiểu** | Yêu cầu dệt tất cả class trên classpath |
| `-d <dir>` | Output đã biên dịch/dệt | Nguồn đầu vào nên bị ghi đè |
| `-showWeaveInfo` | Log weaving | Log method đã thực sự chạy trong request |

~~~text
compiled app .class/JAR -----> -inpath ------+
                                             |
compiled binary aspect -----> -aspectpath ---+--> ajc --> woven artifact
                                             |
other dependencies ----------> -classpath ---+
~~~

Ví dụ lệnh minh họa:

~~~bash
ajc -inpath build/original \
    -aspectpath build/aspects \
    -classpath lib/dependencies.jar \
    -d build/woven \
    -showWeaveInfo -Xlint:warning
~~~

Phải điều chỉnh đường dẫn theo artifact thực. Tạo output riêng và không vô tình đưa output trở lại `-inpath` ở build sau: dệt trùng có thể gây hành vi lặp, khó xác định phiên bản được JVM nạp.

Khi dùng aspect binary, đảm bảo version compiler/runtime tương thích và mang theo các dependency cần thiết của aspect khi chạy.

### 4.1. `call` và `execution` làm thay đổi class cần weave

~~~text
Caller.method()
    |
    +-- CALL join point --> Target.method()
                                |
                                +-- EXECUTION join point
~~~

Pointcut `call(* Target.method(..))` chọn vị trí **bên caller**; `execution(* Target.method(..))` chọn execution **bên callee**. Nếu chỉ bytecode của Caller được weave, advice dạng `call` có thể được chèn ở caller site mà không cần dệt thân Target. Với advice execution, body của Target phải thuộc phạm vi dệt theo kỹ thuật thực tế.

Vì vậy không đủ để hỏi “class Target có trên classpath không”; cần xác định **join point nằm trong bytecode class nào**.

## 5. Load-time weaving (LTW)

LTW gắn advice khi JVM tải/định nghĩa class. AspectJ có thể dùng `aspectjweaver.jar` làm Java agent và một hoặc nhiều file `META-INF/aop.xml` nhìn thấy trên đường tìm class của loader tương ứng.

~~~text
java -javaagent:aspectjweaver.jar
                |
                v
      Class loader sees aop.xml
                |
                v
       Weaver loads aspects
                |
                v
  Eligible types filtered by config
                |
                v
      Matched join points woven
~~~

Ví dụ cấu hình trong file `META-INF/aop.xml`:

~~~xml
<aspectj>
  <aspects>
    <aspect name="lab.aspects.TraceAspect"/>
  </aspects>
  <weaver options="-verbose -showWeaveInfo -debug">
    <include within="lab.app..*"/>
    <exclude within="lab.internal..*"/>
  </weaver>
</aspectj>
~~~

Đọc từng phần:

1. `<aspect name="..."/>` đăng ký một aspect có tên đầy đủ; **không** phải lệnh tự tìm mọi aspect trên classpath.
2. `<weaver>` thiết lập tùy chọn chẩn đoán và phạm vi các **type/class được phép weave**.
3. `<include within="lab.app..*"/>` chỉ cho class trong `lab.app` và package con được xét.
4. `<exclude within="lab.internal..*"/>` loại vùng class nội bộ. Với include đã hẹp như ví dụ, exclude này có tính minh họa/phòng thủ.
5. `-verbose` cho log lifecycle; `-showWeaveInfo` cho thông tin dệt; `-debug` của LTW giúp xem class được xét, bỏ qua hoặc loại trừ.

**Tệp này phục vụ LTW.** Đặt nó ở build folder không tự làm compiler CTW `ajc` thay đổi phạm vi source cần biên dịch. LTW còn phụ thuộc việc Java agent được kích hoạt đúng lúc và class loader thực sự nhìn thấy XML/aspect.

### 5.1. Hai vị trí `include/exclude` khác nhau

~~~xml
<aspectj>
  <aspects>
    <aspect name="lab.aspects.TraceAspect"/>
    <include within="lab.aspects..*"/>
  </aspects>
  <weaver options="-showWeaveInfo">
    <include within="lab.app..*"/>
    <exclude within="lab.app.generated..*"/>
  </weaver>
</aspectj>
~~~

| Nơi đặt | Đối tượng lọc |
| --- | --- |
| `<aspects><include/exclude>` | **Aspect được khai báo**, quyết định aspect nào được sử dụng |
| `<weaver><include/exclude>` | **Class/type đích**, quyết định lớp nào đủ điều kiện weaving |
| Pointcut trong mã aspect | **Join point**, quyết định vị trí advice được áp |

Một class đủ điều kiện theo `<weaver>` vẫn có thể không nhận advice nếu không có pointcut nào match. Một aspect được khai báo nhưng bị filter `<aspects>` loại cũng không tham gia weaving.

Khi có nhiều `META-INF/aop.xml` trên đường tìm class, weaver có thể tổng hợp nội dung theo quy tắc của AspectJ. Vì thế hãy đọc log `using configuration` để biết **các file XML thật sự đang được loader dùng**, không chỉ xem một file trong source tree.

### 5.2. Class loader và thời điểm

LTW diễn ra ở ranh giới class loading; một class đã được JVM nạp trước thời điểm weaver hoạt động **không mặc nhiên** bị biến đổi trở lại. Một ứng dụng có nhiều loader có thể dùng nhiều cấu hình khác nhau. Prefix class loader trong log là dấu vết quan trọng để tìm tại sao module A được weave còn module B không.

## 6. Tùy chọn để đọc thông báo của bộ dệt

| Tùy chọn | Dùng khi | Cách hiểu đúng |
| --- | --- | --- |
| `-verbose` | Cần thông tin compilation/lifecycle | Cho biết bước xử lý hoặc aspect/config được đăng ký, không nhất thiết join point đã nhận advice |
| `-showWeaveInfo` | Cần xem weaving thực tế | Log vị trí/lớp được tác động, không chứng minh method đã chạy |
| `-debug` (LTW) | Class bị bỏ qua hoặc exclude không rõ | Cho log chi tiết các class được weaver xét; không phải `javac -g` |
| `-Xlint` / `-Xlint:warning` | Kiểm tra dấu hiệu cấu hình sai | Cảnh báo khả nghi, cần phân tích theo loại |
| `-Xlint:error` | Chính sách CI nghiêm ngặt | Có thể nâng một số lint lên mức lỗi |
| `-Xlintfile <file>` | Cần tùy chỉnh nhóm lint | Properties cấu hình mức từng loại |
| `-log <file>` | Muốn lưu compiler messages | Thu bằng chứng build có thể đối chiếu |
| `ajc -version` | Chẩn đoán môi trường | Xác định compiler thực đang chạy |
| `ajc -help` | Xác nhận tùy chọn | Kiểm tra flag phù hợp với bản AspectJ |

Đối với LTW, hai system property hữu ích:

~~~text
-Daj.weaving.verbose=true
-Dorg.aspectj.weaver.showWeaveInfo=true
~~~

Chúng là **JVM options**, cần đặt lên command `java` thực tế; không tự chạy riêng trong terminal.

Một số dòng thông báo **minh họa cấu trúc, không phải output exact của bất kỳ phiên bản nào**:

~~~text
[AppClassLoader@...] info AspectJ Weaver Version ...
[AppClassLoader@...] info using configuration .../META-INF/aop.xml
[AppClassLoader@...] info register aspect lab.aspects.TraceAspect
[AppClassLoader@...] weaveinfo ... WorkService.run() ...
[AppClassLoader@...] debug ... SkipService ... excluded/ignored ...
~~~

Đọc theo thứ tự:

- **Loader**: có đúng class loader của module đang chạy?
- **Configuration**: có đúng `aop.xml` dự kiến?
- **Register aspect**: aspect mong đợi có được nhận diện?
- **Weave information**: advice có được gắn ở method đích?
- **Debug**: class bị exclude, không thể weave hay chỉ chưa đến lúc load?
- **Warning/error**: lỗi pointcut, bytecode, dependency, scope hoặc version?

Đừng viết kiểm thử phụ thuộc nguyên văn số dòng/compiler log minh họa; định dạng log, source line và thứ tự có thể đổi theo phiên bản.

## 7. `Xlint` và thông báo không match

Một cảnh báo tiêu biểu là `adviceDidNotMatch`, gợi ý advice chưa tìm được join point phù hợp trong tập class/compiler biết đến. Nguyên nhân có thể là:

- Sai chữ ký: tên method, package, kiểu return, overload, annotation hoặc `call`/`execution`.
- Source/bytecode đích không thuộc input weaving.
- Aspect được viết cho module khác chưa xuất hiện trong lần compile.
- Với LTW, class liên quan có thể chỉ được load sau này.

**Khác biệt quan trọng:** CTW có tập input được xác định tại build nên có thể cảnh báo một advice không match. LTW không biết trước toàn bộ class sẽ load về sau; xử lý `adviceDidNotMatch` có thể khác, ví dụ không nâng thành warning như khi compile-time. Không có warning **không đồng nghĩa** lời gọi đã được bảo vệ.

Tránh tắt mọi cảnh báo bằng `-Xlint:ignore` chỉ vì build ra output. Hãy xác định cảnh báo thuộc loại gì và nó có thể chỉ ra vùng dệt bị mất hay không. Khi cần CI nghiêm ngặt, cấu hình quy tắc có chủ đích thay vì biến mọi message thành lỗi mà không phân loại.

## 8. Ví dụ Java 17 và AspectJ: so sánh CTW với LTW

Bộ ví dụ độc lập gồm **ba file Java** và **một file aspect**. Ta sẽ chạy cùng một chương trình nhưng thay đổi phạm vi dệt:

- CTW: đưa cả hai service vào source input, nên hai execution có advice.
- LTW: filter chỉ cho `lab.app..*`, nên chỉ `WorkService` có advice.
- Không weaving: chỉ có thông báo từ thân hai method.

Cấu trúc:

~~~text
lab/
  app/
    Main.java
    WorkService.java
  internal/
    SkipService.java
  aspects/
    TraceAspect.aj
~~~

### 8.1. `lab/app/Main.java`

~~~java
package lab.app;

import lab.internal.SkipService;

public class Main {
    public static void main(String[] args) {
        new WorkService().run();
        new SkipService().run();
    }
}
~~~

### 8.2. `lab/app/WorkService.java`

~~~java
package lab.app;

public class WorkService {
    public void run() {
        System.out.println("[target] work");
    }
}
~~~

### 8.3. `lab/internal/SkipService.java`

~~~java
package lab.internal;

public class SkipService {
    public void run() {
        System.out.println("[target] skip");
    }
}
~~~

### 8.4. `lab/aspects/TraceAspect.aj`

~~~aspectj
package lab.aspects;

public aspect TraceAspect {
    before():
        execution(void lab.app.WorkService.run())
        || execution(void lab.internal.SkipService.run()) {

        String name = thisJoinPointStaticPart
                .getSignature()
                .getDeclaringType()
                .getSimpleName();

        System.out.println("[advice] " + name + ".run");
    }
}
~~~

Cần `ajc` để biên dịch `.aj`, không dùng `javac TraceAspect.aj`. `thisJoinPointStaticPart` lấy metadata tĩnh, dùng để xác định method được advice.

### 8.5. Compile-time weaving: kết quả có hai advice

Đặt `ASPECTJ_HOME` tới bản phân phối có JAR tương thích, dùng `ajc` phù hợp với JDK 17+.

~~~bash
mkdir -p build/ctw
ajc -d build/ctw \
    -classpath "$ASPECTJ_HOME/lib/aspectjrt.jar" \
    -showWeaveInfo -Xlint:warning \
    lab/app/Main.java \
    lab/app/WorkService.java \
    lab/internal/SkipService.java \
    lab/aspects/TraceAspect.aj

java -cp "build/ctw:$ASPECTJ_HOME/lib/aspectjrt.jar" lab.app.Main
~~~

**Stdout chương trình** (không tính log `ajc`):

~~~text
[advice] WorkService.run
[target] work
[advice] SkipService.run
[target] skip
~~~

Giải thích: cả `lab.app.WorkService` và `lab.internal.SkipService` nằm trong input `ajc`. Pointcut chọn cả hai execution `run()`, do đó advice in trước body của mỗi method. `-showWeaveInfo` sẽ giúp kiểm tra hai vị trí được dệt; không dự đoán format exact của thông báo compiler.

### 8.6. Load-time weaving: chỉ WorkService có advice

**Bước 1:** Compile Java thường, tạo **class chưa weave**:

~~~bash
mkdir -p build/ltw-classes build/ltw-aspects build/ltw-config/META-INF

javac -d build/ltw-classes \
    lab/app/Main.java \
    lab/app/WorkService.java \
    lab/internal/SkipService.java
~~~

**Bước 2:** Compile aspect riêng thành binary (dùng class Java chỉ để resolve type):

~~~bash
ajc -d build/ltw-aspects \
    -classpath "build/ltw-classes:$ASPECTJ_HOME/lib/aspectjrt.jar" \
    lab/aspects/TraceAspect.aj
~~~

**Bước 3:** Lưu nội dung sau đúng vào `build/ltw-config/META-INF/aop.xml`:

~~~xml
<aspectj>
  <aspects>
    <aspect name="lab.aspects.TraceAspect"/>
  </aspects>
  <weaver options="-verbose -showWeaveInfo -debug">
    <include within="lab.app..*"/>
    <exclude within="lab.internal..*"/>
  </weaver>
</aspectj>
~~~

**Bước 4:** Chạy bằng agent và classpath chỉ trỏ tới class Java gốc, aspect binary và config:

~~~bash
java -javaagent:"$ASPECTJ_HOME/lib/aspectjweaver.jar" \
    -cp "build/ltw-classes:build/ltw-aspects:build/ltw-config:$ASPECTJ_HOME/lib/aspectjrt.jar" \
    lab.app.Main
~~~

Bỏ qua các dòng diagnostics của LTW, **stdout chương trình** có thứ tự:

~~~text
[advice] WorkService.run
[target] work
[target] skip
~~~

Tại sao? `lab.app.WorkService` thuộc include nên có execution `run()` được weave. `lab.internal.SkipService` ở ngoài include và được exclude rõ ràng, do đó method vẫn chạy nhưng advice không xuất hiện.

Nếu thấy bốn dòng như CTW, có thể đã chạy nhầm class vốn được weave từ `build/ctw`, có config khác mở rộng scope hoặc class loader khác. Nếu không có advice nào, kiểm tra `-javaagent`, classpath, `META-INF/aop.xml`, tên aspect và logs.

**Đối chứng không weaving:**

~~~bash
java -cp build/ltw-classes lab.app.Main
~~~

Stdout:

~~~text
[target] work
[target] skip
~~~

Với **Windows**, dùng dấu `;` làm phân tách classpath thay vì dấu `:` và trỏ `-javaagent` tới đúng file `aspectjweaver.jar`; trong PowerShell có thể đặt toàn bộ lệnh `java` trên một dòng để tránh lỗi nối dòng.

### 8.7. Vì sao tách các output?

Output CTW đã chứa advice; output LTW ban đầu không chứa advice. Nếu vô tình đặt `build/ctw` lên classpath ở kịch bản LTW, thí nghiệm không còn chứng minh agent weave class nguyên bản. Một build đáng tin cần lưu rõ **input**, **output**, **version ajc**, **runtime JAR**, **config XML** và **classpath**.

## 9. Đọc log trong thực tế: bảng chẩn đoán

| Triệu chứng | Khả năng cần kiểm tra |
| --- | --- |
| Không có bất kỳ log LTW | Agent chưa bật, options chưa bật, config không thấy được |
| Có `using configuration` nhưng không thấy aspect đăng ký | Tên aspect sai, không có binary, filter `<aspects>` loại |
| Có `register aspect` nhưng không có weaveinfo lớp mong đợi | Class chưa load, exclude, pointcut sai hoặc thiếu bytecode input |
| Thấy class `ignored/excluded` trong debug | Kiểm tra type pattern, class loader và restriction |
| Có weaveinfo nhưng advice không in | Nhánh method không chạy, runtime condition false, lớp chạy bị khác |
| `adviceDidNotMatch` khi CTW | Input build thiếu class hoặc pointcut không khớp |
| Thông báo LTW khác CTW | Lượng class biết trước khác nhau; xem thời điểm load |
| Chỉ một overload có advice | Kiểm tra signature/return/args của pointcut |
| Advice chạy hai lần | Tìm double weave, nhiều aspect, call/execution cùng match |
| Không đọc thấy XML từ packaged JAR | Kiểm tra `META-INF/aop.xml` có nằm đúng trên class loader path |
| JVM chạy nhưng policy quan trọng bị bỏ qua | Test positive/negative và entry path, không chỉ nhìn log |

Đừng chỉ grep `register aspect` rồi báo PASS: đăng ký aspect **không chứng minh** đã weave join point cần thiết. Tương tự, thông báo woven class **không chứng minh** runtime đã thực thi nhánh đó.

## 10. Lọc phạm vi an toàn và hiệu năng

**Phạm vi quá rộng** có thể dệt cả các class không liên quan, tăng thời gian build/class load, tăng kích thước bytecode và overhead runtime. Aspect logging nếu vô tình match chính hạ tầng logging có thể tạo vòng lặp đệ quy. **Phạm vi quá hẹp** có thể bỏ sót những method cần audit, transaction hoặc kiểm soát quyền.

Một cách thiết kế hợp lý:

1. Xác định danh sách operation cần tác động.
2. Chọn đúng `call` hay `execution`.
3. Giới hạn lớp có thể weave bằng input, `-inpath` hoặc LTW include/exclude.
4. Viết pointcut đủ cụ thể; đừng dùng một pattern khớp cả ứng dụng chỉ vì muốn warning biến mất.
5. Bật diagnostics trong build/test; đo overhead bằng workload thực.
6. Kiểm tra **positive** (method phải có advice) và **negative** (method không được có advice).
7. Khi dùng cflow, args hoặc điều kiện động, kiểm tra thêm trạng thái runtime.

Cũng cần biết: một security aspect ở vài join point **không tự bảo vệ mọi đường trực tiếp tới resource**; transaction advice không tự cung cấp transaction manager/rollback cho external side effect. Bằng chứng weaving là một phần của QA kiến trúc, không thay thế kiểm thử an toàn nghiệp vụ.

## 11. Lớp đã được weave có thể chưa chạy advice

Có nhiều nguyên nhân:

- Method chưa được gọi trong test case đó.
- Around advice khác short-circuit và không gọi `proceed()`.
- Pointcut có `if()`, `args()` hoặc `cflow()` chỉ đúng trong một số ngữ cảnh runtime.
- Execution xảy ra ở class/loader khác với artifact vừa kiểm tra.
- Công việc thực tế chạy trên worker bất đồng bộ, method ban đầu chỉ trả `CompletionStage`/future.
- Log của advice bị tắt hoặc gửi sang sink khác.

Một chương trình trả handle bất đồng bộ không đồng nghĩa công việc đã hoàn tất. `-showWeaveInfo` không cho biết completion outcome. Nếu muốn đo hết một asynchronous operation, cần hook vào tín hiệu hoàn tất phù hợp, không chỉ vào method return.

## 12. Checklist khi cấu hình cho hệ thống thật

- [ ] Đã xác định **CTW, binary weaving hay LTW**?
- [ ] Lớp đích thật sự có trong source input/`-inpath` hoặc class loader phù hợp?
- [ ] `-aspectpath` chứa binary aspect, không bị nhầm với target classes?
- [ ] `-classpath` cung cấp đúng dependency?
- [ ] Output woven được tách khỏi input và có build sạch?
- [ ] Với LTW, `-javaagent` được bật và `aop.xml` nằm đúng `META-INF`?
- [ ] Aspect được khai báo đầy đủ và có log đăng ký?
- [ ] `<aspects>` filter đúng tập aspect, `<weaver>` filter đúng tập class?
- [ ] `include/exclude` dùng đúng type pattern cho package con?
- [ ] Đã đối chiếu `call`/`execution` với vị trí bytecode có thể weave?
- [ ] `-showWeaveInfo` cho thấy join point quan trọng nhận advice?
- [ ] `-debug` LTW cho biết lý do class bị ignore/exclude?
- [ ] Warning `Xlint` được phân loại thay vì bỏ qua?
- [ ] Runtime test chứng minh behavior đúng, gồm cả case không match?
- [ ] Không có output class cũ hoặc dependency JAR sai version được nạp?
- [ ] Có kiểm chứng riêng cho async, security, transaction và exception khi liên quan?

## 13. Các lỗi thiết kế phổ biến

| Sai lầm | Cách sửa |
| --- | --- |
| Có class trên classpath tức đã weave | Xác nhận source input hoặc `-inpath`/LTW class eligibility |
| Chỉ có aspect binary là đủ | Cần aspect được nhận diện, pointcut match và target class trong scope |
| Nhầm filter trong `<aspects>` với `<weaver>` | Phân biệt lọc aspect và lọc class |
| Chỉ xem `-verbose` | Dùng weaveinfo/debug và runtime test phù hợp |
| Tưởng `-debug` LTW là debug symbol | Phân biệt `-debug` với `-g` |
| Dùng `aop.xml` để giới hạn CTW mà không cấu hình compiler | CTW cần source/input build và pointcut |
| Đổi XML trên đĩa rồi mong class đã load tự đổi | Khởi động JVM mới để kiểm chứng phạm vi LTW |
| Bật agent nhưng thiếu XML/aspect | Kiểm tra classpath, loader và registered aspects |
| Tắt tất cả lint warning | Phân loại nguyên nhân, giữ cảnh báo có ích |
| Dệt cả class logging để chữa missing match | Giới hạn pointcut/scope để tránh đệ quy |
| Chạy test LTW với output CTW | Tách class nguyên bản và class woven |
| Dùng weaveinfo thay kiểm thử hành vi | Kiểm chứng lời gọi thực tế và hợp đồng nghiệp vụ |

## 14. Kết luận

Cấu hình AspectJ đúng là sự phối hợp giữa **input weaving**, **aspect availability**, **class/type filters**, **pointcut matching** và **runtime invocation**. Các thông báo `-verbose`, `-showWeaveInfo`, `-debug` và `Xlint` giúp chẩn đoán từng lớp, nhưng không thay thế kiểm thử hành vi. Cách làm đáng tin là quan sát cả **method phải nhận advice** và **method phải nằm ngoài scope**, sau đó kiểm tra trên đúng artifact, JVM và class loader mà hệ thống sẽ triển khai.

Nhớ ba phân biệt: **classpath khác input để weave; đăng ký aspect khác join point được advise; weave info khác advice đã thực thi**.

## 15. Nguồn tra cứu chính thức

- [AspectJ Development Environment Guide — ajc](https://eclipse.dev/aspectj/doc/latest/devguide/ajc.html)
- [AspectJ Development Environment Guide — Load-Time Weaving](https://eclipse.dev/aspectj/doc/latest/devguide/ltw.html)
- [AspectJ Problem Diagnosis Guide — Messages](https://eclipse.dev/aspectj/doc/latest/pdguide/messages.html)

Dùng `ajc -version` và `ajc -help` trên môi trường của mình để kiểm tra cờ thực tế, vì cách ghi thông báo và mức hỗ trợ có thể thay đổi giữa những phiên bản AspectJ.