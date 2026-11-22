# Trường static, trường đối tượng và phần tử mảng với VarHandle trong Java

## Mục tiêu

Java 9 giới thiệu **VarHandle** trong package **java.lang.invoke** để truy cập và cập nhật biến theo một tập access mode có quy tắc kiểu dữ liệu và memory ordering rõ ràng. Một VarHandle có thể đại diện cho trường của đối tượng, trường static hoặc một phần tử mảng.

VarHandle giúp kết hợp thao tác đọc/ghi thông thường với các thao tác nguyên tử như compare-and-set và get-and-add. Nhờ đó, mã có thể làm việc trực tiếp trên trường hoặc phần tử mảng mà không cần bọc mọi giá trị trong một đối tượng Atomic riêng.

Bài này tập trung vào ba loại vị trí theo đề bài: **trường đối tượng**, **trường static** và **phần tử mảng**; cách tạo VarHandle, kiểu tọa độ, access mode, memory ordering, quyền truy cập và cách kiểm tra hỗ trợ trên Java hiện đại.

## 1. VarHandle là gì?

**VarHandle** là một tham chiếu có kiểu tới một biến. Biến đó có thể là:

- Một trường instance thuộc một đối tượng.
- Một trường static thuộc một lớp.
- Một phần tử của mảng.

VarHandle cung cấp các thao tác đọc, ghi và cập nhật nguyên tử với nhiều mức memory ordering. Các thao tác này được gọi là **access mode**.

Ví dụ, cùng một VarHandle có thể cung cấp:

- **get()** và **set()** để đọc và ghi thông thường.
- **getVolatile()** và **setVolatile()** để dùng ngữ nghĩa volatile.
- **compareAndSet()** để cập nhật nếu giá trị hiện tại khớp giá trị mong đợi.
- **getAndAdd()** để cộng nguyên tử và trả về giá trị trước khi cộng.

VarHandle không phải bản sao của giá trị. Nó đại diện cho vị trí lưu trữ; mỗi lần gọi access mode sẽ đọc hoặc cập nhật vị trí đó.

### Khi nào nên dùng?

VarHandle phù hợp khi cần thao tác trên trường hoặc phần tử mảng hiện có với các bảo đảm đồng thời cụ thể. Nếu chỉ cần một bộ đếm độc lập, **AtomicInteger** hoặc **AtomicLong** có thể đơn giản hơn. Nếu cần truy cập trực tiếp nhiều loại vị trí hoặc cần chọn memory ordering, VarHandle cung cấp khả năng linh hoạt hơn.

## 2. Ba cách tạo VarHandle

Các factory method thường dùng nằm trong **MethodHandles**.

### Trường instance: findVarHandle()

Dùng **Lookup.findVarHandle()** để lấy handle tới trường không static:

```java
VarHandle handle = MethodHandles.lookup()
        .findVarHandle(Counter.class, "value", int.class);
```

Tham số gồm:

1. Lớp khai báo trường.
2. Tên trường.
3. Kiểu trường chính xác.

Khi sử dụng, handle cần đối tượng sở hữu trường làm tọa độ đầu tiên:

```java
Counter counter = new Counter();

handle.set(counter, 10);
int current = (int) handle.get(counter);
```

Nếu trường không tồn tại, việc tìm handle có thể ném **NoSuchFieldException**. Nếu Lookup không có quyền truy cập trường, có thể ném **IllegalAccessException**.

### Trường static: findStaticVarHandle()

Dùng **Lookup.findStaticVarHandle()** cho trường static:

```java
VarHandle handle = MethodHandles.lookup()
        .findStaticVarHandle(Counter.class, "total", int.class);

handle.set(20);
int current = (int) handle.get();
```

Trường static thuộc về lớp, không thuộc một instance cụ thể. Vì vậy, các access mode của handle này không nhận đối tượng làm tọa độ.

Không dùng **findVarHandle()** cho trường static hoặc **findStaticVarHandle()** cho trường instance. Hãy chọn factory method đúng với loại trường.

