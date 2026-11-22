# Cấp phát đối tượng, khả năng truy cập và thu gom rác trong Java 17

Java quản lý phần lớn vòng đời bộ nhớ của object bằng cơ chế tự động: chương trình tạo object, JVM cấp phát vùng nhớ phù hợp, và garbage collector (GC) thu hồi bộ nhớ khi object không còn có thể được truy cập theo các quy tắc của Java. Tuy vậy, “có garbage collector” không có nghĩa ứng dụng không thể hết bộ nhớ hoặc không thể giữ lại object quá lâu.

Để hiểu cách JVM quản lý bộ nhớ, cần nối ba khái niệm:

1. **Cấp phát đối tượng (allocation):** object được tạo và vùng nhớ được dành cho nó như thế nào.
2. **Khả năng truy cập (reachability):** object còn được giữ sống bởi những tham chiếu nào.
3. **Thu gom rác (garbage collection):** JVM xác định và thu hồi vùng nhớ của object không còn reachable ra sao.

Bài học này giải thích mô hình heap và stack, cách object được cấp phát, GC roots, các mức reachability, những loại reference trong Java, các collector hiện đại có trong Java 17, và cách chẩn đoán tình trạng bộ nhớ.

## 1. Object được lưu ở đâu?

Một chương trình Java có thể tạo nhiều object:

~~~java
Customer customer = new Customer("C-100");
Order order = new Order(customer);
~~~

Biến `customer` và `order` là các biến tham chiếu. Chúng cho phép chương trình truy cập các object tương ứng. Trong mô hình bộ nhớ của JVM, object và array được cấp phát trên **heap**. Biến cục bộ và các frame của lời gọi phương thức được quản lý trong **Java stack** của từng thread.

Có thể hình dung đơn giản:

~~~text
Thread A - Java stack                 Heap
┌─────────────────────────┐       ┌──────────────────────┐
│ frame của main          │       │ Customer object      │
│ customer ───────────────┼──────>│ id = "C-100"         │
│ order ──────────────────┼───┐   └──────────────────────┘
└─────────────────────────┘   │
                              │   ┌──────────────────────┐
                              └──>│ Order object         │
                                  │ customer ─────────────┼───┐
                                  └──────────────────────┘   │
                                                            │
                                  ┌──────────────────────┐   │
                                  │ Customer object      │<──┘
                                  └──────────────────────┘
~~~

Sơ đồ chỉ mô tả quan hệ logic. JVM có thể tối ưu cách biểu diễn object trong lúc chạy; không nên suy ra mọi biến tham chiếu luôn tương ứng với một ô nhớ cố định như sơ đồ.

### 1.1. Java stack

Mỗi thread Java có stack riêng. Khi gọi phương thức, JVM tạo một stack frame để chứa dữ liệu phục vụ lần gọi đó, ví dụ:

- biến cục bộ;
- các toán hạng và kết quả trung gian của bytecode;
- thông tin phục vụ việc trả về và xử lý exception.

Khi phương thức kết thúc, frame tương ứng được loại khỏi stack. Điều đó có thể làm các tham chiếu trong frame biến mất khỏi tập tham chiếu đang hoạt động.

~~~java
static void process() {
    Customer customer = new Customer("C-200");
    System.out.println(customer.id());
}
~~~

Biến cục bộ `customer` thuộc phạm vi thực thi của phương thức. Object `Customer` được cấp phát theo mô hình heap; khi phương thức kết thúc và không còn đường tham chiếu nào khác tới object, object có thể trở thành đối tượng đủ điều kiện để GC thu hồi.

Không nên diễn đạt rằng “object tự động bị xóa ngay khi biến cục bộ ra khỏi scope”. GC không cam kết chạy tại thời điểm đó. Điều quan trọng là object có còn reachable hay không.

### 1.2. Heap

Heap là vùng bộ nhớ runtime dùng để cấp phát object và array. Các thread có thể cùng truy cập object trên heap nếu chúng có tham chiếu tới object đó.

Heap thường được chia thành các vùng hoặc region tùy garbage collector. Với collector generational, heap còn được tổ chức theo các thế hệ nhằm tận dụng quan sát rằng nhiều object có vòng đời ngắn.

Các object có thể tham chiếu lẫn nhau, tạo thành đồ thị object. GC không chỉ nhìn một biến riêng lẻ; nó xét khả năng đi tới object từ các điểm bắt đầu được JVM coi là GC roots.

### 1.3. Stack không phải nơi mặc định lưu mọi object

Trong code:

~~~java
int count = 10;
Customer customer = new Customer("C-300");
~~~

`count` là biến kiểu nguyên thủy. `customer` là biến tham chiếu. Object được tạo bởi `new Customer(...)` thuộc mô hình heap của Java.

JIT compiler có thể tối ưu một số allocation bằng escape analysis và scalar replacement. Trong trường hợp đó, JVM có thể loại bỏ việc tạo object vật lý nếu không cần thiết, hoặc thay object bằng các giá trị riêng lẻ trong mã máy đã tối ưu. Đây là tối ưu của runtime; lập trình viên không nên dựa vào giả định rằng object sẽ luôn được cấp phát trên stack.

## 2. Cấp phát object diễn ra như thế nào?

Khi thực hiện `new`, chương trình yêu cầu tạo object của một class:

~~~java
Invoice invoice = new Invoice("INV-001", 250_000);
~~~

Ở mức khái niệm, quá trình gồm:

1. JVM xác định class đã được nạp và khởi tạo cần thiết.
2. JVM dành vùng nhớ đủ cho object theo layout runtime.
3. Các trường instance nhận giá trị mặc định theo kiểu dữ liệu.
4. Constructor và chuỗi constructor được thực thi để khởi tạo object.
5. Tham chiếu tới object được trả về cho biểu thức `new`.

