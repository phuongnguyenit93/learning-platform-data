# Bố trí đối tượng và mảng là chi tiết triển khai, không phải cam kết của Java

## 1. Điều quan trọng nhất cần ghi nhớ

Trong Java, bạn có thể khai báo:

```java
final class Sample {
    byte flag;
    long sequence;
    Object child;
}

Sample value = new Sample();
int[] numbers = new int[3];
```

Từ chương trình này, ngôn ngữ Java **bảo đảm những điều có thể quan sát qua API/ngữ nghĩa**: `flag` mặc định bằng `0`, `sequence` bằng `0L`, `child` bằng `null`, `numbers.length == 3`, các phần tử `numbers` ban đầu bằng `0`, và các biến reference có thể cùng trỏ một object.

Nhưng Java **không hứa** rằng `Sample` luôn dùng đúng 32 byte, `flag` luôn nằm tại offset 12, `sequence` nằm sau `flag`, array header luôn 16 byte, object reference luôn dài 4 hay 8 byte, hoặc mọi garbage collector phải đặt object tại cùng một địa chỉ vật lý suốt vòng đời.

**JVMS `2.7 — Representation of Objects** xác định JVM **không bắt buộc một cấu trúc nội bộ cụ thể cho object**. Những sơ đồ kiểu **mark word + class pointer + fields + padding** thường dùng khi giải thích **HotSpot**, chứ không phải hợp đồng nhị phân áp dụng cho mọi JVM/kiến trúc/JDK.

Đây là phạm vi chính của bài:

- Tách **ngữ nghĩa do Java/JVMS bảo đảm** khỏi **lựa chọn bố trí trong HotSpot**.
- Hiểu object header, class metadata pointer, field placement, alignment/padding, compressed references.
- Hiểu **array object**, length, element storage và mảng nhiều chiều là **mảng của các mảng**.
- Hiểu vì sao những con số 12, 16, 24, 32 byte chỉ là **ví dụ của một cấu hình**.
- Nhận ra thay đổi của HotSpot, gồm **compact object headers** từ JDK 24/25 và mặc định mới trên JDK 27.
- Biết dùng **JOL (Java Object Layout)**, `Instrumentation.getObjectSize`, JFR/heap tools với giới hạn đo lường rõ ràng.
- Tránh hardcode object offsets hoặc dựa vào internal class layout trong Java application logic.

## 2. Ba tầng phải phân biệt: Java, JVMS và HotSpot

| Tầng | Quy định hoặc cung cấp gì? | Ví dụ |
| --- | --- | --- |
| **Java Language Specification (JLS)** | Kiểu, giá trị mặc định, `final`, field access, arrays, thứ tự đánh giá, Java Memory Model | `new int[2]` có length 2; phần tử mặc định 0 |
| **Java Virtual Machine Specification (JVMS)** | Reference types, bytecode, runtime data areas, định nghĩa class/array, ngữ nghĩa instruction | `getfield`, `iaload`, `arraylength` và kiểm tra tương ứng |
| **HotSpot implementation** | Cách biểu diễn object tại runtime, headers, offsets, compressed pointers, GC/JIT, field packing | Mark word, Klass pointer, object alignment, JOL output |

### 2.1. Hợp đồng phía Java

Nếu một class có field `int x`, Java yêu cầu khi chưa được gán cụ thể, field này có default value `0`. Chương trình có thể đọc `obj.x` theo các quy tắc truy cập kiểu, quyền truy cập, initialization và Java Memory Model.

Java **không cung cấp một cú pháp tiêu chuẩn** kiểu `addressOf(obj.x)` để hỏi offset byte của field trong heap. Hai fields đặt cạnh nhau trong source không có nghĩa runtime phải đặt cạnh nhau trong memory.

### 2.2. Hợp đồng phía JVM

Bytecode `getfield` chỉ định field thông qua symbolic reference trong constant pool, không yêu cầu class file mã hóa một offset byte cứng của field trong object. JVM có trách nhiệm giải quyết tham chiếu và truy cập trường hợp lệ theo ngữ nghĩa.

Bytecode `iaload` đọc phần tử `int[]` theo array reference + index. Spec yêu cầu phát sinh `NullPointerException`/`ArrayIndexOutOfBoundsException` trong điều kiện tương ứng, nhưng không buộc JVM dùng một cách tính địa chỉ máy cố định có thể quan sát từ mã Java.

### 2.3. Tầng HotSpot

HotSpot thường tổ chức object trong heap với header và phần dữ liệu fields/elements, tính kích thước theo alignment và chính sách GC. Những chi tiết này có thể thay đổi khi:

- Đổi từ JDK 17 sang JDK 25/27.
- Bật/tắt **compressed oops**, **compressed class pointers**, **compact object headers**.
- Đổi `ObjectAlignmentInBytes` hoặc kiến trúc 32-bit/64-bit.
- Đổi chiến lược field layout, GC, JIT hoặc nội bộ runtime.
- Sử dụng các loại class đặc thù, chẳng hạn arrays, hidden classes, generated classes.

**Hãy gắn mọi con số layout với ít nhất JDK build, VM, kiến trúc và các cờ liên quan.**

## 3. Đối tượng HotSpot: header, instance data và padding

Để thảo luận về **tính khả chuyển**, dùng sơ đồ cấp cao của một **HotSpot 64-bit ở chế độ classic header**:

~~~text
[ runtime header ] [ các instance fields ] [ khoảng trống do alignment nếu có ]
~~~

Object header có thể chứa **mark word** và biểu diễn **class/Klass pointer** phù hợp. Mark word hỗ trợ thông tin quản lý trạng thái như locking, hash hoặc tuổi GC tùy VM; nó **không** là Java field và **không** phải địa chỉ cố định của object. Một số HotSpot modes biểu diễn header gọn hơn, vì thế sơ đồ trên **không phải cấu trúc byte-level bắt buộc**.

Các instance fields bao gồm fields được kế thừa, có thể có internal gaps và được runtime bố trí theo các quy tắc triển khai. Dù HotSpot reorder/pack fields, mọi biểu thức `obj.field` phải giữ đúng semantics Java. Chẳng hạn, hai field cùng tên trong superclass/subclass bị *hiding* vẫn là hai fields logic khác nhau; layout không được làm chúng nhập thành một.

**Nơi kiểm chứng số byte thực:** bài đo layout ngay trước bài này giải thích mark word/Klass pointer, field offsets, padding và JOL/Instrumentation chi tiết. Ở đây ta chỉ dùng chúng để nhận diện **điều không được giả định khi nâng JVM**.

## 4. Object header truyền thống: hiểu số 12, 16 byte có điều kiện

Trong cấu hình HotSpot 64-bit **classic header, JDK 17**, ví dụ thường gặp là:

~~~text
mark word:                   8 bytes
compressed Klass pointer:    4 bytes
------------------------------
classic header:             12 bytes

Nếu class pointer không nén:
mark word:                   8 bytes
Klass pointer:               8 bytes
------------------------------
classic header:             16 bytes
~~~

Đây chỉ là **những ví dụ có điều kiện**, không phải hợp đồng Java/JVMS. Shallow instance size còn phụ thuộc fields, các gaps và `ObjectAlignmentInBytes`. Ví dụ nếu raw size là 13 byte và alignment là 8 byte, shallow size minh họa là `alignUp(13,8)=16`; nếu raw size 17, kết quả là 24. Không được dùng một phép cộng field widths từ source làm phép đo offset chính xác.

Với **Compact Object Headers**, HotSpot có thể dùng header nhỏ hơn đáng kể; theo OpenJDK JEP 450/519/534, quá trình triển khai feature thay đổi giữa JDK 24 (experimental), 25 (product, opt-in) và 27 (mặc định). Vì vậy số “12 byte” không được hardcode trong serializer, Unsafe code, native ABI hoặc benchmark đa phiên bản.

## 5. Field declaration order không phải memory layout contract

Java source:

```java
class Packet {
    byte kind;
    long id;
    boolean valid;
    Object payload;
    int version;
}
```

Một người đọc có thể tưởng rằng VM phải đặt fields theo `kind → id → valid → payload → version`. Không có quy định Java yêu cầu thứ tự địa chỉ như vậy.

Những điều vẫn được bảo đảm:

- `packet.kind` truy cập đúng giá trị của field `kind`.
- `packet.id` truy cập đúng giá trị của `id`.
- Compiler/JVM áp dụng visibility, `final` và memory semantics như đặc tả.
- Reflection cung cấp thông tin fields theo các API, nhưng thứ tự phần tử do `getDeclaredFields()` trả về **không phải bằng chứng về field offsets** và API không bảo đảm một thứ tự khai báo có ý nghĩa.

Những điều **không** được bảo đảm:

- Field `id` nằm sau `kind` đúng 1 byte.
- Field `valid` không có padding bên cạnh.
- `payload` reference luôn là 8 byte trên VM 64-bit.
- Thêm một field `boolean` nhất định tăng instance size đúng 1 byte.
- Đổi thứ tự khai báo fields trong source nhất định làm layout tương ứng đổi.

### 5.1. Khi nào field order trở thành vấn đề thật?

Nếu bạn đang triển khai **binary protocol**, **file format**, **memory-mapped structure** hoặc **native ABI**, hãy dùng một format/representation được định nghĩa tường minh: ví dụ `ByteBuffer` với byte order xác định, `DataOutputStream`, serialization format, hay Foreign Function & Memory API khi tương thích JDK mục tiêu.

**Không** dùng trực tiếp memory layout của Java object làm schema lưu file hay network packet. Layout object có thể thay đổi khi nâng JDK, đổi GC, bật compact headers hoặc chạy JVM vendor khác.

### 5.2. `final` không đồng nghĩa field được cố định vị trí byte

`final` có các quy tắc Java riêng về gán và visibility. Nó không cam kết trường `final long id` phải nằm ở một offset byte cụ thể hoặc có cùng address với bản build trước.

## 6. Object reference và field reference: compressed oops

Java reference có **ngữ nghĩa chỉ tới object**, không phải một pointer arithmetic API. HotSpot 64-bit có thể dùng **compressed ordinary object pointers** (compressed oops) cho nhiều reference fields/array slots; một encoded reference thường nhỏ hơn native machine pointer. Riêng **compressed class pointer** là cơ chế biểu diễn tham chiếu tới runtime class metadata trong header: hai thứ phục vụ **hai loại dữ liệu khác nhau**.

~~~text
Java reference field  ------> Java heap object       (oop)
HotSpot object header ------> Klass/class metadata   (class pointer)
~~~

Với mode classic JDK 17, `UseCompressedOops`, `UseCompressedClassPointers` và `ObjectAlignmentInBytes` có thể ảnh hưởng width/alignment. **Không giả định flags tồn tại hoặc có ý nghĩa giống hệt ở release mới**: chẳng hạn `UseCompressedClassPointers` đã trở thành obsolete trên HotSpot JDK 27, theo JDK 27 release notes. Trước khi đọc flags, chạy `java -version` và đối chiếu tài liệu đúng JDK build.

Mã Java dùng `a == b` vẫn so cùng object identity kể cả GC di chuyển object, reference nén hoặc giải nén. Bài compressed oops kế tiếp phân tích riêng encoding, shift/base và các ngưỡng bộ nhớ, tránh nhân đôi phép tính tại đây.

## 7. Alignment và padding: vì sao thêm field không đồng nghĩa tăng shallow size?

**Alignment** là ràng buộc layout của HotSpot, không phải Java API contract. Khi cần căn shallow size lên bội số của 8 byte, ví dụ minh họa:

~~~text
raw bytes = 17, alignUp(17, 8) = 24
raw bytes = 22, alignUp(22, 8) = 24
~~~

Do đó một field mới có thể chiếm khoảng trống đã có mà không tăng shallow size. Ngược lại, thêm một field có thể vượt ranh giới alignment và làm object tăng thêm một block, không chỉ số byte của field. **Internal padding** nằm giữa các thành phần do placement/alignment; **tail padding** thường nằm cuối object để làm tròn tổng size.

Con số `raw bytes` chỉ hợp lệ khi đã biết offsets từ JVM/tool; không tính bằng cách đoán field declaration order. Muốn tối ưu memory, đo bằng JOL/Instrumentation/heap profiler trên đúng release thay vì thiết kế phụ thuộc vào offsets cụ thể.

## 8. Array là object có hợp đồng Java riêng, không chỉ vùng byte

Java bảo đảm **array identity, runtime type, length cố định và kiểm tra chỉ số**, chẳng hạn:

~~~java
int[] scores = new int[3];
String[] names = new String[3];
System.out.println(scores.length); // 3
System.out.println(scores[0]);     // 0
System.out.println(names[0]);      // null
~~~

Mỗi câu `new int[3]` hay `new String[3]` cấp **một array object** theo ngữ nghĩa; `String[]` chứa **các reference slots**, không tự tạo ba String objects. Index ngoài bounds ném `ArrayIndexOutOfBoundsException`; dereference null array có thể ném `NullPointerException`. Arrays implement `Cloneable` và `Serializable` theo quy tắc Java.

Trong **HotSpot classic header**, một mảng thường có runtime metadata/header, **length** và vùng elements cùng padding. Nhưng Java không chỉ định độ lớn header, vị trí length, offset element đầu tiên hoặc contiguous native layout thành **public ABI**. Primitive elements và reference slots có semantics khác nhau; tổng memory giữ bởi `Object[]` không chỉ bằng shallow size của mảng nếu các referents sống riêng.

Bài học layout chuyên sâu ở hàng trước cho ví dụ `int[]`/`Object[]` byte arithmetic có điều kiện. Ở đây câu hỏi cốt lõi là: **cùng chương trình Java chạy đúng trên VM có physical array layout khác nhau không? Có.**

## 9. Ví dụ kích thước array trên HotSpot 64-bit JDK 17 truyền thống

Giả sử cụ thể **array base offset = 16 byte**, reference slots 4 byte, `int` slots 4 byte, alignment 8 byte, classic compressed header:

| Array | Phép tính minh họa | Shallow bytes |
| --- | --- | ---: |
| `new int[0]` | `alignUp(16 + 0×4, 8)` | 16 |
| `new int[1]` | `alignUp(16 + 1×4, 8)` | 24 |
| `new int[3]` | `alignUp(16 + 3×4, 8)` | 32 |
| `new Object[3]` | `alignUp(16 + 3×4, 8)` | 32 |

**Không phải kết quả cố định của Java SE.** Mỗi `Object[]` chỉ chứa reference slots; nếu phần tử trỏ tới một `byte[]` khác, mảng `byte[]` đó có shallow size riêng. Việc reference được dùng ở nhiều slots cũng **không tự nhân bản** object referent.

Ở JVM có compact headers, alignment khác hoặc representation khác, hãy đo lại bằng JOL/Instrumentation. Số đo mới không làm `arr.length` hoặc `arr[0]` thay đổi ngữ nghĩa.

## 10. Mảng nhiều chiều là mảng của các mảng

Java source:

```java
int[][] matrix = new int[2][3];
```

Ngữ nghĩa là một **mảng ngoài** dài 2, mỗi phần tử là reference tới một `int[]` dài 3:

```text
matrix (int[][])
   |
   +--> outer array length = 2
          |
          +--> row 0 → int[] length 3 : [0, 0, 0]
          |
          +--> row 1 → int[] length 3 : [0, 0, 0]
