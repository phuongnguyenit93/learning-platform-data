# Reducing trong một nhóm với `Collectors.groupingBy` (Java 8)

> **Bối cảnh:** Chủ đề **Phân nhóm dữ liệu** trong Java 8. `Collectors.reducing` là API chính thức của Java Stream, vẫn sử dụng được trên JDK hiện đại. Bài chỉ trình bày cách dùng và các nguyên tắc còn hiệu lực; ví dụ viết bằng cú pháp Java 8 và chạy trên JDK 17+.

## 1. Kết quả cần đạt

Sau bài học, bạn có thể:

1. Giải thích vì sao phải đặt `reducing(...)` **ở vị trí downstream collector** trong `groupingBy(...)` để tính **một kết quả cho mỗi nhóm**.
2. Đọc và chọn đúng ba overload của `Collectors.reducing`: không có identity, có identity và có identity + mapper.
3. Viết chương trình tính **doanh thu, số lượng, phần tử lớn nhất trong từng nhóm** mà không cần thu thập toàn bộ phần tử thành `List` rồi mới xử lý.
4. Phân biệt `Collectors.reducing(...)` với `Stream.reduce(...)` và với collector chuyên dụng như `summingLong`, `maxBy`.
5. Xử lý đúng `Optional`, nhóm thiếu dữ liệu, tính kết hợp của phép gộp và các lưu ý khi chạy parallel stream.

## 2. “Reducing trong một nhóm” nghĩa là gì?

Giả sử dữ liệu bán hàng gồm các dòng với `category`, `quantity`, `unitPriceCents`. Ta muốn biết:

- Nhóm **Book** có tổng giá trị bao nhiêu?
- Nhóm **Toy** có tổng giá trị bao nhiêu?
- Dòng có thành tiền lớn nhất trong **mỗi nhóm** là dòng nào?

`groupingBy` xác định **khóa nhóm** từ từng phần tử. `reducing` tạo **một giá trị tổng hợp riêng cho từng khóa**. Mô hình là:

```text
Stream<OrderLine>
       |
       | classifier: OrderLine::category
       v
+---------------------+---------------------+
| Khóa "Book"         | Khóa "Toy"          |
| Các OrderLine Book  | Các OrderLine Toy   |
+----------+----------+----------+----------+
           |                     |
           v                     v
 downstream reducing       downstream reducing
           |                     |
           v                     v
       Book -> 6900            Toy -> 6400
           \_____________________/
                     |
           Map<String, Long>
```

Về mặt API, đây là một phép **multi-level reduction**: tầng ngoài phân nhóm, tầng trong rút gọn các giá trị thuộc từng nhóm.

Dạng tổng quát:

```java
Map<K, D> result = source.stream().collect(
        Collectors.groupingBy(
                element -> key,             // classifier: T -> K
                downstreamCollector         // mỗi nhóm T -> D
        )
);
```

Khi muốn lựa chọn loại Map, dùng overload ba tham số của `groupingBy`:

```java
Map<K, D> result = source.stream().collect(
        Collectors.groupingBy(
                element -> key,
                TreeMap::new,                // mapFactory
                downstreamCollector
        )
);
```

`TreeMap` sắp xếp các khóa theo thứ tự tự nhiên. Nếu chỉ dùng overload hai tham số của `groupingBy`, đừng giả định kiểu Map cụ thể hoặc thứ tự duyệt khóa do implementation tạo ra.

### Khác gì với `groupingBy` thông thường?

```java
// Đoạn minh họa: giả định có List<OrderLine> lines.
Map<String, List<OrderLine>> groups = lines.stream().collect(
        Collectors.groupingBy(OrderLine::category));

// Mỗi nhóm được rút gọn ngay trong collect.
Map<String, Long> totals = lines.stream().collect(
        Collectors.groupingBy(
                OrderLine::category,
                Collectors.reducing(
                        0L,
                        OrderLine::lineTotalCents,
                        Long::sum)));
```

Trường hợp đầu, `Map` chứa **`List<OrderLine>`** của từng nhóm. Trường hợp sau, `Map` chứa **`Long` tổng thành tiền** của từng nhóm. Giải pháp sau tránh phải tạo các danh sách nhóm chỉ để tính tổng; điều này đặc biệt hữu ích khi cần nhiều nhóm, dữ liệu lớn hoặc kết quả là một giá trị gọn.

