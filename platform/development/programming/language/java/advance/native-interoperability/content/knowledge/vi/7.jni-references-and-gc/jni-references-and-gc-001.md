# Vì sao tham chiếu JNI không phải địa chỉ ổn định của đối tượng Java

## Mục tiêu bài học

Trong Java Native Interface (JNI), tham số có kiểu `jobject`, `jstring`, `jclass` hoặc `jarray` trông giống một con trỏ ở phía C/C++. Tuy nhiên, **một JNI reference là tay nắm (handle) do JVM quản lý, không phải cam kết rằng giá trị bit của nó là địa chỉ vật lý hiện tại của đối tượng Java trên heap**. JVM cần cơ chế tham chiếu như vậy để quản lý vòng đời đối tượng và cho phép garbage collector (GC) di chuyển đối tượng mà mã native vẫn truy cập đúng đối tượng về mặt logic.

Bài này giải thích tại sao không thể dùng `jobject` như địa chỉ ổn định, cách GC và JNI phối hợp, giới hạn của local/global/weak global references, cách xác định identity bằng `IsSameObject` và cách giữ một đối tượng Java an toàn qua nhiều lời gọi native. Ví dụ dùng Java 17+ và JNI C, phân biệt rõ mã độc lập với snippet minh họa.

## 1. Java reference, JNI reference và địa chỉ vùng nhớ là ba khái niệm khác nhau

Một đoạn Java quen thuộc:

~~~java
Object a = new Object();
Object b = a;
System.out.println(a == b); // true: cùng một object về identity
~~~

`a` và `b` là **tham chiếu ở cấp ngôn ngữ Java**; Java specification không định nghĩa chúng như những con số địa chỉ mà ứng dụng được phép dereference. Khi Java gọi:

~~~java
private static native void inspect(Object value);
~~~

mã C nhận một tham số kiểu `jobject`:

~~~c
JNIEXPORT void JNICALL Java_Example_inspect(
        JNIEnv *env, jclass cls, jobject value);
~~~

Với `static native`, JVM bổ sung hai đối số đầu: `JNIEnv *` và `jclass`. Phương thức instance sẽ nhận `jobject receiver` ở vị trí thứ hai. `value` là tham chiếu JNI tới đối tượng Java đã truyền vào. **Chỉ JNI API mới là con đường được bảo đảm để dùng tham chiếu này.**

Cần phân biệt:

| Khái niệm | Ý nghĩa | Có dùng trực tiếp như địa chỉ heap Java không? |
| --- | --- | --- |
| Java reference (`Object a`) | Tham chiếu mức ngôn ngữ tới một object | Không; Java không cấp phép đọc địa chỉ vật lý |
| JNI reference (`jobject`, `jclass`, `jstring`, `jarray`) | Handle native được JVM theo dõi, có thời gian sống và phạm vi hợp lệ | Không; phải gọi các JNI functions |
| Native pointer (`void *`, `char *`, `uint8_t *`) | Địa chỉ một vùng nhớ native hoặc vùng nhớ được API cho mượn | Có thể dùng trong giới hạn hợp đồng cấp phát/acquire/release; không đồng nghĩa địa chỉ đối tượng Java |
| `jlong` dùng làm token | Một số nguyên 64-bit do ứng dụng đặt ý nghĩa | Không tự trở thành handle hợp lệ; không thay được `jobject` hoặc cơ chế ownership |

Từ `jobject` trong header có thể có biểu diễn dạng pointer-like và thậm chí hai handle có giá trị nhìn giống nhau trên một JVM cụ thể. **Kiểu C trông giống pointer không tạo ra hợp đồng địa chỉ**. Không dùng `(void *)value` để dereference nội dung, không đặt `value` vào `uintptr_t` rồi coi như địa chỉ, và không suy đoán layout của đối tượng từ offset.

## 2. Vì sao JVM cần gián tiếp (indirection)?

Nhiều garbage collector hiện đại có khả năng **di chuyển/compact** các đối tượng trong quá trình quản lý heap. Chẳng hạn, tại một thời điểm object `X` có thể nằm ở vùng heap A; sau một pha thu gom, JVM đặt cùng object theo identity tại vùng heap B. Điều quan trọng là object vẫn là object đó, các Java references và JNI references còn hợp lệ vẫn tiếp tục trỏ tới nó một cách logic.

Sơ đồ khái niệm (không phải layout bắt buộc của một JVM):

~~~text
Trước GC:

Native JNI code                 JVM quản lý reference            Java heap
local jobject r  ──────────────>  handle / root  ───────────────> object X ở A

Sau khi GC compact:

Native JNI code                 JVM cập nhật quản lý              Java heap
local jobject r  ──────────────>  handle / root  ───────────────> object X ở B

Identity: vẫn là object X.      Địa chỉ lưu trữ vật lý: có thể đổi.
~~~

Ví dụ này diễn tả một cách triển khai bằng handle table. JVM cũng có thể dùng chiến lược khác (như cập nhật hoặc mã hóa references, read barriers, cơ chế handle riêng). **JNI chỉ cam kết ngữ nghĩa và thời gian sống tham chiếu hợp lệ; không chuẩn hóa nội bộ bảng handle hay địa chỉ object.**

Hai kết luận không được nhầm:

- **Tham chiếu JNI hợp lệ có thể theo cùng một đối tượng xuyên qua GC**, vì JVM nhận biết và xử lý tham chiếu đó.
- **Không có bảo đảm rằng địa chỉ vật lý của đối tượng giữ nguyên**; cũng không có bảo đảm GC lần nào cũng di chuyển đối tượng. Bài học là không được dựa vào địa chỉ, không phải khẳng định mọi JVM luôn dời mọi object.

