# Ý nghĩa sao chép ngược, JNI_COMMIT và JNI_ABORT khi trả mảng

Khi gọi **GetIntArrayElements** hoặc một hàm **Get\<PrimitiveType\>ArrayElements** tương ứng, native code nhận một con trỏ để truy cập các phần tử mảng nguyên thủy của Java. JVM có thể cung cấp **bản sao** hoặc **truy cập trực tiếp** vào dữ liệu mảng. Lựa chọn này ảnh hưởng đến thời điểm Java nhìn thấy các thay đổi, ý nghĩa của **JNI_ABORT**, và việc cần giải phóng buffer sau **JNI_COMMIT**.

Ba mode của **Release\<PrimitiveType\>ArrayElements** có ý nghĩa:

- **0:** nếu dùng bản sao, copy-back các phần tử đã thay đổi vào Java array và giải phóng buffer; nếu không sao chép, kết thúc quyền truy cập vào dữ liệu trực tiếp.
- **JNI_COMMIT:** nếu dùng bản sao, copy-back các giá trị hiện tại nhưng **giữ buffer bản sao** để có thể tiếp tục dùng; sau đó cần một lần release cuối với **0** hoặc **JNI_ABORT**. Khi không có bản sao, mode không làm thay đổi ngữ nghĩa giải phóng.
- **JNI_ABORT:** nếu dùng bản sao, giải phóng buffer **mà không copy-back các thay đổi chưa được commit**; nếu truy cập trực tiếp, **không thể hoàn tác những thay đổi đã ghi vào mảng Java**.

**Điểm mấu chốt:** **JNI_ABORT không phải rollback giao dịch**, và **JNI_COMMIT không phải cách kết thúc mọi lần mượn mảng**. Bài này đi từ mô hình bộ nhớ, bảng hành vi chính xác, code JNI chạy được đến cách thiết kế cập nhật mảng có khả năng từ chối kết quả.

## 1. Mượn dữ liệu mảng Java từ native

Một mảng Java **int[]** tương ứng kiểu **jintArray** của JNI. Khi cần thao tác nhiều phần tử, native thường thực hiện:

~~~c
/* Fragment bên trong một hàm JNI trả về void.
 * Yêu cầu array hợp lệ và có ít nhất một phần tử. */
jboolean isCopy = JNI_FALSE;
jint *elements = (*env)->GetIntArrayElements(env, array, &isCopy);
if (elements == NULL) {
    return; /* Không dereference; JVM có thể đang có exception. */
}

elements[0] = 42;
(*env)->ReleaseIntArrayElements(env, array, elements, 0);
~~~

**GetIntArrayElements** trả con trỏ hợp lệ trong khoảng quyền truy cập do cặp **Get/Release** quản lý. Không được gọi **free(elements)**, **delete[] elements**, giữ pointer để dùng sau khi đã release, hay giả định đó luôn là địa chỉ heap thật của Java array. JVM có quyền chọn chiến lược cấp dữ liệu theo lần gọi, loại mảng và trạng thái runtime.

Hai đường đi có thể xảy ra:

~~~text
A. JVM cấp một buffer bản sao

Java int[] [1, 2, 3]  ── copy ──> native p [1, 2, 3]
                                         |
                                        p[0] = 42
                                         |
                            Release mode=0 / JNI_COMMIT
                                         |
Java int[] [42, 2, 3] <────── copy-back ┘

B. JVM cho truy cập trực tiếp

Java int[] [1, 2, 3]  <───── p cùng dữ liệu ─────> native
            |
          p[0] = 42
            |
Java int[] [42, 2, 3]      (đã đổi trực tiếp)
            |
     Release kết thúc quyền truy cập
~~~

Với nhánh A, sửa con trỏ chưa nhất thiết sửa Java array trước lúc copy-back. Với nhánh B, sửa con trỏ có thể sửa Java array ngay. Dù dùng nhánh nào cũng phải **Release** đúng cặp.

## 2. isCopy: nhận biết bản sao, không điều khiển JVM

Hàm JNI có dạng:

~~~c
jint *GetIntArrayElements(
    JNIEnv *env, jintArray array, jboolean *isCopy);
~~~

