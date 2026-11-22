# Tránh accessor có side effect hoặc quá đắt khi dùng record pattern trong Java 21

## 1. Vì sao accessor là một vấn đề hiệu năng?

Record pattern cho phép kiểm tra kiểu và lấy các component của record chỉ bằng một biểu thức:

```java
record Payment(String code, long amount) {}

if (value instanceof Payment(var code, var amount)) {
    System.out.println(code + ": " + amount);
}
```

Nhìn cú pháp, ta dễ tưởng `Payment(var code, var amount)` là thao tác bóc tách field hoàn toàn miễn phí. Thực tế, trong Java 21, **record pattern đọc các component bằng cách gọi những accessor tương ứng của record**. Một record thông thường có accessor được compiler tạo ra, trả lại field đơn giản. Nhưng Java cho phép tác giả record **khai báo accessor tường minh**, và phương thức đó có thể thực hiện công việc tùy ý: cập nhật counter, ghi log, cấp phát collection, tính lại số liệu, ném exception, thậm chí gọi dịch vụ bên ngoài.

Vì vậy có hai rủi ro độc lập:

- **Side effect:** việc “đọc” component làm thay đổi trạng thái hoặc hệ thống ngoài. Kết quả có thể khác nhau giữa các lần match và khó debug.
- **Chi phí quá đắt:** accessor tính toán, copy dữ liệu hoặc thực hiện I/O nặng. Một `switch` ngắn có thể che giấu nhiều việc đắt đỏ.

Một thiết kế bền vững là **giữ accessor thuần (pure), nhanh, ổn định và nhất quán với trạng thái component**. Việc tính toán nặng, lấy dữ liệu hoặc chuẩn hóa nên có bước và chính sách lỗi rõ ràng, thường tại constructor/factory hoặc application service, trước khi pattern matching trên snapshot.

Bài học nằm trong nhóm **Hiệu năng** nhưng cũng liên quan tính đúng đắn, semantics của record và cách tổ chức domain model. Không có một phép đo nào cho phép kết luận rằng mọi record pattern luôn chậm; điều quan trọng là **tránh đưa công việc bất ngờ vào lúc matching**.

**Phiên bản Java:** Record classes chuẩn từ Java 16 (JEP 395); record patterns (JEP 440) và pattern matching for `switch` (JEP 441) ổn định từ **Java 21**. Ví dụ đầy đủ ở mục 8 chạy bằng JDK 21+ mà không cần `--enable-preview`.

## 2. Record pattern thực hiện deconstruction bằng accessor

Một record đơn giản:

```java
record Location(String city) {}
record Shipment(String code, Location location) {}
```

Nếu dùng:

```java
case Shipment(var code, Location(var city))
        when city != null && !city.isBlank() ->
    "Đi " + code + " đến " + city;
```

trình thực thi cần:

1. Xác định giá trị selector có thể khớp `Shipment` không-null.
2. Trích xuất component `code` và `location` bằng accessor tương ứng để match record pattern.
3. Xác định `location` khớp một record `Location` không-null.
4. Trích xuất `city` bằng accessor `Location.city()`.
5. Chỉ **sau khi cấu trúc pattern khớp**, đánh giá guard `city != null && !city.isBlank()`.
6. Nếu guard true, thân case mới được chọn.

Đây là mô tả ngữ nghĩa; không nên suy diễn từ nó một số lần gọi cố định của mọi accessor cho tất cả các cách biên dịch, bố trí case hay các JDK. Trong code business, hãy thiết kế để kết quả không phụ thuộc vào số lần đọc component.

Theo **Java Language Specification 21, `14.30.2**, record pattern lấy từng component bằng lời gọi accessor. Đặc tả cũng quy định rõ: nếu accessor được gọi trong quá trình deconstruction ném exception, matching kết thúc đột ngột bằng **`MatchException`** và exception gốc nằm ở `cause`.

### So sánh type pattern và record pattern

```java
if (value instanceof Shipment shipment) {
    // Type pattern: ràng buộc cả object, chưa deconstruct component.
}

