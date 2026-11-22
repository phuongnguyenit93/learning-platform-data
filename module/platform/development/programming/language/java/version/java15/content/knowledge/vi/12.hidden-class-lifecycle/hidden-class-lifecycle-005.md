# Vòng đời hidden class: phân biệt Java heap và HotSpot Metaspace

> **Ngữ cảnh:** Java 15 chuẩn hóa hidden classes qua JEP 371 và `MethodHandles.Lookup.defineHiddenClass`. Chúng vẫn là API chính thức trên các JDK hiện đại. Bài này giải thích **dữ liệu nào nằm trên heap, dữ liệu nào thuộc Metaspace**, vì sao tạo nhiều hidden classes có thể làm tăng sử dụng bộ nhớ theo **hai cơ chế khác nhau**, và khi nào một hidden class có thể được JVM unload. **Metaspace là thuật ngữ/thiết kế của HotSpot**, còn Java Virtual Machine Specification không bắt buộc mọi JVM dùng đúng một vùng native memory có tên như vậy.

## 1. Trả lời ngắn: heap chứa object, Metaspace chứa class metadata

Một hidden class là một **class thực sự ở runtime**. Khi định nghĩa nó, JVM cần lưu **thông tin mô tả class**. Nếu tạo instance của hidden class, JVM còn phải cấp phát **các object**. Hai nhóm này thường thuộc hai vùng khác nhau trên **HotSpot**.

| Góc nhìn | Java heap | HotSpot Metaspace |
| --- | --- | --- |
| Mục đích | Chứa **Java objects và arrays** | Chứa **class metadata** do HotSpot quản lý |
| Ví dụ liên quan hidden class | Instance của hidden class; mảng là field của instance; `byte[]` chứa class-file bytes; `Class<?>` mirror trong HotSpot; object `Lookup`/`MethodHandle` | Cấu trúc metadata mô tả class, method, runtime constant pool và thông tin liên kết do VM quản lý |
| Kiểu cấp phát | Vùng bộ nhớ của Java object được garbage collector quản lý | Bộ nhớ **native/off-heap** do bộ cấp phát Metaspace của HotSpot quản lý |
| Tác nhân thu hồi | GC xác định object không còn reachable | **Class unloading** cho phép VM giải phóng/recycle metadata; GC và chính sách VM ảnh hưởng thời điểm |
| Giới hạn phổ biến | `-Xmx` (kích thước heap tối đa) | `-XX:MaxMetaspaceSize` (giới hạn Metaspace của HotSpot nếu được cấu hình) |
| Lỗi thường gặp | `OutOfMemoryError: Java heap space` | `OutOfMemoryError: Metaspace` hoặc lỗi liên quan vùng class metadata |
| Công cụ quan sát | Heap histogram/dump, `GC.heap_info`, JFR/JMX | `VM.metaspace`, `VM.classloader_stats`, NMT, class load/unload logs |
| Điều không suy ra được | Heap giảm không chứng minh class đã unload | Metaspace giảm không chứng minh toàn bộ object liên quan trên heap đã hết |

**Điểm quan trọng:** class metadata không phải là các instance của class. Một class chỉ định nghĩa **một lần** nhưng có thể tạo **nhiều triệu instance**. Ngược lại, một chương trình có thể sinh **rất nhiều class khác nhau** mà mỗi class chỉ có một instance hoặc không có instance nào. Hai kiểu tăng trưởng này tạo ra các mẫu tiêu thụ bộ nhớ khác nhau.

Không dùng công thức “một class = một object trên heap” hoặc “một instance = một phần Metaspace mới”. Class metadata và instance có vòng đời liên quan nhưng không đồng nhất.

## 2. Bốn thực thể khi gọi `defineHiddenClass`

Ví dụ ý tưởng:

~~~java
byte[] classFileBytes = ...; // class file đã biên dịch
MethodHandles.Lookup hiddenLookup =
        MethodHandles.lookup().defineHiddenClass(classFileBytes, false);
Class<?> hiddenType = hiddenLookup.lookupClass();
~~~

Đây là **đoạn mã minh họa**, không phải file tự chạy. Trong HotSpot hiện đại, nên nhận diện:

1. **`byte[] classFileBytes`:** một Java byte array trên **heap**. Nó là **đầu vào** cho API, không phải toàn bộ bộ nhớ runtime mà class sau đó dùng. Sau khi class đã được định nghĩa, giữ lại một bản sao `byte[]` lớn trong cache có thể tiếp tục tốn **heap** độc lập với class metadata.
2. **Metadata của hidden class:** VM tạo cấu trúc runtime cần để xác định methods, fields, interfaces, constant pool và quá trình liên kết. Trên HotSpot, phần metadata thuộc **Metaspace/native memory**; kích thước không phải chỉ bằng số byte của file `.class`.
3. **`Class<?> hiddenType`:** một **Java object** đại diện cho class ở runtime; trên HotSpot, Java mirror này là object trên **heap** và kết nối với metadata VM. Không được hiểu rằng vì `Class<?>` nằm trên heap nên toàn bộ metadata cũng nằm trên heap.
4. **`hiddenLookup`, method handle và instance:** các đối tượng Java mà chương trình giữ reference tới đều tiêu thụ **heap**; một số tài nguyên runtime bổ sung có thể nằm ở những vùng khác của VM. Chúng còn có thể **giữ hidden class sống** thông qua chuỗi reference.

