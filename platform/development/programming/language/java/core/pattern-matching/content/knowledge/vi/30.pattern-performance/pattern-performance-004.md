# Tác động của nested deconstruction đến hiệu năng trong Java Pattern Matching

**Nested deconstruction** là cách dùng **record pattern lồng nhau** để kiểm tra và lấy dữ liệu từ nhiều tầng record trong một biểu thức, ví dụ `Shipment(var id, Customer(var name, Address(var city, Geo(var x, var y))), var units)`. Cú pháp này có thể giúp code diễn đạt **hình dạng dữ liệu cần khớp** rất ngắn gọn. Tuy nhiên, khi cần phân tích hiệu năng, không thể kết luận rằng “càng nhiều tầng pattern càng chậm”, hay “pattern matching luôn nhanh hơn truy cập accessor thủ công”, chỉ từ số dấu ngoặc và số dòng code.

Bài học thuộc **Java Core Pattern Matching → Hiệu năng**. Ta sẽ xem công việc runtime có thể phát sinh khi match record patterns lồng nhau, ảnh hưởng của **accessor calls**, **nhánh thất bại**, **guard**, **fallback pattern**, tối ưu hóa của JIT, và cách đo lường bằng benchmark có đối chứng.

**Phiên bản:** Record patterns (JEP 440) và pattern matching for `switch` (JEP 441) là tính năng chính thức từ **Java 21**. Các chương trình hoàn chỉnh bên dưới sử dụng Java 21+, không cần `--enable-preview`.

## 1. Nested deconstruction thực hiện những gì?

Xét mô hình dữ liệu:

~~~java
// Trích đoạn Java 21+, các record đặt trong phạm vi hợp lệ.
record Geo(int x, int y) {}
record Address(String city, Geo geo) {}
record Customer(String name, Address address) {}
record Shipment(String id, Customer customer, int units) {}
~~~

Một record pattern lồng nhau có thể viết:

~~~java
// Trích đoạn Java 21+, 'value' là Object.
String label = switch (value) {
    case Shipment(var id,
            Customer(var name,
                Address(var city, Geo(var x, var y))),
            var units) when units > 0 ->
            id + ": " + name + " / " + city + " / " + x + "," + y;
    case Shipment(var id, var customer, var units) ->
            "Incomplete " + id;
    case null -> "No shipment";
    default -> "Other";
};
~~~

Cách đọc:

1. Selector phải là `Shipment` khác `null`.
2. Component `customer` phải khớp record `Customer` khác `null`.
3. Component `address` phải khớp record `Address` khác `null`.
4. Component `geo` phải khớp record `Geo` khác `null`.
5. Các biến `id`, `name`, `city`, `x`, `y`, `units` được ràng buộc với component tương ứng.
6. Guard `units > 0` được xét **sau khi pattern của nhánh đã khớp**. Khi cả pattern và guard đúng, chọn nhánh đầu.
7. Nếu một component tham chiếu không khớp, hoặc guard sai, Java có thể xét nhánh `Shipment(var id, var customer, var units)` phía sau.

**Lưu ý về `null`:** Một component tham chiếu trong record có thể là `null`. `var customer` có thể ràng buộc giá trị `null`, nhưng nested record pattern `Customer(...)` không khớp `null`. Đây là một khác biệt **về hành vi**, không chỉ về hiệu năng.

### Những gì nested deconstruction *không* tự làm

- Cú pháp `var` không tạo bản sao của toàn bộ record.
- Pattern binding **không tự tạo các đối tượng `Customer`, `Address` hoặc `Geo` mới**. Nó đọc và kiểm tra những giá trị đã có; việc tạo đối tượng mới, nếu có, phải đến từ nơi khác (ví dụ accessor tùy biến hoặc chính code của bạn).
- Nested deconstruction không tự truy cập database, deserialize JSON hay gọi API. Nếu accessor hoặc lớp bao bên ngoài có cơ chế làm những việc ấy, đó là chi phí và side effect của **đường truy cập dữ liệu cụ thể**.
- Pattern matching không đồng nghĩa với gọi `equals()` để so sánh cấu trúc record. Đây là cơ chế **kiểm tra kiểu và match component patterns**, không phải đối chiếu hai record bằng `equals()`.

