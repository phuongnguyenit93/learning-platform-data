# Đánh đổi sao chép, ghim mảng, bộ đệm trực tiếp và cấp phát ngoài heap

## 1. Vấn đề hiệu năng tại ranh giới Java và mã native

Khi Java trao đổi dữ liệu với thư viện C/C++, hệ điều hành, driver hoặc thiết bị thông qua JNI, JNA hay Foreign Function & Memory API (FFM), dữ liệu phải tồn tại ở vùng nhớ mà phía native có thể truy cập hợp lệ. Quyết định **sao chép dữ liệu (copy)**, **ghim vùng nhớ heap (pin)**, dùng **direct buffer** hay **cấp phát ngoài heap (off-heap allocation)** ảnh hưởng đến cả tốc độ truyền, độ trễ GC, tính an toàn và vòng đời dữ liệu.

Hãy hình dung ứng dụng Java có một **byte[]** dung lượng lớn, định kỳ đưa sang C để nén hoặc giải mã. Có ít nhất bốn thiết kế:

1. **Copy:** sao chép byte từ mảng Java vào một vùng nhớ native; C làm việc trên bản sao, sau đó sao chép kết quả về khi cần.
2. **Pin:** trong một khoảng thời gian ngắn, cho C truy cập dữ liệu của mảng Java mà JVM không di chuyển vùng nhớ liên quan. JNI có API yêu cầu truy cập mảng, nhưng **JVM có quyền chọn copy thay vì pin**; không thể coi mọi lần gọi là zero-copy.
3. **Direct ByteBuffer:** đặt dữ liệu trong một direct buffer để native có thể truy cập địa chỉ bộ nhớ trực tiếp, đồng thời Java có đối tượng **ByteBuffer** để đọc/ghi. Nếu dữ liệu ban đầu vẫn nằm trong **byte[]**, bước **put(byte[])** thường đã là một phép copy.
4. **Off-heap do ứng dụng quản lý:** cấp phát native memory bằng thư viện C/C++ hoặc FFM **Arena/MemorySegment** (API chuẩn từ Java 22), kiểm soát kích thước, alignment, ownership và thời điểm giải phóng.

**Không tồn tại lựa chọn luôn nhanh nhất.** Khi payload nhỏ, số lần crossing Java/native và chi phí chuẩn bị buffer có thể lớn hơn chi phí copy. Khi dữ liệu lớn, tái sử dụng vùng nhớ nhiều lần có thể tiết kiệm bandwidth copy. Khi GC nhạy cảm với tail latency, tránh pin kéo dài có thể quan trọng hơn việc tiết kiệm một lượt copy. Khi native làm việc bất đồng bộ, quản lý vòng đời bộ nhớ thường quyết định tính đúng đắn trước khi quyết định tốc độ.

### 1.1. Bốn câu hỏi phải trả lời trước khi tối ưu

- **Dữ liệu được sinh ra ở đâu?** Nếu đầu vào là heap **byte[]**, tạo direct buffer rồi **put** không loại bỏ lượt copy đầu tiên. Nếu network/native API ghi trực tiếp vào direct buffer, có thể tránh một bước staging qua heap.
- **Ai sở hữu và được phép sửa dữ liệu?** Một bản sao tạo ra snapshot độc lập; một vùng nhớ dùng chung cần quy ước về thời điểm đọc/ghi và đồng bộ.
- **Native giữ con trỏ trong bao lâu?** Chỉ sử dụng trong một lời gọi đồng bộ, hay giữ lại sau khi JNI/FFM trở về, chạy ở thread khác hoặc callback muộn?
- **Sự thay đổi nào cần được tối ưu?** Throughput, median latency, p99 latency, số byte copy, pause GC, native RSS, khả năng phân bổ hay mức độ an toàn? Một benchmark chỉ đo thời gian native loop chưa trả lời đủ.

## 2. Bản đồ bộ nhớ và bảng so sánh

**Heap Java:** mảng như **byte[]** được JVM quản lý và GC có thể di chuyển đối tượng. C không thể tự ý lưu một địa chỉ heap vĩnh viễn. JNI phải sử dụng API phù hợp; JNI object references cũng không phải con trỏ C trực tiếp đến vùng dữ liệu.

**Native/off-heap memory:** thường nằm ngoài Java heap, có địa chỉ phù hợp để truyền cho các API C. Không chịu việc di chuyển do Java GC, nhưng vẫn chiếm RAM và có thể gây **OutOfMemoryError** hoặc lỗi cấp phát native. Tính hợp lệ của địa chỉ phụ thuộc vào owner và thời điểm giải phóng.

| Kỹ thuật | Điều thường phải trả giá | Điểm mạnh | Nguy cơ hoặc giới hạn |
| --- | --- | --- | --- |
| **Copy từng vùng** qua **GetByteArrayRegion/SetByteArrayRegion** | Chi phí copy theo lượng dữ liệu, có thể cần vùng staging | Rõ ràng về thời điểm trao đổi; không giữ pointer heap lâu; dễ chia chunk | Copy lặp đi lặp lại; phải xác định copy-back và trạng thái |
| **GetByteArrayElements/ReleaseByteArrayElements** | JVM có thể copy hoặc pin, có chi phí acquire/release | API thuận tiện khi cần con trỏ C tạm thời | Không cam kết pin; cần release; GC và copy-back tùy nhánh |
| **GetPrimitiveArrayCritical/ReleasePrimitiveArrayCritical** | Giới hạn nghiêm ngặt bên trong critical region | Có thể cho phép truy cập heap với overhead thấp | Có thể vẫn copy; giữ quá lâu có thể cản trở GC; không block/call JNI khác trong region |
| **ByteBuffer.allocateDirect** | Cấp phát/thu hồi thường đắt hơn heap buffer; Java truy cập có thể khác về chi phí | Hữu ích khi native I/O trực tiếp và tái sử dụng buffer | Vòng đời thu hồi gắn với GC, không thể xem như close tức thì; vẫn copy nếu nguồn là heap |
| **Native malloc/free hoặc wrapper tự quản lý** | Cấp phát, quản lý con trỏ và cleanup thủ công | Ownership, alignment và giao thức với thư viện C có thể rất linh hoạt | Leak, double-free, use-after-free, overflow có thể làm hỏng JVM |
| **FFM Arena/MemorySegment** (Java 22+) | Chi phí scope/bounds/lifetime checks và thiết kế ownership | Vùng native có vòng đời rõ ràng; Java kiểm tra giới hạn và scope trên các thao tác MemorySegment | Con trỏ đã đưa cho C không tự được Java chặn nếu C truy cập sau khi arena đóng |