## 3. Ba overload của `Collectors.reducing`

Các overload đều trả về một `Collector` để dùng với `Stream.collect(...)` hoặc làm downstream của `groupingBy`.

| Overload | Loại kết quả mỗi nhóm | Tình huống phù hợp |
| --- | --- | --- |
| `reducing(BinaryOperator<T> op)` | `Optional<T>` | Chọn phần tử lớn nhất/nhỏ nhất, không có identity tự nhiên |
| `reducing(T identity, BinaryOperator<T> op)` | `T` | Gộp các phần tử **đã cùng kiểu** với kết quả |
| `reducing(U identity, Function<T,U> mapper, BinaryOperator<U> op)` | `U` | Ánh xạ từng phần tử kiểu `T` sang kiểu `U` rồi gộp |

Ở dòng thứ ba, bảng viết `Function<T,U>` để dễ đọc; chữ ký Java thật dùng wildcard `Function<? super T, ? extends U>`. Từng overload được phân tích dưới đây.

### 3.1. `reducing(op)` — không có identity, kết quả `Optional<T>`

Ví dụ tìm dòng có **thành tiền lớn nhất** trong từng nhóm:

```java
Comparator<OrderLine> byTotal =
        Comparator.comparingLong(OrderLine::lineTotalCents);

Map<String, Optional<OrderLine>> largest = lines.stream().collect(
        Collectors.groupingBy(
                OrderLine::category,
                Collectors.reducing(BinaryOperator.maxBy(byTotal))));
```

- `BinaryOperator<OrderLine>` nhận **hai `OrderLine`** và chọn một `OrderLine` theo comparator.
- Kết quả mỗi nhóm là `Optional<OrderLine>` vì overload này không có giá trị trung hòa thích hợp cho mọi trường hợp.
- Nhóm không xuất hiện trong dữ liệu sẽ **không có khóa** trong Map; `Optional.empty()` cũng là kết quả hợp lệ khi dùng `reducing(op)` trực tiếp trên stream rỗng.
- Nếu có nhiều giá trị bằng nhau, comparator phải thêm quy tắc xử lý hòa khi nghiệp vụ cần chọn nhất quán. Ví dụ có thể dùng `thenComparing(OrderLine::name)` hoặc mã định danh duy nhất ổn định.

Nếu mục tiêu chỉ là lấy phần tử lớn nhất của từng nhóm, collector `Collectors.maxBy(comparator)` thể hiện ý định rõ hơn và trả cùng loại `Optional`.

### 3.2. `reducing(identity, op)` — gộp các giá trị đã cùng kiểu

Giả sử muốn tính tổng số lượng từng nhóm nhưng mỗi phần tử gốc là `OrderLine`. Trước hết, `mapping` chuyển các `OrderLine` thành `Integer`, sau đó `reducing` cộng chúng:

```java
Map<String, Integer> quantities = lines.stream().collect(
        Collectors.groupingBy(
                OrderLine::category,
                Collectors.mapping(
                        OrderLine::quantity,
                        Collectors.reducing(0, Integer::sum))));
```

Với downstream của `mapping`, các phần tử đến `reducing` đã là `Integer`. `identity = 0` là phần tử trung hòa của phép cộng, `Integer::sum` là phép gộp có tính kết hợp.

Đừng viết `reducing(0, (sum, line) -> sum + line.quantity())` trực tiếp cho `Stream<OrderLine>`: overload hai tham số đòi cả **identity, phần tử được giảm và kết quả** thuộc kiểu `T` như nhau; ở đây `Integer` và `OrderLine` là hai kiểu khác nhau.

### 3.3. `reducing(identity, mapper, op)` — gộp sau khi biến đổi kiểu

Đây thường là dạng trực tiếp nhất khi dùng với `groupingBy`:

```java
Map<String, Long> revenue = lines.stream().collect(
        Collectors.groupingBy(
                OrderLine::category,
                Collectors.reducing(
                        0L,                         // U: Long
                        OrderLine::lineTotalCents,  // T -> U
                        Long::sum                   // U + U -> U
                )));
```

