# So sánh getObjectSize của các đối tượng trong cùng cấu hình JVM

**Ngữ cảnh:** Java Advance → instrumentation → **Thực nghiệm agent**.

`Instrumentation.getObjectSize(Object)` là một phương thức hữu ích của Java Instrumentation API để **ước lượng lượng bộ nhớ mà một đối tượng cụ thể chiếm trong cách JVM hiện tại triển khai object layout**. Nó rất phù hợp với một thực nghiệm đối chiếu **các đối tượng khác kiểu, cấu trúc field và độ dài mảng trong cùng cấu hình JVM**. Nhưng đây không phải phép đo “object graph chiếm bao nhiêu heap” hay một hàm chuẩn trả về kích thước byte chính xác và bất biến trên mọi máy.

Oracle JDK 17 Javadoc mô tả `getObjectSize` là **implementation-specific approximation** (ước lượng phụ thuộc implementation), chỉ hữu ích để so sánh **trong cùng cách triển khai**, có thể bao gồm một phần hoặc toàn bộ overhead của object; **ước lượng có thể thay đổi ngay trong một lần chạy JVM**. API cũng quy định tham số `null` gây `NullPointerException`. Đây là giới hạn cần ghi trong báo cáo trước khi đọc bất cứ con số nào.

Bài thực nghiệm này sẽ:

1. Tạo **Java startup agent tối thiểu** qua `-javaagent` để nhận `Instrumentation` ở `premain`.
2. Viết **ứng dụng Java 17+ chạy được bằng `javac`/`jar`/`java`**, dùng cùng JVM để đo một tập object mẫu.
3. So sánh object rỗng, object có primitive fields, reference fields, record, mảng primitive, mảng tham chiếu, chuỗi và object có graph tham chiếu.
4. Phân biệt **shallow size** của object với **deep/reachable/retained heap size** của graph.
5. Lập quy tắc giữ cố định runtime/JVM flags, kiểm tra nén tham chiếu, alignment và object/array headers.
6. Giải thích cách đọc stdout có kích thước phụ thuộc máy **mà không bịa số byte cố định**.
7. Chẩn đoán lỗi cấu hình agent, nhận diện so sánh sai, và biết khi nào cần **JOL, JFR, heap dump hoặc profiler** thay cho `getObjectSize`.

> **Kết luận định hướng:** Hãy dùng `getObjectSize` như **một phép đo ước lượng cho một object trong một JVM cụ thể**, không như công cụ tính toàn bộ kích thước những gì object đang tham chiếu, không như số lượng bytes một request đã cấp phát, và không như một đại lượng để so tuyệt đối giữa mọi JDK/GC/kiến trúc.

## 1. Hiểu đúng tên và hợp đồng API

Chữ ký chuẩn:

```java
// Fragment API, không phải class Java độc lập.
long getObjectSize(Object objectToSize);
```

Gói: `java.lang.instrument`, interface `Instrumentation`, có trong module `java.instrument`. Một chương trình Java bình thường **không tự tạo instance `Instrumentation`**. JVM cung cấp nó cho agent qua:

```java
// Fragment: thuộc class có Premain-Class trong agent JAR.
public static void premain(
        String agentArgs, Instrumentation instrumentation) {
    // Lưu handle nếu cần; kiểm soát vòng đời và quyền truy cập.
}
```

Điều cần phân biệt:

| Thuật ngữ | Có phải `getObjectSize` đo không? |
| --- | --- |
| Một **object instance cụ thể** | Có: trả `long` ước lượng byte, theo VM |
| Mảng `byte[]` hay `Object[]` cụ thể | Có: mảng cũng là object; phần tử primitive được lưu inline, slots tham chiếu là phần của mảng |
| Toàn bộ object graph reachable từ một root | **Không tự động** duyệt những object được tham chiếu |
| Toàn bộ String characters + backing storage | **Không tự động** cộng vùng lưu nội dung phía sau field reference |
| Tổng bytes được cấp phát trong quá trình thực thi một method | **Không**, đây là metric allocation, không phải size của một object |
| Retained heap nếu object bị GC thu hồi | **Không**, cần phân tích dominator/retained heap từ heap snapshot |
| Footprint process RSS/native memory/metaspace | **Không** |
| Object header/field layout chính xác theo chuẩn portable | **Không**; chỉ trả ước lượng số byte tổng |
| Địa chỉ object hoặc raw object memory | **Không** |
| Tham số `null` | **Không trả 0**; API ném `NullPointerException` |

### 1.1. “Shallow” có nghĩa gì trong cách diễn giải thông dụng?

Ví dụ:

```text
ReferenceBox
  └── Object value ──────────────► byte[4096]
        (slot tham chiếu)            (object riêng)

getObjectSize(referenceBox):
  thông thường phản ánh bộ nhớ bản thân ReferenceBox
  (header, reference field, padding theo implementation)

getObjectSize(value):
  đo riêng đối tượng byte[4096]
```

Trên JVM phổ biến như HotSpot, `getObjectSize(box)` **không truy đệ quy** tới `byte[4096]`. Nếu chỉ thay kích thước array mà không thay class/layout của `ReferenceBox`, shallow estimate của hai boxes thường giống nhau. **Đó là quan sát về layout của runtime đang xét, không phải cam kết kết quả byte bất biến từ Java SE specification.**

Đừng nhầm với `sizeof` kiểu C/C++ cho một class. Java cho phép VM tự sắp xếp, nén và căn chỉnh layout; cùng source có thể nhận sizes khác trên HotSpot 64-bit và một JVM/kiến trúc khác.

### 1.2. Javadoc cảnh báo điều gì?

Những giới hạn phải ghi đúng:

- **Implementation-specific approximation:** không là kích thước tuyệt đối theo ngôn ngữ Java.
- **Có thể gồm một phần/toàn bộ overhead:** headers và alignment không có contract cố định.
- **Chỉ hữu ích so sánh trong cùng implementation:** khác JVM/vendor/flags không thể quy về một “định luật” chung.
- **Có thể đổi ngay trong cùng invocation JVM:** không yêu cầu hai lần gọi cho một object luôn trả đúng cùng số bytes.
- **`null` gây `NullPointerException`:** không sử dụng 0 làm giá trị thay thế cho null.

Với nhu cầu “so sánh trong cùng cấu hình JVM”, ta sẽ **ghi rõ configuration**, đo các objects trong **một process**, và tránh hardcode kích thước kỳ vọng theo folklore như “Object luôn 16 bytes”.

## 2. Điều gì quyết định object size trên JVM?

Tùy JVM, bộ nhớ một Java object có thể liên quan tới:

