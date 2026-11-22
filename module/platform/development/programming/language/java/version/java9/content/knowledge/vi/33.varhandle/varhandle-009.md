# Chế độ truy cập được hỗ trợ theo kiểu và tính chất biến

VarHandle là một tham chiếu có kiểu mạnh đến một biến hoặc một nhóm biến được xác định bằng tọa độ. API này có từ Java 9 và cho phép đọc, ghi, cập nhật nguyên tử với các mức memory ordering khác nhau. Tuy nhiên, **không phải VarHandle nào cũng hỗ trợ mọi access mode**. Tập mode hợp lệ phụ thuộc vào kiểu biến, biến có chỉ đọc hay không, loại vùng nhớ mà handle đại diện và một số điều kiện như alignment.

Trước khi gọi một mode, hãy kiểm tra hợp đồng của factory đã tạo VarHandle và dùng `isAccessModeSupported`. Khi mode không được hỗ trợ, lời gọi tương ứng ném `UnsupportedOperationException`.

## 1. Kiểu biến và kiểu tọa độ

Một VarHandle mô tả hai phần:

- **Variable type**: kiểu của giá trị được đọc hoặc ghi, trả về bởi `varType()`.
- **Coordinate types**: các đối số dùng để xác định biến cụ thể, trả về bởi `coordinateTypes()`.

Ví dụ, với field instance:

~~~java
VarHandle count = MethodHandles.lookup().findVarHandle(
        Counter.class,
        "value",
        int.class
);
~~~

Handle này có variable type là `int` và coordinate type là `Counter`, vì cần một instance để xác định field.

Các factory khác có tọa độ khác:

| Loại biến | Factory thường dùng | Coordinate types |
|---|---|---|
| Field instance | `findVarHandle` | Instance chứa field |
| Field static | `findStaticVarHandle` | Không có tọa độ |
| Phần tử array | `arrayElementVarHandle` | Array và index int |
| View của byte[] | `byteArrayViewVarHandle` | byte[] và byte offset |
| View của ByteBuffer | `byteBufferViewVarHandle` | ByteBuffer và byte offset |

Kiểu tọa độ quyết định cách gọi access mode. Ví dụ, một handle cho array element cần cả array lẫn index; một handle cho field static không cần receiver object.

## 2. Các nhóm access mode

Các mode được chia thành năm nhóm chính:

| Nhóm | Phương thức tiêu biểu | Công dụng |
|---|---|---|
| Read | `get`, `getVolatile`, `getAcquire`, `getOpaque` | Đọc theo memory ordering đã chọn |
| Write | `set`, `setVolatile`, `setRelease`, `setOpaque` | Ghi theo memory ordering đã chọn |
| Atomic update | `compareAndSet`, `compareAndExchange`, `getAndSet` | Cập nhật nguyên tử |
| Numeric atomic update | `getAndAdd` | Cộng nguyên tử vào giá trị hiện tại |
| Bitwise atomic update | `getAndBitwiseOr`, `getAndBitwiseAnd`, `getAndBitwiseXor` | Cập nhật bằng phép toán bit |

Một số nhóm có biến thể Acquire và Release, ví dụ `getAndAddAcquire`, `getAndAddRelease` hoặc `getAndSetAcquire`. Chúng thay đổi memory ordering của thao tác nhưng không làm một mode vốn không được hỗ trợ trở nên hợp lệ.

## 3. Memory ordering của các mode đọc và ghi

Các mode đọc/ghi khác nhau về thứ tự quan sát giữa các thread:

| Mode | Đọc | Ghi | Ý nghĩa |
|---|---|---|---|
| Plain | `get` | `set` | Truy cập thông thường, không tạo ordering giữa các thread |
| Opaque | `getOpaque` | `setOpaque` | Các truy cập cùng biến được quan sát nhất quán, không tạo ordering với biến khác |
| Acquire/Release | `getAcquire` | `setRelease` | Acquire đọc sau các write Release tương ứng; thao tác sau acquire không bị đưa lên trước |
| Volatile | `getVolatile` | `setVolatile` | Ngữ nghĩa volatile và thứ tự toàn phần giữa các volatile operation |

