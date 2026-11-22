# Viết collector có thể kiểm chứng khi xử lý song song trong Java

Một custom collector chỉ đáng tin khi kết quả của nó **không đổi theo cách stream chia dữ liệu thành các phần và ghép các phần đó lại**. Khi dùng `parallelStream()`, Java có thể tạo nhiều accumulator độc lập rồi kết hợp chúng theo cây khác nhau. Nếu `combiner` sai, dùng trạng thái dùng chung hoặc khai báo sai `Collector.Characteristics`, kết quả có thể đúng ở stream tuần tự nhưng sai khi chạy song song.

Bài thực hành này xây dựng một collector tổng hợp đơn hàng theo khu vực: đếm số đơn, tính tổng tiền theo đơn vị xu, tìm giá trị nhỏ nhất/lớn nhất. Collector dùng `HashMap` và accumulator mutable riêng cho từng nhánh, sau đó ghép bằng một phép kết hợp có tính kết hợp. Bài kiểm chứng bằng cách so sánh:
- Kết quả stream tuần tự với stream song song.
- Kết quả custom collector với collector tham chiếu có sẵn của JDK.
- Tính kết hợp của `combiner` với ba partition và hai cách đặt ngoặc.
- Luật identity khi ghép accumulator với accumulator rỗng.
- Các characteristic được khai báo có đúng với implementation hay không.

Ví dụ sử dụng cú pháp và API **Java 8**, có thể biên dịch bằng JDK 8 trở lên. Bài chỉ dùng các API collector hiện hành; không dựa vào cơ chế đã lỗi thời.

## 1. `Collector` giải quyết việc gì?

Một stream pipeline có thể kết thúc bằng `collect(...)` để gom các phần tử thành một kết quả. `Collector<T, A, R>` mô tả cách thực hiện phép gom đó:

- `T`: kiểu phần tử đầu vào.
- `A`: kiểu accumulator trung gian, thường là một container mutable.
- `R`: kiểu kết quả cuối cùng mà caller nhận được.

Ví dụ:
- `Collectors.toList()` gom phần tử thành List.
- `Collectors.toSet()` gom phần tử thành Set.
- `Collectors.joining(",")` nối chuỗi.
- `Collectors.groupingBy(...)` phân nhóm theo key.
- `Collectors.summarizingLong(...)` tạo thống kê count/sum/min/max.
- `Collectors.toMap(...)` tạo Map theo key/value mapper.

Một collector có thể dùng trong stream tuần tự hoặc song song. Framework stream quản lý cách tạo accumulator, phân phối phần tử, kết hợp các accumulator và gọi finisher. **Người viết collector phải định nghĩa các phép toán sao cho mọi cách chia/ghép hợp lệ đều cho kết quả tương đương.**

## 2. Bốn thành phần của một collector

Một collector gồm bốn hàm cốt lõi và một tập characteristic:

| Thành phần | Kiểu khái niệm | Vai trò |
| --- | --- | --- |
| `supplier` | `() -> A` | Tạo accumulator rỗng mới |
| `accumulator` | `(A, T) -> void` | Thêm một phần tử vào accumulator |
| `combiner` | `(A, A) -> A` | Ghép hai accumulator từng xử lý các phần dữ liệu khác nhau |
| `finisher` | `A -> R` | Chuyển accumulator thành kết quả cuối |
| `characteristics` | `Set<Characteristic>` | Cho framework biết những bảo đảm mà collector cung cấp |

Ví dụ ý tưởng với số tiền:
- Supplier tạo một bucket có count bằng 0.
- Accumulator nhận một đơn hàng và cập nhật count, sum, min, max.
- Combiner ghép bucket trái và phải.
- Finisher tạo một object kết quả bất biến để trả cho caller.

`A` và `R` có thể khác nhau. Trong bài này `A` là `Map<String, Bucket>`, còn `R` là `Map<String, Summary>`. Finisher tạo các Summary bất biến và trả một map không sửa được.

## 3. Vì sao parallel stream cần combiner đúng?

Giả sử có 12 đơn hàng. Stream có thể chia thành ba phần:

```text
Đầu vào: [o1 o2 o3 o4 | o5 o6 o7 o8 | o9 o10 o11 o12]

Partition A -> accumulator A
Partition B -> accumulator B
Partition C -> accumulator C

Kết hợp:
combine(A, B) -> AB
combine(AB, C) -> ABC
                    |
                    v
                 finisher
                    |
                    v
                kết quả cuối
```

Một runtime khác có thể kết hợp `B` với `C` trước rồi mới kết hợp `A`. Số partition cũng có thể thay đổi theo nguồn dữ liệu, runtime và tình trạng thực thi.

Nếu phép kết hợp chỉ đúng theo một thứ tự cụ thể, kết quả song song sẽ không ổn định. Vì vậy `combiner` phải thỏa **tính kết hợp (associativity)**; supplier phải tạo identity container; accumulator và combiner phải tương thích.

## 4. Ba luật quan trọng trong hợp đồng Collector

### 4.1. Identity constraint

Với một accumulator đã có dữ liệu `a`, ghép nó với accumulator rỗng do supplier tạo ra phải cho kết quả tương đương `a`:

```text
combine(a, supplier()) ≡ a
```

Ký hiệu `≡` nghĩa là tương đương về kết quả sau finisher, không nhất thiết cùng object hoặc cùng identity trong bộ nhớ.

Ví dụ sum: ghép với tổng 0 không đổi kết quả. Với map thống kê, ghép map có dữ liệu với map rỗng không đổi thống kê.

### 4.2. Associativity constraint

Với ba accumulator `a`, `b`, `c`, hai cách nhóm phép kết hợp phải tương đương:

```text
combine(combine(a, b), c)
        ≡
combine(a, combine(b, c))
```

Phép cộng số nguyên không overflow là associative. Phép trừ không associative:

```text
(10 - 3) - 2 = 5
10 - (3 - 2) = 9
```

Không dùng phép trừ trực tiếp làm combiner nếu kết quả cần độc lập với cách partition. Tương tự, nối chuỗi theo thứ tự tùy ý không thể được đánh dấu UNORDERED.

### 4.3. Compatibility giữa accumulator và combiner

Thêm một phần tử vào accumulator phải tương đương với việc tạo một accumulator mới chỉ chứa phần tử đó rồi ghép vào accumulator ban đầu:

```text
accumulate(a, item)
        ≡
combine(a, accumulate(supplier(), item))
```

