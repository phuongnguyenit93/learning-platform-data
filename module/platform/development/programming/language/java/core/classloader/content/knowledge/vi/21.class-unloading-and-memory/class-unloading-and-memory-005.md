# Metaspace trong HotSpot và giới hạn của mô hình method area

Khi học Java ClassLoader, **method area** và **Metaspace** thường bị dùng như hai tên gọi cho cùng một thứ. Cách nói đó chỉ đúng ở mức diễn giải đơn giản và dễ gây hiểu lầm nghiêm trọng khi cần chẩn đoán **`OutOfMemoryError: Metaspace`**, class-loader leak, native memory hoặc khả năng unload class.

**Phân biệt nền tảng:**

- **Method area** là một **vùng dữ liệu runtime mang tính trừu tượng được Java Virtual Machine Specification (JVMS) yêu cầu**. Nó chứa các cấu trúc theo class như runtime constant pool, thông tin field/method và code của methods/constructors ở mức mô hình. Đặc tả **không bắt buộc** JVM phải triển khai vùng này ở một địa chỉ, một allocator hoặc một heap cụ thể.
- **Metaspace** là **cơ chế HotSpot sử dụng để quản lý một phần quan trọng của class metadata** trong các JDK hiện đại (JDK 8+). HotSpot thường cấp phát metadata này bằng **native memory**, khác với Java object heap chịu giới hạn `-Xmx`.
- **PermGen** là **chi tiết triển khai lịch sử của HotSpot** trước JDK 8. Metaspace thay thế mô hình class-metadata storage cũ của PermGen trong HotSpot, **không có nghĩa cả method area của JVMS đã “biến thành một byte array Metaspace duy nhất”**.
- **Class unloading** phụ thuộc vào runtime class và defining loader theo quy tắc JVM/GC; gọi `URLClassLoader.close()` không trực tiếp xóa class metadata. Metaspace có thể tái sử dụng hoặc trả về hệ điều hành một phần bộ nhớ sau khi JVM thu hồi các class-loader generations phù hợp.
- **Các số liệu memory là những góc nhìn khác nhau**: `used`, `committed`, `reserved`, heap usage, NMT `Class` category, OS RSS và compressed class space **không được cộng trừ hoặc xem là cùng một chỉ số một cách tùy tiện**.

Bài học dựa trên **Java 17+**, phân biệt rõ những yêu cầu **của đặc tả JVM** và những điều **chỉ đúng cho HotSpot/OpenJDK**. Ví dụ cuối bài dùng `java.lang.management`, JAR và hai `URLClassLoader` để quan sát các giới hạn thực tế.

## 1. Phân biệt “đặc tả” và “triển khai” trước khi nói về bộ nhớ

Java là ngôn ngữ và nền tảng có nhiều JVM implementations. Khi đọc **JVMS `2.5.4`**, ta đang đọc mô hình logic mà JVM tương thích phải thể hiện. Khi đọc **HotSpot Metaspace**, ta đang đọc cách một JVM cụ thể triển khai một phần của mô hình ấy.

### Method area theo JVMS

JVMS Java SE 17, `2.5.4` quy định một **method area chia sẻ giữa các JVM threads**, dùng để lưu những cấu trúc theo class, bao gồm:

- Runtime constant pool.
- Dữ liệu của fields và methods.
- Code của methods/constructors, kể cả các phương thức đặc biệt phục vụ initialization.
- Những cấu trúc mà implementation cần để quản lý runtime types.

**Đặc tả nói method area “logically part of the heap”**. Cụm này không có nghĩa HotSpot phải đặt toàn bộ metadata vào **Java heap do `-Xmx` giới hạn**. JVMS cũng nói rõ đặc tả **không ấn định vị trí bộ nhớ**, không yêu cầu một chính sách cụ thể về garbage collection/compaction trong method area, và không bắt mọi implementation lưu compiled code cùng một cách.

Vì vậy hai phát biểu sau **không mâu thuẫn**:

1. **Ở cấp JVMS:** method area được xem là một phần **logic** của heap trong mô hình máy ảo.
2. **Ở cấp HotSpot:** class metadata của Metaspace phần lớn dùng **native/non-heap memory** và được các bộ quản lý/công cụ báo cáo ngoài Java object heap.

Đừng dùng từ “heap” ở hai tầng trừu tượng khác nhau rồi kết luận tài liệu Java tự mâu thuẫn.

### Metaspace là gì?

Metaspace là subsystem quản lý native allocations chứa nhiều cấu trúc liên quan metadata cho **classes được nạp** trong HotSpot. Khi một class được định nghĩa, HotSpot cần metadata để hiểu cấu trúc của runtime type, methods, fields, constant-pool information và những thành phần triển khai khác.

`Metaspace` không phải một Java collection có các object `Class<?>` trực tiếp “nằm trong” theo nghĩa thông thường. Trên HotSpot, **`java.lang.Class` mirrors là các Java objects trên Java heap**, được liên kết với metadata nội bộ tương ứng. Một instance như `new Widget()` cũng ở Java heap; metadata cho runtime class `Widget` có vòng đời/cấp phát khác.

## 2. Sơ đồ dễ nhớ: nơi nào chứa gì?

```text
                   MỘT JVM PROCESS (HotSpot)
  +------------------------------------------------------+
  |                                                      |
  |  Java Object Heap (-Xmx, GC-managed)                |
  |  +-----------------------------------------------+   |
  |  | new Widget() instances                        |   |
  |  | String / Array / Map / Class<?> mirrors        |   |
  |  | objects được static fields tham chiếu tới     |   |
  |  +-----------------------------------------------+   |
  |                                                      |
  |  Native / VM-managed memory                         |
  |  +-----------------------------------------------+   |
  |  | Metaspace: nhiều cấu trúc class metadata      |   |
  |  |  + Non-class metadata allocations             |   |
  |  |  + (khi áp dụng) compressed class space       |   |
  |  +-----------------------------------------------+   |
  |  | Code Cache: machine code/JIT-compiled code    |   |
  |  | Thread stacks, GC data, symbols, VM internals  |   |
  |  +-----------------------------------------------+   |
  |                                                      |
  |  Filesystem / mapped artifacts                      |
  |  +-----------------------------------------------+   |
  |  | class files, JARs, JDK image, CDS archive      |   |
  |  +-----------------------------------------------+   |
  +------------------------------------------------------+
```

