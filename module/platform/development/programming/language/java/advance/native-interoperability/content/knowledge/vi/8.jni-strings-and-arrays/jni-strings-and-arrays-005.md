# GetArrayElements có thể sao chép hoặc ghim mảng tùy JVM

## 1. Vấn đề cốt lõi: con trỏ native trỏ vào đâu?

Khi Java gọi C/C++ qua **JNI (Java Native Interface)**, mã native đôi khi cần đọc hoặc sửa trực tiếp các phần tử của một mảng Java, ví dụ `int[]`, `byte[]` hoặc `double[]`. Nhóm hàm **`Get<PrimitiveType>ArrayElements`** cho phép nhận một con trỏ kiểu C đến vùng phần tử của **mảng nguyên thủy**. Ví dụ, `GetIntArrayElements` trả `jint *` để đọc/sửa một `jintArray`.

Tuy nhiên, **JNI không bảo đảm con trỏ luôn trỏ trực tiếp vào vùng lưu trữ gốc của mảng Java**. Tùy cách triển khai JVM, bộ gom rác (GC), kiểu mảng và điều kiện runtime, JVM có thể chọn:

1. **Sao chép (copy):** tạo một buffer native chứa các phần tử, trả con trỏ đến buffer đó; khi cần đưa thay đổi về mảng Java, JNI có thể phải chép ngược khi `Release<Type>ArrayElements`.
2. **Không sao chép (direct access, thường được mô tả là pinning/ghim):** trả con trỏ truy cập phần tử gốc theo cơ chế JVM hỗ trợ; JVM phải duy trì khả năng truy cập an toàn trong thời gian con trỏ còn hiệu lực, có thể phải hạn chế di chuyển mảng hoặc dùng cơ chế khác.

**Code của bạn phải hoạt động đúng trong cả hai trường hợp.** Không được giả định “JVM này luôn ghim”, “mảng nhỏ luôn copy”, “mảng lớn luôn pin”, hay “`GetIntArrayElements` luôn zero-copy”. Đây là chi tiết thực thi mà chuẩn JNI để JVM quyết định.

### 1.1. Minh họa dòng dữ liệu

```text
                 Java int[]  [10, 20, 30]
                          |
             GetIntArrayElements(...)
                          |
               +----------+----------+
               |                     |
          JVM chọn copy         JVM chọn direct
               |                     |
        buffer tạm [10,20,30]  vùng phần tử của mảng
               |                     |
          jint *elements        jint *elements
               |                     |
       Native sửa elements[i] trên con trỏ trả về
               |                     |
             ReleaseIntArrayElements(..., mode)
               |                     |
       Có thể copy lại         Không cần copy-back
       trước khi dọn buffer    từ buffer tạm
                          |
                    Java tiếp tục
```

Trong nhánh copy, Java có thể **chưa thấy** các giá trị native mới ghi cho đến khi release/copy-back. Trong nhánh direct, native có thể đã chạm vào bộ nhớ gốc trước release, nhưng không vì vậy mà được bỏ qua `Release...`. Không nên dựa vào thời điểm quan sát trung gian khi có nhiều thread.

## 2. Tên API chính xác và phạm vi hỗ trợ

`GetArrayElements` thường chỉ là **cách gọi tắt về mặt khái niệm**. Không có một hàm JNI tiêu chuẩn tên đúng nguyên văn `GetArrayElements` cho mọi kiểu mảng. Tên thật gồm tên kiểu:

| Mảng Java | Kiểu JNI | Hàm lấy phần tử | Con trỏ C nhận được | Hàm release tương ứng |
| --- | --- | --- | --- | --- |
| `boolean[]` | `jbooleanArray` | `GetBooleanArrayElements` | `jboolean *` | `ReleaseBooleanArrayElements` |
| `byte[]` | `jbyteArray` | `GetByteArrayElements` | `jbyte *` | `ReleaseByteArrayElements` |
| `char[]` | `jcharArray` | `GetCharArrayElements` | `jchar *` | `ReleaseCharArrayElements` |
| `short[]` | `jshortArray` | `GetShortArrayElements` | `jshort *` | `ReleaseShortArrayElements` |
| `int[]` | `jintArray` | `GetIntArrayElements` | `jint *` | `ReleaseIntArrayElements` |
| `long[]` | `jlongArray` | `GetLongArrayElements` | `jlong *` | `ReleaseLongArrayElements` |
| `float[]` | `jfloatArray` | `GetFloatArrayElements` | `jfloat *` | `ReleaseFloatArrayElements` |
| `double[]` | `jdoubleArray` | `GetDoubleArrayElements` | `jdouble *` | `ReleaseDoubleArrayElements` |

Nhóm này **chỉ áp dụng cho primitive arrays**. Với `String[]` hoặc `Object[]`, dùng các API object array như `GetObjectArrayElement`/`SetObjectArrayElement`; không có `GetObjectArrayElements` tiêu chuẩn để lấy con trỏ trực tiếp tới mọi phần tử object. `String` đơn lẻ có nhóm API chuỗi riêng với quy tắc trả vùng truy cập của chính nó.

