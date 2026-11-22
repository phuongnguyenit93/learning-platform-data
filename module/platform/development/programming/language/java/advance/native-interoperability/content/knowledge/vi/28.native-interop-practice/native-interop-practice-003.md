# Bài thực hành: Truyền struct lồng nhau và kiểm chứng kích thước, offset giữa Java với C

## 1. Mục tiêu và kết quả phải đạt

Bài thực hành xây dựng một chương trình **Java 17+ gọi C qua JNI** để trao đổi dữ liệu của một **struct lồng nhau**. Java và C phải thống nhất **kích thước đối tượng**, **alignment**, **offset của từng trường**, **thứ tự byte** và **vòng đời vùng nhớ**. Chương trình phải **đối chiếu layout độc lập do Java tính với layout thực do C compiler báo** trước khi đọc/ghi dữ liệu.

Khi hoàn thành, bạn sẽ làm được những việc sau:

1. Khai báo hai kiểu C, **Point** và **Packet**, trong đó **Packet chứa trực tiếp Point** (không phải pointer đến Point).
2. Dùng **sizeof**, **_Alignof** và **offsetof** trong C11 để đo layout thật sau khi compiler áp dụng padding.
3. Tự tính layout phía Java theo quy tắc ABI đã chọn, rồi đối chiếu mọi trường quan trọng với kết quả từ C; **không coi metadata C trả về là bằng chứng rằng Java tự thiết kế đúng**.
4. Dùng **ByteBuffer.allocateDirect** và **ByteOrder.nativeOrder()** để truyền một vùng byte có ý nghĩa như một Packet giữa Java và JNI.
5. Cho C đọc Packet, thay đổi các field lồng nhau, ghi kết quả trở lại đúng vùng nhớ; Java xác nhận giá trị sau round-trip.
6. Cố tình tạo mismatch và kiểm tra chương trình **phát hiện lỗi trước khi chuyển dữ liệu theo layout sai**.
7. Giải thích giới hạn portability, padding, cấu trúc C chứa pointer, ownership và những tình huống không nên dùng thủ thuật diễn giải raw byte như struct.

**Phạm vi runnable chính:** Linux **x86-64**, GCC hỗ trợ C11, OpenJDK/JDK 17 trở lên. Ví dụ đã kiểm tra với GCC và OpenJDK trên Linux x86-64. Ở những ABI khác (32-bit, packing khác, alignment của double khác, hoặc kiến trúc khác), kết quả **có thể khác**: bài sẽ fail fast ở bước kiểm chứng thay vì âm thầm dùng offset sai. Phần mở rộng FFM phía cuối cần **JDK 22+**, bởi FFM chuẩn hóa ở Java 22.

## 2. Tình huống: Java gửi Packet chứa Point sang C

Giả sử một thư viện xử lý dữ liệu tọa độ bằng C. Mỗi bản ghi có loại bản tin (**kind**), một vị trí hai chiều (**point.x, point.y**), trọng số (**weight**) và số lần xử lý (**count**).

Định nghĩa C11:

~~~c
#include <stdint.h>

typedef struct {
    int32_t x;
    int32_t y;
} Point;

typedef struct {
    uint8_t kind;
    Point point;
    double weight;
    int32_t count;
} Packet;
~~~

**Point là trường nhúng trong Packet**, nên bộ nhớ của Point nằm ngay trong vùng nhớ của Packet. Nó khác với **Point *point**: nếu là pointer, struct chỉ chứa địa chỉ, còn đối tượng Point nằm ở chỗ khác và cần quản lý allocation/lifetime riêng.

C dùng các kiểu **int32_t**, **uint8_t** để thể hiện ý định về độ rộng bit. Tuy vậy, **độ rộng dữ liệu không quyết định đầy đủ layout**: compiler còn phải tuân thủ alignment của kiểu và ABI. **double** trong bài dùng môi trường mà nó có kích thước 8 byte và biểu diễn tương thích với Java double.

Không nên mô hình hóa Packet thành chuỗi byte gồm **1 + 8 + 8 + 4 = 21 byte** rồi cho rằng **sizeof(Packet) == 21**. Compiler có thể chèn padding giữa các field và ở cuối struct để mỗi phần tử trong mảng struct đều đáp ứng alignment.

## 3. Tính layout dự đoán trên Linux x86-64

Trong bài, giả định ABI có các thuộc tính:

| Kiểu C | Size | Alignment |
| --- | ---: | ---: |
| **uint8_t** | 1 | 1 |
| **int32_t** | 4 | 4 |
| **double** | 8 | 8 |
| **Point** | 8 | 4 |
| **Packet** | 32 | 8 |

Quy tắc cơ bản: vị trí của mỗi member phải được làm tròn lên bội số alignment của member đó. Với một số dương **alignment** là lũy thừa hai, phép tính tổng quát là:

~~~text
alignUp(offset, alignment) =
    ((offset + alignment - 1) / alignment) * alignment
~~~

Đây là phép toán số nguyên, giả sử không tràn số. **sizeof(struct)** còn được làm tròn lên bội alignment của toàn struct để các phần tử tiếp theo trong mảng có cùng ràng buộc alignment.

### 3.1. Point

- **x**: offset 0, dài 4 byte.
- **y**: offset 4, dài 4 byte.
- Kết thúc dữ liệu ở byte 8; **alignof(Point) = 4**, nên **sizeof(Point) = 8**.

### 3.2. Packet

