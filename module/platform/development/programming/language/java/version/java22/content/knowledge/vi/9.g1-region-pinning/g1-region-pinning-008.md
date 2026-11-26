# Thiết kế JNI critical section ngắn và giải phóng tài nguyên đúng thời điểm

JNI critical section là khoảng thời gian native code giữ con trỏ tới dữ liệu nằm trong heap Java sau khi gọi `GetPrimitiveArrayCritical` hoặc `GetStringCritical`, và kết thúc khi gọi hàm `Release` tương ứng. Thiết kế đúng cần chuẩn bị mọi thao tác có thể gọi JNI hoặc chờ đợi trước khi lấy con trỏ, chỉ làm một lượng công việc CPU ngắn trong critical section, rồi giải phóng con trỏ ngay sau đó.

JDK 22 đưa JEP 423, *Region Pinning for G1*, vào G1 để garbage collection có thể tiếp tục hoạt động trong khi native code đang giữ một số đối tượng. Đây là thay đổi triển khai của G1, không phải API preview hay một API JNI mới. Các hàm JNI critical đã là API chính thức từ JNI 1.2 và vẫn có trong JNI Specification của JDK 27. Tính đến ngày 25/11/2026, JDK 27 là feature release mới nhất và JDK 25 là LTS mới nhất.

## 1. Vì sao phải giới hạn thời gian của critical section?

Khi native code cần truy cập phần tử của một primitive array hoặc nội dung của một Java `String`, JNI có thể trả về con trỏ trực tiếp tới dữ liệu hoặc một bản sao do VM tạo ra. Nếu trả về con trỏ trực tiếp, VM phải bảo đảm địa chỉ đó không bị thay đổi trong lúc native code sử dụng. Với garbage collector di chuyển đối tượng, điều này có thể yêu cầu giữ đối tượng hoặc vùng heap chứa đối tượng ở nguyên vị trí.

Trước khi có G1 region pinning, critical section có thể khiến G1 phải trì hoãn garbage collection để bảo đảm con trỏ native còn hợp lệ. JEP 423 thay đổi cách G1 xử lý: G1 có thể pin vùng chứa đối tượng đang được native code sử dụng và tiếp tục thu gom các vùng khác. Nhờ vậy, một JNI critical section không còn đồng nghĩa với việc phải dừng toàn bộ hoạt động garbage collection của G1.

Tuy nhiên, pinning vẫn có chi phí. Nếu một region có đối tượng bị pin, G1 không thể di chuyển đối tượng đó trong lần evacuation tương ứng. Region có thể gặp `Evacuation Failure: Pinned`, tạm thời không dùng được cho allocation và được đưa vào danh sách để thử evacuation lại ở các lần GC sau. Vì vậy, G1 region pinning giảm ảnh hưởng trên toàn heap nhưng không làm cho critical section dài trở nên miễn phí.

## 2. Các cặp JNI critical API

Hai cặp API thường gặp là:

| API lấy con trỏ | API giải phóng | Dữ liệu |
| --- | --- | --- |
| `GetPrimitiveArrayCritical` | `ReleasePrimitiveArrayCritical` | Phần tử của primitive array như `byte[]`, `int[]`, `float[]`. |
| `GetStringCritical` | `ReleaseStringCritical` | Ký tự UTF-16 của Java `String`, kiểu `jchar`. |

Ví dụ chữ ký của cặp array:

```c
void *GetPrimitiveArrayCritical(
    JNIEnv *env,
    jarray array,
    jboolean *isCopy
);

void ReleasePrimitiveArrayCritical(
    JNIEnv *env,
    jarray array,
    void *carray,
    jint mode
);
```

`GetPrimitiveArrayCritical` có thể trả về địa chỉ dữ liệu gốc hoặc một bản sao. Nếu cần biết VM đã tạo bản sao hay chưa, truyền địa chỉ một biến `jboolean` vào `isCopy`; nếu không cần thông tin này, có thể truyền `NULL`. Không được giả định rằng hàm luôn trả về con trỏ trực tiếp.

Nếu hàm trả về `NULL`, thao tác lấy con trỏ thất bại. JNI có thể đã đặt một exception như `OutOfMemoryError`; native method nên trả về ngay để exception đang chờ được chuyển về Java. Không gọi hàm `Release` khi chưa lấy được con trỏ.