Theo đặc tả, `GetBooleanArrayElements` trả một dãy `jboolean` dạng **một byte cho mỗi phần tử** bất kể JVM biểu diễn `boolean[]` bên trong ra sao; vì vậy với `boolean[]` không thể suy luận từ bố trí Java rằng luôn có thể trả con trỏ vào vùng gốc mà không cần chuyển đổi. Các mảng primitive khác được bảo đảm có biểu diễn phần tử liên tiếp theo giao diện này.

### 2.1. Chữ ký điển hình

Trong JNI C, hình dạng khái niệm của cặp API là:

```c
jint *GetIntArrayElements(
        JNIEnv *env, jintArray array, jboolean *isCopy);

void ReleaseIntArrayElements(
        JNIEnv *env, jintArray array, jint *elems, jint mode);
```

Khi gọi từ mã C sử dụng `JNIEnv`:

```c
jboolean isCopy = JNI_FALSE;
jint *elems = (*env)->GetIntArrayElements(env, array, &isCopy);
/* Sử dụng elems, kiểm tra NULL trước khi dereference. */
(*env)->ReleaseIntArrayElements(env, array, elems, 0);
```

Đoạn trên chỉ mô tả **mẫu API**, không phải hàm hoàn chỉnh: trong chương trình thực phải kiểm tra `array` hợp lệ, `elems != NULL` và quản lý đường thoát lỗi; ví dụ chạy đầy đủ ở mục 7.

## 3. Vì sao JVM có thể phải chọn copy thay vì ghim?

Java thường cho phép garbage collector quản lý heap và có thể **di chuyển đối tượng** khi thực hiện một số pha GC. Một địa chỉ bộ nhớ thô (`jint *`) lưu ở C không được GC cập nhật như Java reference thông thường nếu JVM di chuyển mảng.

Vì vậy, để giữ con trỏ hợp lệ, JVM có thể:

- **Copy** các phần tử sang vùng tạm ổn định. GC tiếp tục quản lý mảng Java theo cơ chế của nó; lúc release, việc ghi ngược có thể cần thiết.
- **Pin** mảng hoặc dùng cơ chế direct-access tương đương trong một khoảng thời gian. Điều này có thể làm phức tạp việc di chuyển đối tượng, gây áp lực cho GC hoặc ảnh hưởng thời gian dừng/khả năng gom bộ nhớ, tùy collector và triển khai.

Không có quy tắc trong JNI Specification buộc JVM phải chọn một nhánh theo kích thước mảng hay tên GC. Một lệnh `GetIntArrayElements` có thể copy trên hệ thống này và không copy trên hệ thống khác. Dùng flag `isCopy` để **quan sát quyết định của lần gọi cụ thể** nếu cần, không dùng nó để thay đổi hợp đồng giải phóng.

### 3.1. Sự đánh đổi về hiệu năng

| Quyết định JVM | Ưu điểm tiềm năng | Chi phí/rủi ro cần lưu ý |
| --- | --- | --- |
| Copy | Native làm việc với buffer độc lập; GC có thể quản lý mảng gốc linh hoạt hơn | Có thể cần cấp phát và copy toàn bộ vùng phần tử, rồi copy-back khi release |
| Direct/pin | Có thể tránh copy nội dung lớn, đọc/ghi trên vùng dữ liệu gốc | Có thể hạn chế một số hoạt động GC; giữ con trỏ lâu là rủi ro cho runtime và phối hợp thread |

**Tránh kết luận “direct chắc chắn nhanh hơn”.** Trong workload thật còn có chi phí gọi JNI, cache, lượng dữ liệu, tối ưu JIT, chi phí pin, GC và đồng bộ. Nên đo cả đường đi Java→native→Java, đặc biệt với mảng lớn hoặc tần suất gọi cao.

## 4. Hiểu chính xác tham số `isCopy`

Ví dụ:

```c
jboolean copied = JNI_FALSE;
jint *p = (*env)->GetIntArrayElements(env, numbers, &copied);

if (p == NULL) {
    /* Lỗi truy cập; không được dereference p. */
    return;
}

if (copied == JNI_TRUE) {
    /* JVM đã tạo một bản sao của các phần tử. */
} else {
    /* JVM không tạo bản sao cho lời gọi này. */
}

(*env)->ReleaseIntArrayElements(env, numbers, p, 0);
```

Đây là **đoạn minh họa đặt trong hàm JNI trả `void`**, với `numbers` hợp lệ; không phải chương trình C độc lập.

Ý nghĩa:

