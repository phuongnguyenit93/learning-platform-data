# Kiểm thử tính chất và tạo dữ liệu ngẫu nhiên có thể tái lập

Trong chương **Gỡ lỗi và kiểm thử pipeline** của **Java Stream API**, kiểm thử một vài ví dụ cố định là cần thiết nhưng chưa đủ. Một pipeline có thể chạy đúng với danh sách năm phần tử mà sai khi nguồn rỗng, có giá trị trùng, thứ tự thay đổi, kết quả nhiều nhóm hoặc chuyển từ `stream()` sang `parallelStream()`. Đặc biệt, lỗi của `reduce`, `collect`, bộ lọc, phép nhóm và thao tác có trạng thái thường xuất hiện ở **sự kết hợp dữ liệu** mà tác giả chưa nghĩ tới.

**Kiểm thử tính chất** (*property-based testing*) đặt câu hỏi khác kiểm thử ví dụ thông thường: thay vì chỉ kiểm tra một đầu vào và một kết quả định sẵn, ta xác định **điều luôn phải đúng** đối với một lớp đầu vào hợp lệ, rồi tạo nhiều bộ dữ liệu để tìm phản ví dụ. Việc tạo ngẫu nhiên phải **có thể tái lập**: khi phát hiện lỗi, lưu lại seed, cấu hình và dữ liệu gây lỗi để chạy lại chính xác, sửa mã và kiểm thử hồi quy.

Bài này hướng dẫn cách thiết kế bộ sinh dữ liệu dựa trên seed, xây *oracle* độc lập, kiểm tra bất biến và phép biến đổi bảo toàn tính chất, so sánh pipeline tuần tự/song song, thu nhỏ ca lỗi và tránh các bẫy ngẫu nhiên không ổn định. Ví dụ hoàn chỉnh sử dụng **Java 17+**, `SplittableRandom` và các API có sẵn trong JDK; không yêu cầu framework kiểm thử bổ sung.

## 1. Từ kiểm thử ví dụ đến kiểm thử tính chất

Một kiểm thử ví dụ có thể là:

~~~java
import java.util.List;

long count = List.of(1, 2, 3, 4).stream()
        .filter(n -> n % 2 == 0)
        .count();

if (count != 2L) {
    throw new AssertionError("Expected 2 even numbers");
}
~~~

Nó xác minh một trường hợp cụ thể: danh sách `[1,2,3,4]` có hai số chẵn. Nhưng vẫn còn nhiều trường hợp chưa được thử: danh sách rỗng, toàn số chẵn, toàn số lẻ, số trùng, số âm, số `0`, đầu vào rất lớn.

Có thể nâng mục tiêu thành một **tính chất**:

> Với mọi danh sách số nguyên hợp lệ, số lượng phần tử đi qua `filter(even)` bằng số phần tử chẵn khi đếm bằng một vòng lặp tham chiếu độc lập.

Tính chất đó có thể được kiểm tra trên hàng trăm danh sách được tạo tự động, thay vì viết thủ công hàng trăm `assert` riêng lẻ.

Một số nhóm tính chất hữu ích cho Stream API:

| Nhóm | Câu hỏi kiểm tra | Ví dụ |
| --- | --- | --- |
| **Bất biến kết quả** | Đầu ra có luôn tuân thủ ràng buộc? | Không có phần tử không thỏa `filter` |
| **Oracle tham chiếu** | Kết quả có bằng cách tính độc lập? | `groupingBy + summingLong` so với vòng lặp `for` |
| **Quan hệ biến hình** (*metamorphic*) | Đổi đầu vào theo một cách hợp lệ có giữ một đặc tính không? | Xáo thứ tự đầu vào không đổi tổng theo nhóm |
| **Luật đại số** | Phép gộp có thỏa identity/tính kết hợp? | Tổng hai đoạn bằng tổng cả dãy |
| **Tương đương thực thi** | Tuần tự và song song có cùng ý nghĩa không? | Cùng `Map<region, total>` |
| **Đường biên** | Trường hợp nhỏ nhất/cực trị có đúng không? | Stream rỗng, một phần tử, nhiều bản ghi trùng khóa |
| **Vòng đời nguồn** | Tài nguyên có đóng cả khi lỗi/dừng sớm? | `Files.lines` trong `try-with-resources` |

Không phải mọi pipeline đều phải thỏa tất cả tính chất trên. **Chọn tính chất từ yêu cầu nghiệp vụ và hợp đồng API**, không tự đặt một tính chất sai rồi coi mọi phản ví dụ là lỗi.

## 2. Đặc tả bài toán dùng xuyên suốt

Giả sử một hệ thống cần tổng hợp doanh thu theo vùng từ danh sách giao dịch:

~~~java
record Sale(
        String region,
        int units,
        long unitPriceCents
) {
    long totalCents() {
        return Math.multiplyExact((long) units, unitPriceCents);
    }
}
~~~

Một giao dịch có:

- `region`: mã vùng, trong tập `NORTH`, `SOUTH`, `CENTRAL`.
- `units`: số lượng đơn vị hàng, không âm.
- `unitPriceCents`: đơn giá theo **xu nguyên**, không âm.
- `totalCents`: thành tiền = số lượng × đơn giá, tính bằng `long`.

Chúng ta chủ động sử dụng số xu nguyên thay vì `double` để tránh sai số dấu phẩy động trong ví dụ tổng hợp tiền. `Math.multiplyExact` cho phép phát hiện tràn số khi đầu vào vượt giới hạn kiểu `long`.

Pipeline cần kiểm thử:

~~~java
Map<String, Long> totalsByRegion = sales.stream()
        .collect(Collectors.groupingBy(
                Sale::region,
                Collectors.summingLong(Sale::totalCents)
        ));
~~~

Yêu cầu kết quả:

1. Mỗi vùng có giao dịch xuất hiện **đúng một khóa** trong Map.
2. Giá trị của khóa là tổng thành tiền của **mọi giao dịch thuộc vùng đó**.
3. Giao dịch có thành tiền bằng 0 vẫn là giao dịch có mặt trong vùng; vùng đó có thể có tổng bằng 0.
4. Danh sách rỗng tạo Map rỗng.
5. Vì phép cộng số nguyên được giới hạn không tràn, tổng không phụ thuộc thứ tự duyệt hoặc cách chia dữ liệu.
6. `Map` không cần giữ thứ tự khóa; phép kiểm thử phải so **ánh xạ khóa–giá trị**, không so chuỗi được in từ `HashMap`.

Đây là hợp đồng cụ thể. Nếu nghiệp vụ cần loại đơn hủy, bổ sung điều kiện lọc vào cả pipeline lẫn oracle; nếu cho phép dữ liệu `null`, phải định nghĩa chính sách riêng thay vì mặc định bỏ qua.

## 3. Thiết kế bộ sinh dữ liệu: đúng miền, có giới hạn, có khả năng lặp lại

Nguồn ngẫu nhiên phải cho ra dữ liệu **nằm trong miền hợp lệ** của tính chất đang kiểm tra. Ví dụ:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.SplittableRandom;

static List<Sale> generateSales(long seed) {
    SplittableRandom random = new SplittableRandom(seed);
    String[] regions = {"NORTH", "SOUTH", "CENTRAL"};

    int count = random.nextInt(0, 201);
    List<Sale> result = new ArrayList<>(count);

    for (int i = 0; i < count; i++) {
        String region = regions[random.nextInt(regions.length)];
        int units = random.nextInt(0, 21);
        long price = random.nextLong(0L, 100_001L);

        result.add(new Sale(region, units, price));
    }

    return List.copyOf(result);
}
~~~