Giá trị mặc định gồm `0` cho kiểu số nguyên, `0.0` cho số thực, `false` cho boolean và `null` cho trường tham chiếu. Constructor có thể gán giá trị khác.

~~~java
class Account {
    int balance;          // mặc định 0
    boolean active;       // mặc định false
    String owner;         // mặc định null

    Account(String owner) {
        this.owner = owner;
        this.active = true;
    }
}
~~~

Không thể đọc một trường instance chưa được khởi tạo bằng cách dựa vào “giá trị rác” như trong một số ngôn ngữ quản lý bộ nhớ thủ công. Java bảo đảm các trường instance được khởi tạo với giá trị mặc định trước khi constructor thực hiện phần khởi tạo của nó.

### 2.1. Thread-Local Allocation Buffer (TLAB)

Trong HotSpot JVM, một kỹ thuật phổ biến để tăng tốc cấp phát object là **Thread-Local Allocation Buffer (TLAB)**. Mỗi thread có thể được cấp một vùng nhỏ trong heap để cấp phát object của thread đó.

Thay vì mọi lần tạo object đều phải tranh chấp trên một con trỏ cấp phát toàn cục, thread có thể dành vùng nhớ từ TLAB của chính nó với chi phí rất thấp. Khi TLAB hết chỗ, JVM có thể cấp TLAB mới hoặc dùng đường cấp phát khác.

~~~text
Heap
┌──────────────────────────────────────────────┐
│ TLAB của Thread A │ TLAB của Thread B        │
│ obj obj obj       │ obj obj                   │
│                  │                           │
│ vùng heap còn lại / các vùng GC quản lý       │
└──────────────────────────────────────────────┘
~~~

TLAB là chi tiết triển khai của JVM, không phải quy tắc ngôn ngữ Java. Không cần tự quản lý TLAB trong code ứng dụng. Tạo object nhỏ thường rẻ; điều quan trọng hơn là tránh allocation quá nhiều trong đường xử lý nóng nếu profiling cho thấy áp lực GC đáng kể.

### 2.2. Escape analysis và scalar replacement

JIT compiler có thể phân tích object có “thoát” khỏi phạm vi sử dụng cục bộ hay không. Nếu object không thoát và các điều kiện tối ưu phù hợp, JVM có thể:

- loại bỏ allocation vật lý;
- thay các trường object bằng các giá trị scalar;
- loại bỏ một số thao tác đồng bộ trên object không thoát.

Ví dụ:

~~~java
static int calculate() {
    Point point = new Point(3, 4);
    return point.x() + point.y();
}
~~~

Nếu `Point` không được trả về, lưu vào field hay truyền tới nơi có thể giữ nó, JIT có thể tối ưu việc tạo object trong một số tình huống.

Đây là tối ưu phụ thuộc runtime, phiên bản JVM, profile thực thi và hình dạng code. Không nên viết code phức tạp chỉ để ép escape analysis hoạt động. Hãy viết code rõ ràng trước, sau đó dùng profiler để xác định allocation nào thực sự tốn kém.

## 3. Object graph và GC roots

Một object còn có thể được truy cập nếu có đường tham chiếu từ một **GC root** tới object đó. GC roots là các điểm bắt đầu mà garbage collector xét khi xác định object còn reachable.

Các loại GC roots thường gặp trong JVM gồm:

- tham chiếu trong stack frame của thread đang hoạt động;
- tham chiếu tới object trong static field của class đang được giữ sống;
- tham chiếu JNI mà native code đang giữ;
- một số tham chiếu nội bộ của JVM, chẳng hạn object liên quan tới thread đang chạy hoặc class loader.

Danh sách chính xác và cách triển khai phụ thuộc JVM. Ý quan trọng là GC bắt đầu từ các root này rồi lần theo những tham chiếu mạnh trong object graph.

~~~text
GC roots
   │
   ├── static field ───────> Cache ───────> Entry
   │
   ├── thread stack ───────> Request ─────> Customer
   │
   └── JNI reference ──────> NativeBridge

Object không có đường đi từ bất kỳ root nào
   └── có thể trở thành unreachable
~~~

### 3.1. Ví dụ object còn reachable

~~~java
class Application {
    private static final List<String> CACHE = new ArrayList<>();

    static void remember(String value) {
        CACHE.add(value);
    }
}
~~~

Các phần tử trong `CACHE` được giữ bởi static field. Chừng nào class và field đó còn reachable theo vòng đời class loader, các phần tử vẫn có thể reachable. Nếu cache tăng vô hạn, bộ nhớ có thể tăng dù ứng dụng không còn cần những giá trị cũ.

### 3.2. Object không còn reachable

~~~java
Customer customer = new Customer("C-400");
customer = null;
~~~

Nếu không có tham chiếu nào khác tới object ban đầu, object đó không còn reachable từ biến `customer`. Nó có thể được GC thu hồi ở một lần chạy GC sau này.

Gán `null` không phải cách giải phóng bộ nhớ cần dùng thường xuyên. Khi biến ra khỏi phạm vi hoặc được gán một object khác, tham chiếu cũ có thể không còn được giữ. Chỉ dùng `null` khi điều đó có ý nghĩa trong logic hoặc giúp rút ngắn lifetime của tham chiếu trong một tình huống cụ thể đã được đo lường.

### 3.3. Chu trình tham chiếu vẫn có thể được thu gom

Một quan niệm sai phổ biến là hai object tham chiếu lẫn nhau sẽ không được GC thu gom:

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