`GetStringCritical` trả về `const jchar *`, vì nội dung Java `String` là immutable. Con trỏ này không phải chuỗi C kết thúc bằng ký tự NUL; hãy dùng độ dài lấy trước bằng `GetStringLength` và không gọi `strlen` trên nó.

## 3. Những quy tắc bắt buộc trong critical section

JNI Specification yêu cầu native code không chạy quá lâu giữa cặp `Get` và `Release`. Trong khoảng này:

- Không gọi các JNI function khác. Hàm `Release` tương ứng là thao tác kết thúc critical section.
- Không thực hiện system call có thể làm thread hiện tại block và chờ một Java thread khác.
- Không giữ con trỏ sau khi đã gọi `Release`.
- Không để con trỏ thoát sang thread khác, callback bất đồng bộ hoặc cấu trúc global để sử dụng sau này.
- Không thực hiện công việc có thời gian không xác định như I/O, chờ lock, chờ condition variable hoặc chờ network response.

Trong thực tế, hãy giữ phần code giữa hai lời gọi ở mức tối thiểu: một vòng lặp CPU-bound có giới hạn, `memcpy` với kích thước đã biết hoặc một phép tính đơn giản. Nên tránh cả cấp phát bộ nhớ, logging và các thao tác có thể tranh chấp lock trong khoảng này, dù chúng không phải lúc nào cũng là system call bị cấm trực tiếp.

Hãy thực hiện trước khi acquire những việc như kiểm tra đầu vào, lấy độ dài array/string, tính kích thước buffer, cấp phát buffer native và tra cứu metadata cần thiết. Nếu cần kiểm tra lỗi hoặc tạo Java exception, hãy làm sau khi release.

## 4. Ví dụ: tính checksum của `byte[]`

Giả sử ứng dụng có native method tính tổng không dấu của các byte trong một mảng. Java kiểm tra đầu vào trước khi gọi native code:

```java
package demo;

import java.util.Objects;

public final class ImageOps {
    static {
        System.loadLibrary("imageops");
    }

    private ImageOps() { }

    public static long checksum(byte[] data) {
        Objects.requireNonNull(data, "data");
        return checksum0(data);
    }

    private static native long checksum0(byte[] data);
}
```

Phần C lấy độ dài trước khi vào critical section, lấy con trỏ, tính toán nhanh rồi release:

```c
#include <jni.h>

JNIEXPORT jlong JNICALL
Java_demo_ImageOps_checksum0(JNIEnv *env, jclass clazz, jbyteArray data) {
    (void) clazz;

    // Chuẩn bị trước critical section.
    const jsize length = (*env)->GetArrayLength(env, data);

    // Bắt đầu critical section.
    jbyte *elements = (jbyte *) (*env)->GetPrimitiveArrayCritical(
            env, data, NULL);

    if (elements == NULL) {
        // Có thể đang có OutOfMemoryError; để exception được trả về Java.
        return 0;
    }

    // Chỉ thực hiện công việc CPU-bound, có giới hạn.
    jlong sum = 0;
    for (jsize i = 0; i < length; i++) {
        sum += (unsigned char) elements[i];
    }

    // Chỉ đọc dữ liệu nên không cần copy dữ liệu trở lại Java array.
    (*env)->ReleasePrimitiveArrayCritical(
            env, data, elements, JNI_ABORT);

    // Critical section đã kết thúc; từ đây có thể gọi JNI nếu cần.
    return sum;
}
```

Trình tự của ví dụ:

1. `GetArrayLength` chạy trước khi lấy con trỏ, nên không vi phạm quy tắc cấm gọi JNI khác trong critical section.
2. `GetPrimitiveArrayCritical` bắt đầu critical section. Nếu kết quả là `NULL`, hàm trả về ngay; không có con trỏ cần release.
3. Vòng lặp chỉ đọc byte và cộng vào biến native cục bộ. Không có JNI call, cấp phát, I/O hoặc chờ thread khác.
4. `ReleasePrimitiveArrayCritical` kết thúc critical section. Sau lời gọi này, `elements` không còn được sử dụng.
5. Hàm trả kết quả về Java.

