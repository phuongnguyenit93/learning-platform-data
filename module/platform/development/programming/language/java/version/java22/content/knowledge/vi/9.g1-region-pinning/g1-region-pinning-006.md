# Phân biệt ghim vùng nhớ của GC với ghim carrier thread của virtual thread

Trong Java có hai cơ chế thường cùng được gọi là *pinning*, nhưng chúng giữ những thứ hoàn toàn khác nhau:

- **G1 region pinning** giữ một vùng của Java heap tại vị trí hiện tại để mã native có thể tiếp tục dùng tham chiếu tới đối tượng trong vùng đó. Đây là cơ chế của garbage collector.
- **Virtual-thread carrier pinning** giữ một virtual thread gắn với platform thread đang chạy nó, khiến carrier không thể được giải phóng để chạy virtual thread khác khi tác vụ bị block. Đây là cơ chế của bộ lập lịch thread.

Hai cơ chế có thể xuất hiện cùng lúc trong một lời gọi JNI, nhưng không thay thế hoặc tự động kéo theo nhau. G1 region pinning được đưa vào G1 từ Java 22 theo JEP 423. Với virtual thread, cần dùng trạng thái hiện hành: JEP 491 đã loại bỏ pinning chỉ do `synchronized` từ JDK 24, nhưng JDK 27 vẫn ghi nhận native method và foreign function là những trường hợp có thể pin carrier.

## 1. G1 region pinning giữ đối tượng trong Java heap

G1 chia Java heap thành các vùng có kích thước cố định gọi là *region*. Khi thu gom rác, G1 thường di chuyển các đối tượng còn sống ra khỏi region được chọn để thu hồi vùng cũ. Việc di chuyển này được gọi là *evacuation*.

Một số đoạn mã native cần giữ con trỏ trực tiếp tới dữ liệu của một Java array trong một khoảng thời gian ngắn. Với JNI, cơ chế thường gặp là cặp hàm `GetPrimitiveArrayCritical` và `ReleasePrimitiveArrayCritical`. Trong khoảng giữa hai lời gọi, native code có thể đang sử dụng địa chỉ phần tử của array; JVM phải bảo đảm địa chỉ đó không bị thay đổi ngoài dự kiến.

JEP 423 bổ sung region pinning cho G1 để garbage collection không phải bị vô hiệu hóa trong toàn bộ JNI critical region. G1 có thể tiếp tục thu gom các vùng heap khác, đồng thời giữ vùng chứa đối tượng đang được native code sử dụng ở vị trí hiện tại. Sau khi native code nhả tham chiếu, vùng đó có thể được di chuyển trong một chu kỳ thu gom sau.

Điều này không có nghĩa toàn bộ heap bị pin, cũng không có nghĩa G1 ngừng chạy. Đơn vị di chuyển và thu hồi của G1 là region; nếu một đối tượng trong region cần được giữ nguyên vị trí, region đó có thể tạm thời không được evacuation.

## 2. JNI critical region là tình huống điển hình

Đoạn mã C dưới đây chỉ minh họa cơ chế mà G1 cần hỗ trợ. Đây là ví dụ để hiểu mã JNI hiện có, không phải lời khuyên dùng JNI cho mọi tích hợp native mới:

```c
JNIEXPORT void JNICALL
Java_com_example_NativeOps_process(JNIEnv *env, jclass type, jintArray values) {
    jsize length = (*env)->GetArrayLength(env, values);
    jboolean is_copy = JNI_FALSE;
    jint *elements = (*env)->GetPrimitiveArrayCritical(
            env, values, &is_copy);

    if (elements == NULL) {
        return; // JVM đã báo lỗi, chẳng hạn thiếu bộ nhớ
    }

    // Chỉ thực hiện công việc ngắn trên vùng dữ liệu đã lấy.
    for (jsize i = 0; i < length; i++) {
        elements[i] *= 2;
    }

    (*env)->ReleasePrimitiveArrayCritical(
            env, values, elements, 0);
}
```

Trong mã thực tế, cần bảo đảm mọi đường đi sau khi lấy được con trỏ đều gọi hàm `ReleasePrimitiveArrayCritical` tương ứng. Critical region phải ngắn; không gọi các hàm JNI khác hoặc thực hiện system call có thể block và chờ thread Java khác trong vùng này. JVM có thể trả về bản sao thay vì địa chỉ trực tiếp của array, vì vậy native code cũng phải tuân thủ hợp đồng của API.