Nếu không còn đường tham chiếu từ GC roots tới hai node, cả chu trình đều unreachable và có thể được thu gom. GC hiện đại không chỉ đếm số tham chiếu; nó xác định reachability từ roots.

## 4. Các mức reachability trong Java

Java định nghĩa các trạng thái reachability có ý nghĩa với API `java.lang.ref`:

| Trạng thái | Ý nghĩa khái quát |
| --- | --- |
| Strongly reachable | Có thể đi tới object bằng đường tham chiếu thông thường từ GC root mà không cần đi qua reference đặc biệt. |
| Softly reachable | Không strongly reachable, nhưng có thể đi tới qua một hoặc nhiều SoftReference. |
| Weakly reachable | Không strongly hoặc softly reachable, nhưng có thể đi tới qua WeakReference. |
| Phantom reachable | Không còn strongly, softly hoặc weakly reachable; object đã ở trạng thái phù hợp cho phantom reference sau các bước xử lý vòng đời liên quan. |
| Unreachable | Không reachable theo các mức trên. |

Các mức này liên quan đến việc JVM xử lý các loại reference khác nhau. Với code ứng dụng thông thường, object được giữ sống bằng strong reference là trường hợp phổ biến nhất.

### 4.1. Strong reference

Mọi phép gán tham chiếu thông thường đều tạo quan hệ strong reference:

~~~java
Customer customer = new Customer("C-500");
Customer another = customer;
~~~

Hai biến cùng trỏ tới một object. Object vẫn strongly reachable khi còn ít nhất một đường strong reference từ root.

Java không có cú pháp riêng tên là `StrongReference`; đây là cách gọi để phân biệt tham chiếu thông thường với SoftReference, WeakReference và PhantomReference.

### 4.2. SoftReference

`SoftReference<T>` cho phép giữ một tham chiếu mềm tới object. Khi object không còn strongly reachable nhưng còn softly reachable, GC có thể quyết định xóa soft references để thu hồi object khi cần bộ nhớ.

~~~java
import java.lang.ref.SoftReference;

byte[] imageData = loadImage();
SoftReference<byte[]> cachedImage = new SoftReference<>(imageData);

imageData = null;

byte[] value = cachedImage.get();
if (value == null) {
    value = loadImage();
    cachedImage = new SoftReference<>(value);
}
~~~

Sau khi object chỉ còn softly reachable, `get()` có thể trả về `null` nếu GC đã xóa tham chiếu. Vì vậy, code luôn phải xử lý trường hợp object không còn trong cache.

Không nên xem SoftReference là cơ chế cache có chính sách eviction ổn định. Thời điểm xóa phụ thuộc GC và áp lực bộ nhớ; ứng dụng không kiểm soát được chính xác cache sẽ giữ object bao lâu. Với cache production, thường nên dùng cache có giới hạn kích thước, thời gian sống và chính sách eviction rõ ràng.

### 4.3. WeakReference

`WeakReference<T>` không giữ object sống trước GC. Nếu object không còn strong hoặc soft reference giữ lại, GC có thể xóa weak references và object có thể được thu gom.

~~~java
import java.lang.ref.WeakReference;

Customer customer = new Customer("C-600");
WeakReference<Customer> weak = new WeakReference<>(customer);

System.out.println(weak.get() != null); // true khi strong reference còn giữ object

customer = null;
// Từ đây GC có thể thu gom object; thời điểm không được bảo đảm.
~~~

`weak.get()` trả về object nếu referent còn tồn tại, hoặc `null` nếu reference đã bị xóa. Không được viết logic yêu cầu object phải còn tồn tại sau khi đã bỏ strong references.

Weak references có thể hữu ích cho một số registry, metadata hoặc cấu trúc liên kết không muốn giữ object sống. Tuy nhiên, chúng không thay thế một chính sách quản lý vòng đời rõ ràng.

### 4.4. WeakHashMap

`WeakHashMap<K,V>` giữ key bằng weak reference. Khi key không còn được giữ mạnh ở nơi khác, entry có thể bị loại bỏ trong quá trình xử lý reference.

~~~java
Map<Object, String> metadata = new WeakHashMap<>();

Object key = new Object();
metadata.put(key, "metadata");

System.out.println(metadata.get(key)); // metadata
key = null;
// Entry có thể biến mất sau khi GC xử lý weak reference.
~~~

Không được giả định entry sẽ biến mất ngay sau khi `key = null`. Việc thu gom và dọn entry diễn ra không xác định thời điểm.

Một bẫy thường gặp: nếu value giữ strong reference quay lại key, key vẫn có thể reachable thông qua value trong map, làm entry không được thu gom như mong đợi. Cần xem toàn bộ đồ thị tham chiếu, không chỉ nhìn vào loại collection.

### 4.5. PhantomReference và ReferenceQueue

`PhantomReference<T>` phục vụ việc nhận biết object đã tới trạng thái phantom-reachable để thực hiện xử lý hậu kỳ. `get()` của phantom reference luôn trả `null`; không dùng nó để lấy lại object.

~~~java
import java.lang.ref.PhantomReference;
import java.lang.ref.ReferenceQueue;

ReferenceQueue<ResourceOwner> queue = new ReferenceQueue<>();
ResourceOwner owner = new ResourceOwner();
PhantomReference<ResourceOwner> phantom =
        new PhantomReference<>(owner, queue);
~~~

Khi GC xử lý reference và đưa phantom reference vào queue, ứng dụng có thể lấy reference đã được enqueue để thực hiện công việc dọn dẹp phù hợp. Trong code thực tế, phải quản lý queue và vòng đời reference cẩn thận; bản thân phantom reference không tự đóng file, socket hay native handle.