Với cùng `seed`, cùng thuật toán sinh và cùng môi trường thực thi, bộ sinh cho ra cùng trình tự lựa chọn. Miền dữ liệu được giới hạn có chủ đích:

| Thuộc tính | Miền sinh | Lý do |
| --- | --- | --- |
| Số giao dịch | Từ 0 đến 200 | Có thể sinh nguồn rỗng; bộ thử không tốn bộ nhớ lớn |
| Vùng | Ba mã cố định | Tạo khóa trùng để thử `groupingBy` |
| `units` | Từ 0 đến 20 | Có trường hợp tổng bằng 0 |
| `unitPriceCents` | Từ 0 đến 100.000 | Có giá trị 0 và giá trị lớn |
| Giá trị bản ghi | Không `null` | Tính chất đầu tiên tập trung trên dữ liệu hợp lệ |
| Thứ tự | Thứ tự sinh được giữ trong `List` | Có encounter order để thử các thao tác có thứ tự |

`nextInt(origin, bound)` và `nextLong(origin, bound)` sử dụng **cận trên loại trừ**. Vì vậy `nextInt(0, 201)` có thể tạo 200, còn `nextLong(0L, 100_001L)` có thể tạo 100.000.

Với tối đa 200 giao dịch, mỗi thành tiền không quá `20 × 100.000 = 2.000.000` xu, nên tổng tuyệt đối không quá 400.000.000 xu. Miền sinh này đủ nhỏ để các phép cộng `long` trong ví dụ không bị tràn. Kiểm thử xử lý overflow phải được thực hiện bằng **nhóm test riêng**, không trộn vào một tính chất đang giả định phép cộng hợp lệ.

### Vì sao không dùng Math.random()?

`Math.random()` không cho phép caller đặt một seed riêng cho từng ca kiểm thử theo cách tiện và rõ ràng như bộ sinh đối tượng. `ThreadLocalRandom.current()` cũng không thích hợp nếu mục tiêu là tái lập chính xác một ca bằng seed do test sở hữu.

`SplittableRandom(seed)` thuận tiện để tạo nhiều số có seed. Tuy nhiên, **seed không phải toàn bộ dữ liệu tái lập**: còn cần ghi rõ thuật toán sinh, khoảng giá trị, thứ tự gọi generator và phiên bản/cấu hình môi trường nếu muốn tái lập lâu dài giữa những hệ thống khác nhau.

Nếu cần một fixture **ổn định tuyệt đối giữa các JDK/toolchain**, hãy lưu lại chính danh sách đầu vào đã gây lỗi, thay vì chỉ dựa vào seed.

## 4. Ngẫu nhiên có thể tái lập khác với “mỗi lần chạy một dữ liệu mới”

Một cách tạo dữ liệu không thể tái lập tốt:

~~~java
// Không phù hợp để debug một ca lỗi đã xảy ra.
List<Integer> data = Stream.generate(
        () -> (int) (Math.random() * 100)
).limit(100).toList();
~~~

Nếu kiểm thử thất bại trên máy CI, lập trình viên có thể không tái tạo được đầu vào đã kích hoạt lỗi.

Thay vào đó, dùng một **seed gốc** và quy tắc suy ra seed cho từng lượt:

~~~java
long baseSeed = 20261118L;

for (int trial = 0; trial < 500; trial++) {
    long caseSeed = baseSeed + trial;
    List<Sale> data = generateSales(caseSeed);

    // Kiểm tra các tính chất trên data.
}
~~~

Để tái lập ca lỗi thứ 137, cần biết `caseSeed = 20261118 + 137` và chạy lại **đúng ca đó**. Đây là lý do mỗi lượt kiểm thử nên tự tạo một `SplittableRandom` mới, không chỉ dùng một generator chung chạy liên tục qua mọi lượt.

Những thứ nên ghi khi test thất bại:

- Tên tính chất bị vi phạm.
- `caseSeed` và số thứ tự lượt thử.
- Danh sách hoặc file chứa đầu vào tối thiểu.
- Kết quả mong đợi và kết quả thực tế.
- Phiên bản JDK, phiên bản mã và cấu hình quan trọng nếu lỗi chỉ xuất hiện ở môi trường cụ thể.

**Đừng chỉ in “Random test failed”.** Một ca lỗi mà không có seed và dữ liệu là ca lỗi khó tái lập, thường tốn thời gian điều tra hơn nhiều so với chính lỗi thuật toán.

## 5. Oracle độc lập: so Stream với vòng lặp dễ hiểu

Một `oracle` là cách tính tham chiếu đủ đơn giản để tin tưởng, độc lập ở mức hợp lý với code cần thử.

Ví dụ tính doanh thu theo vùng bằng vòng lặp:

~~~java
import java.util.HashMap;
import java.util.List;
import java.util.Map;

static Map<String, Long> referenceTotals(List<Sale> sales) {
    Map<String, Long> result = new HashMap<>();

    for (Sale sale : sales) {
        long amount = Math.multiplyExact(
                (long) sale.units(), sale.unitPriceCents());

        result.merge(
                sale.region(),
                amount,
                (left, right) -> Math.addExact(left, right)
        );
    }

    return result;
}
~~~

Oracle này không dùng `groupingBy` hoặc `summingLong`, nên nếu collector bị viết sai, phép so sánh có cơ hội phát hiện khác biệt.

Một số nguyên tắc khi xây oracle:

1. **Ưu tiên thuật toán dễ đọc hơn tốc độ.** Bộ dữ liệu kiểm thử nhỏ, không cần tối ưu oracle như pipeline sản xuất.
2. **Tránh dùng cùng một hàm có thể sai ở cả hai phía.** Ở đây oracle tự tính nhân thay vì gọi `Sale::totalCents`; giảm nguy cơ cả hai cùng che một lỗi.
3. **Dùng cùng đặc tả nghiệp vụ.** Nếu đầu ra bỏ giao dịch `units == 0`, oracle cũng phải làm như vậy.
4. **Kiểm tra oracle bằng fixture cố định.** Một oracle sai cũng có thể tạo kết luận sai về pipeline.
5. **Không phụ thuộc thứ tự duyệt Map.** `Map.equals` so đúng các cặp khóa–giá trị.

Ví dụ so sánh:

~~~java
Map<String, Long> expected = referenceTotals(sales);
Map<String, Long> actual = totalsByRegion(sales, false);

if (!expected.equals(actual)) {
    throw new AssertionError(
            "Expected=" + expected + ", actual=" + actual);
}
~~~

Trong đó `totalsByRegion(sales, false)` là hàm pipeline sẽ được định nghĩa trong chương trình hoàn chỉnh.

## 6. Các tính chất cần kiểm chứng cho phép tổng hợp

### 6.1. Tương đương với oracle

Với mọi danh sách `sales` trong miền hợp lệ:

~~~text
streamTotals(sales) == referenceTotals(sales)
~~~

Đây là tính chất mạnh nhất trong bài, vì nó so toàn bộ Map với phép tính tham chiếu.

### 6.2. Tổng theo nhóm bằng tổng toàn bộ dữ liệu

~~~text
sum(totalsByRegion.values())
    == sum(each sale.units * sale.unitPriceCents)
~~~

Bất biến giúp phát hiện bỏ sót hoặc đếm hai lần một giao dịch, miễn các tổng không tràn. Nhưng chỉ kiểm tra tổng chung **không đủ**: một giao dịch bị gán nhầm vùng có thể không làm thay đổi tổng cuối.

