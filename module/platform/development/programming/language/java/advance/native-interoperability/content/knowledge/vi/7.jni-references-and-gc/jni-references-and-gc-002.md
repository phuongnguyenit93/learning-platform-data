# Phạm vi theo lời gọi và theo luồng của tham chiếu cục bộ (JNI local references)

## 1. Vấn đề cốt lõi

Trong Java Native Interface (JNI), mã C/C++ có thể giữ `jobject`, `jclass`, `jstring`, `jarray` và các kiểu tham chiếu tương tự để thao tác với đối tượng Java. Nhưng một giá trị `jobject` **không phải con trỏ C trỏ trực tiếp tới object trong heap**. Đó là một **tham chiếu JNI** do JVM quản lý. Loại tham chiếu thông dụng nhất là **local reference** (tham chiếu cục bộ).

Có hai ranh giới phải nắm vững:

1. **Theo lời gọi:** Local references nhận khi Java gọi native method, hoặc tạo trong lời gọi đó, nhìn chung chỉ có hiệu lực trong **lượt gọi native hiện tại**; khi native method trả về, JVM tự thu hồi những local references thuộc frame của lượt gọi ấy.
2. **Theo luồng:** Một local reference chỉ có hiệu lực ở **thread đã tạo nó**. Không được truyền nguyên giá trị local `jobject` sang một thread khác để thread kia dùng, ngay cả khi lượt gọi ban đầu vẫn chưa kết thúc.

Đối với **native thread tự gọi `AttachCurrentThread`** vào JVM, có một ngoại lệ quan trọng về thời gian: local references của thread này **không mặc nhiên tự dọn khi một native function C thông thường trả về**; nếu không xóa rõ ràng hoặc quản lý bằng local frame, chúng có thể tồn tại tới khi thread detach.

Ba câu hỏi để quyết định một local reference có còn dùng được không:

- **Nó được tạo trong thread nào?** Thread hiện tại có đúng thread tạo reference không?
- **Frame/lời gọi JNI chứa nó còn sống không?** Đã return, `DeleteLocalRef` hoặc `PopLocalFrame` chưa?
- **Đó có đúng là một JNI reference hợp lệ không?** Không dùng lại một handle đã bị hủy, dù giá trị bit của nó còn nằm trong biến C.

Ghi nhớ: **vòng đời của local JNI reference khác vòng đời của Java object được tham chiếu**. Xóa local reference không đồng nghĩa hủy object. Nếu Java hoặc một reference mạnh hợp lệ khác vẫn giữ object, nó tiếp tục tồn tại; nếu object không còn reachable, GC có thể thu hồi theo cơ chế JVM.

## 2. Local reference được tạo ở đâu?

Các nguồn điển hình:

| Nguồn | Ví dụ | Loại/vòng đời |
| --- | --- | --- |
| Tham số object truyền từ Java sang native method | `jobject receiver`, `jstring text`, `jobjectArray items` | Local references hợp lệ trong native invocation hiện hành |
| Hàm JNI tạo đối tượng | `NewStringUTF`, `NewObject`, `NewObjectArray` | Thường trả local reference |
| Hàm JNI tra cứu class | `FindClass`, `GetObjectClass` | Trả local `jclass` |
| Lấy một phần tử của object array | `GetObjectArrayElement` | Trả local `jobject`, kể cả khi mảng Java còn sống lâu hơn |
| Tạo thêm local handle tới cùng object | `NewLocalRef` | Local reference mới, có vòng đời riêng |
| Chuyển một kết quả ra khỏi frame con | `PopLocalFrame(env, result)` | Tạo local reference hợp lệ ở frame cha khi thành công |

Ví dụ Java/C minh họa đơn giản:

~~~java
// Java: chỉ minh họa chữ ký.
class Example {
    private native void inspect(String value);
}
~~~

~~~c
/* C: chữ ký minh họa, chưa phải chương trình biên dịch độc lập. */
JNIEXPORT void JNICALL Java_Example_inspect(
        JNIEnv *env, jobject receiver, jstring value) {
    jclass actualClass = (*env)->GetObjectClass(env, value);
    if (actualClass == NULL) {
        return; /* Ví dụ: kiểm tra lỗi/exception theo hợp đồng. */
    }

    /* receiver, value và actualClass là các JNI local references
       chỉ được dùng trong thread và frame hợp lệ. */
    (*env)->DeleteLocalRef(env, actualClass);
}
~~~

Trong ví dụ, `receiver` và `value` là local references do JVM cung cấp làm tham số; `actualClass` là local reference mới do `GetObjectClass` tạo. Thông thường không cần xóa thủ công các tham số do Java truyền ở cuối một native method ngắn; `actualClass` có thể được xóa sớm vì không còn cần. JVM dọn phần còn lại khi native method return.

**Không nhầm “biến C cục bộ” với “local JNI reference”.** Biến `jobject ref` có thể đặt trên stack C, trong struct hoặc bị copy sang biến C khác. **Phạm vi C của biến không xác định tính hợp lệ của JNI reference**; hợp đồng về thread và JNI frame mới là điều quyết định.

