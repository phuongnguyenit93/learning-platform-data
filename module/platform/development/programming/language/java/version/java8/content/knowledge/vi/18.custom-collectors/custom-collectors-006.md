# Accumulator riêng cho mỗi phân hoạch trong custom Collector của Java Stream

## Mục tiêu bài học

Sau bài học này, bạn có thể:

1. Giải thích vì sao một Collector không concurrent vẫn có thể được dùng an toàn với parallelStream(), ngay cả khi vùng tích lũy là ArrayList, HashMap hoặc một object mutable tự viết.
2. Phân biệt **phần tử đầu vào T**, **vùng tích lũy trung gian A** và **kết quả cuối R** trong Collector<T, A, R>.
3. Mô tả đúng vai trò của supplier, accumulator, combiner, finisher và mối liên hệ giữa chúng khi Stream được chia thành các phần xử lý.
4. Hiểu câu “accumulator riêng cho mỗi phân hoạch” là mô hình **cô lập vùng tích lũy của collector không CONCURRENT**, không phải lời hứa “mỗi thread có đúng một container”.
5. Thiết kế Collector.of(...) bảo đảm có kết quả đúng ở cả stream tuần tự và song song.
6. Nhận biết khi nào một collector thực sự được phép tích lũy đồng thời trên cùng container (CONCURRENT), và những điều kiện an toàn bắt buộc.
7. Tránh các lỗi supplier trả object dùng chung, combiner làm mất dữ liệu, side effect, đánh dấu characteristics sai và dùng mutable identity trong reduce.

**Phạm vi phiên bản:** Collector, Collector.of, Stream.collect và Collector.Characteristics xuất hiện từ Java 8 và tiếp tục là API Stream hiện hành. Ví dụ trong bài dùng Java 17+ để dễ biên dịch/chạy trên JDK hiện đại. Bài không dựa vào API đã legacy hoặc cơ chế triển khai nội bộ không được Java bảo đảm.

## 1. Vì sao cần accumulator riêng khi phân hoạch?

Một phép thu thập (*mutable reduction*) biến các phần tử Stream thành một kết quả bằng cách cập nhật cấu trúc trung gian: thêm phần tử vào List, tăng bộ đếm, cộng các số, cập nhật Map hoặc ghi nhận thống kê.

Với stream tuần tự, có thể hình dung một container được tạo và nhận lần lượt các phần tử:

~~~text
Nguồn: [A, B, C, D]
           |
       supplier()
           |
        container
           |
    accumulator(A)
    accumulator(B)
    accumulator(C)
    accumulator(D)
           |
       finisher()
           |
       kết quả cuối
~~~

Với stream song song và **collector thông thường không CONCURRENT**, thư viện có thể chia công việc thành các phần. Từng phần tích lũy vào container riêng, rồi các kết quả trung gian được hợp nhất:

~~~text
             [A, B, C, D]
                  |
             chia công việc
             /           \
          [A,B]         [C,D]
            |             |
       supplier()     supplier()
            |             |
       container 1    container 2
            |             |
       add(A),add(B)  add(C),add(D)
            |             |
            +----combiner-+
                    |
              merged state
                    |
                finisher
                    |
               kết quả cuối
~~~

Sơ đồ này chỉ minh họa một chiến lược hợp lệ. Java **không cam kết** chỉ có hai nhánh, số lần gọi supplier cụ thể, một container đúng bằng một CPU core, hoặc một container cố định cho từng worker thread. Điều quan trọng là hợp đồng về tính cô lập và khả năng ghép đúng.

**Ý chính:** Nếu collector không có đặc tính CONCURRENT, kết quả trung gian phải được quá trình reduction sử dụng theo kiểu *serially thread-confined*: một container không bị nhiều accumulator cùng cập nhật đồng thời. Nhờ vậy, **container không nhất thiết phải là cấu trúc thread-safe**. Song song xảy ra giữa các container độc lập; combiner xử lý việc nhập chúng.

## 2. Bốn thành phần của Collector và ý nghĩa T, A, R

Collector<T, A, R> có ba tham số kiểu:

| Ký hiệu | Ý nghĩa | Ví dụ |
|---|---|---|
| T | Kiểu của từng phần tử Stream | String, Sale |
| A | Kiểu trạng thái tích lũy trung gian | ArrayList<String>, MutableStats |
| R | Kiểu kết quả sau khi hoàn tất | List<String>, Summary record |

Các hàm then chốt:

| Hàm | Dạng ý nghĩa | Trách nhiệm |
|---|---|---|
| supplier | () -> A | Cung cấp một **container mới** mỗi khi được gọi |
| accumulator | (A, T) -> void | Gộp một phần tử vào container tương ứng |
| combiner | (A, A) -> A | Ghép hai container trung gian thành một container hợp lệ |
| finisher | A -> R | Chuyển trạng thái trung gian thành kết quả cuối |

Một cách xây dựng reusable collector:

~~~java
Collector<T, A, R> custom = Collector.of(
        supplier,
        accumulator,
        combiner,
        finisher
);
~~~

Đây là **chữ ký minh họa**, không phải tệp biên dịch độc lập vì T, A, R và bốn biến chức năng chưa được khai báo. Các overload Collector.of(...) nhận các hàm tương ứng và có thể nhận thêm đặc tính (Characteristics).

### Supplier là “nhà máy” tạo vùng tích lũy

~~~java
ArrayList::new
~~~

mô tả việc **tạo một ArrayList mới mỗi lần** thư viện yêu cầu. Đối với một collector thường, mỗi container phải khởi đầu ở trạng thái rỗng/trung hòa thích hợp.

Hai biểu thức không tương đương:

~~~java
// ĐÚNG: một đối tượng mới được tạo mỗi lần supplier được gọi.
() -> new java.util.ArrayList<String>()

// SAI: mọi lần gọi trả lại cùng đối tượng đã có.
java.util.List<String> shared = new java.util.ArrayList<>();
() -> shared
~~~

Đây là các **mảnh mã biểu đạt ý tưởng**, không phải các câu lệnh đặt nối tiếp thành một chương trình. Supplier dùng chung như ở dòng cuối phá vỡ mô hình cô lập; song song có thể gây race condition, sai số lượng phần tử, dữ liệu lặp hoặc lỗi cấu trúc.

### Accumulator là hàm, container mới là trạng thái

Tên **accumulator** vừa thường được dùng để chỉ hàm (A, T) -> void, vừa được dùng trong hội thoại để chỉ container A. Cần phân biệt:

- Hàm accumulator là logic chung, có thể được framework gọi nhiều lần.
- Container A là trạng thái trung gian cần được cô lập khi collector không concurrent.
- Không bắt buộc tạo **một bản sao hàm lambda** cho từng phân hoạch; điều cần tách là **dữ liệu mutable** mà lambda thao tác.

Ví dụ, nhiều lần gọi List::add đều dùng cùng chức năng nhưng mỗi lần có thể áp dụng lên một List trung gian khác nhau.

## 3. Quy tắc cô lập: không đồng nghĩa với “mỗi thread có một accumulator”

Tài liệu Java quy định với **non-concurrent collector**, đối tượng trung gian phát sinh từ supplier, accumulator hoặc combiner phải được sử dụng sao cho không có hai lời gọi tích lũy đang cạnh tranh trên cùng object. Vì vậy một ArrayList được tạo riêng có thể dùng trong parallel reduction mà không cần đồng bộ hóa ở bản thân ArrayList.

Nhưng không nên suy ra:

- **Không bảo đảm một container trên mỗi thread:** scheduler có thể thay đổi cách phân hoạch; số task, thread, container có thể khác số phần tử hoặc số lõi CPU.
- **Không bảo đảm mỗi thread chỉ chạm một container suốt vòng đời:** cần tư duy về quyền truy cập *tại một thời điểm*, không tự áp đặt thread affinity.
- **Không bảo đảm supplier gọi bao nhiêu lần:** có thể một lần hoặc nhiều lần tùy dữ liệu và chiến lược thực thi.
- **Không có lời hứa combiner sẽ luôn được gọi:** pipeline tuần tự thường không cần ghép; một số cách thực hiện song song có thể lựa chọn chiến lược khác.
- **Không có lời hứa combiner chạy theo thứ tự gọi cố định:** mã phải tuân theo quy tắc tương đương kết quả và giữ encounter order nếu collector yêu cầu.

Để kiểm tra tính đúng, hãy xem supplier, accumulator, combiner và finisher như một **hợp đồng đại số**. Đừng dựa vào quan sát “hôm nay chạy thấy có bốn container” để quyết định thiết kế.

## 4. Ví dụ 1 — ArrayList riêng cho mỗi kết quả trung gian

Một collector tùy biến tối giản: mỗi supplier tạo ArrayList; accumulator thêm String; combiner nối nội dung container bên phải sang container bên trái.

Tạo tệp **PartitionListCollector.java**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Collector;

public class PartitionListCollector {
    public static void main(String[] args) {
        List<String> names = List.of("An", "Binh", "Chi", "Dung");

        Collector<String, List<String>, List<String>> collector =
                Collector.of(
                        ArrayList::new,
                        List::add,
                        (left, right) -> {
                            left.addAll(right);
                            return left;
                        }
                );

        List<String> result = names.parallelStream()
                .collect(collector);

        System.out.println("items=" + result);
        System.out.println("size=" + result.size());
    }
}
~~~

Biên dịch/chạy bằng JDK 17+:

~~~text
javac --release 17 PartitionListCollector.java
java PartitionListCollector
~~~

Kết quả:

~~~text
items=[An, Binh, Chi, Dung]
size=4
~~~

**Giải thích từng thành phần:**

