# Giới hạn của region pinning khi số vùng bị ghim hoặc thời gian ghim tăng cao

G1 Region Pinning giúp G1 tiếp tục chạy garbage collection (GC) trong khi mã native đang giữ con trỏ tới dữ liệu Java thông qua JNI critical region. Cơ chế này giảm tình trạng GC phải chờ toàn bộ critical region kết thúc. Tuy nhiên, nó không làm cho đối tượng đang được native sử dụng có thể di chuyển: G1 vẫn phải giữ đối tượng ở địa chỉ ổn định và có thể phải trì hoãn việc thu hồi region chứa đối tượng đó.

Tính năng được đưa vào JDK 22 theo JEP 423 và vẫn là hành vi của G1 trong JDK 27. Đây là thay đổi bên trong garbage collector, không phải API Java mới, không phải preview hoặc incubator, và không cần bật bằng một cờ riêng. Bài học tập trung vào giới hạn khi nhiều region cùng bị ghim hoặc critical region tồn tại quá lâu, cách nhận biết áp lực GC và cách thiết kế JNI để giảm thời gian ghim.

Sau bài học, bạn có thể:

- Giải thích vì sao G1 vẫn chạy GC nhưng không thể di chuyển đối tượng đang được native giữ con trỏ.
- Phân biệt tác động của số region bị ghim với thời gian ghim.
- Nhận biết `Evacuation Failure: Pinned` trong GC log và hiểu hệ quả đối với heap.
- Thiết kế JNI critical region ngắn, không chặn và luôn giải phóng con trỏ.
- Chọn cách trao đổi dữ liệu khác khi xử lý native cần thời gian dài hoặc dữ liệu lớn.

## 1. Region pinning giải quyết vấn đề gì?

Khi native code cần truy cập trực tiếp phần tử của một Java primitive array, JNI cung cấp cặp hàm `GetPrimitiveArrayCritical` và `ReleasePrimitiveArrayCritical`. Sau khi nhận được con trỏ, native code phải dùng nó trong phạm vi critical region và trả lại cho JVM bằng hàm release tương ứng.

Trước JDK 22, G1 có thể phải trì hoãn GC trong khi một critical region đang giữ con trỏ tới Java heap. Nếu critical region kéo dài, các luồng ứng dụng khác có thể phải chờ GC. JEP 423 thay đổi cách G1 xử lý: thay vì cần dừng toàn bộ hoạt động GC trong critical region, G1 có thể ghim region chứa đối tượng mà native code đang sử dụng và tiếp tục thu gom những vùng khác.

G1 chia Java heap thành các region. Region là đơn vị cấp phát và thu hồi bộ nhớ của collector. Trong GC, G1 thường di chuyển các đối tượng còn sống ra khỏi region được chọn để thu hồi, sau đó tái sử dụng vùng nhớ cũ. Đối tượng bị ghim phải giữ nguyên địa chỉ vì native code đang giữ con trỏ tới nó. Nếu không thể di chuyển hết đối tượng ra khỏi một region, G1 chưa thể thu hồi region đó trong lần GC hiện tại.

Điểm cần nhớ là GC vẫn có thể chạy, nhưng không phải mọi vùng nhớ đều có thể được di chuyển hoặc thu hồi ngay lúc đó. Đây là đánh đổi cốt lõi của region pinning.

## 2. Số lượng region bị ghim ảnh hưởng đến heap như thế nào?

Tác động phụ thuộc vào số region khác nhau đang bị ghim, thời điểm GC diễn ra và lượng dữ liệu còn sống trong từng region. Một critical array bị ghim có thể khiến region chứa nó không thể được thu hồi hoàn toàn. Nếu nhiều array nằm rải rác trên nhiều region và cùng bị ghim, nhiều region có thể đồng thời không thể được thu hồi.