Đây là **sơ đồ khái niệm**, không phải memory map chính xác và cũng không diễn tả tất cả cấu trúc của mọi JDK. Một số vùng là virtual memory, một số bytes nằm trong mapped files, một số được dùng chung giữa processes, và cách phân loại NMT phụ thuộc HotSpot/JDK release.

### Bảng phân biệt nhanh

| Thành phần | Thuộc mô hình/triển khai nào? | Thường nằm ở đâu trong HotSpot hiện đại? |
|---|---|---|
| **Method area** | **JVMS logical region** | Không có cam kết vật lý duy nhất; các thành phần được HotSpot hiện thực qua nhiều cấu trúc |
| **Metaspace** | **HotSpot implementation** | Native memory cho class metadata |
| **Java heap** | Runtime area của JVM, HotSpot-managed | Java objects và arrays được garbage collector quản lý |
| **`Class<?>` object** | Java reflection API mirror | Java heap, tham chiếu đến runtime class metadata |
| **Instance `new Foo()`** | Java object | Java heap |
| **Runtime constant pool** | JVMS per-class logical structure | Metadata/VM structures tương ứng, không đồng nghĩa `String` objects nằm hết trong Metaspace |
| **`String` interned objects** | Java objects | Trên các HotSpot hiện đại, `String` instances ở Java heap |
| **JIT compiled machine code** | JIT implementation | HotSpot Code Cache và các vùng VM tương ứng, không nói “toàn bộ trong Metaspace” |
| **Bytecode .class trong JAR** | Artifact của ứng dụng | File/JAR/CDS image; không đồng nghĩa mỗi file phải được giữ nguyên bản copy trong Metaspace |
| **Native thread stack** | OS/JVM execution resource | Ngoài Java heap; không phải Metaspace |

Một method có thể có **bytecode metadata** gắn với class và **machine code đã JIT compile** ở code cache. Đừng gộp bytecode, compiled code và method metadata thành một con số “kích thước method area” mà Java API buộc phải công bố.

## 3. Từ PermGen tới Metaspace

### PermGen của HotSpot lịch sử

Ở các phiên bản HotSpot trước JDK 8, class metadata và một số thành phần liên quan được quản lý thông qua cơ chế **Permanent Generation (PermGen)**. Người vận hành thường gặp:

```text
java.lang.OutOfMemoryError: PermGen space
```

và tùy chọn lịch sử `-XX:MaxPermSize`.

### JDK 8 trở đi

HotSpot chuyển class metadata sang **Metaspace**, sử dụng native memory và các thuật toán cấp phát khác. Vì thế lỗi thiếu không gian metadata thường biểu hiện:

```text
java.lang.OutOfMemoryError: Metaspace
```

**Tuy nhiên, không nên nói “PermGen và Metaspace là hai JVM memory areas được JVMS quy định”.** Cả hai là implementation details của HotSpot ở những thời kỳ khác nhau; JVMS vẫn mô tả **method area** trừu tượng.

Tùy chọn `-XX:MaxPermSize` không phải cách giới hạn Metaspace trên JDK 17. Muốn đặt ngưỡng class metadata của HotSpot dùng **`-XX:MaxMetaspaceSize`** với ý nghĩa và giới hạn riêng.

### JDK 16+: Elastic Metaspace

**JEP 387 (Elastic Metaspace)** được đưa vào **JDK 16** nhằm giảm footprint metadata và giúp HotSpot **trả lại bộ nhớ không dùng về hệ điều hành** kịp thời hơn sau class unloading. Nó dùng cơ chế quản lý virtual-memory chunks/commit granules và các chính sách reclamation.

Bài học quan trọng:

- “Metaspace có khả năng co lại” **không đồng nghĩa** JVM luôn lập tức giảm RSS sau khi đóng một plugin loader.
- Trả bộ nhớ về OS phụ thuộc class unloading, allocator state, kích cỡ/granularity, chính sách reclaim và môi trường đo.
- Bộ nhớ được **free/reuse trong allocator** khác với **uncommit** native pages; và uncommit khác với OS RSS lập tức giảm đúng bằng một con số.
- Một phần metadata còn sống vẫn cần memory giữ lại, kể cả khi đã dọn nhiều class-loader generations.

## 4. ClassLoader liên quan thế nào tới Metaspace?

Mỗi **runtime class** được xác định bởi:

```text
(binary class name, defining class loader)
```

Ví dụ hai loader cùng định nghĩa `example.Widget`:

```text
URLClassLoader A
   └── ("example.Widget", A) -> class metadata của A

URLClassLoader B
   └── ("example.Widget", B) -> class metadata của B
```

Hai runtime classes khác nhau, nên JVM có thể cần **metadata riêng** cho từng class. Không có quy tắc “cùng tên + cùng bytecode thì JVM chỉ tốn một bản class metadata” trong mọi trường hợp.

### Vì sao plugin reload dễ làm Metaspace tăng?

Một plugin manager có thể tạo loader mới ở mỗi lần cập nhật:

```text
V1: Loader-1 -> plugin classes v1 -> metadata generation 1
V2: Loader-2 -> plugin classes v2 -> metadata generation 2
V3: Loader-3 -> plugin classes v3 -> metadata generation 3
...
```

Nếu loader generations cũ **vẫn còn reachable** qua registrations, threads hoặc caches, JVM chưa thể thu hồi chúng theo class-unloading rules; lượng class metadata có thể tiếp tục tăng.

Các **nguồn giữ loader** phổ biến:

- Plugin instance bị host giữ trong `Map`, registry hoặc listener list.
- `Class<?>`, `Method`, `Constructor`, `MethodHandle`, generated proxy classes và reflection caches bị lưu giữ.
- Thread vẫn chạy code plugin hoặc **thread context class loader (TCCL)** trỏ tới plugin loader.
- `ThreadLocal` value ở executor thread giữ plugin objects.
- ServiceLoader/provider cache, JDBC driver, MBeans, logging handlers hoặc scheduled tasks chưa unregister.
- Loader graph có strong references từ host hoặc custom loader khác.
- Active call frames, native/JNI global references hay resource lifecycle không được dọn.

**Không phải mọi tăng trưởng Metaspace đều là leak.** Một JVM đang warm-up có thể nạp nhiều classes cần dùng và đạt plateau bình thường. Cần quan sát **số loaded classes, loader generations, used/committed metadata và retaining paths theo thời gian**.