```

Trong mô hình Java, có **ít nhất ba array objects phân biệt theo nhận diện runtime**: outer array và hai inner arrays. Java **không yêu cầu** toàn bộ sáu primitive `int` của các hàng phải nằm trong **một khối bộ nhớ hình chữ nhật liên tục**.

```java
int[][] jagged = new int[2][];
jagged[0] = new int[] {1, 2};
jagged[1] = new int[] {3};
```

Hàng đầu dài 2, hàng sau dài 1. Java hỗ trợ cấu trúc **jagged/ragged arrays** vì mỗi phần tử của outer array là reference tới một array object độc lập.

### 10.1. `int[][]` không phải C-style `int[2][3]`

Trong ngôn ngữ native nhất định, mảng 2D có thể được lưu như một vùng liền khối theo row-major layout. Nhưng Java không cam kết mô hình tương đương. Việc đọc `matrix[i][j]` qua bytecode thể hiện hai bước truy cập mảng theo kiểu reference:

```text
aload ...  (đọc reference outer array)
iload ...  (index i)
aaload     (đọc reference tới row)
iload ...  (index j)
iaload     (đọc int từ row)
```

Đây là sơ đồ nhóm opcode, không phải output cố định của một compiler. Có các null/bounds checks tương ứng từng tầng; HotSpot JIT có thể tối ưu khi chứng minh an toàn nhưng vẫn bảo toàn kết quả quan sát được.

### 10.2. Vấn đề hiệu năng của jagged arrays

Một mảng các mảng có thể:

- Tăng số object và overhead per-array headers.
- Làm truy cập dữ liệu phụ thuộc reference tới hàng.
- Có kích thước hàng linh hoạt và cho phép cấp phát thưa.
- Tạo tính cục bộ cache khác với một mảng primitive phẳng.

Muốn một layout logic phẳng, có thể dùng:

```java
int rows = 2;
int columns = 3;
int[] flat = new int[rows * columns];
flat[1 * columns + 2] = 9;
```

Đây là code minh họa **không phải file Java độc lập**. Mapping `flat[row * columns + col]` do ứng dụng kiểm soát về mặt index, nhưng **vẫn không biến địa chỉ vật lý của Java array thành API công khai**.

Nếu dùng công thức indexing, cần kiểm tra overflow của phép nhân và bounds của row/col khi dữ liệu lớn.

## 11. Compact object headers: thay đổi HotSpot qua các phiên bản JDK

Việc một bài cũ ghi “HotSpot object header luôn là 12 hoặc 16 bytes” cho thấy vì sao chủ đề này phải được gắn với phiên bản JVM.

- **JDK 17 (HotSpot truyền thống):** các sơ đồ 12-byte header (compressed class pointers) và 16-byte header (uncompressed) thường được dùng để giải thích.
- **JDK 24 — JEP 450:** giới thiệu **Compact Object Headers** dưới dạng **experimental feature**.
- **JDK 25 — JEP 519:** đưa compact object headers thành **product feature**, có thể bật bằng `-XX:+UseCompactObjectHeaders` trên HotSpot hỗ trợ; trong JDK 25 feature **không bật mặc định**.
- **JDK 27 — JEP 534:** compact object headers được **bật mặc định** trên cấu hình HotSpot hỗ trợ, với khả năng tắt bằng flag trong bản tương ứng.

Mục tiêu của compact headers là giảm chi phí header của object trên HotSpot 64-bit truyền thống xuống khoảng **8 byte**, thay đổi cách lưu thông tin trạng thái/kiểu object. Những chi tiết thực tế tùy VM/configuration và có thể tiếp tục phát triển.

### 11.1. Vì sao mốc JDK quan trọng?

Một công thức kiểu:

```text
object size = 12-byte header + fields + padding
```

có thể hợp lý như phép ước lượng cho **một bản JDK 17 HotSpot với compressed class pointers**, nhưng sai nếu được dùng như chân lý cho **mọi JDK 27 HotSpot**. Điều này minh họa tính **không portable** của kiến thức layout thấp.

### 11.2. Compact headers không đổi hợp đồng Java

Sau khi VM thay header:

- `obj.getClass()` vẫn trả đúng class runtime.
- `synchronized` vẫn tuân theo Java Memory Model và quy tắc monitor.
- `System.identityHashCode(obj)` vẫn có ngữ nghĩa đã đặc tả.
- `obj.field` vẫn đọc/ghi đúng field theo các quy tắc Java.
- Arrays vẫn có `length` và kiểm tra chỉ số.

Điều thay đổi là **cách VM biểu diễn trạng thái và metadata**, không phải việc Java bổ sung một thuộc tính `headerBytes` có thể gọi từ source.

### 11.3. Đọc flags theo JDK mục tiêu

Ví dụ trên HotSpot JDK 25 tương ứng:

```bash
java -XX:+UseCompactObjectHeaders -version
```

Trên HotSpot JDK 27 khi tính năng được hỗ trợ:

```bash
java -XX:-UseCompactObjectHeaders -version
```

Những câu lệnh là **lệnh khảo sát tùy phiên bản**, không chạy nguyên xi trên JDK 17 vì flag có thể không tồn tại. Trong ứng dụng thật hãy xem `java -version` và `java -XX:+PrintFlagsFinal -version` thay vì đoán cấu hình.

## 12. GC, địa chỉ và identity: “object nằm ở offset X” có thể chỉ đúng trong một thời điểm

Một garbage collector có thể **di chuyển object** trong heap khi compact/relocate. Khi đó một giá trị native address nếu ai đó lấy được qua công cụ nội bộ có thể thay đổi. Java references vẫn tiếp tục dẫn tới **object logic tương ứng** theo ngữ nghĩa JVM.

### 12.1. `==` cho reference không phải so sánh địa chỉ byte thô

Khi viết:

```java
Object a = new Object();
Object b = a;
System.out.println(a == b);
```

Kết quả là `true` vì cả hai reference chỉ tới **cùng object**. Đó là ngữ nghĩa reference identity, không buộc Java expose hay cố định một địa chỉ máy.

### 12.2. `identityHashCode` không phải địa chỉ object

`System.identityHashCode(obj)` trả một giá trị `int` theo hợp đồng của Java. Giá trị này:

- **Không là offset field**.
- **Không buộc bằng địa chỉ bộ nhớ**.
- **Không là định danh duy nhất tuyệt đối**: các object khác nhau có thể có cùng hash code.
- Có thể liên quan chi tiết implementation object-header/hash storage, nhưng ứng dụng không được dựa vào cách lưu nội bộ.

Không dùng `identityHashCode` để tính native pointers hoặc khẳng định GC di chuyển object hay không.

### 12.3. JIT có thể không materialize object trong mọi tình huống

HotSpot JIT có thể dùng escape analysis/scalar replacement trong những trường hợp tối ưu hóa để tránh một số allocation thực tế, trong khi code Java vẫn có biểu hiện ngữ nghĩa tương đương.

Vì vậy **“một lần viết `new` luôn tạo một heap object 16 byte nhìn thấy trên mọi heap snapshot”** không phải giả định tốt cho profiling. Cần phân biệt **allocation semantics** với cách runtime tối ưu ở một thời điểm.

## 13. Chương trình Java 17+ chứng minh semantic contract, không giả định layout

Tạo tệp **`ObjectLayoutContractDemo.java`**:

```java
import java.io.Serializable;
import java.util.Arrays;

