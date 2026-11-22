# Giải phóng tham chiếu cục bộ trong vòng lặp và lời gọi kéo dài (JNI)

Khi mã native gọi Java qua Java Native Interface (JNI), mỗi tham chiếu tới đối tượng Java do các hàm JNI tạo ra thường là một **local reference**. JVM quản lý những tham chiếu này như các gốc có thể giữ đối tượng Java sống trong quá trình GC. Trong một native method ngắn, phần lớn local reference sẽ được dọn tự động khi hàm trả về. Nhưng nếu hàm native lặp hàng chục nghìn lần, xử lý một batch lớn hoặc chạy rất lâu trước khi trả về, đợi đến cuối lời gọi mới dọn có thể làm đầy bảng local reference, giữ đối tượng không cần thiết sống quá lâu và tiêu tốn bộ nhớ.

Hai thao tác trọng tâm là **`DeleteLocalRef`** (xóa một local reference cụ thể) và cặp **`PushLocalFrame` / `PopLocalFrame`** (quản lý một nhóm local reference theo phạm vi). Chúng phục vụ mục tiêu khác với `free()` của C hoặc `ReleaseStringUTFChars`: xóa một JNI reference **không đồng nghĩa trực tiếp với việc giải phóng đối tượng Java hay native buffer**.

Bài học thuộc nhóm **Tham chiếu và GC** trong Java Advance — native-interoperability, tập trung vào cơ chế, lựa chọn API, xử lý lỗi và thực hành đúng với Java 17+ cùng C11.

## 1. Local reference là gì và tồn tại đến khi nào?

Tham chiếu JNI là một **handle opaque** cho phép JVM định vị đối tượng Java ngay cả khi GC có thể di chuyển đối tượng đó. Không diễn giải `jobject`, `jclass`, `jstring` hay `jarray` thành con trỏ C trỏ trực tiếp vào cấu trúc Java object.

Các nguồn local reference thường gặp:

- Đối tượng và class được truyền vào native method, ví dụ `jobject self`, `jclass clazz`, `jstring name`, `jobjectArray items`.
- Kết quả trả về từ `GetObjectArrayElement`, `GetObjectClass`, `FindClass`, `NewStringUTF`, `NewObject`, `CallObjectMethod`, `NewLocalRef`.
- Một local reference được tạo trong local frame lồng nhau bởi `PushLocalFrame`.

Không phải mọi kết quả JNI đều là local reference. `jint`, `jlong` và `jboolean` chỉ là giá trị primitive; `jmethodID`/`jfieldID` là ID opaque, không phải `jobject`; pointer trả về từ `GetStringUTFChars` hoặc `GetByteArrayElements` cần cặp hàm release riêng.

### 1.1. Vòng đời mặc định

Với **native method do Java gọi vào**, JVM tự tạo một phạm vi local reference cho invocation đó. Các local reference thuộc invocation còn hợp lệ trong thread hiện tại cho đến khi bị xóa tường minh hoặc khi native method trả về Java. Trả về một local `jstring` hợp lệ cho Java là một tình huống được JNI hỗ trợ; không cần chuyển thành global reference để trả kết quả.

Trong một vòng lặp ở bên trong cùng native method, **một lần lặp kết thúc không tự dọn local reference**. Cái tự dọn theo lời gọi là lúc native method **trả về**, không phải khi biến C rời lexical scope hoặc khi vòng lặp chuyển iteration.

Với **thread native tự attach** vào JVM qua `AttachCurrentThread`, việc có `JNIEnv *` không tạo một điểm dọn tự động cho từng vòng lặp C. Các local reference phát sinh trong thread gắn bằng Invocation API có thể còn tồn tại đến lúc `DetachCurrentThread` nếu không được xóa hoặc quản lý bằng local frames. Thread tồn tại lâu vì vậy càng cần dọn rõ ràng.

### 1.2. Tham chiếu giữ GC root, nhưng không sở hữu đối tượng như con trỏ C

Một local reference còn hợp lệ là một đường tham chiếu mạnh cho JVM xét khi GC. `DeleteLocalRef(env, ref)` xóa **đường tham chiếu JNI đó**. Nó **không lập tức gọi destructor**, không bảo đảm object bị GC ngay, và không xóa các strong reference khác từ Java stack, field, array hay global JNI references.

Ví dụ: khi `GetObjectArrayElement` đọc phần tử của một `String[]`, việc xóa local reference tới phần tử **không làm phần tử biến mất khỏi array**. Array vẫn giữ đối tượng; tác dụng trực tiếp của `DeleteLocalRef` ở đây là thu hồi một **slot/handle JNI** và tránh cộng dồn local roots do native code tạo.

Ngược lại, nếu JNI `NewStringUTF` tạo một String tạm rồi không còn Java/global reference nào khác, xóa local reference sớm có thể khiến String trở thành đối tượng đủ điều kiện GC, tùy các root còn lại.