- **Object header:** dữ liệu phục vụ runtime như identity/hash/lock/klass metadata; hình thức cụ thể là implementation detail.
- **Instance fields:** primitive data và các slots tham chiếu theo loại và field layout do JVM chọn.
- **Array header/length:** mảng có chiều dài và các phần tử lưu theo cơ chế array layout.
- **Alignment/padding:** JVM có thể căn object tới biên 8, 16 hay một giá trị khác; các byte đệm không tương ứng một Java field.
- **Compressed references:** trên nhiều cấu hình HotSpot 64-bit, reference slots có thể được nén; kết quả không đơn giản bằng `8 × số reference fields`.
- **Kiến trúc/JDK/GC/VM options:** implementation, runtime version, heap settings, alignment, compressed class pointers có thể thay giá trị.

**Đây không phải công thức portable để tự cộng field sizes.** JDK có thể đặt field theo thứ tự khác source, có padding, inherited fields và các chi tiết layout không hiển thị qua reflection thông thường.

### 2.1. So sánh một object rỗng và object nhiều fields

Một object không có instance fields **vẫn cần runtime representation**. Thêm một field `int` không nhất thiết làm size estimate tăng 4 bytes: padding sẵn có đôi khi đủ chứa field mới. Thêm nhiều `long` hoặc references có thể làm vượt qua một ngưỡng alignment.

| Loại | Vì sao đáng đo? | Điều **không** nên kết luận |
| --- | --- | --- |
| `new Object()` | Baseline object tối giản | “Mọi object đều bằng số đó cộng tổng field types” |
| Class rỗng tự định nghĩa | Header, class metadata association | “Tên class dài hơn làm object lớn hơn” |
| Class có `int` | Primitive field có thể dùng padding | “Chính xác lớn hơn 4 bytes” |
| Class có hai `long` | Thêm payload category-2 | “Luôn tăng đúng 16 bytes” |
| Class có references | Chỉ lưu reference slots trong shallow object | “Tự tính cả các object được trỏ tới” |
| `record Point(int,int)` | Record vẫn là object theo layout VM | “Record miễn object header hoặc luôn nhỏ hơn class” |

### 2.2. Với mảng, cần xét kiểu phần tử và độ dài

`byte[64]` chứa 64 giá trị byte inline. `long[64]` chứa 64 giá trị long inline. `Object[64]` chứa 64 **reference slots**, không chứa bản thân 64 object được chỉ tới.

Khái niệm mô hình, **không phải công thức định lượng đảm bảo**:

```text
Shallow size của primitive array ~
  array header + inline element payload + padding

Shallow size của reference array ~
  array header + reference slots + padding

Không gồm object graph của các phần tử tham chiếu.
```

Cần đo các độ dài khác nhau (0,1,7,8,64,...) để nhìn các **bậc alignment**, không giả định độ lớn tăng tuyến tính đúng từng byte. Với JVM và layout cụ thể có thể quan sát khoảng bằng nhau giữa nhiều độ dài gần nhau do padding.

## 3. Thiết kế thí nghiệm: cố định cấu hình trước khi đo

Một phép so công bằng cần ghi lại:

| Thuộc tính | Ví dụ cách lấy | Lý do |
| --- | --- | --- |
| JVM vendor/implementation | `java.vm.name`, `java.vendor` | Object layout là implementation detail |
| Java runtime version | `java.runtime.version`, `java -version` | Version có thể thay headers/layout |
| OS và CPU architecture | `os.name`, `os.arch` | Pointer width/ABI có thể khác |
| Heap settings | `-Xms`, `-Xmx` | HotSpot ergonomics, compressed references có thể phụ thuộc heap |
| `UseCompressedOops` | HotSpot `PrintFlagsFinal` | Nén ordinary object pointers |
| `UseCompressedClassPointers` | HotSpot `PrintFlagsFinal` | Layout class metadata reference |
| `ObjectAlignmentInBytes` | HotSpot `PrintFlagsFinal` | Căn chỉnh kích thước object |
| GC implementation | JVM flags và VM logs | Runtime layout/overhead policy có thể khác |
| Agent set | command line đầy đủ | Các agents khác có thể tác động setup/objects |
| Container memory/CPU | Runtime limits | Cấu hình VM và measurement environment |

Trong **phép so sánh chính**, dùng **một JVM process duy nhất** cho toàn bộ objects. Mọi đối tượng đo được tạo trực tiếp trong `main` sau khi agent có `Instrumentation`, tránh “object A từ cấu hình 1, object B từ cấu hình 2”.

Không ép JVM flags khi chưa biết vendor hỗ trợ. Những ví dụ `-XX:...` ở phần sau là **HotSpot-specific experiments**, không phải API Java chuẩn.

### 3.1. Kiểm tra JVM trước khi build

```bash
java -version
javac -version
jar --help
```

Với HotSpot JDK 17 trên Bash/Linux, có thể kiểm tra những lựa chọn đáng quan tâm:

```bash
java -XX:+PrintFlagsFinal -version 2>&1 \
  | grep -E 'UseCompressedOops|UseCompressedClassPointers|ObjectAlignmentInBytes'
```

Trên PowerShell:

```powershell
java -XX:+PrintFlagsFinal -version 2>&1 | Select-String 'UseCompressedOops|UseCompressedClassPointers|ObjectAlignmentInBytes'
```

`PrintFlagsFinal` có thể in nhiều thông tin và định dạng khác nhau; dùng nó như **bằng chứng cấu hình** chứ không như một output bytes cố định. Nếu VM không chấp nhận flag, bỏ flag đó hoặc đổi đúng cấu hình được vendor hỗ trợ; không suy ra một flag HotSpot là portable.

## 4. Cấu trúc project Java 17+ không cần dependency ngoài

```text
object-size-lab/
├── agent.mf
├── src/
│   └── demo/
│       ├── SizeAgent.java
│       └── CompareSizes.java
├── build/
│   ├── agent/                (tạo khi compile)
│   └── app/                  (tạo khi compile)
└── size-agent.jar            (tạo bằng jar)
```

Mục tiêu chia tách:

- `SizeAgent.java` được đóng gói vào agent JAR có `Premain-Class`.
- `CompareSizes.java` là ứng dụng, được chạy trong **cùng process** với startup agent.
- `CompareSizes` dùng public static API nhỏ của `SizeAgent`, vì vậy phải đưa **agent JAR lên application classpath** ngoài việc khai báo `-javaagent`.
- Không có thư viện native, Maven, ASM hay Byte Buddy.
- Cả hai class đều compile với `javac --release 17`.