Trong đó:

- `T = OrderLine`, `K = String`, `U = Long`.
- `identity` là `0L`, trung hòa với `Long::sum`.
- `mapper` là `OrderLine::lineTotalCents`; thành tiền của một dòng bằng số lượng nhân đơn giá.
- `op` là `Long::sum`; nó kết hợp **hai `Long`**, bao gồm cả các kết quả một phần khi dữ liệu được xử lý song song.

**Điểm cần phân biệt:** overload ba tham số của **`Collectors.reducing(identity, mapper, op)`** khác overload ba tham số của **`Stream.reduce(identity, accumulator, combiner)`**:

| Thuộc tính | `Collectors.reducing(identity, mapper, op)` | `Stream.reduce(identity, accumulator, combiner)` |
| --- | --- | --- |
| Dùng ở đâu? | Trong `collect` hoặc downstream của `groupingBy` | Gọi trực tiếp trên một `Stream` |
| Tham số thứ hai | `Function<T,U>`: biến phần tử thành `U` | `BiFunction<U,T,U>`: kết hợp kết quả một phần với phần tử |
| Tham số thứ ba | `BinaryOperator<U>`: gộp hai giá trị sau mapping | `BinaryOperator<U>`: kết hợp hai kết quả một phần |
| Kết quả lệnh | Một `Collector<T,?,U>` | Một giá trị `U` |

Dùng cú pháp phù hợp với kiểu API; không truyền nhầm lambda hai đối số vào tham số `mapper` của `Collectors.reducing`.

## 4. Ví dụ Java hoàn chỉnh: ba cách reducing trong mỗi nhóm

Bộ dữ liệu cố định gồm năm dòng:

| Category | Tên hàng | Quantity | Unit price (cents) | Line total (cents) |
| --- | --- | ---: | ---: | ---: |
| Book | Java Core | 2 | 1500 | 3000 |
| Toy | Puzzle | 3 | 1000 | 3000 |
| Book | Streams | 1 | 2400 | 2400 |
| Toy | Blocks | 2 | 1700 | 3400 |
| Book | Java Core | 1 | 1500 | 1500 |

Trong bài này, đơn vị là **cent** (số nguyên) để tránh sai số biểu diễn nhị phân của `double`. Chương trình tính:

1. Doanh thu theo `category` với `reducing(identity, mapper, op)`.
2. Tổng số lượng theo `category` với `mapping(..., reducing(identity, op))`.
3. Dòng có thành tiền lớn nhất theo `category` với `reducing(op)`.
4. Đối chiếu kết quả tuần tự và song song, kiểm tra nguồn rỗng.

**Lưu toàn bộ mã sau thành tệp `GroupReducingDemo.java`:**