## 5. Class unloading gắn với defining loader

**JLS 12.7** cho phép JVM unload một class/interface khi **defining class loader đủ điều kiện để GC thu hồi**; thời điểm unload do JVM quyết định. Nếu host còn giữ một instance, `Class<?>`, reflection cache hoặc TCCL của plugin, generation cũ có thể vẫn reachable và Metaspace không được giải phóng cho generation đó.

Đối với ứng dụng reload lặp lại, kiểm tra retaining paths và class-loader generations **trước khi tăng `MaxMetaspaceSize`**; cấu hình bộ nhớ chỉ giảm áp lực tạm thời nếu nguyên nhân là retention.

## 6. Metaspace và Java heap có những OOME riêng

| Lỗi/triệu chứng | Nguyên nhân thường liên quan | Cách điều tra |
|---|---|---|
| `OutOfMemoryError: Java heap space` | Heap objects/arrays, retention, allocation pressure | Heap usage, allocation profiler, heap dump, `-Xmx` |
| `OutOfMemoryError: Metaspace` | HotSpot không thể cấp phát thêm metadata do giới hạn hoặc native memory pressure | Loader/class counts, metaspace pools, `MaxMetaspaceSize`, NMT |
| `OutOfMemoryError: Compressed class space` | Vùng dành cho compressed class pointers/class metadata chạm giới hạn phù hợp | `CompressedClassSpaceSize`, NMT `Class` category, số/loại classes |
| `OutOfMemoryError: unable to create native thread` | Native memory, thread/process limits, OS resources | Thread count/stacks, OS/container limits |
| JVM/process bị OS kill (OOM killer) | Tổng resident/native + heap + stack + JIT/CDS/... vượt hạn ngạch | OS/container RSS, `memory.events`, NMT và GC logs |
| Metaspace committed cao nhưng used thấp | Allocator overhead/free chunks, fragmentation/reclaim policy, sampling | Theo dõi used vs committed/reserved và class unloading theo thời gian |

**Không đánh đồng `OutOfMemoryError: Metaspace` với Java heap đã đầy.** Nâng `-Xmx` không mặc nhiên chữa lỗi Metaspace; tăng heap quá lớn trong container memory-limited còn có thể giảm native headroom.

Ngược lại, đặt `-XX:MaxMetaspaceSize` cao hơn **không chữa classloader leak**; nó có thể trì hoãn triệu chứng trong khi loader generations cũ vẫn còn reachable.

## 7. Ba từ then chốt: used, committed và reserved

Khi quan sát Metaspace/NMT, hãy tách ba mức:

### Used

`used`: bộ nhớ mà allocator/pool báo đã dùng cho metadata hoặc phần sử dụng theo cách thống kê của công cụ. Không phải số lượng objects trên heap, cũng không tự tương đương với OS resident bytes.

### Committed

`committed`: lượng virtual-memory backing đã được JVM **commit** cho vùng liên quan và có thể dùng theo cơ chế quản lý đó. Có thể lớn hơn `used` vì allocations được tổ chức theo chunks/granules, có slack/fragmentation hoặc memory sẵn cho lần cấp phát tiếp theo.

### Reserved

`reserved`: **không gian địa chỉ ảo** JVM dành trước để có thể commit khi cần. `reserved` lớn **không có nghĩa** hệ điều hành đã cấp RAM vật lý cho tất cả bytes ấy.

```text
Virtual address space reserved (có thể rất lớn)
+------------------------------------------------------+
| Committed virtual memory backing                     |
| +----------------------------------+                  |
| | Used metadata | free/slack/      |                  |
| |               | allocator space  |                  |
| +----------------------------------+                  |
|              vùng chưa committed                      |
+------------------------------------------------------+
```

Các chỉ số thay đổi động. Một báo cáo NMT `Class reserved=... committed=...` không phải phép đo “RAM còn trống” hoặc “Java heap đã dùng”. Đặc biệt **Compressed Class Space có thể reserve một vùng địa chỉ ảo lớn** nhưng committed ban đầu nhỏ hơn đáng kể.

### OS RSS có bằng Metaspace committed không?

Không nhất thiết. **Resident Set Size (RSS)** là góc nhìn pages cư trú của toàn process theo OS; nó gồm nhiều subsystem ngoài Metaspace. Shared/mapped pages, demand paging, accounting và memory reclamation làm việc đối chiếu RSS ↔ committed không phải phép cộng đơn giản.

Khi tối ưu theo RAM của container, hãy phối hợp **heap, GC native allocations, metaspace, code cache, thread stacks, direct buffers, libraries/mapped regions và OS reports**. NMT giúp nhìn HotSpot internals nhưng không thống kê toàn bộ native allocations của các thư viện bên thứ ba.

## 8. Giới hạn cấu hình trong HotSpot Java 17+

### `-XX:MaxMetaspaceSize`

Đặt ngưỡng tối đa cho native memory HotSpot dành cho class metadata theo semantics của JVM, ví dụ:

```bash
java -XX:MaxMetaspaceSize=256m -jar app.jar
```

Đây là **lệnh minh họa** cần artifact `app.jar` phù hợp. Nếu các metadata allocations cần vượt giới hạn, JVM có thể thử GC/class unloading rồi cuối cùng ném `OutOfMemoryError: Metaspace`.

Không nên chọn `256m` tùy tiện làm mức production. Phải đo workload có số classes, plugin generations, class metadata, compressed class space và safety headroom phù hợp.

### `-XX:MetaspaceSize`

Đây chủ yếu là **ngưỡng liên quan metadata allocation và kích hoạt một số GC hoạt động**, không phải “Metaspace bắt đầu được pre-allocate chính xác X MB” cũng không phải giới hạn tối đa như `MaxMetaspaceSize`.

Một cấu hình minh họa:

```bash
java -XX:MetaspaceSize=64m -XX:MaxMetaspaceSize=256m -jar app.jar
```

Đừng ngầm hiểu JVM ngay lập tức chiếm 64 MB physical RAM chỉ vì `MetaspaceSize=64m`.

### `-XX:CompressedClassSpaceSize`

Khi HotSpot dùng **compressed class pointers**, metadata có thể chia thành non-class metadata và class metadata trong **compressed class space**. Tùy chọn:

```bash
java -XX:CompressedClassSpaceSize=256m -jar app.jar
```

có thể điều chỉnh kích cỡ reservation/giới hạn tương ứng trong những cấu hình hỗ trợ. Không sử dụng tùy chọn này nếu chưa xác nhận JVM/flags và vấn đề thực sự nằm ở compressed class space.

Một vùng reserved lớn ở NMT `Class` **không phải bằng chứng rò rỉ RAM vật lý**, vì phần lớn virtual space có thể chưa committed.

### `-XX:MetaspaceReclaimPolicy`

HotSpot sau **JEP 387** hỗ trợ các lựa chọn như:

```text
balanced
aggressive
none
```

Với tùy chọn:

```bash
java -XX:MetaspaceReclaimPolicy=balanced -jar app.jar
```

`balanced` là chính sách mặc định thường dùng trong các HotSpot versions áp dụng Elastic Metaspace; `aggressive` có thể tăng độ tích cực khi uncommit/reclaim, đổi lại một số chi phí bookkeeping; `none` giảm hành động trả bộ nhớ theo chính sách đó.

**Không xem `aggressive` là “luôn ít RAM nhất và nhanh nhất”.** Workload có class loading/unloading thường xuyên cần đo throughput, pause behavior và footprint, không tối ưu một con số tại một thời điểm.

### `-Xmx` là chuyện khác

`-Xmx` giới hạn Java heap. Đặt:

```bash
java -Xmx512m -XX:MaxMetaspaceSize=128m -jar app.jar
```

không có nghĩa JVM process bị giới hạn ở 640 MB. Vẫn còn thread stacks, code cache, GC native metadata, direct buffers, JIT, mapped libraries, CDS, JVM internals và OS-level overhead. Nếu chạy trong container, cần dự trù headroom thực thay vì cộng hai flags thành memory limit.

## 9. Demo Java 17+: quan sát Metaspace và hai loader cùng tên class

Demo dưới đây là một **chương trình runnable thực tế**, dùng `java.lang.management.MemoryPoolMXBean` để quan sát **HotSpot pool tên `Metaspace`**, rồi tạo **hai `URLClassLoader`** nạp một JAR có class `example.Widget`.

**Không đưa ra số used/committed cố định:** memory snapshots thay đổi theo JDK, GC, CDS, flags và thời điểm quan sát. Thay vào đó, ví dụ xác nhận những invariant và ngữ nghĩa ổn định đã được kiểm thử.

### 9.1. Cấu trúc thư mục

```text
metaspace-demo/
├── src/
│   ├── plugin/
│   │   └── example/
│   │       └── Widget.java
│   └── host/
│       └── host/
│           └── MetaspaceDemo.java
├── out/
│   ├── plugin/
│   └── host/
└── plugin.jar
```

### 9.2. Class plugin

Tệp **`src/plugin/example/Widget.java`**:

```java
package example;

public final class Widget {
    private static int calls;

    public String hello() {
        calls++;
        return "hello " + calls;
    }
}
```

`calls` là static state theo **runtime class**, không phải biến toàn JVM theo string tên class.

### 9.3. Chương trình host

Tệp **`src/host/host/MetaspaceDemo.java`**:

```java
package host;

import java.lang.management.ManagementFactory;
import java.lang.management.MemoryPoolMXBean;
import java.lang.management.MemoryType;
import java.lang.management.MemoryUsage;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public final class MetaspaceDemo {
    public static void main(String[] args) throws Exception {
        MemoryPoolMXBean metaspace = ManagementFactory
                .getMemoryPoolMXBeans().stream()
                .filter(p -> p.getName().equals("Metaspace"))
                .findFirst().orElseThrow();

        System.out.println("Pool name: " + metaspace.getName());
        System.out.println("Pool is non-heap: "
                + (metaspace.getType() == MemoryType.NON_HEAP));

        MemoryUsage sample = metaspace.getUsage();
        System.out.println("Metadata snapshot valid: "
                + (sample != null && sample.getUsed() >= 0
                   && sample.getCommitted() >= sample.getUsed()));

        URL code = Path.of(args[0]).toUri().toURL();
        ClassLoader parent = MetaspaceDemo.class.getClassLoader();

        try (URLClassLoader a =
                     new URLClassLoader(new URL[] {code}, parent);
             URLClassLoader b =
                     new URLClassLoader(new URL[] {code}, parent)) {

            Class<?> ca = a.loadClass("example.Widget");
            Class<?> cb = b.loadClass("example.Widget");

            System.out.println("Same binary name: "
                    + ca.getName().equals(cb.getName()));
            System.out.println("Different runtime classes: "
                    + (ca != cb));
            System.out.println("Each child defines its class: "
                    + (ca.getClassLoader() == a
                       && cb.getClassLoader() == b));

            Object objectA =
                    ca.getDeclaredConstructor().newInstance();
            System.out.println("Instance created: "
                    + (objectA != null));

            System.out.println("Method: "
                    + ca.getMethod("hello").invoke(objectA));

            a.close();

            System.out.println("Method after close: "
                    + ca.getMethod("hello").invoke(objectA));

            MemoryUsage after = metaspace.getUsage();
            System.out.println("After snapshot valid: "
                    + (after != null && after.getUsed() >= 0));
        }
    }
}
```

### 9.4. Biên dịch và chạy — Bash

Từ thư mục `metaspace-demo` trên Linux/macOS/Git Bash:

```bash
mkdir -p out/plugin out/host

javac --release 17 -d out/plugin \
  src/plugin/example/Widget.java

javac --release 17 -d out/host \
  src/host/host/MetaspaceDemo.java

jar --create --file plugin.jar -C out/plugin .

# Chỉ host classes nằm trên classpath hệ thống.
java -cp out/host host.MetaspaceDemo plugin.jar

# Thử giới hạn Metaspace và bật NMT để thực hành.
java -XX:MaxMetaspaceSize=64m \
  -XX:NativeMemoryTracking=summary \
  -cp out/host host.MetaspaceDemo plugin.jar
```

**Lưu ý:** Đường `plugin.jar` đi vào **program argument**, không vào `-cp`. Nếu đưa plugin JAR vào parent classpath, hai `URLClassLoader` parent-first có thể trả cùng class từ parent thay vì tự định nghĩa.

### 9.5. Lệnh tương đương PowerShell