Do đó khi so sánh hiệu năng, cần tách rõ **chi phí có thể phát sinh khi lấy và kiểm tra component** với **chi phí khởi tạo record, tạo chuỗi kết quả, I/O hoặc logic nghiệp vụ**.

## 2. Các nguồn chi phí runtime có thể ảnh hưởng

| Nguồn chi phí | Vì sao xuất hiện | Điều cần lưu ý |
| --- | --- | --- |
| Kiểm tra kiểu và hình dạng | Mỗi tầng nested pattern cần khớp kiểu record phù hợp | JIT có thể đơn giản hóa một phần khi kiểu runtime rõ ràng |
| Đọc component accessor | Record patterns lấy giá trị component để match tiếp | Accessor mặc định thường đơn giản; accessor tự viết có thể làm nhiều việc hơn |
| Chuỗi kiểm tra `null` | Một component tham chiếu `null` làm nested pattern không khớp | Fail ở tầng nào ảnh hưởng số bước đã đi qua |
| Thử case tiếp theo | Nhánh đầu thất bại có thể khiến `switch` xét pattern dự phòng | Có thể làm lại phép kiểm tra/đọc component mà nhánh trước đã dùng |
| Guard `when` | Chỉ chạy khi record pattern trước guard đã khớp | Guard ở cuối pattern sâu có thể tính quá muộn đối với dữ liệu thường bị loại |
| Phân bố đầu vào | Tỉ lệ dữ liệu đầy đủ, thiếu component, kiểu khác hoặc bị guard loại | Ảnh hưởng branch prediction, code được tối ưu và đường đi hot |
| Custom accessor | Record có thể tự định nghĩa accessor thay vì chỉ trả field | Side effect/exception/chi phí accessor có thể chi phối toàn bộ đường match |
| Kết quả nhánh | Ghép chuỗi, tạo object, gọi service trong body | Có thể lớn hơn nhiều chi phí bản thân deconstruction |

Vì vậy “độ sâu bằng 3” không tương đương với một số nanosecond cố định. Thời gian thực tế phụ thuộc **dữ liệu, compiler/JVM, kiểu accessor, profile chạy và phần công việc nằm ngoài pattern**.

### Đừng đọc số tầng pattern như số object được cấp phát

Với ví dụ:

~~~java
case Shipment(var id,
        Customer(var name, Address(var city, Geo(var x, var y))),
        var units) -> ...
~~~

Các tên `id`, `name`, `city`, `x` và `y` là **pattern variables** chứa giá trị trích ra, không phải các bản clone của record. Nếu benchmark có tạo `new Shipment(new Customer(...))` trong mỗi lượt đo, kết quả có thể phản ánh **allocation của dữ liệu đầu vào**, chứ không phản ánh riêng chi phí deconstruction.

## 3. So sánh với truy cập accessor tường minh

Một cách viết khác là kiểm tra kiểu đầu tiên, sau đó đi qua từng accessor với những guard `null`:

~~~java
// Trích đoạn nằm trong phương thức trả String, 'value' là Object.
if (value == null) return "No shipment";
if (!(value instanceof Shipment shipment)) return "Other";

Customer customer = shipment.customer();
if (customer == null) return "Incomplete " + shipment.id();

Address address = customer.address();
if (address == null) return "Incomplete " + shipment.id();

Geo geo = address.geo();
if (geo == null || shipment.units() <= 0) {
    return "Incomplete " + shipment.id();
}

return "OK " + shipment.id() + ": " + customer.name()
        + " to " + address.city() + " (" + geo.x() + "," + geo.y()
        + ") x" + shipment.units();
~~~

So với nested record pattern:

- **Nested pattern:** cấu trúc cần khớp nằm ngay trong `case`. Có thể rất dễ đọc nếu miền dữ liệu đơn giản và chỉ quan tâm nhánh thành công.
- **Accessor tường minh:** các bước kiểm tra và thứ tự guard thể hiện rõ; có thể lưu từng giá trị vào local variable khi muốn dùng nhiều lần.
- **Cả hai:** có thể được JIT tối ưu; không nên tuyên bố bên nào nhanh hơn chỉ dựa vào cú pháp.
- **Quan trọng:** khi thay đổi code, phải giữ nguyên semantics của `null`, thứ tự kiểm tra, loại ngoại lệ và kết quả cho các trường hợp không khớp.

