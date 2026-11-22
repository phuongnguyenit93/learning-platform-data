# So sánh kết quả Stream tuần tự và song song khi hợp đồng cho phép (Java 17)

## 1. Câu hỏi kiểm thử: khi nào kết quả phải giống nhau?

Java Stream cho phép chạy một pipeline ở chế độ tuần tự (*sequential*) hoặc song song (*parallel*):

~~~java
List<Integer> source = List.of(9, 2, 7, 4, 6, 1, 8, 3, 5, 10);

List<Integer> sequential = source.stream()
        .filter(n -> n % 2 == 0)
        .map(n -> n * n)
        .sorted()
        .toList();

List<Integer> parallel = source.parallelStream()
        .filter(n -> n % 2 == 0)
        .map(n -> n * n)
        .sorted()
        .toList();
~~~

Đây là **đoạn minh họa trong một phương thức**, cần `import java.util.List;`. Hai biến trả về cùng danh sách:

~~~text
[4, 16, 36, 64, 100]
~~~

Phép lọc chọn số chẵn, `map` bình phương, `sorted` sắp theo thứ tự tự nhiên, rồi `toList()` đưa các phần tử thành danh sách. Với những callback thuần và dữ liệu ổn định như ví dụ, kết quả logic không phụ thuộc cách chia phần tử cho các worker trong Stream song song.

Nhưng **không phải mọi biểu thức trông tương tự đều được phép so sánh bằng `equals`**. Các thao tác như `findAny()`, `forEach()`, pipeline đã gọi `unordered()` hoặc phép toán số thực có thể có hợp đồng khác. Đôi khi cách kiểm thử đúng là **cùng tập phần tử**, **cùng tổng theo ý nghĩa số học**, **phần tử trả về thuộc tập hợp lệ**, hoặc **một bất biến nghiệp vụ** — chứ không phải hai object phải có cùng thứ tự in ra.

**Mục tiêu:** học cách xác định *điều mà API thực sự cam kết* trước khi so sánh kết quả tuần tự và song song, xây dựng bộ kiểm thử Java 17 có thể chạy và biết những khác biệt **được phép** với những khác biệt là **lỗi**.

## 2. Những điều bất biến và những điều không bất biến

Hai chế độ đều dùng cùng các interface và các phép xử lý Stream; điểm khác là cách framework có thể chia, xử lý, phối hợp và kết hợp các phần dữ liệu.

### 2.1. Những kết quả thường phải bằng nhau

Nếu nguồn không bị sửa, callback stateless/non-interfering, các phép toán đáp ứng hợp đồng reduction và kết quả có điều kiện thứ tự rõ ràng, ta có thể so sánh:

- **Danh sách cuối có encounter order xác định:** các thao tác giữ thứ tự như `filter`/`map` và terminal `toList()` giữ các phần tử theo encounter order; `sorted()` tạo thứ tự theo Comparator.
- **Tổng nguyên với phép gộp hợp lệ:** `mapToLong(...).sum()` trên dữ liệu nguyên phù hợp có cùng kết quả ở hai chế độ; phải chú ý overflow nếu domain yêu cầu số học chính xác.
- **Reduction với identity và phép kết hợp associative:** kết quả gộp đúng theo hợp đồng, không chứa side effect tùy tiện.
- **`findFirst()` trên ordered Stream:** phần tử đầu theo encounter order phải phù hợp ở hai chế độ, kể cả nếu thời điểm thực thi callback không giống nhau.
- **Map tổng hợp theo nhóm:** các tổng/đếm đúng khóa có thể được so sánh bằng `Map.equals()`, miễn phép gộp và classifier phù hợp.
- **Set kết quả:** nếu chỉ quan trọng tập giá trị, `Set.equals()` so sánh thành viên và không phụ thuộc thứ tự iteration.

### 2.2. Những thứ không nhất thiết giống nhau

- **Thread ID, lịch chạy, thứ tự log của callback:** Stream song song không buộc callback được gọi theo thứ tự thời gian giống bản tuần tự.
- **`findAny()`:** có thể trả bất kỳ phần tử nào hợp lệ; không yêu cầu trả phần tử đầu.
- **`forEach()` trên parallel stream:** action không bắt buộc chạy theo encounter order.
- **Một pipeline unordered có `limit(n)`:** có thể chọn n phần tử khác nhau giữa các lần chạy; phải kiểm tra tính hợp lệ theo hợp đồng.
- **Kiểu Map cụ thể/iteration order của collector mặc định:** một Map có dữ liệu đúng không bắt buộc được in với thứ tự khóa như Map khác.
- **Thứ tự phép tính dấu phẩy động:** cộng số thực không kết hợp hoàn toàn trong số học máy; kết quả có thể khác các chữ số cuối khi cách nhóm thay đổi.
- **Side effects trong callback:** không lấy số lần tăng biến ngoài hoặc thứ tự in ra làm phép kiểm thử tương đương của pipeline.

### 2.3. Bảng nhanh chọn phép so sánh

| Kết quả cần kiểm thử | Cách so sánh nên dùng | Điều kiện quan trọng |
| --- | --- | --- |
| `List<T>` có thứ tự và giá trị rõ | `List.equals()` | Cùng encounter order/sort, hàm thuần, phần tử equals phù hợp |
| `long`/`int` tổng chính xác | `==` | Phép cộng hợp lệ, phạm vi overflow được xét |
| `Map<K,V>` thống kê | `Map.equals()` | Không so sánh riêng `toString()` hoặc iteration order khi API không hứa |
| `Set<T>` | `Set.equals()` | So sánh thành viên, không thứ tự |
| `Optional<T> findFirst()` | `Optional.equals()` | Ordered Stream và pipeline tương đương |
| `Optional<T> findAny()` | Kiểm tra `present`, phần tử hợp lệ | Không bắt buộc bằng kết quả tuần tự |
| `double` trung bình/tổng | Sai số/độ chính xác theo domain | NaN, ±∞, signed zero cần chính sách riêng |
| Phép ghép không associative | Không giả định tương đương | Phải sửa phép giảm, không sửa test cho qua |
| Kết quả của `forEach()` song song | Kiểm tra tập kết quả bằng cấu trúc an toàn nếu phù hợp | Không kiểm tra thứ tự callback |
| Dòng log, thread name, số lượt `peek` | Không dùng làm điều kiện tương đương nghiệp vụ | Side effects không phải đầu ra được bảo đảm |