Nếu **isCopy** là địa chỉ biến **jboolean**:

- **JNI_TRUE**: JVM tạo bản sao; muốn giữ các sửa đổi phải copy-back.
- **JNI_FALSE**: con trỏ trả về không phải bản sao; sửa đổi có thể xảy ra trực tiếp trên Java array.
- **NULL** ở tham số **isCopy**: không yêu cầu JVM trả thông tin cho bạn; **không yêu cầu JVM cấp pointer trực tiếp**.

Một lần **isCopy == JNI_TRUE** không bảo đảm lần sau cũng như vậy. Một lần **isCopy == JNI_FALSE** không cho phép bỏ qua **Release** hay giữ pointer vô hạn. Quy tắc vòng đời JNI vẫn áp dụng ở cả hai trường hợp.

Ví dụ khi chỉ cần đọc:

~~~c
/* Fragment: array hợp lệ, env thuộc thread hiện tại. */
jboolean copied = JNI_FALSE;
jint *p = (*env)->GetIntArrayElements(env, array, &copied);
if (p == NULL) {
    return;
}
/* Xử lý đọc từ p; không sửa bất kỳ phần tử nào. */
(*env)->ReleaseIntArrayElements(env, array, p, JNI_ABORT);
~~~

**JNI_ABORT** thường phù hợp khi chỉ đọc vì không cần copy-back; điều kiện này khác hoàn toàn với việc cố gắng “hủy sửa đổi đã xảy ra”.

## 3. So sánh chính xác mode 0, JNI_COMMIT và JNI_ABORT

Chữ ký:

~~~c
void ReleaseIntArrayElements(
    JNIEnv *env, jintArray array, jint *elems, jint mode);
~~~

| Mode | **isCopy == JNI_TRUE**: buffer bản sao | **isCopy == JNI_FALSE**: dữ liệu trực tiếp |
| --- | --- | --- |
| **0** | Copy-back toàn bộ buffer rồi giải phóng | Kết thúc truy cập; thay đổi đã ghi trực tiếp được giữ |
| **JNI_COMMIT** | Copy-back nhưng không giải phóng bản sao; cần release cuối | Mode không có hiệu lực riêng khi không có bản sao; không coi pointer vẫn dùng được sau Release |
| **JNI_ABORT** | Bỏ nội dung chưa copy-back và giải phóng bản sao | Không phục hồi sửa đổi trực tiếp; kết thúc quyền truy cập |

Tài liệu JNI quy định tham số **mode không có tác dụng nếu elems không phải bản sao**. Vì vậy chỉ có thể dựa vào khả năng giữ buffer sau **JNI_COMMIT** khi thực sự được cấp bản sao (**isCopy == JNI_TRUE**). Trong nhánh còn lại, hãy xem quyền truy cập đã kết thúc sau Release.

### 3.1. mode = 0: kết quả được áp dụng

Giả sử Java có mảng **[1, 2, 3]**:

~~~c
p[0] = 10;
(*env)->ReleaseIntArrayElements(env, array, p, 0);
~~~

Sau khi hàm JNI trả về bình thường, Java có:

~~~text
[10, 2, 3]
~~~

Kết quả không phụ thuộc chiến lược copy hay direct: khi copy thì release chép giá trị về; khi direct thì giá trị đã đổi. **p hết hạn sử dụng sau release**.

### 3.2. JNI_ABORT: hai kết quả hợp lệ

~~~c
p[0] = 10;
(*env)->ReleaseIntArrayElements(env, array, p, JNI_ABORT);
~~~

Nếu ban đầu Java có **[1, 2, 3]**:

| isCopy | Mảng Java sau release | Nguyên nhân |
| --- | --- | --- |
| **JNI_TRUE** | **[1, 2, 3]** | 10 chỉ nằm trong buffer bản sao, không copy-back |
| **JNI_FALSE** | **[10, 2, 3]** | 10 đã được ghi trực tiếp; JNI_ABORT không undo |

Hệ quả: không được dùng **JNI_ABORT** làm cơ chế rollback nghiệp vụ cho một thuật toán sửa mảng rồi có thể bị từ chối.

### 3.3. JNI_COMMIT: checkpoint copy-back cho bản sao

