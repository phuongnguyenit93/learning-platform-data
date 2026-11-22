# AppCDS: Phân biệt siêu dữ liệu lớp với trạng thái đối tượng nghiệp vụ (Java 10+)

## 1. Kết luận cốt lõi

**Application Class-Data Sharing (AppCDS)**, xuất hiện ở **Java 10 qua JEP 310**, giúp JVM **tái sử dụng dữ liệu về lớp** đã được xử lý và lưu trong một archive. Điều đó có thể giảm công việc nạp lớp lúc khởi động và tiết kiệm bộ nhớ khi nhiều tiến trình Java dùng chung những trang archive tương thích.

AppCDS **không phải** một cơ chế **persist/restore dữ liệu nghiệp vụ**. Nó không tự lưu giỏ hàng, đơn hàng, trạng thái đăng nhập, số dư tài khoản, session hay bộ đếm request của lần chạy trước để nạp lại vào lần chạy sau.

**Phân biệt ngay từ ví dụ nhỏ:**

~~~java
final class Order {
    private String status = "NEW";

    void pay() {
        status = "PAID";
    }
}
~~~

- **Siêu dữ liệu lớp (*class metadata*)**: tên lớp `Order`, cấu trúc trường `status`, chữ ký phương thức `pay()`, thông tin bytecode và các dữ liệu giúp JVM nạp/liên kết/thực thi lớp.
- **Trạng thái đối tượng (*instance state*)**: giá trị `status` của **một `new Order()` cụ thể**. Trước khi gọi `pay()`, nó là `NEW`; sau khi gọi, nó là `PAID`.
- **Dữ liệu bền vững (*persistent business data*)**: trạng thái đơn hàng được ứng dụng **chủ động ghi vào database hoặc một kho dữ liệu tin cậy**, rồi có thể khôi phục khi tiến trình kết thúc.

Một lớp `Order` có thể được lấy từ archive AppCDS mà nhiều instance `Order` vẫn được ứng dụng tạo và thay đổi **mới** ở mỗi lần chạy.

## 2. CDS, AppCDS và AOT cache đang được dùng hiện nay

| Tên | Vai trò | Giới hạn cần nhớ |
| --- | --- | --- |
| **CDS** (*Class Data Sharing*) | Lưu các dữ liệu lớp nền tảng và những lớp đủ điều kiện trong archive, tái sử dụng ở các lần khởi động tương thích | Không phải database |
| **AppCDS** (*Application CDS*) | Mở rộng cơ chế CDS để bao gồm dữ liệu lớp của ứng dụng/thư viện | Không tự lưu toàn bộ instance runtime |
| **AOT Cache** (JDK 24+) | Cache artifact tối ưu hóa được chuẩn bị trước, bao gồm dữ liệu lớp đã nạp/liên kết; ở JDK mới có thể chứa cả **những heap object được chọn** | Không phải heap snapshot nghiệp vụ chung cho mọi JVM |

**Lịch sử vừa đủ để áp dụng đúng hiện nay:**

- Java 10: JEP 310 đưa **AppCDS** vào OpenJDK/HotSpot.
- Các JDK sau đó mở rộng khả năng tạo và sử dụng archives; **dynamic CDS archive** là cơ chế hiện còn hỗ trợ.
- JDK 24: JEP 483 đưa **Ahead-of-Time Class Loading & Linking** và AOT cache; hướng AOT tiếp tục phát triển trên JDK mới.
- Tài liệu launcher **Java SE 26** vẫn mô tả CDS/AppCDS, `-XX:SharedArchiveFile` và `-XX:ArchiveClassesAtExit`, bên cạnh AOT cache.

**Ngoại lệ quan trọng:** không nên nói “mọi cơ chế CDS/AOT tuyệt đối không thể chứa heap object”. AOT cache ở HotSpot hiện đại **có thể chứa những heap object được JVM chọn để tối ưu hóa**. Nhưng không có nghĩa mọi `Order`, `Cart`, `UserSession` đang bị sửa ở ứng dụng sẽ tự động trở thành dữ liệu nghiệp vụ bền vững. **Bài học này phân biệt ranh giới mục đích và hợp đồng**: class/AOT artifact là tài sản tối ưu JVM; trạng thái nghiệp vụ phải được quản lý theo kiến trúc dữ liệu ứng dụng.

## 3. Class metadata là gì?

Khi một class file được nạp, JVM phải hiểu một loạt thông tin về kiểu:

- Tên lớp, gói, superclass, interface.
- Mô tả trường: tên, kiểu, đặc tính truy cập và cấu trúc liên quan.
- Mô tả constructor, phương thức, chữ ký và bytecode.
- Constant pool, các tham chiếu biểu tượng và dữ liệu để liên kết.
- Thông tin nội bộ của HotSpot phục vụ nạp, kiểm tra, liên kết và thực thi lớp.

Ví dụ:

~~~java
final class Product {
    private final String code;
    private int stock;

