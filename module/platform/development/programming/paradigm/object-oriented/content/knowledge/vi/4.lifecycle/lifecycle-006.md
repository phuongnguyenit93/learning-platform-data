# Thời gian tồn tại, khả năng truy cập và giải phóng bộ nhớ trong Java

Trong Java, đối tượng được tạo ra trong quá trình chương trình chạy và thường được lưu trong vùng nhớ do JVM quản lý. Java có **garbage collector (GC)** để thu hồi bộ nhớ từ các đối tượng không còn được chương trình sử dụng theo tiêu chí *reachability* (khả năng truy cập).

Tuy nhiên, có ba vấn đề phải phân biệt:

1. **Thời gian tồn tại (lifetime):** Một đối tượng được tạo khi nào, còn được chương trình sử dụng khi nào và khi nào bộ nhớ dành cho nó thực sự có thể được thu hồi?
2. **Khả năng truy cập (reachability):** Có còn đường tham chiếu từ các điểm xuất phát mà GC xem là đang được sử dụng đến đối tượng hay không?
3. **Giải phóng bộ nhớ và tài nguyên:** JVM thu hồi bộ nhớ đối tượng khác với việc ứng dụng đóng file, kết nối mạng, kết nối cơ sở dữ liệu hay tài nguyên hệ điều hành.

Một lệnh `obj = null` **không phải** lệnh xóa đối tượng. Việc ra khỏi một phương thức cũng không bảo đảm GC chạy ngay. Ngược lại, một đối tượng tưởng như đã “dùng xong” vẫn có thể bị giữ trong bộ nhớ rất lâu nếu còn một tham chiếu mạnh từ nơi khác.

## 1. Phân biệt các khái niệm quan trọng

| Khái niệm | Bản chất | Ví dụ |
|---|---|---|
| **Tạo đối tượng** | Thực hiện thao tác tạo instance, thường là `new`, hoặc một cơ chế khác do API cung cấp | `new Book("Java")` |
| **Tham chiếu (reference)** | Giá trị cho phép mã Java truy cập tới đối tượng | `Book current = book;` |
| **Phạm vi biến (scope)** | Đoạn mã mà một tên biến có thể được sử dụng theo quy tắc ngôn ngữ | Biến cục bộ chỉ được gọi tên trong khối khai báo |
| **Khả năng truy cập** | Có đường đi tham chiếu từ các GC roots tới đối tượng hay không | Một field của singleton còn giữ `Book` |
| **Đủ điều kiện để thu gom** | GC không còn coi đối tượng là reachable theo mô hình xử lý tương ứng | Sau khi loại bỏ tham chiếu mạnh cuối cùng |
| **Thu hồi bộ nhớ** | JVM/GC thực sự tái sử dụng hoặc giải phóng bộ nhớ do đối tượng chiếm giữ | Không thể chọn chính xác thời điểm từ mã Java thông thường |
| **Đóng tài nguyên** | Kết thúc việc sở hữu file/socket/connection… theo hợp đồng API | `close()` hoặc `try-with-resources` |

Ba mệnh đề sau **không tương đương**:

- “Biến `x` ra khỏi scope”.
- “Đối tượng từng được `x` tham chiếu hiện không còn reachable”.
- “GC đã thu hồi bộ nhớ của đối tượng đó”.

Đây có thể là ba thời điểm khác nhau.

## 2. Tạo đối tượng và lưu giữ tham chiếu

Ví dụ:

~~~java
class Book {
    final String title;

    Book(String title) {
        this.title = title;
    }
}

Book a = new Book("Java");
Book b = a;
a = null;

System.out.println(b.title); // Java
~~~

Lúc đầu, `a` trỏ tới `Book`. Phép gán `b = a` sao chép **giá trị tham chiếu**, nên cả hai cùng trỏ đến *một* đối tượng. Sau `a = null`, chỉ có `a` không còn trỏ tới nó; `b` vẫn dùng được.

~~~mermaid
flowchart LR
    A["a"] --> N["null"]
    B["b"] --> O["Book object<br/>title = Java"]
~~~

Java **truyền tham số theo giá trị**. Khi truyền biến tham chiếu vào phương thức, Java sao chép giá trị tham chiếu. Phương thức có thể thay đổi trạng thái đối tượng được trỏ tới, nhưng gán lại tham số cục bộ không làm thay đổi biến tham chiếu của phía gọi.

