# Quản lý khung tham chiếu bằng PushLocalFrame và PopLocalFrame trong JNI

## 1. Bài toán: local reference tích lũy trong một native method chạy lâu

Trong Java Native Interface (JNI), mã C/C++ thao tác với đối tượng Java thông qua các **JNI references** như `jobject`, `jstring`, `jclass` hoặc `jobjectArray`. Khi Java chuyển quyền điều khiển vào phương thức `native`, JVM tạo một **khung tham chiếu cục bộ** (*local reference frame*). Các local reference trong khung đó thường được JVM thu hồi tự động sau khi native method kết thúc.

Cơ chế tự động này tiện cho hàm ngắn, nhưng có thể gây vấn đề ở hàm native xử lý **nhiều phần tử trong một lần gọi**. Ví dụ, mã C lặp 50.000 lần, mỗi lần gọi `GetObjectArrayElement` hoặc `NewStringUTF` tạo thêm local reference. Nếu chỉ chờ native method kết thúc, các handles mới có thể tích lũy trong suốt vòng lặp, chiếm tài nguyên JVM và giữ đối tượng Java reachable lâu hơn mức cần thiết.

Để tổ chức một phạm vi dọn tham chiếu, JNI cung cấp:

~~~c
jint PushLocalFrame(JNIEnv *env, jint capacity);
jobject PopLocalFrame(JNIEnv *env, jobject result);
~~~

- **`PushLocalFrame`:** mở một khung local references mới, bảo đảm khả năng tạo ít nhất `capacity` local references trong khung đó.
- **`PopLocalFrame`:** đóng khung hiện tại, xóa toàn bộ local references thuộc khung; có thể đưa **một tham chiếu kết quả** về khung trước.
- Hai thao tác quản lý **handles JNI**, không trực tiếp xóa đối tượng Java khỏi heap, không ép garbage collector (GC) chạy, và không dọn bộ nhớ C do `malloc` cấp phát.

**Mục tiêu bài học:** hiểu quan hệ với GC, phân biệt local/global references, cân bằng Push/Pop trên mọi nhánh, giữ kết quả bằng `PopLocalFrame(result)`, xử lý exception và thực hành Java 17 + C có thể biên dịch, chạy độc lập.

## 2. Local reference khác đối tượng Java và global reference

Một **Java object** là thực thể trên heap được JVM quản lý; **JNI reference** là handle cho phép mã native tham chiếu tới object đó thông qua API JNI. Nhiều handle có thể cùng trỏ tới một Java object.

| Loại tham chiếu JNI | Vòng đời thường gặp | Cơ chế quản lý | Ảnh hưởng tới GC |
|---|---|---|---|
| **Local reference** | Khi native method đang chạy hoặc tới khi bị xóa/frame bị pop | JVM tự dọn khi native method trả về; native có thể dọn sớm | Là strong reference khi còn hiệu lực, có thể giữ đối tượng reachable |
| **Global reference** | Qua nhiều lần gọi JNI, cho đến khi xóa tường minh | `NewGlobalRef` / `DeleteGlobalRef` | Strong reference; có thể giữ object sống lâu |
| **Weak global reference** | Handle tồn tại cho tới khi xóa; đích có thể bị GC thu gom sớm hơn | `NewWeakGlobalRef` / `DeleteWeakGlobalRef` | Không bảo đảm giữ object đích sống |

Ví dụ, `NewStringUTF(env, "hello")` trả một `jstring` local reference tới chuỗi Java được tạo. Khi local reference bị xóa, điều đó có nghĩa handle không còn hợp lệ, **không đồng nghĩa** object bị hủy tức thì. Nếu Java code, một field hay một global reference vẫn giữ object đó, GC không thể coi nó là không reachable chỉ vì một local JNI handle đã biến mất.

**Phân biệt loại dữ liệu:**

- `jstring`, `jclass`, `jarray` đều là các dạng reference JNI và cần được quản lý theo vòng đời.
- `jint`, `jlong` và các kiểu nguyên thủy là giá trị, không phải reference.
- `jfieldID`, `jmethodID` là định danh metadata, không phải `jobject`; không gọi `DeleteLocalRef` lên những ID này.
- Con trỏ từ `GetStringUTFChars` hoặc `malloc` không phải JNI local reference. Chúng cần thao tác release/free tương ứng, kể cả khi frame đã pop.