Nếu tiếp tục:

~~~java
MethodHandle constructor =
        hiddenLookup.findConstructor(
                hiddenType, MethodType.methodType(void.class));
Object instance = constructor.invoke();
~~~

`instance` là Java object. Những field object của nó, chẳng hạn `byte[] payload`, cũng sống trên heap. Trong khi đó **metadata định nghĩa class của instance** vẫn thuộc vùng quản lý class metadata.

### Sơ đồ khái niệm

~~~text
Java HEAP                              HOTSPOT METASPACE / NATIVE
┌────────────────────────────────┐     ┌────────────────────────────┐
│ byte[] classFileBytes           │     │ metadata hidden class      │
│ Class<?> hiddenType ─────────────┼────>│ method/field descriptors   │
│ Lookup hiddenLookup             │     │ runtime constant pool...  │
│ MethodHandle constructor        │     └────────────────────────────┘
│ instance ──> byte[] payload      │
│ các object/cache khác           │     Vùng khác, ví dụ Code Cache:
└────────────────────────────────┘     │ mã máy do JIT biên dịch    │
                                       └────────────────────────────┘
~~~

Sơ đồ chỉ thể hiện **vai trò**, không phải bản đồ địa chỉ thực của JVM. Ví dụ **Code Cache** dành cho mã máy JIT trên HotSpot là một vùng khác, không nên gộp vô điều kiện vào heap hay class metadata Metaspace.

## 3. Tại sao cần phân biệt `Class<?>` với class metadata?

Java code nhìn thấy `Class<?>` qua `hiddenLookup.lookupClass()`, `object.getClass()` hoặc các API reflection. Từ đó dễ tưởng rằng chỉ có một object và GC sẽ tự thu hồi tất cả giống object khác.

Thực tế trên HotSpot:

- `Class<?>` là **đối tượng phản chiếu lớp** mà Java code có thể nắm giữ.
- JVM có metadata cấp VM để mô tả cấu trúc class, phục vụ verification/linking, dispatch và quản lý vòng đời.
- Một Java object `Class<?>` **còn reachable** có thể ngăn class tương ứng bị unload, dù Java application không còn instance nào.
- Một method handle, `Lookup`, call site hoặc cache khác có thể nắm giữ thông tin lớp theo cách **gián tiếp**, khiến class vẫn có lý do tiếp tục tồn tại.
- Ngay cả khi ứng dụng không còn nắm giữ trực tiếp `Class<?>`, một instance đang sống hoặc một chuỗi reference khác vẫn có thể khiến class cần được giữ.

Vì vậy, đừng chỉ hỏi “có bao nhiêu instance hidden class?” khi điều tra class metadata. Một cache chứa hàng nghìn `Class<?>`/`MethodHandle` có thể khiến nhiều class sống lâu dù không có object nghiệp vụ nào đang sử dụng.

**Không nhầm `String.getClass()` với việc lấy một bản sao metadata.** Những API này trả về class mirror/reference; không tạo thêm một class runtime mới.

## 4. Hidden class thông thường và named class khác nhau về unloading

### 4.1. Named class: gắn chặt hơn với defining class loader

Một named class được định nghĩa qua class loader thông thường có quan hệ vòng đời mạnh với **defining loader**. Theo mô hình class unloading, nó chỉ có thể được unload khi loader định nghĩa có thể trở nên reclaimable, cùng các điều kiện liên quan. Với **application class loader** tồn tại gần như suốt phiên chạy, nhiều named classes được giữ lâu dài.

Điều này không có nghĩa Java không bao giờ unload named class: một hệ thống plugin dùng các **class loaders có vòng đời ngắn** có thể unload một tập class cùng loader khi không còn reference ngăn việc thu hồi.

### 4.2. Hidden class mặc định: có thể unload dù loader còn sống

Theo Javadoc của `Lookup.defineHiddenClass`, **mặc định** một hidden class có thể được unload **ngay cả khi class loader được đánh dấu là defining loader vẫn còn reachable**.

Đây là lý do hidden class hữu ích trong runtime tạo **rất nhiều class có thời gian sử dụng ngắn**, chẳng hạn một số chiến lược code generation. VM có thể giải phóng metadata của các hidden classes không còn cần tới mà không bắt buộc chờ dỡ bỏ toàn bộ loader.

**Nhưng “có thể unload” không phải “sẽ unload ngay”:**

- Nếu vẫn có instance, `Class<?>` mirror, `Lookup`, method handle hoặc reference giữ class sống, class chưa đủ điều kiện thu hồi.
- Sau khi mất references liên quan, VM/GC **vẫn quyết định khi nào** tiến hành unloading.
- Không có bảo đảm rằng lời gọi `System.gc()` sẽ lập tức unload class.
- Mất reference tới biến `Class<?>` trong **một phương thức** chưa chứng minh mọi cache, call site hoặc tài nguyên nội bộ khác đã thả class.

### 4.3. `ClassOption.STRONG`: vòng đời giống quan hệ của named class với loader

Cách tạo:

~~~java
MethodHandles.Lookup hiddenLookup =
        MethodHandles.lookup().defineHiddenClass(
                classFileBytes,
                false,
                MethodHandles.Lookup.ClassOption.STRONG
        );