1. **Supplier ArrayList::new:** mỗi lần được gọi tạo một List mới, ban đầu rỗng.
2. **Accumulator List::add:** thay đổi duy nhất List được truyền vào, không ghi ra biến List toàn cục.
3. **Combiner:** nhập phần tử của right vào left, rồi trả left; kết quả có đủ phần tử từ cả hai nhánh.
4. **Finisher:** overload ba hàm Collector.of(supplier, accumulator, combiner) sử dụng identity finisher; ở đây A và R đều là List<String>.
5. **Thứ tự:** nguồn List có encounter order, collector không khai báo UNORDERED, nên kết quả phải bảo toàn thứ tự phần tử khi ghép. Đừng đổi cách kết hợp thành right.addAll(left) nếu muốn giữ thứ tự đó.

ArrayList thông thường không thread-safe, nhưng collector **không khai báo CONCURRENT**, nên cách dùng song song ở đây vẫn đúng hợp đồng vì framework bảo đảm cô lập trạng thái trung gian trong giai đoạn tích lũy.

**Điều không nên làm:** thêm Collector.Characteristics.CONCURRENT chỉ để “tối ưu” collector này. Nếu cùng một ArrayList nhận nhiều List::add từ các thread khác nhau, thiết kế sẽ có race condition. Đặc tính CONCURRENT là **cam kết an toàn của collector**, không phải lệnh yêu cầu JVM tự đồng bộ hóa.

### Tại sao combiner phải trả lại kết quả đã gộp?

~~~java
// ĐÚNG với collector List có thứ tự:
(left, right) -> {
    left.addAll(right);
    return left;
}

// SAI: làm rơi toàn bộ dữ liệu bên phải:
(left, right) -> left
~~~

Hai đoạn là **mảnh mã**. Dòng sai có thể không bộc lộ trong stream tuần tự vì combiner không nhất thiết được gọi; khi song song, dữ liệu từ nhiều container có thể bị bỏ mất.

## 5. Quy tắc identity, associativity và tương đương kết quả

Collector phải cho kết quả tương đương dù framework tổ chức tích lũy và ghép các phần theo cách hợp lệ khác nhau.

### 5.1. Identity của container trung gian

Supplier phải tạo trạng thái trung hòa. Với List, trạng thái trung hòa là List rỗng. Với thống kê (count, total), đó là (0, 0).

Nếu a là kết quả tích lũy bất kỳ và e là trạng thái rỗng do supplier tạo, ghép a với e phải có kết quả **tương đương** a:

~~~text
combine(a, empty) ≡ a
~~~

Dấu ≡ ở đây nhấn mạnh **kết quả quan sát được bằng nhau**, không nhất thiết hai tham chiếu object phải trùng nhau. Với collector thay đổi object mutable, combiner có thể trả một object trong hai đối tượng hoặc object mới nếu tuân thủ hợp đồng.

### 5.2. Tính kết hợp (associativity) của phép ghép

Với các kết quả trung gian a, b, c:

~~~text
combine(combine(a, b), c) ≡ combine(a, combine(b, c))
~~~

Đối với List có thứ tự, thao tác nối danh sách bảo đảm nội dung cuối giống nhau khi **đổi vị trí dấu ngoặc**, miễn vẫn giữ thứ tự nhóm a, b, c. Không được tự ý đổi thứ tự ba nhóm nếu collector phải bảo toàn encounter order.

### 5.3. Accumulator và combiner phải tương thích

Nếu một phần chứa các phần tử x, y và phần khác chứa z, ghép hai trạng thái trung gian phải tương đương với tích lũy trực tiếp toàn bộ phần tử theo quy tắc thứ tự của collector:

~~~text
stateLeft  = accumulate(empty, [x, y])
stateRight = accumulate(empty, [z])

finish(combine(stateLeft, stateRight))
      ≡ finish(accumulate(empty, [x, y, z]))
~~~

Đây là biểu diễn **ngữ nghĩa**, không phải chữ ký API Java. Với phép tính trung bình, không được lấy “trung bình hai giá trị average” nếu số phần tử từng nhóm khác nhau; hãy giữ count và sum để ghép chính xác.

### 5.4. Tránh công thức dựa trên trạng thái dùng chung

Không thể chứng minh tính đúng chỉ bằng phép tính trên từng nhóm nếu accumulator hoặc combiner âm thầm đọc/ghi một biến mutable bên ngoài. Ví dụ bộ đếm dùng chung sẽ tạo phụ thuộc vào lịch thực thi, còn phép nối List trùng object có thể nhân đôi dữ liệu.

Tính **associative của phép ghép**, **identity đúng**, **stateless/non-interfering của hành vi** và **phân tách container** phải được kiểm tra cùng nhau.

## 6. Ví dụ 2 — Mutable accumulator riêng, kết quả cuối bất biến

Trong bài toán thực tế, cần vừa đếm đơn hàng vừa tính tổng số tiền theo vùng. Thiết kế một trạng thái mutable dùng nội bộ, nhưng trả về một record bất biến sau khi hoàn tất.

