# Tạo VarHandle bằng Lookup và arrayElementVarHandle trong Java

## 1. VarHandle là gì?

VarHandle là API chuẩn trong java.lang.invoke được giới thiệu từ Java 9. Nó cung cấp một tham chiếu có kiểu tới một biến hoặc một vị trí phần tử, cho phép đọc, ghi và thực hiện các thao tác nguyên tử với những ngữ nghĩa bộ nhớ được xác định rõ.

VarHandle có thể đại diện cho:

- Trường instance của một object.
- Trường static của một class.
- Phần tử trong mảng primitive hoặc mảng reference.
- Một vị trí trong cấu trúc dữ liệu được hỗ trợ bởi API VarHandle khác.

Khác với việc truy cập trường bằng reflection thông thường, VarHandle cung cấp các access mode như get, set, getVolatile, setRelease và compareAndSet. Các thao tác này cho phép chọn mức đồng bộ phù hợp mà không cần dựa vào API nội bộ như sun.misc.Unsafe.

Hai cách tạo handle quan trọng trong bài này:

- Dùng MethodHandles.Lookup.findVarHandle hoặc findStaticVarHandle để tìm trường của class.
- Dùng MethodHandles.arrayElementVarHandle để tạo handle truy cập phần tử mảng.

VarHandle không tự động làm mọi thao tác trên biến trở thành nguyên tử. Tính nguyên tử và thứ tự bộ nhớ phụ thuộc access mode được gọi.

## 2. Lookup là gì?

MethodHandles.Lookup là đối tượng mang thông tin về class đang thực hiện việc tra cứu và các quyền truy cập mà class đó có. Lookup được dùng để tìm field, method, constructor hoặc tạo VarHandle tương ứng.

Tạo Lookup của class hiện tại:

~~~java
MethodHandles.Lookup lookup = MethodHandles.lookup();
~~~

lookup() trả về Lookup gắn với class gọi phương thức. Lookup này có quyền truy cập theo ngữ cảnh của class đó, bao gồm khả năng truy cập thành viên private của chính class theo quy tắc ngôn ngữ và module.

Một số cách tạo Lookup:

| API | Phạm vi |
|---|---|
| MethodHandles.lookup() | Quyền truy cập theo class đang gọi |
| MethodHandles.publicLookup() | Chỉ quyền truy cập public |
| MethodHandles.privateLookupIn(target, lookup) | Tạo Lookup có quyền private đối với target khi điều kiện module/access được đáp ứng |
| lookup.in(target) | Chuyển lookup class và điều chỉnh quyền theo quy tắc Lookup; không tự cấp thêm quyền |

Lookup không phải cách bỏ qua kiểm soát truy cập. Việc tìm một trường vẫn chịu ảnh hưởng của visibility, module readability và package openness.

## 3. Tạo VarHandle cho trường instance bằng findVarHandle

Lookup.findVarHandle tìm trường instance theo class, tên trường và kiểu dữ liệu chính xác:

~~~java
VarHandle findVarHandle(
    Class<?> recv,
    String name,
    Class<?> type
)
~~~

Ví dụ class có trường private:

~~~java
public class Counter {
    private int value;
}
~~~

Nếu thao tác tạo Lookup được thực hiện trong chính class Counter, có thể tìm trường private value:

~~~java
MethodHandles.Lookup lookup = MethodHandles.lookup();

VarHandle valueHandle = lookup.findVarHandle(
    Counter.class,
    "value",
    int.class
);
~~~

Handle này có một coordinate là object Counter. Khi đọc hoặc ghi, truyền object đó vào trước:

~~~java
Counter counter = new Counter();

valueHandle.set(counter, 10);
int value = (int) valueHandle.get(counter);
~~~

Kiểu trả về của varType() là kiểu trường, trong ví dụ này là int. coordinateTypes() mô tả kiểu đối số định vị biến; với trường instance, danh sách coordinate có kiểu Counter.