Java `byte` có dấu, nên ví dụ ép từng phần tử sang `unsigned char` trước khi cộng. Nếu muốn checksum theo quy tắc khác, hãy thay phép chuyển đổi tương ứng.

## 5. Chọn release mode đúng với mục đích truy cập

`ReleasePrimitiveArrayCritical` nhận một `mode`. Khi VM trả về bản sao, mode quyết định có copy dữ liệu trở lại Java array hay không và có giải phóng buffer copy hay không. Nếu VM trả về địa chỉ trực tiếp, mode bị bỏ qua.

| Mode | Nếu `Get` trả về bản sao | Trường hợp sử dụng |
| --- | --- | --- |
| `0` | Copy nội dung trở lại Java array rồi giải phóng bản sao. | Đã sửa dữ liệu và muốn cập nhật Java array; cũng là lựa chọn đơn giản cho thao tác có thể sửa. |
| `JNI_ABORT` | Giải phóng bản sao mà không copy thay đổi trở lại. | Chỉ đọc dữ liệu hoặc muốn bỏ các thay đổi trên bản sao. |
| `JNI_COMMIT` | Copy dữ liệu trở lại nhưng chưa giải phóng bản sao. | Chỉ dùng khi thật sự cần commit nhiều giai đoạn; vẫn phải gọi `Release` lần cuối để giải phóng bản sao. |

Trong ví dụ checksum, `JNI_ABORT` phù hợp vì code chỉ đọc. Nếu native code sửa các phần tử và muốn Java nhìn thấy thay đổi, dùng mode `0`:

```c
// Sau khi sửa elements trong critical section:
(*env)->ReleasePrimitiveArrayCritical(env, data, elements, 0);
```

Không dùng `JNI_COMMIT` như một lời gọi release cuối cùng nếu VM đã tạo bản sao. Với bản sao, `JNI_COMMIT` chỉ copy nội dung trở lại nhưng giữ buffer; cần một lần gọi `ReleasePrimitiveArrayCritical` nữa với `0` hoặc `JNI_ABORT` để giải phóng buffer. Trong đa số trường hợp, `0` hoặc `JNI_ABORT` rõ ràng và ít lỗi hơn.

`JNI_ABORT` không phải thao tác rollback cho dữ liệu gốc. Nếu VM trả về con trỏ trực tiếp (`isCopy == JNI_FALSE`), thay đổi native code đã ghi vào Java array; mode bị bỏ qua và không thể hoàn tác các thay đổi đó bằng `JNI_ABORT`. Chỉ dựa vào `JNI_ABORT` để bỏ thay đổi khi biết VM đã trả về bản sao.

## 6. Thiết kế cleanup cho mọi đường đi

Một native method có nhiều nhánh xử lý phải bảo đảm mọi đường đi sau khi acquire đều đi qua đúng một lần release. Nếu cần báo lỗi trong lúc xử lý, lưu trạng thái lỗi vào biến native, release trước rồi mới gọi JNI để tạo exception.

Ví dụ về cấu trúc cleanup trong C:

```c
const jsize length = (*env)->GetArrayLength(env, data);

// Kiểm tra mọi điều kiện có thể báo lỗi trước khi acquire.
if (length > MAX_SUPPORTED_LENGTH) {
    jclass exceptionClass = (*env)->FindClass(
            env, "java/lang/IllegalArgumentException");
    if (exceptionClass != NULL) {
        (*env)->ThrowNew(env, exceptionClass, "Input is too large");
    }
    return 0;
}

jbyte *elements = (jbyte *) (*env)->GetPrimitiveArrayCritical(
        env, data, NULL);
if (elements == NULL) {
    return 0;
}

jlong result = 0;
jboolean failed = JNI_FALSE;

// Critical section: không gọi JNI và không block.
if (!calculate_bounded_value(elements, length, &result)) {
    failed = JNI_TRUE;
}

(*env)->ReleasePrimitiveArrayCritical(env, data, elements, JNI_ABORT);
elements = NULL; // Không dùng lại con trỏ sau release.

// Đã ra khỏi critical section; có thể tạo exception.
if (failed) {
    jclass exceptionClass = (*env)->FindClass(
            env, "java/lang/IllegalArgumentException");
    if (exceptionClass != NULL) {
        (*env)->ThrowNew(env, exceptionClass, "Input is too large");
    }
    return 0;
}

return result;
```