- Kiểu đầu vào T: Sale.
- Kiểu trung gian A: MutableTotals.
- Kiểu kết quả R: Summary.
- Supplier tạo mỗi MutableTotals với count=0 và total=0.
- Accumulator cộng một đơn hàng vào đúng MutableTotals đó.
- Combiner cộng hai MutableTotals, trả về một kết quả trung gian hợp lệ.
- Finisher biến MutableTotals thành Summary.

Tạo tệp **PartitionedSalesReport.java**:

~~~java
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collector;
import java.util.stream.Collectors;

public class PartitionedSalesReport {
    record Sale(String region, long cents) {}
    record Summary(long count, long totalCents) {}

    static final class MutableTotals {
        private long count;
        private long totalCents;

        void add(Sale sale) {
            count++;
            totalCents += sale.cents();
        }

        MutableTotals merge(MutableTotals other) {
            count += other.count;
            totalCents += other.totalCents;
            return this;
        }

        Summary finish() {
            return new Summary(count, totalCents);
        }
    }

    public static void main(String[] args) {
        List<Sale> sales = List.of(
                new Sale("North", 150),
                new Sale("South", 230),
                new Sale("North", 70),
                new Sale("West", 50)
        );

        Collector<Sale, MutableTotals, Summary> totalsCollector =
                Collector.of(
                        MutableTotals::new,
                        MutableTotals::add,
                        MutableTotals::merge,
                        MutableTotals::finish
                );

        Summary sequential = sales.stream()
                .collect(totalsCollector);

        Summary parallel = sales.parallelStream()
                .collect(totalsCollector);

        Map<String, Summary> byRegion = sales.parallelStream()
                .collect(Collectors.groupingBy(
                        Sale::region,
                        TreeMap::new,
                        totalsCollector
                ));

        System.out.println("sequential=" + sequential);
        System.out.println("parallel=" + parallel);
        System.out.println("byRegion=" + byRegion);
    }
}
~~~

Chạy:

~~~text
javac --release 17 PartitionedSalesReport.java
java PartitionedSalesReport
~~~

Kết quả:

~~~text
sequential=Summary[count=4, totalCents=500]
parallel=Summary[count=4, totalCents=500]
byRegion={North=Summary[count=2, totalCents=220], South=Summary[count=1, totalCents=230], West=Summary[count=1, totalCents=50]}
~~~

**Tại sao chương trình đúng khi song song?**

- Mỗi lần supplier được gọi, MutableTotals::new trả một object riêng; không có field static chứa kết quả đang cập nhật.
- MutableTotals.add chỉ thay đổi trạng thái của object A mà framework giao; nó không thay đổi Sale hoặc List nguồn.
- MutableTotals.merge gộp count và totalCents theo phép cộng; cả hai phép cộng đều có phần tử trung hòa 0 và có tính kết hợp theo ngữ nghĩa số nguyên Java.
- MutableTotals.finish trả một record Summary mới; consumer của collect nhận kết quả tách khỏi đối tượng tích lũy nội bộ.
- Với groupingBy(..., totalsCollector), từng nhóm vùng có các trạng thái downstream thích hợp. Kết quả cuối được đặt trong TreeMap nên thứ tự khóa của output ổn định.

**Lưu ý kiểu số:** long vẫn có miền hữu hạn; nếu tổng tiền nghiệp vụ có nguy cơ vượt giới hạn long hoặc yêu cầu số thập phân chính xác ngoài đơn vị nhỏ nhất, cần chọn kiểu phù hợp (chẳng hạn BigInteger hoặc BigDecimal với chính sách làm tròn rõ ràng). Không suy diễn “an toàn thread” thành “an toàn tràn số”.

**Lưu ý mutability:** combiner thay đổi object bên trái và trả nó; sau khi kết hợp, framework không tiếp tục dùng object trung gian bị loại bỏ theo cách vi phạm hợp đồng Collector. Ứng dụng không nên giữ tham chiếu của các container này bên ngoài pipeline.

### Vì sao không khai báo IDENTITY_FINISH?

Ở ví dụ trên:

~~~text
A = MutableTotals
R = Summary
~~~

Đây là hai kiểu khác nhau. Finisher thực hiện chuyển đổi thật, nên **không được gắn Collector.Characteristics.IDENTITY_FINISH**. Nếu làm vậy, framework có thể bỏ qua finisher theo hợp đồng characteristics và trả object không đúng kiểu R.

## 7. Hai API collect dễ bị nhầm

Có hai cách thu thập thường gặp:

### 7.1. Stream.collect(supplier, accumulator, combiner)

~~~java
ArrayList<String> result = names.parallelStream().collect(
        ArrayList::new,
        ArrayList::add,
        (left, right) -> left.addAll(right)
);
~~~

Đây là **mảnh mã** dùng names ở mục 4. Trong overload của Stream này, combiner là **BiConsumer<R, R>**: nó chỉ cần cập nhật object thứ nhất; không trả một kết quả. Đây là lý do biểu thức dạng block dưới đây dễ nhận biết:

~~~java
(left, right) -> {
    left.addAll(right);
}
~~~

### 7.2. Stream.collect(Collector.of(...))

~~~java
Collector<String, List<String>, List<String>> collector =
        Collector.of(
                ArrayList::new,
                List::add,
                (left, right) -> {
                    left.addAll(right);
                    return left;
                }
        );
~~~

Đây là **mảnh mã** tương tự mục 4. Trong Collector.of, combiner là **BinaryOperator<A>** và **phải trả về** trạng thái đã ghép. Không thể bê nguyên lambda dùng cho overload ba tham số của Stream sang Collector.of mà bỏ câu return.

**Chọn thế nào?** Nếu chỉ thu thập một lần, Stream.collect(supplier, accumulator, combiner) có thể đủ. Nếu muốn reusable Collector, kết hợp downstream như groupingBy, có finisher riêng hoặc cần khai báo chính xác characteristics, dùng Collector.of hoặc triển khai Collector. Với bài toán phổ biến, ưu tiên các collector chuẩn như toList, groupingBy, counting, summarizingInt thay vì tự viết một collector tương đương không cần thiết.

## 8. Collector.Characteristics: khi nào các container có thể được chia sẻ?

Collector.Characteristics có ba đặc tính quan trọng:

| Đặc tính | Ý nghĩa | Cần chú ý |
|---|---|---|
| CONCURRENT | Container hỗ trợ nhiều lần gọi accumulator đồng thời trên **cùng một object A** | Chính code tích lũy phải an toàn trước truy cập đồng thời |
| UNORDERED | Kết quả collector không cam kết bảo toàn encounter order của phần tử | Không dùng nếu thứ tự là yêu cầu nghiệp vụ |
| IDENTITY_FINISH | Finisher tương đương identity function, A có thể được dùng như R | Không dùng nếu A và R khác nhau hoặc finisher chuyển đổi dữ liệu |

Không được hiểu rằng đánh dấu CONCURRENT khiến ArrayList hay HashMap tự động an toàn. Characteristics là **mô tả hợp đồng collector cung cấp cho framework**.

### Khi nào xảy ra concurrent reduction?

Theo hợp đồng Stream API, giảm đồng thời trên một container có thể được sử dụng khi:

1. Stream chạy song song.
2. Collector khai báo CONCURRENT.
3. Stream là unordered **hoặc** Collector khai báo UNORDERED.

Với collector thỏa các điều kiện trên, framework **có thể** cho nhiều thread dùng cùng một container đồng thời thay vì luôn tạo các container độc lập. Vì thế công thức “mỗi phân hoạch một accumulator riêng” **không còn là mô tả tổng quát** cho tất cả Collector.

Đối với collector chỉ có CONCURRENT mà không có UNORDERED và nguồn có encounter order, không nên giả định được phép tích lũy đồng thời phá vỡ thứ tự. Chỉ đánh dấu UNORDERED nếu kết quả không quan tâm thứ tự.

### So sánh rõ hai trường hợp

~~~text
Collector thường, không CONCURRENT:
  task A -> mutable A1
  task B -> mutable A2
  task C -> mutable A3
  combiner(A1, A2, A3) -> một kết quả
  Container A1/A2/A3 không cần đồng bộ hóa khi tích lũy.

Collector có CONCURRENT, đủ điều kiện unordered:
  task A ----\
  task B -----+--> cùng container đồng thời
  task C ----/
  Accumulator và cấu trúc A phải tự hỗ trợ concurrency.
~~~

Đây là hai **chiến lược có thể có**, không phải lịch thực thi cụ thể JVM buộc phải chọn. Không đếm số lời gọi supplier hoặc combiner để suy ra kết luận cố định về Java API.

## 9. Ví dụ 3 — Một collector thực sự concurrent

Muốn đếm số lần xuất hiện của mỗi chuỗi mà không cần thứ tự, có thể dùng collector concurrent. Ví dụ sau giữ kết quả trung gian trong ConcurrentHashMap<String, LongAdder>:

- ConcurrentHashMap hỗ trợ cập nhật map đồng thời.
- computeIfAbsent chọn đúng LongAdder theo khóa.
- LongAdder hỗ trợ nhiều lần tăng cùng lúc, phù hợp bộ đếm thống kê không yêu cầu đọc giá trị tuyến tính tức thì trong khi cập nhật.
- Combiner vẫn được cài đặt đúng để framework có thể chọn chiến lược nhập hai container trung gian.
- Finisher được gọi khi tích lũy hoàn tất và tạo TreeMap<String, Long> để in ổn định.

Tạo tệp **ConcurrentWordCount.java**:

~~~java
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.LongAdder;
import java.util.function.Function;
import java.util.stream.Collector;
import java.util.stream.Collectors;