Phantom references là API mức thấp. Với nhu cầu dọn dẹp tài nguyên ngoài heap, ưu tiên `AutoCloseable` và try-with-resources; `Cleaner` có thể dùng như cơ chế dự phòng khi có yêu cầu cụ thể.

## 5. Object trở thành eligible for GC khi nào?

Một object đủ điều kiện để GC thu hồi khi không còn reachable theo các quy tắc của Java, kể cả các mức reference đặc biệt đã được xét. Điều đó không đồng nghĩa bộ nhớ được thu hồi ngay lập tức.

Ví dụ:

~~~java
static void createTemporaryObject() {
    byte[] buffer = new byte[10_000_000];
    // Xử lý buffer.
}

public static void main(String[] args) {
    createTemporaryObject();
    // buffer không còn nằm trong frame của createTemporaryObject.
    // Object có thể trở thành eligible for GC nếu không còn tham chiếu khác.
}
~~~

GC có thể chạy sau đó khi JVM thấy phù hợp. Nếu heap còn đủ chỗ, JVM có thể chưa thu gom ngay. Do đó:

- Không thể dựa vào GC để thực thi một hành động nghiệp vụ đúng thời điểm.
- Không thể dựa vào GC để đóng socket hoặc file đúng lúc.
- Không nên dùng `System.gc()` để điều khiển thời điểm object bị thu hồi.

### 5.1. System.gc() không phải lệnh giải phóng bắt buộc

~~~java
System.gc();
~~~

Lời gọi này chỉ yêu cầu JVM xem xét thực hiện garbage collection. JVM có thể bỏ qua, trì hoãn hoặc xử lý theo chính sách runtime; cờ `-XX:+DisableExplicitGC` còn có thể vô hiệu hóa các yêu cầu GC tường minh.

Không nên gọi `System.gc()` trong logic ứng dụng để “chữa” memory leak hoặc đảm bảo object đã biến mất. Hãy sửa đường tham chiếu giữ object và cấu hình/điều tra heap theo dữ liệu đo được.

## 6. Garbage collector thu gom như thế nào?

GC hiện đại thường dựa trên reachability tracing: bắt đầu từ GC roots, lần theo tham chiếu để đánh dấu object còn sống; object không được đánh dấu có thể được thu hồi. Tùy collector, quá trình có thể bao gồm:

- mark: xác định object còn reachable;
- sweep: thu hồi vùng nhớ của object không còn sống;
- compact: di chuyển object sống để giảm phân mảnh;
- copy/evacuate: chuyển object sống sang vùng nhớ khác.

Không phải collector nào cũng thực hiện mọi bước theo cùng cách hoặc trong cùng một pha. Đây là mô hình khái niệm giúp hiểu GC, không phải mô tả chính xác từng thuật toán của mọi JVM.

### 6.1. Stop-the-world pause

Một số pha GC cần tạm dừng các thread ứng dụng để JVM có thể thực hiện công việc nhất quán. Khoảng dừng đó thường được gọi là **stop-the-world (STW) pause**.

~~~text
Thời gian ───────────────────────────────────────────────>
Application threads:  chạy chạy chạy | dừng | chạy chạy
GC work:                         chuẩn bị | GC  | tiếp tục
~~~

Collector hiện đại cố gắng giảm thời gian và/hoặc tần suất pause, nhưng không có collector phổ thông nào bảo đảm ứng dụng không bao giờ pause. Mục tiêu throughput, latency và footprint là các trade-off.

### 6.2. Generational collection

Nhiều collector tận dụng giả thuyết generational: phần lớn object mới tạo có vòng đời ngắn. Heap được chia thành các vùng đại diện cho object mới và object sống lâu hơn.

Mô hình generational cổ điển:

~~~text
Young generation
┌─────────────────────────────────┐
│ Eden │ Survivor 0 │ Survivor 1  │
└─────────────────────────────────┘
                  │ object sống lâu qua các lần thu gom
                  v
Old generation
┌─────────────────────────────────┐
│ object được giữ lại lâu hơn      │
└─────────────────────────────────┘
~~~

Object mới thường được cấp phát trong vùng dành cho object trẻ. Khi có young collection, object còn sống được giữ lại hoặc di chuyển; object sống qua nhiều chu kỳ có thể được promote sang vùng dành cho object lâu sống.

Đây là mô hình hữu ích để hiểu G1 và các collector generational. Cách tổ chức vật lý cụ thể thay đổi theo collector; không nên giả định mọi collector Java 17 đều có cùng các vùng Eden/Survivor/Old như sơ đồ.

### 6.3. Allocation rate và live set

Hai chỉ số cần phân biệt:

- **Allocation rate:** tốc độ chương trình tạo object mới.
- **Live set:** lượng object vẫn reachable sau khi GC đã thu gom những object không còn sống.

Allocation rate cao có thể khiến GC chạy thường xuyên dù live set nhỏ. Ngược lại, live set lớn có thể khiến mỗi chu kỳ GC phải xử lý nhiều object còn sống và làm tăng áp lực heap.

Nếu chương trình tạo nhiều object ngắn hạn, cần xem allocation profile. Nếu heap tăng dần và live set không giảm sau các chu kỳ GC, hãy điều tra các đường tham chiếu giữ object lâu hơn dự kiến.

## 7. Các garbage collector có trong Java 17

Java 17 có nhiều collector để lựa chọn. Mỗi collector có mục tiêu khác nhau; khả năng có sẵn có thể phụ thuộc bản phân phối JVM và nền tảng.