Việc truy cập component qua accessor là một phần của giao thức record. Nếu accessor mặc định chỉ trả field, JVM có cơ hội inline. Nếu accessor tự định nghĩa với side effect, tác dụng đó vẫn thuộc về chương trình; không được mặc định compiler loại bỏ nó.

## 4. Ví dụ đặc biệt: fallback có thể đọc accessor nhiều lần

Một record **có thể tự định nghĩa component accessor**. Khi đó, số lần gọi accessor trở thành hành vi có thể quan sát được. Hãy xem minh họa:

~~~java
record Geo(int x, int y) {}

record Tracked(Geo geo) {
    static int reads;

    public Geo geo() {
        reads++;       // Chỉ dùng để quan sát, không phải thiết kế production.
        return geo;
    }
}
~~~

Và phân nhánh:

~~~java
// Trích đoạn trong một lớp có Tracked và Geo như trên.
static String trace(Object value) {
    return switch (value) {
        case Tracked(Geo(var x, var y)) -> "Point " + x + "," + y;
        case Tracked(var geo) -> "Missing point";
        case null -> "Null";
        default -> "Other";
    };
}
~~~

Nếu `Tracked.geo()` trả một `Geo` hợp lệ, nhánh đầu khớp. Nếu nó trả `null`, nested `Geo(...)` không khớp; Java tiếp tục thử `case Tracked(var geo)`. **Việc thử case thứ hai có thể gọi lại accessor**.

Trong chương trình hoàn chỉnh ở phần 6, với môi trường được kiểm chứng (JDK 24), kết quả quan sát là:

- `Tracked(new Geo(1, 2))`: `reads = 1`.
- `Tracked(null)`: `reads = 2`, vì phép match nested đầu thất bại và case dự phòng đọc component lần nữa.

**Không suy rộng con số 1 và 2 cho mọi chương trình/JDK.** Chúng là kết quả của đúng cấu trúc code và accessor có side effect trong ví dụ. Compiler, JIT, cấu trúc các case và loại pattern ảnh hưởng cách code được thực thi; khi so sánh hiệu năng thực tế hãy đo code đang chạy.

### Vì sao custom accessor đáng chú ý?

- Có thể chứa tính toán, cấp phát hoặc thậm chí side effect.
- Có thể ném ngoại lệ; một accessor lỗi không tự động tương đương “pattern không khớp”.
- Việc đọc lặp có thể làm tăng chi phí hoặc làm kết quả phụ thuộc trạng thái bên ngoài.
- Code accessor thường nên **đơn giản và ổn định**; nếu có nghiệp vụ phức tạp, một phương thức được gọi chủ động ngoài pattern sẽ dễ hiểu hơn.

**Mẹo thiết kế:** Không nên đặt network call, ghi audit hay thay đổi domain state trong record accessor chỉ vì nó được gọi “giống getter”. Với nested matching, thời điểm và số lần đọc không phải chỗ phù hợp để mã hóa nghiệp vụ có side effect.

## 5. Tối ưu đường thất bại thường gặp trước khi deconstruct sâu

Giả sử số lượng `units <= 0` thường gặp và đã đủ để loại shipment, nhưng pattern đầu tiên lại kiểm tra sâu xuống tận `Geo` rồi mới đánh giá `when units > 0`. Có thể đặt một nhánh **kiểm tra giá trị đơn giản trước**:

~~~java
// Java 21+, trích đoạn trong một switch expression trên Object value.
String outcome = switch (value) {
    case Shipment(var id, var customer, var units) when units <= 0 ->
            "Invalid count " + id;

    case Shipment(var id,
            Customer(var name, Address(var city, Geo(var x, var y))),
            var units) ->
            "OK " + id + ": " + name + " / " + city + " / " + x + "," + y;

    case Shipment(var id, var customer, var units) ->
            "Incomplete " + id;

    case null -> "No shipment";
    default -> "Other";
};
~~~

Từ trên xuống:

1. Case đầu khớp `Shipment` nhưng chỉ trích các component trực tiếp, kiểm tra `units <= 0` rồi xử lý sớm.
2. Nếu số lượng dương, Java mới xét nhánh nested để kiểm tra đầy đủ `Customer → Address → Geo`.
3. Nếu dữ liệu lồng nhau không khớp, fallback `Shipment(...)` xử lý shipment không đầy đủ.

