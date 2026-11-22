# Lỗi sai kiểu, sai tọa độ hoặc chế độ không hỗ trợ với `VarHandle`

`VarHandle` là tham chiếu có kiểu mạnh đến một biến hoặc một nhóm biến có thể được xác định bằng tọa độ. API này được giới thiệu trong Java 9 và hỗ trợ đọc, ghi, truy cập volatile, acquire/release, compare-and-set cùng các thao tác cập nhật nguyên tử.

Do các phương thức truy cập của `VarHandle` là *signature-polymorphic*, trình biên dịch không kiểm tra đầy đủ chữ ký truy cập như một lời gọi phương thức thông thường. Kiểu của biến, kiểu tọa độ, số lượng đối số và kiểu trả về được đối chiếu với access mode type khi chạy. Vì vậy, lỗi có thể xuất hiện ở runtime dưới dạng `WrongMethodTypeException`, `ClassCastException`, lỗi tọa độ hoặc `UnsupportedOperationException`.

Bài này phân biệt các nhóm lỗi đó, chỉ ra cách đọc metadata của một VarHandle trước khi gọi và kiểm tra hành vi bằng chương trình Java 17.

## 1. Ba khái niệm kiểu cần phân biệt

Mỗi VarHandle mô tả ít nhất hai nhóm kiểu:

- **Variable type:** kiểu của giá trị mà VarHandle đọc hoặc ghi.
- **Coordinate types:** các kiểu đối số dùng để xác định chính xác biến nào được truy cập.

Khi gọi một access mode, các đối số tọa độ đứng trước; các đối số mang giá trị cho thao tác đứng sau. Ví dụ `compareAndSet` nhận tọa độ, giá trị mong đợi và giá trị mới.

| Loại VarHandle | Variable type | Coordinate types |
| --- | --- | --- |
| Field instance `Box.count` kiểu `int` | `int` | `(Box)` |
| Field static kiểu `long` | `long` | `()` |
| Phần tử của `String[]` | `String` | `(String[], int)` |
| Phần tử `int` nhìn qua `ByteBuffer` | `int` | `(ByteBuffer, int)`; số nguyên cuối là byte offset |

Ví dụ tạo VarHandle cho field instance và mảng:

```java
VarHandle field = MethodHandles.lookup()
    .findVarHandle(Box.class, "count", int.class);

VarHandle array = MethodHandles.arrayElementVarHandle(String[].class);
```

Field instance cần đối tượng chứa field làm tọa độ. Field static không cần receiver. Array element cần tham chiếu mảng và chỉ số `int`.

## 2. Đọc chữ ký trước khi gọi access mode

Ba phương thức hữu ích để kiểm tra metadata:

```java
Class<?> variableType = handle.varType();
List<Class<?>> coordinates = handle.coordinateTypes();
MethodType signature = handle.accessModeType(VarHandle.AccessMode.GET);
```

- `varType()` trả về kiểu của biến được truy cập.
- `coordinateTypes()` trả danh sách kiểu tọa độ theo đúng thứ tự; danh sách này không thể sửa.
- `accessModeType(mode)` trả `MethodType` của access mode cụ thể. Các kiểu tọa độ nằm ở đầu danh sách tham số, tiếp theo là các tham số giá trị của thao tác; kiểu trả về cũng được thể hiện trong `MethodType`.

Với VarHandle cho phần tử `String[]`, chữ ký của `GET` tương đương `(String[], int)String`. `COMPARE_AND_SET` có chữ ký tương đương `(String[], int, String, String)boolean`.

Kiểm tra metadata trước khi gọi đặc biệt hữu ích khi VarHandle được truyền qua API tổng quát, reflection, cấu hình hoặc framework mà kiểu đối số không được thể hiện rõ tại vị trí gọi.

## 3. Lỗi sai kiểu: `WrongMethodTypeException`

`WrongMethodTypeException` xuất hiện khi kiểu lời gọi access mode không thể khớp với access mode type của VarHandle. Việc kiểm tra diễn ra khi chạy vì access mode methods có tính signature-polymorphic.

Các nguyên nhân thường gặp:

