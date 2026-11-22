# 9.4. Kiểu biến, kiểu tọa độ và accessModeType của từng thao tác

> **Bối cảnh:** Đây là bài Knowledge trong nhóm **9. VarHandle** của module **Java Advance – dynamic-runtime**. Một `VarHandle` không chỉ “trỏ vào một field”: nó biểu diễn *một biến hoặc một họ biến* bằng **kiểu giá trị** (`varType()`), **danh sách kiểu tọa độ** (`coordinateTypes()`), và **chữ ký của mỗi chế độ truy cập** (`accessModeType(...)`). Hiểu đúng ba thành phần này là nền tảng để gọi `get`, `set`, CAS, atomic update và chẩn đoán `WrongMethodTypeException` trên Java 21.

## 1. Mục tiêu và phạm vi

Sau bài này, bạn cần có khả năng:

1. Định nghĩa `T = vh.varType()`, `CT = vh.coordinateTypes()`, biết lúc nào `CT` rỗng, có một hoặc nhiều phần tử.
2. Xác định `T` và tọa độ đối với instance field, static field, phần tử mảng, mảng nhiều chiều, `byte[]`/`ByteBuffer` view.
3. Tự suy ra kiểu trả về và thứ tự tham số của **mọi nhóm access modes** từ một cặp `(T, CT)`, sau đó kiểm chứng bằng `vh.accessModeType(AccessMode.X)`.
4. Phân biệt **chữ ký có tồn tại** với **chế độ có được hỗ trợ** (`isAccessModeSupported`), đặc biệt với `final`, reference, boolean, các kiểu số và memory views.
5. Hiểu khác biệt giữa *plain/opaque/acquire/release/volatile* về ý nghĩa bộ nhớ dù các mode có thể dùng **cùng MethodType**.
6. Gọi `VarHandle` và `toMethodHandle` đúng vị trí receiver/array index, kiểu value, return cast; xác định nguyên nhân `WrongMethodTypeException` và `UnsupportedOperationException`.
7. Viết chương trình thuần JDK 21 để tự kiểm tra signature và hành vi, không cần framework hoặc `sun.*`/`jdk.internal.*`.

**Điều kiện nền:** field `static`/instance, array, `Class<?>`, `MethodType`, `MethodHandle`, visibility/access control, kiến thức Java Memory Model ở mức nhận biết. Các lab sử dụng `java.lang.invoke` từ Java 21.

## 2. Mô hình cốt lõi: một VarHandle có T và CT

Một `VarHandle` gắn với:

- **Variable type `T`**: kiểu của giá trị đang được đọc, ghi hoặc cập nhật. Java API: `Class<?> varType()`.
- **Coordinate types `CT1..CTn`**: danh sách có thứ tự những kiểu dùng để **xác định biến cụ thể**. Java API: `List<Class<?>> coordinateTypes()`.
- **Access modes**: các cách thao tác trên biến đã xác định; mỗi mode có một **`MethodType`** riêng mô tả *tham số* và *return*.

Sơ đồ suy luận:

```text
VarHandle
├── varType()            = T
├── coordinateTypes()    = [CT1, CT2, ... CTn]
└── accessModeType(mode) = MethodType(
       return type theo mode,
       CT1, CT2, ... CTn, [các tham số giá trị theo mode]
    )

Ví dụ: int[] values
  T  = int
  CT = [int[], int]
  GET             = (int[], int)int
  SET             = (int[], int, int)void
  COMPARE_AND_SET = (int[], int, int, int)boolean
```

**Tọa độ không phải tham số dữ liệu cần ghi.** Với mảng `int[]`, hai tọa độ là *mảng cụ thể* và *chỉ số*. Với lệnh `set`, đối số `int` cuối cùng mới là giá trị cần ghi. Với compare-and-set, sau các tọa độ có **hai** đối số `expected` và `newValue`.

`coordinateTypes()` trả một danh sách **không sửa được** theo hợp đồng API; không được dựa vào class implementation của danh sách. Mỗi phần tử là một `Class<?>`, có thể là primitive `int.class`, kiểu mảng `int[].class`, kiểu object `Box.class`.

### 2.1. Công thức tổng quát

Đặt `C = (CT1, ..., CTn)` và `T = variable type`:

| Nhóm thao tác | Access-mode type |
| --- | --- |
| Đọc | `(C)T` |
| Ghi | `(C, T newValue)void` |
| Compare-and-set / weak CAS | `(C, T expectedValue, T newValue)boolean` |
| Compare-and-exchange | `(C, T expectedValue, T newValue)T` |
| Get-and-set | `(C, T newValue)T` |
| Get-and-add | `(C, T delta)T` |
| Get-and-bitwise | `(C, T mask)T` |

`C` là **phần danh sách tham số** cần mở rộng, không phải một parameter object tên C. Với `C=[]`, `(C)T` thành `()T`. Với `C=[Box.class]`, `(C,T)void` thành `(Box,T)void`. Với `C=[int[].class,int.class]`, thêm value `int` thành `(int[],int,int)void`.

## 3. Tạo VarHandle và suy ra tọa độ từ nơi lưu biến

### 3.1. Instance field

```java
// Đoạn khai báo và lookup minh họa trong class cùng phạm vi truy cập.
class Counter { int value; }
VarHandle vh = MethodHandles.lookup()
        .findVarHandle(Counter.class, "value", int.class);
```

`T = int.class` và `CT = [Counter.class]`. Tọa độ là **đối tượng Counter** (receiver). `get(counter)` có chữ ký `(Counter)int`; `set(counter, 7)` có chữ ký `(Counter,int)void`.

Đừng nhầm `T` với kiểu class chứa field. `Counter` là **coordinate type**, còn `int` mới là **variable type**. `Lookup.findVarHandle` kiểm tra quyền và yêu cầu đúng tên field/kiểu field. Đối với protected field qua subclass khác package, receiver type trong handle có thể được thu hẹp theo quy tắc quyền truy cập; không suy chung chung mọi handle đều dùng declaring class gốc làm tọa độ.

### 3.2. Static field

```java
// Đoạn minh họa, nằm trong class có quyền truy cập tới Counter.
class Counter { static String label; }
VarHandle vh = MethodHandles.lookup()
        .findStaticVarHandle(Counter.class, "label", String.class);
```

`T = String.class` và `CT = []` (không có receiver). `get()` có type `()String` và `set("ready")` có type `(String)void`. Class dùng để **lookup field** không tự xuất hiện thành tọa độ.

Khi vận hành `VarHandle` static field, JVM có thể phải khởi tạo declaring class theo quy tắc tương ứng. Điều này không thay đổi số lượng coordinate types.

### 3.3. Phần tử mảng

```java
// Đoạn minh họa:
VarHandle vh = MethodHandles.arrayElementVarHandle(int[].class);
int[] values = {2, 4, 6};
int old = (int) vh.getAndAdd(values, 1, 5);
```