## 3. Bước 1: cố định dữ liệu và định nghĩa hợp đồng

Một test chỉ có ý nghĩa nếu cả hai pipeline xử lý cùng **dữ liệu logic**. Ưu tiên `List.of(...)` hoặc snapshot bất biến cho bài kiểm thử để không có writer khác sửa nguồn trong lúc đang kiểm tra.

~~~java
List<Integer> inputs = List.of(9, 2, 7, 4, 6, 1, 8, 3, 5, 10);
~~~

Với List, encounter order là thứ tự theo vị trí phần tử. Với `HashSet`, ngược lại, không được giả định thứ tự tương ứng thứ tự chèn hoặc tăng dần giá trị.

Trước khi chọn assertion, viết rõ:

1. **Nguồn có encounter order không?**
2. **Các thao tác có làm mất thứ tự không?** Ví dụ `unordered()`.
3. **Mỗi hàm có stateless và non-interfering không?**
4. **Phép tổng hợp có associative và identity trung tính không?**
5. **Điều nghiệp vụ cần là thứ tự, giá trị tổng, tập thành viên hay chỉ cần một phần tử thỏa?**
6. **Có float/double, overflow, exception hoặc side effect không?**

Không kiểm thử bằng cách gọi tuần tự trên một nguồn rồi **đồng thời sửa chính nguồn đó** trước khi chạy song song. Khi đầu vào đã khác, kết quả khác không nói lên đúng/sai của chế độ Stream.

### 3.1. So sánh đúng phương pháp, không chỉ đúng dữ liệu ví dụ

Một test có thể tình cờ đi qua vì bộ dữ liệu quá đơn giản. Ví dụ mọi số đều dương khiến `findAny()` và `findFirst()` cùng trả một kết quả trong một số lần chạy, nhưng điều đó **không biến hợp đồng findAny thành findFirst**.

Hãy đưa dữ liệu có:
- Phần tử không phù hợp ở đầu và phần tử phù hợp ở sau.
- Nhiều nhóm/khóa để nhận ra lỗi nhóm.
- Giá trị trùng để kiểm tra `distinct`.
- Nguồn rỗng và nguồn một phần tử.
- Giá trị biên cho phép cộng hoặc Comparator.
- Nhiều phần tử đủ lớn để có khả năng phân chia khi thử song song, nhưng không đòi một số thread cố định.

## 4. So sánh danh sách khi encounter order được bảo đảm

### 4.1. List có thứ tự + filter/map/sorted/toList

~~~java
List<Integer> expected = inputs.stream()
        .filter(n -> n % 2 == 0)
        .map(n -> n * n)
        .sorted()
        .toList();

List<Integer> actual = inputs.parallelStream()
        .filter(n -> n % 2 == 0)
        .map(n -> n * n)
        .sorted()
        .toList();

if (!expected.equals(actual)) {
    throw new AssertionError("Mismatched ordered results");
}
~~~

Đoạn minh họa bên trong một phương thức với `inputs` đã khai báo. Với dữ liệu ở phần 3, hai danh sách đều là `[4,16,36,64,100]`.

Ở đây `sorted()` đảm bảo thứ tự giá trị trong kết quả và `toList()` trả phần tử theo encounter order của Stream. Sự khác nhau của lịch chạy callback không được phép làm sai thứ tự logic cuối cùng.

### 4.2. Không nhất thiết phải sorted

Nếu nguồn đã có encounter order và mọi thao tác đều giữ order:

~~~java
List<Integer> seq = inputs.stream()
        .filter(n -> n > 3).toList();

List<Integer> par = inputs.parallelStream()
        .filter(n -> n > 3).toList();
~~~

Hai danh sách phải có cùng phần tử theo encounter order của nguồn. Việc bỏ `sorted()` trong trường hợp này không làm mất encounter order của List.

Tuy nhiên nếu nguồn là một unordered Set hoặc pipeline gọi `unordered()`, không được áp đặt một danh sách theo thứ tự cố định mà API không hứa.

### 4.3. Sorted có phần tử cùng khóa

Nếu `sorted(comparator)` dùng Comparator coi hai phần tử khác nhau là bằng nhau, hãy xét:
- Với **ordered Stream**, thao tác `sorted` có đặc tính ổn định (*stable*) theo hợp đồng.
- Với **unordered Stream**, không có bảo đảm stability tương tự.
- Nếu thứ tự các giá trị cùng khóa là một phần nghiệp vụ, thêm **tie-breaker tường minh** vào comparator thay vì dựa vào timing.

Ví dụ so sánh đơn hàng theo tổng tiền rồi ID:

~~~java
// Ví dụ thiết kế khi Order có amount() và id():
// Comparator<Order> order = Comparator
//         .comparingLong(Order::amount)
//         .thenComparing(Order::id);
~~~

Đoạn comment chỉ là minh họa với kiểu `Order` chưa định nghĩa ở phần này. Quy tắc là nếu Comparator biểu diễn một thứ tự xác định đầy đủ, test có thể so sánh chính xác danh sách sau `sorted(order)`.

### 4.4. limit/skip trên ordered pipeline

Với List có encounter order, `limit(k)` yêu cầu lấy tối đa k phần tử đầu tại thời điểm áp dụng và `skip(n)` bỏ n phần tử đầu. Do đó, khi callback và nguồn hợp lệ, hai pipeline tương đương vẫn phải chọn cùng phần tử logic dù bản parallel có thể phối hợp chậm hơn.

~~~java
List<Integer> a = inputs.stream()
        .filter(n -> n % 2 == 0)
        .skip(1).limit(2).toList();

List<Integer> b = inputs.parallelStream()
        .filter(n -> n % 2 == 0)
        .skip(1).limit(2).toList();
// Cả hai [4, 6].
~~~

**Đừng tự chuyển** `filter(...).limit(k)` thành `limit(k).filter(...)` rồi so sánh, vì đó là hai thuật toán chọn dữ liệu **khác ngữ nghĩa** trước cả khi xét chuyện song song.

## 5. Tổng, reduce và yêu cầu associative

### 5.1. Cộng số nguyên bằng sum()

