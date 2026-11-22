# Collectors.teeing() để kết hợp hai phép tổng hợp trong Java

## 1. Bài toán: cần hai thống kê từ cùng một nguồn Stream

Giả sử bạn có danh sách đơn hàng và cần tạo báo cáo gồm **số đơn** cùng **tổng doanh thu**. Hai phép tổng hợp riêng biệt có thể viết như sau:

~~~java
long count = sales.stream().count();
long total = sales.stream().mapToLong(Sale::revenue).sum();
~~~

Đây là **đoạn minh họa bên trong phương thức**; kiểu `Sale` có phương thức `revenue()` như chương trình Java 17 ở phần 8. Cách viết trên rõ ràng, nhưng tạo **hai Stream riêng** từ cùng Collection, có thể cần hai lần đánh giá dữ liệu. Nếu nguồn không tái duyệt được hoặc hai báo cáo phải xây dựng trong cùng một lần thu thập, ta muốn mô tả một phép tổng hợp gồm **hai nhánh**.

Từ Java 12, `java.util.stream.Collectors` cung cấp:

~~~java
Collectors.teeing(downstream1, downstream2, merger)
~~~

Tên *teeing* gợi hình ảnh một nhánh chữ T: dữ liệu đi vào được chuyển đến **hai downstream collector** để tính hai kết quả riêng, rồi **merger** ghép hai kết quả đó thành một giá trị cuối cùng.

Ví dụ:

~~~java
Summary summary = sales.stream().collect(Collectors.teeing(
        Collectors.counting(),
        Collectors.summingLong(Sale::revenue),
        (count, total) -> new Summary(count, total)
));
~~~

Đây là mã **minh họa**, giả sử class/record `Summary` có constructor nhận `long count, long total`, và đã import `java.util.stream.Collectors`. Hai nhánh thu thập lần lượt cho:
- `downstream1 = counting()`: số phần tử.
- `downstream2 = summingLong(...)`: tổng doanh thu.
- `merger`: biến hai kết quả thành một `Summary` có cấu trúc.

**Điểm cốt lõi:** `teeing()` không tự tạo thêm một nguồn dữ liệu và không bắt buộc bạn phải viết hai terminal operation. Nó là **một Collector** để dùng với **một** `stream.collect(...)`, trong đó từng phần tử được đưa vào cả hai downstream theo cơ chế của Collector.

## 2. Chữ ký và kiểu generic của teeing()

Chữ ký khái niệm của Java 17:

~~~java
static <T, R1, R2, R> Collector<T, ?, R> teeing(
        Collector<? super T, ?, R1> downstream1,
        Collector<? super T, ?, R2> downstream2,
        BiFunction<? super R1, ? super R2, R> merger)
~~~

Đây là **chữ ký API để đọc hiểu**, không phải mã cần tự khai báo trong ứng dụng. Các tham số kiểu:

| Ký hiệu | Vai trò |
| --- | --- |
| `T` | Kiểu phần tử được thu thập từ Stream |
| `R1` | Kiểu kết quả cuối của downstream thứ nhất |
| `R2` | Kiểu kết quả cuối của downstream thứ hai |
| `R` | Kiểu kết quả cuối cùng sau khi merger ghép hai nhánh |
| `downstream1` | Collector áp dụng cho nguồn T |
| `downstream2` | Collector khác, cũng áp dụng cho nguồn T |
| `merger` | Hàm nhận `(R1,R2)` và trả `R` |

Ví dụ hai collector có thể trả các **kiểu khác nhau**:

~~~java
Collectors.teeing(
        Collectors.counting(),            // Long
        Collectors.toList(),               // List<T>
        (count, elements) -> ...           // Kết quả do bạn định nghĩa
)
~~~

Dấu `...` trong đoạn trên là **ký hiệu minh họa ý tưởng**, không phải Java hoàn chỉnh. Merger có thể tạo một record, DTO, tuple do dự án định nghĩa, một `Map.Entry` phù hợp, hoặc một kiểu nghiệp vụ khác.

Khác với `reduce(identity, accumulator, combiner)`, bạn **không phải tự viết logic quản lý trạng thái của cả hai nhánh**. Mỗi downstream collector tự cung cấp supplier/accumulator/combiner/finisher của nó; teeing phối hợp hai nhánh rồi gọi merger để tạo R.

### 2.1. Nhìn theo sơ đồ dữ liệu

~~~text
                Stream<T>
                    |
              collect(teeing)
                    |
          +---------+---------+
          |                   |
    downstream1          downstream2
    counting()           summingLong(...)
          |                   |
       R1: Long             R2: Long
          |                   |
          +---------+---------+
                    |
              merger(R1, R2)
                    |
                Summary
~~~

Sơ đồ mô tả **luồng dữ liệu và hợp đồng tổng hợp**, không phải lịch thread hay số lần gọi từng hàm mà JDK buộc phải dùng. Với parallel stream, framework có thể có nhiều container thu thập từng phần rồi kết hợp trước khi tạo hai giá trị R1, R2 cuối cùng.

### 2.2. Thứ tự đối số trong merger

Merger nhận kết quả của **downstream thứ nhất trước**, rồi kết quả của **downstream thứ hai**:

~~~java
(count, total) -> new Summary(count, total)
~~~

