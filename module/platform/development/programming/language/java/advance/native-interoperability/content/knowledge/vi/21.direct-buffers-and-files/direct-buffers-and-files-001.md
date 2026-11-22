# ByteBuffer trực tiếp và sự khác nhau giữa đối tượng Java với vùng nhớ nền

`java.nio.ByteBuffer` là **một đối tượng Java cung cấp cách nhìn và thao tác lên một vùng các byte**. Với `ByteBuffer.allocateDirect(n)`, đối tượng `ByteBuffer` vẫn là một Java object được JVM quản lý, nhưng **nội dung byte** có thể nằm ở một vùng nhớ nền (*backing storage*) ngoài Java heap, phù hợp để tương tác với I/O hoặc thư viện native.

Phân biệt hai tầng này quyết định cách viết code đúng:

- **Đối tượng ByteBuffer** giữ các metadata và trạng thái truy cập: `position`, `limit`, `capacity`, `mark`, read-only, byte order và liên kết tới vùng nền.
- **Vùng nhớ nền** chứa các byte thật, có thể là mảng Java, native memory do JVM quản lý, file mapping hoặc allocation do một thư viện C sở hữu.
- **Ownership/lifetime** nói rõ ai có quyền giải phóng vùng nền, khi nào việc giải phóng hợp lệ, và có còn người dùng Java/native nào đang tham chiếu tới vùng đó hay không.

Vì vậy, hai `ByteBuffer` objects có thể **khác nhau về identity nhưng chia sẻ cùng bytes**; ngược lại, một Java ByteBuffer object có thể còn tồn tại dù nguồn native backing memory mà nó bọc đã bị giải phóng sai cách. Direct buffer là công cụ truy cập, **không tự động là một hợp đồng ownership**.

Bài này thuộc nhóm **Bộ đệm và tệp** của Java Advance — native-interoperability. Nội dung tập trung vào direct/heap, NIO cursor, alias qua `duplicate()/slice()/asReadOnlyBuffer()`, copy so với view, bộ nhớ ngoài heap và GC, JNI direct-buffer APIs, native-owned buffer, file mapping, FFM, threading, performance và chương trình ví dụ **Java 17+ và C11**.

## 1. Sơ đồ hai tầng: wrapper và backing bytes

```text
             Java heap                    vùng byte nền
  +--------------------------------+     +---+---+---+---+---+---+---+---+
  | ByteBuffer object A            |     |10 |20 |30 |40 | 0 | 0 | 0 | 0 |
  |  capacity = 8                  |     +---+---+---+---+---+---+---+---+
  |  position = 1                  |                   ^
  |  limit = 4                     |                   |
  |  isDirect() = true             |                   |
  |  metadata + backing reference ---------+
  +--------------------------------+
```

Sơ đồ chỉ thể hiện mối quan hệ khái niệm, **không mô tả private fields hoặc layout thật của `DirectByteBuffer`**. JDK có quyền thay đổi cách lưu handle, attachment hoặc cleanup. Điều quan trọng là các tính chất public API:

| Khái niệm | Ý nghĩa |
| --- | --- |
| `capacity()` | Tổng số byte **view này** có thể đánh chỉ số |
| `position()` | Chỉ số đọc/ghi tương đối tiếp theo |
| `limit()` | Điểm cuối không bao gồm của cửa sổ truy cập |
| `remaining()` | `limit - position` |
| `isDirect()` | Có phải direct buffer theo Java NIO không |
| `isReadOnly()` | View này có cấm ghi qua các Java NIO APIs không |
| `order()` | Cách diễn giải các giá trị đa byte như `int`/`long` |
| Vùng nền | Bytes thực tế và cơ chế sở hữu/giải phóng của chúng |

**Object identity không phải backing identity.** Dùng `a == b` để so sánh hai Java ByteBuffer objects có thể cho kết quả `false` dù chúng cùng đọc/ghi một vùng byte.

### 1.1. Heap buffer và direct buffer

| Tính chất | Heap ByteBuffer | Direct ByteBuffer thông thường |
| --- | --- | --- |
| Tạo bằng | `ByteBuffer.allocate(n)` hoặc `wrap(byte[])` | `ByteBuffer.allocateDirect(n)` |
| Java wrapper | Java heap object | **Vẫn là Java heap object** |
| Chứa bytes | Thường mảng `byte[]` trong heap | Thường native/off-heap allocation |
| `isDirect()` | `false` | `true` |
| `hasArray()` | Thường true với writable array backing | False |
| Native I/O | Có thể cần buffer copy trung gian | JVM cố gắng thao tác trực tiếp hơn |
| Giải phóng vùng nền | GC quản lý byte array | Theo JVM/allocator của nguồn direct memory |
| Allocation cost | Thường thấp hơn | Thường cao hơn; nên benchmark/pool nếu có lợi |

Javadoc nói direct buffer **có thể** chứa dữ liệu ngoài ordinary garbage-collected heap, không hứa implementation nào cũng dùng đúng một cơ chế malloc hay cleaner. Tránh viết code phụ thuộc tên class triển khai hoặc reflection truy cập private address/cleaner.

### 1.2. Cấp phát và quyền truy cập mảng

```java
ByteBuffer heap = ByteBuffer.allocate(8);
ByteBuffer wrapped = ByteBuffer.wrap(new byte[8]);
ByteBuffer direct = ByteBuffer.allocateDirect(8);

System.out.println(heap.isDirect());    // false
System.out.println(wrapped.isDirect()); // false
System.out.println(direct.isDirect());  // true
System.out.println(direct.hasArray());  // false
```

Đây là **đoạn trong một Java method**, không phải file độc lập.