| Tình huống | Tác động có thể xảy ra |
|---|---|
| Chỉ một vài region bị ghim trong thời gian ngắn | G1 vẫn thu gom các region khác; phần bộ nhớ bị ảnh hưởng thường giới hạn. |
| Nhiều array ở nhiều region cùng được ghim | Nhiều region không thể được thu hồi ngay; lượng heap sẵn sàng cho cấp phát và evacuation giảm. |
| Một region có nhiều đối tượng đang được native giữ | Region chỉ có thể trở lại trạng thái thu hồi đầy đủ sau khi các pin liên quan được giải phóng và GC có cơ hội xử lý lại. |
| Số region bị ghim tăng trong lúc ứng dụng cấp phát nhanh | Heap pressure tăng; G1 có thể phải thực hiện nhiều công việc thu gom hơn để tìm đủ vùng trống. |

Số lần gọi `GetPrimitiveArrayCritical` không nhất thiết bằng số region bị ghim. Nhiều array có thể nằm trong cùng một region, còn một số array khác nhau có thể nằm ở nhiều region. Vì vậy, không thể suy ra mức áp lực heap chỉ bằng cách đếm số lần gọi JNI. Phân bố dữ liệu trong heap và thời điểm giải phóng con trỏ cũng quan trọng.

JEP 423 ghi nhận nguy cơ heap exhaustion nếu ứng dụng ghim quá nhiều region cùng lúc. Khi G1 không thể thu hồi đủ dung lượng, ứng dụng có thể chịu thêm áp lực cấp phát, GC liên tiếp hoặc phải chạy Full GC. Region pinning giảm việc GC bị chặn bởi critical region, nhưng không tạo thêm dung lượng heap và cũng không loại bỏ giới hạn bộ nhớ vật lý.

## 3. Thời gian ghim dài khiến việc thu hồi bị trì hoãn

Khi native code giữ con trỏ lâu, region liên quan vẫn phải được giữ ổn định. Trong thời gian đó, G1 có thể gặp lại region này ở các chu kỳ GC khác nhau và không thể hoàn tất evacuation nếu đối tượng còn bị ghim.

Hệ quả thường thấy:

- Region không được thu hồi ngay cả khi phần lớn dữ liệu khác trong đó không còn cần thiết.
- G1 phải giữ lại hoặc thử thu hồi region ở những lần GC sau.
- Nếu có nhiều region bị giữ lâu, khả năng tìm đủ vùng trống giảm và heap pressure tăng.
- Trong tình huống nghiêm trọng, G1 có thể phải thực hiện Full GC; Full GC là thao tác dừng ứng dụng và có thể rất chậm.

Một vùng bị ghim trong thời gian ngắn có thể được thu hồi ở một lần GC tiếp theo sau khi pin được giải phóng. Nhưng nếu native code tiếp tục giữ con trỏ, việc đưa region vào danh sách ứng viên thu hồi không có nghĩa là G1 có thể di chuyển đối tượng ngay lập tức.

JDK 22 cũng cải thiện cách G1 xử lý các region từng gặp evacuation failure: các region này có thể được đưa trở lại làm ứng viên thu hồi ở các lần GC tiếp theo, thay vì bị giữ lại cho tới một lần phân tích toàn heap sau đó. Cải thiện này giúp giảm heap pressure do region thất bại evacuation còn sót lại, nhưng không thể giải quyết một pin vẫn đang hoạt động.

## 4. Ví dụ JNI: giữ critical pointer lâu hơn mức cần thiết

Đoạn mã dưới đây minh họa một native method chỉ đọc một `int[]`. Độ dài được lấy trước khi vào critical region; sau `GetPrimitiveArrayCritical`, native code chỉ đọc dữ liệu và gọi hàm release tương ứng.

```c
#include <jni.h>

JNIEXPORT jlong JNICALL
Java_demo_NativeSum_sum(JNIEnv *env, jclass type, jintArray values) {
    jsize length = (*env)->GetArrayLength(env, values);

    jboolean is_copy = JNI_FALSE;
    jint *elements = (*env)->GetPrimitiveArrayCritical(
            env, values, &is_copy);

    if (elements == NULL) {
        // JVM có thể đã đặt OutOfMemoryError; trả về ngay.
        return 0;
    }

    jlong total = 0;
    for (jsize i = 0; i < length; i++) {
        total += elements[i];
    }

    (*env)->ReleasePrimitiveArrayCritical(
            env, values, elements, JNI_ABORT);
    return total;
}
```