### 6.3. Hoán vị không làm đổi tổng theo vùng

Nếu chỉ quan tâm doanh thu theo vùng, thứ tự giao dịch không phải phần ngữ nghĩa kết quả:

~~~text
totalsByRegion(sales) == totalsByRegion(shuffle(sales))
~~~

Lưu ý, đây **không** phải tính chất đúng cho mọi pipeline. Ví dụ `findFirst`, `limit`, `takeWhile` và `joining` có thể phụ thuộc encounter order. Chỉ dùng tính chất hoán vị cho phép tổng hợp có hợp đồng **không phụ thuộc thứ tự**.

### 6.4. Tách dữ liệu rồi gộp báo cáo

Nếu chia danh sách làm hai đoạn liên tiếp `left` và `right`:

~~~text
aggregate(sales)
    == merge(aggregate(left), aggregate(right))
~~~

Hàm `merge` phải cộng tổng của cùng vùng. Tính chất này mô phỏng việc chia và kết hợp công việc trong Stream song song, giúp phát hiện các lỗi như combiner bỏ qua một nhánh hoặc dùng identity sai.

### 6.5. Tuần tự và song song phải cho cùng ý nghĩa

Với kiểu `long` và miền thử không tràn:

~~~text
sequentialTotals(sales) == parallelTotals(sales)
~~~

Không yêu cầu Map có cùng lớp triển khai, thứ tự duyệt khóa hay số luồng sử dụng. **Chỉ so nội dung theo khóa.**

### 6.6. Filter và map phải giữ đúng thứ tự trên nguồn có thứ tự

Giả sử cần danh sách thành tiền của các giao dịch thuộc `NORTH`:

~~~java
List<Long> northAmounts = sales.stream()
        .filter(s -> "NORTH".equals(s.region()))
        .map(Sale::totalCents)
        .toList();
~~~

Với nguồn `List` có encounter order, kết quả phải là dãy thành tiền **theo đúng thứ tự xuất hiện của các giao dịch `NORTH`**. Có thể kiểm tra bằng một vòng lặp riêng. Không được áp tính chất xáo thứ tự cho danh sách này nếu yêu cầu giữ encounter order.

## 7. Chương trình Java 17+ hoàn chỉnh, chạy không cần thư viện ngoài

Lưu đoạn mã dưới đây thành `StreamPropertyTest.java`. Nó tạo 500 bộ dữ liệu bằng seed, so pipeline với oracle, kiểm tra các bất biến, hoán vị, phép chia–gộp, chế độ song song và đường đi `filter/map`. Chương trình còn hỗ trợ **chạy lại đúng một seed** được truyền qua command line.

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Random;
import java.util.SplittableRandom;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class StreamPropertyTest {

    private static final String[] REGIONS = {
            "NORTH", "SOUTH", "CENTRAL"
    };

    record Sale(String region, int units, long unitPriceCents) {
        long totalCents() {
            return Math.multiplyExact(
                    (long) units, unitPriceCents);
        }
    }

    // Mỗi seed tạo một bộ dữ liệu độc lập, hữu hạn.
    static List<Sale> generate(long seed) {
        SplittableRandom random = new SplittableRandom(seed);
        int count = random.nextInt(0, 201);
        List<Sale> data = new ArrayList<>(count);

        for (int i = 0; i < count; i++) {
            String region = REGIONS[
                    random.nextInt(REGIONS.length)];
            int units = random.nextInt(0, 21);
            long unitPriceCents =
                    random.nextLong(0L, 100_001L);

            data.add(new Sale(
                    region, units, unitPriceCents));
        }
        return List.copyOf(data);
    }

    // Code cần kiểm thử: một pipeline có thể chạy
    // tuần tự hoặc song song với cùng thuật toán.
    static Map<String, Long> totalsByRegion(
            List<Sale> sales, boolean parallel) {

        Stream<Sale> source = parallel
                ? sales.parallelStream()
                : sales.stream();

        return source.collect(Collectors.groupingBy(
                Sale::region,
                Collectors.summingLong(Sale::totalCents)
        ));
    }

    // Oracle độc lập: không dùng groupingBy/summingLong.
    static Map<String, Long> referenceTotals(
            List<Sale> sales) {

        Map<String, Long> result = new HashMap<>();

        for (Sale sale : sales) {
            long amount = Math.multiplyExact(
                    (long) sale.units(),
                    sale.unitPriceCents());

            result.merge(
                    sale.region(),
                    amount,
                    (left, right) ->
                            Math.addExact(left, right)
            );
        }
        return result;
    }

    // Kết quả có encounter order, cần kiểm tra List.
    static List<Long> northAmounts(List<Sale> sales) {
        return sales.stream()
                .filter(s -> "NORTH".equals(s.region()))
                .map(Sale::totalCents)
                .toList();
    }

    static List<Long> referenceNorthAmounts(
            List<Sale> sales) {

        List<Long> result = new ArrayList<>();
        for (Sale sale : sales) {
            if ("NORTH".equals(sale.region())) {
                result.add(Math.multiplyExact(
                        (long) sale.units(),
                        sale.unitPriceCents()));
            }
        }
        return result;
    }

    // In đủ thông tin để tái tạo một lần thử.
    static void checkEqual(
            String property,
            Object expected,
            Object actual,
            long seed,
            List<Sale> data) {

        if (!Objects.equals(expected, actual)) {
            throw new AssertionError(
                    "Property: " + property
                    + "\nseed: " + seed
                    + "\ninput: " + data
                    + "\nexpected: " + expected
                    + "\nactual: " + actual
            );
        }
    }

    static void verify(long seed, List<Sale> sales) {
        Map<String, Long> expected =
                referenceTotals(sales);

        Map<String, Long> sequential =
                totalsByRegion(sales, false);

        Map<String, Long> parallel =
                totalsByRegion(sales, true);

        // Tính chất 1: khớp vòng lặp tham chiếu.
        checkEqual(
                "oracle", expected, sequential, seed, sales);

        // Tính chất 2: song song không đổi giá trị.
        checkEqual(
                "parallel", sequential, parallel, seed, sales);

        // Tính chất 3: đổi thứ tự không đổi tổng theo vùng.
        List<Sale> shuffled = new ArrayList<>(sales);
        Collections.shuffle(
                shuffled,
                new Random(seed ^ 0x5DEECE66DL)
        );

        checkEqual(
                "permutation",
                sequential,
                totalsByRegion(shuffled, false),
                seed,
                sales
        );

        // Tính chất 4: chia hai đoạn rồi gộp tương đương.
        int mid = sales.size() / 2;

        Map<String, Long> combined = new HashMap<>(
                totalsByRegion(sales.subList(0, mid), false)
        );

        Map<String, Long> second = totalsByRegion(
                sales.subList(mid, sales.size()), false
        );

        second.forEach((region, total) ->
                combined.merge(
                        region,
                        total,
                        (left, right) ->
                                Math.addExact(left, right)
                )
        );

        checkEqual(
                "split-and-merge",
                sequential,
                combined,
                seed,
                sales
        );

        // Tính chất 5: tổng các vùng == tổng giao dịch.
        long overall = 0L;
        for (Sale sale : sales) {
            overall = Math.addExact(
                    overall,
                    Math.multiplyExact(
                            (long) sale.units(),
                            sale.unitPriceCents())
            );
        }

        long groupedTotal = 0L;
        for (long value : sequential.values()) {
            groupedTotal = Math.addExact(
                    groupedTotal, value);
        }

        checkEqual(
                "conservation",
                overall,
                groupedTotal,
                seed,
                sales
        );

        // Tính chất 6: filter/map giữ encounter order.
        checkEqual(
                "ordered-filter-map",
                referenceNorthAmounts(sales),
                northAmounts(sales),
                seed,
                sales
        );
    }

    static void edgeCases() {
        // Không có giao dịch.
        verify(-1L, List.of());

        // Có giao dịch doanh thu bằng 0: phải giữ khóa.
        verify(-2L, List.of(
                new Sale("NORTH", 0, 100L)
        ));

        // Nhiều bản ghi cùng vùng, đơn giá bằng 0,
        // nhiều vùng và giá trị lớn nhưng không tràn.
        verify(-3L, List.of(
                new Sale("SOUTH", 20, 100_000L),
                new Sale("SOUTH", 20, 100_000L),
                new Sale("CENTRAL", 1, 0L),
                new Sale("NORTH", 1, 99L)
        ));
    }

    public static void main(String[] args) {
        // java StreamPropertyTest 12345
        // -> chỉ kiểm tra dữ liệu tạo bằng đúng seed 12345.
        if (args.length == 1) {
            long seed = Long.parseLong(args[0]);
            verify(seed, generate(seed));
            System.out.println("PASS seed=" + seed);
            return;
        }

        if (args.length != 0) {
            throw new IllegalArgumentException(
                    "Usage: java StreamPropertyTest [seed]");
        }

        edgeCases();

        long baseSeed = 20261118L;
        int trials = 500;

        for (int trial = 0; trial < trials; trial++) {
            long seed = baseSeed + trial;
            verify(seed, generate(seed));
        }

        System.out.println(
                "PASS fixed-cases and "
                + trials + " random cases"
                + "; baseSeed=" + baseSeed
        );
    }
}
~~~

