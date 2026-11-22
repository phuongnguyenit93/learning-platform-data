# Ảnh hưởng của reflection và deep access

## 1. Reflection ảnh hưởng đến hiệu năng ở những đâu?

Reflection cho phép chương trình kiểm tra class, field, method, constructor và gọi thành viên khi tên hoặc kiểu cần dùng chỉ được xác định ở runtime. Cơ chế này rất hữu ích cho framework, dependency injection, ORM, serialization, plugin và các hệ thống cấu hình động.

Đổi lại, một luồng xử lý dựa trên reflection có thể phát sinh chi phí ở nhiều giai đoạn:

- **Discovery:** tìm class, quét package hoặc đọc metadata.
- **Lookup:** lấy đối tượng mô tả class, field, method hoặc constructor.
- **Access check:** kiểm tra quyền truy cập theo Java language access và ranh giới module.
- **Invocation:** gọi method hoặc constructor thông qua API reflection.
- **Conversion và boxing:** chuyển đổi kiểu, đóng gói primitive hoặc xử lý mảng tham số.
- **Metadata và cache:** lưu đối tượng phản chiếu, annotation hoặc thông tin mapping để tái sử dụng.

Không nên kết luận rằng mọi lời gọi reflection đều chậm hơn một lời gọi Java thông thường theo cùng một tỷ lệ. Chi phí phụ thuộc vào loại thao tác, JDK, cách JVM tối ưu, tần suất gọi, cách cache và workload thực tế. Một thao tác reflection chỉ chạy một lần khi ứng dụng khởi động có thể không đáng kể; cùng thao tác đó nếu nằm trong vòng lặp xử lý hàng triệu request có thể trở thành điểm nóng.

Cũng cần tách chi phí khởi tạo framework khỏi chi phí xử lý mỗi request. Package scan, đọc annotation và tạo metadata thường xảy ra lúc startup hoặc lúc tạo registry. Invocation có thể xảy ra liên tục trong runtime. Hai loại chi phí này cần được đo và tối ưu riêng.

## 2. Các bước reflection có thể tạo overhead

### Discovery và lookup

Ví dụ tìm method theo tên:

~~~java
Method method = Customer.class.getMethod(
    "displayName"
);
~~~

Việc tìm kiếm metadata có thể tốn công hơn so với việc giữ sẵn một tham chiếu method đã tra cứu. Nếu code thực hiện **getMethod** hoặc **getDeclaredMethod** lặp lại trong mỗi lần xử lý, phần lookup có thể tạo thêm chi phí không cần thiết.

Nếu cấu trúc class ổn định, hãy tra cứu một lần khi tạo metadata hoặc registry rồi tái sử dụng đối tượng **Method**, **Field** hoặc **Constructor**. Nếu framework hỗ trợ nhiều class khác nhau, cache theo class và theo loại metadata cần dùng.

### Invocation

Gọi method bằng reflection:

~~~java
Method method = Customer.class.getMethod("name");
Object result = method.invoke(customer);
~~~

Lời gọi **Method.invoke** có một số đặc điểm khác với lời gọi method trực tiếp:

- Tham số được truyền qua mảng hoặc danh sách đối số dạng Object.
- Primitive có thể cần boxing khi đi qua API nhận Object.
- Kết quả được trả về dưới dạng Object, cần cast hoặc unbox nếu cần.
- Lỗi từ method được gọi thường được bọc trong **InvocationTargetException**.
- JVM phải xử lý metadata và quy tắc truy cập tương ứng.

Một lời gọi trực tiếp:

~~~java
String result = customer.name();
~~~

thường cung cấp cho compiler và JIT nhiều thông tin kiểu hơn. Tuy nhiên, chênh lệch hiệu năng thực tế còn phụ thuộc JVM có tối ưu được call site reflection hay không và cách ứng dụng sử dụng đối tượng phản chiếu.

### Constructor và field access

Tạo object bằng reflection:

~~~java
Constructor<Customer> constructor =
    Customer.class.getConstructor(String.class);

Customer customer = constructor.newInstance("An");
~~~

Đọc field:

~~~java
Field field = Customer.class.getDeclaredField("name");
Object value = field.get(customer);
~~~

Ghi field:

~~~java
field.set(customer, "Binh");
~~~

Các thao tác này hữu ích với framework tạo object hoặc ánh xạ dữ liệu. Nếu chúng được gọi nhiều lần, hãy xem xét việc cache constructor/field và tránh lặp lại bước tra cứu. Với dữ liệu có kiểu xác định và đường chạy nóng, API public hoặc factory có kiểu rõ ràng thường dễ tối ưu hơn.