## 3. Vòng đời theo một lần Java gọi native method

Giả sử Java gọi hai lần:

~~~text
Java thread T
  |
  +-- gọi native method lần 1
  |      +-- JVM cung cấp JNI frame F1
  |      +-- tham số jobject/jstring là local references của F1
  |      +-- FindClass / GetObjectClass tạo local refs mới
  |      +-- mã C sử dụng những refs hợp lệ
  |      +-- native method return
  |      +-- JVM giải phóng local refs của F1
  |
  +-- gọi native method lần 2
         +-- JVM cung cấp JNI frame F2 riêng
         +-- tạo local refs mới cho lượt gọi này
         +-- refs thuộc F1 không sống lại
~~~

Những điều cần hiểu:

- **Hai lần gọi liên tiếp, dù ở cùng một Java thread, là hai phạm vi local reference khác nhau.** Một local `jobject` lấy từ lần 1 không được cache rồi dùng vào lần 2.
- Return của native method không hủy toàn bộ Java object mà nó từng nhìn thấy; chỉ chấm dứt các JNI local handles thuộc invocation đó.
- JVM xử lý đặc biệt **giá trị `jobject` trả về từ native method**, để Java nhận được object hợp lệ ở phía gọi. Vì vậy có thể return local `jstring` vừa tạo mà **không cần** biến nó thành global reference.
- Một local reference đã được `DeleteLocalRef` thì hết hiệu lực **ngay tại thời điểm xóa**, không cần đợi native method kết thúc.
- Nếu `PushLocalFrame` và `PopLocalFrame` được dùng trong lượt gọi, local refs của frame con mất hiệu lực khi pop, có thể sớm hơn lúc native method return.

### Trả Java object qua ranh giới native method

Mẫu hợp lệ:

~~~c
/* Ví dụ thân của một JNI native method trả jstring. */
JNIEXPORT jstring JNICALL Java_Example_makeMessage(
        JNIEnv *env, jclass owner) {
    (void) owner;
    return (*env)->NewStringUTF(env, "hello");
}
~~~

`NewStringUTF` trả local `jstring`. JVM nhận object làm kết quả Java trước khi dọn local frame. Sau lời gọi, Java có thể lưu String vào field hoặc biến, không cần global JNI reference.

**Không được** tạo một local `jstring`, gọi `DeleteLocalRef` với handle ấy rồi mới return lại handle đã bị xóa. Nếu muốn dọn frame lồng nhau mà vẫn trả object, dùng `PopLocalFrame(env, result)` và **giá trị trả về của hàm này** (xem mục 6).

## 4. Vòng đời theo thread: điều “local” thực sự ràng buộc

`JNIEnv*` là giao diện JNI gắn với **thread hiện tại**. Tương tự, một **local `jobject` chỉ có hiệu lực ở thread tạo ra nó**. Nó không trở thành reference dùng chung chỉ vì C có thể chép vài byte của biến sang thread khác.

~~~text
Java thread T1                     Java thread T2
------------------                 --------------------
JNIEnv* env1                       JNIEnv* env2
local jobject obj1                 local jobject obj2

obj1 chỉ hợp lệ trên T1            obj2 chỉ hợp lệ trên T2

T1 truyền trực tiếp obj1 cho T2    -> SAI HỢP ĐỒNG JNI
T1 truyền trực tiếp env1 cho T2    -> SAI HỢP ĐỒNG JNI
~~~

**Ngay cả khi T1 và T2 cùng truy cập một Java object**, mỗi thread vẫn cần **một JNI reference hợp lệ trong ngữ cảnh của chính mình** hoặc có thể truy cập object thông qua cơ chế JVM/Java đúng quy định. Khi cần chia sẻ tham chiếu JNI qua thread, cách thường dùng là tạo **global reference** hợp lệ (`NewGlobalRef`) rồi, nếu cần, tạo một local reference mới trong thread nhận (`NewLocalRef`).

Một local reference hợp lệ trên T1 cũng không tự động được phép dùng bằng `JNIEnv*` của T2. Tách hai khái niệm:

1. **JNI reference thuộc thread nào?** T1/T2; local refs không được dùng xuyên thread.
2. **Java object có thread-safe không?** Dù global ref chia sẻ hợp lệ, dữ liệu bên trong object vẫn có thể cần lock, immutable state hoặc cơ chế đồng bộ Java tương ứng.

Ngoài ra, `JavaVM*` là interface dùng ở cấp JVM có thể được chia sẻ với thread để lấy `JNIEnv*` đúng thread thông qua `AttachCurrentThread`/`GetEnv`, tùy thread đã attached hay chưa. Không cache `JNIEnv*` của thread A để dùng ở thread B.

## 5. Chương trình hoàn chỉnh Java 17 + JNI: một native method, nhiều lần gọi và nhiều thread

Ví dụ sau chạy trên **Linux + JDK 17+ + trình biên dịch GCC tương thích kiến trúc JVM**. Chương trình cho thấy Java gọi cùng một native method lần lượt trên thread chính và một Java thread khác. Mỗi lần gọi có local references riêng. Một hàm native khác trả `jstring` hợp lệ về Java.