```powershell
New-Item -ItemType Directory -Force -Path out/plugin, out/host | Out-Null

javac --release 17 -d out/plugin src/plugin/example/Widget.java
javac --release 17 -d out/host src/host/host/MetaspaceDemo.java

jar --create --file plugin.jar -C out/plugin .

java -cp out/host host.MetaspaceDemo plugin.jar

java -XX:MaxMetaspaceSize=64m -XX:NativeMemoryTracking=summary -cp out/host host.MetaspaceDemo plugin.jar
```

### 9.6. Kết quả đã biên dịch và kiểm thử

Đã biên dịch với **`javac --release 17`** và chạy trên **OpenJDK 24.0.2**. Cả bản baseline lẫn bản có `-XX:MaxMetaspaceSize=64m` và `-XX:NativeMemoryTracking=summary` in chính xác:

```text
Pool name: Metaspace
Pool is non-heap: true
Metadata snapshot valid: true
Same binary name: true
Different runtime classes: true
Each child defines its class: true
Instance created: true
Method: hello 1
Method after close: hello 2
After snapshot valid: true
```

**Giải thích từng nhóm kết quả:**

1. **Pool name: Metaspace** — ứng dụng đang chạy trên HotSpot/OpenJDK có `MemoryPoolMXBean` pool tên `Metaspace`. Không nên giả định tên pool này tồn tại trên mọi JVM implementation khác.
2. **Pool is non-heap: true** — API quản lý bộ nhớ của HotSpot phân loại pool này là **NON_HEAP**. Điều đó không bác bỏ phát biểu “method area logically part of the heap” trong JVMS vì hai câu thuộc **hai cấp độ trừu tượng**.
3. **Metadata snapshot valid: true** — có thể lấy một sample hợp lệ và `committed >= used`. Số bytes tuyệt đối không được kiểm thử cố định.
4. **Same binary name: true** và **Different runtime classes: true** — hai `Class<?>` có cùng tên nhưng khác defining loaders.
5. **Each child defines its class: true** — `ca.getClassLoader() == a` và `cb.getClassLoader() == b`, xác nhận isolation.
6. **Method: hello 1** — plugin object đã tạo và method hoạt động.
7. **Method after close: hello 2** — class đã nạp tiếp tục hoạt động dù loader A gọi `close()`; điều này **không phải class unloading**.
8. **After snapshot valid: true** — bean vẫn cho snapshot metadata; không khẳng định size đã giảm hoặc loader cũ đã collectible.

**Giới hạn của demo:** Ứng dụng vẫn giữ `ca`, `cb`, `objectA` trong scope, nên **không** được kỳ vọng JVM unload/reclaim các classes ngay ở đây. `URLClassLoader.close()` xử lý tài nguyên loader, không phải trình điều khiển garbage collector.

## 10. Đọc số liệu MemoryPoolMXBean đúng cách

Từ `java.lang.management`:

```java
MemoryPoolMXBean pool = ManagementFactory
        .getMemoryPoolMXBeans().stream()
        .filter(p -> p.getName().equals("Metaspace"))
        .findFirst().orElseThrow();

MemoryUsage usage = pool.getUsage();

if (usage != null) {
    System.out.println("used=" + usage.getUsed());
    System.out.println("committed=" + usage.getCommitted());
    System.out.println("max=" + usage.getMax());
}
```

Đây là **snippet minh họa bên trong method** với imports `java.lang.management.*`. Nó sẽ in **giá trị động**, không nên dùng một con số stdout cố định làm đáp án.

**Ý nghĩa:**

- `getUsed()`: lượng memory mà pool thống kê đang sử dụng.
- `getCommitted()`: lượng memory backing được commit theo Java Management API cho pool.
- `getMax()`: có thể là **`-1`** nếu không có maximum xác định cho pool theo implementation/configuration. **Không** tự thay `-1` bằng tổng RAM máy.
- Một measurement có thể thay đổi giữa các lần gọi; nếu cần tính delta phải chọn snapshot boundaries/thời điểm rõ ràng.

Nếu chạy trên non-HotSpot JVM, pool có thể có tên khác hoặc không cung cấp cách phân loại tương tự. Nếu logic ứng dụng phụ thuộc memory-pool naming, hãy coi đó là **monitoring integration theo JVM vendor**, không phải JVM portability contract.

### “Used bytes tăng sau khi load class” có chứng minh gì?

Chỉ ra có thay đổi ở snapshot; chưa chứng minh toàn bộ delta do đúng một class. Ngay lúc đó có thể:

- JDK lazily load management/reflection classes.
- Reflection tạo metadata hoặc cache.
- Loader và ZIP/JAR handling tạo nhiều allocations.
- GC/class unloading xảy ra xen kẽ.
- JIT compilation/caches/thread scheduling ảnh hưởng hành vi đo.

Để kết luận về nguyên nhân, đo nhiều lần, dùng JFR/profiler/NMT/classloader stats và phân biệt chi phí ổn định với warmup. Không assert “mỗi class = X bytes Metaspace”.

## 11. Native Memory Tracking (NMT): quan sát toàn VM theo categories

**Native Memory Tracking** là tính năng HotSpot giúp theo dõi những nhóm native allocations của **HotSpot VM**. Trên Java 17, bật lúc **khởi động process**:

```bash
java -XX:NativeMemoryTracking=summary -jar app.jar
```

Hoặc cần phân tích chi tiết hơn:

```bash
java -XX:NativeMemoryTracking=detail -jar app.jar
```

**Không thể bật NMT từ trạng thái off thành on cho process đang chạy chỉ bằng `jcmd`**; thiết kế công cụ cần bật từ startup nếu dự kiến phải điều tra. `detail` có thể tăng overhead và tạo lượng thông tin lớn.

### 11.1. Sử dụng jcmd

Sau khi ứng dụng đang chạy có PID, ví dụ `12345`:

```bash
jcmd 12345 VM.native_memory summary
jcmd 12345 VM.native_memory summary scale=MB
```

Muốn so sánh snapshots cùng process:

```bash
jcmd 12345 VM.native_memory baseline
# Chạy workload: khởi tạo plugins, reload một nhóm.
jcmd 12345 VM.native_memory summary.diff scale=MB
```

Dấu `#` là comment Bash. Trong PowerShell, cũng dùng `#` cho comment; `jcmd` syntax tương tự.