Lệnh chạy:

~~~bash
javac --release 17 StreamPropertyTest.java
java StreamPropertyTest
~~~

Khi thành công:

~~~text
PASS fixed-cases and 500 random cases; baseSeed=20261118
~~~

Để chạy lại đúng một ca có `seed = 20261234`:

~~~bash
java StreamPropertyTest 20261234
~~~

Nếu thuộc tính thất bại, `AssertionError` in tên tính chất, seed và dữ liệu đầu vào; có thể dán seed vào command line để tái lập. Trong ví dụ, mỗi `Sale` là record bất biến và dữ liệu được tạo trước khi chạy pipeline; không có một nguồn ngẫu nhiên mutable bị nhiều tác vụ `parallelStream` cùng dùng.

**Lưu ý:** Đây là một *test harness* độc lập để học bản chất property-based testing, không phải thay thế toàn bộ JUnit hoặc framework quản lý test suite. Khi đưa vào dự án thực, hãy chuyển hàm kiểm tra thành test trong công cụ build đang dùng, để test runner báo lỗi, thống kê và lưu artifact thuận tiện.

## 8. Đọc kết quả: tại sao các tính chất trên hữu ích?

Một trường hợp kết quả kiểm thử có thể thất bại ở **chỉ một** tính chất:

| Tính chất lỗi | Khả năng cần điều tra |
| --- | --- |
| `oracle` | Sai logic gom nhóm, bộ lọc, phép nhân hoặc phép tổng |
| `parallel` | Accumulator/combiner không tương thích, dùng state chung, phụ thuộc thứ tự hoặc phép toán không kết hợp |
| `permutation` | Dùng toán tử phụ thuộc thứ tự dù yêu cầu tổng theo nhóm không phụ thuộc thứ tự |
| `split-and-merge` | Phép gộp hai phần không đúng, mất nhóm hoặc trùng nhóm |
| `conservation` | Bỏ sót hoặc nhân đôi giá trị; có thể gán sai vùng mà tổng vẫn đúng |
| `ordered-filter-map` | Làm mất encounter order hoặc chọn sai phần tử của vùng |

**Không có một tính chất nào đủ chứng minh toàn bộ chương trình đúng.** Ví dụ pipeline có thể cộng đúng tổng tiền nhưng gán mọi khoản vào vùng `NORTH`: bất biến tổng chung vẫn đúng, còn oracle theo từng vùng phát hiện lỗi.

Tương tự, so tuần tự với song song chỉ chứng minh hai cách thực thi **giống nhau trên bộ dữ liệu đã thử**. Nếu cả hai cùng sai một quy tắc nghiệp vụ, phép so đó sẽ không báo lỗi. Vì vậy cần kết hợp **oracle, bất biến, fixture cố định và quan hệ biến hình**.

## 9. Không dùng cùng một Stream cho nhiều phép thử

Một `Stream` thường chỉ được phép thực hiện **một terminal operation**. Nếu muốn kiểm tra nhiều tính chất trên cùng dữ liệu, giữ dữ liệu trong một `List` hoặc nguồn có thể mở lại, sau đó tạo Stream mới cho từng phép thử.

**Sai:**

~~~java
Stream<Integer> source = List.of(1, 2, 3).stream();

long count = source.count();
long sum = source.mapToLong(Integer::longValue).sum();
// Không thể tiếp tục sử dụng cùng source đã bị tiêu thụ.
~~~

**Đúng:**

~~~java
List<Integer> data = List.of(1, 2, 3);

long count = data.stream().count();
long sum = data.stream()
        .mapToLong(Integer::longValue)
        .sum();
~~~

Trong chương trình đầy đủ, mỗi lời gọi `totalsByRegion(...)` tạo một Stream mới từ `List<Sale>`. Vì `Sale` là immutable record và `List.copyOf` ngăn sửa cấu trúc danh sách, các phép thử trên cùng dữ liệu không vô tình tác động lẫn nhau.

Với một Stream gắn I/O như `Files.lines`, **không** được dùng lại Stream sau khi đóng. Nếu cần chạy nhiều thuật toán độc lập trên cùng một tệp, cần mở tệp lại trong các khối `try-with-resources` riêng hoặc vật hóa một bộ dữ liệu thử hữu hạn có kiểm soát.

## 10. Kiểm thử tính chất theo thứ tự và không thứ tự

Không được tự động dùng phép hoán vị cho **mọi thao tác Stream**.

### 10.1. Phép tổng hợp không phụ thuộc thứ tự

~~~java
long sum = data.stream()
        .mapToLong(Long::longValue)
        .sum();
~~~

Với số nguyên trong miền không tràn và cùng tập phần tử, việc xáo thứ tự không làm thay đổi tổng toán học.

### 10.2. Phép lấy phần tử đầu phụ thuộc encounter order

~~~java
List<String> names = List.of("Lan", "An", "Minh");

String first = names.stream()
        .findFirst()
        .orElseThrow();

// "Lan"
~~~

Nếu đổi thứ tự danh sách thành `[Minh, Lan, An]`, kết quả hợp lệ là `"Minh"`. Một tính chất “xáo thứ tự mà `findFirst` không đổi” là **sai từ định nghĩa**.

### 10.3. distinct giữ thứ tự xuất hiện đầu tiên trên Stream ordered

~~~java
List<Integer> input = List.of(2, 1, 2, 3, 1);

List<Integer> unique = input.stream()
        .distinct()
        .toList();

// [2, 1, 3]
~~~

Với nguồn có encounter order, `distinct` giữ phần tử đầu tiên tương ứng với mỗi giá trị theo hợp đồng ổn định. Một tính chất phù hợp là:

~~~text
distinct(distinct(input)) == distinct(input)
~~~

Và danh sách kết quả **không có phần tử trùng**, nhưng không được giả định kết quả vẫn giữ thứ tự cũ nếu đầu vào bị xáo trước phép `distinct`.