Phân biệt **zero-copy tại biên Java/native** với **zero-copy toàn bộ đường dữ liệu**. Direct buffer có thể tránh copy tại một API JNI cụ thể, nhưng vẫn có copy từ decoder vào direct buffer, từ user-space sang kernel hoặc do driver/thư viện thực hiện. Một giá trị **isDirect() = true** chỉ mô tả loại buffer, không chứng minh đường I/O cuối cùng không copy.

## 3. Copy: trả phí bandwidth để có ranh giới dữ liệu rõ ràng

Sao chép thường đơn giản hơn pin khi native xử lý lâu hoặc giữ dữ liệu sau lời gọi Java. Sau copy, mảng heap có thể được GC di chuyển, còn native làm việc trên vùng nhớ riêng của nó. Nếu native chỉ đọc, không cần copy ngược. Nếu native ghi kết quả, phải quyết định copy-back nguyên vùng hay chỉ các byte đã sửa.

### 3.1. JNI region API

**GetByteArrayRegion(env, array, start, len, dst)** chuyển một đoạn của mảng Java sang vùng **dst** do C cung cấp; **SetByteArrayRegion** chuyển ngược lại. Các hàm kiểu **Get/Set<Type>ArrayRegion** tồn tại cho các primitive type tương ứng. Chúng phù hợp khi muốn chuyển một khoảng dữ liệu có ranh giới rõ ràng và không cần giữ con trỏ gắn với mảng Java.

Ví dụ quy trình đọc theo chunk:

~~~text
byte[] (Java heap) ---> JNI GetByteArrayRegion ---> staging buffer (C)
                                                    |
                                                    +--> native xử lý từng chunk
                                                    |
                                          không giữ pointer tới heap
~~~

Ưu điểm của region API là tránh giữ cặp pointer **Get...Elements/Release...Elements** qua nhiều nhánh lỗi; đặc biệt khi ứng dụng vốn đã cần copy vào vùng native. Đừng suy ra region nhanh hơn mọi trường hợp: khi phải copy nhiều lần hoặc thực thi rất nhiều lời gọi JNI nhỏ, overhead có thể lớn.

**Chunk size** là một tham số benchmark: chunk quá nhỏ tốn crossing và vòng lặp; chunk quá lớn tăng footprint, cache pressure và độ trễ mỗi bước. Nếu giao thức hỗ trợ streaming, xử lý từng chunk có thể tránh giữ toàn bộ dữ liệu trong một lần.

### 3.2. JNI Elements API có thể copy hoặc pin

**GetByteArrayElements** trả về **jbyte\***, nhưng JVM được phép cung cấp bản sao hoặc pointer vào mảng đã được giữ ổn định. Tham số **isCopy** (nếu cung cấp) có thể giúp quan sát cơ chế mà một lần gọi sử dụng; nó **không phải tùy chọn buộc JVM phải pin**. **ReleaseByteArrayElements** là phần bắt buộc để trả tài nguyên hoặc đồng bộ kết quả.

Chế độ release:

- **mode = 0:** nếu có bản sao, sao chép thay đổi về mảng gốc rồi giải phóng bản sao; nếu đã pin thì kết thúc quyền truy cập theo cơ chế JVM.
- **JNI_ABORT:** không copy-back bản sao; thích hợp nếu native chỉ đọc. **Không coi JNI_ABORT là rollback thay đổi** nếu pointer thực chất trỏ thẳng vào mảng đã pin, vì những thay đổi trên vùng nhớ gốc có thể đã xảy ra.
- **JNI_COMMIT:** nếu có bản sao, commit kết quả về mảng nhưng **chưa giải phóng bản sao**; phải thực hiện release cuối cùng đúng cách. Không dùng thay cho một release kết thúc.

Với mã chỉ đọc, **JNI_ABORT** có thể tránh copy ngược không cần thiết. Với mã chỉnh sửa, chọn copy-back rõ ràng, quản lý trường hợp lỗi và tránh giữ pointer qua điểm native ownership không còn xác định.

### 3.3. Khi copy lại tốt hơn pin

Sao chép là lựa chọn hợp lý nếu native sẽ chặn khi đọc file/network, thực hiện GPU/driver call kéo dài, gọi lại Java, chia công việc cho native worker khác hoặc giữ dữ liệu qua nhiều request. Mặc dù copy tốn bandwidth, nó tách vòng đời native khỏi heap của JVM. Một số thiết kế copy một lần vào **vùng native tái sử dụng** rồi xử lý hàng nghìn phép tính trên đó; tổng chi phí còn có thể thấp hơn pin ngắn nhiều lần.

## 4. Pin và JNI critical region: tiết kiệm copy có thể đổi lấy độ trễ GC

### 4.1. GetPrimitiveArrayCritical không bảo đảm no-copy

**GetPrimitiveArrayCritical** và **ReleasePrimitiveArrayCritical** tạo một critical region cho primitive array. JVM có thể cung cấp pointer trực tiếp **nếu có thể**, nhưng vẫn được quyền dùng bản sao. Không được giả định **isCopy == JNI_FALSE** trên mọi JVM, collector, loại mảng và trạng thái heap.