### 5.1. `LocalRefLifetimeDemo.java`

~~~java
public final class LocalRefLifetimeDemo {
    static {
        System.loadLibrary("localrefs");
    }

    private static native int sumUtf16Lengths(String[] labels);

    private static native String nativeGreeting();

    public static void main(String[] args) throws InterruptedException {
        String[] mainLabels = {"JNI", "local", null};

        System.out.println(
                "mainSum=" + sumUtf16Lengths(mainLabels));
        System.out.println(
                "message=" + nativeGreeting());

        Thread worker = new Thread(() -> {
            String[] workerLabels = {"thread", "JNI"};
            int total = sumUtf16Lengths(workerLabels);
            System.out.println("workerSum=" + total);
        }, "jni-worker");

        worker.start();
        worker.join();
    }
}
~~~

### 5.2. `localrefs.c`

~~~c
#include <jni.h>
#include "LocalRefLifetimeDemo.h"

JNIEXPORT jint JNICALL Java_LocalRefLifetimeDemo_sumUtf16Lengths(
        JNIEnv *env, jclass owner, jobjectArray labels) {
    (void) owner;

    if (labels == NULL) {
        jclass npe = (*env)->FindClass(
                env, "java/lang/NullPointerException");
        if (npe != NULL) {
            (*env)->ThrowNew(env, npe, "labels must not be null");
            (*env)->DeleteLocalRef(env, npe);
        }
        return 0;
    }

    jsize n = (*env)->GetArrayLength(env, labels);
    jint total = 0;

    for (jsize i = 0; i < n; i++) {
        /* Mỗi lần gọi có thể tạo một local JNI reference. */
        jobject item = (*env)->GetObjectArrayElement(
                env, labels, i);

        if ((*env)->ExceptionCheck(env)) {
            return 0; /* Để pending exception đi ngược về Java. */
        }

        if (item != NULL) {
            total += (*env)->GetStringLength(
                    env, (jstring) item);

            /* Dọn ngay, không giữ tới cuối vòng lặp lớn. */
            (*env)->DeleteLocalRef(env, item);
        }
    }

    return total;
}

JNIEXPORT jstring JNICALL Java_LocalRefLifetimeDemo_nativeGreeting(
        JNIEnv *env, jclass owner) {
    (void) owner;

    /* Trả local jstring về Java là hợp lệ. */
    return (*env)->NewStringUTF(env, "hello from JNI");
}
~~~

Lý do những dòng chính hợp lệ:

- Java khai báo method `static native` nên đối số JNI thứ hai là `jclass owner`. Method instance sẽ nhận `jobject receiver` ở vị trí này.
- `String[]` ánh xạ thành `jobjectArray`, **không phải `jstring*`**. Mỗi lần `GetObjectArrayElement` trả object khác `NULL` là một local JNI reference mới.
- Vì Java bảo đảm mảng là `String[]`, phần tử không null có thể dùng với `GetStringLength` qua cast `(jstring) item`. Hàm trả số **đơn vị mã UTF-16**, không nhất thiết số Unicode code points.
- `DeleteLocalRef` được gọi **trong vòng lặp** sau khi xong từng phần tử; điều này quan trọng khi số phần tử rất lớn, vì native frame không tự dọn từng local ref ở mỗi lần lặp.
- `nativeGreeting` trả local `jstring` sang Java, được JVM xử lý khi native method kết thúc; Java nhận một đối tượng String hợp lệ.

Ví dụ dùng dữ liệu đầu vào rất nhỏ để không bị tràn `jint total`. Khi viết API tổng quát, cần xác định giới hạn độ dài/tổng và chọn kiểu Java/JNI phù hợp.

### 5.3. Biên dịch và chạy

Tạo hai tệp ở cùng thư mục. Đặt `JAVA_HOME` trỏ đến JDK 17+ và chạy:

~~~bash
javac -h . LocalRefLifetimeDemo.java
gcc -fPIC -shared \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  -o liblocalrefs.so localrefs.c
java -Djava.library.path=. LocalRefLifetimeDemo
~~~

Stdout **chính xác** trên Linux với các điều kiện trên:

~~~text
mainSum=8
message=hello from JNI
workerSum=9
~~~

Kiểm tra số liệu: `"JNI"` có 3 UTF-16 units, `"local"` có 5, null không cộng nên lần đầu tổng `8`. `"thread"` có 6, `"JNI"` có 3 nên lần trên worker thread là `9`. `worker.join()` bảo đảm dòng kết quả của worker được in xong trước khi `main` thoát và các dòng trước `start()` đã được in theo thứ tự.

**Lưu ý quan trọng:** Hai lần gọi trong chương trình **không chia sẻ local JNI reference nào**. Ví dụ cho thấy cách hợp lệ để mỗi thread nhận JNI parameters mới và tạo/xóa local references của mình; cố truyền một raw `jobject` từ native invocation đầu sang invocation sau sẽ là lỗi dù output có vẻ bình thường trên một JVM.