if (value instanceof Shipment(var code, var location)) {
    // Record pattern: cần lấy component qua accessor.
}
```

Nếu chỉ cần xác định một object thuộc loại `Shipment` rồi gọi handler, **type pattern** thường đủ. Nếu logic cần `code` hoặc `location`, record pattern giúp lấy chúng rõ ràng.

Dĩ nhiên, một type pattern không tự loại mọi chi phí: nếu handler ngay sau đó gọi một accessor đắt tiền, chi phí vẫn xảy ra. Hãy quyết định dựa trên **dữ liệu thực sự cần**, thay vì nghĩ rằng thay cú pháp sẽ tự động giải quyết hiệu năng.

## 3. Accessor tường minh có thể thay đổi trạng thái

Ví dụ chống chỉ định:

```java
record TrackedPrice(long cents) {
    private static int reads;

    public long cents() {
        reads++;                  // Side effect.
        return cents;             // Trả component đã lưu.
    }
}
```

Mỗi lần `cents()` được gọi, biến static `reads` thay đổi. Khi `TrackedPrice(var cents)` xuất hiện trong record pattern, quá trình deconstruction có thể làm thay đổi counter này.

**Tại sao đây là ý tưởng tồi cho domain model?**

- Đọc một giá trị không còn là thao tác không có tác dụng phụ.
- Counter không đo “số thanh toán xử lý”, chỉ đo số lần có lời gọi accessor; pattern có thể được thử ngay cả khi guard cuối cùng false.
- Với code đồng thời, tăng biến static không được đồng bộ có thể tạo data race và mất lượt đếm.
- Debugging với thêm log/breakpoint có thể làm lộ đường đi khác dự kiến.
- Code có thể lặp deconstruction hoặc thay đổi cấu trúc `case` mà không hề đổi ý nghĩa domain, nhưng counter quan sát được lại khác.

Nếu cần metrics nghiệp vụ, hãy đếm sau khi một **quyết định hoặc hành động** đã được chốt, thay vì đếm mỗi lần accessor được đọc.

### Accessor làm sai ý nghĩa value object

Một trường hợp còn nguy hiểm hơn:

```java
record UnstableScore(int score) {
    private static int sequence;

    public int score() {
        return score + sequence++;
    }
}
```

Mỗi lần đọc lại có thể trả một số khác. Mặc dù record lưu một component final `score`, các phương thức bên ngoài lại thấy trạng thái không ổn định. Điều này trái trực giác của value object và có thể khiến guard `when score >= threshold` cho kết quả khó tái hiện.

Đoạn này minh họa lỗi thiết kế, **không phải implementation nên dùng**. Không thể sửa bằng cách “đảm bảo compiler chỉ gọi getter một lần”; cách sửa là làm accessor trả đúng giá trị component và chuyển mọi stateful operation sang nơi có hợp đồng riêng.

### Side effect trong accessor không nhất thiết là bug cú pháp

Java cho phép khai báo phương thức accessor tường minh nếu tuân thủ các ràng buộc về chữ ký và quyền truy cập. Compiler không tự cấm side effect hay I/O trong thân accessor. Vì vậy đây là vấn đề cần giải quyết bằng **code review, thiết kế và test**, không thể trông chờ tất cả được phát hiện bởi lỗi biên dịch.

## 4. Accessor đắt: copy collection, tính toán và I/O

### 4.1. Copy lại list khi đọc

```java
record SlowCatalog(java.util.List<String> codes) {
    public java.util.List<String> codes() {
        return java.util.List.copyOf(codes);
    }
}
```

Ở đây `codes()` là một accessor component được khai báo tường minh. Nó chạy `List.copyOf` mỗi khi được gọi. Tùy implementation và đầu vào, `List.copyOf` có thể sao chép hoặc tái sử dụng một danh sách đã unmodifiable; **không được khẳng định chắc chắn mỗi lần gọi đều cấp phát một object mới**. Dù vậy, việc đưa một thao tác collection vào accessor khiến chi phí phụ thuộc trạng thái và cách biểu diễn list, khó đoán hơn accessor trả field trực tiếp.

Nếu yêu cầu domain là **giữ một snapshot không cho sửa cấu trúc**, tốt hơn nên copy lúc tạo record:

```java
record SafeCatalog(java.util.List<String> codes) {
    SafeCatalog {
        codes = java.util.List.copyOf(
            java.util.Objects.requireNonNull(codes, "codes"));
    }
}
```

Ở `SafeCatalog`, accessor mặc định `codes()` chỉ trả list đã lưu; không cần copy lại để đọc. `List.copyOf` chặn phần tử null, tạo collection unmodifiable và giúp tránh bị ảnh hưởng khi caller thêm/xóa phần tử ở list nguồn.

**Giới hạn:** `List.copyOf` bảo vệ cấu trúc list, không biến đối tượng phần tử mutable thành immutable. Với `String`, phần tử đã immutable. Với một `List<MutableItem>`, muốn snapshot sâu cần thiết kế kiểu phần tử hoặc copy tương ứng.

### 4.2. Tính toán lại mỗi lần

```java
record Matrix(java.util.List<java.util.List<Integer>> rows) {
    public java.util.List<java.util.List<Integer>> rows() {
        // Không nên làm deep copy rất lớn ở mọi lần đọc component
        // nếu một snapshot bảo vệ từ lúc tạo là điều domain cần.
        return rows.stream()
            .map(java.util.List::copyOf)
            .toList();
    }
}
```

Mã này có thể làm việc đáng kể khi accessor được gọi. Nếu record pattern `Matrix(var rows)` nằm ở nhiều nhánh, logic khó thấy chi phí ngay tại chỗ. Hướng thay thế tùy domain: tạo deep snapshot ở factory/constructor, dùng immutable data structure, hoặc giữ việc tạo bản sao ở phương thức có tên riêng khi caller thật sự yêu cầu.

Phân biệt **accessor record component** và **derived method**:

```java
record Measurements(java.util.List<Integer> numbers) {
    long total() {
        return numbers.stream()
            .mapToLong(Integer::longValue)
            .sum();
    }
}
```

`total()` là phương thức nghiệp vụ bổ sung, **không phải accessor component** vì record chỉ khai báo `numbers`. Record pattern `Measurements(var nums)` không tự động gọi `total()`. Nhưng nếu guard viết `when m.total() > limit`, phép tính đó vẫn xảy ra mỗi khi guard được xét. Đó là một vấn đề chi phí riêng cần chú ý.

### 4.3. Accessor gọi mạng hoặc database

Đặt truy vấn bên trong accessor dẫn đến một ranh giới trách nhiệm nguy hiểm: một biểu thức phân nhánh có vẻ thuần lại có thể timeout, cần retry, tạo transaction hoặc ném exception hạ tầng.

Thay vì một record `Order` có accessor tự truy vấn database để lấy `riskScore`, nên **tách thành bước enrichment**:

```text
Raw request
    |
    v
