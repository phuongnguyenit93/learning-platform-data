# JNI_OnUnload, class loader unloading và những việc cần tránh khi dỡ thư viện native

Trong JNI, câu hỏi “khi nào một thư viện native được dỡ?” không thể trả lời chỉ bằng thời điểm Java thoát khỏi `main` hoặc một object hết được dùng. **`JNI_OnUnload` là hook tùy chọn mà JVM gọi khi class loader sở hữu native library được garbage-collected**, không phải callback bảo đảm chạy sau mỗi `System.loadLibrary`, khi gọi `close()`, hay ngay lúc tiến trình kết thúc. Hook được gọi trong **ngữ cảnh không xác định**; đặc tả JNI khuyên hạn chế sử dụng dịch vụ JVM và **tránh callback Java tùy ý**.

Trong module **Vòng đời JNI**, bài này phân biệt ba vòng đời thường bị đánh đồng: vòng đời tài nguyên của một đối tượng Java/native handle, vòng đời định nghĩa lớp và `ClassLoader`, và vòng đời một thư viện native đã nạp. Ta đi từ hợp đồng `JNI_OnLoad/JNI_OnUnload` đến vấn đề class loader bị giữ sống bởi global references, điểm nguy hiểm trong hook dỡ thư viện, rồi xây dựng ví dụ Java 17 + C11 có **dọn tài nguyên tường minh** và hook unload tối giản. Mục tiêu quan trọng nhất: **ứng dụng đúng ngay cả khi `JNI_OnUnload` không bao giờ được gọi**.

## 1. Sơ đồ vòng đời: ba mốc độc lập

~~~text
Java ClassLoader L bắt đầu dùng thư viện JNI
      |
      | System.loadLibrary("lifecycle")
      v
JVM/OS nạp liblifecycle.so / liblifecycle.dylib / lifecycle.dll
      |
      | Nếu thư viện export hook và JVM chấp nhận version:
      +----> JNI_OnLoad(JavaVM *, void *)          [khi LOAD]
      |
      v
Java gọi các hàm native / tạo native resources
      |
      +----> nativeOpen(): cấp phát C memory
      |      nativeUse():  dùng C memory
      |      nativeClose(): giải phóng C memory    [DO ỨNG DỤNG CHỦ ĐỘNG]
      |
      +----> Có thể còn object/threads/global refs giữ L sống
      |
      v
Không còn strong reachability tới loader L và các class liên quan
      |
      | Nếu GC thực sự xác định loader có thể bị thu hồi
      | và JVM thực hiện unloading của thư viện tương ứng
      v
JNI_OnUnload(JavaVM *, void *)                 [LÚC UNLOAD; KHÔNG BẢO ĐẢM TIMING]
      |
      v
JVM/OS xử lý dỡ native library theo runtime/platform
~~~

Các giai đoạn không đồng nghĩa:

| Sự kiện | Ai quyết định? | Có bảo đảm chạy `JNI_OnUnload` ngay? |
| --- | --- | --- |
| `new Resource()` tạo native handle | Ứng dụng và hàm JNI | Không |
| `Resource.close()` giải phóng handle | Ứng dụng | Không |
| Java method kết thúc, object ra khỏi scope | Java program / khả năng GC | Không |
| `System.gc()` được gọi | Chỉ là yêu cầu gợi ý GC | Không |
| Class không còn được tham chiếu nhưng loader còn sống | Reachability / VM | Không |
| Class loader sở hữu library thực sự bị garbage collected | GC và quản lý loader/library của VM | Hook có thể được VM gọi trong tiến trình unload |
| JVM shutdown / `main` return | JVM/runtime/OS | Không được coi là cam kết chạy hook |
| `JNI_OnUnload` bắt đầu chạy | JVM | Không được giả định môi trường giống lời gọi JNI thông thường |

**Quy tắc thiết kế:** Tài nguyên như file descriptor, socket, native heap, thread pool, buffer lớn, callback registration hay GPU handle có chủ sở hữu Java phải được giải phóng bằng API đóng/destroy xác định trước khi mất quyền kiểm soát. Không trì hoãn chúng tới một hook mà chương trình không kiểm soát được thời điểm chạy.

## 2. Hợp đồng chính xác của hai lifecycle hooks

Thư viện JNI được link động có thể export hai hàm theo tên chuẩn:

~~~c
#include <jni.h>

JNIEXPORT jint JNICALL JNI_OnLoad(JavaVM *vm, void *reserved) {
    (void)vm;
    (void)reserved;
    return JNI_VERSION_1_8;
}

JNIEXPORT void JNICALL JNI_OnUnload(JavaVM *vm, void *reserved) {
    (void)vm;
    (void)reserved;
    /* Không bắt buộc phải làm gì ở đây. */
}
~~~

Đây là một đoạn C minh họa độc lập về **chữ ký hook**, chưa phải toàn bộ chương trình Java+JNI. Thư viện thực còn phải có hàm JNI tương ứng với Java native methods. `JNIEXPORT` đảm bảo export/visibility cần thiết; `JNICALL` mang calling convention; có `JNI_OnLoad` thì return version JNI VM hỗ trợ. `reserved` là tham số dành riêng, không sử dụng.

### 2.1. `JNI_OnLoad`

- Là **hook tùy chọn** được JVM gọi khi thư viện động được nạp qua `System.loadLibrary` hoặc cơ chế tương đương.
- Nhận `JavaVM *`, **không nhận `JNIEnv *` trực tiếp**; nếu dùng JNI cần môi trường hợp lệ theo thread/context.
- Trả về version như `JNI_VERSION_1_8` để báo API JNI tối thiểu yêu cầu; VM từ chối version không hỗ trợ và hành xử như load thất bại.
- Hữu ích cho khởi tạo native-only state ngắn gọn và `RegisterNatives` khi thật sự cần; code khởi tạo phải có đường cleanup lỗi.
- Không phải Java class constructor, không thay thế việc quản lý tài nguyên trên từng object.

Nếu thư viện động không định nghĩa `JNI_OnLoad`, đặc tả quy định VM giả định nó chỉ yêu cầu JNI version `JNI_VERSION_1_1`. Không trả `JNI_OK` thay cho một version JNI; giá trị `JNI_OK` là mã thành công của các API khác, không phải version yêu cầu.

### 2.2. `JNI_OnUnload`