public final class ObjectLayoutContractDemo {
    static final class Packet {
        byte kind;
        long id;
        Object payload;
    }

    public static void main(String[] args) {
        Packet first = new Packet();
        Packet alias = first;

        System.out.println("same object: " + (first == alias));
        System.out.println("default byte: " + first.kind);
        System.out.println("default long: " + first.id);
        System.out.println("default reference is null: "
                + (first.payload == null));

        int[] numbers = new int[3];
        System.out.println("array length: " + numbers.length);
        System.out.println("primitive defaults: "
                + Arrays.toString(numbers));

        int[] sameArray = numbers;
        sameArray[1] = 7;
        System.out.println("alias observes change: "
                + Arrays.toString(numbers));

        Object[] references = new Object[2];
        references[0] = first;
        System.out.println("reference slot 1 null: "
                + (references[1] == null));

        int[][] jagged = new int[2][];
        jagged[0] = new int[] {1, 2};
        jagged[1] = new int[] {3};

        System.out.println("outer length: " + jagged.length);
        System.out.println("row lengths: " + jagged[0].length
                + "," + jagged[1].length);
        System.out.println("rows are distinct objects: "
                + (jagged[0] != jagged[1]));

        System.out.println("array is Object: "
                + (numbers instanceof Object));
        System.out.println("array is Cloneable: "
                + (numbers instanceof Cloneable));
        System.out.println("array is Serializable: "
                + (numbers instanceof Serializable));
    }
}
```

Chạy bằng JDK 17 trở lên:

```bash
javac --release 17 ObjectLayoutContractDemo.java
java ObjectLayoutContractDemo
```

**Stdout chính xác:**

```text
same object: true
default byte: 0
default long: 0
default reference is null: true
array length: 3
primitive defaults: [0, 0, 0]
alias observes change: [0, 7, 0]
reference slot 1 null: true
outer length: 2
row lengths: 2,1
rows are distinct objects: true
array is Object: true
array is Cloneable: true
array is Serializable: true
```

### 13.1. Ví dụ trên chứng minh điều gì?

- Reference identity: `first == alias` là true.
- Field defaults: `byte` và `long` mặc định 0; reference mặc định null.
- Array `length` và primitive defaults.
- Aliasing: hai reference cùng trỏ một mảng, nên sửa qua alias quan sát được.
- Outer array có các inner arrays với độ dài khác nhau.
- Java arrays thuộc nhóm object và implement hai marker interfaces đặc biệt.

### 13.2. Ví dụ không chứng minh điều gì?

Nó **không** biết:

- Packet có shallow size bao nhiêu byte.
- `id` hay `payload` ở byte offset nào.
- Header của `Packet` là 8, 12 hay 16 byte.
- Các references đang được nén hay không.
- Địa chỉ RAM/native cụ thể của arrays.
- GC sẽ di chuyển hoặc giữ nguyên những objects ấy.

Chương trình có thể cho **cùng stdout** trên hai JVM với bố trí hoàn toàn khác nhau. Đó chính là tính di động được Java/JVM nhắm tới.

## 14. Dùng JOL để quan sát implementation hiện tại

**JOL — Java Object Layout** là công cụ OpenJDK cho phép khảo sát layout và shallow sizes của objects dưới các VM configurations khác nhau. Tài liệu nguồn: [OpenJDK JOL](https://openjdk.org/projects/code-tools/jol/).

Thông thường bạn có thể dùng JOL CLI:

```bash
java -jar jol-cli.jar internals java.lang.Integer
```

Trong câu lệnh trên, `jol-cli.jar` là tên giả định của JAR CLI đã được tải/xây dựng từ OpenJDK JOL; không có JAR này sẵn trong mọi JDK. Có thể cần đường dẫn thực tế theo phiên bản JOL của bạn. Nếu JOL đã được tích hợp vào build bằng dependency, có thể dùng API `ClassLayout.parseInstance(...)`.

### 14.1. Những phần thường có trong output JOL

```text
VM mode / pointer compression / object alignment
Object internals:
  OFFSET   SIZE   TYPE / DESCRIPTION
  ...