Nếu native code giữ một raw memory address suy ra bằng mẹo nào đó từ object rồi GC di chuyển object, địa chỉ cũ có thể không còn biểu thị dữ liệu đúng, thậm chí bị tái sử dụng. JNI reference hợp lệ bảo vệ **identity và khả năng truy cập qua JVM**, không tạo quyền đọc trực tiếp layout heap.

## 3. JNI reference là "opaque": điều gì được phép làm?

Trong phần lớn chương trình JNI, quy tắc an toàn là:

1. Nhận `jobject`/`jstring`/`jarray` từ tham số native hoặc từ JNI API.
2. Chỉ dùng JNI functions để đọc field, gọi method, truy cập mảng/chuỗi, tạo/xóa loại reference.
3. Không dereference như struct C và không lưu số địa chỉ tự diễn giải.
4. Kiểm tra tính hợp lệ của reference theo **lifetime và loại reference**; không coi một giá trị pointer khác `NULL` là bằng chứng handle còn sống.
5. Dùng `IsSameObject` để so sánh **object identity** trong JNI; không dựa vào so sánh bit pattern của hai `jobject`.

Ví dụ minh họa JNI C (đoạn bên trong hàm native có `env`, `first` và `second` đều là reference còn hợp lệ):

~~~c
jboolean same = (*env)->IsSameObject(env, first, second);
if (same == JNI_TRUE) {
    /* Hai tham chiếu cùng trỏ về một object theo JNI identity. */
}
~~~

Hàm `IsSameObject` so sánh identity, không gọi Java `equals()`. Hai đối tượng có thể `equals() == true` nhưng **không** cùng identity. Ngược lại, Java `a == b` (cho reference types) hỏi về identity tương tự ý nghĩa của `IsSameObject`.

### Vì sao `first == second` ở C không đủ?

Một JVM có thể tạo **hai local JNI references khác nhau** cho cùng một object; `NewLocalRef` không được yêu cầu tái sử dụng cùng giá trị handle của reference ban đầu. Nếu chỉ so sánh hai biến C kiểu pointer-like bằng `==`, bạn có thể đang so sánh hai vị trí handle nội bộ thay vì identity đối tượng. Việc một số runtime tình cờ cho cùng bit pattern không biến cách đó thành portable.

Cũng không dùng `System.identityHashCode(object)` như địa chỉ; nó trả một giá trị băm dựa trên identity, có thể trùng giữa hai object và không biểu thị heap address.

## 4. Ba loại JNI object references cần nắm

| Loại | Tạo thường dùng | Thời gian sống / nơi sử dụng | Ảnh hưởng tới khả năng GC thu hồi |
| --- | --- | --- | --- |
| **Local reference** | Đối số method, kết quả nhiều JNI calls, `NewLocalRef` | Hợp lệ trong scope JNI hiện tại và **thread tạo ra nó**; thường được thu hồi tự động khi native method trả về | Là strong reference trong thời gian hợp lệ; JVM có thể di chuyển object nhưng không thu hồi object chỉ còn strong reference này |
| **Global reference** | `NewGlobalRef` | Hợp lệ cho đến `DeleteGlobalRef`; có thể mang qua lời gọi và thread khác với đồng bộ phù hợp | Là strong reference; giữ object còn reachable tới khi xóa hoặc vòng đời VM chấm dứt |
| **Weak global reference** (`jweak`) | `NewWeakGlobalRef` | Tồn tại như một JNI handle cho đến `DeleteWeakGlobalRef`, nhưng object mục tiêu có thể không còn | Không giữ object sống; sau khi GC xử lý, reference có thể hành xử như `NULL` |

**"Global" không nghĩa là địa chỉ object ổn định.** Nó chỉ kéo dài thời gian sống và cho phép JNI sử dụng reference qua nhiều native method/thread theo quy tắc. Garbage collector vẫn có thể di chuyển object mà global reference giữ.

**"Weak global" không tương đương với strong global.** Một `jweak` có thể trở nên không sử dụng được khi GC thu hồi mục tiêu, dù handle `jweak` vẫn được mã native lưu trong biến. Cần tạo một strong local/global reference từ weak trước khi thao tác.

### 4.1. Local references: phạm vi và cleanup

Ví dụ nếu C nhận `jobject arg` từ một native method, `arg` là local reference hợp lệ trong lời gọi hiện tại. Nhiều JNI calls trả thêm local references, ví dụ `FindClass`, `GetObjectField` hay `GetObjectArrayElement`.

Nếu tạo local reference trong một vòng lặp dài, bạn nên xóa từng handle khi xong để không tích lũy quá nhiều local references:

~~~c
/* Đoạn minh họa ở trong hàm JNI, giả định array hợp lệ. */
jsize length = (*env)->GetArrayLength(env, array);
for (jsize i = 0; i < length; ++i) {
    jobject item = (*env)->GetObjectArrayElement(env, array, i);
    if ((*env)->ExceptionCheck(env)) {
        return; /* Có exception pending: caller nhận exception của JVM. */
    }

    /* Xử lý item qua các JNI API hợp lệ. */

    if (item != NULL) {
        (*env)->DeleteLocalRef(env, item);
    }
}
~~~

Đây là **snippet**, không phải chương trình C có thể chạy độc lập: `env`, `array` và return type cần nằm trong hàm native tương ứng. Trong mã thực, nếu phần xử lý tạo exception, hãy cleanup trước khi trở về khi an toàn. `DeleteLocalRef` không giải phóng đối tượng Java ngay lập tức; nó bỏ một root tham chiếu, sau đó GC mới quyết định vòng đời object theo toàn bộ đồ thị references.