**Đừng ghi nguyên con số PID `12345` vào runbook như giá trị cố định.** Tìm PID của Java process thực tế bằng `jcmd -l` hoặc công cụ OS phù hợp, rồi thay vào lệnh.

### 11.2. NMT báo gì?

Tùy JDK, output tóm tắt có thể có:

```text
Total: reserved=..., committed=...
  Java Heap       (reserved=..., committed=...)
  Class           (reserved=..., committed=...)
  Thread          (reserved=..., committed=...)
  Code            (reserved=..., committed=...)
  GC              (reserved=..., committed=...)
  Internal        (reserved=..., committed=...)
  ...
```

Đây là **minh họa bố cục**, không phải log chạy cố định; tên categories và cách chi tiết hóa có thể thay đổi giữa HotSpot releases.

Với `Class`, một phần số liệu có thể mô tả metadata/non-class memory, compressed class space, số classes hoặc loader data. **Không kết luận rằng `Class reserved` là toàn bộ RSS**, và **không cộng số `reserved` vào số `committed`** như hai khoản RAM khác nhau.

### 11.3. Giới hạn quan trọng của NMT

NMT **không theo dõi tất cả allocations của bên thứ ba/native libraries** và không nhất thiết đo đầy đủ mọi mapped/CDS memory theo cách người đọc mong muốn. NMT bật theo subsystem có overhead vận hành; nó là công cụ chẩn đoán HotSpot, không thay cho OS metrics.

Do đó:

- NMT cho thấy **VM internal native allocations** tương ứng category nào tăng.
- Heap dump cho thấy **retaining paths của Java objects**.
- JVM classloader stats cho thấy **loader/class populations**.
- OS/container metrics cho thấy **RSS/cgroup usage** và áp lực process thực.
- Kết hợp các nguồn mới chẩn đoán hợp lý.

## 12. VM.classloader_stats và class-unload logging

Trên HotSpot hỗ trợ diagnostic command:

```bash
jcmd 12345 VM.classloader_stats
```

Lệnh này giúp quan sát class loaders và class metadata/class counts theo khả năng JVM. **Không có nghĩa** cứ số loader lớn là leak: application servers và plugin frameworks có thể hợp lệ khi cần nhiều loader.

Để quan sát khi JVM thực hiện class unloading:

```bash
java '-Xlog:class+load=info,class+unload=info' -jar app.jar
```

PowerShell:

```powershell
java "-Xlog:class+load=info,class+unload=info" -jar app.jar
```

Có log `class+unload` khi VM unload một số classes **không chứng minh tất cả plugin resources được cleanup**; ngược lại **không có log unload trong một test ngắn** không chứng minh leak. GC không cam kết unload xảy ra ngay sau `close()` hoặc `System.gc()`.

`java -Xlog:help` liệt kê tags/mức logging được runtime hỗ trợ. Dùng công cụ theo JDK/vendor tương ứng.

## 13. Điều tra một classloader leak làm Metaspace tăng

Giả sử một server cập nhật plugin mỗi phút, mỗi lần tạo `URLClassLoader` mới. Ban đầu mọi thứ ổn, sau vài giờ thấy:

```text
Metaspace used         tăng dần sau mỗi reload
Class count            tăng dần
Classloader generations tăng dần
OS/container memory    tăng dần hoặc dao động cao
GC cycles              có nhưng ít/không unload loader cũ
```

Đây là **mẫu nghi vấn** chứ không phải bằng chứng; metric phải đo thực và phân tích retaining graph.

### Quy trình 7 bước

1. **Chốt baseline:** runtime version, container memory limit, `-Xmx`, `MaxMetaspaceSize`, GC, CDS, flags và loader count trước reload.
2. **Tái hiện có kiểm soát:** lặp plugin load/stop/reload N lần trong môi trường thử nghiệm; log generation IDs.
3. **Theo dõi heap và non-heap độc lập:** lấy Metaspace pool used/committed, NMT `Class` category và heap object population.
4. **Đếm loader/class populations:** `jcmd VM.classloader_stats`, JFR class loading/unloading events khi được bật.
5. **Phân tích heap retaining paths:** xác định những GC roots còn trỏ tới loader cũ hoặc object/class/method của nó.
6. **Dọn lifecycle:** threads, executors, TCCL, listener registries, JDBC/MBeans, reflection/ServiceLoader caches, buffers và resource handles.
7. **Đo lại sau cleanup:** không yêu cầu số liệu tụt ngay nhưng cần xu hướng ổn định hơn; nếu vẫn tăng, quay lại retaining paths/VM-level profiling.

### Ví dụ đường giữ loader

```text
GC root / long-lived host object
    |
    +--> static Map<String, Handler> in host
            |
            +--> PluginHandler instance
                    |
                    +--> Class<plugin.Handler>
                            |
                            +--> defining URLClassLoader V1
                                    |
                                    +--> plugin classes/metadata
```

Dù `pluginManager.currentLoader = loaderV2`, một reference còn trong static map có thể khiến loader V1 vẫn reachable. Thay loader reference chính **không tự xóa mọi references khác**.

**Không phải cứ static field trong plugin là leak vĩnh viễn.** Những object cycles chỉ tự trỏ vào nhau có thể được GC thu hồi khi cả graph không còn reachable từ GC roots. Vấn đề nằm ở **reference roots thật sự** và runtime lifecycle.

## 14. Khi nào Metaspace được tái sử dụng hoặc trả lại OS?

Trên HotSpot hiện đại, metadata allocations thường được quản lý theo **class-loader-associated arenas/chunks**. Từ góc nhìn đơn giản:

```text
Define classes -> class metadata allocations -> Metaspace chunks
          |
          v
Retire class loader generation
          |
          v
Bỏ được các strong references tới loader/classes/instances?
          |
         Có
          |
          v
JVM/GC có thể unload class loader và các classes
          |
          v
Allocator có free chunks hoặc vùng có thể reuse
          |
          v
Elastic Metaspace có thể uncommit một phần unused pages
          |
          v
OS resident memory có thể giảm (không hứa đúng thời điểm/số bytes)
```

### Lý do used giảm mà committed chưa giảm