G1 region pinning giúp collector tiếp tục làm việc trên các region khác trong khi vùng dữ liệu cần được giữ nguyên vị trí. Nó không nới lỏng các quy tắc sử dụng critical region của JNI.

## 3. Virtual-thread pinning giữ carrier thread

Virtual thread được JVM lập lịch lên một platform thread, còn gọi là *carrier*. Trong những thao tác block có thể unmount, JVM tạm dừng virtual thread và giải phóng carrier để carrier chạy virtual thread khác.

Nếu virtual thread đang ở trạng thái pinned, JVM không thể unmount nó trong lúc block. Carrier vẫn bị giữ bởi virtual thread đó. Nếu nhiều virtual thread thường xuyên block trong trạng thái pinned, số carrier sẵn sàng có thể giảm và khả năng mở rộng của ứng dụng bị ảnh hưởng.

Theo tài liệu virtual thread của JDK 27, virtual thread bị pin khi thực thi native method hoặc foreign function. Điều này bao gồm lời gọi hàm native thông qua JNI và lời gọi foreign function qua Foreign Function & Memory API (FFM).

### Thay đổi quan trọng từ JDK 24

Trước JDK 24, virtual thread có thể bị pin khi block bên trong `synchronized` method hoặc block. JEP 491, được phát hành trong JDK 24, thay đổi cách JVM quản lý monitor để virtual thread có thể unmount trong các trường hợp đồng bộ hóa này.

Vì vậy, trên JDK hiện đại, không nên áp dụng máy móc hướng dẫn cũ là thay mọi `synchronized` bằng `ReentrantLock` chỉ để tránh pinning. `synchronized` vẫn là cơ chế đồng bộ hóa hợp lệ. Hãy tìm nguyên nhân pinning thực tế qua dữ liệu quan sát; native method và foreign function vẫn là các trường hợp cần chú ý. JFR cũng có thể ghi nhận một thao tác block khi native hoặc VM frame còn trên stack, ví dụ lúc chờ monitor trong một call stack đã bị pin bởi native frame.

## 4. Hai loại pinning khác nhau ở điểm nào?

| Tiêu chí | G1 region pinning | Virtual-thread carrier pinning |
| --- | --- | --- |
| Thành phần bị giữ | Region chứa đối tượng trong Java heap | Virtual thread gắn với carrier platform thread |
| Thành phần quản lý | G1 garbage collector | JVM virtual-thread scheduler/runtime |
| Mục đích | Giữ địa chỉ đối tượng ổn định khi native code đang sử dụng | Giữ call stack thực thi native/foreign code trên carrier |
| Tình huống điển hình | JNI critical array access như `GetPrimitiveArrayCritical` | Virtual thread gọi native method hoặc foreign function |
| Tác động chính | Region bị pin không thể evacuation trong lúc cần giữ; có thể giảm khả năng thu hồi vùng đó ở chu kỳ hiện tại | Carrier không được giải phóng khi virtual thread bị block trong trạng thái pinned; có thể giảm khả năng phục vụ tác vụ khác |
| Cách quan sát | GC log, ví dụ `Evacuation Failure: Pinned` | JFR event `jdk.VirtualThreadPinned` |
| Phạm vi | Cơ chế của collector G1 | Cơ chế lập lịch virtual thread, không phụ thuộc riêng G1 |

G1 region pinning không làm virtual thread tự động unmount khỏi carrier. Ngược lại, virtual-thread pinning cũng không có nghĩa một region Java heap đang bị G1 pin.

## 5. Khi nào hai cơ chế có thể xuất hiện cùng lúc?

Giả sử một virtual thread gọi native method JNI, và native method đó lấy con trỏ tới một primitive array bằng `GetPrimitiveArrayCritical`:

1. Virtual thread đi vào native method. Trong thời gian thực thi native method, virtual thread vẫn gắn với carrier platform thread.
2. Native method lấy địa chỉ dữ liệu của Java array bằng `GetPrimitiveArrayCritical`.
3. G1 phải giữ ổn định đối tượng chứa dữ liệu native code đang tham chiếu. G1 region pinning cho phép collector tiếp tục làm việc trên các vùng khác trong khi region cần giữ được bảo toàn.
4. Native method gọi `ReleasePrimitiveArrayCritical` rồi kết thúc lời gọi. Điều kiện giữ địa chỉ của array được giải phóng; virtual thread cũng rời native frame khi quay lại Java code.

Trong tình huống này, có thể đồng thời có một region của heap bị pin và một virtual thread bị pin vào carrier. Hai trạng thái có vòng đời và cách chẩn đoán riêng.

FFM downcall cũng có thể pin carrier của virtual thread vì virtual thread đang chạy foreign function. Tuy nhiên, bản thân việc gọi foreign function không đồng nghĩa G1 đang pin một region của Java heap. G1 region pinning trong JEP 423 tập trung vào việc bảo vệ đối tượng heap được native code truy cập qua JNI critical access.

## 6. Phân biệt qua log và công cụ chẩn đoán

### Nhận biết G1 region pinning

Bật GC logging để xem các lần evacuation failure:

```bash
java -Xlog:gc -jar app.jar
```

Một dòng log có thể chứa:

```text
Evacuation Failure: Allocation/Pinned
```

Trong đó:

- `Allocation` cho biết G1 không tìm được đủ vùng đích để di chuyển đối tượng.
- `Pinned` cho biết G1 không thể di chuyển một đối tượng đang bị giữ cố định để native code sử dụng, chẳng hạn qua `GetPrimitiveArrayCritical` hoặc cơ chế JNI tương tự.

Nếu G1 không thể di chuyển các đối tượng ra khỏi một region, region đó tạm thời không có sẵn để cấp phát. G1 đưa các region gặp evacuation failure vào danh sách ứng viên để thử evacuation trong các lần GC tiếp theo. Một log có `Pinned` là dấu hiệu cần điều tra, không tự nó chứng minh ứng dụng có lỗi hoặc phải đổi collector.

### Nhận biết virtual-thread carrier pinning

JDK Flight Recorder cung cấp event `jdk.VirtualThreadPinned`. Event này được bật mặc định với ngưỡng 20 ms; nó ghi nhận virtual thread bị pin đủ lâu và cung cấp thông tin về thao tác block cùng lý do pinning.

Khởi chạy ứng dụng với JFR recording:

```bash
java -XX:StartFlightRecording:dumponexit=true,filename=recording.jfr -jar app.jar
```

Sau khi ứng dụng kết thúc, xem các event pinning:

```bash
jfr print --events jdk.VirtualThreadPinned recording.jfr
```

Event có thể cho biết lý do như `Native or VM frame on stack`, virtual thread bị block ở thao tác nào và carrier nào đang bị giữ. Nếu cần chẩn đoán pinning ngắn hơn ngưỡng mặc định, hãy cấu hình JFR recording phù hợp với môi trường đo.

### Bảng đối chiếu nhanh

| Quan sát | Hướng điều tra |
| --- | --- |
| GC log có `Evacuation Failure: Pinned` | Kiểm tra JNI critical access, thời gian giữ array/string pointer và thời điểm release. |
| JFR có `jdk.VirtualThreadPinned` | Kiểm tra stack trace, native method, FFM downcall và thời gian block trong native/foreign call. |
| Có cả hai dấu hiệu | Kiểm tra một JNI critical call có đang vừa giữ heap object vừa chạy trên virtual thread hay không. |
| Không có hai dấu hiệu trên | Không kết luận có pinning chỉ từ việc thấy ứng dụng sử dụng JNI, FFM hoặc virtual thread. |

## 7. Hướng xử lý theo đúng loại pinning

### Khi G1 region bị pin

- Giữ JNI critical region ngắn và chỉ thực hiện công việc cần thiết trên vùng dữ liệu đã lấy.
- Gọi `ReleasePrimitiveArrayCritical` hoặc hàm release tương ứng đúng cách trên mọi đường đi.
- Không thực hiện I/O, chờ lock hoặc gọi JNI tùy ý trong critical region.
- Dùng GC log để xác định tần suất `Pinned` và xem liệu region có được evacuation thành công ở chu kỳ sau hay không.
- Không đổi G1 hoặc tăng heap chỉ dựa trên một dòng log đơn lẻ; cần đối chiếu với allocation rate, heap occupancy và pause time.