    Product(String code, int stock) {
        this.code = code;
        this.stock = stock;
    }

    int stock() {
        return stock;
    }
}
~~~

Dù ứng dụng tạo một, một nghìn hay một triệu `Product`, **định nghĩa lớp** vẫn mô tả các trường `code`, `stock` và các phương thức như trên. AppCDS có thể lưu **dạng biểu diễn lớp đã chuẩn bị** phù hợp với phiên bản HotSpot để tránh lặp một phần công việc nạp lớp trong những JVM sau.

Ngược lại:

~~~java
Product a = new Product("SKU-A", 10);
Product b = new Product("SKU-B", 50);
~~~

Các giá trị `SKU-A`, `10`, `SKU-B` và `50` là **dữ liệu của instance**, không phải dữ liệu metadata chung của định nghĩa lớp `Product`. Việc `a.stock()` trả `10` và `b.stock()` trả `50` không cần hai định nghĩa lớp khác nhau.

### Có phải `Product.class` chính là toàn bộ metadata?

Không. `Product.class` cho một đối tượng `java.lang.Class<?>` dùng với reflection:

~~~java
Class<Product> type = Product.class;
System.out.println(type.getSimpleName()); // Product
~~~

Đối tượng `Class<?>` **đại diện cho một loại**, không phải một `Product` instance và không đồng nghĩa toàn bộ dữ liệu VM lưu cho loại đó. Trong HotSpot, metadata nội bộ có thể liên quan metaspace/CDS và các cấu trúc khác. Bố trí cụ thể có thể thay đổi giữa JDK; không dùng một sơ đồ bộ nhớ nội bộ cứng để suy ra tính bền vững của object state.

## 4. Business object state là gì?

**Trạng thái nghiệp vụ** là các giá trị phát sinh hoặc thay đổi trong quá trình ứng dụng chạy:

~~~java
final class Order {
    private final String id;
    private String status;

    Order(String id) {
        this.id = id;
        this.status = "NEW";
    }

    void markPaid() {
        this.status = "PAID";
    }

    String status() {
        return status;
    }
}
~~~

~~~java
Order first = new Order("A-1");
Order second = new Order("B-2");

first.markPaid();

System.out.println(first.status());  // PAID
System.out.println(second.status()); // NEW
~~~

Đây là **hai đối tượng riêng**, dù chúng có cùng class metadata. Một instance có thể thay đổi, instance còn lại không bị ảnh hưởng.

Ví dụ khác:

- `Map<String, Order> orders` chứa đơn hàng trong bộ nhớ của ứng dụng.
- `List<CartItem> cart` biểu diễn giỏ hàng đang được xử lý.
- `UserSession session` chứa thời điểm đăng nhập, quyền hiện tại, hạn session.
- `AtomicInteger activeConnections` lưu số kết nối của một JVM cụ thể.
- `ConcurrentHashMap<Key, Value> cache` chứa dữ liệu ứng dụng đã tính ở runtime.
- Một biến `static int requestCount` được tăng theo request trong tiến trình.

Không cái nào **tự** được AppCDS coi là “trạng thái cần phục hồi sau restart” chỉ vì các lớp chứa nó được archive.

## 5. Sơ đồ phân biệt hai JVM dùng chung archive

~~~text
             app.jsa (CDS archive)
         +-----------------------------+
         | Dữ liệu lớp đã được xử lý   |
         | Thông tin kiểu / metadata  |
         +-----------------------------+
                    |         |
         memory-map |         | memory-map
                    v         v
          +---------------+ +---------------+
          | JVM process A | | JVM process B |
          |---------------| |---------------|
          | Class context | | Class context |
          | Heap A:       | | Heap B:       |
          |   Order A     | |   Order B     |
          |   session A   | |   session B   |
          |   cache A     | |   cache B     |
          | static vars A | | static vars B |
          +---------------+ +---------------+
                    |         |
                    v         v
         Database / external storage
         (chỉ có nếu app tự kết nối)
~~~

**Điều được chia sẻ:** các trang chứa **dữ liệu class/archive thích hợp** có thể được ánh xạ vào nhiều JVM, giúp hệ điều hành tiết kiệm bộ nhớ vật lý cho phần dữ liệu giống nhau.

**Điều không tự chia sẻ:** heap mutable của JVM A với heap mutable của JVM B. Hai JVM không tự có cùng đối tượng `Order` chỉ vì chạy cùng bytecode và cùng tệp archive. Các trạng thái mutable `static` cũng **không trở thành một vùng nhớ ứng dụng toàn máy**.

Những gì ứng dụng muốn chia sẻ **thật sự** giữa các process phải được thiết kế: database, shared cache, queue, external service, IPC hoặc giao thức đồng bộ phù hợp.

## 6. Trường `static` thuộc lớp nhưng không phải dữ liệu bền vững của AppCDS

Một nhầm lẫn thường gặp: “`static` là thuộc tính của lớp, AppCDS lưu dữ liệu lớp, vậy AppCDS phải lưu cả giá trị `static`”.

