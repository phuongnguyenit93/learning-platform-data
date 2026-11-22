# Tham chiếu toàn cục yếu trong JNI và cách nâng thành tham chiếu mạnh an toàn trước khi dùng

## 1. Bối cảnh: vì sao JNI cần weak global reference?

Khi Java gọi mã C/C++ qua **Java Native Interface (JNI)**, phía native nhận các tham chiếu như `jobject`, `jstring` hoặc `jclass`. JNI quản lý **vòng đời tham chiếu** khác với vòng đời đối tượng Java: lưu lại một giá trị `jobject` nhận từ tham số của phương thức native vào biến C dùng sau khi phương thức kết thúc là sai nếu đó chỉ là **local reference**.

Một số thư viện native muốn **nhớ đối tượng Java để có thể sử dụng về sau**: cache callback, đối tượng gắn với native handle, metadata, hoặc class. Nhưng nếu luôn dùng strong global reference, thư viện native có thể giữ đối tượng và cả đối tượng liên quan sống quá lâu, cản trở garbage collection (GC).

JNI cung cấp **weak global reference**, kiểu `jweak`, thông qua:

- `NewWeakGlobalRef(env, obj)`: tạo handle yếu có thể lưu qua nhiều lần gọi JNI và được dùng ở các luồng phù hợp.
- `DeleteWeakGlobalRef(env, weak)`: giải phóng handle yếu khi không cần nữa.
- `NewLocalRef(env, weak)`: cố **nâng** một weak global thành **local reference mạnh** trước khi truy cập đối tượng.
- `NewGlobalRef(env, weak)`: cố nâng thành **global reference mạnh**, khi cần giữ đối tượng qua thời gian dài hơn.

Một weak global **không giữ đối tượng Java sống** chỉ vì handle C vẫn tồn tại. Khi GC thu gom đối tượng, handle `jweak` có thể vẫn là một giá trị khác `NULL` nhưng **đối tượng được trỏ đến đã không còn**, và handle đó hoạt động tương đương tham chiếu `null` trong các phép JNI thích hợp.

**Quy tắc quan trọng nhất: không sử dụng đối tượng chỉ vì vừa kiểm tra “weak chưa null”. Hãy tạo một strong reference trước, kiểm tra kết quả, rồi chỉ dùng strong reference đó.**

## 2. Phân biệt ba loại tham chiếu JNI

| Loại JNI | Cách tạo | Có giữ đối tượng khỏi bị GC? | Phạm vi sử dụng và cách giải phóng |
| --- | --- | --- | --- |
| **Local reference** (`jobject`/`jclass`/`jstring`…) | Tham số đối tượng vào native method; kết quả từ phần lớn API JNI; `NewLocalRef` | **Có**, khi còn là local reference hợp lệ | Hợp lệ trong luồng và local JNI frame tương ứng; được dọn khi native method trở về Java; có thể gọi `DeleteLocalRef` sớm |
| **Strong global reference** | `NewGlobalRef` | **Có**, tới khi global reference bị xóa | Có thể giữ qua nhiều native calls và dùng ở các luồng đã gắn với JVM; phải `DeleteGlobalRef` |
| **Weak global reference** (`jweak`) | `NewWeakGlobalRef` | **Không** | Handle sống qua nhiều calls/luồng đến khi `DeleteWeakGlobalRef`, nhưng referent có thể bị GC thu gom bất cứ lúc nào |

**Tham chiếu yếu không phải con trỏ C vào địa chỉ đối tượng cố định.** Đối tượng Java có thể di chuyển khi GC, còn JVM quản lý việc giải mã các handle JNI. Không ép `jweak` thành địa chỉ rồi dereference bằng C/C++.

Ví dụ biểu diễn:

```text
C/C++ giữ jweak W ---------+-------> Java object X
                           |
Java vẫn giữ strong S -----+
                           |
GC: chưa thu gom X khi S còn sống.

Java không còn strong S; X không còn strong roots khác:
GC có thể thu gom X.
W (handle) có thể vẫn tồn tại, nhưng referent đã bị clear.
```

Từ đó rút ra hai khái niệm độc lập:

1. **Handle còn tồn tại hay đã bị xóa:** `W != NULL` chỉ nói biến C có thể đang cất một handle; `DeleteWeakGlobalRef` xử lý vòng đời handle.
2. **Referent Java còn sống hay đã bị thu gom:** chỉ có thể lấy quyền sử dụng ổn định bằng cách **nâng thành strong reference thành công**. Referent có thể mất ngay cả khi biến `W` khác `NULL`.

## 3. Tại sao kiểm tra IsSameObject trước rồi dùng là sai?

