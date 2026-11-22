# Ảnh hưởng của AOP tới tối ưu hóa, khởi động và nạp mã

## 1. Bối cảnh: AOP làm thay đổi đường thực thi ở đâu?

**Aspect-Oriented Programming (AOP)** tách các mối quan tâm xuyên suốt (logging, đo thời gian, kiểm tra quyền, giao dịch, theo dõi lỗi...) khỏi phần nghiệp vụ. Một *aspect* diễn tả hành vi bổ sung (*advice*) và nơi áp dụng qua *pointcut*; một *join point* là vị trí thực thi có thể được tác động. Tùy cơ chế AOP, mã bổ sung có thể được chèn vào bytecode trước khi chạy, lúc JVM nạp lớp, hoặc được thực hiện qua một đối tượng trung gian ở thời gian chạy.

Chủ đề này tập trung vào ba hệ quả liên quan nhau:

- **Tối ưu hóa:** các lớp gọi, nhánh điều kiện, phép phản chiếu, đối tượng tạm, đồng bộ hóa hoặc advice bổ sung có thể thay đổi những gì JIT nhìn thấy và có thể tối ưu.
- **Khởi động:** việc phân tích pointcut, tạo proxy, biến đổi bytecode, xác minh lớp và khởi tạo hạ tầng có thể đẩy chi phí từ mỗi lời gọi sang giai đoạn chuẩn bị.
- **Nạp mã:** can thiệp vào bytecode/lớp tương tác với class loader, liên kết, khởi tạo lớp, Java Platform Module System (JPMS), metadata và cơ chế biến đổi lớp đang chạy.

Không tồn tại kết luận chung rằng “AOP luôn chậm” hay “weaving luôn nhanh hơn proxy”. Tác động phụ thuộc **thời điểm can thiệp, kiểu advice, độ nóng của phương thức, công cụ JVM và hình dạng đường gọi thực tế**.

## 2. Ba thời điểm can thiệp và sự phân bổ chi phí

| Cách thực hiện | Khi nào thêm logic AOP? | Chi phí thường nổi bật | Khả năng tối ưu khi chạy |
|---|---|---|---|
| **Compile-time weaving (CTW)** | Trong quá trình biên dịch hoặc xử lý bytecode khi build | Build lâu hơn, artifact được biến đổi; ít việc weaving lúc khởi động | JIT thấy bytecode cuối cùng và có cơ hội tối ưu cả mã nghiệp vụ lẫn advice, tùy trường hợp |
| **Load-time weaving (LTW)** | Khi lớp được loader định nghĩa, thường qua bộ biến đổi bytecode/Java agent | Phân tích, biến đổi và xác minh lớp có thể kéo dài startup hoặc lần tải lớp đầu | Sau khi nạp, JIT vẫn làm việc với bytecode đã biến đổi; cách chèn mã ảnh hưởng đến kết quả |
| **Runtime interception/proxy** | Khi tạo proxy hoặc lúc lời gọi đi qua đối tượng trung gian | Tạo/lưu metadata proxy; mỗi lời gọi có thể thêm dispatch, handler, reflection hay allocation | JVM có thể inline đường gọi ổn định, nhưng tầng gián tiếp và độ đa hình cũng có thể cản tối ưu |

Đây là các **mô hình**, không phải lời hứa về một thư viện cụ thể. Một ứng dụng có thể phối hợp nhiều cách; một cơ chế bytecode weaving không nhất thiết dùng proxy và ngược lại. Chẳng hạn, JDK dynamic proxy chặn lời gọi **qua interface**; cơ chế bytecode weaving có thể tác động ngay trong thân phương thức. Phạm vi join point hỗ trợ và giới hạn phương thức `final`, `private`, lời gọi nội bộ... khác nhau theo cơ chế.

Có thể hình dung đường thực thi:

```text
Không AOP:
Caller ──> BusinessMethod

Proxy/interception:
Caller ──> Proxy ──> Advice/Handler ──> Target ──> BusinessMethod

Weaving:
Caller ──> [BusinessMethod + mã advice đã chèn vào bytecode]
```

Sơ đồ trên chỉ mô tả cấu trúc, **không biểu diễn thời lượng**. Đặc biệt, không nên giả định bytecode đã weave tự động tương đương “một lời gọi không tốn chi phí”: chính advice vẫn phải thực thi.