`calculate_bounded_value` trong ví dụ chỉ đại diện cho một phép tính native đã được giới hạn thời gian. Nó không được gọi JNI, chờ I/O hoặc giữ con trỏ sau khi trở về. Nếu hàm tính toán có thể thất bại, hãy trả mã trạng thái hoặc ghi lỗi vào biến native rồi thực hiện cleanup trước khi chuyển lỗi thành Java exception.

Với C++, có thể dùng một scope guard có destructor gọi đúng hàm `Release` để giảm nguy cơ quên release khi có nhiều nhánh. Destructor chỉ nên thực hiện thao tác release tương ứng; không để exception C++ thoát qua biên JNI. Với C thuần, một cleanup label duy nhất cũng giúp tránh các nhánh `return` bỏ qua release.

## 7. `GetStringCritical` cũng cần cùng kỷ luật

Đối với Java `String`, lấy độ dài trước rồi mới lấy con trỏ ký tự:

```c
const jsize length = (*env)->GetStringLength(env, text);
const jchar *chars = (*env)->GetStringCritical(env, text, NULL);

if (chars == NULL) {
    return 0; // Giữ nguyên exception nếu VM đã đặt exception.
}

// Chỉ đọc tối đa length phần tử jchar; không gọi JNI hoặc block.
jlong checksum = 0;
for (jsize i = 0; i < length; i++) {
    checksum += chars[i];
}

(*env)->ReleaseStringCritical(env, text, chars);
return checksum;
```

`jchar` biểu diễn một UTF-16 code unit, không phải UTF-8 byte và cũng không nhất thiết tương ứng một Unicode code point. Nếu cần xử lý code point, hãy tính toán đúng cặp surrogate sau khi đã lấy dữ liệu. Không dùng `strlen` hoặc giả định có ký tự NUL kết thúc vùng ký tự.

Nếu chỉ cần sao chép nội dung chuỗi để xử lý lâu hơn, hãy cân nhắc `GetStringChars`/`ReleaseStringChars` hoặc API sao chép phù hợp. Dù chọn API nào, vẫn phải release theo đúng cặp đã acquire.

## 8. G1 region pinning trong JDK hiện đại

JEP 423 được tích hợp trong JDK 22 để G1 có thể tiếp tục garbage collection trong lúc JNI critical section giữ tham chiếu tới Java object. G1 pin vùng chứa đối tượng cần được native code truy cập; các vùng khác vẫn có thể được xử lý trong cùng chu kỳ GC.

Điều này không biến pinning thành một cơ chế giữ nguyên toàn bộ heap và cũng không loại bỏ mọi evacuation failure. Trong JDK 27, tài liệu G1 vẫn mô tả trường hợp `Pinned`:

- `Pinned`: G1 không thể di chuyển một đối tượng đang được giữ cố định để native code sử dụng, ví dụ qua `GetPrimitiveArrayCritical`.
- Nếu G1 không thể di chuyển tất cả đối tượng ra khỏi một region, region đó tạm thời không được dùng cho allocation.
- G1 đưa region gặp evacuation failure thành candidate để thử evacuation trong các lần GC kế tiếp.
- Nếu GC không thu hồi được đủ bộ nhớ, G1 vẫn có thể phải chạy Full GC; pinning không bảo đảm ứng dụng tránh được Full GC.

G1 là garbage collector mặc định trong JDK 27. JEP 423 là thay đổi nội bộ của G1, không có cờ JNI riêng để bật critical section và cũng không thay đổi hợp đồng lập trình JNI. Khi dùng collector khác, không nên suy luận rằng collector đó có hành vi region pinning giống G1.

## 9. Chẩn đoán và quan sát

Trong môi trường kiểm thử, có thể dùng các tùy chọn hiện đại sau:

```bash
java -Xcheck:jni -Xlog:gc -jar application.jar
```