## 2. Vì sao vòng lặp native dễ tích lũy local reference?

Xét mã C JNI sau (chỉ minh họa lỗi, không phải chương trình độc lập):

```c
jsize n = (*env)->GetArrayLength(env, values);

for (jsize i = 0; i < n; ++i) {
    jstring s = (jstring)(*env)->GetObjectArrayElement(env, values, i);
    if (s != NULL) {
        /* Xử lý s. */
    }
    /* Thiếu DeleteLocalRef(env, s). */
}
```

Mỗi lần `GetObjectArrayElement` trả một đối tượng khác `NULL`, nó tạo một local reference. Gán lại `s` ở lần lặp sau **không giải phóng tham chiếu cũ**. Một native method xử lý 100.000 phần tử có thể tạo lượng lớn local reference đang sống đồng thời, dù tại mỗi thời điểm chương trình C chỉ cần một phần tử.

JNI bảo đảm dự trữ tối thiểu **16 local reference slots** khi vào native method. Đây **không phải giới hạn tổng số ref cứng**: VM có thể cấp thêm; khi vượt giới hạn, bạn có thể thấy cảnh báo hoặc lỗi hết bộ nhớ, thậm chí lỗi nghiêm trọng khi không còn cấp phát được slot. Không dựa vào khả năng tự nới bảng của một JVM cụ thể.

Sửa ở mức iteration:

```c
jsize n = (*env)->GetArrayLength(env, values);

for (jsize i = 0; i < n; ++i) {
    jobject element = (*env)->GetObjectArrayElement(env, values, i);
    if ((*env)->ExceptionCheck(env)) {
        return; /* Kiểu trả về void trong mã minh họa này. */
    }

    if (element != NULL) {
        /* Xử lý element khi reference còn sống. */
        (*env)->DeleteLocalRef(env, element);
    }
}
```

Mẫu này giữ số local reference tạm do vòng lặp tạo ra gần như **O(1)** thay vì tăng theo số phần tử **O(n)**. Nó không tự xóa các local references do các hàm con tạo ra rồi quên, nên nếu gọi `FindClass`, `GetObjectClass`, `NewStringUTF` hay các method trả object bên trong vòng lặp, phải dọn cả các ref đó.

## 3. Dùng `DeleteLocalRef` đúng cách

Prototype của JNI ở phía C:

```c
void DeleteLocalRef(JNIEnv *env, jobject localRef);
```

Nguyên tắc:

1. Xóa local reference **sau lần dùng cuối cùng**, trước khi cấp các local refs tiếp theo trong vòng lặp lớn.
2. `DeleteLocalRef(env, NULL)` là no-op theo JNI, nên dùng cho đường cleanup có thể có `NULL` là hợp lệ.
3. Sau khi xóa, biến C vẫn chứa bit/handle cũ. **Không gọi hàm JNI khác với reference đó nữa**; nếu cần giảm nguy cơ vô tình dùng lại, gán biến local thành `NULL`.
4. Nếu hai local references riêng `a` và `b` trỏ cùng một Java object (ví dụ tạo `b = NewLocalRef(env, a)`), xóa `a` **không làm `b` tự mất hiệu lực**. Quản lý từng handle, không lấy danh tính Java object để quyết định “đã xóa rồi”.
5. Chỉ dùng `DeleteLocalRef` với **local** reference. Global reference phải đi với `DeleteGlobalRef`; weak global reference phải đi với `DeleteWeakGlobalRef`.
6. Không xóa local reference rồi trả chính handle đã xóa làm kết quả native method. Nếu cần trả về Java, giữ reference hợp lệ hoặc dùng `PopLocalFrame(env, result)` để chuyển kết quả qua frame.
7. Các tham số object do Java truyền vào JNI cũng là local references, nhưng thông thường để JVM tự dọn ở cuối lời gọi; chỉ xóa tường minh khi chắc chắn sẽ không dùng tham số ấy thêm.
8. Local references chỉ hợp lệ trong **thread tạo ra chúng**. Không truyền `jobject` local sang pthread hoặc lưu vào biến global C để dùng sau khi native method kết thúc.

Điểm quan trọng đối với GC: xóa `ref` không bảo đảm đối tượng được thu gom ngay, vì Java hoặc JNI có thể vẫn giữ các reference khác. Trái lại, chỉ gán `ref = NULL` trong C không bảo đảm slot JNI được thu hồi; phải gọi `DeleteLocalRef` hoặc pop frame.

## 4. Ví dụ hoàn chỉnh Java 17 + C11: xử lý 100.000 phần tử

Ví dụ dùng hai native method để thấy rõ hai cách quản lý:

- `nativeCountNonEmpty` duyệt **toàn bộ** array, tạo một local reference cho mỗi String khác `null`, gọi `DeleteLocalRef` ở mỗi iteration.
- `nativeFirstNonEmpty` dùng `PushLocalFrame` để mở phạm vi reference con; khi gặp String cần trả về Java, gọi `PopLocalFrame(env, result)` giữ **một** reference kết quả hợp lệ ở frame cha.