Ràng buộc quan trọng trong thời gian giữ pointer critical:

- Native code **không chạy lâu** trước khi release.
- **Không gọi các JNI function khác** trong critical region.
- **Không gọi system call có thể block chờ Java thread khác**, chẳng hạn đọc một stream có dữ liệu do Java thread khác cung cấp.
- Tránh lock contention, I/O không giới hạn, callback Java, sleep hoặc gọi thư viện không biết thời gian thực thi.

Các giới hạn này tồn tại vì JVM có thể cần trì hoãn một số hoạt động GC hoặc chịu chi phí pin khác. Pin kéo dài gây ảnh hưởng đến throughput và nhất là **tail latency** của toàn ứng dụng; mức độ cụ thể khác nhau theo JVM/GC. Dù dùng một collector hỗ trợ pin hiệu quả, vẫn phải giữ critical region **ngắn và có thời gian tối đa đo được**.

### 4.2. Phác thảo đúng thứ tự sử dụng JNI critical API

Đây là **một fragment C ở bên trong JNI native method**, minh họa việc tính tổng cực ngắn. **Không phải chương trình C độc lập**; biến **env** và **input** là các tham số JNI đã có, và **GetArrayLength** được gọi **trước** khi vào critical region:

~~~c
jsize n = (*env)->GetArrayLength(env, input);
jbyte *p = (*env)->GetPrimitiveArrayCritical(env, input, NULL);
if (p == NULL) {
    return 0; // JNI có thể đã phát sinh OutOfMemoryError.
}

jlong sum = 0;
for (jsize i = 0; i < n; ++i) {
    sum += (unsigned char)p[i];
}

(*env)->ReleasePrimitiveArrayCritical(env, input, p, JNI_ABORT);
return sum;
~~~

Bên trong region chỉ thực hiện vòng lặp C không chặn và lệnh **ReleasePrimitiveArrayCritical**; không gọi JNI phụ. Trong production, với mảng quá lớn hoặc vòng lặp có thời gian không đoán trước, nên chia công việc hoặc dùng copy/direct/off-heap thay vì giữ một critical region kéo dài.

**Tối ưu bằng pin có hệ thống:** ghi nhận thời lượng critical region, GC pause p99/p999, tần suất GC, allocation pressure và hiệu quả chung. Chỉ nhìn throughput của một luồng native có thể bỏ qua hậu quả của nó đối với các thread Java khác.

## 5. Direct ByteBuffer: địa chỉ ổn định cho native, nhưng vẫn có chi phí và ownership

### 5.1. Cơ chế

**ByteBuffer.allocateDirect(size)** tạo **direct ByteBuffer**; dữ liệu backing thường ở vùng native memory bên ngoài heap Java. Java vẫn giữ một đối tượng ByteBuffer trên heap để quản lý vị trí đọc/ghi (**position**, **limit**, **capacity**) và tham chiếu đến vùng nhớ. JNI có **GetDirectBufferAddress** và **GetDirectBufferCapacity** để kiểm tra/vào vùng dữ liệu trực tiếp nếu JVM hỗ trợ.

- **GetDirectBufferAddress** trả về địa chỉ bắt đầu vùng backing của buffer được truyền, **không tự cộng Java position**. Khi xử lý một khoảng hợp lệ, truyền riêng **offset** và **length**; hoặc dùng **slice()** rồi xác định lại offset của view.
- **GetDirectBufferCapacity** nói về **capacity**, không nói về **remaining()** hay giới hạn nghiệp vụ (**limit**). Native phải kiểm tra **offset >= 0**, **length >= 0**, **offset + length <= capacity**, đồng thời Java caller phải giữ đúng window dữ liệu hợp lệ.
- **GetDirectBufferAddress** có thể trả NULL và **GetDirectBufferCapacity** có thể trả -1 với buffer không trực tiếp hoặc JVM không hỗ trợ JNI direct-buffer access. Không dereference nếu kiểm tra thất bại.
- **ByteBuffer** là mutable state. **duplicate()** tạo vị trí/limit độc lập nhưng **chia sẻ nội dung backing**, không nhân bản dữ liệu. Nhiều thread cùng đọc/ghi backing memory cần quy ước đồng bộ.
- Byte order của ByteBuffer mới mặc định là **BIG_ENDIAN**; khi chia sẻ số nguyên đa byte hoặc C struct, quyết định byte order, alignment, padding và ABI rõ ràng. **order(ByteOrder.nativeOrder())** không tự bảo đảm layout C struct được ánh xạ đúng.

Nếu native xử lý lại cùng một payload nhiều lần, direct buffer có thể giảm copy tại các lần gọi JNI sau. Nếu toàn bộ dữ liệu vừa được tạo trong **byte[]**, lệnh **direct.put(array)** vẫn copy từ heap vào direct buffer. Nếu kết quả phải trở về một **byte[]**, **direct.get(array)** lại copy ngược. Cách tối ưu là thiết kế toàn pipeline để dữ liệu được tạo, biến đổi và tiêu thụ ở vùng nhớ phù hợp, với số lần đổi định dạng/ownership nhỏ.

### 5.2. Dùng lại direct buffer và quản lý capacity

Tạo và hủy direct buffer cho từng phần tử nhỏ thường không đáng. Allocation/cleanup direct buffer thường tốn hơn heap buffer, còn một buffer pool có thể giảm allocation churn. Tuy nhiên pool quá lớn hoặc không giới hạn làm tăng native memory/RSS, fragmentation và thời gian sống của dữ liệu nhạy cảm. Có thể chọn pool có **kích thước tối đa**, chính sách giới hạn concurrency, reset **clear()/flip()** đúng và tránh trả buffer về pool khi native vẫn còn dùng địa chỉ.