`hasArray()` hỏi có thể truy cập một Java backing array không; **`hasArray() == false` không chứng minh direct**, vì read-only heap view cũng không bắt buộc expose array. Nếu `hasArray()` true, `array()` và `arrayOffset()` mới giúp tính vị trí trong array. Nếu muốn biết direct, dùng `isDirect()`.

## 2. Cursor là metadata; `flip()` và `clear()` không phải copy/free

Một ByteBuffer có bốn khái niệm cursor chính: `capacity`, `position`, `limit`, `mark`. Thông thường:

```text
0 <= position <= limit <= capacity
         |--------------|
          remaining bytes
```

Các thao tác:

| API | Tác dụng với cursor | Có thay dữ liệu byte? |
| --- | --- | --- |
| `position(n)` | Đặt position | Không |
| `limit(n)` | Đặt limit | Không |
| `flip()` | `limit = old position; position = 0` | Không |
| `clear()` | `position = 0; limit = capacity` | **Không xóa bytes** |
| `rewind()` | `position = 0` | Không |
| `mark()/reset()` | Lưu/khôi phục position | Không |
| `get()/put()` tương đối | Di chuyển position theo số bytes | Có đọc/ghi bytes |
| `get(index)/put(index,value)` tuyệt đối | Không đổi position | Có đọc/ghi tại index |
| `compact()` | Chuyển bytes còn lại về đầu và cập nhật cursor | **Có di chuyển/copy bytes** |

Ví dụ:

```java
ByteBuffer input = ByteBuffer.allocateDirect(8);

input.put((byte) 10);
input.put((byte) 20);
input.put((byte) 30);

System.out.println(input.position()); // 3
System.out.println(input.limit());    // 8

input.flip();
System.out.println(input.position()); // 0
System.out.println(input.limit());    // 3
System.out.println(input.remaining());// 3
```

Đây là đoạn code Java trong method. `flip()` **không chuyển ba bytes đi đâu**: nó chỉ đặt view từ trạng thái producer đang ghi sang consumer chuẩn bị đọc. `clear()` tiếp theo mở window để tái sử dụng toàn capacity, nhưng các byte cũ vẫn có thể ở đó. **`clear()` không bảo mật để xóa thông tin nhạy cảm.**

Trong file/network code, đừng dùng `capacity()` như “số byte payload hợp lệ”. Nếu đã đọc 3 bytes vào buffer sức chứa 8192, payload có thể chỉ 3 bytes; `remaining()` sau `flip()` mới giúp phản ánh cửa sổ đã ghi.

## 3. Một vùng nền, nhiều đối tượng view: aliasing

### 3.1. `duplicate()` tạo object và cursor mới, không copy bytes

```java
ByteBuffer parent = ByteBuffer.allocateDirect(8);
parent.put(1, (byte) 20);

ByteBuffer duplicate = parent.duplicate();

System.out.println(parent == duplicate); // false

duplicate.put(1, (byte) 25);
System.out.println(parent.get(1));       // 25

duplicate.position(4);
System.out.println(parent.position());   // 0
```

Hai objects có bytes chung: thay đổi byte qua `duplicate` thấy được từ `parent`. Nhưng position độc lập. `duplicate()` phù hợp khi cần hai readers có cursor riêng, **không** phù hợp để tạo snapshot bất biến.

### 3.2. `slice()` tạo cửa sổ với offset 0 mới

```java
ByteBuffer parent = ByteBuffer.allocateDirect(8);

parent.put(2, (byte) 30);
parent.position(2);
parent.limit(5);

ByteBuffer view = parent.slice();

System.out.println(view.capacity()); // 3
System.out.println(view.position()); // 0

view.put(0, (byte) 99);
System.out.println(parent.get(2));   // 99
```

Slice chỉ bao gồm byte indices 2, 3, 4 của parent. Offset 0 của slice nằm ở byte index 2 của parent. Từ góc nhìn JNI, vùng nền cho slice vẫn direct, nhưng **địa chỉ bắt đầu của view** có thể đã được offset, khác địa chỉ của parent.

Thay đổi position/limit của parent **sau khi slice được tạo** không tự thay đổi độ dài hay cursor của slice.

### 3.3. Read-only view vẫn dùng chung dữ liệu

```java
ByteBuffer parent = ByteBuffer.allocateDirect(2);
ByteBuffer readOnly = parent.asReadOnlyBuffer();

System.out.println(readOnly.isReadOnly()); // true

parent.put(0, (byte) 9);
System.out.println(readOnly.get(0));       // 9
```

View read-only chặn ghi qua Java NIO API của chính view đó, nhưng parent writable vẫn có thể sửa backing bytes. Đây không phải “snapshot immutable”. Nếu thư viện C nắm pointer writable của cùng vùng nền, Java read-only metadata không buộc C tuân theo. Không dùng read-only view làm ranh giới bảo mật với native code không tin cậy.

### 3.4. Copy thật phải cấp phát dữ liệu mới

```java
ByteBuffer direct = ByteBuffer.allocateDirect(3);
direct.put(0, (byte) 1);
direct.put(1, (byte) 2);
direct.put(2, (byte) 3);

ByteBuffer reader = direct.duplicate();
reader.position(0);
reader.limit(3);

byte[] snapshot = new byte[reader.remaining()];
reader.get(snapshot);

direct.put(0, (byte) 9);
System.out.println(snapshot[0]); // 1
System.out.println(direct.get(0)); // 9
```

Đây là **copy độc lập**: snapshot không còn alias với direct buffer. Chấp nhận chi phí copy nếu caller phải dùng bytes sau khi owner buffer gốc bị release/reuse hoặc phải giữ trạng thái bất biến.

## 4. Ví dụ Java 17+ hoàn chỉnh: wrapper khác, backing chung