Service/factory: lấy riskScore, xử lý timeout/lỗi
    |
    v
EvaluatedOrder(id, riskScore)  <- snapshot bất biến
    |
    v
switch / record pattern       <- chỉ phân loại
    |
    v
Decision                      <- kết quả nghiệp vụ
```

Không phải mọi dữ liệu đều cần precompute: nếu score cực kỳ tốn kém và chỉ một số đường đi dùng tới, có thể trì hoãn tính toán **ở tầng service có contract rõ**. Điểm chính là không giấu hoạt động ấy trong accessor của value object mà pattern matching có thể gọi.

## 5. Số lần gọi accessor không phải contract nghiệp vụ

Xét:

```java
return switch (value) {
    case Payment(var code, var amount) when amount >= 1_000L ->
        "Giá trị cao";
    case Payment(var code, var amount) ->
        "Giá trị thường";
    default -> "Không phải Payment";
};
```

Khi `Payment.amount` nhỏ hơn 1.000, case đầu có thể match cấu trúc nhưng guard false; case thứ hai mới được chọn. Các thao tác deconstruction gắn với việc xét pattern. Ta không nên cho rằng:

- Cả hai case luôn dùng **một** lần đọc accessor duy nhất.
- Mỗi case luôn buộc đọc mỗi component **đúng một lần** trong mọi cấu hình.
- Đếm getter call là cách đếm các case đã được chọn.
- Mã source ngắn thì số thao tác thực thi luôn ít.

Trình biên dịch/JVM có thể tối ưu những đường đi cụ thể; thiết kế đáng tin cậy không dựa vào chi tiết số lượt gọi. Nếu cần đo một triển khai cụ thể, dùng profiler/microbenchmark trong môi trường tương ứng, không khẳng định số lượt đọc cố định cho mọi JDK.

### Side effect trong guard làm vấn đề lớn hơn

```java
// Chống chỉ định nếu isEligible truy vấn service hoặc mutate state:
case Payment p when remoteService.isEligible(p) ->
    approve(p);