Không cho native giữ pointer sau khi Java đã thả tham chiếu quản lý buffer hoặc đưa buffer vào pool cho request khác. Nếu native call bất đồng bộ, phải duy trì **strong reference** và trạng thái đang dùng cho đến khi native xác nhận kết thúc; **Reference.reachabilityFence** có thể hỗ trợ giữ reachability trong một scope đồng bộ, nhưng **không biến pointer lưu vô thời hạn ở native thành hợp lệ**.

**NewDirectByteBuffer(env, address, capacity)** là chiều ngược lại: JNI tạo Java view trên vùng native sẵn có. Java view này **không mặc nhiên sở hữu và tự free** vùng memory do C cấp phát. Bên tạo vùng nhớ phải quy định khi nào được giải phóng; truy cập view sau free có thể phá hỏng tiến trình JVM.

## 6. Off-heap allocation: kiểm soát vòng đời và chi phí triển khai

### 6.1. JNI với malloc/free hoặc thư viện C/C++

C có thể cấp phát bằng **malloc**, allocator riêng hay API của thiết bị và trả handle về Java. Mô hình này tiện khi native giữ dữ liệu giữa nhiều lần gọi, nhưng phải có giao thức sở hữu: hàm nào tạo handle, hàm nào đóng, có được chia sẻ giữa thread không, có thể cancel giữa chừng không, có được cấp phát lại khi Java view còn sống không.

Một handle kiểu **long** chỉ là số chứa địa chỉ hay token, **không bảo vệ khỏi use-after-free**. Không tự cast bất kỳ giá trị Java long nào thành pointer rồi truy cập. API production cần kiểm tra handle còn sống, giới hạn dữ liệu, kiểm soát double-close, và quy ước rõ cách xử lý khi native task thất bại trước khi close.

Nếu dùng direct ByteBuffer do C tạo, phần mô tả ownership phải sống cùng Java wrapper, chẳng hạn đối tượng **NativeBuffer** có **close()** và bảo đảm native worker đã kết thúc trước khi free. Một **Cleaner** có thể là lưới an toàn cuối cùng, **không thay thế close xác định thời điểm**.

### 6.2. Java 22+: FFM MemorySegment và Arena

**Foreign Function & Memory API** trở thành API chuẩn trong **Java 22**. Các bản Java trước dùng API incubating/preview khác nhau; ví dụ **java.lang.foreign.Arena** dưới đây cần **JDK 22+**, không thể biên dịch bằng JDK 17 chỉ nhờ thêm import.

- **Arena.ofConfined():** vùng nhớ được truy cập/đóng trong thread chủ; thích hợp cho một lời gọi native đồng bộ, có scope rõ.
- **Arena.ofShared():** cho phép chia sẻ segment giữa thread, nhưng người dùng vẫn phải đồng bộ và bảo đảm mọi hoạt động dùng pointer đã kết thúc trước khi close.
- **Arena.ofAuto():** vòng đời do cơ chế reachability quyết định; không có close chủ động, nên thời điểm thu hồi không xác định.
- **Arena.global():** có vòng đời không giới hạn đến khi tiến trình kết thúc; không thích hợp để tích lũy các allocation theo request mà không có chiến lược quản lý.

**MemorySegment** cung cấp kiểm tra phạm vi địa chỉ, alignment theo layout, khả năng truy cập theo scope và lifetime cho các thao tác Java thông qua API này. **Đó không phải sandbox bảo vệ C**: nếu một raw pointer đã đưa cho native bị truy cập sau khi arena đóng, native vẫn có thể gây lỗi nghiêm trọng bất chấp Java đã đánh dấu segment hết hạn.

**MemorySegment.ofArray(byte[])** là một segment gắn với Java heap, **không giống** một segment off-heap do Arena cấp phát. Khi dùng FFM downcall và pointer tham số, phải tuân thủ điều kiện heap/native-address của linker và API cụ thể; không coi một Java heap segment là địa chỉ native ổn định chỉ vì có MemorySegment view.

### 6.3. Chọn loại cấp phát theo vòng đời

| Vòng đời thực tế | Giải pháp thường hợp lý |
| --- | --- |
| Buffer nhỏ, xử lý Java là chính | **byte[]** hoặc heap ByteBuffer; copy nếu native cần |
| Cần native truy cập trực tiếp qua nhiều lời gọi đồng bộ | Direct ByteBuffer tái sử dụng có bound và ownership |
| Một lời gọi native với scratch memory ngắn | FFM **Arena.ofConfined()** trên JDK 22+, đóng sau khi call hoàn tất |
| Native worker nhiều thread cùng dùng vùng nhớ | **Arena.ofShared()** hoặc vùng C-owned với đồng bộ và join trước free |
| Native thư viện cấp phát và trả handle | Wrapper AutoCloseable + API **destroy** của thư viện, không để Java view sống sau free |
| Native có thể block bất định hoặc crash | Cân nhắc tách sang tiến trình khác; direct/off-heap không xử lý được tính không đáng tin của mã native |

## 7. Ví dụ hoàn chỉnh Java 17: thấy chính xác lượt copy vào và ra direct buffer

Ví dụ sau chạy **không cần thư viện native**. Nó minh họa rằng tạo direct buffer không tự làm payload gốc di chuyển sang off-heap miễn phí.

~~~java
// BufferTransferDemo.java
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;

public class BufferTransferDemo {
    public static void main(String[] args) {
        byte[] payload = "JNI FFM".getBytes(StandardCharsets.US_ASCII);
        ByteBuffer heap = ByteBuffer.wrap(payload);
        ByteBuffer direct = ByteBuffer.allocateDirect(payload.length);

        // Copy 1: Java heap -> direct buffer (thường là off-heap).
        direct.put(payload);
        direct.flip();

        // Một JNI function có thể đọc vùng direct trực tiếp ở bước này.
        // Ví dụ Java tự copy lại để mô tả đường đi của dữ liệu.
        byte[] received = new byte[direct.remaining()];
        direct.get(received); // Copy 2: direct buffer -> Java heap.

        System.out.println("heap direct = " + heap.isDirect());
        System.out.println("native direct = " + direct.isDirect());
        System.out.println("round trip = "
                + new String(received, StandardCharsets.US_ASCII));
    }
}
~~~