Không đúng với **trạng thái static mutable thông thường**.

~~~java
final class RequestMetrics {
    private static int processed = 0;

    static int record() {
        return ++processed;
    }
}
~~~

Trong **cùng một JVM**:

~~~java
System.out.println(RequestMetrics.record()); // 1
System.out.println(RequestMetrics.record()); // 2
~~~

Nếu JVM dừng và ứng dụng chạy lại mà không có cơ chế đọc dữ liệu từ kho lưu trữ, trường `processed` của tiến trình mới bắt đầu từ giá trị khởi tạo logic của chương trình. Lần `record()` đầu sẽ cho `1`, **không phải `3` nhờ archive**.

### `static final` có khác?

~~~java
static final String STATUS_NEW = "NEW";
static final java.util.Map<String, Order> ORDERS =
        new java.util.concurrent.ConcurrentHashMap<>();
~~~

`STATUS_NEW` là một hằng. JVM có thể tối ưu các biểu diễn hằng, và một số cơ chế AOT hiện đại có thể cache đối tượng đủ điều kiện. Nhưng:

- `final` ở `ORDERS` chỉ ngăn thay **tham chiếu trường**.
- `ORDERS.put(...)` vẫn cập nhật nội dung của map mutable.
- Các bản ghi thêm vào map ở runtime không tự được lưu thành **cơ sở dữ liệu đơn hàng** trong AppCDS.

**Lưu ý concurrency:** `static` cũng không tự đảm bảo thread safety bên trong cùng JVM. `processed++` có thể có race nếu nhiều thread cập nhật đồng thời. Dùng atomic/locking khi cần; AppCDS không thay thế Java Memory Model hay các primitive đồng bộ.

## 7. Những dữ liệu nào thực sự cần database hoặc state store?

| Nhu cầu | AppCDS | Cách thiết kế đúng |
| --- | --- | --- |
| Nạp nhanh metadata lớp ứng dụng | Có thể hỗ trợ | AppCDS/AOT cache |
| Tái sử dụng dữ liệu lớp giữa nhiều JVM | Có thể hỗ trợ | CDS archive + cấu hình tương thích |
| Lưu đơn hàng đã thanh toán qua restart | Không tự làm | Database + transaction/persistence |
| Giữ session người dùng qua thay thế pod/JVM | Không | Session store hoặc kiến trúc token/session phù hợp |
| Đồng bộ cache nhiều service instance | Không | Distributed cache hoặc kho dữ liệu dùng chung |
| Khôi phục số dư tài khoản | Không | Hệ thống giao dịch/sổ cái có tính nhất quán |
| Đồng bộ hai writer cập nhật đơn hàng | Không | Transaction, khóa, optimistic versioning |
| Bảo vệ dữ liệu khi tiến trình bị kill | Không | Durable storage, recovery, idempotency |
| Cải thiện thời gian khởi động ứng dụng | Là mục tiêu của CDS/AOT | Đo và so sánh trên workload thật |

Ví dụ minh họa tầng nghiệp vụ:

~~~java
// Pseudocode: repository và orderId là thành phần ứng dụng.
Order order = repository.findById(orderId);
order.markPaid();
repository.save(order);
~~~

`repository.save(order)` ở đây **không phải API tiêu chuẩn có sẵn**: ứng dụng cần một triển khai thực sự, có cơ chế commit và xử lý lỗi. AppCDS không thay nó, dù lớp `Order` hoặc `Repository` được lấy từ archive.

**Quy tắc kiến trúc:** AppCDS giải quyết **chi phí chuẩn bị code/class ở runtime**; persistence giải quyết **vòng đời dữ liệu**.

## 8. Cơ chế AppCDS ở mức khái niệm

Một quy trình tiêu biểu:

1. **Chạy ứng dụng đại diện:** JVM nạp những lớp thực sự được sử dụng trong giai đoạn quan sát/training.
2. **Chuẩn bị archive:** các thông tin lớp đủ điều kiện được lưu vào `.jsa` hoặc các artifact AOT tương ứng.
3. **Khởi chạy JVM mới:** nếu tương thích, JVM dùng dữ liệu đã được chuẩn bị để tránh lặp một phần các bước nạp/xử lý lớp.
4. **Thực thi ứng dụng bình thường:** `main` và nghiệp vụ làm việc với những đối tượng và dữ liệu của phiên chạy mới.
5. **Ứng dụng tự khôi phục state nếu cần:** truy vấn database, load cấu hình, dựng cache, khởi tạo session... theo code của chính nó.

Archive **không phải một ảnh chụp toàn bộ heap** ở điểm kết thúc training run. Việc training run đã chuyển một đơn hàng thành `PAID` không khiến mỗi phiên chạy tiếp theo tự nhìn thấy đơn hàng đó trong heap.

### Vì sao startup có thể nhanh hơn?