Đây là ví dụ cho một đoạn xử lý ngắn, có giới hạn. `JNI_ABORT` phù hợp vì native code chỉ đọc mảng; nếu JVM đã tạo bản sao, thay đổi trên bản sao sẽ không được ghi ngược. Nếu JVM trả con trỏ trực tiếp tới mảng, chế độ release này không hoàn tác dữ liệu gốc vì ví dụ không sửa dữ liệu.

`is_copy` cho biết JVM có trả về bản sao hay không, nhưng chương trình không được giả định luôn nhận được con trỏ trực tiếp. JNI cho phép JVM tạo bản sao nếu cách biểu diễn dữ liệu nội bộ yêu cầu. Cả trường hợp copy lẫn pin đều phải gọi hàm release đúng cặp.

Một thiết kế có vấn đề là lấy con trỏ rồi thực hiện I/O, chờ khóa, đợi thread khác, gọi callback Java hoặc xử lý một tác vụ không giới hạn trước khi release. Thời gian từ `GetPrimitiveArrayCritical` đến `ReleasePrimitiveArrayCritical` càng dài, region càng lâu không thể được giải phóng theo cách bình thường.

## 5. Những giới hạn của JNI critical region vẫn còn nguyên

Region pinning không thay đổi các quy tắc của JNI. Sau khi gọi `GetPrimitiveArrayCritical`, native code không nên chạy trong thời gian dài trước khi gọi `ReleasePrimitiveArrayCritical`. Trong critical region, native code không được gọi các JNI function khác và không được gọi system call có thể làm thread hiện tại chặn để chờ một Java thread khác.

Các việc nên tránh trong critical region:

- Đọc hoặc ghi file, socket hay pipe.
- Chờ condition variable, semaphore, monitor hoặc mutex có thể bị giữ bởi thread khác.
- Gọi JNI để truy cập field, tạo object, gọi method hoặc callback về Java.
- Thực hiện tác vụ không giới hạn hoặc xử lý cả một pipeline lớn trong khi giữ con trỏ.
- Giữ nhiều critical pointer cùng lúc nếu không thực sự cần thiết.

Hãy chuẩn bị metadata, kích thước, buffer phụ và các tài nguyên cần thiết trước khi lấy con trỏ. Sau đó chỉ thực hiện đoạn tính toán ngắn, rồi release ngay. Nếu cần chờ, truy cập hệ thống hoặc thực hiện công việc dài, hãy giải phóng con trỏ trước khi thực hiện các thao tác đó.

Một chi tiết quan trọng: `GetPrimitiveArrayCritical` có thể trả về bản sao thay vì pin trực tiếp đối tượng Java. Điều này không làm mất các quy tắc critical region; native code vẫn phải release đúng cách và không được giả định rằng mọi lần gọi đều là zero-copy.

## 6. G1 biểu hiện áp lực pinning trong GC log ra sao?

JDK 27 G1 tuning guide mô tả evacuation failure và các nguyên nhân có thể được in trong GC log khi bật `-Xlog:gc`:

```text
Evacuation Failure: Pinned
```

Một log có thể ghi cả `Allocation` và `Pinned`:

```text
[info][gc] GC(26) Pause Young (Normal) (G1 Evacuation Pause) \
    (Evacuation Failure: Allocation/Pinned) 2159M->402M(3000M) 6.108ms
```

Hai lý do có ý nghĩa khác nhau:

| Nguyên nhân | Ý nghĩa |
|---|---|
| `Allocation` | G1 không tìm đủ vùng đích để di chuyển đối tượng. |
| `Pinned` | Có đối tượng không thể di chuyển vì đang được giữ cố định để native code sử dụng qua `GetPrimitiveArrayCritical` hoặc JNI call tương tự. |