Chuỗi rỗng (`""`) bị bỏ qua; `null` cũng bị bỏ qua. Độ dài dùng `GetStringLength` (đơn vị **UTF-16 code units**), đủ để kiểm tra rỗng mà không cần convert sang UTF-8.

### 4.1. Java: `LocalRefLifecycle.java`

```java
import java.util.Objects;

public final class LocalRefLifecycle {
    static {
        System.loadLibrary("localrefs");
    }

    private static native int nativeCountNonEmpty(String[] values);
    private static native String nativeFirstNonEmpty(String[] values);

    public static int countNonEmpty(String[] values) {
        Objects.requireNonNull(values, "values");
        return nativeCountNonEmpty(values);
    }

    public static String firstNonEmpty(String[] values) {
        Objects.requireNonNull(values, "values");
        return nativeFirstNonEmpty(values);
    }

    public static void main(String[] args) {
        String[] values = new String[100_000];

        for (int i = 0; i < values.length; ++i) {
            values[i] = (i % 10 == 0) ? "hit" : "";
        }
        values[1] = null;

        System.out.println("nonEmpty=" + countNonEmpty(values));
        System.out.println("first=" + firstNonEmpty(values));
    }
}
```

Vì các chỉ số `0, 10, 20, ... 99990` có giá trị `"hit"` nên có đúng **10.000 phần tử không rỗng**. Chỉ số `1` vốn là chuỗi rỗng, đổi sang `null` không làm thay đổi số đếm. Tại chỉ số `0`, hàm thứ hai thấy ngay `"hit"`.

### 4.2. Sinh JNI header

Trong thư mục chứa `LocalRefLifecycle.java`:

```bash
javac -h . LocalRefLifecycle.java
```

Lệnh tạo `LocalRefLifecycle.class` và `LocalRefLifecycle.h`. File C cần include chính header này. Chữ ký native được sinh có hình dạng:

```c
JNIEXPORT jint JNICALL
Java_LocalRefLifecycle_nativeCountNonEmpty(
    JNIEnv *, jclass, jobjectArray);

JNIEXPORT jstring JNICALL
Java_LocalRefLifecycle_nativeFirstNonEmpty(
    JNIEnv *, jclass, jobjectArray);
```

Đây là đoạn **minh họa prototype**; không tạo file header thủ công thay cho `javac -h` khi đổi tên class/package hoặc overload. Với native method `static`, tham số thứ hai là `jclass`; với instance method, đó là `jobject`.

### 4.3. C: `LocalRefLifecycle.c`

```c
#include "LocalRefLifecycle.h"

static void throw_null_array(JNIEnv *env) {
    jclass cls = (*env)->FindClass(
        env, "java/lang/NullPointerException");

    if (cls == NULL) {
        /* FindClass đã thất bại; để exception pending truyền về Java. */
        return;
    }

    (*env)->ThrowNew(env, cls, "values must not be null");
    (*env)->DeleteLocalRef(env, cls);
}

/*
 * Cách 1: DeleteLocalRef trên từng phần tử.
 * Mỗi phần tử chỉ cần sống trong đúng một iteration.
 */
JNIEXPORT jint JNICALL
Java_LocalRefLifecycle_nativeCountNonEmpty(
    JNIEnv *env, jclass clazz, jobjectArray values) {

    (void)clazz;

    if (values == NULL) {
        throw_null_array(env);
        return 0;
    }

    jsize length = (*env)->GetArrayLength(env, values);
    jint count = 0;

    for (jsize i = 0; i < length; ++i) {
        jstring item = (jstring)
            (*env)->GetObjectArrayElement(env, values, i);

        if ((*env)->ExceptionCheck(env)) {
            /* Exception của JNI giữ nguyên; Java sẽ nhận exception. */
            return 0;
        }

        if (item != NULL) {
            jsize utf16_units = (*env)->GetStringLength(env, item);

            /*
             * Trong lúc có exception pending, DeleteLocalRef là
             * một trong các thao tác cleanup vẫn được phép gọi.
             */
            if ((*env)->ExceptionCheck(env)) {
                (*env)->DeleteLocalRef(env, item);
                return 0;
            }

            if (utf16_units > 0) {
                ++count;
            }

            (*env)->DeleteLocalRef(env, item);
            item = NULL;
        }
    }

    return count;
}

/*
 * Cách 2: PushLocalFrame/PopLocalFrame.
 * Giữ đúng một jstring kết quả qua ranh giới frame.
 */
JNIEXPORT jstring JNICALL
Java_LocalRefLifecycle_nativeFirstNonEmpty(
    JNIEnv *env, jclass clazz, jobjectArray values) {

    (void)clazz;

    if (values == NULL) {
        throw_null_array(env);
        return NULL;
    }

    if ((*env)->PushLocalFrame(env, 8) != JNI_OK) {
        /* JNI để lại exception tương ứng nếu không mở được frame. */
        return NULL;
    }

    jsize length = (*env)->GetArrayLength(env, values);

    for (jsize i = 0; i < length; ++i) {
        jstring item = (jstring)
            (*env)->GetObjectArrayElement(env, values, i);

        if ((*env)->ExceptionCheck(env)) {
            (*env)->PopLocalFrame(env, NULL);
            return NULL;
        }

        if (item == NULL) {
            continue;
        }

        jsize utf16_units = (*env)->GetStringLength(env, item);

        if ((*env)->ExceptionCheck(env)) {
            (*env)->PopLocalFrame(env, NULL);
            return NULL;
        }

        if (utf16_units > 0) {
            /*
             * Pop xóa mọi local refs thuộc frame này,
             * đồng thời tạo ref tương đương ở frame cha.
             */
            return (jstring)(*env)->PopLocalFrame(env, item);
        }

        (*env)->DeleteLocalRef(env, item);
        item = NULL;
    }

    return (jstring)(*env)->PopLocalFrame(env, NULL);
}
```