`T = int.class`, `CT = [int[].class, int.class]`. Tọa độ đầu là **mảng**, tọa độ thứ hai là **chỉ số phần tử**. `getAndAdd(values,1,5)` có type `(int[],int,int)int`. Nếu bắt đầu với `values[1]=4`, `old=4` và phần tử đó thành `9`.

Với `MethodHandles.arrayElementVarHandle(String[][].class)`, **mỗi biến được tham chiếu là một phần tử của mảng ngoài**; vì vậy `T = String[].class` và `CT = [String[][].class, int.class]`. API **không tự thêm một tọa độ int thứ hai** chỉ vì component là một array. Muốn trỏ tiếp đến `String` trong mảng con, dùng bước truy cập mảng thứ hai hoặc handle khác cho `String[].class`.

### 3.4. Byte-array và ByteBuffer views

`MethodHandles.byteArrayViewVarHandle(int[].class, ByteOrder.nativeOrder())` có `T = int.class`, `CT = [byte[].class, int.class]`. `MethodHandles.byteBufferViewVarHandle(int[].class, ByteOrder.nativeOrder())` có `CT = [ByteBuffer.class, int.class]`. Ở đây tham số `int` cuối của **tọa độ** là **vị trí byte**, không phải index của một `int[]` vật lý. Cách giải mã bytes phụ thuộc `ByteOrder` được chọn khi tạo view.

Với view kiểu `int`, một lần đọc dùng bốn byte từ vị trí phù hợp. Việc hỗ trợ atomic modes còn phụ thuộc **alignment**, khả năng truy cập, và với `ByteBuffer` còn có trạng thái read-only. Không suy rằng có type signature hợp lệ là mọi địa chỉ đều hỗ trợ CAS; truy cập không aligned có thể ném `IllegalStateException`, vùng ngoài giới hạn ném lỗi index, và ghi vào read-only buffer ném `ReadOnlyBufferException`.

### 3.5. Bảng đối chiếu

| Nguồn của handle | `T = varType()` | `CT = coordinateTypes()` | GET type | SET type |
| --- | --- | --- | --- | --- |
| Instance `Box.count: int` | `int` | `[Box]` | `(Box)int` | `(Box,int)void` |
| Static `Box.banner: String` | `String` | `[]` | `()String` | `(String)void` |
| `arrayElementVarHandle(int[].class)` | `int` | `[int[], int]` | `(int[],int)int` | `(int[],int,int)void` |
| `arrayElementVarHandle(String[][].class)` | `String[]` | `[String[][], int]` | `(String[][],int)String[]` | `(String[][],int,String[])void` |
| `byteArrayViewVarHandle(int[].class, ...)` | `int` | `[byte[], int]` | `(byte[],int)int` | `(byte[],int,int)void` |
| `byteBufferViewVarHandle(int[].class, ...)` | `int` | `[ByteBuffer, int]` | `(ByteBuffer,int)int` | `(ByteBuffer,int,int)void` |

Bảng này là **mẫu chữ ký**, không phải chứng nhận tất cả các access modes đều được hỗ trợ ở mọi địa chỉ hoặc trên field `final`.

## 4. `accessModeType(AccessMode)` trả gì?

`vh.accessModeType(mode)` trả một `java.lang.invoke.MethodType` có:

1. **Parameter prefix**: chính xác các `CT1..CTn` của `vh.coordinateTypes()`, **giữ nguyên thứ tự**.
2. **Parameter suffix**: 0, 1 hoặc 2 biến kiểu `T` tùy thao tác.
3. **Return type**: `T`, `void.class` hoặc `boolean.class` tùy nhóm.

Bạn có thể đọc `MethodType.parameterCount()`, `parameterType(i)`, `returnType()` hoặc in trực tiếp `MethodType.toString()` để kiểm tra. Ví dụ `(Box,int,int)boolean` là **type của phương thức access mode**, không nhất thiết là một method tự khai báo trong class `Box`.

**Điểm cực kỳ quan trọng:** `accessModeType(...)` vẫn cung cấp kiểu cho một mode **không được hỗ trợ**. Để biết có thể thực thi mode đó hay không, kiểm tra **`isAccessModeSupported(mode)`**. Nếu kết quả false thì lời gọi mode đó sẽ ném `UnsupportedOperationException`. `accessModeType` trả type chỉ chứng minh JVM biết **hình dạng lời gọi**, không chứng minh thao tác được phép.

### 4.1. Exhaustive mapping của các nhóm access modes

Mọi enum constant `VarHandle.AccessMode` của Java 21 nằm trong các nhóm dưới. Các hậu tố Acquire/Release/Volatile/Opaque thay đổi **memory semantics** hoặc độ mạnh của thao tác, không thay đổi *shape* đã liệt kê.

| AccessMode enum | Method tương ứng | `accessModeType` |
| --- | --- | --- |
| `GET`, `GET_OPAQUE`, `GET_ACQUIRE`, `GET_VOLATILE` | `get`, `getOpaque`, `getAcquire`, `getVolatile` | `(C)T` |
| `SET`, `SET_OPAQUE`, `SET_RELEASE`, `SET_VOLATILE` | `set`, `setOpaque`, `setRelease`, `setVolatile` | `(C,T)void` |
| `COMPARE_AND_SET` | `compareAndSet` | `(C,T,T)boolean` |
| `WEAK_COMPARE_AND_SET_PLAIN`, `WEAK_COMPARE_AND_SET`, `WEAK_COMPARE_AND_SET_ACQUIRE`, `WEAK_COMPARE_AND_SET_RELEASE` | `weakCompareAndSetPlain`, `weakCompareAndSet`, `weakCompareAndSetAcquire`, `weakCompareAndSetRelease` | `(C,T,T)boolean` |
| `COMPARE_AND_EXCHANGE`, `COMPARE_AND_EXCHANGE_ACQUIRE`, `COMPARE_AND_EXCHANGE_RELEASE` | `compareAndExchange`, `compareAndExchangeAcquire`, `compareAndExchangeRelease` | `(C,T,T)T` |
| `GET_AND_SET`, `GET_AND_SET_ACQUIRE`, `GET_AND_SET_RELEASE` | `getAndSet`, `getAndSetAcquire`, `getAndSetRelease` | `(C,T)T` |
| `GET_AND_ADD`, `GET_AND_ADD_ACQUIRE`, `GET_AND_ADD_RELEASE` | `getAndAdd`, `getAndAddAcquire`, `getAndAddRelease` | `(C,T)T` |
| `GET_AND_BITWISE_OR`, `GET_AND_BITWISE_OR_ACQUIRE`, `GET_AND_BITWISE_OR_RELEASE` | `getAndBitwiseOr`, `getAndBitwiseOrAcquire`, `getAndBitwiseOrRelease` | `(C,T)T` |
| `GET_AND_BITWISE_AND`, `GET_AND_BITWISE_AND_ACQUIRE`, `GET_AND_BITWISE_AND_RELEASE` | `getAndBitwiseAnd`, `getAndBitwiseAndAcquire`, `getAndBitwiseAndRelease` | `(C,T)T` |
| `GET_AND_BITWISE_XOR`, `GET_AND_BITWISE_XOR_ACQUIRE`, `GET_AND_BITWISE_XOR_RELEASE` | `getAndBitwiseXor`, `getAndBitwiseXorAcquire`, `getAndBitwiseXorRelease` | `(C,T)T` |