## 3. Ảnh hưởng tới tối ưu hóa ở JVM

### 3.1. JIT tối ưu mã đã thực sự được thực thi

HotSpot thường bắt đầu với diễn giải và/hoặc biên dịch ở các mức khác nhau, thu thập profile rồi tối ưu các đoạn mã nóng. Trình biên dịch JIT xem bytecode và thông tin kiểu tại đường thực thi thực tế. Một advice rẻ trên đường ít được gọi có thể gần như không đáng kể; một advice rất nhỏ đặt trong vòng lặp chạy hàng triệu lần lại có thể chi phối thời gian CPU.

Một mô hình phân tích, **không phải công thức đo lường tuyệt đối**:

```text
Tổng chi phí quan sát
  ≈ khởi tạo/weaving/proxy một lần
  + số lượt gọi × (dispatch bổ sung + advice + tương tác với target)
  + hệ quả lên JIT, GC, cache và đồng bộ hóa
```

Các hạng tử có thể phụ thuộc lẫn nhau: chẳng hạn phân bổ tạm gây GC, hoặc advice làm phương thức phình to khiến ngưỡng inline khác đi.

### 3.2. Inlining, kiểu gọi và kích thước mã

- **Inlining:** JIT có thể ghép mã một phương thức được gọi vào caller nếu đủ thông tin và có lợi. Một chuỗi proxy → handler → reflection → target dài hoặc biến động có thể khó inline hơn đường gọi trực tiếp; **vẫn có trường hợp JIT tối ưu được một phần hoặc nhiều phần**.
- **Đa hình:** khi một call site lần lượt thấy nhiều kiểu proxy/handler/target, suy đoán kiểu và devirtualization kém ổn định hơn. Không nên mặc định mọi proxy đều tạo call site “megamorphic”.
- **Kích thước và cấu trúc bytecode:** advice chèn trực tiếp có thể làm phương thức dài hơn, thêm `try/finally`, nhánh điều kiện hoặc xử lý ngoại lệ; điều đó có thể thay đổi quyết định inline và bố trí mã máy.
- **Tối ưu xuyên qua ranh giới:** dùng `Method.invoke`, boxing/unboxing, đóng gói `Object[]` có thể xuất hiện trên một số đường interception. Những chi phí này **không phải lúc nào cũng giữ nguyên** sau warmup; JIT và thư viện lõi có thể giảm bớt chúng.
- **Escape analysis và phân bổ:** advice tạo đối tượng ngắn hạn (context, log event, wrapper, mảng tham số) có thể làm tăng allocation; JIT đôi khi khử được, nhưng không có bảo đảm, nhất là khi đối tượng thoát ra ngoài hoặc bị giữ lại.
- **Đồng bộ hóa và bộ nhớ:** lời gọi tới logging, I/O, khóa `synchronized`, biến `volatile` hoặc `ThreadLocal` có thể ảnh hưởng latency và khả năng tối ưu nhiều hơn bản thân lớp proxy.

**Hệ quả thực tế:** đo *đường gọi có advice đang bật*, với dữ liệu và mức tranh chấp đại diện; không lấy thời gian gọi một phương thức trống để suy ra chi phí của hệ thống thật.

### 3.3. Advice làm phát sinh công việc ngay cả khi logic nghiệp vụ không đổi

Ví dụ, một advice đo thời gian có thể gọi `System.nanoTime()` hai lần; advice ghi log có thể định dạng chuỗi, kiểm tra mức log hoặc truyền dữ liệu sang thiết bị ghi. Nếu advice thực hiện quanh mỗi lần gọi (*around advice*), cần xét cả việc kiểm soát ngoại lệ, giá trị trả về và trường hợp có hoặc không gọi `proceed`. Khi advice vô tình gọi cùng một join point lần nữa, có thể phát sinh nhiều tầng advice hoặc đệ quy ngoài ý muốn.

Tối ưu quan trọng thường là **giảm số join point bị chặn** và **giảm lượng công việc trong advice**, trước khi tìm cách tinh chỉnh vài nano giây ở proxy.

## 4. Tác động lên thời gian khởi động