Ở phương thức đếm, `GetObjectArrayElement` tạo một local reference mới cho mỗi phần tử khác `null`. Tất cả chúng được xóa sớm, nên dù có 100.000 iteration, số reference JNI tạm tồn tại cùng lúc không tăng tuyến tính theo số phần tử. Array `values` do Java giữ trong suốt lời gọi vẫn có thể giữ các String sống; mục tiêu trực tiếp là **không làm đầy bảng JNI references**.

Ở phương thức tìm phần tử, `PushLocalFrame(env, 8)` tạo một phạm vi con có sức chứa tối thiểu 8 reference. `PopLocalFrame(env, item)` hủy các local references thuộc frame con **nhưng giữ đối tượng mà `item` trỏ tới dưới dạng local reference mới ở frame cha**, để Java nhận được kết quả hợp lệ. Nếu không tìm thấy, `PopLocalFrame(env, NULL)` chỉ dọn frame rồi trả `null`.

Lưu ý: mã cố ý dọn cả những item rỗng bên trong frame dù `PopLocalFrame` cuối cùng cũng dọn. Nhờ vậy, nếu có một triệu phần tử rỗng trước kết quả, lượng local reference đồng thời vẫn được khống chế. **Một frame tạo ở ngoài vòng lặp nhưng không xóa ref trong vòng lặp không tự biến thành cơ chế cleanup theo iteration.**

Việc truyền `JNIEnv *` và gọi qua `(*env)->...` là cú pháp JNI dành cho C. Trong C++ thường dùng `env->...`. Các tên hàm xuất ra bên C khớp với class Java ở default package; một ứng dụng thực tế có package phải dùng header sinh theo package đó.

### 4.4. Biên dịch và chạy trên Linux

Chuẩn bị JDK 17+ và compiler C11; `JAVA_HOME` phải trỏ đến thư mục JDK chứa `include/jni.h`. Chạy trong thư mục đặt hai source:

```bash
javac -h . LocalRefLifecycle.java

cc -std=c11 -Wall -Wextra -Wpedantic -fPIC -shared \
   -I"$JAVA_HOME/include" -I"$JAVA_HOME/include/linux" \
   LocalRefLifecycle.c -o liblocalrefs.so

java -Djava.library.path=. LocalRefLifecycle
```

**Stdout chính xác** khi chạy thành công:

```text
nonEmpty=10000
first=hit
```

Tên `System.loadLibrary("localrefs")` được JVM ánh xạ thành `liblocalrefs.so` trên Linux. Trên macOS/Windows, đường dẫn JNI headers, cờ compiler và tên shared library khác; không sao chép nguyên lệnh `-I.../linux` vào các nền tảng đó. Nếu đổi package/tên native method, chạy lại `javac -h` và build lại thư viện.

Mã sử dụng Java 17 API thông thường, không phụ thuộc JNI ngoại lệ hoặc API nội bộ `Unsafe`; thư viện C cần đúng architecture và ABI của JVM đang chạy.

## 5. `PushLocalFrame`, `PopLocalFrame` và `EnsureLocalCapacity` khác nhau thế nào?

| API | Tác dụng | Có xóa local references đã tạo không? | Khi nên dùng |
| --- | --- | --- | --- |
| `DeleteLocalRef(env, ref)` | Xóa **một** local reference xác định | **Có**, ref đó | Mỗi iteration chỉ cần một vài ref |
| `PushLocalFrame(env, n)` | Mở một phạm vi lồng nhau, đảm bảo chỗ cho ít nhất `n` local refs mới | **Chưa** | Một tác vụ tạo nhiều refs liên quan cần dọn theo nhóm |
| `PopLocalFrame(env, result)` | Dọn local frame hiện tại, có thể giữ **một** result ở frame cha | **Có**, tất cả local refs thuộc frame con | Kết thúc tác vụ/iteration/batch hoặc trả một ref ra ngoài |
| `EnsureLocalCapacity(env, n)` | Bảo đảm chỗ cho thêm `n` local refs trên thread hiện tại | **Không** | Khi cần chủ động dự trữ lượng refs mới mà không muốn tạo frame |
| `NewLocalRef(env, ref)` | Tạo **một local reference khác** trỏ cùng object | **Không**; còn tạo thêm ref | Tạo ref trong phạm vi hiện tại từ ref hợp lệ |

