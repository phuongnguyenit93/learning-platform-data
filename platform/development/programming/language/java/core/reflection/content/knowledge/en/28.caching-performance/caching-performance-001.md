# Chi phí tra cứu metadata khác chi phí invoke trong Java Reflection

## Mục tiêu học tập

Khi ứng dụng dùng reflection, có ít nhất hai công việc rất khác nhau:

1. **Tìm và diễn giải metadata**: xác định một `Class`, tìm `Method`/`Field`/`Constructor` hoặc đọc chữ ký generic, annotation, modifier.
2. **Thực thi phương thức**: đã có `Method` rồi, gọi `method.invoke(receiver, arguments...)` để chạy logic trên một đối tượng hoặc gọi phương thức static.

Hai công việc có tính chất chi phí khác nhau. Một đoạn code chậm do **tìm lại method trên mỗi request** không có nghĩa bản thân `Method.invoke` phải chịu toàn bộ chi phí đó. Ngược lại, cache `Method` chỉ loại bỏ việc tra cứu lặp; nó **không biến lời gọi reflection thành lời gọi Java trực tiếp**.

Sau bài này, bạn sẽ phân tách được các bước khi đo hiệu năng, hiểu lúc nào cache metadata giúp ích, phân biệt chi phí khởi tạo với chi phí lặp lại và thiết kế benchmark đủ đáng tin.

## 1. Hai công đoạn và phạm vi công việc

Ví dụ có một class:

~~~java
public class Calculator {
    public int add(int a, int b) {
        return a + b;
    }
}
~~~

Đây là **đoạn minh họa khai báo class**, không phải chương trình độc lập chứa `main`.

Cùng một phương thức có thể được tìm rồi gọi như sau:

~~~java
Method method = Calculator.class.getMethod(
        "add", int.class, int.class);    // Bước A: tìm metadata
Object result = method.invoke(
        new Calculator(), 2, 5);        // Bước B: thực thi
~~~

Đây cũng là **đoạn trích**, cần `import java.lang.reflect.Method` và khai báo/ xử lý checked exceptions. Giá trị `result` là `Integer` tương ứng số `7`, vì giá trị primitive trả qua `Method.invoke` được boxing.

| Công đoạn | Ví dụ API | Loại công việc | Kết quả |
| --- | --- | --- | --- |
| Lấy handle class | `Calculator.class`, `obj.getClass()` | Có/nhận diện đối tượng `Class` của kiểu | `Class<?>` |
| Tìm thành viên | `getMethod`, `getDeclaredMethod`, `getDeclaredFields` | Tra cứu tên/chữ ký/phạm vi khai báo, có thể tạo wrapper và mảng kết quả | `Method`, `Field`, `Constructor`, mảng |
| Đọc metadata chuyên sâu | `getGenericReturnType`, `getAnnotations` | Có thể phải phân tích `Signature`/annotation và phân giải kiểu | `Type`, annotation, metadata |
| Chuẩn bị sử dụng thành viên | `canAccess`, `trySetAccessible`, tạo `MethodHandle` | Kiểm tra/thiết lập cách truy cập, ràng buộc vào handle | Khả năng truy cập hoặc handle |
| Thực thi | `Method.invoke(target, args)` | Kiểm tra receiver/đối số/quyền phù hợp, chuyển đổi, dispatch và chạy thân method | Kết quả `Object` hoặc ngoại lệ |

**Không đánh đồng** việc lấy `Class` từ `Calculator.class` với việc phải tìm lại `Method` bằng tên. `Class.forName(...)` còn liên quan tải/khởi tạo class tùy cách gọi nên chi phí cold-start của nó cũng không đại diện cho lookup thông thường.

### 1.1. Tra cứu metadata tốn gì?