```

Đây là **đoạn minh họa trong một switch có service và handler được khai báo**, không phải code độc lập. Guard có thể được đánh giá rồi trả false; case không được chọn nhưng I/O đã xảy ra. Nếu guard ném exception, nó không được diễn giải thành false để chuyển case.

Ưu tiên:
- Guard ngắn, null-safe, thuần, dùng dữ liệu đã sẵn sàng.
- Policy đắt được đánh giá một lần ở bước có tên rõ.
- Một record snapshot lưu kết quả đã chốt, nếu việc giữ giá trị đó là hợp đồng đúng.
- Nếu score cần cập nhật thời gian thực, xác định freshness/consistency thay vì cache ngầm.

## 6. Exception do accessor gây ra: `MatchException`

Đây là ngữ nghĩa Java 21 đặc biệt quan trọng với debugging.

```java
record Fragile(int value) {
    public int value() {
        throw new IllegalStateException("unavailable");
    }
}
```

Khi Java đánh giá:

```java
Object input = new Fragile(5);

try {
    if (input instanceof Fragile(var n)) {
        System.out.println(n);
    }
} catch (MatchException ex) {
    System.out.println(ex.getCause().getClass().getSimpleName());
}
```

Lời gọi accessor `Fragile.value()` trong deconstruction ném `IllegalStateException`. Theo **JLS Java 21 `14.30.2**, quá trình pattern matching kết thúc bằng `MatchException` có cause là `IllegalStateException`. Đoạn trên in tên cause `IllegalStateException`.

**Đừng nhầm bốn kết quả sau:**

| Tình huống | Hành vi |
| --- | --- |
| Selector không có kiểu phù hợp | Pattern không khớp, có thể xét case sau |
| Nested record component là null | Nested record pattern không khớp, guard chưa chạy |
| Pattern khớp nhưng `when` trả false | Xét case tiếp theo |
| Accessor dùng trong deconstruction ném exception | Matching ném `MatchException`, không tự xem là pattern false |
| Guard hoặc body ném exception | Exception xảy ra ở guard/body, không phải quy tắc wrapper do accessor deconstruction |

Vì vậy, cố “dùng case dự phòng để bắt lỗi truy vấn” không phải cách xử lý một accessor ném lỗi trong lúc matching. Đặt truy vấn ở service/boundary, xử lý exception ở nơi hiểu chính sách lỗi rồi pattern match trên dữ liệu đã chuẩn bị.

Ngoài ra, nếu bạn gọi trực tiếp `fragile.value()` **ngoài** pattern matching, đó là lời gọi phương thức Java thông thường; không suy ra mọi exception như vậy đều trở thành `MatchException`.

## 7. Khi nào dùng type pattern thay vì nested record pattern?

Giả sử domain có:

```java
record Point(int x, int y) {}
record Route(String id, Point start, Point end) {}
```

Nếu mục tiêu chỉ là chuyển một Route cho handler:

```java
case Route route -> handleRoute(route);
```

thì type pattern đã đủ, không cần đọc tọa độ trong nhãn case. Tránh viết:

```java
case Route(var id, Point(var x1, var y1),
           Point(var x2, var y2)) ->
    handleRouteById(id);
```

nếu handler thực sự chỉ cần `id`. Pattern thứ hai buộc thêm các ràng buộc `start` và `end` phải khớp `Point` không-null; khi chúng null, case không match. Nó có thể làm sai hành vi **chứ không chỉ tăng chi phí**.

Một lựa chọn khác, nếu chỉ cần ID:

```java
case Route route -> handleRouteById(route.id());
```

Với implicit accessor đơn giản, việc đọc một component cần thiết trở nên rõ. Nhưng nếu accessor `id()` custom và đắt, vẫn cần sửa thiết kế nguồn dữ liệu. Đổi type pattern không phải phép tối ưu tự động.

**Quy tắc:** chỉ deconstruct những tầng và component thật sự cần để quyết định nhánh. Nếu nested record pattern đang bắt quá nhiều dữ liệu, đánh giá lại null semantics và ranh giới nghiệp vụ trước khi refactor.

## 8. Chương trình Java 21 hoàn chỉnh: phát hiện accessor call và dùng snapshot

Chương trình sau minh họa hai cách phân loại:

- `Tracked` có accessor `score()` cố ý tăng counter. Đây là **anti-pattern phục vụ demo**, không dành cho domain thật.
- `Snapshot` lưu dữ liệu có accessor mặc định.
- `classifyTracked` deconstruct trực tiếp `Tracked`.
- `prepare` đọc `Tracked.score()` **một lần rõ ràng trong mã nguồn**, tạo snapshot.
- `classifySnapshot` chạy nhiều lần trên snapshot mà không gọi lại accessor của `Tracked`.
- `Broken` minh họa exception trong accessor làm pattern matching ném `MatchException`.