- Là **hook tùy chọn** được JVM gọi khi class loader chứa native library bị garbage-collected.
- Prototype **trả `void`**; không có “giá trị đồng ý unload” để application dùng.
- Được gọi trong một **unknown context** (ví dụ ngữ cảnh liên quan finalization). Đặc tả khuyên thận trọng khi dùng dịch vụ VM và không tùy tiện callback Java.
- Không nhận sẵn `JNIEnv *`; đừng giả định đang có Java caller, thread Java cụ thể, context class loader ban đầu hoặc JVM đã sẵn sàng để gọi mọi Java API.
- Không bảo đảm đúng lúc ứng dụng `close`, không phải một public Java API để “unload ngay bây giờ”, và không nên dùng như shutdown hook duy nhất.

Lời gọi `System.loadLibrary` **không trả một handle có phương thức `unload()`**. Cơ chế unload thuộc JVM và class-loader lifecycle. Việc Java tự gọi `System.gc()` hay gán một biến bằng `null` không buộc VM phải chạy `JNI_OnUnload`.

### 2.3. `JNI_OnLoad_L` / `JNI_OnUnload_L`: trường hợp link tĩnh

Đặc tả JNI còn có hook cho **thư viện liên kết tĩnh vào image VM**, đặt tên với hậu tố library: `JNI_OnLoad_L` và `JNI_OnUnload_L` (trong đó `L` là tên thư viện). Đây là cơ chế khác với `JNI_OnLoad`/`JNI_OnUnload` của thư viện động. Với ví dụ dùng `.so`, `.dylib` hoặc `.dll` thông thường, ta dùng phiên bản **không hậu tố**.

Không nhầm `JNI_OnUnload_L` (hook unload JNI cho library tĩnh) với phương thức Java `ClassLoader` có tên tương tự. Đặc tả nói `JNI_OnUnload_L` cũng chạy ở unknown context và cần cùng cách tiếp cận thận trọng.

## 3. Ai sở hữu native library? ClassLoader và namespace

Mỗi `ClassLoader` có namespace class của nó. Trong JNI, thư viện được quản lý theo loader đã nạp nó. Theo đặc tả, **cùng một native library không thể được nạp đồng thời vào nhiều class loader theo cách thông thường**; yêu cầu nạp lần nữa ở loader khác có thể ném `UnsatisfiedLinkError`. Quy tắc giúp ngăn namespace JNI lẫn giữa các classloader và cho phép library được dỡ khi loader tương ứng có thể được thu hồi.

Ví dụ:

~~~text
ApplicationClassLoader
    |
    +-- loads liblifecycle.so
    |
    +-- class demo.LifecycleExample

PluginClassLoader A
    |
    +-- plugin classes (may refer to native integration)
    |
PluginClassLoader B
    |
    +-- plugin classes
~~~

Nếu library được nạp từ lớp trong **ApplicationClassLoader**, việc thu hồi một plugin class loader khác **không tự động dỡ** thư viện đó. Nếu library được nạp bởi một loader plugin riêng, unloading phụ thuộc vào việc loader plugin này còn reachable hay không và JVM/OS đang quản lý image tương ứng thế nào.

Cùng tên class nhưng được định nghĩa bởi hai loader khác nhau là **hai class identities khác nhau**. Cached `jmethodID`/`jfieldID` phải gắn với defining class và không được chuyển từ lần nạp cũ sang lớp cùng tên sau reload. Cũng không suy ra chỉ vì có một đường dẫn thư viện giống nhau thì mọi bản class loader đều có thể cùng `System.loadLibrary` thành công.

### 3.1. Classloader bị thu hồi khi nào?

GC thường chỉ có thể unload class loader khi không còn strong reachability cần thiết tới nó và các class/object gắn với nó, đồng thời điều kiện của JVM cho phép. Những thứ thường vô tình giữ loader sống:

- Object Java, thread hoặc task còn giữ instance của class do loader ấy định nghĩa.
- Thread context class loader (`Thread.currentThread().getContextClassLoader()`) còn trỏ tới plugin loader.
- Static registry, event bus, callback list hoặc executor của ứng dụng cha giữ class instance, `Class<?>`, `Method` hoặc listener từ plugin.
- C/C++ lưu **strong JNI global reference** tới class/object/plugin loader rồi không gọi `DeleteGlobalRef`.
- Native thread còn hoạt động/callback, hoặc JVM còn có stack frame/method execution liên quan.
- Framework/service còn giữ các resource hoặc metadata khiến loader reachable.

**Đặc biệt:** `jclass` là JNI object reference tới `java.lang.Class`. `NewGlobalRef(env, clazz)` tạo strong global reference có thể giữ class và loader sống. Nếu bạn định chỉ `DeleteGlobalRef` bên trong `JNI_OnUnload`, hook có thể **không được gọi chính vì strong reference ấy đang ngăn loader trở thành collectible**. Đây là vòng phụ thuộc không thể sửa bằng việc “chờ GC lâu hơn”.

### 3.2. Unload không bằng “giải phóng file DLL ngay lập tức”

Ngay cả khi một loader trở nên eligible for GC, thời điểm GC, class unloading, JNI unload hook và OS-level library handle release là hành vi runtime/platform. Cơ chế JVM gọi `JNI_OnUnload` thuộc hợp đồng JNI; không nên viết business logic phụ thuộc thứ tự chi tiết của mọi pha GC hoặc việc file `.dll` có thể bị xóa ngay trên từng hệ điều hành.

Không tự gọi `dlclose`/`FreeLibrary` trên image thư viện được JVM nạp trong `JNI_OnUnload` để “tăng tốc”: JVM quản lý handle tương ứng, manual unload có thể tạo double unload hoặc code đang chạy từ binary đã bị unmap.

## 4. Những việc **không nên làm** trong `JNI_OnUnload`

Có những thao tác C native-only rất nhỏ có thể được dùng để dọn bộ nhớ cuối cùng **nếu** biết chắc ownership và không còn user nào; nhưng hook không phải nơi an toàn để chạy bất cứ thứ gì mà bạn thường chạy từ Java. Các nhóm rủi ro:

| Không nên làm trong hook | Vì sao | Chuyển việc đó đi đâu? |
| --- | --- | --- |
| `FindClass` để tìm class của plugin đang unload | Loader gốc có thể không còn; `FindClass` trong `JNI_OnUnload` dùng **system class loader** theo đặc tả, không phải loader lúc `JNI_OnLoad` | Tra cứu trước khi unload trong native call thông thường; lấy đúng `Class<?>` từ Java |
| `CallVoidMethod`/`CallStaticVoidMethod` để chạy cleanup Java | Unknown context; callback có thể khởi tạo class, lấy lock, cấp phát hoặc tái nhập VM | Java `close()` khi trạng thái ứng dụng còn hợp lệ |
| Tạo object Java, đăng ký listener, truy cập logger Java | Có thể làm class/loader được hồi sinh, ném exception hoặc deadlock | Đường khởi tạo và đóng thông thường |
| Khởi chạy/attach thread mới vào JVM | Có thể block, phụ thuộc lifecycle VM hoặc giữ code/loader còn sống | Thread quản lý từ `open/start`, dừng/join trước `close` |
| Dùng `JNIEnv *` lưu từ lần callback cũ | `JNIEnv *` thuộc thread cũ và không hợp lệ cho thread khác | Lấy env hợp lệ tại lời gọi JNI đang hoạt động |
| Chờ lock/condition của thread Java | Hook không có thứ tự cố định với Java lifecycle; thread chờ có thể đã dừng | Shutdown có trật tự ở application layer |
| I/O chặn lâu, RPC/network call, truy vấn DB | Không có SLA/timing chắc chắn; deadlock/hang unload | Dừng/flush từ Java hoặc native close trước đó |
| `System.gc()`, `System.exit()`, `DestroyJavaVM()` | Reentrancy hoặc tác động toàn VM từ context không xác định | Quyết định lifecycle chỉ ở tầng application/host |
| Tự `dlclose`/`FreeLibrary` library của mình | JVM/OS đang quản lý native image, nguy cơ unload sai thời điểm | Để VM/loader làm việc của nó |
| Dựa vào thứ tự unload giữa các JNI libraries | Không có hợp đồng thứ tự ứng dụng mong muốn | Quản lý dependency và teardown trước khi dỡ loaders |
| Hủy con trỏ native còn được callback/thread dùng | Use-after-free/dangling function pointer nếu còn công việc bất đồng bộ | Dừng nhận việc, drain, join, sau đó free tại explicit close |
| Giữ global `jclass` tới khi `JNI_OnUnload` | Strong ref có thể pin loader, ngăn hook được chạy | `DeleteGlobalRef` ở shutdown tường minh |

Các hành động “không nên” ở bảng chủ yếu là **các quyết định thiết kế không an toàn**, không phải tuyên bố JNI cấm toàn bộ C standard library. `free` một allocation **thuần C**, do thư viện sở hữu độc quyền, đã không còn ai sử dụng có thể là một cleanup nhỏ phù hợp. Ngược lại, `free` con trỏ mượn từ `GetStringChars` hoặc `Get<Type>ArrayElements` là sai: các pointer đó phải trả bằng JNI Release tương ứng, và lý tưởng không tồn tại borrowed pointer nào khi tới unload.

### 4.1. Vì sao `FindClass` trong unload đặc biệt nguy hiểm?

Oracle JNI Functions nêu rõ: gọi `FindClass` từ `JNI_OnLoad` dùng class loader của class đang nạp library; gọi từ `JNI_OnUnload` dùng kết quả `ClassLoader.getSystemClassLoader()`, bởi loader khi load có thể đã không còn.

Ví dụ không nên viết:

~~~c
/* SAI: KHÔNG chạy; đây chỉ là minh họa anti-pattern. */
JNIEXPORT void JNICALL JNI_OnUnload(JavaVM *vm, void *reserved) {
    JNIEnv *env = NULL;
    (void)reserved;
    if ((*vm)->GetEnv(vm, (void **)&env, JNI_VERSION_1_8) == JNI_OK) {
        jclass plugin = (*env)->FindClass(env, "plugin/PluginMain");
        /* Giả định class plugin phải còn tìm được từ loader cũ! */
        (void)plugin;
    }
}
~~~

Đoạn trên minh họa **tại sao logic sai**, không phải hook được khuyến nghị. Có thể thất bại, dùng sai loader hoặc phát sinh JNI exception; ngay cả khi `GetEnv` thành công cũng không biến context unload thành một Java callback bình thường. Đừng thay `FindClass` bằng `Class.forName` rồi coi như đã giải quyết: điều đó chỉ chuyển việc callback/class loading sang một thời điểm không an toàn.

### 4.2. Tránh hồi sinh dependency

Nếu hook gọi lại Java logger, event listener hoặc một framework singleton, các hệ thống đó có thể giữ lại class/object/loader mà JVM đang cố dỡ; có thể tạo vòng lifetime, deadlock hoặc trạng thái partial shutdown. Cũng không nên ném Java exception từ hook vì đây không phải một Java method có caller rõ ràng để xử lý exception theo ứng dụng.

Thay vì code phức tạp trong hook, cung cấp method `shutdown/close` gọi khi plugin còn hoạt động, gọi được Java/native services mà nó cần, đồng bộ kết thúc in-flight work, xóa registrations và global refs, rồi mới cho loader trở thành không reachable.

## 5. Chiến lược đúng: dọn tài nguyên **trước** khi classloader biến mất

Một ứng dụng/plugin có native resources nên làm theo thứ tự:

~~~text
ACTIVE: Java object / plugin / native library đang hoạt động
  |
  | 1. Ngừng nhận request hoặc callback mới
  | 2. Chờ các request/in-flight native calls kết thúc
  | 3. Dừng và join native workers; detach native threads đúng quy tắc
  | 4. Đóng file/socket/DB/GPU/native handles, trả borrowed JNI refs
  | 5. Hủy native callback registrations, DeleteGlobalRef, clear caches
  | 6. Xóa Java references, context classloader và registries
  v
CLOSED: tài nguyên đã giải phóng; không có native code đang dùng handle cũ
  |
  | 7. Nếu loader trở nên collectible, VM/GC có thể unload
  v
JNI_OnUnload: hook nhỏ, không phụ trách nghiệp vụ hay cleanup chính
~~~

Một vòng đời rõ ràng ở Java có thể dựa vào:

- `AutoCloseable` và `try-with-resources` cho các instance có native handles.
- `close()`/`stop()` ở tầng plugin manager trước khi bỏ `ClassLoader`.
- `ExecutorService.shutdown()` và `awaitTermination()` có timeout hợp lý; native worker threads phải có cơ chế stop/join riêng.
- Cấu trúc owner/lifetime rõ ràng cho `NewGlobalRef`, `NewWeakGlobalRef`, malloc/new, callback function pointers và các resource của hệ điều hành.
- Idempotent cleanup: gọi `close()` hai lần không free hai lần, mọi đường lỗi khởi tạo đều trả tài nguyên đã lấy.
- `Cleaner` của Java chỉ dùng làm **fallback** cuối cùng, không thay `close()` vì thời điểm Cleaner chạy không được bảo đảm.

**Hook unload không phải destructor của mọi Java object.** Một library có thể phục vụ hàng nghìn native handles trong cùng một loader; một object close không unload library, và library unload không là điểm chính để free từng object nếu các object còn cần cleanup trước đó.

### 5.1. Global references và caches JNI

Khi C tạo:

~~~c
/* Mảnh minh họa trong một native method có env hợp lệ. */
jclass global_class = (jclass)(*env)->NewGlobalRef(env, local_class);
/* ... dùng khi class còn sống ... */
(*env)->DeleteGlobalRef(env, global_class);
~~~

Cần khớp chính xác mỗi reference được tạo thành công với một lần xóa, sau khi đã bảo đảm không còn code sử dụng. Xóa quá sớm gây dangling reference; không xóa thì class/loader có thể bị giữ sống. `jmethodID` và `jfieldID` **không** phải JNI object references: chúng không được truyền cho `DeleteGlobalRef` và chỉ hợp lệ khi class định nghĩa method/field còn loaded. Nếu dùng weak global `jclass` để cho phép unloading, phải nâng weak ref thành strong local `NewLocalRef` cho khoảng sử dụng, revalidate identity và rebuild ID nếu class cũ đã unload.

Không đổi lấy “cache nhanh” bằng cách pin loader tới hết process nếu plugin cần hot reload. Những reference/pointer này nên thuộc resource owner hoặc registry có explicit clear, không trông chờ `JNI_OnUnload` cleanup tự động.

## 6. Ví dụ chạy được: Java 17 chủ động `close`, JNI_OnUnload cố ý không callback

Ta tạo một thư viện nhỏ tên logic `lifecycle`. Java mở native counter, gọi C để tăng giá trị, rồi đóng. C implementation có **đúng cả `JNI_OnLoad` và `JNI_OnUnload`**, nhưng không dùng unload hook để giải phóng counter của Java instance: counter được giải phóng bởi `nativeRelease` ngay trong `close()`. Kết quả có thể kiểm chứng **không phụ thuộc GC**.

Cấu trúc:

~~~text
jni-lifecycle-demo/
├── src/
│   └── demo/
│       └── LifecycleExample.java
├── native/
│   └── lifecycle.c
└── build/              (được tạo khi build)
    ├── classes/
    ├── include/
    └── lib/
~~~

### 6.1. Java: nguồn đầy đủ `src/demo/LifecycleExample.java`

~~~java
package demo;

public final class LifecycleExample implements AutoCloseable {
    static {
        System.loadLibrary("lifecycle");
    }

    // 0 nghĩa là chưa mở hoặc đã đóng; chỉ wrapper sở hữu handle.
    private long nativeHandle;

    public LifecycleExample(int seed) {
        if (seed < 0) {
            throw new IllegalArgumentException("seed must be non-negative");
        }
        long opened = nativeCreate(seed);
        if (opened == 0L) {
            throw new IllegalStateException("native creation failed");
        }
        nativeHandle = opened;
    }

    public synchronized int next() {
        long current = nativeHandle;
        if (current == 0L) {
            throw new IllegalStateException("resource is closed");
        }
        return nativeNext(current);
    }

    @Override
    public synchronized void close() {
        long current = nativeHandle;
        if (current != 0L) {
            nativeHandle = 0L;
            nativeRelease(current);
        }
    }

    private static native long nativeCreate(int seed);
    private static native int nativeNext(long handle);
    private static native void nativeRelease(long handle);

    public static void main(String[] args) {
        try (LifecycleExample counter = new LifecycleExample(10)) {
            System.out.println("value=" + counter.next());
            System.out.println("value=" + counter.next());
        }
        System.out.println("closed");
    }
}
~~~

Điểm cần hiểu:

- `try (...)` gọi `close()` khi rời khối, kể cả có exception trong thân khối.
- `synchronized` trên mỗi instance khiến `next` và `close` không thể chạy đồng thời thông qua public wrapper của cùng instance. Không dùng `nativeHandle` sau khi chuyển thành 0.
- `nativeCreate` là function C tạo tài nguyên; nếu đã có Java exception pending, native trả về 0 và exception được truyền ngược về Java. Constructor chỉ ném `IllegalStateException` nếu nhận 0 mà không có exception khác.
- `close` idempotent ở Java: nếu handle đã 0 thì không giải phóng lần nữa.
- **Không** khai báo `finalize()`, không gọi `System.gc()`, không phụ thuộc việc JVM unload library trước hoặc sau dòng `closed`.
- Native methods để `private` giúp tránh caller Java thông thường truyền một số `long` giả làm pointer. Đây không phải security boundary; API native production cần kiểm soát handle mạnh hơn khi data có thể đến từ untrusted clients.

### 6.2. C11: nguồn đầy đủ `native/lifecycle.c`

~~~c
#include "demo_LifecycleExample.h"
#include <stdint.h>
#include <stdlib.h>

_Static_assert(sizeof(void *) <= sizeof(jlong),
               "This demo requires native pointer to fit in jlong");

typedef struct {
    jint value;
} NativeCounter;

static void raise_java(JNIEnv *env, const char *class_name,
                       const char *message) {
    jclass type = (*env)->FindClass(env, class_name);
    if (type != NULL) {
        (*env)->ThrowNew(env, type, message);
        (*env)->DeleteLocalRef(env, type);
    }
}

/* Hook lúc library được nạp: không tạo Java class hoặc thread. */
JNIEXPORT jint JNICALL JNI_OnLoad(JavaVM *vm, void *reserved) {
    (void)vm;
    (void)reserved;
    return JNI_VERSION_1_8;
}