- Truyền `&copied`: JNI ghi `JNI_TRUE` nếu đã **copy**, `JNI_FALSE` nếu **không copy**.
- Truyền `NULL` cho đối số `isCopy`: hợp lệ nếu không cần biết JVM dùng chiến lược nào.
- `copied == JNI_FALSE` **không phải** chứng chỉ rằng bạn được giữ con trỏ mãi mãi hoặc dùng nó sau release. Nó cũng không bảo đảm JVM dùng một cơ chế pin cụ thể.
- Giá trị `isCopy` **không phải** mã thành công/thất bại. Kiểm tra riêng **con trỏ trả về**: `NULL` là dấu hiệu lời gọi không cung cấp vùng truy cập (có thể đi kèm `OutOfMemoryError`).

Có thể dùng `isCopy` cho **thống kê/chẩn đoán**, nhưng code chức năng không nên chia thành “nhánh copy thì release, nhánh direct thì bỏ release” — **cả hai đều phải release**.

## 5. Hợp đồng bộ nhớ: acquire → sử dụng → release

Cặp `Get<Type>ArrayElements` và `Release<Type>ArrayElements` phải được coi như một vòng đời tài nguyên:

1. Có `j<type>Array` không null, đọc độ dài bằng `GetArrayLength` nếu cần.
2. Gọi `Get<Type>ArrayElements`, kiểm tra con trỏ `NULL` trước khi truy cập.
3. Sử dụng `elems[i]` trong phạm vi `0 <= i < length`.
4. Gọi **đúng hàm release tương ứng** cho cùng mảng và con trỏ, với mode thích hợp.
5. Không đọc/ghi `elems` sau khi đã thực sự hoàn tất release; không giữ pointer trong biến global, object hoặc worker thread để dùng về sau.

Nếu JVM đã copy, thay đổi vào buffer có thể **chưa** nằm trong Java array cho đến khi release sao chép ngược. Nếu JVM direct/pin, thay đổi có thể tác động vùng gốc ngay khi native ghi. Code Java không nên quan sát trạng thái nửa chừng từ thread khác: đó không phải giao thức đồng bộ; phải bảo vệ bằng cơ chế thread-safety phù hợp.

**Không dùng `free(elems)`, `delete[] elems` hoặc `realloc(elems,...)`:** bộ nhớ do JVM quản lý theo hợp đồng JNI; chỉ hàm `Release...` tương ứng mới có quyền trả vùng truy cập. Gọi release nhầm kiểu hoặc với pointer không nhận từ hàm Get tương ứng có thể gây hành vi không xác định.

### 5.1. Ba chế độ `mode` của `Release<Type>ArrayElements`

| `mode` | Khi JVM đã **copy** | Khi JVM trả **vùng trực tiếp** |
| --- | --- | --- |
| `0` | Copy thay đổi từ buffer trở lại mảng Java (nếu cần), rồi giải phóng buffer JNI | Kết thúc quyền truy cập, thực hiện các thao tác cleanup/unpin cần thiết |
| `JNI_COMMIT` | Copy thay đổi về mảng Java nhưng **chưa giải phóng buffer tạm** | Mode không có hiệu lực copy-back riêng; không được tự suy ra còn giữ được pointer |
| `JNI_ABORT` | Giải phóng buffer tạm, **không copy** những sửa đổi từ buffer sang mảng Java | Không phải thao tác hoàn tác/rollback những sửa đổi đã chạm bộ nhớ gốc |

Theo JNI Specification, giá trị `mode` không có tác dụng đối với **buffer không phải bản sao**. Điều đó giải thích vì sao **`JNI_ABORT` không đảm bảo bỏ được sửa đổi**: nếu pointer trỏ thẳng vùng gốc thì giá trị có thể đã thay đổi trước khi gọi release. `JNI_ABORT` chỉ bảo đảm **bỏ qua bước copy-back khi JVM dùng bản sao**.

**Dùng `mode=0` làm mặc định khi ghi dữ liệu.** Với thao tác chỉ đọc, `JNI_ABORT` thường hợp lý: nếu có buffer tạm, tránh copy-back không cần thiết; trong cả hai trường hợp vẫn release. `JNI_COMMIT` là trường hợp nâng cao khi muốn đẩy nội dung copy về Java nhưng còn cần buffer: **nếu buffer là bản sao**, sau đó vẫn phải gọi một lần `Release...` kết thúc với `0` hoặc `JNI_ABORT` để giải phóng nó. Đừng coi `JNI_COMMIT` là release hoàn chỉnh trong nhánh copy.

### 5.2. Ví dụ sai về `JNI_ABORT`

```c
jint *p = (*env)->GetIntArrayElements(env, arr, NULL);
if (p != NULL) {
    p[0] = 999;
    (*env)->ReleaseIntArrayElements(env, arr, p, JNI_ABORT);
}
```