Biên dịch và chạy bằng JDK 17+:

~~~bash
javac BufferTransferDemo.java
java BufferTransferDemo
~~~

Stdout chính xác:

~~~text
heap direct = false
native direct = true
round trip = JNI FFM
~~~

Trong một pipeline sử dụng direct buffer **từ đầu tới cuối**, có thể bỏ cả hai phép copy minh họa nếu nguồn tạo dữ liệu và đích tiêu thụ đều làm việc trên vùng direct. Nếu Java vẫn cần xử lý dưới dạng **byte[]**, chi phí chuyển đổi phải được tính vào benchmark. Hãy tái sử dụng direct buffer đủ lớn, nhưng không dùng lại đồng thời cho request khác khi native đang đọc/ghi.

## 8. Ví dụ JNI end-to-end: so sánh region, elements và direct buffer

Ví dụ này dùng **Java 17 + JNI + C11 trên Linux**, thực hiện cùng phép tính tổng byte bằng ba lối vào khác nhau. Kết quả giống nhau; code **không chứng minh phương án nào nhanh hơn**. Khi chạy benchmark, phải đo chi phí khác nhau bằng workload thật.

**Tệp NativeMemoryTradeoff.java**:

~~~java
import java.nio.ByteBuffer;

public final class NativeMemoryTradeoff {
    static {
        System.loadLibrary("memorytradeoff");
    }

    private static native long sumWithRegion(byte[] input);
    private static native long sumWithElements(byte[] input);
    private static native long sumDirect(ByteBuffer input, int offset, int length);

    public static void main(String[] args) {
        byte[] input = {1, 2, 3, 4};

        ByteBuffer direct = ByteBuffer.allocateDirect(input.length);
        direct.put(input); // Đây vẫn là một copy heap -> direct.
        direct.flip();

        System.out.println("region=" + sumWithRegion(input));
        System.out.println("elements=" + sumWithElements(input));
        System.out.println("direct=" + sumDirect(
                direct, direct.position(), direct.remaining()));
    }
}
~~~

**Tệp memorytradeoff.c**:

~~~c
#include <jni.h>
#include <stdint.h>

static void illegal_argument(JNIEnv *env, const char *message) {
    jclass type = (*env)->FindClass(
            env, "java/lang/IllegalArgumentException");
    if (type != NULL) {
        (*env)->ThrowNew(env, type, message);
    }
}

/* Chọn copy dữ liệu từ Java thành từng chunk stack 256 byte. */
JNIEXPORT jlong JNICALL
Java_NativeMemoryTradeoff_sumWithRegion(
        JNIEnv *env, jclass ignored, jbyteArray input) {
    (void)ignored;
    jsize length = (*env)->GetArrayLength(env, input);
    jlong sum = 0;
    jbyte chunk[256];

    for (jsize start = 0; start < length; ) {
        jsize count = length - start;
        if (count > 256) {
            count = 256;
        }
        (*env)->GetByteArrayRegion(
                env, input, start, count, chunk);
        if ((*env)->ExceptionCheck(env)) {
            return 0;
        }
        for (jsize i = 0; i < count; ++i) {
            sum += (unsigned char)chunk[i];
        }
        start += count;
    }
    return sum;
}

/* JVM có thể copy HOẶC pin. Release với JNI_ABORT vì chỉ đọc. */
JNIEXPORT jlong JNICALL
Java_NativeMemoryTradeoff_sumWithElements(
        JNIEnv *env, jclass ignored, jbyteArray input) {
    (void)ignored;
    jsize length = (*env)->GetArrayLength(env, input);
    jbyte *pointer = (*env)->GetByteArrayElements(
            env, input, NULL);
    if (pointer == NULL) {
        return 0; // Chẳng hạn JNI đã phát sinh OutOfMemoryError.
    }

    jlong sum = 0;
    for (jsize i = 0; i < length; ++i) {
        sum += (unsigned char)pointer[i];
    }
    (*env)->ReleaseByteArrayElements(
            env, input, pointer, JNI_ABORT);
    return sum;
}

/* Truy cập trực tiếp vào backing memory nếu JVM hỗ trợ. */
JNIEXPORT jlong JNICALL
Java_NativeMemoryTradeoff_sumDirect(
        JNIEnv *env, jclass ignored, jobject buffer,
        jint offset, jint length) {
    (void)ignored;
    unsigned char *base = (unsigned char *)
            (*env)->GetDirectBufferAddress(env, buffer);
    jlong capacity = (*env)->GetDirectBufferCapacity(env, buffer);

    if (base == NULL || capacity < 0 ||
            offset < 0 || length < 0 ||
            (jlong)offset + (jlong)length > capacity) {
        illegal_argument(env, "Invalid direct buffer window");
        return 0;
    }

    jlong sum = 0;
    for (jint i = 0; i < length; ++i) {
        sum += base[offset + i];
    }
    return sum;
}
~~~

Trên **Linux**, cần đặt **JAVA_HOME** về thư mục JDK 17+ có **include/jni.h** và cài trình biên dịch GCC. Trong cùng thư mục chứa hai tệp nguồn:

~~~bash
javac -h . NativeMemoryTradeoff.java
gcc -std=c11 -O2 -fPIC -shared \
  -I"$JAVA_HOME/include" -I"$JAVA_HOME/include/linux" \
  memorytradeoff.c -o libmemorytradeoff.so
java -Djava.library.path=. NativeMemoryTradeoff
~~~