| Collector | Đặc điểm khái quát | Trường hợp thường cân nhắc |
| --- | --- | --- |
| Serial GC | Thu gom chủ yếu bằng một thread GC; đơn giản, footprint thấp nhưng pause có thể dài khi heap lớn. | Ứng dụng nhỏ, môi trường tài nguyên hạn chế. |
| Parallel GC | Dùng nhiều thread để tăng tốc công việc GC và tối ưu throughput. | Batch hoặc workload ưu tiên tổng lượng công việc hoàn thành. |
| G1 GC | Collector generational theo region, cân bằng throughput và pause; là collector mặc định trên các cấu hình server-class phổ biến của Java 17. | Ứng dụng server tổng quát, heap vừa đến lớn. |
| ZGC | Collector độ trễ thấp, thực hiện phần lớn công việc đồng thời với ứng dụng; có trong Java 17 ở trạng thái production. | Workload cần pause ngắn và có đủ tài nguyên cho collector. |
| Shenandoah | Collector độ trễ thấp với phần lớn công việc thu gom đồng thời; khả năng có sẵn tùy bản phân phối JVM. | Ứng dụng nhạy với latency trên runtime có hỗ trợ. |

Không có lựa chọn “nhanh nhất” cho mọi workload. Hãy đo thời gian pause, throughput, heap occupancy, allocation rate và CPU dùng cho GC trên môi trường gần production.

### 7.1. G1 GC

G1 chia heap thành nhiều region có kích thước tương đối đồng nhất. Các region có thể được dùng cho object trẻ, object lâu sống hoặc mục đích GC khác nhau. G1 ưu tiên thu gom những region có lượng rác có thể thu hồi cao để đạt mục tiêu pause đã cấu hình.

Đặc điểm:

- có các chu kỳ young collection và mixed collection;
- một số công việc đánh dấu được thực hiện đồng thời với ứng dụng;
- có thể chọn region dựa trên lượng bộ nhớ dự kiến thu hồi;
- cố gắng đáp ứng mục tiêu pause, nhưng mục tiêu không phải cam kết cứng.

Chọn G1 tường minh:

~~~bash
java -XX:+UseG1GC -Xms2g -Xmx2g -jar app.jar
~~~

Trong nhiều môi trường Java 17 server, G1 đã là lựa chọn mặc định theo ergonomics; không nhất thiết phải thêm cờ nếu không có lý do.

### 7.2. Parallel GC

Parallel GC ưu tiên throughput. Nó dùng nhiều thread GC để thực hiện các pha thu gom, giúp rút ngắn thời gian GC so với cách xử lý đơn luồng trên máy nhiều core. Tuy nhiên, các pause stop-the-world có thể dài hơn lựa chọn thiên về latency.

~~~bash
java -XX:+UseParallelGC -Xms2g -Xmx2g -jar batch-job.jar
~~~

Collector này có thể phù hợp với tác vụ batch khi thông lượng tổng thể quan trọng hơn pause ngắn.

### 7.3. Serial GC

Serial GC dùng một thread GC và có footprint đơn giản. Với heap nhỏ hoặc môi trường ít CPU, chi phí phối hợp thấp có thể hữu ích.

~~~bash
java -XX:+UseSerialGC -Xms128m -Xmx512m -jar small-tool.jar
~~~

Với workload server nhiều thread hoặc heap lớn, cần đo cẩn thận vì một thread GC có thể không đáp ứng được tốc độ cấp phát và yêu cầu pause.

### 7.4. ZGC

ZGC được thiết kế để giữ thời gian pause rất thấp bằng cách thực hiện phần lớn công việc nặng đồng thời với ứng dụng. Trong Java 17, ZGC là collector production; chế độ generational chưa phải đặc tính của ZGC trong phiên bản này.

~~~bash
java -XX:+UseZGC -Xms4g -Xmx4g -jar latency-sensitive-app.jar
~~~

ZGC có thể hữu ích khi pause dài ảnh hưởng trực tiếp tới latency. Nó vẫn cần CPU và bộ nhớ để thực hiện công việc đồng thời; workload, cấu hình heap và phần cứng quyết định hiệu quả thực tế.

### 7.5. Shenandoah

Shenandoah cũng hướng tới latency thấp bằng cách thực hiện phần lớn công việc GC đồng thời với ứng dụng. Khả năng có sẵn collector này phụ thuộc bản dựng OpenJDK/vendor và nền tảng đang sử dụng.

Không nên giả định mọi bản JDK 17 đều cung cấp cùng collector hoặc cùng cờ. Kiểm tra tài liệu của bản phân phối và thông tin runtime phù hợp trước khi cấu hình.

## 8. Quản lý tài nguyên không phải là garbage collection

GC quản lý bộ nhớ của object trên heap. Nó không thay thế việc đóng các tài nguyên hệ điều hành như:

- file descriptor;
- socket và network connection;
- database connection;
- lock hoặc handle native;
- stream và resource do thư viện ngoài quản lý.

Các tài nguyên này nên được đóng theo vòng đời xác định bằng `AutoCloseable` và try-with-resources:

~~~java
import java.io.BufferedReader;
import java.nio.file.Files;
import java.nio.file.Path;

try (BufferedReader reader =
        Files.newBufferedReader(Path.of("data.txt"))) {
    String line = reader.readLine();
    System.out.println(line);
}
~~~

Khi rời khỏi block, `close()` được gọi tự động. Không phải chờ GC thu gom object `reader` mới đóng file.

### 8.1. finalize() là cơ chế cũ, không nên dùng