“Startup” có thể chỉ từ lúc khởi chạy tiến trình đến khi `main` bắt đầu, hoặc đến khi dịch vụ thật sự sẵn sàng phục vụ yêu cầu. Phải thống nhất mốc đo.

### 4.1. Chi phí trả ở các giai đoạn khác nhau

```text
Build/deployment
  └─ [CTW: phân tích pointcut và weave bytecode trước]
Process start
  ├─ JVM tạo runtime, khởi tạo agent/hạ tầng liên quan
  ├─ Loader yêu cầu lớp → [LTW: biến đổi nếu lớp phù hợp] → define/link
  ├─ [Runtime proxy: tìm metadata, tạo/cache proxy khi được yêu cầu]
  └─ Chương trình sẵn sàng
First requests
  ├─ Có thể kích hoạt nạp/khởi tạo lớp hoặc proxy còn lazy
  └─ JIT warmup, lazy initialization và cache được làm nóng
Steady state
  └─ Các lời gọi AOP lặp lại, cùng hoạt động GC/JIT thông thường
```

- **CTW:** dời phần lớn việc tìm điểm chèn và thay bytecode sang lúc build, nhưng mã đã weave có thể lớn hơn và vẫn chịu verification/class loading và các static initializer khi chạy. Chi phí build, cache build và thời gian phát hành trở thành phần của lựa chọn kiến trúc.
- **LTW:** mỗi lớp phù hợp có thể cần transformer làm việc **trước khi được define**. Nếu rất nhiều lớp khớp bộ lọc hoặc pointcut quá rộng, startup/first-use có thể tăng đáng kể. Chỉ nạp một phần lớp lúc startup thì chi phí khác sẽ dời sang lần sử dụng đầu tiên.
- **Proxy runtime:** tạo proxy, lấy metadata phương thức, dựng chuỗi advice/interceptor và các cache có thể được làm sớm hoặc lười. Tạo lười cải thiện startup hiển thị nhưng có thể tăng **độ trễ request đầu tiên**.
- **Advice khởi tạo tài nguyên:** tạo appender ghi log, kết nối mạng, metrics exporter, bộ đệm, thread hoặc đăng ký hook thường tốn nhiều thời gian hơn việc tạo proxy; đây là chi phí của chức năng kèm theo, phải đo riêng.

### 4.2. Cold start, first use và warm state khác nhau

Đừng gom ba đại lượng thành một:

1. **Cold startup:** tiến trình JVM mới, lớp/metadata/JIT còn lạnh, hệ điều hành và ổ đĩa có trạng thái riêng.
2. **First-use latency:** request đầu tiên chạm một proxy, một class loader, một lớp chưa khởi tạo hoặc logic advice mới.
3. **Steady-state throughput/latency:** sau giai đoạn warmup đại diện, với tải liên tục.

Lazy initialization thường **dời** chi phí từ mốc (1) sang (2), chứ không xóa chi phí. Nếu ứng dụng có SLA khắt khe cho request đầu, một số điểm nóng cần chủ động warmup trong pha sẵn sàng. Ngược lại, khởi tạo mọi aspect ngay từ đầu có thể làm cold start nặng hơn mà không đem lại lợi ích nếu ít chức năng được dùng.

## 5. AOP và vòng đời nạp lớp

### 5.1. Loading, linking, initialization: phân biệt rõ

Trong Java, ba nhóm bước khác nhau:

1. **Loading:** class loader tìm hoặc tạo biểu diễn lớp từ bytecode và JVM định nghĩa đối tượng `Class`.
2. **Linking:** gồm verification, preparation và (có thể thực hiện lười) resolution các tham chiếu tượng trưng.
3. **Initialization:** thực thi bộ khởi tạo lớp như static field initializer và khối `static` khi có trigger tương ứng.

Ví dụ `Class.forName("pkg.Type", false, loader)` yêu cầu tìm lớp mà **không yêu cầu khởi tạo nó**; dạng `Class.forName("pkg.Type")` thường yêu cầu khởi tạo. Đây không phải bảo đảm rằng lớp chưa được load trước đó hoặc rằng mọi bước resolution đều diễn ra tại cùng một thời điểm.