Stdout trên JVM hỗ trợ JNI direct buffer:

~~~text
region=10
elements=10
direct=10
~~~

**Vì sao ví dụ có giá trị:** region chuyển dữ liệu thành chunk C; elements dùng pointer mà JVM có thể cấp qua copy hoặc pin; direct cho phép JNI tính tổng trên backing memory của ByteBuffer. **direct.put(input)** phía Java vẫn là copy nên nếu benchmark chỉ đo **sumDirect** mà bỏ chi phí **put**, kết luận end-to-end sẽ sai. Cả ba hàm đều thực thi đồng bộ và không giữ pointer sau khi return. Không được biến **base** thành biến toàn cục rồi dùng sau khi Java đã bỏ buffer.

Trong phần code JNI này, **sumDirect** kiểm tra kích thước vùng backing (**capacity**), nhưng Java caller còn chịu trách nhiệm bảo đảm **offset, length** khớp window dữ liệu có nghĩa (**position, limit**) và không bị thread khác sửa giữa chừng. Với dữ liệu ngoài ví dụ nhỏ, hàm tổng dùng **jlong** chỉ phù hợp trong phạm vi không tràn số; cần thiết kế overflow/semantic result theo đặc tả thực tế.

## 9. Ví dụ FFM trên Java 22+: arena và giải phóng theo scope

Đoạn dưới là **chương trình độc lập cho JDK 22+**, sử dụng API chuẩn **java.lang.foreign**; không gọi function native nên không cần cấu hình linker. Các FFM downcall cần xem quyền native access của JDK/module và cờ **--enable-native-access** tương ứng.

~~~java
// NativeArenaDemo.java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

public class NativeArenaDemo {
    public static void main(String[] args) {
        try (Arena arena = Arena.ofConfined()) {
            MemorySegment region = arena.allocate(
                    ValueLayout.JAVA_LONG.byteSize(),
                    ValueLayout.JAVA_LONG.byteAlignment());
            region.set(ValueLayout.JAVA_LONG, 0, 42L);

            System.out.println("bytes=" + region.byteSize());
            System.out.println("value=" + region.get(
                    ValueLayout.JAVA_LONG, 0));
        }
        // Scope kết thúc: region không còn hợp lệ cho truy cập Java.
    }
}
~~~

Lệnh với JDK 22+:

~~~bash
javac NativeArenaDemo.java
java NativeArenaDemo
~~~

Stdout:

~~~text
bytes=8
value=42
~~~

**Không đóng arena trước khi native dùng xong.** Nếu truyền địa chỉ từ segment cho một lời gọi native **bất đồng bộ** và thoát khỏi **try**, C có thể vẫn truy cập pointer sau khi memory đã được giải phóng. Muốn dùng shared arena hoặc giữ region lâu hơn, phải có cơ chế báo hoàn thành, join/cancel, quyền truy cập giữa thread và cleanup xác định.

## 10. Mô hình chi phí: nhìn toàn đường dữ liệu thay vì một phép copy

Một công thức suy nghĩ hữu ích:

**Tổng thời gian ≈ chi phí crossing + chi phí cấp phát/thu hồi + tổng chi phí copy + thời gian native xử lý + chi phí đồng bộ/cache + tác động GC.**

Với một lượt copy kích thước **N** và bandwidth hữu hiệu **B**, thành phần lý tưởng khoảng **N/B**, nhưng thực tế phụ thuộc cache, NUMA, độ song song, loại bộ nhớ, cách copy và tình trạng máy. Vì vậy không dùng một ngưỡng cố định kiểu “trên 4 KB luôn chọn direct” cho mọi ứng dụng.

Thực tế có những kịch bản khác nhau:

| Trường hợp | Quyết định ban đầu nên thử | Lý do |
| --- | --- | --- |
| Payload rất nhỏ, gọi native không thường xuyên | **byte[] + region/Elements** có release đúng | Cấp phát direct/arena và quản lý lifecycle có thể đắt hơn một copy |
| Payload lớn, native đọc nhanh, Java không cần giữ snapshot | Benchmark **direct được tái sử dụng** so với **Elements** | Tiết kiệm copy có thể đáng kể nếu nguồn/đích làm việc trực tiếp trên vùng nhớ ấy |
| Native xử lý kéo dài, chờ I/O hoặc callback | **Copy sang vùng native có owner riêng**, hoặc direct/off-heap với hợp đồng lifetime | Tránh giữ array critical khi code block và tránh pointer heap sống lâu |
| Hàng nghìn native call nhỏ mỗi request | Gom batch nếu API cho phép | Giảm overhead crossing có thể hiệu quả hơn đổi copy thành pin |
| Native trả kết quả là C-owned block | Wrapper + owner/close; cân nhắc **NewDirectByteBuffer** hoặc MemorySegment view | Tránh copy-back khi Java có thể xử lý trực tiếp nhưng phải quản lý free |
| Nhiều thread cùng truy cập | Per-thread buffer hoặc shared memory có đồng bộ | Tránh data race và reuse buffer khi call còn chạy |
| Ưu tiên p99, GC nhạy cảm | Đo **critical-region duration** và GC pause; cân nhắc copy | Một chút copy có thể đổi lại latency ổn định hơn |
| Bộ nhớ hạn chế, tải lớn | Bounded direct/off-heap pool và giới hạn in-flight | Native memory quá mức có thể làm tiến trình bị kill dù Java heap còn chỗ |

**Đo riêng chuyển đổi dữ liệu**: nếu native library nhận cấu trúc C cần packing lại các field từ đối tượng Java, chi phí serialization, byte order conversion, alignment và allocate vẫn tồn tại dù buffer là direct. “Không copy bytes” không đồng nghĩa “không có chuyển đổi dữ liệu”.

### 10.1. Điểm cần chú ý ở CPU và GC