```java
import java.util.Arrays;
import java.util.Collections;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.TreeMap;
import java.util.function.BinaryOperator;
import java.util.stream.Collectors;

public class GroupReducingDemo {
    static final class OrderLine {
        private final String category;
        private final String name;
        private final int quantity;
        private final long unitPriceCents;

        OrderLine(String category, String name, int quantity,
                  long unitPriceCents) {
            this.category = category;
            this.name = name;
            this.quantity = quantity;
            this.unitPriceCents = unitPriceCents;
        }

        String category() { return category; }
        String name() { return name; }
        int quantity() { return quantity; }

        long lineTotalCents() {
            return Math.multiplyExact((long) quantity, unitPriceCents);
        }

        @Override
        public String toString() {
            return name + " (" + lineTotalCents() + " cents)";
        }
    }

    public static void main(String[] args) {
        List<OrderLine> lines = Arrays.asList(
                new OrderLine("Book", "Java Core", 2, 1500),
                new OrderLine("Toy", "Puzzle", 3, 1000),
                new OrderLine("Book", "Streams", 1, 2400),
                new OrderLine("Toy", "Blocks", 2, 1700),
                new OrderLine("Book", "Java Core", 1, 1500));

        // (1) OrderLine -> Long -> sum(Long) cho từng category.
        Map<String, Long> revenueByCategory = lines.stream().collect(
                Collectors.groupingBy(
                        OrderLine::category,
                        TreeMap::new,
                        Collectors.reducing(
                                0L, OrderLine::lineTotalCents, Long::sum)));

        // (2) OrderLine -> Integer qua mapping, rồi reducing.
        Map<String, Integer> quantityByCategory = lines.stream().collect(
                Collectors.groupingBy(
                        OrderLine::category,
                        TreeMap::new,
                        Collectors.mapping(
                                OrderLine::quantity,
                                Collectors.reducing(0, Integer::sum))));

        // (3) Không có identity: tối đa một OrderLine/nhóm, bọc Optional.
        Comparator<OrderLine> byLineTotal = Comparator
                .comparingLong(OrderLine::lineTotalCents)
                .thenComparing(OrderLine::name);

        Map<String, Optional<OrderLine>> largestByCategory =
                lines.stream().collect(Collectors.groupingBy(
                        OrderLine::category,
                        TreeMap::new,
                        Collectors.reducing(BinaryOperator.maxBy(byLineTotal))));

        Map<String, String> largestLabels = new TreeMap<>();
        largestByCategory.forEach((category, item) ->
                largestLabels.put(
                        category, item.map(OrderLine::toString).orElse("none")));

        // Mỗi lần collect sử dụng một stream MỚI.
        Map<String, Long> parallelRevenue = lines.parallelStream().collect(
                Collectors.groupingBy(
                        OrderLine::category,
                        TreeMap::new,
                        Collectors.reducing(
                                0L, OrderLine::lineTotalCents, Long::sum)));

        Map<String, Long> emptyGroups =
                Collections.<OrderLine>emptyList().stream().collect(
                        Collectors.groupingBy(
                                OrderLine::category,
                                TreeMap::new,
                                Collectors.reducing(
                                        0L, OrderLine::lineTotalCents, Long::sum)));

        System.out.println("Revenue (cents): " + revenueByCategory);
        System.out.println("Quantities: " + quantityByCategory);
        System.out.println("Largest lines: " + largestLabels);
        System.out.println("Parallel equal: "
                + revenueByCategory.equals(parallelRevenue));
        System.out.println("Empty groups: " + emptyGroups);

        if (!Long.valueOf(6900L).equals(revenueByCategory.get("Book"))
                || !Long.valueOf(6400L).equals(revenueByCategory.get("Toy"))
                || !Integer.valueOf(4).equals(quantityByCategory.get("Book"))
                || !Integer.valueOf(5).equals(quantityByCategory.get("Toy"))
                || !"Java Core (3000 cents)".equals(largestLabels.get("Book"))
                || !"Blocks (3400 cents)".equals(largestLabels.get("Toy"))
                || !revenueByCategory.equals(parallelRevenue)
                || !emptyGroups.isEmpty()) {
            throw new AssertionError("Wrong grouped reducing result");
        }

        System.out.println("Checks passed.");
    }
}
```

Biên dịch và chạy với JDK 17+; `--release 8` xác nhận ví dụ sử dụng API/cú pháp tương thích Java 8:

```bash
javac --release 8 GroupReducingDemo.java
java GroupReducingDemo
```

**Stdout mong đợi (đã kiểm tra các phép tính và luồng chạy trên OpenJDK 24):**

```text
Revenue (cents): {Book=6900, Toy=6400}
Quantities: {Book=4, Toy=5}
Largest lines: {Book=Java Core (3000 cents), Toy=Blocks (3400 cents)}
Parallel equal: true
Empty groups: {}
Checks passed.
```

Do dùng `TreeMap::new`, thứ tự **khóa** `Book` rồi `Toy` trong chuỗi in ra là cố định theo thứ tự từ điển. Kết quả tổng hợp không phụ thuộc thứ tự chạy thực tế của từng nhiệm vụ `parallelStream()`.

## 5. Tự tính bằng tay từng nhóm để hiểu bản chất

### 5.1. Doanh thu của Book

Ba dòng `Book` có thành tiền:

```text
Java Core  = 2 × 1500 = 3000
Streams    = 1 × 2400 = 2400
Java Core  = 1 × 1500 = 1500
Tổng Book  = 0 + 3000 + 2400 + 1500 = 6900
```