Chương trình chính **không cần JNI, C, FFM hay preview**. Mọi kết quả là số hoặc chuỗi cố định từ thao tác buffer, không dựa vào địa chỉ raw hay thời gian GC.

### 4.1. File `DirectBackingDemo.java`

```java
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.ReadOnlyBufferException;
import java.util.Arrays;

public final class DirectBackingDemo {
    private DirectBackingDemo() {}

    public static void main(String[] args) {
        ByteBuffer heap = ByteBuffer.allocate(6);
        ByteBuffer direct = ByteBuffer.allocateDirect(8);

        System.out.println("heap-direct=" + heap.isDirect());
        System.out.println("direct-direct=" + direct.isDirect());
        System.out.println("direct-has-array=" + direct.hasArray());

        direct.put(0, (byte) 10);
        direct.put(1, (byte) 20);
        direct.put(2, (byte) 30);
        direct.put(3, (byte) 40);

        ByteBuffer alias = direct.duplicate();
        System.out.println("same-object=" + (direct == alias));

        alias.put(1, (byte) 25);
        System.out.println(
            "shared-byte=" + Byte.toUnsignedInt(direct.get(1)));

        alias.position(4);
        System.out.println(
            "direct-position-after-alias=" + direct.position());

        direct.position(1);
        direct.limit(4);
        ByteBuffer slice = direct.slice();
        System.out.println("slice-capacity=" + slice.capacity());

        slice.put(1, (byte) 33);
        System.out.println(
            "slice-updated-origin="
                + Byte.toUnsignedInt(direct.get(2)));
        System.out.println("parent-position=" + direct.position());

        ByteBuffer readOnly = direct.asReadOnlyBuffer();
        System.out.println("read-only=" + readOnly.isReadOnly());

        direct.put(2, (byte) 44);
        System.out.println(
            "read-only-sees="
                + Byte.toUnsignedInt(readOnly.get(2)));

        try {
            readOnly.put(2, (byte) 99);
        } catch (ReadOnlyBufferException expected) {
            System.out.println("read-only-write=blocked");
        }

        ByteBuffer transport = ByteBuffer.allocateDirect(5);
        transport.put((byte) 1)
                 .put((byte) 2)
                 .put((byte) 3);

        System.out.println(
            "before-flip="
                + transport.position() + "/" + transport.limit());

        transport.flip();
        System.out.println(
            "after-flip="
                + transport.position() + "/" + transport.limit());

        byte[] snapshot = new byte[transport.remaining()];
        transport.get(snapshot);
        System.out.println("snapshot=" + Arrays.toString(snapshot));

        transport.put(0, (byte) 9);
        System.out.println("snapshot-first=" + snapshot[0]);
        System.out.println(
            "direct-first="
                + Byte.toUnsignedInt(transport.get(0)));

        ByteBuffer endian = ByteBuffer.allocateDirect(4);
        endian.order(ByteOrder.LITTLE_ENDIAN);
        endian.putInt(0, 0x01020304);

        System.out.println(
            "little-endian="
                + Byte.toUnsignedInt(endian.get(0)) + " "
                + Byte.toUnsignedInt(endian.get(1)) + " "
                + Byte.toUnsignedInt(endian.get(2)) + " "
                + Byte.toUnsignedInt(endian.get(3)));
    }
}
```

Giải thích:

1. `heap` là non-direct, `direct` là direct; direct thường không expose Java `byte[]`.
2. `duplicate()` không copy backing, nên ghi byte 1 qua alias hiện ra trong parent.
3. `alias.position(4)` không dịch chuyển `direct.position()`.
4. `direct.position(1), limit(4)` tạo slice có capacity 3; offset 1 của slice trỏ tới byte 2 của root.
5. Read-only view đọc thấy byte 44 do parent vừa ghi nhưng từ chối `put`.
6. `flip()` đổi cursor từ 3/5 thành 0/3; snapshot tạo từ `byte[]` có dữ liệu độc lập.
7. `putInt` với `LITTLE_ENDIAN` tạo bytes 4 3 2 1 theo thứ tự index.

### 4.2. Biên dịch, chạy và kết quả

```bash
javac DirectBackingDemo.java
java DirectBackingDemo
```

**Stdout xác định của chương trình:**

```text
heap-direct=false
direct-direct=true
direct-has-array=false
same-object=false
shared-byte=25
direct-position-after-alias=0
slice-capacity=3
slice-updated-origin=33
parent-position=1
read-only=true
read-only-sees=44
read-only-write=blocked
before-flip=3/5
after-flip=0/3
snapshot=[1, 2, 3]
snapshot-first=1
direct-first=9
little-endian=4 3 2 1
```

Không có dòng in địa chỉ raw: một native address thường thay đổi theo JVM, allocation, ASLR và quá trình chạy; không phải output ổn định để kiểm tra “cùng vùng nền”. **Thử ghi qua một view và đọc lại qua view kia** là phép thử alias rõ ràng hơn.

## 5. Tại sao direct có lợi cho native I/O nhưng không bảo đảm end-to-end zero-copy?

Javadoc `ByteBuffer` nêu rằng JVM sẽ **cố gắng tốt nhất** (best effort) thực hiện native I/O trực tiếp với direct buffers để tránh copy tới/từ buffer trung gian. Không có bảo đảm rằng mọi đường dữ liệu cuối cùng đều zero-copy:

- OS có thể vẫn copy giữa kernel và user space.
- TLS, mã hóa, nén, framing, checksum và protocol transformations có thể cần copy/xử lý khác.
- Một native library có thể chủ động copy bytes sang một buffer khác.
- Một tầng ứng dụng Java có thể chuyển encoding hoặc tạo `byte[]` snapshot.
- Direct allocation/deallocation thường tốn chi phí hơn heap buffer allocation.
- Với dữ liệu nhỏ, lợi ích không đủ bù overhead; đo benchmark thực tế trên workload rồi mới tối ưu.