Lớp ứng dụng thường có nhiều thông tin bytecode/cấu trúc cần JVM chuẩn bị. Với archive hợp lệ, HotSpot có thể nạp một phần dữ liệu dạng đã xử lý, giảm việc lặp công việc và giảm phần metadata trùng lặp. Những trang dữ liệu chỉ đọc phù hợp còn có thể được hệ điều hành **chia sẻ vật lý** giữa các JVM.

Tuy nhiên, JVM vẫn cần thực hiện những công việc runtime khác như cấp phát heap nghiệp vụ, khởi động thread, cấu hình service hoặc kết nối database. Hiệu quả phụ thuộc application, JDK và trạng thái cache hệ điều hành.

## 9. Chương trình Java runnable: cùng lớp, trạng thái mới ở mỗi JVM

Lưu tệp **`AppCdsBoundaryDemo.java`**:

~~~java
public final class AppCdsBoundaryDemo {

    // Biến static mutable của JVM đang chạy.
    private static int processRequestCount = 0;

    static final class Order {
        private String status;

        Order(String status) {
            this.status = status;
        }

        String status() {
            return status;
        }

        void markPaid() {
            status = "PAID";
        }
    }

    public static void main(String[] args) {
        // Thông tin lớp; không phải trạng thái đơn hàng.
        System.out.println("class="
                + Order.class.getSimpleName());

        // Trạng thái process hiện tại.
        System.out.println("requestCount="
                + ++processRequestCount);

        // Instance nghiệp vụ mới.
        Order order = new Order("NEW");

        System.out.println("orderBefore="
                + order.status());

        order.markPaid();

        System.out.println("orderAfter="
                + order.status());

        // Hai cách xác định cùng kiểu trong JVM này.
        System.out.println("orderClassSame="
                + (order.getClass() == Order.class));
    }
}
~~~

Biên dịch và chạy bằng **JDK 17+**:

~~~bash
javac AppCdsBoundaryDemo.java
java AppCdsBoundaryDemo
~~~

**`stdout` của chương trình:**

~~~text
class=Order
requestCount=1
orderBefore=NEW
orderAfter=PAID
orderClassSame=true
~~~

Nếu gọi lệnh `java AppCdsBoundaryDemo` **lần thứ hai**, output vẫn là năm dòng như trên. Đó là một **JVM mới**: `processRequestCount` không tiếp tục từ 1 sang 2 và `Order` mới bắt đầu ở `NEW`.

### Vì sao kết quả `orderClassSame=true`?

`order.getClass() == Order.class` đúng trong cùng JVM vì hai biểu thức chỉ cùng một định nghĩa lớp. Kết quả này **không** nói rằng hai JVM có cùng object, hoặc chứng minh lớp `Order` đã được lấy từ archive. Phải xem log class loading khi muốn kiểm tra archive.

### Có phải thứ tự tạo object quan trọng?

Trong `main`, lệnh `new Order("NEW")` chạy **mỗi lần**. Phương thức `markPaid()` chỉ cập nhật object vừa tạo. Thông tin metadata của `Order` có thể tái sử dụng từ archive, nhưng thao tác khởi tạo instance vẫn mang ngữ nghĩa Java thông thường.

## 10. Tạo archive `.jsa` bằng những tùy chọn còn hỗ trợ

**Dynamic CDS archive** là cách thuận tiện trên JDK hiện hành. Các lệnh ở đây nhằm minh họa với **JDK 17+**; không khẳng định mọi bước dynamic archive có sẵn theo cùng cách ở bản Java 10 đầu tiên.

### Bước A: đóng gói các class vào JAR

Từ thư mục có source:

~~~bash
javac AppCdsBoundaryDemo.java
jar --create --file app.jar AppCdsBoundaryDemo.class 'AppCdsBoundaryDemo$Order.class'
~~~

Lớp lồng `Order` tạo file `AppCdsBoundaryDemo$Order.class`. Dấu nháy đơn ở lệnh trên phù hợp cho **bash, zsh và PowerShell**, tránh shell xử lý `$`. Với **Windows cmd.exe**, dùng dấu nháy kép:

~~~text
jar --create --file app.jar AppCdsBoundaryDemo.class "AppCdsBoundaryDemo$Order.class"
~~~

**Vì sao JAR?** Tài liệu launcher Java hiện hành đặt những yêu cầu nhất định cho classpath/module path của CDS; ví dụ các **thư mục không rỗng** trong classpath có thể làm một archive AppCDS không đủ điều kiện. Đóng gói thành JAR giúp ví dụ bám sát quy trình thực tế.

### Bước B: training run và tạo dynamic archive

~~~bash
java -XX:ArchiveClassesAtExit=app.jsa -cp app.jar AppCdsBoundaryDemo
~~~

Trong lần chạy này, JVM thực thi chương trình và tạo archive `app.jsa` khi thoát thành công, nếu cấu hình cho phép.

**`stdout` phần ứng dụng:**