JNI cho phép thử:

```c
jboolean gone = (*env)->IsSameObject(env, weak, NULL);
```

Nếu `gone == JNI_TRUE`, weak đã tương đương `null` **vào thời điểm kiểm tra**. Tuy nhiên, kết quả `JNI_FALSE` chỉ phản ánh **một thời điểm**; sau đó GC có thể thu gom đối tượng trước lời gọi JNI kế tiếp.

Mẫu **không an toàn** (giả định `weak` là handle `jweak` vẫn hợp lệ):

```c
/* SAI: tồn tại race với GC giữa hai lời gọi */
if (!(*env)->IsSameObject(env, weak, NULL)) {
    jclass cls = (*env)->GetObjectClass(env, weak);
    /* Tham chiếu có thể đã bị clear trước GetObjectClass. */
}
```

Dòng thời gian:

```text
Luồng native                    Garbage collector
------------                   -----------------
IsSameObject(weak, NULL)
  → JNI_FALSE (đang còn)
                                 Java mất strong root cuối
                                 GC clear weak global
GetObjectClass(weak)
  → không còn referent mạnh
```

**Đây là lỗi check-then-use (TOCTOU):** việc “kiểm tra đang sống” **không giữ đối tượng sống** trong đoạn thời gian tiếp theo.

Ngoài ra, `weak != NULL` là điều kiện còn yếu hơn: handle có thể đã mất referent nhưng giá trị handle chưa được xóa. Không dùng phép so sánh con trỏ C để kết luận đối tượng Java còn sống.

**Cách đúng** là làm thao tác nâng tham chiếu bằng chính JNI:

```c
jobject strong = (*env)->NewLocalRef(env, weak);
if (strong == NULL) {
    /* Referent đã mất (hoặc không lấy được local ref, ví dụ thiếu bộ nhớ).
       Không dùng weak để truy cập đối tượng. */
    return;
}

/* Bây giờ strong là một local reference mạnh. */
jclass cls = (*env)->GetObjectClass(env, strong);
/* Kiểm tra cls/exception và thao tác trên strong theo nhu cầu. */

/* Sau khi sử dụng xong: */
if (cls != NULL) {
    (*env)->DeleteLocalRef(env, cls);
}
(*env)->DeleteLocalRef(env, strong);
```

`NewLocalRef` trả về `NULL` nếu tham chiếu nguồn là `null`, referent của weak đã bị GC, hoặc việc tạo local reference thất bại do thiếu tài nguyên. Tùy lỗi và JVM, cần chú ý exception đang pending; **không luôn diễn giải mọi `NULL` thành “GC đã xảy ra”**.

Nếu `strong != NULL`, chính local reference đó giữ đối tượng còn sống trong khi còn hợp lệ. GC không thể thu gom referent trong lúc một strong reference hợp lệ giữ nó, dù biến `weak` gốc sau đó bị clear hoặc xóa (với điều kiện không có thread khác **xóa handle weak trong lúc chính thao tác nâng đang sử dụng handle đó**; đây là bài toán đồng bộ riêng, xem mục 8).

## 4. Hai kiểu nâng: NewLocalRef và NewGlobalRef

### 4.1. Nâng sang local reference để dùng trong một native call

Thông dụng nhất khi muốn dùng đối tượng **ngay bây giờ**:

```c
jobject strongLocal = (*env)->NewLocalRef(env, weak);
if (strongLocal == NULL) {
    /* Không có đối tượng có thể dùng: trả về hoặc xử lý lỗi. */
    return;
}

/* Chỉ truyền strongLocal, KHÔNG truyền weak, vào các JNI calls tiếp theo. */
(*env)->DeleteLocalRef(env, strongLocal);
```

- `strongLocal` hợp lệ trong luồng JNI hiện tại và local reference frame.
- Nếu nhiều lần lặp tạo local refs, giải phóng ngay bằng `DeleteLocalRef` sau khi dùng để không tăng áp lực lên bảng local references.
- Khi một native method **trả về `jobject`** là local reference, có thể trả thẳng strong local cho Java; JVM chuyển kết quả thành tham chiếu Java thích hợp và dọn local frame theo cơ chế return. **Không xóa local reference trước khi trả về nó.**
- Với thread native **tự attach** qua `AttachCurrentThread`, local references không tự động được dọn theo mỗi lời gọi Java giống một native call thông thường; phải quản lý `DeleteLocalRef`/local frame đúng cách và detach khi hoàn tất.

### 4.2. Nâng sang strong global reference để dùng qua nhiều calls/luồng

Nếu cần giữ Java object sống **qua khoảng thời gian vượt quá local JNI frame**, ví dụ để lưu vào một hàng đợi công việc native, có thể dùng:

```c
jobject strongGlobal = (*env)->NewGlobalRef(env, weak);
if (strongGlobal == NULL) {
    /* Referent đã bị GC, hoặc tạo tham chiếu thất bại. */
    return;
}

/* Native code giữ strongGlobal trong khoảng thời gian cần thiết.
   Khi hoàn thành công việc, dùng JNIEnv của luồng đã attach để xóa: */
(*env)->DeleteGlobalRef(env, strongGlobal);
```

Lưu ý **không gọi DeleteGlobalRef ngay** nếu công việc bất đồng bộ còn cần object. Ngược lại, giữ strong global vô hạn biến cache yếu thành cơ chế giữ đối tượng sống lâu dài, khiến GC không giải phóng được referent.

### So sánh hai lựa chọn

| Tình huống | Nâng phù hợp | Kết thúc vòng đời |
| --- | --- | --- |
| Cần đọc field/gọi method ngay trong native function | `NewLocalRef(weak)` | `DeleteLocalRef` khi xong, hoặc để JNI frame dọn |
| Cần trả object cho Java caller | `NewLocalRef(weak)` rồi `return strongLocal` | Java quản lý tham chiếu kết quả; không xóa trước `return` |
| Native worker cần giữ object đến lúc job kết thúc | `NewGlobalRef(weak)` | `DeleteGlobalRef` khi job xong |
| Muốn lưu cache nhưng cho phép GC lấy lại object | `NewWeakGlobalRef` | `DeleteWeakGlobalRef` khi xóa mục cache |
| Chỉ kiểm tra `IsSameObject(weak,NULL)` rồi gọi trên weak | **Không phù hợp** | Dùng thao tác nâng trực tiếp |

## 5. Ví dụ đầy đủ Java 17+ / JNI C: lưu jweak, nâng an toàn, giải phóng

Ví dụ tạo một cache **một slot**, lưu duy nhất một weak global reference. API gồm:

- `store(Object)`: tạo weak global reference và thay thế handle cũ.
- `get()`: dùng `NewLocalRef` để **nâng sang strong local** và trả object cho Java, hoặc trả `null` khi không thể nâng.
- `dispose()`: xóa handle weak và đặt biến C về `NULL`.

Ba phương thức Java khai báo `static synchronized native` để các lời gọi tới slot native này **không chồng lấn nhau** khi cùng đi qua lớp Java đó. Mẫu này giả định không có native worker khác tự truy cập biến C `saved` bên ngoài ba phương thức; khi mở rộng sang các native threads phải dùng cơ chế đồng bộ ở phía native (mục 8).

### 5.1. Tệp src/demo/jni/WeakGlobalCache.java

```java
package demo.jni;

public final class WeakGlobalCache {
    static {
        System.loadLibrary("weakglobalcache");
    }

    public static synchronized native void store(Object value);
    public static synchronized native Object get();
    public static synchronized native void dispose();

    public static void main(String[] args) {
        Object keepAlive = new Object();

        store(keepAlive);
        Object strong = get();

        System.out.println("Same object: " + (strong == keepAlive));

        dispose();
        System.out.println("Empty slot: " + (get() == null));
    }
}
```

Điểm kiểm soát cho kết quả xác định: biến Java `keepAlive` vẫn là strong reference ở thời điểm so sánh `strong == keepAlive`. Vì vậy ví dụ **không dựa vào việc GC có chạy hay không** để đưa ra stdout. `dispose()` xóa handle cache; nó **không** gọi GC và không phá các strong reference Java `keepAlive`/`strong`.

### 5.2. Biên dịch Java và tạo header JNI

Trên Linux hoặc macOS, từ thư mục gốc dự án:

```bash
mkdir -p build/classes build/include build/native

javac -h build/include \
  -d build/classes \
  src/demo/jni/WeakGlobalCache.java
```

Kết quả tạo `build/classes/demo/jni/WeakGlobalCache.class` và `build/include/demo_jni_WeakGlobalCache.h`.

Header quan trọng (rút gọn những dòng comment và include guards do `javac` tạo):

```c
#include <jni.h>

JNIEXPORT void JNICALL Java_demo_jni_WeakGlobalCache_store
  (JNIEnv *, jclass, jobject);

JNIEXPORT jobject JNICALL Java_demo_jni_WeakGlobalCache_get
  (JNIEnv *, jclass);

JNIEXPORT void JNICALL Java_demo_jni_WeakGlobalCache_dispose
  (JNIEnv *, jclass);
```