Khi chắc chắn **isCopy == JNI_TRUE**, có thể thực hiện:

~~~c
p[0] = 10;
(*env)->ReleaseIntArrayElements(env, array, p, JNI_COMMIT);
/* Java đã nhận 10; buffer bản sao vẫn được giữ. */

p[0] = 20;
(*env)->ReleaseIntArrayElements(env, array, p, JNI_ABORT);
/* 20 không được copy-back; Java vẫn giữ 10. */
~~~

Java nhận **[10, 2, 3]**. **JNI_ABORT ở cuối không hoàn tác được lần JNI_COMMIT trước**. Nếu release cuối dùng mode **0** thì bản sao mới có **20** sẽ được copy-back, cho kết quả **[20, 2, 3]**.

Lưu ý: đoạn trên chỉ hợp lệ khi **p là bản sao còn được giữ**. Nếu **isCopy == JNI_FALSE**, đừng truy cập lại **p** sau lời gọi Release với **JNI_COMMIT**. Trong thực tế, nếu không cần tiếp tục dùng buffer sau copy-back, chỉ gọi **Release(..., 0)** là đủ và ít gây lỗi.

### 3.4. Bảng lựa chọn thực tế

| Mục đích | Cách làm nên dùng |
| --- | --- |
| Native sửa array, Java phải nhận kết quả | **Release(..., 0)** |
| Native chỉ đọc, không sửa gì | **Release(..., JNI_ABORT)** để không copy ngược vô ích |
| Muốn công bố trạng thái hiện tại rồi tiếp tục dùng **bản sao** | **JNI_COMMIT** với **isCopy == JNI_TRUE**, sau đó release cuối |
| Muốn loại bỏ toàn bộ tác động nếu thuật toán thất bại | **Buffer độc lập** và chỉ ghi vào Java khi được chấp thuận |
| Chỉ đọc/ghi một vùng cụ thể | **Get...ArrayRegion/Set...ArrayRegion** theo hợp đồng mong muốn |

## 4. Ví dụ JNI chạy được với Java 17+: quan sát cả ba mode

Ví dụ minh họa ba lần mượn mảng riêng biệt và in **isCopy** cho từng lần; không ép JVM phải copy hay pin. Nó cũng thêm đường đi “chấp thuận/từ chối” bằng buffer do native sở hữu.

### 4.1. Java: src/ReleaseModesDemo.java

~~~java
import java.util.Arrays;

public final class ReleaseModesDemo {
    static {
        System.loadLibrary("release_modes");
    }

    private static final int NORMAL = 0;
    private static final int ABORT = 1;
    private static final int COMMIT_THEN_ABORT = 2;

    private static native boolean edit(int[] values, int scenario);
    private static native void applyWhenAccepted(int[] values, boolean accept);

    private static void require(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) {
        int[] a = {1, 2, 3};
        boolean copyA = edit(a, NORMAL);
        System.out.printf("normal: %s (isCopy=%s)%n",
                Arrays.toString(a), copyA);
        require(a[0] == 10, "mode 0 must apply the change");

        int[] b = {1, 2, 3};
        boolean copyB = edit(b, ABORT);
        System.out.printf("abort: %s (isCopy=%s)%n",
                Arrays.toString(b), copyB);
        require(b[0] == (copyB ? 1 : 10),
                "JNI_ABORT must respect the copy/direct branch");

        int[] c = {1, 2, 3};
        boolean copyC = edit(c, COMMIT_THEN_ABORT);
        System.out.printf("commit: %s (isCopy=%s)%n",
                Arrays.toString(c), copyC);
        require(c[0] == 10, "committed value must remain");

        int[] staged = {1, 2, 3};
        applyWhenAccepted(staged, false);
        System.out.println("reject: " + Arrays.toString(staged));
        require(staged[0] == 1, "reject must keep original data");

        applyWhenAccepted(staged, true);
        System.out.println("accept: " + Arrays.toString(staged));
        require(staged[0] == 77, "accept must publish new data");

        System.out.println("Checks passed");
    }
}
~~~