Instance size: ...
Space losses: ...
```

**Đây là hình dạng output minh họa**, không phải dữ liệu đo thực tế của chương trình ở trên.

Các dòng quan trọng:

- **VM mode:** kiến trúc và khả năng pointer encoding.
- **Object alignment:** số byte alignment của một cấu hình.
- **Offset:** vị trí field/header trong cách HotSpot/JOL xác định/suy luận.
- **Instance size:** shallow size dưới cấu hình tương ứng.
- **Space losses:** vùng padding theo cách công cụ tính.

Một số chế độ JOL có thể **suy luận/simulate** layout thay vì đọc địa chỉ vật lý tuyệt đối; phiên bản JOL phải tương thích với VM hiện tại, nhất là khi có compact object headers.

### 14.2. Không chuyển output JOL thành schema giao tiếp

Nếu JOL báo `Packet.id` có offset 16 trong HotSpot JDK 17, **không hardcode offset 16** vào file format, binary protocol hoặc code logic chung.

Một phép đo đúng ở cấu hình A không đồng nghĩa còn đúng ở cấu hình B. Việc đổi JDK, cờ alignment, compressed references hoặc fields/superclass có thể làm offsets và sizes thay đổi.

### 14.3. JOL đo shallow size, không tự động là tổng retained heap

Một object có thể chứa references tới nhiều objects khác. `ClassLayout.parseInstance(obj)` quan sát **một object**; muốn phân tích **object graph/retained memory**, cần thêm công cụ/phân tích phù hợp như JOL `GraphLayout`, heap dump analyzer hoặc profiler, và xử lý vấn đề **shared references**.

JOL cũng là công cụ diagnostic/học tập. Không nên dùng nó làm cơ chế runtime contract bắt buộc trong code business.

## 15. `Instrumentation.getObjectSize` đo gì và không đo gì?

Java Instrumentation API có phương thức:

```java
long size = instrumentation.getObjectSize(someObject);
```

Đây chỉ là **đoạn mã minh họa bên trong Java agent** có `Instrumentation` instance, không phải chương trình Java độc lập. API cần cách khởi động/attach agent hợp lệ; không có biến `instrumentation` tự xuất hiện trong Java thông thường.

Tài liệu API mô tả kích thước theo nghĩa **implementation-specific approximation of the amount of storage consumed by the specified object**. Vì vậy:

- Nó **không** phải toán tử Java `sizeof` portable.
- Nó **không** bao gồm toàn bộ những objects mà reference fields trỏ tới.
- Nó **không** nhất thiết mô tả native memory, thread stacks hay metadata.
- Nó không cố định kích thước theo class name cho mọi cấu hình JDK.

Dùng `Instrumentation.getObjectSize` để đo tương đối trên **môi trường đã ghi nhận**, không biến kết quả thành invariant của ứng dụng.

### 15.1. Vì sao `Runtime.totalMemory()` cũng không cho object size?

`Runtime.totalMemory()` và `freeMemory()` liên quan dung lượng heap do JVM quản lý, chịu ảnh hưởng GC, allocation buffer, background activity, JIT và VM ergonomics. Lấy chênh lệch trước/sau tạo **một object** thường quá nhiễu để kết luận size chính xác.

Để đo footprint của cấu trúc nhiều objects:

- Dùng JOL/JFR/heap dump/allocated-bytes profiler.
- Cân nhắc GC và escape analysis.
- Lặp phép đo với warm-up và workload đại diện.
- Ghi rõ version/flags.
- Phân biệt shallow size, retained size và tổng memory resident process.

## 16. `Unsafe`, field offsets và những rủi ro cần tránh

Một số code low-level có thể tìm offset của field thông qua API không được Java SE cam kết ổn định cho ứng dụng phổ thông (ví dụ một số phương thức của `sun.misc.Unsafe`).

Rủi ro chính:

1. **Field offsets có thể thay đổi** khi VM nâng cấp hoặc đổi cờ.
2. Vi phạm Java Memory Model có thể tạo lỗi concurrency rất khó debug.
3. Mã đọc/ghi raw memory sai có thể phá hỏng trạng thái runtime và gây lỗi nghiêm trọng.
4. Encoded/compressed references không đồng nhất với native raw pointers.
5. GC có thể di chuyển objects; suy ra native address từ giá trị reference là không đáng tin.
6. Module encapsulation/JDK access restrictions có thể ngăn code dựa vào internal APIs.

**Đừng viết bộ serialize bằng cách quét bytes của Java object instance theo offsets cố định.** Cách này nguy hiểm với reference fields, object headers, GC và mọi thay đổi layout.

### 16.1. Có trường hợp nào cần điều khiển layout thật không?

Nếu yêu cầu là một cấu trúc **off-heap** hoặc giao tiếp native với ABI xác định, chọn giải pháp có contract phù hợp theo JDK mục tiêu:

- `ByteBuffer` với thứ tự byte rõ ràng, offset do ứng dụng định nghĩa.
- Binary serialization formats (Protobuf, Avro, custom format có versioning).
- Foreign Function & Memory API (`MemorySegment`, `MemoryLayout`) ở JDK hỗ trợ ổn định tính năng và theo đúng API docs.

Các công cụ này **định nghĩa layout cho dữ liệu do ứng dụng quản lý**, không khiến instance layout của một Java class trên heap trở thành portable.

## 17. Tối ưu memory footprint: hướng nào an toàn hơn hardcode layout?

### 17.1. Đếm objects và đo lường thay vì đoán

Một triệu objects rất nhỏ vẫn có thể tốn nhiều heap do:

- Header/object alignment overhead.
- Fields và reference slots.
- Các objects được tham chiếu, chẳng hạn strings, lists, boxed values.
- Hash table entries, collection backing arrays.
- GC/runtime accounting và fragmentation.

Ví dụ một `List<Integer>` có thể giữ nhiều wrapper objects và backing reference array; một `int[]` giữ primitive values trong một array object theo kiểu lưu của HotSpot thông thường. Nhưng lựa chọn dữ liệu phải dựa vào **API semantics, nullable, cập nhật, phân phối giá trị, GC và benchmark**.

### 17.2. Chọn cấu trúc dữ liệu theo workload

- Với dữ liệu số học dày đặc, primitive arrays có thể giảm số object so với boxing.
- Với data sparse/jagged, cấp phát từng inner array theo nhu cầu có thể giảm memory.
- Dùng collections phù hợp với nhu cầu truy cập, thêm/xóa và khả năng thay đổi.
- Giảm số lượng objects trung gian khi profiling chứng minh ảnh hưởng.
- Dùng streaming/batching khi không cần giữ toàn bộ dữ liệu trong heap.

Không kết luận “primitive array luôn nhanh nhất” cho mọi tình huống; cần đo end-to-end.

### 17.3. False sharing và field proximity

Hai biến được thread khác nhau cập nhật có thể gây contention trên cache line nếu chúng vô tình nằm trong cùng cache line (*false sharing*). Nhưng Java **không hứa** thứ tự fields hoặc một kích thước cache line cố định.

Một số HotSpot builds/cấu hình hỗ trợ kỹ thuật padding hoặc `@Contended` cho mục tiêu đặc biệt, nhưng đây là phần **không portable và tùy JVM/module access/flags**. Không dùng annotation nội bộ như một bảo đảm layout phổ quát.

Hãy cân nhắc các hướng portable trước: chia state theo thread, giảm shared writes, dùng concurrency structures phù hợp, benchmark trong điều kiện thực.

## 18. Các sai lầm thường gặp

| Nhận định sai | Cách hiểu đúng |
| --- | --- |
| “JVMS bắt buộc object có 12-byte header.” | JVMS `2.7 **không bắt buộc cấu trúc nội bộ cụ thể**. |
| “Mọi object HotSpot 64-bit có header 16 byte.” | Tùy compressed class pointers và compact headers; 12, 16, 8 có thể gặp ở cấu hình khác nhau. |
| “Một field `boolean` đúng 1 byte sẽ luôn tăng object size 1 byte.” | Alignment/padding và field layout có thể khiến shallow size không tăng hoặc tăng nhiều hơn. |
| “Fields nằm theo đúng thứ tự khai báo.” | Không là cam kết field offsets của Java. |
| “`getDeclaredFields()` trả về thứ tự layout.” | Reflection metadata không phải công cụ portable đo byte offsets. |
| “Reference trên 64-bit JVM luôn 8 byte.” | Compressed oops có thể dùng encoded references 4 byte. |
| “Compressed oops và compressed Klass pointers là một.” | Khác mục đích: Java object references và class metadata pointer. |
| “`System.identityHashCode(obj)` là địa chỉ object.” | Là giá trị hash theo hợp đồng Java, không phải native pointer. |
| “GC không bao giờ chuyển địa chỉ object.” | Một số garbage collectors có thể relocate objects. |
| “Một `new` luôn tạo object hiện hữu ở heap snapshot.” | JIT có thể tối ưu allocation theo điều kiện cho phép. |
| “Mảng `int[][]` là một khối primitive liên tục.” | Là mảng của các mảng; không có cam kết một block 2D liền khối. |
| “Array header/length luôn ở offset 12.” | Có thể gặp ở cấu hình cụ thể, không phải ABI Java. |
| “Java `boolean[]` luôn bit-packed.” | Không là bảo đảm; HotSpot thông thường dùng một byte/element. |
| “`sizeof(Object[])` chỉ bằng số elements × reference width.” | Còn header/alignment/padding; các object được trỏ tới lại riêng. |
| “JOL nói size 32 byte nghĩa là mọi JVM luôn 32.” | Kết quả gắn với VM/JDK/flags và JOL mode. |
| “`Instrumentation.getObjectSize` trả retained graph size chính xác.” | API là approximation của **một object** theo implementation; không đi sâu graph. |
| “Compact Object Headers chỉ là dự án tương lai.” | Đã có JDK 24 experimental, JDK 25 product và JDK 27 default trên HotSpot phù hợp. |
| “Bật compact headers là Java thay đổi ngữ nghĩa `equals`/`getClass`.” | Header nội bộ thay đổi, các bảo đảm Java phải được giữ. |
| “Hardcode field offsets giúp binary protocol nhanh và portable.” | Rủi ro khi nâng JDK/VM/flags; hãy dùng format có schema/layout rõ ràng. |

