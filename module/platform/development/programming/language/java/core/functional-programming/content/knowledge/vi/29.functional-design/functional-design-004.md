# Truyền hành vi thay cho tạo nhiều lớp chỉ khác một thao tác trong Java

## 1. Vấn đề: cùng một quy trình, chỉ có một bước thay đổi

Trong lập trình hướng đối tượng, một cách phổ biến để thay đổi thuật toán là định nghĩa interface rồi viết nhiều lớp triển khai. Điều này hợp lý khi mỗi cách xử lý có trạng thái, cấu hình, vòng đời và nhiều trách nhiệm riêng. Nhưng nếu nhiều lớp **chỉ khác một phép tính hoặc một điều kiện rất ngắn**, số lượng lớp có thể tăng nhanh mà không mang lại nhiều ý nghĩa.

Ví dụ chức năng tính tổng thanh toán có các bước cố định:

1. Nhận đơn hàng.
2. Kiểm tra dữ liệu đầu vào.
3. Tính phí vận chuyển theo chính sách đang áp dụng.
4. Cộng giá hàng với phí.
5. Trả kết quả.

Trong năm bước đó, chỉ có **bước 3** thay đổi. Ta có thể tạo `FlatFeePolicy`, `PriorityFeePolicy`, `FreeFromThresholdPolicy`, `HolidayPolicy`..., nhưng nếu mỗi lớp chỉ có một phương thức một dòng, việc tạo một file cho từng biến thể có thể làm code dài, gây khó đọc và tăng chi phí bảo trì.

Giải pháp là **truyền hành vi như một giá trị**: phương thức xử lý phần chung nhận thêm một tham số mang hành vi của bước thay đổi. Trong Java, hành vi này thường được biểu diễn bằng **functional interface**, lambda hoặc method reference.

```text
Trước:   Lớp A xử lý quy trình + quy tắc 1
         Lớp B xử lý quy trình + quy tắc 2
         Lớp C xử lý quy trình + quy tắc 3

Sau:     Một quy trình chung
                  |
             tham số Policy
               /    |    \
          lambda A lambda B method reference C
```

**Mục tiêu không phải loại bỏ mọi lớp**. Mục tiêu là giữ quy trình chung ở một nơi, tách phần biến đổi thành một hợp đồng nhỏ và cho caller chọn hành vi phù hợp tại thời điểm gọi.

## 2. Từ Strategy Pattern đến truyền hàm

Ý tưởng này có quan hệ chặt chẽ với **Strategy Pattern**: đóng gói thuật toán thay thế được, rồi truyền thuật toán đó vào nơi sử dụng.

### Cách dùng lớp triển khai truyền thống

Giả sử ta định nghĩa:

```java
@FunctionalInterface
interface FeePolicy {
    int fee(Order order);
}
```

Đây là **đoạn trích định nghĩa kiểu**; cần có kiểu `Order` trong cùng bối cảnh. Có thể viết:

```java
final class FlatFee implements FeePolicy {
    @Override
    public int fee(Order order) {
        return 20;
    }
}

final class PriorityFee implements FeePolicy {
    @Override
    public int fee(Order order) {
        return order.priority() ? 50 : 20;
    }
}
```

Hai lớp có ý nghĩa khi ta muốn những chiến lược được đặt tên riêng, được đăng ký trong hệ thống dependency injection, có trạng thái hoặc nhiều cấu hình. Nhưng nếu chúng chỉ là hai phép tính nhỏ như trên, caller có thể cung cấp lambda mà **không bắt buộc phải tạo hai lớp riêng**.

### Thay bằng lambda

```java
FeePolicy flat = order -> 20;
FeePolicy priority = order -> order.priority() ? 50 : 20;
```

Hai dòng này minh họa trong phương thức có định nghĩa `FeePolicy` và `Order` tương ứng. Lambda triển khai phương thức trừu tượng duy nhất của functional interface: `fee(Order)`.

`FeePolicy` vẫn là một **kiểu giao diện** — chỉ thay đổi cách cung cấp đối tượng triển khai. Đừng hiểu “truyền hàm” là Java đã loại bỏ hệ thống kiểu hay cho phép truyền bất kỳ khối code nào mà không có target type.

## 3. Điều kiện để một hành vi được truyền dưới dạng lambda

Một functional interface có **đúng một phương thức trừu tượng** theo quy tắc Java (không tính các phương thức tương ứng public methods của `Object`); có thể có thêm `default` hoặc `static` methods.

Ví dụ:

```java
@FunctionalInterface
interface FeePolicy {
    int fee(Order order);
}
```

Annotation `@FunctionalInterface` không bắt buộc cho khả năng sử dụng lambda, nhưng giúp trình biên dịch kiểm tra ý định và báo lỗi nếu interface vô tình mất tính chất functional.

Khi viết:

```java
FeePolicy rule = order -> 20;
```

Java dùng kiểu đích `FeePolicy` để hiểu `order` có kiểu `Order` và phần thân trả `int`. Với method reference, trình biên dịch cũng cần kiểu đích:

```java
FeePolicy rule = BehaviorInjectionDemo::flatFee;
```

