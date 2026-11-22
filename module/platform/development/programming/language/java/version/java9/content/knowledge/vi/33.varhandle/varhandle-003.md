# Kiểu biến, kiểu tọa độ và chữ ký của chế độ truy cập trong VarHandle

## 1. Mô hình kiểu của VarHandle

`VarHandle` là một tham chiếu có kiểu mạnh đến một biến, hoặc một họ biến được xác định bằng tọa độ. API này được bổ sung trong Java 9 và thuộc gói `java.lang.invoke`.

Một VarHandle mô tả hai phần kiểu:

- **Variable type (kiểu biến) `T`**: kiểu của giá trị được đọc hoặc ghi, ví dụ `int`, `long`, `String`.
- **Coordinate types (kiểu tọa độ) `CT1, CT2, ...`**: các kiểu đối số dùng để xác định chính xác biến nào được truy cập, ví dụ receiver của một instance field hoặc mảng và chỉ số phần tử.

Một VarHandle không phải là biến và cũng không phải wrapper chứa giá trị. Nó là một capability để truy cập biến theo các chế độ được hỗ trợ. Đối tượng VarHandle là immutable; thông tin kiểu có thể truy vấn bằng `varType()` và `coordinateTypes()`.

Ví dụ: một VarHandle truy cập trường `int value` của một đối tượng `Counter` có kiểu biến là `int`, kiểu tọa độ là `Counter`.

## 2. Variable type: kiểu của giá trị được truy cập

Phương thức:

~~~java
Class<?> type = handle.varType();
~~~

trả về lớp biểu diễn kiểu của biến mà handle tham chiếu.

Một số ví dụ:

| Biến được truy cập | Variable type |
|---|---|
| `int Counter.value` | `int.class` |
| `String Counter.name` | `String.class` |
| `long[]` element | `long.class` |
| `int` view trên ByteBuffer | `int.class` |

`VarHandle` không khai báo generic type như `VarHandle<T>`. Kiểu biến được giữ dưới dạng `Class<?>` và được kết hợp với kiểu tọa độ để tạo chữ ký cho từng access mode.

## 3. Coordinate types: xác định biến nào được truy cập

Danh sách tọa độ được lấy bằng:

~~~java
List<Class<?>> coordinates = handle.coordinateTypes();
~~~

Danh sách trả về không thể sửa đổi. Số lượng tọa độ phụ thuộc vào loại biến và factory đã tạo VarHandle.

| Loại biến | Coordinate types | Ví dụ truy cập |
|---|---|---|
| Instance field của `Counter` | `[Counter]` | `handle.get(counter)` |
| Static field | `[]` | `handle.get()` |
| Phần tử của `int[]` | `[int[], int]` | `handle.get(values, index)` |
| View `int` trên ByteBuffer | `[ByteBuffer, int]` | `handle.get(buffer, byteOffset)` |
| View trên byte array | `[byte[], int]` | `handle.get(bytes, byteOffset)` |

### Instance field

Một trường không static cần receiver để xác định object:

~~~java
VarHandle valueHandle = MethodHandles.lookup()
        .findVarHandle(Counter.class, "value", int.class);

int value = (int) valueHandle.get(counter);
valueHandle.set(counter, 10);
~~~

Kiểu tọa độ là `Counter`; kiểu biến là `int`.

### Static field

Trường static không cần receiver. Vì vậy danh sách tọa độ rỗng:

~~~java
VarHandle totalHandle = MethodHandles.lookup()
        .findStaticVarHandle(Counter.class, "total", int.class);

int total = (int) totalHandle.get();
totalHandle.set(42);
~~~

### Array element

Một phần tử mảng cần cả tham chiếu mảng và chỉ số nguyên:

~~~java
VarHandle elementHandle =
        MethodHandles.arrayElementVarHandle(int[].class);

int value = (int) elementHandle.get(values, 2);
elementHandle.set(values, 2, 99);
~~~

Kiểu tọa độ lần lượt là `int[]` và `int`; kiểu biến là `int`.

### ByteBuffer view

Các factory `byteBufferViewVarHandle` tạo handle để truy cập dữ liệu primitive thông qua một vùng byte của ByteBuffer. Kiểu tọa độ là ByteBuffer và offset dạng int; offset được tính theo byte. Byte order truyền vào factory quyết định thứ tự byte khi diễn giải dữ liệu.