/* Hook lúc VM dỡ library: không gọi Java và không chờ GC. */
JNIEXPORT void JNICALL JNI_OnUnload(JavaVM *vm, void *reserved) {
    (void)vm;
    (void)reserved;
    /* NativeCounter của từng object PHẢI được close trước đó.
       Không chạy arbitrary Java callback trong hook này. */
}

JNIEXPORT jlong JNICALL
Java_demo_LifecycleExample_nativeCreate(JNIEnv *env, jclass owner,
                                        jint seed) {
    (void)owner;

    if (seed < 0) {
        raise_java(env, "java/lang/IllegalArgumentException",
                   "seed must be non-negative");
        return 0;
    }

    NativeCounter *counter = malloc(sizeof *counter);
    if (counter == NULL) {
        raise_java(env, "java/lang/OutOfMemoryError",
                   "cannot allocate native counter");
        return 0;
    }

    counter->value = seed;
    return (jlong)(intptr_t)counter;
}

JNIEXPORT jint JNICALL
Java_demo_LifecycleExample_nativeNext(JNIEnv *env, jclass owner,
                                      jlong handle) {
    (void)owner;

    if (handle == 0) {
        raise_java(env, "java/lang/IllegalStateException",
                   "native handle is closed");
        return 0;
    }

    NativeCounter *counter = (NativeCounter *)(intptr_t)handle;
    if (counter->value == INT32_MAX) {
        raise_java(env, "java/lang/ArithmeticException",
                   "counter overflow");
        return 0;
    }

    return ++counter->value;
}

JNIEXPORT void JNICALL
Java_demo_LifecycleExample_nativeRelease(JNIEnv *env, jclass owner,
                                         jlong handle) {
    (void)env;
    (void)owner;

    if (handle != 0) {
        NativeCounter *counter = (NativeCounter *)(intptr_t)handle;
        free(counter);
    }
}
~~~

Đây là một thư viện JNI **C11 đầy đủ** cho ví dụ, **không có `main` trong C**. Function names phải khớp header sinh bằng `javac -h`. `_Static_assert` giới hạn việc dùng pointer-as-`jlong` ở target mà pointer vừa trong `jlong`; trên nền tảng không phù hợp hoặc khi cần chống forged/dangling handles, thay bằng bảng opaque handles, generation IDs và quản lý reference counting.

Chú ý khác biệt **đúng thời điểm**:

- `JNI_OnLoad` chỉ trả phiên bản JNI; không mở một resource cần `close`. Nó không cần `JNIEnv *`, nên không gọi `GetEnv`/`AttachCurrentThread`.
- `nativeCreate` tạo resource thuộc Java instance và trả native handle.
- `nativeNext` chỉ làm việc với handle còn mở. Java đồng bộ lời gọi `next/close` ở cấp instance. Nếu một tiến trình khác bypass wrapper và dùng raw handle, native vẫn không có cách xác thực pointer: ví dụ là demo, không phải boundary chống dữ liệu không tin cậy.
- `nativeRelease` free native allocation **trong lời gọi có lifecycle rõ ràng**.
- `JNI_OnUnload` **không được dùng để lần ngược tìm các NativeCounter**: không có registry; nếu object quên `close`, code này sẽ leak native allocation trước khi JVM/OS dọn process. Đó là lý do contract yêu cầu close.

Đặt `free` trong `nativeRelease` chứ không phải `JNI_OnUnload` tránh phụ thuộc GC, và tránh giữ global `jclass` khiến loader không bao giờ unload. Kể cả nếu `JNI_OnUnload` không chạy trong cả phiên, mỗi instance được đóng vẫn giải phóng allocation đúng hạn.

## 7. Biên dịch và chạy trên Linux, macOS, Windows

Các lệnh sau chạy từ thư mục `jni-lifecycle-demo`. Cần JDK 17+, C compiler có C11 và kiến trúc phù hợp với JVM. `JAVA_HOME` phải trỏ đến thư mục JDK chứa `include/jni.h`.

### 7.1. Linux (GCC hoặc Clang)

~~~sh
mkdir -p build/classes build/include build/lib
javac -h build/include -d build/classes src/demo/LifecycleExample.java

cc -std=c11 -O2 -Wall -Wextra -Wpedantic -fPIC -shared \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  -Ibuild/include \
  native/lifecycle.c -o build/lib/liblifecycle.so

java -Djava.library.path=build/lib -cp build/classes demo.LifecycleExample
~~~

### 7.2. macOS (Clang)

~~~sh
mkdir -p build/classes build/include build/lib
javac -h build/include -d build/classes src/demo/LifecycleExample.java

cc -std=c11 -O2 -Wall -Wextra -Wpedantic -fPIC -dynamiclib \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/darwin" \
  -Ibuild/include \
  native/lifecycle.c -o build/lib/liblifecycle.dylib

java -Djava.library.path=build/lib -cp build/classes demo.LifecycleExample
~~~

### 7.3. Windows x64 (MSVC Developer Command Prompt)

~~~bat
mkdir build\classes
mkdir build\include
mkdir build\lib
javac -h build\include -d build\classes src\demo\LifecycleExample.java

cl /nologo /std:c11 /W4 /O2 /LD ^
  /I"%JAVA_HOME%\include" ^
  /I"%JAVA_HOME%\include\win32" ^
  /I"build\include" ^
  native\lifecycle.c ^
  /link /OUT:build\lib\lifecycle.dll

java -Djava.library.path=build\lib -cp build\classes demo.LifecycleExample
~~~

Các dòng trên là Windows **Command Prompt**, dấu `^` nối dòng; dùng MSVC có hỗ trợ `/std:c11` (Visual Studio 2019 bản đủ mới hoặc mới hơn). `System.loadLibrary("lifecycle")` nhận tên **logic**, JVM ánh xạ theo OS, không truyền `.so`/`.dll` vào chuỗi tên logic.

Output **stdout chính xác** của ví dụ, sau khi build/load thành công:

~~~text
value=11
value=12
closed
~~~

Không có dòng `unloaded`. Vì chương trình thường dùng application class loader sống suốt quá trình, `JNI_OnUnload` có thể **không chạy trước khi JVM kết thúc**. Nếu tự in một dòng từ hook, nó không phải phần của stdout ổn định để đặt vào unit test.

### 7.4. Kiểm tra symbol thực sự được export

Linux:

~~~sh
nm -D --defined-only build/lib/liblifecycle.so | \
  grep -E 'JNI_On(Load|Unload)|Java_demo_LifecycleExample'
~~~

Cần có `JNI_OnLoad`, `JNI_OnUnload`, `Java_demo_LifecycleExample_nativeCreate`, `Java_demo_LifecycleExample_nativeNext`, `Java_demo_LifecycleExample_nativeRelease`. Địa chỉ, thứ tự và ký tự symbol type tùy binary. Một native lib có `JNI_OnUnload` trong source nhưng không export vì visibility sai sẽ không cung cấp hook cho JVM.

Trên macOS dùng `nm -gU build/lib/liblifecycle.dylib` (Mach-O tools thường hiện dấu gạch dưới ở đầu tên symbol); trên Windows dùng `dumpbin /exports build\lib\lifecycle.dll`. Nếu gặp `UnsatisfiedLinkError`, kiểm tra đúng file/kiến trúc, `java.library.path`, dependency, generated JNI header và export table. Lỗi load library không đồng nghĩa hook unload đã chạy.

## 8. Khi nào `JNI_OnUnload` thực sự có cơ hội chạy?

Trong ví dụ trên, `demo.LifecycleExample` được nạp bởi application class loader thông thường. Loader này có thể sống tới hết process, nên **không thể dùng chương trình một lần chạy để kiểm thử deterministic `JNI_OnUnload`**.

Một bài test nâng cao có thể dùng **child-first/isolated URLClassLoader** tự định nghĩa lớp plugin chứa lệnh `System.loadLibrary`, không nạp thư viện đó trước trong parent. Sau khi gọi plugin:

1. Thực hiện `stop/close` toàn bộ native handles và stop callbacks trước.
2. Xóa listener, task, TCCL và strong references trong parent registry tới plugin.
3. Gỡ những reference Java được giữ trong harness (plugin object, `Class<?>`, `Method`, loader).
4. Dùng `WeakReference<ClassLoader>` để quan sát tính reachability của loader, kết hợp log class unloading của VM.
5. Đề nghị GC và đợi **có giới hạn**, ghi nhận kết quả nhưng không coi chưa unload trong lần chạy là lỗi function `JNI_OnUnload`.

Minh họa đoạn harness Java **không độc lập**:

~~~java
// Mảnh minh họa: pluginLoader thực sự được tạo/nạp plugin ở bên ngoài.
WeakReference<ClassLoader> witness =
        new WeakReference<>(pluginLoader);

// Phải close toàn bộ plugin resources và bỏ mọi strong references.
pluginInstance = null;
pluginClass = null;
pluginLoader = null;

System.gc();  // Chỉ là gợi ý, không bảo đảm GC/unload.
System.out.println("loaderGone=" + (witness.get() == null));
// Cả true lẫn false đều là trạng thái quan sát được, không là assertion.
~~~

Cần `import java.lang.ref.WeakReference;`, biến `pluginLoader`, `pluginClass`, `pluginInstance` được khai báo trong harness thật, và tránh reference còn nằm trên stack/JIT local. Trong test đáng tin cậy, tạo plugin load/unload trong helper method riêng, trả về `WeakReference` rồi mới thực hiện quan sát ở caller, tránh locals giữ loader ngoài ý muốn. `System.gc()` có thể bị vô hiệu hóa hoặc trì hoãn; log/class unloading flags phụ thuộc VM/version.

**Không triển khai test bằng cách nạp chính file `liblifecycle.so` đồng thời ở hai class loaders rồi mong cả hai thành công.** JNI quy định không cùng nạp một native library vào nhiều class loaders; điều đó có thể chủ động sinh `UnsatisfiedLinkError`. Để kiểm thử reload nối tiếp, đợi loader cũ được thu hồi và thư viện được VM unload, hoặc dùng các bản library riêng đúng quy trình và namespace.

### 8.1. Dùng log của HotSpot cho mục đích chẩn đoán

Trên HotSpot/JDK 17, có thể chạy với logging liên quan class unloading; ví dụ:

~~~sh
java -Xlog:class+unload=info \
  -Djava.library.path=build/lib \
  -cp build/classes demo.LifecycleExample
~~~

Lệnh này vẫn chỉ chạy **demo app-loader**, do đó log unload có thể không xuất hiện. `-Xlog:class+unload=info` là **tính năng chẩn đoán HotSpot**, không phải hợp đồng chuẩn bắt buộc mọi JVM hỗ trợ. Với plugin-loader test, dùng nó cùng log native được thiết kế không gây side effect (ví dụ diagnostic C nhỏ không chặn) thay vì lấy việc gọi `System.gc()` làm bằng chứng chắc chắn.

Không nên dùng `JNI_OnUnload` để tăng bộ đếm trong Java rồi chờ Java thấy bộ đếm: đúng lúc Java class/loader được unload, không còn quan hệ Java lifecycle đáng tin để callback và quan sát.

## 9. Vòng tham chiếu khiến hook không chạy: ví dụ sai và cách sửa

### 9.1. Sai: `NewGlobalRef` giữ class mãi, đợi hook giải phóng

~~~c
/* CHỈ MINH HỌA ANTI-PATTERN — KHÔNG GHÉP VÀO DEMO. */
static jclass cached_plugin_class;

static void remember_class(JNIEnv *env, jclass clazz) {
    cached_plugin_class =
        (jclass)(*env)->NewGlobalRef(env, clazz);
}

/* Sai về thiết kế: tính chạy được của hook lại phụ thuộc vào
   việc chính global ref này đã được giải phóng! */
JNIEXPORT void JNICALL JNI_OnUnload(JavaVM *vm, void *reserved) {
    /* Không thể trông chờ luôn tới được đây để delete ref. */
}
~~~

Trong code này, strong global reference làm class reachable. Nếu class được định nghĩa bởi plugin loader, reference còn giữ cả vòng đời loader liên quan. Vì loader không trở nên collectible, hook mong đợi dọn ref có thể không bao giờ chạy. Đây không phải lỗi của GC mà là **lỗi về ownership**.

### 9.2. Đúng: cleanup theo owner trong JNI method bình thường

~~~c
/* Mảnh minh họa khi caller Java còn sống và đang gọi JNI. */
static jclass cached_class;