Đây là đoạn trích từ chương trình chạy đầy đủ ở mục 8, nơi `flatFee(Order)` là phương thức `static`.

Hãy chọn tên interface thể hiện **ý nghĩa miền nghiệp vụ** khi đáng giá: `FeePolicy`, `RetryDecision`, `EligibilityRule` rõ hơn `Function<Order,Integer>` trong một API có nhiều hành vi tương tự. Ngược lại, không cần định nghĩa interface mới khi `Predicate<T>`, `Function<T,R>` hoặc `Comparator<T>` đã mô tả đủ rõ.

## 4. Thiết kế hàm nhận hành vi: cố định khung, mở một điểm biến thiên

Ví dụ `QuoteService` nhận `FeePolicy` thay vì tự quyết định phí:

```java
static final class QuoteService {
    int total(Order order, FeePolicy policy) {
        Objects.requireNonNull(order);
        Objects.requireNonNull(policy);
        if (order.amount() < 0) {
            throw new IllegalArgumentException("amount");
        }
        int fee = policy.fee(order);
        if (fee < 0) {
            throw new IllegalArgumentException("fee");
        }
        return Math.addExact(order.amount(), fee);
    }
}
```

Đây là đoạn trích từ chương trình đầy đủ; cần import `java.util.Objects`, đồng thời khai báo `Order`, `FeePolicy`.

Phần chung được giữ nguyên:

- **Kiểm tra đầu vào** trước khi áp dụng chính sách.
- **Gọi đúng điểm biến thiên** qua `policy.fee(order)`.
- **Kiểm tra hợp đồng của kết quả hành vi** (phí không âm).
- **Cộng có kiểm tra tràn** bằng `Math.addExact` trong ví dụ dùng số nguyên nhỏ.

Bây giờ caller có thể đổi chính sách mà không sửa `QuoteService`:

```java
FeePolicy flat = order -> 20;
FeePolicy priority = order -> order.priority() ? 50 : 20;

int normal = service.total(order, flat);
int rush = service.total(order, priority);
```

Các lệnh trên **chỉ minh họa** với các biến `service`, `order` phù hợp. Mỗi lần gọi chọn một implementation của cùng giao diện.

Hành vi được truyền vào thường gọi là **behavioral parameterization** hoặc **strategy injection**. Đây là một ứng dụng của nguyên lý mở rộng chức năng bằng tham số, không sao chép phần điều phối chỉ vì một quy tắc thay đổi.

## 5. Đối chiếu “trước” và “sau” refactor

| Góc nhìn | Nhiều lớp cho biến thể nhỏ | Một hàm chung nhận hành vi |
| --- | --- | --- |
| Nơi chứa quy trình chung | Có nguy cơ lặp ở từng lớp hoặc nhiều subclass | Tập trung ở một service/hàm |
| Thêm chính sách mới | Có thể tạo class mới và cấu hình/wiring | Truyền lambda, reference, hoặc class khi thực sự cần |
| Kiểm thử quy trình chung | Dễ bị lặp test cho từng class | Dùng một fake/stub policy ở các test của service |
| Cách đọc tại nơi gọi | `new FlatFee()`, `new PriorityFee()` | `order -> ...`, method reference, policy được đặt tên |
| Trạng thái/cấu hình phức tạp | Class riêng thường rõ và dễ quản lý lifecycle | Lambda capture dễ trở nên khó hiểu nếu quá phức tạp |
| Mở rộng nhiều phương thức | Interface/class có thể phù hợp | Một lambda chỉ thể hiện một SAM |
| Thứ tự và side effects | Tùy implementation | Vẫn tùy implementation; lambda không tự làm hành vi thuần |

**Không loại bỏ một lớp chỉ vì nó ngắn** nếu tên lớp mang ý nghĩa miền nghiệp vụ quan trọng hoặc cần được cấu hình/quan sát độc lập. Refactor đáng giá khi nó giảm **biến thể lặp không cần thiết** và làm phần chung rõ hơn.

Một cách nhận diện “class explosion”: hàng loạt class cùng implement một interface, không có trường đáng kể, chỉ override một phương thức bằng vài dòng và được tạo tại chỗ để đưa vào một service. Khi đó hãy cân nhắc lambda, method reference hoặc các factory trả functional interface.

## 6. Java có sẵn các kiểu hành vi phổ biến

Trước khi tạo interface mới, xem `java.util.function` và `java.util.Comparator`:

| Giao diện | SAM | Ý nghĩa thường gặp | Ví dụ |
| --- | --- | --- | --- |
| `Predicate<T>` | `boolean test(T)` | Điều kiện/luật chọn | `order -> order.amount() > 0` |
| `Function<T,R>` | `R apply(T)` | Biến đổi dữ liệu | `Candidate::name` |
| `Consumer<T>` | `void accept(T)` | Hành động nhận dữ liệu | `log::add` |
| `Supplier<T>` | `T get()` | Cung cấp hoặc tạo giá trị khi được gọi | `() -> new ArrayList<>()` |
| `UnaryOperator<T>` | `T apply(T)` | Biến đổi cùng kiểu | `String::trim` |
| `BiFunction<T,U,R>` | `R apply(T,U)` | Hàm có hai đối số | `(a,b) -> a+b` |
| `Comparator<T>` | `int compare(T,T)` | Quy tắc so sánh/sắp xếp | `Comparator.comparing(Candidate::name)` |
| `Runnable` | `void run()` | Một hành động không có input/output | `() -> refresh()` |

