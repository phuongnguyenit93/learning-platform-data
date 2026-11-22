# Kiểm tra Collector tùy chỉnh với nguồn rỗng, chia nhóm và thực thi song song

## Mục tiêu

Một `Collector` có thể đúng khi `stream()` chạy tuần tự trên ba bản ghi nhưng sai khi nguồn rỗng, khi Stream được chia thành các phần hoặc khi chạy `parallelStream()`. Nguyên nhân thường nằm ở `supplier` không tạo trạng thái trung hòa, `combiner` bỏ sót dữ liệu, các nhánh chia sẻ một accumulator mutable, hoặc công bố sai `Collector.Characteristics`.

Bài này kiểm tra một Collector tùy chỉnh thực sự bằng Java 17. Sau khi học, bạn có thể xác định `Collector<T,A,R>`, kiểm thử empty/singleton, chủ động ghép hai vùng tích lũy, dùng Collector làm downstream của `groupingBy`, so sánh tuần tự/song song, đánh giá finisher và characteristics, và xây bộ kiểm thử có expected result độc lập.

## 1. Hợp đồng của Collector.of

Một Collector có ba kiểu:

- `T`: phần tử đầu vào, ví dụ `Sale`.
- `A`: vùng tích lũy trung gian, ví dụ một `Accumulator` có các trường mutable.
- `R`: kết quả cuối, ví dụ record `Report` có Map kết quả không cho sửa.

Dạng factory có finisher:

```java
Collector.of(supplier, accumulator, combiner, finisher)
```

Các chức năng và chức năng hàm:

| Thành phần | Functional interface | Điều cần kiểm thử |
| --- | --- | --- |
| `supplier` | `Supplier<A>` | Mỗi lần tạo vùng `A` **mới**, ban đầu trung hòa |
| `accumulator` | `BiConsumer<A,T>` | Đưa từng phần tử T vào A chính xác |
| `combiner` | `BinaryOperator<A>` | Kết hợp hai A, trả A đã gộp và không mất dữ liệu |
| `finisher` | `Function<A,R>` | Chuyển A sang R đúng kiểu và hợp đồng |
| `characteristics` | Các thuộc tính của Collector | Chỉ công bố điều thực sự bảo đảm |

**Phân biệt API:** `Collector.of` nhận combiner kiểu `BinaryOperator<A>` **trả về A**; overload `Stream.collect(supplier, accumulator, combiner)` nhận combiner kiểu `BiConsumer<R,R>` trả `void`. Không dùng sai hai hợp đồng này.

Các bất biến quan trọng: trạng thái từ supplier phải trung hòa khi gộp; accumulator và combiner phải tương thích; kết quả quan sát được phải tương đương khi phân chia nguồn theo những cách hợp lệ; không phụ thuộc side effect bên ngoài hoặc state dùng chung không kiểm soát.

## 2. Thiết kế dữ liệu và kết quả kỳ vọng

Mô hình dùng hai record:

```java
record Sale(String channel, String region, int units, long unitPriceCents) {}

record Report(long count, long units, long revenueCents,
              SortedMap<String, Long> unitsByRegion) {}
```

Trong chương trình đầy đủ, có năm Sale:

| Channel | Region | Units | Price (cents) | Revenue (cents) |
| --- | --- | ---: | ---: | ---: |
| web | north | 2 | 1250 | 2500 |
| store | south | 1 | 600 | 600 |
| web | north | 3 | 200 | 600 |
| store | west | 4 | 400 | 1600 |
| web | south | 2 | 750 | 1500 |

Kết quả phải là **count=5, units=12, revenueCents=6800, unitsByRegion={north=5, south=3, west=4}**. Đây là *oracle* tính trực tiếp từ đầu vào, độc lập với Collector. Nếu chỉ kiểm tra parallel bằng sequential, hai cách có thể cùng sai do cùng dùng một công thức lỗi.

Khi nhóm theo `channel`:

- `store`: count=2, units=5, revenueCents=2200, region `{south=1, west=4}`.
- `web`: count=3, units=7, revenueCents=4600, region `{north=5, south=2}`.

Hãy kiểm tra cả từng nhóm; chỉ cộng tổng các nhóm vẫn có thể che lỗi classifier gán sai phần tử.

## 3. Accumulator và các lỗi phải phát hiện

Accumulator gồm count, units, doanh thu và `TreeMap<String,Long>`. Khi thêm một Sale:

```java
void add(Sale sale) {
    count++;
    units += sale.units();
    revenueCents += (long) sale.units() * sale.unitPriceCents();
    byRegion.merge(sale.region(), (long) sale.units(), Long::sum);
}
```

Khi kết hợp hai nhánh:

```java
Accumulator combine(Accumulator other) {
    count += other.count;
    units += other.units;
    revenueCents += other.revenueCents;
    other.byRegion.forEach((key, value) ->
            byRegion.merge(key, value, Long::sum));
    return this;
}
```

Từng trường phải được gộp. Nếu combiner chỉ cộng `revenueCents` mà quên `count` hoặc `byRegion`, kiểm thử tuần tự có thể đạt còn kiểm thử chia chunk sẽ sai. Trong ví dụ, `TreeMap` làm đầu ra có thứ tự khóa xác định; `Map.equals` dùng để so kết quả theo entry, không phụ thuộc thứ tự thread thực thi.

Finisher:

```java
Report finish() {
    return new Report(count, units, revenueCents,
            Collections.unmodifiableSortedMap(new TreeMap<>(byRegion)));
}
```

Bản sao `TreeMap` tách dữ liệu kết quả khỏi accumulator mutable. Wrapper ngăn sửa Map qua `Report`. Đây là **bất biến nông**: với giá trị Map là `Long` bất biến thì phù hợp, nhưng nếu value là object mutable vẫn phải xem xét deep copy.

### Supplier phải tạo container mới

**Đúng:** `Accumulator::new`.

**Sai về hợp đồng:**

```java
Accumulator shared = new Accumulator();
// Không dùng: mọi lần supplier gọi đều trả cùng một object.
() -> shared
```

Khi chạy song song, những nhánh có thể sửa cùng object, gây race và combiner thậm chí có thể nhận hai tham chiếu đến cùng trạng thái. Dùng container có `synchronized` cũng không tự sửa lỗi identity/combiner.

### Combiner phải thực sự gộp

Sai: `(left,right) -> left` — không có tác dụng thêm dữ liệu của right. Dạng này có thể biên dịch và vượt qua test tuần tự khi combiner không bị gọi. Vì vậy **tạo hai accumulator riêng và gọi combiner trong test** là điều cần thiết.

## 4. Kiểm thử empty và singleton

Bắt đầu từ nguồn rỗng:

```java
Report empty = List.<Sale>of().stream().collect(reportCollector());
```

Expected:

```text
Report[count=0, units=0, revenueCents=0, unitsByRegion={}]
```

Không có Sale nào được tích lũy. Supplier phải tạo một trạng thái hợp lệ, finisher xử lý được trạng thái rỗng, và không được giả định có phần tử để gọi `get(0)`, `max().get()`, hoặc lấy key đầu tiên.

Với một Sale `("web","north",2,1250)`, expected là count=1, units=2, revenue=2500, region north=2. Empty phát hiện lỗi identity/finisher; singleton giúp kiểm tra `accumulator` trước khi đưa combiner vào bài toán.

**Nhận xét khi dùng groupingBy:** trực tiếp collect nguồn rỗng trả một `Report` rỗng, nhưng `emptyStream.collect(groupingBy(channel, downstream))` trả **Map rỗng** vì không có key nào xuất hiện. Không tự có entry `store -> Report rỗng` nếu ứng dụng không bổ sung tập khóa mong muốn.

## 5. Kiểm thử combiner bằng cách chia dữ liệu

Tạo helper:

```java
static Accumulator accumulate(List<Sale> sales) {
    Accumulator acc = new Accumulator();
    sales.forEach(acc::add);
    return acc;
}
```

Tách năm Sale thành 2 và 3:

```java
Accumulator left = accumulate(sales.subList(0, 2));
Accumulator right = accumulate(sales.subList(2, sales.size()));
Report split = left.combine(right).finish();
Report sequential = sales.stream().collect(reportCollector());

System.out.println(split.equals(sequential)); // true
```

Phần trái gồm count=2, units=3, revenue=3100; phần phải count=3, units=9, revenue=3700. `combine` phải cho count=5, units=12, revenue=6800 và Map north=5/south=3/west=4. Nếu bỏ phần phải, count chỉ là 2.

Mở rộng kiểm thử: chia 0+n, 1+(n-1), nhiều mảnh có khóa trùng ở các mảnh, và ba mảnh `a,b,c` để so `combine(combine(a,b),c)` với `combine(a,combine(b,c))`. **Phải tạo lại các accumulator mới cho hai vế**, vì combine của bài sửa container bên trái. So sánh `finish` theo giá trị, không so object identity.