~~~

`STRONG` được mô tả trong `MethodHandles.Lookup.ClassOption`: hidden class có **quan hệ mạnh** với defining class loader, giống class thường. Nó chỉ có thể được unload khi defining loader không còn reachable và có thể được GC reclaim.

Hệ quả quan trọng:

- Dùng `STRONG` với một loader sống lâu có thể khiến metadata của các hidden classes **tồn tại lâu hơn**.
- Nếu sinh hàng chục nghìn hidden classes với `STRONG` trong một loader sống suốt tiến trình, áp lực lên Metaspace có thể giống tạo rất nhiều named classes.
- Bỏ option `STRONG` **không** có nghĩa class sẽ biến mất ngay khi một instance chết. Điều kiện reachability và chính sách GC vẫn áp dụng.
- Quan hệ unloading được xác lập **lúc định nghĩa class**, không phải cờ có thể đổi sau khi tạo.

### 4.4. `NESTMATE` không phải cờ quản lý bộ nhớ

Một option khác là `ClassOption.NESTMATE`, dùng để đưa hidden class vào quan hệ **nestmate/private access** phù hợp. Nó **không phải** `STRONG`, không tự đảm bảo unload nhanh hơn hoặc chậm hơn.

Các option có thể phối hợp khi API cho phép:

~~~java
lookup.defineHiddenClass(
        bytes,
        false,
        MethodHandles.Lookup.ClassOption.NESTMATE,
        MethodHandles.Lookup.ClassOption.STRONG
);
~~~

Đây là **mảnh mã minh họa** bên trong phương thức; người đọc cần hiểu mỗi option có nhiệm vụ khác nhau: quyền truy cập theo nest và quan hệ vòng đời với loader.

## 5. Một bảng các trường hợp cần suy luận đúng

| Trường hợp | Heap | Metaspace / class unloading |
| --- | --- | --- |
| Giữ `byte[]` của 10.000 class files trong cache | Heap có thể tăng mạnh vì giữ nhiều arrays | **Chưa đủ bằng chứng** Metaspace tăng: các bytes có thể chưa từng được định nghĩa thành class |
| Tạo một hidden class rồi tạo nhiều instance có `byte[] payload` lớn | Heap tăng theo instance/payload | Metadata của một class không tăng theo số instance một cách tuyến tính |
| Gọi `defineHiddenClass` hàng nghìn lần với cùng class-file bytes | Có `Class<?>` mirrors và object runtime liên quan | Mỗi lần tạo **một class runtime mới**, metadata có thể tăng |
| Giữ `Class<?>` của mỗi hidden class trong `List` mạnh | Heap giữ list và class mirrors | Các class được giữ reachable; khả năng unload bị hạn chế |
| Giữ mọi `MethodHandle` được trả về trong static cache | Heap giữ handles/cache | Handles có thể giữ class/target metadata sống |
| Bỏ tất cả references đến hidden class mặc định | Object không còn reachable có thể được GC thu hồi | Class **có thể** unload ngay cả khi loader còn reachable; không có deadline |
| Dùng `STRONG` với loader dài hạn | Heap có thể ít object nghiệp vụ | Metaspace có thể vẫn giữ metadata cho đến khi loader có thể thu hồi |
| Gỡ một plugin và để class loader không còn reachable | Các Java objects liên quan có thể được GC thu hồi | Named/strong hidden classes của loader có thể unload; phụ thuộc references và GC |
| `-Xmx` tăng lên nhưng lỗi `Metaspace` vẫn xảy ra | Heap được phép lớn hơn | Không trực tiếp tăng hạn mức metadata native Metaspace |
| `-XX:MaxMetaspaceSize` tăng nhưng Java heap đang đầy | Metaspace được phép lớn hơn | Không xử lý object leak trên heap |

Hai câu cần nhớ: **heap pressure** và **metadata pressure** có thể xuất hiện đồng thời nhưng không phải một hiện tượng; **class unloading** có quan hệ với GC nhưng không đồng nghĩa với thu hồi một instance thông thường.

## 6. Ví dụ Java 17+ chạy được: class metadata và instance là hai thực thể

Ví dụ dùng **hai file** trong cùng thư mục và package mặc định. Nó tạo cùng lúc hai hidden classes từ cùng bytes, một bản mặc định và một bản có `STRONG`, rồi tạo một instance có mảng payload trên heap.

### File `TaskTemplate.java`

~~~java
public class TaskTemplate implements Runnable {
    private final byte[] payload = new byte[32];

    public TaskTemplate() {
    }

    @Override
    public void run() {
        System.out.println("payload bytes: " + payload.length);
    }
}
~~~

Class này là **named template** để `javac` tạo `TaskTemplate.class`. Mục tiêu của chương trình sau không phải là biến named class thành hidden class; mỗi lời gọi `defineHiddenClass` tạo **một class runtime mới** từ bytes của template.

### File `HiddenMemoryDemo.java`

~~~java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.nio.file.Files;
import java.nio.file.Path;