- Truyền giá trị `String` cho VarHandle đang truy cập biến `int`.
- Truyền chỉ số `long` cho tọa độ yêu cầu `int`.
- Thiếu hoặc thừa đối số tọa độ.
- Dùng kiểu trả về không tương thích với kiểu mà access mode yêu cầu.
- Dùng một call site có descriptor không thể chuyển đổi sang access mode type.

Ví dụ:

```java
VarHandle count = MethodHandles.lookup()
    .findVarHandle(Box.class, "count", int.class);
Box box = new Box();

count.set(box, "not-an-int");
```

Lời gọi không có kiểu tương thích với access mode `SET` của field `int`, nên runtime ném `WrongMethodTypeException`.

VarHandle mặc định có *invoke behavior*: JVM áp dụng các chuyển đổi kiểu mà cơ chế MethodHandle cho phép, chẳng hạn boxing, unboxing, primitive widening và reference cast. Chuyển đổi không được hỗ trợ vẫn gây `WrongMethodTypeException`. Không nên hiểu rằng mọi kiểu số hoặc mọi kiểu tham chiếu đều tự động chuyển đổi được.

### `WrongMethodTypeException` khác `ClassCastException` thế nào?

Đây là hai lỗi dễ nhầm:

- **WrongMethodTypeException:** descriptor/chữ ký của lời gọi không thể thích ứng với access mode type, ví dụ truyền `String` thay cho `int` hoặc thiếu tọa độ.
- **ClassCastException:** lời gọi có thể được thích ứng bằng reference cast, nhưng object thực tế không thuộc kiểu tọa độ được yêu cầu.

Ví dụ field cần receiver `Box`. Nếu truyền một `Object` có kiểu thực tế không phải `Box`, việc ép kiểu receiver khi chạy có thể ném `ClassCastException`.

## 4. Lỗi sai tọa độ

Tọa độ xác định biến cụ thể mà VarHandle sẽ truy cập. Số lượng và kiểu tọa độ phải khớp với metadata của VarHandle.

### Sai số lượng hoặc kiểu tọa độ

Với VarHandle cho `String[]`, tọa độ là `(String[], int)`. Gọi `get(array)` thiếu chỉ số, hoặc `get(array, 1L)` truyền `long` thay cho `int`, gây `WrongMethodTypeException` vì chữ ký không khớp.

```java
VarHandle elements = MethodHandles.arrayElementVarHandle(String[].class);
String[] names = {"Ada", "Lin"};

elements.get(names);       // Thiếu coordinate int
elements.get(names, 1L);   // Coordinate long thay vì int
```

### Receiver sai kiểu tại runtime

Với field instance có coordinate type `Box`, truyền object thực tế không phải `Box` có thể gây `ClassCastException` khi runtime thực hiện reference cast.

```java
VarHandle count = MethodHandles.lookup()
    .findVarHandle(Box.class, "count", int.class);

int value = (int) count.get(new Object());
```

### Tọa độ null

Nếu một coordinate tham chiếu không được phép null, thao tác có thể ném `NullPointerException`. Với array element VarHandle, tham chiếu mảng null gây `NullPointerException`.

### Chỉ số ngoài phạm vi

Với array element VarHandle, chỉ số âm hoặc lớn hơn hay bằng độ dài mảng gây `ArrayIndexOutOfBoundsException`.

```java
String[] names = {"Ada", "Lin"};
elements.get(names, 2);
```

Chỉ số `2` không hợp lệ vì mảng chỉ có các vị trí `0` và `1`.

### Không nhầm chỉ số phần tử với byte offset

VarHandle được tạo bởi `MethodHandles.byteBufferViewVarHandle(int[].class, order)` truy cập một view `int` bên trong `ByteBuffer`, nhưng coordinate kiểu `int` là **byte offset**, không phải chỉ số phần tử `int`.

Với kiểu `int`, offset phải còn đủ bốn byte trong giới hạn buffer. Offset âm hoặc vượt quá `limit - 4` gây `IndexOutOfBoundsException`. Đây là khác biệt quan trọng so với array element VarHandle, nơi coordinate `int` là chỉ số phần tử.

## 5. Chế độ truy cập không được hỗ trợ: `UnsupportedOperationException`

Không phải VarHandle nào cũng hỗ trợ mọi access mode. Các mode có thể phụ thuộc kiểu biến, cách tạo VarHandle và việc biến có thể ghi được hay không.

Ví dụ các nhóm mode:

| Nhóm | Một số access mode |
| --- | --- |
| Đọc | `GET`, `GET_VOLATILE`, `GET_ACQUIRE`, `GET_OPAQUE` |
| Ghi | `SET`, `SET_VOLATILE`, `SET_RELEASE`, `SET_OPAQUE` |
| Cập nhật nguyên tử | `COMPARE_AND_SET`, `COMPARE_AND_EXCHANGE`, `GET_AND_SET` |
| Cập nhật số học nguyên tử | `GET_AND_ADD` và các biến thể acquire/release |
| Cập nhật bit nguyên tử | `GET_AND_BITWISE_OR`, `GET_AND_BITWISE_AND`, `GET_AND_BITWISE_XOR` và các biến thể |

Nếu mode không được hỗ trợ, gọi phương thức tương ứng sẽ ném `UnsupportedOperationException`. `GET` được hỗ trợ cho mọi VarHandle.

### Field `final` là biến chỉ đọc

VarHandle tham chiếu đến field `final` là read-only. Các mode ghi, cập nhật nguyên tử, cập nhật số học và cập nhật bit không được hỗ trợ.

```java
VarHandle fixed = MethodHandles.lookup()
    .findVarHandle(Box.class, "fixed", int.class);

boolean canWrite = fixed.isAccessModeSupported(VarHandle.AccessMode.SET);
```

`canWrite` là `false`. Gọi `fixed.set(box, 10)` sẽ ném `UnsupportedOperationException`.

### Mode phụ thuộc kiểu biến

VarHandle cho `String[]` không hỗ trợ các numeric atomic update modes như `GET_AND_ADD`, vì kiểu phần tử không phải kiểu số được hỗ trợ cho nhóm thao tác đó. Gọi `getAndAdd` trên VarHandle này ném `UnsupportedOperationException`.

Điều này khác với sai kiểu đối số: một lời gọi có thể đúng chữ ký nhưng mode vẫn không được hỗ trợ cho loại biến mà VarHandle tham chiếu.

## 6. Kiểm tra mode trước khi gọi

Dùng `isAccessModeSupported(mode)` để kiểm tra khả năng hỗ trợ:

```java
VarHandle.AccessMode mode = VarHandle.AccessMode.GET_AND_ADD;

if (!handle.isAccessModeSupported(mode)) {
    throw new UnsupportedOperationException(
        "Access mode is not supported: " + mode);
}
```

Kiểm tra này giúp tránh gọi một mode chắc chắn không được hỗ trợ. Tuy nhiên, kết quả `true` không bảo đảm mọi lần truy cập đều thành công: tọa độ vẫn có thể null, sai kiểu hoặc ngoài phạm vi; buffer có thể chỉ đọc; thao tác nguyên tử có thể không thỏa điều kiện căn chỉnh.

Đối với API tổng quát, nên kiểm tra cả ba lớp thông tin:

1. **Kiểu và số lượng đối số:** xem `coordinateTypes()` và `accessModeType(mode)`.
2. **Khả năng hỗ trợ mode:** xem `isAccessModeSupported(mode)`.
3. **Giá trị tọa độ tại runtime:** kiểm tra receiver, null, chỉ số, giới hạn và alignment theo loại VarHandle.

## 7. Lỗi đặc thù của ByteBuffer view VarHandle

ByteBuffer view VarHandle truy cập byte trong buffer như thể chúng là phần tử của kiểu nguyên thủy khác, ví dụ `int` hoặc `long`. Ngoài lỗi sai tọa độ và mode, còn có các điều kiện riêng:

- **Sai giới hạn:** offset phải đủ chỗ cho toàn bộ giá trị. Với `int`, cần bốn byte từ offset đó đến trước `limit`.
- **Sai alignment:** các access mode khác `GET` và `SET` yêu cầu offset căn chỉnh theo kích thước kiểu dữ liệu để bảo đảm atomicity. Truy cập nguyên tử tại offset không căn chỉnh gây `IllegalStateException`.
- **Buffer chỉ đọc:** các access mode ghi trên read-only `ByteBuffer` gây `ReadOnlyBufferException`.
- **Byte order:** `byteBufferViewVarHandle` dùng byte order được truyền vào factory; byte order này quyết định cách ghép byte thành giá trị và ghi đè byte order hiện tại của buffer cho view đó.