Phép cộng số nguyên có giới hạn kiểu. Nếu dùng `double`, thứ tự phép cộng có thể thay đổi sai số; khi đó cần tiêu chí chênh lệch chấp nhận được, không luôn yêu cầu kết quả bit-for-bit bằng nhau.

## 6. Kiểm thử groupingBy với Collector downstream

Đặt Collector tùy chỉnh vào `groupingBy`:

```java
Map<String, Report> byChannel = sales.stream().collect(
        Collectors.groupingBy(
                Sale::channel, TreeMap::new, reportCollector()
        )
);
```

`Sale::channel` quyết định khóa nhóm. `TreeMap::new` bảo đảm Map key được duyệt theo thứ tự tự nhiên trong ví dụ. `reportCollector()` thu riêng từng nhóm thành `Report`.

Kiểm tra `byChannel.keySet()` chứa `store` và `web`, sau đó so `units`, `count`, `revenueCents` và `unitsByRegion` **cho từng Report**. Không chỉ kiểm tra số nhóm hoặc tổng toàn bộ.

Hai khái niệm “chia nhóm” cần phân biệt:

1. **Nhóm nghiệp vụ**: classifier chia theo channel, sản phẩm, khu vực.
2. **Phân đoạn thực thi**: Stream runtime chia nguồn thành các chunk và dùng combiner ghép partial results.

Một Collector phải đúng trong **cả hai**. Với key thiếu, `Collectors.groupingBy` không cho classifier trả `null`, ngay cả khi Map factory dùng HashMap; cần normalize, dùng key trạng thái thiếu hoặc từ chối đầu vào đúng yêu cầu. Với region null trong `TreeMap` tự nhiên của accumulator, phép `merge` có thể ném NPE. Đừng bỏ qua các trường hợp này.

## 7. Kiểm thử song song và characteristics

So sánh kết quả:

```java
Report sequential = sales.stream().collect(reportCollector());
Report parallel = sales.parallelStream().collect(reportCollector());

boolean same = parallel.equals(sequential);
```

Lặp nhiều bộ dữ liệu và phân hoạch khác nhau tốt hơn chỉ chạy một lần. Lặp cùng test 20 lần tăng cơ hội quan sát lỗi nhưng **không chứng minh** Collector an toàn với mọi lịch chạy. Test còn phải dựa trên expected value độc lập.

Với nhóm, so:

```java
Map<String, Report> seqGroups = sales.stream()
        .collect(Collectors.groupingBy(
                Sale::channel, TreeMap::new, reportCollector()));
Map<String, Report> parGroups = sales.parallelStream()
        .collect(Collectors.groupingBy(
                Sale::channel, TreeMap::new, reportCollector()));

boolean groupedSame = seqGroups.equals(parGroups);
```

So sánh Map theo giá trị thay vì so log thứ tự callback. Không được giả định `supplier` được gọi đúng một số lần cố định, hoặc các thread thực hiện `accumulator` theo encounter order.

Collector trong ví dụ **không công bố** `CONCURRENT`, `UNORDERED` hay `IDENTITY_FINISH`. Vì `Accumulator` có `TreeMap` và các biến `long` mutable, không an toàn để nhiều thread sửa cùng container; vì finisher chuyển `Accumulator` sang `Report`, không có identity finish. **Không cần `CONCURRENT` để được dùng với `parallelStream`**: runtime có thể cấp accumulator riêng cho các phần và gộp qua combiner.

Không khai báo `Collector.Characteristics.CONCURRENT` chỉ để “tăng tốc”; đó là hợp đồng về khả năng cập nhật một result container đồng thời, không phải nút bật chế độ song song. Nếu muốn Collector concurrent thật, phải thiết kế accumulator đồng thời an toàn và kiểm thử kỹ.

## 8. Chương trình Java 17 đầy đủ

Tạo tệp **`CustomCollectorValidationDemo.java`**:

```java
import java.util.Collections;
import java.util.List;
import java.util.Map;
import java.util.SortedMap;
import java.util.TreeMap;
import java.util.stream.Collector;
import java.util.stream.Collectors;

public class CustomCollectorValidationDemo {
    record Sale(String channel, String region,
                int units, long unitPriceCents) {}

    record Report(long count, long units, long revenueCents,
                  SortedMap<String, Long> unitsByRegion) {}

    static final class Accumulator {
        long count;
        long units;
        long revenueCents;
        final TreeMap<String, Long> byRegion = new TreeMap<>();

        void add(Sale sale) {
            count++;
            units += sale.units();
            revenueCents += (long) sale.units() * sale.unitPriceCents();
            byRegion.merge(sale.region(), (long) sale.units(), Long::sum);
        }

        Accumulator combine(Accumulator other) {
            count += other.count;
            units += other.units;
            revenueCents += other.revenueCents;
            other.byRegion.forEach((key, value) ->
                    byRegion.merge(key, value, Long::sum));
            return this;
        }

        Report finish() {
            return new Report(count, units, revenueCents,
                    Collections.unmodifiableSortedMap(
                            new TreeMap<>(byRegion)));
        }
    }

    static Collector<Sale, Accumulator, Report> reportCollector() {
        return Collector.of(
                Accumulator::new,
                Accumulator::add,
                Accumulator::combine,
                Accumulator::finish
        );
    }

    static Accumulator accumulate(List<Sale> sales) {
        Accumulator acc = new Accumulator();
        sales.forEach(acc::add);
        return acc;
    }

    public static void main(String[] args) {
        List<Sale> sales = List.of(
                new Sale("web", "north", 2, 1_250),
                new Sale("store", "south", 1, 600),
                new Sale("web", "north", 3, 200),
                new Sale("store", "west", 4, 400),
                new Sale("web", "south", 2, 750)
        );

        Report empty = List.<Sale>of().stream()
                .collect(reportCollector());
        Report sequential = sales.stream()
                .collect(reportCollector());
        Report parallel = sales.parallelStream()
                .collect(reportCollector());

        Accumulator left = accumulate(sales.subList(0, 2));
        Accumulator right = accumulate(sales.subList(2, sales.size()));
        Report split = left.combine(right).finish();

        Map<String, Report> groupedSequential = sales.stream().collect(
                Collectors.groupingBy(
                        Sale::channel, TreeMap::new, reportCollector()));
        Map<String, Report> groupedParallel = sales.parallelStream().collect(
                Collectors.groupingBy(
                        Sale::channel, TreeMap::new, reportCollector()));

        boolean allParallelMatch = true;
        for (int i = 0; i < 20; i++) {
            if (!sequential.equals(
                    sales.parallelStream().collect(reportCollector()))) {
                allParallelMatch = false;
                break;
            }
        }

        System.out.println("Empty: " + empty);
        System.out.println("Sequential: " + sequential);
        System.out.println("Parallel equals sequential: "
                + parallel.equals(sequential));
        System.out.println("Split equals sequential: "
                + split.equals(sequential));
        System.out.println("Repeated parallel matches: " + allParallelMatch);
        System.out.println("Channels: " + groupedSequential.keySet());
        System.out.println("Store units: "
                + groupedSequential.get("store").units());
        System.out.println("Web units: "
                + groupedSequential.get("web").units());
        System.out.println("Grouped parallel matches: "
                + groupedParallel.equals(groupedSequential));
        System.out.println("IDENTITY_FINISH: " + reportCollector()
                .characteristics().contains(
                        Collector.Characteristics.IDENTITY_FINISH));
        System.out.println("CONCURRENT: " + reportCollector()
                .characteristics().contains(
                        Collector.Characteristics.CONCURRENT));
        try {
            sequential.unitsByRegion().put("east", 7L);
        } catch (UnsupportedOperationException e) {
            System.out.println("Result map modifiable: false");
        }

        Accumulator incomplete = accumulate(sales.subList(0, 2));
        System.out.println("Missing combiner loses records: "
                + (incomplete.finish().count() < sequential.count()));
    }
}
```

Biên dịch và chạy:

```bash
javac CustomCollectorValidationDemo.java
java CustomCollectorValidationDemo
```

**Stdout chính xác** (đã chạy với `javac --release 17`):

```text
Empty: Report[count=0, units=0, revenueCents=0, unitsByRegion={}]
Sequential: Report[count=5, units=12, revenueCents=6800, unitsByRegion={north=5, south=3, west=4}]
Parallel equals sequential: true
Split equals sequential: true
Repeated parallel matches: true
Channels: [store, web]
Store units: 5
Web units: 7
Grouped parallel matches: true
IDENTITY_FINISH: false
CONCURRENT: false
Result map modifiable: false
Missing combiner loses records: true
```