Dữ liệu `Toy`:

```text
Puzzle     = 3 × 1000 = 3000
Blocks     = 2 × 1700 = 3400
Tổng Toy   = 0 + 3000 + 3400 = 6400
```

Mỗi nhóm được bắt đầu bằng identity `0L` của riêng phép giảm nhóm đó. Không có chuyện dồn doanh thu nhóm Book vào nhóm Toy.

### 5.2. Tổng số lượng

`Book` có `2 + 1 + 1 = 4` đơn vị; `Toy` có `3 + 2 = 5`. Vì `mapping(OrderLine::quantity, ...)` chuyển các dòng về `Integer`, phép `reducing(0, Integer::sum)` có đủ thông tin để cộng số lượng mà không cần biết cấu trúc `OrderLine`.

### 5.3. Dòng lớn nhất theo thành tiền

- `Book`: dòng `Java Core` số lượng 2, thành tiền 3000, lớn hơn 2400 và 1500.
- `Toy`: dòng `Blocks` thành tiền 3400, lớn hơn `Puzzle` thành tiền 3000.

`reducing(BinaryOperator.maxBy(byLineTotal))` giữ một `OrderLine` đáp ứng comparator cho mỗi nhóm, không tạo danh sách các ứng viên lớn nhất. `thenComparing(OrderLine::name)` xử lý trường hợp hai dòng có cùng thành tiền nhưng khác tên: tên đứng sau theo thứ tự từ điển được chọn. Nếu nghiệp vụ bắt buộc tính ổn định đến từng bản ghi, nên thêm mã định danh duy nhất vào comparator.

## 6. Nhóm rỗng, identity và `Optional`

Đây là ba ý khác nhau, dễ bị lẫn:

**A. Không có phần tử mang khóa `"Book"`**

`groupingBy` không tự tạo nhóm `Book`. Vì thế kết quả có thể **không có khóa** `Book`, chứ không mặc định có `Book=0` hoặc `Book=Optional.empty()`.

```java
long bookRevenue = revenueByCategory.getOrDefault("Book", 0L);
```

Chỉ nên dùng `0L` như giá trị mặc định khi nghiệp vụ coi “không có giao dịch” tương đương “doanh thu bằng 0”; nếu cần phân biệt thiếu dữ liệu, hãy kiểm tra `containsKey`.

**B. Toàn bộ đầu vào rỗng**

`Collections.<OrderLine>emptyList().stream()` sau `groupingBy` trả **Map rỗng** `{}`. Identity của `reducing` không tự sinh thêm bất cứ khóa nhóm nào.

**C. Một collector `reducing(op)` được chạy trực tiếp trên stream rỗng**

```java
Optional<Integer> maximum = Stream.<Integer>empty()
        .collect(Collectors.reducing(Integer::max));
// maximum.isPresent() == false
```

Chính overload không identity trả `Optional.empty()` khi không có phần tử. Khi dùng trong một nhóm do `groupingBy` thực sự tạo ra, nhóm đó có ít nhất một phần tử đầu vào, nên `Optional` thường có giá trị nếu dữ liệu/combiner không chứa `null`. Giữ kiểu `Optional` đúng như hợp đồng thay vì gọi `get()` khi chưa kiểm tra.

## 7. Quy luật giúp reducing đúng khi xử lý song song

Khi `parallelStream()` xử lý dữ liệu, Stream có thể chia nguồn thành các phân đoạn, tạo các kết quả một phần rồi gộp. Với một nhóm `Book`, một cách chia giả định là:

```text
Nhánh A: 3000 + 2400 = 5400
Nhánh B: 1500
Gộp:     5400 + 1500 = 6900
```

Nhánh khác có thể tạo `3000 + (2400 + 1500)`, vẫn ra `6900` do phép cộng có tính kết hợp. Số nhánh và thứ tự xử lý không được bảo đảm.

Một phép reducing hợp lệ phải có:

1. **Identity trung hòa:** với `op`, `op(identity, x) = op(x, identity) = x`. Ví dụ `0L` cho cộng, `1L` cho nhân (khi ý nghĩa dữ liệu phù hợp).
2. **Associativity (tính kết hợp):** `op(op(a,b),c) = op(a,op(b,c))`. Phép cộng số nguyên phù hợp; phép trừ không phù hợp.
3. **Hàm thuần/stateless, không can thiệp nguồn:** `mapper` và `op` không nên sửa collection đầu vào hay dùng trạng thái mutable bên ngoài để quyết định kết quả.
4. **Kiểu giá trị và identity tương thích:** kết quả của mapper phải thuộc `U` và `op` thực sự kết hợp hai `U` thành `U`. Không chọn identity như “phụ phí 100” rồi mong được cộng đúng một lần bất kể số nhánh.

**Phản ví dụ về identity:**

```java
// SAI: 100L không phải phần tử trung hòa của phép cộng.
Collectors.reducing(100L, OrderLine::lineTotalCents, Long::sum)
```

Ở ví dụ tuần tự, mỗi nhóm sẽ bị tăng thêm 100; khi tách/gộp trong xử lý song song, identity có thể tham gia nhiều kết quả một phần và làm sai khác lớn hơn. Nếu cần thu thêm phí cho **mỗi nhóm**, hãy giảm với `0L` rồi áp dụng mức phí một lần **sau** khi có tổng nhóm.

**Phản ví dụ về phép gộp:**

```java
// SAI nếu mục tiêu là tổng: phép trừ không associative.
Collectors.reducing(0L, OrderLine::lineTotalCents, (a, b) -> a - b)
```

Không cố dùng `synchronized` hoặc `AtomicLong` để “chữa” một phép reduction vi phạm quy luật đại số. Các cơ chế đồng bộ không sửa được phép gộp sai.

**Với số tiền thực tế:** `long` biểu diễn cent chính xác trong phạm vi số nguyên 64-bit, nhưng `Long::sum` vẫn có thể **tràn số** nếu tổng quá lớn. Khi cần số tiền ở đơn vị thập phân/đa tiền tệ, hãy chuẩn hóa đơn vị tiền, quy tắc làm tròn và sử dụng `BigDecimal` hoặc số nguyên với kiểm tra tràn (`Math.addExact`), tùy yêu cầu nghiệp vụ. Không dùng `double` để làm đơn vị tiền tệ chính xác.

## 8. Kết hợp reducing với các downstream collector khác

### 8.1. Reducing bên trong hai cấp grouping

Khi muốn **doanh thu theo category rồi theo tên hàng**:

```java
Map<String, Map<String, Long>> nested = lines.stream().collect(
        Collectors.groupingBy(
                OrderLine::category,
                Collectors.groupingBy(
                        OrderLine::name,
                        Collectors.reducing(
                                0L, OrderLine::lineTotalCents, Long::sum))));
```

Kết quả theo giá trị:

```text
Book:
  Java Core -> 4500
  Streams   -> 2400
Toy:
  Puzzle    -> 3000
  Blocks    -> 3400
```

Đây là **đoạn mã minh họa** sử dụng lớp `OrderLine` và biến `lines` ở ví dụ chính. Hai tầng `groupingBy` có thể tạo ra các Map với thứ tự khóa không xác định nếu không chỉ định `mapFactory`, nhưng giá trị tổng vẫn đúng. Không cần đi qua `Map<String, List<OrderLine>>` trung gian.

### 8.2. Đổi kết quả `Optional` thành kiểu ứng dụng

`Collectors.collectingAndThen` cho phép chuyển kết quả của downstream sau khi reduction hoàn tất:

```java
Map<String, String> mostExpensiveName = lines.stream().collect(
        Collectors.groupingBy(
                OrderLine::category,
                Collectors.collectingAndThen(
                        Collectors.reducing(BinaryOperator.maxBy(byLineTotal)),
                        optional -> optional.map(OrderLine::name)
                                            .orElse("none"))));
```

Vì nhóm chỉ tồn tại khi có phần tử, trường hợp `"none"` hiếm xảy ra trong ví dụ dữ liệu hợp lệ này; vẫn nên xử lý `Optional` theo API. Không mặc nhiên cho rằng khóa không có trong Map sẽ được thêm với giá trị `"none"`.