Plain `get` và `set` chỉ bảo đảm bitwise atomic cho reference và primitive có kích thước tối đa 32 bit. Với `long` hoặc `double` trên nền tảng 32 bit, không được mặc định plain access là atomic.

Opaque đảm bảo tính nhất quán giữa các truy cập trên cùng biến. Acquire/Release dùng để công bố dữ liệu: thread ghi hoàn tất dữ liệu rồi gọi setRelease; thread đọc thấy cờ qua getAcquire thì các thao tác đọc tiếp theo được sắp sau acquire.

Volatile có ordering mạnh hơn và các volatile operation được sắp thứ tự toàn phần với nhau. Chọn mode dựa trên giao thức đồng bộ hóa thực tế; không dùng volatile cho mọi biến chỉ vì muốn tránh suy nghĩ về memory model.

**Lưu ý quan trọng:** access mode của VarHandle quyết định memory semantics tại lần truy cập đó, kể cả khi field được khai báo `volatile`. Gọi `get` trên một volatile field vẫn là plain access; gọi `getVolatile` mới yêu cầu volatile semantics. Tránh trộn các mode khác nhau trên cùng biến nếu chưa chứng minh được tính đúng đắn theo Java Memory Model.

## 4. Kiểu biến quyết định nhóm cập nhật nguyên tử

Với field hoặc array element có thể ghi, các nhóm atomic update phụ thuộc variable type:

| Kiểu biến | CAS / exchange / getAndSet | getAndAdd | Bitwise OR/AND/XOR |
|---|---:|---:|---:|
| Reference | Có | Không | Không |
| boolean | Có | Không | Có |
| byte, short, char | Có | Có | Có |
| int, long | Có | Có | Có |
| float, double | Có | Có | Không |

Giải thích:

- Reference có thể được so sánh và thay thế nguyên tử, nhưng không có phép cộng hoặc bitwise trên reference.
- boolean hỗ trợ các phép bitwise theo ngữ nghĩa logic, nhưng không hỗ trợ numeric add.
- byte, short, char, int và long hỗ trợ numeric và bitwise atomic update.
- float và double hỗ trợ numeric add, nhưng không hỗ trợ bitwise atomic update.
- Các mode có hậu tố Acquire/Release tuân theo cùng điều kiện hỗ trợ của nhóm tương ứng.

Đối với floating-point atomic update, việc so sánh trong các mode cập nhật dùng biểu diễn bit. Vì vậy `-0.0` và `+0.0` có thể được phân biệt; các giá trị NaN cũng cần được xử lý theo biểu diễn bit thay vì suy luận từ phép so sánh thông thường.

## 5. Biến final chỉ hỗ trợ đọc

Nếu VarHandle trỏ tới một biến chỉ đọc, ví dụ field `final`, các mode ghi và cập nhật nguyên tử không được hỗ trợ.

Với final field, các read mode được hỗ trợ là:

- `GET`
- `GET_VOLATILE`
- `GET_ACQUIRE`
- `GET_OPAQUE`

Các mode như `SET`, `SET_VOLATILE`, `COMPARE_AND_SET`, `GET_AND_SET` và `GET_AND_ADD` không được hỗ trợ. Gọi một mode ghi sẽ ném `UnsupportedOperationException`.

VarHandle không phải cơ chế bỏ qua quy tắc final của Java. Nếu dữ liệu cần thay đổi, hãy thiết kế biến mutable hoặc thay thế object theo mô hình bất biến; không dựa vào reflection hay cách truy cập nội bộ để sửa final field.

## 6. Field static và instance khác nhau ở tọa độ

Static hay instance chủ yếu quyết định cách xác định biến:

~~~java
VarHandle instanceValue = lookup.findVarHandle(
        Counter.class, "value", int.class
);

VarHandle globalValue = lookup.findStaticVarHandle(
        Counters.class, "total", long.class
);
~~~

Với `instanceValue`, access mode nhận một Counter làm tọa độ:

~~~java
instanceValue.get(counter);
instanceValue.set(counter, 10);
~~~

Với `globalValue`, không cần receiver:

~~~java
globalValue.get();
globalValue.set(100L);
~~~

Việc field là static hay instance không tự làm numeric hoặc bitwise mode được hỗ trợ thêm. Kiểu biến và tính chất chỉ đọc vẫn quyết định các nhóm mode.

