# Cách G1 giữ nguyên vùng bị ghim trong khi vẫn thu gom các vùng khác

## Mục tiêu

Sau bài học này, bạn có thể:

- Giải thích vì sao JNI critical region cần giữ địa chỉ của một số đối tượng Java ổn định.
- Mô tả cách G1 pin vùng chứa đối tượng được native code truy cập và tiếp tục thu gom các vùng khác.
- Nhận biết giới hạn của region pinning và cách quan sát evacuation failure trong GC log.

## Trạng thái của tính năng trên JDK hiện đại

JEP 423, *Region Pinning for G1*, được tích hợp trong JDK 22. Đây là thay đổi bên trong bộ thu gom rác G1, giúp GC tiếp tục hoạt động khi native code đang ở trong JNI critical region. Tính năng vẫn được tài liệu Garbage-First GC của Java SE 27 mô tả; G1 cũng tiếp tục là garbage collector mặc định của JDK 27.

Region pinning không phải API Java mới, không phải preview hay incubator, và không cần bật bằng một cờ JVM riêng. Ứng dụng hưởng lợi tự động khi chạy bằng HotSpot với G1 và sử dụng các JNI critical function phù hợp. Đây là cơ chế triển khai của G1, không phải bảo đảm chung cho mọi garbage collector.

## Vì sao JNI cần pin đối tượng?

G1 chia Java heap thành nhiều vùng (*region*) có kích thước bằng nhau. Khi thu gom một tập hợp vùng, G1 thường di chuyển các đối tượng còn sống sang vùng đích. Việc di chuyển giúp gom phần dữ liệu còn sống lại với nhau và giải phóng vùng nguồn để tái sử dụng.

Native code đôi khi cần truy cập trực tiếp dữ liệu của một Java primitive array hoặc chuỗi trong một khoảng thời gian ngắn. JNI cung cấp các cặp hàm như:

- `GetPrimitiveArrayCritical()` và `ReleasePrimitiveArrayCritical()` để truy cập phần tử của primitive array.
- `GetStringCritical()` và `ReleaseStringCritical()` để truy cập dữ liệu chuỗi.

Khi native code nhận một con trỏ đến dữ liệu Java, địa chỉ đó phải còn hợp lệ cho đến khi gọi hàm release tương ứng. Nếu GC di chuyển đối tượng trong thời gian này, con trỏ native có thể trỏ đến địa chỉ cũ và không còn an toàn. Vì vậy, GC phải bảo vệ đối tượng đang được native code truy cập khỏi việc di chuyển.

Trước JEP 423, G1 có thể phải trì hoãn việc thu gom khi JNI critical region đang hoạt động. Nếu critical region kéo dài hoặc xuất hiện thường xuyên, việc chờ này có thể làm GC bị chậm lại và tăng áp lực bộ nhớ.

## Cơ chế region pinning của G1

JEP 423 thay đổi cách G1 xử lý tình huống trên. Khi native code lấy con trỏ đến dữ liệu Java bằng JNI critical function, G1 ghi nhận vùng heap chứa đối tượng đó là vùng đang bị ghim (*pinned region*). Đối tượng cần giữ địa chỉ được bảo toàn trong suốt thời gian native code giữ con trỏ.

Trong khi vùng có đối tượng bị ghim chưa thể được giải phóng hoàn toàn, G1 vẫn có thể thực hiện chu kỳ thu gom trên những vùng khác. GC không phải trì hoãn một chu kỳ chỉ vì một thread đang ở trong JNI critical region. Những đối tượng khác trong vùng bị ghim vẫn có thể được xử lý khi an toàn; đối tượng mà native code đang tham chiếu phải giữ nguyên địa chỉ.

Region pinning không loại bỏ các stop-the-world pause vốn có của G1. Thay đổi ở đây là G1 có thể thực hiện công việc thu gom cần thiết dù JNI critical region vẫn đang tồn tại, vì đối tượng được native code sử dụng đã được bảo vệ khỏi việc di chuyển.

Khi native code gọi hàm `Release...Critical()` tương ứng, thời gian cần giữ con trỏ kết thúc. G1 có thể xem xét vùng đó trong các lần thu gom tiếp theo. Việc release không có nghĩa vùng sẽ được thu hồi ngay lập tức; quyết định thu gom vẫn phụ thuộc vào chu kỳ và chính sách của G1.

Có thể hình dung quá trình như sau:

```text
Java thread                         G1
     |                               |
     | GetPrimitiveArrayCritical()   |
     |------------------------------>|
     |                         Ghi nhận region bị pin
     |                               |
     | Native code đọc/ghi dữ liệu   | GC vẫn thu gom các region khác
     |                               | Đối tượng pinned giữ nguyên địa chỉ
     |                               |
     | ReleasePrimitiveArrayCritical()|
     |------------------------------>|
     |                         Kết thúc thời gian pin
     |                               | Có thể thu hồi region ở GC sau
```

Điểm cốt lõi là G1 giới hạn phần heap bị ảnh hưởng bởi con trỏ native. Vùng chứa đối tượng bị ghim có thể tạm thời không được thu hồi trọn vẹn, trong khi các vùng còn lại vẫn tham gia thu gom.

## Ví dụ JNI critical region

Các hàm JNI trong ví dụ dưới đây đã tồn tại từ lâu và vẫn có trong JNI Specification của Java SE 27. JEP 423 không tạo ra các hàm này; nó cải thiện cách G1 xử lý đối tượng được truy cập qua chúng.

Phía Java khai báo một native method nhận mảng byte:

```java
import java.util.Objects;

public final class NativeChecksum {
    static {
        System.loadLibrary("nativechecksum");
    }

    public static long sum(byte[] values) {
        Objects.requireNonNull(values, "values");
        return sumNative(values);
    }

    private static native long sumNative(byte[] values);
}
```

Phía C có thể lấy con trỏ đến dữ liệu mảng, thực hiện một phép tính ngắn rồi trả con trỏ lại cho JVM:

```c
#include <jni.h>

JNIEXPORT jlong JNICALL
Java_NativeChecksum_sumNative(JNIEnv *env, jclass type, jbyteArray values) {
    (void) type;

    // Thực hiện các lời gọi JNI cần thiết trước critical region.
    jsize length = (*env)->GetArrayLength(env, values);

    jbyte *bytes = (*env)->GetPrimitiveArrayCritical(env, values, NULL);
    if (bytes == NULL) {
        // Một số VM có thể trả NULL mà không đặt exception đang pending.
        if (!(*env)->ExceptionCheck(env)) {
            jclass error = (*env)->FindClass(
                env, "java/lang/OutOfMemoryError"
            );
            if (error != NULL) {
                (*env)->ThrowNew(
                    env, error, "GetPrimitiveArrayCritical failed"
                );
            }
        }
        return 0;
    }

    jlong sum = 0;
    for (jsize i = 0; i < length; i++) {
        sum += (unsigned char) bytes[i];
    }

    // Chỉ đọc dữ liệu nên JNI_ABORT không yêu cầu copy dữ liệu về mảng.
    (*env)->ReleasePrimitiveArrayCritical(
        env, values, bytes, JNI_ABORT
    );

    return sum;
}
```

Đoạn mã giữa `GetPrimitiveArrayCritical()` và `ReleasePrimitiveArrayCritical()` là critical region. `GetArrayLength()` được gọi trước khi lấy con trỏ. Khi đã lấy con trỏ, ví dụ chỉ duyệt dữ liệu và tính tổng; nó không gọi thêm JNI function hoặc thực hiện thao tác có thể chặn thread.

`GetPrimitiveArrayCritical()` có thể trả về con trỏ đến dữ liệu gốc hoặc một bản sao, tùy cách VM biểu diễn dữ liệu. Vì vậy, native code phải kiểm tra kết quả `NULL` và luôn gọi hàm release tương ứng sau khi lấy con trỏ thành công. Trong ví dụ, `JNI_ABORT` phù hợp vì native code chỉ đọc mảng và không cần copy thay đổi trở lại Java heap.

Ví dụ này minh họa cách dùng JNI critical API, không phải mã để điều khiển region pinning. Ứng dụng không có lời gọi Java nào để tự pin một region; HotSpot và G1 quản lý việc đó khi cần.

## Giới hạn vẫn phải tuân thủ

Region pinning giúp G1 tiếp tục thu gom trong khi native code giữ một con trỏ hợp lệ. Nó không loại bỏ các quy tắc của JNI critical region:

- Native code không được gọi các JNI function khác trong critical region.
- Không thực hiện system call có thể chặn thread và chờ một Java thread khác.
- Không giữ con trỏ trong thời gian dài. Hãy hoàn thành công việc cần thiết rồi gọi hàm release tương ứng càng sớm càng tốt.
- Không sử dụng con trỏ sau khi đã release.
- Luôn kiểm tra kết quả của `GetPrimitiveArrayCritical()` hoặc hàm critical tương ứng. VM vẫn có thể trả về bản sao thay vì địa chỉ gốc; việc pinning không đảm bảo luôn tránh được sao chép.

