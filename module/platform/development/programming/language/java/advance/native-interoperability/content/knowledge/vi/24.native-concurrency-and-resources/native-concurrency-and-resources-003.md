# Đồng bộ dữ liệu mà Java và mã bản địa cùng đọc hoặc ghi

**Ngữ cảnh:** Java Advance → native-interoperability → Đồng thời và tài nguyên.

Khi ứng dụng Java gọi C/C++ qua JNI, hoặc chia sẻ vùng nhớ với thư viện native qua bộ đệm trực tiếp/Foreign Function & Memory API, hai phía có thể cùng quan sát và thay đổi một trạng thái. Việc gọi được hàm native **không tự tạo ra cơ chế bảo vệ** cho mọi truy cập khác đang diễn ra. Muốn dữ liệu đúng, phải xác định ai sở hữu vùng nhớ, ai được đọc/ghi, thao tác nào phải nguyên tử, việc công bố thay đổi diễn ra thế nào và lúc nào vùng nhớ được giải phóng.

Sau bài này, bạn có thể chọn một cơ chế đồng bộ phù hợp với từng kiểu dữ liệu; dùng cùng một monitor Java từ Java và JNI; phân biệt an toàn luồng với an toàn vòng đời; nhận diện những trường hợp Java và C/C++ tưởng như đã “khóa” nhưng thực ra vẫn xảy ra race.

## 1. Xác định chính xác dữ liệu đang được chia sẻ

| Trạng thái | Phía Java truy cập | Phía native truy cập | Ràng buộc quan trọng |
| --- | --- | --- | --- |
| Trường của đối tượng Java | Field/method thông thường, synchronized, Atomic* | JNI Get/Set field hoặc gọi phương thức Java | Cả hai phải cùng tuân thủ quy ước đồng bộ trên đối tượng Java. |
| Mảng Java | Truy cập phần tử mảng | JNI Get/Release array elements, Get/Set array region, critical access | Con trỏ JNI có thể trỏ đến bản sao hoặc vùng bị pin; không được coi là địa chỉ sống vô hạn. |
| DirectByteBuffer | Java NIO đọc/ghi bytes | JNI GetDirectBufferAddress hoặc native giữ bộ nhớ được bọc bởi buffer | Phải thống nhất vòng đời bộ nhớ, byte order, alignment, độ rộng trường và cách đồng bộ. |
| Bộ nhớ native do FFM quản lý (JDK 22+) | MemorySegment, layout, VarHandle | Con trỏ C/C++ trỏ tới vùng nhớ hợp lệ | Scope/Arena kiểm soát phạm vi truy cập và vòng đời, **không tự biến mọi phép đọc/ghi thành atomic**. |
| Handle tài nguyên native | Java giữ mã định danh/đối tượng wrapper | Native sử dụng file/socket/struct/handle | Cần quy tắc đóng tài nguyên và ngăn sử dụng sau khi đã đóng. |

Trước khi viết khóa, đặt bốn câu hỏi:

1. **Cùng một vị trí nhớ hay hai bản sao?** JNI có thể tạo bản sao khi lấy phần tử mảng; ghi vào bản sao không đồng nghĩa Java thấy ngay thay đổi.
2. **Ai có quyền ghi?** Một writer duy nhất, nhiều reader thường dễ kiểm soát hơn nhiều writer cùng sửa.
3. **Thao tác hợp lệ là gì?** Chỉ đọc một số, tăng bộ đếm, hay cập nhật nhiều trường thành một trạng thái nhất quán?
4. **Khi nào công việc kết thúc?** Quyền truy cập phải được thu hồi trước khi giải phóng bộ nhớ hoặc handle.

## 2. Bốn điều kiện của một giao thức đồng bộ đúng