Với `clazz.getMethod("add", int.class, int.class)`, runtime phải tìm thành viên `public` phù hợp tên và danh sách tham số, có xét các thành viên được thừa hưởng theo quy tắc API. `getDeclaredMethod` chỉ tra phương thức **khai báo trực tiếp** trên class đang xét và có thể tìm cả non-public member. Đổi từ phương thức này sang phương thức kia chỉ để chạy nhanh hơn có thể làm **sai tập kết quả**, nên chọn API trước theo ngữ nghĩa.

Các yếu tố ảnh hưởng đến chi phí lookup:

- Số lượng và hình thái thành viên, overload và cây kế thừa/interface cần xử lý.
- Việc dùng `getMethods()` / `getDeclaredMethods()` để liệt kê mảng toàn bộ rồi lọc, so với tra một phương thức có tên và parameter types rõ ràng.
- Allocation cho wrapper `Method` và các mảng metadata; JVM/JDK có thể cache nội bộ nhưng **không có hợp đồng hiệu năng cố định** để dựa vào.
- Phân tích annotation và generic metadata có thể phát sinh thêm công việc riêng, gồm phân giải type; không nên gộp chi phí này vào một chỉ số tên chung là “reflection lookup”.
- Lookup thực hiện một lần lúc ứng dụng khởi động khác lookup lặp hàng nghìn lần trong vòng xử lý request.

Khi có metadata rồi, các lệnh như `method.getName()` và `method.getReturnType()` đọc dữ liệu từ `Method`; chúng không đồng nghĩa với việc phải gọi lại `Class.getMethod(...)`. Tuy vậy, một số API metadata có thể cấp phát đối tượng/mảng hoặc phân giải thông tin bổ sung; không khẳng định mọi getter đều miễn phí.

### 1.2. Một lần `Method.invoke` tốn gì?

Khi đã có `Method`, `invoke` **không tự chạy lại câu lệnh `getMethod` mà ứng dụng đã dùng**. Nó phải thực hiện ngữ nghĩa của lời gọi reflection, trong đó có:

- Xác nhận receiver hợp lệ cho instance method và kiểm tra điều kiện truy cập theo quy tắc reflection/JPMS (cách tối ưu phụ thuộc JDK và trạng thái member).
- Kiểm tra số lượng, kiểu đối số, boxing/unboxing hoặc widening primitive hợp lệ; varargs không tự tiện được trải phẳng từ mảng bất kỳ.
- Đi tới phương thức thực cần gọi, gồm **dynamic dispatch** với instance method override; static method dùng phương thức được chỉ định.
- Thực thi **thân phương thức đích**. Công việc SQL, I/O, mạng hoặc xử lý dữ liệu trong thân method có thể áp đảo overhead của reflection.
- Boxing giá trị trả về primitive hoặc trả `null` cho `void`; lỗi phát sinh từ thân method được bọc trong `InvocationTargetException`.

Chi phí invoke thay đổi theo method, kiểu tham số, JIT warmup, khả năng tối ưu và phiên bản JVM. Không có quy luật như “invoke luôn chậm hơn lookup” hoặc “reflection luôn chậm X lần so với direct call” dùng được cho mọi Java/JVM.

## 2. Mô hình chi phí: tìm lại mỗi lần hay cache Method?

Gọi:

- `L`: chi phí **một lần** tìm `Method` theo tên/chữ ký.
- `I`: chi phí **một lời gọi reflection**, gồm overhead invoke và công việc của target.
- `n`: số lần cần gọi cùng một phương thức.

Một mô hình đơn giản, chưa tính tối ưu JVM/caching/allocation và thời gian tạo cache:

| Cách viết | Tổng chi phí gần đúng |
| --- | --- |
| Mỗi lần tìm rồi gọi | `n × (L + I)` |
| Tìm một lần rồi tái dùng | `L + n × I` |
| Tiết kiệm phần lookup (mô hình) | `(n - 1) × L` |