Với LTW, transformer thông thường nhận bytecode khi lớp sắp được JVM định nghĩa, rồi trả lại bytecode đã biến đổi. JVM vẫn phải xác minh và liên kết mã hợp lệ. **Class loading** và **class initialization** là hai mốc khác nhau: weave lúc load không đồng nghĩa chạy advice hay static initializer ngay lúc đó.

### 5.2. Những ràng buộc kỹ thuật dễ gặp

- **Danh tính lớp:** cùng tên nhị phân do hai class loader định nghĩa tạo ra hai kiểu khác nhau. Cache aspect/proxy hoặc metadata phải xét cả loader (và khả năng giải phóng loader), không chỉ tên lớp.
- **Loader visibility:** proxy cần loader nhìn thấy các interface/kiểu liên quan. Lớp được transform có thể tham chiếu helper/advice mà loader đích không tìm được; lỗi như `ClassNotFoundException`, `NoClassDefFoundError` hoặc `LinkageError` có thể xảy ra.
- **JPMS và đóng gói:** module readability/exports/opens ảnh hưởng việc truy cập kiểu và phản chiếu sâu. `--add-opens` hoặc quyền agent đặc thù chỉ nên dùng khi thật sự cần, sau khi hiểu tác động đóng gói và triển khai.
- **Bytecode hợp lệ:** chèn instruction phải bảo toàn stack, control flow, exception handler, stack-map frame, kiểu trả về và các điều kiện verifier. Lỗi biến đổi có thể biểu hiện là `VerifyError` hoặc lỗi linkage.
- **Thứ tự transformers:** nhiều agent/công cụ quan sát có thể cùng biến đổi một lớp. Thứ tự và tương thích phiên bản bytecode/JDK cần kiểm tra; tracing và coverage cũng có thể tương tác với weaving.
- **`final`, `private`, constructor và self-invocation:** proxy dựa trên kế thừa có thể gặp hạn chế ở `final`; proxy qua interface chỉ chặn những lời gọi **đi qua proxy**. Weaving vào bytecode có tập join point và ngữ nghĩa riêng, không nên gộp các giới hạn này làm một.
- **Tải lớp và cấp phát bộ nhớ:** lớp proxy được tạo ra cần metadata và có thể thêm footprint trong metaspace, code cache, heap. Tạo vô hạn biến thể proxy hay giữ class loader bằng cache mạnh có thể làm bộ nhớ tăng kéo dài.

### 5.3. Java agent, biến đổi sau khi đã load và JIT

Với JVM Java 17, một Java agent có thể dùng API `java.lang.instrument` để đăng ký `ClassFileTransformer` ở thời điểm thích hợp. Việc đổi một lớp **đã được load** yêu cầu cơ chế retransformation hoặc redefinition được JVM/agent hỗ trợ; phạm vi thay đổi cấu trúc lớp chịu hạn chế (ví dụ không mặc nhiên được thêm/xóa field, method hoặc đổi hệ kế thừa). Không thể suy từ “thay bytecode” rằng JVM cho phép thay bất kỳ cấu trúc lớp nào vào bất kỳ lúc nào.

Thay đổi thân phương thức đã biên dịch có thể khiến JVM **vô hiệu hóa mã JIT đã tối ưu, chuyển về đường thực thi khác và biên dịch lại**. Đây là một nguồn spike ngắn hạn có thể xảy ra khi attach agent hoặc retransform lớp nóng; mức độ phụ thuộc phiên bản JVM và cách công cụ hoạt động.

Các kỹ thuật chia sẻ/lưu trữ dữ liệu lớp, cache hoặc archive (ví dụ Class Data Sharing) cũng có thể chịu ảnh hưởng tùy cách ứng dụng dùng agent, bytecode và classpath/module path. Phải đo trên cấu hình triển khai thực, tránh tuyên bố rằng chỉ cần bật LTW là mọi tối ưu startup/archiving đều bị tắt.

## 6. Ví dụ Java 17+: proxy được tạo trước, target được khởi tạo khi cần

Ví dụ sau minh họa **runtime interception qua JDK dynamic proxy**, không yêu cầu một thư viện AOP ngoài JDK. Handler đếm các lời gọi tới interface và tạo target lười; nó **không minh họa toàn bộ khả năng join point của bytecode weaving**.

Tạo tệp `AopStartupDemo.java`:

```java
import java.lang.reflect.InvocationHandler;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.util.function.Supplier;

public class AopStartupDemo {
    public interface Task {
        String run(String value);
    }

    public static final class RealTask implements Task {
        static {
            System.out.println("RealTask initialized");
        }

        @Override
        public String run(String value) {
            return "OK:" + value;
        }
    }

    static final class CountingHandler implements InvocationHandler {
        private final Supplier<Task> factory;
        private Task target;
        private int calls;

        CountingHandler(Supplier<Task> factory) {
            this.factory = factory;
        }

        @Override
        public Object invoke(Object proxy, Method method, Object[] args)
                throws Throwable {
            calls++;
            if (target == null) {
                target = factory.get();
            }
            try {
                return method.invoke(target, args);
            } catch (InvocationTargetException ex) {
                throw ex.getCause();
            }
        }

        int calls() {
            return calls;
        }
    }

    public static void main(String[] args) {
        System.out.println("01 - before proxy");
        CountingHandler handler = new CountingHandler(RealTask::new);
        Task proxy = (Task) Proxy.newProxyInstance(
                Task.class.getClassLoader(),
                new Class<?>[]{Task.class},
                handler);
        System.out.println("02 - after proxy");

        System.out.println(proxy.run("A"));
        System.out.println(proxy.run("B"));
        System.out.println("calls=" + handler.calls());
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac AopStartupDemo.java
java AopStartupDemo
```

Kết quả chuẩn đối với chương trình chạy độc lập:

```text
01 - before proxy
02 - after proxy
RealTask initialized
OK:A
OK:B
calls=2
```

**Đọc kết quả đúng bản chất:**

- `Proxy.newProxyInstance` tạo một proxy khi thực thi dòng tương ứng. Sau `after proxy`, target vẫn chưa **được khởi tạo**; lần đầu `factory.get()` gọi constructor khiến lớp `RealTask` được khởi tạo rồi tạo đối tượng. Việc *nạp* hoặc *resolve* lớp này có thể đã xảy ra sớm hơn; output không chứng minh lớp chưa được load.
- Mỗi lời gọi `proxy.run(...)` đi qua `InvocationHandler`, tăng `calls`, rồi chuyển tiếp tới target qua `Method.invoke`. Counter là bằng chứng hành vi chặn, **không phải số đo throughput**.
- Handler cố ý tối giản cho ví dụ chạy **một luồng**. Với nhiều luồng, việc tạo target lười và counter cần điều phối thích hợp (`synchronized`, `volatile`, atomic...), làm thay đổi đặc điểm chi phí.
- Nếu gọi trực tiếp `new RealTask().run(...)` thay vì qua proxy thì handler không được gọi. Điều này minh họa lý do phải kiểm tra tuyến lời gọi có thật sự đi qua interception point hay không.

Muốn quan sát thêm việc nạp lớp, có thể chạy riêng:

```bash
java -Xlog:class+load=info AopStartupDemo
```

Log nạp lớp sẽ nhiều hơn đáng kể so với stdout ở trên. Sự xuất hiện của một dòng nạp lớp **không chứng minh thời điểm khởi tạo lớp** hoặc chi phí của riêng advice; cần kết hợp log và phép đo được thiết kế đúng.

## 7. Tối ưu AOP theo nguồn chi phí thật sự

### 7.1. Lựa chọn pointcut và advice

- **Thu hẹp phạm vi:** áp dụng advice cho những phương thức cần thiết; tránh chặn getter, phép toán cực ngắn hoặc lời gọi trong vòng lặp nóng nếu không có nhu cầu quan sát cụ thể.
- **Lọc sớm và rẻ:** nếu không cần logging/tracing ở mức hiện tại, bỏ qua định dạng chuỗi, serialize tham số và tạo sự kiện; kiểm tra điều kiện trước phần xử lý đắt.
- **Tránh I/O đồng bộ trên đường nóng:** chuyển ghi log/telemetry sang cơ chế có giới hạn và backpressure phù hợp. Queue bất đồng bộ cũng có chi phí bộ nhớ, độ trễ và rủi ro mất sự kiện nên phải có chính sách rõ ràng.
- **Kiểm soát allocation:** tránh sao chép đối số lớn, giữ tham chiếu dài hạn, capture context không cần thiết. Nếu tham số chứa dữ liệu nhạy cảm, xác định rõ liệu có được ghi/quan sát hay không.
- **Tính đúng trước hiệu năng:** around advice phải giữ đúng giá trị trả về/ngoại lệ, thứ tự advice, phạm vi đồng bộ hóa và bảo toàn trạng thái ngay cả khi target ném lỗi.