Tên trường và kiểu phải khớp với khai báo thực tế. Nếu không tìm thấy trường tương ứng, phương thức ném NoSuchFieldException. Nếu Lookup không có quyền truy cập, phương thức ném IllegalAccessException.

## 4. Tạo VarHandle cho trường static bằng findStaticVarHandle

Trường static không gắn với một object cụ thể. Dùng Lookup.findStaticVarHandle:

~~~java
VarHandle findStaticVarHandle(
    Class<?> decl,
    String name,
    Class<?> type
)
~~~

Ví dụ:

~~~java
public class Settings {
    private static long total;
}
~~~

Tạo handle:

~~~java
VarHandle totalHandle = MethodHandles.lookup().findStaticVarHandle(
    Settings.class,
    "total",
    long.class
);
~~~

Đọc và ghi không cần truyền receiver:

~~~java
totalHandle.set(100L);
long total = (long) totalHandle.get();
~~~

Sự khác nhau về coordinate:

| Loại biến | Cách tìm | Coordinate khi gọi |
|---|---|---|
| Instance field | findVarHandle | Object chứa trường |
| Static field | findStaticVarHandle | Không có receiver |
| Array element | arrayElementVarHandle | Mảng và chỉ số |

Không truyền object vào static VarHandle. Ngược lại, bỏ receiver khi gọi instance VarHandle sẽ gây sai kiểu lời gọi.

## 5. Quyền truy cập private và privateLookupIn

Nếu class gọi không phải class khai báo trường private, Lookup thông thường có thể không truy cập được trường đó. Java 9 cung cấp MethodHandles.privateLookupIn để tạo Lookup có quyền truy cập riêng cho class đích khi điều kiện truy cập module được đáp ứng.

~~~java
MethodHandles.Lookup privateLookup =
    MethodHandles.privateLookupIn(Target.class, MethodHandles.lookup());

VarHandle handle = privateLookup.findVarHandle(
    Target.class,
    "value",
    int.class
);
~~~

Với class ở module khác, module gọi cần đọc module đích và package chứa class đích phải được mở (opens) cho module gọi. Quyền truy cập còn phụ thuộc Lookup ban đầu có các access mode cần thiết.

Ví dụ khai báo module có thể mở package cho một module cụ thể:

~~~java
module target.module {
    opens com.example.model to consumer.module;
}
~~~

Nếu ứng dụng chạy trên classpath hoặc các module không đặt giới hạn bổ sung, điều kiện có thể đơn giản hơn. Tuy vậy, không nên giả định privateLookupIn luôn thành công trong mọi môi trường.

Khi chỉ cần truy cập public member, ưu tiên Lookup phù hợp với quyền public. Chỉ mở package hoặc cấp quyền private khi kiến trúc thực sự cần truy cập thành viên đó.

## 6. Tạo VarHandle cho phần tử mảng bằng arrayElementVarHandle

MethodHandles.arrayElementVarHandle tạo VarHandle cho phần tử của một kiểu mảng:

~~~java
VarHandle arrayHandle =
    MethodHandles.arrayElementVarHandle(int[].class);
~~~

Tham số là class của cả mảng, ví dụ int[].class hoặc String[].class, không phải class của phần tử riêng lẻ.

Với int[]:

- varType() là int.class.
- coordinateTypes() gồm int[] và int.
- Coordinate thứ nhất là mảng.
- Coordinate thứ hai là chỉ số phần tử.

Đọc và ghi:

~~~java
int[] numbers = {10, 20, 30};

int second = (int) arrayHandle.get(numbers, 1);
arrayHandle.set(numbers, 1, 99);
~~~

Sau khi ghi, numbers[1] có giá trị 99.

Với mảng reference, kiểu phần tử được lấy từ component type:

~~~java
VarHandle namesHandle =
    MethodHandles.arrayElementVarHandle(String[].class);

String[] names = {"An", "Binh"};
namesHandle.set(names, 0, "Chi");
String firstName = (String) namesHandle.get(names, 0);
~~~