`Object.finalize()` đã bị deprecated for removal. Finalization không bảo đảm thời điểm chạy, có thể làm object sống lại và gây các vấn đề về hiệu năng, bảo mật cũng như độ tin cậy.

Không viết code quản lý tài nguyên bằng `finalize()`. Hãy dùng:

- `AutoCloseable` và try-with-resources cho đóng tài nguyên xác định;
- `Cleaner` như cơ chế dự phòng trong những trường hợp cần thiết, không phải cách đóng tài nguyên chính;
- API quản lý lifecycle rõ ràng của thư viện hoặc framework.

### 8.2. Cleaner

`java.lang.ref.Cleaner` cho phép đăng ký hành động cleanup sẽ được thực hiện khi object trở nên phantom-reachable và cleaner xử lý tác vụ tương ứng.

Cleaner là cơ chế dự phòng. Không có cam kết hành động cleanup sẽ chạy ngay hoặc chắc chắn chạy trước khi tiến trình kết thúc. Nếu tài nguyên cần đóng đúng lúc, vẫn phải gọi `close()` tường minh.

## 9. Memory leak trong ngôn ngữ có garbage collector

Memory leak trong Java thường không phải là vùng nhớ bị bỏ quên hoàn toàn mà là **object không còn cần thiết nhưng vẫn reachable**. Vì GC thấy đường tham chiếu từ root, nó phải giữ object lại.

Một số nguyên nhân thường gặp:

### 9.1. Collection tăng không giới hạn

~~~java
class EventHistory {
    private final List<Event> events = new ArrayList<>();

    void record(Event event) {
        events.add(event);
    }
}
~~~

Nếu `events` không bao giờ được giới hạn hoặc dọn, tất cả event vẫn reachable qua list. Dùng cache có giới hạn kích thước, TTL hoặc chính sách eviction phù hợp.

### 9.2. Listener không được gỡ bỏ

Một đối tượng đăng ký listener vào publisher có thể bị publisher giữ lại. Dù code không còn dùng listener, tham chiếu từ publisher vẫn làm listener reachable.

Hãy hủy đăng ký khi component kết thúc vòng đời:

~~~java
publisher.removeListener(listener);
~~~

Framework thường có lifecycle hook để cleanup subscription; cần dùng đúng hook thay vì dựa vào GC.

### 9.3. ThreadLocal trong thread pool

Thread pool giữ worker thread sống lâu. Giá trị đặt trong ThreadLocal có thể tiếp tục được giữ bởi worker sau khi task hoàn thành nếu ứng dụng không gọi `remove()` và không ghi đè giá trị.

~~~java
private static final ThreadLocal<RequestContext> CONTEXT =
        new ThreadLocal<>();

void handle(Request request) {
    try {
        CONTEXT.set(new RequestContext(request));
        processRequest();
    } finally {
        CONTEXT.remove();
    }
}
~~~

`remove()` trong `finally` giúp tránh giữ request context qua các task khác nhau chạy trên cùng worker.

### 9.4. Static field và class loader

Static collection, registry hoặc callback có thể giữ object sống rất lâu. Trong ứng dụng có plugin, application server hoặc hot reload, tham chiếu từ class loader sống lâu sang class loader của ứng dụng đã dừng có thể giữ cả class và object liên quan.

Khi unload một module/plugin, cần gỡ listener, thread, ThreadLocal, registry và static reference do plugin đăng ký.

### 9.5. Cache không có giới hạn

Cache không có eviction có thể trở thành memory leak dù mỗi entry vẫn đang được “sử dụng” theo nghĩa reachable. Hãy định nghĩa:

- giới hạn số entry hoặc dung lượng;
- thời gian sống;
- chính sách loại bỏ;
- cách đồng bộ và tải lại dữ liệu.

WeakReference không tự động biến một cache thành cache tốt; thời điểm GC xóa weak reference không phải chính sách eviction mà ứng dụng có thể dự đoán.

## 10. Heap, Metaspace và bộ nhớ native

Không phải mọi phần bộ nhớ của một tiến trình Java đều nằm trong Java heap.

| Khu vực | Chứa gì (khái quát) | Quản lý |
| --- | --- | --- |
| Java heap | Object và array. | Garbage collector. |
| Java stacks | Stack frame của từng thread. | Tạo/loại frame theo lời gọi; stack thuộc vòng đời thread. |
| Metaspace | Metadata của class và một số dữ liệu liên quan class loader. | JVM quản lý; có thể thu hồi metadata khi class loader đủ điều kiện unload. |
| Code cache | Mã máy đã được JIT compiler biên dịch. | JVM quản lý. |
| Direct/native memory | Bộ đệm ngoài heap, thư viện native, cấu trúc runtime và vùng nhớ hệ điều hành cấp phát. | JVM, thư viện và cơ chế native tương ứng. |

Vì vậy, lỗi `OutOfMemoryError` không nhất thiết có nghĩa Java heap đã đầy. Có các loại lỗi như:

- `Java heap space`;
- `Metaspace`;
- `Direct buffer memory`;
- `unable to create native thread`;
- các lỗi native allocation khác.

Khi điều tra, hãy xác định đúng vùng bộ nhớ bị cạn trước khi tăng `-Xmx`.

## 11. Cấu hình heap và quan sát GC trong Java 17

### 11.1. -Xms và -Xmx

- `-Xms` đặt kích thước heap ban đầu/tối thiểu theo cấu hình JVM.
- `-Xmx` đặt giới hạn heap tối đa.

Ví dụ:

~~~bash
java -Xms512m -Xmx2g -jar app.jar
~~~