Một `ByteBuffer.allocateDirect(8192)` chỉ là **vùng chứa tối đa 8192 bytes**; chưa chắc 8192 bytes đều là payload hợp lệ. Channel I/O thường chỉ thao tác `remaining()` bytes giữa position và limit. C code có raw pointer **không tự được NIO cập nhật cursor hay protocol length**.

### 5.1. FileChannel và trạng thái buffer

```java
// Ví dụ cấu trúc: đã có FileChannel channel mở để đọc.
ByteBuffer buffer = ByteBuffer.allocateDirect(8192);

int n = channel.read(buffer);
if (n > 0) {
    buffer.flip(); // Đọc đúng n bytes vừa được ghi vào buffer.
    while (buffer.hasRemaining()) {
        byte value = buffer.get();
        // Xử lý value theo giao thức ứng dụng.
    }
    buffer.clear(); // Reset cursor, KHÔNG zero bytes.
}
```

Đây là **code minh họa**, không phải chương trình độc lập. Với partial protocol frames, buffer không nên bị `clear()` tùy tiện nếu còn bytes chưa giải mã; có thể dùng `compact()` để giữ phần chưa tiêu thụ.

## 6. Vòng đời: ai giữ vùng nhớ nền còn hợp lệ?

### 6.1. Buffer từ `allocateDirect`

Với `ByteBuffer.allocateDirect(n)`, phần memory backing được JVM/implementation quản lý. Trên các JVM thông dụng, dọn native memory có liên quan đến reachability/cleaner và có thể diễn ra trễ hơn thời điểm local variable hết scope.

**Không có `ByteBuffer.close()` chuẩn ở Java 17** cho loại buffer này. Các thao tác dưới đây đều không phải cách release an toàn:

- Gọi C `free(address)` trên một vùng nền do JVM cấp phát.
- Truy cập cleaner/`Unsafe` nội bộ bằng reflection để ép deallocation.
- Gán `buffer = null` rồi giả định native bytes lập tức được trả lại OS.
- Dựa vào `System.gc()` như một API có deadline.
- Giữ `slice` trong cache nhưng kỳ vọng backing allocation của parent đã được dọn.

Một `slice` 10 byte có thể còn giữ vùng backing direct buffer 64 MiB. Đây là lý do một cache nhỏ theo **payload size** chưa chắc nhỏ theo **backing allocation size**.

### 6.2. Native C giữ pointer sau khi Java method đã return

Giả sử Java gọi một native function “start async” và truyền direct buffer. Nếu C lưu pointer vào một hàng đợi native rồi return ngay, **GC không nhìn thấy một raw C pointer như Java strong reference**. Lúc đó phải có một owner Java giữ ByteBuffer/view reachable, đồng thời bảo đảm buffer không bị reuse/free cho tới khi C báo completion/cancellation thật.

Đừng hiểu `Reference.reachabilityFence(buffer)` ở cuối phương thức submit là đủ cho việc native asynchronous chạy về sau. Fence chỉ giữ reference sống **đến vị trí gọi fence**. Muốn giữ lâu hơn, phải có Java owner record in-flight/handle hoặc một native-owned allocation với cleanup protocol rõ ràng.

### 6.3. Reachability fence trong lời gọi JNI đồng bộ

```java
import java.lang.ref.Reference;
import java.nio.ByteBuffer;

static void withFence(ByteBuffer buffer) {
    try {
        synchronousNativeUse(buffer); // Native method do ứng dụng định nghĩa.
    } finally {
        Reference.reachabilityFence(buffer);
    }
}
```

Đoạn **minh họa**, chưa có định nghĩa `synchronousNativeUse`. Fence đảm bảo buffer còn strongly reachable đến đó, không biến backing region thành “sống mãi”. Với C allocation nằm ngoài JVM, Java reachability cũng không thể cản thư viện native khác chủ động `free()` sai lúc.

## 7. JNI có thể lấy địa chỉ bytes, nhưng không sở hữu memory

JNI NIO support gồm ba hàm:

```c
jobject NewDirectByteBuffer(JNIEnv *env,
                            void *address,
                            jlong capacity);

void *GetDirectBufferAddress(JNIEnv *env,
                             jobject buffer);

jlong GetDirectBufferCapacity(JNIEnv *env,
                              jobject buffer);
```

Đây là prototype minh họa; trong C gọi qua `(*env)->...`.

- `GetDirectBufferAddress` trả **địa chỉ đầu của vùng được buffer view tham chiếu** khi được hỗ trợ; với slice, địa chỉ có thể đã bao gồm offset từ parent.
- `GetDirectBufferCapacity` trả số phần tử của vùng liên quan. Với chính **ByteBuffer**, một phần tử = một byte; với typed direct buffers cần chú ý đơn vị khác.
- Hai hàm này không tự áp dụng Java `position/limit` cho từng request. C phải dùng offset và length đã được xác minh.
- JNI chuẩn không có hàm `ReleaseDirectBufferAddress`: đừng `free` pointer trả về chỉ vì đã truy cập xong.
- JVM được phép không hỗ trợ JNI direct-buffer access; lúc ấy `GetDirectBufferAddress` có thể `NULL`, `GetDirectBufferCapacity` có thể `-1`.
- `NewDirectByteBuffer` tạo Java object **bọc một vùng native đã tồn tại**; ownership vẫn thuộc về allocator/contract gốc, không mặc nhiên chuyển cho GC.

### 7.1. Giao thức địa chỉ và offset

Nếu Java truyền một `ByteBuffer` direct có `position=5`, C gọi `GetDirectBufferAddress` thường nhận **địa chỉ đầu của view** chứ không tự động `address + position`. Muốn C chỉ được thấy bytes từ `position..limit`, có thể truyền `buffer.slice()` sau khi đặt cursor đúng; slice mới có capacity bằng `remaining` và offset 0 nằm tại vị trí hiện tại của parent.