Các API `EnsureLocalCapacity`, `PushLocalFrame` và `PopLocalFrame` giúp quản lý nhiều local refs trong code native phức tạp. Đối với native thread tự attach vào JVM, cần đặc biệt chủ động xóa local refs tồn đọng; không nên giả định chúng được thu hồi sau một lời gọi helper C tùy ý.

**Không** lưu `jobject arg` vào biến static/global C hoặc đưa sang thread khác rồi dùng sau khi native method đã return. Cụ thể, đối tượng Java vẫn sống ở Java **không làm handle local cũ sống lại**. Để sử dụng sau lời gọi, tạo `NewGlobalRef` hoặc thiết kế dữ liệu native có ownership rõ ràng.

### 4.2. Global references: kéo dài lifetime có chủ đích

~~~c
/* Bên trong native method; object là local JNI reference còn hợp lệ. */
jobject retained = (*env)->NewGlobalRef(env, object);
if (object != NULL && retained == NULL) {
    /* Có thể có OutOfMemoryError pending. */
    return;
}

/* ... Dùng retained trong các lần gọi JNI sau, có đồng bộ thích hợp ... */

if (retained != NULL) {
    (*env)->DeleteGlobalRef(env, retained);
}
~~~

Các dòng này minh họa nguyên tắc, không phải một chương trình độc lập hay một ví dụ lifetime nhiều lời gọi hoàn chỉnh. Ví dụ có thể chạy đầy đủ ở mục 8.

Một global reference có thể mang qua thread khác, **nhưng `JNIEnv *` thì không**: mỗi thread phải có interface pointer của chính nó khi truy cập JNI (thread native có thể cần attach qua `JavaVM`). Global refs giữ object reachable nên quên `DeleteGlobalRef` có thể gây **rò rỉ giữ sống (retention leak)**, kể cả khi Java code không còn giữ đối tượng.

Đừng dùng `free(retained)` hoặc `delete retained`. Đây là tài nguyên JNI do JVM quản lý và phải xóa bằng **`DeleteGlobalRef`**, không phải native heap allocation.

### 4.3. Weak global references: "kiểm tra còn sống" không đủ

~~~c
/* Ví dụ minh họa; weak là jweak hợp lệ được tạo từ NewWeakGlobalRef. */
jobject strong = (*env)->NewLocalRef(env, weak);
if (strong == NULL) {
    /* Mục tiêu có thể đã được GC thu hồi; cũng kiểm tra exception
       vì cấp phát local reference có thể thất bại. */
} else {
    /* Trong thời gian strong còn hợp lệ, object được giữ reachable. */
    /* Sử dụng strong qua JNI functions. */
    (*env)->DeleteLocalRef(env, strong);
}
~~~

**Vì sao không chỉ gọi `IsSameObject(env, weak, NULL)`?** GC có thể chạy **sau lần kiểm tra** và trước lần bạn dùng `weak`. Kết quả kiểm tra trước không bảo đảm đối tượng còn tồn tại ở thời điểm sau (race giữa check và use). Tạo `NewLocalRef(env, weak)`, xác nhận kết quả và giữ strong local reference suốt thời gian thao tác mới tránh cửa sổ race này. Sau khi xong, `DeleteLocalRef` và cuối cùng `DeleteWeakGlobalRef` khi không cần weak nữa.

Không dùng kết quả có thể thay đổi do GC như điều kiện để tự viết một "địa chỉ ổn định". Weak JNI reference chịu chính sách GC/reference processing; không có cách portable để buộc mục tiêu luôn tồn tại chỉ với `jweak`.

## 5. Cái gì xảy ra khi method native kết thúc?

Xem đoạn Java:

~~~java
static native void saveForLater(Object object);

static void demo() {
    Object item = new Object();
    saveForLater(item);
    // Java vẫn có thể giữ item, nhưng JNI local ref được tạo cho
    // tham số saveForLater không có hiệu lực sau khi method đã trả về.
}
~~~

Nếu C viết như sau thì **sai lifetime**:

~~~c
/* PHẢN VÍ DỤ: tuyệt đối không dùng cho code thật. */
static jobject invalid_cached;

JNIEXPORT void JNICALL Java_Example_saveForLater(
        JNIEnv *env, jclass cls, jobject object) {
    (void) env;
    (void) cls;
    invalid_cached = object;  /* Chỉ chép giá trị handle local. */
}
~~~

Sau khi function return, biến `invalid_cached` chứa một **local JNI reference hết hiệu lực**. Ngay cả khi Java vẫn có strong reference tới cùng object, việc dùng handle cũ trong JNI API sau đó vẫn sai hợp đồng và có thể gây crash hoặc lỗi khó tái hiện.

Sửa đúng bằng cách tạo global reference:

~~~c
/* PHÁC THẢO: cần đồng bộ khi nhiều thread cùng truy cập retained. */
static jobject retained = NULL;

JNIEXPORT void JNICALL Java_Example_saveForLater(
        JNIEnv *env, jclass cls, jobject object) {
    (void) cls;
    jobject fresh = (*env)->NewGlobalRef(env, object);
    if (object != NULL && fresh == NULL) {
        return; /* Nếu OOM: giữ retained cũ, không xóa. */
    }
    if (retained != NULL) {
        (*env)->DeleteGlobalRef(env, retained);
    }
    retained = fresh;
}
~~~