- **kind**: offset 0, dài 1 byte.
- Padding 3 byte ở offset 1–3 để **point** bắt đầu tại bội số 4.
- **point**: offset 4, dài 8 byte; **point.x** ở offset tổng 4 và **point.y** ở offset tổng 8.
- Padding 4 byte ở offset 12–15 để **weight** bắt đầu tại bội số 8.
- **weight**: offset 16, dài 8 byte.
- **count**: offset 24, dài 4 byte.
- Padding cuối 4 byte ở offset 28–31 để stride của mảng **Packet[]** là 32 byte.
- **alignof(Packet) = 8** và **sizeof(Packet) = 32**.

Sơ đồ byte của một Packet với GCC trên Linux x86-64:

~~~text
Offset    0     1..3      4..7      8..11    12..15    16..23      24..27    28..31
         +-----+---------+---------+--------+---------+-----------+---------+--------+
Packet:  |kind | padding | point.x |point.y | padding |  weight   |  count  |padding |
         +-----+---------+---------+--------+---------+-----------+---------+--------+
          1 B     3 B       4 B      4 B       4 B        8 B         4 B      4 B
         <------------------------------ sizeof(Packet) = 32 ------------------------>
                       <---- sizeof(Point) = 8 ---->
~~~

Sơ đồ này là **giả thuyết phía Java** cho ABI bài tập. Phải xác minh bằng **sizeof/offsetof từ compiler đang build thư viện C**, vì cấu hình packing, phiên bản compiler, target ABI hoặc khai báo C thực tế có thể thay đổi kết quả.

## 4. Chiến lược truyền dữ liệu và vì sao dùng direct ByteBuffer

Có nhiều cách đưa một struct qua Java/native boundary:

| Cách | Cơ chế | Khi nào phù hợp |
| --- | --- | --- |
| Tách từng tham số primitive | Java truyền **x, y, weight, count** thành các argument JNI | Số field ít, muốn tránh chia sẻ layout raw memory |
| Serialize có định dạng | Java ghi vào **byte[]**/ByteBuffer theo một protocol tự định nghĩa | Lưu file/network, yêu cầu portability giữa ABI |
| **Direct ByteBuffer** | Java đặt giá trị tại offset của ABI; C lấy backing address qua JNI | Cần thực hành layout memory và native access đồng bộ |
| FFM **MemorySegment + structLayout** | Java mô tả C layout bằng API chuẩn JDK 22+ | Muốn quản lý native memory và truy cập trường có layout rõ |
| JNI ánh xạ mỗi Java object thành C struct | C đọc field Java, tạo C struct nội bộ | Không muốn Java phụ thuộc raw C ABI, chấp nhận mapping cost |

Bài dùng **direct ByteBuffer** vì Java có thể thao tác byte ở các offset tuyệt đối, còn JNI **GetDirectBufferAddress** lấy địa chỉ backing memory. Bộ đệm được giữ sống trong suốt **lời gọi native đồng bộ**; C không giữ pointer sau khi trả về.

**Direct ByteBuffer không tự tạo cấu trúc C.** Bản thân nó chỉ là vùng byte. Tính đúng đắn phụ thuộc vào agreement về field order, kích thước, padding, byte order và ownership. Java sẽ kiểm chứng layout **trước** khi ghi Packet.

## 5. Cấu trúc project thực hành

Tạo một thư mục riêng với hai file nguồn:

~~~text
nested-struct-lab/
  PacketInterop.java
  packet_interop.c
~~~

Sau khi chạy **javac -h .**, thư mục có thêm **PacketInterop.h** do Java tạo. Sau bước GCC, có **libpacketinterop.so**; Java sẽ tải thư viện bằng **System.loadLibrary("packetinterop")**. Không viết tay header JNI nếu có thể sinh từ đúng class đang dùng, vì header giúp giảm sai tên JNI symbol và chữ ký tham số.

**Yêu cầu môi trường:** JDK 17+ (cả javac và java), GCC có hỗ trợ C11, target Linux x86-64, biến **JAVA_HOME** trỏ đến **thư mục gốc JDK** có **include/jni.h**. Hai chương trình Java/C phải được build cùng target kiến trúc; JVM 64-bit không thể tải shared library 32-bit.

## 6. Mã Java 17+: tự tính offset và kiểm tra metadata C

Tạo **PacketInterop.java** với **toàn bộ nội dung** sau. Chương trình không đọc metadata C rồi chấp nhận mù quáng. Nó tính offset dựa trên ABI dự kiến trước, sau đó yêu cầu C compiler xác nhận toàn bộ mảng metadata. Nếu sai, throw **IllegalStateException** và **không gọi nativeTransform**.

~~~java
// PacketInterop.java
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.util.Arrays;

public final class PacketInterop {
    private static final int P_SIZE = 0, P_ALIGN = 1, P_X = 2, P_Y = 3;
    private static final int E_SIZE = 4, E_ALIGN = 5, E_KIND = 6;
    private static final int E_POINT = 7, E_X = 8, E_Y = 9;
    private static final int E_WEIGHT = 10, E_COUNT = 11;

    static { System.loadLibrary("packetinterop"); }

    private static native int[] nativeLayout();
    private static native int nativeTransform(ByteBuffer packet);

    private static int alignUp(int value, int alignment) {
        return ((value + alignment - 1) / alignment) * alignment;
    }