Đừng nhầm `GetDirectBufferCapacity` với “số bytes payload của request”. Với một direct buffer mới có capacity 4096 nhưng chỉ 17 bytes được nhận qua I/O, C không được tự coi 4096 bytes đều là message hợp lệ.

### 7.2. Đọc/ghi raw pointer và byte order

Con trỏ C có thể được xem là `unsigned char*` để truy cập bytes. Khi muốn đọc/ghi `int32_t` bằng cast, phải xem alignment, ABI, byte order và strict-aliasing rules. An toàn hơn là xác định giao thức byte-level, dùng `memcpy` vào biến C local hoặc encode/decode tường minh.

Java `buffer.order(ByteOrder.LITTLE_ENDIAN)` thay đổi cách Java `getInt/putInt` diễn giải, **không tự làm con trỏ C chuyển sang little-endian**. C cũng phải tuân thủ format đã định nghĩa.

## 8. Ví dụ chạy được Java 17 + C11: native ghi trực tiếp vào vùng nền

Ví dụ JNI dưới đây chỉ ghi byte trong **một lời gọi đồng bộ** và không lưu pointer sau return. Buffer được tạo bằng `allocateDirect` trong Java, vì vậy vùng nền do JVM quản lý; C chỉ được **mượn quyền truy cập**, không sở hữu allocation.

### 8.1. File `DirectBufferJniDemo.java`

```java
import java.lang.ref.Reference;
import java.nio.ByteBuffer;

public final class DirectBufferJniDemo {
    static {
        System.loadLibrary("directbufdemo");
    }

    private DirectBufferJniDemo() {}

    private static native void nativeWriteByte(
        ByteBuffer buffer, int index, byte value);

    public static void writeChecked(
        ByteBuffer buffer, int index, byte value) {

        if (buffer == null || !buffer.isDirect()
                || buffer.isReadOnly()) {
            throw new IllegalArgumentException(
                "writable direct ByteBuffer required");
        }

        if (index < 0 || index >= buffer.capacity()) {
            throw new IndexOutOfBoundsException(
                "index outside buffer capacity");
        }

        try {
            nativeWriteByte(buffer, index, value);
        } finally {
            Reference.reachabilityFence(buffer);
        }
    }

    public static void main(String[] args) {
        ByteBuffer direct = ByteBuffer.allocateDirect(4);

        writeChecked(direct, 1, (byte) 77);
        System.out.println(
            "jni-value=" + Byte.toUnsignedInt(direct.get(1)));

        try {
            writeChecked(ByteBuffer.allocate(4), 0, (byte) 1);
        } catch (IllegalArgumentException expected) {
            System.out.println(
                "heap-rejected=IllegalArgumentException");
        }

        try {
            writeChecked(direct.asReadOnlyBuffer(), 0, (byte) 1);
        } catch (IllegalArgumentException expected) {
            System.out.println(
                "readonly-rejected=IllegalArgumentException");
        }

        try {
            writeChecked(direct, 4, (byte) 1);
        } catch (IndexOutOfBoundsException expected) {
            System.out.println(
                "bounds-rejected=IndexOutOfBoundsException");
        }
    }
}
```

`writeChecked` kiểm tra direct, writable và index thuộc [0, capacity). Nếu API của bạn chỉ cho phép ghi trong `position..limit`, phải có kiểm tra window hoặc truyền một slice thay vì dùng toàn capacity. `Reference.reachabilityFence` được đặt sau lời gọi đồng bộ; không thay thế owner của native async.

### 8.2. JNI header được sinh bởi javac

```bash
javac -h . DirectBufferJniDemo.java
```

Prototype trong header có dạng:

```c
JNIEXPORT void JNICALL
Java_DirectBufferJniDemo_nativeWriteByte(
    JNIEnv *, jclass, jobject, jint, jbyte);
```

Đây là trích prototype; file C nên bao gồm **header thật** do `javac -h .` tạo. Phương thức native là `static` nên tham số thứ hai là `jclass`.

### 8.3. File `DirectBufferJniDemo.c`

```c
#include "DirectBufferJniDemo.h"

static void raise_exception(JNIEnv *env,
                            const char *class_name,
                            const char *message) {
    jclass type = (*env)->FindClass(env, class_name);
    if (type == NULL) {
        /* Thường đã có Java exception pending. */
        return;
    }

    (void)(*env)->ThrowNew(env, type, message);
    (*env)->DeleteLocalRef(env, type);
}

JNIEXPORT void JNICALL
Java_DirectBufferJniDemo_nativeWriteByte(
    JNIEnv *env,
    jclass clazz,
    jobject buffer,
    jint index,
    jbyte value) {

    (void)clazz;

    if (buffer == NULL) {
        raise_exception(
            env, "java/lang/IllegalArgumentException",
            "buffer is null");
        return;
    }

    jlong count = (*env)->GetDirectBufferCapacity(env, buffer);
    void *address = (*env)->GetDirectBufferAddress(env, buffer);

    if (count < 0 || address == NULL) {
        raise_exception(
            env, "java/lang/IllegalArgumentException",
            "direct-buffer JNI access unavailable");
        return;
    }

    if (index < 0 || (jlong)index >= count) {
        raise_exception(
            env, "java/lang/IndexOutOfBoundsException",
            "index outside direct buffer capacity");
        return;
    }

    unsigned char *bytes = (unsigned char *)address;
    bytes[index] = (unsigned char)value;
}
```