**Loại trừ tương hỗ (mutual exclusion).** Với thao tác đọc–sửa–ghi, ví dụ tăng bộ đếm, không được để hai luồng cùng đọc giá trị cũ rồi ghi đè kết quả của nhau. Có thể dùng cùng một Java monitor, một dịch vụ Java thực hiện cập nhật nguyên tử, hoặc cơ chế native được thiết kế riêng cho vùng nhớ native.

**Khả năng nhìn thấy (visibility).** Một luồng ghi xong không có nghĩa một luồng khác lập tức thấy giá trị mới nếu thiếu quan hệ đồng bộ. Theo Java Memory Model, thao tác unlock trên một monitor **happens-before** thao tác lock đến sau trên chính monitor đó. Thread.start và việc một luồng hoàn tất trước khi thread khác join thành công cũng tạo các quan hệ happens-before cần thiết.

**Thứ tự và tính nguyên tử (ordering/atomicity).** Một phép ghi riêng lẻ có thể nhìn thấy nhưng chuỗi “đọc trạng thái → kiểm tra → cập nhật” vẫn không nguyên tử. Java volatile hữu ích cho quy tắc công bố/đọc một biến Java, song biểu thức tăng **value++** vẫn gồm nhiều bước. Từ khóa volatile của C/C++ không tương đương với Java volatile, cũng không thay thế C11/C++ atomics.

**Vòng đời (lifetime).** Khóa đúng không cứu được con trỏ trỏ đến vùng nhớ đã free, JNI reference hết hiệu lực, hoặc buffer bị giải phóng khi native còn thao tác. Vòng đời và đồng bộ phải là **một hợp đồng chung**, gồm cả đường lỗi, hủy tác vụ và shutdown.

Đặc biệt, Java Memory Model mô tả hành vi đồng bộ của Java. Đừng suy diễn rằng một **std::mutex** trong C++ tự động tương ứng với một **synchronized** của Java, hoặc Java VarHandle với C11 atomic tự động có cam kết tương thích trên mọi JVM/ABI. Nếu cần truy cập off-heap đồng thời trực tiếp từ hai ngôn ngữ, phải xác lập rõ giao thức bộ nhớ, alignment, kiểu dữ liệu, thứ tự thao tác, khả năng hỗ trợ nền tảng và kiểm thử tương thích. Phương án ít rủi ro hơn là đưa mọi cập nhật qua **một phía chịu trách nhiệm đồng bộ**.

## 3. Chọn chiến lược theo loại trạng thái

### 3.1. Java giữ trạng thái: cùng một Java monitor qua JNI

Nếu dữ liệu là field của object Java, Java có thể dùng **synchronized(lock)** và native dùng **MonitorEnter/MonitorExit** của JNI trên **chính object lock đó**. Không được đồng bộ Java trên một object nhưng C chỉ khóa một mutex riêng rồi giả định hai khóa bảo vệ cùng trạng thái.

Các phép truy cập field qua JNI phải nằm trong critical section tương ứng. Mọi đường đi rời khỏi vùng đã MonitorEnter thành công đều phải MonitorExit, kể cả khi JNI phát sinh exception. MonitorExit không được dùng để “thoát hộ” một monitor mà Java đã vào bằng từ khóa synchronized; và return của một phương thức synchronized Java không tự thoát một monitor do JNI MonitorEnter tạo ra.

Một lựa chọn khác là native **gọi một phương thức Java đã đồng bộ đúng** (chẳng hạn phương thức dùng AtomicInteger.incrementAndGet) qua JNI, thay vì tự đọc/ghi field. Chi phí gọi có thể cao hơn, nhưng hợp đồng nhất quán và dễ bảo trì hơn.

### 3.2. Native giữ trạng thái: đóng gói thao tác hoặc trao đổi snapshot

Nếu nhiều luồng C/C++ sở hữu một cấu trúc native, hãy để thư viện native quản lý mutex/atomic và cung cấp cho Java những thao tác có ngữ nghĩa hoàn chỉnh như “lấy snapshot nhất quán”, “cộng một lượng”, “đặt cấu hình”. Java không nên tự sửa byte của cấu trúc khi native đang giữ mutex mà Java không tham gia.

