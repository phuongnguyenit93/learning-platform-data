# Dùng `-Xcheck:jni` để phát hiện vi phạm hợp đồng JNI

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích vì sao lỗi ở biên Java ↔ mã native (C/C++) có thể gây cảnh báo, sai dữ liệu hoặc làm JVM dừng đột ngột.
- Bật `-Xcheck:jni` khi chạy ứng dụng Java có dùng Java Native Interface (JNI), rồi đọc và phân loại chẩn đoán.
- Nhận diện các nhóm lỗi mà cơ chế kiểm tra bổ sung của HotSpot có thể phát hiện: tham chiếu JNI không hợp lệ, dùng `JNIEnv*` sai luồng, ID/phạm vi tham số sai, cặp `Get...`/`Release...` không khớp, bỏ qua kiểm tra ngoại lệ và lạm dụng vùng critical.
- Tái hiện một cảnh báo bằng ví dụ Java 17 + C, sửa lỗi và xác nhận cảnh báo biến mất.
- Biết giới hạn của tùy chọn: chương trình chạy sạch với `-Xcheck:jni` vẫn chưa được chứng minh an toàn tuyệt đối.

Bối cảnh: bài tập dùng cách triển khai JNI của HotSpot/OpenJDK, với JDK 17 trở lên. Chi tiết thông báo có thể khác giữa phiên bản hoặc nhà cung cấp JVM.

## 1. `-Xcheck:jni` thực chất làm gì?

JNI cho phép Java gọi hàm native và mã native gọi ngược vào JVM qua `JNIEnv*`. API này có **hợp đồng**: đối tượng/tham chiếu phải còn hợp lệ; `jmethodID` và `jfieldID` phải phù hợp với lớp, kiểu và loại lời gọi; một số con trỏ do JVM cấp phải được trả lại đúng cách; ngoại lệ đang chờ xử lý ảnh hưởng đến các lệnh JNI được phép gọi tiếp.

Mã C/C++ không tự động nhận mức bảo vệ bộ nhớ như Java. Một lỗi JNI có thể chỉ biểu hiện khi GC chạy, khi đổi luồng, hoặc sau rất nhiều lần gọi. Chạy JVM với:

```bash
java -Xcheck:jni -cp . Main
```

sẽ yêu cầu HotSpot thực hiện **kiểm tra bổ sung đối với các lời gọi JNI**. Đây là công cụ chẩn đoán lúc chạy; nó không sửa mã native và không thay thế compiler, sanitizer hay kiểm thử nghiệp vụ. Tùy chọn được đặt **khi khởi động JVM**. Nó có overhead nên thường bật trong phát triển, kiểm thử tích hợp hoặc môi trường tái hiện lỗi, thay vì mặc định cho toàn bộ lưu lượng production.

Ví dụ đối với một ứng dụng đóng gói JAR:

```bash
java -Xcheck:jni -jar app.jar
```

Phải bảo đảm đúng tiến trình JVM có nạp thư viện native nhận được cờ này: nếu chạy qua IDE, test runner, service launcher hoặc script, hãy đặt nó vào **VM options/JVM arguments**, không truyền như tham số `main(String[] args)`.

## 2. Những nhóm vi phạm có thể bị phát hiện