Trong mã C, `count` là capacity theo byte vì `buffer` luôn là Java `ByteBuffer` (không phải `IntBuffer`). `address` trỏ tới backing region, C chỉ viết một byte sau khi kiểm tra bounds. **Không `free(address)`** và không cache pointer. Java facade đã chặn read-only view; native C có raw pointer không nên được xem là cơ chế thực thi Java read-only policy nếu API khác gọi thẳng vào.

### 8.4. Build/run trên Linux

Đặt hai file `DirectBufferJniDemo.java` và `DirectBufferJniDemo.c` cùng thư mục, `JAVA_HOME` trỏ tới JDK 17+ có headers:

```bash
javac -h . DirectBufferJniDemo.java

cc -std=c11 -Wall -Wextra -Wpedantic -fPIC -shared \
  -I"$JAVA_HOME/include" -I"$JAVA_HOME/include/linux" \
  DirectBufferJniDemo.c -o libdirectbufdemo.so

java -Djava.library.path=. DirectBufferJniDemo
```

**Stdout chính xác với một JVM Linux hỗ trợ JNI direct-buffer access:**

```text
jni-value=77
heap-rejected=IllegalArgumentException
readonly-rejected=IllegalArgumentException
bounds-rejected=IndexOutOfBoundsException
```

Ba đường lỗi phát sinh ở Java facade trước khi gọi C; đường thành công cho thấy C sửa bytes mà Java `get(1)` thấy. Code đã được viết theo Java 17+ và JNI C11, không sử dụng API FFM preview. Trên Windows/macOS cần thay tên shared library, include folder và build flags. Nếu gặp `UnsatisfiedLinkError`, kiểm tra `java.library.path`, tên thư viện và ABI.

## 9. Chiều ngược: `NewDirectByteBuffer` bọc memory do C sở hữu

Một C library có thể gọi:

```c
jobject view = (*env)->NewDirectByteBuffer(env, ptr, capacity);
```

Đây là **đoạn minh họa**, chưa phải chương trình C độc lập. `ptr` phải trỏ tới vùng native memory hợp lệ dài tối thiểu `capacity` bytes và đáp ứng điều kiện JNI direct buffer. Java sẽ có một `ByteBuffer` **trỏ tới vùng đã tồn tại**, không phải một bản sao và không tự động biến `malloc` của C thành memory do JVM cấp phát.

Anti-pattern **sai và không được dùng**:

```c
void *p = malloc(256);
jobject b = (*env)->NewDirectByteBuffer(env, p, 256);
free(p); /* SAI: b vẫn chứa view trỏ vào vùng đã giải phóng. */
return b;
```

Không bao giờ sao chép anti-pattern này vào chương trình. Nếu Java vẫn đọc/ghi `b` sau `free(p)`, có thể nhận dữ liệu rác, lỗi không xác định hoặc crash JVM.

Cách tổ chức sản phẩm an toàn hơn:

1. Native owner giữ allocation handle và state open/closed.
2. Java wrapper có lifecycle rõ (thí dụ một component `AutoCloseable` chứa handle và view).
3. Không để một raw `ByteBuffer` còn được sử dụng sau khi owner close. Nếu phải giữ dữ liệu, **copy trước khi close**.
4. C và Java phối hợp để không `free` khi có native async operations hay Java consumers còn đang dùng vùng này.
5. Release đúng allocator, đúng một lần. Có thể dùng Cleaner làm fallback nhưng nó không có deadline chính xác và không thay thế explicit close.
6. Không dùng `ByteBuffer.isDirect()` làm dấu hiệu “JVM sẽ tự free”: nguồn cấp phát mới quyết định ownership.

### 9.1. Bảng lifetime theo nguồn cấp phát

| Nguồn | Bytes nền | Ai có quyền release? |
| --- | --- | --- |
| `ByteBuffer.allocate(n)` | Java heap array | Java GC |
| `ByteBuffer.wrap(array)` | Java array của caller | Java GC, caller sở hữu dữ liệu |
| `ByteBuffer.allocateDirect(n)` | Thường off-heap | JVM/direct-buffer allocation mechanism |
| `duplicate()/slice()` của direct buffer | **Cùng** vùng nền với parent | Owner vùng nền của parent, không phải view mới |
| `NewDirectByteBuffer(ptr,n)` | C/native memory có sẵn | Native owner theo hợp đồng của `ptr` |
| `MappedByteBuffer` | File-backed mapping | Mapping/OS/JVM lifecycle tương ứng |
| `MemorySegment.asByteBuffer()` (JDK22+) | Vùng của segment | Scope/Arena owner, không kéo dài sau close |

Trong mọi trường hợp, **có reference tới Java ByteBuffer** và **có quyền truy cập vùng nền hợp lệ** là hai điều kiện khác nhau. C có thể giải phóng một native allocation sai lúc dù Java object vẫn reachable; ngược lại một slice còn reachable có thể giữ một direct backing allocation lớn lâu hơn dự kiến.

## 10. File mapping và FFM: direct không đồng nghĩa cùng owner

`FileChannel.map(...)` trả `MappedByteBuffer`, thường là direct. Nó trỏ tới mapping của file, không phải một vùng `malloc` bình thường do Java caller tự free. Việc đóng `FileChannel` không được hiểu đơn giản là mapped buffer mất hiệu lực ngay lập tức; kiểm tra Javadoc về mapping lifetime, persistence, `force()` và OS behavior khi tích hợp.

Từ JDK 22, FFM cung cấp `MemorySegment.ofBuffer(buffer)`. Ví dụ **minh họa trong method Java 22+**:

```java
ByteBuffer direct = ByteBuffer.allocateDirect(8);
direct.position(2);
direct.limit(5);

MemorySegment view = MemorySegment.ofBuffer(direct);
System.out.println(view.isNative()); // true
System.out.println(view.byteSize()); // 3
```