Ba số **NORMAL/ABORT/COMMIT_THEN_ABORT** là **mã kịch bản của chương trình Java**, không phải giá trị hằng **JNI_ABORT/JNI_COMMIT**. Phía C chuyển lựa chọn sang mode JNI thực sự.

### 4.2. C: native/release_modes.c

~~~c
#include <jni.h>

static void invalid_input(JNIEnv *env, const char *message) {
    jclass type = (*env)->FindClass(
            env, "java/lang/IllegalArgumentException");
    if (type != NULL) {
        (*env)->ThrowNew(env, type, message);
        (*env)->DeleteLocalRef(env, type);
    }
}

JNIEXPORT jboolean JNICALL
Java_ReleaseModesDemo_edit(
        JNIEnv *env, jclass owner, jintArray array, jint scenario) {
    (void)owner;

    if (array == NULL) {
        invalid_input(env, "array must not be null");
        return JNI_FALSE;
    }
    if ((*env)->GetArrayLength(env, array) < 1) {
        invalid_input(env, "array must not be empty");
        return JNI_FALSE;
    }
    if (scenario < 0 || scenario > 2) {
        invalid_input(env, "unknown scenario");
        return JNI_FALSE;
    }

    jboolean copied = JNI_FALSE;
    jint *p = (*env)->GetIntArrayElements(env, array, &copied);
    if (p == NULL) {
        return JNI_FALSE; /* Không dereference; có thể có exception. */
    }

    p[0] = 10;

    if (scenario == 0) {
        (*env)->ReleaseIntArrayElements(env, array, p, 0);
    } else if (scenario == 1) {
        (*env)->ReleaseIntArrayElements(env, array, p, JNI_ABORT);
    } else {
        (*env)->ReleaseIntArrayElements(env, array, p, JNI_COMMIT);

        if (copied == JNI_TRUE) {
            /*
             * Chỉ nhánh có bản sao còn giữ buffer sau COMMIT.
             * Sửa lần nữa nhưng bỏ thay đổi thứ hai.
             */
            p[0] = 20;
            (*env)->ReleaseIntArrayElements(env, array, p, JNI_ABORT);
        }
        /* Nếu không copy, không sử dụng p sau Release. */
    }

    return copied;
}

JNIEXPORT void JNICALL
Java_ReleaseModesDemo_applyWhenAccepted(
        JNIEnv *env, jclass owner, jintArray array, jboolean accept) {
    (void)owner;

    if (array == NULL) {
        invalid_input(env, "array must not be null");
        return;
    }
    if ((*env)->GetArrayLength(env, array) != 3) {
        invalid_input(env, "array must have exactly 3 items");
        return;
    }

    /* Buffer này thuộc native, tách biệt Java array. */
    jint staging[3];
    (*env)->GetIntArrayRegion(env, array, 0, 3, staging);
    if ((*env)->ExceptionCheck(env)) {
        return;
    }

    staging[0] = 77;
    if (accept == JNI_TRUE) {
        (*env)->SetIntArrayRegion(env, array, 0, 3, staging);
    }
}
~~~

Hai export **Java_ReleaseModesDemo_edit** và **Java_ReleaseModesDemo_applyWhenAccepted** ứng với class Java trong **default package** và hai native method **static**; tham số thứ hai là **jclass**. Khi ứng dụng đặt class vào package khác, phải cập nhật tên symbol JNI theo package hoặc dùng đăng ký native methods.

**Giải thích đường đi:**

1. **scenario 0** sửa phần tử đầu rồi release bằng mode **0**, luôn trả lại **10** cho Java.
2. **scenario 1** sửa phần tử đầu rồi release bằng **JNI_ABORT**, giữ **1** nếu copy hoặc nhận **10** nếu direct.
3. **scenario 2** gọi **JNI_COMMIT** sau khi ghi **10**; nếu có bản sao thì sửa tiếp thành **20**, rồi release **JNI_ABORT** để bỏ sửa đổi thứ hai. Nếu không có bản sao thì không tái sử dụng pointer đã release. Kết quả Java là **10** ở cả hai nhánh.
4. **applyWhenAccepted** sao chép vào **staging** bằng **GetIntArrayRegion**; chỉ khi accept mới gọi **SetIntArrayRegion**. Vì vậy từ chối có kết quả ổn định, không phụ thuộc JVM chọn copy hay direct trong API khác.