    private static int[] expectedLinuxX64Layout() {
        // C ABI cua bai: int32_t align 4, double align 8.
        int x = 0;
        int y = alignUp(x + 4, 4);
        int pointSize = alignUp(y + 4, 4);
        int kind = 0;
        int point = alignUp(kind + 1, 4);
        int weight = alignUp(point + pointSize, 8);
        int count = alignUp(weight + 8, 4);
        int packetSize = alignUp(count + 4, 8);
        return new int[] {
                pointSize, 4, x, y,
                packetSize, 8, kind, point,
                point + x, point + y, weight, count
        };
    }

    private static String fields(ByteBuffer b, int[] l) {
        return "kind=" + Byte.toUnsignedInt(b.get(l[E_KIND]))
                + " x=" + b.getInt(l[E_X])
                + " y=" + b.getInt(l[E_Y])
                + " weight=" + b.getDouble(l[E_WEIGHT])
                + " count=" + b.getInt(l[E_COUNT]);
    }

    public static void main(String[] args) {
        int[] expected = expectedLinuxX64Layout();
        int[] actual = nativeLayout();
        if (!Arrays.equals(expected, actual)) {
            throw new IllegalStateException(
                    "ABI mismatch: expected=" + Arrays.toString(expected)
                            + ", actual=" + Arrays.toString(actual));
        }
        System.out.println("ABI layout match: true");
        System.out.println("Point: size=" + actual[P_SIZE]
                + " align=" + actual[P_ALIGN]
                + " x=" + actual[P_X] + " y=" + actual[P_Y]);
        System.out.println("Packet: size=" + actual[E_SIZE]
                + " align=" + actual[E_ALIGN]
                + " kind=" + actual[E_KIND]
                + " point=" + actual[E_POINT]
                + " point.x=" + actual[E_X]
                + " point.y=" + actual[E_Y]
                + " weight=" + actual[E_WEIGHT]
                + " count=" + actual[E_COUNT]);

        ByteBuffer packet = ByteBuffer.allocateDirect(expected[E_SIZE])
                .order(ByteOrder.nativeOrder());
        packet.put(expected[E_KIND], (byte) 7);
        packet.putInt(expected[E_X], 10);
        packet.putInt(expected[E_Y], -3);
        packet.putDouble(expected[E_WEIGHT], 2.5);
        packet.putInt(expected[E_COUNT], 4);

        System.out.println("Before: " + fields(packet, expected));
        int checksum = nativeTransform(packet);
        System.out.println("After:  " + fields(packet, expected));
        System.out.println("Native checksum=" + checksum);
    }
}
~~~

**Giải thích các điểm thiết yếu:**

- **expectedLinuxX64Layout()** tự tính các byte offset, gồm **point.x/point.y nằm trong Packet**, và làm tròn **Packet sizeof** sau field cuối. Nó thể hiện giả định ABI Linux x86-64, **không phải API introspection C**.
- Mảng gồm **12 số** theo thứ tự: **Point.size**, **Point.alignment**, **Point.x offset**, **Point.y offset**, **Packet.size**, **Packet.alignment**, **Packet.kind offset**, **Packet.point offset**, **Packet.point.x offset**, **Packet.point.y offset**, **Packet.weight offset**, **Packet.count offset**. Hai phía phải thống nhất cả thứ tự số.
- **Arrays.equals(expected, actual)** là rào chắn trước khi truyền dữ liệu. Nếu C thay đổi khai báo hoặc packing, Java phát hiện khác biệt.
- **allocateDirect(expected[E_SIZE])** tạo bộ đệm có đủ 32 byte. **order(ByteOrder.nativeOrder())** đặt endian cho các phép **putInt/putDouble/getInt/getDouble**, phù hợp với hệ thống C dùng trong bài.
- Các lệnh **put(index, ...)** là **absolute access**: không tăng position của buffer. C được truyền vùng backing bắt đầu từ offset 0. Khi dùng API tương đối (**putInt(value)**), phải quản lý **position/limit** khác.
- **Byte.toUnsignedInt** khiến **kind** được hiển thị theo phạm vi 0–255 tương ứng với **uint8_t**, thay vì coi nó là số byte có dấu của Java.
- **nativeTransform()** nhận và sửa chính buffer đã cấp phát, sau đó Java đọc lại các field để chứng minh đường truyền hai chiều. Giá trị checksum chỉ là một kiểm tra dễ quan sát, không phải cơ chế bảo mật.

Chương trình dùng **Java 17** và JNI tiêu chuẩn, không cần module **java.lang.foreign**. Lời gọi native là **đồng bộ**; nếu C giữ pointer để xử lý sau khi trả về, phải thiết kế vòng đời bộ nhớ khác.

## 7. Mã C11: sizeof, alignof, offsetof và round-trip

Tạo **packet_interop.c** với **toàn bộ nội dung** bên dưới. File include **PacketInterop.h** do **javac -h .** tạo; header đó đã include **jni.h** và khai báo đúng các native methods.

~~~c
// packet_interop.c
#include "PacketInterop.h"
#include <stdint.h>
#include <stddef.h>
#include <string.h>

typedef struct {
    int32_t x;
    int32_t y;
} Point;

typedef struct {
    uint8_t kind;
    Point point;
    double weight;
    int32_t count;
} Packet;

JNIEXPORT jintArray JNICALL
Java_PacketInterop_nativeLayout(JNIEnv *env, jclass cls) {
    (void)cls;
    const jint values[] = {
        (jint)sizeof(Point), (jint)_Alignof(Point),
        (jint)offsetof(Point, x), (jint)offsetof(Point, y),
        (jint)sizeof(Packet), (jint)_Alignof(Packet),
        (jint)offsetof(Packet, kind), (jint)offsetof(Packet, point),
        (jint)(offsetof(Packet, point) + offsetof(Point, x)),
        (jint)(offsetof(Packet, point) + offsetof(Point, y)),
        (jint)offsetof(Packet, weight), (jint)offsetof(Packet, count)
    };
    const jsize length = (jsize)(sizeof(values) / sizeof(values[0]));
    jintArray result = (*env)->NewIntArray(env, length);
    if (result == NULL) return NULL;
    (*env)->SetIntArrayRegion(env, result, 0, length, values);
    return result;
}

