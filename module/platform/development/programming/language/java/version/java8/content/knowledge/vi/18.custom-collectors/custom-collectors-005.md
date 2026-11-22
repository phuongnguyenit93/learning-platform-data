# Luật đồng nhất và luật kết hợp khi xây dựng Collector tùy biến

Trong Java Stream, một **`Collector` tùy biến** mô tả cách gom các phần tử thành kết quả: tạo vùng chứa, thêm phần tử, hợp nhất các vùng chứa và chuyển sang kết quả cuối. Để cùng một collector cho **kết quả tương đương** khi Stream xử lý tuần tự hoặc chia thành nhiều phần để xử lý song song, các hàm đó phải tuân theo **luật đồng nhất (identity constraint)** và **luật kết hợp (associativity constraint)**.

Hai luật này là *hợp đồng về tính đúng đắn*, không chỉ là mẹo tối ưu hiệu năng. Một collector viết sai có thể tình cờ cho đáp án đúng khi duyệt tuần tự nhưng đếm thừa, bỏ mất dữ liệu hoặc trả kết quả phụ thuộc cách chia nhóm khi gọi `parallelStream()`.

## 1. Collector hoạt động và được chia nhóm như thế nào?

Một `Collector<T, A, R>` gồm ba kiểu:

- **`T`**: kiểu của mỗi phần tử từ Stream.
- **`A`**: kiểu vùng chứa trung gian có thể thay đổi (mutable accumulation type).
- **`R`**: kiểu kết quả cuối, có thể giống hoặc khác `A`.

Bốn hàm chức năng chính:

| Thành phần | Kiểu khái niệm | Nhiệm vụ |
| --- | --- | --- |
| `supplier` | `Supplier<A>` | Tạo **vùng chứa mới**, ở trạng thái rỗng về mặt logic. |
| `accumulator` | `BiConsumer<A,T>` | Đưa một phần tử vào vùng chứa. |
| `combiner` | `BinaryOperator<A>` | Ghép hai vùng chứa đã tích lũy, trả về vùng chứa chứa kết quả gộp. |
| `finisher` | `Function<A,R>` | Hoàn thiện kết quả, chẳng hạn tạo đối tượng `Summary` bất biến từ vùng chứa trung gian. |

Khi dùng `Collector.of(supplier, accumulator, combiner, finisher)`, ta cung cấp các hàm trên. Nếu `A` cũng là `R` và không cần finisher riêng, có overload `Collector.of(supplier, accumulator, combiner)`.

Mô phỏng một pipeline **tuần tự**:

```text
e = supplier()
accumulator(e, t1)
accumulator(e, t2)
accumulator(e, t3)
result = finisher(e)
```

Trong xử lý **song song**, thư viện có quyền phân hoạch dữ liệu:

```text
a = supplier()                  b = supplier()
accumulator(a, t1)             accumulator(b, t2)
accumulator(a, t3)             accumulator(b, t4)
             \                 /
              combiner(a, b)
                    |
               finisher(...)
```

Số vùng chứa được tạo, cách phân hoạch và thứ tự kết hợp không phải điều ta nên hard-code. Chính vì vậy `supplier`, `accumulator`, `combiner` và `finisher` phải thống nhất về *ý nghĩa* của kết quả.

## 2. Luật đồng nhất (identity constraint)

### 2.1. Phát biểu đúng của luật

Gọi `e = supplier.get()` là **một vùng chứa rỗng mới**. Gọi `a` là trạng thái đã tích lũy từ một nhóm phần tử bất kỳ. Hợp nhất `a` với `e` không được làm thay đổi kết quả quan sát được:

```text
combine(a, e) ≈ a
```

Dấu `≈` có nghĩa là **tương đương về kết quả**, không bắt buộc là cùng một tham chiếu đối tượng. Một combiner có thể sửa trực tiếp `a` rồi trả lại nó, hoặc tạo một vùng chứa kết quả khác, miễn phép tổng hợp cuối tương đương.

