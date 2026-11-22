# Đọc bản ghi JFR: `RecordedThread`, `RecordedClass` và stack trace (Java 11+)

## 1. Tại sao cần xem thread, class và stack trace trong một event JFR?

Khi đọc một file `.jfr`, bản ghi sự kiện (*event*) không chỉ cho biết **điều gì đã xảy ra** và **khi nào**. Nó có thể chứa đủ metadata để trả lời:

- **Thread nào** đã phát ra sự kiện? Tên Java của nó là gì? ID nào dùng để liên hệ các events trong cùng JVM?
- **Class nào** được nhắc đến trong sự kiện? Class ấy do class loader nào định nghĩa?
- **Code đang thực thi ở đâu** khi event được ghi? Method, source line, bytecode index và các frames liên quan là gì?
- **Stack trace có thật sự được ghi không**, hay bị tắt/chỉ được giữ một phần?
- Có thể **nhóm các sự kiện theo thread, class và call site** để điều tra contention, allocations hoặc latency không?

Trong Java 11, package `jdk.jfr.consumer` cung cấp:

```java
jdk.jfr.consumer.RecordedEvent
jdk.jfr.consumer.RecordedThread
jdk.jfr.consumer.RecordedThreadGroup
jdk.jfr.consumer.RecordedClass
jdk.jfr.consumer.RecordedClassLoader
jdk.jfr.consumer.RecordedStackTrace
jdk.jfr.consumer.RecordedFrame
jdk.jfr.consumer.RecordedMethod
jdk.jfr.consumer.RecordingFile
```

Những đối tượng này là **biểu diễn dữ liệu đã ghi trong JFR**, **không phải** đối tượng `Thread`, `Class<?>` hay `StackTraceElement` đang sống của JVM hiện tại. Có thể đọc một file JFR sau khi tiến trình đã kết thúc hoặc trên một máy khác; không cần tải class gốc để xem tên được ghi.

**Điểm cần ghi nhớ từ đầu:** `RecordedEvent.getThread()` và `RecordedEvent.getStackTrace()` **có thể trả `null`**. `RecordedClass` thường có được qua **một event field kiểu `Class`** hoặc qua `RecordedMethod.getType()`, chứ không phải mọi event đều có trực tiếp một class field.

Bài sử dụng những API đã tồn tại ở **Java 11** và còn hợp lệ trên các JDK hiện hành, theo giới hạn chỉ trình bày kiến thức còn áp dụng. Có ghi chú rõ những bổ sung của JDK mới hơn như `RecordedThread.isVirtual()` (từ Java 21), nhưng không dùng chúng trong code biên dịch `--release 11`.

## 2. Mô hình dữ liệu: từ `RecordingFile` đến stack frame

```text
file.jfr
   |
   v
RecordingFile
   |
   +-- readEvent()
          |
          v
      RecordedEvent
          |
          +-- getEventType().getName()
          +-- getStartTime() / getDuration()
          |
          +-- getThread() ----------------> RecordedThread
          |                                  ├ getId()
          |                                  ├ getJavaThreadId()
          |                                  ├ getJavaName()
          |                                  ├ getOSThreadId()
          |                                  └ getThreadGroup()
          |
          +-- getClass("observedType") ---> RecordedClass
          |                                  ├ getName()
          |                                  ├ getId()
          |                                  └ getClassLoader()
          |
          +-- getStackTrace() ------------> RecordedStackTrace
                                             ├ isTruncated()
                                             └ getFrames()
                                                 |
                                                 v
                                             RecordedFrame
                                                 ├ isJavaFrame()
                                                 ├ getType()
                                                 ├ getLineNumber()
                                                 ├ getBytecodeIndex()
                                                 └ getMethod()
                                                       |
                                                       v
                                                  RecordedMethod
                                                       ├ getName()
                                                       ├ getDescriptor()
                                                       ├ isHidden()
                                                       └ getType()
                                                            |
                                                            v
                                                       RecordedClass
```

Sơ đồ này chỉ minh họa những thuộc tính có thể dùng, không khẳng định **mọi event** đều có cả ba nhánh. Một event có thể thiếu thread, thiếu stack trace, thiếu class field, hoặc chỉ có một số metadata.

### Ba lớp không nên nhầm lẫn

| Đối tượng JFR | Đại diện cho | Không phải |
| --- | --- | --- |
| `RecordedThread` | Thông tin **một thread được ghi** trong file JFR | `java.lang.Thread` đang chạy |
| `RecordedClass` | Metadata **một class/interface/type được ghi** | `java.lang.Class<?>` có thể gọi reflection trực tiếp |
| `RecordedStackTrace` | Stack frames **được chụp cho một event** | Exception stack trace/live stack của mọi thread |
| `RecordedFrame` | Một frame trong captured stack | `StackTraceElement` của Java exception |
| `RecordedMethod` | Thông tin method trong recorded frame | `java.lang.reflect.Method` hoặc `MethodHandle` |
| `RecordedEvent` | Một event có timestamp, type và fields | Một log line hoặc một transaction audit đầy đủ |

Một API consumer được thiết kế đúng phải **có null checks, kiểm tra event type, kiểm tra field schema và xử lý dữ liệu bị thiếu**, thay vì nghĩ JFR đã bảo đảm mọi thông tin luôn tồn tại.

## 3. Đọc `RecordedEvent` từ file `.jfr`

### 3.1. `RecordingFile.readAllEvents` cho file nhỏ

```java
import java.nio.file.Path;
import java.util.List;
import jdk.jfr.consumer.RecordedEvent;
import jdk.jfr.consumer.RecordingFile;

Path file = Path.of("recording.jfr");
List<RecordedEvent> events = RecordingFile.readAllEvents(file);

for (RecordedEvent event : events) {
    System.out.println(event.getEventType().getName());
}
```

Đây là **đoạn mã bên trong một phương thức** có khai báo/handle `throws IOException`. `readAllEvents` đưa toàn bộ các events vào một `List` nên phù hợp cho **file nhỏ hoặc bài tập**. Không dùng nó không kiểm soát với file JFR lớn có thể gây áp lực heap.

### 3.2. Đọc tuần tự để tiết kiệm bộ nhớ

```java
try (RecordingFile input = new RecordingFile(file)) {
    while (input.hasMoreEvents()) {
        RecordedEvent event = input.readEvent();
        inspect(event); // Hàm do ứng dụng định nghĩa.
    }
}
```

Đây là **snippet**, `inspect` không phải method JDK. `RecordingFile` implement `AutoCloseable`, nên `try-with-resources` giúp đóng reader. Với phân tích hàng triệu events, vẫn cần quản lý kích thước kết quả tổng hợp và I/O, nhưng tránh materialize toàn bộ event objects đồng thời.

### 3.3. Lọc event type trước khi đọc field

```java
if ("demo.MetadataTrace".equals(
        event.getEventType().getName())) {
    // Chỉ bây giờ đọc các field đặc thù của demo.MetadataTrace.
}
```

Một số event types có field tên `"observedType"`, số khác không. Nếu gọi `event.getClass("observedType")` khi không có field này, API `RecordedObject` có thể ném `IllegalArgumentException`.

**Khuyến nghị cho công cụ phân tích:** dựa vào `getEventType().getName()`, `hasField(name)` và `getFields()` để bảo vệ khi event schema khác nhau giữa JDK versions, ứng dụng hoặc nhà cung cấp.

## 4. `RecordedThread`: thread nào phát ra event?

### 4.1. Lấy thread từ `RecordedEvent`

```java
RecordedThread thread = event.getThread();
if (thread != null) {
    System.out.println(thread.getJavaName());
}
```

