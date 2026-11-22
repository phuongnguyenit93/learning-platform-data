# So sánh kích thước trong cùng cấu hình mà không coi số đo là hằng số của Java

Trong quá trình khảo sát một ứng dụng Java đang chạy, ta có thể dùng `Instrumentation.getObjectSize(Object)` để ước lượng kích thước của một đối tượng. Ví dụ, phép đo có thể cho thấy `byte[1024]` lớn hơn `byte[32]`, hoặc hai đối tượng `Holder` chứa tham chiếu tới những mảng dài khác nhau lại có cùng kích thước *shallow*.

**Điều quan trọng là cách diễn giải**: giá trị trả về là một **ước lượng phụ thuộc implementation và trạng thái JVM**, phù hợp để so sánh có kiểm soát trong cùng môi trường. Nó không phải `sizeof` do ngôn ngữ Java quy định, cũng không phải kích thước toàn bộ đồ thị đối tượng hay lượng bộ nhớ thực sự được hệ điều hành cấp cho tiến trình.

## 1. Sau bài học, cần trả lời được gì?

- `Instrumentation.getObjectSize` nhận đầu vào gì, trả về điều gì, và vì sao phải dùng Java agent để lấy `Instrumentation`?
- Vì sao nên so sánh các đối tượng **trong cùng cấu hình JVM**, thay vì ghi một số byte thành “kích thước chuẩn” của kiểu dữ liệu Java?
- *Shallow size*, *reachable size*, *retained size* và bộ nhớ ngoài heap khác nhau thế nào?
- Vì sao một `Holder` tham chiếu mảng lớn có thể có shallow size bằng `Holder` tham chiếu mảng nhỏ?
- Cần giữ cố định những yếu tố nào và ghi lại dữ kiện gì để kết quả so sánh có ý nghĩa?

Bài này thuộc phần **Khảo sát khi chạy** của Java Instrumentation. Trọng tâm là phép đo theo đối tượng **đang tồn tại**, không phải đo bytecode `.class`, kích thước JAR, hay lập trình Java agent để thay đổi hành vi của phương thức.

## 2. Hợp đồng thực tế của `getObjectSize`

Giao diện `java.lang.instrument.Instrumentation` định nghĩa:

```java
long getObjectSize(Object objectToSize);
```