~~~java
static void clearLocalReference(Book book) {
    book = null; // Chỉ gán lại tham số cục bộ.
}

Book myBook = new Book("OOP");
clearLocalReference(myBook);
System.out.println(myBook.title); // OOP
~~~

Đoạn trên minh họa phương thức đặt trong một lớp Java thích hợp. Đối tượng không bị xóa vì tham số `book` đã gán `null`.

## 3. Ví dụ thực hành hoàn chỉnh: vòng đời qua các tham chiếu

Chương trình dưới đây dùng một danh sách static để minh họa một tham chiếu có thể giữ đối tượng tiếp tục được truy cập, rồi loại bỏ đường tham chiếu đó. Phần đầu có đầu ra xác định; ví dụ **không cố ép GC chạy**.

Lưu thành **`Demo.java`** và chạy trên Java 17 trở lên:

~~~java
import java.util.ArrayList;
import java.util.List;

public class Demo {
    // Registry tồn tại cùng với lớp Demo khi lớp còn được nạp.
    private static final List<Document> registry = new ArrayList<>();

    public static void main(String[] args) {
        Document original = new Document("Hợp đồng số 1");
        Document alias = original;

        System.out.println(original == alias); // true

        original = null;
        System.out.println(alias.title()); // Hợp đồng số 1

        // Registry tiếp tục giữ tham chiếu mạnh đến Document.
        registry.add(alias);
        alias = null;

        System.out.println(registry.size()); // 1
        System.out.println(registry.get(0).title()); // Hợp đồng số 1

        // Bỏ đường tham chiếu từ registry tới Document.
        registry.clear();
        System.out.println(registry.size()); // 0

        // Từ đây không có lời hứa GC sẽ chạy hay object biến mất ngay.
    }

    private static final class Document {
        private final String title;

        private Document(String title) {
            this.title = title;
        }

        String title() {
            return title;
        }
    }
}
~~~

Thực thi:

~~~bash
javac Demo.java
java Demo
~~~

Kết quả:

~~~text
true
Hợp đồng số 1
1
Hợp đồng số 1
0
~~~

**Diễn giải:**

1. `new Document(...)` tạo một đối tượng `Document`.
2. `alias = original` thêm một biến tham chiếu tới cùng đối tượng; không tạo đối tượng mới.
3. `original = null` chỉ loại một đường tham chiếu. `alias` vẫn dùng được.
4. `registry.add(alias)` khiến danh sách static nắm giữ đối tượng qua tham chiếu mạnh.
5. `alias = null` không làm đối tượng đủ điều kiện thu gom vì danh sách còn giữ nó.
6. `registry.clear()` loại đường tham chiếu từ danh sách. Nếu không còn đường mạnh nào khác khiến đối tượng reachable, nó có thể trở thành đối tượng có thể thu gom. Điều này **không** đồng nghĩa GC đã thực sự thu hồi bộ nhớ ngay ở dòng đó.

Sơ đồ trước và sau khi xóa registry:

~~~mermaid
flowchart TB
    subgraph before["Trước registry.clear()"]
        R1["GC root: lớp đang được sử dụng"] --> S1["Demo.registry"]
        S1 --> L1["List"]
        L1 --> D1["Document<br/>Hợp đồng số 1"]
    end
    subgraph after["Sau registry.clear()"]
        R2["GC root: lớp đang được sử dụng"] --> S2["Demo.registry"]
        S2 --> L2["List rỗng"]
        D2["Document từng được giữ<br/>không còn cạnh từ List"]
    end
~~~

Hình vẽ mô tả **quan hệ tham chiếu có ý nghĩa logic**. Các JVM và thuật toán JIT/GC có thể sắp xếp bộ nhớ và tối ưu hóa mã khác nhau; sơ đồ không xác định vị trí vật lý của object trong RAM.

## 4. Scope của biến không phải lifetime của đối tượng

Một biến cục bộ có phạm vi theo khối lệnh. Nhưng đối tượng mà nó từng trỏ tới có thể tiếp tục sống nếu một field, phần tử collection hoặc đối tượng khác còn giữ tham chiếu.

~~~java
import java.util.ArrayList;
import java.util.List;

class Notebook {
    String title;

    Notebook(String title) {
        this.title = title;
    }
}

class NotebookStore {
    private final List<Notebook> books = new ArrayList<>();

    void addExample() {
        Notebook local = new Notebook("Ghi chú");
        books.add(local);
    } // Tên biến local ra khỏi scope.