## 3. Hiểu khung local reference như một stack LIFO

Khi Java gọi native method, JVM đã có một khung ban đầu cho lần gọi ấy. Mã C có thể tạo thêm các **khung con lồng nhau**:

~~~text
Java gọi nativeMethod()
    |
    v
[Khung gốc F0: tồn tại trong lời gọi native]
  - receiver/đối số object
  - ref được tạo trước khi push
       |
       | PushLocalFrame(env, 8) == JNI_OK
       v
  [Khung con F1]
    - refA, refB... được tạo trong F1
    - refs thuộc F0 vẫn dùng được
         |
         | PushLocalFrame(env, 4) == JNI_OK
         v
    [Khung con F2]
      - refC, refD được tạo trong F2
         |
         | PopLocalFrame(env, NULL)
         v
    [F2 đã đóng: refC và refD hết hiệu lực]
    [F1 vẫn còn hoạt động]
       |
       | PopLocalFrame(env, NULL)
       v
[F1 đã đóng: refA và refB hết hiệu lực]
[F0 tiếp tục]
       |
       | nativeMethod() trả về Java
       v
[JVM thu hồi local refs còn lại thuộc lời gọi native]
~~~

Quy tắc **LIFO (last in, first out)**: khung đẩy vào sau phải được pop trước. Mỗi lần `PushLocalFrame` **thành công** cần một lần `PopLocalFrame` tương ứng trước khi thoát khỏi phạm vi của nó.

Local references được tạo ở **khung cha** vẫn hợp lệ trong khung con đang chạy. Ngược lại, local references được tạo ở **khung con** không được sử dụng sau khi khung con đã pop, dù biến C vẫn giữ bit pattern của handle cũ.

Đây là **khung quản lý tham chiếu**, không phải lời gọi hàm C mới, không tạo thread, không mở một Java method stack frame độc lập.

## 4. PushLocalFrame: capacity là mức bảo đảm, không phải số object hay số byte

C API:

~~~c
jint PushLocalFrame(JNIEnv *env, jint capacity);
~~~

**Đầu vào:**

- `env` là con trỏ giao diện JNI hợp lệ của **thread hiện tại**.
- `capacity` phải **lớn hơn 0** theo đặc tả; đó là số local references tối thiểu có thể tạo trong frame mới.

**Đầu ra:**

- Thành công: trả `JNI_OK`, bằng `0`, và frame mới đã được mở.
- Thất bại: trả mã âm; không mở frame mới. Theo đặc tả, lỗi có thể gắn với pending Java `OutOfMemoryError`; implementation cũng có thể giới hạn capacity hỗ trợ.

Mẫu sử dụng đúng trong JNI method trả về object:

~~~c
if ((*env)->PushLocalFrame(env, 8) != JNI_OK) {
    /* Không có frame mới, không gọi PopLocalFrame. */
    return NULL;
}

/* Tạo và dùng các local references ở đây. */

(*env)->PopLocalFrame(env, NULL);
return NULL;
~~~

Đây là **trích đoạn cấu trúc**, không phải tệp C hoàn chỉnh.

`PushLocalFrame(env, 8)` không cấp phát tám Java objects và không dành sẵn một vùng heap tám byte. Nó đảm bảo **có thể tạo ít nhất tám JNI local handles trong frame mới**. JVM có thể cho phép tạo hơn mức ấy, nhưng không thể coi capacity là giới hạn cứng hoặc là khả năng tăng vô hạn.

Native method thông thường được JVM đảm bảo có thể tạo tối thiểu **16 local references** khi mới đi vào. Điều đó không đủ để bỏ qua cleanup với vòng lặp rất dài.

**Chọn capacity theo số handle đồng thời cần sống trong một vòng**, ví dụ một element, một class và một chuỗi tạm có thể dùng capacity 8. Đừng lấy tổng số vòng lặp làm capacity nếu mỗi vòng đã pop toàn bộ refs.

## 5. PopLocalFrame: dọn tất cả, hoặc giữ đúng một kết quả