**Đây là thay đổi thứ tự công việc, không phải cam kết tốc độ.** Nếu số lượng hợp lệ gần như mọi lúc, case bổ sung có thể tạo thêm một kiểm tra; nếu phần lớn input bị loại sớm, nó có thể tránh deconstruction sâu. Chỉ benchmark với phân bố dữ liệu thực tế mới trả lời được.

**Cẩn thận semantics:** Mẫu trên trả `"Invalid count"` cho shipment vừa có `units <= 0` vừa thiếu `customer`, trong khi phiên bản `nested` ở ví dụ chính trả `"Incomplete"`. Đó là **thay đổi ưu tiên lỗi**. Khi tối ưu, hãy xác định rõ một đầu vào vi phạm nhiều điều kiện thì lỗi nào có quyền ưu tiên; test phải bao phủ trường hợp đó. Đừng hoán đổi các case chỉ vì có vẻ nhanh hơn mà đổi luôn contract nghiệp vụ.

### Bản prefilter nhỏ chạy độc lập

Tạo tệp `PrefilterDemo.java` khi muốn tự thử thứ tự case:

~~~java
public class PrefilterDemo {
    record Node(String code) {}
    record Box(String id, Node node, int count) {}

    static String classify(Object value) {
        return switch (value) {
            case Box(var id, var node, var count) when count <= 0 ->
                    "Invalid count " + id;
            case Box(var id, Node(var code), var count) ->
                    "OK " + id + ":" + code;
            case Box(var id, var node, var count) ->
                    "Missing node " + id;
            case null -> "Null";
            default -> "Other";
        };
    }

    public static void main(String[] args) {
        System.out.println(classify(new Box("A", new Node("N"), 0)));
        System.out.println(classify(new Box("B", new Node("N"), 2)));
        System.out.println(classify(new Box("C", null, 1)));
    }
}
~~~

Lệnh chạy:

~~~bash
javac --release 21 PrefilterDemo.java
java PrefilterDemo
~~~

Kết quả:

~~~text
Invalid count A
OK B:N
Missing node C
~~~

Nhánh guard đầu không **dominate** nhánh nested phía sau vì nó chỉ nhận phần input có `count <= 0`, không nhận tất cả `Box`. Tuy vậy, **case `Box` tổng quát không guard** được đặt cuối, sau những trường hợp cụ thể.

## 6. Chương trình Java 21+ hoàn chỉnh: so sánh kết quả và đếm accessor

Tạo tệp **`NestedDeconstructionPerformanceDemo.java`**:

~~~java
public class NestedDeconstructionPerformanceDemo {
    record Geo(int x, int y) {}
    record Address(String city, Geo geo) {}
    record Customer(String name, Address address) {}
    record Shipment(String id, Customer customer, int units) {}

    static String nested(Object value) {
        return switch (value) {
            case Shipment(var id, Customer(var name,
                    Address(var city, Geo(var x, var y))), var units)
                    when units > 0 ->
                    "OK " + id + ": " + name + " to " + city
                    + " (" + x + "," + y + ") x" + units;

            case Shipment(var id, var customer, var units) ->
                    "Incomplete " + id;

            case null -> "No shipment";
            default -> "Other";
        };
    }

    static String explicit(Object value) {
        if (value == null) return "No shipment";
        if (!(value instanceof Shipment shipment)) return "Other";

        Customer customer = shipment.customer();
        if (customer == null) return "Incomplete " + shipment.id();

        Address address = customer.address();
        if (address == null) return "Incomplete " + shipment.id();

        Geo geo = address.geo();
        if (geo == null || shipment.units() <= 0) {
            return "Incomplete " + shipment.id();
        }

        return "OK " + shipment.id() + ": " + customer.name()
                + " to " + address.city() + " (" + geo.x() + "," + geo.y()
                + ") x" + shipment.units();
    }

    record Tracked(Geo geo) {
        static int reads;

        public Geo geo() {
            reads++;
            return geo;
        }
    }

    static String trace(Object value) {
        return switch (value) {
            case Tracked(Geo(var x, var y)) -> "Point " + x + "," + y;
            case Tracked(var geo) -> "Missing point";
            case null -> "Null";
            default -> "Other";
        };
    }