~~~java
long sequentialSum = inputs.stream()
        .mapToLong(Integer::longValue)
        .sum();

long parallelSum = inputs.parallelStream()
        .mapToLong(Integer::longValue)
        .sum();
~~~

Với dữ liệu ở phần 3, cả hai tổng đều là 55. Phép cộng số nguyên long có phần tử trung tính 0, và thứ tự nhóm không thay đổi kết quả theo quy tắc số học kiểu long của Java.

Dẫu vậy, **overflow** có thể làm giá trị long khác tổng toán học vô hạn. Nếu doanh thu phải tuyệt đối không tràn, chọn kiểu số/phép kiểm tra hợp lệ (ví dụ BigInteger hoặc chính sách phát hiện overflow). Test bằng `==` có thể chứng minh hai pipeline đồng ý với nhau, **không tự chứng minh tổng đã đúng domain**.

### 5.2. reduce với identity và accumulator hợp lệ

~~~java
int total = inputs.parallelStream()
        .reduce(0, Integer::sum);
// 55
~~~

Để phép giảm song song đúng, accumulator cần **associative**, identity phải trung tính, behavioral parameters cần stateless/non-interfering. Ví dụ tổng với `Integer::sum` và identity 0 thỏa điều kiện liên quan.

Một phép `reduce` đúng ở chế độ tuần tự **không phải** bằng chứng nó đúng khi chia nhóm. Hãy kiểm tra phép toán:

~~~text
(a op b) op c == a op (b op c)
~~~

và identity:

~~~text
op(e, x) == x
op(x, e) == x
~~~

Với overload ba đối số, còn phải kiểm tra combiner tương thích với accumulator:

~~~text
combiner(u, accumulator(identity, t))
    == accumulator(u, t)
~~~

**Đừng dùng** một combiner chỉ giữ giá trị bên trái để “cho chạy”, vì trên parallel Stream kết quả của các phân đoạn khác có thể bị mất.

### 5.3. Phản ví dụ: phép trừ

~~~java
// Phản ví dụ: có thể biên dịch nhưng không đáp ứng hợp đồng reduce.
// int result = inputs.parallelStream()
//         .reduce(0, (a, b) -> a - b);
~~~

Tính không kết hợp có thể thấy trực tiếp:

~~~text
(10 - 3) - 2 = 5
10 - (3 - 2) = 9
~~~

Vì hai cách nhóm cho kết quả khác, **không nên kỳ vọng** reduce dạng này cho cùng kết quả giữa chế độ tuần tự và song song. Nếu test có lúc “bằng nhau”, đó chỉ có thể là trùng hợp của dữ liệu hoặc cách chia việc. Cần **sửa thiết kế phép toán**, không phải bỏ assertion để qua test.

### 5.4. Dấu phẩy động: so sánh với chính sách sai số

Với `float`/`double`, phép cộng dấu phẩy động không hoàn toàn associative do làm tròn. JDK có thể dùng những chiến lược tổng khác nhau và phép cộng nhóm có thể tạo sai khác nhỏ.

~~~java
double a = seqValues.stream().mapToDouble(Double::doubleValue).sum();
double b = seqValues.parallelStream().mapToDouble(Double::doubleValue).sum();
~~~

Đoạn này giả định `seqValues` là `List<Double>` hợp lệ; cần import `java.util.List`. Không khẳng định mọi lần chạy `a != b`, và cũng không hứa mọi lần `a == b`.

Một tiêu chí kiểm tra sai số cho **dữ liệu hữu hạn** có thể là:

~~~java
double tolerance = 1e-9;
boolean close = Math.abs(a - b)
        <= tolerance * Math.max(1.0, Math.max(Math.abs(a), Math.abs(b)));
~~~

Đây là ví dụ chính sách *absolute + relative tolerance* đơn giản, **không phải ngưỡng đúng cho mọi domain**. Với NaN, vô cực, underflow, signed zero hoặc bài toán đòi exact decimal, cần xử lý riêng.

Trong tính toán tiền tệ thường cân nhắc kiểu số đại diện chính xác theo đơn vị nhỏ nhất (long với giới hạn phù hợp) hoặc `BigDecimal` có quy tắc scale/rounding rõ. Không thay một ràng buộc chính xác bằng epsilon tùy ý.

## 6. So sánh nhóm và các collector

Hai pipeline có thể dùng cùng collector hợp lệ để tạo Map thống kê. Đừng so chuỗi `Map.toString()` nếu loại Map không cam kết thứ tự khóa.

~~~java
Map<String, Integer> a = sales.stream()
        .collect(Collectors.groupingBy(
                Sale::category,
                TreeMap::new,
                Collectors.summingInt(Sale::amount)));

Map<String, Integer> b = sales.parallelStream()
        .collect(Collectors.groupingBy(
                Sale::category,
                TreeMap::new,
                Collectors.summingInt(Sale::amount)));

if (!a.equals(b)) {
    throw new AssertionError("Group totals mismatch");
}
~~~

Đoạn minh họa này cần `java.util.Map`, `java.util.TreeMap`, `java.util.stream.Collectors`, và một kiểu `Sale` có method `category()`, `amount()`.

`Map.equals()` kiểm tra tập mapping khóa → giá trị. Với `TreeMap`, thứ tự duyệt khóa cũng được xác định theo natural order/comparator. Nếu không cần thứ tự báo cáo, vẫn có thể dùng collector mặc định rồi so `Map.equals()` mà không tự khẳng định loại Map.

### 6.1. Collector phải đáp ứng hợp đồng

Chỉ so hai kết quả có ý nghĩa khi collector kết hợp kết quả hợp lệ:
- Downstream và combiner phải bảo toàn thống kê.
- Nếu dùng custom Collector, supplier cần cấp container đúng, accumulator và combiner không vi phạm contract.
- Với grouping hoặc toMap có duplicate key, merge function phải thích hợp.
- Không tự sửa Map mutable dùng chung bên ngoài từ `parallelStream().forEach(...)`.

Một `Collectors.groupingBy(...)` thông thường có thể được Stream framework sử dụng trên parallel stream qua cơ chế kết hợp kết quả từng phần; điều đó **không cho phép** callback của bạn tự sửa một HashMap/ArrayList chia sẻ không đồng bộ.