**Không thể nói chắc `arr[0]` vẫn giữ giá trị cũ.** Nếu `p` là bản sao thì sửa đổi không được copy-back; nếu `p` trỏ vùng gốc, giá trị `999` có thể đã ghi trực tiếp. Nếu cần “thử sửa rồi có thể rollback”, hãy **tự copy vào buffer riêng**, hoặc xử lý trong dữ liệu tách biệt rồi chủ động ghi khi thật sự quyết định commit.

## 6. Thời gian giữ con trỏ và tác động của GC

Con trỏ trả về chỉ hợp lệ trong **khoảng thời gian sử dụng do API cho phép**. Hãy rút ngắn thời gian từ Get đến Release:

- Không giữ pointer trong lúc thực hiện thao tác I/O chậm, gọi mạng hoặc chờ lock nếu có thể tách việc xử lý ra.
- Không trả `jint *` về Java làm địa chỉ sống dài hạn của mảng Java.
- Không giao pointer cho thread khác tiếp tục dùng sau khi hàm hiện tại release.
- Không thực hiện xử lý có thể thoát sớm mà bỏ qua release; trong C hãy tổ chức đường thoát rõ ràng (ví dụ một nhãn cleanup khi hợp lý).
- Nếu bị lỗi khi đang có vùng truy cập, vẫn phải release trước khi thoát, trừ trường hợp đặc tả cho phép khác; không tùy tiện gọi hàng loạt JNI API khi đang có exception đang chờ.

**Vì sao không nên giữ lâu?** Ở nhánh copy, buffer tạm tiêu tốn bộ nhớ native; ở nhánh pin/direct, việc JVM phải giữ vùng gốc ổn định có thể cản trở các hoạt động của collector. Mức ảnh hưởng cụ thể phụ thuộc JVM và GC. Không có “thời gian pin tối đa cố định” do chuẩn hứa cho nhóm GetArrayElements thường; điều đúng là **thiết kế thời gian sở hữu càng ngắn càng tốt**.

## 7. Ví dụ JNI chạy được trên Java 17+: cùng kết quả dù JVM copy hay direct

Ví dụ này làm hai việc:

1. `increase`: native tăng từng phần tử của `int[]` thêm `5`; dùng `ReleaseIntArrayElements(..., 0)` để thay đổi được phản ánh về Java trong cả hai chiến lược.
2. `sum`: native chỉ đọc dữ liệu và tính tổng; dùng `ReleaseIntArrayElements(..., JNI_ABORT)` để tránh copy-back khi không có sửa đổi.

Ngoài ra `increase` trả một giá trị boolean quan sát `isCopy`. **Giá trị boolean này phụ thuộc JVM/runtime nên không được dùng làm điều kiện kiểm thử bắt buộc**.

### 7.1. Tệp `ArrayElementsDemo.java`

```java
import java.util.Arrays;
import java.util.Objects;

public final class ArrayElementsDemo {
    static {
        System.loadLibrary("arrayelementsdemo");
    }

    private ArrayElementsDemo() {
    }

    private static native boolean increaseNative(int[] values);
    private static native int sumNative(int[] values);

    public static boolean increase(int[] values) {
        return increaseNative(Objects.requireNonNull(values, "values"));
    }

    public static int sum(int[] values) {
        return sumNative(Objects.requireNonNull(values, "values"));
    }

    public static void main(String[] args) {
        int[] values = {3, 7, 11};
        System.out.println("before = " + Arrays.toString(values));

        boolean copied = increase(values);
        System.out.println("after = " + Arrays.toString(values));
        System.out.println("sum = " + sum(values));

        System.out.println("isCopy = "
                + (copied ? "JNI_TRUE" : "JNI_FALSE"));
    }
}
```

`Objects.requireNonNull` ở các wrapper Java đảm bảo `int[]` không null trước khi gọi JNI theo đường đi minh họa. Phương thức native được khai báo `private static native`, nên C nhận `jclass` làm đối số JNI ẩn thứ hai. Đối với code thực tế có nhiều đường gọi, cần xác thực đầu vào ở biên native phù hợp với hợp đồng API.

### 7.2. Sinh JNI header

Ở thư mục chứa `ArrayElementsDemo.java`, dùng JDK 17+:

```bash
javac -h . ArrayElementsDemo.java
```

Lệnh sinh `ArrayElementsDemo.class` và `ArrayElementsDemo.h`. Tệp header chứa các khai báo `Java_ArrayElementsDemo_increaseNative`, `Java_ArrayElementsDemo_sumNative` và `jni.h` phù hợp chữ ký Java.

### 7.3. Tệp `ArrayElementsDemo.c`