### Phần tử mảng: arrayElementVarHandle()

Dùng **MethodHandles.arrayElementVarHandle()** để lấy handle cho phần tử của một loại mảng:

```java
VarHandle handle = MethodHandles.arrayElementVarHandle(int[].class);

int[] values = {10, 20, 30};
int current = (int) handle.get(values, 1);

handle.set(values, 1, 25);
```

Các tọa độ gồm mảng và chỉ số phần tử. Kiểu mảng truyền vào phải là kiểu mảng thực tế cần truy cập, ví dụ **int[].class**, **long[].class** hoặc **String[].class**.

Chỉ số ngoài phạm vi sẽ gây lỗi truy cập mảng. VarHandle không bỏ qua quy tắc kiểm tra biên của mảng.

## 3. Kiểu tọa độ của từng VarHandle

Một access mode nhận các tọa độ xác định vị trí biến, sau đó mới nhận giá trị cần ghi hoặc giá trị mong đợi/giá trị mới.

| Loại vị trí | Cách tạo | Tọa độ của thao tác đọc | Tọa độ khi ghi |
|---|---|---|---|
| Trường instance | **findVarHandle()** | Đối tượng sở hữu trường | Đối tượng, giá trị mới |
| Trường static | **findStaticVarHandle()** | Không có | Chỉ giá trị mới |
| Phần tử mảng | **arrayElementVarHandle()** | Mảng, chỉ số | Mảng, chỉ số, giá trị mới |

Ví dụ cùng một thao tác **get()** có cách gọi khác nhau:

```java
int instanceValue = (int) INSTANCE_HANDLE.get(counter);
int staticValue = (int) STATIC_HANDLE.get();
int arrayValue = (int) ARRAY_HANDLE.get(values, index);
```

Với **set()**, giá trị cần ghi được đặt sau các tọa độ:

```java
INSTANCE_HANDLE.set(counter, 12);
STATIC_HANDLE.set(40);
ARRAY_HANDLE.set(values, index, 99);
```

Đây là điểm cần chú ý khi đọc lỗi kiểu hoặc số lượng tham số: ba loại handle không có cùng danh sách tọa độ.

Có thể xem thông tin kiểu của handle qua **varType()** và **coordinateTypes()**. Ví dụ, handle cho trường instance có tọa độ là lớp sở hữu; handle static không có tọa độ; handle phần tử mảng có tọa độ mảng và chỉ số int.

## 4. Access mode: đọc, ghi và cập nhật

VarHandle cung cấp nhiều access mode cho cùng một vị trí.

### Đọc và ghi thông thường

Các thao tác cơ bản:

- **get(coordinates...)** đọc giá trị.
- **set(coordinates..., value)** ghi giá trị.

Chúng tương ứng với truy cập plain và không tự tạo một chuỗi thao tác đọc-sửa-ghi nguyên tử. Nếu nhiều thread cùng cập nhật một bộ đếm bằng cách đọc rồi ghi riêng lẻ, cập nhật có thể bị mất.

### Opaque, acquire/release và volatile

Các access mode có mức memory ordering khác nhau:

| Nhóm | Phương thức tiêu biểu | Ý nghĩa chính |
|---|---|---|
| Plain | **get()**, **set()** | Truy cập thông thường, không tạo bảo đảm đồng bộ bổ sung |
| Opaque | **getOpaque()**, **setOpaque()** | Duy trì tính nhất quán truy cập đối với cùng biến với thứ tự yếu hơn volatile |
| Acquire/release | **getAcquire()**, **setRelease()** | Acquire ngăn thao tác sau vượt lên trước; release ngăn thao tác trước bị đẩy xuống sau |
| Volatile | **getVolatile()**, **setVolatile()** | Cung cấp ngữ nghĩa ordering và visibility kiểu volatile |

Acquire/release hữu ích khi công bố dữ liệu: thread ghi hoàn tất các trường dữ liệu rồi thực hiện release trên biến điều phối; thread đọc thấy giá trị đó bằng acquire có thể quan sát các thao tác ghi được công bố trước release.