    int count() {
        return books.size();
    }
}
~~~

Sau khi `addExample()` kết thúc, `local` không còn được dùng theo tên đó, nhưng `books` có thể tiếp tục giữ `Notebook`. Nếu `NotebookStore` vẫn reachable, đối tượng `Notebook` trong danh sách cũng có thể reachable.

Chiều ngược lại cũng đáng chú ý: một biến nằm trong scope về mặt mã nguồn **không đảm bảo** rằng GC phải giữ đối tượng tới hết khối lệnh nếu JVM chứng minh được object không còn được dùng. JIT và GC có thể tối ưu hóa vùng sống của tham chiếu dựa trên việc sử dụng thực tế.

Đối với code Java thông thường, hãy suy luận từ các đường tham chiếu mà chương trình thực sự còn cần và không dựa vào một thời điểm thu gom cụ thể. Với thư viện quản lý tài nguyên ngoài heap có yêu cầu sống chính xác tới cuối đoạn mã, `Reference.reachabilityFence(obj)` là công cụ chuyên biệt; nó không phải thay thế cho `close()`.

## 5. GC roots và đồ thị khả năng truy cập

JVM có các điểm xuất phát (*GC roots*) để tìm những đối tượng đang được sử dụng. Các loại roots cụ thể tùy JVM và cơ chế thu gom, nhưng thường liên quan đến:

- Tham chiếu còn sống trong các luồng Java đang thực thi, như đối tượng được giữ bởi biến cục bộ hoặc tham số cần thiết.
- Tham chiếu trong các field static của những lớp đang được giữ/nạp thích hợp.
- Các tham chiếu do JNI hoặc cơ chế runtime/native giữ.
- Một số cấu trúc runtime khác mà JVM coi là roots.

Từ roots, GC duyệt qua các field tham chiếu, phần tử mảng và quan hệ đối tượng để xác định các object còn reachable.

~~~mermaid
flowchart LR
    R1["GC root<br/>Luồng đang chạy"] --> A["Service"]
    R2["GC root<br/>Static field"] --> B["Cache"]
    A --> C["Order"]
    C --> D["Customer"]
    B --> E["Report"]
    X["Temporary X"] --> Y["Temporary Y"]
    Y --> X
~~~

Trong hình, `Service`, `Cache`, `Order`, `Customer`, `Report` có đường tới root. Cặp `Temporary X` và `Temporary Y` chỉ tham chiếu qua lại nhưng **không có đường từ root**, nên có thể được GC thu gom.

**Một chu trình tham chiếu không tự làm rò rỉ bộ nhớ trong Java.** JVM hiện đại chủ yếu dựa vào reachability, không yêu cầu lập trình viên phá mọi chu trình như trong một số hệ thống dùng reference counting đơn thuần.

### Strong reference là gì?

Tham chiếu bình thường bạn sử dụng khi viết:

~~~java
Order order = new Order();
List<Order> orders = new ArrayList<>();
orders.add(order);
~~~

là **strong reference**. Trong ví dụ, danh sách tiếp tục giữ strong reference đến `order`. Nếu danh sách còn reachable từ GC roots, bản thân đối tượng `Order` vẫn được giữ lại.

Ví dụ `Order` ở đây chỉ là lớp minh họa trong một ngữ cảnh có định nghĩa tương ứng.

Một đối tượng chỉ trở nên *không còn strong reachable* khi không còn đường strong reference thích hợp từ roots. Có thêm các mức reachability khác khi sử dụng `java.lang.ref`, sẽ bàn ở phần sau.

## 6. “Được GC thu gom” có nghĩa gì và khi nào xảy ra?

Một vòng đời được mô tả ở mức khái quát:

~~~mermaid
stateDiagram-v2
    [*] --> Allocated: Tạo đối tượng
    Allocated --> StronglyReachable: Có đường strong reference từ roots
    StronglyReachable --> StronglyReachable: Còn được giữ / sử dụng
    StronglyReachable --> NotStronglyReachable: Mất đường strong reference cuối
    NotStronglyReachable --> Reclaimed: GC có thể xử lý, thu hồi
~~~

Sơ đồ đơn giản hóa tình huống tham chiếu mạnh. Trong thực tế, đối tượng có thể trở lại strong reachable, có weak/soft/phantom references, và có các bước xử lý của GC tùy trạng thái. Không nên coi đây là state machine đầy đủ của garbage collector.

Ba điểm cần ghi nhớ:

**Thứ nhất:** trở thành không còn reachable không tự động tạo một lệnh giải phóng bộ nhớ ở dòng Java kế tiếp. JVM quyết định lúc nào thực hiện GC và thực hiện ra sao.

**Thứ hai:** bộ nhớ được thu hồi cho heap JVM có thể được **tái sử dụng cho đối tượng mới**. JVM không có nghĩa vụ lập tức trả lượng RAM đó về hệ điều hành.

**Thứ ba:** mục tiêu của GC là quản lý bộ nhớ đối tượng; GC không phải một cơ chế bảo đảm mọi tài nguyên bên ngoài bộ nhớ heap được đóng đúng hạn.

Bạn có thể gặp:

~~~java
System.gc();
~~~

Đây là **yêu cầu/gợi ý** để JVM cân nhắc thực hiện thu gom rác, không phải hợp đồng bảo đảm GC đã chạy xong hay mọi object đủ điều kiện đã bị thu hồi. Có thể có cấu hình JVM phớt lờ yêu cầu này. Không viết logic nghiệp vụ hoặc bài test mà tính đúng đắn phụ thuộc vào `System.gc()`.

## 7. Các loại tham chiếu: strong, soft, weak và phantom

Package `java.lang.ref` cung cấp cơ chế để làm việc với các mức reachability chuyên biệt.

| Loại | Cách tạo/biểu diễn | Vai trò | Lưu ý |
|---|---|---|---|
| **Strong reference** | Biến/field/thành phần collection tham chiếu bình thường | Giữ object có thể sử dụng như thường lệ | Nếu reachable từ root theo đường strong, GC không thu hồi object như rác |
| **Soft reference** | `SoftReference<T>` | Cho phép JVM thu hồi đối tượng khi cần bộ nhớ, từng được dùng cho cache nhạy áp lực bộ nhớ | Thời điểm thu hồi không bảo đảm; thường không nên dùng thay chính sách cache rõ ràng |
| **Weak reference** | `WeakReference<T>` | Không giữ object sống chỉ vì tham chiếu yếu | `get()` có thể trở thành `null` sau khi GC xử lý |
| **Phantom reference** | `PhantomReference<T>` với `ReferenceQueue` | Cơ chế theo dõi giai đoạn xử lý sau khi đối tượng không còn được sử dụng, phục vụ quản lý tài nguyên chuyên biệt | `get()` luôn trả `null`; cần thiết kế queue/cleanup đúng |

Strong reference thông thường là loại quan trọng nhất trong mã OOP hằng ngày. Weak, soft và phantom là **công cụ nâng cao**; chúng không nên xuất hiện chỉ vì muốn “tự động tối ưu bộ nhớ”.

### Ví dụ WeakReference không ràng buộc thời điểm GC

~~~java
import java.lang.ref.WeakReference;

class Payload {
    final String value = "data";
}

class WeakDemo {
    public static void main(String[] args) {
        Payload strong = new Payload();
        WeakReference<Payload> weak = new WeakReference<>(strong);

        System.out.println(weak.get() != null); // true tại đây:
                                                 // strong còn dùng được.

        strong = null; // Bỏ tham chiếu mạnh do biến strong giữ.

        Payload observed = weak.get();
        if (observed == null) {
            System.out.println("Đối tượng đã bị GC làm rỗng weak reference");
        } else {
            System.out.println(observed.value);
        }
    }
}
~~~

Sau `strong = null`, chương trình **không thể khẳng định** nhánh nào sẽ được chạy: nó phụ thuộc thời điểm GC và cách JVM xác định đối tượng còn được dùng. Nếu `weak.get()` trả về một tham chiếu khác `null`, biến `observed` tạm thời giữ một strong reference và có thể sử dụng giá trị đó.

**Không** viết bài kiểm thử trông đợi `weak.get() == null` ngay sau `strong = null`.

### ReferenceQueue dùng để làm gì?

Một `ReferenceQueue<T>` giúp mã quản lý nhận biết khi một đối tượng tham chiếu tương ứng đã được GC đưa vào hàng đợi theo quy tắc của loại reference.

~~~java
import java.lang.ref.Reference;
import java.lang.ref.ReferenceQueue;
import java.lang.ref.WeakReference;

class QueueDemo {
    static final class Session {}