Ví dụ: với 10.000 request đều gọi cùng một method, bản **lookup mỗi request** có 10.000 lần tìm; bản cache có một lần tìm và 10.000 lần invoke. Hai bản vẫn thực thi 10.000 lần phương thức nghiệp vụ.

Đây là mô hình để thấy rõ nguồn chi phí, **không phải** khẳng định mỗi `L` hoặc `I` là một hằng số có thể đo độc lập hoàn toàn trên JVM thực. Nếu method chỉ dùng một lần, cache có thể không có ý nghĩa; nếu target làm I/O kéo dài, phần tiết kiệm lookup có thể quá nhỏ so với thời gian end-to-end.

## 3. Ví dụ Java 17+ chạy được: đếm lookup và invoke

Ví dụ này cố ý **không in nanosecond** vì timing cực ngắn từ một lượt chạy dễ gây kết luận sai. Thay vào đó, mã dùng kết quả xác định để chứng minh cache `Method` giảm **số lần tra cứu metadata**, trong khi số lần invoke không đổi.

Lưu tệp **ReflectionCostDemo.java**:

~~~java
import java.lang.reflect.Method;

public class ReflectionCostDemo {
    public static final class Calculator {
        public int add(int a, int b) {
            return a + b;
        }
    }

    public static void main(String[] args) throws ReflectiveOperationException {
        Calculator target = new Calculator();
        final int calls = 4;

        // Cách 1: mỗi lời gọi đều lookup lại Method.
        int repeatedSum = 0;
        int repeatedLookups = 0;
        for (int i = 1; i <= calls; i++) {
            Method method = Calculator.class.getMethod(
                    "add", int.class, int.class);
            repeatedLookups++;
            repeatedSum += (Integer) method.invoke(target, i, 10);
        }

        // Cách 2: lookup một lần rồi invoke nhiều lần.
        Method cached = Calculator.class.getMethod(
                "add", int.class, int.class);
        int cachedSum = 0;
        for (int i = 1; i <= calls; i++) {
            cachedSum += (Integer) cached.invoke(target, i, 10);
        }

        // Đối chứng: gọi Java trực tiếp, không dùng reflection.
        int directSum = 0;
        for (int i = 1; i <= calls; i++) {
            directSum += target.add(i, 10);
        }

        System.out.println("repeated: lookups=" + repeatedLookups
                + ", invokes=" + calls + ", sum=" + repeatedSum);
        System.out.println("cached: lookups=1, invokes=" + calls
                + ", sum=" + cachedSum);
        System.out.println("direct: lookups=0, invokes=0, sum=" + directSum);
        System.out.println("metadata: name=" + cached.getName()
                + ", parameters=" + cached.getParameterCount()
                + ", return=" + cached.getReturnType().getTypeName());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 ReflectionCostDemo.java
java ReflectionCostDemo
~~~

Stdout:

~~~text
repeated: lookups=4, invokes=4, sum=50
cached: lookups=1, invokes=4, sum=50
direct: lookups=0, invokes=0, sum=50
metadata: name=add, parameters=2, return=int
~~~

Giải thích:

1. Ba đường đi đều thực thi phép cộng với `i` từ 1 đến 4 và `10`, cho tổng `11 + 12 + 13 + 14 = 50`.
2. Cách thứ nhất gọi `Class.getMethod(...)` **bốn lần**; cách thứ hai chỉ gọi **một lần**. Cả hai đều dùng `Method.invoke(...)` bốn lần.
3. `cached.getName()`, `getParameterCount()` và `getReturnType()` cho thấy có thể đọc metadata từ `Method` đã lưu mà không thực hiện lại `getMethod(...)`.
4. Đây là **thử nghiệm về cấu trúc công việc**, không phải microbenchmark về thời gian thực. Chỉ số lookup/invoke và stdout trên đây là cố định; latency giữa máy, JDK và từng lần chạy thì không.

## 4. Thiết kế cache đúng phạm vi

### 4.1. Cache ở đâu?

- **Một phương thức cố định trong thành phần dùng lâu dài:** resolve `Method` lúc khởi tạo và giữ trong một field; tái dùng trên nhiều request.
- **Một class có nhiều method:** xây index theo tên + parameter types hoặc annotation một lần khi đăng ký route/serializer/DI bean. Đừng mỗi request quét `getDeclaredMethods()` rồi lọc.
- **Nhiều class động:** dùng cấu trúc cache có key phân biệt đúng `Class<?>` và signature, xử lý đồng thời nếu dùng nhiều thread; cân nhắc `ClassValue<T>` để liên kết dữ liệu với vòng đời class.
- **Plugin/hot reload/classloader có thể thay đổi:** tránh `static Map<Class<?>, Method>` mạnh, tồn tại mãi không giới hạn. Key và value giữ tham chiếu đến class/classloader có thể cản việc unload; dùng vòng đời rõ ràng hoặc cơ chế cache phù hợp.

Một lỗi thường gặp là cache `Method` chỉ bằng tên chuỗi `"save"`. Hai class hoặc hai overload có thể có cùng tên nhưng khác tham số và khai báo. Cache key thường cần bao gồm **class identity (và ngữ cảnh class loader), tên phương thức, kiểu tham số, cách lookup**; đừng chỉ dựa vào tên class dưới dạng String.

`Method` có thể được tái dùng giữa các thread cho mục đích invocation thông thường, miễn chính đối tượng target và dữ liệu nghiệp vụ được quản lý thread-safety đúng cách. Cache không làm `target` trở thành thread-safe. Ngoài ra, việc gọi `trySetAccessible()`/`setAccessible(true)` bị giới hạn bởi quyền và module access; cache kết quả tra cứu không tự vượt qua JPMS.

### 4.2. Cache loại bỏ lookup nào, và không loại bỏ phần nào?

| Quyết định | Có thể giảm | Không tự giảm |
| --- | --- | --- |
| Tái dùng `Method` | Lặp lại `getMethod` / `getDeclaredMethod` | Overhead invoke, thân method |
| Cache kết quả quét annotation/generic hợp lệ | Phân tích/lọc metadata lặp đi lặp lại | Công việc dùng kết quả đó ở mỗi request |
| Chuẩn bị `MethodHandle` một lần | Lặp lại bước lookup/tạo handle | Chi phí thân method; mức lợi từ JIT phải đo |
| Đổi reflection sang gọi Java trực tiếp | Có thể loại bỏ nhiều lớp overhead động | Không thay đổi I/O/CPU nghiệp vụ của method |
| Cache cả **kết quả nghiệp vụ** | Có thể tránh gọi method nếu kết quả được phép tái sử dụng | Tính đúng đắn về dữ liệu mới, invalidation và đồng thời |

Không nhầm **cache metadata** với **cache kết quả nghiệp vụ**. Cache `Method` không trả lại giá trị cũ của lần invoke, còn cache kết quả method phải có quy tắc key/TTL/invalidation riêng.

### 4.3. Khi nào cần MethodHandle hoặc VarHandle?

`java.lang.invoke.MethodHandle` đại diện một đường gọi được chuẩn bị qua `MethodHandles.Lookup` và có thể dùng `invokeExact`/`invoke` theo các quy tắc kiểu riêng. Với đường gọi rất nóng và handle ổn định, JIT có thể tối ưu tốt, nhưng lookup/setup handle cũng có chi phí và không có bảo đảm mọi benchmark đều nhanh hơn reflection.

- Với method hot path, so sánh **cached `Method.invoke`** và **cached `MethodHandle`**, thay vì so handle đã chuẩn bị với `getMethod + invoke` trong mỗi vòng rồi quy chênh lệch hoàn toàn cho invoke.
- `VarHandle` là cơ chế truy cập biến/field có ngữ nghĩa memory-order rõ ràng, khác với phương thức; dùng đúng API theo nhiệm vụ.
- Đừng bỏ qua quyền truy cập, module openness, chữ ký kiểu chính xác và chi phí adaptation của method handle.

## 5. Đo hiệu năng đúng: tách lookup, invoke và tổng đường đi

`System.nanoTime()` là đồng hồ đo khoảng thời gian, nhưng đọc vài lần trong một hàm `main` **không đủ** để kết luận chi phí đơn lẻ của reflection: JIT chưa warm up, khởi tạo class, dead-code elimination, constant folding, GC, CPU scheduling và cache của chính JVM đều có thể ảnh hưởng.

Nên dùng **JMH (Java Microbenchmark Harness)** khi mục tiêu thật sự là so sánh nanosecond/op hoặc throughput trong tình huống nhỏ. Tạo các benchmark tách biệt và chạy trên cùng môi trường:

| Benchmark | Công việc trong mỗi operation | Câu hỏi trả lời |
| --- | --- | --- |
| `lookupOnly` | `clazz.getMethod(name, parameterTypes...)`, consume `Method` | Chi phí tra cứu ở điều kiện đã warm up là bao nhiêu? |
| `invokeCached` | `cachedMethod.invoke(target, ...)`, consume kết quả | Chi phí invoke với `Method` đã có là bao nhiêu? |
| `lookupThenInvoke` | Lookup và invoke trong cùng operation | Tổng chi phí khi code thật tìm lại mỗi lần là bao nhiêu? |
| `directCall` | `target.add(...)`, consume kết quả | Đường gọi Java bình thường cùng logic đích tốn bao nhiêu? |
| `cachedHandleCall` (tùy chọn) | Dùng `MethodHandle` tạo ở setup | Có cơ hội tối ưu khác khi chuẩn bị handle không? |

Một thiết kế thử nghiệm có ý nghĩa phải:

1. Chuẩn bị `target` và `Method` trong `@Setup` cho nhánh cached; **không đưa setup vào thời gian của `invokeCached`**.
2. Có warmup, measurement iterations, nhiều fork/JVM độc lập; ghi phiên bản JDK, máy, JMH, flags và trạng thái compiler.
3. Dùng giá trị đầu vào/kết quả đúng để trình biên dịch không loại bỏ phép tính; trong JMH có thể trả kết quả hoặc dùng `Blackhole`. Chọn target method phản ánh nhiệm vụ thực, không chỉ một phép cộng vô nghĩa nếu muốn suy luận tới ứng dụng.
4. Đo allocation và GC cùng latency/throughput khi cần; phân biệt **cold startup** với **steady state**.
5. Phân biệt `getMethod` tìm một tên với `getMethods` quét tất cả, và phân biệt signature đơn giản với generic/annotation phức tạp.
6. So kết quả tương đối qua nhiều lần thử và khoảng dao động; không gán một con số “reflection chậm gấp N lần” làm thuộc tính cố định của Java.

**Quan trọng:** trong benchmark lookup, JVM có thể tối ưu các giá trị đầu vào không đổi; điều này vẫn phản ánh một trạng thái sử dụng nhất định nhưng chưa đại diện cho lookup theo tên class/method thay đổi liên tục. Hãy đo workload phù hợp: cố định một signature, nhiều overload, hoặc nhiều kiểu được tải động, tùy ứng dụng.

### Phân tích kết quả đo theo nguồn chi phí

Giả sử profiler cho thấy phần lớn thời gian request nằm trong phương thức đích truy vấn cơ sở dữ liệu; tiết kiệm vài lần lookup hầu như không đổi latency end-to-end. Ngược lại, framework ánh xạ hàng triệu object nhỏ, mỗi object lại `getDeclaredFields()` rồi duyệt annotation, có thể tốn allocation và CPU đáng kể; cache schema/metadata một lần thường đáng thử.

Nếu `lookupOnly` chiếm tỷ trọng đáng kể, ưu tiên tái dùng metadata. Nếu `invokeCached` vẫn là nút thắt trên hot path, cân nhắc API tĩnh, method handle ổn định hoặc code generation, nhưng chỉ chọn sau khi đã đo và kiểm tra tính đúng.

## 6. Rủi ro correctness và bẫy tối ưu

### 6.1. Lookup đúng ngữ nghĩa trước khi tối ưu

`getMethod` chỉ lấy method `public` phù hợp (có xét thừa hưởng); `getDeclaredMethod` chỉ lấy member khai báo trên chính class, kể cả non-public. Chúng không thể hoán đổi chỉ vì benchmark thấy khác nhau. Nếu method bị overload, phải dùng đúng `Class<?>` của từng tham số; `Integer.class` không thể thay tùy tiện cho `int.class` khi lookup chữ ký `add(int,int)`.

### 6.2. Reflection invoke có hợp đồng runtime riêng

- `Method.invoke` có thể ném `IllegalAccessException`, `IllegalArgumentException` hoặc `InvocationTargetException`; exception do method đích ném được bọc trong `InvocationTargetException`.
- Với instance method, receiver phải phù hợp; static method không cần instance receiver.
- Tham số primitive được boxing trong mảng đối số, kết quả primitive được boxing trong `Object`; `void` trả `null`.
- Cache sai `Method` theo class/loader hoặc chữ ký dễ dẫn đến lỗi runtime, dù benchmark cache có vẻ nhanh.
- Truy cập non-public trong JPMS có thể bị chặn. Không tự động dùng `setAccessible(true)` như một mẹo hiệu năng; nó thay đổi khả năng truy cập trong phạm vi pháp luật module của JVM.

### 6.3. Đừng tối ưu trước khi biết vòng đời

Một công cụ khởi động, scan annotation một lần rồi lưu router/mapper có thể chấp nhận chi phí startup để giảm chi phí request. Một thư viện plugin sống lâu phải cân nhắc reload và unloading để không giữ class loader cũ. Và một ứng dụng hiếm dùng reflection có thể để code lookup trực tiếp cho đơn giản nếu profiler chưa thấy vấn đề.

## 7. Tổng hợp và câu hỏi tự kiểm tra

Điểm cần nhớ là **thời gian tra cứu metadata** và **thời gian thực thi lời gọi phản xạ** thuộc hai công đoạn. Bản cache `Method` giúp tránh công đoạn tìm `Method` lặp lại; không loại bỏ chi phí `Method.invoke` hoặc công việc của phương thức nghiệp vụ. Metadata chuyên sâu (generic, annotation) cũng có chi phí phân tích riêng cần đo đúng chỗ. Mức lợi luôn phụ thuộc workload/JDK/JIT, nên dùng profiler và JMH thay cho số liệu phỏng đoán.

Tự kiểm tra:

1. Cùng một `Method` gọi 1000 lần, tại sao nên thử cache thay cho 1000 lần `getMethod`? Chi phí nào vẫn tồn tại?
2. `getMethods()` và `getMethod("add", int.class, int.class)` khác nhau về ý nghĩa và lượng công việc như thế nào?
3. Vì sao output `sum=50` của ví dụ chỉ chứng minh tính tương đương chức năng, không chứng minh tốc độ?
4. Khi benchmark `cachedHandleCall` và `lookupThenInvoke`, vì sao kết luận “MethodHandle invoke nhanh hơn” là chưa được kiểm chứng?
5. Khi dùng cache trong plugin có class loader riêng, làm sao tránh nhầm type identity và giữ class loader đã không còn dùng?

### Tài liệu API chính thức

- Java SE 21 — `Class`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html
- Java SE 21 — `Method`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Method.html
- Java SE 21 — `ClassValue`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassValue.html
- Java SE 21 — `MethodHandle`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/MethodHandle.html
- JMH (OpenJDK benchmark harness): https://github.com/openjdk/jmh