Nếu `object == NULL`, `NewGlobalRef` trả `NULL` theo hợp đồng; đoạn này xóa tham chiếu cũ. Nhưng nếu allocation thất bại, phải **giữ global cũ** và để pending exception được truyền về Java. Không phát minh cơ chế lấy địa chỉ hoặc giữ local reference vì sợ chi phí `NewGlobalRef`.

Ví dụ phác thảo cần cơ chế synchronization cho access tới `retained`, bảo đảm không có thread xóa reference khi thread khác đang sử dụng. Cách đơn giản cho ví dụ đồng bộ là serialize các native methods qua `static synchronized` ở Java. Đối với thư viện nhiều consumer, dùng mutex / owner object / native handle table có thread-safety thích hợp.

## 6. Object identity, `equals` và giá trị số của handle

Java có hai khái niệm rõ:

~~~java
String left = new String("data");
String right = new String("data");
String alias = left;

System.out.println(left == right);       // false
System.out.println(left.equals(right));  // true
System.out.println(left == alias);       // true
~~~

Tạo tệp `IdentityOnly.java` để chạy độc lập:

~~~java
public final class IdentityOnly {
    public static void main(String[] args) {
        String left = new String("data");
        String right = new String("data");
        String alias = left;
        System.out.println("same-object-a=" + (left == right));
        System.out.println("same-value=" + left.equals(right));
        System.out.println("same-object-b=" + (left == alias));
    }
}
~~~

Chạy trên JDK 17 trở lên:

~~~bash
javac -encoding UTF-8 IdentityOnly.java
java IdentityOnly
~~~

Stdout:

~~~text
same-object-a=false
same-value=true
same-object-b=true
~~~

Nếu truyền `left` và `right` vào JNI, `IsSameObject` trả `JNI_FALSE` vì chúng là hai object khác identity, bất kể nội dung `"data"` bằng nhau. Nếu truyền `left` và `alias`, `IsSameObject` trả `JNI_TRUE`.

**Tránh thay identity bằng con số dễ nhớ.** Cả `hashCode()`, `System.identityHashCode` lẫn địa chỉ giả định từ `jobject` đều không phải unique ID tuyệt đối hoặc stable object address được Java/JNI specification quy định. Muốn định danh nghiệp vụ xuyên tiến trình/phiên, ứng dụng phải tự tạo ID với phạm vi và quy tắc uniqueness thích hợp.

## 7. Khi nào JNI trả con trỏ dữ liệu thực?

Thỉnh thoảng mã JNI nhận một **native pointer** từ API như:

- `GetByteArrayElements`/`GetIntArrayElements` và các API mảng primitive khác;
- `GetStringChars`/`GetStringUTFChars`;
- `GetPrimitiveArrayCritical`/`GetStringCritical`;
- `GetDirectBufferAddress` cho một direct `ByteBuffer` phù hợp.

Những pointer này **không biến `jobject` thành địa chỉ đối tượng Java**. Chúng là quyền truy cập tới **dữ liệu cụ thể** với lifetime do API quy định:

| JNI API | Pointer chỉ tới đâu? | Điểm cần chú ý |
| --- | --- | --- |
| `GetByteArrayElements` | Vùng phần tử `byte[]`, có thể là copy hoặc vùng pinned | Không giả định là heap object header; gọi `ReleaseByteArrayElements` đúng cặp |
| `GetStringChars` | Vùng UTF-16 code units, có thể là copy | Gọi `ReleaseStringChars` khi xong |
| `GetStringUTFChars` | Vùng byte Modified UTF-8 | Gọi `ReleaseStringUTFChars`; không nhầm MUTF-8 với UTF-8 chuẩn |
| `GetPrimitiveArrayCritical` | Vùng phần tử primitive trong khoảng critical region, có thể là copy | Giữ critical region ngắn, tránh blocking/JNI calls không cho phép, release ngay |
| `GetDirectBufferAddress` | Địa chỉ bắt đầu vùng nhớ của direct buffer | Đó là địa chỉ vùng buffer, không phải địa chỉ object `ByteBuffer` |

Với `GetPrimitiveArrayCritical`, JVM có thể **pin** vùng dữ liệu hoặc dùng phương án khác (bao gồm copy). Mã native không được thực hiện các thao tác chặn kéo dài hay các JNI calls bị hạn chế trong critical region. Con trỏ hết quyền dùng sau release; việc JVM có pin thật hay không là chi tiết triển khai.

Với `GetByteArrayElements`, giả định “luôn trả pointer tới heap” là sai: JVM có thể copy. Nếu `isCopy == JNI_TRUE`, bạn vẫn phải tuân theo release mode để copy-back/thả vùng nhớ theo đúng mục đích. Ngay cả trường hợp truy cập trực tiếp vào các phần tử, pointer chỉ có lifetime của API, **không phải địa chỉ ổn định vĩnh viễn của đối tượng Java**.

Với `GetDirectBufferAddress`, direct buffer có thể dùng bộ nhớ off-heap. Nếu native cần giữ pointer lâu hơn một lời gọi, hãy quy định rõ ownership và bảo đảm buffer/native memory còn sống; một global reference thích hợp tới buffer có thể giúp giữ đối tượng Java reachable, nhưng **không thay cho quy tắc lifetime của allocation gốc**, đặc biệt khi native memory do phía ngoài sở hữu. API có thể trả `NULL` khi buffer không hỗ trợ truy cập direct theo yêu cầu.

## 8. Ví dụ JNI đầy đủ: local identity và giữ object bằng global reference

Mục tiêu chương trình:

1. Tạo thêm một local reference tới cùng object và dùng `IsSameObject` để so sánh identity.
2. Lưu object qua **nhiều lời gọi** bằng `NewGlobalRef`.
3. So sánh một object khác để thấy hai object không cùng identity.
4. Xóa global reference bằng `DeleteGlobalRef`; sau đó trạng thái lưu không còn object.

Không có bước đọc địa chỉ object. Kết quả ví dụ là deterministic, **không cần gọi `System.gc()` và không phụ thuộc JVM có di chuyển object trong lần chạy hay không**.

### 8.1. Java source: `ReferenceHandleDemo.java`

~~~java
public final class ReferenceHandleDemo {
    static {
        System.loadLibrary("jnihandles");
    }

    private static native boolean sameViaLocal(Object value);

    // Đồng bộ hóa các lượt thao tác lên biến global ở C cho ví dụ này.
    private static synchronized native void retain(Object value);
    private static synchronized native boolean matches(Object candidate);
    private static synchronized native void clear();

    public static void main(String[] args) {
        Object a = new Object();
        Object b = new Object();

        System.out.println("same-local=" + sameViaLocal(a));
        retain(a);
        try {
            System.out.println("saved-a=" + matches(a));
            System.out.println("saved-b=" + matches(b));
        } finally {
            clear();
        }
        System.out.println("saved-after-clear=" + matches(a));
    }
}
~~~

`static synchronized native` là Java method vừa `native` vừa `synchronized`; JVM giữ monitor của `ReferenceHandleDemo.class` khi vào mỗi phương thức này. Ở phạm vi ví dụ, ba hàm `retain`/`matches`/`clear` đều truy cập cùng một biến global và được tuần tự hóa qua monitor đó. Khi xây dựng native library dùng đồng thời bởi nhiều class loaders, nhiều API entry points hoặc thread không qua monitor, phải thiết kế khóa/owner ở cấp native thích hợp.

### 8.2. C source: `ReferenceHandleDemo.c`

~~~c
#include <jni.h>
#include "ReferenceHandleDemo.h"

static jobject saved_global = NULL;

JNIEXPORT jboolean JNICALL Java_ReferenceHandleDemo_sameViaLocal(
        JNIEnv *env, jclass clazz, jobject value) {
    (void) clazz;
    if (value == NULL) {
        return JNI_FALSE;
    }

    jobject alias = (*env)->NewLocalRef(env, value);
    if (alias == NULL) {
        /* Nếu hết bộ nhớ có thể đang có exception pending. */
        return JNI_FALSE;
    }

    jboolean same = (*env)->IsSameObject(env, value, alias);
    (*env)->DeleteLocalRef(env, alias);
    return same;
}

JNIEXPORT void JNICALL Java_ReferenceHandleDemo_retain(
        JNIEnv *env, jclass clazz, jobject value) {
    (void) clazz;

    jobject fresh = NULL;
    if (value != NULL) {
        fresh = (*env)->NewGlobalRef(env, value);
        if (fresh == NULL) {
            /* Allocation thất bại: không thay đổi saved_global. */
            return;
        }
    }

    if (saved_global != NULL) {
        (*env)->DeleteGlobalRef(env, saved_global);
    }
    saved_global = fresh;
}

JNIEXPORT jboolean JNICALL Java_ReferenceHandleDemo_matches(
        JNIEnv *env, jclass clazz, jobject candidate) {
    (void) clazz;
    if (saved_global == NULL) {
        return JNI_FALSE;
    }

    return (*env)->IsSameObject(env, saved_global, candidate);
}

JNIEXPORT void JNICALL Java_ReferenceHandleDemo_clear(
        JNIEnv *env, jclass clazz) {
    (void) clazz;
    if (saved_global != NULL) {
        (*env)->DeleteGlobalRef(env, saved_global);
        saved_global = NULL;
    }
}
~~~

Điểm cần quan sát ở C:

- `saved_global` có kiểu `jobject` nhưng **không bao giờ bị dereference** như con trỏ tới struct Java.
- `NewLocalRef` tạo handle thứ hai cùng identity, `IsSameObject` xác nhận; `DeleteLocalRef` bỏ handle tạm.
- `NewGlobalRef` tạo một strong JNI root có hiệu lực qua nhiều lời gọi. Nếu thất bại khi `value != NULL`, hàm giữ handle cũ và để Java nhận lỗi đã pending của JVM.
- `matches` so sánh bằng `IsSameObject`. Nó không so sánh `saved_global == candidate` vì hai reference values có thể khác nhau dù trỏ cùng object.
- `clear` xóa chính global reference tạo trước đó. Sau clear không dùng lại handle đã bị xóa.
- Kiểu và tên function phải khớp header do `javac -h` sinh; tham số `JNIEnv *` và `jclass` đứng trước đối số Java của các `static native` methods.

### 8.3. Build trên Linux và stdout

Yêu cầu: **JDK 17+**, compiler C hỗ trợ C11, biến `JAVA_HOME` trỏ tới JDK đang dùng. Đặt hai tệp chung một thư mục rồi chạy:

~~~bash
javac -encoding UTF-8 -h . ReferenceHandleDemo.java

cc -std=c11 -Wall -Wextra -Werror -fPIC -shared \
   -I"$JAVA_HOME/include" \
   -I"$JAVA_HOME/include/linux" \
   ReferenceHandleDemo.c -o libjnihandles.so

java -Djava.library.path=. ReferenceHandleDemo
~~~

Stdout của lệnh `java`:

~~~text
same-local=true
saved-a=true
saved-b=false
saved-after-clear=false
~~~

Giải thích:

- `same-local=true`: `value` và `alias` là hai references hợp lệ cùng trỏ về `a`.
- `saved-a=true`: global reference còn sống, `IsSameObject(saved_global, a)` trả true.
- `saved-b=false`: `b` là object khác.
- `saved-after-clear=false`: sau `DeleteGlobalRef`, biến C đã đặt về `NULL`, hàm `matches` trả false. Điều này **không chứng minh `a` đã bị GC thu hồi** — trong `main`, biến `a` vẫn có thể giữ object, và GC không có lịch trình cố định.

Lệnh compiler là **cho Linux**; trên macOS/Windows, cách tạo shared library, file extension và thư mục `include/<platform>` khác nhau. Ví dụ dùng package mặc định để dễ kiểm chứng symbol. Trong chương trình có package, overload hoặc tên native có ký tự đặc biệt, **dùng `javac -h`** thay vì đoán cách JNI name mangling.

Tệp header được sinh có prototype tương đương:

~~~c
JNIEXPORT jboolean JNICALL Java_ReferenceHandleDemo_sameViaLocal
  (JNIEnv *, jclass, jobject);
JNIEXPORT void JNICALL Java_ReferenceHandleDemo_retain
  (JNIEnv *, jclass, jobject);
JNIEXPORT jboolean JNICALL Java_ReferenceHandleDemo_matches
  (JNIEnv *, jclass, jobject);
JNIEXPORT void JNICALL Java_ReferenceHandleDemo_clear
  (JNIEnv *, jclass);
~~~

Đây là **phần prototype được trích gọn để giải thích**; header thật có include guards và phần khai báo khác. Nếu native library không tìm thấy, JVM báo `UnsatisfiedLinkError`; lỗi đó liên quan tên đường dẫn/symbol/library, không phải bằng chứng GC đã đổi địa chỉ Java object.

## 9. Weak global: chọn hành vi khi không muốn giữ object sống

Giả sử native cần một cache gắn với Java object, nhưng việc cache không được tự ngăn object bị thu gom. Sử dụng `jweak` và **nâng cấp thành strong local reference trước khi dùng**:

~~~c
/* Snippet: cached_weak là jweak hợp lệ và chưa DeleteWeakGlobalRef. */
jobject safe = (*env)->NewLocalRef(env, cached_weak);
if (safe == NULL) {
    if ((*env)->ExceptionCheck(env)) {
        /* Trường hợp không tạo được reference, ví dụ OOM. */
    } else {
        /* Mục tiêu đã không còn có thể nâng lên strong reference. */
    }
    /* Không gọi method/field access trên cached_weak lúc này. */
} else {
    /* safe giữ object reachable trong khi làm việc qua JNI. */
    /* ... một số JNI operations dùng safe ... */
    (*env)->DeleteLocalRef(env, safe);
}
~~~

Đoạn này là **logic minh họa**, không phải C function đầy đủ vì phụ thuộc `env` và `cached_weak`. Hàm `NewLocalRef` trả `NULL` khi mục tiêu weak đã bị thu hồi; cũng cần xét exception do không cấp được local reference. Nếu tạo được `safe`, strong local ref ngăn mục tiêu bị thu hồi trong khi reference đó còn hiệu lực; nó không ép địa chỉ heap bất biến.

Một ví dụ kiểm tra rồi dùng dễ mắc race:

~~~c
/* SAI: không đủ an toàn để dùng weak ở một thời điểm sau. */
if (!(*env)->IsSameObject(env, cached_weak, NULL)) {
    /* GC có thể xử lý mục tiêu giữa if và thao tác tiếp theo. */
    /* Không coi cached_weak lúc này là strong handle. */
}
~~~

Khi không cần cache, gọi `DeleteWeakGlobalRef` đúng một lần cho handle hợp lệ đó và không dùng nó tiếp. Đừng lấy nội dung pointer-like của `jweak` để khẳng định đối tượng còn sống.

## 10. Truyền reference qua thread và callback

Một lỗi phổ biến là gửi `jobject local` từ Java thread A tới native worker thread B. Trong JNI, **local reference chỉ hợp lệ trên thread tạo nó**. Điều này vẫn đúng nếu bạn tin rằng JVM không dời object hoặc object còn sống trong Java.

Nếu native job phải sử dụng object trên thread khác:

1. **Trước khi method return**, tạo `NewGlobalRef(env, object)` trên thread có `JNIEnv *` hợp lệ, khi local ref vẫn sống.
2. Bàn giao global reference theo một quy tắc thread-safe (queue/mutex/ownership), có đồng bộ khi xóa để tránh use-after-delete.
3. Thread native truy cập JNI bằng **`JNIEnv *` của chính thread đó**; với thread tự tạo, attach JVM qua `JavaVM` nếu cần và detach theo hợp đồng.
4. Khi xử lý xong, xóa global reference bằng `DeleteGlobalRef` trong JNI context hợp lệ; không giữ đến cuối tiến trình nếu không cần.

`JNIEnv *` cũng không phải địa chỉ đối tượng. Nó là interface pointer dành cho JNI calls trong thread; **không chia sẻ chính pointer này giữa threads**. `JavaVM *` có phạm vi VM và dùng trong việc attach/detach, nhưng vẫn cần tuân thủ API và lifetime JVM.