```c
#include "ArrayElementsDemo.h"

/* Nếu GetIntArrayElements thất bại mà JVM chưa để lại
   exception, chuyển trạng thái lỗi thành OutOfMemoryError. */
static void report_access_failure(JNIEnv *env) {
    if ((*env)->ExceptionCheck(env)) {
        return;
    }

    jclass error = (*env)->FindClass(env, "java/lang/OutOfMemoryError");
    if (error != NULL) {
        (*env)->ThrowNew(env, error, "Cannot access int[] elements");
        (*env)->DeleteLocalRef(env, error);
    }
}

JNIEXPORT jboolean JNICALL Java_ArrayElementsDemo_increaseNative(
        JNIEnv *env, jclass clazz, jintArray array) {
    (void) clazz;

    jsize length = (*env)->GetArrayLength(env, array);
    if (length == 0) {
        return JNI_FALSE; /* Không cần gọi Get; không có isCopy thực tế. */
    }

    jboolean isCopy = JNI_FALSE;
    jint *elements = (*env)->GetIntArrayElements(env, array, &isCopy);
    if (elements == NULL) {
        report_access_failure(env);
        return JNI_FALSE; /* Exception sẽ được truyền về Java. */
    }

    for (jsize i = 0; i < length; i++) {
        elements[i] += 5;
    }

    /* Khi có copy: đồng bộ về Java rồi giải phóng buffer.
       Khi direct: kết thúc quyền truy cập/cho phép JVM cleanup. */
    (*env)->ReleaseIntArrayElements(env, array, elements, 0);
    return isCopy;
}

JNIEXPORT jint JNICALL Java_ArrayElementsDemo_sumNative(
        JNIEnv *env, jclass clazz, jintArray array) {
    (void) clazz;

    jsize length = (*env)->GetArrayLength(env, array);
    if (length == 0) {
        return 0;
    }

    /* Không cần biết lần truy cập này có phải bản sao không. */
    jint *elements = (*env)->GetIntArrayElements(env, array, NULL);
    if (elements == NULL) {
        report_access_failure(env);
        return 0; /* Exception sẽ được truyền về Java. */
    }

    jint total = 0;
    for (jsize i = 0; i < length; i++) {
        total += elements[i];
    }

    /* Chỉ đọc: bỏ qua copy-back, vẫn release đúng hợp đồng. */
    (*env)->ReleaseIntArrayElements(env, array, elements, JNI_ABORT);
    return total;
}
```

**Vì sao ví dụ đúng dù JVM copy hay direct?** `increaseNative` luôn dùng `mode=0`, nên nếu có bản sao thì nội dung được ghi ngược; nếu không copy thì dữ liệu đã nằm trên vùng gốc. `sumNative` không sửa `elements`, do đó `JNI_ABORT` không gặp vấn đề “không thể rollback” đã giải thích ở trên. Mọi lời gọi Get thành công đều có Release tương ứng.

`GetIntArrayElements` có thể trả `NULL` khi thất bại; ví dụ không dereference con trỏ rỗng. Khi JVM đã có exception, hàm hỗ trợ giữ nguyên exception; nếu chưa có, nó cố tạo `OutOfMemoryError` để tránh âm thầm trả giá trị nhìn như thành công.

### 7.4. Biên dịch/chạy trên Linux (GCC)

Đặt `JAVA_HOME` trỏ đến JDK phù hợp và chạy trong thư mục chứa Java/C source:

```bash
javac -h . ArrayElementsDemo.java

gcc -shared -fPIC \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  ArrayElementsDemo.c -o libarrayelementsdemo.so

java -Djava.library.path=. ArrayElementsDemo
```

### 7.5. Biên dịch/chạy trên macOS (Clang)

```bash
javac -h . ArrayElementsDemo.java

clang -dynamiclib \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/darwin" \
  ArrayElementsDemo.c -o libarrayelementsdemo.dylib

java -Djava.library.path=. ArrayElementsDemo
```

### 7.6. Biên dịch/chạy trên Windows (MSVC)

Mở Developer Command Prompt có compiler phù hợp kiến trúc JVM; `JAVA_HOME` phải là JDK. Trong `cmd.exe`:

```bat
javac -h . ArrayElementsDemo.java

cl /LD /I"%JAVA_HOME%\include" /I"%JAVA_HOME%\include\win32" ArrayElementsDemo.c /link /OUT:arrayelementsdemo.dll

java -Djava.library.path=. ArrayElementsDemo
```

### 7.7. Kết quả thực thi và cách đọc

**Ba dòng stdout đầu luôn là** (khi biên dịch/nạp và gọi JNI thành công):

```text
before = [3, 7, 11]
after = [8, 12, 16]
sum = 36
```

Dòng cuối là **một trong hai khả năng**, ví dụ:

```text
isCopy = JNI_TRUE
```

hoặc

```text
isCopy = JNI_FALSE
```

Hai trường hợp đều **hợp lệ**. Không nên hard-code assertion bắt `JNI_TRUE` hoặc `JNI_FALSE`, ngay cả khi chạy lặp trên cùng JVM/GC. Nếu chỉ quan tâm đúng/sai của phép tăng và phép cộng, các giá trị `[8, 12, 16]` và `36` mới là tiêu chí kiểm thử ổn định.