public class ConcurrentWordCount {
    public static void main(String[] args) {
        List<String> words = List.of(
                "red", "blue", "red", "green", "blue", "red"
        );

        Collector<
                String,
                ConcurrentHashMap<String, LongAdder>,
                Map<String, Long>
        > concurrentCount = Collector.of(
                ConcurrentHashMap::new,
                (map, word) -> map.computeIfAbsent(
                        word, ignored -> new LongAdder()
                ).increment(),
                (left, right) -> {
                    right.forEach((word, count) ->
                            left.computeIfAbsent(
                                    word, ignored -> new LongAdder()
                            ).add(count.sum())
                    );
                    return left;
                },
                intermediate -> {
                    Map<String, Long> output = new TreeMap<>();
                    intermediate.forEach((word, count) ->
                            output.put(word, count.sum())
                    );
                    return output;
                },
                Collector.Characteristics.CONCURRENT,
                Collector.Characteristics.UNORDERED
        );

        Map<String, Long> custom = words.parallelStream()
                .unordered()
                .collect(concurrentCount);

        ConcurrentMap<String, Long> builtIn = words.parallelStream()
                .unordered()
                .collect(Collectors.groupingByConcurrent(
                        Function.identity(),
                        Collectors.counting()
                ));

        System.out.println("custom=" + custom);
        System.out.println("builtIn=" + new TreeMap<>(builtIn));
    }
}
~~~

Chạy:

~~~text
javac --release 17 ConcurrentWordCount.java
java ConcurrentWordCount
~~~

Kết quả:

~~~text
custom={blue=2, green=1, red=3}
builtIn={blue=2, green=1, red=3}
~~~

**Điểm khác với ví dụ ArrayList:**

- Collector đã khai báo CONCURRENT và UNORDERED, nên accumulator **phải** an toàn ngay cả khi cùng một Map/LongAdder được cập nhật bởi nhiều luồng.
- LongAdder.sum() không phải phép đọc nguyên tử trong lúc nhiều thread đang tăng; ở đây finisher chụp kết quả **sau** khi quá trình thu thập hoàn thành.
- Finisher trả Map<String, Long>, khác A; vì thế không khai báo IDENTITY_FINISH.
- Các từ được đếm độc lập, kết quả không phụ thuộc thứ tự gặp. TreeMap chỉ giúp output ổn định.
- Collectors.groupingByConcurrent(..., counting()) đã cung cấp collector chuẩn cho yêu cầu này; ví dụ tự viết dùng để hiểu ranh giới thread-safety, không phải mặc nhiên là lựa chọn đơn giản nhất.

**Đừng sử dụng tính concurrent khi nghiệp vụ cần thứ tự phần tử.** Nếu muốn danh sách tên giữ encounter order, collector thường với List và combiner phù hợp sẽ rõ ràng hơn.

## 10. Những lỗi phổ biến với accumulator theo phân hoạch

### 10.1. Supplier trả lại chung một object

~~~java
List<String> shared = new ArrayList<>();

Collector<String, List<String>, List<String>> broken =
        Collector.of(
                () -> shared,
                List::add,
                (left, right) -> {
                    left.addAll(right);
                    return left;
                }
        );
~~~

**Mảnh mã phản ví dụ, không chạy trên dữ liệu thật.** Khi supplier được gọi nhiều lần, mọi nhánh nhận cùng object. Combiner có thể ghép object với chính nó, gây nhân đôi dữ liệu; nếu tích lũy đồng thời vào một ArrayList, có thể xảy ra race condition. **Supplier phải trả về container mới thực sự**, không phải tham chiếu tới biến field/static được chia sẻ.

### 10.2. Dùng reduce với mutable identity dùng chung

~~~java
// PHẢN VÍ DỤ: dùng reduce với một ArrayList mutable làm identity.
List<String> broken = names.parallelStream().reduce(
        new ArrayList<String>(),
        (list, name) -> {
            list.add(name);
            return list;
        },
        (left, right) -> {
            left.addAll(right);
            return left;
        }
);
~~~

Mảnh mã trên dùng names là List<String> như mục 4. Khác với Collector.supplier(), overload reduce(identity, accumulator, combiner) nhận **một giá trị identity** để đưa vào các nhánh, không phải hàm tạo container mới. Với một identity mutable, các nhánh có thể cùng nhận tham chiếu đến object đó. Hãy dùng collect để thực hiện mutable reduction.

### 10.3. Cập nhật biến kết quả bên ngoài

~~~java
// PHẢN VÍ DỤ: cùng một List được sửa ngoài cơ chế collect.
List<String> shared = new ArrayList<>();
names.parallelStream().forEach(shared::add);
~~~

ArrayList không an toàn với cập nhật đồng thời. Giải pháp đúng với yêu cầu giữ các phần tử là names.parallelStream().collect(Collectors.toList()) hoặc names.parallelStream().toList() khi muốn List không thể sửa (Stream.toList có từ Java 16).