Không được đảo nghĩa hai tham số chỉ vì chúng trùng kiểu `Long`. Khi cả R1 và R2 là số, compiler vẫn có thể chấp nhận một merger sai thứ tự nghiệp vụ. Đặt tên `count`, `total` theo đúng collector tương ứng giúp tránh lỗi khó phát hiện.

## 3. Ví dụ thiết thực: số đơn và tổng tiền trong một Summary

Một class đơn hàng đơn giản có thể biểu diễn số lượng và đơn giá:

~~~java
record Sale(String region, int units, long unitPrice) {
    long revenue() {
        return Math.multiplyExact((long) units, unitPrice);
    }
}
~~~

Đây là **khai báo kiểu** Java 17; chương trình hoàn chỉnh ở phần 8. `Math.multiplyExact` ném `ArithmeticException` khi phép nhân `long` bị tràn; nó không làm cho các phép cộng ở bước tổng hợp tự được kiểm tra tràn.

Kết quả báo cáo:

~~~java
record Summary(long orders, long revenue,
               OptionalDouble averageRevenue) {}
~~~

Ở đây `OptionalDouble` biểu diễn trung bình có hoặc không có dữ liệu. Để tránh chia cho 0 khi Stream rỗng, merger có thể quyết định:

~~~java
Summary summary = sales.stream().collect(Collectors.teeing(
        Collectors.counting(),
        Collectors.summingLong(Sale::revenue),
        (count, total) -> new Summary(
                count,
                total,
                count == 0 ? OptionalDouble.empty()
                           : OptionalDouble.of((double) total / count))
));
~~~

Đoạn này cần import `Collectors`, `OptionalDouble` và đặt trong phương thức đã có danh sách `sales`. Một vài điểm cần nắm:

1. `counting()` trả `Long`, được tự unbox sang `long` khi tạo record.
2. `summingLong(Sale::revenue)` trả `Long` của tổng.
3. Hai nhánh cùng nhận đối tượng Sale, nhưng **mỗi nhánh tính một phép tổng hợp riêng**.
4. Merger được dùng để tạo **một Summary** từ hai giá trị cuối.
5. Với danh sách rỗng, `count=0`, `total=0`; trung bình được biểu diễn là **không có giá trị**, không tự đánh đồng với mức trung bình thực sự bằng 0.

Nếu ứng dụng muốn hiển thị trung bình 0 khi không có đơn, đó là một **quyết định hiển thị hoặc nghiệp vụ**. Tầng dữ liệu có thể vẫn giữ `OptionalDouble.empty()` để tránh nhầm “không có quan sát” với “trung bình đã đo bằng 0”.

### 3.1. Vì sao đây không phải phép chia đơn giản trong mỗi nhánh?

Tổng doanh thu và số đơn độc lập, nhưng **trung bình** phụ thuộc đồng thời vào cả hai. Nếu cố tính trung bình ngay từ một phần tử mà không có tổng lẫn số lượng, bạn cần một collector thống kê riêng.

`teeing` phù hợp khi:
- Cần hai kết quả được tính độc lập từ cùng phần tử.
- Muốn ghép chúng thành một kiểu kết quả có ý nghĩa.
- Có sẵn collector cho từng nhánh, không muốn tự viết state mutable riêng.

Nếu chỉ cần số trung bình, `Collectors.averagingLong(Sale::revenue)` có thể trực tiếp hơn. `teeing` có giá trị khi **cần cả những chỉ số khác** để tạo báo cáo cùng lúc.

## 4. Kết hợp hai collector rất khác nhau

Hai nhánh không bắt buộc cùng trả số.

Giả sử cần **tổng doanh thu theo vùng** và **tổng doanh thu toàn bộ** trong một báo cáo. Downstream thứ nhất có thể là `groupingBy(...)`, nhánh thứ hai là `summingLong(...)`:

~~~java
record Report(Map<String, Long> revenueByRegion, long grandTotal) {}

Report report = sales.stream().collect(Collectors.teeing(
        Collectors.groupingBy(
                Sale::region,
                TreeMap::new,
                Collectors.summingLong(Sale::revenue)),
        Collectors.summingLong(Sale::revenue),
        Report::new
));
~~~

Đây là **mã minh họa**: khai báo `record Report` ở cấp kiểu, lời gọi `collect` ở trong phương thức. Cần import `java.util.Map`, `java.util.TreeMap` và `Collectors`.

Giả sử danh sách đơn:

~~~text
North: 200
South: 180
North: 150
West:  120
~~~

Hai downstream cho kết quả:

~~~text
Nhánh 1 (TreeMap): {North=350, South=180, West=120}
Nhánh 2 (Long):    650
Merger:             Report(byRegion, 650)
~~~

**Tại sao dùng TreeMap?** Vì báo cáo muốn thứ tự khóa vùng tăng dần theo natural order của String. `groupingBy` mặc định không hứa loại Map/thứ tự duyệt, còn `TreeMap::new` đặt rõ hợp đồng sắp theo khóa. Lưu ý TreeMap sắp **theo khóa**, không sắp theo giá trị doanh thu.

Trong ví dụ thực thi ở phần 8, dùng `parallelStream()` với collector này cũng cho kết quả hợp lệ vì các downstream và phép gộp của chúng được dùng đúng hợp đồng. Tuy nhiên, **không nên suy rằng** parallel stream luôn nhanh hơn hoặc tên vùng sẽ được xử lý theo thứ tự thread.