C API:

~~~c
jobject PopLocalFrame(JNIEnv *env, jobject result);
~~~

Có hai trường hợp quan trọng.

### 5.1. Không giữ kết quả: `PopLocalFrame(env, NULL)`

Khi chỉ cần object tạm trong quá trình xử lý:

~~~c
if ((*env)->PushLocalFrame(env, 4) != JNI_OK) {
    return; /* Ví dụ trong một native method trả về void. */
}

jstring temp = (*env)->NewStringUTF(env, "temporary");
if (temp == NULL) {
    (*env)->PopLocalFrame(env, NULL);
    return;
}

/* Dùng temp trong khi frame còn hoạt động. */

(*env)->PopLocalFrame(env, NULL);
/* Không dùng temp sau đây. */
~~~

Đây là **trích đoạn minh họa** trong native method trả về `void`. Nó nhấn mạnh rằng `PopLocalFrame(NULL)` làm hết hiệu lực tất cả local handles tạo trong khung mới. Nếu có Java exception đang pending khi `NewStringUTF` thất bại, `PopLocalFrame` vẫn được phép gọi để cleanup rồi trả về cho Java xử lý exception.

### 5.2. Muốn giữ một object: `PopLocalFrame(env, result)`

Giả sử mã C tạo một `jstring` trong frame con nhưng muốn trả chuỗi đó cho Java. Dùng `PopLocalFrame` với tham số là handle còn hợp lệ:

~~~c
if ((*env)->PushLocalFrame(env, 4) != JNI_OK) {
    return NULL;
}

jstring inside = (*env)->NewStringUTF(env, "kept");
if (inside == NULL) {
    (*env)->PopLocalFrame(env, NULL);
    return NULL;
}

return (jstring) (*env)->PopLocalFrame(env, inside);
~~~

Đây là **trích đoạn trong JNI method trả về `jstring`**, sẽ xuất hiện trong chương trình hoàn chỉnh phía dưới.

Cách hiểu:

~~~text
Trước Pop:
  F0 (khung cha)          : [oldRef]
  F1 (khung con)          : [tempA, inside, tempB]

  kept = PopLocalFrame(env, inside)

Sau Pop:
  F0 (khung cha)          : [oldRef, kept]
  F1                      : đã bị thu hồi
  tempA, inside, tempB     : handles cũ hết hiệu lực
  kept                    : local reference hợp lệ ở F0
~~~

`PopLocalFrame` không sao chép chuỗi `"kept"` sang object mới. Nó **trả một local reference ở frame trước tới cùng Java object**. Giá trị handle cũ `inside` không được dùng lại sau khi pop; phải dùng **giá trị trả về** của `PopLocalFrame`.

Nếu không có object cần giữ, truyền `NULL`. Không được gọi pop nếu push chưa thành công; cũng không được pop một frame hai lần.

## 6. Ví dụ chạy được: một vòng lặp dọn refs, một kết quả sống qua frame

Ta sẽ viết một chương trình **Java 17+ và thư viện C JNI** với hai native methods:

1. `sumLengths(int iterations)`: mỗi vòng mở frame, tạo chuỗi `"JNI"`, đọc độ dài, đóng frame và không giữ local reference nào.
2. `keepOne()`: mở frame, tạo chuỗi `"kept"`, đóng frame nhưng đưa local reference kết quả về frame cha để trả cho Java.

Toàn bộ tệp được đặt cùng một thư mục:

~~~text
local-frame-demo/
├── LocalFrames.java
├── localframes.c
├── LocalFrames.h       (javac -h sinh ra)
├── LocalFrames.class   (javac sinh ra)
└── thư viện native      (tên phụ thuộc hệ điều hành)
~~~

### 6.1. Viết `LocalFrames.java`

~~~java
public final class LocalFrames {
    static {
        System.loadLibrary("localframes");
    }

    private LocalFrames() {
    }

    private static native long sumLengths(int iterations);

    private static native String keepOne();

    public static void main(String[] args) {
        System.out.println("total = " + sumLengths(4));
        System.out.println("result = " + keepOne());
    }
}
~~~