Nếu accumulator cập nhật count/sum nhưng combiner quên cộng count, hoặc accumulator chuẩn hóa key còn combiner không làm vậy, collector sẽ cho kết quả khác nhau giữa cách chạy tuần tự và song song.

### 4.4. Finisher không được làm thay đổi ý nghĩa

Finisher phải chuyển trạng thái trung gian thành kết quả tương ứng. Nếu finisher bỏ sót một key, làm tròn số khác với accumulator hoặc phụ thuộc vào trạng thái ngoài collector, kết quả sẽ không còn tương đương.

Với một collector có `IDENTITY_FINISH`, finisher phải là phép chuyển identity; không được khai báo characteristic đó chỉ để tối ưu nếu thật ra có bước chuyển đổi.

## 5. Chọn dữ liệu có thể kiểm chứng

Ví dụ dùng đơn hàng với:
- `region`: khu vực.
- `amountCents`: số tiền theo đơn vị xu, kiểu `long`.

Dùng số nguyên cents giúp phép cộng chính xác trong miền biểu diễn của `long`; không dùng `double` cho tiền vì phép toán dấu phẩy động có sai số làm tròn. Collector sẽ tính theo từng region:
- `count`: số đơn.
- `totalCents`: tổng tiền.
- `minCents`: đơn có số tiền nhỏ nhất.
- `maxCents`: đơn có số tiền lớn nhất.

Dữ liệu mẫu:

```text
north: 1000
south: 2500
north: -200
south: 500
central: 0
```

Kết quả mong đợi:
- `north`: count 2, total 800, min -200, max 1000.
- `south`: count 2, total 3000, min 500, max 2500.
- `central`: count 1, total 0, min 0, max 0.

Dữ liệu âm được giữ trong ví dụ để chắc chắn collector không nhầm `min`/`max` với giá trị khởi tạo 0. Trong hệ thống thực, business validation có thể cấm số tiền âm; collector vẫn cần có semantics được xác định rõ.

## 6. Thiết kế accumulator mutable riêng

Một `Bucket` là accumulator cho một region. Nó không cần thread-safe nếu collector **không khai báo CONCURRENT** và mỗi partial result được framework sử dụng riêng trong quá trình parallel reduction.

```java
static final class Bucket {
    long count;
    long totalCents;
    long minCents = Long.MAX_VALUE;
    long maxCents = Long.MIN_VALUE;

    void add(long amount) {
        count = Math.addExact(count, 1L);
        totalCents = Math.addExact(totalCents, amount);
        minCents = Math.min(minCents, amount);
        maxCents = Math.max(maxCents, amount);
    }

    Bucket combine(Bucket other) {
        count = Math.addExact(count, other.count);
        totalCents = Math.addExact(totalCents, other.totalCents);
        minCents = Math.min(minCents, other.minCents);
        maxCents = Math.max(maxCents, other.maxCents);
        return this;
    }
}
```

`Math.addExact` phát hiện overflow thay vì âm thầm wrap quanh giá trị `long`. Nếu tổng vượt giới hạn, operation ném `ArithmeticException`; ứng dụng cần quyết định miền dữ liệu hợp lệ và cách xử lý lỗi đó.

Bucket không khởi tạo min/max bằng 0 vì nếu mọi amount đều dương, min sai thành 0; nếu mọi amount đều âm, max sai thành 0. Vì mỗi bucket chỉ được tạo khi có đơn hàng đầu tiên, `minCents` và `maxCents` sẽ được cập nhật từ dữ liệu thật.

`combine` thay đổi bucket bên trái và trả lại chính bucket đó. Đây là pattern mutable reduction hợp lệ khi accumulator không bị chia sẻ đồng thời và container bên phải được framework tiêu thụ trong phép kết hợp.

## 7. Supplier: mỗi accumulator phải là object mới

Supplier phải trả một container rỗng mới cho mỗi lần được gọi:

```java
Supplier<Map<String, Bucket>> supplier = HashMap::new;
```

Không viết:

```java
Map<String, Bucket> shared = new HashMap<>();
Supplier<Map<String, Bucket>> supplier = () -> shared;
```

Đoạn sai trả cùng một map cho nhiều partial reductions. Trong parallel stream, các nhánh có thể ghi đè/lẫn dữ liệu, race condition hoặc làm combiner ghép một container với chính nó.

Quy tắc thực hành: supplier tạo container mới, không lấy từ static field hoặc cache dùng chung. Nếu muốn dùng object pool, cần có ownership và lifecycle rất rõ; collector thông thường không cần pooling.

## 8. Accumulator: cập nhật một phần tử vào container

Với map theo region:

```java
(map, order) -> map
        .computeIfAbsent(order.getRegion(), key -> new Bucket())
        .add(order.getAmountCents())
```

`computeIfAbsent` tạo bucket khi key chưa có, sau đó cập nhật bucket. Đây là đoạn code dùng Java 8 `Map.computeIfAbsent`.

Không sửa danh sách nguồn hoặc biến ngoài lambda trong accumulator. Không ghi log nghiệp vụ, gửi message, cập nhật database hay tăng biến static trong lúc collect. Stream có thể chạy trong các ngữ cảnh khác nhau; collector nên tập trung vào phép gom dữ liệu thuần.

Accumulator không cần đồng bộ nếu collector không concurrent và stream framework giữ các partial container riêng. Điều đó **không có nghĩa** mọi biến ngoài collector cũng an toàn: side effect lên một `HashMap` static vẫn có race condition.

## 9. Combiner: ghép hai partial result

Với hai map `left` và `right`, ghép từng region:

```java
(left, right) -> {
    right.forEach((region, bucket) ->
            left.merge(region, bucket, Bucket::combine));
    return left;
}
```

- Region chỉ có trong `right`: đưa bucket đó vào `left`.
- Region có ở cả hai: gọi `Bucket.combine` để cộng count/total và lấy min/max.
- Trả `left` làm accumulator sau kết hợp.

Khi một bucket từ `right` được đưa vào map `left`, collector không giữ thêm alias nào do ứng dụng quản lý; `right` là partial container được tiêu thụ và không tiếp tục dùng như kết quả độc lập. Nếu thiết kế của bạn có thể giữ hoặc tái sử dụng partial container bên phải, hãy copy bucket khi chuyển quyền sở hữu.

Một lỗi phổ biến là chỉ merge tổng tiền nhưng quên merge count/min/max. Hãy liệt kê từng trường accumulator và định nghĩa phép combine cho **tất cả** trường. Phép combine phải xử lý trường hợp một phía rỗng nếu supplier/partition có thể tạo accumulator không có dữ liệu.