Mảng vẫn tuân theo kiểm tra kiểu và giới hạn chỉ số thông thường. Truyền null, chỉ số ngoài phạm vi hoặc giá trị không tương thích với kiểu phần tử có thể gây NullPointerException, IndexOutOfBoundsException hoặc ClassCastException/ArrayStoreException tùy thao tác.

arrayElementVarHandle là factory độc lập; không cần Lookup để tạo handle cho phần tử mảng.

## 7. Kiểm tra kiểu và coordinate của VarHandle

VarHandle chứa thông tin về kiểu biến và các coordinate cần thiết để xác định vị trí biến.

Hai phương thức hữu ích:

~~~java
Class<?> variableType = handle.varType();
List<Class<?>> coordinates = handle.coordinateTypes();
~~~

Ví dụ:

- Instance field Counter.value: varType là int, coordinate là Counter.
- Static field Settings.total: varType là long, không có coordinate.
- Phần tử int[]: varType là int, coordinate lần lượt là int[] và int.

Các phương thức này giúp kiểm tra handle khi xây dựng thư viện truy cập dữ liệu tổng quát. Tuy nhiên, không nên thay thế kiểm tra kiểu ở compile time bằng cách chỉ dựa vào metadata lúc chạy.

Các lời gọi get/set là signature-polymorphic. Kiểu tại vị trí gọi cần tương thích với kiểu handle. Dùng sai kiểu có thể gây WrongMethodTypeException hoặc ClassCastException.

## 8. Access mode: đọc, ghi và thao tác nguyên tử

VarHandle cung cấp nhiều access mode. Mỗi mode quy định ngữ nghĩa truy cập và thứ tự bộ nhớ.

| Access mode | Ý nghĩa |
|---|---|
| get / set | Đọc hoặc ghi plain |
| getOpaque / setOpaque | Ngữ nghĩa opaque, bảo đảm nhất quán ở mức opaque |
| getAcquire / setRelease | Acquire khi đọc và release khi ghi |
| getVolatile / setVolatile | Ngữ nghĩa volatile |
| compareAndSet | So sánh và cập nhật nguyên tử |
| compareAndExchange | So sánh và trao đổi nguyên tử, trả về giá trị quan sát |
| getAndSet | Đọc giá trị cũ và thay bằng giá trị mới một cách nguyên tử |
| getAndAdd | Cộng một giá trị và trả về giá trị cũ một cách nguyên tử |

Chọn mode theo yêu cầu đồng bộ:

~~~java
handle.getVolatile(target);
handle.setVolatile(target, 20);

boolean updated = handle.compareAndSet(target, 20, 30);
~~~

get/set plain không tự tạo bảo đảm volatile. Nếu nhiều thread cùng truy cập và cần công bố dữ liệu hoặc phối hợp bộ nhớ, phải chọn mode thích hợp hoặc dùng cơ chế đồng bộ khác.

Không phải mọi access mode đều được hỗ trợ bởi mọi loại VarHandle. Có thể kiểm tra trước:

~~~java
boolean supported = handle.isAccessModeSupported(
    VarHandle.AccessMode.GET_AND_ADD
);
~~~

Nếu gọi mode không được hỗ trợ, VarHandle ném UnsupportedOperationException. Hãy kiểm tra hợp đồng và kiểu biến thay vì giả định mọi handle đều hỗ trợ mọi thao tác nguyên tử.

## 9. compareAndSet và cập nhật nguyên tử

compareAndSet(expected, newValue) chỉ cập nhật nếu giá trị hiện tại bằng expected. Việc so sánh và ghi được thực hiện nguyên tử:

~~~java
boolean success = handle.compareAndSet(target, 10, 11);
~~~

Nếu giá trị hiện tại là 10, thao tác ghi 11 và trả về true. Nếu giá trị đã thay đổi, thao tác không ghi và trả về false.

Với mảng:

~~~java
int[] values = {1, 2, 3};
VarHandle elements =
    MethodHandles.arrayElementVarHandle(int[].class);

boolean success = elements.compareAndSet(values, 1, 2, 20);
~~~

Nếu values[1] đang là 2, nó được cập nhật thành 20.

compareAndSet thường là nền tảng cho vòng lặp cập nhật không khóa (lock-free), nhưng một lời gọi CAS không tự bảo đảm toàn bộ thuật toán lock-free. Cần xem xét contention, retry, ABA problem và tính đúng đắn của trạng thái.

Nếu chỉ cập nhật một biến số nguyên, AtomicInteger có thể đơn giản hơn. VarHandle phù hợp khi cần nhiều memory mode, thao tác trực tiếp trên field/array hoặc tích hợp vào cấu trúc dữ liệu riêng.

## 10. Tạo handle cho các kiểu mảng khác

arrayElementVarHandle hỗ trợ cả mảng primitive và mảng reference:

~~~java
VarHandle ints = MethodHandles.arrayElementVarHandle(int[].class);
VarHandle longs = MethodHandles.arrayElementVarHandle(long[].class);
VarHandle booleans = MethodHandles.arrayElementVarHandle(boolean[].class);
VarHandle strings = MethodHandles.arrayElementVarHandle(String[].class);
VarHandle objects = MethodHandles.arrayElementVarHandle(Object[].class);
~~~

Kiểu mảng quyết định kiểu biến mà handle thao tác. Ví dụ long[] có varType là long, còn String[] có varType là String.

Với mảng nhiều chiều, một handle phần tử của String[][] thao tác một phần tử thuộc kiểu String[] tại một chỉ số của mảng ngoài. Muốn truy cập phần tử String bên trong, cần lấy mảng con rồi dùng handle tương ứng cho String[].

Không truyền int.class thay cho int[].class. Factory cần kiểu array class để xác định chính xác kiểu phần tử và coordinate.

## 11. Ví dụ hoàn chỉnh: Lookup, static field và arrayElementVarHandle

Ví dụ dùng Lookup tạo handle cho trường private instance và trường private static của class hiện tại; đồng thời tạo handle cho phần tử int[].

**Tệp VarHandleCreationDemo.java:**

~~~java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;

public class VarHandleCreationDemo {
    private int count;
    private static long total;

    public static void main(String[] args) throws ReflectiveOperationException {
        MethodHandles.Lookup lookup = MethodHandles.lookup();

        VarHandle countHandle = lookup.findVarHandle(
                VarHandleCreationDemo.class, "count", int.class);
        VarHandle totalHandle = lookup.findStaticVarHandle(
                VarHandleCreationDemo.class, "total", long.class);
        VarHandle arrayHandle =
                MethodHandles.arrayElementVarHandle(int[].class);

        VarHandleCreationDemo target = new VarHandleCreationDemo();
        countHandle.set(target, 10);
        System.out.println("field initial: " + (int) countHandle.get(target));
        System.out.println("field CAS: "
                + countHandle.compareAndSet(target, 10, 15));
        System.out.println("field after CAS: " + (int) countHandle.get(target));

        totalHandle.set(100L);
        System.out.println("static total: " + (long) totalHandle.get());

        int[] values = {3, 6, 9};
        arrayHandle.set(values, 1, 12);
        System.out.println("array element: "
                + (int) arrayHandle.get(values, 1));
        System.out.println("array CAS: "
                + arrayHandle.compareAndSet(values, 1, 12, 18));
        System.out.println("array final: " + values[1]);
        System.out.println("array coordinates: "
                + arrayHandle.coordinateTypes().size());
        System.out.println("array var type: "
                + arrayHandle.varType().getSimpleName());
    }
}
~~~

Biên dịch và chạy bằng Java 17 trở lên:

~~~bash
javac --release 17 -Xlint:all VarHandleCreationDemo.java
java VarHandleCreationDemo
~~~

Output:

~~~text
field initial: 10
field CAS: true
field after CAS: 15
static total: 100
array element: 12
array CAS: true
array final: 18
array coordinates: 2
array var type: int
~~~

Ví dụ cho thấy ba loại handle có cách truyền coordinate khác nhau. Instance field nhận object, static field không nhận object, còn array element nhận cả mảng và chỉ số.

Lệnh compareAndSet cập nhật giá trị chỉ khi giá trị hiện tại khớp expected. coordinateTypes() và varType() cho biết cấu trúc kiểu của handle.

## 12. Lỗi thường gặp

- **Truyền sai kiểu vào findVarHandle:** tên trường và kiểu class phải khớp chính xác; kiểu sai có thể dẫn đến NoSuchFieldException.
- **Dùng Lookup không đủ quyền:** truy cập private có thể ném IllegalAccessException. Tạo Lookup đúng ngữ cảnh và kiểm tra quy tắc module.
- **Nhầm lookup.in với cấp quyền private:** in() không tự cấp thêm quyền truy cập.
- **Dùng publicLookup cho private field:** publicLookup chỉ có quyền truy cập public.
- **Dùng arrayElementVarHandle(int.class):** phải truyền array class như int[].class.
- **Bỏ coordinate:** instance field cần receiver; array element cần mảng và index; static field không cần receiver.
- **Dùng sai kiểu primitive:** lời gọi signature-polymorphic cần kiểu tương thích, nếu không có thể ném WrongMethodTypeException.
- **Giả định mọi access mode đều được hỗ trợ:** kiểm tra isAccessModeSupported khi cần.
- **Dùng get/set plain cho dữ liệu chia sẻ mà cần đồng bộ:** chọn volatile, acquire/release hoặc atomic mode theo mô hình bộ nhớ.
- **Coi get rồi set là một thao tác nguyên tử:** nếu cần cập nhật có điều kiện, dùng compareAndSet hoặc access mode nguyên tử phù hợp.
- **Quên giới hạn mảng:** array handle vẫn kiểm tra null và index như truy cập mảng thông thường.
- **Coi VarHandle là cơ chế tự khóa:** VarHandle cung cấp access mode; nó không tự khóa toàn bộ đoạn code hoặc thuật toán.

## 13. Chọn API theo nhu cầu

| Nhu cầu | API |
|---|---|
| Tạo handle cho instance field | Lookup.findVarHandle |
| Tạo handle cho static field | Lookup.findStaticVarHandle |
| Tạo handle cho phần tử mảng | MethodHandles.arrayElementVarHandle |
| Tạo Lookup theo class hiện tại | MethodHandles.lookup |
| Chỉ tra cứu thành viên public | MethodHandles.publicLookup |
| Xin quyền private cho class đích | MethodHandles.privateLookupIn |
| Xem kiểu biến | VarHandle.varType |
| Xem coordinate | VarHandle.coordinateTypes |
| Kiểm tra access mode | VarHandle.isAccessModeSupported |
| Đọc/ghi plain | get / set |
| Đọc/ghi volatile | getVolatile / setVolatile |
| Cập nhật có điều kiện nguyên tử | compareAndSet |
| Cập nhật số nguyên tử | getAndAdd |

## 14. Ghi nhớ

VarHandle là API chuẩn từ Java 9 để truy cập field và phần tử mảng với các access mode có ngữ nghĩa bộ nhớ rõ ràng. Dùng MethodHandles.lookup() để lấy Lookup theo quyền của class gọi, findVarHandle cho instance field và findStaticVarHandle cho static field. Dùng MethodHandles.arrayElementVarHandle(int[].class) để tạo handle cho phần tử mảng; coordinate của nó là mảng và chỉ số. Kiểm tra quyền truy cập, kiểu và access mode được hỗ trợ. get/set plain không thay thế volatile hoặc thao tác nguyên tử; dùng compareAndSet hay mode phù hợp khi cần cập nhật an toàn giữa nhiều thread.