### 4.1. Cần record/báo cáo bất biến không?

Một `record Report(Map<String,Long>...)` chỉ ngăn gán lại reference trong trường, **không tự làm Map bên trong bất biến**. Trong trường hợp cần public immutable DTO, hãy tạo bản sao bảo vệ với lựa chọn Map phù hợp và cân nhắc cách bảo toàn thứ tự nếu đầu ra cần iteration order. Ví dụ `Map.copyOf(...)` tạo Map không sửa được nhưng **không nên dựa vào nó để giữ nguyên thứ tự duyệt TreeMap**.

Có thể dùng một `SortedMap` được bọc không sửa, hoặc chuyển báo cáo thành danh sách entry đã sắp với contract xuất JSON rõ ràng; phải chọn dựa trên yêu cầu thực tế.

## 5. Kết hợp minBy và maxBy thành một Range

Một trường hợp dễ hiểu khác: cần **giá trị nhỏ nhất và lớn nhất**.

~~~java
record Range(Optional<Integer> min, Optional<Integer> max) {}

Range range = values.stream().collect(Collectors.teeing(
        Collectors.minBy(Comparator.naturalOrder()),
        Collectors.maxBy(Comparator.naturalOrder()),
        Range::new
));
~~~

Đoạn này cần import `java.util.Optional`, `java.util.Comparator` và `Collectors`. Với nguồn `[4,9,2,7]`:

~~~text
Range[min=Optional[2], max=Optional[9]]
~~~

Ở đây:
- Downstream 1 là `minBy` trả `Optional<Integer>`.
- Downstream 2 là `maxBy` trả `Optional<Integer>`.
- Merger `Range::new` dùng hai Optional để tạo một record mới.
- Dạng `teeing` phù hợp vì muốn **cặp giá trị**, không chỉ min hoặc max riêng lẻ.

### 5.1. Nguồn rỗng

Với `List.<Integer>of().stream()`, cả hai downstream `minBy/maxBy` cho `Optional.empty()`. Kết quả:

~~~text
Range[min=Optional.empty, max=Optional.empty]
~~~

Không cần ném exception chỉ vì không có phần tử. Nhưng caller phải có chính sách: hiển thị “không có dữ liệu”, dùng fallback, hoặc từ chối phép tính nếu thiếu dữ liệu là lỗi nghiệp vụ.

### 5.2. Khi nào không cần teeing cho min/max?

Nếu chỉ xử lý **các giá trị nguyên thủy** hoặc chỉ cần min/max/count/average cùng một kiểu số, Java có các phép thống kê chuyên dụng như `IntSummaryStatistics`, `LongSummaryStatistics` và collector `summarizingInt/Long/Double`. Chúng thường ngắn, rõ và tối ưu việc tổng hợp số học hơn so với tự ghép nhiều downstream có cùng dữ liệu.

Ví dụ:

~~~java
IntSummaryStatistics stats = values.stream()
        .collect(Collectors.summarizingInt(Integer::intValue));
~~~

Đây là đoạn minh họa cần import `java.util.IntSummaryStatistics` và `Collectors`. Nó trả các chỉ số min/max/sum/count/average trên IntSummaryStatistics. Với tập số rỗng, hãy xem contract của các getter trước khi hiển thị min/max (các giá trị mặc định của thống kê không nhất thiết tương đương một Optional).

**Chọn teeing nếu hai kết quả và merger biểu diễn đúng ý nghĩa domain**; không cố dùng teeing ở mọi nơi chỉ vì API có thể làm được.

## 6. teeing lồng trong groupingBy: hai thống kê cho mỗi nhóm

Thay vì dùng `teeing` để tính một báo cáo toàn lô, ta còn có thể đặt nó làm **downstream collector** của `groupingBy`.

Giả sử mỗi sale có `type` và `amount`:

~~~java
record Sale(String type, int amount) {}
record GroupStat(long count, int total) {}

Map<String, GroupStat> grouped = sales.stream().collect(
        Collectors.groupingBy(
                Sale::type,
                TreeMap::new,
                Collectors.teeing(
                        Collectors.counting(),
                        Collectors.summingInt(Sale::amount),
                        GroupStat::new))
);
~~~

Đây là mã **minh họa nhiều phần**: hai record phải được khai báo ở cấp kiểu, còn lời gọi `collect` trong phương thức với danh sách `sales` phù hợp; các tên kiểu có thể cần tránh đụng class Sale của phần 8. Đã kiểm chứng phiên bản độc lập của ví dụ bằng Java 17.

Nếu dữ liệu nhóm là:

~~~text
A: 2
B: 5
A: 3
~~~

thì kết quả:

~~~text
{A=GroupStat[count=2, total=5], B=GroupStat[count=1, total=5]}
~~~

Ở đây:
- `groupingBy` tạo nhóm theo `type`.
- Với từng nhóm, downstream là `teeing(counting(), summingInt(...), GroupStat::new)`.
- Kết quả của mỗi nhóm là một `GroupStat`, không phải danh sách phần tử.
- `TreeMap::new` quyết định thứ tự **khóa nhóm**, không quyết định cách hai downstream thống kê phần tử.

Đây là một ứng dụng mạnh của collector composition: **groupingBy + teeing** tạo báo cáo nhiều chỉ số cho mỗi khóa mà không cần viết vòng lặp gộp thủ công.