Ví dụ collector đếm số dòng và cộng số lượng:

```text
a = {soDong=3, soLuong=9}
e = {soDong=0, soLuong=0}

combine(a, e) = {soDong=3, soLuong=9}
combine(e, a) = {soDong=3, soLuong=9}
```

Đặc tả của `Collector` nêu cụ thể yêu cầu kết hợp `a` với `supplier.get()` ở bên phải phải cho kết quả tương đương. Trong thiết kế phép cộng/ghép dữ liệu thông thường, cần giữ phần tử rỗng trung hòa ở **cả hai phía**, vì một vùng chứa rỗng cũng có thể là nhánh bên trái của phép kết hợp khi triển khai chia nhóm.

### 2.2. Vùng chứa rỗng không nhất thiết là số `0`

Phần tử trung hòa phụ thuộc vào loại phép tổng hợp:

| Phép tổng hợp | Trạng thái từ `supplier` | Hợp nhất với trạng thái rỗng |
| --- | --- | --- |
| Tổng số lượng | `0` | `a + 0 = a` |
| Đếm bản ghi | `0` | Không thêm số đếm. |
| Tích số | `1` | `a × 1 = a` |
| Ghép danh sách | Danh sách mới, rỗng | `a ++ [] = a` |
| Gom vào `Map` | `Map` mới, rỗng | Không thêm hoặc sửa các ánh xạ hiện có. |
| Tính trung bình | `{sum=0, count=0}` | Không thay đổi tổng và số phần tử; **không** khởi tạo “trung bình” bằng một số có nghĩa giả. |

`supplier` phải tạo **một vùng chứa độc lập cho mỗi lần gọi**. Không dùng một `ArrayList` hoặc đối tượng accumulator tĩnh duy nhất rồi trả về từ mọi lời gọi `supplier`: hai nhánh song song có thể cùng sửa một đối tượng, làm sai tính cô lập.

### 2.3. Trường hợp vi phạm luật đồng nhất

Giả sử một collector cộng giá trị tiền nhưng `supplier` lại cấp sẵn phí xử lý `100` cho **mỗi vùng chứa**:

```java
// Minh họa sai trong ngữ cảnh có lớp Box và Purchase ở mục 5:
() -> {
    Box box = new Box();
    box.totalCents = 100;
    return box;
}
```

Khi phân thành ba nhóm, phí `100` bị cộng ba lần; trong tuần tự có thể chỉ cộng một lần. Ngay cả ghép với vùng chứa “rỗng” cũng thêm `100`, vi phạm `combine(a, supplier.get()) ≈ a`.

Nếu nghiệp vụ yêu cầu cộng **một khoản phí cho toàn bộ kết quả**, hãy để vùng chứa khởi tạo bằng trạng thái trung hòa và cộng phí **một lần** ở bước `finisher` (hoặc xử lý sau `collect`). Không gắn chi phí phát sinh một lần vào supplier vốn được phép gọi nhiều lần.

## 3. Luật kết hợp (associativity constraint)

### 3.1. Có thể đặt dấu ngoặc ở đâu cũng được

Với các trạng thái đã gom `a`, `b`, `c`, việc hợp nhất phải không làm thay đổi ý nghĩa khi thay cách chia nhóm:

```text
combine(combine(a, b), c) ≈ combine(a, combine(b, c))
```

Ví dụ với phép cộng:

```text
(2 + 3) + 4 = 2 + (3 + 4) = 9
```

Nhờ tính kết hợp, Stream có thể gom dữ liệu từng phần rồi hợp nhất các kết quả mà không phụ thuộc cây kết hợp.

**Không nhầm tính kết hợp với tính giao hoán.** Phép nối danh sách hoặc chuỗi theo thứ tự có tính kết hợp: `(a ++ b) ++ c` bằng `a ++ (b ++ c)`, nhưng thông thường **không có tính giao hoán**: `a ++ b` khác `b ++ a`. Nếu kết quả phụ thuộc thứ tự phần tử, collector phải tôn trọng encounter order của Stream; không tự đánh dấu `UNORDERED`.

