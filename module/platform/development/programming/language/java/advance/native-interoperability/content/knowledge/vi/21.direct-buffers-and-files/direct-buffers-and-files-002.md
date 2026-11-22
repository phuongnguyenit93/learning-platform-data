# Chia sẻ bộ đệm qua NewDirectByteBuffer và GetDirectBufferAddress trong JNI

## 1. Bài toán: Java và mã native cùng làm việc trên một vùng byte

Khi Java giao tiếp với C/C++ qua JNI, việc chuyển dữ liệu bằng `byte[]` đôi khi làm phát sinh một hoặc nhiều lần sao chép. Với dữ liệu lớn như khung hình, gói mạng, audio, dữ liệu mã hóa hoặc block I/O, bạn có thể cần để **Java và native thao tác trực tiếp trên cùng vùng lưu trữ**.

Một giải pháp chuẩn trong JNI là dùng **direct buffer** của `java.nio`:

- **`NewDirectByteBuffer(JNIEnv*, void*, jlong)`**: từ **địa chỉ bộ nhớ native đã có**, tạo một Java `ByteBuffer` trực tiếp tham chiếu vùng ấy.
- **`GetDirectBufferAddress(JNIEnv*, jobject)`**: từ một Java **direct buffer**, lấy địa chỉ vùng nhớ mà buffer đại diện để C/C++ đọc/ghi.
- **`GetDirectBufferCapacity(JNIEnv*, jobject)`**: lấy dung lượng vùng buffer theo **số phần tử**. Với `ByteBuffer`, mỗi phần tử là một byte, nên capacity chính là **số byte**.

Đây là cơ chế chia sẻ **backing memory** chứ không phải copy dữ liệu mỗi khi đi qua ranh giới JNI. Nếu Java sửa một byte, native có thể đọc chính byte đã sửa; nếu native ghi byte mới, Java có thể thấy nó qua cùng buffer. Tuy nhiên **chia sẻ vùng nhớ không có nghĩa là tự an toàn về vòng đời, luồng hoặc đồng bộ**.

> Hai hướng thường dùng:
>
> **Native cấp phát → Java dùng**: `malloc`/allocator native → `NewDirectByteBuffer` → Java `ByteBuffer` → native owner chủ động giải phóng khi mọi người đã ngừng dùng.
>
> **Java cấp phát → Native dùng**: `ByteBuffer.allocateDirect(...)` → truyền buffer qua native method → `GetDirectBufferAddress` → C/C++ đọc/ghi trong khoảng thời gian Java bảo đảm buffer còn sống.

Bài thuộc nhóm **Bộ đệm và tệp** của module *Java Advance - native-interoperability*. Các ví dụ sử dụng **JNI và Java 17 trở lên**, không yêu cầu FFM API hoặc `--enable-native-access` của JDK 22. Chỉ cần một JDK có header `jni.h`, compiler native tương thích và JVM có hỗ trợ JNI direct-buffer access.

## 2. Ba API cốt lõi và hợp đồng JNI

### 2.1. `NewDirectByteBuffer`

C signature:

```c
jobject NewDirectByteBuffer(
        JNIEnv *env, void *address, jlong capacity);
```

Trong C, cách gọi qua `JNIEnv`:

```c
jobject view =
    (*env)->NewDirectByteBuffer(env, address, (jlong)capacity);
```

Trong C++ với `jni.h`:

```cpp
jobject view = env->NewDirectByteBuffer(address, capacity);
```

Các đoạn trên là **minh họa**, cần một `JNIEnv*` hợp lệ trên thread hiện tại và vùng nhớ `address` đang sống. Hàm tạo một Java `java.nio.ByteBuffer` direct trỏ đến đúng vùng `address` có độ dài `capacity` **byte**, không copy các byte đó sang một backing array riêng.

Điều kiện quan trọng:

- `address` phải **không NULL** và trỏ đến vùng nhớ có thật, hợp lệ trong suốt thời gian Java có thể truy cập buffer.
- `capacity` là số byte trong vùng được cung cấp. Để tương thích thực tế tốt, bài sử dụng **capacity dương** và không vượt quá `Integer.MAX_VALUE`; `ByteBuffer.capacity()` ở Java là `int`. Không truyền số âm hoặc kích thước lớn hơn giới hạn Java buffer.
- Hàm trả `jobject` local reference tới `ByteBuffer`; khi trả về Java, kết quả trở thành Java reference thông thường.
- Nếu không tạo được object hoặc JVM không hỗ trợ JNI direct-buffer access, kết quả có thể là `NULL`; nếu có pending Java exception thì phải bảo toàn hoặc xử lý exception phù hợp.
- **NewDirectByteBuffer không cấp phát backing memory và không có nghĩa vụ gọi `free(address)`.** Chính native owner phải quyết định khi nào được giải phóng. Đây là nguồn lỗi use-after-free thường gặp nhất.
- Byte order ban đầu của buffer được tạo bởi JNI là **`BIG_ENDIAN`** theo đặc tả, không mặc nhiên là thứ tự byte CPU native.

**Ví dụ nguy hiểm:**

```c
JNIEXPORT jobject JNICALL Java_Example_bad(
        JNIEnv *env, jclass ignored) {
    unsigned char stackData[8] = {1, 2, 3, 4, 5, 6, 7, 8};
    return (*env)->NewDirectByteBuffer(
            env, stackData, (jlong)sizeof(stackData));
}
```

Đây là **mã cố tình sai**. `stackData` hết thời gian sống sau khi hàm return; `ByteBuffer` Java vẫn tồn tại nhưng con trỏ backing đã treo. Java đọc có thể trả dữ liệu rác, gây crash hoặc lỗi khác. Không sử dụng mẫu này.

### 2.2. `GetDirectBufferAddress`

C signature:

```c
void* GetDirectBufferAddress(JNIEnv *env, jobject buffer);
```

Khi Java truyền một `ByteBuffer.allocateDirect(...)` hoặc buffer được tạo bằng `NewDirectByteBuffer` vào JNI, native lấy địa chỉ đầu vùng buffer:

```c
void *base = (*env)->GetDirectBufferAddress(env, buffer);
```

- `base` trỏ tới **vị trí bắt đầu của vùng được biểu diễn bởi chính buffer object**, không tự dịch theo `position()`.
- Với một `ByteBuffer.slice()`, vùng của slice bắt đầu tại offset mà slice đại diện, vì vậy `base` của slice có thể khác `base` của buffer gốc.
- Không được dùng địa chỉ nếu kết quả là `NULL`. Nguyên nhân có thể là buffer không direct, vùng không xác định hoặc JVM không hỗ trợ JNI direct-buffer access.
- JNI `GetDirectBufferAddress` không tạo một snapshot, không pin Java heap array và không cấp phát vùng nhớ native mới.
- JNI function này nhận `jobject` biểu diễn **direct `java.nio.Buffer`**, không chỉ `ByteBuffer`; nhưng cách diễn giải kích thước/stride khác với typed view buffers như `IntBuffer`. Ví dụ chạy đầy đủ trong bài chỉ nhận **ByteBuffer** cho dễ kiểm chứng theo byte.

### 2.3. `GetDirectBufferCapacity`

C signature:

```c
jlong GetDirectBufferCapacity(JNIEnv *env, jobject buffer);
```

Trong C:

```c
jlong capacity = (*env)->GetDirectBufferCapacity(env, buffer);
```

- Trả `-1` khi đối tượng không phải direct buffer, khi nền tảng không hỗ trợ access tương ứng, hoặc trong một số trường hợp typed view buffer bị lệch alignment trên CPU không hỗ trợ unaligned access.
- Trả **số phần tử chứa được**. Với `ByteBuffer`, 1 phần tử = 1 byte; với `IntBuffer`, 1 phần tử = 1 `int`, **không phải** 1 byte.
- **`capacity` không phải `limit`, `position` hoặc `remaining`**. Native phải có quy ước riêng nếu chỉ được phép thao tác vùng `position..limit`.
- `jlong` cần được kiểm tra trước khi chuyển sang `size_t` hoặc một kiểu số nhỏ hơn trong C, tránh overflow/signedness.