- **Cache locality:** liên tục copy dữ liệu có thể đẩy dữ liệu hữu ích khỏi cache, nhưng copy tuần tự tối ưu cũng có thể nhanh và đơn giản hơn nhiều lần truy cập rời rạc.
- **Allocation frequency:** direct allocation từng request có thể tăng native memory pressure và kéo dài thời gian thu hồi; dùng lại buffer thường hữu ích, nhưng pool phải có giới hạn.
- **GC interference:** pin có thể làm khó việc di chuyển object/collection tùy JVM và collector; metric quan trọng là **GC pause p99**, không chỉ average JNI call time.
- **Thread contention:** một shared direct buffer không tự thread-safe; data race hoặc lock contention có thể xóa sạch lợi ích giảm copy.
- **Native library internals:** thư viện có thể tự copy dữ liệu hoặc tạo buffer nội bộ. Chỉ benchmark phần Java wrapper mà không xem end-to-end sẽ bỏ qua chi phí đó.

## 11. Dùng tài nguyên an toàn: ownership quan trọng hơn tối ưu vi mô

Một bảng owner nên được viết rõ ngay trong API thiết kế:

| Bộ nhớ và API | Ai cấp phát? | Khi nào được giải phóng? | Trường hợp không an toàn |
| --- | --- | --- | --- |
| **byte[]** + **GetByteArrayElements** | JVM sở hữu mảng, JNI có thể tạo bản sao | Release pointer bằng đúng JNI API; Java GC quản lý mảng | Giữ pointer sau release; quên release; native dùng mảng ngoài hợp đồng |
| **GetPrimitiveArrayCritical** | JVM | Release critical ngay sau đoạn xử lý ngắn | Gọi I/O/lock dài khi đang critical |
| **ByteBuffer.allocateDirect** | JVM/NIO direct buffer | Khi cơ chế quản lý của buffer xác định có thể thu hồi; thời điểm không nên giả định tức thì | Native async giữ address khi không còn Java owner; trả buffer về pool quá sớm |
| **malloc + NewDirectByteBuffer** | Thư viện C/native owner | Native owner free sau khi tất cả view/call hoàn tất | Java view vẫn truy cập sau free |
| **FFM Arena.ofConfined/ofShared** | Arena | Khi close sau khi tất cả tác vụ dùng segment đã kết thúc | Close khi C vẫn giữ pointer; truy cập sai thread trong confined arena |

Khi native xử lý bất đồng bộ, quy trình tốt thường là **allocate → submit → native acknowledgment → release**. Timeout bên gọi chỉ nói rằng caller không chờ nữa; không cho phép tự động free vùng nhớ mà native worker vẫn dùng. Nếu thư viện không hỗ trợ cancel/join đáng tin, cân nhắc cách ly trong tiến trình khác. Không cố dừng luồng C tùy tiện khi nó đang giữ pointer/lock.

**Native memory không miễn phí vì nằm ngoài heap.** Giới hạn **-Xmx** chủ yếu kiểm soát Java heap, không giới hạn tổng RSS. **-XX:MaxDirectMemorySize** chủ yếu áp dụng cho nhóm allocation direct-buffer NIO do JVM theo dõi, không phải mức trần tuyệt đối cho **malloc** của bên thứ ba hay mọi FFM allocation. Java object wrapper, metadata, thread stack, code cache và các vùng native khác vẫn tiêu thụ bộ nhớ.

**Các phép đo hữu ích:** Java heap used, direct buffer count/total capacity/memory used qua **BufferPoolMXBean** hoặc JMX, native memory tracking (NMT) nếu bật, RSS/container memory, GC pause, native allocation count/size, số pointer/handle chưa đóng, và số task native còn chạy. NMT không nhất thiết ghi nhận đầy đủ các allocation thủ công của thư viện bên ngoài JVM. Đừng cộng các metric khác hệ quy chiếu một cách máy móc để suy ra tổng footprint.

## 12. Benchmark đúng cách để chọn chiến lược

Một so sánh có giá trị cần **cùng workload, cùng payload và cùng mức độ đúng đắn**:

1. **Xác định đường dữ liệu thật:** nguồn Java heap, network, mapped file hay native allocator? Kết quả dùng tiếp trong Java hay ở C? Có bao nhiêu lần native call trên mỗi payload?
2. **Định nghĩa bốn phương án:** copy qua region, Elements (có thể copy/pin), critical region **chỉ khi xử lý ngắn và hợp lệ**, direct/off-heap reuse. Không giả định phương án Elements chắc chắn pin.
3. **Đo end-to-end và từng thành phần:** allocate, heap-to-direct staging, JNI crossing, native work, copy-back, cleanup; tách thời gian tạo pool lần đầu và hiệu quả steady-state.
4. **Dùng JMH hoặc harness đáng tin cậy:** warmup JVM/JIT, đủ nhiều lần đo và nhiều fork; giữ workload không bị dead-code elimination bằng cách dùng kết quả. Nếu đo JNI/GC, quan sát cả metric từ native và toàn JVM.
5. **Thay đổi dữ liệu và concurrency:** nhiều kích thước payload (nhỏ/trung bình/lớn), số worker, tần suất gọi, batch size, mức direct memory pressure; dùng dữ liệu thực thay vì trường hợp cache quá thuận lợi.
6. **Theo dõi độ trễ và tài nguyên:** throughput, p50/p95/p99, allocation/GC, RSS/direct capacity, cạn pool, lỗi native memory; thử chạy liên tục để phát hiện leak.
7. **Xác nhận correctness:** checksum/byte-by-byte với input có byte âm theo Java signed byte, sửa đổi trực tiếp và copy-back, boundary offset/length, concurrent access, lifetime và thao tác cancel.

