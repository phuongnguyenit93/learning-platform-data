# Truy cập có kiểu tới trường và phần tử mảng bằng VarHandle

Java 9 giới thiệu `java.lang.invoke.VarHandle` để truy cập một biến theo kiểu đã biết tại thời điểm tạo handle. Một VarHandle có thể đại diện cho field instance, field static hoặc phần tử của array. Qua cùng một đối tượng handle, chương trình có thể đọc, ghi, dùng memory ordering hoặc thực hiện thao tác cập nhật nguyên tử như compare-and-set.

VarHandle được thiết kế cho các thao tác truy cập biến có kiểm soát kiểu và ngữ nghĩa bộ nhớ rõ ràng. Nó cung cấp một API cấp thấp hơn các lớp tiện ích như `AtomicInteger`, đồng thời tránh phải tự dùng các cơ chế nội bộ như `sun.misc.Unsafe`.

## 1. VarHandle là gì?

`VarHandle` là một tham chiếu có kiểu tới một biến. Biến được truy cập có thể là:

- Field không static của một đối tượng.
- Field static của một lớp.
- Phần tử trong array.
- Một số dạng biến được hỗ trợ bởi các API nền tảng khác.

Một handle không phải là bản sao của giá trị. Nó đại diện cho vị trí lưu trữ và cho phép thao tác trực tiếp trên biến đó.

Ví dụ:

~~~java
VarHandle valueHandle =
    MethodHandles.lookup().findVarHandle(
        Counter.class, "value", int.class
    );
~~~

Handle trên đại diện cho field `value` kiểu `int` của một đối tượng `Counter`. Có thể dùng cùng handle với nhiều instance của lớp đó; mỗi lần truy cập truyền instance cần thao tác làm tọa độ.

VarHandle là immutable và thread-safe, nên có thể lưu trong field static final và dùng chung giữa nhiều thread. Tính thread-safe của handle không tự làm mọi dữ liệu được truy cập trở nên thread-safe; ứng dụng vẫn phải chọn access mode và thiết kế đồng bộ phù hợp.

## 2. Tạo VarHandle bằng MethodHandles.Lookup

VarHandle thường được tạo qua `MethodHandles.Lookup`. Lookup kiểm tra quyền truy cập tại thời điểm tạo handle theo lớp gọi và quy tắc truy cập của Java.

### Field instance: findVarHandle

~~~java
VarHandle field = MethodHandles.lookup().findVarHandle(
    Counter.class,
    "value",
    int.class
);
~~~

Tham số gồm:

1. Lớp khai báo field.
2. Tên field.
3. Kiểu chính xác của field dưới dạng `Class`.

Handle cho field instance cần một tọa độ receiver khi truy cập. Ví dụ, nếu field thuộc `Counter`, lời gọi sẽ có dạng `field.get(counter)` hoặc `field.set(counter, 10)`.

Nếu tên field không tồn tại hoặc kiểu khai báo không khớp, quá trình tạo handle thất bại với `NoSuchFieldException`. Nếu Lookup không có quyền truy cập, có thể nhận `IllegalAccessException`.

### Field static: findStaticVarHandle

~~~java
VarHandle total = MethodHandles.lookup().findStaticVarHandle(
    Counter.class,
    "total",
    int.class
);
~~~

Field static không cần receiver. Vì vậy, các access mode của handle này không có tọa độ đối tượng:

~~~java
total.set(10);
int current = (int) total.get();
~~~

### Truy cập field private

Nếu lớp gọi không có quyền truy cập trực tiếp vào field private, Java 9 cung cấp `MethodHandles.privateLookupIn`:

~~~java
MethodHandles.Lookup privateLookup =
    MethodHandles.privateLookupIn(
        Account.class,
        MethodHandles.lookup()
    );

VarHandle balance = privateLookup.findVarHandle(
    Account.class,
    "balance",
    long.class
);
~~~

`privateLookupIn` tạo Lookup có quyền private đối với lớp đích nếu thỏa điều kiện truy cập module. Module của bên gọi phải đọc module đích và package chứa lớp đích phải được mở cho module bên gọi. Nếu package không được mở, thao tác có thể thất bại với `IllegalAccessException`.

Trong ứng dụng modular, có thể khai báo `opens` cho package cần truy cập hoặc thiết kế API công khai để tránh mở quyền truy cập private rộng hơn mức cần thiết. Không nên xem `privateLookupIn` là cách bỏ qua mọi ranh giới module.

## 3. Truy cập phần tử array