    public static void main(String[] args) {
        Object[] samples = {
                new Shipment("S-1",
                        new Customer("Mai", new Address("Hue", new Geo(12, 34))), 3),
                new Shipment("S-2", new Customer("An", null), 2),
                new Shipment("S-3", null, 1),
                new Shipment("S-4",
                        new Customer("Bao", new Address("Da Nang", new Geo(5, 6))), 0),
                null,
                "text"
        };

        for (Object sample : samples) {
            String a = nested(sample);
            String b = explicit(sample);
            System.out.println(a + " | equal=" + a.equals(b));
        }

        Tracked.reads = 0;
        System.out.println(trace(new Tracked(new Geo(1, 2)))
                + " | reads=" + Tracked.reads);

        Tracked.reads = 0;
        System.out.println(trace(new Tracked(null))
                + " | reads=" + Tracked.reads);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 21 -encoding UTF-8 NestedDeconstructionPerformanceDemo.java
java NestedDeconstructionPerformanceDemo
~~~

Đầu ra đúng:

~~~text
OK S-1: Mai to Hue (12,34) x3 | equal=true
Incomplete S-2 | equal=true
Incomplete S-3 | equal=true
Incomplete S-4 | equal=true
No shipment | equal=true
Other | equal=true
Point 1,2 | reads=1
Missing point | reads=2
~~~

### Phân tích kết quả

- **`S-1`** có đầy đủ record lồng nhau, `units > 0`. Cả hai cách đều trả cùng chuỗi.
- **`S-2`** thiếu `Address`; nested pattern không khớp và chọn fallback. Bản accessor tường minh dừng sau kiểm tra `address == null`.
- **`S-3`** thiếu `Customer`; nested pattern thất bại sớm hơn.
- **`S-4`** có đầy đủ cấu trúc nhưng `units == 0`, guard của nested case sai; fallback trả `Incomplete`. Bản thủ công cũng từ chối cùng đầu vào.
- **`null`** và một chuỗi không phải `Shipment` được xử lý giống nhau ở hai hàm.
- **`Tracked(new Geo(1, 2))`** khớp pattern đầu nên accessor được đọc một lần trong demo.
- **`Tracked(null)`** không khớp nested `Geo(...)`; pattern tiếp theo đọc component lần nữa. Demo ghi nhận hai lần đọc.

**Bài test xác nhận tính tương đương trên 6 input mẫu và đếm accessor ở 2 input có instrument. Nó không phải benchmark tốc độ.** Hai hàm `nested`/`explicit` cùng tạo chuỗi kết quả, và `Tracked.reads` là một biến static có side effect, nên không thể dùng các dòng kết quả này để kết luận phương án nào nhanh hơn trong production.

## 7. Cách benchmark đúng: ưu tiên JMH, không đo bằng một vòng lặp ngắn

Để đo tác động của nested deconstruction, nên dùng **JMH (Java Microbenchmark Harness)** thay vì đo một lần với `System.nanoTime()` quanh vài lượt chạy. JVM có **warmup, tiered compilation, JIT inlining, escape analysis, dead-code elimination** và những đặc tính khiến microbenchmark thủ công dễ sai.

Quy trình đề xuất:

1. **Chọn đúng câu hỏi.** Muốn đo chi phí *match và trích component* hay đo toàn bộ hàm tạo chuỗi? Nếu chỉ muốn phần pattern, tránh đặt nối chuỗi hoặc tạo record mới trong đoạn `@Benchmark`.
2. **Chuẩn bị input ngoài đoạn đo.** Dùng `@State` và `@Setup` trong JMH để tạo trước các object. Các case nên có input cùng semantics.
3. **Tách các phân bố dữ liệu.** Đo riêng: nested match thành công; null ở `Customer`; null ở `Address`; null ở `Geo`; guard thất bại; selector sai kiểu. Có thể có thêm workload hỗn hợp theo tỉ lệ production.
4. **Dùng cùng công việc đầu ra.** Hai phương pháp phải trả cùng giá trị và cùng quy tắc xử lý. Có thể trả về một `int` nhỏ từ các component thay vì trả về `String` dài. JMH sẽ xử lý kết quả benchmark; hoặc dùng `Blackhole` để ngăn dead-code elimination.
5. **Dùng warmup, measurement iterations và forks.** Đo nhiều lần trong những JVM độc lập, quan sát phân phối thay vì chỉ một con số.
6. **Khóa các điều kiện so sánh.** Cùng JDK/vendor, JVM flags, máy, cấu hình, cùng dữ liệu và cùng chế độ chạy. Nếu dùng `--release 21` để compile trên JDK mới, lưu ý bytecode/nguồn tương thích Java 21 **không có nghĩa runtime đang chạy là JVM 21**.
7. **Đừng đưa counter có side effect vào chính benchmark tốc độ.** Counter có thể chặn những tối ưu vốn xảy ra với accessor thuần túy; ví dụ `Tracked` ở phần 6 dùng để quan sát **số lần gọi**, không phải đo chi phí tối ưu cuối cùng.
8. **Diễn giải kết quả theo use case.** Nếu nested pattern giúp code rõ hơn mà chênh lệch nằm trong nhiễu hoặc không ảnh hưởng profile hệ thống, giữ giải pháp dễ đọc. Chỉ đổi khi có dữ liệu chứng minh đường hot và lợi ích thực tế.

### Khung ý tưởng JMH

Đây là **khung minh họa, không phải tệp độc lập**: cần thêm dependency JMH, chuyển các lớp demo vào package phù hợp, khai báo benchmark state và dùng launcher/plugin JMH theo hướng dẫn của dự án.

~~~java
// Mẫu ý tưởng khi đã cấu hình JMH, input được tạo trong @Setup.
@Benchmark
public String nestedPattern() {
    return NestedDeconstructionPerformanceDemo.nested(input);
}

@Benchmark
public String explicitAccessors() {
    return NestedDeconstructionPerformanceDemo.explicit(input);
}
~~~

Nếu mục tiêu là benchmark thuần chi phí matching, nên tạo hai phiên bản **trả kết quả rẻ như một số nguyên**, không chỉ so sánh hai phương thức tạo chuỗi ở trên. Bản thân chuỗi kết quả và allocation của nó có thể lấn át chi phí pattern/accessor.

**Đơn vị đo cần ghi rõ:** ns/op, ops/s hoặc allocation bytes/op tùy chế độ. Cần công bố JDK, số iterations/forks, phân bố dữ liệu và độ biến thiên. Không đưa ra “nested pattern nhanh hơn N%” nếu không có phép đo cụ thể và tái lập được.

## 8. Chỉ số nào cần quan sát ngoài latency?

Khi hàm chạy thường xuyên, có thể quan sát thêm:

- **CPU profile:** thời gian nóng nằm ở matching, custom accessor, guard hay xử lý trong nhánh?
- **Allocation profile:** có object/string mới phát sinh trong body hoặc accessor không?
- **Branch distribution:** đa số dữ liệu khớp ngay, hay thường rơi vào fallback sau khi đi sâu?
- **Method inlining / compilation:** JIT có inline các accessor đơn giản không? Không nên diễn giải output JIT như bảo đảm giữa các JVM.
- **GC pressure:** allocation phát sinh từ việc tạo dữ liệu và kết quả là bao nhiêu?
- **Tail latency:** đường thất bại hiếm nhưng tốn chi phí có ảnh hưởng p95/p99 không?

Với hệ thống thực tế, thường nên **đo toàn bộ service** trước để biết chỗ nào cần tối ưu, rồi mới dùng JMH cô lập một đoạn matching. Một hàm deconstruction chiếm tỷ lệ CPU rất nhỏ không nên trở thành mục tiêu refactor chỉ để “ít accessor hơn”.

## 9. Lỗi thường gặp khi suy luận hiệu năng

| Ngộ nhận/lỗi | Vì sao sai hoặc thiếu | Cách làm đúng |
| --- | --- | --- |
| “Có 4 tầng deconstruction thì cấp phát 4 object” | Pattern binding không tự tạo bản sao record | Tách allocation đầu vào khỏi việc match |
| “Record pattern chắc chắn chậm hơn accessor thủ công” | JIT có thể inline và tối ưu cả hai | Benchmark trên JDK/workload thực tế |
| “Nested pattern chắc chắn nhanh hơn vì code ngắn” | Số dòng không phản ánh số lượt accessor/branch | Đo profile và hành vi case/fallback |
| “Guard sai nên không có chi phí” | Pattern phải khớp trước khi guard chạy | Xem guard ở tầng nào và phân bố input |
| “Fallback miễn phí” | Các case được thử sau có thể đọc lại component | Kiểm chứng bằng trace hoặc profiler |
| “Accessor luôn là field getter thuần túy” | Record có thể khai báo accessor tùy biến | Đọc implementation và tránh side effect |
| “Counter tăng 2 có nghĩa thời gian gấp đôi” | Counter không phản ánh toàn bộ pipeline/JIT/CPU | Phân biệt đếm lời gọi với đo tốc độ |
| “`System.nanoTime()` một lần là đủ” | JVM warmup/optimization và noise làm sai kết quả | Dùng JMH, nhiều forks/iterations |
| “Test 1 input đại diện cho production” | Nhánh lỗi, null và type khác có phân bố khác | Benchmark nhiều shape và tỉ lệ thật |
| “Refactor tối ưu mà không cần test semantics” | Đổi thứ tự guard/fallback có thể đổi thông báo lỗi | Test các trường hợp vi phạm nhiều rule |
| “`--release 21` cố định hiệu năng JVM 21” | Nó xác định target compile, không JVM runtime | Ghi rõ JVM dùng để chạy benchmark |

## 10. Khi nào nên giữ nested deconstruction và khi nào nên tách bước?

**Nên giữ nested record pattern** khi cấu trúc dữ liệu ổn định, mức lồng vừa phải, hành vi `null` rõ ràng, và pattern thể hiện tốt điều kiện “phải đúng hình dạng này mới xử lý”. Đặc biệt, với sealed hierarchy có vài biến thể, `switch` exhaustive thường giúp bảo trì hơn một chuỗi cast dài.

**Nên cân nhắc tách bước/accessor** khi:

- Có nhiều tầng lồng nhau và muốn báo lý do thất bại ở từng tầng.
- Cần dùng lại một component nhiều lần và tránh truy cập accessor tùy biến lặp.
- Một điều kiện rẻ có thể loại bỏ phần lớn input trước khi phân rã sâu.
- Điều kiện nghiệp vụ hoặc side effect quá phức tạp để nằm trong `when`/pattern.
- Benchmark/profiler cho thấy matcher là điểm nóng thực sự, và phiên bản tách bước có lợi đáng kể mà vẫn giữ semantics.

**Không nên tách chỉ vì tưởng rằng mọi accessor luôn đắt.** Với record chứa vài giá trị bất biến và accessor mặc định, code nested có thể rất gọn; JIT có nhiều cơ hội tối ưu. Tương tự, không nên giữ pattern quá sâu nếu người đọc khó hiểu dù benchmark chưa phát hiện vấn đề.

### Lựa chọn theo mục tiêu

| Mục tiêu ưu tiên | Hướng thiết kế nên thử |
| --- | --- |
| Diễn đạt hình dạng dữ liệu cần khớp | Nested record pattern rõ ràng |
| Báo lỗi chi tiết cho component thiếu | Accessor/guard từng bước, validation result |
| Bảo toàn kiểu cho tập biến thể đóng | Sealed types + exhaustive switch |
| Tránh truy cập lại custom accessor | Trích vào local variable và dùng lại rõ ràng |
| Đường hot có nhiều input fail sớm | Kiểm tra điều kiện rẻ trước, rồi benchmark |
| Hiểu chênh lệch runtime | JMH + profiler + correctness tests |
| Thực hiện I/O hoặc transaction | Service độc lập, không giấu trong record accessor/guard |

## 11. Bài tập tự luyện

### Bài 1 — Phân tích đường match

Cho:

~~~java
record Inner(String code) {}
record Outer(Inner inner) {}
~~~

Với `Object input`, xét:

~~~java
String label = switch (input) {
    case Outer(Inner(var code)) -> "Code: " + code;
    case Outer(var inner) -> "Missing inner";
    case null -> "Null";
    default -> "Other";
};
~~~

Nếu `input = new Outer(null)`, kết quả là gì? Có phải `var inner` sẽ tạo `Inner` mới không?

**Đáp án:** Nested `Inner(var code)` không khớp component `null`, nên chọn `case Outer(var inner)` và kết quả là `"Missing inner"`. `var inner` chỉ ràng buộc component đang có (là `null`), không tạo object `Inner`.

### Bài 2 — So sánh số lượt accessor

Với `Tracked` và `trace` ở phần 6, vì sao `new Tracked(null)` cho `reads=2` trong bản demo đã chạy?

**Đáp án:** Pattern đầu `Tracked(Geo(...))` cần gọi accessor để lấy `geo`, nhưng giá trị `null` không khớp `Geo(...)`; Java tiếp tục kiểm tra case dự phòng `Tracked(var geo)` và đọc lại accessor. Đây là hành vi quan sát được trong ví dụ, không phải phép đo nanosecond.

### Bài 3 — Tối ưu có thể làm đổi kết quả

Với `Shipment("S-4", Customer(...), 0)`, phiên bản `nested` gốc trả `"Incomplete S-4"`. Nếu đặt case `when units <= 0 -> "Invalid count"` lên trước, kết quả thay đổi không?

**Đáp án:** Có. Kết quả thành `"Invalid count S-4"`. Đây là **thay đổi hợp đồng kết quả**, không chỉ thay đổi tốc độ. Cần quyết định nghiệp vụ muốn thông báo nào và cập nhật test tương ứng.

### Bài 4 — Thiết kế một benchmark công bằng

Một người viết vòng lặp 1 triệu lần, mỗi lần tạo mới các record lồng nhau, nối chuỗi, gọi `nested` rồi dùng `System.nanoTime()`. Có thể kết luận pattern chậm vì mất nhiều thời gian không?

**Đáp án:** Không. Phép đo đang trộn thời gian **khởi tạo object, phân phối bộ nhớ, nối chuỗi và pattern matching**, ngoài ra còn chịu warmup/JIT và noise. Nên tách chuẩn bị input khỏi đo, bảo đảm hai hàm trả kết quả tương đương, dùng JMH nhiều forks/iterations và profiling khi cần.

### Bài 5 — Lựa chọn cách viết dễ bảo trì

Một API yêu cầu kiểm tra `Order`, `Customer`, `Address` và trả **mã lỗi riêng** cho từng component thiếu. Nên dùng một nested pattern thật sâu hay các bước guard?

**Đáp án:** Các bước truy cập/guard hoặc một validation result thường diễn đạt rõ các lý do lỗi hơn. Nested pattern phù hợp khi chỉ cần biết toàn bộ cấu trúc khớp hay không. Tối ưu theo độ rõ ràng trước, chỉ refactor vì hiệu năng sau khi có số đo.

## 12. Tổng kết và nguồn tham khảo

- Nested record pattern là **kiểm tra và trích dữ liệu nhiều tầng**; không tự clone hay cấp phát một record mới cho mỗi tầng.
- Chi phí thực tế liên quan đến **kiểm tra kiểu, accessor calls, guard, fallback, phân bố đầu vào** và phần code nằm trong nhánh.
- Khi nested pattern thất bại và `switch` thử case tiếp, **accessor có thể được gọi lại**; có thể instrument để kiểm tra hành vi nhưng không suy ra thời gian từ số lần gọi.
- **JIT có thể tối ưu accessor đơn giản và pattern checks**, nhưng không có quy tắc chung rằng nested hay explicit luôn nhanh hơn.
- Kiểm tra điều kiện rẻ trước khi deconstruct sâu **có thể** hữu ích, nhưng sắp xếp lại case có thể thay đổi semantics; phải có correctness tests.
- Benchmark với **JMH**, input được chuẩn bị trước, warmup/forks, nhiều data shapes, và đối chiếu hai cách xử lý thật sự tương đương. Sử dụng profiler để xác nhận hot path.
- Ưu tiên code dễ hiểu và đúng nghiệp vụ; chỉ đánh đổi độ rõ ràng để tối ưu nếu có bằng chứng hiệu năng trên workload thực tế.

**Tài liệu chính thức:** [JEP 440 — Record Patterns](https://openjdk.org/jeps/440); [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441); [Oracle Java 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html); [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html); [OpenJDK JMH](https://openjdk.org/projects/code-tools/jmh/).