Một mẫu kiểm tra cho `ByteBuffer`:

```c
if (buffer == NULL) {
    // Thông báo NullPointerException ở Java.
    return;
}

void *base = (*env)->GetDirectBufferAddress(env, buffer);
jlong capacity = (*env)->GetDirectBufferCapacity(env, buffer);

if (base == NULL || capacity < 0) {
    // Không dùng base; Java exception có thể được tạo tại đây.
    return;
}
```

Đây là **trích đoạn**, không phải C function độc lập. Ví dụ hoàn chỉnh ở mục 6 sẽ ném Java exception đúng cách thay vì return im lặng.

### 2.4. Không phải JVM nào cũng bắt buộc hỗ trợ JNI direct-buffer access

JNI Specification yêu cầu JVM cung cấp ba entry points này, nhưng cho phép một implementation **không hỗ trợ việc truy cập trực tiếp buffer từ JNI**. Khi không hỗ trợ:

- `NewDirectByteBuffer` và `GetDirectBufferAddress` trả `NULL`.
- `GetDirectBufferCapacity` trả `-1`.

Các HotSpot JVM phổ biến hỗ trợ tốt, nhưng code portable phải xử lý đường lỗi thay vì gọi `memcpy` với `NULL` hoặc trả một `ByteBuffer` null rồi coi như thành công. Nếu môi trường cần hỗ trợ JVM khác, hãy test tính năng hoặc triển khai fallback dựa trên `byte[]`.

## 3. So sánh direct buffer, heap buffer và byte array

| Đặc điểm | `ByteBuffer.allocateDirect(n)` | `ByteBuffer.allocate(n)` | `ByteBuffer.wrap(byte[])` | `NewDirectByteBuffer(nativePtr,n)` |
| --- | --- | --- | --- | --- |
| `isDirect()` | `true` | `false` | `false` | `true` nếu tạo thành công |
| Backing storage | Thường ở native/off-heap memory, JVM quản lý | Java heap array | Java heap array được caller cấp | Native memory do **caller** cung cấp |
| `GetDirectBufferAddress` | Có thể lấy địa chỉ nếu JVM hỗ trợ | `NULL` | `NULL` | Có thể lấy cùng địa chỉ gốc nếu JVM hỗ trợ |
| Có sao chép khi tạo? | Cấp phát vùng mới, không copy từ `byte[]` | Cấp phát mảng mới | Không copy mảng nguồn, nhưng heap-backed | Không copy backing native |
| Ai giải phóng backing? | JVM/cleaner theo cơ chế của buffer | GC Java heap | GC Java heap | **Native owner của địa chỉ** |
| Dùng `ByteBuffer.array()`? | Không nên giả định có backing array | Có | Có | Không nên giả định có backing array |
| Điểm cần lưu ý | Giữ Java buffer reachable trong khi native giữ pointer | Không phải direct; JNI cần copy/cách khác | `wrap` không làm array thành off-heap | Java reference còn tồn tại **không đảm bảo** backing native chưa được `free` |

**`ByteBuffer.wrap(array)` không phải “zero-copy JNI direct access”.** Nó chia sẻ một Java heap array, nhưng C không được dùng `GetDirectBufferAddress` để lấy pointer của mảng ấy. Nếu cần JNI với heap array, dùng `GetByteArrayRegion`/`SetByteArrayRegion` hoặc `GetByteArrayElements`/`ReleaseByteArrayElements` với hợp đồng pin/copy phù hợp.

Direct buffer giúp tránh **một số lần copy dữ liệu trên biên JNI**, nhưng vẫn có overhead JNI transition, bounds checks của Java API, và chi phí cấp phát/giải phóng native memory. Không mặc nhiên nhanh hơn heap array cho mọi workload nhỏ.

## 4. Đường đi Java → Native: `allocateDirect` và `GetDirectBufferAddress`

Một Java method có thể tự cấp phát direct buffer:

```java
ByteBuffer buffer = ByteBuffer.allocateDirect(4);

buffer.put(0, (byte)3);
buffer.put(1, (byte)4);
buffer.put(2, (byte)5);
buffer.put(3, (byte)6);

int total = nativeSum(buffer, 0, 4);
```

Đây là trích đoạn trong class có native method `nativeSum` tương ứng. Native code:

1. Nhận `jobject buffer`.
2. Lấy pointer bằng `GetDirectBufferAddress`.
3. Lấy capacity bằng `GetDirectBufferCapacity`.
4. Kiểm tra `offset`, `length` với capacity.
5. Đọc `uint8_t` từ địa chỉ `base + offset`, trả tổng.

Đối với mảng Java `{3,4,5,6}`, kết quả `3+4+5+6 = 18`. Java và native đang đọc cùng backing của direct buffer; không cần `GetByteArrayElements`.

### 4.1. Native thay đổi bytes và Java thấy ngay

Nếu C dùng `memset(base+1, 8, 2)`, sau JNI method return, Java đọc các byte sẽ thấy:

```text
[3, 8, 8, 6]
```

Vẫn là **cùng vùng backing**, không phải JNI tự tạo một `byte[]` chứa kết quả rồi copy ngược.

### 4.2. Địa chỉ chỉ an toàn khi backing còn sống

Direct buffer được Java cấp phát thường do JVM quản lý backing memory. Nếu native **chỉ dùng con trỏ đồng bộ trong một JNI call**, object `jobject buffer` đang được truyền như tham số và JVM bảo đảm reference hợp lệ cho call; đây là mô hình dễ kiểm soát.

Nếu native **lưu pointer để dùng sau khi JNI call return**, cần thêm ownership protocol:

- Giữ **strong global reference** tới direct buffer (`NewGlobalRef`) để không bị GC coi là không còn reachable chỉ vì Java bỏ reference.
- Khi native worker dừng dùng pointer, xóa global ref (`DeleteGlobalRef`).
- Đồng bộ thời điểm hủy owner và thời điểm native ngừng truy cập; **global ref ngăn thu gom Java object, không ngăn một owner khác tự `free` external memory**.

Đừng chỉ cache `void*` rồi để Java `ByteBuffer.allocateDirect` mất mọi strong reference; cleaner/GC có thể giải phóng vùng nhớ.

## 5. Đường đi Native → Java: `malloc` và `NewDirectByteBuffer`

Đối với vùng nhớ do C cấp phát:

```c
uint8_t *data = (uint8_t *)malloc(8);
if (data == NULL) {
    // Xử lý OutOfMemoryError.
    return NULL;
}

for (int i = 0; i < 8; ++i) {
    data[i] = (uint8_t)(10 + i);
}

jobject view = (*env)->NewDirectByteBuffer(
        env, data, (jlong)8);

if (view == NULL) {
    free(data);  // Không để rò bộ nhớ nếu không tạo được view.
    // Giữ pending exception nếu JVM đã tạo.
}
return view;
```

Đây là **trích đoạn** minh họa, nằm trong JNI function có `env` hợp lệ. Sau khi trả `view` về Java, các truy cập `view.get(0)` và `view.put(0,...)` làm việc trực tiếp trên `data` do `malloc` cấp phát.

**Quan trọng:** khi `view` ra khỏi scope Java, **không có bảo đảm `NewDirectByteBuffer` tự gọi `free(data)`**. Bộ nhớ thuộc owner C, vì vậy phải có giao thức release như `nativeRelease(buffer)`, một native handle với `close()`, hoặc callback/native allocator chuyên dụng có quản lý vòng đời.

### 5.1. Vì sao ví dụ cần `AutoCloseable`?