Tạo tệp **`AccessorPatternCostDemo.java`**:

```java
import java.util.concurrent.atomic.AtomicInteger;

public class AccessorPatternCostDemo {

    private static final AtomicInteger READS = new AtomicInteger();

    record Tracked(String id, int score) {
        public int score() {
            READS.incrementAndGet();
            return score;
        }
    }

    record Snapshot(String id, int score) {}

    enum Branch { HIGH, NORMAL, OTHER, NULL_INPUT }

    record Decision(Branch branch, String detail) {}

    static Decision classifyTracked(Object input) {
        return switch (input) {
            case null ->
                new Decision(Branch.NULL_INPUT, "null");

            case Tracked(var id, var score) when score >= 10 ->
                new Decision(Branch.HIGH, id);

            case Tracked(var id, var score) ->
                new Decision(Branch.NORMAL, id);

            default ->
                new Decision(Branch.OTHER, "unsupported");
        };
    }

    // Chi phí đọc dữ liệu được đặt ở bước có tên rõ ràng.
    static Snapshot prepare(Tracked tracked) {
        return new Snapshot(tracked.id(), tracked.score());
    }

    static Decision classifySnapshot(Object input) {
        return switch (input) {
            case null ->
                new Decision(Branch.NULL_INPUT, "null");

            case Snapshot(var id, var score) when score >= 10 ->
                new Decision(Branch.HIGH, id);

            case Snapshot(var id, var score) ->
                new Decision(Branch.NORMAL, id);

            default ->
                new Decision(Branch.OTHER, "unsupported");
        };
    }

    record Broken(int value) {
        public int value() {
            throw new IllegalStateException("read failed");
        }
    }

    static int deconstructBroken(Object input) {
        if (input instanceof Broken(var n)) {
            return n;
        }
        return -1;
    }

    public static void main(String[] args) {
        Tracked tracked = new Tracked("R-1", 4);

        Decision direct = classifyTracked(tracked);
        System.out.println("direct=" + direct.branch());
        System.out.println(
            "accessorObserved=" + (READS.get() > 0));

        int before = READS.get();
        Snapshot snapshot = prepare(tracked);
        int after = READS.get();

        System.out.println("prepareReads=" + (after - before));

        Decision first = classifySnapshot(snapshot);
        Decision second = classifySnapshot(snapshot);
        System.out.println("snapshot1=" + first.branch());
        System.out.println("snapshot2=" + second.branch());
        System.out.println(
            "additionalTrackedReads=" + (READS.get() - after));

        System.out.println(
            "high=" +
            classifySnapshot(new Snapshot("R-2", 15)).branch());
        System.out.println(
            "other=" + classifySnapshot("not a snapshot").branch());
        System.out.println(
            "null=" + classifySnapshot(null).branch());

        try {
            System.out.println(
                "broken=" + deconstructBroken(new Broken(9)));
        } catch (MatchException ex) {
            System.out.println(
                "cause=" +
                ex.getCause().getClass().getSimpleName());
        }
    }
}
```

Biên dịch và chạy bằng JDK 21 hoặc mới hơn:

```bash
javac --release 21 -encoding UTF-8 AccessorPatternCostDemo.java
java AccessorPatternCostDemo
```

**Đầu ra dự kiến:**

```text
direct=NORMAL
accessorObserved=true
prepareReads=1
snapshot1=NORMAL
snapshot2=NORMAL
additionalTrackedReads=0
high=HIGH
other=OTHER
null=NULL_INPUT
cause=IllegalStateException
```

### Phân tích output

**`direct=NORMAL`:** `Tracked` có `score == 4`, không đạt guard `score >= 10` của case đầu, nên nhánh còn lại nhận nó. Hàm trực tiếp dùng record pattern, nên có thể gọi accessor có side effect.

**`accessorObserved=true`:** chương trình chỉ khẳng định accessor được gọi ít nhất một lần, **không cố ấn định con số** cho chuỗi các case hoặc mọi JDK. Đây là mức chứng minh đủ để thấy deconstruction truy cập accessor.

**`prepareReads=1`:** `prepare` gọi tường minh `tracked.score()` đúng một lần giữa hai lần lấy counter. Đây là tính chất của đoạn mã, không phải số lượt deconstruction mà compiler tạo ra.