Các ví dụ trong bảng là **biểu thức minh họa**; một số cần khai báo biến/kiểu tương ứng (`log`, `Candidate`, `refresh`). `Comparator` thuộc `java.util`; các interface khác chủ yếu thuộc `java.util.function`, còn `Runnable` thuộc `java.lang`.

Không nên dùng `Consumer<T>` chỉ vì phương thức ngắn nếu logic thực chất cần **trả về một giá trị**. Khi hợp đồng cần kết quả, dùng `Function<T,R>` hoặc interface có return type tương ứng. Khi chỉ cần kiểm tra điều kiện, `Predicate<T>` truyền đạt ý định chính xác hơn `Function<T,Boolean>`.

Trong đoạn xử lý tần suất cao với dữ liệu nguyên thủy, các interface chuyên dụng như `IntPredicate`, `IntUnaryOperator`, `ToIntFunction<T>` có thể tránh boxing; chỉ tối ưu sau khi hiểu ngữ nghĩa và đo đạc khi cần.

## 7. Điểm quan trọng: tham số hành vi là một phần hợp đồng API

Nếu phương thức nhận nhiều tham số là hành vi, mỗi tham số phải có **vai trò rõ ràng**:

```java
static List<String> select(
        List<Candidate> source,
        Predicate<? super Candidate> rule,
        Function<? super Candidate, String> format,
        Comparator<? super String> order) {
    return source.stream()
            .filter(rule)
            .map(format)
            .sorted(order)
            .toList();
}
```

Đây là **phương thức trong lớp** của chương trình đầy đủ ở mục 9, không phải tệp độc lập. Mỗi đối số có nhiệm vụ:

1. `source`: dữ liệu nguồn.
2. `rule`: quyết định phần tử nào được giữ.
3. `format`: chuyển phần tử sang chuỗi.
4. `order`: quy tắc so sánh chuỗi kết quả.

Kết quả là **một quy trình chung**, nhưng caller có thể thay cả điều kiện, cách biểu diễn và cách sắp xếp mà không tạo một lớp `ActiveCandidateSelector`, `ExcellentCandidateSelector`, `ReverseCandidateSelector` cho từng tổ hợp.

`? super Candidate` cho phép predicate/function có thể nhận `Candidate` hoặc kiểu cha phù hợp; `Comparator<? super String>` cho phép comparator nhận `String` hoặc kiểu cha phù hợp. Đây là khả năng linh hoạt generic của API Java, không phải phép ép kiểu không an toàn.

**Không truyền quá nhiều lambda khi chúng làm hàm khó đọc**: nếu có 7–10 chính sách khó phân biệt, nên gom chúng vào một configuration object có tên, một domain service rõ ràng hoặc một số policy type chuyên biệt. Parameterization chỉ có ích khi giao diện vẫn dễ hiểu.

## 8. Chương trình Java 17 độc lập: lớp Strategy và lambda cùng dùng một service

Tạo file `BehaviorInjectionDemo.java`:

```java
import java.util.List;
import java.util.Objects;

public class BehaviorInjectionDemo {
    record Order(String code, int amount, boolean priority) {}

    @FunctionalInterface
    interface FeePolicy {
        int fee(Order order);
    }

    static final class FlatFee implements FeePolicy {
        @Override
        public int fee(Order order) {
            return 20;
        }
    }

    static final class PriorityFee implements FeePolicy {
        @Override
        public int fee(Order order) {
            return order.priority() ? 50 : 20;
        }
    }

    static final class QuoteService {
        int total(Order order, FeePolicy policy) {
            Objects.requireNonNull(order);
            Objects.requireNonNull(policy);
            if (order.amount() < 0) throw new IllegalArgumentException("amount");
            int fee = policy.fee(order);
            if (fee < 0) throw new IllegalArgumentException("fee");
            return Math.addExact(order.amount(), fee);
        }
    }

    static int flatFee(Order order) {
        return 20;
    }

    static FeePolicy freeFrom(int threshold, FeePolicy original) {
        Objects.requireNonNull(original);
        return order -> order.amount() >= threshold ? 0 : original.fee(order);
    }

    public static void main(String[] args) {
        QuoteService service = new QuoteService();
        List<Order> orders = List.of(
                new Order("O-1", 80, false),
                new Order("O-2", 120, true));

        for (Order order : orders) {
            System.out.println(order.code() + "/classic-flat=" +
                    service.total(order, new FlatFee()));
            System.out.println(order.code() + "/classic-priority=" +
                    service.total(order, new PriorityFee()));
        }

        FeePolicy flat = BehaviorInjectionDemo::flatFee;
        FeePolicy priority = order -> order.priority() ? 50 : 20;
        FeePolicy freeShipping = freeFrom(100, flat);

        for (Order order : orders) {
            System.out.println(order.code() + "/reference=" + service.total(order, flat));
            System.out.println(order.code() + "/lambda=" + service.total(order, priority));
            System.out.println(order.code() + "/free-from-100=" +
                    service.total(order, freeShipping));
        }

        FeePolicy testPolicy = order -> 0;
        System.out.println("test=" + service.total(orders.get(0), testPolicy));

        try {
            service.total(orders.get(0), order -> -5);
        } catch (IllegalArgumentException ex) {
            System.out.println("invalid=" + ex.getMessage());
        }
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 -encoding UTF-8 BehaviorInjectionDemo.java
java BehaviorInjectionDemo
```