**Lưu ý JDK mới:** Trên JDK 24+ có cơ chế native access restrictions cho JNI; có thể phải cấp quyền native khi chạy trên classpath bằng `--enable-native-access=ALL-UNNAMED` (theo chính sách và phiên bản JDK đang dùng). Ví dụ Java/C này dùng API tương thích **Java 17**, không đòi hỏi FFM API.

## 8. `GetPrimitiveArrayCritical` có luôn tránh copy không?

**Không.** JNI còn có cặp:

```c
void *GetPrimitiveArrayCritical(
        JNIEnv *env, jarray array, jboolean *isCopy);

void ReleasePrimitiveArrayCritical(
        JNIEnv *env, jarray array, void *carray, jint mode);
```

Đây là nhóm dành cho **vùng truy cập critical**, với mục tiêu tăng cơ hội tránh copy trong một số JVM. Nhưng chuẩn vẫn cho phép JVM copy nếu cần do cách biểu diễn bộ nhớ hoặc ràng buộc triển khai. Đổi `GetIntArrayElements` thành `GetPrimitiveArrayCritical` **không đồng nghĩa chắc chắn zero-copy**.

Hợp đồng critical có thêm **hạn chế nghiêm ngặt**:

- Giữ khoảng thời gian giữa Get/Release **rất ngắn**.
- Trong critical region **không gọi JNI function khác**, và **không gọi system call có thể block chờ thread Java khác** (ví dụ chờ I/O hoặc lock tương ứng).
- JVM có thể trì hoãn/giới hạn GC trong lúc giữ critical pointer, vì vậy giữ quá lâu có thể ảnh hưởng toàn bộ ứng dụng.

Nếu chỉ cần xử lý mảng trong một vòng lặp ngắn và đã đo được nút cổ chai, mới xem xét `GetPrimitiveArrayCritical`. Với đoạn xử lý cần Java callback, I/O, chờ lock hoặc thực hiện công việc kéo dài, tránh giữ critical region mở. Cũng không được áp dụng cùng một bộ quy tắc cho cả hai nhóm mà quên những hạn chế tăng thêm của nhóm Critical.

## 9. Khi nào nên dùng `Get/Set<Type>ArrayRegion` thay thế?

Không phải lúc nào cũng cần lấy con trỏ toàn bộ mảng. JNI có nhóm thao tác **copy một vùng xác định**:

```c
void GetIntArrayRegion(
        JNIEnv *env, jintArray array,
        jsize start, jsize len, jint *buf);

void SetIntArrayRegion(
        JNIEnv *env, jintArray array,
        jsize start, jsize len, const jint *buf);
```

Trong C JNI, API thực được gọi qua `(*env)->GetIntArrayRegion(...)` và `(*env)->SetIntArrayRegion(...)`.

- `GetIntArrayRegion` copy đoạn `[start, start + len)` từ mảng Java vào buffer C **do bạn cung cấp**.
- `SetIntArrayRegion` copy dữ liệu từ buffer C vào vùng tương ứng của mảng Java.
- Nhóm `Region` **không trả pointer cần `Release...`**; bạn quản lý bộ nhớ buffer C của mình và phải kiểm tra chỉ số, độ dài, exception.
- Nếu chỉ xử lý một **slice nhỏ** của mảng rất lớn, Region có thể tránh việc JVM phải cung cấp/copy toàn bộ nội dung khi gọi GetElements; tuy nhiên nó vẫn là copy có chủ đích, không phải lời hứa nhanh hơn mọi trường hợp.

Ví dụ minh họa (giả định `env`/`arr` hợp lệ và mảng có ít nhất ba phần tử):

```c
jint values[3];
(*env)->GetIntArrayRegion(env, arr, 0, 3, values);
/* Nếu không có exception: có thể đọc/sửa values trong C. */
values[0] += 100;
(*env)->SetIntArrayRegion(env, arr, 0, 3, values);
```

Đoạn code này **không phải chương trình C độc lập**; sau `GetIntArrayRegion` trong chương trình thực nên kiểm tra exception trước khi sử dụng buffer khi có khả năng tham số không hợp lệ.

### 9.1. So sánh lựa chọn API

| Nhu cầu | API gợi ý | Bản chất |
| --- | --- | --- |
| Đọc/sửa hầu hết phần tử của primitive array | `Get<Type>ArrayElements` và `Release...` | Copy hoặc direct tùy JVM |
| Chỉ đọc primitive array và không cần copy-back | `Get...Elements`, release `JNI_ABORT` | Luôn release; nếu copy, bỏ bước chép ngược |
| Chỉ thao tác một đoạn nhỏ | `Get/Set<Type>ArrayRegion` | Copy phạm vi cụ thể, không có cặp release |
| Vòng xử lý rất ngắn, kiểm soát được critical region | `GetPrimitiveArrayCritical` / `Release...Critical` | Cố giảm copy, nhưng có hạn chế rất chặt |
| Truy cập phần tử của `Object[]` / `String[]` | `GetObjectArrayElement` / `SetObjectArrayElement` | Làm việc với tham chiếu đối tượng, không phải primitive pointer |
| Chia sẻ vùng native rõ vòng đời thay vì Java heap array | `DirectByteBuffer` và các API direct buffer thích hợp | Thiết kế bộ nhớ/ownership khác, cần quản lý vòng đời |