**`snapshot1=NORMAL`, `snapshot2=NORMAL`:** cùng snapshot bất biến chứa score 4 được phân loại hai lần. Cả hai lần đọc dùng accessor `Snapshot` bình thường, không truy cập thêm `Tracked.score()`.

**`additionalTrackedReads=0`:** counter của accessor nguồn không tăng trong hai lần phân loại snapshot. Điều đó **không** chứng minh phân loại không có chi phí; nó chỉ chứng minh không cần làm lại một phép đọc thuộc nguồn cũ.

**`high=HIGH`, `other=OTHER`, `null=NULL_INPUT`:** các nhánh hỗ trợ score cao, kiểu đầu vào khác và selector null. `case null` là chính sách tường minh, không dựa vào `default` để nhận null.

**`cause=IllegalStateException`:** accessor của `Broken` ném exception khi deconstruct; `MatchException` được bắt và in loại cause, không ném tiếp tới các case dự phòng.

Đây là **demo hành vi**, không phải kết quả benchmark về tốc độ tuyệt đối. Bộ counter cố ý tạo side effect để thấy vấn đề; code production nên loại bỏ kiểu accessor đó.

## 9. Thiết kế boundary cho dữ liệu đắt hoặc không ổn định

Một cách tổ chức ứng dụng thường rõ ràng hơn là:

```text
Input / request
      |
      v
Fetch / calculate / normalize
      |  (lỗi, timeout, retry ở service)
      v
Validated snapshot record
      |  (accessor thuần, trạng thái nhất quán)
      v
Pattern matching / switch
      |
      v
Decision with branch ID
      |
      v
Log / metrics / persistence / response
```

**Phân định trách nhiệm:**

- **Service:** gọi API/DB, tính risk score, kiểm soát timeout/circuit breaker.
- **Factory/constructor:** validation, normalize, defensive copy, từ chối dữ liệu sai.
- **Snapshot record:** chứa dữ liệu đã xác định, accessor đơn giản.
- **Switch:** chọn case, so điều kiện thuần, trả kết quả.
- **Observability layer:** ghi case ID và trạng thái thành công, không dựa vào getter call count.

Có những hệ thống cần dữ liệu gần real-time. Khi đó cache/snapshot phải có **thời điểm tạo, version hoặc chính sách stale** đúng domain. Một snapshot đã chuẩn bị có thể rẻ để phân loại nhiều lần, nhưng không được tự suy diễn rằng nó luôn cập nhật nhất.

### Ví dụ service đánh giá trước khi match

```java
record EvaluatedOrder(String id, int score, boolean approved) {}

// Phác họa ở application service, helper đã có:
// int score = riskService.calculate(rawOrder);
// boolean approved = policyService.approve(rawOrder, score);
// EvaluatedOrder evaluated = new EvaluatedOrder(id, score, approved);

// Nhãn case trong switch nhận EvaluatedOrder hoặc Object:
case EvaluatedOrder(var id, var score, var approved)
        when approved && score >= 10 ->
    accept(id);
case EvaluatedOrder(var id, var score, var approved) ->
    reject(id);
```

Đây là **đoạn minh họa**, không phải chương trình chạy riêng. Guard chỉ đọc hai giá trị sẵn có. Không viết `case EvaluatedOrder(var id, var score, true)` và cho rằng literal `true` là component pattern chuẩn của Java 21: cú pháp đó không hợp lệ. Hãy dùng `var approved` và `when approved` như ví dụ trên.

Việc tính score và policy là bước riêng, do vậy những thao tác đắt không bị giấu trong accessor hoặc guard.

## 10. Đọc một lần có luôn tốt hơn không?

Không phải luôn luôn.

Nếu một giá trị thường không được sử dụng, việc **precompute sớm** có thể lãng phí. Nếu dữ liệu có thể đổi, một bản sao cũ có thể sai. Nếu domain yêu cầu mỗi thao tác quyết định dựa trên snapshot nhất quán, việc tính lại từng nơi cũng có thể sai.

Thay vì “cache mọi thứ”, hãy xét:

1. **Tần suất sử dụng:** component có nằm trên hot path hay chỉ một nhánh hiếm khi chạy?
2. **Chi phí thực:** accessor implicit trả field, phép tính CPU, copy collection hay I/O?
3. **Tính ổn định:** dữ liệu thay đổi qua thời gian/thread không?
4. **Consistency:** quyết định phải dùng một ảnh chụp tại thời điểm nào?
5. **Chi phí lưu/copy:** snapshot có quá lớn không?
6. **Thời gian sống:** data có được tái sử dụng cho nhiều lần phân loại không?
7. **Chính sách lỗi:** nếu load/calculation thất bại, caller cần biết như thế nào?

Một lời gọi accessor đơn giản đôi khi rẻ hơn việc tạo đối tượng trung gian. Một hàm tổng hợp trên collection lớn có thể cần precompute; còn một thuộc tính primitive đơn giản hiếm khi đáng tối ưu riêng. **Đo và xác nhận trước khi khẳng định hơn/kém hiệu năng.**

## 11. Benchmark và profiler

Đánh giá hiệu năng đúng cách không dùng thời gian in console trong accessor, vì chi phí I/O và môi trường console dễ lấn át mọi chi phí record pattern.

Một kế hoạch benchmark hợp lý:

- Dùng **JMH** nếu cần microbenchmark Java; có warmup và measurement tách biệt.
- Thử đủ đầu vào cho guard true/false, nested pattern match/fail và case khác.
- Tiêu thụ kết quả để tránh compiler loại bỏ work không được quan sát.
- Đo allocation/GC và CPU, không chỉ wall-clock.
- Nếu accessor gọi I/O, đo ở cấp integration/application và thống kê latency/timeout, không nhầm thành microbenchmark thuần CPU.
- Giữ JDK, hardware, heap, dữ liệu và lượng tải rõ ràng khi so sánh.
- Quan sát profiler để xác định nơi thời gian thực sự tiêu tốn: getter custom, list copy, service, guard hoặc phần xử lý sau case.

**Không đưa ra con số “record pattern chậm hơn switch cũ X%”** nếu chưa có dữ liệu đo cùng workload. Bài này chỉ ra rủi ro thiết kế và phương pháp kiểm chứng.

## 12. Checklist code review

| Câu hỏi | Dấu hiệu rủi ro | Giải pháp |
| --- | --- | --- |
| Record có accessor custom không? | Accessor gọi I/O, mutate state, copy object | Giữ accessor thuần hoặc chuyển công việc ra bước rõ ràng |
| Có sử dụng record pattern để lấy quá nhiều component? | Nested pattern dài, biến không dùng | Chỉ deconstruct dữ liệu cần |
| Có nhiều case cùng loại với guard không? | Deconstruction có thể xảy ra khi xét nhiều case | Không phụ thuộc số lần call, đo khi cần |
| Guard có side effect không? | Gọi service, tăng counter, ghi metrics | Tiền xử lý policy; guard thuần |
| Exception từ accessor có thể xảy ra không? | Matching dừng đột ngột | Nắm `MatchException` và thiết kế lỗi boundary |
| Component có thể null không? | Nested pattern fail hoặc guard NPE | Định nghĩa null contract, kiểm tra đúng vị trí |
| Record có collection mutable không? | Caller sửa dữ liệu giữa các lần đọc | Copy lúc tạo, immutable elements và ownership |
| Phép tính có bị lặp không? | Cùng score được tính ở nhiều nhánh | Local variable hoặc snapshot theo consistency |
| Có cache không hợp lý không? | Dữ liệu stale hoặc tốn bộ nhớ | Xác định lifecycle, TTL/version, invalidation |
| Có test trường hợp guard false không? | Case khác được chọn, accessor vẫn có thể đã chạy | Test case ID, output và exceptions |
| Có đo thực tế không? | Kết luận dựa vào độ dài code | Profiler/JMH, workload phù hợp |
| Metrics có đếm getter call không? | Business counters sai ngữ nghĩa | Ghi metric sau quyết định/hành động |

## 13. Lỗi phổ biến

**Lỗi 1 — tưởng accessor của record luôn là getter mặc định.** Java cho phép override. Hãy đọc khai báo record trước khi suy luận deconstruction rẻ.

**Lỗi 2 — coi accessor ném exception như pattern không khớp.** Trong record matching, exception từ accessor được gói thành `MatchException` có cause; không tự tới case fallback.

**Lỗi 3 — dùng getter call count làm metrics nghiệp vụ.** Guard false có thể vẫn liên quan các lời gọi component; đếm case được chọn bằng kết quả/chính sách rõ ràng.