## 10. Finisher: biến bucket thành kết quả bất biến

Accumulator trung gian là `Map<String, Bucket>`. API bên ngoài không cần nhìn thấy Bucket mutable. Finisher tạo `Summary` bất biến:

```java
source -> {
    Map<String, Summary> result = new TreeMap<>();
    source.forEach((region, bucket) ->
            result.put(region, new Summary(
                    bucket.count,
                    bucket.totalCents,
                    bucket.minCents,
                    bucket.maxCents)));
    return Collections.unmodifiableMap(result);
}
```

`TreeMap` làm thứ tự key ổn định khi hiển thị và kiểm thử. `Collections.unmodifiableMap` ngăn caller thay đổi cấu trúc kết quả qua reference trả về. Summary có các field final và không có setter.

Không khai báo `IDENTITY_FINISH` vì `A` và `R` khác kiểu: accumulator là map Bucket, kết quả là map Summary. Finisher thực hiện một bước chuyển đổi thực sự.

## 11. Hoàn chỉnh collector bằng Collector.of

Factory `Collector.of` cho phép khai báo supplier, accumulator, combiner, finisher và characteristics:

```java
static Collector<Order, Map<String, Bucket>, Map<String, Summary>>
        byRegion() {
    return Collector.of(
            HashMap::new,
            (map, order) -> map
                    .computeIfAbsent(
                            order.getRegion(), key -> new Bucket())
                    .add(order.getAmountCents()),
            (left, right) -> {
                right.forEach((region, bucket) ->
                        left.merge(region, bucket, Bucket::combine));
                return left;
            },
            source -> {
                Map<String, Summary> result = new TreeMap<>();
                source.forEach((region, bucket) ->
                        result.put(region, new Summary(
                                bucket.count,
                                bucket.totalCents,
                                bucket.minCents,
                                bucket.maxCents)));
                return Collections.unmodifiableMap(result);
            },
            Collector.Characteristics.UNORDERED
    );
}
```

Collector này:
- Có `UNORDERED` vì kết quả thống kê không phụ thuộc encounter order của các đơn; map kết quả được sắp theo region bằng TreeMap.
- **Không có `CONCURRENT`** vì HashMap và Bucket không hỗ trợ accumulator đồng thời trên cùng container.
- **Không có `IDENTITY_FINISH`** vì finisher chuyển Bucket thành Summary.

Dùng `Collector.of` overload có bốn đối số nếu không cần characteristic; overload năm đối số cho phép khai báo characteristic rõ ràng. Không thêm characteristic chỉ để “parallel nhanh hơn”; đó là cam kết về ngữ nghĩa và thread-safety mà implementation phải đáp ứng.

## 12. UNORDERED, CONCURRENT, IDENTITY_FINISH nghĩa là gì?

| Characteristic | Cam kết | Chỉ khai báo khi |
| --- | --- | --- |
| `UNORDERED` | Kết quả không phụ thuộc thứ tự encounter của input | Collector thực sự không cần giữ thứ tự |
| `CONCURRENT` | Accumulator có thể được gọi đồng thời trên cùng result container | Container và mọi state được cập nhật đều thread-safe |
| `IDENTITY_FINISH` | Có thể bỏ qua finisher vì accumulator chính là kiểu kết quả | A và R tương thích và finisher chỉ là identity |

`UNORDERED` không có nghĩa Map phải có iteration order ngẫu nhiên. Ví dụ này không phụ thuộc thứ tự đơn hàng, nhưng finisher trả TreeMap nên thứ tự key vẫn được sắp xếp.

`CONCURRENT` là cam kết mạnh hơn “collector chạy được với parallel stream”. Một collector không concurrent vẫn chạy song song bằng nhiều accumulator độc lập và combiner. **Không cần khai báo CONCURRENT để dùng `parallelStream().collect(...)`.**

Khi collector có `CONCURRENT`, framework có thể gọi accumulator đồng thời trên cùng container trong điều kiện reduction concurrent được cho phép (stream unordered hoặc collector cũng UNORDERED). HashMap/Bucket mutable thông thường không đáp ứng cam kết này.

`IDENTITY_FINISH` không có nghĩa finisher “chạy nhanh”; nó có nghĩa kết quả accumulator có thể được dùng trực tiếp như R mà không cần chuyển đổi. Nếu finisher tạo map mới, immutable wrapper hoặc Summary khác kiểu, không được khai báo.

## 13. Dùng custom collector với stream tuần tự và song song

Sau khi có factory `byRegion()`, cách dùng giống collector có sẵn:

```java
Map<String, Summary> sequential =
        orders.stream().collect(byRegion());

Map<String, Summary> parallel =
        orders.parallelStream().collect(byRegion());
```

`collect` là terminal operation. Mỗi lần gọi stream terminal operation, pipeline được thực thi và tạo kết quả mới. Không tái sử dụng một Stream đã terminal operation.

Không viết accumulator bên ngoài rồi gọi `forEach` trên parallel stream để sửa một Map thường:

```java
Map<String, Long> totals = new HashMap<>();

orders.parallelStream().forEach(order ->
        totals.merge(
                order.getRegion(),
                order.getAmountCents(),
                Long::sum));
```

Đoạn này có race condition vì nhiều worker thread có thể cập nhật cùng `HashMap`. Dùng `collect(byRegion())` để framework quản lý các partial containers và combiner. Nếu thật sự cần shared concurrent accumulation, phải chọn concurrent data structure và semantics đúng; không chỉ thay HashMap bằng ConcurrentHashMap rồi giả định mọi giá trị bên trong cũng thread-safe.

## 14. Chương trình chạy đầy đủ — VerifiableCollectorDemo

Tạo file `VerifiableCollectorDemo.java`. Chương trình này tương thích Java 8, không dùng record, var, List.of hay Stream.toList.