    public static void main(String[] args) {
        ReferenceQueue<Session> queue = new ReferenceQueue<>();
        Session session = new Session();
        WeakReference<Session> weak =
                new WeakReference<>(session, queue);

        session = null;

        // Không được dựa vào việc queue đã có phần tử ngay lúc này.
        Reference<? extends Session> event = queue.poll();
        System.out.println("Có sự kiện đã enqueue: " + (event != null));

        // Giữ biến weak ở đây để minh họa đối tượng Reference.
        System.out.println("Tham chiếu weak còn được giữ: " + (weak != null));
    }
}
~~~

Kết quả dòng đầu **không cố định**. Để sử dụng queue trong ứng dụng thực tế, cần lập trình vòng xử lý và vòng đời phù hợp; ví dụ chỉ cho thấy API và lý do không được giả định GC xảy ra theo lịch.

### WeakHashMap không phải “bản đồ không rò rỉ”

`WeakHashMap<K,V>` giữ khóa theo tham chiếu yếu. Nếu không còn strong reference tới khóa từ nơi khác, entry có thể được dọn khi GC xử lý. Tuy nhiên:

- Đây không phải cache có TTL, giới hạn kích thước hay chính sách loại bỏ xác định.
- Nếu *value* giữ strong reference quay lại chính *key*, đối tượng key có thể vẫn còn reachable qua value và map, khiến mục tiêu dọn entry không đạt.
- Không dùng nó để bảo đảm dọn bản ghi đúng giờ hoặc giải quyết mọi trường hợp rò rỉ.

## 8. Một Java object có thể đã được đóng resource nhưng vẫn còn sống

Tình trạng **reachable/unreachable** nói về khả năng GC tìm thấy object từ các roots. Tình trạng **open/closed** nói về vòng đời tài nguyên ngoài heap mà object có thể đang đại diện. Hai trạng thái độc lập:

| Ví dụ | Object còn reachable? | Resource còn mở? |
|---|---|---|
| `BufferedReader` đang được dùng trong `try` | Có | Thường có |
| `BufferedReader` đã `close()` nhưng biến vẫn giữ tham chiếu | Có thể có | Đã yêu cầu đóng theo hợp đồng |
| Mã bỏ hết tham chiếu tới reader mà quên đóng | Có thể không | Không có bảo đảm đã đóng đúng lúc |

Khi chính phương thức mở file và sở hữu reader, nên dùng:

~~~java
try (BufferedReader reader = Files.newBufferedReader(path)) {
    System.out.println(reader.readLine());
} // Java gọi close() khi rời try.
~~~

Đoạn này cần các import `java.io.BufferedReader`, `java.nio.file.Files` và một `Path path` hợp lệ. `try-with-resources` bảo đảm gọi `close()` khi thoát khối theo luồng Java thông thường, kể cả khi gặp exception; không bảo đảm GC đã thu hồi object tại dấu ngoặc đóng. Với lỗi từ `close()`, tài nguyên lồng nhau, `AutoCloseable`, `finalize()` và ownership, xem bài *Đóng tài nguyên và giới hạn của hàm hủy*.

## 9. Khi nào vẫn xảy ra memory leak trong Java?

Trong Java, *memory leak* không nhất thiết là khối nhớ “mất địa chỉ” theo nghĩa của ngôn ngữ quản lý bộ nhớ thủ công. Nó thường có nghĩa **đối tượng không còn hữu ích với nghiệp vụ nhưng vẫn được tham chiếu mạnh từ một root**, làm GC không thể thu hồi nó.

Các trường hợp thường gặp:

| Nguồn giữ tham chiếu | Tình huống | Hậu quả | Cách kiểm soát |
|---|---|---|---|
| Static collection | Thêm mọi session vào `static List` và không xóa | Bộ nhớ tăng theo số request | Loại mục hết hạn, giới hạn cache, thiết kế ownership |
| Cache không giới hạn | `Map<Id, Value>` giữ mọi kết quả vĩnh viễn | Heap tăng không kiểm soát | Dùng cache có kích thước/TTL/eviction |
| Event listener | Đăng ký listener nhưng quên hủy | Publisher tiếp tục giữ subscriber | `unsubscribe` đúng vòng đời |
| Scheduled task | Task giữ closure tham chiếu tới đối tượng không còn cần | Đối tượng được giữ lâu hơn mong đợi | Hủy task, đóng executor theo ownership |
| ThreadLocal | Giá trị sống theo thread chạy dài hạn nếu không dọn đúng | Dữ liệu cũ còn bị giữ qua nhiều tác vụ | `remove()` trong `finally` |
| Collection / queue | Không xóa phần tử đã xử lý | Các phần tử vẫn reachable | `remove()`, `clear()` khi hợp lý |
| Object graph | Root giữ một object lớn và toàn bộ các con | Nhiều đối tượng được giữ gián tiếp | Rà soát cạnh tham chiếu và vòng đời của root |