Không nên đặt `-Xmx` mà không tính tổng memory limit của container hoặc máy. Tiến trình còn cần stack cho thread, metaspace, code cache, direct buffer, native library và các vùng runtime khác.

### 11.2. Bật GC logging

Java 17 dùng unified logging. Bật log GC bằng:

~~~bash
java -Xlog:gc*:file=logs/gc.log:time,uptime,level,tags \
    -Xms512m -Xmx2g -jar app.jar
~~~

Log có thể giúp quan sát:

- thời điểm GC bắt đầu/kết thúc;
- loại chu kỳ GC;
- thời gian pause;
- heap occupancy trước và sau GC;
- region hoặc thế hệ liên quan, tùy collector.

Không nên chỉ nhìn số lần GC. Cần đọc xu hướng occupancy, allocation và pause trong cùng một khoảng tải.

### 11.3. Dùng jcmd

`jcmd` là công cụ chẩn đoán JVM. Ví dụ:

~~~bash
jcmd
jcmd <pid> VM.flags
jcmd <pid> GC.heap_info
jcmd <pid> GC.class_histogram
~~~

`jcmd` không tự động giải thích nguyên nhân memory leak, nhưng cung cấp thông tin hữu ích để định hướng điều tra. Một số lệnh chẩn đoán có thể gây tạm dừng hoặc tiêu thụ tài nguyên; hãy kiểm tra tác động của lệnh trước khi chạy trên hệ thống nhạy cảm với latency.

### 11.4. Heap dump và profiler

Khi heap tăng bất thường, heap dump giúp xem object nào đang chiếm bộ nhớ và vì sao chúng còn reachable. Có thể dùng:

- Java Flight Recorder (JFR) để quan sát allocation, GC và hành vi runtime;
- Java Mission Control để phân tích bản ghi JFR;
- công cụ phân tích heap dump như Eclipse MAT để xem dominator tree và đường dẫn tới GC roots;
- profiler của IDE hoặc công cụ APM có hỗ trợ allocation profiling.

Một cách điều tra hiệu quả là tìm class có số lượng hoặc retained heap lớn, rồi lần theo đường tham chiếu ngược về GC roots để xác định thành phần đang giữ object.

## 12. Ví dụ: phân biệt allocation nhiều và memory leak

### Trường hợp A: nhiều object ngắn hạn

~~~java
static long calculate() {
    long total = 0;
    for (int i = 0; i < 1_000_000; i++) {
        String value = "item-" + i;
        total += value.length();
    }
    return total;
}
~~~

Đoạn code tạo nhiều object tạm thời. Nếu chúng không được giữ lại sau mỗi vòng lặp, GC có thể thu hồi chúng. Allocation rate có thể cao, nhưng live set có thể vẫn ổn định.

### Trường hợp B: giữ object mãi trong collection

~~~java
static final List<byte[]> RETAINED = new ArrayList<>();

static void allocate() {
    RETAINED.add(new byte[1024 * 1024]);
}
~~~

Mỗi lần gọi `allocate()`, một mảng 1 MB được thêm vào static list. Các mảng vẫn reachable từ GC root qua static field và list. GC không thể thu hồi chúng cho tới khi ứng dụng xóa entry hoặc loại bỏ đường tham chiếu.

Hai trường hợp đều tạo object, nhưng nguyên nhân và cách khắc phục khác nhau:

| Dấu hiệu | Allocation pressure | Retained-memory leak |
| --- | --- | --- |
| Số object mới tạo | Cao | Có thể cao hoặc vừa. |
| Live set sau GC | Có thể ổn định | Có xu hướng tăng nếu leak tiếp diễn. |
| GC có thu hồi nhiều object không? | Thường có | Không thu hồi được object còn reachable. |
| Hướng điều tra | Allocation profile, giảm allocation không cần thiết. | Heap dump, dominator tree, GC roots, giới hạn cache/lifecycle. |

## 13. Các lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Gán biến bằng `null` nhưng heap chưa giảm ngay | GC không chạy ngay khi object mất tham chiếu. | Hiểu eligibility khác với thời điểm thu hồi; quan sát GC và live set. |
| Hai object tham chiếu lẫn nhau không được thu gom theo dự đoán | Có thể vẫn còn đường tham chiếu từ GC root. | Phân tích toàn bộ object graph và GC roots; chu trình tự nó không ngăn GC. |
| Dùng `System.gc()` nhưng bộ nhớ không giảm | Đây chỉ là yêu cầu/hint, JVM có thể bỏ qua; object có thể vẫn reachable. | Sửa retention path và dùng GC log/heap dump. |
| Ứng dụng đầy heap dù không có object nào “đang dùng” theo nghiệp vụ | Static collection, cache hoặc listener vẫn giữ object reachable. | Giới hạn cache, gỡ listener và dọn lifecycle. |
| Dùng SoftReference làm cache nhưng hit rate khó đoán | GC quyết định thời điểm xóa soft reference. | Dùng cache có giới hạn và eviction policy rõ ràng. |
| Thread pool giữ request context cũ | ThreadLocal không được remove sau task. | Gọi `ThreadLocal.remove()` trong `finally`. |
| File/socket không được đóng dù object đã không còn biến tham chiếu | GC không phải cơ chế đóng tài nguyên đúng thời điểm. | Dùng AutoCloseable và try-with-resources. |
| `OutOfMemoryError: Metaspace` nhưng heap còn trống | Metadata class/metaspace bị cạn, có thể liên quan class loader hoặc giới hạn metaspace. | Kiểm tra class loading/unloading và class loader retention. |
| `OutOfMemoryError: Direct buffer memory` | Bộ nhớ direct buffer ngoài heap bị cạn. | Kiểm tra lifecycle buffer, giới hạn direct memory và native memory. |
| GC pause dài | Heap/live set lớn, collector hoặc cấu hình không phù hợp, hoặc allocation pressure cao. | Đọc GC log, đo workload, xem collector và heap sizing. |
| Tăng `-Xmx` chỉ trì hoãn lỗi | Object vẫn bị giữ không giới hạn hoặc vùng memory khác bị cạn. | Xác định loại OOME và tìm nguyên nhân retention/allocation. |
| `finalize()` không chạy đúng lúc | Finalization không bảo đảm thời điểm và đã deprecated for removal. | Dùng try-with-resources; Cleaner chỉ làm dự phòng. |