Đối với việc học, một Java wrapper `NativeOwner implements AutoCloseable` cho phép:

```java
try (NativeOwner owner = new NativeOwner(8)) {
    ByteBuffer bytes = owner.buffer();
    // Chỉ dùng bytes trong scope này.
}
// close() yêu cầu native giải phóng vùng backing.
```

Tuy nhiên wrapper đơn giản **không thể tự làm mất hiệu lực** mọi `ByteBuffer.duplicate()`, `slice()` hoặc reference bị giữ ngoài. Nếu Java giữ view lại sau `close()`, view vẫn là object Java nhưng pointer native đã treo: **đọc tiếp là use-after-free**. Production code phải kiểm soát việc view thoát scope, outstanding operations và concurrency; có thể chọn thiết kế chỉ cấp quyền truy cập qua callback ngắn thay vì trả raw buffer cho code bất kỳ.

### 5.2. Đừng dùng memory trên stack để tạo direct buffer dài hạn

Một số C callback có mảng stack cục bộ, ví dụ `char tmp[4096]`. Chỉ được tạo direct buffer trên vùng này nếu Java hoàn tất mọi truy cập **trước khi stack frame kết thúc**, chẳng hạn một callback đồng bộ có hợp đồng nghiêm ngặt. Không trả một `NewDirectByteBuffer` trỏ tới stack array từ native method để Java dùng sau khi method return.

Tương tự, không tạo view dài hạn trỏ tới memory-mapped file đã bị unmap, pointer của library đã free hoặc dữ liệu thuộc arena sẽ bị đóng.

## 6. Ví dụ chạy được: chia sẻ bộ đệm hai chiều với Java 17 + C

Chương trình dưới đây thực hiện hai luồng dữ liệu trong **một Java process**:

- **Native → Java**: `malloc` 8 byte, điền `10..17`, trả direct buffer bằng `NewDirectByteBuffer`. Java sửa bytes, C tính tổng và điền một dải; Java thấy các thay đổi. Một `slice` được đưa lại về JNI, cho thấy địa chỉ và capacity là tương đối với slice.
- **Java → Native**: `ByteBuffer.allocateDirect(4)`, ghi `3,4,5,6`, C tính tổng, ghi lại hai byte, Java đọc kết quả. Trường hợp heap-backed `ByteBuffer.wrap` bị từ chối rõ ràng.

Ví dụ chọn **positive capacity** và **độ dài nhỏ**, kiểm soát `free` bằng `AutoCloseable`. Đây là demo độc lập với FFM và chạy trên **Java 17+** cùng một compiler C. Nó giả định JVM có JNI direct-buffer support; code xử lý trường hợp không hỗ trợ bằng exception.

### 6.1. File Java: `DirectBufferBridge.java`

```java
import java.nio.ByteBuffer;
import java.util.Arrays;

public final class DirectBufferBridge {
    static {
        System.loadLibrary("directbufferbridge");
    }

    // Native cấp phát 8 byte rồi dùng NewDirectByteBuffer.
    private static native ByteBuffer nativeAllocate(int capacity);

    // Chỉ NativeOwner gọi hàm này đúng MỘT LẦN
    // trên buffer gốc được trả từ nativeAllocate.
    private static native void nativeRelease(ByteBuffer original);

    // Kiểm tra direct, offset/length rồi đọc cùng backing.
    private static native int nativeSum(
            ByteBuffer buffer, int offset, int length);

    // Ghi một byte pattern 0..255 vào một dải buffer.
    private static native void nativeFill(
            ByteBuffer buffer, int offset, int length,
            int unsignedValue);

    private DirectBufferBridge() {
    }

    // Wrapper mô tả ownership, không cho dùng sau close
    // thông qua API buffer() của wrapper.
    private static final class NativeOwner implements AutoCloseable {
        private ByteBuffer original;

        NativeOwner(int capacity) {
            original = nativeAllocate(capacity);
            if (original == null) {
                throw new IllegalStateException(
                        "JNI direct buffer unavailable");
            }
        }

        ByteBuffer buffer() {
            if (original == null) {
                throw new IllegalStateException("Native memory closed");
            }
            return original;
        }

        @Override
        public void close() {
            if (original != null) {
                nativeRelease(original);
                original = null;
            }
        }
    }

    // Tạo một snapshot Java của toàn bộ capacity.
    // duplicate + clear chỉ sửa vị trí/limit của view phụ.
    private static int[] snapshot(ByteBuffer buffer) {
        ByteBuffer view = buffer.duplicate();
        view.clear();

        int[] result = new int[view.remaining()];
        for (int i = 0; i < result.length; i++) {
            result[i] = Byte.toUnsignedInt(view.get());
        }
        return result;
    }

    public static void main(String[] args) {
        // Hướng 1: C malloc -> NewDirectByteBuffer -> Java.
        try (NativeOwner owner = new NativeOwner(8)) {
            ByteBuffer data = owner.buffer();

            System.out.println("native-backed direct="
                    + data.isDirect());
            System.out.println("native-backed initial="
                    + Arrays.toString(snapshot(data)));
            System.out.println("native-backed order="
                    + data.order());

            // Java ghi vào cùng native memory.
            data.put(0, (byte) 42);
            System.out.println("sum after Java write="
                    + nativeSum(data, 0, data.capacity()));

            // Native ghi 7 vào byte offsets [2,5).
            nativeFill(data, 2, 3, 7);
            System.out.println("after native fill="
                    + Arrays.toString(snapshot(data)));

            // Slice đại diện vùng gốc [2,5).
            ByteBuffer cursor = data.duplicate();
            cursor.position(2);
            cursor.limit(5);
            ByteBuffer slice = cursor.slice();

            // Native thấy base address/capacity của chính slice.
            nativeFill(slice, 0, slice.capacity(), 9);
            System.out.println("after slice fill="
                    + Arrays.toString(snapshot(data)));
            System.out.println("slice sum="
                    + nativeSum(slice, 0, slice.capacity()));

            // position/limit là state của ByteBuffer,
            // JNI nativeSum ở đây cố ý kiểm tra theo capacity.
            data.position(1);
            data.limit(7);
            System.out.println("full-capacity sum="
                    + nativeSum(data, 0, 8));
            System.out.println("position=" + data.position()
                    + ", limit=" + data.limit());
        }
        // Mọi view đến đây không được phép truy cập nữa:
        // nativeRelease đã free backing memory của chúng.

        // Hướng 2: Java allocateDirect -> C đọc/ghi.
        ByteBuffer javaAllocated = ByteBuffer.allocateDirect(4);
        javaAllocated.put(new byte[]{3, 4, 5, 6});
        javaAllocated.flip();

        System.out.println("java-allocated direct="
                + javaAllocated.isDirect());
        System.out.println("java-allocated sum="
                + nativeSum(javaAllocated, 0,
                        javaAllocated.remaining()));

        nativeFill(javaAllocated, 1, 2, 8);
        System.out.println("java-allocated after native fill="
                + Arrays.toString(snapshot(javaAllocated)));

        // ByteBuffer.wrap là heap-backed, không direct.
        try {
            nativeSum(ByteBuffer.wrap(new byte[]{1, 2}), 0, 2);
            System.out.println("heap buffer rejected=false");
        } catch (IllegalArgumentException expected) {
            System.out.println("heap buffer rejected=true");
        }
    }
}
```

**Lưu ý quan trọng về demo:** `NativeOwner.buffer()` trả raw view cho code **bên trong** `try`. Wrapper này ngăn gọi `buffer()` sau `close` nhưng không thể chặn người dùng cố tình giữ `data` hoặc `slice` rồi truy cập sau `close`. Đó là trách nhiệm sử dụng API trong ví dụ, không phải tính năng Java tự động chống stale pointer.

### 6.2. File C: `DirectBufferBridge.c`