Lưu ý: đồng bộ hóa shared có thể xử lý một vấn đề cạnh tranh cụ thể, nhưng không tự thay thế việc thiết kế đúng hợp đồng supplier, accumulator, combiner và kết quả cần giữ thứ tự.

### 10.4. Combiner bỏ mất nhánh

~~~java
// SAI: các phần tử trong right bị loại.
(left, right) -> left
~~~

Với collector chỉ được thử bằng stream tuần tự, lỗi có thể chưa lộ. Test parallel và so sánh kết quả để phát hiện sai lệch.

### 10.5. Combiner trả object sai hoặc thay đổi sai thứ tự

Nếu collector lấy List từ ordered stream, một combiner ghép right vào trước left có thể đảo thứ tự các phân hoạch. Ngay cả khi đủ số lượng phần tử, kết quả vẫn sai nếu hợp đồng phải giữ encounter order. Nếu thứ tự không quan trọng, chỉ định UNORDERED khi collector thực sự thỏa tính chất đó.

### 10.6. Đánh dấu CONCURRENT chỉ vì container là ConcurrentHashMap

Sử dụng ConcurrentHashMap chưa đủ nếu value bên trong là một ArrayList được update không đồng bộ, hoặc có biến tổng global khác. Tất cả thao tác của accumulator trên **cùng A** phải an toàn nếu đồng thời; điều đó bao gồm các value, cấu trúc lồng nhau, tính đúng của combiner và cách snapshot kết quả.

### 10.7. Đánh dấu IDENTITY_FINISH khi cần biến đổi A thành R

Khi A là MutableTotals và R là Summary, finisher làm công việc thực sự. Gắn IDENTITY_FINISH là khai báo sai và có thể khiến kết quả bị cast sai kiểu hoặc bỏ qua logic hoàn tất.

### 10.8. Dựa vào số container, thread ID hoặc thứ tự log

In Thread.currentThread().getName() hoặc đếm supplier chỉ để **quan sát một lần chạy** có thể hữu ích cho thử nghiệm, nhưng không phải bằng chứng quy định Java luôn tạo đúng một accumulator cho mỗi core/thread/partition. ForkJoinPool và thư viện Stream có thể chọn lịch thực thi khác với kích thước đầu vào, nguồn Stream, JDK hoặc môi trường.

### 10.9. Trạng thái không có identity hay combiner associative

Ví dụ tích lũy giá trị trung bình bằng “average hiện tại” rồi kết hợp hai average bằng phép chia đôi sẽ sai khi các phân hoạch không đều nhau. Hãy lưu count và sum, rồi tính average trong finisher. Với double, cần nhớ sai số floating point khi thay đổi cách nhóm; chọn chiến lược tính toán phù hợp khi yêu cầu độ chính xác cao.

## 11. Trường hợp nên sử dụng collector chuẩn

Custom collector giúp thể hiện cách triển khai nhưng không cần viết lại API chuẩn chỉ để gom vào List hoặc đếm phần tử. Một số lựa chọn:

| Nhu cầu | Giải pháp phù hợp |
|---|---|
| Thu thập phần tử vào List theo encounter order | Collectors.toList(), hoặc Stream.toList() nếu muốn List không sửa được |
| Tạo List mutable cụ thể | Collectors.toCollection(ArrayList::new) |
| Đếm phần tử | Collectors.counting() |
| Cộng trường số nguyên | Collectors.summingInt/summingLong hoặc primitive Stream.sum() |
| Nhóm theo khóa | Collectors.groupingBy(classifier, downstream) |
| Nhóm song song, không cần encounter order | Cân nhắc groupingByConcurrent nếu phù hợp |
| Tạo kết quả thống kê tùy biến với A khác R | Collector.of(supplier, accumulator, combiner, finisher) |
| Thu thập bằng container concurrent có quy tắc riêng | Collector có CONCURRENT chỉ khi chứng minh được mọi cập nhật A an toàn |

**Tối ưu hóa:** parallelStream không luôn nhanh hơn stream. Việc tạo nhiều container và chạy combiner cũng có chi phí; concurrent collector có thể giảm chi phí ghép trong một số workload nhưng tăng tranh chấp khi các phần tử cập nhật cùng key. Đo bằng dữ liệu thực sau khi bảo đảm đúng nghiệp vụ.

## 12. Cách kiểm tra custom Collector có đúng không

### Kiểm tra chức năng

1. Input rỗng: supplier tạo được trạng thái trung hòa, finisher trả kết quả hợp lý.
2. Input một phần tử: accumulator tạo đúng kết quả.
3. Input nhiều phần tử: phép ghép container đúng đủ số lượng và giá trị.
4. Input với phân hoạch không đều: count, tổng, giá trị trung bình và thứ tự (nếu có) đúng.
5. So sánh sequential và parallel trên tập dữ liệu cố định: kết quả tương đương theo hợp đồng collector.
6. Với collector không UNORDERED, bảo đảm encounter order đúng từ nguồn có thứ tự.
7. Với collector CONCURRENT, kiểm tra kết quả dưới tải đồng thời và cấu trúc bên trong thật sự thread-safe, thay vì chỉ nhìn kiểu Map ngoài.
8. Test các giới hạn số học (overflow, floating point) và đầu vào null nếu miền dữ liệu có thể chứa chúng.

