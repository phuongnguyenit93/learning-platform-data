# Reachability, weak reference và vòng đời đối tượng

Trong Java 27, **garbage collector (GC)** tự động quản lý phần lớn bộ nhớ dành cho đối tượng. Lập trình viên thường không phải tự gọi một hàm để giải phóng từng đối tượng như trong những hệ thống quản lý bộ nhớ thủ công. Tuy nhiên, **GC không thể đoán được một đối tượng còn có ích về mặt nghiệp vụ hay không**: nó chủ yếu phân tích đối tượng còn có thể được truy cập từ những nguồn tham chiếu đang sống (*reachability*) hay không.

Sự khác biệt giữa **một đối tượng vẫn được tham chiếu** và **một đối tượng thực sự cần thiết** tạo ra nhiều lỗi khó phát hiện, chẳng hạn cache giữ dữ liệu vô hạn, listener không được hủy đăng ký, task giữ lại dữ liệu request, hoặc tài nguyên ngoài heap không được đóng. Java cung cấp nhóm **java.lang.ref** để thể hiện các mức độ tham chiếu khác nhau, trong đó **WeakReference**, **ReferenceQueue**, **PhantomReference** và **Cleaner** là các công cụ quan trọng.

Bài học thuộc chương **JVM, bộ nhớ và thu gom rác** của mô-đun **Java 27 và các kiến thức liên quan**, tập trung vào những cơ chế **vẫn áp dụng trong Java 27**. Không khuyến nghị xây dựng cleanup dựa trên **finalize()**, vì finalization đã bị đánh dấu *deprecated for removal*. Ví dụ sử dụng API chuẩn, không cần preview feature.

## 1. Trước hết: GC quản lý bộ nhớ, không quản lý mọi loại tài nguyên

Đối tượng Java có thể chứa dữ liệu trong heap, chẳng hạn **String**, **byte[]**, **List**, **Map** hoặc một record. Khi không còn cần thiết theo mô hình reachability của JVM, bộ nhớ dành cho đối tượng có thể được GC thu hồi.

Nhưng một đối tượng Java cũng có thể đại diện cho tài nguyên bên ngoài heap:

- File descriptor, socket, kết nối tới cơ sở dữ liệu.
- Native memory hoặc vùng bộ nhớ được cấp phát bên ngoài Java heap.
- Handle tới thiết bị hay thư viện native.
- Lock hoặc giấy phép truy cập tài nguyên cần được giải phóng theo hợp đồng ứng dụng.

GC không bảo đảm việc đóng những tài nguyên này vào đúng thời điểm bạn muốn. Vì thế, nguyên tắc thiết kế là:

**Đối tượng không còn reachable** và **tài nguyên đã được đóng an toàn** là **hai vấn đề khác nhau**.

Với tài nguyên có thể đóng, ưu tiên **AutoCloseable** và **try-with-resources**:

~~~java
import java.nio.file.Files;
import java.nio.file.Path;

try (var reader = Files.newBufferedReader(Path.of("data.txt"))) {
    System.out.println(reader.readLine());
}
~~~

Khối **try-with-resources** gọi **close()** khi rời phạm vi, kể cả khi xảy ra ngoại lệ. Không phải chờ GC để đóng file.

## 2. Reachability: đối tượng còn có thể được truy cập hay không?

Hãy hình dung các đối tượng trong heap như một **đồ thị**:

- Mỗi đối tượng là một nút.
- Một field, phần tử mảng hoặc biến có thể giữ tham chiếu tới đối tượng khác.
- JVM có những nguồn tham chiếu ban đầu (*GC roots*) dùng để xác định các đối tượng còn có thể truy cập.

~~~mermaid
flowchart TD
    R["GC root (ví dụ biến/stack đang sống)"] --> A["Service"]
    A --> B["Cache"]
    B --> C["Entry #1"]
    C --> D["byte[] dữ liệu"]
    X["Đối tượng rời rạc"] --> Y["Đối tượng con"]
~~~

Trong sơ đồ, nhóm **Service → Cache → Entry → byte[]** còn có đường đi từ root bằng các tham chiếu thông thường. Ngược lại, nếu **X → Y** không còn đường đi từ root và không có cơ chế tham chiếu đặc biệt khác giữ chúng, hai đối tượng có thể trở thành ứng viên để thu hồi.

### 2.1. GC roots gồm những gì?

Danh sách cụ thể phụ thuộc JVM và bộ thu gom rác, nhưng có thể hiểu về mặt khái niệm rằng GC bắt đầu từ các nguồn như:

- Những tham chiếu còn sống trong các luồng thực thi.
- Những field static còn được JVM xem là reachable.
- Các tham chiếu do runtime và native/JNI giữ.
- Các cấu trúc cần thiết để JVM quản lý hoạt động hiện tại.

Không nên xem đây là một danh sách cố định áp dụng giống hệt cho mọi JVM implementation. **Reachability là quan hệ có thể truy cập trong các phép tính còn tiếp diễn**, chứ không đơn giản là “một biến đã được khai báo trong method”.

### 2.2. Một đối tượng có thể trở thành unreachable trước khi method kết thúc

JIT có thể phân tích rằng chương trình **không còn sử dụng** một tham chiếu nữa, dù phạm vi cú pháp của biến vẫn chưa kết thúc.

~~~java
byte[] buffer = new byte[1024 * 1024];
int size = buffer.length;

System.out.println(size);

// Không còn thao tác nào cần buffer.
// JVM có thể xác định buffer không còn thiết yếu ở đây.
~~~

Vì vậy:

- Không thể khẳng định một đối tượng luôn sống đến cuối block/method.
- Gán biến về **null** không phải điều kiện bắt buộc để GC nhận ra đối tượng không còn cần thiết.
- Với các tài nguyên có cleanup quan sát được, đôi khi cần **Reference.reachabilityFence(...)** để xác định mốc cuối của strong reachability; nội dung này được giải thích ở phần sau.

## 3. Strong reference: tham chiếu thông thường

Tham chiếu strong là kiểu bạn dùng hằng ngày trong Java:

~~~java
class Payload {
    private final byte[] bytes = new byte[1024];

    int size() {
        return bytes.length;
    }
}

Payload payload = new Payload();
System.out.println(payload.size());
~~~

Khi **payload** còn được dùng như một strong reference, GC không được thu hồi đối tượng **Payload** chỉ vì bộ nhớ đang thiếu.

Tương tự, một field trong object reachable sẽ tiếp tục giữ những object mà field đó tham chiếu:

~~~java
import java.util.ArrayList;
import java.util.List;

final class Repository {
    private final List<byte[]> history = new ArrayList<>();

    void save(byte[] data) {
        history.add(data);
    }
}
~~~

Nếu **Repository** còn sống trong suốt vòng đời server và **history** không có cơ chế xóa/giới hạn, các mảng byte được lưu sẽ tiếp tục **strongly reachable**, dù ứng dụng không còn dùng tới từng mảng.

**Đây là một dạng giữ bộ nhớ không cần thiết về mặt ứng dụng**, không phải lỗi GC. JVM đang làm đúng khi giữ lại dữ liệu mà ứng dụng vẫn có thể truy cập.

### 3.1. “Memory leak” trong ngôn ngữ có GC

Trong Java, memory leak thường có nghĩa là **đối tượng không còn hữu ích nhưng vẫn bị giữ reachable**.