```c
#include <jni.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

// JNI helper: cố gắng ném Java exception theo class name.
static void throw_java(JNIEnv *env,
                       const char *class_name,
                       const char *message) {
    jclass type = (*env)->FindClass(env, class_name);
    if (type != NULL) {
        (*env)->ThrowNew(env, type, message);
        (*env)->DeleteLocalRef(env, type);
    }
}

// Chỉ chấp nhận direct ByteBuffer có address/capacity hợp lệ.
// offset và length được đo theo BYTE.
// Không tự dùng position()/limit() của ByteBuffer.
static int valid_range(JNIEnv *env,
                       jobject buffer,
                       jint offset,
                       jint length,
                       uint8_t **range_start) {
    if (buffer == NULL) {
        throw_java(env, "java/lang/NullPointerException",
                   "buffer is null");
        return 0;
    }

    void *base = (*env)->GetDirectBufferAddress(env, buffer);
    jlong capacity = (*env)->GetDirectBufferCapacity(env, buffer);

    if (base == NULL || capacity < 0) {
        throw_java(env, "java/lang/IllegalArgumentException",
                   "direct ByteBuffer access unavailable");
        return 0;
    }

    // Dùng jlong để tránh overflow của offset + length.
    if (offset < 0 || length < 0
            || (jlong)offset > capacity
            || (jlong)length > capacity - (jlong)offset) {
        throw_java(env, "java/lang/IndexOutOfBoundsException",
                   "invalid buffer range");
        return 0;
    }

    *range_start = (uint8_t *)base + offset;
    return 1;
}

// Java: private static native ByteBuffer nativeAllocate(int);
JNIEXPORT jobject JNICALL
Java_DirectBufferBridge_nativeAllocate(
        JNIEnv *env, jclass ignored, jint capacity) {
    (void)ignored;

    if (capacity <= 0) {
        throw_java(env, "java/lang/IllegalArgumentException",
                   "capacity must be positive");
        return NULL;
    }

    uint8_t *data = (uint8_t *)malloc((size_t)capacity);
    if (data == NULL) {
        throw_java(env, "java/lang/OutOfMemoryError",
                   "native malloc failed");
        return NULL;
    }

    for (jint i = 0; i < capacity; ++i) {
        data[i] = (uint8_t)(10 + (i % 40));
    }

    jobject view = (*env)->NewDirectByteBuffer(
            env, data, (jlong)capacity);

    if (view == NULL) {
        // Không còn Java owner nào để release nếu tạo thất bại.
        free(data);
        if (!(*env)->ExceptionCheck(env)) {
            throw_java(env, "java/lang/IllegalStateException",
                       "JVM direct-buffer access unsupported");
        }
    }
    return view;
}

// Java: private static native void nativeRelease(ByteBuffer);
// CHỈ wrapper owner gọi với view GỐC từ nativeAllocate.
JNIEXPORT void JNICALL
Java_DirectBufferBridge_nativeRelease(
        JNIEnv *env, jclass ignored, jobject original) {
    (void)ignored;

    uint8_t *base = NULL;
    if (!valid_range(env, original, 0, 0, &base)) {
        return;
    }

    // Vùng này do nativeAllocate malloc cấp phát.
    // Caller phải bảo đảm không còn ai truy cập view/slice.
    free(base);
}

// Java: private static native int nativeSum(ByteBuffer,int,int);
JNIEXPORT jint JNICALL
Java_DirectBufferBridge_nativeSum(
        JNIEnv *env, jclass ignored, jobject buffer,
        jint offset, jint length) {
    (void)ignored;

    uint8_t *data = NULL;
    if (!valid_range(env, buffer, offset, length, &data)) {
        return 0; // JVM ném exception nên Java không dùng giá trị 0.
    }

    jlong total = 0;
    for (jint i = 0; i < length; ++i) {
        total += data[i];
    }
    if (total > 2147483647LL) {
        throw_java(env, "java/lang/ArithmeticException",
                   "sum does not fit Java int");
        return 0;
    }
    return (jint)total;
}

// Java: private static native void nativeFill(ByteBuffer,int,int,int);
JNIEXPORT void JNICALL
Java_DirectBufferBridge_nativeFill(
        JNIEnv *env, jclass ignored, jobject buffer,
        jint offset, jint length, jint unsigned_value) {
    (void)ignored;

    if (unsigned_value < 0 || unsigned_value > 255) {
        throw_java(env, "java/lang/IllegalArgumentException",
                   "unsignedValue must be 0..255");
        return;
    }

    uint8_t *data = NULL;
    if (!valid_range(env, buffer, offset, length, &data)) {
        return;
    }

    memset(data, unsigned_value, (size_t)length);
}
```

**Tại sao C code được viết theo cách này?**

1. Mọi hàm JNI native đều nhận `JNIEnv*` và đối số `jclass` vì Java methods là `static native`.
2. `nativeAllocate` tự `malloc`, khởi tạo backing, gọi `NewDirectByteBuffer` rồi **free ngay trên đường thất bại**.
3. `valid_range` kiểm tra `NULL`, khả năng direct access, offset và length trong **capacity**, sử dụng dạng `length > capacity - offset` để tránh phép cộng bị overflow.
4. `nativeSum` đọc `uint8_t` để các giá trị 128..255 được xem là số không dấu; tổng tích lũy `jlong` rồi xác nhận vừa `jint`.
5. `nativeFill` chỉ chấp nhận giá trị 0..255 và dùng `memset` để sửa backing. Bản thân `memset` không tự áp dụng `ByteBuffer.position`/`limit`.
6. `nativeRelease` chỉ hợp lệ khi được truyền **đúng original buffer** do `nativeAllocate` tạo, đúng một lần, và không có hoạt động native/Java nào còn truy cập các view liên quan.
7. `throw_java` tạo Java exception phù hợp thay vì tiếp tục sử dụng pointer không hợp lệ. Nếu `FindClass` thất bại, JNI giữ exception phát sinh; chương trình không âm thầm dereference `NULL`.
8. Các hàm nhận `ByteBuffer` nhưng JNI `jobject` chỉ được Java type system kiểm tra phần nào; vẫn xác thực native address/capacity trước khi truy cập.

**Ranh giới production:** helper `nativeRelease` cố ý tối giản để trình bày cơ chế. Nó **không** kiểm tra một registry native rằng địa chỉ này đã từng được `malloc` bởi module; vì vậy **không được công khai** để code bất kỳ truyền vào direct buffer từ `allocateDirect` hoặc `slice` rồi `free`. Một thư viện production nên dùng opaque native handle/registry, ownership rõ ràng và chống double-free/use-after-free, chứ không chỉ dựa vào kiểu `ByteBuffer`.

### 6.3. Biên dịch Java và sinh JNI header

Đứng trong thư mục chứa hai tệp:

```bash
javac -h . DirectBufferBridge.java
```

Lệnh tạo `DirectBufferBridge.class` và header `DirectBufferBridge.h` chứa prototypes phù hợp. Ví dụ C ở mục 6.2 dùng tên symbol JNI chuẩn cho **class ở default package**; nếu bạn chuyển class vào package như `com.example`, tên JNI symbol sẽ khác. Khi làm project thật, nên đặt package rõ ràng và **dùng header do `javac -h` sinh** để tránh sai tên/chữ ký.

Không cần JDK 22 hoặc FFM để biên dịch mẫu này; dùng **JDK 17+**.

### 6.4. Linux — GCC

Giả sử `JAVA_HOME` chỉ tới thư mục JDK 17+ chứa `include/jni.h` và `include/linux/jni_md.h`:

```bash
javac -h . DirectBufferBridge.java

gcc -std=c11 -O2 -fPIC -shared \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  DirectBufferBridge.c \
  -o libdirectbufferbridge.so

java -Djava.library.path=. DirectBufferBridge
```