### 6.1. teeing có thể lồng với các collector khác không?

Có, miễn kiểu generic và contract tương thích. Downstream của teeing có thể là:
- `counting()`, `summingLong(...)`, `averagingDouble(...)`.
- `minBy(...)`, `maxBy(...)`.
- `mapping(..., toList())` để lấy danh sách một trường.
- `filtering(predicate, downstream)` để chỉ thống kê phần tử đạt điều kiện.
- `groupingBy(...)` để tạo cấu trúc Map theo khóa.
- Một `Collector.of(...)` tự định nghĩa, nếu tuân thủ các điều kiện collector.

Tuy nhiên, lồng quá nhiều collector có thể làm kiểu generic khó đọc. Một helper có tên nghiệp vụ hoặc một custom Collector thống kê có thể dễ bảo trì hơn, nhất là khi cần ba, bốn chỉ số và xử lý nhiều quy tắc đặc thù.

## 7. teeing khác gì với chạy hai terminal operation?

Xét hai cách:

**Cách A — Hai Stream tách riêng:**

~~~java
long count = sales.stream().count();
long total = sales.stream().mapToLong(Sale::revenue).sum();
Summary summary = ...;
~~~

Dòng `Summary summary = ...;` trong đoạn này là **pseudo-code**, không phải Java độc lập; mục đích chỉ diễn đạt cách ghép kết quả. Nếu nguồn là Collection có thể duyệt lại, cách A có thể đơn giản và chấp nhận được.

**Cách B — Một collect teeing:**

~~~java
Summary summary = sales.stream().collect(Collectors.teeing(
        Collectors.counting(),
        Collectors.summingLong(Sale::revenue),
        (count, total) -> new Summary(
                count, total,
                count == 0 ? OptionalDouble.empty()
                           : OptionalDouble.of((double) total / count))
));
~~~

Cách B mô tả việc tổng hợp thành **một kết quả R từ một lần thu thập Stream**, không cần tạo hai Stream. Điều này hữu ích khi dữ liệu đến từ một luồng có hợp đồng duyệt một lần hoặc khi báo cáo cần đóng gói nhiều phép thống kê có cùng nguồn.

### 7.1. Một pipeline không đồng nghĩa chỉ có một phép toán trên từng phần tử

`teeing` phân phối phần tử cho **cả hai downstream**, vì vậy có thể phát sinh chi phí của **hai phép tổng hợp** trên mỗi phần tử. Nó không tự động giảm số lần tính toán `Sale::revenue` nếu cả hai nhánh cùng gọi method này; ví dụ báo cáo theo vùng và tổng toàn lô đều có thể tính doanh thu theo nhu cầu riêng.

Nếu phép tính từ đầu vào đắt, có thể `map` dữ liệu thành một record trung gian đã tính sẵn rồi mới teeing:

~~~java
// Minh họa ý tưởng: một phép tính chuẩn hóa trước hai downstream.
// stream.map(this::calculateOnce)
//       .collect(Collectors.teeing(downstream1, downstream2, merger));
~~~

Đây là **pseudocode** với tên hàm giả định. Nếu thực hiện, phải bảo đảm bản ghi trung gian đủ thông tin cho cả hai collector và bước chuyển đổi không có side effect khó kiểm soát.

### 7.2. teeing không tự bảo đảm tăng tốc

Một `teeing` có thể duyệt nguồn trong một terminal operation nhưng vẫn phải duy trì **hai bộ trạng thái** và kết hợp chúng, có overhead. Với các chỉ số toán học đơn giản, `summarizingLong` hoặc một custom Collector có thể hiệu quả hơn. Hãy chọn theo tính rõ ràng trước, benchmark có dữ liệu đại diện nếu hiệu năng quan trọng.

### 7.3. Không thể tái sử dụng cùng Stream sau collect

~~~java
Stream<Sale> stream = sales.stream();
Summary result = stream.collect(...);

// Không được dùng lại cùng instance stream để gọi count()/collect() nữa.
~~~

Đây là mã **minh họa/pseudocode**: `...` đại diện cho collector phù hợp. Sau terminal operation `collect(...)`, Stream đã tiêu thụ; không dùng lại instance. Nếu nguồn là List, có thể tạo Stream mới từ chính List khi cần việc khác.

## 8. Ví dụ Java 17 hoàn chỉnh, có thể biên dịch và chạy

Tạo file **TeeingCollectorDemo.java**. Ví dụ thể hiện ba tình huống:

1. Tạo `Summary` gồm số đơn, doanh thu, trung bình có thể rỗng.
2. Tạo `Report` gồm tổng theo vùng và tổng toàn bộ bằng `parallelStream()`.
3. Tạo `Range` gồm min/max dạng Optional, kể cả nguồn rỗng.

~~~java
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.OptionalDouble;
import java.util.TreeMap;
import java.util.stream.Collectors;

public class TeeingCollectorDemo {
    record Sale(String region, int units, long unitPrice) {
        long revenue() {
            return Math.multiplyExact((long) units, unitPrice);
        }
    }

    record Summary(long orders, long revenue,
                   OptionalDouble averageRevenue) {}

    record Report(Map<String, Long> revenueByRegion,
                  long grandTotal) {}

    record Range(Optional<Integer> min, Optional<Integer> max) {}