Ví dụ với view `int`:

```java
VarHandle ints = MethodHandles.byteBufferViewVarHandle(
    int[].class, ByteOrder.nativeOrder());
ByteBuffer buffer = ByteBuffer.allocate(8);

ints.set(buffer, 0, 10);       // Offset 0, căn chỉnh cho int
ints.getAndAdd(buffer, 1, 1);  // Offset 1 không căn chỉnh
```

Ở ví dụ trên, `getAndAdd` tại offset `1` gây `IllegalStateException`. Nếu buffer là read-only, `set` gây `ReadOnlyBufferException`.

## 8. Bảng phân biệt các lỗi thường gặp

| Tình huống | Exception thường gặp | Cách xử lý |
| --- | --- | --- |
| Giá trị truyền vào không thể thích ứng với kiểu biến | `WrongMethodTypeException` | Kiểm tra `varType()` và `accessModeType(mode)`. |
| Thiếu/thừa coordinate hoặc coordinate có kiểu không tương thích | `WrongMethodTypeException` | Kiểm tra số lượng và thứ tự `coordinateTypes()`. |
| Receiver là object sai kiểu tại runtime | `ClassCastException` | Truyền đúng instance của lớp chứa field. |
| Array reference là null | `NullPointerException` | Kiểm tra tham chiếu trước khi truy cập. |
| Array index ngoài phạm vi | `ArrayIndexOutOfBoundsException` | Kiểm tra `0 <= index < array.length`. |
| Mode không được hỗ trợ bởi VarHandle | `UnsupportedOperationException` | Kiểm tra `isAccessModeSupported(mode)`. |
| Atomic access trên ByteBuffer view không căn chỉnh | `IllegalStateException` | Tính alignment theo kích thước kiểu. |
| Ghi vào read-only ByteBuffer | `ReadOnlyBufferException` | Dùng buffer có thể ghi hoặc chỉ đọc. |

Các exception trên xuất phát từ những điều kiện khác nhau. Không nên bắt tất cả bằng `RuntimeException` rồi bỏ qua, vì cách đó có thể che giấu lỗi lập trình hoặc làm dữ liệu sai mà không có dấu hiệu.

## 9. Chương trình hoàn chỉnh kiểm tra kiểu, tọa độ và mode

Chương trình sau kiểm tra field `int`, array element `String`, field `final` và ByteBuffer view `int`. Mỗi trường hợp đều xác nhận đúng exception hoặc kết quả mong đợi.