Tạo một folder mới rỗng để làm bài. Không cần chạy `System.gc()` để “ổn định” phép đo: GC request có thể không được thực hiện, và Javadoc cho phép estimate thay đổi ngay trong cùng process.

## 5. Mã `SizeAgent.java`: nhận Instrumentation từ JVM

Lưu tại `src/demo/SizeAgent.java`:

```java
package demo;

import java.lang.instrument.Instrumentation;
import java.util.Objects;

public final class SizeAgent {
    private static volatile Instrumentation instrumentation;

    private SizeAgent() {}

    public static void premain(
            String agentArgs, Instrumentation instance) {
        instrumentation = Objects.requireNonNull(instance);
        System.out.println("PREMAIN_ARGS=" + agentArgs);
    }

    public static boolean active() {
        return instrumentation != null;
    }

    public static long sizeOf(Object object) {
        Instrumentation current = instrumentation;
        if (current == null) {
            throw new IllegalStateException(
                    "Start JVM with -javaagent:size-agent.jar");
        }
        return current.getObjectSize(object);
    }
}
```

**Giải thích:**

1. JVM khởi động agent từ manifest và gọi `premain` **trước application `main`**.
2. `Instrumentation` không tự `new` được; instance do JVM truyền vào.
3. `volatile` giúp published reference rõ hơn nếu app sau đó đọc từ thread khác. Lab chỉ gọi đo từ main thread, nhưng một agent thật có thể truy cập từ nhiều threads.
4. `sizeOf(Object)` giữ nguyên hợp đồng của API: truyền `null` qua tới `getObjectSize` khi agent active sẽ ném `NullPointerException`, **không tự trả 0**.
5. Nếu quên `-javaagent` nhưng đã đặt JAR trên classpath, `active()` là `false`. Điều này phân biệt **“class agent có trên classpath”** với **“JVM đã thực sự khởi động agent”**.
6. Method không thay đổi bytecode/class model của đối tượng đang được đo; nó chỉ yêu cầu JVM trả estimate cho một object hiện có.

**Lưu ý:** không giữ `Instrumentation` chỉ để một JAR library thông thường gọi vào khi agent chưa chạy. Nếu JVM không được khởi động với agent, Java SE không cung cấp một API chung để ứng dụng lấy handle `Instrumentation` từ chỗ bất kỳ.

## 6. Mã `CompareSizes.java`: tập mẫu đa dạng nhưng có kiểm soát

Lưu tại `src/demo/CompareSizes.java`:

```java
package demo;

import java.util.Arrays;
import java.util.Locale;

public final class CompareSizes {
    private CompareSizes() {}

    static final class Empty {}

    static final class OneInt {
        int value = 7;
    }

    static final class TwoLongs {
        long first = 1L;
        long second = 2L;
    }

    static final class RefBox {
        Object value;

        RefBox(Object value) {
            this.value = value;
        }
    }

    static final class Pair {
        Object left;
        Object right;

        Pair(Object left, Object right) {
            this.left = left;
            this.right = right;
        }
    }

    record Point(int x, int y) {}

    private static void show(String label, Object value) {
        long bytes = SizeAgent.sizeOf(value);
        System.out.printf(
                Locale.ROOT, "SIZE %-23s %d%n", label, bytes);
    }

    public static void main(String[] args) {
        System.out.println("MAIN_BEGIN");
        System.out.println("AGENT_ACTIVE=" + SizeAgent.active());

        if (!SizeAgent.active()) {
            System.out.println("MEASUREMENTS_SKIPPED=true");
            return;
        }

        System.out.println(
                "VM_NAME=" + System.getProperty("java.vm.name"));
        System.out.println(
                "RUNTIME=" + System.getProperty("java.runtime.version"));
        System.out.println(
                "ARCH=" + System.getProperty("os.arch"));

        System.out.println("SECTION=objects");
        show("new Object()", new Object());
        show("Empty", new Empty());
        show("OneInt", new OneInt());
        show("TwoLongs", new TwoLongs());
        show("record Point", new Point(1, 2));

        System.out.println("SECTION=arrays");
        show("byte[0]", new byte[0]);
        show("byte[1]", new byte[1]);
        show("byte[7]", new byte[7]);
        show("byte[8]", new byte[8]);
        show("byte[64]", new byte[64]);
        show("int[0]", new int[0]);
        show("int[8]", new int[8]);
        show("long[8]", new long[8]);
        show("Object[8]", new Object[8]);

        byte[] small = new byte[1];
        byte[] large = new byte[4096];
        RefBox smallBox = new RefBox(small);
        RefBox largeBox = new RefBox(large);

        System.out.println("SECTION=references");
        show("RefBox(small)", smallBox);
        show("RefBox(large)", largeBox);
        show("referent byte[1]", small);
        show("referent byte[4096]", large);

        Object[] none = new Object[8];
        Object[] repeated = new Object[8];
        Arrays.fill(repeated, large);
        show("Object[8] nulls", none);
        show("Object[8] aliases", repeated);
        System.out.println(
                "ARRAY_LENGTH_EQUAL=" + (none.length == repeated.length));

        Pair alias = new Pair(large, large);
        Pair distinct =
                new Pair(new byte[4096], new byte[4096]);
        show("Pair(shared)", alias);
        show("Pair(distinct)", distinct);

        System.out.println(
                "ALIAS_SHARED=" + (alias.left == alias.right));
        System.out.println(
                "DISTINCT_REFERENTS="
                        + (distinct.left != distinct.right));

        System.out.println("SECTION=strings");
        String shortText = new String("a");
        String longText = new String("a".repeat(4096));
        show("String(length=1)", shortText);
        show("String(length=4096)", longText);

        boolean nullThrowsNpe = false;
        try {
            SizeAgent.sizeOf(null);
        } catch (NullPointerException expected) {
            nullThrowsNpe = true;
        }
        if (!nullThrowsNpe) {
            throw new AssertionError("getObjectSize(null) contract");
        }

        System.out.println("NULL_THROWS_NPE=true");
        System.out.println("DONE=true");
    }
}
```

### 6.1. Vì sao mã này chạy trên Java 17?

- `record Point` là tính năng chính thức của Java 16+ nên biên dịch với `--release 17`.
- `String.repeat(int)` có từ Java 11.
- `java.lang.instrument` là API chuẩn.
- `Arrays.fill` và `Locale.ROOT` có sẵn.
- Không dùng reflection vào private fields của JDK, không dùng `Unsafe`, không dùng preview features.
- Chỉ cần hai source files và một agent JAR đúng manifest.

### 6.2. Vì sao không assert hardcoded kích thước?

Mã chỉ in số trả về từ **JVM thực tế**. Ta **cố ý không viết**:

```java
// Anti-pattern, không phải assertion portable.
assert SizeAgent.sizeOf(new Object()) == 16;
```

Số “16” có thể gặp trên một số HotSpot configurations, nhưng **không nằm trong hợp đồng `Instrumentation.getObjectSize`**. Java có object alignment, compressed references và những implementation khác; thậm chí Javadoc cho phép estimate thay đổi trong một lần JVM invocation.

Điều có thể assert portable ở đây là **`getObjectSize(null)` phải ném `NullPointerException`**. Các so sánh kích thước còn lại được thực hiện như **observation** kèm JVM config, không biến folklore về layout thành điều kiện pass/fail.

### 6.3. Vì sao tạo sẵn object cho phép đo?

`RefBox` và `Pair` được tạo thành local variables trước khi gọi `show`. Điều này làm dễ nhận ra **object nào đang được đo** và **object nào chỉ được tham chiếu**; không dùng `Runtime.totalMemory()-freeMemory()` rồi suy kích thước một allocation đơn lẻ từ chênh lệch heap.

`getObjectSize` không cho địa chỉ Java object, không cho field offsets và không trả graph reachability. Nếu cần phân tích layout chi tiết, dùng tool như OpenJDK **JOL**; nếu cần retained heap, dùng heap analyzer.

## 7. Manifest `agent.mf`

Nội dung tệp:

```text
Manifest-Version: 1.0
Premain-Class: demo.SizeAgent
```

**Kết thúc tệp bằng một newline.** `Premain-Class` là **binary class name** dạng `demo.SizeAgent`, không phải đường `demo/SizeAgent.class` và không phải `SizeAgent.java`.

Không cần thêm `Can-Retransform-Classes` hoặc `Can-Redefine-Classes` vì lab chỉ gọi `getObjectSize`. Không cần `Agent-Class` vì không dùng attach động. Agent không chèn transformer và không đụng tới `classfileBuffer`.

## 8. Biên dịch và chạy trên Bash (Linux/macOS)

Đứng ở root `object-size-lab`:

```bash
mkdir -p build/agent build/app

javac --release 17 -encoding UTF-8 \
    -d build/agent src/demo/SizeAgent.java

jar --create --file size-agent.jar \
    --manifest agent.mf -C build/agent .

javac --release 17 -encoding UTF-8 \
    -cp size-agent.jar \
    -d build/app src/demo/CompareSizes.java

jar --list --file size-agent.jar
```

Kiểm tra JAR có tối thiểu:

```text
META-INF/MANIFEST.MF
demo/SizeAgent.class
```

Lệnh `jar --list` có thể in thêm directory entries và thứ tự khác; không phải mọi dòng output đều được hardcode ở đây.

### 8.1. Baseline: class có trên classpath nhưng không nạp agent

```bash
java -cp "build/app:size-agent.jar" demo.CompareSizes
```

**Stdout chính xác của chương trình:**

```text
MAIN_BEGIN
AGENT_ACTIVE=false
MEASUREMENTS_SKIPPED=true
```

Vì không có `-javaagent`, JVM không gọi `premain`, nên reference `Instrumentation` vẫn `null`. Có `size-agent.jar` trên `-cp` **chỉ cho phép liên kết class `SizeAgent`**, không biến nó thành active agent.

### 8.2. Đo bằng startup agent

```bash
java -javaagent:size-agent.jar=lab \
    -cp "build/app:size-agent.jar" demo.CompareSizes
```

**Các dòng xác định theo logic và thứ tự**:

```text
PREMAIN_ARGS=lab
MAIN_BEGIN
AGENT_ACTIVE=true
VM_NAME=...                 (giá trị từ JVM hiện chạy)
RUNTIME=...                 (phiên bản runtime hiện chạy)
ARCH=...                    (kiến trúc thực tế)
SECTION=objects
SIZE new Object()            ... (đo bằng getObjectSize)
SIZE Empty                   ... (đo thực tế)
SIZE OneInt                  ... (đo thực tế)
SIZE TwoLongs                ... (đo thực tế)
SIZE record Point            ... (đo thực tế)
SECTION=arrays
...                          (các dòng SIZE của các mảng)
SECTION=references
...                          (các dòng SIZE của RefBox, Pair và referents)
ARRAY_LENGTH_EQUAL=true
ALIAS_SHARED=true
DISTINCT_REFERENTS=true
SECTION=strings
...                          (hai dòng SIZE của String)
NULL_THROWS_NPE=true
DONE=true
```

**Đây là cấu trúc output được chú giải, không phải stdout nguyên văn**: dấu `...` đại diện những số JVM thực tế trả về và phần dòng `SIZE` lược bớt. Không có “kích thước byte chuẩn” để điền sẵn cho mọi JVM. Những dòng cố định như `PREMAIN_ARGS=lab`, `AGENT_ACTIVE=true`, `ALIAS_SHARED=true`, `NULL_THROWS_NPE=true` và `DONE=true` xuất phát trực tiếp từ source.

### 8.3. Windows PowerShell

```powershell
New-Item -ItemType Directory -Force build/agent,build/app | Out-Null

javac --release 17 -encoding UTF-8 -d build/agent src/demo/SizeAgent.java
jar --create --file size-agent.jar --manifest agent.mf -C build/agent .
javac --release 17 -encoding UTF-8 -cp size-agent.jar -d build/app src/demo/CompareSizes.java

java -cp "build/app;size-agent.jar" demo.CompareSizes
java -javaagent:size-agent.jar=lab -cp "build/app;size-agent.jar" demo.CompareSizes
```

**Dấu phân cách classpath**: trên Unix thông thường là dấu hai chấm `:`; trên Windows là chấm phẩy `;`. Nếu copy lệnh Bash `-cp "build/app:size-agent.jar"` sang Windows, JVM có thể không tìm thấy main class. `-javaagent` và `-cp` là hai chức năng khác nhau; dùng **cả hai** theo cấu hình của lab.

## 9. Cách giải thích các dòng đo

### 9.1. `new Object()` và `Empty`

Cả hai đều là Java objects; `Empty` không có instance fields nhưng không “miễn phí”. Trong một runtime, chúng thường có footprint tương tự nếu layout policy giống nhau. Tuy nhiên không khẳng định kết quả bằng nhau từ spec. Nếu số đo bằng nhau, đó là **quan sát trong cấu hình đang chạy**, không chứng minh mọi classes rỗng luôn chiếm cùng bytes trên mọi JDK.

### 9.2. `OneInt`, `TwoLongs` và `Point`

So kích thước object có một `int`, hai `long` và record có hai `int`. Đừng cộng cố định các kiểu field vào size của `Object`:

```text
Không nên giả định:
size(OneInt) = size(Object) + 4
size(TwoLongs) = size(Object) + 16
size(Point) = size(Object) + 8
```

JVM có thể tận dụng padding và reorder fields. Điều cần so là **giá trị đo trên các instance trong cùng process**. Từ đó đặt câu hỏi: thay đổi nào làm tăng số bậc alignment, hay trường hợp nào thêm field mà estimate vẫn chưa đổi?

### 9.3. `byte[]` với độ dài 0, 1, 7, 8 và 64

Mảng có header và length ngay cả khi `length=0`. Primitive `byte[]` chứa elements inline, nên khi tăng độ dài đủ lớn, shallow size được dự kiến tăng. Nhưng do alignment, `byte[1]` và `byte[7]` **có thể** cùng estimate trên một HotSpot configuration. Không áp đặt một công thức “header luôn 16 bytes” từ Java language specification.

### 9.4. `int[8]`, `long[8]` và `Object[8]`

Các mảng cùng length không có cùng payload width. Trong cách triển khai HotSpot thông dụng:

- `int[]` phần tử kiểu primitive int.
- `long[]` phần tử primitive long, thường lớn hơn payload của int tại cùng length.
- `Object[]` chứa **reference slots**; độ rộng phụ thuộc compressed ordinary object pointers và JVM layout.

Vì thế không thể thay công thức `size(Object[8]) = 8 × size(Object)`: mảng tham chiếu **không chứa inline các Object instances**.

### 9.5. `RefBox(small)` và `RefBox(large)`

`smallBox.value` trỏ tới `byte[1]`; `largeBox.value` trỏ tới `byte[4096]`. Hai boxes cùng class, mỗi box chỉ có **một reference field**; shallow size của boxes thường không phụ thuộc kích thước referent trên HotSpot.

Đối chiếu:

```text
getObjectSize(smallBox)       -> bản thân RefBox
getObjectSize(largeBox)       -> bản thân RefBox
getObjectSize(small)          -> byte[1]
getObjectSize(large)          -> byte[4096]

Không phải:
getObjectSize(largeBox) = getObjectSize(RefBox)
                        + getObjectSize(large)
```

Đây là minh họa mạnh nhất cho khác biệt **reference slot** và **referenced object payload**.

### 9.6. `Object[8] nulls` và `Object[8] aliases`

Hai arrays có cùng class và length. Một array có tám giá trị `null`, array kia có tám references **cùng trỏ tới một object `large`**. Chúng chứa cùng số slots. Việc các slots tham chiếu tới object lớn không làm mảng **tự chứa** object đó.

Khi muốn tính reachable memory của object graph:

- Array instance và referenced object là **hai nodes**.
- Tám references cùng trỏ về một node chỉ được tính **một lần** nếu bạn muốn đếm unique reachable objects.
- Nếu cộng mỗi cạnh “reference → object” như một object mới, sẽ **đếm trùng**.

### 9.7. `Pair(shared)` so `Pair(distinct)`

`Pair(shared)` có hai fields tham chiếu **cùng một byte array**; `Pair(distinct)` có hai references tới **hai arrays độc lập**. Cả hai Pair objects có cấu trúc fields giống nhau, nên shallow size có thể giống nhau, dù reachable object graph có cardinality khác nhau.

`ALIAS_SHARED=true` và `DISTINCT_REFERENTS=true` là **kiểm tra identity của references**, không phải số byte. Phân biệt được sharing là điều kiện cần nếu sau này viết một công cụ duyệt graph tránh đếm trùng.

### 9.8. `String(length=1)` so `String(length=4096)`

Trong Java 17 HotSpot, `String` thường giữ dữ liệu ký tự trong một backing `byte[]` (compact strings được giới thiệu từ JDK 9). `getObjectSize(String)` **không tự cộng toàn bộ backing byte array**. Vì thế đo `String` ngắn và dài có thể thấy shallow estimates tương tự dù số ký tự khác nhau rất nhiều.

**Không** dùng `String.length() × 2` làm footprint của `String`: layout có thể dùng compact strings, encoding/coder, shared storage hoặc chính sách VM khác; các backing arrays còn có headers và alignment. Không truy cập private `String.value` bằng reflection + `--add-opens` chỉ để hoàn thành bài này; nó phụ thuộc JDK internals, không phải hướng tiếp cận portable.

## 10. Ghi nhận dữ liệu đo mà không trộn cấu hình

Gợi ý ghi kết quả từ **một invocation** bằng các nhóm:

| Nhóm | Đối tượng | Câu hỏi cần trả lời |
| --- | --- | --- |
| Object cơ bản | `Object`, `Empty` | Có khác nhau không? |
| Primitive fields | `OneInt`, `TwoLongs`, `Point` | Trường dữ liệu và padding ảnh hưởng thế nào? |
| Primitive arrays | `byte[0/1/7/8/64]`, `int[8]`, `long[8]` | Ảnh hưởng type, length và alignment |
| Reference array | `Object[8]`, `Object[8] nulls`, `Object[8] aliases` | Số slots và nội dung references |
| Holder | `RefBox(small)`/`RefBox(large)` | Referent size có được tính đệ quy không? |
| Alias graph | `Pair(shared)`/`Pair(distinct)` | Phân biệt shallow và graph size |
| Text | `String(length=1/4096)` | String object vs backing storage |

**Không cần có số sẵn trong bảng** để bài học là hoàn chỉnh: code sẽ in từng giá trị `long` thật. Khi nộp báo cáo, copy output thực tế, thêm JVM vendor/version, OS/arch, JVM flags và tên workload. Không lấy bảng kết quả trên mạng từ JVM không rõ flags rồi coi đó là size chính xác của hệ thống mình.

### 10.1. Ví dụ cách tính delta sau khi có output

Giả sử đo được `s0 = getObjectSize(new byte[0])` và `s64 = getObjectSize(new byte[64])`, ta có:

```text
delta_bytes = s64 - s0

Chỉ diễn giải delta cho cùng loại array,
cùng process và cùng measurement setup.
```

Nếu muốn tỷ lệ, có thể tính `s64 / s0` khi `s0 > 0`. Tuy nhiên tỷ lệ đó là **tỷ lệ shallow estimates** gồm headers/padding, không phải “payload compression ratio”. Không suy ra GC sẽ tiết kiệm chính xác `delta_bytes` khi bỏ một reference.

### 10.2. Vì sao không dùng thời gian chạy của `getObjectSize` làm size?