    static Summary summarize(List<Sale> sales) {
        return sales.stream().collect(Collectors.teeing(
                Collectors.counting(),
                Collectors.summingLong(Sale::revenue),
                (count, total) -> new Summary(
                        count, total,
                        count == 0 ? OptionalDouble.empty()
                                   : OptionalDouble.of((double) total / count))
        ));
    }

    public static void main(String[] args) {
        List<Sale> sales = List.of(
                new Sale("North", 2, 100),
                new Sale("South", 1, 180),
                new Sale("North", 3, 50),
                new Sale("West", 1, 120)
        );

        System.out.println("summary=" + summarize(sales));
        System.out.println("empty=" + summarize(List.of()));

        Report report = sales.parallelStream().collect(Collectors.teeing(
                Collectors.groupingBy(
                        Sale::region,
                        TreeMap::new,
                        Collectors.summingLong(Sale::revenue)),
                Collectors.summingLong(Sale::revenue),
                Report::new));
        System.out.println("report=" + report);

        Range range = List.of(4, 9, 2, 7).stream()
                .collect(Collectors.teeing(
                        Collectors.minBy(Comparator.naturalOrder()),
                        Collectors.maxBy(Comparator.naturalOrder()),
                        Range::new));
        Range emptyRange = List.<Integer>of().stream()
                .collect(Collectors.teeing(
                        Collectors.minBy(Comparator.naturalOrder()),
                        Collectors.maxBy(Comparator.naturalOrder()),
                        Range::new));
        System.out.println("range=" + range);
        System.out.println("empty range=" + emptyRange);
    }
}
~~~

Chạy bằng JDK 17 trở lên:

~~~bash
javac --release 17 TeeingCollectorDemo.java
java TeeingCollectorDemo
~~~

**Stdout đã được kiểm chứng khi chạy bằng Java 17:**

~~~text
summary=Summary[orders=4, revenue=650, averageRevenue=OptionalDouble[162.5]]
empty=Summary[orders=0, revenue=0, averageRevenue=OptionalDouble.empty]
report=Report[revenueByRegion={North=350, South=180, West=120}, grandTotal=650]
range=Range[min=Optional[2], max=Optional[9]]
empty range=Range[min=Optional.empty, max=Optional.empty]
~~~

### 8.1. Đọc kết quả

- **Summary:** có bốn đơn, doanh thu 200 + 180 + 150 + 120 = **650**, trung bình **162,5** trên một đơn.
- **Empty Summary:** số đơn 0, tổng 0, trung bình **không xác định do không có dữ liệu** và được biểu diễn bằng `OptionalDouble.empty()`.
- **Report:** vùng North có 200 + 150 = **350**, South = **180**, West = **120**, tổng toàn bộ = **650**. Kết quả theo vùng được giữ trong TreeMap có thứ tự khóa tự nhiên.
- **Range:** min = 2, max = 9; hai downstream trả Optional chứa giá trị.
- **Empty Range:** min và max đều `Optional.empty()`; merger vẫn tạo record Range chứa hai trạng thái rỗng.

### 8.2. Vì sao kết quả report dùng parallelStream vẫn đúng?

Hai nhánh dùng collector chuẩn `groupingBy(..., summingLong(...))` và `summingLong(...)`, được áp dụng theo hợp đồng collector. Framework có thể phân vùng, thu thập riêng và kết hợp các trạng thái tổng hợp trước khi merger tạo Report.

Không có biến đếm mutable dùng chung từ lambda ngoài, và không dựa vào thứ tự thread để tính tổng. `TreeMap` được chọn để kiểm soát **thứ tự khóa của kết quả**, không phải để cho phép nhiều thread tự ý ghi vào cùng một Map không đồng bộ.

Chương trình này không có dữ liệu null và những số nhỏ không bị tràn long. Với dữ liệu nghiệp vụ thật, có thể bổ sung validation đơn giá/số lượng và chính sách xử lý overflow.

## 9. Nguồn rỗng và nghĩa của kết quả từ hai downstream

Một lợi ích của teeing là mỗi nhánh có quy tắc kết quả riêng trên Stream rỗng:

| Downstream | Kết quả điển hình khi rỗng |
| --- | --- |
| `counting()` | `0L` |
| `summingLong(...)` | `0L` |
| `toList()` | Danh sách rỗng |
| `minBy(...)` | `Optional.empty()` |
| `maxBy(...)` | `Optional.empty()` |
| `groupingBy(...)` | Map rỗng |

Merger sẽ nhận kết quả **sau finisher** của mỗi downstream, kể cả khi nguồn không có phần tử. Do đó, quyết định kết quả cuối R cần xử lý những trạng thái rỗng hợp lệ.

Ví dụ `average = total / count` phải tránh chia cho 0. Khi một nhánh trả Optional, merger không nên gọi `get()` vô điều kiện. Một báo cáo “min-max” có thể giữ nguyên Optional; một API khác có thể quyết định trả một lỗi nghiệp vụ nếu buộc phải có dữ liệu.

**Điểm quan trọng:** nguồn rỗng **không tự làm teeing thất bại**. Hành vi rỗng phụ thuộc hai downstream và merger; nếu bản thân merger chủ động ném exception trong trường hợp rỗng, đó là quyết định logic của code được viết, không phải một quy tắc chung của teeing.

## 10. Tee với downstream có điều kiện khác nhau