Đối với dữ liệu lớn, mẫu **snapshot → xử lý → công bố kết quả** giảm thời gian nắm khóa: sao chép trạng thái dưới khóa, xử lý trên bản sao, sau đó kiểm tra version hoặc thay thế trạng thái dưới khóa. Đừng đọc nhiều field độc lập rồi coi chúng là một snapshot nhất quán nếu writer có thể cập nhật giữa chừng.

### 3.3. Vùng nhớ off-heap thực sự chia sẻ

Chọn một trong các thiết kế rõ ràng: một writer và cơ chế công bố được kiểm chứng; lock/callback qua một tầng cầu nối; hoặc giao thức atomic đã được xác nhận tương thích ở cả JVM và native ABI cụ thể. Phải chỉ ra **địa chỉ + kích thước + alignment + byte order + ai giải phóng + điều kiện kết thúc**.

Shared memory, DirectByteBuffer hay Arena.ofShared cho phép truy cập bộ nhớ từ nhiều phía/luồng, nhưng không cung cấp mặc định “mỗi read/write đều không race”. Plain ByteBuffer.getInt/putInt không nên được coi là cách thay thế một giao thức atomic cho cấu trúc chia sẻ giữa C và Java.

## 4. Ví dụ chạy được trên Java 17+: Java và JNI cùng tăng một bộ đếm

Ví dụ cố ý giữ trạng thái ở **Java heap**. Hai luồng Java chạy đồng thời: một luồng tăng bằng mã Java, luồng còn lại gọi mã C qua JNI. Cả hai dùng **cùng monitor lock**. Mỗi luồng tăng 100.000 lần; giá trị cuối phải là 200.000.

**Tệp SharedCounterDemo.java**

~~~java
public final class SharedCounterDemo {
    static {
        System.loadLibrary("sharedcounter");
    }

    private final Object lock = new Object();
    private int value;

    private native void incrementNative(int times);

    private void incrementJava(int times) {
        for (int i = 0; i < times; i++) {
            synchronized (lock) {
                value++;
            }
        }
    }

    private int currentValue() {
        synchronized (lock) {
            return value;
        }
    }

    public static void main(String[] args) throws InterruptedException {
        final int times = 100_000;
        SharedCounterDemo counter = new SharedCounterDemo();

        Thread javaThread = new Thread(
                () -> counter.incrementJava(times), "java-writer");
        Thread nativeThread = new Thread(
                () -> counter.incrementNative(times), "jni-writer");

        javaThread.start();
        nativeThread.start();
        javaThread.join();
        nativeThread.join();

        System.out.println(counter.currentValue());
    }
}
~~~

**Tệp sharedcounter.c**

~~~c
#include <jni.h>

JNIEXPORT void JNICALL
Java_SharedCounterDemo_incrementNative(
        JNIEnv *env, jobject self, jint times) {
    jclass cls = (*env)->GetObjectClass(env, self);
    if (cls == NULL) {
        return;  /* Có thể có exception đang chờ. */
    }

    jfieldID lockField = (*env)->GetFieldID(
            env, cls, "lock", "Ljava/lang/Object;");
    if (lockField == NULL) {
        (*env)->DeleteLocalRef(env, cls);
        return;
    }

    jfieldID valueField = (*env)->GetFieldID(
            env, cls, "value", "I");
    if (valueField == NULL) {
        (*env)->DeleteLocalRef(env, cls);
        return;
    }

    jobject lock = (*env)->GetObjectField(env, self, lockField);
    if (lock == NULL) {
        (*env)->DeleteLocalRef(env, cls);
        return;
    }

    for (jint i = 0; i < times; ++i) {
        if ((*env)->MonitorEnter(env, lock) != JNI_OK) {
            break;
        }

        jint previous = (*env)->GetIntField(
                env, self, valueField);
        if (!(*env)->ExceptionCheck(env)) {
            (*env)->SetIntField(env, self, valueField, previous + 1);
        }

        /* Đã vào monitor bằng JNI thì phải ra bằng JNI. */
        jint exitStatus = (*env)->MonitorExit(env, lock);
        if (exitStatus != JNI_OK || (*env)->ExceptionCheck(env)) {
            break;
        }
    }

    (*env)->DeleteLocalRef(env, lock);
    (*env)->DeleteLocalRef(env, cls);
}
~~~