Khối `static` nạp thư viện native trước khi các method được gọi. Cả hai method là `static native` nên C function nhận `JNIEnv *` và `jclass` ngầm định; `sumLengths` còn nhận một `jint` tương ứng với tham số Java `int`.

### 6.2. Sinh header JNI bằng JDK

Chạy lệnh từ thư mục chứa `LocalFrames.java`:

~~~bash
javac -h . LocalFrames.java
~~~

Kết quả có `LocalFrames.class` và `LocalFrames.h`. Header sinh ra có hai khai báo cốt lõi:

~~~c
JNIEXPORT jlong JNICALL Java_LocalFrames_sumLengths
  (JNIEnv *, jclass, jint);

JNIEXPORT jstring JNICALL Java_LocalFrames_keepOne
  (JNIEnv *, jclass);
~~~

Đây là **trích đoạn**, header thật còn include guard và `#include <jni.h>`. Sử dụng header đã sinh, không tự bịa chữ ký C.

### 6.3. Viết `localframes.c`

~~~c
#include "LocalFrames.h"

JNIEXPORT jlong JNICALL Java_LocalFrames_sumLengths(
    JNIEnv *env, jclass clazz, jint iterations
) {
    (void) clazz;

    if (iterations <= 0) {
        return 0;
    }

    jlong total = 0;

    for (jint i = 0; i < iterations; ++i) {
        /* Một frame mới ở mỗi vòng. */
        if ((*env)->PushLocalFrame(env, 4) != JNI_OK) {
            /* Push thất bại: không có frame mới để pop. */
            return 0;
        }

        jstring temporary = (*env)->NewStringUTF(env, "JNI");
        if (temporary == NULL) {
            /* Frame đã push; cleanup kể cả khi exception pending. */
            (*env)->PopLocalFrame(env, NULL);
            return 0;
        }

        total += (jlong) (*env)->GetStringLength(env, temporary);

        /* Không cần giữ temporary sang vòng sau. */
        (*env)->PopLocalFrame(env, NULL);
    }

    return total;
}

JNIEXPORT jstring JNICALL Java_LocalFrames_keepOne(
    JNIEnv *env, jclass clazz
) {
    (void) clazz;

    if ((*env)->PushLocalFrame(env, 4) != JNI_OK) {
        return NULL;
    }

    jstring inside = (*env)->NewStringUTF(env, "kept");
    if (inside == NULL) {
        (*env)->PopLocalFrame(env, NULL);
        return NULL;
    }

    /* Trả ref trong frame cha, không trả inside handle cũ. */
    return (jstring) (*env)->PopLocalFrame(env, inside);
}
~~~

Đây là **tệp C đầy đủ** cho ví dụ. `JNIEXPORT` và `JNICALL` do header JNI cung cấp qua đúng khai báo; hàm C dùng chính chữ ký đó. `GetStringLength` trả **độ dài UTF-16** của Java string, vì `"JNI"` gồm ba chữ cái ASCII nên độ dài là 3. Biến `total` dùng `jlong` để cộng dồn an toàn hơn kiểu `int` với số vòng lớn; ví dụ chỉ gọi bốn vòng.

Kiểm tra hai quy tắc trong C:

- Sau `PushLocalFrame` thất bại, hàm trả về ngay và **không pop**.
- Sau `PushLocalFrame` thành công, cả đường thành công lẫn đường `NewStringUTF` thất bại đều **pop đúng một lần**.
- `keepOne` không trả trực tiếp `inside` sau pop mà trả **local handle do `PopLocalFrame` sinh ở khung cha**.
- `PopLocalFrame(env, NULL)` dọn các refs tạm sau từng vòng; một vòng không thể để refs mới tích lũy sang vòng tiếp theo.
- Trả `0` hoặc `NULL` khi có exception pending chỉ là giá trị ở mức C; phía Java sẽ thấy exception đang chờ. Không tự gọi `ExceptionClear` để che lỗi OOM.

### 6.4. Biên dịch trên Linux, macOS hoặc Windows

Điều kiện: JDK 17+ với `jni.h`, `JAVA_HOME` trỏ tới JDK, compiler C phù hợp với **kiến trúc JVM đang chạy**. Chạy **một** bộ lệnh cho hệ điều hành của bạn sau khi đã chạy `javac -h`.