Các prototype trên đã được kiểm tra bằng `javac -h` trên JDK 24. Từ khóa `synchronized` thuộc cơ chế khóa của Java, không làm thay đổi tên ký hiệu JNI và không thêm tham số JNI. Tham số thứ hai là `jclass` vì ba native methods đều `static`.

### 5.3. Tệp WeakGlobalCache.c

```c
#include <jni.h>
#include "demo_jni_WeakGlobalCache.h"

/* Handle yếu tồn tại qua nhiều lần gọi JNI.
   Mọi truy cập trong ví dụ đều qua các synchronized static native methods. */
static jweak saved = NULL;

JNIEXPORT void JNICALL Java_demo_jni_WeakGlobalCache_store(
        JNIEnv *env, jclass cls, jobject value) {
    (void) cls;

    jweak fresh = NULL;

    if (value != NULL) {
        fresh = (*env)->NewWeakGlobalRef(env, value);
        if (fresh == NULL) {
            /* Với đối số Java non-null vẫn còn strong ở native call,
               thất bại thường do thiếu bộ nhớ; không xóa handle cũ.
               JVM đã phát sinh exception nếu NewWeakGlobalRef hết bộ nhớ. */
            return;
        }
    }

    /* Chỉ thay slot sau khi đã tạo weak handle mới thành công. */
    if (saved != NULL) {
        (*env)->DeleteWeakGlobalRef(env, saved);
    }
    saved = fresh;
}

JNIEXPORT jobject JNICALL Java_demo_jni_WeakGlobalCache_get(
        JNIEnv *env, jclass cls) {
    (void) cls;

    if (saved == NULL) {
        return NULL;
    }

    /* Thao tác quan trọng: lấy strong local, không dùng trực tiếp jweak. */
    return (*env)->NewLocalRef(env, saved);
}

JNIEXPORT void JNICALL Java_demo_jni_WeakGlobalCache_dispose(
        JNIEnv *env, jclass cls) {
    (void) cls;

    if (saved != NULL) {
        (*env)->DeleteWeakGlobalRef(env, saved);
        saved = NULL;
    }
}
```

Giải thích vòng đời:

1. Tham số `value` truyền từ Java là local reference hợp lệ trong native call, giúp referent sống trong lúc `NewWeakGlobalRef` tạo handle.
2. `saved` là `jweak` có thời gian sống vượt quá lời gọi `store`. Nhưng `saved` **không khiến referent sống** sau khi các strong roots khác mất.
3. `get` trả `NewLocalRef(env, saved)`; khi thành công, kết quả là strong local và có thể được Java giữ bằng biến `strong`.
4. Nếu referent đã bị GC, việc nâng có thể trả `NULL` và Java nhận `null`. Nếu thiếu tài nguyên hoặc có pending exception, phải xử lý lỗi tương ứng; ví dụ đơn giản không cố phân loại mọi nguyên nhân `NULL`.
5. `dispose` gọi **đúng hàm `DeleteWeakGlobalRef`** rồi gán `saved = NULL` để không tái sử dụng handle đã bị giải phóng.
6. `store(null)` cũng xóa slot cũ và lưu `NULL`, vì không cần tạo weak handle cho `null`.

Tại sao `store` tạo `fresh` **trước khi xóa `saved`**? Nếu `NewWeakGlobalRef` thất bại, cache cũ vẫn giữ được handle yếu hợp lệ; không làm mất trạng thái vì lỗi cấp phát. Dù referent cũ đã bị GC, handle cũ vẫn cần được xóa khi thay cache.

### 5.4. Biên dịch shared library trên Linux

Cần JDK 17+ và GCC. Biến `JAVA_HOME` phải là thư mục JDK chứa `include/jni.h`:

```bash
gcc -std=c11 -O2 -fPIC -shared \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  -Ibuild/include \
  -o build/native/libweakglobalcache.so \
  WeakGlobalCache.c

java -Djava.library.path=build/native \
  -cp build/classes \
  demo.jni.WeakGlobalCache
```

**Stdout chính xác khi biên dịch và nạp thư viện thành công:**

```text
Same object: true
Empty slot: true
```

Nếu hệ thống JDK mới bật cảnh báo native access, có thể có **cảnh báo trên stderr** nhưng hai dòng stdout trên không thay đổi. Tuỳ phiên bản JDK, chương trình ở classpath có thể cần tham số `--enable-native-access=ALL-UNNAMED` khi chạy. Không thêm tham số đó một cách mù quáng vào mọi bản JDK.

### 5.5. macOS và Windows

**macOS** (sau khi chạy cùng lệnh `javac -h`; có Clang và `JAVA_HOME` hợp lệ):