Theo Javadoc, `RecordedEvent.getThread()` trả thread **nơi event được commit**, hoặc **`null` nếu thông tin thread không được ghi**. Đừng coi đây luôn là “thread bắt đầu operation”: một event có thể `begin()` ở một thread và `commit()` ở thread khác nếu code/giao thức cho phép, hoặc một JVM event có cấu trúc fields khác.

Một số event có **field kiểu `Thread` riêng**, chẳng hạn một thread liên quan hay đối tượng thread được quan sát. Dùng:

```java
if (event.hasField("observedThread")) {
    RecordedThread related = event.getThread("observedThread");
}
```

`getThread("observedThread")` là phương thức **kế thừa từ `RecordedObject`**, đọc **một field kiểu `Thread` có tên chỉ định**. Nó **không đồng nghĩa** `RecordedEvent.getThread()` (phương thức **không tham số** trả thread commit event).

### 4.2. Các phương thức của `RecordedThread` trong Java 11

| Phương thức | Trả về | Ý nghĩa và khả năng thiếu |
| --- | --- | --- |
| `getId()` | `long` | ID của recorded thread, duy nhất đối với các native/Java threads trong vòng đời JVM nguồn; dùng để liên hệ JFR records |
| `getJavaThreadId()` | `long` | ID ứng với Java thread identity; trả **`-1`** khi không phải Java thread |
| `getJavaName()` | `String` | Tên Java của thread; **`null`** nếu không có Java representation |
| `getOSThreadId()` | `long` | ID thread do OS cung cấp; có thể không khả dụng (`-1`) |
| `getOSName()` | `String` | Tên thread theo OS; **`null`** nếu không tồn tại |
| `getThreadGroup()` | `RecordedThreadGroup` | Thread group trong JFR, có thể **`null`** |

**Ba ID không được dùng thay nhau:**

- `getId()` là **JFR recorded-thread ID**, có ngữ nghĩa duy nhất trong vòng đời JVM được ghi.
- `getJavaThreadId()` đại diện **Java thread ID** tương ứng với `Thread.getId()` trong Java 11.
- `getOSThreadId()` thuộc **OS/native thread identifier**, không phải Java thread ID.

Đừng lấy `getId()` rồi so sánh trực tiếp với `Thread.currentThread().getId()`. Kết quả đôi khi tình cờ có thể bằng nhau trên một môi trường, nhưng **không có hợp đồng** hai loại ID này luôn trùng.

Không dùng ID thread của một file JFR ở JVM A như thể nó nhận diện duy nhất một thread trong JVM B; khi xuất dữ liệu tập trung, cần khóa nhóm gồm application instance/JVM identity và ID tương ứng.

### 4.3. Tên thread không phải định danh duy nhất

Hai Java threads có thể cùng tên `"pool-1-thread-1"` ở những thời điểm khác nhau, hoặc ứng dụng đổi tên thread. `getJavaName()` giúp hiển thị và tìm kiếm, **không đủ làm primary key**.

Ví dụ khi thống kê:

```text
Sai:    groupBy(event.getThread().getJavaName())
Đúng hơn:
        groupBy(jvmInstance, recordedThread.getId())
        rồi dùng tên chỉ làm display label
```

Với file JFR của một JVM duy nhất, `RecordedThread.getId()` hữu ích hơn tên cho việc đối chiếu events. Nếu cần so với thread dump/OS telemetry, dùng đúng loại ID cùng thời điểm và chú ý khả năng ID được tái sử dụng ở OS sau khi thread kết thúc.

### 4.4. `RecordedThreadGroup`

```java
RecordedThreadGroup group = thread.getThreadGroup();
if (group != null) {
    System.out.println(group.getName());
    RecordedThreadGroup parent = group.getParent();
}
```

Đây là **snippet**. Thread group metadata có thể bị thiếu. `getParent()` có thể `null` ở root group. Thread group không phải một cơ chế phân quyền/sandbox đáng tin cậy; dùng làm metadata chẩn đoán nếu hữu ích.

### 4.5. Virtual threads trên JDK mới

Trong **Java 21 trở lên**, `RecordedThread` có thêm `isVirtual()`, dùng để phân biệt virtual thread với platform thread khi runtime và recorded metadata hỗ trợ. **Method này không có trong Java 11** nên không gọi nó trong code biên dịch bằng `javac --release 11`.

Nếu đang xây analyzer phải chạy cả Java 11 và Java 21+, thiết kế theo tập API baseline Java 11; tính năng phân loại virtual threads có thể được bổ sung theo nhánh runtime/JDK version hoặc bằng một build riêng phù hợp.

## 5. `RecordedClass`: hiểu class nào được ghi, không load lại class đó

### 5.1. Từ event field kiểu `Class<?>`

Ví dụ custom JFR event định nghĩa:

```java
@Name("demo.MetadataTrace")
public static class MetadataTrace extends Event {
    public Class<?> observedType;
}
```

Khi producer gán:

```java
MetadataTrace e = new MetadataTrace();
e.observedType = java.lang.String.class;
e.commit();
```

thì consumer của file `.jfr` có thể đọc:

```java
RecordedClass recorded =
        event.getClass("observedType");
if (recorded != null) {
    System.out.println(recorded.getName()); // java.lang.String
}
```

`event.getClass(String)` là API chuyên biệt của `RecordedObject`, **khác `event.getClass()` không tham số** vốn trả **Java class của đối tượng wrapper consumer**. Cần phân biệt rõ overload khi gọi hoặc tìm trong IDE.

### 5.2. Các phương thức `RecordedClass`

| API | Nội dung trả về |
| --- | --- |
| `getName()` | Tên class/type đã ghi, ví dụ `"java.lang.String"` |
| `getId()` | JFR ID cho class ở JVM nguồn; không cam kết giống nhau giữa JVM instances |
| `getModifiers()` | Modifier bitmask của type, có thể diễn giải bằng `java.lang.reflect.Modifier` khi phù hợp |
| `getClassLoader()` | `RecordedClassLoader` định nghĩa class; có thể `null` khi bootstrap loader được JVM biểu diễn bằng null |

`RecordedClass` là **metadata**. Nó **không chứa trực tiếp class bytecode** và không có API gọi constructor hoặc static method của type đó. `Class.forName(recorded.getName())` là một thao tác hoàn toàn khác: nó tìm/tải class trong **JVM đang phân tích**, có thể không tồn tại, có thể là phiên bản khác hoặc đến từ class loader khác. Không làm vậy chỉ để đọc metadata JFR.

### 5.3. `RecordedClassLoader`

```java
RecordedClass type = event.getClass("observedType");
if (type != null) {
    RecordedClassLoader loader = type.getClassLoader();
    String loaderName = loader == null
            ? "<bootstrap/unavailable>" : loader.getName();
    System.out.println(type.getName() + " / " + loaderName);
}
```

`RecordedClassLoader` cung cấp:

- `getId()`: recorded class-loader ID, chỉ có ý nghĩa trong phạm vi JVM nguồn;
- `getName()`: tên loader, có thể `null`;
- `getType()`: class/type của chính class loader, có thể `null`, đặc biệt với bootstrap loader.

**Cẩn thận:** `loader.getType()` là `RecordedClass` mô tả **class của class-loader object**, **không phải** type đang được loader ấy load. Type gốc vẫn là đối tượng `RecordedClass` mà bạn đã có.

Hai classes có cùng `getName()` nhưng do class loaders khác nhau định nghĩa có thể là **hai runtime types khác nhau**. Khi phân tích sự cố class-loader leaks hoặc collisions, đừng nhóm theo class name một cách mù quáng; xem thêm loader ID/name và JVM identity.