Javadoc FFM cho biết segment bao phủ window từ position đến limit. Với direct buffer thông thường, automatic scope giữ buffer reachable khi segment hoặc slices còn reachable. Nhưng với `ByteBuffer` được tạo từ `MemorySegment.asByteBuffer()` của một Arena, segment `ofBuffer` **kế thừa chính scope** của segment gốc:

```java
MemorySegment returned;

try (Arena arena = Arena.ofConfined()) {
    MemorySegment nativeMemory = arena.allocate(8);
    ByteBuffer nioView = nativeMemory.asByteBuffer();
    returned = MemorySegment.ofBuffer(nioView);
}

System.out.println(returned.scope().isAlive()); // false
```

Đây là đoạn JDK 22+ đã import `java.lang.foreign.*`; **không biên dịch trên JDK 17**. Khi Arena đóng, các views cùng scope không còn được phép truy cập, **dù Java object của view chưa bị GC thu hồi**. Đây là minh họa sinh động rằng direct buffer là một view, không là giấy phép kéo dài native memory lifetime.

## 11. Byte order, alignment và C layout

`ByteBuffer` chứa bytes; các thao tác `getInt/putInt/getLong/putLong` sử dụng `ByteOrder` của chính view để mã hóa/giải mã. C raw pointer không tự đọc metadata `order()` của ByteBuffer. Ví dụ:

```java
ByteBuffer b = ByteBuffer.allocateDirect(4);
b.order(ByteOrder.LITTLE_ENDIAN);
b.putInt(0, 0x01020304);

System.out.println(Byte.toUnsignedInt(b.get(0))); // 4
System.out.println(Byte.toUnsignedInt(b.get(1))); // 3
System.out.println(Byte.toUnsignedInt(b.get(2))); // 2
System.out.println(Byte.toUnsignedInt(b.get(3))); // 1
```

Khi truyền buffer chứa C struct, cần đồng ý về **byte order, field widths, alignment, padding và ABI**. Trên một hệ thống, C `long` có thể 8 byte, trên hệ khác 4 byte. Không cast byte address tùy tiện sang `struct*` chỉ vì Java thấy đủ bytes; phải có contract từ native header/compiler.

Các `duplicate/slice` views có thể bắt đầu với `BIG_ENDIAN` theo JDK API; không mặc định mọi view kế thừa `ByteOrder` đã đặt ở parent. Cấu hình `order(...)` rõ ràng cho mỗi view dùng typed access. `ByteOrder.nativeOrder()` hỗ trợ xác định byte order của phần cứng, nhưng một protocol portable nên dùng order đã thống nhất thay vì phụ thuộc local CPU.

## 12. Quan sát native memory, giới hạn và lỗi vận hành

Java heap metrics không phản ánh đầy đủ memory direct buffers và các native allocations. Các nguồn nên phối hợp:

| Nguồn quan sát | Dùng làm gì | Giới hạn |
| --- | --- | --- |
| `BufferPoolMXBean` | Số buffers, total capacity, memory used của direct/mapped pools | Không nhất thiết bao quát mọi native allocation |
| Java Flight Recorder | Allocation, GC, native memory liên quan theo events JVM hỗ trợ | Event availability thay đổi theo JDK |
| HotSpot Native Memory Tracking | Tổng hợp native memory được JVM hạch toán | Không bao quát mọi `malloc` của thư viện ngoài |
| OS RSS/memory maps | Tổng physical memory và mappings của process | Không trực tiếp chỉ ra Java object nào giữ backing |
| Heap dump/retention analysis | Tìm ByteBuffer/slice/views bị cache giữ | Không phải thước đo toàn bộ off-heap bytes |

Ví dụ lấy Java management counters (đặt trong method):

```java
for (java.lang.management.BufferPoolMXBean pool :
     java.lang.management.ManagementFactory.getPlatformMXBeans(
         java.lang.management.BufferPoolMXBean.class)) {

    System.out.println(pool.getName()
        + " count=" + pool.getCount()
        + " capacity=" + pool.getTotalCapacity()
        + " memory=" + pool.getMemoryUsed());
}
```

Đây là code minh họa với **stdout biến động theo JVM và thời điểm đo**, không dùng làm golden stdout. Một số HotSpot versions hỗ trợ:

```bash
java -XX:NativeMemoryTracking=summary MyServer
jcmd <PID> VM.native_memory summary
```

Trong hai lệnh vận hành, thay `MyServer` và `<PID>` theo chương trình thật. NMT cần bật từ lúc startup và có overhead. `-XX:MaxDirectMemorySize=64m` là một ví dụ JVM flag giới hạn phần direct-buffer memory được JVM quản lý trên những runtime hỗ trợ; **không giới hạn mọi allocation của native C library**. Không đề xuất dùng 64 MiB như một default cho production.

Khi gặp `OutOfMemoryError` liên quan direct buffer, có thể heap vẫn chưa đầy. Điều tra in-flight buffers, các views còn sống, hàng đợi, pooling policy, GC cleanup latency, file mapping và allocations C chưa được free.

## 13. Pooling, aliasing và concurrency

Tạo direct buffer có thể đắt hơn heap buffer. Pooling được giới hạn số lượng và tổng bytes có thể giảm churn trong I/O workload lớn, nhưng đi kèm quy tắc sở hữu:

1. Borrow một buffer có trạng thái cursor được reset thích hợp.
2. Producer ghi, `flip()` trước khi consumer đọc.
3. Consumer xử lý trong giới hạn `remaining()` hoặc một slice rõ ràng.
4. Không trả buffer về pool khi còn Java view/native operation dùng bytes cũ.
5. Nếu dữ liệu nhạy cảm, cần **overwrite thực sự** trước khi reassign buffer; `clear()` không zeroize.
6. Giới hạn pool theo **total native backing bytes**, không chỉ theo số wrapper objects.
7. Nếu C sử dụng pointer async, việc Java timeout không có nghĩa C đã dừng. Không reuse/free trước native completion.