**Linux — GCC:**

~~~bash
gcc -fPIC -shared \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  localframes.c -o liblocalframes.so

java -Djava.library.path=. LocalFrames
~~~

**macOS — Clang:**

~~~bash
cc -dynamiclib -fPIC \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/darwin" \
  localframes.c -o liblocalframes.dylib

java -Djava.library.path=. LocalFrames
~~~

**Windows — MSVC Developer Command Prompt (cmd.exe):**

~~~bat
cl /LD /I"%JAVA_HOME%\include" /I"%JAVA_HOME%\include\win32" localframes.c /Fe:localframes.dll

java -Djava.library.path=. LocalFrames
~~~

Theo hệ điều hành, `System.loadLibrary("localframes")` tìm tên tương ứng `localframes.dll`, `liblocalframes.so` hoặc `liblocalframes.dylib` qua các đường dẫn được JVM cấu hình. `-Djava.library.path=.` được đặt **trước** tên class `LocalFrames` để JVM tìm thư viện tại thư mục hiện hành.

**Stdout chính xác khi build và nạp thành công:**

~~~text
total = 12
result = kept
~~~

Tại sao? `sumLengths(4)` gọi `GetStringLength` cho `"JNI"` dài 3 đơn vị UTF-16 tổng cộng bốn lần, nên `4 × 3 = 12`. `keepOne` tạo chuỗi trong frame con, dùng `PopLocalFrame(env, inside)` chuyển một reference về frame cha và trả `"kept"` cho Java. Việc kết quả xuất hiện không khẳng định GC đã chạy; ví dụ chứng minh **hợp đồng tham chiếu và giá trị trả về**.

## 7. Xử lý ngoại lệ: Push thất bại và NewStringUTF thất bại khác nhau

Trong JNI, một Java exception được ghi nhận là **pending exception** trong thread hiện tại. Mã C không tự động nhảy tới `catch` như Java; nó cần kiểm tra các giá trị trả về hoặc `ExceptionCheck` và rời khỏi hàm/cleanup đúng cách.

| Thời điểm lỗi | Frame mới đã tồn tại? | Xử lý chuẩn |
|---|---|---|
| `PushLocalFrame` trả khác `JNI_OK` | **Chưa** | Không gọi `PopLocalFrame`; xử lý/lan truyền lỗi |
| `NewStringUTF` trả `NULL` sau khi push thành công | **Có** | `PopLocalFrame(env, NULL)`, trả về để Java xử lý pending exception |
| Một JNI API khác ném exception khi đang ở frame con | **Có** | Không gọi tùy tiện API JNI tiếp; cleanup frame rồi trả về |
| Xử lý thành công, không cần object | **Có** | `PopLocalFrame(env, NULL)` |
| Xử lý thành công, cần object kết quả | **Có** | Dùng giá trị trả về của `PopLocalFrame(env, result)` |

`PopLocalFrame` thuộc nhóm **JNI functions được phép gọi khi exception pending**. Các JNI APIs nói chung **không** được gọi tùy ý khi exception còn chờ; nếu thực sự xử lý exception ở C, phải hiểu rõ `ExceptionCheck`, `ExceptionOccurred`, `ExceptionClear` và quản lý tài nguyên đã acquire.

**Mẫu cleanup tập trung** (trích đoạn nằm trong JNI method trả về `jobject`; không phải chương trình chạy độc lập):

~~~c
jobject result = NULL;

if ((*env)->PushLocalFrame(env, 8) != JNI_OK) {
    return NULL;              /* Không pop nếu push thất bại. */
}

/* ... xử lý và tạo result hợp lệ khi thành công ...
   ... nếu lỗi, để result = NULL và chuyển tới cleanup ... */

return (*env)->PopLocalFrame(env, result);
~~~

Trong hàm C thực tế, có thể dùng một nhãn cleanup sau khi push thành công. Bất kể có bao nhiêu `return` hay nhánh lỗi, **mỗi lần push thành công phải được pop đúng một lần**. Không pop hai lần, không bỏ qua frame đang hoạt động, và không pop frame chưa được tạo.

## 8. So sánh Push/Pop với các API quản lý reference khác