```bash
clang -O2 -dynamiclib \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/darwin" \
  -Ibuild/include \
  -o build/native/libweakglobalcache.dylib \
  WeakGlobalCache.c

java -Djava.library.path=build/native \
  -cp build/classes \
  demo.jni.WeakGlobalCache
```

**Windows**, trong Visual Studio Developer Command Prompt (có `cl`, JDK, `JAVA_HOME`):

```bat
mkdir build\classes
mkdir build\include
mkdir build\native

javac -h build\include -d build\classes src\demo\jni\WeakGlobalCache.java

cl /LD /I"%JAVA_HOME%\include" /I"%JAVA_HOME%\include\win32" /I"build\include" WeakGlobalCache.c /Febuild\native\weakglobalcache.dll

java -Djava.library.path=build\native -cp build\classes demo.jni.WeakGlobalCache
```

Các nền tảng dùng shared library tương ứng `.so`, `.dylib` hoặc `.dll`. `System.loadLibrary("weakglobalcache")` chỉ cần tên logic; JVM ánh xạ theo hệ điều hành. **JDK và compiler native cần cùng kiến trúc** (x64, ARM64, v.v.). Cần điều chỉnh quyền file và cấu hình thư viện động của OS nếu môi trường triển khai khác.

## 6. GC có thể xảy ra lúc nào? Vì sao không kiểm thử bằng System.gc()?

Ví dụ hoạt động giống nhau nếu GC không chạy, chạy một lần hay nhiều lần. Đây là điểm chủ động của thiết kế.

Khi không còn strong reference Java hoặc JNI nào giữ đối tượng (và không còn các nguồn giữ sống khác), GC **có thể** thu gom referent của `jweak`. Tuy nhiên:

- `System.gc()` chỉ là **yêu cầu/gợi ý** cho runtime; thời điểm xử lý và việc có chạy một GC thu gom đối tượng mục tiêu hay không **không được bảo đảm**.
- JVM có thể còn những strong roots khác: biến Java đang sống, static field, JNI local/global ref, object được giữ bởi một cấu trúc khác.
- Sau `NewLocalRef` thành công, chính strong local mới đảm bảo referent sống trong khoảng thời gian sử dụng; không được suy luận thời điểm thu gom chỉ từ số lần gọi GC.
- Nếu tất cả strong references đã mất, `get()` **có thể** trả object hoặc `null`, tùy GC đã thu gom hay chưa; không có cam kết “ngay sau `System.gc()` thì phải `null`”.

Thử nghiệm bổ sung (chỉ là **đoạn minh họa**, đặt vào một đoạn mã Java có quyền gọi các native methods của lớp `WeakGlobalCache`):

```java
store(new Object());  // Không giữ đối tượng bằng biến Java.
System.gc();          // Không bắt buộc GC thu gom đối tượng ngay lúc này.

Object snapshot = get(); // Cố nâng atomically qua NewLocalRef ở JNI.
System.out.println(snapshot == null
        ? "Không còn referent có thể nâng"
        : "Đã nâng thành strong reference");

dispose();            // Giải phóng weak handle.
```

Hai dòng chuỗi trong nhánh `println` là **hai khả năng khác nhau**, không có output cố định. Nếu `snapshot != null` thì Java giữ một strong reference, giúp object không bị thu gom trong lúc biến này còn thực sự được dùng.

`jweak` được xử lý theo quy tắc reachability/GC của JNI. **Đừng đồng nhất hoàn toàn** `jweak` với `java.lang.ref.WeakReference` hoặc giả định thứ tự clear giống nhau trên mọi phiên bản JVM. Điều quan trọng cho mã JNI đúng là: GC có quyền clear referent của `jweak`, và việc nâng bằng `NewLocalRef`/`NewGlobalRef` là ranh giới bảo vệ trước khi truy cập.

## 7. Quản lý vòng đời handle và bộ nhớ

### Tạo, thay thế và xóa yếu đúng cách

- Gọi `NewWeakGlobalRef` để tạo một handle yếu **mới**. Mỗi lần tạo thành công phải có một đường giải phóng bằng `DeleteWeakGlobalRef`.
- Một `jweak` có thể đã **clear referent** nhưng vẫn có handle do native lưu giữ. **Vẫn phải xóa handle ấy** khi không dùng nữa.
- Không truyền handle yếu vào `DeleteGlobalRef`; loại handle nào phải được giải phóng bằng **API tương ứng**.
- Sau `DeleteWeakGlobalRef`, giá trị handle cũ không được tiếp tục sử dụng. Đặt biến/slot về `NULL`, hoặc loại bỏ nó khỏi cấu trúc dữ liệu cache.
- Không gọi `DeleteWeakGlobalRef` khi một luồng khác có thể đang dùng chính handle đó để gọi `NewLocalRef`; phải đồng bộ toàn bộ thao tác với slot.
- Khi thay handle, tạo handle mới trước và chỉ xóa handle cũ sau khi thành công, trừ khi thiết kế cố ý xóa cache ngay cả khi cấp phát thất bại.