Đầu ra **đã kiểm thử thực tế với Java 17**:

```text
O-1/classic-flat=100
O-1/classic-priority=100
O-2/classic-flat=140
O-2/classic-priority=170
O-1/reference=100
O-1/lambda=100
O-1/free-from-100=100
O-2/reference=140
O-2/lambda=170
O-2/free-from-100=120
test=80
invalid=fee
```

### Cách đọc chương trình

- Record `Order(code, amount, priority)` dùng dữ liệu bất biến của ví dụ (một record có các thành phần đã khai báo).
- `FeePolicy` có một SAM, phù hợp lambda hoặc method reference.
- `FlatFee` và `PriorityFee` cho thấy **cách viết class Strategy truyền thống**. Chúng vẫn là implementation hợp lệ, chỉ không bắt buộc với quy tắc nhỏ.
- `QuoteService.total` không hề có `if (policyType == ...)` để chọn chính sách; caller truyền `FeePolicy` thích hợp.
- `BehaviorInjectionDemo::flatFee` minh họa method reference: một phương thức tĩnh sẵn có được dùng như đối tượng hành vi.
- `order -> order.priority() ? 50 : 20` minh họa lambda inline với logic ngắn.
- `freeFrom(100, flat)` **trả về một FeePolicy khác**: đơn từ 100 trở lên được miễn phí, còn lại ủy quyền cho chính sách gốc. Hành vi có thể được bao bọc/kết hợp.
- `testPolicy = order -> 0` cho phép kiểm thử logic `QuoteService` mà không phải dựng lớp `FreeFeeForTests`.
- `invalid=fee` chứng minh service vẫn **kiểm tra hợp đồng** của chính sách được truyền vào.

Ví dụ biểu diễn tiền bằng `int` để tập trung vào truyền hành vi, và dùng `Math.addExact` để phát hiện tràn. Với hệ thống tiền tệ thực, hãy chọn `BigDecimal` hoặc số nguyên biểu diễn đơn vị nhỏ nhất cùng quy tắc làm tròn và miền an toàn phù hợp.

## 9. Chương trình Java 17 độc lập: truyền nhiều hành vi cho một workflow

Tạo file `FunctionalWorkflowDemo.java`:

```java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.function.Consumer;
import java.util.function.Function;
import java.util.function.Predicate;

public class FunctionalWorkflowDemo {
    record Candidate(String name, int score, boolean active) {}

    static List<String> select(
            List<Candidate> source,
            Predicate<? super Candidate> rule,
            Function<? super Candidate, String> format,
            Comparator<? super String> order) {
        return source.stream()
                .filter(rule)
                .map(format)
                .sorted(order)
                .toList();
    }

    static void deliver(List<String> values, Consumer<? super String> sink) {
        values.forEach(sink);
    }

    public static void main(String[] args) {
        List<Candidate> data = List.of(
                new Candidate("An", 85, true),
                new Candidate("Binh", 72, false),
                new Candidate("Chi", 95, true),
                new Candidate("Dung", 82, true));

        Predicate<Candidate> eligible = c -> c.active() && c.score() >= 80;
        List<String> names = select(
                data, eligible, Candidate::name, Comparator.naturalOrder());
        System.out.println("eligible=" + names);

        Predicate<Candidate> excellent = c -> c.active() && c.score() >= 90;
        System.out.println("excellent=" +
                select(data, excellent, Candidate::name, Comparator.naturalOrder()));

        Function<Candidate, String> label = Candidate::name;
        Function<Candidate, String> uppercase = label.andThen(String::toUpperCase);
        System.out.println("upper=" +
                select(data, eligible, uppercase, Comparator.naturalOrder()));

        List<String> reverse = select(data, eligible,
                c -> c.name() + ":" + c.score(), Comparator.reverseOrder());
        System.out.println("reverse=" + reverse);

        List<String> fakeMessages = new ArrayList<>();
        deliver(names, fakeMessages::add);
        System.out.println("delivered=" + fakeMessages);
        System.out.println("sourceSize=" + data.size());
    }
}
```

Lệnh chạy:

```bash
javac --release 17 -encoding UTF-8 FunctionalWorkflowDemo.java
java FunctionalWorkflowDemo
```

Đầu ra chính xác:

```text
eligible=[An, Chi, Dung]
excellent=[Chi]
upper=[AN, CHI, DUNG]
reverse=[Dung:82, Chi:95, An:85]
delivered=[An, Chi, Dung]
sourceSize=4
```

Giải thích:

- `eligible`: caller dùng `Predicate<Candidate>` “đang hoạt động và điểm ít nhất 80” để chọn người.
- `excellent`: thay đúng predicate “ít nhất 90”, **không cần viết thêm class hoặc copy hàm select**.
- `upper`: dùng `Candidate::name` và `andThen(String::toUpperCase)` để thay bước format.
- `reverse`: giữ predicate, thay formatter và comparator để hiển thị `name:score` theo thứ tự chuỗi đảo.
- `deliver`: nhận `Consumer<String>` để quyết định nơi đưa kết quả tới; trong ví dụ, `fakeMessages::add` là nơi nhận giả (in-memory) thay cho dịch vụ gửi thật.
- `sourceSize=4`: nguồn ban đầu không bị workflow biến đổi; đây là mẫu có khả năng kiểm thử và tái sử dụng tốt.

Điểm cần lưu ý: `select` tạo dữ liệu bằng `filter`, `map`, `sorted`, `toList`. Các hành động cần **thực thi bắt buộc** được đưa vào `deliver` riêng; không giấu việc gửi thông báo vào `map` hay `peek`.

## 10. Method reference khi đã có phương thức phù hợp

Nếu đã có một phương thức thực hiện đúng việc cần làm, method reference thường ngắn gọn:

```java
FeePolicy p = BehaviorInjectionDemo::flatFee;
Function<Candidate, String> name = Candidate::name;
Consumer<String> print = System.out::println;
```

Đây là các câu lệnh minh họa trong lớp có các kiểu phù hợp. Chúng tương ứng về hành vi với:

```java
FeePolicy p = order -> BehaviorInjectionDemo.flatFee(order);
Function<Candidate, String> name = candidate -> candidate.name();
Consumer<String> print = value -> System.out.println(value);
```

Lưu ý: hai nhóm trên **không thể copy chung vào một block scope** vì khai báo trùng tên `p`, `name`, `print`; chúng dùng để so sánh cú pháp.

Java hỗ trợ các dạng phổ biến `ClassName::staticMethod`, `instance::instanceMethod`, `ClassName::instanceMethod` (receiver là tham số của functional interface), và `ClassName::new`. Method reference được chọn theo **target type** và overload resolution; không phải mọi tên phương thức đều tự suy ra được kiểu khi đứng một mình.

Ưu tiên method reference khi nó giúp code **dễ đọc hơn**; nếu cần thêm validation, ghép nhiều bước hoặc điều kiện, lambda có thể rõ ràng hơn.

## 11. Truyền hành vi tại nơi gọi và tạo factory của hành vi

Một ưu điểm là có thể **trả về hành vi** từ một phương thức:

```java
static FeePolicy freeFrom(int threshold, FeePolicy original) {
    Objects.requireNonNull(original);
    return order -> order.amount() >= threshold
            ? 0
            : original.fee(order);
}
```

Đây là phương thức từ ví dụ đầy đủ ở mục 8. `threshold` và `original` được lambda **capture** để dùng về sau.

Ví dụ:

```java
FeePolicy base = order -> 20;
FeePolicy freeShipping = freeFrom(100, base);
```

Khi gọi `freeShipping.fee(order)`, nếu amount của order ít nhất 100 thì trả 0; nếu không, gọi `base.fee(order)`. Đây là cách tạo **biến thể bằng cách kết hợp quy tắc**, không cần lớp `FreeShippingOver100Policy` riêng.

Về lambda capture, biến cục bộ được tham chiếu từ lambda phải là **final hoặc effectively final** theo quy tắc Java; lambda không có quyền tự thay đổi biến cục bộ bắt giữ bên ngoài. Không nên “lách” quy tắc bằng array mutable chỉ để quản lý trạng thái chia sẻ, vì dễ dẫn tới side effects và race.

Nếu logic bao bọc lớn, có trạng thái nhiều bước hoặc cần tài liệu độc lập, tạo một lớp policy riêng vẫn có thể là lựa chọn tốt hơn.

## 12. So sánh điều kiện cấu hình với passing behavior

Một thiết kế thường dẫn đến nhiều nhánh:

```text
int calculate(Order order, String type) {
    if (type.equals("FLAT")) { ... }
    else if (type.equals("PRIORITY")) { ... }
    else if (type.equals("FREE_100")) { ... }
    else { ... }
}
```

Đây là **mã giả**, không phải Java độc lập vì thân các nhánh bị lược bỏ. Vấn đề: mỗi khi thêm chiến lược, phải sửa trực tiếp service, mở rộng danh sách `if/else` và rủi ro phá logic cũ.

Với tham số hành vi:

```java
int total(Order order, FeePolicy policy) {
    int fee = policy.fee(order);
    return Math.addExact(order.amount(), fee);
}
```

Đây là bản **rút gọn chỉ để so sánh cấu trúc**; phiên bản đầy đủ ở mục 8 còn kiểm tra null, amount và fee.

Nếu ứng dụng nhận một chuỗi cấu hình như `"PRIORITY"` từ HTTP/CLI, vẫn có thể có một **bước chọn strategy ở ranh giới**:

```text
String mode từ request
      |
  chọn FeePolicy đúng
      |
QuoteService.total(order, policy)
```

Việc chọn ở ranh giới **khác với** việc nhúng hàng loạt nhánh lựa chọn vào logic tính toán cốt lõi. Caller chịu trách nhiệm chọn policy; service chỉ làm việc với hợp đồng `FeePolicy`.