```java
import java.util.*;
import java.util.stream.*;

public class VerifiableCollectorDemo {
    static final class Order {
        private final String region;
        private final long amountCents;

        Order(String region, long amountCents) {
            if (region == null || region.trim().isEmpty()) {
                throw new IllegalArgumentException("region is required");
            }
            this.region = region;
            this.amountCents = amountCents;
        }

        String getRegion() { return region; }
        long getAmountCents() { return amountCents; }
    }

    static final class Summary {
        final long count;
        final long totalCents;
        final long minCents;
        final long maxCents;

        Summary(long count, long totalCents,
                long minCents, long maxCents) {
            this.count = count;
            this.totalCents = totalCents;
            this.minCents = minCents;
            this.maxCents = maxCents;
        }

        @Override
        public boolean equals(Object value) {
            if (!(value instanceof Summary)) return false;
            Summary other = (Summary) value;
            return count == other.count
                    && totalCents == other.totalCents
                    && minCents == other.minCents
                    && maxCents == other.maxCents;
        }

        @Override
        public int hashCode() {
            return Objects.hash(
                    count, totalCents, minCents, maxCents);
        }

        @Override
        public String toString() {
            return "count=" + count
                    + ",totalCents=" + totalCents
                    + ",minCents=" + minCents
                    + ",maxCents=" + maxCents;
        }
    }

    static final class Bucket {
        long count;
        long totalCents;
        long minCents = Long.MAX_VALUE;
        long maxCents = Long.MIN_VALUE;

        void add(long amount) {
            count = Math.addExact(count, 1L);
            totalCents = Math.addExact(totalCents, amount);
            minCents = Math.min(minCents, amount);
            maxCents = Math.max(maxCents, amount);
        }

        Bucket combine(Bucket other) {
            count = Math.addExact(count, other.count);
            totalCents = Math.addExact(
                    totalCents, other.totalCents);
            minCents = Math.min(minCents, other.minCents);
            maxCents = Math.max(maxCents, other.maxCents);
            return this;
        }
    }

    static Collector<Order, Map<String, Bucket>, Map<String, Summary>>
            byRegion() {
        return Collector.of(
                HashMap::new,
                (map, order) -> map
                        .computeIfAbsent(
                                order.getRegion(),
                                key -> new Bucket())
                        .add(order.getAmountCents()),
                (left, right) -> {
                    right.forEach((region, bucket) ->
                            left.merge(
                                    region, bucket, Bucket::combine));
                    return left;
                },
                source -> {
                    Map<String, Summary> result = new TreeMap<>();
                    source.forEach((region, bucket) ->
                            result.put(region, new Summary(
                                    bucket.count,
                                    bucket.totalCents,
                                    bucket.minCents,
                                    bucket.maxCents)));
                    return Collections.unmodifiableMap(result);
                },
                Collector.Characteristics.UNORDERED
        );
    }

    static Map<String, Summary> reference(List<Order> orders) {
        Map<String, LongSummaryStatistics> statistics =
                orders.stream().collect(Collectors.groupingBy(
                        Order::getRegion,
                        TreeMap::new,
                        Collectors.summarizingLong(
                                Order::getAmountCents)));

        Map<String, Summary> result = new TreeMap<>();
        statistics.forEach((region, stats) ->
                result.put(region, new Summary(
                        stats.getCount(), stats.getSum(),
                        stats.getMin(), stats.getMax())));
        return Collections.unmodifiableMap(result);
    }

    static Map<String, Bucket> accumulate(
            List<Order> orders,
            Collector<Order, Map<String, Bucket>, Map<String, Summary>>
                    collector) {
        Map<String, Bucket> container =
                collector.supplier().get();
        for (Order order : orders) {
            collector.accumulator().accept(container, order);
        }
        return container;
    }

    static void check(String name, boolean condition) {
        if (!condition) {
            throw new AssertionError(name);
        }
        System.out.println(name + "=PASS");
    }

    public static void main(String[] args) {
        Collector<Order, Map<String, Bucket>, Map<String, Summary>>
                collector = byRegion();

        List<Order> sample = Arrays.asList(
                new Order("north", 1000),
                new Order("south", 2500),
                new Order("north", -200),
                new Order("south", 500),
                new Order("central", 0));

        Map<String, Summary> sequential =
                sample.stream().collect(collector);
        Map<String, Summary> parallel =
                sample.parallelStream().collect(collector);
        Map<String, Summary> oracle = reference(sample);

        check("sample sequential equals parallel",
                sequential.equals(parallel));
        check("sample equals JDK reference collector",
                sequential.equals(oracle));
        System.out.println("sample=" + sequential);

        List<Order> empty = Collections.emptyList();
        check("empty result is empty",
                empty.stream().collect(collector).isEmpty());

        List<Order> generated = new ArrayList<>();
        Random random = new Random(20261106L);
        String[] regions = {"north", "south", "central", "west"};
        for (int i = 0; i < 20000; i++) {
            generated.add(new Order(
                    regions[random.nextInt(regions.length)],
                    random.nextInt(20001) - 10000));
        }

        Map<String, Summary> generatedSequential =
                generated.stream().collect(collector);
        Map<String, Summary> generatedParallel =
                generated.parallelStream().collect(collector);
        Map<String, Summary> generatedOracle =
                reference(generated);

        check("20k sequential equals parallel",
                generatedSequential.equals(generatedParallel));
        check("20k equals JDK reference collector",
                generatedSequential.equals(generatedOracle));

        int first = generated.size() / 3;
        int second = generated.size() * 2 / 3;

        Map<String, Bucket> a1 =
                accumulate(generated.subList(0, first), collector);
        Map<String, Bucket> b1 =
                accumulate(generated.subList(first, second), collector);
        Map<String, Bucket> c1 =
                accumulate(generated.subList(second, generated.size()),
                        collector);

        Map<String, Summary> leftAssociated =
                collector.finisher().apply(
                        collector.combiner().apply(
                                collector.combiner().apply(a1, b1), c1));

        Map<String, Bucket> a2 =
                accumulate(generated.subList(0, first), collector);
        Map<String, Bucket> b2 =
                accumulate(generated.subList(first, second), collector);
        Map<String, Bucket> c2 =
                accumulate(generated.subList(second, generated.size()),
                        collector);

        Map<String, Summary> rightAssociated =
                collector.finisher().apply(
                        collector.combiner().apply(
                                a2, collector.combiner().apply(b2, c2)));

        check("combiner associativity",
                leftAssociated.equals(rightAssociated));

        Map<String, Summary> beforeIdentity =
                generated.stream().collect(collector);
        Map<String, Bucket> nonEmpty =
                accumulate(generated, collector);
        Map<String, Summary> afterIdentity =
                collector.finisher().apply(
                        collector.combiner().apply(
                                nonEmpty, collector.supplier().get()));

        check("right identity",
                beforeIdentity.equals(afterIdentity));

        Map<String, Bucket> leftIdentityContainer =
                collector.combiner().apply(
                        collector.supplier().get(),
                        accumulate(generated, collector));

        check("left identity",
                generatedSequential.equals(
                        collector.finisher().apply(
                                leftIdentityContainer)));

        List<Order> prefix =
                new ArrayList<>(generated.subList(0, 100));
        Order probe = new Order("compat", 123);
        List<Order> withProbe = new ArrayList<>(prefix);
        withProbe.add(probe);

        Map<String, Summary> accumulatedDirect =
                withProbe.stream().collect(collector);

        Map<String, Bucket> prefixContainer =
                accumulate(prefix, collector);
        Map<String, Bucket> probeContainer =
                accumulate(Collections.singletonList(probe), collector);

        Map<String, Summary> accumulatedByCombine =
                collector.finisher().apply(
                        collector.combiner().apply(
                                prefixContainer, probeContainer));

        check("accumulator-combiner compatibility",
                accumulatedDirect.equals(accumulatedByCombine));

        check("supplier creates fresh containers",
                collector.supplier().get()
                        != collector.supplier().get());

        check("collector is not concurrent",
                !collector.characteristics().contains(
                        Collector.Characteristics.CONCURRENT));

        check("collector is unordered",
                collector.characteristics().contains(
                        Collector.Characteristics.UNORDERED));

        check("finisher is not identity",
                !collector.characteristics().contains(
                        Collector.Characteristics.IDENTITY_FINISH));

        System.out.println(
                "characteristics=" + collector.characteristics());
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 VerifiableCollectorDemo.java
java VerifiableCollectorDemo
```