`ByteBuffer` không phải một cấu trúc tự động đồng bộ cho hai threads cùng sửa position hoặc bytes. `duplicate()` giúp mỗi thread có cursor riêng nhưng **không xóa data race trên backing storage**. Một reader/writer protocol cần synchronization, ownership transfer hoặc memory ordering phù hợp.

Một slice 16 byte có thể giữ nguyên một parent allocation 64 MiB còn reachable. Nếu cần lưu slice lâu, copy 16 bytes sang vùng độc lập để giảm retained native memory. Tuy nhiên copy có chi phí, nên lựa chọn theo vòng đời và performance đo được.

## 14. Các lỗi thường gặp

| Nhận định sai | Điều đúng cần nhớ |
| --- | --- |
| “Direct buffer không có Java object” | Wrapper và metadata vẫn là Java object |
| “`isDirect` có nghĩa C sở hữu vùng nhớ” | Không, ownership tùy nguồn cấp phát |
| “Hai `ByteBuffer` objects khác nhau nghĩa là hai bản copy” | `duplicate/slice/asReadOnlyBuffer` vẫn alias |
| “`clear()` xóa dữ liệu” | Chỉ reset cursor; không là secure wipe |
| “`flip()` copy bytes” | Chỉ đổi position/limit |
| “`GetDirectBufferAddress` cộng position cho C” | Pointer trỏ base của **view**; position xử lý riêng |
| “`GetDirectBufferCapacity` là payload length” | Nó nói capacity của view, không tự hiểu protocol |
| “`hasArray()==false` chắc chắn direct” | Read-only heap buffer cũng có thể false |
| “Read-only view là immutable snapshot” | View vẫn đọc thấy thay đổi của backing từ owner khác |
| “Read-only Java tự ngăn được C ghi raw pointer” | Native code phải tuân contract; NIO metadata không là sandbox |
| “C được `free` pointer lấy qua JNI từ `allocateDirect`” | Không; JVM quản lý allocation đó |
| “Java GC sẽ free mọi pointer từ `NewDirectByteBuffer`” | Không; native owner phải thiết kế cleanup |
| “Object còn reachable chắc chắn native pointer C còn hợp lệ” | Nếu C tự free sai lúc, object vẫn dangling |
| “Gọi `System.gc()` là close direct buffer” | Không có deadline GC/cleanup được bảo đảm |
| “Giữ slice bé chỉ tốn vài byte” | Slice có thể kéo dài lifetime allocation lớn |
| “Direct = end-to-end zero-copy” | JVM chỉ best effort ở một số native I/O paths |
| “Một buffer dùng đa thread tự động thread-safe” | Cursor và bytes cần synchronization/ownership |
| “C đóng buffer async ngay khi Future timeout” | Native code có thể vẫn dùng pointer |
| “Đổi `ByteOrder` ở parent chắc chắn đổi mọi views” | Set order rõ ràng trên view làm typed access |
| “MemorySegment view kéo dài Arena lifetime” | View của Arena mất hiệu lực khi Arena close |

## 15. Checklist triển khai

**Trước khi tạo buffer:** xác định cần heap hay direct, kích thước, độ dài payload, byte order và nhu cầu native I/O thực sự. Đừng cấp phát direct theo thói quen; đo throughput, latency, GC và native memory footprint.

**Trước khi chia sẻ view:** hỏi liệu `duplicate/slice/asReadOnlyBuffer` có alias với owner cũ không, ai được ghi, ai có cursor riêng, khi nào dữ liệu được phép bị thay thế và có cần copy/snapshot để tách lifetime không.

**Trước khi gọi JNI:** kiểm tra direct, read-only, bounds, position/limit contract, kết quả `GetDirectBufferAddress/Capacity` và ABI. Con trỏ được dùng đồng bộ hay bị C lưu qua return? Nếu async, phải có owner giữ allocation hợp lệ tới completion.

**Khi release:** xác định chính xác allocator đã tạo vùng nền. Không `free` allocation do JVM quản lý; không bỏ quên native `malloc`. Nếu owner là Arena, mọi view liên quan mất hiệu lực khi Arena close. Không để callback hoặc request retry chạm buffer sau khi owner release.

**Khi vận hành:** giới hạn pool, in-flight buffers và queue; kiểm tra memory counters ngoài heap, RSS, caches giữ slices, delayed cleaner, native allocations và cancellation paths. Không dùng `clear()` làm secure wipe.

**Điểm mấu chốt:** **ByteBuffer trực tiếp là Java object dùng để nhìn vào một vùng bytes; chính vùng bytes có owner và lifetime riêng.** Việc tạo thêm view không tự cấp phát thêm data, còn việc native C lấy pointer không tự chuyển ownership. Thiết kế an toàn luôn trả lời được: **Ai sở hữu? Ai đang sử dụng? Khi nào vùng nền hết hiệu lực?**

### Tài liệu tham khảo chính thức

- [Java SE 17 — ByteBuffer, direct buffers, duplicate, slice, read-only và ByteOrder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html)
- [Java SE 17 — Buffer, position, limit, flip, clear, compact](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/Buffer.html)
- [Java SE 17 — JNI Functions, NewDirectByteBuffer/GetDirectBufferAddress/GetDirectBufferCapacity](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/functions.html)
- [Java SE 17 — Reference.reachabilityFence](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/Reference.html)
- [Java SE 17 — BufferPoolMXBean](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/BufferPoolMXBean.html)
- [Java SE 22 — MemorySegment.ofBuffer/asByteBuffer scope](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemorySegment.html)