| Nhóm | Ví dụ sai | Vì sao nguy hiểm | Mức chẩn đoán thường gặp trên HotSpot |
| --- | --- | --- | --- |
| `JNIEnv*` và luồng | Dùng `JNIEnv*` lấy trên luồng A để gọi JNI ở luồng B; dùng từ luồng native chưa attach | `JNIEnv*` gắn với ngữ cảnh luồng JVM | Lỗi nghiêm trọng, JVM có thể kết thúc |
| Tham chiếu JNI | Dùng local reference đã xóa, tham chiếu không hợp lệ hoặc sai loại đối tượng | JVM không còn cách diễn giải đối tượng một cách hợp lệ | Lỗi nghiêm trọng |
| Method/field ID | Truyền `jmethodID` sai lớp, sai kiểu phương thức, nhầm static/instance; dùng `jfieldID` không tương thích | Lời gọi hoặc truy cập trường vi phạm metadata của JVM | Lỗi nghiêm trọng |
| Đối số JNI | `NULL` tại vị trí không cho phép, chỉ số mảng ngoài phạm vi, tham số khác kiểu | Truy cập sai vùng dữ liệu hoặc sai hợp đồng API | Lỗi nghiêm trọng |
| Cặp lấy/trả tài nguyên | Gọi `Release...` với con trỏ không được cấp từ `Get...` tương ứng | Vi phạm quyền sở hữu/vòng đời bộ nhớ do JVM quản lý | Lỗi nghiêm trọng khi được phát hiện |
| Kiểm tra ngoại lệ | Sau `Call...Method` gọi tiếp JNI không an toàn mà chưa kiểm tra khả năng có Java exception | Ngoại lệ đang chờ có thể làm những lệnh sau không hợp lệ | Thường là **WARNING** |
| Vùng critical | Gọi hàm JNI khác giữa `GetPrimitiveArrayCritical` và `ReleasePrimitiveArrayCritical`, hoặc giữa `GetStringCritical` và `ReleaseStringCritical` | Có thể ảnh hưởng GC, kéo dài vùng khóa/pin và gây deadlock | Thường là **WARNING** |
| Local reference quá nhiều | Tạo nhiều local ref mà không giải phóng hoặc cấp đủ capacity | Tăng áp lực tài nguyên native/JVM | Có thể là **WARNING** |

Đây là **các khả năng kiểm tra**, không phải cam kết mọi lần vi phạm đều được phát hiện. Một số cảnh báo mang tính phòng ngừa; các lỗi nghiêm trọng như tham chiếu hỏng, ID sai hoặc tham số bất hợp lệ có thể khiến JVM dừng ngay.

### Đọc đúng hai loại kết quả

**WARNING**: HotSpot phát hiện cách dùng JNI đáng nghi, ví dụ thiếu kiểm tra ngoại lệ sau một lời gọi Java. Chương trình có thể tiếp tục và hoàn thành, nhưng vẫn phải xem lại code native. Thông điệp và stack trace chỉ ra thời điểm chẩn đoán, chưa chắc chính là câu lệnh đầu tiên gây lỗi.

**FATAL ERROR**: HotSpot phát hiện vi phạm nghiêm trọng; JVM có thể in thông tin luồng/stack trace, tạo crash log như `hs_err_pid<PID>.log` và kết thúc. Đừng thiết kế code dựa vào việc `try/catch` Java sẽ bắt được lỗi cấp JVM này. Việc không thấy `FATAL ERROR` cũng không xác nhận native code đúng.

## 3. Lab: tạo một cảnh báo rồi sửa

Ví dụ cố ý bỏ qua bước kiểm tra ngoại lệ sau khi mã C gọi một phương thức Java. Callback thực tế chạy thành công, nhưng JNI vẫn yêu cầu native code kiểm tra khả năng ngoại lệ trước khi tiếp tục gọi một JNI operation không an toàn. Đây là cách quan sát một **WARNING** mà không cần cố ý truyền tham chiếu hỏng để làm crash JVM.

**Điều kiện:** Linux, JDK 17+ gồm `java`, `javac` và header `jni.h`, cùng compiler C (`cc` hoặc `gcc`). Thiết lập `JAVA_HOME` trỏ tới thư mục JDK, ví dụ `/opt/jdk-17`. Tạo hai tệp sau trong cùng một thư mục trống.

**Tệp `JniCheckDemo.java`:**

```java
public final class JniCheckDemo {
    static {
        System.loadLibrary("jnicheckdemo");
    }

    private static native void runNative();

    private static void callback() {
        System.out.println("Callback OK");
    }

    public static void main(String[] args) {
        runNative();
        System.out.println("Completed");
    }
}
```

**Tệp `jnicheckdemo.c`, phiên bản cố ý thiếu kiểm tra:**