## 19. Bài tập tự kiểm tra kèm đáp án

**Câu 1.** JVM Specification có bắt object của mọi VM dùng mark word và Klass pointer không?

**Đáp án:** Không. JVMS `2.7 không bắt buộc cấu trúc nội bộ cho object; mark word và Klass pointer là thuật ngữ triển khai HotSpot.

**Câu 2.** `Object a = new Object(); Object b = a;` có bảo đảm `a == b` là true không?

**Đáp án:** Có, vì hai references cùng trỏ một object. Không cần biết native address của object để kết luận.

**Câu 3.** `class X { int a; boolean b; }` có bảo đảm field `b` nằm ngay sau 4 byte của `a` không?

**Đáp án:** Không. Field order, alignment và padding là chi tiết triển khai.

**Câu 4.** Vì sao `new int[1]` có thể lớn hơn 4 byte nhiều lần?

**Đáp án:** Vì array là object, có header/metadata và padding, không chỉ một phần tử primitive.

**Câu 5.** `new Object[3]` có tự tạo ba instance `Object` không?

**Đáp án:** Không. Nó tạo một reference array, ba phần tử ban đầu null.

**Câu 6.** `new int[2][3]` có bao nhiêu array objects trong mô hình Java?

**Đáp án:** Một outer array và hai inner `int[]` arrays, tổng ba object; Java không cam kết sáu phần tử primitive thuộc một 2D block vật lý.

**Câu 7.** Shallow size của `Object[]` có tính toàn bộ objects được tham chiếu không?

**Đáp án:** Không. Shallow size chỉ tính array object và slots; retained graph/size cần phân tích các objects liên quan.

**Câu 8.** JDK 17 HotSpot báo một object header 12 byte. Có thể hardcode điều đó cho JDK 27 không?

**Đáp án:** Không. Compact object headers và các VM options có thể thay đổi layout; JDK 27 dùng compact headers theo feature/default tương ứng.

**Câu 9.** `System.identityHashCode` có thể dùng thay `addressOf` không?

**Đáp án:** Không. Identity hash không là địa chỉ và có thể trùng giữa objects khác nhau.

**Câu 10.** JVM 64-bit có thể lưu reference field 4 byte không?

**Đáp án:** Có, trên HotSpot với compressed oops và cấu hình hỗ trợ. Đây không phải cam kết của Java.

**Câu 11.** JOL là compiler specification hay công cụ đo implementation?

**Đáp án:** JOL là công cụ quan sát/phân tích layout của runtime/VM mode; output không trở thành ABI bắt buộc của ngôn ngữ.

**Câu 12.** Vì sao đổi `-XX:ObjectAlignmentInBytes` có thể làm object shallow size thay đổi?

**Đáp án:** Vì VM phải sắp xếp/pad object theo alignment; làm tròn và cách encode pointers có thể đổi.

**Câu 13.** Bật compressed class pointers có nghĩa mọi references tới object khác cũng được nén không?

**Đáp án:** Không. Compressed Klass pointers và compressed ordinary object pointers là hai khái niệm khác nhau.

**Câu 14.** Cần format binary portable cho native integration, có nên quét bytes của Java class instance không?

**Đáp án:** Không. Nên định nghĩa schema/byte order và dùng API quản lý layout như ByteBuffer, serializer hoặc FFM phù hợp JDK mục tiêu.

**Câu 15.** Chương trình demo chạy giống hệt trên hai JDK nhưng JOL báo size khác nhau. Đây có phải bug của Java không?

**Đáp án:** Không. Java bảo đảm ngữ nghĩa, không đảm bảo shallow object layout giống nhau giữa JVM/JDK builds.

## 20. Checklist khi phân tích layout hoặc memory performance

1. **Chụp môi trường:** `java -version`, vendor, kiến trúc, GC, JVM flags.
2. **Xác định điều cần đo:** shallow size, retained size, allocation rate, heap usage hay native memory.
3. **Dùng công cụ phù hợp:** JOL cho layout, Instrumentation cho approximate object size, JFR/heap dumps cho allocation/retention, GC metrics cho biến động heap.
4. **Xác định có compressed oops và compressed class pointers hay không.**
5. **Kiểm tra compact headers** nếu dùng JDK 24+.
6. **Xem alignment**, field inheritance, class shape và array component type.
7. **Đừng biến layout quan sát được thành contract của dữ liệu.**
8. **Benchmark workload thực tế** thay vì tối ưu chỉ theo một object sample.
9. **Kiểm tra lại sau nâng JDK hoặc đổi JVM flags**.
10. **Ưu tiên các giải pháp theo Java semantics và API contract** để ứng dụng tiếp tục hoạt động trên các JVM khác nhau.

### Tổng kết cuối cùng

```text
Java/JVMS cam kết:
  Object reference semantics
  Field values và access rules
  Array length, element defaults, bounds checks
  Class/array runtime type rules và memory model