### 3.2. Accumulator và combiner còn phải tương thích

Chỉ viết một `combiner` có vẻ “kết hợp được” chưa đủ. Nó còn phải biểu diễn **cùng một phép tổng hợp** với `accumulator`.

Giả sử hai phần tử nguồn là `t1` và `t2`. Hai cách sau phải cho **kết quả `R` tương đương**:

```java
// Cách A: gom trực tiếp cả hai phần tử
A a1 = supplier.get();
accumulator.accept(a1, t1);
accumulator.accept(a1, t2);
R direct = finisher.apply(a1);

// Cách B: gom mỗi phần tử vào một vùng chứa, rồi ghép
A a2 = supplier.get();
accumulator.accept(a2, t1);
A a3 = supplier.get();
accumulator.accept(a3, t2);
R split = finisher.apply(combiner.apply(a2, a3));

// direct phải tương đương split
```

Đây là cách kiểm tra sát với đặc tả `Collector`: **chia phép tính** không được làm đổi đáp án. Nếu accumulator **cộng** số lượng còn combiner lại lấy `Math.max` của hai tổng tạm, một pipeline có một vùng chứa và một pipeline có nhiều vùng chứa sẽ cho kết quả khác.

### 3.3. Các phép hợp lệ và những phép dễ sai

| Bài toán | Phép gộp nên dùng | Lý do |
| --- | --- | --- |
| Đếm/tổng số nguyên trong miền dữ liệu hợp lệ | Cộng các tổng tạm | Có phần tử trung hòa `0`, kết hợp được. |
| Tìm giá trị lớn nhất | Lấy `max` cùng trạng thái hỗ trợ trường hợp rỗng | Kết quả không phụ thuộc cách nhóm. |
| Ghép danh sách theo encounter order | Ghép danh sách trái rồi phải | Có danh sách rỗng và tính kết hợp; thứ tự **cần** được bảo toàn. |
| Tổng tiền thập phân | `BigDecimal.add` | Cộng chính xác theo giá trị thập phân; quy định scale nếu nghiệp vụ cần. |
| Tính trung bình | Lưu **`sum` và `count`**, tính `sum/count` tại finisher | Trung bình của các trung bình không có trọng số thường sai. |

**Không phù hợp**: dùng `(a, b) -> (a + b) / 2` để “gộp trung bình” của các phân đoạn có số phần tử khác nhau. Ví dụ nhóm A có `1` phần tử giá trị `10`, nhóm B có `3` phần tử giá trị `20`: trung bình cả tập là `(10+20+20+20)/4 = 17.5`, trong khi trung bình của `10` và `20` là `15`. Cách đúng giữ cả tổng và số lượng.

**Cẩn trọng với số thực dấu phẩy động:** phép cộng `double`/`float` không kết hợp chính xác do làm tròn, nên kết quả tuần tự và song song có thể khác một ít. Nếu tổng hợp tiền tệ, dùng `BigDecimal` hoặc lượng đơn vị nhỏ nhất kiểu số nguyên có kiểm soát tràn; nếu tính thống kê dấu phẩy động, chọn sai số chấp nhận và thuật toán số phù hợp.

## 4. Kiểm tra sự tương đương của kết quả

`Collector` không yêu cầu `combiner` phải trả đúng đối tượng `a` hay `b` theo tham chiếu. Quan trọng là giá trị kết quả.