| API | Công dụng | Tạo/đóng frame? | Thường dùng khi |
|---|---|---|---|
| `DeleteLocalRef(env, ref)` | Xóa một local reference cụ thể | Không | Một vòng chỉ tạo một vài references |
| `EnsureLocalCapacity(env, n)` | Bảo đảm có thể tạo thêm tối thiểu n local references trong frame **hiện tại** | Không | Cần chuẩn bị capacity nhưng không cần scope cleanup |
| `PushLocalFrame(env, n)` | Tạo frame con với capacity tối thiểu n | **Tạo** | Mỗi bản ghi/lô sinh nhiều refs tạm |
| `PopLocalFrame(env, result)` | Đóng frame, dọn hàng loạt và tùy chọn giữ một ref sang cha | **Đóng** | Kết thúc phạm vi quản lý local refs |
| `NewLocalRef(env, ref)` | Tạo một local handle mới tới cùng object trong phạm vi hiện tại | Không | Cần một handle local bổ sung |
| `NewGlobalRef(env, ref)` | Tạo global handle tồn tại qua nhiều calls | Không | Cache/sở hữu object dài hạn |

### Vì sao EnsureLocalCapacity không thay được PushLocalFrame?

`EnsureLocalCapacity` giúp có chỗ cho thêm local refs **nhưng không tạo một khung con**. Nếu mỗi lần lặp gọi `EnsureLocalCapacity` rồi tạo một chuỗi mới mà không `DeleteLocalRef`, các refs vẫn tích lũy trong frame của native method. `PushLocalFrame` + `PopLocalFrame` tạo được ranh giới thu hồi **cả nhóm refs**.

### Vì sao NewLocalRef không thay được PopLocalFrame(result)?

Nếu `NewLocalRef(env, inside)` được gọi **bên trong frame con**, handle mới cũng thuộc frame đang hoạt động. Pop frame ấy vẫn làm cả hai handles hết hiệu lực. Muốn đưa một object sang frame cha, dùng **`PopLocalFrame(env, inside)`** và nhận giá trị trả về. Nếu cần giữ lâu qua nhiều native calls, có thể cân nhắc `NewGlobalRef` với vòng đời giải phóng tường minh.

### Khi nào DeleteLocalRef gọn hơn?

Nếu mỗi vòng chỉ lấy một element bằng `GetObjectArrayElement`, xử lý ngay rồi không giữ nữa, `DeleteLocalRef(env, element)` có thể đơn giản hơn. Push/Pop hữu ích khi logic xử lý tạo **nhiều refs tạm**, lồng nhiều hàm, có nhiều đường thoát hoặc cần thiết kế phạm vi rõ ràng.

## 9. GC, thread và tài nguyên native: ranh giới quan trọng

### 9.1. Pop không ép GC giải phóng object ngay

`PopLocalFrame` làm handle trong frame con không còn hợp lệ. Nếu Java variable, object field, class static field hoặc một global reference vẫn trỏ tới object, object vẫn reachable. Nếu không còn root nào, GC **có thể** thu gom nó sau đó; `PopLocalFrame` không định thời điểm chạy GC.

Giữ Java object sống là một hệ quả của strong local references, nhưng đối tượng và reference là **hai thứ khác nhau**. Không dùng giá trị bộ nhớ heap quan sát tức thì để kết luận Pop thành công hay thất bại.

### 9.2. Pop không thay thế native resource cleanup

Nếu mã native đã gọi:

- `malloc`: cần `free`;
- `GetStringUTFChars`: cần `ReleaseStringUTFChars`;
- `GetByteArrayElements`: cần `ReleaseByteArrayElements`;
- `GetPrimitiveArrayCritical`: cần `ReleasePrimitiveArrayCritical`;
- hàm OS cấp file/socket/handle: cần đóng theo API tương ứng.

Các con trỏ/tài nguyên trên không tự biến mất chỉ vì local frame đã pop. Hãy release đúng cặp API, đặc biệt trên đường lỗi khi đang có Java exception pending.

### 9.3. Local references và JNIEnv gắn với thread