| Nguyên nhân | Đường giữ strong reference |
|---|---|
| Cache không có giới hạn | Static cache → Map → value |
| Listener không được unregister | Publisher → listener → service |
| Task hoàn thành nhưng vẫn giữ | Collection → Future → dữ liệu task |
| ThreadLocal không được dọn | Thread → ThreadLocal value |
| Callback/lambda capture object lớn | Callback còn sống → object bị capture |
| ClassLoader không được giải phóng | Registry → classloader / class / object plugin |
| Collection tăng mãi | Root → List/Map → mọi phần tử đã thêm |

Cách sửa thường là **thiết kế lại vòng đời và chính sách loại bỏ**, chứ không phải cố ép GC chạy nhiều hơn.

## 4. Các mức reachability trong java.lang.ref

Java định nghĩa nhiều mức reachability cho đối tượng, xét từ mạnh tới yếu:

1. **Strongly reachable**: còn đường đi từ root mà không phải đi qua referent của một Reference object.
2. **Softly reachable**: không còn strong path, nhưng còn đường đi qua soft reference.
3. **Weakly reachable**: không strong/soft reachable, nhưng còn đường đi qua weak reference.
4. **Phantom reachable**: không còn các dạng trên và được quan sát bằng phantom reference theo quy tắc của reference processing.
5. **Unreachable**: không còn reachable theo những quan hệ nói trên.

Sơ đồ khái niệm:

~~~mermaid
flowchart LR
    A["Strong"] --> B["Soft"]
    B --> C["Weak"]
    C --> D["Phantom"]
    D --> E["Unreachable"]
    E --> F["Bộ nhớ có thể được GC thu hồi"]
~~~

Sơ đồ **không phải máy trạng thái bắt buộc** mà mọi đối tượng đều lần lượt đi qua. Một đối tượng chỉ từng được tham chiếu strong có thể chuyển thẳng tới trạng thái unreachable khi không còn đường tham chiếu cần thiết.

| Loại tham chiếu | API tiêu biểu | Ý nghĩa |
|---|---|---|
| **Strong** | Tham chiếu Java thông thường | Giữ object sống khi còn đường reachable |
| **Soft** | **SoftReference<T>** | GC có thể xóa để đáp ứng nhu cầu bộ nhớ |
| **Weak** | **WeakReference<T>** | Không ngăn GC loại bỏ referent khi nó chỉ còn weakly reachable |
| **Phantom** | **PhantomReference<T>** | Theo dõi giai đoạn cuối vòng đời, không dùng để lấy lại referent |
| **Queue** | **ReferenceQueue<T>** | Nhận thông báo về thay đổi reachability khi reference được enqueue |
| **Cleaner** | **Cleaner** | Quản lý cleaning action dựa trên phantom reachability |

**Lưu ý về finalization:** Một số mô tả chi tiết trong Javadoc/JLS nhắc tới giai đoạn *finalization* như một phần định nghĩa lịch sử của vòng đời. Điều đó **không** có nghĩa nên viết **finalize()** mới. Java 27 xem finalization là cơ chế cần loại bỏ; hãy sử dụng vòng đời tài nguyên tường minh và Cleaner/PhantomReference khi có nhu cầu phù hợp.

## 5. WeakReference<T>: giữ đường truy cập yếu tới một object

**java.lang.ref.WeakReference<T>** là đối tượng wrapper chứa một tham chiếu yếu tới *referent*.

Ví dụ:

~~~java
import java.lang.ref.WeakReference;

Object value = new Object();

WeakReference<Object> weak = new WeakReference<>(value);

System.out.println(weak.get() == value); // true

value = null;

// Sau thời điểm này, nếu không còn strong/soft path nào khác,
// referent có thể được GC nhận diện là weakly reachable.
~~~

Lệnh **new WeakReference<>(value)** không tạo bản sao của **value**. Nó tạo một đối tượng **WeakReference** độc lập chứa quan hệ tham chiếu yếu.

### 5.1. get() có thể trả null bất kỳ khi nào referent được clear

~~~java
Object strong = weak.get();

if (strong != null) {
    // Trong block này, strong là tham chiếu mạnh tới object lấy được.
    System.out.println(strong.getClass().getSimpleName());
} else {
    System.out.println("Referent đã được clear");
}
~~~

**weak.get()** có thể trả **null** khi referent đã bị xóa bởi GC hoặc bởi **weak.clear()** do chương trình gọi.

Không dựa vào việc nó sẽ trở thành **null** sau một khoảng chờ cố định. GC chọn thời điểm thực thi dựa trên áp lực bộ nhớ, collector, cấu hình và lịch chạy.

### 5.2. Dùng kết quả get() một lần rồi giữ strong reference cục bộ

Cách dễ gây race về mặt ý tưởng:

~~~java
// Tránh gọi get() hai lần rồi cho rằng kết quả không đổi.
if (weak.get() != null) {
    System.out.println(weak.get().toString());
}
~~~

Giữa hai lần gọi, referent có thể bị clear nếu không còn strong reference nào khác giữ nó.

Cách đúng:

~~~java
Object object = weak.get();

if (object != null) {
    System.out.println(object.toString());
}
~~~

Khi **get()** trả về đối tượng không null, biến **object** giữ strong reference trong phần sử dụng tiếp theo, nhờ đó object không bị thu hồi giữa chừng trong lúc thực sự cần nó.

### 5.3. WeakReference không phải weak field

Ví dụ:

~~~java
final class Holder {
    final WeakReference<Object> payload;

    Holder(Object value) {
        this.payload = new WeakReference<>(value);
    }
}
~~~

**Holder** có thể sống lâu, nhưng field **payload** chỉ giữ mạnh **WeakReference object**, **không giữ mạnh referent** nằm bên trong.

Nếu **Holder** có thêm một field mạnh tới cùng referent:

~~~java
final class AccidentalRetention {
    final Object strongValue;
    final WeakReference<Object> weakValue;

    AccidentalRetention(Object value) {
        strongValue = value;
        weakValue = new WeakReference<>(value);
    }
}
~~~

Thì **weakValue** gần như không giúp gì về khả năng thu hồi khi **strongValue** vẫn còn reachable.

## 6. Ví dụ chạy được: hiểu weak.get() và clear()

Để kiểm thử hành vi **WeakReference.get()** một cách xác định, hãy dùng **clear()** chủ động. Ví dụ này **không cố chứng minh GC đã chạy**.

Tạo file **WeakReferenceDemo.java**:

~~~java
import java.lang.ref.WeakReference;

public class WeakReferenceDemo {

    record ImageData(String name, byte[] pixels) {}