### 10.4. sorted và limit có hợp đồng riêng

~~~java
List<Integer> top3 = input.stream()
        .sorted()
        .limit(3)
        .toList();
~~~

Nếu yêu cầu “ba số nhỏ nhất” thì việc xáo thứ tự đầu vào không ảnh hưởng danh sách `top3` đối với phần tử so sánh bằng nhau không có thuộc tính phân biệt khác. Trường hợp phần tử là object có comparator chỉ xem một trường, phải xác định rõ quy tắc phá hòa nếu kết quả cần thứ tự ổn định giữa những phần tử được xem là bằng nhau.

Các tính chất về thứ tự nên bám vào **encounter order, comparator và terminal operation** cụ thể; đừng dựa vào thứ tự mà một `HashMap` tình cờ hiển thị.

## 11. Kiểm thử song song: tính kết hợp, state và combiner

Đổi từ `stream()` sang `parallelStream()` có thể làm thay đổi cách chia/ghép các phần dữ liệu. Đó là nơi property-based testing đặc biệt hữu ích.

### 11.1. Phép reduce phải có identity và toán tử phù hợp

~~~java
int correct = List.of(1, 2, 3, 4)
        .parallelStream()
        .reduce(0, Integer::sum);
~~~

Identity của phép cộng là `0`, và phép cộng số nguyên Java có tính kết hợp theo ngữ nghĩa số học modulo khi tràn. Tuy nhiên, nếu nghiệp vụ cấm tràn thì phải thiết kế kiểm soát riêng.

**Không dùng phép trừ để giảm song song theo cách thông thường:**

~~~java
int wrong = List.of(1, 2, 3, 4)
        .parallelStream()
        .reduce(0, (a, b) -> a - b);
~~~

Phép trừ **không có tính kết hợp**: `(a-b)-c` khác `a-(b-c)`. Các cách chia dữ liệu có thể cho kết quả khác nhau. Một test chỉ chạy tuần tự có thể không phát hiện lỗi này.

### 11.2. Kiểm thử trực tiếp luật combiner

Nếu tự viết collector tích lũy nhiều chỉ số, hãy kiểm tra:

~~~text
combine(identity, result) == result
combine(combine(a, b), c) == combine(a, combine(b, c))
aggregate(left + right) == combine(aggregate(left), aggregate(right))
~~~

Phép thử chia–gộp trong chương trình đầy đủ là một phiên bản của luật thứ ba. Với collector có state mutable, cần kiểm tra cả việc hai vùng tích lũy là **độc lập**, không cùng tham chiếu tới một Map/List bên ngoài.

### 11.3. Tránh side effect trong lambda

**Sai:**

~~~java
List<Long> output = new ArrayList<>();

sales.parallelStream()
        .map(Sale::totalCents)
        .forEach(output::add); // ArrayList không an toàn khi ghi đồng thời.
~~~

**Đúng:**

~~~java
List<Long> output = sales.parallelStream()
        .map(Sale::totalCents)
        .toList();
~~~

Với nguồn `List` có encounter order và `toList()`, danh sách đầu ra giữ thứ tự logic; nhưng **thứ tự thực thi các lời gọi mapper không được cam kết**.

Không nên dùng `AtomicInteger` để đánh số thứ tự trong `map` rồi coi các số đó là chỉ số encounter order. Atomicity bảo đảm không mất lượt tăng, không bảo đảm tác vụ chạy theo thứ tự nguồn.

## 12. Ngẫu nhiên trong parallel stream: tạo đầu vào trước, xử lý sau

Một anti-pattern là đặt generator mutable vào mapper:

~~~java
SplittableRandom random = new SplittableRandom(123L);

List<Integer> values = source.parallelStream()
        .map(x -> random.nextInt(100))
        .toList();
~~~

`SplittableRandom` không được thiết kế để chia sẻ sử dụng đồng thời giữa nhiều thread. Ngoài nguy cơ sử dụng không an toàn, thứ tự tiêu thụ các số ngẫu nhiên còn phụ thuộc lịch chạy, nên seed đơn lẻ **không đảm bảo mỗi phần tử luôn nhận đúng số ngẫu nhiên như lần trước**.

Cách được ưu tiên trong kiểm thử:

~~~java
List<Sale> data = generate(123L); // Sinh tuần tự, xác định.

Map<String, Long> result = data.parallelStream()
        .collect(Collectors.groupingBy(
                Sale::region,
                Collectors.summingLong(Sale::totalCents)
        ));
~~~

Đầu vào đã cố định; pipeline chỉ thực hiện tính toán thuần trên dữ liệu đó.

Nếu thật sự cần sinh dữ liệu ngẫu nhiên song song, phải thiết kế **seed riêng theo phần tử/chỉ số hoặc theo nhánh**, cùng quy tắc ánh xạ ổn định. Ví dụ, lập danh sách các chỉ số rồi tạo generator mới từ seed suy ra từ chỉ số; tránh khẳng định việc gọi `split()` theo lịch chạy không xác định sẽ tự tạo dãy đầu vào có cùng thứ tự trên mọi lần thực thi.

**Kiểm thử tính đúng không đồng nghĩa benchmark.** Sinh dữ liệu ngẫu nhiên trong phần đang đo có thể làm sai kết quả đo do thêm chi phí generator; nên sinh fixture trước phép đo.

## 13. Tập trung vào đường biên, không chỉ phân bố ngẫu nhiên

Một bộ sinh hoàn toàn đồng đều có thể hiếm khi sinh ra **trường hợp khó**. Ví dụ, với `count` từ 0 đến 200, xác suất tạo đúng danh sách rỗng trong một lượt chỉ là `1/201`; ngay cả 500 lượt cũng không đảm bảo nó đã xuất hiện.

Vì vậy phải có **fixture cố định** bên cạnh random tests:

| Tình huống | Điều cần kiểm tra |
| --- | --- |
| Danh sách rỗng | Map rỗng, tổng 0 |
| Một giao dịch | Xuất đúng một khóa và số tiền |
| Nhiều giao dịch cùng vùng | Gộp đúng, không mất khoản |
| Doanh thu bằng 0 | Vùng vẫn tồn tại nếu có giao dịch |
| Mọi giao dịch cùng vùng | Không tạo nhóm thừa |
| Một số vùng vắng mặt | Không tạo khóa cho vùng chưa xuất hiện |
| Giá trị cực đại hợp lệ | Không tràn trong miền được cho phép |
| Giá trị gây tràn | Báo lỗi hoặc thực hiện chính sách số học riêng |
| `null` trong region hoặc bản ghi | Từ chối/chấp nhận theo hợp đồng đã xác định |
| Dữ liệu chưa sắp xếp và đã sắp xếp | So đúng các thuộc tính về encounter order |
| Nguồn có phần tử trùng nhau | Xem có cần giữ số lần xuất hiện hay loại trùng |
| Dữ liệu lớn và chia nhiều nhánh | Kiểm tra tính tương đương song song và giới hạn bộ nhớ |

Bộ sinh chính trong ví dụ không tạo `null` và không vượt giới hạn `long`. Đó là **lựa chọn cho một họ tính chất**, không phải bằng chứng pipeline chịu được mọi dữ liệu xấu. Hãy viết test riêng cho dữ liệu không hợp lệ, với kỳ vọng rõ ràng: ném `IllegalArgumentException`, từ chối bản ghi, hay ghi nhận một kết quả parse lỗi.

### Luật cần chú ý khi làm việc với null