`System.nanoTime()` đo **thời lượng**, đơn vị nanoseconds; `getObjectSize` trả **ước lượng byte**. Đó là hai đại lượng khác nhau. Đừng đặt `long before = System.nanoTime()` rồi suy số byte từ `System.nanoTime()-before`. Nếu cần benchmark overhead của agent call, sử dụng JMH và các phương pháp microbenchmark, không thay đổi định nghĩa của size metric.

## 11. Thí nghiệm phụ: thay JVM flags có kiểm soát

**Thí nghiệm chính yêu cầu cùng cấu hình.** Sau khi đã ghi một baseline đầy đủ, bạn có thể chạy **một process mới** với HotSpot flags khác để nghiên cứu ảnh hưởng của layout. Đây là **một thí nghiệm riêng để thấy sự phụ thuộc VM**, không trộn các số của hai invocations rồi tuyên bố phép đo “cùng cấu hình”.

Trên 64-bit HotSpot JDK 17, nếu các options được vendor hỗ trợ:

```bash
# Lần A: cấu hình minh họa cố định heap.
java -Xms256m -Xmx256m \
  -javaagent:size-agent.jar=lab \
  -cp "build/app:size-agent.jar" demo.CompareSizes

# Lần B: tắt compressed ordinary object pointers.
java -Xms256m -Xmx256m -XX:-UseCompressedOops \
  -javaagent:size-agent.jar=lab \
  -cp "build/app:size-agent.jar" demo.CompareSizes

# Lần C: thử object alignment 16 bytes trên HotSpot.
java -Xms256m -Xmx256m -XX:ObjectAlignmentInBytes=16 \
  -javaagent:size-agent.jar=lab \
  -cp "build/app:size-agent.jar" demo.CompareSizes
```

**Các flags `-XX:...` là HotSpot-specific; không bảo đảm mọi JVM chấp nhận.** Không yêu cầu cả B và C phải luôn “lớn hơn A” cho từng loại object. Compressed class pointers, heap ergonomics, field packing, padding và object layout có thể tương tác; đôi khi alignment làm một số kích thước tăng theo bậc, có trường hợp thay đổi không thấy trên object nhỏ.

Mỗi lần chạy gồm một **cấu hình JVM khác**. Phân tích nên tách:

- So sánh **nội bộ A**: object này so object kia trong cùng process A.
- So sánh **nội bộ B**: object này so object kia trong cùng process B.
- Nếu so A với B: ghi rõ đây là **thí nghiệm về config**, không là kết luận portable về JVM nói chung.

### 11.1. Tại sao compressed oops có thể ảnh hưởng?

Trên nhiều JVM HotSpot 64-bit, compressed ordinary object pointers lưu reference theo dạng nén ở nhiều vị trí. Khi tắt, một số object có nhiều reference fields hoặc `Object[]` có thể cần vùng lưu trữ khác. Nhưng không cần biết kích thước pointer từ C compiler hay `sun.arch.data.model` để phán kết quả: hãy đọc **VM flags thực tế** và **`getObjectSize` output**.

Không giả định `-XX:-UseCompressedOops` chắc chắn tạo chính xác `+4 bytes` trên mỗi field; alignment có thể che phần tăng hoặc làm tăng theo từng bậc.

### 11.2. Tại sao alignment thay số size?

Nếu runtime căn object theo `ObjectAlignmentInBytes`, một field mới có thể nằm trong padding đã có hoặc buộc tổng footprint qua ranh giới alignment kế tiếp. Với `-XX:ObjectAlignmentInBytes=16`, một số object nhỏ có thể bị căn lên bội số của 16. **Không** suy từ lệnh rằng mọi object trong mọi JVM phải có byte count chia hết 16 theo Java SE contract; option là chính sách implementation cụ thể.

## 12. Phân biệt size hiện tại với allocation/retained/heap footprint

Một câu hỏi “Object này chiếm bao nhiêu RAM?” có thể có bốn ý nghĩa khác nhau:

| Câu hỏi | Cần công cụ/cách tiếp cận nào? |
| --- | --- |
| Một object có footprint ước lượng bao nhiêu? | `Instrumentation.getObjectSize(object)` |
| Object graph reachable từ root gồm tổng bao nhiêu bytes? | Duyệt graph + identity de-dup + layout estimates, hoặc heap analysis |
| Bỏ root object có giải phóng bao nhiêu heap? | **Retained heap/dominator** analysis, không đơn thuần cộng sizes |
| Một request đã allocate bao nhiêu bytes? | JFR allocation events, allocation profiling, JMH `gc.alloc.rate.norm` hoặc công cụ tương ứng |

### 12.1. Deep size không chỉ là cộng `getObjectSize` của từng field

Giả sử:

```text
          Pair
          /  \
         /    \
       ref    ref
         \    /
          \  /
         byte[4096]
```

Nếu cộng `getObjectSize(pair) + getObjectSize(pair.left) + getObjectSize(pair.right)` sẽ **đếm byte array hai lần** khi hai references trỏ cùng object. Muốn tính một **reachable size estimate**, cần:

1. Duyệt object graph theo reference relationships.
2. Dùng **object identity** (ví dụ `IdentityHashMap`) để tránh đếm trùng.
3. Phân biệt primitive fields với reference fields, đặc biệt arrays.
4. Đối phó cycles, static references, weak/soft references, classloader roots.
5. Có quyền đọc instance fields của target objects; JPMS strong encapsulation có thể ngăn reflection vào JDK internals.
6. Quyết định inclusion policy: class objects/metaspace? off-heap buffers? shared interned objects? external native memory?
7. Chấp nhận rằng tổng các estimates vẫn không phải retained heap.

Đây là **quy trình phân tích**, không phải đoạn mã Java có thể hoàn tất bằng vài dòng. Không tự thêm `--add-opens java.base/java.lang=ALL-UNNAMED` vào production chỉ để quét sâu `String.value`; điều đó mở rộng phạm vi truy cập và vẫn chưa giải quyết retained heap.

### 12.2. Retained heap khác reachable heap

Object X **có thể tham chiếu** tới Y nhưng Y cũng được tham chiếu bởi một root khác. Bỏ X không nhất thiết giải phóng Y. **Retained size** thường liên quan đến dominator tree: các objects chỉ còn reachable nhờ X. `getObjectSize(X)` không chứa thông tin dominator tree, GC roots hoặc inbound references.

Ví dụ:

```text
Root A -> X -> Y
Root B ------> Y
```

Y reachable từ X, nhưng bỏ X **không** làm Y chắc chắn thu hồi vì Root B còn giữ Y. Do đó không thể dùng `getObjectSize(X) + getObjectSize(Y)` làm lượng RAM được giải phóng nếu xóa reference A→X.

### 12.3. Allocation profiler không thay cho object size

Đo chênh lệch:

```java
// Anti-pattern, không phải phép đo size một object.
Runtime r = Runtime.getRuntime();
long before = r.totalMemory() - r.freeMemory();
Object value = new Object();
long after = r.totalMemory() - r.freeMemory();
long guessed = after - before;
```

Phép trừ trên chịu ảnh hưởng allocations khác, GC, thread activity, TLAB, JIT escape analysis và runtime bookkeeping. Nó **không thay thế `getObjectSize(value)`**, cũng không là metric retained heap đáng tin.

## 13. Dùng JOL/JFR/heap analyzer khi nào?

- **JOL (Java Object Layout)**: thư viện/công cụ OpenJDK giúp khảo sát field offsets, headers, alignment/padding ở VM cụ thể. Hữu ích khi muốn hiểu **vì sao** `getObjectSize` cho kết quả như đã đo. Nó có cơ chế truy cập VM internals tùy JDK và có thể cần flags; không phải Java SE API chuẩn.
- **JFR (Java Flight Recorder)**: giúp quan sát allocation hotspots, GC và sự kiện runtime theo thời gian. Dùng khi câu hỏi là “đoạn code này sinh bao nhiêu object/bytes?”, không phải một object cụ thể có size gì.
- **Heap dump + analyzer (Eclipse MAT hoặc công cụ tương đương)**: cho thống kê object counts, shallow/retained sizes và paths to GC roots tại snapshot. Hữu ích để giải thích memory leak.
- **`jcmd GC.class_histogram`/heap histograms**: hữu ích để xem tổng số instances/bytes theo class trên HotSpot tại thời điểm đo, nhưng không phải size của một object riêng và có thể ảnh hưởng application.
- **JMH**: đo overhead/time/allocation rate của mã tính size hoặc code tạo objects trong controlled forks, tránh benchmark thủ công với timer noise.

**Không có công cụ nào hoàn toàn thay thế công cụ khác**. Bài này tập trung vào `getObjectSize`; JOL/JFR/MAT là hướng đi tiếp theo khi câu hỏi vượt khỏi shallow estimate.

## 14. Lỗi điển hình và hướng chẩn đoán

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `AGENT_ACTIVE=false` | Có agent JAR trên classpath nhưng thiếu `-javaagent` | Thêm `-javaagent:size-agent.jar=lab` **trước** main class |
| Startup báo thiếu `Premain-Class` | Manifest không chứa entry hoặc JAR sai | Đọc `META-INF/MANIFEST.MF`, build lại |
| JVM không tìm `demo.SizeAgent` | Manifest binary name và JAR class entry không khớp | `jar --list`, kiểm tra `demo/SizeAgent.class` |
| `ClassNotFoundException: demo.CompareSizes` | `-cp` dùng sai separator/path | Unix `:`, Windows `;`, kiểm tra `build/app` |
| `IllegalStateException` khi gọi sizeOf | `premain` chưa chạy nhưng app gọi agent API | Chạy bằng startup agent, kiểm tra active flag |
| `NullPointerException` khi sizeOf(null) | Đây là hợp đồng chuẩn của getObjectSize | Kiểm thử NPE; không coi null là object 0 byte |
| Array sizes khác số trên blog | JDK/vendor, alignment, compressed references khác | Ghi VM config và so **trong cùng process** |
| `Object[8]` “nhỏ hơn 8 objects” | Object[] chứa reference slots, không chứa các đối tượng được trỏ tới | Đo referents riêng |
| `RefBox(large)` không lớn hơn `RefBox(small)` | Shallow size của box không cộng referred array | Đo `byte[4096]` riêng; giải thích graph |
| `String(long)` và `String(short)` gần giống | `getObjectSize(String)` không đếm backing content | Dùng heap analysis nếu cần total footprint |
| Mỗi số đo khác nhau giữa two runs | VM flags/JDK/GC/ergonomics khác; estimate có thể đổi | Pin runtime config và ghi variability |
| Thêm `int` field nhưng size không tăng | Padding/alignment có thể hấp thụ field | Dùng JOL để xem layout |
| Mã đọc `String.value` bị `InaccessibleObjectException` | JPMS đóng private java.base internals | Tránh reflection private trong lab |
| Heap used delta không khớp `getObjectSize` | Allocation metric có GC/JIT/TLAB interference | Dùng công cụ đúng loại |
| “Retained size” không giống getObjectSize | Retained graph/dominator khác shallow | Heap dump/MAT, paths to GC roots |
| `-XX:-UseCompressedOops` bị từ chối | JVM không hỗ trợ flags HotSpot hoặc runtime policy | Không dùng flags không tương thích |
| `-XX:ObjectAlignmentInBytes=16` không đổi mọi đối tượng | Padding, layout, VM policy | Đo từng type; không gán quy luật cố định |
| Agent compiled Java mới không chạy JVM17 | Bytecode major quá cao | `javac --release 17` và test runtime đích |
| Cần đo CPU/GC overhead nhưng chỉ có size | Hai đại lượng khác nhau | JFR/JMH/profiler thích hợp |

## 15. Checklist thực nghiệm

- [ ] Xác minh JDK, vendor, architecture và VM flags trước khi so sánh.
- [ ] Xác định đúng câu hỏi: **shallow estimate** hay **reachable/retained/allocated bytes**.
- [ ] Dùng `-javaagent` và manifest `Premain-Class` hợp lệ để lấy `Instrumentation`.
- [ ] Chạy baseline không agent: `AGENT_ACTIVE=false`, không có phép đo.
- [ ] Chạy có agent: `PREMAIN_ARGS=lab` trước `MAIN_BEGIN`, active=true.
- [ ] Đo tất cả objects trong cùng JVM process/configuration.
- [ ] Không gán số byte hardcoded theo ví dụ của máy khác.
- [ ] So `Object`/`Empty`/primitive fields/record để thảo luận padding.
- [ ] So `byte[]` nhiều lengths và `int[]`/`long[]`/`Object[]` cùng length.
- [ ] Phân biệt reference array với các object được trỏ tới.
- [ ] So `RefBox` chứa array nhỏ/lớn và đo từng referent array riêng.
- [ ] So `Pair(shared)`/`Pair(distinct)` để thấy sự khác biệt identity và object graph.
- [ ] Không lấy `String.length()` làm số bytes được cấp phát.
- [ ] Kiểm tra `getObjectSize(null)` ném `NullPointerException`.
- [ ] Không dùng `Runtime.totalMemory()-freeMemory()` thay cho size một object.
- [ ] Nếu chạy HotSpot flags khác, báo đây là **thí nghiệm cross-configuration riêng**.
- [ ] Trình bày actual measurements cùng JVM version và flags, không điền số giả.
- [ ] Nhận diện nếu estimate thay đổi giữa calls: Javadoc cho phép; không ép phép đo là bất biến.
- [ ] Với deep/retained memory, dùng identity-aware graph analysis hoặc heap tools.
- [ ] Không mở quyền reflection vào JDK internals chỉ để đo bài này.
- [ ] Kiểm tra công cụ dùng đúng mục tiêu: JOL layout, JFR allocations, MAT retained, JMH performance.