### 6.2. Thứ tự khóa và thứ tự phần tử trong nhóm là hai câu hỏi

`LinkedHashMap` có insertion-order trong điều kiện thích hợp; `TreeMap` sắp theo khóa. Nhưng nếu giá trị nhóm là `List<T>`, thứ tự **trong danh sách nhóm** còn phụ thuộc encounter order và downstream.

Với `Collectors.toSet()`, **thứ tự duyệt Set không được đảm bảo**, nên nên so thành viên thay vì trình tự. Với `groupingByConcurrent(...)`, collector có đặc tính concurrent/unordered: tránh dùng lịch chạy thread như quy tắc thứ tự báo cáo.

Nếu muốn trình bày nhóm theo tổng tiền giảm dần, `TreeMap` theo khóa không tự làm điều đó; cần sort các entry theo value với tie-breaker riêng. Test phải phản ánh đúng trục thứ tự mà nghiệp vụ yêu cầu.

## 7. Kiểm tra Set: bằng nhau về thành viên, không phải iteration order

~~~java
Set<Integer> sequentialSet = inputs.stream()
        .filter(n -> n % 2 == 0)
        .collect(Collectors.toSet());

Set<Integer> parallelSet = inputs.parallelStream()
        .filter(n -> n % 2 == 0)
        .collect(Collectors.toSet());

boolean sameMembers = sequentialSet.equals(parallelSet);
~~~

Đây là đoạn minh họa với `inputs` kiểu List; cần import `java.util.Set` và `Collectors`.

`Collectors.toSet()` là collector không bảo đảm loại Set cụ thể hoặc iteration order. Vì vậy, assert `Set.equals()` là phù hợp nếu nghiệp vụ chỉ quan tâm thành viên, còn assert `Set.toString()` bằng nhau có thể không phù hợp.

Nếu muốn **stdout ổn định** khi giải thích test, biến Set thành danh sách đã sắp:

~~~java
List<Integer> sorted = sequentialSet.stream().sorted().toList();
// [2, 4, 6, 8, 10]
~~~

Phép sắp xếp này dùng cho **trình bày và kiểm chứng**, không có nghĩa collector toSet vốn bảo đảm thứ tự.

### 7.1. So multiset khi số lần xuất hiện cũng quan trọng

Set **loại trùng**, vì thế so Set có thể bỏ sót lỗi nếu dữ liệu kỳ vọng chứa nhiều bản ghi cùng giá trị.

Ví dụ nguồn `[1,1,2]` và nguồn `[1,2,2]` cho cùng Set `{1,2}`, nhưng khác **số lần xuất hiện**. Khi nghiệp vụ yêu cầu bảo toàn số lượng từng giá trị, hãy:
- So danh sách sau khi sắp nếu mọi phần tử so sánh được.
- Hoặc dùng `groupingBy(identity(), counting())` để so Map giá trị → số lần xuất hiện.
- Hoặc so một cấu trúc multiset do ứng dụng định nghĩa.

**Chọn assertion dựa trên ngữ nghĩa dữ liệu**, không chỉ dựa vào API mà bạn đang dùng.

## 8. findFirst và findAny: hai hợp đồng khác nhau

### 8.1. findFirst trên List có encounter order

~~~java
int sequentialFirst = inputs.stream()
        .filter(n -> n % 2 == 0)
        .findFirst().orElseThrow();

int parallelFirst = inputs.parallelStream()
        .filter(n -> n % 2 == 0)
        .findFirst().orElseThrow();
~~~

Với nguồn ở phần 3, cả hai phải trả `2`. Đó là số chẵn **đầu tiên theo encounter order**, không nhất thiết là số chẵn nhỏ nhất về giá trị. `findFirst()` có thể tốn công giữ thứ tự khi chạy parallel.

Với nguồn rỗng hoặc không có phần tử phù hợp, `findFirst()` trả `Optional.empty()` và mã dùng `orElseThrow()` sẽ ném exception. Một test tổng quát nên so hai Optional thay vì buộc mọi nguồn đều không rỗng.

### 8.2. findAny không hứa cùng phần tử

~~~java
int any = inputs.parallelStream()
        .filter(n -> n % 2 == 0)
        .findAny().orElseThrow();

boolean valid = inputs.contains(any) && any % 2 == 0;
~~~

Đúng là `any` phải thuộc các phần tử chẵn phù hợp của nguồn trong ví dụ, nhưng **không** đòi nó bằng 2 hoặc bằng `findAny()` của một lần chạy khác.

Cũng không được viết test ngược “hai kết quả phải khác nhau” vì `findAny()` **được phép trùng**. Một test đúng khi nguồn có phần tử hợp lệ:
- Kiểm tra Optional có giá trị.
- Kiểm tra giá trị thuộc miền đầu vào sau lọc.
- Kiểm tra tính chất nghiệp vụ.
- Không kiểm tra chính xác phần tử nào được chọn, trừ khi pipeline có một phần tử hợp lệ duy nhất.

Khi nguồn không có phần tử khớp, verify `Optional.empty()`. Với nguồn cho phép null và API Stream không chấp nhận null làm giá trị tìm thấy trong nhiều tình huống, phải tránh đưa giá trị null vào phép `findAny`/`findFirst` một cách không kiểm soát.

## 9. forEach() và forEachOrdered(): kiểm tra hành động có thứ tự

`forEach()` trong parallel stream **không bảo đảm thứ tự action**. Ví dụ:

~~~java
// Không dự đoán thứ tự dòng được in:
// inputs.parallelStream().forEach(System.out::println);
~~~

Một lần chạy có thể in số theo thứ tự khác lần chạy sau, và điều đó không tự chứng minh pipeline sai.

Nếu **yêu cầu thực thi action theo encounter order**, có `forEachOrdered()`:

~~~java
StringJoiner output = new StringJoiner(",");
inputs.parallelStream()
        .forEachOrdered(n -> output.add(Integer.toString(n)));
~~~

Đây là đoạn minh họa với List ordered; cần import `java.util.StringJoiner`. Tài liệu Stream bảo đảm action của `forEachOrdered` theo encounter order và **happens-before** giữa action phần tử trước và sau theo thứ tự này. Vì vậy cách tạo chuỗi trong chương trình Java 17 ở phần 11 có thể so với bản tuần tự trong phạm vi action tuần tự theo hợp đồng đó.