Dùng `MethodHandles.arrayElementVarHandle(arrayClass)` để tạo handle cho phần tử của array:

~~~java
VarHandle element =
    MethodHandles.arrayElementVarHandle(int[].class);
~~~

Đối với `int[]`, handle có hai tọa độ:

1. Array cần truy cập.
2. Index của phần tử.

~~~java
int[] values = {10, 20, 30};

element.set(values, 1, 99);
int second = (int) element.get(values, 1);

System.out.println(second); // 99
~~~

Cách này cũng áp dụng cho reference array:

~~~java
VarHandle names =
    MethodHandles.arrayElementVarHandle(String[].class);

String[] data = {"Java", "Flow"};
names.set(data, 0, "VarHandle");
String first = (String) names.get(data, 0);
~~~

Kiểu phần tử của array là kiểu biến mà handle truy cập. Array phải khác null và index phải nằm trong giới hạn hợp lệ. Index không hợp lệ gây lỗi truy cập mảng; kiểu array không phải array class sẽ khiến `arrayElementVarHandle` ném `IllegalArgumentException`.

VarHandle của array không thay đổi kích thước array và không tạo array mới. Nó chỉ truy cập một phần tử đã tồn tại.

## 4. Kiểu biến và tọa độ truy cập

Hai phương thức giúp kiểm tra cấu trúc của handle:

~~~java
Class<?> variableType = handle.varType();
List<Class<?>> coordinates = handle.coordinateTypes();
~~~

- `varType()` trả về kiểu của biến được truy cập.
- `coordinateTypes()` trả về các kiểu tọa độ cần truyền vào access mode.

Số tọa độ thường gặp:

| Loại handle | Tọa độ |
|---|---|
| Field instance | Receiver object |
| Field static | Không có |
| Array element | Array và index kiểu int |

Ví dụ, handle tới field `int value` của `Counter` có kiểu biến là `int` và một tọa độ `Counter`. Handle tới `int[]` có kiểu biến là `int` và hai tọa độ là `int[]`, `int`.

Có thể xem kiểu lời gọi của một access mode bằng:

~~~java
MethodType getType =
    handle.accessModeType(VarHandle.AccessMode.GET);
~~~

Thông tin này hữu ích khi xây dựng thư viện tổng quát, kiểm tra handle lúc khởi tạo hoặc chuyển access mode thành MethodHandle.

## 5. Các access mode đọc và ghi

VarHandle cung cấp nhiều access mode. Chọn mode dựa trên ngữ nghĩa bộ nhớ cần thiết, không chỉ dựa vào tên phương thức.

| Access mode | Phương thức | Ngữ nghĩa |
|---|---|---|
| Plain read | `get` | Đọc thông thường |
| Plain write | `set` | Ghi thông thường |
| Opaque read | `getOpaque` | Bảo đảm tính nhất quán thứ tự truy cập trên cùng biến |
| Opaque write | `setOpaque` | Ghi với ngữ nghĩa opaque |
| Acquire read | `getAcquire` | Đọc có acquire ordering |
| Release write | `setRelease` | Ghi có release ordering |
| Volatile read | `getVolatile` | Ngữ nghĩa đọc volatile |
| Volatile write | `setVolatile` | Ngữ nghĩa ghi volatile |

### Plain

~~~java
handle.set(receiver, 10);
int value = (int) handle.get(receiver);
~~~

Plain mode tương ứng truy cập biến thông thường, không thêm memory ordering mạnh như volatile hoặc acquire/release. Dùng khi ứng dụng đã có cơ chế đồng bộ khác hoặc không cần ordering liên thread.

### Opaque

~~~java
handle.setOpaque(receiver, 10);
int value = (int) handle.getOpaque(receiver);
~~~

Opaque bảo đảm tính nhất quán về thứ tự truy cập đối với cùng biến, nhưng không cung cấp ordering liên biến như acquire/release. Đây là mức ordering yếu hơn volatile.

### Acquire và release

~~~java
handle.setRelease(receiver, 10);
int value = (int) handle.getAcquire(receiver);
~~~

Release bảo đảm các thao tác bộ nhớ trước lần ghi được công bố theo thứ tự phù hợp; acquire bảo đảm các thao tác sau lần đọc không bị đưa lên trước lần đọc đó. Khi acquire đọc được giá trị được ghi bởi release tương ứng, dữ liệu được ghi trước release có thể được nhìn thấy sau acquire.

Một ví dụ công bố dữ liệu:

~~~java
final class Message {
    int payload;
    int ready;
}