static void fail(JNIEnv *env, const char *message) {
    jclass type = (*env)->FindClass(
            env, "java/lang/IllegalArgumentException");
    if (type != NULL) (*env)->ThrowNew(env, type, message);
}

JNIEXPORT jint JNICALL
Java_PacketInterop_nativeTransform(
        JNIEnv *env, jclass cls, jobject buffer) {
    (void)cls;
    void *raw = (*env)->GetDirectBufferAddress(env, buffer);
    jlong capacity = (*env)->GetDirectBufferCapacity(env, buffer);
    if (raw == NULL || capacity < (jlong)sizeof(Packet)) {
        fail(env, "Expected a sufficiently large direct ByteBuffer");
        return 0;
    }

    Packet packet;
    memcpy(&packet, raw, sizeof(packet));
    if (packet.kind != 7) {
        fail(env, "Unexpected packet kind");
        return 0;
    }
    packet.point.x += 100;
    packet.point.y *= 2;
    packet.weight *= 2.0;
    packet.count += 1;
    memcpy(raw, &packet, sizeof(packet));
    return (jint)(packet.point.x + packet.point.y + packet.count);
}
~~~

**Ý nghĩa của mã C:**

1. **sizeof(Point)/sizeof(Packet)** đo kích thước type **gồm cả padding**. **_Alignof** (C11) đo yêu cầu alignment. **offsetof** (từ **stddef.h**) đo offset field so với đầu struct chứa field đó.
2. Offset lồng nhau được tính bằng **offsetof(Packet, point) + offsetof(Point, x/y)**. Vì **point** là object nhúng trực tiếp, phép cộng này cho offset **point.x/point.y** tính từ đầu Packet. Đây là điểm khác với một field dạng **Point***.
3. **nativeLayout** trả metadata thực của binary C compiler đã build. Java so sánh với layout tính từ ABI trước khi dùng bất kỳ raw field offset nào.
4. **GetDirectBufferAddress** trả backing address; **GetDirectBufferCapacity** kiểm tra capacity. Code **không** dùng **buffer.position()** hay **buffer.limit()** ở C; hai phía đã giao ước payload bắt đầu tại byte 0 và có đúng **sizeof(Packet)** byte.
5. **memcpy(&packet, raw, sizeof packet)** đưa byte sang một **Packet** cục bộ có alignment phù hợp. Không trực tiếp cast một **void*** bất kỳ thành **Packet*** để dereference: địa chỉ backing ByteBuffer không được code này chứng minh là đúng alignment cho Packet, và cast còn có những vấn đề về kiểu đối tượng/effective type.
6. C thay đổi **packet.point.x**, **packet.point.y**, **weight** và **count**, rồi **memcpy(raw, &packet, sizeof packet)** để ghi lại vào ByteBuffer. Java nhìn thấy các giá trị mới khi hàm kết thúc.
7. **GetDirectBufferAddress** có thể trả **NULL** và **GetDirectBufferCapacity** có thể trả **-1** nếu buffer không phải loại truy cập được qua JNI; code ném ngoại lệ hợp lệ. Nếu **NewIntArray** hết bộ nhớ, JNI thường đã đặt một pending exception và hàm trả NULL.
8. **raw** chỉ được dùng trong thời gian lời gọi **nativeTransform**. Code không lưu con trỏ vào biến global và không cấp phát C memory cần free riêng.

**Phạm vi an toàn của phép memcpy:** bài kiểm tra ABI Linux x86-64, nơi byte order/biểu diễn **int32_t** và **double** giữa Java và C tương thích. Copy toàn bộ 32 byte gồm padding chỉ nhằm minh họa đường đi của một struct. Trong ứng dụng thực tế, **padding không phải dữ liệu có nghĩa**; không đưa padding chưa được chuẩn hóa vào file, network payload, hash hoặc chữ ký số. Khi thiết kế binary protocol ổn định giữa máy khác ABI, serialize từng field với endian và độ rộng cố định thay vì dump trực tiếp **sizeof(struct)**.

## 8. Biên dịch và chạy thực tế

Đảm bảo đang ở đúng thư mục có **PacketInterop.java** và **packet_interop.c**, đặt **JAVA_HOME** đến thư mục JDK 17+ đang dùng. Ví dụ trên Linux, thay đường dẫn bằng JDK của máy:

~~~bash
export JAVA_HOME=/path/to/jdk-17-or-newer
javac -h . PacketInterop.java
gcc -std=c11 -O2 -Wall -Wextra -fPIC -shared \
  -I"$JAVA_HOME/include" -I"$JAVA_HOME/include/linux" \
  packet_interop.c -o libpacketinterop.so
java -Djava.library.path=. PacketInterop
~~~

**javac -h .** biên dịch Java và sinh header **PacketInterop.h** theo chính các native method đã khai báo. **-shared -fPIC** tạo shared object có thể được JVM tải; tên **libpacketinterop.so** phù hợp **System.loadLibrary("packetinterop")** trên Linux. Thư mục chứa **libpacketinterop.so** được chỉ rõ bằng **-Djava.library.path=.**. Cần dùng thư viện cùng kiến trúc với JVM.