Trên macOS, dùng JNI header `$JAVA_HOME/include/darwin`, tạo thư viện dạng `liblocalrefs.dylib` với tùy chọn liên kết thích hợp như `clang -dynamiclib`. Trên Windows, sử dụng `localrefs.dll` và include `%JAVA_HOME%\include\win32`, với toolchain đúng CPU/ABI. Tên native symbol lấy từ header sinh bởi `javac -h` để tránh sai package, overload và JNI name mangling.

## 6. Thu hồi sớm: `DeleteLocalRef`, `EnsureLocalCapacity` và local frame

JVM **tự thu hồi local references lúc native method trả về**, nhưng không phải lúc từng vòng lặp kết thúc. Giả sử:

~~~c
/* Mẫu không tốt trong native method xử lý rất nhiều phần tử. */
for (jsize i = 0; i < n; i++) {
    jobject obj = (*env)->GetObjectArrayElement(env, values, i);
    /* Xử lý obj, nhưng quên DeleteLocalRef... */
}
~~~

Với `n` lớn, vòng lặp có thể tích lũy rất nhiều local handles trong cùng native frame, gây áp lực bộ nhớ/bảng tham chiếu hoặc lỗi JNI. Đừng suy luận rằng biến C `obj` được gán lại thì local reference của vòng lặp cũ cũng mất; **biến bị ghi đè không xóa JNI reference**.

Mẫu hợp lý cho thao tác ngắn:

~~~c
/* Minh họa thân một native method, values là jobjectArray hợp lệ. */
jsize n = (*env)->GetArrayLength(env, values);

for (jsize i = 0; i < n; i++) {
    jobject obj = (*env)->GetObjectArrayElement(
            env, values, i);

    if ((*env)->ExceptionCheck(env)) {
        return; /* Chữ ký minh họa giả định return void. */
    }

    if (obj != NULL) {
        /* Xử lý obj khi còn hợp lệ... */
        (*env)->DeleteLocalRef(env, obj);
    }
}
~~~

Ba API dùng để quản lý capacity và frame:

| JNI API | Ý nghĩa | Trường hợp sử dụng |
| --- | --- | --- |
| `DeleteLocalRef(env, ref)` | Xóa **một local reference** cụ thể | Dọn object đã xử lý xong, nhất là trong vòng lặp |
| `EnsureLocalCapacity(env, capacity)` | Yêu cầu JVM đảm bảo khả năng tạo thêm ít nhất `capacity` local references | Chuẩn bị cho đoạn mã dùng nhiều local refs; kiểm tra kết quả lỗi |
| `PushLocalFrame(env, capacity)` | Tạo frame con cho local refs, đảm bảo capacity ban đầu | Gom một lượt tính toán/batch có nhiều local refs |
| `PopLocalFrame(env, result)` | Dọn refs của frame con; có thể **giữ lại một object kết quả** trong frame trước | Kết thúc batch mà chỉ trả một reference cần thiết |

Theo JNI specification, trước khi vào native method, JVM bảo đảm chỗ cho **ít nhất 16 local references**. Giới hạn thực tế và cách xử lý tràn có thể thay đổi giữa JVM; không viết code dựa trên giả định có thể tích lũy vô hạn. `EnsureLocalCapacity` hoặc `PushLocalFrame` có thể báo lỗi (thường kèm pending `OutOfMemoryError`) nếu JVM không cấp đủ tài nguyên; phải kiểm tra giá trị trả về.

### Giữ một kết quả sau `PopLocalFrame`

Mẫu **chỉ minh họa thân native method trả `jstring`**, không phải chương trình C độc lập:

~~~c
if ((*env)->PushLocalFrame(env, 8) < 0) {
    return NULL; /* Có thể có pending OutOfMemoryError. */
}

jstring inside = (*env)->NewStringUTF(env, "result");

/* Dọn frame con, chuyển kết quả về frame cha. */
return (jstring) (*env)->PopLocalFrame(env, inside);
~~~

- `inside` ban đầu là local reference trong frame con.
- `PopLocalFrame` dọn các local references của frame con và trả **một reference mới** tới cùng object ở frame trước, nếu có kết quả hợp lệ.
- Giá trị `inside` cũ hết hiệu lực sau khi pop. Chỉ được sử dụng **giá trị mà `PopLocalFrame` trả về**.
- Nếu tạo String thất bại, có thể có pending exception; `PopLocalFrame` là thao tác dọn frame cho phép thực hiện trong trường hợp phù hợp và kết quả sẽ là `NULL`.

`DeleteLocalRef` và `PopLocalFrame` **không phải giải phóng trực tiếp `malloc`/`free` của vùng nhớ native**; chúng giải phóng JNI handles. Tương tự, `GetStringUTFChars`/`GetIntArrayElements` trả **con trỏ dữ liệu tạm có API release riêng** (`ReleaseStringUTFChars`/`ReleaseIntArrayElements`), không được nhầm với `DeleteLocalRef`.