## 16. Câu hỏi tự kiểm tra

1. **`getObjectSize` là một số byte chính xác portable theo Java SE không?**  
   Không. Javadoc gọi đây là approximation phụ thuộc implementation; có thể thay đổi ngay trong một lần JVM.

2. **Tại sao cần `premain`?**  
   Để JVM đưa `Instrumentation` cho Java agent tại startup; ứng dụng thường không tự tạo instance này.

3. **`sizeOf(null)` nên trả 0 hay ném lỗi?**  
   Ném `NullPointerException` theo `Instrumentation.getObjectSize`.

4. **`getObjectSize(new byte[4096])` có đo các phần tử byte không?**  
   Primitive array object chứa inline element storage; estimate phản ánh bản thân array, nhưng exact bytes phụ thuộc VM.

5. **`getObjectSize(new Object[100])` có cộng kích thước của 100 objects được tham chiếu không?**  
   Không tự động. Nó đo array object/slots, không đệ quy qua referents.

6. **Thay một field `RefBox.value` từ `byte[1]` thành `byte[4096]` có nhất thiết tăng shallow size của box không?**  
   Không. Box vẫn lưu một reference field; array là object riêng.

7. **Hai references cùng trỏ một object, tính deep size bằng cách cộng mỗi reference được không?**  
   Không; sẽ đếm object đó hai lần. Cần de-dup theo identity.

8. **Record có được JVM chuẩn bảo đảm chiếm ít memory hơn class thông thường không?**  
   Không. Layout vẫn phụ thuộc JVM implementation.

9. **`String.length()*2` có là size của String object không?**  
   Không. Compact strings, backing arrays, header và sharing làm công thức đó sai.

10. **Tại sao `byte[7]` và `byte[8]` có thể cùng size estimate?**  
    Vì alignment/padding trong một VM layout nhất định, không phải mọi payload byte tạo ra mức tăng footprint ngay.

11. **Tắt compressed oops và thấy size khác. Có nên dùng số đó so trực tiếp với baseline như “cùng cấu hình”?**  
    Không. Đó là hai configurations khác nhau; phải nêu điều kiện thử.

12. **Một object trên HotSpot hôm nay là 16 bytes. Có thể assert `==16` cho mọi JVM Java17 không?**  
    Không. Java SE không đặt kích thước tuyệt đối như thế.

13. **Retained size có bằng tổng reachable object sizes không?**  
    Không nhất thiết. Retained size phụ thuộc dominator/GC roots và shared references.

14. **Heap used delta trước-sau tạo object có bằng `getObjectSize` không?**  
    Không đảm bảo do GC, JIT, TLAB và allocations khác.

15. **Nếu mục tiêu là “method A allocate bao nhiêu byte mỗi giây”, dùng getObjectSize đủ chưa?**  
    Chưa. Dùng JFR/allocation profiling hoặc JMH allocation metrics.

16. **Nếu cần field offsets/header breakdown, dùng gì?**  
    Dùng JOL hoặc công cụ phân tích layout phù hợp, đồng thời kiểm tra JVM version/flags.

17. **Tại sao trong lab phải đưa size-agent.jar vào cả `-javaagent` lẫn `-cp`?**  
    `-javaagent` kích hoạt JVM gọi `premain`; `-cp` để application link tới public class `demo.SizeAgent` theo layout artifact đã chọn.

18. **Có thể đo sizes giữa hai JVM processes có cùng flags mà vẫn thấy khác không?**  
    Có thể. Javadoc không bảo đảm giá trị tuyệt đối bất biến; môi trường/implementation/ergonomics có thể khác.

19. **Nếu value của `Object[]` chuyển từ null sang reference tới mảng lớn, có thể suy total heap từ size của Object[] không?**  
    Không. Referent vẫn là object riêng; phải xét graph/reachability.

20. **Bằng chứng nào là đạt bài?**  
    Agent active, các phép đo có giá trị thật trong một JVM, phân tích được ảnh hưởng của fields/arrays/references, không nhầm shallow với deep/retained, và báo cấu hình mà không hardcode số byte.

## 17. Tài liệu chính thức

1. Oracle JDK 17 — **`Instrumentation.getObjectSize(Object)`**, hợp đồng approximation, `null` NPE, còn có `getAllLoadedClasses`/transformers: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html
2. Oracle JDK 17 — **`java.lang.instrument` package**, `-javaagent`, `Premain-Class` và `premain`: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html
3. Oracle JDK 17 — **`java` launcher**, `-XX:-UseCompressedOops` và `-XX:ObjectAlignmentInBytes` trên HotSpot: https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html
4. Oracle JDK 17 — **Java HotSpot performance enhancements**, compressed ordinary object pointers: https://docs.oracle.com/en/java/javase/17/vm/java-hotspot-virtual-machine-performance-enhancements.html
5. OpenJDK **JOL (Java Object Layout)**, implementation-dependent object headers/field layout/array base: https://github.com/openjdk/jol
6. Oracle JDK 17 — **`Class` và Java reflection** (giới hạn khi phân tích object fields): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html
7. Oracle JDK 17 — **`Runtime`**, `totalMemory`/`freeMemory` không thay trực tiếp object size: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Runtime.html
8. Oracle — **Java Flight Recorder**, allocation/runtime profiling: https://docs.oracle.com/en/java/javase/17/jfapi/
9. OpenJDK **JMH**, microbenchmark và `gc.alloc.rate.norm`: https://github.com/openjdk/jmh
10. Eclipse MAT — **Memory Analyzer**, retained heap và dominator analysis: https://eclipse.dev/mat/

**Kết luận:** Trong Java instrumentation, `Instrumentation.getObjectSize` giúp so sánh **ước lượng footprint của từng object** khi giữ **JVM implementation/configuration** nhất quán. Mảng primitive chứa element payload inline, mảng tham chiếu và các reference fields chỉ lưu slots chứ không tự cộng object graph. Đừng dùng kết quả này như deep/retained size hay số bytes cấp phát của một request. Khi cần trả lời câu hỏi sâu hơn, chọn JOL/JFR/MAT/JMH theo đúng loại metric, và báo các numbers như kết quả đo **của chính JVM đã chạy**, không như hằng số Java SE.