VarHandle READY = MethodHandles.lookup().findVarHandle(
    Message.class, "ready", int.class
);

// Thread producer
message.payload = 42;
READY.setRelease(message, 1);

// Thread consumer
if ((int) READY.getAcquire(message) == 1) {
    System.out.println(message.payload); // nhìn thấy 42
}
~~~

Đoạn mã là minh họa cho quan hệ release/acquire; hai thread phải chia sẻ cùng đối tượng Message và consumer chỉ đọc payload sau khi acquire quan sát trạng thái đã công bố.

### Volatile

~~~java
handle.setVolatile(receiver, 10);
int value = (int) handle.getVolatile(receiver);
~~~

Volatile read/write có ngữ nghĩa tương ứng với thao tác đọc/ghi volatile trong Java Memory Model. Đây là lựa chọn khi cần thứ tự và khả năng hiển thị liên thread mạnh hơn plain hoặc opaque.

Các mode trên không yêu cầu field phải được khai báo bằng từ khóa `volatile`. VarHandle xác định ngữ nghĩa của từng lần truy cập. Tuy nhiên, mọi thread truy cập cùng biến phải phối hợp bằng một chiến lược nhất quán; trộn plain và volatile tùy tiện có thể làm logic khó hiểu.

## 6. Cập nhật nguyên tử: compare-and-set và get-and-add

Ngoài đọc/ghi, VarHandle cung cấp các thao tác read-modify-write nguyên tử.

### compareAndSet

~~~java
boolean changed = handle.compareAndSet(
    receiver,
    expectedValue,
    newValue
);
~~~

Thao tác so sánh giá trị hiện tại với expectedValue và chỉ ghi newValue nếu giá trị hiện tại khớp. Toàn bộ kiểm tra và cập nhật là một thao tác nguyên tử:

- Trả true nếu cập nhật thành công.
- Trả false nếu giá trị hiện tại không còn bằng expectedValue.

Ví dụ:

~~~java
int value = (int) handle.get(receiver);
boolean updated = handle.compareAndSet(receiver, value, value + 1);
~~~

Không nên tách thao tác đọc và ghi thành hai bước khi cần cập nhật nguyên tử. Hai thread có thể đọc cùng giá trị rồi cùng ghi kết quả, làm mất một lần cập nhật. CAS kết hợp kiểm tra và thay đổi trong một thao tác.

### compareAndExchange

`compareAndExchange` cũng so sánh và cập nhật nguyên tử, nhưng trả về giá trị quan sát được tại thời điểm thao tác:

~~~java
int witness = (int) handle.compareAndExchange(
    receiver,
    expectedValue,
    newValue
);
~~~

Nếu witness bằng expectedValue, cập nhật đã thành công. Nếu khác, giá trị trả về cho biết giá trị hiện tại mà thao tác quan sát được. Các biến thể `compareAndExchangeAcquire` và `compareAndExchangeRelease` cung cấp memory ordering tương ứng.

### getAndAdd

~~~java
int previous = (int) handle.getAndAdd(receiver, 1);
~~~

`getAndAdd` cộng một giá trị vào biến một cách nguyên tử và trả về giá trị trước khi cập nhật. Các thao tác tương tự gồm `getAndSet`, `getAndBitwiseOr`, `getAndBitwiseAnd` và `getAndBitwiseXor`, cùng các biến thể ordering được API hỗ trợ.

Các thao tác nguyên tử chỉ bảo đảm tính nguyên tử đối với biến được truy cập. Chúng không tự tạo transaction trên nhiều field. Nếu invariant nghiệp vụ phụ thuộc nhiều biến cùng thay đổi, hãy dùng lock hoặc một cấu trúc dữ liệu nguyên tử phù hợp.

## 7. Weak compare-and-set và vòng lặp cập nhật

VarHandle có các access mode weak compare-and-set như `weakCompareAndSetPlain`, `weakCompareAndSetAcquire` và `weakCompareAndSetRelease`.

Weak CAS có thể thất bại giả (spurious failure), kể cả khi giá trị hiện tại vẫn bằng expected value. Vì vậy, nếu thuật toán cần thử cho tới khi cập nhật thành công, phải dùng vòng lặp:

~~~java
int current;
do {
    current = (int) handle.getVolatile(receiver);
} while (!handle.weakCompareAndSet(receiver, current, current + 1));
~~~

Khi không cần tối ưu đặc biệt và muốn logic đơn giản, `compareAndSet` thường dễ sử dụng hơn vì không có spurious failure theo hợp đồng strong CAS.