Khi biên dịch/chạy với JDK tương thích và GCC Linux x86-64 như giả định, stdout **chính xác**:

~~~text
ABI layout match: true
Point: size=8 align=4 x=0 y=4
Packet: size=32 align=8 kind=0 point=4 point.x=4 point.y=8 weight=16 count=24
Before: kind=7 x=10 y=-3 weight=2.5 count=4
After:  kind=7 x=110 y=-6 weight=5.0 count=5
Native checksum=109
~~~

Đây là kết quả từ **ví dụ đã biên dịch và chạy** bằng OpenJDK/GCC trên Linux x86-64. Có **hai dấu cách** giữa dấu hai chấm trong **After:  ** vì chuỗi hiển thị được viết có chủ đích.

**Giải thích kết quả:**

- Point size 8, alignment 4, x offset 0, y offset 4.
- Packet size 32, alignment 8. **point.x** offset 4, **point.y** offset 8 tính từ đầu Packet.
- C đọc **kind 7**, **x 10**, **y -3**, **weight 2.5**, **count 4**, rồi ghi lại **x = 110**, **y = -6**, **weight = 5.0**, **count = 5**.
- Checksum C trả về là **110 + (-6) + 5 = 109**.
- Vì Java vẫn giữ cùng một direct ByteBuffer, các lần **getInt/getDouble** đọc được kết quả sau khi JNI return.

Nếu stdout không khớp, **không bỏ bước kiểm tra ABI** để cố chạy phần còn lại. Tìm nguyên nhân mismatch ở khai báo C, compiler flags, kiến trúc JVM/native library, packing hoặc quy ước byte order.

## 9. Tại sao chỉ sizeof không đủ: cần kiểm tra từng offset

Hai struct có thể cùng **sizeof** nhưng layout field khác. Ví dụ C đổi thứ tự **kind** và **point** nhưng tổng sizeof Packet vẫn có thể là 32. Nếu Java chỉ kiểm tra **sizeof(Packet)==32** rồi đọc theo offsets cũ, dữ liệu có thể bị giải nghĩa nhầm mà không phát sinh ngoại lệ.

Vì thế, bài kiểm tra đủ các lớp:

| Thứ cần kiểm | Phía Java | Phía C |
| --- | --- | --- |
| **Point.size** | Tự tính end offset làm tròn alignment | **sizeof(Point)** |
| **Point.align** | Giả định ABI (4) | **_Alignof(Point)** |
| **Point.x/y** | Tự tính 0 và 4 | **offsetof(Point, x/y)** |
| **Packet.size** | Làm tròn end offset của count lên align struct | **sizeof(Packet)** |
| **Packet.align** | Giả định ABI (8) | **_Alignof(Packet)** |
| **Packet.kind/point** | Tự tính 0 và 4 | **offsetof(Packet, kind/point)** |
| **Packet.point.x/y** | Offset point + offset field con | Tổng các **offsetof** ở C |
| **Packet.weight/count** | Tự tính 16 và 24 | **offsetof(Packet, weight/count)** |

Không có phép kiểm tra alignment thực của **ByteBuffer backing address** trong bài; đó là lý do C **memcpy** qua một local Packet được compiler cấp phát đúng alignment. Nếu code C đọc trực tiếp thành **Packet***, còn phải chứng minh địa chỉ, ownership và effective type phù hợp.

### 9.1. Nested struct và pointer khác nhau

Nếu thay **Point point** thành **Point *point**, kích thước field trong Packet là **kích thước pointer** của target ABI. **offsetof(Packet, point)** chỉ trỏ tới **nơi lưu địa chỉ**, không phải dữ liệu **x/y**. Muốn đọc **point->x**, C cần dereference pointer hợp lệ có lifetime dài hơn lần sử dụng; Java không thể đơn giản cộng **offsetof(Point,x)** vào offset của field pointer để đọc x.

Tương tự, một **char name[16]** là mảng inline với kích thước cố định trong struct; **char *name** chỉ là pointer. Khi thiết kế FFM/JNA/JNI mapping, phải phân biệt hai dạng này.

## 10. Bài thử lỗi có chủ đích

Thực hiện lần lượt trên **bản sao thư mục thực hành** và build lại thư viện C. Mỗi bài thử cần nêu lỗi xuất hiện trước khi sửa, sau đó khôi phục source về trạng thái gốc.

### Thử A — Đổi cấu trúc C nhưng giữ Java cũ

Trong C, đảo vị trí **kind** và **point**:

~~~c
typedef struct {
    Point point;
    uint8_t kind;
    double weight;
    int32_t count;
} Packet;
~~~

Giữ nguyên phần Java, biên dịch lại **libpacketinterop.so** và chạy. Kết quả đúng mong đợi là **IllegalStateException** chứa **ABI mismatch**, vì mảng **nativeLayout()** khác với kỳ vọng. Java **không chạy nativeTransform**. Dù có thể cùng sizeof là 32, vị trí **kind** hoặc **point** đã thay đổi: kiểm tra size đơn lẻ là chưa đủ.

Không cần nhớ toàn bộ chuỗi stack trace vì số dòng/đường dẫn thay đổi giữa JDK; điều quan trọng là fail fast và in được hai mảng expected/actual.

### Thử B — Dùng heap ByteBuffer