Không chọn memory ordering chỉ dựa trên tên phương thức. Cần xác định quan hệ đồng bộ mà thuật toán yêu cầu. Nếu không chắc, volatile hoặc một cấu trúc đồng bộ cấp cao hơn thường dễ lý giải hơn.

### Thao tác nguyên tử đọc-sửa-ghi

Một số access mode thực hiện cập nhật nguyên tử:

- **compareAndSet(expected, newValue)** chỉ ghi giá trị mới nếu giá trị hiện tại bằng expected; trả về boolean.
- **compareAndExchange(expected, newValue)** thực hiện trao đổi có điều kiện và trả về giá trị quan sát được.
- **getAndSet(newValue)** thay giá trị và trả về giá trị cũ.
- **getAndAdd(delta)** cộng delta nguyên tử và trả về giá trị cũ.

Với trường instance, các thao tác này nhận đối tượng làm tọa độ; với trường static, không cần đối tượng; với mảng, nhận mảng và chỉ số trước các toán hạng cập nhật.

Ví dụ với một trường instance:

```java
int previous = (int) VALUE_HANDLE.getAndAdd(counter, 5);
boolean changed = VALUE_HANDLE.compareAndSet(counter, 15, 16);
```

**getAndAdd()** hữu ích cho bộ đếm chia sẻ. **compareAndSet()** hữu ích khi thuật toán cần thay đổi giá trị chỉ khi trạng thái vẫn đúng như mong đợi.

## 5. Kiểm tra access mode có được hỗ trợ không

Không phải mọi kiểu biến đều hỗ trợ mọi access mode. Ví dụ, **getAndAdd()** không phù hợp với mọi kiểu tham chiếu.

Dùng **isAccessModeSupported()** trước khi gọi một mode tùy chọn:

```java
if (handle.isAccessModeSupported(VarHandle.AccessMode.GET_AND_ADD)) {
    int previous = (int) handle.getAndAdd(counter, 1);
} else {
    throw new UnsupportedOperationException(
            "GET_AND_ADD is not supported for this variable");
}
```

Nếu gọi access mode không được hỗ trợ, thao tác sẽ ném **UnsupportedOperationException**. Hãy kiểm tra khả năng hỗ trợ khi handle có thể đại diện cho nhiều loại trường hoặc kiểu dữ liệu khác nhau.

VarHandle còn cung cấp **accessModeType(mode)** để xem kiểu phương thức của một access mode. Điều này hữu ích trong các framework hoặc mã tổng quát cần kiểm tra chữ ký thao tác.

## 6. Quyền truy cập và kiểu dữ liệu

VarHandle được tạo qua một **MethodHandles.Lookup**. Lookup quyết định mã gọi có quyền tìm handle cho trường đó hay không.

Ví dụ:

```java
MethodHandles.Lookup lookup = MethodHandles.lookup();

VarHandle handle = lookup.findVarHandle(
        Counter.class,
        "value",
        int.class);
```

Các quy tắc truy cập Java vẫn được áp dụng. Nếu trường private thuộc lớp khác, Lookup hiện tại có thể không đủ quyền. Java 9 có **MethodHandles.privateLookupIn()** để tạo Lookup có quyền riêng tư khi điều kiện truy cập và module cho phép.

Không nên mở quyền truy cập rộng chỉ để tránh lỗi. Hãy giới hạn Lookup ở nơi thực sự cần thao tác và tuân thủ ranh giới module của ứng dụng.

Kiểu trường truyền vào khi tìm handle phải khớp kiểu khai báo thực tế. Các access mode là signature-polymorphic: kiểu tham số và kiểu trả về tại điểm gọi quyết định chữ ký được liên kết. Với trường int, ví dụ đọc thường ép kết quả về int:

```java
int value = (int) handle.get(counter);
```