Local references chỉ hợp lệ trong **thread tạo ra chúng**, không được đưa nguyên `jobject` local sang thread native khác. `JNIEnv *` cũng là giao diện sử dụng theo thread, không dùng lại từ thread khác. Khi cần giữ một Java object qua nhiều lần gọi hoặc chuyển ngữ cảnh thread, sử dụng global reference một cách có chủ sở hữu rõ ràng và theo quy tắc attach/detach JNI.

Trong native thread được đính kèm bằng `AttachCurrentThread`, local references có thể tồn tại đến lúc thread detach nếu không được dọn tường minh; vì vậy long-running attached native threads nên quản lý refs bằng `DeleteLocalRef` hoặc Push/Pop.

### 9.4. Dùng handle sau pop là lỗi

**Đoạn C sau là ví dụ SAI, chỉ để nhận diện lỗi, không chạy:**

~~~c
/* env đã hợp lệ; lược bớt kiểm tra lỗi để minh họa sai lầm. */
(*env)->PushLocalFrame(env, 4);
jstring stale = (*env)->NewStringUTF(env, "hello");
(*env)->PopLocalFrame(env, NULL);

/* SAI: stale là JNI handle thuộc frame đã pop! */
(*env)->GetStringLength(env, stale);
~~~

Kể cả khi object `"hello"` còn sống do một tham chiếu khác, handle `stale` đã bị vô hiệu hóa. Kết quả có thể là lỗi kiểm tra JNI hoặc crash JVM; không trông chờ Java `try/catch` bắt được mọi lỗi trong C. Cách sửa: nếu cần chuỗi, truyền `stale` hợp lệ vào `PopLocalFrame(env, stale)` **trước khi frame đóng**, rồi giữ **handle trả về**.

## 10. Mẫu áp dụng cho vòng lặp lấy phần tử từ Java object array

Giả sử một native method nhận `jobjectArray array` và xử lý lần lượt các phần tử. Khung theo vòng lặp ngăn việc tích lũy local refs:

~~~c
/* Trích đoạn trong native method trả void; env/array/count hợp lệ. */
for (jsize i = 0; i < count; ++i) {
    if ((*env)->PushLocalFrame(env, 8) != JNI_OK) {
        return; /* Push thất bại, không pop khung chưa mở. */
    }

    jobject element = (*env)->GetObjectArrayElement(env, array, i);
    if (element == NULL && (*env)->ExceptionCheck(env)) {
        (*env)->PopLocalFrame(env, NULL);
        return;
    }

    /* element có thể null hợp lệ nếu array chứa null.
       Xử lý element; tạo thêm refs tạm nếu cần.
       Thêm kiểm tra exception ở các JNI calls có thể lỗi. */

    (*env)->PopLocalFrame(env, NULL);
}
~~~

Đây là **khung mã minh họa**, chưa phải tệp biên dịch độc lập và không chứa nghiệp vụ. Nó dùng `ExceptionCheck` để phân biệt **phần tử null hợp lệ** với `NULL` do exception khi lấy phần tử. Trước khi đưa vào ứng dụng thật, phải bổ sung xử lý element, các nhánh lỗi và cleanup tương ứng. Mỗi vòng tạo riêng frame capacity 8; frame bị pop ở cuối vòng nên số local refs tạm không tự tăng theo tổng số vòng.

## 11. Lỗi phổ biến và công cụ chẩn đoán

| Sai lầm | Hậu quả | Cách sửa |
|---|---|---|
| Không kiểm tra kết quả `PushLocalFrame` | Có thể pop frame chưa tồn tại | Chỉ pop nếu push trả `JNI_OK` |
| Quên pop ở một nhánh `return` lỗi | Giữ refs/frame lâu hơn dự kiến, mất cân bằng cleanup | Gom đường ra qua cleanup hoặc cân bằng từng nhánh |
| Double-pop | Pop sai frame, có thể làm hỏng trạng thái JNI | Mỗi push thành công chỉ được pop một lần |
| Trả `inside` sau `PopLocalFrame(NULL)` | Use-after-pop trên local handle cũ | `return PopLocalFrame(env, inside)` |
| Tưởng `capacity` là heap bytes hoặc số objects | Ước lượng sai tài nguyên | Đếm các local references đồng thời sống |
| Dùng `EnsureLocalCapacity` thay cho cleanup | Refs vẫn tích lũy | `DeleteLocalRef` hoặc Push/Pop |
| Dùng `NewLocalRef` trong frame con để “giữ” ref | Ref mới cũng bị pop | `PopLocalFrame(result)` |
| Lưu local `jobject` vào static C variable | Ref hết hiệu lực sau frame/native call | Dùng `NewGlobalRef` nếu cần sở hữu dài hạn |
| Pop và quên `ReleaseStringUTFChars`/`free` | Rò rỉ tài nguyên native | Release/free riêng theo API |
| Dùng local ref hoặc `JNIEnv *` từ thread khác | Vi phạm hợp đồng JNI, có thể crash | Quản lý theo thread và dùng global refs khi cần |