### 5.4. `RecordedClass` từ một stack frame

Không phải event nào cũng có field `Class<?>`. Nhưng nếu có stack frame Java, bạn có thể tìm class khai báo method tại frame:

```java
RecordedStackTrace trace = event.getStackTrace();
if (trace != null) {
    for (RecordedFrame frame : trace.getFrames()) {
        if (frame.isJavaFrame()) {
            RecordedMethod method = frame.getMethod();
            if (method != null && method.getType() != null) {
                RecordedClass type = method.getType();
                System.out.println(type.getName());
            }
        }
    }
}
```

**Đây là class của method trong stack frame**, không nhất thiết là class **được event mô tả** hoặc type của object đang bị allocation. Ví dụ một allocation event có thể có một field class về object được cấp phát, nhưng stack frame đầu lại nằm trong phương thức tạo đối tượng thuộc class khác.

## 6. `RecordedStackTrace`: đọc danh sách frames

### 6.1. Lấy stack trace an toàn

```java
RecordedStackTrace trace = event.getStackTrace();

if (trace == null) {
    System.out.println("No stack trace recorded");
} else {
    System.out.println("frames=" + trace.getFrames().size());
    System.out.println("truncated=" + trace.isTruncated());
}
```

Theo Javadoc:

- `getStackTrace()` trả `null` nếu event **không có stack trace**.
- `RecordedStackTrace.getFrames()` trả `List<RecordedFrame>`, **không `null`**.
- `isTruncated()` trả `true` khi stack trace **bị cắt ngắn do kích thước**, `false` nếu không.

Một trace không-null có thể có số frames nhỏ hoặc thậm chí không có frame hữu ích cho chẩn đoán. Đừng viết `trace.getFrames().get(0)` mà không kiểm tra `isEmpty()`.

### 6.2. Stack được chụp tại thời điểm nào?

Đối với custom `jdk.jfr.Event`, setting `stackTrace` áp dụng cho stack **lúc `Event.commit()` được thực hiện**. Vì vậy nó không nhất thiết là stack tại `begin()` hoặc tại thời điểm đầu của một operation dài.

Ví dụ:

```java
event.begin();
doWork();
event.end();
event.commit();
```

Trace mô tả **đường thực thi đến `commit()`**, không phải một lịch sử các method đã gọi trong `doWork()`. Với những JVM-generated events, vị trí capture phụ thuộc event semantics/implementation. Không suy ra toàn bộ business call path chỉ từ một snapshot tại event commit.

### 6.3. `isTruncated()` giải quyết điều gì?

Một stack có thể sâu hơn giới hạn ghi được cấu hình trong JFR. Khi JVM phải cắt ngắn vì giới hạn kích thước, `isTruncated()` cho bạn biết có thể còn các frames không được ghi.

```java
if (trace != null && trace.isTruncated()) {
    System.out.println("Stack trace may omit deeper frames");
}
```

**Không kết luận** `isTruncated()==false` đồng nghĩa “đã có toàn bộ stack của request từ tầng load balancer tới database”: trace chỉ gồm stack của thread tại **thời điểm capture**, với giới hạn của các events/sampling cơ chế liên quan. Nếu asynchronous work chuyển sang thread khác, call path logic có thể không nằm trên cùng Java stack.

### 6.4. Stack trace JFR không phải `Throwable.getStackTrace()`

| `RecordedStackTrace` | `Throwable.getStackTrace()` |
| --- | --- |
| Metadata được ghi trong `.jfr` | Stack của một `Throwable` |
| Có `isTruncated()` | Không có marker tương ứng theo API |
| `RecordedFrame` có Java/non-Java marker, BCI, frame type | `StackTraceElement` có thông tin class/method/file/line |
| Có thể đọc offline sau JVM chết | Thường tồn tại trong object Throwable của JVM hoặc serialized form |
| Có thể mang class-loader metadata qua `RecordedMethod/RecordedClass` | Không cung cấp cùng mô hình recorded-type của JFR |
| `null` khi event không ghi stack trace | `Throwable` có thể cấu hình không ghi/ghi stack riêng |

Không ép/cast một `RecordedStackTrace` thành `Throwable` hay giả định mọi method trả về cùng field.

## 7. `RecordedFrame`: method, line, BCI và kiểu frame

### 7.1. Các method quan trọng

| API | Ý nghĩa | Giá trị đặc biệt |
| --- | --- | --- |
| `isJavaFrame()` | Frame có thuộc một Java method hay không; Java native method vẫn được coi là Java frame | `false` với non-Java frame |
| `getMethod()` | `RecordedMethod` ở vị trí capture | Javadoc nói method object không null |
| `getLineNumber()` | Source line nếu có | **-1** nếu không tồn tại |
| `getBytecodeIndex()` | Offset instruction theo bytecode nếu có | **-1** nếu không tồn tại |
| `getType()` | Mô tả cách thực thi frame, ví dụ `"Interpreted"`, `"JIT compiled"`, `"Inlined"` | Có thể **null** |

**Không biến `getType()` thành một enum cố định do chính mình nghĩ ra:** danh sách các chuỗi frame type có thể phụ thuộc JVM/provider và cách biểu diễn JFR data. Hiển thị giá trị nếu có, xử lý `null`.

### 7.2. Đọc method/type đúng ngữ cảnh

```java
for (RecordedFrame frame : trace.getFrames()) {
    if (!frame.isJavaFrame()) {
        continue;
    }

    RecordedMethod method = frame.getMethod();
    RecordedClass owner = method.getType();

    String className = owner == null
            ? "<unknown>" : owner.getName();

    String location = frame.getLineNumber() >= 0
            ? ":" + frame.getLineNumber()
            : " (line unavailable)";

    System.out.println(
            className + "." + method.getName() + location);
}
```

Đây là **snippet** bên trong một phương thức với `trace` non-null. Kiểm tra `isJavaFrame()` trước khi diễn giải `RecordedMethod.getName/getDescriptor/getType` là quan trọng: Javadoc nói ý nghĩa các method này có thể **không xác định** với frame không thuộc Java method.

### 7.3. Source line và bytecode index có gì khác?

- `getLineNumber()` là **dòng mã nguồn** nếu class có metadata line numbers thích hợp.
- `getBytecodeIndex()` là **vị trí bytecode instruction** được ghi cho frame, không phải số dòng Java.
- Compiler optimizations, inlining, native/JIT execution hoặc class files thiếu debug info có thể khiến line/BCI không tồn tại (`-1`), hoặc một dòng source tương ứng nhiều vị trí bytecode.
- Không lấy BCI làm offset trong file `.jfr`; nó là metadata của vị trí thực thi trong method bytecode.

Nếu cần map BCI về source, cần class artifact/debug info **đúng phiên bản**; một file `.class` mới biên dịch từ source tương tự có thể có BCI/line mappings khác.

### 7.4. `RecordedMethod`

```java
RecordedMethod method = frame.getMethod();

String name = method.getName();
String descriptor = method.getDescriptor();
boolean hidden = method.isHidden();
RecordedClass declaringType = method.getType();
```

Đây là **đoạn minh họa với `frame.isJavaFrame()==true`** và imports phù hợp.

| Method | Mục đích |
| --- | --- |
| `getName()` | Tên method, ví dụ `"service"` hoặc `"run"` |
| `getDescriptor()` | JVM method descriptor, ví dụ `"(Ljava/lang/String;)V"` |
| `getModifiers()` | Modifier bitmask |
| `isHidden()` | Method thuộc dạng hidden theo JVM/JFR semantics, ví dụ wrapper cho lambda |
| `getType()` | `RecordedClass` khai báo method; có thể **null** nếu không phải Java frame |