Chữ ký JNI bên C tương ứng với native method **incrementNative(int)** của lớp không có package và không overload. Trong ứng dụng thực tế, dùng header do **javac -h** sinh ra để đối chiếu chữ ký thay vì tự đoán tên hàm.

**Biên dịch và chạy trên Linux với JDK 17+ và GCC** (JAVA_HOME trỏ tới thư mục JDK):

~~~bash
javac -h . SharedCounterDemo.java
gcc -std=c11 -O2 -fPIC -shared \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  -o libsharedcounter.so sharedcounter.c
java -Djava.library.path=. SharedCounterDemo
~~~

**stdout khi biên dịch/nạp thư viện thành công:**

~~~text
200000
~~~

Trên macOS, JNI headers dùng thư mục **include/darwin** và thư viện động dùng hậu tố **.dylib**; trên Windows, headers dùng **include/win32** và thư viện **.dll**. Lệnh build thư viện native phụ thuộc compiler/nền tảng, còn mã Java/C và hợp đồng monitor không đổi.

### Vì sao ví dụ này đúng?

1. Cả Java và C cùng lấy object **lock** từ đúng instance **counter**. JNI MonitorEnter tranh quyền sở hữu **chính monitor** mà synchronized(lock) sử dụng.
2. Phép **đọc value → cộng 1 → ghi value** nằm trọn trong critical section, vì vậy không mất cập nhật do hai writer xen kẽ.
3. MonitorExit thực thi sau mỗi MonitorEnter thành công, kể cả khi một thao tác field để lại exception đang chờ. C không để quên khóa trên đường đi thông thường.
4. Java gọi **join()** cả hai luồng trước khi đọc kết quả; đọc cuối cùng cũng nằm trong synchronized(lock). Không dựa vào sleep hoặc lịch lập lịch luồng.
5. Field **value** không cần volatile vì **mọi** truy cập trong ví dụ đều theo cùng quy ước monitor. Nếu thêm bất kỳ reader/writer không khóa nào, lập luận này không còn đúng.

**Phản ví dụ:** Bỏ synchronized ở Java hoặc bỏ MonitorEnter/MonitorExit ở C sẽ phá hợp đồng chung. Kết quả *có thể* nhỏ hơn 200.000 hoặc tình cờ vẫn bằng 200.000; một lần chạy “đúng” không chứng minh mã không race. Cũng không được đổi khóa phía Java thành **synchronized(this)** trong khi phía C vẫn khóa field **lock**: đó là hai monitor khác nhau.

Mã C ở đây minh họa JNI thread đã được JVM gọi từ Java. Nó không tạo pthread riêng và không làm việc trực tiếp với con trỏ tới Java heap. Các đường lỗi khi tra class/field có thể để lại JNI exception cho JVM xử lý; trong mã sản xuất cần thiết kế rõ chính sách truyền lỗi và theo dõi, thay vì âm thầm coi thao tác đã thành công.

## 5. Mảng Java, bản sao và vùng nhớ critical

**GetIntArrayElements / ReleaseIntArrayElements** có thể cho pointer tới vùng mảng thực hoặc một bản sao. Nếu native sửa phần tử, chỉ sau thao tác Release với chế độ phù hợp mới có thể dựa vào việc bản sao đã được chép lại. Không giữ pointer để thread native sử dụng bất đồng bộ sau khi Release. Nếu chỉ cần đọc/ghi một vùng nhỏ, các API **GetIntArrayRegion / SetIntArrayRegion** thường tạo hợp đồng copy rõ hơn.