Cũng không nên biến logic rất đơn giản thành cấu trúc quá trừu tượng. Nếu có đúng một cách tính cố định và không có nhu cầu thay đổi, thêm functional parameter có thể chỉ làm API khó hiểu hơn.

## 13. Tính dễ kiểm thử: thay phụ thuộc thật bằng fake function

Tham số hóa hành vi là một hình thức **dependency injection đơn giản**. Khi test, bạn có thể truyền một policy giả, không cần dựng cây class hoặc mock phức tạp:

```java
FeePolicy zeroFee = order -> 0;
int total = service.total(new Order("T-1", 80, false), zeroFee);
if (total != 80) {
    throw new AssertionError("expected 80, got " + total);
}
```

Đoạn minh họa nằm trong bối cảnh có `QuoteService`, `FeePolicy`, `Order` và biến `service`. Vì fee policy là hàm thuần trả 0, test có thể tập trung vào **validation và phép cộng** của service.

Có thể test thêm các trường hợp:

- Policy trả phí âm → service báo `IllegalArgumentException`.
- `order.amount()` âm → service từ chối dữ liệu.
- Policy là `null` → `Objects.requireNonNull` báo lỗi.
- Tổng vượt miền `int` → `Math.addExact` phát sinh `ArithmeticException`.
- Policy tính phí dựa trên priority → kết quả đúng từng loại order.

Nếu test cần quan sát số lần callback được gọi, có thể dùng fake có trạng thái **trong một test tuần tự**. Không nên viết test phụ thuộc thứ tự callback khi API cho phép thực thi song song hoặc tối ưu hóa.

### Kiểm thử hành vi và kiểm thử tích hợp là hai lớp khác nhau

Một lambda fake có thể chứng minh service **gọi đúng hợp đồng**, nhưng không chứng minh một dịch vụ gửi email/ghi DB thật hoạt động. Vẫn cần integration test cho ranh giới hệ thống ngoài, retry và persistence theo kiến trúc thực tế.

## 14. Phân biệt hành vi thuần và hành vi có side effects

**Hàm thuần** (*pure function*) thường chỉ dùng input và trả output, không sửa trạng thái bên ngoài. Một `FeePolicy` nhận Order rồi tính fee là ứng viên tốt cho hàm thuần.

**Hành vi có side effects** như ghi file, gửi thông báo, cập nhật DB hoặc đếm sự kiện có thể được truyền bằng `Consumer` hay interface riêng, nhưng cách truyền lambda **không tự bảo đảm**:

- Hành động chỉ chạy đúng một lần trong toàn hệ thống.
- Có transaction hay rollback khi phát sinh lỗi.
- Mọi hành động đều hoàn tất nếu xử lý bị hủy.
- An toàn luồng khi nhiều thread cùng gọi lambda.
- Thứ tự xử lý khi dùng parallel stream.

Ví dụ `deliver(names, fakeMessages::add)` dùng một List giả ở chương trình chính, không được hiểu là “hệ thống gửi email đã thành công”.

Nếu hành động bắt buộc thực thi trên từng record, hãy gọi nó tại **bước xử lý tường minh** (`for`, terminal `forEach` được quản lý đúng hoặc một service), không ẩn vào `Stream.peek` hoặc `map` rồi giả định framework sẽ chạy side effects. Đồng thời xác định rõ ai chịu trách nhiệm catch/rethrow checked exceptions, ghi trạng thái và thử lại.

## 15. Checked exceptions và functional interface

Các interface chuẩn như `Function<T,R>.apply` hoặc `Consumer<T>.accept` không khai báo checked exception. Vì vậy lambda truyền cho chúng **không thể ném trực tiếp** một checked exception như `IOException` chưa được xử lý.

Ví dụ một method có `throws IOException` không thể được gọi trực tiếp từ lambda `Function<String,String>` nếu không bắt lỗi, chuyển đổi ngoại lệ hoặc thay đổi target interface phù hợp.

Khi hành vi miền nghiệp vụ có lỗi checked cần caller giải quyết, có thể định nghĩa:

```java
@FunctionalInterface
interface CheckedOperation<T> {
    void execute(T value) throws java.io.IOException;
}
```

Đây là khai báo interface độc lập có thể đặt trong một lớp/tệp phù hợp. Nó làm **hợp đồng throws** hiện diện rõ, thay vì âm thầm bọc mọi lỗi thành `RuntimeException`.

Không nên định nghĩa interface riêng chỉ để “tránh try/catch” nếu API bên ngoài vẫn đòi `Consumer<T>`. Khi nối với Stream API, bạn vẫn cần chính sách chuyển đổi hoặc xử lý lỗi ở ranh giới thích hợp.

## 16. Những lúc class riêng vẫn tốt hơn lambda

Hãy **giữ hoặc tạo class** khi hành vi có:

1. **Nhiều phương thức hợp tác** hoặc một protocol vượt quá một SAM.
2. **Trạng thái và lifecycle thực sự**: kết nối, cache, cấu hình mutable, quản lý tài nguyên.
3. **Nhiều dependency** cần được inject rõ ràng và quản lý bởi DI container.
4. **Danh tính/đăng ký plugin/cấu hình**: chính sách được bật tắt, đặt tên và quan sát độc lập.
5. **Hành vi đủ phức tạp** để cần tài liệu, unit test và logging riêng.
6. **Yêu cầu mở rộng có kiểm soát** với phân lớp/sealed hierarchies hoặc kiểu domain cụ thể.
7. **Tái sử dụng nhiều nơi**, nơi một lớp/đối tượng có tên có thể rõ hơn lambda lặp lại.

Ví dụ một chính sách tính phí dựa vào bảng giá, khu vực, tỷ giá, thời gian và rule engine có thể xứng đáng là một service hoặc class. `FeePolicy` vẫn là hợp đồng truyền vào `QuoteService`; chỉ vì caller được phép dùng lambda **không có nghĩa** mọi implementation phải là lambda.

Tương tự, một hàm một dòng nhưng có ý nghĩa nghiệp vụ quan trọng có thể được viết thành **named method reference**, giúp vừa ngắn ở nơi gọi vừa dễ tìm kiếm/kiểm thử.

## 17. Các lỗi thiết kế thường gặp khi truyền hành vi

| Sai lầm | Vì sao là vấn đề | Hướng xử lý |
| --- | --- | --- |
| Tạo class mới cho từng lambda một dòng | Nhiều boilerplate mà không thêm ý nghĩa | Truyền lambda hoặc method reference |
| Dồn logic chung vào mọi strategy | Copy/paste validation và điều phối | Giữ pipeline chung ở một nơi, truyền bước thay đổi |
| Viết `if/else` chọn policy trong core service | Core phải sửa mỗi khi thêm biến thể | Chọn policy ở ranh giới, truyền vào core |
| Truyền `Function<Object,Object>` để “linh hoạt” | Mất an toàn kiểu và ý nghĩa domain | Dùng generic đúng hoặc interface tên miền |
| Dùng `Consumer<T>` khi cần kết quả | Consumer có SAM trả `void` | `Function<T,R>` hay interface với return type |
| Lambda quá dài, chứa nhiều logic nghiệp vụ | Khó đọc, khó test và debug | Đặt tên method/class rõ ràng |
| Lambda capture đối tượng mutable chia sẻ | Kết quả phụ thuộc trạng thái, dễ race | Ưu tiên immutability, hàm thuần |
| Method reference khó hiểu hơn lambda | Người đọc phải truy ngược nhiều lớp | Chọn hình thức dễ đọc nhất |
| Service tin mọi callback đều trả hợp lệ | Có thể nhận giá trị âm/null/vượt miền | Kiểm tra hợp đồng ngay ở ranh giới |
| Dùng `peek` để gọi action bắt buộc | Intermediate stage có thể không được thực thi | Đưa action vào bước terminal tường minh |
| Gộp mọi behavior thành 10 tham số lambda | API rối, dễ đảo tham số | Tạo config object/policy object có tên |
| Tự viết functional interface cho mọi `map` | Lặp API chuẩn không cần thiết | Ưu tiên `java.util.function` nếu đủ ý nghĩa |
| Tưởng lambda tự động thread-safe | Lambda có thể capture shared mutable state | Thiết kế concurrency riêng |
| Tưởng functional interface có thể tự ném mọi checked exception | SAM có hợp đồng `throws` cụ thể | Bắt/convert lỗi hoặc định nghĩa SAM phù hợp |

## 18. Bài tập thực hành (có đáp án)

**Bài 1 — Nhận diện điểm thay đổi.** Một bộ lọc có ba phiên bản: lọc theo tuổi, theo điểm, theo trạng thái. Cả ba cùng chạy `source.stream().filter(...).toList()`. Phần nào nên truyền làm tham số?

Đáp án: truyền `Predicate<T>` cho điều kiện; giữ `stream().filter(rule).toList()` làm pipeline chung.

**Bài 2 — Viết lambda cho phí.** Với `FeePolicy` như bài, viết policy có phí 30 cho đơn priority và 10 cho đơn thường.

Đáp án:

```java
FeePolicy policy = order -> order.priority() ? 30 : 10;
```

Đây là lệnh minh họa trong phương thức có kiểu `Order`, `FeePolicy` phù hợp.

**Bài 3 — Method reference.** Khi có `static int flatFee(Order order)`, biểu diễn nó thành `FeePolicy` bằng method reference như thế nào?

Đáp án: `FeePolicy rule = BehaviorInjectionDemo::flatFee;` khi ở lớp hoặc ngữ cảnh truy cập được phương thức tương ứng.

**Bài 4 — Kiểm thử.** Vì sao truyền `order -> 0` cho `QuoteService` thuận lợi hơn viết một lớp `ZeroFeeTestPolicy` cho một test đơn giản?

Đáp án: fake ngắn, dễ nhìn tại nơi test, không cần tạo class/file riêng; đồng thời vẫn được kiểm tra kiểu `FeePolicy`. Nếu fake phải mô phỏng nhiều trạng thái, class riêng có thể rõ hơn.

**Bài 5 — So sánh interface chuẩn.** Một bước nhận `Candidate` và trả `String`. Nên dùng `Consumer<Candidate>` hay `Function<Candidate,String>`?