    public static void main(String[] args) {
        ImageData image = new ImageData(
            "cover",
            new byte[1024]
        );

        WeakReference<ImageData> weak =
            new WeakReference<>(image);

        ImageData firstRead = weak.get();

        System.out.println(firstRead != null);
        System.out.println(firstRead.name());

        weak.clear();

        ImageData afterClear = weak.get();

        System.out.println(afterClear == null);
        System.out.println(firstRead.name());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac WeakReferenceDemo.java
java WeakReferenceDemo
~~~

Kết quả:

~~~text
true
cover
true
cover
~~~

**Giải thích quan trọng:**

- **clear()** làm wrapper **WeakReference** không còn trỏ tới referent.
- Nó **không hủy object** đang được biến **image** hoặc **firstRead** giữ mạnh.
- Lệnh **weak.clear()** không báo rằng GC đã thu hồi bộ nhớ.
- Khi **firstRead** còn giữ dữ liệu, dòng cuối vẫn truy cập được **name()** bình thường.

Đây là ví dụ thích hợp để kiểm thử **API semantics**. Không nên biến kiểm thử này thành một giả thuyết về thời điểm GC.

## 7. Vì sao không kiểm thử bằng System.gc()?

Một ví dụ trên Internet thường viết:

~~~java
Object value = new Object();
WeakReference<Object> weak = new WeakReference<>(value);

value = null;

System.gc();
System.out.println(weak.get()); // Không có cam kết là null.
~~~

**System.gc()** chỉ gửi yêu cầu/hint để JVM cân nhắc thực hiện GC. Nó có thể bị bỏ qua hoặc hành xử khác nhau tùy JVM options và collector.

Ngay cả khi GC xảy ra, các tham chiếu khác hoặc tối ưu hóa của JVM có thể khiến kết quả không đúng với phỏng đoán đơn giản.

**Nguyên tắc:**

- Unit test kiểm tra logic weak reference bằng cách điều khiển **clear()** và trạng thái ứng dụng.
- Khi cần quan sát GC thực tế, thực hiện phép thử tích hợp riêng và chấp nhận tính không xác định của thời điểm.
- Không dùng **Thread.sleep(1000)** hay số lần gọi **System.gc()** để biến một bất định thành điều kiện pass/fail trong CI.
- Không dùng **Runtime.freeMemory()** đơn lẻ để kết luận một object cụ thể đã được thu hồi.

## 8. ReferenceQueue<T>: quan sát thời điểm reference được enqueue

**ReferenceQueue<T>** cho phép chương trình nhận các Reference object mà GC đã xử lý theo quy tắc của từng loại reference.

Một **WeakReference** có thể được đăng ký với queue:

~~~java
import java.lang.ref.ReferenceQueue;
import java.lang.ref.WeakReference;

ReferenceQueue<Object> queue = new ReferenceQueue<>();

Object value = new Object();
WeakReference<Object> reference =
    new WeakReference<>(value, queue);
~~~

Khi referent trở thành weakly reachable và được xử lý:

1. GC có thể clear weak reference.
2. Reference đã được đăng ký có thể được đưa vào queue.
3. Code ứng dụng có thể lấy Reference object bằng **queue.poll()**, hoặc chờ bằng **queue.remove()**.

### 8.1. poll() và remove()

| API | Hành vi |
|---|---|
| **queue.poll()** | Trả Reference đang có trong queue, hoặc **null** nếu chưa có |
| **queue.remove()** | Chờ cho đến khi có Reference |
| **queue.remove(timeoutMillis)** | Chờ tối đa một thời hạn tính bằng mili giây theo API |
| **reference.get()** | Với WeakReference, trả referent nếu chưa bị clear, ngược lại **null** |
| **reference.clear()** | Xóa tham chiếu, **không tự enqueue** Reference |

Nếu muốn tránh việc chờ vô hạn, ưu tiên **poll()** tại điểm xử lý phù hợp hoặc **remove(timeout)** khi có chính sách lifecycle rõ ràng.

### 8.2. Queue không tự giữ mọi Reference object đã đăng ký

Một điều dễ bỏ sót: **ReferenceQueue không mạnh tay giữ toàn bộ WeakReference đăng ký với nó** để bảo đảm chúng được enqueue sau này.

~~~java
ReferenceQueue<Object> queue = new ReferenceQueue<>();

new WeakReference<>(new Object(), queue);

// Không giữ WeakReference object trong biến/collection nào.
// Wrapper này cũng có thể trở thành unreachable.
~~~

Nếu muốn chắc chắn chương trình còn cơ hội nhận và xử lý một Reference object, hãy **giữ mạnh chính Reference object đó** trong một cấu trúc riêng cho tới khi công việc quan sát kết thúc.

Đây cũng là lý do những cấu trúc như cache/registry có thể cần map từ WeakReference wrapper tới metadata phục vụ cleanup.

## 9. Ví dụ ReferenceQueue có metadata được giữ riêng

Một bộ theo dõi đơn giản muốn ghi nhãn cho những object đã bị clear, nhưng không được để metadata vô tình giữ object sống mãi.

Lưu file **WeakQueueDemo.java**:

~~~java
import java.lang.ref.Reference;
import java.lang.ref.ReferenceQueue;
import java.lang.ref.WeakReference;
import java.util.IdentityHashMap;
import java.util.Map;

public class WeakQueueDemo {

    static final class Tracker<T> {
        private final ReferenceQueue<T> queue =
            new ReferenceQueue<>();

        private final Map<Reference<? extends T>, String> labels =
            new IdentityHashMap<>();

        void track(T referent, String label) {
            WeakReference<T> reference =
                new WeakReference<>(referent, queue);

            labels.put(reference, label);
        }

        void drainQueue() {
            Reference<? extends T> reference;

            while ((reference = queue.poll()) != null) {
                String label = labels.remove(reference);

                if (label != null) {
                    System.out.println(
                        "Tham chiếu đã được enqueue: " + label
                    );
                }
            }
        }

        int trackedCount() {
            return labels.size();
        }
    }

    public static void main(String[] args) {
        Tracker<byte[]> tracker = new Tracker<>();

        byte[] data = new byte[4096];
        tracker.track(data, "buffer-A");

        System.out.println("Tracked: " + tracker.trackedCount());

        data = null;
        tracker.drainQueue();

        System.out.println(
            "Remaining (phụ thuộc GC): " + tracker.trackedCount()
        );
    }
}
~~~

Biên dịch:

~~~bash
javac WeakQueueDemo.java
java WeakQueueDemo
~~~

**Không có cam kết** rằng chương trình sẽ in dòng **“Tham chiếu đã được enqueue”** trong lần chạy ngắn này. Một đối tượng mới chỉ được bỏ strong reference có thể chưa được GC xử lý.

### 9.1. Vì sao dùng IdentityHashMap?

**Reference object** trong ví dụ được dùng làm khóa, với nhận dạng dựa trên **chính wrapper instance**. **IdentityHashMap** thể hiện trực tiếp mục đích đó.

**labels** giữ mạnh Reference wrapper để nó vẫn còn tồn tại và được nhận từ queue. Giá trị **String label** không chứa strong reference tới referent, nên nó không cản trở việc referent được GC thu hồi.

Tracker này là **mẫu học tập không thread-safe**. Nếu nhiều thread cùng gọi **track** và **drainQueue**, phải đồng bộ hoặc dùng cấu trúc phù hợp. Khi một ứng dụng không phát sinh GC trong thời gian dài, tracker cũng có thể giữ nhiều metadata/reference wrapper lâu hơn mong đợi; cần chính sách xóa, đóng hoặc giới hạn vòng đời.

### 9.2. Queue có phải callback được thực thi đúng lúc GC không?

**Không.** ReferenceQueue chỉ cung cấp nơi quan sát các Reference object đã được enqueue. Nó không bảo đảm thời điểm sự kiện đến, và không tự chạy code nghiệp vụ thay cho bạn.

Không dùng ReferenceQueue làm scheduler có deadline chính xác hoặc cơ chế đóng socket/bảo toàn giao dịch quan trọng.

## 10. WeakHashMap: weak keys, nhưng không phải weak values

**java.util.WeakHashMap<K,V>** là Map có **khóa (keys) được giữ theo quan hệ yếu**. Khi một key không còn được giữ mạnh ở nơi khác, GC có thể thu hồi key và entry tương ứng có thể biến mất khỏi map.

~~~java
import java.util.Map;
import java.util.WeakHashMap;

Map<Object, String> descriptions = new WeakHashMap<>();

Object key = new Object();

descriptions.put(key, "Tạm thời");

System.out.println(descriptions.get(key)); // Tạm thời

key = null;

// Entry có thể bị loại bỏ về sau khi GC xử lý key.
~~~

**Không dựa vào descriptions.size() giảm ngay sau khi gán key = null.** WeakHashMap có sự thay đổi do GC và xử lý queue; kích thước được quan sát có thể thay đổi không theo các thao tác put/remove trực tiếp.

### 10.1. Trường hợp phù hợp

- Gắn metadata phụ vào một object nhưng không muốn metadata giữ object sống mãi.
- Một số kiểu canonicalization hoặc registry mà key có vòng đời do thành phần khác quản lý.
- Các trường hợp có thể chấp nhận entry biến mất không xác định thời điểm.

Không dùng WeakHashMap để giữ dữ liệu **bắt buộc phải còn tồn tại** tới khi hoàn thành giao dịch hoặc thanh toán.

### 10.2. Bẫy lớn: value có thể giữ lại key

WeakHashMap chỉ yếu ở **khóa**. Nó giữ **value** bằng strong reference thông thường.

~~~java
import java.util.Map;
import java.util.WeakHashMap;

record Value(Object owner) {}

Map<Object, Value> map = new WeakHashMap<>();

Object key = new Object();

map.put(key, new Value(key));

key = null;
~~~

Đường giữ tham chiếu vẫn có thể là:

~~~text
Strong reference tới map
    |
    v
Map entry --strong--> Value
                      |
                      +--strong--> key
~~~

Dù map dùng weak key, **Value(owner)** đang giữ **key** bằng strong reference, nên key vẫn còn reachable qua chính value. Entry có thể không bao giờ tự biến mất khi map vẫn còn sống.

Cách sửa là **không để value tham chiếu mạnh lại key**, trực tiếp hoặc qua chuỗi object khác. Cần xem toàn bộ đồ thị tham chiếu, không chỉ kiểu Map được khai báo.

### 10.3. Những giới hạn khác của WeakHashMap

- **WeakHashMap không thread-safe**.
- Entry có thể biến mất khi GC chạy, vì vậy không sử dụng để làm nơi lưu dữ liệu nghiệp vụ bắt buộc.
- Key được so sánh theo quy tắc **equals/hashCode** của Map, không nhất thiết là đồng nhất object.
- Nếu dùng key như **String interned**, enum hoặc những object được JVM/ứng dụng giữ mạnh lâu dài, key có thể không bị thu hồi như bạn mong đợi.
- Khi cần cache có giới hạn dung lượng, thời gian hết hạn, thống kê và chính sách loại bỏ ổn định, thường cần một **bounded cache** với eviction rõ ràng, không nên trông đợi riêng GC và weak keys.

### 10.4. Vì sao không dùng WeakHashMap làm cache mọi trường hợp?

Với cache bình thường, bạn có thể muốn:

- Giữ dữ liệu trong 5 phút.
- Giữ tối đa 10.000 entry.
- Ưu tiên loại bỏ entry ít dùng.
- Theo dõi hit/miss và footprint.
- Không đánh mất một kết quả đang được nhiều request sử dụng.

WeakHashMap không tự bảo đảm các chính sách đó. Nó chỉ giải quyết một quan hệ reachability đặc biệt dành cho key.

## 11. SoftReference: liên hệ với cache và áp lực bộ nhớ

**SoftReference<T>** là tham chiếu mềm. Nó cho phép GC giữ lại referent một thời gian khi nguồn lực còn phù hợp, và clear tham chiếu khi có nhu cầu bộ nhớ.

~~~java
import java.lang.ref.SoftReference;

byte[] decoded = new byte[1024 * 1024];

SoftReference<byte[]> cached =
    new SoftReference<>(decoded);

decoded = null;

byte[] candidate = cached.get();

if (candidate == null) {
    // Cần tái tạo dữ liệu khi cache entry đã bị clear.
}
~~~

### 11.1. Không có cam kết về thời hạn sống

Bạn **không thể** nói:

- SoftReference chắc chắn sống tối thiểu 10 giây.
- GC chỉ clear soft references khi gần đầy heap.
- SoftReference bảo đảm tránh mọi **OutOfMemoryError**.
- Tất cả collectors/JDK options xử lý soft references bằng cùng thời điểm và thứ tự.

Đây là các giả định quá mức. Chính sách clear soft reference phụ thuộc GC và áp lực bộ nhớ; chúng có thể bị clear theo quyết định của JVM.

Vì vậy, **SoftReference** không phải công cụ tốt để triển khai TTL hoặc dung lượng cache một cách xác định. Nó vẫn là API hiện hành và có mục đích sử dụng phù hợp cho dữ liệu có thể tái tạo, nhưng nên ưu tiên **cache có giới hạn rõ ràng** khi yêu cầu nghiệp vụ cần tính dự đoán được.

## 12. PhantomReference: quan sát giai đoạn cuối của một object

**PhantomReference<T>** là tham chiếu có mức độ yếu hơn, hướng tới theo dõi quá trình xử lý tham chiếu/vòng đời thay vì cho phép ứng dụng lấy lại referent.

~~~java
import java.lang.ref.PhantomReference;
import java.lang.ref.ReferenceQueue;

ReferenceQueue<Object> queue = new ReferenceQueue<>();

Object referent = new Object();

PhantomReference<Object> phantom =
    new PhantomReference<>(referent, queue);

System.out.println(phantom.get() == null); // true
~~~

Khác với **WeakReference**, **PhantomReference.get()** **luôn trả về null**, kể cả ngay sau khi tạo phantom reference.

Khi GC nhận diện referent ở trạng thái thích hợp, phantom reference có thể được đưa vào **ReferenceQueue**.

### 12.1. Không dùng PhantomReference để gọi method trên referent

Không có đường đi như sau:

~~~java
Object value = phantom.get(); // luôn null
value.toString();              // NullPointerException
~~~

Điểm của PhantomReference **không phải** “giữ object thêm một chút để dùng nốt”. Nó dùng để nhận tín hiệu cho các hành động quản lý liên quan khi object đã vượt qua giai đoạn có thể sử dụng thông thường.

### 12.2. Phân biệt weak và phantom

| Tiêu chí | WeakReference | PhantomReference |
|---|---|---|
| **get()** khi chưa clear | Có thể trả referent | Luôn **null** |
| Mục tiêu chính | Truy cập object nếu vẫn còn; weak-key/canonicalizing | Theo dõi giai đoạn cuối để phối hợp cleanup |
| ReferenceQueue | Có thể dùng | Thường dùng |
| Lấy lại object để thực hiện nghiệp vụ | Có thể, nếu **get() != null** | Không |
| Thời điểm GC xử lý | Không xác định | Không xác định |
| Thích hợp làm scheduler chính xác | Không | Không |

Với nhu cầu cleanup thông thường, **Cleaner** cung cấp abstraction cao hơn và tránh việc phải tự viết quản lý phantom reference và queue.

## 13. Cleaner: cleanup dự phòng dựa trên phantom reachability

**java.lang.ref.Cleaner** quản lý những cặp:

- Một object được theo dõi.
- Một **Runnable cleaning action** sẽ được gọi tối đa một lần, sau khi object trở thành phantom reachable, hoặc khi ứng dụng gọi **Cleanable.clean()** chủ động.

**Cleaner** sử dụng PhantomReference và ReferenceQueue ở bên dưới.

### 13.1. Quan trọng nhất: cleaning action không được giữ object cần dọn

Sai về thiết kế:

~~~java
Cleaner.Cleanable cleanable = cleaner.register(
    this,
    () -> this.releaseResource()
);
~~~

Lambda trên capture **this**, nghĩa là action giữ **strong reference** tới object được đăng ký. Khi Cleaner còn giữ action, object có thể **không bao giờ trở thành phantom reachable**, nên cleanup tự động không xảy ra.

Đây là một trong những lỗi vòng đời quan trọng nhất khi dùng Cleaner.

Giải pháp: đưa trạng thái cần dọn vào **một đối tượng riêng**, ví dụ một **static nested class** triển khai **Runnable**, không giữ tham chiếu ngược về object chủ.

### 13.2. Ví dụ chạy được: Cleaner + AutoCloseable

Lưu vào **CleanerResourceDemo.java**:

~~~java
import java.lang.ref.Cleaner;
import java.util.concurrent.atomic.AtomicBoolean;

public class CleanerResourceDemo {

    static final class SimulatedResource implements AutoCloseable {
        private static final Cleaner CLEANER = Cleaner.create();

        // State không giữ tham chiếu tới SimulatedResource.
        private static final class State implements Runnable {
            private final AtomicBoolean released =
                new AtomicBoolean();

            @Override
            public void run() {
                if (released.compareAndSet(false, true)) {
                    // Demo: giả lập hành động trả tài nguyên.
                    System.out.println("Release simulated handle");
                }
            }

            boolean isReleased() {
                return released.get();
            }
        }

        private final State state = new State();

        private final Cleaner.Cleanable cleanable =
            CLEANER.register(this, state);

        void use() {
            if (state.isReleased()) {
                throw new IllegalStateException(
                    "Resource đã được đóng"
                );
            }

            System.out.println("Using simulated handle");
        }

        @Override
        public void close() {
            cleanable.clean();
        }
    }

    public static void main(String[] args) {
        try (var resource = new SimulatedResource()) {
            resource.use();
        }

        System.out.println("Closed explicitly");
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac CleanerResourceDemo.java
java CleanerResourceDemo
~~~

Kết quả:

~~~text
Using simulated handle
Release simulated handle
Closed explicitly
~~~

### 13.3. Vì sao ví dụ này xác định được?

Ví dụ dùng **try-with-resources**, nên **close()** chắc chắn được gọi khi rời khối theo hợp đồng ngôn ngữ; **cleanable.clean()** chạy action một cách chủ động.

Chúng ta **không** đang dựa vào GC để làm cho output đúng.

Nếu lập trình viên quên **close()**, Cleaner có thể chạy action **về sau** nếu object trở thành phantom reachable và chương trình còn có điều kiện để xử lý. **Không có cam kết thời điểm hoặc bảo đảm action sẽ chạy trước khi JVM kết thúc**.

### 13.4. Lưu ý khi áp dụng Cleaner cho tài nguyên thật

- Action **không tham chiếu ngược** tới referent.
- Action phải được thiết kế để **không thực hiện cleanup lặp lại** hoặc tác động sai khi được yêu cầu nhiều lần.
- Nên thực hiện nhanh và không block lâu, vì một Cleaner có thể xử lý các action trên một thread.
- Ngoại lệ từ cleaning action không phải cơ chế trả lỗi tin cậy về thread nghiệp vụ.
- Không trông đợi Cleaner đóng socket, commit dữ liệu hoặc giải phóng lock tại deadline bắt buộc.
- Với tài nguyên thực như file/socket, **close()** chủ động phải là đường xử lý chính; Cleaner chỉ là safety net nếu thư viện thực sự cần.

### 13.5. Cleaner có phải là finalize() phiên bản mới không?

Không nên hiểu như vậy.

**finalize()** cho phép object tự thực thi logic cleanup không xác định thời điểm và có nhiều vấn đề về độ an toàn, hiệu năng, khả năng hồi sinh object và lifecycle.

**Cleaner** tách cleaning action ra khỏi object cần dọn và sử dụng cơ chế reference processing hiện hành. Dù an toàn hơn trong những mục đích thích hợp, Cleaner **không** thay thế **AutoCloseable** và không cung cấp deadline đóng tài nguyên.

## 14. Vòng đời object và vòng đời resource: hai trục khác nhau

Xét một file reader:

~~~java
var reader = java.nio.file.Files.newBufferedReader(path);
~~~

Nó có thể ở những trạng thái nghiệp vụ:

1. Được tạo và đang mở.
2. Đang đọc dữ liệu.
3. Đã đọc xong, không còn cần thiết.
4. Đã đóng bằng **close()**.
5. Sau đó, object wrapper có thể trở thành unreachable.
6. Một GC tương lai có thể thu hồi bộ nhớ của wrapper.

Ở đây, **bước 4 không phụ thuộc bước 6**. Wrapper vẫn có thể còn reachable sau khi đã đóng. Điều đó bình thường.

Với **try-with-resources**, Java xử lý đóng tài nguyên ở một thời điểm xác định theo luồng chương trình:

~~~java
try (var reader = java.nio.file.Files.newBufferedReader(path)) {
    // Có thể ném IOException trong lúc đọc.
    System.out.println(reader.readLine());
} // reader.close() được gọi khi thoát phạm vi.
~~~

Việc **close()** ném lỗi cũng cần được xử lý; **try-with-resources** có cơ chế giữ **suppressed exceptions** khi cả thân try và close cùng thất bại.

### 14.1. Có nên gọi System.gc() trong close()?

Không. **close()** phải giải phóng tài nguyên theo hợp đồng API, chứ không phải yêu cầu toàn JVM thực thi GC.

~~~java
@Override
public void close() {
    // Giải phóng handle/connection/file thuộc đối tượng này.
    // Không gọi System.gc() làm chiến lược cleanup.
}
~~~

## 15. Reference.reachabilityFence: giữ object sống đến một điểm xác định

Một API quan trọng của Java hiện hành là **Reference.reachabilityFence(Object)**.

Nó đảm bảo object được truyền vẫn **strongly reachable ít nhất cho tới sau lời gọi này**, bất kể JIT có thể tối ưu hóa việc sử dụng object thế nào.

Mẫu khái niệm:

~~~java
import java.lang.ref.Reference;

static void useExternalHandle(NativeWrapper wrapper) {
    try {
        // Hàm giả định thực hiện thao tác native qua handle
        // mà NativeWrapper sở hữu.
        NativeApi.use(wrapper.nativeHandle());
    } finally {
        Reference.reachabilityFence(wrapper);
    }
}
~~~

**NativeWrapper** và **NativeApi** là lớp giả định của ứng dụng/native integration, không phải class của JDK. Ví dụ minh họa vị trí đặt fence khi cleanup của wrapper có thể chạy độc lập với thao tác native.

### 15.1. Vì sao fence quan trọng?

Giả sử:

- Wrapper A sở hữu một native handle.
- Cleaner được đăng ký để đóng handle khi wrapper A trở thành phantom reachable.
- Method chỉ trích xuất **long handle** rồi đưa nó cho native API.
- Sau khi trích xuất, JIT có thể thấy không cần giữ wrapper A thêm.

Nếu Cleaner nhận diện A không còn reachable và đóng handle **trước khi native operation hoàn tất**, chương trình có thể dùng một handle đã bị giải phóng.

Đặt **Reference.reachabilityFence(wrapper)** tại điểm cuối thích hợp ngăn việc wrapper bị xem là reclaimable quá sớm trong phạm vi sử dụng đó.

### 15.2. Fence không làm những việc gì?

- Không khởi động GC.
- Không giải phóng object.
- Không ép tất cả object khác còn sống.
- Không thay thế khóa đồng bộ, memory ordering tổng quát hoặc quản lý concurrency.
- Không thay thế **close()**.
- Không cứu được một thiết kế native handle bị dùng đồng thời sai hợp đồng.

Chỉ dùng fence khi có lý do reachability cụ thể, đặc biệt với **native resources/Cleaner/reference processing**. Không cần thêm **reachabilityFence** vào mọi method thông thường.

## 16. Một số thao tác API cần hiểu đúng

### 16.1. Reference.clear()

~~~java
WeakReference<Object> weak =
    new WeakReference<>(new Object());

weak.clear();

System.out.println(weak.get() == null); // true
~~~

**clear()** xóa referent khỏi Reference wrapper. Nó **không enqueue** wrapper vào ReferenceQueue và không có nghĩa bộ nhớ của object vừa được giải phóng ngay.

### 16.2. Reference.refersTo(Object)

Từ Java 16, **refersTo** là cách kiểm tra referent identity mà không yêu cầu lấy referent ra rồi sử dụng.

~~~java
Object a = new Object();
Object b = new Object();

WeakReference<Object> weak = new WeakReference<>(a);

System.out.println(weak.refersTo(a)); // true
System.out.println(weak.refersTo(b)); // false
~~~

Khi bạn đã có **a** làm strong reference và chỉ cần kiểm tra một Reference có đang trỏ tới **a** hay không, **refersTo** giúp biểu đạt trực tiếp ý định.

### 16.3. isEnqueued() không phải lựa chọn mới

**Reference.isEnqueued()** đã bị đánh dấu deprecated từ Java 16 vì API này không phù hợp để kiểm tra trạng thái theo cách tên method gợi ý. Không nên xây cơ chế điều phối mới dựa trên nó.

Khi muốn xử lý queue, hãy dùng **ReferenceQueue.poll()** hoặc **remove(...)** theo thiết kế và lifecycle phù hợp.

### 16.4. Không phụ thuộc identity của weak/soft reference làm định danh nghiệp vụ

Một WeakReference có thể bị clear và object từng là referent có thể mất khỏi hệ thống. Nếu ứng dụng cần ID ổn định để tra cứu người dùng/đơn hàng, hãy dùng một **business identifier** bền vững, không dùng sự tồn tại của WeakReference làm bằng chứng nghiệp vụ.

## 17. Khi nào nên dùng loại reference nào?

| Nhu cầu | Lựa chọn phù hợp | Vì sao |
|---|---|---|
| Đối tượng phải tồn tại trong suốt giao dịch | **Strong reference** trong phạm vi hợp lý | Bảo đảm dữ liệu còn dùng được |
| Metadata phụ gắn theo vòng đời object key | **WeakHashMap** hoặc cấu trúc tương tự | Metadata không giữ key sống mãi |
| Dữ liệu tính toán lại được, có thể bị bỏ bất kỳ lúc nào | **SoftReference** trong trường hợp được đánh giá kỹ | Cho GC quyền clear khi phù hợp |
| Cần thông báo lúc referent được GC xử lý | **WeakReference + ReferenceQueue** | Quan sát queue không có deadline |
| Cần theo dõi giai đoạn cuối của object | **PhantomReference + ReferenceQueue** | Không lấy lại object, chỉ nhận tín hiệu |
| Cần safety-net cleanup dựa vào reachability | **Cleaner** | Abstraction trên phantom references |
| File, socket, database resource có close() | **AutoCloseable + try-with-resources** | Đóng chính xác theo phạm vi |
| Cache có TTL, size limit, eviction policy | **Bounded cache với chính sách rõ ràng** | Tính dự đoán được |
| Một wrapper có Cleaner và native operation dài | **reachabilityFence** khi phù hợp | Ngăn cleanup quá sớm |

Không tồn tại một loại Reference tốt nhất cho mọi bài toán. Chọn theo **vòng đời dữ liệu** và **điều kiện ứng dụng phải bảo đảm**.

## 18. Weak references và concurrency

Trong chương trình đa luồng, GC có thể clear WeakReference giữa các thời điểm quan sát.

### 18.1. Truy cập an toàn vào referent

~~~java
WeakReference<Session> weakSession = obtainWeakReference();

Session session = weakSession.get();

if (session != null) {
    session.performWork();
}
~~~

**Session** và **obtainWeakReference** trong ví dụ này là những thành phần ứng dụng giả định. Mục đích là nhấn mạnh biến **session** giữ strong reference trong quá trình sử dụng.

Nếu gọi **weakSession.get()** mỗi lần cần đối tượng, bạn có thể nhận null ở lần gọi tiếp theo dù lần trước khác null.

### 18.2. WeakHashMap không đồng bộ

Một **WeakHashMap** thông thường **không thread-safe**. Nếu nhiều thread cập nhật map, bạn cần cơ chế đồng bộ hoặc cấu trúc phù hợp.

Ngay cả với **Collections.synchronizedMap(new WeakHashMap<>())**, việc duyệt iterator phải tuân theo hợp đồng đồng bộ của wrapper. GC cũng có thể khiến entry biến mất giữa các lần quan sát.

Nếu cần cache thread-safe, có giới hạn và semantics ổn định, thường nên dùng cache concurrent có eviction được thiết kế rõ ràng, thay vì kết hợp weak references với những giả định concurrency tự phát.

### 18.3. Không dùng cleanup callback như event nghiệp vụ

Một ReferenceQueue/Cleaner callback không phải nơi tin cậy để:

- Xác nhận người dùng đã đăng xuất.
- Trừ tiền, commit hoặc rollback giao dịch.
- Gia hạn lease có deadline.
- Giải phóng permit của semaphore phải có thời điểm cụ thể.
- Cập nhật dữ liệu cần đảm bảo tính nhất quán.

Những hành động trên phải được điều phối theo **lifecycle nghiệp vụ**, độc lập với việc GC có xảy ra hay không.

## 19. Phân biệt heap usage, GC và retained size

Một object có kích thước nhỏ nhưng có thể **giữ sống cả đồ thị object lớn**.

Ví dụ:

~~~java
import java.util.HashMap;
import java.util.Map;

final class CacheOwner {
    private static final Map<String, byte[]> CACHE =
        new HashMap<>();

    static void remember(String key, byte[] bytes) {
        CACHE.put(key, bytes);
    }
}
~~~

Dù một entry của HashMap chỉ gồm vài field, nó có thể giữ mảng **byte[]** hàng chục MB. Phân tích sự cố phải xem **retained size**: lượng bộ nhớ chỉ còn reachable vì một đối tượng/đường giữ tham chiếu nhất định, không chỉ shallow size của chính entry.

### 19.1. Những câu hỏi cần điều tra

- GC có thực sự chạy, nhưng heap sau GC vẫn tăng không?
- Đối tượng nào chiếm nhiều memory/instances?
- Đường giữ từ GC roots tới object lớn là gì?
- Có static map, listener list, callback queue hoặc ThreadLocal giữ dữ liệu không?
- Có leak ngoài heap không, chẳng hạn direct buffers, native handles hoặc tài nguyên hệ điều hành?
- Tăng heap là nhu cầu tải hợp lệ hay là dữ liệu không được giải phóng đúng vòng đời?

Đừng kết luận “GC lỗi” chỉ vì heap tăng. Một bộ đệm hợp lý có thể tăng tới mức ổn định; một leak thường thể hiện đồ thị retained objects lớn dần ngoài mong đợi.

### 19.2. Memory leak và memory pressure khác nhau

- **Memory pressure**: lượng đối tượng đang cần thiết lớn, GC phải làm việc nhiều hoặc không đủ heap.
- **Memory leak**: đối tượng không còn cần thiết nhưng vẫn bị giữ reachable do logic hoặc cấu trúc dữ liệu.

Tăng **-Xmx** có thể làm giảm triệu chứng trong một thời gian, nhưng không thay thế việc sửa retention logic.

## 20. Quan sát và chẩn đoán trên Java 27

Những công cụ hiện hành của JDK có thể giúp xác định lỗi retention trước khi thay đổi code.

### 20.1. GC logging

Ví dụ bật Unified Logging khi chạy ứng dụng:

~~~bash
java -Xlog:gc*:file=gc.log:time,uptime,level,tags MyApplication
~~~

**MyApplication** là tên lớp main của chương trình thật. Tệp log này có thể cho biết tần suất và một số thống kê GC, nhưng **không tự chỉ ra chính xác field nào đang giữ object**.

Nếu cần log chi tiết reference processing, có thể tham khảo các tag Unified Logging được JVM đang chạy hỗ trợ:

~~~bash
java -Xlog:help
~~~

Không bật log cực chi tiết liên tục ở production mà chưa đánh giá dung lượng lưu, overhead và dữ liệu có thể lộ trong log.

### 20.2. jcmd và class histogram

Với một tiến trình Java cho phép chẩn đoán:

~~~bash
jcmd <pid> GC.heap_info
jcmd <pid> GC.class_histogram
~~~

Thay **<pid>** bằng PID thật của chương trình. Một class histogram giúp xem số instance và lượng byte theo loại đối tượng, nhưng chưa chỉ ra **đường giữ từ GC root**.

Tùy tình huống, heap dump có thể giúp phân tích retained objects/GC roots trong một công cụ như Eclipse Memory Analyzer:

~~~bash
jcmd <pid> GC.heap_dump heap.hprof
~~~

**Lưu ý vận hành:** heap dump có thể rất lớn, gây pause/áp lực I/O, và có thể chứa **mật khẩu, token, dữ liệu cá nhân hoặc thông tin khách hàng**. Chỉ tạo khi được phép, ở vị trí bảo mật và theo quy trình xử lý dữ liệu nhạy cảm của tổ chức.

### 20.3. Java Flight Recorder

Một lựa chọn quan sát với JFR:

~~~bash
java -XX:StartFlightRecording=filename=recording.jfr,dumponexit=true MyApplication
~~~

JFR có thể giúp phân tích allocation, hoạt động GC và một số số liệu runtime khác. Cần đối chiếu sự kiện có sẵn và cấu hình đang dùng, không suy từ một biểu đồ đơn lẻ rằng có memory leak.

### 20.4. Không chạy GC cưỡng bức trong sản phẩm để “kiểm tra leak”

Chèn **System.gc()** trong luồng request không phải giải pháp chẩn đoán bền vững. Nếu vấn đề là một static map vẫn giữ strong references, GC dù chạy cũng không được phép thu hồi các object đó.

Hãy tìm **retaining references** và sửa nơi giữ, hoặc điều chỉnh capacity/eviction.

## 21. Thiết kế cache an toàn hơn

Thay vì để GC tùy ý quyết định khi nào dữ liệu cache biến mất, nhiều trường hợp phù hợp với chính sách:

- **Maximum size/weight**: không giữ quá dung lượng được cấp phép.
- **Time to live (TTL)**: giá trị hết hiệu lực theo thời gian.
- **Explicit invalidation**: xóa khi thay đổi dữ liệu nguồn.
- **Concurrency policy**: kiểm soát tải đồng thời và tránh tái tạo lặp.
- **Monitoring**: hit rate, miss rate, eviction và footprint.

Một ví dụ cực đơn giản với Map có giới hạn theo số mục (chỉ để minh họa chính sách, **không thread-safe**):

~~~java
import java.util.LinkedHashMap;
import java.util.Map;

final class BoundedCache<K, V>
        extends LinkedHashMap<K, V> {

    private final int maxEntries;

    BoundedCache(int maxEntries) {
        super(16, 0.75f, true);

        if (maxEntries <= 0) {
            throw new IllegalArgumentException("maxEntries > 0");
        }

        this.maxEntries = maxEntries;
    }

    @Override
    protected boolean removeEldestEntry(
            Map.Entry<K, V> eldest
    ) {
        return size() > maxEntries;
    }
}
~~~

Ví dụ áp dụng:

~~~java
BoundedCache<String, byte[]> cache =
    new BoundedCache<>(100);

cache.put("img-1", new byte[1024]);
cache.put("img-2", new byte[2048]);
~~~

Cache này dùng strong references và chỉ giới hạn **số entry**, không giới hạn tổng số byte. Nhưng chính sách xóa khi vượt 100 mục **có thể dự đoán**, khác với việc chờ GC clear SoftReference/WeakReference.

Trong ứng dụng production, nếu values có kích thước khác nhau đáng kể, cần giới hạn theo **weight/bytes**, thêm expiry và cơ chế concurrent thích hợp.

## 22. Những lỗi thường gặp khi dùng weak references và Cleaner

| Lỗi/hiểu nhầm | Hậu quả | Hướng xử lý |
|---|---|---|
| “Gán biến = null thì object được thu hồi ngay” | Sai mô hình GC | Hiểu reachability và lịch GC |
| “GC dựa trên việc method đã kết thúc” | Không chính xác khi JIT tối ưu | Dựa vào last use và reachabilityFence nếu cần |
| Chỉ dùng WeakReference nhưng vẫn có field strong tới referent | Referent vẫn sống | Kiểm tra toàn bộ đồ thị |
| Gọi **weak.get()** hai lần rồi giả định kết quả giống nhau | Có thể gặp null ở lần hai | Lưu vào local strong reference |
| Dùng **System.gc()** làm điều kiện unit test | Test flakiness | Test semantics bằng clear(), dùng GC tests riêng |
| Nhầm **clear()** là “đã GC object” | Phân tích sai vòng đời | clear chỉ xóa quan hệ reference |
| Nghĩ ReferenceQueue tự giữ wrapper mãi | Không nhận được notification | Giữ mạnh Reference wrapper đang theo dõi |
| Đọc queue và chờ sự kiện tại một deadline chính xác | Sự kiện có thể đến rất muộn hoặc không đến | Không dùng GC làm scheduler |
| WeakHashMap value giữ lại key | Key không thể thu hồi | Loại strong back-reference từ value |
| Dùng WeakHashMap làm storage dữ liệu bắt buộc | Entry có thể biến mất | Lưu bằng strong references có lifecycle rõ |
| Dùng SoftReference như TTL 5 phút | Không có hạn sống cố định | Bounded TTL cache |
| Dùng PhantomReference.get() để lấy object | Luôn null | Dùng để quan sát giai đoạn cuối |
| Cleaner action capture **this** | Object không trở thành phantom reachable | Dùng static nested State không giữ referent |
| Coi Cleaner như close() chắc chắn | Resource đóng quá trễ hoặc không đóng | AutoCloseable + try-with-resources |
| Dùng **finalize()** để giải phóng tài nguyên | Dựa vào API deprecated for removal | Loại bỏ finalization; dùng close/Cleaner khi cần |
| Tin rằng memory leak chứng minh GC lỗi | Sai nguyên nhân | Tìm retaining path và retention policy |
| Tạo heap dump production không kiểm soát | Nguy cơ lộ dữ liệu bí mật, pause lớn | Quy trình bảo mật/điều tra có kiểm soát |

## 23. Bài thực hành

### Bài A — Quan sát strong reference và weak reference

Tạo record:

~~~java
record Thumbnail(String id, byte[] data) {}
~~~

Viết chương trình:

1. Tạo **Thumbnail** có mảng 1 MiB.
2. Tạo **WeakReference<Thumbnail>**.
3. Xác nhận **get()** chưa null ngay khi object còn strong reference.
4. Gọi **weak.clear()** rồi xác nhận **get() == null**.
5. Xác nhận bản thân **Thumbnail** vẫn dùng được qua biến strong đã giữ.
6. Giải thích vì sao chương trình không chứng minh thời điểm GC.

### Bài B — Cấu trúc WeakHashMap bị giữ ngược

Viết:

~~~java
Map<Object, Object> map = new WeakHashMap<>();

Object key = new Object();

map.put(key, new Object() {
    final Object owner = key;
});
~~~

Lưu ý: khi viết thành chương trình thực tế, biến **key** được capture trong anonymous class phải là effectively final. Nếu muốn mô phỏng bỏ strong reference của key từ phía caller, dùng một kiểu value riêng nhận key qua constructor như record **Value(Object owner)** ở phần 10.2.

Hãy vẽ đường giữ từ **map → value → key**, sau đó sửa thiết kế để value không giữ lại key.

### Bài C — Cleanup có chủ đích

Sửa **CleanerResourceDemo**:

- Gọi **close()** hai lần và kiểm tra action chỉ in “Release” một lần.
- Gọi **use()** sau **close()** và kiểm tra **IllegalStateException**.
- Đặt logic resource release vào **State** không tham chiếu tới **SimulatedResource**.
- Giải thích vì sao output test phải phụ thuộc **close()**, không phụ thuộc GC.

### Bài D — Tìm retained objects

Giả sử một service thêm 500 object vào static Map mỗi phút nhưng không có cơ chế xóa.

Trả lời:

1. Sau một ngày, số entries khoảng bao nhiêu nếu không có key trùng?
2. Những object nào tạo thành retaining path?
3. Vì sao gọi **System.gc()** không giải quyết vấn đề?
4. Nên dùng TTL, max weight, explicit invalidation hay WeakHashMap?
5. Những chỉ số/JFR/heap dump nào giúp xác nhận giả thuyết?

## 24. Câu hỏi tự đánh giá

1. Tại sao object “không còn hữu ích” vẫn có thể strongly reachable?
2. Sự khác nhau giữa một **WeakReference** được giữ mạnh và referent được giữ mạnh là gì?
3. Khi **weak.get()** trả về một object, phải làm gì để sử dụng object an toàn?
4. Vì sao **weak.clear()** không có nghĩa GC đã giải phóng bộ nhớ?
5. **ReferenceQueue.poll()** có chờ đến khi GC xử lý reference không?
6. Vì sao ReferenceQueue một mình không bảo đảm giữ wrapper Reference?
7. Trường hợp nào WeakHashMap không giải phóng key như mong đợi?
8. **SoftReference** có bảo đảm TTL hoặc tránh mọi OOME không?
9. Vì sao **PhantomReference.get()** luôn trả null?
10. Cleaner action capture **this** gây vấn đề gì?
11. Khi nào **Reference.reachabilityFence** cần thiết?
12. Vì sao **AutoCloseable** tốt hơn GC-based cleanup đối với socket và file?
13. Tại sao tăng **-Xmx** không phải cách sửa retention leak?
14. Cần bảo vệ dữ liệu gì khi thu thập heap dump?
15. Vì sao không nên tạo code mới override **finalize()** trong Java 27?

## 25. Ghi nhớ

- **Reachability** nói về khả năng truy cập object từ các nguồn tham chiếu còn sống; nó không nói object còn có ích hay không.
- **Strong references** giữ object reachable. Collection/static field giữ dữ liệu ngoài nhu cầu là nguyên nhân memory leak phổ biến trong Java.
- **WeakReference** không giữ mạnh referent; **get()** có thể trả null khi referent được clear.
- Khi **get()** trả non-null, hãy giữ kết quả trong một local strong reference trong suốt thao tác cần sử dụng.
- Không dùng **System.gc()**, **Thread.sleep()** hoặc thời gian cố định để kiểm thử GC đã clear weak reference.
- **ReferenceQueue** giúp quan sát Reference được enqueue, không bảo đảm thời điểm và không tự giữ mạnh mọi wrapper đăng ký.
- **WeakHashMap** giữ key yếu nhưng value mạnh; value tham chiếu ngược về key có thể làm entry không bao giờ biến mất.
- **SoftReference** không có TTL; **PhantomReference.get()** luôn trả null.
- **Cleaner** là safety net dựa trên phantom reachability; cleaning action không được capture object đang được dọn.
- **AutoCloseable/try-with-resources** là cách ưu tiên để đóng tài nguyên đúng thời điểm.
- **Reference.reachabilityFence** hữu ích trong những trường hợp native/Cleaner khi cần giữ wrapper sống cho đến cuối thao tác.
- **finalize()** đã deprecated for removal, không dùng trong thiết kế Java 27 mới.
- Khi nghi ngờ memory leak, hãy phân tích **retained objects và đường đi từ GC roots**, thay vì tự động tăng heap hoặc ép GC.
- Chọn cấu trúc cache bằng **chính sách dung lượng, TTL và eviction rõ ràng** khi ứng dụng cần hành vi dự đoán được.

## Tài liệu tham khảo

- [Java SE 27 API — java.lang.ref](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/ref/package-summary.html)
- [Java SE 27 API — Reference](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/ref/Reference.html)
- [Java SE 27 API — WeakReference](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/ref/WeakReference.html)
- [Java SE 27 API — ReferenceQueue](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/ref/ReferenceQueue.html)
- [Java SE 27 API — SoftReference](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/ref/SoftReference.html)
- [Java SE 27 API — PhantomReference](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/ref/PhantomReference.html)
- [Java SE 27 API — Cleaner](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/ref/Cleaner.html)
- [Java SE 27 API — WeakHashMap](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/WeakHashMap.html)
- [Java SE 27 API — AutoCloseable](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/AutoCloseable.html)
- [Java SE 27 — Garbage Collection Tuning Guide: Other Considerations](https://docs.oracle.com/en/java/javase/27/gctuning/other-considerations.html)
- [Java SE 27 — Java Virtual Machine Guide](https://docs.oracle.com/en/java/javase/27/vm/java-virtual-machine-guide.html)
- [Java Language Specification — §12.6 Finalization of Class Instances](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-12.html#jls-12.6)
- [OpenJDK JEP 421 — Deprecate Finalization for Removal](https://openjdk.org/jeps/421)