public class HiddenMemoryDemo {
    public static void main(String[] args) throws Throwable {
        byte[] bytes = Files.readAllBytes(
                Path.of("TaskTemplate.class"));

        MethodHandles.Lookup host = MethodHandles.lookup();

        MethodHandles.Lookup ordinaryHidden =
                host.defineHiddenClass(bytes, false);

        MethodHandles.Lookup strongHidden =
                host.defineHiddenClass(
                        bytes, false,
                        MethodHandles.Lookup.ClassOption.STRONG);

        Class<?> ordinaryType = ordinaryHidden.lookupClass();
        Class<?> strongType = strongHidden.lookupClass();

        System.out.println(
                "ordinary hidden: " + ordinaryType.isHidden());
        System.out.println(
                "STRONG hidden: " + strongType.isHidden());
        System.out.println(
                "different runtime classes: "
                        + (ordinaryType != strongType));

        MethodHandle constructor =
                ordinaryHidden.findConstructor(
                        ordinaryType,
                        MethodType.methodType(void.class));

        Runnable task = (Runnable) constructor.invoke();

        System.out.println(
                "instance hidden: " + task.getClass().isHidden());
        System.out.println(
                "named template hidden: "
                        + TaskTemplate.class.isHidden());
        System.out.println(
                "instance is Runnable: "
                        + (task instanceof Runnable));

        task.run();
    }
}
~~~

Cả `TaskTemplate` và `HiddenMemoryDemo` thuộc unnamed package, đáp ứng yêu cầu same package và full privilege của `defineHiddenClass` trong ví dụ.

Biên dịch/chạy bằng JDK 17+:

~~~bash
javac TaskTemplate.java HiddenMemoryDemo.java
java HiddenMemoryDemo
~~~

**Stdout chính xác:**

~~~text
ordinary hidden: true
STRONG hidden: true
different runtime classes: true
instance hidden: true
named template hidden: false
instance is Runnable: true
payload bytes: 32
~~~

Giải thích từng điểm:

1. Cả hai class do `defineHiddenClass` tạo đều là hidden: **`isHidden() == true`**.
2. Hai lời gọi `defineHiddenClass` cùng bytes tạo **hai class runtime riêng**; không phải hai tên khác nhau của cùng class.
3. `task` là một instance của hidden class mặc định. Instance và mảng `payload` trong đó là **Java objects trên heap**.
4. Metadata để VM thực thi instance thuộc về hidden class đã được định nghĩa; trên HotSpot, đó là vùng class metadata ở **Metaspace**, không phải `payload`.
5. `TaskTemplate.class` trỏ đến **named class** được biên dịch và tìm theo classpath; nó khác hai bản hidden đã tạo.
6. Bản `STRONG` vẫn là **hidden class**. Option ảnh hưởng quan hệ **unloading**, không thay đổi kết quả của `Class.isHidden()` và không làm nó trở thành named class.

**Tính quyết định của demo:** chương trình không giả định GC sẽ xảy ra và **không đo thời gian unload**. Không in các địa chỉ bộ nhớ, kích thước Metaspace hoặc tên hidden class có hậu tố runtime không ổn định, nên stdout trên là kết quả ổn định khi điều kiện chạy được đáp ứng.

Để kiểm tra khả năng biên dịch với Java 15 trên compiler hỗ trợ target:

~~~bash
javac --release 15 TaskTemplate.java HiddenMemoryDemo.java
~~~

Không dùng `--enable-preview`. API hidden class đã chính thức có từ Java 15.

## 7. Vì sao không dùng `System.gc()` để chứng minh metadata đã giải phóng?

Một phép thử thường thấy:

~~~java
// Mảnh minh họa, KHÔNG phải test unloading đáng tin:
hiddenType = null;
System.gc();
System.out.println("unloaded");
~~~

Đoạn trên **không chứng minh** hidden class đã unload:

- Gán một biến cục bộ thành `null` không loại mọi reference khác như `Lookup`, instance, method handle, static cache và call site.
- `System.gc()` chỉ là **yêu cầu/gợi ý**; JVM không cam kết chạy GC hay class unloading ngay lập tức.
- Compiler JIT, liveness của biến cục bộ và điểm safepoint ảnh hưởng việc giữ/chấm dứt references trong test.
- Metaspace **used**, **committed** và **reserved** là ba đại lượng khác nhau; sau unloading, bộ nhớ có thể được VM giữ lại để tái sử dụng thay vì trả ngay cho hệ điều hành.
- Một phép đo snapshot đơn lẻ không đủ kết luận class leak. Cần theo dõi **xu hướng qua nhiều chu kỳ hoạt động/GC**.

Nếu muốn kiểm tra weak reachability bằng `WeakReference<Class<?>>`, hãy coi đó là **thí nghiệm GC không quyết định**, không phải assertion bắt buộc phải pass sau thời hạn cố định. Thậm chí khi weak reference được xóa, hãy dùng dữ liệu class-unloading/Metaspace phù hợp để đánh giá vòng đời metadata, không đánh đồng hai sự kiện ở cùng một thời điểm tuyệt đối.

## 8. Metaspace trên HotSpot: used, committed, reserved

Phân biệt ba thông số trước khi đưa ra kết luận:

| Chỉ số | Ý nghĩa khái quát | Cách đọc đúng |
| --- | --- | --- |
| **Used** | Phần bộ nhớ VM thực sự dùng cho metadata theo thước đo công cụ | Có thể thấp hơn committed; không đồng nghĩa với RSS toàn process |
| **Committed** | Trang bộ nhớ native mà VM đã commit để sử dụng trong vùng đó | Có thể vẫn lớn sau unloading do chính sách quản lý/reuse |
| **Reserved** | Khoảng không gian địa chỉ ảo VM giữ để có thể cấp phát khi cần | Không đồng nghĩa đã dùng từng đó RAM vật lý |