~~~java
VarHandle ints = MethodHandles.byteBufferViewVarHandle(
        int[].class, ByteOrder.nativeOrder());

int value = (int) ints.get(buffer, byteOffset);
~~~

Không nhầm offset byte của view với chỉ số phần tử của `int[]`. Factory cụ thể quy định cách diễn giải tọa độ và các điều kiện truy cập như giới hạn, alignment.

## 4. Access mode type: chữ ký của từng thao tác

Một VarHandle có nhiều access mode. Mỗi access mode tương ứng với một phương thức signature-polymorphic, chẳng hạn:

- Đọc: `get`, `getVolatile`, `getAcquire`, `getOpaque`.
- Ghi: `set`, `setVolatile`, `setRelease`, `setOpaque`.
- Cập nhật nguyên tử: `compareAndSet`, `compareAndExchange`, `getAndSet`.
- Cập nhật số học: `getAndAdd`.
- Cập nhật bit: `getAndBitwiseOr`, `getAndBitwiseAnd`, `getAndBitwiseXor`.

Chữ ký của access mode bắt đầu bằng toàn bộ coordinate types, sau đó là các tham số riêng của thao tác.

Ký hiệu:

- `CT1, ..., CTn`: các tọa độ.
- `T`: variable type.
- `expected`: giá trị mong đợi.
- `newValue`: giá trị mới.

| Access mode | Dạng chữ ký khái quát | Giá trị trả về |
|---|---|---|
| `get` | `(CT1, ..., CTn) -> T` | Giá trị biến |
| `set` | `(CT1, ..., CTn, T) -> void` | Không có |
| `compareAndSet` | `(CT1, ..., CTn, T expected, T newValue) -> boolean` | Có cập nhật thành công hay không |
| `compareAndExchange` | `(CT1, ..., CTn, T expected, T newValue) -> T` | Giá trị witness quan sát được |
| `getAndSet` | `(CT1, ..., CTn, T newValue) -> T` | Giá trị trước khi cập nhật |
| `getAndAdd` | `(CT1, ..., CTn, T delta) -> T` | Giá trị trước khi cộng |
| `getAndBitwiseOr` | `(CT1, ..., CTn, T mask) -> T` | Giá trị trước khi OR |

Ví dụ với instance field `int Counter.value`:

~~~text
GET:             (Counter) -> int
SET:             (Counter, int) -> void
COMPARE_AND_SET: (Counter, int, int) -> boolean
GET_AND_ADD:     (Counter, int) -> int
~~~

Với static field `int Counter.total`, không có coordinate:

~~~text
GET:             () -> int
SET:             (int) -> void
COMPARE_AND_SET: (int, int) -> boolean
~~~

Với phần tử `int[]`:

~~~text
GET:             (int[], int) -> int
SET:             (int[], int, int) -> void
COMPARE_AND_SET: (int[], int, int, int) -> boolean
~~~

## 5. Signature-polymorphic có ý nghĩa gì?

Các access mode như `get`, `set`, `compareAndSet` được gọi trực tiếp trên VarHandle, nhưng chúng không hoạt động như một overload Java thông thường.

Ở mức mã nguồn, lời gọi có thể trông như sau:

~~~java
int value = (int) handle.get(receiver);
boolean updated = handle.compareAndSet(receiver, 10, 11);
~~~

Compiler ghi nhận kiểu đối số và kiểu kết quả tại call site. JVM đối chiếu kiểu đó với access mode type của VarHandle cụ thể đang được gọi.

Ví dụ, nếu handle có:

~~~text
coordinateTypes = [Counter]
varType = int
~~~

thì `get` có chữ ký `(Counter) -> int`, còn `compareAndSet` có chữ ký `(Counter, int, int) -> boolean`.

Điều này giải thích vì sao cùng một tên `get` có thể nhận receiver cho instance field, không nhận tọa độ cho static field, hoặc nhận mảng và index cho array element.

### Tra cứu chữ ký lúc chạy

Có thể lấy `MethodType` của một access mode:

~~~java
MethodType getType =
        handle.accessModeType(VarHandle.AccessMode.GET);

MethodType casType =
        handle.accessModeType(VarHandle.AccessMode.COMPARE_AND_SET);
~~~