Tên enum dùng **UPPER_SNAKE_CASE**, còn tên method dùng **camelCase**; `mode.methodName()` trả tên phương thức tương ứng. Cả `GET_AND_ADD` lẫn `GET_AND_ADD_ACQUIRE` có cùng số lượng và kiểu tham số, nhưng khác memory ordering.

### 4.2. Ý nghĩa giá trị trả về

- **`get*`**: trả giá trị `T` được đọc.
- **`set*`**: trả `void`, chỉ ghi.
- **`compareAndSet` và `weakCompareAndSet*`**: trả `boolean`; true nghĩa là cập nhật thành công theo quy tắc mode. *Weak CAS* có thể **thất bại giả** ngay cả khi giá trị hiện tại bằng expected; cần vòng retry nếu yêu cầu.
- **`compareAndExchange*`**: trả về `T` là **giá trị witness quan sát được trước thao tác**. Nó không trả boolean; so witness với expected để suy ra điều kiện thành công theo quy tắc so sánh của kiểu.
- **`getAndSet*`**: trả giá trị `T` cũ và thay bằng new value.
- **`getAndAdd*`**: trả giá trị `T` cũ, cập nhật cộng thêm delta.
- **`getAndBitwiseOr/And/Xor*`**: trả giá trị `T` cũ, cập nhật theo phép bitwise với mask.

Thứ tự `(C, expected, newValue)` của CAS không đảo được. Với reference type, CAS sử dụng so sánh identity/giá trị theo quy tắc compare của VarHandle, không tự gọi `equals()` của object để kiểm tra bằng nhau về nội dung. Với `float`/`double`, các thao tác compare sử dụng biểu diễn bit của số; NaN và `-0.0`/`+0.0` cần chú ý, khác phép so sánh số học thông thường.

## 5. Lab 1 — tự in varType, coordinateTypes và accessModeType

Tạo **`VarHandleShapeLab.java`**:

```java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.VarHandle;
import java.util.Arrays;

public class VarHandleShapeLab {
    static class Box {
        volatile int count = 7;
        static String banner = "hello";
        final long id = 42L;
    }

    public static void main(String[] args) throws ReflectiveOperationException {
        MethodHandles.Lookup lookup = MethodHandles.lookup();
        VarHandle field = lookup.findVarHandle(Box.class, "count", int.class);
        VarHandle statik = lookup.findStaticVarHandle(Box.class, "banner", String.class);
        VarHandle array = MethodHandles.arrayElementVarHandle(int[].class);
        VarHandle readOnly = lookup.findVarHandle(Box.class, "id", long.class);

        System.out.println("field.variable=" + field.varType().getTypeName());
        System.out.println("field.coordinates=" + field.coordinateTypes());
        System.out.println("field.GET=" + field.accessModeType(VarHandle.AccessMode.GET));
        System.out.println("field.SET=" + field.accessModeType(VarHandle.AccessMode.SET));
        System.out.println("field.CAS=" + field.accessModeType(VarHandle.AccessMode.COMPARE_AND_SET));
        System.out.println("field.CAE=" + field.accessModeType(VarHandle.AccessMode.COMPARE_AND_EXCHANGE));
        System.out.println("field.ADD=" + field.accessModeType(VarHandle.AccessMode.GET_AND_ADD));
        System.out.println("field.OR=" + field.accessModeType(VarHandle.AccessMode.GET_AND_BITWISE_OR));

        System.out.println("static.variable=" + statik.varType().getTypeName());
        System.out.println("static.coordinates=" + statik.coordinateTypes());
        System.out.println("static.GET=" + statik.accessModeType(VarHandle.AccessMode.GET));
        System.out.println("static.SET=" + statik.accessModeType(VarHandle.AccessMode.SET));

        System.out.println("array.variable=" + array.varType().getTypeName());
        System.out.println("array.coordinates=" + array.coordinateTypes());
        System.out.println("array.GET=" + array.accessModeType(VarHandle.AccessMode.GET));
        System.out.println("array.CAS=" + array.accessModeType(VarHandle.AccessMode.COMPARE_AND_SET));

        System.out.println("readonly.SET.supported=" +
                readOnly.isAccessModeSupported(VarHandle.AccessMode.SET));
        System.out.println("readonly.GET=" + readOnly.accessModeType(VarHandle.AccessMode.GET));
        System.out.println("readonly.SET=" + readOnly.accessModeType(VarHandle.AccessMode.SET));

        System.out.println("string.ADD.supported=" +
                statik.isAccessModeSupported(VarHandle.AccessMode.GET_AND_ADD));
        System.out.println("string.OR.supported=" +
                statik.isAccessModeSupported(VarHandle.AccessMode.GET_AND_BITWISE_OR));
        System.out.println("int.ADD.supported=" +
                field.isAccessModeSupported(VarHandle.AccessMode.GET_AND_ADD));
        System.out.println("int.OR.supported=" +
                field.isAccessModeSupported(VarHandle.AccessMode.GET_AND_BITWISE_OR));

        System.out.println("GET_VOLATILE.sameType=" +
                field.accessModeType(VarHandle.AccessMode.GET)
                        .equals(field.accessModeType(VarHandle.AccessMode.GET_VOLATILE)));
        System.out.println("SET_RELEASE.sameType=" +
                field.accessModeType(VarHandle.AccessMode.SET)
                        .equals(field.accessModeType(VarHandle.AccessMode.SET_RELEASE)));
        System.out.println("methodHandle.type.equals=" +
                field.toMethodHandle(VarHandle.AccessMode.GET_AND_ADD).type()
                        .equals(field.accessModeType(VarHandle.AccessMode.GET_AND_ADD)));
    }
}
```

Biên dịch và chạy trong cùng thư mục chứa file:

```sh
javac --release 21 -Xlint:all VarHandleShapeLab.java
java VarHandleShapeLab
```

**Stdout có ý nghĩa (dạng `MethodType.toString()` và `Class.toString()`):**

```text
field.variable=int
field.coordinates=[class VarHandleShapeLab$Box]
field.GET=(Box)int
field.SET=(Box,int)void
field.CAS=(Box,int,int)boolean
field.CAE=(Box,int,int)int
field.ADD=(Box,int)int
field.OR=(Box,int)int
static.variable=java.lang.String
static.coordinates=[]
static.GET=()String
static.SET=(String)void
array.variable=int
array.coordinates=[class [I, int]
array.GET=(int[],int)int
array.CAS=(int[],int,int,int)boolean
readonly.SET.supported=false
readonly.GET=(Box)long
readonly.SET=(Box,long)void
string.ADD.supported=false
string.OR.supported=false
int.ADD.supported=true
int.OR.supported=true
GET_VOLATILE.sameType=true
SET_RELEASE.sameType=true
methodHandle.type.equals=true
```