Trong Java, đổi **ByteBuffer.allocateDirect(expected[E_SIZE])** thành **ByteBuffer.allocate(expected[E_SIZE])**, vẫn tạo **ByteOrder.nativeOrder()** như cũ. Khi chạy **nativeTransform**, JNI direct-buffer address không hợp lệ và C ném **IllegalArgumentException: Expected a sufficiently large direct ByteBuffer** (trên JVM hỗ trợ JNI direct access bình thường). Điều này cho thấy một heap ByteBuffer không thể được xử lý y như direct buffer qua **GetDirectBufferAddress**.

### Thử C — Cố tình sai endian

Trong Java, bỏ **.order(ByteOrder.nativeOrder())**. **ByteBuffer** mới mặc định dùng **BIG_ENDIAN**. Trên Linux x86-64 điển hình **little-endian**, các phép **putInt/putDouble** tạo byte theo thứ tự khác với C. **ABI layout match** vẫn có thể là **true** vì kích thước/offset không đổi, nhưng dữ liệu **x/y/weight/count** không còn đúng. Điều đó chứng minh:

**Layout size/offset đúng ≠ biểu diễn byte đúng ≠ ngữ nghĩa dữ liệu đúng.**

Khôi phục native order sau thử nghiệm. Khi dữ liệu dùng để trao đổi qua mạng hoặc lưu file giữa hệ thống khác nhau, cần một định dạng tuần tự hóa có endian cố định, không lấy byte order của máy gửi làm chuẩn giao thức.

### Thử D — Buffer thiếu dung lượng

Đổi allocation thành **allocateDirect(expected[E_SIZE] - 1)**. Trong chương trình gốc, một phép **put** có thể đã ném **IndexOutOfBoundsException** trước khi gọi C, vì Java kiểm tra bounds. Nếu muốn kiểm thử riêng nhánh **capacity** ở C, truyền một direct buffer ngắn **đang không bị Java ghi trước** đến **nativeTransform**; C sẽ phát hiện capacity không đủ rồi ném **IllegalArgumentException**. Đây là ví dụ vì sao phải kiểm tra bounds ở **cả hai phía**.

### Thử E — Kiểm tra tail padding và stride

Tạo **Packet array[2]** ở C và đo:

~~~c
size_t stride = (size_t)((const unsigned char *)&array[1]
        - (const unsigned char *)&array[0]);
~~~

Trong ngữ cảnh một hàm C có **Packet array[2];**, đoạn trên cho **stride == sizeof(Packet)**. Trên ABI bài tập, stride là **32**, không phải **21**. Vì vậy Java phải dùng **index * sizeof(Packet)** khi mô hình mảng struct ở dạng raw byte, không dùng tổng kích thước các field đã khai báo.

## 11. Padding, alignment và nguy cơ tiềm ẩn trong production

### 11.1. Padding không thuộc dữ liệu nghiệp vụ

Các byte padding có thể mang giá trị cũ hoặc khác nhau giữa compiler/build. **memcmp** toàn struct, hash raw bytes, gửi một C struct nguyên xi qua network hoặc dùng struct làm định dạng file dài hạn có thể sai dù mọi field có nghĩa giống nhau. Nếu cần so sánh, so sánh từng field; nếu cần serialize, tạo định dạng xác định và bỏ padding.

Trong chương trình bài tập, **ByteBuffer.allocateDirect** được cấp bộ nhớ mới, và C copy toàn bộ vùng struct để biểu diễn round trip. Điều này **không có nghĩa** phép trao đổi toàn bộ sizeof(struct) là thiết kế tốt cho giao thức public. Chỉ sử dụng ở một ranh giới trong cùng tiến trình, cùng binary ABI đã được kiểm tra.

### 11.2. Không áp dụng trực tiếp với struct chứa pointer hoặc flexible array member

Đối với **char***, **void***, **Point*** hoặc trường chứa pointer, chép raw bytes của struct chỉ chép **giá trị địa chỉ**, không chép object mà pointer trỏ tới. Không thể serialize pointer sang tiến trình khác, máy khác hay lưu vào file rồi dùng lại. Nếu struct có **flexible array member** (ví dụ **char payload[]** ở cuối), **sizeof** chỉ phản ánh phần cố định và padding tương ứng, không gồm payload cấp phát động. Hai trường hợp này cần bài thiết kế layout và ownership riêng.

### 11.3. Packing, alignment override và ABI

**#pragma pack**, compiler-specific attributes như **__attribute__((packed))** hoặc build flags có thể thay đổi alignment và offset. Với packed struct, con trỏ đến member có thể không được căn chỉnh đúng cho kiểu native của member đó; dereference không cẩn thận có thể gây lỗi trên kiến trúc nghiêm ngặt. Không cố ép Java khớp bằng cách giảm **sizeof** mà bỏ qua alignment/cách C truy cập.

Còn một chiều khác: một số ABI có quy tắc đặc biệt cho **bit-field**, union, vector type, long double hoặc struct return-by-value. Không suy rộng công thức đơn giản của Packet cho mọi loại C type. Trong những trường hợp phức tạp, dùng compiler **sizeof/offsetof/alignof**, tài liệu ABI và binding generator (nếu phù hợp).

### 11.4. Vòng đời và xử lý đồng thời

Trong bài, Java tạo direct ByteBuffer, gọi JNI **đồng bộ**, nhận kết quả rồi đọc buffer. C không giữ pointer sau khi return, vì vậy không có native worker đang truy cập buffer sau khi lời gọi kết thúc.