## 15. Kết quả chạy đã kiểm chứng

Chạy chương trình trên JDK 24 cho output:

```text
sample sequential equals parallel=PASS
sample equals JDK reference collector=PASS
sample={central=count=1,totalCents=0,minCents=0,maxCents=0, north=count=2,totalCents=800,minCents=-200,maxCents=1000, south=count=2,totalCents=3000,minCents=500,maxCents=2500}
empty result is empty=PASS
20k sequential equals parallel=PASS
20k equals JDK reference collector=PASS
combiner associativity=PASS
right identity=PASS
left identity=PASS
accumulator-combiner compatibility=PASS
supplier creates fresh containers=PASS
collector is not concurrent=PASS
collector is unordered=PASS
finisher is not identity=PASS
characteristics=[UNORDERED]
```

Bài test tạo 20.000 đơn hàng bằng `Random` với seed cố định `20261106`. Seed cố định giúp dữ liệu test tái lập; nó **không** được dùng làm nguồn khóa hoặc nonce mật mã.

## 16. Vì sao đối chiếu với collector tham chiếu có giá trị?

Chỉ so sánh stream tuần tự và song song chưa đủ. Nếu accumulator và combiner cùng chứa một lỗi logic, hai kết quả vẫn có thể giống nhau. Ví dụ cả hai đều quên cập nhật min; test parallel/sequential vẫn PASS dù đáp án sai.

Trong chương trình, hàm `reference` dùng collector JDK:

```java
Collectors.groupingBy(
        Order::getRegion,
        TreeMap::new,
        Collectors.summarizingLong(Order::getAmountCents))
```

`summarizingLong` trả `LongSummaryStatistics` có count, sum, min, max. Đây là một cách triển khai độc lập để tạo **oracle** đối chiếu. Nó không dùng Bucket hoặc combiner của custom collector.

Một bộ kiểm chứng mạnh thường có nhiều lớp:
1. Đối chiếu với đáp án tính tay trên dataset nhỏ.
2. Đối chiếu với API tham chiếu đã được JDK cung cấp.
3. So sánh sequential và parallel.
4. Kiểm tra luật algebra của accumulator/combiner.
5. Thử dữ liệu rỗng, một phần tử, trùng key, số âm, biên và overflow.

Đừng coi một phép so sánh duy nhất là bằng chứng đầy đủ. Mỗi lớp bắt một loại lỗi khác nhau.

## 17. Kiểm tra associativity bằng ba partition

Chương trình chia dataset 20.000 phần tử thành ba đoạn:
- `A`: phần đầu.
- `B`: phần giữa.
- `C`: phần cuối.

Mỗi đoạn được accumulate vào một container mới. Sau đó so sánh:

```java
combine(combine(A, B), C)
combine(A, combine(B, C))
```

Cả hai kết quả được đưa qua finisher rồi so sánh bằng `Map.equals`. Việc dùng container độc lập cho mỗi cách nhóm rất quan trọng vì combiner có thể mutate container bên trái. Nếu tái sử dụng A/B/C sau lần combine thứ nhất, phép thử thứ hai có thể vô tình nhận dữ liệu đã bị thay đổi.

Test associativity không chỉ là viết công thức ra giấy. Nó giúp bắt các lỗi thường gặp:
- Combiner cộng sum nhưng bỏ count.
- Min/max chỉ cập nhật khi một phía có key.
- Dùng phép toán không associative như trừ hoặc chia.
- Chọn phần tử “đầu tiên” theo thứ tự partition trong khi collector tuyên bố unordered.
- Finisher bỏ qua một phần accumulator.

## 18. Kiểm tra identity và compatibility

Identity test tạo một accumulator rỗng bằng supplier rồi ghép vào accumulator có dữ liệu. Kết quả sau finisher phải bằng kết quả trước khi ghép.

Chương trình kiểm tra cả hai hướng:
- `combine(nonEmpty, empty)`.
- `combine(empty, nonEmpty)`.

Compatibility test lấy một prefix và một order riêng:
1. Gom tất cả trực tiếp bằng accumulator.
2. Gom prefix vào container A.
3. Gom order riêng vào container B.
4. Dùng combiner ghép A và B.
5. So sánh kết quả sau finisher.

Điều này kiểm tra accumulator và combiner mô tả cùng một phép gom. Nếu accumulator xử lý một phần tử theo quy tắc khác combiner, test sẽ phát hiện.

Supplier cũng được kiểm tra bằng cách gọi hai lần và xác nhận hai container khác object. Nếu supplier trả cùng instance, parallel reduction không còn các accumulator độc lập.

## 19. Vì sao collector này không khai báo CONCURRENT?

Collector dùng:
- `HashMap<String, Bucket>`.
- `Bucket` có các field long mutable.
- `computeIfAbsent`, `merge` và phép cộng không được đồng bộ.

Các cấu trúc này **không an toàn khi nhiều thread cùng cập nhật một accumulator duy nhất**. Tuy nhiên, collector vẫn dùng được với parallel stream vì collector không khai báo CONCURRENT: framework tạo các partial containers riêng cho từng nhánh, mỗi nhánh cập nhật container của mình, rồi combiner hợp nhất chúng.

Đây là khác biệt cần nhớ:

| Trường hợp | Container |
| --- | --- |
| Collector không CONCURRENT + parallel stream | Nhiều accumulator độc lập, sau đó combine |
| Collector CONCURRENT | Accumulator có thể nhận cập nhật đồng thời trên cùng container khi điều kiện reduction cho phép |

Đừng thêm `CONCURRENT` vào characteristics để mong stream chạy nhanh hơn. Nếu khai báo, bạn phải chứng minh cả map lẫn giá trị mutable bên trong đều thread-safe, và semantics của accumulator cho phép gọi đồng thời.

## 20. Khi nào nên dùng groupingByConcurrent?

JDK có `Collectors.groupingByConcurrent` cho trường hợp cần concurrent grouping. Ví dụ đơn giản:

```java
ConcurrentMap<String, List<Order>> grouped =
        orders.parallelStream().collect(
                Collectors.groupingByConcurrent(
                        Order::getRegion));
```

Method trả về ConcurrentMap. Đây là lựa chọn có sẵn khi mục tiêu là nhóm theo key và không cần giữ encounter order.

So sánh nhanh:

| API | Dùng khi |
| --- | --- |
| `groupingBy` | Muốn grouping và không cần concurrent collector |
| `groupingByConcurrent` | Muốn concurrent grouping, không cần giữ encounter order |
| `Collector.of` | Cần accumulator/combiner/finisher riêng hoặc kết quả đặc thù |

Không mặc định `groupingByConcurrent` nhanh hơn. Với số key ít, contention cao, hoặc downstream work nặng, performance phụ thuộc dữ liệu và runtime. Benchmark bằng workload thực tế trước khi đổi collector.

Nếu cần downstream collector, có thể kết hợp `groupingBy` với `summarizingLong` hoặc `mapping` để tận dụng collector chuẩn thay vì tự viết.

## 21. Các collector có sẵn nên xem trước khi tự viết

Java 8 cung cấp nhiều collector composable:
- `counting`: đếm phần tử.
- `summingInt`, `summingLong`, `summingDouble`: tính tổng.
- `averagingInt`, `averagingLong`, `averagingDouble`: trung bình.
- `summarizingInt`, `summarizingLong`, `summarizingDouble`: count/sum/min/max.
- `groupingBy` và `partitioningBy`: nhóm dữ liệu.
- `mapping`: áp dụng mapper trước downstream collector.
- `filtering` chưa có trong Java 8; API này được bổ sung sau, vì vậy không dùng trong ví dụ cần chạy Java 8.
- `collectingAndThen`: áp dụng finisher bổ sung.
- `joining`: nối chuỗi.

Ví dụ grouping + summary không cần custom collector:

```java
Map<String, LongSummaryStatistics> stats =
        orders.stream().collect(
                Collectors.groupingBy(
                        Order::getRegion,
                        Collectors.summarizingLong(
                                Order::getAmountCents)));
```

Chỉ viết custom collector khi collector có sẵn không diễn tả được kết quả hoặc hiệu năng cần thiết. Custom collector kéo theo trách nhiệm kiểm tra luật identity, associativity, compatibility và characteristic.

## 22. `collect` và `reduce` không thay thế tùy tiện cho nhau

`reduce` phù hợp với phép reduction có identity và associative operator, thường tạo kết quả theo phép kết hợp bất biến như sum/min/max.

`collect` được thiết kế cho mutable reduction: supplier tạo container, accumulator cập nhật container, combiner ghép container, finisher tạo kết quả.

Không dùng mutable identity với reduce theo cách sau:

```java
List<String> wrong =
        words.parallelStream().reduce(
                new ArrayList<String>(),
                (list, word) -> {
                    list.add(word);
                    return list;
                },
                (left, right) -> {
                    left.addAll(right);
                    return left;
                });
```

Đây là cách dùng mutable object làm identity trong reduce, có thể vi phạm giả định identity/associativity và tạo kết quả không đúng khi song song. Hãy dùng:

```java
List<String> correct =
        words.parallelStream().collect(
                Collectors.toList());
```

Hoặc viết custom Collector nếu cần một container/result riêng. `collect` là abstraction phù hợp cho mutable accumulation.

## 23. Giữ encounter order hay không?

Một collector chỉ được khai báo `UNORDERED` khi kết quả không phụ thuộc encounter order. Ví dụ thống kê count/sum/min/max theo region là không phụ thuộc thứ tự đơn hàng.

Nếu kết quả là danh sách giữ thứ tự input, “phần tử đầu tiên/cuối cùng”, chuỗi ghép theo thứ tự hoặc chọn record thắng theo tie-break phụ thuộc encounter order thì không thể tự động khai báo `UNORDERED`.

Ngay cả khi stream nguồn có encounter order, characteristic UNORDERED nói rằng collector không cam kết giữ thứ tự đó. Trong ví dụ, TreeMap sắp key alphabetically; đó là **thứ tự key của kết quả**, không phải thứ tự các đơn hàng đầu vào.

Nếu cần deterministic winner, định nghĩa comparator/tie-break rõ ràng và dùng phép combine có tính kết hợp. Không để combiner chọn “left thắng” nếu kết quả đúng/sai phụ thuộc partition tree.

## 24. Parallel stream không đồng nghĩa nhanh hơn

Parallel stream có chi phí chia nguồn dữ liệu thành partition, tạo accumulator cho các nhánh, điều phối task/thread và kết hợp partial containers. Nó cũng có thể contention hoặc tốn allocation.

Nguồn dữ liệu dễ split, dataset đủ lớn, công việc mỗi phần tử đáng kể và combiner rẻ thường phù hợp hơn. Với collection nhỏ, pipeline nhẹ hoặc combiner đắt, stream tuần tự có thể nhanh hơn.

Không gọi `parallel()` chỉ vì thấy API hỗ trợ. Hãy xác định phép toán có associative không; xác nhận source split tốt; kiểm tra không có side effect dùng chung; so sánh sequential/parallel; benchmark bằng dữ liệu gần production, có warm-up và nhiều lần đo; theo dõi allocation, CPU, GC và contention.

Test correctness và benchmark performance là hai việc khác nhau. Một collector chạy song song đúng chưa chắc nhanh.

## 25. Kiểm tra overflow và miền dữ liệu

Ví dụ dùng `Math.addExact` để không âm thầm wrap khi tổng vượt `Long.MAX_VALUE` hoặc thấp hơn `Long.MIN_VALUE`. Với dữ liệu tiền, lựa chọn phù hợp có thể là:
- `long` cents nếu đơn vị nhỏ nhất và miền tổng đã được giới hạn.
- `BigDecimal` nếu nghiệp vụ cần decimal precision/scale khác.
- Kiểu số khác theo domain và giới hạn dữ liệu.