JNI shared library được JVM nạp qua `System.loadLibrary("directbufferbridge")`, tương ứng `libdirectbufferbridge.so` trên Linux. C example không cần link `-ljvm` vì đây là JNI library được JVM nạp, không phải native executable dùng Invocation API để tự tạo JVM.

Nếu `JAVA_HOME` chưa được thiết lập, trỏ nó tới **JDK đang được dùng bởi `javac`/`java`** và xác nhận kiến trúc phù hợp. Nếu linker không tìm được dependency của `libdirectbufferbridge.so`, kiểm tra dynamic loader diagnostics, không chỉ `java.library.path`.

### 6.5. macOS — Clang

Với JDK 17+ và Xcode Command Line Tools:

```bash
javac -h . DirectBufferBridge.java

clang -std=c11 -O2 -dynamiclib \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/darwin" \
  DirectBufferBridge.c \
  -o libdirectbufferbridge.dylib

java -Djava.library.path=. DirectBufferBridge
```

`JAVA_HOME` có thể được lấy từ `/usr/libexec/java_home` nếu thích hợp. Dùng JDK/clang và native library cùng kiến trúc (Apple Silicon vs Intel).

### 6.6. Windows — MSVC x64

Mở **x64 Native Tools Command Prompt**, dùng JDK 17+ x64:

```bat
javac -h . DirectBufferBridge.java

cl /nologo /O2 /LD ^
  /I"%JAVA_HOME%\include" ^
  /I"%JAVA_HOME%\include\win32" ^
  DirectBufferBridge.c ^
  /link /OUT:directbufferbridge.dll

java -Djava.library.path=. DirectBufferBridge
```

Lệnh `cl /LD` biên dịch và link thành DLL. Chú ý `JNIEXPORT`/`JNICALL` trong C code giúp export đúng JNI calling convention và symbols; không sửa tên function tùy ý. JVM 64-bit phải nạp DLL 64-bit, JVM 32-bit cần DLL tương ứng.

### 6.7. Stdout chính xác trên đường đi thành công

Với JDK 17+ trên JVM hỗ trợ JNI direct-buffer access, cùng hai file nguồn trên và không có lỗi native load:

```text
native-backed direct=true
native-backed initial=[10, 11, 12, 13, 14, 15, 16, 17]
native-backed order=BIG_ENDIAN
sum after Java write=140
after native fill=[42, 11, 7, 7, 7, 15, 16, 17]
after slice fill=[42, 11, 9, 9, 9, 15, 16, 17]
slice sum=27
full-capacity sum=128
position=1, limit=7
java-allocated direct=true
java-allocated sum=18
java-allocated after native fill=[3, 8, 8, 6]
heap buffer rejected=true
```

**Phép tính xác minh:**

- Native tạo bytes 10,11,...,17 nên Java snapshot ban đầu cho đúng dãy này.
- Java đặt index 0 thành `42`, tổng native đọc là `42+11+12+13+14+15+16+17 = 140`.
- Native điền `7` vào offsets 2,3,4 nên dãy thành `[42,11,7,7,7,15,16,17]`.
- Slice đại diện đúng offsets 2..4, native điền `9` vào ba byte của slice, nên vùng gốc đổi thành `[42,11,9,9,9,15,16,17]`.
- Tổng riêng slice `9+9+9 = 27`.
- Tổng toàn capacity `42+11+9+9+9+15+16+17 = 128`. Việc `position=1` và `limit=7` **không** khiến native `GetDirectBufferCapacity` đổi thành 6 hay áp đặt giới hạn 7.
- Java tạo direct buffer thứ hai với `3,4,5,6`, native tính tổng `18` rồi ghi `8` vào hai byte index 1,2 → Java thấy `[3,8,8,6]`.
- Heap `ByteBuffer.wrap(...)` bị native validation từ chối bằng `IllegalArgumentException`, nên dòng cuối in `true`.

**Byte order không ảnh hưởng các giá trị byte** ở stdout. Với `getInt/getLong`, cần chú ý thứ tự byte như mục 8.

## 7. Vì sao `position`, `limit` và `capacity` không đồng nghĩa?

Java `Buffer` có ba con số:

- **`capacity()`**: lượng phần tử tối đa có thể chứa trong vùng backing.
- **`limit()`**: giới hạn truy cập của các thao tác ByteBuffer tương ứng.
- **`position()`**: vị trí tiếp theo của thao tác đọc/ghi tương đối.

`remaining() = limit() - position()`.

Ví dụ:

```java
ByteBuffer direct = ByteBuffer.allocateDirect(16);
direct.position(4);
direct.limit(12);
```

Kết quả:

```text
capacity = 16
position = 4
limit    = 12
remaining = 8
```

Native gọi `GetDirectBufferAddress(direct)` vẫn lấy địa chỉ bắt đầu **của buffer này**, còn `GetDirectBufferCapacity(direct)` trả **16** (đối với ByteBuffer). JNI **không tự chuyển thành địa chỉ `base+4`, không tự thu hẹp capacity còn 8**, và việc ghi qua raw pointer **không tự cập nhật `position`**.

### 7.1. Muốn native xử lý vùng `remaining()` thì làm thế nào?

**Cách A — Java truyền offset/length rõ ràng:**

```java
int offset = direct.position();
int length = direct.remaining();

int checksum = nativeSum(direct, offset, length);
```

Đây là trích đoạn với các biến và native method tương ứng. Native phải kiểm tra offset/length, không tin dữ liệu gọi truyền vào mù quáng.

**Cách B — Java tạo slice vùng còn lại:**

```java
ByteBuffer slice = direct.slice();
int checksum = nativeSum(slice, 0, slice.capacity());
```

`slice` đại diện đúng dải `position..limit` của buffer nguồn tại **thời điểm tạo**. `GetDirectBufferAddress(slice)` trỏ tới đầu vùng slice, và `GetDirectBufferCapacity(slice)` trả số byte trong slice, không phải capacity của buffer gốc.

**Cách C — native gọi Java NIO methods?** Về kỹ thuật có thể lấy `position`/`limit` bằng JNI method calls, nhưng thêm JNI lookup/method call và phức tạp. Với API cần throughput cao, truyền offset/length rõ ràng hoặc tạo slice ở Java thường đơn giản và kiểm soát được.

### 7.2. `duplicate()` và `slice()` chia sẻ backing nhưng khác cursor

- `duplicate()`: tạo view mới chia sẻ backing, có position/limit/mark độc lập.
- `slice()`: tạo view giới hạn ở vùng `remaining` của buffer tại thời điểm slice.
- Thay đổi bytes qua bất kỳ view nào được quan sát qua các view khác, miễn backing còn sống và không có data race.
- Thay đổi `position/limit` của một view **không tự thay đổi** position/limit của view khác.

Trong ví dụ, `cursor = data.duplicate()` rồi `cursor.position(2); cursor.limit(5); slice = cursor.slice()`. Tạo slice từ cursor tránh đổi trạng thái `data` gốc; native `nativeFill(slice,0,3,9)` đổi bytes offset 2,3,4 của `data`.

### 7.3. Không dùng capacity như quyền truy cập không giới hạn

Về mặt JNI, `GetDirectBufferCapacity` trả capacity. Nhưng nếu Java API chỉ ủy quyền cho native được đọc `remaining`, native phải tuân thủ offset/length được cấp hoặc chỉ nhận slice đã thu hẹp. Thao tác vượt `limit` có thể vẫn nằm trong native capacity, nhưng có thể vi phạm **hợp đồng dữ liệu** của ứng dụng.

## 8. Byte order: tạo direct buffer từ JNI mặc định `BIG_ENDIAN`

Đặc tả JNI nói rõ ByteBuffer trả từ `NewDirectByteBuffer` có byte order **`ByteOrder.BIG_ENDIAN`** lúc tạo. `ByteBuffer.allocateDirect` cũng khởi tạo order là `BIG_ENDIAN` theo Java NIO. Nhưng CPU native có thể là little-endian.