static int init_cache(JNIEnv *env, jclass clazz) {
    jclass global = (jclass)(*env)->NewGlobalRef(env, clazz);
    if (global == NULL) {
        return 0;
    }
    cached_class = global; /* Chỉ publish dưới synchronization phù hợp. */
    return 1;
}

static void clear_cache(JNIEnv *env) {
    jclass old = cached_class;
    cached_class = NULL;
    if (old != NULL) {
        (*env)->DeleteGlobalRef(env, old);
    }
}
~~~

Đây là **đoạn minh họa**, không phải thread-safe implementation độc lập. Cần cùng một lock hoặc owner với protocol active-call stop để không xảy ra race giữa việc xóa ref và native callback đang sử dụng nó. Khi thư viện phục vụ nhiều class loaders hoặc nhiều owners, đừng dùng một global variable duy nhất; dùng registry theo class identity và tránh overwrites/leaks.

Giao thức đúng: application ngừng gọi cache, dừng callback/worker, chờ mọi readers hoàn tất, gọi `clear_cache(env)` từ native method có `JNIEnv *` hợp lệ, rồi cho loader/objects trở thành unreachable. Khi GC quyết định unload, không còn strong global ref pin loader.

### 9.3. Nếu dùng weak references

`NewWeakGlobalRef(env, clazz)` không pin referent giống strong global reference, nhưng weak handle có thể mất đối tượng. Mỗi lần dùng cần tạo strong local `NewLocalRef` và kiểm tra `NULL`; không được kiểm tra weak ref rồi giả định nó bất biến qua GC:

~~~c
/* Mảnh minh họa: weak_class là jweak còn được registry sở hữu. */
jclass strong = (jclass)(*env)->NewLocalRef(
    env, (jobject)weak_class);
if (strong == NULL) {
    /* Class đã bị thu hồi hoặc không tạo được local ref:
       kiểm tra exception và bỏ các IDs cũ khi không còn valid. */
} else {
    /* Dùng IDs đúng class khi strong local còn sống. */
    (*env)->DeleteLocalRef(env, strong);
}
~~~

Khi đã có class mới cùng tên sau reload, `jmethodID`/`jfieldID` cũ không được tái sử dụng. Weak/global registry cũng có cleanup riêng như `DeleteWeakGlobalRef` theo owner; không trì hoãn vô hạn đến hook.

## 10. Native threads và callbacks: phải dừng trước unload

Một native worker thread có thể giữ function pointers vào code của JNI library, đang gọi lại Java qua `JavaVM *`, hoặc dùng objects thuộc plugin. Nếu runtime unload binary khi thread đó vẫn còn chạy code trong binary, hậu quả có thể rất nghiêm trọng. Cần quản lý teardown **ngoài hook**:

1. Phát tín hiệu stop và ngừng nhận việc mới.
2. Chờ in-flight Java→native calls hoàn thành.
3. Hủy native timers, callbacks hoặc OS event hooks đã đăng ký.
4. Join các worker threads có thể join; tránh chờ vô hạn, thiết kế timeout phù hợp.
5. Mỗi attached native thread tự `DetachCurrentThread` trước khi kết thúc, theo hợp đồng Invocation API.
6. Giải phóng global/weak references, method IDs cache owner và memory sau khi không còn users.
7. Thả Java references đến plugin để loader có thể collectible.

`JNIEnv *` không thread-safe để chuyển từ một thread sang thread khác. Nếu worker cần JNI calls, phải nhận môi trường của **chính thread đó** thông qua `GetEnv`/`AttachCurrentThread` theo quy tắc. Attached native threads còn sống có thể cản VM shutdown và giữ các dependencies khác. Không chọn `JNI_OnUnload` là nơi đầu tiên báo stop rồi mới đợi join: hook có thể xảy ra trong context không tương thích, và loader có thể bị giữ sống bởi những worker mà hook đang đợi.

Nếu dùng `RegisterNatives`, function pointers đăng ký cũng phải khớp đúng lớp/loader và không được để callback JNI chạy với code đã dỡ. Hãy xử lý registration ở init/destroy có owner rõ ràng, thay vì tùy tiện `UnregisterNatives` từ unknown unload context.

## 11. `Cleaner`, shutdown hook và VM termination có thay thế được `close()` không?

**Không.** Cả ba đều có ích trong các bối cảnh riêng nhưng không cho cùng cam kết như close:

| Cơ chế | Khi nào chạy | Không bảo đảm |
| --- | --- | --- |
| `try-with-resources` / `AutoCloseable.close` | Khi Java kiểm soát rời scope hoặc gọi close | Chỉ hoạt động khi caller thực sự áp dụng và cleanup không bị crash process |
| `Cleaner` (Java 9+) | Khi object được xác định eligible và cleaner được xử lý | Thời điểm/dù có chạy trước process exit; thứ tự; Java object đã bị GC |
| `Runtime.addShutdownHook` | Trong shutdown sequence khi JVM hỗ trợ | Chạy khi kill cưỡng bức, VM crash, power loss; thứ tự liên quan native unload |
| `JNI_OnUnload` | Khi loader sở hữu library được GC/unload theo JNI | Gọi ngay khi Java object close, lúc `main` return, sau mỗi library load |
| C `atexit` | C runtime process termination theo platform/termination path | Gắn với Java class-loader lifecycle; thời điểm khi JVM vẫn an toàn |
| OS thu hồi process memory | Khi process thật sự kết thúc | Flush/close giao thức ứng dụng, bảo toàn dữ liệu, cleanup thiết bị/remote state |

`Cleaner` nên là fallback nếu cần thu hồi native memory khi caller quên close, nhưng cleaning action không được giữ strong reference tới object được clean. Vì vậy phải quản lý native handle/lifetime thông qua cleaning state riêng và đồng bộ để tránh double-free với `close()`. Đừng mặc định một native pointer được phép free an toàn từ Cleaner nếu native callback khác còn dùng nó.

Shutdown hooks cũng có hạn chế: bất kỳ lỗi JVM/crash/killed process nào cũng có thể bỏ qua hook; thứ tự shutdown hooks và các library unloading không phải cơ chế dọn tài nguyên native phụ thuộc. Đặt **ngữ nghĩa tài nguyên** ở `close()` và **ngữ nghĩa library lifecycle** ở `JNI_OnLoad/OnUnload`.

## 12. Phân tích những tình huống thực tế

### 12.1. Servlet server hot redeploy