### Thời gian sống của strong sau khi nâng

```text
jweak W còn tồn tại ------------------------------> DeleteWeakGlobalRef(W)
       |
       | NewLocalRef(W) thành công
       v
jobject strong S =================> DeleteLocalRef(S)
     referent chắc chắn còn sống
     trong quãng thời gian S hợp lệ
```

Phần `====` biểu thị khoảng thời gian **có strong reference**. Việc xóa `W` trong khi `S` vẫn hợp lệ **không** làm `S` yếu đi. Ngược lại, xóa `S` không tự xóa `W`; hai handle quản lý vòng đời độc lập.

Khi một native method trả `S` làm `jobject` cho Java, local reference kết thúc theo JNI frame, nhưng **giá trị object trả về vẫn là tham chiếu mạnh ở phía Java** nếu được nhận và dùng. Không nhầm thao tác dọn local frame với việc “Java object bị hủy”.

### Khi tham chiếu bị lỗi cấp phát

Các hàm tạo reference như `NewWeakGlobalRef`/`NewGlobalRef`/`NewLocalRef` có thể trả `NULL` khi tài nguyên không đủ. `NewWeakGlobalRef` có thể ném `OutOfMemoryError`. Trong mã native, nếu có pending exception, tránh tiếp tục gọi tùy tiện các JNI APIs khác; hãy trả về để Java xử lý hoặc xử lý exception bằng các API cho phép. Không dùng `NULL` làm bằng chứng duy nhất rằng referent đã bị GC.

## 8. An toàn đa luồng: race GC khác race xóa handle

Có **hai loại race độc lập** cần xử lý.

### Race A — GC clear referent

Đối tượng có thể bị thu gom giữa `IsSameObject` và lời gọi JNI kế tiếp. Đây là **race với GC**, được giải bằng **`NewLocalRef(weak)` hoặc `NewGlobalRef(weak)`**, tức thao tác lấy strong reference trước khi dùng.

### Race B — Thread khác xóa hoặc thay handle

Giả sử luồng A đọc `jweak W` từ cache, trong khi luồng B gọi `DeleteWeakGlobalRef(W)`. Nếu A sau đó đưa handle **đã bị xóa** vào `NewLocalRef`, JNI handle không còn hợp lệ. Nâng lên strong không thể sửa một handle đã bị giải phóng trước khi nâng.

Mô hình cần thiết:

```text
Thread A (get)              Thread B (dispose/store)
-----------------           -----------------------
lock(slot)
  lấy W còn hợp lệ          đợi lock(slot)
  S = NewLocalRef(W)
unlock(slot)
                             lock(slot)
                               DeleteWeakGlobalRef(W)
                             unlock(slot)
dùng S (strong)
DeleteLocalRef(S)
```

Đồng bộ chỉ cần bảo vệ **quyền sử dụng handle W** trong lúc lấy strong; sau khi đã lấy được `S`, A có thể dùng `S` độc lập với việc B xóa `W`. Tùy thiết kế, lock có thể là mutex native, monitor Java được tuân thủ ở mọi đường truy cập, hoặc cơ chế đồng bộ tương đương.

Trong chương trình mẫu, tất cả truy cập `saved` đều nằm trong **ba phương thức `static synchronized native` của cùng một lớp**. Java cấp monitor của đối tượng `Class` khi vào mỗi phương thức, nên các lời gọi đi qua đúng lớp đó được tuần tự hóa. **Nếu native worker khác tự đọc/xóa `saved` trực tiếp, monitor Java không tự bảo vệ worker ấy**; hãy chuyển sang mutex hoặc cách đồng bộ rõ ràng và không giữ mutex trong những lời gọi callback có nguy cơ deadlock.

Một số lưu ý khác:

- `jweak` và strong global có thể lưu qua threads, **nhưng `JNIEnv*` chỉ hợp lệ cho thread sở hữu nó**. Không lưu `JNIEnv*` để tái sử dụng từ thread khác.
- Native thread cần gọi `AttachCurrentThread` để lấy `JNIEnv*` của chính thread đó, rồi quản lý tài nguyên và `DetachCurrentThread` khi thích hợp.
- Local reference tạo từ `NewLocalRef` phải được dùng/giải phóng trong đúng thread và frame; không chuyển `jobject` local sang thread khác để dùng sau khi frame kết thúc.
- Khi cần truyền object cho worker khác, tạo strong global trong thread hiện tại trong lúc local strong còn hợp lệ; worker có `JNIEnv*` riêng và giải phóng strong global sau khi xong việc.