- Với collector **không có đặc tính `UNORDERED`**, đặc tả xét kết quả qua `finisher.apply(a1).equals(finisher.apply(a2))`. Nếu `R` là lớp tự tạo, hãy định nghĩa `equals` đúng theo dữ liệu cần so sánh.
- Với collector được khai báo **`UNORDERED`**, sự tương đương có thể không đòi hỏi cùng thứ tự phần tử trong kết quả. Chỉ dùng thuộc tính này nếu thứ tự thực sự không mang ý nghĩa.
- Nếu `finisher` tạo một đối tượng bất biến `R` khác `A`, đánh giá sự tương đương ở **`R`**, chứ không dựa vào `==` giữa hai vùng chứa `A`.
- Kiểm tra collector trên stream rỗng, một phần tử, nhiều phần tử, cách phân hoạch khác nhau và cả tuần tự/song song. Việc một lần chạy song song trùng kết quả chỉ là bằng chứng kiểm thử, chưa chứng minh định luật với mọi đầu vào.

## 5. Ví dụ Java hoàn chỉnh: Collector gom số dòng, số lượng và thành tiền

Bài toán: mỗi dòng mua hàng chứa mã hàng, số lượng và đơn giá (đơn vị **cent**). Ta cần trả về một `Summary` có:

- `lines`: số dòng mua hàng;
- `units`: tổng số đơn vị sản phẩm;
- `totalCents`: tổng thành tiền của tất cả dòng.

Thay vì ba lần duyệt dữ liệu, collector dùng một vùng chứa `Box` có thể thay đổi, sau đó tạo `Summary` bất biến. Phần này đồng thời kiểm tra hai luật bằng cách hợp nhất với vùng chứa rỗng và thay cách đặt ngoặc ba phân đoạn.

Toàn bộ mã sau sử dụng API tương thích **Java 8**, và chạy được trên JDK 17+.

Lưu tệp **CollectorLawsDemo.java**:

```java
import java.util.Arrays;
import java.util.List;
import java.util.Objects;
import java.util.stream.Collector;
import java.util.stream.Stream;

public class CollectorLawsDemo {
    static final class Purchase {
        final String sku;
        final long quantity;
        final long unitPriceCents;

        Purchase(String sku, long quantity, long unitPriceCents) {
            if (quantity < 0 || unitPriceCents < 0) {
                throw new IllegalArgumentException("Negative amount");
            }
            this.sku = Objects.requireNonNull(sku, "sku");
            this.quantity = quantity;
            this.unitPriceCents = unitPriceCents;
        }
    }

    static final class Box {
        long lines;
        long units;
        long totalCents;

        void accept(Purchase purchase) {
            long lineCents = Math.multiplyExact(
                purchase.quantity, purchase.unitPriceCents
            );
            lines = Math.addExact(lines, 1);
            units = Math.addExact(units, purchase.quantity);
            totalCents = Math.addExact(totalCents, lineCents);
        }

        Box merge(Box other) {
            lines = Math.addExact(lines, other.lines);
            units = Math.addExact(units, other.units);
            totalCents = Math.addExact(totalCents, other.totalCents);
            return this;
        }

        Summary finish() {
            return new Summary(lines, units, totalCents);
        }
    }

    static final class Summary {
        final long lines;
        final long units;
        final long totalCents;

        Summary(long lines, long units, long totalCents) {
            this.lines = lines;
            this.units = units;
            this.totalCents = totalCents;
        }

        @Override
        public boolean equals(Object obj) {
            if (!(obj instanceof Summary)) {
                return false;
            }
            Summary other = (Summary) obj;
            return lines == other.lines
                && units == other.units
                && totalCents == other.totalCents;
        }

        @Override
        public int hashCode() {
            return Objects.hash(lines, units, totalCents);
        }

        @Override
        public String toString() {
            return "Summary{lines=" + lines
                + ", units=" + units
                + ", totalCents=" + totalCents + "}";
        }
    }

    static Collector<Purchase, Box, Summary> collector() {
        return Collector.of(
            Box::new,       // supplier: Box moi, 3 truong = 0
            Box::accept,    // accumulator: them mot dong
            Box::merge,     // combiner: cong hai Box
            Box::finish     // finisher: tao Summary bat bien
        );
    }

    static Box accumulate(List<Purchase> source) {
        Box box = new Box();
        for (Purchase purchase : source) {
            box.accept(purchase);
        }
        return box;
    }

    public static void main(String[] args) {
        List<Purchase> purchases = Arrays.asList(
            new Purchase("NOTEBOOK", 2, 1550),
            new Purchase("PEN", 3, 200),
            new Purchase("BAG", 1, 4900),
            new Purchase("NOTEBOOK", 4, 1550),
            new Purchase("PEN", 1, 200)
        );

        Collector<Purchase, Box, Summary> aggregation = collector();

        Summary sequential = purchases.stream().collect(aggregation);
        Summary parallel = purchases.parallelStream().collect(aggregation);
        Summary empty = Stream.<Purchase>empty().collect(aggregation);

        Summary original = accumulate(purchases).finish();

        // e ben phai va ben trai deu trung hoa.
        boolean rightIdentity = original.equals(
            accumulate(purchases).merge(new Box()).finish()
        );
        boolean leftIdentity = original.equals(
            new Box().merge(accumulate(purchases)).finish()
        );

        List<Purchase> p1 = purchases.subList(0, 2);
        List<Purchase> p2 = purchases.subList(2, 4);
        List<Purchase> p3 = purchases.subList(4, 5);

        // ((a + b) + c) so voi (a + (b + c)).
        Summary leftGrouping = accumulate(p1)
            .merge(accumulate(p2))
            .merge(accumulate(p3))
            .finish();
        Summary rightGrouping = accumulate(p1)
            .merge(accumulate(p2).merge(accumulate(p3)))
            .finish();

        System.out.println("Tuan tu: " + sequential);
        System.out.println("Song song: " + parallel);
        System.out.println("Rong: " + empty);
        System.out.println("Dong nhat phai: " + rightIdentity);
        System.out.println("Dong nhat trai: " + leftIdentity);
        System.out.println("Ket hop: "
            + leftGrouping.equals(rightGrouping));
        System.out.println("Ket qua tuong duong: "
            + sequential.equals(parallel));
        System.out.println("IDENTITY_FINISH: "
            + aggregation.characteristics().contains(
                Collector.Characteristics.IDENTITY_FINISH
            ));
    }
}
```