Hai nhánh có thể tổng hợp **hai tập con khác nhau** của cùng Stream đầu vào thông qua `Collectors.filtering(...)`:

~~~java
record Check(long accepted, long rejected) {}

Check result = orders.stream().collect(Collectors.teeing(
        Collectors.filtering(Order::valid, Collectors.counting()),
        Collectors.filtering(order -> !order.valid(), Collectors.counting()),
        Check::new
));
~~~

Đây là **mã minh họa nhiều phần**, cần đặt record ở cấp kiểu, có class `Order` cung cấp `valid()` và import `Collectors`. Với nguồn hợp lệ, nhánh thứ nhất đếm phần tử valid; nhánh thứ hai đếm phần tử không valid. Merger tạo một `Check(accepted,rejected)`.

Ưu điểm là hai quy tắc được biểu diễn bằng collector composition, không phải hai Stream riêng. Tuy nhiên:
- Hai predicate có thể được đánh giá riêng đối với cùng phần tử.
- Nếu `valid()` có side effect hoặc đọc trạng thái biến đổi, hai phép kiểm tra có thể không nhất quán.
- Nếu tập dữ liệu rất lớn và predicate đắt, cân nhắc một trạng thái tổng hợp riêng hoặc chuẩn hóa dữ liệu trước khi thu thập.
- Đảm bảo hai điều kiện thực sự đối nhau theo nghiệp vụ; nếu có “unknown” thứ ba, mô hình chỉ hai nhánh accepted/rejected có thể làm mất thông tin.

`Collectors.filtering(...)` trong ví dụ chỉ là một **downstream operation** của teeing, không giống `Stream.filter(...)` ngoài pipeline (vốn sẽ loại phần tử trước khi cả hai nhánh được nhận).

## 11. teeing trong Stream song song: hợp đồng an toàn

Một collector có thể được Stream framework dùng theo quy tắc chia nhóm và combine khi nguồn là parallel stream. Việc `teeing` có an toàn và hiệu quả hay không còn phụ thuộc hai downstream:

1. **Downstream phải tuân thủ hợp đồng Collector**: supplier tạo container đúng, accumulator và combiner kết hợp hợp lệ, finisher trả kết quả đúng.
2. **Đầu vào không bị sửa đồng thời một cách vi phạm contract nguồn**; classifier, mapper, predicate nên stateless, non-interfering.
3. **Merger không nên phụ thuộc vào thứ tự thread** hoặc trạng thái ngoài. Merger nhận hai kết quả tổng hợp cuối của downstream và tạo một R.
4. **Đặc tính của collector** (*characteristics*) phải được hiểu theo hai downstream. Không tự cho rằng teeing luôn concurrent, luôn unordered hoặc có identity finisher.
5. **Kết quả dùng container mutable** có thể cần sao chép/bảo vệ ở ranh giới trả ra ngoài nếu client không được phép sửa.

### 11.1. Đặc tính Collector không được suy từ tên teeing

`Collectors.teeing` xây dựng đặc tính từ đặc tính chung của hai downstream; không có `IDENTITY_FINISH` cho collector kết quả vì phải gọi merger để tạo R. Các đặc tính như `UNORDERED` hoặc `CONCURRENT` chỉ có thể được giữ khi đáp ứng điều kiện tương ứng từ **cả hai downstream**.

Không viết mã giả định `teeing(toList(), counting(), ...)` tự thành một concurrent collector chỉ vì Stream ở chế độ parallel. Việc framework gọi các downstream theo cách nào là phần của hợp đồng Collector và Stream implementation.

### 11.2. Tác dụng phụ và exception

Nếu một downstream mapper ném exception chưa được xử lý, phép `collect(teeing(...))` có thể thất bại; teeing **không tự chuyển lỗi thành kết quả Failure** hay rollback side effects đã xảy ra trước đó.

Nếu hai downstream đều gọi ra hệ thống ngoài (gửi HTTP, ghi database), việc mỗi phần tử được đưa vào cả hai nhánh có thể khiến chi phí và nguy cơ tác dụng phụ tăng gấp đôi. Collector được thiết kế để **tổng hợp dữ liệu**, không nên dùng như bộ điều phối giao dịch nhiều dịch vụ. Nếu cần all-or-nothing, transaction/commit design phải nằm ngoài việc chọn collector.

### 11.3. Không coi thứ tự thực thi là thứ tự đầu ra

Với collector Map có thứ tự như TreeMap, thứ tự **duyệt khóa của Map kết quả** được quyết định bởi TreeMap. Không vì thế mà suy ra một phần tử thuộc North đã được xử lý trước South trong các worker thread.

Nếu downstream dùng danh sách và nguồn có encounter order, kết quả của collector phải được xét theo contract cụ thể của downstream và pipeline. Khi cần thứ tự báo cáo ổn định, chọn cấu trúc có hợp đồng sắp xếp rõ ràng, tránh dựa vào logging từ callback để đoán.