### Khi virtual thread bị pin vào carrier

- Xác định native method hoặc foreign function nào nằm trên stack khi virtual thread bị block.
- Tránh để native call kéo dài và block trong khi đang chạy trên virtual thread nếu có thể thay đổi thiết kế.
- Nếu một native operation bắt buộc block lâu, cân nhắc thực thi nó trên platform thread hoặc executor chuyên dụng để không giữ carrier của virtual-thread scheduler.
- Giữ `synchronized` cho mục đích đồng bộ hóa thông thường trên JDK 24+; chỉ thay đổi cơ chế lock khi có lý do cạnh tranh lock hoặc hiệu năng được đo lường, không dựa trên hướng dẫn pinning cũ.
- Dùng JFR để xác định call site và mức độ thường xuyên, thay vì suy đoán từ số lượng virtual thread.

## 8. Tính năng này có còn áp dụng trên JDK hiện đại?

| Tính năng | Trạng thái | Ghi chú hiện hành |
| --- | --- | --- |
| G1 region pinning — JEP 423 | Được triển khai trong Java 22 | Là cải tiến runtime của G1, không phải API Java cần gọi hoặc bật bằng preview. |
| Virtual-thread pinning | Cơ chế runtime vẫn tồn tại | JDK 27 vẫn ghi nhận native method và foreign function là trường hợp pin carrier. |
| Monitor-related pinning trong `synchronized` | Đã được xử lý từ JDK 24 qua JEP 491 | Không áp dụng máy móc workaround cũ cho JDK 24+. |
| `jdk.VirtualThreadPinned` JFR event | Có trong JDK hiện đại | Dùng để chẩn đoán carrier pinning, không phải GC region pinning. |

JEP 423 là tối ưu hóa của G1 và không phải tính năng preview hoặc incubator. JEP 491 là thay đổi runtime chính thức từ JDK 24. Theo tài liệu JDK 27, virtual thread vẫn có thể bị pin khi chạy native method hoặc foreign function; do đó không nên hiểu JEP 491 là loại bỏ mọi loại carrier pinning.

## 9. Kết luận thực hành

Khi thấy từ *pinning*, trước hết hãy hỏi thành phần nào đang bị giữ:

- Nếu GC không thể di chuyển một đối tượng trong heap khi native code giữ địa chỉ của nó, đó là vấn đề G1 region pinning. Xem GC log và vòng đời JNI critical region.
- Nếu virtual thread không thể nhả carrier trong lúc block vì đang chạy native hoặc foreign code, đó là virtual-thread carrier pinning. Xem JFR event `jdk.VirtualThreadPinned`.

Chẩn đoán đúng loại pinning sẽ dẫn đến biện pháp xử lý đúng: một bên liên quan tới khả năng evacuation của G1, bên còn lại liên quan tới khả năng giải phóng carrier cho virtual thread khác.

## 10. Tài liệu tham khảo

- [JEP 423: Region Pinning for G1](https://openjdk.org/jeps/423) — cải tiến G1 cho JNI critical regions trong Java 22.
- [JDK 22 Release Notes — Region Pinning for G1](https://www.oracle.com/java/technologies/javase/22-relnote-issues.html) — mô tả GC vẫn hoạt động và giữ đối tượng native code đang truy cập ở vị trí hiện tại.
- [JDK 27 — Garbage-First (G1) Garbage Collector](https://docs.oracle.com/en/java/javase/27/gctuning/garbage-first-g1-garbage-collector.html) — evacuation failure và log reason `Pinned`.
- [JDK 27 — Virtual Threads](https://docs.oracle.com/en/java/javase/27/core/virtual-threads.html) — carrier, native/foreign function pinning và JFR event `jdk.VirtualThreadPinned`.
- [JEP 491: Synchronize Virtual Threads without Pinning](https://openjdk.org/jeps/491) — thay đổi từ JDK 24 cho pinning liên quan đến monitor.
- [JNI Functions — GetPrimitiveArrayCritical / ReleasePrimitiveArrayCritical](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/functions.html#getprimitivearraycritical-releaseprimitivearraycritical) — hợp đồng và giới hạn của critical region.