## 9. Weak global reference trong callback, cache class và class unloading

**Callback Java:** thư viện native muốn lưu đối tượng listener nhưng không muốn cản listener bị thu gom. Lưu `jweak` của listener; mỗi khi phát sự kiện, dùng `NewLocalRef` để lấy listener mạnh. Nếu nhận `NULL` thì bỏ qua callback hoặc dọn slot cache; nếu thành công, gọi method qua strong, kiểm tra JNI exception và giải phóng local strong sau callback.

**Cache class:** `jclass` cũng là một JNI reference tới đối tượng `java.lang.Class`. Nếu muốn cache yếu để không vô tình giữ class/class loader sống mãi, lưu một `jweak` của class và **nâng thành `jclass` local hợp lệ** trước khi sử dụng `GetMethodID`, `GetStaticMethodID` hoặc các API liên quan. Không giữ một `jclass` local từ lần gọi JNI trước để dùng trong callback về sau.

**Class unloading:** khi class/class loader có thể bị gỡ, những cache khác gắn với class như `jmethodID` và `jfieldID` cần được quản lý theo vòng đời class. Một weak global class đã clear không bảo đảm ID đã cache còn dùng được trong mọi hoàn cảnh. Khi thiết kế plugin/module được nạp lại, phải có chiến lược làm mới cả class handle và metadata tương ứng.

**Native cache không tự phải giống Java WeakHashMap:** `jweak` là primitive dùng để xây dựng cache; nó không tự xóa entry khỏi `std::unordered_map`/map C hay callback table. Hãy có chính sách kiểm tra và loại bỏ entry có referent đã clear, tránh để cache chứa rất nhiều weak handles không còn giá trị.

## 10. Các lỗi phổ biến và cách sửa

| Sai lầm | Vì sao nguy hiểm | Cách làm đúng |
| --- | --- | --- |
| `if (weak != NULL) GetObjectClass(weak)` | Handle còn, referent có thể đã mất | `strong = NewLocalRef(weak)` rồi chỉ dùng `strong` |
| `!IsSameObject(weak,NULL)` rồi `CallObjectMethod(weak,...)` | GC có thể chạy giữa check và use | Dùng một thao tác nâng strong thay vì check trước |
| Lưu local `jobject` trong biến `static` qua nhiều native calls | Local reference hết hiệu lực khi frame cũ kết thúc | Tạo `NewWeakGlobalRef` hoặc `NewGlobalRef` theo nhu cầu |
| Tạo `NewGlobalRef` để “cache yếu” | Strong global ngăn referent bị GC | Dùng `NewWeakGlobalRef` nếu muốn cho phép GC |
| Giữ strong global mãi sau khi job kết thúc | Giữ object sống quá lâu, rò rỉ reference | `DeleteGlobalRef` theo vòng đời công việc |
| GC clear weak nên bỏ qua `DeleteWeakGlobalRef` | Handle JNI vẫn chiếm tài nguyên | Xóa handle yếu khi cache/owner kết thúc |
| Gọi `DeleteLocalRef(strong)` rồi tiếp tục dùng `strong` | Use-after-delete JNI reference | Không dùng sau xóa; trả về trước khi frame dọn |
| Native thread A xóa weak khi B đang nâng | Sử dụng handle đã bị giải phóng | Đồng bộ thao tác đọc/nâng/thay/xóa handle |
| Chia sẻ `JNIEnv*` qua threads | `JNIEnv*` gắn với thread | Mỗi thread phải lấy `JNIEnv*` riêng |
| Dùng `System.gc()` để assert weak đã clear | GC không đảm bảo xảy ra đúng thời điểm | Viết kiểm thử xác định cho API; không giả định thời điểm GC |
| Bất kỳ `NULL` từ `NewLocalRef` đều kết luận “đã bị GC” | Có thể còn nguyên nhân thiếu tài nguyên/exception | Kiểm tra ngữ cảnh và pending exceptions |

## 11. Quy trình áp dụng trong code review

Khi đọc JNI code có `jweak`, hãy kiểm tra theo thứ tự:

1. **Nguồn:** `jweak` được tạo từ một reference JNI hợp lệ với `NewWeakGlobalRef` chưa? Có xử lý `NULL`/exception và bảo toàn cache cũ khi cấp phát thất bại không?
2. **Vòng đời handle:** ai sở hữu `jweak`? Khi nào gọi `DeleteWeakGlobalRef`? Có thể xóa hai lần, rò rỉ, hoặc dùng sau xóa không?
3. **Bảo vệ GC:** mọi lần định dùng referent có gọi `NewLocalRef`/`NewGlobalRef` **trước** khi dùng không? Có đoạn code nào chỉ dựa vào `IsSameObject` hoặc `weak != NULL` không?
4. **Vòng đời strong:** nếu nâng thành công, strong có được dùng rồi giải phóng đúng lúc không? Nếu trả local ref về Java, có tránh xóa trước khi return không?
5. **Luồng:** ai có quyền đọc/thay/xóa weak slot? Thao tác tạo strong có được đồng bộ với thao tác xóa/thay weak handle không? Native threads có `JNIEnv*` riêng không?
6. **Lỗi:** hành vi khi `NewLocalRef` trả `NULL` là gì? Có bỏ qua exception quan trọng hoặc sử dụng referent khi chưa có strong không?
7. **Bài kiểm thử:** có kiểm tra đúng kết quả lúc referent chắc chắn còn sống, xóa handle theo API và callback/worker không tạo use-after-delete không?

Một review tốt phải kiểm tra **cả race GC và race vòng đời handle**. Có `NewLocalRef` mà không đồng bộ với `DeleteWeakGlobalRef` ở thread khác vẫn chưa đủ an toàn.

## 12. Bài tập tự kiểm tra

**Câu 1.** Native cache chứa `jweak w` khác `NULL`. Có thể kết luận đối tượng Java tồn tại không?

**Đáp án:** Không. `w != NULL` chỉ là trạng thái của handle phía C. Referent có thể đã được GC clear. Cần nâng bằng `NewLocalRef`/`NewGlobalRef` để nhận strong reference nếu còn.

**Câu 2.** `IsSameObject(w,NULL)` trả `JNI_FALSE`. Đủ an toàn để gọi `GetObjectClass(env,w)` ngay sau đó chứ?

**Đáp án:** Không. GC có thể clear referent giữa hai thao tác. Dùng `jobject local = NewLocalRef(env,w)` và chỉ dùng `local` nếu khác `NULL`.

**Câu 3.** `NewLocalRef(w)` thành công, rồi một thao tác khác xóa weak handle `w`. Object có thể bị GC khi `local` còn hợp lệ không?

**Đáp án:** Không thể thu gom object chỉ do xóa `w` khi `local` vẫn là strong reference hợp lệ. Tuy nhiên, bản thân thao tác **xóa weak handle không được chạy đồng thời với việc sử dụng handle ấy để nâng** nếu chưa đồng bộ.

**Câu 4.** Muốn native worker giữ object qua nhiều callbacks sau khi native method ban đầu trả về, nên lưu `jobject` local hay global?

**Đáp án:** Tạo một **strong global reference** khi còn một strong reference hợp lệ, giao handle global vào cấu trúc công việc đã đồng bộ, và `DeleteGlobalRef` khi job kết thúc. Không lưu local reference sau frame. Nếu không cần đảm bảo object còn sống, cache có thể giữ `jweak` và nâng mỗi lần sử dụng.

**Câu 5.** GC đã clear referent của `jweak`. Có cần `DeleteWeakGlobalRef`?

**Đáp án:** Có. GC clear referent không tự giải phóng handle phía native; xóa đúng API khi owner xóa slot/cache.

**Câu 6.** Vì sao chương trình mẫu in `Same object: true` ngay cả khi GC đang hoạt động?

**Đáp án:** Biến Java `keepAlive` còn giữ object sống tại thời điểm kiểm tra; `get()` nâng thành strong local và trả về Java. Kết quả phép `==` so sánh cùng object, không phụ thuộc lịch GC.

## Tài liệu tham khảo chính thức

- [JNI Specification — Weak Global References, NewWeakGlobalRef, DeleteWeakGlobalRef](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/functions.html#weak-global-references)
- [JNI Specification — NewLocalRef và NewGlobalRef](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/functions.html#global-and-local-references)
- [JNI Specification — Local and Global References (Design Overview)](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/design.html#global-and-local-references)
- [Oracle Java SE — java.lang.ref package](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/package-summary.html)
- [Android NDK — JNI tips: local/global references, thread-specific JNIEnv](https://developer.android.com/ndk/guides/jni-tips)

**Ghi nhớ:** `jweak` chỉ lưu khả năng **thử lấy lại** object, không đảm bảo object còn sống. `NewLocalRef`/`NewGlobalRef` thành công mới tạo khoảng thời gian **strong reachability** để dùng an toàn; đồng thời phải bảo vệ handle weak khỏi bị xóa/thay bởi thread khác trong lúc thực hiện thao tác nâng.