`Collectors.groupingBy` tiêu chuẩn không chấp nhận classifier trả khóa `null`; nếu dữ liệu nguồn có region thiếu, có thể phát sinh `NullPointerException`. Không nên để generator tạo null ngẫu nhiên rồi coi lỗi đó là bug, trừ khi hợp đồng của pipeline nói rằng null phải được xử lý một cách hợp lệ.

Thiết kế test tốt **phân biệt rõ miền hợp lệ với miền dữ liệu cần bị từ chối**.

## 14. Thu nhỏ phản ví dụ: từ 200 phần tử về vài phần tử

Một lần chạy ngẫu nhiên có thể báo lỗi trên danh sách 180 giao dịch. Đọc toàn bộ danh sách và suy luận bằng mắt rất khó. Kỹ thuật **shrinking** hoặc **delta debugging** cố tìm một đầu vào nhỏ hơn nhưng vẫn gây cùng lỗi.

Quy trình thủ công hữu ích:

1. Lưu `seed` và danh sách đầu vào gây lỗi.
2. Chia danh sách thành các phần, thử **loại bỏ từng khối lớn**.
3. Nếu bỏ khối mà lỗi vẫn xảy ra, giữ đầu vào đã thu nhỏ.
4. Giảm dần kích thước khối; thử rút danh sách về một hoặc hai bản ghi.
5. Thu nhỏ giá trị: số tiền nhỏ hơn, số vùng ít hơn, đưa số lượng về `0`/`1`, rút ngắn chuỗi ID.
6. Lưu **đầu vào tối thiểu** thành fixture hồi quy không phụ thuộc generator.

Ví dụ một collector sai chỉ gộp một phần Map khi chạy song song. Random test 200 phần tử có thể được thu nhỏ thành:

~~~java
List<Sale> counterExample = List.of(
        new Sale("NORTH", 1, 10L),
        new Sale("SOUTH", 1, 20L)
);
~~~

Nếu pipeline song song vẫn mất một trong hai khóa trên input nhỏ này, việc tìm lỗi ở combiner đơn giản hơn nhiều.

Tuy nhiên, **phản ví dụ nhỏ nhất phụ thuộc lỗi**. Không khẳng định ví dụ hai phần tử trên luôn tái tạo lỗi parallel trên mọi JDK; runtime có thể không chia nguồn nhỏ. Đối với lỗi chỉ xuất hiện khi chia song song, hãy kiểm tra **luật combiner trực tiếp** bằng các vùng tích lũy được tạo thủ công, ngoài việc chạy `parallelStream`.

Các framework property-based testing có khả năng shrinking tích hợp có thể tự động hóa bước này; nguyên lý quan trọng vẫn là **lưu phản ví dụ dễ hiểu làm test cố định sau khi sửa**.

## 15. Metamorphic testing khi không có oracle dễ tính

Đôi khi kết quả chính xác khó xác định bằng một thuật toán tham chiếu độc lập, ví dụ một pipeline gồm nhiều phép biến đổi phức tạp. Khi đó các **quan hệ biến hình** có thể bổ sung bằng chứng.

### 15.1. Thêm dữ liệu không liên quan

Nếu đang tính riêng tổng của vùng `NORTH`, thêm một giao dịch vùng `SOUTH` không được làm đổi tổng `NORTH`:

~~~text
northTotal(sales + [SOUTH sale]) == northTotal(sales)
~~~

Chỉ áp dụng nếu không có quy tắc toàn cục khác như mức giảm giá dựa trên tổng tất cả vùng.

### 15.2. Tách một giao dịch thành hai giao dịch tương đương

Một giao dịch `(NORTH, 3 units, 100 cents)` có thể tách thành `(NORTH, 1, 100)` và `(NORTH, 2, 100)`. Nếu báo cáo chỉ cộng thành tiền theo vùng, tổng `NORTH` không đổi.

Đừng áp tính chất này cho phép đếm **số giao dịch**, vì sau khi tách, số giao dịch đúng là tăng thêm một.

### 15.3. Đổi thứ tự các phần tử

Đối với tổng theo vùng, hoán vị không đổi kết quả. Đối với phép nối chuỗi, lấy phần tử đầu, đánh số theo vị trí hoặc `takeWhile`, phép hoán vị có thể đổi ngữ nghĩa.

### 15.4. Ghép hai input

Với phép tổng có tính kết hợp trong miền hợp lệ:

~~~text
total(A ++ B) = total(A) + total(B)
~~~

Nhưng với tính trung bình, không thể cộng trực tiếp hai giá trị trung bình của hai nhóm. Phải ghép theo **tổng và số lượng**, sau đó mới chia. Đây là ví dụ điển hình về việc một quan hệ biến hình tưởng đúng nhưng thiếu dữ liệu trung gian.

### 15.5. Chạy lại cùng đầu vào

Một pipeline tính toán thuần và không phụ thuộc external state phải cho cùng nội dung đầu ra khi chạy lại trên cùng snapshot dữ liệu. Tuy nhiên, `findAny` trên parallel stream hoặc thứ tự duyệt một Map unordered có thể khác theo hợp đồng API. Hãy chỉ khẳng định những thuộc tính **được đặc tả**, ví dụ tập phần tử kết quả, thay vì yêu cầu chuỗi in ra hoàn toàn giống nhau khi không có thứ tự.

## 16. Vì sao kiểm thử side effect bằng peek thường gây hiểu nhầm?

`peek` hữu ích khi **quan sát chẩn đoán** trong một số pipeline, nhưng không phù hợp làm nơi đặt logic bắt buộc.

~~~java
List<String> data = List.of("A", "B", "C");

long count = data.stream()
        .peek(x -> System.out.println("Seen " + x))
        .count();
~~~

Không nên viết tính chất “`peek` phải được gọi đúng ba lần”. Một số implementation có thể tính `count` từ đặc tính `SIZED` của nguồn mà không cần duyệt từng phần tử, vì thế những action không cần thiết có thể không được thực thi.

Các thao tác short-circuit như `findFirst` và `anyMatch` cũng có thể dừng trước khi thấy mọi phần tử. Trong parallel stream, thứ tự/thời điểm gọi side effect không được bảo đảm như một vòng lặp tuần tự.

**Tách mục tiêu kiểm thử:**

- Kiểm tra **kết quả** bằng oracle, bất biến và quan hệ biến hình.
- Ghi log/`peek` chỉ làm phương tiện quan sát tạm thời.
- Nếu một hành động **phải** được thực hiện đúng một lần cho từng bản ghi, thiết kế nó ở tầng tác vụ có hợp đồng riêng thay vì dựa vào một intermediate operation có thể được tối ưu hóa hoặc short-circuit.

Đừng đưa `sleep`, lệnh in log hay bộ đếm dùng chung vào mapper chỉ để "ép" biểu hiện lỗi song song; những thay đổi đó có thể làm biến mất hoặc tạo thêm race condition.

## 17. Kiểm thử độ chính xác số học và giới hạn của long

Miền dữ liệu trong ví dụ được chọn để không tràn `long`, nên ta có thể so tổng chính xác giữa tuần tự và song song.

Nếu thay bằng `double`:

~~~java
List<Double> values = List.of(
        1.0e16, -1.0e16, 1.0
);
~~~

Phép cộng floating-point **không có tính kết hợp tuyệt đối**:

~~~java
double a = 1.0e16;
double b = -1.0e16;
double c = 1.0;

System.out.println((a + b) + c); // 1.0
System.out.println(a + (b + c)); // 0.0
~~~