Nếu bạn đặt một C `uint32_t` vào backing memory bằng cách ghi trực tiếp representation native, rồi gọi Java `buffer.getInt(0)` với mặc định BIG_ENDIAN, kết quả có thể đảo thứ tự byte so với giá trị C.

### 8.1. Chọn endianness theo giao thức dữ liệu

Nếu hai bên muốn sử dụng **endianness native của máy**, Java phải chọn:

```java
import java.nio.ByteOrder;

// Trích đoạn trong scope có ByteBuffer buffer hợp lệ.
buffer.order(ByteOrder.nativeOrder());
int number = buffer.getInt(0);
```

Nếu dữ liệu là **file/network protocol big-endian**, có thể giữ `BIG_ENDIAN` thay vì native order. Không tự đổi `order` chỉ vì buffer là direct: **chọn thứ tự byte theo định dạng dữ liệu**, không theo nơi lưu trữ.

Đối với dữ liệu 16/32/64-bit cần xét:

- C `uint32_t`/`int32_t` có kích thước xác định, nhưng C `long`/`size_t` phụ thuộc ABI.
- Alignment và tính hợp lệ của pointer khi C ép `uint8_t*` sang kiểu nhiều byte.
- Java `ByteBuffer.getInt` truy cập theo byte order đã đặt; không có nghĩa raw C pointer sẽ tự endian-swap.
- Nếu dùng `asIntBuffer()`, byte order được lấy từ ByteBuffer khi view được tạo; kiểm tra alignment/capacity theo phần tử.

### 8.2. Quy tắc riêng cho JNI typed direct buffers

JNI `GetDirectBufferCapacity` nói **số phần tử**, không phải số byte tuyệt đối trên mọi Buffer object. Ví dụ `IntBuffer` có capacity 4 thì nghĩa là 4 giá trị `int`; nếu native xử lý như 4 byte, sẽ đọc thiếu dữ liệu. Chỉ dùng một JNI native API nhận `ByteBuffer` khi hợp đồng tính byte. Nếu chấp nhận `IntBuffer`/`ShortBuffer`, phải xác minh kiểu, stride và alignment riêng.

## 9. Quản lý vòng đời: phần quan trọng hơn mẹo “zero-copy”

### 9.1. JNI object reference không sở hữu `malloc`

Một `ByteBuffer` tạo từ `NewDirectByteBuffer` là Java object trỏ tới địa chỉ native; nó **không** mang sẵn quy tắc tự động giải phóng `malloc`. Java GC có thể thu gom object; nhưng điều đó không có nghĩa đúng allocator C đã được gọi `free`.

Ngược lại, gọi `free` khi Java vẫn có reference tới buffer cũng không làm Java object trở thành “null” hoặc tự ngăn `get/put`. Nó trở thành một view nguy hiểm trên địa chỉ đã không còn hợp lệ.

Vì vậy đặt rõ **owner và release protocol**:

```text
nativeAllocate()
   |
   | malloc(backing)
   | NewDirectByteBuffer(backing, n)
   v
Java NativeOwner  ----- owns ------> backing memory
   |
   | Java/JNI dùng các view đồng bộ
   v
stop accepting new uses
   |
   | wait for active JNI operations to finish
   | invalidate views at application level
   v
nativeRelease(original) -> free(backing)
   |
   v
CLOSED: không Java/JNI code nào được đọc/ghi các view cũ
```

Wrapper `NativeOwner` ở mục 6 dùng `try-with-resources` cho quy trình một-thread đơn giản. Không có reference counting hoặc registry cấp phát trong demo; **đó là giới hạn chủ ý của ví dụ**. Trên sản phẩm thật, cần thiết kế sao cho không thể `free` nhầm `allocateDirect` buffer hoặc `slice` và không thể double-free.

### 9.2. Đừng dùng `GetDirectBufferAddress` rồi lưu pointer vô thời hạn

Đối với `ByteBuffer.allocateDirect` do JVM quản lý, lifetime backing liên quan đến reachability của ByteBuffer/cleaner. Nếu C giữ địa chỉ sau khi Java native method return:

1. C cần sở hữu một **global JNI ref** tới buffer, ví dụ `NewGlobalRef`, nếu phải bảo đảm Java object tiếp tục reachable.
2. Có trạng thái đăng ký/dừng/giải đăng ký quyền dùng pointer.
3. Dùng đúng `JNIEnv*` của mỗi native thread có attach vào JVM nếu cần JNI API.
4. Khi native chắc chắn không còn dùng pointer, `DeleteGlobalRef` trên attached thread hợp lệ.
5. Không lưu pointer sau JVM shutdown hoặc sau native owner khác tự giải phóng vùng bộ nhớ.

Một global reference là **strong reference tới Java object**, không phải khóa bảo vệ memory và không thay đồng bộ.

### 9.3. Nếu chia sẻ cho nhiều native/Java threads?

Direct buffer có thể là vùng nhớ chung nhưng không tự bảo đảm:

- Atomicity của đọc/ghi nhiều byte.
- Memory visibility giữa threads.
- Thứ tự thực thi producer/consumer.
- An toàn khi một thread `free` còn thread khác `get/put`.
- Tính thread-safe của `position`/`limit` được chia sẻ giữa nhiều consumers.

Giải pháp là **đồng bộ phù hợp**: locks, handoff queue, memory barriers/atomic operations theo mô hình Java và C, ownership transitions, hoặc phân vùng không trùng nhau. Không dùng `memset`/`GetDirectBufferAddress` như cơ chế publish một record hoàn chỉnh qua threads.

Một design thực tế cho producer-consumer thường có hai vùng/state: backing bytes + tín hiệu “ready” được publish qua cơ chế đồng bộ đúng. Producer viết xong payload rồi publish; consumer nhận tín hiệu xong mới đọc. Nếu native và Java dùng cơ chế atomics liên ngôn ngữ, phải kiểm chứng memory model và ABI của cả hai bên.

### 9.4. Không chỉ trông chờ `finalize`

Một phương án dựa vào `finalize()` để gọi `free` cho vùng do C cấp phát là khó dự đoán và không phù hợp cho tài nguyên native. Ưu tiên `AutoCloseable` và `try-with-resources`, hoặc một cơ chế cleaner/handle được thiết kế bài bản khi cần safety net, nhưng vẫn cần **explicit close** cho các tài nguyên có lifecycle quan trọng.

## 10. Bộ đệm và tệp: liên hệ với `FileChannel`

NIO APIs có thể đọc dữ liệu tệp vào direct `ByteBuffer` rồi đưa thẳng cho JNI xử lý mà không phải tạo `byte[]` trung gian. Ví dụ trích đoạn trong method Java có imports và native method đã khai báo:

```java
try (var channel = java.nio.channels.FileChannel.open(
        java.nio.file.Path.of("payload.bin"),
        java.nio.file.StandardOpenOption.READ)) {

    ByteBuffer direct = ByteBuffer.allocateDirect(64 * 1024);

    int count = channel.read(direct);
    if (count > 0) {
        direct.flip(); // position=0, limit=count

        // C đọc đúng n byte thực tế được FileChannel ghi.
        int sum = nativeSum(direct, direct.position(),
                            direct.remaining());
        System.out.println("sum=" + sum);
    }
}
```

Đây **không phải file chạy độc lập**: cần `payload.bin` tồn tại và `nativeSum` khai báo/được nạp như trong chương trình trước. `FileChannel.read` có thể đọc ít hơn capacity hoặc trả `-1` khi EOF. Do đó không được gọi native đọc cả 64 KiB chỉ vì buffer có capacity 64 KiB; **chỉ xử lý đúng `remaining()` sau `flip()`**.