### 7.2. Chọn thời điểm weaving theo yêu cầu vận hành

**CTW phù hợp khi** build artifact có thể quản lý, kiểm thử, truy vết chính xác và muốn hạn chế công việc transform lúc runtime. Đổi lại, pipeline build và kiểm soát bytecode đầu ra phức tạp hơn.

**LTW phù hợp khi** cần áp dụng cross-cutting concern trước khi lớp được định nghĩa, hoặc không dễ thay đổi một số artifact đã biên dịch. Cần kiểm soát phạm vi transformer, độ tương thích JDK/loader và hành vi cold start.

**Proxy runtime phù hợp khi** interception qua ranh giới interface/đối tượng đáp ứng đúng semantics và cần cấu hình mềm dẻo. Cần hiểu call path, trường hợp bỏ qua proxy, việc cache proxy và chi phí handler trong đường nóng.

Đây là các tiêu chí phân tích, **không phải bảng xếp hạng cố định**. Đôi khi advice quá đắt đến mức đổi cơ chế weaving gần như không tạo khác biệt đáng kể.

## 8. Đo lường có kiểm soát

### 8.1. Tách startup khỏi steady state

Thiết lập ít nhất hai cấu hình có cùng logic nghiệp vụ, dữ liệu, JDK, heap, CPU và traffic: **baseline không bật advice** và **cấu hình AOP đang dùng**. Nếu cần chẩn đoán tiếp, tách chi phí tạo proxy/weaving khỏi chi phí làm việc thực của advice, chẳng hạn đo advice tối giản và advice đầy đủ.

| Chỉ số | Cách quan sát | Câu hỏi cần trả lời |
|---|---|---|
| Cold start đến ready | timestamp/điểm ready nhất quán trên tiến trình mới; lặp nhiều lần | AOP có làm tăng thời gian sẵn sàng không? |
| First-request latency | đo request đầu trên tiến trình lạnh, báo rõ trạng thái cache/lazy | Có dời chi phí sang lần dùng đầu không? |
| Throughput, p50/p95/p99 latency | tải đại diện, phân bố request và concurrency giống nhau | Advice có tăng tail latency dưới tải thực không? |
| Allocation rate, GC | JFR, profiler hoặc JVM metrics | Có thêm đối tượng trung gian, buffer hay áp lực GC không? |
| CPU/profile stack | JFR, async-profiler tương thích, sampling profiler | Thời gian tập trung ở logic advice, handler hay target? |
| Class loading, metaspace, code cache | unified logging, JFR, chỉ số JVM | Có tăng số lớp, thời gian define/transform hoặc footprint? |
| JIT compilation/deoptimization | JFR và diagnostic phù hợp phiên bản | Proxy/weaving có làm thay đổi đường biên dịch nóng không? |

Ví dụ bật log nạp lớp:

```bash
java -Xlog:class+load=info:file=classes.log:uptime,level,tags AopStartupDemo
```

Ví dụ bắt đầu Java Flight Recorder khi chạy chương trình tương thích JDK 17:

```bash
java -XX:StartFlightRecording=filename=aop.jfr,dumponexit=true AopStartupDemo
```

Các lệnh này tạo dữ liệu để **điều tra**, không tự kết luận nguyên nhân. Đối với microbenchmark Java, dùng JMH với warmup, forks, trạng thái và kết quả tiêu thụ được, tránh dead-code elimination; chạy đủ biến thể phù hợp. Không dùng `System.nanoTime()` quanh một lời gọi đơn lẻ hay phép đo một lần lúc cold start để kết luận overhead ổn định. Khi đang cân nhắc tối ưu, quan sát cả mức nhiễu giữa các lần chạy, GC, throttling CPU và cache.

### 8.2. Cách đọc kết quả và xử lý nguyên nhân