## 3. Reflection trên các phiên bản JDK hiện đại

Cách triển khai reflection của JVM đã thay đổi theo thời gian. Từ JDK 18, JEP 416 thay thế phần triển khai core reflection cũ dựa trên các accessor được sinh bằng bytecode bằng một triển khai dựa trên method handles.

Điều này có nghĩa là các kết luận hiệu năng rút ra từ một JDK cũ có thể không còn đúng với JDK mới. Một số trường hợp reflection có thể được JIT tối ưu tốt hơn, đặc biệt khi đối tượng **Method**, **Constructor** hoặc **Field** được giữ ổn định và có thể được xem như hằng tại call site.

Kết quả vẫn phụ thuộc cách sử dụng:

- Đối tượng reflection được tra cứu một lần và lưu trong field ổn định có thể tạo điều kiện cho JIT tối ưu.
- Lookup động liên tục, metadata thay đổi hoặc call site đa hình phức tạp có thể hạn chế tối ưu.
- Boxing, mảng tham số, chuyển kiểu và exception vẫn có thể tạo overhead.
- Reflection truy cập private hoặc vượt qua ranh giới module có thêm các yêu cầu kiểm tra quyền truy cập.

Vì vậy, khi tối ưu, hãy đo trên đúng JDK dùng trong production. Không lấy một benchmark cũ làm kết luận cho mọi phiên bản Java.

## 4. Deep access và chi phí kiểm tra quyền truy cập

Deep reflection thường dùng **setAccessible(true)** hoặc **trySetAccessible()** để truy cập thành viên không public:

~~~java
Field field = Customer.class.getDeclaredField("email");

if (field.trySetAccessible()) {
    Object email = field.get(customer);
}
~~~

JVM phải tuân theo quy tắc truy cập của Java và JPMS. Package thuộc named module có thể được export cho truy cập kiểu public nhưng chưa được mở cho reflection sâu. Nếu package không được mở phù hợp, **trySetAccessible()** có thể trả về false hoặc **setAccessible(true)** có thể ném **InaccessibleObjectException**.

Deep access có thể tác động tới thiết kế và hiệu năng theo một số cách:

- Framework cần kiểm tra quyền truy cập khi khởi tạo metadata.
- Nếu gọi lại thao tác mở quyền nhiều lần, ứng dụng thực hiện công việc lặp lại không cần thiết.
- Quyền truy cập có thể bị giới hạn bởi module descriptor hoặc tùy chọn runtime.
- Việc mở package rộng làm giảm tính đóng gói và khiến implementation nội bộ trở thành điểm phụ thuộc của framework.

Nếu framework cần truy cập sâu, hãy thực hiện kiểm tra và thiết lập quyền một lần khi tạo metadata, sau đó tái sử dụng đối tượng đã cấu hình. Không nên gọi **setAccessible(true)** cho cùng một field ở mỗi request.

### exports và opens có vai trò khác nhau

**exports** cho phép module khác truy cập các kiểu public trong package:

~~~java
module com.example.model {
    exports com.example.model.api;
}
~~~

**opens** cho phép deep reflection vào package:

~~~java
module com.example.model {
    opens com.example.model.entity
        to com.example.orm;
}
~~~

Nếu cần cấu hình tạm thời lúc khởi chạy, có thể dùng:

~~~bash
java \
  --add-opens com.example.model/com.example.model.entity=com.example.orm \
  -m com.example.app/com.example.app.Main
~~~

Các chỉ thị này xử lý quyền truy cập, không phải cơ chế tăng tốc reflection. Mở package không tự làm **Method.invoke** nhanh hơn; mục đích là cho phép thao tác reflection vốn bị JPMS chặn. Chỉ mở đúng package cho đúng module cần dùng.

## 5. Cache metadata để tránh lookup lặp lại

Một tối ưu phổ biến là lưu metadata đã tra cứu thay vì tìm lại trong mỗi lần gọi.

Ví dụ cache method theo class:

~~~java
private static final Map<Class<?>, Method> NAME_METHODS =
    new ConcurrentHashMap<>();

static Method nameMethod(Class<?> type) {
    return NAME_METHODS.computeIfAbsent(type, key -> {
        try {
            return key.getMethod("name");
        } catch (NoSuchMethodException e) {
            throw new IllegalArgumentException(e);
        }
    });
}
~~~

Khi dùng:

~~~java
Method method = nameMethod(customer.getClass());
Object name = method.invoke(customer);
~~~