Với compressed class pointers trên một số cấu hình HotSpot 64-bit, báo cáo có thể tách **class space** khỏi phần **Metaspace** còn lại. Không kết luận reserved lớn tức là đang tiêu thụ cùng lượng RAM; phân biệt reserved với committed.

Trong một JDK hiện đại, câu chuyện thực tế thường là:

~~~text
Định nghĩa nhiều class -> metadata allocated trong Metaspace
        |
        v
Classes còn sống? ---- Có ----> metadata vẫn cần thiết
        |
       Không
        v
GC/class unloading có thể thu hồi metadata
        |
        v
HotSpot có thể tái sử dụng hoặc trả bớt committed memory cho OS
        (mức độ tùy bản JDK, collector và reclaim policy)
~~~

**JEP 387 — Elastic Metaspace** được đưa vào **Java 16**, sau Java 15. Những JDK hiện đại kế thừa cơ chế quản lý Metaspace cải tiến, giúp trả lại bộ nhớ không còn dùng hiệu quả hơn trong những tình huống phù hợp. Đừng gán JEP 387 cho Java 15; cũng đừng khẳng định mọi lần class unloading làm committed/RSS giảm tức thì.

## 9. Chẩn đoán lỗi bộ nhớ: heap và metaspace cần công cụ khác nhau

### 9.1. Hai triệu chứng phổ biến

**Trường hợp A — `OutOfMemoryError: Java heap space`**

Cần xem object/array đang chiếm heap:

- Mảng payload của instance, cache dữ liệu, collection và buffer giữ lại lâu.
- Nhiều bản `byte[]` class-file bytes được giữ trong `List`/`Map`.
- `Class<?>` mirrors, lookup/method-handle objects và object khác vẫn reachable.
- Có thể cần heap dump, heap histogram, allocation profiling và xem đường giữ reference (retaining path).

**Trường hợp B — `OutOfMemoryError: Metaspace`**

Cần xem vì sao **class metadata** không ngừng tăng:

- Framework tạo hàng loạt hidden classes mới thay vì tái sử dụng.
- Tạo `STRONG` hidden classes với defining loader sống quá lâu.
- Cache giữ `Class<?>`/`Lookup`/`MethodHandle` khiến hidden classes mặc định vẫn reachable.
- Nhiều class loaders hoặc plugin loaders không thể được thu hồi do threads, static caches hoặc callback.
- VM bị giới hạn `-XX:MaxMetaspaceSize` quá thấp so với workload hợp lệ.

Không mặc định kết luận `Metaspace` báo lỗi là “memory leak”: cũng có thể là lượng class hợp lệ lớn hoặc giới hạn không phù hợp. Cần xác định **số class, loader, lifecycle, used/committed và xu hướng**.

### 9.2. Các cờ có ý nghĩa khác nhau

| Cờ / công cụ | Tác động / vai trò | Đừng hiểu sai |
| --- | --- | --- |
| `-Xmx256m` | Giới hạn tối đa Java heap là 256 MiB | Không cấp một giới hạn tương ứng cho Metaspace |
| `-Xms64m` | Thiết lập kích thước heap ban đầu | Không nói Metaspace có 64 MiB |
| `-XX:MaxMetaspaceSize=256m` | Đặt trần Metaspace trên HotSpot | Không tự sửa class leak hoặc heap leak |
| `-XX:MetaspaceSize=...` | Ngưỡng ban đầu liên quan triggering GC do áp lực metadata trên HotSpot | Không phải “kích thước tối đa của Metaspace” |
| `-XX:NativeMemoryTracking=summary` | Bật NMT để theo dõi các hạng mục native memory của HotSpot | NMT không phải heap profiler hay công cụ phân tích mọi thư viện native |
| `-Xlog:class+load=info,class+unload=info` | Quan sát sự kiện class load/unload trên HotSpot phù hợp | Log không chứng minh object heap đã được thu hồi |

**Không khắc phục sai mục tiêu:** tăng `-Xmx` để giải quyết lớp sinh động giữ metadata có thể không có tác dụng; tăng `MaxMetaspaceSize` để xử lý những mảng object khổng lồ trên heap cũng không phù hợp. Có thể cần điều chỉnh cả hai sau khi phân tích thật, nhưng tuning không thay thế sửa lifecycle/reference retention.

## 10. Công cụ JDK kiểm tra thực tế

Các lệnh sau áp dụng cho **tiến trình HotSpot/JDK đang chạy đủ lâu** để gắn công cụ. Demo ở phần 6 kết thúc rất nhanh, nên muốn quan sát, hãy dùng một ứng dụng thử dài hạn hoặc server thực tế có quyền truy cập.

### 10.1. `jcmd`: xem danh sách tiến trình và số liệu

~~~bash
jcmd -l
~~~

Sau khi biết process id (ví dụ minh họa `12345`), gọi:

~~~bash
jcmd 12345 GC.heap_info
jcmd 12345 VM.metaspace
jcmd 12345 VM.classloader_stats
jcmd 12345 GC.class_histogram
~~~

Vai trò của các lệnh:

- `GC.heap_info`: thông tin Java heap do collector cung cấp; các bản JDK có thể thay đổi format.
- `VM.metaspace`: thông tin Metaspace và class-space của HotSpot (nếu phiên bản hỗ trợ), giúp phân biệt used/committed/reserved và mức dùng theo loader/chunk tùy option.
- `VM.classloader_stats`: số liệu liên quan loader và class; hữu ích để phát hiện class-loader retention.
- `GC.class_histogram`: histogram các **Java objects trên heap**; lệnh này có thể có overhead đáng kể và không thay thế số liệu metadata.

Không dựa vào một format output cố định qua mọi JDK. Kiểm tra lệnh hỗ trợ thực tế:

~~~bash
jcmd 12345 help
jcmd 12345 help VM.metaspace
~~~

Nếu không thấy `VM.metaspace`, xem vendor/JDK và công cụ sẵn có; API/diagnostic commands là chi tiết triển khai.

### 10.2. Native Memory Tracking (NMT)

Khởi động ứng dụng **có chủ đích** với:

~~~bash
java -XX:NativeMemoryTracking=summary -Xmx256m YourMainClass
~~~

`YourMainClass` ở đây đại diện cho lớp khởi động thật của ứng dụng cần quan sát, không phải class JDK. Sau đó:

~~~bash
jcmd 12345 VM.native_memory summary
jcmd 12345 VM.native_memory baseline
jcmd 12345 VM.native_memory summary.diff
~~~

NMT cho phép quan sát hạng mục native memory như Class/Metaspace và theo dõi biến động. **Phải bật lúc khởi động JVM** để có thống kê theo cách này; baseline/diff chỉ có ý nghĩa khi đã có khoảng đo và workload rõ ràng. NMT có chi phí quan sát; nên dùng phù hợp môi trường test hoặc điều tra được phép.

Một số phiên bản HotSpot báo Metaspace riêng trong `VM.metaspace`, và cách đặt tên mục Class/Metaspace ở NMT có thể khác. Đừng lấy `VM.native_memory` làm một phép cộng trực tiếp “heap + metaspace = toàn bộ RAM process”: còn thread stacks, code cache, GC, JNI và nhiều native allocations khác.

### 10.3. Log sự kiện class loading và unloading

Có thể dùng unified logging của HotSpot:

~~~bash
java -Xlog:class+load=info,class+unload=info YourMainClass
~~~

Log này phục vụ theo dõi **sự kiện** class được định nghĩa/unload. Với workload sinh class liên tục, output có thể rất lớn và tốn chi phí; chỉ bật ở môi trường và mức log phù hợp.

Nếu không có dòng unload trong một lần chạy ngắn, **không kết luận** JVM không hỗ trợ hidden-class unloading. GC có thể chưa quyết định unload hoặc class vẫn reachable.

### 10.4. JMX/MemoryPoolMXBean

Java SE cho phép truy vấn memory pools qua `ManagementFactory.getMemoryPoolMXBeans()`. Trong HotSpot, thường có pool tên **`Metaspace`** và một pool class-space tùy cấu hình.

~~~java
// Đoạn minh họa bên trong một phương thức:
for (java.lang.management.MemoryPoolMXBean pool
        : java.lang.management.ManagementFactory
                .getMemoryPoolMXBeans()) {
    if ("Metaspace".equals(pool.getName())) {
        System.out.println(pool.getUsage());
    }
}
~~~

Output là **số đo thời điểm chạy**, không cố định. Không bắt buộc mọi JVM hoặc mọi phiên bản phải có pool đúng tên này. Một pool có `MemoryType.NON_HEAP` **không** đồng nghĩa tất cả non-heap memory đều thuộc Metaspace; code cache cũng là một vùng khác.

## 11. Chẩn đoán hai lỗi dễ nhầm bằng tình huống

### Tình huống A — tăng instance, không tăng số class

Một service tạo một hidden class `PayloadTask` duy nhất, rồi tạo một triệu instance, mỗi instance sở hữu một `byte[1024]`.

**Dự kiến phân tích:** phần lớn áp lực bộ nhớ mới liên quan đến **Java heap** vì mảng payload được cấp phát cho từng object. Metadata của một class không nhân lên một triệu lần. Nếu các instances không còn reachable, GC có thể thu hồi object heap mà class vẫn tồn tại (ví dụ cache giữ `Class<?>`).

**Điều cần sửa:** kiểm tra số instances đang sống, payload size, cache, vòng đời request và sự cần thiết của mỗi buffer.

### Tình huống B — tăng số hidden class, ít instance

Một engine liên tục gọi `defineHiddenClass` cho mỗi request với cùng bytes, chỉ tạo một instance rất nhỏ, nhưng cất tất cả `Lookup` vào `static Map`.

**Dự kiến phân tích:** Metaspace có thể tăng vì **mỗi lần định nghĩa sinh một class runtime mới**; heap cũng tăng do lookup objects và cache. Hidden classes mặc định có thể đủ điều kiện unload sớm hơn named class, **nhưng cache mạnh** đang ngăn điều đó.

**Điều cần sửa:** kiểm tra có thể **tái sử dụng class/handle** thay vì định nghĩa lại, thu gọn cache khi kết thúc vòng đời, không giữ references quá lâu.

### Tình huống C — dùng `STRONG` với class loader sống suốt tiến trình