Nếu chỉ cần dữ liệu độc lập (ví dụ id số, byte buffer đã copy hoặc thông tin immutable), bạn có thể **copy dữ liệu** sang native storage có ownership rõ ràng và không giữ reference Java. Quyết định này tùy mục tiêu: giữ đối tượng Java để callback thì global ref; giữ riêng một snapshot dữ liệu thì bản copy có thể phù hợp hơn.

## 11. Tại sao "in ra địa chỉ" không thể chứng minh gì về ổn định?

Bạn có thể gặp mã thử nghiệm:

~~~c
/* Không dùng output này làm địa chỉ object hay làm identity. */
printf("%p\n", (void *) someJObject);
~~~

Kết quả (nếu code compile và `someJObject` được biểu diễn tương thích kiểu pointer) chỉ mô tả **biểu diễn numeric của handle** trong một runtime cụ thể. Nó không chứng minh object nằm ở địa chỉ đó, không chứng minh số đó ổn định theo thời gian, và không chứng minh hai handle trỏ cùng object.

Có ba câu hỏi riêng biệt:

- **Cùng object không?** Dùng `IsSameObject` khi cả hai JNI references hợp lệ.
- **Reference còn hợp lệ không?** Dựa vào loại local/global/weak, thread, frame, lifetime và ownership; không kiểm tra bằng cách dereference hoặc so sánh số pointer.
- **Bộ nhớ thực tế nằm ở đâu?** JNI không hứa cung cấp địa chỉ của một Java object chung; chỉ một số API cho mượn pointer tới dữ liệu cụ thể theo hợp đồng riêng.

`GetObjectRefType` (khi được gọi với reference hợp lệ) có thể trả loại local/global/weak của một JNI reference, nhưng nó **không phải công cụ cứu hộ một dangling handle**: đưa vào reference đã bị xóa hoặc không hợp lệ không biến hành vi thành an toàn. Không dùng `GetObjectRefType` để tự chứng minh object vẫn ở cùng địa chỉ.

## 12. Các lỗi JNI thường gặp và cách sửa

| Sai lầm | Điều gì có thể xảy ra? | Cách làm đúng |
| --- | --- | --- |
| Cast `jobject` thành C struct pointer và đọc field tại offset | Đọc nhầm bảng handle/vùng nhớ không hợp lệ; crash hoặc phá dữ liệu | Dùng `GetFieldID` + `GetObjectField`/`GetIntField` hoặc JNI API phù hợp |
| Lưu local `jobject` vào biến C static để dùng ở lần gọi sau | Dangling local reference sau khi native method return | Tạo `NewGlobalRef` trước khi lưu; `DeleteGlobalRef` đúng lúc |
| Đưa local reference từ thread A sang thread B | Vi phạm giới hạn thread, có thể lỗi JNI | Dùng global ref, ownership rõ, thread B lấy `JNIEnv *` của mình |
| So sánh hai `jobject` bằng toán tử C `==` để kiểm identity | Có thể so sánh giá trị handles khác nhau của cùng object | `IsSameObject` |
| Nghĩ global ref pin object ở vị trí heap hiện tại | Phụ thuộc layout/GC, không portable | Xem global ref là root có lifetime; không suy địa chỉ |
| Kiểm tra weak ref rồi dùng nó sau một khoảng thời gian | GC có thể thu hồi mục tiêu giữa check/use | `NewLocalRef(weak)` hoặc `NewGlobalRef(weak)` rồi giữ strong ref |
| Quên `DeleteGlobalRef` | Global root giữ object/đồ thị object alive lâu ngoài ý muốn | Ghép rõ mỗi acquire với release |
| Dùng pointer từ `GetArrayElements` sau release | Use-after-release; buffer copy có thể đã bị hủy | Chỉ dùng trong khoảng acquire/release |
| Định nghĩa `jstring` như `char *` | Nhầm reference object với dữ liệu text, sai encoding | Dùng `GetStringChars` / `GetStringUTFChars` và release |
| Coi `System.identityHashCode` là địa chỉ object | Nhầm hash identity với physical address | Xem nó là hash; không encode pointer hay ID duy nhất |

### Tình huống 1: thư viện native cache `jclass`

`FindClass` thường trả **local reference** kiểu `jclass`. Nếu thư viện muốn giữ reference tới class qua nhiều lời gọi, cần `NewGlobalRef` cho `jclass`, không cache nguyên local handle. `jclass` vẫn là JNI reference tới đối tượng class, không phải địa chỉ bất biến của metadata Java. Khi không cần cache, xóa global ref theo ownership đã thiết kế.

### Tình huống 2: mã native làm việc lâu trong một vòng lặp

Nếu một native method duyệt hàng trăm nghìn phần tử, cứ gọi `GetObjectArrayElement` mà không `DeleteLocalRef` có thể làm đầy local-reference table, giữ nhiều object sống và gây lỗi. Xóa từng local ref ngay sau khi dùng, hoặc quản lý local frames phù hợp.

### Tình huống 3: C library đòi `void *userData` trong callback

Không tùy tiện ghi `(void *)jobject` vào `userData` rồi coi nó là địa chỉ object. Nếu callback cùng thread và đồng bộ nằm trong lifetime local ref, có thể dùng handle theo hợp đồng JNI tại thời điểm hợp lệ (với quản lý rõ). Nếu callback bất đồng bộ, tạo global ref, quy định ai sở hữu/cancels callback, đồng bộ trước khi xóa và đảm bảo callback thread đã attach JVM. Một phương án khác là tự cấp phát native context chứa **global reference** cùng dữ liệu phụ trợ và giải phóng sau khi mọi callback kết thúc.

### Tình huống 4: “Tôi gọi `System.gc()` và tham chiếu in ra vẫn như cũ”