- `-Xcheck:jni` giúp phát hiện nhiều lỗi sử dụng JNI. Nếu native code gọi JNI function khác trong phạm vi `Get/ReleasePrimitiveArrayCritical` hoặc `Get/ReleaseStringCritical`, HotSpot có thể in cảnh báo.
- `-Xlog:gc` hiển thị thông tin GC. Khi G1 gặp evacuation failure do đối tượng bị pin, log có thể chứa `Evacuation Failure: Pinned`.
- Đối chiếu thời gian critical section trong native code với GC log và latency của request để xác định native call nào giữ con trỏ quá lâu.

Không nên chỉ nhìn một dòng `Pinned` rồi kết luận ứng dụng có lỗi JNI. Đây là dấu hiệu G1 đã gặp đối tượng không thể di chuyển trong lần evacuation đó. Hãy tìm native call tương ứng, đo thời gian acquire-to-release và kiểm tra mọi đường đi có release đầy đủ.

## 10. Khi nào không nên dùng critical API?

Critical API phù hợp khi native code cần truy cập nhanh vào primitive array hoặc string và có thể hoàn tất thao tác trong một khoảng rất ngắn, xác định được. Nếu công việc cần I/O, chờ lock, gọi thư viện có thể block hoặc chạy thuật toán lâu, hãy chọn cách khác:

- Dùng `GetByteArrayRegion`, `GetIntArrayRegion` hoặc hàm `Get<Type>ArrayRegion` tương ứng để sao chép phần dữ liệu cần thiết sang native buffer, sau đó xử lý ngoài critical section.
- Dùng `Set<Type>ArrayRegion` để ghi một vùng dữ liệu trở lại Java array sau khi xử lý xong trong native memory.
- Nếu ứng dụng kiểm soát thiết kế bộ nhớ native, cân nhắc `ByteBuffer` direct hoặc Foreign Function & Memory API để quản lý vùng nhớ native theo vòng đời rõ ràng. FFM là API chính thức từ Java 22; đây là lựa chọn kiến trúc khác, không phải cách thay thế trực tiếp để lấy con trỏ vào Java heap array.

Không nên chuyển sang `Get<Type>ArrayElements` chỉ để né các giới hạn critical section mà không xem xét vòng đời pointer và chi phí copy/pinning. Cặp `Get`/`Release` thông thường cũng phải được giải phóng đúng cách; hãy chọn API theo yêu cầu truy cập và thời gian xử lý.

## Ghi nhớ

- `GetPrimitiveArrayCritical`/`ReleasePrimitiveArrayCritical` và `GetStringCritical`/`ReleaseStringCritical` là JNI API ổn định từ JNI 1.2, không phải API preview của Java 22.
- Critical section phải ngắn. Không gọi JNI function khác, không chờ I/O/lock hoặc system call có thể block chờ Java thread.
- Lấy độ dài, kiểm tra đầu vào, cấp phát buffer và chuẩn bị trạng thái trước khi acquire con trỏ.
- Kiểm tra `NULL` sau `Get`; mỗi lần acquire thành công phải có đúng một lần release tương ứng trên mọi đường đi.
- `0` copy thay đổi về Java array và giải phóng bản sao; `JNI_ABORT` bỏ thay đổi trên bản sao; `JNI_COMMIT` copy nhưng chưa giải phóng bản sao.
- Không dùng pointer sau release và không chuyển pointer sang thread khác.
- JEP 423 đưa region pinning vào G1 từ JDK 22. JDK 27 vẫn ghi nhận `Evacuation Failure: Pinned`; pinning không làm critical section dài trở nên miễn phí.
- Dùng `-Xcheck:jni` và `-Xlog:gc` để hỗ trợ chẩn đoán trong kiểm thử và vận hành.

## Tài liệu tham khảo

- [JEP 423: Region Pinning for G1](https://openjdk.org/jeps/423)
- [Oracle JDK 22 Release Notes — Region Pinning for G1](https://www.oracle.com/java/technologies/javase/22all-relnotes.html)
- [Java Native Interface Specification, JDK 27 — JNI Functions](https://docs.oracle.com/en/java/javase/27/docs/specs/jni/functions.html)
- [Java SE 27 — Garbage-First (G1) Garbage Collector](https://docs.oracle.com/en/java/javase/27/gctuning/garbage-first-g1-garbage-collector.html)
- [Java SE 27 — Garbage-First Garbage Collector Tuning](https://docs.oracle.com/en/java/javase/27/gctuning/garbage-first-garbage-collector-tuning.html)