**Method descriptor** không phải human-readable Java method declaration. Ví dụ `(Ljava/lang/String;)V` nghĩa là method nhận một `String` và trả `void`; `I` là `int`, `J` là `long`, `[I` là `int[]`, `Lpkg/Type;` là reference type.

Khi nhóm hot methods để dựng flame graph/call tree, chỉ dựa vào tên `getName()` là chưa đủ: các overloads có cùng tên nhưng descriptor khác. Nên dùng **class name + loader/context + method name + descriptor**, cộng frame type nếu có lý do chẩn đoán.

## 8. Java 11 demo đầy đủ: tạo file JFR rồi đọc Thread, Class và stack trace

Chương trình này hoạt động **offline**, không cần một dịch vụ hoặc file `.jfr` chuẩn bị sẵn. Nó:

1. Kiểm tra JVM có JFR hay không.
2. Tạo một custom JFR event `demo.MetadataTrace` có hai fields kiểu `Class<?>` và `Thread`.
3. Bật event với `withoutThreshold()` và `withStackTrace()`.
4. Ghi event trong thread Java có tên `"jfr-demo-worker"`, qua method `callSite()` rồi `emitEvent()`.
5. Stop recording và dump ra file `.jfr` tạm.
6. Đọc file bằng `RecordingFile.readAllEvents`, lọc đúng event type.
7. Truy cập `RecordedEvent.getThread()`, `getThread("observedThread")`, `getClass("observedType")` và `getStackTrace()`.
8. Kiểm tra class-loader metadata, method `emitEvent` trong captured Java frames và line number.
9. Dọn file tạm sau khi kiểm tra.

**Lưu file:** `JfrRecordedMetadataDemo.java`.

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

import jdk.jfr.Event;
import jdk.jfr.FlightRecorder;
import jdk.jfr.Label;
import jdk.jfr.Name;
import jdk.jfr.Recording;

import jdk.jfr.consumer.RecordedClass;
import jdk.jfr.consumer.RecordedClassLoader;
import jdk.jfr.consumer.RecordedEvent;
import jdk.jfr.consumer.RecordedFrame;
import jdk.jfr.consumer.RecordedMethod;
import jdk.jfr.consumer.RecordedStackTrace;
import jdk.jfr.consumer.RecordedThread;
import jdk.jfr.consumer.RecordingFile;

public final class JfrRecordedMetadataDemo {

    @Name("demo.MetadataTrace")
    @Label("Metadata Trace")
    public static class MetadataTrace extends Event {
        public Class<?> observedType;
        public Thread observedThread;
        public String outcome;
    }

    private static void emitEvent() {
        MetadataTrace event = new MetadataTrace();

        event.observedType = JfrRecordedMetadataDemo.class;
        event.observedThread = Thread.currentThread();
        event.outcome = "OK";

        event.begin();
        event.end();

        if (event.shouldCommit()) {
            event.commit();
        }
    }

    private static void callSite() {
        emitEvent();
    }