`System.gc()` chỉ là một lời đề nghị JVM thực hiện GC; không bắt buộc phải dời object hay chạy một cách cụ thể. Số numeric của JNI handle không phải object address. Vì vậy thí nghiệm “pointer in ra không đổi” không chứng minh code dùng pointer ấy là hợp lệ.

## 13. Checklist cho một JNI reference boundary an toàn

- [ ] Mọi `jobject`/`jstring`/`jclass`/`jarray` được sử dụng qua JNI APIs, không dereference như địa chỉ object.
- [ ] Local ref chỉ được dùng đúng thread và đúng JNI scope; đối số local không được giữ sau khi method return.
- [ ] Nếu object cần sống qua nhiều lời gọi hoặc thread, đã tạo global ref và xác định đúng lúc `DeleteGlobalRef`.
- [ ] Nếu cache yếu, dùng `jweak`; luôn nâng lên strong local/global ref thành công trước thao tác và xử lý khả năng object đã bị GC.
- [ ] So sánh identity bằng `IsSameObject`; không suy identity từ pointer bits, `equals` hoặc `identityHashCode`.
- [ ] Cặp `Get...Elements`/`Release...Elements`, `GetString...`/`ReleaseString...`, và critical region được xử lý đúng lifetime.
- [ ] Callback/native worker thread dùng `JNIEnv *` của thread đó và có chính sách synchronization/cleanup.
- [ ] Native code kiểm tra JNI exception khi một API có thể thất bại; không dùng reference vừa trả `NULL` như thành công.
- [ ] Không dựa vào việc JVM đang dùng collector di chuyển hay không, hoặc layout heap cụ thể.
- [ ] Kiểm thử lifetime, local refs trong loop, global leak, weak cleared, callback order và concurrency; không yêu cầu GC diễn ra theo một lịch chính xác.

## 14. Câu hỏi tự kiểm tra

**Câu 1.** Nếu hai biến `jobject` có bit pattern khác nhau, có chắc chúng tham chiếu tới hai object Java khác nhau?

Không. JVM có thể biểu diễn hai JNI handles khác nhau cho cùng object. Dùng `IsSameObject` với hai reference đang hợp lệ.

**Câu 2.** Tạo `NewGlobalRef` có giữ nguyên địa chỉ vật lý của đối tượng Java không?

Không. Global ref giữ **strong reachability và lifetime của JNI handle** đến khi `DeleteGlobalRef`; JVM vẫn được phép di chuyển đối tượng.

**Câu 3.** Java còn giữ object sau khi native method return. Native code có thể dùng lại `jobject` local đã lưu vào biến static không?

Không. Local reference hết hiệu lực theo scope của nó bất kể object còn reachable ở phía Java. Tạo `NewGlobalRef` trước khi lưu qua nhiều lời gọi.

**Câu 4.** Có thể dùng `jweak` ngay sau khi `IsSameObject(weak, NULL)` trả false không?

Không nên. GC có thể xử lý weak target sau lần kiểm tra và trước lần sử dụng. Tạo `NewLocalRef(weak)` để có strong local handle, kiểm tra NULL/exception, dùng strong handle rồi xóa.

**Câu 5.** `GetByteArrayElements` trả pointer khác địa chỉ in ra của `jbyteArray`. Có phải JVM lỗi không?

Không. `jbyteArray` là JNI object reference; `GetByteArrayElements` trả pointer tới **dữ liệu byte của array**, có thể là bản copy, với lifetime quản lý bằng release. Đây là hai loại giá trị khác nhau.

**Câu 6.** Khi callback chạy trên native thread khác, cần làm gì để gọi Java instance method trên object đã lưu?

Giữ object bằng global reference (và có đồng bộ với thao tác xóa), sử dụng `JNIEnv *` lấy cho callback thread qua JVM attachment/VM API, gọi đúng JNI method, xử lý exception và giải phóng reference khi kết thúc ownership.

**Câu 7.** Muốn biết hai object bằng nhau theo nội dung thì `IsSameObject` có đủ không?

Không. `IsSameObject` kiểm identity. Nếu cần logic Java `equals`, phải gọi method Java `equals` qua JNI hoặc so sánh dữ liệu theo một quy tắc nội dung rõ ràng.

## Tài liệu chính thức

1. [JNI Specification — Design Overview: Referencing Java Objects](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/design.html): lý do JVM quản lý tham chiếu, local/global references, GC và di chuyển object.
2. [JNI Specification — JNI Functions](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/functions.html): `NewLocalRef`, `NewGlobalRef`, `DeleteGlobalRef`, `IsSameObject`, weak global, `GetObjectRefType`, array/string access, critical regions.
3. [JNI Specification — Types and Data Structures](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/types.html): object reference types và primitive types.
4. [Oracle javac — Generate Native Header](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html): dùng `javac -h` để sinh JNI header.
5. [Android NDK — JNI Tips](https://developer.android.com/ndk/guides/jni-tips): thực hành reference ownership, global/local refs và thread behavior (các nguyên tắc tham chiếu cũng hữu ích khi làm việc với Java JNI thông thường).

**Kết luận:** `jobject` là một **tham chiếu logic có quản lý vòng đời**. JNI giữ mối liên hệ giữa reference và đối tượng đúng ngay cả khi GC thay đổi cách bố trí bộ nhớ, nhưng JNI không hứa một địa chỉ vật lý cố định. Hãy thiết kế dựa trên **local/global/weak reference lifetime**, truy cập qua JNI functions, so sánh bằng `IsSameObject` và quản lý ownership rõ ràng.