Trên HotSpot, có thể bật kiểm tra JNI:

~~~bash
java -Xcheck:jni -Djava.library.path=. LocalFrames
~~~

`-Xcheck:jni` có thể cảnh báo một số cách dùng JNI không hợp lệ (chẳng hạn dùng reference đã vô hiệu hóa), nhưng không chứng minh code native an toàn hoàn toàn. Với chương trình hợp lệ, stdout ứng dụng vẫn là:

~~~text
total = 12
result = kept
~~~

Nếu JVM crash trong mã C/C++, kiểm tra thông tin chẩn đoán của JVM như `hs_err_pid...log` (nếu được tạo), native stack và đường đi của JNI references. Không chủ động gọi `System.gc()` để “thử xem frame đã pop chưa”: GC không phải công cụ xác nhận vòng đời của một JNI handle.

## 12. Tự kiểm tra kiến thức

1. Vì sao native method có 100.000 vòng lặp vẫn có thể thiếu tài nguyên local references dù JVM sẽ thu hồi refs khi hàm trả về?
2. `PushLocalFrame(env, 8)` có tạo tám Java objects hoặc giới hạn cứng số refs ở tám không?
3. Sau một `PushLocalFrame` trả lỗi âm, có nên gọi `PopLocalFrame` không?
4. Vì sao `PopLocalFrame(env, NULL)` không đồng nghĩa mọi object của khung đó đã bị GC thu gom?
5. Nếu cần trả chuỗi Java tạo trong khung con, dùng `PopLocalFrame(env, result)` như thế nào?
6. Khác nhau giữa `EnsureLocalCapacity` và `PushLocalFrame` ở việc giải phóng refs sau một lô xử lý là gì?
7. Khi `NewStringUTF` thất bại sau push thành công, có thể gọi `PopLocalFrame` trong khi Java exception pending không?
8. Nếu gọi `NewLocalRef` bên trong frame con rồi pop, reference mới có sống tiếp trong frame cha không?
9. Khi mã JNI dùng `malloc`, `GetStringUTFChars` và `NewStringUTF`, `PopLocalFrame` xử lý loại tài nguyên nào?
10. Vì sao không nên chuyển `jobject` local hoặc `JNIEnv *` sang một thread C khác?

**Ghi nhớ:** `PushLocalFrame` tạo một phạm vi local JNI references mới với capacity tối thiểu; `PopLocalFrame(env, NULL)` dọn toàn bộ refs tạm trong phạm vi ấy, còn `PopLocalFrame(env, result)` trả một tham chiếu hợp lệ ở khung cha. Luôn kiểm tra push, pop cân bằng, giữ handle mới sau pop, tôn trọng ranh giới thread và cleanup tài nguyên native riêng.

### Tài liệu đối chiếu

- [JNI Specification — Local References, PushLocalFrame, PopLocalFrame](https://docs.oracle.com/en/java/javase/21/docs/specs/jni/functions.html): chữ ký API, capacity, giá trị trả về và phạm vi.
- [JNI Specification — Referencing Java Objects](https://docs.oracle.com/en/java/javase/21/docs/specs/jni/design.html): local/global references, thời hạn hiệu lực và quan hệ với GC.
- [Android NDK JNI Tips — Local references và exceptions](https://developer.android.com/ndk/guides/jni-tips): tình huống vòng lặp dài, thread native được attach và cleanup với pending exception.