Không nên dùng weak CAS một lần rồi xem false chắc chắn có nghĩa một thread khác đã thay đổi giá trị. Kết quả false có thể do thất bại giả.

## 8. Kiểm tra access mode có được hỗ trợ không

Không phải mọi VarHandle đều hỗ trợ mọi access mode. Khả năng hỗ trợ phụ thuộc kiểu biến và cách handle được tạo.

~~~java
boolean supportsAdd = handle.isAccessModeSupported(
    VarHandle.AccessMode.GET_AND_ADD
);
~~~

Nếu gọi access mode không được hỗ trợ, thao tác ném `UnsupportedOperationException`.

Ví dụ, get/set thông thường có thể được hỗ trợ trong khi một thao tác cập nhật nguyên tử cụ thể không được hỗ trợ cho kiểu biến đó. Với field final, handle chỉ hỗ trợ các mode đọc; các mode ghi và cập nhật không được hỗ trợ.

Khi viết thư viện tổng quát, hãy kiểm tra `isAccessModeSupported` trước khi chọn chiến lược. Không nên giả định mọi handle đều có thể dùng CAS hoặc getAndAdd.

## 9. Signature-polymorphic và kiểm tra kiểu

Các phương thức truy cập như `get`, `set`, `compareAndSet` là signature-polymorphic. Dù khai báo Java hiển thị dạng varargs, compiler tạo kiểu lời gọi theo kiểu thực tế tại call site.

Ví dụ với field kiểu int:

~~~java
int value = (int) handle.get(receiver);
handle.set(receiver, 20);
boolean changed = handle.compareAndSet(receiver, 20, 21);
~~~

Kiểu receiver, index và giá trị phải phù hợp với kiểu mà handle yêu cầu. Gọi sai kiểu có thể gây `WrongMethodTypeException` hoặc `ClassCastException`. Với primitive, nên dùng đúng primitive type; không truyền nhầm wrapper hoặc kiểu số khác rồi trông chờ tự chuyển đổi.

Các access mode cũng có thể được chuyển thành MethodHandle:

~~~java
MethodHandle getter =
    handle.toMethodHandle(VarHandle.AccessMode.GET);
~~~

Điều này hữu ích khi tích hợp với API dựa trên MethodHandle hoặc xây dựng pipeline thao tác động. Với mã ứng dụng thông thường, gọi trực tiếp access mode thường dễ đọc hơn.

## 10. Quyền truy cập, final field và lỗi thường gặp

### Quyền truy cập được kiểm tra khi tạo handle

Lookup phải có quyền truy cập field hoặc array. Không thể dùng một Lookup thông thường để truy cập private field tùy ý ở module khác nếu package không được mở theo quy tắc module.

Hãy tạo handle tại nơi có quyền phù hợp rồi chia sẻ handle nếu thiết kế ứng dụng cho phép. Không mở package toàn cục chỉ để né lỗi truy cập.

### Final field

Field final không thể được thay đổi bằng các write/update access mode thông thường của VarHandle. Handle có thể cung cấp các mode đọc phù hợp, còn mode ghi không được hỗ trợ.

Nếu cần trạng thái thay đổi, hãy dùng field có thể thay đổi được và thiết kế đồng bộ rõ ràng; không cố ghi vào final field bằng reflection hoặc cơ chế nội bộ.

### Các lỗi phổ biến

- **Nhầm VarHandle là giá trị của field:** handle đại diện cho vị trí truy cập, không lưu bản sao giá trị.
- **Bỏ qua receiver của field instance:** instance field cần truyền đúng đối tượng làm tọa độ.
- **Truyền receiver cho static field:** static field không có tọa độ receiver.
- **Nhầm array handle chỉ cần index:** phải truyền cả array và index.
- **Truyền sai kiểu field:** kiểu Class lúc tạo handle phải khớp chính xác kiểu field.
- **Dùng plain mode khi cần ordering liên thread:** plain get/set không thay thế volatile hoặc acquire/release.
- **Cho rằng CAS cập nhật nhiều field cùng lúc:** CAS chỉ nguyên tử trên biến mục tiêu của handle.
- **Dùng weak CAS như strong CAS:** weak CAS có thể thất bại giả và thường cần vòng lặp retry.
- **Giả định mọi access mode đều được hỗ trợ:** kiểm tra `isAccessModeSupported` khi kiểu biến có thể thay đổi.
- **Cố ghi field final:** các mode ghi/cập nhật không được hỗ trợ cho final field.
- **Bỏ qua quyền module:** privateLookupIn cần quyền đọc module và package mở thích hợp.
- **Trộn nhiều memory mode tùy tiện:** chọn một hợp đồng đồng bộ rõ ràng cho mọi thread truy cập biến.