## 10. Các lỗi phổ biến với copy/pin

### Lỗi 1 — Không release vì `isCopy == JNI_FALSE`

```c
jboolean copied;
jint *p = (*env)->GetIntArrayElements(env, arr, &copied);
if (p != NULL && copied == JNI_TRUE) {
    (*env)->ReleaseIntArrayElements(env, arr, p, 0);
}
/* SAI: nhánh direct không được release! */
```

Dù copy hay direct, pointer nhận thành công đều phải trả lại cho JVM. Code đúng phải release sau khi hoàn tất mọi xử lý, không dựa vào `isCopy`.

### Lỗi 2 — Coi `JNI_ABORT` là “undo”

`JNI_ABORT` bỏ copy-back **khi JVM có bản sao**, nhưng không undo sửa đổi nếu pointer là direct. Nếu muốn thao tác có thể hủy, **đừng sửa trực tiếp pointer gốc**; hãy xử lý trên buffer độc lập rồi commit có chủ đích.

### Lỗi 3 — Sử dụng pointer sau release

```c
jint *p = (*env)->GetIntArrayElements(env, arr, NULL);
if (p != NULL) {
    (*env)->ReleaseIntArrayElements(env, arr, p, 0);
    /* p[0] = 42;  SAI: p không còn hợp lệ để truy cập. */
}
```

Cả vùng copy đã được giải phóng lẫn vùng direct sau release đều không còn quyền truy cập theo hợp đồng JNI.

### Lỗi 4 — Dùng sai `Release<Type>ArrayElements`

`GetIntArrayElements` phải ghép với `ReleaseIntArrayElements`, dùng **cùng `jintArray` và cùng pointer** được cấp. Không thay bằng `ReleaseByteArrayElements` hoặc giải phóng bằng allocator C.

### Lỗi 5 — Quên kiểm tra `NULL` và ngoại lệ

`Get...Elements` có thể trả `NULL` (ví dụ thiếu bộ nhớ). Dereference ngay gây crash native. Nếu cần trả giá trị thành công cho Java, hãy xử lý thất bại thành exception/đường báo lỗi rõ ràng và vẫn cleanup tài nguyên đã lấy từ trước đó.

### Lỗi 6 — Giả định thay đổi hiển thị trước release

Nếu JVM copy, nội dung mảng Java có thể chưa được đồng bộ. Nếu direct, thay đổi có thể đã tồn tại trong heap nhưng **không đồng nghĩa được phép cho các thread khác đọc đua**. `Get/Release...Elements` không cung cấp một giao thức đồng bộ Java Memory Model độc lập; sử dụng locking, ownership hoặc chuyển giao dữ liệu rõ ràng nếu có nhiều thread.

### Lỗi 7 — Dùng `JNI_COMMIT` rồi tưởng đã xong

Nếu JVM copy, `JNI_COMMIT` chép nội dung về nhưng **giữ buffer tạm**. Cần một lần release cuối phù hợp để giải phóng. Đơn giản nhất cho tác vụ bình thường là release `mode=0` ngay một lần.

### Lỗi 8 — Dùng `GetPrimitiveArrayCritical` cho thao tác chậm

Giữ critical pointer trong lúc gọi mạng, chờ khóa hoặc gọi lại JNI có thể vi phạm hạn chế của API và làm GC bị ảnh hưởng. Phần xử lý dài nên tách khỏi critical region.

## 11. Tình huống thiết kế thực tế

**Tình huống A: thư viện C xử lý toàn bộ mảng mẫu âm thanh `short[]`.** Nếu mỗi lời gọi xử lý một block dữ liệu hoàn chỉnh và cần ghi kết quả trở lại, dùng `GetShortArrayElements`, sửa trong native, release `0`. Đo thời gian tổng thể; pin/copy là quyết định của JVM, không nên nhắm tới một giá trị `isCopy` cụ thể.

**Tình huống B: chỉ đọc vài byte header từ một mảng `byte[]` rất lớn.** Dùng `GetByteArrayRegion` với đúng kích thước header thường dễ kiểm soát: chỉ copy một phần, buffer thuộc sở hữu code C, không giữ pointer mảng Java.

**Tình huống C: cần đọc một mảng nhiều lần nhưng không sửa.** Có thể `Get<Type>ArrayElements` rồi release `JNI_ABORT` ở mỗi phạm vi ngắn. Nếu cùng thuật toán được gọi dày đặc, đo chi phí từng lượt và cân nhắc gộp công việc/lựa chọn cấu trúc bộ nhớ khác; đừng giữ pointer lâu chỉ để tiết kiệm lời gọi.