`MethodType` chứa danh sách kiểu tham số và kiểu trả về. Các coordinate types tạo thành phần đầu của danh sách tham số; phần sau phụ thuộc access mode.

Ví dụ:

~~~java
System.out.println(handle.varType());
System.out.println(handle.coordinateTypes());
System.out.println(handle.accessModeType(VarHandle.AccessMode.GET));
~~~

Cách này hữu ích khi viết thư viện tổng quát, kiểm tra factory hoặc chẩn đoán lỗi kiểu.

## 6. Kiểm tra kiểu và lỗi khi gọi access mode

Khi call-site type không tương thích với access mode type, JVM có thể ném `WrongMethodTypeException`. Khi kiểu tham chiếu được truyền vào không thể ép kiểu phù hợp, có thể gặp `ClassCastException`.

Một số access mode cũng không được hỗ trợ cho mọi variable type. Gọi một mode không được hỗ trợ sẽ ném `UnsupportedOperationException`.

Dùng:

~~~java
boolean supported = handle.isAccessModeSupported(
        VarHandle.AccessMode.GET_AND_ADD);
~~~

để kiểm tra trước khi gọi thao tác tùy chọn.

Ví dụ, một VarHandle tham chiếu trường `String` có thể hỗ trợ `get` và `set`, nhưng không hỗ trợ `getAndAdd`. Ngược lại, handle cho trường `int` có thể hỗ trợ phép cộng nguyên tử.

Với biến chỉ đọc, chẳng hạn final field, các mode ghi và cập nhật nguyên tử không được hỗ trợ. `get` luôn là access mode cơ bản được hỗ trợ.

Việc tạo VarHandle cũng có thể thất bại nếu field không tồn tại hoặc code không có quyền truy cập. `MethodHandles.Lookup` kiểm tra quyền truy cập lúc tạo handle; handle sau đó hoạt động như một capability để truy cập biến tương ứng.

## 7. Các nhóm memory ordering

Access mode không chỉ xác định thao tác mà còn xác định memory ordering:

| Nhóm | Read | Write | Ý nghĩa |
|---|---|---|---|
| Plain | `get` | `set` | Truy cập thông thường, không tạo ordering liên luồng bổ sung |
| Opaque | `getOpaque` | `setOpaque` | Đảm bảo tính nhất quán theo cùng biến, nhưng không thiết lập ordering rộng như acquire/release |
| Acquire / Release | `getAcquire` | `setRelease` | Acquire ngăn các truy cập sau bị đưa lên trước lần đọc; Release ngăn truy cập trước bị đưa xuống sau lần ghi |
| Volatile | `getVolatile` | `setVolatile` | Có thứ tự tổng thể giữa các volatile access theo Java Memory Model |

Các access mode cập nhật nguyên tử như compare-and-set và compare-and-exchange cũng có memory semantics riêng. Hãy chọn mode theo yêu cầu đồng bộ, không chỉ theo tên thao tác.

### Acquire và release

Một producer có thể ghi dữ liệu rồi công bố trạng thái bằng release; consumer đọc trạng thái bằng acquire trước khi đọc dữ liệu liên quan:

~~~java
data = newData;
stateHandle.setRelease(this, READY);

// Consumer:
if ((int) stateHandle.getAcquire(this) == READY) {
    use(data);
}
~~~

Acquire/release tạo quan hệ ordering phù hợp khi được dùng đúng trên cùng giao thức đồng bộ. Chúng không thay thế việc thiết kế ownership và trạng thái chia sẻ một cách rõ ràng.

### Access mode ghi đè semantics tại khai báo

Memory semantics được chọn bởi access mode. Nếu một field được khai báo `volatile` nhưng VarHandle truy cập nó bằng `get` hoặc `set`, thao tác đó dùng semantics plain của access mode được gọi.

Vì vậy, tránh trộn tùy tiện plain, opaque, acquire/release và volatile trên cùng biến. Nếu cần phối hợp nhiều mode, phải xác định rõ quan hệ happens-before và chứng minh giao thức an toàn theo Java Memory Model.

## 8. Ví dụ Java chạy được: kiểu biến, tọa độ và chữ ký

Chương trình dưới đây tạo VarHandle cho instance field, static field, array element và ByteBuffer view. Nó in variable type, coordinate types, MethodType của GET/SET/CAS, sau đó thực hiện một số access mode.