**GetPrimitiveArrayCritical / ReleasePrimitiveArrayCritical** có ràng buộc nghiêm ngặt hơn: giữ đoạn critical thật ngắn; trong khoảng này không gọi JNI khác hoặc syscall có thể chặn chờ luồng Java, không khóa rồi đợi I/O hay callback. VM có thể hạn chế di chuyển heap/GC trong thời gian đó và vẫn có thể cấp một bản sao. “Critical” trong tên API **không phải** khóa bảo vệ các luồng Java đồng thời sửa cùng mảng.

Với cả hai nhóm API, phải phân biệt **pointer lifetime**, **thời điểm copy back**, và **synchronization giữa các luồng**; ba điều kiện này không thay thế được nhau. Nếu có nhiều writer, ưu tiên thao tác ngắn có khóa/copy nhất quán hoặc chuyển công việc cho một owner duy nhất.

## 6. DirectByteBuffer và FFM: truy cập được chưa có nghĩa an toàn đồng thời

**DirectByteBuffer**: Java có thể tạo buffer bằng ByteBuffer.allocateDirect; JNI có thể lấy địa chỉ qua GetDirectBufferAddress (kiểm tra kết quả NULL và dung lượng). Nếu native cấp phát rồi dùng NewDirectByteBuffer bọc địa chỉ ấy, native phải bảo đảm vùng nhớ vẫn hợp lệ cho tới khi Java ngừng truy cập. Việc giải phóng native memory không được dựa vào việc phía Java “chắc đã dùng xong”. Đặc biệt, **NewDirectByteBuffer** ban đầu có byte order big-endian theo đặc tả JNI; hãy chọn byte order một cách tường minh trước khi diễn giải struct nhiều byte.

Với **FFM API chính thức từ JDK 22** (package java.lang.foreign), MemorySegment mang bounds và scope; Arena quyết định thời gian sống vùng nhớ. **Arena.ofConfined()** chỉ cho owner thread truy cập segment tương ứng; **Arena.ofShared()** cho phép nhiều thread truy cập nhưng **không tự khóa các phép cập nhật**. Đóng Arena chỉ sau khi mọi tác vụ native/callback không còn sử dụng địa chỉ đã cấp; native pointer giữ riêng có thể vượt ngoài khả năng kiểm tra vòng đời từ phía Java.

Ví dụ sau chỉ minh họa **cấp phát và giới hạn vòng đời**, không thực hiện truy cập đồng thời; yêu cầu JDK 22+:

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

public class SegmentLifetimeDemo {
    public static void main(String[] args) {
        try (Arena arena = Arena.ofShared()) {
            MemorySegment segment = arena.allocate(
                    ValueLayout.JAVA_INT);
            segment.set(ValueLayout.JAVA_INT, 0, 42);
            System.out.println(
                    segment.get(ValueLayout.JAVA_INT, 0));
        }
    }
}
~~~

~~~text
42
~~~

Trong ví dụ FFM, nhãn **shared** mô tả quyền truy cập của các thread, không phải cam kết rằng **get rồi set** là một phép tăng nguyên tử. Khi xây dựng giao thức chia sẻ với C/C++, phải thống nhất kiểu số, thứ tự byte, canh hàng, liveness, quy tắc công bố, và phương thức atomic/lock thực sự có bảo đảm trên stack được hỗ trợ. Không ghép tùy ý **C volatile**, Java plain get/set và hy vọng cache tự nhất quán.

## 7. Native tự tạo thread, callback và lock ordering

Trong ví dụ JNI, C chạy trên thread đã gọi native method, nên được nhận **JNIEnv*** hợp lệ cho thread đó. Nếu thư viện tự tạo thread C/C++ và muốn gọi ngược vào JVM, thread đó phải attach bằng **JavaVM.AttachCurrentThread** (nếu chưa attach), nhận JNIEnv* của chính nó, rồi detach tại điểm phù hợp. **Không chia sẻ JNIEnv*** giữa các native thread.