### 4.3. Biên dịch và chạy (Linux, JDK 17+)

Cấu trúc file:

~~~text
src/ReleaseModesDemo.java
native/release_modes.c
~~~

Đảm bảo **JAVA_HOME** trỏ tới JDK cài đặt có header JNI và C compiler cùng kiến trúc với JVM:

~~~bash
mkdir -p src native out

javac -h native -d out src/ReleaseModesDemo.java

cc -std=c17 -Wall -Wextra -Wpedantic -fPIC -shared \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  native/release_modes.c -o librelease_modes.so

java -Xcheck:jni -Djava.library.path=. -cp out ReleaseModesDemo
~~~

**javac -h** sinh header chứa prototype JNI để đối chiếu; C source trên dùng **jni.h** và tên export đúng class demo. Trên Windows/macOS, thay cách build shared library và đường dẫn include theo toolchain/JDK; không dùng nguyên xi lệnh Linux.

### 4.4. Stdout: có nhiều kết quả đúng do isCopy

Nếu cả ba lần đều dùng buffer bản sao, stdout có thể là:

~~~text
normal: [10, 2, 3] (isCopy=true)
abort: [1, 2, 3] (isCopy=true)
commit: [10, 2, 3] (isCopy=true)
reject: [1, 2, 3]
accept: [77, 2, 3]
Checks passed
~~~

Nếu cả ba lần đều truy cập trực tiếp:

~~~text
normal: [10, 2, 3] (isCopy=false)
abort: [10, 2, 3] (isCopy=false)
commit: [10, 2, 3] (isCopy=false)
reject: [1, 2, 3]
accept: [77, 2, 3]
Checks passed
~~~

Đây là **hai ví dụ có điều kiện**, không phải cam kết lựa chọn cố định của JVM. Từng lần Get có thể trả **true** hoặc **false** độc lập. Những **require** trong chương trình xác minh ngữ nghĩa theo **isCopy thực tế**, còn **reject/accept** luôn có kết quả xác định.

Nếu thiếu thư viện hoặc kiến trúc JNI không khớp, JVM có thể ném **UnsatisfiedLinkError** trước khi chạy demo; đó là lỗi build/load khác với ngữ nghĩa release mode.

## 5. Vì sao không nên dùng JNI_ABORT như lệnh hủy giao dịch?

Giả sử native code sửa dữ liệu rồi kiểm tra tính hợp lệ. Mẫu xử lý sau có **lỗi ý nghĩa**:

~~~c
/* Phản ví dụ; giả định p lấy thành công từ GetIntArrayElements. */
p[0] = 99;
if (validationFailed) {
    (*env)->ReleaseIntArrayElements(env, array, p, JNI_ABORT);
    return;
}
(*env)->ReleaseIntArrayElements(env, array, p, 0);
~~~

Nếu **p** là direct pointer, mảng Java đã có **99**, dù nhánh validation thất bại. Do đó **JNI_ABORT** không cung cấp đảm bảo “failure ⇒ Java array unchanged”.

Một thiết kế có quyền từ chối rõ ràng:

~~~text
Đọc Java array vào vùng native riêng
            |
            v
    Tính toán / kiểm tra
         /        \
   thất bại      thành công
      |              |
không Set...     Set...ArrayRegion
      |              |
Java không đổi   Java nhận kết quả
~~~

Tùy bài toán, chọn:

- **GetIntArrayRegion → staging → SetIntArrayRegion**: thích hợp với đoạn có kích thước đã biết, native quản lý buffer.
- **Java array.clone() → xử lý clone → chấp thuận mới áp dụng**: tận dụng quản lý bộ nhớ Java, hữu ích khi Java quyết định kết quả.
- **Tạo mảng Java mới bằng NewIntArray/SetIntArrayRegion**: trả dữ liệu kết quả riêng, caller quyết định dùng hay bỏ.
- **Native buffer độc lập với malloc**: nếu dữ liệu lớn, phải tính **sizeof(jint) * len** an toàn, kiểm tra cấp phát và **free** đúng lúc. Đây là buffer thuộc native chứ không phải pointer Get...Elements.