Theo [Javadoc Java 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/Instrumentation.html#getObjectSize(java.lang.Object)), đây là một **implementation-specific approximation** của lượng lưu trữ mà đối tượng sử dụng. Giá trị có thể tính một phần hoặc toàn bộ overhead của đối tượng. Tài liệu nói rõ số đo hữu ích để **so sánh bên trong một implementation**, không dùng làm kết luận tương đương giữa các implementation; thậm chí **ước lượng có thể thay đổi trong cùng một lần chạy JVM**.

Hệ quả:

1. Không có quy tắc ngôn ngữ như “mọi `Object` luôn chiếm 16 byte”, “mọi tham chiếu luôn 4 byte” hay “`String` luôn chiếm 24 byte”.
2. Một JVM có thể trả số khác khi thay đổi phiên bản, kiến trúc, flags liên quan object alignment/compressed references, cách bố trí object hoặc các lựa chọn triển khai.
3. Ngay cả khi cùng process, kết quả là **ước lượng tại thời điểm gọi**, không nên coi số trước đó là một hằng số cố định cho mọi đối tượng cùng lớp hoặc mọi thời điểm.
4. Giá trị được trả về cho **đối tượng cụ thể**. Nó không đại diện tự động cho lớp, toàn bộ instance cùng kiểu, bộ nhớ do các đối tượng được tham chiếu giữ, hay mức tiêu thụ heap của JVM.
5. Truyền `null` gây `NullPointerException`. Muốn gọi API này, ứng dụng cần một đối tượng `Instrumentation` được JVM cung cấp cho agent qua `premain` hoặc `agentmain`; `new Instrumentation()` không tồn tại.

Nhiều JVM phổ biến biểu diễn các số đo dưới dạng byte và người ta thường gọi chúng là “shallow bytes”, nhưng **không suy ngược từ số byte sang một hằng số layout được Java Language Specification bảo đảm**.

## 3. Đo đúng thứ mình muốn so sánh

### 3.1. Shallow size của một đối tượng

*Shallow size* là lượng bộ nhớ của chính object/array đang xét, theo cách JVM ước lượng. Với một object có field tham chiếu, nó tính phần lưu trữ **tham chiếu đó trong object**, chứ không tự đi theo tham chiếu để cộng object bên kia. Với một array, số đo bao gồm chính array và vùng phần tử của nó theo implementation, nhưng `Object[]` chứa các *reference slot*, không bao gồm mọi object mà phần tử trỏ tới.

Ví dụ:

```java
final class Holder {
    final byte[] data;

    Holder(int length) {
        data = new byte[length];
    }
}
```

Hai object `new Holder(32)` và `new Holder(1024)` đều có **một field tham chiếu `data`**. Trong một cấu hình HotSpot thông thường, kích thước shallow của hai object `Holder` có thể bằng nhau; phần chênh lệch đáng kể nằm ở **hai `byte[]`** riêng mà chúng tham chiếu.

```text
Holder(32)  ──data──> byte[32]
   └─ phần của Holder     └─ mảng riêng

Holder(1024)──data──> byte[1024]
   └─ phần của Holder     └─ mảng riêng
```

Vì vậy kết luận “Holder 1024 không tốn thêm RAM” là sai. Phép đo shallow chỉ nói về phần bản thân `Holder`.

### 3.2. Reachable size, retained size và tài nguyên ngoài heap

| Khái niệm | Đo phần nào? | `getObjectSize` có cung cấp trực tiếp không? |
| --- | --- | --- |
| **Shallow size** | Bản thân một object/array | Có, dưới dạng ước lượng phụ thuộc JVM |
| **Reachable object graph** | Những object có thể đi tới qua các reference từ một gốc | Không; muốn ước lượng phải duyệt đồ thị, chống lặp và tránh đếm trùng |
| **Retained size** | Lượng bộ nhớ có thể được giải phóng nếu object/gốc đó không còn giữ các object khác, theo quan hệ giữ sống thực tế | Không; thường cần phân tích heap graph và dominator |
| **Used heap** | Tổng vùng heap đang sử dụng tại một thời điểm | Không; các API heap/GC và công cụ quan sát có ngữ nghĩa khác |
| **Off-heap/native memory** | Vùng memory ngoài Java object heap, như direct buffer/native allocation | Không; bản thân wrapper Java chỉ phản ánh phần object wrapper |

Không nên tính “deep size = shallow object + shallow mọi object trỏ tới” một cách giản đơn nếu có vòng tham chiếu, sharing, interned object hoặc nhiều gốc cùng giữ một object. Và *reachable size* không đồng nghĩa *retained size*: một object có thể được tham chiếu bởi nhiều nơi, nên xóa một tham chiếu chưa chắc giải phóng object đó.

### 3.3. Kích thước class, object, allocation và file là bốn câu hỏi khác nhau

- Dung lượng của file `Foo.class` là số byte bytecode/metadata trong file, không phải shallow size của `new Foo()`.
- `getObjectSize(Foo.class)` đo object `java.lang.Class` tương ứng theo JVM, **không phải** kích thước mọi instance `Foo`, hay toàn bộ metadata Metaspace.
- Tổng số byte **được cấp phát qua nhiều lần tạo object** là một phép đo allocation; không đồng nghĩa kích thước của một object hiện có.
- Resident memory của process còn chứa code cache, stack, native allocations, dữ liệu VM và những yếu tố ngoài shallow size.

## 4. Giữ cùng cấu hình: nền tảng của một so sánh có ý nghĩa

Cần xác định rõ **đối tượng A và B khác nhau ở điểm nào**. Một thí nghiệm tối thiểu nên cố định:

| Yếu tố | Cách kiểm soát |
| --- | --- |
| JVM implementation/vendor và bản phát hành | Chạy A và B **trong cùng process**; ghi `java.vm.name`, `java.vm.version`, `java.version` |
| Kiến trúc và cách biểu diễn reference | Giữ cùng kiến trúc, compressed pointers, object alignment, các tùy chọn JVM có ảnh hưởng |
| Loại đối tượng | So cùng loại hoặc chủ đích đo sự khác biệt loại/shape; không trộn “shallow array” với “deep object graph” |
| Tham số được thay đổi | Ví dụ chỉ thay **chiều dài mảng** hoặc chỉ thay số field; ghi lại chính xác |
| Đường tạo đối tượng | Tạo object bằng cùng chương trình và cách cấp phát; giữ reference tới chúng trong lúc đo |
| Cách tính số đo | Dùng cùng `Instrumentation.getObjectSize`, cùng đơn vị và cùng thời điểm đánh giá |
| Diễn giải | Ghi kết quả là quan sát trên môi trường cụ thể, không gán thành quy luật Java |

Ưu tiên **đo hai phương án trong một JVM đang chạy**, vì khi đó ít nhất các cài đặt khởi động được giữ giống nhau. Nhưng như Javadoc đã nhấn mạnh, **cùng JVM cũng chưa biến kết quả thành hằng số bất biến**. Nếu dùng nhiều lần đo, ghi lại biên độ quan sát, không giả định phép đo luôn ổn định; nếu thấy thay đổi bất thường, điều tra nguyên nhân thay vì âm thầm lấy một lần đo duy nhất làm chân lý.

Không “chuẩn hóa” một kết quả theo machine khác bằng cách suy đoán kích thước header, reference hoặc alignment. Nếu muốn so sánh **hai cấu hình JVM khác nhau**, hãy đặt câu hỏi đó thành một thí nghiệm khác và báo cáo từng môi trường riêng; không dùng số của một môi trường làm định nghĩa của Java.

### So sánh hiệu số và tỷ lệ

Với cùng cách đo và cùng bối cảnh, có thể tính:

```text
delta(A, B) = shallowSize(B) - shallowSize(A)
ratio(A, B) = shallowSize(B) / shallowSize(A), nếu A khác 0
```

Ví dụ: muốn biết một mảng dài hơn tiêu thụ thêm bao nhiêu shallow bytes so với mảng ngắn **trên JVM đang dùng**, `delta(byte[32], byte[1024])` hữu ích hơn câu “byte array luôn có X byte header”. Dù vậy, ratio/delta cũng chỉ là **quan sát trên implementation ấy**, không đảm bảo phổ quát. Với khác biệt rất nhỏ, không nên tạo kết luận quá mức về tác động tổng thể của chương trình.

## 5. Ví dụ Java 17+ chạy được: một agent đo các đối tượng tương quan

Ví dụ sau chạy không cần thư viện bên thứ ba. Startup agent lấy `Instrumentation`, cung cấp một API đo shallow size; ứng dụng tạo một nhóm đối tượng trong **cùng lần chạy** rồi in số đo và hiệu số. Không dùng ASM, bytecode transformer hay retransformation vì mục tiêu ở đây là **khảo sát kích thước**.

Cấu trúc:

```text
size-comparison/
├── agent.mf
├── src/
│   ├── SizeAgent.java
│   └── SizeComparison.java
└── out/                  # được tạo khi javac biên dịch
```

### 5.1. `SizeAgent.java`

Tệp `src/SizeAgent.java`:

```java
import java.lang.instrument.Instrumentation;

public final class SizeAgent {
    private static volatile Instrumentation instrumentation;

    private SizeAgent() {}

    public static void premain(String arguments, Instrumentation inst) {
        instrumentation = inst;
    }

    public static long shallowBytes(Object value) {
        Instrumentation inst = instrumentation;
        if (inst == null) {
            throw new IllegalStateException("Run with -javaagent:size-demo.jar");
        }
        return inst.getObjectSize(value);
    }
}
```

Ở đây:

- JVM gọi `premain(String, Instrumentation)` trước `main` nếu cung cấp `-javaagent` đúng manifest; đó là nơi agent nhận đối tượng `Instrumentation`.
- `volatile` bảo đảm publication của tham chiếu `Instrumentation` trong ví dụ nếu các luồng khác cùng sử dụng phương thức đo. Trong chương trình chỉ có một luồng, đây là lựa chọn an toàn dễ hiểu.
- `shallowBytes` đo **đúng đối tượng truyền vào**. Nó không đệ quy qua field.
- Nếu chạy ứng dụng mà quên `-javaagent`, phương thức báo lỗi có ý nghĩa, tránh `NullPointerException` khó hiểu. API thật vẫn ném `NullPointerException` nếu truyền `null` cho `getObjectSize`.

### 5.2. `SizeComparison.java`

Tệp `src/SizeComparison.java`:

```java
public final class SizeComparison {
    static final class Holder {
        final byte[] data;

        Holder(int length) {
            data = new byte[length];
        }
    }

    private static void display(String name, Object object) {
        System.out.printf("%-18s %6d bytes%n", name,
                SizeAgent.shallowBytes(object));
    }

    public static void main(String[] args) {
        byte[] shortArray = new byte[32];
        byte[] longArray = new byte[1024];
        Object[] fewRefs = new Object[4];
        Object[] manyRefs = new Object[128];
        Holder smallHolder = new Holder(32);
        Holder largeHolder = new Holder(1024);

        System.out.println("Java=" + System.getProperty("java.version"));
        System.out.println("VM=" + System.getProperty("java.vm.name"));
        display("new Object()", new Object());
        display("byte[32]", shortArray);
        display("byte[1024]", longArray);
        display("Object[4]", fewRefs);
        display("Object[128]", manyRefs);
        display("Holder(32)", smallHolder);
        display("Holder(1024)", largeHolder);

        long arrayDelta = SizeAgent.shallowBytes(longArray)
                - SizeAgent.shallowBytes(shortArray);
        long holderDelta = SizeAgent.shallowBytes(largeHolder)
                - SizeAgent.shallowBytes(smallHolder);
        System.out.println("array delta=" + arrayDelta + " bytes");
        System.out.println("holder delta=" + holderDelta + " bytes");
        System.out.println("holder payload measured separately: "
                + SizeAgent.shallowBytes(largeHolder.data) + " bytes");
    }
}
```

Có ba cặp quan sát:

1. **`byte[32]` và `byte[1024]`**: cùng kiểu array, chỉ khác độ dài. Shallow size của mảng bao gồm vùng dữ liệu phần tử nên thường tăng theo length.
2. **`Object[4]` và `Object[128]`**: array lưu nhiều *reference slot* hơn. Việc các phần tử đều `null` trong ví dụ giúp tập trung vào kích thước bản thân array.
3. **`Holder(32)` và `Holder(1024)`**: mỗi Holder chỉ lưu một tham chiếu tới `byte[]`, vì vậy phép đo `Holder` không trực tiếp cho biết độ lớn mảng mà nó trỏ tới.

### 5.3. Manifest và lệnh chạy

Tệp `agent.mf` chứa nội dung sau; có **dòng trống kết thúc** sau thuộc tính:

```text
Manifest-Version: 1.0
Premain-Class: SizeAgent

```

Tại thư mục `size-comparison`, tạo `out`:

```bash
mkdir -p out
```

Trên PowerShell, có thể tạo `out` bằng:

```powershell
New-Item -ItemType Directory -Force out | Out-Null
```

Biên dịch và đóng gói bằng JDK 17 trở lên:

```bash
javac --release 17 -encoding UTF-8 -d out src/SizeAgent.java src/SizeComparison.java
jar --create --file size-demo.jar --manifest agent.mf -C out .
java -javaagent:size-demo.jar -cp size-demo.jar SizeComparison
```

`jar` trên chứa cả lớp agent và ứng dụng để giữ ví dụ gọn; production thường tách agent JAR và application artifact. Không có yêu cầu `Can-Retransform-Classes` vì ví dụ chỉ sử dụng `getObjectSize`.

### 5.4. Một đầu ra thực tế và cách đọc

Đây là **đầu ra đã quan sát được** khi biên dịch với `--release 17` và chạy trên **OpenJDK 21.0.12.1, 64-bit Server VM, một cấu hình mặc định cụ thể**:

```text
Java=21.0.12.1
VM=OpenJDK 64-Bit Server VM
new Object()           16 bytes
byte[32]               48 bytes
byte[1024]           1040 bytes
Object[4]              32 bytes
Object[128]           528 bytes
Holder(32)             16 bytes
Holder(1024)           16 bytes
array delta=992 bytes
holder delta=0 bytes
holder payload measured separately: 1040 bytes
```

**Các con số trong output là quan sát riêng của lần chạy trên**, không phải stdout bất biến theo Java specification. Khi chạy ở JDK/JVM khác, ngay cả cùng phiên bản nhưng flags/layout khác, có thể nhận số khác. Hãy quan sát số thực tế do lệnh in ra và giải thích theo đúng bối cảnh.

Ở lần chạy ví dụ:

- `byte[1024]` lớn hơn `byte[32]` **992 byte theo ước lượng của VM này**. Vì độ dài khác 992 phần tử `byte`, kết quả phù hợp cách bố trí array tại thời điểm đó. Không được từ đây kết luận Java quy định kích thước header array cố định.
- `Object[128]` lớn hơn `Object[4]` **496 byte** trong phép đo này. Ta có thể dùng kết quả để nghiên cứu chi phí vùng lưu reference, nhưng không biến `496 / 124` thành định nghĩa tham chiếu Java luôn dài 4 byte.
- Hai `Holder` đều cho **16 byte shallow**. Điều này không chứng minh chúng có cùng tổng footprint: `largeHolder.data` một mình được đo là **1040 byte**. Một object graph có thể còn nhiều object khác bên ngoài kết quả shallow.

Nếu dùng các số để ước lượng số triệu object trong thực tế, phải tính đến cách tạo object, lượng instance đang sống, padding, share references, vùng nhớ ngoài heap, GC và overhead của cấu trúc lưu trữ. Nhân “16 byte × số đối tượng” là phép phỏng đoán rất hạn chế, **không phải báo cáo heap đã tiêu thụ**.

## 6. Phân tích cơ chế: tại sao kích thước được quan sát có thể khác?

Java quy định ngữ nghĩa đối tượng và trường dữ liệu, **không quy định byte-level layout cố định** cho mọi JVM.

Một implementation có thể lưu:

- **Object header**: thông tin cần thiết cho quản lý đối tượng/metadata/locking/GC, cấu trúc tùy JVM.
- **Instance fields**: primitive fields hoặc reference fields; implementation có thể sắp xếp, làm tròn hoặc padding theo những quy tắc riêng.
- **Array metadata**: thông tin về độ dài mảng, cộng vùng phần tử; có thể cần căn chỉnh.
- **Alignment/padding**: phần trống làm tròn footprint theo các ranh giới bố trí.
- **Reference encoding**: môi trường có/không có compressed ordinary object pointers, compressed class pointers hoặc cơ chế khác; kích thước *reference slot* và layout liên quan có thể khác.

Những yếu tố này là lời giải thích **có điều kiện về implementation**, không phải hợp đồng rằng mọi HotSpot/JVM luôn có cùng số byte ở mọi thời điểm.

### Tại sao “cùng cấu hình” vẫn chưa thành hằng số?

Javadoc cho phép ước lượng thay đổi ngay trong một JVM invocation. API không hứa hai lần gọi với cùng object sẽ mãi trả về một giá trị bất biến. Bởi vậy cách viết cẩn trọng là:

> Trong lần chạy JVM X với các tùy chọn Y, `getObjectSize` đã báo A byte cho đối tượng P và B byte cho đối tượng Q. Số đo cho phép so sánh tương đối tại thời điểm khảo sát; cần xác minh lại khi điều kiện thay đổi.

Không viết:

> Java quy định `new Object()` là 16 byte và `Holder` một field là 16 byte.

Ngay cả khi quan sát nhiều lần giống nhau, việc lặp lại chỉ củng cố kết luận **trong môi trường đo**, chứ không biến con số thành ngữ nghĩa ngôn ngữ.

## 7. Ba tình huống vận dụng thực tế

### 7.1. Tăng dung lượng cache: object mỏng nhưng dữ liệu bên trong lớn

Một cache entry có một trường tham chiếu tới `byte[]`. Nếu chỉ gọi `getObjectSize(entry)`, kết quả có thể gần như không đổi khi tăng kích thước payload. Để điều tra, đo riêng `entry`, mảng payload và các wrapper liên quan; khi cần tổng footprint thực tế, dùng heap profiling hoặc cách duyệt đồ thị phù hợp.

**Kết luận được phép:** shallow size của wrapper có thể không nhạy với dung lượng payload.

**Kết luận không được phép:** tăng payload không làm tăng mức dùng bộ nhớ.

### 7.2. `ArrayList` tăng số phần tử

`new ArrayList<>(10)` có đối tượng danh sách và thường có cấu trúc lưu trữ phần tử riêng theo implementation. `getObjectSize(list)` không phải phép đo toàn bộ backing array hay các element. Với danh sách có 10 phần tử trỏ tới một object duy nhất, 10 reference không đồng nghĩa 10 object độc lập.

Nếu muốn đánh giá chi phí của danh sách, cần xét:
- shallow của list object;
- shallow của backing storage nếu truy cập được bằng công cụ phù hợp;
- số reference slots;
- danh tính và số object thực tế được tham chiếu;
- khả năng các object được chia sẻ giữa nhiều cấu trúc.

Không dùng reflection tùy tiện vào private fields JDK chỉ để lấy shallow size: JPMS có ràng buộc module/opens, và implementation có thể thay đổi.

### 7.3. String và direct memory

Với `String`, shallow size của chính object **không trực tiếp phản ánh** toàn bộ vùng lưu nội dung ký tự. Những phiên bản JDK có thể chọn cách biểu diễn nội dung khác nhau; chia sẻ dữ liệu và intern pool cũng ảnh hưởng graph footprint.

Với `ByteBuffer.allocateDirect(...)`, một Java wrapper có thể tham chiếu tới vùng native/off-heap. Shallow size của wrapper **không bao gồm** dung lượng native mà JVM/allocator đã cấp cho buffer. Dùng Native Memory Tracking hoặc công cụ quan sát phù hợp nếu câu hỏi là native memory.

## 8. Thiết kế bảng khảo sát có thể tái lập

Khi so sánh một nhóm đối tượng, nên ghi theo cấu trúc như sau:

| Trường | Ý nghĩa |
| --- | --- |
| Thời điểm/chương trình | Lần chạy và commit/build của mã đo |
| JVM/Java/architecture | Vendor, VM name/version, `java.version`, architecture |
| JVM options liên quan | Heap, compressed references, alignment, GC nếu ảnh hưởng mục tiêu |
| Đối tượng | Kiểu thật và cách khởi tạo; length/capacity/field values |
| Phạm vi đo | **Shallow object** hay phép đo khác |
| Size quan sát | Giá trị được `getObjectSize` trả về; đơn vị nhất quán |
| Đối tượng đối chứng | Cùng type/cách tạo hoặc giải thích rõ khác biệt |
| Delta/ratio | So sánh trong chính lần chạy hoặc tập phép đo được kiểm soát |
| Hạn chế | Không gồm referents, retained size, off-heap; có thể có variation |

Ví dụ báo cáo cho một lần chạy đã nêu:

| Đối tượng A | Đối tượng B | A (byte) | B (byte) | Delta B − A | Phát biểu chính xác |
| --- | --- | ---: | ---: | ---: | --- |
| `byte[32]` | `byte[1024]` | 48 | 1040 | +992 | Mảng dài hơn được đo lớn hơn trên VM này |
| `Object[4]` | `Object[128]` | 32 | 528 | +496 | Nhiều reference slots hơn được tính vào shallow của array |
| `Holder(32)` | `Holder(1024)` | 16 | 16 | 0 | Shallow của hai wrapper bằng nhau tại phép đo |
| `Holder(1024)` | `Holder(1024).data` | 16 | 1040 | Không có ý nghĩa kiểu “tăng trưởng” | Hai số đo thuộc **hai đối tượng khác loại**, không phải A/B cùng yếu tố |

Kết quả cuối bảng là so sánh **phần wrapper** và **mảng được trỏ tới**, chỉ nhằm chỉ rõ boundary của shallow size. Không dùng hiệu số đó như độ tăng của một object.

### Tránh suy luận thống kê sai

Nếu mục tiêu là khảo sát footprint, nhiều mẫu khác nhau (length, class shapes, JVM flags) giúp tìm quy luật trong hệ thống cụ thể. Nhưng không nên:
- coi `getObjectSize` là đồng hồ đo thời gian và làm “warmup benchmark” rồi suy diễn thông số throughput;
- chọn một mẫu có chênh lệch vài byte, không kiểm tra layout, rồi kết luận tối ưu heap của toàn ứng dụng;
- làm tròn kết quả để che sự khác biệt do object alignment;
- gộp số từ các JVM khác nhau vào một trung bình không có ngữ nghĩa;
- mặc định mọi instance của một lớp đều có số đo bất biến theo thời gian, bất chấp lời cảnh báo của API.

## 9. So sánh phương pháp đo: chọn công cụ đúng câu hỏi

| Câu hỏi đang hỏi | Công cụ hoặc phương pháp thích hợp | Giới hạn |
| --- | --- | --- |
| Object này có shallow footprint ước lượng bao nhiêu? | `Instrumentation.getObjectSize` | Implementation-specific, không đo toàn bộ graph |
| Layout field/header/alignment trên HotSpot này ra sao? | OpenJDK JOL (Java Object Layout) | Mô tả implementation và runtime đã khảo sát |
| Ai đang giữ sống những object lớn và retained size là bao nhiêu? | Heap dump + memory profiler/dominator tree | Snapshot heap, có chi phí thu thập/phân tích |
| Ứng dụng tạo nhiều object ở đoạn code nào? | Allocation profiling/JFR events phù hợp | Đo luồng allocation, khác với tồn kho heap |
| Native/off-heap đang tăng vì đâu? | Native Memory Tracking/JFR/công cụ native thích hợp | Không suy ra từ shallow của wrapper |
| JVM có bao nhiêu heap đang dùng? | MXBeans/JFR/GC metrics hoặc profiling | Used heap không phải tổng `getObjectSize` của vài object |

**Không cố dùng một API trả lời mọi câu hỏi về bộ nhớ.** Mỗi phép đo có scope khác nhau. Trong phần khảo sát nhanh bằng Instrumentation, mục tiêu hợp lý là phân biệt các **ứng viên layout/đối tượng** trong môi trường đang chạy, từ đó quyết định có cần heap dump hoặc profiler chi tiết hay không.

## 10. Lỗi thường gặp và cách sửa

1. **Quên `-javaagent` nhưng gọi `SizeAgent.shallowBytes`:** ứng dụng không được JVM truyền `Instrumentation`. Chạy đúng agent JAR/manifest trước khi gọi `getObjectSize`.
2. **Hiểu `getObjectSize(holder)` như tổng kích thước mọi object reachable:** đo lại những đối tượng được trỏ tới hoặc chuyển sang công cụ phân tích heap graph.
3. **Sao chép output mẫu thành tài liệu “Java Object = 16 bytes”:** ghi kèm JVM/version/options và phạm vi phép đo; không gọi đó là hằng số.
4. **So hai ứng dụng với JDK/JVM/flags khác nhau rồi kết luận class A tốt hơn class B:** trước hết đưa phép đo về cùng môi trường hoặc thiết kế một thử nghiệm cross-configuration riêng, không dùng số thô làm chuẩn ngôn ngữ.
5. **Tưởng `Object[128]` chứa sẵn 128 object:** array mới tạo có 128 reference slots, các phần tử ban đầu là `null`; những object được trỏ tới nếu có là cấp phát khác.
6. **Nhầm số byte cấp phát với số byte đang sống:** nhiều object có thể đã được GC thu hồi; `getObjectSize` chỉ khảo sát object còn có tham chiếu tại thời điểm gọi.
7. **Tính tổng đồ thị bằng DFS mà không chống đếm trùng:** cycle hoặc shared reference gây đếm sai; retained size còn có ngữ nghĩa riêng.
8. **Nhầm `getObjectSize(SomeClass.class)` với kích thước instance:** đối số lúc đó là `java.lang.Class` object, không phải instance của `SomeClass`.
9. **Coi số đo là bất biến trong một lần chạy JVM:** đặc tả cho phép giá trị ước lượng thay đổi; khi cần so sánh chính xác, lưu dữ liệu của lần đo thay vì dựa vào số “mặc định”.
10. **Dùng `getObjectSize` cho direct buffer để suy ra native payload:** chỉ thấy Java object wrapper; phải đo phần native bằng công cụ đúng.

## 11. Bài tập tự thực hành

1. Trong cùng một lần chạy, thêm `byte[0]`, `byte[1]`, `byte[7]`, `byte[8]`, `byte[9]` vào thí nghiệm. Lập bảng size quan sát; có giá trị nào bằng nhau? Liên hệ tới alignment và nhấn mạnh đây là quan sát trên VM của bạn.
2. Thay `Holder` bằng lớp có hai tham chiếu: `byte[] a` và `Object label`. So sánh shallow size của hai instance chỉ khác chiều dài `a`, rồi đo riêng `a`.
3. Thêm `int[32]` và `long[32]`. Diễn giải chênh lệch theo loại phần tử trong JVM của bạn; không suy thành hằng số cho mọi implementation.
4. Thử `Object[]` có 128 ô đều `null` và `Object[]` cùng độ dài nhưng cùng trỏ tới một object. Shallow size của array thay đổi thế nào? Vì sao số object thực tế reachable khác?
5. Chạy lại dưới một cấu hình JVM khác có kiểm soát (nếu JVM hỗ trợ các flags cần thiết). Báo cáo tách riêng hai môi trường, nêu rõ khi nào dữ liệu chỉ còn mang tính so sánh trong từng nhóm.
6. Giải thích vì sao JFR allocation events hoặc heap dump có thể cần thiết ngay cả khi bạn đã đo shallow size của một `Map.Entry`.

## 12. Kiến thức cần giữ lại

- `Instrumentation.getObjectSize` đo **một object cụ thể**, trả **ước lượng phụ thuộc implementation**; số đo có thể thay đổi cả trong một JVM invocation.
- So sánh tốt nhất là **trong cùng JVM/cấu hình**, chỉ thay đổi một yếu tố và ghi lại điều kiện đo, delta cùng scope của object.
- **Shallow size không phải deep/reachable/retained size**, cũng không đo trực tiếp off-heap, tổng heap hay kích thước file `.class`.
- Kết quả “`Holder(32)` bằng `Holder(1024)`” chỉ cho biết chính hai **wrapper** có shallow size bằng nhau trong lần đo; payload của chúng vẫn có thể khác rất lớn.
- Dùng con số như **bằng chứng khảo sát** cho môi trường cụ thể, không đưa nó thành “hằng số kích thước do Java bảo đảm”.

## 13. Tài liệu chính thức và công cụ liên quan

- [Oracle Java SE 21 — `Instrumentation.getObjectSize`](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/Instrumentation.html#getObjectSize(java.lang.Object)): hợp đồng “implementation-specific approximation”, khả năng thay đổi trong cùng JVM.
- [Oracle Java SE 17 — `Instrumentation`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): API tương thích với ví dụ Java 17.
- [Oracle Java SE 21 — `java.lang.instrument` package](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/package-summary.html): manifest `Premain-Class`, startup agent và cơ chế JVM truyền `Instrumentation`.
- [OpenJDK — Java Object Layout (JOL)](https://github.com/openjdk/jol): công cụ nghiên cứu object layout/footprint cụ thể theo JVM, bổ trợ khi cần kiểm tra header, padding và reference layout.