`PushLocalFrame` nhận capacity **lớn hơn 0**. Nếu không thể mở frame, hàm trả mã âm; trong tình huống cấp phát thất bại thông thường JNI báo lỗi tương ứng (ví dụ `OutOfMemoryError`). Chỉ gọi `PopLocalFrame` **sau khi push thành công**; phải bảo đảm mọi đường thoát khỏi scope đã push đều pop tương ứng.

`EnsureLocalCapacity` không bảo đảm garbage collection và không thu hồi các reference đang giữ. Gọi `EnsureLocalCapacity(env, 1000)` trước vòng lặp một triệu lần **không thay thế** việc xóa refs. Một local frame nhỏ cũng không “tự reset” sau mỗi iteration nếu frame sống bên ngoài loop.

### 5.1. Chọn frame theo batch, tránh quên cleanup ở nhánh lỗi

Khi một iteration thực hiện nhiều JNI calls (tạo String, lấy class, gọi factory trả object, đọc thuộc tính), dùng frame theo iteration hoặc theo batch giúp giảm nguy cơ sót ref:

```c
/*
 * Minh họa cấu trúc trong một native method, không phải
 * translation unit độc lập: env/values/work() là giả định
 * do chương trình gọi chuẩn bị và định nghĩa riêng.
 */
for (jsize i = 0; i < length; ++i) {
    if ((*env)->PushLocalFrame(env, 16) != JNI_OK) {
        return;
    }

    /* work(env, i) được phép tạo local refs trong frame này. */
    work(env, i);

    if ((*env)->ExceptionCheck(env)) {
        (*env)->PopLocalFrame(env, NULL);
        return;
    }

    (*env)->PopLocalFrame(env, NULL);
}
```

Khuôn mẫu này cho thấy mỗi iteration tự có điểm cleanup. Chi phí push/pop có thể không cần thiết nếu mỗi iteration tạo đúng một ref và dễ gọi `DeleteLocalRef`. Hãy ưu tiên cách rõ ràng và benchmark trước khi tối ưu.

### 5.2. Giữ một reference kết quả khi pop

Nếu một object tạo trong frame con cần sống sau khi pop:

```c
jobject result = /* ref được tạo trong frame con */;

/* Chuyển object ra frame cha và dọn refs còn lại. */
jobject survivor = (*env)->PopLocalFrame(env, result);

/* result cũ đã mất hiệu lực; chỉ survivor có thể dùng tiếp. */
```

Đoạn trên là **mã minh họa**, chỉ hợp lệ sau khi một `PushLocalFrame` tương ứng đã thành công; không gán `survivor = result` rồi pop, vì handle cũ thuộc frame bị hủy. Chỉ truyền kết quả mà JNI contract cho phép; nếu `survivor == NULL` khi bạn chờ một object, kiểm tra lỗi/exception thích hợp.

## 6. Lời gọi kéo dài: “cuối native method” có thể còn rất xa

Thử tưởng tượng JNI xử lý hàng triệu row trong một lần gọi, mỗi row lại gọi `NewStringUTF` để tạo một String tạm. Nếu không xóa local refs cho từng row, mọi String được tham chiếu từ JNI có thể tồn tại tới lúc phương thức kết thúc, dù kết quả trung gian đã bỏ từ lâu.

Cùng một lỗi có thể xuất hiện ngoài vòng lặp:

- **Pipeline nhiều phase:** phase đầu tạo hàng loạt object để xử lý, phase sau chỉ dùng kết quả số, nhưng toàn bộ refs vẫn sống.
- **Callback Java từ C:** `CallObjectMethod` trả ref mới mỗi lần; nếu loop gọi callback mà không dọn kết quả, ref tích lũy. Khi callback ném exception, phải xử lý/cleanup trước khi tiếp tục JNI.
- **Lời gọi bị block:** native method giữ một local reference tới object rất lớn rồi chờ I/O hoặc mutex lâu; dù code không dùng object nữa, ref có thể tiếp tục giữ object sống.
- **Native worker thread gắn lâu:** không có native-method-return tự nhiên cho logic C chạy trên thread native được attach, nên ref có thể giữ tới lúc detach.

Cách thiết kế tốt là đặt ranh giới lifetime ngay ở **thời điểm dùng xong**, không chờ đến cuối vòng đời toàn bộ worker.