### Ví dụ: bộ nhớ tăng vì cache không giới hạn

~~~java
import java.util.ArrayList;
import java.util.List;

class BadHistory {
    private static final List<byte[]> ALL_REQUESTS = new ArrayList<>();

    static void record(byte[] data) {
        ALL_REQUESTS.add(data); // Không có chính sách loại bỏ.
    }
}
~~~

Nếu `record` được gọi liên tục với các mảng lớn, `ALL_REQUESTS` giữ mọi mảng bằng strong reference. GC không thể tự biết mục nào “không còn có giá trị nghiệp vụ”.

Một phương án là thiết kế nơi lưu có **giới hạn** và cơ chế loại bỏ:

~~~java
import java.util.ArrayDeque;
import java.util.Deque;

class RecentMessages {
    private static final int MAX_SIZE = 100;
    private final Deque<String> messages = new ArrayDeque<>();

    public void add(String message) {
        if (message == null) {
            throw new IllegalArgumentException("message không được null");
        }
        if (messages.size() == MAX_SIZE) {
            messages.removeFirst();
        }
        messages.addLast(message);
    }

    public int size() {
        return messages.size();
    }
}
~~~

Bộ nhớ của cấu trúc giới hạn này vẫn phụ thuộc kích thước chuỗi đầu vào, vì `MAX_SIZE` chỉ giới hạn **số phần tử**, không giới hạn tổng byte. Nếu cần quota bộ nhớ, phải kiểm soát cả kích thước mỗi phần tử và tổng ngân sách.

### Ví dụ: ThreadLocal trong thread pool

~~~java
private static final ThreadLocal<String> CURRENT_USER = new ThreadLocal<>();

static void handleRequest(String userId) {
    CURRENT_USER.set(userId);
    try {
        // Xử lý request với thông tin người dùng hiện tại.
        System.out.println(CURRENT_USER.get());
    } finally {
        CURRENT_USER.remove();
    }
}
~~~

Đoạn này được đặt trong một lớp thích hợp. Với thread pool, luồng có thể được tái sử dụng cho request tiếp theo. `remove()` trong `finally` giúp tránh giữ dữ liệu cũ và rò rỉ ngữ cảnh giữa các request. Nếu code bất đồng bộ chuyển xử lý sang luồng khác, cần cơ chế truyền context phù hợp; ThreadLocal không tự di chuyển giá trị.

## 10. Đối tượng tham chiếu lẫn nhau có bị giữ mãi không?

Không nhất thiết. Xét:

~~~java
class Node {
    Node next;
}

Node first = new Node();
Node second = new Node();
first.next = second;
second.next = first;

first = null;
second = null;
~~~

Hai object `Node` tạo một chu trình. Nếu chúng không còn reachable từ bất cứ GC root nào thì chúng có thể được GC thu gom dù vẫn trỏ tới nhau.

~~~mermaid
flowchart LR
    R["GC root"] -.->|"Không còn đường tham chiếu"| A["Node A"]
    A --> B["Node B"]
    B --> A
~~~

Đường đứt nét biểu thị đường root đã bị mất, **không phải một cạnh tham chiếu thực tế**. GC dựa vào reachability có thể nhận ra cả nhóm đều không còn được chương trình dùng. Cần cẩn thận với chu trình khi một trong các node vẫn reachable qua root: lúc đó cả nhóm có thể tiếp tục được giữ.

## 11. Phạm vi vùng nhớ: heap, stack và static

Trong quá trình học Java thường gặp cách diễn đạt “object nằm trên heap, biến cục bộ nằm trên stack”. Đây là **mô hình học tập hữu ích**, nhưng chưa mô tả đầy đủ mọi tối ưu hóa JVM hiện đại.