## 14. Bài tập tự luyện

### Bài 1 — Xác định object còn reachable

~~~java
static List<Object> cache = new ArrayList<>();

static void run() {
    Object first = new Object();
    Object second = new Object();
    cache.add(first);
    first = null;
    second = null;
}
~~~

Sau khi `run()` kết thúc, object nào có thể được GC thu hồi? Giải thích đường tham chiếu của từng object.

**Gợi ý:** object đầu tiên vẫn được giữ qua static list; object thứ hai không có đường tham chiếu nào được lưu lại từ root sau khi frame kết thúc.

### Bài 2 — Chu trình tham chiếu

Tạo hai object Node tham chiếu lẫn nhau. Sau đó bỏ mọi tham chiếu từ biến cục bộ. Giải thích vì sao GC vẫn có thể thu gom cả hai.

### Bài 3 — WeakReference

Tạo một WeakReference tới một object, bỏ strong reference và đọc `weak.get()`. Vì sao không thể viết test yêu cầu `get()` phải trả null ngay sau khi gán biến bằng null?

### Bài 4 — Tìm memory leak trong ThreadLocal

Viết một task đặt RequestContext vào ThreadLocal trong thread pool. Bổ sung `try/finally` và `remove()` để worker không giữ context của request trước.

### Bài 5 — Phân biệt allocation rate và live set

Một ứng dụng tạo hàng triệu String ngắn hạn mỗi phút, nhưng heap sau GC luôn quay về gần cùng một mức. Đây có nhất thiết là memory leak không? Nêu chỉ số cần xem để phân biệt allocation pressure với retained memory.

### Bài 6 — Chọn collector

Một batch job ưu tiên throughput; một API cần latency ổn định với pause ngắn; một công cụ nhỏ chạy trên máy ít tài nguyên. Hãy cân nhắc Parallel GC, G1/ZGC và Serial GC tương ứng. Nêu vì sao cần benchmark trên workload thật.

### Bài 7 — Quản lý tài nguyên

Viết đoạn code đọc file bằng try-with-resources. Giải thích vì sao không nên chờ garbage collector thu gom FileInputStream để đóng file.

## 15. Ghi nhớ về cấp phát, reachability và GC

- Object và array thuộc mô hình heap; biến cục bộ và stack frame thuộc Java stack của từng thread.
- JVM có thể tối ưu allocation bằng TLAB, escape analysis hoặc scalar replacement; đây là chi tiết runtime, không phải điều code được phép giả định.
- GC xác định object còn sống bằng cách lần theo tham chiếu từ GC roots.
- Object không còn reachable có thể trở thành eligible for GC, nhưng không được bảo đảm thu hồi ngay.
- Chu trình tham chiếu không ngăn GC nếu cả chu trình không còn đường đi từ root.
- Strong reference giữ object sống; SoftReference, WeakReference và PhantomReference có semantics khác nhau và không thay thế cache/lifecycle policy rõ ràng.
- Memory leak trong Java thường là object không còn cần nhưng vẫn reachable qua static field, collection, listener, ThreadLocal hoặc class loader.
- GC quản lý heap; tài nguyên như file, socket và database connection cần được đóng tường minh bằng AutoCloseable/try-with-resources.
- Tránh finalize() vì đã deprecated for removal; Cleaner chỉ là cơ chế dự phòng.
- G1, Parallel, Serial, ZGC và Shenandoah có mục tiêu khác nhau; lựa chọn collector dựa trên số liệu workload, không dựa trên một quy tắc chung.
- Đọc GC log, JFR, heap dump và đường dẫn tới GC roots để phân biệt allocation pressure với retained-memory leak.

### Tài liệu tham khảo

- [Java SE 17 — Java Virtual Machine Specification, Runtime Data Areas](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html#jvms-2.5) — heap, stacks và vùng dữ liệu runtime.
- [Java SE 17 API — Object](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html) — vòng đời object và trạng thái deprecated của finalization.
- [Java SE 17 API — java.lang.ref](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/package-summary.html) — SoftReference, WeakReference, PhantomReference, ReferenceQueue và Cleaner.
- [Java SE 17 API — Cleaner](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/Cleaner.html) — hành động cleanup dự phòng.
- [Java SE 17 G1 Garbage Collector](https://docs.oracle.com/en/java/javase/17/gctuning/garbage-first-garbage-collector-tuning.html) — cấu trúc và điều chỉnh G1.
- [Java SE 17 ZGC](https://docs.oracle.com/en/java/javase/17/gctuning/z-garbage-collector.html) — collector độ trễ thấp.
- [Java SE 17 Shenandoah GC](https://wiki.openjdk.org/display/shenandoah/Main) — thông tin collector Shenandoah; khả năng sử dụng phụ thuộc bản phân phối.
- [Java SE 17 Troubleshooting Guide](https://docs.oracle.com/en/java/javase/17/troubleshoot/) — công cụ chẩn đoán, GC logging và phân tích bộ nhớ.