Cũng cần xem xét **thời gian JNI function nhận diện exception bất đồng bộ**. JNI Design Overview khuyến nghị chèn kiểm tra `ExceptionOccurred` trong phần native chạy dài, nhất là tight loop không có các lời gọi JNI khác có thể ném exception. Khi đã phát hiện exception pending, code nên cleanup rồi trả quyền điều khiển về Java hoặc có chiến lược xử lý rõ ràng; không tiếp tục tùy tiện gọi các hàm JNI khác.

## 7. Xử lý exception mà vẫn dọn references

JNI không tự nhảy về Java ngay khi một hàm JNI ném exception. Nó đánh dấu **pending exception** trên thread và native C vẫn đang chạy cho đến lúc trả về hoặc tự xử lý. Sau khi có pending exception, chỉ một tập nhỏ JNI functions được phép gọi trước khi clear exception.

Trong nhóm cleanup được phép có `DeleteLocalRef`, `PopLocalFrame`, `DeleteGlobalRef`, các hàm `ReleaseStringChars` / `ReleaseStringUTFChars` / `Release<Type>ArrayElements`, `ExceptionCheck`, `ExceptionOccurred` và `ExceptionClear`. Tránh gọi `FindClass`, `CallObjectMethod`, `NewStringUTF` hoặc tạo đối tượng mới khi exception vẫn pending.

Một cấu trúc cleanup tuyến tính điển hình:

```c
/*
 * Minh họa bên trong native method có jint return.
 * "value" là local reference vừa được tạo, hoặc NULL.
 */
jobject value = (*env)->GetObjectArrayElement(env, values, index);

if ((*env)->ExceptionCheck(env)) {
    return 0;       /* Không có ref sử dụng được từ lần gọi lỗi. */
}

/* ... xử lý value ... */

if (value != NULL) {
    (*env)->DeleteLocalRef(env, value);
    value = NULL;
}

if ((*env)->ExceptionCheck(env)) {
    return 0;       /* Để exception Java pending lan lên caller. */
}
```

Nếu một JNI operation bên giữa có thể ném exception, **dọn tất cả refs và resources đã lấy được**, rồi trả về khi exception còn pending. Tránh gọi `ExceptionClear` chỉ để “cho chạy tiếp” mà không biết trạng thái dữ liệu hoặc đối tượng sau lỗi; nếu quyết định khôi phục, phải rõ nguyên nhân và hành vi thay thế.

### 7.1. Đừng nhầm local ref với C buffer do JNI cấp

Ví dụ lấy nội dung UTF-8 của một `jstring` (đây là **mã minh họa** trong một native method đã có `env` và `s` hợp lệ):

```c
const char *bytes = (*env)->GetStringUTFChars(env, s, NULL);
if (bytes == NULL) {
    /* JNI có thể đã báo lỗi: dọn s nếu nó do ta tạo ra. */
    (*env)->DeleteLocalRef(env, s);
    return;
}

/* Dùng bytes chỉ khi s vẫn hợp lệ và chưa release. */

(*env)->ReleaseStringUTFChars(env, s, bytes);
(*env)->DeleteLocalRef(env, s);
```

Có **hai nghĩa vụ riêng**:

1. `ReleaseStringUTFChars` giải phóng/unpin phần dữ liệu byte mà JNI đã trả về tương ứng với `GetStringUTFChars`.
2. `DeleteLocalRef` giải phóng local reference `s` nếu code sở hữu ref tạm đó.

Chỉ gọi `DeleteLocalRef` **không thay thế** `ReleaseStringUTFChars`; chỉ gọi `ReleaseStringUTFChars` **không xóa** local ref. Nếu `s` là tham số method được Java truyền vào, có thể để JVM tự dọn ref của tham số ở cuối native call, nhưng buffer UTF-8 vẫn phải release đúng cặp.

Hàm `GetStringUTFChars` dùng **Modified UTF-8** theo JNI, không đồng nhất hoàn toàn với UTF-8 chuẩn (đặc biệt NUL và các ký tự Unicode bổ sung). Nếu chỉ kiểm tra chuỗi rỗng, `GetStringLength` đơn giản hơn và tránh phải xin/release native buffer.

## 8. Thread native attach: tránh tích lũy reference trong tiến trình lâu sống

Thread native tự tạo (ví dụ qua pthread) không có sẵn `JNIEnv *` hợp lệ. Nó phải dùng `JavaVM *` và `AttachCurrentThread` để gắn vào JVM. `JNIEnv *` chỉ dùng cho chính thread đó; không lưu rồi sử dụng từ một thread khác.

Cấu trúc khái niệm:

```c
/*
 * Minh họa luồng điều khiển, không phải chương trình độc lập:
 * vm và một vòng lặp workload cụ thể do caller cung cấp.
 */
JNIEnv *env = NULL;
if ((*vm)->AttachCurrentThread(vm, (void **)&env, NULL) != JNI_OK) {
    /* Xử lý lỗi attach ở native side. */
    return;
}

while (has_more_work()) {
    if ((*env)->PushLocalFrame(env, 16) != JNI_OK) {
        break;
    }

    /* Đọc/call Java, tạo local references tạm. */
    process_one_batch(env);

    jboolean failed = (*env)->ExceptionCheck(env);
    (*env)->PopLocalFrame(env, NULL);

    if (failed) {
        /* Không gọi tiếp JNI thường lệ khi exception còn pending. */
        break;
    }
}

/* Tại điểm kết thúc hợp lệ: thread tự detach khi xong. */
(*vm)->DetachCurrentThread(vm);
```

Đây là **sơ đồ code**, không thể biên dịch độc lập vì `vm`, `has_more_work` và `process_one_batch` chưa được định nghĩa. Trong ứng dụng thật, còn phải quyết định exception phát sinh trong thread native sẽ được báo về Java thế nào, xử lý shutdown/cancel ra sao, và chắc chắn thread không giữ Java monitor đang khóa khi detach. `DetachCurrentThread` không phải chiến lược “dọn cho mỗi batch”: thread chạy nhiều giờ phải dọn ref ngay trong từng batch.

Nếu native code cần giữ một object **sau khi native method kết thúc**, hoặc cần chia sẻ nó giữa những thread đã attach, hãy tạo `global reference`:

```c
/* objectRef là JNI reference hợp lệ trong thread hiện tại. */
jobject global = (*env)->NewGlobalRef(env, objectRef);
/* Kiểm tra NULL/exception và cất global theo contract. */

/* Khi không còn cần global, trên thread attached hợp lệ: */
(*env)->DeleteGlobalRef(env, global);
```

Đây là đoạn **minh họa**, không phải file độc lập. Global reference cần được release **tường minh**, nếu không có thể giữ cả một đồ thị đối tượng sống lâu vô hạn. `NewWeakGlobalRef` là tùy chọn khi muốn GC có thể thu hồi object, nhưng weak ref có thể trở nên `NULL` và phải kiểm tra bằng cách tạo local mạnh/kiểm tra hợp lệ theo JNI; weak global không phải giải pháp thay thế tự động cho ownership.

## 9. Lỗi phổ biến và cách phòng tránh

| Cách viết hoặc quan niệm sai | Hệ quả | Cách làm đúng |
| --- | --- | --- |
| Tạo ref trong loop rồi chỉ gán biến `jobject x = NULL` | Slot/handle JNI vẫn được giữ tới khi invocation kết thúc | `DeleteLocalRef` hoặc pop frame tương ứng |
| “JVM tự dọn local ref” nên vòng lặp một triệu phần tử không cần cleanup | Local table có thể tràn trước khi native method trả về | Xóa refs theo iteration/batch |
| `PushLocalFrame` một lần ở ngoài loop và không xóa ref | Frame không tự dọn theo iteration | Pop mỗi iteration/batch, hoặc xóa từng ref |
| `EnsureLocalCapacity` rồi bỏ qua cleanup | Chỉ dự trữ chỗ, không giải phóng | Phân biệt reserve với release |
| `DeleteLocalRef(env, x)` rồi `return x` | Trả handle không còn hiệu lực | Giữ ref để return hoặc `PopLocalFrame(env, x)` |
| `PopLocalFrame(env, NULL)` rồi dùng một ref từ frame cũ | Ref bị invalid khi pop | Tạo survivor bằng `PopLocalFrame(env, result)` |
| Xóa một local ref và tin rằng Java object đã bị hủy | Object có thể vẫn còn strong refs khác | Hiểu GC reachability và ownership |
| Truyền local `jobject` sang thread khác | Vi phạm phạm vi thread của local reference | Global ref khi cần chia sẻ đúng contract |
| Giữ `jclass` local từ `FindClass` trong biến `static` | Dùng ref sau lifetime, có thể crash | `NewGlobalRef` rồi `DeleteGlobalRef` |
| Gọi `FindClass`/`CallObjectMethod` khi exception pending | Vi phạm quy tắc JNI | Cleanup bằng API được phép rồi trả về hoặc clear có kiểm soát |
| Xóa `jstring` local thay cho release pointer bytes | Leak hoặc pin/copy buffer JNI | Ghép đúng `Get.../Release...` và ref cleanup |
| `DeleteLocalRef` hai lần trên cùng handle | Lạm dụng ref đã xóa; hành vi không hợp lệ | Một lifetime cho mỗi handle; gán local `NULL` sau xóa |
| `DeleteLocalRef` áp vào global reference | Sai loại reference | Dùng `DeleteGlobalRef` |
| Tạo local refs trong attached worker suốt thời gian chạy | Không có native method return để tự dọn từng batch | Dùng frame/delete liên tục, detach cuối đời thread |

Ngoài correctness, dọn refs đúng làm rõ **lifetime**: đoạn code nào cần object, đoạn nào chỉ cần dữ liệu primitive đã trích ra, đoạn nào có thể cho JVM bớt một GC root. Tuy nhiên không nên ép dọn vô tội vạ các refs sẽ được dùng sau đó, vì JNI không có cơ chế “khôi phục” một handle đã xóa.