~~~text
class=Order
requestCount=1
orderBefore=NEW
orderAfter=PAID
orderClassSame=true
~~~

Sau đó kiểm tra tệp `app.jsa` tồn tại. Tuy nhiên, **file tồn tại không tự chứng minh mọi lớp ứng dụng đều được lấy từ archive trong mỗi lần chạy về sau**.

### Bước C: JVM mới chạy với archive

~~~bash
java -XX:SharedArchiveFile=app.jsa -cp app.jar AppCdsBoundaryDemo
~~~

**`stdout` phần ứng dụng:**

~~~text
class=Order
requestCount=1
orderBefore=NEW
orderAfter=PAID
orderClassSame=true
~~~

Dù JVM có thể dùng lớp đã archive, **trạng thái runtime vẫn được khởi tạo theo code**. Mỗi lần chạy tạo `Order("NEW")`, rồi chuyển thành `PAID` trong chính tiến trình ấy.

### Bước D: tắt CDS để đối chiếu hành vi

~~~bash
java -Xshare:off -cp app.jar AppCdsBoundaryDemo
~~~

**`stdout` phần ứng dụng:**

~~~text
class=Order
requestCount=1
orderBefore=NEW
orderAfter=PAID
orderClassSame=true
~~~

**Kiểm chứng thực tế:** các bước trên đã chạy trên **JDK 24**; archive `app.jsa` được tạo, và cả ba cách chạy đều cho output chính xác như trên.

**Không suy từ cùng output rằng CDS vô dụng.** AppCDS tối ưu **thời gian nạp dữ liệu lớp và footprint**, không được thiết kế để thay đổi logic nghiệp vụ. Kiểm chứng hiệu năng và archive dùng những cách khác.

## 11. Xác minh archive bằng log JVM

Để biết JVM có thực sự sử dụng archive:

~~~bash
java -Xlog:cds=info -XX:SharedArchiveFile=app.jsa -cp app.jar AppCdsBoundaryDemo
~~~

Hoặc xem nguồn nạp từng lớp:

~~~bash
java -Xlog:class+load=info -XX:SharedArchiveFile=app.jsa -cp app.jar AppCdsBoundaryDemo
~~~

Một dòng dạng:

~~~text
[info][class,load] java.lang.Object source: shared objects file
~~~

cho thấy lớp đó được tải từ phần shared archive. Có thể xuất hiện dòng tương tự cho **lớp ứng dụng** đã được archive, phụ thuộc JDK và điều kiện chạy.

**Đó là dạng log minh họa**, không phải stdout cố định: thời điểm log, tên lớp, nguồn class và mức độ dùng archive có thể khác nhau. Nếu cần kiểm thử tự động, hãy lọc theo tên lớp và cụm `shared objects file` trong log thực tế, đồng thời chấp nhận các dòng chẩn đoán khác nhau ở mỗi JDK.

### Ba loại bằng chứng không giống nhau

| Kiểm tra | Chứng minh được gì? |
| --- | --- |
| File `app.jsa` được tạo | Một archive đã được tạo |
| Log ghi class source từ shared archive | Class data của lớp ấy được sử dụng từ archive |
| Output đơn hàng vẫn `NEW → PAID` | Trạng thái nghiệp vụ chạy theo code bình thường |
| Startup đo được nhanh hơn | Tối ưu đem lại lợi ích trên workload được đo |
| JVM B không thấy state của JVM A | Hai process không tự chia sẻ mutable business state nhờ CDS |

Đừng dùng `orderClassSame=true` hoặc việc một file `.jsa` tồn tại để thay cho kiểm tra log archive.

## 12. Sự thật về heap objects trong AOT hiện đại

Đây là phần quan trọng để tránh học kiến thức đã lỗi thời.

Tài liệu **Java SE 26** mô tả **AOT cache**, được đưa vào từ JDK 24, có thể chứa **Java classes và heap objects**. Một số cơ chế HotSpot trước đây cũng đã sử dụng dữ liệu heap được archive có chọn lọc.

Vì thế:

- **Đúng:** AppCDS cổ điển chủ yếu nhằm **chia sẻ siêu dữ liệu và cấu trúc liên quan lớp**.
- **Đúng:** các tối ưu AOT hiện hành có thể cache **những heap objects đủ điều kiện**, theo quy tắc của JVM.
- **Sai:** “Mọi object `new` của ứng dụng sẽ tự được lưu vào archive”.
- **Sai:** “Một phiên chạy của JVM có thể sửa trạng thái nghiệp vụ của JVM khác qua AppCDS”.
- **Sai:** “AOT cache đồng nghĩa snapshot database hoặc một serialization của toàn bộ heap”.
- **Quá tuyệt đối:** “HotSpot không bao giờ có bất kỳ archived heap object nào”.

Hãy xét mục đích: JVM có thể giữ dữ liệu bất biến/chọn lọc để giảm công việc startup; còn số dư, đơn hàng, session và giao dịch cần **vòng đời dữ liệu, quy tắc cập nhật, commit và phục hồi** do ứng dụng thiết kế.