Nếu G1 không thể di chuyển hết đối tượng ra khỏi region, region đó tạm thời không sẵn sàng cho cấp phát. G1 đưa region đã gặp evacuation failure vào danh sách ứng viên collection set cho các lần GC tiếp theo. Nếu GC không thu hồi được dung lượng cần thiết, G1 có thể phải chạy Full GC.

Lưu ý rằng dòng `Pinned` là dấu hiệu để điều tra, không tự nó chứng minh toàn bộ độ trễ GC đến từ JNI pinning. Log có thể đồng thời có `Allocation`, và ứng dụng còn có thể gặp áp lực heap vì tốc độ cấp phát, dữ liệu sống lâu, humongous object hoặc nguyên nhân khác. Hãy đọc toàn bộ chuỗi GC event và so sánh với thời gian xử lý native.

## 7. Quy trình điều tra khi nghi ngờ pinning gây heap pressure

1. **Bật GC logging.** Chạy ứng dụng với `-Xlog:gc` trong môi trường có tải đại diện để quan sát `Evacuation Failure: Pinned`, các lần GC liên tiếp và Full GC.
2. **Đối chiếu thời điểm.** So sánh timestamp GC với các thao tác JNI có dùng `GetPrimitiveArrayCritical`. Ghi nhận thời gian từ lúc lấy con trỏ đến lúc release ở native library.
3. **Đo số critical section đang hoạt động.** Thêm metric trong native code cho số pin đang mở, thời gian giữ trung bình, thời gian giữ lớn nhất và số lần critical section bị lồng nhau. GC log không thay thế metric ở cấp ứng dụng.
4. **Kiểm tra đường thoát.** Xác nhận mọi nhánh thành công, lỗi và early return đều gọi hàm release tương ứng. Một nhánh quên release có thể giữ region lâu hơn dự kiến.
5. **Phân biệt nguyên nhân evacuation failure.** Nếu log có cả `Allocation` và `Pinned`, cần kiểm tra cả dung lượng vùng đích và pinning; không quy mọi sự cố cho JNI.
6. **Thử lại sau khi rút ngắn critical region.** So sánh số lần `Pinned`, thời gian GC, heap occupancy sau GC và throughput dưới cùng tải.

Không có API Java chuẩn để ứng dụng yêu cầu G1 bỏ qua một pin còn hiệu lực hoặc buộc di chuyển đối tượng mà native code đang giữ con trỏ. Vì vậy, bước điều tra có giá trị nhất thường là đo và sửa thời gian sống của critical pointer trong thư viện native.

## 8. Cách giảm tác động khi xử lý native cần nhiều thời gian

| Nhu cầu | Cách tiếp cận nên cân nhắc |
|---|---|
| Xử lý nhanh một mảng nhỏ | `GetPrimitiveArrayCritical` có thể phù hợp nếu critical region ngắn và tuân thủ JNI. |
| Chỉ cần một phần của mảng | Dùng `Get<Type>ArrayRegion` để copy phần cần thiết sang native buffer, xử lý sau khi JNI call kết thúc. |
| Xử lý mảng lớn hoặc thuật toán chạy lâu | Copy dữ liệu sang native buffer hoặc chia thành các chunk; tránh giữ con trỏ Java trong toàn bộ thời gian xử lý. |
| Trao đổi dữ liệu lớn, lặp lại giữa Java và native | Cân nhắc direct `ByteBuffer` hoặc vùng nhớ native được quản lý bằng Foreign Function & Memory API (`MemorySegment`) nếu kiến trúc ứng dụng phù hợp. |
| Có nhiều critical pointer lồng nhau | Giảm số lượng pointer giữ đồng thời và release theo thứ tự ngược với lúc acquire. |

Copy dữ liệu có chi phí bộ nhớ và CPU, nhưng đổi lại thời gian giữ Java heap ổn định có thể ngắn hơn nhiều. Với thuật toán native dài, việc copy một lần rồi xử lý trên buffer riêng thường dễ kiểm soát hơn việc ghim Java array trong suốt thuật toán.

