# getObjectSize trả ước lượng kích thước phụ thuộc cách triển khai

Trong Java agent, **`Instrumentation.getObjectSize(Object)`** trả về số `long` biểu thị **ước lượng lượng lưu trữ mà một object cụ thể tiêu thụ**. Tài liệu Java SE 17 gọi kết quả này là *implementation-specific approximation*: **không phải số byte chính xác theo một công thức cố định của ngôn ngữ Java**. Ước lượng có thể gồm một phần hoặc toàn bộ overhead của object, thường hữu ích khi so sánh **trong cùng một implementation và cấu hình JVM**, nhưng không nên đem đối chiếu tuyệt đối giữa các JVM khác nhau. Đặc tả còn nêu **ước lượng có thể thay đổi ngay trong cùng một lần JVM chạy**.

Điểm dễ nhầm thứ hai: `getObjectSize(holder)` **không tự đi qua các tham chiếu** để tính cả mảng, danh sách, cây hoặc đồ thị object do `holder` giữ sống. Nếu Holder chỉ chứa một reference tới mảng `byte[8192]`, kích thước shallow của Holder có thể rất nhỏ trong khi mảng là một object riêng lớn hơn 8 KiB.

Bài này tập trung vào hợp đồng API, shallow/deep/retained size, object header, array layout, compressed references, alignment, kết quả thực nghiệm Java 17+ trên các cấu hình HotSpot khác nhau và cách tránh diễn giải sai số đo trong khảo sát runtime.

## 1. Hợp đồng `Instrumentation.getObjectSize`

Chữ ký:

```java
long getObjectSize(Object objectToSize);
```

Theo tài liệu chính thức Java SE 17:

- Phương thức nhận **một object** để đo, không phải `Class<?>` hay tên của lớp.
- Trả về **ước lượng implementation-specific** về lượng lưu trữ của **object được chỉ định**, đơn vị byte.
- Kết quả có thể gồm một phần hoặc toàn bộ **object overhead**; hữu ích khi so sánh **trong một implementation**, không phải giữa các implementation.
- **Kết quả ước lượng có thể thay đổi trong một lần JVM invocation**. Không có cam kết giá trị bất biến.
- Nếu đối số là `null`, ném **`NullPointerException`**, không trả `0`.

**API không cam kết** layout header bao nhiêu byte, field nằm ở offset nào, một reference dài bao nhiêu byte, padding bao nhiêu, và cũng không bảo đảm kết quả là tổng heap/native/retained memory mà ứng dụng đang tiêu thụ.

Ví dụ lời gọi:

```java
// Mã minh họa trong phương thức đã có Instrumentation inst.
Object target = new Object();
long estimate = inst.getObjectSize(target);
System.out.println("estimated shallow bytes=" + estimate);
```

Đây là **đoạn mã minh họa**, chưa phải chương trình độc lập: chương trình Java bình thường không tự tạo `Instrumentation` bằng `new`. JVM cung cấp interface đó cho Java agent qua `premain` hoặc `agentmain`.