Reference JNI cục bộ chỉ có hiệu lực trong phạm vi nhất định của thread/lời gọi native. Nếu native lưu Java object để callback sau khi lời gọi đã trả về, phải cân nhắc **NewGlobalRef** và giải phóng bằng **DeleteGlobalRef** khi chắc chắn không dùng nữa. Global reference không tự làm dữ liệu bên trong object an toàn đồng thời.

Tránh giữ Java monitor khi gọi native operation có thể chặn lâu, hoặc giữ native mutex khi gọi callback Java không kiểm soát. Nếu quy trình buộc phải dùng cả hai khóa, đặt một **thứ tự lấy khóa thống nhất** trong tất cả đường đi. Ví dụ: thread A giữ Java monitor rồi chờ native mutex, thread B giữ native mutex rồi gọi Java callback cần cùng monitor → deadlock. Không dùng busy-wait/sleep để “chữa” vấn đề thứ tự khóa.

Khi shutdown, quy trình an toàn thường là: ngừng tiếp nhận công việc mới → báo dừng → chờ tất cả tác vụ đang dùng tài nguyên hoàn tất → thu hồi callback/global refs → free native memory/close handle. Không free trước rồi mới đợi thread dừng.

## 8. Thiết kế hợp đồng chia sẻ trước khi viết mã

Một hợp đồng nên ghi rõ:

| Thành phần | Ví dụ quyết định cần có |
| --- | --- |
| Owner | Java sở hữu counter trên heap; native chỉ truy cập qua JNI dưới monitor. |
| Writer/readers | Java worker và JNI worker cùng ghi; mọi reader cũng dùng cùng monitor. |
| Vùng nguyên tử | Toàn bộ thao tác đọc–cộng–ghi, không chỉ riêng lẻ phép đọc hoặc phép ghi. |
| Cơ chế công bố | MonitorExit trước lần MonitorEnter sau trên đúng object; join trước tổng kết. |
| Vòng đời | Instance còn sống suốt hai thread; không lưu JNI local ref qua lời gọi. |
| Lỗi/hủy | Bảo đảm unlock trong mọi nhánh; xác định cách đưa native exception/status về Java. |
| ABI nếu off-heap | Kích thước field, alignment, byte order, version cấu trúc, quyền free và thời điểm free. |

Nếu chỉ một bên cần thay đổi state, cân nhắc dùng **message passing**: bên Java gửi yêu cầu qua một worker/queue có đồng bộ, native xử lý và trả kết quả/snapshot. Giảm vùng nhớ ghi chung thường dễ chứng minh đúng hơn một cấu trúc off-heap cho phép hai ngôn ngữ tự sửa tùy lúc.

## 9. Lỗi thường gặp và cách phát hiện

| Triệu chứng hoặc lỗi | Nguyên nhân | Hướng sửa |
| --- | --- | --- |
| Bộ đếm thấp hơn kỳ vọng, thỉnh thoảng mới sai | Hai writer cùng đọc–sửa–ghi mà không khóa chung | Dùng cùng monitor JNI/Java hoặc một API cập nhật nguyên tử tại owner. |
| Reader thấy trạng thái cũ hay nửa cập nhật | Không có quan hệ công bố/nhìn thấy, đọc nhiều field ngoài khóa | Dùng cùng cơ chế acquire/release hoặc snapshot dưới khóa. |
| Java synchronized, C std::mutex nhưng vẫn sai | Hai khóa thuộc hai miền độc lập | Chuyển cập nhật qua một bridge đồng bộ duy nhất hoặc giao thức off-heap được chứng minh. |
| Crash trong JNI/FFM, dữ liệu bị hỏng ngẫu nhiên | Pointer quá hạn, buffer đã free, sai bounds/alignment/ABI | Thiết kế ownership, kiểm tra size/offset, chờ tác vụ trước free. |
| Kết quả mảng không xuất hiện ngay phía Java | JNI cấp bản sao hoặc chưa Release đúng | Phân biệt copy back và đồng bộ; Release theo hợp đồng API. |
| Treo chương trình/GC pause dài bất thường | Giữ critical array quá lâu, chờ I/O khi đang pin, lock inversion | Thu hẹp critical section, bỏ blocking/callback, chuẩn hóa thứ tự khóa. |
| Native thread gọi JNI lỗi khó đoán | Dùng JNIEnv* của thread khác, reference sai vòng đời | Attach thread riêng, dùng global ref khi cần, detach/cleanup đúng lúc. |
| Test chạy ổn nhưng production vẫn race | Test chỉ chạy một scheduling và một nền tảng | Stress nhiều lần, kiểm tra trên cấu hình và ABI thật, kiểm thử lỗi/shutdown. |