Biên dịch và chạy ở thư mục chứa tệp:

```bash
javac -encoding UTF-8 CollectorLawsDemo.java
java CollectorLawsDemo
```

Kết quả dự kiến (stdout):

```text
Tuan tu: Summary{lines=5, units=11, totalCents=15000}
Song song: Summary{lines=5, units=11, totalCents=15000}
Rong: Summary{lines=0, units=0, totalCents=0}
Dong nhat phai: true
Dong nhat trai: true
Ket hop: true
Ket qua tuong duong: true
IDENTITY_FINISH: false
```

**Vì sao phép tổng hợp này đúng?**

1. Mỗi `Box::new` tạo ra bộ đếm mới với `lines=0`, `units=0`, `totalCents=0`. Đó là **trạng thái trung hòa**.
2. `Box::accept` tăng bộ đếm dòng, cộng số lượng và cộng `quantity × unitPriceCents` của **chính dòng đó**; `Box::merge` cộng **cùng ba đại lượng**, không dùng quy tắc khác.
3. Cộng các tổng tạm có tính kết hợp trong miền giá trị hợp lệ; `Math.addExact` và `Math.multiplyExact` báo lỗi nếu vượt phạm vi `long`, tránh tạo giá trị sai âm thầm.
4. Đối tượng `Box` có thể thay đổi, nhưng mỗi lời gọi supplier tạo đối tượng riêng. Collector **không** có `CONCURRENT`; quá trình collect song song vẫn có thể an toàn nhờ các vùng chứa con được cô lập theo hợp đồng Stream.
5. `Summary` là kết quả chỉ đọc về mặt trạng thái; `equals`/`hashCode` cho phép xác minh hai kết quả độc lập tương đương. Collector có **finisher chuyển kiểu** từ `Box` sang `Summary` nên không được đánh dấu `IDENTITY_FINISH`.
6. Chương trình dùng bộ dữ liệu nhỏ để dễ kiểm tra: `2+3+1+4+1=11` đơn vị; tổng số cent là `2×1550 + 3×200 + 1×4900 + 4×1550 + 1×200 = 15000`.