## 7. Array element VarHandle

`MethodHandles.arrayElementVarHandle` tạo handle cho phần tử của array:

~~~java
VarHandle values = MethodHandles.arrayElementVarHandle(int[].class);

int[] array = {10, 20, 30};
int old = (int) values.getAndAdd(array, 1, 5);
boolean changed = (boolean) values.compareAndSet(array, 1, 25, 40);
~~~

Coordinate types là array và index. Kiểu phần tử quyết định các atomic update mode:

- int[] và long[] hỗ trợ CAS, getAndSet, getAndAdd và bitwise update.
- double[] hỗ trợ getAndAdd nhưng không hỗ trợ bitwise update.
- Object[] hỗ trợ CAS và getAndSet nhưng không hỗ trợ numeric hoặc bitwise update.

Index vẫn phải nằm trong giới hạn array. VarHandle không bỏ qua null check, bounds check hoặc kiểu dữ liệu của phần tử.

## 8. Byte array view và ByteBuffer view có giới hạn riêng

Các view VarHandle đọc nhiều byte và ghép thành một giá trị primitive theo byte order. Chúng không có cùng tập access mode với array element handle thông thường.

**byteArrayViewVarHandle**

`MethodHandles.byteArrayViewVarHandle` tạo view cho các kiểu short, char, int, long, float hoặc double trên một byte[]. Trong JDK hiện hành từ JDK 23, handle này chỉ hỗ trợ plain `GET` và `SET`; các atomic hoặc ordered access mode khác không được hỗ trợ.

Không dựa vào aligned atomic access của byte[] view trong code mới. Hỗ trợ aligned atomic access mode cũ đã bị loại bỏ từ JDK 23.

**byteBufferViewVarHandle**

`MethodHandles.byteBufferViewVarHandle` tạo view trên ByteBuffer:

- Heap ByteBuffer luôn được xem là unaligned cho view access; chỉ plain `GET` và `SET` được hỗ trợ.
- Direct ByteBuffer có thể hỗ trợ các access mode mạnh hơn khi byte offset được căn chỉnh theo kích thước phần tử.
- Với direct buffer bị misaligned, chỉ plain `GET` và `SET` được phép; mode khác có thể ném `IllegalStateException`.
- Với direct buffer aligned, read/write mode được hỗ trợ cho kiểu view; atomic update hỗ trợ int, long, float, double; numeric và bitwise atomic update được bảo đảm cho int và long.

Do đó, `isAccessModeSupported` cho ByteBuffer view chỉ xác nhận capability của handle. Khi gọi trên một buffer cụ thể, loại buffer và alignment của offset vẫn có thể quyết định thao tác có hợp lệ hay không.

## 9. Kiểm tra trước khi gọi một access mode

Dùng `isAccessModeSupported` để hỏi handle có hỗ trợ một mode hay không:

~~~java
boolean canAdd = handle.isAccessModeSupported(
        VarHandle.AccessMode.GET_AND_ADD
);

if (canAdd) {
    Object previous = handle.getAndAdd(coordinates);
}
~~~

Không gọi thử mode rồi dùng exception làm cách dò thông thường. Hãy kiểm tra trước và thiết kế fallback theo đúng loại dữ liệu.

`accessModeType` cho biết chữ ký chính xác của một mode:

~~~java
MethodType type = handle.accessModeType(
        VarHandle.AccessMode.COMPARE_AND_SET
);
System.out.println(type);
~~~

Các tham số đầu tiên của chữ ký là coordinate types. Các tham số cuối là giá trị cần truyền cho mode. Ví dụ CAS có dạng:

~~~text
(coordinates..., expectedValue, newValue)boolean
~~~

Đối với handle field instance kiểu int, chữ ký có thể là:

~~~text
(Counter, int, int)boolean
~~~

Điều này hữu ích khi nối VarHandle với MethodHandle hoặc khi cần kiểm tra chữ ký động.

## 10. Các exception cần phân biệt