Đáp án: dùng `Function<Candidate,String>` vì cần trả kết quả `String`. `Consumer` có `void accept(...)`.

**Bài 6 — Refactor if/else.** Core service nhận `String feeMode`, tự `if/else` để chọn ba quy tắc phí. Nên chuyển việc chọn chính sách đi đâu?

Đáp án: ra **caller/rìa hệ thống** (chỗ đọc request/config). Core nhận `FeePolicy` và không cần biết mode nào đã được chọn.

**Bài 7 — Truyền nhiều hành vi.** Trong `select(source,rule,format,order)`, thay `rule` nhưng giữ `format` và `order` có phải viết lại phương thức `select` không?

Đáp án: không. Caller truyền `Predicate` khác. Đó là lợi ích của một quy trình chung nhận tham số hành vi.

**Bài 8 — State.** Vì sao `int[] count={0}; Consumer<String> action=s -> count[0]++;` có thể khó dùng an toàn trong parallel stream?

Đáp án: mảng mutable được capture, nhiều luồng có thể tăng không đồng bộ gây race. Quy tắc effectively final chỉ bảo vệ **tham chiếu biến cục bộ**, không khiến nội dung đối tượng capture tự bất biến hoặc thread-safe.

**Bài 9 — Khi dùng class.** Chính sách cần truy cập database, có cache, cấu hình theo khách hàng và vòng đời riêng. Nên nhất quyết viết một lambda dài để giảm số class không?

Đáp án: không. Có thể dùng một class/service riêng implement cùng interface, vì đây là một abstraction độc lập có trạng thái và trách nhiệm thật.

**Bài 10 — Chọn policy và tính total.** Với đơn `amount=120`, `priority=true`, policy priority `50` và policy `freeFrom(100, priority)`, tổng trả về khi dùng policy được bao bọc là bao nhiêu?

Đáp án: `120`. Vì amount đạt ngưỡng nên fee bằng 0; `QuoteService` cộng 120 + 0. Đây là sự thay đổi hành vi qua đối tượng hàm, không cần sửa service.

## 19. Checklist trước khi refactor từ nhiều lớp sang tham số hành vi

1. **Đã xác định đúng điểm biến thiên chưa?** Chỉ khác một bước thực sự hay các lớp còn khác dữ liệu/trách nhiệm khác?
2. **Phần chung có thể đưa vào một hàm/service không?** Tránh duplication ở validation, logging và error handling.
3. **Hợp đồng hành vi đã đủ rõ chưa?** Kiểu tham số, kiểu kết quả, điều kiện hợp lệ, checked exceptions.
4. **Có functional interface phù hợp không?** Ưu tiên chuẩn; tạo interface miền nghiệp vụ khi nó thêm ý nghĩa.
5. **Đã đặt tên cho hành vi phức tạp chưa?** Lambda inline ngắn, method reference cho code có tên, class cho logic nhiều trách nhiệm.
6. **Hành vi có thuần không?** Nếu có side effects, xác định vòng đời, concurrency, transaction và lỗi.
7. **Caller có chọn đúng policy không?** Không chuyển toàn bộ `if/else` khó hiểu từ core sang nhiều nơi khác mà không có quy tắc.
8. **Test có cover cả core và policy không?** Dùng fake policy cho core; test policy thật độc lập, và integration test nếu có hệ thống ngoài.
9. **Refactor có thực sự cải thiện cách đọc không?** Giảm boilerplate mà không làm API khó gọi/khó tìm kiếm hơn.
10. **Có rủi ro capture mutable state không?** Tránh phụ thuộc trạng thái không kiểm soát, nhất là khi parallel.

## 20. Ghi nhớ

- Nếu **nhiều lớp chỉ khác một thao tác ngắn**, có thể giữ một quy trình chung và **truyền hành vi** qua tham số functional interface.
- **Lambda** và **method reference** là cách cung cấp implementation của một functional interface mà không cần viết class chuyên biệt cho mỗi biến thể.
- **Strategy Pattern không biến mất**: thay vì luôn tạo class Strategy, ta có thể triển khai Strategy bằng lambda khi đơn giản.
- Chọn interface chuẩn (`Predicate`, `Function`, `Consumer`, `Supplier`, `Comparator`) khi chúng đủ biểu đạt; dùng interface domain có tên khi cần hợp đồng rõ.
- **Core service** sở hữu quy trình chung và validation; **caller** quyết định hành vi; test truyền fake để kiểm thử phần chung.
- Functional parameterization giúp mở rộng khả năng xử lý mà không thêm hàng loạt class, nhưng **không thay thế** class/service khi có trạng thái, cấu hình, lifecycle hoặc nghiệp vụ phức tạp.
- Lambda không tự bảo đảm side effects, checked exceptions, thread safety hoặc exactly-once. Những vấn đề ấy vẫn cần thiết kế riêng.

Tài liệu chính thức: [Java SE 17 — java.util.function](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/function/package-summary.html), [Function](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/function/Function.html), [Predicate](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/function/Predicate.html), [Comparator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Comparator.html), [JLS 9.8 — Functional Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.8), [JLS 15.27 — Lambda Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.27).