## 6. Chẩn đoán Collector sai: vì sao test tuần tự chưa đủ

### Sai 1: supplier tạo sẵn dữ liệu tính phí

```java
// Sai nếu "100 cent" chỉ được cộng một lần cho toàn bộ tập:
() -> {
    Box b = new Box();
    b.totalCents = 100;
    return b;
}
```

Mỗi nhánh có thể được cấp một `Box` như vậy; `merge` sẽ cộng lại nhiều khoản `100`. Sửa bằng `supplier` trạng thái rỗng, rồi cộng phí một lần khi kết thúc nếu thật sự cần.

### Sai 2: accumulator cộng, combiner bỏ bớt

```java
// Sai: accumulator cong units, nhung combiner khong cong units.
(left, right) -> {
    left.lines += right.lines;
    left.totalCents += right.totalCents;
    return left;
}
```

Với một `Box`, `units` được cộng đủ. Khi kết hợp nhiều `Box`, số đơn vị từ nhánh bên phải mất đi. Điều này phá vỡ yêu cầu **kết quả sau chia nhóm phải tương đương kết quả không chia nhóm**.

### Sai 3: lấy “trung bình của các trung bình”

```java
// Sai khi hai nhom co so phan tu khac nhau:
(leftAverage, rightAverage) -> (leftAverage + rightAverage) / 2.0
```

Giải pháp là lưu `sum` và `count` trong trạng thái `A`, gộp hai cặp bằng **cộng sum và cộng count**, rồi tính trung bình tại finisher. Nếu không có phần tử, phải quyết định biểu diễn kết quả rỗng (ví dụ `OptionalDouble.empty()` hoặc một DTO có `count=0`) thay vì tùy tiện chia cho `0`.

### Sai 4: chia sẻ chung vùng chứa tích lũy

```java
// Sai: supplier trả về cùng một danh sách có thể thay đổi.
List<String> shared = new ArrayList<>();
Supplier<List<String>> supplier = () -> shared;
```

Supplier cần trả một danh sách **mới** mỗi lần: `ArrayList::new`. Một collector không có `CONCURRENT` vẫn được dùng trên parallel stream vì thư viện quản lý các container riêng cho mỗi nhánh; nếu chính ta cho nhiều nhánh cùng dùng `shared` thì phá vỡ sự cô lập.

### Sai 5: phụ thuộc thứ tự gọi hoặc tác dụng phụ

Không nên tăng biến đếm ngoài collector trong `accumulator`, sửa chính dữ liệu nguồn khi stream đang duyệt, hoặc trông đợi `combiner` luôn gọi một lần. Những hành vi này dễ khiến kết quả phụ thuộc triển khai/độ song song. Tránh side effect và giữ phép gộp có ngữ nghĩa xác định.

## 7. Luật đồng nhất khác `IDENTITY_FINISH`

Tên gọi gần nhau nhưng **không cùng khái niệm**:

- **Identity constraint:** ghép kết quả tạm với vùng chứa rỗng phải cho kết quả tương đương. *Mọi collector hợp lệ đều phải thỏa luật này.*
- **`Collector.Characteristics.IDENTITY_FINISH`:** finisher là hàm đồng nhất, kiểu `A` có thể được trả trực tiếp như `R`. Đây là **thông tin mô tả/đặc tính** để thư viện có thể bỏ qua bước finisher. Chỉ khai báo khi thật sự đúng.
- **`Collector.Characteristics.UNORDERED`:** kết quả không cam kết thứ tự theo encounter order; không đánh dấu nếu kết quả yêu cầu thứ tự phần tử giống nguồn.
- **`Collector.Characteristics.CONCURRENT`:** accumulator có thể được gọi đồng thời trên *cùng* một vùng chứa. Chỉ đánh dấu khi vùng chứa và phép cập nhật chịu được truy cập đồng thời theo hợp đồng.