### 5.1. Phân tích từng nhóm kết quả

1. **Instance field**: `field.varType()` là `int`, coordinate list có đúng `Box`. CAS cần `Box` + expected `int` + new `int` và trả `boolean`.
2. **Static field**: `banner` có `String` variable type, **không có tọa độ**. `GET` nhận 0 tham số và trả `String`.
3. **Array**: `varType=int` không nghĩa chỉ cần truyền một `int`. Phải cung cấp `int[]` và index trước giá trị cần ghi.
4. **`final` field**: `SET` có một `MethodType` xác định, nhưng `isAccessModeSupported(SET)` là `false`. Không có mâu thuẫn: một thứ là *chữ ký*, thứ còn lại là *khả năng thực thi*.
5. **Kiểu reference `String`**: numeric atomic update và bitwise atomic update không được hỗ trợ; so sánh `String` bằng CAS hoặc `getAndSet` vẫn có thể khả dụng khi field không final.
6. **Cùng type, khác memory semantics**: `GET` và `GET_VOLATILE` cùng `(Box)int`; `SET` và `SET_RELEASE` cùng `(Box,int)void`.
7. **Chuyển thành MethodHandle**: `toMethodHandle(GET_AND_ADD)` trả handle **đã gắn với VarHandle**, có type bằng `accessModeType(GET_AND_ADD)`. Không tự thêm một parameter `VarHandle` vào type của handle đã bound.

Một số cách in `Class<?>` trong list sẽ dùng tên binary/JVM của mảng (`class [I`) thay vì `int[]`. Để hiển thị thân thiện, duyệt list và dùng `Class.getTypeName()`; không parse `Class.toString()` bằng regex.

## 6. Hỗ trợ từng mode: type của biến quyết định gì?

Không thể suy `isAccessModeSupported` chỉ từ dạng chữ ký. Các VarHandle tạo qua field/array factories của JDK có những quy tắc nền tảng sau:

| Loại biến `T` / nơi lưu | Read (`get*`) | Write (`set*`) / CAS / getAndSet | `getAndAdd*` | `getAndBitwise*` |
| --- | --- | --- | --- | --- |
| Non-final `int` field | Có | Có | Có | Có |
| Non-final `long` field | Có | Có | Có | Có |
| Non-final `float`/`double` field | Có | Có | Có | **Không** |
| Non-final `boolean` field | Có | Có | **Không** | Có |
| Non-final `String`/reference field | Có | Có | **Không** | **Không** |
| `final long` field | Có | **Không** | **Không** | **Không** |
| `int[]` element | Có | Có | Có | Có |
| `String[]` element | Có | Có | **Không** | **Không** |
| `ByteBuffer` view `int` | Có | Tùy mode, alignment và tính read-only của buffer | Phụ thuộc loại view, alignment | Phụ thuộc loại view, alignment |

Đối với instance/static fields và array-element VarHandles tiêu chuẩn:

- Numeric atomic updates `GET_AND_ADD*` được hỗ trợ cho `byte`, `short`, `char`, `int`, `long`, `float`, `double`; **không hỗ trợ boolean hoặc reference**.
- Bitwise atomic updates `GET_AND_BITWISE_{OR,AND,XOR}*` hỗ trợ `boolean`, `byte`, `short`, `char`, `int`, `long`; **không hỗ trợ float/double/reference**.
- Compare-and-set, compare-and-exchange và get-and-set được hỗ trợ cho các kiểu biến có thể cập nhật khi factory/hệ thống bộ nhớ cung cấp thao tác đó.
- Field `final` tạo read-only VarHandle: mọi write/atomic updates không được hỗ trợ; `get` luôn được hỗ trợ.
- Byte-array/ByteBuffer view factories có **giới hạn riêng** theo primitive view type và alignment, không thể thay bằng bảng cho field/array thông thường.

`isAccessModeSupported` là bước kiểm tra cần thiết khi chọn mode động; nhưng kết quả true không loại trừ các lỗi lúc thực thi do tọa độ không hợp lệ, array index quá giới hạn hoặc misalignment. Đặc biệt với `ByteBuffer`, trạng thái **read-only** của buffer là thuộc tính của **object tọa độ tại thời điểm sử dụng**, không thể được phản ánh đầy đủ bằng một chữ ký `MethodType`.

### 6.1. API `get` luôn được hỗ trợ, còn mode khác cần xem xét

Theo hợp đồng `VarHandle`, `get` được hỗ trợ cho mọi VarHandle. `set` hoặc update operations có thể không được hỗ trợ vì `final`, vì biến không có kiểu thích hợp cho numeric/bitwise hoặc vì đặc điểm factory.

Ngay cả khi `vh.accessModeType(SET)` là `(Box,long)void` cho `final long id`, gọi `vh.set(box, 1L)` vẫn ném `UnsupportedOperationException`. Hãy kiểm tra `isAccessModeSupported` trước khi tạo API cho một mode mà người dùng có thể lựa chọn; đồng thời vẫn phải bắt lỗi runtime phù hợp.

## 7. Lab 2 — chạy các thao tác và đọc return types

Tạo file **`VarHandleCallsLab.java`**:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;
import java.lang.invoke.WrongMethodTypeException;

public class VarHandleCallsLab {
    static class Box {
        volatile int count = 7;
        final long id = 42;
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();
        VarHandle counter = lookup.findVarHandle(Box.class, "count", int.class);
        VarHandle id = lookup.findVarHandle(Box.class, "id", long.class);
        Box box = new Box();

        int initial = (int) counter.get(box);
        counter.setRelease(box, 10);
        int afterRelease = (int) counter.getAcquire(box);
        int oldAdd = (int) counter.getAndAdd(box, 5);
        boolean cas = counter.compareAndSet(box, 15, 18);
        int witness = (int) counter.compareAndExchange(box, 18, 30);
        int oldXor = (int) counter.getAndBitwiseXor(box, 3);
        MethodHandle bound = counter.toMethodHandle(VarHandle.AccessMode.GET_AND_ADD);
        int previous = (int) bound.invokeExact(box, 4);

        System.out.println("initial=" + initial);
        System.out.println("afterRelease=" + afterRelease);
        System.out.println("oldAdd=" + oldAdd);
        System.out.println("cas=" + cas);
        System.out.println("witness=" + witness);
        System.out.println("oldXor=" + oldXor);
        System.out.println("handlePrevious=" + previous);
        System.out.println("finalCount=" + (int) counter.getVolatile(box));