### Kiểm thử có chủ đích

- Chạy ví dụ với **-Xcheck:jni** để phát hiện thêm nhiều sai phạm JNI, rồi lặp lại test với lượng thao tác lớn hơn. Kiểm tra cả giá trị cuối và việc không có exception/native crash.
- Stress nhiều luồng đọc/ghi, ép xen kẽ bằng barriers/latches **trong test**, thay vì kết luận từ một lần chạy hoặc dùng sleep làm cơ chế đồng bộ.
- Kiểm thử khi hủy tác vụ, exception JNI, shutdown và native callback đang hoạt động. Theo dõi deadlock và lỗi sử dụng sau giải phóng.
- Với C/C++, dùng công cụ kiểm tra bộ nhớ/race phù hợp với native code và nền tảng, nhưng nhớ rằng chúng không tự chứng minh toàn bộ Java Memory Model và tương tác qua JVM là đúng.
- Đối với off-heap, kiểm tra nhiều kiến trúc/compiler/JVM mà sản phẩm thực sự hỗ trợ; thử sai lệch alignment/endianness/version để bảo đảm phần kiểm tra đầu vào không bỏ sót.

## 10. Tự kiểm tra hiểu biết

1. Nếu Java dùng synchronized(lock) mà C chỉ khóa pthread mutex trước khi SetIntField, vì sao giá trị vẫn có thể mất cập nhật?
2. Vì sao không thể giải quyết một phép **value++** chung bằng cách thêm Java volatile hoặc C volatile một cách độc lập?
3. Nếu native lưu địa chỉ GetDirectBufferAddress để ghi sau khi native method trả về, bạn sẽ chứng minh buffer và bộ nhớ nền còn sống bằng cách nào?
4. Khi một callback native giữ native mutex và cần vào synchronized Java, còn một Java thread giữ monitor rồi chờ native mutex, deadlock hình thành như thế nào?
5. Vì sao Arena.ofShared khác với cơ chế đồng bộ dữ liệu, và khi nào cần thiết kế một owner/queue/snapshot thay cho vùng nhớ ghi chung?

**Kết luận kỹ thuật:** Chỉ coi dữ liệu Java/native là “được đồng bộ” khi tất cả read/write xung đột cùng tuân theo một hợp đồng về atomicity, visibility, ordering **và** lifetime. Bắt đầu bằng ranh giới sở hữu và một điểm đồng bộ chung; chỉ chọn giao thức off-heap phức tạp hơn khi thực sự cần và có thể kiểm chứng nó trên các nền tảng được hỗ trợ.

## Tài liệu chuẩn để đối chiếu

- [Java Language Specification §17 — Threads and Locks (Java 17)](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html): monitor, happens-before và data race.
- [JNI Functions (Java 17)](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/functions.html): MonitorEnter/MonitorExit, array critical APIs, JNI references và direct buffers.
- [Foreign Function and Memory API (Java 22)](https://docs.oracle.com/en/java/javase/22/core/foreign-function-and-memory-api.html): MemorySegment, Arena, giới hạn bộ nhớ và tương tác native.