## 7. Native thread tự attach: ranh giới vòng đời khác với native method

Xem hai tình huống:

**Tình huống A: Java tạo Thread, rồi Thread gọi native method.**

~~~text
Java Thread -> native method JNI -> JNI local refs
            -> native method return -> JVM tự thu hồi local refs của call
~~~

Đây là cách chương trình `LocalRefLifetimeDemo` hoạt động. Mỗi Java thread có ngữ cảnh JNI riêng. Native method invocation vẫn có phạm vi call rõ ràng và JVM thu hồi local refs của invocation khi nó return.

**Tình huống B: C/C++ tạo một OS/native thread, rồi attach vào JVM.**

~~~text
Native thread được C/C++ tạo
    |
    +-- AttachCurrentThread(JavaVM*, ...) -> nhận JNIEnv* riêng
    |
    +-- nhiều lần gọi JNI API, tạo local refs
    |   (C function return KHÔNG tự động là JNI native-method boundary)
    |
    +-- DeleteLocalRef / PushLocalFrame + PopLocalFrame khi hoàn tất
    |
    +-- DetachCurrentThread -> chấm dứt attachment và refs còn lại
~~~

Theo JNI specification, **local references tạo trên native thread đã attach không tự động biến mất mỗi lần một hàm C helper trả về**. Nếu thread chạy lâu, không nên đợi tới `DetachCurrentThread` mới để JVM dọn tất cả; phải chủ động quản lý refs.

Với code native quản lý thread:

- Có thể giữ `JavaVM*` để các thread lấy `JNIEnv*` riêng. `JNIEnv*` **không share** giữa các thread.
- Native thread muốn gọi JNI trước tiên phải attach nếu chưa được attach; thread đã attach có thể dùng `GetEnv`/`AttachCurrentThread` theo hợp đồng.
- Đối với local refs tạo trong long-running native thread, dùng `DeleteLocalRef` trong vòng lặp hoặc `PushLocalFrame`/`PopLocalFrame` để giới hạn tài nguyên.
- Trước khi native thread kết thúc, detach đúng quy định; không giữ local JNI refs sau detach.
- Khi Java callback chạy trong một thread được attach, ranh giới call và callback có thể lồng nhau; vẫn phân biệt local frame nào sở hữu từng reference.

Chú ý: `AttachCurrentThread` không khiến một handle local được tạo ở thread khác bỗng hợp lệ trong thread vừa attach. Attach chỉ cung cấp **một JNI context hợp lệ cho chính thread hiện tại**.

## 8. Nếu cần dùng object ở một lần gọi khác hoặc thread khác

### 8.1. Dùng global reference, rồi thu hồi đúng lúc

Local reference **không được cache** cho lời gọi JNI sau hoặc thread khác. Nếu cần giữ một Java object qua các ranh giới đó:

1. Trong khi local reference còn hợp lệ, gọi `NewGlobalRef(env, local)`.
2. Giữ global reference trong cấu trúc có ownership và đồng bộ thích hợp.
3. Khi một thread khác đã attach vào JVM và có `JNIEnv*` của chính nó, có thể sử dụng global reference; khi cần một local reference trong thread đó, gọi `NewLocalRef(env, global)`.
4. Khi không còn người dùng, gọi `DeleteGlobalRef(env, global)` chính xác một lần theo thiết kế ownership. Đảm bảo không có lượt truy cập đang diễn ra.

Ví dụ mã JNI **minh họa rời**, không phải chương trình C độc lập và chưa có phần locking/thread lifecycle:

~~~c
/* Trong thread T1, local thuộc invocation hiện hành: */
jobject shared = (*env)->NewGlobalRef(env, local);
if (shared == NULL) {
    /* Có thể thiếu bộ nhớ; không sử dụng shared. */
}

/* Sau khi chuyển shared theo giao thức đồng bộ cho thread T2
   và T2 đã có JNIEnv* env2 của chính nó: */
jobject mine = (*env2)->NewLocalRef(env2, shared);
if (mine != NULL) {
    /* Sử dụng mine chỉ trong T2, trong phạm vi hợp lệ. */
    (*env2)->DeleteLocalRef(env2, mine);
}

/* Khi tất cả người sử dụng đã dừng, một bên sở hữu dọn global: */
(*env2)->DeleteGlobalRef(env2, shared);
~~~

Đừng copy đoạn trên nguyên xi vào ứng dụng đa luồng: nó **thiếu triển khai đồng bộ, trao đổi handle, báo lỗi và xác định thread nào dọn**, vì mục đích chỉ trình bày loại reference đúng. Trong thực tế, `NewGlobalRef` có thể thất bại; nếu Java exception đang pending phải xử lý theo hợp đồng; cần bảo vệ trạng thái của biến chứa global ref khỏi use-after-delete.

**Global reference là strong reference**, nên có thể ngăn GC thu hồi Java object nếu quên `DeleteGlobalRef`. Nếu cần tham chiếu yếu không giữ object sống, JNI có **weak global reference** (`NewWeakGlobalRef`, `DeleteWeakGlobalRef`); khi sử dụng phải xem đích có còn sống và thường promote qua `NewLocalRef` rồi kiểm tra `NULL`. Weak global **không** trở thành một local ref dùng xuyên thread.