Nếu dùng `BigDecimal`, hãy định nghĩa scale/rounding ở tầng nghiệp vụ và kiểm tra phép combine giữ đúng semantics. Không chuyển qua double rồi kỳ vọng phép cộng song song giống hệt decimal arithmetic.

Test nên có tổng gần giới hạn kiểu số, số âm và số 0, một region chỉ có một record, nhiều record cùng key, input rỗng và region null/blank bị từ chối hoặc xử lý theo policy rõ. Collector nên xác định rõ lỗi overflow; đừng để số liệu wrap rồi trả kết quả trông có vẻ hợp lệ.

## 26. Lỗi thường gặp khi viết collector song song

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| Supplier trả cùng container | Race condition/lẫn partial results | Tạo container mới mỗi lần |
| Accumulator có side effect bên ngoài | Kết quả phụ thuộc scheduling | Giữ phép gom trong accumulator |
| Combiner quên field | Sequential/parallel khác nhau | Merge mọi field |
| Combiner không associative | Kết quả phụ thuộc cây combine | Dùng phép toán associative |
| Identity container không thực sự rỗng | Kết quả bị cộng/trộn thêm dữ liệu | Supplier trả trạng thái neutral |
| Accumulator và combiner khác logic | Partition làm đổi kết quả | Kiểm tra compatibility |
| Khai báo CONCURRENT với HashMap | Data race/corruption | Không khai báo hoặc dùng thiết kế concurrent thật |
| Khai báo UNORDERED khi cần first/last | Mất semantics encounter order | Bỏ characteristic, định nghĩa tie-break |
| Khai báo IDENTITY_FINISH khi có conversion | Framework bỏ finisher không đúng | Chỉ khai báo nếu finisher identity |
| Finisher sửa accumulator ngoài dự kiến | Kết quả bị mutate/lệch | Tạo result rõ ràng, không phụ thuộc state ngoài |
| Dùng reduce với mutable container | Vi phạm reduction contract | Dùng collect |
| Chỉ test một input nhỏ | Không bắt lỗi partition | Test sample, random và nhiều partition |
| Chỉ so sequential với parallel | Cùng lỗi có thể xuất hiện ở cả hai | Thêm oracle độc lập |
| Chỉ test output mà không test laws | Không rõ combiner có hợp lệ | Test identity, associativity, compatibility |
| Dùng double cho tổng tiền | Sai số làm tròn | Dùng cents/BigDecimal theo domain |

## 27. Bộ test nên kiểm tra những trường hợp nào?

| Nhóm test | Dữ liệu | Điều cần chứng minh |
| --- | --- | --- |
| Empty | Không có order | Kết quả rỗng, không crash |
| Singleton | Một order | Count/min/max đều lấy từ phần tử đó |
| Duplicate key | Nhiều order cùng region | Combiner cộng đủ mọi partition |
| Negative/zero | Số âm và 0 | Min/max không bị khởi tạo sai |
| Large input | Nhiều nghìn phần tử | Parallel và sequential tương đương |
| Oracle | Collector JDK độc lập | Không cùng lặp lại một bug |
| Partition tree | Ba hoặc nhiều partial containers | Associativity |
| Identity | Container rỗng | Ghép rỗng không đổi kết quả |
| Compatibility | Accumulate trực tiếp và accumulate+combine | Accumulator/combiner cùng semantics |
| Overflow | Tổng vượt miền long | Lỗi được phát hiện theo policy |
| Invalid key | Null/blank region | Input validation rõ ràng |
| Characteristics | Đọc characteristic set | Không khai báo cam kết sai |

Một stream nhỏ có thể chạy parallel mode nhưng không tạo đủ công việc để bộc lộ race condition. Dùng dữ liệu lớn hơn và test trực tiếp combiner với các partition độc lập. Với collector concurrent, cần test thêm nhiều thread cùng cập nhật container theo đúng characteristic đã khai báo.

## 28. Đọc lỗi khi sequential đúng nhưng parallel sai

Khi test phát hiện sequential/parallel khác nhau, kiểm tra theo thứ tự:

1. **Supplier:** mỗi lần gọi có tạo accumulator mới không?
2. **Accumulator:** cập nhật đủ mọi field và không mutate state ngoài không?
3. **Combiner:** có merge đủ mọi field, kể cả khi key chỉ có ở một phía không?
4. **Associativity:** kết quả có đổi theo cách đặt ngoặc không?
5. **Identity:** ghép với container rỗng có giữ nguyên kết quả không?
6. **Compatibility:** accumulator một phần tử có tương đương combine với container một phần tử không?
7. **Characteristic:** UNORDERED/CONCURRENT/IDENTITY_FINISH có đúng không?
8. **Input:** source có bị sửa trong khi pipeline chạy không? Mapper/key có phụ thuộc thời gian hoặc mutable state không?
9. **Numeric domain:** overflow hoặc floating-point rounding có làm kết quả khác nhau không?
10. **Side effect:** có ghi vào static map/list, database hoặc external service trong accumulator không?

Nếu chỉ fail trong parallel, đừng thêm `synchronized` ngay để che triệu chứng. Xác định container nào thực sự được chia sẻ và collector có đang hứa CONCURRENT sai không. Một collector không concurrent vốn đã có cơ chế partial-container + combiner để chạy song song.

## 29. Lưu ý khi đưa collector vào ứng dụng thật

- **Định nghĩa null policy:** ví dụ Order constructor từ chối region null/blank. Nếu muốn gán key mặc định, hãy làm rõ đó là business rule.
- **Định nghĩa overflow policy:** ví dụ dùng `Math.addExact` để fail fast; không wrap âm thầm.
- **Giữ source không bị mutate:** không sửa collection đang được stream đọc.
- **Giữ kết quả bất biến nếu có thể:** Summary dùng final fields, map được bọc unmodifiable.
- **Không phụ thuộc global state:** collector không đọc clock, random, locale default hoặc biến static mutable.
- **Giữ combiner rẻ:** tránh sort toàn bộ partition ở mỗi lần combine nếu có thể tổng hợp trực tiếp.
- **Xác định thứ tự:** nếu cần thứ tự input, đừng khai báo UNORDERED.
- **Không thêm CONCURRENT tùy tiện:** HashMap/Bucket mutable không hỗ trợ shared concurrent accumulation.
- **Đo performance riêng:** correctness test không phải benchmark.
- **Tái sử dụng collector factory:** factory có thể trả một collector mới, nhưng không chia sẻ accumulator giữa các lần collect.