| Khía cạnh | Hiểu ở mức lập trình | Lưu ý |
|---|---|---|
| Đối tượng và mảng | Có thể được cấp phát trong vùng nhớ đối tượng do JVM quản lý | JIT có thể loại bỏ/đổi cách cấp phát nhờ escape analysis |
| Biến cục bộ, tham số | Nằm trong khung thực thi logic của phương thức | JVM/JIT có thể dùng thanh ghi hoặc tối ưu hóa khác |
| Instance field | Thuộc trạng thái của từng đối tượng | Có thể giữ tham chiếu mạnh đến object khác |
| Static field | Thuộc về lớp được nạp, không phải một instance cụ thể | Có thể khiến object được giữ trong thời gian dài |
| Native/off-heap resources | Có thể được quản lý ngoài heap Java | Cần theo hợp đồng API, thường có cơ chế close/release |

Không nên dùng những khẳng định tuyệt đối như “mọi biến cục bộ luôn nằm trên stack vật lý”, “mọi đối tượng có địa chỉ cố định”, hay “biến static luôn nằm ở một vùng nhớ xác định”. Những chi tiết triển khai phụ thuộc JVM, collector và tối ưu hóa.

### Đối tượng bị di chuyển trong bộ nhớ có mất danh tính không?

Một số garbage collector có thể **di chuyển đối tượng** để gom bộ nhớ và giảm phân mảnh. Điều này không làm thay đổi danh tính logic mà mã Java quan sát qua phép `==` giữa các tham chiếu còn hợp lệ. Java không cho phép bạn dựa vào một địa chỉ bộ nhớ thô cố định của đối tượng như ID nghiệp vụ.

Nếu cần ID bền vững, sử dụng một định danh được quản lý theo yêu cầu ứng dụng, ví dụ `UUID`, khóa database hoặc mã nghiệp vụ, chứ không dựa vào `hashCode()` hay địa chỉ máy.

## 12. Chẩn đoán một đối tượng bị giữ ngoài dự kiến

Nếu heap tăng đều dù dữ liệu nghiệp vụ cũ đáng lẽ đã hết hạn, **đừng suy luận chỉ từ một lần đo RAM**. Đo xu hướng object còn sống sau các chu kỳ tải tương đương, rồi xem **đường giữ tham chiếu từ GC root tới object**.

Một ví dụ điều tra với profiler hoặc heap dump:

~~~text
GC root → Static field → Cache → Map entry → RequestData
~~~

Nếu `RequestData` đã hết hạn mà entry vẫn còn, cách sửa thường nằm ở **chính sách của cache** (giới hạn, TTL, xóa khi hết nhu cầu), không nằm ở dòng `new RequestData(...)`. Heap dump và dominator tree giúp xác định tập object bị giữ; JFR và GC metrics giúp đối chiếu xu hướng cấp phát/thu gom. Việc thu thập heap dump trên hệ thống thật có thể gây tải, nên chọn thời điểm thích hợp.

Công cụ chẩn đoán GC, phân biệt heap leak với native memory pressure và ví dụ lệnh JDK được tập trung ở bài *Thu gom rác và quản lý bộ nhớ thủ công*.

## 13. Vài tình huống thiết kế điển hình

| Tình huống | Cách xử lý phù hợp | Vì sao? |
|---|---|---|
| Một đối tượng dùng trong một lần tính toán | Để tham chiếu cục bộ và không lưu giữ ngoài nhu cầu | Khi không còn đường từ roots, GC có thể thu gom |
| Kết quả được cache | Cache có giới hạn/TTL và chính sách loại bỏ | Tránh giữ dữ liệu không còn hữu ích |
| Subscription/listener | Trả về handle hủy đăng ký hoặc quản lý `close()` | Tránh publisher giữ subscriber vô hạn |
| File, stream, database connection | Dùng `try-with-resources` theo ownership | Đóng tài nguyên đúng vòng đời |
| Cấu trúc graph có vòng tham chiếu | Không cần phá vòng chỉ để “cho GC chạy” | GC thu gom nhóm unreachable |
| Theo dõi object không được giữ sống bởi mã theo dõi | Cân nhắc `WeakReference`/queue nếu thực sự cần | Tránh quan sát tạo thêm strong retention |
| Giải phóng đối tượng ở một dòng mã xác định | Không xây thiết kế trên giả định này | Java không bảo đảm lịch GC |
| Session gắn với thread pool | Dọn ThreadLocal trong `finally` | Thread được tái sử dụng qua nhiều tác vụ |

### Cân nhắc thêm khi đối tượng quản lý tài nguyên

Một `Connection` hoặc `InputStream` có thể **đã được đóng nhưng vẫn là một đối tượng Java còn sống** nếu còn tham chiếu. Gọi `close()` không biến tham chiếu thành `null`, cũng không thu hồi heap ngay. Tương tự, một object chứa socket còn reachable không bảo đảm socket vẫn mở; trạng thái resource và reachability là hai trục khác nhau.