### Kiểm tra hợp đồng

- Supplier **mỗi lần gọi** có tạo một object trung gian mới độc lập không?
- Accumulator chỉ ghi vào A được truyền vào, không sửa nguồn/biến dùng chung chứ?
- Combiner vừa giữ đủ dữ liệu vừa kết hợp đúng thứ tự khi cần?
- Kết quả khi combiner ghép với container rỗng có tương đương trạng thái ban đầu?
- Phép ghép có associative về kết quả quan sát được không?
- Finisher có được phép chuyển A sang R, và characteristics đã phản ánh đúng điều đó chưa?
- Có đang đánh dấu CONCURRENT mà accumulator chưa an toàn trên cùng A không?

**Lưu ý giới hạn test:** thấy kết quả đúng trong vài lượt chạy parallel không chứng minh tuyệt đối không có race condition. Khi collector có dữ liệu dùng chung hoặc concurrent, phải lập luận về quyền truy cập, dùng primitive đồng bộ hóa/collection phù hợp và có kiểm thử đủ sức phát hiện lỗi dưới tải.

## 13. Câu hỏi tự kiểm tra

**Câu 1.** Tại sao ArrayList::new có thể được dùng trong Collector.of cho parallelStream dù ArrayList không thread-safe?

*Gợi ý trả lời:* Vì collector không CONCURRENT, framework cô lập các container trung gian trong giai đoạn tích lũy và dùng combiner để ghép. Mỗi lần supplier được gọi tạo một ArrayList mới.

**Câu 2.** Supplier trong parallelStream được bảo đảm gọi đúng bằng số thread hay số CPU core không?

*Gợi ý trả lời:* Không. Số container và phân hoạch là chi tiết thực thi; điều cần giữ là hợp đồng cô lập/ghép kết quả.

**Câu 3.** Vì sao () -> sharedList là supplier sai cho collector thông thường?

*Gợi ý trả lời:* Mọi lần gọi trả về cùng object, làm các nhánh chia sẻ mutable state và có thể khiến combiner tự ghép cùng object hoặc nhiều thread sửa chung List.

**Câu 4.** Khác biệt giữa combiner của Stream.collect(supplier, accumulator, combiner) và Collector.of(supplier, accumulator, combiner)?

*Gợi ý trả lời:* Với Stream.collect overload ba tham số, combiner là BiConsumer<R,R> và không trả kết quả. Với Collector.of, combiner là BinaryOperator<A> và phải trả container sau khi ghép.

**Câu 5.** Khi nào có thể gọi accumulator đồng thời trên cùng container?

*Gợi ý trả lời:* Khi collector thật sự hỗ trợ CONCURRENT và quá trình thu thập đáp ứng điều kiện về thứ tự; accumulator và toàn bộ trạng thái A phải an toàn khi nhiều thread cùng cập nhật.

**Câu 6.** Nếu finisher biến MutableTotals thành record Summary, có được khai báo IDENTITY_FINISH không?

*Gợi ý trả lời:* Không. Hai kiểu khác nhau và finisher cần chạy để chuyển đổi kết quả.

**Câu 7.** Combiner trả left mà không nhập right có thể được phát hiện ngay với stream tuần tự không?

*Gợi ý trả lời:* Không chắc; stream tuần tự có thể không gọi combiner. Cần kiểm tra hợp đồng và thử các trường hợp song song/phân hoạch.

## 14. Ghi nhớ khi thiết kế custom Collector

“Accumulator riêng cho mỗi phân hoạch” là cách hình dung về **kết quả trung gian tách biệt của non-concurrent collector**: supplier tạo trạng thái mới, accumulator cập nhật đúng trạng thái đó, combiner hợp nhất các trạng thái, và finisher tạo kết quả cuối. Cách hiểu này đủ để viết Collector.of an toàn với container mutable không thread-safe trong Stream song song.

Điều cần tránh là biến cách hình dung thành giả định về số thread, lịch thực thi hoặc số container chính xác. Nếu collector khai báo CONCURRENT và đủ điều kiện thực hiện concurrent reduction, nhiều lời gọi accumulator **có thể chủ động dùng chung một container**. Khi đó thiết kế phải bảo đảm an toàn đồng thời ngay từ bên trong container.

## Tài liệu tham khảo Java API hiện hành

- Oracle Java SE 25 — Collector: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Collector.html
- Oracle Java SE 25 — Collector.Characteristics: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Collector.Characteristics.html
- Oracle Java SE 25 — Stream.collect: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Stream.html
- Oracle Java SE 25 — Package java.util.stream, Mutable reduction và Concurrency: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/package-summary.html
- Oracle Java SE 25 — Collectors: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Collectors.html