Khi sử dụng bất đồng bộ, một con trỏ C giữ qua nhiều lượt gọi có thể sống lâu hơn Java wrapper hoặc bị ghi đè nếu buffer được đưa trở lại pool. Cần owner rõ ràng, reference/lifetime giữ dữ liệu sống, cơ chế hoàn thành/cancel và quy tắc chỉ đóng/thu hồi sau khi C ngừng sử dụng. **Direct buffer không tự quản lý pointer C mà thư viện giữ lại**. Nếu nhiều thread ghi một buffer, cần đồng bộ và định nghĩa thứ tự nhìn thấy thay đổi; demo single-thread không chứng minh thread safety.

## 12. Mở rộng với Foreign Function & Memory API (JDK 22+)

Trên **JDK 22 trở lên**, **java.lang.foreign.MemoryLayout** có thể mô tả các trường struct lồng nhau, cho phép hỏi **byteSize()**, **byteAlignment()** và **byteOffset(PathElement...)**. **MemoryLayout.structLayout** không tự chèn padding; phải khai báo **paddingLayout** rõ nếu muốn tương ứng với C ABI. Ví dụ dưới đây là **chương trình độc lập không gọi C**; nó mô hình hóa chính bố cục Packet Linux x86-64 của bài. Muốn chứng minh kết nối C thực tế, vẫn cần so với metadata **sizeof/offsetof** từ thư viện C.

Tạo **PacketLayoutFFM.java** (chỉ trên JDK 22+):

~~~java
// PacketLayoutFFM.java -- JDK 22+
import java.lang.foreign.MemoryLayout;
import java.lang.foreign.StructLayout;
import java.lang.foreign.ValueLayout;

public class PacketLayoutFFM {
    public static void main(String[] args) {
        StructLayout point = MemoryLayout.structLayout(
                ValueLayout.JAVA_INT.withName("x"),
                ValueLayout.JAVA_INT.withName("y")
        ).withName("point");

        StructLayout packet = MemoryLayout.structLayout(
                ValueLayout.JAVA_BYTE.withName("kind"),
                MemoryLayout.paddingLayout(3),
                point,
                MemoryLayout.paddingLayout(4),
                ValueLayout.JAVA_DOUBLE.withName("weight"),
                ValueLayout.JAVA_INT.withName("count"),
                MemoryLayout.paddingLayout(4)
        );

        long nestedY = packet.byteOffset(
                MemoryLayout.PathElement.groupElement("point"),
                MemoryLayout.PathElement.groupElement("y"));

        System.out.println("Point size=" + point.byteSize());
        System.out.println("Packet size=" + packet.byteSize());
        System.out.println("Packet.point.y offset=" + nestedY);
    }
}
~~~

Biên dịch và chạy bằng JDK 22+:

~~~bash
javac PacketLayoutFFM.java
java PacketLayoutFFM
~~~

Kết quả dự kiến với layout đã mô tả:

~~~text
Point size=8
Packet size=32
Packet.point.y offset=8
~~~

**Lưu ý:** ví dụ FFM này chỉ **tính layout**, không thực hiện downcall vào thư viện C. Với downcall FFM thực sự phải tuân thủ phiên bản JDK, quyền native access, linker ABI, vòng đời Arena/MemorySegment và signature C chính xác. Không dùng một MemoryLayout được tạo theo phỏng đoán thay cho kiểm chứng thực tế với C build. Đặc biệt, API FFM chuẩn này **không tồn tại trong Java 17**.

## 13. Hướng mở rộng của bài thực hành

### 13.1. Bài mở rộng một — mảng nhiều Packet

Sửa C để nhận số lượng Packet, Java cấp direct buffer dung lượng **count * verified sizeof(Packet)**. Native xử lý từng phần tử bằng **memcpy** từ **base + i * sizeof(Packet)** vào local Packet, chỉnh sửa rồi copy trở lại. Kiểm tra integer overflow trước khi nhân **count * size**, giới hạn capacity, và không truy cập quá **limit** dữ liệu nghiệp vụ. Đặt ít nhất hai phần tử có giá trị khác nhau để phát hiện lỗi stride.

### 13.2. Bài mở rộng hai — field lồng nhau hai cấp

Thêm **struct Header** vào **Point** hoặc thêm **struct Metadata** bao gồm một **Point** khác. Đo offset bằng tổng các **offsetof** qua từng tầng, chẳng hạn **offsetof(Outer, mid) + offsetof(Mid, inner) + offsetof(Inner, value)**. So sánh với offset tính độc lập phía Java. Kiểm tra cả **sizeof** mỗi tầng và alignment của tầng chứa.

### 13.3. Bài mở rộng ba — nhiều ABI và khác endian

Build riêng trên **Linux x86-64**, một ARM64 phù hợp và Windows x64 nếu có công cụ; ghi lại **sizeof/alignof/offsetof** từ C, không giả định mọi kết quả bằng nhau. Trên kiến trúc big-endian (nếu có), quan sát **ByteOrder.nativeOrder()**. Chỉ sửa layout phía Java sau khi đã xác định ABI và có bảng kỳ vọng đúng, không tắt guard khi phát hiện mismatch.

### 13.4. Bài mở rộng bốn — đo chi phí copy và direct

So sánh một phương án **byte[] + JNI GetByteArrayRegion** với phương án direct ByteBuffer đã kiểm tra layout. Đo cả chi phí tạo/copy buffer, JNI crossing, native xử lý và readback. Không đo riêng hàm C rồi tuyên bố toàn pipeline là zero-copy. Dùng workload đủ lớn và benchmark đáng tin cậy (JMH) khi cần kết luận hiệu năng; với nhiệm vụ layout hiện tại, correctness là ưu tiên đầu tiên.