```java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;
import java.lang.invoke.WrongMethodTypeException;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.ReadOnlyBufferException;

public class Main {
    static final class Box {
        int count = 1;
        final int fixed = 9;
    }

    public static void main(String[] args) throws Exception {
        VarHandle count = MethodHandles.lookup()
            .findVarHandle(Box.class, "count", int.class);
        Box box = new Box();

        System.out.println("field variable type: "
            + count.varType().getTypeName());
        System.out.println("field coordinate types: "
            + count.coordinateTypes());

        count.set(box, 2);
        check((int) count.get(box) == 2, "valid field access");
        System.out.println("valid field access: 2");

        try {
            count.set(box, "wrong");
            throw new AssertionError("wrong value type was accepted");
        } catch (WrongMethodTypeException expected) {
            System.out.println("wrong field value type: WrongMethodTypeException");
        }

        try {
            int ignored = (int) count.get(new Object());
            throw new AssertionError("wrong receiver was accepted: " + ignored);
        } catch (ClassCastException expected) {
            System.out.println("wrong receiver object: ClassCastException");
        }

        VarHandle elements =
            MethodHandles.arrayElementVarHandle(String[].class);
        String[] names = {"Ada", "Lin"};
        System.out.println("array coordinate types: "
            + elements.coordinateTypes());
        System.out.println("array GET type: "
            + elements.accessModeType(VarHandle.AccessMode.GET));
        check("Lin".equals((String) elements.get(names, 1)),
            "valid array coordinate");
        System.out.println("valid array access: Lin");

        try {
            elements.get(names);
            throw new AssertionError("missing coordinate was accepted");
        } catch (WrongMethodTypeException expected) {
            System.out.println("missing array index: WrongMethodTypeException");
        }

        try {
            elements.get(names, 1L);
            throw new AssertionError("long index was accepted");
        } catch (WrongMethodTypeException expected) {
            System.out.println("long array index: WrongMethodTypeException");
        }

        try {
            String ignored = (String) elements.get(names, 2);
            throw new AssertionError("out-of-range index was accepted: " + ignored);
        } catch (ArrayIndexOutOfBoundsException expected) {
            System.out.println("out-of-range array index: ArrayIndexOutOfBoundsException");
        }

        try {
            String ignored = (String) elements.get(null, 0);
            throw new AssertionError("null array was accepted: " + ignored);
        } catch (NullPointerException expected) {
            System.out.println("null array coordinate: NullPointerException");
        }

        VarHandle.AccessMode add = VarHandle.AccessMode.GET_AND_ADD;
        System.out.println("String[] supports GET_AND_ADD: "
            + elements.isAccessModeSupported(add));
        try {
            elements.getAndAdd(names, 0, "x");
            throw new AssertionError("unsupported numeric update was accepted");
        } catch (UnsupportedOperationException expected) {
            System.out.println("GET_AND_ADD on String[]: UnsupportedOperationException");
        }

        VarHandle fixed = MethodHandles.lookup()
            .findVarHandle(Box.class, "fixed", int.class);
        System.out.println("final field supports SET: "
            + fixed.isAccessModeSupported(VarHandle.AccessMode.SET));
        try {
            fixed.set(box, 10);
            throw new AssertionError("write to final field was accepted");
        } catch (UnsupportedOperationException expected) {
            System.out.println("write to final field: UnsupportedOperationException");
        }

        VarHandle ints = MethodHandles.byteBufferViewVarHandle(
            int[].class, ByteOrder.nativeOrder());
        ByteBuffer buffer = ByteBuffer.allocate(8);
        ints.set(buffer, 0, 10);
        System.out.println("ByteBuffer view value: "
            + (int) ints.get(buffer, 0));

        try {
            ints.getAndAdd(buffer, 1, 1);
            throw new AssertionError("misaligned atomic access was accepted");
        } catch (IllegalStateException expected) {
            System.out.println("misaligned atomic access: IllegalStateException");
        }

        try {
            ints.set(buffer.asReadOnlyBuffer(), 0, 20);
            throw new AssertionError("read-only buffer accepted a write");
        } catch (ReadOnlyBufferException expected) {
            System.out.println("write to read-only buffer: ReadOnlyBufferException");
        }
    }

    private static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }
}
```