HotSpot có thể lựa chọn:
  Object header format và bytes
  Mark word / Klass metadata representation
  Instance field offsets, order, packing, alignment
  Compressed references
  Array header/base offsets và element slot widths
  Garbage collector và object relocation
  Compact headers theo phiên bản JDK

Hệ quả:
  Cùng một Java program
    ├── có thể in cùng một stdout
    └── nhưng có object/array sizes và offsets khác nhau
```

Bài học cốt lõi là: **biết layout của một HotSpot build giúp phân tích hiệu năng và bộ nhớ; không được nhầm layout ấy với một cam kết của Java.**

### Tài liệu tham khảo chuẩn

- [JVMS `2.7 — Representation of Objects (Java SE 25)](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-2.html#jvms-2.7): JVM không áp đặt cấu trúc object nội bộ duy nhất.
- [JVMS `2.4 — Reference Types and Values](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-2.html#jvms-2.4): class instances, arrays và references.
- [JLS `10 — Arrays (Java SE 25)](https://docs.oracle.com/javase/specs/jls/se25/html/jls-10.html): ngữ nghĩa arrays, length, elements, nhiều chiều.
- [JLS `4.12.5 — Initial Values of Variables](https://docs.oracle.com/javase/specs/jls/se25/html/jls-4.html#jls-4.12.5): default values của fields/array components.
- [OpenJDK JOL — Java Object Layout](https://openjdk.org/projects/code-tools/jol/): công cụ thực nghiệm để quan sát class/object/array layouts.
- [OpenJDK JEP 450 — Compact Object Headers (Experimental)](https://openjdk.org/jeps/450): giới thiệu trong JDK 24.
- [OpenJDK JEP 519 — Compact Object Headers](https://openjdk.org/jeps/519): product feature từ JDK 25.
- [OpenJDK JEP 534 — Compact Object Headers by Default](https://openjdk.org/jeps/534): mặc định mới trong JDK 27.
- [Java Instrumentation API — getObjectSize (Java SE 25)](https://docs.oracle.com/en/java/javase/25/docs/api/java.instrument/java/lang/instrument/Instrumentation.html#getObjectSize(java.lang.Object)): approximation of object size theo implementation.
- [Oracle Java `java` command options (JDK 25)](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): JVM flags về compressed pointers, alignment và compact headers.