Đối tượng bị ghim không thể di chuyển trong thời gian native code cần giữ địa chỉ. Nếu G1 không thể di chuyển tất cả đối tượng sống ra khỏi một region, region đó tạm thời không sẵn sàng để cấp phát. Việc pinning kéo dài hoặc xuất hiện trên nhiều vùng có thể làm tăng áp lực heap và gây evacuation failure. Nếu GC không thu hồi đủ bộ nhớ trong trường hợp xấu nhất, G1 vẫn có thể phải chạy Full GC.

## Quan sát pinning qua GC log

Có thể bật unified logging để xem hoạt động GC:

```bash
java -Xlog:gc -jar application.jar
```

Tài liệu G1 của Java SE 27 mô tả log evacuation failure có thể chứa lý do `Pinned`, ví dụ:

```text
[info][gc] GC(26) Pause Young (Normal) (G1 Evacuation Pause)
    (Evacuation Failure: Allocation/Pinned) ...
```

Ý nghĩa của hai lý do thường gặp:

| Lý do | Ý nghĩa |
|---|---|
| `Pinned` | G1 không thể di chuyển một đối tượng đang được giữ tại địa chỉ cố định để native code sử dụng, chẳng hạn qua `GetPrimitiveArrayCritical()` hoặc JNI call tương tự. |
| `Allocation` | G1 không tìm được đủ chỗ ở vùng đích để di chuyển đối tượng. |

Một dòng log có cả `Allocation` và `Pinned` cho biết cả hai tình huống đều xuất hiện trong lần evacuation đó. Đây là thông tin chẩn đoán về những đối tượng không thể di chuyển trong lần GC, không có nghĩa toàn bộ garbage collection đã bị vô hiệu hóa. G1 đưa các region gặp evacuation failure vào nhóm ứng viên để tiếp tục thu gom ở những lần GC sau.

Khi điều tra vấn đề, hãy xem tần suất của `Pinned`, thời lượng critical region trong native library, mức sử dụng heap và các evacuation failure khác. Không nên kết luận chỉ từ một dòng log; cần đối chiếu với GC log đầy đủ và hành vi ứng dụng.

## Khi nào kiến thức này hữu ích?

Region pinning đặc biệt hữu ích khi vận hành hoặc tối ưu ứng dụng Java có native library, chẳng hạn thư viện xử lý ảnh, âm thanh, nén dữ liệu hoặc tính toán số sử dụng JNI để truy cập primitive array. Nó giải thích vì sao G1 hiện đại có thể tiếp tục thu gom phần lớn heap dù native code đang giữ một con trỏ đến dữ liệu Java.

Khi thiết kế native integration mới, hãy cân nhắc Foreign Function & Memory API (FFM), API chính thức từ JDK 22. FFM có mô hình gọi hàm và quản lý native memory riêng, không dùng JNI critical region trong ví dụ này. Region pinning chủ yếu hữu ích khi vận hành hoặc tối ưu ứng dụng hiện có sử dụng JNI. Dù chọn cơ chế nào, vẫn cần quản lý đúng vòng đời của con trỏ và vùng nhớ native.

## Tự kiểm tra

1. Vì sao G1 phải giữ nguyên địa chỉ của đối tượng mà native code đang truy cập qua `GetPrimitiveArrayCritical()`?
2. Region pinning giúp G1 tiếp tục thu gom heap như thế nào khi một region đang chứa đối tượng bị ghim?
3. Vì sao native code vẫn phải gọi `ReleasePrimitiveArrayCritical()` sớm dù G1 không cần dừng toàn bộ GC?
4. Dòng `Evacuation Failure: Pinned` trong GC log cho biết điều gì? Nó có đồng nghĩa toàn bộ GC đã dừng không?
5. Vì sao region chứa đối tượng pinned có thể chưa được thu hồi ngay sau khi native code release con trỏ?

## Tài liệu tham khảo

- [JEP 423: Region Pinning for G1](https://openjdk.org/jeps/423)
- [Java SE 27 — Garbage-First (G1) Garbage Collector](https://docs.oracle.com/en/java/javase/27/gctuning/garbage-first-g1-garbage-collector.html)
- [Java SE 27 — JNI Functions: GetPrimitiveArrayCritical and ReleasePrimitiveArrayCritical](https://docs.oracle.com/en/java/javase/27/docs/specs/jni/functions.html)
- [JDK 22 Release Notes — Region Pinning for G1](https://www.oracle.com/java/technologies/javase/22-relnote-issues.html)
- [JEP 454: Foreign Function & Memory API](https://openjdk.org/jeps/454)