**Không nên suy ra chỉ vì truyền direct buffer mà luôn zero-copy từ kernel tới Java**. JDK và OS có thể có copy hoặc bước đệm bên trong I/O. Điều ta biết chắc ở lớp JNI là **Java direct buffer và native pointer trỏ tới cùng backing**, tránh một bước chuyển đổi thủ công qua `byte[]`.

### 10.1. MappedByteBuffer và file mapping

`MappedByteBuffer` thường cũng là direct buffer, có thể cho JNI truy cập qua `GetDirectBufferAddress` nếu JVM hỗ trợ. Nhưng mmap có lifetime/unmap semantics riêng; không được cache raw pointer sau khi mapping bị unmap hoặc buffer không còn sở hữu hợp lệ.

Với file mapping, tránh dùng `free` trên địa chỉ mapping. Memory do mmap/OS/JVM quản lý phải được giải phóng bởi đúng cơ chế owner (unmap/cleaner/runtime), không dùng `free` theo thói quen.

## 11. Xử lý lỗi JNI và Java đúng chỗ

### 11.1. Kiểm tra sau `NewDirectByteBuffer`

Nếu `NewDirectByteBuffer` trả `NULL`:

- Nếu có pending exception (ví dụ lỗi cấp phát object), **giữ exception** hoặc xử lý có chủ đích.
- Nếu JVM không hỗ trợ JNI direct buffers và không có exception, nên ném một Java `UnsupportedOperationException`/`IllegalStateException` hay chuyển sang fallback.
- Quan trọng nhất: **giải phóng backing native đã `malloc`** vì Java không nhận được owner để release sau này.

Trong demo, sau `view == NULL`, C gọi `free(data)` rồi mới kiểm tra `ExceptionCheck` và có thể ném `IllegalStateException`.

### 11.2. Kiểm tra `NULL`/`-1` trên đường nhận buffer từ Java

Nếu một native method nhận `ByteBuffer`, đừng mặc nhiên đối số luôn direct. Java có thể truyền `null`, `ByteBuffer.allocate(...)` hoặc `ByteBuffer.wrap(...)`. Kiểm tra:

```c
void *p = (*env)->GetDirectBufferAddress(env, buffer);
jlong cap = (*env)->GetDirectBufferCapacity(env, buffer);

if (p == NULL || cap < 0) {
    // Reject, không dereference p.
}
```

Đoạn này chỉ hợp lệ khi `buffer != NULL`; thiếu bước kiểm tra null có thể vi phạm contract JNI. Ví dụ hoàn chỉnh luôn kiểm tra trước.

**Chú ý:** có tình huống capacity bằng 0 trên một số JVM/version làm address xử lý đặc biệt. Demo dùng capacity dương và coi address NULL là không hỗ trợ/không hợp lệ; nếu sản phẩm cần **zero-length direct buffers**, kiểm thử trên đúng JDK/OS đích và thiết kế đường xử lý riêng.

### 11.3. Bounds và overflow

Cần xác nhận:

```text
0 <= offset
0 <= length
offset <= capacity
length <= capacity - offset
```

Kiểm tra `offset + length <= capacity` bằng số nguyên nhỏ có thể overflow; mẫu `length <= capacity - offset` sau khi xác nhận offset không âm thường an toàn hơn. Sử dụng `jlong` khi nhận `GetDirectBufferCapacity` để tránh ép xuống `jint` quá sớm.

Nếu native method có tham số `int unsignedValue` nhưng dùng `memset`, cần validate 0..255 để giao thức rõ ràng; demo dùng đúng nguyên tắc này.

### 11.4. Không gọi JNI bừa khi đang có pending exception

Các hàm JNI có những quy tắc về việc được phép gọi khi pending exception. Khi `FindClass`/`ThrowNew` thất bại, cần quay về Java hoặc xử lý theo danh mục JNI cho phép, không tiếp tục JNI tùy ý hoặc thao tác pointer đã vô hiệu.

Khi native method trả về cùng pending exception, JVM chuyển exception đó cho Java caller theo cơ chế JNI. Giá trị primitive native return trên đường lỗi không nên được Java dùng; trong demo `nativeSum` trả `0` sau khi đã ném exception, nên Java caller thực tế nhận exception thay vì coi 0 là kết quả thành công.

## 12. Những lỗi thường gặp

| Sai lầm | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Gọi `GetDirectBufferAddress` trên `ByteBuffer.wrap(byte[])` | Trả `NULL`, không có direct backing | Dùng direct `ByteBuffer` hoặc JNI array APIs |
| Tưởng `NewDirectByteBuffer` cũng `malloc` | Dùng địa chỉ chưa hợp lệ | Cấp phát backing native trước |
| Trả ByteBuffer trỏ vào C stack array đã kết thúc | Use-after-return/crash | Dùng heap/native allocation sống đủ lâu |
| Không `free` vùng `malloc` sau khi Java xong | Rò native memory | Owner/AutoCloseable đúng allocator |
| `free` khi Java vẫn giữ/sử dụng `slice` | Use-after-free | Đóng quyền truy cập, chờ active users rồi release |
| Gọi `free` lên địa chỉ của `allocateDirect` Java | Hủy memory không thuộc malloc của bạn | Chỉ giải phóng allocations do chính native owner tạo |
| Native lưu pointer của Java buffer mà không giữ ref | GC có thể giải phóng backing | Quản lý strong global ref và lifecycle |
| Coi `GetDirectBufferCapacity` là `remaining()` | Native xử lý bytes ngoài payload | Truyền offset/length hoặc slice |
| Tưởng `GetDirectBufferAddress` tự dịch theo `position` | Đọc sai byte | Dùng `base + position` có bounds |
| Nhầm `IntBuffer` capacity với số byte | Đọc thiếu/sai dữ liệu | Dùng đúng element size và kiểu buffer |
| Quên xét `BIG_ENDIAN` khi đọc `getInt` | Sai giá trị số nhiều byte | Chọn byte order theo dữ liệu/protocol |
| Bỏ qua `NULL`/`-1` kết quả JNI | Dereference null/crash | Kiểm tra cả address/capacity và exception |
| Dùng `get/put` sau owner đóng arena/`free` | Dangling view | Không để raw buffer thoát scope |
| Đồng thời `nativeFill` và Java `get` thiếu đồng bộ | Race/không có snapshot | Có synchronization/ownership |
| Dùng direct buffer như primitive atomic | Không có bảo đảm về ordering | Locks/atomics/queue phù hợp |
| Tự sửa `position/limit` của buffer từ nhiều threads | Race trên state của Buffer object | Mỗi thread dùng duplicate/slice + sync dữ liệu |
| Dùng `GetByteArrayElements` như bảo đảm zero-copy | JVM có thể copy/pin tùy implementation | Với direct buffer, dùng đúng JNI direct APIs |
| JNI code chạy trên thread khác với `JNIEnv*` ban đầu | Vi phạm thread affinity | Mỗi thread native attach/lấy env riêng |
| Dùng pointer mapping file sau unmap | Memory không hợp lệ | Theo dõi lifetime mapping |
| Mặc định mọi JVM hỗ trợ direct-buffer JNI | Không portable | Xử lý lỗi/cơ chế fallback |

## 13. Đọc/ghi đồng bộ khác với Java memory object ownership

Một tình huống thực tế là `ByteBuffer.allocateDirect` được Java tạo ở một method rồi truyền sang JNI. JNI method lấy pointer và xử lý ngay trước khi return. Đây là trường hợp có ownership đơn giản: Java vẫn giữ local reference tới ByteBuffer trong khi gọi JNI.

Tình huống khác: native driver có một worker thread giữ `void *buffer_addr` và Java code không còn tham chiếu mạnh nào tới buffer. Khi đó dù pointer còn “trông như đúng” trong C, backing có thể được JVM reclaim. Giữ `NewGlobalRef` để root buffer là cần thiết nếu native muốn dùng beyond-call, rồi xử lý unregister/free ref rõ ràng.