**Không dùng** một vòng **System.nanoTime()** chạy vài lần làm kết luận tổng quát. Không so sánh một hàm **sumDirect** bỏ qua **direct.put(byte[])** với **sumWithRegion** tính đủ copy; phép đo đó so sánh hai pipeline khác nhau. Không diễn giải **isCopy** của một máy chạy là tính năng bảo đảm trên các JVM/GC khác.

Khi benchmark thay đổi collector hoặc phiên bản JDK, cần xem lại giả định pin/GC: bản thân API JNI không bảo đảm một chiến lược memory access cố định cho tất cả implementation. Với FFM, cũng phải kiểm tra JDK version và tùy chọn native access khi thử downcall.

## 13. Các lỗi thường gặp

| Lỗi hiểu/cách làm | Vì sao sai hoặc nguy hiểm | Hướng sửa |
| --- | --- | --- |
| “**GetByteArrayElements** luôn zero-copy” | JVM có thể tạo copy | Đọc hợp đồng JNI, kiểm tra và release đúng, benchmark |
| “**GetPrimitiveArrayCritical** luôn pin” | JNI vẫn có thể trả bản sao | Không dựa correctness vào việc pin và giữ region cực ngắn |
| Đọc file/network trong critical region | Có thể block và cản GC | Copy ra vùng native hoặc direct buffer rồi mới I/O |
| **Get...Elements** mà không **Release** | Rò tài nguyên hoặc kéo dài pin | Dùng đường cleanup bao phủ mọi nhánh |
| Dùng **JNI_ABORT** để hoàn tác ghi đã thực hiện | Nếu pointer pin vào mảng thật, dữ liệu đã bị sửa | Không viết vào vùng chỉ đọc; dùng bản sao riêng khi cần rollback |
| “**allocateDirect** = không copy từ **byte[]**” | **put(byte[])** vẫn thực hiện copy | Tính đủ các bước từ nguồn đến đích |
| Nhầm **capacity** và **remaining** | Native có thể xử lý byte ngoài window hợp lệ | Truyền offset/length và kiểm tra ranh giới |
| Giữ native address sau khi trả buffer về pool | Request khác có thể ghi đè hoặc buffer được thu hồi | Owner/lease và native completion acknowledgment |
| Giải phóng C malloc khi **NewDirectByteBuffer** view còn dùng | Dangling pointer/use-after-free | Định nghĩa owner và close sau khi hết view |
| Đóng FFM arena trong khi native worker chưa kết thúc | Java check scope không bảo vệ C khỏi pointer chết | Await/join/cancel xong rồi mới close |
| Tạo direct buffer vô hạn, chỉ nhìn **-Xmx** | Off-heap RSS tăng không kiểm soát | Giới hạn pool/direct memory, đo RSS và BufferPoolMXBean |
| Chia sẻ một ByteBuffer mutable position giữa thread | Data race trong position/limit và backing memory | Per-thread view có đồng bộ, hoặc chủ động cấp vùng riêng |
| Benchmark JNI riêng nhưng bỏ staging/cleanup | Kết luận sai với pipeline thực | Đo end-to-end, GC tail latency và footprint |

## 14. Checklist quyết định triển khai

Trước khi đổi **byte[]** sang pin, direct buffer hoặc off-heap memory, xác minh:

- **Nguồn, đích và định dạng:** ở heap hay native ngay từ đầu; có phải copy/serialize thêm bước nào?
- **Thời lượng native giữ dữ liệu:** trong một JNI call ngắn hay bất đồng bộ, chờ I/O, giữ pointer dài hạn?
- **Giao thức ownership:** ai cấp phát, ai giải phóng, khi nào xác nhận kết thúc, handle có thể bị close trùng không?
- **Ngữ nghĩa sửa dữ liệu:** native chỉ đọc hay cần copy-back; **JNI_ABORT**, **JNI_COMMIT**, **mode 0** có được chọn phù hợp?
- **Ràng buộc GC:** critical region có hoàn toàn ngắn, không blocking và không gọi JNI khác hay không?
- **Window và layout:** position/limit/capacity, byte order, padding, alignment, bounds và độ rộng pointer có nhất quán?
- **Đo hiệu năng:** có kết quả p95/p99, throughput, copy bytes, memory footprint và GC thực tế chưa?
- **Giới hạn tài nguyên:** direct/off-heap pool có bound và cleanup, native async có acknowledgment?
- **Khả năng di chuyển phiên bản:** direct ByteBuffer/JNI dùng trên Java 17+, FFM Arena/MemorySegment chuẩn từ Java 22; đã kiểm tra yêu cầu native access của JDK mục tiêu?
- **Phương án đơn giản có đủ tốt?** Nếu copy đã đáp ứng latency/throughput và an toàn, không thêm ownership phức tạp chỉ vì một lời hứa zero-copy chưa đo được.

**Kết luận kỹ thuật:** copy tiêu tốn bandwidth nhưng tạo ranh giới ownership rõ; pin có thể giảm copy nhưng không được giữ lâu hoặc dựa vào làm bảo đảm; direct buffer giảm staging tại một số biên I/O khi được tái sử dụng đúng; off-heap/FFM cho phép quản lý native memory chủ động nhưng đặt trách nhiệm lifecycle lên thiết kế. Quyết định tốt dựa trên **toàn pipeline, mức độ an toàn của con trỏ và kết quả benchmark thực tế**, không dựa vào riêng tên API.

## 15. Tài liệu chuẩn để đối chiếu

- [JNI Specification — Array Access, GetPrimitiveArrayCritical và Release modes](https://docs.oracle.com/en/java/javase/22/docs/specs/jni/functions.html)
- [JNI Specification — NIO direct buffer access](https://docs.oracle.com/en/java/javase/25/docs/specs/jni/functions.html)
- [Java 17 ByteBuffer API — direct vs non-direct](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html)
- [Java 22 java.lang.foreign API — MemorySegment và Arena](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/package-summary.html)
- [Java 17 java launcher — MaxDirectMemorySize](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html)