Một thiết kế tốt nên thể hiện rõ: ai **sở hữu** tài nguyên, ai được phép dùng, khi nào phải đóng và hành vi nào hợp lệ sau khi đóng.

## 14. Bài tập kiểm tra hiểu biết

### Bài 1 — `null` có xóa object?

~~~java
class Item { int count = 2; }

Item x = new Item();
Item y = x;
x = null;
System.out.println(y.count);
~~~

**Đáp án:** in `2`. Object vẫn có thể truy cập qua `y`.

### Bài 2 — Tham chiếu rời scope có đủ để GC thu hồi?

~~~java
class Service {
    static final List<Object> STORE = new ArrayList<>();

    static void run() {
        Object result = new Object();
        STORE.add(result);
    }
}
~~~

Giả sử đã import `java.util.List` và `java.util.ArrayList`. Sau khi `run()` trả về, `result` ra khỏi scope. Đối tượng mới tạo có chắc đủ điều kiện GC không?

**Đáp án:** Không. `STORE` còn giữ strong reference nếu field/list vẫn reachable. Phải loại đường tham chiếu này (và các đường khác nếu có) khi không còn cần dữ liệu.

### Bài 3 — Chu trình không có root

~~~java
Node a = new Node();
Node b = new Node();
a.next = b;
b.next = a;
a = null;
b = null;
~~~

**Đáp án:** Nếu không còn đường reachable nào khác tới hai node, cả hai có thể được GC thu gom. Chu trình đơn thuần không giữ chúng sống.

### Bài 4 — Có nên đợi GC đóng file?

**Đáp án:** Không. Sử dụng `try-with-resources` hoặc `close()` theo quy tắc sở hữu tài nguyên. GC không hứa đóng file đúng thời điểm.

### Bài 5 — Kết quả WeakReference sau khi bỏ strong reference

~~~java
WeakReference<Object> weak;
{
    Object o = new Object();
    weak = new WeakReference<>(o);
}
// Điều gì được đảm bảo về weak.get() tại đây?
~~~

**Đáp án:** Không thể khẳng định `weak.get()` chắc chắn `null` hay chắc chắn khác `null` chỉ từ việc ra khỏi khối. Nếu GC đã làm rỗng weak reference thì trả `null`; nếu object vẫn còn đó và chưa bị làm rỗng thì có thể nhận tham chiếu tới object.

### Bài 6 — Chọn cách sửa phù hợp

Một ứng dụng giữ tất cả lịch sử request trong `static ArrayList`; heap tăng khi lưu lượng tăng và dữ liệu cũ không được sử dụng nữa.

**Đáp án gợi ý:** Đặt giới hạn/chính sách vòng đời cho lịch sử, chỉ lưu những thông tin cần thiết, loại mục hết hạn và xác nhận bằng profiler/heap dump rằng không còn đường giữ tham chiếu ngoài ý muốn. Gọi `System.gc()` không giải quyết được nếu danh sách vẫn giữ object.

## 15. Checklist khi tự đánh giá một lớp Java

- Đối tượng được tạo khi nào và **ai** phải giữ tham chiếu tới nó?
- Object có được đặt vào field, collection, cache, callback, ThreadLocal hoặc singleton không?
- Nếu không còn dùng, đường tham chiếu mạnh nào phải bị loại bỏ?
- Có tài nguyên ngoài heap nào cần **đóng đúng lúc** không?
- Các sự kiện như request kết thúc, timeout, hủy subscription, shutdown đã được xử lý chưa?
- Có đoạn code nào đang mặc định `System.gc()` hoặc `finalize()` sẽ giải phóng tài nguyên đúng hạn không?
- Có thể chứng minh bằng số liệu và đường từ GC roots rằng đối tượng đang bị giữ ngoài dự kiến không?

**Nguyên tắc cần nhớ:** Java tự động quản lý việc thu hồi **bộ nhớ đối tượng** dựa trên khả năng truy cập; lập trình viên vẫn chịu trách nhiệm thiết kế **vòng đời dữ liệu, quan hệ tham chiếu và vòng đời tài nguyên**. Một đối tượng không còn có ích nhưng vẫn reachable có thể tiếp tục chiếm bộ nhớ; một object đã mất đường tham chiếu không biến mất tức thì; và `close()` giải quyết một trách nhiệm khác với GC.