Ví dụ Java-only cho ý tưởng này:

~~~java
import java.util.Arrays;

public final class ArrayDecision {
    static void maybeReplace(int[] target, boolean accept) {
        int[] candidate = target.clone();
        candidate[0] = 99;
        if (accept) {
            System.arraycopy(candidate, 0, target, 0, target.length);
        }
    }

    public static void main(String[] args) {
        int[] values = {1, 2, 3};
        maybeReplace(values, false);
        System.out.println(Arrays.toString(values));
        maybeReplace(values, true);
        System.out.println(Arrays.toString(values));
    }
}
~~~

Lưu thành **ArrayDecision.java**, rồi chạy **javac ArrayDecision.java** và **java ArrayDecision**. Stdout chính xác:

~~~text
[1, 2, 3]
[99, 2, 3]
~~~

Đây là chương trình **Java-only**, không dùng JNI. Ví dụ native **applyWhenAccepted** ở mục 4 triển khai cùng hợp đồng trên một buffer C.

**Cảnh báo giới hạn:** **Set...ArrayRegion** chỉ là phép sao chép vùng dữ liệu, không tự biến nhiều bước ghi thành transaction toàn cục. Nếu cần bảo đảm atomicity với các tài nguyên và thread khác, phải thiết kế commit/handoff theo yêu cầu nghiệp vụ.

## 6. Những API liên quan và phạm vi của mode

### 6.1. Primitive arrays

Các cặp **Get/Release\<PrimitiveType\>ArrayElements** có mode giống nhau:

| Java | JNI Get | JNI Release |
| --- | --- | --- |
| **boolean[]** | **GetBooleanArrayElements** | **ReleaseBooleanArrayElements** |
| **byte[]** | **GetByteArrayElements** | **ReleaseByteArrayElements** |
| **char[]** | **GetCharArrayElements** | **ReleaseCharArrayElements** |
| **short[]** | **GetShortArrayElements** | **ReleaseShortArrayElements** |
| **int[]** | **GetIntArrayElements** | **ReleaseIntArrayElements** |
| **long[]** | **GetLongArrayElements** | **ReleaseLongArrayElements** |
| **float[]** | **GetFloatArrayElements** | **ReleaseFloatArrayElements** |
| **double[]** | **GetDoubleArrayElements** | **ReleaseDoubleArrayElements** |

Mỗi cặp phải khớp kiểu và cùng mảng nguồn. Với **boolean[]**, JNI cung cấp các phần tử **jboolean**, mỗi phần tử có một byte phía native, bất kể JVM lưu boolean nội bộ như thế nào. Các primitive array khác có dữ liệu liên tục theo JNI, nhưng địa chỉ được cấp vẫn phải quản lý bằng cặp Get/Release.

### 6.2. Get/Set ArrayRegion không có mode Release

**GetIntArrayRegion** sao chép một vùng mảng Java vào buffer C do caller sở hữu. **SetIntArrayRegion** sao chép ngược từ buffer C vào Java. Hai hàm không cấp pointer JNI mà bạn phải Release, nên **không nhận JNI_COMMIT/JNI_ABORT**. Hãy kiểm tra chỉ số và độ dài, kiểm tra exception, và không đọc/ghi vượt kích thước buffer.

### 6.3. GetPrimitiveArrayCritical có hạn chế nghiêm ngặt

**GetPrimitiveArrayCritical** và **ReleasePrimitiveArrayCritical** có ý nghĩa copy/direct và mode tương tự, nhưng tồn tại **critical region**:

- Thời gian từ Get đến Release phải rất ngắn.
- Không gọi tùy ý các hàm JNI khác trong critical region.
- Tránh syscall có thể chặn chờ Java thread, lock/callback/I/O kéo dài.
- Không mặc định API luôn cung cấp zero-copy; JVM vẫn có thể tạo bản sao.
- **JNI_ABORT** không hoàn tác sửa đổi trực tiếp nếu pointer không phải bản sao.

Không dùng **ReleaseIntArrayElements** để trả pointer do **GetPrimitiveArrayCritical** lấy; phải dùng **ReleasePrimitiveArrayCritical**.