**Lỗi 4 — logging trong getter làm thay đổi hiệu năng.** Log có I/O và side effect, nguy cơ ghi thông tin nhạy cảm. Dùng profiler, debug breakpoint hoặc log tại tầng quyết định.

**Lỗi 5 — copy list mỗi lần đọc trong khi domain cần immutable snapshot.** Thường nên copy/validate khi tạo record, sau đó dùng implicit accessor đơn giản.

**Lỗi 6 — thay record pattern bằng type pattern nhưng vẫn gọi getter đắt.** Cú pháp khác không sửa nguyên nhân. Cần thiết kế lại nguồn tính toán/accessor.

**Lỗi 7 — gọi API trong `when`.** Guard được xét trước khi case được chọn; có thể gây latency/exception ở chỗ khó dự đoán.

**Lỗi 8 — nghĩ final reference là deep immutability.** Component mutable có thể đổi; snapshot nhất quán cần ownership/copy và element types thích hợp.

**Lỗi 9 — tối ưu bằng cách precompute mọi trường.** Với dữ liệu hiếm khi dùng hoặc nhanh thay đổi, có thể lãng phí hoặc sai; cần phân tích frequency/cost/consistency.

## 14. Bài tập thực hành

**Bài 1.** Với `Tracked` trong chương trình, vì sao `accessorObserved` được in thành Boolean thay vì một số đếm cố định? Trả lời: demo không dựa vào số lượt deconstruction của các case để suy luận hành vi mọi JDK.

**Bài 2.** Viết `record Bad(int value)` có accessor `value()` ném `IllegalArgumentException`. Match bằng `instanceof Bad(var value)` trong Java 21. Loại exception phát sinh từ quá trình matching là gì? Đáp án: `MatchException` với cause là `IllegalArgumentException`.

**Bài 3.** Khi chỉ cần phân biệt `Shipment` với kiểu khác, hãy dùng type pattern thay cho `Shipment(var code, Location(var city))`. So sánh trường hợp `location == null` giữa hai pattern.

**Bài 4.** Với `SafeCatalog(List<String>)`, thêm phần tử vào list nguồn sau khi tạo; kiểm tra snapshot có đổi không. Vì sao `List.copyOf` không đủ nếu phần tử có setter?

**Bài 5.** Refactor một guard gọi `remotePolicyService.check(request)` thành bước service riêng, tạo `EvaluatedOrder` và guard thuần `when approved`. Nêu rõ nơi bắt timeout.

**Bài 6.** Tạo test cho `Tracked(score=9)`, `Tracked(score=10)` và selector null. Test branch, không chỉ so sánh số lần getter được gọi.

**Bài 7.** Thiết kế phương pháp đo allocation khi một accessor tạo list copy từ dữ liệu lớn. Cần warmup/JMH và test nhiều kích thước list. Giải thích vì sao in console trong accessor làm kết quả không đáng tin.

**Bài 8.** Nếu snapshot lưu `riskScore` nhưng dữ liệu phải được làm mới sau 30 giây, bạn sẽ đặt timestamp/TTL/invalidation ở tầng nào? Vì sao không nên nhúng cơ chế remote refresh ngầm vào accessor record?

## 15. Tổng kết

**Record pattern có thể gọi accessor tùy biến của component, nên không phải mọi phép deconstruction đều rẻ và không có side effect.** Trong Java 21, accessor ném exception khi pattern matching làm phát sinh `MatchException` có cause gốc. Một accessor thay đổi state hoặc thực hiện công việc đắt có thể khiến guard, `switch` và debugging khó dự đoán.

Hướng thiết kế tốt là giữ getter thuần/nhanh/ổn định; bảo vệ dữ liệu trong constructor hoặc tạo snapshot qua service; chỉ deconstruct component cần thiết; giữ `when` thuần, null-safe; xử lý exception ở boundary; và đo đạc bằng profiler/JMH thay vì suy đoán. Khi tối ưu, luôn xác nhận **tính đúng đắn và chính sách nhất quán của dữ liệu** trước hiệu năng.

### Nguồn tham khảo chính thức

- [JLS Java 21 — `14.30.2 Pattern Matching](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30.2) — record pattern gọi accessor và quy tắc `MatchException`.
- [Oracle Java 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html).
- [Oracle Java 21 — Record Classes](https://docs.oracle.com/en/java/javase/21/language/records.html).
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440).
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441).
- [OpenJDK JMH](https://github.com/openjdk/jmh) — benchmark Java.