Engine sinh hàng nghìn STRONG hidden classes bằng application loader.

**Dự kiến phân tích:** dù có xóa các references Java tạm thời, quan hệ mạnh với loader khiến những classes này chỉ có thể unload khi loader không còn reachable; application loader thường tồn tại lâu, nên metadata có thể tích lũy.

**Điều cần sửa:** cân nhắc hidden class mặc định nếu semantics cho phép, quản lý class-loader lifecycle hoặc giới hạn số class được sinh, thay vì mặc định dùng `STRONG`.

### Tình huống D — heap đã ổn nhưng RSS vẫn cao

Sau một đợt GC, heap used giảm rõ rệt, nhưng **process RSS** không giảm tương ứng.

**Giải thích có thể:** Metaspace, compressed class space, code cache, stacks và các vùng native khác vẫn đang committed hoặc được OS/VM giữ để tái sử dụng. Ngoài ra, ngay cả heap committed cũng có thể chưa trả lại OS. Cần dữ liệu từ các công cụ tương ứng mới biết nguyên nhân.

**Điều không nên làm:** khẳng định bộ nhớ đã rò rỉ chỉ vì RSS khác heap used, hoặc coi việc tăng `-Xmx` là câu trả lời mặc định.

## 12. Những sai lầm thường gặp

| Nhầm lẫn | Vì sao không đúng | Cách nghĩ đúng |
| --- | --- | --- |
| “Hidden class nằm hoàn toàn trong Metaspace” | Instance, `Class<?>` mirror và nhiều objects liên quan nằm trên heap | Phân biệt **runtime metadata** với **Java objects** |
| “`Class<?>` nằm trên heap thì metadata cũng nằm trên heap” | Heap mirror tham chiếu cấu trúc metadata native của HotSpot | Hai loại lưu trữ khác nhau có thể liên kết qua references |
| “Tạo thêm 1.000 instance nghĩa là có 1.000 class definitions” | Instance dùng chung class runtime | Đếm class definitions và instance riêng |
| “Giữ `byte[]` class file là giữ Metaspace” | Byte array trên heap; có thể chưa từng định nghĩa class | Xác định bytes, metadata, runtime handles riêng |
| “Bỏ tham chiếu cuối cùng và gọi `System.gc()` chắc chắn unload” | GC/unloading không có bảo đảm tức thời | Theo dõi xu hướng và reachability thật |
| “Hidden class mặc định luôn unload trước named class” | Không bảo đảm thứ tự hay thời điểm GC | Chỉ nói **có thể unload độc lập loader** |
| “`STRONG` không liên quan bộ nhớ” | Nó thay đổi điều kiện unloading với defining loader | Đánh giá vòng đời loader trước khi chọn STRONG |
| “`NESTMATE` khiến lớp bất tử” | NESTMATE nói về access/nest, không định nghĩa quan hệ STRONG | Không nhầm mục đích options |
| “`-Xmx` là trần tổng RAM JVM” | JVM còn native memory ngoài heap | Phân tích Metaspace và các vùng native khác |
| “`-XX:MetaspaceSize` là giới hạn cứng Metaspace” | Đây là ngưỡng quản lý GC/metaspace, không phải max size | Dùng `MaxMetaspaceSize` nếu cần trần và có phân tích |
| “Metaspace reserved 1 GiB là đã chiếm 1 GiB RAM” | Reserved là **virtual address space** | Nhìn used và committed trước |
| “Heap dump không thấy nhiều class metadata thì không có class leak” | Heap dump tập trung vào Java objects | Kết hợp `VM.metaspace`, class-loader stats, JFR/NMT |
| “`OutOfMemoryError: Metaspace` bắt buộc do leak” | Có thể do workload hợp lệ hoặc limit quá thấp | Phân tích trends, cache, class lifecycle và sizing |
| “Không có log unload là VM không unload hidden class” | Có thể class vẫn reachable hoặc chưa có GC phù hợp | Tạo thí nghiệm dài hạn và đối chiếu nhiều chỉ số |

## 13. Bài tập tự kiểm tra

**Bài 1.** Một hidden class có 2.000 instance; mỗi instance giữ mảng `byte[4096]`. Những bytes của các mảng nằm trên heap hay Metaspace?

**Đáp án:** **heap**, vì `byte[]` là Java array object. Metadata mô tả hidden class thuộc Metaspace trên HotSpot; số mảng không nhân số class metadata.

**Bài 2.** Một framework định nghĩa 10.000 hidden classes cùng từ bytes của một template. Nó chỉ có một named class `Template` thôi phải không?

**Đáp án:** **Không**. Mỗi lần `defineHiddenClass` thành công tạo một **class runtime mới**. Dù dùng cùng đầu vào bytes, số định nghĩa class/metadata có thể tăng theo số lần gọi.

**Bài 3.** Default hidden class và STRONG hidden class đều có `isHidden()==true`. Vậy khác biệt là gì?

**Đáp án:** chúng đều hidden về mặt tên/runtime identity; **mặc định** có thể unload dù defining loader còn reachable, còn **STRONG** có quan hệ mạnh với loader và chỉ có thể unload khi loader có thể được reclaim. Không khác nhau ở việc `isHidden`.

**Bài 4.** `System.gc()` đã được gọi nhưng Metaspace committed chưa giảm. Có kết luận chắc class không unload được không?