### 8.2. Không cần global ref nếu có thể truyền object lại từ Java

Nếu Java đã giữ object trong biến, field hoặc một cấu trúc đồng bộ an toàn, cách đơn giản thường là **truyền object lại làm đối số** ở lượt gọi native tiếp theo. JVM sẽ cấp **local JNI reference mới hợp lệ** cho invocation đó.

~~~text
Java giữ object trong field
   -> gọi native lần 1: local JNI ref #1 (hết hạn khi return)
   -> gọi native lần 2: local JNI ref #2 (mới, cùng Java object)
~~~

Thiết kế này thường tránh việc native code phải quản lý global ref dài hạn. Nếu native cần dùng object bất đồng bộ, sau khi lời gọi Java trả về, global ref (hoặc cơ chế quản lý ownership tương đương) mới thực sự cần thiết.

## 9. Một số bẫy về local reference

### 9.1. Lưu local ref vào biến C static để dùng sau

~~~c
/* SAI: local reference sẽ hết hiệu lực sau native return. */
static jobject cached = NULL;

void unsafeStore(jobject local) {
    cached = local;
}
~~~

Việc gán giá trị `jobject` vào biến static **không tạo global reference**. Sau khi native invocation kết thúc, `cached` chỉ là bản sao của JNI handle cũ, không còn quyền truy cập object. Có thể gây lỗi JNI, crash hoặc hành vi bất định. Cách đúng là tạo `NewGlobalRef` trong lúc local còn hiệu lực và có quy tắc dọn global rõ ràng.

### 9.2. Copy local handle bằng phép gán rồi xóa một alias

~~~c
/* SAI nếu tiếp tục sử dụng alias sau DeleteLocalRef. */
jobject alias = local;
(*env)->DeleteLocalRef(env, local);
/* alias cũng chỉ là bản sao handle vừa bị hủy. */
~~~

**Gán biến C không tạo JNI reference mới**. Nếu cần hai local handles độc lập cùng chỉ tới object, dùng `NewLocalRef(env, local)` để tạo handle mới; lúc đó `IsSameObject` có thể xác định hai handle tham chiếu cùng Java object.

### 9.3. Dùng local `jclass` xuyên invocation hoặc thread

~~~c
/* SAI: lưu jclass local do FindClass trả về vào biến static. */
static jclass cachedClass;
cachedClass = (*env)->FindClass(env, "java/lang/String");
~~~

`jclass` là một **JNI object reference**; nó tuân theo cùng quy tắc local/global. Nếu muốn cache `Class` dài hạn, cần một global `jclass` và quy tắc release; lưu ý global refs có thể giữ class/class loader sống lâu hơn mong đợi, đặc biệt trong hệ thống plugin hoặc deployment hot-reload.

### 9.4. Nhầm “local trong JNI” với “local của Java method”

Biến Java `String name` trong Java method tồn tại theo quy tắc tham chiếu và tối ưu của Java/JVM. JNI local reference là **handle trong JNI frame của native thread**. Hai biến có thể trỏ cùng object, nhưng xóa local JNI reference **không** làm null biến Java và không “free” Object theo ý native code.

### 9.5. Dùng `jobject` giống như C pointer

`jobject` là opaque reference; không `free(jobject)`, không `delete jobject`, không đọc field bằng offset trong `struct` và không thực hiện pointer arithmetic. Dùng `GetObjectClass`, `GetFieldID`, `GetObjectField`, `CallObjectMethod`, `IsSameObject` hoặc API JNI thích hợp. Nếu có native pointer lưu trong một field `long` của Java, đó là **một native handle riêng**, không phải local JNI reference; ownership và an toàn của nó phải được thiết kế riêng.

### 9.6. So sánh hai handles bằng toán tử con trỏ

Hai JNI references khác handle vẫn có thể trỏ cùng Java object. Không dùng `a == b` để xác định **object identity**; dùng `IsSameObject(env, a, b)` cho các references hợp lệ. Không dùng `GetObjectRefType`/`IsSameObject` để “kiểm tra” một handle đã `DeleteLocalRef` hoặc hết hiệu lực; gọi JNI với invalid reference đã là lỗi.

### 9.7. Cứ để JVM dọn tất cả cuối method

Native method xử lý vài refs ngắn hạn có thể dựa vào cleanup khi return. Nhưng nếu gọi `GetObjectArrayElement` hàng triệu lần, việc không xóa local refs mỗi lượt có thể làm tăng số handles giữ sống trong cùng native frame. Dùng `DeleteLocalRef` ngay khi xong, hoặc `PushLocalFrame`/`PopLocalFrame` cho từng batch.

### 9.8. Gặp exception nhưng tiếp tục tạo reference