Dùng sai kiểu tọa độ hoặc kiểu giá trị có thể dẫn tới lỗi kiểu như **WrongMethodTypeException** hoặc **ClassCastException**. Hãy giữ kiểu khai báo nhất quán và truyền đúng số lượng tọa độ.

## 7. Memory ordering và an toàn đồng thời

VarHandle cung cấp các thao tác nguyên tử trên một vị trí biến. Tuy nhiên, điều đó không có nghĩa mọi chuỗi thao tác trên nhiều biến tự động trở thành một giao dịch nguyên tử.

Ví dụ, **getAndAdd()** bảo đảm phép cộng trên chính biến được xử lý nguyên tử. Nếu thuật toán cần cập nhật hai trường với nhau như một trạng thái không thể tách rời, chỉ dùng hai VarHandle riêng lẻ không bảo đảm cả cặp thay đổi cùng lúc.

Cũng cần phân biệt:

- **Atomicity**: một thao tác cập nhật cụ thể không bị quan sát ở trạng thái dở dang.
- **Visibility**: thread khác có thể quan sát dữ liệu được công bố.
- **Ordering**: thứ tự các thao tác đọc/ghi được bảo đảm giữa các thread.

Chọn access mode phù hợp với cả ba yêu cầu. Khi cần phối hợp phức tạp, hãy cân nhắc synchronized, Lock, AtomicReference hoặc các cấu trúc đồng bộ cấp cao hơn thay vì tự xây dựng giao thức memory ordering khó kiểm chứng.

VarHandle không làm object mà nó tham chiếu trở nên immutable hoặc thread-safe ở mọi khía cạnh. Nếu một trường chứa tham chiếu tới List mutable, cập nhật tham chiếu nguyên tử không tự bảo vệ các thao tác sửa List đó.

## 8. Ví dụ Java hoàn chỉnh: trường instance, static và mảng

Ví dụ sau tạo ba VarHandle:

- **VALUE** cho trường instance của Box.
- **TOTAL** cho trường static của Box.
- **ELEMENT** cho phần tử của mảng int.

Chương trình minh họa đọc/ghi, get-and-add và compare-and-set.

Tạo tệp **VarHandleStaticInstanceArrayDemo.java**:

```java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;

public class VarHandleStaticInstanceArrayDemo {
    static final class Box {
        int value;
        static int total;
    }

    private static final VarHandle VALUE;
    private static final VarHandle TOTAL;
    private static final VarHandle ELEMENT;

    static {
        try {
            MethodHandles.Lookup lookup = MethodHandles.lookup();
            VALUE = lookup.findVarHandle(Box.class, "value", int.class);
            TOTAL = lookup.findStaticVarHandle(Box.class, "total", int.class);
            ELEMENT = MethodHandles.arrayElementVarHandle(int[].class);
        } catch (ReflectiveOperationException exception) {
            throw new ExceptionInInitializerError(exception);
        }
    }

    public static void main(String[] args) {
        Box box = new Box();
        VALUE.set(box, 10);
        int previousValue = (int) VALUE.getAndAdd(box, 5);

        TOTAL.set(20);
        int previousTotal = (int) TOTAL.getAndAdd(1);

        int[] numbers = {1, 2, 3};
        ELEMENT.set(numbers, 1, 7);
        int previousElement = (int) ELEMENT.getAndAdd(numbers, 1, 3);

        boolean swapped = VALUE.compareAndSet(box, 15, 16);

        System.out.println("instance previous: " + previousValue);
        System.out.println("instance current: " + VALUE.get(box));
        System.out.println("static previous: " + previousTotal);
        System.out.println("static current: " + TOTAL.get());
        System.out.println("array previous: " + previousElement);
        System.out.println("array current: " + ELEMENT.get(numbers, 1));
        System.out.println("compare and set: " + swapped);
        System.out.println("instance after CAS: " + VALUE.get(box));
        System.out.println("getAndAdd supported: "
                + VALUE.isAccessModeSupported(VarHandle.AccessMode.GET_AND_ADD));
    }
}
```

Biên dịch và chạy trên Java 17+:

```bash
javac --release 17 VarHandleStaticInstanceArrayDemo.java
java VarHandleStaticInstanceArrayDemo
```

Stdout chính xác:

```text
instance previous: 10
instance current: 16
static previous: 20
static current: 21
array previous: 7
array current: 10
compare and set: true
instance after CAS: 16
getAndAdd supported: true
```

Trong ví dụ, trường instance được truy cập với đối tượng Box, trường static được truy cập không cần đối tượng, còn phần tử mảng được truy cập bằng mảng và chỉ số. Phép compare-and-set thành công vì giá trị instance sau get-and-add đang là 15.

Ví dụ chạy tuần tự để kết quả dễ đọc. Các access mode nguyên tử vẫn có thể được dùng khi nhiều thread cùng cập nhật biến, nhưng cần kiểm tra toàn bộ thuật toán và memory ordering trong tình huống đồng thời thực tế.

## 9. So sánh VarHandle với reflection và AtomicInteger

| Công cụ | Mục đích chính | Đặc điểm |
|---|---|---|
| Reflection Field | Đọc/ghi trường dựa trên metadata | API phản chiếu; không cung cấp đầy đủ bộ access mode nguyên tử và ordering như VarHandle |
| AtomicInteger | Quản lý một giá trị int nguyên tử độc lập | Đơn giản cho bộ đếm hoặc trạng thái int riêng |
| VarHandle | Truy cập trường hoặc phần tử mảng theo kiểu | Có plain, opaque, acquire/release, volatile và atomic update modes |

Dùng Reflection khi cần khám phá metadata hoặc thao tác tổng quát dựa trên tên trường. Dùng AtomicInteger khi cần một biến nguyên tử độc lập. Dùng VarHandle khi muốn áp dụng access mode có kiểm soát trực tiếp lên trường hoặc phần tử mảng.

## 10. Lỗi thường gặp

1. **Dùng findVarHandle cho trường static**: dùng findStaticVarHandle cho trường static và findVarHandle cho trường instance.
2. **Truyền thừa đối tượng vào static handle**: static handle không có tọa độ receiver.
3. **Quên tọa độ mảng hoặc chỉ số**: array element handle cần mảng và index trước giá trị.
4. **Truyền sai kiểu trường**: kiểu Class truyền khi tạo handle phải khớp kiểu khai báo của trường.
5. **Cho rằng get rồi set là một phép nguyên tử**: hai thao tác riêng có thể bị thread khác xen vào. Dùng compareAndSet hoặc getAndAdd khi phù hợp.
6. **Giả định mọi access mode đều hỗ trợ mọi kiểu**: kiểm tra isAccessModeSupported trước mode tùy chọn.
7. **Chọn memory ordering tùy tiện**: plain, opaque, acquire/release và volatile có bảo đảm khác nhau. Chọn theo quan hệ đồng bộ cần thiết.
8. **Nhầm cập nhật nguyên tử một trường với giao dịch nhiều trường**: VarHandle không tự làm nhiều vị trí cập nhật cùng lúc.
9. **Bỏ qua quyền truy cập Lookup**: tìm handle có thể thất bại do access control hoặc module boundary. Cấp quyền đúng phạm vi.
10. **Cho rằng VarHandle làm object mutable trở nên thread-safe**: handle chỉ điều khiển vị trí biến; object được tham chiếu cần chính sách đồng bộ riêng.

## Kết luận

VarHandle cho phép truy cập trường instance bằng **findVarHandle()**, trường static bằng **findStaticVarHandle()** và phần tử mảng bằng **arrayElementVarHandle()**. Mỗi loại có tọa độ riêng: instance cần receiver, static không cần receiver, còn mảng cần array và index.

Access mode quyết định cách đọc, ghi, đồng bộ bộ nhớ và cập nhật nguyên tử. Hãy chọn đúng factory method, truyền đúng tọa độ và kiểu, kiểm tra mode được hỗ trợ, rồi chọn memory ordering theo yêu cầu đồng thời thực tế.