**Tình huống D: muốn “sửa thử” rồi có quyền hủy.** Không dùng `JNI_ABORT` như transaction. Tạo bản sao độc lập do ứng dụng quản lý, xử lý trên bản sao, chỉ ghi vào mảng Java khi quyết định áp dụng.

**Tình huống E: mảng được nhiều Java thread cùng sửa.** Không dùng `isCopy` để suy luận dữ liệu sẽ nhất quán. Thiết kế handoff/đồng bộ trước và sau lời gọi native hoặc sử dụng thread confinement; tránh truy cập đồng thời không phối hợp.

## 12. Câu hỏi tự kiểm tra

**1. `GetIntArrayElements` có chắc trả địa chỉ gốc của `int[]` không?** Không. JVM có thể trả buffer sao chép hoặc vùng truy cập trực tiếp. Quy tắc đúng là dùng pointer trong thời gian hợp lệ và luôn release.

**2. `isCopy == JNI_TRUE` có nghĩa là Java array đã thay đổi ngay khi C sửa `p[0]`?** Không. Bản sao có thể chỉ được đồng bộ khi `ReleaseIntArrayElements` thực hiện copy-back (với mode phù hợp).

**3. `isCopy == JNI_FALSE` thì có được bỏ `ReleaseIntArrayElements` không?** Không. JVM vẫn cần kết thúc quyền truy cập/cleanup, kể cả khi không có copy.

**4. Có thể dùng `JNI_ABORT` để bỏ mọi thay đổi native không?** Không. Nó chỉ bỏ copy-back của buffer sao chép. Với direct pointer, thay đổi có thể đã ghi vào mảng thật.

**5. Tại sao `JNI_COMMIT` chưa đủ trong nhánh copy?** Vì buffer tạm chưa được giải phóng; phải có release cuối với `0` hoặc `JNI_ABORT`.

**6. `GetPrimitiveArrayCritical` có buộc JVM zero-copy không?** Không. API critical tăng cơ hội direct nhưng vẫn có thể copy, đồng thời yêu cầu thời gian critical rất ngắn và hạn chế các lời gọi bên trong.

**7. Nếu chỉ cần đọc năm phần tử giữa mảng triệu phần tử, nên cân nhắc gì?** `Get<Type>ArrayRegion` cho slice cụ thể, rồi kiểm tra lỗi; tránh quản lý pointer cho cả mảng khi không cần.

## 13. Checklist khi viết và review JNI array code

1. Chọn đúng nhóm primitive `Get<Type>ArrayElements` cho kiểu mảng; đừng dùng nó với object array.
2. Bảo đảm `jarray` khác null; xử lý độ dài và giới hạn chỉ số.
3. Kiểm tra pointer trả về **`NULL`** trước khi dereference.
4. Chỉ coi `isCopy` là thông tin quan sát một lần, không phải điều kiện bỏ release hay bảo đảm hiệu năng.
5. Nếu sửa mảng và muốn giữ kết quả, ưu tiên `Release(..., 0)`.
6. Nếu **chỉ đọc**, có thể dùng `JNI_ABORT` để không copy-back; nhớ nó không phải rollback cho thao tác đã sửa.
7. Nếu dùng `JNI_COMMIT` trên buffer copy, phải có lần release cuối để giải phóng.
8. Không giữ pointer quá lâu, dùng sau release, giải phóng thủ công hoặc trao cho thread khác mà không có hợp đồng an toàn.
9. Nếu chỉ xử lý slice, cân nhắc `Get/Set<Type>ArrayRegion`; nếu cân nhắc Critical, tuân thủ đầy đủ hạn chế blocking/JNI calls.
10. Test kết quả logic trên **nhiều JVM/GC/OS** nếu sản phẩm có yêu cầu; không assert giá trị `isCopy` cố định. Benchmark đo cả độ trễ, GC và bộ nhớ native.

## Tài liệu tham khảo chính thức

- [Oracle — JNI Functions (Java 17): Get<PrimitiveType>ArrayElements và Release<PrimitiveType>ArrayElements](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/functions.html): quy tắc pointer, `isCopy`, `mode=0`, `JNI_COMMIT`, `JNI_ABORT`.
- [Oracle — JNI Functions (Java 17): Get/Set<PrimitiveType>ArrayRegion](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/functions.html): thao tác sao chép một đoạn mảng.
- [Oracle — JNI Functions (Java 17): GetPrimitiveArrayCritical](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/functions.html): ý nghĩa critical region và các hạn chế.
- [Oracle — JNI Specification (Java 17)](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/index.html): tổng quan kiểu, vòng đời reference, cách JNI liên kết Java/C.
- [OpenJDK — JEP 472: Prepare to Restrict the Use of JNI](https://openjdk.org/jeps/472): hành vi cảnh báo/cấu hình quyền JNI từ JDK 24.