**Nếu trong một bản HotSpot mới cơ chế AOT lưu được thêm loại object**, điều đó không mặc nhiên thay đổi hợp đồng nghiệp vụ. Ứng dụng vẫn không được dựa vào archive như nguồn sự thật cho dữ liệu mutable.

## 13. Bảo đảm đúng đắn, bảo mật và vòng đời archive

### Kiểm soát tương thích

Archive CDS/AOT gắn với môi trường tạo ra nó. Những thay đổi có thể khiến cache không được sử dụng:

- Bản JDK/runtime không tương thích.
- Classpath hoặc một JAR dùng lúc archive tạo đã thay đổi.
- Module path, JVM options hoặc các điều kiện nạp lớp khác không phù hợp.
- Nền tảng/kiến trúc khác đối với AOT cache mới.

Đối với CDS archive, **`-XX:SharedArchiveFile`** chỉ định tệp. Một tùy chọn có thể tạo archive động là **`-XX:ArchiveClassesAtExit`**. Với AOT cache JDK 24+, tài liệu launcher có các tùy chọn như **`-XX:AOTCache`** và **`-XX:AOTMode`**. Không trộn tùy tiện hai quy trình; chọn theo JDK, ứng dụng và hướng dẫn hiện hành.

### Chế độ `-Xshare`

| Tùy chọn | Mục đích |
| --- | --- |
| `-Xshare:auto` | Sử dụng shared archive khi có thể; cho phép fallback |
| `-Xshare:off` | Tắt CDS, hữu ích khi đo/điều tra |
| `-Xshare:on` | Bắt buộc phải dùng CDS; có thể lỗi khởi động nếu archive không dùng được |

Tài liệu Oracle nói **`-Xshare:on` dành cho kiểm thử**, không nên ép dùng bừa bãi trong production. Ứng dụng vẫn cần khởi động an toàn khi tối ưu hóa không khả dụng.

### Bảo vệ tệp archive

Tệp `.jsa`/AOT cache là **artifact thực thi liên quan JVM**, không nên để người không có quyền chỉnh sửa. Kiểm soát nguồn tạo, quyền ghi và quy trình deploy, nhất là khi nhiều tiến trình cùng dùng một archive.

**Không đưa dữ liệu cá nhân hoặc bí mật nghiệp vụ vào archive vì nhầm nó là nơi lưu cấu hình an toàn.** Một archive cũng không thay thế mã hóa dữ liệu hay quyền truy cập của database.

## 14. Performance: lợi ích và giới hạn

AppCDS có thể có lợi khi ứng dụng nạp nhiều lớp và nhiều JVM cùng dùng archive. Tuy nhiên, không hứa một con số tăng tốc cố định:

- Số lớp thực sự được archive có thể nhỏ hơn tổng số lớp trong ứng dụng.
- HotSpot vẫn cấp phát đối tượng, thực hiện GC, kết nối mạng/database, khởi tạo service.
- Một số trang nhớ của archive được map chia sẻ nhưng bộ nhớ heap của mỗi JVM vẫn riêng.
- Khi đo RSS của từng process, các trang map chung có thể khiến việc diễn giải tổng RAM khó hơn; trên hệ thống hỗ trợ, PSS hoặc phép đo tổng tiến trình có thể hữu ích hơn.
- Archive không tương thích có thể bị bỏ qua hoặc khiến ứng dụng fail theo chế độ cấu hình.

**Đề xuất quy trình đo đúng:**

1. Giữ nguyên JDK, máy, classpath, bộ tham số và workload.
2. So sánh lần khởi động có CDS phù hợp với cấu hình `-Xshare:off`.
3. Đo startup từ lúc launch đến **mốc sẵn sàng phục vụ request**, không chỉ thời gian load một class.
4. Xem log CDS/class loading để biết archive thật sự được dùng.
5. Đo footprint có tính đến shared pages và nhiều JVM.
6. Đưa kết quả thử nghiệm vào quyết định deploy; không giả định “bật CDS là mọi hiệu năng đều cải thiện”.

**Hai điều có thể cùng đúng:** AppCDS giúp startup nhanh hơn, **và** trạng thái đơn hàng vẫn được tạo lại từ `NEW`. Điều đầu là tối ưu JVM, điều sau là ngữ nghĩa nghiệp vụ.

## 15. Tình huống thiết kế ứng dụng

### A. Microservice đơn hàng chạy nhiều replica

Các replica cùng chạy một bản JAR có thể dùng archive CDS/AOT tương thích để giảm chi phí class loading. Nhưng `Order` instance, map cache, số lượng request của từng replica vẫn độc lập.

Muốn tất cả replica thấy trạng thái `PAID` của đơn hàng, phải ghi trạng thái vào **database dùng chung** và xác định cơ chế đọc nhất quán.

### B. Cache dữ liệu giá trong RAM