| Exception | Nguyên nhân thường gặp |
|---|---|
| `UnsupportedOperationException` | Access mode không được handle hỗ trợ, ví dụ SET trên final field |
| `WrongMethodTypeException` | Kiểu hoặc số lượng tham số không khớp accessModeType |
| `ClassCastException` | Coordinate hoặc reference value có kiểu không tương thích |
| `NullPointerException` | Coordinate object là null khi không hợp lệ |
| `IndexOutOfBoundsException` | Index hoặc byte offset vượt giới hạn |
| `IllegalStateException` | ByteBuffer view yêu cầu atomic mode nhưng offset không aligned |
| `ReadOnlyBufferException` | Ghi vào read-only ByteBuffer |

Không nhầm lỗi không hỗ trợ mode với lỗi coordinate. Một handle có thể hỗ trợ CAS nhưng một lần gọi vẫn thất bại do buffer read-only, index sai hoặc alignment không hợp lệ.

## 11. Ví dụ chạy được với Java 17+

Tạo file **VarHandleAccessSupportDemo.java**:

~~~java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;

public class VarHandleAccessSupportDemo {
    public static class State {
        public int count;
        public Object reference;
        public boolean flags;
        public double total;
        public final int id = 7;
    }

    public static void main(String[] args) throws Exception {
        MethodHandles.Lookup lookup = MethodHandles.lookup();
        Class<State> type = State.class;

        VarHandle count = lookup.findVarHandle(type, "count", int.class);
        VarHandle reference = lookup.findVarHandle(
                type, "reference", Object.class
        );
        VarHandle flags = lookup.findVarHandle(
                type, "flags", boolean.class
        );
        VarHandle total = lookup.findVarHandle(type, "total", double.class);
        VarHandle id = lookup.findVarHandle(type, "id", int.class);

        VarHandle byteArrayView = MethodHandles.byteArrayViewVarHandle(
                int[].class,
                ByteOrder.nativeOrder()
        );
        VarHandle intArray = MethodHandles.arrayElementVarHandle(int[].class);
        VarHandle byteBufferView = MethodHandles.byteBufferViewVarHandle(
                int[].class,
                ByteOrder.nativeOrder()
        );

        System.out.println("int GET_AND_ADD: "
                + count.isAccessModeSupported(
                        VarHandle.AccessMode.GET_AND_ADD));
        System.out.println("reference GET_AND_ADD: "
                + reference.isAccessModeSupported(
                        VarHandle.AccessMode.GET_AND_ADD));
        System.out.println("boolean BITWISE_OR: "
                + flags.isAccessModeSupported(
                        VarHandle.AccessMode.GET_AND_BITWISE_OR));
        System.out.println("double GET_AND_ADD: "
                + total.isAccessModeSupported(
                        VarHandle.AccessMode.GET_AND_ADD));
        System.out.println("double BITWISE_OR: "
                + total.isAccessModeSupported(
                        VarHandle.AccessMode.GET_AND_BITWISE_OR));
        System.out.println("final SET: "
                + id.isAccessModeSupported(VarHandle.AccessMode.SET));
        System.out.println("byte[] view CAS: "
                + byteArrayView.isAccessModeSupported(
                        VarHandle.AccessMode.COMPARE_AND_SET));
        System.out.println("int[] element GET_AND_ADD: "
                + intArray.isAccessModeSupported(
                        VarHandle.AccessMode.GET_AND_ADD));
        System.out.println("ByteBuffer view CAS capability: "
                + byteBufferView.isAccessModeSupported(
                        VarHandle.AccessMode.COMPARE_AND_SET));

        State state = new State();
        count.set(state, 10);
        int previous = (int) count.getAndAdd(state, 5);
        boolean exchanged = (boolean) count.compareAndSet(state, 15, 20);

        System.out.println("previous count: " + previous);
        System.out.println("current count: " + count.get(state));
        System.out.println("CAS success: " + exchanged);
        System.out.println("count CAS type: "
                + count.accessModeType(
                        VarHandle.AccessMode.COMPARE_AND_SET));

        try {
            id.set(state, 8);
        } catch (UnsupportedOperationException exception) {
            System.out.println("final write: UnsupportedOperationException");
        }

        ByteBuffer direct = ByteBuffer.allocateDirect(8);
        byteBufferView.set(direct, 0, 4);
        boolean directCas = (boolean) byteBufferView.compareAndSet(
                direct, 0, 4, 9
        );
        System.out.println("direct aligned ByteBuffer CAS: " + directCas);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac VarHandleAccessSupportDemo.java
java VarHandleAccessSupportDemo
~~~

Kết quả stdout trên JDK 24:

~~~text
int GET_AND_ADD: true
reference GET_AND_ADD: false
boolean BITWISE_OR: true
double GET_AND_ADD: true
double BITWISE_OR: false
final SET: false
byte[] view CAS: false
int[] element GET_AND_ADD: true
ByteBuffer view CAS capability: true
previous count: 10
current count: 20
CAS success: true
count CAS type: (State,int,int)boolean
final write: UnsupportedOperationException
direct aligned ByteBuffer CAS: true
~~~

Ví dụ được biên dịch với API Java 9 bằng `javac --release 9` và chạy trên JDK 24. Kết quả byte[] view phản ánh quy tắc hiện hành sau khi aligned atomic access mode bị loại bỏ. ByteBuffer direct được cấp phát và truy cập tại offset 0, là vị trí aligned cho int trong ví dụ.

## 12. Lỗi thường gặp

**Cho rằng mọi VarHandle đều hỗ trợ mọi mode:** mỗi factory và variable type có tập hỗ trợ riêng. Kiểm tra `isAccessModeSupported` và tài liệu factory.

**Dùng getAndAdd cho reference hoặc boolean:** numeric atomic update không hỗ trợ các kiểu đó. Chọn CAS/getAndSet hoặc một cấu trúc dữ liệu phù hợp.

**Dùng bitwise update cho float/double:** các kiểu này không hỗ trợ bitwise atomic update.

**Ghi vào final field:** final handle chỉ hỗ trợ read mode. SET và atomic update sẽ không được hỗ trợ.

**Cho rằng volatile field luôn được truy cập với volatile semantics:** access mode được gọi quyết định memory ordering. Plain get vẫn là plain read.

**Nhầm byte[] view với array element handle:** array element handle có thể hỗ trợ atomic mode theo kiểu phần tử; byteArrayView hiện chỉ hỗ trợ plain GET/SET.

**Bỏ qua alignment của ByteBuffer:** handle có thể hỗ trợ CAS nhưng một buffer heap hoặc direct offset misaligned vẫn không thực hiện được mode đó.

**Dùng exception để dò mode:** hãy kiểm tra capability trước; chỉ xử lý exception cho lỗi thực tế khi truy cập.

## 13. Checklist lựa chọn mode

- Xác định variable type bằng `varType()`.
- Xác định coordinate types và cách định vị biến.
- Kiểm tra biến có phải final/read-only không.
- Chọn memory ordering: plain, opaque, acquire/release hoặc volatile.
- Chọn atomic update theo kiểu: reference, boolean, numeric hoặc integral.
- Dùng `isAccessModeSupported` trước khi gọi mode tùy chọn.
- Dùng `accessModeType` khi cần kiểm tra chữ ký động.
- Kiểm tra bounds, read-only buffer và alignment tại từng lần truy cập.
- Không giả định byte[] view hoặc heap ByteBuffer hỗ trợ atomic mode trong JDK hiện hành.
- Tránh trộn nhiều memory ordering trên cùng biến nếu chưa có lập luận Java Memory Model rõ ràng.

Tập access mode của VarHandle được quyết định bởi kiểu và tính chất vùng nhớ mà handle đại diện. Mutable reference hỗ trợ CAS nhưng không hỗ trợ phép cộng; numeric primitive hỗ trợ getAndAdd; boolean và integral type hỗ trợ bitwise; final field chỉ đọc; byte-array và ByteBuffer view còn chịu giới hạn hiện hành về alignment. Kiểm tra capability trước khi gọi giúp tránh UnsupportedOperationException và giữ đúng hợp đồng đồng bộ hóa.

## Tài liệu tham khảo

- [VarHandle — Java SE 24 API](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/invoke/VarHandle.html)
- [MethodHandles — Java SE 24 API](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/invoke/MethodHandles.html)
- [JDK 23 Release Notes — Removal of aligned access modes](https://www.oracle.com/java/technologies/javase/23-relnote-issues.html)