Ngược lại, khi backing native do `malloc` tạo và Java `ByteBuffer` tồn tại nhiều ngày, native owner có thể quên `free`. Java reference không quyết định native memory tự được dọn theo `malloc`. Kể cả nếu Java GC object, backing vẫn là trách nhiệm C allocator trừ khi bạn thiết kế hook cleanup có kiểm soát.

**Tóm lại, có hai quy tắc khác nhau:**

- **Java-owned direct memory**: giữ Java buffer reachable khi native còn dùng pointer.
- **Native-owned memory**: giữ native allocation hợp lệ khi Java còn dùng ByteBuffer; giải phóng đúng một lần sau khi tất cả người dùng đã dừng.

Đừng chỉ theo dõi một phía của ranh giới JNI.

## 14. Khi nào nên dùng direct buffer và khi nào không?

**Nên cân nhắc direct buffer khi:**

- Payload lớn hoặc tái sử dụng nhiều lần, nhiều bước xử lý native.
- Giao diện native/I/O API thực sự cần `void*` trỏ tới vùng liên tục.
- Có thể thiết kế owner và lifecycle rõ ràng.
- Benchmark cho thấy tránh copy qua JNI cải thiện throughput/latency.
- Dữ liệu được chia thành các vùng mà Java và native có thể sở hữu luân phiên.

**Nên cân nhắc `byte[]`/`GetByteArrayRegion` khi:**

- Dữ liệu nhỏ, không cần giữ native pointer.
- Việc quản lý native lifecycle quá phức tạp so với lượng data.
- Chỉ cần copy một lần vào Java heap và xử lý chủ yếu bằng Java.
- Cần bảo đảm portability tới JVM không hỗ trợ JNI direct-buffer access.
- API bên trên vốn nhận `byte[]`, nên direct buffer có thể khiến phải copy lại.

**Không coi zero-copy là lời hứa end-to-end:** dùng direct buffer giúp chia sẻ backing giữa Java và JNI, nhưng I/O phía trước/sau (file, mạng, codec, driver, thiết bị) vẫn có thể tạo copy. Dùng profiler/benchmark thay vì suy đoán.

## 15. Bài tập mở rộng

### Bài tập 1 — Offset và limit

Trong `DirectBufferBridge.java`, tạo `ByteBuffer.allocateDirect(16)`, đặt `position(4)` và `limit(12)`. So sánh `nativeSum(buffer,4,8)` với `nativeSum(buffer.slice(),0,8)` khi bytes đã được khởi tạo. Kiểm tra cả hai đọc cùng 8 bytes, và `GetDirectBufferCapacity(buffer)` ở C vẫn là 16.

### Bài tập 2 — Bộ đệm Java và bộ đệm native

Tạo hai buffer 8 byte: một bằng `allocateDirect`, một bằng `nativeAllocate`. Thay đổi byte index 3 qua Java rồi để JNI đọc. Quan sát Java API giống nhau nhưng **quy tắc release khác nhau**: Java-owned direct backing không được gửi cho `nativeRelease`, native-owned phải được free theo owner.

### Bài tập 3 — Byte order

Cho native ghi 4 byte `01 02 03 04` vào direct buffer. In `getInt(0)` khi order là `BIG_ENDIAN` rồi `LITTLE_ENDIAN`, giải thích hai kết quả `0x01020304` và `0x04030201`. Không ép kiểu con trỏ sai alignment chỉ để thuận tiện.

### Bài tập 4 — Bắt lỗi trên heap buffer

Truyền `ByteBuffer.wrap(new byte[]{1,2,3})` vào `nativeSum`. Kiểm tra native nhận `GetDirectBufferAddress == NULL` và Java catch `IllegalArgumentException` theo validation. Không tự thay sang `GetByteArrayElements` nếu chưa có fallback được thiết kế.

### Bài tập 5 — Native fill ngoài phạm vi

Gọi `nativeFill(direct, 7, 2, 9)` khi capacity chỉ 8. C phải ném `IndexOutOfBoundsException` thay vì ghi ra ngoài vùng byte. Thử `unsignedValue=300` và kiểm tra `IllegalArgumentException`.

### Bài tập 6 — API release an toàn hơn

Mở rộng bài bằng registry native ánh xạ một **opaque handle** tới pointer/size/state. Java owner nắm handle và Buffer; `close` ghi trạng thái CLOSED và chỉ gọi release một lần khi không có outstanding access. Native `free` chỉ pointer được registry xác nhận đang ALLOCATED. Không tin một `ByteBuffer` bất kỳ được caller truyền vào `free`.

### Bài tập 7 — FileChannel đọc từng chunk

Mở một tệp nhị phân, đọc từng chunk vào `ByteBuffer.allocateDirect`, `flip` và gọi JNI xử lý đúng `remaining`. Sau mỗi chunk, `clear` trên buffer để tái sử dụng. Không đọc native quá `limit` hoặc vượt capacity.

## 16. Checklist khi triển khai thực tế

1. Xác định data owner: **Java `allocateDirect`** hay **native `malloc`/allocator**.
2. Với native → Java, bảo đảm `address != NULL`, `capacity > 0` và không vượt `Integer.MAX_VALUE`, backing còn sống.
3. Với Java → native, kiểm tra `GetDirectBufferAddress != NULL` và `GetDirectBufferCapacity >= 0` trước khi dùng.
4. Chỉ xử lý `ByteBuffer` theo đơn vị **byte**; nếu typed buffer, tính lại số phần tử/stride.
5. Với offset/length, kiểm tra bounds và tránh overflow; không dùng `capacity` thay cho `remaining` nếu dữ liệu chỉ có tới limit.
6. Biết `GetDirectBufferAddress` trỏ tới đầu **buffer object/view**, không tự cộng `position`; `slice` là một view có base riêng.
7. Chọn `ByteOrder` đúng giao thức; `NewDirectByteBuffer` bắt đầu `BIG_ENDIAN`.
8. Với backing native, đặt owner release rõ ràng, ngăn double-free và tuyệt đối không dùng view sau khi free.
9. Với Java-owned direct backing dùng beyond-call, giữ strong/global reference phù hợp và xóa khi dừng.
10. Kiểm soát **concurrent access**, memory visibility, read/write ownership và shutdown trước khi giải phóng.
11. Không dùng `GetDirectBufferAddress` trên heap-backed `ByteBuffer.wrap`; thiết kế fallback JNI arrays nếu cần.
12. Xử lý JNI support không có, allocation failures và pending Java exceptions.
13. Kiểm thử trên đúng OS/ABI/JDK/native compiler; dùng `javac -h` để sinh header tránh sai JNI symbol.
14. Benchmark dữ liệu thực trước khi kết luận direct buffer tốt hơn mọi lựa chọn khác.

## Tài liệu tham khảo chính thức

- [Oracle Java 17 — JNI Specification, NIO Support](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/functions.html#nio-support): `NewDirectByteBuffer`, `GetDirectBufferAddress`, `GetDirectBufferCapacity`, hợp đồng NULL/-1 và byte order.
- [Oracle Java 17 — `ByteBuffer`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html): `allocateDirect`, `wrap`, `slice`, `duplicate`, `order`, absolute/relative reads/writes.
- [Oracle Java 17 — `Buffer`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/Buffer.html): `capacity`, `position`, `limit` và `remaining`.
- [Oracle Java 17 — `ByteOrder`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteOrder.html): BIG_ENDIAN/LITTLE_ENDIAN/nativeOrder.
- [Oracle Java 17 — `FileChannel`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/FileChannel.html): đọc/ghi dữ liệu vào `ByteBuffer`.
- [Oracle Java 17 — JNI Design Overview](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/design.html): quy tắc đặt JNI native methods và JNI library.
- [Android NDK — JNI Tips](https://developer.android.com/ndk/guides/jni-tips): so sánh sử dụng direct buffer với byte arrays và các chi phí truy cập native/managed.