    public static void main(String[] args) throws Exception {
        if (!FlightRecorder.isAvailable()) {
            System.out.println("jfrAvailable=false");
            return;
        }

        Path file =
                Files.createTempFile("jfr-recorded-metadata-", ".jfr");

        try {
            try (Recording recording = new Recording()) {
                recording.setToDisk(true);
                recording.enable(MetadataTrace.class)
                        .withoutThreshold()
                        .withStackTrace();

                recording.start();

                Thread worker = new Thread(
                        JfrRecordedMetadataDemo::callSite,
                        "jfr-demo-worker");
                worker.start();
                worker.join();

                recording.stop();
                recording.dump(file);
            }

            List<RecordedEvent> all =
                    RecordingFile.readAllEvents(file);

            long matched = all.stream()
                    .filter(event -> "demo.MetadataTrace".equals(
                            event.getEventType().getName()))
                    .count();

            RecordedEvent event = all.stream()
                    .filter(e -> "demo.MetadataTrace".equals(
                            e.getEventType().getName()))
                    .findFirst()
                    .orElseThrow(() -> new IllegalStateException(
                            "Expected event missing"));

            RecordedThread origin = event.getThread();
            RecordedThread custom =
                    event.getThread("observedThread");

            RecordedClass type =
                    event.getClass("observedType");

            RecordedClassLoader loader =
                    type.getClassLoader();

            RecordedStackTrace trace =
                    event.getStackTrace();

            boolean containsEmit = false;
            boolean hasLine = false;
            boolean hasJavaFrame = false;

            if (trace != null) {
                for (RecordedFrame frame : trace.getFrames()) {
                    if (frame.isJavaFrame()) {
                        hasJavaFrame = true;
                    }

                    RecordedMethod method = frame.getMethod();

                    if (method != null
                            && frame.isJavaFrame()
                            && "emitEvent".equals(method.getName())
                            && method.getType() != null
                            && JfrRecordedMetadataDemo.class.getName()
                                    .equals(method.getType().getName())) {

                        containsEmit = true;
                        hasLine = frame.getLineNumber() > 0;
                    }
                }
            }

            System.out.println(
                    "matchingEvents=" + matched);

            System.out.println("eventThread=" +
                    (origin == null
                    ? "<none>" : origin.getJavaName()));

            System.out.println("threadIDsMatch=" +
                    (origin != null && custom != null
                    && origin.getId() == custom.getId()));

            System.out.println(
                    "className=" + type.getName());

            System.out.println(
                    "classLoaderKnown=" + (loader != null));

            System.out.println(
                    "stackPresent=" + (trace != null));

            System.out.println(
                    "containsEmitEvent=" + containsEmit);

            System.out.println(
                    "sourceLineAvailable=" + hasLine);

            System.out.println(
                    "containsJavaFrame=" + hasJavaFrame);

            System.out.println(
                    "stackTruncated=" +
                    (trace != null && trace.isTruncated()));

        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

### Biên dịch và chạy trên Java 11

```bash
javac --release 11 --add-modules jdk.jfr JfrRecordedMetadataDemo.java
java --add-modules jdk.jfr JfrRecordedMetadataDemo
```

**Stdout đã được biên dịch và chạy kiểm chứng:**

```text
matchingEvents=1
eventThread=jfr-demo-worker
threadIDsMatch=true
className=JfrRecordedMetadataDemo
classLoaderKnown=true
stackPresent=true
containsEmitEvent=true
sourceLineAvailable=true
containsJavaFrame=true
stackTruncated=false
```

**Giải thích lần lượt:**

- `matchingEvents=1`: filter đếm đúng một custom event `demo.MetadataTrace`. Nếu JFR ghi các event khác thì cũng không ảnh hưởng count này.
- `eventThread=jfr-demo-worker`: event được commit trên thread có tên xác định trong fixture.
- `threadIDsMatch=true`: thread commit và field `observedThread` trỏ cùng recorded identity trong JVM nguồn. Ở ứng dụng khác, hai fields kiểu Thread không bắt buộc trỏ một thread.
- `className=JfrRecordedMetadataDemo`: field `observedType` chứa `Class<?>` của chính class demo, đọc ra thành `RecordedClass`.
- `classLoaderKnown=true`: ứng dụng mẫu được load bởi class loader có metadata, nên có `RecordedClassLoader`. Đừng suy rộng rằng `String.class` hoặc class của bootstrap loader cũng phải có object này.
- `stackPresent=true`: event settings bật capture stack trace.
- `containsEmitEvent=true`: captured frames chứa method `emitEvent` trong class mẫu.
- `sourceLineAvailable=true`: compiler trong thử nghiệm đã đưa line-number metadata vào class file, nên frame có source line hợp lệ.
- `containsJavaFrame=true`: ít nhất một frame thuộc Java method.
- `stackTruncated=false`: trace của lần chạy ngắn này không bị báo cắt ngắn; không đồng nghĩa mọi trace ở mọi ứng dụng đều đầy đủ.

**Kết quả không phải cam kết tuyệt đối cho mọi runtime/JDK:** Khi VM không có JFR, chương trình in `jfrAvailable=false` rồi kết thúc. Trong một cấu hình bị giảm stack depth, tắt debug line numbers, custom provider hoặc môi trường bị giới hạn, boolean liên quan trace/line và số events có thể khác. Mục tiêu là minh họa **cơ chế JFR consumer**, không phải test tính xác định của scheduler/profiler trên mọi máy.

### Tại sao chọn custom event?

Nếu demo dựa vào JVM event như GC hoặc File I/O, workload nhỏ có thể không phát ra đúng event mong muốn. Custom event tạo trong một thread cố định giúp minh họa quan hệ thread/class/stack rõ ràng và có kết quả quan sát được.

### Tại sao không dùng `Throwable.getStackTrace()` trong demo?

Đề bài yêu cầu **đọc dữ liệu JFR thật**. Việc tự gọi `new Throwable().getStackTrace()` sẽ cho một stack ở runtime hiện tại nhưng **không chứng minh** file JFR có `RecordedStackTrace`. Chương trình này đã đi qua `Recording.dump()` và `RecordingFile` để kiểm tra dữ liệu từ artifact `.jfr`.

## 9. Demo 2: tắt stack trace nhưng vẫn còn thread và class

Một lỗi phân tích hay gặp là thấy `getStackTrace()==null` rồi kết luận **“event đã bị hỏng”**. Thực tế stack trace là một **setting độc lập**: event vẫn có thể ghi thread, class fields và thời gian bình thường.

**Lưu file:** `JfrStackSwitchDemo.java`.

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

import jdk.jfr.*;
import jdk.jfr.consumer.*;

public final class JfrStackSwitchDemo {

    @Name("demo.WithoutTrace")
    public static class WithoutTrace extends Event {
        public Class<?> target;
    }

    public static void main(String[] args) throws Exception {
        Path target =
                Files.createTempFile("jfr-without-trace-", ".jfr");

        try {
            try (Recording recording = new Recording()) {
                recording.enable(WithoutTrace.class)
                        .withoutThreshold()
                        .withoutStackTrace();

                recording.start();

                WithoutTrace event = new WithoutTrace();
                event.target = String.class;
                event.commit();

                recording.stop();
                recording.dump(target);
            }

            List<RecordedEvent> events =
                    RecordingFile.readAllEvents(target);

            RecordedEvent found = events.stream()
                    .filter(e -> "demo.WithoutTrace".equals(
                            e.getEventType().getName()))
                    .findFirst()
                    .orElseThrow(
                            () -> new IllegalStateException("missing"));

            System.out.println(
                    "type=" + found.getClass("target").getName());
            System.out.println(
                    "traceNull=" + (found.getStackTrace() == null));
            System.out.println(
                    "threadPresent=" + (found.getThread() != null));

        } finally {
            Files.deleteIfExists(target);
        }
    }
}
```

Biên dịch và chạy:

```bash
javac --release 11 --add-modules jdk.jfr JfrStackSwitchDemo.java
java --add-modules jdk.jfr JfrStackSwitchDemo
```

**Stdout đã kiểm chứng:**

```text
type=java.lang.String
traceNull=true
threadPresent=true
```

Điều rút ra: `withoutStackTrace()` **không phải tắt việc ghi toàn bộ event**, cũng không tắt mặc định mọi metadata thread/class. `getStackTrace()==null` có thể chỉ là event không được cấu hình capture stack. Nếu event có `@StackTrace(false)`, hoặc settings của recording tắt stack, kết quả tương tự có thể xuất hiện.

**Quan trọng:** Không cố “khôi phục” toàn bộ call stack của một event cũ bằng cách bật `withStackTrace()` sau khi file đã được ghi. Thông tin chưa được capture **không thể dựng lại đầy đủ** chỉ từ thread name/class metadata.

## 10. Phân tích thực tế: thread và class không luôn là một quan hệ một-một

### 10.1. Thread phát event và thread được event nói đến có thể khác

Ví dụ một event của JVM có field `eventThread` (thread gắn với event) và một field riêng `parkedThread` hoặc `targetThread` tùy schema. **Không** giả định luôn có field `parkedThread`: tên field tùy loại event và JDK version.

Một worker có thể phát event nói về một thread khác, hoặc một event tương ứng với một class được allocate/load bởi thread ấy.

Để giữ đúng ý nghĩa:

1. Kiểm tra `event.getEventType().getName()`.
2. Tìm metadata của event fields.
3. Dùng `event.getThread()` cho thread commit (nếu có).
4. Dùng `event.getThread("fieldName")` cho field kiểu `Thread` có tên tương ứng.
5. Đặt tên cột hiển thị rõ `commitThread` và `relatedThread`, không trộn hai loại.

### 10.2. Class của object và class của stack frame có thể khác

Ví dụ một allocation event:

```text
Allocated type: java.util.HashMap
Stack:
  com.example.InventoryService.buildView(...)
  com.example.InventoryController.handle(...)
  ...
```

`java.util.HashMap` là **type của object được cấp phát** nếu event schema cung cấp field đó. `InventoryService` là **class của method** tại stack frame. Cả hai đều là `RecordedClass` trong metadata nhưng trả lời hai câu hỏi khác nhau: **“cái gì được tạo?”** và **“code nào gây ra?”**.

Muốn làm dashboard “top allocated classes”, nhóm theo **class field mô tả allocation**; muốn flame graph “allocation sites”, nhóm theo **stack frames**. Không lấy class của stack frame đầu làm type của object được allocate.

### 10.3. Event time khác stack capture time

`event.getStartTime()` cho biết thời điểm bắt đầu event. Với custom events có `begin/end/commit`, `getStackTrace()` thường chụp tại `commit`. Nếu một event kéo dài 5 giây, stack tại commit không phải toàn bộ trace của công việc đã chạy suốt 5 giây.

Đối với CPU sampling events, stack lại thể hiện điểm sampling; không được đọc nó như một call graph đầy đủ, deterministic cho một request.

## 11. Viết code đọc an toàn với null và field schema

Một parser đơn giản có thể bảo vệ theo event type:

```java
static void inspectMetadata(RecordedEvent event) {
    String eventName = event.getEventType().getName();

    RecordedThread thread = event.getThread();
    String threadName =
            thread == null ? "<unknown>" : thread.getJavaName();

    RecordedStackTrace trace = event.getStackTrace();
    int frameCount =
            trace == null ? 0 : trace.getFrames().size();

    System.out.println(eventName + ": "
            + threadName + ", frames=" + frameCount);

    if (event.hasField("observedType")) {
        // Chỉ gọi getClass khi schema bảo đảm field thuộc type Class.
        RecordedClass type = event.getClass("observedType");
        if (type != null) {
            System.out.println("type=" + type.getName());
        }
    }
}
```

Đây là **method minh họa** với các imports `jdk.jfr.consumer.*`. Để dùng với nhiều event types của một JDK bất kỳ, nên kiểm tra **cả type của field**, vì `hasField("observedType")` chỉ chứng minh tên tồn tại, **không** chứng minh field thuộc `Class`. Nếu field là `String`, `getClass(String)` vẫn có thể ném `IllegalArgumentException`.

### 11.1. Đọc generic field qua `getValue`

`RecordedObject` hỗ trợ:

```java
if (event.hasField("observedType")) {
    Object value = event.getValue("observedType");
    if (value instanceof RecordedClass) {
        RecordedClass c = (RecordedClass) value;
        System.out.println(c.getName());
    }
}
```

Điều này giảm nguy cơ ép sai field type, nhưng **không tự xác định ngữ nghĩa** của field. Cần xem `ValueDescriptor` hoặc tài liệu schema event nếu muốn hiểu ý nghĩa.

### 11.2. Dotted property path

Theo `RecordedObject`, `getValue(String)` có thể truy cập **nested fields** bằng dotted name như `"thread.group.parent.name"` nếu cấu trúc field ấy thực sự tồn tại.

Đừng hard-code dotted path từ một file JFR/JDK rồi giả định mọi event type có cùng layout. Với công cụ tổng quát:

- kiểm tra `event.getFields()`;
- kiểm tra field có tồn tại và có đúng type trước khi đọc;
- xử lý các giá trị null ở từng cấp;
- ghi log lỗi parse có đủ event name/schema version để tìm nguyên nhân;
- không “fallback” bằng cách coi sai field type là bằng 0 hoặc bằng chuỗi trống một cách im lặng.

## 12. Mẫu phân tích top methods và threads

### 12.1. Group theo thread ID

Một nguyên tắc grouping:

```text
key = (jvmInstanceId, recordedThread.getId())
label = recordedThread.getJavaName()
metric = count(events) hoặc sum(event.duration)
```

Nếu file chỉ đến từ một JVM và bạn chắc chắn provenance, có thể dùng recorded thread ID trực tiếp. Khi nhiều files được merge, **giữ JVM identity** hoặc một cách xác thực tương đương; không trộn các thread có cùng số ID từ những tiến trình khác nhau.

**Đừng dùng event count để kết luận thread sử dụng CPU nhiều nhất.** Các loại JFR events khác nhau có sampling rate/threshold khác nhau; cần dùng đúng metric và trọng số theo loại event (CPU samples, allocation events, duration...) mới đưa ra kết luận hiệu năng hợp lý.

### 12.2. Group theo method key

Đối với Java frame:

```text
methodKey = (
  jvmInstanceId,
  recordedClass.getName(),
  recordedClass.getClassLoader()?.getId(),
  recordedMethod.getName(),
  recordedMethod.getDescriptor()
)
```

Đây là **pseudo-code mô hình key**, không phải cú pháp Java 11 chạy độc lập. Nó phân biệt các overloads, lớp cùng tên từ loaders khác nhau và nhiều JVMs.

Một ví dụ sử dụng an toàn:

```java
RecordedStackTrace trace = event.getStackTrace();
if (trace != null) {
    for (RecordedFrame frame : trace.getFrames()) {
        if (!frame.isJavaFrame()) {
            continue;
        }
        RecordedMethod m = frame.getMethod();
        RecordedClass owner = m.getType();
        if (owner != null) {
            String methodKey = owner.getName()
                    + "#" + m.getName()
                    + m.getDescriptor();
            // Tăng counter cho key hoặc ghi ra bảng tổng hợp.
        }
    }
}
```

Đây là **snippet**, phải khai báo imports và xác định key có cần include class-loader ID không trong ứng dụng. Nếu muốn một bảng “top call sites”, nên dùng thêm line number/BCI khi có. Nếu muốn flame graph, giữ thứ tự **toàn bộ stack frames**, đừng chỉ lấy một frame để thay toàn call tree.

### 12.3. Bảo vệ memory khi aggregate

Nếu xử lý hàng chục GB dữ liệu JFR:

- đọc bằng `RecordingFile` iterator thay vì `readAllEvents`;
- giới hạn số lượng nhóm/counters, có eviction hoặc top-k;
- tránh lưu raw `RecordedEvent` trong list kéo dài mãi;
- có thể tách phần parse và phần aggregate, xử lý backpressure;
- gắn metadata về file/time range/JDK version để giải thích kết quả;
- không tạo một map key từ hàng chục field có cardinality không kiểm soát như request URL/UUID.

## 13. Stack traces có thể bị thiếu hoặc ít frames: xác định đúng nguyên nhân

Khi `event.getStackTrace()==null`, những nguyên nhân thực tế gồm:

1. Event type không được cấu hình ghi stack trace (`stackTrace=false`).
2. `Recording.enable(...).withoutStackTrace()` đã tắt capture cho loại event.
3. Event schema/JVM runtime không cung cấp stack trace cho event đó.
4. Metadata đã không được ghi/không còn trong recording file theo đặc điểm của loại event.
5. Event không tồn tại trong file được chọn (lỗi filter/event type), không phải lỗi riêng của stack.

Khi trace có nhưng frames ít:

- `isTruncated()==true`: JVM báo stack bị cắt ngắn do giới hạn kích thước.
- `isTruncated()==false` nhưng frames ngắn: call path thực tế ngắn, sampling/capture tại điểm khác mong đợi, async boundary hoặc JVM-specific frame representation.
- `getLineNumber()==-1`: không có source line metadata cho frame, có thể do class được build thiếu debug lines hoặc frame không map được.
- `getBytecodeIndex()==-1`: không có BCI; không tự đoán ra dòng source.
- `getType()==null`: implementation không cung cấp chuỗi frame type, vẫn có thể có method name.

### Tắt stack khác tắt event

Hai phương thức điều khiển một JFR event khác nhau:

```java
recording.enable(MyEvent.class)
        .withoutStackTrace()
        .withoutThreshold();
```

Điều trên vẫn **bật event**, chỉ không ghi stack trace và không dùng duration threshold. Ngược lại:

```java
recording.disable(MyEvent.class);
```

là yêu cầu tắt event type cho recording ấy. Không dùng `disable` chỉ để giảm overhead stack nếu vẫn cần dữ liệu thread/class fields.

### Stack depth là một giới hạn, không phải toàn bộ lịch sử

Khi JVM chỉ giữ một số lượng frames nhất định, JFR có thể báo `isTruncated`. Đừng tưởng tăng depth sẽ làm một event chứa đầy đủ call chain xuyên các asynchronous handoffs. Mỗi thread chỉ có call stack riêng tại thời điểm snapshot; async causality cần thêm correlation IDs/events và một mô hình tracing phù hợp.

## 14. Tính tương thích giữa Java 11 và JDK mới hơn

Các lớp **`RecordedThread`, `RecordedClass`, `RecordedStackTrace`, `RecordedFrame`, `RecordedMethod` và `RecordingFile`** đã có public API trong Java 11 và tiếp tục hữu ích.

Nhưng khi đọc file từ JVM mới bằng ứng dụng build cho Java 11, hãy nhớ:

- Một JDK mới có thể thêm **event types, fields, annotations và metadata**.
- JFR file parser của runtime cũ **không được bảo đảm** tương thích với mọi format extension của file do runtime tương lai ghi. Kiểm thử analyzer với đúng versions sẽ sử dụng, đặc biệt khi công cụ consumer chạy trên JDK cũ.
- Event names và fields của JVM có thể thay đổi theo phiên bản; không tin mù quáng một event schema mà không kiểm tra.
- `RecordedThread.isVirtual()` là API **thêm từ Java 21**, không có trên baseline Java 11; nếu cần phân tích virtual threads chuyên sâu, dùng runtime tương ứng với API mới, không đặt method ấy trong source bắt buộc `--release 11`.
- `Thread.threadId()` là API mới hơn; ở Java 11 khi muốn Java thread ID trong ứng dụng dùng `Thread.getId()`. Nhưng đừng gọi `Thread.getId()` trên consumer `RecordedThread`; API có `getJavaThreadId()` riêng.

**Không viết code mới phụ thuộc vào API không có trong Java 11 nhưng vẫn ghi tiêu đề “compiles with --release 11”.** Ví dụ chính chỉ sử dụng những methods được khai báo trong Java SE 11 JFR docs.

## 15. An toàn thông tin và giới hạn của JFR metadata

### 15.1. Không đồng nhất JFR với business audit

JFR là cơ chế chẩn đoán/profiling. Nó có thể:

- lấy mẫu hoặc chỉ phát events theo threshold;
- bỏ qua/không giữ event trong điều kiện buffering/retention;
- cắt ngắn stack hoặc không ghi stack;
- lưu một số metadata đủ để điều tra nhưng không phải toàn bộ request context;
- chứa class/method names, file paths và thread names nhạy cảm.

Không dùng chỉ một file JFR để khẳng định nghiệp vụ X đã xử lý thành công 100% hoặc một user đã truy cập đúng tài nguyên. Một audit log có integrity/retention policy riêng mới phù hợp cho mục đích này.

### 15.2. Tên class/method và stack traces cũng là dữ liệu có thể nhạy cảm

Dù JFR không lưu trực tiếp password, metadata có thể tiết lộ:

- tên lớp về thanh toán, xác thực hoặc dữ liệu nội bộ;
- thread names chứa tenant/user IDs nếu app đặt như vậy;
- đường dẫn source/resources qua annotations và metadata;
- call path tới những phần xử lý bảo mật;
- class-loader naming conventions và application architecture.

Không đưa raw file `.jfr` hay hàng nghìn stack frames vào hệ thống/third-party không được phép. Khi làm dashboard, hạn chế data retention, redact hoặc aggregate names khi cần.

### 15.3. Stack-trace capture có overhead

`withStackTrace()` và các event types có tần suất lớn có thể tăng CPU/memory/disk overhead. Khi một event phát hàng triệu lần, việc ghi đầy đủ stack frames cho mọi event sẽ tạo khối lượng đáng kể.

Chọn:

- event types thật sự cần;
- threshold phù hợp với latency;
- sampling period thay vì ghi tất cả nếu event hỗ trợ;
- bật stack trace trong cửa sổ điều tra ngắn;
- retention/maxSize/disk quota và quyền đọc file đúng mức.

Không tối ưu mù bằng cách tắt mọi stack trace rồi đòi phân tích call sites. Phải cân bằng độ chi tiết, chi phí và câu hỏi điều tra.

## 16. Lỗi phổ biến và cách khắc phục

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `event.getThread()` trả `null` | Thread metadata không được ghi cho event | Null check; đọc event schema và event type |
| Tên Java thread là `null` | Recorded native thread không có Java representation | Dùng `getOSName`/`getId` nếu phù hợp |
| `getJavaThreadId()==-1` | Không phải Java thread/không có Java ID | Không ép thành Java `Thread` |
| Lẫn `getId` với Java Thread ID | Hai loại ID khác nhau | Đọc `getJavaThreadId` khi cần so với `Thread.getId` |
| Thống kê gộp sai threads cùng tên | Thread names không duy nhất | Key theo JVM + recorded-thread ID |
| `event.getClass()` in `RecordedEvent.class` | Gọi `Object.getClass()` không tham số | Dùng `getClass("fieldName")` |
| `getClass("field")` báo `IllegalArgumentException` | Field thiếu hoặc không phải `Class` | Filter type, `hasField/getFields` |
| `type.getClassLoader()==null` | Bootstrap loader representation/metadata không khả dụng | Null check, không coi là lỗi mặc định |
| Hai classes cùng name bị gộp | Nhiều class loaders | Thêm loader ID/context |
| Stack trace là `null` | Event không có stack setting/data | Bật `withStackTrace()` trước khi ghi; xử lý null |
| Frames rỗng | Trace có nhưng không có frames để đọc | Kiểm tra `isEmpty` |
| `isTruncated()==true` | Trace bị cắt do size/depth | Đánh dấu thiếu thông tin, điều chỉnh cấu hình nếu cần |
| `getLineNumber()==-1` | Không có source line info | Không gán số dòng giả |
| `getBytecodeIndex()==-1` | BCI không khả dụng | Không xem -1 là bytecode index thật |
| `RecordedMethod.getType()==null` | Frame không thuộc Java method hoặc type thiếu | Kiểm tra `isJavaFrame`/null |
| Gọi `RecordedThread.isVirtual()` bằng `--release 11` | API chỉ có từ Java 21 | Không dùng trong Java 11 source |
| File parser quá tải RAM | Dùng `readAllEvents` cho file lớn | `RecordingFile` iterator |
| Cùng class-name method-key trùng các overloads | Không dùng method descriptor | Include `getDescriptor` |
| Stack trace không chứa logic trước một CompletableFuture | Async boundary chuyển call stack | Gắn correlation ID/event riêng nếu cần |
| Event count bằng 0 nhưng recording có file | Event type không phát/không enabled/threshold | Kiểm tra event settings và filter |
| Mở file JFR không tin cậy | Parser/file nhị phân từ nguồn không rõ | Chỉ đọc file từ nguồn tin cậy hoặc môi trường cách ly |
| Người khác truy cập file JFR | Export/download không có quyền | RBAC, encryption, retention, audit |

## 17. Câu hỏi tự kiểm tra có đáp án

**1.** `RecordedThread` có phải `java.lang.Thread` của JVM đang phân tích không?

**Đáp án:** Không. Nó là metadata đã ghi trong JFR, có thể đọc offline sau khi JVM nguồn đã kết thúc.

**2.** Khác biệt giữa `event.getThread()` và `event.getThread("observedThread")` là gì?

**Đáp án:** Phương thức không tham số lấy thread nơi event được commit (nếu có); phương thức có tên field đọc một giá trị kiểu `Thread` từ event schema.

**3.** `RecordedThread.getId()` có đồng nghĩa `Thread.getId()` trong Java 11 không?

**Đáp án:** Không. Muốn Java thread ID dùng `RecordedThread.getJavaThreadId()`. `RecordedThread.getId()` là JFR recorded-thread ID.

**4.** Khi `getJavaThreadId()` trả `-1`, có nên coi đây là thread ID thật không?

**Đáp án:** Không. `-1` là sentinel cho trường hợp không phải Java thread.

**5.** `getJavaName()` có thể null dù một event có thread metadata không?

**Đáp án:** Có. Native thread không có Java representation có thể không có Java name.

**6.** Vì sao không group events toàn công ty chỉ theo `RecordedThread.getId()`?

**Đáp án:** ID chỉ có phạm vi trong JVM nguồn; nhiều JVMs có thể dùng cùng số ID. Cần thêm JVM/application instance identity.

**7.** `event.getClass("observedType")` trả đối tượng gì?

**Đáp án:** `RecordedClass`, với điều kiện field tồn tại và thuộc type `Class`. Nó không phải `Class<?>` để invoke methods trực tiếp.

**8.** `event.getClass()` không tham số có tương đương `getClass("observedType")` không?

**Đáp án:** Không. `getClass()` không tham số là `Object.getClass()` của wrapper.

**9.** `RecordedClass.getClassLoader()==null` có luôn nghĩa file JFR bị lỗi không?

**Đáp án:** Không. Bootstrap class loader có thể được JVM biểu diễn bằng null.

**10.** Tên class giống nhau có chứng minh hai runtime types giống nhau không?

**Đáp án:** Không nếu do class loaders khác nhau định nghĩa. Khi phân tích cần xét class-loader metadata.

**11.** `RecordedStackTrace.getFrames()` có thể `null` không?

**Đáp án:** Theo Javadoc, không. Nhưng chính `event.getStackTrace()` có thể `null`.

**12.** `isTruncated()==true` nghĩa là gì?

**Đáp án:** Stack trace bị cắt do giới hạn kích thước/depth; thông tin frame phía sâu hơn có thể thiếu.

**13.** `getLineNumber()==-1` nghĩa là dòng `-1` trong source code?

**Đáp án:** Không. Nó có nghĩa source line không khả dụng cho frame.

**14.** `getBytecodeIndex()` là số dòng Java?

**Đáp án:** Không. Đó là vị trí bytecode instruction, khác với source line.

**15.** Vì sao phải kiểm tra `frame.isJavaFrame()` trước khi dùng `method.getType().getName()`?

**Đáp án:** `RecordedMethod` của non-Java frame có thể không có declaring Java type hoặc tên/descriptor không xác định.

**16.** `RecordedMethod.getDescriptor()` cần làm gì khi group methods?

**Đáp án:** Dùng cùng method name và declaring class để phân biệt overloads có cùng tên nhưng tham số khác.

**17.** Event có duration 10 giây thì stack trace có lưu đủ mọi method đã chạy trong 10 giây không?

**Đáp án:** Không. Thường là snapshot tại commit/event capture, không phải lịch sử call path liên tục.

**18.** `withoutStackTrace()` có làm event không còn thread/class metadata không?

**Đáp án:** Không nhất thiết. Demo thứ hai cho thấy thread và class vẫn có trong khi stack trace null.

**19.** Nếu file JFR không chứa stack trace, bật `withStackTrace()` khi đọc có bổ sung được không?

**Đáp án:** Không. Phải bật khi ghi; thông tin không được capture không thể tái tạo từ file chỉ chứa event/thread/class metadata.

**20.** Tại sao không dùng `RecordingFile.readAllEvents()` cho file cực lớn?

**Đáp án:** Nó đọc mọi event vào `List` và có thể làm hết heap. Dùng iterator streaming cho các tác vụ tổng hợp.

**21.** `RecordedThread.isVirtual()` có biên dịch với `--release 11` không?

**Đáp án:** Không. API này xuất hiện từ Java 21.

**22.** `frame.isJavaFrame()` có chắc trả false cho mọi Java method có modifier `native` không?

**Đáp án:** Không. Theo Javadoc, một Java method mang `native` vẫn được coi là Java frame.

**23.** Có thể suy ra class được cấp phát từ class của stack frame đầu không?

**Đáp án:** Không. Class của frame là nơi method chạy; allocated type nếu có nằm trong event field riêng.

**24.** Vì sao các chương trình demo xóa file `.jfr` khi kết thúc?

**Đáp án:** Để tránh tạo artifact tạm. Trong hệ thống thật, nên áp dụng retention và bảo vệ file theo mục đích điều tra, không xóa file khi vẫn cần phân tích.

## 18. Bài tập thực hành mở rộng

### Bài tập A — Nhóm events theo Java thread

Thay vì in `matchingEvents=1`, phát một số events từ hai workers có tên khác nhau. Đọc lại file, group theo `RecordedThread.getId()` trong một JVM và hiển thị `getJavaName()`. Nếu có hai threads cùng tên, kiểm tra cách group theo tên tạo kết quả sai.

### Bài tập B — Thêm field `Class<?>` khác

Trong `MetadataTrace` thêm một field `public Class<?> handlerType;`, gán `String.class`. Sau khi ghi, dùng `event.getClass("handlerType").getName()` và so sánh với class xuất hiện trong captured frames. Hai loại class metadata có nhiệm vụ khác nhau.

### Bài tập C — Ghi stack trace có/không

Dùng `withStackTrace()` và `withoutStackTrace()` trong hai recordings độc lập. So sánh `event.getStackTrace()`, `getThread()` và `getClass("observedType")` để thấy các settings độc lập.

### Bài tập D — Line number không khả dụng

Biên dịch một class với tuỳ chọn bỏ line-number debug info trong môi trường thử, ghi JFR event và đọc frame. Quan sát `getLineNumber()==-1` (nếu JVM không có cách tái tạo từ metadata khác). Không viết assertion tuyệt đối cho tất cả frame types.

### Bài tập E — Viết phân tích stack-depth

Đếm `trace.getFrames().size()` và `trace.isTruncated()` trên một chương trình gọi đệ quy có giới hạn. So sánh với JFR stack-depth configuration và lưu ý mức sâu có thể thay đổi theo JIT/inlining/provider.

### Bài tập F — Stream một file JFR lớn

Thay `readAllEvents` bằng `try (RecordingFile input = new RecordingFile(path))`, aggregate số events theo method key, chỉ giữ top-k counters. Thêm test bảo đảm bộ nhớ không tỷ lệ trực tiếp với tổng số events.

## 19. Tài liệu chính thức còn áp dụng

- [Oracle Java SE 11 — `RecordedEvent`](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/consumer/RecordedEvent.html): `getThread()`, `getStackTrace()`, timestamp/event type và điều kiện trả `null`.
- [Oracle Java SE 11 — `RecordedThread`](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/consumer/RecordedThread.html): JFR ID, Java ID, OS ID, names và thread group.
- [Oracle Java SE 11 — `RecordedClass`](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/consumer/RecordedClass.html): class name/ID/modifiers và class loader.
- [Oracle Java SE 11 — `RecordedClassLoader`](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/consumer/RecordedClassLoader.html): loader ID/name/type và trường hợp bootstrap null.
- [Oracle Java SE 11 — `RecordedThreadGroup`](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/consumer/RecordedThreadGroup.html): thread-group name/parent.
- [Oracle Java SE 11 — `RecordedStackTrace`](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/consumer/RecordedStackTrace.html): `getFrames()` và `isTruncated()`.
- [Oracle Java SE 11 — `RecordedFrame`](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/consumer/RecordedFrame.html): Java frame, source line, BCI, frame type và method.
- [Oracle Java SE 11 — `RecordedMethod`](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/consumer/RecordedMethod.html): method name/descriptor/modifiers, hidden và declaring type.
- [Oracle Java SE 11 — `RecordedObject`](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/consumer/RecordedObject.html): `hasField`, `getClass(String)`, `getThread(String)`, `getValue(String)`, field type validation.
- [Oracle Java SE 11 — `RecordingFile`](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingFile.html): đọc file JFR bằng stream hoặc `readAllEvents` cho file nhỏ.
- [Oracle Java SE 11 — `EventSettings`](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/EventSettings.html): `withStackTrace`, `withoutStackTrace`, `withoutThreshold`.
- [Oracle Java SE 11 — `StackTrace` annotation](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/StackTrace.html): thiết lập mặc định việc capture stack ở `Event.commit()`.
- [Oracle Java SE 26 — `RecordedThread`](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.jfr/jdk/jfr/consumer/RecordedThread.html): xác nhận các API tiếp tục áp dụng và ghi chú `isVirtual()` được bổ sung từ Java 21.
- [OpenJDK JEP 328 — Flight Recorder](https://openjdk.org/jeps/328): JFR trong OpenJDK 11 và các nguyên tắc ghi sự kiện để chẩn đoán.

**Ghi nhớ:** Khi đọc file JFR, xem `RecordedThread` là **identity metadata của thread trong JVM nguồn**, `RecordedClass` là **type metadata**, và `RecordedStackTrace` là **ảnh chụp những frames đã được ghi**. Ba lớp khác nhau và có thể thiếu độc lập. Luôn lọc đúng event type, kiểm tra field schema/null, phân biệt ID/tên thread, phân biệt class của event field với class của frame, đánh dấu trace bị cắt, và tránh dùng dữ liệu JFR như một audit trail đầy đủ.