Dòng cuối là **thí nghiệm âm tính**: cố tình chỉ lấy hai Sale đầu và so số record với kết quả đủ năm Sale. Nó chứng minh test có thể phát hiện phần dữ liệu bị bỏ sót, không nói Collector đúng đã làm mất dữ liệu. `Report` là record nên phép `equals` so các trường theo giá trị; `SortedMap.equals` so nội dung Map.

Ví dụ dùng giá trị cố định, không dùng I/O, có tên file trùng public class và không cần thư viện ngoài Java 17.

## 9. Ma trận test cần có trong dự án

| Tình huống | Dữ liệu thử | Expected |
| --- | --- | --- |
| Nguồn rỗng | 0 Sale | Report count=0, units=0, revenue=0, Map rỗng |
| Một phần tử | Sale đầu tiên | Count=1, units=2, revenue=2500, north=2 |
| Tuần tự | 5 Sale | Count=5, units=12, revenue=6800 |
| Chunk rỗng + đầy | 0+5 phần tử | Kết quả vẫn như nguồn đầy |
| Chunk 2+3 | Hai accumulator riêng | `left.combine(right)` bằng sequential |
| Nhiều chunk | 1+1+3; 2+1+2 | Mọi cách ghép hợp lệ tương đương |
| Duplicate key | north ở cả hai chunk | north được cộng thành 5 |
| groupingBy | store/web | Store units=5, web units=7 |
| groupingBy parallel | Như trên | Mọi Report theo key khớp |
| Song song lặp | Nhiều lần và nhiều input | Không khác oracle |
| Result immutability | Gọi put trên Map Report | UnsupportedOperationException |
| Characteristics | Kiểm tra Collector | Không tuyên bố CONCURRENT/IDENTITY_FINISH |
| Dữ liệu lỗi | region null, Sale null | Xử lý hoặc báo lỗi đúng hợp đồng |

### Độ phủ cần ưu tiên

Nếu sequential đúng nhưng parallel sai, kiểm tra `supplier` có trả cùng object không, `combiner` có bỏ dữ liệu không, các trường thống kê có được gộp hết không, và có dùng state ngoài không. Nếu cả hai sai, kiểm tra phép tính ở `accumulator` cùng oracle. Nếu chỉ `groupingBy` sai, kiểm tra classifier/key, trạng thái null, thứ tự và downstream.

Đừng chỉ so tổng toàn cục: một phân nhóm sai vẫn có thể bảo toàn tổng. Kiểm tra cả từng key, từng Report và số bản ghi.

## 10. Anti-pattern và các giới hạn thực tế

### 10.1. Combiner bỏ dữ liệu

Sai:

```java
(left, right) -> left
```

Sửa bằng cách gộp mọi trường và trả lại kết quả gộp. Chỉ test tuần tự có thể không gọi combiner, nên kiểm thử split thủ công là bắt buộc nếu muốn phát hiện lỗi này chắc chắn.

### 10.2. Khởi tạo sai identity

Nếu `Accumulator` bắt đầu `count=1`, nguồn rỗng đã sai. Khi chạy song song, mỗi nhánh có thể bắt đầu từ count=1, khiến tổng còn sai nhiều hơn. Supplier phải tạo trạng thái trung hòa.

### 10.3. Sử dụng object chia sẻ

Không để một `Accumulator` static/captured được trả về ở mọi lần gọi supplier. Một `AtomicLong` bên ngoài cũng không nên thay thế trường `count` bên trong Report, vì kết quả có thể phụ thuộc số lần chạy lại pipeline. Mutable reduction đúng là **sửa vùng riêng được quản lý trong phép collect**, không tùy tiện sửa state ngoài.

### 10.4. Tính kết hợp và giá trị số

`combine` cần associative theo ngữ nghĩa của kết quả. Phép trừ thông thường không associative; dùng nó để kết hợp nhiều chunk sẽ cho kết quả tùy cách nhóm. Với số `double`, sai số làm tròn có thể phụ thuộc thứ tự cộng; cần kiểm thử bằng ngưỡng sai số chấp nhận được và quyết định loại số theo nghiệp vụ. Ví dụ dùng `long` nhưng vẫn có rủi ro overflow; nếu dữ liệu có thể lớn, dùng `Math.addExact`/`multiplyExact` hoặc kiểu số rộng hơn.

### 10.5. Null, ngoại lệ và tài nguyên