Một `ConcurrentHashMap<String, Price>` chứa dữ liệu sau khi truy vấn. Khi restart JVM, cache cần **được xây lại** hoặc có cơ chế persistence cache riêng. AppCDS không tự nhớ giá vừa truy cập.

Nếu hệ thống dùng distributed cache, dữ liệu có thể được chia sẻ vì **distributed cache**, không phải vì archive lớp.

### C. Bộ đếm request

`static int requestCount` chỉ biểu diễn một biến runtime trong tiến trình. Muốn đếm toàn bộ request trên nhiều replica, hãy dùng monitoring/metrics service, storage hoặc một giao thức tổng hợp.

Ngay trong một JVM, nếu nhiều thread cùng tăng biến, dùng primitive thread-safe như `AtomicLong` hoặc các công cụ metrics phù hợp. CDS không giải quyết race.

### D. Khôi phục session

Phiên đăng nhập cần thiết kế token/session lifecycle, timeouts, khóa và xác thực. Không được coi “cùng ứng dụng, cùng archive” là lý do người dùng đăng nhập ở replica A sẽ tự được nhận diện ở replica B.

### E. Khởi động Spring hoặc framework lớn

Framework có thể nạp rất nhiều lớp; tối ưu CDS/AOT có thể hữu ích. Tuy nhiên, dựng dependency injection graph, đọc secrets, kết nối DB, load config, tạo bean state và kiểm tra schema vẫn là **các bước runtime** với hợp đồng riêng. Một framework có thể cung cấp AOT processing của riêng nó, nhưng không tự thay thế persistence nghiệp vụ.

## 16. Những hiểu nhầm hay gặp

| Hiểu nhầm | Cách hiểu đúng |
| --- | --- |
| “Archive class nghĩa là archive tất cả instance.” | Siêu dữ liệu lớp và trạng thái từng object là hai thứ khác nhau. |
| “Static thuộc lớp nên được ghi lại qua restart.” | `static` mutable không tự thành dữ liệu bền vững. |
| “Hai JVM dùng `app.jsa` thì chung một `HashMap`.” | Heap riêng, không có shared mutable map do CDS tạo ra. |
| “`Order.class` là đơn hàng thực.” | Đó là biểu diễn kiểu; `new Order()` mới tạo instance. |
| “Training run đã trả tiền, lần sau đơn hàng phải ở `PAID`.” | Archive không ghi trạng thái giao dịch. |
| “Có archive file thì tất cả lớp chắc chắn lấy từ đó.” | Cần log và kiểm tra điều kiện tương thích. |
| “CDS thay thế database/serialization.” | CDS tối ưu class loading, không có giao dịch hay bền vững nghiệp vụ. |
| “CDS chia sẻ toàn bộ heap mutable giữa các JVM.” | Chia sẻ metadata/selected artifacts không đồng nghĩa chia sẻ trạng thái nghiệp vụ. |
| “CDS/AOT không bao giờ có heap object.” | AOT cache hiện đại có thể chứa heap object được chọn. |
| “`-Xshare:on` phù hợp mọi production.” | Tùy chọn này có thể làm JVM fail startup; Oracle khuyến cáo chỉ dùng kiểm thử. |
| “Output chạy với CDS phải khác output chạy không CDS.” | Đúng ngữ nghĩa nghiệp vụ phải giữ nguyên; hiệu năng có thể khác. |
| “Bật CDS tự sửa lỗi race.” | Đồng bộ giữa thread là bài toán riêng. |
| “Thay JDK/JAR không ảnh hưởng archive.” | Archive có ràng buộc tương thích, có thể phải tạo lại. |
| “CDS giúp mọi chương trình nhanh gấp hai.” | Lợi ích tùy ứng dụng, JDK và môi trường; phải đo. |

## 17. Tự kiểm tra kiến thức

**Câu 1.** Lớp `Product` có trường `int stock`. Metadata nào có thể được chia sẻ?

**Đáp án:** Cấu trúc lớp `Product`, mô tả trường `stock`, phương thức/bytecode... là class-related data. Giá trị `stock=20` của một instance là dữ liệu runtime.

**Câu 2.** Training run tạo `Order("NEW")`, gọi `markPaid()` rồi sinh `app.jsa`. Lần sau tạo lại `new Order("NEW")`; giá trị trước `markPaid()` là gì?

**Đáp án:** `NEW`. Đối tượng mới nhận trạng thái theo constructor, không khôi phục đơn hàng mutable từ archive.

**Câu 3.** Một JVM tăng `static int count` lên 100 rồi dừng. JVM mới chạy cùng JAR và cùng archive có bắt đầu count=100 không?

**Đáp án:** Không tự động. Nếu code chỉ khởi tạo `count=0` và không nạp từ persistence, giá trị runtime mới bắt đầu ở 0.

**Câu 4.** Hai JVM chia sẻ AppCDS archive. JVM A sửa một `Map` trong heap. JVM B có tự thấy thay đổi không?