### 6.4. String và object array không có các mode này

Java **String** bất biến, và các hàm **ReleaseStringChars**, **ReleaseStringUTFChars**, **ReleaseStringCritical** không nhận tham số **JNI_COMMIT/JNI_ABORT**. Với **jobjectArray**, dùng **GetObjectArrayElement/SetObjectArrayElement**; không có **ReleaseObjectArrayElements**. **DirectByteBuffer** có cơ chế sở hữu bộ nhớ riêng, cũng không dùng ba mode của primitive arrays.

## 7. Vòng đời, exception và ràng buộc thread

**Get thất bại:** nếu **GetIntArrayElements** trả **NULL**, không dereference, không gọi **ReleaseIntArrayElements** trên pointer NULL. JVM có thể báo **OutOfMemoryError** hoặc trạng thái lỗi; caller cần xử lý pending exception theo hợp đồng. JNI specification cũng cho phép một số hàm trả NULL mà không nhất thiết ném exception, nên không nên mặc định mọi NULL đều có exception.

**Release đúng cặp và đủ số lần:**

- Con trỏ từ **GetIntArrayElements** → **ReleaseIntArrayElements** trên **chính jintArray**.
- Sau **Release(..., 0)** hoặc **Release(..., JNI_ABORT)**, không đọc/ghi qua pointer.
- Với **isCopy==JNI_TRUE** và **JNI_COMMIT**, buffer bản sao còn sống; kết thúc bằng một release cuối **0** hoặc **JNI_ABORT**.
- Không lạm dụng release hai lần; chỉ nhánh buffer bản sao còn sống sau commit mới cần final release. Không gọi **free** lên pointer do JNI trả về.

**Không để rò buffer trên đường lỗi:** khi Get thành công mà sau đó có nhiều điều kiện return, cần tổ chức cleanup để đường nào cũng Release. Với code có thể thay đổi mảng rồi thất bại, dọn bằng JNI_ABORT **không đảm bảo dữ liệu bị hủy**; hãy chuyển sang buffer độc lập nếu cần bảo toàn mảng khi lỗi.

**Thread:** **JNIEnv*** thuộc thread, không chuyển sang native thread khác. **isCopy==JNI_FALSE** không cho phép native giữ pointer xuyên thời gian không hạn chế, kể cả khi địa chỉ không đổi. Nếu Java và native/Java thread khác cùng đọc ghi mảng, phải dùng giao thức đồng bộ hợp lệ; **Release...** không tự thay thế lock, happens-before hay một hợp đồng công bố kết quả.

**JNI_COMMIT không phải transaction commit:** giá trị đã copy-back có thể được Java quan sát trong những điều kiện hợp lệ, nhưng commit không đảm bảo atomicity cho nhiều mảng hoặc nhiều thao tác, không ghi dữ liệu xuống disk, không rollback được các side effect đã phát sinh, và không tự bảo đảm thread-safe visibility. Mốc copy-back cần phân biệt với mốc nghiệp vụ.

## 8. Các lỗi phổ biến

| Cách hiểu/cách làm sai | Rủi ro | Cách sửa |
| --- | --- | --- |
| “JNI_ABORT đảm bảo mảng không đổi” | Direct pointer đã sửa Java array | Dùng staging buffer và chỉ Set khi chấp thuận |
| “JNI_COMMIT giải phóng buffer như 0” | Buffer bản sao còn giữ, dễ rò tài nguyên | Release cuối khi **isCopy==JNI_TRUE** |
| “isCopy=false nên khỏi cần Release” | Vi phạm vòng đời JNI, có thể giữ tài nguyên liên quan GC | Luôn Release đúng cặp |
| Gọi **free(p)** sau Get | Sai quyền sở hữu, crash/corruption | Dùng **Release...ArrayElements** |
| Truy cập **p** sau Release cuối | Use-after-release | Không dùng pointer đã hết hạn |
| Sau **JNI_COMMIT** luôn sửa tiếp **p** | Nếu không copy, pointer không được bảo đảm còn hợp lệ | Chỉ tái sử dụng khi bản sao còn được giữ |
| Dùng **JNI_ABORT** để “hủy” một commit đã xảy ra | Giá trị commit vẫn nằm trong Java array | Thiết kế checkpoint hoặc transaction cấp cao |
| Trộn Get/Release của các kiểu khác nhau | Lỗi JNI, bộ nhớ không an toàn | Dùng đúng cặp kiểu và mảng gốc |
| Dùng **JNI_COMMIT** cho **String/jobjectArray** | Sai API | Dùng API string/object array phù hợp |
| Giữ critical pointer lâu, gọi JNI khác hoặc I/O chặn | Ảnh hưởng GC, có nguy cơ deadlock | Critical region thật ngắn |
| Không kiểm tra **NULL**/pending exception | Crash hoặc kết quả vô nghĩa | Kiểm tra và cleanup |
| Mong một lần Release đồng bộ mọi Java thread | Race, thiếu memory ordering | Thiết kế synchronization riêng |