- **Startup tăng, steady state gần như không đổi:** nghi ngờ khởi tạo metadata, transformer, lớp bổ sung hoặc initializers. Xem trace nạp lớp và đoạn thời gian trước ready.
- **Startup nhanh nhưng request đầu chậm:** điều tra lazy proxy/target, nạp lớp muộn, JIT warmup hoặc khởi tạo sink của advice.
- **CPU/latency tăng tỷ lệ với lượt gọi:** xem tần suất advice, đường handler, logging, serialization và tranh chấp; thử thu hẹp pointcut.
- **Tail latency/GC tăng:** tìm đối tượng tạm, batch queue telemetry, allocation spikes, lock contention và áp lực memory.
- **Vấn đề chỉ xuất hiện sau agent attach/retransform:** kiểm tra lớp đã transform, profile/JIT warmup lại, giới hạn redefine, thứ tự agent và tương thích JVM.
- **Chỉ xảy ra ở một môi trường triển khai:** so sánh JDK, module path, class loader, agents, ứng dụng đã package, cấu hình log/JFR và các tùy chọn runtime.

## 9. Những ngộ nhận và lỗi thường gặp

1. **“Weave sẵn thì advice miễn phí.”** CTW có thể giảm thao tác lúc startup nhưng mỗi advice vẫn tiêu thụ CPU/bộ nhớ/I/O tại join point.
2. **“Có proxy là mất hoàn toàn inlining.”** JIT có thể tối ưu các call site ổn định; mức tối ưu tùy profile và cách interceptor cài đặt.
3. **“Đã tạo proxy tức đã tạo target.”** Tạo proxy và khởi tạo target là hai sự kiện độc lập nếu target được tạo lười. Việc tải lớp cũng độc lập với chạy static initializer.
4. **“LTW xảy ra tại lần gọi phương thức đầu tiên.”** Thông thường biến đổi khi lớp được define; việc lớp được yêu cầu load có thể muộn, khiến nhầm lẫn với chi phí lời gọi đầu.
5. **“Mọi lời gọi nội bộ đều được advice chặn.”** Với cơ chế proxy, gọi trực tiếp nội bộ không đi qua proxy có thể bỏ qua advice; với weaving trực tiếp, phạm vi lại khác.
6. **“Có thể đổi bất kỳ bytecode/lớp nào khi JVM đang chạy.”** Redefinition/retransformation chịu giới hạn API và JVM; loader, verifier và JPMS vẫn áp dụng.
7. **“Một vòng `nanoTime` đã chứng minh AOP nhanh/chậm.”** Kết quả dễ bị warmup, dead-code elimination, noise và tải hệ thống bóp méo.
8. **“Chỉ cần xem average latency.”** AOP chứa I/O, lock hoặc allocation thường tác động đặc biệt tới p95/p99 và biến động dưới tải.

## 10. Checklist áp dụng vào một hệ thống cụ thể

1. Xác định **advice nào, join point nào, tần suất gọi bao nhiêu**, và đúng semantics mong muốn.
2. Xác định cơ chế can thiệp: **CTW, LTW hay proxy**; ghi rõ đối tượng/lớp nào bị tác động và khi nào.
3. Phân biệt **startup, first use, warm steady state**; chốt cùng tiêu chí sẵn sàng và cấu hình JVM khi so sánh.
4. Kiểm tra class loader, JPMS, dependency/helper của transformer, bytecode verifier và thứ tự agent nếu có weaving.
5. Profile để tìm chi phí chính: **advice, dispatch, I/O, allocation, lock, class loading hoặc JIT**.
6. Sửa nguyên nhân có tác động lớn nhất: thu hẹp pointcut, giảm việc thừa, tối ưu telemetry, cache hợp lý hoặc đổi chiến lược weaving khi bằng chứng ủng hộ.
7. Chạy kiểm thử chức năng và đo lại cả **cold start, first call, tail latency, throughput, memory**, đồng thời xác nhận advice vẫn chạy đúng ở những join point cần thiết.

**Điều cần nắm vững:** AOP làm thay đổi *đường thực thi* và đôi khi cả *bytecode*, vì thế có thể ảnh hưởng đồng thời đến tối ưu hóa JIT, thời gian sẵn sàng và vòng đời lớp. Muốn đánh giá đúng, phải chỉ rõ **chi phí nào được dời sang giai đoạn nào**, rồi đo bằng một workload đại diện thay vì kết luận từ tên kỹ thuật AOP.