```c
#include <jni.h>
#include "JniCheckDemo.h"

JNIEXPORT void JNICALL Java_JniCheckDemo_runNative(JNIEnv *env, jclass cls) {
    jmethodID callback = (*env)->GetStaticMethodID(
        env, cls, "callback", "()V");
    if (callback == NULL) {
        return; /* Tra cuu that bai: de exception propagates ve Java. */
    }

    (*env)->CallStaticVoidMethod(env, cls, callback);

    /* LOI: chua kiem tra exception sau CallStaticVoidMethod. */
    jclass stringClass = (*env)->FindClass(env, "java/lang/String");
    if (stringClass != NULL) {
        (*env)->DeleteLocalRef(env, stringClass);
    }
}
```

Biên dịch trên Linux, từ thư mục chứa hai tệp:

```bash
javac -h . JniCheckDemo.java
cc -shared -fPIC -I"$JAVA_HOME/include" -I"$JAVA_HOME/include/linux" jnicheckdemo.c -o libjnicheckdemo.so
java -Xcheck:jni -Djava.library.path=. JniCheckDemo
```

`javac -h .` tạo file header `JniCheckDemo.h` với khai báo hàm native đúng tên JNI. Compiler tạo `libjnicheckdemo.so` để `System.loadLibrary("jnicheckdemo")` tìm được qua `java.library.path`. Đổi tên native method, tên lớp hoặc package thì phải tạo lại header và dùng đúng tên hàm được sinh ra.

Các dòng **do ứng dụng in** khi callback hoạt động bình thường:

```text
Callback OK
Completed
```

Với HotSpot và `-Xcheck:jni`, giữa/cạnh những dòng trên có thể xuất hiện cảnh báo tương tự:

```text
WARNING in native method: JNI call made without checking exceptions when required to from CallStaticVoidMethod
```

Thông điệp thực tế có thể kèm stack trace và khác đôi chút theo build/JDK; thứ tự khi gộp stdout với stderr cũng có thể khác. Chú ý: callback **không ném exception** vẫn có thể có cảnh báo, vì vấn đề là native code đã bỏ qua **thao tác kiểm tra khả năng xảy ra exception**.

### Sửa đúng

Thay nội dung `jnicheckdemo.c` bằng phiên bản hoàn chỉnh:

```c
#include <jni.h>
#include "JniCheckDemo.h"

JNIEXPORT void JNICALL Java_JniCheckDemo_runNative(JNIEnv *env, jclass cls) {
    jmethodID callback = (*env)->GetStaticMethodID(
        env, cls, "callback", "()V");
    if (callback == NULL) {
        return; /* Neu co NoSuchMethodError, cho exception propagates. */
    }

    (*env)->CallStaticVoidMethod(env, cls, callback);
    if ((*env)->ExceptionCheck(env)) {
        return; /* De exception dang cho duoc nem ve Java. */
    }

    jclass stringClass = (*env)->FindClass(env, "java/lang/String");
    if (stringClass == NULL) {
        return; /* Neu co exception, cho JVM propagates. */
    }
    (*env)->DeleteLocalRef(env, stringClass);
}
```

Biên dịch lại thư viện native (không cần đổi Java code) và chạy lại:

```bash
cc -shared -fPIC -I"$JAVA_HOME/include" -I"$JAVA_HOME/include/linux" jnicheckdemo.c -o libjnicheckdemo.so
java -Xcheck:jni -Djava.library.path=. JniCheckDemo
```

Kỳ vọng: chương trình vẫn in `Callback OK` và `Completed`; cảnh báo **thiếu kiểm tra exception sau `CallStaticVoidMethod`** không còn xuất hiện. `ExceptionCheck` chỉ kiểm tra trạng thái; nếu Java callback ném exception thì trả về native method để exception được truyền về Java, không được tự ý gọi tiếp các hàm JNI tùy ý khi exception còn pending.