## 9. Câu hỏi tự kiểm tra

**Câu 1.** Java có **[3, 4]**, native nhận **isCopy=JNI_TRUE**, gán **p[0]=9** rồi **JNI_ABORT**. Java nhận gì?

**Đáp án:** **[3, 4]**. Buffer bản sao bị bỏ trước khi copy-back.

**Câu 2.** Tình huống trên với **isCopy=JNI_FALSE**?

**Đáp án:** **[9, 4]**. Đã sửa trực tiếp, JNI_ABORT không hoàn tác.

**Câu 3.** Native nhận **bản sao**, ghi **p[0]=7**, gọi **JNI_COMMIT**, ghi tiếp **p[0]=8**, cuối cùng **JNI_ABORT**. Java nhận giá trị nào?

**Đáp án:** **7**, vì giá trị **7** đã được copy-back ở lần commit; giá trị **8** chỉ nằm trên buffer bản sao và bị bỏ sau đó.

**Câu 4.** Khi nào dùng mode **0** là hợp lý?

**Đáp án:** Khi native đã sửa dữ liệu và muốn Java nhận những giá trị đó, đồng thời muốn kết thúc việc giữ pointer ngay.

**Câu 5.** Dùng **JNI_ABORT** có bảo đảm native parser “chưa hề động đến dữ liệu Java” nếu parser đã sửa pointer trước khi báo lỗi?

**Đáp án:** Không. Phải dùng buffer riêng hoặc mảng kết quả mới nếu cần bảo đảm không thay đổi mảng gốc khi thất bại.

**Câu 6.** Vì sao **JNI_COMMIT** phải được phân biệt với transaction commit?

**Đáp án:** Nó chỉ có ngữ nghĩa copy-back/quản lý buffer JNI. Nó không đảm bảo nguyên tử nhiều thao tác, không cung cấp rollback và không tự thiết lập đồng bộ đa thread.

## Tài liệu chuẩn

- Oracle JNI Specification, Java SE 21 — **Get\<PrimitiveType\>ArrayElements / Release\<PrimitiveType\>ArrayElements**: https://docs.oracle.com/en/java/javase/21/docs/specs/jni/functions.html#releaseprimitivetypearrayelements-routines
- Oracle JNI Specification — **Get\<PrimitiveType\>ArrayRegion / Set\<PrimitiveType\>ArrayRegion**: https://docs.oracle.com/en/java/javase/21/docs/specs/jni/functions.html#getprimitivetypearrayregion-routines
- Oracle JNI Specification — **GetPrimitiveArrayCritical / ReleasePrimitiveArrayCritical**: https://docs.oracle.com/en/java/javase/21/docs/specs/jni/functions.html#getprimitivearraycritical-releaseprimitivearraycritical
- Oracle JNI Specification — **Exception Handling**: https://docs.oracle.com/en/java/javase/21/docs/specs/jni/functions.html#exception-handling

**Kết luận học tập:** **0** giữ sửa đổi và kết thúc quyền truy cập; **JNI_COMMIT** copy-back nhưng giữ **buffer bản sao**; **JNI_ABORT** chỉ bỏ thay đổi chưa copy-back **trên bản sao**. Muốn “hủy kết quả mà Java chắc chắn không đổi”, hãy dùng **staging buffer** và chủ động kiểm soát lúc copy dữ liệu về Java.