Một plugin hoặc ứng dụng web tạo C callback dùng ClassLoader phiên bản A. Redeploy tạo loader phiên bản B, nhưng callback/native registry còn global ref đến class A. Kết quả: loader A không unload, memory và metadata tăng dần. Dù có `JNI_OnUnload` cố gắng clear refs, hook có thể không bao giờ gọi.

**Cách sửa:** hook lifecycle của ứng dụng gọi `stop()` trước undeploy, stop callback, delete global references, clear Java listener/thread context loader, rồi mới bỏ loader A. Không nạp lại cùng native binary từ loader B khi A chưa thực sự được release theo quy tắc JNI; thiết kế common native layer ở parent loader nếu cần chia sẻ.

### 12.2. Một thư viện C cache `JNIEnv *` toàn cục

Native code lưu `JNIEnv *` khi load và dùng lại trong hook unload. Không hợp lệ vì env thuộc thread cụ thể. Ngay cả khi `GetEnv` trong hook trả success, bạn vẫn đang trong unknown context không phù hợp để gọi Java tùy ý.

**Cách sửa:** không cache `JNIEnv *`; mỗi JNI entry point nhận env hợp lệ. Với native workers, attach/detach trước lúc shutdown tường minh. Chỉ cache `JavaVM *` khi có lý do và lifetime VM đã được kiểm soát; `JavaVM *` không biến hook thành nơi an toàn để callback.

### 12.3. Native library quản lý socket/file

Một thư viện giữ socket dùng nhiều lần; đội phát triển chỉ gọi `close(socket)` trong `JNI_OnUnload`. Ứng dụng server chạy nhiều tháng, loader sống suốt process, socket không bao giờ đóng sau khi một session kết thúc.

**Cách sửa:** native socket thuộc session/resource owner; close trong `AutoCloseable.close()` ngay khi xong công việc. Unload hook, nếu có, chỉ thu dọn trạng thái thư viện còn sót thuần native mà chắc chắn không ai dùng, không phụ trách đóng mọi session.

### 12.4. Hook ghi log bằng Java và deadlock

`JNI_OnUnload` cố gọi Java logging framework. Logging class có thể phải initialize hoặc đợi lock mà một thread ứng dụng đang giữ trong quá trình stop, dẫn tới deadlock hoặc class-loader resurrection.

**Cách sửa:** log cần thiết được phát ra khi `stop/close` còn chạy trong Java bình thường. Hook unload tối giản; diagnostic native nhỏ, không block và không có callback Java nếu thực sự cần.

### 12.5. JVM thoát nhưng không có dòng log "onUnload"

Không tự kết luận JNI hook sai: ứng dụng mặc định dùng application loader không được GC trong suốt phiên. JVM process exit không phải classloader unload test có thể định thời. Đặt unit test đúng ở public close contract và để kiểm tra unloading ở harness riêng với điều kiện, logs và timeout.

## 13. Checklist cho library có `JNI_OnUnload`

- **Owner:** Biết ClassLoader nào đã `System.loadLibrary` và library được quản lý bởi loader nào; không giả định cùng file có thể load bởi nhiều loaders đồng thời.
- **Hook chữ ký:** `JNIEXPORT void JNICALL JNI_OnUnload(JavaVM*,void*)` đúng export; `JNI_OnLoad` trả một `JNI_VERSION_*` được hỗ trợ.
- **Unknown context:** Không callback Java tùy ý, không giả định `JNIEnv *` hay original class loader có sẵn; không `FindClass` để tìm plugin class trong unload.
- **Reachability:** Không giữ strong global `jclass`, Java objects, TCCL hoặc native callbacks quá lifetime; đặc biệt không phụ thuộc unload hook để xóa chính global refs đang pin loader.
- **Deterministic cleanup:** Java `AutoCloseable/close/stop` đóng tài nguyên native, clear registrations/caches, stop/join threads và giải phóng refs trước khi bỏ loader.
- **No active code:** Không còn native thread, JNI callback hoặc function pointer đang chạy từ library lúc có thể unload. Đừng `dlclose/FreeLibrary` thủ công thư viện mà JVM quản lý.
- **Concurrency:** Cleanup chống double-free/use-after-free; giải quyết in-flight work và lock theo giao thức dừng có thứ tự, không đợi vô hạn trong unload hook.
- **ID lifetime:** `jmethodID/jfieldID` gắn class identity và không hợp lệ sau khi class unload; không reuse qua classloader reload.
- **Failures:** Mỗi nhánh init lỗi trả tài nguyên đã cấp, không chỉ mong fallback unload. App code phải tiếp tục đúng ngay cả khi VM không gọi hook.
- **Tests:** Unit test `close()` deterministic; class-loader unload test riêng chỉ quan sát, không assert GC timing; kiểm tra exported hook symbols và JNI version trên target JDK.
- **Observability:** Không lấy stdout từ `JNI_OnUnload` làm kết quả bắt buộc của chương trình. GC, shutdown và JNI unload không có chung clock.

**Quy tắc cuối cùng:** `JNI_OnUnload` là **cơ hội dọn phần còn lại trong một thời điểm do VM quyết định**, không phải điểm an toàn để tạo công việc Java mới hoặc xử lý toàn bộ shutdown. Dọn tài nguyên khi **owner vẫn tồn tại**, để class loader có thể thực sự biến mất; sau đó hook unload, nếu xảy ra, nên càng đơn giản và độc lập Java càng tốt.

### Tài liệu tham khảo chính thức

- Oracle, [JNI Invocation API — Library and Version Management](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/invocation.html): cơ chế thư viện theo class loader, `JNI_OnLoad`, `JNI_OnUnload` và cảnh báo unknown context.
- Oracle, [JNI Functions — FindClass](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/functions.html#findclass): quy tắc chọn classloader khi `FindClass` chạy từ `JNI_OnLoad` và `JNI_OnUnload`.
- Oracle, [JNI Functions — Global and Weak References](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/functions.html): `NewGlobalRef`, `DeleteGlobalRef`, `NewWeakGlobalRef`, `NewLocalRef`, quyền sở hữu JNI reference.
- Oracle, [Java SE 17 AutoCloseable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AutoCloseable.html): contract explicit close và try-with-resources.
- Oracle, [Java SE 17 Cleaner](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/Cleaner.html): cleanup fallback và giới hạn không bảo đảm timing.