        try {
            id.set(box, 1L);
            System.out.println("readonly=unexpected");
        } catch (UnsupportedOperationException expected) {
            System.out.println("readonly=UnsupportedOperationException");
        }

        VarHandle exact = counter.withInvokeExactBehavior();
        try {
            Object ignored = exact.get(box);
            System.out.println("exact=unexpected " + ignored);
        } catch (WrongMethodTypeException expected) {
            System.out.println("exact=WrongMethodTypeException");
        }
    }
}
```

Lệnh:

```sh
javac --release 21 -Xlint:all VarHandleCallsLab.java
java VarHandleCallsLab
```

**Stdout:**

```text
initial=7
afterRelease=10
oldAdd=10
cas=true
witness=18
oldXor=30
handlePrevious=29
finalCount=33
readonly=UnsupportedOperationException
exact=WrongMethodTypeException
```

### 7.1. Từng phép thay đổi giá trị

- Ban đầu `count=7`. `setRelease(box,10)` ghi 10, `getAcquire(box)` đọc lại 10.
- `getAndAdd(box,5)` trả **10** (giá trị cũ), sau cập nhật `count=15`.
- `compareAndSet(box,15,18)` trả `true`, sau cập nhật `count=18`.
- `compareAndExchange(box,18,30)` trả witness **18**, sau cập nhật `count=30`.
- `getAndBitwiseXor(box,3)` trả **30**, sau cập nhật `30 ^ 3 = 29`.
- Handle bound `toMethodHandle(GET_AND_ADD)` nhận `(Box,int)int`. `invokeExact(box,4)` trả **29**, sau cập nhật `count=33`.
- `getVolatile` cuối đọc 33. Đây là ví dụ **một thread** để nhận biết signatures/return values, không chứng minh correctness của giao thức đa luồng bất kỳ.

### 7.2. Hai lỗi không thể gộp thành một

- `UnsupportedOperationException`: lời gọi có cấu trúc phù hợp nhưng **mode không được hỗ trợ**, ví dụ cố `set` field `final`.
- `WrongMethodTypeException`: lời gọi không phù hợp **MethodType kỳ vọng** (số lượng/kiểu tọa độ, giá trị hoặc return type theo cách invocation đang sử dụng). Trong lab, `withInvokeExactBehavior()` yêu cầu call-site type chính xác; biến đích `Object ignored` khiến return type mong đợi tại call site là `Object`, nhưng `GET` trên `int` VarHandle yêu cầu return primitive `int`.

`withInvokeExactBehavior()` có từ các phiên bản Java trước 21 và có tác dụng điều chỉnh cách kiểm tra signature của access-mode calls, không thay `varType()`/`coordinateTypes()`. Theo mặc định, VarHandle có thể có hành vi kiểu `MethodHandle.invoke` với một số conversions hợp lệ; không suy mọi mismatch đều tạo đúng một loại exception nếu không biết cách invocation. Việc in `accessModeType` trước khi gọi là cách debug tốt hơn đoán.

## 8. Lab 3 — array element và hạn chế của reference arrays

Tạo **`ArrayModeLab.java`**:

```java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;