Nếu finisher trả một map không sửa được, đó là bảo vệ cấu trúc map; các value cũng cần immutable nếu caller không được phép sửa nội dung. Trong ví dụ Summary có field final và không có setter.

## 30. Checklist code review cho custom collector

**Contract**
- Supplier trả container rỗng mới mỗi lần?
- Accumulator cập nhật mọi trường đúng?
- Combiner merge mọi trường và trả container hợp lệ?
- Finisher chuyển đổi đúng, không phụ thuộc state ngoài?
- Identity và associativity đã được kiểm chứng?
- Accumulator và combiner tương thích?

**Parallel safety**
- Có side effect lên biến ngoài collector không?
- Nếu không CONCURRENT, các partial containers có độc lập không?
- Nếu CONCURRENT, toàn bộ container/value state có thread-safe không?
- UNORDERED có đúng với semantics kết quả không?
- IDENTITY_FINISH có thật sự là identity không?

**Test**
- Có test empty/singleton/duplicate/negative/zero/boundary?
- Có so sequential với parallel?
- Có oracle độc lập?
- Có test combiner với partition tree khác nhau?
- Có test identity và compatibility?
- Có test overflow và invalid input?

**Runtime**
- Source có split tốt và dataset đủ lớn?
- Collector có built-in alternative như groupingBy/summarizingLong không?
- Đã benchmark trên workload gần production?
- Kết quả có deterministic theo contract?

## 31. Câu hỏi tự kiểm tra

**1. `Collector<T, A, R>` mô tả gì?**  
Cách gom phần tử kiểu T qua accumulator A thành kết quả R.

**2. Supplier có nhiệm vụ gì?**  
Tạo một accumulator rỗng mới cho mỗi partial reduction.

**3. Accumulator làm gì?**  
Thêm một phần tử T vào container A.

**4. Combiner làm gì?**  
Ghép hai accumulator từng xử lý các phần dữ liệu riêng.

**5. Finisher làm gì?**  
Chuyển A thành kết quả cuối R.

**6. Vì sao combiner phải associative?**  
Vì runtime có thể ghép các partition theo cây khác nhau.

**7. Identity constraint yêu cầu gì?**  
Ghép accumulator với accumulator rỗng phải giữ kết quả tương đương.

**8. Compatibility kiểm tra điều gì?**  
Accumulator một phần tử phải tương đương tạo partial container rồi combine.

**9. Parallel stream có bắt buộc collector phải CONCURRENT không?**  
Không. Collector không concurrent vẫn chạy song song bằng các accumulator độc lập và combiner.

**10. Khi nào được khai báo CONCURRENT?**  
Khi accumulator có thể được gọi đồng thời trên cùng container mà vẫn đúng.

**11. UNORDERED có nghĩa gì?**  
Kết quả không phụ thuộc encounter order của phần tử đầu vào.

**12. TreeMap có làm collector thành ordered không?**  
Không. Nó sắp key của kết quả; UNORDERED nói về sự phụ thuộc vào thứ tự input.

**13. Khi nào khai báo IDENTITY_FINISH?**  
Khi accumulator có thể được dùng trực tiếp làm result, không cần chuyển đổi finisher.

**14. Vì sao supplier không được trả static HashMap?**  
Các partition sẽ dùng chung container và có race condition/lẫn dữ liệu.

**15. Vì sao collector ví dụ dùng HashMap vẫn chạy parallel được?**  
Mỗi nhánh có container riêng; framework ghép chúng bằng combiner.

**16. Vì sao phải đối chiếu với collector JDK?**  
Sequential và parallel có thể cùng sai; oracle độc lập bắt lỗi logic chung.

**17. `groupingByConcurrent` dùng cho trường hợp nào?**  
Khi muốn grouping bằng concurrent collector và semantics không cần giữ encounter order.

**18. Có nên dùng reduce với ArrayList mutable làm identity?**  
Không; dùng collect vì nó thiết kế cho mutable reduction.

**19. Parallel stream luôn nhanh hơn stream tuần tự không?**  
Không; chia task và combine có chi phí, cần benchmark.

**20. Vì sao dùng cents dạng long cho tiền trong ví dụ?**  
Tránh sai số nhị phân của double; Math.addExact giúp phát hiện overflow.

## 32. Tổng kết

- `Collector<T, A, R>` mô tả supplier, accumulator, combiner, finisher và characteristics.
- **Identity, associativity và compatibility** là các điều kiện cốt lõi để kết quả đúng khi chia/ghép song song.
- **Parallel stream không bắt buộc collector phải CONCURRENT**; collector không concurrent vẫn dùng partial containers riêng và combiner.
- Chỉ khai báo **UNORDERED** khi kết quả không phụ thuộc encounter order; chỉ khai báo **CONCURRENT** khi accumulator thật sự thread-safe; chỉ khai báo **IDENTITY_FINISH** khi không cần chuyển đổi.
- `Collector.of` là factory Java 8 để xây custom collector.
- Kiểm chứng bằng nhiều góc: đáp án nhỏ tính tay, oracle JDK, sequential/parallel, partition tree, identity và compatibility.
- Dùng built-in collector như groupingBy/summarizingLong khi đã đáp ứng nhu cầu; chỉ custom khi cần semantics riêng.
- Parallel correctness và performance là hai câu hỏi khác nhau; kiểm thử luật trước, benchmark sau.

### Tài liệu chính thức

- [Oracle Java SE 8 — Collector](https://docs.oracle.com/javase/8/docs/api/java/util/stream/Collector.html): hợp đồng collector, identity/associativity, characteristics và `Collector.of`.
- [Oracle Java SE 8 — Collectors](https://docs.oracle.com/javase/8/docs/api/java/util/stream/Collectors.html): collector dựng sẵn, grouping, summarizing và concurrent grouping.
- [Oracle Java SE 8 — Stream](https://docs.oracle.com/javase/8/docs/api/java/util/stream/Stream.html): `collect`, reduction và parallel stream semantics.
- [Oracle Java SE 26 — Collector](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Collector.html): tài liệu API hiện hành và contract của Collector.
- [Oracle Java SE 26 — Collectors](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Collectors.html): factory methods hiện hành và grouping collectors.
- [Oracle Java SE 26 — Stream](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Stream.html): stream operations, reduction và execution mode.