- Chunk có free space nhưng vẫn được giữ để **tái sử dụng nhanh**.
- Các commit granules còn metadata sống nên chưa thể uncommit hết.
- Reclaim policy hướng tới cân bằng footprint và CPU overhead.
- Thời điểm GC/class unloading chưa xảy ra hoặc chưa đủ điều kiện.
- Công cụ lấy snapshot ở thời điểm khác nhau.

### Lý do committed giảm nhưng process RSS chưa giảm tương ứng

- OS accounting/mapped pages hoạt động khác expected.
- Subsystems khác đồng thời tăng native memory hoặc heap committed/resident.
- Những pages đã trả/đánh dấu nhưng số liệu RSS chưa phản ánh tức thời.
- Cgroup/process measures và NMT dùng phạm vi khác nhau.

Vì vậy KPI nên gồm **Metaspace used/committed, classloader count, native total, RSS và thời gian**, không chỉ một thanh biểu đồ.

## 15. Compressed Class Space không phải mọi Metaspace

Trong HotSpot 64-bit với **compressed class pointers**, metadata class pointers có thể được biểu diễn qua một vùng địa chỉ được reserve thích hợp gọi **Compressed Class Space**. Một phần non-class metadata dùng allocator khác.

Điều này dẫn tới các báo cáo như:

```text
Class (reserved=..., committed=...)
  Metadata: ...
  Class space: ...
```

Tùy HotSpot/JDK, presentation chính xác có thể khác.

**Phân biệt:**

- `CompressedClassSpaceSize`: giới hạn/reservation liên quan compressed class space trong cấu hình áp dụng.
- `MaxMetaspaceSize`: giới hạn tổng class-metadata allocations theo HotSpot option.
- `-Xmx`: giới hạn Java heap, **không** giới hạn trực tiếp metaspace.
- `reserved`: virtual address space, không bằng resident RAM.
- `committed`: memory backing, không có nghĩa tất cả là objects đang dùng.
- `used`: snapshot theo allocator accounting, không phải số bytes tương đương một class-file JAR.

Nếu `OutOfMemoryError: Compressed class space` xuất hiện, tăng `MaxMetaspaceSize` đơn lẻ không phải lúc nào cũng giải quyết được giới hạn khác; cần xem compressed class space configuration, số lượng classes/loader generations và native headroom.

## 16. CDS, code cache và metadata sharing

**Class Data Sharing (CDS)** trên HotSpot giúp chia sẻ một số class data đã chuẩn bị trước giữa Java processes hoặc cải thiện startup/memory footprint khi archive được sử dụng.

Nhưng:

- CDS không đồng nghĩa “mọi custom-loader class metadata đều được chia sẻ”.
- Một class loader mới vẫn có runtime class identity/lifecycle của mình.
- CDS không biến objects/static mutable fields của plugin A thành state chung có kiểm soát.
- CDS không loại bỏ mọi chi phí class initialization, dynamic linking hoặc JIT.
- Memory-mapped CDS archives có accounting khác với Metaspace committed và Java heap.

Tương tự, **JIT code cache** lưu native compiled code phục vụ thực thi methods. Nó có memory lifecycle và flags riêng; **không nên gộp code cache vào Metaspace chỉ vì method thuộc một class đã load**.

Khi profile native memory, so sánh các nhóm **`Class`, `Code`, `Thread`, `GC` và `Java Heap`** theo công cụ hỗ trợ; tránh đổ lỗi Metaspace cho mọi native memory growth.

## 17. Khác biệt giữa “metadata tăng” và “heap leak”

| Dấu hiệu quan sát | Hướng nghi vấn | Xác minh tiếp |
|---|---|---|
| Heap objects tăng mạnh, loader/class counts ổn định | Heap cache/leak thông thường | Heap histograms, heap dump, allocation profile |
| Loader/class counts tăng theo số plugin reload | Loader generations giữ lại | Retaining path từ GC roots, stop/unregister |
| Metaspace used tăng, heap ổn định tương đối | Nhiều class definitions/loader retention | NMT, classloader stats, JFR |
| Metaspace used plateau, committed cao hơn | Allocator slack/reclaim timing | Elastic Metaspace policy, trends |
| RSS tăng nhưng Metaspace stable | Native subsystem khác, direct buffers, threads, JNI, GC, JIT | NMT subsystem diff và OS tools |
| `Class reserved` rất lớn nhưng committed thấp | Virtual address reservation cho compressed class pointers | Không quy trực tiếp thành physical memory leak |

Trong server containerized, memory leak còn có thể đến từ **direct/mapped buffers**, JNI libraries hoặc native agents mà NMT không thống kê đầy đủ. Đừng chỉ điều chỉnh `MaxMetaspaceSize` nếu OS đang kill process vì RSS tăng từ thành phần khác.

## 18. Những ngộ nhận cần loại bỏ

### “Method area chính là Metaspace theo đặc tả Java”

**Không chính xác.** Method area là abstract runtime region của JVMS; Metaspace là HotSpot implementation detail cho class metadata. Một JVM khác có thể dùng cơ chế phân bổ khác mà vẫn phù hợp đặc tả.

### “Method area logically part of heap, vậy `-Xmx` phải giới hạn Metaspace”

**Không.** `-Xmx` giới hạn Java object heap của HotSpot, còn nhiều HotSpot metadata allocations nằm trong native/non-heap memory. Cụm “logically part” không phải lời cam kết placement vật lý.

### “Tất cả static variables nằm hoàn toàn trong Metaspace”

**Sai về mức độ tuyệt đối.** Class metadata, static field storage, `Class<?>` mirrors và object mà static reference trỏ tới có cách biểu diễn/placement khác nhau theo HotSpot implementation. Đặc biệt **object được static field tham chiếu tới nằm ở Java heap**. Không vẽ mọi static value thành các bytes luôn nằm nguyên trong Metaspace.

### “JAR có 30 MB class files thì Metaspace phải dùng 30 MB”

**Không.** Kích thước JAR đã nén, số classes thực load, class metadata structures, shared archives, JIT code, resources và allocator overhead là các đại lượng khác nhau.

### “Mỗi class loader luôn có một Metaspace riêng”

**Không theo nghĩa một pool riêng có size cố định.** HotSpot có subsystem Metaspace chung và cấp chunks/arenas gắn với loader data structures. Những loaders khác nhau có metadata ownership khác nhau, nhưng không phải mỗi loader sở hữu một OS memory pool độc lập với một `MaxMetaspaceSize` riêng.