Do thay đổi cách nhóm, pipeline song song có thể tạo khác biệt nhỏ trong một số phép tổng dấu phẩy động; hơn nữa, những thao tác tổng của JDK có thể dùng chiến lược bù sai số riêng. Không nên áp một tính chất `Double.equals` giữa mọi cách chia phần nếu nghiệp vụ chỉ đòi độ chính xác theo dung sai.

Thay vào đó:

- Xác định sai số chấp nhận được; xét sai số tương đối/tuyệt đối phù hợp với miền số.
- Với tiền tệ, dùng số nguyên đơn vị nhỏ nhất hoặc `BigDecimal` theo chính sách làm tròn rõ.
- Không làm tròn từng bước accumulator/combiner nếu yêu cầu làm tròn **sau tổng**, vì làm tròn trung gian có thể phá tính kết hợp.
- Kiểm thử overflow của `int`/`long` thành một nhóm riêng: dùng `Math.addExact`/`Math.multiplyExact` khi cần báo lỗi thay vì tràn âm thầm.

Nếu muốn kiểm thử một phép `reduce` với `BigDecimal`, sử dụng `BigDecimal.ZERO` và `BigDecimal::add` không kèm `MathContext` để tổng hợp chính xác, rồi làm tròn ở ranh giới nghiệp vụ. **Không tự giả định mọi `reduce` là phép toán kết hợp**: điều đó là hợp đồng mà người thiết kế accumulator và combiner phải bảo đảm.

## 18. Kiểm thử pipeline với nguồn I/O và vòng đời tài nguyên

Tạo dữ liệu ngẫu nhiên trong bộ nhớ giúp kiểm tra logic nhanh và có thể tái lập, nhưng **không chứng minh** phần nguồn I/O được đóng đúng.

Ví dụ:

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Stream;

static long countNonBlankLines(Path path) throws Exception {
    try (Stream<String> lines = Files.lines(
            path, StandardCharsets.UTF_8)) {
        return lines
                .filter(line -> !line.isBlank())
                .count();
    }
}
~~~

`Files.lines` tạo Stream gắn với tài nguyên tệp; `count()` không tự gọi `close()`. Test về vòng đời cần kiểm tra cả:

- Thành công khi đọc hết.
- Dừng sớm do `limit`, `findFirst` hoặc `anyMatch`.
- Ngoại lệ trong parser/mapper.
- Lỗi I/O khi mở hoặc đọc nguồn.
- Nguồn được đóng sau mỗi trường hợp, và không dùng Stream đã đóng.

Có thể kiểm tra **cơ chế đóng** bằng `onClose`:

~~~java
import java.util.concurrent.atomic.AtomicBoolean;

AtomicBoolean closed = new AtomicBoolean();

try (Stream<Integer> stream = Stream.of(1, 2, 3)
        .onClose(() -> closed.set(true))) {
    stream.findFirst();
}

if (!closed.get()) {
    throw new AssertionError("Stream not closed");
}
~~~

Đây là phép thử `onClose` trên Stream giả lập, không chứng minh một file handle thực tế được hệ điều hành giải phóng. Cần kiểm thử tích hợp nguồn thật hoặc quan sát tài nguyên phù hợp nếu đó là yêu cầu trọng yếu.

Với một file đầu vào được dùng làm oracle, nhớ rằng tệp có thể bị ghi đồng thời hoặc thay đổi giữa các lần chạy; cần fixture cố định hoặc snapshot để bảo đảm sự tái lập.

## 19. Đưa phương pháp vào JUnit và framework property-based

Chương trình tự chạy ở phần 7 chỉ dùng Java chuẩn. Trong dự án có JUnit hoặc một thư viện property-based testing như **jqwik**, bạn có thể biểu diễn những tính chất tương tự dưới dạng nhiều lần chạy được test runner quản lý.

Sơ đồ trách nhiệm:

~~~text
Generator
   |
   +-- chọn seed / sinh dữ liệu hợp lệ
   |
   v
Property
   |
   +-- gọi code cần thử
   +-- gọi oracle hoặc biến đổi đầu vào
   +-- so bất biến / kết quả
   |
   v
Test runner
   |
   +-- lặp nhiều ca
   +-- báo seed và đầu vào khi lỗi
   +-- thu nhỏ phản ví dụ (nếu framework hỗ trợ)
   +-- lưu báo cáo / kết quả CI
~~~

Lợi ích của framework: tích hợp vào build, báo cáo test, sinh dữ liệu theo constraint và có thể hỗ trợ shrinking. Nhưng framework không tự biết **tính chất nghiệp vụ nào đúng**. Nếu bạn viết thuộc tính sai, nó sẽ tìm "phản ví dụ" cho một giả định sai.

Khi dùng công cụ bên thứ ba:

- Kiểm tra phiên bản thư viện tương thích với JDK, JUnit và build hiện tại.
- Cấu hình seed, số lượt thử, miền kích thước và hành vi shrinking theo API phiên bản đang dùng.
- Không hardcode tên annotation/cấu hình theo phiên bản khác nếu chưa kiểm tra.
- Khi CI phát hiện lỗi, lưu **input tối giản** thành test hồi quy bình thường, không chỉ lưu một seed ngẫu nhiên.

**Kết hợp ba lớp kiểm thử** hiệu quả hơn chỉ dùng một lớp: fixture biên cố định, property-based tests và test tích hợp với nguồn/tài nguyên thật.

## 20. Thiết kế ca thử để tránh test không ổn định

Một kiểm thử có thể thất bại ngẫu nhiên vì hai nguyên nhân rất khác nhau:

1. **Pipeline thực sự sai:** ví dụ race condition, combiner sai, lệ thuộc thứ tự không được cam kết.
2. **Test tự sai hoặc khó tái lập:** seed không lưu, nguồn thay đổi, dùng thời gian hiện tại, thứ tự HashMap trong expected string hoặc tạo ngẫu nhiên trong mapper song song.

Checklist thiết kế:

| Quyết định | Nên làm | Tránh |
| --- | --- | --- |
| Seed | Ghi rõ seed cho từng case | Chỉ ghi "random failed" |
| Generator | Có miền giá trị và kích thước có giới hạn | Sinh vô hạn hoặc ngẫu nhiên không kiểm soát |
| Test data | Sinh trước, coi input là bất biến | Vừa sinh vừa sửa cùng dữ liệu trong pipeline |
| Oracle | Vòng lặp rõ và kiểm tra bằng fixture | Copy nguyên pipeline rồi coi là tham chiếu |
| Map | So `Map.equals` | So `map.toString()` với thứ tự khóa ngầm định |
| List có thứ tự | So cả nội dung và thứ tự | Coi kết quả unordered như ordered |
| Parallel | Kiểm tra kết quả và luật combiner | Kiểm tra số thread/tên thread cố định |
| Random trong mapper | Không cần trong test tổng hợp | Chia sẻ `SplittableRandom` mutable giữa task |
| Số học | Giới hạn overflow hoặc kiểm tra overflow riêng | Để tràn ngầm rồi kết luận tính chất sai |
| Lỗi | Lưu seed + input + expected/actual | Chỉ chạy lại toàn bộ suite để "bắt" lỗi |
| Thời gian/I/O | Dùng fixture/snapshot, đóng resource | Dựa vào clock/network live cho expected |
| Shrinking | Lưu đầu vào tối giản làm hồi quy | Chỉ giữ một input rất lớn khó phân tích |