**Lưu ý nền tảng khác:** macOS dùng thư mục header `include/darwin` và thông thường build thư viện `libjnicheckdemo.dylib` bằng `clang -dynamiclib`; Windows dùng `include/win32` và thư viện `jnicheckdemo.dll` (ví dụ biên dịch bằng MSVC). Lệnh `cc` phía trên được viết cụ thể cho Linux, không nên sao chép nguyên xi sang Windows.

## 4. Quy tắc sửa lỗi theo nhóm

### 4.1. Local/global reference và vòng đời

- Local reference (như kết quả `FindClass`) thông thường có hiệu lực trong phạm vi native invocation hiện tại và được JVM giải phóng khi hàm native kết thúc. Nếu tạo nhiều trong vòng lặp dài, hãy `DeleteLocalRef` ở từng lượt hoặc quản lý local frame với `PushLocalFrame`/`PopLocalFrame`.
- Không giữ local reference trong biến static/native cache để dùng sau khi native method đã trở về Java. Nếu cần giữ đối tượng lâu hơn hoặc qua lời gọi/luồng thích hợp, tạo `NewGlobalRef` và giải phóng bằng `DeleteGlobalRef` đúng thời điểm.
- Đừng sử dụng một reference sau khi `DeleteLocalRef`/`DeleteGlobalRef` đã làm nó không còn hợp lệ. `-Xcheck:jni` có thể phát hiện invalid JNI reference, nhưng kiểm tra không thay thế thiết kế vòng đời đúng.

### 4.2. `JNIEnv*` thuộc về đúng luồng

`JNIEnv*` là giao diện JNI dành cho **luồng hiện tại**. Không cache nó rồi truyền sang worker thread. Với một luồng native do C/C++ tự tạo và cần gọi JVM, lấy `JavaVM*` qua cơ chế JNI phù hợp, attach luồng bằng `AttachCurrentThread`, lấy `JNIEnv*` riêng cho luồng đó và detach khi kết thúc nếu chính native code đã attach luồng. Không detach tùy tiện luồng do JVM quản lý. Kiểm tra giá trị trả về khi attach/detach.

### 4.3. Kiểm tra exception ở biên JNI → Java

Các hàm `Call<Type>Method`/`CallStatic<Type>Method` có thể làm phương thức Java ném exception. Sau lời gọi, sử dụng `ExceptionCheck` (hoặc API kiểm tra ngoại lệ thích hợp) **trước một JNI operation tiếp theo không an toàn khi exception pending**. Đối với hàm trả `NULL` để báo lỗi như `GetStaticMethodID` hoặc `FindClass`, kiểm tra kết quả trước khi dùng ID/reference; đừng xóa exception bằng `ExceptionClear` trừ khi bạn thực sự xử lý được lỗi và đã chọn luồng điều khiển thay thế. `ExceptionDescribe` hữu ích khi cần in thông tin trong môi trường chẩn đoán, nhưng không phải cơ chế xử lý exception thay cho Java.

### 4.4. Cặp `Get...` và `Release...`

Khi một hàm JNI như `GetStringUTFChars` trả một con trỏ, con trỏ chỉ hợp lệ theo hợp đồng của hàm đó và phải được trả bằng `ReleaseStringUTFChars` với **đúng `jstring` và đúng con trỏ**. `GetStringUTFChars` có thể trả `NULL` (ví dụ khi không cấp phát được); phải kiểm tra trước khi sử dụng. Không gọi `free()` trên con trỏ do JVM trả về và không giải phóng lặp. Tương tự, chú ý các cặp `Get<Type>ArrayElements`/`Release<Type>ArrayElements` và các hàm critical. Chuỗi trong những API có hậu tố `UTF` dùng **modified UTF-8** theo đặc tả JNI; không mặc định coi mọi byte UTF-8 thông thường là hợp lệ khi chuyển sang `NewStringUTF`.

Mẫu quản lý tài nguyên, trích đoạn C bên trong một JNI method đã nhận `env` và `value` hợp lệ:

```c
const char *chars = (*env)->GetStringUTFChars(env, value, NULL);
if (chars == NULL) {
    return; /* Co the dang co OutOfMemoryError pending. */
}

/* Doc chars trong pham vi con tro con hieu luc; khong free(chars). */
consume_utf8_bytes(chars);

(*env)->ReleaseStringUTFChars(env, value, chars);
```

`consume_utf8_bytes` ở đây chỉ là **hàm minh họa do ứng dụng phải tự định nghĩa**, không thuộc JNI. Nếu hàm xử lý native có thể thất bại, cần thiết kế đường đi cleanup để luôn release đúng một lần trước khi thoát; đoạn trích này không phải chương trình độc lập.

### 4.5. Vùng critical

`GetPrimitiveArrayCritical`/`GetStringCritical` có thể cấp truy cập dữ liệu cần JVM giữ ổn định. Giữa Get và Release tương ứng, phải giữ công việc **rất ngắn**, tránh chặn luồng và tránh các thao tác JNI khác có thể khiến VM cần GC hoặc bị deadlock. `-Xcheck:jni` có thể phát hiện lời gọi JNI khác trong khoảng này và in cảnh báo. Đừng coi cảnh báo chỉ là “nhiễu” mà bỏ qua.

## 5. Quy trình điều tra khi có WARNING hoặc FATAL ERROR

1. **Tái hiện có kiểm soát.** Ghi lại JDK/vendor/phiên bản, hệ điều hành, lệnh chạy thực tế, phiên bản thư viện `.so`/`.dll`/`.dylib` và dữ liệu đầu vào. Dùng build native có symbol debug khi có thể.
2. **Bật cờ trên đúng JVM.** Ví dụ `java -Xcheck:jni -Djava.library.path=. JniCheckDemo`; với ứng dụng thực tế, đặt cờ trong VM arguments của launcher/test runner. Chạy kịch bản tái hiện và thu toàn bộ stdout, stderr, exit code.
3. **Đọc loại thông báo và stack.** WARNING thường chỉ ra hợp đồng đáng ngờ; FATAL là lỗi nghiêm trọng có thể dừng JVM. Tìm tên native method, lời gọi JNI liền trước, luồng hiện tại và trạng thái ngoại lệ; với crash hãy tìm thêm `hs_err_pid*.log` nếu JVM tạo ra.
4. **Truy ngược đến nguyên nhân.** Với lỗi exception, rà lời gọi `Call...Method` trước cảnh báo. Với bad reference, kiểm tra local/global reference, lifetime và luồng. Với ID/type mismatch, rà signature JNI (ví dụ `()V` là phương thức không tham số, trả `void`), class/method static hay instance. Với release mismatch, đối chiếu con trỏ và đối tượng ban đầu.
5. **Sửa hợp đồng tại nơi phát sinh.** Kiểm tra kết quả/exception trước khi dùng tiếp; release đúng tài nguyên; dùng `JNIEnv*` của đúng luồng; giới hạn lifetime; giảm việc làm trong critical region.
6. **Chạy lại cùng test và mở rộng đường đi.** Xác nhận cảnh báo mục tiêu biến mất, ứng dụng còn cho kết quả đúng và không phát sinh cảnh báo/lỗi khác. Thử đường đi exception, nhiều lần lặp, nhiều luồng và vòng đời tài nguyên, vì lỗi JNI dễ phụ thuộc timing.

Đối với lỗi hiếm gặp, thử nhiều lần và giữ lại cả log của lần lỗi. Khi JVM abort, không giả định các lệnh phía sau điểm abort đã chạy hoặc output đã kịp flush.

## 6. Điều `-Xcheck:jni` KHÔNG đảm bảo