public class ArrayModeLab {
    public static void main(String[] args) {
        VarHandle ints = MethodHandles.arrayElementVarHandle(int[].class);
        int[] values = {3, 4};

        int old = (int) ints.getAndAdd(values, 1, 6);
        int now = (int) ints.get(values, 1);
        boolean changed = ints.compareAndSet(values, 0, 3, 9);
        VarHandle strings = MethodHandles.arrayElementVarHandle(String[].class);

        System.out.println("array.old=" + old);
        System.out.println("array.now=" + now);
        System.out.println("array.cas=" + changed);
        System.out.println("array.first=" + values[0]);
        System.out.println("string.variable=" + strings.varType().getTypeName());
        System.out.println("string.coordinates=" + strings.coordinateTypes());
        System.out.println("string.GET=" + strings.accessModeType(VarHandle.AccessMode.GET));
        System.out.println("string.ADD.supported=" +
                strings.isAccessModeSupported(VarHandle.AccessMode.GET_AND_ADD));
        System.out.println("string.BITWISE.supported=" +
                strings.isAccessModeSupported(VarHandle.AccessMode.GET_AND_BITWISE_OR));
    }
}
```

```sh
javac --release 21 -Xlint:all ArrayModeLab.java
java ArrayModeLab
```

**Stdout:**

```text
array.old=4
array.now=10
array.cas=true
array.first=9
string.variable=java.lang.String
string.coordinates=[class [Ljava.lang.String;, int]
string.GET=(String[],int)String
string.ADD.supported=false
string.BITWISE.supported=false
```

`arrayElementVarHandle(String[].class)` có đúng hai tọa độ là **`String[]` và `int`**; variable type mới là `String`. Nó có thể hỗ trợ CAS với references nhưng không thể cộng số hoặc bitwise trên `String`. Đây là ví dụ cho thấy **type của biến** quyết định nhóm cập nhật số học, còn **tọa độ** chỉ xác định ô dữ liệu phải tác động.

### 8.1. Sai tọa độ khi truy cập mảng

`get(values,-1)` không thể hợp lệ chỉ vì accessModeType là `(int[],int)int`. JVM vẫn phải kiểm tra **tọa độ cụ thể** và ném `ArrayIndexOutOfBoundsException` cho index không hợp lệ; array `null` có thể ném `NullPointerException`. `MethodType` mô tả shape, không gói điều kiện phạm vi của giá trị index.

## 9. Lab 4 — mảng nhiều chiều, ByteBuffer views và erasure

Tạo **`VarHandleEdgeLab.java`**:

```java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;
import java.nio.ByteOrder;
import java.util.List;

public class VarHandleEdgeLab {
    static class GenericBox {
        List<String> words;
    }

    static final class Box {
        final int constant = 5;
    }

    public static void main(String[] args) throws ReflectiveOperationException {
        VarHandle twoD = MethodHandles.arrayElementVarHandle(String[][].class);
        VarHandle bytes = MethodHandles.byteArrayViewVarHandle(
                int[].class, ByteOrder.nativeOrder());
        VarHandle buffer = MethodHandles.byteBufferViewVarHandle(
                int[].class, ByteOrder.nativeOrder());
        VarHandle generic = MethodHandles.lookup().findVarHandle(
                GenericBox.class, "words", List.class);
        VarHandle bools = MethodHandles.arrayElementVarHandle(boolean[].class);
        VarHandle doubles = MethodHandles.arrayElementVarHandle(double[].class);
        VarHandle readOnly = MethodHandles.lookup().findVarHandle(
                Box.class, "constant", int.class);

        System.out.println("2D.varType=" + twoD.varType().getTypeName());
        System.out.println("2D.coordinates=" + twoD.coordinateTypes());
        System.out.println("byteView.varType=" + bytes.varType().getTypeName());
        System.out.println("byteView.coordinates=" + bytes.coordinateTypes());
        System.out.println("bufferView.varType=" + buffer.varType().getTypeName());
        System.out.println("bufferView.coordinates=" + buffer.coordinateTypes());
        System.out.println("generic.varType=" + generic.varType().getTypeName());
        System.out.println("bool.ADD=" +
                bools.isAccessModeSupported(VarHandle.AccessMode.GET_AND_ADD));
        System.out.println("bool.BITWISE=" +
                bools.isAccessModeSupported(VarHandle.AccessMode.GET_AND_BITWISE_OR));
        System.out.println("double.ADD=" +
                doubles.isAccessModeSupported(VarHandle.AccessMode.GET_AND_ADD));
        System.out.println("double.BITWISE=" +
                doubles.isAccessModeSupported(VarHandle.AccessMode.GET_AND_BITWISE_OR));
        System.out.println("readonly.modeType=" +
                readOnly.accessModeType(VarHandle.AccessMode.GET_AND_ADD));
        System.out.println("getMode.name=" + VarHandle.AccessMode.GET.methodName());
    }
}
```

```sh
javac --release 21 -Xlint:all VarHandleEdgeLab.java
java VarHandleEdgeLab
```

**Stdout:**

```text
2D.varType=java.lang.String[]
2D.coordinates=[class [[Ljava.lang.String;, int]
byteView.varType=int
byteView.coordinates=[class [B, int]
bufferView.varType=int
bufferView.coordinates=[class java.nio.ByteBuffer, int]
generic.varType=java.util.List
bool.ADD=false
bool.BITWISE=true
double.ADD=true
double.BITWISE=false
readonly.modeType=(Box,int)int
getMode.name=get
```

**Phân tích:**

1. `String[][]`: phần tử được VarHandle nhìn thấy là một `String[]`; chỉ số duy nhất xác định **một mảng con**.
2. `byte[]`/`ByteBuffer` views: `T` vẫn là `int`, tọa độ đầu thay đổi theo nơi lưu bytes; cùng `(C,int)` suffix nhưng khác parameter type đầu và có thêm ràng buộc alignment/endianness.
3. `GenericBox.words` khai báo `List<String>`, nhưng `varType()` là **`List.class`** sau type erasure. `VarHandle` không giữ type argument `String` dưới dạng một runtime variable type riêng. Nếu cần generic metadata, đọc `Field.getGenericType()` từ declaration bằng Reflection.
4. `boolean` hỗ trợ bitwise update nhưng không numeric add; `double` hỗ trợ numeric add nhưng không bitwise update trên field/array element thông thường.
5. `readOnly.accessModeType(GET_AND_ADD)` vẫn trả **`(Box,int)int`**, dù field `final` và mode numeric update không được hỗ trợ. Đây là minh chứng cho việc **signature ≠ support**.

## 10. Các memory modes khác nhau nhưng chữ ký giống nhau

Đối với cùng một `VarHandle` có `T` và `CT` cố định:

- `get`: plain read, ít ràng buộc ordering xuyên thread.
- `getOpaque`: opaque read, cung cấp coherence/order riêng cho cùng variable theo quy tắc JMM; mạnh hơn plain ở khía cạnh tương ứng.
- `getAcquire`: acquire read, dùng trong protocol có release write phù hợp.
- `getVolatile`: volatile read, có semantics volatile mạnh hơn.
- `set`: plain write; `setOpaque`: opaque write; `setRelease`: release write; `setVolatile`: volatile write.
- Các atomic update modes có hậu tố `Acquire`/`Release` khác nhau về memory effects; không phải tất cả đều bảo đảm cùng ordering như phiên bản plain-named hoặc phiên bản volatile.
- `compareAndSet` có semantics cập nhật nguyên tử theo hợp đồng; `weakCompareAndSet*` có thể thất bại giả; `compareAndExchange*` trả witness trước khi cập nhật.

**Nhưng tất cả read modes vẫn là `(C)T`**, và mọi write modes vẫn là `(C,T)void`. Không thể nhìn `MethodType` để xác định **memory ordering**. Muốn biết ordering, bạn phải giữ cả **AccessMode enum** được chọn.

Lưu ý rằng `get`/`set` đơn thuần trên `long`/`double` có một số bảo đảm atomicity theo platform và factory; `getVolatile` và các atomic modes khác có quy tắc riêng. Không dùng sự giống nhau của signature để khẳng định các chế độ có cùng tính chất luồng.

### 10.1. Khi chọn acquire/release

Một cặp `setRelease` và `getAcquire` có thể hữu ích cho protocol publish/consume đã được thiết kế đúng với synchronization/order cần thiết; **một thread** trong Lab 2 chỉ kiểm tra giá trị kết quả, không chứng minh visibility giữa các threads. Cần thiết kế invariant, điều kiện retry và dữ liệu được publish. Nếu bài toán chỉ cần biến đếm nguyên tử, hãy dùng `getAndAdd`/CAS theo yêu cầu, hoặc cân nhắc `AtomicInteger`/`AtomicLong` vốn dễ đọc hơn.

## 11. `MethodType`, signature-polymorphic invocation và toMethodHandle

`VarHandle` access-mode methods là **signature-polymorphic**. Khai báo trong reflection có thể trông như nhận `Object...`, nhưng bytecode ở call site biểu diễn **kiểu thực tế** của các tọa độ/value và kiểu trả về. Trình biên dịch dựa trên kiểu tham số/cast tại điểm gọi; khi chạy, JVM so với `accessModeType` của handle.

### 11.1. Vì sao nhiều ví dụ cần cast ở kết quả?

```java
// Minh họa trong phạm vi có Counter counter và Box box.
int oldValue = (int) counter.getAndAdd(box, 1);
boolean changed = counter.compareAndSet(box, 1, 2);
counter.set(box, 3);
```

- `(int)` khiến call site kỳ vọng return primitive `int`, phù hợp với mode `GET_AND_ADD` trên biến kiểu `int`.
- `compareAndSet` trả primitive `boolean`, nên gán vào `boolean` là hình thức phù hợp.
- `set` có return `void`, thường gọi dạng statement. Dùng như một biểu thức có kiểu trả về không phù hợp với API mode sẽ thất bại.
- Sai số lượng tọa độ, sai kiểu receiver, sai số value arguments hoặc sai return type ở chế độ exact có thể dẫn đến `WrongMethodTypeException`.

Đừng chỉ đọc signature hiển thị bằng `Class.getDeclaredMethods()` rồi kết luận rằng các mode luôn nhận một `Object[]` thật. Reflection thấy lớp phương thức placeholder của signature polymorphism; gọi placeholder qua `Method.invoke` không tạo một VarHandle access hợp lệ. Hãy dùng trực tiếp access mode, `accessModeType`, `toMethodHandle` hoặc các invokers dành riêng cho VarHandle.

### 11.2. Bound MethodHandle và unbound invoker

`vh.toMethodHandle(mode)` trả **MethodHandle đã bound vào `vh`**. Vì đã có receiver VarHandle bên trong, handle này có cùng `MethodType` với `vh.accessModeType(mode)`. Nó nhận các tọa độ và value arguments như mode tương ứng.

Ngược lại, `MethodHandles.varHandleInvoker(mode, type)` hoặc `varHandleExactInvoker(mode, type)` tạo **invoker không bound**; chúng cần thêm một tham số `VarHandle` ở đầu khi gọi. Đừng áp công thức này nhầm cho `toMethodHandle`.

Nếu sử dụng `vh.withInvokeExactBehavior()`, các lời gọi mode trên VarHandle mới yêu cầu chữ ký tại call site phù hợp chính xác với `accessModeType`. `vh.withInvokeBehavior()` chọn cách invocation có conversions tương ứng với `MethodHandle.invoke`. Hai phương thức không thay định nghĩa biến/tọa độ; đó là lựa chọn **cách kiểm tra và thích nghi kiểu của lời gọi**, cần đồng nhất với thiết kế API.

### 11.3. Loại ngoại lệ và nguyên nhân

| Exception | Dấu hiệu thường gặp | Điều tra |
| --- | --- | --- |
| `WrongMethodTypeException` | Call-site type không tương thích access mode type, đặc biệt trong exact behavior | In `accessModeType`, kiểm tra prefix tọa độ, suffix values, return cast. |
| `UnsupportedOperationException` | Mode không được hỗ trợ, ví dụ write vào `final` hoặc getAndAdd với reference | Kiểm tra `isAccessModeSupported(mode)`, type biến và factory. |
| `ClassCastException` | Có thể phát sinh khi ép kiểu reference sau conversion hợp lệ nhưng object sai kiểu | Kiểm tra runtime type, cast và nơi giữ VarHandle. |
| `NullPointerException` | Receiver/array coordinate null | Kiểm tra object/mảng trước khi truy cập. |
| `ArrayIndexOutOfBoundsException` | Array index âm/vượt chiều dài | Kiểm tra index so với array length. |
| `IndexOutOfBoundsException` | ByteBuffer view offset ngoài giới hạn | Kiểm tra buffer limit và số byte của view type. |
| `IllegalStateException` | Byte view access có alignment không phù hợp cho mode mạnh hơn get/set | Căn chỉnh offset, kiểm tra alignment và factory. |
| `ReadOnlyBufferException` | Ghi vào `ByteBuffer` read-only | Kiểm tra `isReadOnly()` và thiết kế dữ liệu. |
| `NoSuchFieldException` / `IllegalAccessException` | Tạo VarHandle bằng Lookup với tên/type/access không đúng | Kiểm tra declaring class, field type, access modifier, module permissions. |

`WrongMethodTypeException` là lỗi **hợp đồng chữ ký**, `UnsupportedOperationException` là lỗi **hỗ trợ mode**. Cả hai xảy ra trong vùng API tương tự nhưng yêu cầu phương pháp sửa khác hẳn nhau.

## 12. Cách kiểm tra Type và support một cách hệ thống

Khi nhận `VarHandle` từ plugin, mapper hoặc metadata, kiểm tra theo đúng thứ tự:

```text
[1] Có VarHandle hợp lệ và có quyền sử dụng?
     |
[2] varType(): T là primitive/reference/array nào?
     |
[3] coordinateTypes(): CT có bao nhiêu phần tử, thứ tự?
     |
[4] Chọn AccessMode: GET/SET/CAS/GET_AND_ADD/...
     |
[5] accessModeType(mode): MethodType kỳ vọng
     |
[6] isAccessModeSupported(mode): được hỗ trợ?
     |
[7] Kiểm tra coordinate values thực tế: null, index, alignment...
     |
[8] Invoke với đúng chữ ký, quan sát return & exception
```

Đừng suy luận support từ tên mode hoặc từ việc call compile thành công. Hãy xem `accessModeType` để xây adapter có kiểu chính xác, rồi kiểm tra `isAccessModeSupported` trước khi thi hành nếu mode được chọn động.

Mẫu code duyệt **toàn bộ enum modes** trong một chương trình đã có `VarHandle vh` (đây là **helper minh họa**, không phải chương trình Java độc lập):

```java
for (VarHandle.AccessMode mode : VarHandle.AccessMode.values()) {
    System.out.printf(
            "%-34s %-12s %s%n",
            mode,
            vh.isAccessModeSupported(mode),
            vh.accessModeType(mode)
    );
}
```

Mẫu này hữu ích để làm bảng tra trong lúc debug. Tuy nhiên kết quả `true` không thay thế logic kiểm tra **coordinate value** (ví dụ ByteBuffer alignment tại index cụ thể). Với mode memory-ordering, hãy ghi rõ mode bên cạnh method type để tránh nhầm `GET` với `GET_VOLATILE`.

### 12.1. Dùng công thức để tự suy ra chữ ký

Giả sử `VarHandle` cho `long[]`:

- `T = long`, `C = (long[], int)`.
- `GET`: `(long[],int)long`.
- `SET_RELEASE`: `(long[],int,long)void`.
- `COMPARE_AND_SET`: `(long[],int,long,long)boolean`.
- `COMPARE_AND_EXCHANGE_ACQUIRE`: `(long[],int,long,long)long`.
- `GET_AND_ADD_RELEASE`: `(long[],int,long)long`.
- `GET_AND_BITWISE_OR`: `(long[],int,long)long`.

Giả sử `VarHandle` cho static `String` field:

- `T = String`, `C = ()`.
- `GET_OPAQUE`: `()String`.
- `SET_VOLATILE`: `(String)void`.
- `COMPARE_AND_SET`: `(String,String)boolean`.
- `GET_AND_SET`: `(String)String`.
- `GET_AND_ADD`: **vẫn có dạng** `(String)String` nhưng thường **unsupported**. Đây là ví dụ cần đồng thời dùng `isAccessModeSupported`.

## 13. Các ngộ nhận thường gặp

| Ngộ nhận | Vì sao sai | Cách hiểu đúng |
| --- | --- | --- |
| `varType()` là kiểu class chứa field | Field `int` của `Box` có variable type `int` | `Box` là tọa độ, `int` là giá trị. |
| Static field cần một receiver object | Static field thuộc class nhưng không cần instance coordinate | `coordinateTypes()` là danh sách rỗng. |
| Array 2D có sẵn hai int coordinates | Array-element VarHandle truy cập **một phần tử của outer array** | `String[][]` cho variable `String[]` và coordinates `(String[][],int)`. |
| `accessModeType` cho biết mode dùng được | Type chỉ mô tả chữ ký | Dùng `isAccessModeSupported` và kiểm tra giá trị tọa độ thực tế. |
| `GET` và `GET_VOLATILE` có MethodType khác nhau | Cùng prefix CT, return T | Khác memory semantics, không khác signature. |
| Compare-and-exchange trả boolean như CAS | Return type của exchange là `T` | Trả witness, có thể đối chiếu expected. |
| `getAndAdd` trả giá trị mới | Nhóm get-and-update trả giá trị cũ | Giá trị mới được lưu ở biến. |
| `String` field có thể dùng `getAndAdd` | Không phải numeric type | Type có nhưng mode unsupported. |
| `boolean` không có bitwise updates vì không phải số | Boolean hỗ trợ bitwise trên field/array element | Numeric add không được hỗ trợ. |
| `ByteBuffer` view index là số thứ tự phần tử `int` | View index là byte offset | Kiểm tra alignment và số byte khả dụng. |
| `List<String>` có varType riêng | Generic type arguments bị erase | `varType()` là raw `List.class`; dùng Reflection để đọc generic signature khai báo. |
| Lấy `toMethodHandle` thì cần truyền `VarHandle` làm đối số | Bound handle đã giữ vh | Chỉ truyền tọa độ + value. |
| Nhìn `Class.toString()` có thể nhận ra mọi type an toàn | Class names không mã hóa generic arguments và các quy tắc runtime | Dùng `Class<?>` identity và `MethodType` thực. |

Một hạn chế tinh tế: khi tạo VarHandle thành công, **quyền truy cập field** đã được kiểm tra tại thời điểm creation. VarHandle là một *capability* có thể truyền cho caller khác; nếu bạn phát tán nó, người nhận có thể sử dụng nó theo access modes được hỗ trợ. Vì vậy tránh công khai handle đến private/sensitive mutable state trong plugin không tin cậy.

## 14. Bài tập thực hành và tiêu chí kiểm tra

**Bài 1 – Bóc tách instance/static/array.** Tạo ba handle cho `int` instance field, `static long` field và `String[]` element. Ghi riêng `T`, `CT`, rồi tự suy ra `GET`, `SET`, `COMPARE_AND_SET` trước khi in `accessModeType`. Giải thích vì sao static field không có receiver.

**Bài 2 – Complete mode table.** Dùng helper `AccessMode.values()` ở mục 12 để in mọi mode cho `int` field; nhóm các method types bằng nhau. Vì sao `GET_ACQUIRE` có cùng chữ ký với `GET_VOLATILE` nhưng không thể thay thế tùy ý trong protocol đa luồng?

**Bài 3 – Không nhầm với support.** Tạo `final int x`, đọc `accessModeType(SET)` rồi kiểm tra `isAccessModeSupported(SET)`. Nêu kỳ vọng của `set` nếu vẫn gọi. Lặp lại với `String[]` và `GET_AND_ADD`.

**Bài 4 – Atomic return.** Trong Lab 2, trước mỗi lời gọi hãy ghi giá trị `count` và expected output. Đổi expected CAS cho sai, chẳng hạn `compareAndSet(box,999,18)`; giải thích vì sao boolean false và biến không đổi. Phân biệt `compareAndExchange` vì nó trả witness.

**Bài 5 – Array index.** Với `arrayElementVarHandle(long[].class)`, suy ra `getAndAdd` type `(long[],int,long)long`. Thử truy cập index ngoài phạm vi rồi đọc exception; tách riêng lỗi chữ ký và lỗi tọa độ.

**Bài 6 – Multidimensional array.** Với `String[][]`, dự đoán variable type và coordinate list. Lấy một `String[]` ở vị trí outer index, rồi dùng VarHandle khác để truy cập phần tử `String` trong mảng con. Tại sao một VarHandle ban đầu không cần `(String[][],int,int)String`?

**Bài 7 – Byte views.** So `byteArrayViewVarHandle(int[].class, order)` với `arrayElementVarHandle(int[].class)`. In `varType()` và `coordinateTypes()`; giải thích tại sao cùng T nhưng coordinate container khác và view cần xử lý byte order/alignment.

**Bài 8 – Invoke-exact.** Trong Lab 2, thay `Object ignored = exact.get(box)` bằng `int value = (int) exact.get(box)` và so kết quả. Giải thích vai trò kiểu trả về tại call site. Không bỏ `withInvokeExactBehavior` khỏi thí nghiệm vì nó quyết định lý do thất bại.

**Bài 9 – Adapter có nhiều modes.** Viết helper nhận một `VarHandle` và enum mode, trả một mô tả chứa `varType`, `coordinateTypes`, `accessModeType`, `isAccessModeSupported`. Mỗi record cần giữ tên mode để không đánh đồng các memory semantics cùng signature.

### Tự đánh giá hoàn thành

- [ ] Phân biệt được **T** (kiểu giá trị) và **CT** (tọa độ để tìm vị trí biến).
- [ ] Suy ra được MethodType cho cả read/write/CAS/exchange/get-and-update mà không đảo thứ tự tham số.
- [ ] Giải thích được `getAndAdd` và `compareAndExchange` trả **giá trị trước cập nhật**, khác CAS boolean.
- [ ] Biết vì sao cùng chữ ký không có nghĩa cùng memory ordering.
- [ ] Chứng minh bằng lab rằng `accessModeType` tồn tại cả với unsupported mode.
- [ ] Chạy được bốn lab, đối chiếu stdout và phân loại lỗi runtime đúng nguyên nhân.
- [ ] Nhận diện array multi-dimension, ByteBuffer byte-offset và type erasure của generic field.

## 15. Tài liệu chính thức để đối chiếu Java 21

- [Java SE 21 – VarHandle](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/VarHandle.html): `varType()`, `coordinateTypes()`, `accessModeType()`, `isAccessModeSupported()`, các access mode methods và memory semantics.
- [Java SE 21 – VarHandle.AccessMode](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/VarHandle.AccessMode.html): tên enum, `methodName()` và các mode có trong JDK.
- [Java SE 21 – MethodHandles](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/MethodHandles.html): `arrayElementVarHandle`, `byteArrayViewVarHandle`, `byteBufferViewVarHandle`, varHandle invokers.
- [Java SE 21 – MethodHandles.Lookup](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): `findVarHandle`, `findStaticVarHandle` và quyền truy cập.
- [Java SE 21 – MethodType](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/MethodType.html): biểu diễn return/parameter types.
- [Java SE 21 – WrongMethodTypeException](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/WrongMethodTypeException.html): phân biệt lỗi chữ ký với lỗi mode không hỗ trợ.

**Điểm cần nhớ:** `VarHandle` trả lời ba câu hỏi độc lập nhưng liên kết chặt: **Giá trị có kiểu gì?** (`varType`), **tìm biến ở đâu?** (`coordinateTypes`), **mode này đòi những tham số và trả kiểu gì?** (`accessModeType`). Chỉ sau khi kiểm tra **mode có được hỗ trợ** và **tọa độ thực tế hợp lệ**, bạn mới có đủ thông tin để sử dụng handle đúng đắn trong ứng dụng.