## 12. Những lỗi thường gặp với teeing

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| Truyền kết quả đã tính thay vì Collector cho downstream | Sai kiểu / sai cú pháp | Truyền `Collectors.counting()`, `Collectors.summingLong(...)`... |
| Đảo thứ tự ý nghĩa R1/R2 trong merger | Trường báo cáo bị gán sai dù kiểu khớp | Đặt tên tham số merger theo hai downstream |
| Cho rằng teeing chỉ cần Java 8 | Không tìm thấy API trên JDK 8/11 | Dùng Java 12+; bài này nhắm Java 17 |
| Dùng `count==0 ? total/count : ...` sai điều kiện | Chia cho 0 | Trả Optional/nhánh xử lý khi count=0 |
| Gọi `Optional.get()` không kiểm tra trong merger | Có thể lỗi với nguồn rỗng | Dùng Optional đúng hợp đồng |
| Nghĩ teeing tự tính một mapper đắt đúng một lần | Hai downstream có thể gọi tính toán riêng | Tính trước bằng bước map nếu hợp lý |
| Nghĩ teeing luôn nhanh hơn hai Stream | Collector có overhead, không cam kết tốc độ | Benchmark trên dữ liệu thật |
| Nghĩ teeing luôn xử lý song song | Phụ thuộc Stream và collector | Chọn nguồn/chế độ đúng, không lạm dụng parallel |
| Dùng Map mặc định rồi trông chờ thứ tự khóa | Không được bảo đảm | Dùng mapFactory TreeMap/LinkedHashMap phù hợp |
| Sửa object ngoài trong accumulator | Race, side effects và khó kiểm thử | Giữ collector/predicate stateless, non-interfering |
| Xem record chứa Map là immutable sâu | Map bên trong có thể mutable | Thiết kế defensive copy/unmodifiable view phù hợp |
| Gọi lại Stream sau collect | Stream đã tiêu thụ | Tạo Stream mới nếu Collection tái duyệt được |

### 12.1. Lỗi thứ tự merger rất dễ lọt qua compiler

Nếu hai downstream cùng trả `Long`:

~~~java
Collectors.teeing(
        Collectors.counting(),
        Collectors.summingLong(Sale::revenue),
        (total, count) -> new Summary(count, total, OptionalDouble.empty())
)
~~~

Đây là **phản ví dụ về ngữ nghĩa**, đoạn minh họa nằm trong code có record Summary/Sale đã định nghĩa. Nó có thể biên dịch vì kiểu của hai tham số đều là Long, nhưng hai tên `total` và `count` đã **đặt ngược vị trí** so với collector. Kết quả Summary sẽ chứa dữ liệu bị tráo.

Cần viết:

~~~java
(count, total) -> new Summary(
        count,
        total,
        count == 0 ? OptionalDouble.empty()
                   : OptionalDouble.of((double) total / count))
~~~

Những ví dụ tên trường rõ ràng và kiểm thử đầu ra giúp phát hiện các lỗi loại này.

## 13. Khi nào nên dùng teeing, khi nào chọn cách khác?

| Bài toán | Gợi ý |
| --- | --- |
| Cần đồng thời **hai thống kê** từ cùng Stream và ghép thành record | `Collectors.teeing(...)` |
| Cần min/max cùng lúc nhưng không yêu cầu cấu trúc custom | `summarizingInt/Long/Double(...)` có thể rõ hơn |
| Cần thống kê theo từng nhóm, mỗi nhóm gồm hai chỉ số | `groupingBy(..., teeing(...))` |
| Chỉ cần một tổng số | `mapToLong(...).sum()` hoặc `summingLong(...)` |
| Muốn tổng hợp nhiều hơn hai nhánh | Lồng teeing khi vẫn dễ đọc, hoặc thiết kế Collector/statistics object riêng |
| Cần cập nhật container mutable đặc thù | `collect(Collector.of(...))`/custom Collector nếu thật sự cần |
| Cần chạy nhiều side effects cho từng phần tử | Không dùng teeing như giao dịch; dùng luồng xử lý hành động rõ ràng |
| Dự án phải chạy Java 8/11 | Không dùng teeing JDK; dùng giải pháp thay thế tương thích |

### 13.1. Lồng teeing nhiều lớp có tốt không?

Có thể lồng để ghép ba phép tổng hợp:

~~~java
// Minh họa dạng cấu trúc:
Collectors.teeing(
    firstCollector,
    Collectors.teeing(secondCollector, thirdCollector, Pair::new),
    (first, pair) -> ...
)
~~~

Đây là **pseudocode**; `firstCollector`, `Pair` và `...` cần định nghĩa trong project. Về mặt loại dữ liệu, lồng teeing được vì mỗi nhánh nhận một Collector và trả R, nhưng với báo cáo phức tạp, một custom Collector có cấu trúc thống kê rõ thường dễ đọc, dễ test và có thể tránh tính toán lặp.

### 13.2. Có thể dùng record làm merger không?

Có. Nếu các kiểu của constructor record trùng với R1 và R2, method reference như `Report::new` hoặc `Range::new` là một merger hợp lệ. Đây là cách giảm boilerplate và giữ rõ hình dạng dữ liệu.

Nếu cần thêm validation, chuyển đổi đơn vị hoặc chính sách giá trị rỗng, dùng lambda có tên tham số rõ thay vì `::new` để thể hiện logic đó.

## 14. Checklist triển khai một collector teeing

Trước khi viết `collect(Collectors.teeing(...))`, hãy tự hỏi:

1. **Hai kết quả cần là gì?** Mỗi downstream có tính đúng một thống kê cần dùng không?
2. **Kiểu R1/R2/R có phù hợp không?** Thứ tự đối số của merger có khớp thứ tự downstream không?
3. **Nguồn có thể rỗng không?** Hai downstream trả gì và merger cần xử lý Optional/0 ra sao?
4. **Thứ tự đầu ra có quan trọng không?** Với Map hãy chọn mapFactory; với List kiểm tra encounter order.
5. **Bài toán có API chuyên dụng tốt hơn không?** Xem `summarizing...`, `counting`, `summing...`.
6. **Hai nhánh có lặp lại phép tính đắt không?** Nếu có, cân nhắc tạo dữ liệu trung gian một lần.
7. **Collector và lambda có stateless/non-interfering không?** Tránh sửa nguồn hoặc shared mutable state.
8. **Có chạy parallel không?** Kiểm tra collector characteristics, combiner và không dựa vào lịch thread.
9. **Merger có tạo trạng thái an toàn để trả API không?** Record chứa List/Map chưa chắc immutable sâu.
10. **Có overflow hoặc độ chính xác số học không?** Chọn kiểu/exception/rounding theo nghiệp vụ.
11. **Có cần hỗ trợ Java 8/11 không?** `Collectors.teeing` được giới thiệu từ Java 12.
12. **Đã kiểm thử nguồn rỗng, một phần tử và dữ liệu nhiều nhóm chưa?** Những ca này thường lộ lỗi merger.

## 15. Bài tập tự kiểm tra

**Bài 1.** Muốn tính cả số phần tử và tổng một trường số của danh sách, phải dùng thành phần nào?

**Đáp án:** hai collector như `counting()` và `summingLong(...)`, cộng một merger để tạo record/DTO chứa hai kết quả.

**Bài 2.** Trong `teeing(downstream1, downstream2, merger)`, đối số đầu của merger là R1 hay R2?

**Đáp án:** R1, kết quả của downstream thứ nhất. Tham số thứ hai là R2.

**Bài 3.** Nếu nguồn rỗng, `teeing(minBy(...), maxBy(...), Range::new)` có tự ném exception không?

**Đáp án:** Không; hai downstream `minBy/maxBy` trả Optional.empty, còn merger nhận hai Optional để tạo Range. Chỉ khi code của merger không xử lý đúng hoặc chủ động ném lỗi mới thất bại.

**Bài 4.** Tại sao một Summary có cả `count` và `revenue` giúp tính trung bình dễ hơn?

**Đáp án:** merger có đủ hai kết quả để tính `revenue/count` và phát hiện count=0, tránh đánh đồng không có dữ liệu với mức trung bình 0.

**Bài 5.** Muốn vừa nhóm theo `region`, vừa tính tổng của tất cả region, có thể làm trong một collect không?

**Đáp án:** Có, dùng `teeing(groupingBy(...), summingLong(...), Report::new)`.

**Bài 6.** Muốn với mỗi khóa region có một record chứa count và total thì lồng collector nào?

**Đáp án:** `groupingBy(Sale::region, mapFactory, teeing(counting(), summingLong(...), GroupStat::new))`.

**Bài 7.** `teeing` có bảo đảm tăng tốc gấp đôi so với chạy hai pipeline riêng không?

**Đáp án:** Không. Nó phối hợp hai downstream trong một collect, nhưng vẫn tính cả hai phép tổng hợp và có overhead. Đo benchmark khi hiệu năng là yêu cầu.

**Bài 8.** Nếu cả hai downstream có kiểu kết quả Long, compiler có phát hiện ta đặt nhầm tên count và total trong merger không?

**Đáp án:** Không nhất thiết. Cả hai cùng kiểu nên có thể biên dịch dù gán trường sai; test giá trị và đặt tên đúng rất quan trọng.

**Bài 9.** Dùng teeing để ghi hai database trong một transaction có tự bảo đảm all-or-nothing không?

**Đáp án:** Không. teeing là Collector dùng để tổng hợp dữ liệu; transactional consistency phải được thiết kế riêng.

**Bài 10.** Vì sao `record Report(Map<String,Long> totals, long grandTotal)` chưa đảm bảo bất biến sâu?

**Đáp án:** record bảo vệ reference không bị thay thế, nhưng Map vẫn có thể là container mutable. Muốn public DTO không bị sửa cần chính sách sao chép/bọc phù hợp.

## 16. Tài liệu tham khảo

- [Java SE 17 — Collectors.teeing](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Collectors.html#teeing(java.util.stream.Collector,java.util.stream.Collector,java.util.function.BiFunction)).
- [Java SE 17 — Collector: supplier, accumulator, combiner, finisher và characteristics](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Collector.html).
- [Java SE 17 — Collectors.groupingBy, counting, summingLong, minBy, maxBy](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Collectors.html).
- [Java SE 17 — Stream.collect](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html#collect(java.util.stream.Collector)).
- [Java SE 17 — Optional và OptionalDouble](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Optional.html).

**Ghi nhớ:** **`Collectors.teeing(downstream1, downstream2, merger)`** cho phép đưa cùng các phần tử Stream qua hai phép tổng hợp và **ghép hai kết quả R1/R2 thành một R trong một collect**. Nó phù hợp cho báo cáo có hai chỉ số, min/max, thống kê nhóm lồng nhau hoặc kết hợp Map và tổng toàn cục. Chọn downstream đúng, kiểm tra nguồn rỗng, ghi rõ thứ tự tham số merger, giữ callback an toàn và không coi teeing là cam kết tăng tốc hay cơ chế giao dịch.