**Cảnh báo:** `forEachOrdered()` không có nghĩa mỗi callback map/filter trước nó đều chạy trên cùng thread hoặc theo thứ tự thời gian nguồn. Và việc ghi database theo thứ tự action không tự tạo transaction; khi exception xảy ra, Stream không rollback những hành động đã thực hiện.

### 9.1. Tránh shared mutable state

Sai:

~~~java
// KHÔNG AN TOÀN với parallel forEach:
// List<Integer> output = new ArrayList<>();
// inputs.parallelStream().forEach(output::add);
~~~

Nhiều thread có thể cùng sửa ArrayList không thread-safe. Nếu cần kết quả dạng List, dùng `map(...).toList()` hoặc Collector thích hợp. Nếu bắt buộc có action bên ngoài, thiết kế thread-safety và chính sách lỗi riêng, không dùng một test kết quả bằng nhau để “chứng minh” side effects an toàn.

## 10. Những trường hợp khác biệt được phép

### 10.1. unordered() + limit(n)

Với pipeline unordered:

~~~java
List<Integer> anyThree = inputs.parallelStream()
        .unordered()
        .filter(n -> n % 2 == 0)
        .limit(3)
        .toList();
~~~

Vì thứ tự gặp đã bị bỏ ràng buộc, không hứa `anyThree` là ba số chẵn **đầu tiên** theo List nguồn. Nó phải có tối đa 3 phần tử phù hợp, nhưng tập phần tử được chọn có thể khác theo điều kiện thực thi.

Test đúng có thể kiểm tra:
- `size() <= 3`.
- Mỗi phần tử là số chẵn có mặt trong nguồn.
- Khi nguồn có ít nhất ba kết quả phù hợp và pipeline không có bước khác cắt bớt, kết quả có ba phần tử.
- Không áp đặt chính xác danh sách `[2,4,6]`.

Nếu nghiệp vụ bắt buộc lấy **ba số chẵn đầu tiên theo nguồn**, **không thêm `unordered()`** chỉ để mong pipeline nhanh hơn.

### 10.2. Map không có thứ tự cố định

`Map.equals()` có thể bằng nhau mặc dù `entrySet()` được duyệt theo thứ tự khác. Nếu API nhận dữ liệu theo thứ tự nhóm tăng dần, chọn `TreeMap` hoặc biểu diễn thành danh sách entry đã sắp; đừng suy ra thứ tự từ `HashMap` hoặc `groupingBy` mặc định.

### 10.3. Double và trật tự cộng

Thứ tự gộp trong reduction có thể ảnh hưởng các bit cuối của số thực. Một sai khác trong ngưỡng chính sách số học có thể được phép; một sai khác rất lớn hoặc NaN ngoài mong đợi vẫn cần điều tra. Không che mọi lỗi dưới câu “parallel floating point có thể lệch”.

### 10.4. Logging, peek, map với side effect

Một số terminal operations có thể tối ưu bỏ callback trung gian. Ví dụ `count()` trên nguồn List có size biết trước có thể không gọi `map`/`peek` nếu các bước ấy không làm đổi cardinality.

Đừng thiết kế test như:

~~~java
// Không phải một test hợp đồng đúng:
// AtomicInteger calls = new AtomicInteger();
// long total = inputs.stream()
//       .peek(n -> calls.incrementAndGet())
//       .count();
// assert calls.get() == inputs.size();
~~~

Số lần `peek` không phải kết quả nghiệp vụ được `count` cam kết. Nếu cần thực hiện hành động bắt buộc cho từng phần tử, dùng một terminal action hoặc workflow riêng với xử lý lỗi và transaction thích hợp.

## 11. Chương trình Java 17 hoàn chỉnh: kiểm thử so sánh theo hợp đồng

Tạo file **SequentialParallelContractDemo.java**. Chương trình dùng assertion tự viết để chạy ngay bằng JDK 17, **không cần JUnit**. Nó cố ý in kết quả ổn định và không in giá trị ngẫu nhiên của `findAny()`; thay vào đó chỉ in rằng phần tử tìm được hợp lệ.

~~~java
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.StringJoiner;
import java.util.TreeMap;
import java.util.stream.Collectors;

public class SequentialParallelContractDemo {
    record Sale(String category, int amount) {}

    static void requireEqual(Object expected, Object actual, String caseName) {
        if (!Objects.equals(expected, actual)) {
            throw new AssertionError(caseName + ": expected=" + expected
                    + ", actual=" + actual);
        }
    }

    static List<Integer> evenSquares(List<Integer> input, boolean parallel) {
        var stream = parallel ? input.parallelStream() : input.stream();
        return stream.filter(n -> n % 2 == 0)
                .map(n -> n * n)
                .sorted()
                .toList();
    }

    static Map<String, Integer> totals(List<Sale> sales, boolean parallel) {
        var stream = parallel ? sales.parallelStream() : sales.stream();
        return stream.collect(Collectors.groupingBy(
                Sale::category,
                TreeMap::new,
                Collectors.summingInt(Sale::amount)));
    }

    static String orderedText(List<Integer> numbers, boolean parallel) {
        StringJoiner result = new StringJoiner(",");
        var stream = parallel ? numbers.parallelStream() : numbers.stream();
        stream.forEachOrdered(n -> result.add(Integer.toString(n)));
        return result.toString();
    }