## 10. Kiểm chứng và quan sát thực tế

Các tình huống nên có trong kiểm thử JNI:

1. **Vòng lặp rất dài:** thử array 100.000, 500.000 hoặc nhiều phần tử hơn tùy heap cho phép; native function phải trả đúng số đếm, không tăng số local references đang sống theo mỗi iteration.
2. **Null/rỗng:** phần tử `null` không được truyền vào `GetStringLength`; chuỗi `""` có `GetStringLength == 0`.
3. **Exception path:** nếu `GetObjectArrayElement` hoặc method callback tạo exception, phải cleanup những local refs đã có; không tiếp tục JNI calls bị cấm trong lúc pending.
4. **Frame return:** `PopLocalFrame(env, result)` cho kết quả dùng được ở frame cha, còn ref tạm cùng frame không dùng lại.
5. **Thread dài hạn:** lặp theo batch trên native-attached thread, đối chiếu số refs, thời gian sống đối tượng và cách shutdown/detach.
6. **GC behavior:** đừng kết luận `DeleteLocalRef` “không hoạt động” chỉ vì object chưa GC: có thể vẫn có tham chiếu từ Java array, stack, global ref hoặc JVM.
7. **Phân loại tài nguyên:** đếm riêng JNI local handles, JNI global refs, C heap allocations và buffers từ `GetStringUTFChars`; chúng có hàm release khác nhau.

Khi chạy trên HotSpot/JDK hỗ trợ, có thể bật kiểm tra JNI tăng cường:

```bash
java -Xcheck:jni -Djava.library.path=. LocalRefLifecycle
```

Tuỳ phiên bản JVM, `-verbose:jni` có thể cung cấp log bổ sung. Trên Android, CheckJNI giúp phát hiện một số lỗi dùng reference sai loại, dùng sau khi xóa và nhiều vi phạm JNI khác. Không dựa vào một chương trình stress có kết quả tốt để chứng minh không có leak: cần review lifetime của từng đường thoát.

Cách suy luận về số reference ở vòng lặp:

- Không xóa sau `GetObjectArrayElement`: số ref tạm *còn sống* có thể tăng xấp xỉ theo số phần tử đã xử lý.
- Xóa ref trước iteration tiếp theo: phần ref tạm phát sinh trực tiếp bởi API này được khống chế quanh 0–1 tại mỗi thời điểm.
- Dùng frame theo batch: số ref đang sống tạm thời được khống chế bởi lượng ref trong **batch hiện tại**; `PopLocalFrame` giải phóng cả nhóm.
- Nếu có ref ở frame cha hoặc global ref, dọn frame con **không** làm chúng biến mất.

## 11. Checklist áp dụng khi viết JNI

Trước khi bàn giao native method duyệt Java objects hoặc xử lý kéo dài, trả lời các câu hỏi:

- Mỗi `jobject/jclass/jstring/jarray` tạm sinh từ **hàm nào** và còn được dùng tới điểm nào?
- Vòng lặp có thể chạy bao lâu và tạo tối đa bao nhiêu local references **đồng thời**?
- Dùng `DeleteLocalRef` cho từng ref hay mở `PushLocalFrame` theo iteration/batch? Mọi đường success, exception, early return đều dọn được chứ?
- Sau `PopLocalFrame`, ref nào được giữ bằng `result` và ref nào đã invalid?
- Native method có trả về sớm, chờ I/O lâu hoặc chạy trên thread native attach lâu không?
- Code có phân biệt local/global/weak global reference với con trỏ C, buffer JNI và primitive `jlong` không?
- Có kiểm tra exception ngay sau các JNI calls có thể thất bại trước khi dùng kết quả và luôn cleanup bằng API hợp lệ không?
- Nếu giữ đối tượng qua lời gọi/thread, có chủ sở hữu cho `NewGlobalRef/DeleteGlobalRef` và điểm release xác định không?

**Quy tắc trọng tâm:** local reference tự hết hạn khi native method trở về Java, nhưng **không tự hết hạn ở cuối mỗi vòng lặp C**. Hãy dọn reference **ngay khi không còn cần**, hoặc gom theo frame với điểm pop rõ ràng; điều này giới hạn số handle đang sống, tránh giữ thêm GC roots và khiến code dễ kiểm soát trên các lời gọi native kéo dài.

### Tài liệu tham khảo

- [Oracle Java SE 17 — JNI Design Overview, Global and Local References](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/design.html)
- [Oracle Java SE 17 — JNI Functions: DeleteLocalRef, EnsureLocalCapacity, PushLocalFrame, PopLocalFrame](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/functions.html)
- [Oracle Java SE 17 — Invocation API / AttachCurrentThread](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/invocation.html)
- [Android Developers — JNI Tips: Local and Global References](https://developer.android.com/ndk/guides/jni-tips)