`Sale` null làm accumulator dereference null. `TreeMap` với thứ tự tự nhiên không chấp nhận region null. `groupingBy` không chấp nhận classifier trả null. Cần chính sách validate, normalize hoặc loại bản ghi rõ ràng trước khi collect.

Các functional interface tiêu chuẩn không khai báo checked exception trong `accept/apply`; I/O trong callback cần được xử lý theo hợp đồng. `collect` cũng không tự đóng nguồn từ `Files.lines`; dùng `try-with-resources` khi nguồn giữ tài nguyên.

### 10.6. Hiệu năng

Collector có thể đúng ở parallel nhưng chậm hơn sequential vì phải tạo nhiều accumulator và hợp nhất các Map. Với nguồn nhỏ, parallel thường không đáng chi phí điều phối. Khi chỉ cần số liệu tổng, accumulator nhỏ tránh phải giữ cả danh sách Sale trong bộ nhớ; nhưng `byRegion` vẫn tăng theo số khóa khác nhau.

## 11. Bài tập

1. Vì sao empty stream phải trả Report có tất cả trường 0 và Map rỗng?
2. Tạo test singleton với Sale đầu tiên. Expected `count`, `units`, `revenue` và region là gì?
3. Tại sao `(left,right) -> left` có thể vượt qua test tuần tự nhưng sai khi chia chunk?
4. Viết test chia nguồn thành 1 và 4 phần tử; so kết quả với sequential.
5. Viết test ghép ba Accumulator theo hai cách đặt ngoặc; lưu ý điều gì khi `combine` sửa left?
6. Dùng `groupingBy(Sale::channel, TreeMap::new, reportCollector())`. Tính giá trị store/web.
7. Nếu cả sequential và parallel cùng cho doanh thu 7000 thay vì 6800, vì sao chỉ so hai kết quả với nhau không đủ?
8. Vì sao không đánh dấu `IDENTITY_FINISH` khi finisher trả Report?
9. Vì sao `parallelStream()` không bắt buộc một Collector phải `CONCURRENT`?
10. Nếu region null, có thể gặp lỗi gì ở TreeMap? Chọn một chính sách xử lý dữ liệu.
11. Một combiner chỉ gộp `revenueCents`. Test nào phát hiện những trường còn lại sai?
12. Report chứa `SortedMap` mutable. Làm cách nào tránh caller sửa cấu trúc và accumulator rò rỉ state?
13. Với dữ liệu mới, làm sao kiểm tra groupingBy đặt đúng từng Sale vào nhóm, không chỉ bảo toàn tổng?
14. Vì sao lặp 20 lần song song chưa chứng minh Collector đúng tuyệt đối?

**Đáp án gợi ý:** (1) Supplier tạo identity; không có phần tử vẫn phải có kết quả hợp lệ. (2) 1, 2, 2500, north=2. (3) Không gộp right; tuần tự có thể không gọi combiner. (4) Tạo hai accumulator độc lập rồi `combine`. (5) Tạo lại accumulator cho mỗi vế để tránh mutation từ phép thử trước. (6) store count2/units5/revenue2200, web count3/units7/revenue4600. (7) Cần oracle độc lập. (8) A và R khác nhau, phải chạy finisher. (9) Framework có thể dùng container độc lập rồi gộp. (10) NPE; validate hoặc key trạng thái thiếu không null. (11) Kiểm tra count, units và byRegion của split/parallel. (12) Copy TreeMap rồi bọc `unmodifiableSortedMap`. (13) Assert key và toàn bộ Report cho từng nhóm. (14) Phạm vi test hữu hạn, cần nhiều input/phân hoạch/biên.

## Kết luận

Một **Collector tùy chỉnh đáng tin** không chỉ cho đúng một kết quả ở Stream tuần tự. Nó cần tạo identity hợp lệ với nguồn rỗng, tích lũy đúng từng phần tử, **gộp đầy đủ các vùng tích lũy** khi bị chia nhỏ, tạo kết quả đúng kiểu qua finisher và công bố characteristics chính xác.

Hãy kiểm tra empty, singleton, chunk split/merge, groupingBy downstream và parallel theo **giá trị quan sát được**; đối chiếu với expected result tính độc lập. Đó là cách phát hiện những lỗi supplier/combiner/state chia sẻ dễ bị che khuất trong một lần chạy tuần tự, đồng thời giúp Collector có thể tái sử dụng an toàn trong ứng dụng Java.