Một số JNI calls có thể tạo pending Java exception. Khi gặp kết quả lỗi, dừng đường xử lý bình thường, chỉ dùng nhóm API cho phép khi exception đang pending để quan sát/cleanup/propagate. Không tiếp tục dereference dữ liệu lỗi hoặc tự ý gọi hàng loạt JNI operations. `ExceptionCheck` giúp phát hiện exception; `DeleteLocalRef` và `PopLocalFrame` hỗ trợ cleanup theo hợp đồng. **Không xóa Java exception rồi trả trạng thái thành công tùy tiện.**

## 10. Local references và garbage collector (GC)

Trong JNI, local references thông thường là **strong references** trong thời gian hợp lệ: JVM phải tính đến việc native code vẫn có thể dùng chúng. Điều này có thể kéo dài khả năng sống của Java object trong khoảng native call hoặc trong một native thread đã attach mà local handles chưa được xóa.

Ví dụ:

~~~text
Java object O
  ^
  |   Local ref L1 (thread T1, native frame F1)
  |   Local ref L2 (thread T1, native frame F1)
  |
  +-- Khi cả L1 và L2 hợp lệ, JVM biết native code có thể dùng O.
  +-- DeleteLocalRef(L1): O vẫn được giữ bởi L2.
  +-- DeleteLocalRef(L2): nếu không còn strong root khác,
      O trở thành đối tượng có thể được GC thu hồi.
~~~

**“Có thể được thu hồi” không có nghĩa “GC lập tức thu hồi”**. JVM quyết định khi nào chạy GC và có thể giữ object vì các strong references khác.

Khác biệt giữa các loại handle:

| Đặc tính | Local reference | Global reference | Weak global reference |
| --- | --- | --- | --- |
| Đối tượng có được giữ mạnh không? | Thông thường có, trong phạm vi local hợp lệ | Có, đến khi xóa global ref | Không giữ object sống một mình |
| Có dùng trực tiếp ở thread khác không? | **Không** | Có, với `JNIEnv*` của thread được attach | Cần xử lý weak semantics, thường promote bằng local ref |
| Khi nào hết hiệu lực? | Khi `DeleteLocalRef`, frame bị pop hoặc native invocation kết thúc; attached native thread có ngoại lệ đến detach | `DeleteGlobalRef` | `DeleteWeakGlobalRef` hoặc đích có thể được GC xóa |
| Nguy cơ khi quên dọn | Tích lũy handles ở vòng lặp/native thread dài hạn | Giữ object và class loader không cần thiết | Rò bookkeeping native; đích có thể đã bị GC xóa |

JNI references chỉ là một phần trong bài toán quản lý bộ nhớ: buffer từ `GetStringUTFChars` hoặc `GetIntArrayElements` có **quy tắc release khác**; `malloc` và direct native memory có **ownership khác**. Không thay thế các API release cho nhau.

## 11. Checklist thiết kế cho hai ranh giới lời gọi và thread

Khi một native method tạo hoặc nhận một Java object reference, đặt các câu hỏi sau:

1. **Reference được tạo bởi hàm JNI nào?** Có phải local `jobject` mới do `GetObjectClass`/`FindClass`/`NewObject`/`GetObjectArrayElement` trả về không?
2. **Người dùng cuối của reference là ai?** Native call hiện tại, Java caller, callback đồng bộ, hay một thread/queue sẽ chạy sau?
3. **Thread có đổi không?** Nếu cần đưa object sang thread khác, không đưa trực tiếp local handle; thiết kế global ref hoặc truyền object lại qua Java.
4. **Lời gọi có kết thúc trước khi object được dùng tiếp không?** Nếu có, phải có tham chiếu dài hạn phù hợp hoặc để Java sở hữu và truyền lại.
5. **Có tạo ref trong vòng lặp dài không?** Dùng `DeleteLocalRef` hoặc local frames để giảm áp lực.
6. **Native thread có tự attach không?** Cần `JNIEnv*` riêng; dọn local refs rõ ràng thay vì đợi detach của thread dài hạn.
7. **Có xử lý exception/cleanup đầy đủ không?** Đường lỗi cũng phải release các handles và buffers mà code đã lấy hợp lệ.
8. **Đang dọn handle hay vùng nhớ?** `DeleteLocalRef` không giải phóng object Java bằng `free` hoặc native buffer.
9. **Đã tài liệu hóa ownership chưa?** Nếu tạo global ref, ai `DeleteGlobalRef`, ở thời điểm nào, làm sao tránh double-delete khi nhiều thread?
10. **Đã kiểm tra bằng công cụ chưa?** Trên HotSpot có thể chạy với `-Xcheck:jni` để phát hiện một số lỗi JNI, kết hợp test nhiều lần gọi và đa luồng.

Khi kiểm tra lỗi thật, hãy log theo **thread, tên native method và thời điểm tạo/xóa reference** ở mức phù hợp, nhưng **không** log hoặc xuất bản giá trị handle như thể đó là địa chỉ Java object cố định.

## 12. Tình huống so sánh trước và sau

Giả sử một native method xử lý 100.000 chuỗi trong một mảng Java.

**Trước:**