**Đáp án:** **Không**. GC không được bảo đảm tức thì; class có thể còn reachable; Metaspace chunks có thể được VM giữ để tái dùng. Cần theo dõi số class, used/committed, GC/unload events và references.

**Bài 5.** Tại sao heap dump có thể hữu ích trong sự cố Metaspace?

**Đáp án:** heap dump có thể giúp tìm **Java-side retainers** như cache giữ `Class<?>`, `Lookup`, method handles hoặc class loaders, dù phần metadata bị giữ nằm ở vùng native Metaspace. Heap dump và Metaspace stats cung cấp **hai góc nhìn bổ sung**.

**Bài 6.** Có nên dùng `-XX:MaxMetaspaceSize` thay `-Xmx` để sửa lỗi `OutOfMemoryError: Java heap space`?

**Đáp án:** **Không**. `MaxMetaspaceSize` không phải heap limit. Hãy xác định loại OOME rồi kiểm tra vùng, số liệu và lifecycle tương ứng.

**Bài 7.** Đối với named class với loader dài hạn, có thể làm nó unload đơn lẻ chỉ bằng cách đặt biến `Class<?>` thành `null` không?

**Đáp án:** Không nên kỳ vọng. Named class có quan hệ class unloading với defining loader; nếu loader còn reachable, named class thường không thể unload độc lập như default hidden class.

**Bài 8.** Một `MethodHandle` được giữ trong cache dài hạn tham chiếu member của hidden class mặc định. Class đó có chắc sẽ unload khi không còn instance không?

**Đáp án:** **Không**. Method handle/reference có thể giữ class sống; cần phân tích toàn bộ graph of references, không chỉ đếm instances.

## 14. Checklist triển khai và vận hành

Trước khi dùng hidden class để giảm áp lực bộ nhớ, xác nhận:

1. **Mục tiêu rõ:** ứng dụng cần tạo class runtime động vì lý do kiến trúc, không chỉ thay thế một class Java thông thường.
2. **Đo hai vùng:** theo dõi heap và Metaspace riêng, và phân biệt used/committed/reserved trên HotSpot.
3. **Đếm số class được tạo:** một class cho mỗi request có thực sự cần hay có thể tái sử dụng?
4. **Không cache vô hạn:** rà soát `Class<?>`, `Lookup`, `MethodHandle`, `CallSite`, instance và class-loader references.
5. **Chọn `STRONG` có chủ đích:** chỉ khi muốn vòng đời class gắn với loader. Đừng dùng chỉ vì nghe “mạnh hơn thì tốt hơn”.
6. **Không đánh đồng `NESTMATE`:** nó giải quyết access control, không phải GC policy.
7. **Kiểm tra collector và workload:** class unloading tùy hoạt động GC, options và điều kiện reachability.
8. **Thu thập số liệu trước/sau cùng một workload:** class counts, loader counts, Metaspace used/committed, heap histogram và GC logs.
9. **Đặt giới hạn bộ nhớ có căn cứ:** `-Xmx`/`MaxMetaspaceSize`, hạn container và tổng process native memory phải được đánh giá riêng.
10. **Đừng kết luận từ một snapshot:** đánh giá xu hướng qua vòng lặp tạo/xóa class, cũng như khả năng khôi phục bộ nhớ qua thời gian.
11. **Thử trên JDK mục tiêu:** tên công cụ, format output và chính sách HotSpot có thể thay đổi; chọn JDK đang được bảo trì.
12. **Ưu tiên sửa giữ reference sai:** tăng memory limit có thể chỉ trì hoãn vấn đề nếu framework vẫn giữ mọi class/handle mãi mãi.

## 15. Tài liệu chuẩn còn áp dụng

- **JEP 371 — Hidden Classes (giới thiệu Java 15):** https://openjdk.org/jeps/371
- **Java SE 17 — `Lookup.defineHiddenClass` (mặc định/`STRONG`, class unloading):** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html#defineHiddenClass(byte%5B%5D,boolean,java.lang.invoke.MethodHandles.Lookup.ClassOption...)
- **Java SE 17 — `MethodHandles.Lookup.ClassOption`:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.ClassOption.html
- **JEP 387 — Elastic Metaspace (Java 16, cải tiến còn áp dụng trên JDK hiện đại):** https://openjdk.org/jeps/387
- **Oracle — Java HotSpot GC Tuning, Class Metadata:** https://docs.oracle.com/en/java/javase/25/gctuning/other-considerations.html
- **Oracle — `jcmd` (VM.metaspace, VM.classloader_stats, VM.native_memory):** https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html
- **Oracle — Troubleshooting, Native Memory Tracking:** https://docs.oracle.com/en/java/javase/17/troubleshoot/diagnostic-tools.html

**Tóm lại:** trong HotSpot, **heap** chủ yếu chứa Java objects như instances, arrays, `Class<?>` mirrors và method handles, còn **Metaspace** chứa **class metadata**. Hidden class mặc định có thể unload **độc lập defining loader** khi không còn live references thích hợp; `STRONG` buộc quan hệ vòng đời giống named class với loader. Khi điều tra sự cố, phải đo **đúng vùng bộ nhớ** và tìm **tham chiếu giữ class sống**, thay vì nhìn mỗi `-Xmx` hoặc chỉ đếm instances.