### 13.5. Tiêu chí đạt bài

- Mọi offset và sizeof/alignof do Java dự đoán **khớp** C, không chỉ kích thước tổng.
- Java ghi và đọc đủ field, gồm **point.x** và **point.y** lồng nhau.
- Native thay đổi field và Java xác nhận kết quả đúng **sau JNI return**.
- Thay đổi layout C có chủ đích gây **fail fast** trước khi dùng raw offsets.
- Bộ đệm không bị đọc ngoài bounds và native không giữ pointer quá vòng đời cho phép.
- Người học chỉ ra được padding 1–3, 12–15 và 28–31 trên ABI mẫu.
- Có phân biệt rõ **struct embedded**, **pointer**, **array stride**, byte order và binary protocol.

## 14. Sự cố phổ biến và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra/xử lý |
| --- | --- | --- |
| **UnsatisfiedLinkError: no packetinterop in java.library.path** | JVM không tìm được **libpacketinterop.so** | Kiểm tra file, thư mục chạy và **-Djava.library.path=.** |
| **UnsatisfiedLinkError: Native method ...** | Tên JNI symbol sai, Java/C build lệch phiên bản | Chạy lại **javac -h .**, include header được sinh và build lại C |
| **fatal error: PacketInterop.h: No such file** | Chưa chạy **javac -h .** hoặc làm việc sai thư mục | Sinh header trước khi GCC build |
| **fatal error: jni.h: No such file** | **JAVA_HOME** không trỏ JDK hoặc thiếu include path | Dùng **$JAVA_HOME/include** và **include/linux** |
| Thư viện có nhưng JVM không tải được | Sai target kiến trúc hoặc dependency native thiếu | So sánh JVM 64-bit và binary bằng **file libpacketinterop.so**, kiểm tra dependencies |
| **ABI mismatch** | C struct sửa, packing/align khác, target ABI khác | In expected/actual; kiểm tra từng **sizeof/_Alignof/offsetof** |
| **Point đúng, Packet sai** | Padding của struct ngoài hoặc field order khác | Xem **point offset**, **weight offset**, **count offset**, tail padding |
| Kích thước/offset đúng nhưng field ra số vô lý | Sai byte order, sai cách diễn giải **int32_t/double**, ghi sai window | Giữ **nativeOrder()**, kiểm tra byte pattern và input |
| **IllegalArgumentException** trong nativeTransform | Buffer không trực tiếp hoặc capacity nhỏ hơn **sizeof(Packet)** | Dùng **allocateDirect**, so sánh capacity và verified size |
| **SIGSEGV/JVM crash** trong phiên bản sửa tay | Dereference pointer lỗi, alignment/lifetime sai, truy cập ngoài bounds | Tránh raw pointer cast; kiểm tra capacity và owner; dùng ASan/Valgrind nếu phù hợp |
| Kết quả thay đổi ngẫu nhiên ở padding | Padding không được chuẩn hóa hoặc code đọc byte không có nghĩa | Không so sánh/hash raw struct; serialize từng field |
| C biên dịch với flags khác lần trước | Shared object cũ vẫn được Java tải | Build sạch **đúng file C** và chạy từ đúng thư mục |

Khi điều tra mismatch, ưu tiên in **actual metadata** của C cùng **expected metadata** của Java. Việc bắt đầu đo offset từ output của chính thư viện C sau đó dùng luôn số ấy để đóng gói có thể khiến chương trình chạy, nhưng bỏ mất bước kiểm chứng **layout độc lập** mà bài đang yêu cầu.

## 15. Các kiến thức cần nhớ

**sizeof** và **_Alignof** nói về kích thước và alignment thực của C type trong build đang chạy. **offsetof** nói về khoảng cách theo byte từ đầu struct đến một trường trực tiếp; với struct nhúng nhiều tầng, có thể cộng offset của từng tầng. **sizeof(struct)** thường lớn hơn tổng kích thước field do padding.

Java **ByteBuffer** mang dữ liệu tại offset tuyệt đối nhưng không biết struct C có bao nhiêu padding. **ByteOrder.nativeOrder()** giải quyết endian trong phạm vi ABI hiện tại; không thay thế xác minh kích thước, offset và representation. **GetDirectBufferAddress** cho JNI truy cập backing memory của một direct buffer được hỗ trợ, còn **GetDirectBufferCapacity** giúp kiểm tra dung lượng. Dùng **memcpy** vào local struct tránh giả định alignment của pointer.

Bài thực hành chỉ được coi hoàn tất khi cả **layout verification** và **data round-trip** đều thành công. Khi đóng gói dữ liệu cho protocol hoặc lưu trữ lâu dài, tránh serialize trực tiếp **sizeof(Packet)** byte vì phụ thuộc ABI, padding và pointer. Thiết kế một wire format ổn định có versioning, field encoding và endian cố định mới phù hợp.

## 16. Tài liệu đối chiếu

- [JNI Functions: GetDirectBufferAddress, GetDirectBufferCapacity, NewDirectByteBuffer](https://docs.oracle.com/en/java/javase/22/docs/specs/jni/functions.html)
- [Java 17 ByteBuffer API: absolute access, direct buffer, byte order](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html)
- [Java 22 MemoryLayout API: structLayout, paddingLayout, byteOffset và layout path](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemoryLayout.html)
- [Java 22 StructLayout API](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/StructLayout.html)
- [C language — sizeof, alignment và offsetof; kiểm chứng theo ABI/compiler mục tiêu](https://en.cppreference.com/w/c/types/offsetof)