Ví dụ collector danh sách có thể trả luôn `ArrayList`, không cần chuyển kiểu:

```java
Collector<String, ?, List<String>> listCollector = Collector.of(
    ArrayList::new,
    List::add,
    (left, right) -> {
        left.addAll(right);
        return left;
    }
);
// Dạng of(supplier, accumulator, combiner) có IDENTITY_FINISH.
```

Còn collector `Box -> Summary` ở mục 5 **không có** `IDENTITY_FINISH`, bởi `Box` và `Summary` là hai kiểu khác nhau và finisher có công việc thật.

## 8. Liên hệ với `reduce` và một checklist kiểm thử

Với `Stream.reduce(identity, accumulator)`, *identity* là một **giá trị trung hòa** cho phép gộp, ví dụ `0` với phép cộng. Với `Collector`, trạng thái trung hòa thường là **vùng chứa mới từ supplier**, và phải tính đến sự tương thích giữa accumulator và combiner. Không nên chuyển thuật toán dùng `Box` biến đổi tại chỗ sang `reduce` với một giá trị khởi tạo mutable chia sẻ; `collect` chính là API dành cho mutable reduction.

Khi tự thiết kế collector, hãy tự đối chiếu:

1. **Rỗng:** `supplier.get()` có tạo được trạng thái rỗng có ý nghĩa, mỗi lần là vùng chứa độc lập?
2. **Đồng nhất:** `combine(a, empty)` có giữ nguyên kết quả cuối của `a`? Với phép tổng hợp này, `combine(empty,a)` cũng vậy?
3. **Kết hợp:** `combine(combine(a,b),c)` có tương đương `combine(a,combine(b,c))` về `R`?
4. **Tương thích:** gom `t1,t2` trong một vùng chứa có cùng kết quả với gom thành hai vùng rồi hợp nhất?
5. **Finisher:** có tạo kết quả cuối đúng kiểu, xử lý trường hợp rỗng, và không bị gắn `IDENTITY_FINISH` sai?
6. **Song song:** có tránh trạng thái chia sẻ, side effect, thứ tự thực thi ngẫu nhiên và khai báo `CONCURRENT` thiếu cơ sở?
7. **Dữ liệu biên:** trường hợp tràn số, `null`, dữ liệu âm/không hợp lệ và sai số làm tròn có chính sách rõ ràng?
8. **Kiểm thử:** đã thử tập rỗng, một phần tử, nhiều partition, tuần tự/song song, và so sánh **giá trị** thay vì tham chiếu?

Kiểm thử tự động cho vài cách chia nhóm là hữu ích nhưng không thay cho việc chứng minh bằng ý nghĩa của phép gộp. Với phép **cộng số đếm và tổng tiền kiểu số nguyên trong miền cho phép**, trạng thái `(lines, units, totalCents)` gộp theo từng trường là một mô hình dễ lập luận và kiểm chứng.

## 9. Tài liệu chính thức

Các quy tắc và API trong bài xuất hiện từ Java 8 và vẫn được duy trì trong Java hiện đại:

- [`Collector<T,A,R>` — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Collector.html): định nghĩa chính thức của identity constraint, associativity constraint, supplier/accumulator/combiner/finisher và characteristics.
- [`Collector.Characteristics` — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Collector.Characteristics.html): `CONCURRENT`, `UNORDERED`, `IDENTITY_FINISH`.
- [`Stream.collect` — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Stream.html): yêu cầu với mutable reduction tuần tự và song song.
- [`Collectors` — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Collectors.html): những collector sẵn có nên ưu tiên dùng khi chúng đã thể hiện đủ yêu cầu.