## 11. Ví dụ Java chạy được

Ví dụ sau tạo VarHandle cho field instance, field static và phần tử `int[]`. Chương trình dùng plain access, release/acquire, CAS và get-and-add để minh họa các kiểu thao tác.

~~~java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;

public class VarHandleExample {
    public static final class Counter {
        public int value;
        public static int total;
    }

    private static final VarHandle VALUE;
    private static final VarHandle TOTAL;
    private static final VarHandle ELEMENT;

    static {
        try {
            MethodHandles.Lookup lookup = MethodHandles.lookup();
            VALUE = lookup.findVarHandle(
                Counter.class, "value", int.class
            );
            TOTAL = lookup.findStaticVarHandle(
                Counter.class, "total", int.class
            );
            ELEMENT = MethodHandles.arrayElementVarHandle(int[].class);
        } catch (ReflectiveOperationException ex) {
            throw new ExceptionInInitializerError(ex);
        }
    }

    public static void main(String[] args) {
        Counter counter = new Counter();

        VALUE.set(counter, 10);
        System.out.println("field get=" + (int) VALUE.get(counter));

        VALUE.setRelease(counter, 12);
        System.out.println("field acquire="
            + (int) VALUE.getAcquire(counter));

        System.out.println("field cas="
            + VALUE.compareAndSet(counter, 12, 13));
        System.out.println("field after cas=" + (int) VALUE.get(counter));

        System.out.println("field add previous="
            + (int) VALUE.getAndAdd(counter, 2));
        System.out.println("field after add=" + (int) VALUE.get(counter));

        TOTAL.set(7);
        System.out.println("static get=" + (int) TOTAL.get());

        int[] values = {4, 5, 6};
        ELEMENT.set(values, 1, 50);
        System.out.println("array get=" + (int) ELEMENT.get(values, 1));

        System.out.println("array cas="
            + ELEMENT.compareAndSet(values, 1, 50, 51));
        System.out.println("array after cas=" + values[1]);

        System.out.println("field coordinate count="
            + VALUE.coordinateTypes().size());
        System.out.println("static coordinate count="
            + TOTAL.coordinateTypes().size());
        System.out.println("array coordinate count="
            + ELEMENT.coordinateTypes().size());
        System.out.println("array varType="
            + ELEMENT.varType().getSimpleName());
        System.out.println("getAndAdd supported="
            + VALUE.isAccessModeSupported(VarHandle.AccessMode.GET_AND_ADD));
    }
}
~~~

Lưu trong tệp `VarHandleExample.java`, biên dịch và chạy với Java 9 trở lên:

~~~shell
javac --release 9 -Xlint:all VarHandleExample.java
java VarHandleExample
~~~

Kết quả stdout chính xác:

~~~text
field get=10
field acquire=12
field cas=true
field after cas=13
field add previous=13
field after add=15
static get=7
array get=50
array cas=true
array after cas=51
field coordinate count=1
static coordinate count=0
array coordinate count=2
array varType=int
getAndAdd supported=true
~~~

Giải thích:

1. `VALUE` truy cập field instance `Counter.value`; mọi thao tác truyền đối tượng `counter` làm receiver.
2. `setRelease` và `getAcquire` minh họa hai access mode có ordering.
3. `compareAndSet` chỉ cập nhật từ 12 sang 13 nếu giá trị hiện tại vẫn là 12.
4. `getAndAdd` cộng 2 nguyên tử và trả về giá trị trước khi cộng là 13.
5. `TOTAL` truy cập field static, vì vậy không truyền receiver.
6. `ELEMENT` truy cập phần tử thứ hai của array bằng hai tọa độ: array và index.
7. `coordinateTypes` cho biết số tọa độ khác nhau giữa instance field, static field và array element.

## 12. Tài liệu tham khảo chính thức

- [VarHandle — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/invoke/VarHandle.html): access mode, kiểu biến, tọa độ, memory ordering và thao tác nguyên tử.
- [MethodHandles — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/invoke/MethodHandles.html): tạo array element handle và các tiện ích Lookup.
- [MethodHandles.Lookup — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): findVarHandle, findStaticVarHandle và privateLookupIn.
- [JEP 193: Variable Handles](https://openjdk.org/jeps/193): mục tiêu thiết kế và các access mode được giới thiệu trong Java 9.