Với ứng dụng có yêu cầu hiệu năng, hãy **benchmark sau khi đã kiểm tra tính đúng**. Kiểm thử sinh ngẫu nhiên 500 lần không tự chứng minh pipeline nhanh, và microbenchmark tự viết có thể bị sai lệch vì JIT warm-up, GC và chi phí sinh input. Sử dụng công cụ phù hợp như JMH khi cần đánh giá hiệu năng nghiêm túc.

## 21. Bài tập thực hành

### Bài 1 — Viết tính chất của filter

Cho:

~~~java
List<Integer> actual = data.stream()
        .filter(n -> n >= 0)
        .toList();
~~~

**Yêu cầu:** Nêu hai tính chất hợp lệ.

**Gợi ý/đáp án:** (1) Mọi phần tử trong `actual` đều không âm; (2) `actual` bằng danh sách tạo bởi vòng lặp chỉ thêm phần tử `n >= 0` theo encounter order của `data`. Chỉ kiểm tra tính chất (1) chưa đủ vì pipeline trả danh sách rỗng luôn thỏa (1).

### Bài 2 — Seed và tái lập

Một test dùng `new SplittableRandom(System.nanoTime())` nhưng chỉ in `"failed"`. Vì sao khó debug?

**Đáp án:** Seed không được lưu, nên khó sinh lại cùng input. Hãy ghi seed, số lượt thử và input khi thất bại; có thể dùng seed hằng trong CI và cho phép chạy lại một seed đơn.

### Bài 3 — Kiểm thử groupingBy

Với `List<Sale>` của bài, nêu ba tính chất hợp lệ cho `groupingBy(region, summingLong(amount))`.

**Đáp án:** Kết quả bằng oracle dùng vòng lặp; tổng của các nhóm bằng tổng tiền của mọi giao dịch; hoán vị input không làm thay đổi Map. Có thể bổ sung phép chia–gộp và so tuần tự/song song.

### Bài 4 — Có được hoán vị trước findFirst?

Một pipeline dùng `findFirst()` trên `List` đã sắp ưu tiên. Tính chất "xáo thứ tự input nhưng kết quả giữ nguyên" đúng không?

**Đáp án:** Không. `findFirst` giữ phần tử đầu theo encounter order. Xáo thứ tự có thể đổi kết quả hợp lệ; cần kiểm tra phần tử đầu của **input sau biến đổi**.

### Bài 5 — Test phát hiện sai combiner

Một collector tính trung bình chỉ giữ `double average` của từng phần rồi gộp bằng `(a+b)/2`. Tính chất nào có thể phát hiện lỗi?

**Đáp án:** `aggregate(A ++ B) == combine(aggregate(A), aggregate(B))` trên các đoạn có kích thước khác nhau. Trung bình chung không phải trung bình đơn giản của hai trung bình nếu số phần tử hai nhóm khác nhau. Đúng hơn là giữ cặp `(sum, count)`, cộng hai cặp rồi mới chia.

### Bài 6 — Ngẫu nhiên trong parallel map

Vì sao chia sẻ một `SplittableRandom(seed)` giữa tất cả lambda trong `parallelStream().map(...)` không phù hợp cho kiểm thử tái lập?

**Đáp án:** Generator có trạng thái không dành cho chia sẻ đa luồng; thứ tự gọi phụ thuộc lịch thực thi, khiến mỗi phần tử có thể nhận giá trị khác. Nên sinh input trước hoặc tạo các bộ sinh độc lập theo chỉ số/seed được xác định rõ.

### Bài 7 — Một property test luôn pass có thể vẫn sai?

Một test chỉ kiểm tra rằng mọi phần tử trong kết quả `filter(even)` đều chẵn. Hàm sản xuất bị lỗi và luôn trả `List.of()`. Test có thất bại không?

**Đáp án:** Không. Mọi phần tử trong danh sách rỗng đều thỏa điều kiện một cách hiển nhiên. Cần so thêm với oracle hoặc kiểm tra số lượng/phép bảo toàn thích hợp.

### Bài 8 — Phân biệt miền hợp lệ và kiểm tra lỗi

Generator tạo `region == null` trong khi pipeline dùng `groupingBy(Sale::region)` và hợp đồng yêu cầu region khác null. Test bị `NullPointerException`. Đây có chắc là lỗi pipeline không?

**Đáp án:** Không. Nếu region null nằm ngoài miền hợp lệ, test phải kỳ vọng hành vi từ chối dữ liệu hoặc không sinh null trong nhóm thử dữ liệu hợp lệ. Nếu nghiệp vụ cần chấp nhận null, phải sửa đặc tả và bổ sung xử lý rõ.

### Bài 9 — Shrinking với lỗi chỉ xuất hiện khi parallel

Tại sao sau khi thu nhỏ từ 100.000 phần tử còn 2 phần tử, cùng phép thử `parallelStream` có thể không tái hiện lỗi?

**Đáp án:** Runtime có thể không chia input cực nhỏ thành nhiều task, nên race/combiner sai không bộc lộ. Cần kiểm thử luật combiner trực tiếp, hoặc giữ kích thước đủ để tái tạo điều kiện lỗi, và lưu bằng chứng về môi trường thực thi.

### Bài 10 — Lỗi tài nguyên

Một pipeline đọc file bằng `Files.lines(path)` rồi gọi `limit(5).toList()`. Làm thế nào viết test đáng tin cậy hơn?

**Đáp án:** Đặt `Files.lines` trong `try-with-resources` và kiểm tra kết quả năm dòng đầu; bổ sung kiểm thử đường đi exception/short-circuit và tài nguyên được đóng. Đừng coi terminal `toList` là cơ chế tự đóng file.

## 22. Ghi nhớ

- **Property-based testing** kiểm tra các luật tổng quát trên nhiều input, không chỉ một vài ví dụ cố định.
- Dùng **seed được kiểm soát** để sinh dữ liệu ngẫu nhiên có thể tái lập; lưu seed, cấu hình và input khi thất bại.
- Xây **oracle độc lập** khi có thể; bổ sung bất biến và quan hệ biến hình (*metamorphic*) để giảm nguy cơ cả oracle lẫn code cùng sai.
- Chọn tính chất đúng hợp đồng: tổng theo nhóm không phụ thuộc thứ tự, nhưng `findFirst`, `limit`, `takeWhile` và `joining` có thể phụ thuộc encounter order.
- Kiểm tra **tính kết hợp, identity và phép ghép** khi reduction/collector sẽ chạy song song; không chia sẻ collection mutable bằng `parallelStream().forEach`.
- **Sinh dữ liệu trước khi chạy pipeline**; tránh dùng generator mutable chung trong mapper song song.
- Luôn có fixture biên cố định: rỗng, một phần tử, dữ liệu trùng, null không hợp lệ, số 0 và giá trị cực trị.
- Thu nhỏ input gây lỗi và lưu thành test hồi quy; một seed có thể giúp tái lập nhưng một input tối giản giúp hiểu lỗi nhanh hơn.
- Tách kiểm thử ngữ nghĩa khỏi benchmark hiệu năng và kiểm thử vòng đời tài nguyên; `peek` không phải cơ chế bảo đảm callback được gọi đúng số lần.

**Ý chính:** Muốn gỡ lỗi pipeline Stream API hiệu quả, hãy kiểm tra **những điều phải luôn đúng** trên nhiều dữ liệu, đồng thời khiến mọi phản ví dụ **có thể tạo lại và thu nhỏ**. Sự kết hợp giữa seed xác định, oracle dễ hiểu, bất biến theo nhóm, kiểm thử song song, fixture biên và kiểm tra tài nguyên mang lại bằng chứng tốt hơn nhiều so với những lần chạy ngẫu nhiên không ghi lại đầu vào.