~~~c
/* Minh họa: tích lũy local refs trong mỗi vòng lặp. */
for (jsize i = 0; i < count; i++) {
    jobject s = (*env)->GetObjectArrayElement(env, array, i);
    if (s != NULL) {
        /* Xử lý s nhưng không dọn local ref. */
    }
}
/* Chỉ khi native method return, JVM mới dọn. */
~~~

Vấn đề: mỗi `GetObjectArrayElement` có thể tạo local ref được giữ tới cuối native method. 100.000 vòng có thể tạo lượng lớn handles không cần thiết.

**Sau:**

~~~c
/* Minh họa: xóa local ref sau khi xong từng phần tử. */
for (jsize i = 0; i < count; i++) {
    jobject s = (*env)->GetObjectArrayElement(env, array, i);
    if ((*env)->ExceptionCheck(env)) {
        return; /* Giả định hàm void. */
    }
    if (s != NULL) {
        /* Xử lý s khi s còn hợp lệ. */
        (*env)->DeleteLocalRef(env, s);
    }
}
~~~

Lợi ích: số JNI local handles sống đồng thời thấp hơn; không phải đợi tới khi native method kết thúc. Đoạn minh họa **không phải hàm hoàn chỉnh**, chưa xử lý toàn bộ trường hợp input `NULL`, giới hạn `count` hoặc lỗi trong logic xử lý. Đừng diễn giải nó như công thức tối ưu cho mọi workload.

Nếu mỗi bước tạo nhiều local refs lồng nhau hoặc nhiều API JNI cần gọi liên tiếp, cân nhắc `PushLocalFrame`/`PopLocalFrame` cho từng batch. Quan trọng vẫn là: **local ref chỉ dùng trong thread và frame hợp lệ**.

## 13. Câu hỏi tự kiểm tra

1. Một Java thread gọi native method hai lần. Có được giữ nguyên local `jobject` tạo ở lần thứ nhất để dùng trong lần thứ hai không? Vì sao?
2. Trong native method, một vòng lặp gọi `GetObjectArrayElement` 50.000 lần. Vì sao không nên chỉ dựa vào cleanup khi method return?
3. Tại sao `jobject copy = original;` không tạo hai JNI references độc lập?
4. `DeleteLocalRef` có lập tức hủy Java object trong heap không?
5. Java tạo hai thread, mỗi thread gọi cùng native method. Có được truyền `JNIEnv*` hoặc local `jobject` của thread thứ nhất sang thread thứ hai không?
6. Native thread được tạo bởi C/C++ rồi `AttachCurrentThread`. Khi một C helper function của thread này return, mọi local refs có tự động được JVM dọn ngay không?
7. Một native method muốn trả một `jstring` vừa tạo bằng `NewStringUTF` cho Java. Có bắt buộc đổi nó thành global ref trước khi return không?
8. `PopLocalFrame(env, result)` khác gì với `DeleteLocalRef(env, result)`?
9. Khi thực sự cần giữ một Java object qua nhiều lượt JNI call và chia sẻ với thread khác, nên dùng loại tham chiếu nào và thu hồi bằng API nào?
10. Một global ref giữ object sống nhưng object chứa trạng thái mutable. Global ref có bảo đảm object thread-safe không?

**Đáp án gợi ý:** (1) không, local ref hết hạn khi lượt gọi đầu kết thúc; (2) các local handles tích lũy trong frame; (3) phép gán chỉ copy handle, muốn ref mới dùng `NewLocalRef`; (4) không, chỉ xóa handle và có thể thay đổi reachability; (5) không, cả hai gắn với thread; (6) không, attached native thread cần explicit cleanup/frames hoặc đợi detach; (7) không, có thể return local JNI result hợp lệ cho JVM; (8) pop dọn toàn bộ frame con và có thể tạo một kết quả ở frame cha, còn delete xóa một handle; (9) `NewGlobalRef` rồi `DeleteGlobalRef` khi hết dùng, có đồng bộ; (10) không, vẫn phải tuân theo Java memory model/đồng bộ.

## 14. Tài liệu tham khảo chính thức

- [Java SE 17 JNI Specification — Design Overview, Global and Local References](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/design.html)
- [Java SE 17 JNI Specification — JNI Functions: Local References](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/functions.html)
- [Java SE 17 JNI Specification — Invocation API (`AttachCurrentThread`, `DetachCurrentThread`)](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/invocation.html)
- [Java SE 17 JNI Specification — JNI Types and Data Structures](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/types.html)

**Điểm cần nắm:** Local JNI reference hợp lệ theo **thread tạo nó** và **frame/lời gọi sở hữu nó**. JVM tự dọn local refs của một native method khi method return, nhưng vòng lặp dài cần dọn sớm; native thread tự attach cần quản lý local refs cho tới khi detach. Muốn giữ Java object qua lượt gọi hoặc thread khác, hãy dùng một thiết kế ownership phù hợp, thường là **global reference** với `NewGlobalRef`/`DeleteGlobalRef`, hoặc để Java giữ object và truyền lại khi cần.