Lưu thành `Main.java`, biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac --release 17 -Xlint:all Main.java
java Main
```

Stdout chính xác trên JDK 17:

```text
field variable type: int
field coordinate types: [class Main$Box]
valid field access: 2
wrong field value type: WrongMethodTypeException
wrong receiver object: ClassCastException
array coordinate types: [class [Ljava.lang.String;, int]
array GET type: (String[],int)String
valid array access: Lin
missing array index: WrongMethodTypeException
long array index: WrongMethodTypeException
out-of-range array index: ArrayIndexOutOfBoundsException
null array coordinate: NullPointerException
String[] supports GET_AND_ADD: false
GET_AND_ADD on String[]: UnsupportedOperationException
final field supports SET: false
write to final field: UnsupportedOperationException
ByteBuffer view value: 10
misaligned atomic access: IllegalStateException
write to read-only buffer: ReadOnlyBufferException
```

Ví dụ dùng các API VarHandle hiện hành, không phụ thuộc thư viện ngoài. Nó cố ý tạo từng lỗi để minh họa nguyên nhân và xác nhận loại exception; trong ứng dụng thực tế, cần kiểm tra điều kiện trước khi thực hiện thao tác.

## 10. Quy trình chẩn đoán có hệ thống

Khi một access mode ném exception, hãy kiểm tra theo thứ tự:

1. **Xác nhận VarHandle đang trỏ đến biến nào:** kiểm tra `varType()` và nguồn tạo VarHandle.
2. **Đọc coordinate types:** đối chiếu đúng số lượng, thứ tự và kiểu của receiver/index/offset.
3. **Đọc access mode type:** dùng `accessModeType(mode)` để xác định cả tham số giá trị và kiểu trả về.
4. **Kiểm tra chuyển đổi kiểu:** xác nhận primitive/reference conversion được phép; không dựa vào việc trình biên dịch cho phép viết lời gọi.
5. **Kiểm tra tọa độ runtime:** receiver đúng lớp, không null; array index hoặc byte offset nằm trong giới hạn.
6. **Kiểm tra mode:** gọi `isAccessModeSupported(mode)` trước các mode phụ thuộc kiểu hoặc biến read-only.
7. **Kiểm tra điều kiện đặc thù:** ByteBuffer có read-only không, offset có căn chỉnh không, buffer còn đủ dung lượng không.
8. **Giữ exception có ý nghĩa:** phân loại lỗi đầu vào, lỗi lập trình và lỗi môi trường; chỉ chuyển đổi exception khi hợp đồng API yêu cầu.

Trong lớp tiện ích dùng VarHandle tổng quát, có thể ghi log `varType`, `coordinateTypes`, mode và `accessModeType` khi khởi tạo. Điều này giúp phát hiện cấu hình sai sớm thay vì đợi đến khi một request thực tế kích hoạt lỗi.

## 11. Lỗi thường gặp

1. **Nghĩ trình biên dịch kiểm tra đầy đủ kiểu access mode.** Các phương thức signature-polymorphic được kiểm tra theo access mode type ở runtime.
2. **Nhầm variable type với coordinate type.** Kiểu biến là giá trị được đọc/ghi; coordinate xác định vị trí của biến.
3. **Cho rằng mọi lỗi sai kiểu đều là `ClassCastException`.** Descriptor không thể thích ứng gây `WrongMethodTypeException`; cast reference thất bại ở runtime có thể gây `ClassCastException`.
4. **Bỏ quên coordinate của field instance.** Field instance cần receiver; field static không có coordinate receiver.
5. **Dùng `long` làm array index.** Array element VarHandle yêu cầu coordinate `int`; chuyển đổi narrowing không tự động được áp dụng.
6. **Không kiểm tra biên array.** Kiểu tọa độ đúng không bảo đảm chỉ số hợp lệ.
7. **Gọi mode không hỗ trợ rồi bỏ qua `UnsupportedOperationException`.** Hãy kiểm tra `isAccessModeSupported` và chọn thao tác phù hợp với kiểu biến.
8. **Ghi vào field `final`.** VarHandle của biến read-only không hỗ trợ write hoặc các mode cập nhật.
9. **Gọi `GET_AND_ADD` trên kiểu không phải số được hỗ trợ.** Numeric atomic update chỉ áp dụng cho các kiểu được factory tương ứng hỗ trợ.
10. **Nhầm byte offset của ByteBuffer view với chỉ số phần tử.** Offset tính theo byte và cần đủ dung lượng cho kiểu dữ liệu.
11. **Thực hiện atomic access ở offset không căn chỉnh.** Với byte-array/ByteBuffer view VarHandle, các mode khác `GET` và `SET` có thể ném `IllegalStateException` khi misaligned.
12. **Bỏ qua buffer chỉ đọc.** Ghi vào read-only ByteBuffer gây `ReadOnlyBufferException`.
13. **Bắt mọi `RuntimeException` rồi tiếp tục.** Điều này có thể che giấu lỗi kiểu, lỗi dữ liệu hoặc vi phạm điều kiện atomicity.

## 12. Ghi nhớ

1. `VarHandle` có `varType`, `coordinateTypes` và access mode type riêng cho từng thao tác.
2. `WrongMethodTypeException` báo chữ ký lời gọi không thể khớp với access mode type.
3. `ClassCastException` có thể xảy ra khi coordinate tham chiếu có object runtime sai kiểu.
4. Coordinate thiếu/thừa hoặc sai kiểu có thể gây `WrongMethodTypeException`; null và chỉ số ngoài phạm vi có exception riêng.
5. `isAccessModeSupported(mode)` cho biết mode có được hỗ trợ; mode không hỗ trợ gây `UnsupportedOperationException`.
6. Field `final` là read-only; các mode ghi và cập nhật không được hỗ trợ.
7. ByteBuffer view dùng byte offset; misaligned atomic access gây `IllegalStateException`, còn ghi vào read-only buffer gây `ReadOnlyBufferException`.
8. Kiểm tra metadata, tọa độ, giới hạn và mode trước khi gọi access mode trong API tổng quát.