Cache có thể giảm lookup lặp lại, nhưng cũng cần quản lý vòng đời và bộ nhớ:

- Không cache mọi class đã từng xuất hiện nếu tập class không giới hạn.
- Một static map giữ strong reference đến Class có thể ngăn classloader được giải phóng.
- Ứng dụng hỗ trợ hot reload hoặc plugin cần dỡ module/classloader phải có chiến lược dọn cache.
- Cache nên lưu metadata thực sự cần dùng, tránh giữ quá nhiều annotation, MethodHandle hoặc object phụ trợ.
- Nếu nhiều thread cùng khởi tạo metadata, dùng cơ chế đồng bộ hoặc concurrent cache phù hợp.

Với metadata gắn với từng class, **ClassValue** thường là lựa chọn đáng cân nhắc:

~~~java
private static final ClassValue<Method> NAME_METHOD =
    new ClassValue<>() {
        @Override
        protected Method computeValue(Class<?> type) {
            try {
                return type.getMethod("name");
            } catch (NoSuchMethodException e) {
                throw new IllegalArgumentException(e);
            }
        }
    };
~~~

**ClassValue** gắn dữ liệu với vòng đời của Class và phù hợp với metadata theo class. Dù vậy, vẫn cần tránh để metadata giữ các tham chiếu ngoài vòng đời mong muốn hoặc tạo chuỗi tham chiếu giữ lại classloader khác.

## 6. MethodHandles như một lựa chọn

**MethodHandles** cung cấp cách gọi method và truy cập field thông qua một đối tượng handle có kiểu. API này thường phù hợp khi framework muốn xây dựng call site có kiểu rõ ràng hoặc tái sử dụng một thao tác đã tra cứu.

Ví dụ tìm method public:

~~~java
MethodHandles.Lookup lookup = MethodHandles.lookup();

MethodHandle getter = lookup.findVirtual(
    Customer.class,
    "name",
    MethodType.methodType(String.class)
);

String name = (String) getter.invokeExact(customer);
~~~

So với **Method.invoke**, MethodHandle có một số điểm khác:

- MethodHandle mang kiểu tham số và kiểu trả về trong MethodType.
- Quyền truy cập được kiểm tra khi tạo handle.
- Có thể kết hợp, biến đổi và tái sử dụng handle.
- **invokeExact** yêu cầu kiểu tại call site khớp chính xác với kiểu handle.
- Lỗi và chuyển đổi kiểu có quy tắc khác reflection.

Đối với deep access, có thể dùng **privateLookupIn** khi module/package cho phép:

~~~java
MethodHandles.Lookup privateLookup =
    MethodHandles.privateLookupIn(
        Customer.class,
        MethodHandles.lookup()
    );
~~~

Nếu package chưa mở cho module caller, việc tạo private lookup có thể thất bại. MethodHandles không bỏ qua ranh giới JPMS.

Không nên chuyển toàn bộ reflection sang MethodHandles chỉ vì nghe nói nhanh hơn. Hãy đo trên workload thật. Với một số call site, JIT tối ưu MethodHandle rất tốt; ở trường hợp khác, chi phí chuyển đổi kiểu, lookup động hoặc logic framework vẫn chi phối.

## 7. Giảm chi phí ở tầng thiết kế

Nếu reflection nằm trong đường chạy nóng, có thể xem xét thay đổi thiết kế:

- **Gọi API trực tiếp:** nếu kiểu và method đã biết tại compile time, gọi trực tiếp thường rõ ràng và dễ tối ưu.
- **Interface dispatch:** định nghĩa interface và gọi qua interface thay vì tìm method bằng tên mỗi lần.
- **Factory hoặc constructor được đăng ký:** tạo object qua factory đã biết thay vì quét constructor liên tục.
- **ServiceLoader:** dùng SPI cho plugin provider được khai báo thay vì quét mọi class tìm implementation.
- **Annotation processing:** chuyển một phần công việc khám phá metadata sang compile time để giảm startup scan.
- **Code generation:** sinh mapper, serializer hoặc adapter khi build nếu workload yêu cầu throughput cao và cấu trúc ổn định.
- **Cache metadata:** tra cứu một lần và tái sử dụng trong vòng đời hợp lý.

Ví dụ interface:

~~~java
public interface NameProvider {
    String name(Customer customer);
}
~~~

Ứng dụng giữ implementation:

~~~java
NameProvider provider = new DefaultNameProvider();
String name = provider.name(customer);
~~~