~~~java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.VarHandle;
import java.lang.invoke.WrongMethodTypeException;
import java.nio.ByteOrder;
import java.util.stream.Collectors;

public class VarHandleCoordinatesDemo {
    private static final class Counter {
        int value;
        static int total;
        String text;
    }

    private static void describe(String label, VarHandle handle) {
        String coordinates = handle.coordinateTypes().stream()
                .map(Class::getSimpleName)
                .collect(Collectors.joining(", ", "[", "]"));
        System.out.println(label + " variable type = "
                + handle.varType().getSimpleName());
        System.out.println(label + " coordinate types = " + coordinates);
        System.out.println(label + " GET signature = "
                + signature(handle.accessModeType(VarHandle.AccessMode.GET)));
        System.out.println(label + " SET signature = "
                + signature(handle.accessModeType(VarHandle.AccessMode.SET)));
        System.out.println(label + " CAS signature = "
                + signature(handle.accessModeType(
                        VarHandle.AccessMode.COMPARE_AND_SET)));
    }

    private static String signature(MethodType type) {
        String parameters = type.parameterList().stream()
                .map(Class::getSimpleName)
                .collect(Collectors.joining(", "));
        return "(" + parameters + ") -> " + type.returnType().getSimpleName();
    }

    public static void main(String[] args) throws Exception {
        MethodHandles.Lookup lookup = MethodHandles.lookup();
        VarHandle field = lookup.findVarHandle(
                Counter.class, "value", int.class);
        VarHandle staticField = lookup.findStaticVarHandle(
                Counter.class, "total", int.class);
        VarHandle array = MethodHandles.arrayElementVarHandle(int[].class);
        VarHandle byteBufferView = MethodHandles.byteBufferViewVarHandle(
                int[].class, ByteOrder.nativeOrder());

        describe("instance field", field);
        describe("static field", staticField);
        describe("array element", array);
        describe("ByteBuffer view", byteBufferView);

        Counter counter = new Counter();
        field.set(counter, 10);
        System.out.println("plain get = " + (int) field.get(counter));
        System.out.println("compareAndSet = "
                + field.compareAndSet(counter, 10, 11));
        System.out.println("getAndAdd previous = "
                + (int) field.getAndAdd(counter, 4));
        System.out.println("compareAndExchange witness = "
                + (int) field.compareAndExchange(counter, 15, 20));
        System.out.println("final field value = " + (int) field.get(counter));
        System.out.println("GET_AND_ADD supported = "
                + field.isAccessModeSupported(VarHandle.AccessMode.GET_AND_ADD));

        field.setRelease(counter, 30);
        System.out.println("getAcquire after setRelease = "
                + (int) field.getAcquire(counter));

        staticField.set(42);
        System.out.println("static field value = " + (int) staticField.get());

        int[] values = new int[3];
        array.set(values, 1, 7);
        System.out.println("array getAndAdd previous = "
                + (int) array.getAndAdd(values, 1, 5));
        System.out.println("array element value = " + (int) array.get(values, 1));

        VarHandle textField = lookup.findVarHandle(
                Counter.class, "text", String.class);
        System.out.println("String GET_AND_ADD supported = "
                + textField.isAccessModeSupported(VarHandle.AccessMode.GET_AND_ADD));
        try {
            textField.getAndAdd(counter, "suffix");
        } catch (UnsupportedOperationException ex) {
            System.out.println("unsupported GET_AND_ADD = UnsupportedOperationException");
        }
        try {
            String wrongType = (String) field.get(counter);
            System.out.println("unexpected value = " + wrongType);
        } catch (WrongMethodTypeException ex) {
            System.out.println("wrong call-site type = WrongMethodTypeException");
        }
    }
}
~~~

Lưu mã nguồn trong `VarHandleCoordinatesDemo.java`, biên dịch và chạy bằng Java 9 trở lên:

~~~bash
javac --release 9 -Xlint:all VarHandleCoordinatesDemo.java
java VarHandleCoordinatesDemo
~~~

Kết quả:

~~~text
instance field variable type = int
instance field coordinate types = [Counter]
instance field GET signature = (Counter) -> int
instance field SET signature = (Counter, int) -> void
instance field CAS signature = (Counter, int, int) -> boolean
static field variable type = int
static field coordinate types = []
static field GET signature = () -> int
static field SET signature = (int) -> void
static field CAS signature = (int, int) -> boolean
array element variable type = int
array element coordinate types = [int[], int]
array element GET signature = (int[], int) -> int
array element SET signature = (int[], int, int) -> void
array element CAS signature = (int[], int, int, int) -> boolean
ByteBuffer view variable type = int
ByteBuffer view coordinate types = [ByteBuffer, int]
ByteBuffer view GET signature = (ByteBuffer, int) -> int
ByteBuffer view SET signature = (ByteBuffer, int, int) -> void
ByteBuffer view CAS signature = (ByteBuffer, int, int, int) -> boolean
plain get = 10
compareAndSet = true
getAndAdd previous = 11
compareAndExchange witness = 15
final field value = 20
GET_AND_ADD supported = true
getAcquire after setRelease = 30
static field value = 42
array getAndAdd previous = 7
array element value = 12
String GET_AND_ADD supported = false
unsupported GET_AND_ADD = UnsupportedOperationException
wrong call-site type = WrongMethodTypeException
~~~

Chương trình được kiểm tra với cả `javac --release 9 -Xlint:all` và `javac --release 17 -Xlint:all`; stdout khớp với kết quả trên. `compareAndExchange` trả về witness value 15, còn `getAndAdd` trả giá trị trước khi cộng.

## 9. Lỗi thường gặp

- **Nhầm variable type với coordinate type:** `int` là kiểu giá trị được truy cập; `Counter` là kiểu receiver dùng để tìm instance field.
- **Truyền receiver cho static field:** static field không có coordinate; chữ ký GET là `() -> T`.
- **Quên index của array:** array element cần cả mảng và index; chữ ký GET là `(arrayType, int) -> T`.
- **Nhầm byte offset với array index:** ByteBuffer view dùng offset theo byte, không phải chỉ số phần tử của mảng primitive.
- **Coi access mode là overload thông thường:** các lời gọi signature-polymorphic được kiểm tra dựa trên call-site descriptor và accessModeType.
- **Không kiểm tra access mode support:** kiểu biến hoặc tính chất read-only có thể khiến một thao tác không được hỗ trợ; kiểm tra bằng `isAccessModeSupported`.
- **Nhầm compareAndSet và compareAndExchange:** CAS trả boolean; compare-and-exchange trả witness value.
- **Dùng getAndAdd với kiểu không hỗ trợ:** cập nhật số học chỉ dùng được với các kiểu/factory hỗ trợ mode tương ứng.
- **Nhầm equals với so sánh CAS cho reference:** các phép so sánh nguyên tử trên reference dùng identity semantics, không gọi `equals`.
- **Trộn memory ordering tùy tiện:** access mode quyết định semantics của thao tác; không giả định field khai báo volatile sẽ biến mọi mode thành volatile.

## 10. Checklist khi tạo và sử dụng VarHandle

1. Variable type của biến là gì?
2. Biến là instance field, static field, array element hay view trên buffer?
3. Danh sách coordinate types cần những đối số nào và theo thứ tự nào?
4. Access mode cần gọi có chữ ký `MethodType` nào?
5. Kiểu đối số và kiểu trả về tại call site có tương thích với `accessModeType` không?
6. Mode đó có được hỗ trợ cho kiểu biến và tính chất read-only không?
7. Thao tác cần plain, opaque, acquire/release, volatile hay atomic update semantics?
8. Quyền truy cập của `MethodHandles.Lookup` đã hợp lệ khi tạo handle chưa?
9. Nếu dùng CAS loop hoặc weak CAS, mã đã xử lý thất bại và thử lại đúng cách chưa?

## 11. Tài liệu tham khảo

- [VarHandle — Java SE 9 API](https://docs.oracle.com/javase/9/docs/api/java/lang/invoke/VarHandle.html)
- [MethodHandles — Java SE 9 API](https://docs.oracle.com/javase/9/docs/api/java/lang/invoke/MethodHandles.html)
- [MethodHandles.Lookup — Java SE 9 API](https://docs.oracle.com/javase/9/docs/api/java/lang/invoke/MethodHandles.Lookup.html)
- [VarHandle — Java SE API hiện hành](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/invoke/VarHandle.html)