- **Không phát hiện toàn bộ lỗi JNI.** Oracle nói rõ các kiểm tra bổ sung không đảm bảo tìm mọi đối số sai hoặc lỗi logic; một đường code chưa chạy thì chưa được kiểm chứng.
- **Không kiểm tra an toàn bộ nhớ C/C++ một cách tổng quát.** Buffer overflow trong heap native, use-after-free trên con trỏ do `malloc` cấp, rò rỉ native, data race C/C++ hoặc undefined behavior nằm ngoài các lời gọi JNI có thể lọt qua. Dùng AddressSanitizer/UndefinedBehaviorSanitizer, debugger, công cụ leak/race và phân tích crash phù hợp.
- **Không chứng minh business logic đúng.** Chuyển mã hóa sai, nhầm đơn vị, sai xử lý lỗi hoặc chuyển kiểu nhưng vẫn thỏa hợp đồng JNI có thể tạo kết quả sai mà không phát cảnh báo.
- **Không đảm bảo hành vi giống nhau trên mọi JVM/JDK.** Danh sách check, câu chữ log và mức độ nghiêm trọng phụ thuộc phiên bản/triển khai. Ví dụ và phân loại ở đây dựa trên tài liệu HotSpot/JDK 17.
- **Không thay thế kiểm thử Java + native.** Cần test cả đường thành công, đường exception, tình huống nhiều luồng, GC pressure và tải lớn. Bật `-Xcheck:jni` làm tăng chi phí kiểm tra lúc chạy, vì vậy phải đo tác động trước khi bật lâu dài.

## 7. Checklist áp dụng cho dự án

- [ ] Chắc chắn service/test runner khởi động **JVM thực thi native code** với `-Xcheck:jni`.
- [ ] Lưu lệnh chạy, Java version, native library version, stdout/stderr và exit code.
- [ ] Sau `Call...Method` có xử lý đúng khả năng pending exception trước lời gọi JNI kế tiếp.
- [ ] `JNIEnv*` không bị chuyển giữa các luồng; native thread được attach/detach đúng cách.
- [ ] `jmethodID`/`jfieldID`, signature, static/instance và tham số phù hợp.
- [ ] Local/global references còn hợp lệ, được giải phóng đúng vòng đời.
- [ ] Mọi `Get...`/`Release...` được ghép đúng đối tượng/con trỏ và cleanup đủ mọi đường ra.
- [ ] Critical regions ngắn và không có JNI calls nguy hiểm bên trong.
- [ ] Sau khi sửa, chạy lại cùng test có kiểm tra output nghiệp vụ, warning/fatal log và các đường lỗi.

## 8. Tự kiểm tra hiểu bài

**Câu 1.** Callback Java chạy thành công nhưng `-Xcheck:jni` cảnh báo sau `CallStaticVoidMethod`. Có nhất thiết xảy ra Java exception không?  
**Đáp án:** Không. Cảnh báo có thể nói rằng native code chưa **kiểm tra khả năng** exception trước lệnh JNI tiếp theo; thao tác `ExceptionCheck` đúng chỗ sẽ giải quyết vi phạm đó.

**Câu 2.** Vì sao không truyền `JNIEnv*` lấy từ luồng A sang luồng B?  
**Đáp án:** Giao diện này gắn với luồng hiện hành; luồng B cần môi trường JNI của chính nó (attach nếu cần), nếu không có thể vi phạm hợp đồng và bị HotSpot dừng.

**Câu 3.** Test đã chạy sạch với `-Xcheck:jni` có chứng minh thư viện native không có lỗi bộ nhớ không?  
**Đáp án:** Không. Các lỗi C/C++ nằm ngoài phạm vi kiểm tra JNI, hoặc các đường code chưa chạy, vẫn có thể tồn tại. Cần sanitizer, debugger và test bổ sung.

## Tài liệu chuẩn

- Oracle JDK 17, *The java Command* (mục `-Xcheck:jni`): https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html
- Oracle JDK 17, *Troubleshooting Guide – Command-Line Options*: https://docs.oracle.com/en/java/javase/17/troubleshoot/command-line-options1.html
- Oracle, *JNI Specification – JNI Functions* (reference lifecycle, string APIs, exceptions): https://docs.oracle.com/en/java/javase/17/docs/specs/jni/functions.html
- Oracle, *Secure Coding Guidelines for Java SE* (JNI boundary input validation/exception handling): https://www.oracle.com/java/technologies/javase/seccodeguide.html