**Đáp án:** Không nhờ AppCDS. Phải dùng một cơ chế giao tiếp/khôi phục/chia sẻ dữ liệu ứng dụng.

**Câu 5.** Nếu archive chứa các class thì chắc chắn chứa không một heap object nào?

**Đáp án:** Không thể khẳng định tuyệt đối cho AOT/CDS hiện đại; JDK mới có selected archived heap objects. Nhưng archive **không** tự chứa toàn bộ trạng thái nghiệp vụ tùy ý.

**Câu 6.** Làm sao xác nhận một lớp được load từ archive?

**Đáp án:** Xem log `-Xlog:class+load=info` hoặc chẩn đoán CDS. Dòng `source: shared objects file` của lớp tương ứng là bằng chứng class data được tải từ archive.

**Câu 7.** AppCDS giải quyết mất đơn hàng khi JVM bị kill không?

**Đáp án:** Không. Cần persistence với xử lý transaction/commit, khôi phục và các biện pháp tính nhất quán.

**Câu 8.** Chạy với/không CDS có cùng `stdout` là lỗi thử nghiệm không?

**Đáp án:** Không. Đây là kỳ vọng đúng về logic nghiệp vụ; hiệu quả CDS cần đo startup/memory riêng.

**Câu 9.** Static mutable state trong một JVM có cần thread safety không?

**Đáp án:** Có nếu nhiều thread truy cập theo mô hình có khả năng xảy ra race. AppCDS không tự khóa hay đồng bộ biến.

**Câu 10.** Tệp `.jsa` có thể mang sang JDK bản khác rồi dùng vô điều kiện không?

**Đáp án:** Không. Tương thích archive phụ thuộc JDK/build và nhiều tùy chọn/classpath; phải kiểm chứng hoặc tạo lại theo hướng dẫn runtime đang triển khai.

## 18. Checklist thiết kế đúng

**Phần tối ưu JVM:**

- Xác định phiên bản JDK, lựa chọn CDS/AppCDS hoặc AOT cache hiện hành.
- Xây archive/cache với app/JDK/config tương thích.
- Xác minh class data được dùng từ archive khi khởi động.
- Đo startup và footprint trên workload thật.
- Cho phép fallback khi archive không dùng được, trừ các bài kiểm thử có chủ đích.

**Phần nghiệp vụ:**

- Xác định nguồn dữ liệu bền vững: database/event store/object storage phù hợp.
- Phân biệt trạng thái in-memory với dữ liệu đã commit.
- Lập cơ chế khôi phục khi khởi động lại JVM.
- Thiết kế giao tiếp giữa nhiều replica/process.
- Kiểm tra concurrent writes, transaction, idempotency, retry và bảo mật.
- Không đưa trạng thái giao dịch vào kỳ vọng của AppCDS.

## 19. Kết luận và nguồn chính thức

- **AppCDS từ Java 10 (JEP 310)** mở rộng tối ưu **Class Data Sharing** cho lớp của ứng dụng; mục tiêu là startup và class-data footprint.
- **Class metadata** mô tả kiểu, phương thức, trường, bytecode và các dữ liệu VM liên quan; nó khác với **trạng thái của từng instance**.
- `static` mutable **không tự thành dữ liệu bền vững qua restart**. Hai JVM dùng cùng archive **không tự chia sẻ mutable business state**.
- **Selected archived heap objects** tồn tại trong một số cơ chế AOT/CDS mới; điều đó **không biến archive thành database hay snapshot nghiệp vụ**.
- Demo tạo `app.jsa`, chạy với `-XX:SharedArchiveFile` và `-Xshare:off` đã xác nhận cùng behavior ứng dụng trên JDK 24.
- Khi cần khôi phục đơn hàng, giỏ hàng, session hoặc bộ đếm, phải có **persistence và đồng bộ ứng dụng riêng**.

**Tài liệu chính thức còn hiệu lực:**

1. [Oracle Java SE 26 — java launcher: Application Class Data Sharing](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html#application-class-data-sharing) — CDS archive, lệnh tạo/đọc, giới hạn classpath, log.
2. [Oracle Java SE 26 — java launcher: Ahead-of-Time Cache](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html#ahead-of-time-cache) — AOT cache từ JDK 24 và artifact chứa lớp/heap object được chọn.
3. [Oracle Java SE 25 — Class Data Sharing](https://docs.oracle.com/en/java/javase/25/vm/class-data-sharing.html) — chia sẻ metadata và memory mapping giữa JVM.
4. [OpenJDK JEP 310 — Application Class-Data Sharing](https://openjdk.org/jeps/310) — nguồn gốc AppCDS trong Java 10.
5. [OpenJDK JEP 483 — Ahead-of-Time Class Loading & Linking](https://openjdk.org/jeps/483) — AOT class loading/linking và JDK 24.
6. [dev.java — CDS and AppCDS](https://dev.java/learn/jvm/cps-appcds/) — hướng dẫn chính thức dành cho người học Java.