Nguồn: [Oracle Java SE 17 — Instrumentation#getObjectSize](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html#getObjectSize(java.lang.Object)).

## 2. Shallow size khác deep graph size và retained size

Một Holder được tạo như sau:

```java
// Mã mô tả object graph, chưa phải chương trình độc lập.
final class Holder {
    Object value;
}
Holder h = new Holder();
h.value = new byte[8192];
```

Mô hình:

```text
  object h: Holder                    object h.value: byte[8192]
+-------------------------+         +---------------------------+
| header + reference slot | ------> | header + 8192 bytes      |
+-------------------------+         +---------------------------+
          object 1                            object 2
```

| Đại lượng | Nội dung | Do `getObjectSize(h)` cung cấp? |
| --- | --- | --- |
| **Shallow size của h** | Lưu trữ của chính Holder, header/instance fields/padding theo JVM | **Có, dưới dạng ước lượng**. |
| **Shallow size của mảng** | Header và 8192 phần tử `byte` nằm trong array object | **Không tự cộng**; đo mảng riêng bằng `getObjectSize(h.value)`. |
| **Deep/reachable-graph size** | Tổng kích thước các object đi đến được theo references, theo chính sách duyệt | **Không**; cần duyệt graph và tránh object trùng/vòng lặp. |
| **Retained size** | Phần graph chỉ được giữ sống nhờ object/root đang xét, theo reachability/dominator | **Không**; cần phân tích heap graph. |
| **Used heap, committed heap, RSS** | Bộ nhớ cấp heap hay process, với overhead/GC/native components khác | **Không**; cần công cụ đo phù hợp từng phạm vi. |

**Không đánh đồng deep size và retained size.** Giả sử:

```text
   Holder A -----\
                  +----> shared byte[8192]
   Holder B -----/
```

Mảng shared nằm trong graph của cả A và B. Nếu cộng mảng theo **mỗi** reference thì sẽ bị double-count. Nếu bỏ A nhưng B vẫn giữ mảng, mảng **không trở thành rác** chỉ vì A được giải phóng. Vì vậy retained size của A không tự bao gồm toàn bộ mảng.

**Phân biệt tham chiếu và nội dung được trỏ tới:** field kiểu `Object` chỉ lưu một **reference slot** trong layout Holder. Nội dung mảng ở **array object khác**. Việc thay reference từ `null` sang mảng 8 KiB không yêu cầu Holder tự thêm một field chứa 8192 byte.

## 3. Vì sao size phụ thuộc JVM implementation?

Ngôn ngữ Java định nghĩa hành vi của field, array, class, method; nó không cố định một layout vật lý cho mọi object trên mọi VM. Những phần có thể khác:

| Thành phần | Tác động |
| --- | --- |
| **Object header** | JVM lưu dữ liệu quản lý object, thông tin loại lớp/metadata theo implementation; kích thước không cố định trong Java SE. |
| **Array header** | Mảng thường có thêm thông tin độ dài, kể cả khi không có phần tử. |
| **Field layout** | JVM có thể bố trí/sắp xếp instance fields và padding theo implementation, inheritance, access rules. |
| **Reference width** | Reference có thể dùng định dạng nén hoặc không nén, làm thay đổi lượng lưu trữ của slot. |
| **Object alignment** | VM có thể làm tròn kích thước object lên bội số alignment, dẫn đến padding. |
| **Primitive array payload** | Mảng `byte[]` lưu phần tử `byte` trong chính mảng; `long[]` và kiểu khác có kích thước slot khác. |
| **Object reference array** | `Object[n]` có n slot reference, **không tự chứa n object con**. |
| **JVM version/vendor/flags** | Layout và chiến lược cấp phát có thể thay đổi dù classfile giống hệt. |

Một mô hình **để hình dung**, **không phải công thức Java SE chuẩn**:

```text
estimated array bytes ~= roundUp(
    arrayHeaderBytes + length * elementSlotBytes,
    alignmentBytes)
```

Không hard-code `arrayHeaderBytes = 16` hoặc `referenceSlotBytes = 4` như hằng số của Java. Với cấu hình JVM khác, các giá trị đó có thể thay đổi; một số implementation còn có bố trí đặc biệt.

### 3.1. Compressed ordinary object pointers

Trên một số HotSpot 64-bit, **compressed oops** cho phép biểu diễn nhiều object references với độ rộng thấp hơn full pointer trong điều kiện nhất định. Điều này đặc biệt rõ trong các mảng `Object[]` có nhiều reference slots. Nếu tắt compressed oops, cùng một mảng có thể có estimate lớn hơn.

Đừng suy ra “cứ JVM 64-bit thì mọi reference bằng 8 byte” hoặc “cứ Java 17 thì mọi reference bằng 4 byte”. Chính VM configuration quyết định. Tài liệu liên quan: [Java 17 HotSpot Performance Enhancements — compressed oops](https://docs.oracle.com/en/java/javase/17/vm/java-hotspot-virtual-machine-performance-enhancements.html).

### 3.2. Alignment và padding

Một object có field payload nhỏ vẫn có thể được làm tròn lên một bội số. `byte[0]` thường có estimate khác 0 vì vẫn là array object có overhead. Mảng `byte[8192]` có payload đúng 8192 byte nhưng có thể cần phần header và padding.

Thay object alignment trong cùng HotSpot có thể đổi `getObjectSize` ngay cả khi **source và classfile không đổi**. Đôi khi một object đã có kích thước bội số alignment mới nên estimate của nó không thay.

### 3.3. So sánh có điều kiện

Để so sánh meaningful, tối thiểu nên nắm được VM vendor/version, architecture, flags, loại object và thời điểm khảo sát. Ngay cả khi tất cả trùng nhau, API vẫn chỉ cung cấp **approximation** — không nên xây tính phí/phân bổ tài nguyên dựa trên giả định tuyệt đối.

## 4. Lấy `Instrumentation` bằng Java agent

Một chương trình Java thông thường không thể viết:

```java
// KHÔNG phải mã hợp lệ để lấy Instrumentation từ JVM.
Instrumentation inst = new Instrumentation();
```

`Instrumentation` là interface, và JVM cung cấp instance qua entry point **Java agent**.

Với startup agent, JAR cần khai báo:

```text
Manifest-Version: 1.0
Premain-Class: demo.size.SizeAgent

```

Khi khởi chạy:

```bash
java -javaagent:size-agent.jar -cp out demo.size.SizeDemo
```

JVM đọc main manifest rồi gọi `public static void premain(String, Instrumentation)` trước application `main`. Agent giữ tham chiếu Instrumentation để ứng dụng thử nghiệm gọi phương thức đo.

**Không cần `Can-Redefine-Classes: true` hoặc `Can-Retransform-Classes: true`** chỉ để gọi `getObjectSize`. Các cờ đó liên quan thao tác redefine/retransform class đã nạp, không phải capability riêng cần bật cho method đo size.

Với agent nạp động bằng Attach API, entry point là `Agent-Class`/`agentmain` nếu môi trường hỗ trợ, nhưng thí nghiệm dưới đây dùng `premain` để tự chứa và dễ tái lập.

## 5. Thí nghiệm Java 17+: cùng Holder, kích thước referent khác nhau

Thí nghiệm có **hai file Java** và một manifest; không dùng Maven, JOL hay thư viện ngoài. Chúng ta đo:

1. Holder giữ `null`, mảng `byte[0]` và mảng `byte[8192]`.
2. Chính hai array objects `byte[0]`, `byte[8192]`.
3. Hai mảng tham chiếu `Object[0]` và `Object[100]`, chưa chứa object element nào.
4. Kiểm tra `getObjectSize(null)` ném exception đúng hợp đồng.
5. Chạy lại với HotSpot flags để thấy estimate có thể khác nhau.

### 5.1. Cấu trúc tệp

```text
object-size-demo/
├── src/demo/size/
│   ├── SizeAgent.java
│   └── SizeDemo.java
└── agent.mf
```

File manifest đã cho ở phần 4, nhớ lưu thành `agent.mf` với newline kết thúc.

### 5.2. `src/demo/size/SizeAgent.java`

```java
package demo.size;

import java.lang.instrument.Instrumentation;

public final class SizeAgent {
    private static volatile Instrumentation instrumentation;

    private SizeAgent() {}

    public static void premain(String options, Instrumentation inst) {
        instrumentation = inst;
        System.out.println("[agent] ready");
    }

    public static long shallowSize(Object value) {
        Instrumentation inst = instrumentation;
        if (inst == null) {
            throw new IllegalStateException("Run with -javaagent:size-agent.jar");
        }
        return inst.getObjectSize(value);
    }
}
```

Giải thích:

- `premain` nhận trực tiếp `Instrumentation` từ JVM; chương trình không đoán layout thủ công.
- Biến `static volatile` là cách công bố tham chiếu an toàn khi các thread khác truy cập. Nó **không** làm phép đo heap trở thành atomic snapshot.
- `shallowSize` gọi `inst.getObjectSize(value)` đúng theo API. Không duyệt field references.
- Nếu quên `-javaagent`, code báo lỗi rõ ràng. Với `null`, nó chuyển `null` tới API và API ném `NullPointerException`.

### 5.3. `src/demo/size/SizeDemo.java`

```java
package demo.size;

public final class SizeDemo {
    private SizeDemo() {}

    static final class Holder {
        final Object value;

        Holder(Object value) {
            this.value = value;
        }
    }

    public static void main(String[] args) {
        byte[] empty = new byte[0];
        byte[] large = new byte[8192];

        long holderNull = SizeAgent.shallowSize(new Holder(null));
        long holderEmpty = SizeAgent.shallowSize(new Holder(empty));
        long holderLarge = SizeAgent.shallowSize(new Holder(large));
        long arrayEmpty = SizeAgent.shallowSize(empty);
        long arrayLarge = SizeAgent.shallowSize(large);
        long refsEmpty = SizeAgent.shallowSize(new Object[0]);
        long refsHundred = SizeAgent.shallowSize(new Object[100]);

        System.out.println("[size] holder-null=" + holderNull);
        System.out.println("[size] holder-empty-array=" + holderEmpty);
        System.out.println("[size] holder-large-array=" + holderLarge);
        System.out.println("[size] byte[0]=" + arrayEmpty);
        System.out.println("[size] byte[8192]=" + arrayLarge);
        System.out.println("[size] Object[0]=" + refsEmpty);
        System.out.println("[size] Object[100]=" + refsHundred);
        System.out.println("[check] holder-estimates-equal=" +
                (holderNull == holderEmpty && holderEmpty == holderLarge));
        System.out.println("[check] long-byte-array-larger=" + (arrayLarge > arrayEmpty));
        System.out.println("[check] long-ref-array-larger=" + (refsHundred > refsEmpty));
        try {
            SizeAgent.shallowSize(null);
            System.out.println("[check] null=unexpected");
        } catch (NullPointerException expected) {
            System.out.println("[check] null=NullPointerException");
        }
    }
}
```

Trong chương trình này:

- Ba Holder là **ba object cùng class**, khác **giá trị reference**. Sự khác nhau về mảng được trỏ tới không tự thay đổi số field của Holder.
- `byte[8192]` là một array object **riêng** với 8192 byte dữ liệu primitive, nên được đo độc lập.
- `new Object[100]` cấp **một array object với 100 slots tham chiếu `null`**; nó không cấp 100 object `new Object()`.
- Các dòng `[check]` là phép so sánh trên **JVM thí nghiệm**. Kể cả khi chúng cho `true` trên JVM thử nghiệm, không được suy diễn thành một công thức layout được Java SE bảo đảm cho mọi VM.

### 5.4. Biên dịch và đóng gói

Từ thư mục `object-size-demo/`, với **Bash**:

```bash
mkdir -p out

javac --release 17 -d out \
  src/demo/size/SizeAgent.java \
  src/demo/size/SizeDemo.java

jar --create --file size-agent.jar --manifest agent.mf \
  -C out demo/size/SizeAgent.class

java -javaagent:size-agent.jar -cp out demo.size.SizeDemo
```

Trên **PowerShell**, mỗi lệnh dùng một dòng:

```powershell
New-Item -ItemType Directory -Force out | Out-Null
javac --release 17 -d out src/demo/size/SizeAgent.java src/demo/size/SizeDemo.java
jar --create --file size-agent.jar --manifest agent.mf -C out demo/size/SizeAgent.class
java -javaagent:size-agent.jar -cp out demo.size.SizeDemo
```

Dấu `\` ở Bash là nối dòng, không phải cú pháp nối dòng PowerShell. Mã biên dịch với `--release 17` chỉ dùng API Java 17; có thể chạy với JDK 17+ khi JVM hỗ trợ Java agent. File `size-agent.jar` cần chứa `SizeAgent.class` và manifest, còn app cùng nested `SizeDemo$Holder.class` nằm trên classpath `out`.

## 6. Kết quả thực nghiệm: cùng code, khác JVM flags

Các stdout dưới đây đã được **biên dịch bằng `javac --release 17` và chạy trên Zulu OpenJDK 24.0.2, HotSpot 64-bit**. Chúng **không phải số byte chuẩn của mọi Java 17/JVM**. Tùy chọn `-XX:...` là VM-specific, cần dùng trên HotSpot có hỗ trợ.

### 6.1. Cấu hình mặc định

```bash
java -javaagent:size-agent.jar -cp out demo.size.SizeDemo
```

Stdout đã kiểm chứng:

```text
[agent] ready
[size] holder-null=16
[size] holder-empty-array=16
[size] holder-large-array=16
[size] byte[0]=16
[size] byte[8192]=8208
[size] Object[0]=16
[size] Object[100]=416
[check] holder-estimates-equal=true
[check] long-byte-array-larger=true
[check] long-ref-array-larger=true
[check] null=NullPointerException
```

Kết quả minh họa rõ:

- `Holder(null)`, `Holder(byte[0])` và `Holder(byte[8192])` **cùng được ước lượng 16 byte** ở cấu hình này.
- Mảng `byte[8192]` lại được ước lượng **8208 byte** khi gọi `getObjectSize` **trên chính mảng**.
- Mảng `Object[100]` có estimate **416 byte** do slots references, không phải nhờ 100 child objects.
- Mảng rỗng `byte[0]` vẫn có estimate **16 byte**, cho thấy object/array overhead.
- Truyền `null` gây `NullPointerException` như tài liệu.

### 6.2. Tắt compressed references trên HotSpot

```bash
java -XX:-UseCompressedOops -javaagent:size-agent.jar -cp out demo.size.SizeDemo
```

Stdout trên cùng OpenJDK 24.0.2:

```text
[agent] ready
[size] holder-null=24
[size] holder-empty-array=24
[size] holder-large-array=24
[size] byte[0]=16
[size] byte[8192]=8208
[size] Object[0]=16
[size] Object[100]=816
[check] holder-estimates-equal=true
[check] long-byte-array-larger=true
[check] long-ref-array-larger=true
[check] null=NullPointerException
```

**Không đổi một dòng Java nào**, nhưng `Holder` tăng từ estimate 16 lên 24 byte; `Object[100]` từ 416 lên 816 byte. Trong thí nghiệm này, `byte[0]` và `byte[8192]` giữ cùng estimate vì không có hàng trăm reference slots cần mở rộng. Đây là một ví dụ cụ thể về ảnh hưởng của **reference width**.

### 6.3. Thay object alignment trên HotSpot

```bash
java -XX:ObjectAlignmentInBytes=32 -javaagent:size-agent.jar -cp out demo.size.SizeDemo
```

Stdout đã kiểm chứng:

```text
[agent] ready
[size] holder-null=32
[size] holder-empty-array=32
[size] holder-large-array=32
[size] byte[0]=32
[size] byte[8192]=8224
[size] Object[0]=32
[size] Object[100]=416
[check] holder-estimates-equal=true
[check] long-byte-array-larger=true
[check] long-ref-array-larger=true
[check] null=NullPointerException
```

Ở cấu hình alignment 32 byte này, `Holder` và mảng rỗng được ước lượng **32 byte**; `byte[8192]` là **8224 byte**. `Object[100]` vẫn **416 byte** vì estimate của nó đã thích hợp với alignment được chọn. **Đổi flag không bắt buộc mọi object phải đổi size.**

### 6.4. Bảng đối chiếu

| Đối tượng | Mặc định | `-XX:-UseCompressedOops` | `-XX:ObjectAlignmentInBytes=32` |
| --- | ---: | ---: | ---: |
| `Holder(null)` | 16 | 24 | 32 |
| `Holder(byte[8192])` | 16 | 24 | 32 |
| `byte[0]` | 16 | 16 | 32 |
| `byte[8192]` | 8208 | 8208 | 8224 |
| `Object[0]` | 16 | 16 | 32 |
| `Object[100]` | 416 | 816 | 416 |

**Đơn vị là byte.** Đây là dữ liệu của **một JVM và ba lần khởi động khác nhau**; không lấy bảng làm hằng số bất biến. `--release 17` bảo đảm source/API/classfile mục tiêu Java 17 khi biên dịch, **không đóng băng object layout** lúc chạy.

Dùng các cờ HotSpot này để nghiên cứu trong môi trường thử nghiệm có kiểm soát, không thay đổi cấu hình production bừa bãi chỉ để tái hiện số byte mẫu.

## 7. String, collections và off-heap: những ví dụ dễ bị hiểu nhầm

### 7.1. String và dữ liệu ký tự

Một `String` có các instance fields và có thể tham chiếu tới một backing array theo implementation. Vì vậy `getObjectSize(s)` đo **String wrapper object**, không tự cộng toàn bộ dữ liệu ký tự nằm ở một object khác.

```java
// Mã minh họa trong method đã có Instrumentation inst.
String shortText = "a";
String longText = "a".repeat(10000);
long shortEstimate = inst.getObjectSize(shortText);
long longEstimate = inst.getObjectSize(longText);
System.out.println(shortEstimate + " / " + longEstimate);
```

Không đưa stdout cố định cho đoạn này: nội dung String, compact strings, interning, backing representation và JVM flags có thể ảnh hưởng. **Hai shallow estimates có thể bằng nhau trong một implementation dù chi phí lưu nội dung ký tự của hai giá trị rất khác nhau.**

### 7.2. List và Map

Một `ArrayList<?>` thường giữ một backing array. Khi gọi `getObjectSize(list)`, đó là ước lượng **chính object danh sách**, không bao gồm mảng backing hoặc các phần tử được nó tham chiếu. Tương tự, `HashMap` có thể giữ table và nodes/entries dưới dạng object khác.

Một danh sách có một triệu phần tử **không thể** được định lượng toàn bộ heap footprint chỉ bằng một lần `getObjectSize(list)`. Muốn đo tổng, phải hiểu object graph, chia sẻ, object reuse và chính sách attribution.

### 7.3. Direct ByteBuffer và native memory

`ByteBuffer.allocateDirect(...)` có thể sử dụng **native/off-heap storage**. `getObjectSize(buffer)` chủ yếu phản ánh phần lưu trữ của **Java object cụ thể** được truyền vào, **không tự đo toàn bộ native allocation** mà object ấy quản lý. Nếu vấn đề là process RSS cao nhưng heap nhỏ, xem native memory/tooling riêng chứ không chỉ size của wrapper.

### 7.4. Static fields và primitive

`static byte[] cache = new byte[100000]` là state liên kết với class, không phải field instance được nhúng trong mỗi object của class đó. `getObjectSize(new MyClass())` không tự cộng mảng static ấy.

Nếu truyền primitive qua phương thức nhận `Object`, Java có thể **boxing** thành wrapper, ví dụ `Integer.valueOf(5)`. Lúc đó bạn đo **Integer object**, không phải kích thước biến primitive `int` trong stack/local variable.

## 8. Vì sao không được suy từ shallow size ra tổng heap hay RSS?

Đo một object và đo JVM process là hai việc khác nhau.

- **Heap usage** biến động theo allocation, GC, fragmentation, heap regions và concurrent activities.
- **Committed/reserved heap** không bằng tổng shallow sizes của mọi object sống.
- **RSS** của process còn có thread stacks, code cache, metaspace/native allocations, mapped files và các vùng ngoài Java heap.
- **TLAB/allocator overhead** không được một lời gọi `getObjectSize(oneObject)` mô tả đầy đủ.
- **Retained heap** cần xét object graph, roots và dominator relationships; phép cộng naive có thể double-count shared objects.
- **GC** không cam kết có thể hoặc sẽ giải phóng byte ngay khi bạn bỏ một reference; object khác có thể vẫn giữ nó sống.

Cũng không nên lấy `Runtime.totalMemory() - Runtime.freeMemory()` “trước và sau new” làm kích thước object exact: giữa hai phép đo có thể có class initialization, thread khác cấp phát, GC, JIT, buffer và VM bookkeeping.

Nếu bạn cần theo dõi memory leak, “kích thước một object là 16 byte” không cho biết **có bao nhiêu object như vậy**, tốc độ tạo mới, các root giữ sống hay lifetime của chúng.

## 9. Công cụ nào hợp với từng câu hỏi?

| Câu hỏi | Vai trò của `getObjectSize` | Phương án bổ sung |
| --- | --- | --- |
| Layout shallow của một object cụ thể? | Cho estimate hữu ích, có ghi JVM/flags | JOL (Java Object Layout) để phân tích header/field/padding của JVM cụ thể |
| Shallow size khác thế nào khi đổi flags? | Có thể đo và so sánh từng cấu hình | Benchmark trên VM cùng vendor/version với cờ xác định rõ |
| Object/GC root nào giữ nhiều heap? | **Không đủ** vì không duyệt reference graph | Heap dump + Eclipse MAT/VisualVM hoặc heap profiler có retained size/dominator tree |
| Loại allocation nào tăng nhanh? | Một lần đo size **không cho allocation rate/provenance** | Java Flight Recorder (JFR), allocation profiler |
| Native memory hoặc RSS cao? | **Không đủ** | Native Memory Tracking (khi hỗ trợ), process/OS profiler, diagnostics |
| Class/field thêm vào có làm shallow size tăng? | Có thể đối chiếu có kiểm soát | Layout inspection + regression tests trên JVM mục tiêu |
| Feature A/B dùng bao nhiêu memory tổng thể? | Chỉ là một nguồn tham khảo rất hẹp | Allocation sampling, heap graph, GC/heap metrics, load test |

**JOL** là một dự án công cụ của OpenJDK, **không phải** API tự động được bao gồm trong `java.lang.instrument`. JFR cũng đo những dữ liệu khác: sự kiện allocation, GC, hoạt động JVM, không thay thế retained graph nếu không có thông tin tham chiếu tương ứng.

## 10. Đo runtime một cách có thể so sánh

### 10.1. Ghi lại môi trường và định nghĩa metric

Mỗi dòng report nên nêu rõ:

```text
metric: estimated_shallow_object_bytes
source_api: Instrumentation.getObjectSize
vm: vendor/name/version
runtime: Java version, architecture, heap/VM flags relevant to layout
object: class name and defining class loader when relevant
sample: number of objects, time window, selection criteria
not_included: reachable objects, retained heap, native memory
```

Có thể đọc một số thông tin từ `System.getProperty("java.vm.name")`, `java.vm.version`, `os.arch`, còn các VM options/GC flags nên dùng diagnostics phù hợp (trên HotSpot có thể dùng `jcmd <pid> VM.flags`) thay vì suy từ class name.

Khi so sánh bản build trước/sau, chạy dưới **cùng VM configuration**. Không kết luận memory leak chỉ vì một bản HotSpot bật compressed references còn bản khác không.

### 10.2. Không giữ bảng size hằng số theo class vô hạn

Giá trị đo **không phải constant của ngôn ngữ**, và API cho phép estimate thay đổi ngay trong cùng JVM invocation. Không nên dùng `Map<Class<?>,Long>` như một “nguồn chân lý vĩnh viễn” cho toàn bộ runtime nếu sản phẩm đòi hỏi tính chính xác.

Nếu ứng dụng chỉ cần ước lượng dùng trong một cửa sổ đo cụ thể, có thể cache kết quả với metadata/cấu hình rõ ràng, nhưng phải ghi nhận giới hạn của suy luận và kiểm tra trên VM đang chạy.

### 10.3. Tránh tự viết “deep size” bằng reflection thiếu kiểm soát

Một phép duyệt tham chiếu từ object gốc gặp nhiều vấn đề:

1. **Shared objects**: cần identity-based visited set; `equals()` có thể coi hai instance khác nhau là bằng nhau.
2. **Cycles**: đồ thị object có thể có vòng tự tham chiếu, dẫn tới đệ quy vô hạn nếu không đánh dấu đã thăm.
3. **JPMS encapsulation**: reflection tới private fields có thể bị chặn; không tự mở tất cả package chỉ để tính size.
4. **Reference types**: weak/soft/phantom references, classloaders, interned objects đòi chính sách rõ.
5. **Off-heap/native resources**: không xuất hiện như các object con đơn giản để traversal.
6. **Tính nhất quán**: thread khác có thể mutate graph trong lúc đo.

Ngay cả khi đã xử lý tất cả các vấn đề đó và cộng shallow sizes của các object **độc nhất** trong graph, bạn mới có một **định nghĩa reachable-graph sum**, **chưa phải retained size**. Retained size dựa vào đồ thị tham chiếu từ **toàn bộ GC roots** và quan hệ dominator.

### 10.4. Không tăng tải ứng dụng vì phép đo

Đừng tạo hàng triệu sample objects trong hot path hoặc yêu cầu Full GC chỉ để “ổn định” một phép đo shallow. Với production, giới hạn tần suất, sampling, overhead của agent, và phân biệt measurement perturbation với hành vi ứng dụng ban đầu.

## 11. Lỗi và ngộ nhận thường gặp

| Phát biểu/sự cố | Cách hiểu đúng |
| --- | --- |
| “`getObjectSize` trả số byte chính xác của class theo Java spec.” | Sai: **implementation-specific approximation**. |
| “Mọi JVM có cùng bytecode phải báo size giống nhau.” | Sai: layout/VM flags khác. |
| “Holder trỏ tới mảng 8 KiB thì size của Holder phải khoảng 8 KiB.” | Sai: đó là object khác; đo mảng riêng. |
| “`byte[0]` không có phần tử nên size bằng 0.” | Sai: array object còn overhead. |
| “`Object[100]` chứa 100 object con.” | Sai: nó chỉ cấp 100 reference slots, mặc định null. |
| “`getObjectSize(list)` tính cả danh sách phần tử.” | Sai: thường chỉ shallow wrapper object; backing array/elements riêng. |
| “`String.length()` càng lớn thì shallow size của String nhất thiết tăng tương ứng.” | Không; backing representation có thể nằm ở object khác. |
| “`getObjectSize(null)` trả 0.” | Sai: ném `NullPointerException`. |
| “Đo `Integer.valueOf(1)` là đo primitive int.” | Sai: đang đo một wrapper object. |
| “Thấy Object[100] từ 416 lên 816 là có leak.” | Có thể chỉ do tắt compressed oops; chưa nói số object hay retained heap. |
| “Bật `Can-Retransform-Classes` mới dùng được `getObjectSize`.” | Không: capability transform/redefine khác phép đo shallow. |
| “Số đo từ HotSpot hôm nay là hằng số cho HotSpot tương lai.” | API không hứa điều đó. |
| “`ByteBuffer.allocateDirect` được đo cả native storage bằng `getObjectSize`.” | Không nên giả định; wrapper không phải toàn bộ off-heap allocation. |
| “Cộng theo mọi field reference không bị trùng.” | Sai khi có shared objects hoặc cycles. |
| “Tổng shallow estimates bằng RSS.” | Không: RSS bao gồm vùng ngoài heap. |
| “Gọi `System.gc()` rồi lấy delta heap là size chính xác.” | Không: GC không phải phép đo cô lập từng object. |
| “Thay alignment thì mọi object phải đổi kích thước.” | Không: một layout đã là bội số alignment mới có thể không đổi. |
| “Số 16/416/8208 ở ví dụ là output bắt buộc của mọi Java 17.” | Không: số đó thuộc JVM/configuration thử nghiệm. |

### Các bước kiểm tra khi stdout của bạn khác ví dụ

Đầu tiên kiểm tra `java -version` và VM vendor, sau đó các cờ layout/heap, manifest JAR, đúng classpath và phiên bản của app. Xác nhận bạn truyền đúng **object** (Holder hay mảng), đúng chiều dài mảng, và thực sự chạy với `-javaagent`. Nếu mục tiêu là đo retained memory hoặc native memory, đổi sang công cụ thích hợp thay vì cố sửa code để ra một con số “đúng bằng ví dụ”.

## 12. Tự kiểm tra kiến thức

**Câu 1.** Holder chứa reference tới `byte[8192]`. `getObjectSize(holder)` có bắt buộc cộng 8192 bytes dữ liệu mảng không?

**Đáp án:** Không. Holder và array là hai object. Đo Holder chỉ cho estimate shallow của Holder; có thể gọi riêng `getObjectSize(array)` nếu cần estimate shallow của mảng.

**Câu 2.** Cùng mã Java, `Object[100]` được đo 416 byte trong JVM A và 816 byte trong JVM B. Có kết luận một JVM sai không?

**Đáp án:** Không. Khác VM/configuration, ví dụ compressed oops, có thể làm reference slot widths khác nhau. API cho phép approximation implementation-specific.

**Câu 3.** Vì sao `byte[0]` có thể chiếm storage khác 0?

**Đáp án:** Vì nó là một array object thực sự; phải lưu overhead/header và có thể padding. Không có phần tử chỉ có nghĩa payload của phần tử bằng 0.

**Câu 4.** `getObjectSize(null)` trả bao nhiêu?

**Đáp án:** Không trả kích thước: ném `NullPointerException` theo API.

**Câu 5.** Hai `ArrayList` có shallow estimates bằng nhau có chứng minh tổng heap của hai danh sách bằng nhau?

**Đáp án:** Không. Backing arrays và element objects có thể khác lớn; không tự cộng referents.

**Câu 6.** Nếu hai Holder cùng giữ một mảng và bỏ Holder thứ nhất, retained size của Holder thứ nhất có bắt buộc bao gồm mảng không?

**Đáp án:** Không. Mảng còn được Holder thứ hai giữ sống; retained size phụ thuộc graph/GC roots.

**Câu 7.** Có thể hard-code `Holder = 16 byte` cho mọi JVM Java 17 không?

**Đáp án:** Không. Giá trị 16 byte trong bài thuộc một JVM cụ thể; Java SE không bảo đảm header/alignment/reference width.

**Câu 8.** Khi dùng `-XX:-UseCompressedOops`, mọi object đều phải tăng byte theo cùng một tỷ lệ?

**Đáp án:** Không. Các object chứa nhiều reference slots có thể thay đổi rõ, trong khi primitive arrays có thể không đổi ở cấu hình thử nghiệm.

**Câu 9.** Muốn điều tra memory leak, chỉ gọi `getObjectSize(suspectedObject)` đủ chưa?

**Đáp án:** Chưa. Cần số lượng object, allocation rate, reachability, GC roots và có thể retained size qua heap dumps/profilers.

**Câu 10.** Agent có cần manifest `Can-Redefine-Classes: true` để đo `getObjectSize`?

**Đáp án:** Không. Điều kiện cơ bản là có đối tượng `Instrumentation` do JVM cấp; cờ redefine dành cho chức năng thay định nghĩa class đã nạp.

## 13. Tổng kết và tài liệu chính thức

**Năm nguyên tắc quan trọng nhất:**

1. **`getObjectSize(Object)` chỉ trả một ước lượng implementation-specific**, có thể gồm object overhead và thay đổi theo JVM/cấu hình, thậm chí trong một lần invocation.
2. **Đo đúng object được truyền vào**, thường là shallow storage; không đếm đệ quy mảng/collection/graph mà object tham chiếu.
3. **Header, compressed references và alignment ảnh hưởng số byte.** Đừng lấy bảng ví dụ làm công thức chung của Java.
4. **`null` ném `NullPointerException`**; primitive boxing, static fields, backing arrays và native memory dễ gây sai số trong diễn giải.
5. Khi cần **retained heap, allocation hotspots, GC roots hoặc native memory**, dùng heap dump, profiler, JFR, JOL hoặc công cụ native phù hợp chứ không đổi tên shallow estimate thành tổng memory.

Tài liệu tham khảo:

- [Java SE 17 API — `Instrumentation.getObjectSize(Object)`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html#getObjectSize(java.lang.Object))
- [Java SE 17 API — `java.lang.instrument` và Java agent manifest](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html)
- [JVMTI — GetObjectSize, implementation-specific approximation](https://docs.oracle.com/en/java/javase/17/docs/specs/jvmti.html#GetObjectSize)
- [Java SE 17 HotSpot Performance Enhancements — compressed ordinary object pointers](https://docs.oracle.com/en/java/javase/17/vm/java-hotspot-virtual-machine-performance-enhancements.html)
- [OpenJDK JOL — Java Object Layout](https://openjdk.org/projects/code-tools/jol/)
- [JFR — Java Flight Recorder](https://openjdk.org/jeps/328)