### “Đóng loader thì Metaspace sẽ lập tức giảm”

**Không.** `URLClassLoader.close()` giải phóng tài nguyên loader, không buộc GC/class unloading. Loader có thể còn reachable; cũng có allocator reclaim delay.

### “Metaspace reserved 1 GB nghĩa là JVM đã ăn 1 GB RAM”

**Không.** Reserved virtual address space khác committed physical backing và khác resident memory. Đặc biệt compressed class space có thể reserve một khoảng địa chỉ lớn.

### “Tăng `MaxMetaspaceSize` là sửa được Metaspace leak”

**Không.** Nó thay giới hạn, không xóa references giữ classloader generations. Cần tìm root cause bằng profiling/heap graph.

### “Method area không bao giờ GC được”

JVMS không bắt buộc mọi implementation áp dụng policy GC cụ thể cho method area; **không cấm JVM thực hiện class unloading**. HotSpot có class unloading và reclaim metadata theo các điều kiện nhất định. JLS giới hạn khi class có thể unload.

## 19. Checklist vận hành Metaspace cho ứng dụng plugin

- [ ] Ghi rõ **JVM implementation/vendor/version** đang chạy.
- [ ] Tách **JVMS method area** khỏi **HotSpot Metaspace** khi giải thích.
- [ ] Không cộng `-Xmx` với `MaxMetaspaceSize` rồi gọi đó là tổng giới hạn RAM process.
- [ ] Quan sát `Metaspace` pool `used/committed` và biết `max` có thể là `-1`.
- [ ] Phân biệt `reserved`, `committed`, `used` và **RSS**.
- [ ] Theo dõi **loaded-class count** và **classloader generations** theo thời gian.
- [ ] Nếu nghi leak, lấy **heap retaining paths** đến loader/instance/reflection handles.
- [ ] Kiểm tra TCCL, `ThreadLocal`, executors, listeners, `ServiceLoader` và global registries.
- [ ] Khi plugin retire, dừng work rồi cleanup và `close` loader đúng thứ tự.
- [ ] Không dùng `System.gc()` làm điều kiện bắt buộc xác nhận unload.
- [ ] Nếu bật NMT, bật từ startup và chấp nhận profiling overhead.
- [ ] Khi điều chỉnh `MetaspaceReclaimPolicy`, benchmark memory lẫn CPU/latency.
- [ ] Kiểm tra CDS, compressed class pointers và allocator differences trước khi diễn giải NMT.
- [ ] Kiểm tra container/cgroup limits, native headroom và các memory pools khác.
- [ ] Không sử dụng classloader như sandbox an ninh chỉ vì nó cách ly metadata.

## 20. Câu hỏi tự kiểm tra

**1. Method area có phải tên riêng của HotSpot Metaspace không?** Không. Method area là cấu trúc trừu tượng của JVMS; Metaspace là cách HotSpot quản lý class metadata.

**2. Vì sao “method area logically part of heap” không mâu thuẫn với HotSpot `MemoryType.NON_HEAP`?** Vì một câu nói về **logic model**, câu còn lại nói về **implementation/management classification**.

**3. `Class<?>` mirror và `new Widget()` thường nằm ở đâu trên HotSpot hiện đại?** Là Java objects trên Java heap; class metadata riêng có thể ở Metaspace.

**4. Hai loaders định nghĩa cùng binary name có cùng runtime class không?** Không. Defining loader là một phần của runtime class identity.

**5. Gọi `URLClassLoader.close()` có trực tiếp xóa metadata của loaded classes không?** Không. Class unloading phụ thuộc JVM/GC và điều kiện của defining loader.

**6. `used` và `committed` có giống nhau không?** Không; committed có thể cao hơn used do allocator chunks, slack và trạng thái reclaim.

**7. `reserved` có bằng lượng RAM vật lý đã dùng không?** Không. Đây là không gian địa chỉ ảo dành trước.

**8. Có thể dùng `-Xmx` để giới hạn chính xác Metaspace không?** Không. `-Xmx` giới hạn Java heap, không phải HotSpot metadata memory.

**9. Tại sao JEP 387 có thể giúp ứng dụng reload plugins?** Elastic Metaspace cải thiện khả năng hoàn trả native memory không dùng sau class unloading, nhưng không thay được lifecycle cleanup.

**10. NMT có bao quát mọi malloc của native code bên thứ ba không?** Không. NMT chủ yếu theo dõi HotSpot VM internals và có giới hạn phạm vi.

**11. Nếu Metaspace tăng liên tục, tăng limit hay tìm references trước?** Xác định tình trạng trước: load thường xuyên hay loader generations không được thu hồi; tìm retaining paths và lifecycle root cause.

**12. Nếu không thấy class-unload log ngay sau `close` thì chắc chắn leak không?** Không. GC/class unloading không có cam kết thời gian cụ thể.

## 21. Tài liệu chính thức để đối chiếu

- **JVMS Java SE 17, `2.5.4` – Method Area**: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html#jvms-2.5.4
- **JLS Java SE 17, `12.7` – Unloading of Classes and Interfaces**: https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.7
- **Java SE 17 `MemoryPoolMXBean` / `MemoryUsage`**: https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/MemoryPoolMXBean.html và https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/MemoryUsage.html
- **Oracle Java SE 17, GC Tuning – Other Considerations, Metaspace**: https://docs.oracle.com/en/java/javase/17/gctuning/other-considerations.html
- **Oracle Java SE 17, Native Memory Tracking**: https://docs.oracle.com/en/java/javase/17/vm/native-memory-tracking.html
- **Oracle Java SE 17, `java` launcher options**: https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html
- **OpenJDK JEP 387 – Elastic Metaspace (JDK 16)**: https://openjdk.org/jeps/387
- **Java SE 17 `URLClassLoader`**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html

**Ghi nhớ:** **Method area là đặc tả logic; Metaspace là chi tiết HotSpot**. Một runtime class có metadata được quản lý gắn với defining loader; loader bị giữ sống có thể khiến metadata tiếp tục chiếm bộ nhớ. Muốn chẩn đoán chính xác hãy kết hợp **Metaspace pool, NMT, classloader stats, heap retaining paths và OS/container metrics**, luôn phân biệt **used, committed, reserved và RSS**. Việc `close` loader hoặc tăng giới hạn bộ nhớ không thể thay thế việc quản lý đúng vòng đời và references.