Direct buffer và native `MemorySegment` nằm ngoài Java heap nên không cần G1 di chuyển vùng nhớ native đó. Tuy nhiên, chúng có vòng đời, giới hạn truy cập và yêu cầu giải phóng bộ nhớ riêng. Chỉ chuyển sang off-heap khi đo đạc cho thấy lợi ích đủ lớn và ứng dụng có quy tắc sở hữu bộ nhớ rõ ràng.

Tăng `-Xmx` có thể tạo thêm headroom trong một số hệ thống, nhưng không giải phóng region đang bị ghim. Thay đổi `-XX:G1HeapRegionSize` cũng không phải giải pháp mặc định: thay đổi kích thước region ảnh hưởng tới toàn bộ hành vi G1 và cần benchmark theo workload thực tế. Trước hết hãy rút ngắn critical region và xác nhận nguyên nhân qua log.

## 9. Phạm vi áp dụng và trạng thái trên JDK hiện đại

| Phiên bản | Trạng thái region pinning của G1 |
|---|---|
| JDK 21 trở về trước | Chưa có cơ chế region pinning theo JEP 423; G1 có thể trì hoãn GC trong JNI critical region. |
| JDK 22 | JEP 423 được tích hợp; G1 có thể tiếp tục GC trong khi region chứa đối tượng native đang sử dụng được ghim. |
| JDK 27 | Hành vi vẫn được hỗ trợ; tài liệu G1 hiện hành mô tả `Evacuation Failure: Pinned` và cách G1 thử thu hồi region ở các lần GC tiếp theo. |

JEP 423 áp dụng cho G1. Không nên suy rộng chi tiết triển khai region pinning này thành một bảo đảm chung cho mọi garbage collector. G1 là collector mặc định của JDK 27, nhưng ứng dụng có thể chọn collector khác; khi đó cần đọc tài liệu của collector được chọn.

Region pinning không phải API để lập trình viên gọi trực tiếp, không có tùy chọn bật/tắt riêng trong mã Java và không loại bỏ các giới hạn của JNI critical section. Đây là cơ chế nội bộ giúp G1 duy trì tiến triển GC tốt hơn khi native code cần truy cập Java heap.

## 10. Kết luận

Region pinning giúp G1 tiếp tục thu gom các vùng heap khác trong khi giữ nguyên địa chỉ của đối tượng mà native code đang truy cập. Giới hạn xuất hiện khi nhiều region cùng bị ghim hoặc critical pointer được giữ quá lâu: G1 không thể hoàn tất evacuation ở các region liên quan, vùng nhớ sẵn sàng cho cấp phát giảm và heap pressure có thể tăng.

Khi điều tra, hãy tìm `Evacuation Failure: Pinned` trong `-Xlog:gc`, đo thời gian giữ critical pointer trong native library và kiểm tra mọi nhánh đều release đúng cặp. Giữ critical region ngắn, không chặn, hoặc chuyển dữ liệu sang native buffer/direct memory khi công việc kéo dài. JEP 423 là tính năng chính thức từ Java 22 và vẫn hữu ích trên JDK 27, nhưng không thay thế trách nhiệm quản lý vòng đời con trỏ JNI.

## Tài liệu tham khảo

- [JEP 423: Region Pinning for G1](https://openjdk.org/jeps/423)
- [Oracle JDK 22 Release Notes: Region Pinning for G1](https://www.oracle.com/java/technologies/javase/22-relnote-issues.html)
- [Oracle Java SE 27: Garbage-First (G1) Garbage Collector — Evacuation Failure](https://docs.oracle.com/en/java/javase/27/gctuning/garbage-first-g1-garbage-collector.html)
- [Oracle Java SE 27: Garbage-First Garbage Collector Tuning](https://docs.oracle.com/en/java/javase/27/gctuning/garbage-first-garbage-collector-tuning.html)
- [Oracle Java SE 27: JNI Functions — GetPrimitiveArrayCritical and ReleasePrimitiveArrayCritical](https://docs.oracle.com/en/java/javase/27/docs/specs/jni/functions.html)
- [OpenJDK review: Implementation details for JEP 423](https://mail-archive.com/serviceability-dev%40openjdk.org/msg09644.html)