    public static void main(String[] args) {
        List<Integer> numbers = List.of(9, 2, 7, 4, 6, 1, 8, 3, 5, 10);
        List<Integer> seq = evenSquares(numbers, false);
        List<Integer> par = evenSquares(numbers, true);
        requireEqual(seq, par, "ordered pipeline");
        System.out.println("ordered lists equal=" + seq.equals(par));
        System.out.println("even squares=" + par);

        long sequentialSum = numbers.stream().mapToLong(Integer::longValue).sum();
        long parallelSum = numbers.parallelStream().mapToLong(Integer::longValue).sum();
        requireEqual(sequentialSum, parallelSum, "exact long sum");
        System.out.println("long sums=" + sequentialSum + "/" + parallelSum);

        int firstSequential = numbers.stream()
                .filter(n -> n % 2 == 0).findFirst().orElseThrow();
        int firstParallel = numbers.parallelStream()
                .filter(n -> n % 2 == 0).findFirst().orElseThrow();
        requireEqual(firstSequential, firstParallel, "ordered findFirst");
        System.out.println("first even=" + firstParallel);

        List<Sale> sales = List.of(
                new Sale("Books", 10),
                new Sale("Games", 5),
                new Sale("Books", 20),
                new Sale("Food", 8));
        Map<String, Integer> seqGroups = totals(sales, false);
        Map<String, Integer> parGroups = totals(sales, true);
        requireEqual(seqGroups, parGroups, "group totals");
        System.out.println("groups equal=" + seqGroups.equals(parGroups));
        System.out.println("groups=" + parGroups);

        Set<Integer> seqSet = numbers.stream().filter(n -> n % 2 == 0)
                .collect(Collectors.toSet());
        Set<Integer> parSet = numbers.parallelStream().filter(n -> n % 2 == 0)
                .collect(Collectors.toSet());
        requireEqual(seqSet, parSet, "unordered set contents");
        System.out.println("sets equal=" + seqSet.equals(parSet));
        System.out.println("set sorted=" + seqSet.stream().sorted().toList());

        int anyEven = numbers.parallelStream()
                .filter(n -> n % 2 == 0).findAny().orElseThrow();
        if (!numbers.contains(anyEven) || anyEven % 2 != 0) {
            throw new AssertionError("findAny contract");
        }
        System.out.println("findAny valid=true");

        String orderedSequential = orderedText(numbers, false);
        String orderedParallel = orderedText(numbers, true);
        requireEqual(orderedSequential, orderedParallel, "forEachOrdered");
        System.out.println("forEachOrdered equal=" +
                orderedSequential.equals(orderedParallel));

        List<Integer> empty = List.of();
        requireEqual(empty.stream().toList(), empty.parallelStream().toList(),
                "empty input");
        requireEqual(0L, empty.parallelStream().mapToLong(Integer::longValue).sum(),
                "empty sum");
        System.out.println("empty tests=PASS");

        List<Integer> duplicates = List.of(2, 2, 1, 1, 3);
        requireEqual(duplicates.stream().distinct().sorted().toList(),
                duplicates.parallelStream().distinct().sorted().toList(),
                "distinct sorted");
        System.out.println("distinct sorted=" +
                duplicates.parallelStream().distinct().sorted().toList());

        System.out.println("all contract tests=PASS");
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 SequentialParallelContractDemo.java
java SequentialParallelContractDemo
~~~

**Stdout đã được biên dịch/chạy và xác minh trực tiếp:**

~~~text
ordered lists equal=true
even squares=[4, 16, 36, 64, 100]
long sums=55/55
first even=2
groups equal=true
groups={Books=30, Food=8, Games=5}
sets equal=true
set sorted=[2, 4, 6, 8, 10]
findAny valid=true
forEachOrdered equal=true
empty tests=PASS
distinct sorted=[1, 2, 3]
all contract tests=PASS
~~~

### 11.1. Phân tích từng assertion

1. **Ordered pipeline:** hai cách tạo Stream khác chế độ nhưng dùng cùng các phép thuần, lọc/bình phương/sắp xếp, nên danh sách bằng nhau; kết quả cụ thể là năm bình phương số chẵn.
2. **Long sum:** hai pipeline tính tổng các số 9+2+7+4+6+1+8+3+5+10 = 55. Không dùng thread ID làm phép kiểm tra.
3. **findFirst:** số chẵn đầu tiên theo List nguồn là 2; dù dùng parallel, kết quả phải tuân theo encounter order.
4. **Nhóm:** cùng kết quả mapping Books→30, Games→5, Food→8; `TreeMap` làm thứ tự khóa khi in báo cáo là Books, Food, Games.
5. **Set:** kiểm tra thành viên bằng `Set.equals()`; dòng `set sorted` chỉ phục vụ hiển thị ổn định.
6. **findAny:** giá trị trả về phải thuộc nguồn và là số chẵn; test cố ý không khẳng định “phải bằng 2” hoặc một số cố định khác.
7. **forEachOrdered:** trên nguồn List ordered, các action theo encounter order nên hai chuỗi kết quả so được bằng nhau.
8. **Nguồn rỗng:** hai danh sách rỗng như nhau; tổng long của nguồn rỗng là 0.
9. **Distinct:** dữ liệu chứa duplicate nhưng `distinct().sorted().toList()` tạo `[1,2,3]` ở cả hai chế độ.
10. **PASS cuối:** mọi assertion đã qua trong một lần chạy. Với dữ liệu và JVM khác, test vẫn phải dựa vào hợp đồng được giải thích, không dựa vào lịch chia thread cụ thể.

### 11.2. Vì sao không có một dòng in giá trị findAny?

Nếu in `anyEven`, output có thể thay đổi giữa các môi trường/chế độ. Muốn đưa một stdout **đúng và có thể đối chiếu** vào tài liệu, chương trình chỉ in kết quả của việc **kiểm tra điều kiện hợp lệ**. Đây là một kỹ thuật thiết kế test quan trọng: tránh ép một API không xác định thứ tự phải có output cố định chỉ để ví dụ dễ viết hơn.

### 11.3. Vì sao test không tự cấp phát ArrayList trong forEach song song?

Bởi cách làm ấy đưa ra một race condition không thuộc bài toán so sánh đúng hợp đồng. Kết quả thu thập bằng Stream collector hoặc `toList()` phù hợp hơn. `forEachOrdered` được dùng riêng để minh họa terminal action có thứ tự, không nhằm làm collector thay thế cho tất cả cấu trúc dữ liệu.

## 12. Mở rộng kiểm thử bằng JUnit 5

Nếu project đã cài **JUnit Jupiter 5**, có thể tổ chức các assertion gọn hơn. Phần này là **mã minh họa trong một lớp test có dependency JUnit 5**, không phải file chạy độc lập bằng `javac` không có thư viện.

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;
import java.util.List;

class StreamContractTest {
    @Test
    void orderedPipelineHasSameResult() {
        List<Integer> input = List.of(9, 2, 7, 4, 6);
        List<Integer> sequential = input.stream()
                .filter(n -> n % 2 == 0).sorted().toList();
        List<Integer> parallel = input.parallelStream()
                .filter(n -> n % 2 == 0).sorted().toList();

        assertEquals(sequential, parallel);
        assertEquals(List.of(2, 4, 6), parallel);
    }

    @Test
    void findAnyReturnsValidElement() {
        List<Integer> input = List.of(9, 2, 7, 4, 6);
        int result = input.parallelStream()
                .filter(n -> n % 2 == 0)
                .findAny().orElseThrow();
        assertTrue(input.contains(result));
        assertEquals(0, result % 2);
    }
}
~~~

**Điểm thiết kế:** test thứ nhất khẳng định một output cụ thể vì pipeline có thứ tự xác định; test thứ hai khẳng định **thuộc tính đúng** thay vì một giá trị không được API hứa.

Nếu không có dependency JUnit 5, dùng chương trình độc lập của phần 11 để kiểm thử core Java 17. Không đưa ví dụ JUnit vào một file `java` rồi kỳ vọng `javac --release 17` tự tìm thấy thư viện test.

### 12.1. Property-based testing

Với những pipeline cần đúng cho nhiều loại dữ liệu, có thể áp dụng kiểm thử theo thuộc tính:

~~~text
Với mọi danh sách số nguyên hữu hạn, không có side effect:
    sort(map(filter(input), f)) ở sequential
    bằng cùng pipeline ở parallel (theo equals),
    nếu f không gây overflow ngoài điều kiện đã định nghĩa
    và phép sort có comparator hợp lệ.
~~~

Dùng bộ sinh dữ liệu của công cụ property-based testing thích hợp để kiểm tra nhiều tổ hợp; luôn gồm các ca biên rỗng, trùng, giá trị cực trị và dữ liệu đặc biệt. Một property cần được phát biểu theo **hợp đồng được bảo đảm**; không viết property “findAny luôn bằng findFirst” rồi cho rằng lỗi test là lỗi của Java.

### 12.2. Repeated runs và điều chúng chứng minh

Chạy pipeline song song nhiều lần giúp tìm race condition hoặc lỗi stateful callback. Nhưng **một trăm lần test qua không chứng minh đã an toàn đa luồng**; lỗi có thể phụ thuộc lịch chạy khó tái hiện.

Nên bổ sung:
- Code review về stateless/non-interfering và nguồn mutable.
- Kiểm thử dữ liệu lớn với cardinality khác nhau.
- Kiểm thử custom Collector và phép giảm về associativity/combiner.
- Cơ chế kiểm thử concurrency chuyên dụng khi có trạng thái chia sẻ.
- Kiểm tra lỗi và retry ở ranh giới I/O thay vì coi Stream là transaction engine.

## 13. Benchmark khác với test đúng kết quả

Một pipeline parallel trả đúng kết quả **không đồng nghĩa nhanh hơn**. Chi phí phân chia nguồn, lập lịch, kết hợp kết quả, bộ nhớ và contention có thể vượt lợi ích nếu danh sách nhỏ hoặc callback rẻ.

Đừng đưa tốc độ vào một assertion kiểu “parallel phải nhanh hơn sequential” vì tốc độ bị ảnh hưởng bởi JVM warm-up, CPU, GC, OS scheduler và tải chạy nền.

Nếu thực sự cần đánh giá performance:
1. Hoàn tất bộ test đúng hợp đồng trước.
2. Dùng dữ liệu và khối lượng đại diện.
3. Chạy JMH hoặc phương pháp benchmark có warm-up, nhiều lần đo và loại bỏ dead-code elimination.
4. So throughput/latency, memory, GC và tác động lên các request khác.
5. Chọn parallel chỉ khi lợi ích ổn định và không làm xấu khả năng vận hành.

Đặc biệt với pipeline chỉ `count()` trên nguồn có kích thước biết trước, cả hai chế độ có thể tính kết quả mà không cần duyệt; việc bật parallel không tạo “năng lực tăng tốc” cho công việc không tồn tại.

## 14. Bảng lỗi phổ biến khi so sánh hai chế độ

| Lỗi kiểm thử | Vì sao không đúng | Cách sửa |
| --- | --- | --- |
| So `findAny()` với `findFirst()` bằng `equals` | findAny chọn bất kỳ phần tử hợp lệ | Kiểm tra membership/predicate |
| So `Set.toString()` hoặc iteration order | Set collector không hứa thứ tự | So `Set.equals()` hoặc sort để hiển thị |
| So `HashMap.toString()` theo thứ tự khóa | HashMap không hứa order | So Map.equals hoặc dùng TreeMap |
| Dùng `reduce(0, (a,b)->a-b)` trên parallel | Phép trừ không associative | Đổi phép toán/thiết kế |
| Đặt `ArrayList.add` vào parallel forEach | Race/mất phần tử, không có thread safety | Dùng toList/collect hoặc đồng bộ thích hợp |
| Dùng `peek` để đếm callback | JDK có thể tối ưu bỏ callback | Kiểm tra giá trị terminal |
| So `double` bằng `==` cho mọi dữ liệu | Sai số và đổi cách nhóm | Chọn tolerance/kiểu số đúng domain |
| Cho rằng List có cùng phần tử là đủ dù thứ tự nghiệp vụ quan trọng | List.equals còn xét vị trí | Chọn assertion đúng thứ tự |
| Cho rằng Set.equals đủ khi duplicate quan trọng | Set bỏ số lần xuất hiện | So multiset/counts |
| Thêm `unordered()` rồi vẫn đòi phần tử đầu của List | Đã bỏ contract order | Không unordered nếu cần phần tử đầu |
| Chỉ test nguồn không rỗng | Bỏ sót Optional.empty và identity | Thêm nguồn rỗng |
| Chỉ chạy một lần rồi kết luận không race | Lỗi concurrency có thể hiếm | Review hợp đồng và test nhiều dữ liệu/lịch chạy |
| Dùng List bị sửa đồng thời trong test | Hai pipeline không xử lý cùng snapshot | Cố định/snapshot nguồn |
| So output đúng nhưng quên overflow | Hai tổng cùng sai nghiệp vụ | Kiểm tra miền số và policy |
| Coi kết quả đúng là hiệu năng tốt | Correctness và performance là hai mục tiêu | Benchmark riêng bằng công cụ phù hợp |

## 15. Checklist kiểm thử thực hành

Trước khi tuyên bố một pipeline sequential và parallel **tương đương**, lần lượt xác minh:

1. **Dữ liệu:** hai phiên bản có cùng nguồn logic ổn định, không bị sửa giữa lúc xử lý không?
2. **Encounter order:** nguồn là List/ordered, hay HashSet/unordered? Đã thêm `unordered()` không?
3. **Bước trung gian:** `map`/`filter`/`sorted` có cùng logic ở cả hai nhánh không?
4. **Tác dụng phụ:** callback có phụ thuộc biến ngoài, clock, random, thread ID hoặc I/O không?
5. **Giảm song song:** identity và phép gộp có associative không? Combiner có đúng không?
6. **Kiểu kết quả:** List, Set, Map, Optional, primitive hay một object domain?
7. **Phép so:** List.equals, Map.equals, Set.equals, optional equality, tolerance hoặc predicate invariant?
8. **Nhiều kết quả hợp lệ:** findAny, unordered limit có được test theo tính chất thay vì một giá trị cố định không?
9. **Thứ tự hành động:** có đang dùng forEach thay vì forEachOrdered khi order bắt buộc không?
10. **Số học:** integer overflow hoặc floating precision có ràng buộc nào chưa được kiểm tra?
11. **Collector:** custom collector có supplier/accumulator/combiner/finisher hợp đồng đúng không?
12. **Nguồn rỗng và singleton:** test có bao gồm không?
13. **Duplicates/ties:** test có phát hiện mất bản ghi, chọn sai nhóm hoặc thiếu tie-breaker không?
14. **Short-circuit:** có nhầm số callback với số phần tử kết quả không?
15. **Test ổn định:** có tránh in/so thread scheduling, Set order, giá trị findAny không?
16. **Hiệu năng:** đã tách correctness khỏi benchmark và tránh ép parallel phải nhanh hơn chưa?

## 16. Bài tập tự kiểm tra

**Bài 1.** Với `List.of(3,2,4,1)` và pipeline `filter(even).sorted().toList()`, sequential và parallel có phải ra cùng List không?

**Đáp án:** Có, với callback thuần và nguồn List ổn định; kết quả là `[2,4]`.

**Bài 2.** Có nên kiểm tra `findAny()` trên `parallelStream()` bằng cách yêu cầu kết quả bằng `findFirst()` không?

**Đáp án:** Không. Chỉ cần kết quả thuộc tập đáp ứng điều kiện; nếu nguồn không có phần tử phù hợp, Optional phải rỗng.

**Bài 3.** Hai Set có cùng phần tử nhưng thứ tự in khác có phải test fail không?

**Đáp án:** Không khi nghiệp vụ chỉ quan tâm thành viên. Dùng `Set.equals()`; nếu cần thứ tự, dùng cấu trúc/operation có thứ tự tương ứng.

**Bài 4.** Hai List cùng Set phần tử nhưng thứ tự khác, `List.equals()` cho gì?

**Đáp án:** Có thể là false vì List.equals so phần tử tại từng vị trí; nếu thứ tự là contract, đó là khác biệt cần kiểm tra.

**Bài 5.** Vì sao phép trừ không được dùng như một associative reducer song song?

**Đáp án:** `(a-b)-c` khác `a-(b-c)`; kết quả phụ thuộc cách nhóm và không đáp ứng hợp đồng reduction.

**Bài 6.** Nếu chỉ một phép `double sum()` khác ở chữ số cuối, có nên tự động bỏ test không?

**Đáp án:** Không. Phải xác định chính sách sai số phù hợp domain, xử lý NaN/∞ và cân nhắc loại số có độ chính xác cần thiết.

**Bài 7.** Một `Map<String,Long>` nhóm ở sequential và parallel có thứ tự khóa in khác nhưng cùng mapping. Phép assert nào phù hợp?

**Đáp án:** `Map.equals()` nếu thứ tự không là yêu cầu; dùng TreeMap/sort khi thứ tự báo cáo là yêu cầu.

**Bài 8.** `parallelStream().forEach(output::add)` với ArrayList chia sẻ là test hợp lệ để kiểm tra thứ tự không?

**Đáp án:** Không; chính bài test có race và không có thread safety. Dùng Collector hoặc một terminal operation phù hợp.

**Bài 9.** Vì sao test findAny nên in `findAny valid=true` thay vì phần tử được chọn?

**Đáp án:** Vì stdout của một phần tử cụ thể không được API bảo đảm, còn kết quả của phép kiểm tra tính hợp lệ có thể ổn định.

**Bài 10.** Khi nào so kết quả của `limit(3)` sequential và parallel theo đúng từng phần tử được?

**Đáp án:** Khi nguồn/pipeline có encounter order tương ứng và không có thao tác bỏ order; limit chọn tiền tố logic. Nếu có `unordered()`, không áp đặt một tiền tố cụ thể.

## 17. Tham khảo Java 17

- [Stream API: pipeline, encounter order, behavioral parameters và các tối ưu hợp lệ](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html).
- [Java Stream package summary: parallelism, ordering, side-effects và associativity](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/package-summary.html).
- [Collectors: groupingBy, groupingByConcurrent, toSet, summingInt](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Collectors.html).
- [Collector: đặc tính, combiner, identity/associativity và parallel reduction](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Collector.html).
- [DoubleStream.sum(): số học dấu phẩy động và thứ tự tính](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/DoubleStream.html#sum()).
- [List.equals()](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#equals(java.lang.Object)).
- [Set.equals()](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html#equals(java.lang.Object)).
- [Map.equals()](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html#equals(java.lang.Object)).

**Kết luận:** Đừng kiểm thử Stream song song bằng câu “mọi thứ phải giống hệt vòng lặp tuần tự”. Hãy kiểm thử **đúng hợp đồng mà API và nghiệp vụ bảo đảm**: danh sách có thứ tự thì so List chính xác; Set/Map không cần thứ tự thì so thành viên/mapping; reduction dùng toán tử associative và identity đúng; `findFirst()` theo encounter order, còn `findAny()` kiểm tra giá trị hợp lệ; số thực cần chính sách sai số. Một pipeline được xem là đúng khi kết quả đáp ứng hợp đồng **bất kể cách chia thread**, không phải khi log và lịch xử lý trông giống nhau.