### 8.3. Khi `reducing` không phải lựa chọn tốt nhất

Java có những collector chuyên dụng, ngắn gọn hơn cho phép gộp thông dụng:

| Cần tính theo nhóm | Downstream thường nên ưu tiên |
| --- | --- |
| Tổng số nguyên | `summingInt` / `summingLong` |
| Số phần tử | `counting` |
| Nhỏ nhất/lớn nhất theo comparator | `minBy` / `maxBy` |
| Thống kê count, sum, min, max, average | `summarizingInt` / `summarizingLong` |
| Trung bình | `averagingInt` / `averagingLong` |
| Ghép chuỗi có delimiter | `mapping(..., joining(...))` |
| Danh sách/set | `toList` / `toSet` (collector của Java 8) |

Ví dụ viết gọn doanh thu theo nhóm:

```java
Map<String, Long> revenue = lines.stream().collect(
        Collectors.groupingBy(
                OrderLine::category,
                Collectors.summingLong(OrderLine::lineTotalCents)));
```

Collector chuyên dụng có thể giảm boxing và làm ý định nghiệp vụ rõ hơn. Dùng `reducing` khi muốn học cơ chế tổng quát, kết hợp một phép gộp tùy chỉnh hoặc cần biểu diễn phép map-reduce mà không có collector chuyên biệt phù hợp.

**Phân biệt tên dễ gây nhầm:** `Collectors.toList()` là collector có từ Java 8. `Stream.toList()` là API được bổ sung ở phiên bản Java mới hơn; ví dụ trong bài tránh dùng nó để giữ tương thích Java 8.

## 9. Các lỗi phổ biến trong nghiệp vụ

| Lỗi | Điều xảy ra | Cách xử lý |
| --- | --- | --- |
| Dùng `groupingBy(classifier)` rồi lặp hết các `List` chỉ để lấy tổng | Tạo các danh sách trung gian không cần thiết | Truyền downstream `summingLong` hoặc `reducing` |
| Viết `Collectors.reducing(0, (sum, line) -> ...)` cho `OrderLine` | Sai kiểu của overload hai đối số | Dùng overload `reducing(0, mapper, op)` hoặc `mapping` trước |
| Dùng `null` làm khóa nhóm | Có thể gây `NullPointerException` ở `groupingBy` | Chuẩn hóa khóa hoặc dùng giá trị “unknown” có chủ đích trước khi nhóm |
| Gọi `map.get("Book")` và tự hiểu `null` là `0` | Không phân biệt nhóm thiếu và nhóm tổng 0 | Dùng `containsKey` hoặc `getOrDefault` theo nghiệp vụ |
| Bỏ `Optional` rồi gọi `get()` không kiểm tra | Có thể `NoSuchElementException` | Dùng `map`, `orElse`, `orElseThrow` theo yêu cầu |
| Identity sai (ví dụ 100 cho phép cộng) | Sai khi có nhiều nhóm/nhánh | Dùng identity trung hòa, áp dụng phí/điều chỉnh sau |
| Combiner không associative | Kết quả phụ thuộc cách chia dữ liệu | Sửa phép gộp, không dựa vào thứ tự gọi |
| Gộp bằng cách mutate `ArrayList` dùng chung | Có thể race và sai kết quả | Dùng collector `toList` hoặc `collect` đúng hợp đồng |
| Gọi `parallelStream` mặc định để tăng tốc | Overhead chia/merge Map có thể tốn hơn | Đo benchmark trên khối lượng và phần cứng thực tế |
| Dựa vào thứ tự in của `HashMap` | Test/log khó lặp lại | Dùng `TreeMap::new` nếu cần thứ tự khóa |

### Có cần `groupingByConcurrent`?

`Collectors.groupingByConcurrent` phục vụ một số tình huống thu thập song song và không cần bảo toàn encounter order; nó là API hợp lệ hiện nay. Tuy nhiên nó **không phải thay thế mặc định** cho `groupingBy`:

- Nhóm đầu ra không có cùng cam kết thứ tự với `TreeMap`.
- Bài toán cần thứ tự ổn định hoặc trạng thái downstream nhạy với thứ tự phải cân nhắc riêng.
- Hiệu quả phụ thuộc phân phối khóa, tranh chấp giữa worker, chi phí mapper/combiner và kích thước dữ liệu.

Trong phần lớn bài toán báo cáo nhỏ hoặc trung bình, bắt đầu với `stream()` và collector đơn giản, rồi chỉ chuyển song song sau khi đã chứng minh tính đúng đắn và đo hiệu quả.

## 10. Bài tập thực hành và kiểm chứng

**Bài 1.** Với bảng dữ liệu ở phần 4, tự tính:

- Tổng thành tiền mỗi category.
- Tổng quantity mỗi category.
- Dòng có thành tiền lớn nhất của từng category.

So sánh với stdout đã trình bày. Giải thích vì sao `Book=6900` nhưng `Book` chỉ có 4 sản phẩm.

**Bài 2.** Thêm `new OrderLine("Book", "Testing", 2, 500)` vào dữ liệu. Tổng doanh thu Book thay đổi thành bao nhiêu? Dòng có thành tiền lớn nhất Book thay đổi hay không? (Đáp án: `7900`; vẫn là `Java Core` với thành tiền `3000`.)

**Bài 3.** Đổi downstream tính tổng doanh thu sang `Collectors.summingLong(OrderLine::lineTotalCents)`. Kết quả theo nhóm có thay đổi không? (Không, nếu dữ liệu và giới hạn số học giống nhau.)

**Bài 4.** Viết một `Map<String, Long>` tính **doanh thu theo tên hàng** thay vì category bằng cách đổi classifier thành `OrderLine::name`. `Java Core` có tổng `4500` vì hai dòng cùng tên được gộp.

**Bài 5.** Đặt `reducing(100L, mapper, Long::sum)` rồi thử kết quả tuần tự và song song. Hãy giải thích bằng quy luật identity vì sao không thể dùng cách này để cộng phụ phí đúng một lần.

**Tự kiểm tra cuối bài:**

1. Vì sao `Collectors.reducing(identity, mapper, op)` có thể nhận `Stream<OrderLine>` nhưng trả `Long`?
2. `groupingBy(..., reducing(op))` tạo `Map<K, Optional<T>>` vì lý do gì?
3. Khi nguồn rỗng, tại sao `groupingBy(..., reducing(0L, ...))` trả `{}` thay vì tự sinh `{"Book": 0}`?
4. Trong phép cộng tổng thành tiền, ba yếu tố nào giúp kết quả không phụ thuộc cách chia nhánh?
5. Khi nào `summingLong` hoặc `maxBy` thể hiện rõ ý định hơn `reducing`?

**Gợi ý trả lời:** (1) mapper đổi kiểu `T` thành `U` trước khi gộp; (2) overload không identity phải biểu diễn trường hợp không có phần tử; (3) `groupingBy` chỉ tạo khóa xuất hiện trong dữ liệu; (4) identity trung hòa, phép gộp associative và hàm stateless/không can thiệp; (5) khi chỉ cần phép tổng hoặc cực trị thông dụng.

## Tài liệu chuẩn còn hiệu lực

- [Oracle Java SE 25 — `Collectors`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Collectors.html): ba overload `reducing`, `groupingBy`, `mapping`, `summingLong`, `maxBy`, `collectingAndThen`.
- [Oracle Java SE 25 — `Stream`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Stream.html): `collect` và `reduce`, sự khác nhau giữa accumulator/combiner và phép gộp terminal.
- [Oracle Java SE 25 — `java.util.stream`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/package-summary.html): reduction, thứ tự, tính kết hợp, parallel/concurrent collectors.
- [Java 8 — `Collectors`](https://docs.oracle.com/javase/8/docs/api/java/util/stream/Collectors.html): đối chiếu API nguồn gốc trong Java 8.

**Điểm cốt lõi:** `groupingBy` chia phần tử theo khóa; **downstream `reducing` tính một giá trị cho từng khóa**. Chọn đúng overload, identity, mapper và phép gộp sẽ giúp kết quả rõ ràng, đúng cả tuần tự lẫn song song, và tránh tạo các danh sách nhóm không cần thiết.