Nếu mục đích chỉ là lấy tên customer, interface có thể đơn giản hơn nhiều so với tìm method bằng chuỗi và gọi reflection ở mỗi lần xử lý. Nhưng với framework cần hỗ trợ class không biết trước, reflection vẫn có giá trị; hãy tối ưu vị trí và tần suất sử dụng.

## 8. Reflection ảnh hưởng đến startup và throughput

Không phải mọi ứng dụng đều chịu tác động theo cùng một cách.

**Startup time** có thể tăng do:

- Quét package và liệt kê class.
- Đọc annotation hoặc generic metadata.
- Tạo registry cho hàng nghìn class.
- Tra cứu constructor, field và method.
- Tạo proxy, adapter hoặc metadata ORM.
- Nạp class và khởi tạo framework.

**Throughput hoặc latency** có thể bị ảnh hưởng khi:

- Reflection invocation nằm trong vòng lặp xử lý request.
- Framework ánh xạ hàng triệu field hoặc property.
- Serialization/deserialization gọi accessor động cho mỗi object.
- ORM đọc/ghi field bằng reflection trong mỗi thao tác.
- Mỗi lần xử lý lại lookup method hoặc kiểm tra accessibility.

Một ứng dụng có thể startup chậm nhưng runtime nhanh nếu metadata được tạo trước và cache tốt. Ngược lại, startup nhẹ nhưng mỗi request lại quét hoặc tra cứu động có thể gây latency cao. Cần đo hai giai đoạn độc lập.

## 9. Đo hiệu năng đúng cách với JMH

Không nên dùng một vòng lặp đơn giản và **System.nanoTime()** để kết luận reflection chậm hơn bao nhiêu lần. JIT, dead-code elimination, warmup, class loading và CPU scheduling có thể làm sai lệch kết quả.

Dùng JMH để benchmark các trường hợp tương đương:

1. Lời gọi trực tiếp.
2. Reflection lookup ở mỗi lần gọi.
3. Reflection với Method đã cache.
4. MethodHandle đã cache.
5. Factory hoặc interface dispatch nếu phù hợp.

Ví dụ benchmark khung:

~~~java
@State(Scope.Thread)
public class ReflectionBenchmark {
    private final Customer customer = new Customer("An");
    private Method cachedMethod;

    @Setup
    public void setup() throws Exception {
        cachedMethod = Customer.class.getMethod("name");
    }

    @Benchmark
    public String direct() {
        return customer.name();
    }

    @Benchmark
    public Object reflectionCached() throws Exception {
        return cachedMethod.invoke(customer);
    }

    @Benchmark
    public Object reflectionLookupEachTime() throws Exception {
        Method method =
            Customer.class.getMethod("name");
        return method.invoke(customer);
    }
}
~~~

Đây chỉ là khung minh họa. Trong benchmark thực tế, cần bảo đảm các trường hợp trả về cùng kết quả và thực hiện công việc tương đương. Có thể thêm benchmark MethodHandle, nhưng phải cấu hình MethodType và kiểu trả về phù hợp.

Các nguyên tắc đo:

- Dùng warmup và nhiều measurement iteration.
- Chạy nhiều fork để giảm ảnh hưởng trạng thái JVM trước đó.
- Tránh để kết quả bị loại bỏ; trả kết quả hoặc dùng Blackhole.
- Tách lookup khỏi invocation nếu muốn biết chi phí của từng bước.
- Đo cả throughput và latency nếu ứng dụng quan tâm đến cả hai.
- Dùng đúng JDK, flags, CPU và workload gần production.
- Đo cả startup riêng bằng công cụ phù hợp, không suy ra startup từ JMH microbenchmark.
- Chạy nhiều lần và báo độ biến thiên, không chỉ chọn con số tốt nhất.

Nếu mục tiêu là giảm thời gian startup, hãy đo số class được quét, thời gian tạo registry và thời gian khởi tạo framework. Nếu mục tiêu là tăng throughput, đo số invocation mỗi request, allocations, CPU profile và latency phân vị.

## 10. Những chi phí bộ nhớ cần lưu ý

Reflection không chỉ ảnh hưởng CPU. Framework có thể tạo và giữ nhiều metadata object:

- Method, Field và Constructor.
- Annotation proxy và dữ liệu annotation.
- Mảng tham số và object boxing.
- Map registry theo class.
- MethodHandle và lookup object.
- Proxy class hoặc adapter được sinh động.

Việc cache có thể giảm CPU nhưng tăng bộ nhớ. Nếu cache không giới hạn, số class/plugin tăng dần có thể làm heap phình ra. Nếu cache giữ class từ classloader plugin, classloader có thể không được giải phóng sau khi plugin dừng.

Khi thiết kế cache:

1. Xác định dữ liệu có thể tái sử dụng và thời gian tồn tại của nó.
2. Gắn metadata theo Class khi phù hợp bằng ClassValue.
3. Có cơ chế xóa registry khi plugin hoặc ứng dụng con bị dỡ.
4. Không giữ classloader, Method hoặc MethodHandle lâu hơn cần thiết.
5. Theo dõi heap, số class được nạp và classloader khi ứng dụng hỗ trợ reload.

Đừng tối ưu CPU bằng cache vô hạn. Chọn chính sách cache theo vòng đời class và plugin.

## 11. Deep access và bảo mật

Deep reflection có thể làm tăng rủi ro phụ thuộc vào implementation nội bộ. Khi framework truy cập field private hoặc package không được công khai, thay đổi cấu trúc class có thể làm ứng dụng hỏng dù API public không thay đổi.

Một số nguyên tắc:

- Ưu tiên constructor, accessor hoặc API public.
- Mở package bằng **opens ... to module** thay vì mở toàn bộ module nếu có thể.
- Tránh mở rộng các package nội bộ của JDK chỉ để làm thư viện cũ tiếp tục chạy.
- Cập nhật framework hỗ trợ JPMS và phiên bản JDK mục tiêu.
- Xử lý lỗi **InaccessibleObjectException** rõ ràng, không âm thầm bỏ qua.
- Không dùng reflection để vượt qua quy tắc bảo mật hoặc ranh giới module ngoài mục đích đã xác định.

**opens** không làm invocation nhanh hơn. Nó chỉ cho phép deep reflection trong phạm vi được khai báo. Việc mở rộng quyền truy cập có thể ảnh hưởng tính đóng gói và khả năng bảo trì, vì vậy không nên coi nó là một tối ưu hiệu năng.

## 12. Quy trình tối ưu đề xuất

Khi phát hiện reflection ảnh hưởng hiệu năng, hãy thực hiện theo thứ tự:

1. Xác định thao tác reflection nằm ở startup hay trong đường chạy request.
2. Dùng profiler để xác nhận lookup, invocation, access check hoặc object allocation thực sự chiếm thời gian.
3. Tra cứu metadata một lần và cache trong phạm vi vòng đời phù hợp.
4. Kiểm tra cache có giữ classloader hoặc plugin đã dỡ hay không.
5. Xem xét MethodHandles nếu cần call site có kiểu và có thể tái sử dụng.
6. Thay reflection bằng API public, interface, factory hoặc code generation khi cấu trúc đã biết.
7. Nếu cần deep access, mở đúng package cho đúng module và thiết lập quyền một lần khi tạo metadata.
8. Benchmark các phương án bằng JMH trên đúng JDK mục tiêu.
9. Chạy kiểm thử chức năng để bảo đảm framework, ORM, serialization và plugin vẫn hoạt động.
10. Đo lại startup, throughput, latency và bộ nhớ trên artifact gần production.

Không nên tối ưu một đoạn reflection chỉ vì nó trông phức tạp. Nếu profiler cho thấy chi phí không đáng kể, thay đổi có thể làm code khó bảo trì hơn mà không cải thiện trải nghiệm thực tế.

## 13. Ghi nhớ

- Reflection có chi phí ở discovery, lookup, access check, invocation, boxing và metadata.
- Lookup lặp lại thường có thể giảm bằng cách cache Method, Field hoặc Constructor.
- JDK 18 trở lên dùng triển khai core reflection dựa trên method handles theo JEP 416; benchmark trên JDK mục tiêu.
- **exports** cho phép truy cập kiểu public; **opens** cho phép deep reflection. Hai cơ chế không phải tối ưu tốc độ.
- **MethodHandles** có kiểu và phù hợp với một số call site động, nhưng không tự động nhanh hơn mọi cách dùng reflection.
- Cache cần quản lý bộ nhớ và vòng đời classloader, đặc biệt trong ứng dụng plugin/hot reload.
- Dùng JMH và profiler để tách lookup, invocation, startup, throughput và latency.
- Chỉ thay đổi thiết kế sau khi đã xác định reflection là điểm nóng thực sự.

Reflection là công cụ quan trọng để xây dựng framework linh hoạt. Hiệu năng tốt phụ thuộc vào việc đặt discovery và lookup ở đúng giai đoạn, tái sử dụng metadata, giới hạn deep access và đo trên JDK triển khai. Khi đường chạy đã ổn định, API có kiểu rõ ràng hoặc code được sinh ở build time có thể giảm công việc động và giúp JVM tối ưu dễ hơn.
